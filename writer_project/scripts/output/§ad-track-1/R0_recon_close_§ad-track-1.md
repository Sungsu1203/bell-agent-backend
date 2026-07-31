# §ad-track-1 계단 0~1 정찰 close — ad 트랙 / 체험마케팅 토픽

- 일자: 2026-07-31
- 목적: ad 트랙을 실제로 돌려보며 파이프라인 이해 + 홍익대 15주 강의자료 확보
- 범위: 계단 0(정찰) · 계단 1(토픽 env 작성). 유료 API 호출 0건.
- 결과: 정찰 종료. 계단 2 STOP 게이트 앞 대기.

---

## 1. 환경 기준선

| 항목 | 값 | 근거 |
|---|---|---|
| repo | `~/dev/bell-agent/bell-agent-backend/writer_project` | CLAUDE.md |
| venv | `../.venv_vertex/bin/python` (macOS 정상) | CLAUDE.md §3 |
| branch | `main` (논문 트랙 잔여 수정분 존재) | `git status` |
| LLM provider | `openai` / `gpt-4o` | `.env:2-3` |
| 임베딩 | `text-embedding-3-large` (3072d) | `.env.openai:35` |
| 거리 공간 | `l2` (squared) — 미지정 → Chroma 기본값 | `ingest_vector.py:323`, `collection_metadata` 0행 |
| 거리 임계 | `1.10` | `.env.openai` |
| chroma 루트 | `data/chroma_store/` (NS별 하위 디렉토리) | 실측 11M |

### 기존 인덱스 실측 (견적 기준선)

| 컬렉션 | 벡터 수 |
|---|---|
| `venfobel-vitamin` (base) | 0 |
| `venfobel-vitamin-web` | 47 |
| `venfobel-vitamin-local` | 810 |

`venfobel`은 `LOCAL_RAG_GLOBS` override가 없어 `refs/` 전체를 인덱싱한 결과.
우리 토픽은 12개 파일만 대상 → **100~250 청크 예상.** 계단 2 dry-run에서 검산.

---

## 2. 파이프라인 구조 (확정)

### 2.1 ad 트랙 진입점

- 실행 = `app.py` (FastAPI) + **자연어 명령 정규식 fast-path**
- RAG 업데이트 트리거 (`agent/supervisor.py:608-619`):
  ```
  (최신|업데이트|update|latest).*?(자료|리소스|레퍼런스|참고|sources|material).*?(rag|벡터|vector|임베딩|embedding|index|색인|chroma)
  ```
- **3단어가 이 순서대로** 있어야 발동. `DOTALL` 없음 → 줄바꿈 금지.
  - `최신 자료로 RAG 업데이트` ✅
  - `RAG 업데이트` ❌ ('자료' 누락)
- 매칭 시 `Task(agent="web_search_agent", description="rag_update:auto")` 등록

### 2.2 로컬 색인 경로

- `ingest_local_files()` = `tools/local_rag.py:1370`
- 호출 지점 = `agent/web_search.py:1235` (**웹검색 노드 내부**, 토픽별 1회 가드)
- 시그니처:
  ```python
  ingest_local_files(globs, namespace, persist_directory, topic_slug, root_dir,
                     add_web_pages_json_to_chroma=None,   # 파사드 주입
                     web_page_json_to_documents=None)
      -> (out_json_paths, docs_preview, chunk_total)
  ```
- **인덱싱 게이트 = `local_rag.py:1562`**
  `if add_web_pages_json_to_chroma is not None:` → **None이면 임베딩 호출 0, `chunk_total=0`**
  → 무료 dry-run 성립

### 2.3 파일 수집 동작

- `build_webjson_from_local()` (`~1191`), `glob.glob(g, recursive=True)` (`:1223`)
  → `**`가 **디렉토리 0개도 매칭** → 루트 파일도 잡힘 (컨테이너 재현 검증 완료)
- 중복 제거: `sorted({...})` set 기반
- 우선순위 정렬: `findings.md > PDF > PPTX > XLSX > 기타(docx·md)`
- cap: `LOCAL_RAG_MAX_FILES` → `LOCAL_MAX_FILES` → 기본 1500 (12개이므로 무관)
- **파싱 캐시**: `_cache_load/_cache_save`, mtime+size 동일 시 재파싱 스킵
  → dry-run이 본실행을 느리게 만들지 않음
