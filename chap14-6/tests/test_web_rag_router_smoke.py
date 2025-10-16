import importlib
import types
import pytest

MOD_PATH = "tools.web_rag"

def _load():
    return importlib.import_module(MOD_PATH)

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    # 백엔드 체인 기본값
    monkeypatch.setenv("SEARCH_BACKENDS", "google_cse,serpapi_naver,serpapi,tavily")
    monkeypatch.setenv("WEB_BACKEND_PICK_POLICY", "first_ok")
    monkeypatch.setenv("WEB_MIN_RESULTS_OK", "2")
    yield

def test_backend_force_directive(monkeypatch):
    m = _load()

    # backend 호출 스텁: 각 엔진명에 따라 결과 갯수 반환
    def fake_backend_call(bk, q, num=10):
        if bk == "serpapi_naver":
            return [{"url":"https://n.example","title":"n","content":""},
                    {"url":"https://n2.example","title":"n2","content":""}]
        if bk == "google_cse":
            return [{"url":"https://g.example","title":"g","content":""}]
        return []

    monkeypatch.setattr(m, "_backend_call", fake_backend_call)

    query = "backend: serpapi_naver; 한국 표준 개정 동향"
    res, path = m.web_search(query, engine="auto", num=5)
    # first_ok 정책: 강제 선두 + 임계치(2) 충족으로 네이버 선택
    assert len(res) == 2
    assert any("n.example" in r["url"] for r in res)

def test_best_of_chain_pick(monkeypatch):
    m = _load()
    def fake_backend_call(bk, q, num=10):
        # 모든 엔진 결과 수 다양
        if bk == "google_cse":
            return [{"url":"https://g1","title":"g1","content":""}]
        if bk == "serpapi_naver":
            return []  # 스킵된 상황 가정
        if bk == "serpapi":
            return [{"url":"https://s1","title":"s1","content":""},
                    {"url":"https://s2","title":"s2","content":""},
                    {"url":"https://s3","title":"s3","content":""}]
        return []
    monkeypatch.setattr(m, "_backend_call", fake_backend_call)
    # 체인은 first_ok지만 전부 시도 후 결과가 없으면 best-of 선택 로직 동작
    res, path = m.web_search("일반 쿼리", engine="auto", num=10)
    assert len(res) == 3
