# content\api.py
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from core.config import DocMode, DOC_MODE

from core.paths import (
    get_content_dir, chapter_filepath, section_filepath, path_for_title,
    get_outline_dir, outline_path, is_written, _coerce_mode         # _coerce_mode 재사용
)
from utils.outline import (
    read_outline, save_outline, parse_outline_headings, list_outline_headings,
    next_unwritten_title,
)
from utils.text_utils import slugify, section_slugify


__all__ = [
    # re-export
    "slugify", "section_slugify",
    "get_content_dir", "chapter_filepath", "section_filepath", "path_for_title",
    "get_outline_dir", "outline_path",
    "read_outline", "save_outline", "parse_outline_headings", "list_outline_headings",
    "is_written", "next_unwritten_title",
    # content_utils 고유 구현(초안 저장/조회 등)도 함께 노출
    "save_md_draft", "save_chapter", "save_section", "read_draft",
    "list_draft_paths", "rename_draft_title", "move_draft_between_topics",
    "merge_drafts",
]

def _write_text(path: Path, content: str, *, backup: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        # PID를 덧붙여 충돌을 줄임
        bak = path.with_suffix(path.suffix + f".{os.getpid()}.bak")
        try:
            bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    path.write_text(content or "", encoding="utf-8")
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
    # mode: Optional[str] = None,
    mode: DocMode | str | None = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> Tuple[str, Path]:
    """
    초안 내용을 읽어서 (text, path)를 반환. 존재하지 않으면 ("" , 예상 경로) 반환.
    """
    m: DocMode = _coerce_mode(mode)
    p = path_for_title(title, mode=m, root_dir=root_dir, topic_slug=topic_slug)
    if not p.exists():
        return "", p
    try:
        return p.read_text(encoding="utf-8"), p
    except Exception:
        return "", p

def list_draft_paths(
    *,
    # mode: Optional[str] = None,
    mode: DocMode | str | None = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> List[Path]:
    """
    현재 세션(토픽)의 모든 초안 경로 리스트.
    """
    m: DocMode = _coerce_mode(mode)
    d = get_content_dir(m, root_dir=root_dir, topic_slug=topic_slug)
    return sorted(p for p in d.glob("*.md"))

def rename_draft_title(
    old_title: str,
    new_title: str,
    *,
    # mode: Optional[str] = None,
    mode: DocMode | str | None = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    overwrite: bool = False,
    backup: bool = True,
) -> Path:
    """
    초안 파일명을 (제목 기준) 변경.
    - overwrite=False일 때 대상이 이미 있으면 ValueError
    """
    m: DocMode = _coerce_mode(mode)
    src = path_for_title(old_title, mode=m, root_dir=root_dir, topic_slug=topic_slug)
    dst = path_for_title(new_title, mode=m, root_dir=root_dir, topic_slug=topic_slug)
    if not src.exists():
        raise FileNotFoundError(f"source not found: {src}")
    if dst.exists() and not overwrite:
        raise ValueError(f"destination exists: {dst}")
    if backup and dst.exists():
        _ = _write_text(dst.with_suffix(dst.suffix + ".pre-rename.bak"), dst.read_text(encoding="utf-8"), backup=False)
    src.rename(dst)
    return dst

def move_draft_between_topics(
    title: str,
    *,
    # mode: Optional[str] = None,
    mode: DocMode | str | None = None,
    root_dir: Optional[str | Path] = None,
    src_topic_slug: Optional[str] = None,
    dst_topic_slug: Optional[str] = None,
    overwrite: bool = False,
    backup: bool = True,
) -> Path:
    """
    같은 모드 내에서 topic_slug 폴더 간 초안을 이동.
    """
    if src_topic_slug == dst_topic_slug:
        raise ValueError("src_topic_slug and dst_topic_slug are the same.")
    m: DocMode = _coerce_mode(mode)
    src = path_for_title(title, mode=m, root_dir=root_dir, topic_slug=src_topic_slug)
    dst = path_for_title(title, mode=m, root_dir=root_dir, topic_slug=dst_topic_slug)
    if not src.exists():
        raise FileNotFoundError(f"source not found: {src}")
    if dst.exists() and not overwrite:
        raise ValueError(f"destination exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if backup and dst.exists():
        _ = _write_text(dst.with_suffix(dst.suffix + ".pre-move.bak"), dst.read_text(encoding="utf-8"), backup=False)
    src.replace(dst)
    return dst

def merge_drafts(
    src_title: str,
    dst_title: str,
    *,
    mode: Optional[str] = None,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    how: str = "append",           # "append" | "prepend" | "replace"
    heading: Optional[str] = None, # 합칠 때 소제목을 붙이고 싶다면
    separator: Optional[str] = None,
    backup: bool = True,
) -> Path:
    """
    src_title의 내용을 dst_title로 합친다.
    - how:
      - append  : dst + SEP + (heading?) + src
      - prepend : (heading?) + src + SEP + dst
      - replace : dst 내용을 src로 교체
    - heading: 예) "### 추가 자료" 같은 마크다운 헤딩 문자열
    - separator: 기본은 "\n\n---\n\n"
    반환: 병합 후 저장된 dst 경로
    """
    sep = separator if separator is not None else "\n\n---\n\n"

    src_txt, src_path = read_draft(src_title, mode=mode, root_dir=root_dir, topic_slug=topic_slug)
    dst_txt, dst_path = read_draft(dst_title, mode=mode, root_dir=root_dir, topic_slug=topic_slug)

    if not src_path.exists():
        raise FileNotFoundError(f"source draft not found: {src_path}")

    dst_dir = dst_path.parent
    dst_dir.mkdir(parents=True, exist_ok=True)

    if backup and dst_path.exists():
        _ = _write_text(dst_path.with_suffix(dst_path.suffix + ".pre-merge.bak"), dst_txt, backup=False)

    if how == "replace":
        new_txt = src_txt
    else:
        block = (f"{heading}\n\n{src_txt}" if heading else src_txt)
        if how == "append":
            new_txt = (dst_txt + (sep if dst_txt else "")) + block
        elif how == "prepend":
            new_txt = block + (sep if dst_txt else "") + dst_txt
        else:
            raise ValueError("how must be one of: append | prepend | replace")

    return _write_text(dst_path, new_txt, backup=False)