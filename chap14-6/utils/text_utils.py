# utils/text_utils.py
from __future__ import annotations
import re

__all__ = ["clean_snip", "plain_snip"]

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