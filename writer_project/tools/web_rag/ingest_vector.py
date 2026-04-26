from __future__ import annotations

# mypy: disable-error-code=annotation-unchecked

import logging
logger = logging.getLogger(__name__)
logging.getLogger("chardet").setLevel(logging.WARNING)  # chardet DEBUG 스팸 억제

# NOTE:
# Canonical URL normalization + doc_id generation are SSoT in tools.web_rag.utils.
from tools.web_rag.utils import (
    _normalize_canonical_url,
    make_doc_id as _make_doc_id_ssot,
    cap_id as _cap_id_ssot,
)


import os
import time
import json
import hashlib
from pathlib import Path
from typing import Set
from types import ModuleType
from typing import (
    Any,
    List,
    Dict,
    Tuple,
    Sequence,
    Callable,
    Mapping,
    MutableMapping,
    Iterable,
    Optional,
    Protocol,
    runtime_checkable,
    cast,
)
import inspect

import re as _re
import glob as _glob

from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# config / 공통 설정
from .ingest_config import (
    CFG,
    reload_config,
    _cfg_str,
    _cfg_bool,
    _cfg_int,
    _REQ_CONN_TIMEOUT,
    _REQ_READ_TIMEOUT,
    _UA,
    record_chunks,
)

# 중앙 LLM(임베딩) 헬퍼
from core.llm import get_embedding_model

# 게이트키핑/호스트 정규화
from settings_gatekeep import (
    gatekeep_enabled,
    url_allowed,
    _normalize_host,  # 로그용 (없다면 제거 가능)
)

# web.json → Document 변환
from .ingest_docs import (
    web_results_to_documents,
    web_page_json_to_documents,
)

# web_rag 유틸 모듈
from .utils import (
    DATA_DIR,
    _is_block_page,
    _looks_like_pdf_bytes,
    _looks_like_serialized_blob,
    _clean_text,
    _resolve_persist_dir,
    _FRESH_KEYS,
    normalize_url as _normalize_url,
    # ✅ seen-hash SSOT (moved to utils.py)
    compute_incoming_hashes,
    load_seen_source_hashes,
    save_seen_source_hashes,
    delete_seen_source_hashes,
)


# ─────────────────────────────────────────────────────────────────────────────
# stored_urls cache helpers (ingest.py와 경로 규칙을 동일하게 유지)
#  - ⚠️ ingest_vector.py → ingest.py import는 순환 위험이 크므로 금지
#  - 여기서는 "삭제"만 담당 (정책/로드/세이브는 ingest.py가 주도)
# ─────────────────────────────────────────────────────────────────────────────
def _stored_urls_path(*, namespace: str, store_kind: str) -> Path:
    ns = (namespace or "").replace("/", "_").replace("\\", "_")
    base = DATA_DIR / "stored_urls"
    return base / f"stored_urls__{store_kind}__{ns}.json"

def _delete_stored_urls_cache(*, namespace: str, store_kind: str) -> None:
    try:
        p = _stored_urls_path(namespace=namespace, store_kind=store_kind)
        if p.exists():
            p.unlink()
            logger.info("[stored_urls] deleted cache: %s", p)
    except Exception as e:
        logger.debug("[stored_urls] delete failed ns=%s kind=%s err=%s", namespace, store_kind, e)

def _delete_all_stored_urls_for_ns(ns: str) -> None:
    """
    split 모드/단일 모드 모두에서 안전하게 stale 방지.
    - 기본: web/local 둘 다 지움
    - split 모드면 ns_web/ns_local도 같이 지움
    """
    try:
        _delete_stored_urls_cache(namespace=ns, store_kind="web")
        _delete_stored_urls_cache(namespace=ns, store_kind="local")
    except Exception:
        pass
    try:
        ns_web = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
        ns_loc = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
        if ns_web:
            _delete_stored_urls_cache(namespace=ns_web, store_kind="web")
        if ns_loc:
            _delete_stored_urls_cache(namespace=ns_loc, store_kind="local")
    except Exception:
        pass

# PDF/HTML 로더 유틸

_PDF_URL_RE = _re.compile(r"\.pdf($|\?)|filedownload|filedown(type)?=|/fileDown|/download", _re.I)
# ─────────────────────────────────────────────────────────────────────────────
# [LOG] pdfminer 과다 로그 억제 (WARNING 이상만)
# ─────────────────────────────────────────────────────────────────────────────
for _name in (
    "pdfminer",
    "pdfminer.psparser",
    "pdfminer.pdfdocument",
    "pdfminer.pdfparser",
    "pdfminer.cmapdb",
    "pdfminer.pdfinterp",
    "pdfminer.pdfdevice",
    "pdfminer.layout",
):
    try:
        logging.getLogger(_name).setLevel(logging.WARNING)
    except Exception:
        pass

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, unquote, quote

from chromadb.api.types import Include  # Chroma 메타 조회 타입
from collections import defaultdict as _dd


# ---- 선택적 백엔드(존재시 사용, 미설치 OK) ----
try:
    import PyPDF2 as _pypdf2_mod
    _pypdf2: Optional[ModuleType] = _pypdf2_mod  # mypy-friendly: 모듈 또는 None
except Exception:
    _pypdf2 = None

# (선택) XLSX 요약용: pandas는 선택 의존성입니다.
try:
    # pandas는 타입 스텁이 없을 수 있으므로 import-untyped만 무시
    import pandas as _pd  # type: ignore[import-untyped]
except Exception:
    _pd = None  # pandas 미설치 시 비활성화

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # mypy는 항상 community 경로의 Chroma 타입으로 고정
    from langchain_community.vectorstores.chroma import Chroma as Chroma
