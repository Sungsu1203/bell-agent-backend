# §12-13 γ Step 0-α — entry contract verification (read-only)

**측정 일자:** 2026-05-17
**branch:** `main` (origin synced)
**HEAD:** `fa27769`
**미션:** γ Step 1~N 진입 전 entry phrase contract 식별 (phrase 추정 risk 회피 — code-level routing 단언).
**scope:** read-only, file edit / commit / 환경 변경 0.

---

## § 1. Task 1~4 결과

### 1-1. Task 1 — supervisor routing 식별

#### `extract_write_title()` 정의 — `rag_expression.py:L252-L285`

```python
def extract_write_title(text_like: Any) -> Optional[str]:
    """문자열/멀티모달 입력에서 write/작성/집필 명령의 타이틀을 추출.
    - 명시형: "write: XXX", "작성: XXX", "집필: XXX"
    - 자연어형: "4. XXX 섹션 작성해주세요", "XXX 작성해줘"
    """
```

| 단계 | 패턴 | 위치 |
|---|---|---|
| 명시형 | `RE_WRITE_LINE = r"^\s*(?:write\|작성\|집필)\s*[:：]\s*(.+)$"` | L179-180 |
| 명시형 inline | `RE_WRITE_INLINE = r"(?:^\|[\s().,;])(?:write\|작성\|집필)\s*[:：]\s*(.+?)\s*(?=$\|[\r\n)\]]\|[.;])"` | L182-183 |
| ko-natural | `RE_WRITE_REQUEST_KO` — `<prefix> <idx>. <title>[ 섹션]<을/를> 작성[해줘/...]` | L186-194 |
| `_ENABLE_KO_NATURAL_WRITE` | bool, CFG 기본값 **True** | L195 |
| new-topic 차단 | `RE_NEW_TOPIC.search(text)` 매칭 시 write 해석 금지 | L262-263 |

#### supervisor.py routing 분기 (실측 line ref)

`agent/supervisor.py` (L560-L920 영역):

| L | 분기 | 발화 조건 | 후속 task |
|---|---|---|---|
| **L560-568** | content_strategist (outline 생성) | `is_outline_creation(last_text)` — `(목차\|outline).*(만들\|작성\|새로\|생성)` | `create_outline:{fname}` |
| **L582-589** | web_search (force_query) | `force_query: ...` inline match | `rag_update:auto` |
| **L608-619** | web_search (RAG update) | `_rag_re = r"(최신\|업데이트\|update\|latest).*?(자료\|리소스\|레퍼런스\|참고\|sources\|material).*?(rag\|벡터\|vector\|임베딩\|embedding\|index\|색인\|chroma)"` | `rag_update:auto` |
| **L621-669** | QA-like → topic guard | `_is_qa_like(last_text)` AND `_topic_match_count(last_text)==0` → communicator(`off_topic:qa_like`) / else → vector_search_agent(`qa_query:...`) | (§12-13-1 guard) |
| **L671-711** | new_topic bootstrap | `extract_new_topic_title(last_text)` (RE_NEW_TOPIC hit) | content_strategist + web_search bootstrap |
| **★ L716-743** | **write fast-path (with RAG)** | `_write_title_early = extract_write_title(last_text)` AND `has_on_disk` (RAG exists) | **section_writer + vector_search_agent**, description=`write: {title}` |
| L745-770 | research mode bootstrap | `_is_research_mode_local(state)` | research_planner 등 4 agents |
| L794-799 | content_strategist (outline display) | `is_outline_display(...)` 또는 `is_outline_creation(...)` 2차 | `create_outline:{fname}` |
| **L802-909** | write fast-path (no RAG) | `target_from_line = extract_write_title(last_text)` 2차 호출 — RAG 없을 시 web_search 먼저 + writer pre-schedule | web_search → section_writer |
| L948 | task description 의 write_title 추출 | section_writer pending task description 에서 `requested` 매칭 | (보조) |
| L1044 | research session 끝 write_title 점검 | (보조) | — |

