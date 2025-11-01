# utils/writer_scheduler.py — dynamic config access (v2025-10-27)
from __future__ import annotations
from typing import Any, MutableMapping, List, Optional, Sequence, Iterable, Literal, TypeAlias, Dict
from core.paths import now_str as _now_str
from core.state_types import State  # noqa: F401 (type reference only)
import os

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config access (CFG → module attr → ENV → default)
# ─────────────────────────────────────────────────────────────
import core.config as config

def _get_cfg_attr(name: str, default):
    """config.CFG.<name> → config.<name> → ENV[name] → default."""
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    env = os.getenv(name)
    return env if env is not None else default


def _cfg_truthy(attr: str, default: bool) -> bool:
    v = _get_cfg_attr(attr, default)
    try:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}
    except Exception:
        return default


def _cfg_str(attr: str, default: str) -> str:
    v = _get_cfg_attr(attr, default)
    try:
        return str(v).strip() if v is not None else default
    except Exception:
        return default

# ─────────────────────────────────────────────────────────────
from core.paths import current_path, outline_base_dir
from core.models import Task

from utils.tasks import has_pending, get_last_write_target
from utils.outline import next_unwritten_title

import warnings, inspect
_DEP_WARNED = False

# ────────────────────────────────────────────────────────────────────────────
# 1) 이 파일에서 쓸 타입은 로컬 TypeAlias 로 “고정”합니다.
#    (외부 모듈에서 가져오지 말고, cast() 도 쓰지 않습니다.)
# ────────────────────────────────────────────────────────────────────────────
DocMode: TypeAlias = Literal["report", "book"]
AgentName: TypeAlias = Literal[
    "content_strategist",
    "communicator",
    "web_search_agent",
    "vector_search_agent",
    "chapter_writer",
    "section_writer",
    "research_planner",
    "research_synthesizer",
]

def _maybe_warn_deprecated():
    """utils.tasks 경유가 아닌 '직접' 호출에만 1회 DeprecationWarning."""
    global _DEP_WARNED
    if _DEP_WARNED:
        return
    st = inspect.stack()
    caller_mod = st[2].frame.f_globals.get("__name__", "") if len(st) > 2 else ""
    if caller_mod != "utils.tasks":
        warnings.warn(
            "Import schedule_writer_if_needed from utils.tasks instead of utils.writer_scheduler",
            DeprecationWarning,
            stacklevel=3,
        )
    _DEP_WARNED = True


# ────────────────────────────────────────────────────────────────────────────
# 2) 타입-안전 헬퍼: 리턴 타입을 리터럴로 “직접” 돌려줍니다 (cast 금지)
# ────────────────────────────────────────────────────────────────────────────

def _as_doc_mode(val: Any) -> DocMode:
    s = str(val or "").strip().lower()
    return "report" if s == "report" else "book"


def _as_agent_name(val: Any) -> AgentName:
    s = str(val or "").strip().lower()
    if s in {
        "content_strategist","communicator","web_search_agent","vector_search_agent",
        "chapter_writer","section_writer","research_planner","research_synthesizer",
    }:
        return s  # type: ignore[return-value]
    return "section_writer"

