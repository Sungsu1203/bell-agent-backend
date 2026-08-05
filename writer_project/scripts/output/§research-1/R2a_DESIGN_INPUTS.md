# §research-1 R2-a — 설계 입력 수집

- 일자: 2026-08-05
- 선행: `R1_FINDINGS.md` · `R1b_BLOCKAGI_COMPARE.md`
- 비용 $0 · 읽기 전용 · blockagi 실행 0 · python 실행 0
- **수집물과 인용까지. 설계안·이식안·스키마 제안 0건** — R2 설계는 챗 소관

> **왜 이 수집인가**: R1b D절 결론 — *"배선이 없어서 못 넘기는 게 아니라 넘길 형태가 아니다."*
> R2 과제가 **"슬롯 1개 추가" → "출력 스키마 + 파서 + 슬롯"**으로 확대됐다. 그 설계에 필요한 재료다.

---

## 6-a-1. `research_synthesizer` 프롬프트 전문

`prompts.py:625-673` (`get_research_synthesizer_prompt()`), `PromptTemplate.from_template`

```
역할: Research Analyst
현재 주제(절대 준수): {topic_title}
현재 라운드: {research_round}회차

[리서치 목표]
{objectives}

[목차 구조 (Writer 참고용)]
{outline}

너는 이번 라운드에서 수집된 근거 스니펫을 합성하여
Writer가 바로 활용할 수 있는 **구조화된 Findings 문서**를 작성하라.

[출력 형식 — 반드시 아래 4개 섹션 순서대로]

## 핵심 요점
- 이번 라운드에서 발견한 가장 중요한 사실 3~6개를 불릿으로 정리
- 각 요점은 목차의 어느 섹션에 활용될지 괄호로 표기 (예: [→ 섹션 2])
- 수치/연도가 있으면 반드시 포함, 없으면 생략

## 근거 요약
- 출처별로 묶어서 핵심 내용만 1~2줄로 요약
- 출처명은 대괄호 표기 [출처명]
- 상충되는 정보가 있으면 "A 주장 vs B 주장" 형태로 명시

## 목표별 달성도
{objectives_checklist}
- 각 목표에 대해 "충분 / 부족 / 미확인" 중 하나로 평가
- 부족/미확인이면 다음 라운드에서 추가 조사할 키워드 1~2개 제안

## 다음 라운드 조사 포인트
- 이번 라운드에서 나온 새로운 의문점 또는 데이터 공백 2~4개
- 구체적인 검색 키워드 형태로 작성

[작성 원칙]
- 과장 금지, 근거 없는 주장 금지
- 스니펫에 없는 수치는 절대 생성하지 말 것
- 자료가 부족한 항목은 "(자료 부족)" 명시

[근거 스니펫]
{snippets}
```

`input_variables` = `{topic_title, research_round, objectives, outline, objectives_checklist, snippets}` — **6개**

**`snippets` 생성** (`agent/research_synthesizer.py:198-221`): `docs`를 `_score_doc` 내림차순 상위 **20건**,
`f"- [{src}] {txt}"` 형식. `src = meta.get("source") or meta.get("url") or "unknown"`, `txt = _clean_snip(page_content, 420)`.
→ **입력 단계에서는 URL이 살아 있다.**

**출력 소비** (`:254-274`, `:355-361`): `research/<slug>/round-NN-findings.md` 저장 +
`state["findings_md"]`(경로 리스트) · `state["last_synthesis"]`(본문).
⚠️ **두 키의 소비처 0건** — R1 A-⑤ ④ 참조.

### ⚠️ 프롬프트가 자기모순이다

- 자기 선언: *"**구조화된** Findings 문서를 작성하라"*
- 실제 지정: **마크다운 H2 4개 + 불릿.** 기계가 파싱할 계약(필드명·타입·구분자)은 **0건**
- `prompts.py:525`가 `section_writer`에게 **금지**한 "자체 합성 `[라벨]`"을,
  `:650`은 synthesizer에게 **요구**한다 (`"출처명은 대괄호 표기 [출처명]"`)

