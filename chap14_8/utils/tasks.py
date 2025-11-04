# utils/tasks.py — dynamic config access (v2025-10-27)
from __future__ import annotations
from typing import Optional, Protocol, Iterable, Any, Sequence, TYPE_CHECKING, Dict, List
from types import ModuleType

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


def _as_list(v: Any) -> List[str]:
    if not v:
        return []
    try:
        return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────
# Per-call dynamic getters (reload_config() 즉시 반영)
# ─────────────────────────────────────────────────────────────
def _pending_prefix_casefold() -> bool:
    try:
        return bool(_get_cfg_attr("PENDING_PREFIX_CASEFOLD", True))
    except Exception:
        return True

def _tool_calls_fields() -> List[str]:
    return _as_list(_get_cfg_attr("TOOL_CALLS_FIELDS", None)) or ["tool_calls", "additional_kwargs.tool_calls"]

def _tool_name_field() -> str:
    try:
        return str(_get_cfg_attr("TOOL_NAME_FIELD", "name") or "name")
    except Exception:
        return "name"

def _tool_args_field() -> str:
    try:
        return str(_get_cfg_attr("TOOL_ARGS_FIELD", "args") or "args")
    except Exception:
        return "args"

def _allow_during_research_default() -> bool:
    try:
        return bool(_get_cfg_attr("ALLOW_DURING_RESEARCH_DEFAULT", False))
    except Exception:
        return False

def _write_title_regex_str() -> str:
    try:
        return str(_get_cfg_attr("WRITE_TITLE_REGEX", r"^\s*write\s*:\s*(.+)$") or r"^\s*write\s*:\s*(.+)$")
    except Exception:
        return r"^\s*write\s*:\s*(.+)$"

# ─────────────────────────────────────────────────────────────
# LangChain message shims (type-checker sees real types)
# ─────────────────────────────────────────────────────────────
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

__all__ = [
    "HumanMessage", "AIMessage", "SystemMessage",
    "has_pending", "get_last_write_target", "iter_tool_calls",
    "schedule_writer_if_needed",
]

# ─────────────────────────────────────────────────────────────
# Task-like 프로토콜 & 도우미
# ─────────────────────────────────────────────────────────────
class _TaskLike(Protocol):
    agent: str
    done: bool
    description: Any  # Optional[str]일 수 있으니 Any로 완화

def _read_task_fields(obj: Any) -> tuple[str, bool, str]:
    """
    덕 타이핑으로 task 유사 객체에서 (agent, done, description) 추출.
    - dict / 객체 모두 지원
    - agent는 str()로 표준화(AgentName Literal도 OK)
    """
    if isinstance(obj, dict):
        agent = str(obj.get("agent", "") or "")
        done = bool(obj.get("done", False))
        desc = obj.get("description", "")
        return agent, done, str(desc or "")
    agent = str(getattr(obj, "agent", "") or "")
    done = bool(getattr(obj, "done", False))
    desc = getattr(obj, "description", "")
    return agent, done, str(desc or "")

from collections.abc import Sequence as _Seq

def has_pending(tasks: Iterable[Any], agent: str, prefix: Optional[str] = None) -> bool:
    """
    미완료(done=False) + agent 일치(+ description prefix 옵션) 검사.
    - 입력 tasks: list/tuple/iterable 모두 지원
    - agent: Literal[...] 포함 어떤 타입이 와도 내부에서 str() 표준화
    - prefix: 기본 casefold 비교(CFG.PENDING_PREFIX_CASEFOLD)
    """
    agent_key = str(agent or "").strip()
    if not agent_key:
        return False

    # 역순 검사(최근 항목 우선)
    if isinstance(tasks, _Seq):
        itr = reversed(list(tasks))
    else:
        buf = list(tasks or [])
        itr = reversed(buf)

    pfx = prefix
    if isinstance(prefix, str) and _pending_prefix_casefold():
        pfx = prefix.casefold()

    for t in itr:
        try:
            t_agent, t_done, t_desc = _read_task_fields(t)
            if t_done:
                continue
            if t_agent.strip() != agent_key:
                continue
            if pfx is None:
                return True
            cmp = t_desc.casefold() if _pending_prefix_casefold() else t_desc
            if isinstance(pfx, str) and cmp.startswith(pfx):
                return True
        except Exception:
            logger.debug("has_pending: task inspection failed", exc_info=True)
            continue
    return False



# ─────────────────────────────────────────────────────────────
# write: <title> 추출기 (동적 정규식 허용)
# ─────────────────────────────────────────────────────────────
try:
    # 실제 구현을 다른 이름으로 들여오고
    from rag_expression import extract_write_title as _extract_write_title  # (text_like: Any) -> Optional[str]

    # 우리가 원하는 정확한 시그니처로 래퍼를 제공
    def extract_write_title(text: Optional[str]) -> Optional[str]:
        return _extract_write_title(text)  

