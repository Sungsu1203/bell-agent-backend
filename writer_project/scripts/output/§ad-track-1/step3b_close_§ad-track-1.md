# §ad-track-1 계단 3-b close — 리포트 생성 경로 확립

- 일자: 2026-08-02
- 범위: 계단 3-b (리포트 부품 정찰 → L0 조립 → L1a 섹션 생성 A/B). **E열 채우기 제외**
- 결과: **PASS(목적) / 가설 반증(내용).** 경로 전 구간 개통. 단 "참조 확대 = 품질 개선" 가설은 실측으로 반증
- 비용: L0 $0 + L1a A/B 합 **≈ $0.12** (추정. 실청구 미확인)
- 코드 변경 0건 · `.env` 변경 0건 · 논문 트랙 무오염
- 선행 문서: `R0_recon_close_§ad-track-1.md`, `step2_close_§ad-track-1.md`, `step3a_close_§ad-track-1.md`

---

## 0. 이번 사이클의 성격

3-b 진입 시 NEXT_SESSION의 정의는 두 작업이 묶여 있었다.
(가) 리포트 생성 경로 확립 (나) E열 14칸 채우기(10주 추가 수집 선행).

**분리했다.** 근거: 리포트 경로가 검증되기 전에 10주치를 색인하면, 결과가 나빠도
원인이 *수집 부족*인지 *리포트 부품 부적합*인지 못 가린다. 3-a/3-b 분할과 같은 논리.

→ **3-b = 기존 4주차분(04·07·13·15)으로 경로만 확립. E열은 3-c로 이월.**

이 분리가 유효했음이 확인됐다. L1a A/B에서 **참조 확대가 본문 품질을 악화**시킨다는
반전이 나왔고, 10주치를 먼저 수집했다면 이 결론에 도달하지 못했다.

### 0.1 순서 정정 — allowlist는 3-b 선행 조건이 아니었다

NEXT_SESSION은 catch P(allowlist 교체)를 "3-b 진입 전 반드시"로 올렸으나,
이는 **실행 경로 의존 항목**이다.

| 리포트 경로 | allowlist 영향 |
|---|---|
| 그래프 완주(REPL/HTTP) | web_search 노드 재실행 → 게이트가 84% 제거 → 필수 선행 |
| 부품 직접 호출 | 신규 검색 없음 → **이번 사이클과 무관** |

정찰 결과 후자로 확정 → catch P는 3-c(추가 수집)로 이월. 순서는 **정찰 우선**이 옳았다.

---

## 1. 리포트 경로 지도 (이번 사이클 최대 수확)

```
outlines/<slug>/outline_report.md          ← 섹션 목록의 단일 진실원 (H2 `##` 만 유효)
        ↓
agent/section_writer.py:191  section_writer(state)          [그래프 안] LLM 1회/섹션
        ↓ save_md_draft
sections/<slug>/<section_slugify(title)>.md  (+ .refs.json 사이드카)
        ↓
report_builder.py:279  build_final_report()                 [그래프 밖] LLM 0
        ↓
reports/<slug>/<timestamp>_report.md  +  latest.md
        ↓ (선택)
