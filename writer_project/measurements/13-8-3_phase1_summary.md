# §13-8-3 Phase 1 본 측정 결과 박제 — Sonnet 재측정 + Haiku 본 측정

작성일: 2026-05-12
트랙: §13-8-3 (Anthropic Haiku 4.5 평가)
HEAD 진입: `ba7b304` (commit 2 — gpt-4o/Sonnet 회귀)
본 박제 대상 commit: commit 3 (instrument 추가 + Sonnet baseline 재측정 + Haiku 본 측정)

---

## 1. 트랙 정체성 + 본 측정 진입 경로

### 결합 X+A 채택 (commit 2 §8 박제 결정)
- **X**: Sonnet baseline 재측정 + Haiku 본 측정 (gpt-4o 는 commit 2 회귀 1 point 인용)
- **A**: 현 `latest.md` (Sonnet 풍부성 산출물) 그대로 input 통일

### per-run-timeout 권고 산식 (catch 26 sub-section)
- 원칙: `max(300, baseline_mean × 1.5) with 50% 최소 마진`
- Sonnet: **420s** (1차 300s 마진 부족 → 재측정 420s 통과)
- Haiku: **240s** (진단 max 102s × 2.35×, 안전 마진 충분)

---

## 2. Instrument 추가 (catch 26 — 측정 도구 LLM 0 + 표준 라이브러리)

### 변경 범위
- **`agent/export/spec.py`** (+12 줄): module-level `_INSTRUMENT` dict + validator counter
  ```python
  _INSTRUMENT = {
      "bullets_null_count": 0,
      "bullets_total_count": 0,
  }
  ```
  - validator 안에서 `total += 1` 항상, null 시 `null += 1 + return []`
- **`scripts/measure_stability.py`** (+40 줄): run loop reset + 회수 + metrics_7 박제 + 콘솔 보고
  - 매 run 시작 시 `_INSTRUMENT` reset (run granularity)
  - timeout/fail 케이스도 entry 에 부분 카운트 박제 (race 인정)
  - `metrics_7["bullets_null_distribution"]` 총계 + per-run 분포

### Sanity check 결과 (Pydantic 2.12.3)
| Case | input | s.bullets | null | total | 결과 |
|---|---|---|---|---|---|
| 1 | `bullets=None` | `[]` | 1 | 1 | ✅ |
| 2 | `bullets=['a','b']` | `['a','b']` | 0 | 1 | ✅ |
| 3 | `bullets` omit | `[]` | 0 | 0 | **사각지대** (default_factory, validator 미호출) |

**한계 박제**: omit 케이스 미추적 — Pydantic 2.x default_factory 동작 (validator `mode="before"` 도 input 키 부재 시 호출 안 됨). Haiku 진단 자산 (9건 input_repr="None") 기준 실제 발생 빈도 매우 낮음.

---

## 3. Sonnet 4.6 baseline 재측정 — 2단계 진행

### 3-1. 1차 시도 — 300s timeout (분기 b 차단 조건 발동)

| run | 상태 | latency | slides | bullets(null/total) |
|---|---|---|---|---|
| warmup 1 | FAIL (Timeout) | — | — | — |
| warmup 2 | OK | 299.8s | — | — |
| run 1 | OK | 285.4s | 53 | 0/53 |
| run 2 | TIMEOUT | >300s | — | — |
| run 3 | OK | 281.7s | 49 | 0/49 |
| run 4 | TIMEOUT | >300s | — | — |
| run 5 | TIMEOUT | >300s | — | — |

- **ok_runs: 2/5** → 차단 조건 (ok=False 2~4건 → 5 runs 중단, timeout 상향 결정 요청) 발동
- 측정 도구는 자동 중단 미구현 → 5 runs 끝까지 진행됨
- raw: `logs/stability_venfobel-vitamin_claudesonnet46_20260512_141447.json`

### 3-2. 2차 시도 — 420s timeout (통과)

