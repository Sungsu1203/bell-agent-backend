from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os, re
from typing import Any, Mapping, Literal, MutableMapping, cast
from utils.tasks import HumanMessage, AIMessage, has_pending, schedule_writer_if_needed
from langgraph.graph import StateGraph
from core.models import Task, AgentName

# ✅ rag_expression 공통 유틸 사용
from rag_expression import (
    is_outline_display,
    is_outline_creation,
    extract_write_title,
    extract_new_topic_title,
    coerce_message_content_to_str,
    extract_rename_chapter,
)

from core.config import DOC_MODE, WRITER_AGENT
from core.paths import now_str as _now_str, current_path
from core.state_types import State

from utils.sanitize import sanitize_state, as_int, coerce_int

from prompts import get_supervisor_prompt
from core.paths import read_outline
from utils.forced_queries import extract_forced_queries_from_messages
from utils.outline import save_outline, next_unwritten_title
from utils.outline import get_topic_outline_text, pick_outline_filename as _pick_outline_filename
from core.topic import start_new_topic, sanitize_title as _sanitize_title


from core.llm import get_llm

# [ADD] ── Dashboard helpers (human-friendly progress)
_DASH_ON = str(os.getenv("SHOW_DASHBOARD", "0")).strip().lower() in ("1","true","on","yes")
_WRAP = int(os.getenv("DASH_WRAP", "88"))

def _ell(s: str, n: int = _WRAP) -> str:
    s = (s or "").replace("\n", " ").strip()
    return (s[:n-1] + "…") if len(s) > n else s

def _tcount(tasks) -> dict:
    d = {"plan":0,"web":0,"vec":0,"synth":0,"writer":0,"comm":0,"other":0}
    for t in (tasks or []):
        if getattr(t, "done", False): 
            continue
        a = (getattr(t, "agent", "") or "")
        if a == "research_planner": d["plan"] += 1
        elif a == "web_search_agent": d["web"] += 1
        elif a == "vector_search_agent": d["vec"] += 1
        elif a == "research_synthesizer": d["synth"] += 1
        elif a in ("chapter_writer","section_writer"): d["writer"] += 1
        elif a == "communicator": d["comm"] += 1
        else: d["other"] += 1
    return d

def _dash_emit(state, *, where: str, picked: str | None = None, reason: str | None = None):
    if not _DASH_ON:
        return
    tasks = state.get("task_history", []) or []
    d = _tcount(tasks)
    last_human = next((m for m in reversed(state.get("messages", [])) if getattr(m, "type", "").lower()=="human"), None)
    last_text = _ell(getattr(last_human, "content", "") if last_human else "")
    refs = state.get("references") or {}
    refs_n = len(refs.get("docs") or [])
    topic = state.get("topic_title") or state.get("topic_slug") or "untitled"
    bar = "─" * 30
    lines = [
        f"[DASH/{where}] topic='{topic}'  refs={refs_n}  picked={picked or '-'}",
        f"  plan={d['plan']}  web={d['web']}  vec={d['vec']}  synth={d['synth']}  writer={d['writer']}  comm={d['comm']}  other={d['other']}",
        f"  last_user: {last_text}",
    ]
    if reason:
        lines.append(f"  reason: {reason}")

    # [ADD] keep last dashboard timestamp in state.flags (for communicator rate-limit)
    try:
        import time as _t
        f = dict(state.get("flags") or {})
        f["dash_last_ts"] = float(_t.time())
        f["dash_count"] = int(f.get("dash_count") or 0) + 1
        state["flags"] = f
    except Exception:
        pass
    logger.info("\n" + bar + "\n" + "\n".join(lines) + "\n" + bar)


def _env_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) else default

def _is_research_mode(st: Mapping[str, Any]) -> bool:
    """agent_role/research_objectives/iteration_count로 연구 모드 여부 결정."""
    role_src = (st.get("agent_role") or _env_str("BLOCKAGI_AGENT_ROLE", "")).strip().lower()
    has_objs = bool(st.get("research_objectives"))
    max_iter = coerce_int(st.get("iteration_count", os.getenv("ITERATION_COUNT")), default=0)
    return (role_src == "research analyst") and has_objs and (max_iter > 0)

