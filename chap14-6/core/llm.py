# # core/llm.py
# from __future__ import annotations
# import os
# from typing import Any, Callable, Optional, cast

# _LLM: Any = None  # 런타임 캐시

# def get_llm(model: Optional[str] = None, temperature: float = 0.3):
#     """Lazy-import + 싱글턴. 타입체커가 None-call로 오해하지 않도록 cast로 호출 보장."""
#     global _LLM
#     if _LLM is not None:
#         return _LLM

#     m = model or os.getenv("OPENAI_MODEL", "gpt-4o")

#     # 런타임 임포트 (신버전 → 구버전 폴백)
#     try:
#         from langchain_openai import ChatOpenAI  # 최신 경로
#     except Exception:
#         try:
#             from langchain.chat_models import ChatOpenAI  # 구버전 폴백  # type: ignore
#         except Exception as e:
#             raise ImportError(
#                 "ChatOpenAI import 실패. pip install langchain-openai 또는 langchain 버전을 확인하세요."
#             ) from e

#     # 🔑 핵심: 타입체커에게 '이건 호출 가능한 것'이라고 알려주기
#     ChatCtor = cast(Callable[..., Any], ChatOpenAI)
#     _LLM = ChatCtor(model=m, temperature=temperature)
#     return _LLM


# def reset_llm() -> None:
#     """테스트용: 내부 캐시 초기화"""
#     global _LLM
#     _LLM = None

# core/llm.py (대체안)
# from __future__ import annotations
# import os
# from typing import Any, Callable, Optional, cast

# _LLM: Any = None  # 런타임 캐시

# def get_llm(
#     model: Optional[str] = None,
#     temperature: float = 0.3,
#     api_key: Optional[str] = None,
#     base_url: Optional[str] = None,
#     organization: Optional[str] = None,
# ):
#     """
#     Lazy-import + 싱글턴. 환경변수 또는 인자로 키/베이스URL을 받으며,
#     langchain-openai 신/구 버전 생성자 모두 대응.
#     """
#     global _LLM
#     if _LLM is not None:
#         return _LLM

#     m = model or os.getenv("OPENAI_MODEL", "gpt-4o")
#     api_key = api_key or os.getenv("OPENAI_API_KEY")
#     base_url = base_url or os.getenv("OPENAI_BASE_URL")
#     organization = organization or os.getenv("OPENAI_ORG_ID")

#     try:
#         from langchain_openai import ChatOpenAI  # 최신
#     except Exception:
#         try:
#             from langchain.chat_models import ChatOpenAI  # 구버전
#         except Exception as e:
#             raise ImportError(
#                 "ChatOpenAI import 실패. pip install langchain-openai 또는 langchain 버전을 확인하세요."
#             ) from e

#     ChatCtor = cast(Callable[..., Any], ChatOpenAI)

#     def _try(**kw):
#         try:
#             return ChatCtor(**kw)
#         except TypeError:
#             return None

#     # 신버전 시그니처 우선 시도
#     if api_key or base_url or organization:
#         cand = _try(model=m, temperature=temperature,
#                     api_key=api_key, base_url=base_url, organization=organization)
#         if cand is not None:
#             _LLM = cand
#             return _LLM

#     cand = _try(model=m, temperature=temperature)
#     if cand is not None:
#         _LLM = cand
#         return _LLM

#     # 구버전 시그니처 폴백
#     if api_key or base_url or organization:
#         cand = _try(model_name=m, temperature=temperature,
#                     openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization)
#         if cand is not None:
#             _LLM = cand
#             return _LLM

#     cand = _try(model_name=m, temperature=temperature)
#     if cand is not None:
#         _LLM = cand
#         return _LLM

#     # 여기까지 왔다면 보통은 키가 없거나 시그니처가 안 맞는 케이스
#     if not api_key:
#         raise RuntimeError(
#             "OPENAI_API_KEY가 설정되지 않았습니다. 환경변수나 get_llm(api_key=...)로 제공하세요."
#         )
#     raise RuntimeError("ChatOpenAI 생성자 시그니처와 맞지 않습니다. langchain/ langchain-openai 버전을 확인하세요.")


