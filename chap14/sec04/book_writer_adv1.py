from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers.string import StrOutputParser
from typing_extensions import TypedDict
from typing import List

from utils import save_state, get_outline, save_outline 
from models import Task
# from tools import retrieve, web_search, add_web_pages_json_to_chroma, save_chapter, next_unwritten_title
from tools_up import retrieve, web_search, add_web_pages_json_to_chroma, save_chapter, save_section, next_unwritten_title
from datetime import datetime
import os

from pathlib import Path
import os, re, shutil

def _preferred_writer_agent() -> str:
    return "section_writer" if _doc_mode() == "report" else "chapter_writer"

def _doc_mode() -> str:
    # Windows에서 set DOC_MODE="report" 형태를 대비해 양쪽 따옴표 제거
    return os.getenv("DOC_MODE", "book").strip('"').strip().lower()

def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^\w\-가-힣\s]", "", s)   # 한글/영문/숫자/밑줄/하이픈/공백만
    s = re.sub(r"\s+", "-", s)
    return s or "untitled"

def _compute_outdir(agent: str, base_dir: str) -> str:
    # agent가 section_writer 이거나 DOC_MODE=report면 sections, 아니면 chapters
    if agent == "section_writer" or _doc_mode() == "report":
        folder = "sections"
    else:
        folder = "chapters"
    outdir = os.path.join(base_dir, folder)
    os.makedirs(outdir, exist_ok=True)
    return outdir

def _save_md(agent: str, title: str, body: str, base_dir: str) -> str:
    fname = f"{_slugify(title)}.md"
    outdir = _compute_outdir(agent, base_dir)
    path  = os.path.join(outdir, fname)

    # 과거에 section_writer가 chapters에 잘못 쓴 파일이 있으면 옮겨줌(1회 보정)
    if agent == "section_writer":
        wrong = os.path.join(base_dir, "chapters", fname)
        if os.path.exists(wrong) and wrong != path:
            try:
                shutil.move(wrong, path)
            except Exception as e:
                print(f"[WARN] move failed {wrong} -> {path}: {e}")

    with open(path, "w", encoding="utf-8") as f:
        f.write(body or "")
    return path


# 현재 폴더 경로 찾기
# 랭그래프 이미지로 저장 및 추후 작업 결과 파일 저장 경로로 활용
filename = os.path.basename(__file__) # 현재 파일명 반환
absolute_path = os.path.abspath(__file__) # 현재 파일의 절대 경로 반환
current_path = os.path.dirname(absolute_path) # 현재 .py 파일이 있는 폴더 경로
 
DOC_MODE = os.getenv("DOC_MODE", "book").lower() # "book" 또는 "report" cmd에서 set DOC_MODE=report

from dotenv import load_dotenv
load_dotenv(r"D:\GPT_AGENT_2025_BOOK\chap02\.env")
api_key=os.getenv("OPENAI_API_KEY")

# 모델 초기화
llm = ChatOpenAI(model="gpt-4o") 

# 상태 정의
class State(TypedDict):
    messages: List[AnyMessage | str]
    task_history: List[Task]    
    references: dict

# ── helpers ───────────────────────────────────────────────────────────────────
def _is_outline_creation(text: str) -> bool:
    # 예: "목차 만들어줘", "책 목차 새로 작성", "report outline 생성"
    return bool(re.search(r"(목차|outline).*(만들|작성|새로|생성)", text, re.IGNORECASE))

def _is_outline_display(text: str) -> bool:
    # 예: "목차 보여줘", "책 목차 보여", "outline display"
    return bool(re.search(r"(목차|outline).*(보여|보기|출력|display|show)|^(책|ai).*(목차)$", text, re.IGNORECASE))

# def _pick_outline_filename(text: str) -> str:
#     t = (text or "").lower()
#     if re.search(r"(보고서|report)", t): 
#         return "outline_report.md"
#     if "책" in t or "book" in t:
#         return "outline_book.md"
#     return "outline.md"

def _preferred_writer_agent() -> str:
    # 전역 DOC_MODE가 있으면 그것을, 없으면 기본적으로 책=chapter_writer
    try:
        return "section_writer" if (DOC_MODE == "report") else "chapter_writer"
    except NameError:
        return "chapter_writer"

def _pick_outline_filename(user_text: str | None) -> str:
    text = (user_text or "").lower()
    # 너무 빡빡하게 잡지 말고, 키워드 조합만 봅니다.
    if re.search(r"ai.*책.*목차|책.*ai.*목차", text):
        return "outline_book.md"
    if re.search(r"(보고서|report).*(목차|outline)", text):
        return "outline_report.md"
    # 기본
    return "outline.md"

