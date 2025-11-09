from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import re
import os, json, time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Sequence, Callable
from datetime import datetime
import threading

import requests
from langchain_core.tools import tool
from tools.web_rag.ingest import get_requests_session  # 공용 재시도 세션/CA 번들 재사용

# ── Timeout defaults (module-level) ──────────────────────────────────────────
# P1-3: 재시도·타임아웃 완화 (Tavily 6→8초)
# 전역 기본 타임아웃 상수. 후속에서 CFG.SEARCH_TIMEOUT 또는 ENV 로 오버라이드 가능.
DEFAULT_TIMEOUT_SECONDS: int = 8


from typing import Any  # for untyped 3rd-party fallbacks
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
def _truthy_env(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1","true","yes","y","on"}

def _truthy_cfg(name: str, default: bool = False) -> bool:
    # config.truthy가 있으면 우선 사용
    try:
        return bool(config.truthy(name, default))
    except Exception:
        return _truthy_env(name, default)

def _metrics_disabled() -> bool:
    # CFG/ENV 통합: METRICS_DISABLED, DISABLE_METRICS, METRICS_ENABLED=0 중 하나라도 true면 비활성
    if _truthy_cfg("METRICS_DISABLED", False): return True
    if _truthy_cfg("DISABLE_METRICS", False):  return True
    # enabled 플래그는 반대 의미(0/false → 비활성)
    v = (os.getenv("METRICS_ENABLED") or "").strip().lower()
    if v in ("0","false","no","off"): return True
    return False

def _try_call(fn) -> None:
    try:
        fn()
    except Exception:
        pass

def _metrics_call(name: str, fn, timeout_s: float = 0.15) -> None:
    """
    메트릭스 호출이 메인 플로우를 블로킹하지 않도록 보호.
    - timeout_s 내에 끝나지 않으면 조용히 스킵.
    - 예외는 삼켜서 검색 로직에 영향 없게 함.
    - METRICS_DISABLED/ DISABLE_METRICS/ METRICS_ENABLED=0 로 전체 비활성화 가능.
    """
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
    _normalize_host,    # 로그 요약용 (없으면 제거 가능)
    get_allowed_domains,
    set_runtime_allowed_domains,
)

# Gatekeep 캐시를 모듈 로드시 최신 상태로 강제 동기화
try:
    from settings_gatekeep import refresh_gatekeep_cache
    refresh_gatekeep_cache()  # 인자/ENV 반영 후 항상 최신화
except Exception:
    pass

def _infer_intent_from_query(q: str) -> str:
    """쿼리에서 의도 힌트를 추정: stats | news | regulation | generic"""
    ql = (q or "").lower()
    if any(k in ql for k in ["규제", "허가", "고시", "공고", "mfds", "법령", "식품의약품안전처"]): 
        return "regulation"
    if any(k in ql for k in ["시장", "규모", "점유율", "통계", "kosis", "index.go.kr", "khidi"]): 
        return "stats"
    if any(k in ql for k in ["뉴스", "보도", "기사", "단신", "속보", "news", "press"]): 
        return "news"
    return "generic"


def _rerank_with_intent_and_diversity(items: List[Dict[str, Any]], *, intent: str, kr_boost: bool, domain_penalty: float) -> List[Dict[str, Any]]:
    """
    - 동일 host 반복에 패널티(coverage 확대)
    - 의도(intent)에 맞는 도메인에 가산점
    - 한국 맥락(kr_boost) 시 .go.kr/.kr 및 국내 매체에 소폭 가산
    """
    def _host(u: str) -> str:
        try:
            from urllib.parse import urlparse
            h = (urlparse(u).netloc or "").lower()
            # 모바일/AMP 간단 정규화(심화 버전은 utils 측에 있음)
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

        # 1) 도메인 다양성 패널티
        repeat = host_seen.get(h, 0)
        base -= repeat * float(domain_penalty or 0.0)

        # 2) 의도 기반 가산점
        if intent == "stats" and any(d in h for d in ("kosis.kr", "index.go.kr", "khidi.or.kr", "hira.or.kr")):
            base += 0.35
        if intent == "news" and any(d in h for d in ("dailypharm.com", "medipana.com", "newsmp.com", "healtho.co.kr")):
            base += 0.25
        if intent == "regulation" and ("mfds.go.kr" in h or h.endswith(".go.kr")):
            base += 0.25

        # 3) 한국 맥락 부스트
        if kr_boost and (h.endswith(".go.kr") or h.endswith(".kr") or h in ("dailypharm.com","medipana.com","newsmp.com")):
            base += 0.15

        # 4) PDF 과점 완화(뉴스/시장질의에 pdf가 과도하게 상위면 살짝 깎기)
        if intent in ("news","stats"):
            url_l = (u or "").lower()
            if url_l.endswith(".pdf") or "/upload/" in url_l:
                base -= 0.10  # 필요 시 조정

        scored.append((base, it))
        host_seen[h] = repeat + 1

    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored]


