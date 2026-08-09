# CLAUDE.md — bell-agent writer_project 운영 가드레일

> 이 프로젝트 = RAG writer agent 공통 뿌리 + 두 트랙.
> 📄 논문 트랙 = paper/ (WORKBOARD, README-dev-paper).  🏢 회사 트랙 = ad/ (GUARDRAILS, WORKBOARD, README-dev, README-dev-§14).
> 이 파일 = 공통 상수·규칙 + 두 트랙 갈림길.

> 이 파일은 Claude Code가 **세션 시작마다 자동으로 전체를 읽는다**(요청 불필요, /compact 후 재주입).
> 매 작업 전 여기부터 확인. 규칙은 흩어진 README가 아니라 **이 파일이 단일 진실원(source of truth)**.
> repo 경로: `/Users/ohsungsu/dev/bell-agent/bell-agent-backend/writer_project/`

---

## 0. 채널 역할 (2-채널 협업)

- **Claude(챗)** = 전체 점검 · 진행 방향/우선순위 판단 · R-게이트 결정. (메모리 보유)
- **Claude Code(여기)** = 분석 · 실행. **메모리 없음 → 이 파일과 레포 파일만 의존.**
- 파일 지도:
  - `CLAUDE.md`(이 파일) = 운영 상수·규칙. 자동 로드.
  - `paper/WORKBOARD.md` = 앞으로 할 일(활성 트랙 · 별 트랙 후보 · 결정 기록). 세션 시작 시 함께 읽을 것.
  - `paper/README-dev-paper.md` = **종결 catch 아카이브(박제)**. 과거 기록 전용. 새 작업 계획은 여기 넣지 않는다.
  - `OBSERVED.md` = 설정층 실측 대장. 규범 아님. 세션 시작 시 통독 불요, 필요할 때 grep.

---

## 1. ⚠️ 토픽 (가장 자주 틀리는 지점 — 실행 전 필수 확인)

**트랙마다 토픽이 다르다. 아래는 트랙별 정본이다.**

| 트랙 | env 파일 | 토픽 |
|---|---|---|
| §paper | `topics/academic-trademark-similarity-consumer.env` | consumer perceived trademark similarity and likelihood of confusion (소비자 지각 상표 유사성과 혼동 가능성) |
| §ad-track | `topics/experiential-marketing-media.env` | 체험마케팅과 미디어 콘텐츠 |

- ⚠️ **진짜 위험은 `TOPIC_SLUG` 미지정이다** (catch AB — 미지정 시 논문 프리셋이 로드됨).
  → 어떤 측정/fetch를 돌리기 전에 로드되는 `.env`가 위 표의 값인지 **눈으로 확인**하고 시작.
  → 스크립트는 무거운 import보다 **앞에** `assert os.environ.get("TOPIC_SLUG")`를 둔다.
    검증은 실행으로 — `TOPIC_SLUG` 없이 돌려 AssertionError로 죽는 것까지 확인한다.
- ⚠️ **"코드 기본값이 `influencer marketing`으로 박혀 있다"는 기존 기술은 stale이다**
  (2026-08-03 실측). `measure_paper.py:131`은 이미 `academic-trademark-similarity-consumer`이고,
  `influencer`는 같은 줄 **주석에만** 남아 있다. `core/`에는 0건.
  나머지 출현은 `§academic-1`·`§academic-4`·`smoke/` 등 개별 스크립트 하드코딩이다.
- **§paper topic 단일 진실 = `topics/<slug>.env` 의 `TOPIC_QUERY` (fetch+writer 공유 소스).**
  `measure_paper.py --topic` default 가 이 값을 읽는다(생략 시 자동 주입). 위 표 문자열과 byte 동기 유지.

---

## 2. vertex 스킵 규칙

- **`SKIP_VERTEX_SEARCH`는 토픽 `.env` 프리셋이 전역 플래그를 이긴다(preset wins).**
  전역에서 켜도 토픽 .env가 off면 최종 off. 반대도 성립.
