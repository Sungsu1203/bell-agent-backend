# utils/outline.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Mapping, Any, List, Tuple

from core.config import DOC_MODE, PROJECT_ROOT, DocMode
from core.paths import (
    path_for_title,
    outline_path as outline_path,
    read_outline as read_outline,
    get_content_dir,
    is_written,
    _coerce_mode,
)
from utils.text_utils import slugify, slugify as _slugify

__all__ = [
    "outline_path",
    "read_outline",
    "parse_outline_headings",
    "list_outline_headings",
    "pick_outline_filename",
    "get_topic_outline_text",
    "outline_default_filename",
    "normalize_outline_headings",
    "save_outline",
    "next_unwritten_title",
    "title_by_index",
]

# ─────────────────────────────────────────────────────────────
# 파일명 선택 & 아웃라인 로딩
# ─────────────────────────────────────────────────────────────

def pick_outline_filename(user_text: Optional[str], doc_mode: DocMode = DOC_MODE) -> str:
    text = (user_text or "")
    if re.search(r"(?:ai|인공지능)?\s*.*책.*(목차|outline)", text, flags=re.I):
        return "outline_book.md"
    if re.search(r"(보고서|report).*(목차|outline)", text, flags=re.I):
        return "outline_report.md"
    return "outline_report.md" if doc_mode == "report" else "outline.md"

def get_topic_outline_text(
    state: Mapping[str, Any],
    root_dir: str = PROJECT_ROOT,
    doc_mode: DocMode = DOC_MODE,
) -> str:
    default_fname = "outline_report.md" if doc_mode == "report" else "outline.md"
    fname = state.get("outline_fname") or default_fname
    txt, _path = read_outline(
        filename=fname,
        root_dir=root_dir,
        topic_slug=state.get("topic_slug"),
        mode=doc_mode,
        allow_fallbacks=True,
    )
    logger.debug("Loaded outline text (fname=%s, path=%s, chars=%d)", fname, getattr(_path, "as_posix", lambda: _path)(), len(txt or ""))
    return txt or ""

# ─────────────────────────────────────────
# 대체: 시그니처를 Optional[str] 허용으로 변경
def title_by_index(outline_text: Optional[str], idx: int) -> Optional[str]:
    """
    목차 본문에서 'N. 제목' 또는 'N) 제목' 형태의 라인을 찾아
    'N. 제목' 형태로 정규화한 문자열을 반환한다.
    - Markdown 헤더(### 4. ...)도 허용
    - outline_text 가 None 이어도 안전하게 처리
    """
    if not outline_text or not isinstance(idx, int):
        return None

    pat = re.compile(r'^\s*(?:#{1,6}\s*)?(?P<num>\d+)\s*[.)]\s*(?P<title>.+?)\s*$')
    for raw in outline_text.splitlines():
        m = pat.match(raw)
        if not m:
            continue
        try:
            n = int(m.group("num"))
        except Exception:
            continue
        if n == idx:
            title = (m.group("title") or "").strip().strip("#").strip()
            return f"{idx}. {title}" if title else None
    return None

# ─────────────────────────────────────────────────────────────
# 경로 & 파일명 규칙
# ─────────────────────────────────────────────────────────────

def outline_default_filename(mode: DocMode) -> str:
    """모드에 따른 기본 outline 파일명."""
    return "outline_report.md" if mode == "report" else "outline.md"

def save_outline(
    text: str,
    *,
    filename: str,
    root_dir: str,
    topic_slug: Optional[str],
    mode: DocMode,
    backup: bool = True,
) -> str:
    """
    목차 파일을 저장하고 저장 경로를 문자열로 반환.
    기존 파일이 있으면 .bak(타임스탬프) 백업.
    저장 경로: {root}/data/{topic_slug}/{filename} (토픽 있으면),
              아니면 {root}/{filename}
    """
    out_path = outline_path(root_dir=root_dir, topic_slug=topic_slug, filename=filename)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if backup and out_path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = out_path.with_suffix(out_path.suffix + f".{ts}.bak")
        try:
            bak.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
            logger.debug("Outline backup created: %s", bak.as_posix())
        except Exception as e:
            logger.warning("Outline backup failed: %s (%s)", bak.as_posix(), e)

    out_path.write_text(text, encoding="utf-8")
    logger.info("Outline saved → %s", out_path.as_posix())
    return str(out_path)