# ── supervisor 본체 ────────────────────────────────────────────────────────────
def supervisor(state: State):  # supervisor 에이전트
    print("\n\n============ SUPERVISOR ============")

    messages = state.get("messages", [])
    task_history = state.get("task_history", [])
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    last_text = (last_human.content if last_human else "") or ""

    # A) FAST-PATH: 목차 생성 요청 → content_strategist
    if _is_outline_creation(last_text):
        fname = _pick_outline_filename(last_text)
        task_history.append(Task(
            agent="content_strategist",
            done=False,
            description=f"create_outline:{fname}",
            done_at=""
        ))
        note = AIMessage(f"[Supervisor fast-path] → content_strategist (target={fname})")
        messages.append(note)
        print(note.content)
        return {"messages": messages, "task_history": task_history}

    # B) FAST-PATH: 목차 보여줘(조회) → communicator (+ 파일 힌트)
    if _is_outline_display(last_text):
        fname = _pick_outline_filename(last_text)
        task_history.append(Task(
            agent="communicator",
            done=False,
            description=f"show_outline:{fname}",
            done_at=""
        ))
        note = AIMessage(f"[Supervisor fast-path] → communicator (show_outline:{fname})")
        messages.append(note)
        print(note.content)
        return {"messages": messages, "task_history": task_history}
    
    # B-2) FAST-PATH: 최신 자료를 RAG에 넣어달라(업데이트)
    # ✅ 수정 포인트: supervisor에서는 web_search_agent만 예약! (vector_search_agent는 web_search_agent가 완료 시점에 예약)
    _rag_re = r"(최신|업데이트|update|latest).*?(자료|리소스|레퍼런스|참고|sources|material).*?(rag|벡터|vector|임베딩|embedding|index|색인|chroma)"
    if re.search(_rag_re, last_text, flags=re.IGNORECASE):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # (선택) 끼어 있던 미완료 writer 태스크(챕터/섹션) 마무리 처리, 정리해서 충돌 방지
        for t in task_history:
            if (not t.done) and t.agent in ("chapter_writer", "section_writer"):
                t.done = True
                t.done_at = now
        messages.append(AIMessage("[Supervisor fast-path] 기존 writer 태스크 정리 후 RAG 업데이트 시작."))

        # ✅ 여기서 'web_search_agent'만 예약하고,
        # vector_search_agent 예약은 web_search_agent가 완료 시점에 수행하도록 맡깁니다.
        task_history.append(Task(
            agent="web_search_agent",
            done=False,
            description="rag_update:auto",  # 힌트: 최신 자료 수집 + JSON 저장
            done_at=""
        ))
        note = AIMessage("[Supervisor fast-path] → web_search_agent (RAG 업데이트 착수: 다음 단계는 web_search_agent가 예약)")
        messages.append(note)
        print(note.content)
        return {"messages": messages, "task_history": task_history}

    # C) FAST-PATH: write: ... / 작성: ... / 집필: ... → writer 바로 생성
    m = re.search(r"^\s*(write|작성|집필)\s*[:：]\s*(.+)$", last_text.strip(), flags=re.IGNORECASE)
    if m:
        target = m.group(2).strip().strip(" '\"“”‘’")
        if target:
            # ---------- 선택 가드: 레퍼런스가 비었거나, RAG 태스크가 진행/대기 중이면 RAG 먼저 ----------
            refs = state.get("references", {})
            refs_empty = not (refs.get("docs") or [])
            has_pending_rag = any((not t.done) and t.agent in ("web_search_agent", "vector_search_agent")
                                  for t in task_history)
            if refs_empty or has_pending_rag:
                # 중복 예약 방지: 이미 web_search_agent가 펜딩이면 추가하지 않음
                already_queued_web = any((not t.done) and t.agent == "web_search_agent" for t in task_history)
                if not already_queued_web:
                    task_history.append(Task(
                        agent="web_search_agent",
                        done=False,
                        description="rag_update:auto",
                        done_at=""
                    ))
                note = AIMessage("[Supervisor fast-path] 레퍼런스 비어있음/진행중 → RAG 먼저 수행(web_search_agent 예약).")
                messages.append(note)
                print(note.content)
                return {"messages": messages, "task_history": task_history}
            
            # ---------- 가드 통과: 바로 집필 ----------
            agent = _preferred_writer_agent()
            quick_task = Task(agent=agent, done=False, description=f"write: {target}", done_at="")
            task_history.append(quick_task)
            note = AIMessage(f"[Supervisor fast-path] → {agent} (write: {target})")
            messages.append(note)
            print(note.content)
            return {"messages": messages, "task_history": task_history}

    # D) 일반 경로: LLM에게 라우팅 결정 맡기기
    supervisor_system_prompt = PromptTemplate.from_template(
        """
        너는 AI 팀의 supervisor로서 팀의 작업을 관리한다.
        최종 목표(책/보고서 집필)에 맞춰 지금 당장 수행할 agent를 결정하라.

        사용 가능한 agent:
        - content_strategist: 전체 목차(outline) 작성/수정
        - communicator: 진행상황 보고/사용자 질의 응대
        - web_search_agent: 웹 검색을 통한 참고자료 수집
        - vector_search_agent: 벡터 DB 검색(RAG)을 통한 참고자료 수집
        - chapter_writer: (책 모드) 확정 목차의 특정 항목 본문 초안
        - section_writer: (보고서 모드) 특정 섹션 본문 초안

        아래 정보를 참고해 단답으로 agent와 설명을 결정하라.
        ------------------------------------------
        previous_outline:
        {outline}
        ------------------------------------------
        messages:
        {messages}
        """
    )
    supervisor_chain = supervisor_system_prompt | llm.with_structured_output(Task)

    inputs = {"messages": messages, "outline": get_outline(current_path)}
    task = supervisor_chain.invoke(inputs)
    task_history.append(task)

    sup_msg = AIMessage(f"[Supervisor] {task}")
    messages.append(sup_msg)
    print(sup_msg.content)

    return {"messages": messages, "task_history": task_history}

# supervisor's route
def supervisor_router(state: State):
    task = state['task_history'][-1]
    # 가드를 쓰신다면:
    # allowed = {"content_strategist","communicator","vector_search_agent","web_search_agent","chapter_writer"}
    # return task.agent if task.agent in allowed else "communicator"
    return task.agent			

