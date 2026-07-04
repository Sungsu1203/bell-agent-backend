"""§paper-writer-1 Step C-2 — end-to-end paper measurement driver.

argparse 7 groups:
  --topic / --sections / --output-dir / --warmup / --measure / --sleep / --timeout / --dry-run

axis 3 metric (B+D 묶음, B-6 design 정합):
  axis 1: APA 7th regex — References 항목 중 regex 통과 비율 ≥ 0.8
  axis 2: IMRD 4 section — 4 section 존재 + 분량 가이드 ±30% 허용
  axis 3: per-backend ratio (catch 66):
    primary 3: OA ≥ 0.70, SS ≥ 0.40, combined (OA+SS+vertex mean) ≥ 0.50
    보조 metric: vertex_filtered_ratio

표준 (catch 49):
  max_retries=0, provider lock, utf-8 wrapper, stage marker 14단계.

실행:
  .venv_vertex\\Scripts\\python.exe writer_project/scripts/§paper-writer-1/measure_paper.py
  .venv_vertex\\Scripts\\python.exe writer_project/scripts/§paper-writer-1/measure_paper.py --dry-run
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Step 1: utf-8 wrapper (Windows cp949 회피, catch 49 표준) ──
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]  # writer_project/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# R2-a: scripts/ 를 sys.path 에 얹어 § 없는 중립 패키지(common)를 import 가능하게.
SCRIPTS_ROOT = HERE.parent  # writer_project/scripts
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

# R2-a: axis3 재설계 — vertex chunk 학술/비학술 가름에 공유 ACADEMIC_DOMAINS 참조.
from urllib.parse import urlparse  # noqa: E402
from common.academic_domains import ACADEMIC_DOMAINS  # noqa: E402


def _chunk_is_academic(chunk: dict) -> bool:
    """chunk 의 domain(우선)·uri(폴백) host 가 ACADEMIC_DOMAINS 에 걸리면 True.

    vertex chunk = {uri, title, domain} (R1 확정) — domain 필드 우선, 없으면 uri host.
    subdomain 허용: host == d 또는 host.endswith('.'+d). www. 프리픽스 정규화.
    """
    host = (chunk.get("domain") or "").strip().lower()
    if not host:
        host = (urlparse(chunk.get("uri") or "").hostname or "").lower()
    host = host.lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return False
    return any(host == d or host.endswith("." + d) for d in ACADEMIC_DOMAINS)


# ── Step 2: dotenv chain 먼저 (catch 64: override=True 강제) ──
from dotenv import load_dotenv  # noqa: E402
for _env_name in (".env", ".env.vertex", ".env.openalex", ".env.semanticscholar"):
    _p = PROJECT_ROOT / _env_name
    if _p.exists():
        load_dotenv(_p, override=True)


# ── Step 3: driver env override (dotenv 후 강제 — catch 69 후보 lesson) ──
# dotenv override=True 가 driver 사전 설정값을 무효화하는 함정 회피:
# 반드시 dotenv chain 완료 후 driver 가 최종 결정권을 갖도록 강제 set 한다.
def _force_driver_env_override() -> None:
    """측정 driver 전용 env 강제 override.

    .env 의 LLM_PROVIDER=openai, OPENAI_MAX_RETRIES=1, SKIP_VERTEX_SEARCH=1,
    TOPIC_SLUG=venfobel-vitamin 등이 dotenv override=True 로 driver 사전
    설정값을 덮어쓰는 함정을 차단한다 (catch 69 후보 lesson).
    """
    os.environ["LLM_PROVIDER"] = "vertexai"
    os.environ["VERTEX_MAX_RETRIES"] = "0"
    os.environ["OPENAI_MAX_RETRIES"] = "0"
    os.environ["LLM_MAX_RETRIES"] = "0"
    os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"
    os.environ["SKIP_VERTEX_SEARCH"] = "0"
    # ── 맥 SSL: OA·SS urllib HTTPS 검증 (certifi 명시 — macOS 루트 인증서 미연결 회피) ──
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    os.environ["TOPIC_SLUG"] = "academic-trademark-similarity-consumer"  # "academic-influencer-marketing-consumer-behavior"


_force_driver_env_override()


# ── Step 4: stage marker (timestamp + 번호 + double flush) ──
def _stage(n: int, total: int, desc: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [Stage {n}/{total}] {desc}", flush=True)
    sys.stdout.flush()


_stage(1, 14, "dotenv chain + env override 완료")


# ── Step 5: logging ──
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ── Step 6: lazy imports (env 확정 후 agent 모듈 로드) ──
from agent.web_search import paper_section_fetch  # noqa: E402
from agent.paper_section_writer import (  # noqa: E402
    write_paper_section,
    build_apa_references,
    attach_references_footer,
)

SECTION_WORD_GUIDE = {
    "Introduction": (800, 1200),
    "Theoretical Background": (1000, 1500),
    "Proposed Framework": (1000, 1500),
    "Research Design (Proposed)": (800, 1200),
    "Expected Contributions": (600, 1000),
}

# SECTION_WORD_GUIDE = {
#    "Introduction": (800, 1200),
#    "Methods": (600, 1000),
#    "Results": (1000, 1500),
#    "Discussion": (1500, 2000),
# }

APA_REGEX = re.compile(
    r"\(\d{4}\)|\(n\.d\.\)|https?://doi\.org/", re.IGNORECASE
)

# ── axis3 재설계 (R2-a) — 학술 회수율 단일 임계 ──
# 구 산식(oa≥0.70 ∧ ss≥0.40 ∧ combined≥0.50)은 같은 분모 3비율이라 구조적 영구 FAIL.
# 신 산식: academic_ratio = (OA + SS + 학술vertex) / 전체회수. 비학술 vertex(블로그)는
# 분모에 남겨 페널티. 개별 백엔드 문턱 폐기, 단일 임계로 판정.
# 0.50 = 학술 과반 합격선. R2-b 3런 실측 0.517~0.549(mean 0.533) → 현 파이프라인 PASS.
# vertex_web 은 분모 페널티(상표 토픽 vertex 학술≈0, R2-b 실측 0~1.2%).
ACADEMIC_RATIO_THRESHOLD = 0.50


def _build_outline(sections: list[str]) -> str:
    return "\n".join(f"## {i}. {s}" for i, s in enumerate(sections, 1))


def _run_one_paper(topic: str, sections: list[str]) -> dict:
    """1 paper end-to-end run. Returns metrics + body + chunks."""
    outline = _build_outline(sections)
    section_bodies: list[str] = []
    section_chunks_all: list[dict] = []
    per_section: dict[str, dict] = {}
    stage_times: dict[str, float] = {}
    t0 = time.monotonic()

    for i, section in enumerate(sections, 1):
        fetch_stage = 2 + i
        write_stage = 6 + i
        # fetch
        _stage(fetch_stage, 14, f"section {i} ({section}) fetch start")
        tf = time.monotonic()
        chunks = paper_section_fetch(topic, section)
        stage_times[f"fetch_{section}"] = round(time.monotonic() - tf, 2)
        section_chunks_all.extend(chunks)
        # write
        _stage(write_stage, 14, f"section {i} ({section}) LLM 본문 생성")
        tw = time.monotonic()
        target_title = f"{i}. {section}"
        body = write_paper_section(
            topic=topic,
            section_type=section,
            target_title=target_title,
            outline=outline,
            references_chunks=chunks,
            previous_sections="\n\n".join(section_bodies),
        )
        stage_times[f"write_{section}"] = round(time.monotonic() - tw, 2)
        section_bodies.append(body)
        per_section[section] = {
            "len_chars": len(body),
            "word_count": len(body.split()),
            "chunks_count": len(chunks),
            "backends": sorted({c.get("_backend", "?") for c in chunks}),
        }

    _stage(11, 14, "References footer build (format_apa7)")
    t_ref = time.monotonic()
    apa_lines = build_apa_references(section_chunks_all)
    paper_body = "\n\n".join(section_bodies)
    paper_full = attach_references_footer(paper_body, apa_lines)
    stage_times["references_footer"] = round(time.monotonic() - t_ref, 2)
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
        "stage_times": stage_times,
    }


def _eval_axes(result: dict) -> dict:
    """axis 1~3 평가."""
    per_section = result["per_section"]

    # axis 1: APA 7th regex
    apa_lines = result["apa_lines"]
    apa_pass = sum(1 for line in apa_lines if APA_REGEX.search(line))
    apa_ratio = apa_pass / len(apa_lines) if apa_lines else 0.0
    axis1 = {"pass_ratio": round(apa_ratio, 3), "n": len(apa_lines),
             "threshold": 0.8, "verdict": "PASS" if apa_ratio >= 0.8 else "FAIL"}

    # axis 2: IMRD section 분량 ±30%
    section_verdicts: dict[str, str] = {}
    for s in result["sections"]:
        lo, hi = SECTION_WORD_GUIDE.get(s, (0, 99999))
        wc = per_section.get(s, {}).get("word_count", 0)
        section_verdicts[s] = "PASS" if int(lo * 0.7) <= wc <= int(hi * 1.3) else "FAIL"
    axis2 = {"per_section": {s: {"word_count": per_section.get(s, {}).get("word_count", 0),
                                  "verdict": v} for s, v in section_verdicts.items()},
             "verdict": "PASS" if all(v == "PASS" for v in section_verdicts.values()) else "FAIL"}

    # axis 3: 학술 회수율 (R2-a 재설계) — academic_ratio = (OA + SS + 학술vertex) / total
    chunks = result["chunks"]
    n_oa = n_ss = n_vx_acad = n_vx_web = n_other = 0
    for c in chunks:
        b = c.get("_backend", "?")
        if b == "openalex":
            n_oa += 1
        elif b == "semantic_scholar":
            n_ss += 1
        elif b == "vertex":
            if _chunk_is_academic(c):
                n_vx_acad += 1
            else:
                n_vx_web += 1
        else:
            n_other += 1
    total = len(chunks)
    academic_hits = n_oa + n_ss + n_vx_acad          # 학술 분자 (비학술 vertex 제외)
    academic_ratio = academic_hits / total if total else 0.0
    # 진단용 per-backend ratio (구 지표 — R2-b 임계 산정 참고, 판정엔 미사용)
    oa_r = n_oa / total if total else 0.0
    ss_r = n_ss / total if total else 0.0
    vx_r = (n_vx_acad + n_vx_web) / total if total else 0.0
    axis3 = {
        "academic_ratio": round(academic_ratio, 3),
        "threshold": ACADEMIC_RATIO_THRESHOLD,           # 0.50 (R2-b 실측 후 R3 확정)
        "academic_hits": academic_hits,
        "total": total,
        "backend_counts": {                               # vertex 를 학술/웹 분해
            "openalex": n_oa, "semantic_scholar": n_ss,
            "vertex_academic": n_vx_acad, "vertex_web": n_vx_web,
            "other": n_other,
        },
        # 진단 ratio (판정 미사용) — vertex_academic_ratio 는 실제 도메인 필터 반영값
        "openalex_ratio": round(oa_r, 3),
        "semantic_scholar_ratio": round(ss_r, 3),
        "vertex_ratio": round(vx_r, 3),
        "vertex_academic_ratio": round(n_vx_acad / total, 3) if total else 0.0,
        "verdict": "PASS" if academic_ratio >= ACADEMIC_RATIO_THRESHOLD else "FAIL",
    }

    return {"axis1_apa": axis1, "axis2_imrd": axis2, "axis3_backend_ratio": axis3}


def _save_md_docx(result: dict, output_dir: Path, ts: str) -> dict:
    """.md + .docx 양 format 출력."""
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", result["topic"].lower())[:60].strip("_")
    md_path = output_dir / f"paper_{slug}_{ts}.md"
    docx_path = output_dir / f"paper_{slug}_{ts}.docx"

    _stage(12, 14, f".md write → {md_path.name}")
    md_path.write_text(result["paper_full"], encoding="utf-8")

    _stage(13, 14, f".docx write → {docx_path.name}")
    docx_size = 0
    try:
        from docx import Document
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

    return {
        "md_path": str(md_path), "docx_path": str(docx_path) if docx_size > 0 else "",
        "md_size": md_path.stat().st_size, "docx_size": docx_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="§paper-writer-1 measure driver")
    parser.add_argument("--topic", type=str,
                        default="consumer behavior in influencer marketing")
    parser.add_argument("--sections", type=str, nargs="+",
                        default=["Introduction", "Theoretical Background",
                                 "Proposed Framework", "Research Design (Proposed)",
                                 "Expected Contributions"])
    parser.add_argument("--output-dir", type=str,
                        default=str(PROJECT_ROOT / "scripts" / "output" / "§paper-writer-1"))
    parser.add_argument("--warmup", type=int, default=0)
    parser.add_argument("--measure", type=int, default=1)
    parser.add_argument("--sleep", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--dry-run", action="store_true",
                        help="Stage 2 (env dump) 까지만 print 후 exit. API 비용 0.")
    args = parser.parse_args()

    # Stage 2: config 확정 + env dump
    _stage(2, 14, "config 확정 + env dump")
    for k in ("LLM_PROVIDER", "VERTEX_MAX_RETRIES", "OPENAI_MAX_RETRIES",
              "LLM_MAX_RETRIES", "SKIP_VERTEX_SEARCH", "TOPIC_SLUG",
              "GCP_PROJECT_ID", "GCP_REGION"):
        print(f"  {k}={os.environ.get(k, '(unset)')}", flush=True)
    print(f"  --topic={args.topic!r}", flush=True)
    print(f"  --sections={args.sections}", flush=True)
    print(f"  --timeout={args.timeout}", flush=True)

    if args.dry_run:
        print("\n[--dry-run] Stage 2 완료, exit (API 비용 0).", flush=True)
        return 0

    out_dir = Path(args.output_dir)
    runs: list[dict] = []
    for run_i in range(args.warmup + args.measure):
        phase = "warmup" if run_i < args.warmup else "measure"
        print(f"\n{'='*60}\nrun {run_i + 1}/{args.warmup + args.measure} phase={phase}\n{'='*60}", flush=True)
        r = _run_one_paper(args.topic, args.sections)
        r["phase"] = phase
        r["run_index"] = run_i
        if phase == "measure":
            axes = _eval_axes(r)
            r.update(axes)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            files = _save_md_docx(r, out_dir, ts)
            r["files"] = files
            _stage(14, 14, "axis 측정 완료 + 결과 박제")
        runs.append(r)
        if run_i < args.warmup + args.measure - 1:
            time.sleep(args.sleep)

    # JSON 박제 (body/chunks 제외)
    measurements = [
        {k: v for k, v in r.items() if k not in ("paper_full", "section_bodies", "chunks")}
        for r in runs
    ]
    summary = {
        "topic": args.topic, "sections": args.sections,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warmup": args.warmup, "measure": args.measure,
        "runs": measurements,
    }
    json_path = out_dir / "c_paper_measurement.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {json_path}", flush=True)
    print(json.dumps(measurements[-1] if measurements else {}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
