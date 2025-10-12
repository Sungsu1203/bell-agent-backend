# core/llm.py
from __future__ import annotations
import os
from typing import Any, Callable, Optional, cast

import logging
logger = logging.getLogger(__name__)

_LLM: Any = None
_EMB: Any = None

def _mask(v: Optional[str]) -> str:
    """민감 값 로깅용 마스킹."""
    if not v:
        return ""
    if len(v) <= 6:
        return "*" * len(v)
    return v[:3] + "…" + v[-2:]


# ─────────────────────────────────────────────────────────────────────────────
# TEST-ONLY FAST PATH: 가벼운 Fake Chat/Embeddings
# ─────────────────────────────────────────────────────────────────────────────
if os.getenv("BLOCKAGI_TEST_FAKE_LLM", "0") == "1":
    try:
        # langchain-core 최신계열
        from langchain_core.language_models.fake import FakeListChatModel as _FakeChat  # type: ignore
    except Exception:
        try:
            from langchain_core.language_models.chat_models import FakeListChatModel as _FakeChat  # type: ignore
        except Exception:
            from langchain_core.language_models.fake import FakeListLLM as _BaseFake  # type: ignore

            class _FakeChat(_BaseFake):  # type: ignore
                def bind_tools(self, tools):  # no-op for compatibility
                    return self

    class _DummyEmbeddings:
        def embed_query(self, text: str): return [0.0]
        def embed_documents(self, texts): return [[0.0] for _ in texts]

    def get_llm(
        model: Optional[str] = None,
        temperature: float = 0.0,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> Any:
        """가벼운 테스트용 LLM (도구 바인딩 호환)."""
        global _LLM
        if _LLM is not None:
            return _LLM
        responses = ["ok", "ack", "noted"]  # 필요한 경우 테스트 응답 추가
        try:
            _LLM = _FakeChat(responses=responses)  # type: ignore[arg-type]
        except TypeError:
            _LLM = _FakeChat()  # type: ignore[call-arg]
        logger.info("[LLM] Using FakeChat for tests (BLOCKAGI_TEST_FAKE_LLM=1)")
        return _LLM

    def get_embedding_model():
        global _EMB
        if _EMB is None:
            _EMB = _DummyEmbeddings()
            logger.info("[Embeddings] Using DummyEmbeddings for tests")
        return _EMB

    def reset_llm() -> None:
        global _LLM, _EMB
        _LLM = None
        _EMB = None
        logger.debug("[LLM] reset (test mode)")

    __all__ = ["get_llm", "get_embedding_model", "reset_llm"]

# ─────────────────────────────────────────────────────────────────────────────
# 실제 실행 경로: OpenAI(Chat) + OpenAIEmbeddings (가능하면)
# ─────────────────────────────────────────────────────────────────────────────
else:
    # ChatOpenAI 호환 임포트
    try:
        from langchain_openai import ChatOpenAI as _ChatOpenAI
    except Exception:
        try:
            from langchain.chat_models import ChatOpenAI as _ChatOpenAI  # type: ignore
        except Exception as e:
            raise ImportError(
                "ChatOpenAI import 실패. `pip install langchain-openai` 또는 langchain 버전을 확인하세요."
            ) from e

    # Embeddings 호환 임포트 (실패 시 더미로 폴백)
    _EmbCtor: Optional[Callable[..., Any]] = None
    try:
        from langchain_openai import OpenAIEmbeddings as _OpenAIEmbeddings  # type: ignore
        _EmbCtor = cast(Callable[..., Any], _OpenAIEmbeddings)
    except Exception:
        try:
            from langchain.embeddings import OpenAIEmbeddings as _OpenAIEmbeddings  # type: ignore
            _EmbCtor = cast(Callable[..., Any], _OpenAIEmbeddings)
        except Exception:
            _EmbCtor = None

    ChatCtor: Callable[..., Any] = cast(Callable[..., Any], _ChatOpenAI)

    def _build_kwargs(
        m: str,
        temperature: float,
        api_key: Optional[str],
        base_url: Optional[str],
        organization: Optional[str],
    ) -> list[dict]:
        """신/구 파라미터 스타일 모두 시도할 수 있도록 후보 kwargs를 생성."""
        # 공통 추가 옵션
        request_timeout = os.getenv("OPENAI_REQUEST_TIMEOUT")
        max_retries = os.getenv("OPENAI_MAX_RETRIES")
        extra: dict = {}
        if request_timeout:
            try: extra["timeout"] = float(request_timeout)
            except Exception: pass
        if max_retries:
            try: extra["max_retries"] = int(max_retries)
            except Exception: pass

        candidates = [
            # 신(新) 스타일
            dict(model=m, temperature=temperature, api_key=api_key, base_url=base_url, organization=organization, **extra),
            dict(model=m, temperature=temperature, **extra),
            # 구(舊) 스타일
            dict(model_name=m, temperature=temperature,
                 openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization, **extra),
            dict(model_name=m, temperature=temperature, **extra),
        ]
        return candidates

    def get_llm(
        model: Optional[str] = None,
        temperature: float = 0.3,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> Any:
        """프로덕션용 LLM 인스턴스를 싱글턴으로 반환."""
        global _LLM
        if _LLM is not None:
            return _LLM

        m = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
        organization = organization or os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")

        logger.info(
            "[LLM] init model=%s | base_url=%s | org=%s | temp=%.2f",
            m, _mask(base_url), _mask(organization), temperature
        )

        def _try_ctor(**kw):
            try:
                return ChatCtor(**kw)
            except TypeError:
                return None
            except Exception as e:
                logger.debug("[LLM] ctor failed with %s: %s", list(kw.keys()), e)
                return None

        # 후보 kwargs 순차 시도
        for kw in _build_kwargs(m, temperature, api_key, base_url, organization):
            inst = _try_ctor(**kw)
            if inst is not None:
                _LLM = inst
                logger.info("[LLM] ready (ctor=%s)", "model" if "model" in kw else "model_name")
                return _LLM

        if not api_key:
            logger.error("OPENAI_API_KEY 미설정: 환경변수 또는 get_llm(api_key=...)로 제공 필요")
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
        logger.error("ChatOpenAI 생성자 시그니처 불일치: langchain / langchain-openai 버전 확인 필요")
        raise RuntimeError("ChatOpenAI 생성자 시그니처와 맞지 않습니다. langchain / langchain-openai 버전을 확인하세요.")

    def get_embedding_model():
        """OpenAIEmbeddings 인스턴스(가능하면) 또는 더미 임베딩 반환."""
        global _EMB
        if _EMB is not None:
            return _EMB
        if _EmbCtor is not None:
            # 신/구 스타일 모두 수용
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
            organization = os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")

            kwargs_list = [
                dict(api_key=api_key, base_url=base_url, organization=organization),
                dict(openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization),
                dict(),  # 기본값
            ]
            for kw in kwargs_list:
                try:
                    _EMB = _EmbCtor(**kw)
                    logger.info("[Embeddings] OpenAIEmbeddings ready")
                    return _EMB
                except Exception as e:
                    logger.debug("[Embeddings] ctor failed %s", e)

        # 폴백: 더미
        class _DummyEmbeddings:
            def embed_query(self, text: str): return [0.0]
            def embed_documents(self, texts): return [[0.0] for _ in texts]
        _EMB = _DummyEmbeddings()
        logger.warning("[Embeddings] OpenAIEmbeddings unavailable → using DummyEmbeddings")
        return _EMB

    def reset_llm() -> None:
        """테스트/재설정용: 캐시를 초기화."""
        global _LLM, _EMB
        _LLM = None
        _EMB = None
        logger.debug("[LLM] reset")

    __all__ = ["get_llm", "get_embedding_model", "reset_llm"]
