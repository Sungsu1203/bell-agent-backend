# 개발자 가이드 (Bell Agent · writer_project)

이 문서는 `writer_project` 백엔드의 RAG 파이프라인 작업 시 알아야 할
구조·관습·운영 노하우를 정리합니다.

---

## 1) 폴더 구조 & 의존 규칙
```
D:\GPT_AGENT\writer_project
│
├─ app.py                    # FastAPI 서버 진입점 (StreamingResponse 기반)
├─ graph.py                  # LangGraph 그래프 정의 (StateGraph 노드 토글)
├─ prompts.py                # LLM 프롬프트 템플릿 모음
├─ report_builder.py         # outline → 섹션 조립, 보고서 빌드
├─ rag_expression.py         # 자연어 명령 파싱 (outline 생성/표시, 새 토픽 등)
├─ content_utils.py          # 섹션 콘텐츠 헬퍼 (slug, 경로 탐색)
├─ settings_gatekeep.py      # gatekeep 정책 (도메인 화이트/블랙리스트)
├─ debug_docid.py            # doc_id 검증 디버그 도구
│
├─ agent/                    # LangGraph 노드 (각 파일 = 노드 함수)
│   ├─ supervisor.py             # 라우팅 슈퍼바이저
│   ├─ communicator.py           # 사용자 응답/Direct QA
│   ├─ content_strategist.py     # outline/전략 결정
│   ├─ research_planner.py       # 검색 쿼리 설계
│   ├─ research_synthesizer.py   # 검색 결과 종합
│   ├─ web_search.py             # 웹 검색 노드
│   ├─ vector_search.py          # RAG 검색 노드
│   ├─ section_writer.py         # 섹션 작성
│   └─ chapter_writer.py         # 챕터 작성
│
├─ core/                     # 공통 인프라 (설정·타입·라우팅)
│   ├─ config.py                 # ENV 단일화 (CFG dataclass)
│   ├─ llm.py                    # LLM/임베딩 모델 팩토리
│   ├─ models.py                 # Task 등 도메인 모델
│   ├─ paths.py                  # 출력 경로/파일명 규칙
│   ├─ routers.py                # LangGraph 분기 함수
│   ├─ state_io.py               # state 직렬화/저장
│   ├─ state_types.py            # State, DocMode 타입
│   └─ topic.py                  # 토픽 컨텍스트 로더
│
├─ tools/                    # 외부 I/O & 인덱싱 도구
│   ├─ web_rag/                  # 웹 검색/수집/임베딩 (패키지)
│   │   ├─ __init__.py               # 외부 공개 API (web_search, retrieve, …)
│   │   ├─ ingest.py                 # PDF/HTML 로더, 5단계 fetch 폴백
│   │   ├─ ingest_docs.py            # web.json/검색결과 → Document 변환
│   │   ├─ ingest_vector.py          # Chroma 인덱싱/검색 본체, 임베딩
│   │   ├─ ingest_net.py             # HTTP 세션, fetch
│   │   ├─ ingest_config.py          # ENV 헬퍼 (_cfg_str/_cfg_int/_cfg_bool)
│   │   ├─ search.py                 # 웹 검색 백엔드 (Naver, Tavily 등)
│   │   ├─ utils.py                  # URL 정규화, 텍스트 가드 (_looks_like_*)
│   │   └─ vertex_search.py          # ⚠ Vertex AI Vector Search 시도 흔적
│   ├─ local_rag.py              # 로컬 파일(.pdf/.pptx/.xlsx) 인제스트
│   ├─ topic_config.py           # 토픽별 설정 로더 (도메인 가중치, XLSX 키워드)
│   ├─ metrics.py                # 메트릭 수집
│   ├─ diagnose_embeddings.py    # 임베딩/NS 진단 (운영 도구)
│   └─ diagnose_chunks_deep.py   # 인덱스 청크 분포 진단 (운영 도구)
│
├─ utils/                    # 공용 헬퍼 (순수 유틸, 외부 I/O 없음)
│   ├─ sanitize.py               # state 정제 (sanitize_state, as_int)
│   ├─ rag_utils.py              # RAG 유틸 (merge_refs, is_qa_like 등)
│   ├─ query_filters.py          # 쿼리 필터링/정제
│   ├─ outline.py                # outline 텍스트 헬퍼
│   ├─ text_utils.py             # plain_snip, slugify 등
│   ├─ refs.py                   # 레퍼런스 데이터 처리
│   ├─ ref_format.py             # 레퍼런스 출력 포맷
│   ├─ tasks.py                  # 메시지/태스크 (HumanMessage 등)
│   ├─ writer_scheduler.py       # writer 스케줄링
│   └─ forced_queries.py         # 강제 쿼리 보정
│
├─ topics/                   # 토픽별 프리셋
│   ├─ _template.env                # 새 토픽용 ENV 템플릿
│   ├─ _example.config.json         # 새 토픽용 JSON 템플릿
│   ├─ height-growth-supplement.env # 토픽 ENV
│   └─ pet-food-premium.env
│
├─ tests/                    # 단위/회귀 테스트
│   ├─ test_communicator_direct_qa.py
│   ├─ test_local_docid_stability.py
│   ├─ test_local_source_stability.py
│   ├─ test_domain_bonus_compat.py     # 도메인 가중치 외부화 회귀
│   ├─ test_xlsx_score_compat.py       # XLSX 키워드 외부화 회귀
│   └─ test_garbled_detection.py       # 깨진 바이너리 검출 검증
│
├─ data/chroma_store/        # 벡터 인덱스 (NS 별 디렉토리)
├─ refs/                     # 회사 자료 (xlsx/pptx/docx) — 로컬 RAG 소스
├─ local/                    # 토픽별 로컬 자료 (md 등)
├─ reports/, outlines/       # 산출물
├─ chapters/, sections/      # 챕터/섹션별 작업물
├─ content/                  # 콘텐츠 빌드 모듈 (api 등)
├─ research/                 # 리서치 산출물
├─ resources/, safe_code/    # 보조 자료/안전 코드 보관
├─ state/                    # 세션 상태 직렬화
└─ logs/                     # 로그 파일

```
의존 방향(순환 금지):
```
utils → tools → agent
        ↑       │
        └── core┘   # core는 설정·타입·라우팅만 제공
```
- `agent/*` ↔ `agent/*` 직접 import 금지 (라우팅은 `core/routers.py`)
- `tools/*`는 `utils/*`와 `core.config`만 참조
- `tools/web_rag/*` 내부 모듈끼리는 지연 import로 순환 회피 (예: `ingest_docs.py` → `tools.web_rag.ingest`은 함수 안에서 import)

