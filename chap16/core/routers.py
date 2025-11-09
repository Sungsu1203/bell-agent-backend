from __future__ import annotations

import os
import logging
from typing import MutableMapping, Any, cast, Optional, Dict, Callable

logger = logging.getLogger(__name__)

# NOTE: communicator가 outline 표시 후 반드시 outline_shown=True를 세팅한다는 전제
# [ADD] ── Metrics (optional) ────────────────────────────────────────────────
# 타입 안정화를 위해 Optional[Callable]로 어노테이션
_metrics_snapshot: Optional[Callable[[str], Any]] = None
_metrics_check_alerts: Optional[Callable[[Any], Any]] = None
try:
    from tools.metrics import snapshot as _ms
    from tools.metrics import check_thresholds_and_alert as _mca
    _metrics_snapshot = cast(Callable[[str], Any], _ms)
    _metrics_check_alerts = cast(Callable[[Any], Any], _mca)
except Exception:
    pass

# [ADD] ── Findings quick-ingest resolver (lazy import to avoid circular load)
def _get_findings_ingest_func() -> Optional[Callable[..., Any]]:
    """
    런타임에 안전하게 임포트해 callable을 반환한다.
    우선순위: add_local_findings_to_chroma → quick_ingest_findings
    """
    try:
        from tools.local_rag import add_local_findings_to_chroma as _alf
        return cast(Callable[..., Any], _alf)
    except Exception:
        pass
    # 정적분석기(마이파이/파이랜스) 경고 회피: importlib + getattr 사용
    try:
        import importlib
        mod = importlib.import_module("tools.local_rag")
        _qif = getattr(mod, "quick_ingest_findings", None)
        if callable(_qif):
            return cast(Callable[..., Any], _qif)
    except Exception:
        pass
    return None


# CFG / 경로 유틸 (동적 접근)
import core.config as config
from core.state_types import State
from utils.sanitize import as_int
from utils.outline import get_topic_outline_text
from utils.tasks import has_pending
from utils.writer_scheduler import schedule_writer_if_needed
from core.paths import research_resources_dir  # 중앙 경로 유틸 사용
from utils.rag_utils import set_direct_qa_flag, is_qa_like


# ─────────────────────────────────────────────────────────────
# Helpers: 동적 CFG 접근 & 공통 라우팅 유틸
# ─────────────────────────────────────────────────────────────
def _cfg_bool(name: str, default: bool = False) -> bool:
    try:
        v = getattr(config.CFG, name, default)
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1","true","yes","on","y"}
    except Exception:
        return default

def _doc_mode() -> str:
    try:
        m = getattr(config.CFG, "DOC_MODE", "report")
        return "book" if m == "book" else "report"
    except Exception:
        return "report"
    
def _safe_int(x: Any, default: int = 0) -> int:
    """object → int 안전 변환(실패 시 default)."""
    try:
        return int(cast(Any, x))
    except Exception:
        return default


def _preferred_writer() -> str:
    return "section_writer" if _doc_mode() == "report" else "chapter_writer"

def _alt_writer() -> str:
    return "chapter_writer" if _preferred_writer() == "section_writer" else "section_writer"

def _skip_web_search(state: State) -> bool:
    flags = state.get("flags") or {}
    return _cfg_bool("SKIP_WEB_SEARCH", False) or bool(flags.get("skip_web_search"))

def _metrics_snapshot_and_alert(state: State) -> None:
    """연구 라운드 종료 시 스냅샷 저장 및 임계치 알람(있으면) 처리."""
    try:
        # 알람 체크
        if _metrics_check_alerts is not None:
            _metrics_check_alerts(logger)

        # 스냅샷 저장 (경로 구성)
        if _metrics_snapshot is not None:
            import time  # 지역 임포트로 의존 최소화
            topic_slug = (state.get("topic_slug") or config.CFG.TOPIC_SLUG or "default").strip()
            base_dir = research_resources_dir(topic_slug)  # <project>/resources/<topic>
            base_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = (base_dir / f"metrics_{int(time.time())}.json").as_posix()

            _metrics_snapshot(snapshot_path)
            logger.info("[METRICS] snapshot saved → %s", snapshot_path)
    except Exception as e:
        logger.debug("[METRICS] snapshot/alert skipped: %s", e)

