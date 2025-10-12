# tools/web_rag.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os, json, time, io, hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, DefaultDict
from datetime import datetime

import requests, certifi, chardet
from dotenv import load_dotenv, find_dotenv
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from settings_gatekeep import (
    gatekeep_enabled,
    url_allowed,
    _normalize_host,   # 로그 요약용 (없으면 제거해도 무방)
)

from collections import defaultdict as _dd

# ─────────────────────────────────────────────────────────────────────────────
# HTTPS 세션 (검증 ON)
# ─────────────────────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({"User-Agent": os.getenv("USER_AGENT", "BookWriterBot/1.0")})
session.verify = certifi.where()  # 신뢰 루트 지정

def http_get(url, **kw):
    # 공통 타임아웃 기본값
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

# ---- RAG (Chroma + OpenAI embeddings) ----
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma


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

# 파일 상단 전역들 근처에 추가
_RECENTLY_CLEARED: dict[str, float] = {}             # dir -> cleared_at epoch (부드러운 신호, 시간기반)
_FRESH_KEYS: set[tuple[str, str]] = set()            # (persist_dir, namespace) 강한 신호(원샷)

def _now(fmt: str = "%Y_%m%d_%H%M%S") -> str:
    return datetime.now().strftime(fmt)

def _truthy(name: str, default: Optional[str] = None) -> bool:
    """
    환경변수의 진리값 해석 헬퍼.
    default=None이면 unset 시 False 처리.
    """
    raw = os.getenv(name) if default is None else os.getenv(name, default)
    v = (raw or "").strip().lower()
    return v in {"1", "true", "yes", "on"}

def _save_results(items, out_dir: Optional[Path | str] = None, *, query: Optional[str] = None) -> str:
    """
    검색 결과를 JSON으로 저장하고 경로 문자열을 반환.
    out_dir 기본값:
      - ENV WEB_RAG_DATA_DIR (값이 비었거나 공백이면 무시)
      - 없으면 DATA_DIR
    파일명: resources_{timestamp}_{hash(query, 4bytes)}.json
    """
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

# =============================================================================
# Common helpers
# =============================================================================