agent/export/cli.py  →  .pptx
```

### 1.1 핵심 구조 — 조립이 그래프 밖에 있다

`build_final_report` 호출부는 **전부 `app.py`. `graph.py`에는 0건.**
그래프를 태우지 않고 직접 호출 가능하며 LLM·임베딩 0.

3-a의 "리포트 경로가 전부 막혔다"는 판정은 **섹션 *생성* 쪽**에 대한 것이었고,
*조립* 쪽은 처음부터 열려 있었다.

### 1.2 section_writer는 검색하지 않는다

```
git grep -n "retrieve\|vector_store\|search\|references" -- agent/section_writer.py
→ 1건 (:288 "references": ref_text)
```

`ref_text = _refs_preview_text(state, numbered=True) + _facts_block(state)` — 둘 다
`state`만 읽는 순수 함수. 네트워크·retrieve 없음. **참조 주입 완전 통제 가능.**

역으로: 3-a에서 색인한 416청크는 `section_writer`가 직접 읽지 않는다.
`vector_search_agent`가 state에 담아줘야 도달한다.

### 1.3 프롬프트 입력 계약

`get_section_writer_prompt()` `input_variables` = 5개
`['messages', 'outline', 'references', 'target_title', 'topic_title']` — 전부 수기 주입 가능.

특수 규칙: `target_title`이 `"Q&A:"`로 시작하면 보고서 스타일·헤딩·표·
Actionable Recommendations를 모두 생략하고 간결한 직접 답변만 출력. **3-c 후보 레버.**

---

## 2. L0 — 조립 검증 (비용 0)

수기 섹션 1건 + 기존 아웃라인(3-a catch O 사고의 생존물)으로 조립.

```
merged sections=1, content=0, chapters=0, _other=0 | missing=6
FINAL REPORT → reports/experiential-marketing-media/20260802-084430_report.md
```

확인된 것:

- `sections/` 1차 경로에서 매칭 (탐색 순서 `sections → content → chapters`, `CFG.REPORT_SOURCES`로 변경 가능)
- `_ensure_heading`이 평문 본문 위에 `## 3. 감각과 감성 모듈의 실행 사례 및 설계 방식`을 자동 삽입
  → **섹션 파일에 헤딩을 직접 쓰지 않는 편이 안전** (파일명은 번호 탈락, 헤딩은 번호 유지 — 비대칭)
- 타임스탬프본 + `latest.md` 이중 저장. latest는 매 실행 덮어씀

---

## 3. L1a — 섹션 생성 A/B (이번 사이클의 핵심 실측)

단일 섹션 프롬프트 체인만 직접 호출(`get_section_writer_prompt() | llm | StrOutputParser()`).
`section_writer` 노드의 ①제목결정 ③파일저장을 우회하고 **②프롬프트 실행만** 측정.
파일 미수정 = 기존 L0 산출물 보존.

### 3.1 조건

| | A | B |
|---|---|---|
| `top_k` | 8 | 25 |
| `REFS_PREVIEW_MAX_DOCS` | 8 (기본) | 25 |
| `REFS_PREVIEW_SNIPPET` | 350 (기본) | 1200 |
| 소스별 상한 | 없음 | 2 |
| 참조 docs / 소스 | 8 / 3 | 16 / 11 |
| 참조 길이 | 3,135자 | 17,863자 (5.7배) |

모델 `gpt-4o`, temp=0.30, `max_tokens` 미설정.

### 3.2 결과 — 가설 반증

| 항목 | A | B |
|---|---|---|
| **본문 브랜드명** | 할리데이비슨 1건 | **0건** |
| 참조 내 브랜드 등장 | 할리데이비슨 1회 | 삼성 8 / 맥도날드 7 / Leffe 6 / 노키아 2 / 인텔·PlayStation·Nokia·할리데이비슨 각 1 = **27회** |
| 본문 길이 | 1,692자 | 1,504자 |
| 마커 형식 | `[[1]]` 정상 | **`[[2], [3]]` 위반** |
| 무출처 주장 | "시장 지속 성장", KPI 나열 | — |
| 확신도 세탁 | — | **96% 문장** |

**A는 1/1을 살렸고 B는 27/0을 버렸다.**

`max_tokens` 미설정(잘림 아님)인데도 B가 A보다 짧다.
입력이 5.7배로 늘자 writer가 개별 사례 대신 공통분모를 뽑아 **추상화 층위가 올라갔다.**

> **리포트 파이프라인의 병목은 참조 부족이 아니라 참조 선택이다.**
> 많이 주는 게 아니라 적게·정확히 주는 쪽이 개선 방향.

### 3.3 소스 상한의 부수 효과 (유일한 순이득)

```
top_k=25 원본      : docs=25 소스=11 28,958자
top_k=25 소스상한2 : docs=16 소스=11 17,863자   ← 소스 손실 0, 길이 38% 절감
```

잘린 9청크는 전부 동일 소스 중복. **다양성 손실 없이 토큰만 절감.**
catch AJ(retrieve에 domain_penalty 없음)의 실효 우회책.

---

## 4. 인용 신뢰성 3종 — 3-c의 전제

### 4.1 catch AO — 확신도 세탁

참조 원문 [7]:
> 여러 전문 기관과 연구에서 사용된 수치는 … (경우에 따라 거의 96% 증가한 것으로 보고되기도 함)

