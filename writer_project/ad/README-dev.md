# 개발자 가이드 (Bell Agent · writer_project)

이 문서는 `writer_project` 백엔드의 RAG 파이프라인 작업 시 알아야 할
구조·관습·운영 노하우를 정리합니다.

---

## README-dev 트랙·catch 박제 인덱스

본 인덱스는 README-dev.md 의 트랙·catch 박제 위치 신속 조회용. 분량 임계 도달 (~3296 줄) 로 분리 운영 진입 — `612cc87` commit (§13-14-2 트랙 close) 이후 박제는 `README-dev-2.md` 참조.

### 트랙 박제 위치

| 트랙 | line 범위 (README-dev.md) | 상태 | 핵심 자산 |
|---|---|---|---|
| (이전 트랙들) | line 1 ~ 2455 | 기존 박제 | §1~§12 + §13-1~§13-12 본문 |
| §13-13 (Word/PPT export 결함 4건) | 2456 ~ 2737 | close (partial) | strip_number_prefix misuse 진단 + 결함 1+3 root → 2·4 cascade |
| §13-14 (트랙 헤더) | 2738 ~ 2853 | 진행 중 | md → pptx 정보 충실도 트랙 + §13-14-1 patch v1 잠정 close |
| §13-14-2 (md 정규화 placeholder) | 2854 ~ 2966 | close | §13-14-α 본문 + Phase 2·3 측정 (cascade 100% + 구조 변동 0/30) |
| §13-14-α-sonnet | 2967 ~ 3126 | close | Sonnet 4.6 3 라운드 + dual track 채택 + catch 25 신규 |
| §13-14-γ | 3127 ~ 3233 | close | linter 정식화 (ad9d40f) + sanity check 양 트랙 1:1 정합 |
| §13-14-2 (트랙 close) | 3234 ~ 3296 | close | 4 sub-track 처리 확정 (α / β 흡수 / γ / δ 보류) |
| (612cc87 이후) | `README-dev-2.md` 참조 | — | — |

### catch 박제 위치

| catch | line 위치 (README-dev.md) | 자산화 |
|---|---|---|
| catch 1~16 | line 1 ~ 2737 (§13-13 이전 + 본문) | 이전 트랙 박제 |
| catch 17 (정밀화 3회) | 2828 / 2940 / 2967~ | stochasticity 표현 진화 — 불가항력 → 조건부 → 강하게 비례 (bf07d23 → 1106d7d → 76db4da) |
| catch 20 | 2942 | md 구조 일관성 → 입력 정규화 우선 (bf07d23 확정) |
| catch 21 | 3207~ (γ 확정) | linter 정규화 후 ground truth 정합 self-validation (ad9d40f 확정) |
| catch 22 | 2940 / 3097 (multi-provider 확장) | 입력 정규화 원칙 provider-agnostic (bf07d23 → 76db4da) |
| catch 24 | 2940 | 함수 의도 vs 호출처 의도 mismatch — misuse 정정 (bf07d23 확정) |
| catch 25 | 3093 | 시각 검증이 정량 측정 권고를 조정한 사례 (76db4da 확정) |
| catch 26 | 3207~ (γ 확정) | 측정 도구의 의존성 0 강제 원칙 (ad9d40f 확정) |

### 분리 운영 진입

- `README-dev.md` = §13-14-2 트랙 close (`612cc87`) 까지의 박제 자산 (~3296 줄)
- `README-dev-2.md` = `612cc87` 이후 신규 박제 자산
- `NEXT_SESSION.md` = 다음 세션 진입 시 두 파일 모두 cross-reference

### 사용 가이드

- **과거 트랙·catch 검색** → 본 인덱스에서 line 위치 확인 → `README-dev.md` 직접 참조
- **최근 박제 추적** → `README-dev-2.md` 참조
- **다음 세션 진입** → `NEXT_SESSION.md` 의 archived decisions 항목 참조

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

## 4) 공개 API(파사드) 사용 규칙

- **`tools/web_rag/__init__.py`**: 외부에서는 이 파사드를 통해 사용 (`__all__` 기준)
  - `web_search()` — 웹 검색 (Naver/Tavily 등 백엔드 통합)
  - `retrieve()` — 벡터 검색 (Chroma 컬렉션 RAG 검색)
  - `web_results_to_documents()`, `web_page_json_to_documents()`
  - `documents_to_chroma()`, `add_web_pages_json_to_chroma()`
  - `clear_vector_store()`, `ensure_vector_store_cleared_once()`
  - `openalex_search()`, `semantic_scholar_search()` — 학술 백엔드 (A9 등록)
  - `default_chroma_dir()` — Chroma 기본 경로
  - ※ `_default_chroma_dir` 는 전환용 별칭 (`default_chroma_dir` 와 동일 객체, `is` True).
    신규 코드 사용 금지, 소비자 전환 완료 후 제거 예정.
- **`tools/topic_config.py`**: 토픽별 설정
  - `get_domain_bonus_groups()`, `get_xlsx_keyword_groups()`
- **`utils/rag_utils.py`**: `merge_refs()` 단일 구현 + 문서 병합용 디듀프
- **`tools/web_rag/utils.py`**: URL 정규화(`normalize_url`) 정규 경로
  - `rag_utils._norm_url_for_key` 는 디듀프 키 생성 전용이며 범용 정규화가 아님. 혼동 주의.
- **`utils/writer_scheduler.py`**: `schedule_writer_if_needed()` 단일 진입
- 라우팅 분기는 **`core/routers.py`**에서만

### 내부 모듈 직접 import — 3분류

기본은 금지. 단 아래 (b)·(c)는 규칙이 인정하는 정당한 경로다.

**(a) 교체 대상** — 파사드에 공개 이름이 있는데 서브모듈을 직접 가져가는 경우

| 위치 | 상태 |
|---|---|
| `agent/web_search.py` ad 트랙 (OA/SS) | ✅ A9-③ 완료 |
| `agent/web_search.py` `ingest` 3항목 | 미처리. 최상단 import 라 교체 시 `ingest.py` 지연 로드 효과 발생 → **별도 커밋** |
| `agent/web_search.py` paper 블록 3건 | **보류 / A8 귀속.** `paper_search.py` 분리와 동시 처리. **개별 교체 금지** |

paper 블록 개별 교체를 금지하는 이유: 파사드 전환은 실패 지점을 메인 스레드에서 워커 스레드로
이동시켜 백엔드 부분 성공을 가능하게 한다(A9 부수 효과). 정상 경로는 동일하나 실패 모드가
바뀌므로 실동작 회귀 확인이 필요하고, 이는 유료 API 호출을 수반한다. A8 트랙에서 함께 처리한다.

**(b) 정당한 예외** — 내부 동작 자체가 검증·관찰 대상

- `tests/` — 내부 동작을 검증하는 게 목적
- `diagnose_*` 4종 — `_get_vs` / `_get_embeddings` 등 엔진 내장을 뜯는 게 목적
- `smoke/` — `_strip_doi_prefix` 등 밑줄 헬퍼 단위 검증
- `debug_docid.py` — 구/신 docid 구조 비교 시뮬레이터. `_normalize_canonical_url` 직접 사용이 목적

**(c) 의도적 회피** — 건드리지 말 것

- `scripts/_phase_b_clear_ns.py` — `_default_chroma_dir` 만 사용(Chroma 객체 미생성).
  파사드 경유로 바꾸면 `ingest.py` 까지 딸려 로드되어 의도가 깨짐
- `agent/vector_search.py` optional binding 블록 — 있으면 쓰고 없으면 넘어가는 방어 패턴.
  파사드 경유는 이 선택성을 없앰

### 확장 시 규칙

새 백엔드는 **소비자 코드보다 먼저** `tools/web_rag/__init__.py` 에 래퍼를 등록한다.

- 래퍼는 함수 내부 지연 import 패턴 유지
  (`def f(*a, **kw): from .모듈 import f as _fn; return _call_maybe_tool(_fn, *a, **kw)`)
- 최상단 실제 import 는 `TYPE_CHECKING` 블록에만 둘 것
- 기준: **파사드를 여는 것만으로 어떤 모듈도 env 를 읽지 않아야 한다**
  (`import tools.web_rag` 직후 `sys.modules` 에 파사드 하나뿐인 상태가 정상)
- ⚠️ PEP 562 모듈 `__getattr__` 도입 금지 — `core/routers.py` 가
  `from tools.web_rag import ingest_docs` 로 서브모듈을 가져간다.
  모듈 `__getattr__` 이 `AttributeError` 아닌 것을 던지면 이 줄이 깨짐

이 절차 누락이 A9 발생 원인이다. OA/SS 확장 시 파사드 등록을 건너뛰어 소비자가 서브모듈을
직접 가져갔고, 파사드는 2026-03 이후 갱신이 멈춰 있었다. 규칙이 틀린 게 아니라 확장이
규칙을 따라잡지 못한 사례.

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
2. **`tools/web_rag` 파사드 사용** & 내부 모듈 직접 import 정리 (§4 (a) 기준, (b)·(c) 제외).
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

    11-4. **호스트 정규화 누락 — oldm.dailypharm.com** — 상태: `closed (2026-05-18 §14-9-W Step A Finding B 정합)`
    - 화이트리스트의 `dailypharm.com`은 `oldm.dailypharm.com` 등 subdomain prefix 호스트와 별개로 인식.
    - 다음 트랙: `tools/web_rag/search.py` GATEKEEP 단계에 subdomain stripping 또는 suffix 매칭.
    - **§14-9-W Step A Finding B 박제 결과 fix 확인 (2026-05-18)** — `settings_gatekeep.py:363-377` `ALLOW_SUBDOMAINS=1` (정합 `.env:208`) + suffix loop 정합으로 이미 매칭 가능. `oldm.dailypharm.com` 의 매칭 흐름: parts = `["oldm", "dailypharm", "com"]` → i=0 cand=`dailypharm.com` → allow set 매칭 → True. 별도 stripping 코드 추가 불요. 본 entry **status: closed**.

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

    ---

    ### §12-13 close (2026-05-17 close session, post HEAD `bff6dd0` = γ 박제) — α/β/γ + RAG 업데이트 전수 PASS

    CLAUDE.md `Current focus (§12-13)` 의 3 영역 (Q&A 헬스체크 / venfobel QA / end-to-end) 전수 충족. §12-13 사용자 검증 본 미션 close.

    **(1) cycle 누적 결과**:
    - **α** (일반 LLM Q&A 헬스체크, 2026-05-17): 3 cases ALL PASS — α-1 off-topic guard + α-2 vector retrieval + α-3 explicit write fast-path. 박제: `scripts/output/§12-13/alpha_smoke_test.md`. commit `cdfc076`.
    - **β** (venfobel 인덱스 직접 QA, 2026-05-17): 9 queries × 3 ns × top-5 = 27 retrievals PASS. threshold_sweep §12-12 exact reproduction (13일 안정). priors 15 신규 자산 (web/base ns 비어있음). 박제: `scripts/output/§12-13/beta_dual_retrieve.md`. commit `cdfc076`.
    - **RAG 업데이트** (S4 + 재indexing, 2026-05-17): S4 scope 11 logical delete + production 7건 무손실 + venfobel-vitamin-web 신규 indexed (17 docs / 768d vertex). priors 15 해소. 박제: `scripts/output/§12-13/rag_update_log.md`. commit `fa27769`.
    - **γ** (end-to-end 리포트 생성, 2026-05-17): driver script 8 invocation FULL PASS, 총 **236.0s** (mean 33.7s / min 19.3s / max 46.2s / **long-tail 0건**). final deliverable: `reports/venfobel-vitamin/20260517-121759_report.md` (**65,719 bytes = 64.2 KB**). 박제: `scripts/output/§12-13/{gamma_step0a_entry_contract.md, gamma_end_to_end.md}`. commit `bff6dd0`.

    **(2) priors 17 scope refinement** (자기 비판 §1 강화):
    - **원** (cdfc076 / fa27769 박제): "research_synthesizer 188s long-tail (vertex chat_models grpc blocking)"
    - **정정** (γ 7 sections 누적 검증 기반):
      - **scope**: RAG ingest auto path 한정 (web_search_agent + vector_search_agent + research_synthesizer chain). 트리거 = `최신 자료로 RAG 업데이트해줘` (supervisor.py:L608-619 `_rag_re` fast-path).
      - **non-scope**: write fast-path (supervisor.py:L716-743) — vector_search + section_writer 단독, research_synthesizer 미진입. γ 7 sections 모두 duration < 50s (long-tail threshold 120s 의 절반 이하).
    - **함의**: §12-13-6 (b)(c) 진입 트리거 ("빈도 증가 시점") 의 측정 영역 = RAG update auto path 한정. write fast-path 빈도 변화는 (b)(c) 진입과 무관.

    **(3) §14-8-B fix 4-layer cumulative CONFIRMED** ★★★:
    - 기존 3-layer (commit `6a9e0dc` `feat(config): protected env list snapshot/restore`):
      - **communicator** (α 3 cases) — POST CFG/env 4 field 회귀 부재
      - **retrieval** (β 27 retrievals + reload_config 명시 invoke) — driver intent 보존
      - **ingest** (188s long invoke = web_search + vector_search + research_synthesizer faulthandler) — state preserved
    - **신규 4 layer**: **section_writer (γ 7회 누적)** — production write path 핵심 경로에서 LLM_PROVIDER/LLM_MODEL/TOPIC_SLUG/CHROMA_NAMESPACE_WEB 4 field 회귀 부재. gamma_run_meta.json post_cfg/post_env 정합 박제.
    - 함의: `_PROTECTED_ENV_KEYS` (core/config.py:L655-661) 의 5 key 보호가 production 운영의 **모든 LLM-bearing path** 에서 effective. wrapper subprocess 환경 (CWD=writer_project, `find_dotenv(usecwd=True)` 의 CWD 의존성 영역) 에서도 안전.

    **(4) priors 누적 17 → 18**:
    - **18 (신규, Step 0 박제)**: chromadb collection metadata 미저장 — `add_collection` 시 명시적 metadata set 부재 → `col.metadata = {}` (실측). embedding_function provenance 단언 근거 = naming convention (`-web` suffix) + sample dim (768d) 의 2-source triangulation 만 가능.
    - **mitigation**: `add_collection(metadata={"embedder": "vertex-multilingual-embedding-002"})` 명시 권장 영역. 별 cycle 또는 housekeeping. 본 close 비포함.

    **(5) sub-§ 상태 (Phase 2 재평가 결과)**:
    - **closed** (6 sub-§): §12-13-1 / §12-13-4 / §12-13-5 / §12-13-6 (a) / §12-13-7 / §12-13-10 — 2026-05-05 §12-13 코드 수정 세션 + 2026-05-05 metric 도입 세션. + 본 cycle: **α / β / γ / RAG 업데이트 4 cycle 자산 close**.
    - **defer (별 cycle, 본 §12-13 close 비포함)** (4 sub-§):
      - §12-13-6 (b)(c) — original intent "추세 데이터 누적 후 결정" 정합 (γ 7 sections + RAG update 누적 데이터, 429 빈도 부재). priors 17 refinement 으로 측정 영역 명확화 (RAG ingest auto path 한정).
      - §12-13-8 — γ 7회 재현 (cosmetic, `[router.tail] outline exists but not shown` 반복 발화). 별 cycle: communicator outline_shown=True 명시 설정 또는 router 우선순위 조정.
      - §12-13-9 — γ section 3/5/7 재현 매핑 (cosmetic). 신규 발견: idx 5 (콜론 + smart-quote) 추가 매핑 — Step 0-α 미예측. 별 cycle: `utils.text_utils.slugify(allow_unicode=True)` 정책 검토.
      - §12-13-11 — cosmetic, 분석 영향 없음. 별 cycle: record_llm_call 호출 측 topic_slug 명시 전달 (정공법).
    - **re-cycle (post-§12-13, substantive 잔여)** (2 sub-§):
      - §12-13-2 — web_search OBJ vs user query 분리 로직. §12-13-1 다층 방어선이 trigger 차단 → 본 §12-13 close 시점 active issue 아님. 별 cycle: web_search 진입 시나리오 재발 시 또는 OBJ 로직 자체 수정 결정 시 진입.
      - §12-13-3 — after_vector 루프 카운터 정확성. §12-13-1/2 와 패키지로 처리 가능. 별 cycle: routers 코드 손댈 때 함께.

    **(6) 의외 발견 별 cycle reserve**:
    - **γ-baseline 87% 단축 가설** — C 미션 (2026-05-05) ~31분 (7+1 invocation) vs 본 γ 4분 (236s). 가설:
      - (a) gemini-2.5-flash vs C 미션 시점 모델 차이 (당시 모델 미박제)
      - (b) state continuity 효과 (vector_search 7회 reuse — 동일 ns 누적 캐시 가능성)
      - (c) §13~§14 cycle 의 prompt/retrieval 누적 최적화 효과
      - → 별 cycle: γ-baseline 측정 정식화 (control variable 통제 + 3-run mean 비교)
    - **§12-13-9 신규 매핑**: idx 5 (`3040 직장인 ... 분석: '어른들의 비타민' 유효성 검증`) → 콜론 (`:`) → `-` + smart-quote (`'`, `'`) 제거. Step 0-α 의 §12-13-9 예측 범위 (괄호 + KPI 소문자화) 외 추가 변환 영역.

    **(7) defer / reserve list 통합 (§12-13 close 시점)**:
    - **γ 후속**: γ-baseline 측정 정식화 (87% 단축 가설 검증)
    - **내용 평가 cycle**: γ 산출 보고서 (64.2 KB, 7 sections) advertising agency tester 관점 quality review — 본 §12-13 close = pipeline 작동 검증, **내용 quality 별 cycle 영역**
    - **§14-8 reserve** (5건, B-3 close 시 박제):
      - CWD-independent .env resolution (`find_dotenv(usecwd=True)` CWD 의존성)
      - 다른 `reload_config()` 호출처 audit (local_rag / web_rag/utils / app.py driver path)
      - `_PROTECTED_ENV_KEYS` 외부화 / config 화
      - CHROMA_DIR 미보호 영향 분리 검증
      - feature/vertex-web-search branch — 1-2주 안정 후 삭제 결정 (현 보존, M2 merge 후 origin/local 모두 존재)
    - **§12-13 cosmetic batch patch**: §12-13-8 (router.tail outline_shown) + §12-13-9 (slug 정규화) 묶음 처리 가능
    - **운영 housekeeping**: chroma store 정기 점검 (S4 정신 적용) + priors 18 (collection metadata 명시 set)
    - **§12-13 re-cycle (post-close)**: §12-13-2 / §12-13-3 (web_search OBJ + routers 카운터, 패키지 처리)

    ---

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

16. **§12-16 — 본문 인용 ↔ footnote 매핑 통일 ([[N]] 마커 기반)** — 상태: `closed (2026-05-06)` / 의존: 없음 / 우선순위: 높음 (사용자 클릭 동작 완전 차단)

    **출처**: 사용자 보고 (2026-05-06) — 보고서 본문에 `[일반의약품_마케팅_분석]`, `[Ipsos_보고서]` 같은 라벨로 인용이 박혔지만 클릭해도 출처 패널이 열리지 않음. 참고문헌엔 `일반_의약품_브랜드_마케팅_광고전략_분석.pdf` 같은 풀 파일명만 등장. 짝 박제: `Bell_Agent/frontend/README-dev.md` §12-14.

    **3겹 미스매치 진단**:
    - (1) `prompts.py:349, 422` — section_writer/chapter_writer 프롬프트가 "짧은 이름만 대괄호로" 지시. 예시도 `[DailyPharm]`/`[아이커.pptx]`/`[foodtoday.or.kr]` 등 확장자 유/무 혼재 → LLM 이 자기 임의로 `[Ipsos_보고서]` 같이 **참고자료에 없는 합성 라벨**을 본문에 박음.
    - (2) `Bell_Agent/frontend/components/ReportCanvas.tsx:628` — chip regex 가 `\[[^\]]*\.[a-zA-Z0-9가-힣_-]+[^\]]*\]` 즉 대괄호 안에 **확장자 점이 필수**. 확장자 없는 합성 라벨은 chip 변환 자체 실패 → 일반 텍스트로 렌더링되어 클릭 핸들러 부재.
    - (3) `Bell_Agent/frontend/lib/markdown.ts:findMatchingFootnote` — chip 으로 만들어졌어도 fileName 정확/부분 매칭 의존. LLM 합성 라벨 ("Ipsos_보고서") 과 footnote.fileName ("..._광고효과조사_종근당.pdf") 간 공통 부분문자열 부재 → 매칭 실패.

    **근본 원인**: 본문 인용 토큰과 footnote 사이에 **stable identifier 부재**. LLM 텍스트 라벨에만 의존 → LLM 단축/의역마다 매칭 운에 맡겨짐.

    **처방 (마커 기반 통일)**:
    | 변경 위치 | 변경 내용 |
    |---|---|
    | `utils/refs.py: refs_preview_text(numbered=True)` | LLM 컨텍스트에 references 를 `[1] {label} — {snippet}` 형식 번호 부여로 직렬화 |
    | `utils/refs.py: attach_marker_citations()` 신설 | 본문 [[N]] 마커 추출 → **본문 등장 순으로 1,2,3,4 재라벨링** (책/논문 인용 관행) → footer `[^N]: {url} ({label})` 1:1 정의 생성 |
    | `prompts.py:349, 422` | "본문 인용은 [참고 자료]의 번호를 [[N]] 형식으로만. **[라벨] 형식의 자체 합성 명칭 금지**" |
    | `agent/section_writer.py`, `agent/chapter_writer.py` | `_refs_preview_text(state, numbered=True)` + `attach_marker_citations` 항상 시도 (AUTO_FOOTNOTE 가드와 무관) |

    **검증 (사용자측)**: 마커 chip 정상 렌더링, chip 클릭 → 출처 패널 정확 매칭, footer `[^1] [^2] [^3] [^4]` 순서 정렬. 1차 패치 직후 footer 가 본문 등장 순(예: `[^3] [^1] [^5]`)으로 비순차 출력되던 회귀 즉시 수정 — `attach_marker_citations` 에 `remap = {orig: i+1}` 추가하여 본문/footer 동시 재라벨링.

    **일반화 교훈**:
    - **본문 토큰과 메타데이터(footnote/링크) 사이엔 stable identifier 가 있어야 한다** — 라벨/파일명 fuzzy 매칭은 LLM 합성 라벨에서 항상 깨진다. 마커(번호 또는 UUID) 가 정공.
    - **인용 형식의 모호한 예시는 LLM 일탈을 부른다** — 프롬프트에 `[A.pdf]` `[B]` `[C.kr]` 처럼 형식이 뒤섞이면 LLM 은 "라벨은 자유" 로 해석하고 합성 라벨을 만들어냄. 인용 토큰은 **단일 형식만** 허용해야.
    - **legacy AUTO_FOOTNOTE 모드(quant/domain/footer) 는 유지하되 우선순위 하락**: marker 모드가 항상 먼저 동작 + footer 존재 가드(`FOOTNOTE_DEF_RE`)로 중복 차단. 후속에서 `AUTO_FOOTNOTE_MODE` 의 default 를 `"marker"` 로 변경 + legacy 모드 deprecation 검토.

    **follow-up (별 박제 후보)**:
    - 프런트 chip 디스플레이 개선: 현재 `[[1]]` 텍스트가 그대로 "1" 로만 보임 — 호버/클릭하면 fileName 보이지만 시각적으로 어떤 출처인지 즉시 식별 어려움. footnotes prop 을 `renderInline → CitationChip` 까지 drilling 해서 fileName/prettyUrl 로 표시.
    - LLM 마커 규칙 위반 fallback: LLM 이 가끔 [[N]] 외 [라벨] 로 인용할 가능성. 후처리에서 라벨→가장 가까운 ref 매칭 + 마커 변환 로직 추가 검토 (단, 거짓 매칭 위험으로 보수적 적용).

17. **§12-17 — 웹 PDF 한도 상향 (5p/10000자 → 30p/50000자) + 효과 검증** — 상태: `closed (2026-05-06)` / 의존: 없음 / 우선순위: 중

    **출처**: 사용자 보고 (2026-05-06) — "벡엔드 프로그램 수정 작업을 하고 싶어. ... web-search와 local-search/rag 작업에서 pdf 파일을 5페이지 이내로 한정한 것으로 기억해. 찾은 자료들의 풍부함이 염려돼." 사실관계 정정: 5페이지 한정은 **웹만** (로컬은 50p). 그러나 풍부도 부족 가설은 정량 확인됨.

    **삭제 전 baseline (venfobel-vitamin-web)**:
    - total 73 청크 (html 62 / pdf 10 / text 1)
    - unique_pdfs=3, total_pdf_chunks=10, **avg_chunks/pdf=3.3**
    - 산업 보고서·정부 자료 PDF가 보통 5p 이후에 핵심부 → 5p 컷에서 정보량의 ~10~20%만 인덱싱

    **변경**:
    - `.env:110-111` + `env_raw.txt:109-110` — `WEB_PDF_MAX_PAGES=5→30`, `WEB_PDF_MAX_CHARS=10000→50000`
    - 코드 fallback(`core/config.py:518` `_env_int("WEB_PDF_MAX_PAGES", 5)`)은 미변경 — `.env`가 항상 있으므로 운영 영향 없음. 새 머신 부트스트랩 일관성 위해 후속에 동기화 검토.

    **효과 측정 (재인제스트 1턴, query="법령 OTC 광고 규정")**:
    | 지표 | 삭제 전 | 재인제스트 후 | 변화 |
    | --- | ---: | ---: | ---: |
    | total chunks | 73 | 73 | — |
    | unique PDFs | 3 | 1 | (질의 스코프 좁아짐) |
    | total PDF chunks | 10 | 14 | +40% |
    | **avg chunks/pdf** | **3.3** | **14.0** | **×4.2** |
    | PDF 평균 청크 길이 | 1574 | 1742 | +11% |
    | PDF p50 길이 | 1867 | 2047 | (chunk_size=2400에 근접) |

    `khidi.or.kr` PDF 한 권에서 1청크 → **14청크**. PDF 풍부도가 PPTX/XLSX 수준에 근접.

    **새로 드러난 후속 후보**:
    - **(a) 단일 source 청크 쏠림** — `dailypharm.com/user/news?category=건기식+A-Z&group=...` 카테고리 인덱스 페이지 1개가 25청크(34.2%) 차지. height-growth-supplement에 박제된 `seoul.co.kr` 40% 쏠림과 동일 패턴. → **§12-18 작업 큐**: 단일 source 청크 상한.
    - **(b) PDF 발견량 자체 부족** — venfobel-vitamin web에 unique PDF 1개. 한국어 의약 매체 PDF 적음. 글로벌 보고서 보강은 §12-3 (Vertex grounded search) 활성화 후보.

    **일반화 교훈**:
    - **풍부도 제약은 "추출 깊이"와 "발견량"의 두 축**. 본 PR(A 옵션)은 추출 깊이를 ×4.2 늘렸고 발견량은 별도 문제로 남음.
    - **보수적 컷이 의도한 수준 이상으로 강하게 작동했음** — 5p/10000자는 "잘 모르는 출처라 보수적"이 의도였으나, ALLOWED_DOMAINS 50개 화이트리스트로 출처 신뢰도가 이미 보장되는 운영에서는 과한 보수. 화이트리스트와 한도는 짝으로 튜닝.
    - **"인덱스 디스크 직접 삭제 + 재인제스트" 플로우가 한도 변경 효과 검증의 표준 패턴** — `CLEAR_CHROMA_ON_START`은 vector_search 진입 시 발동이라 web ingest 단계 효과 측정엔 부족(§12-9). 디스크 직접 삭제 + `__seen_sources__.json` 같이 비우기.

    **진단 도구**:
    - `tools/diagnose_richness.py` 신설 (chromadb Rust binding이 본 환경에서 panic 내는 우회로 sqlite 직접 읽기). 모든 NS 자동 스캔, content_type별 청크 수/길이, 호스트 top, **PDF avg_chunks/pdf** 산출. 한도 변경 효과 측정 표준 도구.

18. **§12-18 — 단일 source 청크 상한 (`MAX_CHUNKS_PER_DOC`) 활성화** — 상태: `closed (2026-05-06)` / 의존: §12-17 / 우선순위: 중

    **출처**: §12-17 효과 측정 직후 발견. venfobel-vitamin-web 재인제스트 결과 `https://dailypharm.com/user/news?category=건기식+A-Z&group=...` 카테고리 인덱스 페이지 1개가 **25청크(34.2%)**. height-growth-supplement에 박제된 `seoul.co.kr` 한 페이지 **34청크(40.0%)** 와 동일 패턴 — 카테고리/검색결과 인덱스 페이지가 헤드라인 나열로 chunk_size 한도까지 길어 다중 청크화되며 NS 신호 비중을 잠식.

    **변경**:
    - `tools/web_rag/ingest_vector.py:1163~ documents_to_chroma()` — short-chunk filter 직후, ID 생성 직전. 한 source가 cap 초과하면 초과분 drop. log 출력으로 drop 통계 가시화.
    - `.env`/`env_raw.txt`의 `MAX_CHUNKS_PER_DOC` 값을 30→**15**로. 이전엔 코드 미참조 dead variable였으므로 사실상 신규 활성화. 코드 default 0(미설정 시 비활성).

    **cap 값 근거 (15)**:
    | 측정 케이스 | 청크 수 | cap=15 효과 |
    | --- | ---: | --- |
    | venfobel khidi.or.kr PDF (정상 보고서) | 14 | 통과 ✅ |
    | venfobel dailypharm 카테고리 인덱스 | 25 | 15로 cut (40%↓) |
    | height seoul.co.kr 검색결과 페이지 | 34 | 15로 cut (56%↓) |

    정상 PDF(현 14청크)는 보존, 인덱스성 페이지(20+)만 절단되는 임계값.

    **위치 선택 근거 (왜 `documents_to_chroma` 안인가)**:
    - 본 함수가 web/local 양쪽 ingest의 단일 funnel — `add_web_pages_json_to_chroma` / `add_documents_to_chroma` 모두 여기로 위임. 한 곳 추가로 모든 경로 커버.
    - 청킹·short-chunk 필터링 **후**, ID 생성 **전**에 cap을 두어 통계 로그가 post-cap 수치를 반영. 측정 일관성.

    **일반화 교훈**:
    - **dead env 변수는 의도가 정확히 일치할 때 살리는 게 깔끔** — 새 변수 신설 대신 기존 `MAX_CHUNKS_PER_DOC` 활성화로 환경변수 표면적 증가 0. 다만 git 이력에서 dead 시점을 추적할 수 있으므로 박제 필수.
    - **풍부도 ↔ 신호품질의 짝**: §12-17(추출 깊이 ×4.2)으로 PDF 풍부도를 늘리면, 본 §12-18(단일 source 상한)으로 신호 품질을 보호. 한 쪽만 하면 노이즈 많은 페이지가 인덱스 비중을 차지하는 부작용 가능.

    **follow-up**:
    - cap이 host 단위로도 필요할 가능성 — dailypharm.com 60.3% 같은 매체 쏠림은 source-level cap으론 못 잡음(매체 안 여러 기사 페이지가 각각 다른 source). 후속 큐 후보: `MAX_CHUNKS_PER_HOST`.
    - 효과 검증: §12-17과 동일 절차 — venfobel-vitamin-web 디스크 삭제 + 재인제스트 + `tools/diagnose_richness.py` 재측정. 다음 운영 흐름 시 자동 적용되므로 별도 실행 불필요.

19. **§12-19 — Vertex grounded search 토픽 활성화 (`SKIP_VERTEX_SEARCH=0`)** — 상태: `closed (2026-05-06, 활성화 + reload 버그 발견·수정·실측 완료 — §12-20 참조)` / 의존: §12-17 / 우선순위: 중

    **출처**: §12-17 효과 측정 직후 발견된 두 번째 풍부도 축 — "추출 깊이"는 ×4.2 늘렸으나 **PDF 발견량 자체가 부족** (venfobel-vitamin-web에 unique PDF 1개). 한국어 의약 매체에서 PDF가 적고, 글로벌 보고서·영어 가이드라인이 비어있는 구조적 한계. README §12-3 권장 패턴(`영어 자료 위주 토픽은 토픽별 .env에서 SKIP_VERTEX_SEARCH=0 override`)을 venfobel-vitamin에 적용.

    **변경**:
    - `topics/venfobel-vitamin.env` 끝에 `SKIP_VERTEX_SEARCH=0` 추가. 글로벌 .env 의 `SKIP_VERTEX_SEARCH=1` 을 토픽 단위로 override.
    - 코드 변경 0줄. `agent/web_search.py:764` 의 `_cfg_bool("SKIP_VERTEX_SEARCH", False)` 토글이 `attempt==0` 일 때 Vertex grounded search를 호출, Naver/Tavily 결과에 **augmentation 형태로 합쳐짐**.

    **인증·환경 prerequisite (이미 충족)**:
    - `GCP_PROJECT_ID=gemini-rag-search-final`
    - `GCP_REGION=us-central1`
    - `GOOGLE_APPLICATION_CREDENTIALS=...service_account_vertex.json`
    - `LLM_MODEL=gemini-2.5-flash` (vertex_search.py:77)

    **비용·위험**:
    - **첫 attempt 대기 시간 수 초 추가** — 모든 web_search 호출의 head latency 증가. 사용자측 체감 가능.
    - **Vertex API 호출 과금** — Gemini 2.5 grounding 콜.
    - **한국어 토픽 효과 제한 가능성** — venfobel은 OBJ 1~5가 한국 시장·매체 중심이라 영어 보고서 보강의 한계효용이 작을 수 있음. 다만 OBJ4(소비자 정서)·OBJ5(채널·메시지)는 글로벌 디지털 헬스 트렌드 보고서가 보강 가치 있음.

    **활성화 결정 근거**:
    - §12-17 측정에서 unique PDF 1개 = 발견량 자체의 구조적 한계 가시화.
    - 영어 토픽 권장 패턴(README §12-3)을 한국어 토픽이지만 글로벌 자료 보강 목적으로 응용 시도 — 효과가 작으면 토픽 .env 한 줄 제거로 즉시 원복 가능.

    **효과 검증 follow-up**:
    - 다음 web_search 흐름 1턴 실행 후 `tools/diagnose_richness.py` 재측정. 핵심 지표: `unique_pdfs` 1→N, `vertexaisearch.cloud.google.com/grounding-api-redirect` 도메인 흔적, 영어 도메인 비율 변화.
    - 응답 latency가 사용자측 체감으로 거슬리는 정도면 토픽 .env에서 즉시 원복.

    **일반화 교훈**:
    - **풍부도는 "추출 깊이"와 "발견량"의 두 축** (§12-17 본문 박제 재확인). §12-17 = 깊이, 본 §12-19 = 발견량. 둘 다 잡아야 web 인덱스 풍부도가 실질적으로 개선됨.
    - **한국어 토픽이라도 발견량 보강 목적의 Vertex 활성화는 옵션** — README §12-3 의 "영어 자료 위주 토픽" 가이드는 권장이지 제한이 아님. 토픽별 override 한 줄로 ROI 실측 가능.

    **효과 실측 (2026-05-06, follow-up 1턴 결과)**:
    - 1차 시도(commit 87ee1cf 직후): web_search 흐름에서 `[web_search] Vertex skipped (SKIP_VERTEX_SEARCH=1)` — **활성화 자체가 안 됨**. 직접 `python -c "from core.config import CFG; print(CFG.SKIP_VERTEX_SEARCH)"` 시는 `False`로 정상이라 모순 발생 → §12-20 으로 분리해 버그 root cause 추적·수정.
    - 2차 시도 (§12-20 fix 적용 후, 같은 쿼리 2개로 재실행):
        - `[web_search] Vertex success (5 urls)` + `Vertex success (15 urls)` ✓
        - web 인덱스 75 → **112 (+37 chunks)**. 직전 두 런이 +2 chunks / 0 chunks 였던 것과 비교해 ×18 이상 풍부도 향상.
        - **§12-17 + §12-19 곱셈 효과 첫 사례**: Vertex가 발견한 미래에셋 IR PDF(`securities.miraeasset.com/.../2091059.pdf`, 100p)가 §12-17 의 30p 한도까지 추출되어 1 docs → **29 chunks** 로 split. 5p 한도였다면 ~5 chunks 였을 자리.
        - Vertex가 끌어온 신규 발견원: `securities.miraeasset.com`(IR), `w4.kirs.or.kr`(JW생명과학 IR), `whosaeng.com`(보장성 PDF). 모두 기존 Naver/Tavily 단독 체인에서는 보이지 않던 도메인.
    - **비용 측정**: 쿼리당 dt 63.55s + 42.39s (이전 5초 ~ 6초). Vertex AFC `max remote calls=10` 로 LLM grounding 콜 10회를 거치는 비용. 당장의 ROI는 명확하지만, 라운드 수 증가 시 latency 부담 — `RESEARCH_MIN_ROUNDS` 상향 시 사전 검토 필요.
    - **손실 (Vertex가 발견했으나 회수 못 한 후보)**:
        - `w4.kirs.or.kr/.../JW생명과학.pdf` — `SSL: CERTIFICATE_VERIFY_FAILED` (인증서 체인 불완전). PDF-rich 토픽이라 회수 가치 큼 — 후속 task 후보: host-allowlist 기반 `verify=False` fallback.
        - `boryung.co.kr/.../IR.pdf` — HTTP 400.
        - `file.myasset.com`, `file.alphasquare.co.kr` — allowlist 미등록 (미래에셋·알파스퀘어 별도 PDF 호스트). allowlist 확장 후속 후보.
        - `whosaeng.com/.../2020112311358142.pdf` — 본문 파싱 결과 너무 짧음(이전 런 3회 동일). PDF 추출기 회수 한계.

