from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers.string import StrOutputParser
from typing_extensions import TypedDict
from typing import List

from utils import save_state, get_outline, save_outline
from models import Task
from tools_up import (
    retrieve,
    web_search,
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    next_unwritten_title,
)
from langchain_core.documents import Document
from datetime import datetime

# ==== helpers (single source of truth) =======================================
import os, re, shutil


def _doc_mode() -> str:
    # Windows set DOC_MODE="report" 대비 따옴표/공백 제거
    return (os.getenv("DOC_MODE", "book") or "book").strip('"').strip().lower()


def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^\w\-가-힣\s]", "", s)  # 한글/영문/숫자/밑줄/하이픈/공백만
    s = re.sub(r"\s+", "-", s)
    return s or "untitled"


def preferred_writer_agent() -> str:
    """report → section_writer, book → chapter_writer"""
    return "section_writer" if _doc_mode() == "report" else "chapter_writer"


def _extract_last_write_target(messages, tasks):
    # 1) 최근 HumanMessage에서 write: … 패턴
    for m in reversed(messages):
        try:
            if isinstance(m, HumanMessage):
                mm = re.search(
                    r"^\s*(write|작성|집필)\s*[:：]\s*(.+)$",
                    (m.content or "").strip(),
                    flags=re.IGNORECASE,
                )
                if mm:
                    return mm.group(2).strip().strip("'\"“”‘’")
        except Exception:
            pass
    # 2) 태스크 히스토리에서 가장 최근 write: … 설명
    for t in reversed(tasks):
        desc = (t.description or "")
        mm = re.search(
            r"^\s*(write|작성|집필)\s*[:：]\s*(.+)$", desc.strip(), flags=re.IGNORECASE
        )
        if mm:
            return mm.group(2).strip().strip("'\"“”‘’")
    return None


def save_md_draft(
    title: str,
    content: str,
    mode: str = None,
    base_dir: str = None,
    current_path: str = None,
):
    """
    sections/chapters에 마크다운 초안 저장 + 기존 파일 있으면 .bak 백업
    mode: 'report'면 sections, 그 외 chapters (base_dir가 주어지면 그 값 우선)
    """
    mode = (mode or os.getenv("DOC_MODE", "book")).strip('"').lower()
    base_dir = base_dir or ("sections" if mode == "report" else "chapters")
    current_path = current_path or os.getcwd()

    os.makedirs(os.path.join(current_path, base_dir), exist_ok=True)

    # 파일 경로 생성 (slug)
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers.string import StrOutputParser
from typing_extensions import TypedDict
from typing import List

from utils import save_state, get_outline, save_outline
from models import Task
from tools_up import (
    retrieve,
    web_search,
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    next_unwritten_title,
)
from langchain_core.documents import Document
from datetime import datetime

# ==== helpers (single source of truth) =======================================
import os, re, shutil


def _doc_mode() -> str:
    # Windows set DOC_MODE="report" 대비 따옴표/공백 제거
    return (os.getenv("DOC_MODE", "book") or "book").strip('"').strip().lower()


def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^\w\-가-힣\s]", "", s)  # 한글/영문/숫자/밑줄/하이픈/공백만
    s = re.sub(r"\s+", "-", s)
    return s or "untitled"


def preferred_writer_agent() -> str:
    """report → section_writer, book → chapter_writer"""
    return "section_writer" if _doc_mode() == "report" else "chapter_writer"


def _extract_last_write_target(messages, tasks):
    # 1) 최근 HumanMessage에서 write: … 패턴
    for m in reversed(messages):
        try:
            if isinstance(m, HumanMessage):
                mm = re.search(
                    r"^\s*(write|작성|집필)\s*[:：]\s*(.+)$",
                    (m.content or "").strip(),
                    flags=re.IGNORECASE,
                )
                if mm:
                    return mm.group(2).strip().strip("'\"“”‘’")
        except Exception:
            pass
    # 2) 태스크 히스토리에서 가장 최근 write: … 설명
    for t in reversed(tasks):
        desc = (t.description or "")
        mm = re.search(
            r"^\s*(write|작성|집필)\s*[:：]\s*(.+)$", desc.strip(), flags=re.IGNORECASE
        )
        if mm:
            return mm.group(2).strip().strip("'\"“”‘’")
    return None


def save_md_draft(
    title: str,
    content: str,
    mode: str = None,
    base_dir: str = None,
    current_path: str = None,
):
    """
    sections/chapters에 마크다운 초안 저장 + 기존 파일 있으면 .bak 백업
    mode: 'report'면 sections, 그 외 chapters (base_dir가 주어지면 그 값 우선)
    """
    mode = (mode or os.getenv("DOC_MODE", "book")).strip('"').lower()
    base_dir = base_dir or ("sections" if mode == "report" else "chapters")
    current_path = current_path or os.getcwd()

    os.makedirs(os.path.join(current_path, base_dir), exist_ok=True)

    # 파일 경로 생성 (slug)
    slug = re.sub(r'[\\/:*?"<>|]', "-", title)
    slug = re.sub(r"\s+", "-", slug).strip("-").lower()
    filename = f"{slug}.md"
    out_path = os.path.join(current_path, base_dir, filename)

    # 최소 변경 백업 로직 (이미 파일이 있으면 .bak로 보관)
    if os.path.exists(out_path):
        shutil.copy2(out_path, out_path + ".bak")

    # 실제 저장
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path


