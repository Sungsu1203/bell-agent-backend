# GUARDRAILS — 회사 트랙 (광고·마케팅 기획서/보고서 writer)

> 🏢 회사 트랙 운영 규칙·상수. 공통 규칙(venv·커밋·측정·subagent·방법론·판정)은 상위 `../CLAUDE.md` 참조.
> 여기엔 **회사 트랙에만 해당하는 것**만 적는다.
> 상태: §research-1 선분 1 종결 반영(2026-08-06). §ad-track-1은 완료(E열 미충족).

---

## 이 트랙이 하는 일
RAG writer agent의 원형 용도 — 광고대행사 기획서·보고서 생성.
(논문 트랙은 이 공통 뿌리에서 학술 논문 작성용으로 확장된 갈래.)

## 회사 트랙 운영규칙 (원본: README-dev.md — 각 항목 상세는 포인터 참조)
> 아래는 한 줄 요약 + 위치 포인터. 상세 아카이브는 `./README-dev.md`에 살아있음.
> ⚠️ 공통 규칙은 여기 안 둠 → `../CLAUDE.md` (§4 커밋범위 · §6 측정 · §7 방법론 · **§9 판정 규율**)
>    + `../STANDARDS.md` (§1 ENV · §2 metric · §3 Chroma · §4 보호키 · §5 credential · §6 venv)

- **폴더 구조 & 의존 규칙** — `utils→tools→agent`, `core`는 설정·타입·라우팅만; `agent/*`끼리 직접 import 금지(라우팅은 `core/routers.py`). [README-dev.md §1]
- **환경변수 단일화** — 모든 ENV는 `core/config.py`(`CFG`)·`ingest_config.py`(`_cfg_*`)에서만 파싱; 타 모듈 `os.getenv` 직접 호출 금지. [README-dev.md §2]
- **RAG 파이프라인 구조** — 수집→변환→인덱싱→검색→드롭필터 흐름; 한국어는 `text-multilingual-embedding-002`(768d), `_looks_like_garbled`로 깨진 바이너리 드롭. [README-dev.md §3]
- **공개 API(파사드)만 사용** — 외부는 `tools/web_rag/__init__.py` 파사드만; 내부 `ingest*.py` 직접 import 금지. [README-dev.md §4]
- **공통 타입/시그니처** — `DocMode` 리터럴, `retrieve()`/`web_search()`/`merge_refs()` 시그니처 고정. [README-dev.md §5]
  ⚠️ **2026-08-08 R6** — `merge_refs()` 실효 범위는 **위치 인자 3개까지.**
  `utils/rag_utils.py:342` 사본에만 keyword-only 4개(`preserve_extra`·`limit_queries`·`limit_docs`·`sort_docs_by_score`)가 더 있다.
  `utils/refs.py:255` 사본은 3인자이고 **본선 import 0곳(사문)**.
- **임베딩 안전망** — 기본 fail-fast(RuntimeError); 더미 폴백은 `ALLOW_DUMMY_EMBEDDINGS=1` opt-in만, 프로덕션 금지(인덱스 0벡터 오염 방지). [README-dev.md §6]
- **진단 도구** — `diagnose_embeddings.py`(임베딩·NS 확인)·`diagnose_chunks_deep.py`(청크 분포); 새 토픽 인덱싱 후 1회 권장. [README-dev.md §8]
- **데이터 품질 운영 노하우** — HWP/이벤트·광고/SEO 시장리포트 노이즈 패턴,
  단일 호스트 50%↑ 의심, `FILTER_BAD_DOMAINS` 업데이트. [README-dev.md §9]
  - 🔴 **사이트크롬 오염 (catch CA, 2026-08-06 실측)** — nav·푸터·사업자등록번호·직원명단·
    댓글폼이 청크로 색인된다. dist **0.669~1.081**로 유의미 자료보다 가깝게 통과.
    web 통과 청크의 **29%**(19/65), local 0건.
    ⚠️ **임계 조정으로 못 막는다.** 수집·색인 단계 제거가 유일한 해법
  - 🔴 **플레이스홀더 오염 (catch CB)** — 강의자료의 `🟨 실무 사례 자리` 슬라이드가
    색인에 포함된다. local 전용 오염
  - 🔴 **경계 없는 부분일치 (catch CP-1, 2026-08-10 §research-1 S4-e)** — 크롬 판별
    `cat_of_one`(`probe_s2_tagmap.py:195`)의 이름사전 대조가 `k in " ".join(chain).lower()`
    **평문 부분일치**다. `inside`←`side` · `desktop`←`top` · `tagdiv`←`tag` 로 **본문 컨테이너가
    크롬 판정**된다. 견본 103 표본에서 **26건 전건 본문(정밀도 0%)**, ③ 452 에서 **58건(12.8%)**.
    `팝업스토어`←`팝업` 오탐과 동일 기전. **경계 매칭으로 해결 가능**
  - 🔴 **의미 불일치 완전일치 (catch CP-2)** — 토큰 경계를 지켜도 남는다. `margin-top` 의 `top` 은
    CSS 여백이지 페이지 상단이 아니고 `id="top"` 도 앵커일 뿐이다. 견본 103 표본 **44건 전건
    본문(100%)**, ③ 452 에서 **30건(6.6%)**. **경계 매칭으로 해결되지 않아 사전 항목 자체의
    재검토가 필요하다**
  - 🔴 **전역 요소 파급 (catch CP-3)** — `<body>`·`<html>` 등 **전역 요소의 class/id 가 사전 항목을
    포함**하면 그 페이지 **전 노드**가 크롬 판정을 받는다. 실물 `layout-aside-right`(aside) ·
    `_body_menu_…`(menu) · `drag-prevent`(prev) · `desktop`(top) · `body#top`(top).
    9 URL 이 ③ 452 중 **188건(41.6%)** 을 덮고 한 URL 이 99건이다. 파급이 페이지 단위라 CP-1·CP-2
    보다 크고, **정답이 나와도 근거가 무효**이므로 정답률이 규칙 성능을 과대평가한다.
    → 라벨 단위는 레코드가 아니라 **URL**(오판 1개가 페이지 전체에 복제됨)
  - 🔴 **`FILTER_BAD_DOMAINS` 실측 = `''`(빈 문자열)** — 2차 필터가 현재 무작동
    (`ingest_vector.py:1644-1647`, 2026-08-06 확인)
    ⚠️ **2026-08-08 R5** — `:1644-1647`의 소속은 **`retrieve()`(@1534)**. 색인부 1차는
    **`:899`**(`documents_to_chroma` 내부). 소비처 4벌 — `:899` · `:1645`/`:1702` · `web_search.py:629`
