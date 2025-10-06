from __future__ import annotations
from typing import Any
from langchain_core.messages import HumanMessage, AIMessage
from core.llm import get_llm
from core.config import DOC_MODE, WRITER_AGENT
from core.paths import current_path, now_str as _now_str, topic_dir as _topic_dir
from core.state_types import State
from core.models import Task, AgentName
from utils.sanitize import sanitize_state, as_int
from utils.rag_utils import merge_refs, refs_preview_text
from utils.query_filters import strip_web_filters as _strip_web_filters, looks_like_local_glob as _looks_like_local_glob, clean_seed as _clean_seed, ok_query as _ok_query

from prompts import get_vector_search_prompt
from content_utils import read_outline, next_unwritten_title
from utils.tasks import has_pending, get_last_write_target, iter_tool_calls
from utils.outline import get_topic_outline_text
from tools.web_rag import (
    retrieve,
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    _default_chroma_dir,
    ensure_vector_store_cleared_once,
)
from tools.local_rag import ingest_local_files
from utils.text_utils import plain_snip as _plain_snip


import os,re
llm=get_llm()


def vector_search_agent(state: State):
    print("\n\n============ VECTOR SEARCH AGENT ============")
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
        # print(f"[INIT] vector store cleared once (ns='{ns}', dir='{persist_dir}')")

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

    # new_url_count = int(l_chunks or 0)
    # state["new_url_count"] = new_url_count
    # state["new_url_count_round"] = new_url_count
    # state["round_new_urls"] = new_url_count

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

    _qs = references.get("queries", [])
    _qs_view = _qs[:8] + (["..."] if len(_qs) > 8 else [])
    messages.append(AIMessage(f"[VECTOR SEARCH AGENT] 검색 완료 (질의 {len(_qs)}건, 예시): { _qs_view }"))
    return {"messages": messages, "task_history": tasks, "references": references}