- 인덱싱 직전 통계 로깅 (`:1428~1465`):
  ```
  [LOCAL RAG][stats] items=N avg_chars=.. p50=.. p90=.. min=.. max=..
  [LOCAL RAG][stats] by_content_type: pptx:6, md:3, ...
  ```

### 2.4 임베딩 결정 로직 (2중 스위치 — 세트로 움직여야 함)

| 결정 대상 | 결정 주체 | 코드 |
|---|---|---|
| 생성자(ctor) | `LLM_PROVIDER` | `core/llm.py:90`(openai) / `:146`(vertex) |
| 모델명 | `RAG_EMBEDDING_MODEL` > provider별 > 기본 | `core/llm.py:436` |

- **서로 검증하지 않음.** provider=openai에 vertex 모델명을 넣으면 존재하지 않는 조합이 생성됨.
- 싱글턴 캐시 `_EMB` (`:420-424`) → **프로세스당 1개 고정.** 계단 2/3은 별도 프로세스로 분리 (STANDARDS §3).
- 검증 로그 (`:447`):
  ```
  [Embeddings] provider=openai | Model=text-embedding-3-large (Override: Yes)
  ```

### 2.5 거리 임계 정합

정규화 벡터에서 `squared L2 = 2 − 2·cos θ`.

- `1.10` → `cos θ = 0.45`
- cosine 환산 `1.10 ÷ 2 = 0.55` → `.env.openai` 주석의 마이그레이션 계획값 `0.5~0.6`과 일치 ✅
- 실측 분포 (venfobel, 2026-05-07, 10쿼리×top10):
  | | min | p25 | median | p75 | p90 | max |
  |---|---|---|---|---|---|---|
  | local(349) | 0.523 | 0.899 | 1.046 | 1.142 | 1.364 | 1.414 |
  | web(61) | 0.800 | 1.129 | 1.233 | 1.309 | 1.439 | 1.505 |
- 임계별 통과율: `0.95` → local 26 / **web 0** (무한 루프 원인) · `1.10` → local 68 / web 21 (권장) · `1.20` → local 81 / web 42 (노이즈)
- **글로벌 `.env:153`의 `0.65`는 vertex 768d 시절 값.** 3-large 공간에선 local 5% / web 0% 수준 → 사용 금지.

### 2.6 ENV 4-layer (STANDARDS §1.1)

로드 순서: **L4**(script) → **L1**(글로벌 `.env`) → **L2**(`.env.{provider}`) → **L3**(`topics/{TOPIC_SLUG}.env`)

- L2/L3는 `override=True` → 나중에 로드되는 L3가 최종 승자
- **L3 활성 조건: `os.environ["TOPIC_SLUG"]` 가 set 되어야 함** (`state.topic_slug`만으론 미작동)
- overlay 파일명 매핑: `core/config.py:116` — `vertexai` → `.env.vertex` (의도된 축약, 불일치 아님)

---

## 3. 핵심 위험과 방어

### 3.1 provider overlay가 NS를 납치 (실재 · 방어 완료)

- NS 자동 파생 = `core/config.py:443-456`, **값이 비었을 때만** 작동
- `.env.openai:56-58` 이 `venfobel-vitamin-oa*` 로 채움 → 자동 파생 무력화
- 방어 없이 실행 시 **강의자료가 종근당/벤포벨 인덱스에 혼입**
- → 토픽 `.env`에 NS 3줄 명시 (L3 > L2)

### 3.2 임베딩 공간 의존 3키 — 토픽에서 덮으면 안 됨

`.env.openai` 가 세트로 관리 중:

| 키 | 값 | 덮었을 때 |
|---|---|---|
| `RAG_EMBEDDING_MODEL` | `text-embedding-3-large` | ctor와 불일치 |
| `RAG_DISTANCE_THRESHOLD` | `1.10` | 0.65 덮으면 web 0% 통과 → 무한 루프 |
| `SKIP_VERTEX_SEARCH` | `0` | 별도 판단 필요 (§4 미결) |

**규칙: 임베딩 공간에 묶인 파라미터(모델·차원·거리임계)는 provider 계층이 관리한다.**

### 3.3 `refs/` 전체 흡수 (방어 완료)

- 글로벌 `LOCAL_RAG_GLOBS=refs/**/*` → 종근당·벤포벨 자료까지 포함
- → 토픽에서 `refs/experiential-marketing/**` 로 좁힘
- **이 override는 전례 없음** (`topics/*.env` 어디에도 이 키 없음) → 계단 3에서 실효성 검증 필요

