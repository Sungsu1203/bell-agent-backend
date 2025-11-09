# agent\vector_search.py -*- coding: utf-8 -*-
from __future__ import annotations

import logging, os, re, json as _json
from typing import TypedDict, List, Any, Mapping, cast, MutableMapping, Tuple, Dict
logger = logging.getLogger(__name__)

from utils.tasks import HumanMessage, AIMessage
from core.llm import get_llm
import core.config as config
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task
from utils.sanitize import sanitize_state, as_int
from utils.rag_utils import merge_refs
from utils.query_filters import (
    strip_web_filters as _strip_web_filters,
    looks_like_local_glob as _looks_like_local_glob,
    clean_seed as _clean_seed,
    ok_query as _ok_query,
)
from prompts import get_vector_search_prompt
from utils.tasks import has_pending, iter_tool_calls, schedule_writer_if_needed
from utils.outline import get_topic_outline_text
from tools.web_rag import (
    retrieve,
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    ensure_vector_store_cleared_once,
    _default_chroma_dir,
)
from tools.local_rag import ingest_local_files
from utils.text_utils import plain_snip as _plain_snip

from utils.ref_format import format_ref_for_log

from typing import Callable, Optional
from pathlib import Path

try:
    from tools.metrics import record_retrieval_source as _record_retrieval_source  # pyright: ignore[reportMissingImports]
except Exception:
    _record_retrieval_source = None  # type: ignore[assignment]

def record_retrieval_source(
    web_cnt: int,
    local_cnt: int,
    *,
    base_cnt: int = 0,
    total: Optional[int] = None,
) -> None:
    try:
        if _record_retrieval_source is not None:
            func = cast(Callable[..., None], _record_retrieval_source)
            func(web_cnt=web_cnt, local_cnt=local_cnt, base_cnt=base_cnt, total=total)
    except Exception:
        pass

# ── Refs ──────────────────────────────────────────────────────────────────────
class Refs(TypedDict):
    queries: List[str]
    docs: List[Any]

def _to_refs(raw: Mapping[str, Any] | None) -> Refs:
    if not isinstance(raw, Mapping):
        return {"queries": [], "docs": []}
    return {"queries": list(cast(List[str], raw.get("queries") or [])),
            "docs":    list(cast(List[Any], raw.get("docs") or []))}

def get_refs(state: Mapping[str, Any]) -> Refs:
    return _to_refs(cast(Mapping[str, Any] | None, state.get("references")))

# ── config helpers (env → CFG → module default) ───────────────────────────────
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
    v = _cfg_str(name, str(default))
    try:
        return int(str(v).strip())
    except Exception:
        return default

def _cfg_float(name: str, default: float = 0.0) -> float:
    v = _cfg_str(name, str(default))
    try:
        return float(str(v).strip())
    except Exception:
        return default

def _cfg_bool(name: str, default: bool = False) -> bool:
    v = _cfg_str(name, "1" if default else "0").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}

# ── logging helpers (runtime-config aware) ────────────────────────────────────
def _log_topk() -> int:
    return _cfg_int("LOG_TOPK", 5)

def _log_wrap() -> int:
    return _cfg_int("LOG_WRAP", 120)

def _ell(s: str, n: Optional[int] = None) -> str:
    if n is None:
        n = _log_wrap()
    s = (s or "").replace("\n", " ").strip()
    return (s[:n-1] + "…") if len(s) > n else s

def _host(u: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(u).netloc or "").lower()
    except Exception:
        return ""

def _raw_title(d: Any) -> str:
    meta = getattr(d, "metadata", {}) or {}
    t = meta.get("title") or ""
    if not t:
        t = (getattr(d, "page_content", "") or "").split("\n", 1)[0]
    return (t or "").strip()

def _doc_title(d: Any) -> str:
    t = _raw_title(d)
    return _ell(t or "(no title)")

def _doc_url(d: Any) -> str:
    meta = getattr(d, "metadata", {}) or {}
    # 일부 로더는 path를 사용함
    return meta.get("source") or meta.get("url") or meta.get("path") or ""


def _doc_score(d: Any):
    s = getattr(d, "score", None)
    if s is None:
        meta = getattr(d, "metadata", {}) or {}
        s = meta.get("score")
    return s

# URL 정규화(추적 파라미터 제거 + fragment 제거 + 소문자 + 트레일링 슬래시 제거)
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
_TRACKING = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","gclid","fbclid","igsh","mc_cid","mc_eid"}
def _normalize_url(u: str) -> str:
    try:
        pu = urlparse((u or "").strip())
        qs = [(k, v) for k, v in parse_qsl(pu.query, keep_blank_values=False)
              if k.lower() not in _TRACKING]
        base = urlunparse((pu.scheme or "https",
                           (pu.netloc or "").replace("m.","www.").lower(),
                           (pu.path or "/"),
                           "", urlencode(qs, doseq=True), ""))  # drop fragment
        return base.rstrip("/")
    except Exception:
        return (u or "").strip().lower().rstrip("/")

def _dedupe_docs(docs: list[Any]) -> list[Any]:
    """(normalized url, lowered title) 키로 문서 중복 제거."""
    seen, out = set(), []
    for d in docs or []:
        url = _normalize_url(_doc_url(d))
        title = (_raw_title(d) or "").lower()
        key = (url, title)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out

def _log_retrieval(query: str, docs: list[Any], tag: str = "vector_search") -> None:
    try:
        logger.info("[%(tag)s][query] %(q)s", {"tag": tag, "q": _ell(query)})
        if not docs:
            logger.info("[%(tag)s] no hits", {"tag": tag})
            return

        lines, topn = [], min(_log_topk(), len(docs))
        for i, d in enumerate(docs[:topn], start=1):
            raw_url = _doc_url(d)
            title = _doc_title(d)
            # 사람이 읽기 쉬운 표시 두 줄 생성
            title_line, link_line = format_ref_for_log(raw_url)

            # 로컬/웹 라벨
            label = "LOCAL" if raw_url.startswith("file://") else _host(raw_url) or ""
            score = _doc_score(d)
            score_part = f"  (score={score})" if score is not None else ""

            # 타이틀은 메타데이터 우선, 없으면 포매터 타이틀 사용
            main_title = title or title_line

            lines.append(f"  {i:>2}. {main_title}\n      └─ {label} :: {link_line}{score_part}")

        logger.info("[%(tag)s][top%(n)d]\n%(body)s", {"tag": tag, "n": topn, "body": "\n".join(lines)})
    except Exception:
        pass

