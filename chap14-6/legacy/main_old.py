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
import pickle
import hashlib
from pathlib import Path
from datetime import datetime
from string import Template
from typing import List, Optional, Literal, cast, Final, Mapping, Any, Required, NotRequired, Dict, TypedDict
from typing_extensions import TypedDict

from dotenv import load_dotenv, find_dotenv

dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, override=True) # override=True로 바꾸면 .env가 항상 최신으로 덮어씁
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
from models import Task, AgentName
from utils_forced_queries import extract_forced_queries_from_messages

from tools.web_rag import (
    retrieve,
    web_search,
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    _default_chroma_dir,
    clear_vector_store,
    ensure_vector_store_cleared_once,

)

from tools.local_rag import ingest_local_files

from content_utils import (
    read_outline,
    save_outline,
    save_md_draft,
    next_unwritten_title,
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
    sanitize_numeric_state_generic,
)

from utils.citation_utils import attach_auto_citations

from settings_gatekeep import gatekeep_enabled, get_allowed_domains

import argparse

# ── 경로/전역 ─────────────────────────────────────────────────────
absolute_path = os.path.abspath(__file__)
current_path = os.path.dirname(absolute_path)


def _now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return datetime.now().strftime(fmt)

# def _doc_mode() -> str:
#     return (os.getenv("DOC_MODE", "book") or "book").strip('"').strip().lower()

# DOC_MODE = _doc_mode()

Mode = Literal["book", "report"]

def _doc_mode() -> Mode:
    v = (os.getenv("DOC_MODE", "book") or "book").strip('"').strip().lower()
    # 안전 캐스팅: 허용값 아니면 기본 "report"로
    return cast(Mode, v if v in ("book", "report") else "report")

DOC_MODE: Final[Mode] = _doc_mode()


def preferred_writer_agent() -> AgentName:
    return "section_writer" if DOC_MODE == "report" else "chapter_writer"

WRITER_AGENT: Final[AgentName] = preferred_writer_agent()


# ── 간단 상태 저장기 ─────────────────────────────────────────────
def save_state(base_dir: str, state: Mapping[str, Any], fname: str = "last_state.pkl") -> None:
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
class ResearchPlan(TypedDict, total=False):
    round: int
    objective: str
    queries: List[str]
    timestamp: str

class State(TypedDict, total=False):
    messages: Required[list[Any]]
    # messages: List[AnyMessage]
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
    facts_ctx: Optional[str]
    _vs_cleared_once: bool | None
    research_plan: ResearchPlan  # ← 새로 추가
    flags: NotRequired[Dict[str, Any]]


# ── 유틸 ──────────────────────────────────────────────────────────
def _clean_snip(s: str, n: int = 120) -> str:
    s = (s or "").replace("\n", " ").replace("\r", " ")
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:n] + ("..." if len(s) > n else ""))


def _clean_seed(s: str) -> str:
    s = re.sub(r"^#+\s*", "", s)
    s = re.sub(r"^\d+[\.\)]\s*", "", s)
    s = re.sub(r"^(작성|write)\s*[:：]\s*", "", s, flags=re.I)
    s = s.strip(" -•—·\t")
    return s


def _ok_query(q: str) -> bool:
    q = (q or "").strip()
    if not q:
        return False
    q2 = _clean_seed(q)
    return bool(q2) and (len(q2) <= 200)

# ─────────────────────────────────────────────────────────────────────────────
# 검색 질의 정제: 웹 필터 토큰 제거 + 고아 Boolean 제거
import re as _re
_BOOLEAN_TOKENS = _re.compile(r"\b(?:AND|OR|NOT)\b", _re.IGNORECASE)

def _strip_web_filters(q: str) -> str:
    if not isinstance(q, str):
        return ""
    s = q
    # (site: a OR site:b ...) 블록 제거
    s = _re.sub(r"\(\s*site:[^)]+\)", " ", s, flags=_re.IGNORECASE)
    # 개별 site: / -site:
    s = _re.sub(r"-?\s*site:[^\s)]+", " ", s, flags=_re.IGNORECASE)
    # SNS/행사/티켓 음수 토큰 제거
    for w in ["event", "events", "exhibition", "tickets", "행사", "티켓", "myfair.co", "facebook.com", "instagram.com"]:
        s = _re.sub(rf"-\s*{_re.escape(w)}\b", " ", s, flags=_re.IGNORECASE)
    # 고아 Boolean 토큰 제거
    s = _BOOLEAN_TOKENS.sub(" ", s)
    # 단독 하이픈 제거
    s = _re.sub(r"\s-\s", " ", s)
    s = _re.sub(r"(^|\s)-($|\s)", " ", s)
    # 괄호/따옴표 및 공백 정리
    s = _re.sub(r"[()\"'“”‘’`]", " ", s)
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s


def _plain_snip(text: str, n: int = 160) -> str:
    t = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.I | re.S)
    t = re.sub(r"<style.*?>.*?</style>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return _clean_snip(t, n)


def _ascii_namespace(seed: str) -> str:
    core = hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()[:10]
    return f"ns-{core}"


def _slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^\w\-가-힣\s]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s or "untitled"

# >>> ANCHOR: LOCAL_GLOB_HELPER >>>
def _looks_like_local_glob(q: str) -> bool:
    """local: 접두나 글롭(**/*.md 등)처럼 보이는 쿼리는 True"""
    q = (q or "")
    ql = q.strip().lower()
    if ql.startswith("local:"):
        return True
    glob_tokens = ("**\\", "**/", "\\*.", "/*.", "\\**", "/**")
    exts = (".pdf", ".md", ".txt", ".html", ".docx", ".pptx")
    if any(tok in q for tok in glob_tokens) and any(ext in ql for ext in exts):
        return True
    if "*" in q and any(ext in ql for ext in exts):
        return True
    return False
# <<< ANCHOR: LOCAL_GLOB_HELPER <<<


def _topic_slug_from(text: str) -> str:
    base = _slugify(text or "untitled")
    return f"{base}-{datetime.now().strftime('%Y%m%d-%H%M')}"


def _topic_dir(slug: str) -> str:
    return os.path.join(current_path, "data", "chroma_store", slug)
# def _topic_dir(slug: Optional[str]) -> Optional[str]:
#     if not slug:
#         return None
#     return os.path.join(current_path, "data", "chroma_store", slug)


def _sanitize_title(raw: str) -> str:
    s = (raw or "")
    s = re.sub(r'^\s*(새\s*(보고서|프로젝트)\s*(작성)?\s*)[:：]?\s*', '', s, flags=re.I)
    while re.match(r'^\s*(작성|write)\s*[:：]\s*', s, flags=re.I):
        s = re.sub(r'^\s*(작성|write)\s*[:：]\s*', '', s, flags=re.I)
    return s.strip(' :\u3000-—–')


def _load_objectives_from_env(prefix: str = "BLOCKAGI_OBJECTIVE_") -> list[str]:
    objs = []
    for i in range(1, 11):
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
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            t = extract_write_title(m.content or "")
            if t:
                return t
    for t in reversed(tasks):
        title = extract_write_title(t.description or "")
        if title:
            return title
    return None