### 3.4 보안 감사 (STANDARDS §5.1) — 통과

| 검사 | 결과 |
|---|---|
| tracked `.env*` | `.env.openalex.example`, `.env.semanticscholar.example` (example만) ✅ |
| `.env.bak_20260730` | `writer_project/.gitignore:67` `*.bak_*` 로 차단 ✅ |
| `.env.vertex/.anthropic/.openai` | `.gitignore:17` `.env.*` 로 차단 ✅ |

실키 노출 0건. rotation 불요.
부수 관찰: ignore 소스가 루트/`writer_project` 두 파일로 분산 — CLAUDE.md §4의 줄번호 지목 시 파일 명시 필요.

---

## 4. 자료 현황과 커버리지 갭

`refs/experiential-marketing/` — 12개 파일 (+ `.DS_Store`)

| 주차 | 자료 | 상태 |
|---|---|---|
| 1 | `1982_Holbrook.pdf`, `체험마케팅_1주차_강의초안.pptx` | ✅ |
| 2 | `week2_experience_economy.pptx`, 경험경제 md 2건 | ✅ |
| 3 | `week3_schmitt_sem_lecture.pptx` + `_note.docx`, `sem_expros_grid.pptx` | ✅ |
| 4 | `wundt_curve_slide.pptx` (감각 모듈 배정 확정) | ✅ |
| 12 | `week12_brakus_..._note.docx`, `brand_experience_scale_survey_items.xlsx` | ✅ |
| **5~11, 13~15** | **없음** | 🔴 **10주 공백** |

**함의**: 로컬 RAG는 기존 4~5주치를 "기억"하는 용도. **나머지는 계단 3(웹 수집)이 처음부터 생성해야 함.**
→ 이번 사이클의 무게중심은 계단 2가 아니라 계단 3.

### 15주 편성 (설계표 기준)

| 파트 | 주차 | 내용 |
|---|---|---|
| 도입 | 1–2 | 홀브룩·허쉬만(1982) → 파인·길모어 4E |
| **SEM 핵심** | **3–9** | 개관(3)·감각(4)·감성(5)·인지(6)·행동(7)·관계(8)·통합(9) |
| 응용·확장 | 10–13 | 디지털/숏폼(10)·측정/여정/플로우(11)·Brakus 척도(12)·공간/팝업/phygital(13) |
| 종합 | 14–15 | 팀 발표(14)·발표+AI/VR 미래(15) |

- **F열(오성수 실무 사례)은 RAG로 채울 수 없음** — 벨컴/디트라이브 내부 자산. 직접 작성 필요.
- **E열(붙일 미디어 사례 유형)이 계단 3의 실제 타겟.**

### 계단 3 성공 기준 (사전 정의)

> E열 15칸에 붙일 **구체적 사례(브랜드명 + 캠페인명 + 연도)** 확보.
> "그럴듯한 일반론"이 나오면 실패로 판정한다.

---

## 5. 계단 1 산출물

`topics/experiential-marketing-media.env` — 유효 키 8개 + objective 5

| 키 | 값 | 근거 |
|---|---|---|
| `TOPIC_TITLE` | 체험마케팅과 미디어 콘텐츠 | — |
| `TOPIC_SLUG` | `experiential-marketing-media` | 논문 트랙 slug와 충돌 없음 |
| `CHROMA_NAMESPACE` ×3 | `experiential-marketing-media{,-web,-local}` | §3.1 방어 |
| `LOCAL_RAG_GLOBS` | `refs/experiential-marketing/**/*.{pdf,pptx,docx,md,xlsx}` | §3.3 방어 |
| `RETRIEVE_WEB_RATIO` | `0.65` | §4 커버리지 갭 대응 (전례 없음, 실측 후 조정) |
| `BLOCKAGI_OBJECTIVE_1~5` | 주차 비중 반영 배분 | 1→1-3주, 2→4-5, 3→6-9, 4→11-12, 5→10·13·15 |

**의도적으로 제외한 키**: `RAG_EMBEDDING_MODEL`, `RAG_DISTANCE_THRESHOLD`, `SKIP_VERTEX_SEARCH` (§3.2)

설계 초안 대비 3키 축소. **오버레이가 이미 관리하는 것은 건드리지 않는다**가 결론.

