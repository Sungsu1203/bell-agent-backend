# core/llm.py
from __future__ import annotations
import os
from typing import Any, Callable, Optional, cast

_LLM: Any = None  # 런타임 캐시

def get_llm(model: Optional[str] = None, temperature: float = 0.3):
    """Lazy-import + 싱글턴. 타입체커가 None-call로 오해하지 않도록 cast로 호출 보장."""
    global _LLM
    if _LLM is not None:
        return _LLM

    m = model or os.getenv("OPENAI_MODEL", "gpt-4o")

    # 런타임 임포트 (신버전 → 구버전 폴백)
    try:
        from langchain_openai import ChatOpenAI  # 최신 경로
    except Exception:
        try:
            from langchain.chat_models import ChatOpenAI  # 구버전 폴백  # type: ignore
        except Exception as e:
            raise ImportError(
                "ChatOpenAI import 실패. pip install langchain-openai 또는 langchain 버전을 확인하세요."
            ) from e

    # 🔑 핵심: 타입체커에게 '이건 호출 가능한 것'이라고 알려주기
    ChatCtor = cast(Callable[..., Any], ChatOpenAI)
    _LLM = ChatCtor(model=m, temperature=temperature)
    return _LLM


def reset_llm() -> None:
    """테스트용: 내부 캐시 초기화"""
    global _LLM
    _LLM = None
