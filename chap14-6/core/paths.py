from __future__ import annotations
import os, re, hashlib
from pathlib import Path
from datetime import datetime
from utils.text_utils import slugify as _slugify
from typing import List, Optional, Tuple, cast
from utils.text_utils import slugify, slugify as _slugify, section_slugify
from core.config import DOC_MODE, DocMode  # ← 추가

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

# def _slugify(title: str) -> str:
#     s = (title or "").strip().lower()
#     s = re.sub(r"[^\w\-가-힣\s]", "", s)
#     s = re.sub(r"\s+", "-", s)
#     return s or "untitled"

# def _base_dir_for_mode(mode: Optional[str] = None) -> str:
#     m = (mode or _doc_mode())
#     return "sections" if m == "report" else "chapters"

def _base_dir_for_mode(mode: Optional[DocMode] = None) -> str:
    m: DocMode = mode or DOC_MODE
    return "sections" if m == "report" else "chapters"

def get_content_dir(
    mode: Optional[DocMode] = None,
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> Path:
    root = Path(root_dir) if root_dir else Path.cwd()
    # base = base_dir or _base_dir_for_mode(mode)
    base = base_dir or _base_dir_for_mode(mode)
    p = root / base
    if topic_slug:
        p = p / topic_slug
    p.mkdir(parents=True, exist_ok=True)
    return p

def path_for_title(
    title: str,
    *,
    mode: Optional[DocMode] = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> Path:
    # m = (mode or _doc_mode())
    m: DocMode = mode or DOC_MODE
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

# def _default_outline_name(mode: Optional[DocMode] = None) -> str:
#     # m = (mode or _doc_mode())
#     m: DocMode = mode or DOC_MODE
#     return "outline_report.md" if m == "report" else "outline_book.md"

def get_outline_dir(
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> Path:
    root = Path(root_dir) if root_dir else Path.cwd()
    d = root / "outlines"
    if topic_slug:
        d = d / topic_slug
    d.mkdir(parents=True, exist_ok=True)
    return d

def outline_path(
    filename: Optional[str] = None,
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    mode: Optional[DocMode] = None,
) -> Path:
    fname = (filename or _default_outline_name(mode))
    return get_outline_dir(root_dir=root_dir, topic_slug=topic_slug) / fname

def _coerce_mode(mode: Optional[str | DocMode]) -> DocMode:
    """문자열/None을 DocMode로 정규화."""
    if mode in ("book", "report"):
        return cast(DocMode, mode)
    return DOC_MODE

def _default_outline_name(mode: Optional[str | DocMode] = None) -> str:
    m: DocMode = _coerce_mode(mode)
    return "outline_report.md" if m == "report" else "outline_book.md"

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
    우선순위:
      topic/outlines/<filename?> → topic/outline_<mode>.md → topic/outline.md
      → root/outlines/<same 순서>
    """
    m: DocMode = _coerce_mode(mode)
    tried: List[Path] = []
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
        tried.append(p)
        if p.exists():
            try:
                return p.read_text(encoding="utf-8"), p
            except Exception:
                pass

    return "", None

# def read_outline(
#     filename: str,
#     *,
#     root_dir: str,
#     topic_slug: str | None,
#     mode: str = "book",
#     allow_fallbacks: bool = True,
# ) -> Tuple[str, Optional[Path]]:
#     """
#     메인 코드 기대 시그니처:
#       (filename, *, root_dir, topic_slug, mode="book", allow_fallbacks=True) -> (text, Path|None)
#     우선순위:
#       topic/outlines/<filename?> → topic/outline_<mode>.md → topic/outline.md
#       → root/outlines/<same 순서>
#     """
#     tried: List[Path] = []
#     m = mode or _doc_mode()
#     candidates: List[Path] = []

#     # 1) topic 우선
#     if filename:
#         candidates.append(outline_path(filename, root_dir=root_dir, topic_slug=topic_slug, mode=m))
#     if allow_fallbacks:
#         candidates.extend([
#             outline_path(_default_outline_name(m), root_dir=root_dir, topic_slug=topic_slug, mode=m),
#             outline_path("outline.md", root_dir=root_dir, topic_slug=topic_slug, mode=m),
#         ])

#     # 2) root 폴백
#     if filename:
#         candidates.append(outline_path(filename, root_dir=root_dir, topic_slug=None, mode=m))
#     if allow_fallbacks:
#         candidates.extend([
#             outline_path(_default_outline_name(m), root_dir=root_dir, topic_slug=None, mode=m),
#             outline_path("outline.md", root_dir=root_dir, topic_slug=None, mode=m),
#         ])

#     for p in candidates:
#         tried.append(p)
#         if p.exists():
#             try:
#                 return p.read_text(encoding="utf-8"), p
#             except Exception:
#                 pass

#     return "", None

def is_written(
    title: str,
    *,
    mode: Optional[DocMode] = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> bool:
    return path_for_title(title, mode=mode, root_dir=root_dir, topic_slug=topic_slug).exists()