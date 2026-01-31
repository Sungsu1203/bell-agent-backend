# tools/web_rag/ingest_net.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from typing import Callable, Any, Optional
import threading

import requests
import socket
from requests.exceptions import SSLError
try:
    from urllib3.exceptions import NameResolutionError as _UR_NRE
    _EXC_NAME_RESOLUTION: tuple[type[BaseException], ...] = (socket.gaierror, _UR_NRE)
except Exception:  # pragma: no cover
    _EXC_NAME_RESOLUTION = (socket.gaierror,)

# ingest_config 쪽 런타임 설정/헬퍼를 가져와서
# 이 모듈에서 실제로 사용할 네트워크 관련 상수로 재정의한다.
from .ingest_config import (
    _REQ_CONN_TIMEOUT,
    _REQ_READ_TIMEOUT,
    _UA,
    _cfg_str,
    _cfg_int,
    _cfg_bool,
 )
# ─────────────────────────────────────────────
# 이 모듈은 "네트워크 단일 진입점"입니다.
#  - HTTP 요청은 반드시 여기 정의된 함수들을 통해 수행합니다.
#  - 다른 모듈에서 직접 requests/try_fetch_pdf(utils) 등을 호출하지 않도록 합니다.
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# ingest_config 내부 심볼 → net 레이어용 심볼 재노출
# ─────────────────────────────────────────────

# 타임아웃(sec): ingest_config에서 ENV 기반으로 계산된 값 사용
REQ_CONN_TIMEOUT: float = _REQ_CONN_TIMEOUT
REQ_READ_TIMEOUT: float = _REQ_READ_TIMEOUT

# User-Agent: 통일된 UA 문자열 사용
USER_AGENT: str = _UA

# 기타 네트워크 옵션은 CFG → _cfg_* 헬퍼를 통해 가져온다.
#  - REQUESTS_MAX_REDIRECTS: 없으면 5
#  - REQUESTS_CA_BUNDLE: 경로가 비어있으면 None
#  - REQUESTS_VERIFY_SSL: bool 플래그(없으면 True)
MAX_REDIRECTS: int = _cfg_int("REQUESTS_MAX_REDIRECTS", 5)
CA_BUNDLE: str | None = _cfg_str("REQUESTS_CA_BUNDLE", "") or None
VERIFY_SSL: bool = _cfg_bool("REQUESTS_VERIFY_SSL", True)

# ─────────────────────────────────────────────
# 타입 정의
# ─────────────────────────────────────────────

# 공개 시그니처: “(url, timeout) → bytes | None” 형태
TryFetchPdf = Callable[[str, int], bytes | None]

# PDF/네임 해석 에러 격리를 위한 전역 세트
SSL_QUARANTINE: set[str] = set()
DNS_QUARANTINE: set[str] = set()


def tag_quarantine(url: str, *, reason: str = "ssl_error") -> None:
    """격리 사유를 로깅(메트릭 등과 연동 가능)."""
    try:
        logger.info("[net][quarantine] %s (%s)", url, reason)
    except Exception:
        pass

# ─────────────────────────────────────────────
# 공용 requests.Session
# ─────────────────────────────────────────────

_session_lock = threading.Lock()
_requests_session: Optional[requests.Session] = None


def get_requests_session() -> requests.Session:
    """공유 requests.Session (CA 번들/SSL/헤더 설정 포함)."""
    global _requests_session
    if _requests_session is not None:
        return _requests_session

    with _session_lock:
        if _requests_session is not None:
            return _requests_session

        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})

        # SSL 검증/CA 번들
        if CA_BUNDLE:
            s.verify = CA_BUNDLE
        else:
            s.verify = VERIFY_SSL

        s.max_redirects = MAX_REDIRECTS
        _requests_session = s
        return s


# ─────────────────────────────────────────────
# Fetch helpers
# ─────────────────────────────────────────────

