from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
logging.getLogger("chardet").setLevel(logging.WARNING)  # chardet DEBUG 스팸 억제

import os, io, json, time
from pathlib import Path
from typing import Any, Dict, Tuple, Sequence, Callable, Mapping, MutableMapping, Iterable, Protocol, runtime_checkable, Optional, cast  # ← quick_ingest 프록시 시그니처용
from types import ModuleType

import requests
from requests.exceptions import SSLError as _SSLError
import codecs  # for BOM checks in _decode_bytes
from requests.auth import AuthBase
from requests.models import Response

from urllib3.exceptions import NameResolutionError
from urllib.parse import urlparse  # host 추출용

# 네트워크 헬퍼/설정은 ingest_net에서 공통 사용
#  ✅ 실제 HTTP 요청/응답은 ingest_net 모듈을 단일 진입점으로 사용한다.
from .ingest_net import (
    get_requests_session as _net_get_requests_session,
    try_fetch_pdf as _net_try_fetch_pdf,
    # 네트워크 관련 상수도 ingest_net 경유로 사용하여 단일 진입점 유지
    REQ_CONN_TIMEOUT as _REQ_CONN_TIMEOUT,
    REQ_READ_TIMEOUT as _REQ_READ_TIMEOUT,
    USER_AGENT as _UA,
    # 실제 바이너리/텍스트 fetch 단일 진입점
    fetch_binary as _net_fetch_binary,
    fetch_text as _net_fetch_text,
)

# 공통 설정/헬퍼는 ingest_config에서 가져온다
from .ingest_config import (
    CFG,
    reload_config,
    _cfg_str,
    _cfg_bool,
    _cfg_int,
)

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