- **상표 토픽 = vertex `off` 확정.** (catch 78 — 벤더 껍데기 참조 오염 차단)
- 실파일 기준 라인 = **`:22`** (`:21`은 주석). off-by-one 주의.

---

## 3. 가상환경 — provider별 분리 (STANDARDS §6)

- **논문/vertex 트랙 = `../.venv_vertex/bin/python`** (vertex 의존성 = requirements.vertex.txt)
- **ad/openai 트랙 = `../.venv_openai/bin/python`** (requirements.openai.txt, 2026-07-31 신설 — catch I)
  ⚠️ `.venv_vertex`에는 `langchain_openai`가 없어 `LLM_PROVIDER=openai` 실행 시 임베딩 ctor 실패.
- `.venv_emb` = 로컬 임베딩(e5-large) 전용.
- **macOS에서도 정상 동작**(윈도우 전용 아님 — 오해 금지).

**zsh 주의 2건**
- `§`, `*` 포함 경로는 **따옴표로 감쌀 것.**
- **word splitting이 안 된다** (catch AM). `set -- $VAR` / `for x in $LIST`는 zsh에서
  분리되지 않고 통째로 한 덩어리가 된다. `${=VAR}`를 쓰고, 배열 인덱스는 1-based다.
  ⚠️ **에러 없이 빈 값으로 돌아간다.** 측정 루프에서 조합이 기본값으로 실행돼도 눈치채지 못한다.

---

## 4. 커밋/푸시 범위 (엄수)

- **커밋 대상 = 수정된 `.py` 코드 파일 + 운영 문서(`README-dev-§14.md` · `WORKBOARD.md` ·
  `CLAUDE.md` · `STANDARDS.md` · `.gitignore`) 변경분 + 작업에 필요한 원자료.**
- **제외** = `scripts/output/**`의 원자료. `.gitignore:84~90`이 확장자로 차단 (`*.json` `*.log` `*.ndjson` `*.console.log` `*.patch` `*.docx` `paper_*.md`).
- **포함** = `scripts/output/`의 분석·판정 `.md` (현재 71건 tracked). 덤프 보관처가 아니라 **결론 문서 보관처**다.
  (건수 확인: `git -c core.quotePath=false ls-files ':(top)' | grep 'scripts/output/' | grep -c '\.md$'`)
- **예외 복원** = 박제의 재현성 근거는 `.gitignore`에 `!`로 되살린다. 새로 추가할 때도 `!` 한 줄 + 이유 주석을 같이.
  - 박제 재현성 2건 — `:92` `:94` (`c_ab_results.json` · `chunks_full_abstract_dump.json`)
  - 도구·자산 2건 — `:109` `!probe_Z_extract.py` (arm Z 드라이버) · `:112` `!refs/experiential-marketing/**/*.pptx` (강의 원자료)
  - ⚠️ 디렉터리 통째 차단(`foo/`) 하위는 `!`로 되살릴 수 없다(git 규칙). **확장자·이름 패턴으로 차단할 것.**
- NEXT_SESSION 메모는 일회용 → 커밋 안 함 (관행).
- repo private → NDA push hold **해제됨. push 가능.**

**🔴 `git add -A` 금지 (catch AS)**
> 워킹트리에 **여러 트랙이 동시에 상주**한다. 2026-08-03 실측 — `§paper-writer-1/measure_paper.py`(수정) ·
> `diversity_rewrite.py`(미추적) · `§rag-core-1/` · `§rag-core-2/`가 ad 세션 중에 떠 있었다.
> `git add -A` 한 번이면 **남의 트랙이 통째로 딸려간다.**
> - **`git add <path>`로만.** 폴더 add도 금지 — NEXT_SESSION이 같은 폴더에 섞여 있다.
> - `git add` 후 **`git diff --staged --name-status`로 스테이징 실물을 세고** 커밋한다.
>   (`git status`에는 `--cached`가 없다 — 스테이징 조회는 `git diff --staged`)
> - 임시 산출물은 `.gitignore`로 걷어낸다. **`??` 목록이 육안으로 안 읽히면 이 규율이 무너진다** —
>   2026-08-03에 `probe_*`·`*.log` 22건을 걸러 30줄 → 16줄로 줄였다.
- 커밋 전 `git status`/`git diff --stat`로 대상이 위 범위인지 확인.

