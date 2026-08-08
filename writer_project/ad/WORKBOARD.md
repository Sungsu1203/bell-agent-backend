# WORKBOARD — 회사 트랙 (광고·마케팅 writer)

> 🏢 회사 트랙 할일·활성 트랙·결정 기록. 운영 규칙은 ./GUARDRAILS.md, 공통은 ../CLAUDE.md.

---

## 지금 상태 (한 줄)
**§research-1 활성.** objective 기반 리서치 리포트 파이프라인(8단계). **선분 1(objective→쿼리) 종결(Q-2)**,
**선분 3(수집→색인) 정찰 범위 결정 중** — 후보 A 크롬제거 / B 플레이스홀더 / C `published_date` / D 조각ID.
§ad-track-1은 **완료(E열 미충족, 미스매치 판정)**로 이동.

## 활성 트랙

### §research-1 — objective 기반 리서치 리포트 파이프라인
- **시작** 2026-08-03 / **토픽** `topics/experiential-marketing-media.env` (ad/research 트랙 공유)
- **venv** `../.venv_openai/bin/python`
- **북극성** objective → 쿼리생성 → 수집 → 색인 → objective별 retrieve → 충분/부족 판정 → 재쿼리 루프 → objective별 writer
  📄 `scripts/output/§research-1/R2c_NORTH_STAR.md` (착수 판정 테스트 포함)
- **현재** 🟢 **선분 1(쿼리 생성) 요건 확정 · Q-2 종결(2026-08-06).**
  다음은 **선분 3(색인 위생) 정찰 범위 결정(챗 소관)**
  ⚠️ 결정 4는 **선분 1로 대체됨**. 코드 반영 방식은 **미정**(방식 (나) 기각)
- **누적 비용** R1~R2 $0 / R3-1 유료 4회(≈73,281토큰) / **Q-1 $0.03 · Q-2 $0.015**

> 🔴 **착수 판정**: "이 작업은 8단계 중 어느 선분을 잇는가?" 답이 안 나오면 **이월표로.**

| 단계 | 결과 |
|---|---|
| R1 | 그래프·fast-path·근거사슬 정찰. **계기판 기발견**(9노드 `emit_event` + `/api/events`·`/api/state`) → 계측기 삽입 작업 소멸 |
| R1b 감사 | credential 이력 오염 발견 → STOP → 키 회전(사용자) + HEAD 정리 + `.gitignore` 보강 + 감사 절차 3축 개정 |
| R1b 대조 | 원형 BlockAGI Plan↔Evaluate 배선 실측 |
| R2-a | 설계 입력 수집 + R1b 정정 2건 |
| R2-b | 결정 1(JSONL 스키마)·3(2단) 확정, 결정 2 결론 |
| R3-a 정찰 | T1~T16 — 진입점·dedup·state·프롬프트 실측. 박제 `R3a_ENTRYPOINT_RECON.md` |
| **R3-1 run1** | 본선 retrieve 0회 · 마커 17(전부 고아) · 사이드카 0 — `flags.smoke_retrieve_done` 이월로 §2~7 스모크 스킵 |
| **R3-1 run2** | 본선 retrieve **0회** · 마커 17(전부 고아) — **쿼리 0개**(`(summary) total 0 queries`). 쿼리 소스 4관문 전부 빔 |
| **R3-1 run3** | 본선 retrieve 7회 · **마커 0** · 사이드카 0 — Direct QA 조기 반환(`:1305`×5/`:1342`×2) + `[이전 대화]`에 QA 산문 유입 |
| **R3-1 run4 (B안)** | **파이프라인 첫 작동** — 사이드카 5 · 마커 12(출처연결 11) · 요약 11콜 · 접힘 0%. **D4 ② FAIL**(§1 마커0 / §7 고아1) |
| **목표 재정의** | 08-06 — "연구 루프 구조 재설계" → "objective 기반 리서치 파이프라인". 결정 4 대체. 박제 `R2c_NORTH_STAR.md` |
| **Q-1 arm 측정** | X/Y/Z/Z' 4arm · 52쿼리 · dist 5,200값. **X 기각**(catch BZ) · web/local 내용 분리 확정(BX) · **크롬 29% 발견**(CA). M4 108건 육안 분류 |
| **Q-2 선분 1 종결** | Z''(요구형) 실측 — 술어 보존 58%→**78%** · 연도 0/4→**3/4** · 병기 국문만 4쌍→2쌍. X 회귀 없음. 박제 `Q2_SEGMENT1_CLOSE.md`(커밋 `16de443f`) |

