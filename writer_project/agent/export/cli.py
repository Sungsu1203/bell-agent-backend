# agent/export/cli.py
"""Markdown 보고서 → PowerPoint deck 변환 CLI.

Usage:
  python -m agent.export.cli <slug>
  python -m agent.export.cli <slug> --report <md>
  python -m agent.export.cli <slug> --report <md> --out <pptx>
  python -m agent.export.cli <slug> --template <pptx>
"""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

from agent.export.planner import plan_deck
from agent.export.renderer import render_deck

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_REL = "templates/agency_default.pptx"


def _resolve_md(slug: str, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = Path.cwd() / p
        if not p.exists():
            raise FileNotFoundError(f"--report not found: {p}")
        return p
    slug_dir = Path("reports") / slug
    if not slug_dir.is_dir():
        raise FileNotFoundError(f"reports/{slug}/ not found")
    latest = slug_dir / "latest.md"
    if latest.exists():
        return latest
    candidates = sorted(slug_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"no .md files in reports/{slug}/")
    return candidates[0]


def _resolve_out(md_path: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = Path.cwd() / p
        return p
    return md_path.with_suffix(".pptx")


def _resolve_template(explicit: str | None) -> Path:
    p = Path(explicit) if explicit else Path(DEFAULT_TEMPLATE_REL)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        raise FileNotFoundError(f"template not found: {p}")
    return p


def _topic_title_for(slug: str, md_text: str) -> str:
    """md 의 첫 # 헤딩 (단일 #) 우선, 없으면 slug → Title Case fallback."""
    for line in md_text.splitlines()[:30]:
        s = line.strip()
        if s.startswith("# ") and not s.startswith("## "):
            return s[2:].strip()
    return slug.replace("-", " ").title()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m agent.export.cli",
        description="Markdown 보고서를 PowerPoint deck (.pptx) 으로 변환.",
    )
    p.add_argument("slug", help="토픽 슬러그 (예: 'venfobel-vitamin')")
    p.add_argument("--report", default=None, help="입력 md 경로 (생략 시 reports/<slug>/latest.md 또는 가장 최근 .md)")
    p.add_argument("--out", default=None, help="출력 .pptx 경로 (생략 시 입력 md 와 동일 dir·basename)")
    p.add_argument("--template", default=None, help=f"템플릿 .pptx 경로 (default: {DEFAULT_TEMPLATE_REL})")
    p.add_argument("--topic-title", default=None, help="토픽 제목 명시 (생략 시 md 의 첫 # 헤딩 또는 slug)")
    p.add_argument("-v", "--verbose", action="store_true", help="DEBUG 로깅")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    md_path = _resolve_md(args.slug, args.report)
    out_path = _resolve_out(md_path, args.out)
    template_path = _resolve_template(args.template)
    md_text = md_path.read_text(encoding="utf-8")
    topic_title = args.topic_title or _topic_title_for(args.slug, md_text)

    print(f"[cli] slug:        {args.slug}")
    print(f"[cli] report:      {md_path}  ({md_path.stat().st_size:,} B)")
    print(f"[cli] template:    {template_path}")
    print(f"[cli] topic_title: {topic_title!r}")
    print(f"[cli] out:         {out_path}")
    print(f"[cli] planning ... (plan_deck — LLM 호출 1회)")

    deck = plan_deck(md_text, slug=args.slug, topic_title=topic_title)
    print(f"[cli] plan_deck OK — slides={len(deck.slides)}")
    print(f"[cli] rendering ...")

    result = render_deck(deck, template_path=template_path, out_path=out_path)
    size_kb = result.stat().st_size / 1024
    print(f"[cli] render_deck OK — {result} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
