from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os
import re
from typing import Any, Mapping, MutableMapping, cast, Dict, List, Iterable, Optional, Protocol
from utils.tasks import HumanMessage, AIMessage, schedule_writer_if_needed
from core.models import Task, AgentName
from utils.sanitize import sanitize_state, coerce_int
from rag_expression import (
    is_outline_display,
    is_outline_creation,
    extract_write_title,
    extract_new_topic_title,
    coerce_message_content_to_str,
    extract_rename_chapter,
    extract_section_index,
)
import core.config as config
from core.paths import now_str as _now_str
from utils.outline import get_topic_outline_text, pick_outline_filename as _pick_outline_filename
from utils.forced_queries import extract_forced_queries_from_messages
from core.topic import start_new_topic, sanitize_title as _sanitize_title
from core.llm import get_llm
from prompts import get_supervisor_prompt
from core.state_types import State  # TypedDict

# ── Safe has_pending ─────────────────────────────────────────────────────────
# utils.tasks.has_pending이 keyword-only 인자(prefix)를 갖는 시그니처를 가짐.
class _HasPendingProto(Protocol):
    def __call__(self, tasks: Iterable[Any], agent: str, *, prefix: str | None = ...) -> bool: ...

_HAS_PENDING: Optional[_HasPendingProto]
try:
    from utils.tasks import has_pending as _HAS_PENDING
except Exception:
    _HAS_PENDING = None

def _safe_has_pending(tasks, agent: str, prefix: str | None = None) -> bool:
    if _HAS_PENDING is not None:
        try:
            return _HAS_PENDING(tasks, agent, prefix=prefix)
        except Exception:
            pass
    try:
        for t in (tasks or []):
            if getattr(t, "done", False):
                continue
            if getattr(t, "agent", "") != agent:
                continue
            if prefix and not str(getattr(t, "description", "") or "").startswith(prefix):
                continue
            return True
        return False
    except Exception:
        return False

# ── Config helpers (env → CFG → module default) ──────────────────────────────
def _cfg_str(name: str, default: str = "") -> str:
    try:
        v = getattr(config.CFG, name, None)
        if v is None:
            v = getattr(config, name, None)
    except Exception:
        v = None
    if v is None:
        v = os.getenv(name, default)
    return str(v) if v is not None else default

def _cfg_int(name: str, default: int = 0) -> int:
    s = _cfg_str(name, str(default))
    try:
        return int(str(s).strip())
    except Exception:
        return default

def _cfg_bool(name: str, default: bool = False) -> bool:
    s = _cfg_str(name, "1" if default else "0").strip().lower()
    return s in {"1", "true", "yes", "y", "on"}

def _doc_mode() -> str:
    return (_cfg_str("DOC_MODE", "report") or "report").lower()

def _writer_agent() -> str:
    return _cfg_str("WRITER_AGENT", "section_writer")

# AgentName 강제 보정: 임의 문자열을 안전한 리터럴로 변환
def _writer_agent_name() -> AgentName:
    w = (_writer_agent() or "").strip().lower()
    if w not in ("section_writer", "chapter_writer"):
        # 설정이 이상하면 DOC_MODE에 맞춰 기본값으로 보정
        w = "section_writer" if _doc_mode() == "report" else "chapter_writer"
    # mypy/pyright 만족을 위한 캐스트 (값은 위에서 보정)
    return cast(AgentName, w)

# ── Dashboard (optional) ─────────────────────────────────────────────────────
def _dash_on() -> bool:
    return _cfg_bool("SHOW_DASHBOARD", False)

def _wrap_val() -> int:
    return _cfg_int("DASH_WRAP", 120)

def _ell(s: str, n: int | None = None) -> str:
    n = n if isinstance(n, int) else _wrap_val()
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

