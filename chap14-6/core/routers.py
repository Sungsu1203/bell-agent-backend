from __future__ import annotations
from core.config import DOC_MODE, WRITER_AGENT
from core.state_types import State
from utils.sanitize import as_int
from content_utils import read_outline, next_unwritten_title
from utils.outline import get_topic_outline_text
import os

def tail_task_router(state: State):
    outline_text = get_topic_outline_text(state)
    outline_missing = not (outline_text or "").strip()
    outline_not_shown = state.get("outline_shown") is False

    if outline_missing:
        return "content_strategist"
    if outline_not_shown:
        return "communicator"

    tasks = state.get("task_history", [])

    # ✅ 1) 우선 writer 태스크가 미완료면 그걸 선택 (보고서/책 모드에 따라)
    preferred_writer = "section_writer" if DOC_MODE == "report" else "chapter_writer"
    for t in reversed(tasks):
        if (not t.done) and t.agent == preferred_writer:
            return preferred_writer

    # ✅ 2) writer(상대 모드)가 걸려 있다면 그것도 우선
    alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
    for t in reversed(tasks):
        if (not t.done) and t.agent == alt_writer:
            return alt_writer

    # ③ 마지막으로 communicator
    for t in reversed(tasks):
        if (not t.done) and t.agent == "communicator":
            return "communicator"

    # ④ 아무 것도 없으면 기본 writer
    return preferred_writer

def after_vector_router(state: State):
    # 직답 플래그가 있으면 바로 커뮤니케이터
    if state.get("qa_direct_reply"):
        return "communicator"

    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = int(state.get("research_round") or 0)
    max_iter = as_int(state, "iteration_count", 0)
    has_objs = bool(state.get("research_objectives"))

    if role == "research analyst" and has_objs and rounds_done < max_iter:
        return "research_synthesizer"
    return tail_task_router(state)


def after_planner_router(state: State):
    announce = os.getenv("RESEARCH_PLANNER_ANNOUNCE", "0") == "1" or as_int(state, "research_planner_announce", 0) == 1
    return "communicator" if announce else "web_search_agent"


def after_synthesizer_router(state: State):
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)

    if os.getenv("DEBUG_ROUTER_KEYS") == "1":
        keys_preview = list(state.keys())[:40]
        print(f"[ROUTER] keys[:40]={keys_preview}")

    def first_int(state, keys, default=0):
        for k in keys:
            if k in state:
                return as_int(state, k, default)
        return default

    url_new_actual = first_int(
        state,
        ["round_added_urls", "new_url_count", "new_url_count_round", "new_urls", "round_new_urls"],
        default=0,
    )

    def _pick(env_key, state_key, default):
        v = os.getenv(env_key)
        if v is not None and str(v).strip() != "":
            try:
                return int(v)
            except Exception:
                pass
        return as_int(state, state_key, default)

