from __future__ import annotations
import os
from typing import Any, Callable, Optional, cast

import logging
logger = logging.getLogger(__name__)

# Vertex AI SDK import (설치되어 있어야 함: pip install google-cloud-aiplatform)
from google.cloud import aiplatform 

# LLM 공급자 이름 (환경 변수로 설정: 'openai' 또는 'gemini')
_PROVIDER = (os.getenv("LLM_PROVIDER") or "openai").strip().lower()

_LLM: Any = None
_EMB: Any = None

def _mask(v: Optional[str]) -> str:
    """민감 값 로깅용 마스킹."""
    if not v:
        return ""
    if len(v) <= 6:
        return "*" * len(v)
    return v[:3] + "…" + v[-2:]


# 환경 변수에서 GCP 설정값을 가져옵니다. (Vertex AI용)
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "your-gcp-project-id") # .env에서 설정한 프로젝트 ID
GCP_REGION = os.getenv("GCP_REGION", "asia-northeast3") # .env에서 설정한 리전
# -----------------------------------------------------------------------------

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
        # 💡 예외 체이닝 문법 수정: raise 문에서 from e 사용
        raise ImportError(
            f"OpenAI LLM/Embeddings import failed: `pip install langchain-openai` is required."
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
        # 💡 예외 체이닝 문법 수정: raise 문에서 from e 사용
        raise ImportError(
            f"Gemini LLM/Embeddings import failed: `pip install langchain-google-genai` is required."
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

        # 이 블록 안에서만 필요한 클래스를 불러옵니다.
        from langchain_google_vertexai import ChatVertexAI as _ChatVertexAI 
        from langchain_google_vertexai import VertexAIEmbeddings as _VertexAIEmbeddings
        # 파일 상단에서 이미 import 되었으므로, ChatCtor와 EmbCtor에 직접 할당합니다.
        # import: from langchain_google_genai import ChatVertexAI, VertexAIEmbeddings 
        ChatCtor = cast(Callable[..., Any], _ChatVertexAI)
        EmbCtor = cast(Callable[..., Any], _VertexAIEmbeddings)
    except Exception as e:
        raise ImportError(
            f"Vertex AI LLM/Embeddings import failed. Check installation: `pip install google-cloud-aiplatform langchain-google-genai`."
        ) from e
# -----------------------------------------------------------------------------

# ─────────────────────────────────────────────────────────────────────────────
# TEST-ONLY FAST PATH: 가벼운 Fake Chat/Embeddings (기존 로직 유지)
# ─────────────────────────────────────────────────────────────────────────────
if os.getenv("BLOCKAGI_TEST_FAKE_LLM", "0") == "1":
    try:
        # langchain-core 최신계열
        from langchain_core.language_models.fake import FakeListChatModel as _FakeChat    # type: ignore
    except Exception:
        try:
            from langchain_core.language_models.chat_models import FakeListChatModel as _FakeChat    # type: ignore
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
# 실제 실행 경로: 선택된 LLM 공급자 로딩 (OpenAI 또는 Gemini)
# ─────────────────────────────────────────────────────────────────────────────
else:
    # --- LLM (Chat Model) 로딩 함수 ---
    
    def _build_openai_kwargs(
        m: str, temp: float, api_key: Optional[str], base_url: Optional[str], organization: Optional[str], extra: dict
    ) -> list[dict]:
        """OpenAI용 신/구 파라미터 스타일 후보 kwargs를 생성."""
        return [
            # 신(新) 스타일
            dict(model=m, temperature=temp, api_key=api_key, base_url=base_url, organization=organization, **extra),
            dict(model=m, temperature=temp, **extra),
            # 구(舊) 스타일 (하위 호환성)
            dict(model_name=m, temperature=temp, 
                 openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization, **extra),
            dict(model_name=m, temperature=temp, **extra),
        ]

    def _build_gemini_kwargs(
        m: str, temp: float, api_key: Optional[str], extra: dict
    ) -> list[dict]:
        """Gemini용 파라미터 스타일 후보 kwargs를 생성."""
        return [
            # Gemini는 model_name 대신 model을 사용하며, api_key를 명시적으로 받음
            dict(model=m, temperature=temp, api_key=api_key, **extra),
            # API 키가 없으면 환경 변수(GEMINI_API_KEY)를 자동으로 찾도록 시도
            dict(model=m, temperature=temp, **extra), 
        ]
    
    def _build_vertexai_kwargs(
        m: str, temp: float, extra: dict
    ) -> list[dict]:
        """Vertex AI용 파라미터 스타일 후보 kwargs를 생성."""
        # Vertex AI는 project/location 인자를 받으며, ADC(서비스 계정)를 자동으로 사용합니다.
        return [
            dict(
                model=m, 
                temperature=temp, 
                project=GCP_PROJECT_ID, 
                location=GCP_REGION, 
                **extra
            ),
            # project/location이 없어도 자동으로 환경을 찾도록 시도
            dict(model=m, temperature=temp, **extra),
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

        m = model or os.getenv(ChatModelKey, DefaultChatModel)
        
        # API 키 로딩: 직접 전달 > 환경 변수 > None
        api_key = api_key or os.getenv(APIKeyName)
        
        # OpenAI 전용 변수 로딩
        if _PROVIDER == "openai":
            base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
            organization = organization or os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")

        # 공통 추가 옵션 로딩
        extra: dict = {}
        # (request_timeout 및 max_retries 로딩 로직은 기존과 동일)
        request_timeout = os.getenv("OPENAI_REQUEST_TIMEOUT")
        max_retries = os.getenv("OPENAI_MAX_RETRIES")
        if request_timeout:
            try: extra["timeout"] = float(request_timeout)
            except Exception: pass
        if max_retries:
            try: extra["max_retries"] = int(max_retries)
            except Exception: pass
        
        # 로깅: 민감 정보 마스킹 및 공급자별 정보만 표시
        if _PROVIDER == "openai":
            log_msg = f"base_url={_mask(base_url)} | org={_mask(organization)}"
        elif _PROVIDER == "vertexai": # <--- Vertex AI 로직 추가
        # Vertex AI는 project/region을 표시 (키는 ADC로 숨김)
             log_msg = f"project={GCP_PROJECT_ID} | region={GCP_REGION}"
        else:
            log_msg = ""
            
        logger.info(
            "[LLM] init provider=%s | model=%s | %s | temp=%.2f",
            _PROVIDER, m, log_msg, temperature
        )

        def _try_ctor(**kw):
            # 💡 수정 포인트: None 호출 경고를 제거하기 위해 런타임 가드 추가
            if ChatCtor is None:
                # 상단에서 임포트 오류 시 raise 했으므로 이 코드는 정적 분석 경고 제거용
                raise RuntimeError("ChatCtor is None. This indicates an internal logic error or incomplete import.")
            
            try:
                return ChatCtor(**kw)
            except TypeError as e:
                # 시그니처 오류는 디버그로만 기록 (구/신 파라미터 시도 허용)
                logger.debug("[LLM] ctor failed (TypeError) with %s: %s", list(kw.keys()), e)
                return None
            except Exception as e:
                # API 키 오류나 다른 심각한 오류는 여기에서 발생
                logger.debug("[LLM] ctor failed with %s: %s", list(kw.keys()), e)
                raise # 심각한 오류는 즉시 전파

        # 후보 kwargs 순차 시도
        if _PROVIDER == "openai":
            kwargs_candidates = _build_openai_kwargs(m, temperature, api_key, base_url, organization, extra)
        elif _PROVIDER == "gemini":
            kwargs_candidates = _build_gemini_kwargs(m, temperature, api_key, extra)
        elif _PROVIDER == "vertexai": # <--- Vertex AI 로직 추가
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
                # _try_ctor에서 심각한 오류(API 키 등) 발생 시 재시도 루프 중단
                raise


        if not api_key:
            logger.error("%s_API_KEY 미설정: 환경변수 또는 get_llm(api_key=...)로 제공 필요", _PROVIDER.upper())
            raise RuntimeError(f"{_PROVIDER.upper()}_API_KEY가 설정되지 않았습니다.")
        
        # 모든 시도가 TypeError 등으로 실패했을 경우
        ctor_name = getattr(ChatCtor, '__name__', 'UnknownChatCtor')
        logger.error("%s 생성자 시그니처 불일치. LangChain/Provider 라이브러리 버전 확인 필요", ctor_name)
        raise RuntimeError(f"{ctor_name} 생성자 시그니처와 맞지 않습니다. 버전을 확인하세요.")

    # --- Embeddings Model 로딩 함수 ---

    def get_embedding_model():
        """선택된 공급자의 Embeddings 인스턴스를 싱글턴으로 반환. 실패 시 더미로 폴백."""
        global _EMB

        # 1) 싱글턴 캐시 확인
        if _EMB is not None:
            return _EMB

        # 2) 모델 이름 결정 (RAG_EMBEDDING_MODEL > Provider Specific > Default)
        rag_model_override = os.getenv("RAG_EMBEDDING_MODEL")
        if rag_model_override:
            model_name = rag_model_override
            is_override = True
        else:
            model_name = os.getenv(EmbModelKey, DefaultEmbedModel)
            is_override = False

        # 3) API 키 로딩
        api_key = os.getenv(APIKeyName)

        # 4) 로딩 시도 로깅
        logger.info(
            "[Embeddings] provider=%s | Model=%s (Override: %s)",
            _PROVIDER, model_name, "Yes" if is_override else "No"
        )
        
        # 5) 생성자 시도 및 예외 처리
        if EmbCtor is not None:
            kwargs_list = []
            
            # 💡 OpenAI kwargs 빌드
            if _PROVIDER == "openai":
                base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
                organization = os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")
                kwargs_list = [
                    dict(model=model_name, api_key=api_key, base_url=base_url, organization=organization),
                    dict(model_name=model_name, openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization),
                    dict(model=model_name),
                ]
            # 💡 Gemini kwargs 빌드 (API 키 명시적 전달이 중요)
            elif _PROVIDER == "gemini":
                # 🚨 GEMINI 임베딩은 api_key를 명시적으로 받는 것이 안전함 (ADC 문제 우회)
                kwargs_list = [
                    # 키를 명시적으로 전달 (GoogleGenerativeAIEmbeddings 생성자에 api_key 인자가 없으면 Type Error 발생 가능성이 있음)
                    dict(model=model_name, api_key=api_key), 
                    # 키가 없거나 실패 시, 환경 변수 자동 로딩 시도 (Google 라이브러리 기본 동작)
                    dict(model=model_name),
                ]

            # 💡 Vertex AI kwargs 빌드 (새로 추가)
            elif _PROVIDER == "vertexai":
                kwargs_list = [
                    dict(
                        model_name=model_name,
                        project=GCP_PROJECT_ID,
                        location=GCP_REGION,
                    ),
                    dict(model_name=model_name), # 폴백
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
                    # API 키 관련 오류는 여기서 명확히 전파
                    emsg = str(e).lower()
                    if 'api key' in emsg or 'credentials' in emsg or 'invalid_argument' in emsg:
                        logger.error("[Embeddings] Fatal API Key Error during construction: %s", e)
                        raise RuntimeError(f"Embedding model construction failed due to API Key issue: {e}") from e

        # 6) 폴백: 더미
        class _DummyEmbeddings:
            def embed_query(self, text: str): return [0.0]
            def embed_documents(self, texts): return [[0.0] for _ in texts]
        
        _EMB = _DummyEmbeddings()
        logger.warning("[Embeddings] Provider Embeddings unavailable → using DummyEmbeddings")
        return _EMB

    # --- Reset 및 Export ---

    def reset_llm() -> None:
        """테스트/재설정용: 캐시를 초기화."""
        global _LLM, _EMB
        _LLM = None
        _EMB = None
        logger.debug("[LLM] reset")

    __all__ = ["get_llm", "get_embedding_model", "reset_llm"]