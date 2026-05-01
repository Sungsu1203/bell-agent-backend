"""리팩토링 전후 _domain_bonus 동작이 동일한지 확인."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.vector_search import _domain_bonus

cases = [
    # (url, expected)
    ("file:///c:/refs/foo.pdf", 1.5),
    ("file://localhost/refs/x.pdf", 1.5),
    ("https://www.dailypharm.com/news/123", 1.0),
    ("https://yakup.com/article", 1.0),
    ("https://pharmnews.com/x", 1.0),
    ("https://kosis.kr/stat", 0.8),
    ("https://www.mfds.go.kr/notice", 0.8),
    ("https://dart.fss.or.kr/disc", 0.8),
    ("https://www.krx.co.kr/page", -0.5),
    ("https://financialreports.eu/x", -0.5),
    ("https://unknown-site.com/x", 0.0),
    ("https://news.naver.com/foo", 0.0),
    ("", 0.0),
]

failed = 0
for url, expected in cases:
    got = _domain_bonus(url)
    status = "ok  " if got == expected else "FAIL"
    if status.strip() == "FAIL":
        failed += 1
    print(f"  [{status}] {url!r:55s} expected={expected:5} got={got}")

print(f"\n{'PASS' if failed == 0 else f'FAILED ({failed} cases)'}")
sys.exit(0 if failed == 0 else 1)