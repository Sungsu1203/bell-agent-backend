# tools/web_rag/semantic_scholar.py
"""§academic-4 catch 51 fix S1 — Semantic Scholar Graph API v1 paper/search 호출.

vertex_search.py:88-194 패턴 답습 (함수 1 + 헬퍼 2 + return schema 통일).
catch 57 lesson 정합: urllib + User-Agent + mailto + Retry-After respect backoff on 429.

Sub-decision 1A' (1A 후속, anonymous pool reality check 후):
  - default: SEMANTIC_SCHOLAR_SKIP=1 → 즉시 빈 결과 (anonymous 429 isolation)
  - key 발급 후: SEMANTIC_SCHOLAR_API_KEY 환경변수 주입 + SKIP=0 변경 시 자동 활성
    (x-api-key 헤더 사전 박제, catch 61 후보 entry)

commit 1 patch (anonymous pool throttle 잔존 대응):
  A-1: URL `mailto` 파라미터 추가 (OpenAlex polite pool 패턴 답습)
  A-2: 429 Retry-After 헤더 respect (정수면 그 값, cap 60s)
  A-3: max_retries=2 (총 3 attempts), default backoff=30s
  B-1: SEMANTIC_SCHOLAR_SKIP=1 toggle (anonymous fail isolation)
  B-2: SEMANTIC_SCHOLAR_API_KEY → x-api-key 헤더 (key 발급 후 자동 활성)
"""
from typing import Any, Dict, List, Optional
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import urllib.request
import ssl
import certifi

from tools.web_rag._scholarly_domain import extract_domain_from_paper

# 맥 urllib 루트 인증서 미연결 회피 — certifi 번들 명시 (catch 신규: macOS SSL)
_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

logger = logging.getLogger(__name__)

_SS_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"
_SS_FIELDS = "title,venue,year,journal,externalIds,openAccessPdf,authors,abstract"
_SS_DEFAULT_LIMIT = 10
_SS_TIMEOUT_S = 10.0
_SS_BACKOFF_S = 30.0  # §academic-4 commit 1 patch A-3: anonymous pool 회복 window 확보
_SS_MAX_RETRIES = 2   # §academic-4 commit 1 patch A-3: 총 3 attempts (0/1/2)


def _empty_result(error: Optional[str] = None, elapsed: float = 0.0) -> Dict[str, Any]:
    """vertex_search.py 정합 빈 dict (에러 isolation backend 측 endpoint)."""
    return {
        "mode": "semantic_scholar",
        "elapsed_sec": round(float(elapsed), 3),
        "items": 0,
        "domains": [],
        "domains_unique": [],
        "chunks": [],
        "supports": [],
        "web_search_queries": [],
        "error": error,
    }


def _paper_to_url(paper: Dict[str, Any]) -> str:
    """SS paper dict → 대표 URL (openAccessPdf > url > doi.org)."""
    oa = (paper.get("openAccessPdf") or {}).get("url") or ""
    if oa:
        return oa
    url = paper.get("url") or ""
    if url:
        return url
    doi = ((paper.get("externalIds") or {}).get("DOI") or "")
    if doi:
        return f"https://doi.org/{doi}"
    return ""


