# §ad-track-1 계단 2 close — 로컬 색인 + 검색 확인

- 일자: 2026-07-31
- 범위: 계단 2 (로컬 자료만 색인 → 검색 확인)
- 결과: **PASS.** 302청크 인덱싱, 검색 정확도 확인, 오염 0
- 누적 비용: 임베딩 4회 실행 **3센트 미만**
- 선행 문서: `R0_recon_close_§ad-track-1.md` (계단 0~1)

---

## 1. 최종 상태

### 1.1 인덱스

| 항목 | 값 |
|---|---|
| 네임스페이스 | `experiential-marketing-media-local` |
| 벡터 수 | **302** |
| 총 분량 | 약 75,500자 |
| 청크 통계 | avg 250.1 / p50 174 / p90 498 / min 60 / max 1415 |
| 임베딩 | openai `text-embedding-3-large` (3072d) |
| 거리 공간 | Chroma 기본 `l2` (squared) |
| 임계 | 1.10 (`.env.openai` 관리) |

### 1.2 형식별 구성

| 형식 | 청크 | 초기 | 배수 | 점유율 |
|---|---|---|---|---|
| md | 229 | 13 | 17.6× | 76% |
| pptx | 46 | 46 | — | 15% |
| docx | 20 | 4 | 5.0× | 7% |
| xlsx | 7 | 7 | — | 2% |
| **합계** | **302** | **70** | **4.3×** | |

**자료를 하나도 추가하지 않고 버그 2건 수정만으로 4.3배.**

### 1.3 파일별 (296청크 시점 실측 + docx 표 반영분)

| 파일 | 청크 | 비고 |
|---|---|---|
| `경험경제-파인앤길모어-상세내용1.md` | 197 | 원본 17,120자 |
| `경험경제-파인앤길모어-골자.md` | 32 | 원본 3,538자 |
| `week2_experience_economy.pptx` | 15 | 슬라이드 15 |
| `체험마케팅_1주차_강의초안.pptx` | 15 | 슬라이드 15 |
| `week3_schmitt_sem_lecture.pptx` | 14 | 슬라이드 14 |
| `week3_schmitt_sem_lecture_note.docx` | 8→11 | 표 포함 |
| `week12_brakus_..._note.docx` | 6→9 | 표 포함 |
| `brand_experience_scale_survey_items.xlsx` | 4 | |
| `체험마케팅_15주_강의설계표.xlsx` | 3 | |
| `sem_expros_grid.pptx` | 1 | |
| `wundt_curve_slide.pptx` | 1 | |
| `1982_Holbrook.pdf` | **0** | 스캔본 (catch E) |

---

## 2. 실행 이력

| 회차 | 조건 | 결과 | 비용 |
|---|---|---|---|
| dry-run | 주입 함수 미전달 | `chunk_total=0` PASS | 0 |
| 2-b #1 | `.venv_vertex` | **FAIL** — `langchain_openai` 부재 | 0 |
| 2-b #2 | `.venv_openai` 신설 | 70청크 PASS | <1¢ |
| 2-b #3 | `MAX_TEXT_CHARS` 800→200000 | 296청크 | <1¢ |
| 2-b #4 | `_read_docx` 표 추출 패치 | **302청크 최종** | <1¢ |

### 2.1 dry-run 게이트 (재사용 가능 패턴)

`ingest_local_files()`의 `add_web_pages_json_to_chroma` 인자를 **미전달**하면
`local_rag.py:1562` 게이트에서 인덱싱이 스킵되어 **API 비용 0**으로 파일 수·청크 수·형식 분포를 사전 확인할 수 있다.

- 단, 디스크 쓰기는 발생: `resources/<slug>/local_*.json`, `research/.cache/*.data.json`,
  그리고 `data/chroma_store/<ns>{,-web}/` 빈 디렉토리
