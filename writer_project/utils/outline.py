# utils/outline.py — dynamic config access (v2025-10-27)
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Mapping, Any, List, Tuple, TYPE_CHECKING, Iterable, Set
import os

# ─────────────────────────────────────────────────────────────
# Dynamic config access (avoid static binding to CFG/DOC_MODE)
# ─────────────────────────────────────────────────────────────
import core.config as config  # access runtime-updated values via config.<attr>

if TYPE_CHECKING:  # type-only import; no runtime binding of values
    from core.config import DocMode  # noqa: F401
else:  # runtime fallback literal type (keeps signatures stable)
    from typing import Literal as _Literal
    DocMode = _Literal["report", "book"]  # type: ignore

from core.paths import (
    path_for_title,
    outline_path as outline_path,
    read_outline as read_outline,
    get_content_dir,
    is_written,
    _coerce_mode,  # (하위호환 유지)
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
# Internal helpers (config/env with safe defaults; runtime-evaluated)
# ─────────────────────────────────────────────────────────────
_DEF_MODE: "DocMode" = "report"  # default if config.DOC_MODE missing

_DEF_REPORT_NAME = "outline_report.md"
_DEF_BOOK_NAME   = "outline_book.md"

def _cfg_str(name: str, default: str) -> str:
    """CFG → ENV → default (공백은 무시)"""
    try:
        v = getattr(config, name)  # reload_config() 이후 최신값
        if v is not None and str(v).strip():
            return str(v).strip()
    except Exception:
        pass
    ev = os.getenv(name, "")
    return ev.strip() or default

def _cfg_bool(name: str, default: bool) -> bool:
    try:
        v = getattr(config, name)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        if v is not None:
            return bool(v)
    except Exception:
        pass
    ev = os.getenv(name)
    return (ev or "").strip().lower() in ("1", "true", "yes", "on") if ev is not None else default

def _cfg_doc_mode() -> DocMode:
    """
    DOC_MODE은 CFG 우선, 없으면 ENV.DOC_MODE, 최종 기본 'report'.
    값은 'report'/'book' 이외는 강제로 'book'으로 수렴(이 파일 내 일관성 목적).
    """
    try:
        dm = getattr(config, "DOC_MODE", None)
        if isinstance(dm, str) and dm.strip():
            return "report" if dm.strip().lower() == "report" else "book"
    except Exception:
        pass
    env = (os.getenv("DOC_MODE") or "").strip().lower()
    if env:
        return "report" if env == "report" else "book"
    return _DEF_MODE

def _outline_report_name() -> str:
    # CFG.OUTLINE_REPORT_FILENAME → ENV.OUTLINE_REPORT_FILENAME → 기본
    return _cfg_str("OUTLINE_REPORT_FILENAME", _DEF_REPORT_NAME)

def _outline_book_name() -> str:
    # CFG.OUTLINE_BOOK_FILENAME → ENV.OUTLINE_BOOK_FILENAME → 기본
    return _cfg_str("OUTLINE_BOOK_FILENAME", _DEF_BOOK_NAME)

def _get_doc_mode() -> DocMode:
    # 런타임 평가(환경/CFG 갱신 반영)
    return _cfg_doc_mode()


def _get_project_root() -> str:
    try:
        return getattr(config, "PROJECT_ROOT", ".")
    except Exception:
        return "."


# ─────────────────────────────────────────────────────────────
# DocMode coercion (dynamic, uses config.DOC_MODE when None)
# ─────────────────────────────────────────────────────────────

def _coerce_doc_mode(val: Optional[DocMode]) -> DocMode:
    """
    안전한 DocMode 보정. None → 글로벌(config.DOC_MODE), 그 외 report/book만 허용.
    동적 접근을 위해 config에서 직접 참조합니다.
    """
    if val is None:
        return _get_doc_mode()
    return "report" if val == "report" else "book"


# ─────────────────────────────────────────────────────────────
# 파일명 선택 & 아웃라인 로딩
# ─────────────────────────────────────────────────────────────

def pick_outline_filename(user_text: Optional[str], doc_mode: Optional[DocMode] = None) -> str:
    """
    사용자의 텍스트 힌트와 문서 모드에 따라 기본 outline 파일명을 결정.
    - 기본값(report): outline_report.md
    - book: outline.md
    - 텍스트에 '보고서|report' + '목차|outline' → outline_report.md
    - 텍스트에 '(AI|인공지능) ... 책 ... (목차|outline)' → outline_book.md
    """
    dm: DocMode = _coerce_doc_mode(doc_mode)
    text = (user_text or "")
    # 동적 기본 파일명(ENV/CFG 반영)
    book_name   = _outline_book_name()
    report_name = _outline_report_name()
    if re.search(r"(?:ai|인공지능)?\s*.*책.*(목차|outline)", text, flags=re.I):
        return book_name
    if re.search(r"(보고서|report).*(목차|outline)", text, flags=re.I):
        return report_name
    return report_name if dm == "report" else book_name


def get_topic_outline_text(
    state: Mapping[str, Any],
    root_dir: Optional[str] = None,
    doc_mode: Optional[DocMode] = None,
) -> str:
    """
    토픽별 아웃라인 텍스트 로드. 경로 로깅은 None-safe.
    동적 접근: PROJECT_ROOT, DOC_MODE는 config에서 직접 조회.
    """
    dm: DocMode = _coerce_doc_mode(doc_mode)
    rd = root_dir or _get_project_root()

    # 동적 기본 파일명(ENV/CFG 반영)
    default_fname = _outline_report_name() if dm == "report" else _outline_book_name()
    fname = state.get("outline_fname") or default_fname

    txt, p = read_outline(
        filename=fname,
        root_dir=rd,
        topic_slug=state.get("topic_slug"),
        mode=dm,
        allow_fallbacks=True,
    )

    # None-safe 경로 문자열
    try:
        if p is None:
            p_str = "(none)"
        else:
            p_str = p.as_posix() if hasattr(p, "as_posix") else str(p)
    except Exception:
        p_str = "(unavailable)"

    logger.debug(
        "Loaded outline text (fname=%s, path=%s, chars=%d)",
        fname, p_str, len(txt or "")
    )
    return txt or ""


# ─────────────────────────────────────────────────────────────
# 대체: 시그니처를 Optional[str] 허용으로 변경
# ─────────────────────────────────────────────────────────────

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
    return _outline_report_name() if mode == "report" else _outline_book_name()


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
_def_bullet = re.compile(r"(?m)^\s*-\s+(.+?)\s*$")


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

def next_unwritten_title(
    outline_text: str,
    *,
    mode: DocMode,
    root_dir: str,
    topic_slug: Optional[str],
    excluded_titles: Optional[Iterable[str]] = None, # <--- 이 라인을 추가
) -> Optional[str]:
    """
    목차(H2) 순서대로 살펴보면서 아직 초안 파일(.md)이 없는 첫 제목을 반환.
    존재 판정 규칙:
      {root}/data/{topic_slug}/{sections|chapters}/{slug}.md
    """
    titles = list_outline_headings(outline_text)
    # 완료된(혹은 제외할) 제목 집합
    _excluded: Set[str] = {str(t).strip() for t in (excluded_titles or []) if str(t).strip()}
    if not titles:
        logger.debug("No titles parsed from outline; nothing to write next.")
        return None

    # ✅ core.paths 규칙을 100% 따르기 위해 is_written()만 사용
    for t in titles:
        # 제외 목록에 있으면 스킵
        if t.strip() in _excluded:
            continue
        if not is_written(t, mode=mode, root_dir=root_dir, topic_slug=topic_slug):
            logger.debug("Next unwritten title selected: %s", t)
            return t

    logger.info("All outline titles appear to have drafts already.")
    return None
