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
from utils.rag_utils import merge_refs
from utils.query_filters import strip_web_filters as _strip_web_filters, looks_like_local_glob
from utils.forced_queries import extract_forced_queries_from_messages
from typing import Any, Dict, MutableMapping, cast
import re
import core.config as config

from core.llm import get_llm


def research_planner(state: State):
    logger.info("============ RESEARCH PLANNER ============")
    llm = get_llm()
    state = sanitize_state(state)

    # ── topic_title 통합 헬퍼 & 로깅 ───────────────────────────────
    def _get_topic_title(st) -> str:
        flags = (st.get("flags") or {})
        return (
            flags.get("topic_title")
            or st.get("topic_title")
            or config.CFG.TOPIC_TITLE
            or st.get("topic_slug")
            or "untitled"
        ).strip()

    topic_title = _get_topic_title(state)
    logger.info("[Planner] topic_title=%r", topic_title)

    # 연구 루프 시작 표식 (writer 자동 기동 가드와 연동)
    cast(MutableMapping[str, Any], state)["research_loop_active"] = True

    max_iter = int(state.get("iteration_count", 0))
    rnd = int(state.get("research_round", 0))

    # 목표 로딩: state 우선 → CFG.RESEARCH_OBJECTIVES
    def _load_objectives(st) -> list[str]:
        # 1) state 우선
        objs0 = [str(s).strip() for s in (st.get("research_objectives") or []) if str(s).strip()]
        if objs0:
            return list(dict.fromkeys(objs0))
        # 2) CFG 값 사용
        return list(dict.fromkeys(config.CFG.RESEARCH_OBJECTIVES or []))

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
            "topic_title": topic_title,  # ← state/flags/env에서 통합 확보한 값
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

    # ======== [SEARCH-ANCHOR: NORMALIZE_AFTER_LLM] ========
    # LLM이 남긴 플레이스홀더([…], {…})를 주제/목표로 치환하고,
    # 한국 타깃을 가볍게 강화하는 보정 단계. (normed가 이미 만들어진 뒤 실행!)
    topic_title = _get_topic_title(state)  # ← 통합 헬퍼 사용

    # (안전망) LLM이 만든 문장 내 (untitled) 잔존 시 즉시 치환
    normed = [q.replace("(untitled)", topic_title) for q in normed]

    def _core_subst(q: str, *, topic: str, objective: str) -> str:
        s = q

        # 불릿/번호/따옴표 정리
        s = re.sub(r"^\s*[\-\•]\s*", "", s)
        s = re.sub(r"^\s*\d+\.\s*", "", s)
        s = s.strip().strip('"').strip("'")

        # 대표 플레이스홀더 → 주제/목표/지역 치환
        repls = [
            (r"\[(?:specific\s+industry/sector|specific\s+industry|industry/sector|industry|sector)\]", objective or topic),
            (r"\{(?:industry|sector|vertical|market)\}", objective or topic),
            (r"\[(?:product|brand|company)\]", topic),
            (r"\{(?:product|brand|company)\}", topic),
            (r"\[(?:region|country|market)\]", "한국"),
            (r"\{(?:region|country|market)\}", "한국"),
        ]
        for pat, val in repls:
            s = re.sub(pat, val, s, flags=re.I)

        # 남은 대괄호/중괄호 블럭 제거
        s = re.sub(r"\[[^\]]+\]", "", s)
        s = re.sub(r"\{[^}]+\}", "", s)

        # 공백 정규화
        s = re.sub(r"\s+", " ", s).strip()

        # 한국 타깃 강화(옵션)
        if config.CFG.PLANNER_FORCE_KR:
            if not any(tok.lower() in s.lower() for tok in ("한국", "국내", "korea", "kr", "site:kr")):
                s = f"{s} 한국 시장"

        # 최소 길이/노이즈 필터
        if len(s) < 3:
            return ""
        bad = ("<script", "gtm.js", "function(", "@media")
        if any(b in s.lower() for b in bad):
            return ""
        return s

    # 핵심 치환 적용(중복 제거 포함)
    _normed_core: list[str] = []
    _seen_keys = set()
    for q in normed:
        qq = _core_subst(q, topic=topic_title, objective=current_obj)
        k = _strip_web_filters(qq).strip().lower()
        if qq and k and k not in _seen_keys:
            _seen_keys.add(k)
            _normed_core.append(qq)

    normed = _normed_core
    
    # ======== [END NORMALIZE_AFTER_LLM] ========
    # (권장) refs에 이번 라운드 쿼리 병합 → has_refs 신호 강화
    cast(MutableMapping[str, Any], state)["references"] = merge_refs(
        state.get("references"),
        normed,   # 새 쿼리들
        None      # 새 문서는 아직 없음
    )

    state["planner_queries"] = normed

    # ======== [SEARCH-ANCHOR: INJECT_FORCED_QUERIES] ========
    # 메시지에서 강제 질의 추출 → 최우선 주입
    try:
        forced = extract_forced_queries_from_messages(messages)  # e.g., "force_query: ..." 형식
        forced = [q.strip() for q in forced if q and q.strip()]
    except Exception:
        forced = []

    if forced:
        # 강제 질의에도 핵심 치환 적용
        forced_fixed = []
        _fk_seen = set()
        for q in forced:
            qq = _core_subst(q, topic=topic_title, objective=current_obj)
            k = _strip_web_filters(qq).strip().lower()
            if qq and k and k not in _fk_seen:
                _fk_seen.add(k)
                forced_fixed.append(qq)

        # 강제 질의가 앞, LLM 질의가 뒤 (중복 제거)
        merged = []
        _all_seen = set()
        for q in forced_fixed + normed:
            k = _strip_web_filters(q).strip().lower()
            if q and k and k not in _all_seen:
                _all_seen.add(k)
                merged.append(q)
        normed = merged

    # 개수 상한(옵션)
    max_q = int(config.CFG.RESEARCH_PLANNER_MAX_Q or 7)

    if max_q > 0 and len(normed) > max_q:
        normed = normed[:max_q]
    # ======== [END INJECT_FORCED_QUERIES] ========

    # ======== [SEARCH-ANCHOR: PLAN_PERSIST] ========
    state["research_plan"] = {
        "round": rnd + 1,
        "objective": current_obj,
        "queries": normed,
        "timestamp": _now_str(),
    }
    # ↓↓↓ 이 라인을 추가해야 합니다. ↓↓↓
    cast(MutableMapping[str, Any], state)["research_round"] = rnd + 1  # <--- 이 라인이 누락됨
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
    skip_web = bool(config.CFG.SKIP_WEB_SEARCH) or bool((state.get("flags") or {}).get("skip_web_search"))
    have_queries = bool(normed)

    announce = bool(config.CFG.RESEARCH_PLANNER_ANNOUNCE) or as_int(state, "research_planner_announce", 0) == 1
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
