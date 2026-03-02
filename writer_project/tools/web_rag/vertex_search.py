# tools/web_rag/vertex_search.py

from typing import Dict, Any, List
import os

import requests

from google import genai
from google.genai.types import (
    GenerateContentConfig,
    GoogleSearch,
    HttpOptions,
    Tool,
)


def _build_client() -> genai.Client:
    """
    .env 설정 기반 Vertex AI 클라이언트 생성.

    필수 환경변수:
      - GCP_PROJECT_ID
      - GCP_REGION (없으면 기본값 us-central1 사용)
      - GOOGLE_APPLICATION_CREDENTIALS (service_account_vertex.json 경로)
    """
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
        http_options=HttpOptions(api_version="v1"),
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

    # 3) grounding 메타에서 URL 추출
    urls: List[str] = []

    try:
        candidates = getattr(response, "candidates", []) or []
        if candidates:
            candidate = candidates[0]
            grounding_md = getattr(candidate, "grounding_metadata", None)

            if grounding_md and getattr(grounding_md, "grounding_chunks", None):
                for chunk in grounding_md.grounding_chunks:
                    web = getattr(chunk, "web", None)
                    uri = getattr(web, "uri", None) if web else None
                    if uri:
                        urls.append(uri)
    except Exception:
        # 구조 변경 등으로 인해 grounding 을 못 읽어도 전체 실패는 막는다.
        pass

    # 🔹 Vertex grounding redirect URL → 실제 URL로 치환
    resolved: List[str] = []
    for u in urls:
        resolved.append(_resolve_vertex_redirect(u))

    # 중복 제거 (순서 유지)
    urls = list(dict.fromkeys(resolved))

    return {
        "summary": summary_text,
        "urls": urls,
        "raw_response": response,
    }