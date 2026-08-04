# §research-1 R1 — 정찰 결과 (Track A)

- 일자: 2026-08-04
- 범위: **Track A만.** 읽기 전용. 코드 수정 0건 · 파일 생성 1건(이 문서) · 유료 호출 0건
- 기준 HEAD: `53a76a88` (= `origin/main`, 프롬프트 기준 시점과 일치)
- venv: 미사용 (전량 `git grep`/`sed`/`awk` — python 실행 0회)
- **STOP 1 준수** — 설계·수정 제안 없음. 사실과 코드 위치, 그리고 그 사실의 쉬운 설명까지.

> ⚠️ 아래 모든 라인번호는 이번 세션에서 실물 재확인했다. 문서·주석 기재값을 그대로 옮기지 않았다.

---

## 0. 프롬프트 가설 대비 정정 3건 (먼저 읽을 것)

| # | 프롬프트/문서의 기술 | 실물 | 판정 |
|---|---|---|---|
| 0-1 | `agent/graph.py` | **`writer_project/graph.py`** (루트). `agent/`에 `graph.py` 없음 | 경로 정정 |
| 0-2 | `README-dev.md`의 `supervisor.py:L716-743` = write fast-path → "§12-13 시절 기록이라 stale 가능" | **stale 아님. 정확하다.** 주석 `:716-719` + 코드 `:720-743`이 그대로 write fast-path | 🟢 문서가 맞았음 |
| 0-3 | A-⑦ "노드 진입 로그를 삽입할 파일:라인 목록" | **삽입 불요.** 9개 노드 전원이 이미 `emit_event()`를 진입부에서 호출하고, `/api/events`·`/api/state` HTTP 엔드포인트가 이미 존재 | 🔴 최대 발견 중 하나 |

0-2는 §9("기록된 것은 현재가 아니다")를 적용한 결과가 **역으로 나온** 사례다.
재검증 규칙은 "문서는 틀렸다"가 아니라 "문서는 확인 대상이다"이며, 이번엔 통과했다.

**(B) 쉬운 설명** — 세 줄 요약:
① 그래프 설계도 파일은 `agent/` 폴더가 아니라 한 층 위에 있다.
② "옛날 기록이라 못 믿는다"던 줄 번호는 열어보니 지금도 맞았다.
③ 우리 시스템에 "지금 어느 단계인지"를 알려주는 계기판이 **이미 달려 있다.** 새로 달 필요가 없다.

---

## A-① 그래프 실체

**정본 파일 = `graph.py` (writer_project 루트). 그래프 정의는 이 파일 1개뿐.**
(`git grep -ln "add_node"` → `graph.py` 1건. 나머지 1건은 `scripts/output/§14-9/…md` 문서)

### 노드 9개 (`graph.py:97-105`)

| 노드 | 구현 | 토글 상수 |
|---|---|---|
| `supervisor` | `agent/supervisor.py:352` | `ENABLE_SUPERVISOR` |
| `communicator` | `agent/communicator.py:23` | `ENABLE_COMMUNICATOR` |
| `content_strategist` | `agent/content_strategist.py:32` | `ENABLE_CONTENT_STRATEGIST` |
| `vector_search_agent` | `agent/vector_search.py:654` | `ENABLE_VECTOR_SEARCH` |
| `web_search_agent` | `agent/web_search.py:181` | `ENABLE_WEB_SEARCH` |
| `chapter_writer` | `agent/chapter_writer.py:146` | `ENABLE_CHAPTER_WRITER` |
| `section_writer` | `agent/section_writer.py:191` | `ENABLE_SECTION_WRITER` |
| **`research_planner`** | `agent/research_planner.py:27` | `ENABLE_RESEARCH_PLANNER` |
| **`research_synthesizer`** | `agent/research_synthesizer.py:51` | `ENABLE_RESEARCH_SYNTHESIZER` |

→ **두 노드 실재. 전부 기본 enabled**(`graph.py:26-34`, 기본값 `True`).

### 엣지 — 고정 엣지는 2개뿐, 나머지 전부 조건부

| 종류 | 위치 | 내용 |
|---|---|---|
| 고정 | `graph.py:110` | `START → supervisor` (supervisor 비활성 시 `communicator`로 폴백) |
| 고정 | `graph.py:125` | `content_strategist → communicator` |
| 고정 | `graph.py:184` | `communicator → END` (communicator 비활성 시 `supervisor → END`) |
| 조건부 | `:113` | `supervisor` → 8개 노드 전부 (`supervisor_router`, `agent/supervisor.py:997`) |
| 조건부 | `:128` | `research_planner` → 6개 (`after_planner_router`, `core/routers.py:811`) |
| 조건부 | `:138` | `web_search_agent` → 7개 (`after_web_search_agent`, `core/routers.py:461`) |
| 조건부 | `:149` | `vector_search_agent` → 6개 (`after_vector_router`, `core/routers.py:678`) |
| 조건부 | `:158` | `research_synthesizer` → 5개 (`after_synthesizer_router`, `core/routers.py:899`) |
| 조건부 | `:167`/`:174` | `chapter_writer`/`section_writer` → 5개 (`tail_task_router`, `core/routers.py:350`) |

**조건부 진입 여부**: `research_planner` 진입 엣지는 `supervisor`(`:113`)와 `research_synthesizer`(`:158`) 두 곳.
`research_synthesizer` 진입 엣지는 `supervisor`·`research_planner`·`web_search_agent`·`vector_search_agent` 네 곳.
→ **`planner → search → synthesizer → planner` 순환이 그래프 위상에 실재한다.**

### 원본명 잔존 — 코드 25건 (문서·토픽 env 제외)

`BLOCKAGI_*`는 **ENV 키 이름으로만** 남아 있다. 클래스/함수/모듈명에는 0건.

