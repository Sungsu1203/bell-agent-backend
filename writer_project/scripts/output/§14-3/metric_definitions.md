# §14-3 측정 metric 정의 박제

## 1. vertex_grounding

### 기술적 정의
Google Vertex AI Gemini 모델의 Grounding with Google Search 기능으로
LLM 응답에 부착되는 source citation.

- Gemini 가 응답 생성 시 Google Search 결과를 retrieval augmentation 으로 활용
- 응답 span 별로 어떤 검색 결과 (URL/title/snippet) 가 근거였는지 메타데이터 반환
- Vertex SDK 용어: `grounding_metadata` / `grounding_attributions`
- LangChain ChatVertexAI 의 `additional_kwargs` 또는 `response_metadata` 포함

### writer_project 내 표현
`state.references.docs[i].source == 'vertex_grounding'` 으로 분류된 ref.

### §14-2 Step 1b patch 와의 관계
- patch (5078a2d, agent/web_search.py:766) 가 grounding metadata 파싱 후
  references 에 누적
- patch 전: grounding metadata 가 LLM 응답 부산물로만 존재, references 미누적
- patch 후: source='vertex_grounding' 으로 references.docs 에 append
- §14-3 본 검증 = 이 차이의 본 측정

## 2. web

### 기술적 정의
Naver / Tavily 등 외부 search API 가 명시 호출로 fetch 한 결과.

### vertex_grounding 과의 차이
| 항목 | vertex_grounding | web |
|------|------------------|-----|
| 검색 주체 | Gemini 내부 (Google Search) | 외부 API 명시 호출 |
| 호출 시점 | LLM 응답 생성 중 자동 | web_search 노드 명시 호출 |
| 결과 형태 | grounding_metadata (응답 부산물) | API response → document 변환 |
| Citation 보장 | LLM 실제 사용 source 표시 | retrieval recall 우선 |

## 3. local

ChromaDB local index 에서 retrieve 된 ref.

## 4. other / unknown

- other: 명시적 source 값 있으나 위 3개 외 (예: 'api', 'manual')
- unknown: source 키 자체 부재 / None / 빈 문자열
- robustness 박제 키 (silent 분류 누락 방지)

## §14-3 측정에서의 의의

### Tier 2 dry-run (Step 3) 진입 조건
- `vertex_grounding count > 0` → 해당 토픽에서 Google Search 활용 가능
- 0 → 토픽이 너무 niche 또는 Google Search index 약함, patch 효과 측정 불가

### Phase 3 본 측정 (5078a2d vs 1135ac1)
- patch 전 commit (1135ac1): vertex_grounding count = 0 예상
- patch 후 commit (5078a2d): vertex_grounding count > 0 예상
- 두 commit 간 차이 = patch 의 in-memory references 누적 효과 본 검증

### Phase 3 변동성 분석
- vertex_grounding count 의 N=3 간 CV > 30% → 토픽 unstable
- patch 효과 vs noise 분리 불가 → Tier 1 fallback / 재시도 결정
- T5 (kr-digital-ad-spend-2026-forecast) 의 한국어 grounding 별도 검증
  : Google Search 한국어 corpus 가 영어 대비 grounding metadata 적게 반환 가능
