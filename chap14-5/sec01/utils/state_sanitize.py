# utils/state_sanitize.py
from typing import Any, Mapping, TypeVar, Dict, cast, Optional, overload

try:
    # Python 3.11+
    from typing import Literal
except ImportError:
    # 3.10 이하면 typing_extensions에서 가져오기
    from typing_extensions import Literal
import math

TState = TypeVar("TState", bound=Mapping[str, Any])

# --- coerce_int overloads ---
@overload
def coerce_int(v: Any, default: int = 0, *, none_ok: Literal[False] = False) -> int: ...
@overload
def coerce_int(v: Any, default: int = 0, *, none_ok: Literal[True]) -> Optional[int]: ...

def coerce_int(v: Any, default: int = 0, *, none_ok: bool = False):
    if v is None:
        return None if none_ok else default
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return default
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return default
        try:
            return int(float(s))
        except Exception:
            return default
    try:
        return int(v)
    except Exception:
        return default

# --- as_int overloads ---
@overload
def as_int(state: Mapping[str, Any], key: str, default: int = 0, *, none_ok: Literal[False] = False) -> int: ...
@overload
def as_int(state: Mapping[str, Any], key: str, default: int = 0, *, none_ok: Literal[True]) -> Optional[int]: ...

def as_int(state: Mapping[str, Any], key: str, default: int = 0, *, none_ok: bool = False):
    return coerce_int(state.get(key), default=default, none_ok=none_ok)


# def coerce_int(v: Any, default: int = 0, none_ok: bool = False):
#     if v is None:
#         return None if none_ok else default
#     if isinstance(v, bool):
#         return int(v)
#     if isinstance(v, int):
#         return v
#     if isinstance(v, float):
#         if math.isnan(v) or math.isinf(v):
#             return default
#         return int(v)
#     if isinstance(v, str):
#         s = v.strip()
#         if not s:
#             return default
#         try:
#             return int(float(s))
#         except Exception:
#             return default
#     try:
#         return int(v)
#     except Exception:
#         return default

# def as_int(state: Mapping[str, Any], key: str, default: int = 0, none_ok: bool = False):
#     return coerce_int(state.get(key), default=default, none_ok=none_ok)

# 기존: 새 dict 반환 (원한다면 유지)
def sanitize_numeric_state(state: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(state)
    out["research_round"]  = as_int(state, "research_round", 0)
    out["iteration_count"] = as_int(state, "iteration_count", 1)
    out["new_url_count"]   = as_int(state, "new_url_count", 0, none_ok=True)
    return out

def sanitize_numeric_state_generic(state: TState) -> TState:
    out: Dict[str, Any] = dict(state)
    out["research_round"]  = as_int(state, "research_round", 0)
    out["iteration_count"] = as_int(state, "iteration_count", 1)
    out["new_url_count"]   = as_int(state, "new_url_count", 0, none_ok=True)
    out["round_added_urls"]    = as_int(state, "round_added_urls", 0, none_ok=True)
    out["new_url_count_round"] = as_int(state, "new_url_count_round", 0, none_ok=True)
    out["round_new_urls"]      = as_int(state, "round_new_urls", 0, none_ok=True)
    out["flags"] = dict(state.get("flags") or {})
    out["local_ingested_once"] = bool(state.get("local_ingested_once"))
    return cast(TState, out)