def _dash_emit(state: Mapping[str, Any], *, where: str, picked: str | None = None, reason: str | None = None):
    if not _dash_on():
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

    try:
        import time as _t
        f = dict(state.get("flags") or {})
        f["dash_last_ts"] = float(_t.time())
        f["dash_count"] = int(f.get("dash_count") or 0) + 1
        # 가변 상태일 때만 쓰기
        if isinstance(state, MutableMapping):
            cast(MutableMapping[str, Any], state)["flags"] = f
    except Exception:
        pass
    logger.info("\n" + bar + "\n" + "\n".join(lines) + "\n" + bar)

def _is_research_mode(st: Mapping[str, Any]) -> bool:
    role_src = (st.get("agent_role") or _cfg_str("BLOCKAGI_AGENT_ROLE", "")).strip().lower()
    has_objs = bool(st.get("research_objectives"))
    max_iter = coerce_int(st.get("iteration_count", _cfg_int("ITERATION_COUNT", 0)), default=0)
    return (role_src == "research analyst") and has_objs and (max_iter > 0)

def _ensure_agent_env(state: MutableMapping[str, Any]) -> None:
    raw_role = state.get("agent_role")
    state["agent_role"] = raw_role.strip() if isinstance(raw_role, str) and raw_role.strip() else _cfg_str("BLOCKAGI_AGENT_ROLE", "")
    state["iteration_count"] = coerce_int(state.get("iteration_count", _cfg_int("ITERATION_COUNT", 0)), default=0)
    state["research_round"] = coerce_int(state.get("research_round", 0), default=0)

def _seed_objectives(state: MutableMapping[str, Any]) -> None:
    if state.get("research_objectives"):
        if isinstance(state["research_objectives"], list):
            state["research_objectives"] = [s.strip() for s in state["research_objectives"] if str(s).strip()]
        return
    # 1차: config 헬퍼로 BLOCKAGI_OBJECTIVE_1..N 읽기
    objs = config.load_research_objectives_from_env()
    # 2차: (선택) BLOCKAGI_OBJECTIVES JSON 배열도 허용
    if not objs:
        raw = getattr(config.CFG, "BLOCKAGI_OBJECTIVES", "") or ""
        if isinstance(raw, str) and raw.strip():
            try:
                import json
                cand = json.loads(raw)
                if isinstance(cand, list):
                    objs = [str(x).strip() for x in cand if str(x).strip()]
            except Exception:
                pass
    state["research_objectives"] = list(dict.fromkeys([o for o in objs if o]))

def _title_by_index(outline_text: str | None, idx: int) -> str | None:
    if not outline_text or idx <= 0:
        return None
    lines = [ln.strip() for ln in str(outline_text).splitlines() if ln.strip()]
    numbered: list[str] = []
    pat = re.compile(r"^\s*\d+\s*[\.\)]?\s*(?:장\s*)?(?P<title>.+?)\s*$")
    for ln in lines:
        m = pat.match(ln)
        if m:
            titled = re.sub(r"^[#\-\*\+]\s*", "", m.group("title").strip())
            numbered.append(titled)
    if 1 <= idx <= len(numbered):
        return numbered[idx - 1]
    return None