---

## 6-a-2. 실제 출력 샘플 — **산출물 실재**

`research/experiential-marketing-media/` — 2026-08-01 15:36/15:37 생성 (ad 트랙 계단 0~2 시절)

| 파일 | 크기 |
|---|---|
| `round-01-findings.md` | 761 B |
| `round-02-findings.md` | 2,423 B |
| `research/venfobel-vitamin/round-01-findings.md` | 4,931 B |

### round-01 (전문)

```markdown
## 핵심 요점
- (자료 부족)

## 근거 요약
- (자료 부족)

## 목표별 달성도
- 목표 1: (자료 부족)
- 목표 2: (자료 부족)
- 목표 3: (자료 부족)
- 목표 4: (자료 부족)
- 목표 5: (자료 부족)

## 다음 라운드 조사 포인트
- 홀브룩 & 허쉬만(1982)와 파인 & 길모어(1998)의 경험적 소비와 경험경제 이론 비교 [검색 키워드: 경험적 소비, 경험경제 이론 비교]
- 슈미트 SEM 모듈의 구체적 실행 사례 [검색 키워드: 슈미트 SEM 사례]
- 체험 효과 측정 방법론 [검색 키워드: 체험 효과 측정, 고객 여정 맵]
- 미디어 형식별 최신 체험 설계 동향 [검색 키워드: 숏폼 콘텐츠 체험 설계, 가상경험 마케팅 동향]
```

### round-02 (전문)

```markdown
## 핵심 요점
- 홀브룩 & 허쉬만(1982)의 경험적 소비 이론은 파인 & 길모어(1998)의 경험경제 4E와 슈미트(1999)의 SEM 이론과 함께 경험 마케팅의 중요한 이론적 기반을 형성한다. [→ 섹션 2]
- 슈미트 SEM의 감각(Sense) 모듈은 사운드 로고와 비주얼 아이덴티티를 통해 감각적 일관성을 설계하며, 이는 브랜드 인지도를 높이는 데 기여한다. [→ 섹션 3]
- 감정 곡선(emotion arc)을 활용한 브랜드 필름은 소비자와의 공감대를 형성하며, 이는 브랜드 충성도를 강화하는 데 효과적이다. [→ 섹션 3]
- 고객 여정 맵과 칙센트미하이의 몰입(flow) 이론은 체험 효과를 측정하고 관리하는 데 유용한 도구로 활용된다. [→ 섹션 5]
- 숏폼 콘텐츠는 노출, 경험, 참여, 관계, 변화의 5단계로 성숙도를 평가할 수 있으며, 이는 브랜드와 소비자 간의 지속적인 관계 형성에 기여한다. [→ 섹션 6]

## 근거 요약
- [홀브룩 & 허쉬만(1982)] 경험적 소비는 환상, 감정, 재미의 3F를 강조하며 정보처리 패러다임을 비판한다.
- [파인 & 길모어(1998)] 경험경제는 엔터테인먼트, 교육, 미적, 현실도피의 4E를 제시하며 경험 연출의 중요성을 강조한다.
- [슈미트(1999)] 전략적 경험모듈(SEM)은 감각, 감성, 인지, 행동, 관계의 5유형을 통해 경험을 제공하는 방법론을 제시한다.
- [숏폼 경험 성숙도] 노출, 경험, 참여, 관계, 변화의 5단계로 구성되며, 각 단계는 브랜드와 소비자 간의 관계를 강화한다.

## 목표별 달성도
- 목표 1: 충분 — 이론적 계보 비교가 명확히 이루어짐.
- 목표 2: 충분 — 감각과 감성 모듈의 실행 사례가 구체적으로 제시됨.
- 목표 3: 부족 — 인지, 행동, 관계 모듈의 구체적 사례가 부족함. 추가 조사 필요.
- 목표 4: 충분 — 체험 효과의 측정과 관리 전략이 명확히 제시됨.
- 목표 5: 충분 — 미디어 형식별 체험 설계와 최신 동향이 잘 설명됨.

## 다음 라운드 조사 포인트
- 인지, 행동, 관계 모듈의 구체적 실행 사례 조사: "인지 모듈 사례", "행동 모듈 사례", "관계 모듈 사례"
- 온·오프 통합 캠페인의 경험 격자 구성 방법: "온오프 통합 캠페인", "경험 격자 구성"
```

