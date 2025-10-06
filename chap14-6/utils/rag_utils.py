from __future__ import annotations
from typing import Mapping, Any
from langchain_core.documents import Document
import re, hashlib
from urllib.parse import urlparse
from datetime import datetime

from utils.refs import refs_preview_text
__all__ = ["refs_preview_text"]

def merge_refs(existing: dict | None, new_queries: list[str] | None, new_docs: list | None) -> dict:
    import hashlib as _hh
    refs = existing or {}
    merged_q = list(refs.get("queries", []) or [])
    merged_d = list(refs.get("docs", []) or [])
    if new_queries: merged_q.extend([q for q in new_queries if q])
    if new_docs:    merged_d.extend([d for d in new_docs if d is not None])

    seen_q, dedup_q = set(), []
    for q in merged_q:
        qq = (q or "").strip()
        if qq and qq not in seen_q:
            dedup_q.append(qq); seen_q.add(qq)

    def _doc_sig(d: Document) -> str:
        pc = (getattr(d,"page_content","") or "")
        pc_head = " ".join(pc.split())[:500]
        meta = getattr(d,"metadata",{}) or {}
        src = (meta.get("source") or meta.get("url") or "").strip()
        return _hh.sha1(f"{src}|{pc_head}".encode("utf-8","ignore")).hexdigest()

    seen_sig, dedup_docs = set(), []
    for d in merged_d:
        try: sig = _doc_sig(d)
        except Exception: sig = repr(d)[:120]
        if sig not in seen_sig:
            dedup_docs.append(d); seen_sig.add(sig)
    return {"queries": dedup_q, "docs": dedup_docs}

def score_doc(d: Document, year_now: int | None = None) -> float:
    if year_now is None: year_now = datetime.now().year
    meta = getattr(d,"metadata",{}) or {}
    src  = (meta.get("source") or meta.get("url") or "").strip().lower()
    text = (getattr(d,"page_content","") or "")
    def _norm_domain(url: str) -> str:
        if not url: return ""
        netloc = urlparse(url).netloc or urlparse("http://"+url).netloc
        netloc = netloc.split("@")[-1].split(":")[0]
        for pref in ("www.","m.","mobile."):
            if netloc.startswith(pref): netloc = netloc[len(pref):]
        return netloc
    domain = _norm_domain(src)
    score = 0.0
    gov_edu = (domain.endswith(".go.kr") or domain.endswith(".gov")
               or domain.endswith(".ac.kr") or domain.endswith(".edu"))
    if gov_edu: score += 3
    if any(k in domain for k in ("imf.org","kostat.go","kotra.or")): score += 2
    if any(k in domain for k in ("kpmg","mckinsey","gartner","idc")): score += 1.5
    m = re.search(r"\b(20\d{2})\b", src) or re.search(r"\b(20\d{2})\b", text)
    if m:
        yr = int(m.group(1)); recency = max(0, 6 - (year_now - yr))
        score += recency * 0.2
    if any(b in text.lower() for b in ["enable javascript","captcha","access denied","just a moment"]):
        score -= 2
    return score

# def refs_preview_text(state: Mapping[str, Any], max_q=5, max_docs=8, snippet_len=350) -> str:
#     # main.py의 _refs_preview_text → 이름만 바꿔 export
#     refs = (state.get("references") or {"queries": [], "docs": []})
#     qs = refs.get("queries", [])[:max_q]
#     docs = refs.get("docs", [])[:max_docs]
#     lines = []
#     for d in docs:
#         meta = getattr(d, "metadata", {}) or {}
#         src = meta.get("source") or meta.get("url") or "unknown"
#         snip = (getattr(d, "page_content", "") or "")[:snippet_len].replace("\n", " ")
#         lines.append(f"- [{src}] {snip}")
#     q_block = "\n".join([f"- {q}" for q in qs])
#     d_block = ("\n\nDocs:\n" + "\n".join(lines)) if lines else ""
#     return "Queries:\n" + q_block + d_block

def vector_count(collection_name: str, persist_directory: str | None) -> int:
    """
    현재 Chroma persistent 디렉토리에서 collection_name 컬렉션의 문서(아이템) 개수를 반환.
    - 컬렉션이 없으면 0
    - 오류 시 -1
    """
    try:
        if not persist_directory:
            return -1
        import chromadb
        client = chromadb.PersistentClient(path=persist_directory)
        try:
            col = client.get_collection(collection_name)  # 존재 안 하면 예외
        except Exception:
            return 0
        return int(col.count())
    except Exception as e:
        print(f"[DEBUG] vector_count failed: {type(e).__name__}: {e}")
        return -1
