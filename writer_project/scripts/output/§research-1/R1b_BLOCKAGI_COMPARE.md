# §research-1 R1b — 원형(BlockAGI) 대조

- 일자: 2026-08-05
- 선행: `R1_FINDINGS.md`(Track A) · `R1b_CREDENTIAL_AUDIT.md`(감사)
- 범위: **B-1a 포크 diff + B-1b Plan ↔ Evaluate 배선 1건.** PRUNE 5단계 전체 대조·Narrate 심층·B-2 이식은 범위 밖(§0 판정)
- 비용 $0 · blockagi 실행 0 · 의존성 설치 0 · python 실행 0
- 대조 기준 = **`~/dev/blockagi-ref`** (`orgexyz/BlockAGI` upstream). 포크는 diff 산출에만 사용
- **사실과 대조표까지. 설계 제안 없음** — R2는 챗에서 결정

---

## 1. B-1a 포크 diff

### 1-a. 포크 구조 — 실질 변경이 2 커밋에 뭉쳐 있다

```
git merge-base upstream/master HEAD  →  1632650f   (진짜 fork. 공통 조상 있음)
git log --oneline HEAD..upstream/master | wc -l  →  0   (upstream에만 있는 커밋 없음)
git log --oneline upstream/master..HEAD          →  3건
```

| 커밋 | 내용 |
|---|---|
| `30974b9` | "Initial commit with working code" |
| `ebc9109` | "update codes" |
| `0587a2b` | (오늘 이 세션의 시크릿 제거 — R1b §A) |

→ 포크 전체 67 커밋 중 **upstream 대비 고유분은 2건**(오늘 것 제외). 커밋 메시지가 `update codes` 뿐이라
**"무엇을 왜 바꿨는지"의 커밋 단위 서사는 존재하지 않는다.** diff 내용으로만 역추정 가능.

### 1-b. 🔴 Q1 모델 교체 — **교체 없음. 리포 기준으로 확인 불가**

```
git diff upstream/master...HEAD -- .env.example   →  0줄
.env.example:2  OPENAI_MODEL=gpt-3.5-turbo-16k    (ref · fork 동일)
```

| 확인 대상 | 결과 |
|---|---|
| `.env.example`의 모델 지정 | **ref와 byte 동일.** `gpt-3.5-turbo-16k` 그대로 |
| `main.py`의 모델 주입 | `openai_model: str = typer.Option(envvar="OPENAI_MODEL")` — ref `:172` / fork `:184`. **하드코딩 없음, ENV 주입** |
| 과거 커밋된 `.env`(`ad89c6d`) | `HOST` · `PORT` 2줄뿐. **모델 라인 부재** |
| 코드 내 모델명 하드코딩 | ref·fork 모두 0건 |

> ⚠️ **핸드오프의 전제 "B-1a에서 확인된 교체 모델"은 이 리포에서 성립하지 않는다.**
> 실제 실행 시 어떤 모델을 썼는지는 **커밋되지 않은 로컬 `.env`**에 있었고, 그 파일은
> 이력에 없다(`ad89c6d`의 `.env`는 HOST/PORT만).
>
> → **"모델이 커졌으니 Narrate의 청크 점증 refinement는 유물"이라는 판정의 근거는 이 리포에서 확보되지 않는다.**
> (해당 판정 자체는 챗에서 `ADVANCED_HACKING.md`·`DESIGN_CHOICES.md` 근거로 이미 확정된 것으로,
> 이 절은 **리포가 그 근거를 뒷받침하지 못한다**는 사실만 기록한다.)

### 1-c. Q2 로직을 바꾼 파일

`git diff upstream/master...HEAD --stat` 기준 27파일 / +32,598 −163.

**기존 파일 수정 (7건)**

| 파일 | 변경 규모 | 성격 |
|---|---|---|
| `blockagi/chains/plan.py` | 16줄 | **리터럴만.** `response_format`을 `ResearchTask(...)` dataclass → 순수 dict로. **로직 무변경** |
| `blockagi/chains/research.py` | 2줄 | `tool.run(task.args)` → `tool.invoke(task.args)`. LangChain API 마이그레이션 |
| `blockagi/run.py` | 10줄 | — |
| `blockagi/tools/google.py` | 119줄 | 검색 백엔드 개편 |
| `blockagi/tools/duckduckgo.py` | 62줄 | — |
| `blockagi/tools/visitweb.py` | 87줄 | — |
| `main.py` | 153줄 | — |

