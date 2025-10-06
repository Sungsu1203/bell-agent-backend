from __future__ import annotations

"""
Refactored agent code focused on **일관성(consistency)**, **간결성(conciseness)**,
그리고 **무한루프 방지**.
- 정규식/탐지 로직: rag_expression.py 단일 출처 사용
- write 타깃 추출: extract_write_title() 일원화
- 파일 저장 경로/슬러그 규칙 단일화
- web_search 가드/재시도/프리뷰 적재
- DOC_MODE별 writer 자동 전환
- force_queries 슈퍼바이저 패스트패스
- 모든 프롬프트는 prompts.py의 get_* 함수 사용
- 상태 숫자 캐스팅 및 보정: utils/state_sanitize.py
"""

# ── 0) 환경 부트스트랩 ─────────────────────────────────────────────
import os
import re
import time
import pickle
import hashlib
from pathlib import Path
from datetime import datetime
from string import Template
from typing import List, Optional
from typing_extensions import TypedDict
import shutil

from dotenv import load_dotenv, find_dotenv

dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, override=False)
else:
    print("[INFO] .env 미발견: OS 환경변수만 사용합니다.")

# USER_AGENT 기본값 (import 전에)
hostname = os.getenv("COMPUTERNAME") or os.getenv("HOSTNAME") or "local"
os.environ.setdefault("USER_AGENT", f"BookWriterBot/1.0 (+{hostname})")

# ── LangChain / LangGraph ─────────────────────────────────────────
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.documents import Document

# ── 내부 모듈 ─────────────────────────────────────────────────────
from models import Task
from utils_forced_queries import extract_forced_queries_from_messages

from tools.web_rag import (
    retrieve,
    web_search,
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    _default_chroma_dir,
)

from tools.local_rag import ingest_local_files

from content_utils import (
    read_outline,
    save_outline,
    save_md_draft,
    next_unwritten_title,
    parse_outline_headings,
    is_written,
    get_content_dir,
    path_for_title,
)

from rag_expression import (
    RE_WRITE_LINE,  # 호환성 유지용
    extract_write_title,
    is_outline_creation,
    is_outline_display,
)

from prompts import (
    get_supervisor_prompt,
    get_content_strategist_prompt,
    get_web_search_prompt,
    get_vector_search_prompt,
    get_chapter_writer_prompt,
    get_section_writer_prompt,
    get_communicator_prompt,
    get_research_planner_prompt,
    get_research_synthesizer_prompt,
)

from utils.state_sanitize import (
    sanitize_numeric_state,
    coerce_int,
    as_int,
)

from utils.citation_utils import attach_auto_citations

import argparse

# ── 경로/전역 ─────────────────────────────────────────────────────
filename = os.path.basename(__file__)
absolute_path = os.path.abspath(__file__)
current_path = os.path.dirname(absolute_path)


def _now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)


def _doc_mode() -> str:
    return (os.getenv("DOC_MODE", "book") or "book").strip('"').strip().lower()


DOC_MODE = _doc_mode()


def preferred_writer_agent() -> str:
    return "section_writer" if DOC_MODE == "report" else "chapter_writer"


WRITER_AGENT = preferred_writer_agent()


# ── 간단 상태 저장기 ─────────────────────────────────────────────

def save_state(base_dir: str, state: dict, fname: str = "last_state.pkl") -> None:
    try:
        outdir = Path(base_dir) / "state"
        outdir.mkdir(parents=True, exist_ok=True)
        with open(outdir / fname, "wb") as f:
            pickle.dump(state, f)
    except Exception as e:
        print(f"[WARN] save_state 실패: {e}")


# ── LLM ───────────────────────────────────────────────────────────
llm = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o"), temperature=0.3)


# ── State 타입 ────────────────────────────────────────────────────
# ── State 타입 ────────────────────────────────────────────────────
class State(TypedDict, total=False):
    messages: List[AnyMessage]
    task_history: List[Task]
    references: dict
    last_saved_path: str
    topic_title: str
    topic_slug: str
    chroma_ns: str
    outline_fname: str
    outline_shown: bool
    agent_role: str
    iteration_count: int
    research_round: int
    research_objectives: List[str]
    findings_md: List[str]
    llm_logs: List[dict]
    new_url_count: int | None
    # 이하 루프 컨트롤 보조키(존재 시 사용)
    new_url_count_round: int | None
    round_new_urls: int | None
    qa_direct_reply: bool | None
    planner_queries: List[str] | None
    no_new_url_streak: int | None
    local_ingested_once: bool | None
    research_planner_announce: int | None
    research_halt_threshold: int | None
    research_min_rounds: int | None
    research_max_no_new_rounds: int | None



# ── 유틸 ──────────────────────────────────────────────────────────

def _clean_snip(s: str, n: int = 120) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ")
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:n] + ("..." if len(s) > n else ""))

def _clean_seed(s: str) -> str:
    s = re.sub(r"^#+\s*", "", s)                 # heading 마크 제거
    s = re.sub(r"^\d+[\.\)]\s*", "", s)          # "1.", "2)" 제거
    s = re.sub(r"^(작성|write)\s*[:：]\s*", "", s, flags=re.I)
    s = s.strip(" -•—·\t")
    return s

def _ok_query(q: str) -> bool:
    q = (q or "").strip()
    if not q: return False
    q2 = _clean_seed(q)
    return bool(q2) and (len(q2) <= 120)

def _plain_snip(text: str, n: int = 160) -> str:
    t = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.I | re.S)
    t = re.sub(r"<style.*?>.*?</style>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return _clean_snip(t, n)

_ASCII_NS_RE = re.compile(r'[^a-zA-Z0-9._-]+')


# def _ascii_namespace(seed: str) -> str:
#     s = _ASCII_NS_RE.sub('-', seed).strip('._-')
#     if not s or not re.match(r'^[A-Za-z0-9].*[A-Za-z0-9]$', s):
#         s = 'ns-' + hashlib.sha1(seed.encode('utf-8', 'ignore')).hexdigest()[:12]
#     return s[:64]

def _ascii_namespace(seed: str) -> str:
    core = hashlib.sha1(seed.encode("utf-8","ignore")).hexdigest()[:10]
    return f"ns-{core}"


def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^\w\-가-힣\s]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s or "untitled"


def _topic_slug_from(text: str) -> str:
    base = _slugify(text or "untitled")
    return f"{base}-{datetime.now().strftime('%Y%m%d-%H%M')}"


def _topic_dir(slug: str) -> str:
    return os.path.join(current_path, "data", "chroma_store", slug)


def _content_base_dir(mode: str, slug: str | None) -> str:
    base = "sections" if mode == "report" else "chapters"
    return os.path.join(base, slug) if slug else base

def _sanitize_title(raw: str) -> str:
    """
    '새 보고서', '새 프로젝트', '작성:', 'write:' 등 선행 토큰을 모두 제거해
    일관된 제목을 만든다. (반복/전각 콜론/여백 모두 방어)
    """
    s = (raw or "")
    # 가장 흔한 패턴부터 제거
    s = re.sub(r'^\s*(새\s*(보고서|프로젝트)\s*(작성)?\s*)[:：]?\s*', '', s, flags=re.I)
    # 선행 '작성:' / 'write:' 반복 제거
    while re.match(r'^\s*(작성|write)\s*[:：]\s*', s, flags=re.I):
        s = re.sub(r'^\s*(작성|write)\s*[:：]\s*', '', s, flags=re.I)
    # 마무리 트리밍
    s = s.strip(' :\u3000-—–')
    return s

def _load_objectives_from_env(prefix: str = "BLOCKAGI_OBJECTIVE_") -> list[str]:
    objs = []
    for i in range(1, 10 + 1):
        v = os.getenv(f"{prefix}{i}")
        if v and v.strip():
            objs.append(v.strip())
    return objs


def has_pending(tasks: List[Task], agent: str, prefix: Optional[str] = None) -> bool:
    for t in reversed(tasks):
        if (not t.done) and t.agent == agent:
            if prefix is None:
                return True
            if (t.description or "").lower().startswith(prefix.lower()):
                return True
    return False


def iter_tool_calls(msg, name: str):
    tcs = getattr(msg, "tool_calls", []) or []
    for tc in tcs:
        if isinstance(tc, dict):
            n = (tc.get("name") or "").lower()
            args = tc.get("args") or {}
        else:
            n = (getattr(tc, "name", "") or "").lower()
            args = getattr(tc, "args", {}) or {}
        if n == name.lower():
            yield args


def get_last_write_target(messages, tasks) -> Optional[str]:
    # 1) 최근 HumanMessage에서 파싱
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            t = extract_write_title(m.content or "")
            if t:
                return t
    # 2) 태스크 히스토리(백워드 호환)
    for t in reversed(tasks):
        title = extract_write_title(t.description or "")
        if title:
            return title
    return None


# ── Outline IO(토픽 인지) ────────────────────────────────────────

def _pick_outline_filename(user_text: str | None) -> str:
    text = (user_text or "").lower()
    if re.search(r"ai.*책.*목차|책.*ai.*목차", text):
        return "outline_book.md"
    if re.search(r"(보고서|report).*(목차|outline)", text):
        return "outline_report.md"
    # 기본값은 현재 DOC_MODE에 맞춰 일관화
    return "outline_report.md" if DOC_MODE == "report" else "outline.md"


def get_topic_outline_text(state: State) -> str:
    txt, _path = read_outline(
        filename=state.get("outline_fname") or "outline.md",
        root_dir=current_path,
        topic_slug=state.get("topic_slug"),
        mode=DOC_MODE,
        allow_fallbacks=True,
    )
    return txt or ""


# ── Topic 초기화 ─────────────────────────────────────────────────

