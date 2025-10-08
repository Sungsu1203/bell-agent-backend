# utils/sanitize.py
from __future__ import annotations
from typing import Any, Mapping, MutableMapping, overload, TYPE_CHECKING, cast

if TYPE_CHECKING:
    # TypedDict(State)를 타입체커 전용으로 참조 (런타임 임포트 없음)
    from core.state_types import State

# 숫자 정규화 대상 키
_NUMERIC_KEYS = {
    "iteration_count", "research_round", "no_new_url_streak", "round_added_urls",
    "new_url_count", "new_url_count_round", "round_new_urls",
    "research_halt_threshold", "research_min_rounds", "research_max_no_new_rounds",
}

def coerce_int(v: object, default: int = 0) -> int:
    """안전하게 int로 변환. None/불리언/공백문자열 등은 default."""
    try:
        if v is None or isinstance(v, bool):
            return default
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, (bytes, bytearray)):
            s = v.decode("utf-8", "ignore").strip()
            return int(float(s)) if s else default
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return default
            # "3.0" 같은 문자열도 허용
            return int(float(s))
        return default
    except Exception:
        return default

def as_int(state: Mapping[str, Any], key: str, default: int = 0) -> int:
    """state[key]를 안전하게 int로."""
    return coerce_int(state.get(key), default)

# --- 오버로드 시그니처 -----------------------------------------------------

@overload
def sanitize_numeric_state_generic(st: "State") -> "State": ...
@overload
def sanitize_numeric_state_generic(st: MutableMapping[str, Any]) -> MutableMapping[str, Any]: ...

def sanitize_numeric_state_generic(st: Any):
    """
    _NUMERIC_KEYS만 in-place로 정규화하여 int로 맞춘다.
    - None/불리언은 의미가 있을 수 있어 그대로 둠
    - str/float 등은 안전 캐스팅(coerce_int)
    """
    if st is None:
        st = {}
    mm = cast(MutableMapping[str, Any], st)
    for k in _NUMERIC_KEYS:
        if k not in mm:
            continue
        v = mm[k]
        if v is None or isinstance(v, bool):
            continue
        mm[k] = coerce_int(v, 0)
    # 오버로드 시그니처 유지 위해 Any로 캐스팅 반환
    return cast(Any, mm)

@overload
def sanitize_state(st: "State") -> "State": ...
@overload
def sanitize_state(st: MutableMapping[str, Any]) -> MutableMapping[str, Any]: ...

def sanitize_state(st: Any):
    """숫자 필드만 정규화(in-place) 후 동일 객체를 반환."""
    return sanitize_numeric_state_generic(st)
