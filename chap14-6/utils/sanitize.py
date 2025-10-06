# from __future__ import annotations
# from typing import Any, Dict, TYPE_CHECKING, cast

# if TYPE_CHECKING:
#     from core.state_types import State  # 타입체크 전용

# # 프로젝트에서 숫자 캐스팅 대상 키만 모아둔 집합
# _NUMERIC_KEYS = {
#     "iteration_count","research_round","no_new_url_streak","round_added_urls",
#     "new_url_count","new_url_count_round","round_new_urls",
#     "research_halt_threshold","research_min_rounds","research_max_no_new_rounds",
# }

# def sanitize_numeric_state_generic(st: "State | Dict[str, Any]") -> "State | Dict[str, Any]":
#     if st is None:
#         st = cast(Dict[str, Any], {})
#     for k in _NUMERIC_KEYS:
#         if k not in st:
#             continue
#         v = st[k]  # type: ignore[index]
#         try:
#             if v is None or isinstance(v, bool):
#                 continue
#             if isinstance(v, (int, float)):
#                 st[k] = int(v)  # type: ignore[index]
#             elif isinstance(v, str) and v.strip():
#                 st[k] = int(v.strip())  # type: ignore[index]
#         except Exception:
#             pass
#     return st

# # ★ 추가: 정확히 State -> State 로 보장해주는 얇은 래퍼
# def sanitize_state(st: "State") -> "State":
#     sanitize_numeric_state_generic(st)  # in-place 보정
#     return st

# def as_int(state: "State | Dict[str, Any]", key: str, default: int = 0) -> int:
#     try:
#         v = state.get(key, default)  # type: ignore[attr-defined]
#         if v is None:
#             return default
#         return int(v)
#     except Exception:
#         return default

# def coerce_int(v, default: int = 0) -> int:
#     try:
#         return int(v)
#     except Exception:
#         return default


from __future__ import annotations
from typing import Any, Dict, Mapping, Optional, TYPE_CHECKING, overload, cast
import math

if TYPE_CHECKING:
    # 타입체커 전용 (런타임 의존성 없음)
    from core.state_types import State

# 숫자 보정 대상 키
_NUMERIC_KEYS = {
    "iteration_count", "research_round", "no_new_url_streak",
    "round_added_urls", "new_url_count", "new_url_count_round", "round_new_urls",
    "research_halt_threshold", "research_min_rounds", "research_max_no_new_rounds",
}

# 내부 헬퍼: 다양한 타입을 안전하게 int로
def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            # "3.0" 같은 문자열도 허용
            return int(float(s))
        except Exception:
            return None
    try:
        return int(v)
    except Exception:
        return None

def _coerce_numeric_fields_in_place(d: Dict[str, Any]) -> None:
    for k in _NUMERIC_KEYS:
        if k in d:
            n = _to_int(d[k])
            if n is not None:
                d[k] = n

# ── 오버로드: 입력이 State면 반환도 State, dict면 dict ──────────────────
@overload
def sanitize_numeric_state_generic(st: "State") -> "State": ...
@overload
def sanitize_numeric_state_generic(st: Dict[str, Any]) -> Dict[str, Any]: ...
def sanitize_numeric_state_generic(st):  # type: ignore[overload-overlap]
    """
    문자열/None 등으로 들어온 숫자 후보 필드를 제자리(in-place)에서 int로 보정.
    - 입력이 State 타입이면 반환도 State로 정적으로 보장(오버로드)
    - dict를 넣으면 dict로 돌아옴
    """
    if st is None:
        d: Dict[str, Any] = {}
        _coerce_numeric_fields_in_place(d)
        return cast(Any, d)

    # TypedDict도 런타임에 dict처럼 동작하므로 캐스트 후 in-place 수정
    d = cast(Dict[str, Any], st)
    _coerce_numeric_fields_in_place(d)
    return st

# State 전용 얇은 래퍼 (원하면 호출부에서 이걸 쓰면 더 명확)
def sanitize_state(st: "State") -> "State":
    return sanitize_numeric_state_generic(st)

# ── as_int / coerce_int (타입 안전) ─────────────────────────────
@overload
def as_int(state: Mapping[str, Any], key: str, default: int = 0, *, none_ok: bool) -> Optional[int]: ...
@overload
def as_int(state: Mapping[str, Any], key: str, default: int = 0, *, none_ok: bool = False) -> int: ...
def as_int(state: Mapping[str, Any], key: str, default: int = 0, *, none_ok: bool = False):
    v = state.get(key, None)
    n = _to_int(v)
    if n is None:
        return None if none_ok else default
    return n

def coerce_int(v: Any, default: int = 0) -> int:
    n = _to_int(v)
    return default if n is None else n
