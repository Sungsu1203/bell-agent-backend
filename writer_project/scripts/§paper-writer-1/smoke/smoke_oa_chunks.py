"""§paper-writer-1 Step C-1 smoke — OA chunks schema 확장 검증.

실행: .venv_vertex\\Scripts\\python.exe writer_project/scripts/§paper-writer-1/smoke/smoke_oa_chunks.py
사전 .env.openalex 의 OPENALEX_API_KEY + OPENALEX_MAILTO 주입 필요.
"""
import sys
from pathlib import Path

WRITER_PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WRITER_PROJECT_DIR))

from dotenv import load_dotenv
load_dotenv(WRITER_PROJECT_DIR / ".env.openalex", override=True)  # catch 64

from tools.web_rag.openalex import (
    openalex_search,
    _strip_doi_prefix,
    _reconstruct_abstract_from_inverted_index,
)

# helper unit
print("--- helper unit ---")
print("strip(None):", _strip_doi_prefix(None))
print("strip(https://doi.org/10.1/a):", _strip_doi_prefix("https://doi.org/10.1/a"))
print("strip(10.2/b):", _strip_doi_prefix("10.2/b"))
print("recon(None):", _reconstruct_abstract_from_inverted_index(None))
print("recon({}):", _reconstruct_abstract_from_inverted_index({}))
inv_sample = {"This": [0], "is": [1], "an": [2], "abstract": [3]}
print("recon(sample):", _reconstruct_abstract_from_inverted_index(inv_sample))
print()

r = openalex_search("consumer behavior in influencer marketing")
print("OA items:", r["items"])
print("OA error:", r["error"])
print("OA elapsed:", r["elapsed_sec"])
print("OA cost_usd:", r["oa_cost_usd"])

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
    if abs_v:
        print("abstract[:120]:", abs_v[:120])
else:
    print("OA chunks empty — check API key")
