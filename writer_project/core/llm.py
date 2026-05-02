from __future__ import annotations
from typing import Any, Callable, Optional, cast

import logging
logger = logging.getLogger(__name__)

# Config 일원화 (동적 접근)
import core.config as config

_LLM: Any | None = None
_EMB: Any = None
_LOADED: dict[str, Any] = {}  # provider별 ctor/기본값 캐시

import os

def _mask(v: Optional[str]) -> str:
    """민감 값 로깅용 마스킹."""
    if not v:
        return ""
    if len(v) <= 6:
        return "*" * len(v)
    return v[:3] + "…" + v[-2:]


def _provider() -> str:
    """실행 시점의 공급자명(소문자)"""
    try:
        return str(getattr(config.CFG, "LLM_PROVIDER", "openai") or "openai").strip().lower()
    except Exception:
        return "openai"

def _gcp_project() -> str:
    try:
        return (getattr(config.CFG, "GCP_PROJECT_ID", "") or "").strip().lower()
    except Exception:
        return ""

def _gcp_region() -> str:
    try:
        return str(getattr(config.CFG, "GCP_REGION", "asia-northeast3"))
    except Exception:
        return "asia-northeast3"

# ─────────────────────────────────────────────────────────────────────────────
# LLM 공급자별 조건부 임포트 및 설정
# ─────────────────────────────────────────────────────────────────────────────

def _load_provider() -> dict[str, Any]:
    """
    공급자별 ctor/키/기본 모델 정보를 지연 로딩하여 반환.
    reload_config() 이후에도 최신 CFG에 맞게 재구성되도록 캐시를 provider key로 분리.
    반환 키: ChatCtor, EmbCtor, ChatModelKey, EmbModelKey, APIKeyName, DefaultChatModel, DefaultEmbedModel
    """
    prov = _provider()
    cached = _LOADED.get(prov)
    if cached:
        return cached

    out: dict[str, Any] = {
        "ChatCtor": None,
        "EmbCtor": None,
        "ChatModelKey": "",
        "EmbModelKey": "",
        "APIKeyName": "",
        "DefaultChatModel": "",
        "DefaultEmbedModel": "",
    }

    if prov == "openai":
        out["ChatModelKey"] = "OPENAI_MODEL"
        out["EmbModelKey"] = "OPENAI_EMBEDDING_MODEL"
        out["APIKeyName"] = "OPENAI_API_KEY"
        out["DefaultChatModel"] = "gpt-4o"
        out["DefaultEmbedModel"] = "text-embedding-ada-002"
        try:
            from langchain_openai import ChatOpenAI as _ChatOpenAI
            from langchain_openai import OpenAIEmbeddings as _OpenAIEmbeddings
            out["ChatCtor"] = cast(Callable[..., Any], _ChatOpenAI)
            out["EmbCtor"]  = cast(Callable[..., Any], _OpenAIEmbeddings)
        except Exception as e:
            logger.debug("OpenAI provider import error: %s", e, exc_info=True)
            # ctor는 None으로 두고, 실제 호출 시 에러를 올림

    elif prov == "gemini":
        out["ChatModelKey"] = "GEMINI_MODEL"
        out["EmbModelKey"]  = "GEMINI_EMBEDDING_MODEL"
        out["APIKeyName"]   = "GEMINI_API_KEY"
        out["DefaultChatModel"] = "gemini-2.5-pro"
        out["DefaultEmbedModel"] = "text-multilingual-embedding-002"
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI as _ChatGemini
            from langchain_google_genai import GoogleGenerativeAIEmbeddings as _EmbedGemini
            out["ChatCtor"] = cast(Callable[..., Any], _ChatGemini)
            out["EmbCtor"]  = cast(Callable[..., Any], _EmbedGemini)
        except Exception as e:
            logger.debug("Gemini provider import error: %s", e, exc_info=True)

    elif prov == "vertexai":
        # Vertex AI는 서비스 계정 인증(ADC)
        out["ChatModelKey"] = "LLM_MODEL"  # 통일
        out["EmbModelKey"]  = "GEMINI_EMBEDDING_MODEL"
        out["APIKeyName"]   = ""  # 키 불필요
        out["DefaultChatModel"]  = "gemini-2.5-flash"
        out["DefaultEmbedModel"] = "text-multilingual-embedding-002"
        try:
            try:
                from google.cloud import aiplatform  # noqa: F401
            except Exception:
                aiplatform = None  # type: ignore
            from langchain_google_vertexai import ChatVertexAI as _ChatVertexAI
            from langchain_google_vertexai import VertexAIEmbeddings as _VertexAIEmbeddings
            def _strip_kwargs_for_vertex(ctor):
                def _wrapped(**kw):
                    for k in ("api_key", "base_url", "organization", "max_retries"):
                        kw.pop(k, None)
                    return ctor(**kw)
                return _wrapped
            out["ChatCtor"] = cast(Callable[..., Any], _strip_kwargs_for_vertex(_ChatVertexAI))
            out["EmbCtor"]  = cast(Callable[..., Any], _VertexAIEmbeddings)
        except Exception as e:
            logger.debug("Vertex provider import error: %s", e, exc_info=True)
    else:
        logger.warning("Unknown LLM_PROVIDER=%s; falling back to openai defaults", prov)

    _LOADED[prov] = out
    return out