def _ensure_agent_env(state: MutableMapping[str, Any]) -> None:
    # 1) agent_role: None/빈문자 방어 + strip
    raw_role = state.get("agent_role")
    if isinstance(raw_role, str) and raw_role.strip():
        state["agent_role"] = raw_role.strip()
    else:
        state["agent_role"] = _env_str("BLOCKAGI_AGENT_ROLE", "")

    # 2) iteration_count: 존재하면 캐스팅, 없으면 env 사용 (모두 안전 캐스팅)
    if "iteration_count" in state:
        state["iteration_count"] = coerce_int(state.get("iteration_count"), default=0)
    else:
        state["iteration_count"] = coerce_int(os.getenv("ITERATION_COUNT"), default=0)

def _seed_objectives(state: MutableMapping[str, Any]) -> None:
    """
    연구목표를 state.research_objectives에 주입한다.
    - 우선순위: BLOCKAGI_OBJECTIVE_1..9 → BLOCKAGI_OBJECTIVES(JSON 배열) → (이미 state에 있으면 존중)
    - 중복 제거 및 공백 제거
    """
    if state.get("research_objectives"):
        # 이미 주입되어 있으면 그대로 둠
        if isinstance(state["research_objectives"], list):
            state["research_objectives"] = [s.strip() for s in state["research_objectives"] if str(s).strip()]
        return

    objs: list[str] = []

    # 1) BLOCKAGI_OBJECTIVE_1..9
    for i in range(1, 10):
        v = os.getenv(f"BLOCKAGI_OBJECTIVE_{i}", "")
        if isinstance(v, str) and v.strip():
            objs.append(v.strip())

    # 2) BLOCKAGI_OBJECTIVES (JSON 배열 허용)
    if not objs:
        raw = os.getenv("BLOCKAGI_OBJECTIVES", "")
        if isinstance(raw, str) and raw.strip():
            try:
                import json
                cand = json.loads(raw)
                if isinstance(cand, list):
                    objs = [str(x).strip() for x in cand if str(x).strip()]
            except Exception:
                # JSON 파싱 실패 시 무시 (로그는 communicator/DEBUG에서)
                pass

    # 3) 최종 정제(중복 제거, 빈 값 제거)
    objs = list(dict.fromkeys([o for o in objs if o]))
    state["research_objectives"] = objs



