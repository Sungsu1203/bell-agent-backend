# tests/test_chroma_ingest_and_clear.py
from __future__ import annotations
import importlib, json, time, os
import pytest

class _DummyEmbeddings:
    """Chroma 호환 더미 임베딩 — 항상 비영零 벡터를 반환"""
    def __init__(self, dim: int = 16):
        self.dim = dim
    def embed_documents(self, texts):
        out = []
        for t in texts:
            v = float((len(t) % 7) + 1)
            out.append([v] * self.dim)
        return out
    def embed_query(self, text):
        v = float((len(text) % 7) + 1)
        return [v] * self.dim

def test_ingest_duplicate_and_clear(tmp_path, monkeypatch):
    # 1) 테스트 격리: ENV 먼저 고정
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma_store"))
    monkeypatch.setenv("GATE_KEEP_SOURCES", "1")
    monkeypatch.setenv("ALLOWED_DOMAINS", "github.com")
    monkeypatch.setenv("RAG_CHUNK_CHARS", "500")
    monkeypatch.setenv("RAG_CHUNK_OVERLAP", "50")
    monkeypatch.setenv("USER_AGENT", "TestBot/0.1 (+pytest)")

    # 2) 게이트키핑 캐시 갱신(모듈 임포트 전에!)
    sg = importlib.import_module("settings_gatekeep")
    if hasattr(sg, "refresh_gatekeep_cache"):
        sg.refresh_gatekeep_cache()

    # 3) 이제 web_rag 임포트 (ENV 반영된 상태)
    wr = importlib.import_module("tools.web_rag")

    # 4) 더미 임베딩 주입 (임포트 직후, 첫 인제스트 전에)
    monkeypatch.setattr(wr, "_get_embeddings", lambda embedding=None: _DummyEmbeddings(dim=16))

    # 5) 깨끗한 시작: 네임스페이스/캐시 클리어
    wr.clear_vector_store(namespace="clear_test")
    wr._VS_CACHE.clear()

    data = [
        {"title": "t1", "url": "https://github.com/a", "content": "hello " * 200, "raw_content": "hello " * 200, "source": "https://github.com/a"},
        {"title": "t2", "url": "https://github.com/b", "content": "world " * 200, "raw_content": "world " * 200, "source": "https://github.com/b"},
    ]
    p = tmp_path / "res.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # 6) 첫 인제스트
    t0 = time.monotonic()
    d1, c1 = wr.add_web_pages_json_to_chroma(str(p), collection_name="clear_test")
    t1 = time.monotonic()
    assert d1 == 2 and c1 >= 1, (d1, c1)
    assert (t1 - t0) < 2.0  # 성능 상한

    # 7) 재인제스트 → 중복 방지
    d2, c2 = wr.add_web_pages_json_to_chroma(str(p), collection_name="clear_test")
    assert d2 == 2 and c2 == 0, (d2, c2)

    # 8) 안전 클리어 후 재인제스트
    wr.clear_vector_store(namespace="clear_test")
    wr._VS_CACHE.clear()
    import gc; gc.collect()
    time.sleep(0.8)

    d3, c3 = wr.add_web_pages_json_to_chroma(str(p), collection_name="clear_test")
    assert d3 == 2 and c3 >= 1, (d3, c3)

    # Size sanity
    assert c1 <= 1000 and c3 <= 1000
