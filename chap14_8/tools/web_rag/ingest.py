# tools/web_rag/ingest.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os, re, io, json, time, hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Sequence, Callable, Any
from types import ModuleType

import requests
from requests.exceptions import SSLError as _SSLError
import certifi

# [PATCH SSL-1] 안전 태깅용 커스텀 예외 + 재시도 후보 기록기
class _PdfSslError(_SSLError):
    """PDF 다운로드 중 SSL 오류. verify=False 폴백 없이 상부에서 처리하도록 신호."""
    pass

# ── CFG helpers (ENV 직접 접근 금지) ─────────────────────────────────────────
def _cfg_str(key: str, default: str = "") -> str:
    try:
        v = getattr(CFG, key)
        return (str(v).strip() if v is not None else default)
    except Exception:
        return default

def _cfg_bool(key: str, default: bool = False) -> bool:
    try:
        v = getattr(CFG, key)
        return bool(v)
    except Exception:
        return default

def _cfg_int(key: str, default: int) -> int:
    try:
        v = getattr(CFG, key)
        if v is None or v == "":
            return default
        return int(str(v).strip())
    except Exception:
        return default


def _record_retry_candidate(url: str, reason: str = "ssl_error") -> None:
    """
    재시도 후보를 jsonl로 남깁니다. (예: DATA_DIR/retry_candidates.jsonl)
    분석/재처리 파이프라인에서 이 파일을 스캔하여 재시도할 수 있습니다.
    """
    try:
        base_dir = _cfg_str("RETRY_CANDIDATE_DIR", "")
        base = Path(base_dir) if base_dir else (DATA_DIR / "quarantine")
        base.mkdir(parents=True, exist_ok=True)
        f = base / "ingest_retry_candidates.jsonl"
        payload = {"url": url, "reason": reason, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        with f.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        logger.warning("[INGEST][RETRY] tagged %s as %s → %s", url, reason, f)
    except Exception:
        logger.debug("[INGEST][RETRY] failed to record retry-candidate: %s (%s)", url, reason)

from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 중앙 LLM(임베딩) 헬퍼
from core.llm import get_embedding_model
from core.config import CFG
from core.config import reload_config as reload_config  # in-place 갱신만 허용

# 게이트키핑/호스트 정규화
from settings_gatekeep import (
    gatekeep_enabled,
    url_allowed,
    _normalize_host,  # 로그용 (없으면 제거 가능)
)

# web_rag 유틸 모듈
from .utils import (
    session, http_get, DATA_DIR, _is_block_page, _looks_like_pdf_bytes,
    _looks_like_serialized_blob, _clean_text, _resolve_persist_dir, _FRESH_KEYS
)

from collections import defaultdict as _dd

# ── incoming/seen hash helpers ────────────────────────────────────────────────
def _seen_hash_path(ns: str, pd: str) -> Path:
    """네임스페이스/퍼시스트디렉터리별 seen-hash 저장 경로."""
    base = Path(pd)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{ns}.__seen_sources__.json"

def _source_hash(title: str, url: str, content: str, raw: str, ctype: str) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update((title or "").encode("utf-8", "ignore"))
    h.update((url or "").encode("utf-8", "ignore"))
    # content가 없으면 raw_content를 사용 (PDF/HTML 원문 포함 가능)
    if content:
        h.update(content.encode("utf-8", "ignore"))
    elif raw:
        h.update(raw.encode("utf-8", "ignore"))
    h.update((ctype or "").encode("utf-8", "ignore"))
    return h.hexdigest()

def _compute_incoming_hashes(json_path: str) -> dict[str, str]:
    """web.json(배열/ndjson/래핑)에서 {source:hash} 맵 생성."""
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
        items = _flex_load(json_path) or []
    except Exception:
        return {}

    out: dict[str, str] = {}
    for r in items:
        if not isinstance(r, dict):
            continue
        url = (r.get("url") or r.get("source") or "").strip()
        if not url:
            continue
        title   = (r.get("title") or "").strip()
        content = (r.get("content") or r.get("snippet") or "").strip()
        raw     = (r.get("raw_content") or "").strip()
        ctype   = (r.get("content_type") or r.get("mime") or "").strip()
        out[url] = _source_hash(title, url, content, raw, ctype)
    return out

def _load_seen_source_hashes(ns: str, pd: str) -> dict[str, str]:
    p = _seen_hash_path(ns, pd)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_seen_source_hashes(ns: str, pd: str, m: dict[str, str]) -> None:
    p = _seen_hash_path(ns, pd)
    try:
        p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("[ingest] save seen hashes failed: %s", p)

# ── Metrics (optional) ───────────────────────────────────────────────────────
# mypy 친화적: Optional[Callable[..., Any]]로 선언해 None 대입 허용
from typing import Callable as _CallableAny
_record_chunks: Optional[_CallableAny[..., Any]]
try:
    from tools.metrics import record_chunks as _record_chunks
except Exception:
    _record_chunks = None

def record_chunks(*, chars_sum: int, chunks_cnt: int, ns: str = "", part: str = "") -> None:
    """환경별 metrics.record_chunks 시그니처 차이를 흡수하는 안전 래퍼."""
    try:
        if _record_chunks is None:
            return
        try:
            import inspect
            params = set(inspect.signature(_record_chunks).parameters.keys())
        except Exception:
            params = {"chars_sum", "chunks_cnt"}  # 최소 호환
        payload: dict[str, Any] = {"chars_sum": chars_sum, "chunks_cnt": chunks_cnt}
        if "ns" in params:   payload["ns"] = ns
        if "part" in params: payload["part"] = part
        _record_chunks(**payload)
    except Exception:
        pass

# ---- 선택적 백엔드(존재시 사용, 미설치 OK) ----
try:
    import PyPDF2 as _pypdf2_mod
    _pypdf2: Optional[ModuleType] = _pypdf2_mod  # mypy-friendly: 모듈 또는 None
except Exception:
    _pypdf2 = None

try:
    from pdfminer.high_level import extract_text as _pdfminer_extract_text_mod
    # pdfminer의 extract_text는 다양한 시그니처를 가지므로 가변 콜러블로 표기
    from typing import Callable as _CallableStr
    _pdfminer_extract_text: Optional[_CallableStr[..., str]] = _pdfminer_extract_text_mod
except Exception:
    _pdfminer_extract_text = None

# ---- Chroma ----
from langchain_chroma import Chroma

# =============================================================================
# RAG: Documents conversion & Chroma ingestion/retrieval
# =============================================================================

def _resolve_ns(
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> str:
    """
    네임스페이스 결정 우선순위:
      1) collection_name
      2) namespace
      3) CFG.CHROMA_NAMESPACE
      4) CFG.TOPIC_SLUG (suffix -default)
      5) "default"
    """
    if collection_name and collection_name.strip():
        return collection_name.strip()
    if namespace and namespace.strip():
        return namespace.strip()
    env_ns = (getattr(CFG, "CHROMA_NAMESPACE", "") or "").strip()
    if env_ns:
        return env_ns
    topic_slug = (getattr(CFG, "TOPIC_SLUG", "") or "").strip()
    if topic_slug:
        return f"{topic_slug}-default"
    return "default"

# PDF/HTML 로더 유틸
import re as _re2
_PDF_URL_RE = _re2.compile(r"\.pdf($|\?)|filedownload|filedown(type)?=|/fileDown|/download", _re2.I)

def _looks_like_pdf_url(url: str) -> bool:
    return bool(_PDF_URL_RE.search(url or ""))

_PDF_HEADERS = {"Accept": "application/pdf"}

def _allow_insecure_ssl() -> bool:
    return _cfg_bool("ALLOW_INSECURE_SSL", False)

def _fetch_binary(url: str, timeout: int = 10) -> bytes:
    """
    PDF/바이너리 안전 가져오기:
      - 항상 certifi 번들로 검증(verify=certifi.where()).
      - SSLError 시 verify=False 폴백은 하지 않음.
      - 대신 상위 로직이 재시도 후보로 태깅할 수 있도록 _PdfSslError를 발생.
    """
    try:
        r = requests.get(
            url,
            headers=_PDF_HEADERS,
            timeout=timeout,
            stream=True,
            verify=certifi.where(),
        )
        r.raise_for_status()
        return r.content
    except _SSLError as e:
        # 상부에서 태깅 후 HTML 폴백 시도/스킵 결정을 하도록 신호
        raise _PdfSslError(str(e))
    except Exception:
        raise


def _pdf_bytes_to_text(data: bytes) -> str:
    """
    PDF 바이트 → 텍스트
      WEB_PDF_MAX_PAGES (기본 40)
      WEB_PDF_MAX_CHARS (기본 200000)
    """
    max_pages = _cfg_int("WEB_PDF_MAX_PAGES", 40)
    max_chars = _cfg_int("WEB_PDF_MAX_CHARS", 200_000)

    # 1) PyPDF2 우선
    if _pypdf2 is not None:
        try:
            reader = _pypdf2.PdfReader(io.BytesIO(data))
            try:
                if getattr(reader, "is_encrypted", False):
                    reader.decrypt("")
            except Exception:
                pass

            n = min(max_pages, len(reader.pages))
            out_parts, total_len = [], 0
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

    # 2) pdfminer 폴백
    if _pdfminer_extract_text is not None:
        try:
            text = _pdfminer_extract_text(io.BytesIO(data), page_numbers=list(range(max_pages))) or ""
            text = text.strip()
            if max_chars > 0 and len(text) > max_chars:
                text = text[:max_chars]
            return text
        except Exception as e:
            logger.debug("pdfminer extract failed: %s", e)

    return ""

def _load_html_as_text(url: str, timeout: int = 10) -> str:
    """
    HTML 페이지 로딩:
      - 1차: session.get(..., verify=session.verify) 시도
      - SSLError 발생 & ALLOW_INSECURE_SSL=1 이면 requests.get(..., verify=False) 1회 폴백
    """
    try:
        r = session.get(url, timeout=timeout, headers=session.headers, verify=session.verify)
        r.raise_for_status()
    except _SSLError:
        if _allow_insecure_ssl():
            logger.warning("[SSL] SSLError on %s — retrying once with verify=False (ALLOW_INSECURE_SSL=1)", url)
            r = requests.get(url, timeout=timeout, headers=session.headers, verify=False)
            r.raise_for_status()
        else:
            raise

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
    """
    web.json 항목(또는 검색 결과 dict 리스트)을 LangChain Document 리스트로 변환.
    - file:// 은 네트워크 요청 없이 item.content 사용
    - raw_content(HTML)가 있으면 패스 1로 처리
    - PDF 스멜나면 PDF 바이트 로더 우선, 실패시 HTML 폴백
    """
    from urllib.parse import urlparse, unquote
    docs: List[Document] = []

    def _guess_content_type_from_path(path: str, default: str = "text/plain") -> str:
        ext = Path(path).suffix.lower()
        if ext == ".pdf": return "application/pdf"
        if ext in (".html", ".htm"): return "text/html"
        if ext in (".pptx", ".xlsx", ".docx"): return "application/vnd.openxmlformats-officedocument"
        if ext in (".txt", ".md", ".markdown"): return "text/plain"
        return default

    for item in results or []:
        url: str = (item.get("url") or item.get("source") or "").strip()
        title: str = (item.get("title") or "").strip()
        item_content: str = (item.get("content") or "").strip()
        raw_content: str = (item.get("raw_content") or "").strip()

        if not url:
            if item_content:
                docs.append(Document(
                    page_content=item_content,
                    metadata={"source": "", "title": title or "(local)", "content_type": "text/plain"}
                ))
            continue

        try:
            parsed = urlparse(url)
            scheme = (parsed.scheme or "").lower()
            url_no_frag = url.split("#", 1)[0]

            # 1) file:// — content만 사용
            if scheme == "file":
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

            # 2) raw_content 우선 (보통 HTML)
            if raw_content:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(raw_content, "lxml")
                    for tag in soup(["script", "style", "noscript"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n")
                    import re
                    text = re.sub(r"[ \t]+", " ", text)
                    text = re.sub(r"\n{3,}", "\n\n", text).strip()
                except Exception:
                    import re
                    text = re.sub(r"<[^>]+>", " ", raw_content)
                    text = re.sub(r"\s{2,}", " ", text).strip()

                if text:
                    docs.append(Document(
                        page_content=text,
                        metadata={"source": url, "title": title or "Web", "content_type": "text/html"},
                    ))
                    continue

            # 3) PDF 의심 → PDF 파서 우선, 실패 시 HTML 폴백
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
                except _PdfSslError:
                    # ✅ SSL 오류: 재시도 후보로 태깅하고 HTML 폴백 시도
                    _record_retry_candidate(url_no_frag, reason="ssl_error")
                    logger.warning("[INGEST][SSL] ssl_error tagged & skipped PDF parse → fallback to HTML: %s", url_no_frag)
                except Exception as e:
                    logger.debug("[web_rag] PDF fetch/parse failed; fallback to HTML: %s", e)

            # 4) HTML 로더
            html_text = _load_html_as_text(url_no_frag)
            if html_text:
                docs.append(Document(
                    page_content=str(html_text),
                    metadata={"source": url, "title": title or "Web", "content_type": "text/html"},
                ))
                continue

            # 5) 마지막 폴백: item.content
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
    """web.json(배열/NDJSON/단일 dict/래핑 dict)을 유연하게 읽어 Document 리스트로 변환."""
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

    # ... 데이터 래핑 해제 ...
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

# 런타임 중 중복 초기화 방지(프로세스 수명 내 1회) 가드
_CLEARED_RUNTIME_KEYS: set[tuple[str, str]] = set()

def _clear_once_guard(pd: str, ns: str, *, reason: str = "") -> bool:
    if _cfg_bool("CLEAR_GUARD_DISABLE", False):
        return True
    key = (pd, ns)
    if key in _CLEARED_RUNTIME_KEYS:
        logger.debug("[INIT] clear skipped (once-guard): ns='%s' dir='%s' reason=%s", ns, pd, reason or "-")
        return False
    _CLEARED_RUNTIME_KEYS.add(key)
    return True


def _resolve_ns_for_docs(base_ns: str, is_web: Optional[bool]) -> tuple[str, bool]:
    """
    split NS 모드면 CHROMA_NAMESPACE_WEB/LOCAL 중 하나를 사용.
    아니면 base_ns 유지. (ns, split_applied)
    """
    ns_web = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    if ns_web and ns_loc and is_web is not None:
        return (ns_web if is_web else ns_loc), True
    return base_ns, False

def _is_web_source(meta: dict) -> Optional[bool]:
    """http/https → True, file:// 또는 로컬경로 → False, 판단불가 → None"""
    src = (meta or {}).get("source") or ""
    s = src.strip().lower()
    if s.startswith("http://") or s.startswith("https://"):
        return True
    if s.startswith("file://"):
        return False
    if re.match(r"^[a-z]:[\\/]", s) or s.startswith("\\\\"):
        return False
    return None

def _extract_local_path(meta: dict) -> Optional[str]:
    """
    Document 메타에서 로컬 경로를 추출합니다.
    우선순위: file_path → source(file:// 또는 로컬 경로) → url
    """
    from urllib.parse import urlparse, unquote
    src = (meta or {}).get("file_path") or (meta or {}).get("source") or (meta or {}).get("url") or ""
    s = (src or "").strip()
    if not s:
        return None
    # file:// 스킴
    if s.lower().startswith("file://"):
        try:
            parsed = urlparse(s)
            return unquote(parsed.path or "") or None
        except Exception:
            return None
    # Windows/UNC or POSIX 경로
    import re as _re
    if _re.match(r"^[a-zA-Z]:[\\/]", s) or s.startswith("\\\\") or s.startswith("/"):
        return s
    return None


def _local_mtime_key(meta: dict) -> str:
    """
    로컬 파일이면 mtime(초단위 정수)을 문자열로 반환. 없으면 "".
    """
    try:
        p = _extract_local_path(meta) or ""
        if not p:
            return ""
        import os
        ts = os.path.getmtime(p)
        return str(int(ts))
    except Exception:
        return ""

def clear_vector_store(namespace: Optional[str] = None, persist_directory: Optional[str] = None) -> str:
    """
    벡터 저장소 디렉터리를 제거 후 재생성. 캐시/핸들도 함께 초기화.
    글로벌(인자 둘 다 None) 클리어는 ENV ALLOW_GLOBAL_CLEAR=1 일 때만 허용.
    """
    import shutil, stat, gc, time as _t

    ns = _resolve_ns(namespace=namespace, collection_name=None)
    pd = _resolve_persist_dir(ns, persist_directory)

    # 런타임 가드: 동일 (pd, ns) 중복 초기화를 억제
    if not _clear_once_guard(pd, ns, reason="clear_vector_store()"):
        return pd

    if (namespace is None and persist_directory is None) and (not _cfg_bool("ALLOW_GLOBAL_CLEAR", False)):
        logger.info("[INIT] clear_vector_store skipped (global clear disabled). ns='%s' dir='%s'", ns, pd)
        return pd

    vs = _VS_CACHE.pop((pd, ns), None)
    try:
        client = getattr(vs, "_client", None)
        for meth in ("persist", "reset", "teardown", "close", "stop", "shutdown"):
            fn = getattr(client, meth, None)
            if callable(fn):
                try: fn()
                except Exception: pass
    except Exception:
        pass
    try: _VS_CACHE.clear()
    except Exception: pass
    vs = None  # drop reference for GC
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
    """
    한 번만 초기 클리어. 트리거: CFG.CLEAR_CHROMA_ON_START 또는
    ENV CLEAR_ON_FIRST_VECTOR/CLEAR_CHROMA_ON_START.
    """
    if not (_cfg_bool("CLEAR_CHROMA_ON_START", False) or
            _cfg_bool("CLEAR_ON_FIRST_VECTOR", False)):
        return False

    ns = _resolve_ns(namespace=namespace, collection_name=None)
    pd = _resolve_persist_dir(ns, persist_directory)
    key = (pd, ns)

    # 런타임 가드도 동시에 마킹(중복 초기화/로그 억제)
    if key in _CLEARED_RUNTIME_KEYS:
        logger.debug("[INIT] clear_once skipped (runtime-guard already cleared): ns='%s' dir='%s'", ns, pd)
        return False

    if key in _CLEARED_ONCE_KEYS:
        logger.debug("[INIT] clear_once skipped (already cleared): ns='%s' dir='%s'", ns, pd)
        return False

    clear_vector_store(namespace=ns, persist_directory=pd)
    _CLEARED_ONCE_KEYS.add(key)
    _CLEARED_RUNTIME_KEYS.add(key)
    logger.info("[INIT] vector store cleared once (ns='%s', dir='%s')", ns, pd)
    return True

# ─────────────────────────────────────────────────────────────────────────────
# 임베딩 모델 선택/로그 강화 (정적체커 안전 호출)
# ─────────────────────────────────────────────────────────────────────────────
import inspect

def _resolve_embedding_model_name() -> str:
    """임베딩 모델 결정: RAG_EMBEDDING_MODEL → GEMINI_EMBEDDING_MODEL → 'text-embedding-004'."""
    name = (getattr(CFG, "RAG_EMBEDDING_MODEL", "") or "").strip()
    if not name:
        name = (getattr(CFG, "GEMINI_EMBEDDING_MODEL", "") or "").strip()
    if not name:
        name = "text-embedding-004"
    return name

def _get_embeddings(embedding=None):
    """
    - 외부에서 embedding 주입 시 그대로 사용
    - 아니면 get_embedding_model의 실제 시그니처를 점검해
      (무인자 | model_name= | model=) 중 가능한 방식으로 호출
    - 정적체커 충돌 회피를 위해 Any 캐스팅 사용
    """
    if embedding is not None:
        return embedding
    model_name = _resolve_embedding_model_name()
    ctor: Any = get_embedding_model  # 정적체커 회피

    try:
        params = list(inspect.signature(ctor).parameters.keys())
    except Exception:
        params = []

    try:
        if not params:
            # 무인자
            emb = ctor()
            used = "no-arg"
        elif "model_name" in params:
            emb = ctor(model_name=model_name)
            used = "model_name"
        elif "model" in params:
            emb = ctor(model=model_name)
            used = "model"
        else:
            # 알 수 없는 케이스 → 무인자 폴백
            emb = ctor()
            used = "fallback:no-arg"
    except TypeError:
        # 런타임 타입 에러시 최종 폴백
        emb = ctor()
        used = "fallback:typeerror:no-arg"
    except Exception:
        emb = ctor(); used = "fallback:exception:no-arg"

    try:
        logger.info("[ingest] embedding model resolved: %s (ctor=%s, via=%s)",
                    model_name, getattr(ctor, "__name__", str(ctor)), used)
    except Exception:
        pass

    return emb


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
    cs = (_cfg_int("RAG_CHUNK_CHARS", 2400) if chunk_size is None else int(chunk_size))
    ov = (_cfg_int("RAG_CHUNK_OVERLAP", 200) if chunk_overlap is None else int(chunk_overlap))
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
    max_seconds: Optional[int] = None,
) -> int:
    """
    Chroma add_documents 배치 업서트.
    - 토큰/배치 제한
    - 실패 시 이분탐색/단건 업서트
    - max_seconds 초과 시 남은 배치는 중단 (진단을 위한 워치독)
    """
    MAX_TOKENS = _cfg_int("RAG_TOKEN_BUDGET_PER_REQ", 250_000)
    MAX_BATCH  = (_cfg_int("RAG_EMBED_BATCH", _cfg_int("CHROMA_MAX_BATCH", 64)))
    total_added = 0
    t_start = time.time()

    if quarantine_dir is None:
        try:
            qdir = _cfg_str("CHROMA_QUARANTINE_DIR", "")
            base = Path(qdir) if qdir else (DATA_DIR / "quarantine")
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
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            qf = quarantine_dir / f"quarantine_{time.strftime('%Y%m%d_%H%M%S')}_{hashlib.sha1((doc_id or str(time.time())).encode()).hexdigest()[:8]}.json"
            qf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.warning("[CHROMA] quarantined bad doc → %s", qf)
        except Exception:
            logger.warning("[CHROMA] quarantine write failed")

    i = 0
    while i < len(splits):
        # 워치독: 전체 인덱싱 시간 상한
        if max_seconds and (time.time() - t_start) > max_seconds:
            logger.error("[INDEX][TIMEOUT] exceeded %ss — stopping remaining batches (%d/%d processed)",
                         max_seconds, i, len(splits))
            break

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
                    vs.add_documents(splits[lo:hi], ids=ids[lo:hi])
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
    """
    Documents → split → Chroma 인덱싱.
    return: (in_docs_count, added_chunks)
    """
    from typing import cast, Any, DefaultDict as _DefaultDictT
    from chromadb.api.types import Include

    # 임베딩 모델 로깅(선행)
    try:
        emb_name = _resolve_embedding_model_name()
        logger.info("[ingest] embedding provider=%s model=%s",
                    (getattr(CFG, "LLM_PROVIDER", "") or "unknown"),
                    emb_name)
    except Exception:
        pass

    # Base NS/dir 및 split 모드 여부
    ns_base = _resolve_ns(namespace=namespace, collection_name=collection_name)
    pd_base = _resolve_persist_dir(ns_base, persist_directory)
    os.makedirs(pd_base, exist_ok=True)

    ns_web_env = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc_env = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    split_mode = bool(ns_web_env and ns_loc_env)

    # clear=True면 대상 NS 모두 초기화
    # (중략 — 기존 clear_once_guard 패치 적용부 유지)
    if clear:
        def _clear_dir(pd_eff: str, ns_eff: str, *, label: str) -> bool:
            _VS_CACHE.pop((pd_eff, ns_eff), None)
            # 런타임 가드: 동일 (pd, ns) 재초기화 방지
            if not _clear_once_guard(pd_eff, ns_eff, reason=f"documents_to_chroma(clear, part={label})"):
                return False
            try:
                import shutil
                if os.path.isdir(pd_eff):
                    shutil.rmtree(pd_eff)
                os.makedirs(pd_eff, exist_ok=True)
                logger.info("documents_to_chroma: cleared vector store (ns=%s, dir=%s, part=%s)", ns_eff, pd_eff, label)
            except Exception as e:
                logger.warning("documents_to_chroma: clear failed for ns=%s dir=%s: %s", ns_eff, pd_eff, e)
            return True

        cleared_labels: list[str] = []
        if _clear_dir(pd_base, ns_base, label="base"):
            cleared_labels.append("base")
        if split_mode:
            if _clear_dir(_resolve_persist_dir(ns_web_env, persist_directory), ns_web_env, label="web"):
                cleared_labels.append("web")
            if _clear_dir(_resolve_persist_dir(ns_loc_env, persist_directory), ns_loc_env, label="local"):
                cleared_labels.append("local")
        # 요약 로그(다중 노출 대신 1회 요약)
        if cleared_labels:
            logger.info("[INIT] vector store cleared once (%s) — ns_base=%s dir_base=%s split=%s",
                        ",".join(cleared_labels), ns_base, pd_base, bool(split_mode))
        else:
            logger.debug("[INIT] clear skipped by runtime guard (already cleared earlier)")

    # 1) 블럭/이상치 제거 및 텍스트 정리
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

        # (옵션) 로컬 파일이면 메타에 mtime 버전을 주입
        try:
            if _cfg_bool("RAG_ID_INCLUDE_MTIME", True):
                md = getattr(d, "metadata", {}) or {}
                ver = _local_mtime_key(md)
                if ver:
                    md["source_version"] = ver
                    # LangChain Document는 metadata dict 재할당을 허용합니다.
                    try:
                        d.metadata = md
                    except Exception:
                        pass
        except Exception:
            pass
    pre_docs_count = len(pre_docs)

    # 2) 웹/로컬/기타 파티션
    web_docs, loc_docs, oth_docs = [], [], []
    for d in pre_docs:
        flag = _is_web_source(getattr(d, "metadata", {}) or {})
        if flag is True:   web_docs.append(d)
        elif flag is False: loc_docs.append(d)
        else:               oth_docs.append(d)

    # 3) 파티션 인덱싱 함수
    def _ingest_partition(part_docs: List[Document], is_web_flag: Optional[bool], label: str) -> Tuple[int, int, int, int]:
        """
        return: (in_count, new_count, split_count, added_chunks)
        """
        if not part_docs:
            return (0, 0, 0, 0)

        ns_eff, _ = _resolve_ns_for_docs(ns_base, is_web_flag if split_mode else None)
        pd_eff = _resolve_persist_dir(ns_eff, persist_directory)
        os.makedirs(pd_eff, exist_ok=True)

        vs_eff = _get_vs(ns_eff, pd_eff, embedding)

        # fresh 판정
        def _is_fresh_store() -> bool:
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

        is_fresh = _is_fresh_store()
        if is_fresh:
            try: _VS_CACHE.pop((pd_eff, ns_eff), None)
            except Exception: pass
            vs_eff = _get_vs(ns_eff, pd_eff, embedding)
            try: _FRESH_KEYS.discard((pd_eff, ns_eff))
            except Exception: pass
            logger.debug("documents_to_chroma[%s]: fresh store — recreated handle (ns=%s dir=%s)", label, ns_eff, pd_eff)

        # 게이트키핑
        filtered_docs, skipped_gate = [], 0
        for d in part_docs:
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""
            if src and not url_allowed(src):
                skipped_gate += 1
                continue
            filtered_docs.append(d)

        # 신규/변경 판단을 위한 (source, version) 수집
        def _sv_pair(d) -> tuple[str, str]:
            m = getattr(d, "metadata", {}) or {}
            src = m.get("source") or m.get("url") or m.get("file_path") or ""
            ver = m.get("source_version") or ""
            # 필요 시 로컬 mtime 강제 산출
            if not ver and _cfg_bool("RAG_ID_INCLUDE_MTIME", True):
                lv = _local_mtime_key(m)
                if lv:
                    m["source_version"] = lv
                    ver = lv
            return (str(src), str(ver))

        all_srcs = []
        cur_versions: dict[str, str] = {}
        for d in filtered_docs:
            src, ver = _sv_pair(d)
            if src:
                all_srcs.append(src)
                if ver and src not in cur_versions:
                    cur_versions[src] = ver

        stored_map: dict[str, str] = {}
        if all_srcs and not is_fresh:
            try:
                urls: list[str] = [u for u in all_srcs if isinstance(u, str) and u]
                # Chroma Where 타입이 엄격해 mypy가 연산자 표현을 추적하지 못함 → Any로 한정 구간만 완화
                where_filter: Any = {"source": {"$in": urls}}
                include: Include = ["metadatas"]
                col: Any = getattr(vs_eff, "_collection", None)
                res: Any = {}
                if col is not None:
                    res = col.get(where=where_filter, include=include)
                for m in (res or {}).get("metadatas") or []:
                    if isinstance(m, dict) and m.get("source"):
                        s = str(m.get("source"))
                        v = str(m.get("source_version") or "")
                        # 가장 최근/마지막 값을 저장 (버전 필드 없던 기존 인덱스는 "")
                        stored_map[s] = v
            except Exception as e:
                logger.debug("chroma get(where=$in) failed(ns=%s): %s", ns_eff, e)
                try:
                    col2: Any = getattr(vs_eff, "_collection", None)
                    res2: Any = {}
                    if col2 is not None:
                        res2 = col2.get(include=["metadatas"])
                    for m in (res2 or {}).get("metadatas") or []:
                        if isinstance(m, dict) and m.get("source"):
                            s = str(m.get("source"))
                            v = str(m.get("source_version") or "")
                            stored_map[s] = v
                except Exception as e2:
                    logger.debug("chroma full metadatas get failed(ns=%s): %s", ns_eff, e2)
                    stored_map = {}
        elif is_fresh:
            logger.debug("documents_to_chroma[%s]: fresh store detected; skip stored_urls check", label)

        # 신규/변경 분류
        new_documents: List[Document] = []
        changed_sources: set[str] = set()
        for d in filtered_docs:
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""
            cur_ver = str((meta.get("source_version") or ""))
            if src and (is_fresh or (src not in stored_map)):
                new_documents.append(d)
            elif src and (stored_map.get(src, "") != cur_ver):
                # 버전이 다르면 교체 대상
                new_documents.append(d)
                changed_sources.add(src)
            elif not src and is_fresh:
                new_documents.append(d)

        if not new_documents:
            if verbose:
                logger.info(
                    "documents_to_chroma(part:%s): no new urls | ns=%s dir=%s | in=%d gate_skipped=%d fresh=%s",
                    label, ns_eff, pd_eff, len(part_docs), skipped_gate, is_fresh
                )
            return (len(part_docs), 0, 0, 0)

        # (옵션) 버전 변경된 소스는 기존 벡터를 삭제 후 재색인
        if changed_sources and _cfg_bool("RAG_DELETE_OLD_ON_VERSION_MISMATCH", True):
            try:
                col_del: Any = getattr(vs_eff, "_collection", None)
                if col_del is not None:
                    for s in changed_sources:
                        try:
                            # 동일 이유로 delete의 where도 Any로 완화
                            col_del.delete(where=cast(Any, {"source": {"$eq": s}}))
                        except Exception as de:
                            logger.debug("delete old docs failed(ns=%s, source=%s): %s", ns_eff, s, de)
            except Exception as e:
                logger.debug("bulk delete on version mismatch failed(ns=%s): %s", ns_eff, e)

        # 스플릿
        splits: List[Document] = split_documents(new_documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not splits:
            if verbose:
                logger.info(
                    ("documents_to_chroma(part:%s): no splits | ns=%s dir=%s | in=%d new=%d | "
                     "note=all texts were filtered/too short/empty-after-cleaning (0 chunks expected)"),
                    label, ns_eff, pd_eff, len(part_docs), len(new_documents)
                )
            return (len(part_docs), len(new_documents), 0, 0)

        # ID 생성
        MAX_ID_CHARS = _cfg_int("CHROMA_MAX_ID_CHARS", 128)
        ids: List[str] = []
        counter: _dd[str, int] = _dd(int)

        def _cap_id(s: str) -> str:
            if len(s) <= MAX_ID_CHARS:
                return s
            keep_tail = 12
            return s[: MAX_ID_CHARS - keep_tail] + s[-keep_tail:]

        for doc in splits:
            meta = getattr(doc, "metadata", {}) or {}
            src  = meta.get("source", "") or meta.get("url", "") or meta.get("file_path", "")
            ver  = meta.get("source_version", "")
            seed = str(src)
            # (옵션) mtime 기반 버전 키를 ID에 포함
            if _cfg_bool("RAG_ID_INCLUDE_MTIME", True) and ver:
                seed = f"{src}|{ver}"
            # (옵션) 내용 기반 버전 보강 — 대용량에서 비용 큼. 기본 Off
            if _cfg_bool("RAG_ID_INCLUDE_CONTENT_SHA", False):
                try:
                    import hashlib as _hl
                    seed += "|" + _hl.sha1((doc.page_content or "").encode("utf-8","ignore")).hexdigest()[:16]
                except Exception:
                    pass
            if seed:
                import hashlib as _hl2
                base = _hl2.sha1(seed.encode("utf-8", "ignore")).hexdigest()
                counter[base] += 1
                raw_id = f"{base}-{counter[base]:06d}"
            else:
                counter["__none__"] += 1
                raw_id = f"none-{counter['__none__']:06d}"
            ids.append(_cap_id(raw_id))

        # 업서트 (워치독 적용)
        INDEX_TIMEOUT_SEC = _cfg_int("INDEX_TIMEOUT_SEC", 60)
        t0 = time.time()
        _qdir_cfg = _cfg_str("CHROMA_QUARANTINE_DIR", "")
        qdir = Path(_qdir_cfg) if _qdir_cfg else (Path(pd_eff) / "quarantine")
        try: qdir.mkdir(parents=True, exist_ok=True)
        except Exception: pass

        try:
            added_chunks = _batched_add(vs_eff, splits, ids, quarantine_dir=qdir, max_seconds=INDEX_TIMEOUT_SEC)
            if added_chunks == 0 and verbose:
                logger.info(
                    ("[HINT][%s] added_chunks=0 → common causes: "
                    "① all URLs already indexed (no new), ② gatekept domains, "
                    "③ cleaners removed boilerplate/blocks, ④ chunk_size too large"),
                    label
                )
        except Exception as e:
            logger.warning("documents_to_chroma(part:%s): batched_add raised — forcing single upserts: %s", label, e)
            added_chunks = 0
            for k, doc in enumerate(splits):
                # 워치독: 단건 업서트도 전체 상한을 존중
                if (time.time() - t0) > INDEX_TIMEOUT_SEC:
                    logger.error("[INDEX][TIMEOUT] exceeded %ss during single upserts — stopping at %d/%d",
                                 INDEX_TIMEOUT_SEC, k, len(splits))
                    break
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
            try: persist_fn()
            except Exception as e: logger.debug("vs.persist failed(ns=%s): %s", ns_eff, e)
        else:
            client: Any = getattr(vs_eff, "_client", None)
            client_persist = getattr(client, "persist", None)
            if callable(client_persist):
                try: client_persist()
                except Exception as e: logger.debug("client.persist failed(ns=%s): %s", ns_eff, e)

        try:
            total_chars: int = sum(len(d.page_content or "") for d in splits)
            avg_len: int = int(total_chars / len(splits)) if splits else 0
        except Exception:
            avg_len = 0

        elapsed = time.time() - t0
        logger.info(
            "documents_to_chroma(part:%s): %d docs → %d chunks (ns=%s, dir=%s) | new=%d, changed=%d, splits=%d, avg_chunk_chars=%d, time=%.2fs",
            label, len(part_docs), added_chunks, ns_eff, pd_eff, len(new_documents), len(changed_sources), len(splits), avg_len, elapsed
        )
        try:
            total_chars_for_splits: int = sum(len(d.page_content or "") for d in splits)
            record_chunks(chars_sum=total_chars_for_splits, chunks_cnt=added_chunks, ns=ns_eff, part=label)
        except Exception:
            pass
        return (len(part_docs), len(new_documents), len(splits), added_chunks)

    # 4) 인덱싱 실행
    if split_mode:
        in_w, new_w, spl_w, add_w = _ingest_partition(web_docs, True,  "web")
        in_l, new_l, spl_l, add_l = _ingest_partition(loc_docs, False, "local")
        in_o, new_o, spl_o, add_o = _ingest_partition(oth_docs, None,  "base")
        total_added = add_w + add_l + add_o
        split_count = spl_w + spl_l + spl_o
        new_docs_count = new_w + new_l + new_o
        pd_for_log = f"{pd_base} (split: web={_resolve_persist_dir(ns_web_env, persist_directory)}, local={_resolve_persist_dir(ns_loc_env, persist_directory)})"
    else:
        in_b, new_b, spl_b, add_b = _ingest_partition(pre_docs, None, "base")
        total_added = add_b
        split_count = spl_b
        new_docs_count = new_b
        pd_for_log = _resolve_persist_dir(ns_base, None)

    # 5) 최종 요약
    logger.info(
        ("documents_to_chroma: %d docs → %d chunks (ns=%s, dir=%s, split=%s) | "
         "in=%d, pre=%d, blocked=%d, new=%d, splits=%d"),
        len(documents or []), total_added, ns_base, pd_for_log, bool(split_mode),
        len(documents or []), pre_docs_count, skipped_block, new_docs_count, split_count
    )
    try:
        record_chunks(chars_sum=0, chunks_cnt=total_added, ns=ns_base, part="summary")
    except Exception:
        pass
    return (len(documents or []), total_added)


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
    """web.json → Document → Chroma 업서트 편의 함수."""
    # [ADD] 사전 해시/버전키 기반 no-op 빠른 종료
    # ns/pd를 먼저 해석해야 seen-hash 파일을 찾을 수 있습니다.
    ns_probe = _resolve_ns(namespace=namespace, collection_name=collection_name)
    pd_probe = _resolve_persist_dir(ns_probe, persist_directory)
    existing = _load_seen_source_hashes(ns_probe, pd_probe)  # {source:hash}
    incoming = _compute_incoming_hashes(json_file)            # {source:hash}
    new_sources = [s for s, h in incoming.items() if existing.get(s) != h]
    if not new_sources and incoming:
        logger.info("[ingest] all sources unchanged → skip build (ns=%s dir=%s, sources=%d)",
                    ns_probe, pd_probe, len(incoming))
        return (0, 0)

    documents = web_page_json_to_documents(json_file)
    in_docs, added = documents_to_chroma(
        documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        namespace=namespace,
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding=(embedding or _get_embeddings()),
        clear=clear,
    )
    # 인덱싱이 실제로 수행되었다면 seen-hash 갱신
    if added > 0 and incoming:
        try:
            ns_effective = _resolve_ns(namespace=namespace, collection_name=collection_name)
            pd_effective = _resolve_persist_dir(ns_effective, persist_directory)
            _save_seen_source_hashes(ns_effective, pd_effective, incoming)
        except Exception:
            logger.debug("[ingest] save seen hashes skipped (ns/pd unresolved or write fail)")
    return (in_docs, added)

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
        q_emb = emb_fn.embed_query(q) if hasattr(emb_fn, "embed_query") else emb_fn(q)  
        n = max(1, int(top_k or 5))
        res = vs._collection.query(  
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