# ── Local utils ──────────────────────────────────────────────────────────────
from .utils import (
    # HTTP
    http_get,

    # 로그/문자열
    _ell, _LOG_TOPK,

    # 쿼리 전처리
    _append_default_negatives, _cap_minus_tokens,

    # 결과 처리
    _apply_gatekeep_to_results, _normalize_results, _pick_top,
    _enrich_raw_content, _save_results, _dedupe_keep_order_dicts,
    normalize_or_block_intermediate_news,

    # 기본값 폴백(ENV/CFG 우선 사용하되 없을 때만)
    _MIN_RESULTS_OK as __MIN_RESULTS_OK_FALLBACK,
    _SEARCH_TOPN as __SEARCH_TOPN_FALLBACK,

    # 네이버 보조
    _simplify_for_naver, _should_skip_naver
)


# ── Local helper: host for logs (utils._host_of 순환/정의순서 이슈 회피) ──
from urllib.parse import urlparse
from .utils import _normalize_url

def _canon_url(u: str) -> str:
    """외부 백엔드가 돌려준 URL을 우리 시스템 표준 규칙으로 즉시 정규화."""
    try:
        return _normalize_url(u or "")
    except Exception:
        return u or ""

def _host_for_log(u: str) -> str:
    try:
        pu = urlparse(_normalize_url(u))
        host = (pu.netloc or "").strip().lower()
        return host.split("/", 1)[0]
    except Exception:
        try:
            pu2 = urlparse(u)
            host = (pu2.netloc or "").strip().lower()
            return host.split("/", 1)[0]
        except Exception:
            return ""

import re as _re  # 네이버 간소화·정규화용

# --- 원문 보강 메타 헬퍼 ------------------------------------------------------
from datetime import timezone

# [PATCH A1] ── Korean query detector (naver 우선 라우팅 용)
def _looks_korean(q: str) -> bool:
    if not q:
        return False
    # 한글 범위 또는 .kr, ko-kr 등의 힌트
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

def _pretag_content_type(items: List[Dict[str, Any]]) -> None:
    """URL 휴리스틱으로 content_type 힌트를 미리 부여."""
    for it in items or []:
        if it.get("content_type"):
            continue
        u = it.get("url") or it.get("source") or ""
        if _looks_like_pdf_url(u):
            it["content_type"] = "application/pdf"

def _annotate_fetch_meta(items: List[Dict[str, Any]]) -> None:
    """원문(raw_content) 보강 이후 메타(바이트 길이/타입/시각) 부착."""
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for it in items or []:
        raw = it.get("raw_content")
        # raw_content가 존재할 때만 메타 부여
        if isinstance(raw, str) and raw:
            # bytes 길이(UTF-8 기준)
            try:
                it["raw_bytes"] = len(raw.encode("utf-8"))
            except Exception:
                it["raw_bytes"] = len(raw)

            # PDF 서명으로 타입 보정
            if (it.get("content_type") or "").strip() == "":
                if raw.lstrip().startswith("%PDF-"):
                    it["content_type"] = "application/pdf"

            # 원문 보강 시각
            it["fetched_at"] = now_iso

        # 원문이 아직 없어도 URL 기반 힌트만 붙여둠
        if not it.get("content_type"):
            u = it.get("url") or it.get("source") or ""
            if _looks_like_pdf_url(u):
                it["content_type"] = "application/pdf"

