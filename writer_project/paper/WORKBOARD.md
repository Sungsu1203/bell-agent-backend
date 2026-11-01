# WORKBOARD — §paper-writer-2 앞으로 할 일

> 활성 트랙·후보·결정 기록만. **종결된 catch는 여기 아님 → `README-dev-§14.md`(아카이브)로.**
> 운영 상수·규칙(토픽/venv/커밋/vertex)은 `CLAUDE.md`.
> 최종 업데이트: 2026-11-01

---

## 지금 상태 (한 줄)

axis1 = **1.0 PASS** (complete 44 / partial 45 / missing 0). references **89** (OA 60 + SS 29).
**catch 83(faithfulness rank: pool 재설계 P∪{C}·마커 2단 교정·full 근거 재조회) 종결·push `5de31128`.**
rank 작동 확정(표적 [[5]] 240 pct 0.077→full 0.615, 근거길이 병목 인과입증). 아카이브 = `README-dev-paper.md`.
**topic-unify Phase 1(CLI→env `TOPIC_QUERY` 단일 진실, influencer footgun 제거) 종결·push `82257557`.**
catch 86(writer temp=0.3 비결정론 → 렌더 byte 회귀검증 대신 입력 불변 증명) 박제.

---

## 🔒 결정 기록 (재론 금지 — 다음 세션이 되돌리지 말 것)

### ❌ doi 결손 트랙 폐기 확정 (2026-07-11)

- **결정**: doi 결손(약 39건) 복구 트랙 **착수 안 함.** 다음 세션에서 doi R1 재개시 금지.
- **이유**:
  1. axis1 pass_ratio 이미 **1.0 천장**, missing 0 → doi를 채워도 게이트 결과 무변(partial도 이미 통과).
  2. doi 작업은 partial→complete "승격"만 하고 verdict/ratio를 **안 움직임**(순수 내부 비율 이동).
  3. 법학 로리뷰는 **doi 부재가 정상** → 결손 다수가 진짜로 없음(=X, 진짜 커버리지). 없는 데이터 억지 생성.
  4. catch 79 설계 원칙 "**doi 필수 아님(venue OR doi)**"과 정합. doi 필수화는 정상 법학인용 오탈락.
- **부수 조치**: `NEXT_SESSION_20260710_axis1-OA충전-close.md`의 Part B(doi 진입 sketch)도 함께 폐기.

---

## ⭐ 별 트랙 후보 (미착수, 우선순위순)

0. ⭐⭐ **retrieval 품질 — pool 중복·미사용** (구 "인용 다양성/앵커링" 항목 교체, 2026-09-29)
   - ❌ **구 앵커링 진단(자기 pool 인용률 PF·EC 0%) = 무효.** catch 84(인용 마커 형식 불일치 → shift 오매핑)의
     측정 아티팩트. (B-1)·(B-2) 축약 설계 폐기. 근거 = `README-dev-paper.md` catch 84 「파생 1」.
   - ✅ **2026-09-29 재계산(유료 0)**: run_objstab·run_newbase(`archive/*_20260714.md`) 모두 5섹션 자기 pool
     인용률 **100%**, 범위밖 0. 번호(슬롯) 기준 고유 53/48 · 상위5 23/29% · 미사용 40/46% = 7/14 수치 그대로 재현.
   - ⭐ **신규 발견 — 슬롯 기준은 다양성을 부풀린다.** pool 89 슬롯 = **고유 논문 53편**(36 슬롯이 섹션 간
     중복 fetch, 예: Beebe 2005 가 여러 섹션에 각각 들어옴). **논문(제목) 기준** 재계산:
     고유 37/33편 · 상위5 **41/48%** · 미사용 **30/38%**(53편 중). 상위 = Beebe *Search and Persuasion*(10~11회)·
     Tushnet *Gone in Sixty Milliseconds*(7~14회).
   - 다음: (1) 다양성 지표를 **논문 기준**으로 고정할지 결정 (2) 섹션 간 중복 fetch 가 설계 의도인지 확인
     (3) 미사용 30~38% 의 원인 분해(섹션 부적합 seed 등) — research-pipeline 교차참조와 병행.

