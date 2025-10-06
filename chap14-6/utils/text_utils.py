# utils/text_utils.py
from __future__ import annotations
import re, unicodedata

__all__ = ["clean_snip", "plain_snip"]

# Windows 파일명에서 금지 문자를 우선 제거
_WIN_FORBIDDEN = re.compile(r'[\/\\:\*\?"<>\|]+')
# 허용 문자: 영문/숫자/하이픈(+ 한글 허용 버전)
_ALLOWED_UNI = re.compile(r'[^0-9a-z가-힣\-]+')
_ALLOWED_ASCII = re.compile(r'[^0-9a-z\-]+')

def slugify(title: str, *, allow_unicode: bool = True, default: str = "untitled") -> str:
    """
    공백→하이픈, 소문자화, 금지문자 제거, 연속 하이픈 정리.
    - allow_unicode=True: 한글 보존
    - allow_unicode=False: ASCII만 (NFKD→ASCII translit)
    """
    s = (title or "").strip()
    if not s:
        return default

    # 정규화 및 금지문자 제거
    s = unicodedata.normalize("NFKC", s)
    s = _WIN_FORBIDDEN.sub(" ", s)

    # 공백을 하이픈으로
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
    return s or default

def section_slugify(text: str) -> str:
    """
    헤딩/번호 접두 제거 후 slugify.
    예) '1) 개요', '## 서론', '작성: 제목' → '개요','서론','제목'
    """
    s = (text or "")
    s = re.sub(r"^#+\s*", "", s)              # Markdown 헤딩 기호 제거
    s = re.sub(r"^\d+[\.\)]\s*", "", s)       # 앞번호 제거: 1. / 1)
    s = re.sub(r"^(작성|write)\s*[:：]\s*", "", s, flags=re.I)
    s = s.strip(" -•—·\t")
    return slugify(s)

def clean_snip(s: str, n: int = 120) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ")
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:n] + ("..." if len(s) > n else ""))

def plain_snip(text: str, n: int = 160) -> str:
    t = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.I | re.S)
    t = re.sub(r"<style.*?>.*?</style>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return clean_snip(t, n)