def start_new_topic(state: State, title: str, outline_fname: str | None = None) -> State:
    slug = _topic_slug_from(title)
    ns = _ascii_namespace(slug)
    state["topic_title"] = title
    state["topic_slug"] = slug
    state["chroma_ns"] = ns
    state["outline_fname"] = outline_fname or state.get("outline_fname") or "outline.md"
    state["outline_shown"] = False          # ← 추가: 새 주제에서 아직 목차를 보여주지 않았음
    state["references"] = {"queries": [], "docs": []}
    state["last_saved_path"] = ""
    os.makedirs(_topic_dir(slug), exist_ok=True)
    os.environ["CHROMA_NAMESPACE"] = ns
    os.environ["CHROMA_DIR"] = _topic_dir(slug)

    # 새 주제 시작 시 연구 상태 리셋(ENV로 끌 수 있음)
    if os.getenv("RESET_OBJECTIVES_ON_NEW_TOPIC", "1") == "1":
        state["research_objectives"] = _load_objectives_from_env()  # 필요시 [] 로 완전 초기화
        state["research_round"] = 0
        state["no_new_url_streak"] = 0

    return state


# ── Refs 유틸 (dedup 등) ─────────────────────────────────────────

def merge_refs(existing: dict | None, new_queries: list[str] | None, new_docs: list | None) -> dict:
    import hashlib as _hh

    refs = existing or {}
    merged_q = list(refs.get("queries", []) or [])
    merged_d = list(refs.get("docs", []) or [])
    if new_queries:
        merged_q.extend([q for q in new_queries if q])
    if new_docs:
        merged_d.extend([d for d in new_docs if d is not None])

    seen_q, dedup_q = set(), []
    for q in merged_q:
        qq = (q or "").strip()
        if qq and qq not in seen_q:
            dedup_q.append(qq)
            seen_q.add(qq)

    def _doc_sig(d: Document) -> str:
        pc = (getattr(d, "page_content", "") or "")
        pc_head = " ".join(pc.split())[:500]
        meta = getattr(d, "metadata", {}) or {}
        src = (meta.get("source") or meta.get("url") or "").strip()
        return _hh.sha1(f"{src}|{pc_head}".encode("utf-8", "ignore")).hexdigest()

    seen_sig, dedup_docs = set(), []
    for d in merged_d:
        try:
            sig = _doc_sig(d)
        except Exception:
            sig = repr(d)[:120]
        if sig not in seen_sig:
            dedup_docs.append(d)
            seen_sig.add(sig)
    return {"queries": dedup_q, "docs": dedup_docs}


def _refs_preview_text(state: "State", max_q=5, max_docs=8, snippet_len=350) -> str:
    refs = state.get("references", {"queries": [], "docs": []})
    qs = refs.get("queries", [])[:max_q]
    docs = refs.get("docs", [])[:max_docs]
    lines = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or "unknown"
        snip = (d.page_content or "")[:snippet_len].replace("\n", " ")
        lines.append(f"- [{src}] {snip}")
    q_block = "\n".join([f"- {q}" for q in qs])
    d_block = ("\n\nDocs:\n" + "\n".join(lines)) if lines else ""
    return "Queries:\n" + q_block + d_block


def _score_doc(d: Document) -> float:
    meta = getattr(d, "metadata", {}) or {}
    src = (meta.get("source") or meta.get("url") or "").lower()
    score = 0.0
    if any(t in src for t in [".go.kr", ".gov", ".ac.kr", ".edu"]):
        score += 3
    if any(k in src for k in ["wsts", "imf", "kostat", "stat", "kotra"]):
        score += 2
    if any(k in src for k in ["kpmg", "mckinsey", "gartner", "idc"]):
        score += 1.5
    y = re.search(r"(20\d{2})", src) or re.search(r"(20\d{2})", (getattr(d, "page_content", "") or ""))
    if y:
        yr = int(y.group(1))
        score += max(0, (2026 - yr) * 0.1)
    return score


# ── Supervisor ===============================================================

def supervisor(state: State):
    print("\n\n============ SUPERVISOR ============")
    state = sanitize_numeric_state(state)

    # ── Task / Messages 안전 초기화 ─────────────────────────────────────────────
    tasks = state.get("task_history", [])
    if not isinstance(tasks, list):
        tasks = list(tasks) if tasks else []
    state["task_history"] = tasks

    messages = state.get("messages", [])
    if not isinstance(messages, list):
        messages = list(messages) if messages else []
    state["messages"] = messages


    tasks = state.get("task_history", [])
    messages = state.get("messages", [])

    # ✅ vector_search_agent가 직답 플래그를 세팅했다면 다른 태스크 추가 없이 바로 반환
    if state.get("qa_direct_reply"):
        return {"messages": messages, "task_history": tasks}

    # ── 마지막 사용자 메시지 추출 ─────────────────────────────────────────────
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    last_text: str = (last_human.content if (last_human and isinstance(last_human.content, str)) else "").strip()

    def _is_qa_like(s: str) -> bool:
        if not isinstance(s, str):
            return False
        s = s.strip()
        if not s:
            return False
        # 흔한 QA/요약/질문 패턴
        qa_markers = ("요약", "정리", "설명해줘", "무엇", "뭐야", "어떻게", "왜", "누가", "어디", "언제", "비교", "?")
        return any(k in s for k in qa_markers)

    # ── QA/요약형 사용자 요청이면: 벡터 검색을 우선 예약하고 즉시 반환 ────────────
    if last_text and _is_qa_like(last_text):
        if not has_pending(tasks, "vector_search_agent"):
            tasks.append(Task(
                agent="vector_search_agent",
                done=False,
                description="사용자 질의 기반 RAG 검색을 수행한다.",
                done_at=""
            ))
        # 이 시점에 section_writer 등은 예약하지 않고 컨트롤을 넘김
        return {"messages": messages, "task_history": tasks}
    
    # 새 토픽
    m_new = re.search(
        r"(?:새\s*(?:보고서|프로젝트)\s*(?:작성)?|주제\s*(?:변경|바꿔)|new\s*(?:report|project)|switch\s*(?:topic|report))\s*[:：]?\s*(?P<title>.*)$",
        last_text,
        re.I,
    )
    if m_new:
        maybe_title = (m_new.group("title") or "").strip() or "untitled report"
        # 선행 토큰 전부 정리
        maybe_title = _sanitize_title(maybe_title)
        state = start_new_topic(state, maybe_title, outline_fname=_pick_outline_filename(last_text))
        msg = f"[Supervisor] 새 주제 세션 시작: '{state['topic_title']}' (ns={state['chroma_ns']})"
        messages.append(AIMessage(msg))
        print(msg)
        task_history.append(
            Task(agent="content_strategist", done=False, description=f"create_outline:{state['outline_fname']}", done_at="")
        )
        return {
            "messages": messages,
            "task_history": task_history,
            "topic_title": state["topic_title"],
            "topic_slug": state["topic_slug"],
            "chroma_ns": state["chroma_ns"],
            "outline_fname": state["outline_fname"],
            "references": state["references"],
            "last_saved_path": state["last_saved_path"],
        }
    
    # ✅ 연구 라운드 모드 부트스트랩 (라우터가 아니라 여기서 상태 변경)
    if (
        (state.get("agent_role") or "").strip().lower() == "research analyst"
        and (state.get("research_objectives") or [])
        and not task_history  # 최초 유입 시에만
        # ⬇️⬇️ 추가: 사용자가 목차 보기/생성을 원하면 fast-path 무시
        and not (is_outline_display(last_text) or is_outline_creation(last_text))
    ):
        task_history.append(Task(agent="research_planner", done=False, description="plan_first", done_at=""))
        msg="[Supervisor fast-path] 연구 라운드 모드 시작 → research_planner"
        messages.append(AIMessage(msg))
        print(msg)
        return {"messages": messages, "task_history": task_history}
    
    # ✅ 목차 생성 태스크가 이미 pending이면 선(先) 처리 (사용자 명시적 요청 제외)
    pending_cs = next((t for t in reversed(task_history) if (not t.done) and t.agent == "content_strategist"), None)
    if pending_cs and not (is_outline_display(last_text) or is_outline_creation(last_text)):
        print("[Supervisor priority] content_strategist pending → 우선 진행")
        return {
            "messages": messages,
            "task_history": task_history,
            "topic_title": state.get("topic_title"),
            "topic_slug": state.get("topic_slug"),
            "chroma_ns": state.get("chroma_ns"),
            "outline_fname": state.get("outline_fname"),
            "references": state.get("references"),
            "last_saved_path": state.get("last_saved_path"),
        }

    # fast-path: 강제 쿼리
    try:
        fqs = extract_forced_queries_from_messages(messages, lookback=5)
    except Exception:
        fqs = []
    if fqs:
        task_history.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        msg=f"[Supervisor fast-path] → web_search_agent (force_queries {len(fqs)}개 감지)"
        messages.append(AIMessage(msg))
        print(msg)
        return {"messages": messages, "task_history": task_history}

    # fast-path: 목차 생성/표시
    if is_outline_creation(last_text):
        fname = _pick_outline_filename(last_text)
        task_history.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        msg=f"[Supervisor fast-path] → content_strategist (target={fname})"
        messages.append(AIMessage(msg))
        print(msg)
        return {"messages": messages, "task_history": task_history}

    if is_outline_display(last_text):
        fname = _pick_outline_filename(last_text)
        task_history.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))
        msg=f"[Supervisor fast-path] → communicator (show_outline:{fname})"
        messages.append(AIMessage(msg))
        print(msg)
        return {"messages": messages, "task_history": task_history}

    # fast-path: RAG 업데이트 키워드
    _rag_re = r"(최신|업데이트|update|latest).*?(자료|리소스|레퍼런스|참고|sources|material).*?(rag|벡터|vector|임베딩|embedding|index|색인|chroma)"
    if re.search(_rag_re, last_text, flags=re.IGNORECASE):
        now = _now_str()
        for t in task_history:
            if (not t.done) and t.agent in ("chapter_writer", "section_writer"):
                t.done = True
                t.done_at = now
        msg="[Supervisor fast-path] 기존 writer 태스크 정리 후 RAG 업데이트 시작."
        messages.append(AIMessage(msg))
        print(msg)
        task_history.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        msg="[Supervisor fast-path] → web_search_agent (RAG 업데이트 착수)"
        messages.append(AIMessage(msg))
        print(msg)
        return {"messages": messages, "task_history": task_history}

    # fast-path: write: ...
    target_from_line = extract_write_title(last_text)
    if target_from_line:
        refs = state.get("references", {})
        refs_empty = not (refs.get("docs") or [])
        has_pending_rag = any((not t.done) and t.agent in ("web_search_agent", "vector_search_agent") for t in task_history)
        if refs_empty or has_pending_rag:
            if not has_pending(task_history, "web_search_agent"):
                task_history.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
            msg="[Supervisor fast-path] 레퍼런스 비어있음/진행중 → RAG 먼저(web_search_agent)."
            messages.append(AIMessage(msg))
            print(msg)
            return {"messages": messages, "task_history": task_history}

        writer_agent = WRITER_AGENT
        task_history.append(Task(agent=writer_agent, done=False, description=f"write: {target_from_line}", done_at=""))
        msg=f"[Supervisor fast-path] → {writer_agent} (mode={DOC_MODE}, write: {target_from_line})"
        messages.append(AIMessage(msg))
        print(msg)
        return {"messages": messages, "task_history": task_history}
    
    # 🔒 여기서 '일반 경로'로 가기 전에 추가: 미완료 태스크가 이미 있으면 새로 안 만든다
    pending_undone = next((t for t in reversed(task_history) if not t.done), None)
    if pending_undone:
        print(f"[Supervisor short-circuit] pending='{pending_undone.agent}' 유지 → 새 태스크 생성 생략")
        # 기존 상태만 반환 (라우터가 마지막 미완료 태스크로 라우팅)
        return {
            "messages": messages,
            "task_history": task_history,
            "topic_title": state.get("topic_title"),
            "topic_slug": state.get("topic_slug"),
            "chroma_ns": state.get("chroma_ns"),
            "outline_fname": state.get("outline_fname"),
            "references": state.get("references"),
            "last_saved_path": state.get("last_saved_path"),
        }

    # 일반 경로
    supervisor_system_prompt = get_supervisor_prompt()
    supervisor_chain = supervisor_system_prompt | llm.with_structured_output(Task)
    task = supervisor_chain.invoke(
        {
            "messages": messages,
            "outline": get_topic_outline_text(state),
            "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
        }
    )

    # DOC_MODE와 불일치하면 보정
    if task.agent in ("chapter_writer", "section_writer"):
        expected = WRITER_AGENT
        if task.agent != expected:
            msg=f"[Supervisor reconcile] DOC_MODE={DOC_MODE} → writer agent forced to {expected} (from {task.agent})"
            messages.append(
                AIMessage(msg)
            )
            print(msg)
            task = Task(agent=expected, done=False, description=task.description, done_at="")

    task_history.append(task)
    msg=f"[Supervisor] {task}"
    messages.append(AIMessage(msg))
    print(msg)

    return {
        "messages": messages,
        "task_history": task_history,
        "topic_title": state.get("topic_title"),
        "topic_slug": state.get("topic_slug"),
        "chroma_ns": state.get("chroma_ns"),
        "outline_fname": state.get("outline_fname"),
        "references": state.get("references"),
        "last_saved_path": state.get("last_saved_path"),
    }


