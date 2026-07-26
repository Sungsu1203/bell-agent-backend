# ARCHITECTURE — bell-agent 구조 지도

> 이 문서 = **지도**. (규칙 = `CLAUDE.md` / 기록 = `README-dev-*.md` / 지도 = 이 파일)
> 목적: "이 프로그램이 무슨 문제를 어떤 구조로 푸는가"의 상위 조망.
> 갱신: 새 트랙이 끝날 때마다 해당 자리에 한 줄씩 추가하는 살아있는 문서.
>
> 작성: 2026-07-25 (세션 A — 1층·2층)
> 표기: ✅ = 명령으로 확인 / ◻︎ = 미확인·추정

---

## 0. 한 줄 요약

**ad(기획서)와 paper(논문)는 "공통 몸통 + 두 갈래"가 아니다.**
그래프 몸통은 ad만 갖고 있고, paper는 그 몸통을 **우회**해 아래층 부품만 공유하는 별개 줄기다.
설계가 아니라 **역사의 결과** — ad 도구를 논문에 재사용하려다 목적이 안 맞아 하나씩 떼어낸 흔적.

```
[🏢 ad 트랙]                        [📄 paper 트랙]
Next.js (별도 repo)
   │ HTTP (CORS :356)
app.py:541                          scripts/§paper-writer-1/measure_paper.py
   └ build_graph()                     └ 그래프 미사용 (import 0건 ✅)
        ↓                                    ↓
   graph.py — supervisor 단일 허브      agent.web_search.paper_section_fetch
        ↓ 8갈래 조건부 분기             agent.paper_section_writer
   9개 노드                                  ↓
        ↓ sections/<slug>/*.md         scripts/output/ + 측정(axis1/3, rank)
   report_builder.py (그래프 밖)
        ↓ reports/<slug>/latest.md

   └──── 공유: agent/web_search.py (한 파일, :1693 경계) · tools/ · Chroma · core/ ────┘
```

---

## 1층 — 능력 지도 (What)

### 🏢 ad 트랙
> **무엇을 넣으면** 클라이언트 실물 자료(refs/의 광고비 엑셀·팩트북 PDF·시장 규제 문서) + 웹검색
> **무엇이 나오나** 광고·마케팅 기획서/보고서 (섹션 단위 집필 → 단일 리포트 조립)

- 실적 ✅ (`sections/` 실물): **프로젝트 2건**
  · `venfobel-vitamin` — 종근당 벤포벨S 3C 분석. 섹션 + 통합본 완료 (71KB ✅ `app.py:1998` 주석 확인)
  · `height-growth-supplement-db-strategy` — 키 성장 보조제. **섹션만 존재, 통합본 미생성**
- 운용 방식: 대화형. supervisor에 지시 → 섹션별 생성 → `build: report`로 조립
- 자료 구조가 곧 분석틀: `refs/` 밑이 1.자사 광고비 / 3.경쟁자 / 4.소비자 = **3C**
- 프런트엔드 연동 ✅ — Next.js(`~/dev/bell-agent/bell-agent-frontend`, 별도 repo)에서 웹으로 열람. **paper엔 없는 층**

### 📄 paper 트랙
> **무엇을 넣으면** 토픽 문자열 하나 (`topics/<slug>.env`의 `TOPIC_QUERY`)
> **무엇이 나오나** 학술 논문 초고 (.md + .docx) + 품질 측정 리포트

- 현재 토픽: consumer perceived trademark similarity and likelihood of confusion
- baseline: references 89 (OA 60 + SS 29), axis1 = 1.0 PASS

### 축적된 능력 (catch로 쌓인 것)

**📄 paper 계열**

| 능력 | 근거 |
|---|---|
| 다중 학술 백엔드 (OpenAlex / Semantic Scholar) | §academic-1~5 |
| 백엔드별 쿼리 최적화 (OA=장쿼리 / SS=tail-only 단쿼리) | catch 74 |
| 비학술 오염 차단 (vertex skip) | catch 78 |
| venue 추출 4단 폴백 | catch 82 |
| 인용 마커 번호 정합 (섹션 간 feedback loop 차단) | catch 81 |
| 측정 인프라 표준화 (dry-run 게이트·warmup·timeout 공식) | catch 69/70/71 |
| seed reference 선주입 + 3단 verify 폴백 | catch 76/77 |

**🏢 ad 계열**

| 능력 | 근거 |
|---|---|
| 웹 UI 연동 (엔드포인트 12종 · 실시간 로그 스트리밍) | `app.py` |
| 아웃라인 사람 개입 (`PUT /api/outline`) | `app.py:1309` |
| 섹션↔출처 역추적 | `app.py:2134` |
| 재료 폴더 3단 폴백 · 원본 무수정 병합 | `report_builder.py` · catch 16 · §13-14-α |
| 덱 자동 생성 + 멀티 LLM 최적화 (gpt-4o 운영 기본) | §13-7 / §13-8 |

