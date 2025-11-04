# utils/writer_scheduler.py — dynamic config access (v2025-10-27)
from __future__ import annotations
from typing import Any, MutableMapping, List, Optional, Sequence, Iterable, Literal, TypeAlias, Dict, Set
from core.paths import now_str as _now_str
from core.state_types import State  # noqa: F401 (type reference only)
import os
import re

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config access (CFG 단일 진입점)
# ─────────────────────────────────────────────────────────────
import core.config as config
from core.config import reload_config as reload_config  # in-place 갱신만 허용

def _cfg_bool(attr: str, default: bool) -> bool:
    """CFG 우선 읽기(ENV 비접근)."""
    try:
        return bool(getattr(config.CFG, attr))
    except Exception:
        return default

def _cfg_str(attr: str, default: str) -> str:
    """CFG 우선 읽기(ENV 비접근)."""
    try:
        v = getattr(config.CFG, attr)
        return (str(v).strip() if v is not None else default)
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
_REQUIRE_EXPLICIT = _cfg_bool("REQUIRE_EXPLICIT_WRITE_TITLE", True)

# ────────────────────────────────────────────────────────────
# 진행률 보조 유틸 (섹션 총량/SEEN 집계)
# ────────────────────────────────────────────────────────────
def _count_sections_in_outline(outline_text: str, *, mode: Literal["report", "book"]) -> int:
    """
    간단 카운트 규칙:
      - report: '## ' 로 시작하는 H2 섹션 수
      - book  : '## ' 로 시작하는 장/절(기본 동일 규칙, 필요 시 강화 가능)
    """
    if not outline_text:
        return 0
    # 코드/펜스 블록 등은 단순 무시(정규식 한 번으로 충분)
    lines = outline_text.splitlines()
    pat = re.compile(r'^\s*##\s+')
    return sum(1 for ln in lines if pat.match(ln))

def _ensure_progress_flags(state: MutableMapping[str, Any], *, outline_text: str, doc_mode: Literal["report","book"]) -> None:
    """sections_total/sections_done/sections_seen/sections_seen_titles 초기화."""
    flags: Dict[str, Any] = dict(state.get("flags") or {})
    # total: 한 번만 세팅(0 또는 미지정일 때)
    total = int(flags.get("sections_total") or 0)
    if total <= 0:
        total = _count_sections_in_outline(outline_text or "", mode=doc_mode)
        flags["sections_total"] = int(total or 0)
    # done/seen 기본값 보정
    if "sections_done" not in flags:
        flags["sections_done"] = 0
    if "sections_seen" not in flags:
        flags["sections_seen"] = 0
    if "sections_seen_titles" not in flags or not isinstance(flags.get("sections_seen_titles"), list):
        flags["sections_seen_titles"] = []
    state["flags"] = flags  # commit

def _mark_title_seen(state: MutableMapping[str, Any], title: str) -> None:
    """중복 없이 SEEN 집계 업데이트."""
    flags: Dict[str, Any] = dict(state.get("flags") or {})
    seen_list = flags.get("sections_seen_titles")
    if not isinstance(seen_list, list):
        seen_list = []
    title_norm = (title or "").strip().lower()
    if title_norm and all(str(t).strip().lower() != title_norm for t in seen_list):
        seen_list.append(title)
        flags["sections_seen_titles"] = seen_list
        try:
            flags["sections_seen"] = int(flags.get("sections_seen") or 0) + 1
        except Exception:
            flags["sections_seen"] = len(seen_list)
    state["flags"] = flags  # commit


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

    # [PATCH: 진행률 카운터 초기화] — 섹션 총량/seen/done 기본값 보정
    try:
        _ensure_progress_flags(state, outline_text=outline_text or "", doc_mode=doc_mode)
    except Exception as _e:
        if debug:
            logger.debug("[writer_scheduler] progress flags init skipped: %s", _e)

    # 3) 연구 루프 감지
    explicit_flag = state.get("research_loop_active")

    if allow_during_research is None:
        allow_during_research = _cfg_bool("AUTO_WRITE_DURING_RESEARCH", False)
    auto_write = _cfg_bool("AUTO_WRITE_AFTER_RAG", True)

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
            "AUTO_WRITE_AFTER_RAG": str(_cfg_bool("AUTO_WRITE_AFTER_RAG", True)),
            "AUTO_WRITE_DURING_RESEARCH": str(_cfg_bool("AUTO_WRITE_DURING_RESEARCH", False)),
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
        # [PATCH: 진행률 집계] — 새로 예약된 타이틀을 SEEN 누적에 반영(중복 보호)
        try:
            _mark_title_seen(state, target_title)
            if debug:
                logger.debug("[writer_scheduler] sections_seen incremented (title=%r)", target_title)
        except Exception as _e:
            if debug:
                logger.debug("[writer_scheduler] mark_title_seen skipped: %s", _e)
        if debug:
            logger.debug("[writer_scheduler] scheduled → %s ('write: %s')", writer_agent, target_title)
        return True

    return False
