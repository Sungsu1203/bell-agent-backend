"""§paper-writer-1 Step C-2 — end-to-end paper measurement driver.

argparse 6 groups (사용자 컨펌 ②):
  --topic / --sections / --output-dir / --warmup / --measure / --sleep / --timeout

axis 3 metric (B+D 묶음, B-6 design 정합):
  axis 1: APA 7th regex 정합 — References 항목 중 regex 통과 비율 ≥ 0.8
  axis 2: IMRD 4 section 정합 — 4 section 존재 + 분량 가이드 ±30% 허용
  axis 3: per-backend ratio (catch 66 정합):
    primary 3: OA ≥ 0.70, SS ≥ 0.40, combined (OA+SS+vertex mean) ≥ 0.50
    보조 metric (PASS/FAIL 무관): vertex_filtered_ratio

표준 (catch 49 정합):
  max_retries=0, provider lock, utf-8 stdout/stderr wrapper, stage marker.

실행:
  .venv_vertex\\Scripts\\python.exe writer_project/scripts/§paper-writer-1/measure_paper.py
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── utf-8 wrapper + provider lock + retry disable (catch 49) ──
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

os.environ.setdefault("LLM_PROVIDER", "vertexai")
os.environ["LLM_MAX_RETRIES"] = "0"
os.environ["VERTEX_MAX_RETRIES"] = "0"
os.environ["OPENAI_MAX_RETRIES"] = "0"


def _stage(msg: str) -> None:
    print(f"[stage] {msg}", flush=True)


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]  # writer_project/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── dotenv chain (catch 64: override=True 강제) ──
from dotenv import load_dotenv  # noqa: E402
for env_name in (".env", ".env.vertex", ".env.openalex", ".env.semanticscholar"):
    p = PROJECT_ROOT / env_name
    if p.exists():
        load_dotenv(p, override=True)


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── lazy imports (after env + sys.path set up) ──
from agent.web_search import paper_section_fetch  # noqa: E402
from agent.paper_section_writer import (  # noqa: E402
    write_paper_section,
    build_apa_references,
    attach_references_footer,
)


SECTION_WORD_GUIDE = {
    "Introduction": (800, 1200),
    "Methods": (600, 1000),
    "Results": (1000, 1500),
    "Discussion": (1500, 2000),
}

APA_REGEX = re.compile(
    r"\(\d{4}\)|\(n\.d\.\)|https?://doi\.org/", re.IGNORECASE
)


def _build_outline(sections: list[str]) -> str:
    return "\n".join(f"## {i}. {s}" for i, s in enumerate(sections, 1))


def _run_one_paper(topic: str, sections: list[str]) -> dict:
    """1 paper end-to-end run. Returns metrics + body + chunks."""
    outline = _build_outline(sections)
    section_bodies: list[str] = []
    section_chunks_all: list[dict] = []
    per_section: dict[str, dict] = {}
    t0 = time.monotonic()

    for i, section in enumerate(sections, 1):
        _stage(f"fetch {section}")
        chunks = paper_section_fetch(topic, section)
        section_chunks_all.extend(chunks)
        _stage(f"write {section}")
        target_title = f"{i}. {section}"
        body = write_paper_section(
            topic=topic,
            section_type=section,
            target_title=target_title,
            outline=outline,
            references_chunks=chunks,
            previous_sections="\n\n".join(section_bodies),
        )
        section_bodies.append(body)
        per_section[section] = {
            "len_chars": len(body),
            "word_count": len(body.split()),
            "chunks_count": len(chunks),
            "backends": sorted({c.get("_backend", "?") for c in chunks}),
        }

    apa_lines = build_apa_references(section_chunks_all)
    paper_body = "\n\n".join(section_bodies)
    paper_full = attach_references_footer(paper_body, apa_lines)
    elapsed = time.monotonic() - t0

    return {
        "topic": topic,
        "sections": sections,
        "paper_full": paper_full,
        "section_bodies": section_bodies,
        "per_section": per_section,
        "chunks": section_chunks_all,
        "apa_lines": apa_lines,
        "elapsed_sec": round(elapsed, 2),
    }


def _eval_axes(result: dict) -> dict:
    """5 검증 항목 평가 (axis 1~3 + .md/.docx PASS/FAIL — axis 5 baseline only)."""
    sections = result["sections"]
    per_section = result["per_section"]

    # axis 1: APA 7th regex 정합
    apa_lines = result["apa_lines"]
    apa_pass = sum(1 for l in apa_lines if APA_REGEX.search(l))
    apa_ratio = apa_pass / len(apa_lines) if apa_lines else 0.0
    axis1 = {"pass_ratio": round(apa_ratio, 3), "n": len(apa_lines),
             "threshold": 0.8, "verdict": "PASS" if apa_ratio >= 0.8 else "FAIL"}

    # axis 2: IMRD section 분량 가이드 ±30%
    section_verdicts: dict[str, str] = {}
    for s in sections:
        lo, hi = SECTION_WORD_GUIDE.get(s, (0, 99999))
        wc = per_section.get(s, {}).get("word_count", 0)
        lo_relaxed = int(lo * 0.7)
        hi_relaxed = int(hi * 1.3)
        section_verdicts[s] = "PASS" if lo_relaxed <= wc <= hi_relaxed else "FAIL"
    axis2 = {"per_section": section_verdicts,
             "verdict": "PASS" if all(v == "PASS" for v in section_verdicts.values()) else "FAIL"}

    # axis 3: per-backend ratio (catch 66, B+D 묶음)
    chunks = result["chunks"]
    backend_counts: dict[str, int] = {}
    for c in chunks:
        b = c.get("_backend", "?")
        backend_counts[b] = backend_counts.get(b, 0) + 1
    total = len(chunks)
    if total > 0:
        oa_ratio = backend_counts.get("openalex", 0) / total
        ss_ratio = backend_counts.get("semantic_scholar", 0) / total
        vx_ratio = backend_counts.get("vertex", 0) / total
        combined = statistics.mean([oa_ratio, ss_ratio, vx_ratio])
    else:
        oa_ratio = ss_ratio = vx_ratio = combined = 0.0
    axis3 = {
        "openalex_ratio": round(oa_ratio, 3),
        "semantic_scholar_ratio": round(ss_ratio, 3),
        "vertex_ratio": round(vx_ratio, 3),
        "combined_ratio": round(combined, 3),
        "vertex_filtered_ratio": round(vx_ratio, 3),  # 보조 (현재는 vertex_ratio 와 동일, future filter 후 분리)
        "primary": {
            "oa_pass": oa_ratio >= 0.70,
            "ss_pass": ss_ratio >= 0.40,
            "combined_pass": combined >= 0.50,
        },
        "verdict": "PASS" if (oa_ratio >= 0.70 and ss_ratio >= 0.40 and combined >= 0.50) else "FAIL",
    }

    return {"axis1_apa": axis1, "axis2_imrd": axis2, "axis3_backend_ratio": axis3}


def _save_md_docx(result: dict, output_dir: Path, ts: str) -> dict:
    """.md + .docx 양 format 출력. Returns {md_path, docx_path, md_size, docx_size}."""
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", result["topic"].lower())[:60].strip("_")
    md_path = output_dir / f"paper_{slug}_{ts}.md"
    docx_path = output_dir / f"paper_{slug}_{ts}.docx"

    md_path.write_text(result["paper_full"], encoding="utf-8")

    try:
        from docx import Document
        from docx.shared import Pt
        doc = Document()
        for line in result["paper_full"].split("\n"):
            if line.startswith("## "):
                doc.add_heading(line[3:].strip(), level=2)
            elif line.startswith("### "):
                doc.add_heading(line[4:].strip(), level=3)
            elif line.strip():
                doc.add_paragraph(line)
        doc.save(str(docx_path))
        docx_size = docx_path.stat().st_size
    except Exception as e:
        logger.warning("[docx] failed: %s", e)
        docx_size = 0

    return {
        "md_path": str(md_path),
        "docx_path": str(docx_path) if docx_size > 0 else "",
        "md_size": md_path.stat().st_size,
        "docx_size": docx_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="§paper-writer-1 Step C-2 measure driver")
    parser.add_argument("--topic", type=str,
                        default="consumer behavior in influencer marketing")
    parser.add_argument("--sections", type=str, nargs="+",
                        default=["Introduction", "Methods", "Results", "Discussion"])
    parser.add_argument("--output-dir", type=str,
                        default=str(PROJECT_ROOT / "scripts" / "output" / "§paper-writer-1"))
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--measure", type=int, default=1)
    parser.add_argument("--sleep", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    runs: list[dict] = []
    for run_i in range(args.warmup + args.measure):
        phase = "warmup" if run_i < args.warmup else "measure"
        _stage(f"run {run_i + 1} phase={phase}")
        r = _run_one_paper(args.topic, args.sections)
        r["phase"] = phase
        r["run_index"] = run_i
        if phase == "measure":
            axes = _eval_axes(r)
            r.update(axes)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            files = _save_md_docx(r, out_dir, ts)
            r["files"] = files
        runs.append(r)
        if run_i < args.warmup + args.measure - 1:
            time.sleep(args.sleep)

    # 측정 결과 박제 (JSON, body 제외)
    measurements = [
        {k: v for k, v in r.items() if k not in ("paper_full", "section_bodies", "chunks")}
        for r in runs
    ]
    summary = {
        "topic": args.topic,
        "sections": args.sections,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warmup": args.warmup,
        "measure": args.measure,
        "runs": measurements,
    }
    json_path = out_dir / "c_paper_measurement.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _stage(f"saved {json_path}")
    print(json.dumps(measurements[-1] if measurements else {}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
