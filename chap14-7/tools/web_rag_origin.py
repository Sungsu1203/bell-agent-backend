# tools/web_rag.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import re
import os, json, time, io, hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, DefaultDict, Sequence
from datetime import datetime

import requests, certifi, chardet
from dotenv import load_dotenv, find_dotenv
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 💡 중앙 LLM 관리 모듈에서 임베딩 함수 임포트
from core.llm import get_embedding_model

from settings_gatekeep import (
    gatekeep_enabled,
    url_allowed,
    _normalize_host,    # 로그 요약용 (없으면 제거해도 무방)
)

from collections import defaultdict as _dd
import re as _re  # ← Naver 쿼리 간소화용

# ─────────────────────────────────────────────────────────────────────────────
# HTTPS 세션 (검증 ON)
# ─────────────────────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({"User-Agent": os.getenv("USER_AGENT", "BookWriterBot/1.0")})
session.verify = certifi.where()  # 신뢰 루트 지정

def http_get(url, **kw):
    kw.setdefault("timeout", (6, 20))
    return session.get(url, **kw)

# ---- Optional: SerpAPI ----
try:
    from serpapi import GoogleSearch  # pip install google-search-results
    _HAS_SERPAPI = True
except Exception:
    _HAS_SERPAPI = False
    logger.debug("SerpAPI not available.")

# ---- Optional: Tavily ----
try:
    from tavily import TavilyClient  # pip install tavily-python
    _HAS_TAVILY = True
except Exception:
    _HAS_TAVILY = False
    logger.debug("Tavily client not available.")

# ---- RAG (Chroma + Embeddings) ----
from langchain_chroma import Chroma

# PDF 파서
try:
    import PyPDF2 as _pypdf2
except Exception:
    _pypdf2 = None

try:
    from pdfminer.high_level import extract_text as _pdfminer_extract_text
except Exception:
    _pdfminer_extract_text = None


# =============================================================================
# Env & Paths
# =============================================================================

dotenv_path = find_dotenv(usecwd=True)
if dotenv_path:
    load_dotenv(dotenv_path, override=False)
else:
    logger.info(".env file not found: using OS environment variables only.")

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[1]))
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

_RECENTLY_CLEARED: dict[str, float] = {}
_FRESH_KEYS: set[tuple[str, str]] = set()

def _now(fmt: str = "%Y_%m%d_%H%M%S") -> str:
    return datetime.now().strftime(fmt)

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _truthy(name: str, default: Optional[str] = None) -> bool:
    raw = os.getenv(name) if default is None else os.getenv(name, default)
    v = (raw or "").strip().lower()
    return v in {"1", "true", "yes", "on"}

def _save_results(items, out_dir: Optional[Path | str] = None, *, query: Optional[str] = None) -> str:
    if out_dir is None:
        env_dir = (os.getenv("WEB_RAG_DATA_DIR", "") or "").strip()
        base_dir = Path(env_dir) if env_dir else DATA_DIR
    else:
        base_dir = Path(out_dir)

    base_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y_%m_%d_%H%M%S_%f")
    suffix = ""
    if query:
        h = hashlib.blake2b(query.encode("utf-8"), digest_size=4).hexdigest()
        suffix = f"_{h}"
    fname = f"resources_{ts}{suffix}.json"
    path = base_dir / fname
    with path.open("w", encoding="utf-8") as f:
        json.dump(items or [], f, ensure_ascii=False, indent=2)
    logger.info("[web_search] results saved → %s (items=%d)", path, len(items or []))
    return str(path)

# ─────────────────────────────────────────────────────────────────────────────
# 검색 정책/TopN (기존 키 + 신규 alias 지원)
# ─────────────────────────────────────────────────────────────────────────────
def _env_int(*names: str, default: int = 0) -> int:
    for n in names:
        v = os.getenv(n)
        if v and v.strip().isdigit():
            return int(v.strip())
    return default

def _env_str(*names: str, default: str = "") -> str:
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return default

_MIN_RESULTS_OK = _env_int("SEARCH_MIN_OK", "WEB_MIN_RESULTS_OK", default=1)
_BACKEND_PICK_POLICY = _env_str("SEARCH_POLICY", "WEB_BACKEND_PICK_POLICY", default="best_of_chain").lower()
_SEARCH_TOPN = _env_int("SEARCH_TOPN", default=10)

# ─────────────────────────────────────────────────────────────────────────────
# 로그 도우미
# ─────────────────────────────────────────────────────────────────────────────
_LOG_TOPK = int(os.getenv("LOG_TOPK", "3") or "3")
_LOG_WRAP = int(os.getenv("LOG_WRAP", "88") or "88")

def _ell(s: str, n: int = _LOG_WRAP) -> str:
    s = (s or "").replace("\n", " ").strip()
    return (s[:n-1] + "…") if len(s) > n else s

def _host_of(u: str) -> str:
    try:
        return (_normalize_host(u) or "").lower()
    except Exception:
        try:
            from urllib.parse import urlparse
            return (urlparse(u).netloc or "").lower()
        except Exception:
            return ""

# =============================================================================
# URL 정규화/디듀프/TopN
# =============================================================================
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

_TRACKING_PARAMS = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","gclid","fbclid","igsh","mc_cid","mc_eid"}

def _normalize_url(u: str) -> str:
    try:
        pu = urlparse((u or "").strip())
        host = (pu.netloc or "").replace("m.", "www.")
        path = pu.path or "/"
        qs = [(k, v) for k, v in parse_qsl(pu.query, keep_blank_values=False) if k.lower() not in _TRACKING_PARAMS]
        return urlunparse((pu.scheme or "https", host, path, "", urlencode(qs, doseq=True), ""))
    except Exception:
        return (u or "").strip()

def _dedupe_keep_order_dicts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items:
        u = _normalize_url(it.get("url") or it.get("source") or "")
        if u and u not in seen:
            seen.add(u)
            out.append(it)
    return out

def _pick_top(items: List[Dict[str, Any]], topn: int) -> List[Dict[str, Any]]:
    return items[:max(1, int(topn or 1))]

# =============================================================================
# Common helpers
# =============================================================================

def _strip_minus_tokens(q: str) -> str:
    if not q:
        return q
    return _re.sub(r"(^|\s)-\S+", " ", q).strip()

def _cap_minus_tokens(q: str, cap: int) -> str:
    if not q:
        return q
    if cap <= 0:
        return _strip_minus_tokens(q)
    toks = q.split()
    negs = [t for t in toks if t.startswith("-")]
    if len(negs) <= cap:
        return q
    keep = set(negs[:cap])
    kept = []
    for t in toks:
        if t.startswith("-") and t not in keep:
            continue
        kept.append(t)
    return " ".join(kept).strip()

