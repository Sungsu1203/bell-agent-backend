# utils/text_utils.py — dynamic config access (v2025-10-27)
from __future__ import annotations
import re, unicodedata
import html
from typing import Optional, Any, Iterable, List

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config access (CFG → module attr → default)
# ─────────────────────────────────────────────────────────────
import core.config as config

def _get_cfg_attr(name: str, default):
    """config.CFG.<name> → config.<name> → default."""
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default

__all__ = ["slugify", "section_slugify", "strip_number_prefix", "clean_snip", "plain_snip", "refresh_text_utils"]

# Windows 파일명에서 금지 문자를 우선 제거
_WIN_FORBIDDEN = re.compile(r'[\/\\:\\*\?"<>\|]+')
# 허용 문자: 영문/숫자/하이픈(+ 한글 허용 버전)
_ALLOWED_UNI = re.compile(r"[^0-9a-z가-힣\-]+")
_ALLOWED_ASCII = re.compile(r"[^0-9a-z\-]+")
_ZERO_WIDTH = re.compile(r"[\u200B-\u200D\uFEFF]")  # ZWSP/ZWNJ/ZWJ/FEFF
_WIN_RESERVED = {
     "con","prn","aux","nul",
     *(f"com{i}" for i in range(1,10)),
     *(f"lpt{i}" for i in range(1,10)),
 }

# ─────────────────────────────────────────────────────────────
# Per-call dynamic getters (reload_config() 즉시 반영)
# ─────────────────────────────────────────────────────────────
def _cfg_bool(name: str, default: bool) -> bool:
    v = _get_cfg_attr(name, default)
    try:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1","true","yes","on","y"}
    except Exception:
        return default

def _cfg_int(name: str, default: int) -> int:
    v = _get_cfg_attr(name, default)
    try:
        if isinstance(v, int):
            return v
        s = str(v)
        return int(float(s))
    except Exception:
        return default

def _as_list(v: Any) -> List[str]:
    if not v:
        return []
    try:
        return [str(x).strip() for x in (v if isinstance(v, (list,tuple)) else str(v).split(";")) if str(x).strip()]
    except Exception:
        return []

def _slug_allow_unicode() -> bool:
    return _cfg_bool("SLUG_ALLOW_UNICODE", True)
def _slug_max_len() -> int:
    return _cfg_int("SLUG_MAX_LEN", 120)
def _slug_normalize_nfkc() -> bool:
    return _cfg_bool("SLUG_NORMALIZE_NFKC", True)
def _slug_protect_win_reserved() -> bool:
    return _cfg_bool("SLUG_PROTECT_WIN_RESERVED", True)
def _slug_use_unidecode() -> bool:
    # ASCII 모드에서 unidecode 우선 사용 여부
    return _cfg_bool("SLUG_USE_UNIDECODE", True)
def _slug_strip_emoji() -> bool:
    return _cfg_bool("SLUG_STRIP_EMOJI", True)

# 간단한 이모지/픽토 범위(완벽하진 않지만 일반 케이스에 유용)
_EMOJI = re.compile(
    "["                                     # noqa: W605
    "\U0001F300-\U0001F64F"                 # Misc Symbols and Pictographs
    "\U0001F680-\U0001F6FF"                 # Transport & Map
    "\U0001F700-\U0001F77F"                 # Alchemical Symbols
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002700-\U000027BF"                 # Dingbats
    "\U00002600-\U000026FF"                 # Misc symbols
    "]"
)

# 번호/챕터 접두 커스터마이즈(세미콜론 구분식 또는 리스트)
def _extra_strip_prefix_patterns() -> List[str]:
    raw = _get_cfg_attr("STRIP_PREFIX_EXTRA_REGEX", [])
    return _as_list(raw)