# ---- 선택적 파서(존재 시 사용, 미설치라면 안전 폴백) ----
# 모듈은 Optional로, 함수는 Optional[Callable[..., str]]로 표기하여
# "Module"/"Callable[...] 에 None 대입" 경고 제거
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
        # mypy가 stubs 없는 외부 모듈을 싫어하므로, 임포트 실패 시 조용히 스킵
        try:
            from tavily import TavilyClient  # type: ignore[import-untyped]
        except Exception:  # pragma: no cover
            logger.debug("tavily module not available; skipping tavily backend.")
            return []
        # 임포트 성공 시에만 클라이언트 생성
        client = TavilyClient(api_key=api_key)

        # [PATCH B1] ── 경량화: basic / raw_content 비활성 / 결과 상한
        max_results = max(1, min(int(num or 10), 5))
        resp = client.search(
            query=query,
            search_depth="basic",          # advanced → basic (지연 절감)
            include_raw_content=False,     # 원문 동시 수집 OFF (지연 절감)
            max_results=max_results,       # 과다 수집 방지
            timeout=timeout,               # 남은 버짓 기반 타임아웃
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
                "raw_content": "",  # include_raw_content=False
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

        # 👇 Google 전용 상한(ENV/CFG로 조절 가능, 기본 DEFAULT_TIMEOUT_SECONDS)
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
        from serpapi import GoogleSearch  # type: ignore[import-untyped]  # 지연 임포트
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
    url = "https://openapi.naver.com/v1/search/news.json"  # 정책상 뉴스 우선
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
# 2xx 이외 응답 사전 필터링: 재시도 없이 즉시 스킵
#  - dailypharm 404 등의 케이스에서 원문 보강 단계로 넘어가기 전에 제거
#  - HEAD 우선 시도, 405/403 등 HEAD 불가 시 GET(stream)으로 1회만 확인
#  - 네트워크 예외(타임아웃/SSL 등)는 "판단 불가"로 간주하여 유지(보수적)
def _probe_http_status(u: str, timeout: float = 6.0) -> Optional[int]:
    if not u:
        return None
    try:
        s = get_requests_session()
        verify = getattr(s, "verify", True)
        # HEAD 우선
        try:
            r = requests.head(u, allow_redirects=True, timeout=timeout, verify=verify)
            return int(r.status_code)
        except requests.exceptions.RequestException:
            # 일부 서버는 HEAD 미지원 → GET(stream)으로 최소 확인
            try:
                r2 = requests.get(u, allow_redirects=True, timeout=timeout, verify=verify, stream=True)
                # 즉시 연결만 확인하고 본문은 소비하지 않음
                return int(r2.status_code)
            except requests.exceptions.RequestException:
                return None
    except Exception:
        return None

def _filter_non_2xx(items: List[Dict[str, Any]], *, timeout: float = 6.0, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    결과 목록에서 2xx 응답이 아닌 URL을 선제적으로 제거합니다.
    - limit가 지정되면 상위 limit개 항목만 프로빙(과도한 네트워크 부하 방지)
    """
    if not items:
        return items
    out: List[Dict[str, Any]] = []
    n = len(items) if limit is None else max(0, min(len(items), int(limit)))
    # 상위 n개만 프로빙, 나머지는 일단 보존(보수적)
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
    # (untitled) 제거
    s = _re.sub(r"^\(\s*untitled\s*\)\s*", "", s, flags=_re.I)

    # 연도 스팬 2000..2024 → (2000 OR 2001 …)
    year_span_pat = r"\b((?:19|20)\d{2})\.\.((?:19|20)\d{2})\b"
    def _expand_years(m):
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y2 < y1: y1, y2 = y2, y1
        return "(" + " OR ".join(str(y) for y in range(y1, y2 + 1)) + ")"
    s = _re.sub(year_span_pat, _expand_years, s)

    # 공백 정규화
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s


def _normalize_query(q: str) -> str:
    """스마트 따옴표 정리 + site: 파이프를 OR로 묶기 (중복 접두어/괄호 보존)"""
    s = (q or "").strip()
    if not s:
        return s
    # 따옴표/이스케이프 정규화
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = s.replace('\\"', '"').replace("\\'", "'")

    # site:a|b|site:c → (site:a OR site:b OR site:c), site:(a OR b)는 보존
    def _site_or_repl(m: re.Match[str]) -> str:
        tail = m.group(1)
        # 이미 괄호로 묶인 경우 그대로 보존
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

    s = re.sub(r"site:([^\s)]+)", _site_or_repl, s, flags=re.I)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def _to_google_precision(q: str) -> str:
    """Google/Tavily용 정밀형: |→OR, site: 묶음 괄호화, 연도 OR trimmed, 네거티브 2개 제한"""
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
    """정밀형 B: 네거티브 제거 + 핵심 키워드만 / site 묶음 유지"""
    s = _re.sub(r"(^|\s)-\S+", " ", q).strip()
    s = _re.sub(r"\s*\|\s*", " OR ", s)
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s


def _to_naver_recall(q: str) -> str:
    """네이버 리콜형: 내부 간소화 + 더 짧게"""
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
        # 👇 Google 호출은 더 공격적 타임아웃 상한 적용
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
    """site:, OR/AND, 괄호가 포함되면 Google 우선 힌트"""
    s = q or ""
    return any(tok in s for tok in ("site:", " OR ", " AND ", "(", ")"))


def _resolve_backend_chain(engine_arg: Optional[str], *, num: int, googleish: bool) -> List[str]:
    eng = (engine_arg or os.getenv("WEB_SEARCH_ENGINE") or "auto").strip().lower()
    cfg_backends = (getattr(CFG, "SEARCH_BACKENDS", "") or "").strip()
    default_chain = "google_cse,naver_direct,serpapi_naver,serpapi,tavily"

    # google-ish면 auto에서도 google_cse를 맨 앞으로
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
    # 런타임 ENV 변경 반영(안전): CFG in-place 리로드 + 게이트키프 캐시 리프레시
    try:
        reload_config()
        from settings_gatekeep import refresh_gatekeep_cache as _refresh_gk
        _refresh_gk()
    except Exception:
        pass
    
    engine = (engine or os.getenv("WEB_SEARCH_ENGINE") or "auto").strip().lower()
    results: List[Dict[str, Any]] = []
    used: Optional[str] = None
    # 저장 경로는 Exception 분기에서 None일 수 있으므로 함수 초반 1회만 선언(재정의 방지)
    # (mypy: "Name 'path' already defined" 해결)
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

    # (A0) 선택적 프리플라이트 핑: DNS/프록시 이슈 조기감지(실패해도 진행)
    if _truthy_cfg("SEARCH_PREFLIGHT_PING", False):
        try:
            _ = http_get("https://www.google.com", timeout=1)
        except Exception:
            logger.warning("[web_search] preflight ping failed (non-fatal)")

    # [METRICS] 라운드 고정 + 쿼리 발행 기록 (best-effort, fire-and-forget)
    try:
        round_id = os.getenv("RUN_ROUND_ID") or datetime.now().isoformat(timespec="seconds")
        _metrics_call("set_round", lambda: set_round(round_id))
        _metrics_call("record_query_issued", record_query_issued)
    except Exception:
        pass

    # ─────────────────────────────────────────────────────────────
    # [GATEKEEP] 허용 도메인 로깅 및 런타임 주입 (즉시 반영)
    # 검색 체인 실행 전에 한 번만 수행하면 downstream에서 동일 목록을 사용합니다.
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

    # (1) backend 지시어
    forced_backend = None
    m = _re.match(r"backend\s*:\s*([a-zA-Z0-9_]+)\s*;\s*(.*)", raw_query)
    if m:
        forced_backend = _normalize_backend_alias(m.group(1))
        raw_query = m.group(2).strip()
        logger.info("[backend.forced] %s (via query directive)", forced_backend)

    # (2) 정규화
    base_query = _sanitize_query(raw_query)
    base_query = _normalize_query(base_query)
    if base_query != raw_query:
        logger.debug("[web_search][sanitized] %s  ←  %s", base_query, raw_query)

    # (3) 네거티브 기본값 부착(비-네이버용) — 현재는 변수만 만들어 두고 필요 시 사용
    _ = _append_default_negatives(base_query)

    # 정책/상한/예산
    _policy = (getattr(CFG, "SEARCH_POLICY", "best_of_chain") or "best_of_chain").strip()
    _min_ok = int(getattr(CFG, "SEARCH_MIN_OK", __MIN_RESULTS_OK_FALLBACK) or __MIN_RESULTS_OK_FALLBACK)
    _topn   = int(getattr(CFG, "SEARCH_TOPN", __SEARCH_TOPN_FALLBACK) or __SEARCH_TOPN_FALLBACK)
    # [ALLOWLIST BOOST] 게이트키핑이 켜져 있으면 다양성 확보를 위해 topn 상향
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
        # 우선순위: CFG.SEARCH_TIMEOUT → ENV BACKEND_TIMEOUT_SEC → 모듈 상수
        _cfg_search_timeout = getattr(CFG, "SEARCH_TIMEOUT", None)
        if _cfg_search_timeout is not None:
            _backend_timeout = int(_cfg_search_timeout)
        else:
            _backend_timeout = int(os.getenv("BACKEND_TIMEOUT_SEC", str(DEFAULT_TIMEOUT_SECONDS)))
    except Exception:
        _backend_timeout = DEFAULT_TIMEOUT_SECONDS
    # 하한(너무 짧은 값 방지)
    if _backend_timeout < 3:
        _backend_timeout = 3
    # 일괄 안전 상한(응답성 향상): DEFAULT_TIMEOUT_SECONDS
    if _backend_timeout > DEFAULT_TIMEOUT_SECONDS:
        logger.debug("[web_search] cap backend timeout: %ss → %ss",
                     _backend_timeout, DEFAULT_TIMEOUT_SECONDS)
        _backend_timeout = DEFAULT_TIMEOUT_SECONDS
    if _backend_timeout > _time_budget:
        _backend_timeout = max(3, int(_time_budget) - 1)

    t_start = time.monotonic()

    # 체인 구성 (google-ish 힌트 반영)
    try:
        logger.debug("[web_search][diag] before chain resolve")
        googleish = _is_googleish(base_query)
        chain = _resolve_backend_chain(engine, num=num, googleish=googleish)

        # [PATCH A2] ── 한국어/국내 도메인 신호가 있으면 naver_direct를 맨 앞으로 재정렬
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
    
    # [PATCH A3] ── 한국어 쿼리일 때 naver 전용 최소 예산(초) 예약
    _kr_context = _looks_korean(base_query)
    _naver_in_chain = any(b in ("naver_direct", "serpapi_naver") for b in chain)
    _naver_called = False
    _naver_reserved = 4.0 if (_kr_context and _naver_in_chain) else 0.0  # 필요 시 3~6초로 조정
    logger.debug("[web_search][A3] kr=%s | naver_in_chain=%s | reserved=%.2fs",
             _kr_context, _naver_in_chain, _naver_reserved)

    # (A) 백엔드 실행 ----------------------------------------------------------
    tried = []
    # [PATCH E1] 허용 도메인 통과 결과 누적 카운터(조기 종료용)
    allowlist_hits = 0
    early_stop_reason: Optional[str] = None
    # [PATCH C1] ── 얼리 스톱을 위한 누적 카운트 (best_of_chain에서만 사용)
    _accum_count = 0
    # [NEW] allowlist hit이어도 최소 N개 백엔드는 실행 보장
    _min_backends = max(2, int(os.getenv("SEARCH_MIN_BACKENDS", "2")))
    _backends_with_results: set[str] = set()
    for bk in chain:
        # [PATCH A4] ── naver를 아직 안 돌렸고, 예약 예산을 남겨둬야 하면 타 백엔드 대기
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
                # [PATCH D1] ── tavily는 1변형만 (지연 절감)
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
                # 각 호출 직전에 남은 예산/타임아웃을 다시 보수적으로 적용
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

        # [PATCH E2] 허용 도메인 통과분 누적 및 조기 종료 판단
        if best_res:
            try:
                _allowed_cnt = 0
                for _it in best_res:
                    _u = _it.get("url") or _it.get("source") or ""
                    if _u and url_allowed(_u):
                        _allowed_cnt += 1
                if _allowed_cnt:
                    allowlist_hits += _allowed_cnt
            except Exception:
                _allowed_cnt = 0
            # 결과를 낸 백엔드 수를 추적 (중복 방지)
            _backends_with_results.add(bk)

            # [RELAX EARLY-STOP] allowlist 충족이어도 최소 _min_backends개는 실행
            if (_policy in ("best_of_chain", "first_ok")) and (allowlist_hits >= _min_ok):
                if len(_backends_with_results) >= _min_backends:
                    early_stop_reason = f"allowlist_min_ok(backends={len(_backends_with_results)})"
                    logger.debug("[backend.pick] early stop by allowlist after %d backends (hits=%d ≥ min_ok=%d, bk=%s)",
                                 len(_backends_with_results), allowlist_hits, _min_ok, bk)
                    results = []   # '아직 최종 선택 없음' 신호 (후단 병합·게이트키프 공정)
                    used = None
                    break
                else:
                    logger.debug("[backend.pick] allowlist hit but continue (results_backends=%d < min_backends=%d)",
                                 len(_backends_with_results), _min_backends)
        # [PATCH C2] ── best_of_chain: 누적 개수 빠르게 모이면 조기 종료
        if _policy == "best_of_chain" and best_res:
            _accum_count += len(best_res)
            if _accum_count >= _topn:
                logger.debug("[backend.pick] early stop: accumulated=%d >= topn=%d", _accum_count, _topn)
                # results, used = None, None  # ❌ 타입 오류 원인
                results = []                  # ✅ 빈 리스트로 '아직 최종 선택 없음' 신호
                used = None                   # Optional[str]라서 OK
                break

        logger.debug("[web_search][backend tried] %-18s got=%2d in %.2fs",
                      f"{bk}:{used_label or 'none'}", len(best_res), dur)
        
        # [PATCH A4-followup] naver 호출 완료 플래그 및 예약 해제
        if bk in ("naver_direct", "serpapi_naver"):
            _naver_called = True
            _naver_reserved = 0.0

        # [METRICS] 백엔드 총 소요 시간 (best-effort, 말단)
        _metrics_call(f"record_backend_latency:{bk}", lambda: record_backend_latency(bk, float(dur)))

        if _policy == "first_ok" and len(best_res) >= _min_ok:
            results, used = best_res, f"{bk}:{used_label}"
            break

    # (A.5) 보정: 한국어 쿼리인데 naver를 전혀 못 돌렸다면 한 번은 강제 시도
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

    # (B) best_of_chain → 합산/정규화/디듀프/TopN
    if not results:
        if _policy == "best_of_chain":
            merged: List[Dict[str, Any]] = []
            for _, _, res in tried:
                merged.extend(res or [])
            merged = _dedupe_keep_order_dicts(_normalize_results(merged))

            # [PATCH B] ── 의도/다양성 기반 리랭크 추가
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

    # (C) 리트라이(비어있고 시간 남아 있을 때만)
    if not results and _budget_left() > 2.0:
        time.sleep(0.6)
        retried: List[Tuple[str, int, List[dict]]] = []
        # [PATCH E3] retry에서도 허용 도메인 조기 종료 재사용
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

            # retry 조기 종료 판단
            if best_res_r:
                try:
                    _allowed_cnt_r = 0
                    for _it in best_res_r:
                        _u = _it.get("url") or _it.get("source") or ""
                        if _u and url_allowed(_u):
                            _allowed_cnt_r += 1
                    if _allowed_cnt_r:
                        retry_allowlist_hits += _allowed_cnt_r
                except Exception:
                    _allowed_cnt_r = 0
                _retry_backends_with_results.add(bk)

                # [RELAX EARLY-STOP][retry] 재시도 경로도 최소 _min_backends 보장
                if (_policy in ("best_of_chain", "first_ok")) and (retry_allowlist_hits >= _min_ok):
                    if len(_retry_backends_with_results) >= _min_backends:
                        early_stop_reason = f"allowlist_min_ok(retry,backends={len(_retry_backends_with_results)})"
                        logger.debug("[web_search][retry] early stop by allowlist after %d backends: hits=%d ≥ min_ok=%d (bk=%s)",
                                     len(_retry_backends_with_results), retry_allowlist_hits, _min_ok, bk)
                        results = []  # 후단 병합 경로 진입
                        used = None
                        break
                    else:
                        logger.debug("[web_search][retry] allowlist hit but continue (results_backends=%d < min_backends=%d)",
                                     len(_retry_backends_with_results), _min_backends)

            # retry latency 기록(말단·비중요)
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
                merged = _dedupe_keep_order_dicts(_normalize_results(merged))

                # [PATCH B-retry] 리랭크 재적용
                _intent = _infer_intent_from_query(base_query)
                merged = _rerank_with_intent_and_diversity(merged, intent=_intent, kr_boost=_kr_context,
                                                           domain_penalty=0.15)

                merged = _pick_top(merged, _topn)
                results, used = merged, f"merged(retry){(':'+early_stop_reason) if early_stop_reason else ''}"
            else:
                best = max(retried, key=lambda t: t[1])
                used, _, results = f"{best[0]}(retry)", best[1], best[2]

    # (D) 최종 로그/메트릭(파일 저장/후속 단계보다 후순위로 유지)
    if results:
        logger.info("[web_search][backend] %s  | got=%d (policy=%s, min_ok=%d, topn=%d, spent=%.2fs)",
                     used, len(results), _policy, _min_ok, _topn, (time.monotonic()-t_start))
    else:
        _metrics_call("record_zero_result", record_zero_result)
        _metrics_call("zero_result_query", lambda: event("zero_result_query", query=base_query))

    # (E) 게이트키핑/원문 보강/저장  ← **핵심: 저장을 먼저!**
    # URL 휴리스틱으로 content_type 힌트 선반영
    _pretag_content_type(results)
    results = _apply_gatekeep_to_results(results)
    results = _pick_top(results, _topn)
    # [PATCH: non-2xx 즉시 스킵] — 원문 보강 전에 2xx 이외 응답은 제거(재시도 없음)
    #    - 과도한 네트워크 부하를 피하기 위해 상위 TopN만 상태 프로빙
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
    # 안전망: n.news.naver.com 중계 URL 최종 필터
    results = [it for it in results if not normalize_or_block_intermediate_news(it.get("url") or it.get("source") or "")[1]]
    # 원문 보강 이후 메타(바이트/타입/타임스탬프) 주입
    _annotate_fetch_meta(results)

    # 저장 경로는 최종적으로 문자열이어야 하지만, 예외 경로에서 None이 될 수 있으므로 Optional로 선언
    try:
        path = _save_results(results, query=raw_query, base_dir=str(research_base_dir()))
    except TypeError:
        path = _save_results(results, query=raw_query)  # 구버전 시그니처 호환
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

    # 말단: 백엔드 선택 이벤트(파일 저장 이후 best-effort)
    if results:
        _metrics_call("backend_selected",
                      lambda: event("backend_selected", backend=str(used or "none"),
                                    result_count=len(results)))

    # 간단 요약 로그
    lines = []
    for i, it in enumerate(results[:_LOG_TOPK], start=1):
        t = _ell(it.get("title") or it.get("name") or "(no title)")
        u = it.get("url") or it.get("source") or it.get("link") or ""
        lines.append(f"  {i:>2}. {t}\n      └─ {_host_for_log(u)} :: {u}")
    if lines:
        logger.info("[web_search][top%d]\n%s", min(_LOG_TOPK, len(results)), "\n".join(lines))

    logger.info("[web_search] backend=%s, results=%d, saved=%s", used, len(results), path)
    return results, path if path is not None else str(Path.cwd() / "web_search_fallback.json")
