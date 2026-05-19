from __future__ import annotations

import os
import logging
import re
from functools import lru_cache
from urllib.parse import urlparse
from typing import Iterable, Set

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config access (CFG → module attr → ENV → default)
# ─────────────────────────────────────────────────────────────
import core.config as config
from typing import cast

# 런타임 주입 허용 도메인(에이전트 계산 결과가 즉시 반영되도록)
_RUNTIME_ALLOWED: Set[str] = set()

# ── (선택) URL 정규화기: ingest/utils와 규칙 일치 ─────────────────────────────
try:
    # tools.web_rag.utils에서 사용 중인 normalize_url을 재사용
    from tools.web_rag.utils import normalize_url as _canon_url
except Exception:  # utils 미존재/순환 임포트 등 모든 상황에서 안전 폴백
    def _canon_url(u: str) -> str:
        return (u or "").strip()

def _get_cfg_attr(name: str, default):
    """CFG → module attr → ENV → default"""
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

# ── 기본 허용 도메인(프로젝트 공통 베이스) ─────────────────────────────────────
#  - CFG/ENV/런타임 주입이 없다면 이 베이스가 최소 허용셋이 됩니다.
#  - 운영 환경에서 확장하려면 ALLOWED_DOMAINS 또는 ALLOWED_DOMAINS_EXTRA 로 보강하세요.
_BASE_ALLOWED_DOMAINS: tuple[str, ...] = (
    # 공공/통계/보건 (agent.vector_search._domain_bonus의 public_hosts와 조응)
    "mfds.go.kr",
    "kosis.kr",
    "index.go.kr",
    "khidi.or.kr",
    "hira.or.kr",
    "data.go.kr",
    "moef.go.kr",
    "law.go.kr",
    "dart.fss.or.kr",

    # 제약/의약/헬스케어 전문 매체 (agent.vector_search._domain_bonus의 pharma_hosts와 조응)
    "dailypharm.com",
    "medipana.com",
    "newsmp.com",
    "yakup.com",
    "kpanews.co.kr",
    "pharmnews.com",
    "medicopharma.co.kr",
    "healtho.co.kr",
)

# ── 공공 포털/기관 도메인: www 강제 금지 규칙 ──────────────────────────────────
_NO_WWW_SUFFIXES: tuple[str, ...] = ("go.kr", "or.kr")
_NO_WWW_EXACT: tuple[str, ...] = ("kosis.kr", "mfds.go.kr", "khidi.or.kr", "index.go.kr", "hira.or.kr")

def _no_www_domain(hostname: str) -> bool:
    """
    www 접두사를 강제 부여하면 안 되는 도메인 여부.
    - *.go.kr, *.or.kr, 그리고 명시 예외 리스트는 www 금지
    """
    h = (hostname or "").strip().lower()
    if not h:
        return False
    base = h.split(":", 1)[0]
    if base in _NO_WWW_EXACT:
        return True
    return any(base.endswith(suf) for suf in _NO_WWW_SUFFIXES)


def set_runtime_allowed_domains(domains: Iterable[str]) -> None:
    """에이전트가 계산한 허용 도메인을 런타임으로 주입."""
    global _RUNTIME_ALLOWED
    try:
        _RUNTIME_ALLOWED = {d.strip().lower() for d in domains if d and d.strip()}
    except Exception:
        _RUNTIME_ALLOWED = set()
    # 주입 직후 캐시 무효화(즉시 반영)
    try:
        _normalized_allowed_domains.cache_clear()
        _normalize_host.cache_clear()
        # 향후 _is_allowed 캐시를 도입하는 경우 여기도 같이 비워야 합니다.
        # _is_allowed_cached.cache_clear()  # (도입 시 활성화)
    except Exception:
        pass

