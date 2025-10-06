# smoke_check_ns_path.py
import os, tempfile
from pathlib import Path

# 1) 임시 베이스 + 루트명이 'chroma_store' 인 케이스
tmp = Path(tempfile.mkdtemp())
os.environ["CHROMA_NAMESPACE"] = "keei-test"
os.environ["CHROMA_DIR"] = str(tmp / "chroma_store")

from tools.web_rag import _default_chroma_dir  # 내부에서 _resolve_persist_dir 호출하도록 수정되어 있어야 함

expected = Path(os.environ["CHROMA_DIR"]) / os.environ["CHROMA_NAMESPACE"]
got = Path(_default_chroma_dir(os.environ["CHROMA_NAMESPACE"]))
print("[CASE A] expected:", expected)
print("[CASE A] got     :", got)
assert got == expected, "CASE A: namespace-dir mismatch"

# 2) CHROMA_DIR이 '.../chroma_store/<old_ns>'로 주어졌을 때 → <store_root>/<new_ns> 로 교체되나?
os.environ["CHROMA_DIR"] = str(tmp / "chroma_store" / "old-ns")
expected2 = (tmp / "chroma_store" / os.environ["CHROMA_NAMESPACE"])
got2 = Path(_default_chroma_dir(os.environ["CHROMA_NAMESPACE"]))
print("[CASE B] expected:", expected2)
print("[CASE B] got     :", got2)
assert got2 == expected2, "CASE B: namespace replace logic failed"

print("✅ smoke ok")