def supervisor_router(state: State):
    state = sanitize_numeric_state(state)
    tasks = state.get("task_history", [])
    if tasks:
        return tasks[-1].agent

    last_human = next((m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), None)
    last_text = (last_human.content if (last_human and isinstance(last_human.content, str)) else "") or ""

    if (
        (state.get("agent_role") or "").strip().lower() == "research analyst"
        and (state.get("research_objectives") or [])
        and not is_outline_display(last_text)
        and not is_outline_creation(last_text)
    ):
        return "research_planner"
    return "communicator"


# ── Content Strategist =======================================================

def content_strategist(state: State):
    print("\n\n============ CONTENT STRATEGIST ============")
    state = sanitize_numeric_state(state)

    strategist_prompt = get_content_strategist_prompt(DOC_MODE)
    chain = strategist_prompt | llm | StrOutputParser()

    messages = state.get("messages", [])
    outline_text = get_topic_outline_text(state)
    gathered = ""
    for chunk in chain.stream(
        {
            "messages": messages,
            "outline": outline_text,
            "references": state.get("references", {"queries": [], "docs": []}),
            "topic_title": state.get("topic_title") or "",
        }
    ):
        print(chunk, end="")
        gathered += chunk
    print()

    # 저장(content_utils)
    fname = state.get("outline_fname") or "outline.md"
    out_path = save_outline(
        gathered,
        filename=fname,
        root_dir=current_path,
        topic_slug=state.get("topic_slug"),
        mode=DOC_MODE,
        backup=True,
    )
    messages.append(AIMessage(f"[Content Strategist] 목차 작성 완료 → {out_path}"))

    task_history = state.get("task_history", [])
    if not task_history or task_history[-1].agent != "content_strategist":
        raise ValueError("Content Strategist가 아닌 agent가 목차 작성을 시도했습니다.")
    task_history[-1].done = True
    task_history[-1].done_at = _now_str()

    if not has_pending(task_history, "communicator"):
        task_history.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))

    return {"messages": messages, "task_history": task_history}


# ── Web Search Agent =========================================================

