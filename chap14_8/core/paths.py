# core/paths.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os, hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple, cast

import core.config as config
from core.config import CFG, DocMode
from utils.text_utils import slugify, section_slugify

# ──────────────────────────────────────────────────────────────
# 프로젝트 루트: 항상 config.CFG.PROJECT_ROOT 기준으로 일원화
# ──────────────────────────────────────────────────────────────
current_path = config.CFG.PROJECT_ROOT


def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)


def _resolve_under_root(p: str | Path) -> Path:
    """절대경로면 그대로, 상대경로면 PROJECT_ROOT 기준으로 해석."""
    q = Path(p)
    return q if q.is_absolute() else (Path(current_path) / q).resolve()


# ── Research output base (RESEARCH_OUT_DIR → REPORT_OUT_DIR/research → <project>/research)
def research_base_dir() -> Path:
    ro = (CFG.RESEARCH_OUT_DIR or "").strip()
    if ro:
        return _resolve_under_root(ro)

    rep = (CFG.REPORT_OUT_DIR or "").strip()
    if rep:
        return _resolve_under_root(rep) / "research"

    return Path(current_path) / "research"


def research_topic_dir(topic_slug: str | None) -> Path:
    topic = (topic_slug or "default").strip() or "default"
    return research_base_dir() / topic


def research_resources_dir(topic_slug: str | None) -> Path:
    """research_base_dir()의 형제 폴더로 resources/<topic> 구성."""
    base = research_base_dir()
    parent = base.parent
    root = parent if str(parent) not in ("", ".") else base
    topic = (topic_slug or "default").strip() or "default"
    return root / "resources" / topic


# ── Outline base (REPORT_OUT_DIR/outlines → <project>/outlines)
def outline_base_dir() -> Path:
    # ✅ 항상 프로젝트 루트 아래 'outlines' 고정 (읽기와 일치)
    return Path(current_path) / "outlines"


def outline_topic_dir(topic_slug: str | None, mode: str | None = None) -> Path:
    """주제별 아웃라인 디렉터리 (mode 하위폴더 제거, 읽기 경로와 일치)."""
    topic = (topic_slug or "default").strip() or "default"
    return outline_base_dir() / topic


def topic_slug_from(text: str) -> str:
    base = slugify(text or "untitled")
    return f"{base}-{datetime.now().strftime('%Y%m%d-%H%M')}"


def ascii_namespace(seed: str) -> str:
    core = hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()[:10]
    return f"ns-{core}"


def topic_dir(slug: str) -> str:
    return os.path.join(current_path, "data", "chroma_store", slug)


def _coerce_mode(mode: Optional[str | DocMode]) -> DocMode:
    """문자열/None을 DocMode로 정규화."""
    if mode in ("book", "report"):
        return cast(DocMode, mode)
    # ✅ CFG.DOC_MODE에서 직접 가져오도록 수정
    return CFG.DOC_MODE


def _base_dir_for_mode(mode: Optional[str | DocMode] = None) -> str:
    m: DocMode = _coerce_mode(mode)
    return "sections" if m == "report" else "chapters"


def get_content_dir(
    mode: Optional[str | DocMode] = None,
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> Path:
    root = _resolve_under_root(root_dir) if root_dir else Path(current_path)
    base = base_dir or _base_dir_for_mode(mode)
    p = root / base
    if topic_slug:
        p = p / topic_slug
    p.mkdir(parents=True, exist_ok=True)
    return p


def path_for_title(
    title: str,
    *,
    mode: Optional[str | DocMode] = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> Path:
    m: DocMode = _coerce_mode(mode)
    outdir = get_content_dir(m, root_dir=root_dir, topic_slug=topic_slug, base_dir=base_dir)
    return outdir / f"{slugify(title)}.md"


def chapter_filepath(
    title: str,
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> Path:
    outdir = get_content_dir("book", root_dir=root_dir, topic_slug=topic_slug)
    return outdir / f"{slugify(title)}.md"


def section_filepath(
    title: str,
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> Path:
    outdir = get_content_dir("report", root_dir=root_dir, topic_slug=topic_slug)
    return outdir / f"{section_slugify(title)}.md"


def get_outline_dir(
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> Path:
    root = _resolve_under_root(root_dir) if root_dir else Path(current_path)
    d = root / "outlines"
    if topic_slug:
        d = d / topic_slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default_outline_name(mode: Optional[str | DocMode] = None) -> str:
    m: DocMode = _coerce_mode(mode)
    return "outline_report.md" if m == "report" else "outline_book.md"


def outline_path(
    filename: Optional[str] = None,
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    mode: Optional[str | DocMode] = None,
) -> Path:
    fname = (filename or _default_outline_name(mode))
    return get_outline_dir(root_dir=root_dir, topic_slug=topic_slug) / fname


def read_outline(
    filename: str,
    *,
    root_dir: str,
    topic_slug: str | None,
    mode: str | DocMode | None = None,
    allow_fallbacks: bool = True,
) -> Tuple[str, Optional[Path]]:
    """
    (filename, *, root_dir, topic_slug, mode='book'|'report'|None, allow_fallbacks=True)
      -> (text, Path|None)
    """
    m: DocMode = _coerce_mode(mode)
    candidates: List[Path] = []

    # 1) topic 우선
    if filename:
        candidates.append(outline_path(filename, root_dir=root_dir, topic_slug=topic_slug, mode=m))
    if allow_fallbacks:
        candidates.extend([
            outline_path(_default_outline_name(m), root_dir=root_dir, topic_slug=topic_slug, mode=m),
            outline_path("outline.md", root_dir=root_dir, topic_slug=topic_slug, mode=m),
        ])

    # 2) root 폴백
    if filename:
        candidates.append(outline_path(filename, root_dir=root_dir, topic_slug=None, mode=m))
    if allow_fallbacks:
        candidates.extend([
            outline_path(_default_outline_name(m), root_dir=root_dir, topic_slug=None, mode=m),
            outline_path("outline.md", root_dir=root_dir, topic_slug=None, mode=m),
        ])

    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8"), p
            except Exception:
                continue
    return "", None


def is_written(
    title: str,
    *,
    mode: Optional[str | DocMode] = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> bool:
    return path_for_title(title, mode=mode, root_dir=root_dir, topic_slug=topic_slug).exists()
