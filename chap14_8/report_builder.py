from __future__ import annotations
import os, re
from datetime import datetime
from typing import List, Tuple, Optional, Literal, TypeAlias
from pathlib import Path

from core.paths import current_path, now_str
from utils.text_utils import section_slugify, strip_number_prefix
from core.paths import read_outline, _coerce_mode

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config access (CFG → module attr → ENV → default)
# ─────────────────────────────────────────────────────────────
import core.config as config

def _get_cfg_attr(name: str, default):
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    env = os.getenv(name)
    return env if env is not None else default


def _cfg_truthy(name: str, default: bool = False) -> bool:
    v = _get_cfg_attr(name, default)
    try:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1","true","yes","on","y"}
    except Exception:
        return default


def _cfg_str(name: str, default: str) -> str:
    v = _get_cfg_attr(name, default)
    try:
        return str(v).strip() if v is not None else default
    except Exception:
        return default

# Local literal to avoid static coupling to external types
DocMode: TypeAlias = Literal["report", "book"]

SEPARATOR = "\n\n---\n\n"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_first_heading(md_path: Path) -> str:
    """파일의 첫 번째 마크다운 헤딩(# …) 한 줄을 돌려줌(없으면 빈 문자열)."""
    try:
        with md_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.lstrip().startswith("#"):
                    return line.strip().lstrip("#").strip()
    except Exception as e:
        logger.debug("read heading failed: %s (%s)", md_path, e)
    return ""


def _read_file_if_exists(p: str) -> Optional[str]:
    try:
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        pass
    return None


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _bool_cfg_env(env_key: str, *, cfg_attr: Optional[str] = None, default: bool = False) -> bool:
    """
    config.CFG 필드가 있으면 우선 사용, 없으면 모듈 속성/ENV를 참조.
    - cfg_attr 미지정 시 env_key와 같은 이름을 CFG에서 찾아봄.
    """
    attr = cfg_attr or env_key
    v = _get_cfg_attr(attr, None)
    if v is None:
        return _cfg_truthy(env_key, default)
    return _cfg_truthy(attr, default)

# ─────────────────────────────────────────────────────────────────────────────
# Findings(연구 요약) 수집/부록 생성
# ─────────────────────────────────────────────────────────────────────────────

_FINDINGS_RE = re.compile(r"round[-_]?(\d+).*findings\.md$", re.I)


def _strip_top_heading(md: str) -> str:
    """문서 맨 위의 최상위 헤딩 한 줄을 제거(있으면)."""
    lines = (md or "").splitlines()
    if not lines:
        return md or ""
    if lines[0].lstrip().startswith("#"):
        return "\n".join(lines[1:]).lstrip()
    return md or ""


def _collect_findings_paths(topic_slug: str, root_dir: str) -> List[Path]:
    """
    두 위치를 모두 스캔:
      - research/<slug>
      - findings/<slug>
    라운드 번호를 기준으로 정렬.
    """
    bases = [
        Path(root_dir) / "research" / (topic_slug or "default"),
        Path(root_dir) / "findings" / (topic_slug or "default"),
    ]
    cands: set[Path] = set()
    for base in bases:
        if base.exists():
            cands.update(base.glob("round-*-findings.md"))
            cands.update(base.glob("round_*_findings.md"))

    def _key(p: Path) -> tuple[int, str]:
        m = _FINDINGS_RE.search(p.name)
        n = int(m.group(1)) if m else 0
        return (n, p.name.lower())

    return sorted({p.resolve() for p in cands if p.is_file()}, key=_key)


def _build_findings_appendix(topic_slug: str, root_dir: str) -> Optional[str]:
    paths = _collect_findings_paths(topic_slug, root_dir)
    if not paths:
        return None

    parts = ["# Appendix: Research Findings", ""]
    for p in paths:
        m = _FINDINGS_RE.search(p.name)
        rn = int(m.group(1)) if m else None
        sub_title = f"## Round {rn:02d} Findings" if rn is not None else f"## {p.stem}"
        body = Path(p).read_text(encoding="utf-8", errors="ignore")
        body = _strip_top_heading(body)
        parts.append(sub_title)
        parts.append("")
        parts.append(body.strip())
        parts.append("")  # spacing

    return "\n".join(parts).strip() + "\n"

# ─────────────────────────────────────────────────────────────────────────────
# 섹션 파일 로딩 (두 에이전트 산출물 통합)
# ─────────────────────────────────────────────────────────────────────────────


def _source_dirs() -> List[str]:
    """
    보고서 조립 시 참조할 디렉터리 우선순위.
    기본: sections → content → chapters
    우선순위 정의는 CFG.REPORT_SOURCES(콤마구분) → ENV REPORT_SOURCES → 기본값.
    """
    raw = _get_cfg_attr("REPORT_SOURCES", None)
    if isinstance(raw, str):
        s = raw.strip()
    else:
        s = (os.getenv("REPORT_SOURCES") or "").strip()
    if s:
        items = [part.strip() for part in s.split(",") if part.strip()]
        return items or ["sections", "content", "chapters"]
    return ["sections", "content", "chapters"]


