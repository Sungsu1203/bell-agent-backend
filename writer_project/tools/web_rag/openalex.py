# tools/web_rag/openalex.py
"""§academic-4 catch 51 fix S1 — OpenAlex /works search 호출.

vertex_search.py:88-194 패턴 답습 (함수 1 + 헬퍼 + return schema 통일).
catch 57 lesson 정합: urllib + User-Agent + mailto + 2s backoff on 429.
1A (사용자 컨펌): api_key 필수 (2026-02-13~ 정책) + mailto polite pool.
catch 60-d: meta.cost_usd 보존 (free tier $1/day = 100k req/day monitor).
"""
from typing import Any, Dict, List, Optional
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from tools.web_rag._scholarly_domain import extract_domain_from_paper

logger = logging.getLogger(__name__)

_OA_ENDPOINT = "https://api.openalex.org/works"
_OA_DEFAULT_PER_PAGE = 10
_OA_TIMEOUT_S = 10.0
_OA_BACKOFF_S = 2.0


def _empty_result(error: Optional[str] = None, elapsed: float = 0.0) -> Dict[str, Any]:
    """vertex_search.py 정합 빈 dict (에러 isolation backend 측 endpoint)."""
    return {
        "mode": "openalex",
        "elapsed_sec": round(float(elapsed), 3),
        "items": 0,
        "domains": [],
        "domains_unique": [],
        "chunks": [],
        "supports": [],
        "web_search_queries": [],
        "oa_cost_usd": 0.0,
        "error": error,
    }


def openalex_search(query: str) -> Dict[str, Any]:
    """OpenAlex /works search 호출.

    Returns: vertex_search.py 정합 dict + oa_cost_usd (catch 60-d monitor).
    """
    t0 = time.monotonic()
    q = (query or "").strip()
    if not q:
        return _empty_result(error="empty query", elapsed=0.0)

    api_key = os.getenv("OPENALEX_API_KEY", "").strip()
    if not api_key:
        return _empty_result(error="OPENALEX_API_KEY 미설정",
                             elapsed=time.monotonic() - t0)
    mailto = os.getenv("OPENALEX_MAILTO", "sungsu.oh@bellcomm.co.kr")

    qs = urllib.parse.urlencode({
        "search": q,
        "per-page": _OA_DEFAULT_PER_PAGE,
        "mailto": mailto,
        "api_key": api_key,
    })
    url = f"{_OA_ENDPOINT}?{qs}"
    headers = {
        "User-Agent": f"writer_project/§academic-4 (mailto:{mailto})",
        "Accept": "application/json",
    }

    body: Optional[Dict[str, Any]] = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=_OA_TIMEOUT_S) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                logger.info("[openalex] 429 backoff %.1fs (attempt=%d)",
                            _OA_BACKOFF_S, attempt)
                time.sleep(_OA_BACKOFF_S)
                continue
            return _empty_result(error=f"HTTPError {e.code}",
                                 elapsed=time.monotonic() - t0)
        except Exception as e:
            return _empty_result(error=f"{type(e).__name__}: {e}",
                                 elapsed=time.monotonic() - t0)

    if body is None:
        return _empty_result(error="unknown failure", elapsed=time.monotonic() - t0)

    meta = body.get("meta") or {}
    cost = float(meta.get("cost_usd") or 0.0)  # catch 60-d monitor

    results: List[Dict[str, Any]] = body.get("results") or []
    chunks: List[Dict[str, Any]] = []
    supports: List[Dict[str, Any]] = []
    domains: List[str] = []

    for i, work in enumerate(results):
        d = extract_domain_from_paper(work, backend="openalex")
        if not d:
            continue
        pl = work.get("primary_location") or {}
        u = pl.get("landing_page_url") or work.get("doi") or ""
        chunks.append({
            "uri": u,
            "title": work.get("title") or "",
            "domain": d,
        })
        supports.append({
            "chunk_indices": [i],
            "text": work.get("title") or "",
            "start_index": 0,
            "end_index": 0,
        })
        domains.append(d)

    elapsed = time.monotonic() - t0
    logger.info("[openalex] ok items=%d domains_unique=%d elapsed=%.3fs cost_usd=%.6f",
                len(results), len(set(domains)), elapsed, cost)

    return {
        "mode": "openalex",
        "elapsed_sec": round(elapsed, 3),
        "items": len(results),
        "domains": domains,
        "domains_unique": sorted(set(d for d in domains if d)),
        "chunks": chunks,
        "supports": supports,
        "web_search_queries": [q],
        "oa_cost_usd": cost,
        "error": None,
    }