def clear_runtime_allowed_domains() -> None:
    """런타임 주입된 허용 도메인 set 을 초기화 (토픽 전환 hook).

    `set_runtime_allowed_domains` 가 박제한 snapshot 을 명시적으로 비워
    다음 `get_allowed_domains()` 호출이 ENV/CFG 로부터 fresh 재계산하도록 한다.
    부수 효과: `_normalized_allowed_domains` lru_cache 도 함께 clear (RUNTIME 변경은 lru_cache 정합성에도 영향).
    """
    global _RUNTIME_ALLOWED
    _RUNTIME_ALLOWED = set()
    try:
        _normalized_allowed_domains.cache_clear()
    except Exception:
        pass

def _flag(name: str, default: bool = False) -> bool:
    """config.truthy가 있으면 우선 사용(단일 진입점)."""
    try:
        return cast(bool, config.truthy(name, default))  
    except Exception:
        v = (os.getenv(name) or "").strip().lower()
        if not v:
            return default
        return v in {"1", "true", "yes", "y", "on"}


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
    """CFG/ENV 변경 또는 런타임 주입 반영을 위해 캐시 무효화."""
    try:
        _normalized_allowed_domains.cache_clear()  
        _normalize_host.cache_clear()              
    except Exception:
        pass


# ── 허용 도메인 ────────────────────────────────────────────────────────────────
def get_allowed_domains() -> Set[str]:
    """런타임 주입 > CFG > ENV 순으로 허용 도메인 해석."""
    if _RUNTIME_ALLOWED:
        return _RUNTIME_ALLOWED
    out: Set[str] = set(x.strip().lower() for x in _BASE_ALLOWED_DOMAINS)
    # CFG가 집합/리스트/문자열을 제공하면 병합
    try:
        raw = _get_cfg_attr("ALLOWED_DOMAINS", None)
        if isinstance(raw, (set, list, tuple)):
            out |= {str(x).strip().lower() for x in raw if str(x).strip()}
        elif isinstance(raw, str) and raw.strip():
            out |= _as_set(raw)
    except Exception:
        pass
    # ENV 기본(ALLOWED_DOMAINS) 및 확장(ALLOWED_DOMAINS_EXTRA) 병합
    out |= _as_set(os.getenv("ALLOWED_DOMAINS", ""))
    out |= _as_set(os.getenv("ALLOWED_DOMAINS_EXTRA", ""))
    return out

# ── TLD 화이트리스트 & 호스트 유효성 검사 ─────────────────────────────────────
#   - 잘못 결합된 호스트(khidi.or.krkps 등) 드랍
_TLD_ALLOW: set[str] = {
    "com","org","net","io","ai","co","kr","go.kr","or.kr","ac.kr","re.kr",
    "biz","info","me","dev","edu","gov"
}

def _valid_host(host: str) -> bool:
    """
    허용 문자 검증, 연속 점/선두/말미 하이픈 방지, TLD 화이트리스트 검사.
    포트는 제거한 뒤 검사합니다.
    """
    h = (host or "").strip().lower()
    if not h:
        return False
    # 포트 제거
    h = h.split(":", 1)[0]
    # 허용 문자(a-z0-9.-) 외 존재하면 탈락
    if re.search(r"[^a-z0-9\.\-]", h):
        return False
    if ".." in h or h.startswith("-") or h.endswith("-"):
        return False
    parts = [p for p in h.split(".") if p]
    if len(parts) < 2:
        return False
    tld = parts[-1]
    last2 = ".".join(parts[-2:])  # e.g., go.kr
    return (tld in _TLD_ALLOW) or (last2 in _TLD_ALLOW)


@lru_cache(maxsize=1)
def _normalized_allowed_domains() -> Set[str]:
    """ALLOWED_DOMAINS를 _normalize_host로 통일 정규화하여 캐시."""
    base = get_allowed_domains()
    out: Set[str] = set()
    for d in base:
        nd = _normalize_host(d)
        if not nd or not _valid_host(nd):
            continue
        out.add(nd)
        # www 동치 옵션이 켜져있으면 상호 형태도 포함(단, 공공 포털은 제외)
        if _treat_www_equiv() and not _no_www_domain(nd):
            if nd.startswith("www."):
                out.add(nd[4:])
            else:
                out.add("www." + nd)
    return out


