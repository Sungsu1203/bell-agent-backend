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
def _get_findings_ingest_func() -> Optional[Callable[[str], Any]]:
    """
    런타임에 안전하게 임포트해 callable을 반환한다.
    - tools.web_rag.ingest_docs.quick_ingest_findings(topic_slug) 를 우선 사용한다.
    - 모듈 자체를 함수처럼 호출하지 않고, 모듈 안의 헬퍼 함수만 호출한다.
    """
    try:
        from tools.web_rag import ingest_docs as _ingest_docs
        fn = getattr(_ingest_docs, "quick_ingest_findings", None)
        if callable(fn):
            # 시그니처: (topic_slug: str) -> Any
            return cast(Callable[[str], Any], fn)
    except Exception:
        logger.debug("[router.after_synth] quick-ingest resolver: ingest_docs.quick_ingest_findings not available", exc_info=True)
        return None
    return None


# CFG / 경로 유틸 (동적 접근)
import core.config as config
from core.state_types import State
from utils.sanitize import as_int
from utils.outline import get_topic_outline_text
from utils.tasks import has_pending, schedule_writer_if_needed
from core.paths import research_resources_dir  # 중앙 경로 유틸 사용
from utils.rag_utils import set_direct_qa_flag, is_qa_like, clear_qa


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

def _merge_docs_unique(a: list[Any], b: list[Any]) -> list[Any]:
    """
    refs/references docs를 합치되, '대충' 중복 제거.
    - doc 객체/딕트 모두 들어올 수 있어 안전하게 str() 기준도 사용
    """
    out: list[Any] = []
    seen: set[str] = set()
    for x in (a or []) + (b or []):
        key = ""
        try:
            if isinstance(x, dict):
                key = str(x.get("id") or x.get("source") or x.get("url") or x.get("title") or "")
            else:
                key = str(getattr(x, "id", "") or getattr(x, "source", "") or getattr(x, "url", "") or getattr(x, "title", "") or "")
        except Exception:
            key = ""
        if not key:
            try:
                key = str(x)
            except Exception:
                key = ""
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(x)
    return out

def _get_refs_merged(state: State) -> Dict[str, Any]:
    """
    state["references"] / state["refs"] 혼용을 흡수.
    - 둘 중 하나만 있으면 그걸 사용
    - 둘 다 있으면 docs를 합쳐서 refs_empty 판단을 안정화
    - 가능하면 state["references"]로 정규화(호환용)
    """
    refs_a = state.get("references")
    refs_b = state.get("refs")
    a = refs_a if isinstance(refs_a, dict) else {}
    b = refs_b if isinstance(refs_b, dict) else {}
    if not a and b:
        # references가 없고 refs만 있으면 references로 미러(혼용 방지)
        try:
            cast(MutableMapping[str, Any], state)["references"] = b
        except Exception:
            pass
        return dict(b)
    if a and not b:
        return dict(a)
    if not a and not b:
        return {}
    # 둘 다 있으면 병합(특히 docs)
    merged = dict(a)
    docs_a = a.get("docs") or []
    docs_b = b.get("docs") or []
    if isinstance(docs_a, list) and isinstance(docs_b, list):
        merged["docs"] = _merge_docs_unique(docs_a, docs_b)
    elif isinstance(docs_a, list):
        merged["docs"] = list(docs_a)
    elif isinstance(docs_b, list):
        merged["docs"] = list(docs_b)
    try:
        cast(MutableMapping[str, Any], state)["references"] = merged
    except Exception:
        pass
    return merged

def _refs_empty(state: State) -> bool:
    refs = _get_refs_merged(state)
    try:
        return not bool((refs.get("docs") or []))
    except Exception:
        return True

def _rag_ready_hint(state: State) -> bool:
    """
    refs가 비어 보여도 실제로는 로컬/베이스 RAG가 준비된 경우가 있어
    공격적 web_search 재진입을 막는 힌트로 사용.
    """
    if bool(state.get("rag_on_disk")):
        return True
    if _safe_int(state.get("doc_count"), 0) > 0:
        return True
    return False

def _preferred_writer() -> str:
    return "section_writer" if _doc_mode() == "report" else "chapter_writer"

def _alt_writer() -> str:
    return "chapter_writer" if _preferred_writer() == "section_writer" else "section_writer"

def _custom_writer_agent() -> Optional[str]:
    try:
        wa = getattr(config.CFG, "WRITER_AGENT", None)
        return wa if isinstance(wa, str) and wa.strip() else None
    except Exception:
        return None

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
    
def _suppress_writer(state: State) -> bool:
    try:
        return bool((state.get("flags") or {}).get("suppress_writer"))
    except Exception:
        return False  

