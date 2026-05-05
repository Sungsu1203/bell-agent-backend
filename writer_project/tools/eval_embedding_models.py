"""
3단계: 두 임베딩 모델 비교 평가 (층위 1 + 층위 2).

비교 대상:
    - text-multilingual-embedding-002 (768d, 현 운영) — REF
    - gemini-embedding-001 (3072d, 평가 대상) — TGT

평가 층위:
    - 층위 1 (clean): local-only ranking, web-only ranking (각 store 내부)
    - 층위 2 (운영 정렬): local + web 합친 통합 풀 ranking

골드셋: eval/goldset/venfobel-vitamin/chunks_sampled.jsonl
        (query 필드가 채워진 행만 사용)

산출 지표 (층위마다):
    1. 분리도: relevant / irrelevant / hardneg 거리 분포 (median, p25, p75, p95)
    2. 단조성: top-1 / top-3 accuracy, MRR
    3. threshold 분석: 현 운영 0.65 기준 precision/recall

사전 가설 (박제용 — 결과 보기 전 못박음):
    층위 2(운영 정렬) 기준으로
    - gap 1.3배 이상 + top-1 +5%p 이상 → 마이그레이션 가치 있음
    - 그 미만 → §12-4 결론 "보류 유지"

사용법:
    python tools/eval_embedding_models.py

출력:
    eval/results/venfobel-vitamin_gemini_vs_multilingual.md
"""

import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.config import load_topic_env

load_topic_env()

from langchain_google_vertexai import VertexAIEmbeddings

# ---------- 설정 ----------
TOPIC_SLUG = os.environ["TOPIC_SLUG"]
GOLDSET_FILE = Path("eval/goldset") / TOPIC_SLUG / "chunks_sampled.jsonl"
OUTPUT_FILE = Path("eval/results") / f"{TOPIC_SLUG}_gemini_vs_multilingual.md"

MODELS = [
    {"name": "text-multilingual-embedding-002", "dim": 768,  "label": "REF"},
    {"name": "gemini-embedding-001",            "dim": 3072, "label": "TGT"},
]

# 층위 정의: 각 층위는 (이름, 청크 풀 필터)로 정의
TIERS = [
    {"name": "tier1_local",  "stores": {"local"},        "desc": "층위 1: local store 내부"},
    {"name": "tier1_web",    "stores": {"web"},          "desc": "층위 1: web store 내부"},
    {"name": "tier2_merged", "stores": {"local", "web"}, "desc": "층위 2: local+web 통합 (운영 정렬)"},
]

# 운영 threshold (현재 768d 기준)
OPERATIONAL_THRESHOLD = 0.65

# 사전 가설 임계값 (층위 2 기준)
HYPOTHESIS_GAP_RATIO = 1.3
HYPOTHESIS_TOP1_DELTA = 0.05

MIN_QUERIES_PER_TIER = 5  # 이 미만이면 해당 층위 제외