---

## 2층 — 파이프라인 지도 (How)

### 🏢 ad — 그래프 기반 (`graph.py`)

**진입점** ✅ `app.py` (FastAPI, 변수명 `web_app`)
- 그래프 조립: `app.py:541` → `build_graph()`
- 측정 하니스도 같은 함수 호출: `scripts/_phase_b_run_inner.py:220`, `scripts/_step3_dry_run_rag_update.py:208`

**엔드포인트 12종** ✅ = ad 트랙이 밖으로 내주는 능력 표면

| 묶음 | 엔드포인트 | 비고 |
|---|---|---|
| 실행 | `POST /api/run`(:1343), `POST /api/cancel`(:1271) | |
| 목차 | `GET /api/outline`(:1281), **`PUT /api/outline`**(:1309) | **사람이 아웃라인 직접 수정 = 개입 지점** |
| 산출물 | `GET /api/files`(:2035), `/api/files/{id}`(:2096) | |
| 근거 추적 | `GET /api/section-refs/{id}`(:2134) | 섹션↔출처 역추적 (RAG 투명성) |
| 내보내기 | `POST /api/export`(:1884) | → 조립 + 덱 생성 |
| 관측 | `GET /api/state`(:1231), `/api/logs`(:2167), `/api/events`(:2188), `/api/health`(:1195) | `:296` 로그 핸들러가 `report_builder` 로그를 잡아 스트리밍 |

**노드 9개** ✅ `graph.py:97~105`

| 노드 | 하는 일 | 산출 폴더 ◻︎추정 |
|---|---|---|
| `supervisor` | 라우팅 관제 (단일 허브) | — |
| `communicator` | 사용자 대화 응답 | — |
| `research_planner` | 조사 계획 수립 | `research/` |
| `web_search_agent` | 웹 검색 | `research/…resources_*.json` |
| `vector_search_agent` | Chroma 검색 (refs 문서) | `local/` |
| `research_synthesizer` | 수집물 종합 | `resources/` |
| `content_strategist` | 목차·전략 수립 | `outlines/` |
| `chapter_writer` | 장 단위 집필 | `sections/<slug>/` ✅ |
| `section_writer` | 절 단위 집필 | `sections/<slug>/` ✅ |

**흐름** ✅
- 입구: `START → supervisor` (`graph.py:108`). supervisor 꺼져 있으면 communicator로 대체
- `supervisor`가 8갈래 조건부 분기 (`:113~123`) — **모든 판단이 `supervisor_router` 한 함수에 집중**
- 고정 선로는 단 하나: `content_strategist → communicator` (`:125`)
- 라우터 5종: `after_planner_router`(:128) / `after_web_search_agent`(:138) / `after_vector_router`(:149) / `after_synthesizer_router`(:158) / `tail_task_router`(:167, :174)
- 출구: `communicator → END` (`:184`)
- **`report_builder.py`는 노드가 아님** ✅ — 조립은 그래프 **밖**에서 별도 수행

**RAG 파이프라인 상세** ✅ (`ad/README-dev.md` §3)

```
[수집]                 [변환] ingest_docs        [인덱싱] ingest_vector
web_search        →   • PDF: PyPDF2→pdfminer  →  • split 2,400자 / 겹침 150
local_rag (refs/)     • HTML: BeautifulSoup      • 콘텐츠별 최소 길이 필터
findings (자기참조)    • 5단계 fetch 폴백          • PPTX 인접 슬라이드 병합
                      • source+version 중복 검사  • XLSX 메타 요약 자동 생성
                                                 • Vertex 임베딩 768d (한국어 최적화)
                                                 • Chroma 3-tier (web/local/base)
```

**검색** (`agent/vector_search.py`): Direct QA 게이트 → 웹/로컬 비율 분배(`RETRIEVE_WEB_RATIO=0.5`) → 도메인 가중치 재랭킹(`topic_config.py`) → distance threshold → **무조건 base 폴백**(0-hit 방지)

**⚠️ 임계값 2종 — 층도 방향도 다름** ✅ (혼동 주의)

| 이름 | 기본값 | 방향 | 위치 |
|---|---|---|---|
| `DIRECT_QA_MIN_SCORE` | 0.35 | **점수 — 이상이면 통과** | `agent/vector_search.py:907` (판단층) |
| `RAG_DISTANCE_THRESHOLD` | 0.65 | **거리 — 이하면 통과** | `tools/web_rag/ingest_vector.py:1603` (엔진층) |