# ── Outline IO(토픽 인지) ────────────────────────────────────────
def _pick_outline_filename(user_text: Optional[str]) -> str:
    text = (user_text or "")
    # 책 목차 신호: 'AI/인공지능'이 있으면 가중치, 없어도 '책.*목차'면 책으로 간주
    if re.search(r"(?:ai|인공지능)?\s*.*책.*(목차|outline)", text, flags=re.I):
        return "outline_book.md"
    # 보고서 목차 신호
    if re.search(r"(보고서|report).*(목차|outline)", text, flags=re.I):
        return "outline_report.md"
    # 기본값: DOC_MODE에 따름
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
    state["outline_shown"] = False
    state["references"] = {"queries": [], "docs": []}
    state["last_saved_path"] = ""
    os.makedirs(_topic_dir(slug), exist_ok=True)
    os.environ["CHROMA_NAMESPACE"] = ns
    os.environ["CHROMA_DIR"] = _topic_dir(slug)

    if os.getenv("RESET_OBJECTIVES_ON_NEW_TOPIC", "1") == "1":
        state["research_objectives"] = _load_objectives_from_env()
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

def _facts_block(state: "State") -> str:
    """
    state['facts_ctx']를 안전하게 문자열 블록으로 변환.
    비어있으면 빈 문자열을 반환한다.
    """
    s = state.get("facts_ctx")
    if isinstance(s, str):
        s = s.strip()
        if s:
            return "\n\n[FACTS]\n" + s
    return ""

def _score_doc(d: Document, year_now: int = 2026) -> float:
    import tldextract, re
    meta = getattr(d, "metadata", {}) or {}
    src = (meta.get("source") or meta.get("url") or "").lower()
    text = (getattr(d, "page_content", "") or "")

    score = 0.0

    # 1) 도메인 레벨 판정
    domain = tldextract.extract(src).registered_domain  # 예: "iea.org"
    gov_edu = (domain.endswith(".go.kr") or domain.endswith(".gov") 
               or domain.endswith(".ac.kr") or domain.endswith(".edu"))
    if gov_edu:
        score += 3

    if any(k in domain for k in ["imf.org", "kostat.go", "kotra.or"]):
        score += 2

    if any(k in domain for k in ["kpmg", "mckinsey", "gartner", "idc"]):
        score += 1.5

    # 2) 연도 보정(최신 선호)
    m = re.search(r"\b(20\d{2})\b", src) or re.search(r"\b(20\d{2})\b", text)
    if m:
        yr = int(m.group(1))
        recency = max(0, 6 - (year_now - yr))
        score += recency * 0.2  # 최대 +1.2

    # 3) 저품질 신호 감점
    bad_signals = ["enable javascript", "captcha", "just a moment", "access denied"]
    if any(b in text.lower() for b in bad_signals):
        score -= 2

    return score

# ── Supervisor ===============================================================
def supervisor(state: State):
    print("\n\n============ SUPERVISOR ============")
    state = sanitize_numeric_state_generic(state)

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
    state.setdefault("agent_role", (state.get("agent_role") or os.getenv("BLOCKAGI_AGENT_ROLE", "")).strip())
    state.setdefault("iteration_count", int(state.get("iteration_count") or os.getenv("ITERATION_COUNT", "0")))

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
        state = start_new_topic(state, maybe_title, outline_fname=_pick_outline_filename(last_text))
        # msg = f"[Supervisor] 새 주제 세션 시작: '{state['topic_title']}' (ns={state['chroma_ns']})"
        # ★ f-string에서도 .get 사용 (기본값까지)
        # [ANCHOR] seed research config from env on NEW SESSION
        # - 새 프로젝트/보고서 시작 직후(state가 초기화된 직후)에 연구 루프용 설정을 주입
        state.setdefault("agent_role", (state.get("agent_role") or os.getenv("BLOCKAGI_AGENT_ROLE", "")).strip())
        state.setdefault("iteration_count", int(state.get("iteration_count") or os.getenv("ITERATION_COUNT", "0")))

        if not state.get("research_objectives"):
            objs = []
            for i in range(1, 10):  # BLOCKAGI_OBJECTIVE_1..9 까지 흡수
                v = os.getenv(f"BLOCKAGI_OBJECTIVE_{i}", "")
                if v and v.strip():
                    objs.append(v.strip())
            state["research_objectives"] = objs

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
            "references": state.get("references"),
            "last_saved_path": state.get("last_saved_path"),
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
    
    # [ANCHOR] research-mode preemption (insert BEFORE communicator fast-path)
    def _is_research_mode(st) -> bool:
        role = (st.get("agent_role") or "").strip().lower() or os.getenv("BLOCKAGI_AGENT_ROLE","").strip().lower()
        has_objs = bool(st.get("research_objectives"))
        max_iter = int(st.get("iteration_count") or os.getenv("ITERATION_COUNT","0"))
        return (role == "research analyst") and has_objs and (max_iter > 0)

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
            "references": state.get("references"),
            "last_saved_path": state.get("last_saved_path"),
        }

    # fast-path: 목차 생성/표시
    if is_outline_creation(last_text):
        fname = _pick_outline_filename(last_text)
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
        return {
            "messages": messages,
            "task_history": tasks,
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
        "references": state.get("references"),
        "last_saved_path": state.get("last_saved_path"),
    }


def supervisor_router(state: State):
    state = sanitize_numeric_state_generic(state)
    # state = sanitize_numeric_state(state)
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
    state = sanitize_numeric_state_generic(state)
    # state = sanitize_numeric_state(state)

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

    # 저장
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

    tasks = state.get("task_history", [])
    if not tasks or tasks[-1].agent != "content_strategist":
        raise ValueError("Content Strategist가 아닌 agent가 목차 작성을 시도했습니다.")
    tasks[-1].done = True
    tasks[-1].done_at = _now_str()

    if not has_pending(tasks, "communicator"):
        tasks.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))

    return {"messages": messages, "task_history": tasks}


