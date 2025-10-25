from __future__ import annotations
import os, importlib, time
import pytest

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("AUTO_WRITE_AFTER_RAG", "1")
    monkeypatch.setenv("AUTO_WRITE_DURING_RESEARCH", "0")
    yield

def _imp_tasks():
    return importlib.import_module("utils.tasks")

def _fake_state():
    return {
        "messages": [],
        "task_history": [],
        "references": {"queries": [], "docs": []},
        "research_round": 2,
        "research_loop_active": True,
        "new_url_count": 0,
        "outline_shown": True,
        "topic_slug": "testtopic",
    }

def test_research_loop_auto_halt_to_writer(monkeypatch):
    ut = _imp_tasks()
    schedule = getattr(ut, "schedule_writer_if_needed", None)
    assert callable(schedule), "utils.tasks.schedule_writer_if_needed 필요"

    state = _fake_state()
    tasks = []
    outline_text = "# Title\n\n## 서론\n## 본론\n## 결론\n"

    # 연구 루프 종료 상태로 설정
    state["research_loop_active"] = False

    t0 = time.monotonic()
    schedule(state, tasks, outline_text=outline_text, mode=os.getenv("DOC_MODE", "report"))
    t1 = time.monotonic()

    assert any(getattr(t, "agent", "").startswith(("writer", "section_writer", "chapter_writer"))
               and not getattr(t, "done", True) for t in tasks)

    # ▶ Perf: 스케줄러는 매우 빠르게 끝나야 함(50ms 이내)
    assert (t1 - t0) < 0.05