README §3은 둘을 한 묶음으로 서술하지만 **실제로는 다른 층**에서 작동. "agent=판단 / tools=실행" 분리의 실증.

**임계값은 실측 근거가 있음** ✅ — `diagnose_distance_threshold.py:46`(후보 7개 0.45~0.80 스윕) · `eval_embedding_models.py:66,392`(0.65 기준 precision/recall + 재조정 권장) · `threshold_sweep.py:53`(베이스라인 [0.600, 0.650] = "현 토픽 override + 글로벌 default"). 토픽별 override 체계(`topics/<slug>.env`)도 이 실측에서 나옴.

**Direct QA는 스위치 3종** (`:907~909`): `DIRECT_QA_MIN_SCORE` / `DIRECT_QA_ALLOW_DURING_RESEARCH`(True) / `DIRECT_QA_REQUIRE_SCORE`(True).
`:877~887` — **스모크 전패해도 `DIRECT_QA=True`면 중단하지 않고 진행**. base 폴백과 같은 "빈손으로 안 돌려보낸다" 사상.

**드롭 필터 4종** (인덱싱 전): `_is_block_page`(CAPTCHA) · `_looks_like_pdf_bytes` · `_looks_like_serialized_blob`(Next.js JSON) · **`_looks_like_garbled`**
> `_looks_like_garbled` = .hwp/.xlsx 등 한국식 바이너리가 HTML로 오분류돼 깨진 텍스트로 색인되는 것 차단. U+FFFD 비율 1% 초과 시 드롭 (정상 0% ↔ 깨진 것 40~50%). **한국 실무에서만 나오는 문제에 대한 방어막.**

**설계 사상 — 신뢰도별 자원 배분** (README §2)
> 웹 PDF 5페이지 / 10,000자 (보수적) ↔ 로컬 PDF 50페이지 (적극적)
> "웹은 잘 모르는 출처라 보수적, 로컬은 회사 신뢰 자료"

**조립 단계** ✅ `report_builder.py`

`section_writer`가 아웃라인 항목별로 `sections/<slug>/*.md`를 각각 저장 → `build_final_report()`(`:279`)가 **목차 순서대로 병합** → `reports/<slug>/<timestamp>_report.md` + `reports/<slug>/latest.md` 생성 (`:286~287`, `:349~355`)

- **재료 폴더 3단 폴백** (`:162~176`): `sections` → `content` → `chapters`.
  표준 저장 위치는 `sections/` (`:201` 주석 명시), 나머지는 하위 호환. catch 82 venue 폴백과 같은 패턴
- **`sections/*.md` 무수정 원칙** (`:233`, `:334` · §13-14-α): 제목 정규화(`_ensure_heading`, `_ensure_section_h2_normalized`)는 **in-memory에서만**. 원본 섹션 파일 불변
- findings 부록 자동 첨부 (`_collect_findings_paths`:113, `_build_findings_appendix`:138)
- **호출처 3곳, 전부 `app.py` (그래프 밖 확정)** ✅ — `:1127`(엔드포인트 앞 = 대화 명령 `build: report` 처리부 ◻︎추정), `:1975`(export 경로), `:2470`

**내보내기 단계 — §13 PPTX 트랙의 자리** ✅ `app.py:1884~2020`

**2축 구조**: `kind`(section|report) × `format`(docx|pptx). 단 **pptx는 `kind=report`만** (`:1960` — 섹션 단위 덱 v1 미정의). §13-12-1에서 분기 추가.

```
sections/<slug>/*.md → build_final_report → reports/<slug>/ → plan_deck → .pptx
        (LLM 0, 단순 병합)                     (LLM structured output 1회, 20~30s)
```

- `plan_deck` 실체 = **`agent/export/planner.py`** ✅ (`app.py:1956`) — `agent/` 하위 패키지, 3층에서 확인
- `:1998` 주석 "~20~30s for **venfobel 71KB**" → 벤포벨 리포트 71KB **코드 확인** ✅
- **§13-7/13-8 멀티 LLM PPTX 평가 트랙이 여기에 위치.** 운영 기본 gpt-4o(mean 35.3s) ↔ 주석 20~30s 정합
- 한글 파일명 ASCII 폴백 (`:2020`) — 실사용에서 겪은 문제 대응 흔적

