# settings_gatekeep.py (새 파일이거나 기존 settings/config 상단)
import os
from urllib.parse import urlparse

def _env_flag(name: str, default: bool=False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")

def get_allowed_domains() -> set[str]:
    raw = os.getenv("ALLOWED_DOMAINS", "")
    if not raw:
        return set()
    return {d.strip().lower() for d in raw.split(",") if d.strip()}

def gatekeep_enabled() -> bool:
    return _env_flag("GATE_KEEP_SOURCES", False)

# settings_gatekeep.py (append)

def _normalize_host(u: str) -> str:
    try:
        h = urlparse((u or "").strip()).netloc.lower()
    except Exception:
        return ""
    if h.startswith("www."):
        h = h[4:]
    return h

def url_allowed(src: str,
                allowed: set[str] | None = None,
                enabled: bool | None = None) -> bool:
    """
    ALLOWED_DOMAINS와 GATE_KEEP_SOURCES를 함께 고려해 URL 허용/차단 판단.
    - gatekeep이 꺼져 있으면(True/False) → 무조건 허용
    - gatekeep이 켜져 있고 allowed가 비어있으면 → 외부 URL 차단(로컬은 허용)
    - file:/data:/about:/blob: 등 로컬/내장 스킴은 항상 허용
    """
    if enabled is None:
        enabled = gatekeep_enabled()
    if not enabled:
        return True

    # 로컬/내장 스킴은 통과
    s = (src or "").strip()
    scheme = urlparse(s).scheme
    if scheme in ("file", "data", "about", "blob"):
        return True

    host = _normalize_host(s)
    if not host:
        return False

    allowed = allowed if allowed is not None else get_allowed_domains()
    if not allowed:
        # 게이트킵 ON인데 허용리스트가 비면 외부는 막는 게 안전
        print("[WARN] GATE_KEEP_SOURCES=ON 이지만 ALLOWED_DOMAINS가 비어 있음 → 외부 URL 차단")
        return False

    return any(host == d or host.endswith("." + d) for d in allowed)