---

## 2) 환경변수 단일화

모든 ENV는 `core/config.py`(`CFG` dataclass)와 `tools/web_rag/ingest_config.py`(`_cfg_*` 헬퍼)에서 파싱.

핵심 변수 그룹:

**LLM/임베딩**
- `LLM_PROVIDER` (vertexai/gemini/openai)
- `LLM_MODEL`, `GEMINI_EMBEDDING_MODEL`, `RAG_EMBEDDING_MODEL`
- `GCP_PROJECT_ID`, `GCP_REGION`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `ALLOW_DUMMY_EMBEDDINGS` (기본 0; opt-in 시 더미 폴백 허용 — 프로덕션 비권장)

**노드 토글** (`graph.py`에서 사용)
- `ENABLE_COMMUNICATOR`, `ENABLE_CONTENT_STRATEGIST`
- `ENABLE_VECTOR_SEARCH`, `ENABLE_WEB_SEARCH`
- `ENABLE_CHAPTER_WRITER`

**RAG 청킹/검색**
- `RAG_CHUNK_CHARS=2400`, `RAG_CHUNK_OVERLAP=150`
- `RAG_DISTANCE_THRESHOLD=0.65` (글로벌 default; pet-food-premium은 `topics/<slug>.env`에서 0.60 override)
- `RAG_TOP_K`, `RETRIEVE_WEB_RATIO`, `MERGE_RETRIEVE_MODE`
- `MIN_CHUNK_CHARS`, `MIN_CHUNK_PPTX`, `MIN_CHUNK_PDF` (코드 기본 80)

**Chroma 컬렉션**
- `CHROMA_NAMESPACE_WEB`, `CHROMA_NAMESPACE_LOCAL` (둘 다 설정 시 split mode)
- `CHROMA_INCLUDE_BASE`
- `CLEAR_CHROMA_ON_START`, `CLEAR_ON_FIRST_VECTOR`

**웹 PDF (보수적)** vs **로컬 PDF (적극적)**
- 웹: `WEB_PDF_MAX_PAGES=5`, `WEB_PDF_MAX_CHARS=10000`
- 로컬: `LOCAL_RAG_PDF_MAX_PAGES=50`, `LOCAL_RAG_MIN_CHARS`
- 의도된 분업: 웹은 잘 모르는 출처 보수적, 로컬은 회사 신뢰 자료

**도메인 필터** (`settings_gatekeep.py` + `tools/web_rag/utils.py`)
- `FILTER_BAD_DOMAINS` — 검색 시 제외할 호스트 (substring 매칭)
- `GATE_KEEP_SOURCES`, `ALLOWED_DOMAINS`

**규칙:**
- 다른 모듈에서 `os.getenv` 직접 호출 금지 → `from core.config import CFG` 또는 동적 접근 헬퍼 사용
- 토픽별 오버라이드: `topics/<slug>.env`로 자동 로드

---

## 3) RAG 파이프라인 그림

**[수집] → [변환] → [인덱싱]**