def supervisor(state: Mapping[str, Any]) -> Dict[str, Any]:
    logger.info("============ SUPERVISOR ============")
    _dash_emit(state, where="supervisor.enter")
    llm = get_llm()
    state = sanitize_state(state)  # Mapping -> dict (copy) or in-place if mutable
    mstate: MutableMapping[str, Any] = cast(MutableMapping[str, Any], state)

    _ensure_agent_env(mstate)
    _seed_objectives(mstate)

    # ↓↓↓ Round 0 고착 문제 해결 로직(메타 기반 승격) ↓↓↓
    rnd = int(state.get("research_round", 0))
    refs = state.get("references", {}) or {}
    has_refs = bool((refs.get("docs") or []) or (refs.get("queries") or []))
    plan = state.get("research_plan") or {}
    has_plan = bool((plan.get("queries") or []))
    rag_meta = state.get("rag_stats") or {}
    has_on_disk = bool(int(rag_meta.get("doc_count") or 0) > 0)

    logger.warning(
        "DEBUG: research_round=%d, has_refs=%s, has_plan=%s, rag_on_disk=%s, docs_in_state=%d",
        rnd, has_refs, has_plan, has_on_disk, len(refs.get("docs") or [])
    )

    if rnd == 0 and (has_refs or has_plan or has_on_disk) and int(state.get("iteration_count", 0)) > 0:
        mstate["research_round"] = 1
        logger.warning("[Supervisor] promote research_round=1 (basis: %s)",
                       "refs" if has_refs else ("plan" if has_plan else "rag_on_disk"))
    # ↑↑↑ Round 0 고착 문제 해결 로직(메타 기반 승격) ↑↑↑

    tasks: List[Task] = list(state.get("task_history", []) or [])
    messages: List[Any] = list(state.get("messages", []) or [])
    mstate["task_history"], mstate["messages"] = tasks, messages

    # [ANCHOR-1] writer 예약이 있으면 qa_direct_reply 차단
    _flags = state.get("flags") or {}
    if _flags.get("suppress_vector_qa"):
        mstate["qa_direct_reply"] = False

    if state.get("qa_direct_reply"):
        _flags = state.get("flags") or {}
        has_writer_pending = _safe_has_pending(tasks, "section_writer", prefix="write:") \
                          or _safe_has_pending(tasks, "chapter_writer", prefix="write:")
        has_locked_title = bool(_flags.get("pending_write_title"))
        if not has_writer_pending and not has_locked_title:
            logger.debug("qa_direct_reply flag detected -> short-circuit return")
            return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}
        else:
            logger.debug("qa_direct_reply ignored due to pending writer or locked title")

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    last_text: str = coerce_message_content_to_str(getattr(last_human, "content", "") if last_human else "").strip()

    # (1) 강제 쿼리
    try:
        fqs = extract_forced_queries_from_messages(messages, lookback=15)
    except Exception:
        logger.exception("extract_forced_queries_from_messages failed")
        fqs = []
    if not fqs and isinstance(last_text, str):
        m_force_inline = re.match(r"^\s*force_query\s*:\s*(.+?)\s*$", last_text, flags=re.IGNORECASE)
        if m_force_inline:
            q = (m_force_inline.group(1) or "").strip().strip('"').strip("'")
            if q:
                fqs = [q]
    if fqs:
        if not _safe_has_pending(tasks, "web_search_agent"):
            tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        msg = f"[Supervisor fast-path] → web_search_agent (force_queries {len(fqs)}개 감지)"
        messages.append(AIMessage(content=msg))
        logger.info(msg)
        _dash_emit(state, where="supervisor", picked="web_search_agent", reason="force_queries")
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

    def _is_qa_like(s: str) -> bool:
        if not isinstance(s, str): return False
        s = s.strip()
        if not s: return False
        write_verbs = ("작성", "집필", "써줘", "작성해", "만들어", "생성", "write:", "write ", "draft")
        if any(k in s.lower() for k in write_verbs):
            return False
        qa_signals = (
            "요약","정리","설명해줘","알려줘",
            "무엇","뭐야","어떻게","왜","누가","어디","언제","비교",
            "분석","평가","시사점","인사이트",
            "해석","의견","추천","제안","해설","논의","고찰","해답","답변"
        )
        if "?" in s:
            return True
        return any(k in s for k in qa_signals)

    if last_text and _is_qa_like(last_text):
        if not _safe_has_pending(tasks, "vector_search_agent"):
            tasks.append(Task(agent="vector_search_agent", done=False, description=f"qa_query:{last_text}", done_at=""))
            mstate["qa_direct_reply"] = True
            logger.info("[Supervisor fast-path] QA-like → vector_search_agent scheduled")
            _dash_emit(state, where="supervisor", picked="vector_search_agent", reason="qa_like_new_task")
        else:
            logger.info("[Supervisor fast-path] vector_search_agent pending already exists.")
        return {"messages": messages, "task_history": tasks, "qa_direct_reply": state.get("qa_direct_reply"), "flags": state.get("flags", {})}

    # 새 주제
    new_title = extract_new_topic_title(last_text)
    if new_title:
        maybe_title = _sanitize_title(new_title or "untitled report")
        # Mapping → dict 물리화 후 TypedDict(State)로 캐스팅
        state_for_start: State = cast(State, dict(state))
        state = start_new_topic(
            state_for_start,
            maybe_title,
            outline_fname=_pick_outline_filename(last_text),
        )
        mstate = cast(MutableMapping[str, Any], state)
        _ensure_agent_env(mstate)
        _seed_objectives(mstate)
        msg = f"[Supervisor] 새 주제 세션 시작: '{state.get('topic_title','')}' (ns={state.get('chroma_ns','')})"
        messages.append(AIMessage(content=msg)); logger.info(msg)
        _dash_emit(state, where="supervisor", picked="content_strategist/web_search_agent", reason="new_topic_boot")
        if not _safe_has_pending(tasks, "content_strategist"):
            fname = state.get("outline_fname", "outline.md")
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        refs = state.get("references") or {}
        if not (refs.get("docs") or []) and not _safe_has_pending(tasks, "web_search_agent"):
            tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
            messages.append(AIMessage(content="[Supervisor fast-path] → web_search_agent (RAG 업데이트 착수)"))
        return {"messages": messages, "task_history": tasks,
                "topic_title": state.get("topic_title"),
                "topic_slug": state.get("topic_slug"),
                "chroma_ns": state.get("chroma_ns"),
                "outline_fname": state.get("outline_fname"),
                "references": state.get("references"),
                "flags": state.get("flags", {})}

    # 연구 라운드 부트스트랩
    def _is_research_mode_local(st: Mapping[str, Any]) -> bool: return _is_research_mode(st)
    if _is_research_mode_local(state):
        research_agents = ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")
        has_research_pending = any(_safe_has_pending(tasks, a) for a in research_agents)
        if not has_research_pending:
            rnd = int(state.get("research_round", 0))
            max_iter = int(state.get("iteration_count", 0))

            if max_iter > 0 and rnd >= max_iter:
                logger.info("[Supervisor] All research rounds completed (%d/%d). Terminating research loop.", rnd, max_iter)
                messages.append(AIMessage(content=f"[Supervisor] 모든 연구 라운드({max_iter}회)가 완료되었습니다. 최종 보고서 작성을 지시해주세요."))
                _dash_emit(state, where="supervisor", picked="communicator", reason="research_loop_end")
                return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

            now = _now_str()
            for t in tasks:
                if (not t.done) and t.agent == "communicator":
                    t.done, t.done_at = True, now
                    t.description = (t.description or "") + " [auto-closed: start research loop]"
            for t in tasks:
                if (not t.done) and t.agent in ("chapter_writer", "section_writer"):
                    t.done, t.done_at = True, now
                    t.description = (t.description or "") + " [auto-closed: start research loop]"
            tasks.append(Task(agent="research_planner", done=False, description="plan: auto", done_at=""))
            msg = "[Supervisor fast-path] 연구 라운드 모드 시작 → research_planner"
            messages.append(AIMessage(content=msg)); logger.info(msg)
            _dash_emit(state, where="supervisor", picked="research_planner", reason="research_mode_bootstrap")
            return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

    # 목차 표시/생성 fast-path
    _outline_show_intent = (
        is_outline_display(last_text)
        or bool(re.search(r"(목차|outline).*(보여줘|보여|display|show)", last_text, re.I))
        or last_text.strip() in {"목차", "목차 보여줘", "show outline", "show me the outline"}
    )
    if _outline_show_intent:
        fname = _pick_outline_filename(last_text)
        if not _safe_has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))
        messages.append(AIMessage(content=f"[Supervisor fast-path] → communicator (show_outline:{fname})"))
        logger.info("[Supervisor fast-path] show_outline → communicator (target=%s)", fname)
        _dash_emit(state, where="supervisor", picked="communicator", reason="show_outline")
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

    if _is_research_mode_local(state):
        no_research_pending = not any(
            _safe_has_pending(tasks, a)
            for a in ("research_planner", "web_search_agent", "vector_search_agent", "research_synthesizer")
        )
        if no_research_pending:
            for t in tasks:
                if (not t.done) and t.agent == "communicator":
                    t.done, t.done_at = True, _now_str()
                    t.description = (t.description or "") + " [auto-closed: start research loop]"
            for t in tasks:
                if (not t.done) and t.agent in ("chapter_writer", "section_writer"):
                    t.done, t.done_at = True, _now_str()
                    t.description = (t.description or "") + " [auto-closed: start research loop]"
            tasks.append(Task(agent="research_planner", done=False, description="plan: auto", done_at=""))
            logger.info("[Supervisor fast-path] research_mode preemption → research_planner")
            _dash_emit(state, where="supervisor", picked="research_planner", reason="research_mode_preempt")
            return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

    # fast-path: outline create/display
    if is_outline_creation(last_text):
        fname = _pick_outline_filename(last_text)
        if not _safe_has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(content=f"[Supervisor fast-path] → content_strategist (target={fname})"))
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

    if is_outline_display(last_text):
        fname = _pick_outline_filename(last_text)
        if not _safe_has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))
        messages.append(AIMessage(content=f"[Supervisor fast-path] → communicator (show_outline:{fname})"))
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

    # fast-path: RAG update
    _rag_re = r"(최신|업데이트|update|latest).*?(자료|리소스|레퍼런스|참고|sources|material).*?(rag|벡터|vector|임베딩|embedding|index|색인|chroma)"
    if re.search(_rag_re, last_text, flags=re.IGNORECASE):
        now = _now_str()
        for t in tasks:
            if (not t.done) and t.agent in ("chapter_writer", "section_writer"):
                t.done, t.done_at = True, now
        messages.append(AIMessage(content="[Supervisor fast-path] 기존 writer 태스크 정리 후 RAG 업데이트 시작."))
        tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        messages.append(AIMessage(content="[Supervisor fast-path] → web_search_agent (RAG 업데이트 착수)"))
        _dash_emit(state, where="supervisor", picked="web_search_agent", reason="rag_update_fastpath")
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

    # fast-path: write:
    target_from_line = extract_write_title(last_text)
    if not target_from_line:
        idx = extract_section_index(last_text)
        if idx:
            target_from_line = _title_by_index(get_topic_outline_text(state), idx)

    if target_from_line:
        now = _now_str()
        for t in tasks:
            if (not t.done) and t.agent == "communicator":
                t.done, t.done_at = True, now
                t.description = (t.description or "") + " [auto-closed: writer request]"
                logger.info("[Supervisor fast-path] auto-closed pending communicator task.")

        refs = state.get("references", {}) or {}
        refs_empty = not (refs.get("docs") or [])
        has_pending_rag = any((not t.done) and t.agent in ("web_search_agent", "vector_search_agent") for t in tasks)

        if refs_empty or has_pending_rag:
            f = dict(state.get("flags") or {})
            f["pending_write_title"] = True
            f["requested_write_title"] = target_from_line
            f["suppress_vector_qa"] = True
            mstate["flags"] = f
            logger.debug("[Supervisor] writer lock set (empty/ongoing refs) → requested='%s'", target_from_line)
            desc = f"rag_update:write:{target_from_line}"
            if not _safe_has_pending(tasks, "web_search_agent"):
                tasks.append(Task(agent="web_search_agent", done=False, description=desc, done_at=""))
            try:
                schedule_writer_if_needed(
                    mstate,
                    tasks=tasks, messages=messages,
                    outline_text=get_topic_outline_text(state),
                    requested_title=target_from_line,
                    allow_during_research=True,  # pre-schedule
                    debug=True,
                )
            except Exception:
                logger.exception("[Supervisor fast-path] pre-schedule writer failed (non-fatal)")

            if not _safe_has_pending(tasks, _writer_agent_name(), prefix="write:"):
                tasks.append(Task(agent=_writer_agent_name(), done=False, description=f"write: {target_from_line}", done_at=""))
                logger.info("[Supervisor fast-path] writer pre-scheduled (fallback) → %s | title=%s",
                            _writer_agent_name(), target_from_line)

            mstate["qa_direct_reply"] = False
            messages.append(AIMessage(content="[Supervisor fast-path] 레퍼런스 비어있음/진행중 → RAG 먼저(web_search_agent). (writer pre-scheduled)"))
            _dash_emit(state, where="supervisor", picked="web_search_agent", reason="write_but_refs_empty")
            return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}
        
        # refs 있음
        ff = dict(state.get("flags") or {})
        if not ff.get("pending_write_title"):
            ff["pending_write_title"] = True
        ff["requested_write_title"] = target_from_line
        mstate["flags"] = ff
        logger.debug("[Supervisor] writer lock set (with refs) → requested='%s'", target_from_line)

        did = schedule_writer_if_needed(
            mstate,
            tasks=tasks, messages=messages,
            outline_text=get_topic_outline_text(state),
            requested_title=target_from_line,
            allow_during_research=_cfg_bool("AUTO_WRITE_DURING_RESEARCH", False),
            debug=True,
        )
        if did:
            _writer = _writer_agent()
            _mode = _doc_mode()
            messages.append(AIMessage(content=f"[Supervisor fast-path] → {_writer} (mode={_mode}, write: {target_from_line})"))
            _dash_emit(state, where="supervisor", picked=_writer, reason="write_with_refs")
        else:
            messages.append(AIMessage(content="[Supervisor] writer 예약이 생략되었습니다(조건 부적합 또는 중복)."))
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

    _rename = extract_rename_chapter(last_text)
    if _rename:
        idx, new_title = _rename
        fname = _pick_outline_filename(last_text)
        if not _safe_has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"rename_heading:{idx}:{new_title}:{fname}", done_at=""))
        messages.append(AIMessage(content=f"[Supervisor fast-path] → content_strategist (rename_heading:{idx}→{new_title})"))
        _dash_emit(state, where="supervisor", picked="content_strategist", reason="rename_heading")
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

    pending_undone = next((t for t in reversed(tasks) if not t.done), None)
    if pending_undone:
        logger.info("[Supervisor short-circuit] pending='%s' 유지 → 새 태스크 생성 생략", pending_undone.agent)
        _dash_emit(state, where="supervisor", picked=pending_undone.agent, reason="pending_short_circuit")
        return {"messages": messages, "task_history": tasks,
                "topic_title": state.get("topic_title"),
                "topic_slug": state.get("topic_slug"),
                "chroma_ns": state.get("chroma_ns"),
                "outline_fname": state.get("outline_fname"),
                "references": state.get("references"),
                "flags": state.get("flags", {})}

    # 일반 경로
    supervisor_system_prompt = get_supervisor_prompt()
    task = (supervisor_system_prompt | llm.with_structured_output(Task)).invoke({
        "messages": messages,
        "outline": get_topic_outline_text(state),
        "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
    })
    if not isinstance(task, Task):
        task = Task(**task)

    if task.agent in ("chapter_writer", "section_writer"):
        requested = extract_write_title(task.description or "") or None
        did = schedule_writer_if_needed(
            mstate,
            tasks=tasks, messages=messages,
            outline_text=get_topic_outline_text(state),
            requested_title=requested,
            allow_during_research=_cfg_bool("AUTO_WRITE_DURING_RESEARCH", False),
            debug=True,
        )
        if did:
            _mode = _doc_mode()
            messages.append(AIMessage(content=f"[Supervisor reconcile] writer 예약 완료 (mode={_mode}, requested={requested or '(auto)'})"))
            if requested:
                ff2 = dict(state.get("flags") or {})
                ff2["pending_write_title"] = True
                ff2["requested_write_title"] = requested
                mstate["flags"] = ff2
                logger.debug("[Supervisor] writer lock set (LLM reconcile) → requested='%s'", requested)
            mstate["qa_direct_reply"] = False

            return {"messages": messages, "task_history": tasks,
                    "topic_title": state.get("topic_title"),
                    "topic_slug": state.get("topic_slug"),
                    "chroma_ns": state.get("chroma_ns"),
                    "outline_fname": state.get("outline_fname"),
                    "references": state.get("references"),
                    "flags": state.get("flags", {})}
        else:
            messages.append(AIMessage(content="[Supervisor] writer 예약 불필요/중복으로 생략됨."))
            _dash_emit(state, where="supervisor", picked="communicator", reason="writer_skipped")
            return {"messages": messages, "task_history": tasks,
                    "topic_title": state.get("topic_title"),
                    "topic_slug": state.get("topic_slug"),
                    "chroma_ns": state.get("chroma_ns"),
                    "outline_fname": state.get("outline_fname"),
                    "references": state.get("references"),
                    "flags": state.get("flags", {})}

    tasks.append(task)
    messages.append(AIMessage(content=f"[Supervisor] {task}"))
    _dash_emit(state, where="supervisor", picked=task.agent, reason="supervisor_fallback_route")
    return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

