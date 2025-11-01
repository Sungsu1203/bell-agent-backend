from __future__ import annotations
from typing import Any, Callable, Optional, cast

import logging
logger = logging.getLogger(__name__)

# Config 일원화 (동적 접근)
import core.config as config

# Vertex SDK는 지연 임포트로 전환(초기 실패로 전체 중단 방지)
# from google.cloud import aiplatform  # ← 즉시 임포트 제거

_PROVIDER = (getattr(config.CFG, "LLM_PROVIDER", "openai") or "openai").strip().lower()

_LLM: Any = None
_EMB: Any = None

def _mask(v: Optional[str]) -> str:
    """민감 값 로깅용 마스킹."""
    if not v:
        return ""
    if len(v) <= 6:
        return "*" * len(v)
    return v[:3] + "…" + v[-2:]


# CFG에서 GCP 설정값을 가져옵니다. (Vertex AI용)
GCP_PROJECT_ID = (getattr(config.CFG, "GCP_PROJECT_ID", "your-gcp-project-id") or "").strip().lower()
GCP_REGION = getattr(config.CFG, "GCP_REGION", "asia-northeast3")

# ─────────────────────────────────────────────────────────────────────────────
# LLM 공급자별 조건부 임포트 및 설정
# ─────────────────────────────────────────────────────────────────────────────

ChatCtor: Optional[Callable[..., Any]] = None
EmbCtor: Optional[Callable[..., Any]] = None
DefaultChatModel: str = ""
DefaultEmbedModel: str = ""
EmbModelKey: str = ""
ChatModelKey: str = ""
APIKeyName: str = ""

_import_error: Optional[ImportError] = None

# --- OpenAI 설정 ---
if _PROVIDER == "openai":
    ChatModelKey = "OPENAI_MODEL"
    EmbModelKey = "OPENAI_EMBEDDING_MODEL"
    APIKeyName = "OPENAI_API_KEY"
    DefaultChatModel = "gpt-4o"
    DefaultEmbedModel = "text-embedding-ada-002"

    try:
        from langchain_openai import ChatOpenAI as _ChatOpenAI
        from langchain_openai import OpenAIEmbeddings as _OpenAIEmbeddings
        ChatCtor = cast(Callable[..., Any], _ChatOpenAI)
        EmbCtor = cast(Callable[..., Any], _OpenAIEmbeddings)
    except Exception as e:
        raise ImportError(
            "OpenAI LLM/Embeddings import failed: `pip install langchain-openai` is required."
        ) from e

# --- Gemini 설정 ---
elif _PROVIDER == "gemini":
    ChatModelKey = "GEMINI_MODEL"
    EmbModelKey = "GEMINI_EMBEDDING_MODEL"
    APIKeyName = "GEMINI_API_KEY"
    DefaultChatModel = "gemini-2.5-pro"
    DefaultEmbedModel = "text-embedding-004"

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI as _ChatGemini
        from langchain_google_genai import GoogleGenerativeAIEmbeddings as _EmbedGemini
        ChatCtor = cast(Callable[..., Any], _ChatGemini)
        EmbCtor = cast(Callable[..., Any], _EmbedGemini)
    except Exception as e:
        raise ImportError(
            "Gemini LLM/Embeddings import failed: `pip install langchain-google-genai` is required."
        ) from e

# --- Vertex AI 설정 (새로 추가) ---
elif _PROVIDER == "vertexai":
    # Vertex AI는 서비스 계정 인증(ADC)을 사용하므로 API Key가 필요 없습니다.
    ChatModelKey = "LLM_MODEL"  # LLM_MODEL 환경 변수를 사용하도록 통일
    EmbModelKey = "GEMINI_EMBEDDING_MODEL"
    APIKeyName = ""  # 키 불필요
    DefaultChatModel = "gemini-2.5-flash"  # 기본 모델을 Flash로 지정
    DefaultEmbedModel = "text-embedding-004"

    try:
        # (선택) aiplatform은 실제 호출 시점에만 로드(설치 누락 시 초기 중단 방지)
        try:
            from google.cloud import aiplatform  # noqa: F401
        except Exception:
            aiplatform = None  # type: ignore

        # langchain-google-vertexai를 사용
        from langchain_google_vertexai import ChatVertexAI as _ChatVertexAI
        from langchain_google_vertexai import VertexAIEmbeddings as _VertexAIEmbeddings

        # Vertex 경로에서만 timeout/request_timeout 및 불필요 키 제거
        def _strip_kwargs_for_vertex(ctor):
            def _wrapped(**kw):
                # langchain-google-vertexai ChatVertexAI는 timeout 인자를 받지 않음
                for k in ("timeout", "request_timeout"):
                    if k in kw:
                        kw.pop(k, None)
                # 공통 경로에서 들어올 수 있는 불필요 키 방어
                for k in ("api_key", "base_url", "organization", "max_retries"):
                    kw.pop(k, None)
                return ctor(**kw)
            return _wrapped

        ChatCtor = cast(Callable[..., Any], _strip_kwargs_for_vertex(_ChatVertexAI))
        EmbCtor = cast(Callable[..., Any], _VertexAIEmbeddings)
    except Exception as e:
        raise ImportError(
            "Vertex AI LLM/Embeddings import failed. "
            "Install: `pip install google-cloud-aiplatform langchain-google-vertexai`"
        ) from e
