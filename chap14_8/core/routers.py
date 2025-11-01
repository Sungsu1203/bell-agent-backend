from __future__ import annotations

import os
import logging
from typing import MutableMapping, Any, cast, Optional

logger = logging.getLogger(__name__)

# [ADD] ── Metrics (optional) ────────────────────────────────────────────────
try:
    from tools.metrics import snapshot as _metrics_snapshot
    from tools.metrics import check_thresholds_and_alert as _metrics_check_alerts
except Exception:
    _metrics_snapshot = None
    _metrics_check_alerts = None

# CFG / 경로 유틸 (동적 접근)
import core.config as config
from core.state_types import State
from utils.sanitize import as_int
from utils.outline import get_topic_outline_text
from utils.tasks import has_pending
from utils.writer_scheduler import schedule_writer_if_needed
from core.paths import research_resources_dir  # 중앙 경로 유틸 사용


def _metrics_snapshot_and_alert(state: State) -> None:
    """연구 라운드 종료 시 스냅샷 저장 및 임계치 알람(있으면) 처리."""
    try:
        # 알람 체크
        if _metrics_check_alerts:
            _metrics_check_alerts(logger)

        # 스냅샷 저장 (경로 구성)
        if _metrics_snapshot:
            import time  # 지역 임포트로 의존 최소화
            topic_slug = (state.get("topic_slug") or config.CFG.TOPIC_SLUG or "default").strip()
            base_dir = research_resources_dir(topic_slug)  # <project>/resources/<topic>
            base_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = (base_dir / f"metrics_{int(time.time())}.json").as_posix()

            _metrics_snapshot(snapshot_path)
            logger.info("[METRICS] snapshot saved → %s", snapshot_path)
    except Exception as e:
        logger.debug("[METRICS] snapshot/alert skipped: %s", e)


def tail_task_router(state: State) -> str:
    """작성 단계(테일)에서 다음 노드를 선택."""
    outline_text = get_topic_outline_text(state)
    outline_missing = not (outline_text or "").strip()
    outline_not_shown = state.get("outline_shown") is False

    if outline_missing:
        logger.info("[router.tail] outline missing → content_strategist")
        return "content_strategist"

    if outline_not_shown:
        # writer-락(pending_write_title) 우선 라우팅
        flags = state.get("flags") or {}
        if flags.get("pending_write_title"):
            tasks = state.get("task_history", []) or []
            preferred_writer = "section_writer" if config.CFG.DOC_MODE == "report" else "chapter_writer"
            alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
            if has_pending(tasks, preferred_writer, prefix="write:") or has_pending(tasks, alt_writer, prefix="write:"):
                logger.info("[router.tail] outline exists but not shown — writer lock → %s", preferred_writer)
                return preferred_writer
        logger.info("[router.tail] outline exists but not shown → communicator")
        return "communicator"

    tasks = state.get("task_history", []) or []

    # 1) 선호 writer가 미완료면 우선
    preferred_writer = "section_writer" if config.CFG.DOC_MODE == "report" else "chapter_writer"
    for t in reversed(tasks):
        if (not getattr(t, "done", False)) and getattr(t, "agent", "") == preferred_writer:
            logger.debug("[router.tail] preferred writer pending → %s", preferred_writer)
            return preferred_writer

    # 2) 대안 writer가 미완료면 그 다음
    alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
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

    # 안전한 정수 추출 유틸 (여러 후보 키 중 먼저 맞는 것 사용)
    def _first_int(keys: list[str], default: int = 0) -> int:
        for k in keys:
            if k in state:
                try:
                    return int(state.get(k) or 0)
                except Exception:
                    pass
        return default

    # 신규 URL/청크 지표
    new_url_count = _first_int(
        ["round_added_urls", "new_url_count", "new_url_count_round", "round_new_urls", "new_urls"],
        default=0,
    )
    has_docs_in_refs = bool(refs.get("docs") or [])        # 미리보기 문서 등
    has_urls_in_refs = bool(refs_light.get("docs") or [])  # 경량 refs(문자열 URL 리스트)

    rag_on_disk = bool(state.get("rag_on_disk"))
    skip_web = bool(config.CFG.SKIP_WEB_SEARCH) or bool(flags.get("skip_web_search"))

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

    # 4) 여기까지 왔다는 건 '비어있음' → web_search 로 재시도 (1회 한정)
    recent_ws_done = False
    for t in reversed(tasks):
        # 바로 직전에 web_search_agent가 완료되었는지 확인
        if getattr(t, "agent", "") == "web_search_agent":
            recent_ws_done = bool(getattr(t, "done", False))
            break
        # 다른 완료된 태스크를 만나면 최근 web_search가 아님
        if getattr(t, "done", False):
            break

    if not recent_ws_done:
        logger.info("[router.after_web] refs empty & no new URLs → web_search_agent (retry 1/1)")
        return "web_search_agent"

    # 5) 재시도까지 했는데도 비어있다면 tail 라우터에 위임
    nxt = tail_task_router(state)
    logger.info("[router.after_web] refs empty (retry exhausted) → %s", nxt)
    return nxt


