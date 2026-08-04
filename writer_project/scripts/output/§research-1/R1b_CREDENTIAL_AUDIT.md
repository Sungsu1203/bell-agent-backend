# §research-1 R1b — credential 감사 (🛑 STOP 발동)

- 일자: 2026-08-04
- 선행: `R1_FINDINGS.md` (Track A 완료)
- **결과: 이력 오염 확인 → 프롬프트 §2 규정에 따라 즉시 중단.** §3(포크 diff)·§4(원형 대조) **미착수**
- 비용 $0 · blockagi 실행 0 · 의존성 설치 0 · python 실행 0 · 코드 수정 0
- **표기 규칙: 키 값 전체 노출 금지.** 이 문서에는 커밋 해시·파일 경로·라인번호·변수명만 기록한다

> ⚠️ 선례: `scripts/output/§14-9-A1/credential_exposure_audit.md`(2026-06-01, HEAD `8258f3c`)에
> 동일 성격의 선행 감사가 있다. **그 감사의 결론은 이번 발견을 커버하지 못한다** — 사유는 §3 참조.

---

## 0. 요약 판정

| 대상 | 판정 |
|---|---|
| `~/dev/blockagi-run` (포크) | 🔴 **HEAD 트리에 평문 Google API 키 1건 상주** |
| `bell-agent-backend` (이 레포) | 🔴 **이력에 완전한 `.env` blob 3건** — HEAD는 클린, 이력에만 |
| AWS 키 (`AKIA`) | 🟢 **오탐.** 정식 형식 0건 (vendored `PIL/ImageFont.py`·웹수집 JSON의 우연 문자열) |
| `.gitignore` 현행 차단 | 🟢 정상 (`.env` / `.env.*` / `*.bak` 모두 매칭) |

**두 레포 모두 GitHub private.**
- 이 레포: `https://github.com/Sungsu1203/bell-agent-backend.git` (`git remote -v` 실측)
- 포크: `Sungsu1203/blockagi` (핸드오프 기재. clone 시 자격증명 프롬프트 없이 통과 = 키체인 자격증명 유효)

---

## 1. 🔴 blockagi-run — HEAD에 평문 키 상주

| 항목 | 값 |
|---|---|
| 파일:라인 | `test_google_search_tool.py:38` |
| 형태 | `GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or "<Google API 키 평문>"` |
| 도입 커밋 | `30974b9` — "Initial commit with working code" |
| **HEAD 잔존** | **예.** `git grep AIzaSy HEAD` 히트 — 삭제된 적 없음 |
| 키 형식 | `AIzaSy` + 33자 = **정식 Google API 키 형식 충족** (placeholder 아님) |

부수:
- `.env`가 **커밋된 이력 있음** — `ad89c6d`("Add simple FastAPI")에서 `A`(추가) → `dff46c8`("Rename .env to .env.example")에서 `D`(삭제). **삭제됐어도 blob은 이력에 남는다.**
- 현재 tracked = `.env.example` 1건만
- `.gitignore` = `/.env`, `/.venv/`, `/venv` (3줄) — 현행 차단은 정상
- 전체 커밋 66개, 브랜치 `main` 단일
- `customsearch` 문자열은 `0f1bdbc`("Add google search")에 등장 — **API 엔드포인트 URL**로 보이며 시크릿 아님

### ⚠️ 이 세션 중 발생한 노출 1건 (보고 의무)

`test_google_search_tool.py:38`을 확인하는 명령 하나에서 **마스킹 정규식이 그 줄에 걸리지 않아 키 값이 터미널 출력에 그대로 찍혔다.**
→ **해당 Google API 키는 이 세션 전사(transcript)에 평문으로 남아 있다.** 회전 우선순위를 이 키에 둘 것.
(이후 모든 명령은 `sed -E 's/AIzaSy[A-Za-z0-9_-]{5,}/…/'` 형태로 통일해 재발 없음)

---

## 2. 🔴 bell-agent-backend — 이력에 완전한 `.env` blob 3건