def semantic_scholar_search(query: str, verbose: bool = False) -> Dict[str, Any]:
    """Semantic Scholar Graph API v1 paper/search 호출.

    Args:
        query: 검색 쿼리.
        verbose: True 시 debug print (URL/headers/status/body keys/raw 1st entry).
                 commit 1 debug 한정 (production 호출 시 False default).

    Returns: vertex_search.py 정합 dict
        {mode, elapsed_sec, items, domains, domains_unique, chunks, supports,
         web_search_queries, error}
    """
    t0 = time.monotonic()
    q = (query or "").strip()
    if not q:
        return _empty_result(error="empty query", elapsed=0.0)

    # ── commit 1 patch B-1: skip toggle (default 1, anonymous 429 isolation) ──
    # SS API key 발급 후 사용자 측 .env.semanticscholar 의 SEMANTIC_SCHOLAR_SKIP=0 변경
    # + SEMANTIC_SCHOLAR_API_KEY=<발급값> 주입 시 자동 활성 (Sub-decision 1A' 정합)
    if os.getenv("SEMANTIC_SCHOLAR_SKIP", "0") == "1":
        if verbose:
            print("[SS debug] SEMANTIC_SCHOLAR_SKIP=1 → skip (anonymous 429 isolation)")
        return _empty_result(error="SS_SKIP", elapsed=time.monotonic() - t0)

    mailto = os.getenv("SEMANTIC_SCHOLAR_MAILTO", "sungsu.oh@bellcomm.co.kr")
    # ── catch 51 commit 1 debug fix ──────────────────────────────────────────
    # (a) User-Agent ASCII-only (이전 `§` U+00A7 → anti-bot heuristic 거부 의심,
    #     A2-c pilot UA 'rag-writer-audit/0.1 (...)' 정합 답습)
    # (b) urlencode safe="," 로 fields 콤마 escape 회피
    #     (A2-c pilot raw URL 의 콤마 그대로 정합)
    # (c) commit 1 patch A-1: URL mailto 파라미터 추가 (OpenAlex polite pool 패턴 답습,
    #     SS 공식 docs 미명시이나 동일 효과 가능성 시도)
    params: Dict[str, Any] = {
        "query": q,
        "limit": _SS_DEFAULT_LIMIT,
        "fields": _SS_FIELDS,
    }
    if mailto:
        params["mailto"] = mailto
    qs = urllib.parse.urlencode(params, safe=",")
    url = f"{_SS_ENDPOINT}?{qs}"
    headers = {
        "User-Agent": f"writer_project-academic-4 (mailto:{mailto})",
        "Accept": "application/json",
    }
    # ── commit 1 patch B-2: SEMANTIC_SCHOLAR_API_KEY 헤더 사전 박제 ──
    # 사용자 측 key 발급 후 .env.semanticscholar 의 SEMANTIC_SCHOLAR_API_KEY 주입 시 자동 활성
    # (env 미설정 시 anonymous fallback, env 있으면 authenticated pool — catch 61 정합)
    ss_api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if ss_api_key:
        headers["x-api-key"] = ss_api_key
    if verbose:
        # x-api-key 값은 hidden, 존재 여부만 보고 (STOP-C-7 정합)
        safe_headers = {k: (v if k != "x-api-key" else "<set>") for k, v in headers.items()}
        print(f"[SS debug] url: {url}")
        print(f"[SS debug] headers: {safe_headers}")
        print(f"[SS debug] x-api-key set: {bool(ss_api_key)}")

    body: Optional[Dict[str, Any]] = None
    last_status: Optional[int] = None
    last_size: int = 0
    # ── commit 1 patch A-2/A-3: Retry-After respect + max_retries=2 (총 3 attempts) ──
    for attempt in range(_SS_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=_SS_TIMEOUT_S, context=_SSL_CTX) as resp:
                raw = resp.read()
                last_status = resp.status
                last_size = len(raw)
                body = json.loads(raw.decode("utf-8"))
            if verbose:
                print(f"[SS debug] attempt={attempt} status={last_status} size={last_size}")
                print(f"[SS debug] resp headers: {dict(resp.headers)}")
            break
        except urllib.error.HTTPError as e:
            # commit 1 patch A-2: Retry-After header respect
            retry_after_raw = ""
            try:
                retry_after_raw = e.headers.get("Retry-After", "") if e.headers else ""
            except Exception:
                retry_after_raw = ""
            if verbose:
                print(f"[SS debug] attempt={attempt} HTTPError code={e.code} "
                      f"Retry-After={retry_after_raw!r}")
                try:
                    print(f"[SS debug] err resp headers: {dict(e.headers) if e.headers else {}}")
                except Exception:
                    pass
            if e.code == 429 and attempt < _SS_MAX_RETRIES:
                # Retry-After 가 정수면 그 값을 (cap 60s), 없으면 default backoff
                backoff_s = _SS_BACKOFF_S
                try:
                    if retry_after_raw and retry_after_raw.strip().isdigit():
                        backoff_s = min(float(int(retry_after_raw.strip())), 60.0)
                except Exception:
                    backoff_s = _SS_BACKOFF_S
                logger.info("[semantic_scholar] 429 backoff %.1fs (attempt=%d, Retry-After=%r)",
                            backoff_s, attempt, retry_after_raw)
                if verbose:
                    print(f"[SS debug] backoff sleep {backoff_s:.1f}s before attempt {attempt+1}")
                time.sleep(backoff_s)
                continue
            return _empty_result(error=f"HTTPError {e.code}",
                                 elapsed=time.monotonic() - t0)
        except Exception as e:
            if verbose:
                print(f"[SS debug] attempt={attempt} {type(e).__name__}: {e}")
            return _empty_result(error=f"{type(e).__name__}: {e}",
                                 elapsed=time.monotonic() - t0)

    if body is None:
        return _empty_result(error="unknown failure", elapsed=time.monotonic() - t0)

    if verbose:
        print(f"[SS debug] body keys: {list(body.keys())}")
        print(f"[SS debug] body.data len: {len(body.get('data') or [])}")
        first = (body.get('data') or [None])[0]
        if first:
            print(f"[SS debug] data[0] keys: {list(first.keys())}")
            print(f"[SS debug] data[0] title: {(first.get('title') or '')[:80]}")
            print(f"[SS debug] data[0] DOI: {(first.get('externalIds') or {}).get('DOI')}")
            print(f"[SS debug] data[0] openAccessPdf: {first.get('openAccessPdf')}")
            print(f"[SS debug] data[0] venue: {first.get('venue')}")

    data: List[Dict[str, Any]] = body.get("data") or []
    chunks: List[Dict[str, Any]] = []
    supports: List[Dict[str, Any]] = []
    domains: List[str] = []

    for i, paper in enumerate(data):
        d = extract_domain_from_paper(paper, backend="semantic_scholar")
        if not d:
            continue
        u = _paper_to_url(paper)
        # §paper-writer-1 Step C-1: chunks schema 확장 (5 필드 신규)
        ss_authors_raw = paper.get("authors") or []
        ss_authors = [
            a.get("name", "") for a in ss_authors_raw
            if isinstance(a, dict) and a.get("name")
        ]
        ss_journal = paper.get("journal") or {}
        ss_venue = paper.get("venue") or (
            ss_journal.get("name") if isinstance(ss_journal, dict) else None
        )
        ss_doi = (paper.get("externalIds") or {}).get("DOI")
        chunks.append({
            "uri": u,
            "title": paper.get("title") or "",
            "domain": d,
            "authors": ss_authors,
            "year": paper.get("year"),
            "venue": ss_venue,
            "doi": ss_doi,
            "abstract": paper.get("abstract"),
        })
        supports.append({
            "chunk_indices": [i],
            "text": paper.get("title") or "",
            "start_index": 0,
            "end_index": 0,
        })
        domains.append(d)

    elapsed = time.monotonic() - t0
    logger.info("[semantic_scholar] ok items=%d domains_unique=%d elapsed=%.3fs",
                len(data), len(set(domains)), elapsed)

    return {
        "mode": "semantic_scholar",
        "elapsed_sec": round(elapsed, 3),
        "items": len(data),
        "domains": domains,
        "domains_unique": sorted(set(d for d in domains if d)),
        "chunks": chunks,
        "supports": supports,
        "web_search_queries": [q],
        "error": None,
    }