B 본문:
> **연구에 따르면**, … 브랜드 인지도를 **최대 96%까지 증가시킬 수 있습니다** [[7]]

수치는 실재 → **환각 아님.** 문제는 3중 헤지(출처 불명 / "경우에 따라" / "보고되기도 함")가
전부 제거되고 "연구에 따르면"으로 승격된 것. 원문 자체도 출처 미상 2차 인용.

⚠️ **grep 사실 검증으로 미탐지.** 원문 대조가 필요하다.

### 4.2 catch AQ — 마커 묶음 조용한 소실

```python
re.compile(r'\[\[(\d+)\]\]').findall('… [[2], [3]] … [[1]] 정상')  →  ['1']
```

`[[2], [3]]`은 2도 3도 미매칭. 결과:
본문에 마커는 **그대로 남고**, footer에는 출처가 **안 붙고**, **에러·경고 없음.**
catch E·H-3·AA 계열 "조용한 손실"의 인용 층 재현.

### 4.3 catch AP — 길이 규칙 미준수

프롬프트 요구 800~1,500단어(한국어 2,400자+) 대비 실제 1,504~1,692자(약 40~50%).
`max_tokens` 미설정이므로 잘림 아닌 **규칙 미준수.** §paper-writer-2 (d) word count와 동형.

---

## 5. 논문 트랙 catch 84 대조 — AQ는 공통 뿌리의 미이식

과거 세션 조회 결과, **논문 트랙에서 동일 문제가 이미 종결됐다.**

writer가 `[[1], [5]]` / `[[1], [[2]]` / `[[1].` 변종 생성 → 파이프라인은 정본 전제.
**하류 정규식으로 4번 고치려다 4번 실패:**

1. catch 83 — 묶음 `[[1],[2]]` 미탐
2. loose grep이 정상 마커 오탐
3. 변종 `[[a], [[b]]` 미탐
4. `\[\[.*?\]\]` — malformed 앞 over-match → **prose 문장 삭제**(육안 확인)

원인은 **프롬프트에 복수 인용·구두점·malformed 규정 부재.** writer가 형식을 자작.
해결 = 상류 표준화 1곳. 하류는 원래 `\[\[(\d+)\]\]`로 충분. catch 85도 자동 해소.

> **원래 정규식은 틀리지 않았다. 정본을 전제한 올바른 코드였다.**
> 문제는 writer가 정본을 안 지킨 것이다.

### 5.1 이식 판정

`prompts.py:394 get_paper_section_writer_prompt()`(적용됨) ↔ `:496 get_section_writer_prompt()`(미적용).
**같은 파일 안에서 한쪽만 고쳐진 상태.**

| 문안 | 광고 | 이식 |
|---|---|---|
| 마커는 `[[`로 열고 `]]`로 닫는다 (단일 예 `[[1]]`) | ❌ | ✅ 그대로 |
| 복수 인용 = 독립 토큰 `[[1]] [[2]] [[3]]` + 금지 예시 4종 | ❌ | ✅ 그대로 |
| 마커는 문장부호 앞 | ❌ | ✅ 그대로 |
| 수치/연도/효과크기는 참조 **명시 값만** | △ 약함 | ✅ 강화 이식 |
| 근거 빈약 문구 금지 — 항상 `[[N]]` 출처 명시 | ❌ | ✅ 이식 (A의 무출처 주장 대응) |
| 로컬 pool 번호만 / previous_sections 재사용 금지 | — | ⚠️ 광고엔 previous_sections 없음. 불요 |
| APA 후처리 / 데이터 날조 금지 / H1·H2 / core_thesis / 미래형 | — | ❌ 논문 전용 |

금지 예시 4종에 **`[[1], [2]]`가 명시**돼 있어 우리 변종을 정조준. 손볼 것 없이 적용 가능.

⚠️ **catch AO는 이 문안으로 닫히지 않는다.** "명시된 값만"은 96%를 못 막는다(실재하므로).
헤지 유지는 신규 요구형 문안이 필요:

> 참고 자료가 수치에 단서(추정·경우에 따라·보고되기도 함)를 달았다면, 본문에서도 그 단서를 함께 유지한다.

논문 트랙 교훈("억압형 실패, 요구형 성공")을 따른 형태. **두 트랙 공통 이득.**