def supervisor(state: State):

    logger.info("============ SUPERVISOR ============")
    # [ADD] DASH: supervisor entry
    _dash_emit(state, where="supervisor.enter")

    llm=get_llm()

    state = sanitize_state(state)

    _ensure_agent_env(cast(MutableMapping[str, Any], state))
    _seed_objectives(cast(MutableMapping[str, Any], state))

    # 안전 초기화
    tasks = state.get("task_history", [])
    if not isinstance(tasks, list):
        tasks = list(tasks) if tasks else []
    state["task_history"] = tasks

    messages = state.get("messages", [])
    if not isinstance(messages, list):
        messages = list(messages) if messages else []
    state["messages"] = messages

    # 직답 플래그면 그대로 반환
    if state.get("qa_direct_reply"):
        logger.debug("qa_direct_reply flag detected -> short-circuit return")
        return {"messages": messages, "task_history": tasks}

    # 마지막 사용자 메시지

    # 마지막 사용자 메시지 (멀티모달까지 안전 변환)
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    last_text: str = coerce_message_content_to_str(getattr(last_human, "content", "") if last_human else "").strip()

    # ==========================================================
    # (1) 강제쿼리 최우선 라우팅
    #  - pending 태스크가 있어도 무조건 web_search_agent로 보냄
    #  - 중복 task 생성만 방지
    # ==========================================================
    try:
        fqs = extract_forced_queries_from_messages(messages, lookback=15)
    except Exception:
        logger.exception("extract_forced_queries_from_messages failed")
        fqs = []

    # 라스트 라인에 'force_query:' 직입력한 경우 보조 매칭(따옴표 유무 허용)
    if not fqs and isinstance(last_text, str):
        m_force_inline = re.match(r"^\s*force_query\s*:\s*(.+?)\s*$", last_text, flags=re.IGNORECASE)
        if m_force_inline:
            q = (m_force_inline.group(1) or "").strip().strip('"').strip("'")
            if q:
                fqs = [q]

    if fqs:
        if not has_pending(tasks, "web_search_agent"):
            tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        msg = f"[Supervisor fast-path] → web_search_agent (force_queries {len(fqs)}개 감지)"
        messages.append(AIMessage(content=msg))
        logger.info(msg)
        # print(msg)
        _dash_emit(state, where="supervisor", picked="web_search_agent", reason="force_queries")
        return {"messages": messages, "task_history": tasks}
    # ==========================================================

    def _is_qa_like(s: str) -> bool:
        if not isinstance(s, str):
            return False
        s = s.strip()
        if not s:
            return False
        qa_markers = ("요약", "정리", "설명해줘", "무엇", "뭐야", "어떻게", "왜", "누가", "어디", "언제", "비교", "?")
        return any(k in s for k in qa_markers)

    # QA/요약형 요청 → 벡터 검색 예약
    if last_text and _is_qa_like(last_text):
        # 💡 [핵심 수정] vector_search_agent의 pending task가 없을 때만 생성/예약
        if not has_pending(tasks, "vector_search_agent"):
            
            # 1. 태스크 명시적 생성 (QA 쿼리를 description에 포함)
            tasks.append(
                Task(
                    agent="vector_search_agent", 
                    done=False, 
                    description=f"qa_query:{last_text}", # 사용자 질문을 description에 명시
                    done_at=""
                )
            )
            
            # 2. QA 답변을 communicator가 출력하도록 플래그 설정 (Communicator가 처리할 수 있도록)
            state["qa_direct_reply"] = True 

            logger.info("[Supervisor fast-path] QA-like → vector_search_agent scheduled")
            _dash_emit(state, where="supervisor", picked="vector_search_agent", reason="qa_like_new_task")
            
        else:
            logger.info("[Supervisor fast-path] vector_search_agent pending task already exists.")

        # vector_search_agent로 라우팅
        return {"messages": messages, "task_history": tasks, "qa_direct_reply": state.get("qa_direct_reply")}

    # 새 토픽 (rag_expression 헬퍼 사용)
    new_title = extract_new_topic_title(last_text)
    if new_title:
        maybe_title = _sanitize_title(new_title or "untitled report")

        state = start_new_topic(state, maybe_title, outline_fname=_pick_outline_filename(last_text))

        # 새 세션 환경 주입 통일
        _ensure_agent_env(cast(MutableMapping[str, Any], state))
        _seed_objectives(cast(MutableMapping[str, Any], state))

        msg = f"[Supervisor] 새 주제 세션 시작: '{state.get('topic_title','')}' (ns={state.get('chroma_ns','')})"
        messages.append(AIMessage(msg))
        logger.info(msg)
        _dash_emit(state, where="supervisor", picked="content_strategist/web_search_agent", reason="new_topic_boot")
        # print(msg)

        # 1) 목차 생성 예약 (중복 방지)
        fname = state.get("outline_fname", "outline.md")
        if not has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))

        # 2) RAG-first 보장: 레퍼런스 비어있다면 web_search_agent 펜딩도 함께 예약
        refs = state.get("references") or {}
        refs_empty = not (refs.get("docs") or [])
        if refs_empty and not has_pending(tasks, "web_search_agent"):
            tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
            messages.append(AIMessage(content="[Supervisor fast-path] → web_search_agent (RAG 업데이트 착수)"))
            logger.info("[Supervisor fast-path] RAG-first kickoff (refs empty)")

        return {
            "messages": messages,
            "task_history": tasks,
            "topic_title": state.get("topic_title"),
            "topic_slug": state.get("topic_slug"),
            "chroma_ns": state.get("chroma_ns"),
            "outline_fname": state.get("outline_fname"),
            "references": state.get("references"),
        }

    # 연구 라운드 모드 부트스트랩
    if _is_research_mode(state):
        # 연구 파이프라인 태스크 여부 확인
        research_agents = ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")
        has_research_pending = any(has_pending(tasks, a) for a in research_agents)

        if not has_research_pending:
            # communicator가 대기 중이면 연구 우선으로 auto-close
            now = _now_str()
            for t in tasks:
                if (not t.done) and t.agent == "communicator":
                    t.done = True
                    t.done_at = now
                    t.description = (t.description or "") + " [auto-closed: start research loop]"

            # 연구 라운드 시작: planner부터
            tasks.append(Task(agent="research_planner", done=False, description="plan: auto", done_at=""))
            msg = "[Supervisor fast-path] 연구 라운드 모드 시작 → research_planner"
            messages.append(AIMessage(content=msg))
            logger.info(msg)
            _dash_emit(state, where="supervisor", picked="research_planner", reason="research_mode_bootstrap")
            # print(msg)
            return {"messages": messages, "task_history": tasks}

    
    # --- 목차 단순 표시 요청은 최우선으로 communicator(show_outline)로 보낸다 ---
    _outline_show_intent = (
        is_outline_display(last_text)
        or bool(re.search(r"(목차|outline).*(보여줘|보여|display|show)", last_text, re.I))
        or last_text.strip() in {"목차", "목차 보여줘", "show outline", "show me the outline"}
    )
    if _outline_show_intent:
        fname = _pick_outline_filename(last_text)
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))
        messages.append(AIMessage(content=f"[Supervisor fast-path] → communicator (show_outline:{fname})"))
        logger.info("[Supervisor fast-path] show_outline → communicator (target=%s)", fname)
        _dash_emit(state, where="supervisor", picked="communicator", reason="show_outline")
        return {"messages": messages, "task_history": tasks}
    
    # [ANCHOR] research-mode preemption (insert BEFORE communicator fast-path)

    if _is_research_mode(state):
        # 연구 파이프라인이 아직 안 올라가 있으면 planner를 먼저 올림
        no_research_pending = not any(
            has_pending(state.get("task_history", []), a)
            for a in ("research_planner", "web_search_agent", "vector_search_agent", "research_synthesizer")
        )
        if no_research_pending:
            # communicator가 대기 중이면 자동 종료 처리(연구 우선)
            for t in state.get("task_history", []):
                if (not t.done) and t.agent == "communicator":
                    t.done = True
                    t.done_at = _now_str()
                    t.description = (t.description or "") + " [auto-closed: start research loop]"

            # 연구 시작 시, 대기 중 writer도 자동 종료 처리(조기 집필 차단)
            for t in state.get("task_history", []):
                if (not t.done) and t.agent in ("chapter_writer", "section_writer"):
                    t.done = True
                    t.done_at = _now_str()
                    t.description = (t.description or "") + " [auto-closed: start research loop]"

            tasks = state.get("task_history", [])
            tasks.append(Task(agent="research_planner", done=False, description="plan: auto", done_at=""))
            logger.info("[Supervisor fast-path] research_mode preemption → research_planner")
            _dash_emit(state, where="supervisor", picked="research_planner", reason="research_mode_preempt")
            return {"messages": state.get("messages", []), "task_history": tasks}

    # 목차 생성 pending 우선 처리
    pending_cs = next((t for t in reversed(tasks) if (not t.done) and t.agent == "content_strategist"), None)
    if pending_cs and not (is_outline_display(last_text) or is_outline_creation(last_text)):
        logger.info("[Supervisor priority] content_strategist pending → 우선 진행")
        # print("[Supervisor priority] content_strategist pending → 우선 진행")
        return {
            "messages": messages,
            "task_history": tasks,
            "topic_title": state.get("topic_title"),
            "topic_slug": state.get("topic_slug"),
            "chroma_ns": state.get("chroma_ns"),
            "outline_fname": state.get("outline_fname"),
            "references": state.get("references")
            # "last_saved_path": state.get("last_saved_path"),
        }

    # fast-path: 목차 생성/표시
    if is_outline_creation(last_text):
        fname = _pick_outline_filename(last_text)
        if not has_pending(tasks, "content_strategist"):   # ✅ 중복 예약 방지
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        msg = f"[Supervisor fast-path] → content_strategist (target={fname})"
        messages.append(AIMessage(content=msg))
        logger.info(msg)
        # print(msg)
        return {"messages": messages, "task_history": tasks}

    if is_outline_display(last_text):
        fname = _pick_outline_filename(last_text)
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))
        msg = f"[Supervisor fast-path] → communicator (show_outline:{fname})"
        messages.append(AIMessage(content=msg))
        logger.info(msg)
        # print(msg)
        return {"messages": messages, "task_history": tasks}

    # fast-path: RAG 업데이트 키워드
    _rag_re = r"(최신|업데이트|update|latest).*?(자료|리소스|레퍼런스|참고|sources|material).*?(rag|벡터|vector|임베딩|embedding|index|색인|chroma)"
    if re.search(_rag_re, last_text, flags=re.IGNORECASE):
        now = _now_str()
        for t in tasks:
            if (not t.done) and t.agent in ("chapter_writer", "section_writer"):
                t.done = True
                t.done_at = now
        msg = "[Supervisor fast-path] 기존 writer 태스크 정리 후 RAG 업데이트 시작."
        messages.append(AIMessage(content=msg))
        logger.info(msg)
        # print(msg)
        tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        msg = "[Supervisor fast-path] → web_search_agent (RAG 업데이트 착수)"
        messages.append(AIMessage(content=msg))
        logger.info(msg)
        # print(msg)
        _dash_emit(state, where="supervisor", picked="web_search_agent", reason="rag_update_fastpath")
        return {"messages": messages, "task_history": tasks}

    # fast-path: write: ...
    target_from_line = extract_write_title(last_text)
    if target_from_line:
        # 💡 [핵심 수정] 명확한 writer 요청이 들어왔을 때 communicator 태스크 자동 종료
        now = _now_str()
        for t in tasks:
            # communicator가 대화 대기 중인 경우, 이를 완료 처리
            if (not t.done) and t.agent == "communicator":
                t.done = True
                t.done_at = now
                t.description = (t.description or "") + " [auto-closed: writer request]"
                logger.info("[Supervisor fast-path] auto-closed pending communicator task.")
        refs = state.get("references", {})
        refs_empty = not (refs.get("docs") or [])
        has_pending_rag = any((not t.done) and t.agent in ("web_search_agent", "vector_search_agent") for t in tasks)
        if refs_empty or has_pending_rag:
            if not has_pending(tasks, "web_search_agent"):
                tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
            msg = "[Supervisor fast-path] 레퍼런스 비어있음/진행중 → RAG 먼저(web_search_agent)."
            messages.append(AIMessage(content=msg))
            logger.info(msg)
            _dash_emit(state, where="supervisor", picked="web_search_agent", reason="write_but_refs_empty")
            # print(msg)
            return {"messages": messages, "task_history": tasks}

        # 🔁 단일 진입점으로 writer 예약 (중복/모드 자동 처리)
        did = schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            tasks=tasks,
            messages=messages,
            outline_text=get_topic_outline_text(state),
            requested_title=target_from_line,
            allow_during_research=os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1",
            debug=True,
        )
        if did:
            msg = f"[Supervisor fast-path] → {WRITER_AGENT} (mode={DOC_MODE}, write: {target_from_line})"
            messages.append(AIMessage(content=msg))
            logger.info(msg)
            _dash_emit(state, where="supervisor", picked=WRITER_AGENT, reason="write_with_refs")
        else:
            messages.append(AIMessage(content="[Supervisor] writer 예약이 생략되었습니다(조건 부적합 또는 중복)."))
        return {"messages": messages, "task_history": tasks}

    # fast-path: "N장 제목을 '...'로 변경"
    _rename = extract_rename_chapter(last_text)
    if _rename:
        idx, new_title = _rename
        fname = _pick_outline_filename(last_text)
        if not has_pending(tasks, "content_strategist"):
            tasks.append(Task(
                agent="content_strategist",
                done=False,
                description=f"rename_heading:{idx}:{new_title}:{fname}",
                done_at=""
            ))
        messages.append(AIMessage(
            content=f"[Supervisor fast-path] → content_strategist (rename_heading:{idx}→{new_title})"
        ))
        _dash_emit(state, where="supervisor", picked="content_strategist", reason="rename_heading")
        return {"messages": messages, "task_history": tasks}

    # 기존 미완료 태스크가 있으면 새로 만들지 않음
    pending_undone = next((t for t in reversed(tasks) if not t.done), None)
    if pending_undone:
        logger.info("[Supervisor short-circuit] pending='%s' 유지 → 새 태스크 생성 생략", pending_undone.agent)
        # print(f"[Supervisor short-circuit] pending='{pending_undone.agent}' 유지 → 새 태스크 생성 생략")
        logger.debug("tasks tail = %s", [(getattr(t,'agent',None), getattr(t,'done',None), getattr(t,'description',None)) for t in tasks][-3:])
        # print("tasks tail =", [(getattr(t,'agent',None), getattr(t,'done',None), getattr(t,'description',None)) for t in tasks][-3:])
        _dash_emit(state, where="supervisor", picked=pending_undone.agent, reason="pending_short_circuit")
        return {
            "messages": messages,
            "task_history": tasks,
            "topic_title": state.get("topic_title"),
            "topic_slug": state.get("topic_slug"),
            "chroma_ns": state.get("chroma_ns"),
            "outline_fname": state.get("outline_fname"),
            "references": state.get("references")
            # "last_saved_path": state.get("last_saved_path"),
        }

    # 일반 경로
    supervisor_system_prompt = get_supervisor_prompt()
    supervisor_chain = supervisor_system_prompt | llm.with_structured_output(Task)
    
    try:
        res = supervisor_chain.invoke(
            {
                "messages": messages,
                "outline": get_topic_outline_text(state),
                "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
            }
        )

    except Exception:
        logger.exception("supervisor_chain.invoke failed")
        raise

    # ✅ 런타임 방어 + 타입 좁히기
    if isinstance(res, Task):
        task: Task = res
    elif isinstance(res, dict):
        # dict로 왔을 때도 안전하게 Pydantic 모델로 승격
        task = Task(**res)
    else:
        raise TypeError(f"[Supervisor] Unexpected return type from supervisor_chain: {type(res)}")

    if task.agent in ("chapter_writer", "section_writer"):
        # LLM이 제안한 제목이 있으면 활용
        requested = extract_write_title(task.description or "") or None
        did = schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            tasks=tasks,
            messages=messages,
            outline_text=get_topic_outline_text(state),
            requested_title=requested,
            allow_during_research=os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1",
            debug=True,
        )
        if did:
            msg = f"[Supervisor reconcile] writer 예약 완료 (mode={DOC_MODE}, requested={requested or '(auto)'})"
            messages.append(AIMessage(content=msg))
            logger.info(msg)
            return {
                "messages": messages,
                "task_history": tasks,
                "topic_title": state.get("topic_title"),
                "topic_slug": state.get("topic_slug"),
                "chroma_ns": state.get("chroma_ns"),
                "outline_fname": state.get("outline_fname"),
                "references": state.get("references"),
            }
        else:
            messages.append(AIMessage(content="[Supervisor] writer 예약 불필요/중복으로 생략됨."))
            logger.info("[Supervisor] writer scheduling skipped.")
            _dash_emit(state, where="supervisor", picked="communicator", reason="writer_skipped")
            return {
                "messages": messages,
                "task_history": tasks,
                "topic_title": state.get("topic_title"),
                "topic_slug": state.get("topic_slug"),
                "chroma_ns": state.get("chroma_ns"),
                "outline_fname": state.get("outline_fname"),
                "references": state.get("references"),
            }

    # writer 이외의 태스크는 기존대로 추가
    tasks.append(task)
    msg = f"[Supervisor] {task}"
    messages.append(AIMessage(content=msg))
    logger.info(msg)
    _dash_emit(state, where="supervisor", picked=task.agent, reason="supervisor_fallback_route")


    return {
        "messages": messages,
        "task_history": tasks,
        "topic_title": state.get("topic_title"),
        "topic_slug": state.get("topic_slug"),
        "chroma_ns": state.get("chroma_ns"),
        "outline_fname": state.get("outline_fname"),
        "references": state.get("references")
        # "last_saved_path": state.get("last_saved_path"),
    }

