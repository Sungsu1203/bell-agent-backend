# utils/writer_scheduler.py — DEPRECATED thin wrapper
from __future__ import annotations
"""
DEPRECATED: import `schedule_writer_if_needed` from `utils.tasks` instead.
This module only provides a backward-compatible pass-through wrapper.
"""
from typing import Any, MutableMapping, Optional, List, Sequence, Protocol, cast

import logging
import warnings
import inspect

logger = logging.getLogger(__name__)

# NOTE: Wrapper에서는 Task 타입을 강제할 필요가 없으므로 불러오지 않습니다.

_DEP_WARNED = False

def _maybe_warn_deprecated() -> None:
    """Show a deprecation warning once if called outside utils.tasks."""
    global _DEP_WARNED
    if _DEP_WARNED:
        return
    try:
        st = inspect.stack()
        caller_mod = st[2].frame.f_globals.get("__name__", "") if len(st) > 2 else ""
    except Exception:
        caller_mod = ""
    if caller_mod != "utils.tasks":
        warnings.warn(
            "DEPRECATED: Use `from utils.tasks import schedule_writer_if_needed`.",
            DeprecationWarning,
            stacklevel=3,
        )
    _DEP_WARNED = True

# Source of truth (prefer legacy shim if available) — 명시적 시그니처
class _FnNewProto(Protocol):
    def __call__(self, state: MutableMapping[str, Any], *, reason: Optional[str] = ...) -> None: ...

class _FnLegacyProto(Protocol):
    def __call__(self, state: Any, tasks: Any, *, outline_text: Any, mode: Any = ..., **kwargs: Any) -> Any: ...

class _GetLastWriteTargetProto(Protocol):
    def __call__(self, messages: Sequence[Any], tasks: Sequence[Any]) -> Optional[str]: ...

_core_new: Optional[_FnNewProto] = None
_core_legacy: Optional[_FnLegacyProto] = None
_get_last_write_target: Optional[_GetLastWriteTargetProto] = None
try:
    from utils import tasks as _tasks_mod
    _core_new = cast(_FnNewProto, getattr(_tasks_mod, "schedule_writer_if_needed", None))
    _core_legacy = cast(_FnLegacyProto, getattr(_tasks_mod, "schedule_writer_if_needed_legacy", None))
    _get_last_write_target = cast(_GetLastWriteTargetProto, getattr(_tasks_mod, "get_last_write_target", None))
except Exception as e:  # pragma: no cover
    logger.error("[writer_scheduler] import from utils.tasks failed: %s", e)

def schedule_writer_if_needed(
    state: MutableMapping[str, Any],
    tasks: Optional[list[Any]] = None,
    *,
    outline_text: str = "",
    mode: Optional[str] = None,
    debug: bool = False,
    **kwargs: Any,
) -> bool:
    """
    Backward-compatible wrapper. Prefer importing from `utils.tasks`.
    Note:
      - Signature aligns with utils.tasks version (accepts **kwargs for forwards-compat).
      - If `tasks` is None, it will be obtained from state within the core function.
    """
    _maybe_warn_deprecated()
    # 1) 레거시 셔임이 있으면 그대로 위임(완전 호환)
    if _core_legacy is not None:
        return bool(
            _core_legacy(
                state,
                tasks or (state.get("task_history") or []),
                outline_text=outline_text,
                mode=mode,
                debug=debug,
                **kwargs,
            )
        )

    # 2) 레거시가 없으면 신규 단일 진입점에 맞춰 변환
    if _core_new is None:  # pragma: no cover
        logger.warning("[writer_scheduler] core function missing; no-op")
        return False

    # requested_title 산출: kwargs → 최근 메시지/태스크 → flags
    requested_title = kwargs.get("requested_title")
    if not requested_title and _get_last_write_target:
        try:
            messages = state.get("messages", [])
            requested_title = _get_last_write_target(messages, tasks or [])
        except Exception:
            requested_title = None
    if not requested_title:
        try:
            flags = state.get("flags") or {}
            requested_title = (flags.get("requested_write_title") or "").strip() or None
        except Exception:
            requested_title = None

    # flags에 주입하여 신규 API가 정상 예약하도록 보조
    try:
        flags = dict(state.get("flags") or {})
        router_flags = dict(flags.get("router") or {})
        if requested_title and not flags.get("requested_write_title"):
            flags["requested_write_title"] = requested_title
        state["flags"] = flags | {"router": router_flags}
    except Exception:
        pass

    # 신규 API 호출 (positional 하나만)
    _core_new(state, reason="writer_scheduler shim")
    return True
__all__ = ["schedule_writer_if_needed"]