# WORKBOARD — §paper-writer-2 앞으로 할 일

> 활성 트랙·후보·결정 기록만. **종결된 catch는 여기 아님 → `README-dev-§14.md`(아카이브)로.**
> 운영 상수·규칙(토픽/venv/커밋/vertex)은 `CLAUDE.md`.
> 최종 업데이트: 2026-07-11

---

## 지금 상태 (한 줄)

axis1 = **1.0 PASS** (complete 44 / partial 45 / missing 0). references **89** (OA 60 + SS 29).
catch 82(OA venue 단일경로 드롭 → locations[] fallback)까지 종결. 아카이브 = `README-dev-§14.md`.

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
