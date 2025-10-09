# tests/test_writer_dedup.py
import os
from dataclasses import dataclass
from typing import Any, Iterable, Optional, cast

from utils.writer_scheduler import schedule_writer_if_needed
from core.models import Task
from utils.tasks import has_pending

@dataclass
class _TaskLikeShim:
    agent: str
    done: bool
    description: Optional[str]

def _as_tasklikes(tasks: Iterable[Task]) -> list[_TaskLikeShim]:
    def _desc(d: Any) -> Optional[str]:
        if d is None:
            return None
        return d if isinstance(d, str) else str(d)
    return [
        _TaskLikeShim(agent=str(t.agent), done=bool(t.done), description=_desc(t.description))
        for t in tasks
    ]

def test_writer_not_scheduled_twice(monkeypatch):
    monkeypatch.setenv("AUTO_WRITE_AFTER_RAG", "1")

    state: dict[str, Any] = {"topic_slug": "default"}
    tasks: list[Task] = []
    messages: list[Any] = []
    outline_text = "# Executive Summary\n\n## Background & Objectives"

    # 첫 호출 → 하나 예약
    did1 = schedule_writer_if_needed(state, tasks=tasks, messages=messages, outline_text=outline_text, debug=False)
    assert did1 is True

    writer = os.getenv("WRITER_AGENT", "section_writer")
    assert has_pending(_as_tasklikes(tasks), writer, prefix="write")

    # 두 번째 호출 → 이미 pending 있으므로 예약 안 됨
    did2 = schedule_writer_if_needed(state, tasks=tasks, messages=messages, outline_text=outline_text, debug=False)
    assert did2 is False

    # 최종적으로 pending writer는 최대 1개
    pending = [t for t in tasks if (not t.done) and t.agent == writer]
    assert len(pending) <= 1