def _set_flag(state: State, key: str, value: Any) -> None:
    """
    mypy/TypedDict 호환을 위한 flags 안전 갱신 헬퍼.
    - 기존 flags가 dict가 아니어도 안전하게 새 dict로 교체
    - 얕은 복사 후 키만 갱신하여 재대입
    """
    try:
        cur = state.get("flags")
        base: Dict[str, Any] = dict(cur) if isinstance(cur, dict) else {}
        base[key] = value
        cast(MutableMapping[str, Any], state)["flags"] = base
    except Exception:
        # 최후 폴백: 최소 dict로 설정
        cast(MutableMapping[str, Any], state)["flags"] = {key: value}

def _last_ai_message(state: State) -> str:
    """
    state.messages에서 마지막 AI 발화 텍스트를 찾아 반환.
    없으면 빈 문자열.
    """
    try:
        msgs = state.get("messages") or []
        for m in reversed(list(msgs)):
            role = (getattr(m, "role", "") or getattr(m, "type", "") or "").lower()
            if role in ("assistant", "ai"):
                content = getattr(m, "content", "") or ""
                if isinstance(content, str) and content.strip():
                    return content.strip()
                # content가 dict/리치구조일 수 있는 경우 최소 처리
                try:
                    txt = str(content)
                    return txt.strip()
                except Exception:
                    pass
        return ""
    except Exception:
        return ""

def _retry_under(state: State, router_key: str, *, max_times: int = 1) -> bool:
    """
    flags.router[router_key] 카운터가 max_times 미만이면 +1 후 True, 아니면 False.
    - after_web_ws_retries 등과 같은 키를 재사용하여 재시도 총량을 1회로 제한.
    """
    try:
        flags = state.get("flags") or {}
        rflags: Dict[str, Any] = dict(flags.get("router") or {})
        cur = int(rflags.get(router_key, 0) or 0)
        if cur < max_times:
            rflags[router_key] = cur + 1
            flags = dict(flags)
            flags["router"] = rflags
            cast(MutableMapping[str, Any], state)["flags"] = flags
            return True
        return False
    except Exception:
        return False

def tail_task_router(state: State) -> str:
    """작성 단계(테일)에서 다음 노드를 선택."""
    # 아웃라인 존재/표시 상태 점검
    outline_text = get_topic_outline_text(state)
    outline_missing = not (outline_text or "").strip()
    outline_fname = (state.get("outline_fname") or "").strip()
    # 가드 조건:
    #  - outline_shown이 True면 재표시 금지
    #  - outline_fname이 비어있으면 커뮤니케이터로 보내지 않음(불필요 반복 방지)
    outline_already_shown = (state.get("outline_shown") is True)
    need_outline_display = (not outline_already_shown) and bool(outline_fname)

    if outline_missing:
        logger.info("[router.tail] outline missing → content_strategist")
        return "content_strategist"

    if need_outline_display:
        # writer-락(pending_write_title) 우선 라우팅
        flags = state.get("flags") or {}
        if flags.get("pending_write_title"):
            tasks = state.get("task_history", []) or []
            preferred_writer = _preferred_writer()
            alt_writer = _alt_writer()
            if has_pending(tasks, preferred_writer, prefix="write:") or has_pending(tasks, alt_writer, prefix="write:"):
                logger.info("[router.tail] outline exists but not shown — writer lock → %s", preferred_writer)
                return preferred_writer
        # outline 파일명도 있고 아직 표시 안 됨 → communicator로 1회 전달
        logger.info(
            "[router.tail] outline exists but not shown → communicator "
            "(fname=%s, shown=%s)",
            outline_fname, state.get("outline_shown")
        )
        return "communicator"

    tasks = state.get("task_history", []) or []

    # 1) 선호 writer가 미완료면 우선
    preferred_writer = _preferred_writer()
    for t in reversed(tasks):
        if (not getattr(t, "done", False)) and getattr(t, "agent", "") == preferred_writer:
            logger.debug("[router.tail] preferred writer pending → %s", preferred_writer)
            return preferred_writer

    # 2) 대안 writer가 미완료면 그 다음
    alt_writer = _alt_writer()
    for t in reversed(tasks):
        if (not getattr(t, "done", False)) and getattr(t, "agent", "") == alt_writer:
            logger.debug("[router.tail] alt writer pending → %s", alt_writer)
            return alt_writer

    # writer-락 우선 (커뮤니케이터 펜딩보다 먼저)
    refs = state.get("references") or {}
    refs_empty = not (refs.get("docs") or [])
    if has_pending(tasks, preferred_writer, prefix="write:") or has_pending(tasks, alt_writer, prefix="write:"):
        if refs_empty:
            logger.debug("[router.tail] write: pending but refs empty → web_search_agent")
            return "web_search_agent"
        logger.debug("[router.tail] writer pending(write:) → %s", preferred_writer)
        return preferred_writer

    # 3) 커뮤니케이터가 미완료면
    for t in reversed(tasks):
        if (not getattr(t, "done", False)) and getattr(t, "agent", "") == "communicator":
            logger.debug("[router.tail] communicator pending → communicator")
            return "communicator"

    # 4) 아무 것도 없으면 기본 writer
    logger.info("[router.tail] no pending tasks → preferred writer %s", preferred_writer)
    return preferred_writer