```
URL/web.json/refs    →   ingest_docs           →   ingest_vector
  • web_search           • web_results_to_doc      • split_documents (2400/150)
  • local_rag            • PDF: PyPDF2 → pdfminer  • 콘텐츠별 최소 길이 필터
  • findings (자기참조)   • HTML: BeautifulSoup     • PPTX 인접 슬라이드 병합
                         • 5단계 fetch 폴백        • XLSX 메타 요약 자동 생성
                         • source+version 중복 검사
                                                   • Vertex AI text-multilingual-embedding-002 (한국어 최적화)
                                                     (768d, RETRIEVAL_DOCUMENT)
                                                   • Chroma 3-tier (web/local/base)
```

**[검색] (`agent/vector_search.py`)**

```
- 스모크 테스트 (인덱스 동작 확인)
- Direct QA 게이트 (점수 ≥0.35 즉시 답변)
- 웹/로컬 비율 분배 (RETRIEVE_WEB_RATIO=0.5)
- 도메인 가중치 재랭킹 (topic_config.py)
- Chroma fast-path (embed_query, RETRIEVAL_QUERY)
- bad_domains 필터, distance threshold
- 무조건 base 폴백 (0-hit 방지)
```

**[드롭 필터] (인덱싱 전 체크)**

```
- _is_block_page          (CAPTCHA, 차단 페이지)
- _looks_like_pdf_bytes   (PDF 매직 넘버)
- _looks_like_serialized_blob  (React/Next.js JSON blob)
- _looks_like_garbled (★) (디코딩 깨진 바이너리)
```

★ `_looks_like_garbled`: 한국식 바이너리 파일 (.hwp, .xlsx)이 HTML로 잘못 분류되어 깨진 텍스트로 인덱싱되는 것을 방지. U+FFFD 비율 1% 초과 시 드롭. 기준 데이터: 정상 0%, 깨진 텍스트 40~50%.

---

## 4) 공개 API(파사드)만 사용

- **`tools/web_rag/__init__.py`**: 외부에서는 이 파사드만 사용
  - `web_search()` — 웹 검색 (Naver/Tavily 등 백엔드 통합)
  - `retrieve()` — 벡터 검색 (Chroma 컬렉션 RAG 검색)
  - `web_results_to_documents()`, `web_page_json_to_documents()`
  - `documents_to_chroma()`, `add_web_pages_json_to_chroma()`
  - `clear_vector_store()`, `ensure_vector_store_cleared_once()`
- **`tools/topic_config.py`**: 토픽별 설정
  - `get_domain_bonus_groups()`, `get_xlsx_keyword_groups()`
- **`utils/rag_utils.py`**: URL 정규화·디듀프·`merge_refs()` 단일 구현
- **`utils/writer_scheduler.py`**: `schedule_writer_if_needed()` 단일 진입
- 라우팅 분기는 **`core/routers.py`**에서만

내부 모듈 (`tools/web_rag/ingest*.py`)을 직접 import하지 마세요. 파사드를 통해서만.

---

## 5) 공통 타입/시그니처

- `DocMode = Literal["report", "book"]` (`core/state_types.py`)
- `coerce_doc_mode(x) -> DocMode`는 반드시 DocMode 리터럴 반환 (문자열 그대로 반환 금지)
- 웹 검색: `web_search(query: str, **kwargs) -> list[dict]`
- 벡터 검색: `retrieve(query: str, *, top_k: int = 5, namespace: str | None, persist_directory: str | None, embedding=None) -> list[Document]`
- 병합: `merge_refs(existing: dict | None, new_queries: list[str] | None, new_docs: list | None) -> dict`

---

## 6) 임베딩 안전망 (중요)

`core/llm.py`의 `get_embedding_model()` 동작:

- **기본**: ctor 실패 시 `RuntimeError` raise (fail-fast)
- **opt-in**: `ALLOW_DUMMY_EMBEDDINGS=1` 설정 시에만 더미(1차원 0벡터) 폴백
- **이유**: 더미 폴백을 조용히 허용하면 인덱스가 0벡터로 오염되어 알아차리기 어려움. 실패가 명확해야 함.

opt-in 사용 시 `logger.error`로 강한 경고. 프로덕션에서는 절대 켜지 마세요.

---

## 7) 토픽별 설정 외부화

새 토픽 추가 시 코드 수정 없이 다음 두 파일로 설정:

**`topics/<slug>.env`** — 환경변수 (`TOPIC_SLUG`, `LOCAL_RAG_GLOBS`, `BLOCKAGI_OBJECTIVE_*`, …)
- 템플릿: `topics/_template.env` 참고

**`topics/<slug>.config.json`** (선택) — 도메인 가중치/키워드:
```json
{
  "domain_bonus": {
    "groups": [
      {"name": "local", "score": 1.5, "match": "file_protocol"},
      {"name": "trusted_industry_media", "score": 1.0,
       "hosts": ["example-trusted.com"]},
      {"name": "penalties", "score": -0.5,
       "hosts": ["example-noisy.com"]}
    ]
  },
  "xlsx_keywords": {
    "primary_metric": {"score": 3, "keywords": ["매출", "판매", "revenue"]},
    "category": {"score": 2, "keywords": ["카테고리", "분류"]}
  }
}
```
- 템플릿: `topics/_example.config.json` 참고
- 설정 파일이 없거나 특정 키가 비어있으면 `tools/topic_config.py`의 코드 기본값을 사용 (호환 유지).