### 🔴 샘플이 드러낸 사실 4건 (관찰만)

| # | 관찰 |
|---|---|
| 1 | **`## 근거 요약`의 `[출처명]`이 URL이 아니다.** 입력 스니펫은 `- [{source_url}] …`였는데 출력은 `[홀브룩 & 허쉬만(1982)]` — LLM이 **저자·연도 라벨로 재작성**했다. 역추적 불가 |
| 2 | **키워드 표기 형식이 회차마다 다르다.** round-01 = `[검색 키워드: A, B]` / round-02 = `: "A", "B"`. **프롬프트가 형식을 지정하지 않아 LLM이 매번 자작한다** |
| 3 | `## 목표별 달성도`는 `충분/부족/미확인` **3-값 어휘가 실제로 지켜졌다** — 프롬프트가 값 집합을 명시한 유일한 항목 |
| 4 | round-01은 전량 `(자료 부족)`인데 **`## 다음 라운드 조사 포인트`는 4건 생성**했다. 목표 원문에서 역산한 것으로 보이며 근거 스니펫과 무관 |

⚠️ 2번은 CLAUDE.md §7 "하류 봉합 금지"가 다룬 `[[N]]` 마커 4연패와 **동형**이다 —
프롬프트가 형식을 못 박지 않으면 writer가 자작하고, 하류 정규식으로는 못 따라간다.

---

## 6-a-3. `research_planner` 프롬프트 전문

`prompts.py:589-624` (`get_research_planner_prompt()`)

```
현재 주제: {topic_title}
역할: Research Analyst. 아래 목표를 달성하기 위해 **검색 질의 2~3개**만 작성한다.
(각 질의는 짧고 단순하게, 한 번에 조건을 많이 넣지 말 것)

- 목표: {objective}
- 기존 레퍼런스 개요: {references}

엄격한 작성 규칙:
1) **반드시 한국어**로만 작성한다. 영어 단어/라벨 금지.
2) {topic_title}를 그대로 복사하지 말고, **핵심 키워드 1~2개만** 추려 포함한다.
   (예: 키성장, 건강기능식품, 키성장 건기식)
3) 국내 맥락 키워드(한국|국내|대한민국 중 1+)를 포함한다.
4) **연산자 기본 금지**: 큰따옴표(", 구문검색), +, |, AND/OR, 괄호 연산은 사용하지 않는다.
   - 예외(가능하면 최소): 쇼핑/체험단 노이즈가 확실할 때만 `-체험단` 또는 `-광고` 중 1개만 허용.
5) **도메인 필터(site:)는 기본적으로 사용하지 않는다.**
   - 예외: 정부/공공 통계·규제 문서가 필요할 때만 **한 도메인 1개**(예: site:mfds.go.kr).
6) 최신성이 정말 중요할 때만 **1개 질의에 한해** 연도(예: 2025 2026)를 포함한다.
7) 정보 의도는 서로 다르게 구성한다(예: 통계/보고서, 브랜드 비교, 소비자 고민/후기).
8) 중복 금지. 각 질의는 **25~80자**로 간결하게.
9) 출력 형식: 부호/번호/설명 없이 **한 줄에 쿼리 1개**만.

# 예시(참고용, 출력에 포함 금지):
# 키성장 건강기능식품 시장규모 국내 통계
# 아이커 아이클타임 키성장 건기식 메시지 비교 한국
# 학부모 키성장 고민 부작용 성분 후기 국내

출력:
```

### `input_variables` = **3개** — 정의·주입 위치

