# tools/web_rag/vertex_search.py

from typing import Dict, Any, List
import os
import logging

import requests

logger = logging.getLogger(__name__)

# google-genai 는 Vertex 전용 의존성. OpenAI 전용 venv(.venv_openai)에는
# 설치되지 않으므로 모듈 import 시점에 깨지지 않도록 try/except 가드를 둔다.
# 실제 호출(_build_client / vertex_web_search) 시점에 미설치면 RuntimeError 또는
# 빈 결과로 graceful degrade 한다 (LLM_PROVIDER=openai 환경 호환).
try:
    from google import genai  # type: ignore
    from google.genai.types import (  # type: ignore
        GenerateContentConfig,
        GoogleSearch,
        HttpOptions,
        Tool,
    )
    _GENAI_AVAILABLE = True
    _GENAI_IMPORT_ERROR = None
except ImportError as _e:  # pragma: no cover
    genai = None  # type: ignore
    GenerateContentConfig = None  # type: ignore
    GoogleSearch = None  # type: ignore
    HttpOptions = None  # type: ignore
    Tool = None  # type: ignore
    _GENAI_AVAILABLE = False
    _GENAI_IMPORT_ERROR = _e


def _build_client() -> Any:
    """
    .env 설정 기반 Vertex AI 클라이언트 생성.

    필수 환경변수:
      - GCP_PROJECT_ID
      - GCP_REGION (없으면 기본값 us-central1 사용)
      - GOOGLE_APPLICATION_CREDENTIALS (service_account_vertex.json 경로)
    """
    if not _GENAI_AVAILABLE:
        raise RuntimeError(
            "google-genai 패키지가 설치되어 있지 않습니다. "
            "Vertex AI 검색을 쓰려면 .venv_vertex 환경을 활성화하거나, "
            "OpenAI venv에서는 SKIP_VERTEX_SEARCH=1 (또는 토픽 프리셋의 "
            "SKIP_VERTEX_SEARCH 값)을 확인해 vertex_web_search 호출을 차단하세요."
        ) from _GENAI_IMPORT_ERROR

    project = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_REGION", "us-central1")

    if not project:
        raise RuntimeError(
            "GCP_PROJECT_ID 환경 변수가 설정되어 있지 않습니다. "
            "(.env 파일과 PowerShell 환경을 확인하세요.)"
        )

    # google-genai 클라이언트 (Vertex AI 경로)
    return genai.Client(
        vertexai=True,              # Vertex AI 사용
        project=project,
        location=location,
        # v1 API 사용 (Vertex AI Search / Grounding 최신 규격)
        http_options=HttpOptions(api_version="v1"),  # type: ignore
    )

def _resolve_vertex_redirect(url: str, timeout: float = 5.0) -> str:
    """
    Vertex AI Search grounding redirect URL
    (https://vertexaisearch.cloud.google.com/grounding-api-redirect/...) 을
    실제 최종 URL로 한 번 따라가서 반환한다.
    실패하면 원본 URL을 그대로 돌려준다.
    """
    if "vertexaisearch.cloud.google.com/grounding-api-redirect" not in url:
        return url

    try:
        # GET 한 번만, 리다이렉트는 자동으로 따라감
        resp = requests.get(url, allow_redirects=True, timeout=timeout)
        # 최종 목적지 URL (리다이렉트 체인 끝)
        return resp.url or url
    except Exception:
        return url

