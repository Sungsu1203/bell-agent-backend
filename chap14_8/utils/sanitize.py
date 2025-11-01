# utils/sanitize.py — dynamic config access (v2025-10-27)
from __future__ import annotations
from typing import Any, Mapping, MutableMapping, overload, TYPE_CHECKING, Dict, Iterable, cast

import re

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config access (CFG → module attr → default)
# ─────────────────────────────────────────────────────────────
import core.config as config

def _get_cfg_attr(name: str, default):
    """config.CFG.<name> → config.<name> → default."""
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default


def _as_set(v: Iterable[str] | None) -> set[str]:
    if not v:
        return set()
    try:
        return {str(x).strip() for x in v if str(x).strip()}
    except Exception:
        return set()

# ── Type alias for State (tooling-friendly) ──────────────────────────────────
# 타입체커 환경에선 실제 State를 사용하고, 런타임/비타입체커 환경에선
# 넓은 MutableMapping[str, Any]로 대체하여 "unknown import symbol"을 방지.
if TYPE_CHECKING:
    from core.state_types import State as StateT  # typed
else:
    # 런타임/비타입체커용 관대한 별칭
    from typing import MutableMapping as StateT  # type: ignore[assignment]

__all__ = [
    "coerce_int",
    "as_int",
    "as_bool",                  # [ADD]
    "sanitize_numeric_state_generic",
    "sanitize_state",
    "sanitize_state_copy",
]

# ─────────────────────────────────────────────────────────────
# Configurable knobs (runtime)
# ─────────────────────────────────────────────────────────────
_DEFAULT_NUMERIC_KEYS = {
    "iteration_count", "research_round", "no_new_url_streak", "round_added_urls",
    "new_url_count", "new_url_count_round", "round_new_urls",
    "research_halt_threshold", "research_min_rounds", "research_max_no_new_rounds",
}
_NUMERIC_KEYS = _as_set(_get_cfg_attr("NUMERIC_STATE_KEYS", None)) or _DEFAULT_NUMERIC_KEYS

# coerce_int 동작 튜닝(필요시 CFG에서 덮어쓰기)
_COERCE_ALLOW_FLOAT: bool = bool(_get_cfg_attr("COERCE_INT_ALLOW_FLOAT", True))
_COERCE_ALLOW_SCI: bool = bool(_get_cfg_attr("COERCE_INT_ALLOW_SCI", True))  # 3e2
_COERCE_STRIP_SEPARATORS: bool = bool(_get_cfg_attr("COERCE_INT_STRIP_SEPARATORS", True))  # 1,234 / 1_234
_COERCE_ON_NAN_INF_DEFAULT: int = int(_get_cfg_attr("COERCE_INT_NAN_INF_DEFAULT", 0))

# 불리언 플래그 키(기본 + CFG로 오버라이드 가능)
_DEFAULT_BOOL_FLAG_KEYS = {
    "AUTO_WRITE_AFTER_RAG",
    "AUTO_WRITE_DURING_RESEARCH",
    "REQUIRE_EXPLICIT_WRITE_TITLE",
    "ALLOW_LOCAL_SUMMARY",
    "RAG_FIRST",
}
_BOOL_FLAG_KEYS = _as_set(_get_cfg_attr("BOOL_STATE_FLAG_KEYS", None)) or _DEFAULT_BOOL_FLAG_KEYS


# ─────────────────────────────────────────────────────────────
# 숫자 유틸
# ─────────────────────────────────────────────────────────────

