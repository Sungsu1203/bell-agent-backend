# utils/tasks.py
from __future__ import annotations
from typing import Optional, Protocol, Iterable, Any, Sequence, TYPE_CHECKING

# # ── 메시지 클래스: 여기서만 임포트/재노출 ─────────────────────────────
# try:
#     from langchain_core.messages import (
#         HumanMessage as _HumanMessage,
#         AIMessage as _AIMessage,
#         SystemMessage as _SystemMessage,
#     )
#     HumanMessage = _HumanMessage
#     AIMessage = _AIMessage
#     SystemMessage = _SystemMessage
# except Exception:
#     # LangChain 미설치 시 얇은 폴백 (테스트/타입용)
#     class _BaseMsg:
#         def __init__(self, content: str) -> None:
#             self.content = content
#     class HumanMessage(_BaseMsg): ...
#     class AIMessage(_BaseMsg): ...
#     class SystemMessage(_BaseMsg): ...


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

def has_pending(tasks: Iterable[_TaskLike], agent: str, prefix: Optional[str] = None) -> bool:
    for t in reversed(list(tasks)):
        if (not t.done) and t.agent == agent:
            if prefix is None:
                return True
            desc = (t.description or "") if isinstance(t.description, (str, type(None))) else str(t.description)
            if desc.lower().startswith(prefix.lower()):
                return True
    return False

from rag_expression import extract_write_title

def get_last_write_target(
    messages: Sequence[Any],
    tasks: Sequence[Any],
) -> Optional[str]:
    # 1) 최근 사용자 메시지에서 추출
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            content = getattr(m, "content", "") or ""
            t = extract_write_title(content)
            if t:
                return t
    # 2) 최근 태스크 설명에서 추출
    for t in reversed(tasks or []):
        desc = getattr(t, "description", None)
        if desc is None and isinstance(t, dict):
            desc = t.get("description", "")
        title = extract_write_title((desc or ""))
        if title:
            return title
    return None

def iter_tool_calls(msg, name: str):
    tcs = getattr(msg, "tool_calls", []) or []
    for tc in tcs:
        if isinstance(tc, dict):
            n = (tc.get("name") or "").lower()
            args = tc.get("args") or {}
        else:
            n = (getattr(tc, "name", "") or "").lower()
            args = getattr(tc, "args", {}) or {}
        if n == name.lower():
            yield args

__all__ = [
    "HumanMessage", "AIMessage", "SystemMessage",
    "has_pending", "get_last_write_target", "iter_tool_calls"
]