0-b. **수동 시드 입력 통로 (seed_import)**
   - ✅ **검증 2026-10-17 (CC, 유료 LLM 0)**: 22건 재현 일치(id 중복 0) · 기존 18건 채택 회귀 0 ·
     신규 4건 = Zaichkowsky1994 채택(doi-match) / 육소영2015 **채택**(title-jaccard 1.00 — 한글도 OA 회수됨) /
     Batykov 러시아어 skip(OA 0건) / Batykov 영문 skip.
   - 🔴 **Batykov 영문 skip 원인 = seed 아니라 회수 경로.** OA 원시 rank#1 이 정확히 그 논문인데
     (doi `10.24158/spp.2020.10.3`) `_scholarly_domain.py:146` `extract_domain_from_paper()` 가
     도메인을 못 뽑아 `None` 을 돌리고, 호출처 `openalex.py:193-194` `if not d: continue` 가 **드롭**한다
     → `chunks[0]` 이 다른 논문이 되어 verify 실패. → **0번(retrieval 품질)과 같은 뿌리, 별도 차수.**
     ⚠️ 행번호 정정(2026-10-30): 10-17 기재 `openalex.py:189` 는 틀렸다(`:189` 는 `domains` 선언).
     드롭은 `extract_domain_from_paper` 가 아니라 **호출처**가 한다.
   - CC 수정 4건: 비라틴 제목 오중복 · 미종결 따옴표 무한루프 · LaTeX 이스케이프 잔존 · `@` 위양성.
   - ⚠️ ③ KCI 백엔드의 확인 기준은 **OA 에 없는 국내 논문**으로 재설정 (육소영(2015)은 OA 가 이미
     회수하므로 기준 부적합). V1 에서 후보 선정 실패 → **이월**, 상세는 0-c 말미.

0-c. **논문 검증 파이프라인 V1** — 2026-10-29~11-01 (`CC_PROMPT_20261024` B1~B4 · `CC_PROMPT_20261101` 마감)
   - **B1 정찰(비용 $0.004)**: 5단계 지도 작성. ③ 동일성 검증은 **seed 경로에만** 있고 일반 fan-out
     회수분에는 없다(`web_search.py:2024-2033` 은 쿼리 관련성만 신뢰). ④ 중복 제거는 doi 기준뿐이라
     **doi 없는 chunk 는 중복 검사 자체를 안 받는다**(`web_search.py:2048-2064`).
   - 🔴 **드롭은 설계 의도다** — `scripts/output/§academic-4/step_b_design.md:98`·`:155` 에
     `if not d: continue` 가 명세돼 있다. 그러나 1단계의 `doi.org` 제외(`_scholarly_domain.py:157`)는
     **설계에 없고 구현에서 추가**됐고, 그것이 드롭의 직접 원인이다(catch CS ① — 선언 ≠ 실물).
   - 🔴 **전수 판정(녹화 픽스처 10건)**: 드롭 5건은 **전부** 1단계 skip(landing=doi.org) → 3단계 표 미등록
     → 4단계 venue 미등록 으로 동일 경로 실패. 생존 5건은 **전부 1단계로만** 살았다.
     **catch 59 DOI prefix 표(40개)·venue 표(10개) 기여 = 0.** 드롭 5건 전원 DOI 보유, 생존 중 DOI 보유는 1건.
   - **영향 범위**: `web_search_agent` 학술 fan-out 은 `MODE=academic` 게이트(`web_search.py:877-879`) 라
     **ad 트랙·§research-1 은 무영향**(두 토픽 프리셋 모두 MODE 미설정). 영향 = paper 트랙 +
     §academic-1/-4 측정 드라이버. 같은 드롭이 `semantic_scholar.py:208-209` 에도 있다.
   - **B2 테스트 기반**: `tests/fixtures/seed_import/` **9 파일**(F1~F4 재현 4 · 정상 대조군 1 ·
     사유 코드 2 · 사용자 실데이터 정리본 1 · OA 녹화 응답 1) + `tests/test_seed_import.py` 19건.
     네트워크 차단(sitecustomize) 상태에서 `pytest tests/` **22 passed / 1 xfailed**.
     ⚠️ 기존 `tests/` 는 모듈 레벨 `sys.exit` 때문에 pytest 수집이 INTERNALERROR 로 죽었다 →
     `tests/conftest.py` `collect_ignore` 3건으로 복구(스크립트 파일은 무수정).
   - **B3 검토 목록**: `<out>.review.json` + 사유 코드 11종(ERROR 4 / WARN 6 / INFO 1).
     정상 입력 산출 **22건 회귀 0** 확인.
   - **B4 = 보류 (2026-11-01 결정).** 「AI 연구 시스템 개발」 **정찰 2 의 첫 후보로 이관.**
     권장안 ⒝ = `_scholarly_domain.py` 4단 폴백 **뒤에 5단계 추가**(전부 실패 + DOI 있으면 `doi.org`).
     적용 시 **hydrate 회귀 재측정(≈$0.02, OA 20회) 필수** — 드롭됐던 work 가 되살아나면 `chunks[0]` 이
     바뀌어 기존 seed 의 verify 가 실패할 수 있다(③ 단계가 top-1 하나에만 의존하는 구조의 노출).
     기각 근거 보존: 1단계 조건 삭제안(⒜)은 `10.1016/` DOI 의 publisher 도메인을 `doi.org` 로
     덮어써 회귀한다(합성 대조로 실증). 증거 3종 = 녹화 응답 픽스처 · xfail(strict) · 시뮬레이션.
   - **V1 마감 2026-11-01**: 묶음 (1) B2+B3 커밋. 파이프라인 코드 무수정 유지.
   - ⚠️ **③ KCI 백엔드 = 이월.** 필요성 자체를 정찰 2 에서 재평가한다
     (OA 한국어 색인 3,281,838건 · ko+trademark **405~417건** 확인됨 → KCI 없이도 상당 부분 덮일 가능성).
     V1 에서 기준 논문을 고르지 못한 사유 = 레포가 아는 국내 논문 2편이 **둘 다 OA 에 있어** 대조군이 없었다.