def _normalize_results(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    norm: List[Dict[str, Any]] = []
    for r in (items or []):
        url = r.get("url") or r.get("source") or r.get("link") or ""
        if not url:
            continue
        norm.append({
            "title": r.get("title") or url,
            "url": url,
            "content": r.get("content") or r.get("snippet") or "",
            "raw_content": r.get("raw_content") or "",
            "source": url,
        })
    return norm

def _clean_text(txt: str) -> str:
    if not txt:
        return ""
    while "\n\n\n" in txt or "\t\t\t" in txt:
        txt = txt.replace("\n\n\n", "\n\n").replace("\t\t\t", "\t\t")
    return txt

def _looks_like_pdf_bytes(txt: str) -> bool:
    return (txt or "").lstrip().startswith("%PDF-")

def _is_block_page(txt: str) -> bool:
    t = (txt or "").lower()
    return any(k in t for k in [
        "access denied", "enable javascript", "just a moment",
        "security controls triggered", "captcha",
    ])

def _looks_like_serialized_blob(txt: str) -> bool:
    t = txt.lower()
    markers = ["__next_data__", "window.__", "\"$\",\"html\"", "static/chunks/"]
    if any(m in t for m in markers):
        return True
    brace_ratio = (txt.count("{") + txt.count("}")) / max(1, len(txt))
    return brace_ratio > 0.02

def _append_default_negatives(q: str) -> str:
    if not q or not _truthy("WEB_APPLY_DEFAULT_NEGATIVES", default="1"):
        return q
    try:
        min_tok = int(os.getenv("WEB_DEFAULT_NEGATIVES_MIN_TOKENS", "3"))
    except Exception:
        min_tok = 3
    if min_tok and len(q.split()) < min_tok:
        return q
    if _is_naver_safe(q):
        return q
    base = (os.getenv("WEB_DEFAULT_NEGATIVES", "-행사 -세미나 -박람회") or "").strip()
    if not base:
        return q
    existing = set(q.split())
    to_add = [tok for tok in base.split() if tok and tok not in existing]
    if not to_add:
        return q
    return (q.rstrip() + " " + " ".join(to_add)).strip()

# ─────────────────────────────────────────────────────────────────────────────
# 게이트키핑
# ─────────────────────────────────────────────────────────────────────────────
def _apply_gatekeep_to_results(results: list[dict]) -> list[dict]:
    if not results or not gatekeep_enabled():
        return results
    allowed, blocked = [], []
    for r in results:
        u = (r.get("url") or r.get("source") or "").strip()
        if not u:
            continue
        if url_allowed(u):
            allowed.append(r)
        else:
            blocked.append(u)
    if blocked:
        try:
            hosts = []
            for u in blocked:
                h = _normalize_host(u)
                hosts.append(h or u)
            logger.warning("[GATEKEEP] blocked %d url(s): %s", len(blocked), ", ".join(hosts[:10]))
        except Exception:
            logger.warning("[GATEKEEP] blocked %d url(s).", len(blocked))
    return allowed

# ─────────────────────────────────────────────────────────────────────────────
# 원문 로딩: PDF/HTML
# ─────────────────────────────────────────────────────────────────────────────
def _load_web_page(url: str) -> str:
    connect_to = int(os.getenv("WEB_FETCH_TIMEOUT_CONNECT", "6"))
    read_to    = int(os.getenv("WEB_FETCH_TIMEOUT_READ", "20"))
    max_bytes  = int(os.getenv("WEB_FETCH_MAX_BYTES", "1000000"))  # 1MB

    try:
        with session.get(url, timeout=(connect_to, read_to), stream=True) as r:
            r.raise_for_status()
            buf = io.BytesIO()
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                buf.write(chunk)
                if buf.tell() >= max_bytes:
                    break
            raw = buf.getvalue()
            try:
                enc = r.encoding or chardet.detect(raw).get("encoding") or "utf-8"
            except Exception:
                enc = "utf-8"
            text = raw.decode(enc, errors="replace")
            while "\n\n\n" in text or "\t\t\t" in text:
                text = text.replace("\n\n\n", "\n\n").replace("\t\t\t", "\t\t")
            return text.strip()
    except Exception as e:
        logger.debug("requests session load failed for %s: %s", url, e)

    try:
        try:
            loader = WebBaseLoader(
                url,
                requests_kwargs={
                    "timeout": (connect_to, read_to),
                    "verify": session.verify,
                    "headers": dict(session.headers),
                },
                verify_ssl=True,
            )
        except TypeError:
            loader = WebBaseLoader(url, requests_kwargs={
                "timeout": (connect_to, read_to),
                "verify": session.verify,
                "headers": dict(session.headers),
            })
        docs = loader.load()
        txt = (docs[0].page_content if docs else "").strip()
        while "\n\n\n" in txt or "\t\t\t" in txt:
            txt = txt.replace("\n\n\n", "\n\n").replace("\t\t\t", "\t\t")
        return txt
    except Exception as e:
        logger.debug("WebBaseLoader fallback failed for %s: %s", url, e)
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# 결과 원문 보강
# ─────────────────────────────────────────────────────────────────────────────
def _enrich_raw_content(results: List[Dict[str, Any]]) -> None:
    top = int(os.getenv("WEB_SEARCH_RAW_FETCH_TOP", "5") or "5")
    if top <= 0:
        return

    budget_s = float(os.getenv("WEB_FETCH_BUDGET_SECONDS", "30"))
    t0 = time.time()

    def _is_bad_doc_text(text: str) -> bool:
        t = (text or "").lower()
        bad_markers = [
            "access denied", "enable javascript", "just a moment",
            "security controls triggered", "captcha", "forbidden"
        ]
        return any(k in t for k in bad_markers)

    for i, r in enumerate(results):
        if i >= top:
            break
        if time.time() - t0 > budget_s:
            logger.debug("raw fetch budget exceeded (>%ss) — stopping enrichment", budget_s)
            break
        if r.get("raw_content"):
            continue
        url = r.get("url")
        if not url:
            continue
        try:
            html = _load_web_page(url)
            if html and not _is_bad_doc_text(html[:2000]):
                if _looks_like_serialized_blob(html):
                    logger.debug("serialized blob detected; skip raw_content for %s", url)
                    continue
                r["raw_content"] = html
        except Exception as e:
            logger.debug("raw_content fetch failed for %s: %s", url, e)
            continue

# -----------------------------------------------------------------------------
# persist_directory 해석
# -----------------------------------------------------------------------------
def _resolve_persist_dir(namespace: str, persist_directory: Optional[str]) -> str:
    if persist_directory is not None:
        s = persist_directory.strip()
        if s:
            return s

    chroma_dir = os.getenv("CHROMA_DIR")
    if chroma_dir is not None:
        s = chroma_dir.strip()
        if s:
            p = Path(s)
            if p.name == namespace:
                return str(p)
            if p.parent.name == "chroma_store":
                return str(p.parent / namespace)
            return str(p / namespace)

    return str(DATA_DIR / "chroma_store" / namespace)

# =============================================================================
# Search backends
# =============================================================================
def _search_tavily(query: str) -> List[Dict[str, Any]]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not (_HAS_TAVILY and api_key):
        return []
    try:
        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, search_depth="advanced", include_raw_content=True)

        if isinstance(resp, dict):
            items = resp.get("results", []) or []
        else:
            items = []
            for r in getattr(resp, "results", []) or []:
                items.append(r.model_dump() if hasattr(r, "model_dump") else dict(r))

        parsed: List[Dict[str, Any]] = []
        for it in items:
            parsed.append({
                "title": it.get("title") or "",
                "url": it.get("url") or "",
                "content": (it.get("content") or "")[:2000],
                "raw_content": it.get("raw_content") or "",
                "source": it.get("url") or "",
            })
        return parsed
    except Exception as e:
        logger.warning("Tavily search failed: %s", e)
        return []

def _search_google_cse(query: str, *, num: int = 10, timeout: int = 20) -> List[Dict[str, Any]]:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_CSE_API_KEY")
    cse_id  = os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CSE_CX")
    if not (api_key and cse_id):
        return []
    try:
        gl = os.getenv("GOOGLE_CSE_GL") or os.getenv("SEARCH_GL") or "us"
        lr = os.getenv("GOOGLE_CSE_LR") or ""
        hl = os.getenv("SEARCH_HL", "en")
        num = max(1, min(int(num or 10), 10))

        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": api_key, "cx": cse_id, "q": query, "num": num, "hl": hl, "gl": gl}
        if lr:
            params["lr"] = lr

        r = http_get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json() or {}
        items = data.get("items") or []
        parsed: List[Dict[str, Any]] = []
        for it in items:
            link = it.get("link") or it.get("formattedUrl") or ""
            if not link:
                continue
            parsed.append({
                "title": it.get("title") or it.get("htmlTitle") or link,
                "url": link,
                "content": it.get("snippet") or it.get("htmlSnippet") or "",
                "raw_content": "",
                "source": link,
            })
        return parsed
    except Exception as e:
        logger.warning("Google CSE search failed: %s", e)
        return []

def _search_serpapi(query: str, *, num: int = 10, timeout: int = 20) -> List[Dict[str, Any]]:
    api_key = os.getenv("SERPAPI_API_KEY")
    if not (api_key and _HAS_SERPAPI):
        return []
    try:
        hl = os.getenv("SEARCH_HL", "en")
        gl = os.getenv("SEARCH_GL", "us")
        num = max(1, min(int(num or 10), 100))

        params = {"engine": "google", "q": query, "api_key": api_key, "num": num, "hl": hl}
        if gl:
            params["gl"] = gl

        search = GoogleSearch(params)
        res = search.get_dict() or {}
        items = (res.get("organic_results") or [])[:num]

        parsed: List[Dict[str, Any]] = []
        for it in items:
            link = it.get("link") or ""
            if not link:
                continue
            parsed.append({
                "title": it.get("title") or link,
                "url": link,
                "content": it.get("snippet") or "",
                "raw_content": "",
                "source": link,
            })
        return parsed
    except Exception as e:
        logger.warning("SerpAPI search failed: %s", e)
        return []

# ───────── Query Sanitizer ─────────
def _sanitize_query(q: str) -> str:
    if not q:
        return q
    s = q.strip()
    s = _re.sub(r"^\(\s*untitled\s*\)\s*", "", s, flags=_re.I)

    year_span_pat = r"\b((?:19|20)\d{2})\.\.((?:19|20)\d{2})\b"
    def _expand_years(m):
        y1, y2 = int(m.group(1)), int(m.group(2))
        if y2 < y1:
            y1, y2 = y2, y1
        return "(" + " OR ".join(str(y) for y in range(y1, y2 + 1)) + ")"
    s = _re.sub(year_span_pat, _expand_years, s)

    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

# ───────── Precision/Recall query shaping ─────────

def _to_google_precision(q: str) -> str:
    """Google CSE/Tavily용 정밀형: |→OR, site: 묶음 괄호화, 연도 OR trimmed, 네거티브 2개 제한"""
    s = q.strip()
    # 1) '|' → ' OR '
    s = _re.sub(r"\s*\|\s*", " OR ", s)
    # 2) site: 묶음 괄호화  ex) site:a OR site:b → (site:a OR site:b)
    def _paren_site(m):
        block = m.group(0)
        # 이미 괄호면 패스
        if block.lstrip().startswith("(") and block.rstrip().endswith(")"):
            return block
        return "(" + block.strip() + ")"
    s = _re.sub(r"(?:\s*site:\S+\s*(?:OR\s*site:\S+\s*)+)", _paren_site, s, flags=_re.I)

    # 3) (2022 OR 2023 OR 2024 ...) 과다 시 최신 1개만 유지
    def _trim_year_or(group: str, keep: int = 1) -> str:
        years = _re.findall(r"\b(19|20)\d{2}\b", group)
        if not years:
            return group
        ys = [int(y) if len(y)==4 else int('20'+y) for y in _re.findall(r"\b((?:19|20)\d{2})\b", group)]
        ys = sorted(set(ys))
        if len(ys) <= keep: 
            return group
        picked = ys[-keep:]
        return "(" + " OR ".join(str(y) for y in picked) + ")"
    s = _re.sub(r"\((?:\s*(?:19|20)\d{2}\s*(?:OR\s*)?)+\)", lambda m: _trim_year_or(m.group(0), keep=1), s)

    # 4) 네거티브 토큰 상한 2개
    s = _cap_minus_tokens(s, cap=2)
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

