"""§citation-claim-faithfulness R2-T3 — 문장↔abstract 코사인 분포 (로컬 임베딩, 유료 0).

입력  : citation_pairs.json (R2-T2), valid 페어만 사용.
모델  : BGE-m3 (1순위) → multilingual-e5-large (폴백) → all-MiniLM-L6-v2(캐시, 최후).
        전부 로컬 무료. GPU 불필요(CPU).
인코딩: 2안 비교(짧은 테스트) —
        (A) symmetric : 프리픽스 없음 (BGE-m3 native).
        (B) asymmetric: 문장="query: ", abstract="passage: " (e5 관습). 비대칭이 mismatch
            변별에 유리한지 확인.
출력  : 전체 valid 페어 코사인 분포(min/max/mean/median/사분위 + 텍스트 히스토그램) +
        Beebe [[58]] 페어의 분포 내 위치. ⚠️ 임계 적용·플래그 없음(사용자 결정 대기).
        cosine_distribution.json 저장.

실행  : <emb_venv>/bin/python "scripts/§paper-writer-1/emb_cosine.py"
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parents[1] / "scripts" / "output" / "§paper-writer-1"
PAIRS = OUT_DIR / "citation_pairs.json"
DIST_OUT = OUT_DIR / "cosine_distribution.json"

_MODEL_CANDIDATES = [
    ("BAAI/bge-m3", "bge-m3"),
    ("intfloat/multilingual-e5-large", "e5-large"),
    ("sentence-transformers/all-MiniLM-L6-v2", "minilm-cached"),
]


def _load_model() -> tuple[SentenceTransformer, str]:
    last = None
    for repo, name in _MODEL_CANDIDATES:
        try:
            print(f"[model] loading {repo} ...", flush=True)
            # torch 2.2.2(x86 mac 최종) + CVE-2025-32434 가드 회피: safetensors 강제.
            m = SentenceTransformer(repo, device="cpu",
                                    model_kwargs={"use_safetensors": True})
            print(f"[model] loaded {name}", flush=True)
            return m, name
        except Exception as e:  # noqa: BLE001
            print(f"[model] {repo} FAIL: {type(e).__name__}: {e}", flush=True)
            last = e
    raise RuntimeError(f"all models failed: {last}")


def _cos(model: SentenceTransformer, a: list[str], b: list[str]) -> np.ndarray:
    ea = model.encode(a, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
    eb = model.encode(b, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
    return np.sum(ea * eb, axis=1)  # 정규화됨 → dot = cosine


def _describe(vals: list[float]) -> dict:
    s = sorted(vals)
    q = np.quantile(s, [0.25, 0.5, 0.75]).tolist()
    return {
        "n": len(s), "min": round(min(s), 4), "max": round(max(s), 4),
        "mean": round(st.mean(s), 4), "median": round(q[1], 4),
        "q25": round(q[0], 4), "q75": round(q[2], 4),
    }


def _histogram(vals: list[float], bins: int = 10) -> str:
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        hi = lo + 1e-9
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in vals:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    mx = max(counts) or 1
    lines = []
    for i, c in enumerate(counts):
        b0 = lo + i * width
        bar = "#" * int(round(30 * c / mx))
        lines.append(f"  [{b0:+.3f},{b0+width:+.3f}) {c:3d} {bar}")
    return "\n".join(lines)


def main() -> int:
    data = json.loads(PAIRS.read_text(encoding="utf-8"))
    valid = [p for p in data["pairs"] if p["status"] == "valid"]
    print(f"[pairs] valid={len(valid)}")

    model, model_name = _load_model()
    sents = [p["sentence"] for p in valid]
    absts = [p["abstract"] for p in valid]

    variants = {
        "A_symmetric": (sents, absts),
        "B_asymmetric_query_passage": (["query: " + s for s in sents],
                                       ["passage: " + a for a in absts]),
    }

    results: dict[str, dict] = {}
    per_pair: list[dict] = [{"n": p["n"], "cited_title": p["cited_title"],
                             "sentence": p["sentence"][:200]} for p in valid]

    for vname, (qa, pa) in variants.items():
        cos = _cos(model, qa, pa)
        vals = [float(x) for x in cos]
        results[vname] = {"describe": _describe(vals),
                          "histogram": _histogram(vals)}
        for i, v in enumerate(vals):
            per_pair[i][vname] = round(v, 4)

    # Beebe [[58]] 위치
    beebe_idx = next((i for i, p in enumerate(valid) if p["n"] == 58), None)

    out = {
        "source": "emb_cosine (R2-T3, local embedding, 유료 0)",
        "model": model_name,
        "n_valid_pairs": len(valid),
        "variants": {k: v["describe"] for k, v in results.items()},
        "note": "임계 미적용 — 분포만. 사용자 임계 결정 대기(T4).",
        "per_pair": sorted(per_pair, key=lambda d: d.get("A_symmetric", 1.0)),
    }
    DIST_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 리포트 ──
    print(f"\n[saved] {DIST_OUT}   model={model_name}")
    for vname in variants:
        d = results[vname]["describe"]
        print(f"\n=== {vname} ===")
        print(f"  n={d['n']} min={d['min']} q25={d['q25']} median={d['median']} "
              f"mean={d['mean']} q75={d['q75']} max={d['max']}")
        print(results[vname]["histogram"])

    if beebe_idx is not None:
        print("\n--- Beebe [[58]] 위치 ---")
        for vname in variants:
            v = per_pair[beebe_idx][vname]
            allv = sorted(pp[vname] for pp in per_pair)
            rank = sum(1 for x in allv if x < v)
            pct = 100.0 * rank / len(allv)
            print(f"  {vname}: cos={v:.4f}  하위 {pct:.0f}%tile (rank {rank}/{len(allv)})")

    # 최저 코사인 5건 (거름망 표적 후보 sanity)
    print("\n--- 최저 코사인 5건 (A_symmetric 기준) ---")
    lowest = sorted(per_pair, key=lambda d: d["A_symmetric"])[:5]
    for pp in lowest:
        print(f"  cos={pp['A_symmetric']:.4f} [[{pp['n']}]] {(pp['cited_title'] or '')[:42]!r}")
        print(f"       文: {pp['sentence'][:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
