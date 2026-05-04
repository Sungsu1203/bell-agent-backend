"""
S1: 운영 OPERATIONAL_THRESHOLD 재조정 효과 검증 - threshold sweep 측정 도구.

§12-12-1 작업의 S1 단계. 단일 모델(현 운영 text-multilingual-embedding-002) 위에서
threshold τ를 sweep하면서 precision/recall/F1을 산출.

운영 retrieval cut-off (`tools/web_rag/ingest_vector.py:1610`)와 동일한 정의:
    drop if distance > threshold

핵심 차별점 — same-source hardneg 보정:
    한 source 파일이 여러 청크로 분할된 경우, 골드셋 정답 청크와 같은 source의
    다른 청크는 hardneg 카운트에서 제외. `source` URI의 fragment(#part=...) 앞부분으로
    source 매칭. venfobel 골드셋의 경우 21 청크 중 17개가 multi-chunk source에서 와서
    이 보정의 effect가 큼.

사용법:
    python tools/threshold_sweep.py

출력:
    eval/threshold_sweep/<topic>_sweep.md
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv("topics/venfobel-vitamin.env", override=True)

from langchain_google_vertexai import VertexAIEmbeddings

# ---------- 설정 ----------
TOPIC_SLUG = "venfobel-vitamin"
GOLDSET_FILE = Path("eval/goldset") / TOPIC_SLUG / "chunks_sampled.jsonl"
OUTPUT_DIR = Path("eval/threshold_sweep")
OUTPUT_FILE = OUTPUT_DIR / f"{TOPIC_SLUG}_sweep.md"

# 운영 모델 (현재 RAG_EMBEDDING_MODEL과 동일해야 함)
MODEL_NAME = "text-multilingual-embedding-002"
MODEL_DIM = 768

# Sweep 범위 — §12-12-1 (i) 결정
SWEEP_THRESHOLDS = [0.150, 0.175, 0.200, 0.225, 0.250, 0.275, 0.300]
BASELINE_THRESHOLDS = [0.600, 0.650]  # 현 토픽 override + 글로벌 default
ALL_THRESHOLDS = sorted(set(SWEEP_THRESHOLDS + BASELINE_THRESHOLDS))

# 절벽 식별 임계값
CLIFF_MIN_JUMP = 0.20  # precision이 한 step 안에서 +20%p 이상 상승하면 절벽

# ---------- 유틸 ----------
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


def normalize_source(source_uri: str) -> str:
    """source URI에서 fragment 제거하여 파일 단위 식별자 반환.

    예: 'file:///D:/.../foo.pdf#part=12&chunk=2' → 'file:///D:/.../foo.pdf'
    """
    return source_uri.split("#", 1)[0]


# ---------- 데이터 로딩 ----------
def load_goldset() -> list[dict]:
    if not GOLDSET_FILE.exists():
        print(f"ERROR: 골드셋 파일 없음 → {GOLDSET_FILE}")
        sys.exit(1)

    rows = []
    with GOLDSET_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    filled = [r for r in rows if r.get("query", "").strip()]
    print(f"  골드셋 로드: 전체 {len(rows)}개 중 query 채워진 것 {len(filled)}개")
    return filled


# ---------- 임베딩 ----------
def embed_all(goldset: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """청크 + 쿼리를 한 번에 임베딩."""
    print(f"\n  모델: {MODEL_NAME} (dim={MODEL_DIM})")

    emb = VertexAIEmbeddings(
        model=MODEL_NAME,
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

    return chunk_embs, query_embs


# ---------- 거리 매트릭스 ----------
def build_distance_matrix(chunk_embs: np.ndarray, query_embs: np.ndarray) -> np.ndarray:
    """n_query × n_chunk 매트릭스. dist_matrix[q, c] = distance(query q, chunk c)."""
    n = len(query_embs)
    matrix = np.zeros((n, n))
    for q in range(n):
        for c in range(n):
            matrix[q, c] = cosine_distance(query_embs[q], chunk_embs[c])
    return matrix


# ---------- Sweep 본체 ----------
def sweep(
    dist_matrix: np.ndarray,
    source_groups: list[str],
    thresholds: list[float],
    same_source_correction: bool,
) -> list[dict]:
    """각 threshold에 대해 precision/recall/F1 산출.

    골드셋 가정: i번째 청크가 i번째 query의 정답 (eval_embedding_models 패턴).

    Args:
        dist_matrix: n_query × n_chunk
        source_groups: 길이 n, source_groups[i] = i번째 청크의 normalized source
        thresholds: sweep할 τ 리스트
        same_source_correction: True면 정답과 same-source인 청크는 hardneg에서 제외

    Returns:
        각 threshold당 dict: {threshold, precision, recall, f1, retrieved_per_q, hardneg_below, ...}
    """
    n = dist_matrix.shape[0]
    results = []

    for tau in thresholds:
        rel_below = 0      # 정답이 retrieved (recall 분자)
        hardneg_below = 0  # hardneg이 retrieved (precision 분모 일부)
        retrieved_total = 0

        for q in range(n):
            answer_idx = q
            answer_source = source_groups[answer_idx]

            for c in range(n):
                dist = dist_matrix[q, c]
                if dist > tau:
                    continue  # cut-off

                retrieved_total += 1

                if c == answer_idx:
                    rel_below += 1
                else:
                    if same_source_correction and source_groups[c] == answer_source:
                        # same-source: hardneg 카운트에서 제외 (회색지대 처리)
                        # retrieved_total은 그대로 (운영에서는 retrieved되니까)
                        # 단 precision 분모에서 제외하기 위해 다시 빼줌
                        retrieved_total -= 1
                        continue
                    hardneg_below += 1

        # precision = rel / (rel + hardneg). same-source는 분모에서 빠짐.
        denom = rel_below + hardneg_below
        precision = rel_below / denom if denom > 0 else 0.0

        # recall = rel / total_relevant (n)
        recall = rel_below / n if n > 0 else 0.0

        # F1
        if precision + recall > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = 0.0

        # query당 평균 retrieved (보정 후 — 분모에 들어가는 수)
        avg_retrieved = (rel_below + hardneg_below) / n if n > 0 else 0.0

        results.append({
            "threshold": tau,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "rel_below": rel_below,
            "hardneg_below": hardneg_below,
            "retrieved_per_q": avg_retrieved,
        })

    return results


# ---------- 절벽 식별 ----------
def detect_cliff(sweep_results: list[dict]) -> dict | None:
    """precision 곡선에서 가장 큰 jump 위치를 절벽으로 식별.

    Returns:
        {"threshold_before": ..., "threshold_after": ..., "jump": ...} 또는 None
    """
    sorted_r = sorted(sweep_results, key=lambda r: r["threshold"])
    best_jump = 0.0
    best = None

    for i in range(1, len(sorted_r)):
        jump = sorted_r[i - 1]["precision"] - sorted_r[i]["precision"]
        # threshold 작을수록 precision 높아짐 (cut-off 강함). i-1이 더 작은 τ.
        if jump > best_jump:
            best_jump = jump
            best = {
                "threshold_low": sorted_r[i - 1]["threshold"],
                "threshold_high": sorted_r[i]["threshold"],
                "precision_low": sorted_r[i - 1]["precision"],
                "precision_high": sorted_r[i]["precision"],
                "jump": jump,
            }

    if best is None or best["jump"] < CLIFF_MIN_JUMP:
        return None
    return best


# ---------- 분포 통계 ----------
def distribution_stats(
    dist_matrix: np.ndarray,
    source_groups: list[str],
) -> dict:
    """relevant / hardneg(raw) / hardneg(보정) 분포 통계."""
    n = dist_matrix.shape[0]
    relevant = []
    hardneg_raw = []
    hardneg_corrected = []

    for q in range(n):
        answer_idx = q
        answer_source = source_groups[answer_idx]
        relevant.append(float(dist_matrix[q, q]))
        for c in range(n):
            if c == answer_idx:
                continue
            d = float(dist_matrix[q, c])
            hardneg_raw.append(d)
            if source_groups[c] != answer_source:
                hardneg_corrected.append(d)

    return {
        "relevant": percentiles(relevant),
        "hardneg_raw": percentiles(hardneg_raw),
        "hardneg_corrected": percentiles(hardneg_corrected),
        "n_relevant": len(relevant),
        "n_hardneg_raw": len(hardneg_raw),
        "n_hardneg_corrected": len(hardneg_corrected),
    }


# ---------- 권장값 산출 ----------
def recommend(sweep_results: list[dict], cliff: dict | None) -> dict:
    """sweep 결과로부터 세 종류 권장값 산출."""
    sorted_r = sorted(sweep_results, key=lambda r: r["threshold"])

    # 1. F1 최대
    best_f1 = max(sorted_r, key=lambda r: r["f1"])

    # 2. precision ≥ 0.5 만족 최저 τ (recall 보존 우선 — τ 클수록 recall 높음)
    p50_candidates = [r for r in sorted_r if r["precision"] >= 0.5]
    p50_recall_max = max(p50_candidates, key=lambda r: r["recall"]) if p50_candidates else None

    # 3. 절벽 직전 (cliff가 있을 때)
    pre_cliff = None
    if cliff is not None:
        pre_cliff = next(
            (r for r in sorted_r if r["threshold"] == cliff["threshold_low"]),
            None,
        )

    return {
        "f1_max": best_f1,
        "p50_recall_max": p50_recall_max,
        "pre_cliff": pre_cliff,
    }


# ---------- 리포트 ----------
def render_markdown(
    goldset_size: int,
    multi_chunk_sources: dict,
    dist_stats: dict,
    sweep_corrected: list[dict],
    sweep_raw: list[dict],
    cliff_corrected: dict | None,
    cliff_raw: dict | None,
    rec: dict,
) -> str:
    lines = []
    lines.append(f"# Threshold Sweep — {TOPIC_SLUG}")
    lines.append("")
    lines.append("§12-12-1 S1 결과. 단일 모델(현 운영 `text-multilingual-embedding-002`) 위에서")
    lines.append("threshold sweep으로 precision/recall/F1을 측정.")
    lines.append("")

    # 입력
    lines.append("## 입력")
    lines.append("")
    lines.append(f"- 골드셋: `{GOLDSET_FILE}` (n={goldset_size})")
    lines.append(f"- 모델: `{MODEL_NAME}` ({MODEL_DIM}d)")
    lines.append(f"- Sweep 범위: {[f'{t:.3f}' for t in sorted(SWEEP_THRESHOLDS)]}")
    lines.append(f"- Baseline: {[f'{t:.3f}' for t in BASELINE_THRESHOLDS]} (현 토픽 override + 글로벌 default)")
    lines.append("")

    # multi-chunk source
    lines.append("## Source 분포")
    lines.append("")
    lines.append(f"- multi-chunk source ({len(multi_chunk_sources)}개):")
    for src, cnt in sorted(multi_chunk_sources.items(), key=lambda x: -x[1]):
        lines.append(f"  - {cnt}x  `...{src[-60:]}`")
    lines.append("")
    total_multi = sum(multi_chunk_sources.values())
    pct = 100.0 * total_multi / goldset_size
    lines.append(f"→ {total_multi}/{goldset_size} 청크 ({pct:.0f}%)가 multi-chunk source 출신. "
                 f"same-source hardneg 보정의 effect 큼.")
    lines.append("")

    # 분포 통계
    lines.append("## Distance 분포")
    lines.append("")
    lines.append("| 카테고리 | n | median | p25 | p75 | p95 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for label, key in [
        ("relevant", "relevant"),
        ("hardneg (raw)", "hardneg_raw"),
        ("hardneg (same-source 보정)", "hardneg_corrected"),
    ]:
        s = dist_stats[key]
        n_key = "n_" + key
        lines.append(
            f"| {label} | {dist_stats[n_key]} | "
            f"{fmt(s['median'])} | {fmt(s['p25'])} | {fmt(s['p75'])} | {fmt(s['p95'])} |"
        )
    lines.append("")

    # Sweep 결과 표 — 보정 ON
    lines.append("## Sweep 결과 (same-source hardneg 보정 ON, 메인)")
    lines.append("")
    lines.append("| τ | precision | recall | F1 | retrieved/q | rel↓ | hardneg↓ |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in sorted(sweep_corrected, key=lambda x: x["threshold"]):
        lines.append(
            f"| {r['threshold']:.3f} | {r['precision']:.3f} | {r['recall']:.3f} | "
            f"{r['f1']:.3f} | {r['retrieved_per_q']:.2f} | "
            f"{r['rel_below']} | {r['hardneg_below']} |"
        )
    lines.append("")

    # Sweep 결과 표 — 보정 OFF
    lines.append("## Sweep 결과 (보정 OFF, 비교용 raw)")
    lines.append("")
    lines.append("| τ | precision | recall | F1 | retrieved/q | rel↓ | hardneg↓ |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in sorted(sweep_raw, key=lambda x: x["threshold"]):
        lines.append(
            f"| {r['threshold']:.3f} | {r['precision']:.3f} | {r['recall']:.3f} | "
            f"{r['f1']:.3f} | {r['retrieved_per_q']:.2f} | "
            f"{r['rel_below']} | {r['hardneg_below']} |"
        )
    lines.append("")

    # 절벽
    lines.append("## 절벽 식별")
    lines.append("")
    if cliff_corrected:
        lines.append(
            f"- 보정 ON: **τ {cliff_corrected['threshold_low']:.3f} → "
            f"{cliff_corrected['threshold_high']:.3f}** 사이에서 "
            f"precision {cliff_corrected['precision_low']:.3f} → "
            f"{cliff_corrected['precision_high']:.3f} "
            f"(jump {cliff_corrected['jump']:+.3f})"
        )
    else:
        lines.append(f"- 보정 ON: 절벽 없음 (jump < {CLIFF_MIN_JUMP})")
    if cliff_raw:
        lines.append(
            f"- 보정 OFF (raw): τ {cliff_raw['threshold_low']:.3f} → "
            f"{cliff_raw['threshold_high']:.3f} "
            f"(jump {cliff_raw['jump']:+.3f})"
        )
    else:
        lines.append(f"- 보정 OFF (raw): 절벽 없음")
    lines.append("")

    # 권장값
    lines.append("## 권장 τ 후보 (보정 ON 기준)")
    lines.append("")
    if rec["f1_max"]:
        r = rec["f1_max"]
        lines.append(f"- **F1 최대**: τ={r['threshold']:.3f} (P={r['precision']:.3f}, R={r['recall']:.3f}, F1={r['f1']:.3f})")
    if rec["pre_cliff"]:
        r = rec["pre_cliff"]
        lines.append(f"- **절벽 직전**: τ={r['threshold']:.3f} (P={r['precision']:.3f}, R={r['recall']:.3f})")
    if rec["p50_recall_max"]:
        r = rec["p50_recall_max"]
        lines.append(f"- **precision≥0.5 중 recall 최대**: τ={r['threshold']:.3f} (P={r['precision']:.3f}, R={r['recall']:.3f})")
    lines.append("")

    # 진행 메모
    lines.append("## §12-12-1 다음 단계 (S3~)")
    lines.append("")
    lines.append("- S3: pet-food-premium 분포 측정 + venfobel 절벽 위치 정성 비교")
    lines.append("- S4: 시나리오 (1/2/3) 판정 → 토픽별 권장값 산출 절차 정립")
    lines.append("- S5: venfobel 토픽 override 적용 (위 권장값 후보 중 선택)")
    lines.append("")

    return "\n".join(lines)


# ---------- main ----------
def main():
    print(f"=== Threshold Sweep — {TOPIC_SLUG} ===")

    # 1. 골드셋
    goldset = load_goldset()
    if not goldset:
        sys.exit(1)
    n = len(goldset)

    # 2. source 그룹화
    source_groups = [normalize_source(r["source"]) for r in goldset]
    src_counts = defaultdict(int)
    for s in source_groups:
        src_counts[s] += 1
    multi_chunk = {s: c for s, c in src_counts.items() if c > 1}

    # 3. 임베딩 + 거리 매트릭스
    chunk_embs, query_embs = embed_all(goldset)
    print(f"\n  거리 매트릭스 ({n}×{n}) 계산 중 ...", end="", flush=True)
    t0 = time.time()
    dist_matrix = build_distance_matrix(chunk_embs, query_embs)
    print(f" {time.time() - t0:.1f}s")

    # 4. 분포 통계
    dist_stats = distribution_stats(dist_matrix, source_groups)
    print(f"\n  Distance 분포:")
    print(f"    relevant median:           {fmt(dist_stats['relevant']['median'])}")
    print(f"    hardneg(raw) median:       {fmt(dist_stats['hardneg_raw']['median'])}")
    print(f"    hardneg(보정) median:      {fmt(dist_stats['hardneg_corrected']['median'])}")

    # 5. Sweep 두 번 (보정 ON / OFF)
    print(f"\n  Sweep ({len(ALL_THRESHOLDS)} 포인트, 보정 ON) ...", end="", flush=True)
    t0 = time.time()
    sweep_corrected = sweep(dist_matrix, source_groups, ALL_THRESHOLDS, same_source_correction=True)
    print(f" {time.time() - t0:.2f}s")

    print(f"  Sweep ({len(ALL_THRESHOLDS)} 포인트, 보정 OFF) ...", end="", flush=True)
    t0 = time.time()
    sweep_raw = sweep(dist_matrix, source_groups, ALL_THRESHOLDS, same_source_correction=False)
    print(f" {time.time() - t0:.2f}s")

    # 6. 절벽 + 권장값
    cliff_corrected = detect_cliff(sweep_corrected)
    cliff_raw = detect_cliff(sweep_raw)
    rec = recommend(sweep_corrected, cliff_corrected)

    # 7. 리포트
    md = render_markdown(
        goldset_size=n,
        multi_chunk_sources=multi_chunk,
        dist_stats=dist_stats,
        sweep_corrected=sweep_corrected,
        sweep_raw=sweep_raw,
        cliff_corrected=cliff_corrected,
        cliff_raw=cliff_raw,
        rec=rec,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(md, encoding="utf-8")
    print(f"\n  → {OUTPUT_FILE}")
    print(f"\n=== 완료 ===")


if __name__ == "__main__":
    main()
