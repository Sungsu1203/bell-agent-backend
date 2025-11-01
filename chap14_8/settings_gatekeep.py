from __future__ import annotations

import os
from urllib.parse import urlparse
import logging
from typing import Iterable
from functools import lru_cache
from typing import Set

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config access (CFG → module attr → ENV → default)
# ─────────────────────────────────────────────────────────────
import core.config as config


def _get_cfg_attr(name: str, default):
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    env = os.getenv(name)
    return env if env is not None else default


def _env_flag(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def _truthy(name: str, default: bool = False) -> bool:
    v = _get_cfg_attr(name, default)
    try:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}
    except Exception:
        return default


def _as_set(val: object) -> set[str]:
    if val is None:
        return set()
    # Already set/iterable of strings
    if isinstance(val, set):
        return {str(x).strip().lower() for x in val if str(x).strip()}
    if isinstance(val, (list, tuple)):
        return {str(x).strip().lower() for x in val if str(x).strip()}
    # Comma-separated string
    s = str(val)
    items = [p.strip().lower() for p in s.split(",") if p.strip()]
    return set(items)


# ── 캐시 리프레시 (CFG 기반이므로 no-op 유지) ─────────────────────────────────
def refresh_gatekeep_cache() -> None:
    """CFG 기반으로 전환되어 별도 캐시 불필요. 호환용 no-op."""
    return


# ── 허용 도메인 ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _normalized_allowed_domains() -> Set[str]:
    """ALLOWED_DOMAINS를 _normalize_host로 통일 정규화하여 캐시."""
    base = get_allowed_domains()
    out: Set[str] = set()
    for d in base:
        nd = _normalize_host(d)
        if not nd:
            continue
        out.add(nd)
        # www 동치 옵션이 켜져있으면 상호 형태도 포함
        if _TREAT_WWW_EQUIV:
            if nd.startswith("www."):
                out.add(nd[4:])
            else:
                out.add("www." + nd)
    return out

def get_allowed_domains() -> set[str]:
    """
    CFG 우선. core.config에서 이미 문자열 → 집합 파싱을 수행하는 경우가 많지만,
    여기에서도 안전하게 재파싱합니다. 비어 있으면 빈 집합 반환.
    허용 형식: set/list/tuple/콤마구분 문자열
    """
    try:
        raw = _get_cfg_attr("ALLOWED_DOMAINS", None)
        if raw is None:
            # ENV 폴백도 지원
            raw = os.getenv("ALLOWED_DOMAINS", "")
        return _as_set(raw)
    except Exception:
        return set()


# ── 게이트키핑 플래그 ─────────────────────────────────────────────────────────
def gatekeep_enabled() -> bool:
    """게이트키핑 on/off — CFG 우선, 실패 시 False."""
    try:
        return _truthy("GATE_KEEP_SOURCES", False)
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────
# 모바일/AMP 호스트 매핑 & 옵션 (web_rag.utils와 일치)
# ─────────────────────────────────────────────────────────────
_MOBILE_HOSTS = {
    "m.dailypharm.com": "www.dailypharm.com",
    "m.newsmp.com": "www.newsmp.com",
    "mobile.newsmp.com": "www.newsmp.com",
}

# www 동치 옵션(게이트키핑 비교 시 유리)
_TREAT_WWW_EQUIV: bool = _truthy("URL_TREAT_WWW_EQUIV", False)
# 모바일/AMP 접기 후 www 선호 여부
_MOBILE_TO_WWW: bool = _truthy("URL_NORMALIZE_MOBILE_TO_WWW", True)


# ── 호스트 정규화 ─────────────────────────────────────────────────────────────
@lru_cache(maxsize=4096)
def _normalize_host(u: str) -> str:
    """
    규칙:
    - 스킴: file/data/about/blob → 빈 문자열 반환(네트워크 대상 아님)
    - 자격증명 제거, 호스트 소문자, trailing dot 제거
    - 명시 매핑(m.* → www.* 등) → 모바일/AMP 라벨 접기(m., mobile., amp.)
      (접기 후 www 선호는 URL_NORMALIZE_MOBILE_TO_WWW로 제어)
    - www 동치 옵션(URL_TREAT_WWW_EQUIV)이 켜져도, 내부 비교 일관성을 위해
      allowed와 입력 모두 동일 규칙으로 정규화한다.
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

        # 1) 명시 매핑 우선 적용
        if host in _MOBILE_HOSTS:
            host = _MOBILE_HOSTS[host]

        # 2) amp. 접두 제거
        if host.startswith("amp."):
            host = host[4:]

        # 3) 모바일 라벨 접기: 선두/중간 'm'/'mobile'
        if _MOBILE_TO_WWW:
            parts = [p for p in host.split(".") if p]
            changed = False
            # 선두 라벨 제거
            while parts and parts[0] in ("m", "mobile"):
                parts.pop(0); changed = True
            # news.m.example.com → news.example.com
            if len(parts) >= 3 and parts[1] in ("m", "mobile"):
                parts.pop(1); changed = True
            # 접은 뒤 www 선호
            if changed and parts and not parts[0].startswith("www"):
                parts.insert(0, "www")
            host = ".".join(parts)

        # 4) www 동치 옵션: 비교 일관성 위해 접두 제거(allowed도 동일 규칙 적용)
        if _TREAT_WWW_EQUIV and host.startswith("www."):
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
def is_allowed_url(url: str) -> bool:
    """
    게이트키핑 판단:
    - gatekeep 꺼짐 → 허용
    - 로컬/내장 스킴 → 허용
    - 허용 리스트 비어있고 gatekeep 켜짐 → 차단(경고 1회)
    - 그 외: 정규화 host가 허용 리스트 항목과 **정확히 일치**하는 경우만 허용
             (기본은 서브도메인 비허용; ALLOW_SUBDOMAINS(있으면) True면 서브도메인 허용)
    """
    if not gatekeep_enabled():
        return True
    if is_local_like(url):
        return True

    # 허용 세트(정규화/확장 포함)를 가져옴
    allow = _normalized_allowed_domains()
    if not allow:
        logger.warning("GATE_KEEP_SOURCES=ON 이지만 ALLOWED_DOMAINS가 비었습니다. 외부 소스는 차단됩니다.")
        return False

    host_port = _normalize_host(url)
    if not host_port:
        return False

    base = host_port.split(":", 1)[0]
    if base in allow:
        return True

    # ── 옵션: 서브도메인 허용(기본 OFF)
    allow_sub = _get_cfg_attr("ALLOW_SUBDOMAINS", None)
    if allow_sub is None:
        allow_sub = _env_flag("ALLOW_SUBDOMAINS", default=False)

    try:
        allow_sub_bool = bool(allow_sub) if isinstance(allow_sub, bool) else str(allow_sub).strip().lower() in {"1","true","yes","y","on"}
    except Exception:
        allow_sub_bool = False

    if allow_sub_bool:
        parts = base.split(".")
        # a.b.example.com → b.example.com / example.com 순회하며 비교
        for i in range(len(parts) - 1):
            cand = ".".join(parts[i+1:])
            if cand in allow:
                return True
            # www 동치 옵션이 켜진 경우 반대 형태도 체크
            if _TREAT_WWW_EQUIV:
                if cand.startswith("www.") and cand[4:] in allow:
                    return True
                if ("www." + cand) in allow:
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