- 파싱 캐시(mtime+size 기준)가 살아 있어 본실행 시 재파싱 없음 → dry-run이 본실행을 느리게 하지 않음

---

## 3. 검색 검증

임계 1.10 기준, `n_results=3`.

| 질의 | 최상위 거리 | 최상위 출처 | 판정 |
|---|---|---|---|
| 슈미트 전략적 경험모듈 5가지 | 0.775 | `week3_..._lecture.pptx` | ✅ |
| 파인·길모어 경험경제 4E | 0.742 | `경험경제-...상세내용1.md` | ✅ |
| 브랜드 경험 척도 측정 문항 | 0.543 | `brand_experience_scale_survey_items.xlsx` | ✅ |
| 브랜드경험 12문항 4차원 | 0.592 | 동상 (표 조각 3위 진입) | ✅ |
| SEM 모듈별 경험 제공수단 정리 | 0.801 | `week3_..._note.docx` **표** | ✅ |
| 분트 곡선과 각성 수준 | 1.248 | `wundt_curve_slide.pptx` | ❌ 미해결 |
| **벤포벨 비타민 핵심 성분** (대조군) | 1.586 | 무관 조각 | ✅ 격리 확인 |

### 3.1 오염 대조군 — 방어 실증

벤포벨 질의에 1.586 / 1.606 / 1.611. 전부 임계 밖이고 반환된 것도 우리 강의자료.
**종근당·벤포벨 원자료는 0건.** 계단 0~1에서 설계한 3중 방어가 역방향으로 검증됨:

1. `CHROMA_NAMESPACE*` 3줄 → provider overlay의 `venfobel-vitamin-oa` 납치 차단
2. `LOCAL_RAG_GLOBS` override → `refs/` 전체 흡수 차단
3. slug 분리 → 논문 트랙과 물리적 경로 분리

### 3.2 절단 해제의 실질 효과

수정 전후로 **최상위 거리는 거의 변하지 않았으나 2·3위가 바뀜.**

- 수정 전: 강의록에서 **목차만** 검색됨 (앞 800자에 목차가 있었으므로)
- 수정 후: 본문·표가 2·3위로 진입 (`0.842`, `0.856` / `0.587`, `0.696`)

→ 답변 생성 시 사용 가능한 재료가 실질적으로 증가.

### 3.3 우려했으나 발생하지 않은 것

md가 인덱스의 76%를 점유하지만, **SEM·Brakus 질의 상위 3개에 md 유입 0건.**
검색은 비율이 아니라 거리로 선택하므로 양적 우세가 잠식으로 이어지지 않음.

### 3.4 부수 발견 — 로컬에 이미 있는 자산

`week3_schmitt_sem_lecture_note.docx` 표에 SEM 모듈 → 사례 → 주차 매핑이 존재:

```
관계 RELATE | 준거집단·문화와 관계 | 질레트 마하3, 밀크 머스태시 | 7주
```

800자 절단으로 인해 그동안 인덱스에 없던 내용.
**계단 3 설계 전에 로컬 보유분을 먼저 훑어야 중복 수집을 피할 수 있다.**

### 3.5 메타데이터 구조 실측

Chroma에 실제 저장된 키는 **4개뿐**:

| 키 | 예시 | 용도 |
|---|---|---|
| `title` | `week2_experience_economy.pptx (10, Index: 10, Chunk 1)` | **표시용. 한글 정상** |
| `source` | `file:///.../refs/%E1%84%8E%E1%85%A6...pptx#part=1&index=1&chunk=1` | 식별용. 한글 깨짐 |
| `source_version` | `1784534786058500528` (나노초 타임스탬프) | Chroma `changed` 판정 |
| `content_type` | `application/vnd...presentationml.presentation` | 형식 구분 |

