from __future__ import annotations
import os, re, hashlib
from pathlib import Path
from datetime import datetime

absolute_path = os.path.abspath(__file__)
current_path = os.path.dirname(os.path.dirname(absolute_path))  # 프로젝트 루트 기준

def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)

def topic_slug_from(text: str) -> str:
    base = _slugify(text or "untitled")
    return f"{base}-{datetime.now().strftime('%Y%m%d-%H%M')}"

def ascii_namespace(seed: str) -> str:
    core = hashlib.sha1(seed.encode("utf-8","ignore")).hexdigest()[:10]
    return f"ns-{core}"

def topic_dir(slug: str) -> str:
    return os.path.join(current_path, "data", "chroma_store", slug)

def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^\w\-가-힣\s]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s or "untitled"
