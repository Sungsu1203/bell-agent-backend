# utils/refs.py — dynamic config access (v2025-10-27)
from __future__ import annotations
from typing import Mapping, Any, TYPE_CHECKING, Dict, List, Tuple, Iterable, Optional, Sequence
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
    "attach_marker_citations",
    "build_marker_refs_map",
    "merge_refs",
    "refs_preview_text",
    "facts_block",
    "_extract_meta",
    "_canonicalize_src_for_dedup",
    "_auto_footnote_label",
    # 선택: 캐시 도입 시 무해한 리프레시 훅
    "refresh_refs",
]

# ── 상수/공용 헬퍼 ──────────────────────────────────────────────
FOOTNOTE_DEF_RE = re.compile(r"^\[\^\d+\]:", re.MULTILINE)
# 푸터 헤더 패턴은 CFG에서 커스터마이즈 가능(기본: "참고 문헌 / 각주")
def _footer_header_pattern() -> re.Pattern[str]:
    pat = _cfg_str("AUTO_FOOTNOTE_HEADER_PATTERN", "AUTO_FOOTNOTE_HEADER_PATTERN", r"^\s*#{1,6}\s*참고 문헌\s*/?\s*각주\s*$")
    try:
        return re.compile(pat, re.I | re.M)
    except Exception:
        return re.compile(r"^\s*#{1,6}\s*참고 문헌\s*/?\s*각주\s*$", re.I | re.M)

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
def _keyword_map() -> List[Tuple[re.Pattern[str], str]]:
    """CFG 반영: reload_config() 직후 최신 매핑 사용."""
    raw = _as_kv_map(_get_cfg_attr("REFS_KEYWORD_DOMAIN_MAP", None))
    base = raw or _DEFAULT_KEYWORD_MAP
    out: List[Tuple[re.Pattern[str], str]] = []
    for pat, dom in base.items():
        try:
            out.append((re.compile(pat, re.I), dom))
        except Exception:
            continue
    return out


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
            return doc 
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

    # queries dedup(대소문자/공백 정규화 보존-무시 전략)
    seen_q: set[str] = set()
    dedup_q: list[str] = []
    for q in merged_q:
        qq = (q or "").strip()
        key = qq.lower()
        if qq and key not in seen_q:
            dedup_q.append(qq); seen_q.add(key)

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


def refs_preview_text(state: Mapping[str, Any], max_q: int = 5, max_docs: int = 8, snippet_len: int = 350, numbered: bool = False) -> str:
    """
    references 를 LLM 컨텍스트로 직렬화.
    - numbered=False (default, 호환): "- [{src}] {snip}"
    - numbered=True: "- [N] {label} — {snip}"  (LLM 이 [[N]] 마커로 인용 가능하도록 인덱스 부여)
      ※ N 은 1-based, references.docs 의 등장 순서를 그대로 보존 (attach_marker_citations 와 동일 인덱싱).
    """
    # CFG 우선 → ENV 폴백 → 인자 기본값
    max_q = _cfg_int("REFS_PREVIEW_MAX_Q", "REFS_PREVIEW_MAX_Q", max_q)
    max_docs = _cfg_int("REFS_PREVIEW_MAX_DOCS", "REFS_PREVIEW_MAX_DOCS", max_docs)
    snippet_len = _cfg_int("REFS_PREVIEW_SNIPPET", "REFS_PREVIEW_SNIPPET", snippet_len)

    refs = state.get("references", {"queries": [], "docs": []}) or {}
    qs = (refs.get("queries") or [])[:max_q]
    docs = (refs.get("docs") or [])[:max_docs]

    lines: list[str] = []
    for i, d in enumerate(docs, start=1):
        meta = _extract_meta(d)
        src = (meta.get("source") or meta.get("url") or "unknown").strip() or "unknown"
        if hasattr(d, "page_content"):
            txt = getattr(d, "page_content") or ""
        elif isinstance(d, dict):
            txt = (d.get("page_content") or d.get("content") or "") or ""
        else:
            txt = ""
        snip = str(txt).replace("\n", " ")[:snippet_len]
        if numbered:
            label = _auto_footnote_label(meta, src)
            lines.append(f"- [{i}] {label} — {snip}")
        else:
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


_MARKER_RE = re.compile(r"\[\[(\d+)\]\]")


