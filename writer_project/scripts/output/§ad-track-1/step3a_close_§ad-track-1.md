# §ad-track-1 계단 3-a close — 웹 수집 + 색인 + 거리 분포

- 일자: 2026-08-01
- 범위: 계단 3-a (웹 검색 → 정제 → 색인 → 거리 분포 측정). **리포트 빌드 제외**
- 결과: **PASS.** 135건 수집 → 416청크 색인, 임계 1.10 통과율 100%
- 비용: 색인 **$0.0947** + REPL 사고분 수 센트. 검색 API는 naver 무료 쿼터
- 선행 문서: `R0_recon_close_§ad-track-1.md`, `step2_close_§ad-track-1.md`

---

## 0. 이번 사이클의 성격

계단 3을 **3-a(수집·계측) / 3-b(리포트)** 로 분할했다.
근거: 수집과 생성을 한 번에 돌리면 결과가 나빠도 원인(검색·임계·프롬프트)을 분리할 수 없다.

이 판단이 유효했음이 실행 중 확인됐다. 3-a에서만 catch 17건이 나왔고,
그중 4건(O·P·T·V)은 리포트까지 갔으면 "검색 품질이 나쁘다"로 오진했을 항목이다.

---

## 1. 최종 상태

### 1.1 인덱스

| 항목 | 값 |
|---|---|
| 네임스페이스 | `experiential-marketing-media-web` |
| 입력 | 135 docs (4쿼리 수집분) |
| 신규 색인 | 120 docs (15건 중복 URL 제외) |
| 청크 | **416** (짧은 청크 18개 필터링: 434 → 416) |
| 청크 통계 | avg 1842.8 / p50 2229 / p90 2389 / min 52 / max 2400 |
| 정제 전 총량 | 1,097,159자 (HTML 제거 후) |
| 절단 후 | 728,099자 (문서당 20,000자 상한, 5건 적용) |
| 소요 | 62.43s |
| 비용 | $0.0947 |

### 1.2 로컬과의 비대칭

| | 청크 수 | 평균 자수 |
|---|---|---|
| local | 302 | 250 |
| web | 416 | **1,843** (7.4배) |

같은 토픽 인덱스에서 크기가 7배 차이. `RETRIEVE_WEB_RATIO` 슬롯 분리로 당장은 무해하나
통합 검색 시 웹 편중. **3-b 조정 대상.**

---

## 2. 실행 경로 확정 — 3중 차단 후 우회

계단 3 진입 시 설계했던 경로가 전부 막혔다.

| # | 시도 | 결과 |
|---|---|---|
| 1 | `app.py` REPL + `force_query:` | ❌ catch O — 입력마다 full-graph 완주 |
| 2 | `/api/run` HTTP + `messages` 배열 | ❌ catch R — 단일 `input` 문자열만 수용 |
| 3 | `web_search(engine=...)` 인자 | ❌ catch V — 체인 불변 |

**최종 경로 = 부품 직접 호출** (계단 2의 `ingest_local_files()` 우회와 동일 패턴):

```
web_search(query, num=40)            검색      LLM 0
  ↓ (results dict 리스트)
web_results_to_documents(results)    HTML 정제  임베딩 0  ← 무료 게이트
  ↓ (Document 리스트, 20000자 절단)
_ingest_add_docs(docs, namespace=)   색인      임베딩 발생
```

`web_results_to_documents`까지 비용 0이므로 **dry-run 게이트가 자연히 성립**한다.
계단 2의 `add_web_pages_json_to_chroma` 미주입 패턴과 같은 구조.

⚠️ `seed_web_namespace()`는 사용하지 않았다 — catch AA 참조.

---

## 3. 검색 실측

### 3.1 쿼리 4종과 결과

무필터(`GATE_KEEP_SOURCES=0`) 기준.

| 주 | 쿼리 | 건수 | 판정 | 대표 수확 |
|---|---|---|---|---|
| 04 | 브랜드 사운드 로고 사운드 아이덴티티 사례 | 35 | 🟢 | 바디프랜드 레드닷 본상, LG전자 사운드 디자이너, DBpia 논문 |
| 07 | 숏폼 챌린지 UGC 캠페인 성공 사례 2025 | 35 | 🟡 | 대행사 SEO 블로그 위주. 학술논문 1건 |
| 13 | 팝업스토어 브랜드 체험관 사례 2025 | 37 | 🟢 | 농심 팝업, 주류·뷰티 팝업, 전문매체 3종 |
| 15 | 가상인간 브랜드 캠페인 사례 | 28 | 🟢 | 구찌 가상모델, 스타벅스 AI 캠페인, 해외 AI 광고 6선 |