⚠️ `prompts.py`는 두 트랙 공유 파일 + 논문 커밋 이력(4ea484a5). 수정은 **diff STOP 밟는 별도 사이클.**

---

## 6. catch 등재 (AB~AQ)

### 6.1 환경·경로

| # | 내용 | 상태 |
|---|---|---|
| **AB** | `TOPIC_SLUG` 미지정 시 **논문 트랙**(`academic-trademark-similarity-consumer`) 프리셋 로드. CLAUDE.md §1의 "기본값 = influencer marketing"은 **stale**. 3-b부터 파일 쓰기 작업이라 오염 위험 실재 | 스크립트 assert로 종결 |
| **AC** | `section_slugify`가 번호 접두 제거(`1. Executive Summary` → `executive-summary`). venfobel `1-executive-summary.md`(6/1 17:54, 구규칙)는 1차 경로 미스 → `find_section_path` 폴백 의존. §13-14-α B 전후 규칙 변경 흔적 | 실측 확인 |
| **AE** | `report_builder` 단독 import 시 graph·LLM 미로드(`graph loaded? False`, openai False). 조립 **비용 0** 재현 가능 | 확정 |
| **AG** | Chroma `persist_directory`에 leaf 대신 루트(`data/chroma_store`)를 주면 빈 `chroma.sqlite3`(188,416B) 생성. **7/31 전례**(`_stray_20260731.sqlite3.bak`, 동일 바이트). `web_rag/utils.py:391` "leaf 전제" 주석이 근거 | 격리 필요 |
| **AM** | **zsh는 `$var` 확장 시 word splitting을 하지 않는다.** `set -- $CFG` / `for x in $LIST` 등 bash 관용구가 통짜 문자열로 전달. 에러 없이 빈 값으로 도는 것이 위험 — 측정 루프에서 전 조합이 기본값으로 실행될 뻔했다. 해결 = `${=VAR}` 강제 split, zsh 배열 1-based | 규칙 확립 |

### 6.2 참조 전달 계층

| # | 내용 | 상태 |
|---|---|---|
| **AF** | `REFS_PREVIEW_MAX_DOCS`(8) / `REFS_PREVIEW_SNIPPET`(350) / `REFS_PREVIEW_MAX_Q`(5) CFG 미선언. `refs.py:34 _cfg_str`이 **CFG → `os.getenv` 폴백** → **셸 env override 가능.** `.env` 미수정 = 논문 트랙 무오염. 3-a에서 막혔던 키들(`GATE_KEEP_SOURCES`·`SEARCH_BACKENDS`)과 정반대 | **확정 — 3-b 유일 무료 레버** |
| **AH** | 리포트 파이프라인 실질 병목 = **references 상위 8건 × 350자.** 웹 청크 평균 1,843자 → **19%만 LLM 도달.** 검색 임계(catch Z)보다 상위 관문 | 확정 |
| **AN** | SNIPPET 350→1200, docs 8→16 확대가 **본문 품질을 악화.** 참조 브랜드 27회 → 본문 0회(B) vs 1회 → 1회(A). 입력 증가가 추상화 층위를 올림. **레버 방향 반전 — 축소가 개선 방향** | **확정 (가설 반증)** |
| **AO** | 참조 원문 헤지가 본문에서 "연구에 따르면"으로 **확신도 세탁.** 수치 실재이므로 사실 검증으로 미탐지. 원문 대조 필요 | 3-c 전제 |
| **AP** | 프롬프트 800~1,500단어 대비 실제 40~50%. `max_tokens` 미설정 → 잘림 아닌 규칙 미준수 | 미조치 |
| **AQ** | `[[2], [3]]`이 `_MARKER_RE`에 미매칭 → 본문 잔존 + footer 누락 + **무경고.** 논문 트랙 catch 84와 동형. `prompts.py` 상류 문안 미이식이 뿌리 | **이식으로 해소 가능** |

### 6.3 검색·색인