**추가 (20건)**: `frontend/**`(Next.js 전체, package-lock 3,184줄) · `requirements.txt`(119줄) ·
`check_env.py` · `get-pip.py`(28,579줄) · `test_google_search_tool.py`

ℹ️ `pyproject.toml`·`poetry.lock`은 **삭제되지 않고 남은 채** `requirements.txt`가 추가됐다 — poetry → pip 병행 전환 흔적.

### 🟢 **대조 안전성 판정 — ref 기준 대조가 유효하다**

이번 대조의 대상 4파일은 **포크 diff에 전혀 등장하지 않는다**:

| 파일 | 포크 변경 |
|---|---|
| `blockagi/chains/evaluate.py` | **없음** |
| `blockagi/chains/narrate.py` | **없음** |
| `blockagi/chains/compose.py` | **없음** |
| `blockagi/schema.py` | **없음** |
| `blockagi/chains/plan.py` | 있으나 **response_format 리터럴 한정** — 프롬프트 본문·input_keys 무변경 |

→ Plan ↔ Evaluate 배선은 **ref = fork**. 아래 §2는 원형 그대로다.

### 1-d. Q3 `DESIGN_CHOICES.md` 커밋 주인 — **원저자. 근거로 사용 가능**

```
git log --follow --format='%h %an %ad %s' --date=short -- docs/DESIGN_CHOICES.md
→  eb57dac  smiled0g  2023-07-03  "Improve docs, minor change on WebUI"
```

| 문서 | ref vs fork |
|---|---|
| `DESIGN_CHOICES.md` · `ARCHITECTURE.md` · `ADVANCED_HACKING.md` · `BUILDING_TOOLS.md` · `PARAMETERS.md` | **5건 전부 동일**(`diff -q` 무차이) |

→ 작성자 `smiled0g`(upstream), 2023-07-03. **Sungsu1203가 추가한 문서 아님.** 대조 근거로 정당.

---

## 2. 🎯 B-1b Plan ↔ Evaluate 배선 (핵심)

### 2-a. 원형의 루프 배선 — 코드 실물

`blockagi/chains/compose.py:52-89`

```python
for step_count in range(self.iteration_count):          # :57
    for chain in self.chains:                            # Plan → Research → Narrate → Evaluate
        outputs = chain(inputs=inputs)
        inputs = outputs                                 # :78  체인 간 직결
    inputs = {                                           # :83-86  ★ 회차 간 배선
        "objectives": outputs["updated_objectives"],
        "findings":   outputs["updated_findings"],
    }
```

→ **Evaluate의 출력이 다음 회차 Plan의 입력으로 물리적으로 대입된다.** 파일 경유 없음. 상태 저장소 없음.

### 2-b. 질문 6개 답

#### Q1 — Plan 프롬프트 입력 변수 전체 목록

`PlanChain.input_keys` = `["objectives", "findings"]` (plan.py:24-28) — **2개.**
그러나 `findings`가 컨테이너이므로 **프롬프트에 실제 렌더링되는 슬롯은 6개**다.

| 슬롯 | 소스 | plan.py 라인 | 위치 | 직전 회차 산출? |
|---|---|---|---|---|
| `## USER OBJECTIVES` | `objectives` | `:59-60` | System | expertise만 갱신 |
| `## GENERATED OBJECTIVES` | `findings.generated_objectives` | `:61-62` | System | **⭕ 예** |
| `## REMARK` | `findings.remark` | `:63-64` | System | **⭕ 예** |
| `## PREVIOUS FINDINGS` | `findings.narrative` | `:70-73` | Human | **⭕ 예** |
| `## RESOURCE POOL` | `resource_pool.get_unvisited()` | `:74-75` | Human | 누적 상태 |
| `## AVAILABLE TOOLS` | `self.tools` | `:76-77` | Human | 고정 |

→ **직전 회차 Findings에서 오는 것 = 3개** (generated_objectives · remark · narrative).

#### Q2 — `remark` 렌더링 형태