**HEAD 트리는 클린이다** (`git grep -c 'AIzaSy' HEAD` → 0건, 워킹트리 grep → 0건).
문제는 **과거 커밋의 blob**이며, 6개 파일 전부 이후 삭제됐으나 이력에서는 조회 가능하다.

### 2-a. 정식 형식 키를 담은 blob (실측 확인)

| blob | 도입 커밋 | 정식형식 키 | HEAD |
|---|---|---|---|
| `env_text.txt` | `0c59bff1` "Initial commit: GPT Agent source code" | **2건** (Google 1 + Tavily 1) | 삭제됨 |
| `.env.bak` | `ffcdfa30` "dedupe: centralize slugify…" | **2건** (Google 1 + OpenAI 1) | 삭제됨 |
| `chap14-6-legacy/env_backup/.env.origin` | `7ea222d6` "update codes 25-10-18" | **2건** (Google 1 + OpenAI 1) | 삭제됨 |

판정 명령(값 미출력, 건수만):
```bash
git show <commit>:<path> | grep -cE 'AIzaSy[A-Za-z0-9_-]{30,}|sk-proj-[A-Za-z0-9_-]{40,}|tvly-[A-Za-z0-9]{20,}'
```

### 2-b. 값이 채워진 시크릿성 변수 — **prefix 없는 키도 함께 노출됐다**

⚠️ **핵심**: 위 3건은 키 하나가 새어나간 게 아니라 **`.env` 파일 전체가 통째로 커밋된 것**이다.
따라서 `sk-`·`AIzaSy` 같은 식별 가능한 prefix가 없는 값(네이버·SerpAPI 등)도 **전부 노출됐다.**

| blob | 값이 채워진 시크릿 변수 |
|---|---|
| `0c59bff1:env_text.txt` | `GOOGLE_CSE_API_KEY` · `GOOGLE_CSE_ID` · `GOOGLE_APPLICATION_CREDENTIALS` · `TAVILY_API_KEY` · **`NAVER_CLIENT_ID`** · **`NAVER_CLIENT_SECRET`** |
| `ffcdfa30:.env.bak` | `GOOGLE_CSE_API_KEY` · `GOOGLE_CSE_ID` · `OPENAI_API_KEY` · `TAVILY_API_KEY` · **`SERPAPI_API_KEY`** |
| `7ea222d6:chap14-6-legacy/env_backup/.env.origin` | `GOOGLE_CSE_API_KEY` · `GOOGLE_CSE_ID` · `OPENAI_API_KEY` · `TAVILY_API_KEY` · **`SERPAPI_API_KEY`** |

→ **회전 대상 서비스 6종**: Google CSE(key + cx) · Google 서비스계정 경로 · OpenAI · Tavily · SerpAPI · Naver(ID/Secret)

### 2-c. 키를 담지 않은 히트 (오탐 — 회전 불요)

| 파일 | 판정 |
|---|---|
| `105eca9b:env_text.txt` | 정식형식 **0건** — 이 시점 버전은 이미 스크럽됨 |
| `0c59bff1:chap14-6-legacy/env_backup/.env.bak` | 정식형식 **0건** |
| `ba901d3d`/`916a8f1b`:`chap14-6/logs/run_full.log` | 정식형식 **0건** |
| `scripts/output/§14-9-A1/credential_exposure_audit.md` · `§14-9/step_a_…md` · `§14-3/env_flow_matrix.md` · `User Guide/USER_GUIDE.md`·`.html` | **마스킹 표기(`sk-proj-***`)만.** 선행 감사 문서 본인들 |
| `chap06/sec02/tts.ipynb` · `chap14-3/sec04/resources_*.json` · `venv/Lib/site-packages/PIL/ImageFont.py` | `AKIA` 우연 일치. AWS 키 형식 미충족 |

---

## 3. ⚠️ 선행 감사(§14-9-A1)가 이번 발견을 놓친 이유