**성공 기준(브랜드명 + 캠페인명 + 연도) 기준 4개 중 3개 통과.**

### 3.2 게이트키핑 ON/OFF 대조

| | 총 건수 | 04 | 07 | 13 | 15 |
|---|---|---|---|---|---|
| 게이트 ON (기본값) | **21** | 5 | 1 | 11 | 4 |
| 게이트 OFF | **135** | 35 | 35 | 37 | 28 |

**84% 손실.** 죽은 것 중 삼성 사운드 아이덴티티 공식 페이지, LG 사운드 디자이너 인터뷰,
레페 사운드 캠페인(2024), 위키백과 '소리 상표', DBpia 논문 등 1차 소스 다수.
살아남은 21건은 `naver.com` 통짜 등재로 통과한 blog.naver.com 위주(16/21).

### 3.3 연도 토큰의 효과 (catch W)

15주 쿼리만 변경한 단일 변수 실험.

| 쿼리 | 결과 성격 |
|---|---|
| `AI 가상인간 VR 브랜드 마케팅 사례 2026` | 정부 연구보고서·산업백서 (XR SHOWROOM, 가상융합 생태계 연구, 캐릭터 산업백서, 대학도서관 AI) |
| `가상인간 브랜드 캠페인 사례` | 실제 캠페인 (구찌 가상모델, 스타벅스 AI, 버추얼 휴먼) |

**당해·차년도 토큰은 사례 기사 대신 "○○년 전망/계획" 문서를 끌어온다.**
직전 연도(13주 `2025`)는 무해 — 사례가 이미 축적됐기 때문.

### 3.4 실측 유효 도메인 (3-b allowlist 근거)

135건에서 실제 사례를 보유했던 곳. **`.env:214`에 `mk.co.kr` 외 전부 부재.**

| 도메인 | 건수 | 성격 |
|---|---|---|
| `brunch.co.kr` | 14 | 실무자 에세이 |
| `sweetspot.co.kr` | 9 | 팝업스토어 전문 |
| `openads.co.kr` | 6 | 광고 전문 (오픈애즈) |
| `aimatters.co.kr` | 3 | AI 마케팅 전문 — **가상 AI 캠페인 시리즈** 보유 |
| `mobiinside.co.kr` | 1 | 광고·마케팅 |
| `careet.net` | 1 | Z세대 트렌드 (캐릿) |
| `marketcast.co.kr` | 1 | 글로벌 브랜드 AI 캠페인 |
| `dbpia.co.kr` | 1 | 학술 |
| `live.lge.co.kr` | 1 | **브랜드 공식 뉴스룸** |
| `etnews.com` / `etoday.co.kr` / `mk.co.kr` | 4 | 경제·산업지 |
| `ko.wikipedia.org` | 1 | 개념 정의 |

`live.lge.co.kr` 유효 확인 → `news.samsung.com`, `newsroom.hyundai.com` 등 확장 후보.

---

## 4. 거리 분포 — 이번 사이클의 핵심 수치

n=40 (4쿼리 × top10), 임베딩 `text-embedding-3-large`, squared L2.

```
min=0.571  p25=0.698  median=0.959  p75=1.030  p90=1.039  max=1.046
```

| 임계 | 통과 | 비율 |
|---|---|---|
| 0.95 | 20/40 | 50% |
| **1.10** | **40/40** | **100%** |
| 1.20 | 40/40 | 100% |
| 1.30 | 40/40 | 100% |

### 4.1 미해결 #5 해소 — `RETRIEVE_WEB_RATIO=0.65`는 유효

venfobel 실측(web 21% 통과)을 근거로 "비율을 올려도 충족량이 제한될 것"이라 우려했으나
**우리 토픽은 100% 통과.** 웹 자료가 리포트에 실제 반영된다.

`max=1.046`으로 임계까지 여유도 크다.

### 4.2 단 통과율 100%는 변별력 상실이다

`1.10`에서 40/40이면 필터가 아무것도 거르지 않는다는 뜻.
원인은 웹 청크 평균 1,843자 — 대형 청크가 어휘 다양성으로 모든 질의에 근접.

