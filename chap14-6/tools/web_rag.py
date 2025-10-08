# tools/web_rag.py
from __future__ import annotations

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

# ---- Optional: Tavily ----
try:
    from tavily import TavilyClient  # pip install tavily-python
    _HAS_TAVILY = True
except Exception:
    _HAS_TAVILY = False

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
    print("[INFO] .env 미발견: OS 환경변수만 사용합니다.")

PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", Path(__file__).resolve().parents[1]))
DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

def _now(fmt: str = "%Y_%m%d_%H%M%S") -> str:
    return datetime.now().strftime(fmt)

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
# 프리뷰/적재 직전: if _looks_like_serialized_blob(page_text): skip

# ─────────────────────────────────────────────────────────────────────────────
# 원문 로딩: 세션 + 타임아웃 + 바이트 한도 + 폴백(WebBaseLoader with timeout)
# ─────────────────────────────────────────────────────────────────────────────

def _load_web_page(url: str) -> str:
    """
    빠르고 안전한 원문 로딩:
    1) requests 세션으로 스트리밍 GET (타임아웃/최대바이트/인코딩 추정)
    2) 실패하면 WebBaseLoader를 '타임아웃 지정'으로 폴백
    """
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
            # 간단 정리
            while "\n\n\n" in text or "\t\t\t" in text:
                text = text.replace("\n\n\n", "\n\n").replace("\t\t\t", "\t\t")
            return text.strip()
    except Exception:
        pass

    # 2) WebBaseLoader 폴백 (타임아웃/헤더/검증 지정)
    try:
        try:
            loader = WebBaseLoader(
                url,
                requests_kwargs={
                    "timeout": (connect_to, read_to),
                    "verify": session.verify,
                    "headers": dict(session.headers),
                },
                verify_ssl=True,  # 최신 langchain-community에선 verify_ssl 지원
            )
        except TypeError:
            # 구버전 호환
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
    except Exception:
        return ""


def _enrich_raw_content(results: List[Dict[str, Any]]) -> None:
    """
    상위 N개 결과만, 각 URL에 타임아웃 걸고, 전체 예산(budget)도 제한.
    - 끊임없이 대기하는 문제 방지
    """
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
            # 전체 예산 초과 → 중단
            break
        if r.get("raw_content"):
            continue
        url = r.get("url")
        if not url:
            continue
        try:
            html = _load_web_page(url)
            if html and not _is_bad_doc_text(html[:2000]):
                # 🔎 프리뷰/적재 전 직렬화 블롭(SSR/번들, next data 등) 차단
                if _looks_like_serialized_blob(html):
                    continue
                r["raw_content"] = html
        except Exception:
            # URL 하나 실패해도 전체는 계속
            continue

# 추가: persist_directory/CHROMA_DIR/기본값을 일관되게 해석
def _resolve_persist_dir(namespace: str, persist_directory: Optional[str]) -> str:
    # 1) 인자로 명시된 persist_directory가 최우선
    if persist_directory is not None:
        s = persist_directory.strip()
        if s:
            return s

    # 2) CHROMA_DIR을 베이스로 취급 (빈 문자열/None 방지)
    chroma_dir = os.getenv("CHROMA_DIR")
    if chroma_dir is not None:
        s = chroma_dir.strip()
        if s:
            p = Path(s)

            # (a) 이미 ns로 끝나면 그대로 사용
            if p.name == namespace:
                return str(p)

            # (b) 과거: .../chroma_store/<old_ns> 를 전체로 넣어둔 케이스 → 마지막 컴포넌트를 ns로 교체
            if p.parent.name == "chroma_store":
                return str(p.parent / namespace)

            # (c) 일반 케이스: 베이스/namespace
            return str(p / namespace)

    # 3) 완전 기본값(프로젝트 data/chroma_store/namespace)
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
        print(f"[web_rag] Tavily 실패: {e}")
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
        print(f"[web_rag] Google CSE 실패: {e}")
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
        print(f"[web_rag] SerpAPI 실패: {e}")
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
    _enrich_raw_content(results)
    path = _save_results(results, query=query)  # ← 기본 out_dir 사용 + query 해시 suffix
    print(f"[web_search] backend={used}, results={len(results)}, saved={path}")
    return results, path