---

## 8) 진단 도구

운영 중 인덱스 상태/품질을 점검할 때:

**`tools/diagnose_embeddings.py`** — 임베딩 모델 + NS별 검색 동작 확인
```powershell
python tools\diagnose_embeddings.py
```
- 현재 임베딩 클래스(`VertexAIEmbeddings` 등) 확인
- 768차원 정상 여부
- 각 NS의 청크 수 + 샘플 검색 distance

**`tools/diagnose_chunks_deep.py`** — 인덱스 청크 분포 심층 진단
```powershell
python tools\diagnose_chunks_deep.py
```
- 콘텐츠 타입별 비율 (html/pdf/pptx/xlsx)
- 콘텐츠 타입별 길이 분포
- PDF/전체 출처 호스트 top
- **새 토픽 인덱싱 후 한 번 돌려보면 노이즈 발견 가능**

언제 사용?
- 검색 품질이 떨어진다고 느낄 때
- 새 토픽을 처음 인덱싱한 후
- `_looks_like_garbled` 외 다른 노이즈 패턴 의심 시
- 도메인 분포가 한쪽 호스트에 쏠려있는지 확인

---

## 9) 데이터 품질 운영 노하우

**경험적으로 발견한 노이즈 패턴들:**

- **HWP 파일** (`.hwp`): 한국 학교/공공기관에서 흔함. PyPDF2도 pdfminer도 못 읽음. HTML로 잘못 분류돼 깨진 텍스트로 인덱싱되는 사례 발견 (`bomun.gen.hs.kr`, `ildong.gen.es.kr`, `sobo112.or.kr`).
- **이벤트/광고 페이지**: 쇼핑몰 도메인 (`eventimg.auction.co.kr` 등)이 검색에 잡히는 경우. xlsx 분류 미스로 깨진 텍스트 들어옴.
- **글로벌 시장 리포트 사이트**: `gminsights.com`, `mordorintelligence.kr`, `fortunebusinessinsights.com` 등은 본문이 거의 없는 SEO 페이지가 많음. `FILTER_BAD_DOMAINS`에 후보.

**대응 전략:**

1. **새 토픽 인덱싱 후 즉시 진단** (`diagnose_chunks_deep.py`)
2. **호스트별 청크 수 확인** — 단일 호스트가 인덱스의 50% 이상이면 의심
3. **샘플 텍스트 확인** — 깨진 인코딩(`�`, Greek 문자)이 보이면 `_looks_like_garbled`가 잡고 있는지 확인. 빠진 패턴이면 임계값 조정 또는 새 필터 추가
4. **`FILTER_BAD_DOMAINS` 업데이트** — 발견된 노이즈 호스트 추가 (`.env`)
5. **인덱스 재빌드 (선택)** — 기존 오염 청크를 물리적으로 제거하려면 `CLEAR_CHROMA_ON_START=1` + 재인제스트

**`.env`는 git에 안 올라감** (시크릿 + 개별 환경 의존). 다른 환경/머신으로 옮길 때는 `env_raw.txt` 참고하여 따로 구성.

---

## 10) 코드 품질 가드

- pre-commit: Ruff(포맷/심플리파이/정렬), Mypy(타입), Pytest(스모크) 묶기
- Deptry(의존성 누락/미사용), Radon(복잡도), Vulture(데드 코드) 권장
- `tests/` 디렉토리에 단위/회귀 테스트 모음

**현재 테스트 커버리지:**
- `test_communicator_direct_qa.py` — Direct QA 동작
- `test_local_docid_stability.py` — 로컬 doc_id 안정성
- `test_local_source_stability.py` — 로컬 source 안정성
- `test_domain_bonus_compat.py` — 도메인 가중치 외부화 회귀 (13 cases)
- `test_xlsx_score_compat.py` — XLSX 키워드 외부화 회귀 (29 cases)
- `test_garbled_detection.py` — 깨진 바이너리 검출 (9 cases)

---

## 11) PR 운영 순서(권장)

1. **config 통합 & import 규칙 강제** (`core.config` 외 `os.getenv` 금지)
2. **`tools/web_rag` 파사드 사용** & 내부 모듈 직접 import 제거
3. **`utils/rag_utils` 통합** (정규화/디듀프/merge_refs 단일 구현)
4. **`writer_scheduler` 단일화** (`schedule_writer_if_needed`만 사용)
5. **routers 가드 정리 & 순환 제거**
6. **토픽별 설정 외부화** (`topics/<slug>.config.json`)
7. **데이터 품질 가드 추가** (`_looks_like_*` 류, 도메인 필터)
8. **deprecated API 제거**

---

