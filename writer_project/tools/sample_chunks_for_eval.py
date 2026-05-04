"""
1단계: venfobel-vitamin Chroma store에서 평가용 청크 샘플링.

운영 dual_retrieve가 web/local만 사용하고 통합 store(슬러그 단독)는 사용하지 않으므로,
평가도 local store와 web store에서만 샘플링한다. 각 store 25개씩, 총 50개.

사용법:
    python tools/sample_chunks_for_eval.py

출력:
    eval/goldset/venfobel-vitamin/chunks_sampled.jsonl

각 줄 형식:
    {"chunk_id": "...", "text": "...", "source": "...", "store": "local|web", "query": ""}
"""

import json
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv("topics/venfobel-vitamin.env", override=True)

# ---------- 설정 ----------
TOPIC_SLUG = "venfobel-vitamin"
CHROMA_BASE = Path("data/chroma_store")

# 운영 dual_retrieve가 사용하는 store만 (통합 store 제외)
STORES = [
    {"name": f"{TOPIC_SLUG}-local", "label": "local"},
    {"name": f"{TOPIC_SLUG}-web",   "label": "web"},
]

OUTPUT_DIR = Path("eval/goldset") / TOPIC_SLUG
OUTPUT_FILE = OUTPUT_DIR / "chunks_sampled.jsonl"

PER_STORE_SAMPLE = 25
MIN_LEN = 100
MAX_LEN = 1200
SEED = 42

# ---------- 메인 ----------
def load_chunks_from_store(store_path: Path, store_label: str) -> list[dict]:
    """단일 Chroma store에서 모든 청크 로드."""
    if not store_path.exists():
        print(f"  [skip] {store_label}: 디렉토리 없음 ({store_path})")
        return []

    try:
        from langchain_chroma import Chroma
        from langchain_google_vertexai import VertexAIEmbeddings

        emb = VertexAIEmbeddings(
            model="text-multilingual-embedding-002",
            project=os.environ.get("GCP_PROJECT_ID"),
            location=os.environ.get("GCP_REGION", "us-central1"),
        )

        vs = Chroma(
            persist_directory=str(store_path),
            embedding_function=emb,
            collection_name=store_path.name,
        )
        col = vs._collection
        result = col.get(include=["documents", "metadatas"])

        docs = result.get("documents", []) or []
        metas = result.get("metadatas", []) or []
        ids = result.get("ids", []) or []

        chunks = []
        for cid, text, meta in zip(ids, docs, metas):
            if not text:
                continue
            source = ""
            if isinstance(meta, dict):
                source = meta.get("source") or meta.get("url") or meta.get("file") or ""
            chunks.append({
                "chunk_id": cid,
                "text": text,
                "source": source,
                "store": store_label,
            })

        print(f"  [ok]   {store_label}: {len(chunks)}개 청크 로드")
        return chunks

    except Exception as e:
        print(f"  [fail] {store_label}: {type(e).__name__}: {e}")
        return []


def sample_from_pool(chunks: list[dict], n: int, seed: int, label: str) -> list[dict]:
    """길이 필터 + dedup + 무작위 샘플링."""
    seen: set[str] = set()
    filtered = []
    for c in chunks:
        text = c["text"].strip()
        if len(text) < MIN_LEN or len(text) > MAX_LEN:
            continue
        key = text[:200]
        if key in seen:
            continue
        seen.add(key)
        filtered.append(c)

    print(f"  {label}: 필터링 후 {len(filtered)}개", end="")

    if len(filtered) < n:
        print(f" (요청 {n} > 가용 {len(filtered)}, 전체 사용)")
        return filtered

    random.seed(seed)
    sampled = random.sample(filtered, n)
    print(f" → {len(sampled)}개 샘플")
    return sampled


def main() -> int:
    print(f"=== 청크 샘플링 (topic={TOPIC_SLUG}) ===\n")

    print("[1/3] Chroma store 로딩")
    store_chunks: dict[str, list[dict]] = {}
    for s in STORES:
        store_path = CHROMA_BASE / s["name"]
        store_chunks[s["label"]] = load_chunks_from_store(store_path, s["label"])

    if not any(store_chunks.values()):
        print("\nERROR: 청크를 하나도 못 받음. store 경로 확인 필요.")
        return 1

    print(f"\n[2/3] 필터링 + 샘플링 (각 store {PER_STORE_SAMPLE}개)")
    sampled: list[dict] = []
    for i, s in enumerate(STORES):
        label = s["label"]
        pool = store_chunks.get(label, [])
        if not pool:
            continue
        s_sample = sample_from_pool(pool, PER_STORE_SAMPLE, SEED + i, label)
        sampled.extend(s_sample)

    print(f"\n[3/3] 출력")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    sampled.sort(key=lambda x: (x["store"], x["chunk_id"]))

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for c in sampled:
            row = {
                "chunk_id": c["chunk_id"],
                "text": c["text"],
                "source": c["source"],
                "store": c["store"],
                "query": "",
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    counts = {}
    for c in sampled:
        counts[c["store"]] = counts.get(c["store"], 0) + 1

    print(f"  → {OUTPUT_FILE}")
    print(f"  store별 분포: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print()
    print("=== 다음 단계 ===")
    print(f"1. {OUTPUT_FILE} 를 VS Code 등으로 열기")
    print(f"2. eval/goldset/{TOPIC_SLUG}/README.md 가이드 따라")
    print(f"   각 청크에 어울리는 한국어 단문 쿼리를 'query' 필드에 입력")
    print(f"   (store별 15~20개씩, 총 30~40개 권장)")
    print(f"3. 채워진 뒤 → python tools/eval_embedding_models.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
