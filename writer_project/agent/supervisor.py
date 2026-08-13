from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os
import re
from typing import Any, Mapping, MutableMapping, cast, Dict, List, Iterable, Optional, Protocol, Callable
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
from core.events import emit_event
# Direct QA 가드/판별 유틸(연구 모드 차단 로직 포함)
from utils.rag_utils import should_direct_qa as _should_direct_qa
from utils.rag_utils import is_qa_like as _is_qa_like_ext

from tools.web_rag.ingest import _default_chroma_dir  # Chroma persist dir resolver

# ── 웹 NS 시드(선택 훅) ───────────────────────────────────────────────────────
# 명시 타입 선언(동적 임포트 실패 시 None 유지)
_seed_web_ns: Optional[Callable[..., Any]] = None
_has_any_docs: Optional[Callable[..., bool]] = None
try:
    from tools.web_rag.ingest import seed_web_namespace as _seed_web_ns  # 동적 훅
except Exception:
    pass
try:
    from tools.web_rag.ingest import has_any_docs as _has_any_docs  # 동적 훅
except Exception:
    pass

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

# ── §12-13-1: 토픽-적합성 가드 헬퍼 ───────────────────────────────────────────
# fast-path(QA-like) 진입 전, 사용자 질의가 현재 토픽과 무관한지 1차 판정.
# 0개 매칭 → off-topic으로 간주, communicator 직행해 vector/web search 누수 차단.
def _topic_keyword_set() -> set[str]:
    """CFG.TOPIC_KEYWORDS + CFG.TOPIC_TITLE 토큰을 소문자 정규화한 셋 반환.
    둘 다 비어 있으면 빈 셋(가드 비활성)."""
    try:
        kws = list(getattr(config.CFG, "TOPIC_KEYWORDS", None) or [])
    except Exception:
        kws = []
    try:
        title = (getattr(config.CFG, "TOPIC_TITLE", "") or "").strip()
    except Exception:
        title = ""
    # TOPIC_TITLE을 비-영문/영문/숫자 경계로 토큰화하여 fallback 키워드로 추가
    # 예: "venfobel-vitamin" → ["venfobel", "vitamin"]
    if title:
        for tok in re.split(r"[^A-Za-z0-9가-힣]+", title):
            tok = tok.strip()
            if tok and len(tok) >= 2:  # 1글자 토큰은 노이즈 위험
                kws.append(tok)
    out: set[str] = set()
    for k in kws:
        s = (k or "").strip().lower()
        if s and len(s) >= 2:
            out.add(s)
    return out

def _topic_match_count(text: str) -> int:
    """text에 토픽 키워드 중 몇 개가 등장하는지 카운트(중복 키워드 1회 카운트).
    키워드 셋이 비었으면 항상 1을 반환(=가드 비활성, 모든 입력 통과)."""
    kws = _topic_keyword_set()
    if not kws:
        return 1  # 키워드 미설정 시 기존 동작 유지
    if not isinstance(text, str) or not text.strip():
        return 0
    s = text.lower()
    return sum(1 for k in kws if k in s)

# ── Chroma NS helpers (web/vector/synth와 동일 규칙) ─────────────────────────
def _ns_sanitize(s: str) -> str:
    s = (s or "").strip().lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9\-]+", "-", s)).strip("-") or "default"

