# tools/web_rag/ingest.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import re
import os, json, time, io, hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, DefaultDict, Sequence
from datetime import datetime

import requests, certifi, chardet
from dotenv import load_dotenv, find_dotenv
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 💡 중앙 LLM 관리 모듈에서 임베딩 함수 임포트
from core.llm import get_embedding_model

from settings_gatekeep import (
    gatekeep_enabled,
    url_allowed,
    _normalize_host,    # 로그 요약용 (없으면 제거해도 무방)
)

from .utils import (
    session, http_get, DATA_DIR, _truthy, _is_block_page, _looks_like_pdf_bytes,
    _looks_like_serialized_blob, _clean_text, _resolve_persist_dir, _FRESH_KEYS
)


from collections import defaultdict as _dd

# ── Metrics (optional) ───────────────────────────────────────────────────────
try:
    from tools.metrics import record_chunks as _record_chunks  # 실제 구현(환경별 상이 가능)
except Exception:
    _record_chunks = None

def record_chunks(*, chars_sum: int, chunks_cnt: int, ns: str = "", part: str = "") -> None:
    """tools.metrics.record_chunks가 어떤 시그니처든 안전하게 호출."""
    try:
        if _record_chunks is None:
            return
        try:
            import inspect
            params = set(inspect.signature(_record_chunks).parameters.keys())
        except Exception:
            params = {"chars_sum", "chunks_cnt"}  # 최소 호환 가정

        payload: dict[str, Any] = {"chars_sum": chars_sum, "chunks_cnt": chunks_cnt}
        if "ns" in params:
            payload["ns"] = ns
        if "part" in params:
            payload["part"] = part
        _record_chunks(**payload)
    except Exception:
        pass

import re as _re  # ← Naver 쿼리 간소화용


# ---- Optional: SerpAPI ----
try:
    from serpapi import GoogleSearch  # pip install google-search-results
    _HAS_SERPAPI = True
except Exception:
    _HAS_SERPAPI = False
    logger.debug("SerpAPI not available.")

# ---- Optional: Tavily ----
try:
    from tavily import TavilyClient  # pip install tavily-python
    _HAS_TAVILY = True
except Exception:
    _HAS_TAVILY = False
    logger.debug("Tavily client not available.")

# ---- RAG (Chroma + Embeddings) ----
from langchain_chroma import Chroma

# PDF 파서
try:
    import PyPDF2 as _pypdf2
except Exception:
    _pypdf2 = None

try:
    from pdfminer.high_level import extract_text as _pdfminer_extract_text
except Exception:
    _pdfminer_extract_text = None

# =============================================================================
# RAG: Documents conversion & Chroma ingestion/retrieval
# =============================================================================

