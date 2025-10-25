# utils/tasks.py
from __future__ import annotations
from typing import Optional, Protocol, Iterable, Any, Sequence, TYPE_CHECKING

import logging
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    # 타입체커에게는 항상 원본 클래스를 보여준다 (아이덴티티 동일)
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
else:
    try:
        # 런타임에도 되면 그대로 사용
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    except Exception:
        # 런타임 폴백 (LangChain 없을 때만)
        class _BaseMsg:
            def __init__(self, content: str) -> None:
                self.content = content
        class HumanMessage(_BaseMsg): ...
        class AIMessage(_BaseMsg): ...
        class SystemMessage(_BaseMsg): ...

# ── Task-like 프로토콜 & 도우미 ─────────────────────────────────────
class _TaskLike(Protocol):
    agent: str
    done: bool
    description: Any  # Optional[str]일 수 있으니 Any로 완화

from collections.abc import Sequence as _Seq

def has_pending(tasks: Iterable[_TaskLike], agent: str, prefix: Optional[str] = None) -> bool:
    agent_key = (agent or "").strip()
    if not agent_key:
        return False

    # Sequence인 경우: 역순 직접 순회
    if isinstance(tasks, _Seq):
        itr = reversed(tasks)  # type: ignore[arg-type]
    else:
        # 이터러블인 경우: 한 번 순회하며 마지막 후보만 기억
        last = None
        for t in tasks:
            last = t
        itr = [last] if last is not None else []

    pfx = prefix.casefold() if isinstance(prefix, str) else None

    for t in itr:
        try:
            if getattr(t, "done", True):
                continue
            if getattr(t, "agent", None) != agent_key:
                continue
            if pfx is None:
                return True
            desc = getattr(t, "description", "")
            if not isinstance(desc, str):
                desc = str(desc or "")
            if desc.casefold().startswith(pfx):
                return True
        except Exception:
            logger.debug("has_pending: task inspection failed", exc_info=True)
            continue
    return False


# from rag_expression import extract_write_title
try:
    # 실제 구현을 다른 이름으로 들여오고
    from rag_expression import extract_write_title as _extract_write_title  # (text_like: Any) -> Optional[str]

    # 우리가 원하는 정확한 시그니처로 래퍼를 제공
    def extract_write_title(text: Optional[str]) -> Optional[str]:
        return _extract_write_title(text)  # type: ignore[call-arg]
    
except Exception:
    import re as _re
    _RE_WRITE = _re.compile(r"^\s*write\s*:\s*(.+)$", _re.I | _re.M)
    def extract_write_title(text: str | None) -> Optional[str]:
        """fallback: 'write: <title>' 패턴만 추출"""
        if not text:
            return None
        m = _RE_WRITE.search(str(text))
        return m.group(1).strip() if m else None

def get_last_write_target(
    messages: Sequence[Any],
    tasks: Sequence[Any],
) -> Optional[str]:
    # 1) 최근 사용자 메시지에서 추출
    for m in reversed(messages or []):
        try:
            # dict 포맷 메시지도 수용
            if isinstance(m, dict):
                role = (m.get("role") or "").lower()
                content = m.get("content") or ""
                if role == "user":
                    t = extract_write_title(str(content))
                    if t:
                        return t
            else:
                if isinstance(m, HumanMessage):
                    content = getattr(m, "content", "") or ""
                    t = extract_write_title(content)
                    if t:
                        return t
        except Exception:
            logger.debug("get_last_write_target: message parse error", exc_info=True)

    # 2) 최근 태스크 설명에서 추출
    for tt in reversed(tasks or []):
        try:
            desc = getattr(tt, "description", None)
            if desc is None and isinstance(tt, dict):
                desc = tt.get("description", "")
            title = extract_write_title((desc or ""))
            if title:
                return title
        except Exception:
            logger.debug("get_last_write_target: task parse error", exc_info=True)
    return None


import json as _json

def iter_tool_calls(msg, name: str):
    # OpenAI/LC 메시지 dict 포맷도 수용
    tcs = None
    if isinstance(msg, dict):
        tcs = (msg.get("tool_calls") or []) or (msg.get("additional_kwargs", {}).get("tool_calls") or [])
    else:
        tcs = getattr(msg, "tool_calls", None) or getattr(msg, "additional_kwargs", {}).get("tool_calls", [])

    tcs = tcs or []
    target = (name or "").lower()

    for tc in tcs:
        try:
            if isinstance(tc, dict):
                n = (tc.get("name") or "").lower()
                args = tc.get("args")
            else:
                n = (getattr(tc, "name", "") or "").lower()
                args = getattr(tc, "args", None)

            if n != target:
                continue

            # args가 문자열(JSON)인 경우 파싱 시도
            if isinstance(args, str):
                try:
                    args = _json.loads(args)
                except Exception:
                    logger.debug("iter_tool_calls: args json parse failed; using raw string")

            yield (args or {})
        except Exception:
            logger.debug("iter_tool_calls: tool call parse error", exc_info=True)
            continue

__all__ = [
    "HumanMessage", "AIMessage", "SystemMessage",
    "has_pending", "get_last_write_target", "iter_tool_calls"
]

# 모듈 단위 임포트로 이름 섀도잉/순환 이슈 최소화
try:
    from . import writer_scheduler as _ws  # type: ignore
    _fn_real = getattr(_ws, "schedule_writer_if_needed", None)
except Exception:
    _ws = None
    _fn_real = None

def schedule_writer_if_needed(state, tasks, *, outline_text, mode=None, **kwargs):
    """
    Back-compat wrapper → utils.writer_scheduler.schedule_writer_if_needed 로 안전 포워딩.

    - 테스트/레거시 코드가 (state, tasks, outline_text=..., mode=...)로 호출해도 작동
    - writer_scheduler 쪽 시그니처는 키워드 전용이므로, 여기서 키워드로 매핑
    - 불필요한 인자(mode 등) 무시
    - 선택 인자(messages, allow_during_research, debug)도 있으면 그대로 전달
    """
    if _fn_real is None:
        raise ImportError("utils.writer_scheduler.schedule_writer_if_needed not available")  # pragma: no cover

    call_kwargs = {
        "tasks": tasks,
        "outline_text": outline_text,
    }
    # 선택 인자 전달
    if "messages" in kwargs:
        call_kwargs["messages"] = kwargs["messages"]
    if "allow_during_research" in kwargs:
        call_kwargs["allow_during_research"] = kwargs["allow_during_research"]
    if "debug" in kwargs:
        call_kwargs["debug"] = kwargs["debug"]

    try:
        res = _fn_real(state, **call_kwargs)
        return bool(res)
    except TypeError as e:
        # 예상치 못한 시그니처 불일치 시에도 힌트 로그 남기고 실패 처리
        logger.debug("writer-schedule shim TypeError: %s; kwargs=%r", e, call_kwargs, exc_info=True)
        return False

# __all__ 보강
try:
    __all__.append("schedule_writer_if_needed")  # type: ignore
except NameError:
    __all__ = ["schedule_writer_if_needed"]