from __future__ import annotations
import os
import logging
from typing import Any, Callable, Optional, cast

logger = logging.getLogger(__name__)

_LLM: Any = None
_EMB: Any = None

def _mask(v: Optional[str]) -> str:
    """Masks sensitive values for logging."""
    if not v:
        return ""
    if len(v) <= 6:
        return "*" * len(v)
    return v[:3] + "…" + v[-2:]


# ─────────────────────────────────────────────────────────────────────────────
# LLM Provider Selection and Configuration
# ─────────────────────────────────────────────────────────────────────────────

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
if LLM_PROVIDER not in ("openai", "gemini"):
    logger.warning(
        "[LLM] Invalid LLM_PROVIDER='%s'. Defaulting to 'openai'. Set LLM_PROVIDER to 'openai' or 'gemini'.",
        LLM_PROVIDER
    )
    LLM_PROVIDER = "openai"

# ─────────────────────────────────────────────────────────────────────────────
# TEST-ONLY FAST PATH (Skipped for brevity, assuming existing code works)
# ─────────────────────────────────────────────────────────────────────────────
if os.getenv("BLOCKAGI_TEST_FAKE_LLM", "0") == "1":
    # --- Existing Fake LLM code (omitted for clean update) ---
    # ... [Your existing Fake LLM code should be here] ...
    # --------------------------------------------------------
    pass # PLACEHOLDER FOR EXISTING TEST CODE