def web_search_agent(state: State):
    import time, shutil, glob
    from pathlib import Path
    from langchain_core.messages import HumanMessage, AIMessage
    from langchain_core.documents import Document

    print("\n\n============ WEB SEARCH AGENT ============")
    state = sanitize_numeric_state(state)

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "web_search_agent"), None)
    if pending is None:
        raise ValueError(f"web_search_agent pending task 없음. 현재 마지막 태스크: {tasks[-1]}")

    web_search_system_prompt = get_web_search_prompt()

    messages = state.get("messages", [])
    references = state.get("references", {"queries": [], "docs": []})
    # 이전 라운드까지 포함한 전역 중복 방지 세트(소문자 기준)
    _existing_qs = set(q.strip().lower() for q in (references.get("queries") or []) if q and q.strip())

    outline_text = get_topic_outline_text(state)
    mission = (pending.description or "").strip()

    inputs = {
        "mission": mission,
        "references": references,
        "messages": messages,
        "outline": outline_text,
        "current_time": _now_str(),
        "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
    }

    queries: list[str] = []
    json_paths: list[str] = []
    new_docs_preview: list[Document] = []

    # ── 환경/제한 설정 ───────────────────────────────────────────────────
    COUNT_PREVIEW_URLS = os.getenv("COUNT_PREVIEW_URLS", "0") == "1"   # 기본: 프리뷰 URL은 카운트 안 함
    MAX_INDEXED_PER_ROUND = int(os.getenv("MAX_INDEXED_PER_ROUND", "0"))  # 0이면 제한 없음
    MAX_SEARCH_QUERIES_PER_ROUND = int(os.getenv("MAX_SEARCH_QUERIES_PER_ROUND", "6"))
    SKIP_WEB = os.getenv("SKIP_WEB_SEARCH", "0") == "1"
    if SKIP_WEB:
        print("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 → 외부 웹검색 전부 건너뜀(로컬 RAG만 수행).")

    # 네임스페이스/저장소
    ns = state.get("chroma_ns") or os.getenv("CHROMA_NAMESPACE") or "default"
    persist_dir = state.get("topic_slug") and _topic_dir(state["topic_slug"]) or None

    # 라운드 성과 집계
    chunk_total = 0            # 실제 인덱싱된 청크 수 합
    ingest_success = 0         # 청크가 1개 이상 들어간 검색 배치 수
    added_preview_urls = set() # 프리뷰에서 본 고유 URL(폴백용)

    # ── 웹검색 실행 헬퍼(가드 포함) ───────────────────────────────────────
    def _run_web_search_with_guard(q: str, preview_limit: int = 5, retries: int = 2) -> bool:
        nonlocal chunk_total, ingest_success, added_preview_urls
        def _is_bad_doc(d):
            txt = ((getattr(d, "page_content", None) or "")[:2000]).lower()
            return any(k in txt for k in [
                "access denied", "enable javascript", "just a moment", "security controls triggered", "captcha"
            ])

        for attempt in range(retries + 1):
            try:
                _, json_path = web_search.invoke({"query": q})
                json_paths.append(json_path)

                # 결과 JSON을 토픽별 경로로 이동: ./resources/<topic_slug>/
                try:
                    res_dir = os.path.join(current_path, "resources", state.get("topic_slug") or "default")
                    Path(res_dir).mkdir(parents=True, exist_ok=True)
                    new_json_path = os.path.join(res_dir, os.path.basename(json_path))
                    if os.path.abspath(json_path) != os.path.abspath(new_json_path):
                        shutil.move(json_path, new_json_path)
                        json_path = new_json_path
                        json_paths[-1] = json_path
                    print(f"[web_search] saved → {json_path}")
                except Exception as e:
                    print(f"[WARN] resources JSON 이동 실패: {e}")

                # 인덱싱(가능하면)
                try:
                    _orig_count, chunk_count = add_web_pages_json_to_chroma(
                        json_path, namespace=ns, persist_directory=persist_dir
                    )
                    chunk_count = int(chunk_count or 0)
                    chunk_total += max(0, chunk_count)
                    if chunk_count > 0:
                        ingest_success += 1
                except Exception as e:
                    print(f"[WARN] add_web_pages_json_to_chroma 실패: {e}")

                # 프리뷰 문서
                try:
                    docs = web_page_json_to_documents(json_path)[:preview_limit]
                    docs = [d for d in docs if not _is_bad_doc(d)]
                    for d in docs:
                        src = ((getattr(d, "metadata", {}) or {}).get("source") or "unknown")
                        if src and src != "unknown":
                            added_preview_urls.add(src)
                        new_docs_preview.append(
                            Document(page_content=(d.page_content or "")[:500], metadata={"source": src})
                        )
                except Exception as e:
                    print(f"[WARN] preview build 실패: {e}")

                queries.append(q)
                return True
            except Exception as e:
                if attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                print(f"[WARN] web_search 실패(재시도 후): {q} -> {e}")
                return False

    # ── 1) 플래너 설계 쿼리(최우선) ───────────────────────────────────────
    planner_qs = list(state.get("planner_queries") or [])
    if planner_qs:
        if not SKIP_WEB:
            print("[WEB SEARCH AGENT] planner queries:", planner_qs)
            for q in planner_qs:
                if q and (q not in queries):
                    _run_web_search_with_guard(q)
        else:
            print("[WEB SEARCH AGENT] (skip) planner queries ignored:", planner_qs)
        state["planner_queries"] = []  # 한 번 소비 후 비움

    # ── 2) 강제 쿼리(사용자 지시) ─────────────────────────────────────────
    try:
        forced_queries = extract_forced_queries_from_messages(messages, lookback=20)
    except Exception:
        forced_queries = []

    if forced_queries:
        if not SKIP_WEB:
            print("[WEB SEARCH AGENT] forced queries:", forced_queries)
            for q in forced_queries:
                q = (q or "").strip()
                if not q:
                    continue
                key = q.lower()
                if key in _existing_qs:
                    print(f"[WEB SEARCH AGENT] skip duplicate (forced): {q}")
                    continue
                print("-------- web search --------", {"query": q})
                if _run_web_search_with_guard(q):
                    _existing_qs.add(key)  # 성공 시에만 기록
        else:
            print("[WEB SEARCH AGENT] (skip) forced queries ignored:", forced_queries)

    # ── 3) LLM 설계 쿼리(툴콜 실행) ────────────────────────────────────────
    if not SKIP_WEB:
        llm_with_web = llm.bind_tools([web_search])
        search_plans = (web_search_system_prompt | llm_with_web).invoke(inputs)
        ran = 0
        for args in iter_tool_calls(search_plans, "web_search"):
            if ran >= MAX_SEARCH_QUERIES_PER_ROUND:
                break
            q = (args.get("query") or "").strip()
            if q and (q not in queries):
                print("-------- web search --------", {"query": q})
                _run_web_search_with_guard(q)
                ran += 1
    else:
        print("[WEB SEARCH AGENT] (skip) LLM-designed web queries suppressed.")

    # ── 4) Fallback(auto) ─────────────────────────────────────────────────
    def _fallback_auto_queries():
        topic = state.get("topic_title") or ""
        base = [
            f"{topic} 2025 overview",
            f"{topic} market size 2025",
            f"{topic} key trends Korea 2025",
            f"{topic} supply chain risks 2025",
            f"{topic} policy & regulation Korea 2025",
        ]
        extra = []
        if outline_text:
            for line in outline_text.splitlines():
                line = _clean_seed(line.strip())
                if not line:
                    continue
                if len(extra) >= 2:
                    break
                extra.append(f"{line[:40]} 2025 overview")
        return base + extra

    auto_mode = "rag_update:auto" in mission.lower()
    if auto_mode and not queries:
        if not SKIP_WEB:
            for q in _fallback_auto_queries():
                q = (q or "").strip()
                if not q:
                    continue
                key = q.lower()
                if key in _existing_qs:
                    print(f"[WEB SEARCH AGENT] skip duplicate (fallback): {q}")
                    continue
                if _run_web_search_with_guard(q):
                    _existing_qs.add(key)
        else:
            print("[WEB SEARCH AGENT] (skip) auto-fallback web queries suppressed.")

    # ── 5) 내부 파일(Local) 인덱싱 ────────────────────────────────────────
    # 5-1) ENV로 글롭 전달
    env_globs = [g.strip() for g in (os.getenv("LOCAL_RAG_GLOBS", "") or "").split("|") if g.strip()]

    slug = state.get("topic_slug") or ""
    slug_or_wc = slug if slug else "**"  # 슬러그가 없으면 와일드카드로 폴백

    def _normalize_and_expand(p: str) -> str:
        p = p.replace("<topic-slug>", slug_or_wc)
        # 윈/리눅스 겸용 슬래시 정리
        p = p.replace("\\", os.sep).replace("/", os.sep)
        return p

    local_globs: list[str] = [_normalize_and_expand(p) for p in env_globs]

    # 5-2) 채팅 명령: "add_local: C:\refs\*.pdf; notes/**/*.md"
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and isinstance(last_human.content, str):
        m = re.search(r"(?:add_local|local_rag|내부자료|내부문서)\s*:\s*(.+)", last_human.content, flags=re.I)
        if m:
            arg = m.group(1)
            for token in re.split(r"[|;,]", arg):
                t = token.strip()
                if t:
                    local_globs.append(_normalize_and_expand(t))

    # 5-3) 글롭 중복 제거(순서 보존)
    seen = set()
    dedup_globs = []
    for g in local_globs:
        key = g.lower() if os.name == "nt" else g
        if key in seen:
            continue
        seen.add(key)
        dedup_globs.append(g)

    # 5-4) 사전 스캔(매칭 파일 수 로그)
    debug_matches_total = 0
    if not dedup_globs:
        print("[LOCAL SCAN] 구성된 글롭이 없습니다. LOCAL_RAG_GLOBS 환경변수 또는 add_local 명령을 확인하세요.")
    else:
        for pat in dedup_globs:
            pat_abs = pat if os.path.isabs(pat) else os.path.join(current_path, pat)
            found = list(glob.iglob(pat_abs, recursive=True))
            print(f"[LOCAL SCAN] {pat}  -> {len(found)} file(s)")
            if len(found) == 0:
                print(f"[LOCAL SCAN]   ↳ 경로를 확인하세요: {pat_abs}")
            debug_matches_total += len(found)
        if debug_matches_total == 0:
            print("[LOCAL SCAN] 모든 글롭이 0개 매칭입니다. 폴더/파일 유무 또는 패턴을 점검하세요.")

    # 5-5) 실제 인덱싱
    if dedup_globs:
        print("[WEB SEARCH AGENT] ingest local refs:", dedup_globs)
        l_jsons, l_docs, l_chunks = ingest_local_files(
            dedup_globs,
            namespace=ns,
            persist_directory=persist_dir,
            topic_slug=slug or "default",
            root_dir=current_path,
            add_web_pages_json_to_chroma=add_web_pages_json_to_chroma,
            web_page_json_to_documents=web_page_json_to_documents,
        )
        # 보고/집계
        json_paths.extend(l_jsons)
        new_docs_preview.extend(l_docs)
        chunk_total += int(l_chunks or 0)

        # 참고 쿼리 목록에도 흔적 남기기(중복방지 세트는 위에서 유지)
        for g in dedup_globs:
            q = f"local:{g}"
            if q.lower() not in _existing_qs:
                queries.append(q)
                _existing_qs.add(q.lower())

    # ── 상태 갱신/라운드 결과 ────────────────────────────────────────────
    state["references"] = merge_refs(state.get("references"), queries, new_docs_preview)

    if COUNT_PREVIEW_URLS:
        new_url_count = chunk_total if chunk_total > 0 else len(added_preview_urls)
    else:
        new_url_count = chunk_total

    if MAX_INDEXED_PER_ROUND > 0:
        new_url_count = min(new_url_count, MAX_INDEXED_PER_ROUND)

        n = int(new_url_count)
        state["new_url_count"] = n
        state["new_url_count_round"] = n
        state["round_new_urls"] = n
        print(f"[DEBUG] new_url_count this round = {n}")

        pending.done = True
        pending.done_at = _now_str()

        if not has_pending(tasks, "vector_search_agent"):
            desc = "RAG 인덱싱을 위한 벡터 검색/검증을 수행한다."
            if queries:
                desc += f" queries={queries}"
            if json_paths:
                desc += f" json_paths={json_paths}"
            tasks.append(Task(agent="vector_search_agent", done=False, description=desc, done_at=""))

        mode_label = "로컬 전용" if SKIP_WEB else "웹+로컬"
        messages.append(
            AIMessage(
                f"[WEB SEARCH AGENT] 검색 완료({len(queries)}건). JSON 저장 및 Chroma 적재(또는 프리뷰) 완료. 모드={mode_label}"
                + (f" (예: {json_paths[0]})" if json_paths else "")
            )
        )

        return {
            "messages": messages,
            "task_history": tasks,
            "references": state["references"],
            "new_url_count": n,
            "new_url_count_round": n,
            "round_new_urls": n,
        }

# ── Research Planner / Synthesizer ==========================================

def research_planner(state: State):
    print("\n\n============ RESEARCH PLANNER ============")
    state = sanitize_numeric_state(state)

    max_iter = state["iteration_count"]
    rnd = state["research_round"]

    objs = state.get("research_objectives") or []
    if not objs:
        return {"messages": state["messages"], "task_history": state["task_history"]}

    # ✅ 본인 pending 태스크 정리
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
    queries = [q.strip("-• ").strip() for q in queries_text.splitlines() if q.strip()]
    state["planner_queries"] = queries  # ← 플래너 설계 쿼리를 상태에 저장

    # 👇 화면/대화 모두에 남길 플랜 텍스트
    plan_msg = (
        f"[Research Planner] Round {rnd + 1} objective: {current_obj}\n"
        "Queries:\n" + "\n".join(f"- {q}" for q in queries)
    )

    # 콘솔에 바로 보여주기
    print("\n" + plan_msg)

    # 대화 메시지에도 기록 (⚠️ 중복 append 금지)
    messages = state.get("messages", [])
    messages.append(AIMessage(plan_msg))

    # (옵션) 플랜을 한 번 말해주고 진행하려면: 환경변수/플래그로 토글
    announce = os.getenv("RESEARCH_PLANNER_ANNOUNCE", "0") == "1" or as_int(state, "research_planner_announce", 0) == 1
    if announce and not has_pending(tasks, "communicator"):
        tasks.append(Task(agent="communicator", done=False, description="announce_planner", done_at=""))

    # 검색 단계 예약
    if not has_pending(tasks, "web_search_agent"):
        tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))

    return {"messages": messages, "task_history": tasks}


