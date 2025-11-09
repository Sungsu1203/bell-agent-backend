# tools/web_rag/ingest.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
logging.getLogger("chardet").setLevel(logging.WARNING)  # chardet DEBUG 스팸 억제

import os
from typing import Optional


# ── 환경 기반 기본값(없으면 안전한 디폴트) ─────────────────────────────
_REQ_CONN_TIMEOUT = float(os.getenv("REQUESTS_CONNECT_TIMEOUT", "5"))
_REQ_READ_TIMEOUT = float(os.getenv("REQUESTS_READ_TIMEOUT", "20"))

# (초기 안전 추출 유틸/단순 PDF 판별은 아래 정식 구현으로 대체)

import os, io, json, time, hashlib
from pathlib import Path
from typing import List, Dict, Tuple, Sequence, Any, Callable, Mapping, MutableMapping, Iterable, cast
from typing import Protocol, runtime_checkable  # ← quick_ingest 프록시 시그니처용
from types import ModuleType

import requests
from requests.exceptions import SSLError as _SSLError
import codecs  # for BOM checks in _decode_bytes
import certifi
from requests.auth import AuthBase
from requests.models import Response

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─────────────────────────────────────────────────────────────────────────────
# [LOG] pdfminer 과다 로그 억제 (WARNING 이상만)
# ─────────────────────────────────────────────────────────────────────────────
for _name in (
    "pdfminer",
    "pdfminer.psparser",
    "pdfminer.pdfdocument",
    "pdfminer.pdfparser",
    "pdfminer.cmapdb",
    "pdfminer.pdfinterp",
    "pdfminer.pdfdevice",
    "pdfminer.layout",
):
    try:
        logging.getLogger(_name).setLevel(logging.WARNING)
    except Exception:
        pass