def after_user_message(state: State) -> str:
    """
    사용자 입력 직후 라우팅:
    - Direct QA 트리거 시: 바로 벡터검색으로(웹검색/연구 스킵)
    - 그 외: 기존 상위 플로우(supervisor)로 위임
    """
    # last_user가 object로 들어오는 경우 방어: 문자열일 때만 strip()
    raw = state.get("last_user")
    user_q = raw.strip() if isinstance(raw, str) else ""
    # Direct QA 플래그 설정(환경/DIRECT_QA, SKIP_WEB_SEARCH, 질의 형태 기반)
    set_direct_qa_flag(cast(MutableMapping[str, Any], state), user_q)
    if (state.get("flags") or {}).get("qa_direct_reply"):
        return "vector_search_agent"
    return "supervisor"


def after_web_search_agent(state: State) -> str:
    """
    웹 검색 완료 후 라우팅 가드:
    1) pending에 vector_search_agent가 있으면 → vector_search_agent
    2) 연구 루프 활성 시 → research_synthesizer
    3) SKIP_WEB_SEARCH=1이면 → vector_search_agent
    4) 인덱스 준비(rag_on_disk) 또는 신규 URL/refs 문서가 있으면 → vector_search_agent
    5) 위 모두 아니면: '단 1회' web_search_agent 재시도 (task_history로 판단)
    6) 재시도 후에도 비어있으면 tail_task_router로 위임
    """
    tasks = state.get("task_history", []) or []
    flags = state.get("flags") or {}
    refs = state.get("references") or {}
    refs_light = state.get("refs") or {}

    # Direct QA는 웹검색 경로를 사용하지 않음
    if (flags or {}).get("qa_direct_reply"):
        logger.info("[router.after_web] qa_direct_reply=True → vector_search_agent")
        return "vector_search_agent"

    # 안전한 정수 추출 유틸 (여러 후보 키 중 먼저 맞는 것 사용)
    def _first_int(keys: list[str], default: int = 0) -> int:
        for k in keys:
            if k in state:
                # 프로젝트의 안전 변환기 사용(Union/object 대응)
                return as_int(state, k, default)
        return default

    # 신규 URL/청크 지표
    new_url_count = _first_int(
        ["round_added_urls", "new_url_count", "new_url_count_round", "round_new_urls", "new_urls"],
        default=0,
    )
    has_docs_in_refs = bool(refs.get("docs") or [])        # 미리보기 문서 등
    has_urls_in_refs = bool(refs_light.get("docs") or [])  # 경량 refs(문자열 URL 리스트)

    rag_on_disk = bool(state.get("rag_on_disk"))
    skip_web = _skip_web_search(state)

    # 0) pending 리스트로 강제 지정된 경우 우선
    if "vector_search_agent" in (state.get("pending") or []):
        logger.info("[router.after_web] pending contains vector_search_agent → vector_search_agent")
        return "vector_search_agent"

    # 1) 연구 루프가 켜져 있으면 합성기로 직행
    if bool(state.get("research_loop_active")):
        logger.info("[router.after_web] research loop active=True → research_synthesizer")
        return "research_synthesizer"

    # 2) 웹 스킵 환경이면 바로 벡터검색
    if skip_web:
        logger.info("[router.after_web] SKIP_WEB_SEARCH=1 → vector_search_agent")
        return "vector_search_agent"

    # 3) 인덱스 준비 또는 신규 참조가 생겼으면 벡터검색
    if rag_on_disk or new_url_count > 0 or has_docs_in_refs or has_urls_in_refs:
        logger.info(
            "[router.after_web] rag_on_disk=%s new_urls=%s has_docs=%s has_urls=%s → vector_search_agent",
            rag_on_disk, new_url_count, has_docs_in_refs, has_urls_in_refs
        )
        return "vector_search_agent"

    # 4) 여기까지 왔다는 건 '비어있음' → web_search 로 재시도 (최대 1회)
    #    ※ setdefault 타입오류 회피: dict 복사/병합 후 되돌려쓰기
    router_flags: Dict[str, Any] = dict((state.get("flags") or {}).get("router") or {})
    retries = _safe_int(router_flags.get("after_web_ws_retries", 0), 0)
    if retries < 1:
        router_flags["after_web_ws_retries"] = retries + 1
        # TypedDict(Flags) 안전 갱신: 가능하면 in-place, 없으면 최소 폴백
        _flags = state.get("flags")
        if isinstance(_flags, dict):
            _flags_mm = cast(MutableMapping[str, Any], _flags)
            _flags_mm["router"] = router_flags
            # 재부착: State TypedDict에 맞춰 명시적 캐스트 후 대입
            cast(MutableMapping[str, Any], state)["flags"] = _flags_mm
        else:
            state_flags: Dict[str, Any] = {"router": router_flags}
            cast(MutableMapping[str, Any], state)["flags"] = state_flags
        logger.info("[router.after_web] refs empty & no new URLs → web_search_agent (retry %d/1)", retries + 1)
        return "web_search_agent"

    # 5) 재시도까지 했는데도 비어있다면 tail 라우터에 위임
    nxt = tail_task_router(state)
    logger.info("[router.after_web] refs empty (retry exhausted) → %s", nxt)
    return nxt