def supervisor_router(state: Mapping[str, Any]) -> str:
    from utils.tasks import HumanMessage
    state = sanitize_state(state)
    tasks = state.get("task_history", []) or []
    refs = state.get("references") or {}
    refs_docs = list(refs.get("docs") or [])
    refs_empty = (len(refs_docs) == 0)

    def _has(agent: str, prefix: str | None = None) -> bool:
        try:
            return _safe_has_pending(tasks, agent, prefix=prefix)
        except Exception:
            return any((not getattr(t, "done", False)) and getattr(t, "agent", "") == agent for t in tasks)

    flags = state.get("flags") or {}
    has_writer_p = _has("section_writer", prefix="write:") or _has("chapter_writer", prefix="write:")
    if has_writer_p and flags.get("pending_write_title"):
        if refs_empty:
            _dash_emit(state, where="router", picked="web_search_agent", reason="writer_locked_but_refs_empty")
            return "web_search_agent"
        ret = "section_writer" if _doc_mode() == "report" else "chapter_writer"
        _dash_emit(state, where="router", picked=ret, reason="writer_pending_locked_title_refs_ok")
        return ret

    preferred = "section_writer" if _doc_mode() == "report" else "chapter_writer"
    alt = "chapter_writer" if preferred == "section_writer" else "section_writer"

    def _is_research_mode_local(st: Mapping[str, Any]) -> bool: return _is_research_mode(st)
    last_human = next((m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), None)
    last_text = coerce_message_content_to_str(getattr(last_human, "content", ""))

    new_topic = extract_new_topic_title(last_text)
    if new_topic:
        ret = "web_search_agent" if refs_empty else "communicator"
        _dash_emit(state, where="router", picked=ret, reason=f"new_topic refs_empty={refs_empty}")
        return ret

    if is_outline_display(last_text):
        ret = "communicator"; _dash_emit(state, where="router", picked=ret, reason="show_outline"); return ret

    if is_outline_creation(last_text):
        ret = "content_strategist"; _dash_emit(state, where="router", picked=ret, reason="create_outline"); return ret

    write_title = extract_write_title(last_text)
    if not write_title:
        idx_fallback = extract_section_index(last_text)
        if idx_fallback:
            write_title = _title_by_index(get_topic_outline_text(state), idx_fallback)
    if write_title:
        if refs_empty:
            ret = "web_search_agent"; _dash_emit(state, where="router", picked=ret, reason="write_refs_empty"); return ret
        ret = preferred; _dash_emit(state, where="router", picked=ret, reason="write_refs_present"); return ret

    if _is_research_mode_local(state):
        if _has(preferred, prefix="write:") or _has(alt, prefix="write:"):
            pass
        elif not any(_has(a) for a in ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")):
            return "research_planner"

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
    elif _has(preferred, prefix="write:"):  # 콜론 포함 일관화
        ret = preferred
    elif _has("communicator"):
        ret = "communicator"
    else:
        is_qa_intent = any(k in last_text for k in ("요약","정리","무엇","왜","비교","?"))
        ret = "vector_search_agent" if is_qa_intent else "communicator"

    _dash_emit(state, where="router", picked=ret, reason="default_route")
    return ret
