# utils/outline.py
from __future__ import annotations
import re
from typing import Optional, Mapping, Any, Tuple
from content_utils import read_outline
from core.config import DOC_MODE, PROJECT_ROOT  # 전역 설정 (순환 import 없음이 전제)
from core.config import DocMode  # Literal["book","report"]
from typing import List, Tuple
from pathlib import Path
from utils.text_utils import slugify as _slugify

from datetime import datetime
from core.paths import path_for_title, outline_path as outline_path, read_outline as read_outline

__all__ = [
    "outline_path",
    "read_outline",
    "parse_outline_headings",
    "list_outline_headings",
]


def pick_outline_filename(user_text: Optional[str], doc_mode: DocMode = DOC_MODE) -> str:
    text = (user_text or "")
    if re.search(r"(?:ai|인공지능)?\s*.*책.*(목차|outline)", text, flags=re.I):
        return "outline_book.md"
    if re.search(r"(보고서|report).*(목차|outline)", text, flags=re.I):
        return "outline_report.md"
    return "outline_report.md" if doc_mode == "report" else "outline.md"

def get_topic_outline_text(
    state: Mapping[str, Any],
    root_dir: str = PROJECT_ROOT,      # ← 기본값 제공
    doc_mode: DocMode = DOC_MODE,      # ← 기본값 제공
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
    return txt or ""


# ─────────────────────────────────────────────────────────────
# 경로 & 파일명 규칙
# ─────────────────────────────────────────────────────────────

def outline_default_filename(mode: DocMode) -> str:
    """모드에 따른 기본 outline 파일명."""
    return "outline_report.md" if mode == "report" else "outline.md"


# def outline_path(
#     *,
#     root_dir: str,
#     topic_slug: Optional[str],
#     filename: str,
#     ensure_dir: bool = False,
# ) -> Path:
#     """
#     outline 저장/조회 기본 경로:
#       {root_dir}/data/{topic_slug}/{filename}
#     topic_slug가 없으면 프로젝트 루트 바로 아래 {root_dir}/{filename}
#     """
#     if topic_slug:
#         p = Path(root_dir) / "data" / topic_slug
#     else:
#         p = Path(root_dir)

#     if ensure_dir:
#         p.mkdir(parents=True, exist_ok=True)

#     return p / filename


# ─────────────────────────────────────────────────────────────
# 목차 I/O
# ─────────────────────────────────────────────────────────────

# def read_outline(
#     *,
#     filename: str,
#     root_dir: str,
#     topic_slug: Optional[str],
#     mode: DocMode,
#     allow_fallbacks: bool = True,
# ) -> Tuple[str, Optional[Path]]:
#     """
#     목차 텍스트와 사용된 실제 파일 경로를 반환.
#     탐색 순서:
#       1) {root}/data/{topic_slug}/{filename}
#       2) {root}/{filename}
#       (allow_fallbacks=True면)
#       3) 모드 기본 파일명으로 1) → 2) 순서 재시도
#     찾지 못하면 ("", None)
#     """
#     # 1) 토픽 스코프 우선
#     p1 = outline_path(root_dir=root_dir, topic_slug=topic_slug, filename=filename, ensure_dir=False)
#     if p1.exists():
#         return p1.read_text(encoding="utf-8"), p1

#     # 2) 프로젝트 루트
#     p2 = Path(root_dir) / filename
#     if p2.exists():
#         return p2.read_text(encoding="utf-8"), p2

#     if allow_fallbacks:
#         # 3) 모드 기본 파일명으로 재시도
#         fallback = outline_default_filename(mode)
#         if fallback != filename:
#             # 3-1) 토픽 스코프
#             pf1 = outline_path(root_dir=root_dir, topic_slug=topic_slug, filename=fallback, ensure_dir=False)
#             if pf1.exists():
#                 return pf1.read_text(encoding="utf-8"), pf1
#             # 3-2) 루트
#             pf2 = Path(root_dir) / fallback
#             if pf2.exists():
#                 return pf2.read_text(encoding="utf-8"), pf2

#     return "", None


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
    out_path = outline_path(root_dir=root_dir, topic_slug=topic_slug, filename=filename, ensure_dir=True)

    if backup and out_path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = out_path.with_suffix(out_path.suffix + f".{ts}.bak")
        try:
            bak.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception as e:
            print(f"[WARN] outline backup failed: {e}")

    out_path.write_text(text, encoding="utf-8")
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


_h2_pat = re.compile(r"(?m)^\s*##\s+(.*)$")

def list_outline_headings(outline_text: str) -> List[str]:
    """
    목차의 H2 라인을 모두 뽑아 제목 리스트로 반환.
    '## 1. 제목' 처럼 번호가 있으면 번호는 제거해서 반환.
    """
    titles: List[str] = []
    for m in _h2_pat.finditer(outline_text or ""):
        raw = (m.group(1) or "").strip()
        # '1. 제목' → '제목'
        raw = re.sub(r"^\d+\.\s*", "", raw).strip()
        if raw:
            titles.append(raw)
    return titles


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
        return None

    drafts_dir = _drafts_dir(root_dir=root_dir, topic_slug=topic_slug, mode=mode)
    for t in titles:
        fn = f"{_slugify(t)}.md"
        if not (drafts_dir / fn).exists():
            return t
    return None

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.M)

def parse_outline_headings(outline_text: str) -> List[Tuple[int, str]]:
    items: List[Tuple[int, str]] = []
    for m in _HEADING_RE.finditer(outline_text or ""):
        level = len(m.group(1))
        title = (m.group(2) or "").strip()
        if title:
            items.append((level, title))
    return items

# def is_written(
#     title: str,
#     *,
#     mode: Optional[str] = None,
#     root_dir: Optional[str | Path] = None,
#     topic_slug: Optional[str] = None,
# ) -> bool:
#     return path_for_title(title, mode=mode, root_dir=root_dir, topic_slug=topic_slug).exists()
