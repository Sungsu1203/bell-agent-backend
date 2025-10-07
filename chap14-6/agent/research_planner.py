from __future__ import annotations
from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.messages import AIMessage

from core.paths import now_str as _now_str
from core.state_types import State
from core.models import Task, AgentName
from utils.sanitize import sanitize_state, as_int
from utils.rag_utils import refs_preview_text
from prompts import get_research_planner_prompt
from utils.tasks import has_pending
from utils.refs import refs_preview_text as _refs_preview_text
from utils.query_filters import strip_web_filters as _strip_web_filters, looks_like_local_glob
from utils.forced_queries import extract_forced_queries_from_messages
import os, re

from core.llm import get_llm
llm=get_llm()

def research_planner(state: State):
    print("\n\n============ RESEARCH PLANNER ============")
    # state = sanitize_numeric_state(state)
    state = sanitize_state(state)

    # 키 이름 일괄 보정 (공백 키 → snake_case)
    if "iteration count" in state and "iteration_count" not in state:
        state["iteration_count"] = state["iteration count"]
    if "research round" in state and "research_round" not in state:
        state["research_round"] = state["research round"]
    if "task history" in state and "task_history" not in state:
        state["task_history"] = state["task history"]

    # 기본값 보정
    state.setdefault("iteration_count", 0)
    state.setdefault("research_round", 0)
    state.setdefault("messages", [])
    state.setdefault("task_history", [])
    state.setdefault("research_objectives", [])

    # max_iter = state["iteration_count"]
    # rnd = state["research_round"]
    # objs = state.get("research_objectives") or []
    max_iter = int(state.get("iteration_count", 0))   # OK
    rnd = int(state.get("research_round", 0))         # OK
    objs = state.get("research_objectives", [])       # OK

    if not objs:
        return {
            "messages": state.get("messages", []),
            "task_history": state.get("task_history", []),  # 공백X
        }
        # return {"messages": state["messages"], "task_history": state["task_history"]}

    tasks = state.get("task_history", [])
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "research_planner"), None)
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
    # ① LLM 결과 줄 분해 + 번호/불릿 제거 + 공백/중복 정리
    raw_lines = [q for q in queries_text.splitlines() if q.strip()]

    def _strip_bullet_num(s: str) -> str:
        s = re.sub(r"^\s*[\-\•]\s*", "", s)      # bullet ("- ", "• ")
        s = re.sub(r"^\s*\d+\.\s*", "", s)       # numbering ("1. ", "2. " ...)
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

    # --- 기존 레퍼런스/이전 플랜과 중복 제거(+필터 토큰 제거) ---
    try:
        existing_qs = set((state.get("references") or {}).get("queries") or [])
        existing_qs = { _strip_web_filters(q).strip().lower() for q in existing_qs if q }
    except Exception:
        existing_qs = set()

    prev_plan_qs = set(((state.get("research_plan") or {}).get("queries") or []))
    prev_plan_qs = { _strip_web_filters(q).strip().lower() for q in prev_plan_qs if q }

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

    
    # ======== [SEARCH-ANCHOR: PLAN_PERSIST] persist planner queries for web_search_agent ========
    state["research_plan"] = {
        "round": rnd + 1,
        "objective": current_obj,
        "queries": normed,   # ← 위에서 정규화한 질의 그대로 저장
        "timestamp": _now_str(),
    }
    print(f"[Planner] saved {len(normed)} queries to state.research_plan (round={rnd + 1})")
    # ======== [END PLAN_PERSIST] =================================================

    plan_msg = (
        f"[Research Planner] Round {rnd + 1} objective: {current_obj}\n"
        "Queries:\n" + "\n".join(f"- {q}" for q in normed)
    )
    print("\n" + plan_msg)

    messages = state.get("messages", [])
    messages.append(AIMessage(plan_msg))

    announce = os.getenv("RESEARCH_PLANNER_ANNOUNCE", "0") == "1" or as_int(state, "research_planner_announce", 0) == 1
    if announce and not has_pending(tasks, "communicator"):
        tasks.append(Task(agent="communicator", done=False, description="announce_planner", done_at=""))

    if not has_pending(tasks, "web_search_agent"):
        tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))

    return {"messages": messages, "task_history": tasks}
