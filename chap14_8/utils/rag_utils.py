# utils/rag_utils.py — dynamic config access (v2025-10-27)
from __future__ import annotations

from typing import Mapping, Any, List, Sequence, Dict, Optional, cast, TypedDict
from langchain_core.documents import Document
import re, hashlib
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
import os

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config (avoid static binding to CFG values at import)
# ─────────────────────────────────────────────────────────────
import core.config as config

# ── refs 프리뷰 함수 re-export (안전 임포트) ─────────────────────
try:
    from utils.refs import refs_preview_text as _refs_preview_text
except Exception:
    def _refs_preview_text(state: Mapping[str, Any], max_q: int = 5, max_docs: int = 8, snippet_len: int = 350) -> str:
        """임시 폴백: refs 미구현 환경에서도 깨지지 않도록."""
        refs = dict(state or {}).get("references", {}) or {}
        qs = (refs.get("queries") or [])[:max_q]
        return "Queries:\n" + ("\n".join(f"- {q}" for q in qs) if qs else "(none)")

# 외부에서 import * 시 노출 대상
__all__ = ["refs_preview_text", "merge_refs", "score_doc", "vector_count"]

# 외부 노출 이름 고정
refs_preview_text = _refs_preview_text  # type: ignore

# ─────────────────────────────────────────────────────────────
# Config helpers & defaults
# ─────────────────────────────────────────────────────────────

def _get_cfg_attr(name: str, default):
    """config.CFG.<name> → config.<name> 순으로 조회."""
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default

# Signature & scoring defaults
_SIG_HEAD_CHARS: int = int(_get_cfg_attr("DOC_SIGNATURE_HEAD_CHARS", 500))
_GOV_EDU_BONUS: float = float(_get_cfg_attr("SCORE_GOV_EDU_BONUS", 3.0))
_IFI_BONUS: float = float(_get_cfg_attr("SCORE_IFI_BONUS", 2.0))
_CONSULT_BONUS: float = float(_get_cfg_attr("SCORE_CONSULT_BONUS", 1.5))
_RECENCY_WINDOW_YEARS: int = int(_get_cfg_attr("RECENCY_WINDOW_YEARS", 6))
_RECENCY_WEIGHT: float = float(_get_cfg_attr("RECENCY_WEIGHT", 0.2))
_BOT_PENALTY: float = float(_get_cfg_attr("SCORE_BOTPAGE_PENALTY", 2.0))

_IFI_DOMAINS: List[str] = [
    *(_get_cfg_attr("SCORE_IFI_DOMAINS", []) or []),
    "imf.org", "kostat.go", "kotra.or",
]
_CONSULT_DOMAINS: List[str] = [
    *(_get_cfg_attr("SCORE_CONSULT_DOMAINS", []) or []),
    "kpmg", "mckinsey", "gartner", "idc",
]
_BOT_TERMS: List[str] = [
    *(_get_cfg_attr("SCORE_BOT_TERMS", []) or []),
    "enable javascript", "captcha", "access denied", "just a moment",
]

# ─────────────────────────────────────────────────────────────
# Refs 타입(문서화/정적체커 친화)
# ─────────────────────────────────────────────────────────────
class Refs(TypedDict, total=False):
    queries: List[str]
    docs: List[Any]
    # 필요한 경우 확장 키 허용(예: 'meta')


# ─────────────────────────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────────────────────────

def _coerce_docs_list(objs: Optional[Sequence[Any]]) -> List[Any]:
    """docs 입력(Sequence|None)을 안전하게 list로 강제."""
    if objs is None:
        return []
    # 이미 시퀀스면 그대로 리스트화
    try:
        return list(objs)
    except Exception:
        # 혹시 모르는 예외 대비
        return [objs]  # type: ignore[list-item]
    
def _norm_queries(seq: Sequence[str] | None) -> List[str]:
    if not seq:
        return []
    out: List[str] = []
    for q in seq:
        if not isinstance(q, str):
            continue
        qq = q.strip()
        if qq:
            out.append(qq)
    return out

