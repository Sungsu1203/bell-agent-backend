# tools/sanity_check_gemini_embedding.py
import os
from dotenv import load_dotenv

# 운영과 동일한 로딩 순서: 루트 .env (GCP 인증, 프로바이더) → 토픽 .env (override)
load_dotenv(".env")
load_dotenv("topics/height-growth-supplement.env", override=True)

# 인증/프로젝트 설정 확인 (디버그)
print(f"[debug] GOOGLE_APPLICATION_CREDENTIALS={os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
print(f"[debug] GCP_PROJECT_ID={os.environ.get('GCP_PROJECT_ID')}")
print(f"[debug] GCP_REGION={os.environ.get('GCP_REGION')}")
print()

from langchain_google_vertexai import VertexAIEmbeddings

project = os.environ.get("GCP_PROJECT_ID")
location = os.environ.get("GCP_REGION", "us-central1")

# 현 운영 모델 (reference)
ref = VertexAIEmbeddings(
    model="text-multilingual-embedding-002",
    project=project,
    location=location,
)
v_ref = ref.embed_query("키 크는 영양제")
print(f"text-multilingual-embedding-002: dim={len(v_ref)}")

# 평가 대상
try:
    tgt = VertexAIEmbeddings(
        model="gemini-embedding-001",
        project=project,
        location=location,
    )
    v_tgt = tgt.embed_query("키 크는 영양제")
    print(f"gemini-embedding-001: dim={len(v_tgt)}")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")