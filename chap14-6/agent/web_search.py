# agents/web_search.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

# (외부 타입/설정/유틸)
from core.state_types import State
from core.config import WRITER_AGENT            # ← main.py의 전역 상수 대신 여기서 import
from core.paths import current_path, topic_dir as _topic_dir, now_str as _now_str
#from utils.sanitize import sanitize_numeric_state_generic
from core.models import Task, AgentName
from utils.sanitize import sanitize_state

from utils.rag_utils import merge_refs, vector_count          # ← main.py의 merge_refs 대신 utils 경로
from prompts import get_web_search_prompt

from utils.tasks import has_pending, get_last_write_target, iter_tool_calls
from utils.outline import pick_outline_filename, get_topic_outline_text
from core.config import DOC_MODE, PROJECT_ROOT  # (또는 여러분이 쓰는 설정 모듈)
from utils.forced_queries import extract_forced_queries_from_messages

from settings_gatekeep import gatekeep_enabled, get_allowed_domains
from settings_gatekeep import url_allowed as _allowed

from tools.web_rag import (
    retrieve,
    web_search,
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    _default_chroma_dir,
    clear_vector_store,

)

from utils.query_filters import looks_like_local_glob, clean_seed as _clean_seed, ok_query
from tools.local_rag import ingest_local_files

from core.llm import get_llm

# (main.py 안에서 쓰던 나머지 import 들은 함수 안 'late import' 그대로 둬도 됩니다)