| # | 내용 | 상태 |
|---|---|---|
| **AI** | web retrieve top-8 중 3건이 앞350자 전량 boilerplate(위키 사이드바·각주, jaenung 메뉴). LLM 도달 구간과 오염 구간 중첩 → **catch X 우선도 하→상** | 승격 |
| **AJ** | top-8 소스 3개(위키 4/volute 2/jaenung 2). `_rerank_with_intent_and_diversity`(`search.py:1709/1808`)는 **web_search 병합 시점 전용** — 벡터 retrieve 경로 미적용. `domain_penalty=0.15` 하드코딩 | 소스 상한으로 우회 |
| **AK** | 3-a 대표 수확(바디프랜드·LG·DBpia)이 top-8 전원 미진입. **top_k=25에서 삼성(15)·Leffe(17)·맥도날드(20)·LG(25) 진입 → 순위 문제로 정정.** 단 바디프랜드·DBpia는 25위 내에도 부재 — 앞350자 boilerplate가 임베딩 유사도를 낮춘 것으로 추정(catch AI 연동) | 부분 정정 |
| **AL** | 동일 임계에서 local 3/8 · web 8/8 반환. 청크 크기(208 vs 2,186)가 필터 작동을 반전. **미해결 #3(청크 비대칭)이 catch Z·X·AI의 공통 뿌리** | 확정 |
| **AD** | `build_final_report`가 `missing=6/7`에서도 리포트 생성 + `latest.md` 갱신. **완성도 게이트 부재.** 부분 리포트가 정상 산출물로 오인 가능 → **판정은 반환 `missing` 개수로만** | 미조치 |

### 6.4 3-a catch 정정

| # | 정정 |
|---|---|
| **V** | **유지(잠정 해제).** 3-a 미해결 #6의 "미수정 가능성"은 해소됐다 — `engine="tavily"` 인자를 실제로 넣어 시험했고, 체인이 변하지 않아 **원복**한 상태다. `grep -n "_ws(" probe_search.py` → `out = _ws(q, num=40)`은 원복 후 상태이며 미적용 증거가 아니다. ⚠️ **grep은 현재 상태만 보여준다 — 이력의 부재 증명이 아니다** |
| **T** | **미해결 유지.** 인자 경로가 실패했으므로 "`.env` 수정이 유일 검증 경로"라는 3-a 판정이 그대로 선다. 검증 방법 = **`.env`의 `SEARCH_BACKENDS`에서 `tavily`를 체인 앞으로 배치.** `naver_direct`가 `SEARCH_TOPN`을 단독으로 채워 조기종료하는 구조이므로, 순서를 바꿔야 tavily 호출 여부를 관측할 수 있다. ⚠️ `.env`는 L1 글로벌 = 논문 트랙 공유 → **백업(`cp .env .env.bak_adtrack_YYYYMMDD`) + 수정 + 복원** 필수 |
| **P** | 근거 강화. 3-a는 "게이트가 84% 제거"(손실)만 봤으나, 청크 기준으로 **게이트 OFF의 대가 = 24.3% 무관 자료**(jaenung 24 / icat 17 / illustkorea 14 / prime-career 12 / adall 12 / atlassian 11 / syncly 11). illustkorea PDF 1건이 14청크로 단일 최대 소스이며 주제 무관. 양방향 수치가 갖춰짐 |

---

## 7. 이번 사이클 오판 기록

| 오판 | 원인 | 교훈 |
|---|---|---|
| catch AQ 처방으로 **정규식 확대**를 제안 | 논문 트랙 catch 84 선례 미조회 | **하류에서 퍼내지 말고 상류에서 잠근다.** 4연패 패턴의 5번째가 될 뻔했다 |
| "3-a 사고가 남긴 게 0" | `sections/` 빈 폴더만 보고 판정. `outlines/`에 아웃라인 생성돼 있었음 | 산출물 확인은 전 경로를 훑는다 |
| `retrieve`가 `tools/local_rag`에 있다고 가정 | 사용처(`vector_search.py:435`)만 보고 정의부 미확인 | 3-a 규칙 "`git grep -n` 무필터 먼저"를 스스로 어김 |
| chroma 조회 명령이 루트 경로를 지시 | "하나의 store, 여러 컬렉션" 구조로 가정 | **읽기 명령인 줄 알았으나 쓰기가 섞였다.** chroma 접근 전 `ls` 선행 |
| "스크립트가 파일로 도니 TOPIC_SLUG는 알아서 잡힌다" | 프리셋 개입 지점 미확인 | catch AB 규칙을 세워놓고 예외를 흘림 → **assert로 코드에 박음** |
| `git grep -A 12 "패턴" -- 경로` (옵션 후치) | git grep 인자 순서 | 패턴 뒤 인자는 revision으로 해석. `git grep [옵션] "패턴" -- [경로]` 고정 |
| A 출력에 Actionable Recommendations 없다고 판정 | 앞 1,200자만 보고 판단 | 산출물은 끝까지 확인 |
| catch V를 **철회**로 판정 | `grep`에 인자가 없는 것을 "수정된 적 없음"으로 읽음. 실제는 시험 후 **원복**된 상태 | **grep은 현재 상태이지 이력이 아니다.** 3-a "grep 0건은 부재 증명이 아니다"의 변주 — 시험·원복 여부는 사람에게 묻거나 `git log`/`git diff`로 확인 |