# 목차를 작성하는 노드(agent)
def content_strategist(state: State):
    print("\n\n============ CONTENT STRATEGIST ============")

    # 시스템 프롬프트 정의
    if DOC_MODE == "report":
        content_strategist_system_prompt = PromptTemplate.from_template(
            """
            너는 **보고서 기획자**다. 이전 대화와 참고자료를 바탕으로
            **실무 보고서 개요**를 작성하라.

            권장 구조(필요 시 조정):
            1. Executive Summary
            2. Background & Objectives
            3. Scope & Methodology
            4. Key Findings (데이터/사례 중심)
            5. Analysis & Insights
            6. Recommendations (Action Items)
            7. Risks & Mitigations
            8. Implementation Plan & Timeline
            9. Appendix (Data, Glossary, References)

            --------------------------------
            - 이전 대화: {messages}
            - 기존 개요: {outline}
            - 참고 자료: {references}
            """
        )
    else:
        # (기존 책 목차용 프롬프트 유지)
        content_strategist_system_prompt = PromptTemplate.from_template(
            """
            너는 책을 쓰는 AI팀의 콘텐츠 전략가(Content Strategist)로서,
            이전 대화 내용을 바탕으로 사용자의 요구사항을 분석하고, AI팀이 쓸 책의 세부 목차를 결정한다.

            지난 목차가 있다면 그 버전을 사용자의 요구에 맞게 수정하고, 없다면 새로운 목차를 제안한다.
            목차를 작성하는데 필요한 정보는 "참고 자료"에 있으므로 활용한다. 

            --------------------------------
            - 지난 목차: {outline}
            --------------------------------
            - 이전 대화 내용: {messages}
            --------------------------------
            - 참고 자료: {references}
            """
        )

    # 시스템 프롬프트와 모델을 연결
    content_strategist_chain = content_strategist_system_prompt | llm | StrOutputParser()

    messages = state["messages"]        # 상태에서 메시지를 가져옴
    # outline = get_outline(current_path) # 저장된 목차를 가져옴

    inputs = {
        "messages": messages,
        "outline": get_outline(current_path), 
        "references": state.get("references", {"queries": [], "docs": []})
    }

    # 목차 작성
    gathered = ''
    for chunk in content_strategist_chain.stream(inputs):
        gathered += chunk
        print(chunk, end='')

    print()

    # ✅ 사용자 최신 메시지 기준으로 파일명 결정
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    user_text = last_human.content if last_human else ""
    fname = _pick_outline_filename(user_text)

    # ✅ 요청 파일명 + 기본 파일명 동시 저장 (호환성)
    save_outline(current_path, gathered, filename=fname)
    save_outline(current_path, gathered, filename="outline.md")

    # save_outline(current_path, gathered) # 목차 저장

    # 메시지 추가
    # 메시지/태스크 처리 동일
    # messages.append(AIMessage(f"[Content Strategist] 목차 작성 완료 → {fname} / outline.md 저장"))    
    content_strategist_message = f"[Content Strategist] 목차 작성 완료 → {fname} / outline.md 저장"
    print(content_strategist_message)
    messages.append(AIMessage(content_strategist_message))

    task_history = state.get("task_history", []) # task_history 가져오기
    # 최근 task 작업완료(done) 처리하기
    if task_history[-1].agent != "content_strategist": 
        raise ValueError(f"Content Strategist가 아닌 agent가 목차 작성을 시도하고 있습니다.\n {task_history[-1]}")
    
    task_history[-1].done = True
    task_history[-1].done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 다음 작업이 communicator로 사용자와 대화하는 것이므로 새 작업 추가 
    new_task = Task(
        agent="communicator",
        done=False,
        description="AI팀의 진행상황을 사용자에게 보고하고, 사용자의 의견을 파악하기 위한 대화를 나눈다",
        done_at=""
    )
    task_history.append(new_task)

    print(new_task)

    # 현재 state를 업데이트한다. 
    return {
        "messages": messages,
        "task_history": task_history
    }