**🔴 R3-1 3대 발견**
1. **B안 확정** — `vector_search_agent` 우회(`_dual_retrieve` → `merge_refs` → `section_writer`).
   그 노드는 D4 산출물을 생산하지 않는 래퍼다. **삭제 아님, 우회. 챗 UI 경로는 그대로**
2. **web 통과율 3.6%** (28→1) vs local 71.4% (14→10) — **실질 코퍼스는 local 302청크뿐** (catch BK)
3. 🔴 **조작은 환각이 아니라 지시 이행** — `[Executive Summary 규칙]` 블록이 **7/7 주입**(절단 분기 0).
   그리고 **§1 은 refs 0 에서 최대 조작을 하고 마커 0 이라 전 검사를 통과했다** — 검사망 최대 사각 (catch BC/BO/BR)

**🔴 R1의 3대 발견**
1. **근거 사슬은 본선에서 안 끊긴다.** X는 `research_synthesizer` 곁가지 1곳뿐이고 소비처가 0건.
   본선은 `[[N]]` 인덱스 + `.refs.json`(URL + 청크 풀텍스트)로 살아 있다
2. **Evaluate→Plan 되먹임 배선이 없다.** 목표는 env 5개 고정 순회(`research_planner.py:227`)
3. **원인은 배선이 아니라 출력 형식.** 원형은 Evaluate 출력에 JSON 스키마를 강제하고
   `json.loads` → dataclass로 필드를 꺼낸다. 우리는 마크다운 자유 서술이라 추출 불가
   → **R2 과제가 "슬롯 1개 추가"에서 "출력 스키마 + 파서 + 슬롯"으로 확대됨**

**우리가 원형보다 나은 2건** (이식 불요): 루프 종료(`no_new_url_streak` 보유) · citation 보증(`.refs.json`)

**이월 — §research-1 (R3b 시점, 2026-08-07)**