def coerce_int(v: object, default: int = 0) -> int:
    """안전하게 int로 변환. None/불리언/공백문자열 등은 default.
    - "1,234" / "1_234" 구분자 허용(설정)
    - NaN/Inf/∞ 등 비정상 표기는 default
    - 지수 표기(3e2) 허용 여부 설정
    """
    try:
        if v is None or isinstance(v, bool):
            return default
        if isinstance(v, int):
            return int(v)
        if isinstance(v, float):
            # NaN/Inf 방지
            if v != v or v in (float("inf"), float("-inf")):
                return _COERCE_ON_NAN_INF_DEFAULT if default == 0 else default
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
            return _COERCE_ON_NAN_INF_DEFAULT if default == 0 else default

        if _COERCE_STRIP_SEPARATORS:
            # 구분자 제거 (1,234 / 1_234)
            s = s.replace(",", "").replace("_", "")

        if not _COERCE_ALLOW_FLOAT and not _COERCE_ALLOW_SCI:
            # 순수 정수만 허용
            m = re.match(r"^[+-]?\d+$", s)
            return int(m.group(0)) if m else default

        # float 캐스팅 허용(3e2, 3.0 등)
        return int(float(s))
    except Exception:
        return default
    
def as_int(state: Mapping[str, Any], key: str, default: int = 0) -> int:
    """state[key]를 안전하게 int로."""
    return coerce_int(state.get(key), default)
    
def as_bool(v: object) -> bool:
    """관대한 불리언 캐스팅: 문자열/수치/불리언/기타를 True/False로 정규화."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        # 0.0은 False, 그 외는 True
        return bool(v)
    if isinstance(v, (bytes, bytearray)):
        try:
            v = v.decode("utf-8", "ignore")
        except Exception:
            return False
    if isinstance(v, str):
        s = v.strip().lower()
        return s in ("1", "true", "yes", "y", "on", "t")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 제일 깔끔한 방법: generic 함수의 오버로드 유지 + 구현에서 분기로 반환형 확정
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

from typing import MutableMapping as _MM

def _sanitize_bool_flags_inplace(st: _MM[str, Any]) -> int:
    """state['flags'] 안의 불리언 플래그를 as_bool로 정규화. 변경 개수 반환."""
    try:
        flags = st.get("flags")
        if not isinstance(flags, _MM):
            return 0
        changed = 0
        for k in _BOOL_FLAG_KEYS:
            if k in flags:
                old = flags[k]
                new = as_bool(old)
                if new != old:
                    flags[k] = new
                    changed += 1
        if changed:
            logger.debug("sanitize_flags: coerced %d boolean flags", changed)
        return changed
    except Exception:
        return 0


@overload
def sanitize_state(st: StateT) -> StateT: ...
@overload
def sanitize_state(st: MutableMapping[str, Any]) -> MutableMapping[str, Any]: ...
@overload
def sanitize_state(st: Mapping[str, Any]) -> Dict[str, Any]: ...

def sanitize_state(st: Any) -> Any:
    """
    숫자 필드(int)와 flags의 불리언 필드를 정규화합니다.
    - State/MutableMapping: in-place 정규화 후 원본 반환(부작용 있음)
    - Mapping: dict(st) 복사본을 만들어 정규화 후 반환(부작용 없음)
    """
    if isinstance(st, MutableMapping):  # in-place
        sanitize_numeric_state_generic(st)
        # (선택) flags가 dict가 아니면 초기화하여 downstream 안전성 향상
        if not isinstance(st.get("flags"), MutableMapping):
            st["flags"] = {}
        _sanitize_bool_flags_inplace(cast(MutableMapping[str, Any], st))  # [ADD] flags 불리언 정규화
        return st

    if isinstance(st, Mapping):
        mm = sanitize_numeric_state_generic(dict(st))  # 복사 정규화
        _sanitize_bool_flags_inplace(cast(MutableMapping[str, Any], mm))  # [ADD]
        return mm

    mm3 = sanitize_numeric_state_generic(st)
    if isinstance(mm3, MutableMapping):
        _sanitize_bool_flags_inplace(cast(MutableMapping[str, Any], mm3))  # [ADD]
    return mm3

def sanitize_state_copy(st: Mapping[str, Any] | None) -> dict[str, Any]:
    """원본을 보존하고 싶은 경우 사용: 항상 dict 복사본을 반환."""
    base = dict(st or {})
    base = sanitize_numeric_state_generic(base)
    # 복사본에서도 불리언 플래그 정규화 수행
    _sanitize_bool_flags_inplace(cast(MutableMapping[str, Any], base))
    return base
