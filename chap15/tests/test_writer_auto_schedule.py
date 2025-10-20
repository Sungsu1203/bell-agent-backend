from __future__ import annotations
import os, importlib, time
import pytest

def _imp_tasks():
    return importlib.import_module("utils.tasks")

def _mk_state():
    return {"messages": [], "task_history": [], "outline_shown": True, "topic_slug": "testtopic"}

def _has_pending(tasks, name_prefix):
    return any(getattr(t, "agent", "").startswith(name_prefix) and not getattr(t, "done", True) for t in tasks)

@pytest.mark.parametrize("after,during,expect_writer", [
    ("1", "0", True),
    ("1", "1", True),
    ("0", "1", False),
    ("0", "0", False),
])
def test_auto_schedule_matrix(monkeypatch, after, during, expect_writer):
    ut = _imp_tasks()
    schedule = getattr(ut, "schedule_writer_if_needed", None)
    assert callable(schedule)

    monkeypatch.setenv("AUTO_WRITE_AFTER_RAG", after)
    monkeypatch.setenv("AUTO_WRITE_DURING_RESEARCH", during)

    state, tasks = _mk_state(), []
    state["research_loop_active"] = False
    outline_text = "# Title\n\n## 서론\n## 본론\n## 결론\n"

    ws = importlib.import_module("utils.writer_scheduler")
    monkeypatch.setattr(ws, "next_unwritten_title", lambda *a, **k: "서론")
    monkeypatch.setattr(ws, "_DEP_WARNED", True, raising=False)  # ★ 추가

    t0 = time.monotonic()
    schedule(state, tasks, outline_text=outline_text, mode=os.getenv("DOC_MODE", "report"))
    dt = time.monotonic() - t0

    got = (_has_pending(tasks, "section_writer") or _has_pending(tasks, "chapter_writer") or _has_pending(tasks, "writer"))
    assert got == expect_writer

    # ▶ Perf: 조합 전체에서도 빠르게 결정(30ms 이내)
    assert dt < 0.03