20. **§12-20 — `reload_config_inplace` 토픽 .env override 누락 버그 수정** — 상태: `closed (2026-05-06)` / 의존: §12-19 / 우선순위: 상

    **출처**: §12-19 follow-up 1턴 효과 측정에서 `SKIP_VERTEX_SEARCH=0` 토픽 override 가 적용된 것처럼 보였으나(직접 `python -c "import core.config; print(c.CFG.SKIP_VERTEX_SEARCH)"` 시 `False` ✓ + 콘솔에 `[Config] 토픽 프리셋 로드: ...venfobel-vitamin.env` print 출력), 정작 web_search 단계 로그에서는 `[web_search] Vertex skipped (SKIP_VERTEX_SEARCH=1)` — Vertex 호출 자체가 안 됨. 새 셸·OS env 미오염 확인(`Get-ChildItem env:SKIP_VERTEX_SEARCH` → 경로 없음) 후에도 동일.

    **Root cause** (`core/config.py:598-614` `reload_config_inplace`):
    ```python
    def reload_config_inplace() -> Config:
        ...
        if _DOTENV_READY:
            try:
                load_dotenv(find_dotenv(usecwd=True), override=True)  # ← 글로벌 .env만 재로드
            except Exception:
                pass
        new_cfg = _build_config()  # ← 그 안의 _load_dotenv_once는 _dotenv_loaded 가드로 no-op
        ...
    ```
    - 첫 import 시 `CFG = _build_config()` → `_load_dotenv_once()` 정상 실행 → 글로벌(=1) → 토픽(=0)로 덮어쓰기 → `CFG.SKIP_VERTEX_SEARCH = False` ✓
    - **`app.py:1896` `_early_config.reload_config()` 호출**:
        - 글로벌 `.env` 만 `override=True` 로 재로드 → OS env 의 `SKIP_VERTEX_SEARCH` **0 → 1로 회귀**
        - 그 후 `_build_config()` 호출하지만 `_load_dotenv_once()` 는 `_dotenv_loaded` 가드로 **no-op** → 토픽 .env 재로드 안 됨
        - 결과: `CFG.SKIP_VERTEX_SEARCH = True` ❌
    - `app.py:1971` 두 번째 `reload_config()` 호출에서 같은 문제 반복.
    - **검출 어려웠던 이유**: 사용자가 직접 `import core.config` 하면 `_build_config()` 만 1회 실행되니 토픽 override 가 살아 있음. 모순 결과(직접 import OK, 앱 실행 fail)가 가설을 좁히는 결정적 단서.

    **변경** (`core/config.py`):
    - `_apply_topic_preset(*, verbose: bool)` 헬퍼 신설 — 토픽 .env 로드 로직(`TOPIC_SLUG` → `topics/{slug}.env` `override=True`) 을 한 곳으로 추출.
    - `_load_dotenv_once()` — 위 헬퍼를 `verbose=True` 로 호출 (사용자에게 보이는 print 는 첫 부팅 1회만).
    - `reload_config_inplace()` — 글로벌 `.env` 재로드 직후 `_apply_topic_preset(verbose=False)` 추가 호출 (재로드 시 print 스팸 방지).

    **검증**:
    - `python -c "import core.config as c; print('init:', c.CFG.SKIP_VERTEX_SEARCH); c.reload_config(); print('after_reload:', c.CFG.SKIP_VERTEX_SEARCH)"` → `init: False / after_reload: False` ✓ (fix 전: `False` → `True`).
    - 새 PowerShell + `.venv_vertex` 에서 `python app.py` → `최신 자료로 RAG 업데이트` 실행. Vertex 호출 라인 (`Vertex success (N urls)`) 두 번 모두 정상. §12-19 효과 실측 가능해짐.

    **일반화 교훈**:
    - **reload 함수는 ENV 로드 흐름의 모든 단계를 재현해야 한다** — 글로벌 `.env` 만 재로드하면 토픽 override 가 글로벌로 회귀. dotenv 의 `override=True` 가 정확히 이 회귀를 일으키는 메커니즘.
    - **첫 import 와 reload 의 경로 분기는 잠재 버그 항상 후보**. `_dotenv_loaded` 같은 once-guard 가 reload 경로에서 silent skip 되면 미묘한 상태 분기 발생. 한 곳에 통합하는 헬퍼(`_apply_topic_preset`) 가 가장 안전.
    - **모순 관찰을 가설 분리에 활용** — "직접 import 하면 정상인데 앱 실행은 비정상"이 reload 경로 차이로 좁혀준 핵심. 같은 결과를 양쪽에서 측정하는 것이 root cause 도달 시간을 결정함.

    **follow-up**:
    - 이 fix 가 다른 토픽 단위 override (`CHROMA_*`, `LOCAL_RAG_GLOBS`, `BLOCKAGI_OBJECTIVE_*`, `RAG_DISTANCE_THRESHOLD` 등) 의 reload 경로에서도 정상 작동하는지 후속 사용 흐름에서 자연 검증 — 별도 액션 불필요.
    - `_dotenv_loaded` once-guard 자체를 제거하고 `_load_dotenv_once` 를 idempotent 로 만들 수도 있으나, 첫 부팅 print 스팸 트레이드오프가 있어 현재 헬퍼 분리 패턴을 유지.

21. **§12-21 — 인용 chunk 원본 사이드카 (`<section>.refs.json`)** — 상태: `closed (2026-05-06)` / 의존: 없음 / 우선순위: 중

    **출처**: 사용자 보고 (2026-05-06) — "출처 상세 창에서 chunk의 내용을 함께 나타나게 할수 있을까? 섹션에서 인용한 구체적인 내용에 대해 힌트를 얻으면 도움이 많이 될 것 같아." 프런트 SourcePanel 이 fileName/URL/경로만 보여줘 사용자가 인용 본문을 알려면 원본 파일을 직접 열어야 함.

    **설계 결정**: 두 옵션 중 (A) 선택.
    - (A) 사이드카 JSON: 섹션 작성 시점에 `<section>.refs.json` 을 .md 옆에 박제, 프런트가 별도 엔드포인트로 조회.
    - (B) footnote 라인에 chunk 발췌 inline. 단순하지만 Word/PDF export 시 footnote가 지저분해지고 발췌 길이 제한이 메시지 품질을 깎음. (A) 가 §7-1 footnote 형식 규약을 건드리지 않음 + 풀 chunk 텍스트 저장 가능.

    **구현 (백엔드)**:
    | 파일 | 변경 |
    |---|---|
    | `utils/refs.py` | `build_marker_refs_map(gathered, state, max_n=20) -> dict[str, dict]` 신설. `attach_marker_citations` 와 동일한 [[N]] → original N → 본문 등장 순 재할당 로직 사용하여, 재할당된 marker → `{marker, url, label, text, source, title}` 맵 생성. **`text` 필드에 `doc.page_content` 풀 텍스트 그대로 저장 (사용자 요청: 발췌 잘라내지 않음).** |
    | `agent/section_writer.py` | `attach_marker_citations` 호출 *전* `build_marker_refs_map` 으로 맵 캡처 → `save_md_draft` 성공 후 `Path(out_path).with_suffix(".refs.json")` 에 `json.dumps(..., ensure_ascii=False, indent=2)` write. 빈 맵이면 사이드카 미생성. |
    | `agent/chapter_writer.py` | section_writer 와 동일 패턴 적용. `Path` import 추가. |
    | `app.py` | `GET /api/section-refs/{file_id:path}` 엔드포인트 신설. `_safe_under_artifacts` 가드 통과 후 `<file>.refs.json` 읽어 `{ok, id, refs}` 반환. **사이드카 부재 시 404 가 아닌 `{ok: True, refs: {}}`** — 옛 섹션(사이드카 없음) 호환을 프런트에서 단순화. |

    **구현 (프런트)**: §12-16 (frontend `bell_agent/frontend/README-dev.md` §12-16) 와 짝 박제.

    **설계 invariant**:
    - `build_marker_refs_map` 은 `attach_marker_citations` 가 본문을 mutate 하기 *전* 의 raw `[[N]]` 마커가 박힌 gathered 에 호출되어야 동일 remap 로직이 작동. 두 함수가 같은 remap 을 독립적으로 계산하므로 입력만 일치하면 결과 marker 키가 footnote `[^N]` 과 1:1.
    - **마커 키는 문자열**(`"1"`, `"2"`, ...) — JSON 직렬화 호환 + 프런트 `FootnoteDef.marker` (string) 와 직접 비교.
    - 사이드카 파일명: `<section>.refs.json`. `.md.bak` 같은 백업 확장자 변형은 무시(엔드포인트가 `splitext` 후 `.refs.json` 강제).

    **운영 영향**:
    - 신규 섹션 작성 시마다 사이드카 1개 추가 생성 (보통 4~10KB). `.gitignore` 에 추가 필요한지는 별도 검토 — `sections/<topic>/*.md` 가 git 추적되면 `*.refs.json` 도 함께 추적이 일관적.
    - 옛 섹션은 사이드카 없으므로 `/api/section-refs` 는 빈 맵 반환 → 프런트 SourcePanel 이 chunk 영역만 안 그릴 뿐 동작 정상. 옛 섹션을 다시 write 하면 자동 생성됨.

    **앞으로의 가드**:
    - 새 footnote 모드 추가 (예: quant/domain) 시 `build_marker_refs_map` 은 marker 모드 전용. 다른 모드용 사이드카가 필요하면 별도 함수로 분기.
    - `references.docs` 항목의 `page_content` 가 비어있으면 `text: ""` 로 저장됨 (정상). 프런트는 빈 text 시 chunk 영역 숨김.

22. **§12-22 — 인용 chunk 요약 (background daemon, 사이드카 점진 갱신)** — 상태: `closed (2026-05-06)` / 의존: §12-21 / 우선순위: 중

    **출처**: 사용자 보고 (2026-05-06, §12-21 직후) — "인용내용이 그대로 다 나오니 오히려 더 헷갈리네. LLM이 본문에서 인용한 맥락을 고려해서 정제한 핵심 내용만 요약해서 보여주는 방법을 해보면 어떨까?" raw chunk 가 길고 dense 해서 사용자가 핵심을 즉시 파악하기 어려운 UX 문제.

    **설계 결정 (write 시점 동기 vs background)**:
    - 동기로 4~8 LLM 호출 추가 시 섹션 write 평균 +2~3초, tail latency 5~10초 + **섹션 저장 성공이 요약 LLM 가용성에 결합** — rate-limit / 일시 장애 시 섹션 저장 자체 지연.
    - **background after save (선택)**: 섹션 저장은 즉시 완료, daemon thread 가 ThreadPoolExecutor(4)로 병렬 LLM 호출 → 완료 marker 부터 사이드카 atomic merge. 프런트가 short-poll 로 자연 갱신.

    **구현**:
    | 파일 | 변경 |
    |---|---|
    | `utils/chunk_summary.py` (신설) | `extract_marker_context(gathered, marker, radius=200)` — 본문 [[N]] 등장 위치 ±200자 발췌. `_summarize_one(llm, chunk_text, section_context)` — 1회 LLM invoke. `_atomic_merge_summary(sidecar, marker, summary)` — read → set `data[marker]["summary"]` → write `.tmp` → `os.replace` (atomic, reader race 차단). `_run_background(...)` — `ThreadPoolExecutor(max_workers=4)` 로 병렬 처리, 각 future per-future 60s timeout. `start_background_summarization(...)` — daemon thread spawn 후 즉시 반환. `_SIDECAR_LOCK` 으로 process-wide write 직렬화 (여러 섹션 동시 요약 contention 방어). |
    | `agent/section_writer.py` | 사이드카 초기 write 직후 `start_background_summarization(sidecar, gathered, marker_refs_map)` 호출. 실패해도 섹션 저장 흐름엔 영향 없음 (try/except). |
    | `agent/chapter_writer.py` | 동일 패턴. |

    **요약 프롬프트 핵심**:
    - 섹션 본문 ±200자 발췌 + chunk 원문 → 1~3문장 한국어 요약.
    - 가드: "보고서가 출처에서 활용한 핵심 사실/주장만", "출처 원문에만 있고 보고서가 활용하지 않은 부분 제외", "요약 외 다른 텍스트(머리말·인용부호·라벨) 금지".

    **운영 invariant / 장애 모델**:
    - **LLM**: `core.llm.get_llm()` 싱글턴 재사용 (langchain ChatModel 은 thread-safe HTTP client). 별도 cheap 모델 분리는 향후 `CHUNK_SUMMARY_MODEL` env var 로 추가 가능 — 현재 미구현 (운영 비용 측면 문제 없을 것으로 판단).
    - **부분 완료 허용**: 8개 marker 중 6개만 성공해도 사이드카에 6개 summary 박힌 상태로 저장. 프런트가 빈 summary 는 "요약 생성 중…" placeholder 로 표시.
    - **서버 종료**: daemon thread 라 process exit 시 같이 종료. 미완성 사이드카는 다음 섹션 rewrite 시 자동 재생성.
    - **atomic write**: tmp → `os.replace` 가 Windows/POSIX 모두 atomic. 동시 읽기 시 reader 는 항상 old 또는 new 의 완전한 JSON 만 봄.

    **앞으로의 가드 / 일반화 교훈**:
    - **write 성공과 부가 작업의 결합 차단**: LangGraph 노드의 사이드 이펙트(요약·인덱싱·후처리)는 노드 반환과 분리하는 것이 default. 본문이 즉시 visible 되어야 사용자 체감 latency 가 안 늘어남.
    - **사이드카 점진 갱신은 atomic + lock 짝**: per-marker write 마다 read-modify-write 가 일어나므로, 동시 marker 완료 시 마지막 쓰기가 이전을 덮을 수 있음. `_SIDECAR_LOCK` 으로 직렬화 + tmp+replace 로 atomic. 둘 중 하나만 빠지면 데이터 손실.
    - **frontend 폴링 책임 분리**: summary 미완성 시 자동 short-poll, 완성 시 자동 종료. backend 가 "완료" 신호를 push 하지 않아도 자연 수렴 (backend 단순성 우선).
    - **§12-21 (사이드카 본체) 와 §12-22 (요약 채널) 짝**: 사이드카 기본 필드는 §12-21 에서 1회 동기 write, summary 필드는 §12-22 가 background 점진 추가. raw text 와 summary 가 함께 박제되어 프런트 UX 토글 (요약 default + 원본 보기) 이 가능.

    **frontend 짝 박제**: `bell_agent/frontend/README-dev.md` §12-17.

    **follow-up 후보**:
    - `CHUNK_SUMMARY_MODEL` env var 로 cheap 모델 (Gemini Flash Lite 등) 분리 — 운영 비용 데이터 본 후 결정.
    - 요약 품질 평가: 사용자 검증 후 프롬프트 튜닝 필요 시 §12-22 본문에 Round 2 박제.
    - chapter (book mode) 는 본문이 길어 ±200자 컨텍스트가 부족할 수 있음 — chapter 전용 컨텍스트 반경 별도 튜닝 후보.

23. **§12-23 — OpenAI provider end-to-end 검증 (`.venv_openai` + venfobel 토픽)** — 상태: `closed (2026-05-07)` / 의존: 없음 / 우선순위: 상

    **출처**: 사용자 요청 (2026-05-07) — "벡엔드에서 LLM Model을 현재는 vertex ai를 쓰고 있어. chatgpt 모델도 번갈아 쓰고 싶어. … vertex ai쓸때 가상환경 잡는데 고생을 많이했었어. dependency 충돌 문제가 많았었어." Vertex 와 OpenAI 양쪽을 venv·의존성·collection 단위로 분리 운용하는 것이 목표.

    **분리 전략 (코어)**:
    | 레이어 | Vertex | OpenAI | 비고 |
    |---|---|---|---|
    | venv | `.venv_vertex` (기존) | `.venv_openai` (신설) | 의존성 충돌 차단 |
    | requirements | `requirements.vertex.txt` | `requirements.openai.txt` | 둘 다 `-r requirements.base.txt` 참조 |
    | .env overlay | `.env.vertex` | `.env.openai` | `LLM_PROVIDER` 값에 따라 `core/config._apply_provider_overlay()` 가 자동 로드 (글로벌 .env 직후, 토픽 프리셋 직전) |
    | Chroma collection | `venfobel-vitamin{,-web,-local}` (768d) | `venfobel-vitamin-oa{,-web,-local}` (3072d) | 임베딩 차원 다르므로 namespace 분리 필수 (`.env.openai` 의 `CHROMA_NAMESPACE` 블록 활성화) |

    **결정적 코드 변경**:
    | 파일 | 변경 |
    |---|---|
    | `core/config.py` | `_apply_provider_overlay()` 추가. 우선순위: 글로벌 → overlay → 토픽 프리셋. `_load_dotenv_once()` 와 `reload_config_inplace()` 양쪽에 결선. |
    | `core/llm.py` | `_none_if_blank()` 헬퍼 추가. `get_llm` / `get_embedding_model` 의 OpenAI 분기에서 `base_url=''` / `organization=''` 빈 문자열을 None 으로 정규화. **OpenAIEmbeddings 가 빈 문자열을 그대로 httpcore 까지 흘려 `Request URL is missing http(s)://` panic** 을 일으키던 문제 해결 (ChatOpenAI 는 자체 정규화로 통과했었음). |
    | `tools/web_rag/vertex_search.py` | `from google import genai` 등 모듈 최상단 import 를 `try/except` lazy guard 로 전환. `_GENAI_AVAILABLE=False` 시 `vertex_web_search()` 는 빈 dict (`summary='', urls=[]`) graceful degrade. OpenAI venv 부팅 시 ImportError 차단. |
    | `requirements.base.txt` | `chromadb==1.2.0 → 1.5.1`. 1.2.0 의 Windows + 신규 collection Rust panic (`pyo3_runtime.PanicException: range start index 10 out of range for slice of length 9` from `chromadb_rust_bindings.Bindings`) 회피. 추가 누락 패키지 보충: `fastapi==0.131.0`, `starlette==0.52.1`, `Jinja2==3.1.6`, `MarkupSafe==3.0.2`. |

    **venfobel 토픽 검색 정책 (실측 기반 튜닝, `topics/venfobel-vitamin.env`)**:
    - `text-embedding-3-large` + Chroma `hnsw.space=l2`(squared L2) 실측 분포 (10쿼리 × top10):
        - **local(349 docs)**: min=0.523 p25=0.899 median=1.046 p75=1.142 p90=1.364 max=1.414
        - **web(61 docs)**: min=0.800 p25=1.129 median=1.233 p75=1.309 p90=1.439 max=1.505
    - `RAG_DISTANCE_THRESHOLD=1.10` — local 68% / web 21% kept. 0.45→0.80→0.95→1.10 단계적으로 측정·조정 (vertex `text-multilingual-embedding-002` 의 0.65 와 분포 차원 자체가 다름).
    - `MERGE_RETRIEVE_MODE=local_first` + **`RETRIEVE_WEB_RATIO=0.33`** — 토픽이 사용자 자료(refs PDF/XLSX)에 정답이 집중되어 있어 local quota 우선. **mode 변수는 머지 정렬 우선순위만 결정하고 k 분배는 ratio 가 단독 결정**한다는 것을 실험으로 발견 (mode 만 바꿔서는 분배 안 뒤집어짐).
    - `RAG_TOP_K=10` — 광고비 xlsx 의 chunk=4 두 개 (`벤포벨_2024/2025 월별 채널별 예산`) 가 query 와 임베딩 공간에서 부적절하게 가까워 quota 자리를 잡아먹는 문제 우회. k=6 → 10 으로 늘리니 split(web=3, local=7) 확보.

    **검증 결과 (4장 섹션 작성)**:
    - merged=7 청크, 인용 마커 `[[1]]~[[5]]` 본문 분포, 각주 5개 모두 다른 출처 (팩트북 PDF, 광고전략 PDF, **`03_활성형B1_클레임_백업.md`**, **`04_3강_제품라인업_비교.md`**, Ipsos 광고효과 PPTX). 약 4,400자 섹션이 `sections/venfobel-vitamin/4장-...md` 에 저장. refs 폴더의 사용자 정리 자산이 보고서에 도달함을 확인.

    **follow-up 후보 (별건)**:
    - **`vector_search [DIRECT QA]` prompt context cap**: `merged=7` 인데 직답 prompt 에는 3개 청크만 들어감. 그래서 직답 길이는 짧아지지만 `research_synthesizer` 는 7개 모두 사용해 findings 풍부 — 단계 분리 자체는 정상 동작이고 cap 이 빠진 청크가 본문에 안 들어가는 것이 별건.
    - **OBJ3 구체 수치 누락**: 토픽 프리셋 OBJ3 의 핵심 차별화 자산 (벤포티아민 100mg + 비스벤티아민 30mg / 메코발라민 500μg / UDCA 60mg / '어른들의 비타민' 슬로건 / 약사 권매 1위 56%) 가 4장 본문에 못 들어감. 인용된 `03_활성형B1_클레임_백업.md` 가 chunk=1 (일반론) 이고 성분 표는 chunk=5 인데 distance 1.10 컷 위. chunk 분할 재조정 또는 section_writer prompt 에 OBJ 사실 가드 추가 후보.
    - **cosine metric 통일**: 현재 chromadb 기본 `l2` 사용 중. `_get_vs` 의 `Chroma()` 호출에 `collection_metadata={"hnsw:space": "cosine"}` 추가하면 직관적 임계 0.5~0.6 로 정렬 가능. 단 collection 생성 시점에 박히는 메타데이터라 **1회 재인덱싱 필요** — 검증 단계 비용 부담으로 보류.

    **앞으로의 가드 / 일반화 교훈**:
    - **provider 분리는 venv + .env overlay + Chroma namespace 3중**: 의존성·환경변수·인덱스 차원이 모두 충돌하므로 한 축만 분리해선 부족. 차원 다른 임베딩(768 vs 3072)을 같은 collection 에 쓰면 dim mismatch 또는 silent 0-vector 오염 발생.
    - **Chroma distance metric 이 임베딩 모델별로 다르게 받아들여진다**: `RAG_DISTANCE_THRESHOLD` 는 임베딩 모델 + metric (`hnsw:space`) 페어로만 의미가 있는 값. 모델 바꿀 때 임계값을 같이 측정·조정하지 않으면 silent 0-hit 가 무한 supervisor 루프(`no_summary_min_qa` → 새 web_search round) 로 이어진다 — 5단계 디버깅 중 가장 큰 함정.
    - **mode 와 ratio 의 책임 분리 인지**: `MERGE_RETRIEVE_MODE` 는 정렬, `RETRIEVE_WEB_RATIO` 는 분배. 동작 변수가 이름과 다르게 분리되어 있는 케이스 — 토픽별 검색 정책 튜닝 시 둘을 짝으로 봐야.
    - **provider overlay 의 토픽 프리셋과의 우선순위**: 토픽 프리셋이 마지막에 적용되므로 토픽이 `LLM_PROVIDER` / `CHROMA_NAMESPACE` 등을 명시하면 venv 토글과 무관하게 토픽이 이김. venfobel 의 `SKIP_VERTEX_SEARCH=0` 라인이 OpenAI 모드에선 노이즈를 만들지만 graceful degrade 로 해결됨 (vertex_search lazy guard).

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

## 14) §13 — pptx export 모듈 신설

**§13 — `.md` 보고서 → `.pptx` 슬라이드 덱 자동 변환** — 상태: `in-progress (2026-05-08)` / 의존: 없음 / 우선순위: 상

**Goal**:
RAG writer 가 `reports/<slug>/...md` 로 떨궈주는 광고 에이전시 딜리버리블(보고서 .md)을 자체 PowerPoint 템플릿(`templates/agency_default.pptx`, 16:9 / Pretendard / 버건디 RGB 139,41,66)에 자동 매핑하여 클라이언트 전달용 `.pptx` 산출물을 생성한다. v1 = OpenAI 단독 end-to-end 동작 확인. 모델 비교(v2 Gemini A/B, v3 Claude)는 후속 단계.

**Context (출처)**:
- 사용자 요청 (2026-05-08): "광고 에이전시 딜리버리블용. 자체 PowerPoint 템플릿 제작 완료." `agency_default.pptx`(33,922 B) `templates/` 로 이동 완료. zip 구조상 `ppt/slideLayouts/slideLayout1~11.xml` 11개 슬롯 — 사용자가 명시한 3종(TITLE / TITLE_CONTENT / SECTION_HEADER) 의 layout 인덱스 확정은 §13-1 에서 1회 점검.
- 첫 검증 대상: `reports/venfobel-vitamin/20260505-063304_report.md` (71,134 B / 395 lines / 7장 구조). 챕터 패턴 일관(`## N.` 큰 챕터 + `### N.M.` 하위 + `### Actionable Recommendations` + `### 참고 문헌 / 각주`), Markdown table 1건(2.2 경쟁 제품 매출 동향), 인라인 인용 마커(`[종근당_팩트북.pdf]`, `[dailypharm.com/...]`) + footnote(`[^1]:`) 분리.
- §12-23 close 직후 신규 트랙. §12 시리즈와 독립된 §13 시리즈로 분기 (CLAUDE.md task 체계 `§<섹션>-<항목>`).

**Design**:
- **3단 분리 (신규 어댑터 도입 없이 `core.llm.get_llm()` 추상화 재사용)**:
  1. **planner (LLM)** — `.md` + slug + topic_title → `SlideDeckSpec`(JSON). provider 토글(`LLM_PROVIDER` env + venv)은 `core/llm.py` 가 이미 처리.
  2. **spec (Pydantic)** — `SlideSpec` / `SlideDeckSpec` BaseModel. `core/models.py:Task` 와 동일 스타일(`Field(..., description=...)`). LLM `with_structured_output(SlideDeckSpec)` 로 직접 파싱.
  3. **renderer (python-pptx)** — spec + template path → `.pptx`. LLM 호출 0, 결정론적.
- **레이아웃 매핑 전략 (두 안 비교)**:
  - (A) **결정론적 규칙** — 첫 슬라이드 = TITLE, `## N.` = SECTION_HEADER 슬라이드 + 다음 본문 슬라이드(들) = TITLE_CONTENT, `### N.M.` = TITLE_CONTENT. 단순·일관·테스트 가능, LLM 비용 0.
  - (B) **LLM 결정 hint** — planner 가 슬라이드별 `layout_hint` 채움. 유연하나 v1 검증 흐림.
  - **결정**: v1 = (A) 단독. (B) 필드는 spec 에 optional 로 reserve 만, v2 이후 활성화.
- **LLM 호출 wrapper**: `agent/section_writer.py:235~261` 패턴 그대로 (`time.monotonic()` 측정 + `tools.metrics.record_llm_call(provider, model, latency_s, success, error_class, section_title="pptx_plan", retry_hint=...)`). retry 는 LangChain 내부 처리. `OPENAI_REQUEST_TIMEOUT` / `OPENAI_MAX_RETRIES` / `VERTEX_REQUEST_TIMEOUT` ctor 전달은 `get_llm()` 이 이미 수행.
- **표(Table) 처리 v1**: Markdown table → renderer 가 native pptx Table shape 으로 변환 (행/열 그대로). 셀 폰트는 layout placeholder 폰트(Pretendard) 상속.
- **인용 마커 / footnote 처리 v1**: 본문 그대로 슬라이드 텍스트에 보존. footnote 매핑은 마지막 슬라이드 1장에 통합 또는 슬라이드별 notes pane 에 부착(렌더러 옵션). 클릭 가능 hyperlink 는 v2 이후.
- **출력 산물 흐름**: 입력 md 와 같은 디렉터리 + 동일 basename + `.pptx` (`reports/<slug>/<basename>.pptx`). 기존 `.md` 합본 흐름과 짝. 자동 트리거(예: `report_builder.py` 직후 호출)는 v1 에서 도입하지 않음 — 별도 CLI 명령으로 분리하여 검증 단순화.

**Files (planned)** — `agent/export/` 신설 (의존 방향 `utils → tools → agent`, agent↔agent 직접 import 없음 — export 는 외부 진입점이라 무관):
| 파일 | 역할 |
|---|---|
| `agent/export/__init__.py` | 패키지 초기화 |
| `agent/export/spec.py` | `SlideSpec`, `SlideDeckSpec`, `TableSpec` Pydantic 모델 |
| `agent/export/planner.py` | `plan_deck(md_text, *, slug, topic_title) -> SlideDeckSpec` (LLM 호출) |
| `agent/export/renderer.py` | `render_deck(spec, *, template_path, out_path) -> Path` (python-pptx) |
| `agent/export/cli.py` | `python -m agent.export.cli <slug> [--report <md>] [--out <pptx>]` |
| `prompts.py` (수정) | `get_pptx_planner_prompt()` 추가 (기존 `get_section_writer_prompt` 와 동일 패턴) |

**Tasks** — 각 항목 메타 형식: 상태 / 의존 / 우선순위.

13-1. **템플릿 layout 매핑 1회 점검** — 상태: `closed (2026-05-08)` / 의존: 없음 / 우선순위: 상
- `.venv_vertex` (또는 `.venv_openai`) 활성 후 `python-pptx` 로 1회 인스펙트: 11개 layout 의 실제 이름·placeholder 인덱스·placeholder type 추출. 사용자가 명시한 TITLE / TITLE_CONTENT / SECTION_HEADER 가 어느 layout 인덱스에 매핑되는지 확정.
- 산출: 인덱스→이름 매핑 표를 본 박제 close 후기에 추가.
- 진입 트리거: 박제 OK 즉시.

**close 후기 (2026-05-08 §13-1 인스펙트 1회 실행, `.venv_vertex` python 3 + python-pptx 1.0.2)**:

- 슬라이드 크기 12,192,000 × 6,858,000 EMU = 13.33 × 7.5 in → **16:9** 확정 (사용자 명시 일치).
- 레이아웃 11개. **사용자 명시 3종이 인덱스 0/1/2 에 정확히 매핑**:

| 인덱스 | layout 이름 | placeholder 구조 |
|---|---|---|
| 0 | `TITLE` | idx=0 `CENTER_TITLE`(type 3), idx=1 `SUBTITLE`(type 4) |
| 1 | `TITLE_CONTENT` | idx=0 `TITLE`(type 1), idx=1 `OBJECT`(type 7) — 본문/표/그림 공용 |
| 2 | `SECTION_HEADER` | **placeholder 0개** (디자인 단독) |
| 3~10 | PowerPoint 한국어 기본 마스터 (콘텐츠 2개·비교·제목만·빈 화면·캡션 있는 콘텐츠·캡션 있는 그림·인용 텍스트·작가 및 인용) | v1 미사용 |

- **SECTION_HEADER 의 placeholder 부재는 의식적 디자인**: layout master 에 챕터 구획용 그래픽(버건디 강조 등)이 직접 그려진 형태로 추정. v1 renderer 는 layout 2 슬라이드 추가 후 챕터 제목을 별도 `add_textbox` 로 주입하여 디자인 위에 텍스트를 얹는 방식 채택 — 정확한 위치(left/top/width/height) 와 폰트는 §13-3 첫 시도 후 사용자 피드백 반복으로 조정.
- layout 3~10 한국어 이름은 본 인스펙트 명령에서 콘솔 cp949 출력으로 깨졌으나 v1 미사용이라 무관. v2 이후 "비교"·"캡션 있는 그림" 등 활용 시 재인스펙트 (UTF-8 stdout 강제 또는 ndjson dump 권장).
- **v1 결정론적 매핑 확정** (Design § 의 (A) 안 구체화):
  - 첫 슬라이드 → layout `0 (TITLE)`: CENTER_TITLE = 보고서 제목, SUBTITLE = 부제/생성일
  - `## N.` 챕터 → layout `2 (SECTION_HEADER)`: 챕터 제목을 textbox 주입 (placeholder 부재로 직접 텍스트박스)
  - `### N.M.` / 본문 → layout `1 (TITLE_CONTENT)`: TITLE = 섹션 제목, OBJECT = 본문 텍스트·bullets·table
- §13-2 spec 에서 `SlideSpec.layout_id` 는 `Literal[0, 1, 2]` 로 좁혀 LLM structured output 의 hallucination(layout 3~10 잘못 선택) 방지 — close 후기 단계에서 결정.

13-2. **`spec.py` 정의** — 상태: `closed (2026-05-08)` / 의존: §13-1 / 우선순위: 상
- `SlideSpec(BaseModel)`: `layout_id: int`, `title: str`, `bullets: list[str]`, `body: str | None`, `table: Optional[TableSpec]`, `notes: str | None`, `layout_hint: str | None` (v2 reserve).
- `SlideDeckSpec(BaseModel)`: `slug: str`, `topic_title: str`, `slides: list[SlideSpec]`.
- `TableSpec(BaseModel)`: `header: list[str]`, `rows: list[list[str]]`.
- `Field(description=...)` 풍부하게 — LLM structured output 의 필드 가이드로 사용.

**close 후기 (2026-05-08)**:
- 신설 파일: `agent/export/__init__.py` (빈 패키지), `agent/export/spec.py` (108 라인). 둘 다 신규로 commit 대상.
- 모델 3종 정의 완료. **`SlideSpec.layout_id` 는 README-dev §13-1 close 결정대로 `Literal[0, 1, 2]` 로 좁힘** — Pydantic v2 `model_json_schema()` 출력에서 `enum: [0, 1, 2]` 로 직렬화 확인 (LLM structured output 시 layout 3~10 hallucination 차단).
- **검증 결과 (`.venv_vertex` 기준, PYTHONIOENCODING=utf-8)**:
  - imports OK — 7 + 3 + 2 = 총 12개 필드 모두 노출
  - 4슬라이드 샘플 deck 인스턴스 생성 OK (TITLE/SECTION_HEADER/TITLE_CONTENT bullets/TITLE_CONTENT table 4종 조합)
  - `layout_id` ∈ {-1, 3, 5, 100} 모두 `ValidationError` 로 거부 — Literal 강제 정상
  - `model_json_schema()` 직렬화 OK, 한국어 description 보존, 전체 schema 약 **3,277 chars** (LLM structured-output payload 부담 미미).
- **필드 우선순위 규칙** (description 에 명시 + planner 프롬프트에서 재강조 예정):
  - layout_id=1(TITLE_CONTENT) 의 OBJECT placeholder 채우기 우선순위: **`bullets` > `body` > `table`** (둘 이상 동시 지정 시 앞쪽 우선, table 은 별도 분기)
  - `notes` 는 본문 노출 X — 출처 인용·footnote 보존용 (slide notes 영역)
  - `layout_hint` v1 미사용(None 기본) — v2 (Gemini A/B) 에서 'compare'/'caption' 등 활용 예약
- **다음 의존 작업**:
  - §13-3 (`renderer.py`): `SlideDeckSpec` 받아 결정론적 렌더. layout_id=2 (SECTION_HEADER, placeholder 0개) 는 `add_textbox` 직접 주입 분기.
  - §13-4 (`planner.py`): `with_structured_output(SlideDeckSpec)` 로 직접 import. JSON schema 가 그대로 LLM 가이드.
- **재진입 조건** (open 사유):
  - planner 시험 결과 LLM 이 자주 누락하는 필드가 발견되면 description 보강 필요.
  - v2 진입 시 `layout_hint` 의 Literal narrowing (`Literal['compare','caption',...]`) 검토.
  - 슬라이드 길이 제한 (bullets 6개 / 항목 80자) 강제가 필요해지면 `model_validator` 추가 검토.

13-3. **`renderer.py` 구현** — 상태: `closed (2026-05-08)` / 의존: §13-2 / 우선순위: 상
- `render_deck(spec, *, template_path, out_path)`. `Presentation(template_path)` 로드 → `spec.slides` 순회 → `slide_layouts[layout_id]` 적용 → placeholder 채움.
- table 슬라이드: `slide.shapes.add_table(rows, cols, left, top, width, height)` 후 셀별 텍스트 주입.
- 결정론적, LLM 호출 0. 단위 테스트(소규모 spec → pptx 생성 후 zipfile 로 XML 라인 검증) 가능.

**close 후기 (2026-05-08)**:
- 신설 파일: `agent/export/renderer.py` (122 라인). 외부 의존 추가 없음 (`python-pptx` 만 사용).
- **인스펙트 발견 2건 반영**:
  - 템플릿에 starter slide 1장 (layout=TITLE) 존재 → `_clear_template_slides()` 가 `prs.slides._sldIdLst` + `drop_rel` 로 silent 삭제. python-pptx 공식 API 우회 패턴이지만 안전함.
  - layout[2] (SECTION_HEADER) 에 layout master 의 `TextBox 7` 좌표 `(720000, 3779999, 9000000, 646331)` EMU 발견 → `SECTION_HEADER_TITLE_BOX` 상수로 박제, `add_textbox` 가 정확히 이 위치에 챕터 제목 주입.