| 파일 | 라인 | 잔존 형태 |
|---|---|---|
| `core/config.py` | `:183` `:186` `:190` `:237-238` `:331-332` `:347` `:429-441` `:470` | `BLOCKAGI_OBJECTIVE_` prefix 상수, `BLOCKAGI_OBJECTIVES` batch 키, `BLOCKAGI_AGENT_ROLE`, `BLOCKAGI_TEST_FAKE_LLM` |
| `agent/research_planner.py` | `:152` `:156` `:172` `:207` | `BLOCKAGI_OBJECTIVE_1..n` 직접 로딩 |
| `agent/supervisor.py` | `:306` `:313` `:322` `:324` `:326` | `BLOCKAGI_AGENT_ROLE`, objectives 로딩 |
| `app.py` | `:486` `:1246` `:1250` `:2330` `:2335` `:2369` `:2371` | role 폴백, `/api/state` objectives 수집 |
| 기타 | `core/llm.py` · `core/state_types.py` · `core/topic.py` | 키 언급 |

토픽 env 5종(`topics/*.env`)이 `BLOCKAGI_OBJECTIVE_1..5`로 목표를 정의한다.
예: `topics/experiential-marketing-media.env:23-27` = 홀브룩&허쉬만 / SEM 감각·감성 / SEM 인지·행동·관계 / 측정 / 미디어 형식별 — **5개 고정.**

**(B) 쉬운 설명** — 원형(BlockAGI)의 흔적은 "설정 항목 이름"에만 남았다. 로직은 전부 갈아엎었고, 목표를 넘겨받는 창구 이름만 옛날 이름 그대로다. 이름만 보고 "원형 구조가 그대로 남았다"고 읽으면 틀린다.

---

## A-② fast-path 진입 조건

### fast-path는 "몇 개"가 아니라 **22개 조기 반환의 사슬**이다

`supervisor()` = `agent/supervisor.py:352-995` (644줄). 이 안에 **`return` 22개**.
각 반환은 `_dash_emit(reason=...)`로 라벨링되어 있고, 위→아래 순서가 그대로 **우선순위**다.

| 순서 | 라인 | reason | 조건 |
|---|---|---|---|
| 1 | `:505` | `off_topic_qa_guard` | Direct QA인데 토픽 키워드 0매칭 |
| 2 | `:527` | `direct_qa_blocked_by_research_mode` | 연구모드 + Direct QA 차단 |
| 3 | `:546` | `direct_qa_fastpath_pending_added` | Direct QA 허용 |
| 4 | `:568` | `create_outline_preempt_qa_like` | 목차 생성 (QA보다 선행) |
| 5 | `:589` | `force_queries` | `force_query:` 감지 |
| 6 | **`:619`** | **`rag_update_fastpath`** | **⭐ "최신자료로 RAG 업데이트"** |
| 7 | `:646` | `off_topic_qa_guard` (2차) | QA-like인데 토픽 키워드 0매칭 |
| 8 | `:669` | `qa_like_new_task` | QA-like → vector_search |
| 9 | `:705` | `new_topic_boot` | 새 주제 감지 |
| 10 | **`:743`** | **`write_rag_fastpath_with_vector`** | **⭐ write 명령 + RAG 있음** |
| 11 | `:756` | `research_loop_end` | 라운드 소진 |
| 12 | **`:771`** | **`research_mode_bootstrap`** | **⭐ 연구 라운드 시작 → research_planner** |
| 13 | `:792` | `research_mode_preempt` | 연구모드 선점 (12와 사실상 중복 블록) |
| 14 | `:800` | (outline create) | 목차 생성 2차 |
| 15 | `:837` | `write_already_completed` | 이미 쓴 섹션 |
| 16 | `:882` | `write_but_refs_empty` | write인데 refs 비었음 → web_search 선행 |
| 17 | `:913` | `write_with_refs` | write + refs 있음 |
| 18 | `:923` | `rename_heading` | 헤딩 이름 변경 |
| 19 | `:929` | `pending_short_circuit` | 미완 태스크 존재 |
| 20-21 | `:974` `:984` | `supervisor_llm_writer` / `writer_skipped` | LLM 라우팅 결과 |
| 22 | `:995` | `supervisor_fallback_route` | 최종 폴백 |

⚠️ **11-13번은 `_is_research_mode_local()` 블록이 두 번 중복 등장한다** (`:745-771`, `:775-792`).
두 번째 블록은 첫 번째가 반드시 선행하므로 **정상 경로에서 도달 불가**로 보인다. 실행 검증은 R3 소관.

### ⭐ "최신자료로 RAG 업데이트" = **6번, 별도 경로다**

`agent/supervisor.py:609-619`

```python
_rag_re = r"(최신|업데이트|update|latest).*?(자료|리소스|레퍼런스|참고|sources|material).*?(rag|벡터|vector|임베딩|embedding|index|색인|chroma)"
if re.search(_rag_re, last_text, flags=re.IGNORECASE):
    # 기존 writer 태스크 전부 done 처리 → web_search_agent 단독 예약
```

- **research_planner를 타지 않는다.** `web_search_agent` 태스크(`rag_update:auto`) 하나만 예약하고 반환.
- 정규식 3부분이 **순서대로 전부** 매칭돼야 한다(`.*?` 연결). "RAG를 최신 자료로 업데이트"는 순서가 어긋나 **미매칭**이다.
- 10번(write fast-path)·12번(연구 라운드)보다 **앞선다** → RAG 업데이트 문구가 섞이면 write/연구 진입이 선점당한다.

### ⭐ 연구 라운드 진입 = 12번 (`:745-771`)

조건 = `_is_research_mode(state)` **AND** 4개 연구 에이전트에 pending 태스크가 하나도 없을 것.
`_is_research_mode`(`:305-309`) = `agent_role`이 research 계열 **또는** `iteration_count > 0`.

**(B) 쉬운 설명** — supervisor는 "생각하는 관리자"가 아니라 **22칸짜리 분류 컨베이어**다. 사용자 문장이 위에서부터 조건에 걸리는 순간 그 칸으로 떨어지고 아래 칸은 못 본다. "최신 자료로 RAG 업데이트해줘"는 6번 칸이라, 12번 칸(연구 라운드 시작)보다 먼저 낚아채간다. 그리고 그 6번 칸은 **웹 검색 한 번만 하고 끝난다** — 계획·합성 없이.

---

## A-③ 3-b가 탄 경로 — **full path도 fast-path도 아니다**

