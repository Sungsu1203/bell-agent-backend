# tests/test_writer_schedule_equivalence.py
from __future__ import annotations
import importlib

def test_schedule_equivalence():
    ts  = importlib.import_module("utils.tasks")
    wsc = importlib.import_module("utils.writer_scheduler")

    state = {"messages": [], "task_history": [], "research_loop_active": False, "topic_slug": "eq"}
    outline = "# T\n\n## 서론\n## 본론\n"

    # A) 공식 엔트리포인트
    ok_a = ts.schedule_writer_if_needed(state, state["task_history"], outline_text=outline)

    # 상태 초기화 후 B) 내부 구현 직접 호출(동일 인자)
    state2 = {"messages": [], "task_history": [], "research_loop_active": False, "topic_slug": "eq"}
    ok_b = wsc.schedule_writer_if_needed(state2, tasks=state2["task_history"], outline_text=outline)

    assert bool(ok_a) == bool(ok_b)
    # 중복 방지/형태 일치
    def _shape(st):
        return [(getattr(t, "agent", ""), getattr(t, "done", True), str(getattr(t, "description", ""))) for t in st["task_history"]]
    assert _shape(state) == _shape(state2)