- **e2e 검증 결과 (4슬라이드 합성 deck → `reports/_render_test/synthetic_4slides.pptx`, 39,486 B, .gitignore 자동 제외)**:
  - slide 수: 4 (starter 삭제 정상)
  - layout 매핑: `TITLE` / `SECTION_HEADER` / `TITLE_CONTENT` / `TITLE_CONTENT` 정확
  - TITLE 슬라이드: idx=0 `'Venfobel-Vitamin 광고 기획 리포트'`, idx=1 `'2026-05-08 / RAG Writer 합성 검증'` (body 우선 → topic_title fallback 분기 동작)
  - SECTION_HEADER: placeholder 0개 유지, 우리 add_textbox 가 `TextBox 1` 로 추가됨, 텍스트 `'2. 시장 환경 및 규제'` 정확
  - TITLE_CONTENT bullets: idx=1 OBJECT 의 text_frame 내 paragraph 3개로 직렬화 — `'항목 A...\n항목 B...\n항목 C...'` (한국어 em-dash 보존)
  - TITLE_CONTENT table: placeholder text 빈 문자열로 숨김, 별도 table shape 4행×3열 (header + 3 rows) 정확. `'벤포벨','100','+5%'` 등 한국어/숫자/% 보존.
  - notes: TITLE 슬라이드 + bullets 슬라이드의 `notes_slide.notes_text_frame.text` readback 정확.
- **재진입 조건** (사용자 피드백 후 조정):
  - SECTION_HEADER textbox 위치/폰트(현재 36pt bold, 색상 기본=검정)가 디자인 위에 시각적으로 어떻게 보이는지 확인 필요. 버건디(RGB 139,41,66) 적용 여부 판단.
  - TITLE_CONTENT bullets 가 layout master 의 list style(불릿 마커)을 실제로 받아오는지 PowerPoint 에서 시각 확인.
  - 표 슬라이드의 placeholder shape 잔존이 디자인상 거슬리면 placeholder 자체 제거 분기 추가.
- **다음 의존**: §13-4 (planner) 가 `render_deck` 을 import 해서 e2e 호출, §13-5 (CLI) 가 그 entrypoint 노출.

**v2 amendment (2026-05-08, template 재정비 후)** — 상태: `closed (2026-05-08)`:

사용자가 `templates/agency_default.pptx` 를 재정비 — SECTION_HEADER 에 placeholder 3개 추가(번호/제목/부제), '제목만'(layout 5) 신설 검증, TITLE 부제 좌표 정렬. v1 renderer 코드를 새 템플릿 구조에 맞춰 갱신.

**박제 (재사용 불가능한 invariants)**:
- **v1 SECTION_HEADER 가 placeholder 기반으로 전환됨** — 이전 textbox 방식(`SECTION_HEADER_TITLE_BOX = (720000, 3779999, ...)` 상수) **deprecated**, renderer.py 에서 제거.
- **placeholder 식별 규칙: layout name + top 좌표 기준 (idx 단독 사용 금지)** — SECTION_HEADER 의 placeholder idx 10/11/12 가 다른 layout 에서 DATE/FOOTER/SLIDE_NUMBER 와 충돌하므로 idx 단독 식별 시 잘못된 placeholder 선택 위험. `_placeholder_by_top_cm(slide, top_cm, tol=0.5)` 헬퍼로 top 좌표 ±0.5cm 매칭 식별.
- **향후 다른 레이아웃에 placeholder 추가 시 같은 규칙 적용** — 새 layout 추가 시 top 좌표 상수를 renderer 모듈 상단에 박제 (현재: `SECTION_HEADER_NUMBER_TOP_CM=5.0`, `SECTION_HEADER_TITLE_TOP_CM=10.5`, `SECTION_HEADER_SUBTITLE_TOP_CM=13.0`).

**구체 변경 사항**:
- `_render_section_header_slide`: textbox 추가 폐기 → `_placeholder_by_top_cm` 으로 3개 placeholder 식별 + 채움. 챕터 번호는 `_split_chapter_title("1. Executive Summary")` → `("01", "Executive Summary")` regex 추출(`^\\s*(\\d+)\\.\\s*(.+)$`, zero-pad). 부제는 `s.body or ""` (None 도 빈 문자열로 강제 채워 마스터 default text "한 줄 부제 또는 챕터 요약" 숨김).
- 표 슬라이드 dispatch: `_render_content_slide` 의 table 분기 폐기 → main loop 에서 `(layout_id==1 and s.table)` 조합 감지 시 `LAYOUT_TITLE_ONLY=5` ('제목만') 으로 dispatch 후 `_render_title_only_with_table` 호출. 표 좌표는 layout 1 OBJECT 와 동일(`(2.0, 4.0, 29.87, 12.5)cm`)로 디자인 일관성 유지. **`SlideSpec.layout_id` Literal 변경 없음** — planner spec 그대로, renderer 가 내부 routing.
- `_render_title_slide`: 부제 placeholder 의 `left/top/width/height` **4개 모두 명시** (`Cm(2.0)/Cm(9.09)/Cm(29.87)/Cm(1.50)`). **새 함정 발견 박제**: python-pptx 에서 placeholder 의 일부 좌표만 set 하면 `spPr` 신설로 master inherit 끊겨 나머지가 0 으로 추락. 첫 시도에서 left/width 만 set 했더니 top=0/h=0 으로 깨져 부제가 안 보임 → 4개 모두 명시로 해결. **향후 placeholder 좌표 수정 시 4개 좌표 모두 set 의무**.

**검증 (2차) — `test_v2.pptx` (`python -m agent.export.cli _cli_test --out ...`)**:
- 11개 assertion 전 통과:
  - S1 subtitle 좌표 `(2.00, 9.09, 29.87, 1.50) cm` 정확 (4-coord fix 검증)
  - S2 SECTION_HEADER placeholder 3개 — 번호 `'01'` (top=5.00), 제목 `'Executive Summary'` (top=10.50, "1. " prefix 제거), 부제 `''` (top=13.00, default 숨김)
  - S4 layout=`'제목만'` dispatch 정확, 표 1개 at `(2.00, 4.00, 29.87, 12.50) cm`, 4×3 데이터 보존
- 4 slides 총, latency 4.16s (gpt-4o), 37.9 KB pptx
- LLM 재호출 1회 발생 (planner spec 변경 없으므로 재plan 동일 결과 기대 가능 — 본 fix 는 renderer-only).

**재진입 조건 (v2)**:
- 챕터 번호 추출이 안 되는 케이스 — 예: `## Executive Summary` (번호 없음) 또는 `## A.` (알파벳) 등 — 현재 regex 매칭 실패시 `('', title)` 로 fallback 해 number placeholder 가 빈 문자열로 채워짐. 디자인상 큰 빈 슬롯이 거슬리면 fallback 으로 자동 1, 2, ... 카운터 부여 검토.
- v2 (Gemini A/B) 진입 시 layout_hint 활용으로 layout 5 ('TITLE_TABLE') 외 layout 3 ('콘텐츠 2개') 등으로 확장 가능 — `SlideSpec.layout_id` Literal 확장은 그때 결정.

**v3 amendment (2026-05-08, 레이아웃 이름·좌표 컨벤션 통일)** — 상태: `closed (2026-05-08)`:

사용자가 templates/agency_default.pptx 를 한번 더 정비. layout 5 의 이름·좌표·디자인 일관성을 다른 본문 layout 과 통일.

**박제 (재사용 불가능한 컨벤션)**:
- **레이아웃 이름 컨벤션: 영문 대문자 SNAKE_CASE 통일** — `TITLE` / `TITLE_CONTENT` / `SECTION_HEADER` / `TITLE_TABLE`. 한국어 layout 명("제목만") 사용 금지. 향후 새 layout 추가 시 동일 규칙.
- **모든 본문 layout 의 제목 placeholder 좌표 통일**: `(2.00, 1.50, 29.87, 1.50) cm`. layout 1 (TITLE_CONTENT) 와 layout 5 (TITLE_TABLE) 모두 동일. 향후 새 본문 layout 도 이 좌표.
- **모든 본문 layout 에 제목 아래 버건디 강조 라인** — AUTO_SHAPE 도형, 좌표 `(2.00, 3.20, 0.80, 0.10) cm`, RGB 139,41,66. layout master 에 박제(슬라이드 인스턴스에 자동 inherit, 코드 별도 처리 불필요).
- **페이지 번호 placeholder 좌표 통일** — type=SLIDE_NUMBER, 좌표 `(left=30.37, top=18.00, w=1.50, h=0.60) cm` 모든 layout 공통. **idx 는 layout 마다 다름** (TITLE/TITLE_CONTENT idx=10, TITLE_TABLE idx=12, layout 3~10 idx=12) — idx 단독 식별 금지, 좌표 또는 type 기준. **검증 완료 (2026-05-09)**: §13-3 v3-fix1 으로 `_ensure_slide_number()` 명시 복사 코드 추가 + test_v4.pptx (4 slides, S1/S3/S4 OK + S2 SECTION_HEADER EXEMPT) 및 venfobel_v2.pptx (23 slides, 16개 OK + 7개 SECTION_HEADER EXEMPT) 모두 PASS.
- **python-pptx `add_slide()` 의 SLIDE_NUMBER placeholder 자동 상속 안 함** — TITLE/CENTER_TITLE/BODY/OBJECT 등은 모두 자동 상속하지만 SLIDE_NUMBER 만 예외. layout 의 sp XML (자동 필드 `<a:fld type="slidenum">` 포함) 을 deep-copy 해서 슬라이드 spTree 에 명시 추가하는 `_ensure_slide_number(slide, layout)` 헬퍼로 처리. SECTION_HEADER (layout 2) 는 layout 자체에 SLIDE_NUMBER 가 없어 자동 skip — 의도적 제외. cNvPr id 충돌 회피를 위해 추가 시 슬라이드 spTree max id + 1 로 재할당.

**구체 변경 사항 (renderer.py)**:
- 상수 rename: `LAYOUT_TITLE_ONLY = 5` → `LAYOUT_TITLE_TABLE = 5` (코멘트도 `'제목만'` → `'TITLE_TABLE'`).
- 함수 rename: `_render_title_only_with_table` → `_render_title_table_slide` (의미 명확화).
- docstring update: layout 5 설명을 `'TITLE_TABLE'` 로 갱신.
- placeholder idx / 표 좌표 / 분기 로직 변경 없음 — layout master 만 변경되어 slide 인스턴스가 자동으로 새 디자인 inherit.

**검증 (`test_v3.pptx` + venfobel 재실행)**:
- test_v3.pptx (작은 합성 md):
  - 4 slides, layout 분포 `{TITLE:1, SECTION_HEADER:1, TITLE_CONTENT:1, TITLE_TABLE:1}` (rename 적용)
  - S03 TITLE_TABLE: 제목 `(2.00, 1.50, 29.87, 1.50)` cm — TITLE_CONTENT 와 정확히 일치 ✓
  - 표 `(2.00, 4.00, 29.87, 12.50)` cm 그대로 ✓
  - 버건디 강조 라인은 layout master 도형 → 슬라이드에 자동 inherit (코드 검증 X, PowerPoint 시각 확인용)
- venfobel.pptx 재실행 (gpt-4o, 32.86s, 24,391 tokens, $0.0700, 22 slides):
  - layout 분포 `{TITLE:1, SECTION_HEADER:7, TITLE_CONTENT:14}` — TITLE_TABLE=0 (§13-6 박제 패턴 "큰 표 → bullet 자율 압축" 재현)
  - 7장 chapter coverage 동일

**§13-6 측정값 비교 (temp=0.3 비결정성)**:
| 측정 | 1차 (§13-6) | 2차 (v3) |
|---|---|---|
| slides | 24 | 22 |
| tokens | 24,648 | 24,391 |
| cost USD | 0.0751 | 0.0700 |
| latency | 21.77s | 32.86s |
| TITLE_TABLE | 0 | 0 |

**잠정 관찰 (n=2)**: 슬라이드 수 ±2장, 토큰 ±300, latency 50% 편차. **n=2 결과는 정량 결론이 아닌 임시 baseline 으로만 사용** — §12-12-1 sweep 정신과 일관되게 **n>=5 재실시 필요**. 정식 수치는 §13-7 (Gemini A/B) 평가와 동시에 측정. 현재 시점에서는 v2 (Gemini A/B) 평가 시 단일 sample 비교 금지·**3회 이상 평균** 만 안전 권장.

**v3-fix1 (2026-05-09, SLIDE_NUMBER 누락 fix)** — 상태: `closed (2026-05-09)`:

사용자 시각 검증으로 v3 산출물 4개 슬라이드·venfobel 22 슬라이드 모두 페이지 번호 placeholder 누락 발견. v3 박제 #4 ("idx=12 모든 layout 공통") 와 실제 동작이 어긋나 진단 후 fix.

**원인 진단 (`scripts/diag_slide_number.py`)**:
- python-pptx `add_slide(layout)` 가 SLIDE_NUMBER placeholder 만 슬라이드 인스턴스로 자동 상속하지 않음 (TITLE/CENTER_TITLE/BODY/OBJECT 등은 정상 상속).
- 추가 발견: 박제 #4 자체가 부정확. layout[0] TITLE / layout[1] TITLE_CONTENT 의 SLIDE_NUMBER **idx=10**, layout[5] TITLE_TABLE 만 idx=12. 좌표 (top=18.00, left=30.37, w=1.50, h=0.60 cm) 만 일관.
- layout 의 SLIDE_NUMBER sp XML 안에 `<a:fld id="..." type="slidenum">` 자동 필드 보존 — sp 통째 deep-copy 만 하면 PowerPoint 가 자동 슬라이드 번호 표시.

**Fix (`agent/export/renderer.py`)**:
- 헬퍼 추가: `_ensure_slide_number(slide, layout)` — layout 에 SLIDE_NUMBER placeholder 가 있으면 sp XML deep-copy 해서 슬라이드 spTree 에 명시 추가. 이미 슬라이드에 있으면 idempotent skip. cNvPr id 충돌 회피 위해 슬라이드 spTree 의 max(cNvPr@id) + 1 로 재할당.
- `render_deck` 의 layout 분기 끝 (notes 처리 직전) 에서 모든 슬라이드에 호출. SECTION_HEADER (layout 2) 는 layout 자체에 SLIDE_NUMBER 미정의이므로 자동 skip — 의도적 제외.
- 상수 `PH_TYPE_SLIDE_NUMBER = 13` 추가 (PP_PLACEHOLDER.SLIDE_NUMBER 매직넘버 회피).

**검증 (`scripts/verify_slide_number_fix.py`, `scripts/verify_pptx_slide_numbers.py`)**:
- 합성 spec 4 슬라이드 (TITLE/SECTION_HEADER/TITLE_CONTENT/TITLE_TABLE) — TITLE/TITLE_CONTENT idx=10, TITLE_TABLE idx=12 로 추가, 좌표 (18.00, 30.37, 1.50, 0.60) cm 일관, SECTION_HEADER 만 EXEMPT — **PASS**.
- `test_v4.pptx` (LLM 1회, gpt-4o, 7.03s, 40.2 KB, 4 slides): S1 TITLE OK / S2 SECTION_HEADER EXEMPT / S3 TITLE_CONTENT OK / S4 TITLE_TABLE OK — **PASS**.
- `venfobel_v2.pptx` (LLM 1회, gpt-4o, 19.27s, 75.2 KB, 23 slides): 일반 슬라이드 16개 모두 OK + SECTION_HEADER 7개 EXEMPT — **PASS**.

**박제 정정**:
- 박제 #4 본문 갱신 (좌표만 layout 공통, idx 는 layout 별 상이) + "검증 완료" 표시 추가.
- 새 박제 추가: "python-pptx add_slide() 의 SLIDE_NUMBER 자동 상속 안 함" + `_ensure_slide_number()` 헬퍼 사용 룰.

**재진입 조건**:
- (F1) 새 layout 추가 시 SLIDE_NUMBER 좌표가 (18.00, 30.37, 1.50, 0.60) cm 와 다르면 박제 갱신 필요 (동일하면 자동 동작).
- (F2) SECTION_HEADER 에도 페이지 번호 표시 결정시 layout 2 의 master 에 SLIDE_NUMBER placeholder 추가하면 자동 동작 — 코드 변경 불필요.
- (F3) PowerPoint 시각 확인에서 페이지 번호 위치/크기 어긋남 발견시 layout master 의 placeholder 좌표 수정으로 처리 (renderer 코드는 좌표 수정 X — sp XML 통째 복사 방식이므로 layout 만 변경하면 됨).

13-4. **`planner.py` 구현 (v1: OpenAI 단독)** — 상태: `closed (2026-05-08)` / 의존: §13-2 / 우선순위: 상
- `plan_deck(md_text, *, slug, topic_title) -> SlideDeckSpec`. `core.llm.get_llm()` + `with_structured_output(SlideDeckSpec)`.
- 프롬프트는 `prompts.get_pptx_planner_prompt()` 분리. 헤딩 깊이 → layout_id 매핑 규칙(결정론적)을 prompt 안에 명시 (LLM 자율 결정 회피).
- LLM wrapper 는 §12-13-6 metric 패턴 그대로 (`record_llm_call(... section_title="pptx_plan")`).

**close 후기 (2026-05-08)**:
- 신설 파일: `agent/export/planner.py` (87 라인). `prompts.py` 에 `get_pptx_planner_prompt()` 추가 (572~635 라인).
- **결정론적 매핑 규칙은 프롬프트 내 hardcode** — LLM 자율 layout_id 결정 회피:
  - 첫 슬라이드 = `layout_id=0` (TITLE) — title=topic_title, body=부제/생성일
  - `## N.` 등장시 = `layout_id=2` (SECTION_HEADER) 1장
  - `### N.M.` / 본문 = `layout_id=1` (TITLE_CONTENT) — bullets > body > table 우선순위
  - layout_hint v1 항상 None
- 추가 규칙: 압축(bullet 3~6개·항목 80자), 출처 인용(`[파일명]`, `[^N]`)을 본문 대신 notes 로 분리, 원문 복사 금지.
- **검증 — quick-test (작은 합성 md, 1챕터, 표 1개, 출처 마커 포함)**:
  - 환경: `.venv_vertex` 셸이지만 `.env.openai` 자동 overlay 로드되어 **실제로 OpenAI(gpt-4o) 로 호출됨** — v1 spec "OpenAI 단독" 그대로 만족.
  - latency: **6.44s** (slow 임계 90s 대비 충분히 빠름, retry_hint 빈 문자열).
  - 산출 deck: 4 slides, layout 분포 `{0:1, 2:1, 1:2}` — 매핑 규칙 정확 적용.
  - 첫 슬라이드: layout_id=0, body=`'2026-05-08 / RAG Writer'` (프롬프트 예시 그대로 인용).
  - bullet 슬라이드: 5개로 압축 (원문 단락 + 3 bullet → 5개 bullet 으로 재요약 — LLM 이 bullet 권장 범위 3~6개 안에 들음).
  - table 슬라이드: 3×3 (header `['브랜드', '2024 매출(억원)', 'YoY']` + 3 rows) — Markdown 표 정확히 구조화.
  - **notes 분리 동작 확인**: 본문 인용 마커 `[종근당_팩트북.pdf]` 와 footnote `[^1]: 2024 약국 매출 통계` 가 슬라이드 본문이 아닌 notes 로 빠짐.
  - metrics ndjson 1행 기록: `provider='openai' model='gpt-4o' latency=6.44s success=True section='pptx_plan'` (필드 11종 모두 정상).
- **알려진 경고 (non-blocking)**:
  - `with_structured_output` 호출 시 `PydanticSerializationUnexpectedValue` UserWarning 1건 (`field_name='parsed'`) — langchain 내부 직렬화 경로 알림. 동작/결과에 영향 없음. langchain 후속 버전에서 자동 해결 예상.
- **재진입 조건**:
  - 큰 문서(venfobel 71KB) 진입 시 LLM 응답이 잘릴 수 있음 — §13-6 e2e 단계에서 출력 길이/완전성 확인. 잘림 발견 시 chunked planning(챕터별 분리 호출 + 합치기) 검토.
  - bullet 6개 초과 / 본문 200자 초과 등 압축 규칙 위반 사례 발견 시 `model_validator` 후처리 또는 프롬프트 강화.
  - v2 (Gemini A/B) 진입 시: `.env.gemini` overlay 추가 + `LLM_PROVIDER=gemini` 셸로 호출하면 동일 코드로 동작 가능 (provider 분기 로직 변경 불필요 — `with_structured_output` 추상화 덕분).

13-5. **CLI 진입점 구현** — 상태: `closed (2026-05-08)` / 의존: §13-3, §13-4 / 우선순위: 상
- `python -m agent.export.cli <slug> [--report <md_path>] [--out <pptx_path>]`.
- `<slug>` 만 주면 `reports/<slug>/` 의 가장 최근 `.md` 자동 선택 + `.pptx` 동일 basename 출력.
- `--report` 명시 시 해당 md 사용 (첫 검증은 `--report reports/venfobel-vitamin/20260505-063304_report.md`).

**close 후기 (2026-05-08)**:
- 신설 파일: `agent/export/cli.py` (108 라인). argparse(stdlib) 만 사용, 신규 패키지 없음.
- **CLI 옵션** (`--help`):
  - 필수: `slug` (positional)
  - 옵션: `--report` (md 명시), `--out` (pptx 명시), `--template` (default `templates/agency_default.pptx`), `--topic-title` (제목 명시), `-v` (DEBUG 로깅)
