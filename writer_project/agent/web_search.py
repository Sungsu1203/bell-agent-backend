from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from typing import Iterable, Set, MutableMapping, Mapping, Sequence, Any, TYPE_CHECKING, cast, TypeVar, Callable, Optional, Dict
from pathlib import Path
from urllib.parse import urlparse, unquote
import os, re, time, json, glob, shutil, hashlib
import concurrent.futures as cf

from core.state_types import State, References
from core.events import emit_event
if TYPE_CHECKING:
    # 타입 전용(순환 의존 방지)
    from core.state_types import Flags
from core.paths import current_path, now_str as _now_str, research_resources_dir
from core.models import Task
from utils.sanitize import sanitize_state
from utils.tasks import schedule_writer_if_needed
from utils.rag_utils import merge_refs, vector_count
from prompts import get_web_search_prompt
from utils.tasks import has_pending, iter_tool_calls, HumanMessage, AIMessage
from utils.outline import get_topic_outline_text
import core.config as config
from utils.forced_queries import extract_forced_queries_from_messages
from settings_gatekeep import gatekeep_enabled, get_allowed_domains
from settings_gatekeep import url_allowed as _allowed
from tools.web_rag.search import web_search
from tools.web_rag.vertex_search import vertex_web_search

# ── Gatekeep 캐시 동기화(모듈 로드시 1회) ─────────────────────────────────
_refresh_gk_cache: Optional[Callable[[], None]]
try:
    from settings_gatekeep import refresh_gatekeep_cache as _refresh_gk_cache
    # 환경변수 변경/런타임 재시작 없이도 최신 허용 목록을 로드
    if _refresh_gk_cache is not None:
        _refresh_gk_cache()
except Exception:
    # 동기화 실패는 검색 플로우에 영향 주지 않도록 묵살
    _refresh_gk_cache = None

from tools.web_rag.ingest import (
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    _default_chroma_dir,
)
from utils.query_filters import clean_seed as _clean_seed
from tools.local_rag import ingest_local_files
from core.llm import get_llm

# ─────────────────────────────────────────────────────────────────────────────
# CFG 동적 접근 유틸(스냅샷 방지, reload_config 반영)
# ─────────────────────────────────────────────────────────────────────────────
def _get_cfg_attr(name: str, default: Any) -> Any:
    """
    config.CFG.<name> → config.<name> → default
    (reload_config() 이후에도 최신값 반영)
    """
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default