| # | 항목 | 우선도 |
|---|---|---|
| **선분 3** | 🔴 **색인 위생 정찰 범위 결정(챗 소관).** 후보 A 크롬제거 / B 플레이스홀더 / C `published_date` / D 조각ID / E 구조보존파싱. ⚠️ **범위를 먼저 좁힐 것** — 다 넣으면 §ad-track-1처럼 미달로 끝난다.<br>✅ **정찰 종료(R3b·R4·R5·R6·R7, 2026-08-08).** 남은 미지 = **크롬 판별 규칙** — 정찰로 풀 수 없고 규칙 초안 + 실측이 필요하다 | **최상** |
| **A 측정 설계 전제** | 🔴 **`q1_arms_dist_raw`(29%)는 before로 쓸 수 없다** — 현존 `*_filtered.json`과 색인 118의 교집합 0, 즉 그 색인은 재현 불가. → **신규 수집 1회 → 같은 `*_filtered.json`에서 색인 2벌**(X 현행 / Y 크롬제거+날짜). before는 X에서 새로 잰다. 29%는 "문제 존재"의 근거일 뿐 **대조 기준선 아님.** ⚠️ 착수 조건 — 수집 직후 그 파일을 **별도 경로로 복사하고 경로·해시를 박제**한다(현재는 `catch CK`의 우연에 기대어 남는 상태). ⚠️ provider 고정 + 실효 NS 3키 실행 시 출력 확인 | **최상** |
| **A 제거 지점** | 🔴 **`ingest_docs.py:260`** `web_results_to_documents`. `soup.get_text(separator="\n")` = 본문 추출 아님, 제거 태그 `script`·`style`·`noscript` 3종뿐. trafilatura·readability 전 레포 0건. **`get_text()` 이후 태그 정보 소실** → 하류 필터 9개는 문서 단위 또는 청크 단위뿐, **문서 내부를 도려내는 층이 없다.** 🔴 **수리 자리 = bs4 2곳**(`ingest_docs.py:386` 분기 · `ingest.py:677`). 둘은 문자 단위 동일 로직이고 `content_type`이 둘 다 `text/html`이라 **색인 메타로 가를 수 없다 → 대칭으로 고친다.** ⚠️ 종전 "사본 3벌"은 **챗 발 오판(39)** — `:260`은 진입점, `:386`은 그 분기다. 사문 2건 확인: `seed_web_namespace:1845` · `search.py:202`. R5 §2 · R6 §1 | **최상** |
| **선분 1** | 🟡 **쿼리 생성 = 종결(Q-2).** 요건 4건 확정 — 술어 보존 58→**78%** · 연도 0/4→**3/4** · 국내강제 제거 · 갈래 분해(X 회귀 없음). Z'' 문안 박제 `Q2_SEGMENT1_CLOSE.md`. 🔴 **남은 것 = objective별 아웃라인 + writer 설계.** 결정 4를 대체함(A 소멸 · B 흡수 · C 불변, `section_writer.py:277` 수정 0건) | **최상** |
| **catch CA** | 🔴 **사이트크롬 색인 오염.** nav·푸터·사업자정보·직원명단이 dist **0.669~1.081**로 상위 통과. web 통과 청크의 **29%**(19/65), local 0건. **임계 조정 불가 — 수집·색인 제거가 유일** | 최상 |
| **catch BX** | 🔴 **web/local 내용 분리** (구 BK 재해석). web min dist — 이론·측정 1.158~1.426(전량 탈락) / 사례·트렌드 0.545~0.811(대량 통과). local은 정반대(홀브룩 0.554·분트곡선 0.634·브라커스 0.738). **objective 1·4는 web에서 원리적 불가.** BK를 "인덱스 부실"로 읽은 것은 오독 — `RETRIEVE_WEB_RATIO` 조정 사안 아님 | 최상 |
| **catch BZ** | 🔴 **형태 분류로 부적합을 못 잡는다.** X obj1 web rank1·2 = 본문형·통과·완결문단이면서 주제 완전 불일치(뷰티 팝업 vs 이론 계보 쿼리). 쿼리 고유명사 13개 중 실재 **0**. 동일 쿼리 local은 정확 매칭(0.5342). **BT(껍데기)에 이은 제2 유형 사각** | 최상 |
| **catch BT** | 🔴 **껍데기 청크 유도 조작.** 목차·헤딩 수준 청크가 "항목 존재"만 전달 → writer가 내용을 채움. §2 부재 7건. refs 2건 + 마커 정상이라 전 검사 통과 | 최상 |
| **catch BS** | 🔴 **objective 원문이 근거 대체재.** round-02 `## 근거 요약` 4건 중 3건이 objective 1 재진술에 `[저자(연도)]` 라벨 부착. 근거 얇을 때 objective가 findings로 역류. ES 블록과 독립된 **제2 조작 경로** | 최상 |
| **판정선** | 🔴 **`refs.docs == 0 && 본문 길이 > N → 즉시 FAIL`.** run4 실측 = refs 0 섹션(§1·§7)이 조작 2섹션과 정확히 일치. 밀도 휴리스틱 불요. ⚠️ **프롬프트 교체가 이 사각을 닫지 않는다 — 별건으로 살아 있다** | **최상** |
| 판정선 개정 | refs==0 단독 불충분(§2 미검출). D4③ **표본 → 전수** 확정(표본이 최악 §2를 놓침, 전수 실비용 $0 확인) | 최상 |
| **catch AY** | `published_date` 메타데이터 부재 — objective에 "2023~2026" · "2025~2026 최신 동향"이 명시돼 **날짜 없이는 구조적으로 충족 불가.** 선분 3의 선행 조건. 중 → **상 승격** | 상 |
| **catch CB** | local 플레이스홀더 오염 — `🟨 실무 사례 자리` 슬라이드가 색인 포함. 2건, web 0건 | 상 |
| **catch BU** | 🔴 **근거 미활용.** §5 refs text에 92%·별점 4.8·아마존 실재, 본문 사용 0. **검사 항목 자체가 부재** | 상 |
| **코드 반영** | 🔴 **미정.** 방식 (나)"v2 함수 신설" **기각** — 호출부 `research_planner.py:229` 1곳이 챗 UI 본선. 후보 (다)조건분기/(라)전용노드/(마)state주입. **결정 시점 = R3-2 루프 설계 후** | 상 |
| **선분 1 이월** | ① obj4 취약(14중 7, 참여지표 갈래 미배정) ② 영문 소실 `experiential grid`·`customer journey map` ③ 자수 하한 미달 6건. ⚠️ **규칙을 추가하지 말 것** | 상 |
| **catch CE** | 🔴 `CHROMA_DIR` 2순위 경로 사문. **읽는 자리 = `tools/web_rag/utils.py:1734`** (`_cfg_str("CHROMA_DIR", default="")`). 그 `_cfg_str`(**utils.py:122**)이 `getattr(CFG, key)`만 읽고 `os.environ`을 안 본다. `Config`(config.py:228)는 `@dataclass`이고 `CHROMA_DIR` 필드 0건 → `AttributeError` → `default=""`. `core/topic.py:142`의 환경변수 미러링은 이 경로에 미반영. **에러 없이 조용히 기본 경로.** 색인 격리는 `CHROMA_NAMESPACE`(L3 topic preset)로만 가능. ⚠️ CFG 재빌드 경로는 미확인<br>⚠️ **2026-08-07 보강 실측** — `.env:125`에 `CHROMA_DIR=data/chroma_store`가 **주석이 아니라 활성 상태로 존재**한다. 값이 없어서가 아니라 **값이 있는데 무시된다.**<br>⚠️ 이 건은 `STANDARDS §1.3` **0단**이 이미 규정한 경우다(CFG 선언 0건 → `.env` 무효, 2~4단 생략). 0단을 밟지 않아 우회로로 갔다. 거짓 0의 원인 = **grep 심 치환(ugrep `--ignore-files`)이 `.gitignore:16-17` 대상인 `.env*`를 배제** → `catch CG`(CLAUDE.md §9)<br>⚠️ **2026-08-08 R4 off-by-one 정정** — 구 문안이 가리킨 `utils.py` `:121`은 `def`가 아니라 `if "_cfg_str" not in globals():` **가드 줄**이다. 정의는 `:122`. 같은 파일 `_cfg_bool`은 `:742`에 **가드 없이** 별도 정의(시그니처도 키워드 전용) — 동명 사본이라 인용 시 위치 확정 필요. R4 §5-a | 상 |
| **재색인 실측** | 🔴 **정정(R7)** — `research/resources_*.json`은 **기록용 스냅샷이고 색인 입력이 아니다**(`_to_safe_json_record:581-583`이 4000자 절단, 113/113 정확히 4000). 색인 입력은 `*_filtered.json`이며 **`raw_content` 보존**(수집 시점 raw_bytes 14,584~16,569,880). 실행 로그 65행 전수 — 스냅샷을 읽은 기록 **0행**. ⚠️ 종전 "원자료에 본문 없음"은 **파이프라인이 안 읽는 파일을 잰 것**(catch CI 계열). → **드리프트 없는 대조가 가능할 수 있다** — 같은 `*_filtered.json`에서 색인 2벌. ✅ **잔존 확인(R7 §1-b-9)** — 삭제 코드 **0건**(`_filtered` 2행 = 생성부·주석, `os.remove`/`unlink`/`rmtree` 14행 전량 대상 확인). 현존 **43건**(mtime 06-01~08-01, 합 19.9MB). `raw_content` 80/80 보유, **>4000 15건 · ==4000 0건**(같은 라운드 스냅샷은 `raw_preview` 276 · >4000 0 — 정반대 형태로 공존). 🔴 **단 현존 43건 ∩ 색인 118 = 0.** 드리프트 없는 대조는 **신규 수집 1회분으로만** 가능. 링크로트 97.5%는 그대로 유효. 🔴 배치 = **46**, `CHROMA_MAX_BATCH=16`에 걸린 배치 **0/46**(64로 올려도 46) — 실제 제약은 하드코딩 `MAX_TEXT_SUM=18000`(`ingest_vector.py:1236`), **env로 못 바꾼다.** `INDEX_TIMEOUT_SEC=60`은 중단이 아니라 **사후 경고 로그**(`_batched_add:646-651`) → 시간 추정 근거 아님. ✅ **링크로트 GET 기준 115/118(97.5%) · 413/416청크(99.3%) 생존** → 재수집 성립. 잔여 3건은 SSL 미해결(죽은 링크 아님 — 논문 트랙 certifi 전례 확인 필요). R5 §4 · R6 §3 | **상** |
| **catch CH** | 🔴 **refs 병합층 접힘.** `utils/rag_utils.py:234` `_doc_key_from_any` 키 = `norm_url\|src:…##part`. web 메타에 `part`/`page`/`fragment`가 **없어**(R4 §2-a 4키) 같은 URL의 N청크가 **1건으로 접힌다.** local은 `source` 자체에 `#part=…&chunk=N`이 박혀 안 접힌다. 호출부 8곳 전량이 그래프 노드 3개(`research_planner`·`vector_search_agent`·`web_search_agent`) **몸통 안**. 정의 2벌 중 `utils/refs.py:255`는 **사문**(본선 import 0곳) — R2c의 `_canonicalize_src_for_dedup` 판정과 정합.<br>⚠️ **논문 트랙 실행 X 확인**(R6 §4). 단 근거는 **함수 경계 스캔**이라 R3b(디렉토리 부재, 물리 증거)보다 약하다. R5 §3 · R6 §4 | 상 |
| **C 게이트** | 🔴 **`published_date` 비용이 분기마다 다르다.** 사본 ①(`ingest_docs.py:386`) = DOM `:385~390`, 반출 경로 **있음**(`:398` 메타 dict) → 한 줄. 사본 ②(`ingest.py:677`) = DOM `:675~682`, 반출 경로 **없음**(계약 `(url,timeout) -> str`) → 시그니처 변경 + 호출부 연쇄. **어느 쪽이 본선인지 미확정.** 폴백(except) 경로는 양쪽 다 정규식이라 DOM 부재 → 불가. ⚠️ 날짜 추출 코드 전 레포 0건, `soup.find`/`find_all` 0건 — **C는 확장이 아니라 신규 기능.**<br>✅ **열림(R7).** 분기 조건 = `ingest_docs.py:382 if raw_content:` truthy 단독(길이·품질·CFG·env 참조 0건). 색인 입력에 `raw_content` 보존 → **갈래 ①이 기본.** → **C 비용 = ① 한 줄.** ②(enrich 실패 폴백)로 빠진 문서는 날짜 없이 통과(열화 허용). ⚠️ 현 색인 118건이 실제 어느 갈래였는지는 **확인 불가** — 해당 라운드 파일 부재, 로그에 07-31 없음. 코드 경로 근거이며 실행 흔적 근거 아님. R6 §2 · R7 | 상 |
| **catch CK** | 🔴 **정규 writer 산출물을 아무도 안 읽는다.** `web_search.invoke`가 `(results, path)`를 반환하나 `:848`에서 path 폐기 → `:948 json_path=""` → fallback writer(`:966-967`)가 **항상** 발동. 결과 ① 매 라운드 두 파일 쓰기 ② 정규 writer 사문 ③ **`_to_safe_json_record` 절단이 파이프라인에 미발동.** ⚠️ ③이 지금 `raw_content`를 살리고 있다 — **우연이다.** `:848`을 "고치면" 절단이 살아나 원본 HTML이 사라진다. **손대기 전 이 행을 볼 것.** R7 | 상 |
| **D 재기술** | 조각ID 신설은 **소멸** — `<sha1>-<6자리>`가 이미 있고 전건 유일. 저장층 접힘 0(118 URL → 416 청크). 남은 것은 **`source` 입도 불일치**(web=문서 단위 / local=`#part=&chunk=N` 청크 단위). **하류에서 `source`를 키로 쓰는 자리가 있을 때만 문제** → 정찰 2에서 grep 1회로 판정 | 중 |
| **R3-2** | 결정 1 스키마(`round-NN.jsonl`) + 파서 + planner 슬롯 = **선분 6~7(판정→루프).** 착수 시 `research/<slug>/` 구·신 형식 혼재 처리 방침 필요 | 중 |
| **catch BV** | `utils/query_filters.py:107` `r"\\b"` 리터럴 → BOOLEAN_TOKENS 제거 무작동. 선분 2 착수 시 수리 | 중 |
| catch BL | `chunk_summary` 섹션 간 캐시 없음 — 동일 청크 재요약(유료 콜 중복). objective 단위 전환 시 재측정 | 중 |
| catch BQ | 모델 입력 = snip 350자 ≠ 대조 대상 = 청크 원문. 7건 중 5건 절단(최저 15%) | 중 |
| **catch CF** | "공유"가 3의미로 갈린다 — **파일 / 로드 / 실행**. 결과를 바꾸는 건 실행뿐. `ingest_vector.py`는 논문 트랙에서 **로드되지만 호출되지 않는다**(R3b). 판정 근거는 코드 추적이 아니라 `academic-trademark-*` 디렉토리 부재(물리 증거).<br>⚠️ **제2축** — "두 트랙"이 어느 두 트랙인지도 문서마다 다르다. GUARDRAILS:41-42 = §ad-track-1·§research-1(명시). 인계 메모·WORKBOARD:124는 회사/논문으로 읽혔다. `ingest_vector.py`는 전자 기준으로는 공유가 맞다 | 중 |
| **Q2 §3.1 대조** | `probe_q1_arms.py:481`·`probe_q2_zdouble.py:523` 행번호의 출처 미확인. 심 grep으로는 나올 수 없는 값이 문서에 있다. 갈래 = ①다른 경로로 검색 ②검색 아닌 출처 ③심 동작이 세션마다 다름(=비균일). **③이면 `catch CG` 문안이 틀린다.** 다음 정찰에 얹어 확인 | 중 |
| **catch CJ** | `seed_web_namespace` 경로 2중 사문 — ① `SEED_URLS`가 CFG·`.env` 4파일 전부 0건 → `_get_seed_urls` 항상 `[]`(`supervisor.py:235` 반환) ② 호출/정의 인자 불일치(`topic_slug` 미존재 파라미터)를 `except Exception`(`:243`)이 삼킨다. ⚠️ **재수집 설계에서 seed 경로를 쓰면 조용히 실패한다.** R6 §1 | 하 |
| ~~catch BW~~ | **철회** — "임계 변별력 부재"의 근거 distinct 32~44%는 52쿼리 **합집합 커버리지**였다. 쿼리별로는 0/50~50/50. 임계는 작동한다 | 철회 |
| ~~catch BY~~ | **정정** — "objective 3 = 코퍼스 구멍"은 오판. 자료는 있고 쿼리가 못 찾았다(X obj3 local 0.667 · Y 3-c 0.713). 선분 1로 이관 | 정정 |
| ~~catch BC~~ | **원인 확정으로 종결** — `[[N]]` + "~에 따르면" + 근거 부재 = **명시적 지시 이행.** 지시 제거는 선분 1에 포함. 증거물 `_FAILED_*` 보존 | 종결 |
| ~~catch BO~~ | **선분 1에 흡수** — 규칙 합성("수치 필수" + "출처 표기 필수"). 신규 프롬프트 작성 요건 | 흡수 |
| ~~catch BR~~ | **선분 1에 흡수** — 장르 미스매치. 전용 프롬프트 신설로 해소, 챗 UI 광고 틀은 불변 | 흡수 |
| ~~§8-4~~ | **조사 취소** — 참조 전 섹션 공용 8건. objective별 refs 주입으로 구조 소멸. 신규 드라이버 요구사항 **"objective별 refs 교체(누적 금지)"** 1줄로 대체 | 취소 |

