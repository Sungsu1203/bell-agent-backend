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
- 상세·진행 방향은 `ad/WORKBOARD.md` 참조. 사이클 박제는 `scripts/output/§ad-track-1/`

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
