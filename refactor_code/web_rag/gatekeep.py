from typing import List, Dict, Any
from settings_gatekeep import gatekeep_enabled, url_allowed, _normalize_host
import logging
logger = logging.getLogger(__name__)

def apply_gatekeep(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not results or not gatekeep_enabled(): return results
    allowed, blocked = [], []
    for r in results:
        u = (r.get("url") or r.get("source") or "").strip()
        if not u: continue
        (allowed if url_allowed(u) else blocked).append(r if url_allowed(u) else u)
    if blocked:
        try:
            hosts = [(_normalize_host(u) or u) for u in blocked]
            logger.warning("[GATEKEEP] blocked %d url(s): %s", len(blocked), ", ".join(hosts[:10]))
        except Exception:
            logger.warning("[GATEKEEP] blocked %d url(s).", len(blocked))
    return [r for r in results if url_allowed(r.get("url") or r.get("source") or "")]