def fetch_binary(url: str, timeout: int | None = None) -> bytes | None:
    """URL에서 바이너리를 가져옵니다. 실패 시 None."""
    sess = get_requests_session()
    t = timeout or int(REQ_READ_TIMEOUT)
    try:
        r = sess.get(url, timeout=(REQ_CONN_TIMEOUT, t), stream=True)
        r.raise_for_status()
        return r.content
    except Exception as e:  # pragma: no cover
        logger.warning("[fetch_binary] url=%s error=%s", url, e)
        return None


def fetch_text(
    url: str,
    timeout: int | None = None,
    *,
    encoding: str | None = None,
) -> str | None:
    """텍스트 응답을 유니코드 문자열로 반환. 실패 시 None."""
    import chardet  # 여기서만 사용

    sess = get_requests_session()
    t = timeout or int(REQ_READ_TIMEOUT)
    try:
        r = sess.get(url, timeout=(REQ_CONN_TIMEOUT, t))
        r.raise_for_status()
        data = r.content
        enc = encoding or r.encoding
        if not enc:
            guessed = chardet.detect(data)
            enc = guessed.get("encoding") or "utf-8"
        return data.decode(enc, errors="replace")
    except Exception as e:  # pragma: no cover
        logger.warning("[fetch_text] url=%s error=%s", url, e)
        return None


def fetch_json(url: str, timeout: int | None = None) -> Any | None:
    """JSON 응답을 파싱하여 반환. 실패 시 None."""
    sess = get_requests_session()
    t = timeout or int(REQ_READ_TIMEOUT)
    try:
        r = sess.get(url, timeout=(REQ_CONN_TIMEOUT, t))
        r.raise_for_status()
        return r.json()
    except Exception as e:  # pragma: no cover
        logger.warning("[fetch_json] url=%s error=%s", url, e)
        return None


def try_fetch_pdf(url: str, timeout: int | None = None) -> bytes | None:
    """
    PDF 전용 fetch 헬퍼.
    - 성공 시: PDF 바이트(bytes) 반환
    - SSLError 발생 시: SSL_QUARANTINE에 추가 후 None
    - DNS 해석 오류 발생 시: DNS_QUARANTINE에 호스트 추가 후 None
    - 그 외 예외: 경고만 로그 후 None

    외부 계약(contract):
      (url: str, timeout: int) → bytes | None
    """
    u = (url or "").strip()
    if not u:
        return None

    # 이미 SSL 격리된 URL은 재시도하지 않음
    if u in SSL_QUARANTINE:
        return None

    sess = get_requests_session()
    t = timeout or int(REQ_READ_TIMEOUT)
    try:
        r = sess.get(u, timeout=(REQ_CONN_TIMEOUT, t), stream=True)
        r.raise_for_status()
        return r.content or b""
    except SSLError:
        SSL_QUARANTINE.add(u)
        tag_quarantine(u, reason="ssl_error")
        return None
    except _EXC_NAME_RESOLUTION:
        # DNS 해석 실패 → 호스트 단위 격리
        try:
            from urllib.parse import urlparse as _up
            host = (_up(u).netloc or "").split("/", 1)[0].lower()
            if host:
                DNS_QUARANTINE.add(host)
                logger.info("[dns][quarantine] %s", host)
        except Exception:
            pass
        return None
    except Exception as e:  # pragma: no cover
        logger.warning("[try_fetch_pdf] url=%s error=%s", u, e)
        return None


__all__ = [
    # 타입
    "TryFetchPdf",
    # 설정/세션
    "REQ_CONN_TIMEOUT",
    "REQ_READ_TIMEOUT",
    "USER_AGENT",
    "MAX_REDIRECTS",
    "CA_BUNDLE",
    "VERIFY_SSL",
    "get_requests_session",
    # 네트워크 헬퍼
    "fetch_binary",
    "fetch_text",
    "fetch_json",
    "try_fetch_pdf",
    # 격리/태깅 심볼
    "SSL_QUARANTINE",
    "DNS_QUARANTINE",
    "tag_quarantine",
]