else:
    # 런타임에서는 langchain_chroma 우선, 없으면 community로 폴백
    try:
        from langchain_chroma import Chroma as Chroma
    except Exception:  # pragma: no cover
        from langchain_community.vectorstores.chroma import Chroma as Chroma


# ─────────────────────────────────────────────────────────────────────────────
# URL 정규화/유일화 보조 (ingest.py와 동일 정책 복사)
# ─────────────────────────────────────────────────────────────────────────────
_TRACKING_KEYS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id",
    "gclid","fbclid","igshid","mc_cid","mc_eid","ref","ref_src","ref_url",
    "spm","si","sck","ved","ei","yclid","msclkid","pk_campaign","pk_kwd",
}

_VOLATILE_PART_PARAMS = {"part","index","page","slide"}

def _strip_tracking_params(qs_items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for k, v in qs_items:
        lk = (k or "").lower()
        if lk in _TRACKING_KEYS or lk.startswith("utm_") or lk in _VOLATILE_PART_PARAMS:
            continue
        out.append((k, v))
    return out

#
# _normalize_canonical_url is imported from tools.web_rag.utils
#


# ---- Vector store cache (persist_dir, collection) ----
_VS_CACHE: Dict[Tuple[str, str], Chroma] = {}
_CLEARED_ONCE_KEYS: set[tuple[str, str]] = set()

def _resolve_ns(
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> str:
    """
    네임스페이스 결정 우선순위:
      1) namespace (명시 인자 최우선; split(web/local) 모드에서 필수)
      2) collection_name
      3) CFG.CHROMA_NAMESPACE
      4) CFG.TOPIC_SLUG (suffix -default)
      5) "default"
    """
    if namespace and namespace.strip():
        return namespace.strip()
    if collection_name and collection_name.strip():
        return collection_name.strip()
    env_ns = (getattr(CFG, "CHROMA_NAMESPACE", "") or "").strip()
    if env_ns:
        return env_ns
    topic_slug = (getattr(CFG, "TOPIC_SLUG", "") or "").strip()
    if topic_slug:
        return f"{topic_slug}-default"
    return "default"

def _resolve_persist_dir_strict(ns: str, persist_directory: Optional[str]) -> str:
    """
    옵션 A 정책(네임스페이스별 디렉터리 유지)을 강제합니다.
    split 모드(CHROMA_NAMESPACE_WEB/LOCAL 둘 다 설정)에서 ns가 web/local 중 하나라면
    persist_directory 인자를 무시하고 해당 ns 고유 디렉터리로 강제 라우팅.
    """
    try:
        ns_web = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
        ns_loc = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
        split_mode = bool(ns_web and ns_loc)
    except Exception:
        ns_web = ns_loc = ""
        split_mode = False

    if split_mode and ns in (ns_web, ns_loc):
        pd_expected = _resolve_persist_dir(ns, None)
        if persist_directory and os.path.normpath(persist_directory) != os.path.normpath(pd_expected):
            logger.warning(
                "[retrieve][strict] overriding persist_directory → ns='%s' dir='%s' (was: %s)",
                ns, pd_expected, persist_directory,
            )
        return pd_expected
    return _resolve_persist_dir(ns, persist_directory)


def _default_chroma_dir(namespace: str) -> str:
    return _resolve_persist_dir(namespace, persist_directory=None)

_CLEARED_RUNTIME_KEYS: set[tuple[str, str]] = set()

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
    """
    if embedding is not None:
        return embedding
    model_name = _resolve_embedding_model_name()
    ctor: Any = get_embedding_model

    try:
        params = list(inspect.signature(ctor).parameters.keys())
    except Exception:
        params = []

    try:
        if not params:
            emb = ctor()
            used = "no-arg"
        elif "model_name" in params:
            emb = ctor(model_name=model_name)
            used = "model_name"
        elif "model" in params:
            emb = ctor(model=model_name)
            used = "model"
        else:
            emb = ctor()
            used = "fallback:no-arg"
    except TypeError:
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
    if _re.match(r"^[a-z]:[\\/]", s) or s.startswith("\\\\"):
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
    if _re.match(r"^[a-zA-Z]:[\\/]", s) or s.startswith("\\\\") or s.startswith("/"):
        return s
    return None


def _local_mtime_key(meta: dict) -> str:
    """
    로컬 파일이면 mtime(ns) 또는 초단위를 문자열로 반환. 없으면 "".
    (doc_id/버전키에 섞어 변경 파일만 재인덱싱)
    """
    try:
        p = _extract_local_path(meta) or ""
        if not p:
            return ""
        st = Path(p).stat()
        # ns 단위가 있으면 우선 사용
        ns = getattr(st, "st_mtime_ns", None)
        if isinstance(ns, int) and ns > 0:
            return str(ns)
        return str(int(st.st_mtime))
    except Exception:
        return ""


def split_documents(
    documents: List[Document],
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[Document]:
    cs = (_cfg_int("RAG_CHUNK_CHARS", 2400) if chunk_size is None else int(chunk_size))
    ov = (_cfg_int("RAG_CHUNK_OVERLAP", 200) if chunk_overlap is None else int(chunk_overlap))
    cs = max(300, min(cs, 6000))
    ov = max(0, min(ov, int(cs * 0.5)))
    splitter = RecursiveCharacterTextSplitter(chunk_size=cs, chunk_overlap=ov)
    return splitter.split_documents(documents)


def _is_pptx_meta(meta: dict) -> bool:
    """메타정보로 PPTX 여부를 추정합니다."""
    try:
        src = (meta or {}).get("source") or (meta or {}).get("file_path") or ""
        ctype = (meta or {}).get("content_type") or ""
        if isinstance(src, str) and src.lower().endswith(".pptx"):
            return True
        if isinstance(ctype, str) and "presentationml" in ctype:
            return True
    except Exception:
        pass
    return False

def _is_xlsx_meta(meta: dict) -> bool:
    """메타정보로 XLSX 여부를 추정합니다."""
    try:
        src = (meta or {}).get("source") or (meta or {}).get("file_path") or ""
        ctype = (meta or {}).get("content_type") or ""
        if isinstance(src, str) and src.lower().endswith(".xlsx"):
            return True
        if isinstance(ctype, str) and "spreadsheetml" in ctype:
            return True
    except Exception:
        pass
    return False

def _format_won(n: float | int) -> str:
    """원 단위 간략 표기(천단위 콤마 + 필요 시 억 단위 병기)."""
    try:
        v = float(n)
    except Exception:
        return str(n)
    if abs(v) >= 100_000_000:
        eok = v / 100_000_000.0
        return f"{int(v):,}원 (~{eok:.2f}억원)"
    return f"{int(v):,}원"

def _xlsx_sheet_summaries(
    path: Path,
    *,
    max_rows: int = 200,
    max_cols: int = 20,
    max_docs: int = 5,
) -> list[str]:
    """
    XLSX 상단 일부(최대 200x20)만 스캔하여 간단 요약문 생성.
    """
    if _pd is None:
        return []
    out: list[str] = []
    try:
        xls = _pd.ExcelFile(path)
    except Exception:
        return out

    year_pat = _re.compile(r"^(20\d{2}|19\d{2})$")
    month_pat = _re.compile(r"^(1[0-2]|0?[1-9])$")
    cost_like = ("광고비", "비용", "집행", "지출", "총액", "합계", "total", "sum", "spend", "cost")
    channel_like = ("디지털", "digital", "tv", "지상파", "케이블", "소셜", "search", "display", "youtube")

    for sheet in xls.sheet_names[: max_docs * 2]:
        try:
            df = xls.parse(sheet_name=sheet, nrows=max_rows, usecols=range(0, max_cols))
        except Exception:
            continue
        if df is None or df.empty:
            continue
        cols = [str(c).strip() for c in df.columns]
        df.columns = cols
        num_df = df.select_dtypes(include=["number"])
        if num_df.empty:
            continue

        def _score_col(name: str) -> int:
            n = name.lower()
            s = 0
            if any(k in n for k in (k.lower() for k in cost_like)): s += 3
            if any(k in n for k in (k.lower() for k in channel_like)): s += 2
            if "합계" in name or "총" in name: s += 2
            if "금액" in name or "원" in name: s += 1
            return s

        scored = sorted([(c, _score_col(c)) for c in num_df.columns], key=lambda x: x[1], reverse=True)
        top_col = scored[0][0] if scored else num_df.columns[0]
        total_val = _pd.to_numeric(num_df[top_col], errors="coerce").fillna(0).sum()

        year = None
        month = None
        if year_pat.match(str(sheet).strip()):
            year = str(sheet).strip()

        head = df.head(10)
        for c in df.columns:
            vals = head[c].astype(str).str.strip()
            cand = [v for v in vals if year_pat.match(v)]
            if len(cand) >= 2 and not year:
                year = cand[0]
            cand_m = [v for v in vals if month_pat.match(v)]
            if len(cand_m) >= 2 and not month:
                month = cand_m[0].lstrip("0")

        brk_parts: list[str] = []
        for c in df.columns:
            lc = str(c).lower()
            if any(k in lc for k in (k.lower() for k in channel_like)):
                try:
                    s = _pd.to_numeric(df[c], errors="coerce").fillna(0).sum()
                    if s and s > 0:
                        brk_parts.append(f"{c}={_format_won(float(s))}")
                except Exception:
                    pass
        brk_parts = sorted(brk_parts, key=lambda t: len(t), reverse=True)[:5]

        y_str = f"{year}년 " if year else ""
        m_str = f"{month}월 " if month else ""
        brk = f" ({', '.join(brk_parts)})" if brk_parts else ""
        msg = f"{y_str}{m_str}광고비 합계={_format_won(float(total_val))}{brk} [sheet={sheet}, col={top_col}]"
        out.append(msg)
        if len(out) >= max_docs:
            break
    return out

def _build_xlsx_meta_documents(
    doc: Document,
    *,
    max_rows: int,
    max_cols: int,
    max_docs: int,
) -> list[Document]:
    """XLSX 문서에서 경량 요약문을 만들어 메타-도큐먼트로 변환."""
    if _pd is None:
        return []
    meta = getattr(doc, "metadata", {}) or {}
    src = meta.get("source") or meta.get("file_path") or ""
    if not isinstance(src, str) or not src:
        return []
    p = _extract_local_path(meta)
    if not p:
        return []
    texts = _xlsx_sheet_summaries(Path(p), max_rows=max_rows, max_cols=max_cols, max_docs=max_docs)
    out: list[Document] = []
    for i, txt in enumerate(texts):
        if not txt:
            continue
        new_meta = dict(meta)
        new_meta["source"] = f"{src}#xlsx-meta-{i+1}"
        new_meta["content_type"] = "text/xlsx-summary"
        new_meta["title"] = (meta.get("title") or "XLSX Summary")
        out.append(Document(page_content=txt, metadata=new_meta))
    return out

def _merge_short_chunks(chunks: List[Document], *, min_merged_chars: int = 300) -> List[Document]:
    """
    인접한 짧은 청크들을 병합합니다. 동일 소스(source) 기반으로만 병합합니다.
    """
    out: List[Document] = []
    buf: Optional[Document] = None

    def _src(d: Document) -> str:
        m = getattr(d, "metadata", {}) or {}
        return str(m.get("source") or m.get("file_path") or "")

    for d in chunks:
        text = (getattr(d, "page_content", "") or "").strip()
        if not text:
            continue
        if buf is None:
            buf = d
            continue
        if _src(buf) == _src(d) and (len((buf.page_content or "").strip()) + len(text) < min_merged_chars):
            sep = "\n"
            try:
                buf.page_content = ((buf.page_content or "").rstrip() + sep + text)
            except Exception:
                buf = Document(
                    page_content=((buf.page_content or "").rstrip() + sep + text),
                    metadata=getattr(buf, "metadata", {}) or {},
                )
        else:
            out.append(buf)
            buf = d
    if buf is not None:
        out.append(buf)
    return out

def _approx_tokens(s: str) -> int:
    return max(1, len(s or "") // 4)



def _batched_add(
    vs: Any,
    docs: List[Document],
    ids: List[str],
    *,
    quarantine_dir: Path,
    max_seconds: int = 60,
) -> int:
    """
    Chroma 업서트용 얇은 배치 래퍼.
    - 현재는 한 번에 add_documents 호출만 수행
    - 호출부에서 예외를 잡아 single upsert fallback으로 전환하므로
      여기서는 예외를 그대로 전파해도 된다.
    """
    if not docs:
        return 0

    t0 = time.time()
    try:
        # ids 길이가 docs와 다르면 안전하게 ids 인자를 생략
        if ids and len(ids) == len(docs):
            vs.add_documents(docs, ids=ids)
        else:
            vs.add_documents(docs)
    except Exception:
        # 상위에서 RuntimeError를 잡고 단건 업서트로 폴백하므로 재전파
        raise

    elapsed = time.time() - t0
    if elapsed > max_seconds:
        logger.warning(
            "[INDEX][WARN] batched_add took %.2fs (> %ss) for %d docs",
            elapsed, max_seconds, len(docs),
        )
    return len(docs)

def clear_vector_store(namespace: Optional[str] = None, persist_directory: Optional[str] = None) -> str:
    """
    벡터 저장소 디렉터리를 제거 후 재생성. 캐시/핸들도 함께 초기화.
    글로벌(인자 둘 다 None) 클리어는 ENV ALLOW_GLOBAL_CLEAR=1 일 때만 허용.
    """
    import shutil, stat, gc, time as _t

    ns = _resolve_ns(namespace=namespace, collection_name=None)
    pd = _resolve_persist_dir(ns, persist_directory)

    # ✅ stored_urls 캐시(= seen-hash)도 함께 삭제
    try:
        delete_seen_source_hashes(ns, pd)
    except Exception:
        pass

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

# ✅ 벡터 스토어가 실제로 비워졌다면 stored_urls도 반드시 제거 (stale 방지)

    if ok:
        try:
            _delete_all_stored_urls_for_ns(ns)
        except Exception:
            pass
    else:
        logger.debug("[stored_urls] skip delete: vector store clear not confirmed (ns=%s dir=%s)", ns, pd)

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
    # cast는 모듈 상단에서 이미 임포트됨
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
                # ✅ ns별 seen-hash 캐시도 같이 삭제
                try:
                    delete_seen_source_hashes(ns_eff, pd_eff)
                except Exception:
                    pass
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

    # ✅ (여기에) 1.5) 초소형/잡음 문서 필터 추가
    # 예: 너무 짧은 본문 제거(메뉴/푸터/한 줄짜리 등)
    min_chars = _cfg_int("RAG_MIN_DOC_CHARS", 200)  # 원하는 기본값
    min_tokens = _cfg_int("RAG_MIN_DOC_TOKENS", 30) # 선택

    filtered_docs: List[Document] = []
    skipped_too_small = 0

    for d in pre_docs:
        txt = getattr(d, "page_content", "") or ""
        # 아주 단순 기준: 글자수 + (선택) 토큰수
        if len(txt) < min_chars:
            skipped_too_small += 1
            continue
        if min_tokens > 0 and len(txt.split()) < min_tokens:
            skipped_too_small += 1
            continue
        filtered_docs.append(d)

    pre_docs = filtered_docs
    pre_docs_count2 = len(pre_docs)  # (옵션) 로그용

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

        vs_eff = _get_vs(ns_eff, pd_eff, embedding)  # fresh 재생성

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

        # [ADD] XLSX 경량 요약 메타-도큐먼트 생성(게이트키핑 통과한 문서 대상)
        try:
            if _pd is not None and _cfg_bool("ENABLE_XLSX_META_SUMMARY", True):
                _max_rows = _cfg_int("XLSX_SCAN_MAX_ROWS", 200)
                _max_cols = _cfg_int("XLSX_SCAN_MAX_COLS", 20)
                _max_docs = _cfg_int("XLSX_META_MAX_DOCS", 5)
                extra_docs: list[Document] = []
                for d in filtered_docs:
                    if _is_xlsx_meta(getattr(d, "metadata", {}) or {}):
                        extra_docs.extend(_build_xlsx_meta_documents(d, max_rows=_max_rows, max_cols=_max_cols, max_docs=_max_docs))
                if extra_docs:
                    filtered_docs.extend(extra_docs)
                    logger.info("[INGEST][%s] xlsx meta summaries added: +%d docs", label, len(extra_docs))
        except Exception as e:
            logger.debug("[INGEST][%s] xlsx meta summaries skipped: %s", label, e)

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
                urls: list[str] = [u for u in all_srcs if isinstance(u, str) and u]  # 빈 문자열/비정상 거르기
                # Chroma Where 타입은 dict[str, Any]로 제한
                where_filter: dict[str, Any] = {"source": {"$in": urls}}
                # Include는 Literal 기반 타입 → 리스트 리터럴을 cast로 지정
                include: Include = cast(Include, ["metadatas"])
                col: Any = getattr(vs_eff, "_collection", None)
                res: dict[str, Any] = {}
                if col is not None:
                    res = col.get(where=where_filter, include=include)
                for m in (res or {}).get("metadatas") or []:
                    if isinstance(m, dict) and m.get("source"):
                        s = str(m.get("source"))  # 타입 강제 일관화
                        v = str(m.get("source_version") or "")
                        # 가장 최근/마지막 값을 저장 (버전 필드 없던 기존 인덱스는 "")
                        stored_map[s] = v
            except Exception as e:
                logger.debug("chroma get(where=$in) failed(ns=%s): %s", ns_eff, e)
                try:
                    col2: Any = getattr(vs_eff, "_collection", None)
                    res2: Any = {}
                    if col2 is not None:
                        res2 = col2.get(include=cast(Include, ["metadatas"]))
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

        # ──────────────────────────────────────────────────────
        # [ADD] PPTX 초단편 병합 + 콘텐츠 타입별 최소 길이 필터
        # ──────────────────────────────────────────────────────
        try:
            # PPTX 청크만 선별
            pptx_idxs = [i for i, d in enumerate(splits) if _is_pptx_meta(getattr(d, "metadata", {}) or {})]
            if pptx_idxs:
                # 원본 순서를 유지하며 PPTX 영역만 병합 적용
                merged: List[Document] = []
                run: List[Document] = []
                def _flush_run():
                    nonlocal merged, run
                    if not run:
                        return
                    # 기본값 160자로 상향(기존 제안: 120→160)
                    merged.extend(_merge_short_chunks(run, min_merged_chars=_cfg_int("PPTX_MIN_MERGED_CHARS", 160)))
                    run = []
                last_pptx = False
                for d in splits:
                    is_pptx = _is_pptx_meta(getattr(d, "metadata", {}) or {})
                    if is_pptx:
                        run.append(d)
                        last_pptx = True
                    else:
                        if last_pptx:
                            _flush_run()
                            last_pptx = False
                        merged.append(d)
                _flush_run()
                splits = merged

            # 콘텐츠 타입별 최소 길이 필터
            GLOBAL_MIN_CHUNK_CHARS = _cfg_int("MIN_CHUNK_CHARS", 120)
            def _min_chars_for(ct: str) -> int:
                cts = (ct or "").lower()
                # PPTX: application/vnd.openxmlformats-officedocument.presentationml.presentation
                if "presentationml" in cts:
                    return _cfg_int("MIN_CHUNK_PPTX", 40)
                # PDF
                if cts == "application/pdf" or "pdf" in cts:
                    return _cfg_int("MIN_CHUNK_PDF", 80)
                # 그 외
                return GLOBAL_MIN_CHUNK_CHARS

            before = len(splits)
            def _len_ok(doc: Document) -> bool:
                text_len = len((getattr(doc, "page_content", "") or "").strip())
                meta = getattr(doc, "metadata", {}) or {}
                ct = str(meta.get("content_type") or "")
                return text_len >= _min_chars_for(ct)

            splits = [d for d in splits if _len_ok(d)]
            after = len(splits)  # 필터 후 길이
            if verbose and before != after:
                logger.info(
                    "[INGEST][%s] filtered short chunks: %d → %d "
                    "(GLOBAL_MIN=%d, PPTX_MIN=%d, PDF_MIN=%d)",
                    label, before, after,
                    GLOBAL_MIN_CHUNK_CHARS,
                    _cfg_int('MIN_CHUNK_PPTX', 40),
                    _cfg_int('MIN_CHUNK_PDF', 80),
                )
        except Exception as e:
            logger.debug("[INGEST][%s] pptx short-chunk merge/filter skipped due to error: %s", label, e)

        # ──────────────────────────────────────────────────────
        # [ADD] 청크 통계 로깅 (길이 분포/평균 등)
        # ──────────────────────────────────────────────────────
        try:
            lens = [len((d.page_content or "").strip()) for d in splits if (d.page_content or "").strip()]
            lens.sort()
            n = len(lens)
            if n:
                avg = sum(lens) / n
                p50 = lens[int((n - 1) * 0.50)]
                p90 = lens[int((n - 1) * 0.90)]
                minv, maxv = lens[0], lens[-1]
                logger.info(
                    "[INGEST][stats][%s] splits=%d avg=%.1f p50=%d p90=%d min=%d max=%d",
                    label, n, avg, p50, p90, minv, maxv
                )
                try:
                    from tools.metrics import event as _metrics_event
                    _metrics_event("chunk_stats", part=label, splits=n,
                                   avg_chars=round(avg, 1),
                                   p50=p50, p90=p90,
                                   min_chars=minv, max_chars=maxv)
                except Exception:
                    pass
            else:
                logger.info("[INGEST][stats][%s] no valid chunks", label)
        except Exception as e:
            logger.debug("[INGEST][stats][%s] chunk stat failed: %s", label, e)

        # ID 생성
        MAX_ID_CHARS = _cfg_int("CHROMA_MAX_ID_CHARS", 128)
        ids: List[str] = []
        counter: _dd[str, int] = _dd(int)

        # ─────────────────────────────────────────────
        # [ADD] 임베딩 안전 배치 가드
        # - 총 텍스트 길이 18k 초과 시 강제 분할
        # - CHROMA_MAX_BATCH 환경변수 상한 적용
        # ─────────────────────────────────────────────
        MAX_BATCH = _cfg_int("CHROMA_MAX_BATCH", 16)  # 기본 16으로 보수적
        MAX_TEXT_SUM = 18000

        def _yield_batches(docs: List[Document], ids_list: List[str]):
            batch_docs, batch_ids = [], []
            text_sum = 0
            for d, i in zip(docs, ids_list):
                l = len((d.page_content or ""))
                # 조건 1: batch size 초과
                # 조건 2: 텍스트 총합 초과
                if (
                    batch_docs
                    and (len(batch_docs) >= MAX_BATCH or text_sum + l > MAX_TEXT_SUM)
                ):
                    yield batch_docs, batch_ids
                    batch_docs, batch_ids = [], []
                    text_sum = 0
                batch_docs.append(d)
                batch_ids.append(i)
                text_sum += l
            if batch_docs:
                yield batch_docs, batch_ids

        def _cap_id(s: str) -> str:
            return _cap_id_ssot(s, max_chars=MAX_ID_CHARS, keep_tail=12)

        def _make_doc_id(src: str, ver: str, text: str) -> str:
            return _make_doc_id_ssot(
                src,
                ver,
                text,
                counter=counter,
                max_id_chars=MAX_ID_CHARS,
                include_mtime=_cfg_bool("RAG_ID_INCLUDE_MTIME", True),
                include_content_sha=_cfg_bool("RAG_ID_INCLUDE_CONTENT_SHA", False),
            )
        
        for doc in splits:
            meta = getattr(doc, "metadata", {}) or {}
            src  = str(meta.get("source") or meta.get("url") or meta.get("file_path") or "")
            ver  = str(meta.get("source_version") or "")
            if src:
                ids.append(_make_doc_id(src, ver, getattr(doc, "page_content", "") or ""))
            else:
                counter["__none__"] += 1
                ids.append(_cap_id(f"none-{counter['__none__']:06d}"))

        # 업서트 (워치독 적용)
        INDEX_TIMEOUT_SEC = _cfg_int("INDEX_TIMEOUT_SEC", 60)
        t0 = time.time()
        _qdir_cfg = _cfg_str("CHROMA_QUARANTINE_DIR", "")
        qdir = Path(_qdir_cfg) if _qdir_cfg else (Path(pd_eff) / "quarantine")
        try: qdir.mkdir(parents=True, exist_ok=True)
        except Exception: pass

        try:
            added_chunks = 0
            for _docs, _ids in _yield_batches(splits, ids):
                added_chunks += _batched_add(
                    vs_eff,
                    _docs,
                    _ids,
                    quarantine_dir=qdir,
                    max_seconds=INDEX_TIMEOUT_SEC,
                )
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
        # ─────────────────────────────────────────────────────────────
        # [HEALTHCHECK] 파티션별 added_chunks ≥ 1 보장 (입력이 있을 때)
        # ─────────────────────────────────────────────────────────────
        # 웹 단계는 중복/게이트/404로 신규 0건이 자연스러울 수 있음 → 예외 대신 경고
        if in_w > 0 and add_w <= 0:
            logger.warning("[ingest] no new chunks for web (in=%d) → continue as ok", in_w)
        if in_l > 0 and add_l <= 0:
            raise RuntimeError("No chunks added for local")
        # base(other) 파티션에 입력이 있고 추가가 0인 경우도 방어
        if in_o > 0 and add_o <= 0:
            raise RuntimeError("No chunks added for base")
    else:
        in_b, new_b, spl_b, add_b = _ingest_partition(pre_docs, None, "base")
        total_added = add_b
        split_count = spl_b
        new_docs_count = new_b
        pd_for_log = _resolve_persist_dir(ns_base, None)
        # ─────────────────────────────────────────────────────────────
        # [HEALTHCHECK] 단일 파티션 모드에서도 0 추가 시 즉시 중단
        # ─────────────────────────────────────────────────────────────
    # 수정 — 이미 인덱싱된 경우는 정상 처리
    if pre_docs_count > 0 and total_added <= 0 and new_docs_count > 0:
        raise RuntimeError("No chunks added for base")

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
    # 함수 보장: 항상 (in_docs, added_chunks) 튜플 반환
    return (len(documents or []), total_added)


def has_any_docs(ns: str, base_dir: str) -> bool:
    """
    지정 컬렉션(ns) / 디렉터리(base_dir)에 문서가 1개 이상 존재하는지 여부.
    1) Chroma 컬렉션 count()가 가능하면 우선 사용
    2) 실패 시 디렉터리에 파일 존재 여부로 폴백
    """
    try:
        vs = _get_vs(ns, base_dir, embedding=_get_embeddings())
        col = getattr(vs, "_collection", None)
        cnt_fn = getattr(col, "count", None)
        if callable(cnt_fn):
            raw: Any = cnt_fn()
            if isinstance(raw, int):
                cnt = raw
            elif isinstance(raw, str):
                try:
                    cnt = int(raw.strip() or "0")
                except Exception:
                    cnt = 0
            else:
                try:
                    cnt = int(cast(Any, raw))
                except Exception:
                    try:
                        cnt = len(cast(Any, raw))
                    except Exception:
                        cnt = 1 if bool(raw) else 0
            return cnt > 0
    except Exception:
        pass
    try:
        p = Path(base_dir)
        if p.exists():
            for _ in p.iterdir():
                return True
    except Exception:
        pass
    return False

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
    ns_base = _resolve_ns(namespace=namespace, collection_name=collection_name)
    ns_web_env = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc_env = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    split_mode = bool(ns_web_env and ns_loc_env)
    # web.json 경로는 "웹 소스"이므로 split 모드면 web ns로 강제
    ns_probe = (ns_web_env if split_mode else ns_base)
    pd_probe = _resolve_persist_dir(ns_probe, persist_directory)
    existing = load_seen_source_hashes(ns_probe, pd_probe)  # {source:hash}
    incoming = compute_incoming_hashes(json_file)            # {source:hash}
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
            ns_base2 = _resolve_ns(namespace=namespace, collection_name=collection_name)
            ns_web_env2 = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
            ns_loc_env2 = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
            split_mode2 = bool(ns_web_env2 and ns_loc_env2)
            ns_effective = (ns_web_env2 if split_mode2 else ns_base2)
            pd_effective = _resolve_persist_dir(ns_effective, persist_directory)
            save_seen_source_hashes(ns_effective, pd_effective, incoming)
        except Exception:
            logger.debug("[ingest] save seen hashes skipped (ns/pd unresolved or write fail)")
    return (in_docs, added)

# -----------------------------------------------------------------------------
# ✅ Public alias (stable API): add_documents_to_chroma
#  - 내부 구현은 documents_to_chroma를 그대로 위임합니다.
#  - 시그니처/리턴타입 동일 → mypy/pyright 안전
# -----------------------------------------------------------------------------
_LOGGED_ALIAS_ONCE: bool = False
def add_documents_to_chroma(
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
    global _LOGGED_ALIAS_ONCE
    if not _LOGGED_ALIAS_ONCE:
        try:
            logger.info("add_documents_to_chroma → documents_to_chroma (alias)")
        except Exception:
            pass
        _LOGGED_ALIAS_ONCE = True
    return documents_to_chroma(
        documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        namespace=namespace,
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding=embedding,
        clear=clear,
        verbose=verbose,
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

    # ✅ [CHECK] Tool/invoke 경로에서 인자가 실제로 전달되는지 확인
    try:
        logger.warning(
            "[CHECK][retrieve][args] namespace=%r collection_name=%r persist_directory=%r top_k=%r",
            namespace, collection_name, persist_directory, top_k
        )
    except Exception:
        pass

    # ✅ 호출자가 namespace를 명시하면 그것을 최우선으로 존중한다.
    #    (dual-retrieve에서 ns_web/ns_local로 호출하는데 _resolve_ns가 base로 덮어쓰는 현상 방지)
    ns_arg = (namespace or "").strip()
    if ns_arg:
        ns = ns_arg
        logger.debug(
            "[retrieve][ns_resolve] (explicit) arg.namespace=%r arg.collection_name=%r -> ns=%r",
            namespace, collection_name, ns
        )
    else:
        ns = _resolve_ns(namespace=namespace, collection_name=collection_name)
        logger.debug(
            "[retrieve][ns_resolve] (resolved) arg.namespace=%r arg.collection_name=%r -> ns=%r",
            namespace, collection_name, ns
        )
    # ✅ 옵션 A 강제: split 모드에서 web/local 네임스페이스일 때는 항상 ns 전용 디렉터리로 라우팅
    pd = _resolve_persist_dir_strict(ns, persist_directory)
    vs = _get_vs(ns, pd, embedding)
    logger.debug("[retrieve] using collection(ns=%s, dir=%s)", ns, pd)

    # ✅ [CHECK] retrieve가 실제로 바라보는 컬렉션 카운트 (dual-retrieve count와 불일치 여부 확인)
    try:
        c = getattr(getattr(vs, "_collection", None), "count", None)
        if callable(c):
            logger.warning("[CHECK][retrieve] ns=%s dir=%s collection_count=%s", ns, pd, c())
        else:
            logger.warning("[CHECK][retrieve] ns=%s dir=%s collection_count=(unknown)", ns, pd)
    except Exception as e:
        logger.warning("[CHECK][retrieve] collection_count failed: %s", e)


    emb_fn = getattr(vs, "_embedding_function", None) or embedding or _get_embeddings(embedding)

    try:
        q_emb = emb_fn.embed_query(q) if hasattr(emb_fn, "embed_query") else emb_fn(q)
        n = max(1, int(top_k or 5))
        # ✅ [CHECK] query embedding 차원 확인 (dimension mismatch는 보통 예외지만, 이상치 탐지용)
        try:
            q_dim = len(q_emb) if hasattr(q_emb, "__len__") else None
            logger.warning("[CHECK][retrieve] ns=%s dir=%s top_k=%d q_len=%d q_emb_dim=%s",
                           ns, pd, n, len(q), q_dim)
        except Exception:
            pass

        res = vs._collection.query(
            query_embeddings=[q_emb],
            n_results=n,
            include=cast(Include, ["documents", "metadatas"]),
        )

        docs_out: list[Document] = []
        docs = (res or {}).get("documents") or []
        metas = (res or {}).get("metadatas") or []
        # ✅ [CHECK] raw 응답 구조/길이 확인 (실제로 0-hit인지 판단)
        try:
            d0 = len(docs[0]) if (isinstance(docs, list) and docs and isinstance(docs[0], list)) else 0
            m0 = len(metas[0]) if (isinstance(metas, list) and metas and isinstance(metas[0], list)) else 0
            logger.warning("[CHECK][retrieve-fast] ns=%s dir=%s raw_docs0=%d raw_metas0=%d keys=%s",
                           ns, pd, d0, m0, list((res or {}).keys()))
        except Exception:
            pass

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


def get_collection_count(ns: str, base_dir: str) -> int:
    """
    해당 네임스페이스/디렉터리의 벡터 컬렉션 청크 수를 반환.
    내부적으로 Chroma collection.count()를 시도하고, 실패 시 디렉터리 존재로 폴백.
    """
    def _to_int_maybe(x: Any) -> Optional[int]:
        # 정적 타입 안전 변환: int/float/str/SupportsInt 처리
        if isinstance(x, bool):
            return int(x)
        if isinstance(x, int):
            return x
        if isinstance(x, float):
            try:
                return int(x)
            except Exception:
                return None
        if isinstance(x, str):
            s = x.strip()
            # 숫자 문자열(정수/실수) 모두 수용
            try:
                return int(s)
            except Exception:
                try:
                    return int(float(s))
                except Exception:
                    return None
        # __int__ 보유 객체는 시도하되 실패 시 None
        if hasattr(x, "__int__"):
            try:
                return int(x)  # x는 Any이므로 런타임 시도
            except Exception:
                return None
        return None

    try:
        vs = _get_vs(ns, base_dir, embedding=_get_embeddings())
        col = getattr(vs, "_collection", None)
        cnt_fn: Any = getattr(col, "count", None)
        if callable(cnt_fn):
            raw: Any = cnt_fn()
            val = _to_int_maybe(raw)
            if val is not None:
                return val
    except Exception:
        pass
    # 폴백: 디렉터리에 뭔가 있으면 1 이상으로 간주(정밀 카운트는 아님)
    try:
        p = Path(base_dir)
        for _ in p.iterdir():
            return 1
    except Exception:
        pass
    return 0

def get_total_collection_count() -> int:
    """
    분리 모드(CHROMA_NAMESPACE_WEB/LOCAL)면 두 컬렉션을 합산, 아니면 기본 NS만 카운트.
    """
    ns_web = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    if ns_web and ns_loc:
        return (
            get_collection_count(ns_web, _default_chroma_dir(ns_web)) +
            get_collection_count(ns_loc, _default_chroma_dir(ns_loc))
        )
    ns = (getattr(CFG, "CHROMA_NAMESPACE", "") or "").strip()
    if not ns:
        topic = (getattr(CFG, "TOPIC_SLUG", "") or "").strip()
        ns = f"{topic}-default" if topic else "default"
    return get_collection_count(ns, _default_chroma_dir(ns))

# -----------------------------------------------------------------------------
# seed_web_namespace: URL 목록 또는 web.json로 웹 네임스페이스 초기 시드
# -----------------------------------------------------------------------------
def seed_web_namespace(
    urls: list[str] | None = None,
    *,
    webjson_path: str | None = None,
    namespace: str | None = None,
    collection_name: str | None = None,
    persist_directory: str | None = None,
    clear: bool = False,
    embedding=None,
) -> tuple[int, int]:
    """
    웹 컬렉션을 간단히 시드합니다.
    - webjson_path가 주어지면: web.json → Document → Chroma (add_web_pages_json_to_chroma 사용)
    - urls가 주어지면: URL 리스트 → web_results_to_documents → Chroma
    반환값: (입력 문서 수, 추가된 청크 수)
    """
    # 분리 모드면 web 네임스페이스로 강제
    ns_base = _resolve_ns(namespace=namespace, collection_name=collection_name)
    ns_web = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    split_mode = bool(ns_web and ns_loc)
    ns_eff = ns_web if split_mode else ns_base

    # [B] 라운드 시작 시 호스트 실패 카운터 리셋
    try:
        _round_fail_reset()
    except NameError:
        pass

    if webjson_path:
        # web.json 경로 시나리오
        in_docs, added = add_web_pages_json_to_chroma(
            webjson_path,
            namespace=ns_eff,
            collection_name=None,  # ns를 우선 사용
            persist_directory=persist_directory,
            embedding=embedding,
            clear=clear,
        )
        return in_docs, added

    # URL 리스트 시나리오
    url_list = [u for u in (urls or []) if isinstance(u, str) and u.strip()]
    if not url_list:
        return (0, 0)

    # 필요 시 초기화
    if clear:
        try:
            pd_eff = _resolve_persist_dir(ns_eff, persist_directory)
            clear_vector_store(namespace=ns_eff, persist_directory=pd_eff)
        except Exception:
            pass

    # URL → Documents → Chroma
    results = [{"url": _normalize_canonical_url(u)} for u in url_list]
    docs = web_results_to_documents(results)
    in_docs, added = documents_to_chroma(
        docs,
        namespace=ns_eff,
        collection_name=None,
        persist_directory=persist_directory,
        embedding=embedding,
        clear=False,  # 이미 위에서 처리
        verbose=True,
    )
    return in_docs, added
# ─────────────────────────────────────────────────────────────────────────────
# [B] 회로 차단기(호스트 단위) 전역 상태/함수
# ─────────────────────────────────────────────────────────────────────────────
_ROUND_FAIL_HOSTS: dict[str, int] = {}
_ROUND_FAIL_LIMIT = 2  # 라운드 내 최대 실패 기록 회수

def _round_fail_reset() -> None:
    """라운드 시작 시 호출하여 실패 카운터를 초기화."""
    try:
        _ROUND_FAIL_HOSTS.clear()
    except Exception:
        pass

def _circuit_break_host(host: str) -> bool:
    """호스트 실패 누적이 한도 초과면 True(스킵)."""
    try:
        cnt = _ROUND_FAIL_HOSTS.get(host.lower(), 0)
        return cnt >= _ROUND_FAIL_LIMIT
    except Exception:
        return False

def _mark_host_fail(host: str) -> None:
    """호스트 실패 회수를 +1."""
    try:
        h = (host or "").lower()
        if not h:
            return
        _ROUND_FAIL_HOSTS[h] = _ROUND_FAIL_HOSTS.get(h, 0) + 1
    except Exception:
        pass

__all__ = [
    "documents_to_chroma",
    "add_documents_to_chroma",
    "add_web_pages_json_to_chroma",
    "retrieve",
    "clear_vector_store",
    "ensure_vector_store_cleared_once",
    "get_collection_count",
    "get_total_collection_count",
    "seed_web_namespace",
    "has_any_docs",
]