# -----------------------------------------------------------------------------

def _test_mode() -> bool:
    try:
        return bool(getattr(config.CFG, "BLOCKAGI_TEST_FAKE_LLM", False))
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# TEST-ONLY FAST PATH: 가벼운 Fake Chat/Embeddings (실행 시점 판정)
# ─────────────────────────────────────────────────────────────────────────────
if _test_mode():
    try:
        from langchain_core.language_models.fake import FakeListChatModel as _FakeChat  # type: ignore
    except Exception:
        try:
            from langchain_core.language_models.chat_models import FakeListChatModel as _FakeChat  # type: ignore
        except Exception:
            from langchain_core.language_models.fake import FakeListLLM as _BaseFake  

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
            from typing import cast, Any
            FakeChatCtor = cast(Any, _FakeChat)  # 시그니처 차이를 정적분석에서 무시
            _LLM = FakeChatCtor(responses=responses)
        except TypeError:
            from typing import cast, Any
            FakeChatCtor = cast(Any, _FakeChat)
            _LLM = FakeChatCtor() 
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

    __all__ = ["get_llm", "get_embedding_model", "reset_llm", "refresh_llm"]

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
        rt = getattr(config.CFG, "VERTEX_REQUEST_TIMEOUT", 120)
        extra_clean = {k: v for k, v in extra.items() if k != "timeout"}
        return [
            dict(model=m, temperature=temp, project=_gcp_project(), location=_gcp_region(), timeout=rt, **extra_clean),
            dict(model=m, temperature=temp, timeout=rt, **extra_clean),
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

        prov = _provider()
        info = _load_provider()
        ChatCtor = info["ChatCtor"]; ChatModelKey = info["ChatModelKey"]
        APIKeyName = info["APIKeyName"]; DefaultChatModel = info["DefaultChatModel"]
        EmbCtor = info.get("EmbCtor")  # 미사용이지만 로더 확보 목적

        if _test_mode():
            # 테스트 모드에서는 FakeChat 경로 사용
            return globals()["get_llm"](model=model, temperature=temperature, api_key=api_key, base_url=base_url, organization=organization)  

        # ctor 없으면 명시 에러
        if ChatCtor is None:
            raise ImportError(f"LLM provider '{prov}' is not available. Please install the corresponding package(s).")

        # 모델명: 직접 인자 > CFG 지정 > 기본값
        m = model or getattr(config.CFG, ChatModelKey, None) or DefaultChatModel

        # API 키 로딩: 직접 인자 > config.CFG > None
        api_key = api_key or (getattr(config.CFG, APIKeyName, None) if APIKeyName else None)

        # OpenAI 전용 변수 로딩
        if prov == "openai":
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
        if prov == "openai":
            log_msg = f"base_url={_mask(base_url)} | org={_mask(organization)}"
        elif prov == "vertexai":  # Vertex AI는 project/region만 표기
            log_msg = f"project={_gcp_project()} | region={_gcp_region()}"
        else:
            log_msg = ""

        logger.info(
            "[LLM] init provider=%s | model=%s | %s | temp=%.2f",
            prov, m, log_msg, temperature
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
        if prov == "openai":
            kwargs_candidates = _build_openai_kwargs(m, temperature, api_key, base_url, organization, extra)
        elif prov == "gemini":
            kwargs_candidates = _build_gemini_kwargs(m, temperature, api_key, extra)
        elif prov == "vertexai":
            kwargs_candidates = _build_vertexai_kwargs(m, temperature, extra)
        else:
            kwargs_candidates = []

        for kw in kwargs_candidates:
            try:
                inst = _try_ctor(**kw)
                if inst is not None:
                    _LLM = inst
                    logger.info("[LLM] ready (provider=%s)", prov)
                    return _LLM
            except Exception:
                raise

        if not api_key and prov in {"openai", "gemini"}:
            logger.error("%s_API_KEY 미설정: 환경변수 또는 get_llm(api_key=...)로 제공 필요", prov.upper())
            raise RuntimeError(f"{prov.upper()}_API_KEY가 설정되지 않았습니다.")

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
        prov = _provider()
        info = _load_provider()
        EmbCtor = info["EmbCtor"]; EmbModelKey = info["EmbModelKey"]
        APIKeyName = info["APIKeyName"]; DefaultEmbedModel = info["DefaultEmbedModel"]

        if _test_mode():
            # 테스트 모드에서는 위의 Fake 경로의 get_embedding_model이 이미 정의되어 있을 수 있음
            pass

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
            prov, model_name, "Yes" if is_override else "No"
        )

        # 5) 생성자 시도 및 예외 처리
        if EmbCtor is not None:
            kwargs_list = []

            if prov == "openai":
                base_url = getattr(config.CFG, "OPENAI_BASE_URL", None) or getattr(config.CFG, "OPENAI_API_BASE", None)
                organization = getattr(config.CFG, "OPENAI_ORG_ID", None) or getattr(config.CFG, "OPENAI_ORGANIZATION", None)
                kwargs_list = [
                    dict(model=model_name, api_key=api_key, base_url=base_url, organization=organization),
                    dict(model_name=model_name, openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization),
                    dict(model=model_name),
                ]
            elif prov == "gemini":
                kwargs_list = [
                    dict(model=model_name, api_key=api_key),
                    dict(model=model_name),
                ]
            elif prov == "vertexai":
                kwargs_list = [
                    dict(model_name=model_name, project=_gcp_project(), location=_gcp_region()),
                    dict(model_name=model_name),  # 폴백1
                    dict(model=model_name),       # 폴백2 (버전 차 호환)
                ]

            for kw in kwargs_list:
                try:
                    inst = EmbCtor(**kw)
                    if inst is not None:
                        _EMB = inst
                        logger.info("[Embeddings] ready (provider=%s)", prov)
                        return _EMB
                except Exception as e:
                    logger.debug("[Embeddings] ctor failed with %s: %s", list(kw.keys()), e)
                    emsg = str(e).lower()
                    if 'api key' in emsg or 'credentials' in emsg or 'invalid_argument' in emsg:
                        logger.error("[Embeddings] Fatal API Key/Credentials Error: %s", e)
                        raise RuntimeError(f"Embedding model construction failed due to credentials: {e}") from e

        # 6) 모든 ctor 시도가 실패한 경우의 처리
        #    기본은 fail-fast (조용한 인덱스 오염 방지).
        #    의도적으로 더미가 필요한 경우(예: 오프라인 점검)에만 ALLOW_DUMMY_EMBEDDINGS=1로 opt-in.
        allow_dummy = (
            bool(getattr(config.CFG, "ALLOW_DUMMY_EMBEDDINGS", False))
            or os.getenv("ALLOW_DUMMY_EMBEDDINGS", "").strip().lower() in {"1", "true", "yes", "on"}
        )

        if not allow_dummy:
            msg = (
                f"[Embeddings] Provider '{prov}' embedding model construction failed for "
                f"model='{model_name}'. Refusing to fall back to DummyEmbeddings "
                f"because ALLOW_DUMMY_EMBEDDINGS is not set. "
                f"This protects the vector index from being silently polluted with "
                f"zero-vectors. To allow dummy embeddings (e.g. for offline tests), "
                f"set ALLOW_DUMMY_EMBEDDINGS=1."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        # opt-in 경로: 강한 경고와 함께 더미 사용
        class _DummyEmbeddings:
            def embed_query(self, text: str): return [0.0]
            def embed_documents(self, texts): return [[0.0] for _ in texts]

        _EMB = _DummyEmbeddings()
        logger.error(
            "[Embeddings] !!! USING DUMMY EMBEDDINGS (ALLOW_DUMMY_EMBEDDINGS=1) !!! "
            "All vectors will be 1-D zero. Any index built in this state is INVALID. "
            "provider=%s model=%s",
            prov, model_name,
        )
        return _EMB

    # --- Reset 및 Export ---

    def reset_llm() -> None:
        """테스트/재설정용: 캐시 초기화."""
        global _LLM, _EMB
        _LLM = None
        _EMB = None
        logger.debug("[LLM] reset")

    def refresh_llm() -> None:  # pragma: no cover
        """reload_config() 이후 provider/ctor 캐시 무효화."""
        global _LOADED
        _LOADED.clear()
        reset_llm()
        logger.debug("[LLM] refresh (providers cleared)")

    __all__ = ["get_llm", "get_embedding_model", "reset_llm", "refresh_llm"]