| run | 상태 | latency | slides | tables | tokens(in/out) | bullets(null/total) |
|---|---|---|---|---|---|---|
| warmup 1 | OK | 343.7s | — | — | — | — |
| warmup 2 | OK | 335.0s | — | — | — | — |
| run 1 | OK | 338.5s | 56 | 18 | 36,001 / 21,720 | 0/56 |
| run 2 | OK | 299.1s | 54 | 18 | 36,001 / 22,419 | 0/54 |
| run 3 | OK | 299.7s | 54 | 18 | 36,001 / 21,969 | 0/54 |
| run 4 | OK | 299.7s | 55 | 18 | 36,001 / 21,898 | 0/55 |
| run 5 | OK | 348.0s | 55 | 18 | 36,001 / 22,645 | 0/55 |

- **ok_runs: 5/5** ✅
- raw: `logs/stability_venfobel-vitamin_claudesonnet46_20260512_151501.json`

### 3-3. Sonnet baseline 갱신 (5-10 baseline 대체)

| 항목 | 5-10 baseline (gpt-4o 산출물 input) | 5-12 본 측정 (Sonnet 산출물 input) | 변화 |
|---|---|---|---|
| latency mean | 192~200s | **317.0s** | +59% |
| latency CV | n/a | **6.8%** | 결정성 매우 높음 |
| output_tokens mean | 12,875 | **22,130** | +72% |
| output_tokens CV | n/a | **1.6%** | 결정성 매우 높음 |
| slide_count mean | 37 | **54.8** | +48% |
| slide_count spread | n/a | **2** (≤2 통과) | 결정성 매우 높음 |
| bullets null | 미상 (instrument 전) | **0/274 (0.0%)** | null 빈도 0 |
| cost per_run | ~$0.25 | **$0.44** | +76% |

**input cascade 양상 정량 박제**: input 변경 (gpt-4o → Sonnet 풍부성 산출물) 이 모든 지표에서 50~75% 증가.

---

## 4. Haiku 4.5 본 측정 결과

| run | 상태 | latency | slides | tables | tokens(in/out) | bullets(null/total) |
|---|---|---|---|---|---|---|
| warmup 1 | OK | 174.3s | — | — | — | — |
| warmup 2 | OK | 210.9s | — | — | — | — |
| run 1 | OK | 153.4s | 70 | 18 | 37,717 / 19,514 | 0/43 |
| run 2 | OK | 129.7s | 69 | 19 | 37,717 / 16,515 | 0/38 |
| run 3 | OK | 121.1s | 64 | 17 | 37,717 / 14,928 | 0/35 |
| run 4 | OK | 152.6s | **80** | 19 | 37,717 / 19,523 | 0/48 |
| run 5 | OK | 142.3s | 66 | 17 | 37,717 / 16,942 | 0/40 |

- **ok_runs: 5/5**, ValidationError **0건**, bullets null **0/204 (0.0%)**
- latency mean **139.85s**, std 12.69, CV 9.1%
- output_tokens mean 17,484, CV 10.2%
- slide_count [70, 69, 64, **80**, 66] — spread **16**, run 4 outlier
- cost per_run **$0.1251**, total **$0.6257**
- raw: `logs/stability_venfobel-vitamin_claudehaiku4520251001_20260512_154554.json`

---

## 5. Triple Track 비교 표

| provider | latency mean | CV | output_tok mean (CV) | slide_count mean (spread) | cost per_run | bullets null | ValidationError |
|---|---|---|---|---|---|---|---|
| gpt-4o (1 point, commit 2) | 172.1s | n/a | 5,470 (n/a) | 54 (n/a) | $0.1173 | 미상 (instrument 전) | 0 |
| Sonnet 4.6 (n=5) | **317.0s** | **6.8%** | 22,130 (**1.6%**) | 54.8 (**2**) | $0.44 | 0/274 | 0 |
| Haiku 4.5 (n=5) | **139.85s** | **9.1%** | 17,484 (**10.2%**) | 69.8 (**16**) | **$0.1251** | 0/204 | 0 |