# def reset_llm() -> None:
#     global _LLM
#     _LLM = None

# core/llm.py
# from __future__ import annotations
# import os
# from typing import Any, Callable, Optional, cast

# _LLM: Any = None  # 런타임 캐시

# def _chat_openai_ctor() -> Callable[..., Any]:
#     """
#     ChatOpenAI 생성자를 버전별 경로로 임포트하고,
#     mypy 'redef' 경고가 없도록 별칭으로 묶어 반환.
#     """
#     try:
#         from langchain_openai import ChatOpenAI
#         return cast(Callable[..., Any], _ChatOpenAI)
#     except Exception:
#         try:
#             from langchain.chat_models import ChatOpenAI
#             return cast(Callable[..., Any], _ChatOpenAI)
#         except Exception as e:
#             raise ImportError(
#                 "ChatOpenAI import 실패. `pip install langchain-openai` 또는 langchain 버전을 확인하세요."
#             ) from e
#     ChatCtor = cast(Callable[..., Any], ChatOpenAI)

# def get_llm(
#     model: Optional[str] = None,
#     temperature: float = 0.3,
#     api_key: Optional[str] = None,
#     base_url: Optional[str] = None,
#     organization: Optional[str] = None,
# ) -> Any:
#     """
#     Lazy-import + 싱글턴.
#     - 환경변수/인자 기반 설정 지원: OPENAI_MODEL / OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_ORG_ID
#     - langchain-openai 신/구 생성자 시그니처 모두 폴백 시도
#     """
#     global _LLM
#     if _LLM is not None:
#         return _LLM

#     m = model or os.getenv("OPENAI_MODEL", "gpt-4o")
#     api_key = api_key or os.getenv("OPENAI_API_KEY")
#     # 일부 환경은 OPENAI_API_BASE를 씁니다(호환 위해 둘 다 체크)
#     base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
#     organization = organization or os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")

#     ChatCtor = _chat_openai_ctor()

#     def _try(**kw):
#         try:
#             return ChatCtor(**kw)
#         except TypeError:
#             return None

#     # (1) 신버전 시그니처 우선: model / api_key / base_url / organization
#     if api_key or base_url or organization:
#         inst = _try(model=m, temperature=temperature,
#                     api_key=api_key, base_url=base_url, organization=organization)
#         if inst is not None:
#             _LLM = inst
#             return _LLM

#     # (2) 신버전 기본 시그니처: model만
#     inst = _try(model=m, temperature=temperature)
#     if inst is not None:
#         _LLM = inst
#         return _LLM

#     # (3) 구버전 폴백: model_name / openai_api_key / openai_api_base / openai_organization
#     if api_key or base_url or organization:
#         inst = _try(model_name=m, temperature=temperature,
#                     openai_api_key=api_key, openai_api_base=base_url, openai_organization=organization)
#         if inst is not None:
#             _LLM = inst
#             return _LLM

#     # (4) 구버전 기본 시그니처: model_name만
#     inst = _try(model_name=m, temperature=temperature)
#     if inst is not None:
#         _LLM = inst
#         return _LLM

#     # 여기까지 오면 보통은 키 미설정/시그니처 불일치
#     if not api_key:
#         raise RuntimeError(
#             "OPENAI_API_KEY가 설정되지 않았습니다. 환경변수나 get_llm(api_key=...)로 제공하세요."
#         )
#     raise RuntimeError("ChatOpenAI 생성자 시그니처와 맞지 않습니다. langchain / langchain-openai 버전을 확인하세요.")

# def reset_llm() -> None:
#     """테스트용: 내부 캐시 초기화"""
#     global _LLM
#     _LLM = None


# core/llm.py
from __future__ import annotations
import os
from typing import Any, Callable, Optional, cast

_LLM: Any = None

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

    if api_key or base_url or organization:
        inst = _try(model=m, temperature=temperature,
                    api_key=api_key, base_url=base_url, organization=organization)
        if inst is not None:
            _LLM = inst; return _LLM

    inst = _try(model=m, temperature=temperature)
    if inst is not None:
        _LLM = inst; return _LLM

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
