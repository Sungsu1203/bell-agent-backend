# utils/ref_format.py
from __future__ import annotations
from urllib.parse import urlparse, unquote, parse_qs
from pathlib import PurePosixPath  # noqa: F401  # (미래 확장 대비)
import os

_PROJECT_ROOT = os.getenv("PROJECT_ROOT", "").strip().rstrip("\\/")

def _shorten(text: str, max_len: int = 96) -> str:
    if len(text) <= max_len:
        return text
    head = max_len - 10
    return text[:head].rstrip() + " … " + text[-9:]

def _posix_to_windows(path: str) -> str:
    # urlparse(file:///D:/path) -> path="/D:/path"
    if path.startswith("/"):
        path = path[1:]
    return os.path.normpath(path)

def _relativize(path: str) -> str:
    if _PROJECT_ROOT:
        try:
            pr_low = _PROJECT_ROOT.lower()
            p_low = path.lower()
            if p_low.startswith(pr_low):
                return os.path.relpath(path, _PROJECT_ROOT)
        except Exception:
            pass
    return path

def format_ref_for_log(raw_url: str) -> tuple[str, str]:
    """
    (title_line, link_line) 반환.
    - file:// 로컬: 퍼센트 디코드 + Windows 경로 + fragment/query 요약
    - 웹 URL: host / 마지막 2~3 세그먼트로 축약
    """
    try:
        u = urlparse(raw_url or "")
        if u.scheme == "file":
            decoded_path = unquote(u.path or "")
            win_path = _relativize(_posix_to_windows(decoded_path))
            title = os.path.basename(win_path) or win_path

            frag = u.fragment or ""
            qs = parse_qs(u.query or "")
            parts = []
            if frag:
                parts.append(frag)
            for k, v in qs.items():
                parts.append(f"{k}={','.join(v)}")
            suffix = f"  [{'; '.join(parts)}]" if parts else ""
            title_line = f"{title}{suffix}"
            link_line = win_path
            return _shorten(title_line), _shorten(link_line)

        # 웹 URL
        host = (u.netloc or "").lower()
        path = unquote(u.path or "/").strip("/")
        segs = [s for s in path.split("/") if s]
        pretty_path = "/".join(segs[-3:]) if len(segs) > 3 else (path or "/")
        name = segs[-1] if segs else host or "/"
        title_line = name
        link_line = f"{host} / {pretty_path or '/'}"
        return _shorten(title_line), _shorten(link_line)
    except Exception:
        dec = unquote(raw_url or "")
        return _shorten(dec), _shorten(dec)
