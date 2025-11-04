from __future__ import annotations

import logging
logger = logging.getLogger(__name__)
from typing import Literal

import io
import json
import os
import re
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Callable
from datetime import datetime
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import base64

import requests
import certifi
import chardet
from langchain_community.document_loaders import WebBaseLoader

# 게이트키핑
from settings_gatekeep import (
    gatekeep_enabled,
    url_allowed,
    _normalize_host,  # 로그 요약용 (없으면 제거 가능)
)

# ✅ 메트릭 이벤트 훅 (안전 임포트: 미존재/비활성 시 no-op, 시그니처 통일)
from typing import Any
try:
    from tools.metrics import event as _metrics_event  # 실제 훅
    def event(kind: str, **payload: Any) -> Any:  # 시그니처 고정
        return _metrics_event(kind, **payload)
except Exception:
    def event(kind: str, **payload: Any) -> Any:  # 시그니처 고정
        return None

from core.config import CFG, reload_config as _reload_config


# ─────────────────────────────────────────────────────────────
# CFG helper shims (define only if missing to avoid redeclare)
# ─────────────────────────────────────────────────────────────
if "_cfg_str" not in globals():
    def _cfg_str(key: str, default: str = "") -> str:
        try:
            v = getattr(CFG, key)
            return (str(v).strip() if v is not None else default)
        except Exception:
            return default

if "_cfg_int" not in globals():
    def _cfg_int(key: str, default: int = 0) -> int:
        try:
            v = getattr(CFG, key)
            if v is None or v == "":
                return default
            return int(str(v).strip())
        except Exception:
            return default

if "_cfg_float" not in globals():
    def _cfg_float(key: str, default: float = 0.0) -> float:
        try:
            v = getattr(CFG, key)
            if v is None or v == "":
                return default
            return float(str(v).strip())
        except Exception:
            return default

# NOTE: 이 파일에는 이미 _cfg_* 헬퍼가 존재합니다(다른 위치).
#       재정의 충돌을 피하기 위해 새 정의는 두지 않고 기존 함수를 그대로 사용합니다.

# ─────────────────────────────────────────────────────────────────────────────
# HTTPS 세션 (검증 ON)
# ─────────────────────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({"User-Agent": (_cfg_str("USER_AGENT", default="BookWriterBot/1.0"))})
session.verify = certifi.where()  # 신뢰 루트

# 런타임 설정 재적용 훅 (외부에서 CFG.reload 후 호출 권장)
def refresh_runtime_config() -> None:
    """
    CFG 값이 바뀐 뒤(예: reload_config()) 런타임 세션 헤더/옵션 재적용.
    """
    try:
        _reload_config()  # in-place 갱신
    except Exception:
        pass
    try:
        session.headers.update({"User-Agent": (_cfg_str("USER_AGENT", default="BookWriterBot/1.0"))})
        # 필요 시 타임아웃/프록시 등도 여기서 재설정 가능
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 문자 정규화(유니코드/제로폭 제거/전각→반각)
# ─────────────────────────────────────────────────────────────────────────────
import unicodedata

# 흔한 제로폭 문자 집합
_ZERO_WIDTH = {
    "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff",  # ZWSP, ZWNJ, ZWJ, WJ, BOM
    "\u180e", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
}

def _strip_zero_width(s: str) -> str:
    if not s:
        return s
    return "".join(ch for ch in s if ch not in _ZERO_WIDTH)

def _to_halfwidth(s: str) -> str:
    # NFKC가 전각→반각 포함, 추가적으로 공백류 정리
    if not s:
        return s
    s2 = unicodedata.normalize("NFKC", s)
    return s2

NormalizationForm = Literal["NFC", "NFD", "NFKC", "NFKD"]

def _normalize_unicode(
    s: str,
    *,
    form: NormalizationForm = "NFKC",
    strip_ws: bool = True
) -> str:
    """BOM/제로폭 제거 → 유니코드 정규화 → 전각→반각 → 공백 정리"""
    if not s:
        return ""
    # BOM/제로폭 제거
    s = _strip_zero_width(s)
    # 유니코드 정규화(NFKC 기본)
    try:
        s = unicodedata.normalize(form, s)
    except Exception:
        # 정상적이면 여기 안 옵니다. (form은 Literal로 제한)
        pass
    # 전각→반각(대부분 NFKC에 포함되지만 명시 호출)
    s = _to_halfwidth(s)
    if strip_ws:
        s = s.strip()
    return s

