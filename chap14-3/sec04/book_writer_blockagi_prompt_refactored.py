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
)

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
class State(TypedDict, total=False):
    messages: List[AnyMessage]
    task_history: List[Task]
    references: dict
    last_saved_path: str
    topic_title: str
    topic_slug: str
    chroma_ns: str
    outline_fname: str
    agent_role: str
    iteration_count: int
    research_round: int
    research_objectives: List[str]
    findings_md: List[str]
    llm_logs: List[dict]
    new_url_count: int | None


# ── 유틸 ──────────────────────────────────────────────────────────

def _clean_snip(s: str, n: int = 120) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ")
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:n] + ("..." if len(s) > n else ""))


_ASCII_NS_RE = re.compile(r'[^a-zA-Z0-9._-]+')


def _ascii_namespace(seed: str) -> str:
    s = _ASCII_NS_RE.sub('-', seed).strip('._-')
    if not s or not re.match(r'^[A-Za-z0-9].*[A-Za-z0-9]$', s):
        s = 'ns-' + hashlib.sha1(seed.encode('utf-8', 'ignore')).hexdigest()[:12]
    return s[:64]


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
    return "outline.md"


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
    state["references"] = {"queries": [], "docs": []}
    state["last_saved_path"] = ""
    os.makedirs(_topic_dir(slug), exist_ok=True)
    os.environ["CHROMA_NAMESPACE"] = ns
    os.environ["CHROMA_DIR"] = _topic_dir(slug)
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

    messages = state.get("messages", [])
    task_history = state.get("task_history", [])
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    last_text: str = (last_human.content if (last_human and isinstance(last_human.content, str)) else "").strip()

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

    # 새 토픽
    m_new = re.search(
        r"(?:새\s*(?:보고서|프로젝트)|주제\s*(?:변경|바꿔)|new\s*(?:report|project)|switch\s*(?:topic|report))\s*[:：]?\s*(?P<title>.*)$",
        last_text,
        re.I,
    )
    if m_new:
        maybe_title = (m_new.group("title") or "").strip() or "untitled report"
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
        task_history.append(Task(agent="communicator", done=False, description="진행상황 보고 및 의견 파악", done_at=""))

    return {"messages": messages, "task_history": task_history}


# ── Web Search Agent =========================================================

