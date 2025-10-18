from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os, re
from typing import TypedDict, List, Any, Mapping, cast, MutableMapping, Iterable
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
from utils.tasks import has_pending, iter_tool_calls
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
from utils.tasks import schedule_writer_if_needed


# ── Refs 타입 도우미 ──────────────────────────────────────────────────────────
class Refs(TypedDict):
    queries: List[str]
    docs: List[Any]           # 안전을 위해 Any

def _to_refs(raw: Mapping[str, Any] | None) -> Refs:
    if not isinstance(raw, Mapping):
        return {"queries": [], "docs": []}
    return {
        "queries": list(cast(List[str], raw.get("queries") or [])),
        "docs":    list(cast(List[Any], raw.get("docs") or [])),
    }

_DEFAULT_REFS: Refs = {"queries": [], "docs": []}

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

def _doc_title(d: Any) -> str:
    meta = getattr(d, "metadata", {}) or {}
    t = meta.get("title") or ""
    if not t:
        t = (getattr(d, "page_content", "") or "").split("\n", 1)[0]
    return _ell(t or "(no title)")

def _doc_url(d: Any) -> str:
    meta = getattr(d, "metadata", {}) or {}
    return meta.get("source") or meta.get("url") or ""

def _doc_score(d: Any):
    s = getattr(d, "score", None)
    if s is None:
        meta = getattr(d, "metadata", {}) or {}
        s = meta.get("score")
    return s

def _log_retrieval(query: str, docs: list[Any], tag: str = "vector_search") -> None:
    try:
        logger.info("[%(tag)s][query] %(q)s", {"tag": tag, "q": _ell(query)})
        if not docs:
            logger.info("[%(tag)s] no hits", {"tag": tag})
            return
        lines = []
        topn = min(_LOG_TOPK, len(docs))
        for i, d in enumerate(docs[:topn], start=1):
            u = _doc_url(d)
            h = _host(u)
            sc = _doc_score(d)
            t = _doc_title(d)
            if sc is not None:
                lines.append(f"  {i:>2}. {t}\n      └─ {h} :: {u}  (score={sc})")
            else:
                lines.append(f"  {i:>2}. {t}\n      └─ {h} :: {u}")
        logger.info("[%(tag)s][top%(n)d]\n%(body)s", {"tag": tag, "n": topn, "body": "\n".join(lines)})
    except Exception:
        pass