# ─────────────────────────────────────────────────────────────
# NS 정규화/디렉토리 해상 (vector_search.py와 동일 규칙)
# ─────────────────────────────────────────────────────────────
def _wr_sanitize_ns(ns: str) -> str:
    s = (ns or "").strip().lower()
    # 공백/슬래시/역슬래시 → 하이픈, 연속 하이픈 축약, 앞뒤 하이픈 제거
    s = re.sub(r"[\\/\s]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "default"

def _wr_resolve_persist_dir(ns: str, default_dir: str) -> str:
    """
    - 기본은 _default_chroma_dir(ns)
    - 외부에서 전달된 default_dir이 있으면 우선 사용 (leaf/base 경로 모두 허용)
    """
    try:
        d = (default_dir or "").strip()
        return d if d else _default_chroma_dir(ns)
    except Exception:
        return _default_chroma_dir(ns)

def _cfg_bool(name: str, default: bool = False) -> bool:
    v = _get_cfg_attr(name, default)
    if isinstance(v, bool):
        return v
    try:
        s = str(v).strip().lower()
        return s in {"1","true","yes","on","y"}
    except Exception:
        return default

def _cfg_int(name: str, default: int = 0) -> int:
    v = _get_cfg_attr(name, default)
    if isinstance(v, int):
        return v
    try:
        return int(float(str(v)))
    except Exception:
        return default

# ─────────────────────────────────────────────────────────────
# P2 품질 유틸/상수: 연식 필터, 권위/잡음 가중 정렬
#  - YEAR_FLOOR: URL에서 추출된 연도가 이 값 미만이면 제외(미추출은 통과)
#  - AUTH_WEIGHTS/NOISE_WEIGHTS: 도메인별 가중치
#  - WEB_DEDUP_REMAIN_MIN: 디듀프 후 JSON에 최소 남길 항목 수(캡과 별개)
# ─────────────────────────────────────────────────────────────
# 하한 연도(기본 2019) — CFG 또는 ENV에서 오버라이드 가능
YEAR_FLOOR: int = _cfg_int("WEB_URL_YEAR_FLOOR", 2019)

# 권위/잡음 도메인 가중치(필요 시 CFG/ENV에서 확장)
AUTH_WEIGHTS: dict[str, int] = {
    # 토픽 중립 권위 도메인만 유지
    "kosis.kr": 2,      # 통계청 (모든 토픽 공통)
    "korea.kr": 1,
    "stat.go.kr": 1,
}

NOISE_WEIGHTS: dict[str, int] = {
    "medium.com": -1,
    "issuu.com": -2,
    "slideshare.net": -1,
    "smroadmap.smtech.go.kr": -10,  # 대용량 PDF 노이즈
    "globalresearchdata.kr": -3,    # 유료 리서치 장벽
}

# 디듀프 후 최소 잔여 수(기본 4) — P1-4
WEB_DEDUP_REMAIN_MIN: int = _cfg_int("WEB_DEDUP_REMAIN_MIN", 4)

def _extract_year_from_url(u: str) -> Optional[int]:
    """URL 경로/쿼리에서 20xx 연도를 경량 추출(본문 파싱 없이)."""
    try:
        m = re.search(r"(?:^|[^0-9])(20\d{2})(?:[^0-9]|$)", u)
        if m:
            y = int(m.group(1))
            if 2000 <= y <= 2100:
                return y
    except Exception:
        pass
    return None

def _host_of(u: str) -> str:
    try:
        p = urlparse(u)
        h = p.netloc.lower()
        if h.startswith("www."):
            h = h[4:]
        if h.startswith("m."):
            h = h[2:]
        return h
    except Exception:
        return ""

def _item_rank(it: dict, idx: int) -> tuple[int, int, int]:
    """정렬 키(내림차순 유리): (weight, year, -idx). idx는 enumerate에서 전달."""
    u = (it.get("url") or it.get("source") or "").strip()
    host = _host_of(u)
    w = int(AUTH_WEIGHTS.get(host, 0)) + int(NOISE_WEIGHTS.get(host, 0))
    y = _extract_year_from_url(u) or 0
    return (w, y, -idx)

def web_search_agent(state: State):
    # QA 모드면 웹검색 자체를 스킵 (Direct QA 단락)
    try:
        if bool((state.get("flags") or {}).get("qa_direct_reply")):
            logger.info("[web_search] skipped (qa_direct_reply)")
            return state
    except Exception:
        # flags 구조가 비정상이어도 웹검색은 진행 가능하도록 무시
        pass

    logger.info("============ WEB SEARCH AGENT ============")
    emit_event("웹 검색")

    # (선택 보강) 런타임 ENV가 바뀌었을 수 있으므로 호출 시점에 재동기화
    try:
        if os.getenv("GATEKEEP_AUTO_REFRESH", "1").strip() not in ("0", "false", "off"):
            if _refresh_gk_cache is not None:
                _refresh_gk_cache()
    except Exception:
        pass

    llm = get_llm()
    # 상태를 가변 매핑으로 정규화 (object 인덱싱/속성 오류 방지)
    state = cast(State, sanitize_state(state))
    # 이후 인덱싱/쓰기 연산은 _s(가변 매핑)만 사용
    _s = cast(MutableMapping[str, Any], state)

    # ── helpers: ensure dict fields on a TypedDict ──────────────────────────
    from typing import MutableMapping as _MM
    def _ensure_flags_dict(st: _MM[str, Any]) -> _MM[str, Any]:
        """State.flags를 dict로 보장. 비정상 타입(bool/None 등)은 dict로 정규화."""
        v = st.get("flags")
        if not isinstance(v, dict):
            v = {} if v in (None, False) else {"enabled": bool(v)}
        st["flags"] = v
        return cast(_MM[str, Any], v)

    def _ensure_subdict(parent: _MM[str, Any], key: str) -> _MM[str, Any]:
        """parent[key]가 dict가 아니면 빈 dict로 교체 후 반환."""
        cur = parent.get(key)
        if not isinstance(cur, dict):
            cur = {}
            parent[key] = cur
        return cast(_MM[str, Any], cur)

    # === NS + Persist Dir (Calculated once) — vector_search.py와 일치 ===
    topic_slug_raw = (state.get("topic_slug") or getattr(config.CFG, "TOPIC_SLUG", "") or "default").strip()
    env_ns_raw     = (getattr(config.CFG, "CHROMA_NAMESPACE", "") or "").strip()
    topic_slug     = _wr_sanitize_ns(topic_slug_raw)
    env_ns         = _wr_sanitize_ns(env_ns_raw) if env_ns_raw else ""
    ns             = env_ns or topic_slug
    persist_dir    = _wr_resolve_persist_dir(ns, _default_chroma_dir(ns))

    # Record in state (TypedDict 안전화): 전체 state를 가변 매핑으로 확장 후 보장
    _s = cast(_MM[str, Any], state)
    flags: _MM[str, Any]  = _ensure_flags_dict(_s)            # flags를 dict로 보장 + 타입 고정
    dbg: _MM[str, Any]    = _ensure_subdict(flags, "debug")   # debug 서브딕셔너리 보장 + 타입 고정
    chroma: _MM[str, Any] = _ensure_subdict(flags, "chroma")  # chroma 서브딕셔너리 보장 + 타입 고정
    chroma["ns"] = ns
    chroma["dir"] = persist_dir

    logger.info("[web_search] ns=%s (CHROMA_NAMESPACE=%r, topic_slug=%r)", ns, env_ns or "-", topic_slug)
    logger.info("[web_search] persist_dir(default_resolve)=%s", persist_dir)

    # --- (1) Get/Ensure Task ------------------------------------------------
    # 하드 예외 → 소프트 가드: 태스크 없으면 즉석 생성하여 진행
    # task_history에는 Task 또는 dict 형태가 혼재할 수 있으므로 Union으로 명시
    tasks: list[Task | Dict[str, Any]] = list(state.get("task_history", []) or [])
    pending: Task | Dict[str, Any] | None = next(
        (t for t in reversed(tasks)
         if (not getattr(t, "done", True)) and getattr(t, "agent", "") == "web_search_agent"),
        None
    )
    if pending is None:
        new_task: Task | Dict[str, Any]
        try:
            new_task = Task(
                agent="web_search_agent",
                done=False,
                description="auto-created: pending missing",
                done_at="",
            )
        except Exception:
            # Task가 dataclass/TypedDict 등 다양한 구현일 수 있어 dict 폴백
            new_task = {
                "agent": "web_search_agent",
                "done": False,
                "description": "auto-created: pending missing",
                "done_at": "",
            }
        tasks.append(new_task)
        state["task_history"] = tasks
        logger.warning("[web_search_agent] pending task was missing → auto-created (soft-guard)")
        pending = new_task  # 이후 로직에서 description 등을 사용하므로 지정

    # --- Task attribute access helpers (support dataclass and dict) ----------
    from typing import Any as _Any
    def _task_get(t: _Any, key: str, default: _Any = None) -> _Any:
        try:
            return getattr(t, key)  # dataclass/obj
        except Exception:
            try:
                return t.get(key, default) if isinstance(t, dict) else default
            except Exception:
                return default

    def _task_set(t: _Any, key: str, value: _Any) -> None:
        try:
            if hasattr(t, key):
                setattr(t, key, value)     # dataclass/obj
                return
        except Exception:
            pass
        if isinstance(t, dict):
            t[key] = value                 # dict

    web_search_system_prompt = get_web_search_prompt()
    messages = state.get("messages", [])

    # ✅ Inherit refs from previous rounds (Ensure References type)
    _refs_in = cast(References | None, state.get("references"))
    references: References = _refs_in or {"queries": [], "docs": []}
    _existing_qs = {
        (q or "").strip().lower()
        for q in cast(Sequence[str], references.get("queries") or [])
        if isinstance(q, str) and q.strip()
    }

    outline_text = get_topic_outline_text(state)
    mission = str(_task_get(pending, "description", "") or "").strip()

    # objectives 추출 (research_synthesizer와 동일 패턴)
    objs = list(state.get("research_objectives") or [])
    if not objs:
        try:
            objs = config.load_research_objectives_from_env()
        except Exception as e:
            logger.debug("[WEB SEARCH AGENT] objectives load skipped: %s", e)
            objs = []
    objectives_text = "\n".join(f"{i+1}. {o}" for i, o in enumerate(objs)) if objs else "(none)"
    if objs:
        logger.info("[WEB SEARCH AGENT] objectives %d개 주입", len(objs))

    inputs = {
        "mission": mission,
        "objectives": objectives_text,    # ← 추가
        "references": references,
        "messages": messages,
        "outline": outline_text,
        "current_time": _now_str(),
        "topic_title": (
            state.get("topic_title")
            or (state.get("flags") or {}).get("topic_title")
            or state.get("topic")
            or state.get("topic_slug")
            or "(untitled)"
        ),
    }

    queries: list[str] = []
    json_paths: list[str] = []
    new_docs_preview: list[Any] = []  # langchain_core.documents.Document

    MAX_INDEXED_PER_ROUND = _cfg_int("MAX_INDEXED_PER_ROUND", 200)
    MAX_SEARCH_QUERIES_PER_ROUND = _cfg_int("MAX_SEARCH_QUERIES_PER_ROUND", 3)
    SKIP_WEB = _cfg_bool("SKIP_WEB_SEARCH", False)
    # P1-4: 디듀프 후 최소 잔여 보장 하한 (CFG → ENV → 기본값 4)
    #  - CFG.WEB_DEDUP_REMAIN_MIN 가 우선, 없으면 ENV WEB_DEDUP_REMAIN_MIN, 기본 4
    WEB_DEDUP_REMAIN_MIN = _cfg_int("WEB_DEDUP_REMAIN_MIN",
                                    int(os.getenv("WEB_DEDUP_REMAIN_MIN", "4") or "4"))
    if SKIP_WEB:
        logger.info("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 -> web search skipped (local RAG only).")

    # 라운드 청크/스플릿 카운터 (docs와 분리)
    chunk_total = 0  # Count of splits(chunks) indexed this round
    # last_ingest_chunks 구조: round 합계 + 단계별(web/local) 세부
    from typing import Dict as _Dict, Any as _Any
    last_ingest: _Dict[str, _Any] = {
        "round": {"splits": 0, "new": 0, "changed": 0},
        "by_phase": {
            "web":   {"splits": 0, "new": 0, "changed": 0},
            "local": {"splits": 0, "new": 0, "changed": 0},
        },
    }

    # [ANCHOR: VECTOR_COUNT_AFTER_INIT]
    try:
        _doc_count0 = vector_count(ns, persist_dir)
        logger.debug("[DEBUG] after init: doc_count_on_disk=%s (refs.docs not included here)", _doc_count0)
    except Exception as e:
        logger.debug("[DEBUG] after init, doc_count_on_disk check failed: %s", e)

    # --- Helper: enforce next step is vector --------------------------------
    def _ensure_next_is_vector(_st: MutableMapping[str, Any]) -> None:
        _pend = list(cast(Sequence[str] | None, _st.get("pending")) or [])
        if "vector_search_agent" not in _pend:
            _pend.append("vector_search_agent")
            _st["pending"] = _pend
            logger.info("[web_search][guard] scheduled (pending) -> vector_search_agent")
        if not _st.get("next_agent"):
            _st["next_agent"] = "vector_search_agent"


    # --- Helper: inject refs + counters and force vector handoff  -----------
    def _inject_vector_handoff(
        _st: MutableMapping[str, Any],
        *,
        doc_hint_count: int = 0,
        doc_hint_source: str = "local_ingest",
    ) -> None:
        """로컬 인제스트만으로도 다음 단계(벡터)로 확실히 넘어가도록 신호 주입."""
        refs_prev = cast(Mapping[str, Any] | None, _st.get("refs")) or {"queries": [], "docs": []}
        # 'docs'에 최소 힌트(카운터)를 넣어 라우터가 '무언가 인덱스됨'을 감지하도록 함
        refs_out = {
            "queries": list(refs_prev.get("queries") or []),
            "docs": list(refs_prev.get("docs") or []) + ([{"source": doc_hint_source, "count": int(doc_hint_count)}] if doc_hint_count else []),
        }
        _st["refs"] = refs_out
        # 일부 경로 하위호환
        _st["references"] = cast(References, merge_refs(cast(Mapping[str, Any], _st.get("references") or {"queries": [], "docs": []}),
                                                       cast(Sequence[str], refs_out.get("queries") or []),
                                                       cast(Sequence[Any], refs_out.get("docs") or [])))
        # 카운터(존재 시 유지, 없으면 업데이트)
        try:
            cur = int(_st.get("new_url_count") or 0)
        except Exception:
            cur = 0
        _st["new_url_count"] = max(cur, int(doc_hint_count or 0))
        _st["new_url_count_round"] = max(int(_st.get("new_url_count_round") or 0), int(doc_hint_count or 0))
        _st["round_new_urls"] = max(int(_st.get("round_new_urls") or 0), int(doc_hint_count or 0))
        # 다음 단계 지정
        _ensure_next_is_vector(_st)

    # --- Helper: normalize domains ------------------------------------------
    def _normalize_domains(domains: Iterable[str] | None) -> Set[str]:
        if not domains:
            return set()
        out: Set[str] = set()
        for d in domains:
            if isinstance(d, str) and d.strip():
                out.add(d.strip().lower())
        return out

    # Gatekeep resolve
    GATE_KEEP_SOURCES: bool = _cfg_bool("GATE_KEEP_SOURCES", False)
    _cfg_allowed = _get_cfg_attr("ALLOWED_DOMAINS", set())
    if isinstance(_cfg_allowed, str):
        _cfg_allowed = [t for t in _cfg_allowed.split(",") if t.strip()]
    ALLOWED_DOMAINS: Set[str] = _normalize_domains(_cfg_allowed)
    try:
        gk_enabled = bool(gatekeep_enabled())
        if gk_enabled != GATE_KEEP_SOURCES:
            GATE_KEEP_SOURCES = gk_enabled
        parsed = _normalize_domains(get_allowed_domains())
        if parsed:
            ALLOWED_DOMAINS = parsed
    except Exception:
        pass

    # 안전 폴백: 게이트키프가 켜졌지만 허용 도메인이 비어 있으면
    # - 한 번 더 캐시 갱신을 시도하고, 여전히 비면 게이트키프를 비활성화
    if GATE_KEEP_SOURCES and not ALLOWED_DOMAINS:
        try:
            if _refresh_gk_cache is not None:
                _refresh_gk_cache()
            parsed2 = _normalize_domains(get_allowed_domains())
            if parsed2:
                ALLOWED_DOMAINS = parsed2
        except Exception:
            pass
        if not ALLOWED_DOMAINS:
            logger.warning("[GATEKEEP] enabled but allowed list is empty → temporarily disabling gatekeep this round")
            GATE_KEEP_SOURCES = False

    try:
        if GATE_KEEP_SOURCES:
            domain_list = sorted(list(ALLOWED_DOMAINS))
            logger.info("[GATEKEEP] enabled; allowed=%s (n=%d)", ", ".join(domain_list), len(domain_list))
        else:
            logger.info("[GATEKEEP] Disabled. (GATE_KEEP_SOURCES=0)")
    except Exception as e:
        logger.warning("[GATEKEEP] Status logging failed: %s", e)

    # --- JSON loader ---------------------------------------------------------
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

    # === Watchdog (MOVE/READ) ===============================================
    # ENV → 안전 파싱
    def _env_int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, "").strip() or default)
        except Exception:
            return default
    MOVE_TIMEOUT = _env_int("MOVE_TIMEOUT_SEC", 15)
    READ_TIMEOUT = _env_int("READ_TIMEOUT_SEC", 15)

    # 제네릭 반환 타입을 갖는 watchdog 래퍼 (타입 안전)
    T = TypeVar("T")
    def _with_watchdog(fn: Callable[[], T], *, timeout_sec: int, what: str) -> T:
        started = time.time()
        with cf.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn)
            try:
                return fut.result(timeout=timeout_sec)
            except cf.TimeoutError:
                logger.error("[TIMEOUT] %s > %ss (elapsed=%.2fs)", what, timeout_sec, time.time() - started)
                raise

    def _move_with_fallback(src: str, dst: str) -> str:
        def _do_move():
            if os.path.abspath(src) != os.path.abspath(dst):
                try:
                    shutil.move(src, dst)
                except Exception:
                    shutil.copyfile(src, dst)
                    try:
                        os.remove(src)
                    except Exception:
                        pass
            return dst
        return _with_watchdog(_do_move, timeout_sec=MOVE_TIMEOUT, what=f"move_json({os.path.basename(src)})")

    def _load_items_with_watchdog(path: str) -> list[dict]:
        def _reader() -> list[dict]:
            return _load_items(path)
        return _with_watchdog(_reader, timeout_sec=READ_TIMEOUT, what=f"read_json({os.path.basename(path)})")

    # --- Gatekeep filter (빈 결과는 빈 JSON 파일 반환) -------------------------
    def _filter_json_by_domain(json_path: str) -> str:
        if not GATE_KEEP_SOURCES:
            return json_path
        try:
            items = _load_items_with_watchdog(json_path)
        except Exception:
            return json_path
        if not isinstance(items, list):
            return json_path
        filtered = []
        blocked = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            url = (it.get("url") or it.get("source") or "")
            if _allowed(url):
                filtered.append(it)
            else:
                blocked += 1
        p = Path(json_path)
        out = p.with_name(p.stem + "_filtered" + p.suffix)
        if not filtered:
            out.write_text("[]", encoding="utf-8")
            # 차단 수를 명시적으로 남겨 오탐·오경보를 진단하기 쉽게 함
            logger.info("[GATEKEEP] filtered: kept=0 blocked=%d file=%s", blocked, p.name)
            return str(out)
        out.write_text(json.dumps(filtered, ensure_ascii=False), encoding="utf-8")
        if blocked:
            logger.info("[GATEKEEP] filtered: kept=%d blocked=%d file=%s",
                        len(filtered), blocked, p.name)
        return str(out)

    # --- URL tally / cap -----------------------------------------------------
    topic_key = (topic_slug or "default")
    _seen_by_topic = _ensure_subdict(flags, "seen_sources_by_topic")
    _seen_sources = set(_seen_by_topic.get(topic_key) or [])
    _round_added_urls = 0
    _round_cap: int = int(MAX_INDEXED_PER_ROUND or 0)  # 0 means unlimited

    def _cap_reached() -> bool:
        return bool(_round_cap > 0 and _round_added_urls >= _round_cap)

    def _norm_url(u: str) -> str:
        u = (u or "").strip()
        if not u:
            return ""
        # Local/file paths
        if u.startswith("file://") or re.match(r"^[a-zA-Z]:[\\/]", u) or u.startswith(os.sep):
            path = u.replace("\\", "/").lower()
            path = re.sub(r"__v_\d+_\d+$", "", path)
            return path
        # HTTP(S)
        if "://" not in u:
            u = "http://" + u
        p = urlparse(u)
        host = p.netloc.lower()
        # m. -> www. 정규화
        if host.startswith("m."):
            host = "www." + host[2:]
        if host.startswith("www."):
            host = host[4:]
        normalized_path = re.sub(r"__v_\d+_\d+$", "", p.path)
        # http → https 승격 (정보 중복 방지용 보수적 규칙)
        scheme = "https"
        return f"{host}{normalized_path}"

    def _tally_new_urls_from_items(items: list[dict]) -> None:
        nonlocal _round_added_urls
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            url = (it.get("url") or it.get("source") or "").strip()
            k = _norm_url(url)
            if k and k not in _seen_sources:
                _seen_sources.add(k)
                _round_added_urls += 1

    def _tally_new_urls_from_json(json_path: str) -> None:
        try:
            items = _load_items_with_watchdog(json_path)
            if isinstance(items, list):
                _tally_new_urls_from_items(items)
        except Exception as e:
            logger.warning("[WARN] url tally failed for %s: %s", json_path, e)

    logger.debug("[DEBUG] seen_sources_by_topic[%s] = %s", topic_key, len(_seen_by_topic.get(topic_key, [])))

    # --- Content quality quick filter ---------------------------------------
    def _is_bad_doc(d) -> bool:
        txt = ((getattr(d, "page_content", None) or "")[:2000]).lower()
        # 기술적 오류 필터
        if any(k in txt for k in [
            "access denied", "enable javascript", "just a moment",
            "security controls triggered", "captcha"
        ]):
            return True
        # 관련성 없는 도메인 필터
        bad_domains_str = (os.environ.get("FILTER_BAD_DOMAINS", "") or "").strip()
        if bad_domains_str:
            meta = getattr(d, "metadata", {}) or {}
            url = (meta.get("source") or meta.get("url") or "").lower()
            bad_domains = [bd.strip() for bd in bad_domains_str.split(",") if bd.strip()]
            if any(bd in url for bd in bad_domains):
                return True
        return False

    # --- Normalize query -----------------------------------------------------
    def _normalize_query(q: str) -> str:
        s = (q or "").strip()
        if not s:
            return ""
        s = s.replace('\\"', '"').replace("\\'", "'")
        s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")

        def _site_or_repl(m):
            tail = m.group(1)
            parts = [p.strip() for p in re.split(r"[|]", tail) if p.strip()]
            if len(parts) <= 1:
                p0 = parts[0] if parts else tail
                return p0 if p0.lower().startswith("site:") else ("site:" + p0)
            norm_parts = [(p if p.lower().startswith("site:") else ("site:" + p)) for p in parts]
            return f"({' OR '.join(norm_parts)})"

        s = re.sub(r"site:([^\s)]+)", _site_or_repl, s)
        s = re.sub(r"\s{2,}", " ", s).strip()
        return s

    # --- Vertex 전용 쿼리 튜닝 ---------------------------------------------
    def _to_vertex_query(q: str) -> str:
        """
        Vertex + Google Search grounding에 맞게
        - 괄호 밖의 AND/OR는 자연어식으로 완화
        - -토큰(제외 검색)이 너무 많으면 일부만 유지
        정도만 가볍게 손보는 래퍼입니다.

        입력은 이미 _normalize_query 를 거친 문자열(norm_q)라고 가정합니다.
        """
        s = (q or "").strip()
        if not s:
            return ""

        # 1) 괄호 밖에서만 AND / OR 를 공백으로 치환
        buf: list[str] = []
        in_paren = 0
        i = 0
        n = len(s)

        while i < n:
            ch = s[i]
            if ch == "(":
                in_paren += 1
                buf.append(ch)
                i += 1
                continue
            if ch == ")":
                in_paren = max(0, in_paren - 1)
                buf.append(ch)
                i += 1
                continue

            # 괄호 밖의 “ AND ” / “ OR ” → 공백 하나로 완화
            if in_paren == 0 and s.startswith(" AND ", i):
                buf.append(" ")
                i += 5
                continue
            if in_paren == 0 and s.startswith(" OR ", i):
                buf.append(" ")
                i += 4
                continue

            buf.append(ch)
            i += 1

        s = "".join(buf).strip()

        # 2) -토큰이 너무 많으면 앞에서 몇 개만 유지 (예: 3개)
        tokens = s.split()
        minus_tokens = [t for t in tokens if t.startswith("-")]
        MAX_MINUS = 3

        if len(minus_tokens) > MAX_MINUS:
            # 앞에서 MAX_MINUS개만 살리고 나머지 -토큰은 버림
            keep = minus_tokens[:MAX_MINUS]
            new_tokens: list[str] = []
            for t in tokens:
                if t.startswith("-"):
                    if t in keep:
                        new_tokens.append(t)
                        keep.remove(t)
                    # 여기서 버려진 -토큰은 그냥 무시
                else:
                    new_tokens.append(t)
            tokens = new_tokens

        # 3) 필요하면 전체 토큰 수도 살짝 제한 (예: 40개)
        MAX_TOKENS = 40
        if len(tokens) > MAX_TOKENS:
            tokens = tokens[:MAX_TOKENS]

        return " ".join(tokens).strip()

    # --- Watchdog (already defined above) -----------------------------------
    # def _with_watchdog(...): ...

    # --- Core search/ingest routine -----------------------------------------
    def _run_web_search_with_guard(q: str, preview_limit: int = 5, retries: int = 2) -> bool:
        nonlocal chunk_total
        if SKIP_WEB:
            logger.info("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 -> web search skipped.")
            return False

        q = (q or "").strip()
        if not q:
            return False

        norm_q = _normalize_query(q)
        if norm_q != (q or ""):
            logger.debug("[web_search][normalized] %s  <-  %s", norm_q, q)
        if not norm_q:
            logger.info("[web_search] empty-after-normalize -> skip")
            return False

        ok = False
        for attempt in range(retries + 1):
            try:
                # 1) Search call (Vertex + legacy 멀티엔진 병합)
                payload = {"query": norm_q}
                t0 = time.monotonic()

                query = (
                    payload.get("query")
                    or payload.get("q")
                    or payload.get("input")
                    or ""
                )

                # Vertex / legacy 결과를 모을 버퍼
                combined_items: list[dict] = []

                # -----------------------------------------
                # 1-1. Vertex 우선 시도 (attempt==0에서 한 번만)
                # -----------------------------------------
                if attempt == 0 and query and not _cfg_bool("SKIP_VERTEX_SEARCH", False):
                    try:
                        vertex_result = vertex_web_search(query)
                        v_chunks = vertex_result.get("chunks") or []
                        v_supports = vertex_result.get("supports") or []
                        v_queries = vertex_result.get("web_search_queries") or []

                        vertex_items_added = 0
                        for support in v_supports:
                            indices = support.get("chunk_indices") or []
                            valid_indices = [i for i in indices if 0 <= i < len(v_chunks)]
                            if not valid_indices:
                                continue
                            rep_idx = valid_indices[0]
                            rep_chunk = v_chunks[rep_idx]
                            rep_url = rep_chunk.get("uri") or ""
                            if not rep_url:
                                continue
                            alt_urls = [
                                v_chunks[i].get("uri") for i in valid_indices[1:]
                                if v_chunks[i].get("uri")
                            ]
                            combined_items.append({
                                "title": "",
                                "url": rep_url,
                                "content": support.get("text") or "",
                                "raw_content": "",
                                "source": rep_url,
                                "metadata": {
                                    "backend": "vertex_grounding",
                                    "alt_urls": alt_urls,
                                    "chunk_domain": rep_chunk.get("domain") or "",
                                },
                            })
                            vertex_items_added += 1

                        if vertex_items_added > 0:
                            logger.info(
                                "[web_search] Vertex success (chunks=%d supports=%d items=%d queries=%s)",
                                len(v_chunks), len(v_supports), vertex_items_added,
                                v_queries[:3] if v_queries else [],
                            )
                        elif v_chunks:
                            logger.warning(
                                "[web_search] Vertex returned chunks=%d but supports=0, skipping",
                                len(v_chunks),
                            )
                    except Exception as e:
                        logger.warning("[web_search] Vertex failed: %s", e)
                elif attempt == 0 and _cfg_bool("SKIP_VERTEX_SEARCH", False):
                    logger.info("[web_search] Vertex skipped (SKIP_VERTEX_SEARCH=1)")

                # -----------------------------------------
                # 1-2. legacy 멀티엔진 검색(Tavily+Naver 등)도 항상 시도
                # -----------------------------------------
                legacy_ret = None
                try:
                    legacy_ret = web_search.invoke(payload)
                    logger.info("[web_search] legacy multi-engine search used")
                except Exception as e:
                    logger.warning("[web_search] legacy search failed: %s", e)

                if legacy_ret is not None:
                    try:
                        if isinstance(legacy_ret, tuple) and len(legacy_ret) >= 2:
                            legacy_items = list(legacy_ret[0] or [])
                        elif isinstance(legacy_ret, list):
                            legacy_items = list(legacy_ret)
                        elif isinstance(legacy_ret, dict):
                            legacy_items = list(
                                legacy_ret.get("results")
                                or legacy_ret.get("items")
                                or []
                            )
                        else:
                            legacy_items = []
                    except Exception as e:
                        logger.debug(
                            "[web_search] legacy return normalize failed: %s", e
                        )
                        legacy_items = []

                    if legacy_items:
                        # dict 타입만 수용 (이후 파이프라인과 호환)
                        combined_items.extend(
                            it for it in legacy_items if isinstance(it, dict)
                        )

                # 최종 ret: list[dict] 형태로 넘기면, 아래 Normalize 블록이 그대로 처리
                ret = combined_items

                dt = time.monotonic() - t0
                logger.info("[web_search][call ok] dt=%.2fs query=%s", dt, norm_q)

                # Normalize return
                items: list[dict] = []
                json_path: str = ""
                try:
                    if isinstance(ret, tuple) and len(ret) >= 2:
                        items = list(ret[0] or [])
                        json_path = str(ret[1] or "")
                    elif isinstance(ret, list):
                        items = list(ret)
                        json_path = ""
                    elif isinstance(ret, dict):
                        items = list(ret.get("results") or ret.get("items") or [])
                        json_path = str(ret.get("json_path") or ret.get("path") or "")
                    else:
                        json_path = str(ret or "")
                except Exception as e:
                    logger.debug("[web_search] return normalize failed: %s", e)

                # 1-2) Path fallback: Save if path is missing
                if not json_path:
                    try:
                        res_dir = research_resources_dir(topic_slug or "default")
                        res_dir.mkdir(parents=True, exist_ok=True)
                        sig_src = (norm_q + "|" + "|".join([(it or {}).get("url") or (it or {}).get("source") or "" for it in (items or [])]))
                        sig = hashlib.sha1(sig_src.encode("utf-8")).hexdigest()[:8]
                        fname = f"web_{int(time.time())}_{sig}.json"
                        forced_path = res_dir / fname
                        with open(forced_path, "w", encoding="utf-8") as f:
                            json.dump(items or [], f, ensure_ascii=False)
                        json_path = str(forced_path)
                        logger.info("[web_search][fallback save] path=%s items=%d", json_path, len(items or []))
                    except Exception as se:
                        logger.warning("[web_search][fallback save] failed: %s", se)
                        try:
                            res_dir = research_resources_dir(topic_slug or "default")
                            res_dir.mkdir(parents=True, exist_ok=True)
                            forced_path = res_dir / f"web_{int(time.time())}_empty.json"
                            forced_path.write_text("[]", encoding="utf-8")
                            json_path = str(forced_path)
                        except Exception:
                            pass

                json_paths.append(json_path)

                # 2) Move result JSON (with cross-volume fallback) — with watchdog
                try:
                    res_dir = research_resources_dir(topic_slug or "default")
                    res_dir.mkdir(parents=True, exist_ok=True)
                    new_json_path = str(res_dir / os.path.basename(json_path))
                    if os.path.abspath(json_path) != os.path.abspath(new_json_path):
                        json_path = _move_with_fallback(json_path, new_json_path)
                        json_paths[-1] = json_path
                    logger.info("[web_search] saved -> %s", json_path)
                except Exception as move_e:
                    logger.warning("[WARN] resources JSON move failed: %s", move_e)

                # 2-1) (P2) 연식 필터 + 권위가중 정렬 + Dedup + cap (with watchdog read)
                try:
                    _items_all = _load_items_with_watchdog(json_path)
                    # (a) 연식 하한(2019) 필터 — URL 상 연도만 근거, 미검출은 통과
                    _items_all = [
                        it for it in _items_all if not isinstance(it, dict)
                        or (_extract_year_from_url((it.get("url") or it.get("source") or "")) or YEAR_FLOOR) >= YEAR_FLOOR
                    ]
                    # (b) 권위/잡음 가중치 + 연식 기반 정렬(내림차순)
                    # dict 항목만 유지하고, 정렬은 (idx, dict) 쌍으로 계산한 뒤 dict 리스트로 복원
                    _items_dicts: list[dict] = [it for it in _items_all if isinstance(it, dict)]
                    # enumerate 결과는 (int, dict) 튜플 → 별도 변수에 담아 타입 혼동 방지
                    ranked_pairs: list[tuple[int, dict]] = sorted(
                        [(i, it) for i, it in enumerate(_items_dicts)],
                        key=lambda pair: _item_rank(pair[1], idx=pair[0]),
                        reverse=True,
                    )
                    # 최종적으로 list[dict] 형태 보장
                    _items_all = [it for _, it in ranked_pairs]

                    # (c) 도메인 정규화 기반 디듀프
                    _seen_norm_urls = set()
                    _deduped: list[dict] = []
                    for it in _items_all:
                        if not isinstance(it, dict):
                            continue
                        u = (it.get("url") or it.get("source") or "").strip()
                        k = _norm_url(u)
                        if not k or k in _seen_norm_urls:
                            continue
                        _seen_norm_urls.add(k)
                        _deduped.append(it)
                    # 남은 인덱싱 예산(캡) 계산
                    remaining = max(0, (_round_cap - _round_added_urls)) if _round_cap > 0 else len(_deduped)
                    # P1-4: 최소 잔여 보장 — 디듀프 후 JSON에는 최소 WEB_DEDUP_REMAIN_MIN 개를 남김
                    #  - 실제 인덱싱 예산은 상위 로직(_round_cap/_round_added_urls)으로 여전히 제한됨
                    #  - 여기서는 JSON 저장 단계에서 너무 일찍 비워지지 않도록 안전 여유를 둠
                    keep_min = max(int(WEB_DEDUP_REMAIN_MIN or 0), 0)
                    # cap이 켜져 있다면, 남길 개수는 cap 잔여와 하한 중 큰 값으로,
                    # 전체 항목 수를 넘지 않도록 제한
                    if _round_cap > 0:
                        keep_n = min(len(_deduped), max(remaining, keep_min))
                    else:
                        # cap이 없으면 원래 목록 유지(하한은 항상 충족)
                        keep_n = len(_deduped)
                    if keep_n < len(_deduped):
                        _deduped = _deduped[:keep_n]
                    Path(json_path).write_text(json.dumps(_deduped, ensure_ascii=False), encoding="utf-8")
                    logger.debug("[web_search] refine+dedup/cap: %d -> %d (remain=%s, floor=%d)",
                                 len(_items_all), len(_deduped), remaining if _round_cap else "∞", YEAR_FLOOR)
                except Exception as e:
                    logger.debug("[web_search] dedup/cap skipped: %s", e)

                # 3) Gatekeep
                filtered_json = _filter_json_by_domain(json_path)
                _tally_new_urls_from_json(filtered_json)

                # 4) Indexing with watchdog (Upsert; clear=False)
                if MAX_INDEXED_PER_ROUND > 0:
                    INDEX_TIMEOUT = int(os.getenv("INDEX_TIMEOUT_SEC", "120") or "120")

                    def _do_index():
                        return add_web_pages_json_to_chroma(
                            json_file=filtered_json,
                            namespace=ns,
                            clear=False,
                            persist_directory=persist_dir
                        )

                    try:
                        _ret = _with_watchdog(_do_index, timeout_sec=INDEX_TIMEOUT, what="indexing")
                        # 반환 호환 처리:
                        # - 신형(dict): {"splits": int, "new": int, "changed": int, ...}
                        # - 구형(tuple): (orig_count, chunk_count)
                        web_splits = web_new = web_changed = 0
                        if isinstance(_ret, dict):
                            web_splits  = int(_ret.get("splits") or _ret.get("chunk_count") or 0)
                            web_new     = int(_ret.get("new") or _ret.get("added") or 0)
                            web_changed = int(_ret.get("changed") or 0)
                        elif isinstance(_ret, tuple) and len(_ret) >= 2:
                            web_splits = int(_ret[1] or 0)
                        else:
                            try:
                                web_splits = int(_ret or 0)
                            except Exception:
                                web_splits = 0

                        # 라운드/단계별 누적
                        chunk_total += web_splits
                        last_ingest["by_phase"]["web"]["splits"]   += web_splits
                        last_ingest["by_phase"]["web"]["new"]      += web_new
                        last_ingest["by_phase"]["web"]["changed"]  += web_changed
                        last_ingest["round"]["splits"]   += web_splits
                        last_ingest["round"]["new"]      += web_new
                        last_ingest["round"]["changed"]  += web_changed
                        try:
                            _tally_new_urls_from_json(filtered_json)
                        except Exception:
                            pass
                    except Exception as idx_e:
                        logger.error("[WEB INDEXING FATAL] add_web_pages_json_to_chroma failed", exc_info=True)
                        raise idx_e
                else:
                    logger.info("[WEB INDEXING SKIP] MAX_INDEXED_PER_ROUND=0. Indexing skipped.")

                # 5) Preview
                try:
                    docs = web_page_json_to_documents(filtered_json)[:preview_limit]
                    if GATE_KEEP_SOURCES:
                        def _src(d) -> str:
                            md = getattr(d, "metadata", {}) or {}
                            return md.get("source") or md.get("url") or ""
                        docs = [d for d in docs if _allowed(_src(d))]
                    docs = [d for d in docs if not _is_bad_doc(d)]
                    for d in docs:
                        md = getattr(d, "metadata", {}) or {}
                        src = md.get("source") or md.get("url") or "unknown"
                        # (P2) 표시용으로만 퍼센트-인코딩 디코드(unquote). 저장/키에는 영향 없음.
                        try:
                            src_disp = unquote(src)
                        except Exception:
                            src_disp = src
                        new_docs_preview.append(
                            type(d)(
                                page_content=(d.page_content or "")[:500],
                                metadata={**md, "source": src_disp}
                            )
                        )
                except Exception as prev_e:
                    logger.warning("[WARN] preview build failed: %s", prev_e)

                queries.append(norm_q)
                ok = True
                break

            except Exception as e:
                logger.debug("[web_search][call fail] attempt=%d err=%s", attempt + 1, e)
                if attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                logger.warning("[WARN] web_search failed (after retry): %s -> %s", norm_q, e)
                ok = False
                break

        return ok

    # --- (4) Query execution pipeline ---------------------------------------
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
        if not isinstance(q, str):
            q = str(q or "")
        nq = re.sub(r"\s+", " ", _normalize_planner_q(q))
        if not nq:
            continue
        lk = nq.lower()
        if lk in seen_norm or lk in _existing_qs:
            continue
        seen_norm.add(lk)
        planner_qs.append(nq)

    # ======== [ANCHOR: RESEARCH_FLAG_SET] ========
    if (state.get("research_plan") or {}).get("objective") or planner_qs:
        state["research_loop_active"] = True
    # =============================================

    auto_mode = "rag_update:auto" in mission.lower()
    if auto_mode:
        state["research_loop_active"] = True

    ran_planner = 0
    if planner_qs:
        if not SKIP_WEB:
            logger.info("[WEB SEARCH AGENT] planner queries: %s", planner_qs)
            for q in planner_qs:
                if _cap_reached():
                    logger.info("[WEB SEARCH AGENT] cap reached; skipping remaining planner queries")
                    break
                if _run_web_search_with_guard(q):
                    _existing_qs.add(q.lower())
                    ran_planner += 1
            logger.info("[WEB SEARCH AGENT] planner queries executed: %s/%s", ran_planner, len(planner_qs))
        else:
            logger.info("[WEB SEARCH AGENT] (skip) planner queries ignored: %s", planner_qs)
        state["planner_queries"] = []
        rp = state.get("research_plan") or {}
        rp["queries"] = []
        state["research_plan"] = rp
        logger.info("[WEB SEARCH AGENT] planner queries executed: %s/%s", ran_planner, len(planner_qs))

    # 4-1) Forced queries
    forced_queries: list[str] = []
    try:
        forced_queries = extract_forced_queries_from_messages(messages, lookback=20) or []
    except Exception as e:
        logger.warning("[WARN] forced query extraction failed: %s", e)

    if forced_queries:
        state["research_loop_active"] = True
        if not SKIP_WEB:
            logger.info("[WEB SEARCH AGENT] forced queries: %s", forced_queries)
            for q in forced_queries:
                if _cap_reached():
                    logger.info("[WEB SEARCH AGENT] cap reached; skipping remaining forced queries")
                    break
                if not isinstance(q, str):
                    q = str(q or "")
                q = (q or "").strip()
                if not q:
                    continue
                lk = q.lower()
                if lk in _existing_qs:
                    logger.debug("[WEB SEARCH AGENT] skip duplicate (forced): %s", q)
                    continue
                logger.debug("-------- web search -------- %s", {"query": q})
                if _run_web_search_with_guard(q):
                    _existing_qs.add(lk)
        else:
            logger.info("[WEB SEARCH AGENT] (skip) forced queries ignored: %s", forced_queries)

    # 4-2) LLM-designed queries
    if not SKIP_WEB:
        llm_with_web = llm.bind_tools([web_search])
        search_plans = (web_search_system_prompt | llm_with_web).invoke(inputs)
        ran = 0
        for args in iter_tool_calls(search_plans, "web_search"):
            if _cap_reached():
                logger.info("[WEB SEARCH AGENT] cap reached; skipping remaining llm-designed queries")
                break
            if ran >= MAX_SEARCH_QUERIES_PER_ROUND:
                break
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"query": args}
            elif isinstance(args, (list, tuple)):
                args = {"query": " ".join(map(str, args))}
            elif not isinstance(args, dict):
                logger.debug("web_search tool args ignored (unsupported type): %r", type(args).__name__)
                continue
            q = (args.get("query") or "").strip()
            if not q:
                continue
            lk = q.lower()
            if lk in _existing_qs:
                continue
            logger.debug("-------- web search -------- %s", {"query": q})
            if _run_web_search_with_guard(q):
                _existing_qs.add(lk)
                ran += 1
    else:
        logger.info("[WEB SEARCH AGENT] (skip) LLM-designed web queries suppressed.")

    # 4-3) Automatic fallback (if auto mode & no queries executed yet)
    def _fallback_auto_queries():
        topic = state.get("topic_title") or ""
        base = [
            f"{topic} 2025 overview",
            f"{topic} market size 2025",
            f"{topic} key trends Korea 2025",
            f"{topic} supply chain risks 2025",
            f"{topic} policy & regulation Korea 2025",
        ]
        extra: list[str] = []
        if outline_text:
            for line in outline_text.splitlines():
                line = _clean_seed(line.strip())
                if not line:
                    continue
                if len(extra) >= 2:
                    break
                extra.append(f"{line[:40]} 2025 overview")
        return base + extra

    if auto_mode and not queries:
        if not SKIP_WEB:
            for q in _fallback_auto_queries():
                if _cap_reached():
                    logger.info("[WEB SEARCH AGENT] cap reached; skipping fallback queries")
                    break
                if not isinstance(q, str):
                    q = str(q or "")
                q = (q or "").strip()
                if not q:
                    continue
                lk = q.lower()
                if lk in _existing_qs:
                    logger.debug("[WEB SEARCH AGENT] skip duplicate (fallback): %s", q)
                    continue
                if _run_web_search_with_guard(q):
                    _existing_qs.add(lk)
        else:
            logger.info("[WEB SEARCH AGENT] (skip) auto-fallback web queries suppressed.")

    # --- (5) Local file indexing (once per topic) ----------------------------
    _raw = str(_get_cfg_attr("LOCAL_RAG_GLOBS", "") or "")
    _tokens = [t.strip() for t in re.split(r"[|;, \n]+", _raw) if t.strip()]

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and isinstance(last_human.content, str):
        m = re.search(r"(?:add_local|local_rag|내부자료|내부문서)\s*:\s*(.+)", last_human.content, flags=re.I)
        if m:
            for tok in re.split(r"[|;, \n]+", m.group(1)):
                if tok.strip():
                    _tokens.append(tok.strip())

    slug_or_wildcard = topic_slug if topic_slug else "**"

    def _normalize_token(p: str) -> str:
        p = p.replace("<topic-slug>", slug_or_wildcard)
        return p.replace("\\", "/").strip()

    tokens_norm = [_normalize_token(t) for t in _tokens]
    logger.info("[DEBUG] Final local RAG globs list: %s", tokens_norm)

    _base_candidates = []
    try:
        _cp = Path(str(current_path)).resolve()
        _base_candidates.extend([_cp, _cp.parent])
    except Exception:
        pass
    _base_candidates.extend([Path.cwd().resolve(), Path(__file__).resolve().parents[1]])

    def _dedup_keep_order(seq):
        seen = set(); out = []
        for s in seq:
            key = s.lower() if os.name == "nt" else s
            if key not in seen:
                seen.add(key); out.append(s)
        return out

    tokens_norm = _dedup_keep_order(tokens_norm)

    def _resolve_to_abs(pattern: str) -> list[str]:
        found_abs = []
        for base in _base_candidates:
            patt_abs = str((base / pattern).as_posix())
            hits = list(glob.iglob(patt_abs, recursive=True))
            if hits:
                found_abs.extend(hits)
        if found_abs:
            return sorted(_dedup_keep_order([str(Path(h).resolve()) for h in found_abs]))
        return [str((_base_candidates[-1] / pattern).resolve())]

    dedup_globs: list[str] = []
    debug_matches_total = 0
    if not tokens_norm:
        logger.info("[LOCAL SCAN] No configured globs. Check LOCAL_RAG_GLOBS or add_local command.")
    else:
        logger.info("[LOCAL SCAN] base candidates = %s", [str(p) for p in _base_candidates])
        for patt in tokens_norm:
            hits = _resolve_to_abs(patt)
            hit_files = [h for h in hits if os.path.isfile(h)]
            logger.info("[LOCAL SCAN] %s  -> %d file(s)", patt, len(hit_files))
            if len(hit_files) == 0:
                logger.info("[LOCAL SCAN]   L Example target: %s", hits[-1] if hits else "(none)")
            debug_matches_total += len(hit_files)
            dedup_globs.append(patt)
        if debug_matches_total == 0:
            logger.info("[LOCAL SCAN] All globs matched 0 files. Check path/pattern.")

    li = _ensure_subdict(flags, "local_ingested")
    skip_local_ingest = bool(li.get(topic_key))
    if skip_local_ingest:
        logger.info("[LOCAL SCAN] already ingested for topic '%s' -> skip ingest", topic_key)

    if dedup_globs and not skip_local_ingest:
        l_jsons, l_docs, l_chunks = ingest_local_files(
            dedup_globs,
            namespace=ns,
            persist_directory=persist_dir,
            topic_slug=topic_slug or "default",
            root_dir=str(current_path),
            add_web_pages_json_to_chroma=add_web_pages_json_to_chroma,
            web_page_json_to_documents=web_page_json_to_documents,
        )
        if l_docs:
            logger.info("[WEB SEARCH AGENT] ingest local refs: %s", dedup_globs)
            json_paths.extend(l_jsons)
            new_docs_preview.extend(l_docs)
            # local ingest는 반환에 splits만 있을 수 있음
            _l_splits = int(l_chunks or 0)
            chunk_total += _l_splits
            last_ingest["by_phase"]["local"]["splits"]  += _l_splits
            last_ingest["round"]["splits"]              += _l_splits
            if int(l_chunks or 0) > 0:
                for jp in (l_jsons or []):
                    _tally_new_urls_from_json(jp)
            for g in dedup_globs:
                q = f"local:{g}"
                lk = q.lower()
                if lk not in _existing_qs:
                    queries.append(q)
                    _existing_qs.add(lk)
            li[topic_key] = True
            state["local_ingested_once"] = True
            # ▼ 로컬 인제스트가 있었으면 바로 벡터 단계 핸드오프 신호 주입
            try:
                _inject_vector_handoff(cast(MutableMapping[str, Any], state),
                                       doc_hint_count=int(l_chunks or len(l_docs) or 0),
                                       doc_hint_source="local_ingest")
            except Exception as _e:
                logger.debug("[local→vector handoff] inject skipped: %s", _e)
        else:
            logger.info("[LOCAL RAG] no docs matched; skip adding local:* queries")

    # [ANCHOR: VECTOR_COUNT_AFTER_LOCAL_INGEST]
    try:
        _doc_count1 = vector_count(ns, persist_dir)
        logger.debug("[DEBUG] after local ingest: doc_count_on_disk=%s", _doc_count1)
    except Exception as e:
        logger.debug("[DEBUG] after local ingest, doc_count_on_disk check failed: %s", e)

    # --- (SKIP_WEB safety + 로컬 인제스트 강제 라우팅) -----------------------
    # 신규 청크가 없더라도(=pre-indexed) 벡터 검색을 반드시 수행하도록 가드
    #  - SKIP_WEB_SEARCH=1 이면 웹쿼리는 생략되므로 로컬 RAG만으로도 다음 스테이지로 진입해야 함
    no_new_docs = (int(chunk_total or 0) <= 0) and (len(new_docs_preview or []) == 0)
    if SKIP_WEB and no_new_docs:
        logger.info("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 & no new docs -> force vector stage (local-only)")
        try:
            _r = _s.get("references") or {"queries": [], "docs": []}
            _s["references"] = cast(References, _r)
        except Exception:
            pass
        _ensure_next_is_vector(_s)
        # 벡터 단계로 넘어가도록 사용자 메시지도 남김(인간 로그 모드에서 보이게)
        try:
            messages.append(AIMessage(content="[WEB SEARCH AGENT] 신규 문서 없음 → 벡터 검색 단계로 진행합니다. (local-only)"))
        except Exception:
            pass

    # --- Local preview allow keywords filter ---------------------------------
    allow_kw_env = str(_get_cfg_attr("LOCAL_RAG_ALLOW", "") or "")
    if allow_kw_env.strip():
        ALLOW_KEYS = {k.strip().lower() for k in allow_kw_env.split(",") if k.strip()}
        def _relevant(d) -> bool:
            txt = (d.page_content or "").lower()
            return any(k in txt for k in ALLOW_KEYS)
        before = len(new_docs_preview)
        new_docs_preview[:] = [d for d in new_docs_preview if _relevant(d)]
        after = len(new_docs_preview)
        if before != after:
            logger.info("[LOCAL RAG] preview filtered by keywords: %s -> %s", before, after)

    # --- (6) State update & next step ---------------------------------------
    _s["references"] = cast(
        References,
        merge_refs(
            cast(Mapping[str, Any] | None, _s.get("references")),
            cast(Sequence[str] | None, queries),
            cast(Sequence[Any] | None, new_docs_preview),
        ),
    )

    # Refs (concise URLs) & rag_on_disk flag
    new_doc_urls: list[str] = []
    try:
        for _d in (new_docs_preview or []):
            _md = getattr(_d, "metadata", {}) or {}
            _u = _md.get("source") or _md.get("url")
            if _u:
                new_doc_urls.append(str(_u))
    except Exception as _e:
        logger.debug("[web_search][refs] url extraction skipped: %s", _e)

    _s = cast(MutableMapping[str, Any], state)
    _s["refs"] = merge_refs(
        cast(Mapping[str, Any] | None, state.get("refs")),
        cast(Sequence[str] | None, queries),
        cast(Sequence[Any] | None, new_doc_urls),
    )
    _s["rag_on_disk"] = True

    # refs는 Dict로 다운캐스팅 후 안전하게 접근
    _refs_map = cast(Mapping[str, Any] | None, _s.get("refs"))
    _q_cnt = len(cast(Sequence[Any], (_refs_map or {}).get("queries") or []))
    _d_cnt = len(cast(Sequence[Any], (_refs_map or {}).get("docs") or []))
    # 디스크(벡터스토어) 문서 수는 별도 측정하여 혼선 방지
    try:
        _doc_count_disk = vector_count(ns, persist_dir)
    except Exception:
        _doc_count_disk = -1

    # ── P2-4: 네임스페이스 합산 카운트(ns, ns-web, ns-local) ─────────────────
    def _ns_variants(base: str) -> list[tuple[str, str]]:
        return [(base, _default_chroma_dir(base)),
                (f"{base}-web", _default_chroma_dir(f"{base}-web")),
                (f"{base}-local", _default_chroma_dir(f"{base}-local"))]

    total_docs_all_ns = 0
    ns_counts: list[tuple[str, int]] = []
    try:
        for ns_i, dir_i in _ns_variants(ns):
            try:
                c_i = vector_count(ns_i, dir_i)
            except Exception:
                c_i = 0
            total_docs_all_ns += max(0, int(c_i or 0))
            ns_counts.append((ns_i, int(c_i or 0)))
    except Exception:
        pass

    try:
        _ns_cnt_str = ", ".join(f"{n}:{c}" for n, c in ns_counts)
    except Exception:
        _ns_cnt_str = "(n/a)"

    logger.info(
        "[web_search] refs: queries=%d, refs.docs=%d | vectorstore(on_disk:%s | sum_ns:%s → %s) | indexed_splits_this_round=%s",
        _q_cnt, _d_cnt, _doc_count_disk, _ns_cnt_str, total_docs_all_ns, int(chunk_total or 0),
    )

    # Pending routing (항상 보장)
    _pend = list(cast(Sequence[str] | None, _s.get("pending")) or [])
    if "vector_search_agent" not in _pend:
        _pend.append("vector_search_agent")
        _s["pending"] = _pend
        logger.info("[web_search] scheduled (pending) -> vector_search_agent")
    if not _s.get("next_agent"):
        _s["next_agent"] = "vector_search_agent"
        logger.info("[web_search] next_agent=vector_search_agent (guard)")

    # AUTO_WRITE_AFTER_RAG
    try:
        # 정본 schedule_writer_if_needed 시그니처(state, *, reason)에 맞게 호출
        schedule_writer_if_needed(
            _s,
            reason="after_web_search",
        )
    except Exception as _e:
        logger.debug("schedule_writer_if_needed skipped: %s", _e)

    # URL tally commit
    _seen_by_topic[topic_key] = list(_seen_sources)
    # flags는 Dict로 보장되어 있으나 정적 분석기 경고 방지를 위해 명시적 캐스트
    cast(Dict[str, Any], flags)["seen_sources_by_topic"] = _seen_by_topic
    logger.debug("[DEBUG] committed seen_sources_by_topic[%s] -> %s", topic_key, len(_seen_sources))

    actual = int(_round_added_urls)
    cap = int(MAX_INDEXED_PER_ROUND)
    capped = min(actual, cap) if cap > 0 else actual

    # state는 MutableMapping으로 정규화되어 있으므로 인덱싱 안전
    _s["round_added_urls"]    = actual
    _s["new_url_count"]       = actual
    _s["new_url_count_round"] = actual
    _s["round_new_urls"]      = actual

    # 마지막 인제스트 청크 메타 저장(라운드/단계별)
    last_ingest["ts"] = _now_str()
    # TypedDict(State)에 없는 키이므로 flags.debug에 저장
    try:
        dbg["last_ingest_chunks"] = last_ingest
    except Exception:
        # dbg가 dict가 아닐 예외 상황 대비(상위 flags에 백업)
        flags["last_ingest_chunks"] = last_ingest
    _s["web_stage"] = {
        "cap": _round_cap,
        "added_urls_round": actual,
        "queries_executed": len(queries),
        "persist_dir": persist_dir,
        "namespace": ns,
    }
    # debug 컨테이너는 위에서 dict로 보장됨
    dbg["last_capped_new_urls"] = capped

    logger.debug(
        "[DEBUG] round_added_urls(actual)=%s | new_url_count(capped)=%s | chunk_total=%s | queries_executed=%s",
        actual, capped, chunk_total, len(queries)
    )

    _task_set(pending, "done", True)
    _task_set(pending, "done_at", _now_str())

    if not has_pending(tasks, "vector_search_agent"):
        desc = "Perform vector search/verification for RAG indexing."
        if queries:
            desc += f" queries={queries}"
        if json_paths:
            desc += f" json_paths={json_paths}"
        desc += f" new_urls={int(state.get('round_added_urls') or 0)}"
        tasks.append(Task(agent="vector_search_agent", done=False, description=desc, done_at=""))

    mode_label = "local-only" if SKIP_WEB else "web+local"
    # f-string 중괄호 충돌 방지: dict → 문자열은 JSON 직렬화로 안전하게 출력
    from typing import Mapping as _Mapping, Any as _Any
    def _to_int(v: _Any, default: int = 0) -> int:
        try:
            s = str(v).strip()
            return int(s) if s else default
        except Exception:
            return default

    _round_map: _Mapping[str, _Any] = cast(_Mapping[str, _Any], last_ingest.get("round") or {})
    _last_ingest_summary = {
        "round": {
            "splits": _to_int(_round_map.get("splits", 0)),
            "new": _to_int(_round_map.get("new", 0)),
            "changed": _to_int(_round_map.get("changed", 0)),
        }
    }
    _msg_tail = f" (e.g., {json_paths[0]})" if json_paths else ""
    messages.append(
        AIMessage(
            content=(
                "[WEB SEARCH AGENT] Search complete "
                f"({len(queries)} queries). JSON saved and Chroma ingestion/preview done. "
                f"Mode={mode_label}; indexed_splits_this_round={int(chunk_total or 0)}; "
                f"last_ingest_chunks={json.dumps(_last_ingest_summary, ensure_ascii=False)}"
            ) + _msg_tail
        )
    )
    # 명시적으로 state에 반영(프레임워크가 in-place 갱신을 기대할 가능성 고려)
    _s["messages"] = messages
    _s["task_history"] = tasks

    # --- FINAL Guard for vector stage transition ----------------
    try:
        _ensure_next_is_vector(_s)
        logger.info("[web_search] guard: ensured vector_search_agent as next stage")
    except Exception as _e:
        _s["router_error"] = f"ensure_next_is_vector: {type(_e).__name__}: {str(_e)[:200]}"
        logger.critical("[web_search][FATAL] ensure_next_is_vector failed", exc_info=True)
        raise

    return {
        "messages": messages,
        "task_history": tasks,
        "references": cast(References, _s.get("references", {"queries": [], "docs": []})),
        "research_loop_active": bool(_s.get("research_loop_active")),
        "research_plan": _s.get("research_plan"),
        "new_url_count": int(_s.get("new_url_count") or actual),
        "new_url_count_round": int(_s.get("new_url_count_round") or actual),
        "round_new_urls": int(_s.get("round_new_urls") or actual),
        # 라우터/디버그용: 이번 라운드 인덱싱 결과(스플릿 기준)
        "indexed_chunks_round": int(chunk_total or 0),
        "last_ingest_chunks": last_ingest,
        "flags": cast("Flags", flags),  # TypedDict 힌트
        "local_ingested_once": bool(_s.get("local_ingested_once")),
        # 라우터가 즉시 다음 스텝으로 넘어가도록 명시 신호 추가
        "next_agent": _s.get("next_agent", "vector_search_agent"),
    }