**프런트엔드 접점** ✅
- `app.py:356~366` CORS — `allow_origins`는 **와일드카드 아닌 명시 목록**(`localhost:3000`, `127.0.0.1:3000`). `allow_credentials=True`면 규격상 와일드카드 금지라 강제된 설정
- `expose_headers=["Content-Disposition"]` — **덱/문서 다운로드 파일명 전달용**. 없으면 브라우저 JS가 파일명을 못 읽음. §13-12(프런트 pptx 다운로드 통합)의 산물
- 프런트는 **별도 repo** `~/dev/bell-agent/bell-agent-frontend` (2026-06-07 이후 미변경)
- **프런트도 `README-dev.md`를 가지며 백엔드와 같은 § 번호로 짝 진행** ✅ (`ad/README-dev.md:2464` "Frontend 짝 task (frontend/README-dev.md §13-12 참조)", `:2469` "Commit 시퀀스(양쪽 레포 짝 진행)", `:2531` §12-15-1 frontend 측)
  → 프런트 조사 시 백지 아님. 같은 § 체계로 이 지도와 대조 가능
- 엔드포인트 12종 = 사실상 **화면 기능 목록**: `PUT /api/outline`(목차 편집 UI) · `/api/events`+`/api/logs`(LogPanel, `core/events.py` §12-14) · `Content-Disposition`(다운로드 버튼) · `/api/section-refs`(출처 표시)
- 이 지도의 범위는 백엔드까지 — 프런트 내부 구조는 별도 세션

**⚠️ 동시성 제약 — 동시 실행 1건** ✅ `app.py:369`

```python
_RUN_LOCK = asyncio.Lock()   # 한 번에 한 요청만 그래프를 실행(상태 공유 + 안전)
```

원인: `core/topic.py:140~143`이 런타임에 **`os.environ`을 동적 변경**(`MIRROR_STATE_TO_ENV`). 환경변수는 프로세스 전역이라 동시 요청 시 서로의 토픽·네임스페이스를 덮어씀 → 락으로 직렬화.
`POST /api/cancel`이 필요한 이유도 이것(큐잉 불가 → 취소로 비움).

**두 트랙이 같은 문제를 다르게 해결**
| | 해법 |
|---|---|
| 🏢 ad | **락으로 직렬화** — 한 프로세스, 동시 1건 |
| 📄 paper | **프로세스 분리** — provider별 venv, 배치 실행 |

→ ad는 다중 사용자 서비스가 아니라 **1인용 내부 도구**로 설계돼 있음.

**노드 on/off 스위치** ✅ `graph.py:26~34` — `_EN_*` 9개, **전부 기본값 True**.
트랙 분기용이 아니라 **고장 격리·디버깅용 안전장치**. edge도 양끝 노드가 켜져 있을 때만 연결(`:71~94`).

### 📄 paper — 그래프 우회, 함수 직결

**진입점** ✅ 둘 다 `scripts/§paper-writer-1/` 안
- `measure_paper.py` — 본선 (논문 생성 + 측정)
- `refetch_abstracts.py` — 보조 (abstract만 full backfill → catch 83 dump 생성. OA/SS 재조회가 비결정적이라 스냅샷 고정용)

graph / build_graph / supervisor **import 0건** ✅

**의존** ✅ `measure_paper.py:154~155`
- `agent.web_search.paper_section_fetch` — 자료 수집
- `agent.paper_section_writer` — 섹션 집필
- (`common.academic_domains`:56, `dotenv`:100)

**흐름**
topic(.env) → 섹션별 fetch(OA/SS) → chunk 적재(Chroma) → writer 섹션 생성(previous_sections 누적) → 마커 shift → 측정(axis1/3, rank)

**import 배치가 곧 측정 표준** ✅
`measure_paper.py`의 import가 21~33 / 55~56 / 100 / 154~155 **네 덩어리로 흩어져** 있고 `# noqa: E402`가 붙어 있음.
이유 = `agent/` 모듈은 로드 시점에 환경변수를 읽으므로 **dotenv 로드·env 정리를 끝낸 뒤에야** import해야 함 (CLAUDE.md §6 / catch 69·71). **문서 규칙이 파일 구조로 굳은 자국.**

### 공유 지점 — `agent/web_search.py` (2,074줄) ✅

한 파일 안에 두 트랙이 동거하되 **경계가 코드에 선언돼 있음** — `:1693~1695` 주석 구분선
`# §paper-writer-1 Step C-2 — section-aware fetch (paper mode)` = **분기 시점까지 명시** ✅

| 라인 | 내용 | 소속 |
|---|---|---|
| 55~173 | 설정 헬퍼 (`_cfg_bool`, `detect_query_lang` 등) | 공용 |
| **181** | `web_search_agent(state)` — **약 1,470줄 단일 함수** | 🏢 ad |
| 1654~1678 | 게터 9종 (SerpAPI·Tavily·Google 키) | 🏢 ad |
| 1681~1690 | `__all__` — 외부 공개 명단 | 선언 |
| **1693** | ── 트랙 경계 주석 구분선 ── | |
| 1696~1977 | `section_to_query`, seed 적재, venue 보정 (함수 9개) | 📄 paper |
| **1989** | `paper_section_fetch` | 📄 paper |