def research_synthesizer(state: State):
    print("\n\n============ RESEARCH SYNTHESIZER ============")
    state = sanitize_numeric_state(dict(state))

    # --- 안전한 값 읽기/캐스팅 ---
    rnd = as_int(state, "research_round", 0)
    max_iter = max(1, as_int(state, "iteration_count", 1))

    refs = state.get("references") or {"queries": [], "docs": []}
    docs = list(refs.get("docs") or [])

    # ── 라운드 신규 URL 수: 여러 키 호환 + 값이 있을 때만 정규화 기록
    def _pick_round_new_urls(st: dict) -> Optional[int]:
        for k in ("new_url_count_round", "round_new_urls", "new_urls", "new_url_count"):
            if k in st and st[k] is not None and str(st[k]).strip() != "":
                try:
                    return max(0, int(str(st[k]).strip()))
                except Exception:
                    continue
        return None

    round_new_urls = _pick_round_new_urls(state)
    if round_new_urls is None:
        print(f"[SYNTH] round={rnd+1}/{max_iter}, round_new_urls=? (missing)")
    else:
        # 값이 있을 때만 표준 키로 동기화(덮어쓰기)
        state["new_url_count"] = round_new_urls
        state["new_url_count_round"] = round_new_urls
        state["round_new_urls"] = round_new_urls
        print(f"[SYNTH] round={rnd+1}/{max_iter}, round_new_urls={round_new_urls}")

    def _as_int_env_first(env_key: str, state_key: str, default: int) -> int:
        v = os.getenv(env_key)
        if v is not None and str(v).strip() != "":
            try:
                return int(v)
            except:
                pass
        return as_int(state, state_key, default)

    halt_threshold = _as_int_env_first("RESEARCH_HALT_THRESHOLD", "research_halt_threshold", 0)
    prev_streak = as_int(state, "no_new_url_streak", 0)
    if round_new_urls is None:
        streak = prev_streak
    elif round_new_urls <= halt_threshold:
        streak = prev_streak + 1
    else:
        streak = 0
    state["no_new_url_streak"] = streak
    print(f"[SYNTH] no_new_url_streak → {streak} (threshold={halt_threshold})")

    # --- 스니펫 구성 ---
    if docs:
        scored = sorted(docs, key=_score_doc, reverse=True)[:20]
        brief, seen = [], set()
        for d in scored:
            meta = getattr(d, "metadata", None)
            if meta is None and isinstance(d, dict):
                meta = d.get("metadata", {})
            meta = meta or {}

            page_content = getattr(d, "page_content", None)
            if page_content is None and isinstance(d, dict):
                page_content = d.get("page_content", "")
            page_content = page_content or ""

            src = meta.get("source") or meta.get("url") or "unknown"
            txt = _clean_snip(page_content, 420)
            key = (src, txt)
            if key in seen:
                continue
            seen.add(key)
            brief.append(f"- [{src}] {txt}")
        snippets = "\n".join(brief) if brief else "(자료 부족)"
    else:
        snippets = "(자료 부족)"

    # --- LLM 요약 (실패 대비) ---
    synth_prompt = get_research_synthesizer_prompt()
    try:
        findings = (synth_prompt | llm | StrOutputParser()).invoke({"snippets": snippets})
    except Exception as e:
        findings = f"""[Fallback Summary]
LLM 호출 실패로 간략 요약을 제공합니다.
에러: {type(e).__name__}: {e}
---
{snippets[:2000]}
"""

    # --- 파일 저장 ---
    topic = state.get("topic_slug") or "default"
    outdir = os.path.join(current_path, "research", topic)
    try:
        Path(outdir).mkdir(parents=True, exist_ok=True)
        out_path = os.path.join(outdir, f"round-{rnd + 1:02d}-findings.md")
        Path(out_path).write_text(findings, encoding="utf-8")
        saved_msg = f"[Research Synthesizer] Round {rnd + 1} findings saved → {out_path}"
    except Exception as e:
        out_path = None
        saved_msg = f"[Research Synthesizer] Round {rnd + 1} findings generated (file save failed: {e})"

    # --- 메시지 / 파일목록 안전 갱신 ---
    msgs = list(state.get("messages") or [])
    msgs.append(AIMessage(saved_msg))

    findings_md = list(state.get("findings_md") or [])
    if out_path:
        findings_md.append(out_path)

    # --- 라운드 증가: 조기중단은 라우터에 위임 ---
    next_round = min(rnd + 1, max_iter)

    # --- 태스크 계획 ---
    tasks = list(state.get("task_history") or [])
    if next_round < max_iter:
        try:
            already_planning = has_pending(tasks, "research_planner", prefix="plan_")
        except Exception:
            already_planning = False
        if not already_planning:
            tasks.append(Task(agent="research_planner", done=False, description="plan_next", done_at=""))
    else:
        writer = WRITER_AGENT
        if not has_pending(tasks, writer, prefix="write"):
            outline_text = get_topic_outline_text(state)
            fallback_default = "Executive Summary" if DOC_MODE == "report" else "서문"
            requested_title = get_last_write_target(msgs, tasks)
            auto_title = next_unwritten_title(
                outline_text, mode=DOC_MODE, root_dir=current_path, topic_slug=state.get("topic_slug")
            )
            target_title = requested_title or auto_title or fallback_default
            tasks.append(Task(agent=writer, done=False, description=f"write: {target_title}", done_at=""))

    return {
        **state,
        "messages": msgs,
        "task_history": tasks,
        "findings_md": findings_md,
        "research_round": next_round,
        "last_synthesis": findings,
    }

# ── Vector Search Agent ======================================================