# ─────────────────────────────────────────────────────────────────────────────
# Backward-compat **getters** (스냅샷 상수 제거; 항상 최신 CFG 반영)
#  - 기존 모듈에서 상수에 의존하던 경우, 아래 getter로 교체하세요.
# ─────────────────────────────────────────────────────────────────────────────
def get_WRITER_AGENT() -> str:
    return str(_get_cfg_attr("WRITER_AGENT", "") or "")

def get_PROJECT_ROOT() -> str:
    return str(_get_cfg_attr("PROJECT_ROOT", "") or "")

def get_SEARCH_BACKENDS() -> str:
    return str(_get_cfg_attr("SEARCH_BACKENDS", "naver_direct,tavily") or "")

def get_HAS_GOOGLE_KEYS() -> bool:
    return _cfg_bool("HAS_GOOGLE_KEYS", False)

def get_HAS_SERPAPI() -> bool:
    return _cfg_bool("HAS_SERPAPI", False)

def get_HAS_TAVILY() -> bool:
    return _cfg_bool("HAS_TAVILY", False)

def get_MAX_INDEXED_PER_ROUND() -> int:
    return _cfg_int("MAX_INDEXED_PER_ROUND", 200)

def get_MAX_SEARCH_QUERIES_PER_ROUND() -> int:
    return _cfg_int("MAX_SEARCH_QUERIES_PER_ROUND", 3)

def get_LOCAL_RAG_ALLOW() -> str:
    return str(_get_cfg_attr("LOCAL_RAG_ALLOW", "") or "")

__all__ = [
    "web_search_agent",
    # runtime CFG getters
    "get_WRITER_AGENT", "get_PROJECT_ROOT", "get_SEARCH_BACKENDS",
    "get_HAS_GOOGLE_KEYS", "get_HAS_SERPAPI", "get_HAS_TAVILY",
    "get_MAX_INDEXED_PER_ROUND", "get_MAX_SEARCH_QUERIES_PER_ROUND",
    "get_LOCAL_RAG_ALLOW",
]