# utils/citation_utils.py
from __future__ import annotations
from typing import List, Tuple
import re
from langchain_core.documents import Document
from rag_expression import RE_QUANT_NUMBER, RE_QUANT_SENT_HINTS, split_sentences_ko_en

FOOTNOTE_DEF_RE = re.compile(r"^\[\^\d+\]:", re.MULTILINE)

def _collect_reference_urls(state, max_refs: int = 20) -> List[str]:
    refs = (state.get("references") or {}).get("docs") or []
    urls: List[str] = []
    for d in refs:
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url")
        if src and (src not in urls):
            urls.append(src)
        if len(urls) >= max_refs:
            break
    return urls

def _detect_quant_sentence_indices(text: str) -> Tuple[List[int], List[str]]:
    sents = split_sentences_ko_en(text)
    idxs: List[int] = []
    for i, s in enumerate(sents):
        if RE_QUANT_NUMBER.search(s) and RE_QUANT_SENT_HINTS.search(s):
            idxs.append(i)
    return idxs, sents

def _insert_markers(sents: List[str], hit_idxs: List[int], n_markers: int) -> str:
    out: List[str] = []
    assigned = 0
    for i, s in enumerate(sents):
        if i in hit_idxs and assigned < n_markers:
            out.append(s + f"[^{assigned+1}]")
            assigned += 1
        else:
            out.append(s)
    # 문장 재조립 (간단 join)
    return " ".join(out)

def _build_footnote_defs(urls: List[str], used: int) -> str:
    lines = [f"[^{i+1}]: {urls[i]}" for i in range(min(used, len(urls)))]
    return "\n".join(lines)

def _build_reference_block(urls: List[str], used: int) -> str:
    if used <= 0:
        return ""
    lines = "\n".join(f"- {urls[i]}" for i in range(min(used, len(urls))))
    return "\n\n## 참고 자료\n" + lines

def attach_auto_citations(text: str, state) -> str:
    """
    1) 정량 문장에 [^n] 마커 자동 삽입
    2) 문서 끝에 각주 정의 + '## 참고 자료' 섹션 생성
    - 이미 각주 정의가 있으면 중복 추가하지 않음
    """
    if not text or FOOTNOTE_DEF_RE.search(text):
        return text  # 이미 각주 정의가 있으면 스킵

    urls = _collect_reference_urls(state, max_refs=20)
    if not urls:
        return text

    hit_idxs, sents = _detect_quant_sentence_indices(text)
    if not hit_idxs:
        return text

    used = min(len(hit_idxs), len(urls))
    body = _insert_markers(sents, hit_idxs, used)
    footnotes = _build_footnote_defs(urls, used)
    ref_block = _build_reference_block(urls, used)

    return body.rstrip() + "\n\n" + footnotes + ref_block + "\n"