# ─────────────────────────────────────────────────────────────────────────────
# Actual Execution Path: Provider Selective Loading
# ─────────────────────────────────────────────────────────────────────────────
else:
    ChatCtor: Optional[Callable[..., Any]] = None
    EmbCtor: Optional[Callable[..., Any]] = None
    
    # 1. OpenAI Provider Loading
    if LLM_PROVIDER == "openai":
        try:
            from langchain_openai import ChatOpenAI as _OpenAIChat, OpenAIEmbeddings as _OpenAIEmbeddings
            ChatCtor = cast(Callable[..., Any], _OpenAIChat)
            EmbCtor = cast(Callable[..., Any], _OpenAIEmbeddings)
        except ImportError as e:
            raise ImportError(
                "OpenAI LLM: 'langchain-openai' or 'langchain' import failed. "
                "Please run: `pip install langchain-openai`"
            ) from e

    # 2. Gemini Provider Loading
    elif LLM_PROVIDER == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI as _GeminiChat, GoogleGenerativeAIEmbeddings as _GeminiEmbeddings
            ChatCtor = cast(Callable[..., Any], _GeminiChat)
            EmbCtor = cast(Callable[..., Any], _GeminiEmbeddings)
        except ImportError as e:
            raise ImportError(
                "Gemini LLM: 'langchain-google-genai' import failed. "
                "Please ensure the package is installed: `pip install langchain-google-genai`"
            ) from e
    
    # [FIX] Ctor가 None인 경우, 명확한 RuntimeError로 바로 종료
    if ChatCtor is None:
        raise RuntimeError(f"Failed to load Chat model constructor for provider: {LLM_PROVIDER}. Check your dependencies and installations.")


    def _build_openai_kwargs(
        m: str,
        temperature: float,
        api_key: Optional[str],
        base_url: Optional[str],
        organization: Optional[str],
    ) -> list[dict]:
        """OpenAI 전용: 신/구 파라미터 스타일 모두 시도할 수 있도록 후보 kwargs를 생성."""
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
            # New style
            dict(model=m, temperature=temperature, api_key=api_key, base_url=base_url, organization=organization, **extra),
            dict(model=m, temperature=temperature, **extra),
            # Old style
            dict(model_name=m, temperature=temperature,
                 openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization, **extra),
            dict(model_name=m, temperature=temperature, **extra),
        ]
        return candidates
    
    def _build_gemini_kwargs(
        m: str,
        temperature: float,
        api_key: Optional[str],
    ) -> list[dict]:
        """Gemini 전용: LangChain 생성자 kwargs를 생성."""
        # model_name은 LangChain v0.1.x 스타일의 모델 이름입니다.
        return [
            dict(model=m, temperature=temperature, api_key=api_key),
            dict(model=m, temperature=temperature),
        ]


    def get_llm(
        model: Optional[str] = None,
        temperature: float = 0.3,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,  # Ignored for Gemini
        organization: Optional[str] = None, # Ignored for Gemini
    ) -> Any:
        """Returns a singleton LLM instance for production."""
        global _LLM
        if _LLM is not None:
            return _LLM

        # 1. Load env vars and defaults based on Provider
        if LLM_PROVIDER == "openai":
            m = model or os.getenv("OPENAI_MODEL", "gpt-4o")
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
            organization = organization or os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")
            kwarg_builder = lambda: _build_openai_kwargs(m, temperature, api_key, base_url, organization)

        elif LLM_PROVIDER == "gemini":
            m = model or os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
            api_key = api_key or os.getenv("GEMINI_API_KEY")
            kwarg_builder = lambda: _build_gemini_kwargs(m, temperature, api_key)
            base_url = organization = None

        logger.info(
            "[LLM] init provider=%s | model=%s | base_url=%s | org=%s | temp=%.2f",
            LLM_PROVIDER, m, _mask(base_url), _mask(organization), temperature
        )

        def _try_ctor(**kw):
            try:
                # ChatCtor가 None이 아님이 보장되었지만, Type Checker를 위해 cast 사용
                return cast(Callable[..., Any], ChatCtor)(**kw)
            except TypeError:
                return None
            except Exception as e:
                logger.debug("[LLM] ctor failed with %s: %s", list(kw.keys()), e)
                return None

        # Try candidate kwargs sequentially
        for kw in kwarg_builder():
            inst = _try_ctor(**kw)
            if inst is not None:
                _LLM = inst
                logger.info("[LLM] ready (provider=%s)", LLM_PROVIDER)
                return _LLM

        # ---------------------------------------------------------------------
        # [FIX: Name access guard] ChatCtor가 None일 때 대비하여 안전하게 이름을 가져옴
        # ---------------------------------------------------------------------
        ctor_name = getattr(ChatCtor, '__name__', 'UnknownChatCtor')

        # API Key Error Handling
        if not api_key:
            key_env_var = "OPENAI_API_KEY" if LLM_PROVIDER == "openai" else "GEMINI_API_KEY"
            logger.error("%s is not set: Must be provided via environment variable or get_llm(api_key=...)", key_env_var)
            raise RuntimeError(f"{key_env_var} is not set.")
        
        # Constructor Mismatch Error
        logger.error("%s 생성자 시그니처 불일치. LangChain/Provider 라이브러리 버전 확인 필요", ctor_name)
        raise RuntimeError(f"{ctor_name} 생성자 시그니처와 맞지 않습니다. 버전을 확인하세요.")

    def get_embedding_model():
        """Returns the embeddings instance (if available), or a dummy."""
        global _EMB
        if _EMB is not None:
            return _EMB
        
        # Determine the model name based on priority:
        # 1. RAG_EMBEDDING_MODEL (Universal override)
        # 2. OPENAI_EMBEDDING_MODEL or GEMINI_EMBEDDING_MODEL (Provider specific)
        # 3. Provider Default

        rag_model_override = os.getenv("RAG_EMBEDDING_MODEL")
        
        # 1. Load env vars, defaults, and API keys based on Provider
        if LLM_PROVIDER == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
            organization = os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")
            provider_model_name = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
            EmbCtor_name = "OpenAIEmbeddings"

        elif LLM_PROVIDER == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            base_url = organization = None
            provider_model_name = os.getenv("GEMINI_EMBEDDING_MODEL", "models/embedding-001")
            EmbCtor_name = "GoogleGenerativeAIEmbeddings"
        
        # 2. Final model name determination
        model_name = rag_model_override or provider_model_name
        
        logger.info(
            "[Embeddings] provider=%s | Model=%s (Override: %s)", 
            LLM_PROVIDER, model_name, "Yes" if rag_model_override else "No"
        )
        
        # 3. Construct kwargs and call constructor
        if EmbCtor is not None:
            if LLM_PROVIDER == "openai":
                kwargs_list = [
                    dict(api_key=api_key, base_url=base_url, organization=organization),
                    dict(openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization),
                    dict(),
                ]
                kwargs_list = [{**kw, 'model': model_name} for kw in kwargs_list]

            elif LLM_PROVIDER == "gemini":
                # Gemini Embeddings requires the model argument
                kwargs_list = [
                    dict(model=model_name, api_key=api_key),
                    dict(model=model_name),
                ]

            for kw in kwargs_list:
                try:
                    _EMB = cast(Callable[..., Any], EmbCtor)(**kw)
                    logger.info("[Embeddings] %s ready (Provider: %s)", EmbCtor_name, LLM_PROVIDER)
                    return _EMB
                except Exception as e:
                    logger.debug("[Embeddings] %s ctor failed: %s", EmbCtor_name, e)
        
        # Fallback: Dummy
        class _DummyEmbeddings:
            def embed_query(self, text: str): return [0.0]
            def embed_documents(self, texts): return [[0.0] for _ in texts]
        _EMB = _DummyEmbeddings()
        logger.warning("[Embeddings] Provider Embeddings unavailable → using DummyEmbeddings")
        return _EMB

    def reset_llm() -> None:
        """For testing/reset: clears the cache."""
        global _LLM, _EMB
        _LLM = None
        _EMB = None
        logger.debug("[LLM] reset")

    __all__ = ["get_llm", "get_embedding_model", "reset_llm", "LLM_PROVIDER"]