| 항목 | 위치 |
|---|---|
| 템플릿 선언 | `prompts.py:589-624`. `PromptTemplate.from_template(tmpl)` `:621` |
| 주입 | `agent/research_planner.py:232-238` |
| `objective` 결정 | `:227` `current_obj = objs[min(rnd, len(objs) - 1)]` |
| `references` 결정 | `:236` `_refs_preview_text(state, max_q=10, max_docs=6)` |
| `topic_title` | `:234` (state/flags/env 통합 헬퍼 `_get_topic_title`) |

```python
queries_text = chain.invoke({
    "topic_title": topic_title,
    "objective":   current_obj,
    "references":  _refs_preview_text(state, max_q=10, max_docs=6),
})
```

⚠️ **`findings`/`last_synthesis`가 들어갈 자리가 없다.** 슬롯 자체가 3개뿐.

**출력 후처리** (`:240-297`): 줄 단위 분해 → 불릿·번호·홀수 따옴표 제거 → 소문자 dedup →
`references.queries` ∪ 직전 `research_plan.queries`와 중복 제거 → 플레이스홀더 치환(`:307-329`) →
`RESEARCH_PLANNER_MAX_Q`(기본 2)로 절단 → `state["research_plan"]` 저장(`:409-414`) + `research_round = rnd+1`(`:416`).

---

## 6-a-4. `.refs.json` 스키마 — **⚠️ 7키. 코드가 쓰는 것은 6키**

### 생성 경로 2단

| 단계 | 시점 | 코드 | 키 |
|---|---|---|---|
| ① 동기 | 섹션 저장 직후 | `utils/refs.py:434 build_marker_refs_map()` → `agent/section_writer.py:321` 캡처 → `:373` 부근 `.refs.json` write | `marker` `url` `label` `text` `source` `title` (**6**) |
| ② **비동기** | 저장 후 daemon thread | `agent/section_writer.py:382 start_background_summarization()` → `utils/chunk_summary.py:161` → `:90 _atomic_merge_summary()` → `:105 entry["summary"] = summary` | **`summary` 추가 (+1)** |

동일 배선이 `agent/chapter_writer.py:291`에도 있다.

> 🔴 **R1 A-⑤에서 `.refs.json`을 6키로 기술했으나 실물은 7키다.**
> 7번째 `summary`는 **별도 LLM 호출**로 사후 병합된다(`chunk_summary.py:67 _summarize_one`).
> 즉 이 파일은 **"비용 0 아님"** — 섹션당 마커 수만큼 요약 호출이 백그라운드로 발생한다.

### 실물 구조 (`sections/venfobel-vitamin/1-executive-summary.refs.json`, 17,591 B, 마커 5건)

```json
{
  "1": {
    "marker":  "1",
    "url":     "file:///…/refs/%EC%A2%85%EA%B7%BC%EB%8B%B9_…pdf",
    "label":   "종근당_팩트북.pdf (4, Index: 4, Chunk 1)",
    "text":    "한국  일반의약품  시장은  노령화  및  만성  질환  관리와 …",   ← 청크 풀텍스트(미절단)
    "source":  "file:///…/refs/%EC%A2%85%EA%B7%BC%EB%8B%B9_…pdf",
    "title":   "종근당_팩트북.pdf (4, Index: 4, Chunk 1)",
    "summary": "건강 및 미용에 대한 소비자들의 높은 관심이라는 메가 트렌드에 따라 …"   ← 비동기 병합
  },
  "2": { … },  "3": { … },  "4": { … },  "5": { … }
}
```

