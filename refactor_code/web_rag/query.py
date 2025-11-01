import os, re
from .config import truthy

_re = re

def sanitize_query(q: str) -> str:
    if not q: return q
    s = q.strip()
    s = _re.sub(r"^\(\s*untitled\s*\)\s*", "", s, flags=_re.I)
    s = _re.sub(r"\b((?:19|20)\d{2})\.\.((?:19|20)\d{2})\b",
                lambda m: "(" + " OR ".join(str(y) for y in range(min(int(m.group(1)), int(m.group(2))), max(int(m.group(1)), int(m.group(2)))+1)) + ")",
                s)
    return _re.sub(r"\s{2,}", " ", s).strip()

def _strip_minus(q: str) -> str:
    return _re.sub(r"(^|\s)-\S+", " ", q).strip()

def cap_minus(q: str, cap: int) -> str:
    if cap <= 0: return _strip_minus(q)
    toks = q.split(); negs = [t for t in toks if t.startswith("-")]
    if len(negs) <= cap: return q
    keep = set(negs[:cap])
    return " ".join(t for t in toks if not (t.startswith("-") and t not in keep)).strip()

def is_naver_safe(q: str) -> bool:
    if not q or len(q) > 80 or len(q.split()) > 6: return False
    bad = [r"\b(site:|filetype:|ext:|intitle:|inurl:|cache:)\S*", r"[()\"{}|\[\]]", r"\b(AND|OR|NOT)\b"]
    return not any(_re.search(p, q, flags=_re.I) for p in bad)

def append_default_negatives(q: str) -> str:
    if not q or not truthy("WEB_APPLY_DEFAULT_NEGATIVES", default="1"): return q
    min_tok = int(os.getenv("WEB_DEFAULT_NEGATIVES_MIN_TOKENS", "3"))
    if min_tok and len(q.split()) < min_tok: return q
    if is_naver_safe(q): return q
    base = (os.getenv("WEB_DEFAULT_NEGATIVES", "-행사 -세미나 -박람회") or "").strip()
    if not base: return q
    existing = set(q.split())
    to_add = [tok for tok in base.split() if tok and tok not in existing]
    return (q.rstrip() + " " + " ".join(to_add)).strip() if to_add else q

# --- Naver 전용 간소화/스킵 ---
def simplify_for_naver(q: str) -> str:
    if not q: return q
    s = q
    m = _re.search(r"(종근당|벤포벨)", s);  s = s[m.start():] if m else s
    s = s.replace('\'',' ').replace('"',' ').replace('/',' ').replace('|',' ')
    s = _re.sub(r"\s+"," ",s).strip()
    if truthy("NAVER_TRIM_OPERATORS","1"):
        s = _re.sub(r"site:\S+|filetype:\S+"," ",s,flags=_re.I)
        s = _re.sub(r"\b(OR|AND|NOT)\b"," ",s,flags=_re.I)
        s = _re.sub(r"[()]"," ",s); s = s.replace(".."," ")
        s = _re.sub(r"\b(event|exhibition|tickets)\b"," ",s,flags=_re.I)
    cap = int(os.getenv("NAVER_NEGATIVE_CAP","0") or "0")
    s = cap_minus(s, cap)
    s = _re.sub(r"\s+"," ",s).strip()
    return s[:200].rstrip() if len(s) > 200 else s

def should_skip_naver(q: str) -> bool:
    s = simplify_for_naver(q or "")
    if not s: return True
    max_len = int(os.getenv("NAVER_MAX_LEN","120") or "120")
    max_toks = int(os.getenv("NAVER_MAX_TOKENS","8") or "8")
    if len(s) > max_len or len(s.split()) > max_toks: return True
    bad = [r"\b(site:|filetype:|ext:|intitle:|inurl:|cache:)\S*", r"[\"{}|\[\]]", r"\.\."]
    return any(_re.search(p, s, flags=_re.I) for p in bad)
