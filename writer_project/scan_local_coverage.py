# scan_local_coverage.py — 임시, 커밋 안 함
import os
os.environ["TOPIC_SLUG"] = "experiential-marketing-media"
from dotenv import load_dotenv
load_dotenv(".env"); load_dotenv(".env.openai", override=True)

import chromadb
from langchain_openai import OpenAIEmbeddings

PATH = "data/chroma_store/experiential-marketing-media-local"

Q = {
    1:  "정보전달형 광고 경험유발형 브랜드필름",
    2:  "경험 자체를 판매한 브랜드 유튜브 숏폼",
    3:  "5개 모듈 통합 작동 캠페인",
    4:  "사운드 로고 비주얼 아이덴티티 감각",
    5:  "감동 공감 서사형 브랜드 필름",
    6:  "반전 퀴즈 인터랙티브 콘텐츠",
    7:  "참여형 챌린지 UGC 숏폼",
    8:  "팬덤 커뮤니티 브랜드 콜라보",
    9:  "여러 모듈 결합 대형 통합 캠페인",
    10: "숏폼 네이티브 라이브 인터랙티브",
    11: "고객 여정 단계별 설계 참여지표",
    12: "일관된 브랜드 경험 장기 캠페인",
    13: "팝업스토어 브랜드 체험관 phygital",
    15: "AI 가상인간 VR 가상경험",
}

emb = OpenAIEmbeddings(model="text-embedding-3-large")
client = chromadb.PersistentClient(path=PATH)
names = [c.name for c in client.list_collections()]
print("[collections]", names)
col = client.get_collection(names[0])
print("[count]", col.count())

for wk, q in Q.items():
    r = col.query(query_embeddings=[emb.embed_query(q)], n_results=3)
    d = r["distances"][0]
    v = "보유" if d[0] < 1.10 else ("애매" if d[0] < 1.30 else "공백")
    print(f"\n[{wk:>2}주] {v}  top={d[0]:.3f}  | {q}")
    for dist, m in zip(d, r["metadatas"][0]):
        print(f"      {dist:.3f}  {m.get('title','')[:70]}")