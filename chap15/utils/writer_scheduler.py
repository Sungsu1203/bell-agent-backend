# utils/writer_scheduler.py
from __future__ import annotations
from typing import Any, MutableMapping, List, Optional, Sequence, Iterable, cast, Union, get_args
from typing import cast as _cast
from core.config import DocMode

from core.state_types import State
import os
import logging
logger = logging.getLogger(__name__)

from core.paths import current_path
from core.models import Task
from utils.tasks import has_pending
from utils.outline import next_unwritten_title

import warnings, inspect

# 내부 호출 경로(utils.tasks) 외 직접 사용 시 한 번만 경고
_DEP_WARNED = False

# ── 단일 writer 노드 정규화 상수 ─────────────────────────────
WRITER_AGENT = "writer"
WRITER_ALIASES = ("writer", "section_writer", "chapter_writer")

def _env_doc_mode(default: str = "report") -> str:
    return (os.getenv("DOC_MODE") or default).strip().lower()

def _has_any_writer_pending(tasks_iter, prefix: str | None = None) -> bool:
    """히스토리에 남아있는 과거 writer 라벨까지 포함해 펜딩 여부 확인."""
    try:
        return any(has_pending(tasks_iter, alias, prefix=prefix) for alias in WRITER_ALIASES)
    except Exception:
        # tasks_iter가 일반 리스트인 경우의 보수 처리
        for t in tasks_iter:
            if (not getattr(t, "done", False)) and getattr(t, "agent", "") in WRITER_ALIASES:
                if prefix is None:
                    return True
                if (getattr(t, "description", "") or "").startswith(prefix):
                    return True
        return False

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
            stacklevel=3,
        )
    _DEP_WARNED = True

def _env_truthy(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}

# 제목이 명시되지 않으면 writer 예약을 금지(기본 True: 안전 모드)
_REQUIRE_EXPLICIT = _env_truthy("REQUIRE_EXPLICIT_WRITE_TITLE", default=True)

def schedule_writer_if_needed(
    state: MutableMapping[str, Any],
    *,
    tasks: Optional[List[Task]] = None,
    messages: Optional[List[Any]] = None,
    outline_text: str = "",
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

    # 2) 시그니처에 맞게 Sequence/Iterable로 고정
    tasks_seq: Sequence[Any] = tuple(task_list)
    tasks_iter_for_check: Iterable[Any] = cast(Iterable[Any], tasks_seq)

    # 모드 결정 (ENV → DocMode 캐스팅)
    _mode_str = _env_doc_mode(default="report")
    _mode: DocMode = _cast(DocMode, _mode_str if _mode_str in get_args(DocMode) else "report")

    # 예약에 사용할 실제 writer 라벨(AgentName): 타입 안전
    scheduled_writer_agent: str = "section_writer" if _mode == "report" else "chapter_writer"
    # 참고용(로그/호환): 통합 별칭
    writer_agent: str = WRITER_AGENT

    fallback_default = "Executive Summary" if _mode == "report" else "서문"

    # 2. 타이틀 정제 (+ flags 폴백)
    flags = (state.get("flags") or {})
    flag_req = (flags.get("requested_write_title") or "").strip() or None

    # 1순위: 인자 requested_title → 2순위: flags.requested_write_title
    req_param = (requested_title or "").strip() or None
    req = req_param or flag_req

    # 2-a. 안전 가드: 명시적 제목이 필요한 설정이라면, 제목 없을 때 예약 금지
    if _REQUIRE_EXPLICIT and not req:
        if debug:
            logger.debug(
                "[writer_scheduler] blocked: REQUIRE_EXPLICIT_WRITE_TITLE=True & requested_title is empty "
                "| param=%r | flags.requested_write_title=%r",
                requested_title, flag_req
            )
        return False

    # 3. 자동 후보 계산 (req가 없을 때만 활용)
    auto_title = None
    if not req:
        auto_title = next_unwritten_title(
            outline_text or "",
            mode=_mode,  # DocMode로 캐스팅된 값 사용
            root_dir=current_path,
            topic_slug=state.get("topic_slug"),
        )
        auto_title = (auto_title or "").strip() or None

    # 4. 최종 타이틀 결론
    target_title = req or auto_title or None
    if not target_title:
        if debug:
            logger.debug("[writer_scheduler] blocked: no requested/auto title → avoid fallback default")
        return False
    # 필요 시 폴백 사용:
    # target_title = req or auto_title or fallback_default

    logger.debug(
        "[WriterScheduler Debug] ParamReq=%r | FlagReq=%r | AutoTitle=%r | FinalTarget=%r",
        req_param, flag_req, auto_title, target_title
    )

    # 3) 연구 루프 감지 (명시 플래그 우선 → 없으면 유도 판정)
    explicit_flag = state.get("research_loop_active")

    # 허용/자동 여부 플래그
    if allow_during_research is None:
        allow_during_research = _env_truthy("AUTO_WRITE_DURING_RESEARCH", default=False)
    auto_write = _env_truthy("AUTO_WRITE_AFTER_RAG", default=True)

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

    # 연구 플로우 에이전트 펜딩이면 연구중으로 승격
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
            "DOC_MODE(env)": _mode,
            "WRITER_AGENT(unified)": writer_agent,
            "WRITER_AGENT(scheduled)": scheduled_writer_agent,
            "AUTO_WRITE_AFTER_RAG": os.getenv("AUTO_WRITE_AFTER_RAG"),
            "AUTO_WRITE_DURING_RESEARCH": os.getenv("AUTO_WRITE_DURING_RESEARCH"),
            "allow_during_research": allow_during_research,
            "research_loop_active": research_loop_active,
            "has_writer_pending(any)": _has_any_writer_pending(tasks_iter_for_check, prefix="write:"),
            "target_title": target_title,
        })

    # 4) 연구 루프 중 자동 예약 금지면 종료
    if research_loop_active and not allow_during_research:
        if debug:
            logger.debug("[writer_scheduler] blocked: research_loop_active=True & allow_during_research=False")
        return False

    # 5) 예약 (중복 방지) — 과거 라벨도 중복으로 간주
    if auto_write and not _has_any_writer_pending(tasks_iter_for_check, prefix="write:"):
        # 타입 안전한 라벨로 예약 (AgentName)
        task_list.append(Task(agent=scheduled_writer_agent, done=False, description=f"write: {target_title}", done_at=""))
        logger.info("writer task scheduled: agent=%s title=%s", scheduled_writer_agent, target_title)
        if debug:
            logger.debug("[writer_scheduler] scheduled → %s ('write: %s')", scheduled_writer_agent, target_title)
        return True

    return False
