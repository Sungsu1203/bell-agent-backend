"""§14-2 Step 1a — Vertex grounding 응답 구조 덤프 스크립트.

목적: 한국어 쿼리 3개 + 영어 1개를 vertex_web_search 로 호출하고
반환된 chunks/supports/web_search_queries 구조를 JSON 으로 저장.
patcher 가 실제 데이터를 보고 agent/web_search.py 패치 설계를 확정하기 위함.

사용법 (.venv_vertex 활성화 상태에서):
    cd D:\\gpt_agent\\writer_project
    python scripts/dump_vertex_grounding.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

# writer_project/ 를 sys.path 에 올려 tools.* import 가능하게
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# .env.vertex 명시 로드 (config.py 거치지 않고 직접)
try:
    from dotenv import load_dotenv
    env_vertex = PROJECT_ROOT / ".env.vertex"
    if env_vertex.exists():
        load_dotenv(env_vertex, override=True)
        print(f"[env] loaded {env_vertex}")
    else:
        print(f"[env] WARN: {env_vertex} not found — using process env only")
except ImportError:
    print("[env] WARN: python-dotenv not installed — using process env only")

from tools.web_rag.vertex_search import vertex_web_search  # noqa: E402

QUERIES = [
    "벤포벤S 종근당 광고비 2024",
    "활성형 비타민 시장 규모 한국",
    "비타민 B군 임상시험 효능",
    "vitamin B benfotiamine clinical trial",
]


def _truncate(s: str, n: int = 200) -> str:
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


def _run_one(query: str) -> dict[str, Any]:
    print(f"\n[query] {query}")
    t0 = time.monotonic()
    err: str | None = None
    result: dict[str, Any] | None = None
    try:
        result = vertex_web_search(query)
    except Exception as e:
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        print(f"[error] {err}")
    dt = time.monotonic() - t0

    summary = (result or {}).get("summary", "") if result else ""
    chunks = (result or {}).get("chunks", []) or []
    supports = (result or {}).get("supports", []) or []
    wsq = (result or {}).get("web_search_queries", []) or []
    urls = (result or {}).get("urls", []) or []

    # 콘솔 요약
    print(f"  elapsed: {dt:.2f}s")
    print(f"  chunks: {len(chunks)} | supports: {len(supports)} | "
          f"web_search_queries: {len(wsq)} | urls(dedup): {len(urls)}")
    if wsq:
        print(f"  web_search_queries sample: {wsq[:3]}")
    if supports:
        sample_text = supports[0].get("text", "")
        print(f"  segment[0] text: {_truncate(sample_text, 160)}")
    if chunks:
        c0 = chunks[0]
        print(f"  chunk[0]: title={_truncate(c0.get('title', ''), 80)} | "
              f"domain={c0.get('domain', '')}")
    if summary:
        print(f"  summary[:160]: {_truncate(summary, 160)}")

    # JSON 직렬화 (raw_response 는 repr 로)
    raw_repr = ""
    if result is not None:
        try:
            raw_repr = repr(result.get("raw_response"))[:500]
        except Exception:
            raw_repr = "<unreprable>"

    return {
        "query": query,
        "elapsed_sec": round(dt, 3),
        "error": err,
        "summary": summary,
        "urls": urls,
        "chunks": chunks,
        "supports": supports,
        "web_search_queries": wsq,
        "raw_response_repr": raw_repr,
        "counts": {
            "chunks": len(chunks),
            "supports": len(supports),
            "web_search_queries": len(wsq),
            "urls_dedup": len(urls),
            "summary_chars": len(summary),
        },
    }


def main() -> int:
    # 환경 진단
    print("[env diag]")
    print(f"  GCP_PROJECT_ID = {os.getenv('GCP_PROJECT_ID', '<unset>')}")
    print(f"  GCP_REGION     = {os.getenv('GCP_REGION', '<unset>')}")
    gac = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    print(f"  GOOGLE_APPLICATION_CREDENTIALS = "
          f"{gac if gac else '<unset>'}"
          f"{'  (exists)' if gac and Path(gac).exists() else '  (NOT FOUND)' if gac else ''}")
    print(f"  LLM_MODEL      = {os.getenv('LLM_MODEL', '<unset, default=gemini-2.5-flash>')}")

    out_dir = HERE / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"vertex_grounding_dump_{ts}.json"

    results = []
    for q in QUERIES:
        results.append(_run_one(q))

    payload = {
        "timestamp": ts,
        "model": os.getenv("LLM_MODEL", "gemini-2.5-flash"),
        "project": os.getenv("GCP_PROJECT_ID", ""),
        "region": os.getenv("GCP_REGION", ""),
        "queries": results,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n[saved] {out_path}")
    print("\n=== summary table ===")
    print(f"{'query':<45} {'chunks':>7} {'supports':>9} {'queries':>8} {'sec':>6}")
    for r in results:
        q_short = r["query"][:43] + ("…" if len(r["query"]) > 43 else "")
        c = r["counts"]
        print(f"{q_short:<45} {c['chunks']:>7} {c['supports']:>9} "
              f"{c['web_search_queries']:>8} {r['elapsed_sec']:>6.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