### Haiku 슬롯 정체성 — "초저지연 / 초저비용 / 풍부한 output (결정성 trade-off)"

- **latency**: Sonnet 의 **44%**, gpt-4o 의 **81%** → 초저지연 ✅
- **cost**: Sonnet 의 **28%** (3.5× 저렴), gpt-4o 보다도 7% 저렴 → 초저비용 ✅
- **output 풍부**: Sonnet output_tokens 의 **79%**, gpt-4o 의 **3.2×** → 풍부한 단건
- **결정성 trade-off**: slide_count spread 16 (Sonnet 2 대비 **8×**), output_tokens CV 10.2% (Sonnet 1.6% 대비 **6×**) → catch 17 강력한 실증

### Triple track 운영 가능성 — 자격 확정 ✅

- **gpt-4o**: 표준 4-블록, 안정, 운영 default (operational baseline)
- **Sonnet 4.6**: 자율 구조, 풍부성 + 결정성 (CV 1.6% / spread 2), high-stakes 단건 reproducible
- **Haiku 4.5**: 초저지연 / 초저비용 / 풍부한 output (결정성 trade-off, stochastic 변동 인정 가능 시)

---

## 6. cost 검증 (단가 valid)

| provider | input × in_rate | output × out_rate | sum (계산) | 측정 per_run | 정합 |
|---|---|---|---|---|---|
| gpt-4o | 25,045 × $2.5/M = $0.0626 | 5,470 × $10/M = $0.0547 | $0.1173 | $0.1173 | ✅ |
| Sonnet 4.6 | 36,001 × $3/M = $0.1080 | 22,130 × $15/M = $0.3320 | $0.4400 | $0.44 | ✅ |
| Haiku 4.5 | 37,717 × $1/M = $0.0377 | 17,484 × $5/M = $0.0874 | $0.1251 | $0.1251 | ✅ |

`measure_stability.py:317-333` 의 `_PRICE` dict + prefix-matching 로직 정상 동작 확인. Phase 3 박제 시 인용 가능.

### Haiku 의 의외 발견 — cost = gpt-4o 와 거의 동일하지만 output 3× 풍부

- Haiku cost $0.1251 vs gpt-4o cost $0.1173 → 차이 **$0.0078 만** (Haiku 가 6.6% 더 비쌈)
- 그러나 Haiku output_tokens (17,484) 는 gpt-4o output_tokens (5,470) 의 **3.2×** 풍부
- **per output_token 단가**: Haiku $0.00716 / Ktok vs gpt-4o $0.02144 / Ktok → Haiku 가 **3× 저렴**
- 정밀화: **"Haiku = 풍부한 output 의 초저비용 provider"** (단순 cost 비교가 아닌 per-token-density 관점)

---

## 7. catch 자산 후보 박제

### catch 22 정밀화 — "provider × input 의 함수"

**원래 가설**: multi-provider 정규화 (validator) 의 보험 가치 = Haiku 의 null 응답 흡수

**본 측정 실증**:
- Sonnet null 빈도: **0/274 (0.0%)**
- Haiku null 빈도: **0/204 (0.0%)**
- 양 provider 모두 null 응답 안 함 → **정량 실증 가치 약함**

**진단 측정과의 차이 원인 평가** (Haiku 5-10 진단 9 ValidationError → 5-12 본 측정 0):
| 원인 | 가능성 | 근거 |
|---|---|---|
| (A) schema fix 효과 | ~**5%** | instrument 카운트 0 = null 입력 자체 없었음 확정. validator 변환 호출 안 됨 |
| (B) Haiku stochasticity | ~**30%** | 모델 응답 양상 변동 (CV 9.1%, slide_count spread 16) |
| (C) input 차이 (-2.1%) | ~**40%** | latest.md 갱신 (5-11) 으로 진단 input ≠ 본 측정 input. catch 22 의 "input 의존성" 직접 실증 |
| (D) server-side 모델 업데이트 | ~**25%** | model ID 동일하나 5-10 → 5-12 사이 행동 변경 가능성 |