| 키 | 타입 | 출처 | 비고 |
|---|---|---|---|
| (최상위) | `str` | 재할당된 마커 번호 `"1"`,`"2"`… | **본문 등장 순 1-based.** footer `[^N]`과 1:1 |
| `marker` | `str` | 최상위 키와 동일 | 중복 보유 |
| `url` | `str` | `meta["url"] or meta["source"]` | `file://`(로컬, percent-encoded) 또는 `https://` |
| `label` | `str` | `_auto_footnote_label()` (`refs.py:181`) | `title` 우선, 없으면 파일명/도메인. **80자 절단 + `...`** |
| `text` | `str` | `doc.page_content` **풀텍스트** | 절단 없음 |
| `source` | `str` | `meta["source"]` (없으면 `url`) | `url`과 대개 동일 |
| `title` | `str` | `meta["title"]` | 없으면 `""` |
| `summary` | `str` | **LLM 사후 생성** | 없을 수 있음(스레드 미완/실패 시) |

**로컬·웹 혼재 실증**: 마커 1·2·3·5 = `file://` 로컬 PDF/MD, 마커 4 = `https://consumernews.co.kr/…` 웹.
→ **한 사이드카 안에 두 소스 종류가 공존**한다.

**조회 API**: `GET /api/section-refs/{file_id:path}` (`app.py:2134`)

**실재 현황**: `sections/venfobel-vitamin/` 2건만 존재.
`sections/experiential-marketing-media/`(ad 트랙)·`height-growth-supplement-db-strategy/`에는 **사이드카 없음**
(각각 3-b L0 수기 섹션 / 구세대 산출물).

---

## 6-a-5. 라운드 간 유지 state 키

`core/state_types.py` 실측. **LangGraph state는 전 키가 다음 노드로 넘어간다** — 아래는 그중 라운드 의미를 갖는 것.

### 연구 루프 제어 (`:96-121`)

| 키 | 타입 | 갱신처 | 역할 |
|---|---|---|---|
| `research_round` | `int` | `research_planner.py:416` | 라운드 카운터 |
| `iteration_count` | `int` | `supervisor.py:314` (CFG `ITERATION_COUNT`) | 최대 라운드 |
| `research_loop_active` | `bool` | `supervisor.py` 다수 | 루프 활성 |
| **`research_plan`** | `ResearchPlan` = `{round:int, objective:str, queries:List[str], timestamp:str}` (`:23-27`) | `research_planner.py:409-414` | **직전 회차 계획.** planner가 dedup에 자기참조(`:286`) |
| `research_objectives` | `List[str]` | env/CFG | **고정 5개** |
| `planner_queries` | `List[str]` | — | — |
| `research_halt_threshold` · `research_min_rounds` · `research_max_no_new_rounds` | `int` | CFG | 종료 파라미터 |

### 무수확 감지 (`:108-112`) — 원형에 없는 우리 자산

`new_url_count` · `new_url_count_round` · `round_new_urls` · `round_added_urls` (`int`) ·
**`no_new_url_streak`** (`int`, `research_synthesizer.py:185-194` 갱신 → `:322` HALT)

⚠️ 같은 값을 담는 키가 **4개 병존**한다. `research_synthesizer.py:104-144`가 5개 이름을 순차 폴백 탐색한다.

### 자료·산출 (`:75-93`)

| 키 | 타입 | 비고 |
|---|---|---|
| **`references`** | `References` = `{queries:List[str], docs:List[Any]}` (`:16-18`) | **누적. 라운드 간 실질 전달 채널** |
| `refs` | 동일 | 이중 유지 (`vector_search.py:1443-1445`가 둘 다 씀) |
| **`findings_md`** | `List[str]` | 파일 **경로** 리스트. 🔴 **소비처 0건** |
| **`last_synthesis`** | `str` | findings **본문**. 🔴 `research_synthesizer.py:360` 쓰기만, **소비처 0건** |
| `facts_ctx` | `Optional[str]` | 수치 포함 줄 최대 5건 (`vector_search.py:1454-1466`). `section_writer`가 `_facts_block()`으로 소비 |
| `completed_sections` | `list[str]` | writer 루프 방지 |
| `last_saved_path` · `last_saved_report` | `str` | — |

> 🔴 **다음 회차 planner가 실제로 읽는 것은 `references`(상위 6건) + `research_plan.queries`(dedup용) 둘뿐이다.**
> `last_synthesis`·`findings_md`는 state에 실려 다니지만 **누구도 읽지 않는다** (R1 A-⑤ ④).