- **원문 문자열 그대로.** `f"## REMARK:\n{findings.remark}\n\n"` (plan.py:63-64). 구조화·요약·절단 **없음**
- **코드 길이 제한 없음.** 제약은 생성 측 프롬프트 문안뿐 — evaluate.py:47 `"a note to the next iteration of BlockAGI to help it improve"` + `:86-87` `"Be critical and suggest only concise and helpful feedback"`
- ⚠️ **같은 remark가 Evaluate 프롬프트에도 다시 들어간다**(evaluate.py:69-70). Plan과 Evaluate가 동일 remark를 공유한다
- 초기값 = `""` (run.py:52-56)

#### Q3 — `generated_objectives` 합류 정책 — **대체가 아니라 추가(분리 슬롯)**

- plan.py:59-62가 `## USER OBJECTIVES`와 `## GENERATED OBJECTIVES`를 **별도 섹션으로 분리** 렌더링
- **사용자 목표 수정 금지가 명시**: evaluate.py:85 `"Do not modify the USER OBJECTIVES."`
  단 `expertise` 값은 갱신 대상(`updated_objectives`, evaluate.py:88-89 / :113-119)
- **개수 상한 = 프롬프트 문안 `"Modified up to 1 new GENERATED OBJECTIVE"`(evaluate.py:84).**
  ⚠️ **코드 상한은 없다** — LLM이 반환한 배열을 그대로 `Findings.generated_objectives`에 넣는다(:101-107)
- 초기값 = `[]` (run.py:55) → 회차마다 누적·갱신

#### Q4 — `Objective.expertise`(float)의 실제 사용

| 층 | 실물 |
|---|---|
| **렌더링** | `format_objectives()` → `f"{i+1}. {o.topic} (expertise: {o.expertise})"` (`blockagi/utils/format_data.py:13`) |
| **Plan 지시** | plan.py:86-88 — "Prioritize finding more about topics with **low expertise**" / "When your expertise is **low**, consider finding more resource and gather **generic** information" / "When your expertise is **high**, consider visiting **specific** resources over finding generic answer" |
| **갱신** | evaluate.py:88-89 — "A new expertise weight between (0 and 1) of all the OBJECTIVES. If the goal is close to being met, its expertise should be higher" |

🔴 **코드 분기 0건.** `if expertise > x` 같은 임계 비교·라우팅이 **어디에도 없다.**
스칼라를 **문자열로 프롬프트에 박고 LLM이 알아서 해석**하는 구조다.
`ARCHITECTURE.md`의 "expertise에 따라 넓게/좁게 조사"는 **프롬프트 문안의 기술이지 제어 로직이 아니다.**

#### Q5 — 🔴 Evaluate 출력 파싱 — **구조화 강제. 자유 텍스트 아님**

| 단계 | 실물 |
|---|---|
| 스키마 선언 | `response_format` dict — `updated_findings.{generated_objectives[], remark}` + `updated_objectives[]` (evaluate.py:38-56) |
| 프롬프트 강제 | `"You should ONLY respond in the JSON format as described below"` + `to_json_str(response_format)` (`:71-73`) |
| 파싱 | **`json.loads(response.content)`** (`:98`) |
| 물리화 | 필드명으로 꺼내 dataclass 생성 — `Objective(topic=obj["topic"], expertise=obj["expertise"])`, `remark=result["updated_findings"]["remark"]` (`:100-119`) |
| 실패 처리 | `self.retry_llm(messages)` (`:96`) — 재시도 경로 존재 |
| 배선 선언 | `output_keys` 주석에 **`# Evaluate -> Plan`** 명시 (`:26-30`) |

타입 정의 (`blockagi/schema.py`):
```python
@dataclass
class Objective:  topic: str; expertise: float                    # :6-9
@dataclass
class Findings:   narrative: str; remark: str;                    # :38-42
                  generated_objectives: List[Objective]
```

> 🔴 **이것이 우리와의 결정적 차이다.**
> 원형의 Evaluate 출력은 **처음부터 "다음 회차가 필드로 꺼내 쓸 자료구조"**로 설계됐다.
> 우리 `research_synthesizer` 출력은 마크다운 자유 서술(`## 다음 라운드 조사 포인트`)이라
> **기계가 필드로 꺼낼 수 없다.**
>
> → **배선이 없어서 못 넘기는 게 아니라, 넘길 수 있는 형태가 아니다.**
> 슬롯을 뚫는 것(프롬프트에 변수 추가)만으로는 닫히지 않는 층이다.

