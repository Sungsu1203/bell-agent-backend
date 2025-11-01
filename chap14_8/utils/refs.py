# utils/refs.py — dynamic config access (v2025-10-27)
from __future__ import annotations
from typing import Mapping, Any, TYPE_CHECKING, Dict, List, Tuple, Iterable, Optional
from pathlib import Path
from urllib.parse import urlparse, urlunparse, unquote
import os
import re
import logging

logger = logging.getLogger(__name__)

# 타입 체커 전용으로만 Document 임포트 (런타임 하드 의존성 제거)
if TYPE_CHECKING:  # pragma: no cover
    from langchain_core.documents import Document  # noqa: F401

# ─────────────────────────────────────────────────────────────
# Dynamic config access (CFG → module attr → ENV → default)
# ─────────────────────────────────────────────────────────────
import core.config as config

def _get_cfg_attr(name: str, default):
    """config.CFG.<name> → config.<name> → default."""
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default


def _cfg_str(name: str, env: str, default: str) -> str:
    v = _get_cfg_attr(name, None)
    if v is not None:
        try:
            s = str(v).strip()
            if s:
                return s
        except Exception:
            pass
    return (os.getenv(env, default) or default).strip()


def _cfg_int(name: str, env: str, default: int) -> int:
    s = _cfg_str(name, env, str(default))
    try:
        return int(s)
    except Exception:
        try:
            return int(float(s))
        except Exception:
            return default


def _as_kv_map(v: Optional[Dict[str, str]] | Optional[Iterable[Tuple[str, str]]]) -> Dict[str, str]:
    if not v:
        return {}
    try:
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        return {str(k): str(val) for k, val in dict(v).items()}
    except Exception:
        return {}


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
FOOTER_HEADER_RE = re.compile(r"^\s*#{1,6}\s*참고 문헌\s*/?\s*각주\s*$", re.I | re.M)

# 키워드 → 대표 도메인 매핑(정규식)
_DEFAULT_KEYWORD_MAP: Dict[str, str] = {
    r"\bIEA\b": "iea.org",
    r"\bOECD\b": "oecd.org",
    r"\bKDI\b": "kdi.re.kr",
    r"KIET|산업연구원": "kiet.re.kr",
    r"KEEI|에너지경제연구원": "keei.re.kr",
    r"국회미래연구원|NAFI": "nafi.re.kr",
    r"KOTRA": "kotra.or.kr",
}
_KEYWORD_MAP_RAW: Dict[str, str] = _as_kv_map(_get_cfg_attr("REFS_KEYWORD_DOMAIN_MAP", None)) or _DEFAULT_KEYWORD_MAP
# 사전 컴파일
KEYWORD_MAP: List[Tuple[re.Pattern[str], str]] = [(re.compile(pat, re.I), dom) for pat, dom in _KEYWORD_MAP_RAW.items()]


def _netloc(u: str) -> str:
    try:
        if "://" not in u:
            u = "http://" + u
        return urlparse(u).netloc.lower()
    except Exception:
        return ""

# ── 내부 헬퍼들 ────────────────────────────────────────────────

