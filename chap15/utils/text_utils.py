# utils/text_utils.py
from __future__ import annotations
import re, unicodedata
import html

import logging
logger = logging.getLogger(__name__)

__all__ = ["slugify", "section_slugify", "strip_number_prefix", "clean_snip", "plain_snip"]

# Windows 파일명에서 금지 문자를 우선 제거
_WIN_FORBIDDEN = re.compile(r'[\/\\:\*\?"<>\|]+')
# 허용 문자: 영문/숫자/하이픈(+ 한글 허용 버전)
_ALLOWED_UNI = re.compile(r'[^0-9a-z가-힣\-]+')
_ALLOWED_ASCII = re.compile(r'[^0-9a-z\-]+')
_ZERO_WIDTH = re.compile(r"[\u200B-\u200D\uFEFF]")  # ZWSP/ZWNJ/ZWJ/FEFF
_WIN_RESERVED = {
     "con","prn","aux","nul",
     *(f"com{i}" for i in range(1,10)),
     *(f"lpt{i}" for i in range(1,10)),
 }

def slugify(title: str, *, allow_unicode: bool = True, default: str = "untitled", max_len: int = 120) -> str:
    """
    공백→하이픈, 소문자화, 금지문자 제거, 연속 하이픈 정리.
    - allow_unicode=True: 한글 보존
    - allow_unicode=False: ASCII만 (NFKD→ASCII translit)
    - 윈도우 예약어/끝점·공백/제로폭 문자 제거, 길이 제한(max_len)
    """
    s = (title or "").strip()
    if not s:
        return default

    # 정규화 및 금지문자/제로폭 제거
    s = unicodedata.normalize("NFKC", s)
    s = _ZERO_WIDTH.sub("", s)
    s = _WIN_FORBIDDEN.sub(" ", s)

    # 공백을 하이픈으로 -> 소문자화
    s = re.sub(r"\s+", "-", s).lower()

    if allow_unicode:
        s = _ALLOWED_UNI.sub("", s)
    else:
        # ASCII만 남기기 (transliteration)
        s = unicodedata.normalize("NFKD", s)
        s = s.encode("ascii", "ignore").decode("ascii")
        s = _ALLOWED_ASCII.sub("", s)

    # 연속 하이픈/양끝 하이픈 정리
    s = re.sub(r"-{2,}", "-", s).strip("-")

    # 윈도우에서 문제되는 끝 공백/점 제거
    s = s.rstrip(" .")

    # 예약어 회피
    if s in _WIN_RESERVED:
        s = f"{s}-file"

    # 길이 제한
    if max_len and len(s) > max_len:
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