`CC·CD = 결번 (Claude Code 약칭과 충돌)`


- **드라이버** `scripts/§research-1/run_r3a_straight.py` · `probe_q1_arms.py` · `probe_q2_zdouble.py` (전부 `.gitignore` probe_*/untracked)
- **박제** `R1_FINDINGS.md` · `R1b_{CREDENTIAL_AUDIT,HYGIENE_CLOSE,BLOCKAGI_COMPARE}.md` · `R2a_DESIGN_INPUTS.md` · `R2b_DECISION_1_3.md` · `R3a_ENTRYPOINT_RECON.md` · **`R2c_NORTH_STAR.md`** · **`Q2_SEGMENT1_CLOSE.md`**(커밋 `16de443f`) · **`q1_arms_dist_raw_20260806.md`**(커밋 `dda58a70`·`5b16cdd5`, **push 완료**) · `R3b_INGEST_SHARE_RECON.md`
- **원자료** `q1_arms_20260806-161606.json`(16.0MB, ignored) · `q2_zdouble_20260806-210440.json`(ignored)
- **실행 로그** `scripts/output/§research-1/R3a_run_*.log` 6건 · 결과 JSON 4건 · 산출물 `sections/…/_FAILED_20260805-run{1..4}_*`(삭제 금지)
- **대조 자산** `~/dev/blockagi-ref`(upstream, 읽기전용) · `~/dev/blockagi-run`(포크, `ahead 1` 미push)