def vector_search_agent(state: State):
    print("\n\n============ VECTOR SEARCH AGENT ============")
    state = sanitize_numeric_state(state)

    tasks = state.get("task_history", []) or []
    messages = state.get("messages", []) or []
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "vector_search_agent"), None)
    if pending is None:
        last = tasks[-1]
        if (last.agent == "vector_search_agent") and (not last.done):
            pending = last
        else:
            raise ValueError(f"vector_search_agent pending task가 없습니다. 현재 마지막 태스크: {tasks[-1]}")

    vector_search_system_prompt = get_vector_search_prompt()

    mission = (pending.description or "")
    references = state.get("references", {"queries": [], "docs": []}) or {"queries": [], "docs": []}
    outline_text = get_topic_outline_text(state)
    ns = state.get("chroma_ns") or os.getenv("CHROMA_NAMESPACE") or "default"

    # ★ 검색/인덱싱 공통 persist_dir 고정
    persist_dir = state.get("topic_slug") and _topic_dir(state["topic_slug"]) or (
        os.getenv("CHROMA_DIR") or _default_chroma_dir(ns)
    )
    TOP_K = int(os.getenv("RAG_TOP_K", "6"))

    # ─────────────────────────────────────────────────────────────
    # (옵션) on-demand 로컬 인덱싱 (웹 스킵 환경에서 web_search_agent를 안 거쳐도 1회 보장)
    # ─────────────────────────────────────────────────────────────
    # try 직전
    l_chunks = 0  # ← 기본 0으로 초기화

    try:
        ensure_local = os.getenv("SKIP_WEB_SEARCH", "0") == "1"
        local_globs_env = os.getenv("LOCAL_RAG_GLOBS", "")
        need_local = ensure_local and bool(local_globs_env.strip())
        not_yet = not state.get("local_ingested_once")
        if need_local and not_yet:
            from tools.local_rag import ingest_local_files
            # (주의) 아래 두 함수는 상위 스코프에 import 되어 있어야 합니다.
            # from tools.web_rag import add_web_pages_json_to_chroma, web_page_json_to_documents
            slug = state.get("topic_slug") or "default"

            raw_globs = [g.strip() for g in local_globs_env.split("|") if g.strip()]

            def _norm(p: str) -> str:
                p = p.replace("<topic-slug>", slug or "**")
                return p.replace("\\", os.sep).replace("/", os.sep)

            dedup, seen = [], set()
            for g in (_norm(x) for x in raw_globs):
                k = g.lower() if os.name == "nt" else g
                if k in seen:
                    continue
                seen.add(k)
                dedup.append(g)

            if dedup:
                print("[VECTOR SEARCH AGENT] on-demand local ingest:", dedup)
                l_jsons, l_docs, l_chunks = ingest_local_files(
                    dedup,
                    namespace=ns,
                    persist_directory=persist_dir,   # ★ 동일 persist_dir
                    topic_slug=slug,
                    root_dir=current_path,
                    add_web_pages_json_to_chroma=add_web_pages_json_to_chroma,
                    web_page_json_to_documents=web_page_json_to_documents,
                )
                if l_docs:
                    references = merge_refs(references, [], l_docs)
                    state["references"] = references
                state["local_ingested_once"] = True
    except Exception as e:
        print(f"[WARN] on-demand local ingest 실패: {e}")

    # on-demand ingest 결과 변수: l_chunks (인덱싱된 청크 수)
    new_url_count = int(l_chunks or 0)
    state["new_url_count"] = new_url_count
    state["new_url_count_round"] = new_url_count
    state["round_new_urls"] = new_url_count

    # ★ 여기서 미리 누적 버퍼 선언 (user_q 분기에서 바로 사용하므로)
    ran_queries: list[str] = []
    accum_queries: list[str] = []
    accum_docs: list = []

    # 사용자 질의 전처리
    def _extract_user_query(s: str) -> str:
        if not isinstance(s, str):
            return ""
        s = s.strip()
        if s.lower() in {"최신 자료로 rag 업데이트", "최신 자료로 rag 업데이트.", "최신 자료 업데이트", "rag 업데이트"}:
            return ""
        s = s.strip(" \"'“”‘’`")
        s = re.sub(r"^write\s*:\s*", "", s, flags=re.I).strip()
        s = re.sub(r"(요약해줘|요약|정리해줘|정리)\s*[\.\!\?…]*\s*$", "", s).strip()
        s = re.sub(r"[\.\!\?…]+$", "", s).strip()
        m = re.search(r"[A-Za-z0-9_]{6,}", s)
        return (m.group(0) if m else s) if len(s) >= 2 else ""

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    user_q = _extract_user_query(last_human.content) if (last_human and isinstance(last_human.content, str)) else ""

    # --- 사용자 질의 우선 검색 ---
    if user_q:
        try:
            print("-----------------------------------", {"name": "retrieve", "args": {"query": user_q, "top_k": TOP_K}})
            retrieved_docs = retrieve.invoke({
                "query": user_q,
                "namespace": ns,
                "persist_directory": persist_dir,
                "top_k": TOP_K
            })
            accum_queries.append(user_q)
            accum_docs.extend(retrieved_docs)
            ran_queries.append(user_q)
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{user_q}'): {e}")
            retrieved_docs = []

        # 병합(early return 전에)
        state["references"] = merge_refs(references, accum_queries, accum_docs)
        references = state["references"]

        # 디버그 출력
        print(f"[DEBUG] ns={ns} persist_dir={persist_dir} TOP_K={TOP_K} ALLOW_LOCAL_SUMMARY={os.getenv('ALLOW_LOCAL_SUMMARY')}")
        print(f"[DEBUG] retrieved_docs={len(retrieved_docs)} for user_q={user_q!r}")
        for i, d in enumerate((retrieved_docs or [])[:2], 1):
            meta = getattr(d, "metadata", {}) or {}
            snip = (getattr(d, "page_content", "") or "")[:100].replace("\n", " ")
            print(f"[DEBUG] ctx{i} source={meta.get('source')} snip={snip!r}")

        if os.getenv("ALLOW_LOCAL_SUMMARY", "0") == "1":
            # 컨텍스트 구축
            ctx_parts = []
            for d in (retrieved_docs or [])[:3]:
                txt = (getattr(d, "page_content", "") or "").strip()
                if txt:
                    ctx_parts.append(txt[:1200])
            context = "\n\n---\n\n".join(ctx_parts).strip()

            if context:
                prompt = (
                    "다음 컨텍스트만 근거로 한국어로 1문단 요약을 작성하세요.\n"
                    f"질문: {user_q}\n\n"
                    f"컨텍스트:\n{context}\n\n"
                    "지시사항:\n- 컨텍스트 밖의 지식은 쓰지 말 것\n- 불확실하면 모른다고 말할 것\n- 1문단(3~5문장)으로 간결히"
                )
                try:
                    ans = llm.invoke(prompt)
                    reply_text = ans if isinstance(ans, str) else getattr(ans, "content", "")
                    messages.append(AIMessage(reply_text))

                    # ✅ 직답 모드 플래그를 남겨 라우터가 Synthesizer로 가지 않게 함
                    state["qa_direct_reply"] = True

                    # (선택) 라우터/합성 단계에서 쓰는 카운터 키도 최소값으로 채워 'missing' 경고 방지
                    for k in ("new_url_count", "new_url_count_round", "round_new_urls"):
                        state[k] = int(state.get(k, 0) or 0)

                    # ✅ 바로 커뮤니케이터만 돌도록 Task 예약(중복 방지)
                    if not has_pending(tasks, "communicator"):
                        tasks.append(Task(agent="communicator", done=False,
                                        description="사용자 질의에 대한 요약 답변 전달", done_at=""))
                        
                    pending.done = True
                    pending.done_at = _now_str()
                    return {"messages": messages, "task_history": tasks, "references": references}
                except Exception as e:
                    print(f"[WARN] QA 요약 생성 실패: {e}")
            else:
                messages.append(AIMessage("요청과 직접 매칭되는 로컬 문서를 찾지 못했어요. 파일 경로/패턴(LOCAL_RAG_GLOBS)을 확인해 주세요."))
                # ✅ 직답 모드 플래그를 남겨 라우터가 Synthesizer로 가지 않게 함
                state["qa_direct_reply"] = True

                # (선택) 라우터/합성 단계에서 쓰는 카운터 키도 최소값으로 채워 'missing' 경고 방지
                for k in ("new_url_count", "new_url_count_round", "round_new_urls"):
                    state[k] = int(state.get(k, 0) or 0)

                if not has_pending(tasks, "communicator"):
                    tasks.append(Task(agent="communicator", done=False, description="안내 전달 및 다음 요청 확인", done_at=""))
                pending.done = True
                pending.done_at = _now_str()
                return {"messages": messages, "task_history": tasks, "references": references}

    # 여기서부터는 기존 LLM 설계 질의/기보유 쿼리 실행 루틴
    inputs = {
        "mission": mission,
        "references": references,
        "messages": messages,
        "outline": outline_text,
        "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
    }

    llm_with_retriever = llm.bind_tools([retrieve])
    search_plans = (vector_search_system_prompt | llm_with_retriever).invoke(inputs)
    preexisting_queries = list(references.get("queries", []))

    # 4) LLM 설계 질의 실행
    for args in iter_tool_calls(search_plans, "retrieve"):
        query = _clean_seed((args.get("query") or ""))
        if not _ok_query(query) or (query in ran_queries):
            continue
        print("-----------------------------------", {"name": "retrieve", "args": {"query": query, "top_k": TOP_K}})
        try:
            retrieved_docs = retrieve.invoke({
                "query": query,
                "namespace": ns,
                "persist_directory": persist_dir,   # ★ 동일 persist_dir
                "top_k": TOP_K
            })
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{query}'): {e}")
            continue
        accum_queries.append(query)
        accum_docs.extend(retrieved_docs)
        ran_queries.append(query)

    # 5) 기존/미실행 쿼리 실행
    for q in preexisting_queries:
        q = _clean_seed(q)
        if (not _ok_query(q)) or (q in ran_queries):
            continue
        print("-----------------------------------", {"name": "retrieve", "args": {"query": q, "top_k": TOP_K}})
        try:
            retrieved_docs = retrieve.invoke({
                "query": q,
                "namespace": ns,
                "persist_directory": persist_dir,   # ★ 동일 persist_dir
                "top_k": TOP_K
            })
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{q}'): {e}")
            continue
        accum_docs.extend(retrieved_docs)
        ran_queries.append(q)

    # 최종 병합
    state["references"] = merge_refs(references, accum_queries, accum_docs)
    references = state["references"]

    print("\n\nQueries:--------------------------")
    for q in references["queries"]:
        print(q)

    print("\n\nReferences:--------------------------")
    for i, doc in enumerate(references["docs"][:20], start=1):
        print(f"[{i:02d}] " + _plain_snip(getattr(doc, "page_content", "") or "", 160))
        print("--------------------------")

    pending.done = True
    pending.done_at = _now_str()

    # 연구 루프/집필 스케줄링 (기존 로직 유지)
    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)
    research_loop_active = (role == "research analyst") and bool(state.get("research_objectives")) and (rounds_done < max_iter)

    writer_agent = WRITER_AGENT
    if not research_loop_active:
        fallback_default = "Executive Summary" if DOC_MODE == "report" else "서문"
        requested_title = get_last_write_target(messages, tasks)
        auto_title = next_unwritten_title(
            outline_text, mode=DOC_MODE, root_dir=current_path, topic_slug=state.get("topic_slug")
        )
        target_title = requested_title or auto_title or fallback_default

        AUTO_WRITE = os.getenv("AUTO_WRITE_AFTER_RAG", "1") == "1"
        if AUTO_WRITE and not has_pending(tasks, writer_agent, prefix="write"):
            tasks.append(Task(agent=writer_agent, done=False, description=f"write: {target_title}", done_at=""))
        else:
            if not has_pending(tasks, "communicator"):
                tasks.append(Task(agent="communicator", done=False, description="검색/인덱싱 완료 보고 및 다음 집필 대상 확인", done_at=""))
    else:
        messages.append(AIMessage("[VECTOR SEARCH AGENT] 연구 라운드 진행 중 → 합성 단계(Research Synthesizer)로 이동"))

    messages.append(AIMessage(f"[VECTOR SEARCH AGENT] 다음 질문에 대한 검색 완료: {references['queries']}"))
    return {"messages": messages, "task_history": tasks, "references": references}


# ── Chapter Writer ===========================================================