def _load_section_body(root_dir: str, topic_slug: str, title: str) -> Optional[tuple[str, str, str]]:
    """
    우선순위 디렉터리 순서대로 <dir>/<slug>/<slugified_title>.md 를 찾는다.
    반환: (used_dir, file_path, body) or None
    """
    fname = f"{section_slugify(title)}.md"
    for dirname in _source_dirs():
        base = os.path.join(root_dir, dirname, topic_slug)
        p = os.path.join(base, fname)
        body = _read_file_if_exists(p)
        if body is not None:
            return dirname, p, body
    return None


def _ensure_heading(title: str, body: str) -> str:
    """
    문서가 이미 #/##/### 로 시작하면 그대로 둔다.
    아니면 상단에 '## {title}' 삽입 (최종 산출물의 섹션 레벨을 H2로 통일).
    """
    body = (body or "").lstrip()
    if body.startswith("#"):
        return body
    return f"## {title}\n\n{body}"

# ─────────────────────────────────────────────────────────────────────────────
# 메인: 리포트 빌드
# ─────────────────────────────────────────────────────────────────────────────

def _as_doc_mode(val: str | None) -> DocMode:
    s = (val or _cfg_str("DOC_MODE", "report")).strip().lower()
    return "report" if s == "report" else "book"


def build_final_report(
    topic_slug: str,
    outline_fname: str = "outline_report.md",
    mode: DocMode | str | None = None,
    root_dir: str = str(current_path),
) -> Tuple[str, List[str]]:
    """
    목차(outline) 순서대로 sections/content/chapters/<slug>/*.md 를 병합하여
    reports/<slug>/<timestamp>_report.md 와 reports/<slug>/latest.md 를 생성.
    또한 (옵션) research|findings/<slug>/round_*_findings.md 를 Appendix로 자동 포함.

    Returns:
        (final_path, missing_titles)
    """
    # 1) 목차 로드
    m: DocMode = _coerce_mode(mode or _as_doc_mode(None))
    outline_text, used_path = read_outline(
        filename=outline_fname,
        root_dir=root_dir,
        topic_slug=topic_slug,
        mode=m,
        allow_fallbacks=False,
    )

    # H2 헤딩(`##`)만 유효 섹션으로 간주 — 프롬프트의 H2-only 정책과 일치
    titles: List[str] = []
    for line in (outline_text or "").splitlines():
        if not line:
            continue
        ls = line.lstrip()
        if not ls.startswith("##"):
            continue
        # "## 1. 제목" → "제목" 추출
        s = strip_number_prefix(ls[2:].strip())
        if s:
            titles.append(s)

    # 2) 섹션 병합
    merged_parts: List[str] = []
    missing: List[str] = []
    used_dir_counter: dict[str, int] = {k: 0 for k in _source_dirs()}
    used_dir_counter["_other"] = 0

    for t in titles:
        res = _load_section_body(root_dir, topic_slug, t)
        if res is None:
            missing.append(t)
            continue
        used_dir, path_used, src = res
        if used_dir in used_dir_counter:
            used_dir_counter[used_dir] += 1
        else:
            used_dir_counter["_other"] += 1
        merged_parts.append(_ensure_heading(t, src))

    # 2-b) Findings 부록 자동 포함(옵션)
    if _bool_cfg_env("INCLUDE_FINDINGS_IN_REPORT"):
        appendix_md = _build_findings_appendix(topic_slug, root_dir)
        if appendix_md:
            merged_parts.append(appendix_md)
            # 목차에 Appendix가 있었는데 파일이 없어 missing에 들어갔다면 제거
            for idx, mt in list(enumerate(missing)):
                if mt.lower().startswith("appendix"):
                    missing.pop(idx)
                    break

    # 3) 저장
    reports_dir = os.path.join(root_dir, "reports", topic_slug)
    os.makedirs(reports_dir, exist_ok=True)

    ts = _timestamp()
    final_name = f"{ts}_report.md"
    final_path = os.path.join(reports_dir, final_name)
    latest_path = os.path.join(reports_dir, "latest.md")

    merged = (SEPARATOR.join(m.strip() for m in merged_parts if (m or "").strip())).rstrip() + "\n"
    with open(final_path, "w", encoding="utf-8") as f:
        f.write(merged)
    try:
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(merged)
    except Exception:
        pass

    # 4) 요약 로그 + 옵션 에코
    logger.info(
        "[ReportBuilder] merged sections → %s | missing=%d",
        ", ".join(f"{k}={v}" for k, v in used_dir_counter.items()),
        len(missing),
    )

    # ECHO_REPORT(ENV/CFG 폴백) 또는 ECHO_SECTIONS가 True면 본문 에코
    echo_report = _bool_cfg_env("ECHO_REPORT")
    if echo_report or bool(_get_cfg_attr("ECHO_SECTIONS", False)):
        bar = "=" * 24
        print("\n" + bar)
        print(f"FINAL REPORT → {final_path}")
        print(bar + "\n")
        print(merged)
        print(bar)

    return final_path, missing