`scripts/output/§ad-track-1/step3b_close_§ad-track-1.md`(tracked, 399줄) 실측:

| 3-b 작업 | 실제 호출 | 그래프 |
|---|---|---|
| L0 조립 | `report_builder.build_final_report()` 직접 | **미경유** (`:57` — "`build_final_report` 호출부는 전부 `app.py`. `graph.py`에는 0건") |
| L1a 섹션 A/B | `get_section_writer_prompt() \| llm \| StrOutputParser()` 직접 | **미경유** (`:106-107` — 노드의 ①제목결정 ③파일저장을 우회, ②프롬프트 실행만) |

→ **3-b는 supervisor를 한 번도 호출하지 않았다.** 부품 직접 호출이다.
그래서 3-b가 관측한 실패(catch AN 참조확대 역효과 · AO 확신도 세탁 · AQ 마커 묶음 소실)는
**전부 프롬프트 층의 실패**이며, 라우팅·fast-path와 무관하다.

`git -c core.quotePath=false ls-files | grep "ad-track-1"` → tracked 5건
(`R0_recon` · `step2` · `step3a` · `step3b` · `step3c` close). NEXT_SESSION 6건은 untracked(관행대로).

**(B) 쉬운 설명** — 3-b는 자동차를 몰아본 게 아니라 **엔진만 작업대에 올려놓고 돌려본 것**이다. 그래서 "3-b가 실패했다"를 "라우팅이 잘못됐다"로 읽으면 안 된다. 엔진(프롬프트)의 문제였다.

---

## A-④ 리포트 산출 형식

### 섹션 정의의 단일 진실원 = 아웃라인 파일의 **H2(`##`)만**

`report_builder.py:302-315` — `outline_text`를 줄 단위로 훑어 `##`로 시작하는 줄만 `titles`에 넣는다.
`###` 이하는 섹션으로 인정하지 않는다. (`section_writer` 프롬프트 `prompts.py:513`의 "상위 헤딩은 딱 한 번"과 대칭)

### 출력 경로

```
outlines/<slug>/outline_report.md            ← 섹션 목록 (H2만)
  ↓ section_writer(state)  [그래프 안]  LLM 1회/섹션
sections|content|chapters/<slug>/<section_slugify(title)>.md   (+ .refs.json 사이드카)
  ↓ build_final_report()   [그래프 밖]  LLM 0
reports/<slug>/<YYYYMMDD-HHMMSS>_report.md  +  latest.md   (둘 다 매 실행 기록)
```

- 탐색 순서 = `_source_dirs()`(`report_builder.py:162`), `CFG.REPORT_SOURCES`로 변경 가능
- 병합은 `SEPARATOR.join(...)` — **섹션 본문을 그대로 이어붙인다**(요약·재작성 없음)
- 옵션 `INCLUDE_FINDINGS_IN_REPORT`가 켜지면 `research|findings/<slug>/round-*-findings.md`를
  `# Appendix: Research Findings`로 말미에 붙인다 (`:113-160`)
- **완성도 게이트 없음** — `missing`이 6/7이어도 리포트를 쓰고 `latest.md`를 덮는다.
  반환값 `(final_path, missing_titles)`의 `missing` 개수로만 판정 가능 (3-b catch AD와 일치)

### 근거 표기 — **있다. 3층으로.**

| 층 | 산출 | 생성 위치 |
|---|---|---|
| 본문 마커 | `[[N]]` (본문 등장 순으로 1,2,3… 재할당) | `utils/refs.py:360 attach_marker_citations` |
| 섹션 말미 footer | `[^N]: <url>  (<label>)` + `### 참고 문헌 / 각주` | 동 `:417-431` |
| 사이드카 JSON | `<section>.refs.json` = `{marker: {url, label, text(청크 풀텍스트), source, title}}` | `utils/refs.py:434 build_marker_refs_map` → `agent/section_writer.py:321` |

⚠️ footer는 `section_writer`가 **저장 전에** 본문에 붙인다(`:326` → `:350 save_md_draft`).
따라서 `build_final_report`가 이어붙이는 시점에 footer는 이미 파일 안에 있고, 최종 리포트까지 살아간다.

⚠️ 프롬프트가 **본문 URL 직접 삽입을 금지**한다 (`prompts.py:526`: "절대로 `file://` 또는 `http://`로 시작하는 URL을 본문에 직접 삽입하지 말 것"). URL은 오직 footer/사이드카로만 나온다 — 설계된 동작이다.

---

## A-⑤ 🔴 근거 사슬 생존 확인 — **최우선 결과**

### 판정표

```
수집 원문 → 청크 metadata → 검색 결과 → key finding → 섹션 본문 → 최종 리포트
    O            O              O           ✖ X           O            O
                                            ↑ 여기서 끊긴다
```

⚠️ 다만 **끊긴 지점이 사슬의 "중간"이 아니다.** 실측 결과 우리 파이프라인은 **한 줄이 아니라 두 갈래**이고, `key finding`은 본선이 아니라 **곁가지**다. 아래가 정확한 형태다.

```
수집 원문 ─→ 청크 metadata ─→ 검색 결과(Document) ─→ state["references"]["docs"]
   O              O                    O                        O
                                                                │
                          ┌─────────────────────────────────────┴──────────────────┐
                          │ (본선)                                    (곁가지)      │
                          ▼                                              ▼
              refs_preview_text(numbered=True)              research_synthesizer
                     → 섹션 본문 [[N]]                          → findings.md
                            O                                        ✖ X
                          ▼                                              ▼
                  footer [^N]: url  +  .refs.json          (writer·planner 아무도 안 읽음)
                            O                                        ✖ X
                          ▼                                              ▼
                     최종 리포트 O                       옵션 Appendix로만 재합류 (원문 그대로)
```

### 구간별 근거 (코드 위치)

**① 수집 원문 → 청크 metadata = O**
- 웹: `tools/web_rag/ingest_docs.py:260 web_results_to_documents()` — `item["source"]|["url"]`, `["title"]`을 `Document.metadata`에 실어 보냄
- 로컬: `tools/local_rag.py:20-28` SSoT 주석 + `_build_local_source()` — `metadata["source"]` = canonical `file://` URI (part/index/chunk fragment 포함), `metadata["source_version"]` = mtime