def attach_marker_citations(gathered: str, state: Mapping[str, Any] | None = None, max_n: int = 20) -> str:
    """
    §13: 본문에 박힌 [[N]] 마커를 references[N-1] 와 1:1 매칭해서 footer 정의 생성.
    - 본문 등장 순서로 번호 재할당 (첫 마커 → [[1]], 두 번째 → [[2]] ...).
      ※ LLM 이 [참고 자료 요약]의 원본 N 으로 인용했어도, 책/논문 인용 관행에 맞게
        독자 시점 1,2,3,4 순이 되도록 후처리에서 일괄 재라벨링.
    - footer 는 재할당된 번호로 출력: [^new_N]: <url>  (<label>)
    - 범위 밖 N (references 부족) 마커는 그대로 두고 footer 미포함.
    """
    if not gathered:
        return gathered

    state_map = dict(state or {})
    refs = (state_map.get("references") or {}).get("docs") or []
    if not refs:
        return gathered

    # 이미 footer 가 있으면 중복 추가 방지
    if FOOTNOTE_DEF_RE.search(gathered) or _footer_header_pattern().search(gathered):
        logger.debug("attach_marker_citations: existing footnotes detected; skipping")
        return gathered

    # 본문 등장 순서로 original N 을 모음 (중복 제거)
    upper = min(len(refs), max_n)
    order: list[int] = []
    seen: set[int] = set()
    for m in _MARKER_RE.finditer(gathered):
        try:
            n = int(m.group(1))
        except Exception:
            continue
        if n < 1 or n > upper:
            logger.debug("attach_marker_citations: skip out-of-range marker [[%d]] (refs=%d)", n, len(refs))
            continue
        if n not in seen:
            seen.add(n)
            order.append(n)

    if not order:
        logger.debug("attach_marker_citations: no [[N]] markers found in body")
        return gathered

    # original N → new N (본문 등장 순서대로 1-based 재할당)
    remap: dict[int, int] = {orig: i + 1 for i, orig in enumerate(order)}

    # 본문 치환: [[orig]] → [[new]] (범위 밖은 그대로 유지)
    def _sub(match: "re.Match[str]") -> str:
        try:
            orig = int(match.group(1))
        except Exception:
            return match.group(0)
        new_n = remap.get(orig)
        return f"[[{new_n}]]" if new_n is not None else match.group(0)

    new_body = _MARKER_RE.sub(_sub, gathered)

    # footer: new_N 오름차순으로 출력
    lines: list[str] = []
    for orig, new_n in sorted(remap.items(), key=lambda kv: kv[1]):
        doc = refs[orig - 1]
        meta = _extract_meta(doc)
        url = (meta.get("url") or meta.get("source") or "").strip()
        if not url:
            continue
        label = _auto_footnote_label(meta, url)
        lines.append(f"[^{new_n}]: {url}  ({label})")

    if not lines:
        return new_body

    footer_title = _cfg_str("AUTO_FOOTNOTE_HEADER", "AUTO_FOOTNOTE_HEADER", "### 참고 문헌 / 각주")
    return new_body.rstrip() + "\n\n---\n\n" + footer_title + "\n" + "\n".join(lines) + "\n"


def build_marker_refs_map(gathered: str, state: Mapping[str, Any] | None = None, max_n: int = 20) -> Dict[str, Dict[str, Any]]:
    """
    `attach_marker_citations` 와 동일한 [[N]] → original N → 본문 등장 순 재할당 로직을 사용하여,
    재할당된 marker(문자열) → 인용된 chunk 의 풀 메타(text/url/label/source/...) 를 만들어 반환.

    프런트 SourcePanel 의 'chunk 원본' 표시를 위한 사이드카 JSON 의 본체.
    원본 gathered (LLM 이 [[N]] 마커를 박아 보낸 직후, attach_marker_citations 호출 *전*) 에 대해 호출해야 함.
    """
    if not gathered:
        return {}

    state_map = dict(state or {})
    refs = (state_map.get("references") or {}).get("docs") or []
    if not refs:
        return {}

    upper = min(len(refs), max_n)
    order: list[int] = []
    seen: set[int] = set()
    for m in _MARKER_RE.finditer(gathered):
        try:
            n = int(m.group(1))
        except Exception:
            continue
        if n < 1 or n > upper:
            continue
        if n not in seen:
            seen.add(n)
            order.append(n)

    if not order:
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for new_idx, orig in enumerate(order, start=1):
        doc = refs[orig - 1]
        meta = _extract_meta(doc)
        url = (meta.get("url") or meta.get("source") or "").strip()
        if not url:
            continue
        label = _auto_footnote_label(meta, url)
        # chunk text 추출 — Document.page_content / dict.page_content 또는 dict.content
        if hasattr(doc, "page_content"):
            text = getattr(doc, "page_content") or ""
        elif isinstance(doc, dict):
            text = (doc.get("page_content") or doc.get("content") or "") or ""
        else:
            text = ""
        out[str(new_idx)] = {
            "marker": str(new_idx),
            "url": url,
            "label": label,
            "text": str(text),
            "source": (meta.get("source") or "").strip() or url,
            "title": (meta.get("title") or "").strip(),
        }
    return out


