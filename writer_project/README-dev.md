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
│   ├─ events.py                 # 사용자 관점 진행 이벤트 버퍼 (frontend LogPanel 헤더용, §12-14)
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
   - 본체: `core.config._load_dotenv_once()` 가 `.env` → `TOPIC_SLUG` → `topics/{slug}.env`(override) 자동 로드. `.env` 의 `TOPIC_SLUG` 한 줄이 단일 스위치.
   - 평가 도구(`tools/sample_chunks_for_eval.py`, `tools/eval_embedding_models.py`, `tools/sanity_check_gemini_embedding.py`)도 같은 부트스트랩 사용 — `core.config.load_topic_env()` 호출 + `TOPIC_SLUG = os.environ["TOPIC_SLUG"]`. 토픽 전환 시 코드 수정 0줄. (2026-05-05 통합)
7. **데이터 품질 가드 추가** (`_looks_like_*` 류, 도메인 필터)
8. **deprecated API 제거**

---

## 12) 알려진 후속 후보

코드 워크스루 중 발견된 개선 후보 (우선순위 순):

1. **메타데이터 풍부화** — `published_date`, `language` 추가 시 시간 가중치/언어 필터 가능
2. **distance threshold 재튜닝 절차** — 현재값: 글로벌 0.65, pet-food-premium 0.60 (text-multilingual-embedding-002 기준). 새 토픽 추가 시 `tools/diagnose_distance_threshold.py`로 분포 측정 후 절벽 직전 값 선택. 임베딩 모델 변경 시 재튜닝 필수.

    **한계 (2026-05-04, §12-12-1 결과로 명시)**: "절벽 직전 값 선택" 절차는 분포에 절벽이 존재한다는 가정에 의존. venfobel-vitamin 토픽에서는 9 포인트 sweep 결과 절벽 자체가 식별 안 됨 (relevant/hardneg 분포 꼬리 중첩, multi-chunk source 81%). 이런 좁은 분포 토픽에서는 본 절차 적용 불가 — 토픽 override 미설정 유지하고 §12-6 (BM25) 같은 다른 mechanism 검토. 상세: `eval/threshold_sweep/CONCLUSION.md`.
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
   - height 오염은 별도 작업 후보로 박제 (아래 신설 §12-N 또는 별도 절 참조 — ingest 큐레이션 점검 + GATE_KEEP_SOURCES 적용 검토). [2026-05-04 정정: §12-N은 §12-12로 채번 확정. 단 height 오염 후속 작업은 §12-12에 포함되지 않았고 §12-10 본문이 후속 트랙 — 별도 §12-N 신설은 미실행.]

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

   **정정 (2026-05-05)**: 위 "3개 파일 한 줄씩 수정"은 `core.config.load_topic_env()` 통합 부트스트랩 도입으로 해소됨. 평가 도구는 이제 `.env` 의 `TOPIC_SLUG` 만 따라간다 — 토픽 전환 시 tools/ 코드 변경 0줄. 자세한 내용은 §7 "토픽별 설정 외부화" 참고.

   *다음 세션 시작점*:
   1. `.env` 에서 `TOPIC_SLUG=<slug>` 만 확인 (현 운영: `venfobel-vitamin`). 평가 도구가 자동으로 따라감.
   2. `python tools/sanity_check_gemini_embedding.py` (두 모델 dim 확인)
   3. `python tools/sample_chunks_for_eval.py` → eval/goldset/venfobel-vitamin/chunks_sampled.jsonl 생성
   4. 골드셋 작성 (정성 작업, 30~60분)
   5. `python tools/eval_embedding_models.py` → eval/results/venfobel-vitamin_gemini_vs_multilingual.md
   6. 사전 가설 판정(gap 1.3x AND top-1 +5%p) → §12-4-B 박제

   **(b) 2차 시도 결과 (2026-05-04, venfobel-vitamin)**

    평가 실행 완료. 사전 가설 판정 + 부가 발견 정리.

    *평가 환경*:
    - 골드셋: eval/goldset/venfobel-vitamin/chunks_sampled.jsonl, 27 청크 중 21개 query 채움 (local 19 + web 2)
    - web n=2로 `MIN_QUERIES_PER_TIER=5` 미달 → tier1_web 자동 스킵, tier1_local + tier2_merged만 산출
    - REF: text-multilingual-embedding-002 (768d), TGT: gemini-embedding-001 (3072d)

    *사전 가설 판정 (tier2_merged 기준)*:

    | 조건 | 임계값 | 측정값 | 통과 |
    | --- | --- | --- | --- |
    | gap_ratio (TGT/REF) | ≥ 1.30× | 0.94× | ❌ |
    | top-1 Δ (TGT−REF) | ≥ +5%p | +14.3%p | ✅ |

    AND 조건 → **fail (보류 유지)**.

    단 fail 사유가 "효과 없음"이 아닌 **"효과 있으나 마이그레이션 ROI 정밀 검증 필요"**. top-1 +14.3%p, MRR +0.074는 retrieval ranking 품질에서 의미 있는 우세이며, gap_ratio < 1.0은 gemini-001의 임베딩 공간 특성(조밀 분포, 변별 폭은 작으나 ranking은 정확)을 드러내는 결과로 해석.

    *tier별 결과*:

    | 층위 | 모델 | gap | top-1 | top-3 | MRR |
    | --- | --- | --- | --- | --- | --- |
    | tier1_local (n=19) | REF | 0.117 | 63.2% | 84.2% | 0.756 |
    | tier1_local (n=19) | TGT | 0.117 | **78.9%** | **89.5%** | **0.840** |
    | tier1_web (n=2) | — | skipped | — | — | — |
    | tier2_merged (n=21) | REF | 0.112 | 57.1% | 81.0% | 0.706 |
    | tier2_merged (n=21) | TGT | 0.106 | **71.4%** | **85.7%** | **0.780** |

    tier1_local은 더 큰 격차(top-1 +15.7%p) — 깨끗한 도메인 내부에서 TGT 우세 분명. tier2_merged 격차가 줄어드는 건 web 청크 2개의 작은 풀이 평균을 흐리는 영향.

    *부가 발견 — 운영 cleanup 후보 박제*:

    1. **OPERATIONAL_THRESHOLD = 0.65 사실상 무의미**. 두 모델 모두 threshold 0.65 적용 시 precision 5% / recall 100% — 골드셋 모든 쌍이 distance < 0.65라 cut-off로 기능 안 함. 이는 모델 비교와 무관한 운영 retrieval 자체의 문제로, 권장 threshold는 분포 기준 ~0.19~0.20 (rel.p75와 hardneg.median 중간). 운영 retrieval이 사실상 cut-off 없이 머지 중. **§12-12-1 작업 큐**로 박제: 운영 threshold 재조정 효과 검증.

    2. **collection_name 명시 누락 silent fail 버그 발견 + 패치**. 1차 시도(commit a731f2f) 평가 도구는 langchain-chroma `Chroma(...)` 호출에 `collection_name=` 미지정 → default `"langchain"` 이름의 빈 collection 자동 생성, 거기서 0건 silent 반환. 2차 시도에서 `collection_name=store_path.name` 명시로 패치. 박제된 1차 환경 검증 메모(§12-4-A 1차 시도)가 정확히 이 케이스를 예고했으나 코드 반영 누락 — **박제 → 코드 동기화 갭의 사례**. 1차 시도가 만든 빈 langchain collection 두 개도 같은 commit에서 cleanup.

    3. **VertexAIEmbeddings deprecation 경고**. `langchain-google-vertexai.VertexAIEmbeddings`는 LangChain 3.2.0에서 deprecated, 4.0.0에서 제거 예정. `langchain-google-genai.GoogleGenerativeAIEmbeddings`로 마이그레이션 권고. 본 평가는 운영 일관성 위해 동일 클래스 유지 — 운영(`core/llm.py`)도 같은 클래스 사용 중. 운영 마이그레이션 시점에 평가도 함께 cleanup. **§12-12-2 작업 큐**.

    4. **`core/llm.py:386-399` kwargs 폴백 순서 cleanup 후보** (§12-4-A 1차 시도에서 박제). `model_name=`(deprecated alias) 첫 시도 → `model=` 폴백 순서를 `model=` 우선으로 뒤집기. 동작 변화 없음. **§12-12-2 작업 큐에 통합**.

    *venfobel 토픽 인덱스 한계 박제*:

    - web 인덱스 8 청크 → 골드셋 web 2 청크 → tier1_web 평가 구조적 불가능
    - height 1차 시도(web 85)와 venfobel 2차 시도(web 8)의 차이는 인덱스 품질이 아닌 양의 차이. 토픽별 평가 진입 가능성 판정 시 web 청크 수가 선결 조건
    - 향후 venfobel web 인덱스 보강(ALLOWED_DOMAINS 50개 활용) 후 재평가는 **§12-12-3 작업 큐**

    *마이그레이션 결정 — 보류 유지*:

    본 평가는 단일 토픽 결과이며, gemini-001의 retrieval 우세는 분명하나:
    - 차원 4배 증가에 따른 인덱스 저장 비용 4배
    - 임베딩 호출 비용 (3072d API 호출)
    - threshold 재조정 필요 (§12-12-1과 연동)
    - 인덱스 재생성 필요

    이 운영 부담을 +14.3%p top-1 / +0.074 MRR로 정당화하려면 **다른 토픽(pet-food-premium 등)에서 동일 평가를 반복하여 결과 일반화 검증**이 선결. **§12-12-4 작업 큐**: pet-food-premium 토픽으로 임베딩 평가 반복.

    *산출물 commit*:
    - 평가 도구 패치: `tools/sample_chunks_for_eval.py` collection_name 명시
    - 빈 langchain collection cleanup: `data/chroma_store/venfobel-vitamin-{local,web}/langchain` 삭제
    - 골드셋: `eval/goldset/venfobel-vitamin/{README.md, chunks_sampled.jsonl}`
    - 결과: `eval/results/venfobel-vitamin_gemini_vs_multilingual.md`
    - topic 적응: tools/{sanity_check_gemini_embedding,sample_chunks_for_eval,eval_embedding_models}.py 슬러그 치환

    *push 보류 유지 사유*:

    origin/main 대비 6 commits ahead (이번 commit 포함). 광고대행사 자료 NDA risk + 골드셋 jsonl이 광고대행사 자료 본문 일부 포함 → push 금지. NDA 정리 끝날 때까지 local commit만 누적. §12-11-7과 동일 정책.

    **해소 (2026-05-05)**: GitHub repo `Sungsu1203/bell-agent-backend` public → **private** 전환 완료(웹 UI Danger Zone). NDA risk가 외부 익명 노출 → repo 권한 보유자 한정 노출로 전환됨에 따라 push 보류 정책 해제. 누적 백로그 25 commits(`a731f2f..1b8c839`) push 완료. 본 시점부터 commit → push 일반 흐름. 단, NDA 자료(refs/, eval/goldset/venfobel-vitamin/) 자체가 repo 안에 있다는 사실은 변하지 않으므로 collaborator 추가 시 NDA 권한 사전 확인 필수.

    *다음 세션 진입점*:
    §12-12 작업 큐(§12-12-1~4) 중 우선순위 결정. 가장 ROI 높은 후보는 §12-12-1 (운영 threshold 재조정 효과 검증) — gemini 마이그레이션과 무관하게 현 운영 retrieval 품질 직접 개선 가능성.