def _has_qa_intent(state: State) -> bool:
    """flags.qa_intent을 안전하게 확인."""
    try:
        return bool((state.get("flags") or {}).get("qa_intent"))
    except Exception:
        return False

def _has_writer_pending_strict(state: State) -> bool:
    """
    STRICT 모드에서의 writer pending 여부 판단.

    - write: prefix 가 붙은 writer 태스크
    - 커스텀 WRITER_AGENT (있다면) 의 write: 태스크
    - prefix 없이 열린 writer 태스크(미완료)

    만 본다. suppress_writer=True면 항상 False.

    ⚠️ 주의:
    - flags.pending_write_title 은 supervisor/after_planner 에서
      "writer 한 번 띄우기 위한 락" 용도로만 사용하고,
      tail 라우터의 무한 재진입을 막기 위해 여기서는 보지 않는다.
    """
    if _suppress_writer(state):
        return False

    tasks = state.get("task_history", []) or []
    preferred = _preferred_writer()
    alt = _alt_writer()

    # 1) 명시적인 write: prefix 태스크가 열려 있으면 → pending
    if has_pending(tasks, preferred, prefix="write:") or has_pending(tasks, alt, prefix="write:"):
        return True

    # 2) 커스텀 writer agent (있다면)도 동일하게 체크
    wa = _custom_writer_agent()
    if wa and has_pending(tasks, wa, prefix="write:"):
        return True

    # 3) prefix 없이 열린 writer 태스크 안전망
    for t in reversed(tasks):
        if isinstance(t, dict):
            agent = t.get("agent", "")
            done = bool(t.get("done", True))
        else:
            agent = getattr(t, "agent", "")
            done = getattr(t, "done", True)

        if (not done) and agent in (preferred, alt, wa or ""):
            return True

    # flags.pending_write_title 은 여기서는 보지 않는다.
    return False


def tail_task_router(state: State) -> str:
    """작성 단계(테일)에서 다음 노드를 선택."""
    # ── STRICT WRITER GUARD: writer가 펜딩이면 최우선 라우팅
    if _has_writer_pending_strict(state):
        preferred_writer = _preferred_writer()
        refs_empty = _refs_empty(state)
        # refs_empty여도 RAG 준비 흔적이 있으면 writer로 진행(무한루프 방지)
        if refs_empty and (not _rag_ready_hint(state)) and not _skip_web_search(state):
            logger.debug("[router.tail] writer pending but refs empty → web_search_agent")
            return "web_search_agent"
        logger.debug("[router.tail] writer pending(strict) → %s", preferred_writer)
        return preferred_writer

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
        if flags.get("pending_write_title") and not _suppress_writer(state):
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
    # Direct QA 의향만 기록(환경/DIRECT_QA, SKIP_WEB_SEARCH, 질의 형태 기반)
    set_direct_qa_flag(cast(MutableMapping[str, Any], state), user_q)
    # 답 생성 전에 올라가 있던 qa_direct_reply를 선제적으로 내린다(루프 충돌 방지).
    _set_flag(state, "qa_direct_reply", False)
    # 의도가 있으면 writer 방해를 막고 곧바로 벡터검색으로
    if _has_qa_intent(state):
        _set_flag(state, "suppress_writer", True)
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
    # refs/references 혼용 흡수(merged refs는 references로 정규화도 수행)
    refs = _get_refs_merged(state)
    refs_light = state.get("refs") or {}

    # Direct QA는 웹검색 경로를 사용하지 않음(이미 답이 준비된 경우)
    if (flags or {}).get("qa_direct_reply") or _has_qa_intent(state):
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

    # ─────────────────────────────────────────────────────────────
    # (A/D) Direct QA 콜드스타트 보강:
    #  - 웹검색 직후 인덱스 증가가 감지되면(added_chunks_* > 0)
    #  - DIRECT_QA=True 이고 last_user_query 가 있을 때
    #  - 동일 질의로 vector_search_agent 1회 강제 재실행
    #  - 재시도 키는 after_web_ws_retries 를 재사용(질문 단위 1회)
    # ─────────────────────────────────────────────────────────────
    try:
        metrics: Dict[str, Any] = dict(cast(dict, state.get("metrics") or {}))
    except Exception:
        metrics = {}

    def _i(v: Any) -> int:
        try:
            return int(v)
        except Exception:
            return 0

    added_chunks_total = (
        _i(metrics.get("added_chunks_web", 0))
        + _i(metrics.get("added_chunks_local", 0))
        + _i(metrics.get("added_chunks_base", 0))
    )
    direct_qa = bool((flags or {}).get("DIRECT_QA"))
    last_q = ""
    try:
        v = (flags or {}).get("last_user_query")
        last_q = v.strip() if isinstance(v, str) else ""
    except Exception:
        last_q = ""

    if direct_qa and last_q and added_chunks_total > 0:
        # 재시도 1회 제한: 내부 헬퍼 사용(typed safely)
        if _retry_under(state, "after_web_ws_retries", max_times=1):
            logger.info(
                "[router.after_web] Direct QA coldstart: index increased (+%d) → vector_search_agent (retry 1/1)",
                added_chunks_total,
            )
            return "vector_search_agent"


    # 0) writer strict guard — 검색 이후에도 writer가 대기면 우선 라우팅
    if _has_writer_pending_strict(state):
        preferred_writer = _preferred_writer()
        refs_empty = not ((state.get("references") or {}).get("docs") or [])
        if refs_empty and not _skip_web_search(state):
            logger.debug("[router.after_web] writer pending but refs empty → web_search_agent")
            return "web_search_agent"
        logger.info("[router.after_web] writer pending(strict) → %s", preferred_writer)
        return preferred_writer

    # 0-b) pending 리스트로 강제 지정된 경우 우선
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
    # 🔒 더 보수적 재시도 가드:
    # 완전히 아무 결과도 없을 때만 web_search 1회 재시도 허용
    truly_empty = (
        (not rag_on_disk)
        and (new_url_count == 0)
        and (not has_docs_in_refs)
        and (not has_urls_in_refs)
    )

    if retries < 1 and truly_empty:
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
    logger.info(
        "[router.after_web] skip retry (not truly empty or retry exhausted) → %s",
        nxt,
    )
    return nxt


