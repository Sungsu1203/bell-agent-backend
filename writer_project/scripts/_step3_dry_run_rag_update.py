"""§14-3 Phase 2 Step 3: Tier 2 토픽 단발 dry-run.

Trigger B (`최신 자료로 RAG 업데이트해줘` 등 `_rag_re` 매칭 명령) 1회 graph.invoke
실행 후 state.references 박제.

Phase B 의 multi-turn (write: <섹션>) 인프라와 분리 — outline 없는 새 토픽에서도
web_search 노드 도달 가능 여부 + vertex_grounding 활성 가능 여부 검증.

ns_web 은 시작 시점에 별도 subprocess (_phase_b_clear_ns.py --ns) 로 wipe.

CLI:
    python scripts/_step3_dry_run_rag_update.py \\
      --topic-slug <slug> --topic-title <title> \\
      --trigger "<자연어 명령>" --output <path.json>
      [--recursion-limit 100] [--clear-timeout 60]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CLEAR_SCRIPT = HERE / "_phase_b_clear_ns.py"


def env_snapshot(label: str) -> None:
    """env stage 박제 — graph 내부 modification 추적용 (§14-3 G4-2)."""
    keys = (
        "LLM_PROVIDER", "LLM_MODEL", "TOPIC_SLUG",
        "SKIP_VERTEX_SEARCH", "MIRROR_STATE_TO_ENV",
        "CHROMA_NAMESPACE", "CHROMA_NAMESPACE_WEB",
        "CHROMA_NAMESPACE_LOCAL", "CHROMA_DIR",
    )
    print(f"[env_trace] {label}", flush=True)
    for k in keys:
        print(f"  {k} = {os.environ.get(k, '')}", flush=True)


env_snapshot("STAGE_1_script_start")

try:
    from dotenv import load_dotenv
    env_vertex = PROJECT_ROOT / ".env.vertex"
    if env_vertex.exists():
        load_dotenv(env_vertex, override=True)
        print(f"[env] loaded {env_vertex}", flush=True)
    else:
        print(f"[env] WARN: {env_vertex} not found", flush=True)
except ImportError:
    print("[env] WARN: python-dotenv not installed", flush=True)

env_snapshot("STAGE_2_dotenv_vertex_loaded")


def _run_clear_subprocess(ns: str, out_dir: Path, timeout_s: float) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"clear_{ns}.json"
    cmd = [sys.executable, str(CLEAR_SCRIPT), "--ns", ns, "--output", str(out_json)]
    print(f"[clear] subprocess: {' '.join(cmd[-3:])}", flush=True)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, timeout=timeout_s, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        elapsed = round(time.monotonic() - t0, 2)
        log = {
            "elapsed_sec": elapsed,
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-1500:] if proc.stdout else "",
            "stderr_tail": proc.stderr[-1500:] if proc.stderr else "",
        }
        if out_json.exists():
            try:
                log["result"] = json.loads(out_json.read_text(encoding="utf-8"))
            except Exception as e:
                log["result_parse_err"] = f"{type(e).__name__}: {e}"
        return log
    except subprocess.TimeoutExpired:
        return {"elapsed_sec": round(time.monotonic() - t0, 2), "error": "TimeoutExpired"}


def _serialize_doc(doc: Any) -> dict:
    if isinstance(doc, dict):
        meta = doc.get("metadata") or {}
        out = {"_form": "dict"}
        for k in ("source", "url", "title", "content_type", "backend", "alt_urls",
                  "chunk_domain", "search_provider", "score"):
            v = doc.get(k) if k in doc else meta.get(k)
            if v is not None:
                out[k] = v
        out["metadata_keys"] = list(meta.keys()) if isinstance(meta, dict) else []
        pc = doc.get("page_content") or ""
        out["page_content_len"] = len(pc) if isinstance(pc, str) else 0
        out["page_content_head"] = (pc[:240] if isinstance(pc, str) else "")
        return out
    meta = getattr(doc, "metadata", None) or {}
    out = {"_form": "Document"}
    for k in ("source", "url", "title", "content_type", "backend", "alt_urls",
              "chunk_domain", "search_provider", "score"):
        if isinstance(meta, dict) and k in meta:
            out[k] = meta[k]
    if isinstance(meta, dict):
        out["metadata_keys"] = list(meta.keys())
    pc = getattr(doc, "page_content", "") or ""
    out["page_content_len"] = len(pc) if isinstance(pc, str) else 0
    out["page_content_head"] = (pc[:240] if isinstance(pc, str) else "")
    return out


def _classify_source(src: str) -> str:
    s = (src or "").strip()
    if "vertexaisearch.cloud.google.com" in s:
        return "vertex_grounding"
    if s.startswith("http://") or s.startswith("https://"):
        return "web"
    if s.startswith("file://"):
        return "local"
    if not s:
        return "unknown"
    return "other"


def _analyze_refs(docs: list) -> dict:
    serialized: list[dict] = []
    dist: dict[str, int] = {}
    for d in docs or []:
        try:
            row = _serialize_doc(d)
        except Exception as e:
            row = {"_form": "error", "error": f"{type(e).__name__}: {str(e)[:120]}"}
        src = str(row.get("source") or row.get("url") or "")
        key = _classify_source(src)
        dist[key] = dist.get(key, 0) + 1
        row["source_class"] = key
        serialized.append(row)
    return {"count": len(serialized), "source_dist": dist, "docs": serialized}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic-slug", required=True)
    parser.add_argument("--topic-title", required=True)
    parser.add_argument("--trigger", required=True,
                        help="_rag_re 매칭 자연어 명령 (예: '최신 자료로 RAG 업데이트해줘')")
    parser.add_argument("--output", required=True)
    parser.add_argument("--recursion-limit", type=int, default=100)
    parser.add_argument("--clear-timeout", type=float, default=60.0)
    args = parser.parse_args()

    t_start = time.monotonic()
    ns_web = f"{args.topic_slug}-web"
    out_path = Path(args.output)

    result: dict[str, Any] = {
        "topic_slug": args.topic_slug,
        "topic_title": args.topic_title,
        "trigger": args.trigger,
        "ns_web": ns_web,
        "recursion_limit": args.recursion_limit,
        "clear_log": {},
        "elapsed_sec": 0.0,
        "abort_reason": None,
        "state_references_analysis": {},
        "final_state_summary": {},
        "messages_count": None,
        "task_history_count": None,
    }

    print("[env diag]", flush=True)
    for k in ("LLM_PROVIDER", "LLM_MODEL", "SKIP_VERTEX_SEARCH", "VERTEX_MAX_RETRIES",
              "GCP_PROJECT_ID", "GCP_REGION"):
        print(f"  {k} = {os.getenv(k, '<unset>')}", flush=True)

    # 1. ns_web clear (별도 subprocess, LangChain 미 import 상태)
    clear_log = _run_clear_subprocess(ns_web, out_path.parent / "_clear", args.clear_timeout)
    result["clear_log"] = clear_log
    cleared = bool((clear_log.get("result") or {}).get("cleared"))
    print(f"[clear] cleared={cleared}  elapsed={clear_log.get('elapsed_sec')}s", flush=True)
    if not cleared:
        result["abort_reason"] = "ns_web_clear_failed"
        result["elapsed_sec"] = round(time.monotonic() - t_start, 2)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8")
        return 2

    # 2. graph build + invoke
    print("\n[graph] importing graph module...", flush=True)
    from graph import build_graph
    print("[graph] import done. building...", flush=True)
    from langchain_core.messages import HumanMessage
    graph = build_graph()
    print("[graph] build_graph done.", flush=True)
    env_snapshot("STAGE_3_graph_imported")

    state: dict = {
        "topic_slug": args.topic_slug,
        "topic_title": args.topic_title,
        "messages": [HumanMessage(content=args.trigger)],
        "last_user": args.trigger,
        "task_history": [],
        "flags": {"pending_write_title": False, "completed_sections": []},
        "outline_fname": "outline_report.md",
        "references": {"queries": [], "docs": []},
    }

    print(f"\n[invoke] trigger={args.trigger!r}", flush=True)
    env_snapshot("STAGE_4_before_invoke")
    t_inv = time.monotonic()
    try:
        result_state = graph.invoke(state, config={"recursion_limit": args.recursion_limit})
        invoke_elapsed = round(time.monotonic() - t_inv, 2)
        if isinstance(result_state, dict):
            state.update(result_state)
        print(f"[invoke] elapsed={invoke_elapsed}s", flush=True)
        env_snapshot("STAGE_5_after_invoke")
    except Exception as e:
        invoke_elapsed = round(time.monotonic() - t_inv, 2)
        result["abort_reason"] = f"invoke_exception: {type(e).__name__}: {str(e)[:300]}"
        result["invoke_elapsed_sec"] = invoke_elapsed
        result["elapsed_sec"] = round(time.monotonic() - t_start, 2)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                            encoding="utf-8")
        print(f"[ERROR] {result['abort_reason']}", flush=True)
        return 3

    result["invoke_elapsed_sec"] = invoke_elapsed

    # 3. 분석
    final_refs = state.get("references") or {}
    final_docs = final_refs.get("docs") or []
    try:
        result["state_references_analysis"] = _analyze_refs(final_docs)
    except Exception as e:
        result["state_references_analysis"] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}

    result["messages_count"] = len(state.get("messages") or [])
    result["task_history_count"] = len(state.get("task_history") or [])
    result["final_state_summary"] = {
        "refs_docs_count": len(final_docs),
        "source_dist": (result["state_references_analysis"] or {}).get("source_dist", {}),
        "tasks_count": result["task_history_count"],
        "messages_count": result["messages_count"],
    }
    result["elapsed_sec"] = round(time.monotonic() - t_start, 2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")

    sd = result["final_state_summary"].get("source_dist", {})
    print(f"\n[summary] invoke={invoke_elapsed}s  total={result['elapsed_sec']}s  "
          f"refs_docs={len(final_docs)}  source_dist={sd}", flush=True)
    print(f"[saved] {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
