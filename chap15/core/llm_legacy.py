# core/llm.py
from __future__ import annotations
import os
from typing import Any, Callable, Optional, cast

import logging
logger = logging.getLogger(__name__)

_LLM: Any = None

# ─────────────────────────────────────────────────────────────────────────────
# TEST-ONLY FAST PATH: BLOCKAGI_TEST_FAKE_LLM=1 이면 가벼운 Fake Chat 모델 사용
#  - transformers/torch 등 무거운 의존성 import를 피하기 위해 langchain_openai를 건드리지 않음
#  - .bind_tools()를 호출하는 코드가 있으므로 Chat 계열 fake를 우선 시도
# ─────────────────────────────────────────────────────────────────────────────
if os.getenv("BLOCKAGI_TEST_FAKE_LLM", "0") == "1":
    try:
        # langchain-core 최신계열: FakeListChatModel 이 존재 (도구 바인딩 지원)
        from langchain_core.language_models.fake import FakeListChatModel as _FakeChat  # type: ignore
    except Exception:
        try:
            # 일부 버전 호환
            from langchain_core.language_models.chat_models import FakeListChatModel as _FakeChat  # type: ignore
        except Exception:
            # 최후수단: FakeListLLM + bind_tools 어댑터
            from langchain_core.language_models.fake import FakeListLLM as _BaseFake  # type: ignore

            class _FakeChat(_BaseFake):  # type: ignore
                # bind_tools를 호출해도 자기 자신을 반환만 하도록
                def bind_tools(self, tools):  # type: ignore
                    return self

    def get_llm(
        model: Optional[str] = None,
        temperature: float = 0.0,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> Any:
        global _LLM
        if _LLM is not None:
            return _LLM
        # 테스트에 충분한 더미 응답들
        responses = [
            "ok", "ack", "noted",
            # 필요 시 더 추가 가능
        ]
        try:
            _LLM = _FakeChat(responses=responses)  # type: ignore[arg-type]
        except TypeError:
            # 일부 구현은 responses 인자를 안 받기도 함
            _LLM = _FakeChat()  # type: ignore[call-arg]
        return _LLM

    class _DummyEmbeddings:
        def embed_query(self, text: str): return [0.0]
        def embed_documents(self, texts): return [[0.0] for _ in texts]

    def get_embedding_model():
        return _DummyEmbeddings()

    def reset_llm() -> None:
        global _LLM
        _LLM = None

    __all__ = ["get_llm", "get_embedding_model", "reset_llm"]
else:
    # ─────────────────────────────────────────────────────────────────────────
    # 실제 실행 경로: OpenAI Chat 모델 사용
    # ─────────────────────────────────────────────────────────────────────────
    from typing import cast

    # ✅ 두 분기 모두 같은 별칭으로 임포트
    try:
        from langchain_openai import ChatOpenAI as _ChatOpenAI
    except Exception:
        try:
            from langchain.chat_models import ChatOpenAI as _ChatOpenAI  # type: ignore
        except Exception as e:
            raise ImportError(
                "ChatOpenAI import 실패. `pip install langchain-openai` 또는 langchain 버전을 확인하세요."
            ) from e

    ChatCtor: Callable[..., Any] = cast(Callable[..., Any], _ChatOpenAI)

    def get_llm(
        model: Optional[str] = None,
        temperature: float = 0.3,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> Any:
        global _LLM
        if _LLM is not None:
            return _LLM

        m = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        base_url = (base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE"))
        organization = (organization or os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION"))

        def _try(**kw):
            try:
                return ChatCtor(**kw)
            except TypeError:
                return None

        # 신(新) 파라미터 스타일 우선
        if api_key or base_url or organization:
            inst = _try(model=m, temperature=temperature,
                        api_key=api_key, base_url=base_url, organization=organization)
            if inst is not None:
                _LLM = inst; return _LLM

        inst = _try(model=m, temperature=temperature)
        if inst is not None:
            _LLM = inst; return _LLM

        # 구(舊) 파라미터 스타일 (호환용)
        if api_key or base_url or organization:
            inst = _try(model_name=m, temperature=temperature,
                        openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization)
            if inst is not None:
                _LLM = inst; return _LLM

        inst = _try(model_name=m, temperature=temperature)
        if inst is not None:
            _LLM = inst; return _LLM

        if not api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다. 환경변수나 get_llm(api_key=...)로 제공하세요.")
        raise RuntimeError("ChatOpenAI 생성자 시그니처와 맞지 않습니다. langchain / langchain-openai 버전을 확인하세요.")

    def reset_llm() -> None:
        global _LLM
        _LLM = None

    __all__ = ["get_llm", "reset_llm"]