---

## 6-a-6. 본선 진입 함수 시그니처

> R1 A-⑧ 수집분은 인용. 신규 확인분만 실측 추가.

| # | 함수 | 위치 | 시그니처 |
|---|---|---|---|
| 1 | `vector_search_agent` | `agent/vector_search.py:654` | `(state: State)` — 그래프 노드. 인자 없음, state 경유 |
| 1-보조 | `retrieve` | `tools/web_rag/ingest_vector.py:1534` | `(query, *, top_k=5, namespace=None, collection_name=None, persist_directory=None, embedding=None)` *(R1 A-⑧ 인용)* |
| 1-보조 | `_dual_retrieve` | `agent/vector_search.py:391` | `(query, *, top_k, ns_default, persist_dir) -> List[Any]` |
| 2 | `refs_preview_text` | `utils/refs.py:306` | `(state: Mapping, max_q=5, max_docs=8, snippet_len=350, numbered=False) -> str` |
| 2 | `attach_marker_citations` | `utils/refs.py:360` | `(gathered: str, state: Mapping\|None = None, max_n=20) -> str` |
| 2 | `build_marker_refs_map` | `utils/refs.py:434` | `(gathered: str, state: Mapping\|None = None, max_n=20) -> Dict[str, Dict[str, Any]]` |
| 2-보조 | `start_background_summarization` | `utils/chunk_summary.py:161` | `(sidecar_path: Path\|str, gathered: str, refs_map: Mapping) -> Optional[threading.Thread]` |
| 3 | `section_writer` | `agent/section_writer.py:191` | `(state: State)` — 그래프 노드 |
| 4 | `build_final_report` | `report_builder.py:279` | `(topic_slug: str, outline_fname="outline_report.md", mode: DocMode\|str\|None = None, root_dir: str = str(current_path)) -> Tuple[str, List[str]]` |

⚠️ **1·3은 순수 함수가 아니다.** `state: State` 하나만 받고 필요한 값을 내부에서 꺼낸다.
`refs_preview_text` 계열(2)과 `build_final_report`(4)는 인자로 통제 가능하다
— 3-b가 그래프를 우회해 부품 직접 호출이 가능했던 이유(`R1_FINDINGS.md` A-③).

---

## 6-b. 원형 Evaluate — JSON 스키마 필드 정의 전문

`~/dev/blockagi-ref/blockagi/chains/evaluate.py`. ⚠️ **포크 diff에 없음 = ref와 fork 동일** (R1b §1-c).

### 스키마 선언 (`:38-56`)

```python
response_format = {
    "updated_findings": {
        "generated_objectives": [
            Objective(
                topic="additional objective that helps achieve the user objectives",
                expertise="a new float value in [0, 1] range indicating the expertise of this objective",
            ),
            "... include all generated objectives",
        ],
        "remark": "a note to the next iteration of BlockAGI to help it improve",
    },
    "updated_objectives": [
        Objective(
            topic="same as the user objectives",
            expertise="a new float value in [0, 1] range indicating the expertise of this objective",
        ),
        "... include all objectives",
    ],
}
```

⚠️ 스키마는 **JSON Schema가 아니라 "예시 인스턴스"**다. 필드값 자리에 **설명 문자열**을 넣고
`to_json_str()`로 직렬화해 프롬프트에 박는다(`:73`). 배열은 마지막 원소에
`"... include all generated objectives"` 같은 **의사 지시문**을 끼워 넣어 반복을 표현한다.

| 필드 | 타입 | 프롬프트 내 설명 | 제약 |
|---|---|---|---|
| `updated_findings.generated_objectives[]` | `List[Objective]` | "additional objective that helps achieve the user objectives" | 개수 상한 = 문안 `"Modified up to 1 new"`(`:84`). **코드 상한 없음** |
| `└ .topic` | `str` | — | — |
| `└ .expertise` | `float` | "a new float value in **[0, 1]** range" | **범위 검증 코드 없음** |
| `updated_findings.remark` | `str` | "a note to the next iteration of BlockAGI to help it improve" | **길이 제한 없음.** 문안 `"concise"`(`:87`)뿐 |
| `updated_objectives[]` | `List[Objective]` | "same as the user objectives" | `"Do not modify the USER OBJECTIVES"`(`:85`) — **문안 제약, 코드 검증 없음** |

