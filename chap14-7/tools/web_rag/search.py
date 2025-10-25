# tools/web_rag/search.py
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

from tools.metrics import record_query_issued, record_zero_result, record_backend_latency, set_round, event

# 💡 중앙 LLM 관리 모듈에서 임베딩 함수 임포트
from core.llm import get_embedding_model

from settings_gatekeep import (
    gatekeep_enabled,
    url_allowed,
    _normalize_host,    # 로그 요약용 (없으면 제거해도 무방)
)

# 🔽 utils에서 공용 상수/헬퍼 불러오기
from .utils import (
    # 세션/HTTP
    http_get, session,

    # 로그/문자열
    _ell, _host_of, _LOG_TOPK,

    # 포트폴리오/전처리
    _append_default_negatives, _cap_minus_tokens, _truthy,

    # 결과 처리
    _apply_gatekeep_to_results, _normalize_results, _pick_top,
    _enrich_raw_content, _save_results, _dedupe_keep_order_dicts,

    # 검색 정책 상수
    _BACKEND_PICK_POLICY, _MIN_RESULTS_OK, _SEARCH_TOPN,

    # 백엔드 사용 가능 플래그
    _HAS_SERPAPI, _HAS_TAVILY,
    _simplify_for_naver, _should_skip_naver
)

from collections import defaultdict as _dd
import re as _re  # ← Naver 쿼리 간소화용

# ─────────────────────────────────────────────────────────────────────────────
# HTTPS 세션 (검증 ON)
# ─────────────────────────────────────────────────────────────────────────────
# session = requests.Session()
# session.headers.update({"User-Agent": os.getenv("USER_AGENT", "BookWriterBot/1.0")})
# session.verify = certifi.where()  # 신뢰 루트 지정

# def http_get(url, **kw):
#     kw.setdefault("timeout", (6, 20))
#     return session.get(url, **kw)

# ---- Optional: SerpAPI ----
# try:
#     from serpapi import GoogleSearch  # pip install google-search-results
#     _HAS_SERPAPI = True
# except Exception:
#     _HAS_SERPAPI = False
#     logger.debug("SerpAPI not available.")

# # ---- Optional: Tavily ----
# try:
#     from tavily import TavilyClient  # pip install tavily-python
#     _HAS_TAVILY = True
# except Exception:
#     _HAS_TAVILY = False
#     logger.debug("Tavily client not available.")

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
# Search backends
# =============================================================================
def _search_tavily(query: str) -> List[Dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not (_HAS_TAVILY and api_key):
        return []
    try:
        # ✅ 함수 내부 지연 import (플래그로 가용성 확인 후)
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, search_depth="advanced", include_raw_content=True)

        if isinstance(resp, dict):
            items = resp.get("results", []) or []
        else:
            items = []
            for r in getattr(resp, "results", []) or []:
                items.append(r.model_dump() if hasattr(r, "model_dump") else dict(r))

        parsed: List[Dict[str, Any]] = []
        for it in items:
            parsed.append({
                "title": it.get("title") or "",
                "url": it.get("url") or "",
                "content": (it.get("content") or "")[:2000],
                "raw_content": it.get("raw_content") or "",
                "source": it.get("url") or "",
            })
        return parsed
    except Exception as e:
        logger.warning("Tavily search failed: %s", e)
        return []

def _search_google_cse(query: str, *, num: int = 10, timeout: int = 20) -> List[Dict[str, Any]]:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_CSE_API_KEY")
    cse_id  = os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CSE_CX")
    if not (api_key and cse_id):
        return []
    try:
        gl = os.getenv("GOOGLE_CSE_GL") or os.getenv("SEARCH_GL") or "us"
        lr = os.getenv("GOOGLE_CSE_LR") or ""
        hl = os.getenv("SEARCH_HL", "en")
        num = max(1, min(int(num or 10), 10))

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
            link = it.get("link") or it.get("formattedUrl") or ""
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
    api_key = os.getenv("SERPAPI_API_KEY")
    if not (api_key and _HAS_SERPAPI):
        return []
    try:
        # ✅ 함수 내부 지연 import
        from serpapi import GoogleSearch
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
            link = it.get("link") or ""
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