#### Q6 — 루프 종료 조건 — **라운드 수 고정. 그것뿐**

```python
for step_count in range(self.iteration_count):   # compose.py:57
```

| 종료 기전 | 원형 |
|---|---|
| 라운드 수 고정 | **⭕ 유일** (`iteration_count`, run.py:60에서 주입) |
| expertise 임계 도달 시 조기 종료 | ✖ 없음 |
| 무수확(신규 URL 0) 감지 | ✖ 없음 |
| `break` / 조기 반환 | ✖ 없음 |

→ expertise는 **탐색 방향만 바꾸고 종료에는 관여하지 않는다.**

### 2-c. 부수 — `ResearchResult.citation`은 **채워진다**

`schema.py:30` `citation: Optional[str] = None` — 스키마 존재. **그리고 실제 대입 경로가 있다.**

```
도구 반환 dict["citation"]  →  research.py:39  citation=task_result.get("citation", None)
                            →  narrate.py     to_json_str(research_results) 로 프롬프트 삽입
                            →  각주 [^1^] 규칙 (narrate.py:109, :111-112)
```

| 도구 | citation 값 | URL 포함? |
|---|---|---|
| `tools/visitweb.py:49` | `f"[{resource.description}]({url})"` | **⭕ 예** — 마크다운 링크 |
| `tools/google.py:42` | `f"Google Search Links: {query}"` | ✖ **쿼리 라벨** |
| `tools/duckduckgo.py:23` `:63` | `f"DuckDuckGo Search Answer/Links: {query}"` | ✖ **쿼리 라벨** |

→ **URL이 실제로 실리는 건 `visitweb` 하나뿐.** 검색 도구 3종은 "무슨 쿼리였나"를 적을 뿐이다.
→ 그리고 이 citation은 **LLM 프롬프트를 경유해 각주로 재생성**된다. 코드가 URL↔각주 1:1을 보증하지 않는다
   (narrate.py:112 `"Preserve all the footnote references"` = **요구형 프롬프트 지시**).

ℹ️ 우리 역추적(`[[N]]` 위치 인덱스 + `attach_marker_citations`의 코드 매핑 + `.refs.json` 사이드카)은
**코드가 보증**한다. **이 항목에서 원형에서 물려받을 것은 없다** (R1 A-⑤와 일치).

---

## 3. 대조표 (산출)

| 항목 | 원형 (`blockagi-ref`) | 우리 (`writer_project`) | 차이 |
|---|---|---|---|
| **Plan 입력 변수** | `input_keys` 2개 → 렌더링 슬롯 **6개**<br>(objectives · generated_objectives · remark · narrative · resource_pool · tools)<br>`plan.py:24-28, :59-77` | **3개**<br>`{topic_title, objective, references}`<br>`prompts.py:589-624` | 🔴 원형이 **직전 회차 산출 3종**을 넘김. 우리는 **0종** |
| **직전 회차 결과 전달** | `compose.py:83-86` — Evaluate 출력을 **다음 Plan 입력에 직접 대입** | **없음.** `last_synthesis`·`findings_md` 소비처 0건 (R1 A-⑤) | 🔴 배선 자체가 부재 |
| **목표 생성 정책** | 사용자 목표 **불변**(수정 금지 명시) + `generated_objectives` **별도 누적**<br>상한 = 프롬프트 "up to 1 new", **코드 상한 없음**<br>`evaluate.py:84-85, :101-107` | env 5개 **고정 순회**<br>`objs[min(rnd, len(objs)-1)]`<br>`research_planner.py:227` | 🔴 원형=자기증식 / 우리=고정.<br>라운드>5면 우리는 5번 목표 반복 |
| **Evaluate 출력 형식** | **JSON 스키마 강제** → `json.loads` → dataclass 물리화<br>`evaluate.py:38-56, :98-119` | **마크다운 자유 서술**<br>`## 다음 라운드 조사 포인트`<br>`prompts.py:653-660` | 🔴 **배선 불가의 진짜 원인.**<br>슬롯만 뚫어선 안 닫힘 |
| **탐색 방향 제어** | `expertise` float를 프롬프트에 문자열로 렌더링<br>**코드 분기 0** — LLM 자율 해석<br>`format_data.py:13`, `plan.py:86-88` | 없음 (목표 순번이 곧 방향) | 원형도 **제어 로직은 아님**. 프롬프트 문안 |
| **루프 종료** | `for _ in range(iteration_count)` **단일**<br>`compose.py:57` | `iteration_count` **+ `no_new_url_streak`**<br>`research_synthesizer.py:185-194, :322` | 🟢 **우리가 더 정교** (무수확 감지 보유) |
| **근거(citation) 보증** | 도구 dict → dataclass 필드 → **프롬프트 경유 각주 재생성**<br>URL 실림은 `visitweb` 1종뿐 | `[[N]]` 위치 인덱스 → **코드가 `refs[N-1]`로 매핑** + `.refs.json` 사이드카(URL+청크 풀텍스트) | 🟢 **우리가 더 강함** |