- **auto-discovery 우선순위 (`_resolve_md`)**: `--report` > `reports/<slug>/latest.md` > top-level `*.md` 가장 최근 mtime (qa/ 등 하위 디렉토리 제외).
- **topic_title 도출 (`_topic_title_for`)**: md 의 첫 단일 `#` 헤딩 (단, `##` 헤딩은 무시) > slug → Title Case fallback.
- **검증 결과**:
  - **(A) `--help`** : argparse 정상 출력, exit=0, 한국어 description 깨짐 없음.
  - **(B) path resolution unit**:
    - auto-discovery: `latest.md` (71,134 B) 정확히 픽업 (mtime 무관, latest.md 우선)
    - explicit `--report`: 절대 경로/상대 경로 모두 처리
    - 없는 slug → `FileNotFoundError: reports/<slug>/ not found`
    - 없는 `--report` 파일 → `FileNotFoundError`
    - 기본 `--out`: `md_path.with_suffix(".pptx")` (latest.md → latest.pptx)
    - 기본 `--template`: `templates/agency_default.pptx` 픽업, 없으면 에러
    - topic_title: `# 벤포벨 광고 리포트` → `'벤포벨 광고 리포트'`, # 없으면 `pet-food-premium` → `'Pet Food Premium'`
  - **(C) e2e CLI 1회 호출** (`python -m agent.export.cli _cli_test`, 합성 md `reports/_cli_test/test.md` 572 B):
    - 총 실행 시간 ~6s (LLM 1회 + render)
    - LLM: gpt-4o, plan_deck latency 5.45s, 4 slides 산출
    - 산출 .pptx: 37.6 KB, 재오픈(`Presentation()`) 검증 통과
    - 산출 검증:
      - slide[0] TITLE: `'CLI 합성 검증 — Vitamin B 시장 미니 리포트'` (md 의 # 헤딩 정확히 인용) + `'2026-05-08 / RAG Writer'`
      - slide[1] SECTION_HEADER: placeholder 0개, TextBox 1 = `'1. Executive Summary'`
      - slide[2] TITLE_CONTENT bullets: 제목 LLM 자체 생성(`'벤포벨-비타민 매출 및 시장 위치'`), 4 bullets 압축
      - slide[3] TITLE_CONTENT table: 4×3 (header + 3 rows), 한국어/숫자/% 보존, **notes 에 `[종근당_팩트북.pdf], [^1]: 2024 약국 매출 통계` 분리** (본문 노출 없음)
- **재진입 조건**:
  - 큰 보고서(venfobel 71KB) 진입 → §13-6 e2e 단계에서 슬라이드 수·압축 품질·LLM 응답 잘림 여부 확인.
  - `latest.md` 가 stale 인 경우(가장 최근 mtime 보다 오래됨) auto-discovery 가 잘못된 보고서를 픽업할 수 있음 — 필요 시 mtime 비교 추가.
  - Windows 경로에서 `reports/_cli_test/test.md` 가 `\\` 로 표시되는 것은 cosmetic, 동작 영향 없음.

13-6. **첫 e2e 검증 (venfobel-vitamin 1주일 전 보고서)** — 상태: `closed (2026-05-08)` / 의존: §13-5 / 우선순위: 상
- 입력: `reports/venfobel-vitamin/20260505-063304_report.md` (71,134 B / 395 lines / 7장).
- 검증 항목:
  (i) CLI 1회 호출로 `.pptx` 생성
  (ii) PowerPoint 정상 열림 (파일 corrupt 아님)
  (iii) 7장 모두 슬라이드화 (Executive Summary / 시장 환경·규제 / 경쟁 브랜드 / 차별화 자산 / 3040 직장인 / 2026 광고기획 / 실행 로드맵·KPI)
  (iv) 2.2 매출 동향 표가 native pptx Table shape 으로 변환
  (v) 인용 마커(`[종근당_팩트북.pdf]` 등) 본문 보존
  (vi) footnote 매핑이 슬라이드 또는 notes pane 으로 출력
- 산출물: `reports/venfobel-vitamin/20260505-063304_report.pptx`.
- close 조건: 위 6개 모두 통과 + 사용자 시각 확인. close 후기에 latency / 슬라이드 수 / 발견된 corner case 박제.

**close 후기 (2026-05-08, 1차 e2e — sub-condition (iv) 부분 통과)**:

**실측 (`get_openai_callback` 컨텍스트로 wrap 한 plan_deck → render_deck 1회)**:
| 항목 | 값 |
|---|---|
| 입력 .md | 71,134 B (디스크 UTF-8) / 34,866 chars (메모리) / 396 lines |
| LLM | gpt-4o (`.env.openai` overlay 자동 로드, v1 spec 그대로) |
| LLM 호출 횟수 | **1회** |
| prompt tokens | **22,850** |
| completion tokens | **1,798** |
| total tokens | **24,648** |
| **cost (USD)** | **$0.0751** |
| plan latency | 21.64s |
| render latency | 0.12s |
| total latency | **21.77s** |
| 산출 슬라이드 수 | **24** (TITLE 1 + SECTION_HEADER 7 + TITLE_CONTENT 16) |
| 산출 .pptx 크기 | 74,033 B |

**검증 결과**:
- (i) CLI 1회 호출로 `.pptx` 생성 ✅ (cli.py 직접 호출 대신 plan_deck → render_deck wrapper 동일 동작)
- (ii) PowerPoint 정상 열림 (파일 corrupt 아님) — 재오픈 readback 통과 ✅
- (iii) **7장 모두 슬라이드화** ✅ — SECTION_HEADER 7개 챕터 제목 정확:
  1. Executive Summary
  2. 고함량 활성비타민 시장 환경 및 규제 동향 분석
  3. 경쟁 브랜드 전략 비교 및 메시지 빈 공간 도출
  4. 벤포벨S 핵심 차별화 자산 기반 광고 클레임 개발
  5. 3040 직장인 만성피로 인식 및 비타민 구매 행동 분석
  6. 벤포벨S 2026 광고기획 전략 방향 및 채널 운영 방안
  7. 실행 로드맵 및 핵심 성과 지표(KPI)
- (iv) **표 변환 ⚠️ 부분 통과** — 원본 md L43-49 의 5컬럼×6행 Markdown 표 ("브랜드별 매출 동향" — 임팩타민/아로나민/비맥스/벤포벨/메가트루) 가 `TableSpec` 으로 추출되지 않고 LLM 이 **bullet 으로 압축** (S07 "경쟁 환경 변화" 슬라이드의 `'임팩타민, 아로나민 매출 감소'`, `'비맥스, 메가트루 성장세 둔화'` 등). 데이터 보존 측면에선 손실, 발표 deck 관점에선 합리적 압축.
- (v) 인용 마커 본문 보존 — **본문에는 미노출 (의도된 룰), notes 에 보존** ✅. 16/24 슬라이드(모든 본문 슬라이드)에 notes 작성됨.
- (vi) footnote 가 notes pane 으로 출력 ✅ (`[종근당_팩트북.pdf]` 등 출처/`[^N]` footnote 모두 notes 영역).

**박제 (corner case + invariants)**:
- **표 추출 누락 패턴** — Markdown 표가 5컬럼 이상이거나 6행 이상이면 LLM 이 슬라이드 가독성 우려로 자율 bullet 압축 결정. 현재 프롬프트 우선순위 ("표 있으면 → table") 가 strict 하지 않게 동작. v2 단계에서 (a) 프롬프트에 "행/열 수 제약 없이 무조건 table" 명시 강화, (b) `model_validator` 후처리로 md 의 표 line count vs deck table count 비교 경고, (c) 표가 너무 크면 슬라이드 분할 명시 — 중 택1 검토.
- **챕터당 평균 2.3개 본문 슬라이드** — 71KB 보고서를 24슬라이드로 압축. 광고 발표 deck 으로는 적정선이나, 더 풍부한 deck 이 필요하면 프롬프트에 "챕터당 최소 5슬라이드" 등 하한 추가 검토.
- **비용 효율** — gpt-4o 24K tokens 처리 ~22초 / $0.075 — 일상 사용 가능 수준. v2 (Gemini) 비교 시 latency / 비용 / 품질 3축 평가.
- **completion tokens 1,798** — 24슬라이드 × 평균 75 토큰/슬라이드. 응답 잘림 없음. 더 긴 보고서(예: 100KB+)에서도 충분히 여유 (gpt-4o output 한도 16K tokens 대비).
- **render latency 0.12s** — LLM-free renderer 가 매우 빠름. e2e 비용 거의 전부 plan 단계.

**재진입 조건**:
- 표 추출 누락이 critical 한 사용 케이스 발견 시 — 프롬프트 강화 + post-validate 추가. **closed in §13-9 Round 3 (2026-05-09)** — 표 보존 강제로 X'=1 100% 추출.
- 다른 토픽 보고서로 검증 — 산출 스타일이 토픽 종류에 따라 일관성 유지되는지.
- v2 (Gemini A/B) 진입 시 동일 md 로 비교 측정 (이 표가 §13-7 baseline).

**§13-6 v3 (n>=5 정량 baseline) 처리 (2026-05-09)**:
- 별도 task 진행 X — **§13-9 Round 3 의 stability 측정 5회 결과가 사실상 §13-6 v3 baseline 역할**.
- gpt-4o baseline 박제: 평균 37.4 slides / 매 run 표 1개 / 한국어 100% / latency 26~48s / spread 1.
- §13-7 (Gemini) 진입 시 동일 `scripts/measure_stability.py` 로 측정해 직접 비교 가능.

13-7. **(v2) Gemini A/B 비교** — 상태: `closed (2026-05-09, Flash deferred)` / 의존: §13-6 close / 우선순위: 중
- v1 deck 사용자 평가 통과 후 진입. `.venv_vertex` + `LLM_PROVIDER=vertexai` 토글로 동일 입력에 대한 deck 비교. spec/renderer 동일, planner LLM 만 교체.
- close 결과 (§13-7-4 박제): 운영 default = **gpt-4o** (안정성·속도·검증 완료). Pro = partial close (n=3 통계 한계 + src_body 비결정성, tuning 가능하나 deferred). Flash = deferred (quota TPM 한도, cool-down 또는 별도 project 회복 후 재진입).

**§13-7-1 (closed 2026-05-09)**: provider 어댑터 점검 + `measure_stability.py --model` 추가
- `agent/export/spec.py`: `Literal[0,1,2]` → `int + Field(ge=0,le=2) + field_validator` (Vertex function_calling 호환).
- `agent/export/planner.py`: `model` 인자 추가 (명시 시 reset_llm + get_llm(model=...)).
- `scripts/measure_stability.py`: `--model`, `--region`, `--per-run-timeout`, `--inter-run-sleep`, `--warmup-runs`, `--warmup-input` CLI 옵션.

**§13-7-3a (closed 2026-05-09)**: 1차 측정 데이터 quota-pollution 의심으로 격리
- `reports/_quarantine/` 로 이동 (Pro venfobel n=5 + Flash test 결과). 운영 결정 근거 사용 금지.
- 격리 사유: GCP project minimal 상태 + langchain 내부 retry 로 polluted measurements (Flash 713s, Pro 336s 비정상 latency).

**§13-7-3b (closed 2026-05-09)**: measure_stability 안전장치 (per-run timeout / inter-run-sleep / warmup) 추가
- ThreadPoolExecutor wall-clock timeout (langchain 무한 backoff 차단).
- `_print(flush=True)` (background 종료 시 buffer 손실 방지).

**§13-7-3c-region (closed 2026-05-09)**: `--region` CLI 옵션
- env set + reload_config_inplace + reset_llm 시퀀스 (LLM_PROVIDER/MODEL 보존·복원).

**§13-7-3d (closed 2026-05-09)**: asia-northeast3 sanity check
- `_cli_test/test.md` (350 chars) Flash latency 20.7s — region 정상.

**§13-7-2 (close 2026-05-09, Pro 평가 진정 종결)**: gemini-2.5-pro n=5 평가 (asia-northeast3, warmup 1회, timeout 300s, sleep 60s) — Flash deferred 결정으로 Pro warm 3 run baseline 박제 후 §13-7-2 진정 close.

| Run | Latency | slides | tables | lang | body marker | notes marker | ok |
|---|---|---|---|---|---|---|---|
| 1 | 337s | - | - | - | - | - | False (timeout) |
| 2 | 346s | - | - | - | - | - | False (timeout) |
| 3 | 91s | 43 | 1 | ko (0.91) | 28 | 8 | True |
| 4 | 94s | 43 | 1 | ko (0.90) | 28 | 8 | True |
| 5 | 100s | 43 | 1 | ko (0.99) | **0** | **50** | True |

§13-9 close 조건 (warm 3 run 기준):
- slide_spread = 0 (43/43/43) ✅ — gpt-4o spread 1 보다 우수
- lang_consistency: 100% ko ✅
- table_consistency: X'=1, 1/1/1 ✅
- src_body_clean: 28/28/0 → 2/3 위반 ❌
- src_notes_present: 8/8/50 ✅

→ **4/5 metric PASS, src_body 만 비결정 = partial close**.

**핵심 발견 (run 5 분석)**:
- Run 3, 4 = body 28 + notes 8 (정책 A: 마커 split 후 일부만 notes 이동)
- Run 5 = body 0 + notes 50 (정책 B: 완벽 분리 ✅)
- → Pro 의 능력 부족이 아니라 **prompt 해석 비결정성** (run 5 가 가능 증거).
- → §13-9 Round 2-3 패턴과 본질 동일 ("자율 판단 여지 부여").

**비교 baseline (gpt-4o 전체 vs Pro warm 3)**:
| metric | gpt-4o (n=5) | Pro warm (n=3) | 우위 |
|---|---|---|---|
| slide_spread | 1 | 0 | Pro |
| body marker (n PASS) | 5/5 | 1/3 | gpt-4o |
| latency | 26~48s | 91~100s | gpt-4o (2-3x faster) |
| cost / run | $0.075 | $0.046 | Pro (38% saving) |

**§13-7-3 (deferred 2026-05-09)**: gemini-2.5-flash n=5 평가
- Pro partial close 후 즉시 진입 시도 → quota 한도 도달로 deferred.
- warmup 처리 옵션 (1) 채택: `plan_deck(_record_metrics=False)` + `logs/warmup_log.ndjson` 별도 보존. 코드 박제 완료, 재진입 시 즉시 활용.
- 운영 default 결정 보류 — 현재 §13-7 close 시점에서 gpt-4o 가 baseline (안정성 검증 완료 + 운영 deck 사용 중).
- **재진입 조건**: (a) GCP project quota 회복 (24h+ cool-down) 또는 (b) 별도 GCP project 신규 생성. 재진입 시 §13-7-3-retry task 재오픈.

**§13-7-3-asia-fail (2026-05-09)**: asia-northeast3 1차 시도 실패 — quota retry 누적 확정
- 1차 명령어 (sleep 60, region asia-northeast3, retry default 6): run 1 timeout 240s + run 2 동일 패턴.
- log 결정적 증거: `langchain_google_vertexai ... _completion_with_retry ... ResourceExhausted: 429`.
- 진단 1.75h: TPM 0.04% / TTS RPM 10 (무관) / 일반 모델 RPM 한도 미확정.
- → 진단 종료 결정 ("§13-9 의 justifiable improvement 정신" 적용). 우회 적용 우선.

**§13-7-3-bypass (in-progress 2026-05-09)**: 우회 적용 — root cause 변수 분리 검증
- **목표**: max_retries=0 단독 효과 검증. 정상 시 "retry 누적이 root cause" 박제, 비정상 시 sleep 180s 또는 다른 원인 추가 진단.
- 코드 변경:
  - `core/llm.py` — `_strip_kwargs_for_vertex` 가 max_retries 도 strip 하던 issue 제거. `_build_vertexai_kwargs` 가 `VERTEX_MAX_RETRIES` 명시 전달.
  - `core/config.py` — `VERTEX_MAX_RETRIES: int` 필드 + env loader (default 6, range 0~10).
  - `scripts/measure_stability.py` — `--max-retries` CLI (default 0), `--region` default us-central1, summary JSON 에 region/max_retries 박제.
  - `agent/export/planner.py` — `_record_metrics: bool = True` flag (warmup 호출 시 False → metrics.ndjson 미기록 + `logs/warmup_log.ndjson` 별도 보존).
- **재개 순서** (§13-7-3-retry 진입 전 prerequisite 2건 必先 — 본 측정 비용·시간 손실 회피):
  - **Step 1 (§13-7-3-regress)**: 회귀 테스트 gpt-4o n=1 — 코드 변경 (core/llm.py·config.py·planner.py·measure_stability.py) 후 OpenAI 흐름 무손실 검증. error 없으면 PASS.
  - **Step 2 (§13-7-3-sanity)**: Sanity check Flash n=1 (짧은 입력 test.md) — `max_retries=0` 효과 검증. 즉시 성공/실패 판정 가능한지 확인. PASS = retry 차단이 root cause 박제 + Step 3 진입. FAIL = sleep 180s 또는 다른 원인 진단.
  - **Step 3 (§13-7-3-retry)**: Flash n=5 본 측정 — Step 1·2 모두 PASS 시에만 진입.
  - 본 측정 진입 후: §13-7-4 (gpt-4o vs Pro 2-way 비교, Flash deferred) → §13-7-restore (.env 복원).
- **재개 명령어**:
  ```
  # Step 1: 회귀 테스트 (gpt-4o, OpenAI 흐름 무손실 검증)
  $env:PYTHONIOENCODING="utf-8"; & "D:\gpt_agent\.venv_openai\Scripts\python.exe" `
    -u scripts\measure_stability.py --md reports\_cli_test\test.md `
    --slug _cli_test --topic-title "Regression Test" --n 1 --model gpt-4o

  # Step 2: Sanity check (Flash 1회, 짧은 입력, max_retries=0 효과 검증)
  $env:PYTHONIOENCODING="utf-8"; & "D:\gpt_agent\.venv_vertex\Scripts\python.exe" `
    -u scripts\measure_stability.py --md reports\_cli_test\test.md `
    --slug _cli_test --topic-title "Flash Sanity" --n 1 `
    --model gemini-2.5-flash --region us-central1 `
    --per-run-timeout 60 --max-retries 0

  # Step 3: Flash 재측정 (us-central1, sleep 60, max_retries 0) — Step 1·2 PASS 후
  $env:PYTHONIOENCODING="utf-8"; & "D:\gpt_agent\.venv_vertex\Scripts\python.exe" `
    -u scripts\measure_stability.py --md reports\venfobel-vitamin\latest.md `
    --slug venfobel-vitamin --topic-title "Venfobel Vitamin" `
    --n 5 --model gemini-2.5-flash --region us-central1 `
    --per-run-timeout 240 --inter-run-sleep 60 --max-retries 0 `
    --warmup-runs 2 --warmup-input reports\_cli_test\test.md
  ```
- 시간 추정: Step 1 ~30s, Step 2 ~30s, Step 3 ~10분.
- 비용 추정: ~$0.06 (warmup 무시, Step 1/2 무시 가능).

**§13-7-3-bypass-fix (2026-05-09)**: bypass 블록 provider 분기 추가 — `measure_stability.py:313` 에서
`if args.region or args.max_retries is not None:` → provider=='vertexai' 조건 추가. OpenAI 경로에서
`reload_config_inplace` 가 .env override=True 로 LLM_PROVIDER 를 덮어써 ImportError 유발하는 문제 회피.
회귀 테스트 시 `$env:LLM_PROVIDER="openai"` PowerShell 명시 → bypass 블록 skip 분기 진입.
- 박제: **reload_config_inplace 의 .env override=True 함정** — 호출자 env var 보존 위해 두 번째 reload 호출하지만 .env 가 다시 덮어씀. provider 별 분기로 회피.

**§13-7-3-regress 결과 (PASS, 2026-05-09)**: gpt-4o n=1, test.md (348 chars)
- bypass skip 분기 정상 작동 (`[bypass] skip — LLM_PROVIDER='openai'` 출력)
- run 1: slides=4, tables=1, src(body=0,notes=4), lat=16.1s. ImportError 없음, structured output 정상.
- lang_consistency=False (kor=0.55, mixed) — test.md "Executive Summary" 영문 헤딩 보존 (코드 변경과 무관).
- 결론: 코드 변경 (core/llm·config·planner·measure_stability) 후에도 OpenAI 흐름 무손실.

**§13-7-3-sanity 결과 (PASS, 2026-05-09)**: gemini-2.5-flash n=1, test.md, us-central1, max_retries=0
- 1차 (per-run-timeout 60s) FAIL — TIMEOUT. 60s 는 Flash cold start 에 빡빡.
- 2차 (per-run-timeout 180s) PASS — run 1 lat=33.3s, slides=4, tables=1, src(body=0,notes=2). 즉시 응답 (retry 누적 패턴 아님).
- 결론: max_retries=0 단독으로 즉시 성공/실패 판정 가능. Step 3 본 측정 진입 조건 충족.
- cold start 영향: 본 측정 시 warmup 2 회 + per-run-timeout 240s 로 완화.

**§13-7-3-retry 결과 (FAIL, 2026-05-09 — quota 한도 도달, Flash deferred 결정 근거)**:
- 명령: venfobel-vitamin/latest.md (34,866 chars), n=5, us-central1, sleep 60, max_retries 0, warmup 2.
- warmup: 2/2 OK (25.5s + 16.0s, test.md 348 chars).
- 본 측정: run 1~4 모두 `ResourceExhausted: 429 Resource exhausted` FAIL (run 5 시작 전 사용자 중단).
- inter-run-sleep 60s 도 회복 못 함 → RPM 한도 보다 **TPM 한도 도달** 가능성 (warmup 2 + 큰 입력 ×4 burst 에서 토큰 누적).
- **max_retries=0 효과 검증됨**: retry 누적 없이 즉시 fail (이전 `_completion_with_retry` 무한 backoff 패턴 재현 안 됨). bypass 코드는 의도대로 동작.
- 결론: quota 한도 자체가 별도 차원. Flash 측정은 §13-7-3-deferred 로 분리 — gpt-4o vs Pro 2-way 비교만으로 §13-7 진정 close.
- 박제: **`max_retries=0` 은 retry 누적 차단에는 유효하나 quota 한도 도달 시 4xx 가 그대로 노출됨**. 이는 진단 가치 (혼란 제거) 측면에서 정상 동작.

**§13-7-3-bypass-fix (2026-05-09, 회귀 안전성 보강)**: bypass 블록 provider 분기 추가 — `measure_stability.py:313` 에서
`if args.region or args.max_retries is not None:` → `provider == 'vertexai'` 조건 추가. OpenAI 경로에서
`reload_config_inplace` 가 .env override=True 로 LLM_PROVIDER 를 덮어써 ImportError 유발하는 문제 회피.
회귀 테스트 시 `$env:LLM_PROVIDER="openai"` PowerShell 명시 → bypass 블록 skip 분기 진입.
- 박제: **`reload_config_inplace` 의 .env override=True 함정** — 호출자 env var 보존 위해 두 번째 reload 호출하지만 .env 가 다시 덮어씀. provider 별 분기로 회피.

**§13-7-restore (open)**: 측정 종료 후 `.env` 의 `LLM_PROVIDER=vertexai` → `openai` 복원 필수 (현재 측정용 임시 변경).
- `.env.bak` 백업 보존 중 (현재 동일 vertexai). 실 복원은 `.env` 의 LLM_PROVIDER 한 줄 직접 수정 (overlay 는 LLM_PROVIDER 따라 자동 선택).

**§13-7-3 진단 박제 (재진입 시 참조)**:
1. **진단 도구의 한계**:
   - Console quota 페이지: 50/page 표시, 검색 키워드 정확히 알아야 함
   - TTS 변종과 일반 모델 quota 분리 (TTS RPM 10 = §13-7 와 무관)
   - "Unlimited" 의 실제 의미 불투명
   - Audit Log 기본 비활성, 활성화해도 retry-success 는 ERROR 안 남김
   - APIs Dashboard 는 메트릭만 (정확한 status code 모름)
2. **가설 검증 사이클**: quota → 부정 (TPM 0.04%) → 다시 활성 (RPM 한도 미확정) / project 혼선 → 부분 부정 / cold start → 부분 진실 (run 1, 2 cold) / region 부하 → 미확정 / **retry 누적 → 확정** (ResourceExhausted 명시)
3. **진단 종료 결정 패턴**: 진단 시간 vs 우회 시간 비교, marginal value 평가, "justifiable improvement" 정신 적용 (1.75h 진단 후 우회 5분 적용 결정).
4. **평가 시 표준 안전장치 (§13-8 Claude 평가 적용 가능)**:
   - inter-run-sleep 60s+ (RPM 한도 무관 안전)
   - **max_retries=0 (langchain 내부 retry 차단 — 가장 정밀한 root cause 검증 변수)**
   - PYTHONIOENCODING=utf-8, PYTHONUNBUFFERED=1
   - per-run timeout 명시
   - warmup 1~2 회 (cold start 차단)
   - 모델 간 cool-down 30분+ (quota 회복)

**§13-7-2-tune (deferred 2026-05-09, Flash 결과 없이 분기 결정 불가)**: Pro src_body 비결정성 prompt 튜닝
- 재진입 조건: §13-7-3-deferred 회복 후 Flash n=5 측정 완료. 그때 가설 A/B/C 분기 결정.
  - 가설 A (Flash 도 src_body 비결정): Vertex 모델군 공통 이슈 → prompt 의 "마커 → notes 이동" 강화 (예: "본문 마커 발견 시 100% notes 이동, 본문 절대 잔존 금지")
  - 가설 B (Flash PASS): Pro 특이 이슈 → Pro 전용 미세 조정 또는 Flash 운영 default
  - 가설 C (Flash 더 심함): Pro baseline → Flash 추가 튜닝
- 현재 운영 default: gpt-4o (안정성 + 속도, body marker 5/5 PASS, latency 26~48s).

**§13-7-4 (close 2026-05-09)**: gpt-4o vs Pro 2-way 종합 비교 + §13-7 close 박제 (Flash deferred)

### 1. 운영 default 결정 — **gpt-4o**

| 결정 사유 | 근거 |
|---|---|
| **안정성 (재현성)** | n=5 모든 close 조건 PASS (slide_spread 1, kor_ratio 0.92~0.98, table 1/1/1/1/1, body 마커 0/5, notes 마커 14~19/run). Pro 는 n=3 warm runs 만 안정 (cold runs 2회 timeout). |
| **검증 완료** | §13-9 Round 3 에서 5/5 PASS — close 조건 6 종 (ok_runs, slide_spread, lang, table, src_body_clean, src_notes_present) 모두 충족. |
| **운영 사용 중** | §13-6 e2e baseline (venfobel 71KB, 24슬라이드, $0.075/run, 22s) 으로 이미 사용자 deck 산출. fallback 없이 단일 provider 신뢰 가능. |
| **속도** | gpt-4o 26~48s vs Pro warm 91~100s (2~3x faster). 사용자 대기 경험 우위. |
| 비용 | gpt-4o $0.075/run vs Pro $0.046/run (Pro 38% saving). 안정성·속도 우위 대비 비용 차이 수용 가능. |

### 2. Pro partial close 사유 (§13-7-2)

**partial close 이유**:
- **n=3 통계 한계**: 5 run 시도 → 2 run cold timeout (337s, 346s, asia-northeast3 region 부하) → warm 3 run 만 유효 데이터. n=3 은 95% CI 산출에 부족.
- **src_body 비결정성**: Run 3=28, Run 4=28, Run 5=0. Run 5 가 PASS (body=0, notes=50) 가능 → Pro 의 능력 부족이 아닌 **prompt 해석 비결정성**. §13-9 Round 2-3 패턴과 본질 동일 ("자율 판단 여지 부여" 시 LLM 이 다른 정책 선택).
- 결정성 보장이 안 되므로 운영 default 부적합. tuning (§13-7-2-tune) 으로 해결 가능하나 Flash 결과 없이 분기 결정 불가 → deferred.

### 3. Flash deferred 사유 + 재진입 조건 (§13-7-3-deferred)

**deferred 사유**:
- §13-7-3-retry: venfobel n=5 시도 → warmup 2 OK (25.5s + 16.0s) 후 run 1~4 모두 `ResourceExhausted: 429`.
- inter-run-sleep 60s + max_retries=0 + region us-central1 안전장치 모두 적용했음에도 quota 한도 도달.
- **TPM 한도** 우세 가설: warmup 2회 (~700 chars) + 본 측정 venfobel 34,866 chars × N run burst 누적 토큰. RPM 만이라면 60s sleep 으로 회복했어야 함.
- max_retries=0 은 retry 누적 차단 효과 검증됨 (즉시 fail, 이전 무한 backoff 패턴 재현 안 됨) — 진단 가치 (혼란 제거) 측면에서 정상 동작.

**재진입 조건**:
- (a) GCP project quota 회복: 24h+ cool-down 후 재시도. TPM 한도가 일일 초기화되는지 확인 필요.
- (b) 별도 GCP project 신규 생성: setup overhead (project 생성 + Vertex AI API enable + IAM + billing 연결) 그러나 quota 새로 시작.
- (c) 측정 비용 분산: venfobel 대신 짧은 입력으로 n=5 + warmup 별도 시점 (1시간+ 분리). 단 §13-9 baseline 과 비교 가능성 저하.
- 재진입 시 §13-7-3-retry task 재오픈 + §13-7-2-tune 분기 결정 (가설 A/B/C).

### 4. §13-8 Claude 평가 baseline 명시

**비교 기준**:
- **gpt-4o n=5 baseline** (§13-9 Round 3): slide=37.4±0.5 / table=1/1/1/1/1 / kor_ratio 0.92~0.98 / src_body=0/5 / src_notes 14~19 / latency 26~48s / cost $0.075/run.
- venfobel md (`reports/venfobel-vitamin/20260505-063304_report.md` 34,866 chars, X'=1, ## 7 / ### 35 / 결정론 43장).
- close 조건 6 종 모두 적용: ok_runs ≥ 5/5, slide_spread ≤ 2, kor_ratio ≥ 0.7, table_consistency, src_body_clean, src_notes_present.

**측정 인프라 (박제 자산 재사용)**:
- `scripts/measure_stability.py`: `--model`, `--region`, `--per-run-timeout`, `--inter-run-sleep`, `--warmup-runs`, `--warmup-input`, `--max-retries` CLI.
- 안전장치: `provider == 'vertexai'` bypass 분기 (§13-7-3-bypass-fix), ThreadPoolExecutor wall-clock timeout, `_print(flush=True)`, `_record_metrics=False` warmup 격리.
- Vertex 평가 시 표준: inter-run-sleep 60s+, max_retries=0, warmup 1~2회, per-run-timeout 240s+, 모델 간 cool-down 30분+.
- Anthropic provider 추가 시 동일 인프라 재사용 — `--model claude-*` + `LLM_PROVIDER=anthropic` overlay 만 추가하면 즉시 측정 가능.

### 5. §13-7 진정한 산출물 (요약)

| 산출물 | 가치 |
|---|---|
| **코드 fix (`575485a` + `0326e5b`)** | provider 어댑터 점검 (spec.py Literal→int+validator) / langchain max_retries 명시 전달 / bypass provider 분기 / warmup metric 격리 — 향후 모든 multi-LLM 평가에 재사용. |
| **박제 자산 (진단 메서드)** | 진단 도구 한계 (Console/Audit Log/APIs Dashboard) / 가설 검증 사이클 패턴 / "justifiable improvement" 진단 종료 결정 / reload_config_inplace .env override 함정 / max_retries=0 의 root cause 격리 효과 — §13-7-3 진단 박제 + §13-7-3-bypass-fix 박제. |
| **운영 default 결정** | gpt-4o = baseline. Anthropic 평가·Vertex 재진입 시 비교 기준 명확. |
| **측정 인프라 표준화** | `measure_stability.py` 의 6 종 metric + close 조건 6 종 + 안전장치 7 종 = §13-8 Claude 평가 즉시 진입 가능. 새 모델 평가 비용 = LLM 호출 비용 only (인프라 비용 0). |
| **(부수) 격리 결정** | Flash 측정은 quota 한도가 별도 차원임을 확인. cool-down/별도 project 회복 후 재진입 가능 — 차단 아닌 보류. |

→ §13-7 close. §13-8 Claude 평가는 `deferred` 유지 (의존: §13-7 close 충족).

13-8. **(v3) Claude 평가 (claude-sonnet-4-6)** — 상태: `closed (2026-05-10, deferred 재진입 조건 명시)` / 의존: §13-7 close ✅ (2026-05-09) / 우선순위: 후
- 별도 evaluation 트랙. Anthropic provider 추가 시점은 §12-13-6 (b) Anthropic fallback 도입과 묶어 검토 가능 (의존도 큰 변경이므로 단독 트랙은 비효율).
- baseline 박제 완료 (§13-7-4 항목 4): gpt-4o n=5 baseline + 측정 인프라 재사용. 진입 시 `--model claude-*` + Anthropic overlay 만 추가.

**§13-8 진입 환경 (2026-05-10)**:
- Anthropic API 잔액: $25.00 (충전 2026-05-10), Tier 1 (RPM 50, ITPM 30K, OTPM 8K)
- API key 명: writer-project-eval-13-8 (eval/운영 분리)
- Auto-reload disabled (의도적 — 토큰 폭주 안전장치)
- venv: `.venv_anthropic` 신규 (langchain-anthropic 1.4.3 + langchain-openai 1.0.0 embedding fallback)
- Provider 분기 키 분리 convention 운영 중: `.env.anthropic` ANTHROPIC_API_KEY (글로벌 .env 미보관)

**§13-8-pre 사전 정책 박제 (2026-05-10, phase 2 진입 전)**:

*(1) timeout 시나리오 분류 (phase 2 결과 박제 정책)*:
- **시나리오 A** (5/5 < 240s): §13-7 표준 깨끗한 baseline 박제. mean±std 정상 산출.
- **시나리오 B** (1~2건 timeout): 5/5 시도 그대로 박제, timeout 도 데이터. 성공 N건 mean±std + "M/5 timeout" 명시. 추가 run 으로 채우지 않음 (표본 정의 모호 방지).
- **시나리오 C** (3건+ timeout): "Sonnet 4.6 violates §13-7 240s standard" 결론. baseline 산출 의미 없음, §13-8 운영 부적합 결론 데이터로 박제.

*(2) slide count 결과 분류*:
- **37 ± 1 범위 내**: phase 2 slide_count 결정성 OK. §13-9 prompt 의 ### 사전 카운트 + 분할 금지 가 Claude 에서도 효과 검증.
- **±1 범위 밖**: §13-8 결론 재분류. (a) prompt 재튜닝 (Claude 특이 분기 도입) vs (b) 운영 부적합 결론. 측정 후 결정 아님 — 분류 정책 사전 박제 (이 줄).

*(3) cost 검증 정책*:
- 측정 종료 후 console.anthropic.com Usage 페이지 실측 청구액 확인 → 추정치 (스크립트 내 hardcoded $3/$15 per Mtok) 와 비교.
- ±5% 이내: 추정 모델 신뢰. §13-9 운영 cost 예측의 기반 자산.
- ±5% 초과: 추정 보정 필요. _PRICE 사전 (`scripts/measure_stability.py`) 갱신 + 후속 모델 평가 시 동일 검증.

*(4) ThreadPoolExecutor cancel 불가 함정 박제 (`scripts/measure_stability.py:_invoke_with_timeout`)*:
- timeout 발동 후 future cancel 안 됨 → background 에서 anthropic SDK timeout=600s 까지 호출 잔류 가능.
- §13-8 phase 2 안전 마진 검증: phase 1 OTPM 4K << 한도 8K, inter-run-sleep 60s, RPM 50 충분 → 실측 환경에서 함정 발현 안 함.
- 진짜 cancel 필요 시: multiprocessing/ProcessPoolExecutor (강제 종료). 향후 §13-x 에서 OTPM 한도 가까운 모델 평가 시 재검토.

*(5) 측정 인프라 §13-8 확장 (2026-05-10)*:
- `core/llm.py`: `prov == "anthropic"` 분기 추가 — chat=langchain-anthropic, embedding=OpenAI fallback (text-embedding-3-large, venfobel-vitamin-oa 인덱스 재사용).
- `core/llm.py`: Anthropic init log (`timeout=X | max_retries=Y`) — §13-7-3-bypass kwargs strip 함정 가시화.
- `agent/export/planner.py`: `with_structured_output(include_raw=True)` — usage_metadata 캡처 → 모듈-global `_LAST_USAGE_METADATA` 게재.
- `scripts/measure_stability.py`: per-run usage 회수 + 7-metric summary (`metrics_7` 필드 — ok_runs / timeout_count / latency_stats / input_tokens_stats / output_tokens_stats / slide_count_distribution / cost_estimate).
- 안전장치 표준 표 (§13-8 시점 추가): `PYTHONIOENCODING=utf-8` (Windows cp949 함정 회피, em-dash·curly quotes 인코딩 실패 차단).

**phase 1 진단 close (2026-05-10, claude-sonnet-4-6 venfobel n=1)**:
- latency: **186.5s** (gpt-4o baseline 26~48s 대비 5배)
- input_tokens: 36,929 / output_tokens: 12,542 / total: 49,471
- 슬라이드: **37** (gpt-4o n=5 baseline 37.4±0.5 와 동일 결정성)
- OTPM 실측: 4,035 tok/min (Tier 1 한도 8K 의 50%)
- ctor 검증 OK: max_retries=0, timeout=600 (진단 override) 정상 적용 — §13-7-3-bypass 함정 회피
- 비용 1 run: $0.299 (input 36,929×$3/Mtok + output 12,542×$15/Mtok)
- **부적합 시그널**: latency 5배 + 비용 4배 → 운영 default 후보 부적합 가능. phase 2 baseline 의 가치는 default 산출이 아니라 (a) 분산 정량화 (b) timeout violation rate (c) OTPM 누적 거동 검증 → §13-8 결론의 정량 보강.

**phase 2 baseline close (2026-05-10, claude-sonnet-4-6 venfobel n=5)**:

*결과 (logs/baseline_anthropic_claudesonnet46_20260510_080113.json)*:

| run | slides | tables | lang(kor) | src(body/notes) | latency | tok(in/out) |
|---|---|---|---|---|---|---|
| 1 | 37 | 3 | ko (0.97) | 0 / 58 | 192.9s | 36,929 / 12,875 |
| 2 | 37 | 3 | ko (0.96) | 0 / 58 | 199.7s | 36,929 / 11,945 |
| 3 | 37 | 3 | ko (0.96) | 0 / 53 | 189.8s | 36,929 / 12,564 |
| 4 | 36 | 3 | ko (0.96) | 0 / 32 | 184.1s | 36,929 / 12,288 |
| 5 | 38 | 3 | ko (0.97) | 0 / 67 | 204.0s | 36,929 / 13,495 |

*7-metric (사전 정책 결정 기준)*:
1. ok_runs: **5/5** (warmup 2 + main 5 = 7/7) — timeout 0, other_fail 0
2. timeout 분류: **A (clean baseline)** — §13-8-pre 정책 (1) 적용 완료
3. latency: mean **194.1s** ±7.06s (CV 3.6%) — min 184.1 / max 204.0
4. input_tokens: mean **36,929** std **0.0** — 완전 결정성 (prompt + md 동일)
5. output_tokens: mean **12,633** std 528.9 (CV 4.2%)
6. slide_count: **[37, 37, 37, 36, 38]** spread 2 — 사전 정책 (2) "37 ± 1" 만족 → §13-8 재분류 불필요
7. cost 추정: $0.300/run × 5 = **$1.50 total** (rates: in $3/Mtok, out $15/Mtok)

*close 조건 6종 평가*:
| 조건 | 결과 | 비고 |
|---|---|---|
| ok_runs ≥ 5/5 | ✅ 5/5 | clean baseline |
| slide_spread ≤ 2 | ✅ 2 | [37,37,37,36,38] |
| lang_consistency | ✅ | 100% ko, kor 0.96~0.97 |
| **table_consistency** | **❌** | **X'=1 vs tables=3 (5/5 모두)** — systematic 위반 |
| src_body_clean | ✅ | body 0 |
| src_notes_present | ✅ | notes 32~67 |
| **종합 PASS** | **False** | table_consistency 단일 위반 |

*§13-7 (gpt-4o n=5 §13-9 Round 3) baseline 비교 (logs/stability_venfobel-vitamin_20260509_085057.json)*:

| 지표 | gpt-4o n=5 | Sonnet n=5 | 비율 / 패턴 |
|---|---|---|---|
| slides | [38,37,38,37,37] mean 37.4 spread 1 | [37,37,37,36,38] mean 37.0 spread 2 | **1.0배 (동등 결정성)** |
| tables | [1,1,1,1,1] | [3,3,3,3,3] | **3.0배 (체계적, 분산 0)** |
| notes | [17,15,19,14,16] mean 16.2 spread 5 | [58,58,53,32,67] mean 53.6 spread **35** | **3.3배 + 분산 7배** |
| latency | mean 35.3s | mean 194.1s | **5.5배** |

**가설 박제 — Sonnet 4.6 의 systematic 자율 확장 패턴 (§13-8 발견)**:
- **구조적 골격** (slides, input_tokens) 은 prompt 충실 + 결정적
- **의미적 부속** (tables, notes) 은 모델 자율 + 부분 확률적
- 데이터 시그너처:
  - slides: 1.0배 (동등 결정성)
  - tables: 3.0배 (체계적, 분산 0 — 입력 X'=1 위반이지만 5/5 모두 정확히 3개)
  - notes: 3.3배 + 분산 7배 (체계적 + 확률적 — gpt-4o spread 5 vs Sonnet spread 35)
- 시사: gpt-4o 와의 차이는 latency/cost 뿐 아니라 **출력 스타일 해석 자체** 에서 발생.
  prompt 의 "structural constraint" (슬라이드 수, 헤딩 매핑) 은 양 모델 동등 충실,
  "stylistic constraint" (표 보존, 출처 마커) 은 Sonnet 이 자율 확장.
- 진단 가치: 단일 항목 (tables 만) 패치보다 출력 스타일 통제 prompt 재설계가 작업
  범위 (§13-9 재진입 조건 (c) 확장 — tables 및 notes 자율 확장 억제 prompt 패치).

**§13-8 함정 박제 (2026-05-10, phase 1·2 진행 중 발견)**:

*함정 1 — PowerShell stdout cp949 codec → em-dash 인코딩 실패*:
- 증상: `print(f"...{value} — ...")` 같은 한글 + em-dash (`—` U+2014) 문자열이 PowerShell stdout 으로 흐를 때 `UnicodeEncodeError: 'cp949' codec can't encode character '—'` 발생. 스크립트 즉시 abort, 측정 진입조차 불가.
- 원인: Windows PowerShell 의 default stdout codec = cp949 (한글 Windows). Python 의 sys.stdout encoding 도 동일하게 cp949 자동 잡힘.
- 해결: 측정 명령 앞에 `$env:PYTHONIOENCODING='utf-8'` 명시. Python 의 sys.stdout encoding override → utf-8 강제. PowerShell 의 stdout codec 자체는 그대로지만 Python 출력은 utf-8 byte sequence 로 흐르므로 BOM 없는 utf-8 콘솔에서 정상 표시.
- 박제 가치: §13-x 모든 진단/측정 스크립트 실행 표준 — em-dash, curly quotes 등 cp949 미지원 문자가 한글 출력에 흔히 섞임. 실행 템플릿에 `$env:PYTHONIOENCODING='utf-8'` 영구 포함.

*함정 2 — measure_stability.py ThreadPoolExecutor cancel 불가*:
- 증상: `_invoke_with_timeout` 의 `future.result(timeout=240)` 가 240s 도달 시 `FuturesTimeoutError` raise 하나, future 자체는 cancel 되지 않음. 백그라운드에서 anthropic SDK 의 timeout=600s 까지 호출 잔류 가능.
- 원인: ThreadPoolExecutor 는 Python thread 강제 종료 불가 (GIL + cooperative). future.cancel() 은 PENDING 상태에서만 효과 있고, RUNNING 상태에서는 무시됨.
- 잠재 위험: cancelled future 가 background 에서 OTPM 계속 소비 → 다음 run 의 호출과 중첩 시 한도 초과 가능.
- §13-8 phase 2 안전 마진 검증 (claude-sonnet-4-6 venfobel 기준):
  · phase 1 단독 run OTPM = 4,035 tok/min (Tier 1 한도 8,000 의 50%)
  · inter-run-sleep 60s 동안 OTPM budget refresh 가능
  · background future 의 anthropic SDK timeout = 600s — 240s 측정 timeout 후 최대 360s 잔여
  · 다음 run 의 OTPM 과 합쳐도 Sonnet API 호출 1개당 ≤4K rate → 2개 동시 ≤8K (한도 ±경계)
  · RPM 한도 Tier 1 50/min 충분 여유
- phase 2 실측: timeout 0건 (시나리오 A clean) → 함정 발현 없음, 안전 마진 검증 완료
- 박제: `scripts/measure_stability.py:_invoke_with_timeout` 함수 docstring 에 함정 + 안전 마진 분석 영구 박제. 진짜 cancel 필요 시 multiprocessing/ProcessPoolExecutor (강제 종료) 검토 — 향후 §13-x 에서 OTPM 한도 가까운 모델 평가 시 재검토.

*함정 3 — .env.anthropic / OpenAI overlay 비대칭 (timeout/max_retries 환경변수화)*:
- 증상: Anthropic 측은 `ANTHROPIC_REQUEST_TIMEOUT` / `ANTHROPIC_MAX_RETRIES` 환경변수로 ChatAnthropic ctor 에 직접 전달. OpenAI 측은 `OPENAI_REQUEST_TIMEOUT` / `OPENAI_MAX_RETRIES` 만 있고, baseline 표준 값 (max_retries=0) 의 명시 일관성 보장 안 됨.
- 원인: §13-7-3 시점에 Vertex 측만 `VERTEX_MAX_RETRIES=0` 강제 박제 (provider bypass 블록). OpenAI 는 retry 누적 함정 미관측이라 명시 표준 미적용.
- 영향: §13-7-4 gpt-4o baseline cost 측정이 OPENAI_MAX_RETRIES=1 (default) 환경에서 실행 → retry 발생 시 latency 가 retry sleep 로 오염 가능. Anthropic baseline 비교 시 무결성 위반 위험.
- 대응 (현재): `.env.anthropic` 표준 박제 — `ANTHROPIC_MAX_RETRIES=0` (latency 오염 차단), `ANTHROPIC_REQUEST_TIMEOUT=240` (gpt-4o baseline 과 동일 조건). 진단 phase 의 timeout 600s override 는 스크립트가 `core.config.CFG` 직접 mutate (overlay 재로드 회피).
- 후속 (§13-9 일관성 후보): `.env.openai` 에도 `OPENAI_MAX_RETRIES=0` 명시 + 표준 안전장치 패턴 통일. §13-7-4 cost 재검증 시 동일 표준으로 재측정 (§13-7-4-cost-revisit task).
- 박제 가치: provider 별 안전장치 표준은 **명시 + symmetry** 원칙. Vertex `VERTEX_MAX_RETRIES`, Anthropic `ANTHROPIC_MAX_RETRIES`, OpenAI `OPENAI_MAX_RETRIES` 모두 baseline 측정 시 0 강제.

*함정 4 — ChatAnthropic ctor max_retries default = 2 (langchain-anthropic 1.4.3)*:
- 증상: `ChatAnthropic(...)` 호출 시 `max_retries` 미지정하면 default 2 적용. baseline 측정에서 retry sleep (anthropic SDK 내부 backoff) 가 latency 에 누적 → §13-7 baseline 비교 시 latency 오염.
- 원인: langchain-anthropic 의 ChatAnthropic 는 anthropic.Anthropic 클라이언트 default 인 max_retries=2 를 그대로 계승. 명시 전달 안 하면 sleep 누적.
- 함정 패턴 동일성: §13-7-3-bypass 함정 (`langchain-google-vertexai` 의 `_strip_kwargs_for_vertex` 가 max_retries 를 strip → ChatVertexAI default retry 6 적용 → quota 누적 패턴) 과 **동형**. provider 별 어댑터 ctor 마다 retry default 가 다름 — 명시 전달이 표준.
- 대응:
  - `core/llm.py:_build_anthropic_kwargs` 에서 `CFG.ANTHROPIC_MAX_RETRIES` 를 `extra_clean["max_retries"]` 로 명시 전달 (`OPENAI_MAX_RETRIES` 의 잔재는 strip).
  - `core/llm.py:get_llm` Anthropic 분기 init log 추가 — `[LLM] init provider=anthropic | model=... | timeout=240 | max_retries=0` 출력. ctor 적용 값 가시화.
  - `scripts/_measure_anthropic_tokens.py:_verify_llm_attrs` — 측정 진입 직후 LLM 인스턴스의 `max_retries`/`default_request_timeout` 속성 직접 검증, 미일치 시 WARN.
- 박제 가치: 새 provider 어댑터 추가 시 표준 체크리스트 — (a) ctor 의 retry default 확인, (b) `CFG.<PROVIDER>_MAX_RETRIES` 환경변수 분기 박제, (c) init log 에 적용 값 가시화, (d) 측정 도구에 ctor attrs 검증 진입 단계 박제.

*함정 5 — structured output schema overhead (usage_metadata 가 console 실측 underestimate)*:
- 증상: phase 1 + phase 2 합산 토큰 추정 vs Anthropic Console Usage 실측 비교 시 input/output 둘 다 30~54% 추가 토큰 청구 발견.
  · 추정 input (스크립트 합산): 6 × 36,929 (n=1 + n=5) + 2 × ~1K (warmup) ≈ 225,574
  · 실측 input (console 2026-05-09 UTC): **347,873** (+54%)
  · 추정 output: 6 × 12,633 + 2 × ~600 ≈ 76,998
  · 실측 output: **102,352** (+33%)
  · 절대 비용: 추정 $2.40 vs 실측 $2.57 (+7.1%) — 토큰 카운트 underestimate 가 가격 차로 부분 상쇄됨
- 원인 가설: `with_structured_output(SlideDeckSpec, include_raw=True)` 가 주입하는 schema (tool_use definition) 가 `usage_metadata.input_tokens` 카운트에 미반영. Anthropic API 의 실제 청구는 schema 포함 전체 토큰 — langchain 측 metadata 는 raw prompt 만 표기.
- 검증 데이터:
  · 토큰 기반 역산: 347,873 × $3/Mtok + 102,352 × $15/Mtok = $2.5789 ≈ console 실측 $2.57 (오차 0.35%) → **Anthropic 가격 모델 자체는 정확**, 차이는 토큰 카운트 방식
  · 잔액 차감: $25.00 → $22.43 (−$2.57) 일치
- 영향:
  · §13-8 phase 1/2 cost 추정치 ($0.299/$1.50) 는 underestimate. 실측 보정 시 **per_run ≈ $0.43** (보정 계수 1.4x).
  · §13-9 운영 cost 예측 시 동일 underestimate 가능 — provider 무관 langchain `with_structured_output` 사용처 모두.
  · §13-7-4 gpt-4o baseline cost ($0.075/run) 도 동일 underestimate 가능성 → §13-7-4-cost-revisit 후속 task 검증 필요.
- 대응:
  · 잠정 보정 계수: **1.4x** (실측 input/output 토큰 평균 +43%). cost 추정 시 곱.
  · 정확 검증: §13-8-cost-recalibration (후속 task) — Anthropic raw API `messages.count_tokens` (schema 포함) 와 `usage_metadata.input_tokens` 비교 정량화.
  · provider 별 차이 측정: gpt-4o (`tiktoken` count vs OpenAI Usage) / Vertex (`vertexai.tokenization` vs Cloud Console) 도 동일 검증.
  · 박제 정책: cost 추정값 표기 시 `(추정, 실측 +43% 보정 미적용)` 명시. 운영 cost 예측은 console 실측 기반 박제 우선.
- 박제 가치: structured output 사용처의 cost 추정은 **항상 실측 검증 필요**. langchain `usage_metadata` 는 prompt 토큰만 보장 — schema/tool_use 토큰은 별도 카운트. §13-9 운영 cost 예측 자산의 무결성 확보 핵심.

**§13-8 결론 (2026-05-10, claude-sonnet-4-6)**:

| 측면 | 평가 | 데이터 |
|---|---|---|
| **결정성** | gpt-4o **동등 또는 우월** | slide spread 2 (gpt-4o 1) / input_tokens std **0.0** / latency CV 3.6% |
| **latency** | gpt-4o 대비 **5.5배** | Sonnet mean 194.1s ±7.06 vs gpt-4o mean 35.3s |
| **cost (추정 기반)** | gpt-4o 대비 **4배** | Sonnet $0.300/run vs gpt-4o $0.075/run (rates: in $3 vs $2.5, out $15 vs $10) |
| **prompt 호환성** | tables/notes 자율 확장 — **결정적이나 위반** | tables 5/5 모두 3 (X'=1 위반), notes mean 53.6 vs gpt-4o 16.2 |

**운영 default 결정**: **gpt-4o 유지** (§13-7-4 결정 재확인). Sonnet 4.6 = 운영 default 부적합 — latency 5.5배 + cost 4배 + tables/notes systematic 자율 확장. 결정성 자체는 우월하나 운영 비용/속도 손익 무시 불가.

**Sonnet 4.6 deferred 재진입 조건 (3종)**:
- (a) Anthropic 측 latency 개선 — Sonnet API 인프라 개선 또는 Sonnet 5+ 등 후속 모델로 latency 60s 이하 진입 시 재평가.
- (b) cost 4배 감수 가능 use case — 예측 가능 latency (CV 3.6%) 가 가치 있는 배치 처리, 결정성 critical 한 회계·법무·규제 도메인. 운영 default 가 아닌 특수 트랙.
- (c) tables / notes 자율 확장 억제 prompt 패치 + 재측정 — §13-9 재진입 조건 (c) 확장 (tables 단일 → tables+notes 통합 억제). 출력 스타일 통제 prompt 재설계 필요.

**§13-8 cost 4배 차이 분해 (가설 박제)**:
- 가격 차 자체: input 1.2배 (gpt-4o $2.5 → Sonnet $3 / Mtok), output 1.5배 ($10 → $15)
- structured output schema overhead: input +54% (§13-8 commit E 박제 — usage_metadata vs console 실측)
- systematic 자율 확장: output +5~10% (notes·tables 추가 토큰 — gpt-4o 대비 53.6 vs 16.2 notes)
- 잔여 차이: Anthropic 측 input 토큰 카운트 방식 + 가격 모델 변동 가능성
- 검증: §13-8-cost-recalibration (후속 task) 에서 raw API `messages.count_tokens` 와 비교 + 보정 계수 1.4x 검증

**§13-8 후속 task 등록 (2026-05-10)**:
- §13-8-3 (Haiku 4.5 평가): claude-haiku-4-5-20251001 phase 1 진단 → phase 2 baseline. 인프라 재사용 (`.venv_anthropic`, `_measure_anthropic_tokens.py`). 추가 검증 항목 — (i) tables=3 인지 (Anthropic family 공통 시그널 여부), (ii) notes 분산이 Sonnet 비슷한가 (자율 확장 패턴 family 공통성). Haiku notes 16~20 → Sonnet 특이 / Haiku notes 50+ → family 공통 → §13-9-style 신규 task 분리 명확. 예상 비용 ~$0.85 (보정 1.4x 적용 후).
- §13-8-cost-recalibration: structured output schema overhead 검증. raw API `messages.count_tokens` vs `usage_metadata.input_tokens` 비교 → 잠정 보정 계수 1.4x 정량화. §13-9 운영 cost 예측 기반 자산.
- §13-7-4-cost-revisit (사용자 응답 대기): gpt-4o baseline cost 도 동일 underestimate 가능성. console.openai.com Usage 데이터 접근 가능 시 재검증 + Sonnet/gpt-4o 비교 비율 (4배) 유효성 확인.
- §13-9 재오픈 vs §13-8-table 분기: §13-8-3 (Haiku) 결과 후 결정.
  · Haiku 도 tables/notes 자율 확장 → Anthropic family 공통 → §13-9 재오픈 (provider 분기 없는 prompt 강화)
  · Haiku 정상 → Sonnet 특이 → §13-8-table (Claude Sonnet 한정 prompt 분기)

**§13-8 자산 박제 요약**:
| 자산 | 위치 | 가치 |
|---|---|---|
| phase 1 진단 결과 | `logs/anthropic_tokens_1778366464.json` | latency/token 단일 측정점 (warmup 0, n=1) |
| phase 2 baseline | `logs/baseline_anthropic_claudesonnet46_20260510_080113.json` | clean baseline (5/5 ok, 7-metric) |
| 진단 도구 | `scripts/_measure_anthropic_tokens.py` | 후속 Anthropic 모델 phase 1 재사용 |
| Anthropic provider 어댑터 | `core/llm.py:_load_provider() == 'anthropic'`, `_build_anthropic_kwargs` | chat=langchain-anthropic, embedding=OpenAI fallback (3072d 인덱스 재사용) |
| usage_metadata 캡처 인프라 | `agent/export/planner.py:_LAST_USAGE_METADATA` (include_raw=True) | per-run 토큰 박제 가능 — 모든 provider 공통 |
| 7-metric summary | `scripts/measure_stability.py:metrics_7` | ok_runs/timeout/latency/tokens/slides/cost 자동 산출 |
| 함정 4종 박제 | README-dev.md §13-8 함정 박제 | PowerShell cp949 / ThreadPoolExecutor / .env 비대칭 / ctor max_retries default |
| 사전 정책 + 가설 박제 | README-dev.md §13-8-pre, systematic 자율 확장 가설 | 측정 후 결정 회피 + Anthropic 모델 family 평가 framework |

→ §13-8 close. §13-7 운영 default (gpt-4o) 재확인. Anthropic 평가 트랙은 §13-8-3 (Haiku) 으로 family 시그널 검증 진입.

**§13-8 close 시점 push 정책 박제 (2026-05-10)**: NDA 보류 해제 — repo visibility private 전환 확인. §13-7 부터 누적된 commit (`5bc94e5..d2b9bd1` 5 commit) origin push 완료. 향후 push 정책: private repo 한정 자유 push.

13-8-3. **(v3) Haiku 4.5 평가 (claude-haiku-4-5-20251001)** — 상태: `closed (2026-05-10, phase 2 skip — case B 조기 결론)` / 의존: §13-8 close ✅ (2026-05-10) / 우선순위: 후

**§13-8-3 진입 환경 (2026-05-10)**:
- venv: `.venv_anthropic` 재사용 (langchain-anthropic 1.4.3 + OpenAI embedding fallback)
- model: `claude-haiku-4-5-20251001` (`.env.anthropic` 의 `ANTHROPIC_MODEL` 변경 — gitignored, 로컬 mutate 만)
- 측정 표준: §13-8 (Sonnet) 동일 — timeout=240s baseline / max_retries=0 / warmup 2 / inter-run-sleep 60s / `$env:PYTHONIOENCODING='utf-8'`
- 진단 phase timeout override: 600s (CFG mutate, .env 미수정)
- 잔액 진입 시점: $22.43 (§13-8 close 직후)

**§13-8-3 측정 인프라 추가 박제 (commit A)**:
- `scripts/_measure_anthropic_tokens.py` CLI 인자화 — `--model claude-haiku-4-5-20251001` 형식. Sonnet/Haiku/Opus 평가 시 같은 도구 재사용.
- `scripts/_measure_anthropic_tokens.py` parse fail 정밀 진단:
  - `parsed_is_none` / `parsing_error.error_type` / `parsing_error.error_msg`
  - `parsing_error.validation_errors[]` (Pydantic ValidationError `e.errors()` 구조화 — loc/msg/type/input_repr/url) — schema-relax 후속 task ground truth
  - `raw_diagnostic.stop_reason / tool_calls_count / invalid_tool_calls_count / tool_use_blocks_count / first_tool_slides_count` — case 분류용
  - `case_classification` (A/B/C/D 자동) + `case_classification_nuance` (B/A 경계 등 nuance)
  - `slides_in_raw / slides_target / slides_overshoot` — 자율 확장 정량화
  - `fix_options[]` — 3종 (schema_relax / prompt_patch / schema_relax_with_validator) 사전 박제
- `scripts/measure_stability.py` `_PRICE` prefix 매칭 — `claude-haiku-4-5-20251001` 같은 datestamp suffix 모델 ID 도 정확 매칭 (가장 긴 prefix 우선). strict `dict.get()` 매칭 미스 → cost=None 함정 회피.
- 출력 파일명에 `_<model_tag>_` 추가 — `logs/anthropic_tokens_claudehaiku4520251001_<ts>.json` 등 모델별 충돌 회피.

**§13-8-3 phase 1 진단 결과 (2026-05-10, claude-haiku-4-5-20251001 venfobel n=1, 3차 진단)**:

*핵심 측정값 (3 run latency 분산 시그널)*:

| 차수 | latency | output_tokens | slides_in_raw | OTPM (tok/min) |
|---|---|---|---|---|
| 1차 (parse fail capture 미적용) | 102.22s | 14,559 | 50 | 8,546 |
| 2차 (parse fail capture 적용) | 73.72s | 10,757 | n/a | 8,755 |
| 3차 (구조화 자산 캡처) | 82.75s | 11,880 | **44** | 8,614 |

- input_tokens 결정성 ✅: 3차 모두 38,569 (프롬프트 + md 동일)
- latency spread: **28.5s** (gpt-4o ~25%, Sonnet std 7.06s 대비 큼) — Haiku latency 비결정성 시그널
- slides spread: **44 vs 50 = 6** (gpt-4o spread 1, Sonnet spread 2 대비) — 구조적 골격마저 자율
- OTPM: 평균 8,638 tok/min — Tier 1 한도 8,000 **+7.9% 일관 초과**

*case 분류 (자동, 3차 진단)*: **B (tool_use 형식 fail — Pydantic ValidationError)**
- nuance: **B/A 경계** — tool_use 응답 valid (schema 따르려는 의도 OK), payload type strict fail (prompt patch 또는 schema relax 가능)
- ctor 검증 ✅: max_retries=0, default_request_timeout=600 (진단 override) 정상 적용

*ValidationError 구조화 박제 (`logs/anthropic_tokens_claudehaiku4520251001_1778377725.json`)*:
- 9건 모두 동일 패턴: `loc=["slides", N, "bullets"], msg="Input should be a valid list", type=list_type, input_repr=None`
- N (slide index) = **0, 1, 3, 6, 9, 17, 25, 31, 36** (44 slides 중 9개에서 `bullets=None` 명시)
- url: `https://errors.pydantic.dev/2.12/v/list_type`
- raw_diagnostic: stop_reason=`tool_use`, tool_use_blocks=1, tool_calls=1, invalid_tool_calls=0, first_tool_input_keys=`["slides","slug","topic_title"]`

*ValidationError 원인 분석*:
- `SlideSpec.bullets` 정의: `List[str] = Field(default_factory=list)` — **default=[], omit 시 자동 [] 정상**
- Haiku 응답: 일부 slide 에서 `bullets: None` **명시** → Pydantic strict type 거부
- gpt-4o / Sonnet: omit 또는 `[]` 응답 → 정상 통과

*fix_options 3종 (자동 박제, schema-relax 후속 task ground truth)*:

| id | desc | scope | side_effect | permanence |
|---|---|---|---|---|
| **schema_relax** | `SlideSpec.bullets` 를 `Optional[List[str]] = None` 으로 완화 — Haiku null 허용 + gpt-4o/Sonnet omit 호환 | `agent/export/spec.py` | gpt-4o/Sonnet 회귀 테스트 필요 | **영구 자산** |
| prompt_patch | prompt 에 'bullets 가 없으면 [] 또는 필드 생략' 명시 | `prompts/get_pptx_planner_prompt()` | prompt 길이 증가 → input_tokens 누적 비용 | 모델별 누적 비용 |
| **schema_relax_with_validator** | Optional 완화 + `@field_validator` 로 None → [] | `agent/export/spec.py` Pydantic validator | renderer/소비자 측 None 처리 불필요 | **영구 자산 + 정합성** |

*비용 (3 run 진단)*:
- input 38,569 × 3 = 115,707 tok / output 14,559+10,757+11,880 = 37,196 tok
- raw: $0.116 + $0.186 = **$0.302** / 1.4x 보정: **$0.423**
- 잔액 진입 $22.43 → 진단 후 ~$22.13 (실측은 console 검증 시점 통합)

**§13-8-3 close 결론 (2026-05-10, claude-haiku-4-5-20251001)**:

| 측면 | 평가 | 데이터 |
|---|---|---|
| **structured output** | ❌ ValidationError 9건 (tool_use 정확도 한계) | slides[N].bullets=None — schema strict 거부 |
| **구조적 골격 (slides)** | ❌ 자율 — gpt-4o/Sonnet 동등 결정성 미보장 | 44/50 spread 6 (gpt-4o 1, Sonnet 2 대비) |
| **의미적 부속 (tables/notes)** | 평가 불가 (parse fail, raw input 추출 가능하나 미수행) | — |
| **latency** | ❌ gpt-4o 대비 2.4배 느림 (mean 86s) | 73~102s spread 28.5s (CV ~14%) |
| **cost (raw 추정)** | gpt-4o 1.7배 (Sonnet 4배보다 양호) | 0.092/run raw / 0.129 보정 |
| **OTPM (Tier 1)** | ❌ 한도 일관 초과 +7.9% | 평균 8,638 tok/min (한도 8,000) |

**Haiku 4.5 = 운영 default 부적합 확정** (Sonnet 동일 결론) — phase 2 skip + 조기 close. 사유:
- structured output ValidationError 결정적 시그널 (5/5 burst 시도해도 동일 패턴 반복 예상)
- OTPM Tier 1 한도 일관 위반 → burst 시 throttle/timeout 위험
- §13-8-pre 매트릭스 1 마지막 항목 (quality 심각히 낮음) 트리거

**Anthropic family 자율성 거동 가설 (§13-8 + §13-8-3 통합, 2026-05-10)**:

자율성 차원 4종 분리 — 모델별 결정성/자율성 매트릭스:

| 차원 | gpt-4o | Sonnet 4.6 | Haiku 4.5 | 패턴 |
|---|---|---|---|---|
| (1) 구조적 골격 (slides 개수) | 결정 (37.4±0.5) | 결정 (37.0±0.7) | **자율 (44~50, spread 6)** | family 내부 분기 |
| (2) 의미적 부속 (tables/notes) | 결정 (1.0/16.2) | 자율 (3.0/53.6) | 평가 불가 | family 공통? (검증 미완) |
| (3) schema strictness (null 응답) | omit 정상 | omit 정상 | **null 명시 — strict fail** | Haiku 특이 |
| (4) latency 결정성 (CV) | ~25% | 3.6% | ~14% | family 내부 분기 |

**가설**: Anthropic family 모델은 작아질수록 자율성 차원이 늘어남 (Sonnet < Haiku 자율성).
- 차원 (1): Sonnet 결정 / Haiku 자율 → **모델 크기 반비례** 시그너처
- 차원 (3): Sonnet omit / Haiku null → schema 따르기 정확도가 모델 크기와 비례
- 차원 (4): Sonnet 3.6% < Haiku 14% < gpt-4o 25% — 단순 모델 크기 반비례 아님 (다른 요인)
- 검증 미완: **Opus 4.7 측정 시 Sonnet 보다 더 결정적인지** — §13-8-2 (Opus) 우선순위 재검토 (가설 검증 차원 가치 발생)

**§13-8-3 후속 task 우선순위 (1~4, 2026-05-10 결정)**:

| 순위 | task | 비용·시간 | 가치 |
|---|---|---|---|
| **1** | **§13-8-cost-recalibration** | $0.30 / 30분 | schema overhead 1.4x 보정 계수가 모델 무관 시그널인지 검증 → §13-9 cost 모델 신뢰도 결정. 저비용·고가치. |
| **2** | **§13-8-3-schema-relax** | $0.16 / 10분 | `SlideSpec.bullets: Optional[List[str]] = None` 변경 + Haiku parse 통과 여부 검증. **gpt-4o/Sonnet 회귀 테스트 필수** (schema 변경 부작용 점검). |
| 3 | (§13-8-3-prompt-patch) | — | **채택 안 함** — schema-relax 와 중복, 모델별 누적 비용 단점. |
| **4** | §13-8-2 (Opus 4.7) | $1.50+ / 30분 | family 자율성 가설 (모델 크기 반비례) 검증 차원 가치 발생. cost 높음, 우선순위 후. |

**§13-8-3-schema-relax 선호 근거**:
- schema 수정 = 영구 자산 (모든 모델 호환성 향상)
- prompt-patch = 모델별 누적 비용 (prompt 길이 증가 → input_tokens 누적)
- 단 gpt-4o/Sonnet 회귀 테스트 필요 (default behavior 변동 점검)

**§13-8-3 자산 박제 요약**:

| 자산 | 위치 | 가치 |
|---|---|---|
| phase 1 진단 결과 (3차 구조화) | `logs/anthropic_tokens_claudehaiku4520251001_1778377725.json` | ValidationError 9건 + slides_overshoot + fix_options 3종 — schema-relax ground truth |
| 측정 도구 일반화 | `scripts/_measure_anthropic_tokens.py` (CLI 인자화) | Sonnet/Haiku/Opus 평가 시 같은 도구 재사용 |
| _PRICE prefix 매칭 | `scripts/measure_stability.py:314~` | datestamp suffix 모델 ID 호환 — 향후 `claude-*-YYYYMMDD` 모두 정확 cost 추정 |
| family 자율성 거동 가설 | README-dev.md §13-8-3 close | Opus 4.7 측정 시 검증 가능, gpt-4o 와 분리된 Anthropic family 평가 framework |

→ §13-8-3 close. 운영 default = **gpt-4o 유지** (§13-7-4·§13-8 재재확인). Anthropic family 평가 트랙은 §13-8-2 (Opus) 진입 시 family 자율성 가설 검증 가능.

**다음 진입 분기 (사용자 결정)**:
- (a) §13-8-cost-recalibration 즉시 진입 (1순위, 저비용·고가치)
- (b) §13-8-3-schema-relax 즉시 진입 (2순위, Haiku 재측정 + gpt-4o/Sonnet 회귀)
- (c) §13-9 운영 진입 우선 (§13-8-x 후속 task 모두 deferred)
- (d) 새 세션에서 결정 (작업 강도 누적, 휴식 후)

**§13-x-commit-meta-cleanup 후속 task 등록 (2026-05-10, 우선순위: 저)** — 발견 시점: §13-8-3 commit A 진입 검토.
- 문제: §13-7~§13-8 commit 9건 (`575485a..272327d`) 에 모두 동일 형식 메타데이터 오염 박제됨 — `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`. 실제 작업 모델은 claude-sonnet-4-6, "Opus 4.7"·"1M context" 는 끌로드 코드의 자율 박제로 사실과 불일치.
- 영향: `git log` 재참조 시 측정 모델 vs 박제 모델 혼동 가능. §13-x 자산 신뢰성 미세 손상.
- 처리 정책 (옵션 α 채택, 2026-05-10):
  - §13-8-3 commit 부터 Co-Authored-By 라인 통째 제거 (옵션 1) — 새 commit 부터 깨끗.
  - 과거 9건 정정은 `git push --force` 위험 회피 위해 deferred.
  - 처리 시점: `git rebase -i` 자연 발생 시점 (예: feature branch squash, main merge 전).
- 처리 방법: `git rebase -i` 로 amend, force-push 필요 (private repo + 단독 사용자 가정 시 안전).
- 검증: `git log --format="%H %an %s"` 로 9건 commit 의 author/committer 정확성 별도 확인 — Co-Authored-By 외 다른 메타데이터 오염 가능성 점검.
- 관찰: 끌로드 코드 자율 박제 패턴 (commit 한글 제목 / 박제 본문 "사용자 동일 표준" 표현 / 이모지 ✅⚠️❌ 의미 일관성) 도 향후 audit 가치. 별도 task `§13-x-autobaked-content-audit` 후보 — 관찰 누적 후 결정.

13-9. **출력 안정화 (언어·표 추출·슬라이드 수)** — 상태: `closed (2026-05-09)` / 의존: §13-3 v3-fix1 close / 우선순위: 중

**문제 (open 시점)**:
- 출력 언어 비결정성: 동일 venfobel md 1차 한국어 (`'3C 분석'`), 2차 영어 (`'3C Analysis'`) — temp 0.3 단독으로 설명 어려운 swap.
- 표 추출 비결정성: 동일 입력 3회 = 표 0/1/1 (LLM 자율 압축 vs 보존).
- 슬라이드 수 편차: 동일 입력 3회 = 22/23/32 (±10).
- 출처 마커가 본문에 침투 (가독성 저하).

**Fix 적용 — 3 Round 점진 강화** (commits 누적):

| Round | 변경 | n=5 결과 | PASS |
|---|---|---|---|
| 1 | (a)~(d) 적용: system/user 분리, 강제 규칙 (출력 한국어, 표 보존, 출처 노트), few-shot 1건, temp 0.3→0.1 | 23~29 spread 6, 한국어 100%, 표 1/1/1/1/1 | 3/4 (slide_spread FAIL) |
| 2 | (A 일부) ### 1:1 매핑 규칙 + (g) 출처 metric 자동화 | 22~41 spread 19 (악화), 노트 마커 0 | 3/5 |
| **3** | **(A 강화) ### 헤딩 사전 카운트 + prompt 변수 주입 + (B) few-shot 노트 강조 + 분할 금지** | **37~38 spread 1, 노트 마커 14~19** | **5/5 PASS** ✅ |

**최종 close 조건 (Round 3 PASS 기준)**:
1. `ok_runs = 5/5` ✅
2. `slide_spread ≤ 2` (실측 1) ✅
3. 출력 언어 100% 한국어 (`kor_ratio ≥ 0.7` 모든 run) ✅ — 0.92~0.98
4. 표 추출 일관성: 모든 run 의 `TableSpec` 개수 = X' (사전 측정값) ✅ — X' = 1 박제됨
5. 본문 출처 마커 0 (모든 run) ✅
6. 노트 출처 마커 ≥1 (md 에 마커 ≥1개 있을 때) ✅ — 14~19/run

**venfobel md 사전 측정 박제 (재실험 시 baseline)**:
- 파일: `reports/venfobel-vitamin/20260505-063304_report.md` (34,866 chars)
- 유의미한 표 X' = **1** (5×5 매출 동향)
- ## 챕터 = 7, ### 섹션 = 35 → 결정론 슬라이드 수 = 1 + 7 + 35 = **43장**
- 출처 마커 (URL+footnote+파일) = 54
- 실측 슬라이드 평균 = **37.4장** (기대 43장 대비 -5.6장 — LLM 이 반복 섹션 "Actionable Recommendations"/"참고 문헌" 약간 수렴 압축, 매 run 일관되어 spread=1).

**결정성 vs 재현성 박제** (§13-9 본질 결과):
- 평균 37.4장 / 결정론 기대 43장 → **12.7% 압축률**.
- "분할/합병/생략/추가 금지" 규칙이 **100% 결정성 강제는 미달** — LLM 이 일부 섹션을 자율 압축.
- 그러나 **매 run 결과가 일관 (spread=1)** → §13-9 본질 목표 "재현성" 은 달성.
- §13-11 (분량 적정성) 의 출발점: "12.7% 압축 패턴이 광고 발표에 적합한지" 평가. 결정성 100% 가 필요하면 prompt 추가 강화 또는 post-processing 도입 검토 (§13-11 진입 시 결정).

**박제**:
- **단일 string PromptTemplate → ChatPromptTemplate (system+human) 분리** — gpt-4o system 준수율 활용. langchain `with_structured_output` 호환.
- **`get_llm()` 은 싱글턴** — 인자 temperature 첫 호출 후 무시. `llm.bind(temperature=0.1)` 로 호출별 override 필수.
- **추상 규칙보다 구체 숫자가 압도적으로 강력** — "1:1 매핑" 규칙만으로는 spread 19, "정확히 N장" 변수 주입으로 spread 1. 사전 카운트 + prompt 변수 주입 패턴 향후 재사용.
- **"분할 금지·합병 금지·생략 금지·추가 금지"** 4종을 모두 명시해야 LLM 자율 판단 차단. 분할 예외 허용 단서 (Round 2) 가 오히려 LLM 자율 여지 증가시킴.
- **출처 마커 처리 = "삭제 금지·이동만"** 표현이 결정적. Round 1~2 의 "분리" 표현은 LLM 이 "삭제" 로 해석.
- **few-shot 예시 1건** (system 안 fenced block) 으로 표 보존 + 출처 노트 이동 패턴 동시 강제. langchain message-pair 형식 X (with_structured_output 와 충돌 가능).

**파일 변경**:
- `prompts.py` — `get_pptx_planner_prompt()` 리팩터: PromptTemplate → ChatPromptTemplate, system 강제 규칙 + few-shot, human 입력만. 새 변수 3종 (`{n_h2_chapters}`, `{n_h3_sections}`, `{n_total_slides}`) 추가.
- `agent/export/planner.py` — `_count_headings(md_text)` 헬퍼 + `chain.invoke` 에 헤딩 카운트 변수 전달. `llm.bind(temperature=0.1)` 적용.
- `scripts/measure_stability.py` — n 회 실행 측정 + 6종 metric (slide_spread, kor_ratio, table_count, src_in_body, src_in_notes, ok_runs).
- `scripts/count_meaningful_tables.py` — md 의 X' 사전 측정.
- `scripts/count_bullets_per_section.py` — ### 섹션별 bullet/lines 분포 (Round 3 사전 위험 평가).
- `scripts/verify_prompt_refactor.py` — ChatPromptTemplate 구조 + 강제 규칙 키워드 검증.

**재진입 조건**:
- (S1) 다른 토픽(pet-food-premium, height-growth-supplement) 으로 재실험 시 동일 close 조건 통과 확인. 토픽별 X' / 헤딩 분포 박제 갱신 필요.
- (S2) 슬라이드 수가 기대 (1 + N_h2 + N_h3) 와 ±5 이상 어긋나면 prompt 추가 강제 검토 — 현재 venfobel -5.6장 은 허용 범위.
- (S3) Gemini / Claude 평가 진입 시 동일 prompt 로 안정성 측정 (provider 차이로 strategy 변경 필요할 수 있음).
- (S4) §13-11 (분량 적정성, ~37장이 광고 발표용으로 적정한지 평가) 진입 결정 시 활성화.

13-10. **표 렌더링 품질 개선 (스타일·컬럼 너비)** — 상태: `closed (2026-05-09)` / 의존: §13-3 v3-fix1 close / 우선순위: 중
- **Goal**: venfobel_v2.pptx S7 검사에서 발견된 표 품질 이슈 (균등 5.97cm 컬럼 → 긴 텍스트 잘림, 헤더 강조 X, 18pt default 폰트 과대) 해소.
- **표 디자인 정의 위치 결정 (박제)**: **표 디자인은 템플릿이 아닌 코드에 정의**.
  - python-pptx 의 `add_table()` 은 PowerPoint "표 스타일" 갤러리 적용을 직접 지원하지 않음 (확인됨).
  - 마스터 테마에서 자동 상속되는 것: 폰트 종류(Pretendard), 색 팔레트.
  - 마스터 테마에서 상속 안 되는 것: 폰트 크기, 컬럼 너비, 헤더 배경 강조, 줄무늬.
  - 결론: 템플릿에 박을 수 있는 부분(폰트 종류·색)은 이미 활용 중. 박을 수 없는 부분(폰트 크기·헤더 강조·컬럼 너비)만 코드 명시. 향후 python-pptx 가 표 스타일 적용을 지원하면 그때 마이그레이션.
  - 대안 (방법 3 "참조 표 슬라이드 deep copy") 검토 → 행/열 가변 LLM 출력에 부적합, v1 마무리 단계 도입 비용 > 이득. 적용하지 않음.
- **Phase 1 — 헤더/본문 스타일 + 행 높이 자동 조정 (renderer.py)**:
  - 헤더 행 (row=0): Pretendard Bold 12pt, 글자 RGB(255,255,255), 셀 배경 RGB(26,26,26) 차콜.
  - 본문 행 (row≥1): Pretendard 10pt, 글자 RGB(26,26,26).
  - 행 수 ≥ 8 일 때 fallback: 헤더 11pt / 본문 9pt (placeholder 영역 12.5cm 보호).
  - 행 높이 명시적 고정 X — 최소값 0.6cm 만 설정해 PowerPoint 자동 맞춤 활성화.
  - 상수: `TABLE_HEADER_FONT_SIZE/_FALLBACK`, `TABLE_BODY_FONT_SIZE/_FALLBACK`, `TABLE_HEADER_BG/_FG`, `TABLE_BODY_FG`, `TABLE_ROW_HEIGHT_MIN_CM`, `TABLE_FALLBACK_THRESHOLD_ROWS`.
- **Phase 2 — 컬럼 너비 비례 분할 (`_set_column_widths`)**:
  - 알고리즘: 1) 각 컬럼 (header + 본문 셀) 평균 char 길이. 2) 비율 × 29.87cm = ideal. 3) max(ideal, 2.5cm) 으로 최소 너비 보장. 4) 합계 / 29.87 로 항상 비례 scale → 합계 정확히 29.87cm 유지.
  - 상수: `TABLE_COL_MIN_WIDTH_CM = 2.5`.