**공통 구조**: 3-a와 동일하게 대부분 *확인 없이 다음 단계로 진행*. 다만 이번엔
STOP 게이트가 작동해 유료 사고는 0건. 무료 정찰 단계에서만 발생했다.

---

## 8. 운영 규칙 (이번 사이클 확립)

**TOPIC_SLUG는 지시가 아니라 코드로 강제**
> 모든 ad-track 스크립트 상단, **무거운 import보다 앞에** assert를 둔다.
> 검증은 선언이 아니라 실행: `TOPIC_SLUG` 없이 돌려 AssertionError로 죽고
> `[Config] 토픽 프리셋 로드` 줄이 뜨지 않는 것까지 확인한다.

**zsh word splitting**
> `set -- $VAR` / `for x in $LIST`는 zsh에서 분리되지 않는다. `${=VAR}` 사용.
> 측정 루프가 조용히 기본값으로 도는 사고를 만든다.

**하류 봉합 금지**
> 출력 형식 문제는 프롬프트(상류)에서 잠근다. 정규식(하류) 확대는 금지.
> 논문 트랙 4연패 기록 참조. 금지 예시를 **구체적으로** 제시할 것 —
> 추상 규칙보다 "이건 안 됨: `[[1], [2]]`"가 확실하다.

**참조는 적게·정확히**
> 참조량 확대는 본문 품질을 떨어뜨린다(catch AN). 소스별 상한이 다양성 손실 0으로
> 토큰을 줄이는 유일한 순이득 조작.

**dry-run 게이트 (프롬프트 경로)**
> `refs_preview_text()`까지 비용 0. **LLM이 볼 문자열 실물을 파일로 떨구고 육안 검수**한 뒤
> `--go`. 3-a의 `web_results_to_documents` 게이트와 동일 패턴.

**판정 기준은 실행 전에 정의**
> 결과를 본 뒤 기준을 만들면 자기합리화가 된다. L1a는 브랜드명·연도·마커·환각·길이
> 5항목을 사전 고정했고, 그래서 "B가 더 나쁘다"를 인정할 수 있었다.

---

## 9. 미해결 항목

| # | 항목 | 우선도 | 비고 |
|---|---|---|---|
| 1 | **catch AQ 문안 이식** | 🔴 최상 | 논문 `prompts.py:394` → `:496`. 검증된 문안. diff STOP 필요 |
| 2 | **catch AO 헤지 유지 문안** | 🔴 최상 | 신규 요구형 1줄. 두 트랙 공통 이득. 강의자료 사실성 직결 |
| 3 | **catch AN 역방향 실험** | 상 | docs 4~6 / SNIPPET 600 등 **축소** 조합. A보다 나아지는 지점 탐색 |
| 4 | **catch AI/X boilerplate 정제** | 상 | `nav`·`header`·`footer` decompose 추가. 검색 유사도까지 개선될 가능성(AK 연동) |
| 5 | **catch P allowlist** | 상 | 3-c 추가 수집 시 필수. **`topics/<slug>.env`(L3)에 `ALLOWED_DOMAINS_EXTRA`** — 글로벌 `.env`는 논문 트랙 공유 |
| 6 | **청크 크기 비대칭** | 상 | web 1,843 / local 250. catch Z·X·AI·AL 공통 뿌리 |
| 7 | **catch AJ retrieve 다양성** | 중 | 소스 상한으로 우회 중. 코드 반영은 별 트랙 |
| 8 | **catch AP 길이 규칙** | 중 | §paper-writer-2 (d) word count와 동형. 공통 처방 가능성 |
| 9 | **catch T — tavily 미호출** | 중 | 인자 경로는 실패 확정(catch V). **`.env` `SEARCH_BACKENDS`에서 tavily를 체인 앞으로** 옮겨 검증. `.env` 백업+복원 필수(논문 트랙 공유). 3-c 추가 수집 전에 판단하면 백엔드 선택지가 넓어짐 |
| 10 | **catch AD 완성도 게이트** | 하 | 3-c에서 판정은 반환 `missing`으로 |
| 11 | **접미사 없는 NS 정체** | 하 | `data/chroma_store/experiential-marketing-media`(8/1 15:36, catch O 사고 시각) 내용 미확인 |
| 12 | **stray sqlite 격리** | 하 | `mv data/chroma_store/chroma.sqlite3 data/chroma_store/_stray_20260802.sqlite3.bak` |