def _ensure_chroma_ns(state: MutableMapping[str, Any]) -> None:
    """flags.chroma에 {'ns','dir',('ns_web'),('ns_local')} 저장하고, legacy key 'chroma_ns'도 유지."""
    flags: Dict[str, Any] = dict(state.get("flags") or {})
    chroma: Dict[str, Any] = dict(flags.get("chroma") or {})

    topic_slug_raw = (state.get("topic_slug") or _cfg_str("TOPIC_SLUG", "") or "default")
    env_ns_raw     = _cfg_str("CHROMA_NAMESPACE", "")
    ns_web_raw     = _cfg_str("CHROMA_NAMESPACE_WEB", "")
    ns_loc_raw     = _cfg_str("CHROMA_NAMESPACE_LOCAL", "")

    topic_slug = _ns_sanitize(topic_slug_raw)
    ns = _ns_sanitize(env_ns_raw) if env_ns_raw.strip() else topic_slug
    persist_dir = _default_chroma_dir(ns)

    chroma.update({"ns": ns, "dir": persist_dir})
    if ns_web_raw.strip():
        chroma["ns_web"] = _ns_sanitize(ns_web_raw)
    if ns_loc_raw.strip():
        chroma["ns_local"] = _ns_sanitize(ns_loc_raw)

    flags["chroma"] = chroma
    state["flags"] = flags
    # legacy/편의: 최상위에도 유지
    state["chroma_ns"] = ns
    logger.info("[Supervisor][ns] ns=%s dir=%s ns_web=%s ns_local=%s",
                ns, persist_dir, chroma.get("ns_web", "-"), chroma.get("ns_local", "-"))

def _get_seed_urls(state: Mapping[str, Any]) -> list[str]:
    """
    시드 URL 소스:
      1) CFG.SEED_URLS (list[str] 또는 콤마구분 str)
      2) ENV SEED_URLS  (콤마구분 str)
    """
    urls: list[str] = []
    try:
        raw = getattr(config.CFG, "SEED_URLS", None)
        if isinstance(raw, (list, tuple)):
            urls.extend([str(u).strip() for u in raw if str(u).strip()])
        elif isinstance(raw, str) and raw.strip():
            urls.extend([u.strip() for u in raw.split(",") if u.strip()])
    except Exception:
        pass
    env_raw = os.getenv("SEED_URLS", "")
    if env_raw.strip():
        urls.extend([u.strip() for u in env_raw.split(",") if u.strip()])
    # 중복 제거(순서 유지)
    dedup: list[str] = []
    seen = set()
    for u in urls:
        if u in seen: continue
        seen.add(u); dedup.append(u)
    return dedup