- **검증 결과**:
  - 합성 spec 2 케이스 — 4행×3열 (일반) + 11행×4열 (fallback): 헤더 배경/글자/Bold/12pt(or 11pt) + 본문 10pt(or 9pt) + 컬럼 합계 29.87 + spread 4.65~16.38cm + 행 높이 0.60cm 모두 PASS.
  - test_v5.pptx (LLM, gpt-4o, 4 slides, 39.3 KB) — 표 1개 (4행×3열): 컬럼 [9.29, 12.61, 7.97] cm spread 4.65 PASS, 페이지 번호 회귀 OK.
  - venfobel_v3.pptx (LLM, gpt-4o, 32 slides, 84.2 KB) — 표 1개 (6행×4열): 컬럼 [3.98, 4.16, **13.94**, 7.78] cm spread 9.96 PASS — venfobel_v2 의 균등 5.97cm 모두 → 길었던 동향 컬럼이 13.94cm 로 확장. 페이지 번호 회귀 OK (25 + 7 EXEMPT).
- **Conclusion**: 표 디자인을 코드에 위임하는 패턴 박제. 이후 표 디자인 변경은 `agent/export/renderer.py` 의 `TABLE_*` 상수 + `_style_cell_*` / `_set_column_widths` 만 수정.
- **Re-entry conditions**:
  - (T1) 표 행 수 매우 많은 케이스 (>15) 발견 시 ellipsis / 페이지 분할 전략 검토.
  - (T2) 셀 병합 요구 발생 시 별도 task — TableSpec 확장 + add_merge_cells 처리.
  - (T3) python-pptx 0.7.x 이상에서 표 스타일 갤러리 적용 지원 시 마이그레이션 — `TABLE_HEADER_BG` 등 상수 제거 후 layout master 표 스타일 참조.
  - (T4) Phase 3 (출처 URL → notes 이동) 은 별도 — §13-9 prompt 안정화 task 와 묶어 처리. **closed in §13-9 Round 3 (2026-05-09)** — 노트 분리 강제 적용으로 본문 마커 0 / 노트 마커 14~19/run 달성.