**② 청크 metadata → 검색 결과 = O**
- `tools/web_rag/ingest_vector.py:1534 retrieve()`가 Chroma Document를 그대로 반환 (metadata 무손실)
- `agent/vector_search.py:492-498`이 오히려 **정보를 추가**한다 — `md["_retrieved_src"]`("web"|"local"|"base"), `md["_retrieved_ns"]`

**③ 검색 결과 → state["references"] = O**
- `utils/refs.py:255 merge_refs()` — Document 객체를 통째로 리스트에 보관. 텍스트로 납작하게 만들지 않는다
- dedup 키는 `_canonicalize_src_for_dedup()`(`:150`) = URL 정규화

**④ 검색 결과 → key finding = ✖ X ← 첫 X**
- 입력은 **살아 있다**: `agent/research_synthesizer.py:212-218`이 `src = meta.get("source") or meta.get("url")`로 `- [{src}] {txt}` 스니펫을 만든다 (상위 20건, 각 420자)
- **출력에서 죽는다**: `prompts.py:648-651`이 요구하는 형식은 `"출처명은 대괄호 표기 [출처명]"` 뿐이다.
  **안정적 식별자(URL·인덱스·chunk id) 계약이 없다.** LLM이 자유 문자열로 출처를 적는다.
  → `prompts.py:525`가 section_writer에게는 "**절대로 `[라벨]` 형식의 자체 합성 명칭을 만들지 말 것**"이라고 금지한 바로 그 행위를, synthesizer 프롬프트는 **요구**하고 있다.
- **그리고 아무도 읽지 않는다**: `findings`는 `agent/research_synthesizer.py:260`에서 `research/<slug>/round-NN-findings.md`로 저장되고, `:274 state["findings_md"]` / `:360 state["last_synthesis"]`에 담긴다.
  전 코드베이스 grep 결과 이 두 키의 **소비처는 0건** — `findings_md`는 `research_synthesizer.py`(쓰기)와 `app.py:492`(초기화)에만, `last_synthesis`는 `:360`(쓰기)에만 등장한다.
  `section_writer`/`chapter_writer`의 프롬프트 입력은 `{target_title, outline, references, messages, topic_title}` 5개뿐(`prompts.py:496-561`) — findings가 들어갈 자리가 없다.
- 유일한 재합류 경로 = `report_builder.py:138 _build_findings_appendix()`가 **디스크의 .md 파일을 그대로 읽어** Appendix로 붙인다. state를 경유하지 않고, 옵션(`INCLUDE_FINDINGS_IN_REPORT`)이며, 내용 가공 없음.

**⑤ state["references"] → 섹션 본문 = O (단, 위치 인덱스에 의존)**
- `utils/refs.py:306 refs_preview_text(numbered=True)` → `- [N] {label} — {snip}` 형식.
  **여기서 LLM에 보이는 건 URL이 아니라 `label`**(title, 없으면 파일명/도메인 — `:181 _auto_footnote_label`)
- 역추적은 **텍스트가 아니라 위치**로 이뤄진다: `attach_marker_citations`(`:419`)가 `refs[orig-1]`로 되짚어 `meta.get("url") or meta.get("source")`를 꺼낸다
- **이 링크가 성립하는 조건 3가지** (전부 깨지기 쉽다):
  1. LLM이 `[[N]]` 정본 형식을 지킬 것 — `_MARKER_RE = r"\[\[(\d+)\]\]"`(`:357`). `[[2], [3]]`은 미매칭 (3-b catch AQ)
  2. `N ≤ min(len(refs), 20)` — 범위 밖은 `:391-393`에서 **조용히 skip**(debug 로그만, 경고 없음)
  3. `references.docs`의 **순서**가 preview 생성 시점과 attach 시점에 동일할 것 (같은 state이므로 현재는 성립)
- ⚠️ **`refs_preview_text`는 `max_docs`(기본 8)로 자르지만 `attach_marker_citations`는 `max_n`(기본 20)까지 본다.** 인덱스 기준이 8 vs 20으로 어긋나 있다. LLM은 1~8만 보므로 현재는 사고가 안 나지만, 두 상한이 다른 소스를 갖는다(`utils/refs.py:315` CFG `REFS_PREVIEW_MAX_DOCS` vs `:360` 인자 기본값)

**⑥ 섹션 본문 → 최종 리포트 = O**
- footer가 저장 전에 본문에 병합되므로(`agent/section_writer.py:326` → `:350`) 파일에 이미 들어 있다
- `report_builder.py`는 `_ensure_section_h2_normalized()`로 H2만 정규화하고 본문은 손대지 않는다
- `.refs.json` 사이드카는 리포트에 병합되지 않지만 **디스크에 남는다** → `/api/section-refs/{file_id}`(`app.py:2134`)로 조회 가능

### 결론

> **URL은 파이프라인 어디서도 소실되지 않는다. 소실되는 건 "본문의 어느 문장이 어느 URL에서 왔는가"이며, 그것도 오직 `research_synthesizer` 쪽 곁가지에서만 그렇다.**
>
> 본선(retrieve → references → section_writer)은 `[[N]]` **위치 인덱스**로 역추적이 살아 있다.
> §2 승부처(역추적)의 자산은 **`.refs.json` 사이드카**다 — 마커별로 URL + **청크 풀텍스트**를 이미 저장하고 있어, 3-b가 필수라고 판정한 "원문 대조"(catch AO)를 파일 하나로 할 수 있다.

**(B) 쉬운 설명** — 자료의 출처(URL)는 수집부터 최종 리포트까지 **한 번도 잃어버리지 않는다.** 다만 본문에는 URL 대신 `[[3]]` 같은 번호표만 찍히고, 번호표 ↔ URL 대응표는 섹션 끝(각주)과 옆 파일(`.refs.json`)에 따로 보관된다. 옆 파일에는 **인용된 원문 덩어리 전체**까지 들어 있다 — "AI가 이 문장을 어디서 가져왔나"를 사람이 확인할 재료가 이미 있다는 뜻이다.
반면 `research_synthesizer`가 만드는 "라운드 요약본"은 출처를 자유 텍스트로 적어서 되짚을 수 없고, **더 중요하게는 그 요약본을 읽는 사람이 아무도 없다.** 파일로만 저장되고 다음 단계로 전달되지 않는다.