## 완료 트랙

### §ad-track-1 — 체험마케팅과 미디어 콘텐츠 (홍익대 대학원 15주) — **완료(E열 미충족)**

> **종결 판정**: 목표(E열 14칸)에 도달하지 못했다. arm Z로 3요소 5건 + 준확정 3건까지가 실적이다.
> 미충족 사유는 수집 부족이 아니라 **파이프라인과 목표의 미스매치**로 판정됐다 —
> 리포트 생성 경로는 브랜드·연도를 깎고(catch AN), 추출 경로는 소스 그룹핑·`published_date`가 없다.
> 잔여 계단(3-d-1 ④~⑧, 3-d-2 ⑨)은 아래 **이월** 표로 이관.
- **시작** 2026-07-30 / **토픽** `topics/experiential-marketing-media.env`
- **목표** 15주 설계표 E열 14칸을 **브랜드 + 캠페인 + 연도 + URL** 4요소로 채운다
- **현재** 계단 3-d-1 (①②③ 완료 / ④⑤⑥⑦⑧ 이월)
- **누적 비용** ≈ $0.25

| 계단 | 결과 |
|---|---|
| 0~2 | 환경·인덱스 구축. `-local` 302청크 / `-web` 416청크 |
| 3-a | 웹 수집 4주차(04·07·13·15). catch J~AA |
| 3-b | LLM arm 리포트 경로. **실패** — 브랜드 27회 참조에 본문 0회(catch AN), 연도 0건. $0.12 |
| 3-c | **arm Z(비-LLM) PASS.** `retrieve` → 청크 원문 + `metadata.source` 직결. 3요소 5건. $0 |
| 3-d-1 | ①git ②커밋 ③catch AT 종결. 코드 변경 0건 |