→ **routing 단일성**: γ pipeline 의 핵심 entry = **L716-743 fast-path (write + rag_on_disk)** — `extract_write_title` 발화 + RAG existing 조건 정합. venfobel-vitamin 인덱스 (local 349 + web 17) 보유 → has_on_disk True → 본 분기 발화 보장.

---

### 1-2. Task 2 — outline 로딩 trigger 식별

| 단계 | 위치 | 동작 |
|---|---|---|
| 토픽 preset 로드 | `topics/venfobel-vitamin.env` (실측 read) | `TOPIC_TITLE`, `TOPIC_KEYWORDS`, `TOPIC_SLUG=venfobel-vitamin`, OBJ1~5, MERGE_RETRIEVE_MODE=local_first, RETRIEVE_WEB_RATIO=0.33, RAG_TOP_K=10 — outline_fname 미설정 (default 사용) |
| outline_fname default | `app.py:L1158` + `app.py:L1972-1974` + `agent/section_writer.py:L212` | `"outline_report.md" if config.DOC_MODE == "report" else "outline.md"` — DOC_MODE=report 가정 시 자동 `outline_report.md` 결정 |
| outline 자동 load | `agent/section_writer.py:L210` | `outline_text = get_topic_outline_text(state)` — topic_slug + mode 기반 자동 path 해석 (수동 phrase 불필요) |
| **outline 부재 시 fallback** | `agent/section_writer.py:L211-222` | `outline_text` 빈 경우 → content_strategist(`create_outline:{fname}`) 자동 schedule + section_writer 본인은 skip |

→ **outline 자동 dispatch ★** — `topic_slug` state 에 set 되어 있으면 outline 명시 phrase 불필요. venfobel-vitamin outline 이미 존재 (`outlines/venfobel-vitamin/outline_report.md` — 7 sections, 실측 read 정합) → trigger 부재.

#### venfobel-vitamin outline 내용 (실측 read)

```
## 1. Executive Summary
## 2. 일반의약품 종합비타민 시장 환경 및 규제 변화 분석
## 3. 경쟁사(아로나민·임팩타민) 전략 비교 및 메시지 빈 공간 도출
## 4. 벤포벨S 핵심 차별화 자산 및 광고 클레임 개발 방안
## 5. 3040 직장인 만성피로 인식 및 비타민 구매 행동 분석: '어른들의 비타민' 유효성 검증
## 6. 벤포벨S 2026 광고 및 채널 전략 방향성 제안
## 7. 실행 로드맵 및 핵심 성과 지표(KPI)
```

`_OUTLINE_H2_RE = re.compile(r"^\s*##\s+(?:(\d+)\.\s+)?(.+?)\s*$", re.M)` (`section_writer.py:L146`) → 번호 prefix 자동 분리, 본문 title `Executive Summary` / `일반의약품 종합비타민 시장 환경 및 규제 변화 분석` / ... / `실행 로드맵 및 핵심 성과 지표(KPI)`.

---

### 1-3. Task 3 — multi-section dispatch 조건

#### section_writer `_resolve_title()` — `agent/section_writer.py:L95-L122`

```python
title = _last or next_unwritten_title(
    outline_text or "",
    mode="report",
    root_dir=str(current_path() ...),
    topic_slug=_as_str(state.get("topic_slug")) or None,
    excluded_titles=done,  # 완료 목록 제외
)
```

| 단계 | 동작 |
|---|---|
| `_last = get_last_write_target(messages, tasks)` (L112) | 최근 `write: X` task description 에서 explicit title 회수 |
| `_last in done` 시 → `_last = None` (L113-114) | 이미 완료된 section repeat 차단 |
| `_last` truthy → 직접 사용 (L115) | **single-section write** (explicit) |
| `_last` 부재 → `next_unwritten_title(...)` (L115-121) | outline 의 다음 undone section 자동 추천 |
| `target_title` 부재 → "모든 섹션 초안이 이미 작성되었습니다" + handoff communicator (L259-268) | terminal |

