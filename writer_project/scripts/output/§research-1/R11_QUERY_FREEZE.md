# R11 — 수집 쿼리 동결 ($0 갈래)

- **실행일 2026-08-10** · 채널 = 기술 정밀 · 실비용 **$0**
- 계보 `CC_S5S6_20260809_query_freeze.md`(원 지시서) → `CC_S5S6_20260810_query_freeze_addendum.md`(부칙) → `CC_S6_20260810_query_freeze_exec.md`(실행 지시)
- 우선순위 = **실행 지시 > 부칙 > 원 지시서.** 원 지시서 §6·§7 및 부칙 §6 불변
- 🔴 **파일명 날짜 불일치** — `Q_FROZEN_20260809.txt` 의 `20260809` 는 **원 지시서 작성일**이며 실행일이 아니다. 실행일은 **2026-08-10** 이다. 파일명을 근거로 실행일을 역산하지 말 것 (부칙 §4)

---

## 1. 실행 환경 캡처 (STANDARDS §7 / catch CO)

```
cwd     /Users/ohsungsu/dev/bell-agent/bell-agent-backend/writer_project
venv    ../.venv_openai/bin/python
        → /Users/ohsungsu/dev/bell-agent/bell-agent-backend/.venv_openai/bin/python
python  3.11.6
bs4     4.14.2
lxml    6.0.2
libxml2 2.14.6   (LIBXML_VERSION == LIBXML_COMPILED_VERSION)
libxslt 1.1.43
```

catch AR 재검증 — HEAD `d6aebcc6`, 인계문 §1 기재와 일치. 워킹트리 미커밋분 = 논문 트랙 `scripts/§paper-writer-1/measure_paper.py` 1건.

> ⚠️ **일부 검색은 레포 루트에서 실행했다.** 심 grep 의 `.gitignore` 적용 범위가 cwd 에 따라 달라지므로(`CLAUDE.md §9` catch CG) 각 절에 cwd 를 병기했다. `.env*` 등 ignore 대상은 **파일 지목 + `command grep`** 로 확인했다.

---

## 2. S5 결과 — A 수집축 / B 검색축

### 2-a. A 수집축 — **있음** ✅

| 항목 | 값 |
|---|---|
| 함수 | `web_search_agent(state: State)` |
| 파일:행 | `agent/web_search.py:181` — **정의 경계 `181 ~ 1645`** (ast 실측, 총 1,465행) |
| 쿼리 인자 | **직접 인자 아님.** state 키 주입 |
| 쿼리 타입 | **`list[str]`** |
| 주입 키 1순위 | `state["research_plan"]["queries"]` — `:1148` |
| 주입 키 2순위 | `state["planner_queries"]` — `:1149` |
| 집행 | `:1181` `_run_web_search_with_guard(q)` — 쿼리 1개씩 |
| 산출 | `:1049` `_filter_json_by_domain(json_path)` → `:552` `p.stem + "_filtered" + p.suffix` |

```python
from agent.web_search import web_search_agent
web_search_agent({"research_plan": {"queries": [q1, ..., q17], "objective": "..."},
                  "messages": [], "task_history": []})
```

`State` = `core/state_types.py:73 TypedDict, total=False` → 평 dict 가능. pending task 부재는 `:273` soft-guard 가 자동 생성.

⚠️ `:1148-1149` 는 **`or` 연쇄**다. 1순위가 비어야 2순위를 읽는다.

### 2-b. B 검색축 — **있음** ✅

| 항목 | 값 |
|---|---|
| 함수 | `_dual_retrieve(query, *, top_k, ns_default, persist_dir) -> List[Any]` |
| 파일:행 | `agent/vector_search.py:391` |
| 쿼리 타입 | **`str` 1개** (list 아님) |
| 실행 전례 | `scripts/§research-1/run_r3a_straight.py:656-663` (tracked) |
| 노드 레벨 | `vector_search_agent(state)` — `agent/vector_search.py:654`, 쿼리 소스 `:711` |

```python
from agent.vector_search import _dual_retrieve
docs = _dual_retrieve(q, top_k=6, ns_default=ns, persist_dir=pd)
```

### 2-c. 🔴 A ≠ B — 근거

서로 다른 파일의 다른 함수다. **같을 것이라고 가정하지 않고 실물로 확인했다**(부칙 §1).

다만 **노드 레벨 주입 키는 공유한다.** `vector_search.py:711` 이 `((state.get("research_plan") or {}).get("queries") or []) or (state.get("planner_queries") or [])` 로 `web_search.py:1148-1149` 와 동일 표현을 읽는다.

⚠️ **순서 위험** — A 실행 후 `:1187-1190` 이 주입 키를 비우므로, 같은 state 를 이어 B 에 넘기면 쿼리 **0건**이 된다.

### 2-d. 부칙 §1 근거 문장 검증 — 실제 거리는 한 칸 더 멀다

부칙은 *"Q-1·Q-2 가 수행한 것은 기존 색인 대상 retrieve"* 라 했다. 실측하니 probe 2종은 **`_dual_retrieve` 조차 쓰지 않았다.**

```
probe_q1_arms.py:372·387   _get_vs / _get_embeddings → vs._collection.query()
probe_q2_zdouble.py:463    동일
주석: "_collection.query() 는 ingest_vector.py:1618-1622 와 동일 호출"
```

**파이프라인 retrieve 함수까지 우회한 재구현**이다. → 원 지시서 §1-a 의 *"probe 가 검색까지 했으니 자리가 있을 것"* 은 A축은 물론 **B축 근거로도 약했다.** 부칙의 2축 분리 지시가 실제로 오판을 막았다. (catch 후보 **CQ** — §13)

### 2-e. A축 보조 경로 2건

