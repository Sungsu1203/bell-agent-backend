# settings_gatekeep.py (새 파일이거나 기존 settings/config 상단)
import os

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