---

## 5. 보고 방식 — "쉬운 설명" 의무 (학습 목적, 중요)

Claude Code가 코드 변경·명령을 보고할 때 **항상 두 층으로** 낸다:

- **(A) 기술 정밀층** — 파일:라인, diff 요지, STOP 게이트, self-check 결과.
- **(B) 쉬운 설명층** — 이 코드/명령이 **"무엇을 하는지 + 고치면 뭐가 좋아지는지"**를
  일상어·비유·예시로. 전문용어 최소화. 사용자가 핵심을 이해하고 넘어가도록.
- 명령어(bash 등)도 붙여넣기만 하지 말고 **"이 명령은 X를 확인/실행한다" 한 줄**을 곁들인다.

예시(catch 82):
- (A) `openalex.py:157` `_extract_venue()` fallback 추가 — `primary_location.source`가 repo type면 `locations[]` 순회.
- (B) OpenAlex가 논문 정보를 줄 때 "출판 저널명"을 보통 맨 앞칸에 넣는데, 법학 논문은 앞칸에 '저장소 사본'을
  넣고 진짜 저널명을 뒷칸에 두는 경우가 많다. 기존 코드는 앞칸만 봐서 저널명을 놓쳤음. 이제 앞칸이 저장소면
  뒷칸까지 뒤져 진짜 저널명을 찾는다. → 참고문헌에 저널 이름이 제대로 붙는다.

---

## 6. 측정 표준 (박제)

- **dry-run 플래그 먼저** — API cost=0 게이트 통과 후에만 유료 실행.
- **dotenv load → env override 순서 준수** (catch 69 — `override=True`가 `LLM_PROVIDER`를 덮음).
- **ENV 파서 truthy 패턴 확인 후 값 설정** (catch 71 — `"false"` 문자열이 True로 읽힘).
- `max_retries=0`, warmup 2런, per-run-timeout `max(300, mean×1.5)`, inter-run-sleep 60s, `PYTHONIOENCODING=utf-8`.
- provider별 venv·`.env` 분리.

> 공통 표준 상세 → `STANDARDS.md`
> - ENV 4-layer 로드 순서·override (STANDARDS §1)
> - 측정 metric·ref source 분류 (STANDARDS §2)
> - **Chroma 정책 — ns_web reset · 읽기 접근 (STANDARDS §3)**
>   ⚠️ 읽기 전용 조회는 `sqlite3 -readonly`. `PersistentClient`는 경로 오지정 시 **빈 DB를 생성**한다 (catch AG).
> - `_PROTECTED_ENV_KEYS` 5키 (STANDARDS §4)
> - **credential 노출 감사 — 현재상태 2-명령 + 🔴 이력 3축 (STANDARDS §5.1 / §5.1-a)**
>   ⚠️ 이력 감사의 **1순위는 키 prefix가 아니라 파일명 축**이다. prefix 없는 키(naver·serpapi)는
>   정규식으로 영원히 안 걸리고, 실제 사고는 `.env` **파일 통째** 커밋이었다.
>   판정은 `git show <commit>:<path>`로 마감한다 — `git grep ... -- .`은 pathspec이 cwd 기준이라
>   레포 루트 파일을 **에러 없이 0건**으로 흘린다 (§research-1 R1b 실사고).
> - history scrub(`filter-repo`) = **이 레포 기각 확정, 재론 금지** (STANDARDS §5.4-a)
> - **provider별 venv 분리 (STANDARDS §6)**

---

## 7. 방법론 (§-cycle)

