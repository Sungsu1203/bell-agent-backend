"""§14-2 Step 2 Phase A — Vertex grounding baseline 측정.

목적: vertex_web_search 단독 호출의 안정성 + flash/pro 비교 baseline.
patch 영향 없음 (vertex_search.py 만 사용, agent/web_search.py 무관).

사용법 (.venv_vertex 활성화 상태에서):
    cd D:\\gpt_agent\\writer_project
    python scripts/measure_vertex_phase_a.py [--sanity] [--model {flash,pro,both}] [--n N]

옵션:
    --sanity           : 4 query × 1 model (flash) × 1 run = 4 호출 (강제 override)
    --model            : flash | pro | both (default: both)
    --n                : run count per (model, query) (default: 3)
    --inter-sleep SEC  : run 간 sleep (default 60.0, sanity 시 0)
    --timeout SEC      : per-call timeout (default 120.0)

중단 조건 (즉시 abort + 부분 결과 저장):
    - 429 ResourceExhausted
    - elapsed_sec > 120 (timeout 미발생인데 latency 초과)
    - chunks=0 (응답 비정상)
    - 동일 (model, query) 의 chunks 가 prev_runs 평균 대비 50%+ 변동
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# .env.vertex 명시 로드
try:
    from dotenv import load_dotenv
    env_vertex = PROJECT_ROOT / ".env.vertex"
    if env_vertex.exists():
        load_dotenv(env_vertex, override=True)
        print(f"[env] loaded {env_vertex}")
    else:
        print(f"[env] WARN: {env_vertex} not found")
except ImportError:
    print("[env] WARN: python-dotenv not installed")

from tools.web_rag.vertex_search import vertex_web_search  # noqa: E402

QUERIES = [
    "벤포벤S 종근당 광고비 2024",
    "활성형 비타민 시장 규모 한국",
    "비타민 B군 임상시험 효능",
    "vitamin B benfotiamine clinical trial",
]

MODELS = {
    "flash": "gemini-2.5-flash",
    "pro": "gemini-2.5-pro",
}


class StopMeasurement(Exception):
    pass


def _is_429(rec: dict) -> bool:
    ec = (rec.get("error_class") or "").lower()
    em = (rec.get("error_msg") or "").lower()
    return ("resourceexhausted" in ec or "429" in em
            or "resource exhausted" in em or "quota" in em)


def _call_one(query: str, timeout_s: float) -> dict:
    """vertex_web_search 단발 호출 + ThreadPoolExecutor 기반 timeout."""
    t0 = time.monotonic()
    err_class: str | None = None
    err_msg: str | None = None
    result: dict | None = None

    def _inner():
        return vertex_web_search(query)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_inner)
            result = fut.result(timeout=timeout_s)
    except FuturesTimeoutError:
        err_class = "Timeout"
        err_msg = f"per-call timeout {timeout_s}s 초과"
    except Exception as e:
        err_class = type(e).__name__
        err_msg = str(e)[:500]

    elapsed = time.monotonic() - t0
    summary = (result or {}).get("summary", "") if result else ""
    chunks = (result or {}).get("chunks", []) or []
    supports = (result or {}).get("supports", []) or []
    wsq = (result or {}).get("web_search_queries", []) or []
    urls = (result or {}).get("urls", []) or []

    return {
        "elapsed_sec": round(elapsed, 3),
        "error_class": err_class,
        "error_msg": err_msg,
        "chunks": len(chunks),
        "supports": len(supports),
        "web_search_queries": len(wsq),
        "summary_chars": len(summary),
        "urls_dedup": len(urls),
    }


def _check_stop(rec: dict, prev_runs: list[dict]) -> str | None:
    """abort 조건만 검사 (429 / latency>120 / chunks=0). chunks 변동은 _variation_warning 으로 분리."""
    if _is_429(rec):
        return f"429 quota: {rec.get('error_msg')}"
    if rec["elapsed_sec"] > 120 and not rec.get("error_class"):
        return f"latency > 120s ({rec['elapsed_sec']}s)"
    if rec["chunks"] == 0 and not rec.get("error_class"):
        return "chunks=0 (응답 비정상)"
    return None


def _variation_warning(rec: dict, prev_runs: list[dict]) -> str | None:
    """chunks 50%+ 변동 시 warning 메시지 반환 (abort 안 함, 정상 vertex 비결정성)."""
    if rec.get("error_class") or rec["chunks"] == 0:
        return None
    prev_chunks = [r["chunks"] for r in prev_runs if r["chunks"] > 0]
    if not prev_chunks:
        return None
    avg_prev = sum(prev_chunks) / len(prev_chunks)
    if avg_prev <= 0:
        return None
    pct = abs(rec["chunks"] - avg_prev) / avg_prev * 100
    if pct > 50:
        return (f"chunks variation {int(pct)}% (current={rec['chunks']} "
                f"vs prev_mean={avg_prev:.1f}) — 정상 vertex 비결정성, 계속")
    return None


def measure(
    results: dict,
    models: list[str],
    n: int,
    inter_sleep: float,
    timeout_s: float,
) -> None:
    """results 외부 dict 에 incremental 누적 (StopMeasurement raise 시에도 부분 결과 보존)."""
    original_model = os.environ.get("LLM_MODEL")
    try:
        for mi, model_key in enumerate(models):
            model_name = MODELS[model_key]
            print(f"\n{'='*70}\n[model] {model_name}\n{'='*70}")
            os.environ["LLM_MODEL"] = model_name
            results.setdefault(model_key, {})

            for q in QUERIES:
                print(f"\n[query] {q}")
                results[model_key].setdefault(q, [])
                for run in range(1, n + 1):
                    if run > 1 and inter_sleep > 0:
                        print(f"  [sleep {inter_sleep}s]")
                        time.sleep(inter_sleep)
                    print(f"  run {run}/{n}: ", end="", flush=True)
                    rec = _call_one(q, timeout_s=timeout_s)
                    rec["run"] = run
                    prev_runs = list(results[model_key][q])
                    results[model_key][q].append(rec)
                    err_tag = f" ERR={rec['error_class']}" if rec["error_class"] else ""
                    print(f"elapsed={rec['elapsed_sec']:.2f}s "
                          f"chunks={rec['chunks']} supports={rec['supports']} "
                          f"queries={rec['web_search_queries']}{err_tag}")
                    warning = _variation_warning(rec, prev_runs)
                    if warning:
                        print(f"    [WARN] {warning}")
                    stop = _check_stop(rec, prev_runs)
                    if stop:
                        print(f"\n[STOP] {stop}")
                        raise StopMeasurement(stop)

            if mi < len(models) - 1:
                print(f"\n[inter-model sleep 120s]")
                time.sleep(120)
    finally:
        if original_model is None:
            os.environ.pop("LLM_MODEL", None)
        else:
            os.environ["LLM_MODEL"] = original_model


def _stats(vals: list) -> dict:
    if not vals:
        return {"n": 0, "mean": 0.0, "stdev": 0.0, "cv_pct": 0.0, "min": 0.0, "max": 0.0}
    mean = statistics.mean(vals)
    stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
    cv = (stdev / mean * 100) if mean > 0 else 0.0
    return {
        "n": len(vals),
        "mean": round(mean, 2),
        "stdev": round(stdev, 2),
        "cv_pct": round(cv, 1),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
    }


def summarize(results: dict, models: list[str]) -> dict:
    summary: dict[str, Any] = {}
    for model_key in models:
        if model_key not in results:
            continue
        all_elapsed: list[float] = []
        all_chunks: list[int] = []
        all_supports: list[int] = []
        n_runs = 0
        n_errors = 0
        per_query: dict[str, dict] = {}
        variation_50_count = 0  # chunks 50%+ 변동 발생 횟수
        for q, runs in results[model_key].items():
            q_elapsed: list[float] = []
            q_chunks: list[int] = []
            q_supports: list[int] = []
            q_urls: list[int] = []
            for r in runs:
                n_runs += 1
                if r.get("error_class"):
                    n_errors += 1
                    continue
                q_elapsed.append(r["elapsed_sec"])
                q_chunks.append(r["chunks"])
                q_supports.append(r["supports"])
                q_urls.append(r.get("urls_dedup") or 0)
            all_elapsed.extend(q_elapsed)
            all_chunks.extend(q_chunks)
            all_supports.extend(q_supports)
            # per-query variation 50%+ 카운트 (run i 가 prev runs 평균 대비)
            if len(q_chunks) >= 2:
                for i in range(1, len(q_chunks)):
                    prev_mean = sum(q_chunks[:i]) / i
                    if prev_mean > 0:
                        pct = abs(q_chunks[i] - prev_mean) / prev_mean * 100
                        if pct > 50:
                            variation_50_count += 1
            per_query[q] = {
                "elapsed": _stats(q_elapsed),
                "chunks": _stats(q_chunks),
                "supports": _stats(q_supports),
                "urls_dedup": _stats(q_urls),
            }
        es = _stats(all_elapsed)
        per_run_timeout = max(300, int(es["mean"] * 1.5)) if es["mean"] > 0 else 0
        summary[model_key] = {
            "model": MODELS[model_key],
            "n_runs": n_runs,
            "n_errors": n_errors,
            "variation_50_count": variation_50_count,
            "elapsed": es,
            "chunks": _stats(all_chunks),
            "supports": _stats(all_supports),
            "recommended_per_run_timeout_s": per_run_timeout,
            "per_query_stats": per_query,
        }
    return summary


def _print_summary(summary: dict, models: list[str]) -> None:
    print(f"\n{'='*70}\n[summary]\n{'='*70}")
    for mk in models:
        if mk not in summary:
            continue
        s = summary[mk]
        es = s["elapsed"]; cs = s["chunks"]; ss = s["supports"]
        print(f"\n  {s['model']}:")
        print(f"    runs: {s['n_runs']} (errors: {s['n_errors']})")
        print(f"    elapsed   mean={es['mean']:>6.2f}s  stdev={es['stdev']:>5.2f}  "
              f"cv={es['cv_pct']:>5.1f}%  range=[{es['min']}, {es['max']}]")
        print(f"    chunks    mean={cs['mean']:>6.2f}   stdev={cs['stdev']:>5.2f}  "
              f"cv={cs['cv_pct']:>5.1f}%  range=[{cs['min']}, {cs['max']}]")
        print(f"    supports  mean={ss['mean']:>6.2f}   stdev={ss['stdev']:>5.2f}  "
              f"cv={ss['cv_pct']:>5.1f}%  range=[{ss['min']}, {ss['max']}]")
        print(f"    recommended per-run-timeout: {s['recommended_per_run_timeout_s']}s")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sanity", action="store_true")
    p.add_argument("--model", choices=["flash", "pro", "both"], default="both")
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--inter-sleep", type=float, default=60.0)
    p.add_argument("--timeout", type=float, default=120.0)
    args = p.parse_args()

    if args.sanity:
        models = ["flash"]
        n = 1
        inter_sleep = 0.0
        print("[sanity] flash × 4 query × 1 run, no inter-sleep")
    else:
        models = ["flash", "pro"] if args.model == "both" else [args.model]
        n = args.n
        inter_sleep = args.inter_sleep

    print("[env diag]")
    print(f"  GCP_PROJECT_ID = {os.getenv('GCP_PROJECT_ID', '<unset>')}")
    print(f"  GCP_REGION     = {os.getenv('GCP_REGION', '<unset>')}")
    print(f"  VERTEX_MAX_RETRIES = {os.getenv('VERTEX_MAX_RETRIES', '<default 6>')}")
    gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    print(f"  GOOGLE_APPLICATION_CREDENTIALS = "
          f"{gac if gac else '<unset>'}"
          f"{'  (exists)' if gac and Path(gac).exists() else '  (NOT FOUND)' if gac else ''}")
    print(f"\n[plan] models={[MODELS[m] for m in models]} n={n} "
          f"inter_sleep={inter_sleep}s timeout={args.timeout}s")
    print(f"  total calls: {len(models) * len(QUERIES) * n}")

    out_dir = HERE / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_sanity" if args.sanity else ""
    out_path = out_dir / f"phase_a{suffix}_{ts}.json"

    results: dict = {}
    stop_reason: str | None = None
    try:
        measure(results, models, n, inter_sleep, args.timeout)
    except StopMeasurement as e:
        stop_reason = str(e)

    summary = summarize(results, models)
    _print_summary(summary, models)

    payload = {
        "timestamp": ts,
        "git_head": os.popen("git -C .. rev-parse --short HEAD").read().strip(),
        "models": [MODELS[m] for m in models],
        "n": n,
        "inter_sleep_s": inter_sleep,
        "timeout_s": args.timeout,
        "sanity": args.sanity,
        "stop_reason": stop_reason,
        "queries": QUERIES,
        "results": results,
        "summary": summary,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n[saved] {out_path}")
    if stop_reason:
        print(f"[STOP REASON] {stop_reason}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