# ─────────────────────────────────────────────────────────────
# [ADD] 안전 바이트 → 텍스트 디코더
# ─────────────────────────────────────────────────────────────
def safe_decode(b: bytes, fallback: str | None = None) -> str:
    try:
        return b.decode("utf-8")
    except Exception:
        pass
    for enc in ("cp949", "euc-kr", "latin-1"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode(fallback or "utf-8", errors="ignore")

def http_get(url: str, **kw) -> requests.Response:
    """requests.Session.get 래퍼 (기본 타임아웃 튜플)."""
    kw.setdefault("timeout", (_cfg_int("WEB_FETCH_TIMEOUT_CONNECT", default=6),
                              _cfg_int("WEB_FETCH_TIMEOUT_READ", default=20)))
    return session.get(url, **kw)

# =============================================================================
# Env & Paths
# =============================================================================
# ※ .env 로드는 core.config에서 일괄 처리. 이 모듈은 CFG만 신뢰.
# 프로젝트/데이터 루트: CFG만 사용
_PRJ_ROOT_CAND = _cfg_str("PROJECT_ROOT", "")
PROJECT_ROOT = Path(_PRJ_ROOT_CAND) if _PRJ_ROOT_CAND else Path(__file__).resolve().parents[1]
_DATA_DIR_CAND = _cfg_str("WEB_RAG_DATA_DIR", "")
DATA_DIR = Path(_DATA_DIR_CAND) if _DATA_DIR_CAND else (PROJECT_ROOT / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 외부에서 참조되는 캐시 키/플래그
_RECENTLY_CLEARED: dict[str, float] = {}
_FRESH_KEYS: set[tuple[str, str]] = set()

def _now(fmt: str = "%Y_%m%d_%H%M%S") -> str:
    return datetime.now().strftime(fmt)

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _truthy_cfg(name: str, default: bool = False) -> bool:
    """CFG 불리언 키를 안전하게 해석."""
    return _cfg_bool(name, default=default)

# ─────────────────────────────────────────────────────────────────────────────
# JSON-safe 변환(바이너리 → base64) 헬퍼
# ─────────────────────────────────────────────────────────────────────────────
def _looks_binary_text(s: str) -> bool:
    """문자열이 사실상 바이너리인지 휴리스틱 판별."""
    if not s:
        return False
    # PDF 시그니처
    if s.startswith("%PDF-") or "%PDF-" in s[:32]:
        return True
    # 제어문자 비율이 높으면 바이너리로 간주
    ctrl = sum(1 for ch in s if ord(ch) < 9 or (10 < ord(ch) < 32))  # \n(10)은 허용, \r(13)은 허용
    return (ctrl / max(1, len(s))) > 0.05

def _to_safe_json_record(it: Dict[str, Any]) -> Dict[str, Any]:
    """
    단일 검색 아이템을 JSON 저장용으로 정리:
    - raw_content가 바이너리로 의심되면 raw_b64로 치환
    - content_type 힌트 설정
    - 너무 긴 raw_content는 미리보기로 축약
    """
    d = dict(it or {})
    raw = d.get("raw_content")
    mime = d.get("content_type") or d.get("mime") or ""

    if isinstance(raw, (bytes, bytearray)):
        d["raw_b64"] = base64.b64encode(bytes(raw)).decode("ascii")
        d["raw_is_binary"] = True
        d.pop("raw_content", None)
        if not mime:
            d["content_type"] = "application/octet-stream"
    elif isinstance(raw, str) and _looks_binary_text(raw):
        # 문자열 형태로 들어왔지만 사실상 바이너리
        d["raw_b64"] = base64.b64encode(raw.encode("latin1", "ignore")).decode("ascii")
        d["raw_is_binary"] = True
        d.pop("raw_content", None)
        if "%PDF-" in raw[:64] and not mime:
            d["content_type"] = "application/pdf"
        elif not mime:
            d["content_type"] = "application/octet-stream"
    else:
        # 순수 텍스트이면서 너무 길면 보기용 프리뷰만 남김(선택)
        if isinstance(raw, str) and len(raw) > 4000:
            d["raw_preview"] = raw[:4000]
            d.pop("raw_content", None)

    # content가 과도하게 길면 축약(선택)
    txt = d.get("content")
    if isinstance(txt, str) and len(txt) > 8000:
        d["content"] = txt[:8000] + " …(truncated)"

    return d

# ─────────────────────────────────────────────────────────────────────────────
# 결과 저장 (web.json 스냅샷) + 메트릭
# ─────────────────────────────────────────────────────────────────────────────
def _save_results(
    items: List[Dict[str, Any]] | List[Any],
    out_dir: Optional[Union[Path, str]] = None,              # ← 기존 시그니처 유지 (deprecated)
    *,
    query: Optional[str] = None,
    base_dir: Optional[Union[Path, str]] = None,             # ← 신규 권장 인자
) -> str:
    """
    결과 저장 경로 우선순위:
      1) base_dir 인자(권장)
      2) out_dir 인자(구형, deprecated)
      3) core.paths.research_base_dir()  (가능 시)
      4) WEB_RAG_DATA_DIR / DATA_DIR
    """
    # 1) 명시 base_dir(권장)
    if base_dir is not None:
        base_path = Path(base_dir)
    # 2) 구형 out_dir (후방호환)
    elif out_dir is not None:
        base_path = Path(out_dir)
        logger.debug("[_save_results] 'out_dir' is deprecated; prefer 'base_dir' keyword.")
    else:
        # 3) 연구 산출물 표준 경로
        try:
            from core.paths import research_base_dir
            base_path = Path(research_base_dir())
        except Exception:
            # 4) 최후 폴백: 기존 환경 변수/상수
            env_dir = (getattr(CFG, "WEB_RAG_DATA_DIR", None) or os.getenv("WEB_RAG_DATA_DIR", "") or "").strip()
            base_path = Path(env_dir) if env_dir else DATA_DIR

    base_path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y_%m_%d_%H%M%S_%f")
    suffix = ""
    if query:
        h = hashlib.blake2b(query.encode("utf-8"), digest_size=4).hexdigest()
        suffix = f"_{h}"
    fname = f"resources_{ts}{suffix}.json"
    path = base_path / fname

    # ⬇️ 추가된 한 줄: JSON-safe 변환
    safe_items = [_to_safe_json_record(x) for x in (items or [])]

    with path.open("w", encoding="utf-8") as f:
        json.dump(safe_items, f, ensure_ascii=False, indent=2)

    logger.info("[web_search] results saved → %s (items=%d)", path, len(safe_items))

    # ✅ METRICS: 저장 스냅샷 기록 (no-op 안전)
    try:
        event(
            "results_saved",
            items_count=len(items or []),
            saved_path=str(path),
            query_hash=(suffix.lstrip("_") if suffix else "")
        )
    except Exception:
        pass

    return str(path)

# ─────────────────────────────────────────────────────────────────────────────
# 검색 정책/TopN (기존 키 + 신규 alias 지원)
# ─────────────────────────────────────────────────────────────────────────────
_MIN_RESULTS_OK = _cfg_int("SEARCH_MIN_OK", default=_cfg_int("WEB_MIN_RESULTS_OK", default=1))
_BACKEND_PICK_POLICY = _cfg_str("SEARCH_POLICY",
                                default=_cfg_str("WEB_BACKEND_PICK_POLICY", default="best_of_chain")).lower()
_SEARCH_TOPN = _cfg_int("SEARCH_TOPN", default=10)

# ─────────────────────────────────────────────────────────────────────────────
# 로그 도우미
# ─────────────────────────────────────────────────────────────────────────────
_LOG_TOPK = _cfg_int("LOG_TOPK", default=3)
_LOG_WRAP = _cfg_int("LOG_WRAP", default=88)

def _ell(s: str, n: int = _LOG_WRAP) -> str:
    s = (s or "").replace("\n", " ").strip()
    return (s[: n - 1] + "…") if len(s) > n else s

def _host_of(u: str) -> str:
    try:
        pu = urlparse(_normalize_url(u))
        return (pu.netloc or "").lower()
    except Exception:
        try:
            return (urlparse(u).netloc or "").lower()
        except Exception:
            return ""


# =============================================================================
# URL 정규화/디듀프/TopN
# =============================================================================

# ── 정규화 동작 스위치(환경변수/CFG로 제어) ─────────────────────────────────
def _cfg_bool(name: str, *, default: bool) -> bool:
    v = getattr(CFG, name, None)
    if isinstance(v, bool):
        return v
    s = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return s in ("1", "true", "yes", "on")

_URL_STRIP_DEFAULT_PORTS         = _cfg_bool("URL_STRIP_DEFAULT_PORTS", default=True)
_URL_NORMALIZE_DEFAULT_INDEX     = _cfg_bool("URL_NORMALIZE_DEFAULT_INDEX", default=True)
_URL_CANONICALIZE_TRAILING_SLASH = _cfg_bool("URL_CANONICALIZE_TRAILING_SLASH", default=True)
_URL_SORT_QUERY                  = _cfg_bool("URL_SORT_QUERY", default=True)
_URL_CANONICALIZE_AMP            = _cfg_bool("URL_CANONICALIZE_AMP", default=True)
_URL_TREAT_WWW_EQUIV             = _cfg_bool("URL_TREAT_WWW_EQUIV", default=False)  # 필요시 on

# 추적/광고성 파라미터(확장)
_TRACKING_PARAMS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id",
    "gclid","fbclid","dclid","msclkid","yclid","igsh","mc_cid","mc_eid",
    "spm","ref","ref_src","cmpid","cmp","campaign","ga_source","ga_medium",
    "utm_name","utm_reader","utm_social","utm_social-type","vero_id"
}

def _strip_default_port(host: str, scheme: str) -> str:
    if not (_URL_STRIP_DEFAULT_PORTS and host):
        return host
    if ":" not in host:
        return host
    name, _, port = host.rpartition(":")
    if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
        return name
    return host

def _drop_default_index(path: str) -> str:
    if not (_URL_NORMALIZE_DEFAULT_INDEX and path):
        return path or "/"
    s = path or "/"
    for idx in ("/index.html", "/index.htm", "/index.php", "/default.aspx", "/default.htm"):
        if s.lower().endswith(idx):
            return s[:-len(idx)] or "/"
    return s

def _collapse_slashes(path: str) -> str:
    return re.sub(r"/{2,}", "/", path or "/")

def _normalize_path_segments(path: str) -> str:
    segs: list[str] = []
    for p in (path or "/").split("/"):
        if p in ("", "."):
            continue
        if p == "..":
            if segs: segs.pop()
            continue
        segs.append(p)
    out = "/" + "/".join(segs)
    return out or "/"

def _strip_amp_variants(path: str, qs_pairs: list[tuple[str,str]]) -> tuple[str, list[tuple[str,str]]]:
    if not _URL_CANONICALIZE_AMP:
        return path, qs_pairs
    # /amp 또는 /amp/ 접기
    p = re.sub(r"/amp/?$", "/", path or "/", flags=re.I)
    # ?amp=1, ?output=amp, ?amp=true 등 제거
    qs_pairs = [(k,v) for (k,v) in qs_pairs if not (k.lower() in {"amp","amp_js_v","output"} and (v.lower() in {"1","true","amp","standard"} or k.lower()=="output"))]
    return p, qs_pairs

# ─────────────────────────────────────────────────────────────
# [ADD] 모바일/AMP 호스트 명시 매핑
# ─────────────────────────────────────────────────────────────
_MOBILE_HOSTS = {
    "m.dailypharm.com": "www.dailypharm.com",
    "m.newsmp.com": "www.newsmp.com",
    "mobile.newsmp.com": "www.newsmp.com",
}

def _normalize_host_map(host: str) -> str:
    h = host.lower().strip(".")
    return _MOBILE_HOSTS.get(h, h[4:] if h.startswith("amp.") else h)

def _sort_and_filter_query(qs_pairs: list[tuple[str,str]]) -> list[tuple[str,str]]:
    # 추적 파라미터 제거 + 키/값 트리밍 + 정렬
    cleaned = []
    for (k,v) in qs_pairs:
        k2 = (k or "").strip()
        v2 = (v or "").strip()
        if not k2:
            continue
        if k2.lower() in _TRACKING_PARAMS:
            continue
        cleaned.append((_normalize_unicode(k2, strip_ws=True),
               _normalize_unicode(v2, strip_ws=True)))
    if _URL_SORT_QUERY:
        cleaned.sort(key=lambda kv: (kv[0].lower(), kv[1]))
    return cleaned

def _mobile_to_www_enabled() -> bool:
    """
    모바일 서브도메인(m./mobile.) → www. 치환 여부 스위치.
    CFG.URL_NORMALIZE_MOBILE_TO_WWW (기본: 켬).
    """
    return _cfg_bool("URL_NORMALIZE_MOBILE_TO_WWW", default=True)

def _normalize_mobileish_host(host: str) -> str:
    """
    모바일/AMP 서브도메인 정규화:
      - 선두 레이블이 m|mobile|amp 인 경우 제거 후 www. 선호
      - news.m.example.com → news.example.com (중간 'm' 레이블 제거)
      - amp.example.com → www.example.com
    """
    # [ADD] 우선 명시 매핑 적용(예외/특정 매체 도메인 보정)
    try:
        mapped = _normalize_host_map(host or "")
        if mapped:
            host = mapped
    except Exception:
        pass
    try:
        h = (host or "").strip().lower()
        if not h or not _mobile_to_www_enabled():
            return h
        labels = [p for p in h.split(".") if p]
        if not labels:
            return h

        def _drop_mobile_label(lbl: str) -> bool:
            return lbl in ("m", "mobile", "amp")

        # 1) 선두 라벨이 모바일/AMP인 경우 제거
        changed = False
        while labels and _drop_mobile_label(labels[0]):
            labels.pop(0); changed = True

        # 2) 두 번째 라벨이 'm' 형태(예: news.m.example.com)면 제거
        if len(labels) >= 3 and _drop_mobile_label(labels[1]):
            labels.pop(1); changed = True

        if not labels:
            return "www"

        # 선호: www. 프리픽스 (옵션)
        if changed and (not labels[0].startswith("www")):
            labels.insert(0, "www")

        return ".".join(labels)
    except Exception:
        return host
from urllib.parse import unquote, quote

# RFC3986 권장: 퍼센트 인코딩을 소문자 hex로 정규화
# 경로는 안전문자 보존하여 재-quote
_SAFE_PATH = "/:@$&()*+=,;-'._~"  # unreserved(-._~) + 필요한 sub-delims + ':' '@' '/' 등

def _percent_normalize_path(path: str) -> str:
    if not path:
        return "/"
    try:
        # 1) 일단 decode (중복 인코딩 방지)
        dec = unquote(path)
        # 2) 다시 quote하여 표준화(소문자 hex)
        norm = quote(dec, safe=_SAFE_PATH)
        # 슬래시는 quote에서 유지됨
        return norm or "/"
    except Exception:
        return path or "/"


def _normalize_url(u: str) -> str:
    try:
        raw = (u or "").strip()
        if not raw:
            return ""
        pu = urlparse(raw)

        # 1) 스킴 기본값 및 소문자화
        scheme = (pu.scheme or "https").lower()

        # 2) 호스트: 소문자 + IDNA 정규화 + 모바일/AMP 제거 + 기본 포트 제거
        host = (pu.netloc or "").strip()
        try:
            host = host.encode("idna").decode("idna")
        except Exception:
            pass
        host = _normalize_mobileish_host(host.lower())
        host = _strip_default_port(host, scheme)

        # 3) 경로: 인덱스/세그먼트/중복슬래시 처리
        path = pu.path or "/"
        path = _collapse_slashes(path)
        path = _normalize_path_segments(path)
        path = _drop_default_index(path)
        # 퍼센트 인코딩 표준화
        path = _percent_normalize_path(path)

        # 4) 쿼리: 추적 파라미터 제거 + AMP 접기 + 정렬
        qs_pairs = parse_qsl(pu.query, keep_blank_values=False)
        # AMP 접기(경로/쿼리 함께)
        path, qs_pairs = _strip_amp_variants(path, qs_pairs)
        qs_pairs = _sort_and_filter_query(qs_pairs)
        query = urlencode(qs_pairs, doseq=True)

        # 5) fragment 제거, 파일 스킴 등 기타 처리
        frag = ""  # 항상 제거

        # 6) 일부 호스트는 www 무시 동치 옵션
        if _URL_TREAT_WWW_EQUIV and host.startswith("www."):
            host = host[4:]

        return urlunparse((scheme, host, path or "/", "", query, frag))
    except Exception:
        return (u or "").strip()


def _dedupe_keep_order_dicts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items or []:
        raw = it.get("url") or it.get("source") or ""
        nu = _normalize_url(raw)
        if not nu:
            continue
        if nu in seen:
            continue
        seen.add(nu)
        # 디버그용 정규화 URL 힌트(다운스트림에서 필요 없으면 제거 가능)
        try:
            it["norm_url"] = nu
        except Exception:
            pass
        out.append(it)
    return out


def _pick_top(items: List[Dict[str, Any]], topn: int) -> List[Dict[str, Any]]:
    return items[: max(1, int(topn or 1))]

# ====== Naver 질의 간소화/스킵 판정 ======
import re as _re

def _simplify_for_naver(q: str) -> str:
    if not q:
        return q
    s = q
    m = _re.search(r"(종근당|벤포벨)", s)
    if m:
        s = s[m.start():]
    s = _re.sub(
        r"\b(overview|summary|key trends|market size|supply chain risks|policy & regulation|Korea)\b",
        lambda m: {
            "overview": "개요", "summary": "요약", "key trends": "주요 동향",
            "market size": "시장 규모", "supply chain risks": "공급망 위험",
            "policy & regulation": "정책 규제", "korea": "한국"
        }.get(m.group(1).lower(), m.group(1)),
        s, flags=_re.I
    )
    s = s.replace("'", " ").replace('"', " ").replace("/", " ").replace("|", " ")
    s = _re.sub(r"\s+", " ", s).strip()

    if _truthy_cfg("NAVER_TRIM_OPERATORS", default=True):
        s = _re.sub(r"site:\S+", " ", s, flags=_re.I)
        s = _re.sub(r"filetype:\S+", " ", s, flags=_re.I)
        s = _re.sub(r"\b(OR|AND|NOT)\b", " ", s, flags=_re.I)
        s = _re.sub(r"[()]", " ", s)
        s = s.replace("..", " ")
        s = _re.sub(r"\b(event|exhibition|tickets)\b", " ", s, flags=_re.I)

    cap = _cfg_int("NAVER_NEGATIVE_CAP", default=0)
    s = _cap_minus_tokens(s, cap)
    s = _re.sub(r"\s+", " ", s).strip()
    if len(s) > 200:
        s = s[:200].rstrip()
    return s

def _should_skip_naver(q: str) -> bool:
    s = _simplify_for_naver(q or "")
    if not s:
        logger.debug("[naver.skip] reason=empty-after-simplify")
        return True
    max_len = _cfg_int("NAVER_MAX_LEN", default=120)
    max_toks = _cfg_int("NAVER_MAX_TOKENS", default=8)
    if len(s) > max_len:
        logger.debug("[naver.skip] reason=too_long len=%d max=%d q=%r", len(s), max_len, s)
        return True
    tokc = len(s.split())
    if tokc > max_toks:
        logger.debug("[naver.skip] reason=too_many_tokens tok=%d max=%d q=%r", tokc, max_toks, s)
        # 완전 차단 대신 약간의 버퍼 허용(운용 튜닝)
        if tokc > (max_toks + 2):
            return True
    bad = [
        r"\b(site:|filetype:|ext:|intitle:|inurl:|cache:)\S*",
        r"[\"{}|\[\]]",
        r"\.\.",
    ]
    for pat in bad:
        if _re.search(pat, s, flags=_re.I):
            logger.debug("[naver.skip] reason=bad_pattern pattern=%r q=%r", pat, s)
            return True
    return False

def _is_naver_safe(q: str) -> bool:
    if not q:
        return False
    if len(q) > 80:
        return False
    toks = q.split()
    if len(toks) > 6:
        return False
    bad = [
        r"\b(site:|filetype:|ext:|intitle:|inurl:|cache:)\S*",
        r"[()\"{}|\[\]]",
        r"\b(AND|OR|NOT)\b",
    ]
    for pat in bad:
        if _re.search(pat, q, flags=_re.I):
            return False
    return True

# =============================================================================
# Common helpers
# =============================================================================

def _strip_minus_tokens(q: str) -> str:
    if not q:
        return q
    return _re.sub(r"(^|\s)-\S+", " ", q).strip()

def _cap_minus_tokens(q: str, cap: int) -> str:
    if not q:
        return q
    if cap <= 0:
        return _strip_minus_tokens(q)
    toks = q.split()
    negs = [t for t in toks if t.startswith("-")]
    if len(negs) <= cap:
        return q
    keep = set(negs[:cap])
    kept = []
    for t in toks:
        if t.startswith("-") and t not in keep:
            continue
        kept.append(t)
    return " ".join(kept).strip()

def _normalize_results(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    norm: List[Dict[str, Any]] = []
    for r in (items or []):
        url = r.get("url") or r.get("source") or r.get("link") or ""
        if not url:
            continue
        # [ADD] title/content가 bytes인 경우 안전 디코딩
        _title = r.get("title")
        if isinstance(_title, (bytes, bytearray)):
            _title = safe_decode(bytes(_title))
        _content = r.get("content") or r.get("snippet")
        if isinstance(_content, (bytes, bytearray)):
            _content = safe_decode(bytes(_content))

        norm.append({
            "title": _normalize_unicode(_title or url),
            "url": url,
            "content": _normalize_unicode(_content or ""),
            "raw_content": r.get("raw_content") or "",
            "source": url,
            "content_type": r.get("content_type") or r.get("mime") or "",
        })
    return norm

def _clean_text(txt: str) -> str:
    if not txt:
        return ""
    txt = _normalize_unicode(txt, form="NFKC", strip_ws=False)
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n\n" in txt or "\t\t\t" in txt:
        txt = txt.replace("\n\n\n", "\n\n").replace("\t\t\t", "\t\t")
    return txt.strip()

def _looks_like_pdf_bytes(txt: str) -> bool:
    return (txt or "").lstrip().startswith("%PDF-")

def _is_block_page(txt: str) -> bool:
    t = (txt or "").lower()
    return any(k in t for k in [
        "access denied", "enable javascript", "just a moment",
        "security controls triggered", "captcha",
    ])

def _looks_like_serialized_blob(txt: str) -> bool:
    t = (txt or "")
    tl = t.lower()
    markers = ["__next_data__", "window.__", "\"$\",\"html\"", "static/chunks/"]
    if any(m in tl for m in markers):
        return True
    brace_ratio = (t.count("{") + t.count("}")) / max(1, len(t))
    return brace_ratio > 0.02

def _append_default_negatives(q: str) -> str:
    if not q or not _truthy_cfg("WEB_APPLY_DEFAULT_NEGATIVES", default=True):
        return q
    min_tok = _cfg_int("WEB_DEFAULT_NEGATIVES_MIN_TOKENS", default=3)
    if min_tok and len(q.split()) < min_tok:
        return q
    if _is_naver_safe(q):
        return q
    base = _cfg_str("WEB_DEFAULT_NEGATIVES", default="-행사 -세미나 -박람회")
    if not base:
        return q
    existing = set(q.split())
    to_add = [tok for tok in base.split() if tok and tok not in existing]
    if not to_add:
        return q
    return (q.rstrip() + " " + " ".join(to_add)).strip()

# ─────────────────────────────────────────────────────────────────────────────
# 게이트키핑 (+ 메트릭)
# ─────────────────────────────────────────────────────────────────────────────
def _apply_gatekeep_to_results(results: list[dict]) -> list[dict]:
    if not results or not gatekeep_enabled():
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
            hosts = []
            for u in blocked:
                try:
                    h = _normalize_host(_normalize_url(u))
                except Exception:
                    h = _normalize_host(u)
                hosts.append(h or u)
            logger.warning("[GATEKEEP] blocked %d url(s): %s", len(blocked), ", ".join(hosts[:10]))
        except Exception:
            logger.warning("[GATEKEEP] blocked %d url(s).", len(blocked))

    # ✅ METRICS
    try:
        event(
            "gatekeep_stats",
            blocked_count=len(blocked),
            allowed_count=len(allowed),
            blocked_rate=(len(blocked) / max(1, len(blocked) + len(allowed)))
        )
    except Exception:
        pass

    return allowed

# ─────────────────────────────────────────────────────────────────────────────
# 원문 로딩: PDF/HTML
# ─────────────────────────────────────────────────────────────────────────────
def _load_web_page(url: str) -> str:
    """원문 HTML을 받아 텍스트로 정리 (스트리밍 + 최대 바이트 예산 + 인코딩 추정)."""
    connect_to = _cfg_int("WEB_FETCH_TIMEOUT_CONNECT", default=6)
    read_to    = _cfg_int("WEB_FETCH_TIMEOUT_READ", default=20)
    max_bytes  = _cfg_int("WEB_FETCH_MAX_BYTES", default=1_000_000)  # 1MB

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

            # 인코딩 추정 비용 최소화 전략: r.encoding → BOM/UTF-8 → chardet(샘플 64KB)
            enc = (r.encoding or "").strip() or None
            if not enc:
                if raw.startswith(b"\xef\xbb\xbf"):
                    enc = "utf-8"
                else:
                    try:
                        sample = raw[:65536]
                        enc = chardet.detect(sample).get("encoding") or "utf-8"
                    except Exception:
                        enc = "utf-8"

            # [CHANGE] 안전 디코더 사용 (UTF-8 우선, 한글(cp949/euc-kr) 폴백)
            text = safe_decode(raw, fallback=enc)

            # 1) 유니코드/BOM/전각→반각/제로폭 제거
            text = _normalize_unicode(text, form="NFKC", strip_ws=False)
            # 2) 과다 공백 축약
            while "\n\n\n" in text or "\t\t\t" in text:
                text = text.replace("\n\n\n", "\n\n").replace("\t\t\t", "\t\t")
            # 3) 표준 개행으로 통일
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            return text.strip()
        
    except Exception as e:
        logger.debug("requests session load failed for %s: %s", url, e)

    # 폴백: LangChain WebBaseLoader
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
        txt = (docs[0].page_content if docs else "")
        txt = _normalize_unicode(txt, form="NFKC", strip_ws=False)
        while "\n\n\n" in txt or "\t\t\t" in txt:
            txt = txt.replace("\n\n\n", "\n\n").replace("\t\t\t", "\t\t")
        txt = txt.replace("\r\n", "\n").replace("\r", "\n")
        return txt.strip()
    except Exception as e:
        logger.debug("WebBaseLoader fallback failed for %s: %s", url, e)
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# 결과 원문 보강 (+ 메트릭)
# ─────────────────────────────────────────────────────────────────────────────
def _enrich_raw_content(results: List[Dict[str, Any]]) -> None:
    """
    상위 N개 결과에 대해 원문을 페치해 raw_content 채우기.
    예산: WEB_SEARCH_RAW_FETCH_TOP / WEB_FETCH_BUDGET_SECONDS
    """
    top = _cfg_int("WEB_SEARCH_RAW_FETCH_TOP", default=5)
    if top <= 0:
        return

    budget_s = _cfg_float("WEB_FETCH_BUDGET_SECONDS", default=30.0)
    per_url_cap = _cfg_float("WEB_FETCH_PER_URL_CAP", default=8.0)  # URL당 최대 N초 캡
    t0 = time.time()

    # ✅ METRICS: 시작
    try:
        event("raw_fetch_start", top=top, budget_seconds=budget_s, candidates=len(results or []))
    except Exception:
        pass

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
            try:
                event("raw_fetch_budget_exceeded", elapsed=round(time.time() - t0, 3), budget_seconds=budget_s)
            except Exception:
                pass
            break

        if r.get("raw_content"):
            continue
        url = r.get("url")
        if not url:
            continue
        try:
            t_url0 = time.time()
            html = _load_web_page(url)
            elapsed = time.time() - t_url0
            if elapsed > per_url_cap:
                logger.debug("per-url cap exceeded (>%ss) — skip remaining processing: %s", per_url_cap, url)
                try:
                    event("raw_fetch_per_url_cap", url=_host_of(url), elapsed=round(elapsed, 3))
                except Exception:
                    pass
                continue

            if html and not _is_bad_doc_text(html[:2000]):
                if _looks_like_serialized_blob(html):
                    logger.debug("serialized blob detected; skip raw_content for %s", url)
                    try:
                        event("raw_fetch_skip_serialized", url=_host_of(url))
                    except Exception:
                        pass
                    continue
                r["raw_content"] = html
                try:
                    event("raw_fetch_ok", url=_host_of(url), bytes=len(html.encode("utf-8")))
                except Exception:
                    pass
        except Exception as e:
            logger.debug("raw_content fetch failed for %s: %s", url, e)
            try:
                event("raw_fetch_fail", url=_host_of(url), err=str(e.__class__.__name__))
            except Exception:
                pass
            continue

# -----------------------------------------------------------------------------
# persist_directory 해석
# -----------------------------------------------------------------------------
def _resolve_persist_dir(namespace: str, persist_directory: Optional[str]) -> str:
    """
    persist_directory가 주어지면 그대로 사용.
    아니면 CHROMA_DIR/ENV/기본(DATA_DIR/chroma_store/<ns>) 규칙으로 경로를 결정.
    """
    if persist_directory is not None:
        s = persist_directory.strip()
        if s:
            return s

    # CFG.CHROMA_DIR 우선 → 기본(DATA_DIR/chroma_store/ns)
    chroma_dir = _cfg_str("CHROMA_DIR", default="")
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

# -----------------------------------------------------------------------------
# 공개 심볼
# -----------------------------------------------------------------------------
__all__ = [
    "session", "http_get",
    "_normalize_unicode",
    "PROJECT_ROOT", "DATA_DIR",
    "_now", "_now_iso", "refresh_runtime_config",
    "_save_results",
    "_ell", "_host_of",
    "_normalize_url", "_dedupe_keep_order_dicts", "_pick_top",
    "_simplify_for_naver", "_should_skip_naver", "_is_naver_safe",
    "_strip_minus_tokens", "_cap_minus_tokens",
    "_normalize_results", "_clean_text",
    "_looks_like_pdf_bytes", "_is_block_page", "_looks_like_serialized_blob",
    "_append_default_negatives",
    "_apply_gatekeep_to_results",
    "_load_web_page", "_enrich_raw_content",
    "_resolve_persist_dir",
    "_RECENTLY_CLEARED", "_FRESH_KEYS",
]
