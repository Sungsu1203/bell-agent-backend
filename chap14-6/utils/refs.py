# blockagi/utils/refs.py
from __future__ import annotations
from typing import Mapping, Any
from pathlib import Path
from urllib.parse import urlparse, urlunparse, unquote
from langchain_core.documents import Document
import re, hashlib

import os

__all__ = [
    "attach_auto_citations",
    "_extract_meta",
    "_canonicalize_src_for_dedup",
    "_auto_footnote_label",
    "refs_preview_text",
    "facts_block"
]

def _extract_meta(doc) -> dict:
    """
    refs 항목이 LangChain Document, dict, 혹은 {"metadata": {...}} 변종이어도
    {url|source, title...}를 최대한 찾아서 반환.
    """
    # dict 계열
    if isinstance(doc, dict):
        if ("url" in doc) or ("source" in doc) or ("metadata" in doc):
            md = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else None
            if md and (("url" in md) or ("source" in md) or ("title" in md)):
                return md
            return doc
        return doc

    # 객체 계열 (예: LangChain Document)
    meta = getattr(doc, "metadata", {}) or {}
    if isinstance(meta, dict) and ("url" not in meta and "source" not in meta):
        inner = meta.get("metadata")
        if isinstance(inner, dict):
            meta = inner
    return meta if isinstance(meta, dict) else {}

def _canonicalize_src_for_dedup(src: str | None) -> str:
    """
    URL/파일경로를 디듀프용 키로 표준화.
    - URL: scheme/netloc/path만 유지 (query/fragment 제거, 끝슬래시 정리)
    - 파일경로: 소문자 + 슬래시 통일
    - "__v_xxx" 같은 버전 접미사 제거(가능할 때)
    """
    if not src:
        return ""
    s = str(src).strip()
    # 버전 접미사 제거 시도 (__v_숫자_숫자)
    s = re.sub(r"__v_\d+_\d+$", "", s)

    try:
        pu = urlparse(s)
        if pu.scheme and pu.netloc:
            path = pu.path or ""
            if path != "/" and path.endswith("/"):
                path = path[:-1]
            return urlunparse((pu.scheme.lower(), pu.netloc.lower(), path, "", "", ""))
        # 로컬 경로로 간주
        return str(Path(s)).replace("\\", "/").lower()
    except Exception:
        return s.lower()

def _auto_footnote_label(meta: dict, url: str) -> str:
    """
    각주 라벨(제목/파일명/도메인). 너무 길면 80자로 자름.
    """
    title = (meta.get("title") or "").strip()
    if title:
        return title[:80] + ("..." if len(title) > 80 else "")

    label = ""
    if url:
        try:
            pu = urlparse(url if "://" in url else "http://" + url)
            label = unquote(Path(pu.path).name or pu.netloc)
        except Exception:
            label = Path(url).name or url
    if not label:
        label = "source"
    return label[:80] + ("..." if len(label) > 80 else "")


def merge_refs(existing: dict | None, new_queries: list[str] | None, new_docs: list | None) -> dict:
    import hashlib as _hh

    refs = existing or {}
    merged_q = list(refs.get("queries", []) or [])
    merged_d = list(refs.get("docs", []) or [])
    if new_queries:
        merged_q.extend([q for q in new_queries if q])
    if new_docs:
        merged_d.extend([d for d in new_docs if d is not None])

    seen_q, dedup_q = set(), []
    for q in merged_q:
        qq = (q or "").strip()
        if qq and qq not in seen_q:
            dedup_q.append(qq)
            seen_q.add(qq)

    def _doc_sig(d: Document) -> str:
        pc = (getattr(d, "page_content", "") or "")
        pc_head = " ".join(pc.split())[:500]
        meta = getattr(d, "metadata", {}) or {}
        src = (meta.get("source") or meta.get("url") or "").strip()
        return _hh.sha1(f"{src}|{pc_head}".encode("utf-8", "ignore")).hexdigest()

    seen_sig, dedup_docs = set(), []
    for d in merged_d:
        try:
            sig = _doc_sig(d)
        except Exception:
            sig = repr(d)[:120]
        if sig not in seen_sig:
            dedup_docs.append(d)
            seen_sig.add(sig)
    return {"queries": dedup_q, "docs": dedup_docs}