1. **venue 부정합/predatory 판별** — 품질 축. 예: SS Anita(2024) 제목↔저널 불일치
   (상표법 논문인데 venue=`African J of Biological Sci`). 리뷰어가 즉시 잡는 신뢰도 사고 = doi보다 高임팩트.
   존재 판정 아니라 **의미 정합**(제목↔저널 매칭) → embedding/LLM 필요. axis1(존재·결정론·무료) 계약 밖, 규모 큼.
   → 착수 확정 시 별도 축 설계부터.

2. **axis2 word count (IMRD 미달)** — 저비용·결정론 후보. §paper-writer-1서 FAIL 이력.
   프롬프트 튜닝 수준. venue 부정합보다 규모 작음 = 빠른 성과 원하면 여기부터.

3. **deprecated 라이브러리 마이그레이션** — `ChatVertexAI`/`VertexAIEmbeddings`(LangChain 4.0.0 제거예정)
   → `langchain_google_genai`. vertex off 상태라 급하지 않음. 버전 올릴 때 착수(시한폭탄).

4. **paper↔레거시 vertex 게이팅 통합** — paper 경로 flat flag vs 레거시 catch-43 language routing 이원화.
   현재 무해. 통합 필요 시 catch 후보.

5. **topic-unify Phase 2** (Phase 1 종결 후속) — Phase 1(CLI→env `TOPIC_QUERY` 단일 진실) 완결(커밋 `82257557`, push).
   - **Phase 2a** (유료·회귀 트랙): writer `{topic_title}` wart 분리. fetch 는 쿼리형, writer 는 제목형이어야 하나
     현재 한 문자열이 겸함(`measure_paper.py:254` fetch ↔ `:268`→`paper_section_writer.py:81` writer). 분리 시 생성 회귀 위험.
   - **Phase 2b** (유료 트랙): retrieval 개선. Phase 1 은 문자열 통일만(`perception of`→`perceived`). 질의 최적화는
     fetch query 변경 → pool 재생성·검증 필요. catch 86(seed 없는 렌더 byte 대조 금지) 유의.

---

## 🧹 정리 잔무 (무비용, 다음 세션 시작 시 처리)

- [ ] `NEXT_SESSION_20260710_axis1-OA충전-close.md` → archive/삭제 (convention: 일회성).
- [ ] baseline **89**·라인 `:22` 정정이 `CLAUDE.md`·아카이브에 반영됐는지 확인(stale 77 재유입 방지).
- [ ] KCI 커버리지(윤선희 계열): 결손 누적 시에만 별 트랙 재검토. 현재 1건 = 수동 override로 처리 완료, 착수 안 함.
- [ ] `measure_paper.py` abstract-dump hunk(`@@ -505/-513`, `_abs_snip` 3줄) → §citation-claim-faithfulness 트랙으로 분리 커밋. 현재 worktree unstaged 보존(topic-unify Phase 1 커밋서 제외됨).
