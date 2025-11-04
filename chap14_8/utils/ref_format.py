# utils/ref_format.py — dynamic config access (v2025-10-27)
from __future__ import annotations
from urllib.parse import urlparse, unquote, parse_qs
from pathlib import Path
import os
import re
from typing import Iterable, Optional, Set, List, Dict

# ─────────────────────────────────────────────────────────────
# Dynamic config access (avoid static binding at import)
# ─────────────────────────────────────────────────────────────
import core.config as config

# Helpers to read from config.CFG first, then module-level fallbacks

def _get_cfg_attr(name: str, default):
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default


def _as_set(v: Optional[Iterable[str]]) -> Set[str]:
    if not v:
        return set()
    try:
        return {str(x).strip() for x in v if str(x).strip()}
    except Exception:
        return set()

# ─────────────────────────────────────────────────────────────
# Per-call dynamic getters (reload_config() 즉시 반영)
# ─────────────────────────────────────────────────────────────
def _project_root() -> str:
    val = str(_get_cfg_attr("PROJECT_ROOT", os.getenv("PROJECT_ROOT", "")) or "")
    return val.strip().rstrip("\\/")

def _tracking_params() -> Set[str]:
    default = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "gclid", "fbclid", "igshid", "igsh", "mc_cid", "mc_eid",
    }
    return _as_set(_get_cfg_attr("REF_TRACKING_PARAMS", default))

def _title_max_len() -> int:
    try:
        return int(_get_cfg_attr("REF_TITLE_MAX_LEN", 96) or 96)
    except Exception:
        return 96

def _link_max_len() -> int:
    try:
        return int(_get_cfg_attr("REF_LINK_MAX_LEN", 96) or 96)
    except Exception:
        return 96

def _path_tail_segments() -> int:
    # 마지막 몇 개의 path 세그먼트를 표시할지 (2~3 권장)
    try:
        n = int(_get_cfg_attr("REF_TAIL_SEGMENTS", 3) or 3)
        return 3 if n < 1 else n
    except Exception:
        return 3

def _strip_www() -> bool:
    try:
        return bool(_get_cfg_attr("REF_STRIP_WWW", True))
    except Exception:
        return True


def _shorten(text: str, max_len: Optional[int] = None) -> str:
    if not text:
        return ""
    if max_len is None:
        max_len = 96
    if len(text) <= max_len:
        return text
    head = max_len - 10
    return text[:head].rstrip() + " … " + text[-9:]


def _posix_to_windows(path: str) -> str:
    r"""
    file:///D:/path/to/file → D:\\path\\to\\file
    file:////server/share/file → \\server\\share\\file (UNC)
    """
    if not path:
        return path
    # UNC (file:////server/share/...)
    if path.startswith("//"):
        return os.path.normpath("\\" + path.lstrip("/"))
    # 일반 드라이브 (urlparse(path).path = "/D:/...")
    if path.startswith("/"):
        path = path[1:]
    return os.path.normpath(path)


def _relativize(path: str) -> str:
    if not path:
        return path
    pr = _project_root()
    if pr:
        try:
            # Windows 대소문자 무시 경로 대비
            pr_low = os.path.normcase(pr)
            p_low = os.path.normcase(path)
            if p_low.startswith(pr_low):
                return os.path.relpath(path, pr)
        except Exception:
            pass
    return path


def _strip_tracking_qs(q: str) -> Dict[str, List[str]]:
    try:
        qs = parse_qs(q or "")
    except Exception:
        return {}
    if not qs:
        return {}
    # 추적 파라미터 제거 (동적 목록 사용)
    tparams = {p.lower() for p in _tracking_params()}
    clean = {k: v for k, v in qs.items() if k.lower() not in tparams}
    return clean


def _looks_like_local_path(s: str) -> bool:
    """스킴이 없어도 로컬 경로처럼 보이는 경우 처리."""
    if not s:
        return False
    s = s.strip()
    # 드라이브 레터 시작 (C:\\ or C:/)
    if re.match(r"^[a-zA-Z]:[\\/]", s):
        return True
    # 상대/절대 경로 형태(./, ../, /, \\)
    if s.startswith((".", "/", "\\")) or s.startswith(".."):
        return True
    return False