`scripts/output/§14-9-A1/credential_exposure_audit.md` §1-c는 이렇게 결론지었다:

> `git log --all --oneline -S "<prefix>"` (각 prefix 별 실측) → **5 key 모두 git history 전 구간 노출 0건**

**이 결론 자체는 틀리지 않았다.** 검색한 prefix가 `tvly-k4Rrm` · `sk-proj-9BjSi` 처럼
**당시 현행 키의 앞 5~9자**였기 때문이다.

이번에 발견된 blob들은 **그보다 이전 세대의(이미 회전됐을 수 있는) 키**를 담고 있다.
현행 키 prefix로 검색하면 당연히 0건이 나온다.

> **교훈: 특정 키 값으로 이력을 검색하면 "그 키"의 노출만 판정된다.**
> **파일 단위(`git log -- .env*`)와 형식 정규식(`AIzaSy[A-Za-z0-9_-]{30,}`)으로도 함께 훑어야 한다.**

---

## 4. 🔴 이번 세션 오판 1건 (§9 자기적발)

**중간에 "정식 형식 키 0건 = all clear"를 한 번 보고했고, 그것은 틀렸다.**

```bash
# 잘못된 명령 (cwd = writer_project)
git rev-list --all | while read c; do git grep -lE '<형식>' "$c" -- . ; done
#                                                                  ^^^^
#  `-- .` 가 cwd 기준 → writer_project/ 하위로만 한정
```

문제의 blob들(`env_text.txt` · `.env.bak` · `chap14-6-legacy/…`)은 **레포 루트**에 있어
pathspec 밖으로 밀려났다. **에러 없이 0건**이 나왔다.

CLAUDE.md §9 "도구 출력은 계산 방식을 확인한 뒤 해석한다"의 재현 사례다.
`namespaces=N`이 이름 필터였던 것과 같은 구조 — **무엇을 세는지 확인 전에 근거로 썼다.**

→ 정정 명령: `git show <commit>:<path>`로 **blob을 직접 열어** grep. pathspec 개입 없음.

---

## 5. 판정 대기 항목 (챗 결정 필요 — 파괴적 작업)

이 문서는 **사실만** 싣는다. 아래는 결정 대상이며 제안이 아니다.

| # | 항목 | 성격 |
|---|---|---|
| 1 | 이 세션 전사에 평문으로 남은 Google 키 (blockagi-run `test_google_search_tool.py:38`) | 🔴 즉시성 있음 |
| 2 | `blockagi-run` HEAD의 평문 키 제거 | 커밋 필요 |
| 3 | 두 레포 이력 재작성(`filter-repo` 등) 여부 | **파괴적.** force-push 수반 |
| 4 | 6종 서비스 키 회전 범위 — 이전 세대 키가 아직 live인지 미확인 | 미조사 |
| 5 | `scripts/output/§14-9-A1/credential_exposure_audit.md`의 §1-c 결론 갱신 | 문서 정정 |

⚠️ 이력 재작성은 **두 레포 모두 private**이라는 점, **협업자 유무**, **fork/clone 존재 여부**에 따라
실효가 달라진다. 판단 근거가 이 문서 범위 밖에 있다.

---

## 6. 미착수 (STOP으로 남긴 것)

| 절 | 내용 | 상태 |
|---|---|---|
| §3 | B-1a 포크 diff (모델 교체 · 로직 변경 파일 · `DESIGN_CHOICES.md` 커밋 주인) | **미착수** |
| §4 | B-1b 원형 대조 — Plan ↔ Evaluate 배선 6개 질문 + `citation` 확인 | **미착수** |
| §5 산출 | `R1b_BLOCKAGI_COMPARE.md` | **미생성** |

두 리포는 **clone 완료 상태로 대기 중**이다 (`~/dev/blockagi-ref`, `~/dev/blockagi-run`).
§3·§4는 credential 결정과 **독립적이고 전량 $0 읽기 전용**이므로, 승인 시 즉시 재개 가능하다.

---

## (B) 쉬운 설명층