# ---------- 유틸 ----------
def load_goldset() -> list[dict]:
    if not GOLDSET_FILE.exists():
        print(f"ERROR: 골드셋 파일 없음 → {GOLDSET_FILE}")
        print(f"먼저 1단계: python tools/sample_chunks_for_eval.py 실행")
        sys.exit(1)

    rows = []
    with GOLDSET_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows.append(row)

    filled = [r for r in rows if r.get("query", "").strip()]
    print(f"  골드셋 로드: 전체 {len(rows)}개 중 query 채워진 것 {len(filled)}개")

    counts = {}
    for r in filled:
        counts[r.get("store", "?")] = counts.get(r.get("store", "?"), 0) + 1
    print(f"  store별 분포: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    if len(filled) == 0:
        print(f"  ERROR: 쿼리 0개. eval/goldset/.../README.md 가이드 따라 작성 필요.")
        sys.exit(1)

    return filled


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Chroma의 distance와 동일한 정의: 1 - cosine_similarity. 범위 [0, 2]."""
    sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))
    return 1.0 - sim


def percentiles(values: list[float]) -> dict:
    if not values:
        return {"median": math.nan, "p25": math.nan, "p75": math.nan, "p95": math.nan}
    arr = np.array(values)
    return {
        "median": float(np.median(arr)),
        "p25": float(np.percentile(arr, 25)),
        "p75": float(np.percentile(arr, 75)),
        "p95": float(np.percentile(arr, 95)),
    }


def fmt(x: float, n: int = 3) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return f"{x:.{n}f}"


# ---------- 모델별 임베딩 (한 번만) ----------
def embed_all(model_cfg: dict, goldset: list[dict]) -> dict:
    """모델 1개로 전체 청크 + 전체 쿼리를 임베딩. 한 번만 호출."""
    print(f"\n  [{model_cfg['label']}] {model_cfg['name']} (dim={model_cfg['dim']})")

    emb = VertexAIEmbeddings(
        model=model_cfg["name"],
        project=os.environ.get("GCP_PROJECT_ID"),
        location=os.environ.get("GCP_REGION", "us-central1"),
    )

    chunk_texts = [r["text"] for r in goldset]
    queries = [r["query"].strip() for r in goldset]

    print(f"    청크 임베딩 {len(chunk_texts)}개 ...", end="", flush=True)
    t0 = time.time()
    chunk_embs = np.array(emb.embed_documents(chunk_texts))
    print(f" {time.time() - t0:.1f}s")

    print(f"    쿼리 임베딩 {len(queries)}개 ...", end="", flush=True)
    t0 = time.time()
    query_embs = np.array(emb.embed_documents(queries))
    print(f" {time.time() - t0:.1f}s")

    return {
        "model": model_cfg["name"],
        "label": model_cfg["label"],
        "dim": model_cfg["dim"],
        "chunk_embs": chunk_embs,
        "query_embs": query_embs,
    }


# ---------- 층위별 평가 ----------
def evaluate_tier(model_data: dict, goldset: list[dict], tier: dict) -> dict | None:
    """
    한 모델 임베딩 + 한 층위로 ranking 평가.
    
    핵심: 층위는 *청크 풀 필터*만 적용한다. 쿼리는 그 풀 안에 있는 정답 청크에 대응되는 것만 사용.
    예: tier1_local이면 store=='local' 청크만 풀로 쓰고, 그 청크가 정답인 쿼리만 평가.
    """
    chunk_embs = model_data["chunk_embs"]
    query_embs = model_data["query_embs"]

    # 청크 풀: 층위 필터 적용
    pool_indices = [i for i, r in enumerate(goldset) if r["store"] in tier["stores"]]
    if len(pool_indices) < MIN_QUERIES_PER_TIER:
        return None

    pool_chunk_embs = chunk_embs[pool_indices]
    pool_size = len(pool_indices)

    # 쿼리: 풀 안에 정답이 있는 것만 (= pool_indices와 동일)
    query_indices = pool_indices

    relevant_distances = []
    irrelevant_distances = []
    hardneg_distances = []
    rank_of_correct = []

    for q_idx, full_idx in enumerate(query_indices):
        q_emb = query_embs[full_idx]
        # 풀 안에서 거리 계산
        dists = np.array([cosine_distance(q_emb, pool_chunk_embs[j]) for j in range(pool_size)])

        # q_idx == 풀 내 정답 인덱스 (pool_indices가 query_indices와 동일하므로)
        rel_d = float(dists[q_idx])
        irrel = [float(dists[j]) for j in range(pool_size) if j != q_idx]

        relevant_distances.append(rel_d)
        irrelevant_distances.extend(irrel)
        hardneg_distances.append(min(irrel) if irrel else math.nan)

        sorted_indices = np.argsort(dists)
        rank = int(np.where(sorted_indices == q_idx)[0][0]) + 1
        rank_of_correct.append(rank)

    n = len(query_indices)
    rel_stats = percentiles(relevant_distances)
    irrel_stats = percentiles(irrelevant_distances)
    hardneg_stats = percentiles(hardneg_distances)

    gap = irrel_stats["median"] - rel_stats["median"]
    hardneg_gap = hardneg_stats["median"] - rel_stats["median"]

    top1 = sum(1 for r in rank_of_correct if r == 1) / n
    top3 = sum(1 for r in rank_of_correct if r <= 3) / n
    mrr = sum(1.0 / r for r in rank_of_correct) / n

    rel_below = sum(1 for d in relevant_distances if d < OPERATIONAL_THRESHOLD)
    irrel_below = sum(1 for d in irrelevant_distances if d < OPERATIONAL_THRESHOLD)
    recall = rel_below / len(relevant_distances) if relevant_distances else 0.0
    precision = (
        rel_below / (rel_below + irrel_below) if (rel_below + irrel_below) > 0 else 0.0
    )

    return {
        "tier": tier["name"],
        "tier_desc": tier["desc"],
        "n_queries": n,
        "pool_size": pool_size,
        "rel_stats": rel_stats,
        "irrel_stats": irrel_stats,
        "hardneg_stats": hardneg_stats,
        "gap": gap,
        "hardneg_gap": hardneg_gap,
        "top1": top1,
        "top3": top3,
        "mrr": mrr,
        "recall_at_threshold": recall,
        "precision_at_threshold": precision,
    }


# ---------- 리포트 ----------
def render_tier_table(ref_r: dict, tgt_r: dict) -> list[str]:
    """한 층위 결과를 4개 표(분리도/단조성/threshold/권장 threshold)로 렌더."""
    lines = []
    lines.append(f"### {ref_r['tier_desc']}")
    lines.append("")
    lines.append(f"- 쿼리 수: **{ref_r['n_queries']}** (풀 크기: {ref_r['pool_size']})")
    lines.append("")

    # 1) 분리도
    lines.append("**1. 분리도 (코사인 distance)**")
    lines.append("")
    lines.append("| 모델 | rel.median | rel.p75 | irrel.median | gap | hardneg.median | hardneg.gap |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in [ref_r, tgt_r]:
        lines.append(
            f"| {r['_label']} ({r['_dim']}d) | "
            f"{fmt(r['rel_stats']['median'])} | {fmt(r['rel_stats']['p75'])} | "
            f"{fmt(r['irrel_stats']['median'])} | "
            f"**{fmt(r['gap'])}** | {fmt(r['hardneg_stats']['median'])} | {fmt(r['hardneg_gap'])} |"
        )
    lines.append("")

    # 2) 단조성
    lines.append("**2. Ranking**")
    lines.append("")
    lines.append("| 모델 | top-1 | top-3 | MRR |")
    lines.append("| --- | --- | --- | --- |")
    for r in [ref_r, tgt_r]:
        lines.append(
            f"| {r['_label']} ({r['_dim']}d) | "
            f"{r['top1']*100:.1f}% | {r['top3']*100:.1f}% | {fmt(r['mrr'])} |"
        )
    lines.append("")

    # 3) threshold
    lines.append(f"**3. Threshold {OPERATIONAL_THRESHOLD} 적용 시**")
    lines.append("")
    lines.append("| 모델 | precision | recall |")
    lines.append("| --- | --- | --- |")
    for r in [ref_r, tgt_r]:
        lines.append(
            f"| {r['_label']} ({r['_dim']}d) | "
            f"{r['precision_at_threshold']*100:.1f}% | "
            f"{r['recall_at_threshold']*100:.1f}% |"
        )
    lines.append("")

    # 4) TGT 권장 threshold
    if not math.isnan(tgt_r["rel_stats"]["p75"]) and not math.isnan(tgt_r["hardneg_stats"]["median"]):
        suggested = (tgt_r["rel_stats"]["p75"] + tgt_r["hardneg_stats"]["median"]) / 2
        lines.append(f"**TGT 권장 threshold**: ~{fmt(suggested, 2)} "
                     f"(rel.p75={fmt(tgt_r['rel_stats']['p75'])} 와 "
                     f"hardneg.median={fmt(tgt_r['hardneg_stats']['median'])} 의 중간)")
        lines.append("")

    return lines


def render_report(goldset: list[dict], all_results: dict) -> str:
    """
    all_results 구조:
    {
      "tier1_local":  {"REF": {...}, "TGT": {...}} or None,
      "tier1_web":    {"REF": {...}, "TGT": {...}} or None,
      "tier2_merged": {"REF": {...}, "TGT": {...}},
    }
    """
    lines = []
    lines.append(f"# 임베딩 모델 비교 평가 — {TOPIC_SLUG}")
    lines.append("")
    lines.append(f"**골드셋 크기**: {len(goldset)}쿼리")

    counts = {}
    for r in goldset:
        counts[r.get("store", "?")] = counts.get(r.get("store", "?"), 0) + 1
    lines.append(f"**store별 분포**: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    lines.append("")
    lines.append("**비교 모델**:")
    for m in MODELS:
        lines.append(f"- {m['label']}: `{m['name']}` ({m['dim']}d)")
    lines.append("")

    # ===== 결론 (층위 2 기준) =====
    tier2 = all_results.get("tier2_merged")
    if tier2 and "REF" in tier2 and "TGT" in tier2:
        ref2 = tier2["REF"]
        tgt2 = tier2["TGT"]
        gap_ratio = tgt2["gap"] / ref2["gap"] if ref2["gap"] > 0 else float("nan")
        top1_delta = tgt2["top1"] - ref2["top1"]
        pass_gap = gap_ratio >= HYPOTHESIS_GAP_RATIO
        pass_top1 = top1_delta >= HYPOTHESIS_TOP1_DELTA
        verdict_pass = pass_gap and pass_top1

        if verdict_pass:
            verdict = ("**마이그레이션 가치 있음** — 본 평가(인덱스 재생성, threshold 재조정, "
                       "회귀 테스트) 진행 검토.")
        elif pass_gap or pass_top1:
            verdict = ("**부분 통과** — 한 지표만 개선됨. 운영 부담(인덱스 재생성, "
                       "3072d 저장 비용 4배, threshold 재조정) 고려해 보류 권장.")
        else:
            verdict = ("**보류 유지** — §12-4 결론대로 마이그레이션 가치 없음. "
                       "(b) 패키지 import 교체 평가로 이동 권장.")

        lines.append("## 결론 (층위 2 기준)")
        lines.append("")
        lines.append(verdict)
        lines.append("")
        lines.append("**사전 가설 판정** (결과 보기 전에 박제된 임계값)")
        lines.append("")
        lines.append("| 조건 | 임계값 | 측정값 | 통과 |")
        lines.append("| --- | --- | --- | --- |")
        lines.append(f"| gap_ratio (TGT/REF) | ≥ {HYPOTHESIS_GAP_RATIO:.2f}× | "
                     f"{fmt(gap_ratio, 2)}× | {'✅' if pass_gap else '❌'} |")
        lines.append(f"| top-1 delta (TGT−REF) | ≥ +{HYPOTHESIS_TOP1_DELTA*100:.0f}%p | "
                     f"{top1_delta*100:+.1f}%p | {'✅' if pass_top1 else '❌'} |")
        lines.append("")

    # ===== 층위별 상세 =====
    lines.append("## 층위별 결과")
    lines.append("")
    lines.append("- **층위 1** (`tier1_local`, `tier1_web`): 각 store 내부 ranking. "
                 "임베딩 모델 자체의 store-내부 품질만 측정.")
    lines.append("- **층위 2** (`tier2_merged`): local+web 통합 풀 ranking. "
                 "운영 `_dual_retrieve` 머지 후 시점과 정렬.")
    lines.append("")

    for tier_def in TIERS:
        tier_name = tier_def["name"]
        tier_data = all_results.get(tier_name)
        if not tier_data or "REF" not in tier_data or "TGT" not in tier_data:
            lines.append(f"### {tier_def['desc']}")
            lines.append("")
            lines.append(f"_쿼리 부족 ({MIN_QUERIES_PER_TIER}개 미만) — 평가 스킵._")
            lines.append("")
            continue

        ref_r = tier_data["REF"]
        tgt_r = tier_data["TGT"]
        lines.extend(render_tier_table(ref_r, tgt_r))

    # ===== 운영 부담 비교 =====
    lines.append("## 운영 부담 비교 (참고)")
    lines.append("")
    lines.append("| 항목 | REF (768d) | TGT (3072d) |")
    lines.append("| --- | --- | --- |")
    lines.append("| 벡터 차원 | 768 | 3072 (4×) |")
    lines.append("| 디스크 저장 | 1× | ~4× |")
    lines.append("| 인덱스 재생성 | — | 필요 |")
    lines.append("| Threshold 재조정 | 0.65 (현 운영) | 위 권장값 참고 |")
    lines.append("")

    # ===== 부록 =====
    lines.append("## 부록: 골드셋 샘플")
    lines.append("")
    lines.append("처음 5개 쿼리:")
    lines.append("")
    for i, r in enumerate(goldset[:5]):
        text_preview = r['text'][:80] + ('...' if len(r['text']) > 80 else '')
        lines.append(f"{i+1}. **`{r['query']}`** [{r['store']}] ← `{text_preview}`")
    lines.append("")

    return "\n".join(lines)


# ---------- 메인 ----------
def main() -> int:
    print(f"=== 임베딩 모델 비교 평가 (topic={TOPIC_SLUG}) ===\n")

    print("[1/3] 골드셋 로드")
    goldset = load_goldset()

    print("\n[2/3] 모델별 임베딩 (한 번만)")
    model_data = {}
    for cfg in MODELS:
        model_data[cfg["label"]] = embed_all(cfg, goldset)

    print("\n[3/3] 층위별 평가")
    all_results: dict = {}
    for tier in TIERS:
        all_results[tier["name"]] = {}
        n_in_tier = sum(1 for r in goldset if r["store"] in tier["stores"])
        print(f"\n  {tier['desc']} (쿼리 {n_in_tier}개)")
        if n_in_tier < MIN_QUERIES_PER_TIER:
            print(f"    → 스킵 (쿼리 {MIN_QUERIES_PER_TIER}개 미만)")
            continue
        for label, mdata in model_data.items():
            res = evaluate_tier(mdata, goldset, tier)
            if res is None:
                continue
            res["_label"] = label
            res["_dim"] = next(m["dim"] for m in MODELS if m["label"] == label)
            all_results[tier["name"]][label] = res
            print(f"    [{label}] gap={fmt(res['gap'])} top-1={res['top1']*100:.1f}% "
                  f"MRR={fmt(res['mrr'])}")

    print("\n[리포트 생성]")
    report = render_report(goldset, all_results)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(report, encoding="utf-8")
    print(f"  → {OUTPUT_FILE}")

    # 콘솔 요약 (층위 2 기준)
    tier2 = all_results.get("tier2_merged", {})
    if "REF" in tier2 and "TGT" in tier2:
        ref2 = tier2["REF"]
        tgt2 = tier2["TGT"]
        gap_ratio = tgt2["gap"] / ref2["gap"] if ref2["gap"] > 0 else float("nan")
        top1_delta = tgt2["top1"] - ref2["top1"]
        print(f"\n=== 층위 2 (운영 정렬) 요약 ===")
        print(f"  gap_ratio = {fmt(gap_ratio, 2)}×  (가설 임계: {HYPOTHESIS_GAP_RATIO}×)")
        print(f"  top-1 Δ   = {top1_delta*100:+.1f}%p  (가설 임계: +{HYPOTHESIS_TOP1_DELTA*100:.0f}%p)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
