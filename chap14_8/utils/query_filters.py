# utils/query_filters.py — dynamic config access (v2025-10-27)
from __future__ import annotations

import re
from typing import Final, Pattern, Iterable, Optional, List

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config access (no static binding)
# ─────────────────────────────────────────────────────────────
import core.config as config

__all__ = [
    "strip_web_filters",
    "looks_like_local_glob",
    "clean_seed",
    "ok_query",
    # ↓ 하위호환 별칭
    "_strip_web_filters",
    "_clean_seed",
    "_ok_query",
]

# ─────────────────────────────────────────────────────────────
# Config helpers with safe defaults
# ─────────────────────────────────────────────────────────────

def _get_cfg_attr(name: str, default):
    """config.CFG.<name> 또는 config.<name> 를 순서대로 조회."""
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default


def _as_list(v: Optional[Iterable[str]]) -> List[str]:
    if not v:
        return []
    try:
        return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        return []


# Defaults (동작 보장용)
_DEF_BOOLEAN_TOKENS: List[str] = ["AND", "OR", "NOT"]
_DEF_NEGATIVE_KEYWORDS: List[str] = [
    # EN
    "event", "events", "exhibition", "tickets",
    # KR
    "행사", "티켓",
]
_DEF_NEGATIVE_DOMAINS: List[str] = [
    "myfair.co", "facebook.com", "instagram.com"
]
_DEF_LOCAL_GLOB_EXTS: List[str] = [".pdf", ".md", ".txt", ".html", ".docx", ".pptx"]
_DEF_LOCAL_GLOB_TOKENS: List[str] = ["**\\", "**/", "\\*.", "/*.", "\\**", "/**"]
_DEF_MAX_QUERY_LEN: int = 200


# Load from dynamic config (config reload 시 재평가 필요하면 함수화하여 호출부에서 재컴파일 가능)
_BOOLEAN_TOKENS_SET: List[str] = (
    _as_list(_get_cfg_attr("BOOLEAN_TOKENS", None)) or _DEF_BOOLEAN_TOKENS
)
_NEGATIVE_KEYWORDS: List[str] = (
    _as_list(_get_cfg_attr("SEARCH_NEGATIVE_KEYWORDS", None)) or _DEF_NEGATIVE_KEYWORDS
)
_NEGATIVE_DOMAINS: List[str] = (
    _as_list(_get_cfg_attr("SEARCH_NEGATIVE_DOMAINS", None)) or _DEF_NEGATIVE_DOMAINS
)
_LOCAL_GLOB_EXTS: List[str] = (
    _as_list(_get_cfg_attr("LOCAL_GLOB_EXTS", None)) or _DEF_LOCAL_GLOB_EXTS
)
_LOCAL_GLOB_TOKENS: List[str] = (
    _as_list(_get_cfg_attr("LOCAL_GLOB_TOKENS", None)) or _DEF_LOCAL_GLOB_TOKENS
)
_MAX_QUERY_LEN: int = int(_get_cfg_attr("MAX_QUERY_LEN", _DEF_MAX_QUERY_LEN) or _DEF_MAX_QUERY_LEN)
_STRIP_SITE_FILTERS: bool = bool(_get_cfg_attr("STRIP_SITE_FILTERS", True))

# typing.Pattern을 사용해야 타입체커/런타임 호환성이 좋음 (re.Pattern[str]은 일부 환경에서 불안정)
_BOOLEAN_TOKENS: Final[Pattern[str]] = re.compile(
    r"\\b(?:" + "|".join(map(re.escape, _BOOLEAN_TOKENS_SET)) + r")\\b",
    re.IGNORECASE,
)


def strip_web_filters(q: str) -> str:
    """검색어에서 불필요한 필터/부정 토큰/불리언 연산자 제거.

    동적 설정:
      - STRIP_SITE_FILTERS: site: 필터 제거 여부 (기본 True)
      - SEARCH_NEGATIVE_KEYWORDS / SEARCH_NEGATIVE_DOMAINS: -키워드/-도메인 제거 목록
      - BOOLEAN_TOKENS: 불리언 토큰 목록
    """
    if not isinstance(q, str):
        return ""
    s = q

    # site: 필터 제거 (괄호 포함/미포함)
    if _STRIP_SITE_FILTERS:
        s = re.sub(r"\(\s*site:[^\)]+\)", " ", s, flags=re.IGNORECASE)
        s = re.sub(r"-?\s*site:[^\s)]+", " ", s, flags=re.IGNORECASE)

    # 자주 차단하는 부정 키워드/도메인들 제거
    for w in (*_NEGATIVE_KEYWORDS, *_NEGATIVE_DOMAINS):
        s = re.sub(rf"-\s*{re.escape(w)}\b", " ", s, flags=re.IGNORECASE)

    # 불리언 토큰 제거
    s = _BOOLEAN_TOKENS.sub(" ", s)

    # 고립된 '-' 정리
    s = re.sub(r"\s-\s", " ", s)
    s = re.sub(r"(^|\s)-($|\s)", " ", s)

    # 괄호/인용부호/백틱 제거
    s = re.sub(r"[()\"'“”‘’`]", " ", s)

    # 공백 정규화
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def looks_like_local_glob(q: str) -> bool:
    """로컬 파일 글롭 패턴처럼 보이는지 판정.

    동적 설정:
      - LOCAL_GLOB_TOKENS, LOCAL_GLOB_EXTS
    """
    ql = (q or "").strip().lower()
    if ql.startswith("local:"):
        return True

    if any(tok in ql for tok in _LOCAL_GLOB_TOKENS) and any(ext in ql for ext in _LOCAL_GLOB_EXTS):
        return True
    if "*" in ql and any(ext in ql for ext in _LOCAL_GLOB_EXTS):
        return True
    return False


def clean_seed(s: str) -> str:
    """헤딩/번호/작성 접두 제거 후 양끝 불릿/대시 공백 정리."""
    s = re.sub(r"^#+\s*", "", s)                             # Markdown 헤딩
    s = re.sub(r"^\d+[\\.\)]\s*", "", s)                      # 1. / 1)
    s = re.sub(r"^(작성|write)\s*[:：]\s*", "", s, flags=re.IGNORECASE)
    s = s.strip(" -•—·\t")
    return s


def ok_query(q: str) -> bool:
    """질의가 비어있지 않고 너무 길지 않은지 간단 검증.

    동적 설정:
      - MAX_QUERY_LEN (기본 200)
    """
    q = (q or "").strip()
    if not q:
        return False
    q2 = clean_seed(q)
    return bool(q2) and (len(q2) <= _MAX_QUERY_LEN)


# ---- 하위호환(기존 코드가 _prefix 이름을 호출해도 깨지지 않도록) ----
_strip_web_filters = strip_web_filters
_clean_seed = clean_seed
_ok_query = ok_query
