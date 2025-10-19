from __future__ import annotations
import os
from typing import Optional

import logging
logger = logging.getLogger(__name__)

from core.config import DOC_MODE
from core.state_types import State
from utils.sanitize import as_int
from utils.outline import get_topic_outline_text

from utils.tasks import has_pending, schedule_writer_if_needed


def tail_task_router(state: State):
    """작성 단계(테일)에서 다음 노드를 선택."""
    outline_text = get_topic_outline_text(state)
    outline_missing = not (outline_text or "").strip()
    outline_not_shown = state.get("outline_shown") is False

    if outline_missing:
        logger.info("[router.tail] outline missing → content_strategist")
        return "content_strategist"
    if outline_not_shown:
        # [ADD] writer-락(pending_write_title) 우선 라우팅
        flags = state.get("flags") or {}
        if flags.get("pending_write_title"):
            tasks = state.get("task_history", []) or []
            preferred_writer = "section_writer" if DOC_MODE == "report" else "chapter_writer"
            alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
            if has_pending(tasks, preferred_writer, prefix="write:") or has_pending(tasks, alt_writer, prefix="write:"):
                logger.info("[router.tail] outline exists but not shown — writer lock → %s", preferred_writer)
                return preferred_writer
        logger.info("[router.tail] outline exists but not shown → communicator")
        return "communicator"

    tasks = state.get("task_history", []) or []

    # 1) 선호 writer가 미완료면 우선
    preferred_writer = "section_writer" if DOC_MODE == "report" else "chapter_writer"
    for t in reversed(tasks):
        if (not getattr(t, "done", False)) and getattr(t, "agent", "") == preferred_writer:
            logger.debug("[router.tail] preferred writer pending → %s", preferred_writer)
            return preferred_writer

    # 2) 대안 writer가 미완료면 그 다음
    alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
    for t in reversed(tasks):
        if (not getattr(t, "done", False)) and getattr(t, "agent", "") == alt_writer:
            logger.debug("[router.tail] alt writer pending → %s", alt_writer)
            return alt_writer

    # [ADD] writer-락 우선 (커뮤니케이터 펜딩보다 먼저)
    # refs 비어있으면 write: 펜딩이어도 먼저 RAG(Web)으로 보냄
    refs = state.get("references") or {}
    refs_empty = not (refs.get("docs") or [])

    if has_pending(tasks, preferred_writer, prefix="write:") or has_pending(tasks, alt_writer, prefix="write:"):
        if refs_empty:
            logger.debug("[router.tail] write: pending but refs empty → web_search_agent")
            return "web_search_agent"
        logger.debug("[router.tail] writer pending(write:) → %s", preferred_writer)
        return preferred_writer

    # 3) 커뮤니케이터가 미완료면
    for t in reversed(tasks):
        if (not getattr(t, "done", False)) and getattr(t, "agent", "") == "communicator":
            logger.debug("[router.tail] communicator pending → communicator")
            return "communicator"

    # 4) 아무 것도 없으면 기본 writer
    logger.info("[router.tail] no pending tasks → preferred writer %s", preferred_writer)
    return preferred_writer


def after_vector_router(state: State):
    """벡터검색 이후 라우팅."""
    # ✅ 이 스코프의 tasks 확보
    tasks = state.get("task_history", []) or []

    # 0) 연구 루프 활성 + synthesizer 펜딩이면 → 최우선
    if bool(state.get("research_loop_active")) and has_pending(tasks, "research_synthesizer"):
        logger.info("[router.after_vector] research_loop_active & synthesizer pending → research_synthesizer")
        return "research_synthesizer"

    # 1) (옵션) 집필 예약 — 연구 중 허용 플래그로 제어
    schedule_writer_if_needed(
        state,
        tasks=tasks,  # ← 확보한 tasks 사용
        messages=state.get("messages"),
        outline_text=get_topic_outline_text(state),
        allow_during_research=os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1",
    )

    # [ADD] refs 가드: refs 비어있으면 write: 펜딩이어도 우선 RAG(Web)로 라우팅
    preferred_writer = "section_writer" if DOC_MODE == "report" else "chapter_writer"
    alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
    has_write_pending = (
        has_pending(tasks, preferred_writer, prefix="write:") or
        has_pending(tasks, alt_writer, prefix="write:")
    )
    if has_write_pending:
        refs = state.get("references") or {}
        refs_empty = not (refs.get("docs") or [])
        if refs_empty:
            logger.info("[router.after_vector] write: pending but refs empty → web_search_agent")
            return "web_search_agent"
        logger.info("[router.after_vector] writer pending(write:) → %s", preferred_writer)
        return preferred_writer

    # 2) QA 직답 모드면 → 커뮤니케이터
    if state.get("qa_direct_reply"):
        logger.info("[router.after_vector] qa_direct_reply=True → communicator")
        return "communicator"

    # 3) 연구 루프 조건 충족 시 → synthesizer (펜딩이 없더라도 루프 계속)
    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = int(state.get("research_round") or 0)
    max_iter = as_int(state, "iteration_count", 0)
    has_objs = bool(state.get("research_objectives"))

    if (role == "research analyst") and has_objs and (rounds_done < max_iter):
        logger.info("[router.after_vector] research loop continues → research_synthesizer")
        return "research_synthesizer"

    # 4) 그 외 → tail router
    nxt = tail_task_router(state)
    logger.info("[router.after_vector] fallback → %s", nxt)
    return nxt


