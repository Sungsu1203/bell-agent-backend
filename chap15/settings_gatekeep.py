# settings_gatekeep.py
from __future__ import annotations
import os
from urllib.parse import urlparse
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

# ── ENV flag ──────────────────────────────────────────────────────────────────
def _env_flag(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}

# ── 캐시 리프레시 (테스트/런타임 재설정용) ──────────────────────────────────────
def refresh_gatekeep_cache() -> None:
    try:
        _allowed_domains_cached.cache_clear()
    except Exception:
        pass
    try:
        _gatekeep_enabled_cached.cache_clear()
    except Exception:
        pass

# ── 허용 도메인 ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _allowed_domains_cached(env_value: str) -> set[str]:
    if not env_value:
        return set()
    return {d.strip().lower() for d in env_value.split(",") if d.strip()}

def get_allowed_domains() -> set[str]:
    # 환경값을 캐시 키로 사용 → env 변경 시 자동 반영
    raw = os.getenv("ALLOWED_DOMAINS", "")
    return _allowed_domains_cached(raw)

# ── 게이트키핑 플래그 ─────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _gatekeep_enabled_cached(flag_value: str) -> bool:
    v = (flag_value or "").strip().lower()
    if not v:
        return False
    return v in {"1", "true", "yes", "y", "on"}

def gatekeep_enabled() -> bool:
    # 환경값을 캐시 키로 사용 → env 변경 시 자동 반영
    return _gatekeep_enabled_cached(os.getenv("GATE_KEEP_SOURCES", ""))

# ── 호스트 정규화 ─────────────────────────────────────────────────────────────
def _normalize_host(u: str) -> str:
    """
    규칙:
    - 스킴: file/data/about/blob → 빈 문자열 반환(네트워크 대상 아님)
    - 자격증명 제거, 호스트 소문자, trailing dot 제거, www. 제거
    - IDNA(punycode) 정규화 시도
    - 포트: HTTP 80, HTTPS 443은 기본 포트이므로 제거 / 그 외 포트는 유지
    반환:
      - 'host' 또는 'host:port' (비네트워크면 '')
    """
    try:
        s = (u or "").strip()
        if not s:
            return ""
        pu = urlparse(s)
        scheme = (pu.scheme or "").lower()

        # 로컬/비네트워크 스킴은 빈 호스트
        if scheme in ("file", "data", "about", "blob"):
            return ""

        host = pu.hostname or ""
        if not host:
            return ""

        # IDNA 정규화
        try:
            host = host.encode("idna").decode("ascii")
        except Exception:
            pass

        host = host.lower().rstrip(".")
        if host.startswith("www."):
            host = host[4:]

        # 포트 처리
        port = pu.port
        default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
        if port and port != default_port:
            return f"{host}:{port}"
        return host
    except Exception:
        return ""

# ── 정책 헬퍼: 로컬/루프백/내장 스킴 항상 허용 ─────────────────────────────────
def is_local_like(url: str) -> bool:
    try:
        pu = urlparse((url or "").strip())
        if pu.scheme in ("file", "data", "about", "blob"):
            return True
        h = (pu.hostname or "").lower()
        return h in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False

# ── 메인 판단 로직 ────────────────────────────────────────────────────────────
# settings_gatekeep.py 내 is_allowed_url 교체

def is_allowed_url(url: str) -> bool:
    """
    게이트키핑 판단:
    - gatekeep 꺼짐 → 허용
    - 로컬/내장 스킴 → 허용
    - 허용 리스트 비어있고 gatekeep 켜짐 → 차단(경고 1회)
    - 그 외: 정규화 host가 허용 리스트 항목과 **정확히 일치**하는 경우만 허용
             (기본은 서브도메인 비허용; ALLOW_SUBDOMAINS=1이면 서브도메인 허용)
    """
    if not gatekeep_enabled():
        return True
    if is_local_like(url):
        return True

    allow = get_allowed_domains()
    if not allow:
        logger.warning("GATE_KEEP_SOURCES=ON 이지만 ALLOWED_DOMAINS가 비었습니다. 외부 소스는 차단됩니다.")
        return False

    host_port = _normalize_host(url)
    if not host_port:
        return False

    base = host_port.split(":", 1)[0]
    if base in allow:
        return True

    # ── 옵션: 서브도메인 허용(기본 OFF) ─────────────────────────
    if _env_flag("ALLOW_SUBDOMAINS", default=False):
        for dom in allow:
            if base.endswith("." + dom):
                return True

    return False

# 하위호환 별칭
url_allowed = is_allowed_url

__all__ = [
    "refresh_gatekeep_cache",
    "get_allowed_domains",
    "gatekeep_enabled",
    "is_local_like",
    "is_allowed_url",
    "url_allowed",
    "_normalize_host",
]