except Exception:
    import re as _re
    def _re_write() -> "_re.Pattern[str]":
        pat = _write_title_regex_str()
        try:
            return _re.compile(pat, _re.I | _re.M)
        except Exception:
            return _re.compile(r"^\s*write\s*:\s*(.+)$", _re.I | _re.M)
    def extract_write_title(text: str | None) -> Optional[str]:
        """fallback: 기본은 'write: <title>' 패턴, 설정으로 커스터마이즈 가능"""
        if not text:
            return None
        m = _re_write().search(str(text))
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


# ─────────────────────────────────────────────────────────────
# tool_calls 파서 (동적 필드 경로 허용)
# ─────────────────────────────────────────────────────────────
import json as _json

def _get_path(obj: Any, dotted: str):
    cur = obj
    for part in dotted.split('.'):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
        if cur is None:
            return None
    return cur


def iter_tool_calls(msg, name: str):
    # OpenAI/LC 메시지 dict 포맷도 수용 + 설정 기반 경로
    tcs = None
    if isinstance(msg, dict):
        for path in _tool_calls_fields():
            tcs = _get_path(msg, path)
            if tcs:
                break
    else:
        # 속성 접근 우선, 없으면 additional_kwargs에서
        tcs = getattr(msg, "tool_calls", None) or getattr(getattr(msg, "additional_kwargs", {}), "get", lambda *_: [])("tool_calls")

    tcs = tcs or []
    target = (name or "").lower()

    for tc in tcs:
        try:
            if isinstance(tc, dict):
                n = (tc.get(_tool_name_field()) or "").lower()
                args = tc.get(_tool_args_field())
            else:
                n = (getattr(tc, _tool_name_field(), "") or "").lower()
                args = getattr(tc, _tool_args_field(), None)

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

# 모듈 단위 임포트로 이름 섀도잉/순환 이슈 최소화
_ws: ModuleType | None = None
_fn_real: Any | None = None
try:
    from . import writer_scheduler as _ws  # 모듈이 없을 수도 있으므로 예외 허용
    _fn_real = getattr(_ws, "schedule_writer_if_needed", None)
except Exception:
    _ws = None
    _fn_real = None


def _prefer(s: Optional[str], alt: Optional[str]) -> Optional[str]:
    """s가 비어있으면 alt, 아니면 s"""
    s = (s or "").strip()
    return s or ((alt or "").strip() or None)

def schedule_writer_if_needed(state, tasks, *, outline_text, mode=None, **kwargs):
    """
    Back-compat wrapper → utils.writer_scheduler.schedule_writer_if_needed 로 안전 포워딩.

    - 레거시 코드가 (state, tasks, outline_text=..., mode=...)로 호출해도 작동
    - 최신 writer_scheduler 시그니처(키워드 전용)에 맞춰 매핑
    - requested_title은 다음 우선순위로 전달:
        kwargs['requested_title'] → 최근 user 메시지 'write: ...' → state.flags.requested_write_title
    - 선택 인자(messages, allow_during_research, debug)도 있으면 그대로 전달 (없으면 설정 기본값)
    """
    if _fn_real is None:
        raise ImportError("utils.writer_scheduler.schedule_writer_if_needed not available")  # pragma: no cover

    # messages 추출(없으면 state에서 폴백)
    messages = kwargs.get("messages")
    if messages is None:
        try:
            messages = state.get("messages", [])
        except Exception:
            messages = []

    # requested_title 결정
    requested_title = kwargs.get("requested_title")
    if not requested_title:
        # 최근 user 메시지/태스크에서 'write: <title>' 추출
        try:
            requested_title = get_last_write_target(messages or [], tasks or [])
        except Exception:
            requested_title = None
        # flags 폴백
        if not requested_title:
            try:
                flags: Dict[str, Any] = state.get("flags") or {}
                requested_title = (flags.get("requested_write_title") or "").strip() or None
            except Exception:
                requested_title = None

    call_kwargs = {
        "tasks": tasks,
        "outline_text": outline_text,
        "messages": messages,
        "requested_title": requested_title,
    }
    # 선택 인자 전달
    if "allow_during_research" in kwargs:
        call_kwargs["allow_during_research"] = kwargs["allow_during_research"]
    else:
        call_kwargs["allow_during_research"] = _allow_during_research_default()
    if "debug" in kwargs:
        call_kwargs["debug"] = kwargs["debug"]

    try:
        res = _fn_real(state, **call_kwargs)  
        return bool(res)
    except TypeError as e:
        # 예상치 못한 시그니처 불일치 시에도 힌트 로그 남기고 실패 처리
        logger.debug("writer-schedule shim TypeError: %s; kwargs=%r", e, call_kwargs, exc_info=True)
        return False

# __all__는 상단에서 이미 선언/포함됨

# ─────────────────────────────────────────────────────────────
# (옵션) 캐시 무효화 훅 — 현재 구현은 per-call 조회이므로 no-op
# ─────────────────────────────────────────────────────────────
def refresh_tasks() -> None:  # pragma: no cover
    """향후 lru_cache 최적화 시 cache_clear() 연결용 훅.
    현재 버전은 per-call 조회로 즉시 반영되므로 동작 없음."""
    return

