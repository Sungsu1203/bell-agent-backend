from langchain_core.documents import Document
from tools.web_rag import documents_to_chroma, _default_chroma_dir

pd   = _default_chroma_dir("dedup_probe")
ns   = "dedup_probe"

doc1 = Document(page_content="a", metadata={"source": "file:///tmp/a.pdf?sha=AAA#page=1"})
doc2 = Document(page_content="b", metadata={"source": "file:///tmp/a.pdf?sha=BBB#page=1"})

# 1회차: 둘 다 시도
_, added1 = documents_to_chroma([doc1, doc2], namespace=ns, persist_directory=pd, clear=True, verbose=True)
print("added1 =", added1)  # 기대: 2 (무시 안 함) / 1 또는 0 (무시함)

# 2회차: 같은 두 개 다시 시도 (중복 체크)
_, added2 = documents_to_chroma([doc1, doc2], namespace=ns, persist_directory=pd, verbose=True)
print("added2 =", added2)  # 기대: 0
