# utils/tasks.py
from __future__ import annotations
from typing import Optional, Protocol, Iterable, Any, Sequence

class _TaskLike(Protocol):
    agent: str
    done: bool
    description: Optional[str]

def has_pending(tasks: Iterable[_TaskLike], agent: str, prefix: Optional[str] = None) -> bool:
    # reversed()를 쓰려면 list로 한 번 감싸서 역순 순회
    for t in reversed(list(tasks)):
        if (not t.done) and t.agent == agent:
            if prefix is None:
                return True
            if (t.description or "").lower().startswith(prefix.lower()):
                return True
    return False

# LangChain이 없는 환경에서도 안전하게 동작하도록 '선택적' 임포트
try:
    from langchain_core.messages import HumanMessage  # type: ignore
except Exception:  # 런타임/타입체커 모두 통과용 폴백
    class HumanMessage:  # type: ignore
        pass

from rag_expression import extract_write_title

def get_last_write_target(
    messages: Sequence[Any],
    tasks: Sequence[Any],
) -> Optional[str]:
    """
    최근 HumanMessage/Task에서 `write:` 대상 제목을 추출.
    - messages: LangChain 스타일 메시지 시퀀스(섞여 있어도 됨)
    - tasks: Task(pydantic/dict 유사) 시퀀스
    """
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

__all__ = ["has_pending","get_last_write_target"]