def web_search_agent(state: State):
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

    # 강제 쿼리
    try:
        forced_queries = extract_forced_queries_from_messages(messages, lookback=20)
    except Exception:
        forced_queries = []

    queries: list[str] = []
    json_paths: list[str] = []
    new_docs_preview: list[Document] = []

    ns = state.get("chroma_ns") or os.getenv("CHROMA_NAMESPACE") or "default"
    persist_dir = state.get("topic_slug") and _topic_dir(state["topic_slug"]) or None

    # ✅ 라운드 성과 집계용
    chunk_total = 0            # 실제 인덱싱된 청크 수 합
    ingest_success = 0         # 청크가 1개 이상 들어간 검색 배치 수
    added_preview_urls = set() # 프리뷰에서 본 고유 URL(폴백용)

    def _run_web_search_with_guard(q: str, preview_limit: int = 5, retries: int = 2) -> bool:
        nonlocal chunk_total, ingest_success, added_preview_urls
        def _is_bad_doc(d):
            txt = ((getattr(d, "page_content", None) or "")[:2000]).lower()
            return any(k in txt for k in [
                "access denied", "enable javascript", "just a moment", "security controls triggered"
            ])

        for attempt in range(retries + 1):
            try:
                _, json_path = web_search.invoke({"query": q})
                json_paths.append(json_path)

                # 인덱싱(가능하면)
                try:
                    orig_count, chunk_count = add_web_pages_json_to_chroma(
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

    # 1) 강제 쿼리 즉시 실행
    if forced_queries:
        print("[WEB SEARCH AGENT] forced queries:", forced_queries)
        for q in forced_queries:
            if q and (q not in queries):
                _run_web_search_with_guard(q)

    # 2) LLM으로 추가 질의 설계 → tool call 실행
    llm_with_web = llm.bind_tools([web_search])
    search_plans = (web_search_system_prompt | llm_with_web).invoke(inputs)
    for args in iter_tool_calls(search_plans, "web_search"):
        q = (args.get("query") or "").strip()
        if q and (q not in queries):
            print("-------- web search --------", {"query": q})
            _run_web_search_with_guard(q)

    # 3) Fallback (rag_update:auto & 아무것도 없을 때)
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
                line = line.strip("- ").strip()
                if not line:
                    continue
                if len(extra) >= 2:
                    break
                extra.append(f"{line[:40]} 2025 overview")
        return base + extra

    auto_mode = "rag_update:auto" in mission.lower()
    if auto_mode and not queries:
        for q in _fallback_auto_queries():
            _run_web_search_with_guard(q)

    # 상태 갱신
    state["references"] = merge_refs(state.get("references"), queries, new_docs_preview)

    # ✅ 다음 라운드 진행 여부 판단용:
    # 1순위: 실제 인덱싱 청크 수(>0이면 확실히 새로 들어간 것 있음)
    # 2순위: 프리뷰에서 본 고유 URL 수(폴백)
    state["new_url_count"] = (chunk_total if chunk_total > 0 else len(added_preview_urls))
    print(f"[DEBUG] new_url_count this round = {state.get('new_url_count')}")

    # ▼▼▼ 표준 키로 동기화(라우터/시디사이저가 어느 키를 읽더라도 동일)
    n_raw = state.get("new_url_count")
    if n_raw is not None:
        try:
            n = int(n_raw)
            state["new_url_count_round"] = n
            state["round_new_urls"] = n
        except Exception:
            pass
    # ▲▲▲

    pending.done = True
    pending.done_at = _now_str()

    # 다음 단계 예약
    if not has_pending(tasks, "vector_search_agent"):
        desc = "RAG 인덱싱을 위한 벡터 검색/검증을 수행한다."
        if queries:
            desc += f" queries={queries}"
        if json_paths:
            desc += f" json_paths={json_paths}"
        tasks.append(Task(agent="vector_search_agent", done=False, description=desc, done_at=""))

    messages.append(
        AIMessage(
            f"[WEB SEARCH AGENT] 검색 완료({len(queries)}건). JSON 저장 및 Chroma 적재(또는 프리뷰) 완료."
            + (f" (예: {json_paths[0]})" if json_paths else "")
        )
    )

    # ⚠️ 반환에 동기화된 키를 포함해 상태 반영을 확실히
    n = int(state.get("new_url_count") or 0)
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

    if not has_pending(tasks, "web_search_agent"):
        tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))

    state["messages"].append(
        AIMessage(
            f"[Research Planner] Round {rnd + 1} objective: {current_obj}\nQueries:\n" + "\n".join(f"- {q}" for q in queries)
        )
    )
    return {"messages": state["messages"], "task_history": tasks}


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
        print(f"[SYNTH] round={rnd+1}/{max_iter}, round_new_urls={round_new_urls}")
        # 값이 있을 때만 표준 키로 동기화(덮어쓰기)
        state["new_url_count"] = round_new_urls
        state["new_url_count_round"] = round_new_urls
        state["round_new_urls"] = round_new_urls

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

    tasks = state.get("task_history", [])
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
    references = state.get("references", {"queries": [], "docs": []})
    messages = state.get("messages", [])
    outline_text = get_topic_outline_text(state)

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
    ran_queries: list[str] = []
    accum_queries: list[str] = []
    accum_docs: list = []

    ns = state.get("chroma_ns") or os.getenv("CHROMA_NAMESPACE") or "default"

    for args in iter_tool_calls(search_plans, "retrieve"):
        query = (args.get("query") or "").strip()
        if not query:
            continue
        print("-----------------------------------", {"name": "retrieve", "args": {"query": query}})
        try:
            retrieved_docs = retrieve.invoke({"query": query, "namespace": ns})
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
            retrieved_docs = retrieve.invoke({"query": q, "namespace": ns})
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{q}'): {e}")
            continue
        accum_docs.extend(retrieved_docs)
        ran_queries.append(q)

    state["references"] = merge_refs(references, accum_queries, accum_docs)
    references = state["references"]

    print("\n\nQueries:--------------------------")
    for q in references["queries"]:
        print(q)

    print("\n\nReferences:--------------------------")
    for i, doc in enumerate(references["docs"][:20], start=1):
        print(f"[{i:02d}] " + _clean_snip(getattr(doc, "page_content", "") or "", 160))
        print("--------------------------")

    pending.done = True
    pending.done_at = _now_str()

    # ✅ 연구 루프 활성 여부 판단
    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)
    research_loop_active = (role == "research analyst") and bool(state.get("research_objectives")) and (rounds_done < max_iter)

    writer_agent = WRITER_AGENT
    if not research_loop_active:
         # 기존 동작(집필/커뮤니케이션 예약)
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
        # 연구 라운드가 남아있으면 합성 단계로 이어질 것이므로 태스크 추가 불필요
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
        raise ValueError("아웃라인이 비어 있습니다. 먼저 content_strategist로 생성/확정하세요.")

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
        raise ValueError("아웃라인이 비어 있습니다. 먼저 보고서 개요(목차)를 만드세요.")

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

    out_path = save_md_draft(
        target_title, gathered, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    messages.append(AIMessage(f"[Section Writer] '{target_title}' 초안 작성 완료 → {out_path}"))
    state["last_saved_path"] = out_path

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
        fname = explicit_fname or _pick_outline_filename(last_human.content if last_human else "")
        # 사용자가 본다고 한 파일명을 세션 기본으로 고정
        state["outline_fname"] = fname
        outline_text, used_path = read_outline(
            filename=fname,
            root_dir=current_path,
            topic_slug=state.get("topic_slug"),
            mode=DOC_MODE,
            allow_fallbacks=False,
        )
        if not (outline_text or "").strip():
            # 파일이 없으면 생성 태스크를 예약하고 사용자에게 알림
            if not has_pending(tasks, "content_strategist"):
                tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
            msg = f"({fname}) 파일이 아직 없습니다. 지금 기본 목차를 생성하겠습니다."
            print("\nAI\t:\n" + msg)          # ⬅️ 이 한 줄 추가
            messages.append(AIMessage(msg))
            if pending:
                pending.done = True
                pending.done_at = _now_str()
            return {"messages": messages, "task_history": tasks}

        title = f"## 현재 목차 ({used_path.name if used_path else fname})"
        content = f"{title}\n\n{outline_text}"
        print("\nAI\t:\n" + content)
        messages.append(AIMessage(content))

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

    # 마지막 저장 경로가 대화에 노출되지 않았다면 한 줄 덧붙임
    try:
        base_text = messages[-1].content
        if not any(x in base_text for x in ["chapters\\", "sections\\", "chapters/", "sections/"]):
            last_save_path = None
            moved_note = None
            _p1 = re.compile(r"\[(?:Section|Chapter)\s+Writer\].*?→\s*(.+?\.md)\s*", flags=re.DOTALL)
            _p2 = re.compile(r"\[(?:Section|Chapter)\s+Writer\]\s*moved.*?->\s*(.+?\.md)\s*", flags=re.DOTALL)
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
    allowed = {"chapter_writer", "section_writer", "communicator"}
    for t in reversed(state.get("task_history", [])):
        if (not t.done) and t.agent in allowed:
            return t.agent
    return WRITER_AGENT if WRITER_AGENT in {"chapter_writer", "section_writer"} else "chapter_writer"


def after_vector_router(state: State):
    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = int(state.get("research_round") or 0)
    max_iter = as_int(state,"iteration_count", 0)
    has_objs = bool(state.get("research_objectives"))

    if role == "research analyst" and has_objs and rounds_done < max_iter:
        return "research_synthesizer"
    return tail_task_router(state)


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
    def _as_int_env_first(env_key: str, state_key: str, default: int) -> int:
        val = os.getenv(env_key)
        if val is not None and str(val).strip() != "":
            try:
                return int(val)
            except Exception:
                pass
        return as_int(state, state_key, default)

    halt_threshold = _as_int_env_first("RESEARCH_HALT_THRESHOLD",       "research_halt_threshold",        0)
    min_rounds     = _as_int_env_first("RESEARCH_MIN_ROUNDS",           "research_min_rounds",            1)
    max_no_new     = _as_int_env_first("RESEARCH_MAX_NO_NEW_ROUNDS",    "research_max_no_new_rounds",     1)
    max_no_new     = max(1, max_no_new)   # 0은 무의미 → 최소 1

    streak = as_int(state, "no_new_url_streak", 0)

    print(f"[ROUTER] after_synthesizer: rounds_done={rounds_done}, max_iter={max_iter}, "
          f"new_url_count={new_url_count}, halt_threshold={halt_threshold}, "
          f"min_rounds={min_rounds}, no_new_url_streak={streak}/{max_no_new}")

    # ── 중단 판정: 최소 라운드 충족 + (무신규 연속 라운드 ≥ 허용치)
    should_halt = (rounds_done >= max(1, min_rounds)) and (streak >= max_no_new)

    if rounds_done < max_iter and not should_halt:
        print("[ROUTER] → research_planner")
        return "research_planner"

    if should_halt:
        print(f"[ROUTER] halt: new_url_count<=threshold for {streak} round(s) → section_writer")
        return "section_writer"

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

graph_builder.add_edge("research_planner", "web_search_agent")

graph_builder.add_edge("web_search_agent", "vector_search_agent")

graph_builder.add_conditional_edges(
    "vector_search_agent",
    after_vector_router,
    {
        "research_synthesizer": "research_synthesizer",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",
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
    base = State(
        messages=[
            SystemMessage(
                f"""
                너희 AI들은 사용자의 요구에 맞는 {('보고서' if DOC_MODE=='report' else '책')}을(를) 쓰는 작가팀이다.
                사용자가 사용하는 언어로 대화하라.
                현재시각은 {_now_str()}이다.
                """
            )
        ],
        task_history=[],
        references={"queries": [], "docs": []},
        agent_role=(agent_role or os.getenv("BLOCKAGI_AGENT_ROLE", "").strip().lower()),
        iteration_count=int(iteration_count),
        research_objectives=_load_objectives_from_env(),
        research_round=0,
        findings_md=[],
        llm_logs=[],
        new_url_count=None,                 # ← 합성기 조기종료 방지(초기 None)
        topic_slug=os.getenv("TOPIC_SLUG") or "default",  # ← 경로 일관성
        outline_fname=default_outline,             # ⬅️ 추가
    )
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
