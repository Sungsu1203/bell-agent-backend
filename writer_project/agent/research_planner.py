from __future__ import annotations
from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage
import os

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
from tools.web_rag.ingest import _default_chroma_dir  # Chroma persist dir resolver

def research_planner(state: State):
    logger.info("============ RESEARCH PLANNER ============")
    llm = get_llm()
    state = cast(State, sanitize_state(state))

    # ── Config helpers (env → CFG → module default) ───────────────────────────
    def _cfg_str(name: str, default: str = "") -> str:
        try:
            v = getattr(config.CFG, name, None)
            if v is None:
                v = getattr(config, name, None)
        except Exception:
            v = None
        if v is None:
            import os as _os
            v = _os.getenv(name, default)
        return str(v) if v is not None else default

    def _cfg_int(name: str, default: int = 0) -> int:
        s = _cfg_str(name, str(default))
        try:
            return int(str(s).strip())
        except Exception:
            return default

    def _cfg_bool(name: str, default: bool = False) -> bool:
        s = _cfg_str(name, "1" if default else "0").strip().lower()
        return s in {"1","true","yes","y","on"}
    
    # ── ns helper (간단 정규화: 소문자, 영문/숫자/하이픈만 유지) ──────────────────
    import re as _re
    def _ns_sanitize(s: str) -> str:
        s = (s or "").strip().lower()
        s = _re.sub(r"[^a-z0-9\-]+", "-", s)
        s = _re.sub(r"-{2,}", "-", s).strip("-")
        return s or "default"


    # ── topic_title 통합 헬퍼 & 로깅 ───────────────────────────────
    def _get_topic_title(st) -> str:
        flags = (st.get("flags") or {})
        return (
            flags.get("topic_title")
            or st.get("topic_title")
            or _cfg_str("TOPIC_TITLE", "")
            or st.get("topic_slug")
            or "untitled"
        ).strip()

    topic_title = _get_topic_title(state)
    logger.info("[Planner] topic_title=%r", topic_title)

    # 연구 루프 시작 표식 (writer 자동 기동 가드와 연동)
    cast(MutableMapping[str, Any], state)["research_loop_active"] = True


    # ── [CHROMA NS INIT] 웹/벡터 단계와 조응되는 네임스페이스/디렉터리 기록 ─────
    # topic_slug 우선, 없으면 CFG.TOPIC_SLUG → 'default'
    topic_slug_raw = (state.get("topic_slug") or _cfg_str("TOPIC_SLUG", "") or "default").strip()
    env_ns_raw     = (_cfg_str("CHROMA_NAMESPACE", "") or "").strip()
    ns_web_raw     = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc_raw     = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()

    topic_slug = _ns_sanitize(topic_slug_raw)
    env_ns     = _ns_sanitize(env_ns_raw) if env_ns_raw else ""
    ns         = env_ns or _ns_sanitize(f"{topic_slug}-default")
    persist_dir = _default_chroma_dir(ns)

    # flags.chroma에 일관 포맷으로 주입 (web_search/vector_search와 동일 키)
    flags_mm = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    chroma   = cast(MutableMapping[str, Any], flags_mm.setdefault("chroma", {}))
    chroma.update({
        "ns": ns,
        "dir": persist_dir,
    })
    if ns_web_raw:
        chroma["ns_web"] = _ns_sanitize(ns_web_raw)
    if ns_loc_raw:
        chroma["ns_local"] = _ns_sanitize(ns_loc_raw)
    logger.info("[Planner][ns] ns=%s dir=%s ns_web=%s ns_local=%s",
                ns, persist_dir, chroma.get("ns_web","-"), chroma.get("ns_local","-"))

    max_iter = int(state.get("iteration_count", 0))
    rnd = int(state.get("research_round", 0))

    # 목표 로딩: state 우선 → CFG.RESEARCH_OBJECTIVES
    def _coerce_objectives(obj: Any) -> list[str]:
        """임의의 반환값을 안전한 리스트[str]로 변환."""
        try:
            # 1) 이미 리스트/튜플/셋 계열
            from collections.abc import Iterable
            if isinstance(obj, (list, tuple, set)):
                return [str(x).strip() for x in obj if str(x).strip()]
            # 2) 문자열: JSON 배열 → split(줄바꿈/쉼표) 처리
            if isinstance(obj, str):
                s = obj.strip()
                if not s:
                    return []
                # JSON 배열 시도
                import json as _json
                try:
                    arr = _json.loads(s)
                    if isinstance(arr, list):
                        return [str(x).strip() for x in arr if str(x).strip()]
                except Exception:
                    pass
                # 구분자 기반 파싱
                import re as _re
                toks = [t.strip() for t in _re.split(r"[,\n;|]+", s) if t.strip()]
                return toks
            # 3) 매핑: values()를 후보로 사용
            if isinstance(obj, dict):
                return [str(v).strip() for v in obj.values() if str(v).strip()]
            # 4) 그 외 단일 객체
            return [str(obj).strip()] if str(obj).strip() else []
        except Exception:
            return []

    def _load_objectives(st) -> list[str]:
        # 1) state 우선
        objs0 = [str(s).strip() for s in (st.get("research_objectives") or []) if str(s).strip()]
        if objs0:
            return list(dict.fromkeys(objs0))

        # 1.5) ENV: BLOCKAGI_OBJECTIVE_1..n (가장 흔한 형태) 직접 로딩
        # loader가 없거나 실패해도 objectives가 "합쳐지지 않도록" 보장합니다.
        env_split: list[str] = []
        for i in range(1, 10):
            v = (os.getenv(f"BLOCKAGI_OBJECTIVE_{i}") or "").strip()
            if v:
                env_split.append(v)
        if env_split:
            return list(dict.fromkeys(env_split))
        
        # 2) ENV/CFG 혼합 로딩 (가능하면 helper 사용)
        try:
            loader = getattr(config, "load_research_objectives_from_env", None)
            if callable(loader):
                cand = loader()
                coerced = _coerce_objectives(cand)
                if coerced:
                    return list(dict.fromkeys(coerced))
        except Exception:
            pass
        raw = _cfg_str("BLOCKAGI_OBJECTIVES", "")
        coerced_env = _coerce_objectives(raw)
        if coerced_env:
            return list(dict.fromkeys(coerced_env))
        # 3) 마지막으로 CFG.RESEARCH_OBJECTIVES (있다면)
        try:
            ro = getattr(config.CFG, "RESEARCH_OBJECTIVES", []) or []
            return list(dict.fromkeys(_coerce_objectives(ro)))
        except Exception:
            return []

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

    def _strip_unbalanced_quotes(s: str) -> str:
        """
        LLM 출력에 따옴표가 한쪽만 남아 있으면(odd count) 검색이 0건이 되는 경우가 많습니다.
        - " 개수가 홀수면: 전체 " 제거
        - ' 도 홀수면 제거(보수적으로)
        """
        if not s:
            return s
        try:
            if s.count('"') % 2 == 1:
                s = s.replace('"', " ")
            if s.count("'") % 2 == 1:
                s = s.replace("'", " ")
            s = re.sub(r"\s{2,}", " ", s).strip()
            return s
        except Exception:
            return s

    def _strip_bullet_num(s: str) -> str:
        s = re.sub(r"^\s*[\-\•]\s*", "", s)
        s = re.sub(r"^\s*\d+\.\s*", "", s)
        s = re.sub(r"\s+", " ", s).strip().strip('"').strip("'")
        return _strip_unbalanced_quotes(s)

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
        # 따옴표 안전화(LLM이 남긴 홀수 따옴표 제거)
        s = _strip_unbalanced_quotes(s)

        # 한국 타깃 강화(옵션)
        if _cfg_bool("PLANNER_FORCE_KR", False):
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
    # 1목표=1쿼리 기본값(필요하면 ENV로 늘릴 수 있음)
    max_q = int(_cfg_int("RESEARCH_PLANNER_MAX_Q", 2) or 2)

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
    skip_web = _cfg_bool("SKIP_WEB_SEARCH", False) or bool((state.get("flags") or {}).get("skip_web_search"))
    have_queries = bool(normed)

    announce = _cfg_bool("RESEARCH_PLANNER_ANNOUNCE", False) or as_int(state, "research_planner_announce", 0) == 1
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