def chapter_writer(state: State):
    if DOC_MODE != "book":
        print(f"[CHAPTER WRITER] Skipped: DOC_MODE={DOC_MODE} (expected 'book').")
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}
    print("\n\n============ CHAPTER WRITER ============")
    state = sanitize_numeric_state(state)

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "chapter_writer"), None)
    if pending is None:
        print("[WARN] pending 'chapter_writer' task가 없습니다. edge pass.")
        return {"messages": state.get("messages", []), "task_history": tasks}

    messages = state.get("messages", [])
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and is_outline_creation(last_human.content):
        now = _now_str()
        pending.done = True
        pending.done_at = now
        tasks.append(Task(agent="content_strategist", done=False, description="create_outline:auto", done_at=""))
        messages.append(AIMessage("[Chapter Writer] Outline 요청 감지 → content_strategist로 위임"))
        return {"messages": messages, "task_history": tasks}

    outline_text = get_topic_outline_text(state)
    if not outline_text.strip():
        # 목차가 없으면 자동으로 생성 태스크를 예약하고 챕터 라이팅은 보류
        fname = state.get("outline_fname") or "outline.md"
        if not has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(f"[Chapter Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        return {"messages": messages, "task_history": tasks}

    target_title = get_last_write_target(messages, tasks) or next_unwritten_title(
        outline_text, mode="book", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    if not target_title:
        messages.append(AIMessage("[Chapter Writer] 모든 목차 항목의 초안이 이미 작성되었습니다."))
        now = _now_str()
        pending.done = True
        pending.done_at = now
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="집필 완료 보고 및 편집 여부 확인", done_at=""))
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target chapter: {target_title}")
    ref_text = _refs_preview_text(state)

    chapter_writer_prompt = get_chapter_writer_prompt()
    writer_chain = chapter_writer_prompt | llm | StrOutputParser()
    gathered = ""
    for chunk in writer_chain.stream(
        {
            "target_title": target_title,
            "outline": outline_text,
            "references": ref_text,
            "messages": messages,
            "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
        }
    ):
        print(chunk, end="")
        gathered += chunk
    print()

    # 저장(content_utils)
    # 저장 전: 정량 문장 자동 각주 + 참고 자료 블록
    if os.getenv("AUTO_FOOTNOTE", "1") == "1":
        try:
            before_len = len(gathered)
            gathered = attach_auto_citations(gathered, state)
            if os.getenv("DEBUG_CITATION","0") == "1":
                print(f"[DEBUG] auto-citation applied: {before_len} → {len(gathered)} chars")
        except Exception as e:
            print(f"[WARN] auto-citation 실패: {e}")

    out_path = save_md_draft(
        target_title, gathered, mode="book", root_dir=current_path, topic_slug=state.get("topic_slug")
    )

    state["last_saved_path"] = out_path
    messages.append(AIMessage(f"[Chapter Writer] '{target_title}' 초안 작성 완료 → {out_path}"))

    pending.done = True
    pending.done_at = _now_str()

    if not has_pending(tasks, "communicator"):
        tasks.append(
            Task(agent="communicator", done=False, description=f"'{target_title}' 초안 완료 보고 및 다음 집필/수정 확인", done_at="")
        )

    return {"messages": messages, "task_history": tasks}


# ── Section Writer ===========================================================

def section_writer(state: State):
    if DOC_MODE != "report":
        print(f"[SECTION WRITER] Skipped: DOC_MODE={DOC_MODE} (expected 'report').")
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}
    print("\n\n============ SECTION WRITER ============")
    state = sanitize_numeric_state(state)

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "section_writer"), None)
    if pending is None:
        print("[WARN] pending 'section_writer' task가 없습니다. edge pass.")

    messages = state.get("messages", [])
    outline_text = get_topic_outline_text(state)
    if not outline_text.strip():
        # 목차가 없으면 자동으로 생성 태스크를 예약하고 섹션 라이팅은 보류
        fname = state.get("outline_fname") or "outline_report.md"
        if not has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(f"[Section Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        return {"messages": messages, "task_history": tasks}

    target_title = get_last_write_target(messages, tasks) or next_unwritten_title(
        outline_text, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    if not target_title:
        messages.append(AIMessage("[Section Writer] 모든 섹션 초안이 이미 작성되었습니다."))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="집필 완료 보고 및 편집 단계 여부 파악", done_at=""))
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target section: {target_title}")
    ref_text = _refs_preview_text(state)

    report_writer_prompt = get_section_writer_prompt()
    chain = report_writer_prompt | llm | StrOutputParser()
    gathered = ""
    for chunk in chain.stream(
        {
            "target_title": target_title,
            "outline": outline_text,
            "references": ref_text,
            "messages": messages,
            "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
        }
    ):
        print(chunk, end="")
        gathered += chunk
    print()

    # 저장 전: 정량 문장 자동 각주 + 참고 자료 블록
    if os.getenv("AUTO_FOOTNOTE", "1") == "1":
        try:
            before_len = len(gathered)
            gathered = attach_auto_citations(gathered, state)
            if os.getenv("DEBUG_CITATION","0") == "1":
                print(f"[DEBUG] auto-citation applied: {before_len} → {len(gathered)} chars")
        except Exception as e:
            print(f"[WARN] auto-citation 실패: {e}")

    out_path = save_md_draft(
        target_title, gathered, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug")
    )

    messages.append(AIMessage(f"[Section Writer] '{target_title}' 초안 작성 완료 → {out_path}"))
    state["last_saved_path"] = out_path
    print(f"[Section Writer] saved → {out_path}")

    now = _now_str()
    if pending:
        pending.done = True
        pending.done_at = now

    if not has_pending(tasks, "communicator"):
        tasks.append(
            Task(agent="communicator", done=False, description=f"'{target_title}' 초안 완료 보고 및 다음 섹션/수정 범위 확인", done_at="")
        )

    return {"messages": messages, "task_history": tasks}


# ── Communicator =============================================================

def communicator(state: State):
    print("\n\n============ COMMUNICATOR ============")
    state = sanitize_numeric_state(state)

    messages = state.get("messages", [])
    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
    desc = (pending.description if pending else "") or ""

    # 🔊 플래너 발표 모드
    if "announce_planner" in desc.lower():
        last_planner = next(
            (m for m in reversed(messages)
             if isinstance(m, AIMessage) and str(m.content or "").startswith("[Research Planner]")),
            None
        )
        text = last_planner.content if last_planner else "(리서치 플래너 메시지를 찾지 못했습니다.)"
        print("\nAI\t:\n" + text)
        messages.append(AIMessage(text))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        if not has_pending(tasks, "web_search_agent"):
            tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # show_outline 요청 처리
    show_outline_req = False
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    explicit_fname = None
    mdesc = re.search(r"show_outline\s*:\s*([A-Za-z0-9_\-\.]+)", desc)
    if mdesc:
        explicit_fname = mdesc.group(1).strip()
        show_outline_req = True
    if ("show_outline" in desc.lower()) or (last_human and is_outline_display(last_human.content)):
        show_outline_req = True

    if show_outline_req:
        preferred = state.get("outline_fname")
        default_by_mode = "outline_report.md" if DOC_MODE == "report" else "outline.md"
        fname = explicit_fname or preferred or default_by_mode
        state["outline_fname"] = fname

        outline_text, used_path = read_outline(
            filename=fname,
            root_dir=current_path,
            topic_slug=state.get("topic_slug"),
            mode=DOC_MODE,
            allow_fallbacks=False,
        )

        if not (outline_text or "").strip():
            if not has_pending(tasks, "content_strategist"):
                tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))

            note = f"({fname}) 파일이 아직 없습니다. 지금 기본 목차를 생성하겠습니다."
            print("\nAI\t:\n" + note)
            messages.append(AIMessage(note))
            state["outline_shown"] = False

            if pending:
                pending.done = True
                pending.done_at = _now_str()
            return {"messages": messages, "task_history": tasks, "outline_fname": fname}

        title = f"## 현재 목차 ({used_path.name if used_path else fname})"
        content = f"{title}\n\n{outline_text}"
        print("\nAI\t:\n" + content)
        messages.append(AIMessage(content))
        state["outline_shown"] = True

        # ✅ 자연스러운 후속 멘트 즉시 제공
        followup = (
            "목차를 확인했습니다. 다음 중 어떻게 진행할까요?\n"
            "1) 특정 섹션부터 바로 집필 → `write: 섹션명`\n"
            "2) 목차 수정 → 바꿀 제목/순서를 말씀해 주세요\n"
            "3) 최신 자료 보강 → `최신 자료로 RAG 업데이트`\n"
        )
        print("\nAI\t:\n" + followup)   # ← 콘솔 출력 추가
        messages.append(AIMessage(followup))
        if os.getenv("DEBUG_OUTLINE_SHOWN","0")=="1": print(f"[DEBUG] outline_shown={state.get('outline_shown')}")

        # 다음 턴에 대화 이어가도록 커뮤니케이터 1건 예약
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="목차 확인 후 다음 집필 대상/수정 요청 파악", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # 일반 커뮤니케이션
    fallback_outline = get_topic_outline_text(state)
    doc_label = "보고서" if DOC_MODE == "report" else "책"
    communicator_prompt = get_communicator_prompt()
    system_chain = communicator_prompt | llm

    text_buf = ""
    for chunk in system_chain.stream(
        {
            "messages": messages,
            "outline": fallback_outline,
            "doc_label": doc_label,
            "topic_title": state.get("topic_title") or "",
        }
    ):
        print(chunk.content, end="")
        text_buf += chunk.content
    messages.append(AIMessage(text_buf))

    # 마지막 저장 경로 힌트 부가
    try:
        base_text = messages[-1].content
        if not any(x in base_text for x in ["chapters\\", "sections\\", "chapters/", "sections/"]):
            last_save_path = None
            moved_note = None
            _p1 = re.compile(r"\[(?:Section|Chapter|Content)\s+Writer|(Content Strategist)\].*?→\s*(.+?\.md)\s*", flags=re.DOTALL)
            _p2 = re.compile(r"\[(?:Section|Chapter|Content)\s+Writer\]\s*moved.*?->\s*(.+?\.md)\s*", flags=re.DOTALL)
            for m in reversed(messages):
                if not isinstance(m, AIMessage):
                    continue
                m1 = _p1.search(m.content or "")
                if m1:
                    last_save_path = (m1.group(1) or "").strip()
                    break
                m2 = _p2.search(m.content or "")
                if m2:
                    last_save_path = (m2.group(1) or "").strip()
                    moved_note = " (파일이 자동 정리되어 sections로 이동되었습니다.)"
                    break
            if not last_save_path:
                lsp = (state or {}).get("last_saved_path")
                if isinstance(lsp, str) and lsp.strip():
                    last_save_path = lsp.strip()
            if last_save_path:
                try:
                    last_save_path = os.path.normpath(last_save_path)
                except Exception:
                    pass
                messages[-1] = AIMessage(base_text + f"\n\n최종 저장 경로: `{last_save_path}`" + (moved_note or ""))
    except Exception:
        pass

    if pending:
        pending.done = True
        pending.done_at = _now_str()

    return {"messages": messages, "task_history": tasks}


# ── Graph ====================================================================

graph_builder = StateGraph(State)

