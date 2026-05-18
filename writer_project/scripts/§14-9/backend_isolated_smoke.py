"""§14-9 Step B Phase 1 - backend isolated smoke driver.

목적: vertex_grounding 단독 / legacy chain 단독 / 양쪽 병합 3 mode 의
backend latency · items · per-backend distribution · URL dedup 측정.

설계 정합:
- §14-2 Phase A driver 패턴 (scripts/measure_vertex_phase_a.py) 재활용.
- §13-7 측정 표준 (max_retries=0, warmup, per-call timeout, inter-run sleep, utf-8).
- §14-9 Step A § 6-d 박제 (driver 신규 작성 vs 재활용 분리).
- production code (agent/, tools/, core/) 무수정 - 본 driver 외 작성 0.

호출 path (mode 별):
  vertex_grounding : tools.web_rag.vertex_search.vertex_web_search(query)        직접
  legacy_only      : tools.web_rag.search.web_search.invoke({"query": q})       직접
  both             : agent.web_search._run_web_search_with_guard(q, ...)        직접

사용법 (caller PowerShell 가 venv 전환):
  .venv_vertex   activate → python scripts/diag/§14-9/backend_isolated_smoke.py
                 --provider vertexai --backend vertex_grounding --n 3 --warmup 2
  .venv_openai   activate → python scripts/diag/§14-9/backend_isolated_smoke.py
                 --provider openai   --backend legacy_only      --n 3 --warmup 2

STOP 조건 (즉시 abort + 부분 결과 저장):
  - 429 ResourceExhausted (vertex quota - §14-_14.md L107 Pitfall)
  - per-call timeout (default 240s, vertex baseline_mean 24.93s × ~10 margin)
  - chunks=0 (vertex 응답 비정상, vertex_grounding mode only)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import statistics
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Log capture (Task 2 보강) ────────────────────────────────────────────────
class _BackendLogHandler(logging.Handler):
    """tools.web_rag.search 의 backend invocation/result 로그를 구조화 캡처.

    캡처 패턴 (search.py 정합):
      - "[web_search][chain] <chain> | policy=..."         search.py:1496
      - "[web_search] calling backend=<bk> variant=<v> ..." search.py:1556
      - "[web_search] backend=<bk> variant=<v> got=<n>"     search.py:1614/1617
      - "[web_search][backend tried] <bk> got=<n> in ..."  search.py:1674
      - "[web_search][backend] <bk> | got=<n> ..."         search.py:1817

    record schema: list[{event, backend?, variant?, got?, raw_msg, timestamp}]
    """
    _RE_CHAIN = re.compile(r"\[web_search\]\[chain\]\s+(.+?)\s+\|")
    _RE_CALL = re.compile(r"\[web_search\]\s+calling\s+backend=(\S+)\s+variant=(\S+)")
    _RE_GOT = re.compile(r"\[web_search\]\s+backend=(\S+)\s+variant=(\S+)\s+got=(\d+)")
    _RE_TRIED = re.compile(r"\[web_search\]\[backend tried\]\s+(\S+)\s+got=\s*(\d+)")
    _RE_FINAL = re.compile(r"\[web_search\]\[backend\]\s+(\S+)\s+\|\s+got=(\d+)")
    _RE_SKIPPED = re.compile(r"\[web_search\]\s+time budget exceeded.*?backend=(\S+)|reserve budget.*?skip\s+(\S+)")

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.events: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            return
        ts = round(time.monotonic(), 3)
        if (m := self._RE_GOT.search(msg)):
            self.events.append({"event": "got", "backend": m.group(1), "variant": m.group(2), "got": int(m.group(3)), "raw_msg": msg[:200], "t": ts})
        elif (m := self._RE_TRIED.search(msg)):
            self.events.append({"event": "tried", "backend": m.group(1), "got": int(m.group(2)), "raw_msg": msg[:200], "t": ts})
        elif (m := self._RE_FINAL.search(msg)):
            self.events.append({"event": "final", "backend": m.group(1), "got": int(m.group(2)), "raw_msg": msg[:200], "t": ts})
        elif (m := self._RE_CALL.search(msg)):
            self.events.append({"event": "call", "backend": m.group(1), "variant": m.group(2), "raw_msg": msg[:200], "t": ts})
        elif (m := self._RE_CHAIN.search(msg)):
            self.events.append({"event": "chain", "chain": m.group(1).strip(), "raw_msg": msg[:200], "t": ts})
        elif (m := self._RE_SKIPPED.search(msg)):
            self.events.append({"event": "skipped", "backend": m.group(1) or m.group(2), "raw_msg": msg[:200], "t": ts})

    def reset(self) -> None:
        self.events = []

    def snapshot(self) -> list[dict]:
        return list(self.events)


_LOG_HANDLER: _BackendLogHandler | None = None


def _install_log_capture() -> _BackendLogHandler:
    """tools.web_rag.search logger 에 capture handler 설치 (1회만)."""
    global _LOG_HANDLER
    if _LOG_HANDLER is not None:
        return _LOG_HANDLER
    handler = _BackendLogHandler()
    target = logging.getLogger("tools.web_rag.search")
    target.addHandler(handler)
    if target.level == logging.NOTSET or target.level > logging.INFO:
        target.setLevel(logging.INFO)
    _LOG_HANDLER = handler
    print("[log-capture] installed handler on tools.web_rag.search (level=INFO)", flush=True)
    return handler


def _log_to_per_backend_dist(events: list[dict]) -> dict[str, int]:
    """log event list → backend별 got 합산 (per-backend distribution).

    - 'got' event: 각 backend×variant 호출 직후 success count (search.py:1614, INFO 레벨)
    - 'tried' / 'final' event: 후속 집계 로그 (DEBUG/INFO 혼재)
    - merge 패턴 (final bk='merged') 은 별도 키 'merged_total' 로 분리해 per-backend 와 혼동 방지
    """
    out: dict[str, int] = {}
    for ev in events:
        bk = ev.get("backend")
        if not bk:
            continue
        if bk == "merged":
            out["_merged_total"] = max(out.get("_merged_total", 0), int(ev.get("got", 0)))
            continue
        if ev.get("event") == "got":
            out[bk] = out.get(bk, 0) + int(ev.get("got", 0))
    return out

# writer_project 를 sys.path 에 올려 tools.* / agent.* / core.* import 가능
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]  # scripts/§14-9/ → scripts/ → writer_project/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# 기본 4 query (§14-2 Phase A 동일, KR 3 + EN 1)
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
    """global .env (override=False) + provider .env overlay (override=True) 명시 로드.

    core.config._load_dotenv_once 와 동일 우선순위 재현 - 단 driver 의 pre-dump
    시점부터 cred 가 보이도록 import 이전에 명시 호출.
    """
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        print("[env] WARN: python-dotenv not installed - process env only", flush=True)
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


def _pre_dump(provider: str, backend: str) -> dict:
    """측정 전 env / cred 정합 dump (axis 분리 박제 정합)."""
    dump = {
        "provider": provider,
        "backend_mode": backend,
        "LLM_PROVIDER": os.getenv("LLM_PROVIDER", ""),
        "LLM_MODEL": os.getenv("LLM_MODEL", ""),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", ""),
        "ANTHROPIC_MODEL": os.getenv("ANTHROPIC_MODEL", ""),
        "SKIP_VERTEX_SEARCH": os.getenv("SKIP_VERTEX_SEARCH", ""),
        "VERTEX_MAX_RETRIES": os.getenv("VERTEX_MAX_RETRIES", ""),
        "OPENAI_MAX_RETRIES": os.getenv("OPENAI_MAX_RETRIES", ""),
        "ANTHROPIC_MAX_RETRIES": os.getenv("ANTHROPIC_MAX_RETRIES", ""),
        "SEARCH_BACKENDS": os.getenv("SEARCH_BACKENDS", ""),
        "WEB_SEARCH_ENGINE": os.getenv("WEB_SEARCH_ENGINE", ""),
        "has_TAVILY_API_KEY": bool(os.getenv("TAVILY_API_KEY", "").strip()),
        "has_NAVER_CLIENT_ID": bool(os.getenv("NAVER_CLIENT_ID", "").strip()),
        "has_NAVER_CLIENT_SECRET": bool(os.getenv("NAVER_CLIENT_SECRET", "").strip()),
        "has_GCP_PROJECT_ID": bool(os.getenv("GCP_PROJECT_ID", "").strip()),
        "has_GOOGLE_APPLICATION_CREDENTIALS": bool(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        ),
        "python_exec": sys.executable,
        "cwd": os.getcwd(),
    }
    print(f"[pre-dump] {json.dumps(dump, ensure_ascii=False)}", flush=True)
    return dump


def _call_vertex_grounding(query: str, timeout_s: float) -> dict:
    """vertex_web_search() 직접 호출 (§14-2 Step 1b commit d88a8b9 정합)."""
    t0 = time.monotonic()
    err_class: str | None = None
    err_msg: str | None = None
    result: dict | None = None

    def _inner():
        from tools.web_rag.vertex_search import vertex_web_search  # late import
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

    # raw items count: supports 가 items 등가 (web_search.py:772-797 fusion path 정합)
    return {
        "mode": "vertex_grounding",
        "elapsed_sec": round(elapsed, 3),
        "error_class": err_class,
        "error_msg": err_msg,
        "raw_items": len(supports),
        "items_post_dedup": len(urls),  # vertex 내부 url dedup 후
        "per_backend_dist": {"vertex_grounding": len(supports)},
        "vertex_chunks": len(chunks),
        "vertex_supports": len(supports),
        "vertex_web_search_queries": len(wsq),
        "summary_chars": len(summary),
        "first_3_urls": urls[:3],
        "item_keys_observed": ["uri", "title", "domain"] if chunks else [],
    }


def _call_legacy_only(query: str, timeout_s: float) -> dict:
    """search.web_search.invoke() 직접 호출 (LangChain @tool wrapping bypass: .invoke)."""
    t0 = time.monotonic()
    err_class: str | None = None
    err_msg: str | None = None
    items: list[dict] = []
    json_path: str = ""

    # log capture reset (호출 전 events 초기화 — per-call 격리)
    if _LOG_HANDLER is not None:
        _LOG_HANDLER.reset()

    def _inner():
        from tools.web_rag.search import web_search  # late import
        return web_search.invoke({"query": query})

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_inner)
            ret = fut.result(timeout=timeout_s)
            if isinstance(ret, tuple) and len(ret) >= 2:
                items = list(ret[0] or [])
                json_path = str(ret[1] or "")
            elif isinstance(ret, list):
                items = list(ret)
            elif isinstance(ret, dict):
                items = list(ret.get("results") or ret.get("items") or [])
    except FuturesTimeoutError:
        err_class = "Timeout"
        err_msg = f"per-call timeout {timeout_s}s 초과"
    except Exception as e:
        err_class = type(e).__name__
        err_msg = str(e)[:500]

    elapsed = time.monotonic() - t0

    # per-backend dist 추정: items[i].get("source") + URL host 분석
    per_backend: dict[str, int] = {}
    urls_seen: list[str] = []
    keys_seen: set[str] = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        u = (it.get("url") or it.get("source") or "").strip()
        if u:
            urls_seen.append(u)
        keys_seen.update(it.keys())
        # naver_direct: openapi.naver.com 또는 KR 도메인 패턴, tavily: 다양 - heuristic
        host = u.split("/", 3)[2].lower() if "//" in u else ""
        bk = "unknown"
        if "naver.com" in host or "naver." in host:
            bk = "naver_direct"
        elif "wikipedia.org" in host or "pubmed" in host or "nih.gov" in host:
            bk = "tavily_or_cse"  # 둘 다 가능
        else:
            bk = "legacy_unattributed"
        per_backend[bk] = per_backend.get(bk, 0) + 1

    # dedup 효과 측정 (URL-level)
    urls_unique = list({u.split("#")[0].rstrip("/") for u in urls_seen if u})

    # log-based per-backend dist (heuristic 의 ground truth axis)
    log_events: list[dict] = []
    log_per_backend: dict[str, int] = {}
    if _LOG_HANDLER is not None:
        log_events = _LOG_HANDLER.snapshot()
        log_per_backend = _log_to_per_backend_dist(log_events)

    return {
        "mode": "legacy_only",
        "elapsed_sec": round(elapsed, 3),
        "error_class": err_class,
        "error_msg": err_msg,
        "raw_items": len(items),
        "items_post_dedup": len(urls_unique),
        "urls_before_dedup": len(urls_seen),
        "urls_after_dedup": len(urls_unique),
        "per_backend_dist": per_backend,  # heuristic (URL host 기반, 한계 박제)
        "per_backend_dist_log": log_per_backend,  # log-based (정확 attribution)
        "backend_log_events": log_events,
        "first_3_urls": urls_seen[:3],
        "item_keys_observed": sorted(keys_seen),
        "json_path_returned": json_path,
    }


def _call_both(query: str, timeout_s: float) -> dict:
    """_run_web_search_with_guard() 직접 호출 - vertex × legacy 병합 path 검증.

    주의: 이 함수는 graph state 를 요구하므로 simulation 어려움. Phase 1 scope 에서는
    'both' mode 는 stub 만 두고, 실제 측정은 vertex_grounding + legacy_only 단독 비교로 대체.
    상위 호출자가 합산 effect 를 분석.
    """
    return {
        "mode": "both",
        "elapsed_sec": 0.0,
        "error_class": "NotImplemented",
        "error_msg": "both mode 는 graph state 의존 - Phase 1 scope 외 (vertex+legacy 단독 측정으로 갈음)",
        "raw_items": 0,
        "items_post_dedup": 0,
        "per_backend_dist": {},
    }


_CALL_FN = {
    "vertex_grounding": _call_vertex_grounding,
    "legacy_only": _call_legacy_only,
    "both": _call_both,
}


def _check_stop(rec: dict, backend: str) -> str | None:
    if _is_429(rec):
        return f"429 quota: {rec.get('error_msg')}"
    if rec.get("error_class") == "Timeout":
        return f"timeout: {rec.get('error_msg')}"
    if backend == "vertex_grounding":
        if rec.get("vertex_chunks", 0) == 0 and not rec.get("error_class"):
            return "vertex chunks=0 (응답 비정상)"
    return None


def measure(
    provider: str,
    backend: str,
    queries: list[str],
    warmup: int,
    n: int,
    inter_sleep: float,
    timeout_s: float,
) -> dict:
    """warmup 후 N runs × Q queries 측정. abort 시에도 부분 결과 반환."""
    fn = _CALL_FN[backend]
    results: dict[str, Any] = {
        "provider": provider,
        "backend": backend,
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
                rec = fn(q, timeout_s=timeout_s)
                rec["run"] = run
                rec["tag"] = tag
                rec["query"] = q
                if tag == "warmup":
                    results["warmup_records"].append(rec)
                else:
                    results["measured_records"].append(rec)
                err = f" ERR={rec.get('error_class')}" if rec.get("error_class") else ""
                log_bk = rec.get("per_backend_dist_log") or {}
                log_tag = f" log_bk={log_bk}" if log_bk else ""
                print(
                    f"elapsed={rec['elapsed_sec']:.2f}s "
                    f"raw={rec.get('raw_items', 0)} "
                    f"dedup={rec.get('items_post_dedup', 0)}{log_tag}{err}",
                    flush=True,
                )
                stop = _check_stop(rec, backend)
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
    return {
        "n": len(vals),
        "mean": round(m, 2),
        "stdev": round(sd, 2),
        "cv_pct": round(cv, 1),
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
    }


def summarize(results: dict) -> dict:
    measured = [
        r for r in results.get("measured_records", []) if not r.get("error_class")
    ]
    all_elapsed = [r["elapsed_sec"] for r in measured]
    all_raw = [r["raw_items"] for r in measured]
    all_dedup = [r["items_post_dedup"] for r in measured]
    n_errors = sum(
        1 for r in results.get("measured_records", []) if r.get("error_class")
    )

    per_query: dict[str, dict] = {}
    for q in results.get("queries", []):
        runs = [
            r
            for r in measured
            if r.get("query") == q
        ]
        per_query[q] = {
            "n": len(runs),
            "elapsed": _stats([r["elapsed_sec"] for r in runs]),
            "raw_items": _stats([float(r["raw_items"]) for r in runs]),
        }

    backend_agg: dict[str, int] = {}
    backend_agg_log: dict[str, int] = {}
    for r in measured:
        for bk, c in (r.get("per_backend_dist") or {}).items():
            backend_agg[bk] = backend_agg.get(bk, 0) + int(c)
        for bk, c in (r.get("per_backend_dist_log") or {}).items():
            backend_agg_log[bk] = backend_agg_log.get(bk, 0) + int(c)

    return {
        "n_measured": len(measured),
        "n_errors": n_errors,
        "elapsed": _stats(all_elapsed),
        "raw_items": _stats([float(v) for v in all_raw]),
        "items_post_dedup": _stats([float(v) for v in all_dedup]),
        "per_backend_total": backend_agg,
        "per_backend_total_log": backend_agg_log,
        "per_query": per_query,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="§14-9 Phase 1 backend isolated smoke")
    ap.add_argument(
        "--provider",
        choices=["vertexai", "openai", "anthropic"],
        required=True,
    )
    ap.add_argument(
        "--backend",
        choices=["vertex_grounding", "legacy_only", "both"],
        required=True,
    )
    ap.add_argument("--topic", default="venfobel-vitamin")
    ap.add_argument("--n", type=int, default=3, help="measured runs per query (max 5)")
    ap.add_argument("--warmup", type=int, default=2, help="warmup runs per query (excluded)")
    ap.add_argument("--timeout", type=float, default=240.0, help="per-call timeout sec")
    ap.add_argument("--inter-sleep", type=float, default=60.0, help="inter-call sleep sec")
    ap.add_argument("--queries", default=None, help="newline-delim file (UTF-8); empty → DEFAULT_QUERIES")
    ap.add_argument("--out-dir", default=None, help="raw JSON output dir override")
    ap.add_argument("--tag", default="", help="output filename suffix tag")
    ap.add_argument("--sanity", action="store_true", help="--warmup 0 --n 1 --inter-sleep 0 강제 override")
    ap.add_argument("--log-capture", action="store_true", help="tools.web_rag.search backend invocation logger 캡처 활성 (legacy_only mode)")
    args = ap.parse_args()

    if args.n > 5:
        print(f"[ABORT] --n {args.n} > 5 (STOP condition)", flush=True)
        return 2
    if args.timeout > 300:
        print(f"[ABORT] --timeout {args.timeout} > 300s (STOP condition)", flush=True)
        return 2

    if args.sanity:
        args.warmup = 0
        args.n = 1
        args.inter_sleep = 0.0
        print("[sanity] warmup=0 n=1 inter_sleep=0 강제 override", flush=True)

    # env overlay 명시 로드
    _load_provider_env(args.provider)

    # TOPIC_SLUG 명시 — args.topic 우선 override 정합 (§14-9-W Step C § 6-f 박제).
    # .env:50 의 TOPIC_SLUG 가 _load_provider_env 의 override=False load 로
    # 선점된 경우 setdefault 는 무효 → 본 cycle 부터는 명시 override.
    os.environ["TOPIC_SLUG"] = args.topic

    # log capture 설치 (import 이전 — handler 가 logger 생성 후에도 attach 되도록)
    if args.log_capture:
        _install_log_capture()

    queries: list[str] = DEFAULT_QUERIES
    if args.queries:
        qp = Path(args.queries)
        if qp.exists():
            queries = [
                ln.strip() for ln in qp.read_text(encoding="utf-8").splitlines() if ln.strip()
            ]

    pre = _pre_dump(args.provider, args.backend)

    # backend mode × provider env sanity (warning only, no abort)
    if args.backend == "vertex_grounding":
        if not pre["has_GCP_PROJECT_ID"]:
            print("[WARN] GCP_PROJECT_ID 미설정 - vertex_web_search 실패 예상", flush=True)
    if args.backend == "legacy_only":
        if not (pre["has_TAVILY_API_KEY"] or pre["has_NAVER_CLIENT_ID"]):
            print("[WARN] TAVILY_API_KEY / NAVER_CLIENT_ID 모두 부재 - legacy chain 0 items", flush=True)

    print(
        f"\n[start] provider={args.provider} backend={args.backend} "
        f"topic={args.topic} warmup={args.warmup} n={args.n} "
        f"timeout={args.timeout}s inter_sleep={args.inter_sleep}s "
        f"queries={len(queries)}",
        flush=True,
    )

    results = measure(
        args.provider,
        args.backend,
        queries,
        args.warmup,
        args.n,
        args.inter_sleep,
        args.timeout,
    )
    results["pre_dump"] = pre

    summary = summarize(results)
    results["summary"] = summary

    # 출력 파일
    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "scripts" / "output" / "§14-9"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{args.tag}" if args.tag else ""
    out_path = out_dir / f"phase1_{args.provider}_{args.backend}{suffix}_{ts}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[summary] {json.dumps(summary, ensure_ascii=False)}", flush=True)
    print(f"[saved] {out_path}", flush=True)

    if results.get("abort"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