`local_rag.py`가 조각 생성 시 붙이는 필드는 11개(`url`·`part`·`locator`·`bytes`·`fetched_at`·`mtime`·`pri` 포함)이나,
`web_rag/ingest.py`를 거치며 **4개로 축소**됨. `part`(슬라이드 번호 등)가 유실되어 위치 정보는 `title` 문자열 파싱으로만 획득 가능.

**`title` 형식이 분기별로 다름** — §3.2의 절단 이슈와 같은 구조:

```
pptx : week2_experience_economy.pptx (1, Index: 1, Chunk 1)         ← 슬라이드 번호
xlsx : brand_..._items.xlsx (브랜드경험 척도, Index: 1, Chunk 1)     ← 시트명
md   : 경험경제-파인앤길모어-골자.md (Chunk 1)                        ← 청크 번호만
```

→ 리포트 인용 시 "3주차 강의록 9번 슬라이드" 수준의 정밀도는 pptx·xlsx만 가능.

---

## 4. catch 등재

| # | 내용 | 상태 |
|---|---|---|
| **A** | provider overlay(`.env.openai`)가 `CHROMA_NAMESPACE*`·`RAG_EMBEDDING_MODEL`·`RAG_DISTANCE_THRESHOLD`를 **세트로** 관리. NS 자동 파생(`config.py:443`)은 값이 빈 경우에만 작동하므로 overlay가 채우면 무력화. 토픽 프리셋이 세트 중 일부만 덮으면 정합 파손 | 실측 확인 |
| **B** | 로컬 색인이 `web_search` 노드에 종속(`web_search.py:1235`). 독립 실행 경로 없음. `ENABLE_WEB_SEARCH=0` 시 로컬 색인도 동반 중단. `ingest_local_files()` 직접 호출로만 분리 가능 | 우회 확립 |
| **C** | `LOCAL_RAG_GLOBS` 토픽 override 전례 0건 (README-dev.md:1275 "자연 검증 예정" 항목) | **검증 완료 · 정상 작동** |
| **D** | `RAG_DISTANCE_THRESHOLD`가 CFG 미선언. 사용처 2곳(`diagnose_distance_threshold.py:47`, `ingest_vector.py:1603`)이 `os.environ.get(..., "0.65")`로 직접 read. fallback 0.65는 vertex 768d 시절 값 → overlay 부재 시 조용히 무한루프 구간으로 회귀. `_PROTECTED_ENV_KEYS`에도 미포함 | 미조치 |
| **E** | 텍스트 층 없는 스캔 PDF가 **경고 없이** 스킵. `1982_Holbrook.pdf` 10페이지 전량 누락, 로그·에러 0건 | 미조치 |
| **G** | macOS NFD 한글 파일명이 percent-encoding되어 `source` 필드에 저장. 자모 분리형(`%E1%84%8E...`)이라 판독 불가. **단 `title` 필드는 한글이 정상 보존됨**(251건 확인) → 표시 목적에는 `title` 사용으로 회피 가능. `source` 사용 시 `unquote` + `unicodedata.normalize("NFC")` 필요 | **회피책 확보.** 리포트 생성 코드가 어느 필드를 쓰는지는 계단 3에서 실물 확인 |
| **H-1** | `LOCAL_RAG_MAX_TEXT_CHARS=800`이 글로벌 `.env:134`에 잔존. 코드 기본값 200000의 **1/250**. `_to_webjson_items`의 `elif text` 분기(**md·docx·txt·html·csv**)가 앞 800자만 인덱싱. pptx·xlsx·pdf는 요소 단위 분기라 영향 없음. **프로젝트 전 토픽 영향** | **조치 완료** |
| **H-2** | `_read_docx`가 `d.paragraphs`만 순회하고 `d.tables` 미포함 → 표 전량 누락 | **조치 완료** |
| **H-3** | 부분/전체 추출 실패 무보고. pptx는 `slides=15/15`로 완결성을 보고하나 pdf·docx·md는 무보고. glob 매칭 파일 수와 실제 기여 분량의 괴리를 로그로 알 수 없음 | 미조치 |
| **I** | macOS 이관 시 **openai venv 누락**. `.venv_vertex`/`.venv_emb` 2개뿐이며 둘 다 `langchain_openai` 부재. §13-8이 확정한 운영 기본값(`LLM_PROVIDER=openai`/`gpt-4o`)을 실행할 환경이 없었음. `requirements.openai.txt`(`-r requirements.base.txt` 참조) 기준으로 `.venv_openai` 신설하여 복구 | **조치 완료** |

