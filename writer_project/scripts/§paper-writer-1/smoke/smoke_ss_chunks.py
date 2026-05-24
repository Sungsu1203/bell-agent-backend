"""§paper-writer-1 Step C-1 smoke — SS chunks schema 확장 검증.

실행: .venv_vertex\\Scripts\\python.exe writer_project/scripts/§paper-writer-1/smoke/smoke_ss_chunks.py
사전 .env.semanticscholar 의 SEMANTIC_SCHOLAR_API_KEY + SKIP=0 주입 필요 (catch 61).
"""
import sys
from pathlib import Path

WRITER_PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WRITER_PROJECT_DIR))

from dotenv import load_dotenv
load_dotenv(WRITER_PROJECT_DIR / ".env.semanticscholar", override=True)  # catch 64

from tools.web_rag.semantic_scholar import semantic_scholar_search

r = semantic_scholar_search("consumer behavior in influencer marketing")
print("SS items:", r["items"])
print("SS error:", r["error"])
print("SS elapsed:", r["elapsed_sec"])

if r["chunks"]:
    c0 = r["chunks"][0]
    print()
    print("--- chunks[0] schema keys ---")
    print(sorted(c0.keys()))
    required = {"uri", "title", "domain", "authors", "year", "venue", "doi", "abstract"}
    missing = required - set(c0.keys())
    print("required_keys_present:", not missing, "missing:", sorted(missing))
    print()
    print("--- chunks[0] sample values ---")
    print("title:", (c0.get("title") or "")[:80])
    print("authors[:3]:", (c0.get("authors") or [])[:3])
    print("year:", c0.get("year"))
    print("venue:", c0.get("venue"))
    print("doi:", c0.get("doi"))
    abs_v = c0.get("abstract")
    print("abstract_present:", bool(abs_v), "len:", len(abs_v) if abs_v else 0)
else:
    print("SS chunks empty — check SKIP env / API key")