**오염 실증 (07주 숏폼 질의 상위 10):**

```
0.981  숏폼 영상광고의 트렌드와 브랜드캠페인 성공사례에 관한 연구   ← 정답
1.011  2025년 2월 팝업스토어 총정리                        ← 13주 자료
1.012  2025 팝업스토어 트렌드 총결산                        ← 13주 자료
1.014  2025년 상반기 패션 팝업스토어 성공 사례                ← 13주 자료
```

`sweetspot.co.kr`(팝업 전문, 9건 수집)이 허브 역할.
**catch L(md 허브 청크)의 웹 버전이며, 임계 0.95면 오염 3건이 전량 배제된다.**

→ **임계 하향(1.10 → 0.95) 검토 근거 확보.** 단 로컬 분포와 함께 봐야 하므로 3-b 과제.

---

## 5. catch 등재 (J~Z)

### 5.1 진입점·제어 계층

| # | 내용 | 상태 |
|---|---|---|
| **J** | `ENABLE_WEB_SEARCH`가 CFG 미선언. 사용처 2곳(`app.py:561`, `graph.py:29`) 모두 `default=True`. `graph.py:29`는 **모듈 최상단 import 시점 평가** → `.env`·토픽 프리셋 어느 층에서도 OFF 불가. 웹검색 OFF 대조군 실험 시 코드 수정 선행 필요 | 미조치(무해) |
| **N** | `forced_queries.py:409` docstring이 `ALLOW_FORCED_QUERIES(False)`로 표기하나 `:72` 실제 기본값은 `True`. **주석 기준 판단 시 기능이 죽어 있다고 오판** | 실측 확인 |
| **M** | `extract_forced_queries_from_messages` lookback이 호출부마다 상이(`research_planner`=기본, `supervisor`=15, `web_search`=20). 노드 간 쿼리 집합 불일치 가능. 사용자 메시지 **누적 파싱** 구조라 이전 턴의 force_query가 후속 런에 잔존 → 단일변수 통제 시 **세션 분리 필수** | 미조치 |
| **O** | `RUN_ONCE_FAST`의 `handled=False`는 무시가 아니라 **full-graph fallthrough**. fast-path 미매칭 입력이 전량 그래프를 완주해 리포트까지 자동 생성. REPL은 입력마다 독립 실행이라 `messages` 이력 미누적 → forced_queries가 REPL 경로에서 구조적으로 무력 | **실사고 발생** |
| **Q** | R0 §2.1의 "진입점 = `app.py` (FastAPI)" 오판. 실제는 CLI REPL이 기본이며 `--serve` 플래그로만 uvicorn 기동(`app.py:2236/2430`). FastAPI 객체명이 `app`이 아니라 **`web_app`**(`:354`)이라 `grep "@app.post"`가 0건 반환 | 정정 완료 |
| **R** | `/api/run`(`app.py:1343`)이 단일 `input` 문자열만 수용, `messages` 배열 주입 불가. REPL과 동일하게 `run_once` 호출 → 입력마다 그래프 완주. **forced_queries는 REPL·HTTP 어느 진입점에서도 활성화 불가** (기능은 존재하나 진입점 부재 — catch B와 동형) | 미조치 |

### 5.2 검색 백엔드