def _basename_or(s: str, fallback: str) -> str:
    try:
        base = os.path.basename(s)
        return base or fallback
    except Exception:
        return fallback


def format_ref_for_log(raw_url: str) -> tuple[str, str]:
    """
    (title_line, link_line) 반환.
    - file:// 로컬: 퍼센트 디코드 + Windows/UNC 경로 + fragment/query 요약
    - 웹 URL: host / 마지막 2~3 세그먼트로 축약 (추적 쿼리 제거)
    - 스킴 없는 로컬 경로도 지원
    - 실패 시 입력 문자열을 짧게 잘라 반환
    """
    try:
        raw = (raw_url or "").strip()
        if not raw:
            return ("", "")

        # 스킴이 없고 로컬 경로처럼 보이면 로컬로 처리
        if "://" not in raw and _looks_like_local_path(raw):
            abs_path = os.path.abspath(raw)
            rel = _relativize(abs_path)
            title = _basename_or(rel, rel)
            return _shorten(title), _shorten(rel)

        u = urlparse(raw)

        # ── file:// 로컬
        if u.scheme == "file":
            # 다양한 변형(file://host/path, file:///D:/path)을 모두 수용
            # urlparse 규칙상 host가 들어오는 경우 u.netloc 사용
            host = u.netloc or ""
            decoded_path = unquote(u.path or "")
            if host and not decoded_path.startswith("//"):
                # UNC: file://server/share/path  → //server/share/path
                decoded_path = f"//{host}{('/' + decoded_path.lstrip('/')) if decoded_path else ''}"
            win_path = _relativize(_posix_to_windows(decoded_path))

            # 제목과 부가정보(fragment/중요한 쿼리만)
            frag = u.fragment or ""
            qs = _strip_tracking_qs(u.query or "")
            parts: list[str] = []
            if frag:
                parts.append(f"#{frag}")
            # 쿼리는 'k=v1,v2' 요약 (tracking 파라미터는 이미 제거)
            for k, v in qs.items():
                parts.append(f"{k}={','.join(v)}")
            suffix = f"  [{' ; '.join(parts)}]" if parts else ""
            title = _basename_or(win_path, win_path) + suffix
            return _shorten(title, _title_max_len()), _shorten(win_path, _link_max_len())

        # ── 웹 URL
        # 스킴 누락 시에도 urlparse는 netloc이 비니까, host 인식 실패할 수 있다.
        # 이 경우 'example.com/path' 같은 입력을 보완
        if not u.scheme and not u.netloc and not raw.startswith("/"):
            u = urlparse("http://" + raw)

        host = (u.netloc or "").lower()
        if _strip_www() and host.startswith("www."):
            host = host[4:]
        path = unquote(u.path or "/").strip("/")

        # 추적 쿼리를 제거한 요약을 만들되, 로그에서는 경로 중심으로만 표시
        _ = _strip_tracking_qs(u.query or "")  # 현재 링크 라인엔 사용하지 않지만 추후 확장을 위해 남김

        segs = [s for s in path.split("/") if s]
        # 마지막 N 세그먼트만 표시 (CFG: REF_TAIL_SEGMENTS)
        n_tail = _path_tail_segments()
        if len(segs) >= n_tail:
            pretty_path = "/".join(segs[-n_tail:])
        elif len(segs) > 0:
            pretty_path = "/".join(segs)
        else:
            pretty_path = "/"

        name = segs[-1] if segs else (host or "/")
        title_line = name or "/"
        link_line = f"{host} / {pretty_path or '/'}"
        return _shorten(title_line, _title_max_len()), _shorten(link_line, _link_max_len())

    except Exception:
        # 완전 실패 시: 퍼센트 디코드 후 동일 문자열 반환
        dec = unquote(raw_url or "")
        s = _shorten(dec, _title_max_len())
        return s, s

# ─────────────────────────────────────────────────────────────
# (옵션) 캐시 무효화 훅 — 현재 구현은 per-call 조회이므로 no-op
# ─────────────────────────────────────────────────────────────
def refresh_ref_format() -> None:  # pragma: no cover
    """향후 최적화로 캐시 도입 시 cache_clear()를 연결하기 위한 훅.
    현재 버전은 per-call 조회로 즉시 반영되므로 동작 없음."""
    return