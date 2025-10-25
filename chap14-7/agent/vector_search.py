# agent\vector_search.py -*- coding: utf-8 -*-
from __future__ import annotations

import logging, os, re, json as _json
from typing import TypedDict, List, Any, Mapping, cast, MutableMapping, Tuple
logger = logging.getLogger(__name__)

from utils.tasks import HumanMessage, AIMessage
from core.llm import get_llm
from core.config import DOC_MODE, WRITER_AGENT
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

# ── logging helpers ───────────────────────────────────────────────────────────
_LOG_TOPK = int(os.getenv("LOG_TOPK", "3") or "3")
_LOG_WRAP = int(os.getenv("LOG_WRAP", "88") or "88")

def _ell(s: str, n: int = _LOG_WRAP) -> str:
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

        lines, topn = [], min(_LOG_TOPK, len(docs))
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
    try:
        r = float(os.getenv("RETRIEVE_WEB_RATIO", "0.67"))
        return 0.0 if r < 0 else (1.0 if r > 1 else r)
    except Exception:
        return 0.67

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
    ns_web = (os.getenv("CHROMA_NAMESPACE_WEB") or "").strip()
    ns_loc = (os.getenv("CHROMA_NAMESPACE_LOCAL") or "").strip()
    include_base = os.getenv("CHROMA_INCLUDE_BASE", "0") == "1"
    mode = (os.getenv("MERGE_RETRIEVE_MODE", "web_first") or "web_first").lower()

    # persist_directory 일관성: 외부 인자가 있으면 모든 NS에 동일 적용, 없으면 기본 규칙
    def _dir_for(ns: str) -> str:
        return persist_dir.strip() if (persist_dir and persist_dir.strip()) else _default_chroma_dir(ns)

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
        "[dual-retrieve] mode=%s include_base=%s k=%d (web=%d, local=%d, base=%d) → merged=%d",
        mode, include_base, top_k, len(web_docs), len(loc_docs), len(base_docs), len(merged or [])
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


# ── Main ──────────────────────────────────────────────────────────────────────
def vector_search_agent(state: State):
    logger.info("============ VECTOR SEARCH AGENT ============")
    llm = get_llm()
    state = sanitize_state(state)

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
    references: Refs = get_refs(state)
    outline_text = get_topic_outline_text(state)

    # ✅ 플래너/레퍼런스 기반 seed 쿼리 후보 확보
    plan_qs = ((state.get("research_plan") or {}).get("queries") or []) or (state.get("planner_queries") or [])
    refs_qs = list(references.get("queries") or [])

    # Namespace & persist dir
    topic_slug: str = (state.get("topic_slug") or os.getenv("TOPIC_SLUG") or "default").strip()
    env_ns = (os.getenv("CHROMA_NAMESPACE") or "").strip()
    ns: str = env_ns or f"{topic_slug}-default"
    persist_dir = _default_chroma_dir(ns)

    # 웹/로컬 네임스페이스가 있으면 1회 초기화 가드도 양쪽 적용
    try:
        ensure_vector_store_cleared_once(namespace=ns, persist_directory=persist_dir)
        ns_web = (os.getenv("CHROMA_NAMESPACE_WEB") or "").strip()
        ns_loc = (os.getenv("CHROMA_NAMESPACE_LOCAL") or "").strip()
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

    TOP_K = int(os.getenv("RAG_TOP_K", "6"))

    # Local ingest on-demand (optional)
    try:
        ensure_local = os.getenv("SKIP_WEB_SEARCH", "0") == "1"
        local_globs_env = os.getenv("LOCAL_RAG_GLOBS", "")
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
                    dedup, namespace=(os.getenv("CHROMA_NAMESPACE_LOCAL") or ns),
                    persist_directory=_default_chroma_dir(os.getenv("CHROMA_NAMESPACE_LOCAL") or ns),
                    topic_slug=slug, root_dir=current_path,
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

            ALLOW_SUMMARY = os.getenv("ALLOW_LOCAL_SUMMARY", "0") == "1"

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

                            _flags = state.get("flags") or {}
                            _writer_waiting = _has_writer_pending(tasks) and _flags.get("pending_write_title")
                            if _writer_waiting:
                                state["qa_direct_reply"] = False
                                logger.info("[vector_search] writer pending detected → skip qa_direct_reply; hand off to writer.")
                            else:
                                messages.append(AIMessage(content=reply_text))
                                state["qa_direct_reply"] = True
                                state["new_url_count"] = as_int(state, "new_url_count", 0)
                                state["new_url_count_round"] = as_int(state, "new_url_count_round", 0)
                                state["round_new_urls"] = as_int(state, "round_new_urls", 0)

                                flags = state.get("flags") or {}
                                has_writer_lock = bool(flags.get("pending_write_title"))
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
                                        if state.get("qa_direct_reply") else
                                        "Writer pending; suppressed QA handoff (no communicator).")
                            return {"messages": messages, "task_history": tasks,
                                    "references": references,
                                    "qa_direct_reply": bool(state.get("qa_direct_reply"))}
                        except Exception as e:
                            logger.warning("QA 요약 생성 실패: %s", e)

            if not ALLOW_SUMMARY and os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1":
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

    if os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1":
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

    writer_agent = WRITER_AGENT
    AUTO_WRITE_DURING_RESEARCH = os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1"

    logger.debug("[writer_guard] %s", {
        "DOC_MODE": DOC_MODE,
        "WRITER_AGENT": writer_agent,
        "AUTO_WRITE_AFTER_RAG": os.getenv("AUTO_WRITE_AFTER_RAG"),
        "AUTO_WRITE_DURING_RESEARCH": os.getenv("AUTO_WRITE_DURING_RESEARCH"),
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

        flags = state.get("flags") or {}
        has_writer_p = (
            has_pending(tasks, "section_writer", prefix="write:")
            or has_pending(tasks, "chapter_writer", prefix="write:")
        )

        if has_writer_p:
            state["qa_direct_reply"] = False

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
