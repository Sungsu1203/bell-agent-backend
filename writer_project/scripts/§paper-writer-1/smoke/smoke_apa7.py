"""§paper-writer-1 Step C-1 smoke — utils.citations.format_apa7 단위 검증.

실행 (cwd 무관):
  .venv_vertex\\Scripts\\python.exe writer_project/scripts/§paper-writer-1/smoke/smoke_apa7.py
"""
import sys
from pathlib import Path

WRITER_PROJECT_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WRITER_PROJECT_DIR))

from utils.citations import format_apa7, _format_authors_apa7, _format_doi_url

r = format_apa7(
    authors=["Smith, J. A.", "Doe, B. C."],
    year=2024,
    title="Consumer behavior in influencer marketing",
    venue="Journal of Marketing Research",
    doi="10.1177/00222437241234567",
)
print("APA7 output:")
print(r)
print()

checks = {
    "authors_joined": "Smith, J. A., & Doe, B. C." in r,
    "year_paren": "(2024)" in r,
    "venue_italic": "*Journal of Marketing Research*" in r,
    "doi_url": "https://doi.org/10.1177/" in r,
}
print("checks:", checks)
print("all_pass:", all(checks.values()))

print()
print("--- edge cases ---")
print("nd:", format_apa7(authors=[], year=None, title="Anon", venue=None, doi=None))
print("21auth:", _format_authors_apa7([f"A{i}, X. {i}" for i in range(25)])[:60], "...")
print("doi_strip:", _format_doi_url("https://doi.org/10.1/abc"))
print("doi_bare:", _format_doi_url("10.2/xyz"))