**공개 표면(`__all__`)이 매우 작음** ✅ — 실질 함수 3개(`web_search_agent` / `section_to_query` / `paper_section_fetch`) + 게터 9개.
paper 내부 헬퍼는 전부 밑줄 접두어 = 비공개. **paper 블록은 입구 2개뿐인 닫힌 덩어리.**

**호출처** ✅ `paper_section_fetch`를 부르는 곳 = `measure_paper.py:254`, `refetch_abstracts.py:89` **둘뿐**.
ad 경로(`app.py`·`graph.py`·`agent/` 기타)에서의 호출 **0건** → paper 전용 확정.

- 명명 규칙: **`paper_` 접두어 = paper 전용**, 없으면 ad
- catch 74/78 diff 모두 1962~1990 구간에만 국한 ✅ — ad 무접촉
- ⚠️ **ad 쪽은 함수 하나짜리 덩어리, paper 쪽은 잘게 분해됨.** ad가 파악하기 어려운 구조적 이유가 여기 있음

### vertex 계보 — 두 트랙이 갈라진 서사

```
① vertex_search = ad가 쓰던 웹검색 도구
② paper에도 그대로 재사용 시도
③ 실패 — 학술 논문 대신 로펌 홍보페이지 등을 회수해 References 오염
④ 차단 (catch 78, 2026-07-05) → References 169→77, 껍데기 −92, 학술 100%
⑤ 학술 전용 백엔드(OpenAlex/Semantic Scholar)로 전환
```

vertex 켜기 판단 방식도 갈림:
- 🏢 ad = `detect_query_lang`(:112) 기반 자동 판단 (catch 43 — EN 쿼리 → vertex 자동 활성)
- 📄 paper = 플래그 하나로 확정 (`SKIP_VERTEX_SEARCH`) — **일부러 덜 똑똑하고 더 확실한 쪽 선택**

---

## 3층 — 모듈 지도 (구조)

> 세션 B 착수분. `ad/README-dev.md` §1·§3·§4 + 실물 확인 대조.

### 층 구조 (5층)

```
utils/   순수 헬퍼, 외부 I/O 없음 (10파일)
  ↑
tools/   실제 엔진 — 검색·수집·적재 (25파일, 12,986줄) ★무게중심
  ↑
agent/   LangGraph 노드 껍데기 (1노드 1파일, 16파일)
  ↑
core/    설정·타입·라우팅 제공 (9파일)
graph.py / app.py / report_builder.py   조립·진입
```

**의존 방향 규칙** (README §1, 순환 금지)
```
utils → tools → agent
        ↑       │
        └── core┘
```
- `agent/*` ↔ `agent/*` 직접 import **금지** (라우팅은 `core/routers.py`로만)
- `tools/*`는 `utils/*`와 `core.config`만 참조
- `tools/web_rag/*` 내부끼리는 **지연 import**로 순환 회피

### tools/ 무게중심 ✅

| 파일 | 줄 | 하는 일 |
|---|---|---|
| `web_rag/ingest_vector.py` | 1,897 | Chroma 인덱싱·검색 본체, 임베딩 |
| `web_rag/search.py` | 1,889 | 웹 검색 백엔드 (Naver/Tavily 등) |
| `web_rag/utils.py` | 1,782 | URL 정규화, 텍스트 가드 |
| `local_rag.py` | 1,656 | **로컬 파일 인제스트 (.pdf/.pptx/.xlsx) = refs/ 처리** |
| `web_rag/ingest.py` | 871 | PDF/HTML 로더, 5단계 fetch 폴백 |
| `web_rag/ingest_docs.py` | 722 | 검색결과 → Document 변환 |
| 진단·평가 7종 | ~1,750 | `metrics` `threshold_sweep` `eval_embedding_models` `diagnose_*` |

**상위 6개 = 8,817줄(68%).** `agent/`는 얇은 노드층, `tools/`가 실제 엔진 — 가설 확정.

### agent/ — 1노드 1파일 ✅

노드 9개 ↔ 파일 9개 정확히 대응. 추가로:
- `paper_section_writer.py` — 📄 paper 전용
- `export/` 5파일 — `spec.py`(슬라이드 데이터 모델) → `planner.py`(LLM 설계) → `renderer.py`(pptx 출력) + `cli.py`(단독 실행) + `__init__.py`

### ⚠️ 파사드 규칙 위반 (핵심 정리 대상)

README §4 규칙:
> `tools/web_rag/__init__.py` 파사드만 사용. 내부 모듈(`ingest*.py`) 직접 import 금지.

**실제로는 위반이 광범위** ✅ (grep 확인)