def _to_google_precision_alt(q: str) -> str:
    """정밀형 B: 네거티브 제거 + 핵심 키워드만 / site 묶음 유지"""
    s = _re.sub(r"(^|\s)-\S+", " ", q).strip()  # 모든 네거티브 제거
    s = _re.sub(r"\s*\|\s*", " OR ", s)
    s = _re.sub(r"\s{2,}", " ", s).strip()
    return s

def _to_naver_recall(q: str) -> str:
    """네이버 리콜형: 내부 간소화 but 더 짧게"""
    s = _simplify_for_naver(q)
    # 토큰수 5 초과 시 앞 5개로 cut
    toks = s.split()
    if len(toks) > 5:
        s = " ".join(toks[:5])
    return s

# ====== Naver 질의 간소화/스킵 판정 ======
def _simplify_for_naver(q: str) -> str:
    if not q:
        return q
    s = q
    m = _re.search(r"(종근당|벤포벨)", s)
    if m:
        s = s[m.start():]
    s = _re.sub(r"\b(overview|summary|key trends|market size|supply chain risks|policy & regulation|Korea)\b",
                lambda m: {"overview": "개요", "summary": "요약", "key trends": "주요 동향",
                           "market size": "시장 규모", "supply chain risks": "공급망 위험",
                           "policy & regulation": "정책 규제", "Korea": "한국"}.get(m.group(1).lower(), m.group(1)),
                s, flags=_re.I)
    s = s.replace('\'', ' ').replace('"', ' ').replace('/', ' ').replace('|', ' ')
    s = _re.sub(r"\s+", " ", s).strip()

    if _truthy("NAVER_TRIM_OPERATORS", default="1"):
        s = _re.sub(r"site:\S+", " ", s, flags=_re.I)
        s = _re.sub(r"filetype:\S+", " ", s, flags=_re.I)
        s = _re.sub(r"\b(OR|AND|NOT)\b", " ", s, flags=_re.I)
        s = _re.sub(r"[()]", " ", s)
        s = s.replace("..", " ")
        s = _re.sub(r"\b(event|exhibition|tickets)\b", " ", s, flags=_re.I)

    try:
        cap = int(os.getenv("NAVER_NEGATIVE_CAP", "0"))
    except Exception:
        cap = 0
    s = _cap_minus_tokens(s, cap)
    s = _re.sub(r"\s+", " ", s).strip()
    if len(s) > 200:
        s = s[:200].rstrip()
    return s

def _should_skip_naver(q: str) -> bool:
    s = _simplify_for_naver(q or "")
    if not s:
        logger.debug("[naver.skip] reason=empty-after-simplify")
        return True
    try:
        max_len = int(os.getenv("NAVER_MAX_LEN", "120"))
    except Exception:
        max_len = 120
    try:
        max_toks = int(os.getenv("NAVER_MAX_TOKENS", "8"))
    except Exception:
        max_toks = 8
    if len(s) > max_len:
        logger.debug("[naver.skip] reason=too_long len=%d max=%d q=%r", len(s), max_len, s)
        return True
    tokc = len(s.split())
    if tokc > max_toks:
        logger.debug("[naver.skip] reason=too_many_tokens tok=%d max=%d q=%r", tokc, max_toks, s)
        return True
    bad = [
        r"\b(site:|filetype:|ext:|intitle:|inurl:|cache:)\S*",
        r"[\"{}|\[\]]",
        r"\.\.",
    ]
    for pat in bad:
        if _re.search(pat, s, flags=_re.I):
            logger.debug("[naver.skip] reason=bad_pattern pattern=%r q=%r", pat, s)
            return True
    return False

def _is_naver_safe(q: str) -> bool:
    if not q:
        return False
    if len(q) > 80:
        return False
    toks = q.split()
    if len(toks) > 6:
        return False
    bad = [
        r"\b(site:|filetype:|ext:|intitle:|inurl:|cache:)\S*",
        r"[()\"{}|\[\]]",
        r"\b(AND|OR|NOT)\b",
    ]
    for pat in bad:
        if _re.search(pat, q, flags=_re.I):
            return False
    return True