def after_vector_router(state: State) -> str:
    """벡터검색 이후 라우팅."""
    tasks = state.get("task_history", []) or []
    flags = state.get("flags") or {}

    # 0) 연구 모드 강제 합성 라우팅
    if bool(state.get("research_loop_active")):
        # QA 단락 플래그를 내려 부작용 방지(FLAGS 경로로 일원화)
        _set_flag(state, "qa_direct_reply", False)
        logger.info("[router.after_vector] research_loop_active=True → research_synthesizer (override qa_direct_reply)")
        return "research_synthesizer"

    # Direct QA 가드:
    # - 답(qa_reply 또는 마지막 AI 발화)이 있으면 → communicator
    # - 답이 없으면 → web_search_agent 1회 재시도 (키: after_web_ws_retries)
    # - 재시도 후에도 없으면 → qa_direct_reply를 내려 벡터로 종료 보고
    if (flags or {}).get("qa_direct_reply"):
        _set_flag(state, "suppress_writer", True)  # writer 충돌 방지
        has_reply = bool(state.get("qa_reply")) or bool(_last_ai_message(state))
        if has_reply:
            logger.info("[router.after_vector] qa_direct_reply=True & reply found → communicator")
            return "communicator"
        # 답이 없으면 — web_search_agent 재시도(최대 1회, after_web_ws_retries 공유)
        if _retry_under(state, "after_web_ws_retries", max_times=1):
            logger.info("[router.after_vector] qa_direct_reply=True but no reply → web_search_agent (retry 1/1)")
            return "web_search_agent"
        # 재시도 소진: Direct QA 종료(루프 충돌 방지), 벡터로 종료 보고
        _set_flag(state, "qa_direct_reply", False)
        logger.info("[router.after_vector] qa_direct_reply exhausted without reply → vector_search_agent (final)")
        return "vector_search_agent"

    # 1) (옵션) 집필 예약 — 연구 중 허용 플래그로 제어
    schedule_writer_if_needed(
        cast(MutableMapping[str, Any], state),
        tasks=tasks,
        messages=state.get("messages"),
        outline_text=get_topic_outline_text(state),
        allow_during_research=bool(config.CFG.AUTO_WRITE_DURING_RESEARCH),
    )

    # refs 가드: refs 비어있으면 write: 펜딩이어도 우선 RAG(Web)
    preferred_writer = _preferred_writer()
    alt_writer = _alt_writer()
    has_write_pending = (
        has_pending(tasks, preferred_writer, prefix="write:") or
        has_pending(tasks, alt_writer, prefix="write:")
    )
    if has_write_pending:
        refs = state.get("references") or {}
        refs_empty = not (refs.get("docs") or [])
        if refs_empty:
            logger.info("[router.after_vector] write: pending but refs empty → web_search_agent")
            return "web_search_agent"
        logger.info("[router.after_vector] writer pending(write:) → %s", preferred_writer)
        return preferred_writer

    # 2) (이전 가드에서 이미 처리됨) — qa_direct_reply는 위에서 커뮤니케이터로 전환

    # 3) 연구 루프 조건 충족 시 → synthesizer
    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)
    has_objs = bool(state.get("research_objectives"))

    if (role == "research analyst") and has_objs and (rounds_done < max_iter):
        logger.info("[router.after_vector] research loop continues → research_synthesizer")
        return "research_synthesizer"

    # 4) 그 외 → tail router
    nxt = tail_task_router(state)
    logger.info("[router.after_vector] fallback → %s", nxt)
    return nxt