| # | 내용 | 상태 |
|---|---|---|
| **P** | **`.env:214 ALLOWED_DOMAINS`가 종근당/벤포벨 유산**(제약·의약 ~80%, 광고·마케팅 8개). `.env:208 GATE_KEEP_SOURCES=1`로 활성 상태. 무필터 135건 → 게이트 ON 21건(**84% 손실**). `settings_gatekeep.py:45` `_BASE_ALLOWED_DOMAINS`(하드코딩 19개, 광고·마케팅 0건)와 `:156`에서 **합집합** 병합 → 축소 불가, `ALLOWED_DOMAINS_EXTRA` 확장만 가능. 부수: `naver.com` 통짜 등재로 `blog.naver.com` 전량 통과 | **3-b 조치 대상** |
| **S** | `web_search` 결과의 `source` 필드가 백엔드 식별자가 아니라 **URL 중복**. `best_of_chain`에서 어느 백엔드가 무엇을 기여했는지 결과물만으로 추적 불가 → 실행 로그 파싱 의존 | 미조치 |
| **T** | `[backend.pick] early stop: accumulated=40 >= topn=40` — naver_direct 단독으로 `SEARCH_TOPN`을 채우면 **tavily 미호출**. 직전 줄의 `min_backends=2` 판정(`allowlist hit but continue`)이 topn 조기종료에 무효화. `best_of_chain` 정책명과 달리 실질 단일 백엔드. 4쿼리 전부 tavily 0회 | 미조치 |
| **U** | `GATE_KEEP_SOURCES`가 `_PROTECTED_ENV_KEYS`(STANDARDS §4) 미포함. `web_search()` 내부 `reload_config()` + `refresh_gatekeep_cache()`가 매 호출마다 `.env` 값을 재적용 → **셸 override가 실행 중 무효화**. import 시점 `gatekeep_enabled()`는 False를 반환하나 실제 필터는 동작 (진단값과 실동작 불일치) | 우회 확립 |
| **V** | `_resolve_backend_chain`(`search.py:1301`)이 `CFG.SEARCH_BACKENDS`를 우선 평가하고 `or`로 `os.getenv` 폴백 → CFG가 항상 채워져 있어 **셸 env override 도달 불가**. `WEB_SEARCH_ENGINE` env / `web_search(engine=...)` 인자 경로도 체인 불변 확인(별칭 `'tavily'→'tavily'` 정상, `.func` 시그니처 정상). **백엔드 전환은 `.env` 수정이 유일한 확인 경로** | ⚠️ §7-1 참조 |
| **W** | 쿼리 내 **당해·차년도 토큰**이 사례 기사 대신 정책·전망 보고서를 끌어옴. 국내 웹에서 당해 연도는 "○○년 전망/계획" 문서가 지배적. 직전 연도(2025)는 무해 | 실측 확인 |

### 5.3 수집·정제·색인

| # | 내용 | 상태 |
|---|---|---|
| **AA** |	`seed_web_namespace(search.py:202)`가 부르는 `load_urls_as_documents`가 `ingest.py`에 부재 → 항상 `_fallback_load_urls_as_documents(:120)`로 폴백. WebBaseLoader로 **URL 재수집**하므로 확보된 `raw_content`를 버리고, `ingest_docs`의 BeautifulSoup 정제 경로를 타지 않음. 실패 시 `page_content=""`인 빈 Document를 append(`:154·:156`)하며 예외를 삼킴 → **조용한 손실**(catch E·H-3 계열). → **웹 색인**은 **`web_results_to_documents + _ingest_add_docs` 직접 호출로 우회** |	우회 확립 |
| **X** | `raw_content`는 **HTML 원본**(DOCTYPE·script·style 포함). 평균 233,110자, 최대 3,277,712자(`syncly.kr`). 단 `ingest_docs.py:385-389`가 BeautifulSoup으로 `script/style/noscript` 제거 후 텍스트 추출 → **색인 전 정제됨**(233,110 → 8,127자, 29배 압축). 다만 `nav`·`header`·`footer`·사이드바는 제거 대상 아님 → **문서 앞머리에 메뉴·로그인·검색 UI 문자열 잔존**. 계단 2에서 관측한 `blog.naver.com` EXIF·공감수 오염(catch P 초기 가설)의 실제 원인. `:392` 정규식 폴백은 script 잔존 | 부분 조치 |
| **Y** | `ingest_net` SSL 블랙리스트가 세션 단위로 4개 도메인 차단: `webzine.seoulmetro.co.kr`, `shareit.kr`(농심 팝업), `marketcast.co.kr`(글로벌 AI 캠페인), `bizon.kookmin.ac.kr`. macOS 이관 후 SSL 이슈(OpenAlex/SS urllib 수정과 동일 계열 추정). 해당 건은 `content` 스니펫(160자)으로만 색인 → 본문 결손. **WARNING 있음**(조용한 손실 아님) | 미조치 |
| **Z** | 웹 청크 평균 1,843자(로컬 250자의 7.4배)로 임계 1.10 통과율 100% — **변별력 상실**. 대형 청크가 어휘 다양성으로 모든 질의에 근접. 07주 질의 상위 10위 중 3건이 13주 팝업 자료(1.011~1.014). **catch L(md 허브 청크)의 웹 버전.** 임계 0.95에서 50% 통과로 변별 회복, 오염 3건 전량 배제 | **3-b 판단 대상** |

