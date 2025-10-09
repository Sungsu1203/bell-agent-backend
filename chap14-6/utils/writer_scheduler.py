# utils/writer_scheduler.py
from __future__ import annotations
from typing import Any, MutableMapping, List, Optional, Sequence, Iterable, cast, Union
from core.state_types import State
import os

from core.config import DOC_MODE, WRITER_AGENT
from core.paths import current_path
from core.models import Task
from utils.tasks import has_pending, get_last_write_target
from content_utils import next_unwritten_title


def schedule_writer_if_needed(
    state: MutableMapping[str, Any],
    *,
    tasks: Optional[List[Task]] = None,
    messages: Optional[List[Any]] = None,
    outline_text: str = "",
    allow_during_research: Optional[bool] = None,
    debug: bool = False,
) -> bool:
    """WRITER_AGENT 태스크를 중복 없이 1건 예약."""

    # 1) 리스트 보장
    if tasks is None:
        state_tasks = state.setdefault("task_history", [])
        task_list: List[Task] = cast(List[Task], state_tasks if isinstance(state_tasks, list) else [])
        if not isinstance(state_tasks, list):
            state["task_history"] = task_list
    else:
        task_list = tasks

    if messages is None:
        state_msgs = state.setdefault("messages", [])
        msg_list: List[Any] = cast(List[Any], state_msgs if isinstance(state_msgs, list) else [])
        if not isinstance(state_msgs, list):
            state["messages"] = msg_list
    else:
        msg_list = messages

    # 2) 시그니처에 맞게 Sequence로 고정
    msgs_seq: Sequence[Any] = tuple(msg_list)          # Sequence[Any]
    tasks_seq: Sequence[Any] = tuple(task_list)        # Sequence[Any]
    # has_pending 은 Iterable이면 충분하므로 캐스트로 전달
    tasks_iter_for_check: Iterable[Any] = cast(Iterable[Any], tasks_seq)

    writer_agent: str = WRITER_AGENT
    fallback_default = "Executive Summary" if DOC_MODE == "report" else "서문"

    requested_title = get_last_write_target(msgs_seq, tasks_seq)
    auto_title = next_unwritten_title(
        outline_text or "", mode=DOC_MODE, root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    target_title = requested_title or auto_title or fallback_default

    # 3) 연구 루프 감지
    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = int(state.get("research_round") or 0)
    max_iter = int(state.get("iteration_count") or 0)
    research_loop_active = (role == "research analyst") and bool(state.get("research_objectives")) and (rounds_done < max_iter)

    if allow_during_research is None:
        allow_during_research = os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1"

    auto_write = str(os.getenv("AUTO_WRITE_AFTER_RAG", "1")).strip().lower() in ("1", "true", "yes")

    if debug:
        print("[writer_scheduler]", {
            "DOC_MODE": DOC_MODE,
            "WRITER_AGENT": writer_agent,
            "AUTO_WRITE_AFTER_RAG": os.getenv("AUTO_WRITE_AFTER_RAG"),
            "AUTO_WRITE_DURING_RESEARCH": os.getenv("AUTO_WRITE_DURING_RESEARCH"),
            "research_loop_active": research_loop_active,
            "has_writer_pending": has_pending(tasks_iter_for_check, writer_agent, prefix="write"),
            "target_title": target_title,
        })

    # 4) 연구 루프 중 자동 예약 금지면 종료
    if research_loop_active and not allow_during_research:
        return False

    # 5) 예약 (중복 방지)
    if auto_write and not has_pending(tasks_iter_for_check, writer_agent, prefix="write"):
        task_list.append(Task(agent=writer_agent, done=False, description=f"write: {target_title}", done_at=""))
        return True

    return False
