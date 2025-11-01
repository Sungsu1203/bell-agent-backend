from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from typing import Iterable, Set, MutableMapping, Mapping, Sequence, Any, Final, cast
from pathlib import Path
from urllib.parse import urlparse
import os, re, time, json, glob, shutil, hashlib
import concurrent.futures as cf

from core.state_types import State, References
from core.paths import current_path, now_str as _now_str, research_resources_dir
from core.models import Task
from utils.sanitize import sanitize_state
from utils.writer_scheduler import schedule_writer_if_needed
from utils.rag_utils import merge_refs, vector_count
from prompts import get_web_search_prompt
from utils.tasks import has_pending, iter_tool_calls, HumanMessage, AIMessage
from utils.outline import get_topic_outline_text
import core.config as config
from utils.forced_queries import extract_forced_queries_from_messages
from settings_gatekeep import gatekeep_enabled, get_allowed_domains
from settings_gatekeep import url_allowed as _allowed
from tools.web_rag.search import web_search
from tools.web_rag.ingest import (
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    _default_chroma_dir,
)
from utils.query_filters import clean_seed as _clean_seed
from tools.local_rag import ingest_local_files
from core.llm import get_llm


def web_search_agent(state: State):
    logger.info("============ WEB SEARCH AGENT ============")

    llm = get_llm()
    state = sanitize_state(state)

    # === NS + Persist Dir (Calculated once) ===
    topic_slug = (state.get("topic_slug") or config.CFG.TOPIC_SLUG or "default").strip()
    env_ns = (config.CFG.CHROMA_NAMESPACE or "").strip()
    ns = env_ns or f"{topic_slug}-default"
    persist_dir = _default_chroma_dir(ns)

    # Record in state (type safety: flags.chroma.*)
    flags = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    chroma = cast(MutableMapping[str, Any], flags.setdefault("chroma", {}))
    chroma["ns"] = ns
    chroma["dir"] = persist_dir

    logger.info("[web_search] ns=%s (CHROMA_NAMESPACE=%r, topic_slug=%r)", ns, env_ns, topic_slug)
    logger.info("[web_search] persist_dir(default_resolve)=%s", persist_dir)

    # --- (1) Get Task ------------------------------------------------------
    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("Task history is empty.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "web_search_agent"), None)
    if pending is None:
        raise ValueError(f"web_search_agent pending task missing. Last task: {tasks[-1]}")

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
    mission = (pending.description or "").strip()

    inputs = {
        "mission": mission,
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

    MAX_INDEXED_PER_ROUND = config.CFG.MAX_INDEXED_PER_ROUND
    MAX_SEARCH_QUERIES_PER_ROUND = config.CFG.MAX_SEARCH_QUERIES_PER_ROUND
    SKIP_WEB = config.CFG.SKIP_WEB_SEARCH
    if SKIP_WEB:
        logger.info("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 -> web search skipped (local RAG only).")

    chunk_total = 0  # Count of chunks indexed this round

    # [ANCHOR: VECTOR_COUNT_AFTER_INIT]
    try:
        logger.debug("[DEBUG] after init, doc_count=%s", vector_count(ns, persist_dir))
    except Exception as e:
        logger.debug("[DEBUG] after init, doc_count check failed: %s", e)

    # --- Helper: enforce next step is vector --------------------------------
    def _ensure_next_is_vector(_st: MutableMapping[str, Any]) -> None:
        _pend = list(cast(Sequence[str] | None, _st.get("pending")) or [])
        if "vector_search_agent" not in _pend:
            _pend.append("vector_search_agent")
            _st["pending"] = _pend
            logger.info("[web_search][guard] scheduled (pending) -> vector_search_agent")
        if not _st.get("next_agent"):
            _st["next_agent"] = "vector_search_agent"

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
    GATE_KEEP_SOURCES: bool = bool(getattr(config.CFG, "GATE_KEEP_SOURCES", False))
    _cfg_allowed = getattr(config.CFG, "ALLOWED_DOMAINS", set())
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
    MOVE_TIMEOUT = int(os.getenv("MOVE_TIMEOUT_SEC", "15") or "15")
    READ_TIMEOUT = int(os.getenv("READ_TIMEOUT_SEC", "15") or "15")

    def _with_watchdog(fn, *, timeout_sec: int, what: str):
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
        return _with_watchdog(lambda: _load_items(path), timeout_sec=READ_TIMEOUT, what=f"read_json({os.path.basename(path)})")

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
        for it in items:
            if not isinstance(it, dict):
                continue
            url = (it.get("url") or it.get("source") or "")
            if _allowed(url):
                filtered.append(it)
        p = Path(json_path)
        out = p.with_name(p.stem + "_filtered" + p.suffix)
        if not filtered:
            out.write_text("[]", encoding="utf-8")
            return str(out)
        out.write_text(json.dumps(filtered, ensure_ascii=False), encoding="utf-8")
        return str(out)

    # --- URL tally / cap -----------------------------------------------------
    topic_key = (topic_slug or "default")
    _seen_by_topic = flags.setdefault("seen_sources_by_topic", {})
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
        return any(k in txt for k in [
            "access denied", "enable javascript", "just a moment",
            "security controls triggered", "captcha"
        ])

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

        googleish = any(tok in norm_q for tok in ("site:", " OR ", " AND ", "(", ")"))

        ok = False
        for attempt in range(retries + 1):
            try:
                # 1) Search call
                payload = {"query": norm_q}
                if googleish:
                    payload["engine"] = "google_cse"
                t0 = time.monotonic()
                ret = web_search.invoke(payload)
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

                # 2-1) Dedup + cap (with watchdog read)
                try:
                    _items_all = _load_items_with_watchdog(json_path)
                    _seen_norm_urls = set()
                    _deduped = []
                    for it in _items_all:
                        if not isinstance(it, dict):
                            continue
                        u = (it.get("url") or it.get("source") or "").strip()
                        k = _norm_url(u)
                        if not k or k in _seen_norm_urls:
                            continue
                        _seen_norm_urls.add(k)
                        _deduped.append(it)
                    remaining = max(0, (_round_cap - _round_added_urls)) if _round_cap > 0 else len(_deduped)
                    if _round_cap > 0:
                        _deduped = _deduped[:remaining]
                    Path(json_path).write_text(json.dumps(_deduped, ensure_ascii=False), encoding="utf-8")
                    logger.debug("[web_search] dedup/cap applied: %d -> %d (remain=%s)", len(_items_all), len(_deduped), remaining if _round_cap else "∞")
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
                        _orig_count, chunk_count = _with_watchdog(_do_index, timeout_sec=INDEX_TIMEOUT, what="indexing")
                        chunk_total += int(chunk_count or 0)
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
                        new_docs_preview.append(
                            type(d)(
                                page_content=(d.page_content or "")[:500],
                                metadata={"source": src}
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
    _raw = config.CFG.LOCAL_RAG_GLOBS or ""
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

    li = flags.setdefault("local_ingested", {})
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
        logger.debug("[DEBUG] after local ingest, doc_count=%s", vector_count(ns, persist_dir))
    except Exception as e:
        logger.debug("[DEBUG] after local ingest, doc_count check failed: %s", e)

    # --- (SKIP_WEB safety) ---------------------------------------------------
    if SKIP_WEB:
        no_new_docs = (chunk_total <= 0) and (len(new_docs_preview) == 0)
        if no_new_docs:
            logger.info("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 & no new docs this round -> force vector stage")
            try:
                _ = state.get("references") or {"queries": [], "docs": []}
                state["references"] = cast(References, _)
            except Exception:
                pass
            _ensure_next_is_vector(cast(MutableMapping[str, Any], state))

    # --- Local preview allow keywords filter ---------------------------------
    allow_kw_env = config.CFG.LOCAL_RAG_ALLOW or ""
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
    state["references"] = cast(
        References,
        merge_refs(
            cast(Mapping[str, Any] | None, state.get("references")),
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

    _refs_map = cast(Mapping[str, Any] | None, cast(dict, state).get("refs"))
    _q_cnt = len(cast(Sequence[Any], (_refs_map or {}).get("queries") or []))
    _d_cnt = len(cast(Sequence[Any], (_refs_map or {}).get("docs") or []))
    logger.info("[web_search][refs] merged: q=%d, docs=%d", _q_cnt, _d_cnt)

    # Pending routing
    _pend = list(cast(Sequence[str] | None, state.get("pending")) or [])
    if "vector_search_agent" not in _pend:
        _pend.append("vector_search_agent")
        _s["pending"] = _pend
        logger.info("[web_search] scheduled (pending) -> vector_search_agent")

    # AUTO_WRITE_AFTER_RAG
    try:
        schedule_writer_if_needed(_s)
    except Exception as _e:
        logger.debug("schedule_writer_if_needed skipped: %s", _e)

    # URL tally commit
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

    state["last_resources"] = list(json_paths)
    state["indexed_chunks_round"] = int(chunk_total or 0)
    state["web_stage"] = {
        "cap": _round_cap,
        "added_urls_round": actual,
        "queries_executed": len(queries),
        "persist_dir": persist_dir,
        "namespace": ns,
    }
    flags.setdefault("debug", {})["last_capped_new_urls"] = capped

    logger.debug(
        "[DEBUG] round_added_urls(actual)=%s | new_url_count(capped)=%s | chunk_total=%s | queries_executed=%s",
        actual, capped, chunk_total, len(queries)
    )

    pending.done = True
    pending.done_at = _now_str()

    if not has_pending(tasks, "vector_search_agent"):
        desc = "Perform vector search/verification for RAG indexing."
        if queries:
            desc += f" queries={queries}"
        if json_paths:
            desc += f" json_paths={json_paths}"
        desc += f" new_urls={int(state.get('round_added_urls') or 0)}"
        tasks.append(Task(agent="vector_search_agent", done=False, description=desc, done_at=""))

    mode_label = "local-only" if SKIP_WEB else "web+local"
    messages.append(AIMessage(
        content=f"[WEB SEARCH AGENT] Search complete ({len(queries)} queries). JSON saved and Chroma ingestion/preview done. Mode={mode_label}"
                + (f" (e.g., {json_paths[0]})" if json_paths else "")
    ))
    # 명시적으로 state에 반영(프레임워크가 in-place 갱신을 기대할 가능성 고려)
    state["messages"] = messages
    state["task_history"] = tasks

    # --- FINAL Guard for vector stage transition ----------------
    try:
        _ensure_next_is_vector(cast(MutableMapping[str, Any], state))
    except Exception as _e:
        # NOTE: State TypedDict에 router_error 키를 추가했는지 확인 필요
        state["router_error"] = f"ensure_next_is_vector: {type(_e).__name__}: {str(_e)[:200]}"
        logger.critical("[web_search][FATAL] ensure_next_is_vector failed", exc_info=True)
        raise

    return {
        "messages": messages,
        "task_history": tasks,
        "references": cast(References, state.get("references", {"queries": [], "docs": []})),
        "research_loop_active": bool(state.get("research_loop_active")),
        "research_plan": state.get("research_plan"),
        "new_url_count": int(state.get("new_url_count") or actual),
        "new_url_count_round": int(state.get("new_url_count_round") or actual),
        "round_new_urls": int(state.get("round_new_urls") or actual),
        "round_added_urls": int(state.get("round_added_urls") or actual),
        "flags": flags,
        "local_ingested_once": bool(state.get("local_ingested_once")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Backward compatibility constants (snapshot at import-time)
# ─────────────────────────────────────────────────────────────────────────────
WRITER_AGENT: Final[str] = config.CFG.WRITER_AGENT
PROJECT_ROOT: Final[str] = getattr(config.CFG, "PROJECT_ROOT", "")

SEARCH_BACKENDS: Final[str] = getattr(
    config.CFG, "SEARCH_BACKENDS",
    "google_cse,naver_direct,serpapi_naver,serpapi,tavily"
)
HAS_GOOGLE_KEYS: Final[bool] = bool(getattr(config.CFG, "HAS_GOOGLE_KEYS", False))
HAS_SERPAPI: Final[bool] = bool(getattr(config.CFG, "HAS_SERPAPI", False))
HAS_TAVILY: Final[bool] = bool(getattr(config.CFG, "HAS_TAVILY", False))
MAX_INDEXED_PER_ROUND: Final[int] = int(getattr(config.CFG, "MAX_INDEXED_PER_ROUND", 200))
MAX_SEARCH_QUERIES_PER_ROUND: Final[int] = int(getattr(config.CFG, "MAX_SEARCH_QUERIES_PER_ROUND", 3))
LOCAL_RAG_ALLOW: Final[str] = getattr(config.CFG, "LOCAL_RAG_ALLOW", "")
