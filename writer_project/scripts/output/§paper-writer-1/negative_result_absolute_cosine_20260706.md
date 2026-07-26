# Negative Result — 절대 코사인 기반 citation-claim faithfulness 측정 (2026-07-06)

**트랙**: §citation-claim-faithfulness / R2-T3
**결론 한 줄**: 문장↔인용abstract **절대 코사인 임계**는 이 corpus에서 mismatch 거름망으로
**부적합**(도메인 포화). 단 R1 판정 B(grounding 약)는 **정량 확증**됨.

---

## 측정 개요
- 대상: draft `...20260706_004833.md`의 `[[N]]` 인용 문장 ↔ 인용된 chunk abstract(240자 절단).
- valid 페어 43건(1≤N≤89 + abstract 존재). no_abstract 6 / out_of_range 3 제외.
- 임베딩: **e5-large**(로컬, 무료). BGE-m3는 x86 Mac(torch 2.2.2<2.6, CVE 가드) + HF safetensors
  부재로 로드 불가 → 지시서 폴백 e5-large 채택. (rank 축은 절대 임베딩 품질에 덜 민감 → 재시도 불요.)
- 2 variant: A_symmetric(프리픽스 무), B_asymmetric(query:/passage: 프리픽스).

## 분포 (A_symmetric, n=43)
| min | q25 | median | mean | q75 | max |
|-----|-----|--------|------|-----|-----|
|0.722|0.765| 0.794 |0.802|0.830|0.936|

- 전 페어가 **0.72–0.94**에 압축. B_asymmetric은 0.694–0.890(전반 ~0.03↓)이나 변별력 개선 없음.
- 원인: 본문 문장·abstract가 **전부 상표법/소비자혼동 동일 도메인·동일 언어** → 임베딩 유사도
  바닥이 ~0.72로 상승(도메인 포화). 절대 임계로 mismatch를 분리할 여지 소멸.

## 왜 절대 임계가 실패하나 (핵심 증거)
1. **Beebe [[58]] = 0.797 = 53%tile(중앙/median)**. mismatch 표적이 하위 꼬리가 아님 →
   절대 코사인이 못 잡음.
2. **하위 꼬리 = false positive**: 최저 [[25]] *Gone in Sixty Milliseconds*(cos 0.743) ↔
   "소비자가 시각정보를 밀리초 단위로 처리" = **정합 양호한데 최하위**. 임계 하향 시 오탐.
3. **분리 가능한 단일 임계 부재**: Beebe 잡으려 ≥0.80이면 전체 ~50% 플래그(오탐 홍수),
   꼬리(~0.74)면 양호 인용 잡고 Beebe 놓침.

## 그러나 — R1 판정 B는 정량 확증됨 (버리지 않는 이유)
같은 논문 **Beebe(Search and Persuasion)** 인용이 문장별로 **0.775~0.936 산포**:
- [[2]] "trademark law posits that the consumer's perception is the ultimate..." = **0.936**
  (abstract 논지 "the consumer is the measure of all things" 복창 → 최상위).
- [[58]] "consumers often rely on visual cues for rapid identification..." = **0.797**(느슨).

→ 한 논문이 논지 그대로 인용된 곳과 느슨히 붙은 곳으로 **논문 내부에서 갈림** = 인용이
warrant 아닌 **decoration**임을 정량 확인. (측정 도구로서 절대 코사인은 실패했지만, 현상 자체는
포착.)

## 방법론적 함의 (논문 limitation 후보)
- 도메인 동질 corpus에서 임베딩 절대 유사도는 공통 오프셋에 confound됨.
- 전환: **rank(상대/대조)** — 인용된 abstract가 그 섹션 후보 pool에서 몇 등인가 → 공통 오프셋
  상쇄. (R2 연장 T5에서 배선.)

## 산출물
- `cosine_distribution.json` — 2 variant describe + per_pair 코사인(A_symmetric 오름차).
- 스크립트: `scripts/§paper-writer-1/emb_cosine.py`.

## Re-entry 조건
- 절대 코사인으로 회귀하지 말 것. 도메인 포화가 해소되는 이질 corpus(예: 다분야 리뷰)에서만
  절대 임계 재검토 여지. 동일 도메인 논문 생성에는 rank 축을 표준으로.