5. **VertexAIEmbeddings lazy validation 보강** — ctor는 통과하지만 첫 호출 시 인증 에러 가능. 그 시점 처리
6. **BM25 키워드 검색 보강** — 정확 매칭(제품명, 회사명) 약한 부분 보완. **우선순위 상향 trigger (2026-05-04, §12-12-1 결과)**: venfobel-vitamin처럼 좁은 도메인 + 임베딩 분포 변별 부족 토픽에서는 distance threshold cut-off가 작동 안 함이 정량 확인됨. BM25 같은 keyword-based mechanism이 보완 가치 큼. 상세: `eval/threshold_sweep/CONCLUSION.md`.
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

11. **§12-11 — venfobel-vitamin 작업 발견 사항 (2026-05-04)**

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
    - **정합성 메모 (2026-05-05)**: §12-4-A 의 push 보류 정책 해소(repo private 전환 + 25 commits push)로 "다음 push 전" 조건은 이미 지나감. dead credential history 는 여전히 commit `3fce3e6` 에 잔존. private 전환으로 외부 익명 접근은 차단됐으나 collaborator 모두에게는 여전히 보임. 위생 차원 scrub 가치는 유지되며 우선순위는 낮음(secret 무력화 + 권한 한정 노출 → 잔여 risk 미미).

---

12. **§12-12 — 운영 retrieval/임베딩 cleanup 큐 (2026-05-04~)**

    **현재 상태 (2026-05-04 세션 close 시점)**: §12-12-1 close 완료. §12-12-2/3/4는 우선순위 하향 — backend mechanism 개선 작업이 backend 위생 layer에 머물러 있고, 사용자 측 동작 검증(리포트 end-to-end 생성, Direct QA 작동, 일반 LLM Q&A 흐름)이 선행되어야 함. 사용자 측 검증에서 retrieval 품질 부족이 실제로 드러나는 시점에 §12-12-2/3/4 또는 §12-6(BM25/cross-encoder reranking) 재진입. 그 전까지 본 큐는 보류.

    **현재 상태 (2026-05-04 사용자측 검증 세션 후)**: 본 세션 미션 B(Direct QA on 벤포벨 인덱스) 정식 통과. 글로벌 0.65 임계 정상 작동 확인 — venfobel-vitamin local 인덱스(349 청크)에서 "벤포벨이 뭐야" 질의 → Ipsos 광고효과조사 PPTX 청크 2건 hit, Direct QA Summary 생성(161자). 단, **임계 경계 진동 정량 관찰**: (a) 동일 청크 `dailypharm.com/user/news/7806`이 query에 따라 0.679 통과 / 0.675 컷으로 진동, (b) `distance=0.650` 정확 일치 케이스가 컷됨 (`> 0.650` strict 비교 추정). 이는 §12-12-1 close 시 명시한 "venfobel-vitamin은 분포 절벽 부재 → 본 절차 적용 불가" 판단과 정합. **override 재진입 결정은 보류 유지**하되, C 미션(end-to-end 리포트) 결과물의 인용 분포에서 0.65 컷이 정성적으로 유의미한 잡음 제거인지 vs 누락 신호인지 추가 평가 후 §12-12-2/3/4 또는 §12-6 재진입 판단.

    출처: §12-4-A (b) 2차 시도(venfobel-vitamin) 평가 부산물로 발견된 운영 정합성 작업 4건. 본 큐는 venfobel 토픽에 종속되지 않으며 글로벌 운영 retrieval/임베딩 품질에 관한 cleanup 항목 모음.

    각 항목 메타 형식: **상태 / 의존 / 차단 사유**
    - 상태: `pending` / `active` / `blocked` / `done`
    - 의존: 선행 작업 또는 외부 조건
    - 차단 사유: blocked일 때만 명시

    12-1. **운영 OPERATIONAL_THRESHOLD 재조정 효과 검증** — 상태: `done (close, 2026-05-04 — 운영 적용 미실시)` / 의존: 없음

    - 발견(§12-4-A (b)): 운영 threshold 0.65에서 venfobel 골드셋 기준 precision 5% / recall 100% — cut-off로 기능 안 함.
    - 사전 가설: τ를 rel.p75와 hardneg.median 중간(~0.20)으로 내리면 retrieval 노이즈 감소 → **결과적으로 정정됨** (산술적 중간이 분리 가능 cut-off 아님).
    - 측정: 산출물 `tools/threshold_sweep.py` (신규) + `eval/threshold_sweep/venfobel-vitamin_sweep.md`. 9 포인트 sweep (0.150~0.300 step 0.025 + baseline 0.60, 0.65), same-source hardneg 보정 ON/OFF 두 결과.
    - 결과 핵심:
      - 절벽 없음 (가장 큰 jump -0.196, CLIFF_MIN_JUMP=0.20 미만)
      - F1 최대 τ=0.150에서도 P=0.591/R=0.619 → recall 38% 손실 대비 precision 개선이 운영 가치 없음
      - 운영 0.65 = 사실상 cut-off 없음 (recall 1.000) 정량 재확인
    - **Close 결론**: venfobel 토픽 분포 특성상 distance threshold cut-off는 retrieval 분리 mechanism으로 부적합. 운영 cut-off 변경하지 않음. 글로벌 default 0.65 + venfobel override 미설정 유지.
    - 상세 박제: `eval/threshold_sweep/CONCLUSION.md` (시나리오 판정, 재진입 조건 R1~R3, 후속 분기).
    - 후속 분기: §12-2 (재튜닝 절차의 한계 명시) + §12-6 (BM25 우선순위 데이터 포인트).
    - 재진입 조건 요약: (R1) 다른 토픽에서 절벽 식별 시 토픽별 override / (R2) 임베딩 모델 변경 시 재측정 / (R3) 골드셋 보강 — 상세는 CONCLUSION.md §6-4.

    12-2. **VertexAIEmbeddings deprecation 마이그레이션 + kwargs 폴백 순서 cleanup** — 상태: `pending` / 의존: LangChain 4.0 출시 동향 / 차단 사유: ROI 우선순위 낮음 + 과거 마이그레이션 회귀 이력(§12-4)

    - 통합 대상 두 건:
      - (a) `langchain-google-vertexai.VertexAIEmbeddings` (LangChain 3.2.0 deprecated, 4.0.0 제거 예정) → `langchain-google-genai.GoogleGenerativeAIEmbeddings` 마이그레이션. 운영(`core/llm.py`) + 평가 도구 동시 cleanup.
      - (b) `core/llm.py:386-399` kwargs_list 폴백 순서 뒤집기. 현재 `model_name=`(deprecated alias) 첫 시도 → `model=` 폴백. `model=` 우선으로 변경 (동작 변화 없음).
    - 위험: 과거 GenAI API key 직접 인증 시 동작 실패 → ADC 회귀 이력. 본 작업은 ADC 인증 유지 + import 경로만 교체로 한정 (§12-4 (b) 후보안).
    - 진입 트리거: LangChain 4.0 RC 발표 시점 또는 별도 운영 사유 발생 시.

    12-3. **venfobel-vitamin web 인덱스 보강 후 재평가** — 상태: `blocked` / 의존: §12-11-3, §12-11-4, §12-11-5 / 차단 사유: web seeding 단계 fetch/호스트 정규화 이슈 미해결

    - 발견(§12-4-A (b)): venfobel web 인덱스 8 청크 → 골드셋 web 2 청크 → tier1_web 평가 구조적 불가능. ALLOWED_DOMAINS 38→50 확장 효과는 fetch 실패로 미발현.
    - 선행 작업: §12-11-3(의약 매체 fetch 실패 — SSL/404), §12-11-4(oldm.dailypharm.com 호스트 정규화), §12-11-5(backend 다양화 + 재시도 로직).
    - 진입 조건: web 청크 수가 tier1_web 평가 가능 수준(≥ 골드셋 5건 확보 가능)으로 회복.
    - 재평가 시 §12-4-A 1차/2차 시도 평가 도구 그대로 재사용 가능 (collection_name 명시 패치 적용 후 commit 기준).

    12-4. **pet-food-premium 토픽으로 임베딩 평가 반복 (일반화 검증)** — 상태: `pending` / 의존: 없음 (인덱스 검증 완료 — median 0.410/p95 0.618)

    - 목적: §12-4-A (b) venfobel 결과(top-1 +14.3%p, gap_ratio 0.94×)가 단일 토픽 결과인지, gemini-embedding-001의 일반적 특성인지 분리 검증.
    - 마이그레이션 결정의 선결조건: pet-food-premium 결과가 venfobel과 동일 방향(top-1 우세 + gap_ratio < 1.0)이면 gemini-001의 임베딩 공간 특성으로 일반화 가능 → 마이그레이션 ROI 정밀 평가 단계 진입.
    - 평가 도구: §12-4-A 2차 시도 산출물 그대로 재사용. 슬러그 치환 3곳(`tools/sample_chunks_for_eval.py:L26`, `tools/eval_embedding_models.py:L40`, `tools/sanity_check_gemini_embedding.py:L8`)만 변경.
    - 골드셋 작성 정성 작업 30~60분 필요.
    - 진입 트리거: §12-12-1 완료 후 또는 광고대행사 작업(venfobel) 일단락 후.