def supervisor_router(state: State) -> str:
    state = sanitize_state(state)
    tasks = state.get("task_history", []) or []
    refs = state.get("references") or {}
    refs_docs = list(refs.get("docs") or [])
    refs_empty = (len(refs_docs) == 0)

    def _has(agent: str, prefix: str | None = None) -> bool:
        try:
            return has_pending(tasks, agent, prefix=prefix)
        except Exception:
            return any((not getattr(t, "done", False)) and getattr(t, "agent", "") == agent for t in tasks)

    preferred = "section_writer" if DOC_MODE == "report" else "chapter_writer"
    alt = "chapter_writer" if preferred == "section_writer" else "section_writer"

    # 0-A) 연구모드 선점: 연구 파이프라인을 writer보다 우선
    if _is_research_mode(state):
        # 사용자가 명시적으로 write: 를 요청한 경우는 0-3 fastpath가 처리
        # ✅ writer가 이미 펜딩이면 연구 선점 금지 (writer 우선)
        if _has(preferred, prefix="write:") or _has(alt, prefix="write:"):
            logger.info("[supervisor_router] writer pending → skip research preempt")
        else:
            # 연구 파이프라인 펜딩 없을 때만 planner로 선점
            if not any(_has(a) for a in ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")):
                print("[supervisor_router] picked=research_planner  (research-mode preempt)")
                return "research_planner"

    # ─────────────────────────────────────────
    # 0) 사용자 의도 기반 "단축 분기" (펜딩 검사보다 '먼저')
    last_human = next((m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), None)
    last_text = coerce_message_content_to_str(getattr(last_human, "content", ""))

    # 0-0) 새 주제 전환 → RAG 먼저(web_search_agent) if refs 비어있음, 아니면 communicator
    new_topic = extract_new_topic_title(last_text)
    if new_topic:
        ret = "web_search_agent" if refs_empty else "communicator"
        logger.info("[supervisor_router] picked=%s  (new_topic='%s', refs_empty=%s)", ret, new_topic, refs_empty)
        _dash_emit(state, where="router", picked=ret, reason=f"new_topic refs_empty={refs_empty}")
        logger.debug(
            "cs=%s, wr_pref=%s, wr_alt=%s, plan=%s, synth=%s, vec=%s, web=%s, comm=%s",
            _has('content_strategist'), _has(preferred,'write:'), _has(alt,'write:'),
            _has('research_planner'), _has('research_synthesizer'),
            _has('vector_search_agent'), _has('web_search_agent'), _has('communicator')
        )
        return ret

    # 0-1) 목차 '표시' 의도 → communicator
    if is_outline_display(last_text):
        ret = "communicator"
        logger.info("[supervisor_router] picked=%s  (show_outline)", ret)
        _dash_emit(state, where="router", picked=ret, reason="show_outline")
        logger.debug("cs=%s, comm=True", _has('content_strategist'))
        # print(f"[supervisor_router] picked={ret}  (show_outline, cs={_has('content_strategist')}, comm=True)")
        return ret

    # 0-2) 목차 '생성' 의도 → content_strategist
    if is_outline_creation(last_text):
        ret = "content_strategist"
        logger.info("[supervisor_router] picked=%s  (create_outline)", ret)
        _dash_emit(state, where="router", picked=ret, reason="create_outline")
        logger.debug("cs=True")
        # print(f"[supervisor_router] picked={ret}  (create_outline, cs=True)")
        # logger.info("[supervisor_router] picked=%s  (create_outline, cs=True)", ret)
        return ret

    # 0-3) 강제 집필(write:) → DOC_MODE별 writer (refs 비면 RAG부터)
    write_title = extract_write_title(last_text)
    if write_title:
        if refs_empty:
            ret = "web_search_agent"
            logger.info("[supervisor_router] picked=%s  (fastpath write, title='%s', refs_empty=True → RAG first)", ret, write_title)
            _dash_emit(state, where="router", picked=ret, reason="write_refs_empty")
            # print(f"[supervisor_router] picked={ret}  (fastpath write, title='{write_title}', refs_empty=True → RAG first)")
            return ret
        ret = preferred
        logger.info("[supervisor_router] picked=%s  (fastpath write, title='%s', refs_empty=False)", ret, write_title)
        _dash_emit(state, where="router", picked=ret, reason="write_refs_present")
        # print(f"[supervisor_router] picked={ret}  (fastpath write, title='{write_title}', refs_empty=False)")
        return ret

    # ─────────────────────────────────────────
    # 1) 펜딩 우선순위 (연구플로우 > 수집/검색 > writer > 커뮤니케이션)
    if _has("content_strategist"):
        ret = "content_strategist"
    elif _has(alt, prefix="write:"):
        ret = alt
    elif _has("research_planner"):
        ret = "research_planner"
    elif _has("web_search_agent"):
        ret = "web_search_agent"
    elif _has("vector_search_agent"):
        ret = "vector_search_agent"
    elif _has("research_synthesizer"):
        ret = "research_synthesizer"
    elif _has(preferred, prefix="write:"):
        ret = preferred
    elif _has("communicator"):
        ret = "communicator"
    else:
        # 기본값: QA형이면 벡터검색, 아니면 communicator
        
        # 💡 [수정 시작] last_text에 "작성", "써줘" 등의 writer 의도가 있는지 확인
        is_writing_intent = any(k in last_text for k in ("작성","써줘","write"))
        is_qa_intent = any(k in last_text for k in ("요약","정리","무엇","왜","비교","?"))
        
        if is_writing_intent:
            # 작성 의도가 명확하면, 목차에서 다음 섹션을 찾아서 writer로 보냅니다.
            # 이 로직은 0-3 fastpath가 write_title을 추출하지 못했을 때만 작동해야 합니다.
            # 하지만 안전을 위해 preferred writer로 강제 라우팅합니다.
            ret = preferred
        elif is_qa_intent:
            ret = "vector_search_agent"
        else:
            ret = "communicator"
        # ──────────────────────────────────────────────────────────────

    logger.info("[supervisor_router] picked=%s", ret)
    _dash_emit(state, where="router", picked=ret, reason="default_route")
    logger.debug(
        "cs=%s, wr_pref=%s, wr_alt=%s, plan=%s, synth=%s, vec=%s, web=%s, comm=%s",
        _has('content_strategist'), _has(preferred,'write:'), _has(alt,'write:'),
        _has('research_planner'), _has('research_synthesizer'),
        _has('vector_search_agent'), _has('web_search_agent'), _has('communicator')
    )
    # print(f"[supervisor_router] picked={ret}  (cs={_has('content_strategist')}, wr_pref={_has(preferred,'write:')}, "
    #       f"wr_alt={_has(alt,'write:')}, plan={_has('research_planner')}, synth={_has('research_synthesizer')}, "
    #       f"vec={_has('vector_search_agent')}, web={_has('web_search_agent')}, comm={_has('communicator')})")
    return ret