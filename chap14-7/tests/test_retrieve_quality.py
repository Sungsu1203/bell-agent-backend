from __future__ import annotations
import importlib, os, json, time
import pytest

def _imp():
    return importlib.import_module("tools.web_rag")

@pytest.fixture(scope="module")
def built_collection(tmp_path_factory):
    wr = _imp()
    data = [
        {"title": "assistant-ui", "url": "https://github.com/assistant-ui/assistant-ui", "content": "assistant-ui component library", "raw_content": "assistant-ui component library", "source": "https://github.com/assistant-ui/assistant-ui"},
        {"title": "neon", "url": "https://github.com/neondatabase/yc-idea-matcher", "content": "yc idea matcher", "raw_content": "yc idea matcher", "source": "https://github.com/neondatabase/yc-idea-matcher"},
    ]
    p = tmp_path_factory.mktemp("coll") / "seed.json"
    p.write_text(__import__("json").dumps(data, ensure_ascii=False), encoding="utf-8")
    wr.clear_vector_store(namespace="retrieve_q")
    wr.add_web_pages_json_to_chroma(str(p), collection_name="retrieve_q")
    return "retrieve_q"

def test_retrieve_topk_and_metadata(built_collection):
    wr = _imp()
    t0 = time.monotonic()
    docs = wr.retrieve.invoke({"query": "assistant-ui", "top_k": 3, "collection_name": built_collection})
    dt = time.monotonic() - t0

    assert 1 <= len(docs) <= 3
    for d in docs:
        src = (d.metadata or {}).get("source", "")
        assert "github.com" in src
        txt = d.page_content or ""
        assert len(txt) > 0
        # ▶ Accuracy: 과도한 길이 방지(단일 청크 텍스트 20k chars 미만)
        assert len(txt) < 20000

    # ▶ Perf: 소규모 top_k 검색은 400ms 이내(캐시/로컬 디스크 기준)
    assert dt < 0.4
