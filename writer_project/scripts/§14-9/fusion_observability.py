"""§14-9 Step B Phase 3 — fusion observability driver.

목적:
- vertex_grounding + legacy chain 의 combined_items inspection
- web_results_to_documents 호출 후 Document.metadata 의 신규 키
  (backend / alt_urls / chunk_domain) 보존율 측정
- A/B 측정: patch 전 (3 keys whitelist) vs patch 후 (확장 whitelist)
  ※ patch 후 본 driver 실행만 가능 (patch 전은 git revert 또는 baseline raw 재분석)

호출 path:
  1. vertex_web_search(q)              직접 호출 → vertex items 빌드 (graph state 우회)
  2. tools.web_rag.search.web_search.invoke({"query": q})  → legacy items
  3. combined = vertex_items + legacy_items
  4. web_results_to_documents(combined) → Document list
  5. per-source metadata key 분포 측정 (backend / alt_urls / chunk_domain 보존율)

§13-7 측정 표준 정합 — max_retries=0, warmup, per-call timeout, inter-run sleep, utf-8.

STOP 조건 (즉시 abort + 부분 결과 저장):
  - 429 ResourceExhausted (vertex quota)
  - per-call timeout (default 240s)

호출 예시:
  D:/gpt_agent/.venv_vertex/Scripts/python.exe scripts/§14-9/fusion_observability.py \\
    --provider vertexai --topic venfobel-vitamin \\
    --warmup 2 --n 3 --timeout 240 --inter-sleep 60 \\
    --queries scripts/§14-9/_q1_q4.txt \\
    --out-dir scripts/output/§14-9 --tag phase3_after
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]  # scripts/§14-9/ -> scripts/ -> writer_project/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")


DEFAULT_QUERIES = [
    "벤포벤S 종근당 광고비 2024",
    "활성형 비타민 시장 규모 한국",
    "비타민 B군 임상시험 효능",
    "vitamin B benfotiamine clinical trial",
]


class StopMeasurement(Exception):
    pass


def _is_429(rec: dict) -> bool:
    ec = (rec.get("error_class") or "").lower()
    em = (rec.get("error_msg") or "").lower()
    return (
        "resourceexhausted" in ec
        or "429" in em
        or "resource exhausted" in em
        or "quota" in em
    )


def _load_provider_env(provider: str) -> Path | None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        print("[env] WARN: python-dotenv not installed", flush=True)
        return None
    global_env = PROJECT_ROOT / ".env"
    if global_env.exists():
        load_dotenv(global_env, override=False)
        print(f"[env] loaded {global_env} (override=False)", flush=True)
    prov_file = "vertex" if provider in {"vertex", "vertexai"} else provider
    overlay = PROJECT_ROOT / f".env.{prov_file}"
    if overlay.exists():
        load_dotenv(overlay, override=True)
        print(f"[env] loaded {overlay} (override=True)", flush=True)
        return overlay
    print(f"[env] WARN: {overlay} not found", flush=True)
    return None


def _build_vertex_items(query: str) -> list[dict]:
    # agent/web_search.py:766-797 의 vertex merge path 재현 — graph state 우회.
    from tools.web_rag.vertex_search import vertex_web_search
    vr = vertex_web_search(query)
    v_chunks = vr.get("chunks") or []
    v_supports = vr.get("supports") or []
    items: list[dict] = []
    for support in v_supports:
        indices = support.get("chunk_indices") or []
        valid_indices = [i for i in indices if 0 <= i < len(v_chunks)]
        if not valid_indices:
            continue
        rep_idx = valid_indices[0]
        rep_chunk = v_chunks[rep_idx]
        rep_url = rep_chunk.get("uri") or ""
        if not rep_url:
            continue
        alt_urls = [
            v_chunks[i].get("uri") for i in valid_indices[1:]
            if v_chunks[i].get("uri")
        ]
        items.append({
            "title": "",
            "url": rep_url,
            "content": support.get("text") or "",
            "raw_content": "",
            "source": rep_url,
            "metadata": {
                "backend": "vertex_grounding",
                "alt_urls": alt_urls,
                "chunk_domain": rep_chunk.get("domain") or "",
            },
        })
    return items


def _legacy_call(query: str) -> list[dict]:
    from tools.web_rag.search import web_search
    ret = web_search.invoke({"query": query})
    if isinstance(ret, tuple) and len(ret) >= 2:
        items = list(ret[0] or [])
    elif isinstance(ret, list):
        items = list(ret)
    elif isinstance(ret, dict):
        items = list(ret.get("results") or ret.get("items") or [])
    else:
        items = []
    return [it for it in items if isinstance(it, dict)]


def _call_fusion(query: str, timeout_s: float) -> dict:
    t0 = time.monotonic()
    err_class: str | None = None
    err_msg: str | None = None
    vertex_items: list[dict] = []
    legacy_items: list[dict] = []
    docs: list[Any] = []

    def _inner():
        v = _build_vertex_items(query)
        l = _legacy_call(query)
        from tools.web_rag.ingest_docs import web_results_to_documents
        combined = v + l
        d = web_results_to_documents(combined)
        return v, l, d

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_inner)
            vertex_items, legacy_items, docs = fut.result(timeout=timeout_s)
    except FuturesTimeoutError:
        err_class = "Timeout"
        err_msg = f"per-call timeout {timeout_s}s 초과"
    except Exception as e:
        err_class = type(e).__name__
        err_msg = str(e)[:500]

    elapsed = time.monotonic() - t0

    # Document.metadata key 분포 측정 — Document 의 source 가 vertex item url 과
    # 일치하는 케이스를 vertex 출처로 분류.
    vertex_urls = {it.get("url") or it.get("source") for it in vertex_items if it.get("url") or it.get("source")}
    vertex_doc_count = 0
    vertex_doc_meta_keys_observed: set[str] = set()
    legacy_doc_count = 0
    vertex_promoted_full = 0  # backend + alt_urls + chunk_domain 모두 있는 doc
    vertex_promoted_partial = 0  # 일부만 있는 doc
    sample_vertex_meta: list[dict] = []
    sample_legacy_meta: list[dict] = []
    for d in docs:
        meta = dict(getattr(d, "metadata", {}) or {})
        src = meta.get("source") or ""
        is_vertex = src in vertex_urls
        if is_vertex:
            vertex_doc_count += 1
            vertex_doc_meta_keys_observed.update(meta.keys())
            has_bk = meta.get("backend") == "vertex_grounding"
            has_cd = bool(meta.get("chunk_domain"))
            has_au = bool(meta.get("alt_urls"))
            if has_bk and has_cd and has_au:
                vertex_promoted_full += 1
            elif has_bk or has_cd or has_au:
                vertex_promoted_partial += 1
            if len(sample_vertex_meta) < 3:
                sample_vertex_meta.append({k: (v if isinstance(v, str) else str(v)[:80]) for k, v in meta.items()})
        else:
            legacy_doc_count += 1
            if len(sample_legacy_meta) < 3:
                sample_legacy_meta.append({k: (v if isinstance(v, str) else str(v)[:80]) for k, v in meta.items()})

    vertex_promote_rate = (vertex_promoted_full / vertex_doc_count) if vertex_doc_count else 0.0

    return {
        "elapsed_sec": round(elapsed, 3),
        "error_class": err_class,
        "error_msg": err_msg,
        "vertex_items_count": len(vertex_items),
        "legacy_items_count": len(legacy_items),
        "docs_total": len(docs),
        "vertex_doc_count": vertex_doc_count,
        "legacy_doc_count": legacy_doc_count,
        "vertex_promoted_full": vertex_promoted_full,
        "vertex_promoted_partial": vertex_promoted_partial,
        "vertex_promote_rate_full": round(vertex_promote_rate, 3),
        "vertex_doc_meta_keys_observed": sorted(vertex_doc_meta_keys_observed),
        "sample_vertex_meta": sample_vertex_meta,
        "sample_legacy_meta": sample_legacy_meta,
    }


def _check_stop(rec: dict) -> str | None:
    if _is_429(rec):
        return f"429 quota: {rec.get('error_msg')}"
    if rec.get("error_class") == "Timeout":
        return f"timeout: {rec.get('error_msg')}"
    return None


def measure(
    queries: list[str],
    warmup: int,
    n: int,
    inter_sleep: float,
    timeout_s: float,
) -> dict:
    results: dict[str, Any] = {
        "queries": queries,
        "warmup_n": warmup,
        "measured_n": n,
        "inter_sleep_sec": inter_sleep,
        "per_call_timeout_sec": timeout_s,
        "warmup_records": [],
        "measured_records": [],
        "abort": None,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    total_calls = warmup + n
    call_idx = 0
    try:
        for q in queries:
            print(f"\n[query] {q}", flush=True)
            for run in range(1, total_calls + 1):
                if call_idx > 0 and inter_sleep > 0:
                    print(f"  [sleep {inter_sleep}s]", flush=True)
                    time.sleep(inter_sleep)
                call_idx += 1
                tag = "warmup" if run <= warmup else "measured"
                print(f"  {tag} {run}/{total_calls}: ", end="", flush=True)
                rec = _call_fusion(q, timeout_s=timeout_s)
                rec["run"] = run
                rec["tag"] = tag
                rec["query"] = q
                if tag == "warmup":
                    results["warmup_records"].append(rec)
                else:
                    results["measured_records"].append(rec)
                err = f" ERR={rec.get('error_class')}" if rec.get("error_class") else ""
                print(
                    f"elapsed={rec['elapsed_sec']:.2f}s "
                    f"v_items={rec['vertex_items_count']} l_items={rec['legacy_items_count']} "
                    f"docs={rec['docs_total']} (v_doc={rec['vertex_doc_count']} l_doc={rec['legacy_doc_count']}) "
                    f"v_promote_full={rec['vertex_promoted_full']}/{rec['vertex_doc_count']} "
                    f"({rec['vertex_promote_rate_full']*100:.0f}%){err}",
                    flush=True,
                )
                stop = _check_stop(rec)
                if stop:
                    print(f"\n[STOP] {stop}", flush=True)
                    raise StopMeasurement(stop)
    except StopMeasurement as e:
        results["abort"] = str(e)
    except Exception as e:
        results["abort"] = f"unexpected {type(e).__name__}: {str(e)[:300]}"
        results["abort_traceback"] = traceback.format_exc()[:1500]
    results["ended_at"] = datetime.now().isoformat(timespec="seconds")
    return results


def _stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    m = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    cv = (sd / m * 100) if m > 0 else 0.0
    return {"n": len(vals), "mean": round(m, 2), "stdev": round(sd, 2), "cv_pct": round(cv, 1),
            "min": round(min(vals), 2), "max": round(max(vals), 2)}


def summarize(results: dict) -> dict:
    measured = [r for r in results.get("measured_records", []) if not r.get("error_class")]
    elapsed_all = [r["elapsed_sec"] for r in measured]
    v_items_all = [r["vertex_items_count"] for r in measured]
    v_doc_all = [r["vertex_doc_count"] for r in measured]
    v_promo_full_all = [r["vertex_promoted_full"] for r in measured]
    v_promo_rate_all = [r["vertex_promote_rate_full"] for r in measured]
    n_errors = sum(1 for r in results.get("measured_records", []) if r.get("error_class"))

    per_query: dict[str, dict] = {}
    for q in results.get("queries", []):
        runs = [r for r in measured if r.get("query") == q]
        per_query[q] = {
            "n": len(runs),
            "elapsed": _stats([r["elapsed_sec"] for r in runs]),
            "vertex_items_count": _stats([float(r["vertex_items_count"]) for r in runs]),
            "vertex_doc_count": _stats([float(r["vertex_doc_count"]) for r in runs]),
            "vertex_promoted_full": _stats([float(r["vertex_promoted_full"]) for r in runs]),
            "vertex_promote_rate_full_mean": round(
                statistics.mean([r["vertex_promote_rate_full"] for r in runs]) if runs else 0.0, 3
            ),
        }

    return {
        "n_measured": len(measured),
        "n_errors": n_errors,
        "elapsed": _stats(elapsed_all),
        "vertex_items_count": _stats([float(v) for v in v_items_all]),
        "vertex_doc_count": _stats([float(v) for v in v_doc_all]),
        "vertex_promoted_full": _stats([float(v) for v in v_promo_full_all]),
        "vertex_promote_rate_full_overall_mean": round(
            statistics.mean(v_promo_rate_all) if v_promo_rate_all else 0.0, 3
        ),
        "per_query": per_query,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="§14-9 Phase 3 fusion observability driver")
    ap.add_argument("--provider", choices=["vertexai", "openai"], default="vertexai")
    ap.add_argument("--topic", default="venfobel-vitamin")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--inter-sleep", type=float, default=60.0)
    ap.add_argument("--queries", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--sanity", action="store_true", help="--warmup 0 --n 1 --inter-sleep 0 강제")
    args = ap.parse_args()

    if args.n > 5:
        print(f"[ABORT] --n {args.n} > 5", flush=True)
        return 2
    if args.timeout > 300:
        print(f"[ABORT] --timeout {args.timeout} > 300s", flush=True)
        return 2

    if args.sanity:
        args.warmup = 0
        args.n = 1
        args.inter_sleep = 0.0
        print("[sanity] warmup=0 n=1 inter_sleep=0 강제", flush=True)

    _load_provider_env(args.provider)

    # args.topic 우선 override (driver setdefault 패턴 회피)
    os.environ["TOPIC_SLUG"] = args.topic

    queries: list[str] = DEFAULT_QUERIES
    if args.queries:
        qp = Path(args.queries)
        if qp.exists():
            queries = [
                ln.strip() for ln in qp.read_text(encoding="utf-8").splitlines() if ln.strip()
            ]

    print(
        f"\n[start] provider={args.provider} topic={args.topic} "
        f"warmup={args.warmup} n={args.n} timeout={args.timeout}s "
        f"inter_sleep={args.inter_sleep}s queries={len(queries)}",
        flush=True,
    )

    results = measure(queries, args.warmup, args.n, args.inter_sleep, args.timeout)
    results["summary"] = summarize(results)

    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "scripts" / "output" / "§14-9"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{args.tag}" if args.tag else ""
    out_path = out_dir / f"phase3_fusion_obs_{args.provider}{suffix}_{ts}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[summary] {json.dumps(results['summary'], ensure_ascii=False)}", flush=True)
    print(f"[saved] {out_path}", flush=True)

    if results.get("abort"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
