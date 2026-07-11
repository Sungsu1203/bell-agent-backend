# CLAUDE.md — bell-agent writer_project 운영 가드레일

> 이 프로젝트 = RAG writer agent 공통 뿌리 + 두 트랙.
> 📄 논문 트랙 = paper/ (WORKBOARD, README-dev-§14).  🏢 회사 트랙 = ad/ (GUARDRAILS, WORKBOARD, README-dev).
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
  - `paper/README-dev-§14.md` = **종결 catch 아카이브(박제)**. 과거 기록 전용. 새 작업 계획은 여기 넣지 않는다.

---

## 1. ⚠️ 토픽 (가장 자주 틀리는 지점 — 실행 전 필수 확인)

- **실제 작업 토픽 = `consumer perceived trademark similarity and likelihood of confusion`**
  (소비자 지각 상표 유사성과 혼동 가능성)
- **env 파일 = `topics/academic-trademark-similarity-consumer.env`**
- ⚠️ **코드/스크립트 기본값이 `influencer marketing`으로 박혀 있다.** 그대로 두면 엉뚱한 토픽으로 측정·커밋.
  → 어떤 측정/fetch를 돌리기 전에 토픽 slug와 로드되는 .env가 **위 값인지 눈으로 확인**하고 시작.

---

## 2. vertex 스킵 규칙

- **`SKIP_VERTEX_SEARCH`는 토픽 `.env` 프리셋이 전역 플래그를 이긴다(preset wins).**
  전역에서 켜도 토픽 .env가 off면 최종 off. 반대도 성립.
- **상표 토픽 = vertex `off` 확정.** (catch 78 — 벤더 껍데기 참조 오염 차단)
- 실파일 기준 라인 = **`:22`** (`:21`은 주석). off-by-one 주의.

---

## 3. 가상환경

- **`../.venv_vertex/bin/python` 사용.** **macOS에서도 정상 동작**(윈도우 전용 아님 — 오해 금지).
- vertex 계열 의존성 = `requirements.vertex.txt`.
- zsh에서 `§`, `*` 포함 경로는 따옴표로 감쌀 것.

---

## 4. 커밋/푸시 범위 (엄수)

- **커밋 대상 = 수정된 `.py` 코드 파일 + `README-dev-§14.md`(+ `WORKBOARD.md`/`CLAUDE.md` 변경분) 만.**
- **제외** = measurement JSON, output 논문, `scripts/output/*` 덤프 (gitignore/관행).
- repo private → NDA push hold **해제됨. push 가능.**
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

---

## 7. 방법론 (§-cycle)

- **R1 정찰(read-only)** → **R2 설계** → **R3 구현+측정**. 유료 API 호출 전 **STOP 게이트**(코드수정 0, 커밋 0 확인).
- catch 인용 시 **항상 한 줄 설명 첨부** — 예: "catch 43(EN 쿼리 → vertex 자동활성 language routing)".
- NEXT_SESSION 파일명: `NEXT_SESSION_<YYYYMMDD>_<§cycle-id>-close.md` (untracked, 일회성. 사용 후 archive/삭제).

---

## 8. 현재 baseline (stale 수치 주의)

- **references = 89 (OA 60 + SS 29).** ⚠️ 77은 catch 78 직후 stale — 이후 catch 74(SS tail-only 복구)가 늘림. 함정.
- axis1 = **1.0 PASS** (complete 44 / partial 45 / missing 0).
- 상세·진행 방향은 `paper/WORKBOARD.md` 참조.
