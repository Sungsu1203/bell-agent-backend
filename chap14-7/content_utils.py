# content_utils.py

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

import logging
logger = logging.getLogger(__name__)

from core.config import DocMode, DOC_MODE

from core.paths import (
    get_content_dir, chapter_filepath, section_filepath, path_for_title,
    get_outline_dir, outline_path, is_written, _coerce_mode         # _coerce_mode 재사용
)

def _write_text(path: Path, content: str, *, backup: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        bak = path.with_suffix(path.suffix + f".{os.getpid()}.bak")
        try:
            bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            logger.debug("backup written: %s -> %s", path, bak)
        except Exception:
            logger.warning("backup failed: %s", bak, exc_info=True)
    try:
        path.write_text(content or "", encoding="utf-8")
        logger.info("draft saved: %s (bytes=%d)", path, len((content or "").encode("utf-8")))
    except Exception:
        logger.exception("write failed: %s", path)
        raise
    return path

def save_md_draft(
    title: str,
    content: str,
    *,
    # mode: str = "book",
    mode: DocMode | str | None = None,
    root_dir: str,
    topic_slug: str | None = None,
    backup: bool = True,
) -> str:
    """
    메인 코드 기대 시그니처:
      (title, content, *, mode="book", root_dir, topic_slug=None, ...) -> str
    """
    m: DocMode = _coerce_mode(mode)
    p = path_for_title(title, mode=m, root_dir=root_dir, topic_slug=topic_slug)
    out = _write_text(p, content, backup=backup)
    return str(out.resolve())

def save_chapter(
    title: str,
    content: str,
    *,
    root_dir: str,
    topic_slug: Optional[str] = None,
    backup: bool = True,
) -> str:
    p = chapter_filepath(title, root_dir=root_dir, topic_slug=topic_slug)
    out = _write_text(p, content, backup=backup)
    return str(out.resolve())

def save_section(
    title: str,
    content: str,
    *,
    root_dir: str,
    topic_slug: Optional[str] = None,
    backup: bool = True,
) -> str:
    p = section_filepath(title, root_dir=root_dir, topic_slug=topic_slug)
    out = _write_text(p, content, backup=backup)
    return str(out.resolve())

# =============================================================================
# 초안 읽기/목록/리네이밍/이동/머지 (보조: 반환 타입은 유지)
# =============================================================================

def read_draft(
    title: str,
    *,
    mode: DocMode | str | None = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> Tuple[str, Path]:
    m: DocMode = _coerce_mode(mode)
    p = path_for_title(title, mode=m, root_dir=root_dir, topic_slug=topic_slug)
    if not p.exists():
        logger.debug("read_draft: not found (title=%s, path=%s)", title, p)
        return "", p
    try:
        txt = p.read_text(encoding="utf-8")
        logger.debug("read_draft: loaded (title=%s, bytes=%d)", title, len(txt.encode("utf-8")))
        return txt, p
    except Exception:
        logger.exception("read_draft failed: %s", p)
        return "", p


def list_draft_paths(
    *,
    mode: DocMode | str | None = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> List[Path]:
    m: DocMode = _coerce_mode(mode)
    d = get_content_dir(m, root_dir=root_dir, topic_slug=topic_slug)
    if not d.exists():
        logger.debug("list_draft_paths: base dir not exists: %s", d)
        return []
    out = sorted(p for p in d.glob("*.md"))
    logger.debug("list_draft_paths: %d files in %s", len(out), d)
    return out

def rename_draft_title(
    old_title: str,
    new_title: str,
    *,
    mode: DocMode | str | None = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    overwrite: bool = False,
    backup: bool = True,
) -> Path:
    m: DocMode = _coerce_mode(mode)
    src = path_for_title(old_title, mode=m, root_dir=root_dir, topic_slug=topic_slug)
    dst = path_for_title(new_title, mode=m, root_dir=root_dir, topic_slug=topic_slug)
    if not src.exists():
        raise FileNotFoundError(f"source not found: {src}")
    if dst.exists():
        if not overwrite:
            raise ValueError(f"destination exists: {dst}")
        if backup:
            try:
                _write_text(dst.with_suffix(dst.suffix + ".pre-rename.bak"),
                            dst.read_text(encoding="utf-8"), backup=False)
            except Exception:
                logger.warning("pre-rename backup failed: %s", dst, exc_info=True)
    src.rename(dst)
    logger.info("draft renamed: %s -> %s", src, dst)
    return dst


def move_draft_between_topics(
    title: str,
    *,
    mode: DocMode | str | None = None,
    root_dir: Optional[str | Path] = None,
    src_topic_slug: Optional[str] = None,
    dst_topic_slug: Optional[str] = None,
    overwrite: bool = False,
    backup: bool = True,
) -> Path:
    if src_topic_slug == dst_topic_slug:
        raise ValueError("src_topic_slug and dst_topic_slug are the same.")
    m: DocMode = _coerce_mode(mode)
    src = path_for_title(title, mode=m, root_dir=root_dir, topic_slug=src_topic_slug)
    dst = path_for_title(title, mode=m, root_dir=root_dir, topic_slug=dst_topic_slug)
    if not src.exists():
        raise FileNotFoundError(f"source not found: {src}")
    if dst.exists():
        if not overwrite:
            raise ValueError(f"destination exists: {dst}")
        if backup:
            try:
                _write_text(dst.with_suffix(dst.suffix + ".pre-move.bak"),
                            dst.read_text(encoding="utf-8"), backup=False)
            except Exception:
                logger.warning("pre-move backup failed: %s", dst, exc_info=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dst)
    logger.info("draft moved between topics: %s -> %s", src, dst)
    return dst


def merge_drafts(
    src_title: str,
    dst_title: str,
    *,
    mode: Optional[str] = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    how: str = "append",           # "append" | "prepend" | "replace"
    heading: Optional[str] = None,
    separator: Optional[str] = None,
    backup: bool = True,
) -> Path:
    valid = {"append", "prepend", "replace"}
    if how not in valid:
        raise ValueError(f"how must be one of: {', '.join(sorted(valid))}")

    sep = separator if separator is not None else "\n\n---\n\n"

    src_txt, src_path = read_draft(src_title, mode=mode, root_dir=root_dir, topic_slug=topic_slug)
    dst_txt, dst_path = read_draft(dst_title, mode=mode, root_dir=root_dir, topic_slug=topic_slug)

    if not src_path.exists():
        raise FileNotFoundError(f"source draft not found: {src_path}")

    dst_dir = dst_path.parent
    dst_dir.mkdir(parents=True, exist_ok=True)

    if backup and dst_path.exists():
        try:
            _write_text(dst_path.with_suffix(dst_path.suffix + ".pre-merge.bak"), dst_txt, backup=False)
        except Exception:
            logger.warning("pre-merge backup failed: %s", dst_path, exc_info=True)

    if how == "replace":
        new_txt = src_txt
    else:
        block = (f"{heading}\n\n{src_txt}" if heading else src_txt)
        if how == "append":
            new_txt = (dst_txt + (sep if dst_txt else "")) + block
        else:  # prepend
            new_txt = block + (sep if dst_txt else "") + dst_txt

    out = _write_text(dst_path, new_txt, backup=False)
    logger.info(
        "draft merged: %s (%s) -> %s [how=%s, heading=%s, bytes=%d]",
        src_path, src_title, dst_path, how, bool(heading), len(new_txt.encode("utf-8"))
    )
    return out
