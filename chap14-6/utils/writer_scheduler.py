# utils/writer_scheduler.py
from __future__ import annotations
from typing import Any, MutableMapping, List, Optional, Sequence, Iterable, cast, Union
from core.state_types import State
import os

import logging
logger = logging.getLogger(__name__)

from core.config import DOC_MODE, WRITER_AGENT
from core.paths import current_path
from core.models import Task
from utils.tasks import has_pending, get_last_write_target
from utils.outline import next_unwritten_title

import warnings, inspect
# 내부 호출 경로(utils.tasks) 외 직접 사용 시 한 번만 경고
_DEP_WARNED = False

def _maybe_warn_deprecated():
    """utils.tasks 경유가 아닌 '직접' 호출에만 1회 DeprecationWarning."""
    global _DEP_WARNED
    if _DEP_WARNED:
        return
    st = inspect.stack()
    # [0]=this func, [1]=schedule_writer_if_needed, [2]=외부 호출자
    caller_mod = st[2].frame.f_globals.get("__name__", "") if len(st) > 2 else ""
    if caller_mod != "utils.tasks":
        warnings.warn(
            "Import schedule_writer_if_needed from utils.tasks instead of utils.writer_scheduler",
            DeprecationWarning,
            stacklevel=3,  # 외부 호출 지점을 가리키도록
        )
    _DEP_WARNED = True

# def _maybe_warn_deprecated():
#     # 호출자 모듈이 utils.tasks가 아니면(=직접 사용) 경고
#     frm = inspect.stack()[1]
#     caller_mod = frm.frame.f_globals.get("__name__", "")
#     if caller_mod != "utils.tasks":
#         warnings.warn(
#             "Import schedule_writer_if_needed from utils.tasks instead of utils.writer_scheduler",
#             DeprecationWarning,
#             stacklevel=2,
#         )

def _env_truthy(name: str, default: bool = False) -> bool:
     v = os.getenv(name)
     if v is None:
         return default
     return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def schedule_writer_if_needed(
    state: MutableMapping[str, Any],
    *,
    tasks: Optional[List[Task]] = None,
    messages: Optional[List[Any]] = None,
    outline_text: str = "",
    # 💡 [핵심 수정] 이 인수가 누락되었을 가능성이 가장 높습니다. 추가해야 합니다.
    requested_title: Optional[str] = None,
    allow_during_research: Optional[bool] = None,
    debug: bool = False,
) -> bool:
    """WRITER_AGENT 태스크를 중복 없이 1건 예약."""
    _maybe_warn_deprecated()  # utils.tasks 경유면 경고 없음

    # 1) 리스트 보장
    if tasks is None:
        state_tasks = state.setdefault("task_history", [])
        task_list: List[Task] = cast(List[Task], state_tasks if isinstance(state_tasks, list) else [])
        if not isinstance(state_tasks, list):
            logger.debug("schedule_writer_if_needed: task_history is not list; replacing with empty list")
            state["task_history"] = task_list
    else:
        task_list = tasks

    if messages is None:
        state_msgs = state.setdefault("messages", [])
        msg_list: List[Any] = cast(List[Any], state_msgs if isinstance(state_msgs, list) else [])
        if not isinstance(state_msgs, list):
            logger.debug("schedule_writer_if_needed: messages is not list; replacing with empty list")
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

    # requested_title = get_last_write_target(msgs_seq, tasks_seq)
    auto_title = next_unwritten_title(
        outline_text or "", mode=DOC_MODE, root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    target_title = requested_title 
    if not target_title:
        target_title = auto_title
    if not target_title:
        target_title = fallback_default # 최종 폴백
    # target_title = (requested_title or auto_title or fallback_default) or fallback_default

    # -------------------------------------------------------------------------
    # 참고: get_last_write_target이 추출하는 제목이 섹션 번호가 포함된 전체 제목이어야 합니다.
    #      (ex: "7. 예상 리스크 및 완화 방안")
    # -------------------------------------------------------------------------

    # 3) 연구 루프 감지 (명시 플래그 우선 → 없으면 유도 판정)
    explicit_flag = state.get("research_loop_active")

    # (항상 바인딩) 허용/자동 여부 플래그는 블록 밖에서 결정
    if allow_during_research is None:
        allow_during_research = _env_truthy("AUTO_WRITE_DURING_RESEARCH", default=False)
    auto_write = _env_truthy("AUTO_WRITE_AFTER_RAG", default=True)

    # 기본 유도 판정
    if isinstance(explicit_flag, bool):
        research_loop_active = explicit_flag
    else:
        role = (state.get("agent_role") or "").strip().lower()
        rounds_done = int(state.get("research_round") or 0)
        max_iter = int(state.get("iteration_count") or 0)
        research_loop_active = (
            role == "research analyst"
            and bool(state.get("research_objectives"))
            and (max_iter > 0)
            and (rounds_done < max_iter)
        )

    # 연구 플로우 에이전트가 펜딩이면 연구중으로 강제 승격
    def _has(agent: str, prefix: str | None = None) -> bool:
        try:
            return has_pending(tasks_iter_for_check, agent, prefix=prefix)
        except Exception:
            return any((not getattr(t, "done", False)) and getattr(t, "agent", "") == agent for t in task_list)

    if not research_loop_active:
        if any(_has(a) for a in ("research_planner", "web_search_agent", "vector_search_agent", "research_synthesizer")):
            research_loop_active = True

    if debug:
        logger.debug("[writer_scheduler] %s", {
            "DOC_MODE": DOC_MODE,
            "WRITER_AGENT": writer_agent,
            "AUTO_WRITE_AFTER_RAG": os.getenv("AUTO_WRITE_AFTER_RAG"),
            "AUTO_WRITE_DURING_RESEARCH": os.getenv("AUTO_WRITE_DURING_RESEARCH"),
            "allow_during_research": allow_during_research,
            "research_loop_active": research_loop_active,
            "has_writer_pending": has_pending(tasks_iter_for_check, writer_agent, prefix="write:"),
            "target_title": target_title,
        })


    # 4) 연구 루프 중 자동 예약 금지면 종료
    if research_loop_active and not allow_during_research:
        if debug:
            logger.debug("[writer_scheduler] blocked: research_loop_active=True & allow_during_research=False")
        return False

    # 5) 예약 (중복 방지)
    if auto_write and not has_pending(tasks_iter_for_check, writer_agent, prefix="write:"):
        task_list.append(Task(agent=writer_agent, done=False, description=f"write: {target_title}", done_at=""))
        logger.info("writer task scheduled: agent=%s title=%s", writer_agent, target_title)
        return True

    return False
