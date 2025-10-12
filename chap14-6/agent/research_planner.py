from __future__ import annotations
from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage

import logging
logger = logging.getLogger(__name__)

from core.paths import now_str as _now_str
from core.state_types import State
from core.models import Task, AgentName
from utils.sanitize import sanitize_state, as_int
from prompts import get_research_planner_prompt
from utils.tasks import has_pending
from utils.refs import refs_preview_text as _refs_preview_text
from utils.query_filters import strip_web_filters as _strip_web_filters, looks_like_local_glob
from utils.forced_queries import extract_forced_queries_from_messages
from typing import Any, Dict, MutableMapping, overload, TYPE_CHECKING, Union, cast
import os, re

from core.llm import get_llm


def research_planner(state: State):
    logger.info("============ RESEARCH PLANNER ============")
    llm = get_llm()
    state = sanitize_state(state)

    # 연구 루프 시작 표식 (writer 자동 기동 가드와 연동)
    cast(MutableMapping[str, Any], state)["research_loop_active"] = True

    max_iter = int(state.get("iteration_count", 0))
    rnd = int(state.get("research_round", 0))

    # 목표 로딩: state 우선 → BLOCKAGI_OBJECTIVE_1..9 → BLOCKAGI_OBJECTIVES(JSON)
    def _load_objectives(st) -> list[str]:
        objs0 = [str(s).strip() for s in (st.get("research_objectives") or []) if str(s).strip()]
        if objs0:
            return list(dict.fromkeys(objs0))
        env_objs = []
        for i in range(1, 10):
            v = os.getenv(f"BLOCKAGI_OBJECTIVE_{i}", "")
            if isinstance(v, str) and v.strip():
                env_objs.append(v.strip())
        if not env_objs:
            raw = os.getenv("BLOCKAGI_OBJECTIVES", "")
            if isinstance(raw, str) and raw.strip():
                try:
                    import json
                    cand = json.loads(raw)
                    if isinstance(cand, list):
                        env_objs = [str(x).strip() for x in cand if str(x).strip()]
                except Exception:
                    pass
        return list(dict.fromkeys(env_objs))

    objs = _load_objectives(state)
    cast(MutableMapping[str, Any], state)["research_objectives"] = objs

    # 항상 리스트 보장
    tasks = state.get("task_history", []) or []
    messages = state.get("messages", []) or []

    # 최근 planner pending 탐지 (없으면 None)
    pending = next(
        (t for t in reversed(tasks) if (not getattr(t, "done", False)) and getattr(t, "agent", "") == "research_planner"),
        None,
    )

    # ======== 목표 없음: 루프 HOLD + communicator 안내 (writer 금지) ========
    if not objs:
        if pending:
            pending.done = True
            pending.done_at = _now_str()
            if not getattr(pending, "description", ""):
                pending.description = "plan: auto"
            pending.description += " [skipped: no research_objectives]"
        messages.append(AIMessage(
            content=(
                "[Research Planner] 연구 목표(research_objectives)가 비어 있어 플래닝을 일시 정지합니다. "
                "환경변수(BLOCKAGI_OBJECTIVE_1..n 또는 BLOCKAGI_OBJECTIVES)나 메시지로 목표를 알려주세요."
            )
        ))
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="ask: set research objectives", done_at=""))
        cast(MutableMapping[str, Any], state)["research_loop_active"] = True
        return {
            "messages": messages,
            "task_history": tasks,
            "research_loop_active": True,
            "research_objectives": objs,
            "research_plan": state.get("research_plan", {"round": 0, "objective": "", "queries": [], "timestamp": _now_str()}),
        }
    # ======== END ============================================================

    # 여기부터는 목표가 있는 정상 경로
    if pending:
        pending.done = True
        pending.done_at = _now_str()

    current_obj = objs[min(rnd, len(objs) - 1)]
    planner_prompt = get_research_planner_prompt()
    chain = planner_prompt | llm | StrOutputParser()

    queries_text = chain.invoke(
        {
            "topic_title": state.get("topic_title") or "(untitled)",
            "objective": current_obj,
            "references": _refs_preview_text(state, max_q=10, max_docs=6),
        }
    )

    # ① LLM 결과 정규화
    raw_lines = [q for q in queries_text.splitlines() if q.strip()]

    def _strip_bullet_num(s: str) -> str:
        s = re.sub(r"^\s*[\-\•]\s*", "", s)
        s = re.sub(r"^\s*\d+\.\s*", "", s)
        return re.sub(r"\s+", " ", s).strip().strip('"').strip("'")

    normed: list[str] = []
    _seen = set()
    for ln in raw_lines:
        qn = _strip_bullet_num(ln)
        if not qn:
            continue
        lk = qn.lower()
        if lk in _seen:
            continue
        _seen.add(lk)
        normed.append(qn)

    # 기존 레퍼런스/이전 플랜과 중복 제거
    try:
        existing_qs = set((state.get("references") or {}).get("queries") or [])
        existing_qs = {_strip_web_filters(q).strip().lower() for q in existing_qs if q}
    except Exception:
        existing_qs = set()

    prev_plan_qs = set(((state.get("research_plan") or {}).get("queries") or []))
    prev_plan_qs = {_strip_web_filters(q).strip().lower() for q in prev_plan_qs if q}

    deduped_normed: list[str] = []
    seen_all = set()
    for q in normed:
        k = _strip_web_filters(q).strip().lower()
        if (not k) or (k in existing_qs) or (k in prev_plan_qs) or (k in seen_all):
            continue
        seen_all.add(k)
        deduped_normed.append(q)
    normed = deduped_normed

    state["planner_queries"] = normed

    # ======== [SEARCH-ANCHOR: PLAN_PERSIST] ========
    state["research_plan"] = {
        "round": rnd + 1,
        "objective": current_obj,
        "queries": normed,
        "timestamp": _now_str(),
    }
    logger.info("[Planner] saved %s queries to state.research_plan (round=%s)", len(normed), rnd + 1)
    # ======== [END PLAN_PERSIST] ========

    plan_msg = (
        f"[Research Planner] Round {rnd + 1} objective: {current_obj}\n"
        "Queries:\n" + "\n".join(f"- {q}" for q in normed)
    )
    logger.debug(plan_msg)
    messages.append(AIMessage(content=plan_msg))

    # ======== [SEARCH-ANCHOR: SCHEDULE_NEXT] ========
    tasks = state.setdefault("task_history", [])
    skip_web = (os.getenv("SKIP_WEB_SEARCH", "0") == "1") or bool((state.get("flags") or {}).get("skip_web_search"))
    have_queries = bool(normed)

    announce = os.getenv("RESEARCH_PLANNER_ANNOUNCE", "0") == "1" or as_int(state, "research_planner_announce", 0) == 1
    if announce and not has_pending(tasks, "communicator"):
        tasks.append(Task(agent="communicator", done=False, description="announce_planner", done_at=""))

    if have_queries:
        if skip_web:
            if not has_pending(tasks, "vector_search_agent"):
                tasks.append(Task(agent="vector_search_agent", done=False, description="retrieve:auto", done_at=""))
            logger.info("[Planner] schedule next → vector_search_agent (queries=%s)", len(normed))
        else:
            if not has_pending(tasks, "web_search_agent"):
                tasks.append(Task(agent="web_search_agent", done=False, description="search:auto", done_at=""))
            logger.info("[Planner] schedule next → web_search_agent (queries=%s)", len(normed))
    else:
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="planner:no_new_queries", done_at=""))
        logger.info("[Planner] no new queries → communicator")

    return {
        "messages": messages,
        "task_history": tasks,
        "research_loop_active": True,
        "research_objectives": objs,
        "research_plan": state["research_plan"],
    }
    # ======== [END SCHEDULE_NEXT] ========