## 12) 알려진 후속 후보

코드 워크스루 중 발견된 개선 후보 (우선순위 순):

1. **메타데이터 풍부화** — `published_date`, `language` 추가 시 시간 가중치/언어 필터 가능
2. **distance threshold 재튜닝 절차** — 현재값: 글로벌 0.65, pet-food-premium 0.60 (text-multilingual-embedding-002 기준). 새 토픽 추가 시 `tools/diagnose_distance_threshold.py`로 분포 측정 후 절벽 직전 값 선택. 임베딩 모델 변경 시 재튜닝 필수.
3. **Vertex AI grounded search 운영** — `tools/web_rag/vertex_search.py`는 살아있는 기능 모듈로 `SKIP_VERTEX_SEARCH` 토글로 제어됨. 한국어 자료는 Naver/Tavily로 충분하고 Vertex 호출 시 대기 시간이 길어 현재 비활성 (`SKIP_VERTEX_SEARCH=1`). 그러나 영어 자료(글로벌 시장 리포트 등)에서는 커버리지를 보강하는 효과가 있어, **영어 자료 위주 토픽은 `topics/<slug>.env`에서 `SKIP_VERTEX_SEARCH=0`으로 오버라이드** 권장. Vertex 결과는 Naver/Tavily 결과에 추가되는 augmentation 형태 (`agent/web_search.py:745` 참조).
4. **`VertexAIEmbeddings` deprecation 모니터링** — `core/llm.py:404`에서 두 종류 deprecation warning 발생:
   - `LangChainDeprecationWarning`: 4.0에서 제거 예정, `langchain-google-genai`의 `GoogleGenerativeAIEmbeddings` 권고
   - `DeprecationWarning` (vertexai 패키지 측): 같은 권고
   
   현재 운영 상태:
   - 패키지 `langchain-google-vertexai` 3.2.2는 maintained 상태로 살아 있음 (deprecate된 건 그 안의 `VertexAIEmbeddings` 클래스).
   - 3.2.2 시점에서 `VertexAIEmbeddings` 내부는 이미 `google.genai.Client` SDK를 백엔드로 사용. 즉 권고 따라 옮겨도 백엔드는 동일.
   
   **마이그레이션은 보류**. 과거 시도 시 회귀 발생 이력:
   - `text-embedding-004`로 갔을 때 한국어 짧은 쿼리 임베딩 품질 부족 → `text-multilingual-embedding-002`(Vertex)로 회귀 (`data/chroma_store_backup_pre_multilingual/`이 그 흔적). `CLEAR_CHROMA_ON_START=1`로는 정합성 있게 비워지지 않아 디스크 직접 삭제로 처리한 이력.
   - GenAI API key 직접 인증 시 동작 실패 → service_account.json 기반 ADC로 회귀.
   
   다음 작업 후보 (LangChain 4.0 출시 전):
   - (a) `gemini-embedding-001`(3072d) 한국어 짧은 쿼리 품질 사전 평가 — `text-embedding-004`와 다른 모델이므로 별도 검증 필요.
   - (b) ADC 인증 유지하면서 `langchain-google-genai` 패키지로의 import 교체만 시도 — 인증 변수를 고정해서 모델/패키지 변수만 분리 평가.
   - (c) deprecation warning suppress (filterwarnings) — 임시방편.
   
   Chroma는 `langchain-chroma` 1.0.0으로 마이그레이션 완료 (commit 172c004), retrieve fallback 경로의 distance/bad_domains 필터 일관성도 함께 정리됨 (commit 4c14430).

   **(a) 1차 시도 (진행 중, 데이터 오염으로 중단)**

   환경 검증 통과 후 평가 진입했으나, 평가 대상 토픽의 인덱스 오염으로 의미 있는 측정 불가. 평가 자체는 다음 세션에서 검증된 토픽으로 재개.

   *환경 검증 통과 사항:*
   - `VertexAIEmbeddings(model="gemini-embedding-001", project=..., location=...)` 호출 정상 (dim=3072 확인). `text-multilingual-embedding-002`도 동일 경로로 768d 확인. 두 모델 모두 ADC 인증 + Vertex 경로로 호출 가능.
   - 운영 `core/llm.py:386-399`의 `kwargs_list` 폴백 패턴 확인: `model_name=` 첫 시도 → `model_name=`(기본값) → `model=` 폴백. `langchain-google-vertexai` 3.2.2 기준 `model_name`은 deprecated alias이므로 **첫 시도 → `model=` 우선으로 순서 뒤집기 cleanup 후보** (동작 변화 없음).
   - 운영 Chroma store collection name 규칙: store 디렉토리 이름과 동일 (예: `<slug>-web/` → collection `<slug>-web`). langchain-chroma 기본값 `"langchain"` 아님 → 평가 스크립트에서 `collection_name=` 명시 필수.
   - 운영 `_dual_retrieve` 흐름 (`agent/vector_search.py:390`): `{slug}-web`/`{slug}-local` 두 NS만 사용 (통합 store는 `CHROMA_INCLUDE_BASE=False` 디폴트로 미사용). 평가 설계 = 층위 1 (각 store 내부) + 층위 2 (web+local 통합) 둘 다 산출.

   *사전 가설 박제 (결과 보기 전):*
   - `gap_ratio` (TGT/REF) ≥ 1.3× **AND** top-1 Δ ≥ +5%p → 마이그레이션 가치 있음
   - 미만 → §12-4 결론 "보류 유지"
   (계산 정의: `gap = irrelevant.median - relevant.median`. 코사인 distance 기준.)

   *중단 사유 — 평가 대상 토픽 인덱스 오염:*
   - **height-growth-supplement**: local 12개 청크가 광고 운영 제안서로 100% 오염 (CPA/LMS/매체 전략 등, 키성장 영양제 토픽과 무관). web 85개 중 `seoul.co.kr` 34개(40%) + `greened.kr` 15개(18%)가 한 페이지에서 다중 청크화돼 있고, `seoul.co.kr` 내용은 부동산/쿠팡/메르스 기사 등 토픽 외 ~40% 오염 추정.
   - 이 인덱스로 평가하면 "도메인 다른 텍스트 분리"를 재는 것이 되어 한국어 단문 retrieval 변별력 측정으로서 무의미.

   *다음 세션 시작점:*
   - 권장 = **pet-food-premium으로 (a) 평가 재개**. 검증된 인덱스 (median 0.410/p95 0.618, fast path 분포 안정). 평가 절차/스크립트는 토픽 슬러그 변경만으로 재사용 가능.
   - 산출물 (commit 포함): `tools/sanity_check_gemini_embedding.py`, `tools/sample_chunks_for_eval.py`, `tools/eval_embedding_models.py`, `eval/goldset/<slug>/README.md`.
   - height 오염은 별도 작업 후보로 박제 (아래 신설 §12-N 또는 별도 절 참조 — ingest 큐레이션 점검 + GATE_KEEP_SOURCES 적용 검토).

   **(a) 2차 시도 (2026-05-04, venfobel-vitamin 토픽)**

   토픽 변경 사유: pet-food-premium 대신 종근당 광고기획 작업이 들어와서 venfobel-vitamin으로 진입.

   *인덱스 구축 결과 — 깨끗 + 풍성*:
   - `data/chroma_store/venfobel-vitamin-{web,local}/`
   - web 8 청크, local 349 청크, 합계 357 청크
   - 청크 통계: avg 651자, p50 754자, p90 1144자
   - source 분포: xlsx 190, pptx 78, pdf 50, md 43 (local) + dailypharm·hankyung·khidi·krx (web 일부)
   - 광고대행사 보유 자료(refs/1. 벤포벨/, 종근당_*.pdf) + 우리 보강 .md 6개(시장규모·OTC 광고 규제·활성형 B1·3강 라인업·광고 크리에이티브·Consumer)

   *본 세션 인프라 패치 (commit 누적)*:
   - commit 99692c6: refs/ 광고기획 자료 일괄 추가 (15 files, 1183 insertions)
   - commit 10295ee: topics/venfobel-vitamin.env OBJ 5개 정의 (3C+Consumer+전략 시사점)
   - commit d296f5c: oauth_client_info.json 무력화 + .gitignore 패치 (§12-11-7 참조)
   - commit 6ddf20b: feat(web_search): inject objectives into prompt (§12-11-1 fix)
   - .env: ALLOWED_DOMAINS 38→50 확장 (의약 매체 9 + 광고 매체 4)
   - .env: LOCAL_RAG_GLOBS에 .md, .docx 패턴 추가 (§12-10 정정 결과)

   *(a) 평가 진입 직전 상태*:
   - 환경 검증: VertexAIEmbeddings(text-multilingual-embedding-002) dim=768 정상 호출 확인
   - 평가 도구 4개는 commit a731f2f 시점에 height-growth-supplement로 하드코딩 → venfobel용 적응 필요 (3개 파일에서 TOPIC_SLUG 한 줄씩 수정)
   - 평가 흐름: sanity_check → sample_chunks → 골드셋 작성(정성, 30~60분) → eval 실행
   - 골드셋 형식: chunks_sampled.jsonl, store별 15~20개씩, 작성 가이드는 eval/goldset/height-growth-supplement/README.md 참조

   *다음 세션 시작점*:
   1. tools/sample_chunks_for_eval.py L26, tools/eval_embedding_models.py L40, tools/sanity_check_gemini_embedding.py L8 — 3개 파일에서 `TOPIC_SLUG = "height-growth-supplement"` → `"venfobel-vitamin"` 변경
   2. `python tools/sanity_check_gemini_embedding.py` (두 모델 dim 확인)
   3. `python tools/sample_chunks_for_eval.py` → eval/goldset/venfobel-vitamin/chunks_sampled.jsonl 생성
   4. 골드셋 작성 (정성 작업, 30~60분)
   5. `python tools/eval_embedding_models.py` → eval/results/venfobel-vitamin_gemini_vs_multilingual.md
   6. 사전 가설 판정(gap 1.3x AND top-1 +5%p) → §12-4-B 박제