# Nodes
graph_builder.add_node("supervisor", supervisor)
graph_builder.add_node("communicator", communicator)
graph_builder.add_node("content_strategist", content_strategist)
graph_builder.add_node("vector_search_agent", vector_search_agent)
graph_builder.add_node("web_search_agent", web_search_agent)
graph_builder.add_node("chapter_writer", chapter_writer)
graph_builder.add_node("section_writer", section_writer)
graph_builder.add_node("research_planner", research_planner)
graph_builder.add_node("research_synthesizer", research_synthesizer)


def tail_task_router(state: State):
    # ✅ 목차 파일이 비어있거나 아직 한 번도 보여준 적이 없다면 → content_strategist
    outline_text = get_topic_outline_text(state)
    outline_missing = not (outline_text or "").strip()
    outline_not_shown = state.get("outline_shown") is False

    if outline_missing:
        return "content_strategist"   # 먼저 만들어야 함
    if outline_not_shown:
        return "communicator"         # 만들어졌으면 이제 보여주기

    allowed = {"chapter_writer", "section_writer", "communicator"}
    for t in reversed(state.get("task_history", [])):
        if (not t.done) and t.agent in allowed:
            return t.agent
    return WRITER_AGENT if WRITER_AGENT in {"chapter_writer", "section_writer"} else "chapter_writer"

def after_vector_router(state: State):
    # 직답 플래그가 있으면 바로 커뮤니케이터
    if state.get("qa_direct_reply"):
        return "communicator"
    
    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = int(state.get("research_round") or 0)
    max_iter = as_int(state,"iteration_count", 0)
    has_objs = bool(state.get("research_objectives"))

    if role == "research analyst" and has_objs and rounds_done < max_iter:
        return "research_synthesizer"
    return tail_task_router(state)

def after_planner_router(state: State):
    # ENV 또는 state 플래그로 제어
    announce = os.getenv("RESEARCH_PLANNER_ANNOUNCE", "0") == "1" or as_int(state, "research_planner_announce", 0) == 1
    return "communicator" if announce else "web_search_agent"


# 라우터 보강안: 상태키 표준화 + 조기중단 정확도 개선
def after_synthesizer_router(state: State):
    # 기본 카운터
    rounds_done = as_int(state, "research_round", 0)
    max_iter    = as_int(state, "iteration_count", 0)

    # 디버그(옵션): 키 스냅샷
    if os.getenv("DEBUG_ROUTER_KEYS") == "1":
        keys_preview = list(state.keys())[:40]
        print(f"[ROUTER] keys[:40]={keys_preview}")

    # ── 키 불일치 방어: 라운드의 신규 URL 수 읽기
    #   - 실제 파이프라인에 따라 "new_url_count_round" / "new_url_count" / "new_urls" 등 혼용 가능
    def first_int(state, keys, default=0):
        for k in keys:
            if k in state:
                return as_int(state, k, default)
        return default

    new_url_count = first_int(
        state,
        ["new_url_count", "new_url_count_round", "new_urls", "round_new_urls"],
        0,
    )

    # ── 임계값/최소라운드/무신규 연속라운드(ENV 우선, 없으면 state, 없으면 기본)
    def _pick(env_key, state_key, default):
        v = os.getenv(env_key)
        if v is not None and str(v).strip() != "":
            try:
                return int(v)
            except Exception:
                pass
        return as_int(state, state_key, default)

    halt_threshold = _pick("RESEARCH_HALT_THRESHOLD",       "research_halt_threshold",        0)
    min_rounds     = _pick("RESEARCH_MIN_ROUNDS",           "research_min_rounds",            1)
    max_no_new     = max(1, _pick("RESEARCH_MAX_NO_NEW_ROUNDS", "research_max_no_new_rounds", 1))
    streak         = as_int(state, "no_new_url_streak", 0)

    print(f"[ROUTER] after_synthesizer: rounds_done={rounds_done}, max_iter={max_iter}, "
          f"new_url_count={new_url_count}, halt_threshold={halt_threshold}, "
          f"min_rounds={min_rounds}, no_new_url_streak={streak}/{max_no_new}")

    # ── 중단 판정: 최소 라운드 충족 + (무신규 연속 라운드 ≥ 허용치)
    should_halt = (rounds_done >= max(1, min_rounds)) and (streak >= max_no_new)

    if rounds_done < max_iter and not should_halt:
        print("[ROUTER] → research_planner")
        return "research_planner"

    if should_halt:
        print(f"[ROUTER] halt: new_url_count<=threshold for {streak} round(s) → writer")
        return WRITER_AGENT # ← 보고서면 section_writer, 책이면 chapter_writer

    # 라운드 다 썼거나 기타 케이스 → 테일 라우팅
    nxt = tail_task_router(state)
    print(f"[ROUTER] → {nxt}")
    return nxt

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
        "research_planner": "research_planner",
    },
)

graph_builder.add_edge("content_strategist", "communicator")

graph_builder.add_conditional_edges(
    "research_planner",
    after_planner_router,
    {"communicator": "communicator", "web_search_agent": "web_search_agent"},
)

graph_builder.add_edge("web_search_agent", "vector_search_agent")

graph_builder.add_conditional_edges(
    "vector_search_agent",
    after_vector_router,
    {
        "research_synthesizer": "research_synthesizer",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",   # ← 추가
    },
)


graph_builder.add_conditional_edges(
    "research_synthesizer",
    after_synthesizer_router,
    {
        "research_planner": "research_planner",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",   # ← 추가
    },
)

graph_builder.add_edge("chapter_writer", "communicator")

graph_builder.add_edge("section_writer", "communicator")

graph_builder.add_edge("communicator", END)

# Compile graph
graph = graph_builder.compile()


# ── Mermaid 렌더 (선택) ------------------------------------------------------
HTML_TMPL = Template(
    """<!DOCTYPE html>
<html>
<head>
<meta charset=\"UTF-8\">
<script src=\"https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js\"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'default' });</script>
<style> body{margin:0;padding:16px;} </style>
</head>
<body><div class=\"mermaid\">$mmd</div></body>
</html>
"""
)


def render_mermaid_with_playwright(mmd: str, out_path: str, width: int = 1600, height: int = 1000):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("[INFO] Playwright 미설치: 그래프 렌더를 건너뜁니다.")
        return None
    html = HTML_TMPL.substitute(mmd=mmd)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(300)
        page.locator(".mermaid").screenshot(path=out_path)
        browser.close()
    return out_path


# ── 초기 상태 & CLI 루프 ──────────────────────────────────────────

def _initial_state(iteration_count: int, agent_role: str | None = None) -> State:
    default_outline = "outline_report.md" if DOC_MODE == "report" else "outline.md"
    base: State = {
        "messages": [
            SystemMessage(
                f"""
                너희 AI들은 사용자의 요구에 맞는 {('보고서' if DOC_MODE=='report' else '책')}을(를) 쓰는 작가팀이다.
                사용자가 사용하는 언어로 대화하라.
                현재시각은 {_now_str()}이다.
                """
            )
        ],
        "task_history": [],
        "references": {"queries": [], "docs": []},
        "agent_role": (agent_role or os.getenv("BLOCKAGI_AGENT_ROLE", "").strip().lower()),
        "iteration_count": int(iteration_count),
        "research_objectives": _load_objectives_from_env(),
        "research_round": 0,
        "findings_md": [],
        "llm_logs": [],
        "new_url_count": None,                 # ← 합성기 조기종료 방지(초기 None)
        "topic_slug": os.getenv("TOPIC_SLUG") or "default",  # ← 경로 일관성
        "outline_fname": default_outline,
        "outline_shown": False,               # ← 목차 실제 표시 여부 추적
    }
    return sanitize_numeric_state(base)

def read_user_input() -> str:
    r'''
    콘솔에서 멀티라인 입력을 한 번에 읽어오는 도우미.
    - 첫 줄이 ``` 또는 """ 면 '펜스 모드': 같은 펜스로 닫힐 때까지 읽음
    - 첫 줄이 \ 로 끝나면 줄연결 모드
    '''
    first = input("\nUser\t: ")
    s = first.strip()
    if s in ('```', '"""'):
        fence = s
        lines = []
        while True:
            line = input()
            if line.strip() == fence:
                break
            lines.append(line)
        return "\n".join(lines).strip()
    buf = first
    while buf.endswith("\\"):
        buf = buf[:-1] + "\n" + input()
    return buf.strip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--iteration_count",
        type=str,
        default=os.getenv("ITERATION_COUNT", os.getenv("BLOCKAGI_ITERATION_COUNT", "3")),
        help="연구 라운드 최대 횟수(정수/문자열 모두 허용)",
    )
    parser.add_argument(
        "--agent_role",
        type=str,
        default=os.getenv("BLOCKAGI_AGENT_ROLE", "").strip().lower(),
        help="'research analyst'로 설정하면 연구 라운드 모드 활성화",
    )
    parser.add_argument(
        "--render_graph",
        action="store_true",
        help="Mermaid 그래프 PNG 렌더",
    )
    args = parser.parse_args()

    iter_count = coerce_int(args.iteration_count, default=3)
    state: State = _initial_state(iteration_count=iter_count, agent_role=args.agent_role)

    if args.render_graph or os.getenv("RENDER_GRAPH", "0") == "1":
        try:
            mmd = graph.get_graph().draw_mermaid()
            out_png = absolute_path.replace(".py", ".png")
            if render_mermaid_with_playwright(mmd, out_png):
                print("Saved:", out_png)
        except Exception as e:
            print("[WARN] mermaid 렌더 실패:", e)

    while True:
        try:
            user_input = read_user_input()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ["exit", "quit", "q"]:
            print("Goodbye!")
            break

        state["messages"].append(HumanMessage(user_input))
        state = graph.invoke(state, config={"recursion_limit": 200})
        print("\n------------------------------------ MESSAGE COUNT\t", len(state["messages"]))
        save_state(current_path, state)