| 구분 | 사례 |
|---|---|
| ✅ 준수 | `vector_search.py:35` — `from tools.web_rag import (...)` 묶음 import |
| ⚠️ 중복 | `vector_search.py:66` — `retrieve` 재import. `:35`에 이미 포함. 동작 무해, 정리 대상 |
| ❌ 내부 모듈 직접 | `web_search.py:29/30/43` |
| ~~❌ 오분류~~ → ✅ 해소 | `settings_gatekeep.py:24`·`vector_search.py:48` — `normalize_url` 정의는 `tools/web_rag/utils.py:1199` **단일 지점**. `rag_utils`에 없음 → 위반 아님, README §4 서술 오류였음 (`b6fc2e41` 정정). `debug_docid.py:1`은 구/신 docid 비교 시뮬레이터 = 정당한 예외 |
| ❌❌ **비공개 함수 직접** | `_default_chroma_dir` ← agent 4파일(`research_planner:25`/`research_synthesizer:22`/`supervisor:34`/`web_search:46`) + `tools/diagnose_*` 4 + `scripts/_phase_b_*` 2 = **총 11파일 / 진입 경로 3종** ✅ (기존 "5곳"은 과소집계) |
| ~~❌ 신규 백엔드 우회~~ → ✅ 해소 | `web_search.py:882` 파사드 경유 전환 완료 (A9-③). paper 블록 `:1829`/`:1994~1995`는 A8 대기 |

**원인 추정**: 파사드는 ad 시대 규칙. §academic에서 OA/SS 백엔드를 추가하며 **파사드 `__init__.py`를 갱신하지 않고 직접 import로 우회**. 규칙이 틀린 게 아니라 **확장이 규칙을 따라잡지 못한 상태**.
→ "구조가 얽혀 보이는" 체감의 실제 원인. 정리 방향(-> 아래 A9 완료 참조)

**✅ A9 완료 (2026-07-26)** — 커밋 `3f9aac45`(①②) / `f7375f45`(③)

| 단계 | 내용 | 검증 |
|---|---|---|
| ① | `openalex_search`·`semantic_scholar_search` 파사드 등록 | `__all__` 12개 ✅ |
| ② | `default_chroma_dir` 공개판 신설, 밑줄판 별칭 유지 | `is` 동일성 True ✅ |
| ③ | `agent/web_search.py:882` ad 호출부 파사드 경유 | py_compile / 인자 무변형 ✅ |

- **PEP 562 불필요** — 파사드가 이미 함수 내부 지연 import 방식이었음. 집 스타일 그대로 확장
- **지연성 실측** ✅ 파사드 import 시 `sys.modules` = `['tools.web_rag']` 뿐. catch 69/71 재발 경로 없음
- **부수 효과**: ③으로 백엔드 **부분 성공** 가능해짐. import 실패가 워커 → `fut.result()`로 이동해
  `:894` 백엔드별 `except`가 잡음 (이전엔 fan-out 통째 스킵). **정상 경로 동일, 실패 모드만 변경**
- **stale 물증** ✅ 파사드 커밋 이력 2건·최종 2026-03 → 백엔드 수정 6~7월. "확장이 규칙을 못 따라잡음" 확정

**잔여** — ② 소비자 11파일 전환(별칭이 받쳐 급하지 않음) / **✅ 규칙 3분류 명문화 완료 (2026-07-26, `b6fc2e41`)** — `ad/README-dev.md` §4 재작성. (a) 교체 대상 / (b) 정당한 예외 / (c) 의도적 회피 + "확장 시 규칙"(파사드 등록 선행, PEP 562 금지 사유) 신설. 부수 정정 2건: 공개 API 목록 8→11개, `rag_utils` "URL 정규화 단일 구현" 서술 오류.

### ⚠️ ENV 규칙 위반 (기존 발견과 연결)

README §2 규칙: "다른 모듈에서 `os.getenv` 직접 호출 금지 → `core.config CFG` 사용"
- `tools/web_rag/vertex_search.py:112` — `os.getenv("LLM_MODEL")` 직접 (§14-3 발견)
- `core/topic.py:140~143` — 런타임에 `os.environ` 동적 변경 (`MIRROR_STATE_TO_ENV`)
- `utils/rag_utils.py:542~555` — `_truthy` / `_get_bool` env 파싱 **별도 구현**. catch 71(`_env_flag` truthy 파싱 함정, "false"를 True로 읽음)과 같은 계열 → A10 진입 시 `core.config`와 파싱 규칙 일치 여부 확인 필요

### ~~README-dev.md stale 목록~~ → ✅ A11 완료 (2026-07-26, `310c4a80`)

