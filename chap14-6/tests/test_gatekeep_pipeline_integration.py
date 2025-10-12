from __future__ import annotations
import os, importlib, time
import pytest

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GATE_KEEP_SOURCES", "1")
    monkeypatch.setenv("ALLOWED_DOMAINS", "openai.com,github.com")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    yield

def _imp():
    return importlib.import_module("tools.web_rag")

def test_gatekeep_pipeline(monkeypatch, caplog):
    wr = _imp()

    # Mock 검색(허용/차단 혼합)
    monkeypatch.setattr(wr, "_search_tavily", lambda q: [
        {"title": "a", "url": "https://github.com/a", "content": "x", "raw_content": "x", "source": "https://github.com/a"},
        {"title": "b", "url": "https://news.ycombinator.com/item?id=1", "content": "y", "raw_content": "y", "source": "https://news.ycombinator.com/item?id=1"},
        {"title": "c", "url": "https://openai.com/blog", "content": "z", "raw_content": "z", "source": "https://openai.com/blog"},
    ])
    monkeypatch.setattr(wr, "_search_google_cse", lambda q, num=10, timeout=20: [])
    monkeypatch.setattr(wr, "_search_serpapi", lambda q, num=10, timeout=20: [])

    t0 = time.monotonic()
    with caplog.at_level("INFO"):
        res, path = wr.web_search.invoke({"query": "dummy", "engine": "auto", "num": 5})
    dt = time.monotonic() - t0

    kept = [r["url"] for r in res]
    assert "https://github.com/a" in kept
    assert "https://openai.com/blog" in kept
    assert not any("ycombinator.com" in u for u in kept)

    # ▶ Accuracy: kept는 전부 허용 도메인
    assert all( ("github.com" in u) or ("openai.com" in u) for u in kept )

    # ▶ Perf: 게이트키핑 + 정규화 + 저장까지 150ms 이내(모킹 기준)
    assert dt < 0.15

    # 차단 로그 존재
    assert any("GATEKEEP" in r.getMessage() and "blocked" in r.getMessage() for r in caplog.records)

    # 인제스트(2차 방어)
    d, c = wr.add_web_pages_json_to_chroma(path, collection_name="gatekeep_int")
    assert d >= 2 and c >= 1