- **R1 정찰(read-only)** → **R2 설계** → **R3 구현+측정**. 유료 API 호출 전 **STOP 게이트**(코드수정 0, 커밋 0 확인).
- catch 인용 시 **항상 한 줄 설명 첨부** — 예: "catch 43(EN 쿼리 → vertex 자동활성 language routing)".
- NEXT_SESSION 파일명: `NEXT_SESSION_<YYYYMMDD>_<§cycle-id>-close.md` (untracked, 일회성. 사용 후 archive/삭제).

**🔴 핸드오프 문서는 git으로 재검증하고 시작한다 (catch AR)**
> 문서의 "지금 상태"는 **작성 시점 스냅샷**이다. 세션 첫 명령은 이것:
> ```
> git log --oneline -8 && git diff --stat && git status --short
> ```
> 실례 — 3-b 문서가 `tools/local_rag.py` 미커밋이라 기술했으나 이미 커밋(`2612e7a6`)돼 있었고,
> 대신 **논문 트랙 미커밋분이 상주**하고 있었다(catch AS). 문서가 말한 위험과 실제 위험이 달랐다.

**선행 조건은 정찰로 확정한다**
> 실행 경로가 정해지기 전의 "진입 전 반드시"는 **가설**이다.
> 3-b가 필수로 올린 3건(catch AQ 문안 이식 · AO 신규 문안 · 마커 재할당 검증)이
> 정찰 1회($0)로 전부 소멸했다 — `metadata.source`에 URL이 이미 있어 마커 체인 자체가 불필요했다.
> **선언이 아니라 실측으로 판정한다.**

**하류 봉합 금지 — 출력 형식은 상류에서 잠근다**
> 프롬프트가 만든 형식 오류를 **정규식 확대로 막지 않는다.** 논문 트랙에서 4연패한 경로다:
> (1) 묶음 `[[1],[2]]` 미탐 (2) loose grep이 정상 마커 오탐
> (3) 변종 `[[a], [[b]]` 미탐 (4) `\[\[.*?\]\]` over-match → prose 문장 삭제
> 원래 정규식 `\[\[(\d+)\]\]`는 틀리지 않았다. **writer가 정본을 안 지킨 것이다.**
> - 금지 예시를 **구체적으로** 프롬프트에 넣는다 — 추상 규칙보다 "이건 안 됨: `[[1], [2]]`"가 확실하다.
> - **억압형("~하지 마라")은 실패하고 요구형("~를 유지하라")이 통한다.**

---

## 8. 현재 baseline (stale 수치 주의)

### 8.1 §paper 트랙
- **references = 89 (OA 60 + SS 29).** ⚠️ 77은 catch 78 직후 stale — 이후 catch 74(SS tail-only 복구)가 늘림. 함정.
- axis1 = **1.0 PASS** (complete 44 / partial 45 / missing 0).
- ⚠️ **위 수치는 §paper-writer-1 시점이다. §paper-writer-2 진행 중이므로 미검증.**
  갱신은 논문 트랙 세션에서 한다 — ad 세션에서 건드리지 않는다.
- 상세·진행 방향은 `paper/WORKBOARD.md` 참조.

### 8.2 §ad-track (2026-08-02, 계단 3-c close 기준)
- 인덱스: `-local` **302청크**(avg 208자) / `-web` **416청크**(avg 1,873자)
- **추출 경로 = arm Z (비-LLM).** `retrieve` → 청크 원문 + `metadata.source` 직결.
  LLM을 거치면 브랜드·연도가 깎인다(catch AN) — 목표물이 원문에 있으면 추출이 생성보다 낫다.
- E열 확보: **확정 5건 + 준확정 3건** / 목표 14칸
- 누적 비용 ≈ **$0.25** (계단 0~3-c)
- ⚠️ **2026-08-05 §ad-track-1 완료 처리 (E열 미충족).** 미충족 사유 = 수집 부족이 아니라
  파이프라인·목표 미스매치. 잔여 계단은 `ad/WORKBOARD.md` 이월 표로 이관
- 상세·진행 방향은 `ad/WORKBOARD.md` 참조. 사이클 박제는 `scripts/output/§ad-track-1/`

