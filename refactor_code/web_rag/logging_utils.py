from settings_gatekeep import _normalize_host
from .config import LOG_WRAP

def ell(s: str, n: int = LOG_WRAP) -> str:
    s = (s or "").replace("\n", " ").strip()
    return (s[:n-1] + "…") if len(s) > n else s

def host_of(u: str) -> str:
    try: return (_normalize_host(u) or "").lower()
    except Exception: 
        from urllib.parse import urlparse
        return (urlparse(u).netloc or "").lower()