경로(`D:\GPT_AGENT\` → `~/dev/bell-agent/bell-agent-backend/`) · 없어진 폴더 3종 · 노드 토글 5→9 · vertex 주석 · venv 목록 실측 반영. **명세표 자체에 오류 3건 있었음** — ① 정정 경로가 `~/dev/bell-agent/`로 한 단계 짧았고 ② 토글 축약 표기(`PLANNER`/`SYNTH`)가 실제 env 이름(`ENABLE_RESEARCH_PLANNER`/`ENABLE_RESEARCH_SYNTHESIZER`)과 달라 `graph.py:26~34` 재실측 필요 ③ "`agent/` 목록 누락"은 오판 — `export/` 5파일은 README `:1439~1446`에 표로 문서화돼 있음, 누락된 건 `:65` 트리 그림뿐. 미반영 1건: `paper_section_writer.py` 언급 0건 — 다만 본 문서가 `ad/` 전용이므로 paper 파일 부재는 누락이 아닌 범위 밖일 수 있음, 판단 보류.

---

## 부록 A - 정리 대상 목록

| # | 항목 | 상태 |
|---|---|---|
| A1 | **`refs/` 13개 tracked** — 종근당 실물 자료(광고비 xlsx·팩트북 PDF)가 git 이력에 존재. `.gitignore`에 `refs/` 규칙 없음. `topics/*.env`는 "NDA/client assets"로 막았으면서 refs/는 누락 | 부분 처리 — 로컬 삭제 완료(백업 보유). git 이력 세탁은 미결, 단독 트랙 |
| A2 | **`scripts/output/` 규칙 위반 5건** — `c_paper_measurement.json`, `smoke_*.log` 2건, `paper_…influencer_marketing….docx/.md`. 원인 = ignore 규칙(§14-2)보다 **먼저 추적 시작**된 파일. `git rm --cached`로 해소 | ✅ 완료 (2026-07-26) — .gitignore 규칙 재작성 + rm --cached 5건. 진단이 지목한 5건은 정확했으나 **규칙 자체가 자기모순** 상태였음: `scripts/output/` 디렉토리 통째 차단이 앞선 negation 설계를 덮어 `c_ab_results.json` 박제 예외와 `.md` 요약 추적이 죽어 있었음. 확장자+이름패턴 방식으로 전환 |
| A3 | **CLAUDE.md §8 시간 모순** — "77은 catch 78 직후 stale, 이후 catch 74가 늘림"이라 서술. 실제 git 날짜는 catch 74(7/4) → catch 78(7/5) **역순**. 77은 catch 74 적용 후 잰 값이며 커밋 메시지상 원인은 **SS 429 flaky**. catch 번호 ≠ 시간순 | ⚠️ 정정 필요 |
| A4 | `agent/web_search.py`에 CRLF(`^M`) 혼입 — 2026-07 추가분만 윈도우식 줄바꿈 | 청소 — A9-③ 편집으로 추가 오염 없음 확인 ✅ |
| A5 | `.gitignore` 이원화 — 루트/writer_project 중복 다수. 특히 **`data/`**: 루트는 통째 무시, writer_project는 하위 2개만 의도 → 루트가 이겨 의도와 실제 불일치 | 정리 |
| A6 | writer_project/.gitignore 1~9줄 = `chap14-6`, `chap14_8` 등 **타 프로젝트 화석** (현 repo에 미존재). `*.pptx` 중복 | 삭제 |
| A7 | 구조 파악용 텍스트 파일 6종 누적 (`folder_tree.txt`, `structure*.txt`, `repo_tree.txt`, `gpt_agent_full_structure.txt`) | 정리 |
| A8 | `agent/web_search.py` 트랙 분리 — **난이도 낮음**. 경계 주석(`:1693`) 아래를 통째로 `paper_search.py`로 분리하고 import 2줄 수정이면 됨. 공개 함수 2개·호출처 2곳뿐. 공유 헬퍼(`:55~173`) 처리 방식만 결정 필요 | 후보 |
| A9 | **파사드 규칙 위반** — README §4는 `tools/web_rag/__init__.py`만 쓰라는데 내부 모듈·비공개 함수(`_default_chroma_dir`) 직접 import가 광범위. §academic 신규 백엔드(OA/SS)가 파사드를 우회. **"구조가 얽혀 보이는" 체감의 실제 원인** | ✅ 완료 (2026-07-25) — 잔여: ② 소비자 11파일 전환 · 규칙 3분류 명문화는 2026-07-26 `b6fc2e41` 완료 |
| A10 | `os.getenv`/`os.environ` 직접 호출 금지 규칙(README §2) 위반 3건 — `tools/web_rag/vertex_search.py:112`(`LLM_MODEL`), `tools/web_rag/ingest_vector.py:1603`(`RAG_DISTANCE_THRESHOLD`), `core/topic.py:140~143`(런타임 `os.environ` 변경). ⚠️ topic.py가 런타임에 env를 바꾸는 상태에서 직접 읽기가 섞이면 **읽는 시점에 따라 값이 달라짐** — `_RUN_LOCK`이 필요한 이유와 같은 뿌리 | 정리 |
| A11 | `ad/README-dev.md` stale — 윈도우 경로, 노드 토글 5개(실제 9개), 없어진 폴더(`chapters/` `safe_code/` `state/`) 기재, vertex 주석·venv 목록 | ✅ 완료 (2026-07-26, `310c4a80`) — 명세표 자체 오류 3건 발견, 상세는 3층 참조. 미반영: `paper_section_writer.py` (범위 밖 가능성, 판단 보류) |

**해제된 우려**: catch 74/78이 ad에 영향을 줬을 가능성 → diff 확인 결과 **paper 구간(1962~1990)만 수정, ad 경로 무접촉** ✅ 기각.

---

## 부록 B — 미확인 항목 (다음 세션 확인 대상)

- ◻︎ `utils/` 10파일 내부 구조 (3층 미조사분)
- ◻︎ `agent/export/` 5파일 상세 (spec/planner/renderer/cli 역할 분담)
- ◻︎ docx 내보내기를 두 트랙이 공유하는가 (paper도 .docx 산출)
- ◻︎ `app.py:1127` 호출 맥락 — 대화 명령(`build: report`) 처리부인지
- ◻︎ `height-growth-supplement-db-strategy`가 통합본 없이 남은 이유

**해소됨** (2026-07-25)
- `paper_section_fetch` 호출처 → `measure_paper.py:254` · `refetch_abstracts.py:89` 둘뿐, ad 호출 0건 ✅
- `build_final_report` 호출처 → `app.py:1127/1975/2470`, 그래프 밖 확정 ✅
- FastAPI 엔드포인트 12종 확보 ✅ (변수명은 `web_app`)
- `plan_deck` 위치 → `agent/export/planner.py` ✅
- **Chroma 3-tier(web/local/base) 확정** ✅ — `CHROMA_NAMESPACE_WEB`/`_LOCAL` 둘 다 설정 시 split mode, `CHROMA_INCLUDE_BASE`
- **`agent/`가 얇은 노드층, `tools/`가 엔진층** 확정 ✅ (12,986줄)
- **ad 트랙 품질 측정축 존재 확정** ✅ — `metrics.py`(578) · `threshold_sweep.py`(515) · `eval_embedding_models.py`(460, precision/recall) · `diagnose_distance_threshold.py`(후보 7개 스윕) · `sample_chunks_for_eval.py`(골드셋 샘플링) · `diagnose_*` 5종. **paper 측정 인프라(catch 69~71)는 이 위에 얹힌 것**

**정정** (2026-07-25)
- 이전 기록에서 "SS는 ad가 안 쓰는 학술 백엔드"라 서술 → **틀림**. `web_search.py:882~883`(= `web_search_agent` 내부)도 OA/SS를 호출. 단 catch 74/78 판정(ad 무영향)은 diff 구간 기준이라 유효
- ◻︎ Chroma 네임스페이스 3종(base/web/local) 현행 여부 — 2026-05 대화 기록 기반
- ◻︎ `§12-13` 결함 8건 현행 여부 (특히 §12-13-5 — 한국어 자연어 write 의도 라우팅 실패, `write:` 접두어로만 동작 7/7. **supervisor 단일 허브 구조상 단일지점 고장**)
- ◻︎ `prompts.py`를 두 트랙이 공유하는가
- ◻︎ paper 진입점 2개가 `§paper-writer-1`(사이클 폴더) 안에 있음 — 정식 위치인가, 이동 대상인가

**해소됨**: `paper_section_fetch` 호출처 → `measure_paper.py:254` · `refetch_abstracts.py:89` 둘뿐, ad 호출 0건 ✅ (2026-07-25)

---

## 부록 C — 트랙 연대기 (4층 재료 · 세션 C용)

`scripts/output/` 폴더 이름이 곧 연대기:

```
§12-13   ad 결함 큐 8건 (supervisor 라우팅·communicator 오염 등)
  ↓
§14-3~9  vertex·웹검색 인프라 (검색 계층 정비)
  ↓  ★ 여기가 ad → paper 분기점
§academic-1~5   학술 백엔드 도입 (OA/SS)
  ↓
§paper-writer-1~2   논문 생성·측정
```

`.gitignore` 주석도 같은 연대기를 기록 중: `2026-05-13 NDA 인식` → `§academic-1` → `§14-2/14-3` → `§14-8` → `catch 83`.
