# report_builder.py
from __future__ import annotations
import os, re
from datetime import datetime
from typing import List, Tuple, Optional
from pathlib import Path

from core.paths import current_path, now_str
from utils.text_utils import section_slugify, strip_number_prefix
from core.paths import read_outline

import logging
logger = logging.getLogger(__name__)

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

def _truthy_env(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in {"1", "true", "yes", "on"}

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
    ENV REPORT_SOURCES 로 재정의 가능(예: "sections,content,chapters")
    """
    env = (os.getenv("REPORT_SOURCES") or "").strip()
    if env:
        items = [s.strip() for s in env.split(",") if s.strip()]
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
    아니면 상단에 '# {title}' 삽입.
    """
    body = (body or "").lstrip()
    if body.startswith("#"):
        return body
    return f"# {title}\n\n{body}"

# ─────────────────────────────────────────────────────────────────────────────
# 메인: 리포트 빌드
# ─────────────────────────────────────────────────────────────────────────────

def build_final_report(
    topic_slug: str,
    outline_fname: str = "outline_report.md",
    mode: str = "report",
    root_dir: str = current_path,
) -> Tuple[str, List[str]]:
    """
    목차(outline) 순서대로 sections/content/chapters/<slug>/*.md 를 병합하여
    reports/<slug>/<timestamp>_report.md 와 reports/<slug>/latest.md 를 생성.
    또한 (옵션) research|findings/<slug>/round_*_findings.md 를 Appendix로 자동 포함.

    Returns:
        (final_path, missing_titles)
    """
    # 1) 목차 로드
    outline_text, used_path = read_outline(
        filename=outline_fname,
        root_dir=root_dir,
        topic_slug=topic_slug,
        mode=mode,
        allow_fallbacks=False,
    )

    titles: List[str] = []
    for line in (outline_text or "").splitlines():
        s = (line or "").strip()
        if not s:
            continue
        s = strip_number_prefix(s)
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
    if _truthy_env("INCLUDE_FINDINGS_IN_REPORT"):
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

    if _truthy_env("ECHO_REPORT") or _truthy_env("ECHO_SECTIONS"):
        bar = "=" * 24
        print("\n" + bar)
        print(f"FINAL REPORT → {final_path}")
        print(bar + "\n")
        print(merged)
        print(bar)

    return final_path, missing
