"""§academic-4 commit 2 smoke driver (OA authenticated 검증)
실행 (cwd 무관):
  .venv_vertex\\Scripts\\python.exe writer_project/scripts/§academic-4/smoke/smoke_oa.py
사전 .env.openalex 의 OPENALEX_API_KEY + OPENALEX_MAILTO 주입 필요
"""
import sys
from pathlib import Path

WRITER_PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WRITER_PROJECT_DIR))

from dotenv import load_dotenv
load_dotenv(WRITER_PROJECT_DIR / '.env.openalex', override=True)  # 절대 경로

from tools.web_rag.openalex import openalex_search

r = openalex_search('consumer behavior in influencer marketing')
print('OA items:', r['items'])
print('OA domains_unique[:5]:', r['domains_unique'][:5])
print('OA cost_usd:', r['oa_cost_usd'])
print('OA elapsed:', r['elapsed_sec'])
print('OA error:', r['error'])