---

## A-⑥ 라운드 간 피드백 유무

### 결론: **부분 의존. 단, Evaluate→Plan 되먹임은 없다.**

라운드 N의 planner 입력 = `agent/research_planner.py:232-238`

```python
queries_text = chain.invoke({
    "topic_title": topic_title,
    "objective":   current_obj,                                  # ← objs[min(rnd, len(objs)-1)]  (:227)
    "references":  _refs_preview_text(state, max_q=10, max_docs=6),  # ← 누적 refs 상위 6건
})
```

| 입력 | N-1 회차 결과에 의존? | 근거 |
|---|---|---|
| `objective` | **✖ 아니오** | `:227 objs[min(rnd, len(objs)-1)]` — **토픽 env에 사전 정의된 5개 목표를 라운드 인덱스로 순회.** 평가 결과로 생성/수정되지 않는다. 라운드가 목표 수를 넘으면 **마지막 목표를 계속 재사용** |
| `references` | **⭕ 예** | 누적된 `references.docs` **앞에서 6건** + queries 10건. 웹검색이 새 문서를 넣었으면 반영됨 |
| 쿼리 중복 제거 | **⭕ 예** | `:281-297` — 기존 `references.queries` ∪ 직전 `research_plan.queries`와 겹치면 폐기. **이것이 라운드 간 실질 차별화의 주력** |
| **`last_synthesis` / findings** | **✖ 아니오** | **planner 프롬프트에 findings 슬롯이 없다.** `prompts.py:589-624` `input_variables` = `{topic_title, objective, references}` 3개뿐 |

### 원형(ReAct 계보)과의 결정적 차이

`research_synthesizer` 프롬프트는 **다음 라운드용 산출물을 명시적으로 만든다** — `prompts.py:653-660`:

```
## 목표별 달성도    … "충분/부족/미확인" + 추가 조사 키워드 1~2개 제안
## 다음 라운드 조사 포인트  … 구체적인 검색 키워드 형태로 작성
```

**이 두 섹션은 파일로만 저장되고 planner에 전달되지 않는다.** (A-⑤ ④ 참조)
즉 **Evaluate 단계가 산출물을 만들지만, Plan 단계가 그것을 읽는 배선이 없다.**

### 라운드 제어 변수

| 변수 | 갱신 위치 | 용도 |
|---|---|---|
| `research_round` | `agent/research_planner.py:416` | 라운드 카운터 (`rnd+1`) |
| `iteration_count` | `agent/supervisor.py:314` (CFG `ITERATION_COUNT`) | 최대 라운드 |
| `round_new_urls` | `agent/research_synthesizer.py:104-144` (5개 키 이름 폴백 탐색) | 이번 라운드 신규 URL 수 |
| `no_new_url_streak` | `agent/research_synthesizer.py:185-194` | 연속 무수확 → HALT (`:322`) |

⚠️ **§9(catch BA) 적용 — 코드 주석에 낚이지 말 것.**
`agent/research_planner.py:415-416`:
```python
    # ↓↓↓ 이 라인을 추가해야 합니다. ↓↓↓
    cast(MutableMapping[str, Any], state)["research_round"] = rnd + 1  # <--- 이 라인이 누락됨
```
주석은 "누락됨"이라고 말하지만 **코드는 이미 들어가 있다.** 과거 패치 시점의 잔존 주석이다. 이 주석을 근거로 "라운드가 안 올라간다"고 판정하면 오판이다.

**(B) 쉬운 설명** — 우리 연구 루프는 "**해봤더니 이렇더라, 그러니 다음엔 이걸 파보자**"가 없다. 라운드마다 할 일은 **처음부터 5개로 정해져 있고** 순서대로 하나씩 꺼내 쓴다. 라운드가 6회차가 되면 5번째 목표를 계속 다시 한다.
회차가 달라지는 이유는 딱 두 가지 — ① 그동안 모은 자료 6건이 프롬프트에 붙어서 ② 이미 써먹은 검색어는 버리기 때문이다.
그리고 요약가(synthesizer)는 매 회차 "다음엔 이 키워드로 찾아보라"는 제안을 **성실히 써서 파일로 남기는데, 계획가(planner)가 그 파일을 열어보지 않는다.**

---

## A-⑦ 호출 흔적 프로브 지점 — **삽입 불요 (기존 계기판 발견)**

### 🔴 9개 노드 전원이 이미 진입부에서 `emit_event()`를 호출한다

| 노드 | `emit_event` 라인 | 라벨 |
|---|---|---|
| `supervisor` | `agent/supervisor.py:354` | `"작업 분석"` |
| `content_strategist` | `agent/content_strategist.py:34` | `"목차 구성"` |
| `research_planner` | `agent/research_planner.py:29` | `"조사 계획 수립"` |
| `research_synthesizer` | `agent/research_synthesizer.py:53` | `"참고문헌 정리"` |
| `web_search_agent` | `agent/web_search.py:192` | `"웹 검색"` |
| `vector_search_agent` | `agent/vector_search.py:656` | `"참고문헌 검색"` |
| `chapter_writer` | `agent/chapter_writer.py:153` | `"장 본문 작성"` |
| `section_writer` | `agent/section_writer.py:199` | `"섹션 본문 작성"` |
| `communicator` | `agent/communicator.py:183` | `"응답 정리"` |
| (실행 시작) | `app.py:1364` | `"작업 시작"`, `kind="start"` |

저장소 = `core/events.py:20 emit_event()` / 조회 = `:33 get_events_since(cursor, limit)` (커서 기반, seq·ts 포함)

### 🔴 그리고 HTTP 관측 엔드포인트가 이미 있다 — **원형의 `/api/state`와 동일 구조**

