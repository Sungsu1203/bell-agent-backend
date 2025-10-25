# tests/test_gatekeep.py
from __future__ import annotations
import os
import importlib
import pytest

def _imp():
    m = importlib.import_module("settings_gatekeep")
    return m

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ["GATE_KEEP_SOURCES", "ALLOWED_DOMAINS"]:
        monkeypatch.delenv(k, raising=False)
    yield

def test_gatekeep_default_off(monkeypatch):
    sg = _imp()
    monkeypatch.delenv("GATE_KEEP_SOURCES", raising=False)
    assert sg.gatekeep_enabled() is False

def test_gatekeep_on_with_empty_allowlist(monkeypatch, capsys):
    sg = _imp()
    monkeypatch.setenv("GATE_KEEP_SOURCES", "1")
    monkeypatch.delenv("ALLOWED_DOMAINS", raising=False)
    # 빈 허용리스트면 내부 정책상 경고 로그 후 외부 차단이 기대된다고 가정
    assert sg.gatekeep_enabled() is True
    assert sg.get_allowed_domains() == set()

def test_allowed_domains_parse(monkeypatch):
    sg = _imp()
    monkeypatch.setenv("ALLOWED_DOMAINS", " github.com , OpenAI.com ,, example.org ")
    assert sg.get_allowed_domains() == {"github.com", "openai.com", "example.org"}

@pytest.mark.skipif(not hasattr(importlib.import_module("settings_gatekeep"), "_normalize_host"), reason="no _normalize_host")
def test_normalize_host_variants(monkeypatch):
    sg = _imp()
    n = sg._normalize_host  # type: ignore[attr-defined]
    cases = {
        "https://www.Example.com:443/path?utm=1": "example.com",
        "http://example.com.": "example.com",
        "https://user:pass@sub.EXAMPLE.com:8443/": "sub.example.com:8443",
        "file:///C:/data.txt": "",  # non-network scheme → 빈 호스트 기대
        "http://xn--bcher-kva.example/": "xn--bcher-kva.example",  # IDNA 그대로 혹은 정규화
        "http://localhost:8000": "localhost:8000",
    }
    for u, want in cases.items():
        got = n(u)
        assert got == want, (u, got, want)