### 8.3 §research-1 (2026-08-07, R3b 시점) — **현재 활성**
- 목표: **objective 기반 리서치 리포트 파이프라인** — `.env`의 `BLOCKAGI_OBJECTIVE_N`을 입력으로 `쿼리 생성 → 수집 → 색인 → objective별 retrieve → 충분/부족 판정 → 재쿼리 루프 → objective별 writer` 8단계를 한 명령으로 완주 (정본 `scripts/output/§research-1/R2c_NORTH_STAR.md`). 토픽은 ad 트랙과 공유(`experiential-marketing-media`)
- 누적 비용 **$0** — R1·R1b 전량 읽기 전용
- **🔴 계측기는 이미 있다.** 9개 노드 전원이 진입부에서 `emit_event()` 호출 + `/api/events`(`app.py:2188`)·
  `/api/state`(`:1231`) 노출. **노드 진입 로그 삽입 작업은 불요.**
  단 `/api/state`가 `research_round`·`research_plan`·`last_synthesis`를 노출하지 않아
  라운드 관측은 `research/<slug>/round-NN-findings.md`와 planner 로그로 한다
- **🔴 근거 사슬은 본선에서 안 끊긴다.** `[[N]]` 위치 인덱스 + `.refs.json` 사이드카
  (URL + 청크 풀텍스트)로 역추적 생존. X는 `research_synthesizer` 곁가지 1곳뿐이고
  `last_synthesis`·`findings_md`의 **소비처가 0건**이다
- **🔴 Evaluate→Plan 되먹임 배선이 없다.** 목표는 토픽 env 5개를 `objs[min(rnd, len-1)]`로
  **고정 순회**(`agent/research_planner.py:227`). 원인은 배선이 아니라 **출력 형식** —
  원형은 JSON 스키마 강제 + `json.loads` → dataclass, 우리는 마크다운 자유 서술이라 추출 불가
- 상세는 `ad/WORKBOARD.md` 활성 트랙. 박제는 `scripts/output/§research-1/`

---

## 9. 판정 규율 (근거를 쓰기 전에)

> §7이 "어떤 순서로 하나"라면, §9는 **"그 근거를 믿어도 되나"**다.
> 아래 4건은 전부 **오판이 실제로 발생한 뒤** 승격된 규칙이다.

**기록된 것은 현재가 아니다 — 세 갈래**
> 같은 뿌리의 오판이 한 사이클에 세 번 나왔다.
> - **문서** (catch AR) — 핸드오프의 "지금 상태"는 작성 시점 스냅샷
> - **주석** (catch BA) — 코드 주석의 환경 기술은 작성 시점 환경.
>   `diagnose_richness.py`의 "PersistentClient panic"은 Windows 시절(2026-05-06) 기록이었고
>   macOS 실측은 정상(`count=416`)이었다
> - **분류** (catch P) — 호스트명·파일명은 내용의 대리값이 아니다.
>   `illustkorea.or.kr`을 "주제 무관"으로 분류했으나 실제 제목은
>   「숏폼 영상광고의 트렌드와 브랜드캠페인 성공사례에 관한 연구」 — 핵심 학술자료였다
>
> **공통 처방: 판정 전에 실행하거나 열어본다.**
> 주석은 작성 커밋 날짜를, 문서는 `git log`를, 소스 분류는 **제목**을 확인한 뒤 판정한다.
> ⚠️ 이 규칙이 적발한 첫 사례는 **CLAUDE.md §1 자기 자신**이었다(influencer 기술 stale).

