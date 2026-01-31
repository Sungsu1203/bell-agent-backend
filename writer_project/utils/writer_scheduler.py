from __future__ import annotations
"""
DEPRECATED shim.

✅ 앞으로는 반드시:
    from utils.tasks import schedule_writer_if_needed
를 사용하세요.

이 모듈은 예전 코드 호환용으로만 남겨둔 얇은 래퍼입니다.
"""

from typing import Any, MutableMapping, Optional, Protocol, cast
import logging
import warnings

logger = logging.getLogger(__name__)


def _maybe_warn_deprecated() -> None:
    warnings.warn(
        "DEPRECATED: import schedule_writer_if_needed from utils.tasks "
        "instead of utils.writer_scheduler.",
        DeprecationWarning,
        stacklevel=2,
    )


class _CoreScheduleProto(Protocol):
    def __call__(self, state: MutableMapping[str, Any], *, reason: str | None = None) -> None: ...


_core_schedule: Optional[_CoreScheduleProto]
try:
    # 정본 구현을 들여와서 우리가 기대하는 시그니처로 캐스팅
    from utils.tasks import schedule_writer_if_needed as _core_schedule_impl
    _core_schedule = cast(_CoreScheduleProto, _core_schedule_impl)
except Exception:  # pragma: no cover
    _core_schedule = None


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
    Backward-compatible wrapper.

    - legacy 시그니처(state, tasks, outline_text, ...)를 그대로 받아도,
      내부에서는 utils.tasks.schedule_writer_if_needed(state, ...)만 호출합니다.
    - tasks / outline_text / mode / debug 는 여기서는 해석하지 않고 버립니다
      (필요한 정보는 이미 state.flags 등에 들어있다는 가정).
    """
    _maybe_warn_deprecated()

    if _core_schedule is None:
        logger.warning(
            "writer_scheduler shim: core schedule_writer_if_needed not available; noop"
        )
        return False

    reason = kwargs.get("reason") or "writer_scheduler shim"
    _core_schedule(state, reason=str(reason))
    return True


__all__ = ["schedule_writer_if_needed"]