def _maybe_seed_web_namespace(state: MutableMapping[str, Any]) -> None:
    """
    web ns가 설정되어 있고, 컬렉션이 비어 있으면 1회 시드.
    flags.web_seeded_once = True로 재실행 방지.
    """
    try:
        flags = cast(Dict[str, Any], state.setdefault("flags", {}))
        if flags.get("web_seeded_once"):
            return
        chroma = cast(Dict[str, Any], flags.get("chroma") or {})
        ns_web = str(chroma.get("ns_web") or "").strip()
        if not ns_web or _seed_web_ns is None:
            return
        persist_dir = _default_chroma_dir(ns_web)
        # 이미 문서가 있으면 시드 생략
        try:
            if callable(_has_any_docs) and _has_any_docs(ns_web, persist_dir):
                return
        except Exception:
            pass
        seed_urls = _get_seed_urls(state)
        if not seed_urls:
            return
        topic_slug = str(state.get("topic_slug") or "")
        # 실행
        _seed_web_ns(seed_urls, ns_web, persist_directory=persist_dir, topic_slug=topic_slug)
        flags["web_seeded_once"] = True
        state["flags"] = flags
        logger.info("[Supervisor] web namespace seeded: ns=%s, urls=%d", ns_web, len(seed_urls))
    except Exception as e:
        logger.warning("[Supervisor] web namespace seeding skipped/failed: %s", e)


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
    emit_event("작업 분석")
    _dash_emit(state, where="supervisor.enter")

    # ✅ ultra-early pre-flight: command_intent가 아직 안 박혀도 '목차' 입력이면 즉시 처리(LLM init 방지)
    try:
        msgs = list(state.get("messages") or [])
        last_human = next(
            (
                m for m in reversed(msgs)
                if (
                    isinstance(m, HumanMessage)
                    or (getattr(m, "type", "") in ("human", "HumanMessage"))
                    or (m.__class__.__name__ == "HumanMessage")
                )
            ),
            None,
        )
        last_txt = str(getattr(last_human, "content", "") or "").strip()
    except Exception:
        last_txt = ""
    # 🔍 디버그 로그 추가 (여기!)
    logger.info(
        "[Supervisor][preflight-debug] last_txt=%r | msgs=%d | last_cls=%s",
        last_txt,
        len(msgs),
        (last_human.__class__.__name__ if last_human else None),
    )

    # ✅ pre-flight: show_outline은 LLM/Embedding 초기화 없이 즉시 처리

    llm = get_llm()
    state = sanitize_state(state)  # Mapping -> dict (copy) or in-place if mutable
    mstate: MutableMapping[str, Any] = cast(MutableMapping[str, Any], state)

    _ensure_agent_env(mstate)
    _seed_objectives(mstate)

    # ── Chroma NS/dir 초기화(최상단 1회 보장)
    try:
        _ensure_chroma_ns(mstate)
    except Exception:
        logger.exception("[Supervisor] _ensure_chroma_ns failed (continuing without ns init)")

    # ▶︎ 웹 NS 시드(once): web=0 편향 해소
    try:
        _maybe_seed_web_namespace(mstate)
    except Exception:
        logger.debug("[Supervisor] _maybe_seed_web_namespace skipped")

    # ↓↓↓ Round 0 고착 문제 해결 로직(메타 기반 승격) ↓↓↓
    rnd = int(state.get("research_round", 0))
    refs = state.get("references", {}) or {}
    has_refs = bool((refs.get("docs") or []) or (refs.get("queries") or []))
    plan = state.get("research_plan") or {}
    has_plan = bool((plan.get("queries") or []))
    rag_meta = state.get("rag_stats") or {}
    ns_base_count = int(rag_meta.get("ns_base_count") or 0)
    ns_web_count = int(rag_meta.get("ns_web_count") or 0)
    ns_local_count = int(rag_meta.get("ns_local_count") or 0)
    doc_total = int(rag_meta.get("doc_count") or 0)
    # rag_stats가 없으면 Chroma DB 직접 조회
    if not (ns_base_count or ns_web_count or ns_local_count or doc_total):
        try:
            from tools.web_rag.ingest_vector import get_collection_count
            slug = state.get("topic_slug") or "default"
            from core.paths import current_path
            base = str(current_path() if callable(current_path) else current_path)
            import os as _os
            chroma_base = _os.path.join(base, "data", "chroma_store")
            ns_web_count = get_collection_count(f"{slug}-web", _os.path.join(chroma_base, f"{slug}-web"))
            ns_local_count = get_collection_count(f"{slug}-local", _os.path.join(chroma_base, f"{slug}-local"))
        except Exception as _e:
            logger.debug("[Supervisor] chroma direct count failed: %s", _e)
    has_on_disk = (
        ns_base_count > 0
        or ns_web_count > 0
        or ns_local_count > 0
        or doc_total > 0
    )
    if has_on_disk:
        mstate["rag_on_disk"] = True

    logger.warning(
        "DEBUG: research_round=%d, has_refs=%s, has_plan=%s, rag_on_disk=%s, "
        "docs_in_state=%d, ns_base=%d, ns_web=%d, ns_local=%d, doc_total=%d",
        rnd,
        has_refs,
        has_plan,
        has_on_disk,
        len(refs.get("docs") or []),
        ns_base_count,
        ns_web_count,
        ns_local_count,
        doc_total,
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
            logger.debug("qa_direct_reply flag detected")
            # 마지막 사용자 입력 확보(예외 안전)
            try:
                last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
                _last_text: str = coerce_message_content_to_str(getattr(last_human, "content", "") if last_human else "").strip()
            except Exception:
                _last_text = ""

            # ── §12-13-1: 토픽-적합성 가드 ────────────────────────────
            # qa_direct_reply 플래그가 켜진 상태라도, 사용자 질의가 현재 토픽
            # 키워드와 0개 매칭이면 vector/web search로 누수되지 않도록 차단.
            # (TOPIC_KEYWORDS 미설정 시 _topic_match_count는 항상 1 반환 → 통과)
            if _last_text and _topic_match_count(_last_text) == 0:
                logger.info(
                    "[Supervisor] Direct QA off-topic (no keyword match) → communicator (q=%r)",
                    _last_text[:80],
                )
                # qa_direct_reply 플래그 해제 (재진입 방지)
                mstate["qa_direct_reply"] = False
                _flags_off = dict(mstate.get("flags") or {})
                _flags_off["qa_direct_reply"] = False
                # §12-13-1 (2차): research_round/research_loop_active 강제 리셋.
                # 이 함수 상단(L449)에서 'promote research_round=1 (basis: rag_on_disk)'로
                # 자동 승격된 값이 후속 라우터들의 research mode 분기를 트리거하므로
                # off-topic 가드 발화 시 명시적으로 0으로 되돌려 research loop 진입 차단.
                _flags_off["research_loop_active"] = False
                mstate["flags"] = _flags_off
                mstate["research_round"] = 0
                mstate["research_loop_active"] = False
                if not _safe_has_pending(tasks, "communicator"):
                    tasks.append(
                        Task(agent="communicator", done=False, description="off_topic:direct_qa", done_at="")
                    )
                _dash_emit(state, where="supervisor", picked="communicator", reason="off_topic_qa_guard")
                return {
                    "messages": messages,
                    "task_history": tasks,
                    "flags": mstate.get("flags", {}),
                    "qa_direct_reply": False,
                    "research_round": 0,
                    "research_loop_active": False,
                }

            # [변경점] 연구 모드에서도 Direct QA 우선권 부여
            # 연구 모드 && (qa_direct_reply 진행 중 OR 질의가 QA-like)이면 합성기 대신 벡터검색으로 보낸다.
            if _is_research_mode(mstate) and (_flags.get("qa_direct_reply") or _is_qa_like_ext(_last_text)):
                logger.info("[Supervisor] research_mode active but Direct QA prioritized → vector_search_agent")
            else:
                # 기존 가드: 필요 시 Direct QA 차단(연구 모드 일반 규칙)
                if not _should_direct_qa(state):
                    logger.info("[Supervisor] research_mode active -> Direct QA blocked → route research_synthesizer")
                    if not _safe_has_pending(tasks, "research_synthesizer"):
                        tasks.append(
                            Task(agent="research_synthesizer", done=False, description="synthesize: qa_blocked", done_at="")
                        )
                    _dash_emit(state, where="supervisor", picked="research_synthesizer", reason="direct_qa_blocked_by_research_mode")
                    return {
                        "messages": messages,
                        "task_history": tasks,
                        "flags": state.get("flags", {}),
                    }

            # Direct QA 허용/우선: 반드시 vector_search_agent를 펜딩으로 등록
            desc = f"qa_query:{_last_text[:64]}" if _last_text else "qa_query:(empty)"
            if not _safe_has_pending(tasks, "vector_search_agent"):
                tasks.append(
                    Task(agent="vector_search_agent", done=False, description=desc, done_at="")
                )
            # vector_search 입력 채널 보강
            if _last_text:
                mstate["last_user"] = _last_text
                cast(MutableMapping[str, Any], mstate.setdefault("flags", {}))["last_user_query"] = _last_text

            logger.info("[Supervisor] Direct QA fast-path → vector_search_agent (pending added)")
            _dash_emit(state, where="supervisor", picked="vector_search_agent", reason="direct_qa_fastpath_pending_added")
            return {
                "messages": messages,
                "task_history": tasks,
                "flags": state.get("flags", {}),
            }
        else:
            logger.debug("qa_direct_reply ignored due to pending writer or locked title")

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    last_text: str = coerce_message_content_to_str(getattr(last_human, "content", "") if last_human else "").strip()

    # ✅ FAST-PATH(우선): 목차/outline 요청은 QA-like보다 먼저 처리하여 vector_search(LLM)를 타지 않게 한다.


    # ✅ FAST-PATH(우선): 목차 생성도 QA-like보다 먼저 처리
    if is_outline_creation(last_text):
        fname = _pick_outline_filename(last_text)
        if not _safe_has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        mstate["qa_direct_reply"] = False
        messages.append(AIMessage(content=f"[Supervisor fast-path] → content_strategist (target={fname})"))
        _dash_emit(state, where="supervisor", picked="content_strategist", reason="create_outline_preempt_qa_like")
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

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

    if last_text and _is_qa_like(last_text):
        # ── §12-13-1: 토픽-적합성 가드 ────────────────────────────
        # QA-like 입력이지만 토픽 키워드 0개 매칭 → off-topic으로 간주.
        # vector_search_agent 펜딩 등록 대신 communicator로 직행하여
        # venfobel 인덱스 retrieval/no-hits→web_search 누수 차단.
        if _topic_match_count(last_text) == 0:
            logger.info(
                "[Supervisor fast-path] QA-like off-topic (no keyword match) → communicator (q=%r)",
                last_text[:80],
            )
            # §12-13-1 (2차): research_round/research_loop_active 강제 리셋.
            # 함수 상단의 자동 승격(L449)을 무력화하여 후속 라우터의
            # research mode 분기 진입을 차단.
            _flags_off2 = dict(mstate.get("flags") or {})
            _flags_off2["qa_direct_reply"] = False
            _flags_off2["research_loop_active"] = False
            mstate["flags"] = _flags_off2
            mstate["qa_direct_reply"] = False
            mstate["research_round"] = 0
            mstate["research_loop_active"] = False
            if not _safe_has_pending(tasks, "communicator"):
                tasks.append(
                    Task(agent="communicator", done=False, description="off_topic:qa_like", done_at="")
                )
            _dash_emit(state, where="supervisor", picked="communicator", reason="off_topic_qa_guard")
            return {
                "messages": messages,
                "task_history": tasks,
                "flags": mstate.get("flags", {}),
                "qa_direct_reply": False,
                "research_round": 0,
                "research_loop_active": False,
            }

        if not _safe_has_pending(tasks, "vector_search_agent"):
            tasks.append(Task(agent="vector_search_agent", done=False, description=f"qa_query:{last_text}", done_at=""))
            # vector_search 입력 채널 보강(q='' 방지)
            mstate["last_user"] = last_text
            flags_now = dict(mstate.get("flags") or {})
            flags_now["last_user_query"] = last_text
            mstate["flags"] = flags_now
            # vector_search가 실제로 읽는 입력 채널 보강(빈 q 방지)
            mstate["last_user"] = last_text
            cast(MutableMapping[str, Any], mstate.setdefault("flags", {}))["last_user_query"] = last_text
            logger.info("[Supervisor fast-path] QA-like → vector_search_agent scheduled")
            _dash_emit(state, where="supervisor", picked="vector_search_agent", reason="qa_like_new_task")
        else:
            logger.info("[Supervisor fast-path] vector_search_agent pending already exists.")
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {})}

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
        # 새 주제 부트스트랩 시에도 NS/dir 일관 세팅
        try:
            _ensure_chroma_ns(mstate)
        except Exception:
            logger.exception("[Supervisor] _ensure_chroma_ns (new topic) failed")
        # 새 주제 부트스트랩 시에도 웹 NS 시드 시도
        try:
            _maybe_seed_web_namespace(mstate)
        except Exception:
            logger.debug("[Supervisor] _maybe_seed_web_namespace (new topic) skipped")
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

    # write 명령(explicit "write:" 또는 ko-natural "X 섹션 작성해주세요") + RAG 있으면
    # 리서치 건너뛰고 바로 section_writer로
    # §12-13-5: extract_write_title()이 둘 다 hit하므로 explicit prefix 검사 대신 통일 사용.
    #           description은 "write: <title>"로 정규화하여 section_writer 측 파싱 일관성 확보.
    _write_title_early = extract_write_title(last_text)
    if _write_title_early and has_on_disk:
        _hit_kind = "explicit" if last_text.lower().startswith("write:") else "ko-natural"
        _norm_desc = f"write: {_write_title_early}"
        if not _safe_has_pending(tasks, "section_writer"):
            tasks.append(Task(agent="section_writer", done=False, description=_norm_desc, done_at=""))
        if not _safe_has_pending(tasks, "vector_search_agent"):
            tasks.append(Task(agent="vector_search_agent", done=False, description=f"qa_query:{last_text}", done_at=""))
        # ── §12-13-5 보강: vector_search direct_qa skip 가드 발화용 flag 세팅 ──
        f = dict(state.get("flags") or {})
        f["pending_write_title"] = True              # 필수 — L1235 가드 발화
        f["requested_write_title"] = _write_title_early  # 필수 — schedule_writer가 title 없으면 noop
        f["suppress_vector_qa"] = True               # 권장 — supervisor 재진입 시 qa_direct_reply 차단
        mstate["flags"] = f
        try:
            schedule_writer_if_needed(mstate, reason="early_write_fastpath_with_refs")
        except Exception:
            logger.exception("[Supervisor early write] schedule_writer_if_needed failed (non-fatal)")
        logger.info(
            "[Supervisor fast-path] write + rag_on_disk → vector_search → section_writer (title=%s, hit=%s)",
            _write_title_early, _hit_kind,
        )
        _dash_emit(state, where="supervisor", picked="vector_search_agent", reason="write_rag_fastpath_with_vector")
        return {"messages": messages, "task_history": tasks, "flags": state.get("flags", {}), "rag_on_disk": True, "topic_title": state.get("topic_title")}

    # [§research-1 R28] fast-path(:721) 밖에서도 section_writer Task 를 만든다.
    #   위 블록이 return 하므로 여기는 fast-path 미진입 경로 전용이다.
    #   사유: :725 가 프로덕션 유일한 section_writer Task 생성 지점인데 fast-path 안에 있어,
    #         write 어간이 없는 질의(관통 2회차)에서는 ⑧이 설 근거가 만들어지지 않았다.
    #         라우터(core/routers.py:301)는 write: prefix Task 만 본다. 박제: R26 §1-d·§1-e.
    #   제목: _write_title_early 가 있으면 그것(기존 동작 유지), 없으면 CFG.TOPIC_TITLE(:128 과 동일 형태).
    #         빈 문자열이면 Task 를 만들지 않는다 — "write: " 를 만드느니 안 만드는 편이 낫다.
    if not _safe_has_pending(tasks, "section_writer"):
        _r28_title = _write_title_early or (getattr(config.CFG, "TOPIC_TITLE", "") or "").strip()
        if _r28_title:
            tasks.append(Task(agent="section_writer", done=False, description=f"write: {_r28_title}", done_at=""))

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

    # fast-path: write:
    target_from_line = extract_write_title(last_text)
    if not target_from_line:
        idx = extract_section_index(last_text)
        if idx:
            target_from_line = _title_by_index(get_topic_outline_text(state), idx)

    if target_from_line:
        # ── SAFETY GUARD: 이미 완료된 섹션이면 writer 예약/락을 다시 걸지 않는다 ──
        try:
            flags_now: Dict[str, Any] = dict(cast(Dict[str, Any], state.get("flags") or {}))
            completed_now = {
                str(t).strip()
                for t in (flags_now.get("completed_sections") or [])
                if str(t).strip()
            }
        except Exception:
            completed_now = set()

        if target_from_line.strip() in completed_now:
            logger.info(
                "[Supervisor fast-path] write: requested title already completed → communicator (title=%s)",
                target_from_line,
            )
            # 이미 작성된 섹션이므로, 진행상황 안내만 communicator에게 맡긴다.
            if not _safe_has_pending(tasks, "communicator"):
                tasks.append(
                    Task(
                        agent="communicator",
                        done=False,
                        description=f"'{target_from_line}' 섹션은 이미 작성됨: 진행상황 보고 및 다음 섹션 안내",
                        done_at="",
                    )
                )
            _dash_emit(state, where="supervisor", picked="communicator", reason="write_already_completed")
            return {
                "messages": messages,
                "task_history": tasks,
                "flags": state.get("flags", {}),
            }

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
                # 새 코어 스케줄러는 state 기반으로만 동작하므로,
                # 플래그 세팅 후 reason만 전달한다.
                schedule_writer_if_needed(
                    mstate,
                    reason="pre_schedule_write_with_empty_or_pending_refs",
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

        # 호출 전/후 router.writer_pending 플래그를 비교하여 did 여부 추론
        flags_before: Dict[str, Any] = dict(cast(Dict[str, Any], mstate.get("flags") or {}))
        router_before: Dict[str, Any] = dict(flags_before.get("router") or {})
        was_pending = bool(router_before.get("writer_pending"))

        schedule_writer_if_needed(
            mstate,
            reason="write_with_refs",
        )

        flags_after: Dict[str, Any] = dict(cast(Dict[str, Any], mstate.get("flags") or {}))
        router_after: Dict[str, Any] = dict(flags_after.get("router") or {})
        now_pending = bool(router_after.get("writer_pending"))
        did = (not was_pending) and now_pending
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
        # 호출 전/후 router.writer_pending 플래그 비교로 did 여부 추론
        flags_before2: Dict[str, Any] = dict(cast(Dict[str, Any], mstate.get("flags") or {}))
        router_before2: Dict[str, Any] = dict(flags_before2.get("router") or {})
        was_pending2 = bool(router_before2.get("writer_pending"))

        schedule_writer_if_needed(
            mstate,
            reason="supervisor_llm_writer",
        )

        flags_after2: Dict[str, Any] = dict(cast(Dict[str, Any], mstate.get("flags") or {}))
        router_after2: Dict[str, Any] = dict(flags_after2.get("router") or {})
        now_pending2 = bool(router_after2.get("writer_pending"))
        did = (not was_pending2) and now_pending2
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
        # ── §12-15 가드: refs(in-memory)가 비어있어도 rag_on_disk(Chroma 영속)면
        # web_search 로 빠지지 않고 vector_search 우선. 서버 재시작 직후엔 state["references"]
        # 가 휘발해 refs_empty=True 지만 디스크 RAG 는 살아있는 케이스를 처리한다.
        has_on_disk = bool(state.get("rag_on_disk"))
        if refs_empty and not has_on_disk:
            _dash_emit(state, where="router", picked="web_search_agent", reason="writer_locked_refs_empty_no_rag")
            return "web_search_agent"
        if _has("vector_search_agent"):
            _dash_emit(state, where="router", picked="vector_search_agent", reason="writer_locked_vector_pending")
            return "vector_search_agent"
        ret = "section_writer" if _doc_mode() == "report" else "chapter_writer"
        _dash_emit(state, where="router", picked=ret, reason="writer_pending_locked_title_refs_or_rag_ok")
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

    if is_outline_creation(last_text):
        ret = "content_strategist"; _dash_emit(state, where="router", picked=ret, reason="create_outline"); return ret

    write_title = extract_write_title(last_text)
    if not write_title:
        idx_fallback = extract_section_index(last_text)
        if idx_fallback:
            write_title = _title_by_index(get_topic_outline_text(state), idx_fallback)
    if write_title:
        _has_rag_on_disk = bool(state.get("rag_on_disk"))
        if refs_empty and not _has_rag_on_disk:
            ret = "web_search_agent"; _dash_emit(state, where="router", picked=ret, reason="write_refs_empty"); return ret
        if _has("vector_search_agent"):
            ret = "vector_search_agent"; _dash_emit(state, where="router", picked=ret, reason="write_vector_pending"); return ret
        ret = preferred; _dash_emit(state, where="router", picked=ret, reason="write_refs_present_or_rag"); return ret

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