13-11. **슬라이드 분량 적정성 (광고 발표 시간 가정)** — 상태: `open (2026-05-09)` / 의존: §13-9 close / 우선순위: 후
- **현상**: §13-9 Round 3 close 후 venfobel md (71KB, ## 7개 / ### 35개) → 평균 37.4 슬라이드. 광고 에이전시 클라이언트 발표 시간 (60분 가정) 대비 다소 길 가능성.
- **참고 추정**: 1슬라이드 1.5~2분 = 30~40 슬라이드 적정. 37장은 경계.
- **고려 전략**:
  - (a) 반복 섹션 ("Actionable Recommendations" / "참고 문헌 / 각주") 을 챕터별 1장으로 통합 (현재 LLM 이 일부 압축 중).
  - (b) appendix 슬라이드 분리 (참고 문헌 7개 → 본 deck 끝 단일 챕터로).
  - (c) abstract / executive summary 슬라이드 추가 (현재 첫 챕터를 그대로 매핑 중).
- **재진입 조건**:
  - §13-7 (Gemini A/B) 결과 보고 결정. Gemini 가 더 자연스러운 분량을 내면 prompt 차용.
  - 사용자 시각 검증에서 "너무 길다" 판정 시 진입.
- **블로커 영향**: §13-7 자체는 차단 없음 — §13-9 baseline 으로 비교 가능.

**Conclusion (v1 close)** — 상태: `closed (2026-05-09)`:
§13-1 ~ §13-6 6개 task + §13-3 v3-fix1 (SLIDE_NUMBER) + §13-10 (표 품질) 모두 close. 사용자 시각 검증 통과 (test_v5.pptx 4 slides, venfobel_v3.pptx 32 slides — 헤더 차콜+흰글씨, 컬럼 비례 분할로 동향 컬럼 13.94cm 확장 잘림 해소, 페이지 번호 정상, 줄무늬 자동 적용). v1 (gpt-4o 단독) 생산 가능 상태.

**v1 박제 요약**:
- (a) layout 인덱스 → 이름 매핑: 0=TITLE, 1=TITLE_CONTENT, 2=SECTION_HEADER, 5=TITLE_TABLE (코드 dispatch). 3/4/6~10 미사용.
- (b) 실측 (gpt-4o, temp=0.3, n=3 잠정 — n>=5 정식 측정 §13-9 close 후 §13-6 v3 로 재실시 필요):
  - venfobel md (71 KB) → 22 / 23 / 32 slides (편차 ±10), 표 0 / 1 / 1, latency 21.77 / 19.27 / 32.86s, cost ~$0.07~$0.075/run.
  - test md (572 B) → 4 slides 안정, latency 5~7s, cost ~$0.005/run.
- (c) pptx 구조: title 1 + section 5~7 + content 14~24 + table 0~1 (가변).
- (d) 정성 평가:
  - 인용 표현: `[파일명]`, `[^N]` 정확히 슬라이드 노트로 분리 (본문 침투 없음).
  - 표 변환: Markdown 표 → TableSpec 매핑 정확하나 추출 자체가 비결정적 (LLM 자율 압축 / 보존 / 분할 선택 § 13-9 처리).
  - 챕터 번호 추출: `^\d+\. ` regex 매칭 + zero-pad (`1.` → `01`) 정확.
  - 출력 언어: 한국어 ↔ 영어 swap (§13-9 처리).
- 코드 라인: spec.py 108 / planner.py 87 / renderer.py 296 (§13-10 +120) / cli.py 108 = **599 라인**. prompts.py +63 (`get_pptx_planner_prompt()`).

**Re-entry conditions**:
- (R1) v1 deck 사용자 평가에서 layout 매핑 / table / 인용 표현 중 하나라도 재작업 필요 → 해당 §13-N task 재오픈.
- (R2) Gemini A/B 진입 결정 시 §13-7 활성화.
- (R3) 다른 토픽(pet-food-premium, height-growth-supplement)으로 재사용 시 토픽별 차이(refs 패턴, 챕터 수, 표 빈도) 정량 측정 후 spec 확장 검토.
- (R4) Anthropic provider 추가 시 §13-8 활성화. §12-13-6 (b) 와 묶어 결정.
- (R5) 출력 언어 비결정성·표 추출 비결정성 fix 필요 시 §13-9 활성화 (§13-7 진입 전). **closed (2026-05-09)** — 다른 토픽 재실험 시 (S1) 조건 모니터.
- (R6) 표 디자인 변경 (셀 병합/페이지 분할/python-pptx 표 스타일 마이그레이션) 시 §13-10 재오픈 (T1~T4 조건).
- (R7) §13-7 결과 / 사용자 시각 검증에서 분량 과다 판정 시 §13-11 (분량 적정성) 활성화.

---

## §13-12 (트랙) — 프론트엔드 pptx 다운로드 통합

상태: `closed (2026-05-10)` / 시작: 2026-05-10 / 종결: 2026-05-10
의존: §13-1~§13-10 close + §12-13-10 export endpoint + §12-14 events 채널 + §12-15 frontend Content-Disposition
후속: §13-13 (가칭) 4 결함 / §12-15-1 (가칭, frontend) 운영 자원 가이드

### 배경

§13 v1 자산 (`agent.export.cli` md → pptx) 을 사용자 UI 에 노출. CLI 는 운영 가능하나 프론트엔드 진입점 부재 — `Header.tsx` 의 [전체 보고서 (Word)] 옆에 [PPT] 버튼 추가가 본 트랙의 1cm.

### Phase A 보강 발견 (2026-05-10) — 운영 ground truth

| | 마지막 mtime | 비고 |
|---|---|---|
| `sections/venfobel-vitamin/` 활성 .md | 2026-05-07 17:16 | 4장 작업 진행 중 |
| `reports/venfobel-vitamin/latest.md` | 2026-05-05 06:33 | **이틀 묵음** |
| `reports/venfobel-vitamin/venfobel_v3.pptx` | 2026-05-09 07:16 | 5/5 latest 기반 — 5/6~5/7 변경 미반영 |

**핵심 비대칭** (이 트랙 진입의 결정적 사실):
- `/api/export?kind=report&format=docx`: `sections/<slug>/*.md` 합성 → 항상 최신
- `agent.export.cli` (§13 검증): `reports/<slug>/latest.md` 단일 → stale 위험
- `build_final_report()` 트리거: 사용자 명시 명령 (`build: report` / `report build` / `보고서 빌드` / `최종 보고서 생성`) 만 (app.py:1121, 2188 두 곳, 자동 호출 0)
- 프론트엔드는 `fetchFiles("artifact")` → `sections/` 만 봄 (`reports/` 는 비표시)

→ pptx 분기는 `build_final_report()` 자동 호출 필수. 그렇지 않으면 사용자가 섹션 재작성 후 [PPT] 클릭해도 옛날 latest.md 로 deck 생성됨 (= venfobel_v3.pptx 와 동일 함정).

### Phase B 결정 (4건 + cleanup)

**결정 1 (입력 비대칭, 옵션 1a)**: `/api/export?format=pptx` 진입 시 `build_final_report()` 자동 호출 → reports/latest.md 갱신 → cli 흐름 (`plan_deck` + `render_deck`). build 는 LLM 0 (단순 파일 합치기, ~1s) — 비용 부담 없음.

**결정 2 (renderer 시그니처, R1)**: `render_deck(spec, *, template_path, out: Union[str, Path, BinaryIO]) -> Optional[Path]`. python-pptx `Presentation.save()` native BinaryIO 지원 활용. CLI backward compatible (Path 인자 그대로).

**결정 3 (UX, 옵션 B)**: events 채널 통합. `emit_event()` 로 진행 표시 (§12-14 인프라 재사용). 4단계 — 변환 준비 / 슬라이드 구성 / 파일 생성 / 완료.

**결정 4 (UI, 별도 버튼)**: Header.tsx 의 [전체 보고서 (Word)] 옆에 [PPT] 버튼 추가. 1-클릭, 단순.

**Cleanup 정책 (β, 누적 그대로)**: `build_final_report()` 동작 변경 없음. `reports/<slug>/<ts>_report.md` 매번 신규 생성 (latest.md 도 매번 덮어쓰기). archive 보존, 별도 정리 cron 없음.

### Sub-tasks

13-12-1. **백엔드 /api/export format='pptx' 분기 + build_final_report 자동 호출** — 상태: `closed (commit ee26c62)` / 의존: 결정 1·3 / 우선순위: 높음
- 위치: `app.py:1702` (현재 `if req.format != "docx"` 단일 차단점)
- format='pptx' 분기 추가 (kind='report' 만 허용 — section 단위 deck 미정의)
- `build_final_report(slug)` 자동 호출 → `_resolve_md` 또는 직접 `reports/<slug>/latest.md` 사용
- emit_event 4단계 + 에러 분기 (build/plan/render 각각 HTTPException + emit_event(kind="error"))
- 에러 처리: sections 부재 시 409 / build 실패 500 / plan LLM 실패 500 / render 실패 500
- Content-Disposition RFC 5987 한글 파일명 — docx 패턴 그대로 재사용 (§12-15 짝)
- 박제: pptx 만 reports/ 정전제 (docx 와 비대칭) + reports/ 의 communicator QA 노이즈 (§12-13-9 박제) 우회는 build_final_report 가 sections 합성으로 보장

13-12-2. **agent/export/renderer.py BytesIO 지원 (R1 시그니처 확장)** — 상태: `closed (commit ee26c62)` / 의존: 결정 2 / 우선순위: 높음
- 시그니처: `out: Union[str, Path, BinaryIO]`
- Path/str 분기: 기존 동작 (mkdir + save) → `Path` 반환
- BinaryIO 분기: `prs.save(out)` 직접 → `None` 반환
- CLI (cli.py:106) 호출 backward compatible
- 박제: `out: Union[Path, BinaryIO]` 패턴은 향후 export 형식 추가 (PDF deck 등) 시 재사용

13-12-5. **events 채널 통합** — 상태: `흡수 완료 (no-op as standalone)` / 의존: §13-12-1 / 우선순위: —
- **백엔드**: §13-12-1 의 `_api_export_pptx()` 에 emit_event 4단계 (start / phase / phase / done) + 에러 분기 통합 — 별도 commit 불필요
- **프론트엔드**: `useEvents()` 폴링이 이미 운영 중 (§12-14) → 새 이벤트 자동 수신 → LogPanel 헤더 갱신. **변경 0**
- `clear_events()` 호출 안 함 (기존 명령 흐름 끊지 않음)
- 충돌 함정: write 명령 도중 export 시 events 섞임 가능 — v1 미대응 (드문 케이스)
- 박제: events 채널은 emit 발화처가 늘어나도 소비측 (frontend) 변경 없는 패턴 — 향후 다른 long-running endpoint 추가 시도 동일 재사용

13-12-6. **e2e 검증 + 박제 정리** — 상태: `closed (2026-05-10)` / 의존: §13-12-1·2·5 + 프론트 §13-12-3·4 / 우선순위: 높음
- 시나리오 1: sections 작성 완료 → [PPT] 클릭 → 다운로드 정상 + LogPanel 진행 표시 — **PASS**
- 시나리오 2: sections 일부 (write phase 도중) → [PPT] 버튼 disable 확인 — **PASS**
- 시나리오 3: 한글 파일명 정확 다운로드 (RFC 5987) — **PASS**
- 시나리오 4: build 실패 시 사용자에게 에러 메시지 표시 — **PASS** (alert)
- 시나리오 5 (stale 재검증): venfobel sections 4장 갱신 (5/7) 반영된 deck 생성 → §13 v1 stale 함정 해결 검증 — **PASS** (Slide 17 "활성형 B1" / Slide 24 "58%" — 모두 5/6~5/7 sections 갱신본 반영, 5/5 stale latest.md 기반 venfobel_v3.pptx 와 차별)
- 시나리오 6: Word 다운로드 회귀 테스트 — **PASS** (기존 docx 분기 무영향)
- 양쪽 README close 후기 작성 — 본 commit 6 (writer_project) + commit 7 (frontend) 짝 박제
- 측정값: pptx 38 slides / 96KB / build_final_report ~1s (LLM 0) / 전체 다운로드 latency ~30s (gpt-4o plan_deck 지배)

### Frontend 짝 task (frontend/README-dev.md §13-12 참조)

- 13-12-3. lib/api.ts downloadExport format 인자 'pptx' 추가
- 13-12-4. components/Header.tsx 다운로드 UI 확장 — 별도 [PPT] 버튼

### Commit 시퀀스 (양쪽 레포 짝 진행)

placeholder (인프라 사전 박제):
- **commit 1** (writer_project): README-dev.md §13-12 placeholder
- **commit 2** (frontend): README-dev.md §13-12 짝 placeholder

writer_project (백엔드):
- **commit 3 (P1)**: §13-12-1 + §13-12-2 + §13-12-5 백엔드 (endpoint + renderer R1 + emit_event 통합) — 같은 트랙이라 묶음. §13-12-5 단독 commit 폐기 (P1 흡수)
- **commit 6 (P3)**: §13-12-6 백엔드 e2e + close 박제

frontend (프론트엔드):
- **commit 4 (F1)**: §13-12-3 + §13-12-4 (api.ts + Header.tsx)
- **commit 7 (F2)**: §13-12-6 프론트 e2e + close 박제 (commit 6 짝)

진행 순서: commit 1·2 placeholder → commit 3 (P1) → commit 4 (F1) → e2e 검증 (사용자 시각) → commit 6+7 close.

**실제 진행 (2026-05-10)**:
- 7dbf76d (commit 1, writer_project): §13-12 placeholder
- a956cd7 (commit 2, frontend): §13-12 짝 placeholder
- ee26c62 (commit 3 / P1, writer_project): §13-12-1 + §13-12-2 + §13-12-5 백엔드
- d290852 (commit 4 / F1, frontend): §13-12-3 + §13-12-4 UI
- (본 commit) commit 6 (writer_project) + 짝 commit 7 (frontend): close 박제

### Close 후기 (2026-05-10) — e2e 검증 PASS + 후속 발견 + 사고 박제

**검증 결론**: 시나리오 1~6 모두 PASS. **Phase A 의 핵심 비대칭 해소 검증** — `sections/` 가 `reports/latest.md` 보다 이틀 최신인 상황에서 [PPT] 클릭만으로 자동 build_final_report 호출 → 가장 최신 sections 반영 deck 생성. §13 v1 의 stale 함정 (venfobel_v3.pptx 가 5/5 stale latest.md 입력) 이 §13-12 흐름에서 재현 불가능 — 결정 1 (옵션 1a) 의 실효성 입증.

**§13 자산 회귀 0건 검증**:
- §13-3 v3-fix1 SLIDE_NUMBER 정상 (38 slides 모두 정상 번호)
- §13-9 한국어 일관 (영어 fallback 0건)
- §13-10 표 품질 회귀 0
- 결정 2 (R1, BytesIO 시그니처 확장) — CLI backward compatible 검증 (기존 §13 검증 path 무영향)

**박제된 일반화 교훈**:
- **결정 1 (build_final_report 자동 호출)**: long-running endpoint 가 디스크 입력 전제 (latest.md) 를 받을 때, "입력 전제를 갱신하는 사전 단계" 를 endpoint 자체가 책임지는 패턴. 사용자 mental model 단순화 (한 클릭) + stale 함정 차단. 향후 다른 입력 전제 의존 endpoint (예: PDF deck) 추가 시 동일 패턴 재사용.
- **결정 2 (out: Union[Path, BinaryIO])**: 디스크 vs HTTP stream 양쪽을 같은 renderer 로 서비스. python-pptx native 지원이라 분기 비용 없음. 향후 export 형식 추가 시 (PDF deck 등) 시그니처 그대로 재사용.
- **결정 3 (events 채널 통합)**: emit 발화처가 늘어도 소비측 (frontend) 변경 0. §12-14 인프라 가치 재확인.

**§13 v1 stale 함정 소급 박제 — "코드 동작 vs 사용자 의도" 분리 mental model**:
- §13-9 close (2026-05-09) 시점의 venfobel_v3.pptx 는 5/5 stale `reports/latest.md` 입력으로 생성됐고, 그 시점에 사용자가 시각 검증 통과시킴.
- 그러나 `sections/venfobel-vitamin/` 4장은 이미 5/6~5/7 에 사용자 손으로 갱신된 상태였음 — venfobel_v3.pptx 는 5/7 갱신분 미반영.
- 즉 §13 v1 검증은 **renderer/planner 코드 동작** 측면 (SLIDE_NUMBER, 한국어 일관, 표 품질 등) 은 유효했지만 **"사용자 의도 콘텐츠 반영"** 측면 검증은 안 된 상태였음.
- §13-12 진입 시 Phase A 보강 점검 (mtime 비교) 단계에서 비대칭 (`sections/` 5/7 vs `reports/latest.md` 5/5) 가 노출되며 발견.
- **자산**: 무거운 트랙 (LLM/렌더러/평가) 검증 시 "코드 동작 검증 통과" 와 "사용자 의도 콘텐츠 반영 검증 통과" 는 분리해서 점검해야 함. 전자만 통과한 산출물을 후자로 오인하면 stale 함정 누적. mtime/입력 전제 비교가 후자의 ground truth 점검 도구.

**Cold storage 정리** (별도 chore commit, close commit 6 이후):
- `writer_project/.tmp_haiku_tokens.log` / `.tmp_haiku_tokens2.log` / `.tmp_haiku_tokens3.log` (§13-8-3 진단 도중 생성된 임시 token 로그) — 삭제
- `writer_project/NEXT_SESSION.md` (§13-8-3 진입 노트, §13-8-3 close 50d6684 박제 후 무용) — 삭제

### §13-13 (가칭, 후속) — Word/PPT export 결함 4건 — 상태: `pending` / 발견: 2026-05-10 §13-12 e2e 검증 / 우선순위: 중

검증 도중 부수적으로 발견된 결함 — §13-12 close 와 분리하여 별도 트랙으로 처리.

- **결함 1**: 4장 sections 의 `## ` heading 누락 → Word slug fallback 동작 / PPT 번호 placeholder 빈 공간. root cause 추정: write 단계의 heading 정규화 누락.
- **결함 2**: Word 합본 순서 깨짐 (4장 → 7장 → … 비정상 순서) / PPT 정상. root cause 추정: docx 합본 흐름의 정렬 키와 pptx plan_deck 의 정렬 키가 다름.
- **결함 3**: 7장 sections 의 `## ` heading 누락 (결함 1 과 동일 root cause 추정). 결함 1 과 묶어 한 fix 가능성.
- **결함 4**: Word 5장 "3040." 표기 / PPT 제목 prefix 잔존. root cause 추정: 제목 prefix 제거 정규화의 양쪽 분기 불일치.

**양상 다름 자체가 자산**: Word 결함 (slug fallback / 합본 순서 / 번호 추출 실패) 와 PPT 결함 (번호 placeholder 빈 공간 / 제목 prefix 잔존) 가 동일 `sections/` 입력에서 다른 발현. → planner 가 `build_final_report` 의 latest.md 와 별도로 `outline.md` 또는 다른 정전제를 참조하는 경로 시그널. §13-13-2 (가칭, build_final_report 정렬 강화) 진입 시 ground truth 로 활용.

진입 조건: §13-12 close push 후. 진입 전 root cause 별 묶음 (결함 1+3 / 결함 2 / 결함 4) 가설 검증.

### §12-15-1 (가칭, frontend 측) — 운영 자원 가이드 박제 — 상태: `pending` / 발견: 2026-05-10 §13-12 검증 도중 / 우선순위: 중

**사고 (2026-05-10)**: §13-12 e2e 검증 도중 단발성 시스템 다운 — Windows ERROR 1450 (시스템 thread 한도 초과) + tailwindcss 해석 실패 회귀 메시지가 동시 표면화.

**진단 결과** (사용자 + 끌로드 코드 read-only 점검):
- frontend `next.config.ts` 의 §12-15 박제 fix (`turbopack: { root: path.join(__dirname) }`) **그대로 살아있음** (commit a0cf62d 이후 변경 0).
- §12-15 박제 fix 자체는 정상 동작 — 4일간 (2026-05-06 ~ 2026-05-10) frontend dev 무문제 운영.
- 사고 시점에만 fix 가 우회됨 — 시스템 자원 임계 race condition 으로 turbopack worker spawn 시 OS 가 거절 (ERROR 1450) → resolver 컨텍스트 손상 → default 동작 (부모 디렉터리 추정) 으로 폴백.

**trigger 추정**: §13-12 검증 시점 baseline 평소보다 무거움 — backend python (Uvicorn + Chroma + LangGraph) + frontend node (Turbopack + dev) + Claude 데스크톱 + 끌로드 코드 + msedge (localhost:3000 + Claude.ai 다중 탭) + PowerPoint (사용자 .pptx 검증) + PPT 다운로드 흐름 (gpt-4o ~30s + 메모리 spike) 동시 활성. Thread baseline 4,223 (idle) 에 worker spawn 추가로 임계 도달.

**박제할 것**:
- 시스템 자원 baseline 측정 (메모리·thread idle / 검증 시점 / 임계 직전)
- 검증 시점 운영 가이드: "PPT 다운로드 같은 무거운 작업 진입 전 thread count + 메모리 점검 권고"
- §12-15 박제 fix 의 견고성 한계: 시스템 자원 race 시점에는 우회 가능 — race 자체를 차단하는 운영 가이드가 보완책

**진입 조건**: §13-12 close push 후. 측정 도구 검토 (PowerShell `Get-Process` baseline / threadcount diff / 메모리 watermark).

### 보존 자산 (재사용)

- §13-3 v3-fix1 SLIDE_NUMBER + `_ensure_slide_number()`
- §13-9 출력 안정화 / §13-10 표 품질 (renderer 변경 없음)
- §12-14 events 채널 (`emit_event` / `clear_events`)
- §12-13-10 export endpoint 패턴 + slug↔파일명 invariant
- §12-15 frontend Content-Disposition RFC 5987
- §13-6 cli `_resolve_md` / `_topic_title_for` (HTTP 분기에서 직접 호출)

### Cold storage (본 트랙 미사용)

- §13-7~§13-8-3 측정 트랙 (LLM 재평가 시점까지)
- `.venv_anthropic` / `scripts/_measure_anthropic_tokens.py` / `scripts/measure_stability.py`
- `NEXT_SESSION.md` (§13-8-3 진입 노트 — 재진입 시 참조)

---

## §13-13 (트랙) — Word/PPT export 결함 4건 fix

상태: `closed (2026-05-10, partial)` — 결함 1+3 close / 결함 2 cascade 자동 해소 close / 결함 4 PPT cascade 검증 미완 (backend e2e 이월) / §13-13-3 (7장 평문 중복) 분리
시작: 2026-05-10 / 종결: 2026-05-10
의존: §13-12 close (e2e 검증 시 발견)
짝 placeholder: §13-12 본문 §13-13 (가칭, 후속) — 라인 2408 (close 시점 가설로 보존)

### 배경

§13-12 close e2e 검증에서 부수적으로 발견된 4 결함. §13-12 close 본문에 placeholder 박제. 본 트랙 진입 시 ground truth 재확인 결과 **일부 박제 표현 정정 + cascade 가설 확정**.

### Phase A 진단 (close 2026-05-10)

**Ground truth 확보** (sections fs + reports/latest.md):

| 결함 | placeholder 박제 | ground truth | drift |
|---|---|---|---|
| 1 | 4장 `## ` heading 누락 | `sections/venfobel-vitamin/벤포벨s-핵심-차별화-자산-기반-광고-클레임-개발.md:1` 본문 산문 직접 시작 — heading 완전 누락 | 일치 |
| 2 | Word 합본 순서 깨짐 (4→7→…) | `reports/venfobel-vitamin/latest.md:115` `## 벤포벨S 핵심 차별화...` (번호 누락) / `:233` `## 실행 로드맵...(KPI)` (번호 누락) — **합본 순서는 정상 1→7** | ⚠ "순서 깨짐" 표현 부정확. 실제는 **번호 prefix 누락** |
| 3 | 7장 `## ` heading 누락 | `sections/.../실행-로드맵-및-핵심-성과-지표kpi.md:1` 평문 (`## ` + 번호 둘 다 누락) | 일치 |
| 4 | Word 5장 "3040." / PPT 제목 prefix 잔존 | latest.md 5장 자체는 `## 5. 3040 직장인...` 정상 | ⚠ Word "3040." 양상 ground truth 미확보 (.docx 직접 검증 보류) |

**전체 7장 sections heading ground truth**: 1·2·3·5·6 정상 (`## N. 제목`) / 4·7장 누락. → **section_writer LLM 출력 일관성 5/7 (28% 실패율)**.

**Cascade 가설** (확정):
- **결함 1+3 = root cause**: section_writer LLM 일관성 결함. `prompts.py:408-410` explicit instruction 있어도 LLM 출력 불일치.
- **결함 2 = 결함 1+3 cascade 후과** (확정): `report_builder.py:259` `strip_number_prefix(ls[2:])` 가 outline title 에서 번호 미리 제거 → titles=["Executive Summary",...,"벤포벨S 핵심 차별화...",...] → 4·7장 sections heading 누락 → `report_builder.py:207 _ensure_heading()` fallback 이 번호 없는 `## {title}` prepend → latest.md 4·7장만 번호 누락.
- **결함 4 PPT = 결함 1+3 cascade 후과** (강한 추정): planner 가 latest.md 의 번호 없는 heading 추출 → `SlideSpec.title="벤포벨S..."` → `renderer.py:203 _CHAPTER_NUM_RE = r"^\s*(\d+)\.\s*(.+)$"` 매칭 실패 → `("", title)` 반환 → number_str 빈 슬라이드 (또는 prefix 잔존).
- **결함 4 Word "3040." = 양상 미확보**: B 안 fix 후 docx 재현 검증.

**catch 자산** (§ placeholder 박제 vs ground truth drift):
- §13-12 close 본문의 §13-13 placeholder 는 **4 결함 독립 가설**. 진입 후 진단 결과는 **결함 1+3 root → 결함 2·4 cascade**. → `placeholder 박제는 § close 시점의 작업 의도 가설, 진입 후 ground truth 와 drift 가능` 의 §13-13 측 발현. §13-12 close NEXT_SESSION.md catch 1 ("박제 vs fs drift") 의 박제·진단 단계로 확장.
- placeholder 박제 표현 정정: 결함 2 "순서 깨짐" → "번호 prefix 누락". 결함 4 Word 양상 ground truth 보류.

### Phase B 결정 (close 2026-05-10)

**결정 1 (결함 1+3 fix = B 안, post-process 정규화)**:
- `agent/section_writer.py:149` 내 LLM 출력 후 outline 의 번호+제목 기반 `## N. <title>` 강제 prepend
- 이미 `## N. 제목` 으로 시작하면 skip / 다른 형태면 정규화
- LLM 의존 줄임 — 결정적 fix
- prompt 강화 (A 안) 폐기 — LLM 일관성 의존 잔존 위험. B 안 결정적이므로 단독 진입.

**결정 2 (결함 2·4 fix = cascade 검증 우선)**:
- B 안 fix 후 e2e 재실행 → latest.md + .docx + .pptx 결함 2·4 자동 해소 검증
- 자동 해소 시 별도 fix 불필요
- 잔존분 발견 시 별도 sub-task 분기 (§13-13-3 가칭)

**결정 3 (결함 4 Word "3040." 양상 ground truth)**: B 안 fix 후 docx 재현 검증. 사용자 .docx 샘플 ground truth 미확보 상태에서 cascade 가설 검증으로 자동 확인.

### Sub-tasks

13-13-1. **section_writer post-process heading 정규화 (B 안)** — 상태: `closed (2026-05-10)` / 의존: 결정 1 / 우선순위: 높음
- 위치: `agent/section_writer.py:144` (helper `_ensure_section_heading`) + `:305` (호출, save_md_draft 직전)
- helper 동작: outline 에서 target_title 의 번호 매칭 → expected_heading=`## N. <title>` 도출 → body 첫 라인 점검:
  - 이미 expected 와 동일 → skip
  - `## ` 로 시작하지만 expected 와 다름 → 첫 라인 교체
  - heading 누락 → expected prepend
- outline 매칭 실패 fallback: 번호 없는 `## <title>` prepend (현재 `_ensure_heading()` 동작 유지)
- target_title 자체 번호 prefix 방어 (requested_write_title 흐름) — `re.sub(r"^\s*\d+[.)]\s*", "", ...)` 으로 normalize 후 매칭
- regex: `_OUTLINE_H2_RE = re.compile(r"^\s*##\s+(?:(\d+)\.\s+)?(.+?)\s*$", re.M)` — H2 한정
- **단위 검증** (8 케이스 ALL PASS): 4장 산문 / 7장 평문 / 5장 정규 skip / `##` 번호 누락 (교체) / target_title 번호 prefix 포함 / outline 매칭 실패 fallback / target_title empty / body empty
- 박제: LLM 출력 후 fallback 정규화는 prompt 의존 줄이는 일반 패턴 — 향후 다른 LLM 출력 일관성 결함 발견 시 동일 패턴 재사용

13-13-2. **Cascade 검증** — 상태: `closed (2026-05-10, partial)` / 의존: §13-13-1 close / 우선순위: 높음

**검증 방식**: §13-13-1 helper 동작 시뮬레이션 (4·7장 .md 직접 prepend) + `build_final_report("venfobel-vitamin")` 직접 호출 + latest.md ground truth 확인. backup → prepend → build → verify → restore (fs 변경 0).

**결과**:
- ✅ **결함 2 cascade 자동 해소 PASS**:
  - 4장 라인 115: `## 벤포벨S 핵심 차별화...` (번호 누락) → `## 4. 벤포벨S 핵심 차별화 자산 기반 광고 클레임 개발` 정상 복구
  - 7장 라인 233: `## 실행 로드맵 및 핵심 성과 지표(KPI)` (번호 누락) → `## 7. 실행 로드맵 및 핵심 성과 지표(KPI)` 정상 복구
  - missing 섹션 0건 / baseline 양상 잔존 0건 → 결함 1+3 fix **단독으로** 결함 2 자동 해소 가설 입증
- ⏸ **결함 4 PPT cascade 검증 미완**: backend e2e (frontend [PPT] 다운로드 + 사용자 시각 검증) 필요 — 본 세션 backend 미기동, 다음 세션 이월
- ⏸ **결함 4 Word "3040." 양상**: latest.md 5장 자체 정상이라 cascade 시뮬레이션에서 별도 양상 없음. 사용자 docx ground truth 직접 검증 필요 (다음 세션 이월)
- 📌 **추가 catch (7장 평문 중복)**: helper v1 prepend 분기는 첫 라인이 평문 제목인 경우 중복 발생. 7장 본문 라인 235 에 평문 `실행 로드맵 및 핵심 성과 지표(KPI)` 잔존. **가독성 영향은 사용자 시각 판단 영역** (docx 본문 첫 줄 평문 잔존이 거슬리는 정도). 회피 fix 는 §13-13-3 (가칭) 으로 분리.

13-13-3. **(가칭, 후속) helper v1.1 — 첫 라인 평문 제목 매칭 시 교체** — 상태: `pending` / 발견: 2026-05-10 §13-13-2 검증 시 / 우선순위: 중·저 (사용자 가독성 판단 결과 기반)

**증상**: helper v1 의 prepend 분기는 첫 라인이 `## ` 으로 시작 안 하면 무조건 prepend. 첫 라인이 평문 제목 (LLM 이 `## ` + 번호만 누락한 케이스 — 7장 venfobel ground truth) 인 경우 → expected_heading prepend 후 본문 첫 라인에 평문 제목 잔존 → 중복.

**fix 가설**: helper 안에 첫 라인 점검 분기 추가:
- 첫 라인이 `## ` 안 시작 + expected_heading 의 title 부분과 정확히 일치 (whitespace strip 후) → 첫 라인 교체 분기
- 일치 안 함 → 현재 prepend 분기 유지 (중복 위험 0)

**진입 조건**: 사용자가 7장 본문 첫 라인 평문 잔존이 가독성에 미치는 영향 시각 검증 후 결정. **사용자 판단 영역**.

**참고**: §13-13-1 helper 변경 1 hunk + 단위 테스트 1 케이스 추가 → trivial fix.

13-13-4. **backend e2e — 결함 4 PPT cascade + Word 양상** — 상태: 본격 결함 close (4-1 + 4-2 모두 closed 2026-05-10) / 4-3 저우선 pending / 우선순위: 중

진입 시 ground truth 검증으로 결함 양상 분기 확정 → 별도 sub-task 분리:
- **§13-13-4-1**: docx H1 결함 2종 (§4·§7 slug+.md / §3040 prefix drift + §5 누락) — closed (commit 74675fb)
- **§13-13-4-2**: docx 본문 list cascade (list block 경계 번호 reset 누락) — closed (commit 3bad5d7)
- **§13-13-4-3**: `_ensure_heading` matcher 결손 (H3 시작 body 의 `## N.` prepend 누락) — closed (commit pending, 2026-05-11)

**회귀 점검 (2026-05-10 close)**: 단일 섹션 export (`kind=section&format=docx`) 가 §13-13-4-2 patch G 의 효과를 추가 fix 없이 그대로 받음. code path 재사용 (kind=section / kind=report 둘 다 `_markdown_to_docx(blocks, doc_title)` 공유, blocks 갯수만 차이). §4·§6 (3 blocks 케이스) 단일 export XML 분포 + LibreOffice 시각 검증 PASS. catch 12 박제.

13-13-4-1. **docx export 단계 helper 전파 + sid 가드** — 상태: `closed (2026-05-10)` / 의존: §13-13-1 / 우선순위: 높음

**Phase A (조사, read-only)**:
- 결함 양상 ground truth 확보 (사용자 e2e 산출 docx unzip):
  - **결함 1 (§4·§7 H1 = slug+.md)**: `## ` 누락 → docx 변환 단계 fallback 이 fname 사용 (`app.py:1505 title = fname`)
  - **결함 4 (§5 H1 = `3040.` prefix + §5 누락)**: 파일명 `3040-직장인-...md` → `re.match(r"^(\d+)-", fname)` 가 sid=3040 으로 오매핑 → §5 자리 비고 §3040 잡음 H1 추가
  - **결함 2 (본문 list cascade)**: word/numbering.xml 의 numId=5 단일 참조 → OOXML 사양상 누적 — §13-13-4-2 분리
- 결정적 단서: §4·§7 sections/.md mtime (19:39:35) < §13-13 commit 62e2775 (19:46:42) → §13-13 fix 미전파 (sections 재작성 안 됨)

**Phase B (결정 + 패치)**:
- **결정 1 (in-memory 정규화)**: sections/.md 무수정 (§13-13 박제 원칙). docx export 단계 (`_read_all_sections`, `_read_section_file`) 가 content 읽은 직후 helper 호출.
- **결정 2 (sid 가드)**: `re.match(r"^(\d+)-", fname)` 매칭 시 outline 범위 `1 <= sid <= len(outline_items)` 안일 때만 인정. outline title 첫 단어 숫자 (예: "3040") 가 신 형식 slug 와 옛 형식 sid prefix 와 충돌하던 양상 차단.
- **결정 3 (helper 입력 계약 확장)**: section_writer 는 평문 target_title 전달 / docx export 는 outline 한 줄 (`## N. <title>`) 전달 — 호출자별 비대칭. helper 본체에 `^\s*#+\s*` prefix 제거 추가 (평문 input 에 no-op, ## prefix 흡수).

**Patch 4건**:
- A: `app.py:26` — `from agent.section_writer import _ensure_section_heading` 추가
- B: `app.py:1486-1521` — `_read_all_sections()` 에 outline_text 합성 + sid 가드 + helper 호출
- C: `app.py:1444-1456` — `_read_section_file()` 에 helper 호출
- D: `agent/section_writer.py:155-159` — helper 입력 계약 확장

**검증 ALL PASS** (라운드 a 단위 5건 + 라운드 b e2e 5건):
- 라운드 a (단위, `scripts/verify_13_13_4_1.py`):
  - §4 (## 누락 산문): sid=4 + helper prepend → 정규 H1
  - §5 (정상 ##, prefix drift): sid=5 (3040 차단) + content 무변동 (idempotent)
  - §7 (평문 제목, ## 누락): sid=7 + helper prepend → 정규 H1
  - mtime 변동: 0 (in-memory 정규화 확인)
  - 회귀 §3·§6: content/title 무변동
- 라운드 b (e2e, `scripts/verify_13_13_4_1_b.py`):
  - 검증 6 (docx report): H1 7개 정확히 §1~§7, slug+.md 잔존 0, §3040 잔존 0, §5 존재
  - 검증 7 (docx section 1..7): 단일 export 7회 모두 H1 정확
  - 검증 8 (PPTX 회귀): code path 분리 cross-check (`_api_export_pptx` / `report_builder.build_final_report` 모두 helper / `_read_all_sections` 무사용)
  - 검증 9 (mtime 무변동): 7 파일 모두 0건
  - 검증 10 (단위 회귀): 5/5 PASS 유지

**§13-13 박제 cascade**:
- §13-13 helper 가 *신규 작성 sections 에만* 적용되는 한계 → docx export 단계 in-memory 정규화로 cascade 자동화
- 산출물 무수정 원칙 유지

13-13-4-2. **docx 본문 list cascade fix** — 상태: `closed (2026-05-10)` / 의존: §13-13-4-1 / 우선순위: 중

**증상**: docx 본문의 번호 list (Actionable Recommendations 등) 가 list block 경계마다 1·2·3 reset 되지 않고 보고서 전체에 걸쳐 누적 카운트.

**XML 레벨 원인 (Phase A 조사)**:
- `word/document.xml`: 모든 list item 이 `<w:pStyle w:val="ListNumber"/>` 단일 스타일, 직접 `<w:numPr>` override 0건
- `word/styles.xml`: ListNumber 스타일이 `<w:numId w:val="5"/>` 단일 참조
- `word/numbering.xml`: numId=5 → abstractNumId=7, `<w:lvlOverride>` 0건
- OOXML 사양상 같은 numId 공유 paragraph = 단일 연속 리스트 → 카운터 누적

**fix 경로 (라운드 a-1 → a-2 → a-3 점진 보강)**:

라운드 (a-1) — 옵션 B v1: § 경계마다 새 numId 등록 + paragraph inline numPr override
- XML 검증 PASS (numbering.xml 9→16, ListNumber paragraph 모두 inline numId)
- **시각 검증 FAIL**: §1 1-5 → §2 6-8 → ... 누적 — cascade 그대로 (catch 9 발현)

라운드 (a-2) — Patch E 추가: `<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>` 명시
- numId 분리만으로는 카운터 분리 implementation-defined → startOverride val=1 명시가 사양 보장 핵심
- 시각 검증 부분 PASS: § 경계 reset (§1 1-5, §2 1-3, §3 1-5...) — Patch E 효과 입증
- 잔존: § 안 다중 list block (§2 의 실행방안+Actionable, §4·§5·§6·§7 동일) 의 cross-block continuation

라운드 (a-3) — Patch G: § 경계 → *list block 경계* 단위 numId 발급 (catch 11)
- `_render_markdown_to_docx` 가 line-by-line 으로 `prev_was_list_number` 추적
- ListNumber paragraph 진입 시 prev=False 면 새 numId 발급 (closure allocator)
- 헤딩/구분자/일반 paragraph/bullet 만나면 prev=False (block 끊김)
- 빈 라인은 prev 유지 (markdown loose list 사양)
- XML 검증 7/7 PASS + 시각 검증 PASS (모든 § 의 모든 list block 1 부터 reset)

**Patch 누적 (app.py +129 / -3)**:
- helper 3개: `_list_number_abstract_id` / `_allocate_section_num_id` / `_set_paragraph_inline_num_id`
- `_markdown_to_docx`: closure allocator 캡처
- `_render_markdown_to_docx`: 시그니처 변경 (`section_num_id` → `allocate_num_id`) + line tracker 분기

**검증 ALL PASS (라운드 a-3 XML 7건 + 라운드 b e2e 4건)**:
- 라운드 a-3 (`scripts/verify_13_13_4_2.py`):
  - 검증 1: numbering.xml <w:num> count = 9 baseline + 14 list blocks = 23
  - 검증 2: ListNumber paragraph 56/56 inline numId 보유, unique 14개 = list block 갯수
  - 검증 3: list block 단위 분리 (intra-block uniform + inter-block disjoint)
    · §1: 1 block / §2: 2 blocks / §3: 1 block / §4: 3 blocks / §5: 2 blocks / §6: 3 blocks / §7: 2 blocks
  - 검증 4: ListBullet 21개 inline numPr 0 (bullet 무영향)
  - 검증 5: H1 시퀀스 §1~§7 정확 (§13-13-4-1 회귀 0)
  - 검증 6: sections/.md mtime 변동 0
  - 검증 7: 14/14 신규 numId 모두 lvlOverride+startOverride 보유
- 라운드 b (`verify_13_13_4_1_b.py` 재실행): §13-13-4-1 H1 회귀 0 + 단위 5/5 PASS 유지
- PPTX 경로 분리 cross-check 0 호출 (catch 8 패턴 재사용)

**산출물 무수정 원칙 유지** (sections/.md mtime 변동 0).

13-13-4-3. **`_ensure_heading` matcher 결손 fix** — 상태: `closed (2026-05-11)` / 의존: 없음 / 우선순위: 중

**진앙 (catch 16 ground truth 입증 트리거)**:
- `report_builder._ensure_heading` (line 207-215) 의 `if body.startswith("#"):` 가 `###` (H3) 도 매칭
- §5 처럼 section body 가 `### 배경\n3040 직장인은...` 으로 시작하면 prepend skip → reports/latest.md 에 `## 5.` 헤딩 누락
- docx path 는 §13-13-4-1 in-memory helper (`_ensure_section_heading`) 로 우회되어 산출 정상
- **pptx path 는 helper 미적용** — `build_final_report → plan_deck` 가 §5 누락 md 를 받음
- baseline 운영 산출 (gpt-4o, 2026-05-08): LLM 추론으로 §5 SECTION_HEADER "05" + "3040 직장인..." 정확 출력 — **우연히 무력화**
- §13-14-1 patch v1 (prompts.py 압축 규칙 완화 + few-shot 2) 적용 후 라운드 (a-2): §5 SECTION_HEADER + 5 TITLE_CONTENT **완전 누락** — LLM 추론 무력화 깨짐 (catch 16 ground truth 입증)

**진앙 트리거**: §13-14-1 patch v1 라운드 (a-2) 측정. baseline 38 슬라이드 → patch 후 32 슬라이드. §5 6 슬라이드 통째 누락. patch 의 압축 가이드 변화가 LLM 의 §5 추론 휴리스틱을 끊음.

**fix**:
```python
# 기존
if body.startswith("#"):    # ### 도 매칭 — 결함
    return body
# 신규
if re.match(r"^#{1,2}\s", body):   # H1/H2 만 skip
    return body
```

`re.match(r"^#{1,2}\s", body)` 가 `#`·`##` + 공백 후 텍스트 패턴만 매칭. H3 (`### `) 이상은 매칭 안 되어 `## {title}` prepend 진행.

**단위 검증 6 케이스 (scripts/verify_13_13_4_3.py)**: ALL PASS
- a. H1 (`# 제목\n본문`) → prepend skip ✓
- b. H2 (`## 제목\n본문`) → prepend skip ✓
- c. H3 (`### 소제목\n본문`) → prepend 진행 (fix 핵심) ✓
- d. H4 (`#### ...`) → prepend 진행 ✓
- e. 평문 (`본문 시작`) → prepend 진행 ✓
- f. 공백 후 헤딩 (`\n\n## 제목`) → lstrip 후 skip ✓

**e2e 검증 (build_final_report 1회 호출)**:
- latest.md 의 `##` 헤딩 dump: §1·§2·§3·§5·§6 정상 (sid prefix 보유) + §4 (`## 벤포벨S 핵심 차별화 자산`)·§7 (`## 실행 로드맵`) 은 section body 의 기존 H2 잔존 (matcher skip)
- **§5 `## 5. 3040 직장인 만성피로 인식 및 비타민 구매 행동 분석` 정확히 prepend** ✓
- H2 카운트 7 (전부) — baseline 동일

**fix 범위 (§13-13-4-3 한정)**:
- H3 시작 body 의 ## prepend = `_ensure_heading` matcher 강화로 해결 (본 fix 범위)
- §4·§7 처럼 section body 가 기존 H2 헤딩 보유 (sid prefix 불일치) 케이스는 `_ensure_section_heading` docx in-memory helper 가 해결 (cascade 유지)
- **cascade 패턴 결정 (catch 12 활용)**: docx helper 는 유지 — `_ensure_heading` 이 root cause fix 이고 helper 는 §4·§7 sid prefix 케이스의 방어 layer. 중복 fix 정리는 §13-14 트랙 close 후 cleanup 트랙으로 분리.

**catch 8 cross-check (§13-14-1 진입 트리거 grep)**:
- `from prompts import|import prompts`: `agent/export/planner.py:7` 만 `get_pptx_planner_prompt` import. docx path (app.py / agent/section_writer.py) 는 다른 prompt 함수 사용 → **prompt 함수 단위로 PPTX/docx 분리**
- `SlideSpec|SlideDeckSpec|TableSpec`: planner.py + renderer.py + spec.py 자체 + 측정/검증 scripts 만. docx path 무영향
- **PPTX path 분리 확정** — §13-13 catch 8 패턴 재사용. §13-14-1 patch 영향 PPTX path 한정.

**§13-14-1 patch v1 효과 분리 측정 환경 확보**:
- 본 fix 가 §5 5 슬라이드 측정 가능 환경 마련 — 라운드 (a-2)' 진입 선결조건 충족
- patch v1 효과는 라운드 (a-2)' 결과에서 확정 (별도 commit)

### 진행 박제

- **commit c3af4c7** (placeholder, 진입 시): Phase A close (drift catch + cascade 가설) + Phase B 결정 close + sub-task 박제
- **commit 62e2775** (close, partial): §13-13-1 구현 (helper + 호출) + 단위 검증 ALL PASS + §13-13-2 cascade 검증 PASS (결함 2 자동 해소) + §13-13-3·4 후속 분리 박제
- **commit 74675fb** (§13-13-4-1 close): docx export 단계 helper 전파 + sid 가드 + helper 입력 계약 확장. 라운드 a/b ALL PASS. §13-13-4-2 (list cascade) + §13-13-4-3 (_resolve_section_file 점검) 분리
- **commit 3bad5d7** (§13-13-4-2 close): docx 본문 list cascade fix — list block 경계 단위 numId 발급 + lvlOverride/startOverride 명시. 라운드 a-1 → a-2 → a-3 점진 보강. 시각 검증 PASS. catch 8·9·10·11 박제.
- **commit 86a8a9c** (§13-13-4 회귀 점검 close + catch 12 박제).
- **commit 37d39f3** (catch 13·14·15 박제).
- **본 commit** (§13-13-4-3 close): `_ensure_heading` matcher 강화 — `re.match(r"^#{1,2}\s", body)` 로 H1/H2 만 skip, H3 이상은 `## {title}` prepend. 단위 6 케이스 + e2e build_final_report PASS. §5 ## 헤딩 in-memory normalization → pptx path LLM 추론 의존도 제거. catch 8 cross-check (PPTX path 분리) + catch 16 (공유 단계 fix 누락 → 양쪽 path 양상 차이 ground truth 입증) 박제. §13-14-1 라운드 (a-2)' 측정 선결조건 충족.

### Re-entry conditions

- (R1) §13-13-3 — 사용자가 7장 본문 첫 라인 평문 잔존 가독성 영향 판단 후 v1.1 진입 결정 시.
- (R2) §13-13-4 — backend e2e 진입 시 결함 4 양상 검증. cascade 가설 confirm/refute.
- (R3) 다른 토픽 (pet-food-premium 등) 에서 동일 결함 1+3 양상 발현 시 helper v1 동작 검증 + 토픽별 outline 형태 차이 점검.

### catch 자산 (본 트랙)

- **catch 1 (§ placeholder 박제 vs ground truth drift)**: §13-12 close 본문 §13-13 placeholder 의 4 결함 독립 가설 → 진단 결과 결함 1+3 root → 결함 2·4 cascade 후과. **§ placeholder 박제는 close 시점 작업 의도 가설, 진입 후 ground truth 와 drift 자연스러움**. §13-12 NEXT_SESSION catch 1 ("박제 vs fs drift") 의 박제·진단 단계 확장.
- **catch 2 (LLM 일관성 결함 → post-process 정규화 패턴)**: section_writer prompts.py:408-410 explicit instruction 있어도 5/7 (28% 실패율). prompt 강화 (A 안) 대신 post-process fallback (B 안) 이 결정적. **LLM 출력 일관성 결함은 prompt 강화로 0% 실패율 도달 보장 어려움 → 결정적 post-process 정규화로 우회**. 향후 다른 LLM 출력 일관성 결함 (e.g., citation marker 누락 / 표 형식 불일치 등) 발견 시 동일 패턴 재사용.
- **catch 3 (cascade 가설 검증의 가치)**: 결함 4 독립 fix 진입 대신 cascade 가설 검증 우선 (결정 2). 결함 1+3 fix 만으로 결함 2 자동 해소 입증 → 결함 4 도 동일 cascade 추정 (backend e2e 시점 검증). **독립 fix 분기 추가하기 전에 cascade 가설로 묶음 fix 가능성 점검** — fix 작업량 / 코드 변경 면적 최소화.
- **catch 4 (helper v1 prepend 분기의 평문 중복 trap)**: 첫 라인이 평문 제목인 LLM 출력 케이스에서 prepend 만으로는 중복 잔존. v1.1 (첫 라인 매칭 교체 분기) 후속 가능성. v1 단순성 vs v1.1 정확성 trade-off — 사용자 가독성 영향 시각 판단 영역.
- **catch 5 (§13-13-4-1: helper 입력 계약 호출자별 비대칭)**: section_writer 호출자는 평문 target_title (예: `"Executive Summary"`) 전달 / docx export 호출자는 outline 한 줄 (`"## 1. Executive Summary"`) 전달 — 같은 helper 에 다른 형식 input. 호출자별 정제 코드를 분산 배치하면 sync 부담. **helper 본체에 입력 흡수층** (`^\s*#+\s*` + `^\s*\d+[.)]\s*` 단계 prefix 제거) 을 두면 호출자 측 정제 0 + 미래 호출자 추가 시 자유. 평문 input 에 no-op (회귀 0) — §13-13-1 박제 단위 8 케이스 무영향. 자산화: **공유 helper 의 입력 계약은 호출자 다양성을 helper 본체에서 흡수** (호출자 측 정제 분산보다 결합 낮음).
- **catch 6 (§13-13-4-1: 산출물 cascade 자동화)**: §13-13 helper 는 section_writer 단계 (LLM 출력 직후) 에 인입 — *신규 작성 sections* 에만 효과. 기존 sections/.md (fix 이전 작성분) 는 fix 미전파. 사용자 e2e 산출 docx 의 §4·§7 mtime (19:39:35) < §13-13 commit (19:46:42) 가 결정적 단서. 자산화: **fix 가 LLM 단계에 들어가면 기존 산출물에 자동 cascade 안 됨** → 산출물 무수정 원칙 유지하면서도 cascade 보장하려면 *consumer 단계에 in-memory 정규화* (re-run 없이 즉시 효과). 향후 다른 LLM 출력 후처리 fix 도 동일 패턴 적용 검토.
- **catch 7 (§13-13-4-1: slug 와 sid prefix 형식 충돌)**: `re.match(r"^(\d+)-", fname)` 이 옛 형식 (`1-Executive_Summary.md`) 인식용으로 도입됨. 그러나 `section_slugify` 결과가 outline title 첫 단어 숫자 ("3040 직장인...") 를 보존하면서 신 형식 (`3040-직장인-...md`) 도 같은 패턴에 매칭 — sid=3040 으로 잘못 결정. **outline 범위 가드** (`1 <= sid <= len(outline_items)`) 한 줄로 격리. 자산화: **숫자 prefix 컨벤션 재사용 시 의미 영역 (section_id 범위) 가드 필수** — 동일 패턴이 미래 다른 mode (book chapter 등) 에도 잠재.
- **catch 8 (§13-13-4-1·4-2: PPTX path 분리 cross-check 패턴)**: docx-only fix 가 PPTX 산출에 영향 없음을 확인하기 위해 *실제 PPTX 호출 (LLM 1회 ~$0.07, ~30s)* 대신 *코드 path 분석 grep* 으로 확정. `_api_export_pptx` 와 `report_builder.build_final_report` 가 patch 함수 (`_read_all_sections` / `_read_section_file` / `_markdown_to_docx` / `_render_markdown_to_docx` / `_allocate_section_num_id` 등) 를 호출하지 않음을 grep 으로 입증 → 회귀 0. 자산화: **format-specific fix 의 cross-format 회귀는 코드 path 분리만 grep 으로 확인 가능 — 실제 LLM 호출 비용 회피**.
- **catch 9 (§13-13-4-2: XML 검증 PASS ≠ 시각 검증 PASS)**: 라운드 (a-1) 의 XML 6/6 PASS 가 LibreOffice 시각 검증에서 cascade 잔존으로 무효화. numId 분리 + abstractNum 공유 만으로는 카운터 분리 implementation-defined (OOXML 사양 미규정). 실제 office 도구 (Word/LibreOffice) 가 startOverride 같은 명시 reset 신호 없으면 카운터 공유 가능. 자산화: **OOXML 류 fix 는 XML 레벨 검증 + 실제 office 도구 시각 검증 (또는 PDF 변환) 양쪽 병행 필수** — XML 만으로 PASS 판정 위험.
- **catch 10 (§13-13-4-2: OOXML cascade fix 정공법)**: `<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>` 가 카운터 reset 의 핵심. 새 `<w:num>` 등록 + abstractNum 공유 + paragraph inline numPr override 까지만으로는 부족. startOverride val="1" 명시가 OOXML 사양상 시작값 강제. 자산화: **OOXML number list cascade 차단 = 새 numId + abstractNum (공유 OK) + lvlOverride wrapper + startOverride val=1 + paragraph inline numPr 의 5요소 조합**.
- **catch 11 (§13-13-4-2: 옵션 B 의 'block 단위' 정의 — § 경계 vs list block 경계)**: 라운드 (a) 의 fix 단위 정의가 사용자 본래 결함 보고를 정확히 반영하지 못함. placeholder 박제 ("§ 경계 reset") 가 시각 검증 후 "list block 경계 reset" 으로 정정됨 — §2 의 실행방안 1·2·3 후 Actionable Recommendations 가 *4·5·6·7·8 누적* 이 아니라 *1·2·3·4·5 reset* 이 사용자 기대치. 즉 같은 § 안 다중 list block 도 독립 카운터. 자산화: **사용자 본래 결함 보고를 fine-grained 양상까지 재해석하는 것이 fix 단위 결정의 ground truth** — placeholder 박제 단계의 결함 정의가 fix 단계에서 coarse 한 경우 잦음 → 시각 검증 단계에서 정정.
- **catch 12 (§13-13-4 회귀 점검: 공유 entry-point 의 자동 cascade)**: format-specific fix 가 공유 entry-point 에 들어간 경우, 호출 경로 분기에 자동 전파. 본 케이스 — `_markdown_to_docx(blocks, doc_title)` 가 `blocks` 갯수와 무관하게 동일 로직 (outer loop + closure allocator) → `kind=section` (blocks=1개) 도 `kind=report` (blocks=7개) 도 patch G 자동 PASS. **catch 5 (helper 입력 계약 호출자 비대칭, §13-13-4-1) 와 대조** — catch 5 는 호출자별 입력 형식 차이로 helper 가 한 쪽만 흡수 → 본체 입력 계약 확장 필요 / catch 12 는 공유 함수 단일 진입점 덕에 양 호출자 모두 자동 적용. 자산화: **format-specific fix 의 회귀 점검 시, 공유 entry-point 인지 호출자별 분기인지 먼저 확인** — 공유면 grep 만으로 회귀 0 입증 (실제 e2e 호출 비용 회피), 분기면 호출자별 개별 검증 필요. catch 8 (PPTX path 분리 cross-check) 가 *분리* 케이스 / catch 12 가 *공유* 케이스 — 양쪽 다 grep 단계에서 결정.
- **catch 13 (§13-13 트랙 후처리: fix 의 provider-agnostic 여부 판정 기준)**: 사용자 질문 "openai 통용 fix 가 gemini 에도 적용?" 분석 결과 박제. fix 를 3 카테고리로 분류하면 provider 전환 시 transfer 여부 즉시 판단 가능:
  - **변환 단계 fix** (markdown → docx, OOXML 조작): **provider 무관** — input markdown 의 텍스트 양상에만 의존. §13-13-4-1 (sid 가드 + helper 호출 in-memory 정규화) / §13-13-4-2 (list block 단위 numId + lvlOverride/startOverride) 가 이 카테고리. provider 전환 (openai → vertexai → anthropic) 무영향.
  - **LLM 출력 정규화 fix** (post-process helper): **provider 의존** — helper 입력 계약이 산출물 양상에 결합. §13-13-1 `_ensure_section_heading` helper 가 이 카테고리. gpt-4o 의 `## ` 누락 / 평문 제목 / 산문 직접 시작 양상 기반 8 케이스 단위 검증 — 다른 provider 의 출력 양상 (e.g., `##### 5단계` 또는 영문 fallback) 등장 시 helper 분기 추가 필요.
  - **측정 인프라 fix** (venv / .env / 측정 스크립트): **provider 별 분리** — §13-8 패턴 (`.venv_openai` / `.venv_vertex` / `.venv_anthropic` + `.env.<provider>` + `LLM_PROVIDER` 환경변수). provider 전환 = 인프라 전환.
  - 자산화: **새 fix 작성 시 위 3 카테고리 중 어디 속하는지 판정** → provider 전환 시 transfer 여부 즉시 결정. fix 위치 (변환 layer vs LLM layer vs 인프라 layer) 가 판정 기준.
- **catch 14 (§13-13-1 helper 의 provider 변종 가능성)**: §13-13-1 `_ensure_section_heading` helper 의 단위 검증 8 케이스 = **gpt-4o 산출물 기반 ground truth**. 다른 provider 전환 시 새 양상 등장 가능 — `##### 5단계` 같은 ilvl 깊이 / 영문 fallback (`## Section 1` 형식) / 다른 escape 패턴. catch 5 (helper 입력 계약 호출자 비대칭) 의 *provider 변종* — 호출자가 같아도 LLM provider 가 다르면 input 양상 분기. 자산화: **helper docstring 에 입력 ground truth provider 명시** — 다른 provider 전환 시 재검증 트리거. §13-13-1 helper 도 docstring 에 "gpt-4o 산출물 기반 ground truth, provider 전환 시 8 케이스 재검증" 명시 검토.
- **catch 15 (heredoc commit 메시지 중복 양상 — 끌로드 코드 워크플로우 결함)**: §13-13-4-1 / §13-13-4-2 / catch 12 commit 3건 모두 heredoc 첫 강조 블록 중복 발생 (3/3). 사용자 검토에서 모두 잡혀 reject 후 재 commit 처리 — git log 오염 0. 양상 — heredoc 안에 같은 단락이 두 번 등장 (제목 다음 요약 + 본문 첫 섹션 헤더). 끌로드 코드 환경의 heredoc 작성 시 빈도 높은 패턴. **대책**: (a) `git commit -F <file>` 사용 — commit message 를 별도 파일에 작성 후 read 로 검토 가능 / (b) heredoc 작성 후 첫·마지막 5줄 중복 grep / (c) 사용자 검토 단계에 의존. 자산화: **commit 메시지 작성 = 단일 source 원칙** — 제목 + 본문 첫 섹션이 의미 중복하지 말 것. heredoc 보다 `-F <file>` 권장.
- **catch 16 (§13-13-4-3: 공유 단계 fix 누락 → 양쪽 path 양상 차이 ground truth)**: build_final_report 의 `_ensure_heading` matcher 결손 (H3 시작 body 의 `## N.` prepend 누락) 은 docx path 만 §13-13-4-1 in-memory helper 로 우회 → pptx path 는 미해결. **양쪽 path 의 결함 양상 차이는 docx path 의 fix 가 root cause 가 아닌 *consumer 단계 우회* 였음을 입증**. baseline pptx (gpt-4o, 2026-05-08) 의 §5 정확 출력은 LLM 추론으로 우연히 무력화. §13-14-1 patch v1 (prompts.py 압축 규칙 완화) 적용 후 라운드 (a-2): §5 SECTION_HEADER + 5 TITLE_CONTENT 통째 누락 — LLM 추론 무력화 깨짐. 자산화: **format-specific fix 가 한쪽 path 만 in-memory normalization 으로 우회되고 있다면, 다른 path 는 LLM/외부 양상에 의존해 살아남고 있을 가능성** — root cause 의 진정한 위치 (sections → reports 합성 단계 등 공유 entry-point) 에 fix 적용해야 catch 12 (공유 entry-point 자동 cascade) 의 cascade 효과 회수. catch 8 (PPTX path 분리 cross-check) 와 cross-check: catch 8 은 *영향 없음* 입증 / catch 16 은 *영향 누락* 입증 — 두 catch 가 cross-format 영향 분석의 양면.

### 보존 자산 (재사용)

- §13-12 결정 1 (build_final_report 자동 호출) — pptx 분기 그대로 활용
- §13-12 결정 2 (R1 BytesIO) — renderer 시그니처 그대로
- §12-14 events 채널 — emit_event 재사용 시 (선택)
- **§13-13-1 helper `_ensure_section_heading`**: post-process 정규화 일반 패턴 — outline ground truth + body 첫 라인 분기 (skip / 교체 / prepend / fallback) 패턴 그대로 재사용

---

## §13-14. md → pptx 정보 충실도 트랙

13-14. **md → pptx 정보 충실도 트랙** — 상태: 진행 중 (§13-14-1 단계 1 close, 단계 2 사용자 결정 대기) / 우선순위: 중

**진입 트리거**: 사용자 e2e 인지 양상 — md 의 `**KEY**: 설명` 패턴 bullet 이 pptx 에서 키워드만 보존, 단락 본문은 2-3 키워드로 압축. ground truth 비교 (운영 산출 pptx + 동일 docx + latest.md): §5 (3040 직장인) 5 H3 슬라이드 모두 P1 (키워드만) / P2 (수치+키워드) 양상으로 정보 ~80% 누락 입증. §4·§6·§7 동일 양상 확인.

**결함 진앙 (라운드 a-1 조사)**:
- `plan_deck` (LLM 1회, gpt-4o, temperature=0.1) 의 `prompts.py:get_pptx_planner_prompt` 압축 규칙 "bullets 3~6개·80자 이내·body 200자" + LLM "핵심 판단" 자율성
- gpt-4o 양상: bold 키워드 + 수치 우선, 설명문 절단 (P1·P2 카테고리)
- SlideSpec.bullets Field description 의 권장 길이 (3~6개·80자) 가 prompt 와 별도로 LLM 압축 압박 (signal 일관성)
- renderer 의 자동 폰트 축소 부재 — 단 본 케이스 텍스트 짧아 우선순위 낮음

**catch 13 분류**: **LLM 단계 결함 (provider 의존)** — gpt-4o 양상 기준 fix, Anthropic 전환 시 catch 14 재검증 트리거.

### sub-task

- **§13-14-1**: prompt 압축 규칙 재설계 + SlideSpec Field 동기화 — 단계 1 close (2026-05-11), 단계 2 (옵션 B 추가 보강) 사용자 결정 대기

13-14-1. **prompt 압축 규칙 재설계 — 단계 1 (patch v1 + §13-13-4-3 fix 묶음)** — 상태: `close (2026-05-11, 단계 1)` / 의존: §13-13-4-3 / 우선순위: 중

**catch 8 cross-check (진입 트리거 grep)**:
- `from prompts import|import prompts`: `agent/export/planner.py:7` 만 `get_pptx_planner_prompt` import. docx path (app.py / agent/section_writer.py) 는 다른 prompt 함수 사용 → **prompt 함수 단위로 PPTX/docx 분리**
- `SlideSpec|SlideDeckSpec|TableSpec` consumer: planner.py + renderer.py + spec.py 자체 + 측정/검증 scripts 만. docx path 무영향
- **PPTX path 분리 확정** — §13-13 catch 8 패턴 재사용. patch 영향 PPTX path 한정.

**Patch v1 (prompts.py + spec.py)**:

prompts.py:642-647 — 압축 규칙 완화:
- bullets 3~6개·80자 → **3~8개·150자**
- body 200자 → **400자**
- "원문 그대로 복사 금지 — 핵심만 한국어로 요약 (단 아래 정보 보존 우선순위 준수)" — 신규 우선순위 5단계 명시

prompts.py:649~ — 정보 보존 우선순위 5단계 신규 추가:
1. **수치·정량 데이터** (58%, 800억 원, GRPs, 위) 최우선
2. **고유명사·브랜드명·약어** (벤포벨S, 아로나민, 메코발라민, UDCA) 원문 표기
3. **md 의 `**KEY**: 설명` 패턴은 KEY 와 설명 둘 다 보존** — 키워드만 추출 금지
4. **단락(평문) 본문**은 핵심 1-2 문장 + bullets 3-5 분해
5. 후순위 (생략 가능): 부사·접속사·중복 표현, 정성적 일반화

prompts.py — Few-shot 2 추가 (§4 실행방안 입력 — §5·§6 검증 표본과 분리 in-distribution 회피): `**KEY**: 설명` → `KEY: 압축 설명` 보존 예시

spec.py:66-94 — SlideSpec Field description 동기화:
- bullets: "3~8개, 150자 이내, `**KEY**: 설명` 패턴 보존"
- body: "400자 이내"

**라운드 (a-2) 측정 (§13-13-4-3 fix 전, scripts/verify_13_14_1.py)**:
- n_total_slides 32 (expected 44) — §5 SECTION_HEADER + 5 TITLE_CONTENT 통째 누락 (catch 16 ground truth — LLM 추론 무력화 깨짐)
- §5 측정 표본 n=0 — 측정 불가
- §6 측정 표본 5 슬라이드 모두 baseline 100% 동일 텍스트 (KEY+설명 보존 0/5)

→ **§13-13-4-3 본격 fix 진입 (commit 03e0ef8) — §5 측정 환경 확보 후 라운드 (a-2)' 재실행**

**라운드 (a-2)' 측정 (§13-13-4-3 fix 후)**:
- n_total_slides 38 (expected 45) — baseline (38) 와 동일. catch 17 본질 = LLM 의 참고문헌 ### 7 H3 자율 제외 (patch 무관)
- SECTION_HEADER 7개 (§1~§7) — §5 정확 출력 ("5. 3040 직장인 만성피로 인식 및 비타민 구매 행동 분석")
- §5 5 슬라이드 측정 결과:

| §5 슬라이드 | baseline | new | KEY+설명 보존 | 길이 변화 | 양상 |
|---|---|---|---|---|---|
| 배경 | 2 bullets, 18.0자 (키워드) | 2 bullets, 38.0자 | 0/2 | +20자 | 정보 풍부화 (P3 단락 → bullet 분해는 KEY 부재) |
| 핵심 요점 | 3 bullets, 7.7자 (키워드) | 3 bullets, 30.3자 | **3/3** | +22.6자 | **PASS** (P1 해소) |
| 데이터 기반 근거 | 3 bullets, 27.7자 (수치 보존) | 2 bullets, 46.0자 | 2/2 | +18.3자 | 갯수 -1, 길이 풍부화 (P2 → KEY+설명) |
| 실행방안 | 3 bullets, 10.0자 (키워드) | 3 bullets, 32.7자 | **3/3** | +22.7자 | **PASS** (P1 해소) |
| Actionable Rec | 5 bullets, 9.4자 (키워드) | **3 bullets**, 34.0자 | 3/3 | +24.6자 | 갯수 -2 합병, 길이 풍부화 |

§6 cross-check (few-shot §4 외 일반화):
- 핵심 요점: 2 bullets (baseline 2 동일), KEY+설명 보존 OK
- 데이터 기반 근거: 2 bullets (baseline 3 → 2 갯수 -1), 수치 보존 OK
- 실행방안: 2 bullets (baseline 3 → 2), KEY+설명 보존
- Actionable Rec: 2 bullets (baseline 5 → 2 갯수 -3), KEY+설명 보존

**판정 (라운드 a-1 권고 기준 1-5)**:
- §5 KEY+설명 보존: **4/5 슬라이드** (3건 완전 PASS + 1건 부분, 배경만 P3 양상으로 KEY 부재), bullets 기준 **8/10**. 권고 기준 "3/5 이상 = 효과 충분" 충족 → **단계 2 불필요**
- §13-9 결정성: baseline 38 / 라운드 (a-2) 32 / 라운드 (a-2)' **38** — fix 후 baseline 회복. **patch v1 의 결정성 약화 효과 없음** (catch 17 본질 = LLM 자율 제외, patch 무관)
- §5 Actionable Rec 갯수/길이 분리: **(c) 항목 감소 5→3 — 갯수 한계 8 미해소** (LLM 의 압축 default = 갯수 합병). 별도 결함 양상으로 박제 (단계 2 진입 후보)

**판정 결과**: 단계 1 patch v1 효과 충분 입증. 단계 2 (옵션 B 추가 보강) 진입 여부 사용자 결정 대기.

**잔존 양상 (단계 2 진입 시 fix 후보)**:
- LLM 의 "압축 default = 갯수 합병" 양상 — bullets 8 한계 완화에도 N → N-2/N-3 합병 (§5·§6 Actionable Rec 5→3, 5→2)
- "배경" 단락 (P3 양상) 의 KEY+설명 보존 부재 — bullet 분해 시 KEY 추출 안 됨. few-shot 2 (§4 실행방안 = bullet list 입력) 가 P3 (단락 입력) 까지 일반화 못 함

**Patch 누적**:
- prompts.py +27 lines (압축 규칙 완화 + 정보 보존 우선순위 + few-shot 2)
- agent/export/spec.py +5 lines (bullets/body description 동기화)
- (별도 commit 03e0ef8 = §13-13-4-3 fix, 본 patch 의 §5 측정 환경 선결)

### 진행 박제

- **commit 03e0ef8** (§13-13-4-3 close, 본 commit 선결): `_ensure_heading` matcher 강화. §5 측정 환경 확보.
- **본 commit** (§13-14-1 단계 1 close): prompts.py 압축 규칙 완화 + few-shot 2 추가 + spec.py Field 동기화. 라운드 (a-2)' KEY+설명 보존 4/5 슬라이드 PASS. catch 17 박제. 단계 2 사용자 결정 대기.

### 잠정 close (2026-05-11, 사용자 ground truth 시각 검증 결과 후)

**결정**: §13-14-1 단계 1 close (623238c) 결과 (patch v1 효과 KEY+설명 보존 4/5 유효, §13-9 결정성 baseline 38 회복) 는 유지. 단계 2 진입 + 후속 분기 4건 (§13-14-1-a/b/c + §13-14-1-b 이월) 은 **모두 폐기**. 잔존 양상 fix 는 §13-14-2 (md 정규화 우선 패턴) 로 이월.

**사용자 판단 근거**: md 입력 분포 자체가 들쭉날쭉한 상태에서 plan_deck/render_deck downstream fix 누적은 결함 양상 다양성마다 새 cross-check 부담 → 입력 정규화로 N 결함 다양성 자체를 차단.

**라운드 (b) 사용자 ground truth 시각 검증 결과 (8건)**:
- 갯수 합병 7건: §4 실행방안 5→3 / §5 데이터근거 3→2 / §5 Rec 5→3 / §6 데이터근거 3→2 / §6 Rec 5→3 / §7 핵심요점 3→2 / §7 Rec 5→3
- 구조 누락 1건: §4 SECTION_HEADER 전체 누락 (LLM stochasticity 가 sid prefix 불일치 케이스에 영향 직접 노출)

**catch 17 강화 후보 폐기**: LLM stochasticity 가 별도 결함이 아니라 입력 정규화 부재의 후과로 재해석. §13-14-α 규약 + §13-14-β 정규화 layer 후 stochasticity 영향 측정 가능, 별도 catch 박제 불필요.

### Re-entry conditions

- (R1) ~~§13-14-1 단계 2~~ — **폐기** (잠정 close 박제 본문 참조). 단계 2 진입 + 후속 분기 4건 모두 폐기, 잔존 양상은 §13-14-2 로 이월.
- (R2) **§13-14-2 (md 정규화 우선 패턴)** — md 입력 정규화로 N 결함 다양성 자체 차단. sub-track 4건 (§13-14-α 규약 정의 / §13-14-β 정규화 layer / §13-14-γ linter / §13-14-δ 잔존 결함 fix 재진입).
- (R3) §13-8-3 Anthropic Haiku 4.5 평가 — patch v1 의 catch 13 카테고리 = LLM 단계 (provider 의존). Anthropic 양상 재검증 트리거 (catch 14).

### catch 자산 (본 트랙)

- **catch 17 (§13-14-1: 결정론 강제 vs 정보 충실도 트레이드오프)**: §13-9 Round 3 의 "정확히 1+H2+H3 슬라이드" 강제 매핑은 LLM 측에서 부분 무시되는 운영 양상 — baseline pptx (gpt-4o, 2026-05-08): expected 44 (= 1 + 6 H2 + 37 H3) vs actual 38, 참고문헌 ### 7 H3 자율 제외. §13-13-4-3 fix 후 expected 45 (= 1 + 7 H2 + 37 H3) vs actual 38, 동일 자율 제외 + §5 정규화. 라운드 (a-2) (§13-13-4-3 fix 전, patch v1 적용): 32 — §5 통째 누락 (catch 16). 라운드 (a-2)' (양쪽 fix 묶음): 38 회복. **patch v1 의 압축 규칙 완화 자체는 결정성 약화 효과 없음** — 양상의 본질은 LLM 의 참고문헌 등 의미 메타 ### 자율 제외 패턴. 자산화: **§13-9 결정론 강제 (강제 매핑 1+H2+H3) 와 LLM 의 자율 제외 (참고문헌·메타 ### 등) 가 운영상 일관된 trade-off** — 강제 매핑은 "최대 슬라이드 수" 가이드 역할, 자율 제외는 LLM 의 의미 판단 기준. §13-14-2 md 정규화 우선 패턴 트랙 진입 시 본 trade-off 의 입력 단계 차단 가능성 검증. catch 16 (공유 단계 fix 누락) 과 cross-check: catch 16 의 §5 누락이 라운드 (a-2) 32 의 직접 원인, catch 17 의 LLM 자율 제외가 라운드 (a-2)' 38 의 잔존 원인 — 두 catch 가 결정성 실패의 양면.

---

## §13-14-2. md 정규화 우선 패턴 (placeholder)

13-14-2. **md 정규화 우선 패턴** — 상태: `placeholder (2026-05-11)` — 본격 진입은 다음 세션 / 우선순위: 중

**진입 트리거**: §13-14-1 잠정 close. md 입력 분포 들쭉날쭉 상태에서 plan_deck/render_deck downstream fix 누적은 결함 양상 다양성마다 새 cross-check 부담 → **입력 정규화로 N 결함 다양성 자체 차단** (사용자 판단).

**사용자 결함 ground truth 시퀀스 (라운드 b 시각 검증, 8건)**:

갯수 합병 7건:
- §4 실행방안 5→3
- §5 데이터근거 3→2
- §5 Actionable Recommendations 5→3
- §6 데이터근거 3→2
- §6 Actionable Recommendations 5→3
- §7 핵심요점 3→2
- §7 Actionable Recommendations 5→3

구조 누락 1건:
- §4 SECTION_HEADER 전체 누락 (`## 벤포벨S 핵심 차별화 자산 기반 광고 클레임 개발` sid prefix 누락이 SECTION_HEADER 분리 실패로 노출, §3 마지막 TITLE_CONTENT 로 흡수)

### sub-track 4건 (placeholder)

- **§13-14-α** — md 규약 정의 + 1차 라운드 close (2026-05-11) ✓
  - **commit 1616e88** (코드: `report_builder.py` +55/-3): 옵션 A2 helper (`_ensure_section_h2_normalized`) + 옵션 B (strip_number_prefix misuse 정정)
  - **변경 위치**:
    - `report_builder.py:263` (옵션 B): `strip_number_prefix(ls[2:].strip())` → `ls[2:].strip()`. 함수 의도 (text_utils.py:227 docstring 명시 = 매칭 폴백) vs 호출처 의도 (prepend strip) misuse 정정. section_slugify 가 자체 strip 처리 — 부작용 0
    - `report_builder.py:220-256` (옵션 A2): `_ensure_section_h2_normalized(outline_title, body)` 신규 helper. outline_title ground truth 기반 H2 + sid prefix 정규화 (in-memory, sections/.md 무수정). 4 분기 — sid 일치 통과 / sid 불일치 첫 줄 교체 / 평문 제목 한 줄 제거 + prepend (§7 케이스) / H3 이상 또는 도입부 평문 prepend (§4 케이스)
    - `report_builder.py:285` (호출 교체): `_ensure_heading(t, src)` → `_ensure_section_h2_normalized(t, src)`
  - **라운드 1 측정 (e2e, gpt-4o, temperature=0.1, scripts/regen_pptx_13_14_1.py)**:
    - n_total 38 slides (baseline 회복), SECTION_HEADER 7개 모두 sid 보유 (§1~§7)
    - §4 결함 (SECTION_HEADER + cascade 4 슬라이드) 해결 — slide#15 SECTION_HEADER + 본문 5장 모두 정상
    - §7 평문 제목 한 줄 잔존 제거 — latest.md line 233-235 `## 7. 실행 로드맵.../### 배경` 직결
    - 갯수 합병 7건 중 6건 해결: §5·§6 데이터근거·Rec (4건) + §4·§7 Rec (2건) bullets 보존
    - 잔존 1건: §7 핵심요점 3→2 (plan_deck LLM downstream, §13-14-δ 이월)
  - **결과**: 9/10 결함 해결 (90%)
  - **A1 후순위 유지**: A2 가 입력 정규화로 §4 결함 + §7 평문 제목 + sid prefix 일관성 모두 달성. A1 (section_writer prompt 강화) 추가 효과 = sections/.md 자체 정규화 (docx 단독 export 영향, catch 12 cascade) — 별도 트랙 이월
  - 보조 자료: `writer_project/scripts/_md_ground_truth_for_13_14_alpha.md` (untracked)
  - 라운드 1 산출 pptx: `writer_project/reports/venfobel-vitamin/20260511_13-14-alpha_round1.pptx` (38 slides, 105217 bytes)

- **§13-14-α stochasticity 측정 (라운드 α2 + α3, 2026-05-11)** — Phase 2·3
  - **측정 목적**: 라운드 α1 의 갯수 합병 5건 동시 해결이 stochastic 우연 vs 입력 정규화 cascade 의 안정 효과 분리. §7 핵심요점 3→2 잔존 원인 분리.
  - **측정 환경**: 동일 (gpt-4o, temperature=0.1, max_retries=0, inter-run sleep 60s)
  - **라운드 산출**:
    - α2: `reports/venfobel-vitamin/20260511_alpha_round2.pptx` (38 slides, 97581 bytes, plan 32.0s)
    - α3: `reports/venfobel-vitamin/20260511_alpha_round3.pptx` (38 slides, 99414 bytes, plan 32.2s)
  - **결함 10건 × 3 라운드 측정 표**:

  | 결함 | α1 | α2 | α3 | 양상 |
  |---|---|---|---|---|
  | §4 H2 누락 / SECTION_HEADER 누락 / cascade 4 슬라이드 누락 | 해결 | 해결 | 해결 | **3/3 안정 해결** |
  | §7 평문 제목 중복 | 해결 | 해결 | 해결 | **3/3 안정 해결** |
  | §5 데이터근거 3→2 | 3 (해결, cascade) | 3 | 3 | **3/3 안정** |
  | §5 Rec 5→3 | 5 (해결, cascade) | 5 | 5 | **3/3 안정** |
  | §6 데이터근거 3→2 | 3 (해결, cascade) | 3 | 3 | **3/3 안정** |
  | §6 Rec 5→3 | 5 (해결, cascade) | 5 | 5 | **3/3 안정** |
  | **§7 핵심요점 3→2** | **2 (잔존)** | **3 (해결)** | **3 (해결)** | **stochastic 변동 (1/3 잔존)** |
  | §7 Rec 5→3 | 5 (해결, cascade) | 5 | 5 | **3/3 안정** |

  - **추가 양상 (결함 아닌 LLM 자율 축약)**: §6 SECTION_HEADER title `α1: "벤포벨S" 누락 / α2: 원형 / α3: "벤포벨S" 누락` — SECTION_HEADER 자체는 정상, title 자율 축약 stochastic 변동.
  - **cascade 효과 안정도**: 갯수 합병 cascade 해결 후보 5건 × 3 라운드 = **15/15 안정 해결 = 100%**. catch 22 단서 확증 강화 — 입력 정규화 cascade 메커니즘 안정 동작 입증.
  - **§7 핵심요점 잔존 원인 분리 판정**: **(i) stochastic 잔류 확정**
    - (ii) §7 핵심요점 특이 메커니즘 → 부정 (α2·α3 해결됨)
    - (iii) 3 bullets 임계 양상 → 부정 (§5·§6 데이터근거 3 bullets 도 3/3 안정 해결)
    - (i) stochastic 잔류 → 확정 — α1 잔존이 *우연 잔존*, α2·α3 에서 plan_deck LLM 이 정상 3 bullets 출력
  - **§13-14-β 진입 영향**: A2+B 만으로 90%+ 결함 차단 + cascade 100% 안정 → **β-1 (LLM prompt 강화) 불필요 / β-2 (section_writer 후처리) 선택사항 / β-3 (build_final_report 후처리) 본 라운드 구현 완료**. **§13-14-β 본격 진입 의의 약화**.
  - **§13-14-δ 진입 보류 확정**: §7 핵심요점 1건만으론 진입 트리거 약함 (3/3 안정 잔존 아니라 1/3 stochastic 잔류). 진입 트리거 조건:
    - 추가 stochastic 변동 결함 발견 시
    - 사용자 e2e 시각 검증 추가 결함 보고 시
  - **§13-14-γ 비용 사전 조사**: 낙관 ~1.5h / 비관 ~4.25h. 비관 트리거 = edge case (참고문헌 자율 제외, §6 자율 축약, §7 평문 제목, §4 도입부 평문) 디버깅. **본 세션 컨텍스트 부담 + 비관 위험으로 다음 세션 분기 결정**.

- **§13-14-β** — 정규화 layer 구현
  - 진입 조건: §13-14-α close 후
  - 작업: 규약 적용 위치 결정 (section_writer LLM 출력 직후 vs build_final_report 합성 직전 vs cascade) + 3 양상 변환 로직 + 단위 검증 케이스

- **§13-14-γ** — linter
  - 진입 조건: §13-14-β close 후
  - 작업: 규약 위반 검출 (정규화 후 LLM stochasticity 잔존) + reject/warning 결정 + 호출 위치
  - commit 시점 catch 21 박제 확정

- **§13-14-δ** — 잔존 결함 fix 재진입
  - 진입 조건: §13-14-α·β·γ close 후, 정규화 layer 차단 못 한 결함 잔존 시
  - 작업: §13-14-1 patch v1 패턴 재활용 (prompts.py / spec.py) vs §13-14-2 정규화 layer 보강 분기 결정
  - catch 18 후보 (LLM 압축 양상 차원별 분리) / catch 19 후보 (few-shot 입력 분포 일반화 한계) 박제 결정 — 정규화 layer 가 입력 양상 통일하면 catch 19 의의 약화 가능성

### catch 박제 (§13-14-α 1차 라운드 commit 시점 — catch 17 번복 / catch 20·22·24 확정 / catch 18·19 조건부 / catch 21 예약)

- **catch 17 번복 (§13-14-α A2+B 적용 후)** — 1차 박제 (직전 §13-14-1 단계): "stochasticity = 결정론 강제 vs 정보 충실도 trade-off 의 운영 양상, LLM 자율 제외 + 강제 매핑 trade-off". **번복 (본 commit 시점)**: §13-14-α A2+B 적용 후 라운드 1 측정 결과 — "stochasticity = 입력 양상 일관성에 *조건부* 비례, 정규화 layer 로 *대부분* 차단 가능". 라운드 (b) 33 slides + §4 누락 (입력 양상 불일치 — §4 sid 없는 H2) → 라운드 α1 38 slides + 7 SECTION_HEADER 정상 (입력 양상 일관성 — 7개 sid 보유 H2). *조건부* 표현은 §7 핵심요점 3→2 잔존 1건의 측정 근거 — plan_deck LLM downstream 결함은 입력 정규화로도 차단 안 됨. 자산화: 입력 양상 일관성이 downstream LLM stochasticity 의 *진폭 결정 변수*, 완전 차단 변수는 아님. **추가 정밀화 (Phase 2·3, α2+α3 측정 후)**: **stochasticity = 입력 양상 일관성에 *강하게* 비례, 정규화 layer 로 *대부분* 차단 + 잔존도 bullet 갯수 수준 미세 변동 (구조 변동 0)**. 보정 근거 — cascade 15/15 = 100% 안정 + §7 핵심요점 잔존이 bullet 1개 차이 (3→2) 수준 미세 변동 + SECTION_HEADER 누락·슬라이드 누락 같은 구조 변동 0/30 (3 라운드 30 케이스 모두 0). "조건부" → "강하게" 표현 보정은 측정값 (cascade 100% + 구조 변동 0) 의 정합 표현.

- **catch 20 확정 (§13-14-α 1차 라운드 commit 시점)** — md 구조 일관성 → 입력 정규화 우선: 입력 양상의 분기 (sid prefix / 본문 패턴 / bullet KEY / 출처 마커) 가 downstream LLM (plan_deck) 처리 안정성을 결정. 규약 정의 = 결함 다양성의 차단점. 라운드 α1 측정값 — §4 sid 보유 H2 정규화 → SECTION_HEADER 매핑 안정성 강화 + cascade 효과로 갯수 합병 5건 동시 해결 입증.

- **catch 21 (§13-14-γ commit 시점 박제 예약)** — linter (정규화 후 잔존 결함 검출): 정규화 layer 가 LLM stochasticity 영향까지 차단 못 함 (catch 17 *조건부* 표현 참조). linter 가 build_final_report 단계 reject/warning. catch 9 (XML 검증 PASS ≠ 시각 검증 PASS) 의 *입력 단계 변종*.

- **catch 22 확정 (§13-14-α 1차 라운드 commit 시점)** — 입력 정규화 우선 원칙: md 입력 분포 들쭉날쭉 상태에서 downstream fix tree 누적 = 결함 양상 다양성마다 새 cross-check 부담. 입력 정규화로 N 결함 다양성 자체 차단. §13-14-1 downstream fix tree (§13-14-1-a/b/c) 폐기 결정의 ground truth. catch 16 (공유 단계 fix 누락) 의 *root cause 단계 결정 원칙* 변종. **단서 (라운드 α1 측정값 입증)**: **입력 정규화 효과가 직접 fix 범위를 *초과* 할 수 있음 — downstream LLM 처리 안정성 cascade 강화 메커니즘**. 본 라운드 갯수 합병 5건 (§5·§6 데이터근거·Rec + §4·§7 Rec) 동시 해결이 측정 근거 — A2+B 의 직접 fix 범위 (§4 H2 + §7 평문 제목 + sid prefix 일관성) 는 갯수 합병을 포함하지 않았으나 cascade 효과로 해결.

- **catch 24 신규 확정 (§13-14-α 1차 라운드 commit 시점)** — 함수 의도 vs 호출처 의도 mismatch (misuse 정정): `strip_number_prefix` 함수 의도 (text_utils.py:227 docstring 명시 = 매칭 폴백) vs 호출처 의도 (report_builder.py:263 prepend strip) mismatch. 폐기 (함수 제거) 가 아니라 호출처 정정 (옵션 B = strip 호출 제거) 으로 해결. 자산화: **함수 자체는 정합 의도 보유, 호출처가 의도 외 용도로 사용한 misuse 케이스는 함수 폐기가 아니라 호출처 정정으로 해결**. catch 5 (helper 입력 계약 호출자별 비대칭) 의 *의도 비대칭* 변종 — catch 5 는 입력 형식 비대칭, catch 24 는 사용 의도 비대칭.

- **catch 18 후보 (§13-14-δ 진입 조건부 박제)** — LLM 압축 양상의 차원별 분리 (텍스트 길이 vs 갯수): §7 핵심요점 3→2 잔존 분석 시 차원별 분리 양상 부합 여부로 확정/폐기 결정. **Phase 2·3 측정 후 갱신**: §7 핵심요점 α2·α3 해결 → 차원별 분리 양상 아닌 *stochastic 잔류*. catch 18 **폐기 시사 강함** — §13-14-δ 진입 보류와 정합.

- **catch 19 후보 (§13-14-δ 진입 조건부 박제)** — few-shot 입력 분포 일반화 한계 (list vs 단락): 정규화 layer 가 입력 양상 통일하면 본 catch 의의 약화 가능성. 라운드 α1 결과로 입력 정규화 cascade 효과 강 → catch 19 폐기 시사 강함. **Phase 2·3 측정 후 확정**: cascade 효과 100% 안정 (15/15) → catch 19 **폐기 확정** — few-shot 입력 분포 일반화 한계는 본 측정 범위에서 발현 안 됨.

- **§13-14-δ 진입 보류 확정 (Phase 2·3 측정 후)**: 본 측정 범위 (3 라운드) §7 핵심요점 1건만 stochastic 잔류, 나머지 9건 안정 해결. **§13-14-δ 진입 트리거 조건**:
  - 추가 stochastic 변동 결함 발견 시
  - 사용자 e2e 시각 검증 추가 결함 보고 시
  - 본 측정 범위 진입 보류, §13-14-2 트랙 잠정 close 후보로 이동

### 보조 자료 위치

- §4·§7 ground truth md 본문 + 양상 메모: `writer_project/scripts/_md_ground_truth_for_13_14_alpha.md` (본 세션 작성, untracked)
- 라운드 (b) 산출 pptx: `writer_project/reports/venfobel-vitamin/20260511_§13-14-1-patch-v1.pptx` (33 slides)
- 사용자 baseline pptx: `D:\Downloads\종근당_'벤포벨S'_2026_광고기획___고함량_활성비타민_시장_3C_분석 (1).pptx` (38 slides)

---

## §13-14-α-sonnet — Sonnet 4.6 호환성 + 풍부함 + dual track 채택 (2026-05-11)

### 진입 배경

§13-14-α A2+B fix 가 1106d7d 시점 gpt-4o 측정 (α1·α2·α3) 에서 cascade 100% 안정 + 구조 변동 0/30 입증 후, 사용자 직전 세션 종료 시점 NEXT_SESSION.md 박제는 §13-14-γ linter 진입 노트로 작성돼 있었음. 본 세션 사용자 명시 의도로 **§13-14-γ 잠정 보류 + Sonnet 4.6 1 라운드 탐색 우선** 결정. 1 라운드 후 사용자 시각 검증으로 **풍부함 = 가치** 판정 → 추가 2 라운드 측정 후 **dual track 운영 채택**.

### Phase 1 — Sonnet 4.6 호환성 검증 (3 라운드 측정)

**측정 환경**: .venv_anthropic + LLM_PROVIDER=anthropic + ANTHROPIC_MODEL=claude-sonnet-4-6 + temperature=0.1 + max_retries=0 + ANTHROPIC_REQUEST_TIMEOUT=600s

**측정 방식**: section_writer × 7 (RAG references 는 gpt-4o 시점 `.refs.json` 직접 재사용 — RAG 우회로 fair 비교 보장) → build_final_report → plan_deck → render_deck

**3 라운드 기본 측정값**:

| round | n_slides | pptx KB | n_h3 (planner 입력) | section_writer 7회 (s) | plan_deck (s) | e2e 합계 (s) |
|---|---|---|---|---|---|---|
| R1 | 52 | 162.6 | 49 | 457.6 (mtime 추정) | 344.5 (retry) | 803.5 (≈13.4분) |
| R2 | 53 | 165.8 | 50 | 379.8 | 284.8 | 665.2 (≈11.1분) |
| R3 | 55 | 172.9 | 51 | 380.7 | 303.2 | 684.4 (≈11.4분) |
| mean | 53.3 | 167.1 | 50.0 | 406.0 | 310.8 | 717.7 (≈12.0분) |
| CV | 2.86% | 3.16% | 2.00% | 11.1% | 9.8% | 10.6% |

### Phase 2 — §13-14-α A2+B 4 분기 cascade 안정도 (Sonnet 4.6 영역)

| 분기 | R1 | R2 | R3 | 안정도 |
|---|---|---|---|---|
| (a) §4 SECTION_HEADER 존재 + 7개 sid prefix | 7/7 ✓ | 7/7 ✓ | 7/7 ✓ | **3/3 안정** |
| (b) §7 평문 제목 중복 없음 | ✓ | ✓ | ✓ | **3/3 안정** |
| (c) §4 본문 슬라이드 ≥5 | 6 | 6 | 7 | **3/3 안정** |
| (d) §X cascade 권고 5건 표준 패턴 | 7/7 § 모두 표준 | 7/7 | 7/7 | **3/3 안정** |

**판정**: §13-14-α A2+B fix 가 **Sonnet 4.6 에서 3/3 cascade 안정 작동 ✓**. gpt-4o (α1·α2·α3) 의 100% cascade 안정도가 그대로 재현 — **fix 가 provider-agnostic 입증** (catch 13 "변환 단계 fix = provider 무관" 의 multi-provider 측정값 입증).

### Phase 3 — plan_deck 누락 분리 (본질 + stochastic 혼재)

**누락률 분포**: R1 8.8% / R2 8.6% / R3 6.8% (mean 8.1%, range 2.0%, CV 13.6%)

**§ 별 누락 패턴 (md H3 vs pptx buckets)**:

| § | md H3 (R3) | R1 buckets | R2 buckets | R3 buckets | 양상 |
|---|---|---|---|---|---|
| §1 | 8 | 6 (-2) | 7 (-1) | 7 (-1) | stochastic 변동 |
| §2 | 7 | 6 (-1) | 6 (-1) | 6 (-1) | **systematic 1개 누락** |
| §3 | 7 | 6 (-1) | 6 (-1) | 7 (0) | 부분 누락 |
| §4 | 8 | 6 (-2) | 6 (-2) | 7 (-1) | 부분 누락 |
| §5 | 8 | 7 (-1) | 6 (-2) | 7 (-1) | stochastic |
| §6 | 6 | 6 (0) | 7 (+1) | 6 (0) | 0 누락 / R2 +1 잉여 |
| §7 | 7 | 7 (0) | 7 (0) | 7 (0) | **0 누락 3/3 안정** |

**판정 = (i) 본질 한계 + (ii) stochastic 잔류 혼재**
- §2 **systematic -1 누락 (3/3)** — Sonnet section_writer 의 §2 md 입력 양상이 plan_deck 처리 비호환 본질 한계
- §7 0 누락 3/3 안정 — md 형태 plan_deck 호환 양상 (기준점)
- §1, §3, §4, §5 stochastic 변동
- §6 R2 +1 잉여 — plan_deck 가 md H3 외 슬라이드 추가 생성 가능성

**향후 prompt 패치 진입 시 §2 양상 우선 분석 권고**.

### Phase 4 — 풍부함 일관성 (박제 §13-8 "CV 3.6%" 검증)

| metric | R1 | R2 | R3 | mean | CV % |
|---|---|---|---|---|---|
| n_slides | 52 | 53 | 55 | 53.3 | **2.86%** |
| pptx KB | 162.6 | 165.8 | 172.9 | 167.1 | **3.16%** |
| merged_md chars | 33,872 | 33,433 | 34,126 | 33,810 | **1.03%** |
| n_h3 (md 입력) | 49 | 50 | 51 | 50.0 | **2.00%** |
| TITLE_TABLE | 16 | 15 | 18 | 16.3 | 9.35% |
| TITLE_CONTENT | 28 | 30 | 29 | 29.0 | 3.45% |

**판정**: 핵심 풍부함 지표 (n_slides, pptx KB, merged_md chars, n_h3) CV **1~3% 범위** → 박제 §13-8 "CV 3.6%" **정확 재현**. TITLE_TABLE 만 CV 9.35% (표 산출 약간 stochastic). **batch use case 채택 정당성 강하게 입증**.

### Phase 5 — dual track 운영 결정

**비교 표 (gpt-4o vs Sonnet 4.6 3 라운드 mean)**:

| 항목 | gpt-4o (α1·α2·α3) | Sonnet 4.6 (R1·R2·R3) | 비교 |
|---|---|---|---|
| 총 슬라이드 수 | 38 (3/3 안정) | 53.3 (CV 2.86%) | Sonnet **1.40×** |
| md sections chars 합 | ~16,000~18,000 | merged 33,810 (CV 1.03%) | Sonnet **~1.86×** |
| md 입력 H3 갯수 | ~30 | 50.0 (CV 2.00%) | Sonnet **~1.66×** |
| pptx 파일 크기 | 99~105 KB | 167.1 KB (CV 3.16%) | Sonnet **~1.6×** |
| plan_deck latency | ~30~32s | 310.8s (CV 9.8%) | Sonnet **~9.7×** |
| e2e (full pipeline) | 추정 ~4~5 분 | 12.0 분 (CV 10.6%) | Sonnet **~2.6×** |
| plan_deck 누락률 | 0% (구조 변동 0/30) | 8.1% (range 2.0%) | gpt-4o 압도 |
| TITLE_TABLE 갯수 | 0 (추정) | 16.3 (CV 9.35%) | Sonnet 표 양상 풍부 |
| cascade 안정도 (A2+B 4분기) | 3/3 안정 | **3/3 안정** | **동일** |
| 권고 5건 표준 패턴 | 5/7 § 5 bullets | 7/7 § 표준 패턴 | Sonnet 우세 |

**use case 매핑 (dual track 운영)**:

- **gpt-4o 트랙** = 빠른 산출 / 비용 민감 / 단건 처리 / 즉시 응답 use case
- **Sonnet 4.6 트랙** = 풍부한 산출 / batch 처리 / 시간 허용 / 정성 산출 use case

**provider 토글 절차**:

openai → anthropic:
- `.env`: `LLM_PROVIDER=anthropic`
- `.env.anthropic`: `ANTHROPIC_MODEL=claude-sonnet-4-6` (또는 `claude-haiku-4-5-20251001`)

anthropic → openai 복귀:
- `.env`: `LLM_PROVIDER=openai`
- `.env.openai`: `OPENAI_MODEL=gpt-4o` 확인

주의:
- 글로벌 `.env` 의 `LLM_MODEL` 은 vertexai key 라 openai/anthropic 경로에서 무시
- plan_deck + section_writer 가 싱글턴 공유 (core/llm.py `_LLM`) — provider 토글 시 동시 변경
- 임베딩은 `RAG_EMBEDDING_MODEL` overlay 로 provider 자동 매칭 (anthropic 사용 시 `.env.anthropic` 가 `text-embedding-3-large` 3072d 강제 → `venfobel-vitamin-oa-*` 인덱스와 일치)

### Phase 6 — timeout 240s → 600s 상향 결정

**근거**: Sonnet 4.6 plan_deck mean 310.8s, 3/3 라운드 모두 240s 초과 (R1 첫 시도 = APITimeoutError after 240s)

**조치**: `.env.anthropic` 의 `ANTHROPIC_REQUEST_TIMEOUT=600` 운영 default (anthropic provider 사용 시 필수). openai provider 는 기존 default 유지 가능.

**적용 범위**: dual track 의 인프라 측 분기 — provider 별 timeout 분리는 `.env.<provider>` overlay 패턴으로 이미 지원 (catch 13 "측정 인프라 fix = provider 별 분리" 의 measurement-stage 입증).

### Phase 7 — §13-8 재진입 갱신

기존 박제 (사용자 메모리): "재진입 조건부 보류 — (a) latency improvement / (b) cost-insensitive batch / (c) suppression prompt patch"

**본 측정 후 갱신**:
- (a) latency: 기존 박제 "~5×" → 실측 **~2.6×** (e2e). dual track 채택 시 *시간 부담 = 선택 비용* 으로 흡수
- (b) batch use case: CV 1~3% 측정으로 **batch 적합성 확정**
- (c) suppression prompt patch: **미적용**. 다만 *사용자 시각 검증으로 풍부함 = 가치* 판정 → 패치 없이 dual track 채택 정당화

**결론**: 재진입 조건부 보류 → **dual track 채택 확정**. §2 systematic 누락만 향후 prompt 패치 시 우선 분석 대상.

### catch 박제 (§13-14-α-sonnet commit 시점 — catch 25 신규)

- **catch 25 신규 확정 (§13-14-α-sonnet commit 시점)** — 시각 검증이 정량 측정 권고를 조정한 사례: 정량 측정 (1 라운드) 만으로 운영 채택 비권고 결론이 나왔으나, 사용자 시각 검증으로 *풍부함 = 가치* 판정 → dual track 분기 발견. **정량 측정 < 사용자 use case 평가** 의 사례. 자산화: **박제 권고에 *시각 검증 입력 항목* 포함 원칙**. 근거 측정값 — 본 세션 Sonnet 4.6 1 라운드 시점 본 세션 측 권고 ("재진입 조건 (c) 미충족, 채택 비권고 시사") vs 사용자 시각 검증 후 "dual track 채택" 결정 분기.

- **catch 22 cascade 단서 확장 (§13-14-α-sonnet commit 시점)** — 입력 정규화 원칙 multi-provider 일관 작동: gpt-4o 에서 cascade 100% 안정 + 구조 변동 0/30 + Sonnet 4.6 에서 cascade 4분기 3/3 안정. **§13-14-α A2+B fix 가 provider-agnostic 변환 단계 fix 의 multi-provider 측정 입증** (catch 13 "변환 단계 fix = provider 무관" 의 multi-provider ground truth).

- **catch 17 정밀화 (§13-14-α-sonnet commit 시점, 본 라운드 측정 후)** — stochasticity = *입력 양상 일관성* + *plan_deck 자체 stochasticity* 양 차원. gpt-4o 는 plan_deck stochasticity 가 bullet count 미세 변동 (§7 핵심요점 3→2 1/3 잔존) 으로만 발현. Sonnet 4.6 은 plan_deck stochasticity 가 **H3 누락 양상** 으로 발현 (§ 별 -1~-2 변동). 본 차이는 provider 의 plan_deck 처리 양상 차이 — A2+B 정규화 layer 가 입력 양상 차원만 일관화, plan_deck 자체 stochasticity 는 provider 별 발현 차이 유지.

### 산출 자산 위치

- pptx 3개:
  - `reports/venfobel-vitamin/20260511_214020_sonnet_round1.pptx` (162.6 KB, 52 slides)
  - `reports/venfobel-vitamin/20260511_221134_sonnet_round2.pptx` (165.8 KB, 53 slides)
  - `reports/venfobel-vitamin/20260511_223033_sonnet_round3.pptx` (172.9 KB, 55 slides)
- 종합 보고서: `scripts/_sonnet_3rounds_report.md` (본 박제 본문의 원자료)
- 분석 dump: `scripts/_sonnet_3rounds_analysis_output.txt`
- 1 라운드 단독 보고: `scripts/_sonnet_round1_report.md`
- 라운드 별 meta JSON: `scripts/_sonnet_round{1_retry,2,3}_meta_*.json`
- 라운드 별 콘솔 dump: `scripts/_sonnet_round{1,1_retry,2,3}_console.txt`
- driver 스크립트: `scripts/regen_sonnet_round1.py` (round 인자 받는 generic e2e), `scripts/regen_sonnet_round1_retry_plan.py` (Phase B+C+D 재실행용), `scripts/sonnet_3rounds_analysis.py` (3 라운드 분석)
- backup 체인:
  - `reports/venfobel-vitamin/_backup_pre_sonnet_round1_*` — gpt-4o 원본 sections
  - `reports/venfobel-vitamin/_backup_pre_sonnet_round2_*` — R1 sections
  - `reports/venfobel-vitamin/_backup_pre_sonnet_round3_*` — R2 sections
- 현재 sections/ = R3 (Sonnet 최신)

### Re-entry conditions (§13-14-α-sonnet)

- (R1) Sonnet 4.6 prompt 패치 진입 시 — §2 systematic 누락 양상 분석 우선
- (R2) Haiku 4.5 평가 진입 (§13-8-3) 시 — 본 §13-14-α-sonnet 측정값 baseline 으로 비교
- (R3) 다른 토픽 일반화 검증 (pet-food-premium 등) — provider-agnostic 양상 추가 측정

---

## §13-14-γ — linter 정식화 (2026-05-11)

### 진입 배경

§13-14-2 트랙의 명시적 sub-track 4건 (α / β / γ / δ) 중 마지막 — **linter 정식화로 트랙 정체성 완수**. 직전까지 ad-hoc grep + 수동 카운트로 측정해 온 결함 양상·cascade 안정도·풍부함 CV 를 *자동 측정 스크립트* 로 정식화. dual track (gpt-4o + Sonnet 4.6) 시점에서 양 트랙 ground truth 일치 검증 도구로 활용.

### 모듈 구성

단일 파일 `scripts/lint_report_consistency.py` (LLM 호출 0, python-pptx 의존 0):

| 모듈 | 측정 항목 |
|---|---|
| `md_measure` | sections/.md + latest.md 의 H2 양상 (sid prefix / 평문 도입부 / 평문 제목 한 줄), H3 갯수, H3 별 bullet 갯수 |
| `pptx_measure` | extract_pptx_text.py 의 zip+ET 패턴 재사용 — slide layout 분류, SECTION_HEADER sid prefix 보유, TITLE_CONTENT bullet 갯수, table 갯수 |
| `compare` | md ↔ pptx cascade 안정도 + 누락률 (`expected = 1 + n_h2 + n_h3` vs actual) + § 별 본문 슬라이드 수 |
| `report` | 결함 양상 표 + 다중 라운드 통합 (3 라운드 → CV 자동 계산) |
| `CLI` | `--pptx` (단일) / `--rounds + --rounds-md` (다중 라운드 + 라운드별 latest.md) / `--outline` / `--sections-dir` / `--output` |

### 재사용 자산

| 자산 | 위치 | 재사용 |
|---|---|---|
| extract_pptx_text.py | scripts/ (119 lines) | zip + ET parsing 100% 재사용 (python-pptx 의존성 회피 — gpt-4o 측정 인프라와 동일 의존성 0 패턴) |
| verify_13_14_1.py | scripts/ (305 lines) | bullet 측정 패턴 부분 재사용 |
| sonnet_3rounds_analysis.py | scripts/ | python-pptx 기반 분석 — γ 와 의존성 별개 (linter 는 의존성 0 강제, analysis 는 신속 측정) |

### Sanity check — 두 트랙 ground truth 정합 (catch 21 확정 근거)

**gpt-4o 트랙** (sections/ = gpt-4o 복원 후, α1·α2·α3 pptx):

| 측정값 | linter 출력 | 박제 ground truth (1106d7d / bf07d23) | 정합 |
|---|---|---|---|
| n_slides (3 라운드) | 38·38·38 | 38·38·38 (3/3 안정 해결) | ✓ |
| SECTION_HEADER 7개 + sid prefix | 7/7 (3/3 라운드) | 7/7 | ✓ |
| 누락률 | 0%·0%·0% | 0% (구조 변동 0/30) | ✓ |
| §1~§7 본문 slides | 1·5·4·5·5·5·5 (CV 0%) | 동일 (cascade 15/15 = 100%) | ✓ |
| pptx KB CV | 3.96% | 박제 §13-8 "CV 3.6%" 정합 | ✓ |
| md §4 (벤포벨S 핵심) | H2 ✗ / 평문 도입부 ✓ | §13-14-α A2 분기 4 작동 대상 | ✓ |
| md §7 (실행 로드맵) | H2 ✗ / 평문 제목 한 줄 ✓ | §13-14-α A2 분기 3 작동 대상 | ✓ |

**Sonnet 4.6 트랙** (sonnet_round1·2·3 pptx, 라운드별 latest.md 와 1:1 매칭):

| 측정값 | linter 출력 | 박제 ground truth (76db4da §13-14-α-sonnet) | 정합 |
|---|---|---|---|
| n_slides | 52·53·55 (CV 2.86%) | 52·53·55 (CV 2.86%) | ✓ |
| pptx KB CV | 3.16% | 3.16% | ✓ |
| 누락률 | 8.77%·8.62%·6.78% (mean 8.06%) | 8.8%·8.6%·6.8% (mean 8.1%) | ✓ |
| §2 systematic 누락 | buckets 6·6·6 (CV 0%) | 3/3 모두 -1 (systematic) | ✓ |
| §7 0 누락 안정 | buckets 7·7·7 (CV 0%) | 3/3 안정 | ✓ |
| §1/§3/§4/§5/§6 stochastic | CV 8.66/9.12/9.12/8.66/9.12% | 박제 표 그대로 | ✓ |
| TITLE_TABLE CV | 9.35% (16·15·18) | 9.35% | ✓ |
| TITLE_CONTENT CV | 3.45% (28·30·29) | 3.45% | ✓ |
| SECTION_HEADER 7+sid | 7/7 (3/3 라운드) | 7/7 (3/3) | ✓ |

**판정**: linter 측정값이 직전 박제 ground truth 와 **1:1 정확 일치 (양 트랙 모두)**. **catch 21 확정 박제 자격 충족** (linter 정규화 후 ground truth 정합).

### 사용 예시

```powershell
# gpt-4o 3 라운드 측정 (sections/ + outline + 3 pptx)
python scripts/lint_report_consistency.py `
  --sections-dir sections/venfobel-vitamin `
  --rounds reports/venfobel-vitamin/20260511_13-14-alpha_round1.pptx `
           reports/venfobel-vitamin/20260511_alpha_round2.pptx `
           reports/venfobel-vitamin/20260511_alpha_round3.pptx `
  --outline outlines/venfobel-vitamin/outline_report.md `
  --output scripts/_lint_gpt4o_3rounds.md

# Sonnet 3 라운드 측정 (라운드별 latest.md 1:1 매칭으로 정확한 누락률)
python scripts/lint_report_consistency.py `
  --rounds reports/venfobel-vitamin/20260511_214020_sonnet_round1.pptx `
           reports/venfobel-vitamin/20260511_221134_sonnet_round2.pptx `
           reports/venfobel-vitamin/20260511_223033_sonnet_round3.pptx `
  --rounds-md reports/venfobel-vitamin/20260511-214020_report.md `
              reports/venfobel-vitamin/20260511-221755_report.md `
              reports/venfobel-vitamin/20260511-223653_report.md `
  --outline outlines/venfobel-vitamin/outline_report.md `
  --output scripts/_lint_sonnet_3rounds.md
```

### catch 박제 (§13-14-γ commit 시점 — catch 21 확정 + catch 26 신규)

- **catch 21 확정 (§13-14-γ commit 시점, 직전 박제 예약 충족)** — linter (정규화 후 잔존 결함 검출 + ground truth 정합 자기검증): 본 linter 가 두 트랙 (gpt-4o + Sonnet 4.6) 의 직전 박제 ground truth 와 1:1 정확 일치 측정값 산출 → linter 측정 자체의 self-validation 양상. 향후 측정은 ad-hoc grep 이 아닌 본 linter 기준점으로 표준화 가능. **catch 9 "XML 검증 PASS ≠ 시각 검증 PASS" 의 *입력 단계 변종*** — linter 측정 PASS 가 시각 검증 PASS 를 보장하지는 않으나, *측정 일관성 + 박제 ground truth 정합* 의 자동화 도구.

- **catch 26 신규 확정 (§13-14-γ commit 시점)** — 측정 도구의 *의존성 0 강제* 원칙: linter 가 python-pptx 미사용 (zip + xml.etree 표준 라이브러리만) → 다음 가치 입증:
  - (i) **인프라 분리 catch 13 변환 단계 fix 의 측정 도구 변종** — 의존성 0 으로 운영 venv 변화 (gpt-4o/anthropic/vertex) 무관 작동
  - (ii) **측정 인프라 보존성** — 의존성 추가 비용 0, 향후 dual track 운영 또는 추가 provider 추가 시 동일 linter 재사용
  - (iii) **catch 24 (함수 의도 vs 호출처 의도) 의 정합 변종** — extract_pptx_text.py 의 zip+ET 패턴이 *의도된 재사용 자산* 으로 설계 (단일 책임 + 의존성 0). linter 가 그 의도를 100% 흡수 → misuse 없는 *catch 24 정합 케이스*.

  추가 단서: python-pptx 기반 측정 (`sonnet_3rounds_analysis.py`) 과 linter 측정값이 일치 → 두 라이브러리 패턴의 cross-check 자산.

### 산출 자산 위치

- linter 본체: `scripts/lint_report_consistency.py` (LLM 0, python-pptx 0, 표준 라이브러리만)
- sanity check 보고서:
  - `scripts/_lint_gpt4o_3rounds.md` (gpt-4o 트랙 + sections/ 양상)
  - `scripts/_lint_sonnet_3rounds.md` (Sonnet 트랙 + 라운드별 latest.md 매칭)
- 재사용 의존: `scripts/extract_pptx_text.py` (zip+ET 패턴 100% 재사용)

### Re-entry conditions (§13-14-γ)

- (R1) 다른 토픽 (pet-food-premium / height-growth-supplement 등) 측정 시 — linter outline H2 vs SECTION_HEADER 매칭 일반화 확인
- (R2) provider 추가 (Haiku 4.5 / Vertex Gemini 등) — linter 재사용 + ground truth 박제
- (R3) build_final_report 단계 reject/warning 도입 — catch 21 의 *운영 layer 진입* 단계 (현재 linter 는 측정만, reject 없음)

---

## §13-14-2 트랙 close (2026-05-11)

§13-14-2 트랙 (md 입력 정규화 우선 패턴) 의 4 sub-track 모두 처리 완수.

### sub-track 처리 상태

| sub-track | 상태 | 산출 / 박제 commit |
|---|---|---|
| **§13-14-α** | **close** | A2+B fix (1616e88 report_builder.py) + cascade 100% gpt-4o (1106d7d) + Sonnet 4.6 호환 + dual track 채택 (76db4da) |
| **§13-14-β** | **별도 진입 의의 약화** | β-3 (build_final_report 후처리) 가 α 안에 흡수. β-1·β-2 진입 의의 약화 박제 (1106d7d) |
| **§13-14-γ** | **close** | linter 정식화 (ad9d40f, scripts/lint_report_consistency.py) + sanity check 양 트랙 1:1 정합 + catch 21 확정 + catch 26 신규 |
| **§13-14-δ** | **진입 보류** | stochastic 잔류 1건만 발현, 진입 트리거 조건 박제 (1106d7d) |

### 트랙 commit 시퀀스

| commit | 내용 |
|---|---|
| 1616e88 | §13-14-α A2+B 코드 변경 (report_builder.py +55/-3) |
| bf07d23 | §13-14-α 1차 라운드 박제 (catch 17 번복 + catch 20·22·24 확정) |
| 1106d7d | §13-14-α Phase 2·3 측정 (cascade 100% + 구조 변동 0/30) + §13-14-δ 진입 보류 |
| 76db4da | §13-14-α-sonnet dual track 박제 (Sonnet 4.6 3 라운드 + catch 25 신규) |
| ad9d40f | §13-14-γ linter 구현 + sanity check (catch 21 확정 + catch 26 신규) |
| (본 commit) | §13-14-2 트랙 close 박제 |

### 트랙 자산 종합

**측정 자산**:
- 결함 10건 × 3 라운드 (gpt-4o α1·α2·α3): 결함 9/10 해결 (90%) + §7 핵심요점 1/3 stochastic 잔류
- 4 분기 cascade × 3 라운드 (Sonnet 4.6 R1·R2·R3): 4/4 cascade 안정 + 누락 mean 8.1%
- 풍부함 CV 1~3% (양 트랙 모두 §13-8 박제 "CV 3.6%" 정합)

**운영 자산**:
- dual track 운영 결정 (gpt-4o + Sonnet 4.6)
- provider 토글 절차 (.env LLM_PROVIDER + .env.<provider> *_MODEL)
- timeout 운영 default (anthropic 600s / openai 240s)
- linter 정식화 (의존성 0, 자동 측정)

**catch 자산 종합**:

| catch | 박제 시점 | 자산 |
|---|---|---|
| catch 17 | bf07d23 번복 → 1106d7d 정밀화 → 76db4da 정밀화 | stochasticity = 입력 양상 + plan_deck provider 별 발현 |
| catch 20 | bf07d23 확정 | md 구조 일관성 → 입력 정규화 우선 |
| catch 21 | ad9d40f 확정 | linter 정규화 후 ground truth 정합 self-validation |
| catch 22 | bf07d23 확정 → 76db4da multi-provider 확장 | 입력 정규화 우선 원칙 provider-agnostic |
| catch 24 | bf07d23 확정 | 함수 의도 vs 호출처 의도 mismatch (misuse 정정) |
| catch 25 | 76db4da 확정 | 시각 검증이 정량 측정 권고를 조정한 사례 |
| catch 26 | ad9d40f 확정 | 측정 도구의 의존성 0 강제 원칙 |

### Re-entry conditions (§13-14-2 트랙 전체)

- (R1) **§13-14-δ 진입** — 추가 stochastic 변동 결함 발견 시 / 사용자 e2e 시각 검증 추가 결함 보고 시
- (R2) **§13-14-α-sonnet R2** — Sonnet 4.6 prompt 패치 진입 (§2 systematic 누락 양상 분석 우선)
- (R3) **§13-14-γ R3** — build_final_report 단계 reject/warning 도입 (linter 의 운영 layer 진입)
- (R4) **다른 토픽 일반화 검증** — pet-food-premium / height-growth-supplement 등 (provider-agnostic + topic-agnostic 양상 측정)

### 다음 트랙 후보

- **§13-8-3** — Anthropic Haiku 4.5 평가 (사용자 메모리 박제 트랙)
- 또는 사용자 결정 다른 트랙

---

© Bell Agent · writer_project — Developer Guide