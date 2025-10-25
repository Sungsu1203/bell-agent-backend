# tools/web_rag/utils.py
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

# ✅ 메트릭 이벤트 훅
from tools.metrics import event

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
    from pdfminer.high_level import extract_text as _pdfminer_extract_text  # may be unused
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

# ─────────────────────────────────────────────────────────────────────────────
# 결과 저장 (web.json 스냅샷) + 메트릭
# ─────────────────────────────────────────────────────────────────────────────
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

    # ✅ METRICS: 저장 스냅샷 기록
    try:
        event("results_saved",
              items_count=len(items or []),
              saved_path=str(path),
              query_hash=(suffix.lstrip("_") if suffix else ""))
    except Exception:
        pass

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
# 게이트키핑 (+ 메트릭)
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

    # ✅ METRICS: 게이트키핑 집계
    try:
        event("gatekeep_stats",
              blocked_count=len(blocked),
              allowed_count=len(allowed),
              blocked_rate=(len(blocked) / max(1, len(blocked) + len(allowed))))
    except Exception:
        pass

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
# 결과 원문 보강 (+ 메트릭)
# ─────────────────────────────────────────────────────────────────────────────
def _enrich_raw_content(results: List[Dict[str, Any]]) -> None:
    top = int(os.getenv("WEB_SEARCH_RAW_FETCH_TOP", "5") or "5")
    if top <= 0:
        return

    budget_s = float(os.getenv("WEB_FETCH_BUDGET_SECONDS", "30"))
    t0 = time.time()

    # ✅ METRICS: 원문 보강 시작
    try:
        event("raw_fetch_start", top=top, budget_seconds=budget_s, candidates=len(results or []))
    except Exception:
        pass

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
            # ✅ METRICS: 예산 초과
            try:
                event("raw_fetch_budget_exceeded",
                      elapsed=round(time.time() - t0, 3),
                      budget_seconds=budget_s)
            except Exception:
                pass
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
                    # 실패라기보다 스킵 처리
                    try:
                        event("raw_fetch_skip_serialized", url=_host_of(url))
                    except Exception:
                        pass
                    continue
                r["raw_content"] = html
                # ✅ METRICS: 페치 성공
                try:
                    event("raw_fetch_ok", url=_host_of(url), bytes=len(html.encode("utf-8")))
                except Exception:
                    pass
        except Exception as e:
            logger.debug("raw_content fetch failed for %s: %s", url, e)
            # ✅ METRICS: 페치 실패
            try:
                event("raw_fetch_fail", url=_host_of(url), err=str(e.__class__.__name__))
            except Exception:
                pass
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