def web_search_agent(state: State):
    # ────────────────────────────────────────────────────────────────────────────
    # Imports (내부 임포트 고정)
    import os, re, time, json, glob, shutil
    from pathlib import Path
    from utils.tasks import HumanMessage, AIMessage
    from langchain_core.documents import Document
    from urllib.parse import urlparse
    import re as _re
    from typing import Iterable, Set
    # ────────────────────────────────────────────────────────────────────────────
    logger.info("============ WEB SEARCH AGENT ============")
    llm = get_llm()
    state = sanitize_state(state)

    # --- (1) 태스크 확보 ------------------------------------------------------
    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "web_search_agent"), None)
    if pending is None:
        raise ValueError(f"web_search_agent pending task 없음. 현재 마지막 태스크: {tasks[-1]}")

    web_search_system_prompt = get_web_search_prompt()

    messages = state.get("messages", [])
    # ✅ 이전 라운드까지의 refs를 그대로 이어받기
    references: dict[str, list] = state.get("references", {"queries": [], "docs": []})
    _existing_qs = set(q.strip().lower() for q in (references.get("queries") or []) if q and q.strip())

    outline_text = get_topic_outline_text(state)
    mission = (pending.description or "").strip()

    inputs = {
        "mission": mission,
        "references": references,
        "messages": messages,
        "outline": outline_text,
        "current_time": _now_str(),
        "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
    }

    queries: list[str] = []         # 이번 라운드 실제 실행/추가된 질의 목록
    json_paths: list[str] = []      # 저장된 웹검색 JSON 경로
    new_docs_preview: list[Document] = []  # 미리보기용 문서 샘플

    MAX_INDEXED_PER_ROUND = int(os.getenv("MAX_INDEXED_PER_ROUND", "0"))  # 0=제한없음
    MAX_SEARCH_QUERIES_PER_ROUND = int(os.getenv("MAX_SEARCH_QUERIES_PER_ROUND", "6"))
    SKIP_WEB = os.getenv("SKIP_WEB_SEARCH", "0") == "1"
    if SKIP_WEB:
        logger.info("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 → 외부 웹검색 건너뜀(로컬 RAG만).")

    ns = state.get("chroma_ns") or os.getenv("CHROMA_NAMESPACE") or "default"
    slug = state.get("topic_slug")
    persist_dir = _topic_dir(slug) if slug else None

    chunk_total = 0  # 이번 라운드 인덱싱된 청크 수

    # [ANCHOR: VECTOR_COUNT_AFTER_INIT]
    try:
        logger.debug("[DEBUG] after init, doc_count=%s", vector_count(ns, persist_dir))
    except Exception as e:
        logger.debug("[DEBUG] after init, doc_count check failed: %s", e)

    # --- (2) 소스 게이트 설정(허용 도메인) -----------------------------------
    _DEFAULT_ALLOWED: Set[str] = {
        "me.go.kr","molit.go.kr","motie.go.kr","korea.kr","mss.go.kr","moef.go.kr",
        "kofpi.or.kr","kepco.co.kr","kesis.kr","kama.or.kr","kotra.or.kr","kei.re.kr",
        "iea.org","oecd.org","kdi.re.kr","kiep.go.kr",
    }

    def _normalize_domains(domains: Iterable[str] | None) -> Set[str]:
        if not domains:
            return set()
        return {d.strip().lower() for d in domains if isinstance(d, str) and d.strip()}

    _env_allowed_raw = os.getenv("ALLOWED_DOMAINS")
    if _env_allowed_raw and _env_allowed_raw.strip():
        ENV_ALLOWED_DOMAINS: Set[str] = _normalize_domains(_env_allowed_raw.split(","))
    else:
        ENV_ALLOWED_DOMAINS = set(_DEFAULT_ALLOWED)

    ENV_GATE: bool = os.getenv("GATE_KEEP_SOURCES", "0").strip().lower() in {"1", "true", "yes"}

    GATE_KEEP_SOURCES: bool = ENV_GATE
    ALLOWED_DOMAINS: Set[str] = set(ENV_ALLOWED_DOMAINS)

    try:
        GATE_KEEP_SOURCES = bool(gatekeep_enabled())
        _maybe_domains = get_allowed_domains()
        parsed = _normalize_domains(_maybe_domains)
        if parsed:
            ALLOWED_DOMAINS = parsed
    except Exception:
        pass

    # --- (2b) JSON 로더/필터 ---------------------------------------------------
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

    def _filter_json_by_domain(json_path: str) -> str:
        if not GATE_KEEP_SOURCES:
            return json_path
        try:
            items = _load_items(json_path)
        except Exception:
            return json_path
        if not isinstance(items, list):
            return json_path
        filtered = []
        for it in items:
            if not isinstance(it, dict):
                continue
            url = (it.get("url") or it.get("source") or "")
            if _allowed(url):
                filtered.append(it)
        if not filtered:
            return json_path
        p = Path(json_path)
        out = p.with_name(p.stem + "_filtered" + p.suffix)
        out.write_text(json.dumps(filtered, ensure_ascii=False), encoding="utf-8")
        return str(out)
    
    # [ANCHOR: ROUND_URL_TALLY_INIT]
    flags = state.setdefault("flags", {})
    topic_key = (slug or "default")

    _seen_by_topic = flags.setdefault("seen_sources_by_topic", {})
    _seen_sources = set(_seen_by_topic.get(topic_key) or [])

    _round_added_urls = 0

    def _norm_url(u: str) -> str:
        u = (u or "").strip()
        if not u:
            return ""
        # 로컬/파일 경로
        if u.startswith("file://") or _re.match(r"^[a-zA-Z]:[\\/]", u) or u.startswith(os.sep):
            path = u.replace("\\", "/").lower()
            path = _re.sub(r"__v_\d+_\d+$", "", path)
            return path
        # HTTP(S)
        if "://" not in u:
            u = "http://" + u
        p = urlparse(u)
        host = p.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        normalized_path = _re.sub(r"__v_\d+_\d+$", "", p.path)
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
            items = _load_items(json_path)
            if isinstance(items, list):
                _tally_new_urls_from_items(items)
        except Exception as e:
            logger.warning("[WARN] url tally failed for %s: %s", json_path, e)

    # 🔎 상태 디버그
    logger.debug("[DEBUG] seen_sources_by_topic[%s] = %s", topic_key, len(_seen_by_topic.get(topic_key, [])))

    # --- (2c) 품질 필터 --------------------------------------------------------
    def _is_bad_doc(d: Document) -> bool:
        txt = ((getattr(d, "page_content", None) or "")[:2000]).lower()
        return any(k in txt for k in ["access denied","enable javascript","just a moment","security controls triggered","captcha"])

    # --- (3) 실제 검색/적재 실행 유틸 -----------------------------------------
    def _run_web_search_with_guard(q: str, preview_limit: int = 5, retries: int = 2) -> bool:
        nonlocal chunk_total
        if SKIP_WEB:
            logger.info("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 → web search skipped.")
            return False

        q = (q or "").strip()
        if not q:
            return False

        ok = False
        for attempt in range(retries + 1):
            try:
                # 1) 검색 호출
                _, json_path = web_search.invoke({"query": q})
                json_paths.append(json_path)

                # 2) 결과 JSON 이동(옵션)
                try:
                    res_dir = os.path.join(current_path, "resources", state.get("topic_slug") or "default")
                    Path(res_dir).mkdir(parents=True, exist_ok=True)
                    new_json_path = os.path.join(res_dir, os.path.basename(json_path))
                    if os.path.abspath(json_path) != os.path.abspath(new_json_path):
                        shutil.move(json_path, new_json_path)
                        json_path = new_json_path
                        json_paths[-1] = json_path
                    logger.info("[web_search] saved → %s", json_path)
                except Exception as move_e:
                    logger.warning("[WARN] resources JSON 이동 실패: %s", move_e)

                # 3) 허용 도메인 필터
                filtered_json = _filter_json_by_domain(json_path)
                _tally_new_urls_from_json(filtered_json)

                # 4) 인덱싱
                try:
                    _orig_count, chunk_count = add_web_pages_json_to_chroma(
                        filtered_json, namespace=ns, persist_directory=persist_dir
                    )
                    chunk_total += int(chunk_count or 0)
                except Exception as idx_e:
                    logger.warning("[WARN] add_web_pages_json_to_chroma 실패: %s", idx_e)

                # 5) 프리뷰
                try:
                    docs = web_page_json_to_documents(filtered_json)[:preview_limit]
                    if GATE_KEEP_SOURCES:
                        def _src(d: Document) -> str:
                            md = getattr(d, "metadata", {}) or {}
                            return md.get("source") or md.get("url") or ""
                        docs = [d for d in docs if _allowed(_src(d))]
                    docs = [d for d in docs if not _is_bad_doc(d)]
                    for d in docs:
                        meta = getattr(d, "metadata", {}) or {}
                        src = meta.get("source") or meta.get("url") or "unknown"
                        new_docs_preview.append(
                            Document(
                                page_content=(d.page_content or "")[:500],
                                metadata={"source": src}
                            )
                        )
                except Exception as prev_e:
                    logger.warning("[WARN] preview build 실패: %s", prev_e)

                queries.append(q)
                ok = True
                break

            except Exception as e:
                if attempt < retries:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                logger.warning("[WARN] web_search 실패(재시도 후): %s -> %s", q, e)
                ok = False
                break

        return ok

    # --- (4) 쿼리 실행 파이프라인 ---------------------------------------------
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

    # 4-1) 강제 쿼리
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

    # 4-2) LLM 설계 쿼리
    if not SKIP_WEB:
        llm_with_web = llm.bind_tools([web_search])
        search_plans = (web_search_system_prompt | llm_with_web).invoke(inputs)
        ran = 0
        for args in iter_tool_calls(search_plans, "web_search"):
            if ran >= MAX_SEARCH_QUERIES_PER_ROUND:
                break
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

    # 4-3) 자동 폴백(자동 모드 & 지금까지 실행 쿼리 전무)
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

    # --- (5) 로컬 파일 인덱싱 (토픽당 1회, TypedDict-safe) --------------------
    env_globs = [g.strip() for g in (os.getenv("LOCAL_RAG_GLOBS", "") or "").split("|") if g.strip()]
    slug_or_wildcard = slug if slug else "**"

    def _normalize_and_expand(p: str) -> str:
        p = p.replace("<topic-slug>", slug_or_wildcard)
        p = p.replace("\\", os.sep).replace("/", os.sep)
        return p

    local_globs: list[str] = [_normalize_and_expand(p) for p in env_globs]

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and isinstance(last_human.content, str):
        m = re.search(r"(?:add_local|local_rag|내부자료|내부문서)\s*:\s*(.+)", last_human.content, flags=re.I)
        if m:
            arg = m.group(1)
            for token in re.split(r"[|;,]", arg):
                t = token.strip()
                if t:
                    local_globs.append(_normalize_and_expand(t))

    # 중복 제거
    seen = set(); dedup_globs = []
    for g in local_globs:
        key = g.lower() if os.name == "nt" else g
        if key in seen:
            continue
        seen.add(key); dedup_globs.append(g)

    # 스캔 로그
    debug_matches_total = 0
    if not dedup_globs:
        logger.info("[LOCAL SCAN] 구성된 글롭이 없습니다. LOCAL_RAG_GLOBS 또는 add_local 명령을 확인하세요.")
    else:
        for pattern in dedup_globs:
            pattern_abs = pattern if pattern.startswith(os.sep) or (":" in pattern) else os.path.join(current_path, pattern)
            found = list(glob.iglob(pattern_abs, recursive=True))
            logger.info("[LOCAL SCAN] %s  -> %s file(s)", pattern, len(found))
            if len(found) == 0:
                logger.info("[LOCAL SCAN]   ↳ 경로 확인: %s", pattern_abs)
            debug_matches_total += len(found)
        if debug_matches_total == 0:
            logger.info("[LOCAL SCAN] 모든 글롭이 0개 매칭입니다. 경로/패턴 점검 필요.")

    # ✅ 토픽별 1회 인덱싱 가드
    flags = state.setdefault("flags", {})
    li = flags.setdefault("local_ingested", {})
    topic_key = (slug or "default")
    skip_local_ingest = bool(li.get(topic_key))
    if skip_local_ingest:
        logger.info("[LOCAL SCAN] already ingested for topic '%s' → skip ingest", topic_key)

    if dedup_globs and not skip_local_ingest:
        l_jsons, l_docs, l_chunks = ingest_local_files(
            dedup_globs,
            namespace=ns,
            persist_directory=persist_dir,
            topic_slug=slug or "default",
            root_dir=current_path,
            add_web_pages_json_to_chroma=add_web_pages_json_to_chroma,
            web_page_json_to_documents=web_page_json_to_documents,
        )
        if l_docs:
            logger.info("[WEB SEARCH AGENT] ingest local refs: %s", dedup_globs)
            json_paths.extend(l_jsons)
            new_docs_preview.extend(l_docs)
            chunk_total += int(l_chunks or 0)
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
        else:
            logger.info("[LOCAL RAG] no docs matched; skip adding local:* queries")

    # [ANCHOR: VECTOR_COUNT_AFTER_LOCAL_INGEST]
    try:
        if persist_dir:
            logger.debug("[DEBUG] after local ingest, doc_count=%s", vector_count(ns, persist_dir))
        else:
            logger.debug("[DEBUG] after local ingest, doc_count skipped (persist_dir=None)")
    except Exception as e:
        logger.debug("[DEBUG] after local ingest, doc_count check failed: %s", e)

    # (선택) 로컬 프리뷰 키워드 필터
    allow_kw_env = os.getenv("LOCAL_RAG_ALLOW", "")
    if allow_kw_env.strip():
        ALLOW_KEYS = {k.strip().lower() for k in allow_kw_env.split(",") if k.strip()}
        def _relevant(d: Document) -> bool:
            txt = (d.page_content or "").lower()
            return any(k in txt for k in ALLOW_KEYS)
        before = len(new_docs_preview)
        new_docs_preview[:] = [d for d in new_docs_preview if _relevant(d)]
        after = len(new_docs_preview)
        if before != after:
            logger.info("[LOCAL RAG] preview filtered by keywords: %s → %s", before, after)

    # --- (6) 상태 갱신 & 다음 단계 -------------------------------------------
    state["references"] = merge_refs(state.get("references"), queries, new_docs_preview)

    # [ANCHOR: ROUND_URL_TALLY_COMMIT]
    _seen_by_topic[topic_key] = list(_seen_sources)
    flags["seen_sources_by_topic"] = _seen_by_topic

    logger.debug("[DEBUG] committed seen_sources_by_topic[%s] -> %s", topic_key, len(_seen_sources))

    actual = int(_round_added_urls)
    cap = int(MAX_INDEXED_PER_ROUND)
    capped = min(actual, cap) if cap > 0 else actual

    state["round_added_urls"]     = actual
    state["new_url_count"]        = actual
    state["new_url_count_round"]  = actual
    state["round_new_urls"]       = actual

    flags.setdefault("debug", {})["last_capped_new_urls"] = capped

    logger.debug(
        "[DEBUG] round_added_urls(actual)=%s | new_url_count(capped)=%s | chunk_total=%s | queries_executed=%s",
        actual, capped, chunk_total, len(queries)
    )

    n = actual

    pending.done = True
    pending.done_at = _now_str()

    if not has_pending(tasks, "vector_search_agent"):
        desc = "RAG 인덱싱을 위한 벡터 검색/검증을 수행한다."
        if queries:
            desc += f" queries={queries}"
        if json_paths:
            desc += f" json_paths={json_paths}"
        desc += f" new_urls={int(state.get('round_added_urls') or 0)}"
        tasks.append(Task(agent="vector_search_agent", done=False, description=desc, done_at=""))

    mode_label = "로컬 전용" if SKIP_WEB else "웹+로컬"
    messages.append(AIMessage(
        content=f"[WEB SEARCH AGENT] 검색 완료({len(queries)}건). JSON 저장 및 Chroma 적재/프리뷰 완료. 모드={mode_label}"
                + (f" (예: {json_paths[0]})" if json_paths else "")
    ))

    return {
        "messages": messages,
        "task_history": tasks,
        "references": state.get("references", {"queries": [], "docs": []}),
        "research_loop_active": bool(state.get("research_loop_active")),
        "research_plan": state.get("research_plan"),
        "new_url_count": int(state.get("new_url_count") or n),
        "new_url_count_round": int(state.get("new_url_count_round") or n),
        "round_new_urls": int(state.get("round_new_urls") or n),
        "round_added_urls": int(state.get("round_added_urls") or n),
        "flags": flags,
        "local_ingested_once": bool(state.get("local_ingested_once")),
    }