5. **VertexAIEmbeddings lazy validation 보강** — ctor는 통과하지만 첫 호출 시 인증 에러 가능. 그 시점 처리
6. **BM25 키워드 검색 보강** — 정확 매칭(제품명, 회사명) 약한 부분 보완
7. ~~**HWP 파일 읽기 지원**~~ — 보류 (회사 자료 0개, 외부 HWP는 노이즈 위주). 재검토 조건: 회사가 HWP 자료 도입 시
8. **백업 파일 정리** — `agent/supervisor.py.bak`, `agent/supervisor.py.broken`, `requirements_vertex.txt.bak` 등 git tracked 백업이 있다면 정리 검토
9. **`CLEAR_CHROMA_ON_START` 메커니즘 개선** — 현재는 vector_search 노드 진입 시 발동하는 늦은 청소. 임베딩 모델 변경 같은 큰 작업에는 부족 (web_search ingest 단계에서 이미 옛 인덱스에 새 청크 추가됨). 디스크 직접 삭제로 우회. 향후 app.py 시작 즉시 청소되도록 메커니즘 옮기기 검토.
10. **ingest 큐레이션 점검 (height-growth-supplement 사례)** — height-growth-supplement 토픽 인덱스에서 토픽 외 콘텐츠가 다량 적재된 사례 발견. local store 100% 오염(광고 운영 제안서), web store ~40% 오염(`seoul.co.kr` 검색결과 페이지가 다중 청크화). 원인 추정: `GATE_KEEP_SOURCES` 미적용 상태에서 supervisor 자동 web seeding 진행 (베이스 화이트리스트 17개 도메인 미적용). 점검 항목:
    - 토픽 .env에 `GATE_KEEP_SOURCES=1` 명시 의무화 검토
    - local store ingest 경로 추적 (refs 폴더는 운영 ingest 파이프라인이 자동으로 읽지 않음 — `refs/`는 LangGraph state 키와 무관한 너 작업용 raw 폴더)
    - 다중 청크화된 단일 페이지(seoul.co.kr 패턴) 차단 휴리스틱 검토 (한 source당 청크 상한)
    - 별도 세션 권장.

    **정정 메모 (2026-05-04, venfobel-vitamin 작업 중 발견)**:
    - 위 박제 중 "refs 폴더는 운영 ingest 파이프라인이 자동으로 읽지 않음" — **부정확**.
    - 실제 동작: `agent/web_search.py:1235`에서 `ingest_local_files()` 자동 호출 (`LOCAL_RAG_GLOBS` 환경변수 읽음, 토픽별 1회 가드, vector handoff 자동 주입).
    - height 작업 시점의 진짜 원인 추정: `LOCAL_RAG_GLOBS=refs/**/*.pdf,refs/**/*.pptx,refs/**/*.xlsx`에 .md/.docx 패턴 누락 → .docx로 저장된 광고대행사 자료, .md 형식 보강 자료 적재 누락.
    - 본 세션 패치: `LOCAL_RAG_GLOBS`에 `,refs/**/*.md,refs/**/*.docx` 추가 (글로벌 .env).
    - height 오염 재해석: "광고 운영 제안서로 100% 오염" 박제는 web side 관찰일 가능성 — local side는 실제로 빈 상태였을 가능성 있음. height 토픽 인덱스가 남아있다면 source 분포 재확인 필요.

