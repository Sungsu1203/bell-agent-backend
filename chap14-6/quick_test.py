import os
# 1) 검색/네이버 우선
os.environ["SEARCH_BACKENDS"] = "serpapi_naver,google_cse,serpapi,tavily"
os.environ["WEB_SEARCH_ENGINE"] = "auto"
os.environ["SERPAPI_NAVER_WHERE"] = "web"
os.environ["SERPAPI_NAVER_HL"] = "ko"
os.environ["SERPAPI_NAVER_GL"] = "kr"
# 2) RAG/네임스페이스 고정
os.environ["CHROMA_NAMESPACE"] = "kr-vitamin3"  # 전 구간 동일
# 3) 원문 로딩(품질 모드)
os.environ["WEB_SEARCH_RAW_FETCH_TOP"] = "5"    # 속도모드면 0
# 4) 단위 검색 테스트
from tools.web_rag import web_search, add_web_pages_json_to_chroma, retrieve, ensure_vector_store_cleared_once

ensure_vector_store_cleared_once(namespace=os.getenv("CHROMA_NAMESPACE"))

topics = [
    "한국 피로회복 비타민제 시장 현황",
    "종근당 벤포벨 마케팅 광고 현황",
]
paths = []
for q in topics:
    res, p = web_search.invoke(q, num=10)
    paths.append(p)

for p in paths:
    add_web_pages_json_to_chroma(p, namespace=os.getenv("CHROMA_NAMESPACE"))

docs = retrieve.invoke("벤포벨 효능 및 국내 광고 마케팅 사례", top_k=5, namespace=os.getenv("CHROMA_NAMESPACE"))
print("RAG hits:", len(docs))
for d in docs:
    print("-", d.metadata.get("source"))
