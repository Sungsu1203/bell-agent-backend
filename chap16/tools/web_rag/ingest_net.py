# tools/web_rag/ingest_net.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from typing import Callable, Any, Optional
import threading

import requests

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

# 내부 구현은 시그니처가 약간 달 수 있으므로, Callable[..., bytes | None]로 완화
PdfFetcher = Callable[..., bytes | None]

# PDF 전용 헬퍼는 utils에 이미 있을 수 있으니, Optional로 안전하게 감싼다.
_try_fetch_pdf_impl: Optional[PdfFetcher]
try:
    # utils.try_fetch_pdf의 실제 시그니처와 상관없이 PdfFetcher로 본다.
    from tools.web_rag.utils import try_fetch_pdf as _try_fetch_pdf_impl
except Exception:  # pragma: no cover
    _try_fetch_pdf_impl = None

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
    PDF 전용 fetch 래퍼.
    내부적으로 _try_fetch_pdf_impl(=utils.try_fetch_pdf)를 감싼다.
    """
    if _try_fetch_pdf_impl is None:
        return None
    t = timeout or int(REQ_READ_TIMEOUT)
    try:
        return _try_fetch_pdf_impl(url, t)
    except Exception as e:  # pragma: no cover
        logger.warning("[try_fetch_pdf] url=%s error=%s", url, e)
        return None
