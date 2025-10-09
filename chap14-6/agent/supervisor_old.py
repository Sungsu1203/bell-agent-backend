from __future__ import annotations
import os, re
from typing import Any, Mapping, Literal, MutableMapping, cast
from utils.tasks import HumanMessage, AIMessage, has_pending
from langgraph.graph import StateGraph
from core.models import Task, AgentName

# ✅ rag_expression 공통 유틸 사용
from rag_expression import (
    is_outline_display,
    is_outline_creation,
    extract_write_title,
    extract_new_topic_title,
    coerce_message_content_to_str,
)

from core.config import DOC_MODE, WRITER_AGENT
from core.paths import now_str as _now_str, current_path
from core.state_types import State

from utils.sanitize import sanitize_state, as_int, coerce_int

from prompts import get_supervisor_prompt
from content_utils import read_outline
from utils.forced_queries import extract_forced_queries_from_messages
from content_utils import save_outline, next_unwritten_title
from utils.outline import get_topic_outline_text, pick_outline_filename as _pick_outline_filename
from core.topic import start_new_topic, sanitize_title as _sanitize_title


from core.llm import get_llm

def _env_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v.strip() if isinstance(v, str) else default

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
    """환경변수 BLOCKAGI_OBJECTIVE_1..9 를 research_objectives 에 주입 (비어있을 때만)."""
    if state.get("research_objectives"):
        return
    objs: list[str] = []
    for i in range(1, 10):
        v = os.getenv(f"BLOCKAGI_OBJECTIVE_{i}", "")
        if isinstance(v, str) and v.strip():
            objs.append(v.strip())
    state["research_objectives"] = objs


