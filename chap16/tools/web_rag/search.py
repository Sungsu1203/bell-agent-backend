from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import re
import os, json, time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Sequence, Callable, TYPE_CHECKING, cast, Type
from datetime import datetime
import threading

import requests
from langchain_core.tools import tool
from tools.web_rag.ingest import get_requests_session  # 공용 재시도 세션/CA 번들 재사용
# documents_to_chroma는 ingest 리팩토링 이후 심볼/시그니처가 바뀔 수 있어
# 아래 import_module 경로로만 동적 탐색합니다(중복 임포트 제거).

# ── Timeout defaults (module-level) ──────────────────────────────────────────
DEFAULT_TIMEOUT_SECONDS: int = 8

# ── Metrics (best-effort wrapper) ─────────────────────────────────────────────
from tools.metrics import (
    record_query_issued,
    record_zero_result,
    record_backend_latency,
    set_round,
    event,
)

# ── Config 단일 진입점 ────────────────────────────────────────────────────────
import core.config as config
from core.config import CFG, reload_config

# ── (옵션) url→Document 로더 동적 획득: 정적 임포트 금지, importlib 사용 ─────
from importlib import import_module
_load_urls_as_documents: Optional[Callable[..., Any]] = None
try:
    _ingest_mod = import_module("tools.web_rag.ingest")
    _load_urls_as_documents = getattr(_ingest_mod, "load_urls_as_documents", None)
except Exception:
    _load_urls_as_documents = None

# ── LangChain Document: 타입(정적)과 런타임 분리 ─────────────────────────────
# 정적 힌트는 Any로, 런타임은 DocClass로 통일
LCDocumentT = Any

# 런타임에 사용할 문서 클래스 핸들(항상 '클래스' 보장). 실패 시 폴백 클래스 사용.
try:
    from langchain_core.documents import Document as _LC_Doc  # langchain >=0.2
    _DOC_RUNTIME: Any = _LC_Doc