---

## 10. 3-c 설계 (근거 확보분)

**결론: E열은 리포트가 아니라 추출 경로로 채운다.**

3-b 실측이 "리포트로 E열 채우기"를 지지하지 않는다:

- 참조를 늘려도 브랜드·연도가 본문에 나오지 않음 (AN)
- 나온 수치는 확신도가 조작됨 (AO)
- URL은 프롬프트가 본문 삽입을 금지 (설계상)
- 마커 묶음은 조용히 소실 (AQ)

### 10.1 제안 경로

```
Q&A 모드 target_title  →  사례 목록 생성  →  [[N]] 마커 파싱
                                              ↓
                        refs 인덱스로 URL 역추적 (.refs.json / footer)
                                              ↓
                        ⭐ 원문 대조 육안 검수 (AO 대응 — 생략 불가)
                                              ↓
                        15주 설계표 E열
```

**⚠️ 원문 대조는 필수 단계다.** AO가 확인된 이상 LLM 출력을 그대로 E열에 넣을 수 없다.
브랜드·연도가 참조 원문에 그렇게 적혀 있는지 사람이 확인한다.

### 10.2 선행 조건

1. catch AQ 문안 이식 (미이식 상태로 3-c를 돌리면 인용 추적이 깨진다)
2. catch AO 문안 추가
3. catch P allowlist — 10주 추가 수집 전
4. 마커 번호 재할당 검증 — `attach_marker_citations`가 **본문 등장 순서로 재할당**하므로
   프롬프트의 `[5]`가 최종본에서 `[[1]]`이 될 수 있다. 원본 N ↔ 최종 N 매핑 확인 필요

### 10.3 성공 기준 (3-a에서 승계, 판정 방법 보강)

> 15주 설계표 **E열 14칸**에 **브랜드명 + 캠페인명 + 연도 + 출처 URL**.
> URL 없이 본문에만 등장하는 것은 미검증으로 분류.
> **추가: 원문 대조를 통과한 것만 인정.** 참조에 존재하되 헤지가 제거된 진술은 미검증.

F열(오성수 실무 사례)은 RAG 대상 아님 — 벨컴/디트라이브 내부 자산, 직접 작성.

---

## 11. 산출물

| 파일 | 성격 |
|---|---|
| `probe_section_L1a.py` | L1a 드라이버. dry-run 기본 + TOPIC_SLUG assert. 임시, 커밋 안 함 |
| `probe_L1a_A_refs.txt` / `probe_L1a_B_refs.txt` | LLM 입력 실물 (3,135자 / 17,863자) |
| `probe_L1a_A_out.md` / `probe_L1a_B_out.md` | 생성 본문 (1,692자 / 1,504자) |
| `sections/experiential-marketing-media/감각과-감성-모듈의-실행-사례-및-설계-방식.md` | L0 수기 섹션 |
| `reports/experiential-marketing-media/20260802-084430_report.md` + `latest.md` | L0 조립 산출물 |
| `/tmp/L0_manual_section.md`, `/tmp/L0_report.md`, `/tmp/outline_bak_adtrack.md` | 백업 |

`data/chroma_store/experiential-marketing-media-web`(416청크)·`-local`(302청크) **보존.**

**코드 변경 0건. `.env` 변경 0건.** 계단 2 미커밋분(`tools/local_rag.py:503`)은 그대로 유지.