def after_vector_router(state: State) -> str:
    """벡터검색 이후 라우팅."""
    tasks = state.get("task_history", []) or []

    # 0) 연구 모드 강제 합성 라우팅
    if bool(state.get("research_loop_active")):
        # QA 단락 플래그를 내려 부작용 방지
        state["qa_direct_reply"] = False
        logger.info("[router.after_vector] research_loop_active=True → research_synthesizer (override qa_direct_reply)")
        return "research_synthesizer"

    # 1) (옵션) 집필 예약 — 연구 중 허용 플래그로 제어
    schedule_writer_if_needed(
        cast(MutableMapping[str, Any], state),
        tasks=tasks,
        messages=state.get("messages"),
        outline_text=get_topic_outline_text(state),
        allow_during_research=bool(config.CFG.AUTO_WRITE_DURING_RESEARCH),
    )

    # refs 가드: refs 비어있으면 write: 펜딩이어도 우선 RAG(Web)
    preferred_writer = "section_writer" if config.CFG.DOC_MODE == "report" else "chapter_writer"
    alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
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

    # 2) QA 직답 모드면 → 커뮤니케이터
    if state.get("qa_direct_reply"):
        logger.info("[router.after_vector] qa_direct_reply=True → communicator")
        return "communicator"

    # 3) 연구 루프 조건 충족 시 → synthesizer
    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = int(state.get("research_round") or 0)
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
        preferred = "section_writer" if config.CFG.DOC_MODE == "report" else "chapter_writer"
        for t in reversed(tasks):
            if (not getattr(t, "done", False)) and getattr(t, "agent", "") == preferred:
                return preferred
        alt = "chapter_writer" if preferred == "section_writer" else "section_writer"
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
    skip_web = bool(config.CFG.SKIP_WEB_SEARCH) or bool(flags.get("skip_web_search"))
    if skip_web:
        logger.info("[router.after_planner] SKIP_WEB_SEARCH=1 → vector_search_agent")
        return "vector_search_agent"

    # 로컬 인덱스/참조가 이미 있으면 웹검색 생략하고 바로 벡터로
    refs = state.get("references") or {}
    has_refs_docs = bool(refs.get("docs") or [])
    rag_on_disk = bool(state.get("rag_on_disk"))
    doc_count = int(state.get("doc_count") or 0)  # 있으면 활용(없어도 무시)

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
    preferred_writer = "section_writer" if config.CFG.DOC_MODE == "report" else "chapter_writer"
    alt_writer = "chapter_writer" if preferred_writer == "section_writer" else "section_writer"
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
    halt_threshold = as_int(state, "research_halt_threshold", config.CFG.RESEARCH_HALT_THRESHOLD)
    min_rounds = as_int(state, "research_min_rounds", config.CFG.RESEARCH_MIN_ROUNDS)
    max_no_new = as_int(state, "research_max_no_new_rounds", config.CFG.RESEARCH_MAX_NO_NEW_ROUNDS)
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

    # 연구 중단(라운드 종료) 시점 → 스냅샷 & 임계치 알람
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
    "after_web_search_agent",
    "after_vector_router",
    "after_planner_router",
    "after_synthesizer_router",
    "router_after_vector",
    "router_after_planner",
    "router_after_synth",
]