| 경로 | 판정 |
|---|---|
| `tools/web_rag/search.py:1336` `web_search(query: str, *, engine, num) -> (results, json_path)` — `@tool`(langchain_core.tools), 평함수 래퍼 `tools/web_rag/__init__.py:63` | **A축 요건 미충족(부분)** — str 1개, `_filtered.json` 미생성, 색인 없음 |
| `utils/forced_queries.py:403` `extract_forced_queries_from_messages(messages, lookback)` — `messages` 에 `force_query: …` / `force_queries: [...]` 주입. `ALLOW_FORCED_QUERIES` 기본 **True**. `web_search.py:1196` 호출 → `:1218` 집행 | **A축 3번째 벡터** |

---

## 3. 동결 쿼리 17줄

`scripts/output/§research-1/Q_FROZEN_20260809.txt` — 한 줄 1쿼리, **후처리 0**

```
 1  홀브룩 허쉬만 1982 경험적 소비 3F 정보처리 패러다임 비판 논문
 2  파인 길모어 1998 경험경제 4E 경험 연출 개념 사례
 3  슈미트 1999 전략적 경험모듈 SEM 5유형 경험제공수단 ExPro 비교 연구
 4  슈미트 SEM 감각 모듈 사운드 로고 비주얼 아이덴티티 사례
 5  분트 곡선 Wundt curve 자극 강도 선호 역U자 관계 연구
 6  감정 곡선 emotion arc 설계 브랜드 필름 공감 서사형 캠페인 2023 2026 사례
 7  슈미트 SEM 인지 행동 관계 모듈 실행 사례
 8  반전 퀴즈형 인터랙티브 콘텐츠 설계 메커니즘
 9  UGC 참여 챌린지 참여 설계 메커니즘
10  팬덤 커뮤니티 기반 브랜드 콜라보 사례
11  온오프 통합 캠페인 경험 격자 구성 사례
12  고객 여정 맵 작성법 체험마케팅 사례
13  칙센트미하이 몰입 이론 마케팅 적용 연구
14  브랜드 경험 척도 4차원 측정문항과 브랜드 충성도 연구
15  숏폼 네이티브 브랜드 콘텐츠 알고리즘 확산 사례
16  팝업스토어 브랜드 체험관 온오프 통합 phygital 사례
17  AI VR 가상인간 기반 가상경험 마케팅 2025 2026 동향
```

- **줄 수 17** · **objective 배분 [3, 3, 5, 3, 3] = 17** (Q2 §6.3 기재와 실물 일치)
- 🔴 **`Q_FROZEN_20260809.txt` 는 신규 생성물이 아니라 `Q2_SEGMENT1_CLOSE.md` 박제분의 전사본이다.** 출처 파일과 해시는 아래 3-a 에 기재

### 3-a. 해시 4종 (실행 지시 §3-b)

| # | 대상 | sha256 |
|---|---|---|
| 1 | **사본** `Q_FROZEN_20260809.txt` (1,142 B · 17줄) | `06e5f81828d0f287e324760a455ab5dc05d1edeb109d951101b155a8218b03a8` |
| 2 | **출처** `Q2_SEGMENT1_CLOSE.md` (tracked) | `0ebeccc45c0a522067207975fe21154a520edb21a575301e574ec017c722e1ff` |
| 3 | **원자료** `q2_zdouble_20260806-210440.json` (`.gitignore:84` 차단) | `7f8ad71f85783fc8b3aa0c871944906bf8286530d4eb7fcae6855bd5118937a2` |
| 4 | **미채택 판본** 원출력 17줄 (말미 공백 보존, 1,168 B) | `b58687715f9cc31d4fa1c035c4cfce0b97b2bbe67561bacef700249431a4d472` |

> #4 는 **선택 은폐 방지**용이다. 채택본 대비 **+26 B = 말미 공백 2칸 × 13행**으로 정확히 설명된다(말미 공백 보유 행 **13/17**).

### 3-b. 개행 · BOM · CRLF (부칙 §2-b-5)

| 파일 | BOM | CRLF | CR 단독 | 말미 개행 |
|---|---|---|---|---|
| `Q_FROZEN_20260809.txt` | 없음 | 없음 | 없음 | **있음** |
| `Q2_SEGMENT1_CLOSE.md` | 없음 | 없음 | 없음 | **있음** |

---

## 4. 갈래 처리

### 4-a. #69 재현 대조 — **해당 없음**