- **박제** `scripts/output/§ad-track-1/step3{a,b,c}_close_§ad-track-1.md`
- **도구** `probe_Z_extract.py`(arm Z 드라이버) · `probe_dist_adtrack.py`(거리 분포) · `scan_local_coverage.py`

## 결정 기록

| 일자 | 결정 | 근거 |
|---|---|---|
| 08-02 | **추출 경로 = arm Z (비-LLM)** | 목표물이 원문에 있으면 추출이 생성보다 낫다. LLM은 브랜드·연도를 깎는다(catch AN) |
| 08-03 | **`RAG_DISTANCE_THRESHOLD` 조정하지 않음** | 1.10에서 04·13은 100% 통과. 상향하면 04·13 최악(0.98)보다 먼 자료가 섞인다 |
| 08-03 | **NS별 임계 분기 도입하지 않음** | ① local 5.6% 통과는 정상 작동 ② 1.10~1.25 구간에 E열용 사례 없음 ③ `ingest_vector.py`는 두 트랙 공유<br>⚠️ **2026-08-07** — 근거 ③의 "두 트랙"이 어느 쌍인지 원문으로 확정되지 않는다. 회사/논문 독법이면 파일 공유일 뿐 실행 공유가 아니다(R3b, 논문 트랙 호출 0건). §ad-track-1/§research-1 독법이면 그대로 참이다. 어느 쪽이든 근거 ①②가 독립적으로 성립하므로 이 결정은 유지된다. `R3b_INGEST_SHARE_RECON.md` · `catch CF` |
| 08-03 | **07·15주 재수집 필요 확정** | 04·13 최대값 ≤ 07·15 최소값. 임계가 아니라 자료 이격 |
| 08-03 | 논문 트랙 미커밋분 **A안**(개별 add 유지) | stash 분실 위험(B) · 남의 트랙 커밋 월권(C) 기각 |
| 08-05 | **history scrub(`filter-repo`) 기각 — 재론 금지** | 회전하면 옛 키는 무효 문자열. scrub은 죽은 문자열을 가릴 뿐인데 **모든 커밋 해시가 바뀌어** 1년치 박제의 추적성이 파손된다. 두 레포 모두 적용 [STANDARDS §5.4-a] |
| 08-05 | **`blockagi-run` push 하지 않음** | 키가 콘솔에서 이미 삭제돼 무효. B-2 보류로 실익 0. 재사용 사유 발생 시 push |
| 08-05 | **credential 감사 = 파일명 축 1순위** | 구 절차(현행 키 prefix 검색)가 이전 세대 키를 원리적으로 놓쳤다. prefix 없는 키(naver·serpapi)는 정규식으로 검출 불가 [STANDARDS §5.1-a] |
| 08-05 | **§ad-track-1 완료 처리(E열 미충족)** | 미충족 사유 = 수집 부족이 아니라 파이프라인·목표 미스매치. 잔여 계단은 이월 |
| 08-06 | **목표 재정의 — objective 기반 리서치 파이프라인** | 기존 목표문("연구 루프 구조 재설계")이 8단계 중 하나만 가리켜 다음 세션이 루프만 보게 된다 [R2c_NORTH_STAR.md] |
| 08-06 | **코드 반영 방식 (나)"v2 함수 신설" 기각** | 호출부가 `research_planner.py:229` **1곳**이고 그 1곳이 챗 UI 본선이다. v2를 추가해도 :229가 무엇을 부르냐만 남아 트랙 분리가 성립하지 않는다 |

