# utils/state_sanitize.py
import math
from typing import Any, Optional

def coerce_int(v: Any, default: int = 0, none_ok: bool = False) -> Optional[int]:
    """값을 안전하게 int로 변환. None 처리, 문자열/float도 대응."""
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
            # "3", "3.0", "  4  " 모두 허용
            return int(float(s))
        except Exception:
            return default
    # 기타 타입
    try:
        return int(v)
    except Exception:
        return default


def as_int(state: dict, key: str, default: int = 0, none_ok: bool = False) -> Optional[int]:
    """state 딕셔너리에서 key를 안전하게 int로 꺼냄."""
    return coerce_int(state.get(key), default=default, none_ok=none_ok)


def sanitize_numeric_state(state: dict) -> dict:
    """state에 자주 쓰는 숫자 키들을 일괄 보정."""
    state["research_round"]  = as_int(state, "research_round", 0)
    state["iteration_count"] = as_int(state, "iteration_count", 1)
    # new_url_count는 None을 의미 있게 쓸 수도 있으면 none_ok=True
    state["new_url_count"]   = as_int(state, "new_url_count", 0, none_ok=True)
    return state