def pending_task(tasks, agent: str):
    return next((t for t in reversed(tasks) if (not t.done) and t.agent == agent), None)


def complete_task(t) -> None:
    if t and (not t.done):
        t.done = True
        t.done_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def merge_refs(
    existing: dict | None, new_queries: list[str] | None, new_docs: list | None
) -> dict:
    """
    기존 references(dict)와 새 질의/문서를 병합하고, 순서를 보존하면서 중복을 제거합니다.
    - queries: 공백 트리밍 후 순서 보존 중복 제거
    - docs   : (source/url + 본문 앞부분) 기반 시그니처로 중복 제거
    """
    import hashlib

    refs = existing or {}
    merged_q = list(refs.get("queries", []) or [])
    merged_d = list(refs.get("docs", []) or [])

    # 1) 새 항목 추가
    if new_queries:
        merged_q.extend([q for q in new_queries if q])
    if new_docs:
        merged_d.extend([d for d in new_docs if d is not None])

    # 2) queries 중복 제거(순서 보존)
    seen_q, dedup_q = set(), []
    for q in merged_q:
        if not q:
            continue
        qq = q.strip()
        if qq and qq not in seen_q:
            dedup_q.append(qq)
            seen_q.add(qq)

    # 3) docs 중복 제거(간결한 시그니처)
    def _doc_sig(d: Document) -> str:
        pc = (getattr(d, "page_content", "") or "")
        pc_head = " ".join(pc.split())[:500]  # 공백 압축 + 앞부분 500자
        meta = getattr(d, "metadata", {}) or {}
        src = (meta.get("source") or meta.get("url") or "").strip()
        return hashlib.sha1(f"{src}|{pc_head}".encode("utf-8", "ignore")).hexdigest()

    seen_sig, dedup_docs = set(), []
    for d in merged_d:
        try:
            sig = _doc_sig(d)
        except Exception:
            sig = repr(d)[:120]  # 실패 시 얕은 repr 폴백
        if sig not in seen_sig:
            dedup_docs.append(d)
            seen_sig.add(sig)

    return {"queries": dedup_q, "docs": dedup_docs}

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _refs_preview_text(state: State, max_q=5, max_docs=8, snippet_len=350) -> str:
    refs = state.get("references", {"queries": [], "docs": []})
    qs = refs.get("queries", [])[:max_q]
    docs = refs.get("docs", [])[:max_docs]
    lines = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or "unknown"
        snip = (d.page_content or "")[:snippet_len].replace("\n", " ")
        lines.append(f"- [{src}] {snip}")
    return "Queries:\n" + "\n".join([f"- {q}" for q in qs]) + ("\n\nDocs:\n" + "\n".join(lines) if lines else "")

# === end minimal helper ===


# 현재 폴더 경로 찾기
filename = os.path.basename(__file__)  # 현재 파일명 반환
absolute_path = os.path.abspath(__file__)  # 현재 파일의 절대 경로 반환
current_path = os.path.dirname(absolute_path)  # 현재 .py 파일이 있는 폴더 경로

from dotenv import load_dotenv, find_dotenv
dotenv_path = find_dotenv(usecwd=True)  # CWD 기준으로 위로 탐색 D:\GPT_AGENT_2025_BOOK\.env에 있으면 찾음.
if dotenv_path:
    load_dotenv(dotenv_path, override=False)
else:
    print("[INFO] .env 미발견: OS 환경변수만 사용합니다.")

api_key = os.getenv("OPENAI_API_KEY")

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
    return bool(
        re.search(
            r"(목차|outline).*(보여|보기|출력|display|show)|^(책|ai).*(목차)$",
            text,
            re.IGNORECASE,
        )
    )


def _pick_outline_filename(user_text: str | None) -> str:
    text = (user_text or "").lower()
    if re.search(r"ai.*책.*목차|책.*ai.*목차", text):
        return "outline_book.md"
    if re.search(r"(보고서|report).*(목차|outline)", text):
        return "outline_report.md"
    return "outline.md"