def web_search_agent(state: State):  # ①
    print("\n\n============ WEB SEARCH AGENT ============")

    # 작업 이력 & pending 찾기 (마지막 요소만 신뢰하지 않음)
    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "web_search_agent"), None)
    if pending is None:
        raise ValueError(f"web_search_agent pending task가 없습니다. 현재 마지막 태스크: {tasks[-1]}")

    # ③ 시스템 프롬프트 정의 (LLM 주도형 검색 계획 수립에 사용)
    web_search_system_prompt = PromptTemplate.from_template(
        """
        너는 다른 AI Agent 들이 수행한 작업을 바탕으로,
        목차(outline)나 보고서에 필요한 정보를 웹에서 수집하는 Web Search Agent다.

        - 'rag_update:auto'면, 초보자도 이해할 수 있게 **핵심 주제 3~7개**의 검색 질의를 설계하라.
          (예: "AI definition 2025 overview", "history of AI timeline", "ML vs DL differences 2025" 등)
        - 그 외에는 사용자가 원하는 미션을 달성할 수 있도록 구체적 질의를 만든다.
        - 결과는 `web_search` 툴 호출로 실행하라.

        [검색 목적/미션]
        {mission}

        --------------------------------
        [과거 검색/레퍼런스 상태]
        {references}
        --------------------------------
        [이전 대화]
        {messages}
        --------------------------------
        [현재 목차/개요]
        {outline}
        --------------------------------
        [현재 시각]
        {current_time}
        """
    )

    # ④ 기존 대화/레퍼런스/목차
    messages = state.get("messages", [])
    references = state.get("references", {"queries": [], "docs": []})
    outline_text = get_outline(current_path)

    mission = (pending.description or "").strip()
    inputs = {
        "mission": mission,
        "references": references,
        "messages": messages,
        "outline": outline_text,
        "current_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    # ⑥ LLM+툴 결합
    llm_with_web = llm.bind_tools([web_search])
    web_search_chain = web_search_system_prompt | llm_with_web

    # ⑧ 웹 검색 계획 생성 (필요 시 자동 질의 생성)
    # rag_update:auto가 명시되면, LLM이 툴콜 못해도 안전하게 fallback 질의 사용
    auto_mode = "rag_update:auto" in mission.lower()

    search_plans = web_search_chain.invoke(inputs)
    tool_calls = getattr(search_plans, "tool_calls", []) or []

    # ⑨ 어떤 내용을 검색했는지 누적
    queries: list[str] = []
    json_paths: list[str] = []

    # 🔸 Fallback: 툴콜이 전혀 없고 auto_mode면 간단한 기본 질의 세트 구성
    def _fallback_auto_queries():
        base = [
            "AI definition and importance 2025 overview",
            "History of artificial intelligence timeline",
            "Machine learning vs deep learning differences 2025",
            "Natural language processing key applications",
            "Computer vision applications overview",
        ]
        # 목차가 있으면 상위 항목 몇 개를 붙여 확장
        extra = []
        if outline_text:
            for line in outline_text.splitlines():
                line = line.strip("- ").strip()
                if not line:
                    continue
                if len(extra) >= 2:
                    break
                # 너무 긴 줄은 자르고 연도 키워드 추가
                extra.append(f"{line[:40]} 2025 overview")
        return base + extra

    if not tool_calls and auto_mode:
        # 툴콜이 없을 때 자동 질의 사용
        tool_calls = [{"name": "web_search", "args": {"query": q}} for q in _fallback_auto_queries()]

    # ⑩ 계획에 따라 실제 검색 실행 → JSON 저장 → 곧바로 Chroma 적재
    #     - tools.web_search()는 (results, json_path)를 반환
    #     - add_web_pages_json_to_chroma(json_path)로 바로 적재
    for tc in tool_calls:
        if not isinstance(tc, dict) or tc.get("name") != "web_search":
            # 혹시 다른 툴콜이 섞여 있어도 무시
            continue
        args = tc.get("args") or {}
        q = args.get("query", "").strip()
        if not q:
            continue

        print("-------- web search --------", tc)
        queries.append(q)

        try:
            _, json_path = web_search.invoke(args)  # (results, json_path)
            print("json_path:", json_path)
            json_paths.append(json_path)
        except Exception as e:
            print(f"[WARN] web_search.invoke 실패: {e}")
            continue

        # JSON → Chroma 적재 (중복 URL 자동 필터링 로직은 tools.py의 documents_to_chroma에 있음)
        try:
            add_web_pages_json_to_chroma(json_path)
        except Exception as e:
            print(f"[WARN] add_web_pages_json_to_chroma 실패: {e}")

    # 참고: 방금 수집한 JSON을 references에 미리 미리 요약 주입(선택)
    #       writer 프롬프트가 'references.docs'를 간단히 미리보기로 쓰므로 일부만 가볍게 추가
    #       (문서 전체를 다 넣으면 state가 너무 커질 수 있으니 preview만)
    new_docs_preview = []
    if 'web_page_json_to_documents' in globals():
        try:
            for p in json_paths[:3]:
                for d in web_page_json_to_documents(p)[:5]:
                    meta = getattr(d, "metadata", {}) or {}
                    d_stub = Document(page_content=d.page_content[:500],
                                    metadata={"source": meta.get("source", "unknown")})
                    new_docs_preview.append(d_stub)
        except Exception as e:
            print(f"[WARN] web_page_json_to_documents 미리보기 생성 실패: {e}")
    else:
        print("[INFO] web_page_json_to_documents 미정의: 미리보기 스킵")

    # references 병합 저장
    merged_refs = {
        "queries": (references.get("queries", []) or []) + queries,
        "docs":   (references.get("docs", []) or []) + new_docs_preview
    }
    state["references"] = merged_refs  # 이후 vector/section/chapter_writer가 그대로 사용

    # ⑪ 현재 태스크 완료 처리
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    pending.done = True
    pending.done_at = now

    # ⑪-추가) Supervisor가 이미 vector_search_agent를 예약했는지 확인해 중복 방지
    has_pending_vector = any((not t.done) and t.agent == "vector_search_agent" for t in tasks)
    if not has_pending_vector:
        desc = "RAG 인덱싱을 위한 벡터 검색/검증을 수행한다. "
        if queries:
            desc += f"queries={queries} "
        if json_paths:
            desc += f"json_paths={json_paths}"
        tasks.append(Task(
            agent="vector_search_agent",
            done=False,
            description=desc,
            done_at=""
        ))

    # ⑫ 피드백 메시지
    log_msg = f"[WEB SEARCH AGENT] 검색 완료({len(queries)}건). JSON 저장 및 Chroma 적재 완료."
    if json_paths:
        log_msg += f" (예: {json_paths[0]})"
    messages.append(AIMessage(log_msg))

    # ⑬ state 업데이트
    return {
        "messages": messages,
        "task_history": tasks,
        "references": state.get("references", merged_refs)  # 안전하게 동기화
    }

def vector_search_agent(state: State):
    print("\n\n============ VECTOR SEARCH AGENT ============")
    
    tasks = state.get("task_history", [])
    task = tasks[-1]
    if task.agent != "vector_search_agent":
        raise ValueError(f"Vector Search Agent가 아닌 agent가 Vector Search Agent를 시도하고 있습니다.\n {task}")

    vector_search_system_prompt = PromptTemplate.from_template(
        """
        너는 다른 AI Agent 들이 수행한 작업을 바탕으로, 
        목차(outline) 작성에 필요한 정보를 벡터 검색을 통해 찾아내는 Agent이다.

        현재 목차(outline)을 작성하는데 필요한 정보를 확보하기 위해, 
        다음 내용을 활용해 적절한 벡터 검색을 수행하라. 

        - 검색 목적: {mission}
        --------------------------------
        - 과거 검색 내용: {references}
        --------------------------------
        - 이전 대화 내용: {messages}
        --------------------------------
        - 목차(outline): {outline}
        """
    )

    # inputs 설정
    mission = task.description
    references = state.get("references", {"queries": [], "docs": []})
    messages = state["messages"]
    outline = get_outline(current_path)

    inputs = {
        "mission": mission,
        "references": references,
        "messages": messages,
        "outline": outline
    }

    # LLM과 벡터 검색 모델 연결
    llm_with_retriever = llm.bind_tools([retrieve]) 
    vector_search_chain = vector_search_system_prompt | llm_with_retriever

    # (A) LLM이 만든 검색 계획 실행
    search_plans = vector_search_chain.invoke(inputs)

    # 기존에 references에 이미 있던 질의(웹 검색 등이 남긴 것)를 스냅샷
    preexisting_queries = list(references.get("queries", []))

    ran_queries = []  # 이번 턴에 실제로 retrieve를 실행한 질의들 로그용

    # LLM이 제시한 tool_calls 수행
    for tool_call in getattr(search_plans, "tool_calls", []) or []:
        print('-----------------------------------', tool_call)
        args = tool_call.get("args", {})
        query = (args.get("query") or "").strip()
        if not query:
            continue
        try:
            retrieved_docs = retrieve.invoke({"query": query})
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{query}'): {e}")
            continue

        # 결과 담아 두기
        references.setdefault("queries", []).append(query)
        references.setdefault("docs", []).extend(retrieved_docs)
        ran_queries.append(query)
    
    # (B) references["queries"]에 이미 있던 질의들도 반드시 RAG로 실행
    #     (단, 위에서 이미 실행한 질의는 중복 실행 방지)
    for q in preexisting_queries:
        if not q or q in ran_queries:
            continue
        print('-----------------------------------', {"name": "retrieve", "args": {"query": q}})
        try:
            retrieved_docs = retrieve.invoke({"query": q})
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{q}'): {e}")
            continue
        references.setdefault("docs", []).extend(retrieved_docs)
        ran_queries.append(q)

    # (C) queries / docs 중복 정리
    # 질의 중복 제거(순서 보존)
    references["queries"] = list(dict.fromkeys(references.get("queries", [])))

    # 문서 중복 제거(page_content 기준)
    unique_docs = []
    unique_page_contents = set()
    for doc in references.get("docs", []):
        content = (getattr(doc, "page_content", "") or "").strip()
        if content and content not in unique_page_contents:
            unique_docs.append(doc)
            unique_page_contents.add(content)
    references["docs"] = unique_docs

    # 검색 결과 로그
    print('Queries:--------------------------')
    for q in references["queries"]:
        print(q)
    print('References:--------------------------')
    for doc in references["docs"]:
        print((getattr(doc, "page_content", "") or "")[:100])
        print('--------------------------')

    # ✅ 1) task 완료
    tasks[-1].done = True
    tasks[-1].done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # ✅ 2) 다음 집필 대상 결정 (헬퍼가 있으면 사용, 없으면 안전 기본값)
    try:
        from tools import next_unwritten_title
    except Exception:
        def next_unwritten_title(_):  # fallback
            return None

    outline_text = get_outline(current_path)
    doc_mode = str(globals().get("DOC_MODE", "book")).lower()
    default_title = "Executive Summary" if doc_mode == "report" else "1. AI의 개요"
    target_title = next_unwritten_title(outline_text) or default_title

    # ✅ 3) 모드에 맞는 writer 선택
    writer_agent = _preferred_writer_agent() # ← 모드 일관성 보장

    # ✅ 4) 동일 writer의 미완료 write 태스크가 이미 있으면 중복 추가 금지
    has_pending_writer = any(
        (not t.done) and t.agent == writer_agent and (t.description or "").lower().startswith("write")
        for t in tasks
    )
    if not has_pending_writer:
        tasks.append(Task(
            agent=writer_agent,
            done=False,
            description=f"write: {target_title}",
            done_at=""
        ))
        # 주의: communicator는 여기서 붙이지 않는다. 
        # (writer가 초안 저장 후 스스로 communicator 태스크를 append함)

    # 작업후기 메시지
    msg_str = f"[VECTOR SEARCH AGENT] 다음 질문에 대한 검색 완료: {references['queries']}"
    print(msg_str)
    messages.append(AIMessage(msg_str))

    # state 업데이트
    state["references"] = references
    return {
        "messages": messages,
        "task_history": tasks,
        "references": references
    }

def chapter_writer(state: State):
    print("\n\n============ CHAPTER WRITER ============")

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    
     # 최근 미완료 chapter_writer 태스크
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "chapter_writer"), None)
    if pending is None:
        print("[WARN] pending 'chapter_writer' task가 없습니다. edge 트리거로 건너뜁니다.")
        return {"messages": state.get("messages", []), "task_history": tasks}

    # # ✅ 최근 '미완료 chapter_writer' 태스크를 뒤에서부터 탐색 (tasks[-1] 의존 X)
    # pending = next(
    #     (t for t in reversed(tasks) if (not t.done) and t.agent == "chapter_writer"),
    #     None
    # )

    messages = state.get("messages", [])

     # ✅ 최근 사용자 발화가 '목차 생성'이면 위임하고 종료
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and _is_outline_creation(last_human.content):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        pending.done = True
        pending.done_at = now
        tasks.append(Task(agent="content_strategist", done=False, description="create_outline:auto", done_at=""))
        messages.append(AIMessage("[Chapter Writer] Outline 요청 감지 → content_strategist로 위임"))
        return {"messages": messages, "task_history": tasks}
    
    outline_text = get_outline(current_path)
    if not outline_text or outline_text.strip() == "":
        raise ValueError("아웃라인이 비어 있습니다. 먼저 content_strategist로 아웃라인을 생성/확정하세요.")

    # ✅ pending이 없어도 'edge 트리거'로 들어온 경우를 지원: desc_for_parse는 빈 문자열로
    desc_for_parse = (pending.description if pending else "") or ""

    # 1) 집필 대상 결정: description의 'write: ...' 우선 → 최근 사용자 메시지의 'write: ...' → 아직 미작성 자동 선택
    target_title = None

    # (a) description에서 write: ... 추출
    m = re.search(r"write[:：]\s*(.+)", desc_for_parse, flags=re.IGNORECASE)
    if m:
        target_title = m.group(1).strip().strip("'\"")

    # (b) 최근 사용자 메시지에서 write: ... 추출 (pending 없거나 desc에 없을 때)
    if not target_title:
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                m2 = re.search(r"write[:：]\s*(.+)", msg.content, flags=re.IGNORECASE)
                if m2:
                    target_title = m2.group(1).strip().strip("'\"")
                    break

    # (c) 그래도 없으면 아직 미작성 항목 자동 선택
    if not target_title:
        target_title = next_unwritten_title(outline_text)

    # (d) 타깃을 못 찾으면: 모든 항목 이미 작성 → 보고 예약 후 종료
    if not target_title:
        messages.append(AIMessage("[Chapter Writer] 모든 목차 항목의 초안이 이미 작성되었습니다."))
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if pending:
            pending.done = True
            pending.done_at = now
        else:
            # 기록 보존(선택): pending 없이 진입했음을 남김
            tasks.append(Task(agent="chapter_writer", done=True, description="(auto) nothing to write", done_at=now))
        tasks.append(Task(
            agent="communicator",
            done=False,
            description="집필 진행 완료를 사용자에게 보고하고, 편집/다듬기 단계로 넘어갈지 물어본다.",
            done_at=""
        ))
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target chapter: {target_title}")

    # 2) 참고자료 요약(길이 제한)
    references = state.get("references", {"queries": [], "docs": []})
    ref_queries = references.get("queries", [])[:5]
    ref_docs = references.get("docs", [])[:8]
    ref_preview = []
    for d in ref_docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or "unknown"
        snippet = (d.page_content or "")[:350].replace("\n", " ")
        ref_preview.append(f"- [{src}] {snippet}")
    ref_text = "Queries:\n" + "\n".join([f"- {q}" for q in ref_queries]) + "\n\nDocs:\n" + "\n".join(ref_preview)

    # 3) 집필 프롬프트(도서 톤)
    chapter_writer_prompt = PromptTemplate.from_template(
        """
        너는 초·중급 독자를 위한 **기술서 집필 에이전트**다.
        아래 '확정된 목차', '대화 맥락', '참고 자료 요약'을 바탕으로
        지정된 **챕터 본문 초안**을 작성하라.

        작성 규칙:
        - 대상 독자: 입문자 및 초중급 개발자 (친절하고 명확하게)
        - 구성: 개념 → 쉬운 비유 → 간단 예제(코드/명령어는 fenced code block) → 작은 실습 → "핵심 요약" 불릿
        - 분량: 1,200~2,000자
        - 과장 금지, 참고자료는 재서술(필요시 [출처] 표기)

        [작성 대상 챕터]
        {target_title}

        --------------------------------
        [확정된 목차]
        {outline}
        --------------------------------
        [참고 자료 요약]
        {references}
        --------------------------------
        [이전 대화]
        {messages}
        """
    )

    inputs = {
        "target_title": target_title,
        "outline": outline_text,
        "references": ref_text,
        "messages": messages,
    }

    # 4) 집필(스트리밍)
    writer_chain = chapter_writer_prompt | llm | StrOutputParser()
    gathered = ''
    print("\nAI\t: ", end='')
    for chunk in writer_chain.stream(inputs):
        print(chunk, end='')
        gathered += chunk
    print()

    # 5) 파일 저장 (chapters/ 폴더)
    out_path = save_chapter(target_title, gathered)
    messages.append(AIMessage(f"[Chapter Writer] '{target_title}' 초안 작성 완료 → {out_path}"))

    # 6) 태스크 완료 & 다음 단계
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if pending:
        pending.done = True
        pending.done_at = now
    else:
        # pending 없이 실제 집필 수행: 히스토리 보존용 완료 기록 (선택)
        tasks.append(Task(agent="chapter_writer", done=True, description=f"write: {target_title}", done_at=now))

    tasks.append(Task(
        agent="communicator",
        done=False,
        description=f"'{target_title}' 초안 작성이 완료되었음을 사용자에게 보고하고, 다음 집필 대상(또는 수정/분량조정)을 물어본다.",
        done_at=""
    ))

    return {"messages": messages, "task_history": tasks}

