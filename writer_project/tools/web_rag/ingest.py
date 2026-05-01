from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
logging.getLogger("chardet").setLevel(logging.WARNING)  # chardet DEBUG 스팸 억제

# NOTE:
# Canonical URL normalization MUST be a single source of truth.
# Do not re-define normalization logic here.
from tools.web_rag.utils import _normalize_canonical_url


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
from urllib.parse import urlparse, urlunparse  # host 추출용

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

def _coerce_timeout(v: Any) -> float | tuple[float, float] | None:
    """
    requests timeout 타입 정규화:
      - float/int -> float
      - (a,b) -> (float(a), float(b))  (None 섞이면 None으로 대체하거나 기본값으로 치환)
      - None/기타 -> None
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, tuple) and len(v) == 2:
        a, b = v
        # requests는 tuple 내 None을 싫어하므로 안전하게 치환
        #  - None이면 0.0(즉시 타임아웃) 대신, "미지정" 의미로 기본값을 넣는 게 보통 더 안전
        #  - 여기서는 cfg 상수(REQ_CONN/READ_TIMEOUT)로 치환
        ca = float(a) if isinstance(a, (int, float)) else float(_REQ_CONN_TIMEOUT)
        cb = float(b) if isinstance(b, (int, float)) else float(_REQ_READ_TIMEOUT)
        return (ca, cb)
    return None

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
            timeout=_coerce_timeout(kw.pop("timeout", None)),
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
            # 403은 크롤링 차단 사이트 → 세션 전체 블랙리스트 즉시 등록
            if resp.status_code == 403:
                _DNS_BAD_HOSTS.add(_host)
                logger.warning("[403-BLACKLIST] %s → blocked for session", _host)
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
            # DH_KEY_TOO_SMALL / CERTIFICATE_VERIFY_FAILED 사이트는
            # 세션 전체에서 완전 차단 (매 쿼리 재시도 방지)
            if ("DH_KEY_TOO_SMALL" in str(e) or
                "CERTIFICATE_VERIFY_FAILED" in str(e)):
                import re as _re  # ← 이 줄 추가
                # 원래 URL 호스트도 등록
                _DNS_BAD_HOSTS.add(_host)
                # 에러 메시지에서 실제 실패 호스트 추출 (리다이렉트 경유 시)
                try:
                    _err_str = str(e)
                    _m = _re.search(r"host='([^']+)'", _err_str)
                    if _m:
                        _real_host = _m.group(1)
                        _DNS_BAD_HOSTS.add(_real_host)
                        logger.warning("[SSL-BLACKLIST] %s + %s → blocked for session",
                                       _host, _real_host)
                    else:
                        logger.warning("[SSL-BLACKLIST] %s → blocked for session", _host)
                except Exception:
                    logger.warning("[SSL-BLACKLIST] %s → blocked for session", _host)
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
    looks_like_pdf_url as _looks_like_pdf_url
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
from .utils import looks_like_pdf_url as _looks_like_pdf_url

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

#
# _normalize_canonical_url is imported from tools.web_rag.utils
#

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
        if "application/pdf" in ct or ext == ".pdf" or (u and _looks_like_pdf_url(u)):
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

    # 🔧 KHIDI /fileDownload 예외 처리:
    #   - 정규화 과정에서 'www.'가 제거되면 KHIDI 서버가 잘못된 Location 헤더를 반환해
    #     'www.khidi.or.krfiledownload' 같은 호스트로 깨질 수 있음.
    #   - /fileDownload 요청에 대해서는 항상 www 호스트를 유지/복원한다.
    try:
        pu = urlparse(u)
        host = (pu.netloc or "").lower()
        path_l = (pu.path or "").lower()
        if ("khidi.or.kr" in host) and ("filedownload" in path_l):
            new_netloc = "www.khidi.or.kr"
            u = urlunparse((
                pu.scheme or "https",
                new_netloc,
                pu.path,
                pu.params,
                pu.query,
                pu.fragment,
            ))
    except Exception:
        # KHIDI 보정 중 오류가 나더라도 전체 흐름을 막지 않음
        pass

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
        from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning  # type: ignore[attr-defined]
        import warnings as _warnings

        # XML 문서를 HTML 파서로 읽을 때 나오는 XMLParsedAsHTMLWarning만 조용히 무시
        with _warnings.catch_warnings():
            _warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
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
    ensure_vector_store_cleared_once as _ensure_vector_store_cleared_once,
    get_collection_count,
    get_total_collection_count,
    seed_web_namespace,
    _default_chroma_dir,
    _resolve_persist_dir_strict,
    has_any_docs,
)

def _stored_urls_path(*, namespace: str, store_kind: str) -> Path:
    """
    stored_urls 캐시 파일 경로 (ns + kind 분리)
      - store_kind: "web" | "local"
    """
    ns = (namespace or "").replace("/", "_").replace("\\", "_")
    base = DATA_DIR / "stored_urls"
    return base / f"stored_urls__{store_kind}__{ns}.json"

def _load_stored_urls_cache(*, namespace: str, store_kind: str = "web") -> set[str]:
    """
    stored_urls 캐시 로드.

    ✅ 정책:
      - (ns 컬렉션 count==0)이면 fresh store로 간주 → stored_urls 캐시를 "스킵" (빈 set 반환)
      - 이때 stale 파일이 있으면 함께 삭제하여 재시도/리빌드 시 혼선 방지

    반환: 정규화 이전 raw URL 문자열 set (상위에서 필요 시 normalize)
    """
    ns = (namespace or "").replace("/", "_").replace("\\", "_")
    base = DATA_DIR / "stored_urls"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    p = _stored_urls_path(namespace=ns, store_kind=store_kind)

    # 1) fresh store 판정(count==0) → 캐시 스킵(+삭제)
    try:
        # get_collection_count / _default_chroma_dir 는 이미 상단에서 ingest_vector로부터 import됨
        cnt = int(get_collection_count(ns, _default_chroma_dir(ns)))
        if cnt == 0:
            try:
                if p.exists():
                    p.unlink()
                    logger.info("[stored_urls] fresh store(count=0) → deleted stale cache: %s", p)
            except Exception:
                pass
            return set()
    except Exception:
        # count 판정 실패 시에는 캐시 로드를 시도
        pass

    # 2) 캐시 로드
    try:
        if not p.exists():
            return set()
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return {str(x) for x in data if isinstance(x, str) and x.strip()}
        if isinstance(data, dict):
            # 과거 포맷 호환: 키를 URL로 간주
            out: set[str] = set()
            for k in data.keys():
                if isinstance(k, str) and k.strip():
                    out.add(k)
            return out
    except Exception as e:
        logger.debug("[stored_urls] load failed ns=%s kind=%s err=%s", ns, store_kind, e)
    return set() 

def _delete_stored_urls_cache(*, namespace: str, store_kind: str = "web") -> None:
    try:
        p = _stored_urls_path(namespace=namespace, store_kind=store_kind)
        if p.exists():
            p.unlink()
            logger.info("[stored_urls] deleted cache: %s", p)
    except Exception as e:
        logger.debug("[stored_urls] delete failed ns=%s kind=%s err=%s", namespace, store_kind, e)

def ensure_vector_store_cleared_once(
    namespace: str,
    *,
    persist_directory: str | None = None,
) -> bool:
    """
    ingest_vector.ensure_vector_store_cleared_once 래퍼:
      - CLEAR_CHROMA_ON_START로 Chroma를 비우는 경우,
        같은 namespace의 stored_urls 캐시도 함께 삭제한다.
    """
    cleared = False
    try:
        cleared = bool(
            _ensure_vector_store_cleared_once(
                namespace,
                persist_directory=persist_directory,
            )
        )
    finally:
        # ✅ 안전장치: CLEAR_CHROMA_ON_START가 켜져 있으면 캐시도 삭제
        if cleared or _cfg_bool("CLEAR_CHROMA_ON_START", False):
            # web_rag/ingest.py는 기본적으로 web 캐시를 지운다.
            _delete_stored_urls_cache(namespace=namespace, store_kind="web")
            # split/local 혼용 흔적 방지: 같은 ns의 local 캐시도 같이 제거
            _delete_stored_urls_cache(namespace=namespace, store_kind="local")
    return cleared


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