# ── supervisor 본체 ────────────────────────────────────────────────────────────
def supervisor(state: State):  # supervisor 에이전트
    print("\n\n============ SUPERVISOR ============")

    messages = state.get("messages", [])
    task_history = state.get("task_history", [])
    last_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )
    last_text = (last_human.content if last_human else "") or ""

    # A) FAST-PATH: 목차 생성 요청 → content_strategist
    if _is_outline_creation(last_text):
        fname = _pick_outline_filename(last_text)
        task_history.append(
            Task(
                agent="content_strategist",
                done=False,
                description=f"create_outline:{fname}",
                done_at="",
            )
        )
        note = AIMessage(
            f"[Supervisor fast-path] → content_strategist (target={fname})"
        )
        messages.append(note)
        print(note.content)
        return {"messages": messages, "task_history": task_history}

    # B) FAST-PATH: 목차 보여줘(조회) → communicator (+ 파일 힌트)
    if _is_outline_display(last_text):
        fname = _pick_outline_filename(last_text)
        task_history.append(
            Task(
                agent="communicator",
                done=False,
                description=f"show_outline:{fname}",
                done_at="",
            )
        )
        note = AIMessage(
            f"[Supervisor fast-path] → communicator (show_outline:{fname})"
        )
        messages.append(note)
        print(note.content)
        return {"messages": messages, "task_history": task_history}

    # B-2) FAST-PATH: 최신 자료를 RAG에 넣어달라(업데이트)
    _rag_re = r"(최신|업데이트|update|latest).*?(자료|리소스|레퍼런스|참고|sources|material).*?(rag|벡터|vector|임베딩|embedding|index|색인|chroma)"
    if re.search(_rag_re, last_text, flags=re.IGNORECASE):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for t in task_history:
            if (not t.done) and t.agent in ("chapter_writer", "section_writer"):
                t.done = True
                t.done_at = now
        messages.append(
            AIMessage("[Supervisor fast-path] 기존 writer 태스크 정리 후 RAG 업데이트 시작.")
        )

        task_history.append(
            Task(
                agent="web_search_agent",
                done=False,
                description="rag_update:auto",
                done_at="",
            )
        )
        note = AIMessage(
            "[Supervisor fast-path] → web_search_agent (RAG 업데이트 착수: 다음 단계는 web_search_agent가 예약)"
        )
        messages.append(note)
        print(note.content)
        return {"messages": messages, "task_history": task_history}

    # C) FAST-PATH: write: ... / 작성: ... / 집필: ... → DOC_MODE로 writer 확정
    m = re.search(
        r"^\s*(write|작성|집필)\s*[:：]\s*(.+)$", last_text.strip(), flags=re.IGNORECASE
    )
    if m:
        target = m.group(2).strip().strip(" '\"“”‘’")
        if target:
            refs = state.get("references", {})
            refs_empty = not (refs.get("docs") or [])
            has_pending_rag = any(
                (not t.done) and t.agent in ("web_search_agent", "vector_search_agent")
                for t in task_history
            )
            if refs_empty or has_pending_rag:
                already_queued_web = any(
                    (not t.done) and t.agent == "web_search_agent"
                    for t in task_history
                )
                if not already_queued_web:
                    task_history.append(
                        Task(
                            agent="web_search_agent",
                            done=False,
                            description="rag_update:auto",
                            done_at="",
                        )
                    )
                note = AIMessage(
                    "[Supervisor fast-path] 레퍼런스 비어있음/진행중 → RAG 먼저 수행(web_search_agent 예약)."
                )
                messages.append(note)
                print(note.content)
                return {"messages": messages, "task_history": task_history}

            mode = _doc_mode()
            writer_agent = preferred_writer_agent()

            quick_task = Task(
                agent=writer_agent, done=False, description=f"write: {target}", done_at=""
            )
            task_history.append(quick_task)
            note = AIMessage(
                f"[Supervisor fast-path] → {writer_agent} (mode={mode}, write: {target})"
            )
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

    # ★ 교정 로직: LLM이 고른 writer가 DOC_MODE와 다르면 강제 조정
    if task.agent in ("chapter_writer", "section_writer"):
        mode = _doc_mode()
        expected = preferred_writer_agent()
        if task.agent != expected:
            fix_note = AIMessage(
                f"[Supervisor reconcile] DOC_MODE={mode} → writer agent forced to {expected} (from {task.agent})"
            )
            messages.append(fix_note)
            print(fix_note.content)
            task = Task(
                agent=expected, done=False, description=task.description, done_at=""
            )

    task_history.append(task)
    sup_msg = AIMessage(f"[Supervisor] {task}")
    messages.append(sup_msg)
    print(sup_msg.content)

    return {"messages": messages, "task_history": task_history}


# supervisor's route
def supervisor_router(state: State):
    task = state["task_history"][-1]
    return task.agent


# 목차를 작성하는 노드(agent)
def content_strategist(state: State):
    print("\n\n============ CONTENT STRATEGIST ============")

    # 시스템 프롬프트 정의
    if _doc_mode() == "report":
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

    content_strategist_chain = content_strategist_system_prompt | llm | StrOutputParser()

    messages = state["messages"]

    inputs = {
        "messages": messages,
        "outline": get_outline(current_path),
        "references": state.get("references", {"queries": [], "docs": []}),
    }

    gathered = ""
    for chunk in content_strategist_chain.stream(inputs):
        gathered += chunk
        print(chunk, end="")
    print()

    # ✅ 사용자 최신 메시지 기준으로 파일명 결정
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    user_text = last_human.content if last_human else ""
    fname = _pick_outline_filename(user_text)

    # ✅ 요청 파일명 + 기본 파일명 동시 저장
    save_outline(current_path, gathered, filename=fname)
    save_outline(current_path, gathered, filename="outline.md")

    content_strategist_message = f"[Content Strategist] 목차 작성 완료 → {fname} / outline.md 저장"
    print(content_strategist_message)
    messages.append(AIMessage(content_strategist_message))

    task_history = state.get("task_history", [])
    if task_history[-1].agent != "content_strategist":
        raise ValueError(
            f"Content Strategist가 아닌 agent가 목차 작성을 시도하고 있습니다.\n {task_history[-1]}"
        )

    task_history[-1].done = True
    task_history[-1].done_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_task = Task(
        agent="communicator",
        done=False,
        description="AI팀의 진행상황을 사용자에게 보고하고, 사용자의 의견을 파악하기 위한 대화를 나눈다",
        done_at="",
    )
    task_history.append(new_task)

    print(new_task)

    return {"messages": messages, "task_history": task_history}


