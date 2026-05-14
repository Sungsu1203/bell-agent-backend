"""§14-2 Phase B 풀파이프라인 측정 driver (Option A multi-turn wrapper)

§13-7 측정 표준 5개 준수:
1. max_retries=0 (env: VERTEX_MAX_RETRIES=0, .env.vertex 박제)
2. 2 warmup runs (본 측정 N=3 전, 결과 제외)
3. per-run-timeout 900s (multi-turn = research ~9 × 30s + writer 7 × 75s + overhead ~50s)
4. inter-run-sleep 60s
5. PYTHONIOENCODING=utf-8

호출 패턴: Option A multi-turn (1 run = 1 subprocess = outline 7 섹션 multi-turn 완성)
- 매 run subprocess.run([python, scripts/_phase_b_run_inner.py, --output ...])
- subprocess 내부: ns_web reset → outline 파싱 → max_turns 21 의 multi-turn loop
- 매 turn: msg="write: <남은 첫 섹션>" → graph.invoke → state 누적

비교 대상: d88a8b9 (patch 후) vs 1135ac1 (patch 전)
토픽: venfobel-vitamin (§12-12 정책: local_first + 0.33)

CLI:
    python scripts/measure_vertex_phase_b.py --mode dry
    python scripts/measure_vertex_phase_b.py --mode measure [--n 3] [--warmup 2]
    python scripts/measure_vertex_phase_b.py --mode summary

체크아웃 자동화 미실시. checkout 은 사용자가 수동 수행 후 --mode measure 호출.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# §13-8 pitfall #1: UTF-8 강제
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
INNER_SCRIPT = HERE / "_phase_b_run_inner.py"
CLEAR_SCRIPT = HERE / "_phase_b_clear_ns.py"

# .env.vertex 명시 로드 (main driver process 도 env diag 정합성 확보)
try:
    from dotenv import load_dotenv
    _env_vertex = PROJECT_ROOT / ".env.vertex"
    if _env_vertex.exists():
        load_dotenv(_env_vertex, override=True)
        print(f"[env] loaded {_env_vertex}", flush=True)
except ImportError:
    pass

# 토픽 박제
TOPIC_SLUG = "venfobel-vitamin"
SECTIONS_DIR = PROJECT_ROOT / "sections" / TOPIC_SLUG

# 출력 경로
OUT_BASE = HERE / "output"
PHASE_B_OUT = OUT_BASE / "phase_b"
DRY_OUT = OUT_BASE / "phase_b_dry_run"
SNAPSHOT_DIR = PHASE_B_OUT / "snapshot"
WARMUP_OUT = PHASE_B_OUT / "warmup"
INNER_OUT_DIR = PHASE_B_OUT / "_inner"  # subprocess 결과 JSON 임시 저장

DEFAULT_PER_RUN_TIMEOUT = 900.0
DEFAULT_INTER_RUN_SLEEP = 60.0
DEFAULT_N = 3
DEFAULT_WARMUP = 2
DEFAULT_MAX_TURNS = 21
DEFAULT_RECURSION_LIMIT = 200
DEFAULT_CLEAR_TIMEOUT = 60.0

FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:\s+(.*)$", re.MULTILINE)
LOCAL_FILE_RE = re.compile(r"file://|\.pdf\b|\.docx\b|\.md\b|\.txt\b|\.hwp\b|\.xlsx\b", re.IGNORECASE)
WEB_URL_RE = re.compile(r"https?://", re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# 환경 진단
# ─────────────────────────────────────────────────────────────────────────────
def _git_head() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT.parent), text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return out
    except Exception:
        return "<unknown>"


def _git_status_dirty_tracked() -> tuple[bool, list[str]]:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(PROJECT_ROOT.parent), text=True, stderr=subprocess.DEVNULL,
        )
        lines = out.splitlines()
        modified = [l for l in lines if l[:2].strip() and not l.startswith("??")]
        return (len(modified) > 0, modified[:20])
    except Exception as e:
        return (True, [f"<git error: {e}>"])


def _env_diag() -> dict:
    gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    return {
        "LLM_PROVIDER": os.getenv("LLM_PROVIDER", "<unset>"),
        "LLM_MODEL": os.getenv("LLM_MODEL", "<unset>"),
        "SKIP_VERTEX_SEARCH": os.getenv("SKIP_VERTEX_SEARCH", "<unset>"),
        "VERTEX_MAX_RETRIES": os.getenv("VERTEX_MAX_RETRIES", "<unset>"),
        "GCP_PROJECT_ID": os.getenv("GCP_PROJECT_ID", "<unset>"),
        "GCP_REGION": os.getenv("GCP_REGION", "<unset>"),
        "PYTHONIOENCODING": os.getenv("PYTHONIOENCODING", "<unset>"),
        "GAC_set": bool(gac),
        "GAC_exists": (Path(gac).exists() if gac else False),
        "SECTIONS_DIR_exists": SECTIONS_DIR.exists(),
        "INNER_SCRIPT_exists": INNER_SCRIPT.exists(),
        "CLEAR_SCRIPT_exists": CLEAR_SCRIPT.exists(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Run 격리: sections wipe/snapshot
# ─────────────────────────────────────────────────────────────────────────────
def _snapshot_sections(label: str, root: Path) -> Path:
    """sections/<TOPIC_SLUG> 전체를 root/<label>/ 로 이동. 원본 디렉토리는 빈 상태로 재생성."""
    root.mkdir(parents=True, exist_ok=True)
    dest = root / label
    if dest.exists():
        shutil.rmtree(dest)
    if SECTIONS_DIR.exists():
        shutil.move(str(SECTIONS_DIR), str(dest))
    SECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    return dest


def _wipe_sections() -> int:
    """sections/<TOPIC_SLUG> 의 .md/.json/.bak 만 삭제. 디렉토리 보존. 반환: 삭제 파일 수."""
    if not SECTIONS_DIR.exists():
        SECTIONS_DIR.mkdir(parents=True, exist_ok=True)
        return 0
    n = 0
    for p in SECTIONS_DIR.iterdir():
        if p.is_file() and (p.suffix in (".md", ".json") or ".bak" in p.name):
            try:
                p.unlink()
                n += 1
            except Exception:
                pass
    return n


# ─────────────────────────────────────────────────────────────────────────────
# subprocess 호출
# ─────────────────────────────────────────────────────────────────────────────
def _run_clear_subprocess(label: str, timeout_s: float = DEFAULT_CLEAR_TIMEOUT) -> dict:
    """ns_web reset 전용 subprocess 호출. cleared=False 시 main driver 가 abort."""
    INNER_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = INNER_OUT_DIR / f"{label}.clear.json"
    out_console = INNER_OUT_DIR / f"{label}.clear.console.log"
    cmd = [sys.executable, str(CLEAR_SCRIPT), "--output", str(out_json)]

    t0 = time.monotonic()
    err = None
    rc = None
    try:
        proc = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_s,
        )
        rc = proc.returncode
        out_console.write_text((proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or ""),
                                encoding="utf-8")
    except subprocess.TimeoutExpired:
        err = f"clear subprocess timeout {timeout_s}s"
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:300]}"

    elapsed = time.monotonic() - t0
    inner_result: dict | None = None
    if out_json.exists():
        try:
            inner_result = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception as e:
            err = err or f"InvalidClearJSON: {str(e)[:200]}"

    log = {
        "elapsed_sec": round(elapsed, 2),
        "returncode": rc,
        "error": err,
        "inner": inner_result,
        "cleared": (inner_result or {}).get("cleared", False) if inner_result else False,
        "before": (inner_result or {}).get("before_count"),
        "after": (inner_result or {}).get("after_count"),
        "fallback_used": (inner_result or {}).get("fallback_used", False),
    }
    return log


def _run_inner_subprocess(label: str, timeout_s: float, max_turns: int,
                          recursion_limit: int) -> dict:
    """scripts/_phase_b_run_inner.py 를 subprocess 로 실행. timeout 경과 시 kill.

    반환: rec dict (inner 의 결과 JSON + subprocess wrapper 정보)
    """
    INNER_OUT_DIR.mkdir(parents=True, exist_ok=True)
    inner_json = INNER_OUT_DIR / f"{label}.json"
    inner_console = INNER_OUT_DIR / f"{label}.console.log"
    # 같은 venv 의 python 재사용 (driver 호출 시 사용된 python.exe)
    python_exe = sys.executable

    cmd = [python_exe, str(INNER_SCRIPT),
           "--output", str(inner_json),
           "--max-turns", str(max_turns),
           "--recursion-limit", str(recursion_limit)]

    t0 = time.monotonic()
    err_class: str | None = None
    err_msg: str | None = None
    returncode: int | None = None
    inner_result: dict | None = None

    try:
        proc = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_s,
        )
        returncode = proc.returncode
        inner_console.write_text((proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or ""),
                                  encoding="utf-8")
    except subprocess.TimeoutExpired as e:
        err_class = "subprocess.TimeoutExpired"
        err_msg = f"subprocess timeout {timeout_s}s 초과"
        inner_console.write_text(
            (e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
            + "\n--- STDERR ---\n"
            + (e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")),
            encoding="utf-8",
        )
    except Exception as e:
        err_class = type(e).__name__
        err_msg = str(e)[:500]

    elapsed = time.monotonic() - t0

    # inner JSON 결과 읽기 (subprocess timeout 이어도 부분 결과 있을 수 있음)
    if inner_json.exists():
        try:
            inner_result = json.loads(inner_json.read_text(encoding="utf-8"))
        except Exception as e:
            err_class = err_class or "InvalidInnerJSON"
            err_msg = err_msg or f"{type(e).__name__}: {str(e)[:200]}"

    rec: dict = {
        "label": label,
        "elapsed_sec": round(elapsed, 3),
        "subprocess_returncode": returncode,
        "subprocess_error_class": err_class,
        "subprocess_error_msg": err_msg,
        "inner_console_path": str(inner_console.relative_to(PROJECT_ROOT)),
        "inner_json_path": str(inner_json.relative_to(PROJECT_ROOT)),
        "inner": inner_result,
    }
    # error_class 통일 (driver level)
    if err_class:
        rec["error_class"] = err_class
        rec["error_msg"] = err_msg
    elif inner_result and inner_result.get("abort_reason"):
        rec["error_class"] = "InnerAbort"
        rec["error_msg"] = inner_result["abort_reason"]
    else:
        rec["error_class"] = None
        rec["error_msg"] = None
    return rec


# ─────────────────────────────────────────────────────────────────────────────
# 후처리: sections/<TOPIC_SLUG>/ 의 .md + .refs.json 집계
# ─────────────────────────────────────────────────────────────────────────────
def collect_metrics(sections_dir: Path) -> dict:
    metrics: dict = {
        "section_count": 0,
        "footnote_count": {},
        "refs_docs_count": {},
        "refs_source_dist": {},
        "totals": {},
    }
    if not sections_dir.exists():
        return metrics

    md_files = sorted([p for p in sections_dir.iterdir()
                       if p.suffix == ".md" and ".bak" not in p.name])
    metrics["section_count"] = len(md_files)

    total_local_fn = 0
    total_web_fn = 0
    total_docs = 0
    total_dist: dict[str, int] = {}

    for md in md_files:
        slug = md.stem
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        local_n = 0
        web_n = 0
        for m in FOOTNOTE_DEF_RE.finditer(text):
            body = m.group(2) or ""
            if WEB_URL_RE.search(body):
                web_n += 1
            elif LOCAL_FILE_RE.search(body):
                local_n += 1
            else:
                local_n += 1
        metrics["footnote_count"][slug] = {"local": local_n, "web": web_n, "total": local_n + web_n}
        total_local_fn += local_n
        total_web_fn += web_n

        sidecar = md.with_suffix(".refs.json")
        if sidecar.exists():
            try:
                refs = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception as e:
                metrics["refs_docs_count"][slug] = None
                metrics["refs_source_dist"][slug] = {"error": str(e)[:200]}
                continue
            items = refs.values() if isinstance(refs, dict) else (refs if isinstance(refs, list) else [])
            items = list(items)
            metrics["refs_docs_count"][slug] = len(items)
            total_docs += len(items)
            dist: dict[str, int] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                src = str(item.get("source") or item.get("url") or "")
                if "vertexaisearch.cloud.google.com" in src:
                    key = "vertex_grounding"
                elif src.startswith("http://") or src.startswith("https://"):
                    key = "web"
                elif src.startswith("file://"):
                    key = "local"
                else:
                    key = "other"
                dist[key] = dist.get(key, 0) + 1
                total_dist[key] = total_dist.get(key, 0) + 1
            metrics["refs_source_dist"][slug] = dist

    metrics["totals"] = {
        "footnote_local": total_local_fn,
        "footnote_web": total_web_fn,
        "refs_docs": total_docs,
        "refs_source_dist": total_dist,
    }
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# Run orchestration
# ─────────────────────────────────────────────────────────────────────────────
def _stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0, "mean": 0.0, "stdev": 0.0, "cv_pct": 0.0, "min": 0.0, "max": 0.0}
    mean = statistics.mean(vals)
    stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
    cv = (stdev / mean * 100) if mean > 0 else 0.0
    return {"n": len(vals), "mean": round(mean, 2), "stdev": round(stdev, 2),
            "cv_pct": round(cv, 1), "min": round(min(vals), 2), "max": round(max(vals), 2)}


def _run_single(label: str, timeout_s: float, max_turns: int,
                recursion_limit: int, snapshot_root: Path, save_dir: Path,
                clear_timeout_s: float = DEFAULT_CLEAR_TIMEOUT) -> dict:
    wiped = _wipe_sections()
    print(f"  [pre] sections wiped={wiped} files", flush=True)

    # 1단계: ns_web clear (별도 subprocess)
    print(f"  [clear] subprocess start (timeout={clear_timeout_s}s)...", flush=True)
    clear_log = _run_clear_subprocess(label, timeout_s=clear_timeout_s)
    print(f"  [clear] cleared={clear_log['cleared']}  before={clear_log['before']}  "
          f"after={clear_log['after']}  fallback={clear_log['fallback_used']}  "
          f"elapsed={clear_log['elapsed_sec']}s  err={clear_log['error']}", flush=True)

    rec: dict
    if not clear_log["cleared"]:
        # abort: clear 실패 시 measurement subprocess 진입 안 함
        rec = {
            "label": label,
            "elapsed_sec": clear_log["elapsed_sec"],
            "error_class": "ClearFailed",
            "error_msg": f"cleared=False  before={clear_log['before']} after={clear_log['after']}",
            "chroma_clear_log": clear_log,
            "inner": None,
            "metrics": {},
        }
        snapshot = _snapshot_sections(label, snapshot_root)
        rec["snapshot_path"] = str(snapshot.relative_to(PROJECT_ROOT))
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / f"{label}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return rec

    # 2단계: measurement (multi-turn) subprocess
    rec = _run_inner_subprocess(label, timeout_s, max_turns, recursion_limit)
    rec["chroma_clear_log"] = clear_log
    rec["metrics"] = collect_metrics(SECTIONS_DIR)

    snapshot = _snapshot_sections(label, snapshot_root)
    rec["snapshot_path"] = str(snapshot.relative_to(PROJECT_ROOT))

    save_dir.mkdir(parents=True, exist_ok=True)
    out_path = save_dir / f"{label}.json"
    out_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return rec


def _print_run_summary(rec: dict) -> None:
    ms = rec.get("metrics", {})
    tot = ms.get("totals", {})
    inner = rec.get("inner") or {}
    clear_log = rec.get("chroma_clear_log") or {}
    turn_count = len(inner.get("turn_log") or [])
    completed = len(inner.get("completed_sections") or [])
    outline_n = len(inner.get("outline_titles") or [])
    state_dist = (inner.get("state_references_analysis") or {}).get("source_dist") or {}
    err = rec.get("error_class") or ""
    err_str = f"  ERR={err}" if err else ""
    print(f"  elapsed={rec['elapsed_sec']:.1f}s  turns={turn_count}  "
          f"completed={completed}/{outline_n}  sections_md={ms.get('section_count',0)}  "
          f"refs_sidecar={tot.get('refs_docs',0)}  "
          f"refs_state={(inner.get('state_references_analysis') or {}).get('count')}  "
          f"sidecar_fn(local={tot.get('footnote_local',0)},web={tot.get('footnote_web',0)})  "
          f"state_dist={state_dist}  "
          f"clear(before={clear_log.get('before')}→after={clear_log.get('after')},"
          f"fb={clear_log.get('fallback_used')}){err_str}",
          flush=True)


def run_measure(commit: str, n: int, warmup: int, timeout_s: float, inter_sleep: float,
                max_turns: int, recursion_limit: int, save_dir: Path) -> dict:
    short = (commit or "head")[:7]
    payload: dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "git_head": _git_head(),
        "commit_tag": short,
        "n": n, "warmup": warmup,
        "per_run_timeout_s": timeout_s,
        "inter_run_sleep_s": inter_sleep,
        "max_turns": max_turns,
        "recursion_limit": recursion_limit,
        "env": _env_diag(),
        "warmup_runs": [],
        "runs": [],
        "summary": {},
    }

    for w in range(warmup):
        label = f"warmup_{short}_{w+1}"
        print(f"\n[warmup {w+1}/{warmup}] {label}", flush=True)
        rec = _run_single(label, timeout_s, max_turns, recursion_limit, SNAPSHOT_DIR, WARMUP_OUT)
        payload["warmup_runs"].append({
            "label": label,
            "elapsed_sec": rec["elapsed_sec"],
            "error_class": rec.get("error_class"),
            "section_count": rec.get("metrics", {}).get("section_count", 0),
        })
        _print_run_summary(rec)
        if w < warmup - 1 and inter_sleep > 0:
            print(f"  [sleep {inter_sleep}s]", flush=True)
            time.sleep(inter_sleep)

    for r in range(n):
        if (r > 0 or warmup > 0) and inter_sleep > 0:
            print(f"  [sleep {inter_sleep}s]", flush=True)
            time.sleep(inter_sleep)
        label = f"{short}_run{r+1}"
        print(f"\n[run {r+1}/{n}] {label}", flush=True)
        rec = _run_single(label, timeout_s, max_turns, recursion_limit, SNAPSHOT_DIR, save_dir)
        payload["runs"].append(rec)
        _print_run_summary(rec)
        if r >= 1 and payload["runs"][-1].get("error_class") and payload["runs"][-2].get("error_class"):
            print("[STOP] 2회 연속 error — 측정 중단", flush=True)
            payload["stop_reason"] = "2회 연속 error"
            break

    ok = [r for r in payload["runs"] if not r.get("error_class")]
    payload["summary"] = {
        "n_ok": len(ok), "n_total": len(payload["runs"]),
        "elapsed": _stats([r["elapsed_sec"] for r in ok]),
        "section_count": _stats([float(r.get("metrics", {}).get("section_count", 0)) for r in ok]),
        "refs_docs_per_run": _stats(
            [float(r.get("metrics", {}).get("totals", {}).get("refs_docs", 0)) for r in ok]
        ),
        "footnote_total_per_run": _stats([
            float((r.get("metrics", {}).get("totals", {}).get("footnote_local", 0)
                   + r.get("metrics", {}).get("totals", {}).get("footnote_web", 0)))
            for r in ok
        ]),
        "turn_count_per_run": _stats([
            float(len((r.get("inner") or {}).get("turn_log") or [])) for r in ok
        ]),
    }
    return payload


def run_dry(timeout_s: float, max_turns: int, recursion_limit: int) -> dict:
    print("\n[mode] dry-run (N=1, warmup=0)", flush=True)
    return run_measure(commit=_git_head(), n=1, warmup=0,
                       timeout_s=timeout_s, inter_sleep=0.0,
                       max_turns=max_turns, recursion_limit=recursion_limit,
                       save_dir=DRY_OUT)


def run_summary() -> dict:
    payload: dict[str, Any] = {"runs": []}
    if PHASE_B_OUT.exists():
        for p in sorted(PHASE_B_OUT.glob("*_run*.json")):
            try:
                payload["runs"].append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
    ok = [r for r in payload["runs"] if not r.get("error_class")]
    payload["summary"] = {
        "n_ok": len(ok),
        "elapsed": _stats([r["elapsed_sec"] for r in ok]),
    }
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description="§14-2 Phase B 풀파이프라인 측정 driver (Option A)")
    p.add_argument("--mode", choices=["dry", "measure", "summary"], required=True)
    p.add_argument("--n", type=int, default=DEFAULT_N)
    p.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    p.add_argument("--timeout", type=float, default=DEFAULT_PER_RUN_TIMEOUT)
    p.add_argument("--inter-sleep", type=float, default=DEFAULT_INTER_RUN_SLEEP)
    p.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    p.add_argument("--recursion-limit", type=int, default=DEFAULT_RECURSION_LIMIT)
    args = p.parse_args()

    print("[env diag]", flush=True)
    for k, v in _env_diag().items():
        print(f"  {k} = {v}", flush=True)

    dirty, modified = _git_status_dirty_tracked()
    print(f"[git] HEAD={_git_head()[:7]}  tracked_files_dirty={dirty}", flush=True)
    if dirty:
        print("  modified (truncated):", flush=True)
        for line in modified:
            print(f"    {line}", flush=True)

    if not INNER_SCRIPT.exists():
        print(f"[FATAL] inner script not found: {INNER_SCRIPT}", flush=True)
        return 1
    if not CLEAR_SCRIPT.exists():
        print(f"[FATAL] clear script not found: {CLEAR_SCRIPT}", flush=True)
        return 1

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.mode == "dry":
        DRY_OUT.mkdir(parents=True, exist_ok=True)
        payload = run_dry(args.timeout, args.max_turns, args.recursion_limit)
        out = DRY_OUT / f"phase_b_dry_{ts}.json"
    elif args.mode == "measure":
        PHASE_B_OUT.mkdir(parents=True, exist_ok=True)
        payload = run_measure(commit=_git_head(), n=args.n, warmup=args.warmup,
                              timeout_s=args.timeout, inter_sleep=args.inter_sleep,
                              max_turns=args.max_turns, recursion_limit=args.recursion_limit,
                              save_dir=PHASE_B_OUT)
        out = PHASE_B_OUT / f"phase_b_measure_{ts}.json"
    else:
        payload = run_summary()
        PHASE_B_OUT.mkdir(parents=True, exist_ok=True)
        out = PHASE_B_OUT / f"phase_b_summary_{ts}.json"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[saved] {out}", flush=True)

    s = payload.get("summary", {})
    if s:
        print("\n=== summary ===", flush=True)
        for k, v in s.items():
            print(f"  {k}: {v}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