| 엔드포인트 | 위치 | 반환 |
|---|---|---|
| `GET /api/events?cursor=&limit=` | `app.py:2188` | `{ok, next_cursor, events:[{seq, ts, label, kind, detail}]}` |
| `GET /api/state` | `app.py:1231` | `{doc_mode, namespace, pending(태스크수), refs(문서수), last_saved_path, flags, objectives, phase, cancel_requested, iteration_count, updated_at, current_provider}` |
| `GET /api/section-refs/{file_id}` | `app.py:2134` | `.refs.json` 사이드카 조회 |
| `GET /api/logs` | `app.py:2167` | 로그 |
| `POST /api/run` | `app.py:1343` | 실행 트리거 |
| `GET /api/health` `/api/outline` `/api/files` `POST /api/cancel` `/api/export` | `:1195` `:1281` `:2035` `:1271` `:1884` | — |

`web_app = FastAPI(...)` = `app.py:354`. 서버 기동 = `app.py:2236 --serve` (`--host` `--port`, 기본 `127.0.0.1:8000`).

### ⚠️ 다만 `/api/state`로는 A-⑥를 못 본다 — 노출 안 되는 값

`api_state()`(`app.py:1231-1269`)가 반환하지 **않는** 것:
`research_round` · `research_plan`(objective·queries) · `last_synthesis` · `findings_md` · `references.docs`의 실물(개수만 반환) · `no_new_url_streak`.
`objectives`는 **state가 아니라 `os.environ`에서 다시 읽는다**(`:1246-1252`) — 즉 **항상 env 고정값**이며 라운드별 변화를 볼 수 없다.

→ **A-⑥의 실물 증거(라운드별 쿼리 변화)는 `/api/state`가 아니라 다른 데서 봐야 한다.** 무비용 대안 2가지:
1. `research/<slug>/round-NN-findings.md` 파일들 (synthesizer가 라운드마다 자동 저장, `agent/research_synthesizer.py:259-260`)
2. `[Research Planner] Round N objective: … Queries: …` 로그 (`agent/research_planner.py:419-424`, `AIMessage`로도 남음)
3. `core/state_io.py:177 save_state()` — pickle + JSON 스냅샷. 자동 호출 여부는 R3에서 확인

### R3에서 계측기를 **붙인다면** 여기 (지금은 안 붙임)

| 목적 | 위치 | 비고 |
|---|---|---|
| 라우터 판정 근거 | `core/routers.py:350` `:461` `:678` `:811` `:899` | 각 `after_*` 진입/반환 |
| supervisor 분기 | `agent/supervisor.py:274 _dash_emit()` **1곳** | 이미 22개 반환 전부가 이 함수를 경유 → **여기 한 줄이면 전 분기 포착** |
| 노드 일괄 래핑 | `graph.py:64 _add_node()` **1곳** | `fn`을 감싸면 9개 노드 동시 계측 |
| 라운드 상태 | `agent/research_synthesizer.py:306-307` (`dbg` dict) | `round_new_urls`·`no_new_url_streak` 이미 기록 중 |

→ **최소 침습 지점은 `graph.py:64`와 `agent/supervisor.py:274` 단 2곳.**

### 실행 커맨드 초안 (R3용, 아직 실행 금지)

⚠️ 아래는 **초안**이며 STOP 게이트 통과 전 실행하지 않는다.

**공통 전제 — `TOPIC_SLUG` 명시 (catch AB: 미지정 시 논문 프리셋 로드)**

```bash
cd ~/dev/bell-agent/bell-agent-backend/writer_project
export TOPIC_SLUG=experiential-marketing-media      # ad/research 트랙 정본
export PYTHONIOENCODING=utf-8
```

스크립트 최상단(무거운 import보다 **앞**)에 둘 것:

```python
import os
assert os.environ.get("TOPIC_SLUG") == "experiential-marketing-media", \
    f"TOPIC_SLUG 미지정/오지정: {os.environ.get('TOPIC_SLUG')!r} (catch AB — 미지정 시 논문 프리셋 로드)"
# ↑ 검증은 실행으로: TOPIC_SLUG 없이 돌려 AssertionError로 죽고
#   "[Config] 토픽 프리셋 로드" 줄이 안 뜨는 것까지 확인한다.
```

**① 서버 기동 + 이벤트 관측 (계측기 삽입 불요)**

```bash
TOPIC_SLUG=experiential-marketing-media PYTHONIOENCODING=utf-8 \
  ../.venv_openai/bin/python app.py --serve --port 8000 --log-dashboard --log-level INFO
# 별 셸에서:
curl -s 'localhost:8000/api/events?cursor=0&limit=500' | jq '.events[] | {seq,ts,label,kind}'
curl -s localhost:8000/api/state | jq -S .
```

**② 대표 명령 3종 — 어느 fast-path 칸으로 떨어지는지 판정**

`POST /api/run`(`app.py:1343`)의 요청 스키마는 **R3 진입 시 확인 후 확정**한다(이번 사이클 미확인).
판정은 응답이 아니라 `/api/events`의 라벨 순서로 한다.

| # | 입력 문장 | 예상 칸 (A-② 표) | 예상 이벤트 순서 |
|---|---|---|---|
| 1 | `최신 자료로 RAG 업데이트해줘` | 6번 `rag_update_fastpath` | 작업 분석 → 웹 검색 |
| 2 | `write: 2. 감각과 감성 모듈` | 10번 or 17번 (refs 유무) | 작업 분석 → (참고문헌 검색) → 섹션 본문 작성 |
| 3 | (`ITERATION_COUNT=3` 설정 후) 일반 지시 | 12번 `research_mode_bootstrap` | 작업 분석 → 조사 계획 수립 → 웹 검색 → 참고문헌 정리 → … |

⚠️ **3번은 유료 루프다.** `ITERATION_COUNT`를 **최소값으로 고정**하고 STOP 3에서 비용 승인 후 실행.
⚠️ 1번은 정규식 어순 의존(A-② 참조) — `RAG를 최신 자료로 업데이트`로 쓰면 **미매칭**되어 다른 칸으로 떨어진다. 문안을 바꾸지 말 것.

**③ 무비용 사전 확인 ($0, R3 진입 즉시 가능)**

