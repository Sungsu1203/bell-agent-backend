from __future__ import annotations
import importlib, os, time
import pytest

def _imp():
    return importlib.import_module("settings_gatekeep")

def test_subdomain_and_ports(monkeypatch):
    sg = _imp()
    monkeypatch.setenv("GATE_KEEP_SOURCES", "1")
    monkeypatch.setenv("ALLOWED_DOMAINS", "example.com")

    # ENV → 캐시 반영
    try:
        sg.refresh_gatekeep_cache()
    except Exception:
        pass

    t0 = time.monotonic()
    assert sg.is_allowed_url("https://example.com/page")
    assert not sg.is_allowed_url("https://sub.example.com/page")
    assert sg._normalize_host("https://example.com:443/x") == "example.com"
    assert sg._normalize_host("https://example.com:8443/x") == "example.com:8443"
    # ▶ Perf: 정규화·판단 1ms 내외(여유 5ms)
    assert (time.monotonic() - t0) < 0.005

def test_local_and_special_schemes():
    sg = _imp()
    assert sg.is_local_like("file:///C:/data.txt")
    assert sg.is_local_like("http://localhost:8000/x")
    assert sg.is_local_like("http://127.0.0.1/x")
    assert sg.is_local_like("http://[::1]/x")
