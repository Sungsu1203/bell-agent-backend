# WORKBOARD — §paper-writer-2 앞으로 할 일

> 활성 트랙·후보·결정 기록만. **종결된 catch는 여기 아님 → `README-dev-§14.md`(아카이브)로.**
> 운영 상수·규칙(토픽/venv/커밋/vertex)은 `CLAUDE.md`.
> 최종 업데이트: 2026-07-12

---

## 지금 상태 (한 줄)

axis1 = **1.0 PASS** (complete 44 / partial 45 / missing 0). references **89** (OA 60 + SS 29).
**catch 83(faithfulness rank: pool 재설계 P∪{C}·마커 2단 교정·full 근거 재조회) 종결·push `5de31128`.**
rank 작동 확정(표적 [[5]] 240 pct 0.077→full 0.615, 근거길이 병목 인과입증). 아카이브 = `README-dev-paper.md`.

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

0. ⭐⭐ **인용 다양성 / writer 편중** (catch 83 분산도 실측으로 데이터 확보 — **최우선**)
   - **실측**: 최신 논문 58 인용 → 고유 **15논문**(fetch된 53 중 15만 사용, 38 미사용). 상위5=**67%**, 상위1([[11]])=11회.
   - ★**Beebe 오조준 박제**: 원래 의심 [[2]] Beebe(8회)는 **3위일 뿐**. [[11]]11회·[[14]]10회가 더 심함.
     개별 인용 왜곡(faithfulness)이 아니라 **소수 총론 의존 패턴**이 상위 문제 = **축이 다르다**(rank/LLM 정합축 오조준).
   - **원인 3분기 값싼 확인(유료 0)**:
     · **(b) 주입 배선 = 반증** — writer가 pool 전체 봄. top-k 절단 없음(`paper_section_writer.py:48` 전체순회,
       `measure_paper.py:272 references_chunks=chunks` 무슬라이스, 섹션당 15~20개 전부 주입).
     · **(a) writer 선택편향 = 유력** — 미사용 38개 다수 주제적합: RD에 survey evidence 3개([[67]][[69]][[72]]) 안 씀,
       TB dilution 논문 다수 안 씀. writer가 섹션특화보다 소수 범용총론([[11]][[14]][[2]]) 반복 선호.
     · **(c) retrieval/seed 노이즈 = 부분** — PF의 seed 주입 NLP논문(SBERT/LaBSE/STS [[37][38][39][54]])은 법학본문 부적합.
   - ⭐**원인 확정 = 앵커링**(240자 가설 기각): 섹션별 자기 pool 인용률 **Intro 100%·TB 7%·PF 0%·RD 33%·EC 0%**
     = 뒤 섹션이 자기 pool 무시하고 앞(Intro) 논문 재소환. 58 인용 중 55개(95%)가 N≤14. 240자 가설은
     abstract empty인 [[14]]10회·[[1]]4회 상위인용이 반증(writer는 초록 없이도 재인용).
     기제 = `previous_sections` 누적 주입(`measure_paper.py:242/273/278`) + `prompts.py:453` "앞 주장 유지" 지시 +
     `:470` 자기 pool 활용 지시 **부재(비대칭)**. `paper_section_writer.py:64`가 `[[N]]`만 strip, prose(용례·주장)는 유지.
     = **catch 81 계보(번호는 막고 용례는 못 막음 = 또 절반만 고침).**
   - **처방 방향(R3, 유료 dry 대기)**: `:453` "빼기" 금지(논지 일관성 필수) → **"구분해주기"**(주장 이어라 + 근거는 이 섹션 pool).
     `:470` references 우선활용 짝 맞춤(catch 81 교훈: 한쪽만 손대면 부작용). 표적2(Beebe 총론성)는 여기 흡수.
     부작용 관측 필수: 다양성 / 논지 일관성 회귀 / 마커 표기 회귀 / 인용 총량 / axis1·3.

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

---

## 🧹 정리 잔무 (무비용, 다음 세션 시작 시 처리)

- [ ] `NEXT_SESSION_20260710_axis1-OA충전-close.md` → archive/삭제 (convention: 일회성).
- [ ] baseline **89**·라인 `:22` 정정이 `CLAUDE.md`·아카이브에 반영됐는지 확인(stale 77 재유입 방지).
- [ ] KCI 커버리지(윤선희 계열): 결손 누적 시에만 별 트랙 재검토. 현재 1건 = 수동 override로 처리 완료, 착수 안 함.