→ **section_writer 는 invoke 당 1 section** 처리. multi-section 자동 loop **부재** ★.

#### supervisor 측 multi-section trigger 부재

- supervisor 의 write fast-path (L720) 가 `extract_write_title(last_text)` 1회 hit 시 1 task 만 schedule
- "모든 섹션 작성" / "전체 섹션" / "all sections" 등 grep 결과 — supervisor / section_writer 내 matching 부재 (별 항목 검출 안 됨)
- iteration_count / research_loop 가 multi-section 으로 발전하는 분기 부재

#### final_report build trigger — `app.py` 명시 phrase 4건

`app.py:L1124-1136` (run_once 진입 직후 fast-path) + `app.py:L2466-2503` (CLI shell loop) 동일:

```python
_u = user_input.strip().lower()
if _u in ("build: report", "report build", "보고서 빌드", "최종 보고서 생성"):
    out_path, missing = build_final_report(
        topic_slug=slug, outline_fname=outline_fname,
        mode=config.DOC_MODE, root_dir=str(current_path)
    )
```

- **LLM 0회** — `report_builder.build_final_report` 는 sections/{slug}/*.md 단순 합본 (`report_builder.py:L279`)
- output: `reports/{slug}/latest.md` (또는 등가 path — `report_builder.py` 추가 read 권장)
- `missing` list 반환 — 누락 section title 식별 가능

#### /api/export endpoint (alt path)

- `app.py:L1944 _api_export_pptx` — pptx kind 만, HTTP-level
- internally `build_final_report` + `plan_deck` + `render_deck` 호출
- γ Step 1~N scope 외 (md → docx/pptx 변환은 별 mission reserve)

---

### 1-4. Task 4 — 과거 성공 invocation 흔적

#### README-dev.md L749-751 (C 미션 실측 흔적)

> 대조군: 같은 의도를 "write: <섹션명>"(explicit hit)으로 입력 시 `[Supervisor fast-path] write + rag_on_disk → vector_search → section_writer` 분기 정확 작동. **7섹션 연속 100% 일관 재현 (06:01:54~06:32:34)**.
> 임시 우회: C 미션은 `write:` 명시형 prefix 사용 시 정상 작동. **7섹션 + report_builder 합본까지 31분에 완수**.

→ **C 미션 = γ 의 직계 선행 cycle** (2026-05-05 검증). 7 explicit `write: <section>` invocation × per-section ~25-30s baseline + final `report_builder` 합본 → **총 ~31분**.

#### α-3 smoke test 흔적 (gamma 가능성 확인)

- input: `write: 도입부 (벤포벨S 광고 콘셉트)` — outline 외 section (free-form title)
- elapsed: 25.8s
- saved: `D:\GPT_AGENT\writer_project\sections\venfobel-vitamin\도입부-벤포벨s-광고-콘셉트.md`
- §12-13-9 (filename slug parens 제거) 재현됨
- → **single-section write fast-path 정합 검증 완료** (`alpha_smoke_test.md` § 3-3)

#### CLI / main entry — `app.py:L2466` shell loop

- console input → `run_once(state, user_input, recursion_limit=args.recursion_limit)` (L2506)
- `recursion_limit` default — script (`scripts/diag/§12-13/rag_update.py:L79`) 에서 `recursion_limit=50` 사용
- `scripts/diag/§12-13/alpha_smoke.py:L92` — `recursion_limit=15` (single QA scope)
- → γ multi-section 시 **recursion_limit=50** 권장 (RAG update 패턴 정합)

#### scripts/output 의 prior end-to-end 흔적

- §12-13/alpha_smoke_test.md, beta_dual_retrieve.md, rag_update_log.md, gamma_step0_meta.json, gamma_end_to_end.md (Step 0 only) — γ 본 단계 박제 부재 (Step 0 까지)
- §14-8/B-3_close.md, B-3_regression_test.md — §14-8 cycle close 박제 (γ 무관)

→ **γ Step 1~N 의 직접 prior 박제 부재** — C 미션 (2026-05-05) 이 ground truth.

---

## § 2. 권장 entry phrase 후보

### 2-1. 단일 entry 부재 박제 ★

본 codebase 에 "outline 의 모든 section 을 1 phrase 로 multi-section dispatch + final report build" 단일 entry **부재 ★** — code-level grep + routing 분석 정합. C 미션 도 7+1 = **8 invocation sequence** 로 진행.

### 2-2. 권장 entry phrase sequence (8 invocations)

#### Phase A — per-section write (7 invocations)

| # | input phrase | supervisor 분기 | section_writer target |
|---|---|---|---|
| 1 | `write: Executive Summary` | L720 fast-path (explicit hit) | "Executive Summary" → file `1-executive-summary.md` (또는 등가 slug) |
| 2 | `write: 일반의약품 종합비타민 시장 환경 및 규제 변화 분석` | 동일 | section 2 |
| 3 | `write: 경쟁사(아로나민·임팩타민) 전략 비교 및 메시지 빈 공간 도출` | 동일 (§12-13-9 — 파일명 괄호 제거 재현 가능) | section 3 |
| 4 | `write: 벤포벨S 핵심 차별화 자산 및 광고 클레임 개발 방안` | 동일 | section 4 |
| 5 | `write: 3040 직장인 만성피로 인식 및 비타민 구매 행동 분석: '어른들의 비타민' 유효성 검증` | 동일 (콜론·따옴표 포함 — `_strip_smart_quotes` 정합 영역) | section 5 |
| 6 | `write: 벤포벨S 2026 광고 및 채널 전략 방향성 제안` | 동일 | section 6 |
| 7 | `write: 실행 로드맵 및 핵심 성과 지표(KPI)` | 동일 (§12-13-9 — 괄호 끝 잘림 risk: `_strip_tail_punct` 짝 매칭 보장, 단 §12-13-9 slug 변환 시 cosmetic 제거) | section 7 |

**code-level 근거**:
- `extract_write_title` 명시형 우선 (rag_expression.py:L266) → 1 hit / KO-natural 우회 risk 부재
- `supervisor.py:L720-743` fast-path: `_write_title_early AND has_on_disk` → section_writer + vector_search_agent 동시 schedule
- `_resolve_title` (section_writer.py:L112) — `_last` (write task description) 우선 → explicit title 직접 사용
- section title 의 번호 prefix (`1.` 등) → `_OUTLINE_H2_RE` (section_writer.py:L146) + `_ensure_section_heading` (L149-185) 가 자동 처리 → ground truth 강제 (§13-13-1 자산)

#### Phase B — final report build (1 invocation)

| input phrase (4건 중 1) | code path |
|---|---|
| **`보고서 빌드`** ★ (권장 1순위 — 한국어 의도 명확) | `app.py:L1124-1136` fast-path → `build_final_report(topic_slug, outline_fname, mode, root_dir)` |
| `최종 보고서 생성` (2순위) | 동일 |
| `build: report` (3순위 — 영어) | 동일 |
| `report build` (4순위) | 동일 |

**code-level 근거**: `_u = user_input.strip().lower()` 기준 case-insensitive match. **LLM 0회**. 결과 = `reports/{slug}/latest.md` (또는 등가 — `report_builder.py:L279` 정밀 read 권장).

### 2-3. 대안 entry — supervisor 측 ko-natural 검토 (skip 권장)

- ko-natural `"7. 실행 로드맵 및 핵심 성과 지표(KPI) 섹션 작성해줘"` 형식도 `RE_WRITE_REQUEST_KO` (L186-194) hit 가능
- 단 `_strip_tail_punct` 짝 매칭 (§13-7 패치) 정합 — `(KPI)` 보존됨
- §12-13-5 README 박제: explicit 와 ko-natural 모두 `extract_write_title` 통일 hit 검증 완료
- **단 risk**: ko-natural 의 보조 패턴은 `섹션`/`을`/`를` 등 조사 매칭 — section title 자체에 조사 포함 시 mis-extract 가능. **explicit `write: <title>` 권장** ★

---

## § 3. 미해소 risk / 의외 발견

### 3-1. 발견 1 — multi-section auto-dispatch 부재

- **risk**: γ Step 1~N "section_writer multi-section dispatch" prompt 표현이 codebase 와 불일치 — 실제로는 user 가 1 section per invocation 진행 필요
- **mitigation**: γ 실행 script (`scripts/diag/§12-13/gamma_run.py` 등) 작성 시 `for section in outline_sections: run_once(state, f"write: {section}", recursion_limit=50)` loop 자동화 가능 — code-level 단일 entry 부재이지만 driver 측 loop 으로 우회 가능
- **권장**: γ Step 1~N hand-off prompt 에 "8 invocation sequence" 명시 → driver loop script 작성 컨펌 필요

### 3-2. 발견 2 — outline_fname 의 DOC_MODE 의존

- `app.py:L1158` 등에서 `"outline_report.md" if config.DOC_MODE == "report" else "outline.md"`
- 본 검증 환경 DOC_MODE 실측 미확인 — `core/config.py` 또는 `.env` 의 DOC_MODE 값 확인 필요
- **mitigation**: γ Step 1 진입 전 `python -c "import core.config; print(core.config.CFG.DOC_MODE)"` 1회 확인 권장
- **mission 차단 X** — DOC_MODE 가 "book" 인 경우 `outline.md` (별 파일) 로 fallback, 그 자체 정상

### 3-3. 발견 3 — §12-13-9 (cosmetic) 재현 영역

- C 미션 §12-13-9: filename slug 에서 괄호 제거 (`(KPI)` → `kpi`)
- section 3 (`경쟁사(아로나민·임팩타민) ...`) + section 7 (`... (KPI)`) 두 곳에서 재현 가능
- **mission 차단 X** — cosmetic, 별 commit 보류 (γ entry prompt 명시 정합)

### 3-4. 발견 4 — section_writer LLM long-tail (§12-13-6)

- `agent/section_writer.py:L305-307`: 90s 임계값 — `_record_llm_call(retry_hint="slow")` 자동 발화
- C 미션 baseline ~31분 / 7 section → **section 당 평균 ~265s** (4.4분) — 본 α-3 의 25.8s 보다 10배 길다. 단 α-3 은 outline 외 section (도입부) + 단일 invoke → 직접 비교 부적합.
- **권장 timeout box (γ prompt 동의 영역)**: section 당 최대 300s (벗어나면 long-tail = priors 17 재현 박제, mission 계속)
- 7 sections × 300s = 2100s = **35분** + build_final_report < 30s + α-3-baseline correction → 총 ~40분 (γ time box 30-45분 정합)

### 3-5. 발견 5 — priors 18 정신 적용

- chromadb collection metadata empty (Step 0 박제) 와 동일 정신:
- "outline title naming convention 단언 전 실측" — 본 § 1-2 의 outline H2 line 실측 read 로 우회 완료
- "extract_write_title behavior 단언 전 code read" — § 1-1 의 rag_expression.py L252-285 실측 read 로 우회 완료
- **priors 18 정신 충족** ★

---

## § 4. 다음 cycle hand-off note

### 4-1. Step 1 진입 조건 확정

| 조건 | status |
|---|---|
| supervisor routing 단일 분기 식별 | ✓ L716-743 fast-path (write + rag_on_disk) |
| outline 자동 load 확인 | ✓ topic_slug 기반 자동 (phrase 불필요) |
| section_writer single-section 동작 확인 | ✓ `_resolve_title` 명시 우선, fallback `next_unwritten_title` |
| multi-section auto-dispatch | **부재** (8 invocation sequence 필요) |
| build_final_report trigger | ✓ 4 phrase 중 `보고서 빌드` 권장 (LLM 0회) |
| outline 실측 (venfobel) | ✓ 7 sections, H2 + 번호 prefix 정합 |
| past invocation 흔적 (C 미션) | ✓ 7+1=8 invocation sequence, ~31분 |
| §12-13-9 재현 영역 | section 3, 7 (cosmetic, 별 commit 보류) |

### 4-2. γ Step 1~N 진행 옵션

**옵션 (A)** — **interactive (사용자 수동 invocation × 8)** — original prompt 정합. 단 시간 ~31분, 사용자 attention 필요.

**옵션 (B)** ★ **권장** — **driver script `gamma_run.py` 작성** (`scripts/diag/§12-13/`). 패턴:
```python
from app import initial_state, run_once
state = initial_state()
sections = [
    "Executive Summary",
    "일반의약품 종합비타민 시장 환경 및 규제 변화 분석",
    # ... 7건
]
for s in sections:
    state = run_once(state, f"write: {s}", recursion_limit=50)
    # per-section state snapshot / timing capture
state = run_once(state, "보고서 빌드", recursion_limit=50)
# build_final_report fast-path (LLM 0)
```
- C 미션 패턴 + α/β/RAG update script 패턴 정합 (`alpha_smoke.py`, `rag_update.py`)
- timing + per-section state JSON 박제 가능 (`gamma_run_log.json`)
- §12-13-9 재현 자동 박제 (saved path 검사)
- priors 17 (long-tail) 자연 박제 + STOP condition 자동 판정 (per-section >300s 등)

### 4-3. 사용자 컨펌 필요 항목

**Q1.** γ Step 1~N 진행 옵션 (A interactive vs **B driver script ★권장**)?

**Q2.** 옵션 B 선택 시 driver script 작성 권한 (write 권한 — 본 cycle 의 read-only scope 외) — γ entry round 에서 자율 작성 OK?

**Q3.** Phase A 의 section title 형식 — explicit `write: <title>` 7건 (권장) vs ko-natural 혼합?

**Q4.** Phase B final build phrase — `보고서 빌드` (한국어 1순위 권장) vs 다른 변형?

**Q5.** §12-13-9 cosmetic — γ 진행 중 자동 박제만 + 별 commit 보류 (γ entry prompt default 동의) OK?

---

## § 5. 본 cycle 종결

| 항목 | 결과 |
|---|---|
| Task 1 supervisor routing | ✓ 8 분기 식별 + write fast-path L720-743 단일성 박제 |
| Task 2 outline 로딩 | ✓ topic_slug 자동 (phrase 불필요), venfobel outline 7 sections 실측 |
| Task 3 multi-section dispatch | ✓ **부재 박제** (1 invoke = 1 section) + final build phrase 4건 |
| Task 4 과거 invocation 흔적 | ✓ C 미션 (2026-05-05) ground truth — 7+1=8 invocation, ~31분 |
| § 2 권장 entry sequence | ✓ Phase A (7 write) + Phase B (1 보고서 빌드) |
| § 3 미해소 risk | 5건 자산화 (mission 차단 X) |
| § 4 hand-off note | ✓ Step 1 진입 조건 확정 + Q1-Q5 컨펌 대기 |

**자율 진행 정지** — Q1-Q5 컨펌 후 γ Step 1~N 진입은 별도 round.

**박제 chain self-contained** — 본 file + `gamma_step0_meta.json` + `gamma_end_to_end.md` (Step 0) + `alpha_smoke_test.md` + `beta_dual_retrieve.md` + `rag_update_log.md` 만으로 γ Step 1~N hand-off prompt 작성 가능.