def section_writer(state: State):
    print("\n\n============ SECTION WRITER ============")

    # --- [MINIMAL PATCH: local helpers] -------------------------------------
    import os, re, shutil
    def _doc_mode() -> str:
        # Windows에서 set DOC_MODE="report" 형태 대비: 양쪽 따옴표/공백 제거
        return os.getenv("DOC_MODE", "book").strip('"').strip().lower()

    def _slugify(title: str) -> str:
        s = (title or "").strip().lower()
        s = re.sub(r"[^\w\-가-힣\s]", "", s)   # 한글/영문/숫자/밑줄/하이픈/공백만 허용
        s = re.sub(r"\s+", "-", s)
        return s or "untitled"

    def _compute_outdir_for_section_writer(base_dir: str) -> str:
        # 섹션 라이터는 항상 sections/로 저장 (report/book 무관)
        outdir = os.path.join(base_dir, "sections")
        os.makedirs(outdir, exist_ok=True)
        return outdir

    def _save_md_section(title: str, body: str, base_dir: str) -> str:
        """section_writer 전용 저장: sections/에 저장, 과거 chapters/ 오저장본 자동 이동"""
        fname = f"{_slugify(title)}.md"
        outdir = _compute_outdir_for_section_writer(base_dir)
        correct_path = os.path.join(outdir, fname)

        # 과거 잘못 chapters/ 에 저장된 동일 파일명이 있으면 1회 이동 보정
        wrong_path = os.path.join(base_dir, "chapters", fname)
        if os.path.exists(wrong_path) and wrong_path != correct_path:
            try:
                shutil.move(wrong_path, correct_path)
                print(f"[Section Writer] moved (chapters → sections): {wrong_path} -> {correct_path}")
            except Exception as e:
                print(f"[WARN] move failed {wrong_path} -> {correct_path}: {e}")

        # 최종 쓰기
        with open(correct_path, "w", encoding="utf-8") as f:
            f.write(body or "")
        return correct_path
    # ------------------------------------------------------------------------

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    # ✅ 최근 '미완료 section_writer' 태스크를 뒤에서부터 탐색
    pending = next(
        (t for t in reversed(tasks) if (not t.done) and t.agent == "section_writer"),
        None
    )
    if pending is None:
        print("[WARN] pending 'section_writer' task가 없습니다. edge 트리거로 진행합니다.")
        desc_for_parse = ""
    else:
        desc_for_parse = pending.description or ""

    messages = state.get("messages", [])
    outline_text = get_outline(current_path)
    if not outline_text or outline_text.strip() == "":
        raise ValueError("아웃라인이 비어 있습니다. 먼저 보고서 개요(목차)를 만드세요.")

    # 1) 집필 타깃
    target_title = None
    m = re.search(r"write[:：]\s*(.+)", desc_for_parse, flags=re.IGNORECASE)
    if m:
        target_title = m.group(1).strip()
    
    # 🔧 추가: pending.description에 없으면, 최근 사용자 메시지에서 한 번 더 찾아본다
    if not target_title:
        for msg in reversed(messages):
            # 최신 HumanMessage에서 write: ... 패턴 탐색
            if isinstance(msg, HumanMessage):
                m2 = re.search(r"write[:：]\s*(.+)", msg.content, flags=re.IGNORECASE)
                if m2:
                    target_title = m2.group(1).strip().strip("'\"")
                    break
    # 그래도 없으면 '아직 미작성 항목' 자동 선택
    if not target_title:
        target_title = next_unwritten_title(outline_text)
    if not target_title:
        messages.append(AIMessage("[Section Writer] 모든 섹션 초안이 이미 작성되었습니다."))
        # pending이 있으면 그 태스크만 완료 처리
        if pending:
            pending.done = True
            pending.done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 다음 대화 예약
        tasks.append(Task(
            agent="communicator",
            done=False,
            description="집필 진행 완료를 사용자에게 보고하고, 편집/수정 단계로 넘어갈지 물어본다.",
            done_at=""
        ))
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target section: {target_title}")

    # 2) 프롬프트(보고서 톤/형식)
    report_writer_prompt = PromptTemplate.from_template(
        """
        너는 기업/연구용 **보고서** 집필 에이전트다.
        아래 개요(목차), 대화 기록, 참고 자료 요약을 바탕으로
        지정된 섹션의 **실무 보고서 스타일** 초안을 작성하라.

        작성 규칙:
        - 대상 독자: 의사결정자 및 실무자
        - 구성: 배경/핵심 요점/근거(데이터·사례)/시사점
        - 표나 목록은 Markdown으로 간결히 표현
        - 길이: 800~1,500 단어 내외(요약 섹션은 400~800)
        - 마지막에 **Actionable Recommendations** 3~5개 불릿
        - 참고자료 내용 인용 시 과장 없이 재서술하고 출처명을 대괄호로 표기(예: [IBM], [Stanford HAI])

        [작성 대상 섹션 제목]
        {target_title}

        --------------------------------
        [보고서 개요(목차)]
        {outline}
        --------------------------------
        [참고 자료 요약]
        {references}
        --------------------------------
        [이전 대화]
        {messages}
        """
    )

    # 3) 참고자료 요약(기존 references를 요약해 주입)
    references = state.get("references", {"queries": [], "docs": []})
    ref_queries = references.get("queries", [])[:5]
    ref_docs = references.get("docs", [])[:8]
    ref_preview = []
    for d in ref_docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or "unknown"
        snippet = (d.page_content or "")[:350].replace("\n", " ")
        ref_preview.append(f"- [{src}] {snippet}")
    ref_text = "Queries:\n" + "\n".join([f"- {q}" for q in ref_queries]) + "\n\nDocs:\n" + "\n".join(ref_preview)

    inputs = {
        "target_title": target_title,
        "outline": outline_text,
        "references": ref_text,
        "messages": messages,
    }

    # 4) 집필(스트리밍)
    chain = report_writer_prompt | llm | StrOutputParser()
    gathered = ''
    print("\nAI\t: ", end='')
    for chunk in chain.stream(inputs):
        print(chunk, end='')
        gathered += chunk
    print()

    # 5) 파일 저장 (sections/ 폴더)   ←←← 기존 save_section() 제거, 보정 저장
    out_path = _save_md_section(target_title, gathered, base_dir=current_path)
    messages.append(AIMessage(f"[Section Writer] '{target_title}' 초안 작성 완료 → {out_path}"))
    # (선택) 커뮤니케이터가 실제 경로를 그대로 안내할 수 있게 남겨둠
    state["last_saved_path"] = out_path

    # 6) 태스크 상태 & 다음 단계
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if pending:
        pending.done = True
        pending.done_at = now
    else:
        # 기록 유지용(선택): pending이 없었지만 실제 집필이 수행됐음을 남김
        tasks.append(Task(
            agent="section_writer",
            done=True,
            description=f"write: {target_title}",
            done_at=now
        ))

    tasks.append(Task(
        agent="communicator",
        done=False,
        description=f"'{target_title}' 초안 작성 완료를 사용자에게 보고하고, 다음 섹션/수정 범위를 물어본다.",
        done_at=""
    ))

    return {"messages": messages, "task_history": tasks}


