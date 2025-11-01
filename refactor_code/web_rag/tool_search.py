from typing import List, Dict, Any, Optional, Tuple
import time, re, logging
from langchain_core.tools import tool
from .config import BACKEND_POLICY, SEARCH_MIN_OK, SEARCH_TOPN
from .logging_utils import ell, host_of
from .query import sanitize_query, append_default_negatives
from .router import resolve_backend_chain, backend_call, normalize_backend_alias
from .gatekeep import apply_gatekeep
from .fetch import enrich_raw_content
from .normalize import normalize_results, dedupe_keep_order
from .results_io import save_results

logger = logging.getLogger(__name__)

@tool("web_search")
def web_search(query: str, *, engine: Optional[str] = None, num: int = 10) -> Tuple[List[Dict[str, Any]], str]:
    raw_query = query
    logger.info("[web_search][query] %s", ell(raw_query))
    forced_backend = None
    m = re.match(r"backend\s*:\s*([a-zA-Z0-9_]+)\s*;\s*(.*)", raw_query)
    if m:
        forced_backend = normalize_backend_alias(m.group(1))
        raw_query = m.group(2).strip()
        logger.info("[backend.forced] %s", forced_backend)

    base_query = sanitize_query(raw_query)
    neg_query  = append_default_negatives(base_query)

    chain = resolve_backend_chain(engine)
    if forced_backend:
        chain = [forced_backend] + [b for b in chain if b != forced_backend]
    logger.debug("[web_search][chain] %s (policy=%s)", " → ".join(chain), BACKEND_POLICY)

    results: List[Dict[str, Any]] = []
    used: Optional[str] = None
    tried = []
    for bk in chain:
        t0 = time.time()
        q_use = base_query if bk in ("naver","serpapi_naver","naver_direct") else neg_query
        res = []
        try:
            res = backend_call(bk, q_use, num=num) or []
        except Exception as e:
            logger.warning("backend '%s' failed: %s", bk, e)
        tried.append((bk, len(res), res))
        logger.debug("[tried] %-14s got=%2d in %.2fs", bk, len(res), time.time()-t0)
        if BACKEND_POLICY == "first_ok" and len(res) >= SEARCH_MIN_OK:
            results, used = res, bk; break

    if not results:
        if BACKEND_POLICY == "best_of_chain":
            merged = []
            for _,_,res in tried: merged.extend(res or [])
            results = dedupe_keep_order(normalize_results(merged))[:SEARCH_TOPN]; used="merged"
        elif tried:
            best = max(tried, key=lambda t: t[1]); used, results = best[0], best[2]

    if not results:
        time.sleep(1.0)
        # 간단한 재시도 (동일 로직)
        for bk in chain:
            q_use = base_query if bk in ("naver","serpapi_naver","naver_direct") else neg_query
            res = backend_call(bk, q_use, num=num) or []
            if BACKEND_POLICY == "first_ok" and len(res) >= SEARCH_MIN_OK:
                results, used = res, f"{bk}(retry)"; break
        if not results:
            results, used = [], "none"

    if results:
        top_lines = []
        for i, it in enumerate(results[:3], 1):
            t = ell(it.get("title") or "(no title)")
            u = it.get("url") or it.get("source") or ""
            top_lines.append(f"  {i:>2}. {t}\n      └─ {host_of(u)} :: {u}")
        logger.info("[web_search][backend=%s] got=%d\n%s", used, len(results), "\n".join(top_lines))

    # 게이트키핑/보강/저장
    results = apply_gatekeep(results)[:SEARCH_TOPN]
    enrich_raw_content(results)
    path = save_results(results, query=raw_query)
    return results, path