---

## (B) 쉬운 설명층

**원형은 회차마다 자기 반성문을 "서식"으로 쓴다.**
BlockAGI는 한 바퀴를 돌 때마다 평가 단계에서 세 가지를 남긴다 — ① 스스로 추가한 목표 ② 다음 번 자신에게 남기는 쪽지(remark) ③ 지금까지의 보고서 본문. 그리고 **다음 바퀴의 계획 단계가 이 셋을 그대로 받아 읽는다.** 코드로 `다음_입력 = 이번_출력` 한 줄이 박혀 있다.

**우리도 반성문을 쓴다. 그런데 아무도 안 읽는다.**
우리 요약가도 "다음엔 이 키워드로 찾아보라"를 매 회차 성실히 쓴다. 문제는 그걸 **줄글(마크다운)로 쓴다**는 점이다. 사람은 읽을 수 있지만 프로그램은 거기서 "키워드만 딱 떼어내기"를 못 한다.

원형은 처음부터 **표 채우듯(JSON) 쓰게 강제**하고, 코드가 칸 이름으로 값을 꺼낸다. 형식이 깨지면 다시 쓰게 한다.

> **그래서 "계획가 프롬프트에 슬롯 하나 뚫으면 되지 않나"는 통하지 않는다.**
> 넘길 통로가 없는 게 아니라, **넘길 물건이 줄글이라 담기지 않는** 것이다. 이게 이번 대조의 핵심 발견이다.

**우리가 더 나은 곳도 있다.**
① **언제 멈출지**: 원형은 "5바퀴 돌고 끝"이 전부다. 우리는 새 자료가 안 나오면 멈추는 감지기가 있다.
② **출처 추적**: 원형은 각주를 AI에게 "잘 옮겨 적어라"고 부탁한다. 우리는 번호↔URL 대응을 **코드가 계산**하고, 인용된 원문 덩어리까지 옆 파일에 저장한다. 이 항목은 원형에서 배울 게 없다.

**포크에 대해 알아낸 것.**
- 모델을 바꿨다는 흔적이 **리포에 없다.** 설정 예시 파일은 원본과 글자 하나 안 다르고, 실제 쓰던 설정 파일은 커밋된 적이 없다. → "모델이 커져서 옛 방식이 유물"이라는 판단의 근거를 **이 리포는 대주지 못한다.**
- 바꾼 곳은 주로 **검색 도구 3종과 화면(Next.js)**이고, **핵심 4단계 로직은 원본 그대로**다. 그래서 이번 대조는 원본 기준으로 봐도 안전하다.
- 설계 문서 5종은 **원저자가 2023년에 쓴 것 그대로**다(작성자 `smiled0g`). 근거로 써도 된다.

---

## Self-check

- [x] blockagi 의존성 설치 0 · 실행 0 · 서버 기동 0 · python 실행 0 · 유료 호출 0
- [x] `blockagi-ref`를 수정하지 않았다 (`git status` 클린 확인)
- [x] 대조표는 포크가 아니라 **`blockagi-ref` 기준**으로 작성했다
- [x] 대조 대상 4파일(evaluate·narrate·compose·schema)이 포크 diff에 **없음**을 확인해 ref 기준의 유효성을 입증했다
- [x] 모든 diff/grep 명령에 마스킹 파이프를 적용했다. 키 값 0건 기재
- [x] 라인번호를 실물 파일에서 재확인했다 (문서 기재값 그대로 옮기지 않았다)
- [x] 설계 제안 0건 — 사실과 대조표까지
- [x] 이력 재작성(`filter-repo`·force-push) 미수행

---

## 🛑 STOP — R2 설계는 챗에서 결정