def refs_preview_text(state: Mapping[str, Any], max_q: int = 5, max_docs: int = 8, snippet_len: int = 350) -> str:
    refs = state.get("references", {"queries": [], "docs": []})
    qs = refs.get("queries", [])[:max_q]
    docs = refs.get("docs", [])[:max_docs]
    lines = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or "unknown"
        snip = (d.page_content or "")[:snippet_len].replace("\n", " ")
        lines.append(f"- [{src}] {snip}")
    q_block = "\n".join([f"- {q}" for q in qs])
    d_block = ("\n\nDocs:\n" + "\n".join(lines)) if lines else ""
    return "Queries:\n" + q_block + d_block

def facts_block(state: Mapping[str, Any]) -> str:
    """
    state['facts_ctx']를 안전하게 문자열 블록으로 변환.
    비어있으면 빈 문자열을 반환.
    """
    s = state.get("facts_ctx")
    if isinstance(s, str):
        s = s.strip()
        if s:
            return "\n\n[FACTS]\n" + s
    return ""

def attach_auto_citations(gathered: str, state: Mapping[str, Any] | None = None) -> str:
    """
    references.docs 메타데이터를 이용, 문서 하단에 각주 블록 삽입.
    - AUTO_FOOTNOTE_MAX: 최대 각주 수(기본 12)
    - AUTO_FOOTNOTE_INLINE=1: 간단 키워드 매칭으로 라인 끝에 [^n] 삽입(기본 off)
    """
    state_map = dict(state or {})
    refs = (state_map.get("references") or {}).get("docs") or []
    if not refs:
        return gathered

    text = gathered
    max_n = int(os.getenv("AUTO_FOOTNOTE_MAX", "12"))

    footnotes: list[str] = []
    seen: set[str] = set()
    index_by_key: dict[str, int] = {}
    url_by_key: dict[str, str] = {}

    for doc in refs:
        meta = _extract_meta(doc)
        url = (meta.get("url") or meta.get("source") or "").strip()
        if not url:
            continue

        key = _canonicalize_src_for_dedup(meta.get("source") or url)
        if not key or key in seen:
            continue

        seen.add(key)
        idx = len(footnotes) + 1
        index_by_key[key] = idx
        url_by_key[key] = url

        label = _auto_footnote_label(meta, url)
        footnotes.append(f"[^{idx}]: {url}  ({label})")

        if len(footnotes) >= max_n:
            break

    if not footnotes:
        return gathered

    # (옵션) 본문 인라인 [^n] 추가
    if os.getenv("AUTO_FOOTNOTE_INLINE", "0") == "1":
        def _netloc(u: str) -> str:
            try:
                if "://" not in u:
                    u = "http://" + u
                return urlparse(u).netloc.lower()
            except Exception:
                return ""

        domain_by_key = {k: _netloc(u) for k, u in url_by_key.items()}

        # 간단 키워드 → 대표 도메인 매핑 (필요시 확장)
        keyword_map = {
            r"\bIEA\b": "iea.org",
            r"\bOECD\b": "oecd.org",
            r"\bKDI\b": "kdi.re.kr",
            r"KIET|산업연구원": "kiet.re.kr",
            r"KEEI|에너지경제연구원": "keei.re.kr",
            r"국회미래연구원|NAFI": "nafi.re.kr",
            r"KOTRA": "kotra.or.kr",
        }

        lines = text.splitlines()
        for i, line in enumerate(lines):
            for pat, dom in keyword_map.items():
                if re.search(pat, line, flags=re.I):
                    # 해당 도메인을 가진 첫 각주 번호 부착
                    for k, net in domain_by_key.items():
                        if dom in net:
                            idx = index_by_key[k]
                            token = f"[^{idx}]"
                            if token not in line:
                                lines[i] = line.rstrip() + token
                            break
                    break
        text = "\n".join(lines)

    # 하단 각주 블록 추가
    text = text.rstrip() + "\n\n---\n\n### 참고 문헌 / 각주\n" + "\n".join(footnotes) + "\n"
    return text