### 4.1 H 계열의 공통 구조

세 건 모두 **"조용한 손실"** 이다.

| 대상 | 손실률 | 경고 |
|---|---|---|
| `~$....xlsx` 엑셀 락파일 | 100% | **WARNING 있음** |
| `1982_Holbrook.pdf` | 100% | 없음 |
| docx 2건 | 82% | 없음 |
| md 2건 | 87% | 없음 |

**락파일(무해)은 경고했으나 실제 자료 손실(유해)은 침묵.**
개선 방향은 pptx가 이미 하고 있는 것 — `slides=15/15` 형태의 반영률 로깅을 다른 형식에도 적용.

---

## 5. 적용된 조치

### 5.1 `topics/experiential-marketing-media.env` 최종

```
TOPIC_TITLE / TOPIC_SLUG
CHROMA_NAMESPACE / _WEB / _LOCAL      # overlay 납치 차단 (catch A)
LOCAL_RAG_GLOBS                       # refs/ 전체 흡수 차단
RETRIEVE_WEB_RATIO=0.65               # 로컬 커버리지 갭 대응
SKIP_VERTEX_SEARCH=1                  # 계단 3 기준선 확보 (§6)
BLOCKAGI_OBJECTIVE_1~5
```

**의도적 미포함**: `RAG_EMBEDDING_MODEL`, `RAG_DISTANCE_THRESHOLD` (catch A — overlay 세트)
**글로벌 처리**: `LOCAL_RAG_MAX_TEXT_CHARS` (overlay에 없으므로 `.env` 수정으로 충분)

### 5.2 토픽 vs 글로벌 판별 규칙 (박제)

```bash
grep -n "^<KEY>" .env .env.openai
```

`.env.openai`에 **존재하면 토픽 프리셋 필요**(L3가 L2를 이김), 부재하면 글로벌 수정으로 충분.

| 키 | overlay | 토픽 필요? |
|---|---|---|
| `CHROMA_NAMESPACE*` | ✅ | 필요 |
| `RAG_EMBEDDING_MODEL` | ✅ | 필요하나 **건드리지 말 것** (세트) |
| `RAG_DISTANCE_THRESHOLD` | ✅ | 동일 |
| `SKIP_VERTEX_SEARCH` | ✅ | 필요 |
| `LOCAL_RAG_GLOBS` | ❌ | 불필요(격리 목적으로 명시) |
| `RETRIEVE_WEB_RATIO` | ❌ | 불필요(값 변경 목적) |
| `LOCAL_RAG_MAX_TEXT_CHARS` | ❌ | **불필요** |

### 5.3 코드 변경 (커밋 대상)

`tools/local_rag.py:503` `_read_docx` — 본문 XML 순회 방식으로 교체.

- `d.element.body.iterchildren()`로 `p`/`tbl` 순서대로 순회 → 표의 문서 내 위치 보존
- 병합 셀은 `r.cells`가 동일 `_tc`를 반복 반환하므로 `id()` 기준 dedup
- 행은 `|` 구분자로 직렬화
- **공용 함수** — `.docx`를 인덱싱하는 모든 토픽에 영향. 기존 동작 변경이 아닌 **누락분 추가**이므로 회귀 위험 낮음

### 5.4 재인덱싱 절차 (설정 변경 시 필수)

파싱 결과가 캐시에 저장되므로 **설정만 고치면 캐시 히트로 반영되지 않음.**