# ───────── Query Sanitizer ─────────
def _sanitize_query(q: str) -> str:
    if not q:
        return q
    s = q.strip()
    s = _re.sub(r"^\(\s*untitled\s*\)\s*", "", s, flags=_re.I)

    year_span_pat = r"\b((?:19|20)\d{2})\.\.((?:19|20)\d{2})\b"
    def _expand_years(m):
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y2 < y1:
            y1, y2 = y2, y1
        return "(" + " OR ".join(str(y) for y in range(y1, y2 + 1)) + ")"
    s = _re.sub(year_span_pat, _expand_years, s)

    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

# ───────── Precision/Recall query shaping ─────────

def _to_google_precision(q: str) -> str:
    """Google CSE/Tavily용 정밀형: |→OR, site: 묶음 괄호화, 연도 OR trimmed, 네거티브 2개 제한"""
    s = q.strip()
    # 1) '|' → ' OR '
    s = _re.sub(r"\s*\|\s*", " OR ", s)
    # 2) site: 묶음 괄호화  ex) site:a OR site:b → (site:a OR site:b)
    def _paren_site(m):
        block = m.group(0)
        # 이미 괄호면 패스
        if block.lstrip().startswith("(") and block.rstrip().endswith(")"):
            return block
        return "(" + block.strip() + ")"
    s = _re.sub(r"(?:\s*site:\S+\s*(?:OR\s*site:\S+\s*)+)", _paren_site, s, flags=_re.I)

    # 3) (2022 OR 2023 OR 2024 ...) 과다 시 최신 1개만 유지
    def _trim_year_or(group: str, keep: int = 1) -> str:
        years = _re.findall(r"\b(19|20)\d{2}\b", group)
        if not years:
            return group
        ys = [int(y) if len(y)==4 else int('20'+y) for y in _re.findall(r"\b((?:19|20)\d{2})\b", group)]
        ys = sorted(set(ys))
        if len(ys) <= keep: 
            return group
        picked = ys[-keep:]
        return "(" + " OR ".join(str(y) for y in picked) + ")"
    s = _re.sub(r"\((?:\s*(?:19|20)\d{2}\s*(?:OR\s*)?)+\)", lambda m: _trim_year_or(m.group(0), keep=1), s)

    # 4) 네거티브 토큰 상한 2개
    s = _cap_minus_tokens(s, cap=2)
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

def _to_google_precision_alt(q: str) -> str:
    """정밀형 B: 네거티브 제거 + 핵심 키워드만 / site 묶음 유지"""
    s = _re.sub(r"(^|\s)-\S+", " ", q).strip()  # 모든 네거티브 제거
    s = _re.sub(r"\s*\|\s*", " OR ", s)
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

def _to_naver_recall(q: str) -> str:
    """네이버 리콜형: 내부 간소화 but 더 짧게"""
    s = _simplify_for_naver(q)
    # 토큰수 5 초과 시 앞 5개로 cut
    toks = s.split()
    if len(toks) > 5:
        s = " ".join(toks[:5])
    return s

# ====== 네이버(Direct) / SerpAPI(Naver) ======
def _search_naver_direct(query: str, *, num: int = 10, timeout: int = 20) -> List[Dict[str, Any]]:
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not (client_id and client_secret):
        logger.warning("Naver direct search skipped: NAVER_CLIENT_ID or SECRET not set.")
        return []
    q_naver = _simplify_for_naver(query)
    if not q_naver or len(q_naver) < 2:
        logger.info("[Naver(Direct)] skipped (empty after simplify)")
        return []
    from urllib.parse import quote
    encoded_query = quote(q_naver)
    # 웹문서 대신 뉴스엔진 사용 중(정책상 조정 가능)
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
            link = it.get("link") or it.get("url") or ""
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
        logger.warning("Naver(Direct) HTTP Error %s: %s (query=%s)", getattr(e.response, "status_code", "?"), getattr(e.response, "text", ""), _ell(q_naver))
        return []
    except Exception as e:
        logger.warning("Naver(Direct) search failed: %s", e)
        return []