# -----------------------------------------------------------------------------

# ─────────────────────────────────────────────────────────────────────────────
# TEST-ONLY FAST PATH: 가벼운 Fake Chat/Embeddings (기존 로직 유지)
# ─────────────────────────────────────────────────────────────────────────────
if getattr(config.CFG, "BLOCKAGI_TEST_FAKE_LLM", False):
    try:
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
        responses = ["ok", "ack", "noted"]
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
# 실제 실행 경로: 선택된 LLM 공급자 로딩 (OpenAI/Gemini/Vertex AI)
# ─────────────────────────────────────────────────────────────────────────────
else:
    # --- LLM (Chat Model) 로딩 함수 ---

    def _build_openai_kwargs(
        m: str, temp: float, api_key: Optional[str], base_url: Optional[str], organization: Optional[str], extra: dict
    ) -> list[dict]:
        """OpenAI용 신/구 파라미터 스타일 후보 kwargs."""
        return [
            # 신 스타일
            dict(model=m, temperature=temp, api_key=api_key, base_url=base_url, organization=organization, **extra),
            dict(model=m, temperature=temp, **extra),
            # 구 스타일 (하위 호환)
            dict(model_name=m, temperature=temp,
                 openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization, **extra),
            dict(model_name=m, temperature=temp, **extra),
        ]

    def _build_gemini_kwargs(
        m: str, temp: float, api_key: Optional[str], extra: dict
    ) -> list[dict]:
        """Gemini용 파라미터 스타일 후보 kwargs."""
        return [
            dict(model=m, temperature=temp, api_key=api_key, **extra),
            dict(model=m, temperature=temp, **extra),
        ]

    def _build_vertexai_kwargs(
        m: str, temp: float, extra: dict
    ) -> list[dict]:
        """Vertex AI용 파라미터 스타일 후보 kwargs."""
        return [
            dict(model=m, temperature=temp, project=GCP_PROJECT_ID, location=GCP_REGION, **extra),
            dict(model=m, temperature=temp, **extra),  # project/location 미지정 폴백
        ]

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

        # 모델명: 직접 인자 > config.CFG 지정 > 기본값
        m = model or getattr(config.CFG, ChatModelKey, None) or DefaultChatModel

        # API 키 로딩: 직접 인자 > config.CFG > None
        api_key = api_key or (getattr(config.CFG, APIKeyName, None) if APIKeyName else None)

        # OpenAI 전용 변수 로딩
        if _PROVIDER == "openai":
            base_url = (
                base_url
                or getattr(config.CFG, "OPENAI_BASE_URL", None)
                or getattr(config.CFG, "OPENAI_API_BASE", None)
            )
            organization = (
                organization
                or getattr(config.CFG, "OPENAI_ORG_ID", None)
                or getattr(config.CFG, "OPENAI_ORGANIZATION", None)
            )

        # 공통 추가 옵션 로딩
        extra: dict = {}
        # (request_timeout 및 max_retries: config.CFG에서 읽음)
        rt = getattr(config.CFG, "OPENAI_REQUEST_TIMEOUT", None)
        mr = getattr(config.CFG, "OPENAI_MAX_RETRIES", None)
        if isinstance(rt, (int, float)) and rt > 0:
            extra["timeout"] = float(rt)
        if isinstance(mr, int) and mr >= 0:
            extra["max_retries"] = mr

        # 로깅: 민감 정보 마스킹 및 공급자별 정보만 표시
        if _PROVIDER == "openai":
            log_msg = f"base_url={_mask(base_url)} | org={_mask(organization)}"
        elif _PROVIDER == "vertexai":  # Vertex AI는 project/region만 표기
            log_msg = f"project={GCP_PROJECT_ID} | region={GCP_REGION}"
        else:
            log_msg = ""

        logger.info(
            "[LLM] init provider=%s | model=%s | %s | temp=%.2f",
            _PROVIDER, m, log_msg, temperature
        )

        def _try_ctor(**kw):
            if ChatCtor is None:
                raise RuntimeError("ChatCtor is None. This indicates an internal logic error or incomplete import.")
            try:
                return ChatCtor(**kw)
            except TypeError as e:
                logger.debug("[LLM] ctor failed (TypeError) with %s: %s", list(kw.keys()), e)
                return None
            except Exception as e:
                logger.debug("[LLM] ctor failed with %s: %s", list(kw.keys()), e)
                raise

        # 후보 kwargs 순차 시도
        if _PROVIDER == "openai":
            kwargs_candidates = _build_openai_kwargs(m, temperature, api_key, base_url, organization, extra)
        elif _PROVIDER == "gemini":
            kwargs_candidates = _build_gemini_kwargs(m, temperature, api_key, extra)
        elif _PROVIDER == "vertexai":
            kwargs_candidates = _build_vertexai_kwargs(m, temperature, extra)
        else:
            kwargs_candidates = []

        for kw in kwargs_candidates:
            try:
                inst = _try_ctor(**kw)
                if inst is not None:
                    _LLM = inst
                    logger.info("[LLM] ready (provider=%s)", _PROVIDER)
                    return _LLM
            except Exception:
                raise

        if not api_key and _PROVIDER in {"openai", "gemini"}:
            logger.error("%s_API_KEY 미설정: 환경변수 또는 get_llm(api_key=...)로 제공 필요", _PROVIDER.upper())
            raise RuntimeError(f"{_PROVIDER.upper()}_API_KEY가 설정되지 않았습니다.")

        ctor_name = getattr(ChatCtor, '__name__', 'UnknownChatCtor')
        logger.error("%s 생성자 시그니처 불일치. LangChain/Provider 라이브러리 버전 확인 필요", ctor_name)
        raise RuntimeError(f"{ctor_name} 생성자 시그니처와 맞지 않습니다. 버전을 확인하세요.")

    # --- Embeddings Model 로딩 함수 ---

    def get_embedding_model():
        """선택된 공급자의 Embeddings 인스턴스를 싱글턴으로 반환. 실패 시 더미로 폴백."""
        global _EMB

        # 1) 싱글턴 캐시
        if _EMB is not None:
            return _EMB

        # 2) 모델 이름 결정 (RAG_EMBEDDING_MODEL > Provider Specific > Default)
        rag_model_override = (getattr(config.CFG, "RAG_EMBEDDING_MODEL", "") or "").strip()
        if rag_model_override:
            model_name = rag_model_override
            is_override = True
        else:
            model_name = getattr(config.CFG, EmbModelKey, None) or DefaultEmbedModel
            is_override = False

        # 3) API 키 로딩
        api_key = (getattr(config.CFG, APIKeyName, None) if APIKeyName else None)

        # 4) 로딩 시도 로깅
        logger.info(
            "[Embeddings] provider=%s | Model=%s (Override: %s)",
            _PROVIDER, model_name, "Yes" if is_override else "No"
        )

        # 5) 생성자 시도 및 예외 처리
        if EmbCtor is not None:
            kwargs_list = []

            if _PROVIDER == "openai":
                base_url = getattr(config.CFG, "OPENAI_BASE_URL", None) or getattr(config.CFG, "OPENAI_API_BASE", None)
                organization = getattr(config.CFG, "OPENAI_ORG_ID", None) or getattr(config.CFG, "OPENAI_ORGANIZATION", None)
                kwargs_list = [
                    dict(model=model_name, api_key=api_key, base_url=base_url, organization=organization),
                    dict(model_name=model_name, openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization),
                    dict(model=model_name),
                ]
            elif _PROVIDER == "gemini":
                kwargs_list = [
                    dict(model=model_name, api_key=api_key),
                    dict(model=model_name),
                ]
            elif _PROVIDER == "vertexai":
                kwargs_list = [
                    dict(model_name=model_name, project=GCP_PROJECT_ID, location=GCP_REGION),
                    dict(model_name=model_name),  # 폴백1
                    dict(model=model_name),       # 폴백2 (버전 차 호환)
                ]

            for kw in kwargs_list:
                try:
                    inst = EmbCtor(**kw)
                    if inst is not None:
                        _EMB = inst
                        logger.info("[Embeddings] ready (provider=%s)", _PROVIDER)
                        return _EMB
                except Exception as e:
                    logger.debug("[Embeddings] ctor failed with %s: %s", list(kw.keys()), e)
                    emsg = str(e).lower()
                    if 'api key' in emsg or 'credentials' in emsg or 'invalid_argument' in emsg:
                        logger.error("[Embeddings] Fatal API Key/Credentials Error: %s", e)
                        raise RuntimeError(f"Embedding model construction failed due to credentials: {e}") from e

        # 6) 폴백: 더미
        class _DummyEmbeddings:
            def embed_query(self, text: str): return [0.0]
            def embed_documents(self, texts): return [[0.0] for _ in texts]

        _EMB = _DummyEmbeddings()
        logger.warning("[Embeddings] Provider Embeddings unavailable → using DummyEmbeddings")
        return _EMB

    # --- Reset 및 Export ---

    def reset_llm() -> None:
        """테스트/재설정용: 캐시 초기화."""
        global _LLM, _EMB
        _LLM = None
        _EMB = None
        logger.debug("[LLM] reset")

    __all__ = ["get_llm", "get_embedding_model", "reset_llm"]
