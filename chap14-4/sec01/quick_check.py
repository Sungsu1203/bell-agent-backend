from tools.web_rag import web_search, web_page_json_to_documents, add_web_pages_json_to_chroma
import os

os.environ["WEB_SEARCH_ENGINE"] = "google"  # 또는 사용 가능한 엔진
os.environ["WEB_SEARCH_RAW_FETCH_TOP"] = "0"  # 원문 로딩 비활성화로 속도/안정성 ↑

res, path = web_search.invoke({"query": "IMF World Economic Outlook 2025 site:imf.org"})
print("saved json:", path, "results:", len(res))

docs = web_page_json_to_documents(path)
print("docs from json:", len(docs))

added = add_web_pages_json_to_chroma(path, namespace="smoke", persist_directory="_tmp_chroma\\smoke")
print("chroma added (orig, chunks):", added)