**도구 출력은 계산 방식을 확인한 뒤 해석한다**
> `diagnose_richness.py`의 `namespaces=N`은 **`-web`/`-local` 접미사 이름 필터**다.
> 내용이 아니라 폴더명으로 거른다. 이를 "빈 NS의 증거"로 읽으면 틀린다.
> 같은 유형 3건이 한 사이클에 나왔다 — 정규식 캡처그룹 `['20']` · 파일 크기 188,416B 일치 ·
> `namespaces=4`. **셋 다 지표를 근거로 쓰기 전에 그게 뭘 세는지 안 봤다.**
>
> ⚠️ **`git` 출력은 비ASCII 경로를 이스케이프하고 전체를 따옴표로 감싼다.**
> `§`가 든 경로는 `"scripts/output/\302\24714-8/foo.md"`가 되어 `grep '\.md$'`에 안 걸린다.
> 2026-08-03 실측 — 68건이 3건으로 세어졌다. **이 레포는 `§` 경로가 다수다.**
> 대안: `git ls-files -z` + `tr '\0' '\n'`, 또는 `git -c core.quotePath=false ls-files`.

**정규식은 자기가 못 보는 것에 침묵한다**
> 파이프라인의 `\[\[(\d+)\]\]`는 그대로 둔다(정본을 전제한 올바른 코드).
> 그러나 **세는 용도로는 정규식을 쓰지 않는다.**
> `re.findall`은 캡처 그룹이 있으면 그룹만 반환한다 — `(19|20)\d{2}` → `['20']`.
> `(?:19|20)\d{2}`로 써야 한다. 조용히 틀린 답이 나오고 에러는 없다.
> **판정은 앵커 문자를 컨텍스트와 함께 전량 덤프해 육안으로 한다.**

**🔴 깨진 명령도 출력을 낸다 (catch BB)**
> zsh에서 따옴표 짝이 어긋나면 `dquote>`(heredoc은 `heredoc>`)로 다음 줄을 계속 먹는다.
> 그 상태로 실행된 명령은 **에러 없이 엉뚱한 인자로 돌아 그럴듯한 출력을 낸다.**
> 실례(2026-08-02) — `.gitignore` 확인 중 `1: 2: 3:`이 출력됐고, 이는
> "1~3행에 `!` 예외가 있다"로 읽히지만 무의미한 값이었다.
> - **`dquote>`·`heredoc>`가 보였으면 그 블록의 전 출력을 폐기하고 재실행한다.**
> - `||` 분기는 **exit code 의미를 확인한 뒤** 쓴다. `git check-ignore`는 `!` 예외 매치에도
>   0을 반환하므로 `cmd || echo "차단 안 됨"`은 작동하지 않는다.
> - 검증은 **부작용 없는 실물 명령**으로. 예: `git add --dry-run <path> | wc -l`
>
> 위 "도구 출력" 항목이 *도구가* 가짜 근거를 만드는 경우라면, BB는 *실행이* 만드는 경우다.

