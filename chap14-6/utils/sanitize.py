from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from core.state_types import State  # 타입체크 전용

# 프로젝트에서 숫자 캐스팅 대상 키만 모아둔 집합
_NUMERIC_KEYS = {
    "iteration_count","research_round","no_new_url_streak","round_added_urls",
    "new_url_count","new_url_count_round","round_new_urls",
    "research_halt_threshold","research_min_rounds","research_max_no_new_rounds",
}

def sanitize_numeric_state_generic(st: "State | Dict[str, Any]") -> "State | Dict[str, Any]":
    if st is None:
        st = cast(Dict[str, Any], {})
    for k in _NUMERIC_KEYS:
        if k not in st:
            continue
        v = st[k]  # type: ignore[index]
        try:
            if v is None or isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                st[k] = int(v)  # type: ignore[index]
            elif isinstance(v, str) and v.strip():
                st[k] = int(v.strip())  # type: ignore[index]
        except Exception:
            pass
    return st

# ★ 추가: 정확히 State -> State 로 보장해주는 얇은 래퍼
def sanitize_state(st: "State") -> "State":
    sanitize_numeric_state_generic(st)  # in-place 보정
    return st

def as_int(state: "State | Dict[str, Any]", key: str, default: int = 0) -> int:
    try:
        v = state.get(key, default)  # type: ignore[attr-defined]
        if v is None:
            return default
        return int(v)
    except Exception:
        return default

def coerce_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default