```
① 설정 변경
② 해당 형식 캐시 삭제 (research/.cache/*.<ext>.data.json 중 해당 토픽분)
③ rm -rf data/chroma_store/<ns>-local     # 안 지우면 changed=0으로 구버전 잔존 + 신버전 추가
④ 2-b 재실행
```

### 5.5 topics/experiential-marketing-media.env 전문

(파일 자체는 `.gitignore:75` 대상. 재현용 전문 기록)

```dotenv
# 체험마케팅과 미디어 콘텐츠 — 홍익대 대학원 15주 특강 (ad 트랙 학습용)
TOPIC_TITLE=체험마케팅과 미디어 콘텐츠
TOPIC_SLUG=experiential-marketing-media

# ── 인덱스 격리 (필수) ────────────────────────────
# .env.openai:56-58 이 NS를 venfobel-vitamin-oa 로 덮음 → L3에서 탈환
CHROMA_NAMESPACE=experiential-marketing-media
CHROMA_NAMESPACE_WEB=experiential-marketing-media-web
CHROMA_NAMESPACE_LOCAL=experiential-marketing-media-local

# ⚠️ 아래 3키는 여기 쓰지 말 것 — .env.openai 가 관리 중:
#   RAG_EMBEDDING_MODEL     (text-embedding-3-large / 3072d)
#   RAG_DISTANCE_THRESHOLD  (1.10 — 3-large+L2 실측. 0.65 덮으면 local 5%/web 0% → 무한루프)
#   SKIP_VERTEX_SEARCH      (오버레이 =0 으로 vertex ON. 계단3 전 별도 결정 — 미결)

# ── 로컬 자료 (오버레이에 없음 = 유일 소스) ────────
LOCAL_RAG_GLOBS=refs/experiential-marketing/**/*.pdf,refs/experiential-marketing/**/*.pptx,refs/experiential-marketing/**/*.docx,refs/experiential-marketing/**/*.md,refs/experiential-marketing/**/*.xlsx

# 로컬은 15주 중 4주(1·2·3·12)만 커버 → 웹 비중 상향. 계단3 실측 후 재조정.
RETRIEVE_WEB_RATIO=0.65

# ── 리서치 목표 (1→1-3주, 2→4-5, 3→6-9, 4→11-12, 5→10·13·15) ──
BLOCKAGI_OBJECTIVE_1=홀브룩 & 허쉬만(1982) 경험적 소비의 환상·감정·재미(3F)와 정보처리 패러다임 비판, 파인 & 길모어(1998) 경험경제 4E(엔터테인먼트·교육·미적·현실도피) 및 경험 연출(staging) 개념, 슈미트(1999) 전략적 경험모듈(SEM) 5유형과 경험제공수단(ExPro)의 이론적 계보 비교
BLOCKAGI_OBJECTIVE_2=슈미트 SEM의 감각(Sense)·감성(Feel) 모듈 실행 사례 — 사운드 로고·비주얼 아이덴티티·감각적 일관성 설계 방식, 분트 곡선(Wundt curve)이 설명하는 자극 강도와 선호의 역U자 관계 및 감각 과부하의 역효과, 감정 곡선(emotion arc)을 설계한 브랜드 필름과 공감 서사형 캠페인의 국내외 2023~2026 사례
BLOCKAGI_OBJECTIVE_3=슈미트 SEM의 인지(Think)·행동(Act)·관계(Relate) 모듈 실행 사례 — 반전·퀴즈형 인터랙티브 콘텐츠, UGC 참여 챌린지의 참여 설계 메커니즘, 팬덤·커뮤니티 기반 브랜드 콜라보, 그리고 여러 모듈을 결합한 온·오프 통합 캠페인의 경험 격자(experiential grid) 구성
BLOCKAGI_OBJECTIVE_4=체험 효과의 측정과 관리 — 고객 여정 맵(customer journey map) 작성법, 칙센트미하이 몰입(flow) 이론의 마케팅 적용, 참여지표(체류시간·UGC 생성률·재방문) 설계, 그리고 브라커스·슈미트·자란토넬로(2009) 브랜드 경험 척도 4차원(감각·정서·지성·행동)의 측정문항과 브랜드 충성도 연결 연구
BLOCKAGI_OBJECTIVE_5=미디어 형식별 체험 설계 — 숏폼(릴스·틱톡) 네이티브 브랜드 콘텐츠의 문법과 알고리즘 확산, 팝업스토어·브랜드 체험관·페스티벌의 온오프 통합(phygital) 사례, AI·VR·가상인간 기반 가상경험 마케팅의 2025~2026 최신 동향
SKIP_VERTEX_SEARCH=1
```