def supervisor(state: State):
    ### BEGIN: copy main.py's supervisor body, replacing helpers with imported ones
    #  - now_str -> _now_str
    #  - DOC_MODE/WRITER_AGENT from core.config
    #  - sanitize_numeric_state_generic/as_int from utils.sanitize
    #  - read_outline/save_outline/next_unwritten_title from content_utils
    #  - etc.
    ### END

    print("\n\n============ SUPERVISOR ============")
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
        return {"messages": messages, "task_history": tasks}

    # 마지막 사용자 메시지
    def _ensure_text(c) -> str:
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            # OpenAI-style: [{"type":"text","text":"..."}] 등 처리
            parts = []
            for item in c:
                if isinstance(item, dict):
                    # text 필드 우선, 없으면 data/url 등 필요한 것 추출 가능
                    t = item.get("text") or item.get("content") or ""
                    if isinstance(t, str):
                        parts.append(t)
            return " ".join(parts)
        return ""

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    raw_content = getattr(last_human, "content", "") if last_human else ""
    last_text: str = _ensure_text(raw_content).strip()

    # [ANCHOR] seed research config from env on NEW SESSION
    # - 새 프로젝트/보고서 시작 직후(state가 초기화된 직후)에 연구 루프용 설정을 주입
    # state.setdefault("agent_role", (state.get("agent_role") or os.getenv("BLOCKAGI_AGENT_ROLE", "")).strip())
    # state.setdefault("iteration_count", int(state.get("iteration_count") or os.getenv("ITERATION_COUNT", "0")))

    if not state.get("research_objectives"):
        objs = []
        for i in range(1, 10):  # BLOCKAGI_OBJECTIVE_1..9 까지 흡수
            v = os.getenv(f"BLOCKAGI_OBJECTIVE_{i}", "")
            if v and v.strip():
                objs.append(v.strip())
        state["research_objectives"] = objs

    # ==========================================================
    # (1) 강제쿼리 최우선 라우팅
    #  - pending 태스크가 있어도 무조건 web_search_agent로 보냄
    #  - 중복 task 생성만 방지
    # ==========================================================
    try:
        fqs = extract_forced_queries_from_messages(messages, lookback=15)
    except Exception:
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
        messages.append(AIMessage(msg))
        print(msg)
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
        if not has_pending(tasks, "vector_search_agent"):
            tasks.append(Task(agent="vector_search_agent", done=False, description="사용자 질의 기반 RAG 검색을 수행한다.", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # 새 토픽
    m_new = re.search(
        r"(?:새\s*(?:보고서|프로젝트)\s*(?:작성)?|주제\s*(?:변경|바꿔)|new\s*(?:report|project)|switch\s*(?:topic|report))\s*[:：]?\s*(?P<title>.*)$",
        last_text,
        re.I,
    )
    if m_new:
        maybe_title = (m_new.group("title") or "").strip() or "untitled report"
        maybe_title = _sanitize_title(maybe_title)
        # state = start_new_topic(state, maybe_title, outline_fname=_pick_outline_filename(last_text))
        # # msg = f"[Supervisor] 새 주제 세션 시작: '{state['topic_title']}' (ns={state['chroma_ns']})"
        # # ★ f-string에서도 .get 사용 (기본값까지)
        # # [ANCHOR] seed research config from env on NEW SESSION
        # # - 새 프로젝트/보고서 시작 직후(state가 초기화된 직후)에 연구 루프용 설정을 주입
        # state.setdefault("agent_role", (state.get("agent_role") or os.getenv("BLOCKAGI_AGENT_ROLE", "")).strip())
        # state.setdefault("iteration_count", int(state.get("iteration_count") or os.getenv("ITERATION_COUNT", "0")))

        # if not state.get("research_objectives"):
        #     objs = []
        #     for i in range(1, 10):  # BLOCKAGI_OBJECTIVE_1..9 까지 흡수
        #         v = os.getenv(f"BLOCKAGI_OBJECTIVE_{i}", "")
        #         if v and v.strip():
        #             objs.append(v.strip())
        #     state["research_objectives"] = objs

        state = start_new_topic(state, maybe_title, outline_fname=_pick_outline_filename(last_text))

        # 새 세션 환경 주입은 유틸로 통일
        _ensure_agent_env(cast(MutableMapping[str, Any], state))
        _seed_objectives(cast(MutableMapping[str, Any], state))

        msg = (
            f"[Supervisor] 새 주제 세션 시작: "
            f"'{state.get('topic_title', '')}' "
            f"(ns={state.get('chroma_ns', '')})"
        )
        messages.append(AIMessage(msg))
        print(msg)
        # ★ description에도 .get 사용
        tasks.append(Task(
            agent="content_strategist",
            done=False,
            description=f"create_outline:{state.get('outline_fname', 'outline.md')}",
            done_at=""
        ))

        # ★ 반환 값 구성도 .get 사용
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

    # 연구 라운드 모드 부트스트랩
    if (
        (state.get("agent_role") or "").strip().lower() == "research analyst"
        and (state.get("research_objectives") or [])
        and not tasks
        and not (is_outline_display(last_text) or is_outline_creation(last_text))
    ):
        tasks.append(Task(agent="research_planner", done=False, description="plan_first", done_at=""))
        msg = "[Supervisor fast-path] 연구 라운드 모드 시작 → research_planner"
        messages.append(AIMessage(msg))
        print(msg)
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
        messages.append(AIMessage(f"[Supervisor fast-path] → communicator (show_outline:{fname})"))
        return {"messages": messages, "task_history": tasks}
    
    # [ANCHOR] research-mode preemption (insert BEFORE communicator fast-path)
    # def _is_research_mode(st) -> bool:
    #     role = (st.get("agent_role") or "").strip().lower() or os.getenv("BLOCKAGI_AGENT_ROLE","").strip().lower()
    #     has_objs = bool(st.get("research_objectives"))
    #     max_iter = int(st.get("iteration_count") or os.getenv("ITERATION_COUNT","0"))
    #     return (role == "research analyst") and has_objs and (max_iter > 0)
    
    def _is_research_mode(st: Mapping[str, Any]) -> bool:
        role_src = (st.get("agent_role") or _env_str("BLOCKAGI_AGENT_ROLE", "")).strip().lower()
        has_objs = bool(st.get("research_objectives"))
        # coerce_int는 Any -> int 안전 변환
        max_iter = coerce_int(st.get("iteration_count", os.getenv("ITERATION_COUNT")), default=0)
        return (role_src == "research analyst") and has_objs and (max_iter > 0)

    if _is_research_mode(state):
        # 연구 파이프라인이 아직 안 올라가 있으면 planner를 먼저 올림
        no_research_pending = not any(
            has_pending(state.get("task_history", []), a)
            for a in ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")
        )
        if no_research_pending:
            # communicator가 대기 중이면 자동 종료 처리(연구 우선)
            for t in state.get("task_history", []):
                if (not t.done) and t.agent == "communicator":
                    t.done = True
                    t.done_at = _now_str()
                    t.description = (t.description or "") + " [auto-closed: start research loop]"
            tasks = state.get("task_history", [])
            tasks.append(Task(agent="research_planner", done=False, description="plan: auto", done_at=""))
            return {"messages": state.get("messages", []), "task_history": tasks}


    # 목차 생성 pending 우선 처리
    pending_cs = next((t for t in reversed(tasks) if (not t.done) and t.agent == "content_strategist"), None)
    if pending_cs and not (is_outline_display(last_text) or is_outline_creation(last_text)):
        print("[Supervisor priority] content_strategist pending → 우선 진행")
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
        messages.append(AIMessage(msg))
        print(msg)
        return {"messages": messages, "task_history": tasks}

    if is_outline_display(last_text):
        fname = _pick_outline_filename(last_text)
        tasks.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))
        msg = f"[Supervisor fast-path] → communicator (show_outline:{fname})"
        messages.append(AIMessage(msg))
        print(msg)
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
        messages.append(AIMessage(msg))
        print(msg)
        tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        msg = "[Supervisor fast-path] → web_search_agent (RAG 업데이트 착수)"
        messages.append(AIMessage(msg))
        print(msg)
        return {"messages": messages, "task_history": tasks}

    # fast-path: write: ...
    target_from_line = extract_write_title(last_text)
    if target_from_line:
        refs = state.get("references", {})
        refs_empty = not (refs.get("docs") or [])
        has_pending_rag = any((not t.done) and t.agent in ("web_search_agent", "vector_search_agent") for t in tasks)
        if refs_empty or has_pending_rag:
            if not has_pending(tasks, "web_search_agent"):
                tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
            msg = "[Supervisor fast-path] 레퍼런스 비어있음/진행중 → RAG 먼저(web_search_agent)."
            messages.append(AIMessage(msg))
            print(msg)
            return {"messages": messages, "task_history": tasks}

        # writer_agent = WRITER_AGENT
        writer_agent: Literal["chapter_writer", "section_writer"] = (
            "section_writer" if DOC_MODE == "report" else "chapter_writer"
        )
        tasks.append(Task(agent=writer_agent, done=False, description=f"write: {target_from_line}", done_at=""))
        msg = f"[Supervisor fast-path] → {writer_agent} (mode={DOC_MODE}, write: {target_from_line})"
        messages.append(AIMessage(msg))
        print(msg)
        return {"messages": messages, "task_history": tasks}

    # 기존 미완료 태스크가 있으면 새로 만들지 않음
    pending_undone = next((t for t in reversed(tasks) if not t.done), None)
    if pending_undone:
        print(f"[Supervisor short-circuit] pending='{pending_undone.agent}' 유지 → 새 태스크 생성 생략")
        print("tasks tail =", [(getattr(t,'agent',None), getattr(t,'done',None), getattr(t,'description',None)) for t in tasks][-3:])
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
    
    res = supervisor_chain.invoke(
        {
            "messages": messages,
            "outline": get_topic_outline_text(state),
            "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
        }
    )

    # ✅ 런타임 방어 + 타입 좁히기
    if isinstance(res, Task):
        task: Task = res
    elif isinstance(res, dict):
        # dict로 왔을 때도 안전하게 Pydantic 모델로 승격
        task = Task(**res)
    else:
        raise TypeError(f"[Supervisor] Unexpected return type from supervisor_chain: {type(res)}")

    if task.agent in ("chapter_writer", "section_writer"):
        expected = WRITER_AGENT
        if task.agent != expected:
            msg = f"[Supervisor reconcile] DOC_MODE={DOC_MODE} → writer agent forced to {expected} (from {task.agent})"
            messages.append(AIMessage(msg))
            print(msg)
            task = Task(agent=expected, done=False, description=task.description, done_at="")

    tasks.append(task)
    msg = f"[Supervisor] {task}"
    messages.append(AIMessage(msg))
    print(msg)

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

    # ─────────────────────────────────────────
    # 0) 사용자 의도 기반 "단축 분기" (펜딩 검사보다 '먼저')
    last_human = next((m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), None)
    last_text = coerce_message_content_to_str(getattr(last_human, "content", ""))

    # 0-0) 새 주제 전환 → RAG 먼저(web_search_agent) if refs 비어있음, 아니면 communicator
    new_topic = extract_new_topic_title(last_text)
    if new_topic:
        ret = "web_search_agent" if refs_empty else "communicator"
        print(f"[supervisor_router] picked={ret}  (new_topic='{new_topic}', refs_empty={refs_empty}, "
              f"cs={_has('content_strategist')}, wr_pref={_has(preferred,'write:')}, wr_alt={_has(alt,'write:')}, "
              f"plan={_has('research_planner')}, synth={_has('research_synthesizer')}, "
              f"vec={_has('vector_search_agent')}, web={_has('web_search_agent')}, comm={_has('communicator')})")
        return ret

    # 0-1) 목차 '표시' 의도 → communicator
    if is_outline_display(last_text):
        ret = "communicator"
        print(f"[supervisor_router] picked={ret}  (show_outline, cs={_has('content_strategist')}, comm=True)")
        return ret

    # 0-2) 목차 '생성' 의도 → content_strategist
    if is_outline_creation(last_text):
        ret = "content_strategist"
        print(f"[supervisor_router] picked={ret}  (create_outline, cs=True)")
        return ret

    # 0-3) 강제 집필(write:) → DOC_MODE별 writer (refs 비면 RAG부터)
    write_title = extract_write_title(last_text)
    if write_title:
        if refs_empty:
            ret = "web_search_agent"
            print(f"[supervisor_router] picked={ret}  (fastpath write, title='{write_title}', refs_empty=True → RAG first)")
            return ret
        ret = preferred
        print(f"[supervisor_router] picked={ret}  (fastpath write, title='{write_title}', refs_empty=False)")
        return ret

    # ─────────────────────────────────────────
    # 1) 펜딩 우선순위 (writer > 연구플로우 > 수집/검색 > 커뮤니케이션)
    if _has("content_strategist"):
        ret = "content_strategist"
    elif _has(preferred, prefix="write:"):
        ret = preferred
    elif _has(alt, prefix="write:"):
        ret = alt
    elif _has("research_planner"):
        ret = "research_planner"
    elif _has("research_synthesizer"):
        ret = "research_synthesizer"
    elif _has("vector_search_agent"):
        ret = "vector_search_agent"
    elif _has("web_search_agent"):
        ret = "web_search_agent"
    elif _has("communicator"):
        ret = "communicator"
    else:
        # 기본값: QA형이면 벡터검색, 아니면 communicator
        ret = "vector_search_agent" if any(k in last_text for k in ("요약","정리","무엇","왜","비교","?")) else "communicator"

    print(f"[supervisor_router] picked={ret}  (cs={_has('content_strategist')}, wr_pref={_has(preferred,'write:')}, "
          f"wr_alt={_has(alt,'write:')}, plan={_has('research_planner')}, synth={_has('research_synthesizer')}, "
          f"vec={_has('vector_search_agent')}, web={_has('web_search_agent')}, comm={_has('communicator')})")
    return ret