13. **§12-13 — supervisor 라우팅 가드 + web/vector 루프 종결 조건 (2026-05-04 사용자측 검증 세션 발견)**

    __현재 상태 (2026-05-05 §12-13-1 + §12-13-4 패키지 close 세션 후)__: §12-13-1/4/5/7 close. §12-13 큐 9개 누적 중 4개 close, 5개 pending (§13-2/3/6/8/9).

    출처: §12-12-1 close 직후 사용자측 검증 세션(2026-05-04). 미션 A에서 "비타민 B1이 뭐야"(60초, 정상), "파이썬에서 리스트 컴프리헨션이 뭐야"(247초, 5회 vector→web 루프, 인덱스 8→37), "벤포벨이 뭐야"(9초, 정상)의 3건 비교 로그에서 검출. C 미션은 본 큐 미해결 상태로 진입(하자 인지 + 인덱스 변화 메모 + reports/ 디렉토리 분리 운영으로 risk 격리).

    13-1. **supervisor fast-path 토픽-적합성 가드 부재** — 상태: `closed (2026-05-05 §12-13-1 + §12-13-4 패키지 close 세션, 2차 패치 포함)` / 의존: 없음 / 우선순위: 높음 (C 미션 진행 중 재발 위험)
    - 발견: 입력에 "?"가 포함되면 supervisor가 "QA-like" 분류만으로 vector_search_agent로 직행. 토픽(`venfobel-vitamin`) 키워드와의 매칭은 검사하지 않음.
    - 증상: "파이썬에서 리스트 컴프리헨션이 뭐야"가 venfobel 인덱스 retrieval 시도 → no hits → web_search 진입 → outline OBJ 5개 쿼리로 venfobel 자료 추가 인덱싱 → 인덱스 8→37 증가.
    - 검토안: fast-path 진입 전 토픽 키워드(`venfobel`, `벤포벨`, `비타민`, `B1`, `벤포티아민`, `종근당` 등) 1차 매칭. 매칭 0이면 communicator 직행, ≥1이면 현재 동작 유지. 키워드 셋은 `core.config.CFG.TOPIC_TITLE` 또는 별도 `TOPIC_KEYWORDS` 설정에서 주입.
    - 진입 트리거: C 미션 완료 후 즉시 (예방적 수정 — C 산출물 평가에는 영향 없음, 다만 후속 사용자측 검증에서 재발 차단).

    **close 후기 (2026-05-05 §12-13-1 + §12-13-4 패키지 close 세션, 1차 + 2차 패치)**:

    *1차 패치*:
    - `core/config.py`: `TOPIC_KEYWORDS` env 신규 (`List[str]`, 콤마 구분, 미설정 시 `TOPIC_TITLE` 토큰 fallback). 비어 있으면 가드 비활성(기존 동작 유지).
    - `agent/supervisor.py`: 모듈-레벨 헬퍼 `_topic_keyword_set()` / `_topic_match_count()` 신규. 가드 2곳 적용 — ANCHOR-1(qa_direct_reply set 분기), L545 QA-like fast-path 직전. 키워드 0개 매칭 시 `task_history`에 `('communicator', 'off_topic:direct_qa'|'off_topic:qa_like')` 등록 + early return.

    *1차 검증 결과 (2026-05-05 09:27~29) — 부분 실패*:
    - 1차 가드 발화는 정확함 (`[Supervisor fast-path] QA-like off-topic ... → communicator`)
    - 그러나 그래프 엣지가 `research_planner`를 호출하면서 우회됨. 09:29:05 `[router.after_vector] research_loop_active=True → research_synthesizer (override qa_direct_reply)` 가 결정적 우회 지점.
    - ns_web 37 → 69 오염 (32 chunks 추가, 새 URL 15개 인덱싱). 09:29:19 `[router.after_synth] findings quick-ingest added=1` 부작용까지 발생.
    - 다행히 오염 자료 분석 결과 OBJ1/OBJ2(이중제형/오쏘몰, 일반약 광고 규제, 아로나민/임팩타민 비교, 활성비타민 비교표, 벤포벨 직접 언급)와 우연히 부합 → ns_web=69 그대로 보존하고 C 미션 진행 결정.

    *2차 패치*:
    - `core/routers.py`: `_has_off_topic_pending()` 헬퍼 신규 + 5개 라우터 진입 가드 (`tail_task_router`, `after_web_search_agent`, `after_vector_router`, `after_planner_router`, `after_synthesizer_router`). 모든 다른 분기(research_loop_active 등)보다 우선.
    - `agent/supervisor.py`: 두 가드 분기에 `research_round=0` + `research_loop_active=False` 강제 리셋 추가 (state mutation + return dict 양쪽). 함수 상단 L449 `[Supervisor] promote research_round=1 (basis: rag_on_disk)` 자동 승격을 가드 발화 시 무력화.

    *2차 검증 결과 (2026-05-05 09:46~47) — 성공*:
    - 입력: `파이썬 리스트 컴프리헨션이 뭐야?` (박제 회귀 케이스)
    - 1차 가드 발화 ✓ → 그래프가 `research_planner` 호출 → 2차 가드 차단 ✓ (`[router.after_planner] off_topic task pending → communicator (guard)`)
    - 미출현 확인: `[Web Search Agent]`, `documents_to_chroma(part:web)`, `[Research Synthesizer]`
    - ns_web 69 → 69 (인덱스 오염 0)
    - 응답 저장: `reports/venfobel-vitamin/qa/qa_venfobel-vitamin_20260505_094715.md` (921 bytes, 407 chars). 1차 검증(325 bytes) 대비 약 3배 풍부.

    *ENV 적용 (옵션 A: TOPIC_TITLE 원본 유지)*:
    - `topics/venfobel-vitamin.env`: `TOPIC_KEYWORDS=venfobel,벤포벨,비타민,B1,벤포티아민,종근당` 추가
    - `TOPIC_TITLE`의 일반어("시장", "분석", "2026" 등)도 fallback 토큰으로 합류 — 광범위 보조 질의는 통과, 박제 회귀 케이스는 차단. 운영 의도와 부합.

    *부산물 정리*:
    - `reports/venfobel-vitamin/_qa_session_20260505_communicator/` 8개 파일 삭제 (옵션 1 통째 삭제). 박제 ts(170636/171821/172655) 3개는 본 디렉터리에 부재 → 사실상 이미 정리된 상태였음.

    *잔여 관찰사항 (close 차단 사유 아님)*:
    - 2차 검증 후 task_history에 `web_search_agent` (False, search:auto) pending 잔존
    - `research_loop_active=True` 잔존
    - 다층 방어선(5개 라우터 가드) 덕분에 실제 부작용은 없으나 깔끔한 close를 위한 보강은 §12-13 큐 다른 항목 처리 시 같이 검토.

    *부수 효과*:
    - §12-13-2 (web_search agent의 query 파생 로직) 의 본 시나리오 트리거 차단. supervisor 가드 + router 가드 다층 방어선이 web_search 진입 자체를 막으므로 OBJ 5개 쿼리 생성 부작용도 발생 불가. (§12-13-2 자체는 일반 on-topic 질의에서 user query와 OBJ 분리 문제는 여전히 미수정.)
    - §12-13-3 (after_vector → web 루프 카운터) 의 본 시나리오도 차단. router 가드가 진입 자체를 막으므로 카운터 증가 여부와 무관하게 안전. (§12-13-3 자체는 카운터 정확성 문제 미수정.)

    13-2. **web_search agent의 query 파생 로직: 사용자 질의와 OBJ 분리** — 상태: `pending` / 의존: §12-13-1과 패키지로 처리 가능 / 우선순위: 중
    - 발견: web_search agent는 사용자 질의를 무시하고 outline OBJ 5개를 그대로 검색 쿼리로 사용 (`[WEB SEARCH AGENT] objectives 5개 주입` 로그). 즉 사용자 의도와 web_search 의도가 의도적으로 분리되어 있음.
    - 증상: vector retrieval이 no hits일 때 fallback으로 web_search가 호출되는데, 발사되는 쿼리는 사용자 질의와 무관 → 사용자 질의로 다시 vector retrieval 시도해도 또 no hits → 루프.
    - 검토안 (택1):
      - (a) vector no-hits 시 web_search 진입 자체를 차단 (`router.after_vector` 분기에서 "QA-like 의도이고 user query와 OBJ 무관"이면 communicator로 직행)
      - (b) web_search 쿼리에 user query 1개 혼합 (OBJ 4 + user 1)
      - (a)가 단순하고 §12-13-1과 결합 시 자연스러움. (b)는 OBJ 기반 research workflow와 충돌 가능.
    - 진입 트리거: §12-13-1과 함께.

    13-3. **after_vector → web_search → after_vector 루프 카운터 검증** — 상태: `pending` / 의존: §12-13-1/2와 묶음 / 우선순위: 중
    - 발견: 로그상 `after_vector_ws_retries=1/1` 명시(retry 1회로 제한)에도 실제로는 5회 루프 발생 → 카운터 의도와 실제 동작 불일치.
    - 증상: 2번째 질의(파이썬)에서 vector_search 5회 + web_search 5회 = 10단계가 4분 7초 동안 진행됨. `core/routers.py`의 `after_vector` / `after_web` 분기에서 카운터 증가 누락 또는 round 진입 시 reset 로직 의심.
    - 검토안: `core/routers.py` 해당 분기 코드 점검 + 카운터 state path(예: `state["routing_counters"]["after_vector_ws_retries"]`) 추적. 단위 테스트로 재현 + 1회 제한 회복.
    - 진입 트리거: §12-13-1/2 작업 시 함께. routers 코드 손댈 때 한 번에 처리.

    13-4. **communicator 자동 저장 파일명이 C 미션 리포트와 충돌** — 상태: `closed (2026-05-05 §12-13-1 + §12-13-4 패키지 close 세션)` / 의존: 없음 / 우선순위: 높음 (C 진입 직전 즉시 필요)
    - 발견: communicator가 모든 응답을 `reports/venfobel-vitamin/{slug}_{timestamp}.md`로 자동 저장. Direct QA hard-stop 응답(317B/377B)도, 일반 communicator 응답(512B)도, C 미션 end-to-end 리포트도 모두 동일 파일명 형식 → 시각적 식별 불가.
    - 증상: 본 세션 검증 중 `reports/venfobel-vitamin/`에 3개 QA 응답 파일 자동 생성 (170636/171821/172655). C 진입 시 진짜 리포트와 섞일 위험.
    - 검토안: QA 응답 저장 경로를 `reports/venfobel-vitamin/qa/{slug}_{ts}.md` 또는 `reports/venfobel-vitamin/{slug}_qa_{ts}.md`(qa prefix)로 분리. `agent.communicator`의 `[SAVE] report saved` 분기에서 `qa_direct_reply` 플래그 보고 경로 분기.
    - C 진입 전 검증 세션 부산물 3개 파일을 삭제.
    - 진입 트리거: 코드 수정은 차후. **임시 우회는 본 세션 C 진입 전 즉시.**
    **close 후기 (2026-05-05 §12-13-1 + §12-13-4 패키지 close 세션)**:
    - 패치 (`agent/communicator.py`):
      - `_safe_save_report(state, content_hint, *, qa_mode=False)` 시그니처 확장. `qa_mode=True` 시 저장 경로를 `<out>/<topic_slug>/qa/qa_<topic_slug>_<ts>.md`로 분리.
      - 호출처 3곳 분기:
        - L294 (레거시 플래그 QA): `qa_mode=True` 명시
        - L383 (tagged QA delivery): `qa_mode=True` 명시
        - L913 (generated reply 후크): `desc.startswith("off_topic:")` OR `qa_direct_reply` flag 추론 → 자동 분기 (§12-13-1 가드가 라우팅한 응답도 자동 격리)
      - `_save_last_ai_if_any` 경로(L170)는 비-QA 컨텍스트 유지 (announce_planner, show_outline 등).
    - 검증: `reports/venfobel-vitamin/qa/qa_venfobel-vitamin_20260505_094715.md` 정상 저장 (921 bytes). C 미션 진짜 리포트(`reports/venfobel-vitamin/` 직하)와 디렉터리 단위 분리 확인.
    - 부산물 정리: `_qa_session_20260505_communicator/` 8개 파일 옵션 1로 통째 삭제 처리.

    13-5. **`write:` 명시형 prefix 외 라우팅 실패 (ko-natural 형식)** — 상태: `closed (2026-05-05 §12-13 코드 수정 세션)` / 의존: 없음 / 우선순위: 최상 (Blocker)
    - 발견: 2026-05-05 사용자측 검증 세션 C 미션 진입 시. "2. <섹션명> 섹션 작성해주세요"(ko-natural hit) 입력 → supervisor가 write 의도 무시 + research_round 0→1 promote → web_search → vector → synthesizer → communicator Direct QA 흐름으로 진행. **section_writer 진입 실패** (90초, 356자 응답).
    - 대조군: 같은 의도를 "write: <섹션명>"(explicit hit)으로 입력 시 `[Supervisor fast-path] write + rag_on_disk → vector_search → section_writer` 분기 정확 작동. 7섹션 연속 100% 일관 재현 (06:01:54~06:32:34).
    - 임시 우회: **C 미션은 `write:` 명시형 prefix 사용 시 정상 작동.** 7섹션 + report_builder 합본까지 31분에 완수.
    - 검토안: `agent.supervisor` 의도 분류 분기에서 `extract_write_title()` 결과를 explicit/ko-natural 구분 없이 동일 우선순위로 처리. `rag_expression.py:213-243` 함수는 둘 다 정상 hit하므로 supervisor 측에서 결과 사용 시점에서 구분이 발생.
    - 진입 트리거: §12-13-1/2/3과 함께 supervisor 분기 코드 손댈 때. 코드 수정 우선순위 최상이지만 임시 우회로 사용자 작업은 막히지 않음.

    **close 후기 (2026-05-05 §12-13 코드 수정 세션)**:
    - 패치: `agent/supervisor.py` Line 607~617 — `_is_write_cmd = last_text.lower().startswith("write:")` 검사를 `_write_title_early = extract_write_title(last_text)` 호출로 통일. explicit/ko-natural 둘 다 hit 시 동일 fast-path 진입.
    - description 정규화: `last_text` 원본 → `f"write: {_write_title_early}"` 로 변환하여 section_writer 측 파싱 일관성 확보.
    - 로그에 `hit=explicit/ko-natural` 표기 추가 — 라우팅 분기 진단성 확보.
    - 검증: ko-natural 입력 "7. 실행 로드맵 및 핵심 성과 지표(KPI) 섹션 작성해주세요" → fast-path 정확 진입 + section_writer 도달 + 4905자 초안/10165 bytes .md 저장 (08:08:50~08:11:21, 2분 31초). 직전 세션 7회 100% 실패 → 본 세션 1회 회복 확정.
    - 회귀 검증 explicit 형식은 단위 테스트 (`extract_write_title('write: 실행 로드맵 및 핵심 성과 지표(KPI)')` → `'실행 로드맵 및 핵심 성과 지표(KPI)'`) 로 갈음. 함수 hit 결과만 사용하는 패치 구조상 explicit 회귀 가능성 무시 가능.
    - 부수 효과: §12-13-3 (after_vector → web 루프) 의 본 시나리오 트리거 차단. writer_pending 사전 등록으로 router.after_vector가 vector no hits 시에도 web_search 우회 후 section_writer 직행. (§13-3 자체는 일반 QA-like 입력에서 여전히 미수정.)
    - 2026-05-05 17:46 추가 검증 (explicit + 신규 세션 / refs 비어있는 컨텍스트): msgs=3, docs_in_state=0 상태에서 write:
  ▎ 실행 로드맵 및 핵심 성과 지표(KPI) 입력. supervisor.py L718-731 신설 분기에 pending_write_title=True +
  ▎ requested_write_title + suppress_vector_qa=True + schedule_writer_if_needed() 추가. 흐름은 web_search →
  ▎ section_writer (refs 비어있음으로 vector 단계 우회), router.after_web 의 strict writer_pending 검사 통과로
  ▎ section_writer 직행. draft 4922 chars, 11546 bytes 저장. 직전 17:06 회귀(468 chars) 회복 확정.

    13-6. **Vertex 429 ResourceExhausted retry — quota 모니터링 부재** — 상태: `closed (2026-05-05 metric 도입 + 검증 4단계 완료) — (a) 완료 / (b)(c) 추세 데이터 누적 후 결정` / 의존: 없음 / 우선순위: 중
    - 발견: C 미션 Section 7 작성 중(06:28:46~06:31:20, 2분 49초) `langchain_google_vertexai._retry`가 `ResourceExhausted: 429` 발생 → 4초 대기 후 재시도 → 성공. **다른 섹션 평균(35~50초) 대비 5배 소요.**
    - risk: retry 한도 초과 시 해당 섹션 작성 실패 가능. C 미션 7섹션 처리 정도 트래픽에서 1회 발생 → 일상 운영 트래픽에서 빈도 추정 필요.
    - 검토안: (a) Vertex quota 일일 사용량 추적 metric 추가, (b) 429 발생 시 fallback (gemini-flash → gemini-flash-lite, Anthropic API), (c) 긴 섹션 LLM 호출 분할.
    - 진입 트리거: 사용자측 작업이 누적되며 429 빈도가 증가하는 시점.

    **close 후기 — (a) 부분 완료 (2026-05-05 metric 도입 세션)**:
    - 결정: 발견 빈도가 "C 미션 7섹션 중 1회" 수준에서 (b) Anthropic fallback 도입(패키지 추가 + provider 추가)이나 (c) 호출 분할(프롬프트/체인 구조 변경, 품질 영향 가능)은 비용 대비 과투자. 박제 본문의 "진입 트리거: 빈도가 증가하는 시점" 명시에 맞춰 (a) metric만 우선 도입하여 추세 데이터부터 확보 — (b)(c)는 metric 추세를 본 뒤 데이터로 결정.
    - 패치:
      - `tools/metrics.py` — `record_llm_call(provider, model, latency_s, success, error_class, section_title, retry_hint)` 함수 신설. 기존 `_emit` / `_enabled` 인프라 재사용, NDJSON 라인 1건을 `logs/metrics.ndjson` 에 누적. 집계(`RoundAgg`)에는 추가하지 않음 — 후처리(`jq` 등)로 일별 집계 가능, 필요 시 추후 합산 항목 추가.
      - `agent/section_writer.py` — Line 226 부근 `chain.invoke(...)` 를 `time.monotonic()` 측정 + try/except 로 감싸서 성공/실패 양쪽에서 `record_llm_call` emit. provider는 `config.CFG.LLM_PROVIDER`, model은 `getattr(llm, "model_name", ...) or getattr(llm, "model", ...) or type(llm).__name__` 로 추출.
      - retry_count 직접 수집 불가 사유: langchain_google_vertexai 의 `_retry` 가 라이브러리 내부에서 끝까지 처리하고 결과만 반환 — 호출 측 시야에 retry 횟수가 노출되지 않음. 대신 latency 가 평균(35~50초) 대비 비정상적으로 길면(임계값 90초) `retry_hint="slow"` 로 표기 → 후처리에서 retry 추정 가능. 임계값 90초는 §12-13-6 발견 케이스(2분 49초)를 식별하기 위한 보수적 기준.
      - 실패 케이스(`ResourceExhausted` 한도 초과 등)는 `error_class=type(_llm_err).__name__` 로 기록 후 raise — 기존 흐름 유지(에러 전파).
    - 검증 방법(권장): `logs/metrics.ndjson` 에 `"type":"llm_call"` 라인이 누적되는지 1회 섹션 작성으로 확인 → `jq 'select(.type=="llm_call")'` 로 필터, `select(.retry_hint=="slow")` 또는 `select(.success==false)` 로 의심 케이스 추적. 일일 집계 예: `jq -r 'select(.type=="llm_call") | [.ts, .latency, .retry_hint, .success] | @tsv' logs/metrics.ndjson`.
    - 잔여 (보류 — metric 추세 본 뒤 결정):
      - (b) gemini-flash-lite / Anthropic fallback: 현재 `core/llm.py` 는 OpenAI/Gemini/Vertex AI 3개 provider 지원, Anthropic 패키지 미설치. 도입 시 패키지 추가 + `_provider_modules()` 분기 추가 + `LLM_PROVIDER` env 케이스 추가 필요. 의존도 큰 변경.
      - (c) 호출 분할: `prompts.get_section_writer_prompt()` 와 `agent/section_writer.py:226` 체인 구조를 "긴 섹션은 H3 단위로 분할 → 부분 호출 → 결합" 으로 재설계. 품질 영향(연결성/일관성) 가능 → 별도 검증 필요.
    - 박제 후기:
      - **수치적 진입 기준(가설)**: NDJSON 데이터 누적 후 (i) 일일 LLM 호출 수, (ii) `retry_hint=="slow"` 비율, (iii) `success==false` 비율(특히 `error_class=="ResourceExhausted"`) 3개 지표가 의미 있는 추세를 보일 때 (b)(c) 진입 결정. 임계값은 데이터를 보고 정함.
      - **이름 충돌 주의**: `tools/metrics.py` 에 `record_*` 시리즈(record_query_issued, record_zero_result, ...) 이미 존재 — 새 함수도 동일 패턴(`record_llm_call`)으로 명명. 시그니처는 키워드 전용(`*` 강제)으로 호출 측 가독성 우선.
      - **§12-13-6 외 LLM 호출 진입점**: `agent/communicator`, `agent/content_strategist` 등 다른 LLM 호출 지점은 본 세션에서 미계측. 발견 케이스가 `section_writer` 한정이라 우선순위 낮음. 추후 (b)/(c) 진입 시 또는 다른 노드에서 429 관측 시 동일 wrapper 추가.

    **게이트 함정 close 후기 (2026-05-05 검증 단계 추가 발견)**:
    - 증상: metric 도입 후 `.env:METRICS_ENABLED=0 → 1` + 백엔드 재시작 + 섹션 1회 재작성 (19:30:49 [LLM] init / 19:31:15~19:31:35 SECTION WRITER, 20초, draft 3008자) 정상 수행됐으나 `logs/metrics.ndjson` 파일 자체가 생성 안 됨.
    - 진단: `tools/metrics.py:_enabled()` 가 단락 평가 순서로 `os.getenv("POSTHOG_DISABLED")` 를 `METRICS_ENABLED` 보다 먼저 검사 → `.env:POSTHOG_DISABLED=1` 이 살아있어 즉시 False 반환 → `_emit()` 진입 자체 차단.
    - 변수명-실효 괴리: 코드 주석은 "과거 텔레메트리 경로 호환" 이라 적혀있었지만, 실제로 이 모듈은 더 이상 PostHog 로 송신하지 않고 ndjson 로컬 파일만 emit. 즉 변수명은 PostHog인데 실효는 자체 메트릭 마스터 스위치 — 사용자가 PostHog 외부 송신 차단 의도로 둔 변수가 자체 메트릭까지 끄는 함정.
    - 패키지 경로 추적: `requirements_vertex.txt:123 posthog==5.4.0` 은 ChromaDB(`chromadb==1.5.1`)의 의존성. 코드베이스 내 `import posthog` 직접 사용 0건. ChromaDB 의 외부 PostHog 송신 차단은 별도 변수 `ANONYMIZED_TELEMETRY=False` (ChromaDB 가 직접 읽음) 가 정공법.
    - 패치:
      - `.env` — `POSTHOG_DISABLED=1` 줄 삭제, `ANONYMIZED_TELEMETRY=False` 추가, 주석으로 두 변수의 차이 명시 (자체 ndjson vs 외부 PostHog).
      - `tools/metrics.py:_enabled()` — `POSTHOG_DISABLED` / `POSTHOG_DISABLE` 게이트 줄 삭제. `DISABLE_METRICS` (kill switch) + `METRICS_ENABLED` (기본 on) 단일 게이트로 단순화. docstring 에 분리 사유 박제.
    - 검증 절차(사용자 권장): (i) 백엔드 재시작 → (ii) 섹션 1회 작성 → (iii) `Get-Content logs/metrics.ndjson -Tail 20 | Select-String 'llm_call'` 로 라인 확인. 19:31 케이스 재현 시 기대 출력: `latency≈20s, success=true, retry_hint=""`.
    - 박제 후기:
      - **이름이 의미를 호도하는 게이트는 항상 함정**: 과거 호환 명목으로 남긴 변수가 신규 사용자/디버거 입장에서 단서 0. metrics 게이트는 metrics 라는 이름의 변수만 보도록 하는 게 정공법. 외부 SDK 차단은 그 SDK 의 공식 변수를 별도로.
      - **잔재 정리의 시점**: §12-13-6 (a) metric 도입 → 즉시 검증 시도 → 게이트 함정 노출. metric 추가 자체보다 검증 단계가 함정 폭로의 트리거. 코드 도입 + 첫 검증을 같은 세션에 묶는 게 잔재 청소 기회.
      - **의존성으로 끌려온 패키지의 가시성**: `posthog==5.4.0` 이 ChromaDB 의존성으로 들어온 사실은 `pip show posthog` 또는 의존성 트리(`pipdeptree`) 안 보면 모름. 변수명 단서만으로는 추적 불가했음.

    **Deadlock close 후기 (2026-05-05 검증 2단계 — 게이트 풀고 나서 노출)**:
    - 증상: 게이트 함정 패치 후 백엔드 재시작 + 섹션 작성 재시도 → web_search 정상 진행 (naver_direct + tavily, 19:59:13 results saved items=1) → **그 직후 결정론적 hang**. 208초 idle, ChromaDB sqlite 19:44:11 이후 무갱신, worker CPU 거의 0 (29.7s/4분), outbound 4건 모두 `CloseWait` (직전 검색 API 잔재). PID kill 후 동일 시나리오 재시도 → **완전히 동일 위치에서 재현**.
    - 진단 인프라: `pip install --user py-spy` (0.4.2) → `py-spy dump --pid <worker>` 로 전체 thread stack 확보. WindowsApps Python 의 user-site 경로는 `…\LocalCache\local-packages\Python312\Scripts\py-spy.exe`. 향후 Python hang 진단 standard tool로 박제.
    - py-spy stack trace 핵심:
      - `asyncio_0` (실제 작업): `metrics.py:event()` (`with _METRICS_LOCK:`) 진입 시도에서 멈춤. 호출 체인: `web_search → _save_results → utils.py:event() → metrics.py:event()`.
      - `metrics:set_round` thread: `metrics.py:round()` 의 `with _METRICS_LOCK:` 대기.
      - `metrics:record_query_issued` thread: `metrics.py:record_query_issued()` 의 `with _METRICS_LOCK:` 대기.
      - `metrics:record_backend_latency:naver_direct` thread: 동일 lock 대기.
      - 모든 metrics thread 가 동일 `_METRICS_LOCK` 대기 — lock holder 가 release 못 하고 있음.
    - 진짜 원인 (기존 잠재 버그): `tools/metrics.py:10 _METRICS_LOCK = threading.Lock()` 은 비재진입(non-reentrant). `record_query_issued()` / `record_backend_latency()` / `record_chunks()` 등이 `with _METRICS_LOCK:` 안에서 `REG.round()` 를 호출하는데, `round()` 도 같은 lock 을 다시 잡으려 함 → 같은 thread 의 nested acquire → **자기 자신 데드락**. 모든 다른 thread 는 그 holder 를 무한 대기.
    - **노출 시점이 우리 변경과 맞물린 이유**: `POSTHOG_DISABLED=1` 시절엔 `_enabled() == False` → `record_*` / `event()` 들이 즉시 return → lock 진입조차 안 해서 reentrancy 버그가 가려져 있었음. 게이트 함정 패치로 `METRICS_ENABLED=1` 이 비로소 효력 발휘 → 첫 lock 진입 → 데드락 폭로. 즉 (a) metric 도입 자체가 원인이 아니라 (b) 활성화로 잠재 버그가 노출된 것.
    - 패치: `tools/metrics.py:10` 를 `threading.Lock()` → `threading.RLock()` 한 줄 교체. RLock 은 같은 thread 의 재진입 허용, 다른 thread 에는 동일 mutual exclusion. 의미 동일하면서 nested 호출 패턴 안전. 호출 측 코드 수정 불필요.
    - 박제 후기:
      - **노출 트리거의 다층 구조**: §12-13-6 (a) metric 추가 → 게이트 함정 → 게이트 패치 → reentrancy 데드락. 한 번에 한 layer 만 보여서 진단이 단계적이었음. 이런 잠재 버그는 "도입 시점" 이 아니라 "활성화 시점" 에 폭로되므로, 새 인프라 활성화 직후 1~2회 정상 동작 확인 권장.
      - **py-spy 진단 가치**: stack trace 1번 떠서 즉시 lock contention 패턴 식별. 외부 connection / process state / 로그만으로는 "외부 hang 인지 내부 deadlock 인지" 구분 불가했음. WindowsApps Python 환경에서도 정상 동작 확인 — 인프라로 박제.
      - **Lock vs RLock 디폴트 선택**: 모듈 내 함수가 서로 호출하는 구조라면 RLock 이 안전. Lock 은 "단순 mutual exclusion + nested 호출 없음" 이 보장될 때만. metrics.py 처럼 `record_*` → `round()` 패턴이 흔한 코드는 RLock 이 디폴트.

    **Flush 누락 close 후기 (2026-05-05 검증 3단계 — deadlock 풀고 나서 노출)**:
    - 증상: deadlock 패치 후 백엔드 재시작 + 섹션 작성 → hang 사라지고 정상 진행. `logs/metrics.ndjson` **파일은 생성**됐으나 **내용이 0바이트**. record_llm_call / event 호출은 분명 일어났는데 디스크에 안 떨어짐.
    - 진단: `tools/metrics.py:228 _FH = open(fpath, "a", encoding="utf-8")` 는 **default block buffering** (Python text mode 기본 ~8KB). `_FH.write(...)` 후 명시 flush 없음. `_shutdown()` (L244) 의 `_FH.flush() + close()` 만 flush 호출하는데, 이건 `atexit.register(_shutdown)` 으로 등록 → **프로세스 종료 시점에만 발동**. 백엔드가 살아있는 동안엔 buffer 에 누적되고 디스크 0바이트.
    - 노출 시점이 늦은 이유: 게이트 함정 / deadlock 두 개를 풀고 나서야 실제로 emit 이 worker 큐까지 도달 → 처음으로 _worker() 가 _FH.write() 호출 → 그제서야 buffer 에만 쌓이는 패턴 노출. 즉 §12-13-6 (a) 도입 단계에서 이 버그도 같이 잠재돼 있었으나, 앞 두 layer 가 emit 자체를 막아서 가려져 있었음.
    - 패치: `tools/metrics.py:228` 한 줄 — `open(fpath, "a", encoding="utf-8")` → `open(fpath, "a", encoding="utf-8", buffering=1)`. `buffering=1` 은 **line buffering**: 매 `"\n"` 만나면 자동 flush. NDJSON 라인 단위 emit 패턴과 정확히 맞음. 매 라인마다 syscall 1회 추가되지만 fsync 가 아닌 OS 페이지 캐시 flush 라 성능 영향 측정 불가능 수준.
    - 박제 후기:
      - **검증 단계의 다층 노출 패턴 (재정리)**: §12-13-6 (a) metric 도입 → 검증 1단계 게이트 함정 → 검증 2단계 reentrancy 데드락 → 검증 3단계 flush 누락. 4개 layer 가 결과적으로 같은 commit 묶음에 박혀있었고, 사용자 입장에서 "1번 켜면 동작해야 할 기능" 이 3번 추가 패치 후에야 작동. **새 인프라는 1단 검증으로 끝나는 일이 거의 없다는 교훈** — 활성화 후 첫 1~3회는 모두 진단 trigger 로 가정하고 디버깅 인프라(py-spy 등) 미리 준비.
      - **block buffering vs line buffering**: 로그/메트릭 파일에 default block buffering 은 함정. `print(..., flush=True)` 와 같은 명시 flush 또는 `open(..., buffering=1)` 이 NDJSON 같은 라인 단위 emit 패턴의 디폴트가 되어야. `tail -f` / `Get-Content -Wait` 류 라이브 모니터링 도구가 동작하려면 line buffering 필수.
      - **atexit 의존의 함정**: shutdown hook 만 flush 하던 패턴은 "프로세스가 정상 종료될 때만 데이터가 보존됨" 을 의미. SIGKILL / OOM / Stop-Process -Force 같은 비정상 종료에선 buffer 째 잃음. 메트릭 같은 운영 데이터는 라이브 가시성 + 비정상 종료 내성 양쪽 다 line buffering 이 정공법.

    **최종 검증 성공 (2026-05-05 검증 4단계 — flush 풀고 나서)**:
    - line buffering 패치 후 백엔드 재시작 + 섹션 작성 → hang 없음, `logs/metrics.ndjson` 실시간 누적 확인. 50라인 7785바이트, type 분포: event 14 / chunks 10 / backend_latency 10 / set_round 7 / query_issued 7 / **llm_call 2**.
    - **§12-13-6 (a) 핵심 결과 — llm_call 라인 2건**:
      - `{ts: 20:30:30, latency: 47.6s, success: true, retry_hint: "", error_class: "", provider: "vertexai", model: "gemini-2.5-flash", section: "경쟁 브랜드(아로나민·임팩타민) 전략 비교 및 메시지 빈 공간 도출"}`
      - `{ts: 20:37:56, latency: 29.0s, success: true, retry_hint: "", error_class: "", provider: "vertexai", model: "gemini-2.5-flash", section: 동일}`
    - **baseline 확정**: 2건 모두 정상 호출 (retry 없음). §12-13-6 발견 케이스(154초, ResourceExhausted 1회 retry) 와 비교 시 5배 빠름 = 평균 35~50초 범위 정확히 부합.
    - **(b)(c) 진입 신호 정의 (운영 가이드)**:
      - `latency > 90s` 라인 비율 증가 (NDJSON 후처리: `jq 'select(.type=="llm_call" and .latency > 90)'`)
      - `success: false` + `error_class: "ResourceExhausted"` 출현
      - 일일 호출 수 누적 추세 (특정 quota 임계 접근)
      - 위 3개 지표가 **의미 있는 빈도** 로 나타나기 시작하면 (b) Anthropic fallback 도입 또는 (c) 호출 분할 진입 결정. 임계값은 데이터를 보고 정함.
    - 잔여(보류 → 별도 박제):
      - `topic_slug: null` 정합성 — llm_call 라인의 topic_slug 가 null. record_llm_call 호출 시점에 REG.topic_slug 가 set 되어 있지 않은 듯. 분석엔 영향 없으나 일별 topic 별 집계 어려움. **§12-13-11 로 분리 박제**.
      - section_writer 외 LLM 호출 진입점 (communicator, content_strategist 등) 미계측. 우선순위 낮음.

    13-7. **`extract_write_title` 닫는 괄호 처리 미흡** — 상태: `closed (2026-05-05 §12-13 코드 수정 세션)` / 의존: §12-13-1과 패키지 처리 가능 / 우선순위: 낮음
    - 발견: C 미션 Section 7 입력 `'write: 실행 로드맵 및 핵심 성과 지표(KPI)'` → extract 결과 `'실행 로드맵 및 핵심 성과 지표(KPI'` (닫는 `)` 잘림). 본문 작성에 영향 없으나 파일명도 `실행-로드맵-및-핵심-성과-지표kpi.md`로 정규화됨(괄호 자체 누락).
    - 검토안: `rag_expression.py:213-243` 함수의 `_TAIL_PUNCT_RE` 정규식 점검. tail 정리 시 닫는 괄호도 trim 대상에 포함된 것으로 추정 → 매칭된 여는 괄호 `(` 직전까지 포함하는 group 처리 필요.
    - 진입 트리거: §12-13-1 이후 또는 별도 cosmetic 정리 시.

    - 진입 트리거: §12-13-1 이후 또는 별도 cosmetic 정리 시.

    **close 후기 (2026-05-05 §12-13 코드 수정 세션)**:
    - 진단 정정: 박제 본문은 `_TAIL_PUNCT_RE` 만 원인으로 지목했으나, 실제로는 `_strip_smart_quotes()` (Line 207~209) 의 `s.strip(...)` 인자에도 `'(', ')', '[', ']'` 포함되어 있어 explicit 경로에서도 닫는 `)` 잘림. 단위 테스트 `extract_write_title('write: 실행 로드맵 및 핵심 성과 지표(KPI)')` → `'실행 로드맵 및 핵심 성과 지표(KPI'` 로 explicit 경로 버그 확인.
    - 패치 (`rag_expression.py`):
      - Line 27 부근 — `_strip_tail_punct(s)` 헬퍼 신규 추가: 닫는 따옴표는 기존대로 제거, 닫는 `)`/`]` 는 문자열 안에 대응 여는 짝이 있으면 보존, 없으면 제거 (떠돌이 closer 정리). `_TAIL_PUNCT_RE` 는 legacy 변수로 보존 (다른 모듈 사용처 0건 확인, 향후 cleanup 가능).
      - `_strip_smart_quotes()` (Line 207~209) — strip 인자에서 `()`, `[]` 제거 + 함수 끝에 `_strip_tail_punct()` 호출 추가.
      - Line 239 — `_TAIL_PUNCT_RE.sub("", raw)` → `_strip_tail_punct(raw)` 교체.
    - 단위 검증: 7개 케이스 (#1 explicit+괄호, #2 ko-natural+괄호, #3 ko-natural 일반, #4 떠돌이 `)`, #5 끝 마침표, #7 대괄호 짝) 모두 통과. (#6 따옴표 케이스는 PowerShell escape 이슈로 보류, 회귀 가능성 낮음.)
    - e2e 검증: 위 §12-13-5 검증과 동일 입력에서 `extract_write_title ko-natural hit: 실행 로드맵 및 핵심 성과 지표(KPI)` 정확 출력 — 닫는 `)` 보존 확인.
    - 잔여: 슬러그 정규화 단계에서 괄호 자체 누락은 별개 함수 (`section_writer` 또는 `content_utils.save_md_draft` 슬러그 정규화) 영역 → §12-13-9 신규 박제로 분리.

    13-8. **router.tail outline_shown=False 영구 미설정 → communicator prompt 분기와 비일관** — 상태: `pending` / 의존: 없음 / 우선순위: 낮음
    - 발견: C 미션 7섹션 진행 중 매번 `[router.tail] outline exists but not shown → communicator (shown=False)` 라우팅. 그러나 communicator 응답은 outline 표시하지 않고 일반 응답만 생성. 즉 router가 "outline 표시" 의도로 보냈으나 communicator는 "다시 출력하지 않겠다" 분기 선택 → state.outline_shown 계속 False → 다음 섹션 처리 시 또 동일 라우팅 반복.
    - 증상: communicator 호출 7회 누적 + reports/ 디렉토리에 1KB대 부산물 7개 누적 (§12-13-4 누적 가속).
    - 검토안: communicator가 outline 표시 분기를 거쳤다면(prompt가 outline을 컨텍스트로 받았으나 출력 생략 결정 포함) state.outline_shown=True 명시 설정. 또는 router.tail의 outline_display 분기 우선순위 조정.
    - 진입 트리거: §12-13-4 코드 수정 시 함께.

    - 진입 트리거: §12-13-4 코드 수정 시 함께.

    13-9. **section_writer 슬러그 정규화에서 괄호 자체 제거** — 상태: `pending` / 의존: 없음 / 우선순위: 낮음 (cosmetic)
    - 발견: 2026-05-05 §12-13 코드 수정 세션. §12-13-7 패치로 `extract_write_title()` 결과는 `'실행 로드맵 및 핵심 성과 지표(KPI)'` (괄호 보존) 정상 반환. 그러나 section_writer 가 .md 파일명 슬러그 생성 시 `실행-로드맵-및-핵심-성과-지표kpi.md` (괄호 자체 누락) 로 정규화. 본문 제목은 정상 표기.
    - 증상: cosmetic 이슈 — 합본 보고서 본문 영향 없음. 다만 sections/ 디렉토리 파일명에서 괄호 정보 손실 → 동명이섹션 (예: "...(요약)" vs "...(상세)") 충돌 잠재 위험.
    - 검토안: `content_utils._slugify()` 또는 section_writer 측 슬러그 함수 점검. `re.sub(r'[^\w\-]', '', s)` 같은 정규식이 괄호를 제거 중일 가능성. 괄호를 `-`로 치환하거나 보존하도록 수정.
    - 진입 트리거: 별도 cosmetic 정리 시 또는 동명이섹션 충돌 발생 시.

    13-10. **`/api/export` 엔드포인트가 prefix 없는 신형 섹션 파일을 매칭 못 함** — 상태: `closed (2026-05-05 §12-13-10 close 세션)` / 의존: §12-13-9와 같은 슬러그 정합성 라인 / 우선순위: 높음 (사용자 다운로드 기능 차단)
    - **발견 (2026-05-05)**: 프론트엔드에서 Word 다운로드 시도 시 모든 섹션이 `HTTP 404 — {"detail":"section N not found"}`. 사용자 보고: "Word 다운로드 실패: HTTP 404 Not Found — section 2 not found". 보고서 본문 화면 표시는 정상이고 (`/api/files`는 잘 매칭) export만 깨짐.
    - **증상**: `kind="section"` 으로 보내든 `kind="report"` 로 보내든 동일하게 매칭 실패 — `_read_section_file()`은 404, `_read_all_sections()`는 빈 리스트 반환 ("no sections found").
    - **진단**:
      - `app.py:1386` `_read_section_file()` — 폴더 내 .md 파일 중 `fname.startswith(f"{section_id}-")` 만 매칭. 신형 슬러그 파일명(예: `실행-로드맵-및-핵심-성과-지표kpi.md`) 에는 prefix 없음 → 항상 fail.
      - `app.py:1429` `_read_all_sections()` — `re.match(r"^(\d+)-", fname)` 으로 prefix 매칭만. 신형 파일은 모두 skip → 빈 결과.
      - 정합성 깨짐의 근원: writer (`section_writer` / `content_utils.save_md_draft`) 가 `slugify(title)` 결과만 파일명으로 사용하고 prefix를 붙이지 않음. §12-13-9 (슬러그 cosmetic) 발견 당시에도 prefix 부재는 발견됐으나 export endpoint 측 회귀를 catch 못함 — export 기능을 사용자가 처음 시도한 시점에 노출.
    - **해결** (`app.py` 패치):
      - 헬퍼 3개 신설: `_load_outline_items()` (활성 outline 줄 단위 로드), `_outline_title_to_slug(raw)` (제목만 추출 후 `utils.text_utils.slugify(allow_unicode=True)`), `_resolve_section_file(section_id, slug_dir, outline_items)` (1차 prefix → 2차 슬러그 fallback).
      - `_read_section_file()` / `_read_all_sections()` 가 위 헬퍼를 사용하도록 단순화. 옛 형식 (`{N}-...md`) 역호환 유지 + 신형 슬러그 파일명 매칭 추가.
      - 슬러그 비교는 case-insensitive (lower) — `slugify()`가 이미 lower로 내려주지만 안전망.
    - **검증**:
      - 사용자측: 패치 + 백엔드 재시작 후 섹션 2 Word 다운로드 정상. PDF/복사도 동일 흐름이므로 영향 없음(원래 정상이었던 PDF는 별도 §frontend §12-10/-11과 묶인 viewport CSS 회귀가 있었음).
    - **박제 후기**:
      - **3중 동기화 invariant**: outline 항목 제목 → 백엔드 `utils.text_utils.slugify` (writer가 파일 저장 시 사용) → 프론트 `lib/data.ts:slugifyTitle` (파일↔섹션 매칭) → 백엔드 `/api/export` (이번 추가). 한 곳만 규칙이 바뀌면 전부 깨짐. §7-2/§12-8/§12-13-9 와 동일 라인 위에 있음.
      - **prefix 재도입 검토 거절**: writer가 `{N}-` prefix를 다시 붙이는 옵션도 있었으나 (a) 기존 신형 파일들 일괄 rename 비용 (b) outline 항목 순서 변경 시 파일명도 따라 바꿔야 하는 양방향 의존 발생 (c) 슬러그 자체가 이미 사람이 읽기 좋은 파일명 — 셋 모두 부정적이라 fallback 추가가 정공법.
      - **잔여 위험**: outline 항목 슬러그가 동일한 두 섹션이 들어오면 첫 매칭만 잡힘. 현재 outline은 모두 고유 제목이라 문제없으나 §12-13-9 의 동명이섹션 시나리오와 결합 시 위험. 그때는 outline 인덱스를 우선 쓰는 별도 로직 필요.

    13-11. **llm_call 메트릭 라인의 `topic_slug: null` 정합성** — 상태: `pending` / 의존: §12-13-6 (a) / 우선순위: 낮음 (cosmetic, 분석 영향 없음)
    - 발견 (2026-05-05 §12-13-6 (a) 검증 4단계 직후): `logs/metrics.ndjson` 의 `type: "llm_call"` 라인 2건 모두 `"topic_slug": null`. 다른 type (set_round, query_issued 등) 도 topic_slug 안 들어가는 건 동일하나, llm_call 은 우리가 박제한 의도가 "section + topic_slug 로 어느 토픽에 어떤 섹션 호출했는지" 추적인데 topic_slug 누락으로 토픽별 집계 불가.
    - 진단: `tools/metrics.py:record_llm_call()` 이 `REG.topic_slug` 를 직접 읽음. set_topic_slug 가 호출되어 REG.topic_slug 가 채워지는 시점과 record_llm_call 호출 시점 사이에 어딘가에서 reset 되거나, 혹은 REG.topic_slug 가 이번 라운드에서 처음부터 set 안 됨. set_topic_slug 호출처 점검 필요.
    - 검토안: (a) record_llm_call 호출 측(section_writer)에서 명시적으로 topic_slug 인자 전달 — `state.get("topic_slug")` 를 그대로 넘김. (b) set_topic_slug 호출 위치를 supervisor/세션 진입점에 강제. (a) 가 호출 측 한 줄 추가로 끝나는 정공법.
    - 진입 트리거: 일별 토픽별 호출 집계가 필요해질 때 또는 별도 cosmetic 정리 시.

14. **§12-14 — 사용자 관점 진행 이벤트 채널 (frontend LogPanel 헤더 공급)** — 상태: `closed (2026-05-05)` / 의존: 없음 / 우선순위: 중

    **출처**: 프런트엔드 사용자가 진행 로그(원시 백엔드 로그) 가 개발자용이라 "지금 어느 단계에서 작업 중인지" 한눈에 안 보인다는 보고. 짝 박제: `Bell_Agent/frontend/README-dev.md` §12-12.

    **설계**:
    - 원시 logger 파이프(`_LOG_BUFFER` + `/api/logs`) 와 별개의 **구조화 이벤트 채널** 신설. 같은 패턴(deque + lock + cursor 폴링) 미러.
    - `core/events.py` (신규): `_EVENT_BUF` (`deque[(seq, ts, label, kind, detail)]`, maxlen=200), `_EVENT_LOCK`, `_EVENT_SEQ`. 공개 API:
      - `emit_event(label, kind="phase", detail=None)` — 노드 진입 시 한국어 라벨로 적재.
      - `get_events_since(cursor, limit) -> (next_cursor, events)` — cursor 폴링.
      - `clear_events()` — `api_run` 진입 시 호출 (명령 한 번 = 워크플로 한 흐름 정책).
      - `latest_event()` — 최신 이벤트 조회.
    - `app.py`: `/api/events?cursor=...&limit=...` 엔드포인트 + `api_run` 의 lifecycle 이벤트 (`작업 시작` / `작업 완료` / `오류 발생`).
    - 9개 노드 진입에 한 줄씩 `emit_event` 박음. 라벨은 사용자 친화적 한국어 (노드 이름 그대로 X):
      - `supervisor` → `"작업 분석"`
      - `communicator` → `"응답 정리"`
      - `content_strategist` → `"목차 구성"`
      - `research_planner` → `"조사 계획 수립"`
      - `research_synthesizer` → `"참고문헌 정리"`
      - `vector_search_agent` → `"참고문헌 검색"`
      - `web_search_agent` → `"웹 검색"`
      - `section_writer` → `"섹션 본문 작성"`
      - `chapter_writer` → `"장 본문 작성"`
    - 박제 위치 관습: 각 agent 함수의 `logger.info("============ NAME ============")` banner **직후**. 조기 return 분기(예: section_writer 의 `DOC_MODE != "report"`, web_search 의 `qa_direct_reply`) 보다 뒤에 두어 실제 노드가 실행될 때만 발화하도록 함.

    **순환 의존 회피**: `app.py → graph.py → agent/* `구조라 agent 가 app.py 를 import 하면 순환. 그래서 버퍼/헬퍼를 `core/events.py` 에 두고 app.py 와 agent/* 가 일방향으로 import.

    **버그 1건 close (cursor reset 미감지)**:
    - 시나리오: Run 1 후 frontend cursor=7. Run 2 시작 → `clear_events()` 가 `_EVENT_SEQ=0`, buffer 비움 → 첫 emit 으로 seq=1 발생. Frontend polls cursor=7 → buffer 의 seq=1 < 7 이라 필터 통과 못함, `out=[]`, naive 구현은 `next_cursor = int(cursor) = 7` 반환 → frontend reset 감지 조건 `next_cursor < cursor` 가 `7 < 7 == false` → 영원히 새 이벤트 못 받음.
    - 패치: `get_events_since()` 에 명시 reset 신호 추가 — caller cursor 가 현재 `_EVENT_SEQ` 보다 크면 즉시 `(_EVENT_SEQ, [])` 반환. frontend 는 `next_cursor < cursor` 로 감지 → cursor=0 으로 reset → 다음 폴링에서 첫 이벤트부터 새로 받음.
    - 일반화: backend reset + monotonic-from-zero seq 패턴은 frontend 의 단순 cursor 비교 폴링과 충돌. 다른 cursor 채널 추가 시 동일 가드 필요.

    **운영 규칙**:
    - 새 LangGraph 노드 추가 시 `agent/<node>.py` 의 banner 직후에 `emit_event("...")` 한 줄 의무. 라벨 누락 시 frontend 헤더가 이전 단계에 정체.
    - 라벨은 한국어 사용자 표현으로 (노드 이름이 아니라). frontend `LogPanel.tsx` 가 그대로 노출하므로 가독성 우선.
    - 명령 한 번 = 이벤트 흐름 한 번. `clear_events()` 는 `api_run` 외에 다른 곳에서 호출 금지 (frontend reset 감지 가정 위배).
    - `kind` 4종: `"phase"` (기본, 노드 진입), `"start"` (api_run 시작), `"done"` (api_run 정상 종료), `"error"` (예외). frontend 는 done/error 면 펄스 애니메이션 정지 + 색상 변경.

    **검증**: 백엔드 재시작 후 명령 두 번 연속 실행. 첫 명령 "대기 중" → "작업 시작" → "작업 분석" → ... → "작업 완료" 흐름. 두 번째 명령 시 1.5s 내 헤더 라벨 갱신 시작 (cursor reset 정상 동작).

    **잔여**:
    - `tools/metrics.py` 의 `record_*` 와 `core/events.py` 는 별개 채널 (운영 분석용 NDJSON vs 사용자 UI용 인메모리). 통합 검토는 우선순위 낮음 — 목적과 수명이 달라 분리 유지가 자연스러움.
    - communicator 등 일부 노드는 함수 본문 안쪽에 banner 가 있어 emit_event 위치도 그에 맞춰 깊숙이 배치됨. 향후 banner 위치 정리 시 emit_event 도 같이 옮길 것.

15. **§12-15 — 라우터의 in-memory references vs disk rag_on_disk 분리 가드 (서버 재시작 직후 write fast-path 우회 버그)** — 상태: `closed (2026-05-05)` / 의존: 없음 / 우선순위: 높음

    **출처**: 사용자 보고 — "백엔드 서버 재시작하고 프런트엔드에서 write:섹션 하면 RAG 없다고 가정하고 web_search 부터 하고 vector_search 안 하고 section_writer 로 감. 실제로는 RAG 있어서 web_search 불필요, vector_search 후 section_writer 가 정답인데."

    **현상 (재시작 직후 write 명령)**:
    - supervisor 본함수: `rag_on_disk=True` (Chroma ns_web=73 + ns_local=349 = 422 청크 영속) 정확히 인식 → `[Supervisor fast-path] write + rag_on_disk → vector_search → section_writer` 의도 표명, `task_history=[section_writer, vector_search_agent]` 등록 + `flags.pending_write_title=True`.
    - 그런데 직후 supervisor_router 가 `============ WEB SEARCH AGENT ============` 로 분기. web_search 후 `[router.after_web] writer pending(strict) → section_writer` 로 vector_search 통째로 스킵. 의도 라우팅 회로가 통째로 빗나감.

    **루트 원인 (라우터 두 군데, 같은 가정 누락)**:
    - `agent/supervisor.py:supervisor_router` (L1013-1023): `if has_writer_p and pending_write_title: if refs_empty: return "web_search_agent"` — `state["references"]["docs"]` (in-memory, 서버 재시작 시 휘발) 만 보고 `state["rag_on_disk"]` (디스크 Chroma 메타) 무시. 서버 재시작 직후엔 references 가 빈 dict 라서 가드가 잘못 발화하여 web_search 강제.
    - `core/routers.py:after_web_search_agent` (L552-564): 웹검색 끝난 뒤 `pending_write_title=True && has_writer_p=True` 면 vector_search 펜딩 검사 없이 바로 `return preferred_writer` 직행. 결과적으로 retrieval 단계 자체를 스킵하고 빈 references 로 본문 생성.

    **패치**:
    - `agent/supervisor.py:1013-1027` — `has_on_disk = bool(state.get("rag_on_disk"))` 추가, 가드를 `refs_empty and not has_on_disk` 로 강화. refs 비어있어도 rag_on_disk=True 면 web_search 안 가고, vector_search_agent 펜딩이면 그쪽 우선, 아니면 writer 직행.
    - `core/routers.py:560-568` — web_search 후 writer-pending 분기에서 `return preferred_writer` 직전에 `if has_pending(state, "vector_search_agent"): return "vector_search_agent"` 한 줄 추가. retrieval 단계가 통째로 스킵되어 빈 본문이 나가는 사고 차단.

    **검증 (동일 시나리오, 백엔드 재시작 후 `write: 고함량 활성비타민 시장 환경 및 규제 동향 분석` 재실행)**:

    | 항목 | 패치 전 | 패치 후 |
    |---|---|---|
    | 파이프라인 | supervisor → **web_search** → section_writer | supervisor → **vector_search** → section_writer |
    | 처리 시간 | 22:31:28 → 22:32:37 = **69초** | 22:58:48 → 22:59:16 = **28초** |
    | retrieval | web_search 4건 fetch, 모두 `attach_auto_citations skip unverified` → 인용 **0개** | dual-retrieve web=3 / local=2 → 검증된 ref **5개** |
    | top sources | dailypharm.com 3건 (모두 unverified) | 종근당_팩트북.pdf, 벤포벨 광고효과조사 PPT, dailypharm/91137 |
    | draft 본문 | 3530 chars / 8338 bytes (인용 없는 산문) | 2942 chars / 7180 bytes (검증된 RAG 기반) |

    **일반화 교훈 (다른 라우터/가드에도 적용)**:
    - **in-memory state 와 disk state 를 분리해서 가드**: `state["references"]` (휘발성, 세션 단위) vs `state["rag_on_disk"]` / `state["rag_stats"]` (영속, 디스크 메타). 라우터는 둘 다 봐야 함. references 비어있다고 RAG 자체가 없다고 가정하면 서버 재시작 직후 / 새 세션 첫 명령에서 빗나감.
    - **fast-path 의도와 라우터 결정의 정합성 점검**: supervisor 본함수의 `[fast-path] ... → A → B` 로그와 직후 `============ A 또는 B ============` banner 가 일치하는지 운영 점검 항목으로 추가. 어긋나면 supervisor_router 의 가드가 본함수 의도를 무력화하는 케이스 의심.
    - **retrieval 단계 스킵은 사고**: writer-pending 가드가 retrieval(vector_search) 펜딩보다 우선하면 빈 references 로 본문 생성 → unverified citation 0개 + LLM hallucination 위험. 라우터 가드 우선순위는 `vector_search 펜딩 → writer 직행` 순서가 정답.

    **짝 박제**: 프런트엔드 측 `Bell_Agent/frontend/README-dev.md` §12-13 (사용자 origin, 현상). 본 §12-15 가 백엔드 패치 본체.

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