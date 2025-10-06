# mini_ingest_check.py
import os, tempfile
from pathlib import Path
from langchain_core.documents import Document

os.environ["CHROMA_NAMESPACE"] = "keei-test"
root = Path(tempfile.mkdtemp())
# CHROMA_DIR이 루트거나 기존 ns가 붙은 경로여도 동작 확인
os.environ["CHROMA_DIR"] = str(root / "chroma_store" / "old-ns")

from tools.web_rag import documents_to_chroma, retrieve, _default_chroma_dir

expected_dir = Path(_default_chroma_dir(os.environ["CHROMA_NAMESPACE"]))
print("expected_dir =", expected_dir)

# 1) 더미 문서 2개 적재
docs = [
    Document(page_content="alpha bravo charlie", metadata={"source": "file://doc1"}),
    Document(page_content="delta echo foxtrot", metadata={"source": "file://doc2"}),
]
n_src, n_chunks = documents_to_chroma(docs, verbose=False)
print("loaded:", n_src, "docs,", n_chunks, "chunks")

# 2) 디렉터리 실존/파일 생성 확인
assert expected_dir.exists(), "persist dir not created"
assert any(expected_dir.iterdir()), "persist dir is empty"

# 3) 검색 동작 확인
hits = retrieve.invoke({"query": "alpha", "top_k": 3})
print("hits:", len(hits))
assert len(hits) >= 1, "retrieve failed"

print("✅ mini ingest ok")