```bash
# fast-path 분기만 확인 — LLM 호출 전 supervisor 반환값을 보는 경로
git grep -n "def run_once\|_WEB_STATE\|_RUN_LOCK" -- app.py | head
ls -la research/experiential-marketing-media/ 2>/dev/null   # 과거 라운드 findings 잔존 여부
ls -la sections/experiential-marketing-media/*.refs.json 2>/dev/null  # 사이드카 실물
```

---

## A-⑧ 🔴 `tools/` 엔진의 독립성

### 1. `tools/` → `agent/` 역참조 = **0건. 분리 가능.**

```
git grep -n "from agent\|import agent\." -- tools/    →  0줄
```

`tools/` 어느 파일도 supervisor·graph·노드를 import하지 않는다. **한 건도 없다.**

### 2. `tools/` → `core/` 의존 = 있다. 단 **3모듈로 좁혀지고, 그 3모듈은 그래프를 모른다.**

| tools 파일 | 의존 |
|---|---|
| `tools/local_rag.py:67-69` | `core.config.CFG` · `reload_config` · `core.paths` |
| `tools/web_rag/ingest_config.py:13-14` | `core.config.CFG` · `reload_config` |
| `tools/web_rag/ingest_vector.py:63` | `core.llm.get_embedding_model` |
| `tools/web_rag/search.py:41-42, 263` | `core.config` · `core.paths.research_base_dir` |
| `tools/web_rag/utils.py:45, 624` | `core.config` · `core.paths` |
| `tools/metrics.py:20, 28` | `core.config.CFG` · `core.paths` |
| `tools/eval_embedding_models.py:42`, `sample_chunks_for_eval.py:24`, `sanity_check_gemini_embedding.py:7`, `diagnose_embed_validate.py:29` | `core.config.load_topic_env` |

**필요한 core 모듈은 4개뿐: `config` · `models` · `paths` · `llm`.** 이들의 의존은:

```
core/config.py  → core/models.py                            (그 외 표준 라이브러리만)
core/llm.py     → core/config.py
core/paths.py   → core/config.py + utils/text_utils.py
core/models.py  → (없음)
```

**`core/` → `agent/`·`graph` 역참조도 0건**(`git grep "from agent\|from graph" -- core/` → 0줄).
`core/routers.py`·`core/state_types.py`는 그래프 전용이지만 **`tools/`가 import하지 않는다.**

→ **답: 예. `core/`를 통째로 뗄 필요 없이 4개 모듈만 떼면 된다.**

**추가 의존 1건 (주의)**: `tools/`가 **writer_project 루트 모듈 `settings_gatekeep.py`**를 import한다
(`tools/web_rag/ingest_vector.py:66`, `tools/web_rag/search.py:266, 275, 1368`).
루트 스크립트라 패키지 경계 밖 — 라이브러리화 시 함께 옮겨야 한다.

**최소 이식 세트** = `tools/` + `core/{config,models,paths,llm}.py` + `utils/text_utils.py` + `settings_gatekeep.py`

### 3. 검색·색인·retrieve 공개 진입 함수

패키지 표면 = `tools/web_rag/__init__.py:63-93` (7개를 `*args, **kwargs` 얇은 래퍼로 재노출.
`_call_maybe_tool`(`:22`)이 LangChain `BaseTool` 인스턴스도 흡수)

| 함수 | 실구현 | 시그니처 |
|---|---|---|
| `retrieve` | `tools/web_rag/ingest_vector.py:1534` | `(query, *, top_k=5, namespace=None, collection_name=None, persist_directory=None, embedding=None)` |
| `web_search` | `tools/web_rag/search.py:1336` | (인자 다수 — R3에서 필요 시 확인) |
| `web_results_to_documents` | `tools/web_rag/ingest_docs.py:260` | `(results: Sequence[Dict]) -> List[Document]` |
| `documents_to_chroma` | `tools/web_rag/ingest_vector.py:775` | — |
| `add_web_pages_json_to_chroma` | `tools/web_rag/ingest_vector.py:1442` | — |
| `clear_vector_store` | `tools/web_rag/ingest_vector.py:654` | `(namespace=None, persist_directory=None) -> str` |
| `ensure_vector_store_cleared_once` | `tools/web_rag/ingest_vector.py:744` | — |

보조(패키지 `__init__` 미노출, 직접 import 필요):
`add_documents_to_chroma`(`:1502`) · `has_any_docs`(`:1403`) · `get_collection_count`(`:1715`) ·
`get_total_collection_count`(`:1769`) · `seed_web_namespace`(`:1789`) · `split_documents`(`:408`) · `_default_chroma_dir`(`:262`)

로컬 색인 진입 (`tools/local_rag.py`, `__all__` = `:59`):
`build_webjson_from_local`(`:1207`) · `ingest_local_files`(`:1387`) ·
`add_local_findings_to_chroma`(`:1605`) · `quick_ingest_findings`(`:1661`) · `ensure_config_fresh`(`:235`)

### 4. 전역 상태 — **import만으로는 부족하다. 순서 의존이 있다.**

| 유형 | 위치 | 내용 |
|---|---|---|
| 🔴 **import 시점 ENV 동결** | `tools/web_rag/utils.py:311-314` | `PROJECT_ROOT` · `DATA_DIR`을 `_cfg_str()`로 **모듈 로드 시** 확정 |
| 🔴 **import 시점 ENV 동결** | `tools/web_rag/utils.py:664-673` | `_MIN_RESULTS_OK` · `_BACKEND_PICK_POLICY` · `_SEARCH_TOPN` · `_LOG_TOPK` · `_LOG_WRAP` |
| 🔴 **import 시점 ENV 동결** | `tools/web_rag/utils.py:749-754` | URL 정규화 플래그 6종 |
| 런타임 재로드 훅 | `tools/local_rag.py:157-158, 235-241` | `_RELOAD_ONCE_FLAG` + `threading.Lock` — `ensure_config_fresh()`가 1회만 `reload_config()` |
| 지연 바인딩 슬롯 | `tools/local_rag.py:78-79`, `tools/web_rag/search.py:46` | `_wr_resolve_persist_dir` · `_wr_sanitize_ns` · `_load_urls_as_documents` = `None` 초기화 후 런타임 주입 |
| 1회성 로그 가드 | `ingest_vector.py:1514` `global _LOGGED_ALIAS_ONCE` | — |
| 서킷브레이커 | `ingest_vector.py:1860-1877` `_ROUND_FAIL_LIMIT=2` | 호스트별 실패 누적 |
| HTTP 세션 싱글턴 | `tools/web_rag/utils.py:166` `global session` | — |
| **런타임 ENV 직독** | `ingest_vector.py:1603-1605` | `retrieve()`가 **호출 시점에** `RAG_DISTANCE_THRESHOLD`(기본 `0.65`) · `FILTER_BAD_DOMAINS`를 `os.environ`에서 읽음 |