# ── 게이트키핑 플래그 ─────────────────────────────────────────────────────────
def gatekeep_enabled() -> bool:
    """게이트키핑 on/off — CFG 우선, 실패 시 False."""
    return _flag("GATE_KEEP_SOURCES", False)

# ─────────────────────────────────────────────────────────────
# 모바일/AMP 호스트 매핑 & 옵션 (web_rag.utils와 일치)
# ─────────────────────────────────────────────────────────────
_MOBILE_HOSTS = {
    "m.dailypharm.com": "www.dailypharm.com",
    "m.newsmp.com": "www.newsmp.com",
    "mobile.newsmp.com": "www.newsmp.com",
    # yakup 모바일 보정(존재 시 www로 접기)
    "m.yakup.com": "www.yakup.com",
}

# 동적 플래그 getter (리로드 시점마다 최신값 반영)
def _treat_www_equiv() -> bool:
    return _flag("URL_TREAT_WWW_EQUIV", False)

def _mobile_to_www() -> bool:
    return _flag("URL_NORMALIZE_MOBILE_TO_WWW", True)


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
        # 베어 도메인/호스트도 허용: 스킴이 없으면 임시로 http:// 를 부여해 파싱
        _s_for_parse = s if "://" in s else f"http://{s}"
        pu = urlparse(_s_for_parse)
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
        if _mobile_to_www():
            parts = [p for p in host.split(".") if p]
            changed = False
            # 선두 라벨 제거
            while parts and parts[0] in ("m", "mobile"):
                parts.pop(0); changed = True
            # news.m.example.com → news.example.com
            if len(parts) >= 3 and parts[1] in ("m", "mobile"):
                parts.pop(1); changed = True
            # 접은 뒤 www 선호(옵션 성격): 이미 다른 서브도메인이 있으면 추가 안 함
            if changed and parts:
                # 공공 포털/기관 도메인은 www 강제 금지
                if not parts[0].startswith("www") and len(parts) == 2:
                    base_host = ".".join(parts)
                    if not _no_www_domain(base_host):
                        parts.insert(0, "www")
            host = ".".join(parts)

        # 4) www 동치 옵션: 비교 일관성 위해 접두 제거(allowed도 동일 규칙 적용)
        if _treat_www_equiv() and host.startswith("www."):
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
    # ① URL 자체를 먼저 정규화(모바일/AMP/추적 파라미터 제거 등)
    #    - ingest 파이프라인과 동일한 규칙으로 맞추기 위함
    _u = _canon_url(url)

    if is_local_like(_u):
        return True

    # 허용 세트(정규화/확장 포함)를 가져옴
    allow = _normalized_allowed_domains()
    if not allow:
        logger.warning("GATE_KEEP_SOURCES=ON 이지만 ALLOWED_DOMAINS가 비었습니다. 외부 소스는 차단됩니다.")
        return False

    # ② 호스트 정규화(모바일 라벨 접기, www 동치, 포트 보정 등)
    host_port = _normalize_host(_u)
    if not host_port:
        return False

    base = host_port.split(":", 1)[0]
    # 호스트 유효성(TLD 등) 실패 시 즉시 차단
    if not _valid_host(base):
        return False

    if base in allow:
        return True

    # ── 옵션: 서브도메인 허용(기본 OFF)
    allow_sub_bool = _flag("ALLOW_SUBDOMAINS", False)

    if allow_sub_bool:
        parts = base.split(".")
        # a.b.example.com → b.example.com / example.com 순회하며 비교
        for i in range(len(parts) - 1):
            cand = ".".join(parts[i+1:])
            if cand in allow:
                return True
            # www 동치 옵션이 켜진 경우 반대 형태도 체크
            if _treat_www_equiv():
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
    "set_runtime_allowed_domains",
    "clear_runtime_allowed_domains",
    "gatekeep_enabled",
    "is_local_like",
    "is_allowed_url",
    "url_allowed",
    "_normalize_host",
    "_no_www_domain",
    "_valid_host",
]