### 5.4 계단 2 잔여분 정정

| # | 내용 | 정정 |
|---|---|---|
| **K** | xlsx 추출 손실(설계표 19행 → 3청크). **초기 가설(topic_config 키워드 필터)은 철회.** `get_xlsx_keyword_groups`는 `ingest_vector.py:479`(벡터 색인 단계)에서만 사용되며 `local_rag.py`는 호출 0건. 실제 지점은 `local_rag.py:786` — `_read_xlsx_tsv`가 **시트 루프 안에서 `row_index=1`로 item 1개만 append** → 시트 전체가 단일 텍스트 덩어리. `rows_cap=500`과 무관(19행). pptx가 슬라이드당 item 1개인 것과 대칭이나, **표는 행이 의미 단위**라 부적합 | 위치 확정, 미조치 |
| **L** | md 과분할이 **허브 청크**를 생성, 로컬에 답이 없는 질의에서 상위를 독식. `경험경제-파인앤길모어-상세내용1.md`(197청크, 인덱스의 65%)가 14개 질의 중 10개에서 1위. 15주 "AI 가상인간 VR" 질의에 1998년 저작이 0.954로 1위, 8주 "팬덤 콜라보"에서 실제 사례 보유 자료(`week3_..._note.docx`의 질레트 마하3)를 밀어냄. **계단2 §3.3의 "md 유입 0건" 판정은 정답 존재 질의로만 검증한 결과** | 실측 확인 |

---

## 6. 커버리지 재판정 (catch L 반영)

계단 2 close의 "10주 공백" 판정을 정정한다. 거리값 단독 판정이 위양성을 낳았다.

| 판정 | 주차 | 근거 |
|---|---|---|
| **실보유** | 2, 3 | 2주=파인앤길모어(주제 일치), 3주=schmitt pptx |
| **부분** | 1 | 골자 md + 1주차 강의초안 pptx |
| **공백** | **4~13, 15 (11주)** | 전부 허브 청크 오탐 |

**규칙: 커버리지 스캔은 거리값만으로 판정 금지. 출처 파일의 주제 적합성 육안 확인 필수.**

---

## 7. 미해결 항목

| # | 항목 | 우선도 | 비고 |
|---|---|---|---|
| 1 | **catch P — allowlist 교체** | 🔴 최상 | 3-b 최우선. §3.4 실측 목록을 `ALLOWED_DOMAINS_EXTRA`로. 합집합이라 `naver.com` 제거는 불가 |
| 2 | **catch Z — 임계 1.10 재검토** | 상 | 웹 100% 통과 = 변별력 없음. 0.95 후보. 로컬 분포와 함께 판단 |
| 3 | **청크 크기 비대칭** (web 1,843 / local 250, 7.4배) | 상 | catch L·Z의 공통 뿌리. 청킹 설정 통일 필요 |
| 4 | **07주 쿼리 품질** | 중 | `성공 사례`가 대행사 SEO 블로그를 부름. `숏폼 챌린지 캠페인` 또는 플랫폼명(`틱톡 챌린지 브랜드`) 검토 |
| 5 | **catch T — tavily 미호출** | 중 | `SEARCH_TOPN` 조기종료. `.env` 수정으로만 검증 가능(catch V) |
| 6 | **catch V 검증 미완** | 중 | ⚠️ `engine="tavily"` 인자 반영 실패 확인 시 `probe_search.py:29` 실제 수정 여부를 **재grep으로 확인하지 않았다.** 미수정 상태였을 가능성 잔존 → 재확인 전까지 catch V는 잠정 |
| 7 | **catch Y — SSL 블랙리스트 4건** | 하 | 유효 소스 3건 포함. 인증서 설정 점검 |
| 8 | **catch X — boilerplate** | 하 | 앞 1~2청크만 오염. 본문은 온전. `nav/header/footer` decompose 추가로 해결 가능 |
| 9 | **catch K — xlsx 시트 단위 청킹** | 하 | 설계표 E열은 수동 확보로 우회함. 별도 사이클 |

---

## 8. 이번 사이클 오판 기록

