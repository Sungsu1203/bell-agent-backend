"""XLSX 키워드 점수 함수 리팩토링 동등성 확인."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.topic_config import get_xlsx_keyword_groups

# 새 로직 (ingest_vector._xlsx_sheet_summaries 안의 _score_col과 동일)
keyword_groups = get_xlsx_keyword_groups()

def score_new(name: str) -> int:
    n = name.lower()
    s = 0
    for grp in keyword_groups.values():
        try:
            score = int(grp.get("score", 0))
        except (TypeError, ValueError):
            continue
        keywords = grp.get("keywords") or []
        if any(kw.lower() in n for kw in keywords):
            s += score
    return s


# 기존 로직 (리팩토링 전 코드 그대로)
cost_like = ("광고비", "비용", "집행", "지출", "총액", "합계", "total", "sum", "spend", "cost")
channel_like = ("디지털", "digital", "tv", "지상파", "케이블", "소셜", "search", "display", "youtube")

def score_old(name: str) -> int:
    n = name.lower()
    s = 0
    if any(k in n for k in (k.lower() for k in cost_like)): s += 3
    if any(k in n for k in (k.lower() for k in channel_like)): s += 2
    if "합계" in name or "총" in name: s += 2
    if "금액" in name or "원" in name: s += 1
    return s


# 테스트 케이스
cases = [
    "광고비",          # cost(3) + summary(0:합계는 부분 매치 X)
    "총광고비",        # cost(3) + summary(2:총)
    "디지털 광고비",    # channel(2) + cost(3)
    "TV비용",          # channel(2) + cost(3)
    "총 디지털",       # channel(2) + summary(2)
    "합계",            # cost(3:합계) + summary(2:합계)
    "총액",            # cost(3:총액) + summary(2:총)
    "금액",            # currency(1)
    "원",              # currency(1)
    "Channel TV",      # channel(2:tv)
    "Total Cost",      # cost(3:total or cost)
    "Search",          # channel(2:search)
    "기타항목",        # 0
    "",                # 0
    "Display Spend",   # channel(2:display) + cost(3:spend)
]

failed = 0
print(f"{'name':25s} {'old':>5s} {'new':>5s} {'status':>8s}")
print("-" * 50)
for name in cases:
    o = score_old(name)
    n = score_new(name)
    status = "ok" if o == n else "FAIL"
    if status == "FAIL":
        failed += 1
    print(f"{name!r:25s} {o:>5d} {n:>5d} {status:>8s}")

print(f"\n{'PASS' if failed == 0 else f'FAILED ({failed} cases)'}")

# ─────────────────────────────────────────────────────────────────────────────
# Channel 매칭 동등성 (brk_parts 로직)
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== channel keyword matching ===")

# 새 로직
channel_keywords_new = (keyword_groups.get("channel") or {}).get("keywords") or []
channel_keywords_new_lower = [kw.lower() for kw in channel_keywords_new]

def is_channel_new(col_name: str) -> bool:
    lc = str(col_name).lower()
    return any(kw in lc for kw in channel_keywords_new_lower)


# 기존 로직 (위에 정의된 channel_like 재사용)
def is_channel_old(col_name: str) -> bool:
    lc = str(col_name).lower()
    return any(k in lc for k in (k.lower() for k in channel_like))


col_cases = [
    "디지털",
    "Digital",
    "TV",
    "tv 광고비",
    "케이블TV",
    "지상파",
    "소셜",
    "Search",
    "YouTube",
    "Display ads",
    "기타",
    "Total",
    "광고비",
    "",
]

ch_failed = 0
print(f"{'col_name':25s} {'old':>5s} {'new':>5s} {'status':>8s}")
print("-" * 50)
for name in col_cases:
    o = is_channel_old(name)
    n = is_channel_new(name)
    status = "ok" if o == n else "FAIL"
    if status == "FAIL":
        ch_failed += 1
    print(f"{name!r:25s} {str(o):>5s} {str(n):>5s} {status:>8s}")

print(f"\n{'channel PASS' if ch_failed == 0 else f'channel FAILED ({ch_failed} cases)'}")

# 최종 종료 코드
total_failed = failed + ch_failed
sys.exit(0 if total_failed == 0 else 1)