def _search_serpapi_naver(query: str) -> list[dict]:
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
    try_others = _truthy("SERPAPI_NAVER_TRY_OTHERS", "0")
    url = "https://serpapi.com/search.json"
    logger.debug("[SerpAPI(Naver)][query] %s", _ell(q_naver))

    def _collect(data, sink: list):
        def _push(lst):
            for r in lst or []:
                link = r.get("link") or r.get("url") or ""
                if not link:
                    continue
                title = r.get("title") or ""
                snippet = r.get("snippet") or r.get("snippet_highlighted_words") or ""
                if isinstance(snippet, list):
                    snippet = " ".join(snippet)
                sink.append({"title": title, "url": link, "source": link, "snippet": snippet or ""})
        _push(data.get("organic_results"))
        if not sink: _push(data.get("web_results"))
        if not sink: _push(data.get("news_results"))
        if not sink: _push(data.get("blog_results"))

    def _req(params: dict) -> tuple[list, dict]:
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code >= 400:
                logger.warning("SerpAPI(Naver) HTTP %s (where=%s)", resp.status_code, params.get("where"))
                return [], {}
            data = resp.json() if resp.text else {}
        except Exception as e:
            logger.warning("SerpAPI(Naver) request failed: %s", e.__class__.__name__)
            return [], {}
        items: list[dict] = []
        if data.get("error"):
            logger.warning("SerpAPI(Naver) error: %s (where=%s)", data.get("error"), params.get("where"))
        sm = data.get("search_metadata") or {}
        if sm:
            logger.debug("SerpAPI(Naver) metadata: id=%s status=%s where=%s",
                         sm.get("id"), sm.get("status"), params.get("where"))
        _collect(data, items)
        return items, data

    params = {"engine":"naver","query":q_naver,"api_key":api_key,"hl":hl,"gl":gl,"where":where,"num":num}
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

# ====== Backend router & helpers =============================================
def _backend_call(backend_key: str, query: str, *, num: int = 10) -> List[Dict[str, Any]]:
    key = (backend_key or "").strip().lower()
    if key in ("google", "google_cse"):
        return _search_google_cse(query, num=num)
    if key in ("serpapi", "serpapi_google"):
        return _search_serpapi(query, num=num)
    if key in ("naver", "serpapi_naver"):
        return _search_serpapi_naver(query)
    elif key == "naver_direct":
        return _search_naver_direct(query, num=num)
    if key == "tavily":
        return _search_tavily(query)
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