# 사용자와 대화할 노드(agent): communicator
import re, os  # ← 파일 상단에 없으면 추가
from langchain_core.messages import AIMessage

def communicator(state: State):
    print("\n\n============ COMMUNICATOR ============")

    messages = state.get("messages", [])
    tasks = state.get("task_history", [])

    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    # ✅ 최근 '미완료 communicator' 태스크 탐색(기존 유지)
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
    desc = (pending.description if pending else "") or ""

    # 기본 outline (fallback)
    fallback_outline = get_outline(current_path)

    # ❶ show_outline 요청 여부 판단 (기존 로직 + description에 show_outline:<fname> 지원)
    show_outline_req = False
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)

    explicit_fname = None
    # description에 show_outline:<fname> 이면 최우선
    mdesc = re.search(r"show_outline\s*:\s*([A-Za-z0-9_\-\.]+)", desc)
    if mdesc:
        explicit_fname = mdesc.group(1).strip()
        show_outline_req = True

    # 기존: desc에 show_outline가 있거나, 최근 사용자 입력에 '목차/outline'이 있으면
    if ("show_outline" in desc.lower()) or (last_human and re.search(r"(목차|차례|outline)", last_human.content, re.IGNORECASE)):
        show_outline_req = True

    if show_outline_req:
        # ✅ 어떤 outline 파일을 보여줄지 결정
        if explicit_fname:
            fname = explicit_fname
        else:
            user_text = last_human.content if last_human else ""
            # 사용자의 표현(책/보고서/ai)로부터 파일명 추정: outline_book.md / outline_report.md 등
            fname = _pick_outline_filename(user_text)

        # 👉 시도 순서: (1) fname 명시값 → (2) DOC_MODE 기본 → (3) outline.md → (4) 기본 get_outline
        tried = []
        outline_text = ""
        fname_used = None

        def try_read(name: str):
            """get_outline(current_path, name) 시도. 비어있으면 '' 반환."""
            try:
                return (get_outline(current_path, name) or "")
            except TypeError:
                # get_outline이 파일명 인자 없이만 정의된 경우 대비
                abs_path = os.path.join(current_path, name)
                if os.path.exists(abs_path):
                    try:
                        with open(abs_path, "r", encoding="utf-8") as f:
                            return (f.read() or "")
                    except Exception:
                        return ""
                return ""

        # (1) 명시 fname
        if fname:
            tried.append(fname)
            txt = try_read(fname)
            if txt.strip():
                outline_text, fname_used = txt, fname

        # (2) DOC_MODE 기본 파일
        if not outline_text:
            mode = os.getenv("DOC_MODE", "book").strip('"').lower()
            default_by_mode = "outline_report.md" if mode == "report" else "outline_book.md"
            if default_by_mode not in tried:
                tried.append(default_by_mode)
            txt = try_read(default_by_mode)
            if txt.strip():
                outline_text, fname_used = txt, default_by_mode

        # (3) outline.md
        if not outline_text:
            if "outline.md" not in tried:
                tried.append("outline.md")
            txt = try_read("outline.md")
            if txt.strip():
                outline_text, fname_used = txt, "outline.md"

        # (4) 최종 폴백: 기존 get_outline(current_path)
        if not outline_text:
            # 없으면 “없음 안내”를 기본으로…
            asked = explicit_fname or fname or "(not specified)"
            noti = f"(저장된 목차가 없습니다: {asked})"
            # …가능하면 폴백도 함께 제시
            fallback = (fallback_outline or "").strip()
            if fallback:
                outline_text = noti + "\n\n[참고] 폴백 목차를 대신 보여드립니다.\n\n" + fallback
                fname_used = "auto(fallback)"
            else:
                outline_text = noti
                fname_used = asked

            outline_text = (fallback_outline or "").strip()
            fname_used = fname_used or "(auto)"

        # ✅ 출력
        title = f"## 현재 목차 ({fname_used})" if fname_used else "## 현재 목차"
        content = f"{title}\n\n{outline_text}"
       
        print("\nAI\t:\n" + content)
        messages.append(AIMessage(content))

        # 태스크 완료 처리
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if pending:
            pending.done = True
            pending.done_at = now

        # 다음 대화 예약(기존 UX 유지)
        tasks.append(Task(
            agent="communicator",
            done=False,
            description="목차를 보여준 뒤, 다음 집필 대상이나 수정 요청을 물어본다.",
            done_at=""
        ))
        return {"messages": messages, "task_history": tasks}

    # ❷ show_outline가 아니면 기존 LLM 스트리밍 로직 유지 (최소 변경)
    communicator_system_prompt = PromptTemplate.from_template(
        """
        너는 책을 쓰는 AI팀의 커뮤니케이터로서, 
        AI팀의 진행상황을 사용자에게 보고하고, 사용자의 의견을 파악하기 위한 대화를 나눈다. 

        사용자도 outline(목차)을 이미 보고 있으므로, 다시 출력할 필요는 없다.
        outline: {outline} 
        --------------------------------
        messages: {messages}
        """
    )
    system_chain = communicator_system_prompt | llm

    inputs = {
        "messages": messages,          # ← 이미 위에서 가져온 messages 사용
        "outline": fallback_outline    # ← 기본 outline을 넣되, 위 분기에서는 직접 출력함
    }

    gathered = None
    print('\nAI\t: ', end='')
    for chunk in system_chain.stream(inputs):
        print(chunk.content, end='')
        gathered = chunk if gathered is None else (gathered + chunk)
    
     # === [추가] 저장 경로 한 줄만 덧붙이기 ===
    # 최근 완료된 writer 태스크가 있고, 메시지에 아직 경로가 없다면 한 줄 안내를 추가
    try:
        has_path_already = ("chapters\\" in gathered.content) or ("sections\\" in gathered.content)
        if not has_path_already:
            last_writer = next((t for t in reversed(tasks)
                                if t.done and t.agent in ("chapter_writer", "section_writer")
                                and (t.description or "").lower().startswith("write")), None)
            if last_writer:
                m = re.search(r"write\s*[:：]\s*(.+)$", last_writer.description, flags=re.IGNORECASE)
                title = (m.group(1).strip() if m else "")
                if title:
                    mode = (globals().get("DOC_MODE") or os.getenv("DOC_MODE", "book")).strip('"').lower()
                    base_dir = "sections" if mode == "report" else "chapters"
                    # 단순 슬러그: 공백 → '-', 위험문자 제거
                    fname = re.sub(r"[\\/:*?\"<>|]", "-", title)
                    fname = re.sub(r"\s+", "-", fname).strip("-") + ".md"
                    abs_path = os.path.join(current_path, base_dir, fname)
                    gathered = AIMessage(gathered.content + f"\n\n(참고: 최근 초안은 `{abs_path}` 에 저장되었습니다.)")
    except Exception as _:
        pass
    # === [추가] 끝 ===

    messages.append(gathered)

    # ✅ 마지막 에러 유발 체크 제거하고, pending만 안전하게 완료 처리
    if pending:
        pending.done = True
        pending.done_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return {"messages": messages, "task_history": tasks}

