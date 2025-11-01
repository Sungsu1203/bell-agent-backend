from __future__ import annotations
import os, json, hashlib, logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

def truthy(name: str, default: Optional[str] = None) -> bool:
    raw = os.getenv(name) if default is None else os.getenv(name, default)
    v = (raw or "").strip().lower()
    return v in {"1", "true", "yes", "on"}

def env_int(*names: str, default: int = 0) -> int:
    for n in names:
        v = os.getenv(n)
        if v and v.strip().isdigit(): return int(v.strip())
    return default

def env_str(*names: str, default: str = "") -> str:
    for n in names:
        v = os.getenv(n)
        if v and v.strip(): return v.strip()
    return default

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data"))); DATA_DIR.mkdir(parents=True, exist_ok=True)

SEARCH_MIN_OK     = env_int("SEARCH_MIN_OK", "WEB_MIN_RESULTS_OK", default=1)
SEARCH_TOPN       = env_int("SEARCH_TOPN", default=10)
BACKEND_POLICY    = env_str("SEARCH_POLICY", "WEB_BACKEND_PICK_POLICY", default="best_of_chain").lower()
LOG_TOPK          = int(os.getenv("LOG_TOPK", "3") or "3")
LOG_WRAP          = int(os.getenv("LOG_WRAP", "88") or "88")

def now(fmt: str = "%Y_%m%d_%H%M%S") -> str:
    from datetime import datetime
    return datetime.now().strftime(fmt)
