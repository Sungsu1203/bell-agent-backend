"""현재 chroma 인덱스 상태 점검."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

print(f"=== diagnose_embeddings start ===")
print(f"CWD: {Path.cwd()}")
print(f"Script root: {ROOT}")
print()

try:
    from tools.web_rag.ingest_vector import _get_vs, _get_embeddings, _default_chroma_dir
    print("[ok] imports succeeded")
except Exception as e:
    print(f"[FAIL] import error: {e}")
    raise

NAMESPACES = [
    "height-growth-supplement",
    "height-growth-supplement-web",
    "height-growth-supplement-local",
    "pet-food-premium",
    "pet-food-premium-web",
    "pet-food-premium-local",
]

print(f"\n=== checking embedding model ===")
emb = _get_embeddings()
print(f"Embedding class: {type(emb).__name__}")
sample_vec = emb.embed_query('test')
print(f"Sample query embedding dim: {len(sample_vec)}")
if len(sample_vec) == 1 and abs(sample_vec[0]) < 1e-9:
    print("🚨 WARNING: current embedding is DummyEmbeddings (1-D zero)")
elif len(sample_vec) == 768:
    print("✅ embedding looks like text-embedding-004 (768-D)")
else:
    print(f"ℹ️ unusual dim ({len(sample_vec)}), please verify")

print(f"\n=== checking namespaces ===")
print(f"NAMESPACES to check: {NAMESPACES}")
print()

for ns in NAMESPACES:
    pd = _default_chroma_dir(ns)
    if not Path(pd).exists():
        print(f"[{ns}] dir not found")
        continue

    # 1) count만 먼저 — 안전한 호출
    try:
        vs = _get_vs(ns, pd)
        cnt = vs._collection.count()
    except Exception as e:
        print(f"[{ns}] count failed: {e}")
        continue

    if cnt == 0:
        print(f"[{ns}] empty (count=0)")
        continue

    # 2) 실제 검색을 한 번 던져봄 — dim mismatch면 즉시 드러남
    try:
        result = vs._collection.query(
            query_embeddings=[sample_vec],  # 768-D
            n_results=1,
            include=["distances"],
        )
        distances = (result or {}).get("distances") or [[]]
        d0 = distances[0] if distances else []
        if d0:
            dist_val = float(d0[0])
            print(f"[{ns}] count={cnt} ✅ search ok (sample distance={dist_val:.4f})")
        else:
            print(f"[{ns}] count={cnt} ⚠️ search returned no distances")
    except Exception as e:
        emsg = str(e).lower()
        if "dimension" in emsg or "dim" in emsg:
            print(f"[{ns}] count={cnt} 🚨 DIMENSION MISMATCH — index may be polluted: {e}")
        else:
            print(f"[{ns}] count={cnt} search error: {e}")

print(f"\n=== done ===")