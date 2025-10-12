# utils/rag_utils.py
from __future__ import annotations

from typing import Mapping, Any, List, Tuple
from langchain_core.documents import Document
import re, hashlib
from urllib.parse import urlparse
from datetime import datetime

import logging
logger = logging.getLogger(__name__)

# 다른 모듈로부터의 프리뷰 함수만 re-export
from utils.refs import refs_preview_text
__all__ = ["refs_preview_text", "merge_refs", "score_doc", "vector_count"]


# ─────────────────────────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────────────────────────

def _coerce_docs_list(objs: Any) -> list:
    """docs 입력(any)을 안전하게 list로 강제."""
    if objs is None:
        return []
    if isinstance(objs, list):
        return objs
    try:
        return list(objs)
    except Exception:
        return [objs]

def _signature_for_doc_like(d: Any) -> str:
    """
    문서 중복 판정용 시그니처.
    - source(URL) + 내용 앞부분(공백 정규화 후 500자)
    - Document/딕셔너리/임의 객체 모두 수용
    """
    try:
        if isinstance(d, Document):
            pc = (d.page_content or "")
            meta = d.metadata or {}
        elif isinstance(d, dict):
            pc = (d.get("page_content") or d.get("content") or "") or ""
            meta = d.get("metadata") or {}
        else:
            pc = getattr(d, "page_content", "") or ""
            meta = getattr(d, "metadata", {}) or {}

        pc_head = " ".join(pc.split())[:500]
        src = (meta.get("source") or meta.get("url") or "").strip()
        base = f"{src}|{pc_head}"
    except Exception as e:
        # 어떤 형태든 문자열로 고정
        base = repr(d)[:200]
        logger.debug("Doc signature fallback used: %s", e)

    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()


# ─────────────────────────────────────────────────────────────
# 공개 함수
# ─────────────────────────────────────────────────────────────

def merge_refs(existing: dict | None, new_queries: list[str] | None, new_docs: list | None) -> dict:
    """
    references 딕셔너리 병합:
    - {"queries": [...], "docs": [...]} 스키마 유지
    - 쿼리는 트림 후 집합 기반 디듀프
    - 문서는 (source + 내용 앞 500자) 해시로 디듀프
    """
    refs = existing or {}
    merged_q: List[str] = list(refs.get("queries", []) or [])
    merged_d: List[Any] = list(refs.get("docs", []) or [])

    if new_queries:
        merged_q.extend(q for q in new_queries if isinstance(q, str) and q)

    if new_docs:
        merged_d.extend(x for x in _coerce_docs_list(new_docs) if x is not None)

    # 쿼리 디듀프
    seen_q, dedup_q = set(), []
    for q in merged_q:
        qq = (q or "").strip()
        if qq and qq not in seen_q:
            dedup_q.append(qq)
            seen_q.add(qq)

    # 문서 디듀프
    seen_sig, dedup_docs = set(), []
    for d in merged_d:
        try:
            sig = _signature_for_doc_like(d)
        except Exception as e:
            sig = repr(d)[:120]
            logger.debug("Doc signature build failed; using repr: %s", e)
        if sig not in seen_sig:
            dedup_docs.append(d)
            seen_sig.add(sig)

    logger.debug(
        "merge_refs: queries %d→%d, docs %d→%d",
        len(merged_q), len(dedup_q), len(merged_d), len(dedup_docs),
    )
    return {"queries": dedup_q, "docs": dedup_docs}


def score_doc(d: Document, year_now: int | None = None) -> float:
    """
    간단 점수 함수(정렬용):
    - .gov/.go.kr/.edu/.ac.kr 가산
    - 공공/국제/컨설팅 일부 도메인 가산
    - URL/본문 내 연도(20xx) → 최신일수록 가산
    - 차단/봇 페이지 패턴 감점
    """
    if year_now is None:
        year_now = datetime.now().year

    meta = getattr(d, "metadata", {}) or {}
    src  = (meta.get("source") or meta.get("url") or "").strip().lower()
    text = (getattr(d, "page_content", "") or "")

    def _norm_domain(url: str) -> str:
        if not url:
            return ""
        try:
            netloc = urlparse(url).netloc or urlparse("http://" + url).netloc
        except Exception:
            return ""
        netloc = netloc.split("@")[-1].split(":")[0]
        for pref in ("www.", "m.", "mobile."):
            if netloc.startswith(pref):
                netloc = netloc[len(pref):]
        return netloc

    domain = _norm_domain(src)
    score = 0.0

    gov_edu = (
        domain.endswith(".go.kr") or domain.endswith(".gov")
        or domain.endswith(".ac.kr") or domain.endswith(".edu")
    )
    if gov_edu:
        score += 3

    if any(k in domain for k in ("imf.org", "kostat.go", "kotra.or")):
        score += 2
    if any(k in domain for k in ("kpmg", "mckinsey", "gartner", "idc")):
        score += 1.5

    m = re.search(r"\b(20\d{2})\b", src) or re.search(r"\b(20\d{2})\b", text)
    if m:
        yr = int(m.group(1))
        recency = max(0, 6 - (year_now - yr))
        score += recency * 0.2

    if any(b in text.lower() for b in ["enable javascript", "captcha", "access denied", "just a moment"]):
        score -= 2

    return score


def vector_count(collection_name: str, persist_directory: str | None) -> int:
    """
    현재 Chroma persistent 디렉터리에서 collection_name 컬렉션의 문서(아이템) 개수를 반환.
    - 컬렉션이 없으면 0
    - 오류 시 -1
    """
    try:
        if not persist_directory:
            logger.debug("vector_count: persist_directory is None/empty.")
            return -1

        import chromadb  # 런타임 임포트 (선택적 의존성)
        client = chromadb.PersistentClient(path=persist_directory)
        try:
            col = client.get_collection(collection_name)  # 존재 안 하면 예외
        except Exception:
            return 0
        return int(col.count())
    except Exception as e:
        logger.debug("vector_count failed: %s: %s", type(e).__name__, e)
        return -1
