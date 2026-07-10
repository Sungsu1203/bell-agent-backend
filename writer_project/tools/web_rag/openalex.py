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

import urllib.request
import ssl
import certifi

from tools.web_rag._scholarly_domain import extract_domain_from_paper

# 맥 urllib 루트 인증서 미연결 회피 — certifi 번들 명시 (catch 신규: macOS SSL)
_SSL_CTX = ssl.create_default_context(cafile=certifi.where())

logger = logging.getLogger(__name__)

_OA_ENDPOINT = "https://api.openalex.org/works"
_OA_DEFAULT_PER_PAGE = 10
_OA_TIMEOUT_S = 10.0
_OA_BACKOFF_S = 2.0


# ── §paper-writer-1 Step C-1: chunks schema 확장 helper ──────────────────────
def _strip_doi_prefix(doi: Optional[str]) -> Optional[str]:
    """OA work.doi 'https://doi.org/{doi}' prefix 제거 후 bare DOI 반환."""
    if not doi:
        return None
    s = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if s.lower().startswith(prefix):
            return s[len(prefix):].strip() or None
    return s or None


# ── §axis1 OA충전 catch 82: venue 추출 type-aware fallback ────────────────────
# 원인(catch 82): 기존 venue = primary_location.source.display_name 단일경로. OA 는
# primary_location 을 리포지토리 사본(source=None 또는 type=repository)에 걸어두는
# 경우가 흔해(법학·preprint), 저널이 뒤 location 에 있어도 통째 드롭됨.
# ("blanket host_venue 오독" 가설 폐기 — 실제 기제 = 신 스키마의 잘못된 단일 위치.)
# safe-core 회수 정책(R2 오프라인 검증, 60 chunk / garbage 0 / regression 0):
#   1) primary_location.source (type 이 리포 계열 아닐 때만)
#   2) locations[] 전체 순회(인덱스 무가정) → type 이 리포 계열 아닌 첫 구조화 source
#   3) 없으면 primary_location.source 리포명이라도 보존 (arXiv/SSRN = 기존 동작, regression 0)
#   4) 그것도 없으면 None (책·진짜 결손)
# ★raw_source_name 폴백 미채택 — filename('...pdf')·vol번호('40')·vendor-id('MODID-...')·
#   citation-dump 등 garbage 다수(R2 STOP 보고). arXiv 는 표시 유지(OA 에 저널/학회 source
#   부재 = 데이터 부재, 규범선택 아님).
_OA_REPO_SOURCE_TYPES = {"repository", "ebook platform"}


def _oa_source_name(src: Any) -> Optional[str]:
    """OA source dict → 비어있지 않은 display_name (아니면 None)."""
    if isinstance(src, dict):
        n = src.get("display_name")
        if isinstance(n, str) and n.strip():
            return n.strip()
    return None


def _extract_venue(work: Dict[str, Any]) -> Optional[str]:
    """OA work → venue. primary_location.source 단일경로 대신 type-aware fallback."""
    pl = work.get("primary_location") or {}
    ps = pl.get("source")
    # 1) primary source 가 리포 계열이 아니면 채택
    if isinstance(ps, dict) and ps.get("type") not in _OA_REPO_SOURCE_TYPES:
        n = _oa_source_name(ps)
        if n:
            return n
    # 2) locations[] 전체 순회 → 리포 계열 아닌 첫 구조화 source
    for loc in (work.get("locations") or []):
        if not isinstance(loc, dict):
            continue
        s = loc.get("source")
        if isinstance(s, dict) and s.get("type") not in _OA_REPO_SOURCE_TYPES:
            n = _oa_source_name(s)
            if n:
                return n
    # 3) 저널 없음 → primary 리포명 보존(기존 동작 == regression 0) / 4) 없으면 None
    return _oa_source_name(ps)


def _reconstruct_abstract_from_inverted_index(
    inv: Optional[dict],
) -> Optional[str]:
    """OpenAlex abstract_inverted_index (dict[word, list[int]]) → 문자열 재조립.

    OpenAlex 는 abstract 를 word→positions dict 로 저장 (저작권 우회). 단어를
    position 순으로 정렬해 공백 join 한다. None 또는 빈 dict 입력은 None 반환.
    """
    if not inv or not isinstance(inv, dict):
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        if not isinstance(idxs, list):
            continue
        for i in idxs:
            if isinstance(i, int):
                positions.append((i, word))
    if not positions:
        return None
    positions.sort(key=lambda p: p[0])
    return " ".join(w for _, w in positions)


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
            with urllib.request.urlopen(req, timeout=_OA_TIMEOUT_S, context=_SSL_CTX) as resp:
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
        # §paper-writer-1 Step C-1: chunks schema 확장 (5 필드 신규)
        oa_authorships = work.get("authorships") or []
        oa_authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in oa_authorships
            if isinstance(a, dict) and (a.get("author") or {}).get("display_name")
        ]
        # catch 82: primary_location.source 단일경로 드롭 방지 (type-aware fallback)
        oa_venue = _extract_venue(work)
        chunks.append({
            "uri": u,
            "title": work.get("title") or "",
            "domain": d,
            "authors": oa_authors,
            "year": work.get("publication_year"),
            "venue": oa_venue,
            "doi": _strip_doi_prefix(work.get("doi")),
            "abstract": _reconstruct_abstract_from_inverted_index(
                work.get("abstract_inverted_index")
            ),
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