# ── Web Search Agent =========================================================
def web_search_agent(state: State):
    # ────────────────────────────────────────────────────────────────────────────
    # Imports (내부 임포트 고정)
    import os, re, time, json, glob, shutil
    from pathlib import Path
    from langchain_core.messages import HumanMessage, AIMessage
    from langchain_core.documents import Document
    # ────────────────────────────────────────────────────────────────────────────
    print("\n\n============ WEB SEARCH AGENT ============")
    state = sanitize_numeric_state_generic(state)

    # --- (1) 태스크 확보 ------------------------------------------------------
    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "web_search_agent"), None)
    if pending is None:
        raise ValueError(f"web_search_agent pending task 없음. 현재 마지막 태스크: {tasks[-1]}")

    web_search_system_prompt = get_web_search_prompt()

    messages = state.get("messages", [])
    references = state.get("references", {"queries": [], "docs": []})
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

    queries: list[str] = []         # 이번 라운드 실제 실행/추가된 질의 목록
    json_paths: list[str] = []      # 저장된 웹검색 JSON 경로
    new_docs_preview: list[Document] = []  # 미리보기용 문서 샘플

    MAX_INDEXED_PER_ROUND = int(os.getenv("MAX_INDEXED_PER_ROUND", "0"))  # 0=제한없음
    MAX_SEARCH_QUERIES_PER_ROUND = int(os.getenv("MAX_SEARCH_QUERIES_PER_ROUND", "6"))
    SKIP_WEB = os.getenv("SKIP_WEB_SEARCH", "0") == "1"
    if SKIP_WEB:
        print("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 → 외부 웹검색 건너뜀(로컬 RAG만).")

    ns = state.get("chroma_ns") or os.getenv("CHROMA_NAMESPACE") or "default"
    slug = state.get("topic_slug")
    persist_dir = _topic_dir(slug) if slug else None

    chunk_total = 0  # 이번 라운드 인덱싱된 청크 수

    # --- (2) 소스 게이트 설정(허용 도메인) -----------------------------------
    GATE_KEEP_SOURCES = os.getenv("GATE_KEEP_SOURCES", "0") == "1"
    _DEFAULT_ALLOWED = [
        "me.go.kr","molit.go.kr","motie.go.kr","korea.kr","mss.go.kr","moef.go.kr",
        "kofpi.or.kr","kepco.co.kr","kesis.kr","kama.or.kr","kotra.or.kr","kei.re.kr","iea.org",
        "oecd.org","kdi.re.kr","kiep.go.kr"
    ]
    _env_allowed = os.getenv("ALLOWED_DOMAINS", "")
    ALLOWED_DOMAINS = {d.strip().lower() for d in _env_allowed.split(",") if d.strip()} if _env_allowed.strip() else set(_DEFAULT_ALLOWED)

    def _allowed(src: str) -> bool:
        if not GATE_KEEP_SOURCES:
            return True
        s = (src or "").lower()
        return any(dom in s for dom in ALLOWED_DOMAINS)

    # --- (2b) JSON 로더/필터 ---------------------------------------------------
    def _load_items(json_path: str) -> list[dict]:
        txt = Path(json_path).read_text(encoding="utf-8")
        try:
            data = json.loads(txt)
        except json.JSONDecodeError:
            items = []
            for line in txt.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
            return items
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("results", "items", "data"):
                v = data.get(key)
                if isinstance(v, list):
                    return v
            return [data]
        return []

    def _filter_json_by_domain(json_path: str) -> str:
        if not GATE_KEEP_SOURCES:
            return json_path
        try:
            items = _load_items(json_path)
        except Exception:
            return json_path
        if not isinstance(items, list):
            return json_path
        filtered = []
        for it in items:
            if not isinstance(it, dict):
                continue
            url = (it.get("url") or it.get("source") or "")
            if _allowed(url):
                filtered.append(it)
        if not filtered:
            return json_path
        p = Path(json_path)
        out = p.with_name(p.stem + "_filtered" + p.suffix)
        out.write_text(json.dumps(filtered, ensure_ascii=False), encoding="utf-8")
        return str(out)

    # --- (2c) 품질 필터 --------------------------------------------------------
    def _is_bad_doc(d: Document) -> bool:
        txt = ((getattr(d, "page_content", None) or "")[:2000]).lower()
        return any(k in txt for k in ["access denied","enable javascript","just a moment","security controls triggered","captcha"])

    # --- (3) 실제 검색/적재 실행 유틸 -----------------------------------------
    def _run_web_search_with_guard(q: str, preview_limit: int = 5, retries: int = 2) -> bool:
        nonlocal chunk_total
        q = (q or "").strip()
        if not q:
            return False
        for attempt in range(retries + 1):
            try:
                # 3-1) 검색 호출
                _, json_path = web_search.invoke({"query": q})
                json_paths.append(json_path)

                # 3-1b) 결과 JSON 프로젝트 리소스 폴더로 이동
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

                # 3-2) 허용 도메인 필터
                filtered_json = _filter_json_by_domain(json_path)

                # 3-3) 인덱싱
                try:
                    _orig_count, chunk_count = add_web_pages_json_to_chroma(
                        filtered_json, namespace=ns, persist_directory=persist_dir
                    )
                    chunk_count = int(chunk_count or 0)
                    chunk_total += max(0, chunk_count)
                except Exception as e:
                    print(f"[WARN] add_web_pages_json_to_chroma 실패: {e}")

                # 3-4) 프리뷰(허용 도메인 + 품질 필터)
                try:
                    docs = web_page_json_to_documents(filtered_json)[:preview_limit]
                    if GATE_KEEP_SOURCES:
                        def _src(d: Document) -> str:
                            md = getattr(d, "metadata", {}) or {}
                            return md.get("source") or md.get("url") or ""
                        docs = [d for d in docs if _allowed(_src(d))]
                    docs = [d for d in docs if not _is_bad_doc(d)]
                    for d in docs:
                        src = ((getattr(d, "metadata", {}) or {}).get("source")
                               or (getattr(d, "metadata", {}) or {}).get("url")
                               or "unknown")
                        new_docs_preview.append(Document(page_content=(d.page_content or "")[:500], metadata={"source": src}))
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

    # --- (4) 쿼리 실행 파이프라인 ---------------------------------------------
    # 4-0) 플래너 쿼리: research_plan.queries 우선, 없으면 planner_queries
    def _normalize_planner_q(s: str) -> str:
        s = (s or "").strip()
        s = re.sub(r"^\s*[\-\•]\s*", "", s)      # bullet
        s = re.sub(r"^\s*\d+\.\s*", "", s)       # numbering
        return s.strip().strip('"').strip("'")

    plan_from_state = (state.get("research_plan") or {}).get("queries") or []
    raw_planner_qs = list(plan_from_state or []) or list(state.get("planner_queries") or [])
    planner_qs = []
    seen_norm = set()
    for q in raw_planner_qs:
        nq = re.sub(r"\s+", " ", _normalize_planner_q(q))
        if not nq: 
            continue
        lk = nq.lower()
        if lk in seen_norm or lk in _existing_qs:
            continue
        seen_norm.add(lk)
        planner_qs.append(nq)

    ran_planner = 0
    if planner_qs:
        if not SKIP_WEB:
            print("[WEB SEARCH AGENT] planner queries:", planner_qs)
            for q in planner_qs:
                if _run_web_search_with_guard(q):
                    _existing_qs.add(q.lower())
                    ran_planner += 1
        else:
            print("[WEB SEARCH AGENT] (skip) planner queries ignored:", planner_qs)
        # 사용 후 항상 비움
        state["planner_queries"] = []
        rp = state.get("research_plan") or {}
        rp["queries"] = []
        state["research_plan"] = rp
        print(f"[WEB SEARCH AGENT] planner queries executed: {ran_planner}/{len(planner_qs)}")

    # 4-1) 강제 쿼리
    forced_queries: list[str] = []
    try:
        forced_queries = extract_forced_queries_from_messages(messages, lookback=20) or []
    except Exception as e:
        print(f"[WARN] forced query extraction failed: {e}")

    if forced_queries:
        if not SKIP_WEB:
            print("[WEB SEARCH AGENT] forced queries:", forced_queries)
            for q in forced_queries:
                q = (q or "").strip()
                if not q:
                    continue
                lk = q.lower()
                if lk in _existing_qs:
                    print(f"[WEB SEARCH AGENT] skip duplicate (forced): {q}")
                    continue
                print("-------- web search --------", {"query": q})
                if _run_web_search_with_guard(q):
                    _existing_qs.add(lk)
        else:
            print("[WEB SEARCH AGENT] (skip) forced queries ignored:", forced_queries)

    # 4-2) LLM 설계 쿼리
    if not SKIP_WEB:
        llm_with_web = llm.bind_tools([web_search])
        search_plans = (web_search_system_prompt | llm_with_web).invoke(inputs)
        ran = 0
        for args in iter_tool_calls(search_plans, "web_search"):
            if ran >= MAX_SEARCH_QUERIES_PER_ROUND:
                break
            q = (args.get("query") or "").strip()
            if not q:
                continue
            lk = q.lower()
            if lk in _existing_qs:
                continue
            print("-------- web search --------", {"query": q})
            if _run_web_search_with_guard(q):
                _existing_qs.add(lk)
                ran += 1
    else:
        print("[WEB SEARCH AGENT] (skip) LLM-designed web queries suppressed.")

    # 4-3) 자동 폴백(자동 모드 & 지금까지 실행 쿼리 전무)
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
    if auto_mode and not queries:  # 아직 단 한 건도 실행되지 않았다면 폴백
        if not SKIP_WEB:
            for q in _fallback_auto_queries():
                q = (q or "").strip()
                if not q:
                    continue
                lk = q.lower()
                if lk in _existing_qs:
                    print(f"[WEB SEARCH AGENT] skip duplicate (fallback): {q}")
                    continue
                if _run_web_search_with_guard(q):
                    _existing_qs.add(lk)
        else:
            print("[WEB SEARCH AGENT] (skip) auto-fallback web queries suppressed.")

    # --- (5) 로컬 파일 인덱싱 (토픽당 1회) -----------------------------------
    env_globs = [g.strip() for g in (os.getenv("LOCAL_RAG_GLOBS", "") or "").split("|") if g.strip()]
    slug_or_wildcard = slug if slug else "**"

    def _normalize_and_expand(p: str) -> str:
        p = p.replace("<topic-slug>", slug_or_wildcard)
        p = p.replace("\\", os.sep).replace("/", os.sep)
        return p

    local_globs: list[str] = [_normalize_and_expand(p) for p in env_globs]

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and isinstance(last_human.content, str):
        m = re.search(r"(?:add_local|local_rag|내부자료|내부문서)\s*:\s*(.+)", last_human.content, flags=re.I)
        if m:
            arg = m.group(1)
            for token in re.split(r"[|;,]", arg):
                t = token.strip()
                if t:
                    local_globs.append(_normalize_and_expand(t))

    # 중복 제거
    seen = set(); dedup_globs = []
    for g in local_globs:
        key = g.lower() if os.name == "nt" else g
        if key in seen:
            continue
        seen.add(key); dedup_globs.append(g)

    # ✅ 토픽별 1회 인덱싱 가드 (TypedDict-safe)
    flags = state.setdefault("flags", {})                 # 안전 컨테이너
    li = flags.setdefault("local_ingested", {})           # 토픽별 기록 맵
    topic_key = (slug or "default")
    skip_local_ingest = bool(li.get(topic_key))
    if skip_local_ingest:
        print(f"[LOCAL SCAN] already ingested for topic '{topic_key}' → skip ingest")

    if state.get("local_ingested"):
        print("[LOCAL SCAN] already ingested this topic → skip")
    else:
        debug_matches_total = 0
        if not dedup_globs:
            print("[LOCAL SCAN] 구성된 글롭이 없습니다. LOCAL_RAG_GLOBS 또는 add_local 명령을 확인하세요.")
        else:
            for pattern in dedup_globs:
                pattern_abs = pattern if pattern.startswith(os.sep) or (":" in pattern) else os.path.join(current_path, pattern)
                found = list(glob.iglob(pattern_abs, recursive=True))
                print(f"[LOCAL SCAN] {pattern}  -> {len(found)} file(s)")
                if len(found) == 0:
                    print(f"[LOCAL SCAN]   ↳ 경로 확인: {pattern_abs}")
                debug_matches_total += len(found)
            if debug_matches_total == 0:
                print("[LOCAL SCAN] 모든 글롭이 0개 매칭입니다. 경로/패턴 점검 필요.")
        
        # [ANCHOR] per-topic local ingest guard
        flags = state.setdefault("flags", {})              # TypedDict에 flags 필드가 선언돼 있어야 함
        li = flags.setdefault("local_ingested", {})        # 토픽별 인덱싱 이력 저장
        topic_key = (slug or "default")
        skip_local_ingest = bool(li.get(topic_key))
        if skip_local_ingest:
            print(f"[LOCAL SCAN] already ingested for topic '{topic_key}' → skip ingest")

        if dedup_globs and not skip_local_ingest:
            l_jsons, l_docs, l_chunks = ingest_local_files(
                dedup_globs,
                namespace=ns,
                persist_directory=persist_dir,
                topic_slug=slug or "default",
                root_dir=current_path,
                add_web_pages_json_to_chroma=add_web_pages_json_to_chroma,
                web_page_json_to_documents=web_page_json_to_documents,
            )
            if l_docs:
                print("[WEB SEARCH AGENT] ingest local refs:", dedup_globs)
                json_paths.extend(l_jsons)
                new_docs_preview.extend(l_docs)
                chunk_total += int(l_chunks or 0)
                # 실행 질의 목록에 local:* 도장 (향후 중복 방지)
                for g in dedup_globs:
                    q = f"local:{g}"
                    lk = q.lower()
                    if lk not in _existing_qs:
                        queries.append(q)
                        _existing_qs.add(lk)
                # ✅ 토픽당 1회 ingest 마킹
                li[topic_key] = True
                state["local_ingested"] = True
            else:
                print("[LOCAL RAG] no docs matched; skip adding local:* queries")

    # (선택) 로컬 프리뷰 키워드 필터
    allow_kw_env = os.getenv("LOCAL_RAG_ALLOW", "")
    if allow_kw_env.strip():
        ALLOW_KEYS = {k.strip().lower() for k in allow_kw_env.split(",") if k.strip()}
        def _relevant(d: Document) -> bool:
            txt = (d.page_content or "").lower()
            return any(k in txt for k in ALLOW_KEYS)
        before = len(new_docs_preview)
        new_docs_preview[:] = [d for d in new_docs_preview if _relevant(d)]
        after = len(new_docs_preview)
        if before != after:
            print(f"[LOCAL RAG] preview filtered by keywords: {before} → {after}")

    # --- (6) 상태 갱신 & 다음 단계 -------------------------------------------
    state["references"] = merge_refs(state.get("references"), queries, new_docs_preview)

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
    messages.append(AIMessage(
        f"[WEB SEARCH AGENT] 검색 완료({len(queries)}건). JSON 저장 및 Chroma 적재/프리뷰 완료. 모드={mode_label}"
        + (f" (예: {json_paths[0]})" if json_paths else "")
    ))

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
    # state = sanitize_numeric_state(state)
    state = sanitize_numeric_state_generic(state)

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
    queries = [q.strip("-• ").strip() for q in queries_text.splitlines() if q.strip()]
    state["planner_queries"] = queries

    
    # ======== [SEARCH-ANCHOR: PLAN_PERSIST] persist planner queries for web_search_agent ========
    # - Web Search Agent가 라운드별 플랜 쿼리를 우선 사용하도록 상태에 구조화 저장
    # - 중복/공백 정리 (local:* 는 여기선 그대로 두되, web_search_agent에서 필터링)
    import re as _re
    def _norm_q(_q: str) -> str:
        return _re.sub(r"\s+", " ", (_q or "").strip())

    _seen = set()
    _normed = []
    for _q in (queries or []):
        _qn = _norm_q(_q)
        if not _qn:
            continue
        _lk = _qn.lower()
        if _lk in _seen:
            continue
        _seen.add(_lk)
        _normed.append(_qn)

    state["research_plan"] = {
        "round": rnd + 1,
        "objective": current_obj,
        "queries": _normed,        # ← Web Search Agent가 여기 우선 사용
        "timestamp": _now_str(),
    }
    print(f"[Planner] saved {len(_normed)} queries to state.research_plan (round={rnd + 1})")
    # ======== [END PLAN_PERSIST] ==============================================================

    plan_msg = (
        f"[Research Planner] Round {rnd + 1} objective: {current_obj}\n"
        "Queries:\n" + "\n".join(f"- {q}" for q in queries)
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


def research_synthesizer(state: State):
    print("\n\n============ RESEARCH SYNTHESIZER ============")
    # state = sanitize_numeric_state(dict(state))
    state = sanitize_numeric_state_generic(state)

    rnd = as_int(state, "research_round", 0)
    max_iter = max(1, as_int(state, "iteration_count", 1))

    refs = state.get("references") or {"queries": [], "docs": []}
    docs = list(refs.get("docs") or [])

    # def _pick_round_new_urls(state_dict: dict) -> Optional[int]:
    def _pick_round_new_urls(state_dict: Mapping[str, Any]) -> Optional[int]:
        for key in ("new_url_count_round", "round_new_urls", "new_urls", "new_url_count"):
            value = state_dict.get(key)
            if value is None:
                continue
            s = str(value).strip()
            if not s:
                continue
            try:
                return max(0, int(s))
            except Exception:
                continue
        return None

    # def _pick_round_new_urls(st: dict) -> Optional[int]:
    #     for k in ("new_url_count_round", "round_new_urls", "new_urls", "new_url_count"):
    #         if k in st and st[k] is not None and str(st[k]).strip() != "":
    #             try:
    #                 return max(0, int(str(st[k]).strip()))
    #             except Exception:
    #                 continue
    #     return None

    round_new_urls = _pick_round_new_urls(state)

    if round_new_urls is None:
        print(f"[SYNTH] round={rnd+1}/{max_iter}, round_new_urls=? (missing)")
    else:
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

    msgs = list(state.get("messages") or [])
    msgs.append(AIMessage(saved_msg))

    findings_md = list(state.get("findings_md") or [])
    if out_path:
        findings_md.append(out_path)

    next_round = min(rnd + 1, max_iter)

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
    state = sanitize_numeric_state_generic(state)

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

    slug = state.get("topic_slug")  # Optional[str]
    persist_dir = _topic_dir(slug) if slug else (os.getenv("CHROMA_DIR") or _default_chroma_dir(ns))

    # 💡 세션 디렉터리 확정 후 '1회만' 초기화 (환경변수로 on/off)
    if os.getenv("CLEAR_CHROMA_ON_START", "0") == "1" and not state.get("_vs_cleared_once"):
        # clear_vector_store(namespace=ns, persist_directory=persist_dir)
        ensure_vector_store_cleared_once(namespace=ns, persist_directory=persist_dir)
        state["_vs_cleared_once"] = True
        print(f"[INIT] vector store cleared once (ns='{ns}', dir='{persist_dir}')")

    TOP_K = int(os.getenv("RAG_TOP_K", "6"))

    l_chunks = 0
    try:
        ensure_local = os.getenv("SKIP_WEB_SEARCH", "0") == "1"
        local_globs_env = os.getenv("LOCAL_RAG_GLOBS", "")
        need_local = ensure_local and bool(local_globs_env.strip())
        not_yet = not state.get("local_ingested_once")
        if need_local and not_yet:
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
                    persist_directory=persist_dir,
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

    new_url_count = int(l_chunks or 0)
    state["new_url_count"] = new_url_count
    state["new_url_count_round"] = new_url_count
    state["round_new_urls"] = new_url_count

    # ✅ ran_queries를 set()으로 변경 (중복 체크 O(1))
    ran_queries: set[str] = set()
    accum_queries: list[str] = []
    accum_docs: list = []


    def _skip_reason(q: str, key: str) -> str:
        if not (q or "").strip():
            return "empty=True"
        r = []
        if _is_noise_query(q): r.append("noise=True")
        if not _ok_query(q):   r.append("ok=False")
        if key in ran_queries: r.append("dup=True")
        return " ".join(r) if r else ""

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

    def _is_noise_query(q: str) -> bool:
        ql = (q or "").strip().lower()
        if not ql:
            return True
        if ql in {"force_query", "force_queries", "force"}:
            return True
        if len(ql) <= 2:
            return True
        bad_markers = ["gtm.js", "function(", "<meta", "<script", "@media", "var ", "cookieconsent", "usercentrics"]
        if any(b in ql for b in bad_markers):
            return True
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # 1) 사용자 질의 우선 검색 (+ 정제/중복/노이즈 가드, 스킵 이유 로그)
    # ─────────────────────────────────────────────────────────────────────────
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    user_q = _extract_user_query(last_human.content) if (last_human and isinstance(last_human.content, str)) else ""
    user_q = _clean_seed(user_q)
    user_q_clean = _strip_web_filters(user_q)
    user_key = user_q_clean.strip().lower()

    if user_q_clean and (not _is_noise_query(user_q_clean)) and _ok_query(user_q_clean) and (user_key not in ran_queries):
        # >>> ANCHOR: FILTER_USER_QUERY_BEFORE_RETRIEVE >>>
        if _looks_like_local_glob(user_q_clean):
            print(f"[FILTER] skip local/glob query: {user_q_clean}")
            # 실행/기록 모두 건너뜀
        else:
        # <<< ANCHOR: FILTER_USER_QUERY_BEFORE_RETRIEVE <<<
            try:
                print("-----------------------------------", {
                    "name": "retrieve",
                    "args": {
                        "query_raw": user_q,
                        "query_retrieval": user_q_clean,
                        "top_k": TOP_K
                    }
                })
                retrieved_docs = retrieve.invoke({
                    "query": user_q_clean,
                    "namespace": ns,
                    "persist_directory": persist_dir,
                    "top_k": TOP_K
                })
            except Exception as e:
                print(f"[WARN] retrieve 실패(user_q='{user_q}' → '{user_q_clean}'): {e}")
                retrieved_docs = []

            accum_queries.append(user_q_clean)
            accum_docs.extend(retrieved_docs)
            ran_queries.add(user_key)  # ✅ set에 추가

        state["references"] = merge_refs(references, accum_queries, accum_docs)
        references = state["references"]

        print(f"[DEBUG] ns={ns} persist_dir={persist_dir} TOP_K={TOP_K} ALLOW_LOCAL_SUMMARY={os.getenv('ALLOW_LOCAL_SUMMARY')}")
        print(f"[DEBUG] retrieved_docs={len(retrieved_docs)} for user_q_clean={user_q_clean!r}")
        for i, d in enumerate((retrieved_docs or [])[:2], 1):
            meta = getattr(d, "metadata", {}) or {}
            snip = (getattr(d, "page_content", "") or "")[:100].replace("\n", " ")
            print(f"[DEBUG] ctx{i} source={meta.get('source')} snip={snip!r}")

        if os.getenv("ALLOW_LOCAL_SUMMARY", "0") == "1":
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
                    resp = llm.invoke(prompt)
                    reply_text = getattr(resp, "content", str(resp))
                    messages.append(AIMessage(reply_text))

                    state["qa_direct_reply"] = True
                    for k in ("new_url_count", "new_url_count_round", "round_new_urls"):
                        state[k] = int(state.get(k, 0) or 0)

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
                state["qa_direct_reply"] = True
                for k in ("new_url_count", "new_url_count_round", "round_new_urls"):
                    state[k] = int(state.get(k, 0) or 0)
                if not has_pending(tasks, "communicator"):
                    tasks.append(Task(agent="communicator", done=False, description="안내 전달 및 다음 요청 확인", done_at=""))
                pending.done = True
                pending.done_at = _now_str()
                return {"messages": messages, "task_history": tasks, "references": references}
    else:
        # ✅ 스킵 사유 디버깅 로그
        print(f"[SKIP user] q='{user_q_clean}' "
              f"empty={not bool(user_q_clean)} noise={_is_noise_query(user_q_clean)} "
              f"ok={_ok_query(user_q_clean)} dup={user_key in ran_queries}")

    # ─────────────────────────────────────────────────────────────────────────
    # 2) 설계 질의/기보유 쿼리 실행 루틴
    # ─────────────────────────────────────────────────────────────────────────
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

    # 3b) 기존 레퍼런스 질의 재조회 (정제/중복 가드 + 스킵 로그)
    for q in preexisting_queries:
        raw = q
        q = _clean_seed(raw)
        q_for_retrieve = _strip_web_filters(q)
        key = q_for_retrieve.strip().lower()

        # >>> ANCHOR: FILTER_PREEXISTING_QUERY_BEFORE_RETRIEVE >>>
        if _looks_like_local_glob(q_for_retrieve):
            print(f"[FILTER] skip local/glob query: {q_for_retrieve}")
            continue
        # <<< ANCHOR: FILTER_PREEXISTING_QUERY_BEFORE_RETRIEVE <<<

        if (not q_for_retrieve) or _is_noise_query(q_for_retrieve) or (not _ok_query(q_for_retrieve)) or (key in ran_queries):
            print(f"[SKIP preexisting] q='{q_for_retrieve}' "
                  f"empty={not bool(q_for_retrieve)} noise={_is_noise_query(q_for_retrieve)} "
                  f"ok={_ok_query(q_for_retrieve)} dup={key in ran_queries}")
            continue

        print("-----------------------------------", {
            "name": "retrieve",
            "args": {
                "query_raw": q,
                "query_retrieval": q_for_retrieve,
                "top_k": TOP_K
            }
        })

        try:
            retrieved_docs = retrieve.invoke({
                "query": q_for_retrieve,
                "namespace": ns,
                "persist_directory": persist_dir,
                "top_k": TOP_K
            })
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{q}' → '{q_for_retrieve}'): {e}")
            continue

        accum_queries.append(q_for_retrieve)
        accum_docs.extend(retrieved_docs)
        ran_queries.add(key)  # ✅ set에 추가

    # 4) LLM 설계 질의 실행 (정제/중복 가드 + 스킵 로그)
    for args in iter_tool_calls(search_plans, "retrieve"):
        raw = (args.get("query") or "")
        query = _clean_seed(raw)
        q_for_retrieve = _strip_web_filters(query)
        key = q_for_retrieve.strip().lower()

        # >>> ANCHOR: FILTER_PLAN_QUERY_BEFORE_RETRIEVE >>>
        if _looks_like_local_glob(q_for_retrieve):
            print(f"[FILTER] skip local/glob query: {q_for_retrieve}")
            continue
        # <<< ANCHOR: FILTER_PLAN_QUERY_BEFORE_RETRIEVE <<<

        if (not q_for_retrieve) or _is_noise_query(q_for_retrieve) or (not _ok_query(q_for_retrieve)) or (key in ran_queries):
            print(f"[SKIP plan] q='{q_for_retrieve}' "
                  f"empty={not bool(q_for_retrieve)} noise={_is_noise_query(q_for_retrieve)} "
                  f"ok={_ok_query(q_for_retrieve)} dup={key in ran_queries}")
            continue

        print("-----------------------------------", {
            "name": "retrieve",
            "args": {
                "query_raw": query,
                "query_retrieval": q_for_retrieve,
                "top_k": TOP_K
            }
        })

        try:
            retrieved_docs = retrieve.invoke({
                "query": q_for_retrieve,
                "namespace": ns,
                "persist_directory": persist_dir,
                "top_k": TOP_K
            })
        except Exception as e:
            print(f"[WARN] retrieve 실패(query='{query}' → '{q_for_retrieve}'): {e}")
            continue

        accum_queries.append(q_for_retrieve)
        accum_docs.extend(retrieved_docs)
        ran_queries.add(key)  # ✅ set에 추가

    state["references"] = merge_refs(references, accum_queries, accum_docs)
    references = state["references"]

    # (선택) 숫자 포함 스니펫을 facts_ctx로 구성하여 후속 Writer에 힌트 제공
    try:
        snips = []
        for d in (references.get("docs") or [])[:20]:
            txt = (getattr(d, "page_content", "") or "")
            # 숫자 + 단위/기호가 보이는 라인만 추출
            lines = [ln.strip() for ln in txt.splitlines()
                    if re.search(r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:%|조|억|만대|GWh|kWh|원|달러|bn|trn)\b", ln)]
            for ln in lines[:2]:
                snips.append(ln[:300])
            if len(snips) >= 5:
                break
        state["facts_ctx"] = "\n".join(snips[:5])
    except Exception:
        state["facts_ctx"] = ""

    print("\n\nQueries:--------------------------")
     # >>> ANCHOR: PRINT_EXECUTED_QUERIES_ONLY >>>
    for q in accum_queries:   # 기존: references["queries"]
        print(q)
    # <<< ANCHOR: PRINT_EXECUTED_QUERIES_ONLY <<<
    # for q in references["queries"]:
    #     print(q)

    print("\n\nReferences:--------------------------")
    for i, doc in enumerate(references["docs"][:20], start=1):
        print(f"[{i:02d}] " + _plain_snip(getattr(doc, "page_content", "") or "", 160))
        print("--------------------------")

    pending.done = True
    pending.done_at = _now_str()

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

# >>>>>>>>> [AUTO-FOOTNOTE HELPERS START] <<<<<<<<<
import os, re
from urllib.parse import urlparse, unquote

def _canonicalize_src_for_dedup(src: str) -> str:
    """source의 페이지/버전 접미사를 제거해 중복 판단 키를 만든다."""
    if not src:
        return ""
    s = str(src)
    # __v_ 접미사는 버전/mtime -> 디듀프에서는 제거
    if "__v_" in s:
        s = s.split("__v_")[0]
    return s

def _auto_footnote_label(meta: dict, url: str) -> str:
    """각주에 함께 보여줄 짧은 라벨(파일명/제목/도메인)을 만든다."""
    title = (meta.get("title") or "").strip()
    if title:
        return (title[:80] + "...") if len(title) > 80 else title

    label = ""
    if url:
        u = urlparse(url)
        label = unquote(os.path.basename(u.path) or u.netloc).replace("%20", " ")
    if not label:
        label = "source"
    return (label[:80] + "...") if len(label) > 80 else label

def attach_auto_citations(text: str, state: dict) -> str:
    """
    references.docs 메타데이터를 이용해 문서 하단에 각주 블록을 자동 삽입.
    - AUTO_FOOTNOTE=1 일 때 동작 (section_writer에서 이미 가드)
    - AUTO_FOOTNOTE_MAX: 최대 각주 수(기본 12)
    - AUTO_FOOTNOTE_INLINE=1: 간단 키워드 매칭 기반 줄 끝에 [^n] 자동 삽입(기본 OFF)
    """
    refs = (state.get("references") or {}).get("docs") or []
    if not refs:
        print("[AUTO_FOOTNOTE] No references found.")
        return text

    max_n = int(os.getenv("AUTO_FOOTNOTE_MAX", "12"))

    footnotes = []
    seen = set()
    index_by_key = {}   # 디듀프 키 -> 각주 번호

    for doc in refs:
        meta = getattr(doc, "metadata", {}) or {}
        url  = meta.get("url") or meta.get("source") or ""
        key  = _canonicalize_src_for_dedup(meta.get("source") or url)
        if (not key) or (key in seen):
            continue
        seen.add(key)

        idx = len(footnotes) + 1
        index_by_key[key] = idx
        label = _auto_footnote_label(meta, url)
        footnotes.append(f"[^{idx}]: {url}  ({label})")

        if len(footnotes) >= max_n:
            break

    if not footnotes:
        return text

    # (옵션) 간단 키워드 매칭으로 줄 끝에 [^n] 붙이기 — 기본 OFF
    if os.getenv("AUTO_FOOTNOTE_INLINE", "0") == "1":
        try:
            # 디도메인 맵 구성 (키: 디듀프키, 값: netloc)
            domain_map = {}
            for key in index_by_key:
                try:
                    netloc = urlparse(key).netloc
                except Exception:
                    netloc = ""
                domain_map[key] = netloc.lower()

            # 키워드 -> 기대 도메인
            keyword_map = {
                r"\bIEA\b": "iea.org",
                r"\bOECD\b": "oecd.org",
                r"\bKDI\b": "kdi.re.kr",
                r"KIET|산업연구원": "kiet.re.kr",
                r"KEEI|에너지경제연구원": "keei.re.kr",
                r"국회미래연구원|NAFI": "nafi.re.kr",
                r"KOTRA": "kotra.or.kr",
            }

            lines = text.splitlines()
            for i, line in enumerate(lines):
                for pat, dom in keyword_map.items():
                    if re.search(pat, line, flags=re.I):
                        # 해당 도메인을 가진 첫 각주 번호를 찾아 달아준다
                        for k, netloc in domain_map.items():
                            if dom in netloc:
                                idx = index_by_key[k]
                                if f"[^{idx}]" not in line:
                                    lines[i] = line.rstrip() + f"[^{idx}]"
                                break
                        break
            text = "\n".join(lines)
        except Exception as e:
            print(f"[AUTO_FOOTNOTE] inline marker skipped: {e}")

    # 문서 하단 각주 블록 추가
    text = text.rstrip() + "\n\n---\n\n### 참고 문헌 / 각주\n" + "\n".join(footnotes) + "\n"
    print(f"[AUTO_FOOTNOTE] Added {len(footnotes)} references.")
    return text
# <<<<<<<<< [AUTO-FOOTNOTE HELPERS END] >>>>>>>>>

# ── Chapter Writer ===========================================================
def chapter_writer(state: State):
    if DOC_MODE != "book":
        print(f"[CHAPTER WRITER] Skipped: DOC_MODE={DOC_MODE} (expected 'book').")
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}
    print("\n\n============ CHAPTER WRITER ============")
    state = sanitize_numeric_state_generic(state)
    # state = sanitize_numeric_state(state)

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "chapter_writer"), None)
    if pending is None:
        print("[WARN] pending 'chapter_writer' task가 없습니다. edge pass.")
        # section_writer와 동일: 경고만 띄우고 계속 진행

    messages = state.get("messages", [])
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and is_outline_creation(last_human.content):
        now = _now_str()
        if pending:
            pending.done = True
            pending.done_at = now
        tasks.append(Task(agent="content_strategist", done=False, description="create_outline:auto", done_at=""))
        messages.append(AIMessage("[Chapter Writer] Outline 요청 감지 → content_strategist로 위임"))
        return {"messages": messages, "task_history": tasks}

    outline_text = get_topic_outline_text(state)
    if not outline_text.strip():
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
        if pending:
            pending.done = True
            pending.done_at = now
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="집필 완료 보고 및 편집 여부 확인", done_at=""))
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target chapter: {target_title}")
    ref_text = _refs_preview_text(state) + _facts_block(state)
    
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

    if os.getenv("AUTO_FOOTNOTE", "1") == "1":
        try:
            gathered = attach_auto_citations(gathered, state)
        except Exception as e:
            print(f"[WARN] auto-citation 실패: {e}")

    out_path = save_md_draft(
        target_title, gathered, mode="book", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    state["last_saved_path"] = out_path
    messages.append(AIMessage(f"[Chapter Writer] '{target_title}' 초안 작성 완료 → {out_path}"))

    if pending:
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
    state = sanitize_numeric_state_generic(state)
    # state = sanitize_numeric_state(state)

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "section_writer"), None)
    if pending is None:
        print("[WARN] pending 'section_writer' task가 없습니다. edge pass.")

    messages = state.get("messages", [])
    outline_text = get_topic_outline_text(state)
    if not outline_text.strip():
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
    ref_text = _refs_preview_text(state) + _facts_block(state)

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

    if os.getenv("AUTO_FOOTNOTE", "1") == "1":
        try:
            gathered = attach_auto_citations(gathered, state)
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
    state = sanitize_numeric_state_generic(state)
    # state = sanitize_numeric_state(state)

    messages = state.get("messages", [])
    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
    desc = (pending.description if pending else "") or ""

    def _as_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    # 흔한 키들 우선
                    for k in ("text", "content", "value"):
                        v = item.get(k)
                        if isinstance(v, str):
                            parts.append(v)
                            break
                    else:
                        # 텍스트가 없으면 안전하게 문자열화
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

    # 플래너 발표 모드
    if "announce_planner" in desc.lower():
        last_planner = next(
            (m for m in reversed(messages)
             if isinstance(m, AIMessage) and str(m.content or "").startswith("[Research Planner]")),
            None
        )
        raw = last_planner.content if last_planner else "(리서치 플래너 메시지를 찾지 못했습니다.)"
        text = _as_text(raw)
        print("\nAI\t:\n" + text)
        messages.append(AIMessage(text))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        if not has_pending(tasks, "web_search_agent"):
            tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # show_outline 처리
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

        followup = (
            "목차를 확인했습니다. 다음 중 어떻게 진행할까요?\n"
            "1) 특정 섹션부터 바로 집필 → `write: 섹션명`\n"
            "2) 목차 수정 → 바꿀 제목/순서를 말씀해 주세요\n"
            "3) 최신 자료 보강 → `최신 자료로 RAG 업데이트`\n"
        )
        print("\nAI\t:\n" + followup)
        messages.append(AIMessage(followup))

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

    parts: list[str] = []
    for chunk in system_chain.stream({
        "messages": messages,
        "outline": fallback_outline,
        "doc_label": doc_label,
        "topic_title": state.get("topic_title") or "",
    }):
        part_text = _as_text(getattr(chunk, "content", ""))
        print(part_text, end="")
        parts.append(part_text)

    text_buf = "".join(parts)
    messages.append(AIMessage(text_buf))

    # 마지막 저장 경로 힌트 부가
    try:
        base_text = _as_text(messages[-1].content)
        if not any(x in base_text for x in ["chapters\\", "sections\\", "chapters/", "sections/"]):
            last_save_path = None
            moved_note = None
            _p1 = re.compile(r"\[(?:Section|Chapter|Content)\s+Writer|(Content Strategist)\].*?→\s*(.+?\.md)\s*", flags=re.DOTALL)
            _p2 = re.compile(r"\[(?:Section|Chapter|Content)\s+Writer\]\s*moved.*?->\s*(.+?\.md)\s*", flags=re.DOTALL)
            for m in reversed(messages):
                if not isinstance(m, AIMessage):
                    continue
                content_text=_as_text(m.content)
                m1 =  _p1.search(content_text)
                if m1:
                    last_save_path = (m1.group(2) or "").strip()  # ← 그룹(2)이 경로
                    break
                m2 = _p2.search(content_text)
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
    except Exception as e:
        print(f"[WARN] last-save-path hint failed: {e}")
    
    #except Exception:
    #    pass


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
    outline_text = get_topic_outline_text(state)
    outline_missing = not (outline_text or "").strip()
    outline_not_shown = state.get("outline_shown") is False

    if outline_missing:
        return "content_strategist"
    if outline_not_shown:
        return "communicator"

    tasks = state.get("task_history", [])

    # ✅ 1) 우선 writer 태스크가 미완료면 그걸 선택 (보고서/책 모드에 따라)
    preferred_writer = "section_writer" if DOC_MODE == "report" else "chapter_writer"
    for t in reversed(tasks):
        if (not t.done) and t.agent == preferred_writer:
            return preferred_writer

    # ✅ 2) writer(상대 모드)가 걸려 있다면 그것도 우선
    alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
    for t in reversed(tasks):
        if (not t.done) and t.agent == alt_writer:
            return alt_writer

    # ③ 마지막으로 communicator
    for t in reversed(tasks):
        if (not t.done) and t.agent == "communicator":
            return "communicator"

    # ④ 아무 것도 없으면 기본 writer
    return preferred_writer