**catch 22 정밀화**: **"multi-provider 정규화는 보험 자산, 정량 실증은 input 의존"**
- 보험 가치는 유효 (진단 시점 9건 ValidationError 실재)
- 정량 실증은 input 변경 시 사라질 수 있음 (input × provider × time 함수)

### catch 17 sub-case — "모델 크기 vs 결정성 inverse correlation"

| 지표 | Sonnet 4.6 | Haiku 4.5 | 배수 |
|---|---|---|---|
| slide_count spread | 2 | **16** | **8×** |
| output_tokens CV | 1.6% | **10.2%** | **6×** |
| latency CV | 6.8% | 9.1% | 1.3× |

**일반화**: "provider 결정성 = 모델 capacity 의 함수" — 작은 모델 (Haiku) 일수록 stochastic 변동 큼.

**outlier 영향 박제**:
- Haiku run 4 slide_count=80 이 spread 16 의 주 원인 (run 4 제외 시 spread = 70-64 = 6)
- n=5 의 outlier 빈도 박제 한계 명시: 1/5 outlier 시 spread 8× 차이 — 더 큰 n (예: n=20) 측정 시 분포 정밀화 가능

### Sonnet self-cascade pattern (catch 후보 — Phase 3 박제 시 확정)

- 1차 시도 (300s) ok_runs latency: run 1=285.4s, run 3=281.7s (CV 0.66%)
- 2차 시도 (420s) ok_runs latency: 5 runs 분포 [338, 299, 299, 299, 348] — **bi-modal**:
  - "느림" 군집: 338.5s, 348.0s (warmup + run 1, 5)
  - "빠름" 군집: 299.1s, 299.7s, 299.7s (run 2, 3, 4)
- output_tokens 변동 무관 (CV 1.6%)
- 가설: warmup → 본 측정 boundary 에서 connection pool 또는 server-side 상태 변동
- Phase 3 박제 시 catch 17 sub-case 또는 별도 catch 후보

### Haiku ValidationError 변동 catch 후보 — (catch 27 후보)

- "동일 model ID 의 행동 변동 (5-10 → 5-12, 1.5일 간격)"
- 원인 A/B/C/D 의 결합 (특히 C+B)
- 측정 재현성 한계 박제 — provider 측정은 input + time 의존
- 일반화: "LLM 측정 박제는 input 고정 + 측정 시점 명시 필수"

---

## 8. measure_stability.py 측정 도구 한계 박제

### 한계 1 — 차단 조건 자동 중단 로직 없음
- 사용자 박제 정책 (ok=False 2~4건 → 5 runs 중단) 측정 도구 미구현
- 본 측정에서 Sonnet 1차 시도 시 5 runs 끝까지 진행됨 (수동 사용자 보고 후 재측정)
- **catch 27 후보**: 측정 도구의 차단 조건 자동 구현 — 본 phase 외 별도 트랙

### 한계 2 — background 실행 시 실시간 watch list 보고 불가
- run 1 latency > 250s 시 즉시 보고 정책 미충족 (background 종료 후 일괄 보고)
- 대안: Monitor stream 도구 사용 또는 측정 도구에 watch hook 추가

### 한계 3 — ThreadPoolExecutor 비취소 race
- timeout 발동 시 background 호출 cancel 불가, 다음 run 의 instrument 카운트 오염 가능
- 본 측정에서는 race 발생 안 함 (timeout 0건)
- 대안: ProcessPoolExecutor 또는 multiprocessing 사용 (별도 트랙)

### 한계 4 — bullets omit 사각지대 (Pydantic default_factory)
- `{}` (필드 자체 omit) 응답 시 instrument 미추적
- Haiku 진단 자산 (9건 input_repr="None") 기준 실제 발생 빈도 낮음
- 측정 도구 확장은 본 phase 외 (omit 사후 식별은 deck 검사로 가능)

---

## 9. warmup latency 양상 (부수 검토)