## 이월 — §ad-track-1 잔여 계단 (재개 시)

| | 단계 | 비용 |
|---|---|---|
| ④ | 게이트 위치 정찰 → catch P 재판정 | $0 |
| ⑤ | `published_date` 추출률 실측 → 구현 + diff STOP | $0 |
| ⑥ | arm Z 소스 그룹핑 개선 (catch AV 대응) | $0 |
| ⑦ | 목록 토큰 A/B 검색 dry-run → 10주 쿼리 확정 | $0 |
| ⑧ | 준확정 3건 URL 확인 → 승격 | $0 |
| ⑨ | a) aimatters 목록 4페이지 / b) 10주 신규 / c) 07·15 재수집(쿼리 변형 동반) | **유료** |

## 별건 이월 — credential·외부 서비스 (§research-1 R1b 발)

| # | 항목 | 기한 | 우선도 |
|---|---|---|---|
| 1 | **NAVER Search API → API HUB 이관** — NCP 계정 신규 가입 + 인증 체계 변경(개발자센터 Client ID/Key → API HUB Key) | **2027-06-30 지원 종료** (프로모션 2026-09-30) | 중 |
| 2 | **Naver Client Secret 회전** — 1번과 동시 처리 | 상동 | 중 |
| 3 | SerpAPI 계정 정리 (`.env` 미참조) | — | 하 |
| 4 | `gemini-rag-project-new` 프로젝트/계정 정리 | — | 하 |
| 5 | `blockagi-run` push (평문 키 제거 커밋, `ahead 1`) | blockagi 재사용 시 | 하 |