# ====== 네이버(Direct) / SerpAPI(Naver) ======
def _search_naver_direct(query: str, *, num: int = 10, timeout: int = 20) -> List[Dict[str, Any]]:
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not (client_id and client_secret):
        logger.warning("Naver direct search skipped: NAVER_CLIENT_ID or SECRET not set.")
        return []
    q_naver = _simplify_for_naver(query)
    if not q_naver or len(q_naver) < 2:
        logger.info("[Naver(Direct)] skipped (empty after simplify)")
        return []
    from urllib.parse import quote
    encoded_query = quote(q_naver)
    # 웹문서 대신 뉴스엔진 사용 중(정책상 조정 가능)
    url = "https://openapi.naver.com/v1/search/news.json"
    num = max(1, min(int(num or 10), 100))
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    params = {"query": q_naver, "display": num, "start": 1, "sort": "sim"}
    logger.debug("[Naver(Direct)][query] %s (encoded: %s)", _ell(q_naver), encoded_query[:50] + "...")
    try:
        r = http_get(url, headers=headers, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json() or {}
        items = data.get("items") or []
        parsed: List[Dict[str, Any]] = []
        for it in items:
            link = it.get("link") or it.get("url") or ""
            if not link:
                continue
            parsed.append({
                "title": it.get("title") or link,
                "url": link,
                "content": it.get("description") or "",
                "raw_content": "",
                "source": link,
            })
        logger.debug("[Naver(Direct)] success. items=%d", len(parsed))
        return parsed
    except requests.exceptions.HTTPError as e:
        logger.warning("Naver(Direct) HTTP Error %s: %s (query=%s)", getattr(e.response, "status_code", "?"), getattr(e.response, "text", ""), _ell(q_naver))
        return []
    except Exception as e:
        logger.warning("Naver(Direct) search failed: %s", e)
        return []

def _search_serpapi_naver(query: str) -> list[dict]:
    api_key = (os.getenv("SERPAPI_API_KEY") or "").strip()
    if not api_key:
        return []
    q_naver = _simplify_for_naver(query)
    if not q_naver or len(q_naver) < 2:
        logger.info("[SerpAPI(Naver)] skipped (empty after simplify)")
        return []
    if _should_skip_naver(q_naver):
        logger.info("[SerpAPI(Naver)] skipped (complex after simplify): %s", _ell(q_naver))
        return []
    num = int(os.getenv("SERPAPI_NAVER_NUM", "10"))
    hl  = (os.getenv("SERPAPI_NAVER_HL") or "ko").strip()
    gl  = (os.getenv("SERPAPI_NAVER_GL") or "kr").strip()
    where = (os.getenv("SERPAPI_NAVER_WHERE") or "web").strip()
    try_others = _truthy("SERPAPI_NAVER_TRY_OTHERS", "0")
    url = "https://serpapi.com/search.json"
    logger.debug("[SerpAPI(Naver)][query] %s", _ell(q_naver))

    def _collect(data, sink: list):
        def _push(lst):
            for r in lst or []:
                link = r.get("link") or r.get("url") or ""
                if not link:
                    continue
                title = r.get("title") or ""
                snippet = r.get("snippet") or r.get("snippet_highlighted_words") or ""
                if isinstance(snippet, list):
                    snippet = " ".join(snippet)
                sink.append({"title": title, "url": link, "source": link, "snippet": snippet or ""})
        _push(data.get("organic_results"))
        if not sink: _push(data.get("web_results"))
        if not sink: _push(data.get("news_results"))
        if not sink: _push(data.get("blog_results"))

    def _req(params: dict) -> tuple[list, dict]:
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code >= 400:
                logger.warning("SerpAPI(Naver) HTTP %s (where=%s)", resp.status_code, params.get("where"))
                return [], {}
            data = resp.json() if resp.text else {}
        except Exception as e:
            logger.warning("SerpAPI(Naver) request failed: %s", e.__class__.__name__)
            return [], {}
        items: list[dict] = []
        if data.get("error"):
            logger.warning("SerpAPI(Naver) error: %s (where=%s)", data.get("error"), params.get("where"))
        sm = data.get("search_metadata") or {}
        if sm:
            logger.debug("SerpAPI(Naver) metadata: id=%s status=%s where=%s",
                         sm.get("id"), sm.get("status"), params.get("where"))
        _collect(data, items)
        return items, data

    params = {"engine":"naver","query":q_naver,"api_key":api_key,"hl":hl,"gl":gl,"where":where,"num":num}
    items, data = _req(params)
    if items:
        return items

    params2 = dict(params); params2.pop("query", None); params2["q"] = q_naver
    items, _ = _req(params2)
    if items:
        return items

    if try_others:
        for w in ("news", "blog", "cafe"):
            params3 = dict(params); params3["where"] = w
            items, _ = _req(params3)
            if items:
                return items
            params4 = dict(params2); params4["where"] = w
            items, _ = _req(params4)
            if items:
                return items

    logger.debug("SerpAPI(Naver) returned no parsable items for query=%r (where tried: %s%s)",
                 q_naver, where, ", others" if try_others else "")
    return []

# ====== Backend router & helpers =============================================
def _backend_call(backend_key: str, query: str, *, num: int = 10) -> List[Dict[str, Any]]:
    key = (backend_key or "").strip().lower()
    if key in ("google", "google_cse"):
        return _search_google_cse(query, num=num)
    if key in ("serpapi", "serpapi_google"):
        return _search_serpapi(query, num=num)
    if key in ("naver", "serpapi_naver"):
        return _search_serpapi_naver(query)
    elif key == "naver_direct":
        return _search_naver_direct(query, num=num)
    if key == "tavily":
        return _search_tavily(query)
    return []

def _normalize_backend_alias(b: str) -> str:
    b = (b or "").strip().lower()
    if b in {"google", "googlecse"}:
        return "google_cse"
    if b in {"naver", "serpapi_naver"}:
        return "serpapi_naver"
    if b in {"serpapi_google", "google_serpapi"}:
        return "serpapi"
    if b in {"tavily"}:
        return "tavily"
    if b in {"naver_direct"}:
        return "naver_direct"
    return b

def _resolve_backend_chain(engine_arg: Optional[str], *, num: int) -> list[str]:
    eng = (engine_arg or os.getenv("WEB_SEARCH_ENGINE") or "auto").strip().lower()
    if eng and eng != "auto":
        fallback = (os.getenv("SEARCH_BACKENDS") or "google_cse,naver_direct,serpapi_naver,serpapi,tavily")
        chain = [_normalize_backend_alias(eng)]
        for b in fallback.split(","):
            a = _normalize_backend_alias(b.strip())
            if a and a not in chain:
                chain.append(a)
        return chain
    env_list = (os.getenv("SEARCH_BACKENDS") or "").strip()
    if env_list:
        return [_normalize_backend_alias(s) for s in env_list.split(",") if s.strip()]
    # 기본 체인(네이버 직접 포함)
    return ["google_cse", "naver_direct", "serpapi_naver", "serpapi", "tavily"]

# =============================================================================
# Public Tool: web_search
# =============================================================================
@tool("web_search")
def web_search(
    query: str,
    *,
    engine: Optional[str] = None,  # "auto" | "tavily" | "google" | "serpapi" | "naver"
    num: int = 10,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    멀티 엔진 웹검색 (Google CSE ↔ Naver Direct/SerpAPI ↔ Tavily)
    반환: (results[list[dict]], json_path[str])
    - 결과 스키마: {title, url, content, raw_content, source}
    - ENV:
      SEARCH_POLICY=best_of_chain | first_ok
      SEARCH_MIN_OK=1
      SEARCH_TOPN=10
      SEARCH_BACKENDS=google_cse,naver_direct,serpapi_naver,serpapi,tavily
    """
    engine = (engine or os.getenv("WEB_SEARCH_ENGINE") or "auto").strip().lower()

    results: List[Dict[str, Any]] = []
    used: Optional[str] = None

    raw_query = query
    logger.info("[web_search][query] %s", _ell(raw_query))

    # (1) backend 지시어
    forced_backend = None
    m = _re.match(r"backend\s*:\s*([a-zA-Z0-9_]+)\s*;\s*(.*)", raw_query)
    if m:
        forced_backend = _normalize_backend_alias(m.group(1))
        raw_query = m.group(2).strip()
        logger.info("[backend.forced] %s (via query directive)", forced_backend)

    # (2) 표준 정규화
    base_query = _sanitize_query(raw_query)
    if base_query != raw_query:
        logger.debug("[web_search][sanitized] %s", base_query)

    # (3) 네거티브 부착(비-네이버용)
    neg_query = _append_default_negatives(base_query)

    logger.debug(
        "[web_search][env] backends=%s | policy=%s min_ok=%d topn=%d | keys: G=%s CSE=%s S=%s T=%s",
        os.getenv("SEARCH_BACKENDS"),
        _BACKEND_PICK_POLICY, _MIN_RESULTS_OK, _SEARCH_TOPN,
        "Y" if (os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_CSE_API_KEY")) else "N",
        "Y" if (os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CSE_CX")) else "N",
        "Y" if os.getenv("SERPAPI_API_KEY") else "N",
        "Y" if os.getenv("TAVILY_API_KEY") else "N",
    )

    # 체인 구성
    chain = _resolve_backend_chain(engine, num=num)
    if forced_backend:
        chain = [forced_backend] + [b for b in chain if b != forced_backend]

    try:
        _chain_preview = " → ".join(chain)
    except Exception:
        _chain_preview = str(chain)
    logger.debug("[web_search][chain] %s (policy=%s, min_ok=%d)", _chain_preview, _BACKEND_PICK_POLICY, _MIN_RESULTS_OK)

    # (A) 백엔드 실행 — backend별 query portfolio
    tried: list[tuple[str, int, list[dict]]] = []  # (backend[:variant], raw_count, results)
    for bk in chain:
        start = time.time()

        # 1) 백엔드별 쿼리 변형 포트폴리오 구성
        variants: list[tuple[str, str]] = []  # (label, query)
        if bk in ("google", "google_cse", "tavily", "serpapi"):   # 정밀형
            base_q = base_query  # sanitize 이후 원문
            q_prec_a = _to_google_precision(base_q)
            q_prec_b = _to_google_precision_alt(base_q)
            # 기본 네거티브 부착한 정밀형 A' (회귀 방지)
            q_prec_a_neg = _append_default_negatives(q_prec_a)
            variants = [("precAneg", q_prec_a_neg), ("precA", q_prec_a), ("precB", q_prec_b)]
        elif bk in ("naver", "serpapi_naver", "naver_direct"):    # 리콜형
            q_recall = _to_naver_recall(base_query)
            variants = [("recall", q_recall)]
        else:
            variants = [("default", base_query)]

        # 2) 변형들을 순차 시도
        best_res: list[dict] = []
        used_label: Optional[str] = None
        for label, q_use in variants:
            try:
                q_final = q_use  # 정밀형 함수에서 네거티브/OR 정리됨
                _res = _backend_call(bk, q_final, num=num) or []
            except Exception as e:
                logger.warning("web_search backend '%s' failed on %s: %s", bk, label, e)
                _res = []

            if _res:
                best_res = _res
                used_label = label
                if _BACKEND_PICK_POLICY == "first_ok" and len(_res) >= _MIN_RESULTS_OK:
                    break  # 이 백엔드는 성공했으니 다음 백엔드로

        dur = time.time() - start
        tried.append((f"{bk}:{used_label or 'none'}", len(best_res), best_res))
        logger.debug("[web_search][backend tried] %-18s got=%2d in %.2fs",
                    f"{bk}:{used_label or 'none'}", len(best_res), dur)

        if _BACKEND_PICK_POLICY == "first_ok" and len(best_res) >= _MIN_RESULTS_OK:
            results, used = best_res, f"{bk}:{used_label}"
            break

    # (B) 선택: best_of_chain → 합산/정규화/디듀프/TopN
    if not results:
        if _BACKEND_PICK_POLICY == "best_of_chain":
            merged: List[Dict[str, Any]] = []
            for _, _, res in tried:
                merged.extend(res or [])
            # URL 정규화 기반 디듀프 + TopN
            merged = _dedupe_keep_order_dicts(_normalize_results(merged))
            merged = _pick_top(merged, _SEARCH_TOPN)
            results = merged
            used = "merged"
            logger.debug("[backend.pick] best_of_chain → merged(%d)", len(results))
        elif tried:
            best = max(tried, key=lambda t: t[1])
            used, best_count, best_res = best[0], best[1], best[2]
            results = best_res
            logger.debug("[backend.pick] first_ok/best_of_chain fallback → %s (count=%d)", used, best_count)

    # (C) 리트라이 블록(비어있을 때만)
    if not results:
        time.sleep(0.8)
        retried: list[tuple[str, int, list[dict]]] = []
        for bk in chain:
            # C에서도 variants 구성 (A와 동일)
            if bk in ("google", "google_cse", "tavily", "serpapi"):
                q_prec_a = _to_google_precision(base_query)
                q_prec_b = _to_google_precision_alt(base_query)
                q_prec_a_neg = _append_default_negatives(q_prec_a)
                vset = [("precAneg", q_prec_a_neg), ("precA", q_prec_a), ("precB", q_prec_b)]
            elif bk in ("naver", "serpapi_naver", "naver_direct"):
                vset = [("recall", _to_naver_recall(base_query))]
            else:
                vset = [("default", base_query)]

            best_res = []
            used_label = None
            for label, q_use in vset:
                try:
                    _res = _backend_call(bk, q_use, num=num) or []
                except Exception:
                    _res = []
                if _res:
                    best_res = _res; used_label = label
                    if _BACKEND_PICK_POLICY == "first_ok" and len(_res) >= _MIN_RESULTS_OK:
                        break
            retried.append((f"{bk}:{used_label or 'none'}", len(best_res), best_res))
            if _BACKEND_PICK_POLICY == "first_ok" and len(best_res) >= _MIN_RESULTS_OK:
                results, used = best_res, f"{bk}:{used_label}(retry)"
                break
        if not results and retried:
            if _BACKEND_PICK_POLICY == "best_of_chain":
                merged = []
                for _, _, res in retried:
                    merged.extend(res or [])
                merged = _dedupe_keep_order_dicts(_normalize_results(merged))
                merged = _pick_top(merged, _SEARCH_TOPN)
                results, used = merged, "merged(retry)"
            else:
                best = max(retried, key=lambda t: t[1])
                used, _, results = f"{best[0]}(retry)", best[1], best[2]

    # (D) 최종 로그
    if results:
        logger.info("[web_search][backend] %s  | got=%d (policy=%s, min_ok=%d, topn=%d)",
                    used, len(results), _BACKEND_PICK_POLICY, _MIN_RESULTS_OK, _SEARCH_TOPN)
        lines = []
        for i, it in enumerate(results[:_LOG_TOPK], start=1):
            t = _ell(it.get("title") or it.get("name") or "(no title)")
            u = it.get("url") or it.get("source") or it.get("link") or ""
            lines.append(f"  {i:>2}. {t}\n      └─ {_host_of(u)} :: {u}")
        logger.info("[web_search][top%d]\n%s", min(_LOG_TOPK, len(results)), "\n".join(lines))

    # (E) 게이트키핑/원문 보강/저장 (TopN 유지)
    results = _apply_gatekeep_to_results(results)
    results = _pick_top(results, _SEARCH_TOPN)
    _enrich_raw_content(results)
    path = _save_results(results, query=raw_query)

    logger.info("[web_search] backend=%s, results=%d, saved=%s", used, len(results), path)
    return results, path


# =============================================================================
# RAG: Documents conversion & Chroma ingestion/retrieval
# =============================================================================

def _resolve_ns(
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> str:
    if collection_name and collection_name.strip():
        return collection_name.strip()
    if namespace and namespace.strip():
        return namespace.strip()
    env_ns = (os.getenv("CHROMA_NAMESPACE") or "").strip()
    if env_ns:
        return env_ns
    topic_slug = (os.getenv("TOPIC_SLUG") or os.getenv("TOPIC") or "").strip()
    if topic_slug:
        return f"{topic_slug}-default"
    return "default"

# PDF/HTML 로더 유틸
import re as _re2
_PDF_URL_RE = _re2.compile(r"\.pdf($|\?)|filedownload|filedown(type)?=|/fileDown|/download", _re2.I)

def _looks_like_pdf_url(url: str) -> bool:
    return bool(_PDF_URL_RE.search(url or ""))

PDF_HEADERS = {"Accept": "application/pdf"}

def _fetch_binary(url: str, timeout: int = 20) -> bytes:
    r = requests.get(url, headers=PDF_HEADERS, timeout=timeout, stream=True)
    r.raise_for_status()
    return r.content

def _pdf_bytes_to_text(data: bytes) -> str:
    """
    PDF 바이트 → 텍스트
    - 환경변수:
      WEB_PDF_MAX_PAGES (기본 40): 앞쪽 N페이지까지만 추출
      WEB_PDF_MAX_CHARS (기본 200000): 추출 텍스트를 최대 N자까지 제한
    - 참고: 다운로드 바이트 가드는 상위 단계(HTTP fetch)에서 WEB_FETCH_MAX_BYTES로 처리
    """
    try:
        max_pages = int(os.getenv("WEB_PDF_MAX_PAGES", "40") or "40")
    except Exception:
        max_pages = 40
    try:
        max_chars = int(os.getenv("WEB_PDF_MAX_CHARS", "200000") or "200000")
    except Exception:
        max_chars = 200000

    # 1) PyPDF2 우선 경로 (페이지 단위 제어가 쉬움)
    if _pypdf2 is not None:
        try:
            reader = _pypdf2.PdfReader(io.BytesIO(data))
            # 암호화 PDF 처리 시도 (빈 패스워드)
            try:
                if getattr(reader, "is_encrypted", False):
                    reader.decrypt("")
            except Exception:
                pass

            n = min(max_pages, len(reader.pages))
            out_parts = []
            total_len = 0
            for i in range(n):
                try:
                    txt = reader.pages[i].extract_text() or ""
                except Exception:
                    txt = ""
                if not txt:
                    continue
                out_parts.append(txt)
                total_len += len(txt)
                if max_chars > 0 and total_len >= max_chars:
                    break

            text = ("\n".join(out_parts)).strip()
            if text:
                if max_chars > 0 and len(text) > max_chars:
                    text = text[:max_chars]
                return text
        except Exception as e:
            logger.debug("PyPDF2 extract failed; fallback to pdfminer: %s", e)

    # 2) pdfminer.six 폴백 (page_numbers로 앞쪽 N페이지만)
    if _pdfminer_extract_text is not None:
        try:
            # pdfminer는 page_numbers 인자로 추출 페이지를 제한할 수 있음
            text = _pdfminer_extract_text(io.BytesIO(data), page_numbers=list(range(max_pages))) or ""
            text = text.strip()
            if max_chars > 0 and len(text) > max_chars:
                text = text[:max_chars]
            return text
        except Exception as e:
            logger.debug("pdfminer extract failed: %s", e)

    # 3) 전부 실패
    return ""

def _load_html_as_text(url: str, timeout: int = 20) -> str:
    r = session.get(url, timeout=timeout, headers=session.headers, verify=session.verify)
    r.raise_for_status()
    html = r.text
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        import re
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s{2,}", " ", text)
        return text.strip()

def web_results_to_documents(results: Sequence[Dict[str, Any]]) -> List[Document]:
    from urllib.parse import urlparse, unquote
    docs: List[Document] = []

    def _guess_content_type_from_path(path: str, default: str = "text/plain") -> str:
        ext = Path(path).suffix.lower()
        if ext == ".pdf":
            return "application/pdf"  # 추출 텍스트지만 출처 힌트
        if ext in (".html", ".htm"):
            return "text/html"
        if ext in (".pptx", ".xlsx", ".docx"):
            return "application/vnd.openxmlformats-officedocument"  # generic hint
        if ext in (".txt", ".md", ".markdown"):
            return "text/plain"
        return default

    for item in results or []:
        url: str = (item.get("url") or item.get("source") or "").strip()
        title: str = (item.get("title") or "").strip()
        item_content: str = (item.get("content") or "").strip()
        raw_content: str = (item.get("raw_content") or "").strip()

        if not url:
            # URL이 없어도 content가 있으면 받아들임(희귀 케이스)
            if item_content:
                docs.append(Document(
                    page_content=item_content,
                    metadata={"source": "", "title": title or "(local)", "content_type": "text/plain"}
                ))
            continue

        try:
            parsed = urlparse(url)
            scheme = (parsed.scheme or "").lower()
            # 프래그먼트(#...) 제거한 정규 URL (PDF 판별/요청용)
            url_no_frag = url.split("#", 1)[0]

            # ── 1) 로컬 파일(file://) → 네트워크 요청 금지, content를 그대로 사용 ──
            if scheme == "file":
                # content가 반드시 있어야 함( local_rag 가 이미 추출함 )
                if not item_content:
                    logger.debug("file:// url but empty content; skip: %s", url)
                    continue
                file_path = unquote(parsed.path or "")
                ctype = _guess_content_type_from_path(file_path, default="text/plain")
                docs.append(Document(
                    page_content=item_content,
                    metadata={
                        "source": url,
                        "title": title or (Path(file_path).name if file_path else "Local File"),
                        "content_type": ctype,
                    },
                ))
                continue

            # ── 2) raw_content가 있으면 우선 활용(네트워크 무요청) ──
            if raw_content:
                # raw_content는 보통 HTML 텍스트. 태그 제거 후 사용.
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(raw_content, "lxml")
                    for tag in soup(["script", "style", "noscript"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n")
                    text = re.sub(r"[ \t]+", " ", text)
                    text = re.sub(r"\n{3,}", "\n\n", text).strip()
                except Exception:
                    # 최소 폴백
                    text = re.sub(r"<[^>]+>", " ", raw_content)
                    text = re.sub(r"\s{2,}", " ", text).strip()
                if text:
                    docs.append(Document(
                        page_content=text,
                        metadata={
                            "source": url,
                            "title": title or "Web",
                            "content_type": "text/html",
                        },
                    ))
                    continue  # 이 항목 처리 완료

            # ── 3) HTTP/HTTPS: PDF 의심 → 바이너리 로더 시도, 실패 시 HTML 폴백 ──
            if _looks_like_pdf_url(url_no_frag):
                try:
                    pdf_bytes = _fetch_binary(url_no_frag)
                    pdf_text = _pdf_bytes_to_text(pdf_bytes)
                    if pdf_text:
                        docs.append(Document(
                            page_content=str(pdf_text),
                            metadata={"source": url, "title": title or "PDF", "content_type": "application/pdf"},
                        ))
                        continue
                except Exception as e:
                    logger.debug("[web_rag] PDF fetch/parse failed; fallback to HTML: %s", e)

            # ── 4) HTML 로더 ──
            html_text = _load_html_as_text(url_no_frag)
            if html_text:
                docs.append(Document(
                    page_content=str(html_text),
                    metadata={"source": url, "title": title or "Web", "content_type": "text/html"},
                ))
                continue

            # ── 5) 마지막 폴백: 아이템의 content라도 사용 ──
            if item_content:
                docs.append(Document(
                    page_content=item_content,
                    metadata={"source": url, "title": title or "Web", "content_type": "text/plain"},
                ))

        except Exception as e:
            logger.warning("web_results_to_documents item fail (%s): %s", url, e)

    logger.debug("web_results_to_documents: %d docs built", len(docs))
    return docs


def web_page_json_to_documents(json_file: str) -> List[Document]:
    if not os.path.exists(json_file):
        logger.debug("web_page_json_to_documents: file not found %s", json_file)
        return []

    def _flex_load(path: str):
        txt = Path(path).read_text(encoding="utf-8")
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
            for k in ("results", "items", "data"):
                v = data.get(k)
                if isinstance(v, list):
                    return v
            return [data]
        return []

    try:
        resources = _flex_load(json_file) or []
    except Exception as e:
        logger.warning("web_page_json_to_documents: load failed for %s: %s", json_file, e)
        resources = []

    docs = web_results_to_documents(resources)
    logger.info("web_page_json_to_documents: %d docs from %s", len(docs), json_file)
    return docs


# ---- Vector store cache (persist_dir, collection) ----
_VS_CACHE: Dict[Tuple[str, str], Chroma] = {}
_CLEARED_ONCE_KEYS: set[tuple[str, str]] = set()

def _default_chroma_dir(namespace: str) -> str:
    return _resolve_persist_dir(namespace, persist_directory=None)

def _resolve_ns_for_docs(base_ns: str, is_web: Optional[bool]) -> tuple[str, bool]:
    """
    split NS 모드라면 (CHROMA_NAMESPACE_WEB/LOCAL 존재) 웹/로컬에 맞게 NS를 바꿔 주고,
    아니면 base_ns 그대로 반환.
    return: (ns, is_split)
    """
    ns_web = (os.getenv("CHROMA_NAMESPACE_WEB") or "").strip()
    ns_loc = (os.getenv("CHROMA_NAMESPACE_LOCAL") or "").strip()
    if ns_web and ns_loc and is_web is not None:
        return (ns_web if is_web else ns_loc), True
    return base_ns, False

def _is_web_source(meta: dict) -> Optional[bool]:
    """
    문서 메타에서 source 스킴을 보고 web/local 추정.
    - http/https → True
    - file:// 또는 로컬 경로 힌트 → False
    - 판단 불가 → None (split 모드면 base_ns로 저장)
    """
    src = (meta or {}).get("source") or ""
    s = src.strip().lower()
    if s.startswith("http://") or s.startswith("https://"):
        return True
    if s.startswith("file://"):
        return False
    # Windows 경로 힌트 (선택)
    if re.match(r"^[a-z]:[\\/]", s) or s.startswith("\\\\"):
        return False
    return None


def clear_vector_store(namespace: Optional[str] = None, persist_directory: Optional[str] = None) -> str:
    import shutil, stat, gc, time as _t

    ns = _resolve_ns(namespace=namespace, collection_name=None)
    pd = _resolve_persist_dir(ns, persist_directory)

    if (namespace is None and persist_directory is None) and os.getenv("ALLOW_GLOBAL_CLEAR", "0") != "1":
        logger.info("[INIT] clear_vector_store skipped (global clear disabled). ns='%s' dir='%s'", ns, pd)
        return pd

    vs = _VS_CACHE.pop((pd, ns), None)
    try:
        client = getattr(vs, "_client", None)
        for meth in ("persist", "reset", "teardown", "close", "stop", "shutdown"):
            fn = getattr(client, meth, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        _VS_CACHE.clear()
    except Exception:
        pass
    try:
        del vs  # type: ignore
    except Exception:
        pass
    gc.collect()
    _t.sleep(0.15)

    def _on_rm_error(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    ok = False
    for i in range(6):
        try:
            if os.path.isdir(pd):
                shutil.rmtree(pd, onerror=_on_rm_error)
            ok = True
            break
        except Exception:
            _t.sleep(0.2 * (i + 1))

    if not ok:
        try:
            if os.path.isdir(pd):
                quarantine = f"{pd}.quarantine_{int(_t.time())}"
                os.replace(pd, quarantine)
                logger.debug("[INIT] vector store quarantined → %s", quarantine)
            ok = True
        except Exception as e:
            logger.warning("[INIT] clear_vector_store failed(final): %s", e)

    try:
        os.makedirs(pd, exist_ok=True)
    except Exception as e:
        logger.warning("[INIT] re-create dir failed: %s", e)

    try:
        _FRESH_KEYS.add((pd, ns))
    except Exception:
        pass

    logger.info("[INIT] vector store cleared → ns='%s' dir='%s'", ns, pd)
    return pd

def ensure_vector_store_cleared_once(
    namespace: Optional[str] = None,
    persist_directory: Optional[str] = None,
) -> bool:
    if not (_truthy("CLEAR_ON_FIRST_VECTOR", default=None) or _truthy("CLEAR_CHROMA_ON_START", default=None)):
        return False

    ns = _resolve_ns(namespace=namespace, collection_name=None)
    pd = _resolve_persist_dir(ns, persist_directory)
    key = (pd, ns)

    if key in _CLEARED_ONCE_KEYS:
        logger.debug("[INIT] clear_once skipped (already cleared): ns='%s' dir='%s'", ns, pd)
        return False

    clear_vector_store(namespace=ns, persist_directory=pd)
    _CLEARED_ONCE_KEYS.add(key)
    logger.info("[INIT] vector store cleared once (ns='%s', dir='%s')", ns, pd)
    return True

def _get_embeddings(embedding=None):
    return embedding or get_embedding_model()

def _get_vs(collection_name: str, persist_directory: str, embedding=None) -> Chroma:
    key = (persist_directory, collection_name)
    vs = _VS_CACHE.get(key)
    if vs is None:
        vs = Chroma(
            collection_name=collection_name,
            persist_directory=persist_directory,
            embedding_function=_get_embeddings(embedding),
        )
        _VS_CACHE[key] = vs
        logger.debug("Chroma instance created (collection=%s, dir=%s)", collection_name, persist_directory)
    return vs

def split_documents(documents: List[Document], *, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None) -> List[Document]:
    cs = int(os.getenv("RAG_CHUNK_CHARS", "2400")) if chunk_size is None else int(chunk_size)
    ov = int(os.getenv("RAG_CHUNK_OVERLAP", "200")) if chunk_overlap is None else int(chunk_overlap)
    cs = max(300, min(cs, 6000))
    ov = max(0, min(ov, int(cs * 0.5)))
    splitter = RecursiveCharacterTextSplitter(chunk_size=cs, chunk_overlap=ov)
    return splitter.split_documents(documents)

def _approx_tokens(s: str) -> int:
    return max(1, len(s or "") // 4)

def _batched_add(
    vs: Chroma,
    splits: List[Document],
    ids: Optional[List[str]] = None,
    *, 
    quarantine_dir: Optional[Path] = None,
) -> int:
    MAX_TOKENS = int(os.getenv("RAG_TOKEN_BUDGET_PER_REQ", "250000"))
    MAX_BATCH  = int(os.getenv("RAG_EMBED_BATCH", os.getenv("CHROMA_MAX_BATCH", "64")))
    total_added = 0

    if quarantine_dir is None:
        try:
            base = Path(os.getenv("CHROMA_QUARANTINE_DIR", "") or (DATA_DIR / "quarantine"))
            base.mkdir(parents=True, exist_ok=True)
            quarantine_dir = base
        except Exception:
            quarantine_dir = None

    def _write_quarantine(doc: Document, doc_id: Optional[str], err: Exception) -> None:
        if quarantine_dir is None:
            return
        try:
            payload = {
                "id": doc_id,
                "metadata": getattr(doc, "metadata", None),
                "text_head": (getattr(doc, "page_content", "") or "")[:600],
                "error": str(err),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
            qf = quarantine_dir / f"quarantine_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
            qf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.warning("[CHROMA] quarantined bad doc → %s", qf)
        except Exception:
            logger.warning("[CHROMA] quarantine write failed")

    i = 0
    while i < len(splits):
        tok_sum, j = 0, i
        while j < len(splits) and (j - i) < MAX_BATCH:
            tok_sum += _approx_tokens(splits[j].page_content)
            if tok_sum > MAX_TOKENS and j > i:
                break
            j += 1

        def _try_range(lo: int, hi: int) -> int:
            n = hi - lo
            if n <= 0:
                return 0
            try:
                if ids:
                    vs.add_documents(splits[lo:hi], ids=ids[lo:hi])  # type: ignore[arg-type]
                else:
                    vs.add_documents(splits[lo:hi])
                return n
            except Exception as e:
                if n >= 2:
                    mid = lo + n // 2
                    return _try_range(lo, mid) + _try_range(mid, hi)
                _write_quarantine(splits[lo], ids[lo] if ids else None, e)
                return 0

        total_added += _try_range(i, j)
        i = j

    logger.info("batched_add: added %d chunks", total_added)
    return total_added

def documents_to_chroma(
    documents: List[Document],
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
    persist_directory: Optional[str] = None,
    embedding=None,
    clear: bool = False,
    verbose: bool = True,
) -> Tuple[int, int]:
    from typing import cast, DefaultDict as _DefaultDictT
    from chromadb.api.types import Where, Include
    from settings_gatekeep import url_allowed

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers (로컬)
    # ─────────────────────────────────────────────────────────────────────────
    def _is_web_source(meta: dict) -> Optional[bool]:
        """http/https → True, file:// or 로컬경로 → False, 판단불가 → None"""
        src = (meta or {}).get("source") or (meta or {}).get("url") or (meta or {}).get("file_path") or ""
        s = str(src).strip().lower()
        if s.startswith("http://") or s.startswith("https://"):
            return True
        if s.startswith("file://"):
            return False
        # Windows 로컬 경로 힌트
        if re.match(r"^[a-z]:[\\/]", s) or s.startswith("\\\\"):
            return False
        return None

    def _resolve_ns_for_docs(base_ns: str, is_web_flag: Optional[bool]) -> Tuple[str, bool]:
        """분리 모드면 -web/-local로 NS 분기, 아니면 base_ns 유지. (ns, split_applied)"""
        ns_web = (os.getenv("CHROMA_NAMESPACE_WEB") or "").strip()
        ns_loc = (os.getenv("CHROMA_NAMESPACE_LOCAL") or "").strip()
        if ns_web and ns_loc and (is_web_flag is not None):
            return (ns_web if is_web_flag else ns_loc), True
        return base_ns, False

    def _is_fresh_store(ns_eff: str, pd_eff: str, vs_eff) -> bool:
        """해당 NS/디렉토리가 비었는지 판정"""
        if (pd_eff, ns_eff) in _FRESH_KEYS:
            return True
        try:
            col = getattr(vs_eff, "_collection", None)
            cnt_fn = getattr(col, "count", None)
            if callable(cnt_fn) and cnt_fn() == 0:
                return True
        except Exception:
            pass
        try:
            p = Path(pd_eff)
            if p.exists():
                for _ in p.iterdir():
                    break
                else:
                    return True
        except Exception:
            pass
        return False

    def _clear_dir(pd_eff: str, ns_eff: str) -> None:
        """해당 NS 디렉터리 삭제/재생성 및 캐시 초기화"""
        _VS_CACHE.pop((pd_eff, ns_eff), None)
        try:
            import shutil
            if os.path.isdir(pd_eff):
                shutil.rmtree(pd_eff)
            os.makedirs(pd_eff, exist_ok=True)
            logger.info("documents_to_chroma: cleared vector store (%s, %s)", ns_eff, pd_eff)
        except Exception as e:
            logger.warning("documents_to_chroma: clear failed for ns=%s dir=%s: %s", ns_eff, pd_eff, e)

    # ─────────────────────────────────────────────────────────────────────────
    # Base NS/dir 및 분리 모드 판정
    # ─────────────────────────────────────────────────────────────────────────
    ns_base = _resolve_ns(namespace=namespace, collection_name=collection_name)
    pd_base = _resolve_persist_dir(ns_base, persist_directory)
    os.makedirs(pd_base, exist_ok=True)

    ns_web_env = (os.getenv("CHROMA_NAMESPACE_WEB") or "").strip()
    ns_loc_env = (os.getenv("CHROMA_NAMESPACE_LOCAL") or "").strip()
    split_mode = bool(ns_web_env and ns_loc_env)

    # clear=True면 대상 NS들을 모두 정리
    if clear:
        # 기본 NS
        _clear_dir(pd_base, ns_base)
        # 분리 모드면 -web/-local도 같이
        if split_mode:
            _clear_dir(_resolve_persist_dir(ns_web_env, persist_directory), ns_web_env)
            _clear_dir(_resolve_persist_dir(ns_loc_env, persist_directory), ns_loc_env)

    # ─────────────────────────────────────────────────────────────────────────
    # 1) 전처리(공통): 차단 텍스트/바이너리/직렬화 블랍 제거 + 정리
    # ─────────────────────────────────────────────────────────────────────────
    total_in_docs = len(documents or [])
    pre_docs: List[Document] = []
    skipped_block = 0
    for d in (documents or []):
        txt = getattr(d, "page_content", "") or ""
        if (not txt) or _is_block_page(txt) or _looks_like_pdf_bytes(txt) or _looks_like_serialized_blob(txt):
            skipped_block += 1
            continue
        d.page_content = _clean_text(txt)
        pre_docs.append(d)
    pre_docs_count = len(pre_docs)

    # ─────────────────────────────────────────────────────────────────────────
    # 2) 파티션: 웹/로컬/기타(판단불가)
    # ─────────────────────────────────────────────────────────────────────────
    web_docs: List[Document] = []
    loc_docs: List[Document] = []
    oth_docs: List[Document] = []
    for d in pre_docs:
        flag = _is_web_source(getattr(d, "metadata", {}) or {})
        if flag is True:
            web_docs.append(d)
        elif flag is False:
            loc_docs.append(d)
        else:
            oth_docs.append(d)

    # ─────────────────────────────────────────────────────────────────────────
    # 3) 파티션별 인덱싱 함수
    # ─────────────────────────────────────────────────────────────────────────
    def _ingest_partition(part_docs: List[Document], is_web_flag: Optional[bool], label: str) -> Tuple[int, int, int, int]:
        """
        return: (in_count, new_count, split_count, added_chunks)
        - in_count: part_docs 원본 개수
        - new_count: 게이트/중복 제외 후 실제 신규 문서 수
        - split_count: 청크 개수
        - added_chunks: 벡터 저장소에 실제 추가된 청크 수
        """
        if not part_docs:
            return (0, 0, 0, 0)

        ns_eff, _ = _resolve_ns_for_docs(ns_base, is_web_flag if split_mode else None)
        pd_eff = _resolve_persist_dir(ns_eff, persist_directory)
        os.makedirs(pd_eff, exist_ok=True)

        vs_eff = _get_vs(ns_eff, pd_eff, embedding)
        is_fresh = _is_fresh_store(ns_eff, pd_eff, vs_eff)
        if is_fresh:
            # fresh면 핸들 재생성 및 fresh 키 정리
            try:
                _VS_CACHE.pop((pd_eff, ns_eff), None)
            except Exception:
                pass
            vs_eff = _get_vs(ns_eff, pd_eff, embedding)
            try:
                _FRESH_KEYS.discard((pd_eff, ns_eff))
            except Exception:
                pass
            logger.debug("documents_to_chroma[%s]: fresh store — recreated handle (ns=%s dir=%s)", label, ns_eff, pd_eff)

        # 게이트/차단/중복 URL 계산(해당 NS 기준)
        # 1) 게이트/차단은 위 전처리에서 안 했으므로 여기서 처리
        filtered_docs: List[Document] = []
        skipped_gate = 0
        for d in part_docs:
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""
            if not url_allowed(src):
                skipped_gate += 1
                continue
            filtered_docs.append(d)

        # 2) 저장된 URL과 비교하여 신규만
        all_urls = {
            (getattr(d, "metadata", {}) or {}).get("source")
            for d in filtered_docs if (getattr(d, "metadata", {}) or {}).get("source")
        }
        stored_urls = set()
        if all_urls and not is_fresh:
            try:
                urls: list[str] = [u for u in all_urls if isinstance(u, str) and u]
                where_filter = {"source": {"$in": urls}}
                include = ["metadatas"]
                res = vs_eff._collection.get(  # type: ignore[attr-defined]
                    where=cast(Where, where_filter),
                    include=cast(Include, include),
                )
                for m in (res or {}).get("metadatas") or []:
                    if isinstance(m, dict) and m.get("source"):
                        stored_urls.add(m["source"])
            except Exception as e:
                logger.debug("chroma get(where=$in) failed(ns=%s): %s", ns_eff, e)
                try:
                    res = vs_eff._collection.get(include=["metadatas"])  # type: ignore[attr-defined]
                    for m in (res or {}).get("metadatas") or []:
                        if isinstance(m, dict) and m.get("source"):
                            stored_urls.add(m["source"])
                except Exception as e2:
                    logger.debug("chroma full metadatas get failed(ns=%s): %s", ns_eff, e2)
                    stored_urls = set()
        elif is_fresh:
            logger.debug("documents_to_chroma[%s]: fresh store detected; skip stored_urls check", label)

        new_documents: List[Document] = []
        for d in filtered_docs:
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""
            if src and (is_fresh or src not in stored_urls):
                new_documents.append(d)
            elif not src and is_fresh:
                new_documents.append(d)

        if not new_documents:
            if verbose:
                logger.info(
                    "documents_to_chroma(part:%s): no new urls | ns=%s dir=%s | in=%d gate_skipped=%d fresh=%s",
                    label, ns_eff, pd_eff, len(part_docs), skipped_gate, is_fresh
                )
            return (len(part_docs), 0, 0, 0)

        # 분할
        splits = split_documents(new_documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not splits:
            if verbose:
                logger.info(
                    "documents_to_chroma(part:%s): no splits | ns=%s dir=%s | in=%d new=%d",
                    label, ns_eff, pd_eff, len(part_docs), len(new_documents)
                )
            return (len(part_docs), len(new_documents), 0, 0)

        # ID 생성
        MAX_ID_CHARS = int(os.getenv("CHROMA_MAX_ID_CHARS", "128"))
        ids: List[str] = []
        counter: _DefaultDictT[str, int] = _dd(int)

        def _cap_id(s: str) -> str:
            if len(s) <= MAX_ID_CHARS:
                return s
            keep_tail = 12
            return s[: MAX_ID_CHARS - keep_tail] + s[-keep_tail:]

        for s in splits:
            src = (getattr(s, "metadata", {}) or {}).get("source", "")
            if src:
                base = hashlib.sha1(src.encode("utf-8", "ignore")).hexdigest()
                counter[base] += 1
                raw_id = f"{base}-{counter[base]:06d}"
            else:
                counter["__none__"] += 1
                raw_id = f"none-{counter['__none__']:06d}"
            ids.append(_cap_id(raw_id))

        # 업서트
        t0 = time.time()
        qdir = Path(os.getenv("CHROMA_QUARANTINE_DIR", "") or (Path(pd_eff) / "quarantine"))
        try:
            qdir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        try:
            added_chunks = _batched_add(vs_eff, splits, ids, quarantine_dir=qdir)
        except Exception as e:
            logger.warning("documents_to_chroma(part:%s): batched_add raised — forcing single upserts: %s", label, e)
            added_chunks = 0
            for k, doc in enumerate(splits):
                try:
                    if ids:
                        vs_eff.add_documents([doc], ids=[ids[k]])
                    else:
                        vs_eff.add_documents([doc])
                    added_chunks += 1
                except Exception as e2:
                    logger.warning("single upsert failed(part:%s) at %d: %s", label, k, e2)

        # persist
        persist_fn = getattr(vs_eff, "persist", None)
        if callable(persist_fn):
            try:
                persist_fn()
            except Exception as e:
                logger.debug("vs.persist failed(ns=%s) (ignored): %s", ns_eff, e)
        else:
            client = getattr(vs_eff, "_client", None)
            client_persist = getattr(client, "persist", None)
            if callable(client_persist):
                try:
                    client_persist()
                except Exception as e:
                    logger.debug("client.persist failed(ns=%s) (ignored): %s", ns_eff, e)

        # 요약 로그
        try:
            total_chars = sum(len(d.page_content or "") for d in splits)
            avg_len = int(total_chars / len(splits)) if splits else 0
        except Exception:
            avg_len = 0

        elapsed = time.time() - t0
        logger.info(
            "documents_to_chroma(part:%s): %d docs → %d chunks (ns=%s, dir=%s) | new=%d, splits=%d, avg_chunk_chars=%d, time=%.2fs",
            label, len(part_docs), added_chunks, ns_eff, pd_eff, len(new_documents), len(splits), avg_len, elapsed
        )
        return (len(part_docs), len(new_documents), len(splits), added_chunks)

    # ─────────────────────────────────────────────────────────────────────────
    # 4) 인덱싱 실행 (분리 모드면 웹/로컬/기타 각각, 아니면 단일로)
    # ─────────────────────────────────────────────────────────────────────────
    if split_mode:
        in_w, new_w, spl_w, add_w = _ingest_partition(web_docs, True,  "web")
        in_l, new_l, spl_l, add_l = _ingest_partition(loc_docs, False, "local")
        in_o, new_o, spl_o, add_o = _ingest_partition(oth_docs, None,  "base")
        total_added = add_w + add_l + add_o
        split_count = spl_w + spl_l + spl_o
        new_docs_count = new_w + new_l + new_o
        skipped_gate_total = None  # 파티션 내부에서만 집계, 상단 요약에선 생략
        pd_for_log = f"{pd_base} (split: web={_resolve_persist_dir(ns_web_env, persist_directory)}, local={_resolve_persist_dir(ns_loc_env, persist_directory)})"
    else:
        # 단일 NS 경로: pre_docs 전체를 base_ns로
        in_b, new_b, spl_b, add_b = _ingest_partition(pre_docs, None, "base")
        total_added = add_b
        split_count = spl_b
        new_docs_count = new_b
        pd_for_log = _resolve_persist_dir(ns_base, None)

    # ─────────────────────────────────────────────────────────────────────────
    # 5) 최종 요약 로그 & 반환
    # ─────────────────────────────────────────────────────────────────────────
    logger.info(
        ("documents_to_chroma: %d docs → %d chunks (ns=%s, dir=%s, split=%s) | "
         "in=%d, pre=%d, blocked=%d, new=%d, splits=%d"),
        total_in_docs, total_added, ns_base, pd_for_log, split_mode,
        total_in_docs, pre_docs_count, skipped_block, new_docs_count, split_count
    )
    return (total_in_docs, total_added)


def add_web_pages_json_to_chroma(
    json_file: str,
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
    persist_directory: Optional[str] = None,
    embedding=None,
    clear: bool = False,
) -> Tuple[int, int]:
    documents = web_page_json_to_documents(json_file)
    return documents_to_chroma(
        documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        namespace=namespace,
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding=(embedding or _get_embeddings()),
        clear=clear,
    )

@tool("retrieve")
def retrieve(
    query: str,
    *,
    top_k: int = 5,
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
    persist_directory: Optional[str] = None,
    embedding=None,
):
    """
    세션/주제별 Chroma 컬렉션에서 RAG 검색 (고속 경로 + 친절한 예외 메시지)
    """
    q = (query or "").strip()
    if not q:
        return []

    qL = q.lower()
    if qL.startswith("local:"):
        logger.debug("[retrieve] skip local/glob query: %s", query)
        return []
    if any(tok in q for tok in ("**\\", "**/", "\\*.", "/*.", "\\**", "/**")):
        logger.debug("[retrieve] skip glob-like query: %s", query)
        return []

    ns = _resolve_ns(namespace=namespace, collection_name=collection_name)
    pd = _resolve_persist_dir(ns, persist_directory)
    vs = _get_vs(ns, pd, embedding)

    emb_fn = getattr(vs, "_embedding_function", None) or embedding or _get_embeddings(embedding)

    try:
        q_emb = emb_fn.embed_query(q) if hasattr(emb_fn, "embed_query") else emb_fn(q)  # type: ignore
        n = max(1, int(top_k or 5))
        res = vs._collection.query(  # type: ignore[attr-defined]
            query_embeddings=[q_emb],
            n_results=n,
            include=["documents", "metadatas"],
        )

        docs_out = []
        docs = (res or {}).get("documents") or []
        metas = (res or {}).get("metadatas") or []
        if docs and isinstance(docs, list):
            rows = zip(docs[0] if docs else [], metas[0] if metas else [])
            for doc_text, meta in rows:
                text = (doc_text or "")
                if len(text) > 19000:
                    text = text[:19000]
                m = meta if isinstance(meta, dict) else {}
                docs_out.append(Document(page_content=text, metadata=m))
        logger.debug("[retrieve-fast] ns=%s dir=%s k=%d → %d docs", ns, pd, n, len(docs_out))
        return docs_out

    except Exception as e:
        emsg = (str(e) or "").lower()
        mismatch_signals = (
            "dimension" in emsg or
            ("embed" in emsg and "mismatch" in emsg) or
            ("expected" in emsg and "got" in emsg and "dimension" in emsg)
        )
        if mismatch_signals:
            raise RuntimeError(
                "Vector query failed due to a likely embedding model/dimension mismatch between "
                "ingestion and retrieval.\n\n"
                "How to fix:\n"
                "   • Ensure the SAME embedding model is used for both ingestion and retrieval.\n"
                "   • If you pass a custom `embedding=` here, it must match the one used to build this collection.\n"
                "   • Otherwise, omit `embedding` so the vector store’s existing embedding function is reused."
            ) from e

        logger.debug("[retrieve-fast] direct query failed; falling back to retriever: %s", e)

    retriever = vs.as_retriever(search_kwargs={"k": max(1, int(top_k or 5))})
    results = retriever.invoke(q)
    out = []
    for d in (results or []):
        text = d.page_content or ""
        if len(text) > 19000:
            text = text[:19000]
        d.page_content = text
        out.append(d)
    logger.debug("[retrieve-fallback] ns=%s dir=%s k=%d → %d docs", ns, pd, top_k, len(out))
    return out

# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "web_search",
    "web_results_to_documents",
    "web_page_json_to_documents",
    "documents_to_chroma",
    "add_web_pages_json_to_chroma",
    "retrieve",
    "clear_vector_store",
    "ensure_vector_store_cleared_once",
    "_default_chroma_dir",
]