> S6 를 실행하지 않았으므로 생성 재현 대조(#69)는 성립하지 않는다. 문자열 동결 설계는 생성의 결정론성에 의존하지 않으며, 원 지시서 §4 에서 라운드 반복을 이미 포기했으므로 재생성 능력은 이번 코퍼스의 요건이 아니다. 결정론 여부는 미검증 상태로 남으며 이를 검증된 것으로 기술하지 않는다.

### 4-b. #67 Z'' 문안 byte 대조 — **수행분** ✅

$0 갈래여도 성립한다(`probe_q2_zdouble.py:689` json.dump 가 `zdouble_template` 를 원자료에 저장).

| 대상 | 길이 | sha256 |
|---|---|---|
| `Q2_SEGMENT1_CLOSE.md §4` (펜스 `:159`~`:192` 내부) | **1,189자** | `9da6206999804277a3cb54bd2f88c1035ea8366c1b08d83bcdef228d74dc0620` |
| `q2_zdouble_*.json` 의 `zdouble_template` | **1,189자** | `9da6206999804277a3cb54bd2f88c1035ea8366c1b08d83bcdef228d74dc0620` |

**byte 일치 ✅** — 지시서 기재 1,189자와도 정확히 일치. STOP 12 미발동.

**불변식 3건 (Q2 §4.1)**

| # | 불변식 | 실물 확인 |
|---|---|---|
| 1 | 번호 재부여 없음 — 2·4·5·6·7·8·9 원번호 유지 | ✅ 규칙 `1)`~`9)` 연속. 🔴 표시가 붙은 신규분은 `1)`·`3)` 2건이고 나머지 7개 원번호 유지 |
| 2 | 예시는 타 도메인 고정 | ✅ `:187-189` 페스팅거(인지부조화)·넛지(선택설계)·카너먼·트버스키(prospect theory) — **체험마케팅 술어 0건** |
| 3 | 규칙 7 의 3축과 하단 예시 3줄 1:1 대응 | ✅ 규칙 7 `이론 원전 / 실행 사례 / 측정·실증` ↔ 예시 `…원전` / `…적용 사례` / `…실험 검증 논문` |

**Q2 §4.2 잔여 유출 1건 — 기록만.** 규칙 2 예시(`:174`) `(예: 체험마케팅, 브랜드 경험, 경험경제)` 의 **`경험경제`** 는 obj1 술어(파인·길모어 1998). **문안 무변경이 확정 사항**이므로 그대로 둔다.

### 4-c. 전사 무손실 대조 (실행 지시 §3-a)

| 절차 | 결과 |
|---|---|
| 펜스 경계 **실측 확정**(하드코딩 0) | §7 헤딩 `:423` · open `:425` · close `:452` — S5 확정분과 재확인 일치 |
| **`assert len(lines) == 17` 선행** | 통과 (S5 deviation 1 재발 방지) |
| 축자 복사 — 정렬·중복제거·공백정리·인용부호 정규화 | **전부 0** |
| 원본 구간 vs 사본 `diff` | **출력 0줄, exit=0** ✅ |

> 🔴 정본이 이미 정규화본이라는 사실을 **추가 정규화의 근거로 쓰지 않았다**(실행 지시 §3-a-2).

### 4-d. 정본 선택 근거 (챗 판정 2 — §2-1 확인 통과분)

> 동결 정본은 `Q2_SEGMENT1_CLOSE.md §7` 의 정규화본이다. 이는 문서 편집상의 정리가 아니라 **파이프라인이 실제로 수행하는 변환을 통과한 값**이다. `probe_q2_zdouble.py:371 normalize_llm_queries` 는 `agent/research_planner.py:241 + 243-277` 의 축자 복사본이며, 말미 공백 제거는 `_strip_bullet_num` 내부 `re.sub(r"\s+", " ", s).strip()` 의 결과다. 따라서 정규화본은 planner 출력의 열화판이 아니라 **하류가 수령하는 형태 그 자체**다. 원출력 판본(13/17 행 말미 공백 2칸)의 해시도 함께 기재하며, 선택 사실을 은폐하지 않는다.

**§2-1 확인 결과 — 근거 성립 ✅ (단 1건 정밀 정정 포함)**

`git log -L 241,277:agent/research_planner.py` → 변경 **2건**, 최종 **2026-03-02 `105eca9b`**. 2026-08-06 이후 **0건**. STOP 10 미발동.

| 함수 | 원본 (research_planner.py) | probe_q2 | probe_q1 | 판정 |
|---|---|---|---|---|
| `_strip_unbalanced_quotes` | `243-259` | `348-360` | `247-259` | **byte 일치 ✅** (본문 237자, sha `985bfcb4…`) |
| `_strip_bullet_num` | `261-265` | `363-368` | `262-267` | **byte 일치 ✅** (본문 162자, sha `9f2d13f7…`) |
| `normalize_llm_queries` | 인라인 `241 + 267-277` | `371-384` | `270-284` | **q1 = 축자 일치 ✅ / q2 = 1행 병합 🔴** |

- byte 대조는 **docstring 제외 + 들여쓰기 정규화** 후 수행(원본은 중첩 함수라 +4 들여쓰기). AST 등가성도 병행 확인 — `원본==q2 True`, `원본==q1 True`.
- 🔴 **`probe_q2_zdouble.py:371` 의 1행 병합** — docstring 이 *"research_planner.py:241 + 267-277 축자 복사"* 라 선언하나 실물은 다르다:

```diff
- normed: list[str] = []      # 원본 (2행)
- _seen = set()
+ normed, _seen = [], set()   # probe_q2 (1행 병합)
```

  **의미는 등가**(빈 list·빈 set 초기화)이며, **말미 공백 제거를 담당하는 `_strip_bullet_num` 은 byte 일치**이므로 **판정 2 근거에 영향 없다.** 다만 "축자 복사" 선언이 부정확한 것은 사실이므로 기록한다(catch 후보 **CQ** 계통).

### 4-e. §2-2 미치환 플레이스홀더 — **0건 확인** ✅

동결 17줄은 `_core_subst`(`research_planner.py:307-347`, 실측 확인) **미경유** 값이다. 치환해 줄 층이 없으므로 전수 검사했다.

| 검사 대상 | 결과 |
|---|---|
| 특수문자 5종 `[` `]` `\|` `{` `}` | **0건** |
| 토큰 `region` · `country` · `market` · `region\|country\|market` | **0건** |
| **합계** | 🔴 **0건 — 미치환 플레이스홀더 없음.** STOP 11 미발동 |

> **양성 대조 (STANDARDS §8)** — 의도적으로 `테스트 [region|country|market] 문자열` 을 검사기에 투입해 **검출 1/1** 확인. 검사기가 실제로 동작함을 확인한 뒤의 0건이다. (`CLAUDE.md §9` — 양성 대조 없는 0건은 근거가 아니다)

---

## 5. "해당 없음" 항목 — 사유 문장 (공란·삭제 없음)

| 항목 | 처리 |
|---|---|
| **STOP 조건 2** (총수 17 아님) | **해당 없음.** S6 LLM 재실행이 없어 새 생성 출력이 존재하지 않는다. 전사본 줄 수는 §4-c 의 `assert` 로 별도 확인했다 |
| **STOP 조건 3** (배분 [3,3,5,3,3] 아님) | **해당 없음.** 위와 동일. 배분은 원자료 `llm_rows[].queries` 실측으로 확인했다(§3) |
| **STOP 조건 4** (`[Config] 토픽 프리셋 로드` 미출력) | **해당 없음.** LLM 을 실행하지 않았으므로 파이프라인 부팅 자체가 없다. L3 활성 확인이 성립하지 않는다 |
| **env capture log (콘솔 L1~10)** | **해당 없음.** 위와 동일 사유. 대신 §1 에 **정적 환경 캡처**(cwd·venv·5버전)를 수록했다 |
| **#69 재현 대조** | **해당 없음** — §4-a 사유 문안 |
| **#70 실비용** | **$0 실측** (미기재 아님). §9 |

---

## 6. 수집 단계용 검색 파라미터 전재 (Q2 §6.0)

```
model gpt-4o · temperature 0.0 (객체 실측) · N=1 · references=""
RAG_DISTANCE_THRESHOLD 1.10 (무변경) · RAG_TOP_K 6 (무변경) · RETRIEVE_WEB_RATIO 0.65 (무변경)
M1-a 창 = agent/vector_search.py:360 _split_k(6) = web 4 / local 2   ← import 호출, 하드코딩 0
n_results = 50 (드라이버 인자, C7-a 저촉 아님)
RESEARCH_PLANNER_MAX_Q 미적용 · _core_subst 미적용(국내 편향 재주입 차단)
색인 web 416 / local 302 · dim 3072 (sqlite3 -readonly 확인, Chroma 개방 전)
```

⚠️ 이 중 검색 파라미터는 **M1-a 통과 측정용**이며 쿼리 생성에는 개입하지 않는다. 수집 단계에서 필요하므로 전재해 둔다(원 지시서 §2-a).

---

## 7. 쏠림표 + objective 별 채점 원칙 + 계보 단서 2건

### 7-a. Q2 §6.2 쏠림 실측 (Z'')

| obj | 쿼리 | web | local |
|---|---|---|---|
| **1 (이론)** | 3 | **0/12** | 6/6 |
| 2 | 3 | 5/12 | 4/6 |
| 3 | 5 | 4/20 | 2/10 |
| 4 | 3 | 8/12 | 6/6 |
| **5 (숏폼·트렌드)** | 3 | **12/12** | 6/6 |

`catch BX` — web 에는 이론·측정 자료가 없고 사례·트렌드가 대량 통과한다. **obj1 의 web 0 은 정상이다.**

### 7-b. 🔴 배분·쏠림 교정 0 · objective 별 채점

- **통과 쿼리 쪽으로 배분을 몰지 않는다.** 몰면 마케팅 블로그·업계 매체에 표본이 쏠려 **크롬 비율 자체가 부풀려진다.** 크롬 비율은 어느 사이트를 긁었느냐로 정해지므로 사이트 구성을 비틀면 측정 결과가 비틀린다.
- **대신 채점을 objective 별로 분리한다.** 5개를 합산 평균하면 obj1 의 0 이 obj5 의 12 를 상쇄해 **해석 불가능한 값**이 된다.
- Q2 §8 이월 3건(obj4 취약 14중 7 / 영문 소실 `experiential grid`·`customer journey map` / 자수 하한 미달 6건)을 **그대로 안고 간다. 규칙을 추가하지 않는다.**

### 7-c. 단서 1 — 쏠림표의 계보 (실행 지시 §5-a)

> `Q2 §6.2` 쏠림표는 `probe_q2_zdouble.py` 산출이다. 이 probe 는 임베딩(`_get_embeddings`)·컬렉션 개방(`_get_vs`)·경로 해결(`_resolve_persist_dir_strict`)·창 분할(`_split_k`) 을 **파이프라인 함수로 수행**하나, `retrieve()` 상위층은 경유하지 않는다. 미경유분 = 드롭필터 · `merge_refs` 접힘(`catch CH`) · `FILTER_BAD_DOMAINS`(`:1645`). 따라서 이 표는 **거리 기준 통과**이며 **파이프라인 최종 통과가 아니다.**

### 7-d. 단서 2 — 동결본의 계보 (실행 지시 §5-b)

> 동결 17줄은 `_core_subst`(`research_planner.py:307-347`) **미경유** 값이다. state 직접 주입 시 파이프라인에서도 이 단계를 건너뛰므로 내적 일관성은 유지된다. 다만 기존 색인 118 URL 이 `_core_subst` 적용 쿼리로 수집됐을 가능성이 있어, **옛 색인과의 비교에는 차이축이 하나 추가된다.** X·Y 대조(동일 코퍼스)에는 영향 없다.

### 7-e. 단서 3 — 수집 산출물 2계보 병존 (`catch CK` 실측)

> ⚠️ 실행 지시 `CC_R11_20260810_fix_commit.md §3` 은 이 블록의 헤딩을 `5-c` 로 제시했다. 그것은 **지시서 자신의 §5 번호**(5-a·5-b = 단서 1·2)이며, R11 에서 그 둘은 **7-c·7-d** 이므로 단서 3 은 **7-e** 로 붙였다. 내용은 무변경이다.

> `web_search.py` 사슬 실측: `:846-849` path 폐기 → `:934 ret = combined_items`(list) → `:946-948 json_path=""` → `:958` 항상 True → `:964-968` fallback 저장 → `:1049 _filter_json_by_domain`.
>
> | 경로 | 명명 | 실물 | filtered 사슬 |
> |---|---|---|---|
> | 정규 `_save_results`(`utils.py:600`) | `resources_<ts>[_blake2b8].json` | 72건 (`writer_project/research/`) | **진입 0** |
> | fallback(`:964`) | `web_<epoch10>_<sha1_8>.json` | 43건 (`resources/<slug>/`) | **43/43 전건** |
>
> **정규 경로는 죽지 않았다. 파일을 산출하되 하류가 읽지 않는다.** 색인에 들어가는 것은 fallback 계보이며, 이것이 `catch CK` 의 *"이 버그가 `raw_content` 원본을 살리고 있다"* 의 실체다.
>
> → **파일명 규칙으로 계보를 판별할 수 있다.** 유료 수집분이 `raw_content` 를 보유한다는 근거가 된다(X·Y 대조 재료 요건).
>
> ⚠️ 이 표는 자체 정정을 거쳤다. 1차 집계는 `./resources` 하위만 세어 `resources_*.json` **0건** 을 얻었고 *"정규 경로 산출물이 아예 없다"* 로 갈 뻔했다. 레포 루트 재탐색에서 72건. **양성 대조 없는 0건을 부재 근거로 쓰지 않는다**(`CLAUDE.md §9`)가 작동한 지점이다.

---

## 8. 🔴 1라운드 고정 — 절대수치 금지 (원 지시서 §4 문안 그대로)

쿼리를 문자열로 동결하면 **라운드 반복이 성립하지 않는다.** 파이프라인 원래 동작(라운드마다 신규 쿼리 생성 + `no_new_url_streak` 종료)과 다르다.

> 본 코퍼스는 동결 쿼리 17개의 1라운드 수집분이다. X·Y 대조의 내적 타당성은 성립하나, **웹 전반에 대한 절대 수치 진술에는 사용할 수 없다.**

- 이전 색인 118 URL 은 **다라운드 산물일 가능성이 높다**(라운드 수 미확인 — 해당 라운드 파일 부재, `R7`)
- 🔴 **불가능한 것: 절대 수치 진술.** "웹 전반의 크롬 비율은 N%" 류를 쓰지 않는다. **X 대비 Y 의 차이만 읽는다**

---

## 9. 실비용 — **$0 실측**

LLM 호출 **0회**, 유료 API 호출 **0회**. 전 작업이 파일 읽기·해시·`git` 조회다. 예상 $0.015 대비 **$0.015 절감**(S6 재실행 회피분).

---

## 10. 🔴 유료 착수 전 게이트 (§2-4 결과 + 이월 8항)

> ## 🔴 유료 수집 착수 전 필수 확인 — `GATE_KEEP_SOURCES`
>
> **현재 꺼져 있다.** `.env:208 GATE_KEEP_SOURCES=0` · `topics/experiential-marketing-media.env` 에 설정 0건(=1 보유 프리셋은 academic 계열 4개뿐).
>
> 이대로 수집하면 `web_search.py:533-534` 가 원본 경로를 그대로 반환하여 **`*_filtered.json` 이 생성되지 않는다. 실행은 성공으로 끝나고 유료 비용만 소모된다.**
>
> CFG 선언은 있다(`core/config.py:278`·`:511`·`:771`) → `.env` 로 점화 가능. 별도 수단 = `app.py:2232-2234 --gatekeep`.
> `_env_flag` 는 엄격 파서로 `"0"`→False 정상 처리 — `catch 71`(truthy 오파싱) 유형 아니다.
>
> **꺼진 시점 실측** — filtered 43건 = 6/1 5건 + 8/1 15:35~15:38 38건. `probe_A2/B1.log`(8/1 17:02·17:07) = enabled(n=79), `probe_C~F.log`(17:21~17:48) = disabled. → **8/1 17:07~17:21 사이에 꺼졌고 현재까지 꺼짐.**
>
> 🔴 **미확정 (`catch CM` — 판단 불가는 제3의 칸. 어느 쪽으로도 밀지 않는다)** — 그때 켠 수단이 `.env` 값인지 `--gatekeep` 인지는 판정 불가하다(`.env` untracked, 이력 없음). 어느 쪽으로도 밀지 않는다. 조치는 어느 쪽이든 동일하다 — **수집 직전 점화하고 로그로 실동작을 확인한다.**

⚠️ 아래 §10-d 이월 8항의 1번은 위 블록과 **중복되나 그대로 둔다.** 표의 완결성이 우선이며, 이 항목에서 중복은 위험이 아니다.

### 10-a. §2-4-a — `web_search_agent` 정의 경계 **실측**

| 항목 | 값 |
|---|---|
| 정의 경계 | **`181 ~ 1645`** (ast, 총 1,465행). 다음 최상위 def = `get_WRITER_AGENT :1653` |
| `:1049`·`:1148`·`:1149`·`:1181`·`:1187`·`:425`·`:532`·`:533`·`:552` | **전량 내부 ✅** |

**"산출(`:1049`)이 집행(`:1181`)보다 앞선다"의 해소** — 지시서의 추론이 옳았고 실측으로 확정했다. 중첩 함수 34개 중 관련분:

```
_load_items_with_watchdog     526-529
_filter_json_by_domain        532-562     ← 헬퍼 정의
_run_web_search_with_guard    737-1139    ← 헬퍼 정의. :1049 는 이 본문 안
_normalize_planner_q         1142-1146
```

`:1049` 는 `_run_web_search_with_guard` **본문 내부**이고, 그 헬퍼의 **호출**이 `:1181` 이다. **정의 순서와 실행 순서가 다른 것이 정상**이다.

### 10-b. 🔴 §2-4-b — `GATE_KEEP_SOURCES` 는 **현재 꺼져 있다**

**0단 (STANDARDS §1.3) — CFG 선언 확인** · cwd = 레포 루트

```
core/config.py:278   GATE_KEEP_SOURCES: bool
core/config.py:511   GATE_KEEP_SOURCES=_env_flag("GATE_KEEP_SOURCES", False),
core/config.py:771   GATE_KEEP_SOURCES: Final[bool] = CFG.GATE_KEEP_SOURCES
```

→ **CFG 선언 3건 있음.** `.env` 로 켤 수 있다. **STOP 13 미발동** (조건은 "CFG 선언 0건 + `.env` 무효").

**`.env` 4파일 실측** · cwd = `writer_project/` · `command grep` + 파일 지목(catch CG)

| 파일 | `GATE_KEEP_SOURCES` |
|---|---|
| `.env` | 🔴 **`:208  GATE_KEEP_SOURCES=0`** — 꺼짐 |
| `.env.openai` | 0건 |
| `.env.vertex` | 0건 |
| `.env.anthropic` | 0건 |

**토픽 프리셋** — `topics/experiential-marketing-media.env` **0건**(설정 없음). `GATE_KEEP_SOURCES=1` 은 **academic 계열 4개 프리셋에만** 있다(`academic-_template` `:25` / `academic-genz-…` `:18` / `academic-influencer-…` `:18` / `academic-trademark-…` `:21`). → **§research-1 토픽은 프리셋으로 켜지지 않는다.**

**truthy 패턴 (catch 71)** — `core/config.py:29 _env_flag` 는 엄격 파서다. `True={"1","true","yes","on"}` / `False={"0","false","no","off",""}` / 그 외 default. **`"0"` 은 정상적으로 False 로 읽힌다** — catch 71 유형 아님.

**실효 경로** — `web_search.py:431` 이 `gatekeep_enabled()`(`settings_gatekeep.py:223`)로 덮어쓰는데, 그것도 같은 키를 읽는다(`_flag("GATE_KEEP_SOURCES", False)`). **점화 수단은 `app.py:2232-2234 --gatekeep` / `:2269-2272`** 다.

**"어디서 켜졌는가" — 시점 실측**

| 증거 | 값 |
|---|---|
| `*_filtered.json` 43건 생성 시각 | 6/1 17:50 **5건** + 8/1 15:35~15:38 **38건** |
| `probe_A2.log`(8/1 17:02) · `probe_B1.log`(8/1 17:07) | **`[GATEKEEP] enabled` (n=79)** |
| `probe_C/D/E/F.log`(8/1 17:21~17:48) | **`[GATEKEEP] disabled`** |

→ **8/1 17:07 ~ 17:21 사이에 꺼졌고, 그대로 현재까지 꺼져 있다.** filtered 생성 구간(15:35~15:38)은 켜져 있던 때다.

> 🔴 **미확정 (`catch CM` — 판단 불가는 제3의 칸. 어느 쪽으로도 밀지 않는다)** —
그때 켠 수단이 `.env` 값인지 `--gatekeep` 인지는 판정 불가다(`.env` untracked, 이력 없음).
어느 쪽으로도 밀지 않는다. **조치는 어느 쪽이든 동일하므로 열어 둔다** —
수집 직전 점화하고 로그로 실동작을 확인한다.
⚠️ `CM` 조문의 *"미확정 칸의 크기가 결론을 바꿀 만하면 닫으러 간다"* 기준 적용 —
본건은 **조치가 갈리지 않으므로 닫으러 가지 않는다.**

### 10-c. 🔴 §2-4-c — `_filter_json_by_domain` 이 받는 것은 **fallback 산출**이다

**사슬 실측 (catch CK)**

| 행 | 내용 |
|---|---|
| `:846-849` | `legacy_ret` 튜플에서 **`[0]`(items)만** 취한다 → **path 폐기** |
| `:934` | `ret = combined_items` — **list** |
| `:946-948` | `elif isinstance(ret, list):` → **`json_path = ""`** |
| `:958` | `if not json_path:` → **항상 True** |
| `:964-968` | fallback 저장 `web_{int(time.time())}_{sha1[:8]}.json` |
| `:1049` | `_filter_json_by_domain(json_path)` ← **위 fallback 경로** |

**명명 규칙 대조 (양성 대조 성립)**

| 경로 | 명명 | 실물 |
|---|---|---|
| 정규 writer `_save_results` (`tools/web_rag/utils.py:600`, 호출 `search.py:1860`) | `resources_<YYYY_MM_DD_HHMMSS_ffffff>[_<blake2b8>].json` | **72건** — `writer_project/research/` |
| fallback (`web_search.py:964`) | `web_<epoch10>_<sha1_8>.json` | **43건** — `writer_project/resources/<slug>/` |
| filtered 43건 | `web_<epoch10>_<sha1_8>_filtered.json` | **43/43 전건이 fallback 명명** ✅ |

→ **정규 writer 산출물(`resources_*.json` 72건)은 존재하지만 filtered 사슬에 들어가지 않는다.** 두 계보가 병존하며, **색인에 쓰이는 것은 fallback 쪽**이다. `catch CK` 가 말한 *"지금 `raw_content` 를 살리는 것이 fallback"* 의 실체가 이것이다.

> ⚠️ **자체 정정 1건** — 1차 집계에서 `./resources` 하위만 세어 `resources_*.json` **0건**이 나왔고, 이는 *"정규 경로 산출물이 아예 없다"* 로 읽힐 뻔했다. 레포 루트 기준 재탐색에서 **72건**이 나왔다. **양성 대조 없는 0건을 근거로 쓰지 않는다**(`CLAUDE.md §9`)는 규율이 작동한 지점이며, 위 표는 재탐색 결과다.

🔴 **읽기 전용 준수** — `web_search.py` 편집 **0**. `:848` 무접촉(원 지시서 §6-2).

### 10-d. 이월 8항 (수집 지시서 작성 시 다시 찾지 않도록)

| # | 항목 | 근거 |
|---|---|---|
| 1 | 🔴 `GATE_KEEP_SOURCES` **현재 0**. 꺼진 채로 돌리면 `:533-534` 가 원본 경로 반환 → **`*_filtered.json` 미생성** | §10-b |
| 2 | 허용 도메인이 비면 `:442-453` 이 **그 라운드만 자동 비활성화** | `:453` |
| 3 | `SKIP_WEB_SEARCH` 확인 | `:739`·`:1175` |
| 4 | 🔴 `references["queries"]` 기적재분은 **소리 없이 배제**. 17개 중 일부만 나가면 **§8 "동결 쿼리 17개의 1라운드 수집분" 문장이 거짓이 된다.** 주입 직전 `references` 상태 확인 + 실제 집행 쿼리 수 로깅 | `:303-308`·`:1160` |
| 5 | 🔴 **수집 직후 색인까지 이어진다.** 수집만 떼어낼 수 없다 → 이 자동 색인을 X 로 쓸지, 버리고 filtered 에서 2벌 재색인할지 **미결(판정은 챗)**. **직접 색인 진입점은 존재한다**: `tools/web_rag/ingest_vector.py:1442` `add_web_pages_json_to_chroma(json_file: str, *, chunk_size, chunk_overlap, namespace, collection_name, persist_directory, embedding, clear=False) -> Tuple[int,int]` (모듈 최상위 공개 함수, 래퍼 `tools/web_rag/__init__.py:79`) | `:1053-1060` · §6-5 |
| 6 | 주입 키 `:1148`·`:1149` 는 **`or` 연쇄** — 둘 다 채우지 않는다 | §2-a |
| 7 | 실행 후 `:1187-1190` 이 주입 키를 비운다 → **1회성.** 같은 state 를 B 로 넘기면 쿼리 0건 | §2-c |
| 8 | 17줄 플레이스홀더 재확인 (§4-e 를 수집 직전 1회 반복) | §4-e |

---

## 11. 커밋 전 게이트 (부칙 §3 / 실행 지시 §8)

cwd = `writer_project/`

```
$ git check-ignore -v scripts/output/§research-1/Q_FROZEN_20260809.txt
  (출력 없음)  exit=1

$ git check-ignore -v scripts/output/§research-1/R11_QUERY_FREEZE.md
  (출력 없음)  exit=1
```

**둘 다 출력 0줄 → 통과 ✅. STOP 9 미발동.**

> ⚠️ `git check-ignore` 는 `!` 예외 매치에도 0 을 반환하므로 exit code 만으로 판정하지 않는다(`CLAUDE.md §9` catch BB). **부작용 없는 실물 명령**으로 재확인했다:
> ```
> $ git add --dry-run scripts/output/§research-1/Q_FROZEN_20260809.txt
> add 'writer_project/scripts/output/§research-1/Q_FROZEN_20260809.txt'
> ```
> `.gitignore:84` 는 `scripts/output/**/*.json` 이므로 `.txt` 는 대상이 아니다 — **추론이 아니라 위 실측으로 확인했다**(부칙 §3 요구).

**커밋 대기 상태.** `git add -A` **금지**(논문 트랙 `scripts/§paper-writer-1/measure_paper.py` 상주, `CLAUDE.md §4` catch AS) — 개별 add. 커밋은 **지시받은 뒤**.

---

## 12. Deviation 자진 보고 — **2건** (이번 차수 신규 0건, 전부 S5 이월분의 후속 조치)

이번 차수 신규 deviation **0건**. 아래는 S5 에서 보고한 2건의 처리 결과다.

1. **`zip` 절단 (S5 deviation 1)** — 이번 차수 전 대조에 **`assert len(...) == N` 을 선행**시켰다(§4-c). 전사 스크립트·플레이스홀더 검사·원출력 판본 재구성 3곳 전부 적용. catch 후보 **CR** 로 값을 냈다(§13).
2. **grep 패턴 비대칭 (S5 deviation 2)** — 이번 차수는 대조 시 **동일 패턴**을 사용하고 cwd 를 병기했다.

추가 자체 정정 1건은 deviation 이 아니라 **규율 작동 사례**로 §10-c 말미에 기록했다(`resources_*.json` 0건 → 72건 재탐색).

---

## 13. catch 후보 — 값만 낸다 (번호 부여·원장 배치는 챗 소관)

문자 계열(CP 다음).

| 후보 | 문안 초안 |
|---|---|
| **CQ** | Q-1·Q-2 probe 의 측정 계보 — 임베딩·컬렉션·창분할은 파이프라인 함수를 쓰나 `retrieve()` 상위 필터층은 미경유. 주석의 *"`ingest_vector.py:1618-1622` 와 동일 호출"* 은 **기술이지 실행 확인이 아니다**(`CLAUDE.md §9`). **보강 실측 1건** — `probe_q2_zdouble.py:371 normalize_llm_queries` 의 docstring 이 *"축자 복사"* 를 선언하나 실물은 원본 2행을 1행으로 병합했다(`normed: list[str] = []` + `_seen = set()` → `normed, _seen = [], set()`). 의미는 등가지만 **선언과 실물이 다르다.** 반면 probe_q1 은 축자 일치였다 — **같은 선언을 단 두 사본의 충실도가 달랐다** |
| **CR** | 길이 단언 없는 `zip` 이 조용히 잘라 **가짜 합격 신호**를 낸다. 18줄 vs 17줄이 "불일치 0건"으로 출력됨. 대조 전 `assert len(...) == N` 이 선행 조건 |

⚠️ **CR 의 계통(패턴 γ "에러 없이 잘못된 결과" vs `catch CL` "본 것이 전부가 아님")은 판정하지 않는다.** 양쪽 후보를 병기만 한다.

### 관측 (catch 후보 아님)

- **`Q1_JSON` 의존** — `probe_q2_zdouble.py:92`·`:434` 가 `q1_arms_20260806-161606.json`(16 MB, ignored)에서 Y·Z' 를 재사용한다. **Q-2 재현이 ignored 파일 1개에 걸려 있다.** 이번 동결이 그 사슬을 끊는 부수 효과가 있다 — 17줄이 tracked `.txt` 로 나온다.
- **패턴 α(단위 혼동) 4회차 후보** — 원 지시서 §3-a 가 정정한 *"objective 4개 · 52쿼리(13×4)"* 오판. 52 는 Q-1 **arm 4종(X·Y·Z·Z') 합계**이지 objective 배분이 아니며, 1회 산출은 **17쿼리**다. 08-09 문안이라 08-10 S4 종결의 α 3회(H·J·L) 집계에 미포함. 🔴 **원장 등재 여부는 챗 소관·미판정. 회차를 세지 않는다.**
- **WORKBOARD 활성 트랙에 S5·S6 행이 없다.** 현재 "지금 상태" 한 줄은 세션 C(라벨 320)만 가리킨다. **등재 문안 작성은 챗 소관.**

---

## 14. Self-check

| # | 항목 | 결과 |
|---|---|---|
| 63 | 실행 환경 | ✅ cwd · `.venv_openai` · python/bs4/lxml/libxml2/libxslt (§1) |
| 66 | `prompts.py` 무수정 | ✅ `git status --short prompts.py` → **0줄** |
| **67** | Z'' 문안 byte 대조 | ✅ **수행.** 1,189자 sha 일치. 불변식 3 확인 (§4-b) |
| 69 | 재현 대조 | **해당 없음 + 사유** (§4-a) |
| 70 | 실비용 | **$0 실측** (§9) |
| 71 | 전사 무손실 | ✅ `diff` **0줄** · 해시 **4종** · BOM/CRLF/개행 명시 · `assert len==17` **선행** (§3-a·§3-b·§4-c) |
| 72 | 커밋 전 게이트 | ✅ `check-ignore` 2파일 **0줄** · `git add --dry-run` 실물 확인 · `git add -A` 미사용 (§11) |
| 73 | 해당 없음 처리 | ✅ #69 · STOP 2·3·4 · env capture log 를 **사유 문장**으로. 공란 **0** (§5) |
| 74 | 날짜 불일치 설명 | ✅ 서두 1줄 |
| **75** | 복사본 stale | ✅ `git log -L` 최종 **2026-03-02**, 08-06 이후 0건. 함수 3개 byte 대조 — 2개 일치 / `normalize_llm_queries` q1 일치·q2 1행 병합 (§4-d) |
| **76** | 플레이스홀더 | ✅ **0건 명시 기재** + 양성 대조 1/1 (§4-e) |
| **77** | A축 정합 3건 | ✅ a·b·c 각각 실측값. **추론과 실측을 구분 표기** (§10-a·b·c) |
| **78** | 행번호 재확인 | ✅ 아래 표 |
| **79** | 편집 3건 반영 (2026-08-10 fix 차수) | ✅ ① `CM` 표기 처리 → **2026-08-10 재정정, 아래 참조** ② §10 서두 독립 블록 ③ §7-e 단서 3 |
| **80** | 재측정 0 | ✅ 실행·API 호출 **0건**. `Q_FROZEN_20260809.txt` 해시 `06e5f818…03a8` **불변 재확인** |
| **81** | 커밋 게이트 | ✅ `check-ignore` 0줄 + `add --dry-run` 실물 확인 **둘 다**. `git add -A` 미사용 |
| **82** | 스테이징 범위 | ✅ `git status --short` 로 **2건만** 스테이징 확인. 논문 트랙 미포함 |

> **fix 차수 catch 라벨 스캔 결과 (#79-①)** — 🔴 **2026-08-10 재정정.** 당시 `CM` 을 "CC 판단으로 새로 부여한 라벨"로 보고 제거했으나 **오판이었다.** `catch CM` 조문(`CLAUDE.md §9`)(*판단 불가는 제3의 칸*)의 **정확한 인용**이며 `:327`·`:386` 에 복원했다. 원인 = 챗이 원장 실물을 열지 않고 라벨 규율을 지시했고(`catch CT`), 수신 측이 재확인 없이 동의했다(`catch CL` 보강). 재스캔 결과 **CC 가 신규 부여한 라벨은 0건**이다. 나머지 문자 라벨(`CO`·`AR`·`CG`×2·`BX`·`CH`·`CK`×2·`BB`·`AS`·`CL`)과 숫자 라벨(`71`)은 **전부 기존 등재분 인용**이라 유지했다. §13 의 `CQ`·`CR` 은 "catch 후보" 수식과 함께 초안 표기(본문 참조 3곳 `:87`·`:206`·`:427`). ⚠️ **`CQ` 는 이후 결번 처리**됐다 — `CLAUDE.md §9 catch CI` 로 흡수.

### 14-a. #78 — 지시서 인용 행번호 대 실물

| 지시서 인용 | 실물 | 판정 |
|---|---|---|
| `research_planner.py:241 + 243-277` | `241` raw_lines / `243-259` / `261-265` / `267-277` | **일치** |
| `research_planner.py:307-347` `_core_subst` | `307-347` | **일치** |
| `probe_q2_zdouble.py:348-384` | `348-360` / `363-368` / `371-384` | **일치** |
| `probe_q2_zdouble.py:371 normalize_llm_queries` | `371` | **일치** |
| `probe_q2_zdouble.py:689` json.dump | `zdouble_template` 저장 확인 | **일치** |
| `web_search.py:181` `web_search_agent` | `181-1645` | **일치** |
| `web_search.py:425` `GATE_KEEP_SOURCES` | `425` | **일치** |
| `web_search.py:533-534` 원본 경로 반환 | `533` `if not GATE_KEEP_SOURCES:` / `534` `return json_path` | **일치** |
| `web_search.py:848` path 폐기 | `846-849` 블록 (`848` = `legacy_items = list(legacy_ret[0] or [])`) | **일치** |
| `web_search.py:948` `json_path=""` | `948` | **일치** |
| `web_search.py:966-967` fallback | `964` fname / `965` forced_path / `966` `with open` / `967` `json.dump` | **1행 범위차** — 저장 블록은 `964-968`. 실질 동일 |
| `web_search.py:1049`·`1053-1060`·`1148`·`1149`·`1181`·`1187-1190`·`303-308`·`1160`·`739`·`1175`·`552` | 전건 확인 | **일치** |
| `vector_search.py:391`·`654`·`711`·`360` | 전건 확인 | **일치** |
| Q2 §4 전문 **1,189자** | 1,189자 | **일치** |
| Q2 §7 펜스 `425`~`452` | `425`~`452` | **일치** |

**어긋난 것 = 1건**(`web_search.py:966-967` → 실물 `964-968`). 나머지 전건 일치. off-by-one 없음.

---

## 15. 이번 차수가 하지 않은 것

| 항목 | 상태 |
|---|---|
| 수집·색인 착수 | ❌ **미착수** (원 지시서 §6-7 불변) |
| `prompts.py` 수정 | ❌ **0** (#66 확인) |
| `web_search.py` 편집 | ❌ **0** — `:848` 무접촉. 읽기만 |
| Z'' 문안 수정 | ❌ **0** (불변식 3 확인) |
| 출력 후처리 | ❌ **0** (정렬·중복제거·공백정리·인용부호 정규화 전부) |
| 배분·쏠림 교정 | ❌ **0** |
| catch 번호 부여·원장 등재 | ❌ **챗 소관** |
| §10-d 유료 게이트 항목의 "조치" | ❌ **확인·기록까지** |
| 커밋 | ⏸ **지시 대기** |