# ── Dual-namespace retrieve (웹/로컬 병합) ────────────────────────────────────
def _env_ratio() -> float:
    r = _cfg_float("RETRIEVE_WEB_RATIO", 0.5)
    return 0.0 if r < 0 else (1.0 if r > 1 else r)

def _split_k(top_k: int) -> Tuple[int, int]:
    """웹/로컬 k 분배: round half up 보정으로 최소 1 보장."""
    k = max(1, int(top_k or 1))
    r = _env_ratio()
    k_web = max(1, int(round(k * r))) if k > 1 else 1
    k_loc = max(0, k - k_web)
    return (k_web, k_loc)

def _merge_web_first(web_docs: List[Any], local_docs: List[Any], k: int) -> List[Any]:
    """웹 우선 인터리브: w, l, w, l ... 식으로 채우되, 부족분은 나머지로 채움."""
    merged: List[Any] = []
    i = j = 0
    while len(merged) < k and (i < len(web_docs) or j < len(local_docs)):
        if i < len(web_docs):
            merged.append(web_docs[i]); i += 1
        if len(merged) >= k: break
        if j < len(local_docs):
            merged.append(local_docs[j]); j += 1
    return _dedupe_docs(merged)[:k]

def _merge_by_score(web_docs: List[Any], local_docs: List[Any], k: int) -> List[Any]:
    """간단 점수 병합(없으면 웹>로컬 우선순)."""
    both = []
    for d in (web_docs or []):
        both.append(("web", _doc_score(d) or 0.0, d))
    for d in (local_docs or []):
        both.append(("local", _doc_score(d) or 0.0, d))
    # 점수 내림차순, 동점은 웹 우선
    both.sort(key=lambda x: (x[1], 1 if x[0]=="local" else 2), reverse=True)
    return _dedupe_docs([t[2] for t in both])[:k]

def _dual_retrieve(query: str, *, top_k: int, ns_default: str, persist_dir: str) -> List[Any]:
    """환경설정에 따라 웹/로컬(+기본) 네임스페이스를 병합 조회.
       ⚠️ 말미에 기본 NS로 '무조건 폴백'을 수행하여 0-hit 반복을 방지한다.
       ⚠️ persist_directory는 호출 인자(persist_dir)를 우선 사용하여 모든 NS에 일관 적용.
    """
    ns_web = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    include_base_cfg = _cfg_bool("CHROMA_INCLUDE_BASE", False)
    mode = (_cfg_str("MERGE_RETRIEVE_MODE", "web_first") or "web_first").lower()

    # persist_directory 일관성: 외부 인자가 있으면 모든 NS에 동일 적용, 없으면 기본 규칙
    def _dir_for(ns: str) -> str:
        return persist_dir.strip() if (persist_dir and persist_dir.strip()) else _default_chroma_dir(ns)

    # ◀︎ 개선: base 컬렉션이 비어 있으면 include_base 비활성화
    include_base = False
    if include_base_cfg:
        base_ns = ns_default
        base_dir = _dir_for(base_ns)
        try:
            cnt = _collection_count(base_ns, base_dir)
            include_base = (cnt > 0)
            if not include_base:
                logger.debug("[dual-retrieve] base collection empty (ns=%s dir=%s) → include_base=False", base_ns, base_dir)
            else:
                logger.debug("[dual-retrieve] base collection count=%s (ns=%s) → include_base=True", cnt, base_ns)
        except Exception as e:
            # 불명일 땐 보수적으로 끔(불필요한 0건 조회 방지)
            include_base = False
            logger.debug("[dual-retrieve] base collection check failed → include_base=False (%s)", e)


    # 0) 아무 것도 없으면 기본 NS만
    if not ns_web and not ns_loc:
        try:
            docs = retrieve.invoke({
                "query": query, "namespace": ns_default,
                "persist_directory": _dir_for(ns_default), "top_k": top_k
            })
            return _dedupe_docs(list(docs or []))
        except Exception as e:
            logger.warning("retrieve 실패(single ns='%s'): %s", ns_default, e)
            return []

    # 내부 헬퍼
    def _get(ns: str, k: int) -> List[Any]:
        if k <= 0:
            return []
        try:
            return retrieve.invoke({
                "query": query, "namespace": ns,
                "persist_directory": _dir_for(ns), "top_k": k
            }) or []
        except Exception as e:
            logger.warning("retrieve 실패(ns='%s'): %s", ns, e)
            return []

    # 1) (공통) 웹/로컬 조회
    #    - 우선 웹/로컬을 k 분할로 조회 (한쪽만 설정된 경우 자동으로 (top_k,0) 또는 (0,top_k))
    k_web, k_loc = _split_k(top_k) if (ns_web and ns_loc) else ((top_k, 0) if ns_web else (0, top_k))
    web_docs = _dedupe_docs(_get(ns_web, k_web) if ns_web else [])
    loc_docs = _dedupe_docs(_get(ns_loc, k_loc) if ns_loc else [])

    # 2) base 포함 설정이면 부족분만큼 기본 NS에서 추가
    base_docs: List[Any] = []
    if include_base:
        remaining = max(0, top_k - len(web_docs) - len(loc_docs))
        if remaining > 0:
            try:
                base_docs = _dedupe_docs(retrieve.invoke({
                    "query": query, "namespace": ns_default,
                    "persist_directory": _dir_for(ns_default), "top_k": remaining
                }) or [])
                logger.info("[dual-retrieve] include_base used → fetched %d from base", len(base_docs))
            except Exception as e:
                logger.warning("retrieve 실패(base ns='%s'): %s", ns_default, e)
                base_docs = []

    # 3) 병합 정책 적용
    if mode == "score_merge":
        # 세 소스(웹/로컬/기본)를 점수 기준으로 통합 정렬(동점: 웹>로컬>기본)
        pool = []
        for d in web_docs:  pool.append(("web",   _doc_score(d) or 0.0, d))
        for d in loc_docs:  pool.append(("local", _doc_score(d) or 0.0, d))
        for d in base_docs: pool.append(("base",  _doc_score(d) or 0.0, d))
        prio = {"web": 3, "local": 2, "base": 1}  # 동점 우선순위
        pool.sort(key=lambda x: (x[1], prio.get(x[0], 0)), reverse=True)
        merged = _dedupe_docs([t[2] for t in pool])[:top_k]
    else:
        # web_first: 웹/로컬 인터리브 후, 부족분을 기본으로 보충
        merged = _merge_web_first(web_docs, loc_docs, top_k)
        if include_base and len(merged) < top_k and base_docs:
            tail_need = top_k - len(merged)
            merged = _dedupe_docs(list(merged) + list(base_docs)[:tail_need])[:top_k]

    # 4) ✅ 무조건 폴백: 병합 결과가 비었으면 기본 NS에서 재조회
    if not merged:
        try:
            fallback = _dedupe_docs(retrieve.invoke({
                "query": query, "namespace": ns_default,
                "persist_directory": _dir_for(ns_default), "top_k": top_k
            }) or [])
            if fallback:
                logger.warning("[dual-retrieve] web/local empty → FALLBACK to base ns='%s' (%d hits)",
                               ns_default, len(fallback))
                # [METRICS] 폴백이 적용된 경우: 베이스만으로 집계
                try:
                    record_retrieval_source(web_cnt=0, local_cnt=0, base_cnt=len(fallback or []), total=len(fallback or []))
                except Exception:
                    pass

                return fallback
        except Exception as e:
            logger.warning("retrieve 실패(fallback base ns='%s'): %s", ns_default, e)

    logger.debug(
        "[dual-retrieve] mode=%s include_base=%s k=%d (web=%d, local=%d, base=%d) → merged=%d | ns_default=%s",
        mode, include_base, top_k, len(web_docs), len(loc_docs), len(base_docs), len(merged or []), ns_default
    )
    # [METRICS] 병합 결과의 웹/로컬(및 베이스) 비율 집계
    try:
        m_ids = {id(d) for d in (merged or [])}
        web_in  = sum(1 for d in (web_docs  or []) if id(d) in m_ids)
        local_in= sum(1 for d in (loc_docs  or []) if id(d) in m_ids)
        base_in = sum(1 for d in (base_docs or []) if id(d) in m_ids)
        record_retrieval_source(web_cnt=web_in, local_cnt=local_in, base_cnt=base_in, total=len(merged or []))
    except Exception:
        pass

    return merged