def slugify(
    title: str,
    *,
    allow_unicode: Optional[bool] = None,
    default: str = "untitled",
    max_len: Optional[int] = None,
) -> str:
    """
    공백→하이픈, 소문자화, 금지문자 제거, 연속 하이픈 정리.
    - allow_unicode=True: 한글 보존
    - allow_unicode=False: ASCII만 (NFKD→ASCII translit, unidecode 있으면 사용)
    - 윈도우 예약어/끝점·공백/제로폭 문자 제거, 길이 제한(max_len)
    설정 기본값은 CFG에서 읽어 동적으로 적용됩니다.
    """
    # CFG 기본값(런타임 조회)
    if allow_unicode is None:
        allow_unicode = _slug_allow_unicode()
    if max_len is None:
        max_len = _slug_max_len()
    normalize_nfkc = _slug_normalize_nfkc()
    protect_win_reserved = _slug_protect_win_reserved()

    s = (title or "").strip()
    if not s:
        return default

    # 정규화 및 금지문자/제로폭 제거
    if normalize_nfkc:
        s = unicodedata.normalize("NFKC", s)
    s = _ZERO_WIDTH.sub("", s)
    s = _WIN_FORBIDDEN.sub(" ", s)
    if _slug_strip_emoji():
        s = _EMOJI.sub(" ", s)

    # 공백을 하이픈으로 -> 소문자화
    s = re.sub(r"\s+", "-", s).lower()

    if allow_unicode:
        s = _ALLOWED_UNI.sub("", s)
    else:
        # ASCII만 남기기 (transliteration)
        try:
            # 더 자연스러운 라틴 변환
            if _slug_use_unidecode():
                from unidecode import unidecode  # type: ignore
                s = unidecode(s)
            else:
                raise ImportError()
        except Exception:
            s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = _ALLOWED_ASCII.sub("", s)

    # 연속 하이픈/양끝 하이픈 정리
    s = re.sub(r"-{2,}", "-", s).strip("-")

    # 윈도우에서 문제되는 끝 공백/점 제거
    s = s.rstrip(" .")

    # 예약어 회피
    if protect_win_reserved and s.lower() in _WIN_RESERVED:
        s = f"{s}-file"

    # 길이 제한
    if max_len and max_len > 0 and len(s) > max_len:
        s = s[:max_len].rstrip("-.")

    return s or default


def strip_number_prefix(text: str) -> str:
    """
    헤딩/번호/불릿 접두만 제거하여 '원제목'을 정규화.
    - 슬러그화(소문자/하이픈 치환)는 하지 않음.
    - 리포트 빌더에서 '파일 내부 첫 헤딩'과 '아웃라인 타이틀'을
      사람 눈높이 기준으로 매칭할 때 폴백으로 사용.
    """
    s = (text or "")
    # Markdown 헤딩 기호 제거
    s = re.sub(r"^#+\s*", "", s)
    # 앞번호 제거: (1) / 1. / 1)
    s = re.sub(r"^\(?\d+[\.\)]\s*", "", s)
    # 로마 숫자 i. ii. iv) 등
    s = re.sub(r"^[ivxlcdm]+\.\s*", "", s, flags=re.I)
    # 원형 숫자 ①-⑳
    s = re.sub(r"^[①-⑳]\s*", "", s)
    # '제 N 장' / 'Chapter 1' 등 관용 접두 제거
    s = re.sub(r"^(제\s*\d+\s*장)\s*", "", s)
    s = re.sub(r"^(chapter|chap\.?)\s*\d+\s*[:\.\-]?\s*", "", s, flags=re.I)
    # '작성:' / 'write:' 제거
    s = re.sub(r"^(작성|write)\s*[:：]\s*", "", s, flags=re.I)
    # 흔한 불릿/대시 제거
    s = s.strip(" -–—•·\t")
    # (옵션) 추가 패턴 제거(CFG)
    for pat in _extra_strip_prefix_patterns():
        try:
            s = re.sub(pat, "", s, flags=re.I)
        except Exception:
            continue
    return s


def section_slugify(text: str) -> str:
    """
    헤딩/번호 접두 제거 후 slugify.
    예) '1) 개요', '## 서론', '작성: 제목' → '개요','서론','제목'
    """
    s = strip_number_prefix(text)
    # 섹션 슬러그는 보통 유니코드 유지가 더 직관적이므로 CFG 기본을 따르되 override 가능
    return slugify(s)


def clean_snip(s: str, n: int = 120) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ")
    # 제어문자 제거
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+", " ", s)
    s = _ZERO_WIDTH.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:n] + ("..." if len(s) > n else ""))


def plain_snip(text: str, n: int = 160) -> str:
    # HTML 엔티티 디코딩 우선
    t = html.unescape(text or "")
    # script/style 제거
    t = re.sub(r"<script.*?>.*?</script>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<style.*?>.*?</style>", " ", t, flags=re.I | re.S)
    # 태그 제거
    t = re.sub(r"<[^>]+>", " ", t)
    return clean_snip(t, n)

# ─────────────────────────────────────────────────────────────
# (옵션) 캐시 무효화 훅 — 현재 구현은 per-call 조회이므로 no-op
# ─────────────────────────────────────────────────────────────
def refresh_text_utils() -> None:  # pragma: no cover
    """향후 lru_cache 최적화 시 cache_clear() 연결용 훅.
    현재 버전은 per-call 조회로 즉시 반영되므로 동작 없음."""
    return