11. **§12-N — venfobel-vitamin 작업 발견 사항 (2026-05-04)**

    11-1. **web_search prompt에 OBJ 미주입 (해결됨, commit 6ddf20b)**
    - 증상: web seeding 시 LLM이 `BLOCKAGI_OBJECTIVE_*` 무시하고 일반론 쿼리만 생성. 1차 실행 시 토픽 제목 + mission 텍스트 기반 추상 쿼리 2개만 만들어짐.
    - 진단: `prompts.py:173 get_web_search_prompt()` PromptTemplate vars에 `objectives` 누락. `agent/web_search.py` inputs dict에도 OBJ 주입 없음.
    - 해결: `get_web_search_prompt()`에 `{objectives}` 변수 + 규칙 6,7 추가. `agent/web_search.py`에 `config.load_research_objectives_from_env()` 호출 + inputs dict 주입. (research_synthesizer와 동일 패턴 재사용)
    - 효과 검증: 재실행 시 정밀 쿼리 생성 (IQVIA, 오쏘몰, 아로나민, 임팩타민 등 OBJ 키워드 포함).

    11-2. **MAX_SEARCH_QUERIES_PER_ROUND 미스터리 cap=2 (미해결)**
    - 증상: .env 어디에도 명시 없는데 런타임 `CFG.MAX_SEARCH_QUERIES_PER_ROUND=2`.
    - 코드 디폴트 충돌: `agent/web_search.py:333` 디폴트 3, `core/config.py:501` 디폴트 6, 실제 2.
    - 가설: LLM이 OBJ 5개를 2개 쿼리에 압축해서 자연 종료(cap 미발동) vs hidden config override.
    - 다음 세션: `_env_int` 구현 추적, setup 스크립트 또는 미발견 .env 파일 점검.

    11-3. **의약 매체 fetch 실패 (외부 이슈)**
    - `dailypharm.com` → SSL blacklist (`oldm.dailypharm.com` 호스트로 접근됨)
    - `hitnews.co.kr` → HTTP 404
    - `kpanews.co.kr` → HTTP 404
    - GATEKEEP 통과해도 본문 수집 단계 실패 → 인덱스 적재 안 됨.
    - 다음 트랙: `tools/web_rag/ingest_net.py`의 fetch 재시도 로직 + SSL 검증 옵션.

    11-4. **호스트 정규화 누락 — oldm.dailypharm.com**
    - 화이트리스트의 `dailypharm.com`은 `oldm.dailypharm.com` 등 subdomain prefix 호스트와 별개로 인식.
    - 다음 트랙: `tools/web_rag/search.py` GATEKEEP 단계에 subdomain stripping 또는 suffix 매칭.

    11-5. **화이트리스트 확장 효과 제한 (38→50)**
    - 증상: 의약 매체 9개 + 광고 매체 4개 추가했지만 web 청크 0→8로 미증.
    - 원인: URL 자체 죽음(§12-11-3) + backend 다양화 부재(naver_direct + tavily만).
    - 다음 트랙: backend 추가 + fetch 재시도(§12-11-3 연계) + 호스트 정규화(§12-11-4 연계).

    11-6. **dual_retrieve web≠0일 때 정상 작동 (본 세션 확인)**
    - 지난 박제: web=0일 때 local fallback 안 함 의심 → 본 세션 web≠0 케이스로 검증.
    - smoke hit 로그 확인 (`q=일반의약품 종합비타민... → [데일리팜] | oldm.dailypharm.com`).
    - 미해결: web=0 케이스의 fallback은 여전히 미검증 (이번 세션 web≠0이라 못 봄).

    11-7. **oauth_client_info.json client_secret 노출 사고 (처리 완료)**
    - 발견: `git ls-files | Select-String "service_account|credentials|\.json$"` 결과 oauth_client_info.json이 추적 중.
    - 노출 commit: `3fce3e6` "update codes" — github.com/Sungsu1203/bell-agent-backend (Public 레포)에 push되어 외부 노출.
    - 자격증명 내용: project_id=`gemini-rag-project-new` (현재 vertex 운영 프로젝트 `gemini-rag-search-final`과 별개), client_id=`1068404894813-...`, client_secret 포함.
    - 사용처 확인: 본 시스템 코드에서 import 없음 → dead credential.
    - 처리: Cloud Console gemini-rag-project-new에서 OAuth client (Gemini-RAG-ADC) Delete → 노출된 secret 영구 무력화.
    - working tree 정리: oauth_client_info.json 삭제 + .gitignore에 추가 (commit d296f5c).
    - 미완 트랙: git history scrub via `git filter-repo --path oauth_client_info.json --invert-paths` (다음 push 전 별도 트랙). secret 무력화 완료이므로 history 정리는 위생 차원.