def web_search_agent(state: State):  # ①
    print("\n\n============ WEB SEARCH AGENT ============")

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next(
        (t for t in reversed(tasks) if (not t.done) and t.agent == "web_search_agent"),
        None,
    )
    if pending is None:
        raise ValueError(
            f"web_search_agent pending task가 없습니다. 현재 마지막 태스크: {tasks[-1]}"
        )

    web_search_system_prompt = PromptTemplate.from_template(
        """
        너는 다른 AI Agent 들이 수행한 작업을 바탕으로,
        목차(outline)나 보고서에 필요한 정보를 웹에서 수집하는 Web Search Agent다.

        - 'rag_update:auto'면, 초보자도 이해할 수 있게 **핵심 주제 3~7개**의 검색 질의를 설계하라.
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

    messages = state.get("messages", [])
    references = state.get("references", {"queries": [], "docs": []})
    outline_text = get_outline(current_path)

    mission = (pending.description or "").strip()
    inputs = {
        "mission": mission,
        "references": references,
        "messages": messages,
        "outline": outline_text,
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    llm_with_web = llm.bind_tools([web_search])
    web_search_chain = web_search_system_prompt | llm_with_web

    auto_mode = "rag_update:auto" in mission.lower()
    search_plans = web_search_chain.invoke(inputs)
    tool_calls = getattr(search_plans, "tool_calls", []) or []

    queries: list[str] = []
    json_paths: list[str] = []

    def _fallback_auto_queries():
        base = [
            "AI definition and importance 2025 overview",
            "History of artificial intelligence timeline",
            "Machine learning vs deep learning differences 2025",
            "Natural language processing key applications",
            "Computer vision applications overview",
        ]
        extra = []
        if outline_text:
            for line in outline_text.splitlines():
                line = line.strip("- ").strip()
                if not line:
                    continue
                if len(extra) >= 2:
                    break
                extra.append(f"{line[:40]} 2025 overview")
        return base + extra

    if not tool_calls and auto_mode:
        tool_calls = [{"name": "web_search", "args": {"query": q}} for q in _fallback_auto_queries()]

    for tc in tool_calls:
        if not isinstance(tc, dict) or tc.get("name") != "web_search":
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

        try:
            add_web_pages_json_to_chroma(json_path)
        except Exception as e:
            print(f"[WARN] add_web_pages_json_to_chroma 실패: {e}")

    # 미리보기 문서
    new_docs_preview = []
    try:
        for p in json_paths[:3]:
            docs = web_page_json_to_documents(p)[:5]
            for d in docs:
                meta = getattr(d, "metadata", {}) or {}
                src = meta.get("source") or meta.get("url") or "unknown"
                new_docs_preview.append(
                    Document(
                        page_content=(d.page_content or "")[:500],
                        metadata={"source": src},
                    )
                )
    except Exception as e:
        print(f"[WARN] web_page_json_to_documents 미리보기 생성 실패: {e}")

    state["references"] = merge_refs(references, queries, new_docs_preview)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pending.done = True
    pending.done_at = now

    has_pending_vector = any(
        (not t.done) and t.agent == "vector_search_agent" for t in tasks
    )
    if not has_pending_vector:
        desc = "RAG 인덱싱을 위한 벡터 검색/검증을 수행한다."
        if queries:
            desc += f" queries={queries}"
        if json_paths:
            desc += f" json_paths={json_paths}"
        tasks.append(
            Task(agent="vector_search_agent", done=False, description=desc, done_at="")
        )

    log_msg = f"[WEB SEARCH AGENT] 검색 완료({len(queries)}건). JSON 저장 및 Chroma 적재 완료."
    if json_paths:
        log_msg += f" (예: {json_paths[0]})"
    messages.append(AIMessage(log_msg))

    return {
        "messages": messages,
        "task_history": tasks,
        "references": state["references"],
    }


def vector_search_agent(state: State):
    print("\n\n============ VECTOR SEARCH AGENT ============")

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next(
        (t for t in reversed(tasks) if (not t.done) and t.agent == "vector_search_agent"),
        None,
    )
    if pending is None:
        last = tasks[-1]
        if (last.agent == "vector_search_agent") and (not last.done):
            pending = last
        else:
            raise ValueError(
                f"vector_search_agent pending task가 없습니다. 현재 마지막 태스크: {tasks[-1]}"
            )

    vector_search_system_prompt = PromptTemplate.from_template(
        """
        너는 다른 AI Agent 들이 수행한 작업을 바탕으로, 
        목차(outline) 작성에 필요한 정보를 벡터 검색을 통해 찾아내는 Agent이다.

        - 검색 목적: {mission}
        --------------------------------
        - 과거 검색 내용: {references}
        --------------------------------
        - 이전 대화 내용: {messages}
        --------------------------------
        - 목차(outline): {outline}
        """
    )

    mission = (pending.description or "")
    references = state.get("references", {"queries": [], "docs": []})
    messages = state.get("messages", [])
    outline_text = get_outline(current_path)

    inputs = {
        "mission": mission,
        "references": references,
        "messages": messages,
        "outline": outline_text,
    }

    llm_with_retriever = llm.bind_tools([retrieve])
    vector_search_chain = vector_search_system_prompt | llm_with_retriever

    search_plans = vector_search_chain.invoke(inputs)

    preexisting_queries = list(references.get("queries", []))
    ran_queries: list[str] = []

    # 누적 버킷
    accum_queries: list[str] = []
    accum_docs: list = []

    tool_calls = getattr(search_plans, "tool_calls", []) or []
    for tool_call in tool_calls:
        name, args = None, {}
        if isinstance(tool_call, dict):
            name = tool_call.get("name")
            args = tool_call.get("args", {}) or {}
        else:
            name = getattr(tool_call, "name", None)
            args = getattr(tool_call, "args", {}) or {}
        if (name or "").lower() != "retrieve":
            continue

        query = (args.get("query") or "").strip()
        if not query:
            continue

        print("-----------------------------------", {"name": name, "args": {"query": query}})
        try:
            retrieved_docs = retrieve.invoke({"query": query})
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{query}'): {e}")
            continue

        accum_queries.append(query)
        accum_docs.extend(retrieved_docs)
        ran_queries.append(query)

    for q in preexisting_queries:
        if not q or q in ran_queries:
            continue
        print("-----------------------------------", {"name": "retrieve", "args": {"query": q}})
        try:
            retrieved_docs = retrieve.invoke({"query": q})
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{q}'): {e}")
            continue
        accum_docs.extend(retrieved_docs)
        ran_queries.append(q)

    state["references"] = merge_refs(references, accum_queries, accum_docs)
    references = state["references"]

    print("Queries:--------------------------")
    for q in references["queries"]:
        print(q)
    print("References:--------------------------")
    for doc in references["docs"]:
        print((getattr(doc, "page_content", "") or "")[:100])
        print("--------------------------")

    pending.done = True
    pending.done_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 다음 집필 대상(title)
    fallback_default = "Executive Summary" if _doc_mode() == "report" else "서문"
    requested_title = _extract_last_write_target(messages, tasks)
    auto_title = next_unwritten_title(outline_text)
    target_title = requested_title or auto_title or fallback_default

    # writer 선택 — 단 하나의 함수만 사용
    writer_agent = preferred_writer_agent()

    # 동일 writer 펜딩 있으면 중복 금지
    has_pending_writer = any(
        (not t.done)
        and t.agent == writer_agent
        and (t.description or "").lower().startswith("write")
        for t in tasks
    )
    if not has_pending_writer:
        tasks.append(
            Task(
                agent=writer_agent,
                done=False,
                description=f"write: {target_title}",
                done_at="",
            )
        )

    msg_str = f"[VECTOR SEARCH AGENT] 다음 질문에 대한 검색 완료: {references['queries']}"
    print(msg_str)
    messages.append(AIMessage(msg_str))

    return {"messages": messages, "task_history": tasks, "references": references}


def chapter_writer(state: State):
    # --- DOC_MODE guard ---
    if _doc_mode() != "book":
        print(f"[CHAPTER WRITER] Skipped: DOC_MODE={_doc_mode()} (expected 'book').")
        return {
            "messages": state.get("messages", []),
            "task_history": state.get("task_history", []),
        }
    # -----------------------

    print("\n\n============ CHAPTER WRITER ============")

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    # 최근 미완료 chapter_writer 태스크
    pending = next(
        (t for t in reversed(tasks) if (not t.done) and t.agent == "chapter_writer"),
        None,
    )
    if pending is None:
        print("[WARN] pending 'chapter_writer' task가 없습니다. edge 트리거로 건너뜁니다.")
        return {"messages": state.get("messages", []), "task_history": tasks}

    messages = state.get("messages", [])

    # ✅ 최근 사용자 발화가 '목차 생성'이면 위임하고 종료
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and _is_outline_creation(last_human.content):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pending.done = True
        pending.done_at = now
        tasks.append(
            Task(
                agent="content_strategist",
                done=False,
                description="create_outline:auto",
                done_at="",
            )
        )
        messages.append(
            AIMessage("[Chapter Writer] Outline 요청 감지 → content_strategist로 위임")
        )
        return {"messages": messages, "task_history": tasks}

    outline_text = get_outline(current_path)
    if not outline_text or outline_text.strip() == "":
        raise ValueError(
            "아웃라인이 비어 있습니다. 먼저 content_strategist로 아웃라인을 생성/확정하세요."
        )

    desc_for_parse = (pending.description if pending else "") or ""

    # 1) 집필 대상 결정
    target_title = None

    # (a) description에서 write: ... 추출
    m = re.search(r"write[:：]\s*(.+)", desc_for_parse, flags=re.IGNORECASE)
    if m:
        target_title = m.group(1).strip().strip("'\"")

    # (b) 최근 사용자 메시지에서 write: ...
    if not target_title:
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                m2 = re.search(r"write[:：]\s*(.+)", msg.content, flags=re.IGNORECASE)
                if m2:
                    target_title = m2.group(1).strip().strip("'\"")
                    break

    # (c) 그래도 없으면 아직 미작성 자동
    if not target_title:
        target_title = next_unwritten_title(outline_text)

    if not target_title:
        messages.append(AIMessage("[Chapter Writer] 모든 목차 항목의 초안이 이미 작성되었습니다."))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if pending:
            pending.done = True
            pending.done_at = now
        else:
            tasks.append(
                Task(
                    agent="chapter_writer",
                    done=True,
                    description="(auto) nothing to write",
                    done_at=now,
                )
            )
        tasks.append(
            Task(
                agent="communicator",
                done=False,
                description="집필 진행 완료를 사용자에게 보고하고, 편집/다듬기 단계로 넘어갈지 물어본다.",
                done_at="",
            )
        )
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target chapter: {target_title}")

    # 2) 참고자료 요약
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

    # 3) 프롬프트
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
    gathered = ""
    print("\nAI\t: ", end="")
    for chunk in writer_chain.stream(inputs):
        print(chunk, end="")
        gathered += chunk
    print()

    # 5) 파일 저장
    out_path = save_md_draft(
        target_title,
        gathered,
        mode="book",
        current_path=current_path,
    )
    messages.append(AIMessage(f"[Chapter Writer] '{target_title}' 초안 작성 완료 → {out_path}"))

    # 6) 태스크 완료 & 다음 단계
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if pending:
        pending.done = True
        pending.done_at = now
    else:
        tasks.append(
            Task(
                agent="chapter_writer", done=True, description=f"write: {target_title}", done_at=now
            )
        )

    tasks.append(
        Task(
            agent="communicator",
            done=False,
            description=f"'{target_title}' 초안 작성이 완료되었음을 사용자에게 보고하고, 다음 집필 대상(또는 수정/분량조정)을 물어본다.",
            done_at="",
        )
    )

    return {"messages": messages, "task_history": tasks}


def section_writer(state: State):
    def _compute_outdir_for_section_writer(base_dir: str) -> str:
        # 섹션 라이터는 항상 sections/로 저장
        outdir = os.path.join(base_dir, "sections")
        os.makedirs(outdir, exist_ok=True)
        return outdir

    def _save_md_section(title: str, body: str, base_dir: str) -> str:
        """
        section_writer 전용 저장:
        - 무조건 sections/에 저장
        - 과거 chapters/에 잘못 저장된 동일 파일명을 발견하면 1회 이동 보정
        - 기존 파일이 있으면 .bak 백업(최소 변경 한 줄)
        """
        fname = f"{_slugify(title)}.md"
        outdir = _compute_outdir_for_section_writer(base_dir)
        correct_path = os.path.join(outdir, fname)

        # 과거 잘못 저장본 이동 보정
        wrong_path = os.path.join(base_dir, "chapters", fname)
        if os.path.exists(wrong_path) and wrong_path != correct_path:
            try:
                shutil.move(wrong_path, correct_path)
                print(
                    f"[Section Writer] moved (chapters → sections): {wrong_path} -> {correct_path}"
                )
            except Exception as e:
                print(f"[WARN] move failed {wrong_path} -> {correct_path}: {e}")

        # 최소 변경 백업 한 줄
        try:
            if os.path.exists(correct_path):
                shutil.copy2(correct_path, correct_path + ".bak")
        except Exception as e:
            print(f"[WARN] backup failed {correct_path}.bak: {e}")

        # 최종 쓰기
        with open(correct_path, "w", encoding="utf-8") as f:
            f.write(body or "")
        return correct_path

    # ----- DOC_MODE guard -----
    if _doc_mode() != "report":
        print(f"[SECTION WRITER] Skipped: DOC_MODE={_doc_mode()} (expected 'report').")
        return {
            "messages": state.get("messages", []),
            "task_history": state.get("task_history", []),
        }

    # ----- Main -----
    print("\n\n============ SECTION WRITER ============")

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    # ✅ 최근 '미완료 section_writer' 태스크 탐색
    pending = next(
        (t for t in reversed(tasks) if (not t.done) and t.agent == "section_writer"),
        None,
    )
    desc_for_parse = pending.description if pending else ""
    if pending is None:
        print("[WARN] pending 'section_writer' task가 없습니다. edge 트리거로 진행합니다.")

    messages = state.get("messages", [])
    outline_text = get_outline(current_path)
    if not outline_text or outline_text.strip() == "":
        raise ValueError("아웃라인이 비어 있습니다. 먼저 보고서 개요(목차)를 만드세요.")

    # 1) 집필 타깃
    target_title = None
    m = re.search(r"write[:：]\s*(.+)", desc_for_parse or "", flags=re.IGNORECASE)
    if m:
        target_title = m.group(1).strip()

    if not target_title:
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                m2 = re.search(r"write[:：]\s*(.+)", msg.content, flags=re.IGNORECASE)
                if m2:
                    target_title = m2.group(1).strip().strip("'\"")
                    break

    try:
        auto_pick = next_unwritten_title(outline_text)
    except Exception:
        auto_pick = None
    if not target_title:
        target_title = auto_pick

    if not target_title:
        messages.append(AIMessage("[Section Writer] 모든 섹션 초안이 이미 작성되었습니다."))
        if pending:
            pending.done = True
            pending.done_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tasks.append(
            Task(
                agent="communicator",
                done=False,
                description="집필 진행 완료를 사용자에게 보고하고, 편집/수정 단계로 넘어갈지 물어본다.",
                done_at="",
            )
        )
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
        - 길이: 800~1,500 단어 내외(요약 섭션은 400~800)
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

    # 3) 참고자료 요약
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
    gathered = ""
    print("\nAI\t: ", end="")
    for chunk in chain.stream(inputs):
        print(chunk, end="")
        gathered += chunk
    print()

    # 5) 파일 저장 (sections/)
    try:
        _ = save_md_draft  # 존재 확인만
        out_path = save_md_draft(
            target_title,
            gathered,
            mode=_doc_mode(),  # 'report'
            current_path=current_path,
        )
    except NameError:
        out_path = _save_md_section(target_title, gathered, base_dir=current_path)

    messages.append(AIMessage(f"[Section Writer] '{target_title}' 초안 작성 완료 → {out_path}"))
    state["last_saved_path"] = out_path

    # 6) 태스크 상태 & 다음 단계
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if pending:
        pending.done = True
        pending.done_at = now
    else:
        tasks.append(
            Task(agent="section_writer", done=True, description=f"write: {target_title}", done_at=now)
        )

    tasks.append(
        Task(
            agent="communicator",
            done=False,
            description=f"'{target_title}' 초안 작성 완료를 사용자에게 보고하고, 다음 섹션/수정 범위를 물어본다.",
            done_at="",
        )
    )

    return {"messages": messages, "task_history": tasks}


# 사용자와 대화할 노드(agent): communicator
def communicator(state: State):
    print("\n\n============ COMMUNICATOR ============")

    messages = state.get("messages", [])
    tasks = state.get("task_history", [])

    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    pending = next(
        (t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"),
        None,
    )
    desc = (pending.description if pending else "") or ""

    fallback_outline = get_outline(current_path)

    # ❶ show_outline 판단
    show_outline_req = False
    last_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
    )

    explicit_fname = None
    mdesc = re.search(r"show_outline\s*:\s*([A-Za-z0-9_\-\.]+)", desc)
    if mdesc:
        explicit_fname = mdesc.group(1).strip()
        show_outline_req = True

    if ("show_outline" in desc.lower()) or (
        last_human and re.search(r"(목차|차례|outline)", last_human.content, re.IGNORECASE)
    ):
        show_outline_req = True

    if show_outline_req:
        if explicit_fname:
            fname = explicit_fname
        else:
            user_text = last_human.content if last_human else ""
            fname = _pick_outline_filename(user_text)

        tried = []
        outline_text = ""
        fname_used = None

        def try_read(name: str):
            try:
                return (get_outline(current_path, name) or "")
            except TypeError:
                abs_path = os.path.join(current_path, name)
                if os.path.exists(abs_path):
                    try:
                        with open(abs_path, "r", encoding="utf-8") as f:
                            return (f.read() or "")
                    except Exception:
                        return ""
                return ""

        if fname:
            tried.append(fname)
            txt = try_read(fname)
            if txt.strip():
                outline_text, fname_used = txt, fname

        if not outline_text:
            mode = _doc_mode()
            default_by_mode = "outline_report.md" if mode == "report" else "outline_book.md"
            if default_by_mode not in tried:
                tried.append(default_by_mode)
            txt = try_read(default_by_mode)
            if txt.strip():
                outline_text, fname_used = txt, default_by_mode

        if not outline_text:
            if "outline.md" not in tried:
                tried.append("outline.md")
            txt = try_read("outline.md")
            if txt.strip():
                outline_text, fname_used = txt, "outline.md"

        if not outline_text:
            asked = explicit_fname or fname or "(not specified)"
            noti = f"(저장된 목차가 없습니다: {asked})"
            fallback = (fallback_outline or "").strip()
            if fallback:
                outline_text = noti + "\n\n[참고] 폴백 목차를 대신 보여드립니다.\n\n" + fallback
                fname_used = "auto(fallback)"
            else:
                outline_text = noti
                fname_used = asked

        title = f"## 현재 목차 ({fname_used})" if fname_used else "## 현재 목차"
        content = f"{title}\n\n{outline_text}"

        print("\nAI\t:\n" + content)
        messages.append(AIMessage(content))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if pending:
            pending.done = True
            pending.done_at = now

        tasks.append(
            Task(
                agent="communicator",
                done=False,
                description="목차를 보여준 뒤, 다음 집필 대상이나 수정 요청을 물어본다.",
                done_at="",
            )
        )
        return {"messages": messages, "task_history": tasks}

    # ❷ 일반 커뮤니케이션
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
        "messages": messages,
        "outline": fallback_outline,
    }

    gathered = None
    print("\nAI\t: ", end="")
    for chunk in system_chain.stream(inputs):
        print(chunk.content, end="")
        gathered = chunk if gathered is None else (gathered + chunk)

    # 저장 경로 한 줄 덧붙이기
    try:
        has_path_already = isinstance(gathered, AIMessage) and (
            ("chapters\\" in gathered.content)
            or ("sections\\" in gathered.content)
            or ("chapters/" in gathered.content)
            or ("sections/" in gathered.content)
        )
        if not has_path_already:
            last_save_path = None
            moved_note = None

            for m in reversed(messages):
                if not isinstance(m, AIMessage):
                    continue
                m1 = re.search(r"\[(?:Section|Chapter)\s+Writer\].*?→\s*(.+?\.md)\s*$", m.content)
                if m1:
                    last_save_path = m1.group(1).strip()
                    break
                m2 = re.search(r"\[(?:Section|Chapter)\s+Writer\]\s*moved.*?->\s*(.+?\.md)\s*$", m.content)
                if m2:
                    last_save_path = m2.group(1).strip()
                    moved_note = " (파일이 자동 정리되어 sections로 이동되었습니다.)"
                    break

            if last_save_path:
                try:
                    last_save_path = os.path.normpath(last_save_path)
                except Exception:
                    pass
                suffix = f"\n\n최종 저장 경로: `{last_save_path}`"
                if moved_note:
                    suffix += moved_note
                base_text = getattr(gathered, "content", str(gathered))
                gathered = AIMessage(base_text + suffix)
    except Exception:
        pass

    messages.append(gathered)

    if pending:
        pending.done = True
        pending.done_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {"messages": messages, "task_history": tasks}


# 상태 그래프 정의
graph_builder = StateGraph(State)

# Nodes
graph_builder.add_node("supervisor", supervisor)
graph_builder.add_node("communicator", communicator)
graph_builder.add_node("content_strategist", content_strategist)
graph_builder.add_node("vector_search_agent", vector_search_agent)
graph_builder.add_node("web_search_agent", web_search_agent)
graph_builder.add_node("chapter_writer", chapter_writer)
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
        "section_writer": "section_writer",
    },
)
graph_builder.add_edge("content_strategist", "communicator")
graph_builder.add_edge("web_search_agent", "vector_search_agent")  # ③

def tail_task_router(state: State):
    allowed = {"chapter_writer", "section_writer", "communicator"}
    # 1) 최신 '미완료' + 허용 agent
    for t in reversed(state["task_history"]):
        if (not t.done) and t.agent in allowed:
            return t.agent
    # 2) 없으면 DOC_MODE에 맞는 writer로
    return preferred_writer_agent()

graph_builder.add_conditional_edges(
    "vector_search_agent",
    tail_task_router,
    {
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",  # 안전망
    },
)

graph_builder.add_edge("chapter_writer", "communicator")
graph_builder.add_edge("section_writer", "communicator")
graph_builder.add_edge("communicator", END)

graph = graph_builder.compile()

# graph.get_graph().draw_mermaid_png(output_file_path=absolute_path.replace('.py', '.png'))

# from playwright.sync_api import sync_playwright
from string import Template

HTML_TMPL = Template(
    """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'default' });</script>