---

## 6. catch 후보 (사이클 close 시 정식 등재)

| # | 내용 |
|---|---|
| A | **provider overlay가 NS·임베딩모델·거리임계를 세트로 관리** — 토픽 프리셋이 그중 하나만 덮으면 세트 파손. NS 자동 파생(`config.py:443`)도 overlay가 값을 채우면 무력화됨. |
| B | **로컬 색인이 `web_search` 노드에 종속** (`web_search.py:1235`) — 독립 실행 경로 없음. `ENABLE_WEB_SEARCH=0` 시 로컬 색인도 동반 중단. `ingest_local_files()` 직접 호출로만 분리 가능. |
| C | **`LOCAL_RAG_GLOBS` 토픽 override 전례 0건** — README-dev.md:1275가 "자연 검증 예정"으로 남겨둔 항목. 본 사이클이 첫 케이스. |

---

## 7. 미결 항목

| # | 항목 | 결정 시점 |
|---|---|---|
| 1 | **vertex on/off** — 현재 overlay가 ON(`=0`). 근거 필요: (a) `tools/web_rag/vertex_search.py` 과금 구조·인증 요건, (b) catch 78(벤더 껍데기 참조 오염)이 한국어 토픽에서 재현되는지, (c) 한국어 grounding 실측 (STANDARDS §2.2 경고) | 계단 3 진입 전 |
| 2 | **`RETRIEVE_WEB_RATIO=0.65` 실효성** — web은 임계 1.10에서 21%만 통과. 비율을 올려도 실제 충족량은 제한적일 수 있음 | 계단 3 실측 후 |
| 3 | **xlsx 키워드 튜닝 불일치** — `topic_config.py` 기본값이 매출·판매 등 영업 데이터용. 강의설계표·설문문항표에는 부적합 | 계단 2 통계 확인 후 |
| 4 | **우선순위 정렬 편향** — `docx`·`md`가 "기타"로 최하위. 우리 자료 중 밀도 높은 강의노트가 여기 해당 (cap 미적용이므로 이번엔 무해) | 관찰만 |

---

## 8. 정찰 중 발생한 오류 기록 (재발 방지)

| 오류 | 원인 | 교훈 |
|---|---|---|
| `data/chroma_store/chroma.sqlite3` 빈 파일 생성 | `chromadb.PersistentClient(path=)`는 없으면 생성 | 기존 DB 조회는 `sqlite3` 직접 읽기 |
| 마스킹이 필요한 값을 가림 | `sed` 기준이 "8자 초과"(길이)였음 | 마스킹은 **키 이름** 기준, 또는 `cut -d= -f1`로 값을 아예 안 뽑기 |
| 임계 `0.65` 초안 삽입 | 글로벌 `.env`만 보고 overlay 미확인 | **토픽에 쓸 모든 키는 overlay 존재 여부 먼저 확인** |
| "NS 자동 파생이라 명시 불요" 판정 | 자동 파생의 발동 조건(값이 빔) 미확인 | 조건부 로직은 조건까지 읽는다 |
| "vertex는 Gemini 종속" 판정 | STANDARDS §2.1의 *분류명* 정의를 *호출 경로*로 오독 | 결과물 분류 ≠ 실행 경로 |
| glob 루트 파일 보험 줄 추가 | Python `**`가 0-디렉토리 매칭함을 미확인 | 동작 불확실 시 재현 테스트 먼저 |

---

## 9. 다음 단계

**계단 2 (STOP 게이트 앞)**

- 2-a: dry-run — `add_web_pages_json_to_chroma` 미주입. **API 비용 0.** 디스크 쓰기는 발생(`research/<slug>/resources/*.json`)
- 2-b: 실인덱싱 — 승인 후. 예상 $0.05 내외 (`text-embedding-3-large` $0.13/1M tokens)

**2-a 판정 기준 4종**

1. `Pattern ... matched N files` → 파일 12개 (13이면 `.DS_Store` 유입)
2. `[LOCAL RAG][stats] items=N` → 100~250 (3000이면 glob 오작동)
3. `by_content_type` 분포 → pptx 과대대표 여부
4. `chunk_total == 0` → **유료 미발생 증거**

추가 검증: `[Config] 토픽 프리셋 로드` 메시지 + `[Embeddings] provider=openai | Model=text-embedding-3-large (Override: Yes)` (STANDARDS §1.5 env capture evidence)
