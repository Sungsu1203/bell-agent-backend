"""§14-2 Phase B 풀파이프라인 1 run subprocess entry (v2).

driver 가 매 run 별로 이 script 를 subprocess.run 으로 호출.
완전 격리: graph cache / LLM cache / Chroma handle 모두 새 process 에서 생성.

v2 변경 (Phase B brief):
- ns_web reset 제거 (별도 _phase_b_clear_ns.py subprocess 가 담당)
- chroma_initial_count 박제 (cross-check)
- state.references.docs 박제 (마지막 turn 의 final state)
- state_references_source_dist 분석 (vertex_grounding/web/local/other)
- 매 turn 의 refs_docs_count_in_state 박제 (변동 추적)

CLI:
    python scripts/_phase_b_run_inner.py --output <path.json> [--max-turns 21] [--recursion-limit 200]
"""
from __future__ import annotations

import argparse
import json
import os
import re
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

TOPIC_SLUG = "venfobel-vitamin"
TOPIC_TITLE = "벤포벨S 2026 광고기획"
NS_WEB = f"{TOPIC_SLUG}-web"
OUTLINE_PATH = PROJECT_ROOT / "outlines" / TOPIC_SLUG / "outline_report.md"


def parse_outline(path: Path) -> list[str]:
    """outline_report.md 파싱 → 섹션 title list."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    titles: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(\d+)\.\s+(.+?)\s*$", line.strip())
        if m:
            titles.append(m.group(2).strip())
    return titles


def cross_check_chroma_count() -> dict:
    """시작 시 ns_web count 확인 (clear subprocess 결과 cross-check 용).

    clear 가 성공했다면 0 이어야 함. measurement 진행 중에는 web_search_agent 가
    chunks 추가하므로 점점 증가.
    """
    diag: dict = {"ns": NS_WEB, "count": None, "persist_dir": None, "error": None}
    try:
        from tools.web_rag.ingest_vector import _default_chroma_dir
        from langchain_chroma import Chroma
        from core.llm import get_embedding_model
        pd = _default_chroma_dir(NS_WEB)
        diag["persist_dir"] = pd
        emb = get_embedding_model()
        vs = Chroma(persist_directory=pd, embedding_function=emb, collection_name=NS_WEB)
        diag["count"] = vs._collection.count()
    except Exception as e:
        diag["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return diag


def _doc_to_dict(doc: Any) -> dict:
    """LangChain Document 또는 dict 형태 reference 를 직렬화.

    page_content 는 길어서 제외, metadata + 핵심 필드만.
    """
    if isinstance(doc, dict):
        meta = doc.get("metadata") or {}
        out = {"_form": "dict"}
        for k in ("source", "url", "title", "content_type", "backend", "alt_urls",
                  "chunk_domain", "search_provider", "score"):
            v = doc.get(k) if k in doc else meta.get(k)
            if v is not None:
                out[k] = v
        out["metadata_keys"] = list(meta.keys()) if isinstance(meta, dict) else []
        out["page_content_len"] = len(doc.get("page_content") or "")
        return out
    # LangChain Document — duck-type
    out = {"_form": "Document"}
    meta = getattr(doc, "metadata", None) or {}
    for k in ("source", "url", "title", "content_type", "backend", "alt_urls",
              "chunk_domain", "search_provider", "score"):
        if isinstance(meta, dict) and k in meta:
            out[k] = meta[k]
    if isinstance(meta, dict):
        out["metadata_keys"] = list(meta.keys())
    pc = getattr(doc, "page_content", "") or ""
    out["page_content_len"] = len(pc) if isinstance(pc, str) else 0
    return out


def classify_source(src: str) -> str:
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


def analyze_references_docs(docs: list) -> dict:
    """state.references.docs 의 source 분포 + 직렬화 박제."""
    serialized: list[dict] = []
    dist: dict[str, int] = {}
    for d in docs or []:
        try:
            row = _doc_to_dict(d)
        except Exception as e:
            row = {"_form": "error", "error": f"{type(e).__name__}: {str(e)[:120]}"}
        src = str(row.get("source") or row.get("url") or "")
        key = classify_source(src)
        dist[key] = dist.get(key, 0) + 1
        row["source_class"] = key
        serialized.append(row)
    return {
        "count": len(serialized),
        "source_dist": dist,
        "docs": serialized,
    }


def build_initial_state() -> dict:
    return {
        "topic_slug": TOPIC_SLUG,
        "topic_title": TOPIC_TITLE,
        "messages": [],
        "task_history": [],
        "flags": {
            "pending_write_title": False,
            "completed_sections": [],
        },
        "outline_fname": "outline_report.md",
        "references": {"queries": [], "docs": []},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-turns", type=int, default=21)
    parser.add_argument("--recursion-limit", type=int, default=200)
    args = parser.parse_args()

    from langchain_core.messages import HumanMessage

    t_start = time.monotonic()
    result: dict[str, Any] = {
        "label": Path(args.output).stem,
        "max_turns": args.max_turns,
        "recursion_limit": args.recursion_limit,
        "chroma_initial_count": None,
        "chroma_initial_diag": {},
        "outline_titles": [],
        "turn_log": [],
        "abort_reason": None,
        "completed_sections": [],
        "elapsed_sec": 0.0,
        "final_state_summary": {},
        "state_references_analysis": {},
    }

    print("[env diag]", flush=True)
    for k in ("LLM_PROVIDER", "LLM_MODEL", "SKIP_VERTEX_SEARCH", "VERTEX_MAX_RETRIES",
              "GCP_PROJECT_ID", "GCP_REGION"):
        print(f"  {k} = {os.getenv(k, '<unset>')}", flush=True)

    # cross-check: clear subprocess 결과 검증
    print("\n[chroma] cross-check ns_web count...", flush=True)
    diag = cross_check_chroma_count()
    result["chroma_initial_diag"] = diag
    result["chroma_initial_count"] = diag.get("count")
    print(f"[chroma] initial count={diag.get('count')}  err={diag.get('error')}", flush=True)

    titles = parse_outline(OUTLINE_PATH)
    result["outline_titles"] = titles
    print(f"\n[outline] {len(titles)} sections", flush=True)
    if not titles:
        result["abort_reason"] = "no_outline_titles"
        result["elapsed_sec"] = round(time.monotonic() - t_start, 2)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                                     encoding="utf-8")
        return 1

    print("\n[graph] build_graph...", flush=True)
    from graph import build_graph
    graph = build_graph()

    state = build_initial_state()
    print(f"\n[loop] max_turns={args.max_turns}, recursion_limit={args.recursion_limit}\n", flush=True)

    for turn_idx in range(1, args.max_turns + 1):
        flags = state.get("flags") or {}
        done_before = set(flags.get("completed_sections") or [])
        remaining = [t for t in titles if t not in done_before]
        if not remaining:
            print(f"[turn {turn_idx}] 모든 섹션 완료 — 정상 종료", flush=True)
            break

        next_title = remaining[0]
        user_msg = f"write: {next_title}"
        print(f"[turn {turn_idx}/{args.max_turns}] msg='{user_msg[:80]}'  remaining={len(remaining)}",
              flush=True)

        messages = list(state.get("messages") or [])
        messages.append(HumanMessage(content=user_msg))
        state["messages"] = messages
        state["last_user"] = user_msg

        t_inv = time.monotonic()
        try:
            result_state = graph.invoke(state, config={"recursion_limit": args.recursion_limit})
            elapsed = time.monotonic() - t_inv
            if isinstance(result_state, dict):
                state.update(result_state)
            flags_after = state.get("flags") or {}
            done_after = set(flags_after.get("completed_sections") or [])
            new_done = sorted(done_after - done_before)
            refs_now = state.get("references") or {}
            refs_docs_count = len(refs_now.get("docs") or [])
            print(f"  elapsed={elapsed:.1f}s  completed={len(done_after)}/{len(titles)}  "
                  f"refs_docs={refs_docs_count}  new={new_done}", flush=True)
            result["turn_log"].append({
                "turn": turn_idx,
                "msg": user_msg,
                "elapsed_sec": round(elapsed, 2),
                "completed_total": len(done_after),
                "new_completed": new_done,
                "tasks_count": len(state.get("task_history") or []),
                "messages_count": len(state.get("messages") or []),
                "refs_docs_count_in_state": refs_docs_count,
                "research_round": state.get("research_round"),
            })
        except Exception as e:
            result["abort_reason"] = f"exception_turn_{turn_idx}: {type(e).__name__}: {str(e)[:300]}"
            print(f"  ERROR: {type(e).__name__}: {str(e)[:300]}", flush=True)
            break
    else:
        result["abort_reason"] = f"max_turns ({args.max_turns}) reached"
        print(f"\n[STOP] max_turns {args.max_turns} 도달", flush=True)

    final_flags = state.get("flags") or {}
    result["completed_sections"] = list(final_flags.get("completed_sections") or [])
    result["elapsed_sec"] = round(time.monotonic() - t_start, 2)

    # 최종 state.references 분석
    final_refs = state.get("references") or {}
    final_docs = final_refs.get("docs") or []
    print(f"\n[refs] final state.references.docs count={len(final_docs)}", flush=True)
    try:
        result["state_references_analysis"] = analyze_references_docs(final_docs)
    except Exception as e:
        result["state_references_analysis"] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}

    result["final_state_summary"] = {
        "messages_count": len(state.get("messages") or []),
        "tasks_count": len(state.get("task_history") or []),
        "refs_docs_count": len(final_docs),
        "research_round": state.get("research_round"),
        "refs_source_dist": (result["state_references_analysis"] or {}).get("source_dist", {}),
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                                 encoding="utf-8")
    print(f"\n[saved] {args.output}", flush=True)
    print(f"[summary] elapsed={result['elapsed_sec']}s  "
          f"completed={len(result['completed_sections'])}/{len(titles)}  "
          f"refs_state={result['final_state_summary'].get('refs_docs_count')}  "
          f"dist={result['final_state_summary'].get('refs_source_dist')}  "
          f"abort={result['abort_reason']}", flush=True)
    return 0 if result["abort_reason"] is None else 2


if __name__ == "__main__":
    sys.exit(main())
