# utils/text_utils.py — dynamic config access (v2025-10-27)
from __future__ import annotations
import re, unicodedata
import html
from typing import Optional

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

__all__ = ["slugify", "section_slugify", "strip_number_prefix", "clean_snip", "plain_snip"]

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

# 기본 동작을 설정으로 제어(런타임에 읽음)
_DEF_ALLOW_UNICODE = bool(_get_cfg_attr("SLUG_ALLOW_UNICODE", True))
_DEF_MAX_LEN = int(_get_cfg_attr("SLUG_MAX_LEN", 120))
_DEF_NORMALIZE_NFKC = bool(_get_cfg_attr("SLUG_NORMALIZE_NFKC", True))
_DEF_PROTECT_WIN_RESERVED = bool(_get_cfg_attr("SLUG_PROTECT_WIN_RESERVED", True))


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
    # CFG 기본값 일원화 (없으면 기존 디폴트 유지)
    if allow_unicode is None:
        allow_unicode = _cfg_bool("SLUG_ALLOW_UNICODE", _DEF_ALLOW_UNICODE)
    if max_len is None:
        max_len = _cfg_int("SLUG_MAX_LEN", _DEF_MAX_LEN)
    normalize_nfkc = _cfg_bool("SLUG_NORMALIZE_NFKC", _DEF_NORMALIZE_NFKC)
    protect_win_reserved = _cfg_bool("SLUG_PROTECT_WIN_RESERVED", _DEF_PROTECT_WIN_RESERVED)

    s = (title or "").strip()
    if not s:
        return default

    # 정규화 및 금지문자/제로폭 제거
    if normalize_nfkc:
        s = unicodedata.normalize("NFKC", s)
    s = _ZERO_WIDTH.sub("", s)
    s = _WIN_FORBIDDEN.sub(" ", s)

    # 공백을 하이픈으로 -> 소문자화
    s = re.sub(r"\s+", "-", s).lower()

    if allow_unicode:
        s = _ALLOWED_UNI.sub("", s)
    else:
        # ASCII만 남기기 (transliteration)
        try:
            # 더 자연스러운 라틴 변환
            from unidecode import unidecode  # type: ignore
            s = unidecode(s)
        except Exception:
            s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        s = _ALLOWED_ASCII.sub("", s)

    # 연속 하이픈/양끝 하이픈 정리
    s = re.sub(r"-{2,}", "-", s).strip("-")

    # 윈도우에서 문제되는 끝 공백/점 제거
    s = s.rstrip(" .")

    # 예약어 회피
    if protect_win_reserved and s in _WIN_RESERVED:
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