def after_vector_router(state: State):
    # 직답 플래그가 있으면 바로 커뮤니케이터
    if state.get("qa_direct_reply"):
        return "communicator"

    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = int(state.get("research_round") or 0)
    max_iter = as_int(state, "iteration_count", 0)
    has_objs = bool(state.get("research_objectives"))

    if role == "research analyst" and has_objs and rounds_done < max_iter:
        return "research_synthesizer"
    return tail_task_router(state)


def after_planner_router(state: State):
    announce = os.getenv("RESEARCH_PLANNER_ANNOUNCE", "0") == "1" or as_int(state, "research_planner_announce", 0) == 1
    return "communicator" if announce else "web_search_agent"


def after_synthesizer_router(state: State):
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)

    if os.getenv("DEBUG_ROUTER_KEYS") == "1":
        keys_preview = list(state.keys())[:40]
        print(f"[ROUTER] keys[:40]={keys_preview}")

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

    def _pick(env_key, state_key, default):
        v = os.getenv(env_key)
        if v is not None and str(v).strip() != "":
            try:
                return int(v)
            except Exception:
                pass
        return as_int(state, state_key, default)

    halt_threshold = _pick("RESEARCH_HALT_THRESHOLD", "research_halt_threshold", 0)
    min_rounds = _pick("RESEARCH_MIN_ROUNDS", "research_min_rounds", 1)
    max_no_new = max(1, _pick("RESEARCH_MAX_NO_NEW_ROUNDS", "research_max_no_new_rounds", 1))
    streak = as_int(state, "no_new_url_streak", 0)

    print(f"[ROUTER] after_synthesizer: rounds_done={rounds_done}, max_iter={max_iter}, "
          f"new_url_count={new_url_count}, halt_threshold={halt_threshold}, "
          f"min_rounds={min_rounds}, no_new_url_streak={streak}/{max_no_new}")

    should_halt = (rounds_done >= max(1, min_rounds)) and (streak >= max_no_new)

    if rounds_done < max_iter and not should_halt:
        print("[ROUTER] → research_planner")
        return "research_planner"

    if should_halt:
        print(f"[ROUTER] halt: new_url_count<=threshold for {streak} round(s) → writer")
        return WRITER_AGENT

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
        "content_strategist": "content_strategist",
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
        "content_strategist": "content_strategist",
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
<meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'default' });</script>
<style> body{margin:0;padding:16px;} </style>
</head>
<body><div class="mermaid">$mmd</div></body>
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
        "new_url_count": None,
        "topic_slug": os.getenv("TOPIC_SLUG") or "default",
        "outline_fname": default_outline,
        "outline_shown": False,    
        "facts_ctx": "",  # ← 기본값
    }
    return sanitize_numeric_state_generic(base)


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

        state.setdefault("messages",[]).append(HumanMessage(user_input))
        result = graph.invoke(state, config={"recursion_limit": 200})
        # 런타임 방어 (선택)
        if not isinstance(result, dict):
            raise TypeError(f"graph.invoke returned unexpected type: {type(result).__name__}")
        # 타입 고정
        state = cast(State, result)
        # state = graph.invoke(state, config={"recursion_limit": 200})
        print("\n------------------------------------ MESSAGE COUNT\t", len(state.get("messages", [])))
        save_state(current_path, state)