def _extract_meta(doc: Any) -> dict:
    """
    refs 항목이 LangChain Document, dict, 혹은 {"metadata": {...}} 변종이어도
    {url|source, title...}를 최대한 찾아서 반환.
    """
    # dict 계열
    if isinstance(doc, dict):
        # 최상위 metadata가 dict면 우선
        md = doc.get("metadata")
        if isinstance(md, dict):
            return md
        # 아니면 doc 자체에서 url/source/title 시도
        if any(k in doc for k in ("url", "source", "title")):
            return doc  # type: ignore[return-value]
        return {}

    # 객체 계열 (Document 등)
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
           + www 제거, 기본포트(:80,:443) 제거
    - 파일경로: 소문자 + 슬래시 통일
    - "__v_xxx" 같은 버전 접미사 제거(가능할 때)
    """
    if not src:
        return ""
    s = str(src).strip()
    s = re.sub(r"__v_\d+_\d+$", "", s)

    try:
        pu = urlparse(s)
        if pu.scheme and pu.netloc:
            host = pu.netloc.lower()
            if host.endswith(":80"): host = host[:-3]
            if host.endswith(":443"): host = host[:-4]
            if host.startswith("www."): host = host[4:]
            path = pu.path or ""
            if path != "/" and path.endswith("/"):
                path = path[:-1]
            # 쿼리/프래그먼트 제거
            return urlunparse((pu.scheme.lower(), host, path, "", "", ""))
        # 로컬 경로
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
    seen_keys: set[str] = set()
    for d in refs:
        meta = _extract_meta(d)
        raw = (meta.get("url") or meta.get("source") or "").strip()
        if not raw:
            continue
        key = _canonicalize_src_for_dedup(raw)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        urls.append(raw)
        if len(urls) >= max_refs:
            break
    return urls


def _collect_footnotes_from_refs(refs: list, max_n: int) -> tuple[list[str], dict[str, int], dict[str, str]]:
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
        footnotes_lines.append(f"[^#{idx}]: {url}  ({label})".replace("^#", "^"))

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

    # queries dedup
    seen_q, dedup_q = set(), []
    for q in merged_q:
        qq = (q or "").strip()
        if qq and qq not in seen_q:
            dedup_q.append(qq); seen_q.add(qq)

    def _doc_sig(d: Any) -> str:
        # meta
        meta = _extract_meta(d)
        src = (meta.get("source") or meta.get("url") or "").strip()
        key = _canonicalize_src_for_dedup(src) or src.lower()
        # content head
        if hasattr(d, "page_content"):
            pc = getattr(d, "page_content") or ""
        elif isinstance(d, dict):
            pc = (d.get("page_content") or d.get("content") or "") or ""
        else:
            pc = ""
        head_len = int(_get_cfg_attr("DOC_SIGNATURE_HEAD_CHARS", 500))
        pc_head = " ".join(str(pc).split())[:head_len]
        return _hh.sha1(f"{key}|{pc_head}".encode("utf-8","ignore")).hexdigest()

    seen_sig, dedup_docs = set(), []
    for d in merged_d:
        try:
            sig = _doc_sig(d)
        except Exception:
            logger.debug("merge_refs: _doc_sig failed; fallback repr", exc_info=True)
            sig = repr(d)[:120]
        if sig not in seen_sig:
            dedup_docs.append(d); seen_sig.add(sig)

    logger.debug("merge_refs: queries %d->%d, docs %d->%d",
                 len(merged_q), len(dedup_q), len(merged_d), len(dedup_docs))
    return {"queries": dedup_q, "docs": dedup_docs}


def refs_preview_text(state: Mapping[str, Any], max_q: int = 5, max_docs: int = 8, snippet_len: int = 350) -> str:
    # CFG 우선 → ENV 폴백 → 인자 기본값
    max_q = _cfg_int("REFS_PREVIEW_MAX_Q", "REFS_PREVIEW_MAX_Q", max_q)
    max_docs = _cfg_int("REFS_PREVIEW_MAX_DOCS", "REFS_PREVIEW_MAX_DOCS", max_docs)
    snippet_len = _cfg_int("REFS_PREVIEW_SNIPPET", "REFS_PREVIEW_SNIPPET", snippet_len)

    refs = state.get("references", {"queries": [], "docs": []}) or {}
    qs = (refs.get("queries") or [])[:max_q]
    docs = (refs.get("docs") or [])[:max_docs]

    lines: list[str] = []
    for d in docs:
        meta = _extract_meta(d)
        src = (meta.get("source") or meta.get("url") or "unknown").strip() or "unknown"
        if hasattr(d, "page_content"):
            txt = getattr(d, "page_content") or ""
        elif isinstance(d, dict):
            txt = (d.get("page_content") or d.get("content") or "") or ""
        else:
            txt = ""
        snip = str(txt).replace("\n", " ")[:snippet_len]
        lines.append(f"- [{src}] {snip}")

    q_block = "\n".join([f"- {q}" for q in qs]) if qs else "(none)"
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
    if not gathered:
        return gathered

    state_map = dict(state or {})
    refs = (state_map.get("references") or {}).get("docs") or []
    if not refs:
        logger.debug("attach_auto_citations: no refs; skipping")
        return gathered

    # 이미 각주 블록/정의가 있으면 중복 추가 방지
    if FOOTNOTE_DEF_RE.search(gathered) or FOOTER_HEADER_RE.search(gathered):
        logger.debug("attach_auto_citations: existing footnotes detected; skipping")
        return gathered

    mode = _cfg_str("AUTO_FOOTNOTE_MODE", "AUTO_FOOTNOTE_MODE", "footer").lower()
    max_n = _cfg_int("AUTO_FOOTNOTE_MAX", "AUTO_FOOTNOTE_MAX", 12)
    logger.debug("attach_auto_citations: mode=%s, max_n=%d, refs=%d", mode, max_n, len(refs))

    # ── quant 모드 ─────────────────────────────────────────────
    if mode == "quant":
        try:
            from rag_expression import RE_QUANT_NUMBER, RE_QUANT_SENT_HINTS, split_sentences_ko_en  # type: ignore
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
            for pat, dom in KEYWORD_MAP:
                if pat.search(line):
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

    if _cfg_str("AUTO_FOOTNOTE_INLINE", "AUTO_FOOTNOTE_INLINE", "0") in {"1", "true", "yes"}:
        domain_by_key = {k: _netloc(u) for k, u in url_by_key.items()}
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for pat, dom in KEYWORD_MAP:
                if pat.search(line):
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