# 통일된 UA (yakup 등 일부 사이트에서 헤더 파서 문제 완화)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# [PATCH SSL-1] 안전 태깅용 커스텀 예외 + 재시도 후보 기록기
class _PdfSslError(_SSLError):
    """PDF 다운로드 중 SSL 오류. verify=False 폴백 없이 상부에서 처리하도록 신호."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# requests.Session.get() 타입 안전 래퍼
#  - dict를 받아 지원되는 키만 분해/캐스팅하여 전달
#  - mypy의 arg-type 경고를 해소
# ─────────────────────────────────────────────────────────────────────────────
RequestHooks = Mapping[str, Iterable[Callable[[requests.Response], Any]]]
def _session_get(session: requests.Session, url: str, kwargs: Mapping[str, Any]) -> Response:
    kw: Dict[str, Any] = dict(kwargs)  # 복사해서 pop
    # ── allow_redirects: bool로 확정 ─────────────────────────────
    _ar_val = kw.pop("allow_redirects", True)
    allow_redirects: bool
    if isinstance(_ar_val, bool):
        allow_redirects = _ar_val
    else:
        allow_redirects = bool(_ar_val)

    # ── proxies: MutableMapping[str, str] 로 강제 ────────────────
    _proxies_in = kw.pop("proxies", None)
    proxies: MutableMapping[str, str] | None
    if isinstance(_proxies_in, MutableMapping):
        proxies = _proxies_in
    elif isinstance(_proxies_in, Mapping):
        proxies = dict(_proxies_in)
    else:
        proxies = None

    return session.get(
        url,
        params=cast(Mapping[str, Any] | None, kw.pop("params", None)),
        headers=cast(Mapping[str, str] | None, kw.pop("headers", None)),
        cookies=cast(MutableMapping[str, str] | None, kw.pop("cookies", None)),
        data=kw.pop("data", None),
        files=kw.pop("files", None),
        auth=cast(tuple[str, str] | AuthBase | None, kw.pop("auth", None)),
        timeout=cast(float | tuple[float | None, float | None] | None, kw.pop("timeout", None)),
        allow_redirects=allow_redirects,
        proxies=proxies,
        verify=kw.pop("verify", None),
        stream=cast(bool | None, kw.pop("stream", None)),
        hooks=cast(RequestHooks | None, kw.pop("hooks", None)),
        **kw,
    )

# ── CFG helpers (ENV 직접 접근 금지) ─────────────────────────────────────────
def _cfg_str(key: str, default: str = "") -> str:
    try:
        v = getattr(CFG, key)
        return (str(v).strip() if v is not None else default)
    except Exception:
        return default

def _cfg_bool(key: str, default: bool = False) -> bool:
    try:
        v = getattr(CFG, key)
        return bool(v)
    except Exception:
        return default

def _cfg_int(key: str, default: int) -> int:
    try:
        v = getattr(CFG, key)
        if v is None or v == "":
            return default
        return int(str(v).strip())
    except Exception:
        return default


def _record_retry_candidate(url: str, reason: str = "ssl_error") -> None:
    """
    재시도 후보를 jsonl로 남깁니다. (예: DATA_DIR/retry_candidates.jsonl)
    분석/재처리 파이프라인에서 이 파일을 스캔하여 재시도할 수 있습니다.
    """
    try:
        base_dir = _cfg_str("RETRY_CANDIDATE_DIR", "")
        base = Path(base_dir) if base_dir else (DATA_DIR / "quarantine")
        base.mkdir(parents=True, exist_ok=True)
        f = base / "ingest_retry_candidates.jsonl"
        payload = {"url": url, "reason": reason, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        with f.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(payload, ensure_ascii=False) + "\n")
        logger.warning("[INGEST][RETRY] tagged %s as %s → %s", url, reason, f)
    except Exception:
        logger.debug("[INGEST][RETRY] failed to record retry-candidate: %s (%s)", url, reason)

from langchain_core.tools import tool
from langchain_core.documents import Document  # re-export 타입에 사용
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 중앙 LLM(임베딩) 헬퍼
from core.llm import get_embedding_model
from core.config import CFG
from core.config import reload_config as reload_config  # in-place 갱신만 허용

# 게이트키핑/호스트 정규화
from settings_gatekeep import (
    gatekeep_enabled,
    url_allowed,
    _normalize_host,  # 로그용 (없으면 제거 가능)
)

# web_rag 유틸 모듈
from .utils import (
    session, http_get, DATA_DIR, _is_block_page, _looks_like_pdf_bytes,
    _looks_like_serialized_blob, _clean_text, _resolve_persist_dir, _FRESH_KEYS,
    normalize_url as _normalize_url,  # ← 요청 전 정규화에 사용
    safe_urljoin,                     # ← 안전 조인(정규화 동반)
)
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, unquote, quote
from chromadb.api.types import Include  # Chroma 메타 조회 타입
from collections import defaultdict as _dd

# ── incoming/seen hash helpers ────────────────────────────────────────────────
def _seen_hash_path(ns: str, pd: str) -> Path:
    """네임스페이스/퍼시스트디렉터리별 seen-hash 저장 경로."""
    base = Path(pd)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{ns}.__seen_sources__.json"

def _source_hash(title: str, url: str, content: str, raw: str, ctype: str) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update((title or "").encode("utf-8", "ignore"))
    h.update((url or "").encode("utf-8", "ignore"))
    # content가 없으면 raw_content를 사용 (PDF/HTML 원문 포함 가능)
    if content:
        h.update(content.encode("utf-8", "ignore"))
    elif raw:
        h.update(raw.encode("utf-8", "ignore"))
    h.update((ctype or "").encode("utf-8", "ignore"))
    return h.hexdigest()

def _compute_incoming_hashes(json_path: str) -> dict[str, str]:
    """web.json(배열/ndjson/래핑)에서 {source:hash} 맵 생성."""
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
        # 데이터 래핑 해제
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
        items = _flex_load(json_path) or []
    except Exception:
        return {}

    out: dict[str, str] = {}
    for r in items:
        if not isinstance(r, dict):
            continue
        url = _normalize_canonical_url((r.get("url") or r.get("source") or "").strip())
        if not url:
            continue
        title   = (r.get("title") or "").strip()
        content = (r.get("content") or r.get("snippet") or "").strip()
        raw     = (r.get("raw_content") or "").strip()
        ctype   = (r.get("content_type") or r.get("mime") or "").strip()
        out[url] = _source_hash(title, url, content, raw, ctype)
    return out

def _load_seen_source_hashes(ns: str, pd: str) -> dict[str, str]:
    p = _seen_hash_path(ns, pd)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_seen_source_hashes(ns: str, pd: str, m: dict[str, str]) -> None:
    p = _seen_hash_path(ns, pd)
    try:
        p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("[ingest] save seen hashes failed: %s", p)

# ── Metrics (optional) ───────────────────────────────────────────────────────
from typing import Callable as _TypingCallable
_record_chunks: Optional[_TypingCallable[..., Any]]
try:
    from tools.metrics import record_chunks as _record_chunks
except Exception:
    _record_chunks = None

def record_chunks(*, chars_sum: int, chunks_cnt: int, ns: str = "", part: str = "") -> None:
    """환경별 metrics.record_chunks 시그니처 차이를 흡수하는 안전 래퍼."""
    try:
        if _record_chunks is None:
            return
        try:
            import inspect
            params = set(inspect.signature(_record_chunks).parameters.keys())
        except Exception:
            params = {"chars_sum", "chunks_cnt"}  # 최소 호환
        payload: dict[str, Any] = {"chars_sum": chars_sum, "chunks_cnt": chunks_cnt}
        if "ns" in params:   payload["ns"] = ns
        if "part" in params: payload["part"] = part
        _record_chunks(**payload)
    except Exception:
        pass

# ---- 선택적 백엔드(존재시 사용, 미설치 OK) ----
try:
    import PyPDF2 as _pypdf2_mod
    _pypdf2: Optional[ModuleType] = _pypdf2_mod  # mypy-friendly: 모듈 또는 None
except Exception:
    _pypdf2 = None

# (선택) XLSX 요약용: pandas는 선택 의존성입니다.
try:
    import pandas as _pd  # type: ignore
except Exception:
    _pd = None  # pandas 미설치 시 비활성화

try:
    from pdfminer.high_level import extract_text as _pdfminer_extract_text_mod
    # pdfminer의 extract_text는 다양한 시그니처를 가지므로 가변 콜러블로 표기
    _pdfminer_extract_text: Optional[Callable[..., str]] = _pdfminer_extract_text_mod
except Exception:
    _pdfminer_extract_text = None

#
# ---- Chroma (type-check friendly dual import) ----
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    # mypy는 항상 community 경로의 Chroma 타입으로 고정
    from langchain_community.vectorstores.chroma import Chroma as Chroma
else:
    # 런타임에서는 langchain_chroma 우선, 없으면 community로 폴백
    try:
        from langchain_chroma import Chroma as Chroma
    except Exception:  # pragma: no cover
        from langchain_community.vectorstores.chroma import Chroma as Chroma

# Include 타입(리스트 리터럴은 cast로 지정 필요)
from typing import cast

# =============================================================================
# Quick Ingest (Findings 빠른 인덱스용) — 프록시를 함수처럼 호출하지 않도록 래퍼 제공
# =============================================================================

@runtime_checkable
class _QuickIngestProto(Protocol):
    """
    multiprocessing.Manager 등의 프록시가 구현해야 할 최소 인터페이스.
    """
    def add(
        self,
        *,
        urls: list[str],
        namespace: str,
        persist_directory: str,
        topic_slug: str,
        priority: int = 0,
        meta: Dict[str, Any] | None = None,
    ) -> int: ...


class _LocalQuickIngest:
    """
    기본(폴백) 구현: 별도 프로세스 없이 즉시 처리하는 더미 큐.
    필요한 환경에서는 set_quick_ingest_proxy(...)로 실제 프록시를 주입하십시오.
    """
    def __init__(self) -> None:
        pass

    def add(
        self,
        *,
        urls: list[str],
        namespace: str,
        persist_directory: str,
        topic_slug: str,
        priority: int = 0,
        meta: Dict[str, Any] | None = None,
    ) -> int:
        # 현재 파일 범위에서는 URL을 직접 인덱싱하지 않고, 호출부가
        # web_results_to_documents → documents_to_chroma 경로를
        # 이미 사용하고 있으므로 큐에 "등록되었다"는 의미로 개수만 반환.
        try:
            return int(len(urls or []))
        except Exception:
            return 0

# 모듈 전역 프록시(기본은 로컬 더미). 외부에서 실제 프록시로 교체 가능.
_quick_ingest_proxy: _QuickIngestProto = _LocalQuickIngest()

def set_quick_ingest_proxy(proxy: _QuickIngestProto) -> None:
    """
    외부(multiprocessing.Manager 등)에서 실제 프록시를 주입할 때 사용.
    """
    global _quick_ingest_proxy
    _quick_ingest_proxy = proxy

def quick_ingest_add(
    urls: Iterable[str],
    *,
    namespace: str,
    persist_directory: str,
    topic_slug: str,
    priority: int = 0,
    meta: Dict[str, Any] | None = None,
) -> int:
    """
    ✅ 권장 호출 경로: 프록시의 .add(...)를 안전하게 위임.
    '_RootProxy object is not callable'를 방지하기 위한 래퍼.
    """
    try:
        return int(
            _quick_ingest_proxy.add(
                urls=[u for u in urls if isinstance(u, str) and u.strip()],
                namespace=str(namespace),
                persist_directory=str(persist_directory),
                topic_slug=str(topic_slug),
                priority=int(priority),
                meta=meta or {},
            )
        )
    except Exception as e:
        logger.warning("[quick_ingest_add] proxy.add failed: %s", e)
        return 0

# 🧩 임시 호환 레이어: 과거 quick_ingest(...) 형태를 그대로 호출해도 동작
def quick_ingest(*args, **kwargs) -> int:  # TEMP compatibility; 제거 예정
    return quick_ingest_add(*args, **kwargs)


# =============================================================================
# RAG: Documents conversion & Chroma ingestion/retrieval
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# 공용 HTTPS 세션 (재시도/CA 번들 강제)
#  - 기존 .utils.session 을 기반으로 설정을 보강하고 재사용합니다.
# ─────────────────────────────────────────────────────────────────────────────
_SESSION_ENFORCED: Optional[requests.Session] = None
def get_requests_session() -> requests.Session:
    global _SESSION_ENFORCED
    if _SESSION_ENFORCED is not None:
        return _SESSION_ENFORCED
    try:
        s = session  # 기존 utils.session 사용
    except Exception:
        s = requests.Session()
    # 재시도 정책(5xx/429) + 풀 사이즈
    retry = Retry(
        total=3, connect=3, read=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["HEAD", "GET", "OPTIONS"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=32)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    # certifi CA 번들 강제
    s.verify = certifi.where()
    # UA가 비어있을 수 있는 사이트 대비
    if not s.headers.get("User-Agent"):
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; WebRAG/1.0; +https://example.local)",
            "Accept": "*/*",
        })
    _SESSION_ENFORCED = s
    return s

def _resolve_ns(
    namespace: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> str:
    """
    네임스페이스 결정 우선순위:
      1) collection_name
      2) namespace
      3) CFG.CHROMA_NAMESPACE
      4) CFG.TOPIC_SLUG (suffix -default)
      5) "default"
    """
    if collection_name and collection_name.strip():
        return collection_name.strip()
    if namespace and namespace.strip():
        return namespace.strip()
    env_ns = (getattr(CFG, "CHROMA_NAMESPACE", "") or "").strip()
    if env_ns:
        return env_ns
    topic_slug = (getattr(CFG, "TOPIC_SLUG", "") or "").strip()
    if topic_slug:
        return f"{topic_slug}-default"
    return "default"

# PDF/HTML 로더 유틸
import re as _re
_PDF_URL_RE = _re.compile(r"\.pdf($|\?)|filedownload|filedown(type)?=|/fileDown|/download", _re.I)

def _looks_like_pdf_url(url: str) -> bool:
    return bool(_PDF_URL_RE.search(url or ""))

_PDF_HEADERS = {"Accept": "application/pdf"}

def _allow_insecure_ssl() -> bool:
    return _cfg_bool("ALLOW_INSECURE_SSL", False)



# ─────────────────────────────────────────────────────────────────────────────
# URL 정규화/유일화 보조
# ─────────────────────────────────────────────────────────────────────────────
_TRACKING_KEYS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id",
    "gclid","fbclid","igshid","mc_cid","mc_eid","ref","ref_src","ref_url",
    "spm","si","sck","ved","ei","yclid","msclkid","pk_campaign","pk_kwd",
}

# 문서 동일성에 영향 없는 가변 파라미터(페이지/슬라이드 등)
_VOLATILE_PART_PARAMS = {"part","index","page","slide"}

def _strip_tracking_params(qs_items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for k, v in qs_items:
        lk = (k or "").lower()
        if lk in _TRACKING_KEYS or lk.startswith("utm_") or lk in _VOLATILE_PART_PARAMS:
            continue
        out.append((k, v))
    return out

def _normalize_canonical_url(u: str) -> str:
    """
    강한 URL 정규화:
    - file:// → 절대경로 URI(Path.resolve().as_uri())로 일원화 **하되 fragment/쿼리를 보존**
      (PPTX/PDF split 조각 식별자: #part, #index 등 유지)
    - http(s):// → fragment 제거, 트래킹 파라미터 제거
      (utm_*, gclid 등) 및 AMP 흔적(/amp, .amp, *.amp.dev) 제거
    - m. 호스트를 www.로 보정(가능할 때)
    """
    raw = (u or "").strip()
    if not raw:
        return ""
    try:
        nu = _normalize_url(raw)
    except Exception:
        nu = raw

    try:
        p = urlparse(nu)
        scheme_lower = (p.scheme or "").lower()

        # 1) file:// — OS 경로를 절대 URI로 일원화 (fragment/쿼리 보존)
        if scheme_lower == "file":
            path_raw = unquote(p.path or "")
            frag_raw = p.fragment or ""
            query_raw = p.query or ""
            try:
                # Windows "file:///D:/..." 케이스 보정
                if path_raw.startswith("/") and len(path_raw) >= 3 and path_raw[2] == ":":
                    path_raw = path_raw.lstrip("/")
                base_uri = Path(path_raw).resolve().as_uri()
            except Exception:
                # as_uri 실패 시, 최소한 표준 포맷으로 재구성 (fragment/쿼리 유지)
                base_uri = urlunparse(p._replace(fragment="", params=""))

            # file:// 는 조각 식별(슬라이드/페이지) 정보를 유지해야 하므로 fragment 보존
            if query_raw:
                base_uri = f"{base_uri}?{query_raw}"
            if frag_raw:
                base_uri = f"{base_uri}#{frag_raw}"
            return base_uri

        # 0) http(s) 등은 fragment 제거
        p = p._replace(fragment="")
        # host 정규화: m. → www. (가능한 경우)
        host = (p.netloc or "").lower()
        # 도메인 예외: dailypharm는 모바일/데스크톱 경로 규칙이 달라 'm.' 강제변환 금지
        if not host.endswith("dailypharm.com") and host.startswith("m.") and len(host) > 2:
            host = "www." + host[2:]
        # AMP 프록시 제거 등 기존 로직은 유지
        # 일부 AMP 프록시 도메인 흔적 제거(가능한 범위 내에서만)
        if host.endswith(".amp.dev"):
            host = host.removesuffix(".amp.dev")

        # AMP 경로 흔적 제거( /amp, .amp )
        path = p.path or ""
        if path.endswith("/amp"):
            path = path[:-4] or "/"
        if path.endswith(".amp"):
            path = path[:-4] or "/"

        # 쿼리에서 추적/가변 파라미터 제거
        items = parse_qsl(p.query, keep_blank_values=True)
        items = _strip_tracking_params(items)
        query = urlencode(items, doseq=True)

        # 기본 포트 제거
        netloc = host
        if netloc.endswith(":80"):
            netloc = netloc[:-3]
        if netloc.endswith(":443"):
            netloc = netloc[:-4]

        cano = urlunparse((p.scheme.lower(), netloc, path, "", query, ""))  # fragment 없음
        return cano
    except Exception:
        return nu.split("#", 1)[0]

def _base_file_key(u: str) -> str:
    """
    PDF/PPTX 등의 '파일 단위' 유일화 키. 쿼리/fragment 제거, 호스트 소문자.
    """
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower()
        return urlunparse((p.scheme.lower(), host, p.path or "", "", "", ""))
    except Exception:
        return (u or "").strip()
    
def _priority_sort_key(item: dict) -> tuple[int, int, int, int, str]:
    """
    로컬 인제스트 우선순위 정렬키:
      1) file:// 우선 (0) → http/https (1)
      2) file:// 이면서 파일명이 findings.md 인가 (0) → 아니면 (1)
      3) 확장자/콘텐츠 유형 우선순위: pdf(0) > pptx(1) > xlsx(2) > 기타(3)
      4) (선택) 파일 크기 bytes 큰 순 정렬을 위해 -bytes 사용 → 파이썬 sort는 오름차순이므로 부호 반전
      5) 안정 Tie-breaker: source/url 문자열
    """
    try:
        u = (item.get("url") or item.get("source") or "").strip()
        ct = (item.get("content_type") or item.get("mime") or "").lower()
        is_file = 0 if u.lower().startswith("file://") else 1
        # 파일명 추출
        try:
            p = urlparse(u)
            fname = Path(unquote(p.path or "")).name.lower()
        except Exception:
            fname = ""
        is_findings = 0 if (is_file == 0 and fname == "findings.md") else 1
        # 확장자/타입 랭크
        ext = (Path(fname).suffix.lower() if fname else Path(urlparse(u).path or "").suffix.lower())
        rank = 3
        if "application/pdf" in ct or ext == ".pdf":
            rank = 0
        elif "presentationml" in ct or ext == ".pptx":
            rank = 1
        elif "spreadsheetml" in ct or ext == ".xlsx":
            rank = 2
        # bytes는 클수록 우선 → 오름차순 정렬을 위해 부호 반전
        try:
            neg_bytes = -int(item.get("bytes", 0) or 0)
        except Exception:
            neg_bytes = 0
        src = (item.get("source") or u or "")
        return (is_file, is_findings, rank, neg_bytes, str(src))
    except Exception:
        # 예외 시 맨 뒤로
        return (1, 1, 3, 0, str(item))


_NORM_I = 0  # [NORM] 로그 샘플링 카운터(모듈 전역)
def _normalize_before_request(u: str) -> str:
    """
    네트워크 요청 직전 안전 정규화:
      - 스킴/호스트 정규화(모바일/AMP→www 포함)
      - 추적 파라미터 제거, 퍼센트 인코딩 표준화
      - fragment 제거(단, file:// 는 조각 식별을 위해 fragment 보존)
    """
    raw = (u or "").strip()
    if not raw:
        return ""
    nu = _normalize_canonical_url(raw)
    # [NORM] 로그 스팸 억제: 변경된 경우만, 초기/샘플 간격에만 출력
    if nu != raw:
        global _NORM_I
        _NORM_I += 1
        if _NORM_I in (1, 50, 200) or (_NORM_I % 500 == 0):
            logger.debug("[NORM][%d] %s → %s", _NORM_I, raw, nu)
    return nu

def _fetch_binary(url: str, timeout: int = 10) -> bytes:
    """
    PDF/바이너리 안전 가져오기:
      - 항상 certifi 번들로 검증(verify=certifi.where()).
      - SSLError 시 verify=False 폴백은 하지 않음.
      - 대신 상위 로직이 재시도 후보로 태깅할 수 있도록 _PdfSslError를 발생.
    """
    try:
        # ✅ 요청 전 정규화(안전망)
        url = _normalize_before_request(url)
        cap = _cfg_int("WEB_PDF_FETCH_MAX_BYTES", _cfg_int("WEB_PDF_MAX_BYTES", 20_000_000))
        # connect/read 타임아웃은 환경값을 기본으로 사용
        _to = ( _REQ_CONN_TIMEOUT, _REQ_READ_TIMEOUT )
        s = get_requests_session()
        r = _session_get(s, url, {
            "headers": _PDF_HEADERS,
            "timeout": _to,   # (connect, read)
            "stream": True,
            "verify": s.verify,
        })
        r.raise_for_status()

        # Content-Length 사전 체크(있을 때만)
        try:
            clen = int((r.headers.get("Content-Length") or "0").strip() or "0")
        except Exception:
            clen = 0
        if cap > 0 and clen > cap:
            logger.warning("[INGEST][PDF] content-length exceeds cap: %s (%d > %d)", url, clen, cap)
            raise ValueError(f"PDF too large by header: {clen} > {cap}")

        # 스트리밍 수신 + 누적 바이트 캡
        buf = io.BytesIO()
        for chunk in r.iter_content(chunk_size=8192):
            if not chunk:
                continue
            buf.write(chunk)
            if cap > 0 and buf.tell() > cap:
                logger.warning("[INGEST][PDF] stream exceeded cap at ~%d bytes: %s", buf.tell(), url)
                raise ValueError(f"PDF too large by stream: {buf.tell()} > {cap}")
        return buf.getvalue()
    except _SSLError as e:
        # 상부에서 태깅 후 HTML 폴백 시도/스킵 결정을 하도록 신호
        raise _PdfSslError(str(e))
    except Exception:
        raise

def _decode_bytes(data: bytes) -> str:
    """바이트 → 텍스트 (requests/chardet 유사 전략, BOM/헤더 미존재 시에도 방어)"""
    if not data:
        return ""
    try:
        # BOM 우선
        if data.startswith(codecs.BOM_UTF8):
            return data.decode("utf-8", "ignore")
    except Exception:
        pass
    try:
        import chardet
        det = chardet.detect(data or b"")
        enc = (det or {}).get("encoding") or "utf-8"
        return data.decode(enc, "ignore")
    except Exception:
        try:
            return data.decode("utf-8", "ignore")
        except Exception:
            return data.decode("latin-1", "ignore")

def _fetch_with_fallbacks(url: str, *, timeout: float = 8.0) -> tuple[bytes, str]:
    """
    yakup.com 등 비표준 헤더/포트/압축 문제를 단계적으로 완화하며 (content, final_url)을 반환.
    순서: ① 정규화 URL → ② 기본포트 제거 → ③ Accept-Encoding: identity → ④ http 폴백 → ⑤ urllib.request
    """
    s = get_requests_session()
    req_kwargs = {"timeout": ( _REQ_CONN_TIMEOUT, _REQ_READ_TIMEOUT ), "headers": {"User-Agent": _UA}}
    u0 = _normalize_before_request(url)
    # ① 1차 시도
    try:
        r = _session_get(s, u0, req_kwargs)
        r.raise_for_status()
        return r.content, str(r.url)
    except Exception as e1:
        # ② 기본 포트 제거(:80/:443)
        try:
            u1 = u0  # ← 안전 초기화(이후 단계에서 참조)
            p = urlparse(u0)
            netloc = p.netloc.replace(":80", "").replace(":443", "")
            u1 = urlunparse(p._replace(netloc=netloc))
            r = _session_get(s, u1, req_kwargs)
            r.raise_for_status()
            return r.content, str(r.url)
        except Exception as e2:
            # ③ 압축/헤더 완화
            try:
                req_kwargs2 = {"timeout": ( _REQ_CONN_TIMEOUT, _REQ_READ_TIMEOUT ),
                               "headers": {"User-Agent": _UA, "Accept-Encoding": "identity"}}
                r = _session_get(s, u1, req_kwargs2)
                r.raise_for_status()
                return r.content, str(r.url)
            except Exception as e3:
                # ④ http 폴백
                try:
                    p2 = urlparse(u1)
                    if p2.scheme == "https":
                        u2 = urlunparse(p2._replace(scheme="http"))
                        r = _session_get(s, u2, req_kwargs2)
                        r.raise_for_status()
                        return r.content, str(r.url)
                except Exception:
                    pass
                # ⑤ 최종 폴백: urllib (헤더 파서 무시)
                try:
                    import urllib.request
                    with urllib.request.urlopen(u1, timeout=_REQ_READ_TIMEOUT) as fp:
                        return fp.read(), u1
                except Exception:
                    raise e1


def _pdf_bytes_to_text(data: bytes) -> str:
    """
    PDF 바이트 → 텍스트
      WEB_PDF_MAX_BYTES (기본 20000000 = 20MB)  ← 바이트 가드
      WEB_PDF_MAX_PAGES (기본 40)               ← 페이지 상한
      WEB_PDF_MAX_CHARS (기본 200000)           ← 총 글자 수 상한
    """
    # 0) 용량 가드: 과대 PDF는 즉시 중단
    max_bytes = _cfg_int("WEB_PDF_MAX_BYTES", 20_000_000)
    if max_bytes > 0 and len(data or b"") > max_bytes:
        raise ValueError(f"PDF too large: {len(data)} bytes > {max_bytes}")

    # 1) 페이지/문자 상한
    max_pages = _cfg_int("WEB_PDF_MAX_PAGES", 40)
    max_chars = _cfg_int("WEB_PDF_MAX_CHARS", 200_000)

    # 2) PyPDF2 우선
    if _pypdf2 is not None:
        try:
            reader = _pypdf2.PdfReader(io.BytesIO(data))
            try:
                if getattr(reader, "is_encrypted", False):
                    reader.decrypt("")
            except Exception:
                pass

            # 페이지 상한 적용
            n = min(max(1, int(max_pages or 1)), len(reader.pages))
            out_parts, total_len = [], 0
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

    # 3) pdfminer 폴백 (page_numbers 제한 적용)
    if _pdfminer_extract_text is not None:
        try:
            n = max(1, int(max_pages or 1))
            text = _pdfminer_extract_text(
                io.BytesIO(data),
                page_numbers=list(range(n))
            ) or ""
            text = text.strip()
            if max_chars > 0 and len(text) > max_chars:
                text = text[:max_chars]
            return text
        except Exception as e:
            logger.debug("pdfminer extract failed: %s", e)

    return ""

def _load_html_as_text(url: str, timeout: int = 10) -> str:
    """
    HTML 페이지 로딩 (yakup 헤더 문제/포트/압축/SSL 예외 및 dailypharm 404 경로 차이 보정 포함)
    """
    # 1) 일반 경로: 완화된 fetch로 바이트 수신 → 디코드 → 텍스트 추출
    try:
        content, final_url = _fetch_with_fallbacks(url, timeout=timeout)
        html = _decode_bytes(content)
    except _SSLError:
        if _allow_insecure_ssl():
            logger.warning("[SSL] SSLError on %s — retrying once with verify=False (ALLOW_INSECURE_SSL=1)", url)
            s = get_requests_session()
            r = _session_get(s, _normalize_before_request(url), {
                "timeout": ( _REQ_CONN_TIMEOUT, _REQ_READ_TIMEOUT ),
                "headers": {"User-Agent": _UA},
                "verify": False,
            })
            r.raise_for_status()
            html = r.text
            final_url = str(r.url)
        else:
            raise
    except requests.HTTPError as he:
        # 2) 404 등일 때 도메인/경로 보정 후 재시도
        p_orig = urlparse(url)
        p_norm = urlparse(_normalize_before_request(url))
        # dailypharm 특수: /newsView.html → /Users/News/NewsView.html
        if p_norm.netloc.endswith("dailypharm.com") and p_norm.path.lower() == "/newsview.html":
            q2 = p_norm._replace(path="/Users/News/NewsView.html")
            try:
                content, final_url = _fetch_with_fallbacks(urlunparse(q2), timeout=timeout)
                html = _decode_bytes(content)
            except Exception:
                # 모바일 원본으로 최후 재시도
                try:
                    content, final_url = _fetch_with_fallbacks(url, timeout=timeout)
                    html = _decode_bytes(content)
                except Exception:
                    raise
        # 정규화로 호스트/스킴이 달라졌다면 원본으로 재시도
        elif (p_orig.netloc != p_norm.netloc) or (p_orig.scheme != p_norm.scheme):
            content, final_url = _fetch_with_fallbacks(url, timeout=timeout)
            html = _decode_bytes(content)
        else:
            raise
    except Exception:
        # 마지막 방어선: 원본으로 재시도
        content, final_url = _fetch_with_fallbacks(url, timeout=timeout)
        html = _decode_bytes(content)

    # 3) HTML → 텍스트 추출 (기존 로직 유지)
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        text = _re.sub(r"[ \t]+", " ", text)
        text = _re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    except Exception:
        text = _re.sub(r"<[^>]+>", " ", html or "")
        text = _re.sub(r"\s{2,}", " ", text)
        return text.strip()
    
def web_results_to_documents(results: Sequence[Dict[str, Any]]) -> List[Document]:
    """
    web.json 항목(또는 검색 결과 dict 리스트)을 LangChain Document 리스트로 변환.
    - file:// 은 네트워크 요청 없이 item.content 사용
    - raw_content(HTML)가 있으면 패스 1로 처리
    - PDF 스멜나면 PDF 바이트 로더 우선, 실패시 HTML 폴백
    """
    docs: List[Document] = []
    # 정규화 후 중복 차단(같은 URL, 같은 파일 단위)
    _seen_urls: set[str] = set()
    _seen_files: set[str] = set()

    def _guess_content_type_from_path(path: str, default: str = "text/plain") -> str:
        ext = Path(path).suffix.lower()
        if ext == ".pdf": return "application/pdf"
        if ext in (".html", ".htm"): return "text/html"
        if ext in (".pptx", ".xlsx", ".docx"): return "application/vnd.openxmlformats-officedocument"
        if ext in (".txt", ".md", ".markdown"): return "text/plain"
        return default

    for item in results or []:
        url: str = (item.get("url") or item.get("source") or "").strip()
        title: str = (item.get("title") or "").strip()
        item_content: str = (item.get("content") or "").strip()
        raw_content: str = (item.get("raw_content") or "").strip()

        if not url:
            if item_content:
                docs.append(Document(
                    page_content=item_content,
                    metadata={"source": "", "title": title or "(local)", "content_type": "text/plain"}
                ))
            continue

        try:
            # ✅ 처리 전 정규화 및 fragment 제거
            url = _normalize_before_request(url)
            # 정규화된 URL 중복 차단
            if url and url in _seen_urls:
                continue
            if url:
                _seen_urls.add(url)

            parsed = urlparse(url)
            scheme = (parsed.scheme or "").lower()
            url_no_frag = url  # 이미 fragment 제거됨

            # (선택) 같은 PDF/PPTX 파일의 다중 파트 유입 차단
            if parsed.path:
                lp = parsed.path.lower()
                if lp.endswith(".pdf") or lp.endswith(".pptx"):
                    base_key = _base_file_key(url_no_frag)
                    if base_key in _seen_files:
                        continue
                    _seen_files.add(base_key)

            # 1) file:// — content만 사용
            if scheme == "file":
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

            # 2) raw_content 우선 (보통 HTML)
            if raw_content:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(raw_content, "lxml")
                    for tag in soup(["script", "style", "noscript"]):
                        tag.decompose()
                    text = soup.get_text(separator="\n")
                    text = _re.sub(r"[ \t]+", " ", text)
                    text = _re.sub(r"\n{3,}", "\n\n", text).strip()
                except Exception:
                    text = _re.sub(r"<[^>]+>", " ", raw_content)
                    text = _re.sub(r"\s{2,}", " ", text).strip()

                if text:
                    docs.append(Document(
                        page_content=text,
                        metadata={"source": url, "title": title or "Web", "content_type": "text/html"},
                    ))
                    continue

            # 3) PDF 의심 → PDF 파서 우선(내부: PyPDF2 → pdfminer 폴백) + 0자 방지 가드
            if _looks_like_pdf_url(url_no_frag):
                try:
                    pdf_bytes = _fetch_binary(url_no_frag)
                    pdf_text = _pdf_bytes_to_text(pdf_bytes)
                    if pdf_text and len(pdf_text.strip()) >= 30:
                        docs.append(
                            Document(
                                page_content=str(pdf_text),
                                metadata={
                                    "source": url,
                                    "title": title or "PDF",
                                    "content_type": "application/pdf",
                                },
                            )
                        )
                        continue
                    # 최종 가드: 0자 또는 과소 텍스트면 드랍(HTML 폴백하지 않음)
                    logger.warning("[ingest][pdf] empty/too-short text after fallback; dropping url=%s", url_no_frag)
                    continue
                except _PdfSslError:
                    # ✅ SSL 오류: 재시도 후보로 태깅하고 HTML 폴백 시도
                    _record_retry_candidate(url_no_frag, reason="ssl_error")
                    logger.warning("[INGEST][SSL] ssl_error tagged & skipped PDF parse → fallback to HTML: %s", url_no_frag)
                except Exception as e:
                    msg = str(e)
                    # DNS 해석 실패 계열은 폴백/재시도 없이 즉시 스킵
                    if ("NameResolutionError" in msg) or ("Failed to resolve" in msg) or ("Temporary failure in name resolution" in msg):
                        logger.warning("[web_rag] DNS failure; skip (no fallback): %s", e)
                        continue
                    logger.debug("[web_rag] PDF parse failed; fallback to HTML: %s", e)

            # 4) HTML 로더
            html_text = _load_html_as_text(url_no_frag)
            if html_text:
                docs.append(Document(
                    page_content=str(html_text),
                    metadata={"source": url, "title": title or "Web", "content_type": "text/html"},
                ))
                continue

            # 5) 마지막 폴백: item.content
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
    """web.json(배열/NDJSON/단일 dict/래핑 dict)을 유연하게 읽어 Document 리스트로 변환."""
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
        # 데이터 래핑 해제
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

    # ──────────────────────────────────────────────────────────
    # [ADD] 로컬 우선 정렬 + cap 적용
    #   - 의도: cap(1500) 이전에 findings.md > PDF > PPTX > XLSX > 기타
    #   - 기준 cap: LOCAL_RAG_MAX_DOCS (없으면 0 = 무제한)
    #   - 정렬은 전체에 적용하되, file:// 항목이 자연스럽게 상단 배치됨
    # ──────────────────────────────────────────────────────────
    try:
        if isinstance(resources, list) and resources:
            before_n = len(resources)
            # 정렬 (in-place)
            resources.sort(key=_priority_sort_key)
            # cap 적용 (있을 때만)
            cap = _cfg_int("LOCAL_RAG_MAX_DOCS", 0)
            if isinstance(cap, int) and cap > 0 and len(resources) > cap:
                resources = resources[:cap]
                logger.info(
                    "[ingest][local-priority] resources sorted & capped: %d → %d (cap=%d)",
                    before_n, len(resources), cap
                )
            else:
                logger.debug("[ingest][local-priority] resources sorted (no cap or under cap)")
    except Exception as e:
        logger.debug("[ingest][local-priority] sort/cap skipped: %s", e)

    # 입력 단계에서도 URL 정규화 후 유일화가 적용되므로 그대로 변환
    docs = web_results_to_documents(resources)
    logger.info("web_page_json_to_documents: %d docs from %s", len(docs), json_file)
    return docs


# ---- Vector store cache (persist_dir, collection) ----
_VS_CACHE: Dict[Tuple[str, str], Chroma] = {}
_CLEARED_ONCE_KEYS: set[tuple[str, str]] = set()

def _default_chroma_dir(namespace: str) -> str:
    return _resolve_persist_dir(namespace, persist_directory=None)

_CLEARED_RUNTIME_KEYS: set[tuple[str, str]] = set()

def _clear_once_guard(pd: str, ns: str, *, reason: str = "") -> bool:
    if _cfg_bool("CLEAR_GUARD_DISABLE", False):
        return True
    key = (pd, ns)
    if key in _CLEARED_RUNTIME_KEYS:
        logger.debug("[INIT] clear skipped (once-guard): ns='%s' dir='%s' reason=%s", ns, pd, reason or "-")
        return False
    _CLEARED_RUNTIME_KEYS.add(key)
    return True


def _resolve_ns_for_docs(base_ns: str, is_web: Optional[bool]) -> tuple[str, bool]:
    """
    split NS 모드면 CHROMA_NAMESPACE_WEB/LOCAL 중 하나를 사용.
    아니면 base_ns 유지. (ns, split_applied)
    """
    ns_web = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    if ns_web and ns_loc and is_web is not None:
        return (ns_web if is_web else ns_loc), True
    return base_ns, False

def _is_web_source(meta: dict) -> Optional[bool]:
    """http/https → True, file:// 또는 로컬경로 → False, 판단불가 → None"""
    src = (meta or {}).get("source") or ""
    s = src.strip().lower()
    if s.startswith("http://") or s.startswith("https://"):
        return True
    if s.startswith("file://"):
        return False
    if _re.match(r"^[a-z]:[\\/]", s) or s.startswith("\\\\"):
        return False
    return None

def _extract_local_path(meta: dict) -> Optional[str]:
    """
    Document 메타에서 로컬 경로를 추출합니다.
    우선순위: file_path → source(file:// 또는 로컬 경로) → url
    """
    from urllib.parse import urlparse, unquote
    src = (meta or {}).get("file_path") or (meta or {}).get("source") or (meta or {}).get("url") or ""
    s = (src or "").strip()
    if not s:
        return None
    # file:// 스킴
    if s.lower().startswith("file://"):
        try:
            parsed = urlparse(s)
            return unquote(parsed.path or "") or None
        except Exception:
            return None
    # Windows/UNC or POSIX 경로
    if _re.match(r"^[a-zA-Z]:[\\/]", s) or s.startswith("\\\\") or s.startswith("/"):
        return s
    return None


def _local_mtime_key(meta: dict) -> str:
    """
    로컬 파일이면 mtime(ns) 또는 초단위를 문자열로 반환. 없으면 "".
    (doc_id/버전키에 섞어 변경 파일만 재인덱싱)
    """
    try:
        p = _extract_local_path(meta) or ""
        if not p:
            return ""
        st = Path(p).stat()
        # ns 단위가 있으면 우선 사용
        ns = getattr(st, "st_mtime_ns", None)
        if isinstance(ns, int) and ns > 0:
            return str(ns)
        return str(int(st.st_mtime))
    except Exception:
        return ""

def clear_vector_store(namespace: Optional[str] = None, persist_directory: Optional[str] = None) -> str:
    """
    벡터 저장소 디렉터리를 제거 후 재생성. 캐시/핸들도 함께 초기화.
    글로벌(인자 둘 다 None) 클리어는 ENV ALLOW_GLOBAL_CLEAR=1 일 때만 허용.
    """
    import shutil, stat, gc, time as _t

    ns = _resolve_ns(namespace=namespace, collection_name=None)
    pd = _resolve_persist_dir(ns, persist_directory)

    # 런타임 가드: 동일 (pd, ns) 중복 초기화를 억제
    if not _clear_once_guard(pd, ns, reason="clear_vector_store()"):
        return pd

    if (namespace is None and persist_directory is None) and (not _cfg_bool("ALLOW_GLOBAL_CLEAR", False)):
        logger.info("[INIT] clear_vector_store skipped (global clear disabled). ns='%s' dir='%s'", ns, pd)
        return pd

    vs = _VS_CACHE.pop((pd, ns), None)
    try:
        client = getattr(vs, "_client", None)
        for meth in ("persist", "reset", "teardown", "close", "stop", "shutdown"):
            fn = getattr(client, meth, None)
            if callable(fn):
                try: fn()
                except Exception: pass
    except Exception:
        pass
    try: _VS_CACHE.clear()
    except Exception: pass
    vs = None  # drop reference for GC
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
    """
    한 번만 초기 클리어. 트리거: CFG.CLEAR_CHROMA_ON_START 또는
    ENV CLEAR_ON_FIRST_VECTOR/CLEAR_CHROMA_ON_START.
    """
    if not (_cfg_bool("CLEAR_CHROMA_ON_START", False) or
            _cfg_bool("CLEAR_ON_FIRST_VECTOR", False)):
        return False

    ns = _resolve_ns(namespace=namespace, collection_name=None)
    pd = _resolve_persist_dir(ns, persist_directory)
    key = (pd, ns)

    # 런타임 가드도 동시에 마킹(중복 초기화/로그 억제)
    if key in _CLEARED_RUNTIME_KEYS:
        logger.debug("[INIT] clear_once skipped (runtime-guard already cleared): ns='%s' dir='%s'", ns, pd)
        return False

    if key in _CLEARED_ONCE_KEYS:
        logger.debug("[INIT] clear_once skipped (already cleared): ns='%s' dir='%s'", ns, pd)
        return False

    clear_vector_store(namespace=ns, persist_directory=pd)
    _CLEARED_ONCE_KEYS.add(key)
    _CLEARED_RUNTIME_KEYS.add(key)
    logger.info("[INIT] vector store cleared once (ns='%s', dir='%s')", ns, pd)
    return True

# ─────────────────────────────────────────────────────────────────────────────
# 임베딩 모델 선택/로그 강화 (정적체커 안전 호출)
# ─────────────────────────────────────────────────────────────────────────────
import inspect

def _resolve_embedding_model_name() -> str:
    """임베딩 모델 결정: RAG_EMBEDDING_MODEL → GEMINI_EMBEDDING_MODEL → 'text-embedding-004'."""
    name = (getattr(CFG, "RAG_EMBEDDING_MODEL", "") or "").strip()
    if not name:
        name = (getattr(CFG, "GEMINI_EMBEDDING_MODEL", "") or "").strip()
    if not name:
        name = "text-embedding-004"
    return name

def _get_embeddings(embedding=None):
    """
    - 외부에서 embedding 주입 시 그대로 사용
    - 아니면 get_embedding_model의 실제 시그니처를 점검해
      (무인자 | model_name= | model=) 중 가능한 방식으로 호출
    - 정적체커 충돌 회피를 위해 Any 캐스팅 사용
    """
    if embedding is not None:
        return embedding
    model_name = _resolve_embedding_model_name()
    ctor: Any = get_embedding_model  # 정적체커 회피

    try:
        params = list(inspect.signature(ctor).parameters.keys())
    except Exception:
        params = []

    try:
        if not params:
            # 무인자
            emb = ctor()
            used = "no-arg"
        elif "model_name" in params:
            emb = ctor(model_name=model_name)
            used = "model_name"
        elif "model" in params:
            emb = ctor(model=model_name)
            used = "model"
        else:
            # 알 수 없는 케이스 → 무인자 폴백
            emb = ctor()
            used = "fallback:no-arg"
    except TypeError:
        # 런타임 타입 에러시 최종 폴백
        emb = ctor()
        used = "fallback:typeerror:no-arg"
    except Exception:
        emb = ctor(); used = "fallback:exception:no-arg"

    try:
        logger.info("[ingest] embedding model resolved: %s (ctor=%s, via=%s)",
                    model_name, getattr(ctor, "__name__", str(ctor)), used)
    except Exception:
        pass

    return emb


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
    cs = (_cfg_int("RAG_CHUNK_CHARS", 2400) if chunk_size is None else int(chunk_size))
    ov = (_cfg_int("RAG_CHUNK_OVERLAP", 200) if chunk_overlap is None else int(chunk_overlap))
    cs = max(300, min(cs, 6000))
    ov = max(0, min(ov, int(cs * 0.5)))
    splitter = RecursiveCharacterTextSplitter(chunk_size=cs, chunk_overlap=ov)
    return splitter.split_documents(documents)

def _is_pptx_meta(meta: dict) -> bool:
    """메타정보로 PPTX 여부를 추정합니다."""
    try:
        src = (meta or {}).get("source") or (meta or {}).get("file_path") or ""
        ctype = (meta or {}).get("content_type") or ""
        if isinstance(src, str) and src.lower().endswith(".pptx"):
            return True
        if isinstance(ctype, str) and "presentationml" in ctype:
            # application/vnd.openxmlformats-officedocument.presentationml.presentation
            return True
    except Exception:
        pass
    return False


def _is_xlsx_meta(meta: dict) -> bool:
    """메타정보로 XLSX 여부를 추정합니다."""
    try:
        src = (meta or {}).get("source") or (meta or {}).get("file_path") or ""
        ctype = (meta or {}).get("content_type") or ""
        if isinstance(src, str) and src.lower().endswith(".xlsx"):
            return True
        if isinstance(ctype, str) and "spreadsheetml" in ctype:
            # application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
            return True
    except Exception:
        pass
    return False

def _format_won(n: float | int) -> str:
    """원 단위 간략 표기(천단위 콤마 + 필요 시 억 단위 병기)."""
    try:
        v = float(n)
    except Exception:
        return str(n)
    if abs(v) >= 100_000_000:
        eok = v / 100_000_000.0
        return f"{int(v):,}원 (~{eok:.2f}억원)"
    return f"{int(v):,}원"

def _xlsx_sheet_summaries(path: Path, *, max_rows: int = 200, max_cols: int = 20, max_docs: int = 5) -> list[str]:
    """
    XLSX 상단 일부(최대 200x20)만 스캔하여 간단 요약문 생성.
    - 연/월, 매체/채널, 합계/총액 후보 컬럼을 감지해 한두 줄 문장으로 요약.
    - 과도한 생성 방지를 위해 시트당 1문장, 파일당 max_docs 제한.
    """
    if _pd is None:
        return []
    out: list[str] = []
    try:
        xls = _pd.ExcelFile(path)  # type: ignore
    except Exception:
        return out

    year_pat = _re.compile(r"^(20\d{2}|19\d{2})$")
    month_pat = _re.compile(r"^(1[0-2]|0?[1-9])$")
    # 지출/광고비/합계 후보
    cost_like = ("광고비", "비용", "집행", "지출", "총액", "합계", "total", "sum", "spend", "cost")
    channel_like = ("디지털", "digital", "tv", "지상파", "케이블", "소셜", "search", "display", "youtube")

    for sheet in xls.sheet_names[: max_docs * 2]:  # 느슨히 제한
        try:
            df = xls.parse(sheet_name=sheet, nrows=max_rows, usecols=range(0, max_cols))  # type: ignore
        except Exception:
            continue
        if df is None or df.empty:
            continue
        # 컬럼명 정규화
        cols = [str(c).strip() for c in df.columns]
        df.columns = cols
        # 숫자열만 선별
        num_df = df.select_dtypes(include=["number"])
        if num_df.empty:
            continue
        # 후보 컬럼 스코어링(이름에 키워드 포함)
        def _score_col(name: str) -> int:
            n = name.lower()
            s = 0
            if any(k in n for k in (k.lower() for k in cost_like)): s += 3
            if any(k in n for k in (k.lower() for k in channel_like)): s += 2
            if "합계" in name or "총" in name: s += 2
            if "금액" in name or "원" in name: s += 1
            return s
        scored = sorted([(c, _score_col(c)) for c in num_df.columns], key=lambda x: x[1], reverse=True)
        # 최상위 금액 열 하나 선택
        top_col = scored[0][0] if scored else num_df.columns[0]
        total_val = _pd.to_numeric(num_df[top_col], errors="coerce").fillna(0).sum()  # type: ignore

        # 연/월 후보(컬럼 또는 시트명)
        year = None
        month = None
        # 시트명이 연도처럼 보이면 우선 사용
        if year_pat.match(str(sheet).strip()):
            year = str(sheet).strip()
        # 컬럼에서 연/월 유사값 추출(상위 10행에서 다수결)
        head = df.head(10)
        for c in df.columns:
            vals = head[c].astype(str).str.strip()
            # 연도
            cand = [v for v in vals if year_pat.match(v)]
            if len(cand) >= 2 and not year:
                year = cand[0]
            # 월
            cand_m = [v for v in vals if month_pat.match(v)]
            if len(cand_m) >= 2 and not month:
                month = cand_m[0].lstrip("0")
        # 채널 브레이크다운(있다면 상위 몇 개)
        brk_parts: list[str] = []
        for c in df.columns:
            lc = str(c).lower()
            if any(k in lc for k in (k.lower() for k in channel_like)):
                try:
                    s = _pd.to_numeric(df[c], errors="coerce").fillna(0).sum()  # type: ignore
                    if s and s > 0:
                        brk_parts.append(f"{c}={_format_won(float(s))}")
                except Exception:
                    pass
        brk_parts = sorted(brk_parts, key=lambda t: len(t), reverse=True)[:5]

        # 문장화
        y_str = f"{year}년 " if year else ""
        m_str = f"{month}월 " if month else ""
        brk = f" ({', '.join(brk_parts)})" if brk_parts else ""
        msg = f"{y_str}{m_str}광고비 합계={_format_won(float(total_val))}{brk} [sheet={sheet}, col={top_col}]"
        out.append(msg)
        if len(out) >= max_docs:
            break
    return out

def _build_xlsx_meta_documents(doc: Document, *, max_rows: int, max_cols: int, max_docs: int) -> list[Document]:
    """XLSX 문서에서 경량 요약문을 만들어 메타-도큐먼트로 변환."""
    if _pd is None:
        return []
    meta = getattr(doc, "metadata", {}) or {}
    src = meta.get("source") or meta.get("file_path") or ""
    if not isinstance(src, str) or not src:
        return []
    # file:// 또는 로컬 경로만 지원
    p = _extract_local_path(meta)
    if not p:
        return []
    texts = _xlsx_sheet_summaries(Path(p), max_rows=max_rows, max_cols=max_cols, max_docs=max_docs)
    out: list[Document] = []
    for i, txt in enumerate(texts):
        if not txt:
            continue
        # source를 fragment로 구분해 별도 ID로 취급
        new_meta = dict(meta)
        new_meta["source"] = f"{src}#xlsx-meta-{i+1}"
        new_meta["content_type"] = "text/xlsx-summary"
        new_meta["title"] = (meta.get("title") or "XLSX Summary")
        out.append(Document(page_content=txt, metadata=new_meta))
    return out

def _merge_short_chunks(chunks: List[Document], *, min_merged_chars: int = 300) -> List[Document]:
    """
    인접한 짧은 청크들을 병합합니다. 동일 소스(source) 기반으로만 병합합니다.
    """
    out: List[Document] = []
    buf: Optional[Document] = None

    def _src(d: Document) -> str:
        m = getattr(d, "metadata", {}) or {}
        return str(m.get("source") or m.get("file_path") or "")

    for d in chunks:
        text = (getattr(d, "page_content", "") or "").strip()
        if not text:
            continue
        if buf is None:
            buf = d
            continue
        # 같은 소스 & 길이 합이 기준 미만이면 병합
        if _src(buf) == _src(d) and (len((buf.page_content or "").strip()) + len(text) < min_merged_chars):
            sep = "\n"
            try:
                buf.page_content = ((buf.page_content or "").rstrip() + sep + text)
            except Exception:
                # 재할당 실패시 새 Document 구성
                buf = Document(page_content=((buf.page_content or "").rstrip() + sep + text),
                               metadata=getattr(buf, "metadata", {}) or {})
        else:
            out.append(buf)
            buf = d
    if buf is not None:
        out.append(buf)
    return out


def _approx_tokens(s: str) -> int:
    return max(1, len(s or "") // 4)

def _batched_add(
    vs: Chroma,
    splits: List[Document],
    ids: Optional[List[str]] = None,
    *,
    quarantine_dir: Optional[Path] = None,
    max_seconds: Optional[int] = None,
) -> int:
    """
    Chroma add_documents 배치 업서트.
    - 토큰/배치 제한
    - 실패 시 이분탐색/단건 업서트
    - max_seconds 초과 시 남은 배치는 중단 (진단을 위한 워치독)
    """
    MAX_TOKENS = _cfg_int("RAG_TOKEN_BUDGET_PER_REQ", 250_000)
    MAX_BATCH  = (_cfg_int("RAG_EMBED_BATCH", _cfg_int("CHROMA_MAX_BATCH", 64)))
    total_added = 0
    t_start = time.time()

    if quarantine_dir is None:
        try:
            qdir = _cfg_str("CHROMA_QUARANTINE_DIR", "")
            base = Path(qdir) if qdir else (DATA_DIR / "quarantine")
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
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            qf = quarantine_dir / f"quarantine_{time.strftime('%Y%m%d_%H%M%S')}_{hashlib.sha1((doc_id or str(time.time())).encode()).hexdigest()[:8]}.json"
            qf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.warning("[CHROMA] quarantined bad doc → %s", qf)
        except Exception:
            logger.warning("[CHROMA] quarantine write failed")

    i = 0
    while i < len(splits):
        # 워치독: 전체 인덱싱 시간 상한
        if max_seconds and (time.time() - t_start) > max_seconds:
            logger.error("[INDEX][TIMEOUT] exceeded %ss — stopping remaining batches (%d/%d processed)",
                         max_seconds, i, len(splits))
            break

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
                    vs.add_documents(splits[lo:hi], ids=ids[lo:hi])
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
    """
    Documents → split → Chroma 인덱싱.
    return: (in_docs_count, added_chunks)
    """

    from typing import cast  # 전역 Any/Include 사용, 지역 중복 import 제거
    # 임베딩 모델 로깅(선행)
    try:
        emb_name = _resolve_embedding_model_name()
        logger.info("[ingest] embedding provider=%s model=%s",
                    (getattr(CFG, "LLM_PROVIDER", "") or "unknown"),
                    emb_name)
    except Exception:
        pass

    # Base NS/dir 및 split 모드 여부
    ns_base = _resolve_ns(namespace=namespace, collection_name=collection_name)
    pd_base = _resolve_persist_dir(ns_base, persist_directory)
    os.makedirs(pd_base, exist_ok=True)

    ns_web_env = (getattr(CFG, "CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc_env = (getattr(CFG, "CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    split_mode = bool(ns_web_env and ns_loc_env)

    # clear=True면 대상 NS 모두 초기화
    # (중략 — 기존 clear_once_guard 패치 적용부 유지)
    if clear:
        def _clear_dir(pd_eff: str, ns_eff: str, *, label: str) -> bool:
            _VS_CACHE.pop((pd_eff, ns_eff), None)
            # 런타임 가드: 동일 (pd, ns) 재초기화 방지
            if not _clear_once_guard(pd_eff, ns_eff, reason=f"documents_to_chroma(clear, part={label})"):
                return False
            try:
                import shutil
                if os.path.isdir(pd_eff):
                    shutil.rmtree(pd_eff)
                os.makedirs(pd_eff, exist_ok=True)
                logger.info("documents_to_chroma: cleared vector store (ns=%s, dir=%s, part=%s)", ns_eff, pd_eff, label)
            except Exception as e:
                logger.warning("documents_to_chroma: clear failed for ns=%s dir=%s: %s", ns_eff, pd_eff, e)
            return True

        cleared_labels: list[str] = []
        if _clear_dir(pd_base, ns_base, label="base"):
            cleared_labels.append("base")
        if split_mode:
            if _clear_dir(_resolve_persist_dir(ns_web_env, persist_directory), ns_web_env, label="web"):
                cleared_labels.append("web")
            if _clear_dir(_resolve_persist_dir(ns_loc_env, persist_directory), ns_loc_env, label="local"):
                cleared_labels.append("local")
        # 요약 로그(다중 노출 대신 1회 요약)
        if cleared_labels:
            logger.info("[INIT] vector store cleared once (%s) — ns_base=%s dir_base=%s split=%s",
                        ",".join(cleared_labels), ns_base, pd_base, bool(split_mode))
        else:
            logger.debug("[INIT] clear skipped by runtime guard (already cleared earlier)")

    # 1) 블럭/이상치 제거 및 텍스트 정리
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

        # (옵션) 로컬 파일이면 메타에 mtime 버전을 주입
        try:
            if _cfg_bool("RAG_ID_INCLUDE_MTIME", True):
                md = getattr(d, "metadata", {}) or {}
                ver = _local_mtime_key(md)
                if ver:
                    md["source_version"] = ver
                    # LangChain Document는 metadata dict 재할당을 허용합니다.
                    try:
                        d.metadata = md
                    except Exception:
                        pass
        except Exception:
            pass
    pre_docs_count = len(pre_docs)

    # 2) 웹/로컬/기타 파티션
    web_docs, loc_docs, oth_docs = [], [], []
    for d in pre_docs:
        flag = _is_web_source(getattr(d, "metadata", {}) or {})
        if flag is True:   web_docs.append(d)
        elif flag is False: loc_docs.append(d)
        else:               oth_docs.append(d)

    # 3) 파티션 인덱싱 함수
    def _ingest_partition(part_docs: List[Document], is_web_flag: Optional[bool], label: str) -> Tuple[int, int, int, int]:
        """
        return: (in_count, new_count, split_count, added_chunks)
        """
        if not part_docs:
            return (0, 0, 0, 0)

        ns_eff, _ = _resolve_ns_for_docs(ns_base, is_web_flag if split_mode else None)
        pd_eff = _resolve_persist_dir(ns_eff, persist_directory)
        os.makedirs(pd_eff, exist_ok=True)

        vs_eff = _get_vs(ns_eff, pd_eff, embedding)  # fresh 재생성

        # fresh 판정
        def _is_fresh_store() -> bool:
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

        is_fresh = _is_fresh_store()
        if is_fresh:
            try: _VS_CACHE.pop((pd_eff, ns_eff), None)
            except Exception: pass
            vs_eff = _get_vs(ns_eff, pd_eff, embedding)
            try: _FRESH_KEYS.discard((pd_eff, ns_eff))
            except Exception: pass
            logger.debug("documents_to_chroma[%s]: fresh store — recreated handle (ns=%s dir=%s)", label, ns_eff, pd_eff)

        # 게이트키핑
        filtered_docs, skipped_gate = [], 0
        for d in part_docs:
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""
            if src and not url_allowed(src):
                skipped_gate += 1
                continue
            filtered_docs.append(d)

        # [ADD] XLSX 경량 요약 메타-도큐먼트 생성(게이트키핑 통과한 문서 대상)
        try:
            if _pd is not None and _cfg_bool("ENABLE_XLSX_META_SUMMARY", True):
                _max_rows = _cfg_int("XLSX_SCAN_MAX_ROWS", 200)
                _max_cols = _cfg_int("XLSX_SCAN_MAX_COLS", 20)
                _max_docs = _cfg_int("XLSX_META_MAX_DOCS", 5)
                extra_docs: list[Document] = []
                for d in filtered_docs:
                    if _is_xlsx_meta(getattr(d, "metadata", {}) or {}):
                        extra_docs.extend(_build_xlsx_meta_documents(d, max_rows=_max_rows, max_cols=_max_cols, max_docs=_max_docs))
                if extra_docs:
                    filtered_docs.extend(extra_docs)
                    logger.info("[INGEST][%s] xlsx meta summaries added: +%d docs", label, len(extra_docs))
        except Exception as e:
            logger.debug("[INGEST][%s] xlsx meta summaries skipped: %s", label, e)

        # 신규/변경 판단을 위한 (source, version) 수집
        def _sv_pair(d) -> tuple[str, str]:
            m = getattr(d, "metadata", {}) or {}
            src = m.get("source") or m.get("url") or m.get("file_path") or ""
            ver = m.get("source_version") or ""
            # 필요 시 로컬 mtime 강제 산출
            if not ver and _cfg_bool("RAG_ID_INCLUDE_MTIME", True):
                lv = _local_mtime_key(m)
                if lv:
                    m["source_version"] = lv
                    ver = lv
            return (str(src), str(ver))

        all_srcs = []
        cur_versions: dict[str, str] = {}
        for d in filtered_docs:
            src, ver = _sv_pair(d)
            if src:
                all_srcs.append(src)
                if ver and src not in cur_versions:
                    cur_versions[src] = ver

        stored_map: dict[str, str] = {}
        if all_srcs and not is_fresh:
            try:
                urls: list[str] = [u for u in all_srcs if isinstance(u, str) and u]  # 빈 문자열/비정상 거르기
                # Chroma Where 타입은 dict[str, Any]로 제한
                where_filter: dict[str, Any] = {"source": {"$in": urls}}
                # Include는 Literal 기반 타입 → 리스트 리터럴을 cast로 지정
                include: Include = cast(Include, ["metadatas"])
                col: Any = getattr(vs_eff, "_collection", None)
                res: dict[str, Any] = {}
                if col is not None:
                    res = col.get(where=where_filter, include=include)
                for m in (res or {}).get("metadatas") or []:
                    if isinstance(m, dict) and m.get("source"):
                        s = str(m.get("source"))  # 타입 강제 일관화
                        v = str(m.get("source_version") or "")
                        # 가장 최근/마지막 값을 저장 (버전 필드 없던 기존 인덱스는 "")
                        stored_map[s] = v
            except Exception as e:
                logger.debug("chroma get(where=$in) failed(ns=%s): %s", ns_eff, e)
                try:
                    col2: Any = getattr(vs_eff, "_collection", None)
                    res2: Any = {}
                    if col2 is not None:
                        res2 = col2.get(include=cast(Include, ["metadatas"]))
                    for m in (res2 or {}).get("metadatas") or []:
                        if isinstance(m, dict) and m.get("source"):
                            s = str(m.get("source"))
                            v = str(m.get("source_version") or "")
                            stored_map[s] = v
                except Exception as e2:
                    logger.debug("chroma full metadatas get failed(ns=%s): %s", ns_eff, e2)
                    stored_map = {}
        elif is_fresh:
            logger.debug("documents_to_chroma[%s]: fresh store detected; skip stored_urls check", label)

        # 신규/변경 분류
        new_documents: List[Document] = []
        changed_sources: set[str] = set()
        for d in filtered_docs:
            meta = getattr(d, "metadata", {}) or {}
            src = meta.get("source") or meta.get("url") or meta.get("file_path") or ""
            cur_ver = str((meta.get("source_version") or ""))
            if src and (is_fresh or (src not in stored_map)):
                new_documents.append(d)
            elif src and (stored_map.get(src, "") != cur_ver):
                # 버전이 다르면 교체 대상
                new_documents.append(d)
                changed_sources.add(src)
            elif not src and is_fresh:
                new_documents.append(d)

        if not new_documents:
            if verbose:
                logger.info(
                    "documents_to_chroma(part:%s): no new urls | ns=%s dir=%s | in=%d gate_skipped=%d fresh=%s",
                    label, ns_eff, pd_eff, len(part_docs), skipped_gate, is_fresh
                )
            return (len(part_docs), 0, 0, 0)

        # (옵션) 버전 변경된 소스는 기존 벡터를 삭제 후 재색인
        if changed_sources and _cfg_bool("RAG_DELETE_OLD_ON_VERSION_MISMATCH", True):
            try:
                col_del: Any = getattr(vs_eff, "_collection", None)
                if col_del is not None:
                    for s in changed_sources:
                        try:
                            # 동일 이유로 delete의 where도 Any로 완화
                            col_del.delete(where=cast(Any, {"source": {"$eq": s}}))
                        except Exception as de:
                            logger.debug("delete old docs failed(ns=%s, source=%s): %s", ns_eff, s, de)
            except Exception as e:
                logger.debug("bulk delete on version mismatch failed(ns=%s): %s", ns_eff, e)

        # 스플릿
        splits: List[Document] = split_documents(new_documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not splits:
            if verbose:
                logger.info(
                    ("documents_to_chroma(part:%s): no splits | ns=%s dir=%s | in=%d new=%d | "
                     "note=all texts were filtered/too short/empty-after-cleaning (0 chunks expected)"),
                    label, ns_eff, pd_eff, len(part_docs), len(new_documents)
                )
            return (len(part_docs), len(new_documents), 0, 0)

        # ──────────────────────────────────────────────────────
        # [ADD] PPTX 초단편 병합 + 콘텐츠 타입별 최소 길이 필터
        # ──────────────────────────────────────────────────────
        try:
            # PPTX 청크만 선별
            pptx_idxs = [i for i, d in enumerate(splits) if _is_pptx_meta(getattr(d, "metadata", {}) or {})]
            if pptx_idxs:
                # 원본 순서를 유지하며 PPTX 영역만 병합 적용
                merged: List[Document] = []
                run: List[Document] = []
                def _flush_run():
                    nonlocal merged, run
                    if not run:
                        return
                    # 기본값 160자로 상향(기존 제안: 120→160)
                    merged.extend(_merge_short_chunks(run, min_merged_chars=_cfg_int("PPTX_MIN_MERGED_CHARS", 160)))
                    run = []
                last_pptx = False
                for d in splits:
                    is_pptx = _is_pptx_meta(getattr(d, "metadata", {}) or {})
                    if is_pptx:
                        run.append(d)
                        last_pptx = True
                    else:
                        if last_pptx:
                            _flush_run()
                            last_pptx = False
                        merged.append(d)
                _flush_run()
                splits = merged

            # 콘텐츠 타입별 최소 길이 필터
            GLOBAL_MIN_CHUNK_CHARS = _cfg_int("MIN_CHUNK_CHARS", 120)
            def _min_chars_for(ct: str) -> int:
                cts = (ct or "").lower()
                # PPTX: application/vnd.openxmlformats-officedocument.presentationml.presentation
                if "presentationml" in cts:
                    return _cfg_int("MIN_CHUNK_PPTX", 40)
                # PDF
                if cts == "application/pdf" or "pdf" in cts:
                    return _cfg_int("MIN_CHUNK_PDF", 80)
                # 그 외
                return GLOBAL_MIN_CHUNK_CHARS

            before = len(splits)
            def _len_ok(doc: Document) -> bool:
                text_len = len((getattr(doc, "page_content", "") or "").strip())
                meta = getattr(doc, "metadata", {}) or {}
                ct = str(meta.get("content_type") or "")
                return text_len >= _min_chars_for(ct)

            splits = [d for d in splits if _len_ok(d)]
            after = len(splits)  # 필터 후 길이
            if verbose and before != after:
                logger.info(
                    "[INGEST][%s] filtered short chunks: %d → %d "
                    "(GLOBAL_MIN=%d, PPTX_MIN=%d, PDF_MIN=%d)",
                    label, before, after,
                    GLOBAL_MIN_CHUNK_CHARS,
                    _cfg_int('MIN_CHUNK_PPTX', 40),
                    _cfg_int('MIN_CHUNK_PDF', 80),
                )
        except Exception as e:
            logger.debug("[INGEST][%s] pptx short-chunk merge/filter skipped due to error: %s", label, e)

        # ──────────────────────────────────────────────────────
        # [ADD] 청크 통계 로깅 (길이 분포/평균 등)
        # ──────────────────────────────────────────────────────
        try:
            lens = [len((d.page_content or "").strip()) for d in splits if (d.page_content or "").strip()]
            lens.sort()
            n = len(lens)
            if n:
                avg = sum(lens) / n
                p50 = lens[int((n - 1) * 0.50)]
                p90 = lens[int((n - 1) * 0.90)]
                minv, maxv = lens[0], lens[-1]
                logger.info(
                    "[INGEST][stats][%s] splits=%d avg=%.1f p50=%d p90=%d min=%d max=%d",
                    label, n, avg, p50, p90, minv, maxv
                )
                try:
                    from tools.metrics import event as _metrics_event
                    _metrics_event("chunk_stats", part=label, splits=n,
                                   avg_chars=round(avg, 1),
                                   p50=p50, p90=p90,
                                   min_chars=minv, max_chars=maxv)
                except Exception:
                    pass
            else:
                logger.info("[INGEST][stats][%s] no valid chunks", label)
        except Exception as e:
            logger.debug("[INGEST][stats][%s] chunk stat failed: %s", label, e)

        # ID 생성
        MAX_ID_CHARS = _cfg_int("CHROMA_MAX_ID_CHARS", 128)
        ids: List[str] = []
        counter: _dd[str, int] = _dd(int)

        def _cap_id(s: str) -> str:  # ID 길이 상한 보정
            if len(s) <= MAX_ID_CHARS:
                return s
            keep_tail = 12
            return s[: MAX_ID_CHARS - keep_tail] + s[-keep_tail:]

        def _make_doc_id(src: str, ver: str, text: str) -> str:
            """
            같은 원칙:
            1) 안정 키 구성: source(정규화) + version(mtime 등) [+ 내용 해시 옵션]
            2) 결정적 base 해시 + 시퀀스 번호(충돌 방지)
            3) 길이 상한(capping)
            """
            # source 정규화(모바일/AMP/트래킹 파라미터 제거)
            try:
                src_norm = _normalize_canonical_url(src)
            except Exception:
                src_norm = src
            seed = src_norm
            if _cfg_bool("RAG_ID_INCLUDE_MTIME", True) and ver:
                seed = f"{seed}|{ver}"
            if _cfg_bool("RAG_ID_INCLUDE_CONTENT_SHA", False):
                try:
                    import hashlib as _hl
                    seed += "|" + _hl.sha1((text or "").encode("utf-8", "ignore")).hexdigest()[:16]
                except Exception:
                    pass
            # 결정적 base 해시 + 시퀀스
            import hashlib as _hl2
            base = _hl2.sha1(seed.encode("utf-8", "ignore")).hexdigest()
            counter[base] += 1
            raw_id = f"{base}-{counter[base]:06d}"
            return _cap_id(raw_id)

        for doc in splits:
            meta = getattr(doc, "metadata", {}) or {}
            src  = str(meta.get("source") or meta.get("url") or meta.get("file_path") or "")
            ver  = str(meta.get("source_version") or "")
            if src:
                ids.append(_make_doc_id(src, ver, getattr(doc, "page_content", "") or ""))
            else:
                counter["__none__"] += 1
                ids.append(_cap_id(f"none-{counter['__none__']:06d}"))

        # 업서트 (워치독 적용)
        INDEX_TIMEOUT_SEC = _cfg_int("INDEX_TIMEOUT_SEC", 60)
        t0 = time.time()
        _qdir_cfg = _cfg_str("CHROMA_QUARANTINE_DIR", "")
        qdir = Path(_qdir_cfg) if _qdir_cfg else (Path(pd_eff) / "quarantine")
        try: qdir.mkdir(parents=True, exist_ok=True)
        except Exception: pass

        try:
            added_chunks = _batched_add(vs_eff, splits, ids, quarantine_dir=qdir, max_seconds=INDEX_TIMEOUT_SEC)
            if added_chunks == 0 and verbose:
                logger.info(
                    ("[HINT][%s] added_chunks=0 → common causes: "
                    "① all URLs already indexed (no new), ② gatekept domains, "
                    "③ cleaners removed boilerplate/blocks, ④ chunk_size too large"),
                    label
                )
        except Exception as e:
            logger.warning("documents_to_chroma(part:%s): batched_add raised — forcing single upserts: %s", label, e)
            added_chunks = 0
            for k, doc in enumerate(splits):
                # 워치독: 단건 업서트도 전체 상한을 존중
                if (time.time() - t0) > INDEX_TIMEOUT_SEC:
                    logger.error("[INDEX][TIMEOUT] exceeded %ss during single upserts — stopping at %d/%d",
                                 INDEX_TIMEOUT_SEC, k, len(splits))
                    break
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
            try: persist_fn()
            except Exception as e: logger.debug("vs.persist failed(ns=%s): %s", ns_eff, e)
        else:
            client: Any = getattr(vs_eff, "_client", None)
            client_persist = getattr(client, "persist", None)
            if callable(client_persist):
                try: client_persist()
                except Exception as e: logger.debug("client.persist failed(ns=%s): %s", ns_eff, e)

        try:
            total_chars: int = sum(len(d.page_content or "") for d in splits)
            avg_len: int = int(total_chars / len(splits)) if splits else 0
        except Exception:
            avg_len = 0

        elapsed = time.time() - t0
        logger.info(
            "documents_to_chroma(part:%s): %d docs → %d chunks (ns=%s, dir=%s) | new=%d, changed=%d, splits=%d, avg_chunk_chars=%d, time=%.2fs",
            label, len(part_docs), added_chunks, ns_eff, pd_eff, len(new_documents), len(changed_sources), len(splits), avg_len, elapsed
        )
        try:
            total_chars_for_splits: int = sum(len(d.page_content or "") for d in splits)
            record_chunks(chars_sum=total_chars_for_splits, chunks_cnt=added_chunks, ns=ns_eff, part=label)
        except Exception:
            pass
        return (len(part_docs), len(new_documents), len(splits), added_chunks)

    # 4) 인덱싱 실행
    if split_mode:
        in_w, new_w, spl_w, add_w = _ingest_partition(web_docs, True,  "web")
        in_l, new_l, spl_l, add_l = _ingest_partition(loc_docs, False, "local")
        in_o, new_o, spl_o, add_o = _ingest_partition(oth_docs, None,  "base")
        total_added = add_w + add_l + add_o
        split_count = spl_w + spl_l + spl_o
        new_docs_count = new_w + new_l + new_o
        pd_for_log = f"{pd_base} (split: web={_resolve_persist_dir(ns_web_env, persist_directory)}, local={_resolve_persist_dir(ns_loc_env, persist_directory)})"
        # ─────────────────────────────────────────────────────────────
        # [HEALTHCHECK] 파티션별 added_chunks ≥ 1 보장 (입력이 있을 때)
        # ─────────────────────────────────────────────────────────────
        if in_w > 0 and add_w <= 0:
            raise RuntimeError("No chunks added for web")
        if in_l > 0 and add_l <= 0:
            raise RuntimeError("No chunks added for local")
        # base(other) 파티션에 입력이 있고 추가가 0인 경우도 방어
        if in_o > 0 and add_o <= 0:
            raise RuntimeError("No chunks added for base")
    else:
        in_b, new_b, spl_b, add_b = _ingest_partition(pre_docs, None, "base")
        total_added = add_b
        split_count = spl_b
        new_docs_count = new_b
        pd_for_log = _resolve_persist_dir(ns_base, None)
        # ─────────────────────────────────────────────────────────────
        # [HEALTHCHECK] 단일 파티션 모드에서도 0 추가 시 즉시 중단
        # ─────────────────────────────────────────────────────────────
        if pre_docs_count > 0 and total_added <= 0:
            raise RuntimeError("No chunks added for base")

    # 5) 최종 요약
    logger.info(
        ("documents_to_chroma: %d docs → %d chunks (ns=%s, dir=%s, split=%s) | "
         "in=%d, pre=%d, blocked=%d, new=%d, splits=%d"),
        len(documents or []), total_added, ns_base, pd_for_log, bool(split_mode),
        len(documents or []), pre_docs_count, skipped_block, new_docs_count, split_count
    )
    try:
        record_chunks(chars_sum=0, chunks_cnt=total_added, ns=ns_base, part="summary")
    except Exception:
        pass
    # 함수 보장: 항상 (in_docs, added_chunks) 튜플 반환
    return (len(documents or []), total_added)


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
    """web.json → Document → Chroma 업서트 편의 함수."""
    # [ADD] 사전 해시/버전키 기반 no-op 빠른 종료
    # ns/pd를 먼저 해석해야 seen-hash 파일을 찾을 수 있습니다.
    ns_probe = _resolve_ns(namespace=namespace, collection_name=collection_name)
    pd_probe = _resolve_persist_dir(ns_probe, persist_directory)
    existing = _load_seen_source_hashes(ns_probe, pd_probe)  # {source:hash}
    incoming = _compute_incoming_hashes(json_file)            # {source:hash}
    new_sources = [s for s, h in incoming.items() if existing.get(s) != h]
    if not new_sources and incoming:
        logger.info("[ingest] all sources unchanged → skip build (ns=%s dir=%s, sources=%d)",
                    ns_probe, pd_probe, len(incoming))
        return (0, 0)

    documents = web_page_json_to_documents(json_file)
    in_docs, added = documents_to_chroma(
        documents,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        namespace=namespace,
        collection_name=collection_name,
        persist_directory=persist_directory,
        embedding=(embedding or _get_embeddings()),
        clear=clear,
    )
    # 인덱싱이 실제로 수행되었다면 seen-hash 갱신
    if added > 0 and incoming:
        try:
            ns_effective = _resolve_ns(namespace=namespace, collection_name=collection_name)
            pd_effective = _resolve_persist_dir(ns_effective, persist_directory)
            _save_seen_source_hashes(ns_effective, pd_effective, incoming)
        except Exception:
            logger.debug("[ingest] save seen hashes skipped (ns/pd unresolved or write fail)")
    return (in_docs, added)

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
    logger.debug("[retrieve] using collection(ns=%s, dir=%s)", ns, pd)

    emb_fn = getattr(vs, "_embedding_function", None) or embedding or _get_embeddings(embedding)

    try:
        q_emb = emb_fn.embed_query(q) if hasattr(emb_fn, "embed_query") else emb_fn(q)
        n = max(1, int(top_k or 5))
        res = vs._collection.query(
            query_embeddings=[q_emb],
            n_results=n,
            include=cast(Include, ["documents", "metadatas"]),
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

def has_any_docs(ns: str, base_dir: str) -> bool:
    """
    지정 컬렉션(ns) / 디렉터리(base_dir)에 문서가 1개 이상 존재하는지 여부.
    1) Chroma 컬렉션 count()가 가능하면 우선 사용
    2) 실패 시 디렉터리에 파일 존재 여부로 폴백
    """
    try:
        vs = _get_vs(ns, base_dir, embedding=_get_embeddings())
        col = getattr(vs, "_collection", None)
        cnt_fn = getattr(col, "count", None)
        if callable(cnt_fn):
            # 정적체커 우회: 반환값을 Any로 캐스팅 후 안전 변환
            raw: Any = cnt_fn()
            if isinstance(raw, int):
                cnt = raw
            elif isinstance(raw, str):
                try:
                    cnt = int(raw.strip() or "0")
                except Exception:
                    cnt = 0
            else:
                # pyright/mypy에 안전: Any로 캐스팅 후 int/len/bool 순으로 폴백
                try:
                    cnt = int(cast(Any, raw))
                except Exception:
                    try:
                        cnt = len(cast(Any, raw))
                    except Exception:
                        cnt = 1 if bool(raw) else 0
            return cnt > 0
    except Exception:
        pass
    try:
        p = Path(base_dir)
        if p.exists():
            for _ in p.iterdir():
                return True
    except Exception:
        pass
    return False


__all__ = [
    "web_results_to_documents",
    "web_page_json_to_documents",
    "documents_to_chroma",
    "add_web_pages_json_to_chroma",
    "retrieve",
    "clear_vector_store",
    "ensure_vector_store_cleared_once",
    "_default_chroma_dir",
    "get_requests_session",
    "has_any_docs",
    # 빠른 인덱스(Findings) 관련 공개 심볼
    "quick_ingest_add",
    "quick_ingest",               # 호환용
    "set_quick_ingest_proxy",
]
