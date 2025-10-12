# utils/query_filters.py
from __future__ import annotations
import re
from typing import Final

import logging
logger = logging.getLogger(__name__)

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

_BOOLEAN_TOKENS: Final[re.Pattern[str]] = re.compile(r"\b(?:AND|OR|NOT)\b", re.IGNORECASE)

def strip_web_filters(q: str) -> str:
    if not isinstance(q, str):
        return ""
    s = q
    s = re.sub(r"\(\s*site:[^)]+\)", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"-?\s*site:[^\s)]+", " ", s, flags=re.IGNORECASE)
    for w in ["event", "events", "exhibition", "tickets", "행사", "티켓", "myfair.co", "facebook.com", "instagram.com"]:
        s = re.sub(rf"-\s*{re.escape(w)}\b", " ", s, flags=re.IGNORECASE)
    s = _BOOLEAN_TOKENS.sub(" ", s)
    s = re.sub(r"\s-\s", " ", s)
    s = re.sub(r"(^|\s)-($|\s)", " ", s)
    s = re.sub(r"[()\"'“”‘’`]", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s

def looks_like_local_glob(q: str) -> bool:
    ql = (q or "").strip().lower()
    if ql.startswith("local:"):
        return True
    glob_tokens = ("**\\", "**/", "\\*.", "/*.", "\\**", "/**")
    exts = (".pdf", ".md", ".txt", ".html", ".docx", ".pptx")
    if any(tok in ql for tok in glob_tokens) and any(ext in ql for ext in exts):
        return True
    if "*" in ql and any(ext in ql for ext in exts):
        return True
    return False

def clean_seed(s: str) -> str:
    s = re.sub(r"^#+\s*", "", s)
    s = re.sub(r"^\d+[\.\)]\s*", "", s)
    s = re.sub(r"^(작성|write)\s*[:：]\s*", "", s, flags=re.IGNORECASE)
    s = s.strip(" -•—·\t")
    return s

def ok_query(q: str) -> bool:
    q = (q or "").strip()
    if not q:
        return False
    q2 = clean_seed(q)
    return bool(q2) and (len(q2) <= 200)

# ---- 하위호환(기존 코드가 _prefix 이름을 호출해도 깨지지 않도록) ----
_strip_web_filters = strip_web_filters
_clean_seed = clean_seed
_ok_query = ok_query