**🔴 grep이 진짜 grep이 아니다 (catch CG)**
> Claude Code 셸 심이 `grep`을 `ugrep -G --ignore-files --hidden`으로 치환한다
> (`type grep`으로 확인). `--ignore-files` = .gitignore 준수.
> 실측 — `grep -rn "CHROMA" --include=".env*" .` → **0건**,
> `command grep` 동일 명령 → **39건**. `.env`·`.env.*`는 `.gitignore:16-17` 대상.
> 쉽게 설명하자면 grep이라는 이름이 다른 프로그램에 연결돼 있다(셸 함수 → ugrep).
> 확인 = `type grep`. 우회 = `command grep`.
> ⚠️ **"비균일"의 근거 2건 중 1건은 해소됐다** — R3b #2가 검출한
> `probe_dist_adtrack.py`·`probe_local_dump.py`는 `.gitignore:110-111` `!` 예외라
> 애초에 ignore 대상이 아니었다(오분류).
> (`:106 probe_*` 아래 `!` 예외는 `:109~:111` 3건 — `probe_Z_extract.py` 포함.)
> ✅ **`Q2 §3.1` 1건도 해소(2026-08-09) — 갈래 ①(다른 경로로 검색).**
> 행번호 `probe_q1_arms.py:481`·`probe_q2_zdouble.py:523`은 **옳다**(실물 대조 일치).
> 미확인의 원인은 검색기가 아니라 **경로 오기**였다 — 두 probe는 `scripts/§research-1/`에 없고
> `writer_project/` 루트에 있다. `scripts/` 하위를 뒤지면 심·실물 **둘 다 0건**이라
> 애초에 양성 대조가 성립하지 않는 검색이었다.
> 루트 기준 재측정 = 심 **16** vs `command grep` **25**(차이 9건), **심에만 있는 행 0건 → 심 동작은 균일하다.**
> (③ 비균일 아님. 상세는 `ad/WORKBOARD.md` 이월표 `Q2 §3.1` 행)
> **배제 조건은 2개다. 둘 다 만족해야 빠진다.**
> - **(1) 재귀 탐색일 것.** 🔴 심 grep은 **명시 경로 인자에는 ignore 대상도 검색한다.**
>   `--ignore-files` 배제는 **재귀 탐색에만** 걸린다
>   (2026-08-08 실측, 1-e 부수 관측 / 08-09 재확인 — `grep -c "EMBEDDING" .env.openai` → 심 **2건** = `command grep` 2건).
>   **따라서 재귀 검색의 0건은 부재의 근거가 아니다.** 파일을 지목해 다시 물어야 한다.
> - **(2) 그 `.gitignore`가 탐색 루트에 있거나 그 아래일 것.** 🔴 **탐색 루트 위의 `.gitignore`는 적용되지 않는다**
>   → **같은 명령이 cwd에 따라 다른 답을 낸다.** 2026-08-09 실측, `grep -rln "RAG_EMBEDDING_MODEL" --include=".env*" .`:
>
> | cwd | 심 grep | `command grep` |
> |---|---|---|
> | 레포 루트 | **0건** | 6건 |
> | `writer_project/` | **4건** (`.env` `.env.openai` `.env.vertex` `.env.anthropic`) | 6건 |
>
> `.env*` 4건은 **레포 루트** `.gitignore:16-17` 대상이라 루트에서 돌리면 빠지고,
> `writer_project/`에서 돌리면 그 규칙이 탐색 루트 위에 있어 **잡힌다.**
> 두 cwd 모두에서 빠지는 `.env.bak_*` 2건은 `writer_project/.gitignore:67 *.bak_*` — 규칙이 안쪽에 있다.
> ⚠️ 그러므로 **"ignore 대상이면 빠진다"는 단독으로 성립하지 않는다.** `git check-ignore`가 잡아도
> 심 grep은 잡을 수 있다 — 두 도구의 `.gitignore` 적용 범위가 다르다.
> ⚠️ 이것은 §9의 **"심 동작이 세션마다 다름(③)"과 다른 건**이다. 심은 균일하게 동작한다.
> 달라지는 것은 **어디서 실행했는가**다.
> - ignore 대상을 찾을 때는 `command grep` 병행. **cwd도 같이 적는다.**
> - 양성 대조는 **대상과 같은 ignore 상태**의 것으로 한다.
>   추적 파일로 대조하면 검색기 생존만 보이고 배제는 안 보인다.

**🔴 탐침이 파이프라인과 다르면 그 측정은 파이프라인을 말하지 않는다 (catch CI)**
> 실측 — 링크 생존 확인에 `HEAD`를 썼더니 404 **14건**, 그런데 **14/14가 한 호스트**였다.
> 완전 일치는 삭제가 아니라 **메서드 거부**의 신호다. `GET` 대조 → 전건 200.
> 파이프라인 실수집은 `ingest_net.py:151 sess.get` = **GET**.
> - **탐침 방법을 파이프라인 실제 동작에 맞춘 뒤 측정한다.** 코드에서 확인하고 시작.
> - 실패가 **한 호스트·한 확장자·한 디렉토리에 몰리면** 그것부터 의심한다.
> CG가 *도구가 이름과 다른* 경우라면, CI는 *도구는 맞는데 방법이 다른* 경우다.