def after_planner_router(state: State) -> str:
    """
    플래너 이후 라우팅:
    1) announce=1 → communicator
    2) writer 펜딩이 있으면 writer 최우선
    3) 쿼리 없으면 communicator
    4) SKIP_WEB_SEARCH=1 또는 state.flags.skip_web_search → vector_search_agent
    5) refs/references에 이미 문서가 있거나 rag_on_disk=True → vector_search_agent
    6) 기본: web_search_agent
    """
    tasks = state.get("task_history", []) or []

    # refs → references 미러링(혼용 방지)
    if ("refs" in state) and ("references" not in state):
        try:
            state["references"] = state.get("refs") or {}
        except Exception:
            pass

    def _pending_writer() -> Optional[str]:
        preferred = _preferred_writer()
        for t in reversed(tasks):
            if (not getattr(t, "done", False)) and getattr(t, "agent", "") == preferred:
                return preferred
        alt = _alt_writer()
        for t in reversed(tasks):
            if (not getattr(t, "done", False)) and getattr(t, "agent", "") == alt:
                return alt
        return None

    announce = bool(config.CFG.RESEARCH_PLANNER_ANNOUNCE) or as_int(state, "research_planner_announce", 0) == 1
    if announce:
        logger.info("[router.after_planner] announce=1 → communicator")
        return "communicator"

    w = _pending_writer()
    if w:
        logger.info("[router.after_planner] writer pending → %s", w)
        return w

    plan_qs = ((state.get("research_plan") or {}).get("queries") or []) or state.get("planner_queries") or []
    have_queries = bool(plan_qs)
    if not have_queries:
        if bool(state.get("research_loop_active")):
            logger.info("[router.after_planner] no planner queries but research_loop_active=True → research_synthesizer")
            return "research_synthesizer"
        logger.info("[router.after_planner] no planner queries → communicator")
        return "communicator"

    flags = state.get("flags") or {}
    skip_web = _skip_web_search(state)
    if skip_web:
        logger.info("[router.after_planner] SKIP_WEB_SEARCH=1 → vector_search_agent")
        return "vector_search_agent"

    # 로컬 인덱스/참조가 이미 있으면 웹검색 생략하고 바로 벡터로
    refs = state.get("references") or {}
    has_refs_docs = bool(refs.get("docs") or [])
    rag_on_disk = bool(state.get("rag_on_disk"))
    doc_count = _safe_int(state.get("doc_count"), 0)  # 있으면 활용(없어도 무시)

    if has_refs_docs or rag_on_disk or doc_count > 0:
        logger.info("[router.after_planner] refs/docs or rag_on_disk detected → vector_search_agent")
        return "vector_search_agent"

    logger.info("[router.after_planner] default → web_search_agent")
    return "web_search_agent"