# 통일된 UA 값은 ingest_config._UA 를 사용합니다.

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

    # DNS 블랙리스트 빠른 차단
    try:
        from urllib.parse import urlparse as _urlparse
        _host = _urlparse(url).netloc
    except Exception:
        _host = ""
    if _host and _host in _DNS_BAD_HOSTS:
        raise RuntimeError(f"skip_bad_host:{_host}")

    # ── [B] 회로 차단기(호스트 단위) ─────────────────────────────────────
    # 라운드 내 동일 호스트 실패 누적이 상한을 넘으면 즉시 스킵
    if _host:
        try:
            if _circuit_break_host(_host):
                logger.warning("[host-circuit] skip(host fail-limit reached): %s", _host)
                raise RuntimeError(f"host_circuit_skip:{_host}")
        except NameError:
            # 함수/테이블이 아직 정의되지 않은 초기 구간에서는 무시
            pass

    try:
        resp = session.get(
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
        # 상태코드 4xx/5xx는 실패로 간주해 누적 (raise_for_status는 호출부에서 할 수도 있음)
        if resp is not None and resp.status_code >= 400 and _host:
            try:
                _mark_host_fail(_host)
            except NameError:
                pass
        return resp
    except Exception as e:
        # DNS 실패는 재시도 가치 낮음 → 블랙리스트 등록
        try:
            if isinstance(getattr(e, "__cause__", None), NameResolutionError) or "NameResolutionError" in str(e):
                if _host:
                    _DNS_BAD_HOSTS.add(_host)
            # SSL/DNS 등 연결성 오류는 호스트 실패 누적
            if _host and (
                "SSLError" in e.__class__.__name__
                or "ssl" in str(e).lower()
                or "NameResolutionError" in str(e)
                or "Failed to resolve" in str(e)
            ):
                try:
                    _mark_host_fail(_host)
                except NameError:
                    pass
        finally:
            raise

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

# web_rag 유틸 모듈
#  - 네트워크/파일 경로 등 ingest 레벨에서 필요한 것만 사용
from .utils import (
    DATA_DIR,
    normalize_url as _normalize_url,  # ← 요청 전 정규화에 사용
)
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, unquote, quote

# ---- 선택적 백엔드(존재시 사용, 미설치 OK) ----  (PDF 텍스트 추출용이므로 유지)
try:
    import PyPDF2 as _pypdf2_mod
    _pypdf2: Optional[ModuleType] = _pypdf2_mod  # mypy-friendly: 모듈 또는 None
except Exception:
    _pypdf2 = None

try:
    from pdfminer.high_level import extract_text as _pdfminer_extract_text_mod
    # pdfminer의 extract_text는 다양한 시그니처를 가지므로 가변 콜러블로 표기
    _pdfminer_extract_text: Optional[Callable[..., str]] = _pdfminer_extract_text_mod
except Exception:
    _pdfminer_extract_text = None

from typing import cast  # _session_get 등에서만 사용

# =========================================================================
# Quick Ingest (Findings 빠른 인덱스용) — 프록시를 함수처럼 호출하지 않도록 래퍼 제공
# =========================================================================

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
# DNS 실패 호스트 블랙리스트 (세션 전역)
#  - NameResolutionError가 발생한 호스트는 이후 요청을 즉시 스킵
# ─────────────────────────────────────────────────────────────────────────────

_DNS_BAD_HOSTS: set[str] = set()

# ─────────────────────────────────────────────────────────────────────────────
# 공용 HTTPS 세션 (재시도/CA 번들 강제)
#  - 기존 .utils.session 을 기반으로 설정을 보강하고 재사용합니다.
# ─────────────────────────────────────────────────────────────────────────────
_SESSION_ENFORCED: Optional[requests.Session] = None

def get_requests_session() -> requests.Session:
    """
    공용 requests.Session 제공.
    - 실제 세션 생성/설정은 ingest_net.get_requests_session()에서 담당한다.
    - 이 래퍼를 두는 이유는 기존 코드/호출부와의 호환성을 유지하기 위함.
    """
    # 과거 구현에서 사용하던 캐시 변수를 유지하지만,
    # 실제 객체는 ingest_net 쪽에서 관리한다.
    global _SESSION_ENFORCED
    s = _net_get_requests_session()
    _SESSION_ENFORCED = s
    return s

# (과거 벡터 관련 네임스페이스 해석은 ingest_vector._resolve_ns로 이동)

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
        # 예외: 공공 포털/기관 도메인은 www 강제 금지(서비스 라우팅이 다름)
        _NO_WWW_DOMAINS = ("khidi.or.kr", "mfds.go.kr", "kosis.kr")
        def _no_www(h: str) -> bool:
            return (
                h.endswith(".go.kr") or
                h.endswith(".or.kr") or
                any(h.endswith(d) for d in _NO_WWW_DOMAINS)
            )
        # 예외: Dailypharm도 m→www 강제 금지
        _is_dailypharm = host.endswith("dailypharm.com")
        if host.startswith("m.") and len(host) > 2 and not _is_dailypharm and not _no_www(host):
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

# ─────────────────────────────────────────────────────────────────────────────
# [C] 잡음 URL 드랍 규칙(경량)
#   - kpanet.or.kr EULA API, 루트 페이지 등 무의미 엔드포인트 제거
# ─────────────────────────────────────────────────────────────────────────────
def _is_noise_url(u: str) -> bool:
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower()
        path = p.path or ""
    except Exception:
        return False
    # 1) KPA EULA API (콘텐츠 무의미 + 인증서 이슈 잦음)
    if host.endswith("kpanet.or.kr") and "/api/web/eula" in path:
        return True
    # 2) 대한약사회 루트 페이지(텍스트 거의 없음)
    if host == "kpanet.or.kr" and (path == "" or path == "/"):
        return True
    return False


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
        elif "presentationml" in ct or ext in (".pptx", ".ppt"):
            rank = 1
        elif "spreadsheetml" in ct or ext in (".xlsx", ".xls"):
            rank = 2
        # 크기 큰 문서를 우선. 다양한 키 지원(bytes/size/content_length)
        try:
            size_val = (
                item.get("bytes", None)
                or item.get("size", None)
                or item.get("content_length", None)
                or 0
            )
            neg_bytes = -int(size_val or 0)
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

def _fetch_binary(url: str, timeout: int = 10) -> bytes | None:
    """
    PDF/바이너리 가져오기 - ✅ 네트워크 단일 진입점 래퍼

    계약(contract):
      - ingest_docs.web_results_to_documents 등에서 기대하는 시그니처는
        (url: str, timeout: int) -> bytes | None 입니다.
      - 실제 HTTP 요청은 ingest_net.fetch_binary / ingest_net.try_fetch_pdf 에서만 수행합니다.
      - 이 함수는 예외를 밖으로 퍼뜨리지 않고, 실패 시 None을 반환하도록 설계합니다.
    """
    if not url:
        return None

    # 요청 전에 항상 정규화
    u = _normalize_before_request(url)

    # 1) PDF로 보이면 우선 PDF 전용 경로 한 번 시도
    try:
        if _looks_like_pdf_url(u):
            data = _net_try_fetch_pdf(u, timeout)
            if data is not None:
                return data
    except Exception as e:  # pragma: no cover
        logger.warning("[_fetch_binary] try_fetch_pdf failed url=%s err=%s", u, e)

    # 2) 일반 바이너리 fetch (ingest_net.fetch_binary)
    try:
        return _net_fetch_binary(u, timeout)
    except Exception as e:  # pragma: no cover
        logger.warning("[_fetch_binary] fetch_binary failed url=%s err=%s", u, e)
        return None

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
                    # 모든 시도 실패 → 호스트 실패 누적
                    try:
                        _h = urlparse(u0).netloc
                        if _h:
                            _mark_host_fail(_h)
                    except Exception:
                        pass
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
    HTML 페이지 로딩 → 텍스트로 변환

    계약(contract):
      - ingest_docs.web_results_to_documents에서 기대하는 시그니처는
        (url: str, timeout: int) -> str 입니다.
      - 실제 HTTP 요청은 ingest_net.fetch_text 를 통해서만 수행합니다.
      - 네트워크 에러/디코딩 실패 시에는 빈 문자열("")을 반환합니다.
    """
    if not url:
        return ""

    u = _normalize_before_request(url)

    # 1) ingest_net.fetch_text 를 통한 단일 네트워크 진입점
    try:
        html = _net_fetch_text(u, timeout)
    except Exception as e:  # pragma: no cover
        logger.warning("[_load_html_as_text] fetch_text failed url=%s err=%s", u, e)
        html = None

    if not html:
        return ""

    # 2) HTML → 텍스트 추출 (기존 정제 로직 유지)
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


# =============================================================================
# web.json / 검색결과 → LangChain Document 변환 유틸
#  - 실제 구현은 ingest_docs.py에 있으며,
#    ingest.py에서는 기존 호출부 호환을 위해 얇게 재노출만 수행한다.
# =============================================================================
from .ingest_docs import web_results_to_documents, web_page_json_to_documents

# =============================================================================
# Vector-store 관련 공개 API는 ingest_vector.py 구현을 재노출
#  - 순환 없이 역할 분리: 네트워크/HTML/PDF 로딩은 ingest.py,
#    벡터 인덱싱/검색은 ingest_vector.py
# =============================================================================
from .ingest_vector import (
    documents_to_chroma,
    add_documents_to_chroma,
    add_web_pages_json_to_chroma,
    retrieve,
    clear_vector_store,
    ensure_vector_store_cleared_once,
    get_collection_count,
    get_total_collection_count,
    seed_web_namespace,
    _default_chroma_dir,
    _resolve_persist_dir_strict,
    has_any_docs,
)

__all__ = [
    # web.json → Document 변환
    "web_results_to_documents",
    "web_page_json_to_documents",
    # 벡터 인덱싱/검색 (ingest_vector 재노출)
    "documents_to_chroma",
    "add_documents_to_chroma",
    "add_web_pages_json_to_chroma",
    "retrieve",
    "clear_vector_store",
    "ensure_vector_store_cleared_once",
    "get_collection_count",
    "get_total_collection_count",
    "seed_web_namespace",
    "_default_chroma_dir",
    "_resolve_persist_dir_strict",
    "has_any_docs",
    # 네트워크/세션
    "get_requests_session",
    # 빠른 인덱스(Findings) 관련 공개 심볼
    "quick_ingest_add",
    "quick_ingest",               # 호환용
    "set_quick_ingest_proxy",
]


# ─────────────────────────────────────────────────────────────────────────────
# [B] 회로 차단기(호스트 단위) 전역 상태/함수
# ─────────────────────────────────────────────────────────────────────────────
_ROUND_FAIL_HOSTS: dict[str, int] = {}
_ROUND_FAIL_LIMIT = 2  # 라운드 내 최대 실패 기록 회수

def _round_fail_reset() -> None:
    """라운드 시작 시 호출하여 실패 카운터를 초기화."""
    try:
        _ROUND_FAIL_HOSTS.clear()
    except Exception:
        pass

def _circuit_break_host(host: str) -> bool:
    """호스트 실패 누적이 한도 초과면 True(스킵)."""
    try:
        cnt = _ROUND_FAIL_HOSTS.get(host.lower(), 0)
        return cnt >= _ROUND_FAIL_LIMIT
    except Exception:
        return False

def _mark_host_fail(host: str) -> None:
    """호스트 실패 회수를 +1."""
    try:
        h = (host or "").lower()
        if not h:
            return
        _ROUND_FAIL_HOSTS[h] = _ROUND_FAIL_HOSTS.get(h, 0) + 1
    except Exception:
        pass