def _resolve_backend_chain(engine_arg: Optional[str], *, num: int) -> list[str]:
    eng = (engine_arg or os.getenv("WEB_SEARCH_ENGINE") or "auto").strip().lower()
    if eng and eng != "auto":
        fallback = (os.getenv("SEARCH_BACKENDS") or "google_cse,naver_direct,serpapi_naver,serpapi,tavily")
        chain = [_normalize_backend_alias(eng)]
        for b in fallback.split(","):
            a = _normalize_backend_alias(b.strip())
            if a and a not in chain:
                chain.append(a)
        return chain
    env_list = (os.getenv("SEARCH_BACKENDS") or "").strip()
    if env_list:
        return [_normalize_backend_alias(s) for s in env_list.split(",") if s.strip()]
    # 기본 체인(네이버 직접 포함)
    return ["google_cse", "naver_direct", "serpapi_naver", "serpapi", "tavily"]

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
    """
    engine = (engine or os.getenv("WEB_SEARCH_ENGINE") or "auto").strip().lower()

    results: List[Dict[str, Any]] = []
    used: Optional[str] = None

    raw_query = query
    logger.info("[web_search][query] %s", _ell(raw_query))
    # [METRICS] 라운드 고정(ENV가 없으면 현재 시각으로) + 쿼리 1건 발행 기록
    try:
        round_id = os.getenv("RUN_ROUND_ID") or datetime.now().isoformat(timespec="seconds")
        logger.debug("[metrics] round_id=%s", round_id)  # ← 추가: 트레이싱용
        set_round(round_id)
        record_query_issued()
    except Exception:
        pass

    # (1) backend 지시어
    forced_backend = None
    m = _re.match(r"backend\s*:\s*([a-zA-Z0-9_]+)\s*;\s*(.*)", raw_query)
    if m:
        forced_backend = _normalize_backend_alias(m.group(1))
        raw_query = m.group(2).strip()
        logger.info("[backend.forced] %s (via query directive)", forced_backend)

    # (2) 표준 정규화
    base_query = _sanitize_query(raw_query)
    if base_query != raw_query:
        logger.debug("[web_search][sanitized] %s", base_query)

    # (3) 네거티브 부착(비-네이버용)
    neg_query = _append_default_negatives(base_query)

    logger.debug(
        "[web_search][env] backends=%s | policy=%s min_ok=%d topn=%d | keys: G=%s CSE=%s S=%s T=%s",
        os.getenv("SEARCH_BACKENDS"),
        _BACKEND_PICK_POLICY, _MIN_RESULTS_OK, _SEARCH_TOPN,
        "Y" if (os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_CSE_API_KEY")) else "N",
        "Y" if (os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CSE_CX")) else "N",
        "Y" if os.getenv("SERPAPI_API_KEY") else "N",
        "Y" if os.getenv("TAVILY_API_KEY") else "N",
    )

    # 체인 구성
    chain = _resolve_backend_chain(engine, num=num)
    if forced_backend:
        chain = [forced_backend] + [b for b in chain if b != forced_backend]

    try:
        _chain_preview = " → ".join(chain)
    except Exception:
        _chain_preview = str(chain)
    logger.debug("[web_search][chain] %s (policy=%s, min_ok=%d)", _chain_preview, _BACKEND_PICK_POLICY, _MIN_RESULTS_OK)

    # (A) 백엔드 실행 — backend별 query portfolio
    tried: list[tuple[str, int, list[dict]]] = []  # (backend[:variant], raw_count, results)
    for bk in chain:
        start = time.time()

        # 1) 백엔드별 쿼리 변형 포트폴리오 구성
        variants: list[tuple[str, str]] = []  # (label, query)
        if bk in ("google", "google_cse", "tavily", "serpapi"):   # 정밀형
            base_q = base_query  # sanitize 이후 원문
            q_prec_a = _to_google_precision(base_q)
            q_prec_b = _to_google_precision_alt(base_q)
            # 기본 네거티브 부착한 정밀형 A' (회귀 방지)
            q_prec_a_neg = _append_default_negatives(q_prec_a)
            variants = [("precAneg", q_prec_a_neg), ("precA", q_prec_a), ("precB", q_prec_b)]
        elif bk in ("naver", "serpapi_naver", "naver_direct"):    # 리콜형
            q_recall = _to_naver_recall(base_query)
            variants = [("recall", q_recall)]
        else:
            variants = [("default", base_query)]

        # 2) 변형들을 순차 시도
        best_res: list[dict] = []
        used_label: Optional[str] = None
        for label, q_use in variants:
            try:
                q_final = q_use  # 정밀형 함수에서 네거티브/OR 정리됨
                _res = _backend_call(bk, q_final, num=num) or []
            except Exception as e:
                logger.warning("web_search backend '%s' failed on %s: %s", bk, label, e)
                _res = []

            if _res:
                best_res = _res
                used_label = label
                if _BACKEND_PICK_POLICY == "first_ok" and len(_res) >= _MIN_RESULTS_OK:
                    break  # 이 백엔드는 성공했으니 다음 백엔드로

        dur = time.time() - start
        tried.append((f"{bk}:{used_label or 'none'}", len(best_res), best_res))
        logger.debug("[web_search][backend tried] %-18s got=%2d in %.2fs",
                    f"{bk}:{used_label or 'none'}", len(best_res), dur)
        # [METRICS] 백엔드 총 소요 시간 기록 (이 백엔드에서 시도한 variants 포함)
        try:
            record_backend_latency(bk, float(dur))
        except Exception:
            pass

        if _BACKEND_PICK_POLICY == "first_ok" and len(best_res) >= _MIN_RESULTS_OK:
            results, used = best_res, f"{bk}:{used_label}"
            break

    # (B) 선택: best_of_chain → 합산/정규화/디듀프/TopN
    if not results:
        if _BACKEND_PICK_POLICY == "best_of_chain":
            merged: List[Dict[str, Any]] = []
            for _, _, res in tried:
                merged.extend(res or [])
            # URL 정규화 기반 디듀프 + TopN
            merged = _dedupe_keep_order_dicts(_normalize_results(merged))
            merged = _pick_top(merged, _SEARCH_TOPN)
            results = merged
            used = "merged"
            logger.debug("[backend.pick] best_of_chain → merged(%d)", len(results))
        elif tried:
            best = max(tried, key=lambda t: t[1])
            used, best_count, best_res = best[0], best[1], best[2]
            results = best_res
            logger.debug("[backend.pick] first_ok/best_of_chain fallback → %s (count=%d)", used, best_count)

    # (C) 리트라이 블록(비어있을 때만)
    if not results:
        time.sleep(0.8)
        retried: list[tuple[str, int, list[dict]]] = []
        for bk in chain:
        # [METRICS] 재시도 루프용 타이머 시작
            _retry_t0 = time.time()
            # C에서도 variants 구성 (A와 동일)
            if bk in ("google", "google_cse", "tavily", "serpapi"):
                q_prec_a = _to_google_precision(base_query)
                q_prec_b = _to_google_precision_alt(base_query)
                q_prec_a_neg = _append_default_negatives(q_prec_a)
                vset = [("precAneg", q_prec_a_neg), ("precA", q_prec_a), ("precB", q_prec_b)]
            elif bk in ("naver", "serpapi_naver", "naver_direct"):
                vset = [("recall", _to_naver_recall(base_query))]
            else:
                vset = [("default", base_query)]

            best_res = []
            used_label = None
            for label, q_use in vset:
                try:
                    _res = _backend_call(bk, q_use, num=num) or []
                except Exception:
                    _res = []
                if _res:
                    best_res = _res; used_label = label
                    if _BACKEND_PICK_POLICY == "first_ok" and len(_res) >= _MIN_RESULTS_OK:
                        break
            retried.append((f"{bk}:{used_label or 'none'}", len(best_res), best_res))
            # [METRICS] 재시도 백엔드 총 소요 시간
            try:
                _retry_dur = time.time() - _retry_t0
                record_backend_latency(bk, float(_retry_dur))
            except Exception:
                pass
            if _BACKEND_PICK_POLICY == "first_ok" and len(best_res) >= _MIN_RESULTS_OK:
                results, used = best_res, f"{bk}:{used_label}(retry)"
                break
        if not results and retried:
            if _BACKEND_PICK_POLICY == "best_of_chain":
                merged = []
                for _, _, res in retried:
                    merged.extend(res or [])
                merged = _dedupe_keep_order_dicts(_normalize_results(merged))
                merged = _pick_top(merged, _SEARCH_TOPN)
                results, used = merged, "merged(retry)"
            else:
                best = max(retried, key=lambda t: t[1])
                used, _, results = f"{best[0]}(retry)", best[1], best[2]

    # (D) 최종 로그
    if results:
        logger.info("[web_search][backend] %s  | got=%d (policy=%s, min_ok=%d, topn=%d)",
                    used, len(results), _BACKEND_PICK_POLICY, _MIN_RESULTS_OK, _SEARCH_TOPN)
        lines = []
        for i, it in enumerate(results[:_LOG_TOPK], start=1):
            t = _ell(it.get("title") or it.get("name") or "(no title)")
            u = it.get("url") or it.get("source") or it.get("link") or ""
            lines.append(f"  {i:>2}. {t}\n      └─ {_host_of(u)} :: {u}")
        logger.info("[web_search][top%d]\n%s", min(_LOG_TOPK, len(results)), "\n".join(lines))

        # [METRICS] 최종 선택된 백엔드/결과수 이벤트 기록(대시보드용)
        try:
            event("backend_selected", backend=str(used or "none"), result_count=len(results))
        except Exception:
            pass

    # [METRICS] 최종 병합 결과가 0건이면 지표 기록(게이트키핑 전에 판단)
    if not results:
        try:
            record_zero_result()
            event("zero_result_query", query=base_query)
        except Exception:
            pass

    # (E) 게이트키핑/원문 보강/저장 (TopN 유지)
    results = _apply_gatekeep_to_results(results)
    results = _pick_top(results, _SEARCH_TOPN)
    _enrich_raw_content(results)
    path = _save_results(results, query=raw_query)

    logger.info("[web_search] backend=%s, results=%d, saved=%s", used, len(results), path)
    return results, path