- **코드 품질 가드** — pre-commit(Ruff·Mypy·Pytest), `tests/` 회귀 스위트(domain_bonus·xlsx·garbled 등). [README-dev.md §10]
- **PR 운영 순서(권장)** — config 통합→파사드→rag_utils→scheduler→routers→토픽 외부화→품질가드→deprecated 제거. [README-dev.md §11]
- **알려진 이슈/주의사항** — 한국어 임베딩 모델 필수(`text-embedding-004` 금지, 변경 시 인덱스 재빌드), `vertex_search.py`는 토글 보존 코드(dead 아님). [README-dev.md §13]
- 디버깅 표준 → `./README-dev-2.md` "디버깅 표준 박제(영구 박제, §14-3 origin)" 참조 (추정 기반 진단 위험성·사전확인 가치·Bash vs PowerShell 등).

## 트랙 전용 상수
- **활성 토픽** = `topics/experiential-marketing-media.env` (§ad-track-1 · §research-1 **공유**)
  ⚠️ 두 트랙 공유이므로 `RETRIEVE_WEB_RATIO` 등 검색 파라미터 조정 시 양쪽 영향 확인 필수
  - NS 격리 3키 필수 — `.env.openai:56-58`이 venfobel NS로 덮으므로 L3에서 탈환
  - `RAG_DISTANCE_THRESHOLD` · `RAG_EMBEDDING_MODEL` · `SKIP_VERTEX_SEARCH`는 **L3에 쓰지 말 것** (`.env.openai` 관리)
- 대상 산출물 포맷: 강의 사례표(E열 4요소) / 기획서·보고서체 (TODO)
- 클라이언트·프로젝트별 설정: (TODO)

## 측정·품질 기준
- **사례 추출 판정 = 3요소**(브랜드 + 캠페인 + 연도 + URL). 부분 확보는 준확정
- **추출 > 생성**: 목표물이 원문에 있으면 LLM을 거치지 않는다 (catch AN — 참조 27회에 본문 0회)
- **가상 기획 배제**: 집행되지 않은 기획안이 사례로 위장한다 (catch AU — aimatters "가상 AI 캠페인")
- **연도는 복수 청크 교차 확정** (catch AW/AX — 한국 마케팅 블로그는 사례 연도를 본문에 안 적는다)
- 공통 측정 표준은 `../CLAUDE.md §6` + `../STANDARDS.md §2`
- **추출 > 생성**: 목표물이 원문에 있으면 LLM을 거치지 않는다 (catch AN)

## 파일 지도
- 이 파일 = 회사 트랙 운영 규칙.
- ./WORKBOARD.md = 회사 트랙 할일·활성 트랙·결정 기록.
- ./README-dev.md, ./README-dev-2.md = 회사 트랙 개선 기록(아카이브).
- ./README-dev-§14.md = §14 vertex 백엔드 점검·개선 아카이브.
- **catch 네임스페이스 2계열 — 섞지 않는다.** (2026-08-10 명문화)
  - **문자**(CA·CB·CI·CJ·CK·CL~CP…) = ad·RAG 파이프라인.
    본 파일 + `../STANDARDS.md` + `../CLAUDE.md §9`(판정 규율분)
  - **숫자**(1~67) = §13 pptx · §14 vertex · paper 트랙.
    `./README-dev.md`(`612cc87` 에서 동결) · `./README-dev-2.md`(현행) · `./README-dev-§14.md`
  - ⚠️ 두 계열이 어디에도 적혀 있지 않아 배치를 두 차례 잘못 지정한 전례가 있다.
    새 catch 는 **네임스페이스를 먼저 확인**하고 배치한다.
