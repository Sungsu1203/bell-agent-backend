import os
import importlib
import re
import types
import pytest

# 대상 모듈
MOD_PATH = "tools.web_rag"

@pytest.fixture(autouse=True)
def _env_isolation(monkeypatch):
    # 기본 ENV
    monkeypatch.setenv("NAVER_TRIM_OPERATORS", "1")
    monkeypatch.setenv("NAVER_NEGATIVE_CAP", "0")
    monkeypatch.setenv("NAVER_MAX_LEN", "120")
    monkeypatch.setenv("NAVER_MAX_TOKENS", "8")
    monkeypatch.setenv("WEB_APPLY_DEFAULT_NEGATIVES", "1")
    monkeypatch.setenv("WEB_DEFAULT_NEGATIVES", "-행사 -세미나 -박람회")
    # 모듈 리로드로 최신 ENV 반영
    yield
    importlib.reload(importlib.import_module(MOD_PATH))

def _load():
    return importlib.import_module(MOD_PATH)

def test_sanitize_year_span():
    m = _load()
    q = "(untitled) 한국 전자담배 규제 2020..2022"
    s = m._sanitize_query(q)
    assert "(2020 OR 2021 OR 2022)" in s
    assert "untitled" not in s.lower()

def test_simplify_for_naver_removes_ops_and_caps_neg(monkeypatch):
    m = _load()
    monkeypatch.setenv("NAVER_NEGATIVE_CAP", "1")
    importlib.reload(m)
    q = "site:mfds.go.kr 벤포티아민 -블로그 -쇼핑"
    s = m._simplify_for_naver(q)
    # site: 제거
    assert "site:" not in s
    # -토큰 cap=1 → 1개만 남거나 전부 제거(나머지는 사라짐)
    assert s.count("-") <= 1

def test_should_skip_naver_len_token_threshold(monkeypatch):
    m = _load()
    # 길이 기준
    monkeypatch.setenv("NAVER_MAX_LEN", "20")
    importlib.reload(m)
    long_q = "아주아주아주아주 긴 질의어 테스트 입니다"
    assert m._should_skip_naver(long_q) is True

    # 토큰 기준
    monkeypatch.setenv("NAVER_MAX_LEN", "999")
    monkeypatch.setenv("NAVER_MAX_TOKENS", "3")
    importlib.reload(m)
    many_tokens = "의료기기 인증 기준 절차 가이드"
    assert m._should_skip_naver(many_tokens) is True

def test_should_skip_naver_blocks_googleish_ops():
    m = _load()
    q = "intitle:규정 inurl:notice -행사"
    assert m._should_skip_naver(q) is True

def test_short_brand_query_keeps_negatives_off_for_naver(monkeypatch):
    m = _load()
    # 전역 네거티브는 모듈 내부에서 백엔드별로 붙이는 정책이므로
    # 여기서는 단순화 결과가 짧은 질의로 보전되는지만 확인
    q = "삼성 갤럭시"
    s = m._simplify_for_naver(q)
    assert len(s.split()) <= 3