**무슨 일인가.**
비밀번호에 해당하는 API 키가 **깃 기록 속에 평문으로 남아 있다.** 두 군데다.

- **blockagi 포크**: 테스트 스크립트 안에 구글 검색 키가 **지금도 그대로** 박혀 있다. 파일을 열면 바로 보인다.
- **우리 레포**: 지금 폴더에는 없지만, **과거 커밋에 `.env` 파일이 통째로 들어갔던 적이 세 번** 있다. 파일을 나중에 지워도 깃은 옛날 버전을 계속 보관하므로, 명령 한 줄이면 꺼내볼 수 있다.

**왜 "키 하나"가 아니라 "6종"인가.**
새어나간 게 키 한 줄이 아니라 **설정 파일 전체**다. 그 안에는 구글·오픈AI·Tavily·SerpAPI·네이버 키가 같이 들어 있었다. 구글·오픈AI 키는 `AIzaSy`·`sk-` 같은 고유한 머리글자가 있어 검색으로 찾히지만, 네이버 키처럼 **평범하게 생긴 값은 검색으로 못 찾는다** — 그래서 "파일 전체가 통째로 노출됐다"는 관점으로 봐야 한다.

**과거에 이미 점검했는데 왜 또 나왔나.**
6월에 한 점검은 **"지금 쓰는 키"의 앞 몇 글자로 검색**했다. 이번에 발견된 건 **그보다 옛날 세대의 키**라서, 현행 키로 검색하면 당연히 안 걸렸다. 점검 자체가 틀린 게 아니라 **찾는 방식이 특정 키에만 맞춰져 있었다.**

**솔직히 밝힐 것 두 가지.**
① 확인 과정에서 마스킹이 한 번 새어, **구글 키 값이 이 대화 기록에 그대로 찍혔다.** 그 키를 가장 먼저 교체해야 한다.
② 중간에 "정식 형식 키는 없다 — 이상 없음"이라고 한 번 보고했는데, **그건 검색 범위를 잘못 지정한 탓이었다.** 문제 파일들이 한 단계 위 폴더에 있어서 검색에서 빠졌고, 에러 없이 "0건"으로 나왔다. 파일을 직접 열어 다시 확인해 정정했다.

**다음에 뭘 해야 하나 (결정은 사용자 몫).**
키를 새로 발급받는 일과, 깃 기록에서 옛 파일을 지우는 일은 성격이 다르다. 앞은 되돌릴 수 있고, **뒤는 되돌릴 수 없으며 원격 저장소를 강제로 덮어써야 한다.** 그래서 여기서 멈췄다.

---

## Self-check

- [x] blockagi 의존성을 설치하지 않았다 (`poetry install` 미실행)
- [x] blockagi를 실행하지 않았다 (서버 기동 0회)
- [x] 유료 호출 0건 · python 실행 0건
- [~] **키 값을 이 문서에 옮겨 적지 않았다** — 단 §1 주의: 확인 명령 1건에서 값이 **터미널 출력**에 노출됨(문서에는 미기재). 보고 완료
- [x] `blockagi-ref`(대조 기준)를 수정하지 않았다
- [x] writer_project의 코드·설정을 수정하지 않았다 (이 `.md` 1건 외)
- [x] `git add`를 실행하지 않았다 (`-A`도 물론)
- [x] 보고에 설계 제안이 아니라 사실만 담았다
- [x] 라인번호·커밋해시를 실물 명령으로 재확인했다
- [x] §9 적용 — 선행 감사 문서를 인용 전에 **열어봤고**, 그 결론의 적용 한계를 명시했다
- [x] §9 적용 — 자기 오판(pathspec 범위 오지정)을 §4에 기록했다

---

## 🛑 STOP — 챗 판정 대기

프롬프트 최상단 규정 준수: *"credential 감사에서 이력 오염 발견 시 즉시 중단."*
§3·§4는 승인 시 즉시 재개 가능 (clone 완료, $0 읽기 전용).