# ─────────────────────────────────────────────────────────────
# 목차 텍스트 정규화/파싱
# ─────────────────────────────────────────────────────────────

_def_num_head = re.compile(r"(?m)^\s*(\d+)\.\s+(.+?)\s*$")
_def_bullet   = re.compile(r"(?m)^\s*-\s+(.+?)\s*$")

def normalize_outline_headings(s: str) -> str:
    """
    - '### 세부 목차 제안' 제거
    - '1. 제목' → '## 1. 제목'
    - '- 제목'  → '## n. 제목' (연속 불릿을 H2로 승격하며 번호 부여)
    """
    if not isinstance(s, str) or not s.strip():
        return s

    # 1) 제목 블럭 제거
    s = re.sub(r'(?m)^\s*###\s*세부\s*목차\s*제안\s*$', '', s).strip()

    # 2) 숫자 리스트를 H2로 승격
    s = _def_num_head.sub(r'## \1. \2', s)

    # 3) 불릿을 H2로 승격 + 번호 부여
    lines, out, n = s.splitlines(), [], 1
    for ln in lines:
        m = _def_bullet.match(ln)
        if m:
            out.append(f"## {n}. {m.group(1).strip()}")
            n += 1
        else:
            out.append(ln)
    return "\n".join(out)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.M)

def parse_outline_headings(outline_text: str) -> List[Tuple[int, str]]:
    items: List[Tuple[int, str]] = []
    for m in _HEADING_RE.finditer(outline_text or ""):
        level = len(m.group(1))
        title = (m.group(2) or "").strip()
        if title:
            items.append((level, title))
    return items

def list_outline_headings(outline_text: str) -> List[str]:
    # 모든 레벨 헤딩을 가져오되, 앞번호(예: "1.", "1)")는 제거
    return [
        re.sub(r"^\d+[.)]\s*", "", title).strip()
        for _lvl, title in parse_outline_headings(outline_text)
        if title
    ]

# ─────────────────────────────────────────────────────────────
# 파일명 & 미작성 타이틀 선택
# ─────────────────────────────────────────────────────────────

def _drafts_dir(
    *,
    root_dir: str,
    topic_slug: Optional[str],
    mode: DocMode,
) -> Path:
    """
    초안 저장 디렉터리 규칙:
      {root}/data/{topic_slug}/{sections|chapters}
    """
    base = Path(root_dir) / "data" / (topic_slug or "default")
    sub  = "sections" if mode == "report" else "chapters"
    p = base / sub
    p.mkdir(parents=True, exist_ok=True)
    return p

def next_unwritten_title(
    outline_text: str,
    *,
    mode: DocMode,
    root_dir: str,
    topic_slug: Optional[str],
) -> Optional[str]:
    """
    목차(H2) 순서대로 살펴보면서 아직 초안 파일(.md)이 없는 첫 제목을 반환.
    존재 판정 규칙:
      {root}/data/{topic_slug}/{sections|chapters}/{slug}.md
    """
    titles = list_outline_headings(outline_text)
    if not titles:
        logger.debug("No titles parsed from outline; nothing to write next.")
        return None

    drafts_dir = _drafts_dir(root_dir=root_dir, topic_slug=topic_slug, mode=mode)
    for t in titles:
        fn = f"{_slugify(t)}.md"
        if not (drafts_dir / fn).exists():
            logger.debug("Next unwritten title selected: %s (missing: %s)", t, fn)
            return t

    logger.info("All outline titles appear to have drafts already.")
    return None
