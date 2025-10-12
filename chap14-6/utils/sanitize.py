# utils/sanitize.py
from __future__ import annotations
from typing import Any, Mapping, MutableMapping, overload, TYPE_CHECKING, cast, Dict

import logging
logger = logging.getLogger(__name__)

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
    """안전하게 int로 변환. None/불리언/공백문자열 등은 default.
    - "1,234" / "1_234" 구분자 허용
    - NaN/Inf/∞ 등 비정상 표기는 default
    """
    try:
        if v is None or isinstance(v, bool):
            return default
        if isinstance(v, (int,)):
            return int(v)
        if isinstance(v, (float,)):
            # NaN/Inf 방지
            if v != v or v in (float("inf"), float("-inf")):
                return default
            return int(v)
        if isinstance(v, (bytes, bytearray)):
            s = v.decode("utf-8", "ignore")
        elif isinstance(v, str):
            s = v
        else:
            # 기타 타입은 문자열로 한 번 시도
            s = str(v)

        s = s.strip()
        if not s:
            return default

        # 비정상 표기 빠르게 차단
        low = s.lower()
        if "nan" in low or "inf" in low or "infinity" in low or "∞" in low:
            return default

        # 구분자 제거 (1,234 / 1_234)
        s = s.replace(",", "").replace("_", "")

        # float 캐스팅 허용(3e2, 3.0 등)
        return int(float(s))
    except Exception:
        return default


def as_int(state: Mapping[str, Any], key: str, default: int = 0) -> int:
    """state[key]를 안전하게 int로."""
    return coerce_int(state.get(key), default)

# ─────────────────────────────────────────────────────────────────────────────
# 제일 깔끔한 방법: generic 함수의 오버로드 제거 + 구현에서 분기로 반환형 확정
# ─────────────────────────────────────────────────────────────────────────────
def sanitize_numeric_state_generic(st: Any) -> Any:
    """
    _NUMERIC_KEYS만 정규화하여 int로 맞춘다.
    - MutableMapping이면 제자리(in-place) 변환 후 동일 객체 반환
    - 불변 Mapping이면 dict 복사본에 반영해 반환
    - 그 외 타입은 dict로 변환 시도 후 반환
    """
    if st is None:
        st = {}

    changed = 0

    if isinstance(st, MutableMapping):
        mm: MutableMapping[str, Any] = st
        for k in _NUMERIC_KEYS:
            if k not in mm:
                continue
            v = mm[k]
            if v is None or isinstance(v, bool):
                continue
            new_v = coerce_int(v, 0)
            if new_v != v:
                changed += 1
                mm[k] = new_v
        if changed:
            logger.debug("sanitize_numeric_state_generic: coerced %d fields (in-place)", changed)
        return mm  # 그대로 반환

    if isinstance(st, Mapping):
        mm2: Dict[str, Any] = dict(st)  # 불변 Mapping은 dict 복사
        for k in _NUMERIC_KEYS:
            if k not in mm2:
                continue
            v = mm2[k]
            if v is None or isinstance(v, bool):
                continue
            new_v = coerce_int(v, 0)
            if new_v != v:
                changed += 1
                mm2[k] = new_v
        if changed:
            logger.debug("sanitize_numeric_state_generic: coerced %d fields (copied)", changed)
        return mm2  # dict 반환

    # 그 외 타입
    mm3: Dict[str, Any] = dict(st) if hasattr(st, "items") else {}
    for k in _NUMERIC_KEYS:
        if k not in mm3:
            continue
        v = mm3[k]
        if v is None or isinstance(v, bool):
            continue
        new_v = coerce_int(v, 0)
        if new_v != v:
            changed += 1
            mm3[k] = new_v
    if changed:
        logger.debug("sanitize_numeric_state_generic: coerced %d fields (coerced to dict)", changed)
    return mm3

@overload
def sanitize_state(st: "State") -> "State": ...
@overload
def sanitize_state(st: MutableMapping[str, Any]) -> MutableMapping[str, Any]: ...
@overload
def sanitize_state(st: Mapping[str, Any]) -> Dict[str, Any]: ...

def sanitize_state(st: Any) -> Any:
    """
    숫자 필드만 정규화 후 동일 객체(가능하면 in-place) 또는 복사본을 반환.
    - State/MutableMapping: in-place 정규화 후 원본 반환
    - Mapping: dict(st) 복사본을 만들어 정규화 후 반환
    """
    if isinstance(st, MutableMapping):            # State도 보통 여기에 해당 (TypedDict는 런타임엔 dict)
        sanitize_numeric_state_generic(st)        # in-place
        return st                                 # 원본 그대로 (State | MutableMapping)
    if isinstance(st, Mapping):
        return sanitize_numeric_state_generic(dict(st))  # 항상 dict로 강제
    return sanitize_numeric_state_generic(st)     # 기타 타입

def sanitize_state_copy(st: Mapping[str, Any] | None) -> dict[str, Any]:
    """원본을 보존하고 싶은 경우 사용: 항상 dict 복사본을 반환."""
    base = dict(st or {})
    return sanitize_numeric_state_generic(base)