**판정**: `import tools.web_rag` 만으로 동작하지만, **`.env`/`TOPIC_SLUG`를 import보다 먼저 세팅해야 한다.**
`utils.py`의 상수들은 import 이후 env를 바꿔도 **반영되지 않는다.**
반면 `retrieve()`의 임계값은 호출 시점 읽기라 **런타임 변경이 먹는다** — 두 정책이 한 패키지 안에 섞여 있다.

⚠️ 이 확인은 **읽기 전용 판정**이며 어떤 수정도 제안하지 않는다. `tools/`는 논문 트랙과 공유한다.

**(B) 쉬운 설명** — 검색·색인 엔진(`tools/`)은 **에이전트 쪽을 전혀 모른다.** 그래서 통째로 떼어내 다른 프로그램에서 부품으로 갖다 쓸 수 있다. 같이 따라오는 짐은 설정·경로·임베딩 담당 4개 파일과 도메인 허용목록 파일 하나뿐이다.
단 하나 주의점: 이 엔진은 **불러오는 순간 설정값을 사진 찍듯 굳혀버리는 항목**이 있다. 그러니 "설정 먼저, 불러오기 나중" 순서를 어기면 조용히 옛날 값으로 돈다.

---

## 1. 이번 사이클 최대 발견 3건 (챗 판정용 요약)

| # | 발견 | 영향 |
|---|---|---|
| **1** | **근거 사슬은 본선에서 안 끊긴다.** X는 `research_synthesizer` 곁가지 1곳뿐이고, 그 곁가지는 **아무도 읽지 않는다**(`last_synthesis`·`findings_md` 소비처 0건). 본선은 `[[N]]` 인덱스 + `.refs.json` 사이드카(URL + **청크 풀텍스트**)로 살아 있다 | §2 역추적의 자산은 **이미 존재**. 신규 구축 불요 |
| **2** | **Evaluate→Plan 되먹임 배선이 없다.** synthesizer가 "다음 라운드 조사 포인트"를 매 회차 생성하지만(`prompts.py:658-660`) planner 프롬프트에 슬롯이 없다(`input_variables` 3개). 목표는 토픽 env의 **고정 5개를 라운드 인덱스로 순회** | ReAct 계보의 핵심이 미구현. 원형 대조(B-1b)의 초점 |
| **3** | **계측기가 이미 있다.** 9개 노드 전원 `emit_event()` + `/api/events`·`/api/state` HTTP 노출. **A-⑦의 코드 삽입 작업이 통째로 소멸** | R3 비용·리스크 하락. 단 `/api/state`가 `research_round`·`research_plan`을 노출하지 않아 A-⑥ 관측은 findings 파일/로그로 |

부수 발견: `tools/`는 `agent/`를 **0건** 참조 → 하부 엔진 라이브러리 재사용안은 **성립한다**(A-⑧).

**(B) 쉬운 설명** — ① 출처 추적은 이미 되고 있었다. 안 되던 건 요약본 쪽인데, 그 요약본은 어차피 아무도 안 본다. ② 우리 연구 루프는 "해보고 배워서 다음 계획을 고치는" 능력이 없다 — 할 일이 처음부터 5개로 정해져 있다. ③ 진행 상황을 들여다볼 창문이 이미 뚫려 있어서, 이번에 계획했던 "로그 심는 작업"은 안 해도 된다.

---

## 2. 미확인 (이번 범위 밖, 추정 금지)

| 항목 | 왜 미확인인가 |
|---|---|
| `POST /api/run` 요청 스키마 | A-⑦ 대표 명령 실행에 필요. R3 진입 시 확인 |
| `web_search()` 전체 시그니처 (`search.py:1336`) | A-⑧ 3번 표의 빈칸 |
| supervisor `:775-792` 블록 도달 가능 여부 | 정적 판독으로는 unreachable로 보이나 **실행 확인 필요** |
| `save_state()` 자동 호출 여부 | 라운드 스냅샷 관측 대안 3번의 전제 |
| Track B 전체 (blockagi 두 리포) | **STOP 1로 미착수** |

---

## Self-check

- [x] Track A에서 파일을 수정하지 않았다 (이 문서 1건 생성 외 0건 — `git status` 재확인 예정)
- [x] 모든 라인번호를 실물로 재확인했다 (문서 기재값 그대로 쓰지 않았다 — 0-2에서 README-dev 기재값을 검증해 **맞음**을 확인)
- [x] §9 적용 — 주석의 환경 기술을 인용하지 않았다. `research_planner.py:415-416`의 "누락됨" 주석은 **stale임을 명시**(A-⑥)
- [x] §9 적용 — `git` 비ASCII 경로에 `-c core.quotePath=false` 사용 (A-③)
- [x] §9 적용 — 정규식을 세는 용도로 쓰지 않았다. supervisor 반환 22건은 `awk` 라인 덤프로 육안 확인
- [x] blockagi 리포를 clone하지 않았다 (STOP 1 준수)
- [x] 유료 실행 0건 · python 실행 0건 · API 호출 0건
- [x] 보고에 설계 제안이 아니라 사실만 담았다
- [x] A-⑤ 사슬 O/X를 코드 위치와 함께 적었다
- [x] `git add`를 아직 실행하지 않았다 (`-A`도 물론)
- [x] 논문 트랙 워킹트리 파일을 건드리지 않았다

---

## 🛑 STOP 1 — 챗 판정 대기

Track B(blockagi 두 리포 clone + 대조)는 **착수하지 않았다.** 판정 후 진행.
