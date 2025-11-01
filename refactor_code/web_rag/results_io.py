import json, hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from .config import DATA_DIR

def save_results(items, out_dir: Optional[Path | str] = None, *, query: Optional[str] = None) -> str:
    base_dir = Path(out_dir) if out_dir else DATA_DIR
    base_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y_%m_%d_%H%M%S_%f")
    suffix = f"_{hashlib.blake2b((query or '').encode('utf-8'), digest_size=4).hexdigest()}" if query else ""
    path = base_dir / f"resources_{ts}{suffix}.json"
    path.write_text(json.dumps(items or [], ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
