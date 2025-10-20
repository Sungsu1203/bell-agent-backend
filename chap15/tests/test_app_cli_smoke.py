from __future__ import annotations
import importlib, time
import pytest

def _imp():
    return importlib.import_module("app")

def test_app_setup_logging_and_exit(monkeypatch, capsys):
    app = _imp()

    monkeypatch.setenv("LOG_JSON", "1")
    t0 = time.monotonic()
    app.setup_logging()
    dt = time.monotonic() - t0
    # ▶ Perf: 로깅 초기화 20ms 이내
    assert dt < 0.02

    seq = iter(["help", "q"])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(seq))

    from core import state_io as sio
    monkeypatch.setattr(sio, "save_state", lambda *a, **k: None)

    s1 = app.read_user_input()
    assert s1 == ""  # help 처리 후 빈 문자열
    s2 = app.read_user_input()
    assert s2 == "q"