# 상태 그래프 정의
graph_builder = StateGraph(State)

# Nodes
graph_builder.add_node("supervisor", supervisor)     
graph_builder.add_node("communicator", communicator)
graph_builder.add_node("content_strategist", content_strategist)
graph_builder.add_node("vector_search_agent", vector_search_agent)
graph_builder.add_node("web_search_agent", web_search_agent)
# Nodes (기존 노드들과 함께)
graph_builder.add_node("chapter_writer", chapter_writer)
# Node
graph_builder.add_node("section_writer", section_writer)


# Edges
graph_builder.add_edge(START, "supervisor")
graph_builder.add_conditional_edges(
    "supervisor", 
    supervisor_router,
    {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "vector_search_agent": "vector_search_agent", 
        "web_search_agent": "web_search_agent",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer"
    }
)
graph_builder.add_edge("content_strategist", "communicator")
graph_builder.add_edge("web_search_agent", "vector_search_agent") #③
# (report 모드만 쓸 때)
# graph_builder.add_edge("vector_search_agent", "chapter_writer")  # ← 이 줄 주석/삭제
graph_builder.add_edge("vector_search_agent", "section_writer")    # 보고서 집필만 직행
# graph_builder.add_edge("vector_search_agent", "communicator") # 보고서 모드에서 제외. writer가 쓰는 동안 communicator가 먼저 실행되어 "이미 다 썼다"는 식의 메시지를 내거나, 스트리밍 출력이 서로 섞여 보일 수 있음.
# Edges (chapter_writer → communicator)
graph_builder.add_edge("chapter_writer", "communicator")
graph_builder.add_edge("section_writer", "communicator")
graph_builder.add_edge("communicator", END)

