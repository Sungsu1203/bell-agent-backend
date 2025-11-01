from typing import List, Dict, Any
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

_TRACK = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","gclid","fbclid","igsh","mc_cid","mc_eid"}

def normalize_url(u: str) -> str:
    pu = urlparse((u or "").strip())
    host = (pu.netloc or "").replace("m.", "www.")
    path = pu.path or "/"
    qs = [(k, v) for k, v in parse_qsl(pu.query) if k.lower() not in _TRACK]
    return urlunparse((pu.scheme or "https", host, path, "", urlencode(qs, doseq=True), ""))

def dedupe_keep_order(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items:
        u = normalize_url(it.get("url") or it.get("source") or "")
        if u and u not in seen:
            seen.add(u); out.append(it)
    return out

def normalize_results(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in (items or []):
        url = r.get("url") or r.get("source") or r.get("link") or ""
        if url:
            out.append({
                "title": r.get("title") or url,
                "url": url,
                "content": r.get("content") or r.get("snippet") or "",
                "raw_content": r.get("raw_content") or "",
                "source": url,
            })
    return out