# =============================================================================
# RAG: Documents conversion & Chroma ingestion/retrieval
# =============================================================================

def web_results_to_documents(resources: List[Dict[str, Any]]) -> List[Document]:
    """
    이미 메모리 상의 검색결과 리스트를 LangChain Document로 변환.
    - 차단/봇 페이지/바이너리 감지 시 제외
    """
    docs: List[Document] = []
    for r in (resources or []):
        pc = r.get("raw_content") or r.get("content") or ""
        if not pc or _is_block_page(pc) or _looks_like_pdf_bytes(pc):
            continue
        # 🔎 직렬화 블롭(Next.js __NEXT_DATA__, huge JSON, 번들 청크 등) 제외
        if _looks_like_serialized_blob(pc):
            continue
        src = r.get("source") or r.get("url") or ""  # ← source 우선!
        docs.append(Document(
            page_content=_clean_text(pc),
            metadata={"title": r.get("title", ""), "source": src}))
    return docs

def web_page_json_to_documents(json_file: str) -> List[Document]:
    if not os.path.exists(json_file):
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
    except Exception:
        resources = []

    return web_results_to_documents(resources)


# ---- Vector store cache (persist_dir, collection) ----
_VS_CACHE: Dict[Tuple[str, str], Chroma] = {}

# ✅ 프로세스 당 1회 초기화 가드
_CLEARED_ONCE = False

def _default_chroma_dir(namespace: str) -> str:
    # 과거 직접 구현 대신, 단일 해석 로직으로 통일
    return _resolve_persist_dir(namespace, persist_directory=None)