graph = graph_builder.compile()

# graph.get_graph().draw_mermaid_png(output_file_path=absolute_path.replace('.py', '.png'))

from playwright.sync_api import sync_playwright
from string import Template
import os

HTML_TMPL = Template("""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'default' });</script>
<style> body{margin:0;padding:16px;} </style>
</head>
<body><div class="mermaid">$mmd</div></body></html>
""")

def render_mermaid_with_playwright(mmd: str, out_path: str, width: int = 1600, height: int = 1000):
    html = HTML_TMPL.substitute(mmd=mmd)  # ← 중괄호 그대로, $mmd만 치환
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(300)
        page.locator(".mermaid").screenshot(path=out_path)
        browser.close()
    return out_path

# 호출부
mmd = graph.get_graph().draw_mermaid()
out_png = absolute_path.replace(".py", ".png")
render_mermaid_with_playwright(mmd, out_png)
print("Saved:", out_png)


# 상태 초기화
state = State(
    messages = [
        SystemMessage(
            f"""
        너희 AI들은 사용자의 요구에 맞는 책을 쓰는 작가팀이다.
        사용자가 사용하는 언어로 대화하라.

        현재시각은 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}이다.

        """
        )
    ],
    task_history=[]
)

while True:
    user_input = input("\nUser\t: ").strip()

    if user_input.lower() in ['exit', 'quit', 'q']:
        print("Goodbye!")
        break
    
    state["messages"].append(HumanMessage(user_input))
    state = graph.invoke(state)

    print('\n------------------------------------ MESSAGE COUNT\t', len(state["messages"]))

    save_state(current_path, state) # 현재 state 내용 저장