def after_synthesizer_router(state: State) -> str:
    """
    합성기 이후 라우팅:
    - 연구 라운드를 더 돌지 결정(신규 URL 수, 최소/최대 라운드, 무신규 연속치 등)
    - 계속 연구면 research_planner, 아니면 tail_task_router(writer/communicator 등)
    """
    tasks = state.get("task_history", []) or []

    schedule_writer_if_needed(
        cast(MutableMapping[str, Any], state),
        tasks=tasks,
        messages=state.get("messages"),
        outline_text=get_topic_outline_text(state),
        allow_during_research=bool(config.CFG.AUTO_WRITE_DURING_RESEARCH),
    )

    # write: 펜딩이 있으면 writer 우선
    preferred_writer = _preferred_writer()
    alt_writer = _alt_writer()
    if has_pending(tasks, preferred_writer, prefix="write:") or has_pending(tasks, alt_writer, prefix="write:"):
        logger.info("[router.after_synth] writer pending(write:) → %s", preferred_writer)
        # 합성 이후 writer로 즉시 전이되는 경우도 라운드 종료로 간주하여 스냅샷/알람
        _metrics_snapshot_and_alert(state)
        return preferred_writer

    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)

    if getattr(config.CFG, "DEBUG_ROUTER_KEYS", False) or os.getenv("DEBUG_ROUTER_KEYS") == "1":
        keys_preview = list(state.keys())[:40]
        logger.debug("[router.after_synth] keys[:40]=%s", keys_preview)

    def first_int(st: State, keys: list[str], default: int = 0) -> int:
        for k in keys:
            if k in st:
                return as_int(st, k, default)
        return default

    # 이번 라운드의 "신규 URL" 수치(여러 키 중 먼저 찾음)
    url_new_actual = first_int(
        state,
        ["round_added_urls", "new_url_count", "new_url_count_round", "new_urls", "round_new_urls"],
        default=0,
    )

    # 합성 루프/중단 파라미터
    halt_threshold = as_int(state, "research_halt_threshold", getattr(config.CFG, "RESEARCH_HALT_THRESHOLD", 0))
    min_rounds = as_int(state, "research_min_rounds", getattr(config.CFG, "RESEARCH_MIN_ROUNDS", 0))
    max_no_new = as_int(state, "research_max_no_new_rounds", getattr(config.CFG, "RESEARCH_MAX_NO_NEW_ROUNDS", 0))
    no_new_streak = as_int(state, "no_new_url_streak", 0)

    can_continue = (
        (rounds_done < max_iter)
        and ((rounds_done < min_rounds) or (url_new_actual > halt_threshold) or (no_new_streak < max_no_new))
    )

    logger.info(
        "[router.after_synth] round=%s/%s | new=%s | streak=%s (max_no_new=%s) | min=%s | threshold=%s | continue=%s",
        rounds_done, max_iter, url_new_actual, no_new_streak, max_no_new, min_rounds, halt_threshold, can_continue
    )

    if can_continue:
        logger.info("[router.after_synth] continue research → research_planner")
        return "research_planner"

    # 연구 중단(라운드 종료) 시점
    # 1) 방금 생성된 findings를 즉시 RAG에 포함시키기 위한 경량 재스캔
    #    (callable 체크: quick_ingest_findings가 없거나 함수가 아니면 스킵)
    try:
        # findings quick-ingest
        from tools.local_rag import quick_ingest_findings as _qif  # lazy import
        topic_slug = (state.get("topic_slug") or getattr(config.CFG, "TOPIC_SLUG", "") or "default").strip()
        added = _qif(topic_slug) if callable(_qif) else 0
        logger.info("[router.after_synth] findings quick-ingest added=%s (topic=%s)", added, topic_slug)
    except Exception as e:
        logger.debug("[router.after_synth] findings quick-ingest skipped: %s", e)

    # 2) 스냅샷 & 임계치 알람
    _metrics_snapshot_and_alert(state)

    nxt = tail_task_router(state)
    logger.info("[router.after_synth] halt research → %s", nxt)
    return nxt


# ─────────────────────────────────────────────────────────────
# 그래프 빌더가 기대하는 이름과 매칭되는 에일리어스
def router_after_vector(state: State):
    return after_vector_router(state)

def router_after_planner(state: State):
    return after_planner_router(state)

def router_after_synth(state: State):
    return after_synthesizer_router(state)

# 내보내기 심볼(정적 선언)
__all__ = [
    "tail_task_router",
    "after_user_message",
    "after_web_search_agent",
    "after_vector_router",
    "after_planner_router",
    "after_synthesizer_router",
    "router_after_vector",
    "router_after_planner",
    "router_after_synth",
]