def attach_auto_citations(gathered: str, state: Mapping[str, Any] | None = None) -> str:
    if not gathered:
        return gathered

    state_map = dict(state or {})
    refs = (state_map.get("references") or {}).get("docs") or []
    if not refs:
        logger.debug("attach_auto_citations: no refs; skipping")
        return gathered

    # 이미 각주 블록/정의가 있으면 중복 추가 방지
    if FOOTNOTE_DEF_RE.search(gathered) or _footer_header_pattern().search(gathered):
        logger.debug("attach_auto_citations: existing footnotes detected; skipping")
        return gathered

    mode = _cfg_str("AUTO_FOOTNOTE_MODE", "AUTO_FOOTNOTE_MODE", "footer").lower()
    max_n = _cfg_int("AUTO_FOOTNOTE_MAX", "AUTO_FOOTNOTE_MAX", 12)
    logger.debug("attach_auto_citations: mode=%s, max_n=%d, refs=%d", mode, max_n, len(refs))

    # ── marker 모드 (§13): 본문 [[N]] 마커 ↔ refs 1:1 매핑 ───────
    if mode == "marker":
        return attach_marker_citations(gathered, state_map, max_n=max_n)

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
            for pat, dom in _keyword_map():
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
    # ── 참고문헌 자동 검증: 본문에서 실제 인용된 문서만 각주에 포함 ──
    _verify = bool(getattr(getattr(__import__("core.config", fromlist=["CFG"]), "CFG", None), "AUTO_FOOTNOTE_VERIFY", True))
    if _verify:
        text_lower = text.lower()
        verified_lines = []
        verified_index = {}
        verified_url = {}
        new_idx = 1
        for key, idx in index_by_key.items():
            url = url_by_key.get(key, "")
            # 1) 로컬 파일은 무조건 포함
            if url.startswith("file://"):
                verified_lines.append(footnotes_lines[idx - 1].replace(f"[^{idx}]", f"[^{new_idx}]"))
                verified_index[key] = new_idx
                verified_url[key] = url
                new_idx += 1
                continue
            # 2) 도메인이 본문에 언급된 경우 포함
            domain = _netloc(url).lower()
            if domain and domain in text_lower:
                verified_lines.append(footnotes_lines[idx - 1].replace(f"[^{idx}]", f"[^{new_idx}]"))
                verified_index[key] = new_idx
                verified_url[key] = url
                new_idx += 1
                continue
            # 3) 제목/레이블이 본문에 언급된 경우 포함
            label = _auto_footnote_label(_extract_meta(next((d for d in refs if (_canonicalize_src_for_dedup((getattr(d, "metadata", {}) or {}).get("source") or "") == key)), {})), url).lower()
            if label and len(label) > 5 and label[:20] in text_lower:
                verified_lines.append(footnotes_lines[idx - 1].replace(f"[^{idx}]", f"[^{new_idx}]"))
                verified_index[key] = new_idx
                verified_url[key] = url
                new_idx += 1
                continue
            logger.debug("[attach_auto_citations] skip unverified ref: %s", url)
        footnotes_lines = verified_lines
        index_by_key = verified_index
        url_by_key = verified_url
    if not footnotes_lines:
        return text

    if _cfg_str("AUTO_FOOTNOTE_INLINE", "AUTO_FOOTNOTE_INLINE", "0").lower() in {"1", "true", "yes"}:
        domain_by_key = {k: _netloc(u) for k, u in url_by_key.items()}
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for pat, dom in _keyword_map():
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

    footer_title = _cfg_str("AUTO_FOOTNOTE_HEADER", "AUTO_FOOTNOTE_HEADER", "### 참고 문헌 / 각주")
    footer_block = "\n".join(footnotes_lines)
    return text.rstrip() + "\n\n---\n\n" + footer_title + "\n" + footer_block + "\n"

# ─────────────────────────────────────────────────────────────
# (옵션) 캐시 무효화 훅 — 현재 구현은 per-call 조회이므로 no-op
# ─────────────────────────────────────────────────────────────
def refresh_refs() -> None:  # pragma: no cover
    """향후 lru_cache 최적화 시 cache_clear() 연결용 훅.
    현재 버전은 per-call 조회로 즉시 반영되므로 동작 없음."""
    return