**🔴 요약·대표값·첫 일치를 전수 대신 쓰면 답이 달라진다 (catch CL)**
> **판정에 쓰는 값은 그 값이 전수인지 표본인지를 먼저 밝힌다.**
> 2026-08-09 §research-1 작업 3에서 같은 뿌리의 오판이 **한 세션에 3번** 나왔다.
> - **행번호 하나** — `ingest_docs.py:386`을 `soup` 생성행과 대조해 "2행 어긋남"으로 보고했다.
>   실물은 **태그 제거 행**이었고 지시문이 옳았다. 블록 전체를 안 봤다.
> - **임계 0건** — 본문 대조군이 임계 80에서 0건인 것을 "본문이 없다"로 읽었다.
>   페이지를 열어보니 본문 **2,623자**가 있었고 최대 행이 67자였을 뿐이다(브런치는 문장을 잘게 쪼갠다).
> - **대표 체인 하나** — 한 문구가 본문·크롬 양쪽에 나오는데 집계가 **첫 일치**만 저장하고
>   그것으로 판정했다. 출현 전수로 다시 재니 61 대 11로 갈렸다.
>
> ⚠️ **채널을 가리지 않는다.** 챗도 같은 실수를 했다 — CC 1차 보고를 전수 확인 없이 지시로 올렸고,
> 그 지시(대장 행번호 정정)를 실행했으면 **옳은 기술을 틀리게 고칠 뻔했다.**
> 뿌리가 같다: **요약본이 전수보다 먼저 손에 들어온다.**
> - 판정 근거로 쓰기 전에 **"이건 전수인가 표본인가"**를 한 줄 적는다.
> - 표본이면 전수로 확대할 방법을 먼저 찾는다. 없으면 **표본임을 판정문에 남긴다.**
> - **0건은 특히 위험하다** — 위 "양성 대조 없는 0건은 근거가 아니다"와 같은 계통이다.
> CI가 *방법이 파이프라인과 다른* 경우라면, CL은 *본 것이 전부가 아닌* 경우다.

**🔴 판단 불가는 제3의 칸에 넣는다. 어느 쪽으로도 밀지 않는다 (catch CM)**
> 대조·검증이 성립하지 않아 답을 못 내는 건이 나오면 **"미확정" 칸을 따로 만든다.**
> 다수 쪽에 얹거나 "보수적으로" 한쪽에 몰면 그 순간 수치가 근거를 잃는다.
> 2026-08-09 §research-1 작업 3에서 **두 번** 나왔고, **두 번 다 어느 쪽으로 밀었어도 틀렸다.**
> - **`④-미확정` 5건** — 본문 대조군이 0이라 판정 보류. 나중에 탐침을 고쳐 대조군을 만드니
>   **전량 반대편**(구분가능)이었다. ④로 밀었으면 STOP이 오발동했다.
> - **`(c)` 5건** — 같은 호스트 다른 URL이 0개라 자동/저자 판별 불가. 페이지 2장을 더 받으니
>   **전량 `(b)`**였고 미해결이 5 → 10으로 **2배**가 됐다. `(a)`로 밀었으면 절반을 놓쳤다.
>
> - 미확정 칸의 크기가 **결론을 바꿀 만하면 닫으러 간다.** 위 `(c)`는 *"(b)로 읽으면 10, (a)로 읽으면 5"* —
>   2배라 열어둘 값이 아니었고 **GET 2회**로 닫혔다. 비용을 먼저 재보면 대개 싸다.
> - 닫을 수 없으면 **미확정인 채로 보고한다.** 판정문에 그 수와 "어느 쪽으로도 안 옮겼다"를 남긴다.
> - ⚠️ **닫으러 갈 때 기준을 손대지 않는다.** 바꾸는 것은 **자료(코퍼스)뿐**이다.
>   기준을 같이 바꾸면 자기 채점이 된다. 기준은 분류 착수 **전에** 커밋해 시간 순서를 남긴다.
> CL이 *본 것이 전부가 아닌* 경우라면, CM은 *못 본 것을 본 것처럼 세는* 경우다.
