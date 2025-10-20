from __future__ import annotations
import importlib, json, time
import pytest

def _imp():
    return importlib.import_module("tools.web_rag")

def test_flex_load_variants(tmp_path, monkeypatch):
    wr = _imp()
    monkeypatch.setenv("GATE_KEEP_SOURCES", "0")

    base = {"title":"a","url":"https://github.com/a","content":"x","raw_content":"x","source":"https://github.com/a"}

    p1 = tmp_path / "list.json"; p1.write_text(json.dumps([base]), encoding="utf-8")
    p2 = tmp_path / "obj.json";  p2.write_text(json.dumps({"results":[base]}), encoding="utf-8")
    p3 = tmp_path / "nd.json";   p3.write_text("\n".join(json.dumps(x) for x in [base]), encoding="utf-8")

    t0 = time.monotonic(); docs1 = wr.web_page_json_to_documents(str(p1)); t1 = time.monotonic()
    docs2 = wr.web_page_json_to_documents(str(p2))
    docs3 = wr.web_page_json_to_documents(str(p3))

    assert isinstance(docs1, list) and len(docs1) == 1
    assert isinstance(docs2, list) and len(docs2) == 1
    assert isinstance(docs3, list) and len(docs3) == 1

    # ▶ Perf: 로더는 매우 빠르게(20ms 이내)
    assert (t1 - t0) < 0.02