def after_vector_router(state: State) -> str:
    """벡터검색 이후 라우팅."""
    tasks = state.get("task_history", []) or []
    flags = state.get("flags") or {}

    # ── (NEW) Direct QA 패스스루: 플래그가 True면 내용 유무와 무관하게 communicator로 전달
    if bool((flags or {}).get("qa_direct_reply", False)):
        logger.info("[router.after_vector] direct_qa=True → communicator (passthrough & clear flags)")
        # Direct QA 응답 경로를 잡았으므로, 같은 턴/다음 턴에서 writer가 살아나도록 플래그 정리
        try:
            # qa_direct_reply / DIRECT_QA 플래그 제거
            clear_qa(cast(MutableMapping[str, Any], state))
            # (선택) 디버깅 편의 표식: flags.router.writer_skipped="direct_qa"
            flags_typed: Dict[str, Any] = dict(cast(Dict[str, Any], state.get("flags") or {}))
            router_flags: Dict[str, Any] = dict(cast(Dict[str, Any], flags_typed.get("router") or {}))
            if "writer_skipped" not in router_flags:
                router_flags["writer_skipped"] = "direct_qa"
            flags_typed["router"] = router_flags
            cast(MutableMapping[str, Any], state)["flags"] = flags_typed
        except Exception:
            # 타입/구조 이상 시에도 조용히 통과
            pass
        return "communicator"

    # 0) 연구 모드 강제 합성 라우팅
    if bool(state.get("research_loop_active")):
        # 연구 모드에서는 Direct QA 상태를 정리해 부작용 방지
        clear_qa(cast(MutableMapping[str, Any], state))
        logger.info("[router.after_vector] research_loop_active=True → research_synthesizer (override qa_direct_reply)")
        return "research_synthesizer"

    #   ↑ 위에서 Direct QA는 무조건 communicator로 보냈으므로, 이하 분기는 Direct QA 비활성 시에만 실행

    # 1) (옵션) 집필 예약 — 연구 중 허용 플래그로 제어
    if callable(schedule_writer_if_needed):
        try:
            # 정본 schedule_writer_if_needed(state, *, reason) 시그니처에 맞게 호출
            schedule_writer_if_needed(
                cast(MutableMapping[str, Any], state),
                reason="after_vector_router",
            )
        except Exception as e:
            logger.debug(
                "[router.after_vector] schedule_writer_if_needed skipped: %s",
                e,
            )

    # refs 가드: refs 비어있으면 write: 펜딩이어도 우선 RAG(Web)
    preferred_writer = _preferred_writer()
    alt_writer = _alt_writer()
    # STRICT: suppress_writer가 꺼져 있고, 커스텀 writer/제목락까지 포함
    has_write_pending = False
    if not _suppress_writer(state):
        wa = _custom_writer_agent()
        has_write_pending = (
            has_pending(tasks, preferred_writer, prefix="write:")
            or has_pending(tasks, alt_writer, prefix="write:")
            or (wa is not None and has_pending(tasks, wa, prefix="write:"))
            or bool((state.get("flags") or {}).get("pending_write_title"))
        )
    if has_write_pending:
        refs_empty = _refs_empty(state)
        # ✅ 공격적 재진입 완화:
        # refs_empty여도 로컬/베이스 RAG 준비 흔적이 있으면 writer로 진행
        if refs_empty and (not _rag_ready_hint(state)) and (not _skip_web_search(state)):
            logger.info("[router.after_vector] write: pending but refs empty & no rag hint → web_search_agent")
            return "web_search_agent"
        logger.info("[router.after_vector] writer pending(write:) → %s", preferred_writer)
        return preferred_writer

    # 2) (Direct QA는 상단에서 이미 처리됨)

    # 3) refs 비면 웹검색 1회 재시도(공통 가드) — refs/references 혼용 모두 대응
    refs_empty = _refs_empty(state)
    if refs_empty:
        # ✅ RAG 준비 흔적이 있으면(로컬 인덱스 존재 등) web_search로 도망가지 말고 tail로 위임
        if _rag_ready_hint(state):
            nxt = tail_task_router(state)
            logger.info("[router.after_vector] refs empty but rag hint exists → %s", nxt)
            return nxt
        # after_vector 단계의 재시도 카운터를 분리 관리 (가독성/추적성 향상)
        if _retry_under(state, "after_vector_ws_retries", max_times=1):
            # ❗ 실제로 web_search_agent 태스크를 추가하여 pending 누락 방지
            _tasks = list(state.get("task_history") or [])
            _has_ws_pending = False
            for t in _tasks:
                agent = getattr(t, "agent", None) if hasattr(t, "agent") else (t.get("agent") if isinstance(t, dict) else None)
                done = getattr(t, "done", True) if hasattr(t, "done") else (bool(t.get("done", True)) if isinstance(t, dict) else True)
                if (agent == "web_search_agent") and (not done):
                    _has_ws_pending = True
                    break
            if not _has_ws_pending:
                from core.models import Task
                _tasks.append(Task(agent="web_search_agent", done=False,
                                   description="router.after_vector: refs empty → rag_update:auto",
                                   done_at=""))
                cast(MutableMapping[str, Any], state)["task_history"] = _tasks
            logger.info("[router.after_vector] refs empty → web_search_agent (retry 1/1, key=after_vector_ws_retries)")
            return "web_search_agent"
        # retry 소진 시: 무조건 synthesizer로 던지지 말고 tail로 위임(불필요 루프 감소)
        nxt = tail_task_router(state)
        logger.info("[router.after_vector] refs empty (retry exhausted) → %s", nxt)
        return nxt

    # 4) 연구 루프 조건 충족 시 → synthesizer
    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)
    has_objs = bool(state.get("research_objectives"))

    if (role == "research analyst") and has_objs and (rounds_done < max_iter):
        logger.info("[router.after_vector] research loop continues → research_synthesizer")
        return "research_synthesizer"

    # 5) 그 외 → tail router
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
        if _suppress_writer(state):
            return None
        preferred = _preferred_writer()
        alt = _alt_writer()
        wa = _custom_writer_agent()
        # write: prefix 우선
        if has_pending(tasks, preferred, prefix="write:"):
            return preferred
        if has_pending(tasks, alt, prefix="write:"):
            return alt
        if wa and has_pending(tasks, wa, prefix="write:"):
            return wa
        # prefix 없이 열린 태스크도 포착
        for t in reversed(tasks):
            agent = getattr(t, "agent", "")
            if (not getattr(t, "done", False)) and agent in (preferred, alt, wa or ""):
                return agent
        # 제목 대기 락
        if bool((state.get("flags") or {}).get("pending_write_title")):
            return preferred
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

    if callable(schedule_writer_if_needed):
        try:
            # 정본 schedule_writer_if_needed(state, *, reason) 시그니처에 맞게 호출
            schedule_writer_if_needed(
                cast(MutableMapping[str, Any], state),
                reason="after_synthesizer_router",
            )
        except Exception as e:
            logger.debug(
                "[router.after_synth] schedule_writer_if_needed skipped: %s",
                e,
            )

    # write: 펜딩이 있으면 writer 우선 (STRICT + suppress 고려)
    preferred_writer = _preferred_writer()
    alt_writer = _alt_writer()
    if not _suppress_writer(state):
        wa = _custom_writer_agent()
        if (
            has_pending(tasks, preferred_writer, prefix="write:")
            or has_pending(tasks, alt_writer, prefix="write:")
            or (wa is not None and has_pending(tasks, wa, prefix="write:"))
            or bool((state.get("flags") or {}).get("pending_write_title"))
        ):
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
        # findings quick-ingest (순환 의존 방지를 위해 헬퍼 사용)
        ingest_fn = _get_findings_ingest_func()
        topic_slug = (state.get("topic_slug") or getattr(config.CFG, "TOPIC_SLUG", "") or "default").strip()
        added = ingest_fn(topic_slug) if callable(ingest_fn) else 0
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