| 오판 | 원인 | 교훈 |
|---|---|---|
| `handled=False`를 "무시됨"으로 읽고 실행 승인 | fallthrough 가능성 미확인 상태에서 STOP 게이트 통과 | **미확인 항목이 있으면 유료 실행 승인 금지** |
| "진입점 = FastAPI" (R0) | 파일을 열지 않고 프로젝트 구성에서 추론 | 진입점은 서버 기동 코드로 확인 |
| `grep "@app.post"` 0건 → "라우트 없음" | 객체명을 `app`으로 가정 | **grep 0건은 부재 증명이 아니다.** 프레임워크 import부터 역추적 |
| `agent/`·`tools/`·`core/`만 grep → 함수 미발견 | 탐색 범위 선제 축소 | `git grep -n "<symbol>"` **무필터 우선** |
| topic_config 키워드가 xlsx 절단 원인이라 단정 | 정의부만 보고 사용처 미확인 | **값의 존재 ≠ 값의 작동** |
| `ALLOWED_DOMAINS`가 낡았다 → "범인 확정" | 게이트 활성 여부 미확인 | 동일 |
| "게이트 OFF인데도 21건이니 allowlist 무관" | 셸 override가 reload에 무효화됨을 모름 | **판정 근거는 실행 로그의 동작 흔적**(DROP 로그), 설정 선언값 아님 |
| 로깅 미설정 상태로 원인 추정 반복 | `basicConfig()` 누락 → `logger.info` 전량 소실 | 측정 스크립트는 **로깅 설정을 첫 줄에** |
| `raw_content` 그대로 색인 → $3.9 견적 | 정제 단계 존재 여부 미확인 | 견적 전 파이프라인 끝까지 추적 |
| 코드 수정 지시가 두 차례 미반영 | "이렇게 바꿔"로 조각만 전달 | **줄 번호 + 현재 줄 + 교체 줄** 3종 세트로 지시, 수정 후 재grep |

**공통 구조**: 대부분 *확인 없이 다음 단계로 진행*했고, 그중 하나(catch O)는 실제 비용을 발생시켰다.

---

## 9. 운영 규칙 (이번 사이클 확립)

**env override 판정**
> 이 repo에서 env override 가능 여부는 **키별로 코드 확인 후 판정.**
> 성공 사례(`TOPIC_SLUG`)를 다른 키에 일반화 금지.
> 확인 못 했으면 `.env` 백업+수정+복원이 기본 경로.

실측 결과: `TOPIC_SLUG` ✅ / `GATE_KEEP_SOURCES` ❌(reload가 덮음) / `SEARCH_BACKENDS` ❌(CFG 우선) / `WEB_SEARCH_ENGINE` ❌

**심볼 탐색**
> `git grep -n "<symbol>"` 무필터 먼저. 경로 제한은 결과가 많을 때만 사후 적용.
> 루트(`app.py`·`graph.py`)와 `utils/`에 실행 로직이 있어 `agent/`·`core/`만 뒤지면 놓친다.

**측정 스크립트 표준**
> `logging.basicConfig(level=DEBUG)` + `urllib3`/`httpx` WARNING 억제를 **모듈 import보다 먼저.**
> 로거 없이 실행하면 `logger.info` 전량 소실되어 원인 추정이 불가능해진다.

**dry-run 게이트 (웹 경로)**
> `web_results_to_documents()`까지는 임베딩 0. 여기서 문자 수·본문 샘플·정제 품질을 확인한 뒤
> `_ingest_add_docs()`로 넘긴다. 계단 2의 `add_web_pages_json_to_chroma` 미주입과 동일 패턴.

**커버리지 스캔**
> 거리값 단독 판정 금지. 출처 파일의 주제 적합성을 육안 확인한다.
> 정답이 존재하는 질의로만 검증하면 허브 청크 문제가 드러나지 않는다.

---

## 10. 산출물

| 파일 | 성격 |
|---|---|
| `probe_search.py` | 검색 프로브. 임시, 커밋 안 함 |
| `probe_ingest_dryrun.py` | 정제 견적. 임시 |
| `probe_ingest_run.py` | 색인 + 거리 분포. `--go` / `--measure` 플래그. 임시 |
| `probe_search_result.json` | 135건 메타(host·url·title·clen·rlen) |
| `probe_A.log` ~ `probe_ingest.log` | 실행 로그 |
| `research/resources_2026_08_01_174*.json` | 수집 원자료 4건 |
| `data/chroma_store/experiential-marketing-media-web` | **416청크** |

코드 변경 0건. `.env` 변경 0건. 계단 2의 미커밋분(`tools/local_rag.py:503`)은 그대로 유지.