# ── 메인 에이전트 ─────────────────────────────────────────────────────────────
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

    # === 네임스페이스 & 퍼시스트 디렉터리 (A안: 단일 진실) ====================
    topic_slug: str = (state.get("topic_slug") or os.getenv("TOPIC_SLUG") or "default").strip()
    env_ns = (os.getenv("CHROMA_NAMESPACE") or "").strip()
    ns: str = env_ns or f"{topic_slug}-default"

    # 단일 persist_dir: 항상 ns 기준 디렉터리 사용
    persist_dir = _default_chroma_dir(ns)

    # 상태에 기록(타입 안전: flags.chroma.* 사용)
    flags = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    chroma = cast(MutableMapping[str, Any], flags.setdefault("chroma", {}))
    chroma["ns"] = ns
    chroma["dir"] = persist_dir

    logger.info("[vector_search] ns=%s (CHROMA_NAMESPACE=%r, topic_slug=%r)", ns, env_ns, topic_slug)
    logger.info("[vector_search] persist_dir(default_resolve)=%s", persist_dir)

    # ✅ 첫 라운드에만 clear (내부에서 CLEAR_ON_FIRST_VECTOR/CLEAR_CHROMA_ON_START 체크)
    try:
        ensure_vector_store_cleared_once(namespace=ns, persist_directory=persist_dir)
    except Exception as e:
        logger.debug("ensure_vector_store_cleared_once skipped/failed: %s", e)

    TOP_K = int(os.getenv("RAG_TOP_K", "6"))

    # ── (옵션) 웹 검색을 건너뛴 세션에서 로컬만 인덱싱 요청이 있을 때 1회 수행 ──
    l_chunks = 0
    try:
        ensure_local = os.getenv("SKIP_WEB_SEARCH", "0") == "1"
        local_globs_env = os.getenv("LOCAL_RAG_GLOBS", "")
        need_local = ensure_local and bool(local_globs_env.strip())
        not_yet = not state.get("local_ingested_once")
        if need_local and not_yet:
            slug = topic_slug
            import re as _re
            raw_globs = [g.strip() for g in _re.split(r"[|,\n]+", local_globs_env) if g.strip()]

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
                logger.info("[VECTOR SEARCH AGENT] on-demand local ingest: %s", dedup)
                l_jsons, l_docs, l_chunks = ingest_local_files(
                    dedup,
                    namespace=ns,
                    persist_directory=persist_dir,   # ★ 통일된 persist_dir 사용
                    topic_slug=slug,
                    root_dir=current_path,
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
        return any(b in ql for b in bad_markers)

    # ─────────────────────────────────────────────────────────────────────────
    # 1) 사용자 질의 우선 검색
    # ─────────────────────────────────────────────────────────────────────────
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    user_q = _extract_user_query(last_human.content) if (last_human and isinstance(last_human.content, str)) else ""
    user_q = _clean_seed(user_q)
    user_q_clean = _strip_web_filters(user_q)
    user_key = user_q_clean.strip().lower()

    if user_q_clean and (not _is_noise_query(user_q_clean)) and _ok_query(user_q_clean) and (user_key not in ran_queries):
        if _looks_like_local_glob(user_q_clean):
            logger.debug("[FILTER] skip local/glob query: %s", user_q_clean)
        else:
            try:
                logger.debug("retrieve.invoke args: %s", {
                    "query_raw": user_q,
                    "query_retrieval": user_q_clean,
                    "top_k": TOP_K,
                })
                retrieved_docs: list[Any] = retrieve.invoke({
                    "query": user_q_clean,
                    "namespace": ns,
                    "persist_directory": persist_dir,   # ★ 통일
                    "top_k": TOP_K
                })
            except Exception as e:
                logger.warning("retrieve 실패(user_q='%s' → '%s'): %s", user_q, user_q_clean, e)
                retrieved_docs = []

            _log_retrieval(user_q_clean, retrieved_docs, tag="vector_search")

            accum_queries.append(user_q_clean)
            accum_docs.extend(retrieved_docs)
            ran_queries.add(user_key)

        merged_dict = merge_refs(cast(dict[str, Any], references), accum_queries, accum_docs)
        references = _to_refs(merged_dict)
        cast(MutableMapping[str, Any], state)["references"] = references

        if os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1":
            schedule_writer_if_needed(
                cast(MutableMapping[str, Any], state),
                tasks=tasks, messages=messages, outline_text=outline_text, debug=True
            )

        logger.debug("ns=%s persist_dir=%s TOP_K=%s ALLOW_LOCAL_SUMMARY=%s",
                     ns, persist_dir, TOP_K, os.getenv('ALLOW_LOCAL_SUMMARY'))
        logger.debug("retrieved_docs=%s for user_q_clean=%r", len(retrieved_docs), user_q_clean)
        for i, d in enumerate((retrieved_docs or [])[:2], 1):
            meta = getattr(d, "metadata", {}) or {}
            snip = (getattr(d, "page_content", "") or "")[:100].replace("\n", " ")
            logger.debug("ctx%s source=%s snip=%r", i, meta.get('source'), snip)

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
                    messages.append(AIMessage(content=reply_text))

                    state["qa_direct_reply"] = True
                    state["new_url_count"] = as_int(state, "new_url_count", 0)
                    state["new_url_count_round"] = as_int(state, "new_url_count_round", 0)
                    state["round_new_urls"] = as_int(state, "round_new_urls", 0)

                    if not has_pending(tasks, "communicator"):
                        tasks.append(Task(agent="communicator", done=False,
                                          description="사용자 질의에 대한 요약 답변 전달", done_at=""))

                    pending.done = True
                    pending.done_at = _now_str()
                    return {"messages": messages, "task_history": tasks, "references": references}
                except Exception as e:
                    logger.warning("QA 요약 생성 실패: %s", e)
            else:
                messages.append(AIMessage(content="요청과 직접 매칭되는 로컬 문서를 찾지 못했어요. 파일 경로/패턴(LOCAL_RAG_GLOBS)을 확인해 주세요."))
                state["qa_direct_reply"] = True
                state["new_url_count"] = as_int(state, "new_url_count", 0)
                state["new_url_count_round"] = as_int(state, "new_url_count_round", 0)
                state["round_new_urls"] = as_int(state, "round_new_urls", 0)

                if not has_pending(tasks, "communicator"):
                    tasks.append(Task(agent="communicator", done=False, description="안내 전달 및 다음 요청 확인", done_at=""))
                pending.done = True
                pending.done_at = _now_str()
                return {"messages": messages, "task_history": tasks, "references": references}
    else:
        logger.debug("[SKIP user] q='%s' empty=%s noise=%s ok=%s dup=%s",
                     user_q_clean,
                     not bool(user_q_clean),
                     _is_noise_query(user_q_clean),
                     _ok_query(user_q_clean),
                     user_key in ran_queries)

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

    # 3b) 기존 레퍼런스 질의 재조회
    for q in preexisting_queries:
        raw = q
        q = _clean_seed(raw)
        q_for_retrieve = _strip_web_filters(q)
        key = q_for_retrieve.strip().lower()

        if _looks_like_local_glob(q_for_retrieve):
            logger.debug("[FILTER] skip local/glob query: %s", q_for_retrieve)
            continue

        if (not q_for_retrieve) or _is_noise_query(q_for_retrieve) or (not _ok_query(q_for_retrieve)) or (key in ran_queries):
            logger.debug("[SKIP preexisting] q='%s' empty=%s noise=%s ok=%s dup=%s",
                         q_for_retrieve,
                         not bool(q_for_retrieve),
                         _is_noise_query(q_for_retrieve),
                         _ok_query(q_for_retrieve),
                         key in ran_queries)
            continue

        logger.debug("retrieve.invoke args: %s", {
            "query_raw": q,
            "query_retrieval": q_for_retrieve,
            "top_k": TOP_K
        })

        try:
            retrieved_docs = retrieve.invoke({
                "query": q_for_retrieve,
                "namespace": ns,
                "persist_directory": persist_dir,   # ★ 통일
                "top_k": TOP_K
            })
        except Exception as e:
            logger.warning("retrieve 실패(query='%s' → '%s'): %s", q, q_for_retrieve, e)
            continue

        _log_retrieval(q_for_retrieve, retrieved_docs, tag="vector_search")

        accum_queries.append(q_for_retrieve)
        accum_docs.extend(retrieved_docs)
        ran_queries.add(key)

    # 4) LLM 설계 질의 실행
    import json as _json

    for args in iter_tool_calls(search_plans, "retrieve"):
        if isinstance(args, str):
            try:
                args = _json.loads(args)
            except Exception:
                args = {"query": str(args)}
        elif not isinstance(args, dict):
            logger.debug("retrieve tool args ignored (unsupported type): %r", type(args).__name__)
            continue

        raw = (args.get("query") or "")
        query = _clean_seed(raw)
        q_for_retrieve = _strip_web_filters(query)
        key = q_for_retrieve.strip().lower()

        if _looks_like_local_glob(q_for_retrieve):
            logger.debug("[FILTER] skip local/glob query: %s", q_for_retrieve)
            continue

        if (not q_for_retrieve) or _is_noise_query(q_for_retrieve) or (not _ok_query(q_for_retrieve)) or (key in ran_queries):
            logger.debug("[SKIP plan] q='%s' empty=%s noise=%s ok=%s dup=%s",
                         q_for_retrieve,
                         not bool(q_for_retrieve),
                         _is_noise_query(q_for_retrieve),
                         _ok_query(q_for_retrieve),
                         key in ran_queries)
            continue

        logger.debug("retrieve.invoke args: %s", {
            "query_raw": query,
            "query_retrieval": q_for_retrieve,
            "top_k": TOP_K
        })

        try:
            retrieved_docs = retrieve.invoke({
                "query": q_for_retrieve,
                "namespace": ns,
                "persist_directory": persist_dir,   # ★ 통일
                "top_k": TOP_K
            })
        except Exception as e:
            logger.warning("retrieve 실패(query='%s' → '%s'): %s", query, q_for_retrieve, e)
            continue

        _log_retrieval(q_for_retrieve, retrieved_docs, tag="vector_search")

        accum_queries.append(q_for_retrieve)
        accum_docs.extend(retrieved_docs)
        ran_queries.add(key)

    merged_dict = merge_refs(cast(dict[str, Any], references), accum_queries, accum_docs)
    references = _to_refs(merged_dict)
    cast(MutableMapping[str, Any], state)["references"] = references

    if os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1":
        schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            tasks=tasks, messages=messages, outline_text=outline_text, debug=True
        )

    # 숫자 포함 스니펫 facts_ctx 구성
    try:
        snips = []
        for d in (references.get("docs") or [])[:20]:
            txt = (getattr(d, "page_content", "") or "")
            lines = [ln.strip() for ln in txt.splitlines()
                     if re.search(r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:%|조|억|만대|GWh|kWh|원|달러|bn|trn)\b", ln)]
            for ln in lines[:2]:
                snips.append(ln[:300])
            if len(snips) >= 5:
                break
        state["facts_ctx"] = "\n".join(snips[:5])
    except Exception:
        state["facts_ctx"] = ""

    logger.info("Queries executed: %s", len(accum_queries))
    for q in accum_queries[:10]:
        logger.debug("  - %s", q)
    if len(accum_queries) > 10:
        logger.debug("  ... (+%s more)", len(accum_queries) - 10)

    logger.info("References collected: %s", len(references["docs"]))
    for i, doc in enumerate(references["docs"][:10], start=1):
        logger.debug("[%02d] %s", i, _plain_snip(getattr(doc, "page_content", "") or "", 160))
    if len(references["docs"]) > 10:
        logger.debug("  ... (+%s more)", len(references["docs"]) - 10)

    try:
        _log_retrieval(f"(summary) total {len(accum_queries)} queries", references["docs"], tag="vector_search")
    except Exception:
        pass

    pending.done = True
    pending.done_at = _now_str()

    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)

    def _has_research_pipeline(tsk_list) -> bool:
        return any(
            (getattr(t, "done", True) is False)
            and getattr(t, "agent", "") in (
                "research_planner", "web_search_agent", "vector_search_agent", "research_synthesizer"
            )
            for t in (tsk_list or [])
        )

    explicit_flag = state.get("research_loop_active")
    if isinstance(explicit_flag, bool):
        research_loop_active = explicit_flag
    else:
        has_objective = bool(state.get("research_objectives"))
        has_plan = bool((state.get("research_plan") or {}).get("objective"))
        pipeline_on = _has_research_pipeline(tasks)
        research_loop_active = (
            (role == "research analyst")
            and (max_iter > 0)
            and (rounds_done < max_iter)
            and (has_objective or has_plan or pipeline_on)
        )

    writer_agent = WRITER_AGENT
    AUTO_WRITE_DURING_RESEARCH = os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1"

    logger.debug("[writer_guard] %s", {
        "DOC_MODE": DOC_MODE,
        "WRITER_AGENT": writer_agent,
        "AUTO_WRITE_AFTER_RAG": os.getenv("AUTO_WRITE_AFTER_RAG"),
        "AUTO_WRITE_DURING_RESEARCH": os.getenv("AUTO_WRITE_DURING_RESEARCH"),
        "research_loop_active": research_loop_active,
        "has_writer_pending": has_pending(tasks, writer_agent, prefix="write"),
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
                    round_new = max(0, int(str(v)))
                    break
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

    if (not research_loop_active) or AUTO_WRITE_DURING_RESEARCH:
        did = schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            tasks=tasks,
            messages=messages,
            outline_text=outline_text,
            debug=True,
        )
        if (not did) and not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="검색/인덱싱 완료 보고 및 다음 집필 대상 확인", done_at=""))

    _qs = references.get("queries", [])
    _qs_view = _qs[:8] + (["..."] if len(_qs) > 8 else [])
    messages.append(AIMessage(content=f"[VECTOR SEARCH AGENT] 검색 완료 (질의 {len(_qs)}건, 예시): { _qs_view }"))
    return {"messages": messages, "task_history": tasks, "references": references}
