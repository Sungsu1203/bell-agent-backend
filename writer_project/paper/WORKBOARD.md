# WORKBOARD — §paper-writer-2 앞으로 할 일

> 활성 트랙·후보·결정 기록만. **종결된 catch는 여기 아님 → `README-dev-§14.md`(아카이브)로.**
> 운영 상수·규칙(토픽/venv/커밋/vertex)은 `CLAUDE.md`.
> 최종 업데이트: 2026-09-29

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
     (doi `10.24158/spp.2020.10.3`) `openalex.py:189` `extract_domain_from_paper()` 가 DOI prefix 를
     도메인으로 못 바꿔 드롭 → `chunks[0]` 이 다른 논문이 되어 verify 실패. 같은 쿼리 10건 중 **4건 드롭,
     전부 DOI 보유분**. 생존 6건은 전부 DOI 없는 리포지터리 사본. → **0번(retrieval 품질)과 같은 뿌리, 별도 차수.**
   - CC 수정 4건: 비라틴 제목 오중복 · 미종결 따옴표 무한루프 · LaTeX 이스케이프 잔존 · `@` 위양성.
   - ⚠️ ③ KCI 백엔드의 확인 기준은 **OA 에 없는 국내 논문**으로 재설정 (V1 정찰에서 후보 선정,
     육소영(2015)은 OA 가 이미 회수하므로 기준 부적합)

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