### 강제 문구 (`:71-73`)

```
"You should ONLY respond in the JSON format as described below\n"
"## RESPONSE FORMAT:\n"
f"{to_json_str(response_format)}"
```

### 파싱 (`:96-119`)

```python
response = self.retry_llm(messages)          # :96
result = json.loads(response.content)        # :98   ← retry 밖

updated_findings = Findings(
    generated_objectives=[
        Objective(topic=obj["topic"], expertise=obj["expertise"])
        for obj in result["updated_findings"]["generated_objectives"]
    ],
    remark=result["updated_findings"]["remark"],
    narrative=narrative.markdown,             # :109  Narrate 출력을 그대로 승계
)
updated_objectives = [
    Objective(topic=obj["topic"], expertise=obj["expertise"])
    for obj in result["updated_objectives"]
]
return {"updated_findings": updated_findings, "updated_objectives": updated_objectives}
```

### 🔴 파싱 실패 시 처리 경로 — **없다**

`blockagi/chains/base.py:55-64`

```python
def retry_llm(self, messages, retry_count=5):
    sleep_duration = 0.5
    for _idx in range(retry_count - 1):
        try:
            return self.llm(messages)          # ← LLM 호출만 감싼다
        except Exception as e:
            self.fire_log(f"LLM failed with error: {e}; Retrying")
            time.sleep(sleep_duration)
        sleep_duration *= 2
    return self.llm(messages)
```

| 실패 유형 | 처리 |
|---|---|
| LLM 호출 예외(네트워크·rate limit 등) | 5회 재시도, 지수 백오프(0.5→1→2→4s) |
| **JSON 형식 위반** | 🔴 **없음.** `json.loads`(`:98`)가 retry 밖 → `JSONDecodeError` 그대로 전파 |
| **필드 누락** | 🔴 **없음.** `result["updated_findings"]["remark"]` → `KeyError` 그대로 |
| **타입 위반** (`expertise`가 문자열 등) | 🔴 **없음.** `Objective`는 `@dataclass`, 런타임 타입 검증 없음 |

> **원형은 "형식을 강제"하지만 "형식을 보증"하지는 않는다.**
> 검증층·복구층이 없고, 위반은 예외로 루프를 죽인다.

### 배선 선언 (`:24-30`)

```python
@property
def output_keys(self) -> List[str]:
    return [
        # Feedback to next iteration
        "updated_findings",     # Evaluate   -> Plan
        "updated_objectives",   # Evaluate   -> Plan
    ]
```

→ 실제 대입은 `compose.py:83-86`. 관련 타입 = `schema.py:6-9`(`Objective`) · `:38-42`(`Findings`).

⚠️ **이식 제안 없음.** 원형이 어떻게 생겼는지만 기록했다.

---

## 7. 수집 중 드러난 사실 정정 2건 (§9)

| # | 대상 | 1차 기재 | 실측 | 반영 |
|---|---|---|---|---|
| 1 | `.refs.json` 스키마 | 6키 (`marker,url,label,text,source,title`) | **7키** — `summary`가 **비동기 LLM 호출**로 사후 병합 (`chunk_summary.py:105`) | 이 문서 §6-a-4 |
| 2 | 원형 Evaluate 실패 처리 | "`retry_llm` — JSON 파싱 실패 시 재시도 경로" | `retry_llm`의 `try`는 **`self.llm()` 호출만** 감싼다. `json.loads`는 밖 | `R1b_BLOCKAGI_COMPARE.md` 각주 `[^ev1]` |