# 제목이 명시되지 않으면 writer 예약을 금지(기본 True: 안전 모드)
_REQUIRE_EXPLICIT = _cfg_truthy("REQUIRE_EXPLICIT_WRITE_TITLE", True)


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
    _maybe_warn_deprecated()

    # 1) 리스트 보장
    if tasks is None:
        state_tasks = state.setdefault("task_history", [])
        task_list: List[Task] = state_tasks if isinstance(state_tasks, list) else []
        if not isinstance(state_tasks, list):
            logger.debug("schedule_writer_if_needed: task_history is not list; replacing with empty list")
            state["task_history"] = task_list
    else:
        task_list = tasks

    if messages is None:
        state_msgs = state.setdefault("messages", [])
        msg_list: List[Any] = state_msgs if isinstance(state_msgs, list) else []
        if not isinstance(state_msgs, list):
            logger.debug("schedule_writer_if_needed: messages is not list; replacing with empty list")
            state["messages"] = msg_list
    else:
        msg_list = messages

    # 2) 시그니처에 맞게 Sequence로 고정
    msgs_seq: Sequence[Any] = tuple(msg_list)
    tasks_seq: Sequence[Any] = tuple(task_list)
    tasks_iter_for_check: Iterable[Any] = tasks_seq

    # ── 설정 값 읽고 “로컬 리터럴 타입”으로 정규화
    doc_mode: DocMode = _as_doc_mode(_cfg_str("DOC_MODE", "report"))
    writer_agent: AgentName = _as_agent_name(_cfg_str("WRITER_AGENT", "section_writer"))
    fallback_default = "Executive Summary" if doc_mode == "report" else "서문"

    # 2. 타이틀 정제 (+ flags 폴백)
    flags = (state.get("flags") or {})
    flag_req = (flags.get("requested_write_title") or "").strip() or None

    # 1순위: 인자 requested_title → 2순위: flags.requested_write_title
    req_param = (requested_title or "").strip() or None
    req = req_param or flag_req

    # 2-a. 안전 가드
    if _REQUIRE_EXPLICIT and not req:
        if debug:
            logger.debug(
                "[writer_scheduler] blocked: REQUIRE_EXPLICIT_WRITE_TITLE=True & requested_title is empty "
                "| param=%r | flags.requested_write_title=%r",
                requested_title, flag_req
            )
        return False

    # 자동 후보
    auto_title = None
    if not req:
        auto_title = next_unwritten_title(
            outline_text or "",
            mode=doc_mode,
            root_dir=str(outline_base_dir()),
            topic_slug=state.get("topic_slug"),
        )
        auto_title = (auto_title or "").strip() or None

    # 4. 최종 타이틀 결론
    target_title = req or auto_title or None
    if not target_title:
        if debug:
            logger.debug("[writer_scheduler] blocked: no requested/auto title → avoid fallback default")
        return False

    logger.debug(
        "[WriterScheduler Debug] ParamReq=%r | FlagReq=%r | AutoTitle=%r | FinalTarget=%r",
        req_param, flag_req, auto_title, target_title
    )

    # 3) 연구 루프 감지
    explicit_flag = state.get("research_loop_active")

    if allow_during_research is None:
        allow_during_research = _cfg_truthy("AUTO_WRITE_DURING_RESEARCH", False)
    auto_write = _cfg_truthy("AUTO_WRITE_AFTER_RAG", True)

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

    # 연구 플로우 에이전트 펜딩 시 연구중으로 간주
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
            "DOC_MODE": doc_mode,
            "WRITER_AGENT": writer_agent,
            "AUTO_WRITE_AFTER_RAG": _cfg_str("AUTO_WRITE_AFTER_RAG", ""),
            "AUTO_WRITE_DURING_RESEARCH": _cfg_str("AUTO_WRITE_DURING_RESEARCH", ""),
            "allow_during_research": allow_during_research,
            "research_loop_active": research_loop_active,
            "has_writer_pending": has_pending(tasks_iter_for_check, str(writer_agent), prefix="write:"),
            "target_title": target_title,
        })

    # 4) 연구 루프 중 자동 예약 금지면 종료
    if research_loop_active and not allow_during_research:
        if debug:
            logger.debug("[writer_scheduler] blocked: research_loop_active=True & allow_during_research=False")
        return False

    # 예약 중복 확인
    has_writer_pending = has_pending(tasks_iter_for_check, str(writer_agent), prefix="write:")
    is_explicit_request = bool(req)

    if has_writer_pending and is_explicit_request:
        now = _now_str()
        for t in task_list:
            if (not getattr(t, "done", False)) and str(getattr(t, "agent", "")) == writer_agent and (getattr(t, "description", "") or "").startswith("write:"):
                t.done, t.done_at = True, now
                t.description = (t.description or "") + " [auto-closed: new explicit request]"
                logger.info("Auto-closed old writer task due to new explicit request: %s", t.description)
        has_writer_pending = False

    if auto_write and not has_writer_pending:
        task_list.append(Task(agent=writer_agent, done=False, description=f"write: {target_title}", done_at=""))
        logger.info("writer task scheduled: agent=%s title=%s", writer_agent, target_title)
        if debug:
            logger.debug("[writer_scheduler] scheduled → %s ('write: %s')", writer_agent, target_title)
        return True

    return False