---

## 6. vertex OFF 판정

`tools/web_rag/vertex_search.py` (194줄) 확인 결과:

- `_build_client()`가 `GCP_PROJECT_ID` 요구 (`:52-57`, 부재 시 RuntimeError)
- `client.models.generate_content()` 호출 (`:125`) — **Gemini를 직접 호출하는 독립 검색 백엔드**
- `LLM_PROVIDER`와 무관하게 작동 (openai overlay가 `SKIP_VERTEX_SEARCH=0`으로 켜둔 상태였음)

### OFF 근거

| # | 근거 |
|---|---|
| a | Vertex AI Gemini + Google Search grounding은 **요청 단위 과금**. 지금까지의 임베딩 비용(3센트)과 자릿수가 달라 계단 3 예산 예측이 붕괴 |
| b | **catch 78** — 논문 트랙이 "벤더 껍데기 참조 오염"으로 vertex OFF 확정한 전례 |
| c | **STANDARDS §2.2** — 한국어 grounding이 영어 대비 metadata를 적게 반환. 본 토픽은 한국어 |
| d | **단일변수 원칙** — 계단 3은 웹 수집 첫 실행. 백엔드 2개 동시 활성 시 결과 원인 분리 불가 |

### 대체 백엔드 확보

`.env`에 `SEARCH_BACKENDS`, `TAVILY_API_KEY`, `NAVER_CLIENT_ID/SECRET` 존재.
vertex OFF여도 Tavily + Naver로 계단 3 실행 가능. 한국어 토픽이므로 Naver의 국내 사례 커버리지가 유리할 가능성.

**ON 비교 실험은 계단 3 기준선 확보 후 별도 런으로.**

---

## 7. 미해결 항목

| # | 항목 | 우선도 | 비고 |
|---|---|---|---|
| 1 | **분트 곡선 1.248** — 정답인데 임계 탈락. 어휘 불일치(질의 "각성 수준" vs 원문 "자극과 쾌감"). 청킹 변경으로도 불변 | 중 | 임계 재튜닝 또는 슬라이드 텍스트 보강. `tools/diagnose_distance_threshold.py` 활용 |
| 2 | **md 과분할** — `markdown_features=True` + 오버랩으로 원본 대비 ×1.85 부풀림 (docx는 ×1.15). 평균 청크 160자. 4E 질의 1위가 목차 나열 조각으로 잡히는 증상 | 중 | 계단 3에서 웹 자료와 혼합 시 영향 재평가 |
| 3 | **중복 2쌍** — `wundt_curve_slide.pptx` ↔ `체험마케팅_1주차_강의초안.pptx`, `sem_expros_grid.pptx` ↔ `week3_..._lecture.pptx#part=9`. 동일 텍스트가 상위 3칸 중 2칸 점유 | 하 | 다음 재인덱싱 때 정리 |
| 4 | **`1982_Holbrook.pdf`** 스캔본 | 중 | 학교 도서관 DB(JSTOR 등) 텍스트본 확보 권장. OCR은 1982년 스캔 품질상 차선 |
| 5 | **`RETRIEVE_WEB_RATIO=0.65` 실효성** — venfobel 실측상 web은 임계 1.10에서 21%만 통과. 비율을 올려도 실제 충족량이 제한될 수 있음 | 중 | 계단 3 실측 후 판단. 미해결 1번과 같은 뿌리 |
| 6 | **catch G 한글 파일명** | 하 | `title` 필드로 회피 가능(§3.5). 리포트 생성 코드가 `source`를 쓰는 경우에만 실제 문제 |
| 7 | **논문 트랙 baseline 영향** — `LOCAL_RAG_MAX_TEXT_CHARS` 800→200000 변경으로 이전 측정과 직접 비교 불가 | 하 | 논문 트랙은 `-oa` 컬렉션 자체가 미생성이므로 실제 영향 작음 |