⚠️ 1번은 **비용 함의**가 있다. `.refs.json`을 "비용 0 자산"으로 취급하면 안 된다 —
섹션 저장마다 **마커 수만큼 요약 LLM 호출**이 백그라운드로 발생한다.

---

## 8. 답하지 않은 것 (범위 밖 — 프롬프트 §6-c)

| 항목 | 소관 |
|---|---|
| 스키마 설계안 | 챗 |
| 전용 진입점 코드 | R3 |
| 프롬프트 수정 | 상류 구조 확정 후 |
| `section_writer` 점증 refinement 승계 여부 | R2 설계 시 별도 확인 (`R1b_BLOCKAGI_COMPARE.md` §2-d 미검증 사유 1) |

---

## (B) 쉬운 설명층

**요약가가 쓴 글을 실제로 꺼내 봤다.** 두 회차 분량이 남아 있었고, 예상보다 문제가 선명했다.

첫째, **출처가 사라지는 지점이 눈에 보인다.** 요약가에게 들어간 재료에는 `[https://…]` 같은 주소가 붙어 있었는데, 나온 글에는 `[홀브룩 & 허쉬만(1982)]`처럼 **사람이 읽기 좋은 이름으로 바뀌어** 있다. 읽기엔 낫지만, 이 이름으로는 원래 자료로 되돌아갈 수 없다.

둘째, **"다음에 이걸 찾아보라"의 적는 방식이 회차마다 다르다.** 1회차는 `[검색 키워드: A, B]`, 2회차는 `: "A", "B"`. 아무도 형식을 정해주지 않아 AI가 매번 새로 지어낸 것이다. 이건 예전에 인용 표시(`[[1]]`)에서 네 번 연달아 실패했던 것과 **정확히 같은 종류의 문제**다.

셋째, 반대로 **형식을 지정해준 항목은 잘 지켜졌다.** "충분/부족/미확인 중 하나로 쓰라"고 못 박은 부분은 두 회차 모두 그 셋 안에서만 답했다. → **못 지키는 게 아니라 안 정해줘서 못 지킨 것**이다.

**옆 파일(`.refs.json`)에 대해 하나 정정한다.** 이전에 "칸이 6개"라고 했는데 실제로는 **7개**였다. 일곱 번째 `요약` 칸은 섹션을 저장한 **뒤에 따로 AI를 불러서** 채운다. 그래서 이 파일은 **공짜가 아니다** — 섹션 하나 쓸 때마다 인용 개수만큼 요약 호출이 뒤에서 돈다. 설계할 때 이 비용을 빼먹으면 안 된다.

**원형의 "서식"을 자세히 봤더니 생각보다 허술하다.** JSON으로 답하라고 강하게 요구하지만, **답이 틀렸을 때 고치는 장치가 없다.** 형식이 어긋나면 그냥 오류를 내며 죽는다. 재시도 기능은 있는데 그건 **네트워크가 끊겼을 때**만 작동하고, 형식 오류는 그 바깥에 있다.
→ 즉 원형에서 배울 것은 **"틀을 정해두면 꺼내 쓸 수 있다"**는 점이고, **"틀이 깨졌을 때 어떻게 할 것인가"는 원형도 답을 안 가지고 있다.**

---

## Self-check

- [x] **설계안·이식안·스키마 제안 0건** — 수집물과 인용만
- [x] `R1_FINDINGS.md`에 있는 항목(`retrieve` 시그니처 등)은 **인용 표기**하고 재조사하지 않았다
- [x] 프롬프트·샘플은 **원문 그대로** 옮겼다 (요약·의역 없음)
- [x] 라인번호를 실물 파일에서 재확인했다
- [x] `blockagi-ref` 미수정 · 실행 0 · 의존성 설치 0 · python 실행 0 · 유료 호출 0
- [x] 1차 기재와 실측이 어긋난 2건을 **정정하고 출처 문서에 반영**했다 (§7)
- [x] 시크릿 값 0건 기재

---

## 🛑 STOP — R2 설계는 챗에서 결정
