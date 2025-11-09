# core/paths.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os, hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple, cast, Any, Union, TYPE_CHECKING

import core.config as config
if TYPE_CHECKING:  # 타입 전용(런타임 바인딩 방지)
    from core.config import DocMode
else:
    from typing import Literal as _Lit
    DocMode = _Lit["report", "book"]  # 런타임 안전 폴백
from utils.text_utils import slugify, section_slugify, section_slug_candidates

# ──────────────────────────────────────────────────────────────
# Config helpers (동적 조회)
# ──────────────────────────────────────────────────────────────
def _cfg_str(name: str, default: str = "") -> str:
    try:
        v = getattr(config.CFG, name, default)
        s = (v if isinstance(v, str) else str(v)).strip()
        return s or default
    except Exception:
        return default

def _cfg_bool(name: str, default: bool = False) -> bool:
    v = getattr(config.CFG, name, default)
    if isinstance(v, bool):
        return v
    try:
        return str(v).strip().lower() in {"1","true","yes","on","y"}
    except Exception:
        return default

# ──────────────────────────────────────────────────────────────
# 프로젝트 루트: 항상 config.CFG.PROJECT_ROOT (동적)
# ──────────────────────────────────────────────────────────────
def get_project_root() -> str:
    # 없으면 현재 작업 디렉터리로 폴백
    return _cfg_str("PROJECT_ROOT", os.getcwd())

class _RootProxy:
    """문자열/경로 연산에 자연스럽게 동작하는 동적 루트 프록시 (reload 후 즉시 반영)."""
    def __fspath__(self) -> str:  # os.fspath 지원
        return get_project_root()
    def __str__(self) -> str:
        return get_project_root()
    def __repr__(self) -> str:
        return f"_RootProxy({get_project_root()!r})"
    # Path-like 연산 편의
    def __truediv__(self, other: Union[str, os.PathLike[str]]) -> Path:
        return Path(get_project_root()) / other
    def joinpath(self, *parts: Union[str, os.PathLike[str]]) -> Path:
        return Path(get_project_root()).joinpath(*parts)

# 과거 호환: 변수처럼 쓰이던 current_path를 동적 프록시로 유지
current_path: Any = _RootProxy()


def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)


def _resolve_under_root(p: str | Path) -> Path:
    """절대경로면 그대로, 상대경로면 PROJECT_ROOT 기준으로 해석."""
    q = Path(p)
    if q.is_absolute():
        return q
    return (Path(str(current_path)) / q).resolve()


# ── Research output base (RESEARCH_OUT_DIR → REPORT_OUT_DIR/research → <project>/research)
def research_base_dir() -> Path:
    ro = _cfg_str("RESEARCH_OUT_DIR", "")
    if ro:
        return _resolve_under_root(ro)

    rep = _cfg_str("REPORT_OUT_DIR", "")
    if rep:
        return _resolve_under_root(rep) / "research"

    return Path(str(current_path)) / "research"


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
    # 기본값 'outlines', CFG.OUTLINES_DIR_NAME로 오버라이드 가능
    name = _cfg_str("OUTLINES_DIR_NAME", "outlines")
    return Path(str(current_path)) / name


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


def chroma_base_dir() -> Path:
    """
    벡터스토어 기본 디렉터리.
    - CFG.CHROMA_BASE_DIR 설정 시 우선
    - 없으면 <PROJECT_ROOT>/data/chroma_store
    """
    base = _cfg_str("CHROMA_BASE_DIR", "")
    if base:
        return _resolve_under_root(base)
    return Path(str(current_path)) / "data" / "chroma_store"

def topic_dir(slug: str) -> str:
    return str(chroma_base_dir() / slug)


def _coerce_mode(mode: Optional[str | DocMode]) -> DocMode:
    """문자열/None을 DocMode로 정규화."""
    if mode in ("book", "report"):
        return cast(DocMode, mode)
    # CFG.DOC_MODE 동적 조회
    try:
        m = getattr(config.CFG, "DOC_MODE", "report")
        return cast(DocMode, "book" if m == "book" else "report")
    except Exception:
        return cast(DocMode, "report")


def _base_dir_for_mode(mode: Optional[str | DocMode] = None) -> str:
    """
    콘텐츠 하위 디렉터리 이름을 결정.
    - 기본: report → 'sections', book → 'chapters'
    - CFG.CONTENT_DIR_REPORT_NAME / CFG.CONTENT_DIR_BOOK_NAME로 오버라이드
    """
    m: DocMode = _coerce_mode(mode)
    if m == "report":
        return _cfg_str("CONTENT_DIR_REPORT_NAME", "sections")
    return _cfg_str("CONTENT_DIR_BOOK_NAME", "chapters")


def get_content_dir(
    mode: Optional[str | DocMode] = None,
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> Path:
    root = _resolve_under_root(root_dir) if root_dir else Path(str(current_path))
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

def sections_dir(
    topic_slug: Optional[str] = None,
    *,
    root_dir: Optional[str | Path] = None,
    mode: Optional[str | DocMode] = "report",
) -> Path:
    """chapXX/sections/<topic_slug> 디렉토리 경로를 돌려줍니다."""
    # report 기준으로 강제(섹션 저장 위치 규칙과 일치)
    return get_content_dir("report", root_dir=root_dir, topic_slug=topic_slug)


def find_section_path(
    title: str,
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
    mode: Optional[str | DocMode] = "report",
) -> Optional[Path]:
    """
    섹션 제목으로 실제 저장된 .md 파일을 탐색합니다.
    - 번호 접두어 포함/미포함
    - 0패딩(02) 포함/미포함
    - 특수문자 정규화는 작성기 규칙과 동일
    """
    sdir = sections_dir(topic_slug=topic_slug, root_dir=root_dir, mode=mode)
    for slug in section_slug_candidates(title):
        p = (sdir / f"{slug}.md")
        if p.exists():
            return p
    return None

def get_outline_dir(
    *,
    root_dir: Optional[str | Path] = None,
    topic_slug: Optional[str] = None,
) -> Path:
    root = _resolve_under_root(root_dir) if root_dir else Path(str(current_path))
    d = root / _cfg_str("OUTLINES_DIR_NAME", "outlines")
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


# ──────────────────────────────────────────────────────────────
# Reload hook (선택): config.reload_config() 이후 호출 시 로깅만
# ──────────────────────────────────────────────────────────────
def refresh_paths() -> None:  # pragma: no cover
    """동적 프록시를 쓰므로 특별한 갱신은 필요 없지만, 호출 시 현재 루트를 로그에 남깁니다."""
    logger.info("[paths] project_root=%s | chroma_base=%s | outlines=%s",
                get_project_root(), chroma_base_dir(), outline_base_dir())