def clear_vector_store(namespace: Optional[str] = None, persist_directory: Optional[str] = None) -> str:
    """
    해당 namespace/persist_directory의 Chroma를 완전히 초기화한다.
    - _VS_CACHE에서 핸들 제거
    - 디스크 폴더 삭제 후 재생성
    반환: 실제 초기화된 디렉터리 경로(문자열)
    """
    import shutil, stat

    # ns = (namespace or os.getenv("CHROMA_NAMESPACE", "default")).strip()
    env_ns = os.getenv("CHROMA_NAMESPACE")
    ns = (namespace or (env_ns if env_ns is not None else "default")).strip()
    pd = _resolve_persist_dir(ns, persist_directory)

    # (안전장치) 명시적 인자가 없는 전역 초기화는 기본적으로 막는다.
    if (namespace is None and persist_directory is None) and os.getenv("ALLOW_GLOBAL_CLEAR", "0") != "1":
        print(f"[INIT] clear_vector_store skipped (global clear disabled). ns='{ns}' dir='{pd}'")
        return pd

    # 메모리 캐시 제거
    try:
        _VS_CACHE.pop((pd, ns), None)
    except Exception:
        pass

    # Windows에서 읽기전용 파일도 지울 수 있게 onerror 핸들러
    def _on_rm_error(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    # 디스크 폴더 제거 후 재생성
    try:
        if os.path.isdir(pd):
            shutil.rmtree(pd, onerror=_on_rm_error)
        os.makedirs(pd, exist_ok=True)
    except Exception as e:
        print(f"[INIT] clear_vector_store 실패: {e}")

    print(f"[INIT] vector store cleared → ns='{ns}' dir='{pd}'")
    return pd

def ensure_vector_store_cleared_once(
    namespace: Optional[str] = None,
    persist_directory: Optional[str] = None,
) -> bool:
    """
    프로세스 시작 후 '한 번만' 벡터스토어를 초기화한다.
    - CLEAR_CHROMA_ON_START=1 (기본)일 때만 동작
    - 이미 한 번 초기화했으면 False 반환
    - 실제 초기화하면 True 반환
    """
    global _CLEARED_ONCE
    if _CLEARED_ONCE:
        return False

    if os.getenv("CLEAR_CHROMA_ON_START", "1") != "1":
        # 스위치로 비활성화된 상태
        return False

    clear_vector_store(namespace=namespace, persist_directory=persist_directory)
    _CLEARED_ONCE = True
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
    return vs

def split_documents(documents: List[Document], *, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None) -> List[Document]:
    # ENV 기반 기본값(문자 기준, 토큰≈문자/4 가정)
    cs = int(os.getenv("RAG_CHUNK_CHARS", "2400")) if chunk_size is None else int(chunk_size)
    ov = int(os.getenv("RAG_CHUNK_OVERLAP", "200")) if chunk_overlap is None else int(chunk_overlap)
    cs = max(300, min(cs, 6000))
    ov = max(0, min(ov, int(cs * 0.5)))
    splitter = RecursiveCharacterTextSplitter(chunk_size=cs, chunk_overlap=ov)
    return splitter.split_documents(documents)

def _approx_tokens(s: str) -> int:
    # 대략 토큰≈문자/4
    return max(1, len(s or "") // 4)

def _batched_add(vs: Chroma, splits: List[Document], ids: Optional[List[str]] = None) -> int:
    """
    안전 배치 삽입:
    - 요청 당 토큰 상한(ENV: RAG_TOKEN_BUDGET_PER_REQ, 기본 250k) 이하로 묶음
    - 건수 상한(ENV: RAG_EMBED_BATCH, 기본 64)도 동시에 적용
    """
    MAX_TOKENS = int(os.getenv("RAG_TOKEN_BUDGET_PER_REQ", "250000"))
    MAX_BATCH  = int(os.getenv("RAG_EMBED_BATCH", "64"))
    total_added = 0

    i = 0
    while i < len(splits):
        tok_sum = 0
        j = i
        while j < len(splits) and (j - i) < MAX_BATCH:
            tok_sum += _approx_tokens(splits[j].page_content)
            if tok_sum > MAX_TOKENS and j > i:
                break
            j += 1
        batch_docs = splits[i:j]
        batch_ids  = ids[i:j] if ids else None
        try:
            if batch_ids:
                vs.add_documents(batch_docs, ids=batch_ids)
            else:
                vs.add_documents(batch_docs)
            total_added += len(batch_docs)
        except Exception as e:
            # 혹시 실패하면 더 작은 단위로 폴백
            mid = (i + j) // 2
            if mid == i:
                # 한 건도 못 넣는다면 해당 문서는 스킵
                print(f"[WARN] add_documents 실패(1건 스킵): {e}")
                i += 1
                continue
            # 재귀적 분할 대신 선형 축소
            step = max(1, (j - i) // 2)
            j = i + step
            continue
        i = j
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
    문서들을 세션/주제별 Chroma 컬렉션에 적재.
    - namespace/collection_name + persist_directory 로 논리/물리 격리
    - 기존 저장 URL(source) 중복 방지
    - 초대형 문서 안전 청킹 + 배치 임베딩(토큰 상한 보호)
    - 반환: (원본 문서 수, 적재된 청크 수)
    """
    from typing import cast
    from chromadb.api.types import Where, Include  # ← 중요
    from settings_gatekeep import url_allowed

    ns = collection_name or namespace or os.getenv("CHROMA_NAMESPACE") or "default"
    pd = _resolve_persist_dir(ns, persist_directory)
    os.makedirs(pd, exist_ok=True)
    
    if clear:
        _VS_CACHE.pop((pd, ns), None)
        try:
            import shutil
            if os.path.isdir(pd):
                shutil.rmtree(pd)
            os.makedirs(pd, exist_ok=True)
        except Exception:
            pass

    vs = _get_vs(ns, pd, embedding)

    # 0) 차단/바이너리 텍스트 제거
    pre_docs: List[Document] = []
    for d in (documents or []):
        txt = getattr(d, "page_content", "") or ""
        if (not txt
            or _is_block_page(txt)
            or _looks_like_pdf_bytes(txt)
            or _looks_like_serialized_blob(txt)  # 🔎 이중 안전망
        ):
            continue
        d.page_content = _clean_text(txt)
        pre_docs.append(d)

    # 1) 이미 저장된 URL set
    all_urls = {
        (getattr(d, "metadata", {}) or {}).get("source")
        for d in (pre_docs or [])
        if (getattr(d, "metadata", {}) or {}).get("source")
    }
    stored_urls = set()
    if all_urls:
        try:
            urls: list[str] = [u for u in all_urls if isinstance(u, str) and u]  # None 제거 + 문자열 보장
            where_filter = {"source": {"$in": urls}}  # 런타임에서 유효한 쿼리
            include = ["metadatas"]
            res = vs._collection.get(
                where=cast(Where, where_filter),
                include=cast(Include, include),
            )
            # where_filter: Where = {"source": {"$in": list(all_urls)}}
            # include: Include = ["metadatas"]
            # res = vs._collection.get(where=where_filter, include=include)
            for m in (res or {}).get("metadatas") or []:
                if isinstance(m, dict) and m.get("source"):
                    stored_urls.add(m["source"])
        except Exception:
            try:
                res = vs._collection.get(include=["metadatas"])
                for m in (res or {}).get("metadatas") or []:
                    if isinstance(m, dict) and m.get("source"):
                        stored_urls.add(m["source"])
            except Exception:
                stored_urls = set()

    new_documents: List[Document] = []
    skipped = []  # ← [옵션] 로그용
    new_url_set = all_urls - stored_urls
    for d in (pre_docs or []):
        meta = getattr(d, "metadata", {}) or {}
        src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""

        # [2번 수정] 허용 도메인 필터
        if not url_allowed(src):
            skipped.append(src)
            continue

        if src and src in new_url_set:
            new_documents.append(d)
            if verbose:
                print(d.metadata)
                
    if skipped and verbose:
        print(f"[GATEKEEP] skipped {len(skipped)} doc(s) by allowlist; sample={skipped[:3]}")

    if not new_documents:
        if verbose:
            print("[INFO] documents_to_chroma: No new urls to process")
        return (len(documents or []), 0)

    # 2) 안전 청킹(ENV 기반)
    splits = split_documents(new_documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not splits:
        return (len(documents or []), 0)

    # 3) 결정적 ID 생성(업서트 친화)
    from collections import defaultdict as _dd
    ids: List[str] = []
    # counter = _dd(int)
    counter: DefaultDict[str, int] = _dd(int)
    for s in splits:
        src = (getattr(s, "metadata", {}) or {}).get("source", "")
        if src:
            base = hashlib.sha1(src.encode("utf-8", "ignore")).hexdigest()
            counter[base] += 1
            ids.append(f"{base}-{counter[base]:06d}")
        else:
            counter["__none__"] += 1
            ids.append(f"none-{counter['__none__']:06d}")

    # 4) 배치 임베딩(토큰 상한 보호)
    added = _batched_add(vs, splits, ids)

    persist_fn = getattr(vs, "persist", None)
    if callable(persist_fn):
        persist_fn()
    else:
        client = getattr(vs, "_client", None)
        client_persist = getattr(client, "persist", None)
        if callable(client_persist):
            client_persist()

    # added = _batched_add(vs, splits, ids)

    # try:
    #     vs.persist()
    # except AttributeError:
    #     pass

    return (len(documents or []), added)

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
    세션/주제별 Chroma 컬렉션에서 RAG 검색.
    미지정 시 CHROMA_NAMESPACE/CHROMA_DIR 사용.
    """
    # --- 추가: local/glob 쿼리 방어 ---
    ql = (query or "").lower().strip()
    if ql.startswith("local:"):
        print(f"[retrieve] skip local/glob query: {query}")
        return []
    if any(tok in query for tok in ("**\\", "**/", "\\*.", "/*.", "\\**", "/**")):
        print(f"[retrieve] skip glob-like query: {query}")
        return []
    # ---------------------------------
    
    ns = collection_name or namespace or os.getenv("CHROMA_NAMESPACE") or "default"
    pd = _resolve_persist_dir(ns, persist_directory)

    vs = _get_vs(ns, pd, embedding)
    retriever = vs.as_retriever(search_kwargs={"k": top_k})
    return retriever.invoke(query)


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
    # ✅ 추가
    "clear_vector_store",
    "ensure_vector_store_cleared_once",
    "_default_chroma_dir",  # ← 추가
]