# ── collection size helpers (optional, safe fallbacks) ────────────────────────
def _collection_count(ns: str, persist_dir: str) -> int:
    """
    벡터 스토어의 ns 컬렉션에 문서가 몇 개인지 추정.
    - tools.web_rag.ingest.get_collection_count 가 있으면 그것을 사용
    - 없으면 has_any_docs로 0/1만 판정
    - 실패 시 -1 반환(불명)
    """
    try:
        # 최우선: 명시적 카운트 함수
        from tools.web_rag.ingest import get_collection_count as _gcc  # type: ignore
        try:
            return int(_gcc(ns, persist_dir))
        except Exception:
            pass
    except Exception:
        pass
    try:
        # 폴백: 존재 여부만 체크(있으면 1, 없으면 0)
        from tools.web_rag.ingest import has_any_docs as _had  # type: ignore
        ok = bool(_had(ns, persist_dir))
        return 1 if ok else 0
    except Exception:
        return -1


# ── Main ──────────────────────────────────────────────────────────────────────
def vector_search_agent(state: State):
    logger.info("============ VECTOR SEARCH AGENT ============")
    llm = get_llm()
    state = cast(State, sanitize_state(state))

    # ── [DIRECT_QA] 모드: 선주입 금지 → 의도만 표시하고, 실제 답변 생성 시점에만 qa_direct_reply=True 세팅
    try:
        dq = bool(getattr(config.CFG, "DIRECT_QA", False))
    except Exception:
        dq = False
    if dq:
        flags_mm0 = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
        # 의도 플래그만 남김: 실제 답변 생성 성공 시점에 qa_direct_reply/suppress_writer를 켠다.
        flags_mm0["direct_qa_intent"] = True
        # 과거 선세팅 잔여치가 남아있다면 방지
        flags_mm0.pop("qa_direct_reply", None)
        flags_mm0.pop("suppress_writer", None)
        logger.debug("[vector_search][direct_qa] intent=1 (qa_direct_reply will be set only when reply is generated)")


    tasks = state.get("task_history", []) or []
    messages = state.get("messages", []) or []
    if not tasks:
        # 방어적 처리: 작업 이력이 없더라도 자체 펜딩을 생성해 진행
        logger.warning("[vector_search] task_history empty → auto-create and pend self")
        tasks = []
        # state는 TypedDict(State)이므로 MutableMapping으로 캐스팅 후 갱신
        cast(MutableMapping[str, Any], state)["task_history"] = tasks
        auto_task = Task(agent="vector_search_agent", done=False, description="auto-pend", done_at="")
        tasks.append(auto_task)
        # messages에도 안내 메시지를 남겨 가시성 확보(선택)
        messages.append(AIMessage(content="[VECTOR SEARCH AGENT] 펜딩이 없어 자동으로 등록하고 진행합니다."))

    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "vector_search_agent"), None)
    if pending is None:
        # 마지막 태스크가 본인이며 미완료면 그것을 사용
        if tasks:
            last = tasks[-1]
            if (getattr(last, "agent", "") == "vector_search_agent") and (not getattr(last, "done", True)):
                pending = last
        # 그래도 없으면 자동 펜딩 추가 후 진행
        if pending is None:
            logger.warning("[vector_search] pending missing → auto-append and continue")
            auto_task = Task(agent="vector_search_agent", done=False, description="auto-pend", done_at="")
            tasks.append(auto_task)
            # state 반영(참조 동일하지만 안전하게 다시 대입)
            cast(MutableMapping[str, Any], state)["task_history"] = tasks
            messages.append(AIMessage(content="[VECTOR SEARCH AGENT] 기존 펜딩이 없어 자동 등록했습니다."))
            pending = auto_task

    vector_search_system_prompt = get_vector_search_prompt()

    mission = (pending.description or "")
    references: Refs = get_refs(state)
    outline_text = get_topic_outline_text(state)

    # ✅ 플래너/레퍼런스 기반 seed 쿼리 후보 확보
    plan_qs = ((state.get("research_plan") or {}).get("queries") or []) or (state.get("planner_queries") or [])
    refs_qs = list(references.get("queries") or [])

    # Namespace & persist dir
    topic_slug: str = (state.get("topic_slug") or getattr(config.CFG, "TOPIC_SLUG", "") or "default").strip()
    env_ns = (_cfg_str("CHROMA_NAMESPACE", "") or "").strip()
    ns: str = env_ns or f"{topic_slug}-default"
    persist_dir = _default_chroma_dir(ns)

    # ── [ANCHOR: NS_POLICY_INIT] 웹/로컬 NS 병합 정책(환경변수 우선) ─────────────
    ns_web = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    merge_mode = (_cfg_str("MERGE_RETRIEVE_MODE", "web_first") or "web_first").lower()
    web_ratio = _cfg_float("RETRIEVE_WEB_RATIO", 0.5)
    include_base = _cfg_bool("CHROMA_INCLUDE_BASE", False)

    # 상태/플래그에 NS 정책 기록 (디버그/가시성)
    flags = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    chroma = cast(MutableMapping[str, Any], flags.setdefault("chroma", {}))
    chroma.update({
        "ns": ns, "dir": persist_dir,
        "ns_web": ns_web, "ns_local": ns_loc,
        "merge_retrieve_mode": merge_mode,
        "retrieve_web_ratio": web_ratio,
        "include_base": include_base,
    })

    # [P0-5] base 컬렉션이 비어 있으면 include_base 비활성화
    try:
        from tools.web_rag.ingest import has_any_docs as _has_any_docs
        if callable(_has_any_docs) and not _has_any_docs(ns, persist_dir):
            include_base = False
            chroma["include_base"] = False
            logger.debug("[vector_search] base collection empty → include_base=False (ns=%s)", ns)
    except Exception as e:
        logger.debug("[vector_search] base collection check skipped: %s", e)

    # 양쪽(NS_WEB/NS_LOCAL) 모두 설정되어 있고 include_base가 꺼져 있으면
    # 기본 NS에서도 부족분을 보충하도록 안내 로그(정책 확인용)
    if ns_web and ns_loc and not include_base:
        logger.info("[vector_search][ns_policy] Both web/local namespaces set. "
                    "Consider enabling CHROMA_INCLUDE_BASE=1 to backfill from base ns (optional).")

    logger.info("[vector_search][ns_policy] ns(web)=%r ns(local)=%r base=%r | mode=%s ratio=%.2f",
                ns_web or "-", ns_loc or "-", ns, merge_mode, web_ratio)


    # 웹/로컬 네임스페이스가 있으면 1회 초기화 가드도 양쪽 적용
    try:
        ensure_vector_store_cleared_once(namespace=ns, persist_directory=persist_dir)
        # reload_config() 이후 값 반영 보장
        ns_web = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()
        ns_loc = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()
        if ns_web:
            ensure_vector_store_cleared_once(namespace=ns_web, persist_directory=_default_chroma_dir(ns_web))
        if ns_loc:
            ensure_vector_store_cleared_once(namespace=ns_loc, persist_directory=_default_chroma_dir(ns_loc))
    except Exception as e:
        logger.debug("ensure_vector_store_cleared_once skipped/failed: %s", e)

    flags = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    chroma = cast(MutableMapping[str, Any], flags.setdefault("chroma", {}))
    chroma["ns"], chroma["dir"] = ns, persist_dir

    logger.info("[vector_search] ns=%s (CHROMA_NAMESPACE=%r, topic_slug=%r)", ns, env_ns, topic_slug)
    logger.info("[vector_search] persist_dir(default_resolve)=%s", persist_dir)

    TOP_K = _cfg_int("RAG_TOP_K", 5)

    # ────────────────────────────────────────────────────────────────────
    # [SMOKE RETRIEVE] 시작점 품질 점검: 2~3개 선택 질의로 top-1 조회
    #   - 목적: 인덱스/네임스페이스/쿼리 정규화가 정상 동작하는지 빠르게 확인
    #   - 실패(전부 미스) 시: 라우팅 중단 + 사용자/로그 안내
    # 스위치: SMOKE_RETRIEVE(기본 on), SMOKE_RETRIEVE_MAX(기본 3)
    # ────────────────────────────────────────────────────────────────────
    def _mk_smoke_queries(st: Mapping[str, Any]) -> list[str]:
        title = (st.get("topic_title") or st.get("topic") or "").strip()
        base_qs: list[str] = []
        if title:
            base_qs.extend([f"{title} 성분", f"{title} 시장 규모", f"{title} 브랜드"])
        # 플래너/refs 보강(있으면 앞 2개만)
        plan = ((st.get("research_plan") or {}).get("queries") or [])[:2]
        refs = ((st.get("references") or {}).get("queries") or [])[:1]
        for q in list(plan) + list(refs):
            q = _strip_web_filters(_clean_seed(str(q or "")))
            if q and q not in base_qs:
                base_qs.append(q)
        # 과도 길이/노이즈 제거
        out: list[str] = []
        for q in base_qs:
            qc = _strip_web_filters(_clean_seed(q))
            if qc and (not _looks_like_local_glob(qc)) and _ok_query(qc):
                out.append(qc)
        max_n = max(1, _cfg_int("SMOKE_RETRIEVE_MAX", 3))
        return out[:max_n]

    def _summarize_doc(d: Any) -> str:
        try:
            ttl = _doc_title(d)
            url = _doc_url(d)
            score = _doc_score(d)
            host = "LOCAL" if (url or "").startswith("file://") else _host(url)
            sp = f" score={score}" if score is not None else ""
            return f"{ttl} | {host}{sp}"
        except Exception:
            return "(unknown)"

    flags_boot = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    do_smoke = _cfg_bool("SMOKE_RETRIEVE", True) and not bool(flags_boot.get("smoke_retrieve_done"))
    if do_smoke:
        smoke_qs = _mk_smoke_queries(state)
        hits: list[tuple[str, Any]] = []
        for sq in smoke_qs:
            try:
                docs1 = _dual_retrieve(sq, top_k=1, ns_default=ns, persist_dir=persist_dir) or []
            except Exception as e:
                logger.warning("[smoke] retrieve 실패(q=%r): %s", sq, e)
                docs1 = []
            if docs1:
                top = docs1[0]
                hits.append((sq, top))
                logger.info("[smoke][hit] q=%s → %s", _ell(sq, 80), _summarize_doc(top))
            else:
                logger.info("[smoke][miss] q=%s", _ell(sq, 80))

        flags_boot["smoke_retrieve_done"] = True

        if not hits:
            # 전부 실패 → 라우팅 중단 + 안내
            note = (
                "[VECTOR SEARCH AGENT] 스모크 조회 결과, 인덱스에서 적합한 문서를 찾지 못했습니다.\n"
                "- 점검 사항: (1) 네임스페이스/저장 경로, (2) 로컬 인제스트 수행 여부, (3) 웹 검색 후 인덱싱 상태\n"
                "- 제안: web_search_agent 실행 또는 LOCAL_RAG_GLOBS 설정 후 재인제스트를 시도하세요."
            )
            messages.append(AIMessage(content=note))
            logger.warning("[smoke] all queries miss → stop routing (ns=%s dir=%s)", ns, persist_dir)
            # 조기 종료(라우팅 stop)
            pending.done = True
            pending.done_at = _now_str()
            # 선택: 상위 라우터가 참조할 수 있게 플래그 남김
            flags_boot["routing_stopped_by_smoke"] = True
            return {"messages": messages, "task_history": tasks}
        
        else:
            # ── [DIRECT QA 게이트] 스모크 hit 중 최상위 스코어가 임계 이상이면 communicator 우선
            _MIN = _cfg_float("DIRECT_QA_MIN_SCORE", 0.35)
            _ALLOW_DUR = _cfg_bool("DIRECT_QA_ALLOW_DURING_RESEARCH", True)
            _REQ_SCORE = _cfg_bool("DIRECT_QA_REQUIRE_SCORE", True)

            def _score_of(d: Any) -> Optional[float]:
                s = _doc_score(d)
                try:
                    return float(s) if s is not None else None
                except Exception:
                    return None

            # 현재 연구 파이프라인 동작 중인지 경량 판정
            _pipeline_on = any(
                (getattr(t, "done", True) is False)
                and getattr(t, "agent", "") in ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")
                for t in (state.get("task_history") or [])
            )
            _ok_during = (not _pipeline_on) or (_ALLOW_DUR is True)

            # 점수 최댓값을 가진 문서 선택(스코어 없으면 정책에 따라 배제/허용)
            best_q, best_doc, best_sc = None, None, None
            for q, d in hits:
                sc = _score_of(d)
                if sc is None and _REQ_SCORE:
                    continue
                if (best_sc is None) or ((sc or 0.0) > (best_sc or 0.0)):
                    best_q, best_doc, best_sc = q, d, (sc if sc is not None else 0.0)

            if _ok_during and best_doc is not None and (best_sc is not None) and (best_sc >= _MIN):
                # writer가 이미 대기 중이면 직답 우선권을 양보
                _has_writer = (
                    has_pending(tasks, "section_writer", prefix="write:")
                    or has_pending(tasks, "chapter_writer", prefix="write:")
                )
                if not _has_writer:
                    # facts_ctx 제공(communicator가 바로 사용)
                    try:
                        txt = (getattr(best_doc, "page_content", "") or "").strip()
                        state["facts_ctx"] = (txt[:800] if txt else "")
                    except Exception:
                        state["facts_ctx"] = state.get("facts_ctx") or ""

                    flags_now = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
                    flags_now["qa_direct_reply"] = True
                    flags_now["suppress_writer"] = True
                    if flags_now.get("direct_qa_intent"):
                        flags_now.pop("direct_qa_intent", None)

                    if not has_pending(tasks, "communicator"):
                        tasks.append(
                            Task(
                                agent="communicator",
                                done=False,
                                description="스모크 매치: 최상위 문서 점수 임계 초과 → 즉시 직답",
                                done_at=""
                            )
                        )
                    logger.info(
                        "[vector_search][smoke→communicator] q=%r | url=%s | score=%.3f (min=%.3f)",
                        best_q, _ell(_doc_url(best_doc), 96), best_sc, _MIN
                    )
                    pending.done = True; pending.done_at = _now_str()
                    return {
                        "messages": messages,
                        "task_history": tasks,
                        "references": references,
                        "qa_direct_reply": True,
                    }


    # Local ingest on-demand (optional)
    try:
        ensure_local = _cfg_bool("SKIP_WEB_SEARCH", False)
        local_globs_env = _cfg_str("LOCAL_RAG_GLOBS", "")
        need_local = ensure_local and bool(local_globs_env.strip())
        not_yet = not state.get("local_ingested_once")
        if need_local and not_yet:
            slug = topic_slug
            import re as _re
            raw_globs = [g.strip() for g in _re.split(r"[|;, \n]+", local_globs_env) if g.strip()]

            def _norm(p: str) -> str:
                p = p.replace("<topic-slug>", slug or "**")
                return p.replace("\\", os.sep).replace("/", os.sep)

            dedup, seen = [], set()
            for g in (_norm(x) for x in raw_globs):
                k = g.lower() if os.name == "nt" else g
                if k in seen: continue
                seen.add(k); dedup.append(g)

            if dedup:
                logger.info("[VECTOR SEARCH AGENT] on-demand local ingest: %s", dedup)
                l_jsons, l_docs, l_chunks = ingest_local_files(
                    dedup, namespace=((getattr(config.CFG, "CHROMA_NAMESPACE_LOCAL", "") or ns)),
                    persist_directory=_default_chroma_dir(getattr(config.CFG, "CHROMA_NAMESPACE_LOCAL", "") or ns),
                    topic_slug=slug, root_dir=str(current_path),
                    add_web_pages_json_to_chroma=add_web_pages_json_to_chroma,
                    web_page_json_to_documents=web_page_json_to_documents,
                )
                if l_docs:
                    merged_dict = merge_refs(cast(dict[str, Any], references), [], l_docs)
                    references = _to_refs(merged_dict)
                    cast(MutableMapping[str, Any], state)["references"] = references
                state["local_ingested_once"] = True
    except Exception as e:
        logger.warning("on-demand local ingest 실패: %s", e)

    ran_queries: set[str] = set()
    accum_queries: list[str] = []
    accum_docs: list[Any] = []

    def _extract_user_query(s: str) -> str:
        if not isinstance(s, str):
            return ""
        s = s.strip().strip(" \"'“”‘’`")
        s_l = s.lower()
        if s_l in {"research", "research:", "research;"} or s_l.startswith("research "):
            return ""
        if re.search(r"<\s*research\s*:\s*[^>]+>", s, re.I):
            return ""
        if re.search(r"(섹션|section|챕터|chapter).{0,10}(작성|집필|써|write)", s, re.I) or \
           re.search(r"(작성|집필)\s*해\s*줘", s) or \
           re.search(r"섹션을\s*작성", s):
            return ""
        s = re.sub(r"^write\s*:\s*", "", s, flags=re.I).strip()
        s = re.sub(r"(요약해줘|요약|정리해줘|정리)\s*[\.\!\?…]*\s*$", "", s).strip()
        s = re.sub(r"[\.\!\?…]+$", "", s).strip()
        m = re.search(r"[A-Za-z0-9_]{6,}", s)
        return (m.group(0) if m else s) if len(s) >= 2 else ""

    def _was_research_token(s: str) -> bool:
        if not isinstance(s, str):
            return False
        s_l = s.strip().lower()
        return (s_l == "research" or s_l.rstrip(":;") == "research" or s_l.startswith("research "))

    def _is_noise_query(q: str) -> bool:
        ql = (q or "").strip().lower()
        if ql.rstrip(":;") == "research":
            return True
        if not ql or ql in {"force_query","force_queries","force"} or len(ql) <= 2:
            return True
        return any(b in ql for b in ["gtm.js","function(","<meta","<script","@media","var ","cookieconsent","usercentrics"])

    # --- seed query 우선 적용 (planner/refs) ---
    plan_q = ((state.get("research_plan") or {}).get("queries") or [])[:1]
    refs_q = (state.get("references") or {}).get("queries") or []
    seed = plan_q or refs_q
    if seed:
        cast(MutableMapping[str, Any], state)["vector_seed_query"] = str(seed[0]).strip()

    # 연구 루프 판정
    def _looks_like_research_mode(st):
        role = (st.get("agent_role") or "").strip().lower()
        has_plan = bool((st.get("research_plan") or {}).get("queries"))
        pipeline_on = any((getattr(t, "done", True) is False)
                          and getattr(t, "agent", "") in ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")
                          for t in (st.get("task_history") or []))
        explicit = bool(st.get("research_loop_active"))
        return explicit or (role == "research analyst") or has_plan or pipeline_on

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    forced_seed = bool(last_human and isinstance(last_human.content, str) and _was_research_token(last_human.content))
    skip_direct_qa = _looks_like_research_mode(state)
    user_q = "" if skip_direct_qa else _extract_user_query(last_human.content) if (last_human and isinstance(last_human.content, str)) else ""
    user_q = _clean_seed(user_q)
    user_q_clean = _strip_web_filters(user_q)
    user_key = user_q_clean.strip().lower()

    # 유저 질의가 비고, 강제시드 허용 상태면 시드 사용
    if (not user_q_clean) and state.get("vector_seed_query") and (forced_seed or not bool(state.get("research_loop_active"))):
        user_q = str(state.get("vector_seed_query") or "").strip()
        user_q_clean = _strip_web_filters(user_q)
        user_key = user_q_clean.strip().lower()

    if user_q_clean and (not _is_noise_query(user_q_clean)) and _ok_query(user_q_clean) and (user_key not in ran_queries):
        if _looks_like_local_glob(user_q_clean):
            logger.debug("[FILTER] skip local/glob query: %s", user_q_clean)
        else:
            try:
                logger.debug("retrieve.invoke (dual) args: %s", {"query": user_q_clean, "top_k": TOP_K})
                retrieved_docs: list[Any] = _dual_retrieve(user_q_clean, top_k=TOP_K, ns_default=ns, persist_dir=persist_dir)
            except Exception as e:
                logger.warning("retrieve 실패(user_q='%s' → '%s'): %s", user_q, user_q_clean, e)
                retrieved_docs = []

            retrieved_docs = _dedupe_docs(retrieved_docs)
            _log_retrieval(user_q_clean, retrieved_docs, tag="vector_search")
            accum_queries.append(user_q_clean); accum_docs.extend(retrieved_docs); ran_queries.add(user_key)

            merged_dict = merge_refs(cast(dict[str, Any], references), accum_queries, accum_docs)
            references = _to_refs(merged_dict)
            cast(MutableMapping[str, Any], state)["references"] = references

            ALLOW_SUMMARY = _cfg_bool("ALLOW_LOCAL_SUMMARY", False)

            from utils.tasks import has_pending as _has_p
            def _has_writer_pending(_tasks):
                try:
                    return _has_p(_tasks, "section_writer", prefix="write:") or _has_p(_tasks, "chapter_writer", prefix="write:")
                except Exception:
                    return any((not getattr(t, "done", False))
                               and getattr(t, "agent", "") in ("section_writer","chapter_writer")
                               and str(getattr(t, "description", "")).startswith("write:")
                               for t in (_tasks or []))

            _flags = state.get("flags") or {}
            if _has_writer_pending(tasks) and _flags.get("pending_write_title"):
                state["qa_direct_reply"] = False
                logger.info("[vector_search] writer pending detected → skip Direct QA generation; hand off to writer.")
                pending.done = True; pending.done_at = _now_str()
                return {"messages": messages, "task_history": tasks, "references": references}

            if ALLOW_SUMMARY:
                if retrieved_docs:
                    ctx_parts = []
                    for d in (retrieved_docs or [])[:3]:
                        txt = (getattr(d, "page_content", "") or "").strip()
                        if txt: ctx_parts.append(txt[:1200])
                    context = "\n\n---\n\n".join(ctx_parts).strip()

                    if context:
                        try:
                            prompt = (
                                "다음 컨텍스트만 근거로 한국어로 1문단 요약을 작성하세요.\n"
                                f"질문: {user_q}\n\n컨텍스트:\n{context}\n\n"
                                "지시사항:\n- 컨텍스트 밖의 지식은 쓰지 말 것\n- 불확실하면 모른다고 말할 것\n- 1문단(3~5문장)으로 간결히"
                            )
                            resp = llm.invoke(prompt)
                            reply_text = getattr(resp, "content", str(resp))

                            flags_now = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
                            _writer_waiting = _has_writer_pending(tasks) and flags_now.get("pending_write_title")
                            if _writer_waiting:
                                # writer가 대기 중이면 직답 모드를 켜지 않음
                                flags_now["qa_direct_reply"] = False
                                logger.info("[vector_search] writer pending detected → skip qa_direct_reply; hand off to writer.")
                            else:
                                messages.append(AIMessage(content=reply_text))
                                # ✅ 실제 답변 생성 성공 → 이 시점에서만 직답 모드 on
                                flags_now["qa_direct_reply"] = True
                                flags_now["suppress_writer"] = True
                                # 직답 의도 플래그는 소모 처리(선택)
                                if flags_now.get("direct_qa_intent"):
                                    flags_now.pop("direct_qa_intent", None)
                                state["new_url_count"] = as_int(state, "new_url_count", 0)
                                state["new_url_count_round"] = as_int(state, "new_url_count_round", 0)
                                state["round_new_urls"] = as_int(state, "round_new_urls", 0)

                                flags_mm = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
                                has_writer_lock = bool(flags_mm.get("pending_write_title"))
                                has_writer_p = (
                                    has_pending(tasks, "section_writer", prefix="write:")
                                    or has_pending(tasks, "chapter_writer", prefix="write:")
                                )
                                if not (has_writer_lock and has_writer_p):
                                    if not has_pending(tasks, "communicator"):
                                        tasks.append(
                                            Task(
                                                agent="communicator",
                                                done=False,
                                                description="사용자 질의에 대한 요약 답변 전달",
                                                done_at=""
                                            )
                                        )
                            pending.done = True; pending.done_at = _now_str()
                            logger.info("[DIRECT QA] %s",
                                        "Summary generated and returning to communicator."
                                        if cast(MutableMapping[str, Any], state.get("flags", {})).get("qa_direct_reply") else
                                        "Writer pending; suppressed QA handoff (no communicator).")
                            return {"messages": messages, "task_history": tasks,
                                    "references": references,
                                    "qa_direct_reply": bool(cast(MutableMapping[str, Any], state.get("flags", {})).get("qa_direct_reply"))}
                        except Exception as e:
                            logger.warning("QA 요약 생성 실패: %s", e)

            if not ALLOW_SUMMARY and _cfg_bool("AUTO_WRITE_DURING_RESEARCH", False):
                schedule_writer_if_needed(
                    cast(MutableMapping[str, Any], state),
                    tasks=tasks, messages=messages, outline_text=outline_text, debug=True
                )
    else:
        logger.debug("[SKIP user] q='%s' empty=%s noise=%s ok=%s dup=%s",
                     user_q_clean, not bool(user_q_clean), _is_noise_query(user_q_clean),
                     _ok_query(user_q_clean), user_key in ran_queries)

    # 2) Preexisting and planned queries
    if not ran_queries:
        seed_list = [q for q in plan_qs if q] or [q for q in refs_qs if q]
        if seed_list:
            seed_raw = seed_list[0]
            seed_clean = _strip_web_filters(_clean_seed(seed_raw))
            seed_key = seed_clean.strip().lower()
            if seed_clean and (not _is_noise_query(seed_clean)) and _ok_query(seed_clean) and (not _looks_like_local_glob(seed_clean)):
                try:
                    logger.debug("retrieve.invoke (dual) args: %s", {"query_raw": seed_raw, "query_retrieval": seed_clean, "top_k": TOP_K})
                    retrieved_docs = _dual_retrieve(seed_clean, top_k=TOP_K, ns_default=ns, persist_dir=persist_dir)
                except Exception as e:
                    logger.warning("retrieve 실패(seed='%s' → '%s'): %s", seed_raw, seed_clean, e)
                    retrieved_docs = []

                retrieved_docs = _dedupe_docs(retrieved_docs)
                _log_retrieval(seed_clean, retrieved_docs, tag="vector_search")
                accum_queries.append(seed_clean); accum_docs.extend(retrieved_docs); ran_queries.add(seed_key)

                merged_dict = merge_refs(cast(dict[str, Any], references), accum_queries, accum_docs)
                references = _to_refs(merged_dict)
                cast(MutableMapping[str, Any], state)["references"] = references

                flags = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
                flags["last_user_query"] = seed_raw

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

    for raw in preexisting_queries:
        q = _clean_seed(raw); q_for_retrieve = _strip_web_filters(q); key = q_for_retrieve.strip().lower()
        if _looks_like_local_glob(q_for_retrieve): continue
        if (not q_for_retrieve) or _is_noise_query(q_for_retrieve) or (not _ok_query(q_for_retrieve)) or (key in ran_queries):
            continue
        try:
            retrieved_docs = _dual_retrieve(q_for_retrieve, top_k=TOP_K, ns_default=ns, persist_dir=persist_dir)
        except Exception as e:
            logger.warning("retrieve 실패(query='%s' → '%s'): %s", q, q_for_retrieve, e); continue
        retrieved_docs = _dedupe_docs(retrieved_docs)
        _log_retrieval(q_for_retrieve, retrieved_docs, tag="vector_search")
        accum_queries.append(q_for_retrieve); accum_docs.extend(retrieved_docs); ran_queries.add(key)

    for args in iter_tool_calls(search_plans, "retrieve"):
        if isinstance(args, str):
            try: args = _json.loads(args)
            except Exception: args = {"query": str(args)}
        elif not isinstance(args, dict):
            logger.debug("retrieve tool args ignored (unsupported type): %r", type(args).__name__); continue

        query = _clean_seed(args.get("query") or "")
        q_for_retrieve = _strip_web_filters(query); key = q_for_retrieve.strip().lower()
        if _looks_like_local_glob(q_for_retrieve): continue
        if (not q_for_retrieve) or _is_noise_query(q_for_retrieve) or (not _ok_query(q_for_retrieve)) or (key in ran_queries):
            continue
        try:
            retrieved_docs = _dual_retrieve(q_for_retrieve, top_k=TOP_K, ns_default=ns, persist_dir=persist_dir)
        except Exception as e:
            logger.warning("retrieve 실패(query='%s' → '%s'): %s", query, q_for_retrieve, e); continue
        retrieved_docs = _dedupe_docs(retrieved_docs)
        _log_retrieval(q_for_retrieve, retrieved_docs, tag="vector_search")
        accum_queries.append(q_for_retrieve); accum_docs.extend(retrieved_docs); ran_queries.add(key)

    accum_docs = _dedupe_docs(accum_docs)
    merged_dict = merge_refs(cast(dict[str, Any], references), accum_queries, accum_docs)
    references = _to_refs(merged_dict)
    cast(MutableMapping[str, Any], state)["references"] = references

    if _cfg_bool("AUTO_WRITE_DURING_RESEARCH", False):
        schedule_writer_if_needed(cast(MutableMapping[str, Any], state),
                                  tasks=tasks, messages=messages, outline_text=outline_text, debug=True)

    # facts_ctx (optional)
    try:
        snips = []
        for d in (references.get("docs") or [])[:20]:
            txt = (getattr(d, "page_content", "") or "")
            lines = [ln.strip() for ln in txt.splitlines()
                     if re.search(r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:%|조|억|만대|GWh|kWh|원|달러|bn|trn)\b", ln)]
            for ln in lines[:2]:
                snips.append(ln[:300])
            if len(snips) >= 5: break
        state["facts_ctx"] = "\n".join(snips[:5])
    except Exception:
        state["facts_ctx"] = ""

    try:
        _log_retrieval(f"(summary) total {len(accum_queries)} queries", references["docs"], tag="vector_search")
    except Exception:
        pass

    pending.done = True; pending.done_at = _now_str()

    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)

    def _has_research_pipeline(tsk_list) -> bool:
        return any((getattr(t, "done", True) is False)
                   and getattr(t, "agent", "") in ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")
                   for t in (tsk_list or []))

    explicit_flag = state.get("research_loop_active")
    if isinstance(explicit_flag, bool):
        research_loop_active = explicit_flag
    else:
        has_objective = bool(state.get("research_objectives"))
        has_plan = bool((state.get("research_plan") or {}).get("objective"))
        pipeline_on = _has_research_pipeline(tasks)
        research_loop_active = (role == "research analyst") and (max_iter > 0) and (rounds_done < max_iter) and (has_objective or has_plan or pipeline_on)

    writer_agent = getattr(config.CFG, "WRITER_AGENT", "section_writer")
    AUTO_WRITE_DURING_RESEARCH = _cfg_bool("AUTO_WRITE_DURING_RESEARCH", False)
 

    logger.debug("[writer_guard] %s", {
        "DOC_MODE": getattr(config.CFG, "DOC_MODE", "report"),
        "WRITER_AGENT": writer_agent,
        "AUTO_WRITE_AFTER_RAG": _cfg_bool("AUTO_WRITE_AFTER_RAG", True),
        "AUTO_WRITE_DURING_RESEARCH": AUTO_WRITE_DURING_RESEARCH,
        "research_loop_active": research_loop_active,
        "has_writer_pending": has_pending(tasks, writer_agent, prefix="write:"),
        "agent_role": state.get("agent_role"),
        "iteration_count": state.get("iteration_count"),
        "research_round": state.get("research_round"),
    })

    if research_loop_active:
        logger.info("[HANDOFF] scheduling research_synthesizer (research_loop_active=True)")
        try:
            round_new = None
            for k in ("new_url_count_round", "round_added_urls", "round_new_urls", "new_urls", "new_url_count"):
                v = state.get(k)
                if v is not None and str(v).strip() != "":
                    round_new = max(0, int(str(v))); break
            if round_new is not None:
                state["new_url_count"] = round_new
                state["new_url_count_round"] = round_new
                state["round_new_urls"] = round_new
        except Exception:
            pass

        if not has_pending(tasks, "research_synthesizer"):
            tasks.append(Task(agent="research_synthesizer", done=False, description="synthesize:auto", done_at=""))

        messages.append(AIMessage(content="[VECTOR SEARCH AGENT] 연구 라운드 진행 중 → 합성 단계(Research Synthesizer)로 이동"))
        return {"messages": messages, "task_history": tasks, "references": references}

    writer_task_scheduled = False
    if (not research_loop_active) or AUTO_WRITE_DURING_RESEARCH:
        did = schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            tasks=tasks, messages=messages, outline_text=outline_text, debug=True
        )
        if did:
            writer_task_scheduled = True

        flags_mm2 = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
        has_writer_p = (
            has_pending(tasks, "section_writer", prefix="write:")
            or has_pending(tasks, "chapter_writer", prefix="write:")
        )

        if has_writer_p:
            flags_mm2["qa_direct_reply"] = False
            # 직답 의도가 남아있다면 여기서도 소거(옵션)
            if flags_mm2.get("direct_qa_intent"):
                flags_mm2.pop("direct_qa_intent", None)

        if (not writer_task_scheduled) and (not has_writer_p):
            if not has_pending(tasks, "communicator"):
                tasks.append(
                    Task(
                        agent="communicator",
                        done=False,
                        description="검색/인덱싱 완료 보고 및 다음 집필 대상 확인",
                        done_at=""
                    )
                )

        return {"messages": messages, "task_history": tasks, "references": references}
    
# (모듈 하단의 정적 상수는 제거하여 reload_config() 이후에도 값이 반영되도록 함)