---

## 8. 계단 3 진입 전 준비

1. **로컬 보유분 선조사** — §3.4 참조. 15주 중 어느 주차의 어떤 요소가 이미 로컬에 있는지 확인해야 중복 수집 방지
2. **`SEARCH_BACKENDS` 값 확인** — Tavily/Naver 중 무엇이 어떤 순서로 활성인지
3. **계단 3 성공 기준 (사전 정의)**
   > 15주 설계표 **E열(붙일 미디어 사례 유형)** 에 넣을 구체적 사례 — **브랜드명 + 캠페인명 + 연도** — 확보.
   > "그럴듯한 일반론"이 나오면 실패로 판정.
4. **F열은 RAG 대상 아님** — 벨컴/디트라이브 내부 자산. 직접 작성 필요
5. **실행 방식** — `app.py` 경유. 트리거 문자열은 `최신 자료로 RAG 업데이트` (정규식 `agent/supervisor.py:609`, 3단어 순서 고정, 줄바꿈 불가)
6. **`TOPIC_SLUG` 전환** — 계단 3은 app.py를 타므로 글로벌 `.env:49` 수정 필요. **논문 트랙 값 백업·복원 절차 필수**

---

## 9. 정찰~계단2 중 발생한 오판 기록

| 오판 | 원인 | 교훈 |
|---|---|---|
| `chromadb.PersistentClient`로 빈 DB 파일 생성 | 라이브러리가 없으면 생성하는 동작 미인지 | 기존 DB 조회는 `sqlite3` 직접 읽기 |
| `sed` 마스킹이 필요한 값을 가림 | 기준이 "8자 초과"(길이)였음 | 마스킹은 **키 이름** 기준, 또는 `cut -d= -f1`로 값을 안 뽑기 |
| 임계 `0.65` 초안 삽입 | 글로벌 `.env`만 보고 overlay 미확인 | 토픽에 쓸 키는 **overlay 존재 여부 먼저** (§5.2 규칙화) |
| "NS 자동 파생이라 명시 불요" | 자동 파생의 발동 조건(값이 빔) 미확인 | 조건부 로직은 조건까지 읽는다 |
| "vertex는 Gemini 종속" → 철회 → 재정정 | STANDARDS §2.1의 *분류명* 정의를 *호출 경로*로 오독. 철회 시에도 "Gemini 미호출"로 잘못 정정 | 결과물 분류 ≠ 실행 경로. 코드로 확인 후 단정 |
| glob 루트 파일 보험 줄 추가 | Python `**`의 0-디렉토리 매칭 미확인 | 동작 불확실 시 재현 테스트 먼저 |
| `.gitignore` venv 누락 판정 | `git check-ignore`가 **미존재 경로 + 디렉토리 전용 패턴**(`/` 접미)에서 매칭 실패하는 특성 미인지 | `check-ignore`는 미존재 경로에 대해 신뢰 불가 |
| "md는 절단을 피했다" | 청크 **개수**(13)만 보고 분량 미확인 | 개수 ≠ 분량. 원본 대비 반영률로 판단 |

