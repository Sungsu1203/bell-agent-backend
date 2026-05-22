"""§academic-4 commit 2 smoke driver (SS skip / authenticated pool 검증)
실행 (cwd 무관):
  .venv_vertex\\Scripts\\python.exe writer_project/scripts/§academic-4/smoke/smoke_ss.py
.env.semanticscholar 의 SEMANTIC_SCHOLAR_MAILTO / SKIP / API_KEY 자동 로드.
PowerShell $env:* 잔존 영역 override (override=True).
"""
import sys
from pathlib import Path

WRITER_PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WRITER_PROJECT_DIR))

from dotenv import load_dotenv
# override=True: PowerShell $env:* 잔존 영역 .env.semanticscholar 값으로 덮어씀
load_dotenv(WRITER_PROJECT_DIR / '.env.semanticscholar', override=True)

from tools.web_rag.semantic_scholar import semantic_scholar_search

r = semantic_scholar_search('consumer behavior in influencer marketing', verbose=True)
print()
print('--- final ---')
print('SS items:', r['items'])
print('SS elapsed:', r['elapsed_sec'])
print('SS domains_unique[:5]:', r['domains_unique'][:5])
print('SS error:', r['error'])