def _resolve_ns(
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> str:
    if collection_name and collection_name.strip():
        return collection_name.strip()
    if namespace and namespace.strip():
        return namespace.strip()
    env_ns = (os.getenv("CHROMA_NAMESPACE") or "").strip()
    if env_ns:
        return env_ns
    topic_slug = (os.getenv("TOPIC_SLUG") or os.getenv("TOPIC") or "").strip()
    if topic_slug:
        return f"{topic_slug}-default"
    return "default"

# PDF/HTML 로더 유틸
import re as _re2
_PDF_URL_RE = _re2.compile(r"\.pdf($|\?)|filedownload|filedown(type)?=|/fileDown|/download", _re2.I)

def _looks_like_pdf_url(url: str) -> bool:
    return bool(_PDF_URL_RE.search(url or ""))

PDF_HEADERS = {"Accept": "application/pdf"}

def _fetch_binary(url: str, timeout: int = 20) -> bytes:
    r = requests.get(url, headers=PDF_HEADERS, timeout=timeout, stream=True)
    r.raise_for_status()
    return r.content

def _pdf_bytes_to_text(data: bytes) -> str:
    """
    PDF 바이트 → 텍스트
    - 환경변수:
      WEB_PDF_MAX_PAGES (기본 40): 앞쪽 N페이지까지만 추출
      WEB_PDF_MAX_CHARS (기본 200000): 추출 텍스트를 최대 N자까지 제한
    - 참고: 다운로드 바이트 가드는 상위 단계(HTTP fetch)에서 WEB_FETCH_MAX_BYTES로 처리
    """
    try:
        max_pages = int(os.getenv("WEB_PDF_MAX_PAGES", "40") or "40")
    except Exception:
        max_pages = 40
    try:
        max_chars = int(os.getenv("WEB_PDF_MAX_CHARS", "200000") or "200000")
    except Exception:
        max_chars = 200000

    # 1) PyPDF2 우선 경로 (페이지 단위 제어가 쉬움)
    if _pypdf2 is not None:
        try:
            reader = _pypdf2.PdfReader(io.BytesIO(data))
            # 암호화 PDF 처리 시도 (빈 패스워드)
            try:
                if getattr(reader, "is_encrypted", False):
                    reader.decrypt("")
            except Exception:
                pass

            n = min(max_pages, len(reader.pages))
            out_parts = []
            total_len = 0
            for i in range(n):
                try:
                    txt = reader.pages[i].extract_text() or ""
                except Exception:
                    txt = ""
                if not txt:
                    continue
                out_parts.append(txt)
                total_len += len(txt)
                if max_chars > 0 and total_len >= max_chars:
                    break

            text = ("\n".join(out_parts)).strip()
            if text:
                if max_chars > 0 and len(text) > max_chars:
                    text = text[:max_chars]
                return text
        except Exception as e:
            logger.debug("PyPDF2 extract failed; fallback to pdfminer: %s", e)

    # 2) pdfminer.six 폴백 (page_numbers로 앞쪽 N페이지만)
    if _pdfminer_extract_text is not None:
        try:
            # pdfminer는 page_numbers 인자로 추출 페이지를 제한할 수 있음
            text = _pdfminer_extract_text(io.BytesIO(data), page_numbers=list(range(max_pages))) or ""
            text = text.strip()
            if max_chars > 0 and len(text) > max_chars:
                text = text[:max_chars]
            return text
        except Exception as e:
            logger.debug("pdfminer extract failed: %s", e)

    # 3) 전부 실패
    return ""

def _load_html_as_text(url: str, timeout: int = 20) -> str:
    r = session.get(url, timeout=timeout, headers=session.headers, verify=session.verify)
    r.raise_for_status()
    html = r.text
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        import re
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s{2,}", " ", text)
        return text.strip()

def web_results_to_documents(results: Sequence[Dict[str, Any]]) -> List[Document]:
    from urllib.parse import urlparse, unquote
    docs: List[Document] = []

    def _guess_content_type_from_path(path: str, default: str = "text/plain") -> str:
        ext = Path(path).suffix.lower()
        if ext == ".pdf":
            return "application/pdf"  # 추출 텍스트지만 출처 힌트
        if ext in (".html", ".htm"):
            return "text/html"
        if ext in (".pptx", ".xlsx", ".docx"):
            return "application/vnd.openxmlformats-officedocument"  # generic hint
        if ext in (".txt", ".md", ".markdown"):
            return "text/plain"
        return default

    for item in results or []:
        url: str = (item.get("url") or item.get("source") or "").strip()
        title: str = (item.get("title") or "").strip()
        item_content: str = (item.get("content") or "").strip()
        raw_content: str = (item.get("raw_content") or "").strip()

        if not url:
            # URL이 없어도 content가 있으면 받아들임(희귀 케이스)
            if item_content:
                docs.append(Document(
                    page_content=item_content,
                    metadata={"source": "", "title": title or "(local)", "content_type": "text/plain"}
                ))
            continue

        try:
            parsed = urlparse(url)
            scheme = (parsed.scheme or "").lower()
            # 프래그먼트(#...) 제거한 정규 URL (PDF 판별/요청용)
            url_no_frag = url.split("#", 1)[0]

            # ── 1) 로컬 파일(file://) → 네트워크 요청 금지, content를 그대로 사용 ──
            if scheme == "file":
                # content가 반드시 있어야 함( local_rag 가 이미 추출함 )
                if not item_content:
                    logger.debug("file:// url but empty content; skip: %s", url)
                    continue
                file_path = unquote(parsed.path or "")
                ctype = _guess_content_type_from_path(file_path, default="text/plain")
                docs.append(Document(
                    page_content=item_content,
                    metadata={
                        "source": url,
                        "title": title or (Path(file_path).name if file_path else "Local File"),
                        "content_type": ctype,
                    },
                ))
                continue

            # ── 2) raw_content가 있으면 우선 활용(네트워크 무요청) ──
            if raw_content:
                # raw_content는 보통 HTML 텍스트. 태그 제거 후 사용.
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(raw_content, "lxml")
                    for tag in soup(["script", "style", "noscript"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n")
                    text = re.sub(r"[ \t]+", " ", text)
                    text = re.sub(r"\n{3,}", "\n\n", text).strip()
                except Exception:
                    # 최소 폴백
                    text = re.sub(r"<[^>]+>", " ", raw_content)
                    text = re.sub(r"\s{2,}", " ", text).strip()
                if text:
                    docs.append(Document(
                        page_content=text,
                        metadata={
                            "source": url,
                            "title": title or "Web",
                            "content_type": "text/html",
                        },
                    ))
                    continue  # 이 항목 처리 완료

            # ── 3) HTTP/HTTPS: PDF 의심 → 바이너리 로더 시도, 실패 시 HTML 폴백 ──
            if _looks_like_pdf_url(url_no_frag):
                try:
                    pdf_bytes = _fetch_binary(url_no_frag)
                    pdf_text = _pdf_bytes_to_text(pdf_bytes)
                    if pdf_text:
                        docs.append(Document(
                            page_content=str(pdf_text),
                            metadata={"source": url, "title": title or "PDF", "content_type": "application/pdf"},
                        ))
                        continue
                except Exception as e:
                    logger.debug("[web_rag] PDF fetch/parse failed; fallback to HTML: %s", e)

            # ── 4) HTML 로더 ──
            html_text = _load_html_as_text(url_no_frag)
            if html_text:
                docs.append(Document(
                    page_content=str(html_text),
                    metadata={"source": url, "title": title or "Web", "content_type": "text/html"},
                ))
                continue

            # ── 5) 마지막 폴백: 아이템의 content라도 사용 ──
            if item_content:
                docs.append(Document(
                    page_content=item_content,
                    metadata={"source": url, "title": title or "Web", "content_type": "text/plain"},
                ))

        except Exception as e:
            logger.warning("web_results_to_documents item fail (%s): %s", url, e)

    logger.debug("web_results_to_documents: %d docs built", len(docs))
    return docs


def web_page_json_to_documents(json_file: str) -> List[Document]:
    if not os.path.exists(json_file):
        logger.debug("web_page_json_to_documents: file not found %s", json_file)
        return []

    def _flex_load(path: str):
        txt = Path(path).read_text(encoding="utf-8")
        try:
            data = json.loads(txt)
        except json.JSONDecodeError:
            items = []
            for line in txt.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
            return items

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("results", "items", "data"):
                v = data.get(k)
                if isinstance(v, list):
                    return v
            return [data]
        return []

    try:
        resources = _flex_load(json_file) or []
    except Exception as e:
        logger.warning("web_page_json_to_documents: load failed for %s: %s", json_file, e)
        resources = []

    docs = web_results_to_documents(resources)
    logger.info("web_page_json_to_documents: %d docs from %s", len(docs), json_file)
    return docs


# ---- Vector store cache (persist_dir, collection) ----
_VS_CACHE: Dict[Tuple[str, str], Chroma] = {}
_CLEARED_ONCE_KEYS: set[tuple[str, str]] = set()

def _default_chroma_dir(namespace: str) -> str:
    return _resolve_persist_dir(namespace, persist_directory=None)

def _resolve_ns_for_docs(base_ns: str, is_web: Optional[bool]) -> tuple[str, bool]:
    """
    split NS 모드라면 (CHROMA_NAMESPACE_WEB/LOCAL 존재) 웹/로컬에 맞게 NS를 바꿔 주고,
    아니면 base_ns 그대로 반환.
    return: (ns, is_split)
    """
    ns_web = (os.getenv("CHROMA_NAMESPACE_WEB") or "").strip()
    ns_loc = (os.getenv("CHROMA_NAMESPACE_LOCAL") or "").strip()
    if ns_web and ns_loc and is_web is not None:
        return (ns_web if is_web else ns_loc), True
    return base_ns, False

def _is_web_source(meta: dict) -> Optional[bool]:
    """
    문서 메타에서 source 스킴을 보고 web/local 추정.
    - http/https → True
    - file:// 또는 로컬 경로 힌트 → False
    - 판단 불가 → None (split 모드면 base_ns로 저장)
    """
    src = (meta or {}).get("source") or ""
    s = src.strip().lower()
    if s.startswith("http://") or s.startswith("https://"):
        return True
    if s.startswith("file://"):
        return False
    # Windows 경로 힌트 (선택)
    if re.match(r"^[a-z]:[\\/]", s) or s.startswith("\\\\"):
        return False
    return None


def clear_vector_store(namespace: Optional[str] = None, persist_directory: Optional[str] = None) -> str:
    import shutil, stat, gc, time as _t

    ns = _resolve_ns(namespace=namespace, collection_name=None)
    pd = _resolve_persist_dir(ns, persist_directory)

    if (namespace is None and persist_directory is None) and os.getenv("ALLOW_GLOBAL_CLEAR", "0") != "1":
        logger.info("[INIT] clear_vector_store skipped (global clear disabled). ns='%s' dir='%s'", ns, pd)
        return pd

    vs = _VS_CACHE.pop((pd, ns), None)
    try:
        client = getattr(vs, "_client", None)
        for meth in ("persist", "reset", "teardown", "close", "stop", "shutdown"):
            fn = getattr(client, meth, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        _VS_CACHE.clear()
    except Exception:
        pass
    try:
        del vs  # type: ignore
    except Exception:
        pass
    gc.collect()
    _t.sleep(0.15)

    def _on_rm_error(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    ok = False
    for i in range(6):
        try:
            if os.path.isdir(pd):
                shutil.rmtree(pd, onerror=_on_rm_error)
            ok = True
            break
        except Exception:
            _t.sleep(0.2 * (i + 1))

    if not ok:
        try:
            if os.path.isdir(pd):
                quarantine = f"{pd}.quarantine_{int(_t.time())}"
                os.replace(pd, quarantine)
                logger.debug("[INIT] vector store quarantined → %s", quarantine)
            ok = True
        except Exception as e:
            logger.warning("[INIT] clear_vector_store failed(final): %s", e)

    try:
        os.makedirs(pd, exist_ok=True)
    except Exception as e:
        logger.warning("[INIT] re-create dir failed: %s", e)

    try:
        _FRESH_KEYS.add((pd, ns))
    except Exception:
        pass

    logger.info("[INIT] vector store cleared → ns='%s' dir='%s'", ns, pd)
    return pd

def ensure_vector_store_cleared_once(
    namespace: Optional[str] = None,
    persist_directory: Optional[str] = None,
) -> bool:
    if not (_truthy("CLEAR_ON_FIRST_VECTOR", default=None) or _truthy("CLEAR_CHROMA_ON_START", default=None)):
        return False

    ns = _resolve_ns(namespace=namespace, collection_name=None)
    pd = _resolve_persist_dir(ns, persist_directory)
    key = (pd, ns)

    if key in _CLEARED_ONCE_KEYS:
        logger.debug("[INIT] clear_once skipped (already cleared): ns='%s' dir='%s'", ns, pd)
        return False

    clear_vector_store(namespace=ns, persist_directory=pd)
    _CLEARED_ONCE_KEYS.add(key)
    logger.info("[INIT] vector store cleared once (ns='%s', dir='%s')", ns, pd)
    return True

def _get_embeddings(embedding=None):
    return embedding or get_embedding_model()

def _get_vs(collection_name: str, persist_directory: str, embedding=None) -> Chroma:
    key = (persist_directory, collection_name)
    vs = _VS_CACHE.get(key)
    if vs is None:
        vs = Chroma(
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedding_function=_get_embeddings(embedding),
        )
        _VS_CACHE[key] = vs
        logger.debug("Chroma instance created (collection=%s, dir=%s)", collection_name, persist_directory)
    return vs

def split_documents(documents: List[Document], *, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None) -> List[Document]:
    cs = int(os.getenv("RAG_CHUNK_CHARS", "2400")) if chunk_size is None else int(chunk_size)
    ov = int(os.getenv("RAG_CHUNK_OVERLAP", "200")) if chunk_overlap is None else int(chunk_overlap)
    cs = max(300, min(cs, 6000))
    ov = max(0, min(ov, int(cs * 0.5)))
    splitter = RecursiveCharacterTextSplitter(chunk_size=cs, chunk_overlap=ov)
    return splitter.split_documents(documents)

def _approx_tokens(s: str) -> int:
    return max(1, len(s or "") // 4)

def _batched_add(
    vs: Chroma,
    splits: List[Document],
    ids: Optional[List[str]] = None,
    *, 
    quarantine_dir: Optional[Path] = None,
) -> int:
    MAX_TOKENS = int(os.getenv("RAG_TOKEN_BUDGET_PER_REQ", "250000"))
    MAX_BATCH  = int(os.getenv("RAG_EMBED_BATCH", os.getenv("CHROMA_MAX_BATCH", "64")))
    total_added = 0

    if quarantine_dir is None:
        try:
            base = Path(os.getenv("CHROMA_QUARANTINE_DIR", "") or (DATA_DIR / "quarantine"))
            base.mkdir(parents=True, exist_ok=True)
            quarantine_dir = base
        except Exception:
            quarantine_dir = None

    def _write_quarantine(doc: Document, doc_id: Optional[str], err: Exception) -> None:
        if quarantine_dir is None:
            return
        try:
            payload = {
                "id": doc_id,
                "metadata": getattr(doc, "metadata", None),
                "text_head": (getattr(doc, "page_content", "") or "")[:600],
                "error": str(err),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            qf = quarantine_dir / f"quarantine_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
            qf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.warning("[CHROMA] quarantined bad doc → %s", qf)
        except Exception:
            logger.warning("[CHROMA] quarantine write failed")

    i = 0
    while i < len(splits):
        tok_sum, j = 0, i
        while j < len(splits) and (j - i) < MAX_BATCH:
            tok_sum += _approx_tokens(splits[j].page_content)
            if tok_sum > MAX_TOKENS and j > i:
                break
            j += 1

        def _try_range(lo: int, hi: int) -> int:
            n = hi - lo
            if n <= 0:
                return 0
            try:
                if ids:
                    vs.add_documents(splits[lo:hi], ids=ids[lo:hi])  # type: ignore[arg-type]
                else:
                    vs.add_documents(splits[lo:hi])
                return n
            except Exception as e:
                if n >= 2:
                    mid = lo + n // 2
                    return _try_range(lo, mid) + _try_range(mid, hi)
                _write_quarantine(splits[lo], ids[lo] if ids else None, e)
                return 0

        total_added += _try_range(i, j)
        i = j

    logger.info("batched_add: added %d chunks", total_added)
    return total_added

def documents_to_chroma(
    documents: List[Document],
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
    persist_directory: Optional[str] = None,
    embedding=None,
    clear: bool = False,
    verbose: bool = True,
) -> Tuple[int, int]:
    from typing import cast, DefaultDict as _DefaultDictT
    from chromadb.api.types import Where, Include
    from settings_gatekeep import url_allowed

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers (로컬)
    # ─────────────────────────────────────────────────────────────────────────
    def _is_web_source(meta: dict) -> Optional[bool]:
        """http/https → True, file:// or 로컬경로 → False, 판단불가 → None"""
        src = (meta or {}).get("source") or (meta or {}).get("url") or (meta or {}).get("file_path") or ""
        s = str(src).strip().lower()
        if s.startswith("http://") or s.startswith("https://"):
            return True
        if s.startswith("file://"):
            return False
        # Windows 로컬 경로 힌트
        if re.match(r"^[a-z]:[\\/]", s) or s.startswith("\\\\"):
            return False
        return None

    def _resolve_ns_for_docs(base_ns: str, is_web_flag: Optional[bool]) -> Tuple[str, bool]:
        """분리 모드면 -web/-local로 NS 분기, 아니면 base_ns 유지. (ns, split_applied)"""
        ns_web = (os.getenv("CHROMA_NAMESPACE_WEB") or "").strip()
        ns_loc = (os.getenv("CHROMA_NAMESPACE_LOCAL") or "").strip()
        if ns_web and ns_loc and (is_web_flag is not None):
            return (ns_web if is_web_flag else ns_loc), True
        return base_ns, False

    def _is_fresh_store(ns_eff: str, pd_eff: str, vs_eff) -> bool:
        """해당 NS/디렉토리가 비었는지 판정"""
        if (pd_eff, ns_eff) in _FRESH_KEYS:
            return True
        try:
            col = getattr(vs_eff, "_collection", None)
            cnt_fn = getattr(col, "count", None)
            if callable(cnt_fn) and cnt_fn() == 0:
                return True
        except Exception:
            pass
        try:
            p = Path(pd_eff)
            if p.exists():
                for _ in p.iterdir():
                    break
                else:
                    return True
        except Exception:
            pass
        return False

    def _clear_dir(pd_eff: str, ns_eff: str) -> None:
        """해당 NS 디렉터리 삭제/재생성 및 캐시 초기화"""
        _VS_CACHE.pop((pd_eff, ns_eff), None)
        try:
            import shutil
            if os.path.isdir(pd_eff):
                shutil.rmtree(pd_eff)
            os.makedirs(pd_eff, exist_ok=True)
            logger.info("documents_to_chroma: cleared vector store (%s, %s)", ns_eff, pd_eff)
        except Exception as e:
            logger.warning("documents_to_chroma: clear failed for ns=%s dir=%s: %s", ns_eff, pd_eff, e)

    # ─────────────────────────────────────────────────────────────────────────
    # Base NS/dir 및 분리 모드 판정
    # ─────────────────────────────────────────────────────────────────────────
    ns_base = _resolve_ns(namespace=namespace, collection_name=collection_name)
    pd_base = _resolve_persist_dir(ns_base, persist_directory)
    os.makedirs(pd_base, exist_ok=True)

    ns_web_env = (os.getenv("CHROMA_NAMESPACE_WEB") or "").strip()
    ns_loc_env = (os.getenv("CHROMA_NAMESPACE_LOCAL") or "").strip()
    split_mode = bool(ns_web_env and ns_loc_env)

    # clear=True면 대상 NS들을 모두 정리
    if clear:
        # 기본 NS
        _clear_dir(pd_base, ns_base)
        # 분리 모드면 -web/-local도 같이
        if split_mode:
            _clear_dir(_resolve_persist_dir(ns_web_env, persist_directory), ns_web_env)
            _clear_dir(_resolve_persist_dir(ns_loc_env, persist_directory), ns_loc_env)

    # ─────────────────────────────────────────────────────────────────────────
    # 1) 전처리(공통): 차단 텍스트/바이너리/직렬화 블랍 제거 + 정리
    # ─────────────────────────────────────────────────────────────────────────
    total_in_docs = len(documents or [])
    pre_docs: List[Document] = []
    skipped_block = 0
    for d in (documents or []):
        txt = getattr(d, "page_content", "") or ""
        if (not txt) or _is_block_page(txt) or _looks_like_pdf_bytes(txt) or _looks_like_serialized_blob(txt):
            skipped_block += 1
            continue
        d.page_content = _clean_text(txt)
        pre_docs.append(d)
    pre_docs_count = len(pre_docs)

    # ─────────────────────────────────────────────────────────────────────────
    # 2) 파티션: 웹/로컬/기타(판단불가)
    # ─────────────────────────────────────────────────────────────────────────
    web_docs: List[Document] = []
    loc_docs: List[Document] = []
    oth_docs: List[Document] = []
    for d in pre_docs:
        flag = _is_web_source(getattr(d, "metadata", {}) or {})
        if flag is True:
            web_docs.append(d)
        elif flag is False:
            loc_docs.append(d)
        else:
            oth_docs.append(d)

    # ─────────────────────────────────────────────────────────────────────────
    # 3) 파티션별 인덱싱 함수
    # ─────────────────────────────────────────────────────────────────────────
    def _ingest_partition(part_docs: List[Document], is_web_flag: Optional[bool], label: str) -> Tuple[int, int, int, int]:
        """
        return: (in_count, new_count, split_count, added_chunks)
        - in_count: part_docs 원본 개수
        - new_count: 게이트/중복 제외 후 실제 신규 문서 수
        - split_count: 청크 개수
        - added_chunks: 벡터 저장소에 실제 추가된 청크 수
        """
        if not part_docs:
            return (0, 0, 0, 0)

        ns_eff, _ = _resolve_ns_for_docs(ns_base, is_web_flag if split_mode else None)
        pd_eff = _resolve_persist_dir(ns_eff, persist_directory)
        os.makedirs(pd_eff, exist_ok=True)

        vs_eff = _get_vs(ns_eff, pd_eff, embedding)
        is_fresh = _is_fresh_store(ns_eff, pd_eff, vs_eff)
        if is_fresh:
            # fresh면 핸들 재생성 및 fresh 키 정리
            try:
                _VS_CACHE.pop((pd_eff, ns_eff), None)
            except Exception:
                pass
            vs_eff = _get_vs(ns_eff, pd_eff, embedding)
            try:
                _FRESH_KEYS.discard((pd_eff, ns_eff))
            except Exception:
                pass
            logger.debug("documents_to_chroma[%s]: fresh store — recreated handle (ns=%s dir=%s)", label, ns_eff, pd_eff)

        # 게이트/차단/중복 URL 계산(해당 NS 기준)
        # 1) 게이트/차단은 위 전처리에서 안 했으므로 여기서 처리
        filtered_docs: List[Document] = []
        skipped_gate = 0
        for d in part_docs:
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""
            if not url_allowed(src):
                skipped_gate += 1
                continue
            filtered_docs.append(d)

        # 2) 저장된 URL과 비교하여 신규만
        all_urls = {
            (getattr(d, "metadata", {}) or {}).get("source")
            for d in filtered_docs if (getattr(d, "metadata", {}) or {}).get("source")
        }
        stored_urls = set()
        if all_urls and not is_fresh:
            try:
                urls: list[str] = [u for u in all_urls if isinstance(u, str) and u]
                where_filter = {"source": {"$in": urls}}
                include = ["metadatas"]
                res = vs_eff._collection.get(  # type: ignore[attr-defined]
                    where=cast(Where, where_filter),
                    include=cast(Include, include),
                )
                for m in (res or {}).get("metadatas") or []:
                    if isinstance(m, dict) and m.get("source"):
                        stored_urls.add(m["source"])
            except Exception as e:
                logger.debug("chroma get(where=$in) failed(ns=%s): %s", ns_eff, e)
                try:
                    res = vs_eff._collection.get(include=["metadatas"])  # type: ignore[attr-defined]
                    for m in (res or {}).get("metadatas") or []:
                        if isinstance(m, dict) and m.get("source"):
                            stored_urls.add(m["source"])
                except Exception as e2:
                    logger.debug("chroma full metadatas get failed(ns=%s): %s", ns_eff, e2)
                    stored_urls = set()
        elif is_fresh:
            logger.debug("documents_to_chroma[%s]: fresh store detected; skip stored_urls check", label)

        new_documents: List[Document] = []
        for d in filtered_docs:
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""
            if src and (is_fresh or src not in stored_urls):
                new_documents.append(d)
            elif not src and is_fresh:
                new_documents.append(d)

        if not new_documents:
            if verbose:
                logger.info(
                    "documents_to_chroma(part:%s): no new urls | ns=%s dir=%s | in=%d gate_skipped=%d fresh=%s",
                    label, ns_eff, pd_eff, len(part_docs), skipped_gate, is_fresh
                )
            return (len(part_docs), 0, 0, 0)

        # 분할
        splits = split_documents(new_documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not splits:
            if verbose:
                logger.info(
                    "documents_to_chroma(part:%s): no splits | ns=%s dir=%s | in=%d new=%d",
                    label, ns_eff, pd_eff, len(part_docs), len(new_documents)
                )
            return (len(part_docs), len(new_documents), 0, 0)

        # ID 생성
        MAX_ID_CHARS = int(os.getenv("CHROMA_MAX_ID_CHARS", "128"))
        ids: List[str] = []
        counter: _DefaultDictT[str, int] = _dd(int)

        def _cap_id(s: str) -> str:
            if len(s) <= MAX_ID_CHARS:
                return s
            keep_tail = 12
            return s[: MAX_ID_CHARS - keep_tail] + s[-keep_tail:]

        for s in splits:
            src = (getattr(s, "metadata", {}) or {}).get("source", "")
            if src:
                base = hashlib.sha1(src.encode("utf-8", "ignore")).hexdigest()
                counter[base] += 1
                raw_id = f"{base}-{counter[base]:06d}"
            else:
                counter["__none__"] += 1
                raw_id = f"none-{counter['__none__']:06d}"
            ids.append(_cap_id(raw_id))

        # 업서트
        t0 = time.time()
        qdir = Path(os.getenv("CHROMA_QUARANTINE_DIR", "") or (Path(pd_eff) / "quarantine"))
        try:
            qdir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        try:
            added_chunks = _batched_add(vs_eff, splits, ids, quarantine_dir=qdir)
        except Exception as e:
            logger.warning("documents_to_chroma(part:%s): batched_add raised — forcing single upserts: %s", label, e)
            added_chunks = 0
            for k, doc in enumerate(splits):
                try:
                    if ids:
                        vs_eff.add_documents([doc], ids=[ids[k]])
                    else:
                        vs_eff.add_documents([doc])
                    added_chunks += 1
                except Exception as e2:
                    logger.warning("single upsert failed(part:%s) at %d: %s", label, k, e2)

        # persist
        persist_fn = getattr(vs_eff, "persist", None)
        if callable(persist_fn):
            try:
                persist_fn()
            except Exception as e:
                logger.debug("vs.persist failed(ns=%s) (ignored): %s", ns_eff, e)
        else:
            client = getattr(vs_eff, "_client", None)
            client_persist = getattr(client, "persist", None)
            if callable(client_persist):
                try:
                    client_persist()
                except Exception as e:
                    logger.debug("client.persist failed(ns=%s) (ignored): %s", ns_eff, e)

        # 요약 로그
        try:
            total_chars = sum(len(d.page_content or "") for d in splits)
            avg_len = int(total_chars / len(splits)) if splits else 0
        except Exception:
            avg_len = 0

        elapsed = time.time() - t0
        logger.info(
            "documents_to_chroma(part:%s): %d docs → %d chunks (ns=%s, dir=%s) | new=%d, splits=%d, avg_chunk_chars=%d, time=%.2fs",
            label, len(part_docs), added_chunks, ns_eff, pd_eff, len(new_documents), len(splits), avg_len, elapsed
        )
        # [METRICS] 파티션 단위 청크 길이/개수 집계
        try:
            total_chars_for_splits = sum(len(d.page_content or "") for d in splits)
            # 업서트 실패로 일부 빠질 수 있어 'added_chunks' 기준으로 개수 기록
            record_chunks(chars_sum=total_chars_for_splits, chunks_cnt=added_chunks, ns=ns_eff, part=label)
        except Exception:
            pass
        return (len(part_docs), len(new_documents), len(splits), added_chunks)

    # ─────────────────────────────────────────────────────────────────────────
    # 4) 인덱싱 실행 (분리 모드면 웹/로컬/기타 각각, 아니면 단일로)
    # ─────────────────────────────────────────────────────────────────────────
    if split_mode:
        in_w, new_w, spl_w, add_w = _ingest_partition(web_docs, True,  "web")
        in_l, new_l, spl_l, add_l = _ingest_partition(loc_docs, False, "local")
        in_o, new_o, spl_o, add_o = _ingest_partition(oth_docs, None,  "base")
        total_added = add_w + add_l + add_o
        split_count = spl_w + spl_l + spl_o
        new_docs_count = new_w + new_l + new_o
        skipped_gate_total = None  # 파티션 내부에서만 집계, 상단 요약에선 생략
        pd_for_log = f"{pd_base} (split: web={_resolve_persist_dir(ns_web_env, persist_directory)}, local={_resolve_persist_dir(ns_loc_env, persist_directory)})"
    else:
        # 단일 NS 경로: pre_docs 전체를 base_ns로
        in_b, new_b, spl_b, add_b = _ingest_partition(pre_docs, None, "base")
        total_added = add_b
        split_count = spl_b
        new_docs_count = new_b
        pd_for_log = _resolve_persist_dir(ns_base, None)

    # ─────────────────────────────────────────────────────────────────────────
    # 5) 최종 요약 로그 & 반환
    # ─────────────────────────────────────────────────────────────────────────
    logger.info(
        ("documents_to_chroma: %d docs → %d chunks (ns=%s, dir=%s, split=%s) | "
         "in=%d, pre=%d, blocked=%d, new=%d, splits=%d"),
        total_in_docs, total_added, ns_base, pd_for_log, split_mode,
        total_in_docs, pre_docs_count, skipped_block, new_docs_count, split_count
    )
    # [METRICS](optional) 전체 요약 — 총 청크 개수만 집계, 길이 합은 파티션 단위에서 더 정확히 기록됨
    try:
        record_chunks(chars_sum=0, chunks_cnt=total_added, ns=ns_base, part="summary")
    except Exception:
        pass
    return (total_in_docs, total_added)


def add_web_pages_json_to_chroma(
    json_file: str,
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
    persist_directory: Optional[str] = None,
    embedding=None,
    clear: bool = False,
) -> Tuple[int, int]:
    documents = web_page_json_to_documents(json_file)
    return documents_to_chroma(
        documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        namespace=namespace,
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding=(embedding or _get_embeddings()),
        clear=clear,
    )

@tool("retrieve")
def retrieve(
    query: str,
    *,
    top_k: int = 5,
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
    persist_directory: Optional[str] = None,
    embedding=None,
):
    """
    세션/주제별 Chroma 컬렉션에서 RAG 검색 (고속 경로 + 친절한 예외 메시지)
    """
    q = (query or "").strip()
    if not q:
        return []

    qL = q.lower()
    if qL.startswith("local:"):
        logger.debug("[retrieve] skip local/glob query: %s", query)
        return []
    if any(tok in q for tok in ("**\\", "**/", "\\*.", "/*.", "\\**", "/**")):
        logger.debug("[retrieve] skip glob-like query: %s", query)
        return []

    ns = _resolve_ns(namespace=namespace, collection_name=collection_name)
    pd = _resolve_persist_dir(ns, persist_directory)
    vs = _get_vs(ns, pd, embedding)

    emb_fn = getattr(vs, "_embedding_function", None) or embedding or _get_embeddings(embedding)

    try:
        q_emb = emb_fn.embed_query(q) if hasattr(emb_fn, "embed_query") else emb_fn(q)  # type: ignore
        n = max(1, int(top_k or 5))
        res = vs._collection.query(  # type: ignore[attr-defined]
            query_embeddings=[q_emb],
            n_results=n,
            include=["documents", "metadatas"],
        )

        docs_out = []
        docs = (res or {}).get("documents") or []
        metas = (res or {}).get("metadatas") or []
        if docs and isinstance(docs, list):
            rows = zip(docs[0] if docs else [], metas[0] if metas else [])
            for doc_text, meta in rows:
                text = (doc_text or "")
                if len(text) > 19000:
                    text = text[:19000]
                m = meta if isinstance(meta, dict) else {}
                docs_out.append(Document(page_content=text, metadata=m))
        logger.debug("[retrieve-fast] ns=%s dir=%s k=%d → %d docs", ns, pd, n, len(docs_out))
        return docs_out

    except Exception as e:
        emsg = (str(e) or "").lower()
        mismatch_signals = (
            "dimension" in emsg or
            ("embed" in emsg and "mismatch" in emsg) or
            ("expected" in emsg and "got" in emsg and "dimension" in emsg)
        )
        if mismatch_signals:
            raise RuntimeError(
                "Vector query failed due to a likely embedding model/dimension mismatch between "
                "ingestion and retrieval.\n\n"
                "How to fix:\n"
                "   • Ensure the SAME embedding model is used for both ingestion and retrieval.\n"
                "   • If you pass a custom `embedding=` here, it must match the one used to build this collection.\n"
                "   • Otherwise, omit `embedding` so the vector store’s existing embedding function is reused."
            ) from e

        logger.debug("[retrieve-fast] direct query failed; falling back to retriever: %s", e)

    retriever = vs.as_retriever(search_kwargs={"k": max(1, int(top_k or 5))})
    results = retriever.invoke(q)
    out = []
    for d in (results or []):
        text = d.page_content or ""
        if len(text) > 19000:
            text = text[:19000]
        d.page_content = text
        out.append(d)
    logger.debug("[retrieve-fallback] ns=%s dir=%s k=%d → %d docs", ns, pd, top_k, len(out))
    return out

# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "web_results_to_documents",
    "web_page_json_to_documents",
    "documents_to_chroma",
    "add_web_pages_json_to_chroma",
    "retrieve",
    "clear_vector_store",
    "ensure_vector_store_cleared_once",
    "_default_chroma_dir",
]