---

## 13) 알려진 이슈/주의사항

**PowerShell 인코딩 설정**: 모든 소스 파일은 UTF-8로 저장되어 있음. PowerShell의 `Get-Content` 등은 기본적으로 시스템 로케일(CP949)로 읽어서 한글이 깨져 보일 수 있음. `$PROFILE`에 다음 추가 권장:

```powershell
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null
$PSDefaultParameterValues['Get-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Out-File:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'UTF8'
$PSDefaultParameterValues['Add-Content:Encoding'] = 'UTF8'
```

**가상환경 다중 존재**: 프로젝트 루트(`D:\GPT_AGENT`)에 `.venv_lcl`, `.venv_vertex`, `venv` 세 개의 가상환경이 있음. 현재는 `.venv_vertex`(Vertex AI 통합용) 사용 중.

**`tools/web_rag/vertex_search.py`**: Vertex AI **grounded search** 모듈. 현재 `SKIP_VERTEX_SEARCH=1`로 비활성. dead code 아님 — 토글 끄고 보존된 기능.

**임베딩 모델 선택**: `text-embedding-004`는 짧은 한국어 query에 사실상 같은 벡터를 반환 (cos≈1.0). 한국어 RAG는 반드시 `text-multilingual-embedding-002`를 사용해야 함. `.env`의 `RAG_EMBEDDING_MODEL`로 설정. 모델 변경 시 인덱스 재빌드 필수 (벡터 공간 다름).

---

© Bell Agent · writer_project — Developer Guide