def vertex_web_search(query: str) -> Dict[str, Any]:
    """
    Vertex AI Gemini 2.5 + Google Search grounding 으로 웹 검색을 수행하고,
    요약 텍스트와 URL 리스트를 반환한다.

    반환 형식:
        {
            "summary": str,
            "urls": list[str],
            "raw_response": <GenerateContentResponse 객체>
        }
    """
    # google-genai 미설치(OpenAI venv 등) → 빈 결과로 graceful degrade.
    # 호출자(merge 흐름)는 빈 dict를 정상 처리할 수 있다.
    if not _GENAI_AVAILABLE:
        logger.warning(
            "[vertex_web_search] google-genai 미설치 — 빈 결과 반환 "
            "(LLM_PROVIDER=openai venv 추정). SKIP_VERTEX_SEARCH=1 권장."
        )
        return {"summary": "", "urls": [], "raw_response": None}

    client = _build_client()

    # .env 에서 LLM_MODEL을 읽되, 없으면 gemini-2.5-flash 기본값 사용
    model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")

    # 1) Google Search tool 설정
    config = GenerateContentConfig(
        tools=[
            Tool(
                google_search=GoogleSearch()
            )
        ]
    )

    # 2) 모델 호출
    #   - google-genai는 타입이 꽤 유연하므로, 여기서는 Any 로 취급
    response: Any = client.models.generate_content(
        model=model_name,
        contents=query,
        config=config,
    )

    summary_text: str = getattr(response, "text", "") or ""

    # 3) grounding 메타에서 chunks/supports/web_search_queries 추출
    #    chunks 의 인덱스는 supports.chunk_indices 와 매칭되어야 하므로 dedup 하지 않음.
    #    urls 는 chunks 의 uri 를 redirect-resolve 후 dedup 한 별도 list (기존 호환).
    chunks_out: List[Dict[str, Any]] = []
    supports_out: List[Dict[str, Any]] = []
    web_search_queries: List[str] = []

    try:
        candidates = getattr(response, "candidates", []) or []
        if candidates:
            candidate = candidates[0]
            grounding_md = getattr(candidate, "grounding_metadata", None)

            if grounding_md:
                # 3-1) chunks (원본 인덱스 보존)
                raw_chunks = getattr(grounding_md, "grounding_chunks", None) or []
                for chunk in raw_chunks:
                    web = getattr(chunk, "web", None)
                    if web is None:
                        # image chunk 등은 skip 하되 인덱스 어긋남 방지를 위해 빈 항목 자리 유지
                        chunks_out.append({"uri": "", "title": "", "domain": ""})
                        continue
                    uri = getattr(web, "uri", None) or ""
                    title = getattr(web, "title", None) or ""
                    domain = getattr(web, "domain", None) or ""
                    chunks_out.append({"uri": uri, "title": title, "domain": domain})

                # 3-2) supports (segment ↔ chunk 매핑)
                raw_supports = getattr(grounding_md, "grounding_supports", None) or []
                for sup in raw_supports:
                    seg = getattr(sup, "segment", None)
                    chunk_indices = list(getattr(sup, "grounding_chunk_indices", None) or [])
                    supports_out.append({
                        "chunk_indices": [int(i) for i in chunk_indices],
                        "text": (getattr(seg, "text", "") or "") if seg else "",
                        "start_index": int(getattr(seg, "start_index", 0) or 0) if seg else 0,
                        "end_index": int(getattr(seg, "end_index", 0) or 0) if seg else 0,
                    })

                # 3-3) web_search_queries (Vertex 가 실제 발사한 검색 쿼리들)
                wsq = getattr(grounding_md, "web_search_queries", None) or []
                web_search_queries = [str(q) for q in wsq if q]
    except Exception:
        # 구조 변경 등으로 인해 grounding 을 못 읽어도 전체 실패는 막는다.
        pass

    # 🔹 Vertex grounding redirect URL → 실제 URL로 치환
    #    chunks 의 uri 도 동일하게 resolve 하여 downstream 에서 일관 사용.
    for c in chunks_out:
        if c["uri"]:
            c["uri"] = _resolve_vertex_redirect(c["uri"])

    resolved_urls = [c["uri"] for c in chunks_out if c["uri"]]
    urls = list(dict.fromkeys(resolved_urls))

    return {
        "summary": summary_text,
        "urls": urls,
        "raw_response": response,
        "chunks": chunks_out,
        "supports": supports_out,
        "web_search_queries": web_search_queries,
    }