<style> body{margin:0;padding:16px;} </style>
</head>
<body><div class="mermaid">$mmd</div></body></html>
"""
)

def render_mermaid_with_playwright(mmd: str, out_path: str, width: int = 1600, height: int = 1000):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("[INFO] Playwright 미설치: 그래프 렌더를 건너뜁니다.")
        return None
    
    html = HTML_TMPL.substitute(mmd=mmd)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.set_content(html, wait_until="networkidle")
                page.wait_for_timeout(300)
                page.locator(".mermaid").screenshot(path=out_path)
            finally
                browser.close()
        return out_path
    except Exception as e:
        print(f"[WARN] Mermaid 렌더 실패: {e}")
        return None

# 호출부 (필요 시만)
if os.getenv("RENDER_GRAPH", "0") == "1":
    mmd = graph.get_graph().draw_mermaid()
    out_png = absolute_path.replace(".py", ".png")
    result_path = render_mermaid_with_playwright(mmd, out_png)
    if result_path:
        print("Saved:", result_path)
    else:
        print("[INFO] 그래프 이미지 저장이 건너뛰어졌거나 실패했습니다.")

# 상태 초기화
state = State(
    messages=[
        SystemMessage(
            f"""
        너희 AI들은 사용자의 요구에 맞는 책을 쓰는 작가팀이다.
        사용자가 사용하는 언어로 대화하라.

        현재시각은 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}이다.
        """
        )
    ],
    task_history=[],
)

while True:
    user_input = input("\nUser\t: ").strip()

    if user_input.lower() in ["exit", "quit", "q"]:
        print("Goodbye!")
        break

    state["messages"].append(HumanMessage(user_input))
    state = graph.invoke(state)

    print("\n------------------------------------ MESSAGE COUNT\t", len(state["messages"]))

    save_state(current_path, state)  # 현재 state 내용 저장