def _normalize_results(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    서로 다른 백엔드의 결과를 통일 스키마로 정규화.
    Output keys: title, url, content, raw_content, source
    """
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

def _dedup_by_url(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for r in items:
        u = r.get("url")
        if u and u not in seen:
            seen.add(u)
            out.append(r)
    return out

def _clean_text(txt: str) -> str:
    if not txt:
        return ""
    # 과도한 공백/탭/줄바꿈 정리
    while "\n\n\n" in txt or "\t\t\t" in txt:
        txt = txt.replace("\n\n\n", "\n\n").replace("\t\t\t", "\t\t")
    return txt

def _looks_like_pdf_bytes(txt: str) -> bool:
    # PDF 바이너리 헤더가 텍스트로 들어온 경우(거대 바이트→토큰 폭증 원인)
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
    return brace_ratio > 0.02  # 경험치 임계값

# ─────────────────────────────────────────────────────────────────────────────
# 게이트키핑: 검색 결과 URL에 대한 허용/차단 적용
# ─────────────────────────────────────────────────────────────────────────────
def _apply_gatekeep_to_results(results: list[dict]) -> list[dict]:
    if not results:
        return results
    if not gatekeep_enabled():
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
            # 호스트만 요약해서 로그
            hosts = []
            for u in blocked:
                h = _normalize_host(u)
                hosts.append(h or u)
            logger.warning("[GATEKEEP] blocked %d url(s): %s", len(blocked), ", ".join(hosts[:10]))
        except Exception:
            logger.warning("[GATEKEEP] blocked %d url(s).", len(blocked))

    return allowed


# ─────────────────────────────────────────────────────────────────────────────
# 원문 로딩: 세션 + 타임아웃 + 바이트 한도 + 폴백(WebBaseLoader with timeout)
# ─────────────────────────────────────────────────────────────────────────────

def _load_web_page(url: str) -> str:
    connect_to = int(os.getenv("WEB_FETCH_TIMEOUT_CONNECT", "6"))
    read_to    = int(os.getenv("WEB_FETCH_TIMEOUT_READ", "20"))
    max_bytes  = int(os.getenv("WEB_FETCH_MAX_BYTES", "1000000"))  # 1MB

    # 1) 세션으로 시도
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
            # 인코딩 추정
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

    # 2) WebBaseLoader 폴백
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


def _enrich_raw_content(results: List[Dict[str, Any]]) -> None:
    top = int(os.getenv("WEB_SEARCH_RAW_FETCH_TOP", "5") or "5")
    if top <= 0:
        return

    budget_s = float(os.getenv("WEB_FETCH_BUDGET_SECONDS", "30"))  # 전체 예산(초)
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

# 추가: persist_directory/CHROMA_DIR/기본값을 일관되게 해석
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
        hl = os.getenv("SEARCH_HL", "en")
        gl = os.getenv("SEARCH_GL", "us")
        num = max(1, min(int(num or 10), 10))

        url = "https://www.googleapis.com/customsearch/v1"
        r = http_get(
            url,
            params={"key": api_key, "cx": cse_id, "q": query, "num": num, "hl": hl, "gl": gl},
            timeout=timeout,
        )
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


# =============================================================================
# Public Tool: web_search
# =============================================================================

@tool("web_search")
def web_search(
    query: str,
    *,
    engine: Optional[str] = None,  # "auto" | "tavily" | "google" | "serpapi"
    num: int = 10,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    멀티 엔진 웹검색 (Tavily → Google CSE → SerpAPI 폴백)
    반환: (results[list[dict]], json_path[str])
    - 결과 스키마: {title, url, content, raw_content, source}
    - ENV:
      TAVILY_API_KEY
      GOOGLE_API_KEY/GOOGLE_CSE_API_KEY, GOOGLE_CSE_ID/GOOGLE_CSE_CX
      SERPAPI_API_KEY
      SEARCH_HL, SEARCH_GL
      WEB_SEARCH_ENGINE=auto|tavily|google|serpapi
      WEB_SEARCH_RAW_FETCH_TOP (원문 로딩 상위 N, 기본 5)
      WEB_RAG_DATA_DIR (검색 결과 JSON 저장 디렉터리)
    """
    engine = (engine or os.getenv("WEB_SEARCH_ENGINE") or "auto").strip().lower()
    results: List[Dict[str, Any]] = []
    used = None

    # 1) Tavily
    if engine in ("auto", "tavily"):
        results = _search_tavily(query)
        used = "tavily" if results else None

    # 2) Google CSE
    if not results and engine in ("auto", "google", "tavily"):
        results = _search_google_cse(query, num=num)
        used = "google_cse" if results else used

    # 3) SerpAPI
    if not results and engine in ("auto", "serpapi", "google", "tavily"):
        results = _search_serpapi(query, num=num)
        used = "serpapi" if results else used

    # 간단 재시도(완전 빈 결과일 때만 1회)
    if not results:
        time.sleep(1.0)
        results = _search_tavily(query) or _search_google_cse(query, num=num) or _search_serpapi(query, num=num)
        if results and not used:
            used = "retry"

    if not results:
        raise RuntimeError(
            "web_search: Tavily/Google CSE/SerpAPI 모두 실패. "
            "TAVILY_API_KEY 또는 GOOGLE_API_KEY/GOOGLE_CSE_ID 또는 SERPAPI_API_KEY를 확인하세요."
        )

    results = _dedup_by_url(_normalize_results(results))
    # 🔒 게이트키핑 적용 (ON일 때만)
    results = _apply_gatekeep_to_results(results)
    _enrich_raw_content(results)
    path = _save_results(results, query=query)
    logger.info("[web_search] backend=%s, results=%d, saved=%s", used, len(results), path)
    return results, path


# =============================================================================
# RAG: Documents conversion & Chroma ingestion/retrieval
# =============================================================================

def web_results_to_documents(resources: List[Dict[str, Any]]) -> List[Document]:
    docs: List[Document] = []
    for r in (resources or []):
        pc = r.get("raw_content") or r.get("content") or ""
        if not pc or _is_block_page(pc) or _looks_like_pdf_bytes(pc):
            continue
        if _looks_like_serialized_blob(pc):
            continue
        src = r.get("source") or r.get("url") or ""  # ← source 우선!
        docs.append(Document(
            page_content=_clean_text(pc),
            metadata={"title": r.get("title", ""), "source": src}))
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
            # NDJSON fallback
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
            return [data]  # 단일 객체
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

# ✅ 네임스페이스별 1회 초기화 가드 상태
_CLEARED_ONCE_KEYS: set[tuple[str, str]] = set()

def _default_chroma_dir(namespace: str) -> str:
    return _resolve_persist_dir(namespace, persist_directory=None)

def clear_vector_store(namespace: Optional[str] = None, persist_directory: Optional[str] = None) -> str:
    """
    해당 namespace/persist_directory의 Chroma를 완전히 초기화한다.
    - _VS_CACHE에서 핸들 제거 + 클라이언트 close/reset 시도
    - 디스크 폴더 삭제(재시도/격리) 후 재생성
    - 재생성 직후 (pd, ns)에 대한 fresh 신호를 기록
    반환: 실제 초기화된 디렉터리 경로(문자열)
    """
    import shutil, stat, gc, time

    env_ns = os.getenv("CHROMA_NAMESPACE")
    ns = (namespace or (env_ns if env_ns is not None else "default")).strip()
    pd = _resolve_persist_dir(ns, persist_directory)

    # 전역 클리어 안전 가드
    if (namespace is None and persist_directory is None) and os.getenv("ALLOW_GLOBAL_CLEAR", "0") != "1":
        logger.info("[INIT] clear_vector_store skipped (global clear disabled). ns='%s' dir='%s'", ns, pd)
        return pd

    # 0) VS 캐시/클라이언트 정리 → 파일 핸들 해제
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
        _VS_CACHE.clear()  # 동일 dir의 다른 키가 남아있을 가능성 차단
    except Exception:
        pass

    try:
        del vs  # type: ignore
    except Exception:
        pass
    gc.collect()
    time.sleep(0.15)  # Windows 파일락 완화

    def _on_rm_error(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    # 1) rmtree 재시도 (백오프)
    ok = False
    for i in range(6):  # 필요시 8로 상향 가능
        try:
            if os.path.isdir(pd):
                shutil.rmtree(pd, onerror=_on_rm_error)
            ok = True
            break
        except Exception:
            time.sleep(0.2 * (i + 1))  # 0.2, 0.4, ..., 1.2s

    # 2) 최후 수단: quarantine 폴더로 격리(rename)
    if not ok:
        try:
            if os.path.isdir(pd):
                quarantine = f"{pd}.quarantine_{int(time.time())}"
                os.replace(pd, quarantine)
                logger.debug("[INIT] vector store quarantined → %s", quarantine)
            ok = True
        except Exception as e:
            logger.warning("[INIT] clear_vector_store failed(final): %s", e)

    # 3) 재생성
    try:
        os.makedirs(pd, exist_ok=True)
    except Exception as e:
        logger.warning("[INIT] re-create dir failed: %s", e)

    # 4) fresh 신호 기록 (강한 신호: 원샷)
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
    """
    (persist_dir, namespace) 단위로 '최초 1회만 clear' 수행.
    - 신규 플래그 CLEAR_ON_FIRST_VECTOR(우선) 또는 레거시 CLEAR_CHROMA_ON_START 가 true일 때 동작
    - 한 번 실행되면 동일 (pd, ns) 키에 대해 재실행하지 않음
    """
    # 둘 중 하나라도 true면 허용
    if not (_truthy("CLEAR_ON_FIRST_VECTOR", default=None) or _truthy("CLEAR_CHROMA_ON_START", default=None)):
        return False

    env_ns = os.getenv("CHROMA_NAMESPACE")
    ns = (namespace or (env_ns if env_ns is not None else "default")).strip()
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
    model = os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-large")
    return embedding or OpenAIEmbeddings(model=model)

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
) -> int:
    """
    안전 업서트:
      - 토큰/배치 예산으로 1차 배치 구성
      - 예외 시 배치 반으로 축소 → 단건까지 이분탐색
      - 단건도 실패하면 해당 청크를 격리(quarantine) JSON으로 기록하고 건너뜀
    """
    MAX_TOKENS = int(os.getenv("RAG_TOKEN_BUDGET_PER_REQ", "250000"))
    # 기존 RAG_EMBED_BATCH가 있으면 우선 사용, 없으면 CHROMA_MAX_BATCH, 없으면 64
    MAX_BATCH  = int(os.getenv("RAG_EMBED_BATCH", os.getenv("CHROMA_MAX_BATCH", "64")))
    total_added = 0

    # 격리 폴더 준비
    quarantine_dir = Path(
        os.getenv("CHROMA_QUARANTINE_DIR", "")
        or (Path(vs._persist_directory) / "quarantine")  # type: ignore[attr-defined]
    )
    try:
        quarantine_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    def _write_quarantine(doc: Document, doc_id: Optional[str], err: Exception) -> None:
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

    # 메인 루프
    i = 0
    while i < len(splits):
        # 토큰/배치 한도로 1차 배치 구성
        tok_sum, j = 0, i
        while j < len(splits) and (j - i) < MAX_BATCH:
            tok_sum += _approx_tokens(splits[j].page_content)
            if tok_sum > MAX_TOKENS and j > i:
                break
            j += 1

        def _try_range(lo: int, hi: int) -> int:
            """[lo, hi) 구간을 최대한 추가. 실패 시 이분 분해. 반환=성공 추가 개수"""
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
                # 배치를 절반으로 쪼개서 재귀 시도
                if n >= 2:
                    mid = lo + n // 2
                    left  = _try_range(lo, mid)
                    right = _try_range(mid, hi)
                    return left + right
                # n == 1 인데도 실패 → 격리 후 스킵
                _write_quarantine(splits[lo], ids[lo] if ids else None, e)
                return 0

        added_now = _try_range(i, j)
        total_added += added_now
        i = j  # 다음 배치로 진행

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
    """
    입력 문서를 Chroma에 안전하게 인덱싱.
    - 게이트키핑/블롭/차단 텍스트 필터
    - fresh store 감지(초기화 이후 캐시 핸들 재생성)
    - 안전 배치 업서트(_batched_add) 사용
    - 상세 진단 로그 및 ID 길이 제한(환경변수로 조정)
    """
    from typing import cast
    from chromadb.api.types import Where, Include
    from settings_gatekeep import url_allowed

    ns = collection_name or namespace or os.getenv("CHROMA_NAMESPACE") or "default"
    pd = _resolve_persist_dir(ns, persist_directory)
    os.makedirs(pd, exist_ok=True)

    # 요약 로그용 카운터
    total_in_docs   = len(documents or [])
    pre_docs_count  = 0
    skipped_gate    = 0
    skipped_block   = 0
    new_docs_count  = 0
    split_count     = 0
    added_chunks    = 0

    if clear:
        _VS_CACHE.pop((pd, ns), None)
        try:
            import shutil
            if os.path.isdir(pd):
                shutil.rmtree(pd)
            os.makedirs(pd, exist_ok=True)
            logger.info("documents_to_chroma: cleared vector store (%s, %s)", ns, pd)
        except Exception as e:
            logger.warning("documents_to_chroma: clear failed: %s", e)

    vs = _get_vs(ns, pd, embedding)

    # --- 새(빈) 스토어 감지: 컬렉션 카운트/디렉터리 비어있음/강한 신호(FRESH_KEYS)
    def _is_fresh_store() -> bool:
        if (pd, ns) in _FRESH_KEYS:  # 강한 신호
            return True
        try:
            col = getattr(vs, "_collection", None)
            cnt_fn = getattr(col, "count", None)
            if callable(cnt_fn) and cnt_fn() == 0:
                return True
        except Exception:
            pass
        try:
            p = Path(pd)
            if p.exists():
                for _ in p.iterdir():
                    break
                else:
                    return True  # 비어 있음
        except Exception:
            pass
        return False

    is_fresh = _is_fresh_store()
    if is_fresh:
        try:
            _VS_CACHE.pop((pd, ns), None)
        except Exception:
            pass
        vs = _get_vs(ns, pd, embedding)
        try:
            _FRESH_KEYS.discard((pd, ns))
        except Exception:
            pass
        logger.debug("documents_to_chroma: fresh store — evicted cached VS and recreated handle")

    # 0) 차단/바이너리/블롭 텍스트 제거 + 클린업
    pre_docs: List[Document] = []
    for d in (documents or []):
        txt = getattr(d, "page_content", "") or ""
        if (not txt
            or _is_block_page(txt)
            or _looks_like_pdf_bytes(txt)
            or _looks_like_serialized_blob(txt)
        ):
            skipped_block += 1
            continue
        d.page_content = _clean_text(txt)
        pre_docs.append(d)
    pre_docs_count = len(pre_docs)

    # 1) 이미 저장된 URL set 수집
    all_urls = {
        (getattr(d, "metadata", {}) or {}).get("source")
        for d in (pre_docs or [])
        if (getattr(d, "metadata", {}) or {}).get("source")
    }
    stored_urls = set()

    # fresh store면 저장된 URL 조회를 생략
    if all_urls and not is_fresh:
        try:
            urls: list[str] = [u for u in all_urls if isinstance(u, str) and u]
            where_filter = {"source": {"$in": urls}}
            include = ["metadatas"]
            res = vs._collection.get(  # type: ignore[attr-defined]
                where=cast(Where, where_filter),
                include=cast(Include, include),
            )
            for m in (res or {}).get("metadatas") or []:
                if isinstance(m, dict) and m.get("source"):
                    stored_urls.add(m["source"])
        except Exception as e:
            logger.debug("chroma get(where=$in) failed, fallback to full metadatas: %s", e)
            try:
                res = vs._collection.get(include=["metadatas"])  # type: ignore[attr-defined]
                for m in (res or {}).get("metadatas") or []:
                    if isinstance(m, dict) and m.get("source"):
                        stored_urls.add(m["source"])
            except Exception as e2:
                logger.debug("chroma full metadatas get failed: %s", e2)
                stored_urls = set()
    elif is_fresh:
        logger.debug("documents_to_chroma: fresh store detected; skip stored_urls check")

    # 2) 게이트키핑 및 신규 문서 선택
    new_documents: List[Document] = []
    new_url_set = all_urls - stored_urls
    skipped_samples: list[str] = []
    for d in (pre_docs or []):
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""
        if not url_allowed(src):
            skipped_gate += 1
            if len(skipped_samples) < 3 and src:
                skipped_samples.append(src)
            continue
        if src and (is_fresh or src in new_url_set):
            new_documents.append(d)
        elif not src and is_fresh:
            # 소스가 없지만 fresh면 그대로 수용(희귀 케이스)
            new_documents.append(d)
    new_docs_count = len(new_documents)

    # fresh인데도 enqueue가 비었고 URL은 있는 경우 → 강제 enqueue
    if not new_documents and is_fresh and all_urls:
        logger.debug("fresh-store fallback: forcing enqueue of all urls")
        new_documents = list(pre_docs)
        new_docs_count = len(new_documents)

    if skipped_gate and verbose:
        logger.info("[GATEKEEP] skipped %d doc(s) by allowlist; sample=%s", skipped_gate, skipped_samples)

    if not new_documents:
        if verbose:
            logger.info(
                "documents_to_chroma: no new urls to process | "
                "in=%d, pre=%d, blocked=%d, gate_skipped=%d, fresh=%s",
                total_in_docs, pre_docs_count, skipped_block, skipped_gate, is_fresh
            )
        return (total_in_docs, 0)

    # 3) 안전 청킹
    splits = split_documents(new_documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    split_count = len(splits)
    if not splits:
        if verbose:
            logger.info(
                "documents_to_chroma: no splits produced | "
                "in=%d, pre=%d, new=%d", total_in_docs, pre_docs_count, new_docs_count
            )
        return (total_in_docs, 0)

    # 4) 결정적 ID 생성 + 길이 제한(강제)
    MAX_ID_CHARS = int(os.getenv("CHROMA_MAX_ID_CHARS", "128"))
    ids: List[str] = []
    counter: DefaultDict[str, int] = _dd(int)

    def _cap_id(s: str) -> str:
        if len(s) <= MAX_ID_CHARS:
            return s
        # 뒤쪽 일련번호 보존을 위해 12자 정도는 남겨둔다.
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

    # 5) 배치 업서트(안전화된 _batched_add 사용)
    t0 = time.time()
    try:
        added_chunks = _batched_add(vs, splits, ids)
    except Exception as e:
        logger.warning("documents_to_chroma: batched_add raised — forcing smaller path: %s", e)
        # 비상 경로: 개별 업서트 시도(최소 손실)
        added_chunks = 0
        for k, doc in enumerate(splits):
            try:
                if ids:
                    vs.add_documents([doc], ids=[ids[k]])
                else:
                    vs.add_documents([doc])
                added_chunks += 1
            except Exception as e2:
                logger.warning("single upsert failed at %d: %s", k, e2)

    # 6) persist
    persist_fn = getattr(vs, "persist", None)
    if callable(persist_fn):
        try:
            persist_fn()
        except Exception as e:
            logger.debug("vs.persist failed (ignored): %s", e)
    else:
        client = getattr(vs, "_client", None)
        client_persist = getattr(client, "persist", None)
        if callable(client_persist):
            try:
                client_persist()
            except Exception as e:
                logger.debug("client.persist failed (ignored): %s", e)

    # 7) 상세 요약 로그
    avg_len = 0
    if split_count:
        try:
            total_chars = sum(len(d.page_content or "") for d in splits)
            avg_len = int(total_chars / split_count)
        except Exception:
            avg_len = 0

    elapsed = time.time() - t0
    logger.info(
        ("documents_to_chroma: %d docs → %d chunks (ns=%s, dir=%s) | "
         "in=%d, pre=%d, blocked=%d, gate_skipped=%d, new=%d, splits=%d, avg_chunk_chars=%d, fresh=%s, time=%.2fs"),
        total_in_docs, added_chunks, ns, pd,
        total_in_docs, pre_docs_count, skipped_block, skipped_gate, new_docs_count,
        split_count, avg_len, is_fresh, elapsed
    )

    return (total_in_docs, added_chunks)

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
    세션/주제별 Chroma 컬렉션에서 RAG 검색 (고속 경로 + 친절한 예외 메시지).
    - vs에 이미 설정된 임베딩 함수를 우선 재사용(테스트 더미 임베딩 포함)
    - 직접 Chroma .query()로 문서/메타만 가져와 빠르게 반환
    - 임베딩 모델/차원 불일치 등 흔한 오류는 RuntimeError로 원인/해결책 안내
    """
    q = (query or "").strip()
    if not q:
        return []

    ql = q.lower()
    if ql.startswith("local:"):
        logger.debug("[retrieve] skip local/glob query: %s", query)
        return []
    if any(tok in q for tok in ("**\\", "**/", "\\*.", "/*.", "\\**", "/**")):
        logger.debug("[retrieve] skip glob-like query: %s", query)
        return []

    ns = collection_name or namespace or os.getenv("CHROMA_NAMESPACE") or "default"
    pd = _resolve_persist_dir(ns, persist_directory)
    vs = _get_vs(ns, pd, embedding)

    # ★ 임베딩 함수: vs에 붙어있는 것을 1순위로 재사용
    emb_fn = getattr(vs, "_embedding_function", None) or embedding or _get_embeddings(embedding)

    # -------- Fast path: 직접 Chroma 질의 --------
    try:
        # 더미/실 임베딩 모두 embed_query 인터페이스를 가정
        q_emb = emb_fn.embed_query(q) if hasattr(emb_fn, "embed_query") else emb_fn(q)  # type: ignore
        n = max(1, int(top_k or 5))
        res = vs._collection.query(  # type: ignore[attr-defined]
            query_embeddings=[q_emb],
            n_results=n,
            include=["documents", "metadatas"],  # 최소 데이터만으로 I/O 절감
        )

        docs_out = []
        docs = (res or {}).get("documents") or []
        metas = (res or {}).get("metadatas") or []
        if docs and isinstance(docs, list):
            rows = zip(docs[0] if docs else [], metas[0] if metas else [])
            for doc_text, meta in rows:
                text = (doc_text or "")
                # 테스트/운영 보호: 단일 청크는 20k 미만으로 제한
                if len(text) > 19000:
                    text = text[:19000]
                m = meta if isinstance(meta, dict) else {}
                docs_out.append(Document(page_content=text, metadata=m))
        logger.debug("[retrieve-fast] ns=%s dir=%s k=%d → %d docs", ns, pd, n, len(docs_out))
        return docs_out

    except Exception as e:
        # 흔한 원인: 인제스트와 검색 시 임베딩 모델/차원 불일치
        emsg = (str(e) or "").lower()
        mismatch_signals = (
            "dimension" in emsg or
            ("embed" in emsg and "mismatch" in emsg) or
            "expected" in emsg and "got" in emsg and "dimension" in emsg
        )
        if mismatch_signals:
            raise RuntimeError(
                "Vector query failed due to a likely embedding model/dimension mismatch between "
                "ingestion and retrieval.\n\n"
                "How to fix:\n"
                "  • Ensure the SAME embedding model is used for both ingestion and retrieval.\n"
                "  • If you pass a custom `embedding=` here, it must match the one used to build this collection.\n"
                "  • Otherwise, omit `embedding` so the vector store’s existing embedding function is reused."
            ) from e

        # 그 외 예외는 디버그로 남기고 폴백 경로 시도
        logger.debug("[retrieve-fast] direct query failed; falling back to retriever: %s", e)

    # -------- Fallback: LangChain retriever --------
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