def _dedupe_preserve_order_str(items: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for it in items:
        key = it.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _signature_for_doc_like(d: Any) -> str:
    """
    문서 중복 판정용 시그니처.
    - source(URL) + 내용 앞부분(공백 정규화 후 N자; N=DOC_SIGNATURE_HEAD_CHARS)
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

        pc_head = " ".join(str(pc).split())[:_SIG_HEAD_CHARS]
        src = (meta.get("source") or meta.get("url") or "").strip()
        base = f"{src}|{pc_head}"
    except Exception as e:
        base = repr(d)[:200]
        logger.debug("Doc signature fallback used: %s", e)

    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()


#─────────────────────────────────────────────────────────────
# 공개 함수
# ─────────────────────────────────────────────────────────────

def merge_refs(
    existing: Mapping[str, Any] | None,
    new_queries: Sequence[str] | None,
    new_docs: Sequence[Any] | None,
    *,
    preserve_extra: bool = True,
    limit_queries: Optional[int] = None,
    limit_docs: Optional[int] = None,
    sort_docs_by_score: bool = False,
) -> Refs:
    """
    references 병합(불변): 입력을 절대 수정하지 않고 새로운 dict(List 포함)를 반환.
    - preserve_extra=True: existing의 기타 키(meta 등)를 그대로 보존
    - limit_*: 상한 적용(CFG.MERGE_REFS_MAX_QUERIES / CFG.MERGE_REFS_MAX_DOCS 기본값 사용)
    - sort_docs_by_score=True: score_doc 기준 내림차순 정렬 후 상한 적용
    """
    # CFG 기반 상한 기본값
    if limit_queries is None:
        limit_queries = int(_get_cfg_attr("MERGE_REFS_MAX_QUERIES", 0) or 0)
    if limit_docs is None:
        limit_docs = int(_get_cfg_attr("MERGE_REFS_MAX_DOCS", 0) or 0)

    base: Dict[str, Any] = dict(existing or {})  # shallow copy(입력 보호)
    base_q = _norm_queries(cast(Sequence[str] | None, base.get("queries")))
    base_d = _coerce_docs_list(cast(Sequence[Any] | None, base.get("docs")))

    add_q = _norm_queries(new_queries)
    add_d = _coerce_docs_list(new_docs)

    # 1) 쿼리: 기존→신규 순서 유지+디듀프(대소문자 무시)
    merged_q = _dedupe_preserve_order_str([*base_q, *add_q])
    if limit_queries and limit_queries > 0:
        merged_q = merged_q[:limit_queries]

    # 2) 문서: 시그니처 기반 "처음 등장 우선" 디듀프
    seen_sig: set[str] = set()
    dedup_docs: List[Any] = []
    for d in [*base_d, *add_d]:
        if d is None:
            continue
        try:
            sig = _signature_for_doc_like(d)
        except Exception as e:
            sig = repr(d)[:120]
            logger.debug("Doc signature build failed; using repr: %s", e)
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        dedup_docs.append(d)

    # 3) (옵션) 점수 정렬
    docs_out = dedup_docs
    if sort_docs_by_score:
        try:
            docs_out = sorted(
                dedup_docs,
                key=lambda x: score_doc(x) if isinstance(x, Document) else 0.0,
                reverse=True,
            )
        except Exception:
            # 안전 폴백: 정렬 실패 시 원래 순서 유지
            docs_out = dedup_docs

    if limit_docs and limit_docs > 0:
        docs_out = docs_out[:limit_docs]

    # 4) 순수 새 객체 구성(입력 불변 보장)
    out: Refs = {"queries": list(merged_q), "docs": list(docs_out)}
    if preserve_extra:
        # 나머지 키(meta 등)는 얕은 복사로 보존(참조 공유 허용)
        for k, v in base.items():
            if k not in ("queries", "docs"):
                out[k] = v  # 그대로 보존

    logger.debug(
        "merge_refs(pure): queries %d→%d, docs %d→%d (sorted=%s, cap_q=%s, cap_d=%s)",
        len(base_q) + len(add_q), len(out["queries"]),
        len(base_d) + len(add_d), len(out["docs"]),
        sort_docs_by_score, limit_queries, limit_docs,
    )
    return out


def score_doc(d: Document, year_now: int | None = None) -> float:
    """
    간단 점수 함수(정렬용):
    - .gov/.go.kr/.edu/.ac.kr 가산 (SCORE_GOV_EDU_BONUS)
    - 공공/국제/컨설팅 일부 도메인 가산 (SCORE_IFI_DOMAINS, SCORE_CONSULT_DOMAINS)
    - URL/본문 내 연도(20xx) → 최신일수록 가산 (RECENCY_WINDOW_YEARS, RECENCY_WEIGHT)
    - 차단/봇 페이지 패턴 감점 (SCORE_BOT_TERMS, SCORE_BOTPAGE_PENALTY)
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
        score += _GOV_EDU_BONUS

    if any(k in domain for k in _IFI_DOMAINS):
        score += _IFI_BONUS
    if any(k in domain for k in _CONSULT_DOMAINS):
        score += _CONSULT_BONUS

    m = re.search(r"\b(20\d{2})\b", src) or re.search(r"\b(20\d{2})\b", text)
    if m:
        yr = int(m.group(1))
        recency = max(0, _RECENCY_WINDOW_YEARS - (year_now - yr))
        score += recency * _RECENCY_WEIGHT

    lt = text.lower()
    if any(b in lt for b in _BOT_TERMS):
        score -= _BOT_PENALTY

    return score


def vector_count(collection_name: str, persist_directory: str | os.PathLike[str] | None) -> int:
    """
    현재 Chroma persistent 디렉터리에서 collection_name 컬렉션의 문서(아이템) 개수를 반환.
    - 컬렉션이 없으면 0
    - 오류 시 -1
    """
    try:
        if not persist_directory:
            logger.debug("vector_count: persist_directory is None/empty.")
            return -1

        p = str(Path(persist_directory))
        if not p:
            return -1

        import chromadb  # 선택적 의존성, 런타임 임포트
        client = chromadb.PersistentClient(path=p)
        try:
            try:
                col = client.get_collection(collection_name)  # 존재 안 하면 예외
            except Exception:
                return 0
            return int(col.count())
        finally:
            # 가능한 경우 클라이언트 정리
            for meth in ("close", "shutdown", "persist", "teardown", "reset", "stop"):
                fn = getattr(client, meth, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
    except Exception as e:
        logger.debug("vector_count failed: %s: %s", type(e).__name__, e)
        return -1
