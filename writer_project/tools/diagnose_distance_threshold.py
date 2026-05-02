"""distance threshold 분포 진단.
여러 토픽 관련 쿼리에 대해 top-K 검색 결과의 distance 분포를 측정한다.
text-multilingual-embedding-002 마이그레이션 후, distance 분포에 맞춘
threshold 후보(0.45~0.80)에서 cut %를 평가한다.
현재 운영 threshold는 .env의 RAG_DISTANCE_THRESHOLD 값을 따른다.
"""
import os
import sys
from pathlib import Path
import statistics

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")  # 운영 코드와 동일한 .env 로드

from tools.web_rag.ingest_vector import _get_vs, _default_chroma_dir


# (namespace, queries) — 각 토픽에 맞는 실제 검색어
TARGETS = [
    (
        "height-growth-supplement-web",
        [
            "키성장 건강기능식품 시장 규모",
            "어린이 성장 영양제 효능",
            "프로바이오틱스 키성장",
            "한국 건강기능식품 시장 트렌드 2025",
            "성장기 영양 권장량",
        ],
    ),
    (
        "pet-food-premium-web",
        [
            "프리미엄 펫푸드 시장 규모",
            "반려동물 사료 한국 시장",
            "강아지 사료 트렌드 2025",
            "premium pet food market growth",  # 영어 쿼리
            "유기농 펫푸드 소비자 선호",
        ],
    ),
]

TOP_K = 10
THRESHOLD_CANDIDATES = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80]
CURRENT_THRESHOLD = float(os.environ.get("RAG_DISTANCE_THRESHOLD", "0.65"))


for ns, queries in TARGETS:
    pd = _default_chroma_dir(ns)
    if not Path(pd).exists():
        continue

    try:
        vs = _get_vs(ns, pd)
    except Exception as e:
        print(f"[{ns}] open failed: {e}")
        continue

    print(f"\n{'=' * 70}")
    print(f"=== {ns} ===")
    print(f"{'=' * 70}")

    all_distances: list[float] = []
    per_query: list[tuple[str, list[float]]] = []

    for q in queries:
        try:
            # similarity_search_with_score는 (Document, distance) 튜플 반환
            results = vs.similarity_search_with_score(q, k=TOP_K)
        except Exception as e:
            print(f"  query '{q}' failed: {e}")
            continue

        distances = [score for _, score in results]
        per_query.append((q, distances))
        all_distances.extend(distances)

    if not all_distances:
        print("  no results")
        continue

    # 쿼리별 출력
    print(f"\n  [per-query top-{TOP_K} distances]")
    for q, dists in per_query:
        q_short = q if len(q) <= 35 else q[:32] + "..."
        d_str = " ".join(f"{d:.3f}" for d in dists)
        print(f"    {q_short:35s} | {d_str}")

    # 전체 분포
    n = len(all_distances)
    sorted_d = sorted(all_distances)
    avg = statistics.mean(all_distances)
    median = statistics.median(all_distances)
    p25 = sorted_d[n // 4]
    p75 = sorted_d[3 * n // 4]
    p95 = sorted_d[min(n - 1, int(n * 0.95))]
    p99 = sorted_d[min(n - 1, int(n * 0.99))]
    
    print(f"\n  [overall distribution] n={n}")
    print(f"    min={sorted_d[0]:.3f}  p25={p25:.3f}  median={median:.3f}  p75={p75:.3f}")
    print(f"    p95={p95:.3f}  p99={p99:.3f}  max={sorted_d[-1]:.3f}  avg={avg:.3f}")

    # threshold별 컷 비율
    print(f"\n  [threshold candidates]")
    print(f"    {'threshold':<12} {'kept':<10} {'cut':<10} {'cut %':<8}")
    for t in THRESHOLD_CANDIDATES:
        kept = sum(1 for d in all_distances if d < t)
        cut = n - kept
        cut_pct = cut * 100 / n
        marker = "  ← current" if abs(t - CURRENT_THRESHOLD) < 0.001 else ""
        print(f"    {t:<12.2f} {kept:<10d} {cut:<10d} {cut_pct:<8.1f}%{marker}")

print(f"\n{'=' * 70}")
print("=== done ===")