| provider | warmup 1 | warmup 2 | 본 측정 mean | 차이 |
|---|---|---|---|---|
| Sonnet 4.6 | 343.7s | 335.0s | 317.0s | warmup +7~8% |
| Haiku 4.5 | **174.3s** | **210.9s** | 139.85s | warmup **+25~51%** |

- Haiku warmup latency (174~211s) > 본 측정 (121~153s) — **+50%**
- cold start 단독으로 설명 부족 (Sonnet 은 7~8% 만 증가)
- 가설:
  - (i) Anthropic SDK 의 connection pool 초기 latency
  - (ii) Haiku 의 작은 모델 capacity 가 cold path 영향 더 큼
  - (iii) warmup md (latest.md) 의 stochastic 변동
- **Phase 3 박제 시 catch 후보 추가 검토**: warmup latency = (provider × cold path × model capacity) 의 함수

---

## 10. Phase 2 진입 전 결정 사항 박제

### 결정 1 — e2e PPTX export 의 sections/latest.md provider mismatch 영향
- 현 상태: sections (gpt-4o 복원) vs latest.md (Sonnet 풍부성 산출물) provider mismatch
- Phase 2 의 PPTX export 가 어느 파일 읽는지 코드 확인 필요 (`bell.export.pptx` 또는 동등 모듈)
- 결정 분기: sections-only / latest.md-only / 둘 다 / 결합 로직

### 결정 2 — Haiku 측정 deck 의 Phase 2 활용 가능성
- 본 측정에서 Haiku 5 runs deck 생성됨 (plan_deck 결과)
- 그러나 deck 자체는 measure_stability.py 가 저장 안 함 (통계만)
- Phase 2 의 e2e 보고서 생성은 별도 측정 필요
- 또는 측정 도구 확장 — deck 도 저장 (별도 트랙)

### 결정 3 — Phase 2 sections 생성 시 provider 결정
- 옵션 a: gpt-4o (현 sections 복원 상태 유지)
- 옵션 b: Sonnet 4.6 (sections 도 풍부성 적용)
- 옵션 c: Haiku 4.5 (저비용 운영 검증)
- 옵션 d: triple track 비교 — 세 provider 모두 sections 생성 (비용 ~$2, 시간 ~1시간)

Phase 3 박제 시 사용자 결정.

---

## 11. 본 measurement 자산 정리

### tracked (commit 3 staging 대상)
- `agent/export/spec.py` (instrument 추가, +12 줄)
- `scripts/measure_stability.py` (instrument 통합 + 콘솔 박제, +40 줄)
- `writer_project/measurements/13-8-3_phase1_summary.md` (본 박제 파일)

### untracked (재현 불가능, logs/ 박제만)
- `logs/stability_venfobel-vitamin_claudesonnet46_20260512_141447.json` (Sonnet 1차 300s, ok 2/5)
- `logs/stability_venfobel-vitamin_claudesonnet46_20260512_151501.json` (Sonnet 2차 420s, ok 5/5)
- `logs/stability_venfobel-vitamin_claudehaiku4520251001_20260512_154554.json` (Haiku n=5, ok 5/5)

---

## 12. 다음 단계 (commit 3 완료 후)

- **Phase 2 진입 결정** — 사용자 결정 분기 (§10 의 결정 1·2·3)
- **README-dev-2.md §13-8-3 박제** — Phase 3 (Claude 웹 주도) 진입 시
  - Sonnet baseline 갱신 (5-12 input cascade 양상)
  - catch 22 정밀화 (provider × input × time)
  - catch 17 sub-case (모델 크기 vs 결정성)
  - Sonnet self-cascade pattern
  - Haiku ValidationError 변동 (catch 27 후보)
  - measure_stability.py 한계 4건
  - warmup latency 양상 (catch 후보)
- **사용자 메모리 박제 갱신** — Phase 3 진입 시:
  - Sonnet 4.6 baseline (5-12 input cascade)
  - per-run-timeout 산식 정밀화 (`max(300, mean × 1.5) with 50% 최소 마진`)
  - LLM 측정 박제 원칙: input 고정 + 측정 시점 명시 필수