def after_planner_router(state: State):
    """
    플래너 이후 라우팅:
    1) announce=1 → communicator
    2) writer 펜딩이 있으면 writer 최우선
    3) 쿼리 없으면 communicator
    4) SKIP_WEB_SEARCH=1 또는 state.flags.skip_web_search → vector_search_agent
    5) 기본: web_search_agent
    """
    tasks = state.get("task_history", []) or []

    def _has_pending(agent: str) -> bool:
        return any((not getattr(t, "done", False)) and getattr(t, "agent", "") == agent for t in tasks)

    def _pending_writer() -> Optional[str]:
        preferred = "section_writer" if DOC_MODE == "report" else "chapter_writer"
        for t in reversed(tasks):
            if (not getattr(t, "done", False)) and getattr(t, "agent", "") == preferred:
                return preferred
        alt = "chapter_writer" if preferred == "section_writer" else "section_writer"
        for t in reversed(tasks):
            if (not getattr(t, "done", False)) and getattr(t, "agent", "") == alt:
                return alt
        return None

    # 0) 플래너 announce 옵션
    announce = os.getenv("RESEARCH_PLANNER_ANNOUNCE", "0") == "1" or as_int(state, "research_planner_announce", 0) == 1
    if announce:
        logger.info("[router.after_planner] announce=1 → communicator")
        return "communicator"

    # 1) writer 펜딩 최우선
    w = _pending_writer()
    if w:
        logger.info("[router.after_planner] writer pending → %s", w)
        return w

    # 2) 새 쿼리 유무
    plan_qs = ((state.get("research_plan") or {}).get("queries") or []) or state.get("planner_queries") or []
    have_queries = bool(plan_qs)
    if not have_queries:
        logger.info("[router.after_planner] no planner queries → communicator")
        return "communicator"

    # 3) 웹검색 스킵 → 벡터검색
    skip_web = (os.getenv("SKIP_WEB_SEARCH", "0") == "1") or bool((state.get("flags") or {}).get("skip_web_search"))
    if skip_web:
        logger.info("[router.after_planner] SKIP_WEB_SEARCH=1 → vector_search_agent")
        return "vector_search_agent"

    # 4) 기본 경로 = 웹검색
    logger.info("[router.after_planner] default → web_search_agent")
    return "web_search_agent"


def after_synthesizer_router(state: State):
    """
    합성기 이후 라우팅:
    - 연구 라운드를 더 돌지 결정(신규 URL 수, 최소/최대 라운드, 무신규 연속치 등)
    - 계속 연구면 research_planner, 아니면 tail_task_router(writer/communicator 등)
    """
    # ✅ 이 스코프의 tasks 확보
    tasks = state.get("task_history", []) or []

    schedule_writer_if_needed(
        state,
        tasks=tasks,  # ← 확보한 tasks 사용
        messages=state.get("messages"),
        outline_text=get_topic_outline_text(state),  # ← 안전한 outline 주입
        allow_during_research=os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1",
    )

    # [CHANGE] 플래그 유무와 상관없이 write: 펜딩이 있으면 writer 우선
    preferred_writer = "section_writer" if DOC_MODE == "report" else "chapter_writer"
    alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
    if has_pending(tasks, preferred_writer, prefix="write:") or has_pending(tasks, alt_writer, prefix="write:"):
        logger.info("[router.after_synth] writer pending(write:) → %s", preferred_writer)
        return preferred_writer

    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)

    if os.getenv("DEBUG_ROUTER_KEYS") == "1":
        keys_preview = list(state.keys())[:40]
        logger.debug("[router.after_synth] keys[:40]=%s", keys_preview)

    def first_int(st: State, keys: list[str], default: int = 0) -> int:
        for k in keys:
            if k in st:
                return as_int(st, k, default)
        return default

    # 이번 라운드의 "신규 URL" 수치(여러 키 중 먼저 찾음)
    url_new_actual = first_int(
        state,
        ["round_added_urls", "new_url_count", "new_url_count_round", "new_urls", "round_new_urls"],
        default=0,
    )

    def _pick(env_key: str, state_key: str, default: int) -> int:
        v = os.getenv(env_key)
        if v is not None and str(v).strip() != "":
            try:
                return int(v)
            except Exception:
                pass
        return as_int(state, state_key, default)

    halt_threshold = _pick("RESEARCH_HALT_THRESHOLD", "research_halt_threshold", 0)
    min_rounds     = _pick("RESEARCH_MIN_ROUNDS", "research_min_rounds", 0)
    max_no_new     = _pick("RESEARCH_MAX_NO_NEW_ROUNDS", "research_max_no_new_rounds", 1)
    no_new_streak  = as_int(state, "no_new_url_streak", 0)

    can_continue = (
        (rounds_done < max_iter)
        and ((rounds_done < min_rounds) or (url_new_actual > halt_threshold) or (no_new_streak < max_no_new))
    )

    logger.info(
        "[router.after_synth] round=%s/%s | new=%s | streak=%s (max_no_new=%s) | min=%s | threshold=%s | continue=%s",
        rounds_done, max_iter, url_new_actual, no_new_streak, max_no_new, min_rounds, halt_threshold, can_continue
    )

    if can_continue:
        logger.info("[router.after_synth] continue research → research_planner")
        return "research_planner"

    nxt = tail_task_router(state)
    logger.info("[router.after_synth] halt research → %s", nxt)
    return nxt
