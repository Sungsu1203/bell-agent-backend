#!/usr/bin/env python3
"""§14-3 Phase 3: §14-2 Step 1b patch (d88a8b9) 본 검증 driver.

architecture: patch-based
- patched state (현재 브랜치, d88a8b9 적용 상태): N=3 + warmup 2
- reverted state (d88a8b9 revert 상태): N=3 + warmup 2
- 측정 종료 시 patch 복구 + git diff clean 검증

미션:
- vertex_grounding count 의 patch 효과 측정 (patched vs reverted)
- elapsed_sec, refs_docs, source_dist 박제
- chroma collection_count 부수 박제

§13-7 측정 표준:
- max_retries=0 (env: VERTEX_MAX_RETRIES=0, .env.vertex 박제)
- warmup 2 runs per state (결과 제외)
- per-run-timeout 300s
- inter-run-sleep 60s
- PYTHONIOENCODING=utf-8

자율 진행 금지 (사용자 컨펌 받고 sub-task 3 실행).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DRY_RUN_SCRIPT = PROJECT_ROOT / "scripts" / "_step3_dry_run_rag_update.py"
PATCH_PATH = PROJECT_ROOT / "scripts" / "output" / "§14-3" / "_phase3" / "d88a8b9.patch"
OUTPUT_DIR = PROJECT_ROOT / "scripts" / "output" / "§14-3" / "_phase3"

DEFAULTS = {
    "topic_slug": "ai-generated-creative-ad-platforms",
    "topic_title": "AI 생성 광고 크리에이티브 플랫폼 동향",
    "trigger": "최신 자료로 RAG 업데이트해줘",
    "n_runs": 3,
    "n_warmup": 2,
    "per_run_timeout": 300.0,
    "inter_run_sleep": 60.0,
    "recursion_limit": 100,
}


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _git(*args: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8"
    )


def verify_clean() -> tuple[bool, str]:
    """git diff --stat clean 여부 + stat 문자열 반환."""
    proc = _git("diff", "--stat")
    stat = proc.stdout.strip()
    return (stat == ""), stat


def apply_patch(patch_path: Path, *, reverse: bool = False) -> None:
    """git apply (reverse=True → revert). 실패 시 RuntimeError."""
    args = ["apply"]
    if reverse:
        args.append("-R")
    args.append(str(patch_path))
    proc = _git(*args)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git apply {'-R' if reverse else ''} fail: {proc.stderr.strip()}"
        )


def pre_clear_ns(ns: str, out_dir: Path, timeout_s: float = 60.0) -> dict:
    """ns_web 격리 — `_phase_b_clear_ns.py` subprocess 호출."""
    clear_script = PROJECT_ROOT / "scripts" / "_phase_b_clear_ns.py"
    out_json = out_dir / f"clear_{ns}.json"
    cmd = [sys.executable, str(clear_script), "--ns", ns, "--output", str(out_json)]
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, timeout=timeout_s, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        log = {
            "elapsed_sec": round(time.monotonic() - t0, 2),
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-1000:] if proc.stdout else "",
        }
        if out_json.exists():
            try:
                log["result"] = json.loads(out_json.read_text(encoding="utf-8"))
            except Exception as e:
                log["result_parse_err"] = f"{type(e).__name__}: {e}"
        return log
    except subprocess.TimeoutExpired:
        return {"elapsed_sec": round(time.monotonic() - t0, 2), "error": "TimeoutExpired"}


def run_single(state_label: str, run_id: str, config: dict, output_dir: Path) -> dict:
    """단일 dry-run subprocess 호출."""
    output_json = output_dir / f"phase3_{state_label}_{run_id}.json"
    output_log = output_dir / f"phase3_{state_label}_{run_id}.console.log"

    env = os.environ.copy()

    # G4-2: pollution vars pop (precautionary unset)
    # core/topic.py:141-142 mirror 결과 + .env.openai 잔재 차단
    POLLUTION_VARS = [
        "CHROMA_NAMESPACE",
        "CHROMA_NAMESPACE_WEB",
        "CHROMA_NAMESPACE_LOCAL",
        "CHROMA_DIR",
    ]
    for k in POLLUTION_VARS:
        env.pop(k, None)

    env["PYTHONIOENCODING"] = "utf-8"
    env["LOCAL_RAG_ALLOW_EMPTY"] = "1"
    env["TOPIC_SLUG"] = config["topic_slug"]

    # G4-2: graph 내부 modification 우회 (명시 set)
    env["LLM_PROVIDER"] = "vertexai"
    env["LLM_MODEL"] = "gemini-2.5-flash"
    env["SKIP_VERTEX_SEARCH"] = "0"
    env["MIRROR_STATE_TO_ENV"] = "0"  # core/topic.py:140 mirror 차단

    # G4-2: driver-side env trace (subprocess 호출 직전)
    print(f"[driver_env] state={state_label} run={run_id}", flush=True)
    for k in ("LLM_PROVIDER", "LLM_MODEL", "TOPIC_SLUG", "SKIP_VERTEX_SEARCH",
              "MIRROR_STATE_TO_ENV", "CHROMA_NAMESPACE", "CHROMA_DIR"):
        print(f"  {k} = {env.get(k, '')}", flush=True)

    cmd = [
        sys.executable, str(DRY_RUN_SCRIPT),
        "--topic-slug", config["topic_slug"],
        "--topic-title", config["topic_title"],
        "--trigger", config["trigger"],
        "--output", str(output_json),
        "--recursion-limit", str(config["recursion_limit"]),
    ]

    t_start = time.monotonic()
    timeout_flag = False
    exit_code: int = -999
    try:
        with open(output_log, "wb") as f_log:
            proc = subprocess.run(
                cmd, env=env, stdout=f_log, stderr=subprocess.STDOUT,
                timeout=config["per_run_timeout"], check=False,
            )
            exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timeout_flag = True
        exit_code = -1

    elapsed = round(time.monotonic() - t_start, 2)

    # 결과 JSON 에서 metric 추출 (있으면)
    metrics: dict = {}
    if output_json.exists():
        try:
            data = json.loads(output_json.read_text(encoding="utf-8"))
            sra = data.get("state_references_analysis") or {}
            metrics = {
                "elapsed_sec": data.get("elapsed_sec"),
                "invoke_elapsed_sec": data.get("invoke_elapsed_sec"),
                "abort_reason": data.get("abort_reason"),
                "refs_docs_count": sra.get("count"),
                "source_dist": sra.get("source_dist"),
            }
        except Exception as e:
            metrics = {"parse_err": f"{type(e).__name__}: {e}"}

    return {
        "run_id": run_id,
        "state": state_label,
        "exit_code": exit_code,
        "elapsed_sec_driver": elapsed,
        "timeout": timeout_flag,
        "json_path": str(output_json),
        "log_path": str(output_log),
        "metrics": metrics,
    }


def measure_state(state_label: str, config: dict, output_dir: Path) -> dict:
    """warmup 2 + N=3 측정 + 매 run 전 pre-clear."""
    ns_web = f"{config['topic_slug']}-web"
    print(f"\n[measure] state={state_label} warmup={config['n_warmup']} n={config['n_runs']}", flush=True)

    warmup_results: list[dict] = []
    for w in range(config["n_warmup"]):
        pre_clear_ns(ns_web, output_dir)
        r = run_single(state_label, f"warmup_{w+1}", config, output_dir)
        vg = (r["metrics"].get("source_dist") or {}).get("vertex_grounding", 0)
        rd = r["metrics"].get("refs_docs_count")
        print(f"  [warmup {w+1}] exit={r['exit_code']} elapsed={r['elapsed_sec_driver']:.1f}s "
              f"vertex={vg} refs={rd}", flush=True)
        warmup_results.append(r)
        if w < config["n_warmup"] - 1 or config["n_runs"] > 0:
            time.sleep(config["inter_run_sleep"])

    runs: list[dict] = []
    for i in range(config["n_runs"]):
        pre_clear_ns(ns_web, output_dir)
        r = run_single(state_label, f"run_{i+1}", config, output_dir)
        vg = (r["metrics"].get("source_dist") or {}).get("vertex_grounding", 0)
        rd = r["metrics"].get("refs_docs_count")
        print(f"  [run {i+1}] exit={r['exit_code']} elapsed={r['elapsed_sec_driver']:.1f}s "
              f"vertex={vg} refs={rd}", flush=True)
        runs.append(r)
        if i < config["n_runs"] - 1:
            time.sleep(config["inter_run_sleep"])

    return {"state": state_label, "warmup": warmup_results, "runs": runs}


def summarize_runs(runs: list[dict]) -> dict:
    """N=3 결과 mean/stdev/cv (vertex_grounding + elapsed)."""
    import statistics as st
    vgs = [(r["metrics"].get("source_dist") or {}).get("vertex_grounding", 0) for r in runs]
    els = [r["elapsed_sec_driver"] for r in runs]
    refs = [r["metrics"].get("refs_docs_count") or 0 for r in runs]

    def _stats(xs):
        if not xs:
            return {}
        mean = st.fmean(xs)
        stdev = st.stdev(xs) if len(xs) >= 2 else 0.0
        cv = (stdev / mean * 100) if mean else 0.0
        return {"mean": round(mean, 3), "stdev": round(stdev, 3),
                "cv_pct": round(cv, 2), "min": min(xs), "max": max(xs)}

    return {
        "n": len(runs),
        "vertex_grounding": _stats(vgs),
        "elapsed_sec_driver": _stats(els),
        "refs_docs_count": _stats(refs),
        "exit_codes": [r["exit_code"] for r in runs],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 patch-based 측정 driver")
    ap.add_argument("--topic-slug", default=DEFAULTS["topic_slug"])
    ap.add_argument("--topic-title", default=DEFAULTS["topic_title"])
    ap.add_argument("--trigger", default=DEFAULTS["trigger"])
    ap.add_argument("--n-runs", type=int, default=DEFAULTS["n_runs"])
    ap.add_argument("--n-warmup", type=int, default=DEFAULTS["n_warmup"])
    ap.add_argument("--per-run-timeout", type=float, default=DEFAULTS["per_run_timeout"])
    ap.add_argument("--inter-run-sleep", type=float, default=DEFAULTS["inter_run_sleep"])
    ap.add_argument("--recursion-limit", type=int, default=DEFAULTS["recursion_limit"])
    ap.add_argument("--patch", type=Path, default=PATCH_PATH)
    ap.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    ap.add_argument("--skip-reverted", action="store_true",
                    help="reverted state 측정 생략 (patched only)")
    args = ap.parse_args()

    config = {
        "topic_slug": args.topic_slug,
        "topic_title": args.topic_title,
        "trigger": args.trigger,
        "n_runs": args.n_runs,
        "n_warmup": args.n_warmup,
        "per_run_timeout": args.per_run_timeout,
        "inter_run_sleep": args.inter_run_sleep,
        "recursion_limit": args.recursion_limit,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 사전 검증: working tree clean
    ok, stat = verify_clean()
    if not ok:
        print(f"[fatal] working tree not clean. diff stat:\n{stat}", flush=True)
        return 2

    # patch 파일 존재 검증
    if not args.patch.exists():
        print(f"[fatal] patch 파일 부재: {args.patch}", flush=True)
        return 3

    print(f"[start] {_ts()} topic={config['topic_slug']} N={config['n_runs']} warmup={config['n_warmup']}")
    print(f"[config] timeout={config['per_run_timeout']}s sleep={config['inter_run_sleep']}s")
    print(f"[patch] {args.patch}")

    t_total_start = time.monotonic()
    results: dict[str, Any] = {
        "meta": {
            "ts_start": _ts(),
            "config": config,
            "patch_path": str(args.patch),
            "project_root": str(PROJECT_ROOT),
            "git_head": _git("rev-parse", "HEAD").stdout.strip(),
        },
    }

    try:
        # 1. patched state 측정 (현재 브랜치 상태)
        results["patched"] = measure_state("patched", config, args.output_dir)
        results["patched"]["summary"] = summarize_runs(results["patched"]["runs"])

        if not args.skip_reverted:
            # 2. patch revert
            print(f"\n[patch] reverse apply {args.patch.name}", flush=True)
            apply_patch(args.patch, reverse=True)
            ok, stat = verify_clean()
            print(f"[patch] post-revert clean={ok} stat=\n{stat}", flush=True)

            # 3. reverted state 측정
            results["reverted"] = measure_state("reverted", config, args.output_dir)
            results["reverted"]["summary"] = summarize_runs(results["reverted"]["runs"])
    finally:
        # 4. patch 복구 (반드시 실행)
        ok_pre, _ = verify_clean()
        if not ok_pre:
            print(f"\n[patch] recover (forward apply {args.patch.name})", flush=True)
            try:
                apply_patch(args.patch, reverse=False)
            except Exception as e:
                print(f"[fatal] patch recover fail: {e}", flush=True)

        # 5. 사후 검증
        ok, stat = verify_clean()
        results["meta"]["post_clean"] = ok
        results["meta"]["post_stat"] = stat
        print(f"\n[final] post-clean={ok}", flush=True)
        if not ok:
            print(f"  stat:\n{stat}", flush=True)

    results["meta"]["ts_end"] = _ts()
    results["meta"]["total_elapsed_sec"] = round(time.monotonic() - t_total_start, 2)

    summary_path = args.output_dir / f"phase3_summary_{_ts()}.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[saved] {summary_path}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
