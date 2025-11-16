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
import os

logger = logging.getLogger(__name__)

# NOTE: Wrapper에서는 Task 타입을 강제할 필요가 없으므로 불러오지 않습니다.
_WS_REENTRY = False  # 재진입 가드: 동일 호출 트리 내 중복/순환 호출 방지

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

class _FnNewProto(Protocol):
    def __call__(self, state: MutableMapping[str, Any], *, reason: Optional[str] = ...) -> None: ...
class _FnLegacyProto(Protocol):
    def __call__(self, state: Any, tasks: Any, *, outline_text: Any, mode: Any = ..., **kwargs: Any) -> Any: ...
class _GetLastWriteTargetProto(Protocol):
    def __call__(self, messages: Sequence[Any], tasks: Sequence[Any]) -> Optional[str]: ...

def _load_core() -> tuple[Optional[_FnNewProto], Optional[_FnLegacyProto], Optional[_GetLastWriteTargetProto]]:
    """지연 로딩: 호출 시점에 utils.tasks 에서 코어 참조를 읽는다."""
    try:
        from utils import tasks as _tasks_mod
        core_new = cast(Optional[_FnNewProto], getattr(_tasks_mod, "schedule_writer_if_needed", None))
        core_legacy = cast(Optional[_FnLegacyProto], getattr(_tasks_mod, "schedule_writer_if_needed_legacy", None))
        get_last = cast(Optional[_GetLastWriteTargetProto], getattr(_tasks_mod, "get_last_write_target", None))
        return core_new, core_legacy, get_last
    except Exception:
        return None, None, None

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
    global _WS_REENTRY
    # 재진입/순환 호출 방지(레거시-신규 ping-pong 차단)
    if _WS_REENTRY:
        logger.debug("[writer_scheduler.shim] re-entry detected → noop")
        return False
    _WS_REENTRY = True
    try:
        # ── Direct QA 노이즈 억제 가드 ──────────────────────────
        try:
            _flags = dict(state.get("flags") or {})
            if (bool(_flags.get("qa_direct_reply")) or bool(_flags.get("DIRECT_QA"))) and not bool(_flags.get("force_writer")):
                _router = dict(_flags.get("router") or {})
                if not _router.get("writer_skipped"):
                    _router["writer_skipped"] = "direct_qa"
                _flags["router"] = _router
                state["flags"] = _flags
                return False
        except Exception:
            pass

        core_new, core_legacy, get_last = _load_core()

        # ⚠️ 순환 차단 정책: 이 shim은 항상 신규 코어만 호출한다.
        #    (레거시 코어는 호출하지 않는다. core_legacy 경로는 완전 차단)
        if core_new is None:  # pragma: no cover
            # 과도한 경고 방지를 위해 조용히 no-op (디버그 환경에서만 로그)
            if (os.getenv("DEBUG_WRITER_SCHEDULER_NOOP") or "").strip() in {"1","true","yes"}:
                logger.info("[writer_scheduler] core missing; noop")
            return False

        # requested_title 산출: kwargs → 최근 메시지/태스크 → flags
        requested_title = kwargs.get("requested_title")
        if not requested_title and get_last:
            try:
                messages = state.get("messages", [])
                requested_title = get_last(messages, tasks or [])
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
        # 레거시 어댑터에서 호출되는 경우에도 여기서는 역호출하지 않음
        core_new(state, reason=str(kwargs.get("reason") or "writer_scheduler shim"))
        return True
    finally:
        _WS_REENTRY = False
__all__ = ["schedule_writer_if_needed"]