# utils/refs.py
from __future__ import annotations
from typing import Mapping, Any
from pathlib import Path
from urllib.parse import urlparse, urlunparse, unquote
from langchain_core.documents import Document
import os
import re

__all__ = [
    "attach_auto_citations",
    "merge_refs",
    "refs_preview_text",
    "facts_block",
    "_extract_meta",
    "_canonicalize_src_for_dedup",
    "_auto_footnote_label",
]

# ── 상수/공용 헬퍼 ──────────────────────────────────────────────
FOOTNOTE_DEF_RE = re.compile(r"^\[\^\d+\]:", re.MULTILINE)

KEYWORD_MAP: dict[str, str] = {
    r"\bIEA\b": "iea.org",
    r"\bOECD\b": "oecd.org",
    r"\bKDI\b": "kdi.re.kr",
    r"KIET|산업연구원": "kiet.re.kr",
    r"KEEI|에너지경제연구원": "keei.re.kr",
    r"국회미래연구원|NAFI": "nafi.re.kr",
    r"KOTRA": "kotra.or.kr",
}


def _netloc(u: str) -> str:
    try:
        if "://" not in u:
            u = "http://" + u
        return urlparse(u).netloc.lower()
    except Exception:
        return ""


# ── 내부 헬퍼들 ────────────────────────────────────────────────
def _extract_meta(doc) -> dict:
    """
    refs 항목이 LangChain Document, dict, 혹은 {"metadata": {...}} 변종이어도
    {url|source, title...}를 최대한 찾아서 반환.
    """
    if isinstance(doc, dict):
        if ("url" in doc) or ("source" in doc) or ("metadata" in doc):
            md = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else None
            if md and (("url" in md) or ("source" in md) or ("title" in md)):
                return md
            return doc
        return doc

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
    s = re.sub(r"__v_\d+_\d+$", "", s)  # 버전 접미사 제거

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


def _collect_reference_urls_from_refs(refs: list, max_refs: int = 20) -> list[str]:
    urls: list[str] = []
    for d in refs:
        meta = _extract_meta(d)
        src = (meta.get("source") or meta.get("url"))
        if src and (src not in urls):
            urls.append(src)
        if len(urls) >= max_refs:
            break
    return urls


def _collect_footnotes_from_refs(refs: list, max_n: int):
    """
    refs에서 고유 소스를 뽑아 각주 라인/인덱스/URL 매핑을 구성.
    반환: (footnotes_lines, index_by_key, url_by_key)
    """
    footnotes_lines: list[str] = []
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
        idx = len(footnotes_lines) + 1
        index_by_key[key] = idx
        url_by_key[key] = url

        label = _auto_footnote_label(meta, url)
        footnotes_lines.append(f"[^{idx}]: {url}  ({label})")

        if len(footnotes_lines) >= max_n:
            break

    return footnotes_lines, index_by_key, url_by_key


# ── 공개 함수들 ────────────────────────────────────────────────
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
    AUTO_FOOTNOTE_MODE:
      - "quant"   : 정량 문장 감지 → 본문 인라인 [^n] + footer
      - "domain"  : 본문에 도메인/키워드가 보이면 [^n] 인라인 + footer
      - "footer"  : (기본) 인라인 없이 footer만 생성
    """
    if not gathered:
        return gathered

    state_map = dict(state or {})
    refs = (state_map.get("references") or {}).get("docs") or []
    if not refs:
        return gathered

    if FOOTNOTE_DEF_RE.search(gathered):
        return gathered

    mode = os.getenv("AUTO_FOOTNOTE_MODE", "footer").strip().lower()
    max_n = int(os.getenv("AUTO_FOOTNOTE_MAX", "12"))

    # ── quant 모드 ─────────────────────────────────────────────
    if mode == "quant":
        try:
            from rag_expression import RE_QUANT_NUMBER, RE_QUANT_SENT_HINTS, split_sentences_ko_en
        except Exception:
            mode = "footer"
        else:
            sents = split_sentences_ko_en(gathered)
            hit_idxs = [i for i, s in enumerate(sents) if RE_QUANT_NUMBER.search(s) and RE_QUANT_SENT_HINTS.search(s)]
            if hit_idxs:
                urls = _collect_reference_urls_from_refs(refs, max_refs=max_n)
                used = min(len(hit_idxs), len(urls), max_n)
                if used > 0:
                    out_sents: list[str] = []
                    assigned = 0
                    for i, s in enumerate(sents):
                        if i in hit_idxs and assigned < used:
                            out_sents.append(s + f"[^{assigned+1}]")
                            assigned += 1
                        else:
                            out_sents.append(s)
                    body = " ".join(out_sents)
                    footnotes_str = "\n".join(f"[^{i+1}]: {urls[i]}" for i in range(used))
                    return body.rstrip() + "\n\n---\n\n### 참고 문헌 / 각주\n" + footnotes_str + "\n"

    # ── domain 모드 ────────────────────────────────────────────
    if mode == "domain":
        text = gathered
        footnotes_lines, index_by_key, url_by_key = _collect_footnotes_from_refs(refs, max_n=max_n)
        if not footnotes_lines:
            return gathered

        domain_by_key = {k: _netloc(u) for k, u in url_by_key.items()}
        domain_tokens = {d for d in domain_by_key.values() if d}

        lines = text.splitlines()
        for i, line in enumerate(lines):
            appended = False

            # (a) 라인에 실제 도메인 문자열이 등장하는 경우
            low = line.lower()
            for dom in domain_tokens:
                if dom in low:
                    for k, net in domain_by_key.items():
                        if dom in net:
                            idx = index_by_key[k]
                            token = f"[^{idx}]"
                            if token not in line:
                                lines[i] = line.rstrip() + token
                                appended = True
                            break
                if appended:
                    break
            if appended:
                continue

            # (b) 키워드 → 대표 도메인 매칭
            for pat, dom in KEYWORD_MAP.items():
                if re.search(pat, line, flags=re.I):
                    for k, net in domain_by_key.items():
                        if dom in net:
                            idx = index_by_key[k]
                            token = f"[^{idx}]"
                            if token not in line:
                                lines[i] = line.rstrip() + token
                            break
                    break

        text = "\n".join(lines)
        footer_block = "\n".join(footnotes_lines)
        return text.rstrip() + "\n\n---\n\n### 참고 문헌 / 각주\n" + footer_block + "\n"

    # ── footer(기본) 모드 ──────────────────────────────────────
    text = gathered
    footnotes_lines, index_by_key, url_by_key = _collect_footnotes_from_refs(refs, max_n=max_n)
    if not footnotes_lines:
        return gathered

    if os.getenv("AUTO_FOOTNOTE_INLINE", "0") == "1":
        domain_by_key = {k: _netloc(u) for k, u in url_by_key.items()}
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for pat, dom in KEYWORD_MAP.items():
                if re.search(pat, line, flags=re.I):
                    for k, net in domain_by_key.items():
                        if dom in net:
                            idx = index_by_key[k]
                            token = f"[^{idx}]"
                            if token not in line:
                                lines[i] = line.rstrip() + token
                            break
                    break
        text = "\n".join(lines)

    footer_block = "\n".join(footnotes_lines)
    return text.rstrip() + "\n\n---\n\n### 참고 문헌 / 각주\n" + footer_block + "\n"