⚠️ 2번을 단독 선행하지 말 것 — **개발자센터 신규 신청 차단일(2026-07-31)이 지나** 재발급 가능
여부가 불확실하다. 섣불리 회전하면 **현행 키만 죽을 수 있다.** 현행 키는 200 응답으로 유효 확인됨.

> 회전 완료분·미착수분 상세 = `scripts/output/§research-1/R1b_HYGIENE_CLOSE.md` §E

## 보류 트랙 (재개 시 승격)
- **§13-8-3** Haiku 4.5 평가, dual/triple track cost·latency 세분화 [README-dev-2.md]
- **다른 토픽 일반화 검증** pet-food-premium·height-growth 등 [README-dev-2.md]
- **§13-14-α-sonnet R2 prompt 패치** [README-dev-2.md]

## 미결 과제 (원본: README-dev.md §12)
> 요약+포인터. 상세는 원본 §12. 종결·STANDARDS 이관분 제외.

- **메타데이터 풍부화** — `published_date`·`language` 추가. [§12-1] ⚠️ **§ad-track-1 catch AY와 동일 항목.** 3-d-1 ⑤에서 착수
- **distance threshold 재튜닝 절차** [§12-2] ⚠️ **체험마케팅 토픽도 절벽 부재형**(2026-08-03 실측, 인접 최대 점프 +0.11). venfobel과 동일하게 본 절차 적용 불가
- **BM25 키워드 검색 보강** [§12-6] — 좁은 분포 토픽의 대안 mechanism. §12-2 불가 판정이 반복되어 **우선순위 유지**
- **Vertex grounded search 운영** — 영어 자료 토픽만 `SKIP_VERTEX_SEARCH=0` [§12-3]
- **`VertexAIEmbeddings` deprecation 모니터링** [§12-4] / **lazy validation 보강** [§12-5]
- **백업 파일 정리** [§12-8] / **`CLEAR_CHROMA_ON_START` 개선** [§12-9] / **ingest 큐레이션 점검** [§12-10]
- (참고) §12-11~13 sub-track 묶음, §12-14~23 대부분 `closed` → 재개 시 원본에서 open 재확인

### 신규 (§ad-track-1 발)
- 🔴 **`published_date` 메타데이터 추가 (catch AY)** — §12-1과 동일 항목. **우선도 상.**
  ⚠️ **누적 인덱스의 선행 조건이다.** §research-1 R2 설계에서 다시 걸린다
- **arm Z 소스 그룹핑 개선 (catch AV)** — 우선도 중. 이월 ⑥과 동일
- **`topics/pet-food-premium.env`에 vertex 시절 `RAG_DISTANCE_THRESHOLD=0.60` 박제** — openai 오버레이로 돌리면 전량 컷. 우선도 하
- **`1982_Holbrook.pdf`가 텍스트 diff 처리**(5,717줄) — `.gitattributes`에 `*.pdf binary` 검토. 우선도 하

### 신규 (§research-1 발)
- **`.gitignore` 차단 잔여** — `api_secrets.txt` 류 접미 변형 · `*.p12` · `*.pfx` · `id_rsa` 계열 미차단.
  현행 차단분은 루트 `.gitignore:21-36`. 우선도 하
- **`research/<slug>/` 구·신 형식 혼재** — R3-2에서 결정 1 스키마(`round-NN.jsonl`)를 적용하면
  기존 `round-01-findings.md` · `round-02-findings.md`(구 형식, 마크다운 자유 서술)와
  **한 디렉터리에 섞인다.** 파서가 무엇을 읽을지·구 형식을 이관할지 폐기할지 착수 시 방침 필요.
  실물 확인(2026-08-05): `research/experiential-marketing-media/` 에 findings 2건 + `state/` 2건.
  우선도 **중**. (출처: §research-1 R3-1 착수 정찰)

## 아카이브
- README-dev.md, README-dev-2.md = 기존 기획서/보고서 에이전트 개선 기록
- README-dev-§14.md = §14 vertex 백엔드 점검·개선 아카이브
