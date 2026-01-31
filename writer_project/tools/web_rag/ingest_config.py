# b/tools/web_rag/ingest_config.py
from __future__ import annotations

import logging
import os
from typing import Optional, Any, Callable as _TypingCallable

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Runtime config (CFG) + reload_config 재노출
# ─────────────────────────────────────────────────────────────
from core.config import CFG  # 실제 CFG 객체
from core.config import reload_config as reload_config  # in-place 갱신


# ─────────────────────────────────────────────────────────────
# 환경 기반 기본값(없으면 안전한 디폴트)
#  - requests 타임아웃
#  - 공통 User-Agent
# ─────────────────────────────────────────────────────────────
_REQ_CONN_TIMEOUT: float = float(os.getenv("REQUESTS_CONNECT_TIMEOUT", "5"))
_REQ_READ_TIMEOUT: float = float(os.getenv("REQUESTS_READ_TIMEOUT", "20"))

# 통일된 UA (yakup 등 일부 사이트에서 헤더 파서 문제 완화)
_UA: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)


# ─────────────────────────────────────────────────────────────
# CFG helpers (ENV 직접 접근 금지)
# ─────────────────────────────────────────────────────────────
def _cfg_str(key: str, default: str = "") -> str:
    try:
        v = getattr(CFG, key)
        return str(v).strip() if v is not None else default
    except Exception:
        return default


def _cfg_bool(key: str, default: bool = False) -> bool:
    try:
        v = getattr(CFG, key)
        return bool(v)
    except Exception:
        return default


def _cfg_int(key: str, default: int) -> int:
    try:
        v = getattr(CFG, key)
        if v is None or v == "":
            return default
        return int(str(v).strip())
    except Exception:
        return default


# ─────────────────────────────────────────────────────────────
# Metrics (optional) — tools.metrics.record_chunks 안전 래퍼
# ─────────────────────────────────────────────────────────────
_record_chunks: Optional[_TypingCallable[..., Any]]
try:
    from tools.metrics import record_chunks as _record_chunks
except Exception:  # pragma: no cover
    _record_chunks = None


def record_chunks(*, chars_sum: int, chunks_cnt: int, ns: str = "", part: str = "") -> None:
    """환경별 metrics.record_chunks 시그니처 차이를 흡수하는 안전 래퍼."""
    try:
        if _record_chunks is None:
            return
        try:
            import inspect

            params = set(inspect.signature(_record_chunks).parameters.keys())
        except Exception:
            params = {"chars_sum", "chunks_cnt"}  # 최소 호환
        payload: dict[str, Any] = {"chars_sum": chars_sum, "chunks_cnt": chunks_cnt}
        if "ns" in params:
            payload["ns"] = ns
        if "part" in params:
            payload["part"] = part
        _record_chunks(**payload)
    except Exception:
        # metrics 실패는 전체 플로우에 영향 주지 않음
        pass


__all__ = [
    "CFG",
    "reload_config",
    "_cfg_str",
    "_cfg_bool",
    "_cfg_int",
    "_REQ_CONN_TIMEOUT",
    "_REQ_READ_TIMEOUT",
    "_UA",
    "record_chunks",
]