except Exception:  # pragma: no cover
    class _DocFallback:
        page_content: str
        metadata: Dict[str, Any]
        def __init__(self, page_content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
            self.page_content = page_content
            self.metadata = dict(metadata or {})
    _DOC_RUNTIME = _DocFallback

# 단 한 번만 최종 타입으로 선언
DocClass: Type[Any] = cast(Type[Any], _DOC_RUNTIME)

# ── ingest 적재 함수 동적 호출 유틸 ─────────────────────────────────────────
def _coerce_added_count(ret: Any) -> int:
    """int | tuple[…], None 등 다양한 반환을 안전하게 정수로 변환"""
    try:
        if isinstance(ret, tuple):
            if ret:
                return int(ret[0] if ret[0] is not None else 0)
            return 0
        if ret is None:
            return 0
        return int(ret)
    except Exception:
        return 0

def _ingest_add_docs(docs: List["LCDocumentT"], *, namespace: str) -> int:
    """
    ingest 모듈의 documents_to_chroma / add_documents_to_chroma / 호환 함수들을
    런타임에 탐색하여 호출. 없으면 0을 반환.
    """
    fn = None
    if _ingest_mod is not None:
        # 우선순위: documents_to_chroma → add_documents_to_chroma → documents_to_chroma_compat
        for name in ("documents_to_chroma", "add_documents_to_chroma", "documents_to_chroma_compat"):
            _cand = getattr(_ingest_mod, name, None)
            if callable(_cand):
                fn = _cand
                break
    if not callable(fn):
        logger.debug("[web_seed] ingest add function not found; skip seeding")
        return 0
    try:
        # 파라미터 이름이 namespace 또는 ns 인 경우 모두 대응
        params = fn.__code__.co_varnames if hasattr(fn, "__code__") else ()
        kwargs: Dict[str, Any] = {}
        if "namespace" in params:
            kwargs["namespace"] = namespace
        elif "ns" in params:
            kwargs["ns"] = namespace
        # 마지막 폴백: 키워드 없이 호출(함수 쪽에서 내부 기본 ns 사용 가능)
        ret = cast(Callable[..., Any], fn)(docs, **kwargs)
        return _coerce_added_count(ret)
    except Exception as e:
        logger.warning("[web_seed] ingest add call failed: %s", e)
        return 0


# ── 폴백 로더 ────────────────────────────────────────────────────────────────
def _fallback_load_urls_as_documents(urls: list[str]) -> List["LCDocumentT"]:
    """
    폴백 로더: LangChain WebBaseLoader 사용(가벼운 HTML 스냅샷).
    ingest 쪽 로더가 없을 때만 사용됩니다.
    항상 List[Document] 반환으로 통일합니다.
    """
    docs_rt: list[Any] = []
    try:
        from langchain_community.document_loaders import WebBaseLoader
        for u in urls or []:
            try:
                loader = WebBaseLoader([u])
                loaded = loader.load() or []
                # source 메타 보강
                for d in loaded:
                    try:
                        md = getattr(d, "metadata", {}) or {}
                        if "source" not in md:
                            md["source"] = u
                        # 타입체커 경고 없이 안전하게 대입
                        setattr(d, "metadata", md)
                    except Exception:
                        pass
                # Document 타입으로 통일
                for d in loaded:
                    try:
                        if isinstance(d, DocClass):
                            docs_rt.append(d)
                        else:
                            pc = getattr(d, "page_content", "") if hasattr(d, "page_content") else ""
                            md = getattr(d, "metadata", {}) if hasattr(d, "metadata") else {}
                            docs_rt.append(DocClass(page_content=str(pc or ""), metadata=dict(md or {})))
                    except Exception:
                        # 마지막 안전망
                        docs_rt.append(DocClass(page_content="", metadata={"source": u}))
            except Exception:
                logger.debug("[web_seed][fallback] load failed: %s", u)
                docs_rt.append(DocClass(page_content="", metadata={"source": u}))
    except Exception:
        # WebBaseLoader 자체가 없을 때: URL만 source로 넣어 빈 Document 생성
        docs_rt = [DocClass(page_content="", metadata={"source": u}) for u in (urls or [])]
    from typing import cast as _cast
    return _cast(List["LCDocumentT"], docs_rt)

def _normalize_documents(docs_in: object) -> List["LCDocumentT"]:
    """
    다양한 형태(list[Document] | list[dict] | 기타)를 안전하게 List[Document]로 정규화.
    - dict 항목은 {page_content, metadata} 키를 기준으로 변환
    - 알 수 없는 타입은 page_content=str(x)로 승격
    """
    out_rt: list[Any] = []
    if not isinstance(docs_in, list):
        from typing import cast as _cast
        return _cast(List["LCDocumentT"], out_rt)
    for x in docs_in:
        # 1) 이미 Document 타입인 경우
        try:
            if isinstance(x, DocClass):
                out_rt.append(x)
                continue
        except Exception:
            # 2) 속성으로 유추 가능한 객체: 강제 승격
            if hasattr(x, "page_content") and hasattr(x, "metadata"):
                try:
                    pc = getattr(x, "page_content", "")
                    md = getattr(x, "metadata", {}) or {}
                    out_rt.append(DocClass(page_content=str(pc or ""), metadata=dict(md)))
                    continue
                except Exception:
                    pass
        # 3) dict → Document
        if isinstance(x, dict):
            pc = x.get("page_content", "")
            md = x.get("metadata", {}) or {}
            out_rt.append(DocClass(page_content=str(pc or ""), metadata=dict(md)))
        else:
            # 4) 기타 → 문자열로 승격
            out_rt.append(DocClass(page_content=str(x), metadata={}))
    from typing import cast as _cast
    return _cast(List["LCDocumentT"], out_rt)

# ── 빠른 시드: URL → Documents → Chroma 적재 ────────────────────────────────
def seed_web_namespace(urls: list[str], namespace: str) -> int:
    """
    URL 리스트를 로드하여 web 네임스페이스에 한 번에 적재합니다.
    - 반환값: 신규 추가된 문서 수(중복이면 0일 수 있음)
    - 사용 예: seed_web_namespace(SEED_URLS, f"{topic_slug}-web")
    """
    if not urls:
        logger.info("[web_seed] no urls provided; skip seeding")
        return 0
    try:
        if callable(_load_urls_as_documents):
            raw_docs = _load_urls_as_documents(urls)
        else:
            raw_docs = _fallback_load_urls_as_documents(urls)

        docs_typed: List["LCDocumentT"] = _normalize_documents(raw_docs)
        # ingest 적재 호출(리팩토링 전후 시그니처 차이 흡수)
        added_count = _ingest_add_docs(list(docs_typed), namespace=namespace)

        logger.info("[web_seed] seeded %d docs into namespace=%s", added_count, namespace)
        return added_count
    except Exception as e:
        logger.exception("[web_seed] failed: %s", e)
        return 0

# ── truthy helpers & metrics wrapper ─────────────────────────────────────────
def _truthy_env(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1","true","yes","y","on"}

def _truthy_cfg(name: str, default: bool = False) -> bool:
    try:
        return bool(config.truthy(name, default))
    except Exception:
        return _truthy_env(name, default)

def _metrics_disabled() -> bool:
    if _truthy_cfg("METRICS_DISABLED", False): return True
    if _truthy_cfg("DISABLE_METRICS", False):  return True
    v = (os.getenv("METRICS_ENABLED") or "").strip().lower()
    if v in ("0","false","no","off"): return True
    return False

def _try_call(fn) -> None:
    try:
        fn()
    except Exception:
        pass

def _metrics_call(name: str, fn, timeout_s: float = 0.15) -> None:
    if _metrics_disabled():
        return
    try:
        t = threading.Thread(target=lambda: _try_call(fn), name=f"metrics:{name}", daemon=True)
        t.start()
        t.join(timeout_s)
    except Exception:
        pass

from core.paths import research_base_dir

# ── Gatekeep ─────────────────────────────────────────────────────────────────
from settings_gatekeep import (
    gatekeep_enabled,
    url_allowed,
    _normalize_host,
    get_allowed_domains,
    set_runtime_allowed_domains,
)

try:
    from settings_gatekeep import refresh_gatekeep_cache
    refresh_gatekeep_cache()
except Exception:
    pass

# ── 의도 추정/리랭크 ─────────────────────────────────────────────────────────
def _infer_intent_from_query(q: str) -> str:
    ql = (q or "").lower()
    if any(k in ql for k in ["규제", "허가", "고시", "공고", "mfds", "법령", "식품의약품안전처"]):
        return "regulation"
    if any(k in ql for k in ["시장", "규모", "점유율", "통계", "kosis", "index.go.kr", "khidi"]):
        return "stats"
    if any(k in ql for k in ["뉴스", "보도", "기사", "단신", "속보", "news", "press"]):
        return "news"
    return "generic"

def _rerank_with_intent_and_diversity(items: List[Dict[str, Any]], *, intent: str, kr_boost: bool, domain_penalty: float) -> List[Dict[str, Any]]:
    def _host(u: str) -> str:
        try:
            from urllib.parse import urlparse
            h = (urlparse(u).netloc or "").lower()
            if h.startswith("m."): h = h[2:]
            if h.startswith("amp."): h = h[4:]
            return h
        except Exception:
            return ""

    host_seen: Dict[str, int] = {}
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for it in items or []:
        u = it.get("url") or it.get("source") or ""
        h = _host(u)
        base = float(it.get("score") or 1.0)
        repeat = host_seen.get(h, 0)
        base -= repeat * float(domain_penalty or 0.0)

        if intent == "stats" and any(d in h for d in ("kosis.kr", "index.go.kr", "khidi.or.kr", "hira.or.kr")):
            base += 0.35
        if intent == "news" and any(d in h for d in ("dailypharm.com", "medipana.com", "newsmp.com", "healtho.co.kr")):
            base += 0.25
        if intent == "regulation" and ("mfds.go.kr" in h or h.endswith(".go.kr")):
            base += 0.25
        if kr_boost and (h.endswith(".go.kr") or h.endswith(".kr") or h in ("dailypharm.com","medipana.com","newsmp.com")):
            base += 0.15

        url_l = (u or "").lower()
        if intent in ("news","stats") and (url_l.endswith(".pdf") or "/upload/" in url_l):
            base -= 0.10

        scored.append((base, it))
        host_seen[h] = repeat + 1

    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored]

# ── Local utils ──────────────────────────────────────────────────────────────
from .utils import (
    http_get,
    _ell, _LOG_TOPK,
    _append_default_negatives, _cap_minus_tokens,
    _apply_gatekeep_to_results, _normalize_results, _pick_top,
    _save_results, _dedupe_keep_order_dicts,
    normalize_or_block_intermediate_news,
    _MIN_RESULTS_OK as __MIN_RESULTS_OK_FALLBACK,
    _SEARCH_TOPN as __SEARCH_TOPN_FALLBACK,
    _simplify_for_naver, _should_skip_naver
)

from .utils import try_fetch_pdf, SSL_QUARANTINE  # PDF 단회 시도 / SSL 격리

from urllib.parse import urlparse
from tools.web_rag.utils import normalize_url  # URL 정규화 단일 진입점

def _canon_url(u: str) -> str:
    try:
        return normalize_url(u or "")
    except Exception:
        return u or ""
    
def _canon_and_dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    URL을 강제 정규화하고 중복을 제거합니다.
    - 모바일/AMP 변형(예: /amp) 접기
    - 추적 파라미터(utm_*, gclid, fbclid 등) 제거
    - fragment(#...) 제거
    """
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for it in items or []:
        try:
            raw = (it.get("url") or it.get("source") or "").strip()
            if not raw:
                continue
            cu = _canon_url(raw)
            if not cu or cu in seen:
                continue
            seen.add(cu)
            it2 = dict(it)
            if "url" in it2:
                it2["url"] = cu
            elif "source" in it2:
                it2["source"] = cu
            # 제목/요약 공백 정리
            if isinstance(it2.get("title"), str):
                it2["title"] = it2["title"].strip()
            if isinstance(it2.get("snippet"), str):
                it2["snippet"] = it2["snippet"].strip()
            out.append(it2)
        except Exception:
            continue
    return out


def _host_for_log(u: str) -> str:
    try:
        pu = urlparse(normalize_url(u))
        host = (pu.netloc or "").strip().lower()
        return host.split("/", 1)[0]
    except Exception:
        try:
            pu2 = urlparse(u)
            host = (pu2.netloc or "").strip().lower()
            return host.split("/", 1)[0]
        except Exception:
            return ""

import re as _re
from datetime import timezone

def _looks_korean(q: str) -> bool:
    if not q:
        return False
    if any('\uac00' <= ch <= '\ud7a3' for ch in q):
        return True
    ql = q.lower()
    return (".kr" in ql) or (" korea" in ql) or (" ko-kr" in ql) or (" site:naver.com" in ql)

def _looks_like_pdf_url(u: str) -> bool:
    if not u:
        return False
    s = u.lower()
    return (
        s.endswith(".pdf")
        or "filedown" in s
        or "filedownload" in s
        or "filedowntype" in s
        or "downfile" in s
    )


# ── 연도 범위 확장(예: 2023..2025 → (2023 OR 2024 OR 2025)) ──────────────────
_YEAR_RANGE_RE = _re.compile(r"\b(19|20)\d{2}\.\.(19|20)\d{2}\b")

def _expand_year_ranges(q: str, *, max_span: int = 6) -> str:
    """
    '2023..2025' → '(2023 OR 2024 OR 2025)'
    과도 확장 방지: max_span(기본 6년) 초과면 원문 유지.
    연도 패턴(19xx/20xx)에만 반응.
    """
    def _repl(m: _re.Match[str]) -> str:
        raw = m.group(0)
        a, b = raw.split("..", 1)
        try:
            ya, yb = int(a), int(b)
        except Exception:
            return raw
        if yb < ya:
            ya, yb = yb, ya
        if (yb - ya) > max_span:
            return raw
        years = " OR ".join(str(y) for y in range(ya, yb + 1))
        return f"({years})"
    try:
        return _YEAR_RANGE_RE.sub(_repl, q)
    except Exception:
        return q

def _pretag_content_type(items: List[Dict[str, Any]]) -> None:
    for it in items or []:
        if it.get("content_type"):
            continue
        u = it.get("url") or it.get("source") or ""
        if _looks_like_pdf_url(u):
            it["content_type"] = "application/pdf"

def _annotate_fetch_meta(items: List[Dict[str, Any]]) -> None:
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for it in items or []:
        raw = it.get("raw_content")
        if isinstance(raw, str) and raw:
            try:
                it["raw_bytes"] = len(raw.encode("utf-8"))
            except Exception:
                it["raw_bytes"] = len(raw)
            if (it.get("content_type") or "").strip() == "":
                if raw.lstrip().startswith("%PDF-"):
                    it["content_type"] = "application/pdf"
            it["fetched_at"] = now_iso
        if not it.get("content_type"):
            u = it.get("url") or it.get("source") or ""
            if _looks_like_pdf_url(u):
                it["content_type"] = "application/pdf"

def _fetch_pdf_once(u: str, timeout: int = 20) -> Optional[bytes]:
    """
    동일 URL은 세션 생존 동안 SSLError 발생 시 재시도하지 않도록 격리.
    성공 시 bytes 반환, 실패/격리 시 None.
    """
    if not u or u in SSL_QUARANTINE:
        return None
    return try_fetch_pdf(u, timeout=timeout)

def _enrich_raw_content(items: List[Dict[str, Any]], *, timeout: int = 20) -> None:
    """
    결과 원문 보강:
      - PDF URL: try_fetch_pdf()로 단회 시도 → 성공하면 raw_bytes만 기록(텍스트 추출은 별도 파서 단계)
                  실패(예: SSLError) 시 같은 세션에서 재시도하지 않음. 단, HTML 폴백 1회만 시도.
      - 비-PDF URL: 기존 HTML 경로(http_get) 1회만 시도하여 text를 raw_content에 저장.
    """
    if not items:
        return
    for it in items or []:
        try:
            u = it.get("url") or it.get("source") or ""
            if not u:
                continue
            # 이미 채워진 경우 스킵
            if it.get("raw_content"):
                continue

            if _looks_like_pdf_url(u):
                pdf_bytes = _fetch_pdf_once(u, timeout=timeout)
                if pdf_bytes:
                    it["raw_content"] = ""  # 텍스트 변환은 다운스트림 파서에 맡김
                    it["raw_bytes"] = len(pdf_bytes)
                    it["content_type"] = it.get("content_type") or "application/pdf"
                else:
                    # SSLError 등 실패 시: HTML 폴백 1회만 시도
                    try:
                        r = http_get(u, timeout=timeout)
                        if r is not None:
                            it["raw_content"] = r.text or ""
                    except Exception:
                        pass
            else:
                # 비-PDF: HTML 1회만
                r = http_get(u, timeout=timeout)
                if r is not None:
                    it["raw_content"] = r.text or ""
        except Exception:
            continue

# ---- 선택적 파서(존재 시 사용, 미설치라면 안전 폴백) ----
from types import ModuleType

try:
    import PyPDF2 as _pypdf2_mod  # noqa: F401
    _pypdf2: Optional[ModuleType] = _pypdf2_mod
except Exception:
    _pypdf2 = None

try:
    from pdfminer.high_level import extract_text as _pdfminer_extract_text_mod  # noqa: F401
    _pdfminer_extract_text: Optional[Callable[..., str]] = _pdfminer_extract_text_mod
except Exception:
    _pdfminer_extract_text = None

# =============================================================================
# Backend calls
# =============================================================================
def _search_tavily(query: str, *, num: int = 10, timeout: int = 15) -> List[Dict[str, Any]]:
    api_key = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not (getattr(CFG, "HAS_TAVILY", False) and api_key):
        return []
    try:
        try:
            from tavily import TavilyClient  # type: ignore[import-untyped]
        except Exception:  # pragma: no cover
            logger.debug("tavily module not available; skipping tavily backend.")
            return []
        client = TavilyClient(api_key=api_key)
        max_results = max(1, min(int(num or 10), 5))
        resp = client.search(
            query=query,
            search_depth="basic",
            include_raw_content=False,
            max_results=max_results,
            timeout=timeout,
        )
        items: List[Dict[str, Any]] = []
        if isinstance(resp, dict):
            items = resp.get("results", []) or []
        else:
            for r in getattr(resp, "results", []) or []:
                items.append(r.model_dump() if hasattr(r, "model_dump") else dict(r))
        parsed: List[Dict[str, Any]] = []
        for it in items:
            parsed.append({
                "title": it.get("title") or "",
                "url": _canon_url(it.get("url") or ""),
                "content": (it.get("content") or "")[:2000],
                "raw_content": "",
                "source": _canon_url(it.get("url") or ""),
            })
        return parsed
    except Exception as e:
        logger.warning("Tavily search failed: %s", e)
        return []

def _search_google_cse(query: str, *, num: int = 10, timeout: int = 20) -> List[Dict[str, Any]]:
    api_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_CSE_API_KEY") or "").strip()
    cse_id  = (os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CSE_CX") or "").strip()
    if not (getattr(CFG, "HAS_GOOGLE_KEYS", False) and api_key and cse_id):
        return []
    try:
        gl = os.getenv("GOOGLE_CSE_GL") or os.getenv("SEARCH_GL") or "us"
        lr = os.getenv("GOOGLE_CSE_LR") or ""
        hl = os.getenv("SEARCH_HL", "en")
        num = max(1, min(int(num or 10), 10))

        g_cap = max(3, int(os.getenv("GOOGLE_TIMEOUT_SEC", str(DEFAULT_TIMEOUT_SECONDS))))
        timeout = min(timeout, g_cap)

        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": api_key, "cx": cse_id, "q": query, "num": num, "hl": hl, "gl": gl}
        if lr:
            params["lr"] = lr

        r = http_get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json() or {}
        items = data.get("items") or []
        parsed: List[Dict[str, Any]] = []
        for it in items:
            link = _canon_url(it.get("link") or it.get("formattedUrl") or "")
            if not link:
                continue
            parsed.append({
                "title": it.get("title") or it.get("htmlTitle") or link,
                "url": link,
                "content": it.get("snippet") or it.get("htmlSnippet") or "",
                "raw_content": "",
                "source": link,
            })
        return parsed
    except Exception as e:
        logger.warning("Google CSE search failed: %s", e)
        return []

def _search_serpapi(query: str, *, num: int = 10, timeout: int = 20) -> List[Dict[str, Any]]:
    api_key = (os.getenv("SERPAPI_API_KEY") or "").strip()
    if not (api_key and getattr(CFG, "HAS_SERPAPI", False)):
        return []
    try:
        from serpapi import GoogleSearch  # type: ignore[import-untyped]
        hl = os.getenv("SEARCH_HL", "en")
        gl = os.getenv("SEARCH_GL", "us")
        num = max(1, min(int(num or 10), 100))

        params = {"engine": "google", "q": query, "api_key": api_key, "num": num, "hl": hl}
        if gl:
            params["gl"] = gl

        search = GoogleSearch(params)
        res = search.get_dict() or {}
        items = (res.get("organic_results") or [])[:num]

        parsed: List[Dict[str, Any]] = []
        for it in items:
            link = _canon_url(it.get("link") or "")
            if not link:
                continue
            parsed.append({
                "title": it.get("title") or link,
                "url": link,
                "content": it.get("snippet") or "",
                "raw_content": "",
                "source": link,
            })
        return parsed
    except Exception as e:
        logger.warning("SerpAPI search failed: %s", e)
        return []

def _search_naver_direct(query: str, *, num: int = 10, timeout: int = 20) -> List[Dict[str, Any]]:
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not (client_id and client_secret):
        logger.debug("Naver direct search skipped: credential not set.")
        return []
    q_naver = _simplify_for_naver(query)
    if not q_naver or len(q_naver) < 2:
        logger.info("[Naver(Direct)] skipped (empty after simplify)")
        return []
    from urllib.parse import quote
    encoded_query = quote(q_naver)
    url = "https://openapi.naver.com/v1/search/news.json"
    num = max(1, min(int(num or 10), 100))
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    params = {"query": q_naver, "display": num, "start": 1, "sort": "sim"}
    logger.debug("[Naver(Direct)][query] %s (encoded: %s)", _ell(q_naver), encoded_query[:50] + "...")
    try:
        r = http_get(url, headers=headers, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json() or {}
        items = data.get("items") or []
        parsed: List[Dict[str, Any]] = []
        for it in items:
            link = _canon_url(it.get("link") or it.get("url") or "")
            if not link:
                continue
            parsed.append({
                "title": it.get("title") or link,
                "url": link,
                "content": it.get("description") or "",
                "raw_content": "",
                "source": link,
            })
        logger.debug("[Naver(Direct)] success. items=%d", len(parsed))
        return parsed
    except requests.exceptions.HTTPError as e:
        logger.warning("Naver(Direct) HTTP Error %s: %s (query=%s)",
                         getattr(e.response, "status_code", "?"),
                         getattr(e.response, "text", ""), _ell(q_naver))
        return []
    except Exception as e:
        logger.warning("Naver(Direct) search failed: %s", e)
        return []

def _search_serpapi_naver(query: str) -> List[dict]:
    api_key = (os.getenv("SERPAPI_API_KEY") or "").strip()
    if not api_key:
        return []
    q_naver = _simplify_for_naver(query)
    if not q_naver or len(q_naver) < 2:
        logger.info("[SerpAPI(Naver)] skipped (empty after simplify)")
        return []
    if _should_skip_naver(q_naver):
        logger.info("[SerpAPI(Naver)] skipped (complex after simplify): %s", _ell(q_naver))
        return []
    num = int(os.getenv("SERPAPI_NAVER_NUM", "10"))
    hl  = (os.getenv("SERPAPI_NAVER_HL") or "ko").strip()
    gl  = (os.getenv("SERPAPI_NAVER_GL") or "kr").strip()
    where = (os.getenv("SERPAPI_NAVER_WHERE") or "web").strip()
    try_others = _truthy_cfg("SERPAPI_NAVER_TRY_OTHERS", False)
    url = "https://serpapi.com/search.json"
    logger.debug("[SerpAPI(Naver)][query] %s", _ell(q_naver))

    def _collect(data, sink: list):
        def _push(lst):
            for r in lst or []:
                link = _canon_url(r.get("link") or r.get("url") or "")
                if not link:
                    continue
                title = r.get("title") or ""
                snippet = r.get("snippet") or r.get("snippet_highlighted_words") or ""
                if isinstance(snippet, list):
                    snippet = " ".join(snippet)
                sink.append({"title": title, "url": link, "source": link, "content": snippet or ""})
        _push(data.get("organic_results"))
        if not sink: _push(data.get("web_results"))
        if not sink: _push(data.get("news_results"))
        if not sink: _push(data.get("blog_results"))

    def _req(params: dict) -> Tuple[List[dict], dict]:
        try:
            s = get_requests_session()
            resp = s.get(url, params=params, timeout=30, verify=s.verify)
            if resp.status_code >= 400:
                logger.warning("SerpAPI(Naver) HTTP %s (where=%s)", resp.status_code, params.get("where"))
                return [], {}
            data = resp.json() if resp.text else {}
        except Exception as e:
            logger.warning("SerpAPI(Naver) request failed: %s", e.__class__.__name__)
            return [], {}
        items: List[dict] = []
        if data.get("error"):
            logger.warning("SerpAPI(Naver) error: %s (where=%s)", data.get("error"), params.get("where"))
        sm = data.get("search_metadata") or {}
        if sm:
            logger.debug("SerpAPI(Naver) metadata: id=%s status=%s where=%s",
                          sm.get("id"), sm.get("status"), params.get("where"))
        _collect(data, items)
        return items, data

    params = {"engine": "naver", "query": q_naver, "api_key": api_key, "hl": hl, "gl": gl, "where": where, "num": num}
    items, data = _req(params)
    if items:
        return items

    params2 = dict(params); params2.pop("query", None); params2["q"] = q_naver
    items, _ = _req(params2)
    if items:
        return items

    if try_others:
        for w in ("news", "blog", "cafe"):
            params3 = dict(params); params3["where"] = w
            items, _ = _req(params3)
            if items:
                return items
            params4 = dict(params2); params4["where"] = w
            items, _ = _req(params4)
            if items:
                return items

    logger.debug("SerpAPI(Naver) returned no parsable items for query=%r (where tried: %s%s)",
                  q_naver, where, ", others" if try_others else "")
    return []

# ─────────────────────────────────────────────────────────────────────────────
# 2xx 이외 응답 사전 필터링
def _probe_http_status(u: str, timeout: float = 6.0) -> Optional[int]:
    if not u:
        return None
    try:
        s = get_requests_session()
        try:
            # 공용 세션을 통한 HEAD 요청 (세션에 설정된 verify/CA 번들 사용)
            r = s.head(u, allow_redirects=True, timeout=timeout)
            return int(r.status_code)
        except requests.exceptions.RequestException:
            try:
                # HEAD 실패 시 동일 세션으로 GET 한 번만 시도
                r2 = s.get(u, allow_redirects=True, timeout=timeout, stream=True)
                return int(r2.status_code)
            except requests.exceptions.RequestException:
                return None
    except Exception:
        return None

def _filter_non_2xx(items: List[Dict[str, Any]], *, timeout: float = 6.0, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not items:
        return items
    out: List[Dict[str, Any]] = []
    n = len(items) if limit is None else max(0, min(len(items), int(limit)))
    for idx, it in enumerate(items):
        u = it.get("url") or it.get("source") or ""
        if idx < n:
            sc = _probe_http_status(u, timeout=timeout)
            if sc is not None and not (200 <= sc < 300):
                logger.info("[web_search][drop-non2xx] %s  → HTTP %s (skip, no retry)", _host_for_log(u), sc)
                continue
        out.append(it)
    return out

# =============================================================================
# Query shaping / normalization
# =============================================================================
def _sanitize_query(q: str) -> str:
    if not q:
        return q
    s = q.strip()
    s = _re.sub(r"^\(\s*untitled\s*\)\s*", "", s, flags=_re.I)

    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

def _normalize_query(q: str) -> str:
    s = (q or "").strip()
    if not s:
        return s
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace('\\"', '"').replace("\\'", "'")
    def _site_or_repl(m: re.Match[str]) -> str:
        tail = m.group(1)
        if tail.startswith("(") and tail.endswith(")"):
            return "site:" + tail
        parts = [p.strip() for p in tail.split("|") if p.strip()]
        if len(parts) <= 1:
            p = parts[0] if parts else tail
            return p if p.lower().startswith("site:") else ("site:" + p)
        norm_parts = []
        for p in parts:
            norm_parts.append(p if p.lower().startswith("site:") else ("site:" + p))
        ors = " OR ".join(norm_parts)
        return f"({ors})"

    s = _re.sub(r"site:([^\s)]+)", _site_or_repl, s, flags=_re.I)
    # 숫자 범위 → OR 확장 (연도 한정 + 스팬 상한)
    s = _expand_year_ranges(s, max_span=6)
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

def _to_google_precision(q: str) -> str:
    s = q.strip()
    s = _re.sub(r"\s*\|\s*", " OR ", s)

    def _paren_site(m):
        block = m.group(0)
        if block.lstrip().startswith("(") and block.rstrip().endswith(")"):
            return block
        return "(" + block.strip() + ")"
    s = _re.sub(r"(?:\s*site:\S+\s*(?:OR\s*site:\S+\s*)+)", _paren_site, s, flags=_re.I)

    def _trim_year_or(group: str, keep: int = 1) -> str:
        years = _re.findall(r"\b((?:19|20)\d{2})\b", group)
        if not years:
            return group
        ys = sorted({int(y) for y in years})
        if len(ys) <= keep:
            return group
        picked = ys[-keep:]
        return "(" + " OR ".join(str(y) for y in picked) + ")"
    s = _re.sub(r"\((?:\s*(?:19|20)\d{2}\s*(?:OR\s*)?)+\)", lambda m: _trim_year_or(m.group(0), keep=1), s)

    s = _cap_minus_tokens(s, cap=2)
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

def _to_google_precision_alt(q: str) -> str:
    s = _re.sub(r"(^|\s)-\S+", " ", q).strip()
    s = _re.sub(r"\s*\|\s*", " OR ", s)
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

def _to_naver_recall(q: str) -> str:
    s = _simplify_for_naver(q)
    toks = s.split()
    if len(toks) > 5:
        s = " ".join(toks[:5])
    return s

# =============================================================================
# Backend router & helpers
# =============================================================================
def _backend_call(backend_key: str, query: str, *, num: int = 10, timeout: int = 15) -> List[Dict[str, Any]]:
    key = (backend_key or "").strip().lower()
    if key in ("google", "google_cse"):
        g_cap = max(3, int(os.getenv("GOOGLE_TIMEOUT_SEC", "8")))
        return _search_google_cse(query, num=num, timeout=min(timeout, g_cap))
    if key in ("serpapi", "serpapi_google"):
        return _search_serpapi(query, num=num, timeout=timeout)
    if key in ("naver", "serpapi_naver"):
        return _search_serpapi_naver(query)
    if key == "naver_direct":
        return _search_naver_direct(query, num=num, timeout=timeout)
    if key == "tavily":
        return _search_tavily(query, num=num, timeout=timeout)
    return []

def _normalize_backend_alias(b: str) -> str:
    b = (b or "").strip().lower()
    if b in {"google", "googlecse"}:
        return "google_cse"
    if b in {"naver", "serpapi_naver"}:
        return "serpapi_naver"
    if b in {"serpapi_google", "google_serpapi"}:
        return "serpapi"
    if b in {"tavily"}:
        return "tavily"
    if b in {"naver_direct"}:
        return "naver_direct"
    return b

def _is_googleish(q: str) -> bool:
    s = q or ""
    return any(tok in s for tok in ("site:", " OR ", " AND ", "(", ")"))

def _resolve_backend_chain(engine_arg: Optional[str], *, num: int, googleish: bool) -> List[str]:
    eng = (engine_arg or os.getenv("WEB_SEARCH_ENGINE") or "auto").strip().lower()
    cfg_backends = (getattr(CFG, "SEARCH_BACKENDS", "") or "").strip()
    default_chain = "google_cse,naver_direct,serpapi_naver,serpapi,tavily"

    if eng == "auto" and googleish:
        base = cfg_backends or (os.getenv("SEARCH_BACKENDS") or default_chain)
        chain = ["google_cse"]
        for b in base.split(","):
            a = _normalize_backend_alias(b.strip())
            if a and a not in chain:
                chain.append(a)
        return chain

    if eng and eng != "auto":
        fallback = cfg_backends or (os.getenv("SEARCH_BACKENDS") or default_chain)
        chain = [_normalize_backend_alias(eng)]
        for b in fallback.split(","):
            a = _normalize_backend_alias(b.strip())
            if a and a not in chain:
                chain.append(a)
        return chain

    src_list = cfg_backends or (os.getenv("SEARCH_BACKENDS") or "")
    if src_list:
        return [_normalize_backend_alias(s) for s in src_list.split(",") if s.strip()]

    return [s.strip() for s in default_chain.split(",")]

# =============================================================================
# Public Tool: web_search
# =============================================================================
@tool("web_search")
def web_search(
    query: str,
    *,
    engine: Optional[str] = None,  # "auto" | "tavily" | "google" | "serpapi" | "naver"
    num: int = 10,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    멀티 엔진 웹검색 (Google CSE ↔ Naver Direct/SerpAPI ↔ Tavily)
    반환: (results[list[dict]], json_path[str])
    - 결과 스키마: {title, url, content, raw_content, source}
    - ENV:
      SEARCH_POLICY=best_of_chain | first_ok
      SEARCH_MIN_OK=1
      SEARCH_TOPN=10
      SEARCH_BACKENDS=google_cse,naver_direct,serpapi_naver,serpapi,tavily
      SEARCH_TIME_BUDGET_SEC=25
      BACKEND_TIMEOUT_SEC=15 (cap to DEFAULT_TIMEOUT_SECONDS)
    """
    try:
        reload_config()
        from settings_gatekeep import refresh_gatekeep_cache as _refresh_gk
        _refresh_gk()
    except Exception:
        pass

    # NOTE: 검색 모듈은 인덱스 병합/조회(retrieval)를 수행하지 않습니다.
    # CHROMA_INCLUDE_BASE는 agent/vector_search.py 등 'retrieval' 단계에서만 동작합니다.
    try:
        _incl = getattr(CFG, "CHROMA_INCLUDE_BASE", None)
        if _incl is None:
            _incl = (os.getenv("CHROMA_INCLUDE_BASE", "").strip().lower() in {"1","true","yes","on"})
        logger.debug("[web_search] CHROMA_INCLUDE_BASE=%s (info only; used in retrieval stage)", bool(_incl))
    except Exception:
        pass

    engine = (engine or os.getenv("WEB_SEARCH_ENGINE") or "auto").strip().lower()
    results: List[Dict[str, Any]] = []
    used: Optional[str] = None
    path: Optional[str] = None

    raw_query = query
    if not (raw_query and str(raw_query).strip()):
        logger.info("[web_search] empty query → skip")
        try:
            path = _save_results([], query="")
        except TypeError:
            path = _save_results([], query="", base_dir=str(research_base_dir()))
        return [], path

    logger.info("[web_search][query] %s", _ell(raw_query))

    if _truthy_cfg("SEARCH_PREFLIGHT_PING", False):
        try:
            _ = http_get("https://www.google.com", timeout=1)
        except Exception:
            logger.warning("[web_search] preflight ping failed (non-fatal)")

    try:
        round_id = os.getenv("RUN_ROUND_ID") or datetime.now().isoformat(timespec="seconds")
        _metrics_call("set_round", lambda: set_round(round_id))
        _metrics_call("record_query_issued", record_query_issued)
    except Exception:
        pass

    try:
        allowed_domains = sorted(get_allowed_domains())
        if gatekeep_enabled():
            logger.info("[GATEKEEP] enabled; allowed=%s (n=%d)",
                        ", ".join(allowed_domains), len(allowed_domains))
            set_runtime_allowed_domains(allowed_domains)
        else:
            logger.info("[GATEKEEP] disabled")
    except Exception as e:
        logger.warning("[GATEKEEP] runtime allowed-domains injection failed: %s", e)

    forced_backend = None
    m = _re.match(r"backend\s*:\s*([a-zA-Z0-9_]+)\s*;\s*(.*)", raw_query)
    if m:
        forced_backend = _normalize_backend_alias(m.group(1))
        raw_query = m.group(2).strip()
        logger.info("[backend.forced] %s (via query directive)", forced_backend)

    base_query = _sanitize_query(raw_query)
    base_query = _normalize_query(base_query)
    if base_query != raw_query:
        logger.debug("[web_search][sanitized] %s  ←  %s", base_query, raw_query)

    _ = _append_default_negatives(base_query)

    _policy = (getattr(CFG, "SEARCH_POLICY", "best_of_chain") or "best_of_chain").strip()
    _min_ok = int(getattr(CFG, "SEARCH_MIN_OK", __MIN_RESULTS_OK_FALLBACK) or __MIN_RESULTS_OK_FALLBACK)
    _topn   = int(getattr(CFG, "SEARCH_TOPN", __SEARCH_TOPN_FALLBACK) or __SEARCH_TOPN_FALLBACK)

    try:
        if gatekeep_enabled():
            _topn_allow = int(os.getenv("SEARCH_TOPN_ALLOW", "15"))
            if _topn_allow > _topn:
                logger.debug("[web_search] gatekeep on → topn boost: %d → %d", _topn, _topn_allow)
                _topn = _topn_allow
    except Exception:
        pass
    try:
        _time_budget = float(os.getenv("SEARCH_TIME_BUDGET_SEC", "25"))
    except Exception:
        _time_budget = 25.0
    if _time_budget < 5.0:
        _time_budget = 5.0

    try:
        _cfg_search_timeout = getattr(CFG, "SEARCH_TIMEOUT", None)
        if _cfg_search_timeout is not None:
            _backend_timeout = int(_cfg_search_timeout)
        else:
            _backend_timeout = int(os.getenv("BACKEND_TIMEOUT_SEC", str(DEFAULT_TIMEOUT_SECONDS)))
    except Exception:
        _backend_timeout = DEFAULT_TIMEOUT_SECONDS
    if _backend_timeout < 3:
        _backend_timeout = 3
    if _backend_timeout > DEFAULT_TIMEOUT_SECONDS:
        logger.debug("[web_search] cap backend timeout: %ss → %ss",
                     _backend_timeout, DEFAULT_TIMEOUT_SECONDS)
        _backend_timeout = DEFAULT_TIMEOUT_SECONDS
    if _backend_timeout > _time_budget:
        _backend_timeout = max(3, int(_time_budget) - 1)

    t_start = time.monotonic()

    try:
        logger.debug("[web_search][diag] before chain resolve")
        googleish = _is_googleish(base_query)
        chain = _resolve_backend_chain(engine, num=num, googleish=googleish)
        if _looks_korean(base_query) and "naver_direct" in chain:
            seen: set[str] = set()
            new_chain: List[str] = ["naver_direct"]
            for b in chain:
                if b == "naver_direct":
                    continue
                if b not in seen:
                    new_chain.append(b)
                    seen.add(b)
            chain = new_chain
        logger.debug("[web_search][diag] after chain resolve: %s", chain)
        if forced_backend:
            chain = [forced_backend] + [b for b in chain if b != forced_backend]
    except Exception as e:
        logger.warning("[web_search] chain resolve failed (%s) → fallback to ['google_cse']", e)
        chain = ["google_cse"]

    logger.info("[web_search][chain] %s | policy=%s min_ok=%d topn=%d budget=%.1fs timeout=%ds",
                " → ".join(chain), _policy, _min_ok, _topn, _time_budget, _backend_timeout)

    def _budget_left() -> float:
        return _time_budget - (time.monotonic() - t_start)

    _kr_context = _looks_korean(base_query)
    _naver_in_chain = any(b in ("naver_direct", "serpapi_naver") for b in chain)
    _naver_called = False
    _naver_reserved = 4.0 if (_kr_context and _naver_in_chain) else 0.0
    logger.debug("[web_search][A3] kr=%s | naver_in_chain=%s | reserved=%.2fs",
             _kr_context, _naver_in_chain, _naver_reserved)

    tried = []
    allowlist_hits = 0
    early_stop_reason: Optional[str] = None
    _accum_count = 0
    _min_backends = max(2, int(os.getenv("SEARCH_MIN_BACKENDS", "2")))
    _backends_with_results: set[str] = set()

    for bk in chain:
        if _naver_reserved > 0 and not _naver_called and bk not in ("naver_direct", "serpapi_naver"):
            if _budget_left() <= _naver_reserved:
                logger.info("[web_search] reserve budget for naver (left=%.2fs, reserve=%.2fs) → skip %s for now",
                            _budget_left(), _naver_reserved, bk)
                continue

        if _budget_left() <= 0:
            logger.info("[web_search] time budget exceeded before backend=%s", bk)
            break

        start = time.monotonic()

        if bk in ("google", "google_cse", "tavily", "serpapi"):
            base_q = base_query
            q_prec_a = _to_google_precision(base_q)
            q_prec_b = _to_google_precision_alt(base_q)
            q_prec_a_neg = _append_default_negatives(q_prec_a)
            if bk == "tavily":
                variants = [("precAneg", q_prec_a_neg)]
            else:
                variants = [("precAneg", q_prec_a_neg), ("precA", q_prec_a), ("precB", q_prec_b)]
        elif bk in ("naver", "serpapi_naver", "naver_direct"):
            variants = [("recall", _to_naver_recall(base_query))]
        else:
            variants = [("default", base_query)]

        best_res: List[Dict[str, Any]] = []
        used_label = None
        for label, q_use in variants:
            if _budget_left() <= 0:
                logger.info("[web_search] time budget exceeded during variants on %s", bk)
                break
            try:
                to = min(_backend_timeout, max(3, int(_budget_left())))
                logger.info("[web_search] calling backend=%s variant=%s timeout=%ss", bk, label, to)
                _res = _backend_call(bk, q_use, num=num, timeout=to) or []
                logger.info("[web_search] backend=%s variant=%s got=%d", bk, label, len(_res))
            except Exception as e:
                logger.warning("web_search backend '%s' failed on %s: %s", bk, label, e)
                _res = []

            if _res:
                best_res = _res; used_label = label
                if _policy == "first_ok" and len(_res) >= _min_ok:
                    break

        dur = time.monotonic() - start
        tried.append((f"{bk}:{used_label or 'none'}", len(best_res), best_res))

        if best_res:
            try:
                _allowed_cnt = 0
                for _it in best_res:
                    _u = _it.get("url") or _it.get("source") or ""
                    # ✅ 정규화된 URL 기준으로 게이트키핑 (normalize_url 일관 사용)
                    if _u and url_allowed(_canon_url(_u)):
                        _allowed_cnt += 1
                if _allowed_cnt:
                    allowlist_hits += _allowed_cnt
            except Exception:
                _allowed_cnt = 0
            _backends_with_results.add(bk)

            if (_policy in ("best_of_chain", "first_ok")) and (allowlist_hits >= _min_ok):
                if len(_backends_with_results) >= _min_backends:
                    early_stop_reason = f"allowlist_min_ok(backends={len(_backends_with_results)})"
                    logger.debug("[backend.pick] early stop by allowlist after %d backends (hits=%d ≥ min_ok=%d, bk=%s)",
                                 len(_backends_with_results), allowlist_hits, _min_ok, bk)
                    results = []
                    used = None
                    break
                else:
                    logger.debug("[backend.pick] allowlist hit but continue (results_backends=%d < min_backends=%d)",
                                 len(_backends_with_results), _min_backends)

        if _policy == "best_of_chain" and best_res:
            _accum_count += len(best_res)
            if _accum_count >= _topn:
                logger.debug("[backend.pick] early stop: accumulated=%d >= topn=%d", _accum_count, _topn)
                results = []
                used = None
                break

        logger.debug("[web_search][backend tried] %-18s got=%2d in %.2fs",
                      f"{bk}:{used_label or 'none'}", len(best_res), dur)

        if bk in ("naver_direct", "serpapi_naver"):
            _naver_called = True
            _naver_reserved = 0.0

        _metrics_call(f"record_backend_latency:{bk}", lambda: record_backend_latency(bk, float(dur)))

        if _policy == "first_ok" and len(best_res) >= _min_ok:
            results, used = best_res, f"{bk}:{used_label}"
            break

    if not results and _kr_context and _naver_in_chain and not _naver_called and _budget_left() > 1.5:
        try:
            to = int(max(2.0, min(float(_backend_timeout), _budget_left())))
            logger.info("[web_search] forcing one naver_direct call (timeout=%ss, budget_left=%.2f)",
                        to, _budget_left())
            _res = _backend_call("naver_direct", _to_naver_recall(base_query), num=num, timeout=to) or []
            if _res:
                tried.append(("naver_direct:forced", len(_res), _res))
        except Exception as e:
            logger.warning("[web_search] forced naver_direct failed: %s", e)

    if not results:
        if _policy == "best_of_chain":
            merged: List[Dict[str, Any]] = []
            for _, _, res in tried:
                merged.extend(res or [])
            # ✅ 1차: 강한 URL 정규화 + 디듀프
            merged = _canon_and_dedupe(merged)
            # ✅ 2차: 기존의 결과 정규화/정렬 유틸과 병행 적용(보강용)
            merged = _dedupe_keep_order_dicts(_normalize_results(merged))

            _intent = _infer_intent_from_query(base_query)
            merged = _rerank_with_intent_and_diversity(merged, intent=_intent, kr_boost=_kr_context,
                                                       domain_penalty=0.15)

            merged = _pick_top(merged, _topn)
            results = merged
            used = f"merged{(':'+early_stop_reason) if early_stop_reason else ''}"
            logger.debug("[backend.pick] best_of_chain → merged(%d)", len(results))
        elif tried:
            best = max(tried, key=lambda t: t[1])
            used, best_count, best_res = best[0], best[1], best[2]
            results = best_res
            logger.debug("[backend.pick] first_ok/best_of_chain fallback → %s (count=%d)", used, best_count)

    if not results and _budget_left() > 2.0:
        time.sleep(0.6)
        retried: List[Tuple[str, int, List[dict]]] = []
        retry_allowlist_hits = 0
        _retry_backends_with_results: set[str] = set()
        for bk in chain:
            if _budget_left() <= 0:
                logger.info("[web_search] time budget exceeded before retry backend=%s", bk)
                break
            _retry_t0 = time.monotonic()
            if bk in ("google", "google_cse", "tavily", "serpapi"):
                q_prec_a = _to_google_precision(base_query)
                q_prec_b = _to_google_precision_alt(base_query)
                q_prec_a_neg = _append_default_negatives(q_prec_a)
                vset = [("precAneg", q_prec_a_neg), ("precA", q_prec_a), ("precB", q_prec_b)]
            elif bk in ("naver", "serpapi_naver", "naver_direct"):
                vset = [("recall", _to_naver_recall(base_query))]
            else:
                vset = [("default", base_query)]

            best_res_r: List[dict] = []
            used_label = None
            for label, q_use in vset:
                if _budget_left() <= 0:
                    logger.info("[web_search] time budget exceeded during retry variants on %s", bk)
                    break
                try:
                    logger.info("[web_search][retry] backend=%s variant=%s timeout=%ss", bk, label, _backend_timeout)
                    _res = _backend_call(bk, q_use, num=num, timeout=_backend_timeout) or []
                    logger.info("[web_search][retry] backend=%s variant=%s got=%d", bk, label, len(_res))
                except Exception:
                    _res = []
                if _res:
                    best_res_r = _res; used_label = label
                    if _policy == "first_ok" and len(best_res_r) >= _min_ok:
                        break
            retried.append((f"{bk}:{used_label or 'none'}", len(best_res_r), best_res_r))

            if best_res_r:
                try:
                    _allowed_cnt_r = 0
                    for _it in best_res_r:
                        _u = _it.get("url") or _it.get("source") or ""
                        # ✅ 재시도 단계도 정규화된 URL 기준으로 게이트키핑
                        if _u and url_allowed(_canon_url(_u)):
                            _allowed_cnt_r += 1
                    if _allowed_cnt_r:
                        retry_allowlist_hits += _allowed_cnt_r
                except Exception:
                    _allowed_cnt_r = 0
                _retry_backends_with_results.add(bk)

                if (_policy in ("best_of_chain", "first_ok")) and (retry_allowlist_hits >= _min_ok):
                    if len(_retry_backends_with_results) >= _min_backends:
                        early_stop_reason = f"allowlist_min_ok(retry,backends={len(_retry_backends_with_results)})"
                        logger.debug("[web_search][retry] early stop by allowlist after %d backends: hits=%d ≥ min_ok=%d (bk=%s)",
                                     len(_retry_backends_with_results), retry_allowlist_hits, _min_ok, bk)
                        results = []
                        used = None
                        break
                    else:
                        logger.debug("[web_search][retry] allowlist hit but continue (results_backends=%d < min_backends=%d)",
                                     len(_retry_backends_with_results), _min_backends)

            _metrics_call(f"record_backend_latency:{bk}", lambda: record_backend_latency(bk, float(time.monotonic() - _retry_t0)))

            if _policy == "first_ok" and len(best_res_r) >= _min_ok:
                results, used = best_res_r, f"{bk}:{used_label}(retry)"
                break
            if _policy == "best_of_chain" and _accum_count >= _topn:
                logger.debug("[web_search] early stop triggered before exhausting backends (best_of_chain)")

        if not results and retried:
            if _policy == "best_of_chain":
                merged = []
                for _, _, res in retried:
                    merged.extend(res or [])
                # ✅ 재시도 병합에도 동일 규칙 적용
                merged = _canon_and_dedupe(merged)
                merged = _dedupe_keep_order_dicts(_normalize_results(merged))

                _intent = _infer_intent_from_query(base_query)
                merged = _rerank_with_intent_and_diversity(merged, intent=_intent, kr_boost=_kr_context,
                                                           domain_penalty=0.15)

                merged = _pick_top(merged, _topn)
                results, used = merged, f"merged(retry){(':'+early_stop_reason) if early_stop_reason else ''}"
            else:
                best = max(retried, key=lambda t: t[1])
                used, _, results = f"{best[0]}(retry)", best[1], best[2]

    if results:
        logger.info("[web_search][backend] %s  | got=%d (policy=%s, min_ok=%d, topn=%d, spent=%.2fs)",
                     used, len(results), _policy, _min_ok, _topn, (time.monotonic()-t_start))
    else:
        _metrics_call("record_zero_result", record_zero_result)
        _metrics_call("zero_result_query", lambda: event("zero_result_query", query=base_query))

    # ✅ 최종 단계에서도 한 번 더 보강(앞선 단계의 결과라도 안전 재확인)
    results = _canon_and_dedupe(results)
    _pretag_content_type(results)
    results = _apply_gatekeep_to_results(results)
    results = _pick_top(results, _topn)
    try:
        probe_timeout = float(os.getenv("WEB_FETCH_PROBE_TIMEOUT", "6"))
    except Exception:
        probe_timeout = 6.0
    try:
        probe_limit = int(os.getenv("WEB_FETCH_PROBE_LIMIT", str(_topn)))
    except Exception:
        probe_limit = _topn
    results = _filter_non_2xx(results, timeout=probe_timeout, limit=probe_limit)
    _enrich_raw_content(results)
    results = [it for it in results if not normalize_or_block_intermediate_news(it.get("url") or it.get("source") or "")[1]]
    _annotate_fetch_meta(results)

    try:
        path = _save_results(results, query=raw_query, base_dir=str(research_base_dir()))
    except TypeError:
        path = _save_results(results, query=raw_query)
    except Exception as e:
        logger.warning("[web_search][final save] failed: %s", e)
        try:
            path = _save_results(results, query=raw_query)
        except Exception as e_f:
            logger.warning("[web_search][final save] failed on fallback: %s", e_f)
            try:
                path = str(Path(research_base_dir()) / "web_search_fallback.json")
            except Exception:
                path = str(Path.cwd() / "web_search_fallback.json")

    if results:
        _metrics_call("backend_selected",
                      lambda: event("backend_selected", backend=str(used or "none"),
                                    result_count=len(results)))

    lines = []
    for i, it in enumerate(results[:_LOG_TOPK], start=1):
        t = _ell(it.get("title") or it.get("name") or "(no title)")
        u = it.get("url") or it.get("source") or it.get("link") or ""
        # 로그에도 정규화 URL을 그대로 사용
        lines.append(f"  {i:>2}. {t}\n      └─ {_host_for_log(u)} :: {_canon_url(u)}")
    if lines:
        logger.info("[web_search][top%d]\n%s", min(_LOG_TOPK, len(results)), "\n".join(lines))

    logger.info("[web_search] backend=%s, results=%d, saved=%s", used, len(results), path)
    return results, path if path is not None else str(Path.cwd() / "web_search_fallback.json")
