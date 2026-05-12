# README-dev (cont.) — §13-14-2 트랙 close 이후

## 이전 README-dev.md 와의 관계

본 파일은 `README-dev.md` 분량 임계 도달로 분리 운영된 후속 박제 파일.

- `README-dev.md` = §13-14-2 트랙 close (commit `612cc87`) 까지의 박제 자산 (~3296 줄)
- `README-dev-2.md` (본 파일) = `612cc87` 이후 신규 박제 자산
- cross-reference: `README-dev.md` 상단의 *트랙·catch 박제 인덱스* + 본문 catch 17·20·21·22·24·25·26 + §13-14 트랙 본문 참조

---

## 분리 운영 cut-off 시점

- HEAD (분리 직전) = `612cc87` (§13-14-2 트랙 close)
- 분리 commit hash = `08edfd7` (본 파일 신규 commit)
- 다음 박제 진입 시점 = 신규 트랙 (§13-8-3 Haiku 4.5 평가 또는 사용자 결정 다른 트랙)

---

## 트랙·catch 인덱스 (본 파일)

(이후 박제 진행 시 본 파일 안의 트랙·catch 위치 인덱스 추가 예정)

---

## 환경 상태 (분리 시점)

- `LLM_PROVIDER=anthropic`
- `ANTHROPIC_MODEL=claude-sonnet-4-6`
- `ANTHROPIC_REQUEST_TIMEOUT=600`
- `sections/venfobel-vitamin/` = gpt-4o 복원 상태
- Sonnet R3 backup = `reports/venfobel-vitamin/_sections_sonnet_R3_backup/` (1 명령 복원 가능)

---

## 다음 트랙 후보

- **(권고 1순위) §13-8-3** — Anthropic Haiku 4.5 평가 — dual track cost/latency trade-off 세분화, triple track 가능성
- **(권고 2순위) 다른 토픽 일반화 검증** — pet-food-premium / height-growth-supplement 등 (provider-agnostic + topic-agnostic 양상 확장)
- **(권고 3순위) §13-14-α-sonnet R2 prompt 패치** — Sonnet 4.6 의 §2 systematic 누락 양상 분석

---

## (이후 박제 진행 영역)

신규 트랙 진입 시 본 영역에 박제 시작.

# §13-8-3 Phase 3 박제 — Triple Track 정량 + catch 12건 정밀화

박제 일자: 2026-05-12
직전 commit: `5e6536b` (branch `feature/pptx-multi-llm`, origin push 완료)
박제 source: 본 세션 Claude 웹 단독 산출 (Step 1~7 사용자 확정)

---

## §13-8-3-A — Triple Track 정량 비교 (2026-05-12 본 측정)

### 측정 조건
- topic: venfobel-vitamin (3-section input, gpt-4o sections 기준)
- runs: n=5 each (gpt-4o 는 회귀 1 point)
- max_retries=0, warmup 2 runs, inter-run sleep 60s
- per-run timeout: Sonnet 420s (1차 300s 실패 후 상향), Haiku 240s (1차 통과)
- measurement script: `scripts/measure_stability.py` (instrument 통합, commit `5e6536b`)
- schema fix: SlideSpec.bullets None→[] before-validator (commit `7713426`)

### Triple Track 비교 표

| 지표 | gpt-4o (1 point) | Sonnet 4.6 (n=5) | Haiku 4.5 (n=5) | Haiku/Sonnet | Haiku/gpt-4o |
|---|---|---|---|---|---|
| **latency mean** | 172.1s | 317.0s | 139.85s | 44% | 81% |
| **latency CV** | n/a | 6.8% | 9.1% | 1.34× | n/a |
| **slide_count mean** | 54 | 54.8 | 69.8 | 1.27× | 1.29× |
| **slide_count spread** | n/a | 2 | 16 | **8×** | n/a |
| **output_tokens mean** | ~6,400 (추정) | ~13,200 | ~10,400 | 79% | 1.63× |
| **output_tokens CV** | n/a | 1.6% | 10.2% | **6.4×** | n/a |
| **cost per run** | $0.1173 | $0.44 | $0.1251 | 28% | 107% |
| **per output_token 단가** | $0.02144/Ktok | $0.0333/Ktok | $0.00716/Ktok | 22% | 33% |
| **bullets null count** | 미상 | 0/274 | 0/204 | — | — |
| **ValidationError** | 0 | 0 | 0 | — | — |

### 핵심 발견 4건

1. **Haiku 초저지연 확인** — Sonnet 의 44% 수준 (317s → 139.85s). gpt-4o 대비도 81% 로 가장 빠름.
2. **Haiku 초저비용 + 풍부 output 결합** — per run cost 는 gpt-4o 와 동일 ($0.0078 차이) 하지만 output_tokens 는 1.63× 풍부. per output_token 단가 기준 gpt-4o 의 33%, Sonnet 의 22% — 풍부한 output 산출 trip 의 최저비용 provider.
3. **결정성 trade-off 정량화** — slide_count spread 8×, output_tokens CV 6.4× (Sonnet 대비). 모델 capacity 와 결정성의 inverse correlation 패턴 (catch 17 sub-case).
4. **Schema fix 보험 가치 유효** — 진단 측정 (5-10) 9건 ValidationError → 본 측정 (5-12) 0건. 단 catch 22 정밀화 필요 (보험 자산 vs input × provider × time 의존 분리).

### Triple Track 슬롯 정체성 (요약)

| provider | 슬롯 정체성 | 주 용도 후보 |
|---|---|---|
| **gpt-4o** | 균형형 (운영 default, §13-7-4) | 표준 운영 |
| **Sonnet 4.6** | 고결정성 + 풍부 output, 고지연/고비용 | 결정성 critical batch 트랙 |
| **Haiku 4.5** | 초저지연 + 초저비용 + 풍부 output, 결정성 trade-off | 저비용 대량 처리, 결정성 비critical 트랙 |

### Sonnet 4.6 baseline 갱신 (5-10 → 5-12)

| 지표 | 5-10 (gpt-4o input) | 5-12 (Sonnet self-cascade input) | 변동 |
|---|---|---|---|
| latency mean | 199.4s | 317.0s | +59% |
| output_tokens mean | ~7,680 | ~13,200 | +72% |
| slide_count mean | 37 | 54.8 | +48% |
| cost per run | $0.25 | $0.44 | +76% |

→ input cascade 양상 박제. 측정 baseline 은 input × provider × time 의 함수 (catch 11 input cascade 일반화로 별도 박제).

### Log 자산 (untracked, 재현 불가능)
- `logs/stability_venfobel-vitamin_gpt4o_20260512_102240.json` (gpt-4o 회귀)
- `logs/stability_venfobel-vitamin_claudesonnet46_20260512_141447.json` (Sonnet 1차 300s, ok 2/5)
- `logs/stability_venfobel-vitamin_claudesonnet46_20260512_151501.json` (Sonnet 2차 420s, ok 5/5)
- `logs/stability_venfobel-vitamin_claudehaiku4520251001_20260512_154554.json` (Haiku ok 5/5)

---

## §13-8-3-B — Haiku 4.5 슬롯 정체성 정밀화

### 4축 정체성

#### 축 1 — 초저지연
- Haiku mean latency = 139.85s
- Sonnet 대비 44% (177s 단축), gpt-4o 대비 81% (32s 단축)
- Anthropic provider 내부 비교: Sonnet 의 2.27× 빠름
- 시사점: 대량 batch 처리 또는 사용자 대기 시간 critical 트랙에서 Anthropic provider 선택지 확보

#### 축 2 — 초저비용
- Haiku per run cost = $0.1251
- Sonnet 대비 28% ($0.31 절감, 3.52× 저렴), gpt-4o 대비 107% ($0.0078 추가)
- gpt-4o 와 cost parity 수준 — Anthropic provider 가 가격 경쟁력 확보한 첫 슬롯

#### 축 3 — 풍부 output
- Haiku output_tokens mean ≈ 10,400 (Sonnet 의 79%, gpt-4o 의 1.63×)
- slide_count mean 69.8 (Sonnet 54.8 대비 1.27×, gpt-4o 54 대비 1.29×)
- per output_token 단가 = $0.00716/Ktok
  - gpt-4o ($0.02144/Ktok) 의 33% — **3.0× 저렴**
  - Sonnet ($0.0333/Ktok) 의 22% — **4.65× 저렴**
- 시사점: "풍부한 output 산출" trip 의 최저비용 provider 슬롯

#### 축 4 — 결정성 trade-off
- slide_count spread = 16 (Sonnet 2 대비 **8×**)
- output_tokens CV = 10.2% (Sonnet 1.6% 대비 **6.4×**)
- latency CV = 9.1% (Sonnet 6.8% 대비 1.34×) — latency 결정성은 비교적 양호
- 시사점: 결정성 critical 트랙 (계약서 자동화, 회계 보고 등) 부적합. 결정성 비critical 트랙 (브레인스토밍, 초안 생성, 대량 변형 생성) 적합.

### 슬롯 정체성 1줄 요약

> **"풍부한 output 을 초저지연 + 초저비용으로 산출하는 provider, 단 결정성 trade-off 수용 시"**

### Triple Track 운영 분기 권고

| 트랙 유형 | 권장 provider | 근거 |
|---|---|---|
| 표준 운영 (default) | gpt-4o | §13-7-4 박제 유지, 검증된 균형형 |
| 결정성 critical batch | Sonnet 4.6 | slide_count spread 2, CV 1.6% — Anthropic 슬롯 내 최고 결정성 |
| 저비용 대량 처리 | Haiku 4.5 | per output_token 단가 최저, 초저지연 |
| 결정성 비critical 초안 | Haiku 4.5 | 풍부 output + 저비용 + 초저지연 결합 |
| latency critical | Haiku 4.5 | 81% latency (gpt-4o 대비) |

### Sonnet 4.6 Baseline 갱신 (5-10 → 5-12)

#### Baseline 갱신 사유
5-10 baseline 은 gpt-4o sections input 기반. 5-12 본 측정은 Sonnet 자신이 생성한 풍부성 산출물 (latest.md, §13-14-α-sonnet 5-11 저녁) 을 다시 input 으로 사용 — **self-cascade input** 조건.

#### Baseline 비교 표

| 지표 | 5-10 baseline (gpt-4o input) | 5-12 갱신 (Sonnet self-cascade input) | 변동률 |
|---|---|---|---|
| latency mean | 199.4s | 317.0s | **+59%** |
| latency CV | 3.6% | 6.8% | +89% |
| output_tokens mean | ~7,680 | ~13,200 | **+72%** |
| output_tokens CV | n/a (미측정) | 1.6% | — |
| slide_count mean | 37 | 54.8 | **+48%** |
| slide_count spread | n/a | 2 | — |
| cost per run | $0.25 | $0.44 | **+76%** |

#### 갱신 baseline 의미
- "Sonnet 4.6 의 venfobel-vitamin 측정 baseline" 은 단일 값 아님
- input 조건 (gpt-4o sections / Sonnet sections / Haiku sections) 에 따라 4축 (latency / output / slide / cost) 전 지표 동반 변동
- baseline 박제 시 input provider + input 생성 시점 명시 필수 (catch 11 input cascade 일반화로 별도 박제)

#### Self-cascade 패턴 잠정 명명
- **Sonnet self-cascade pattern**: Sonnet 산출물을 Sonnet 의 input 으로 재투입 시 latency/output/cost 가 비선형 확대
- 메커니즘 가설: 풍부성 산출물의 토큰 밀도 증가 → 후속 산출 토큰 수 증가 → 처리 시간 증가 (선형 누적 가능성)
- 1회 측정 기반이므로 패턴 정밀화는 Phase 3-후속 또는 §13-9 별도 트랙 필요 (catch 3 sub-case 로 박제)

#### 운영 시사점
- Sonnet 4.6 batch 측정 baseline 박제 시 "input provider + 생성 시점" tag 필수
- 풍부성 누적이 의도된 트랙 (보고서 점진 정밀화) 에서는 self-cascade 가 자산
- 비용/지연 통제가 critical 한 트랙에서는 self-cascade 회피 (gpt-4o input fallback 또는 명시적 input freeze)

---

## §13-8-3-C — Catch 22 정밀화 (Multi-provider 정규화 보험 가치)

### 기존 catch 22 박제 내용 (§13-7~§13-8 시점)
> "schema fix (SlideSpec.bullets None→[]) 는 multi-provider 정규화 보험 자산"

### 정밀화 (5-12 본 측정 데이터 반영)

#### 정량 증거
- 진단 측정 (5-10): 9건 ValidationError 발생 (Haiku 진단 trip)
- 본 측정 (5-12): 0건 ValidationError (Sonnet n=5 + Haiku n=5, schema fix 후)
- bullets null count: Sonnet 0/274, Haiku 0/204 (정상 산출, validator 무관)

#### 정밀화된 명제
> "Multi-provider 정규화 (schema fix) 는 **보험 자산** 으로 유효. 단 ValidationError 발생률은 **input × provider × time 의 함수** — 단일 측정으로 보험 효과 정량화 불가."

#### 진단 → 본 측정 ValidationError drop 원인 평가 (4 가설)

| 가설 | 영향 추정 | 근거 |
|---|---|---|
| (A) Schema fix 단독 효과 | 5% | 본 측정 0건은 schema fix 후 측정이라 fix 가 필요 조건이긴 함. 다만 진단 9건은 fix 전 산출이므로 fix 적용 자체로 0 보장 안 됨 (Pydantic default_factory 사각지대 존재 — measure_stability 한계 4) |
| (B) Stochasticity | 30% | LLM 산출 자체 확률 변동. n=5 small sample 에서 0건 관측은 진단 trip 의 모집단 분포 미반영 가능성 |
| (C) Input 차이 | 40% | 진단 trip 의 input 조건과 본 측정 input 조건 불일치 가능성 (자세한 input log 부재 → 사후 검증 불가) |
| (D) Time 의존 (provider 측 변동) | 25% | Anthropic API endpoint 의 산출 분포가 5-10 → 5-12 사이 변동 가능성. 외부 통제 불가 변수 |

→ **(C) input 차이 + (B) stochasticity 결합** 가장 가능성 높음 (사용자 박제 평가)

#### 운영 결론
- Schema fix 는 **유지** — 보험 자산으로 cost 0, downside 0
- ValidationError 정량 보장 불가 — production 트랙에서 try/except 또는 retry 정책 필수
- 향후 ValidationError 발생 시 input × provider × time 3축 모두 log 필수 (재현 가능성 확보)

---

## §13-8-3-D — Catch 17 Sub-case (모델 Capacity vs 결정성 Inverse Correlation)

### 기존 catch 17 박제 내용
> "모델 capacity 와 결정성은 단순 비례 관계 아님"

### Sub-case 정량 증거 (Sonnet vs Haiku, same provider family)

| 지표 | Sonnet 4.6 | Haiku 4.5 | 비율 (Haiku/Sonnet) |
|---|---|---|---|
| capacity proxy (output_tokens mean) | ~13,200 | ~10,400 | 79% |
| capacity proxy (slide_count mean) | 54.8 | 69.8 | **127%** ⚠ |
| 결정성 (slide_count spread) | 2 | 16 | **800%** |
| 결정성 (output_tokens CV) | 1.6% | 10.2% | **638%** |
| 결정성 (latency CV) | 6.8% | 9.1% | 134% |

### Sub-case 명제
> "동일 provider family 내에서 lower-tier 모델 (Haiku) 이 higher-tier 모델 (Sonnet) 대비 **결정성은 일관적으로 낮고 (CV 6.4×, spread 8×)**, capacity proxy 는 지표별로 분기 (output_tokens 79% but slide_count 127%)."

### 메커니즘 가설
- Sonnet: 명시적 plan-and-execute 패턴 강화 학습 가능성 → 산출 구조 안정 → 결정성 ↑
- Haiku: 빠른 산출 우선 → plan 단계 simplification → 산출 구조 변동 ↑
- slide_count 가 output_tokens 보다 더 크게 변동 (8× vs 6.4×) → "구조 분해 결정성" 이 "토큰 산출 결정성" 보다 더 민감

### Catch 17 일반화
> "모델 capacity 를 단일 축으로 평가하면 결정성 trade-off 가 은닉됨. provider tier 선택 시 (capacity, 결정성, latency, cost) 4축 동시 평가 필수."

### 운영 시사점
- "Haiku = mini Sonnet" 식 단순 인식 회피
- 동일 provider family 내 tier 선택도 트랙 특성 (결정성 critical 여부) 기반 결정 필요

---

## §13-8-3-E — Catch 27 후보 (Haiku ValidationError 변동 평가)

### 후보 명제
> "Haiku 4.5 의 ValidationError 발생률은 단일 측정으로 정량화 불가. 진단 trip 9건 → 본 측정 0건 drop 의 4축 원인 분리 필요."

### 4 가설 평가 (catch 22 정밀화에서 도출)
- (A) Schema fix 효과: 5%
- (B) Stochasticity: 30%
- (C) Input 차이: 40%
- (D) Time 의존: 25%

### Catch 27 정식 박제 조건
- n=5 본 측정 1회 기반 → 통계적 신뢰도 부족
- 정식 박제 진입 조건:
  - condition 1: Haiku n≥15 측정 (3회 반복 측정 × n=5)
  - condition 2: input 통제 (sections, sections 생성 시점 명시)
  - condition 3: time 분산 (1주 간격 등) 으로 (D) 분리
- 현 상태: **후보 박제** — Phase 3 후속 또는 §13-9 트랙에서 정밀화

### 잠정 운영 정책
- Haiku production 트랙: schema fix + try/except + 1회 retry 정책 권고
- ValidationError rate 모니터링 — 일정 임계치 (예: 5%) 초과 시 input/time/version 조사 trigger

### Catch 27 정식 박제 시 추가 측정 필요 항목
- Haiku version 변동 (`claude-haiku-4-5-20251001` 이후 마이너 업데이트 추적)
- Schema 복잡도 vs ValidationError 상관 (bullets None 외 다른 nullable field)
- Input 길이 vs ValidationError 상관

---

## §13-8-3-F — Catch 26 Sub-section (Per-run-timeout 산식 정밀화)

### 기존 catch 26 박제 내용 (§13-7~§13-8 시점)
> "측정 인프라 표준: max_retries=0 + 2 warmup + per-run timeout + inter-run sleep 60s + PYTHONIOENCODING=utf-8"

### Sub-section 도출 배경 (5-12 본 측정에서 1차 timeout 실패 발생)

#### Sonnet 4.6 1차 측정 실패 사례
- **1차**: per-run timeout = 300s
- **결과**: ok 2/5 (3 runs timeout 직격)
- **원인**: Sonnet 4.6 self-cascade input 조건에서 mean latency 317s — 산식 부재 상태로 300s 설정 → mean 보다 낮은 timeout
- **2차 재산정**: per-run timeout = 420s (1차 측정 mean 317s × 1.32)
- **결과**: ok 5/5

### 사용자 박제 per-run-timeout 산식

```python
per_run_timeout = max(300, baseline_mean * 1.5)
# 추가 조건: 50% 최소 마진 확보
```

#### 산식 의미
- **floor**: 300s (gpt-4o/Sonnet baseline 의 안전 하한)
- **scaling factor**: 1.5× baseline mean (50% 마진)
- **2단계 산정**: 1차 시도 실패 시 측정 결과 mean 기반 재산정

### Triple Track per-run-timeout 권장값 (산식 적용)

| provider | baseline mean | 산식 결과 | 권장 timeout | 마진 |
|---|---|---|---|---|
| gpt-4o | 172.1s | max(300, 258) = 300s | 300s | 74% |
| Sonnet 4.6 (5-12 baseline) | 317.0s | max(300, 476) = 476s | **480s** (반올림) | 51% |
| Haiku 4.5 | 139.85s | max(300, 210) = 300s | 300s | 114% |

→ Sonnet 의 경우 5-12 baseline 갱신 후 산식 적용 시 480s 권장. 2차 측정 420s 도 ok 5/5 통과했으므로 두 값 모두 유효 영역.

### 산식 적용 운영 순서

1. **사전 baseline 확인**
   - 측정 대상 provider × input 조건의 기존 baseline 존재 여부 확인
   - baseline 없으면 → 진단 측정 (n=2~3) 으로 baseline 잠정 산정
2. **1차 timeout 설정**
   - 산식 적용: `max(300, baseline_mean * 1.5)`
3. **본 측정 실행 (n=5)**
4. **실패 분기**
   - ok 5/5: 통과, baseline 갱신
   - ok 0~4/5 with timeout: 2차 재산정 — `max(1차 timeout, 1차 mean * 1.5)`
   - ok 0~4/5 without timeout (다른 원인): timeout 외 원인 조사

### 차단 조건 표준 (본 phase 박제 — measure_stability 운영 정책)

| 조건 | 대응 |
|---|---|
| ValidationError ≥ 1건 | **즉시 중단** |
| ok=False 1건 (timeout) | 5 runs 계속, baseline drift 박제 |
| ok=False 2~4건 (timeout) | 5 runs 중단, timeout 상향 결정 요청 |
| ok=False 5건 (전건 timeout) | 인프라 이슈 보고 (API 측 장애 의심) |
| bullets_null_count > 5 | 즉시 보고 (sanity check 실패 — schema fix 우회 가능성) |
| 평균 latency drift > 30% (기존 baseline 대비) | 측정 계속, baseline drift 박제 후 원인 조사 |

### Sub-section 운영 시사점

- **timeout 단일 값 박제 회피** — provider/input 조합별 산식 적용 박제
- **baseline drift 박제 필수** — 동일 provider 라도 input 변경 시 baseline 갱신
- **2단계 측정 표준화** — 진단 측정 → 본 측정 분리 가능 (진단 n=2, 본 n=5)
- **차단 조건 표는 measure_stability.py 의 자동 중단 로직 미구현 상태에서 운영자 수동 판단 기준** (catch 26 sub 한계 1 으로 별도 박제 — §13-8-3-H)

---

## §13-8-3-G — Catch 32 (Sections/latest.md Provider Mismatch)

### 발생 경위

#### Phase 1 측정 trip 중 산출물 변동 이력

| 시점 | sections/venfobel-vitamin/ | reports/venfobel-vitamin/latest.md | 상태 |
|---|---|---|---|
| §13-14-α-sonnet 5-11 저녁 | Sonnet 풍부성 산출물 | Sonnet 풍부성 산출물 | provider 일치 |
| 5-12 measurement 진입 (gpt-4o 회귀) | gpt-4o 복원 | (변동 없음) | mismatch 발생 |
| 5-12 Sonnet 회귀 측정 | (변동 없음, gpt-4o 유지) | (변동 없음, Sonnet 유지) | mismatch 유지 |
| 5-12 Haiku 본 측정 | (변동 없음, gpt-4o 유지) | (변동 없음, Sonnet 유지) | mismatch 유지 |
| **Phase 1 close 시점 (5-12)** | **gpt-4o 복원 상태** | **Sonnet 풍부성 산출물** | **mismatch 의도적 보존** |

### Mismatch 의 의미

#### sections/venfobel-vitamin/
- §13-7-4 운영 default (gpt-4o) 기준 sections 박제
- 측정 baseline input 조건으로 사용 (Sonnet/Haiku 측정 trip 모두 동일 input)
- 측정 baseline 의 input 통제 보장 (input × provider × time 분리 가능)

#### reports/venfobel-vitamin/latest.md
- §13-14-α-sonnet 트랙의 풍부성 산출물 보존
- Sonnet 4.6 self-cascade input 조건의 원천 (5-12 Sonnet 재측정 input)
- 풍부성 트랙 자산 보존 (재현 불가능 — sections 변경 후 재생성 불가)

### Mismatch 가 야기하는 위험

#### 위험 1 — Phase 2 e2e export 시 산출물 일관성 손실
- `bell.export.pptx` (또는 동등 모듈) 이 어느 파일을 읽는가에 따라 결과 분기
- 케이스 A: sections-only 의존 → mismatch 무관, gpt-4o 산출물 PPTX
- 케이스 B: latest.md-only 의존 → sections 무관, Sonnet 산출물 PPTX
- 케이스 C: 둘 다 의존 → provider mismatch 산출물 PPTX (정합성 무너짐)

#### 위험 2 — 측정 baseline 의 재현 가능성 손실
- 5-12 Sonnet 재측정 input (latest.md, Sonnet 풍부성 산출물) 이 영구 보존되지 않으면 self-cascade pattern 재측정 불가
- 현재는 `reports/venfobel-vitamin/_sections_sonnet_R3_backup/` 1 명령 복원 가능 (안전망 존재)

#### 위험 3 — 후속 보고서 생성 시 input 출처 혼동
- §13-9 이후 venfobel-vitamin topic 으로 재진입 시 어느 파일을 input 으로 쓸지 명시 필요
- 의도된 mismatch 임을 운영자가 인지하지 못하면 비의도된 결과 발생

### Phase 2 진입 전 사전 점검 항목

#### 사전 점검 1 — 코드 의존 분석
- 대상 모듈: `bell.export.pptx`, `agent/export/*`, `agent/communicator.py`
- 확인 사항: sections / latest.md / 둘 다 / 다른 파일 의존 분기
- 분석 방법: grep `"sections/"`, `"latest.md"`, `"_sections_"` 패턴

#### 사전 점검 2 — 산출물 일관성 정책 결정
- 옵션 A: sections-only 의존이면 → mismatch 보존, latest.md 는 자산 보관용
- 옵션 B: latest.md 의존이면 → sections 도 Sonnet 으로 재생성 (mismatch 해소)
- 옵션 C: 양쪽 의존이면 → provider 통일 (gpt-4o 또는 Sonnet) 또는 input 출처 명시 정책 추가

#### 사전 점검 3 — Phase 2 측정 baseline input 결정
- Phase 2 e2e 측정 시 input 으로 sections / latest.md / 양자 결합 중 선택
- 선택 후 Phase 2 baseline 박제 시 input 출처 + provider + 생성 시점 tag 필수

### Catch 32 일반화

> "Multi-provider 측정 trip 에서 산출물 파일 (sections, latest.md, _backup_*) 의 **provider tag** 부재 시 mismatch 발생 가능. 산출물 파일에 generation metadata (provider, model, timestamp, input 출처) 박제 정책 필요."

### 운영 시사점

- **산출물 metadata 박제 정책 도입 검토** — 파일 헤더 또는 sidecar (.meta.json) 에 generation 정보 박제
- **현 mismatch 는 안전망 backup (`_sections_sonnet_R3_backup/`) 으로 복원 가능 — 보존 가치 유효**
- **Phase 2 진입 시 사전 점검 1~3 완료 후 mismatch 해소 또는 명시적 보존 결정**
- **catch 32 정식 박제 조건**: 사전 점검 1 (코드 의존 분석) 완료 후 의존 케이스 확정 시 정식 박제. 현 상태는 **후보 박제** (실측 의존 분석 미완료).

### Phase 2 진입 시 의사결정 트리

```
Phase 2 진입
├─ 사전 점검 1: 코드 의존 분석
│   ├─ Case A (sections-only): mismatch 무관 → Phase 2 진입
│   ├─ Case B (latest.md-only): sections 무관 → Phase 2 진입 (단, sections 변경 영향 0 명시)
│   └─ Case C (양쪽 의존): mismatch 해소 결정 필요
│       ├─ Option B-1: sections 를 Sonnet 으로 재생성 (cost ~$0.44, 풍부성 일관)
│       ├─ Option B-2: latest.md 를 gpt-4o 로 재생성 (cost ~$0.12, default 일관)
│       └─ Option B-3: 양쪽 모두 Haiku 로 재생성 (cost ~$0.13, 저비용 트랙 검증)
└─ 결정 후 Phase 2 진입
```

---

## §13-8-3-H — measure_stability.py 한계 4건 (인프라 Catch 박제)

### 박제 배경
Phase 1 측정 trip (gpt-4o 회귀 + Sonnet 회귀 + Sonnet 본 측정 + Haiku 본 측정) 운영 과정에서 measure_stability.py 의 4 가지 구조적 한계가 노출됨. 측정 도구 자체의 catch 로 박제하여 후속 개선 트랙 또는 운영자 우회 정책 도출 근거 확보.

### 한계 1 — 차단 조건 자동 중단 로직 부재

#### 증상
- ValidationError 발생 시 즉시 중단 정책 (§13-8-3-F 차단 조건 표) 이 코드에 미구현
- ok=False 2~4건 발생 시 자동 중단 미작동 — 5 runs 강제 완주
- 운영자가 background 실행 후 결과 회수 시점에 차단 조건 위반 사후 확인

#### 영향
- 진단 측정 9건 ValidationError 의 경우, 1건 시점 중단되었으면 측정 비용 절감 가능 (실제 9건 완주 = ~$0.5 추가 소비)
- 5-12 Sonnet 1차 측정 (300s timeout, ok 2/5) 의 경우 3건째 timeout 시점 중단되었으면 60s × 2 inter-run sleep 추가 소비 회피 가능

#### 우회 정책 (현행)
- 운영자 수동 판단 — background 실행 후 결과 회수 시점에 차단 조건 표 적용
- 비용 효율은 낮으나 인프라 안전성은 유지 (race condition 없음)

#### 개선 옵션
- (a) 차단 조건 인라인 hook 추가 — 각 run 종료 시 조건 평가 후 ThreadPoolExecutor cancel
- (b) 차단 조건 외부 watcher — log 파일 polling 으로 조건 위반 감지 → SIGTERM 발송
- (c) **현행 유지** — 운영 빈도 (월 1~2회 measurement trip) 고려 시 자동화 ROI 낮음

#### 박제 결론
- 후속 개선 트랙 후보 (우선순위 낮음)
- 현행 수동 판단 정책 박제 유지 (§13-8-3-F 차단 조건 표)

### 한계 2 — Background 실행 시 실시간 Watch List 보고 불가

#### 증상
- measure_stability.py 를 background 실행 시 (Claude Code `&` 또는 nohup) 실시간 progress / watch list 출력 회수 불가
- 종료 후 stdout log + json log 일괄 회수만 가능
- run 1 → run 2 진행 중 차단 조건 위반 발생 시 인지 시점이 종료 후로 지연

#### 영향
- 측정 trip 의 실시간 모니터링 trip 분리 — "background 실행 + 일괄 검토" 패턴 강제
- 차단 조건 위반 시 비용 절감 기회 손실 (한계 1 과 결합 효과)

#### 우회 정책 (사용자 박제)
- "background 측정 종료 후 watch list 일괄 점검 (실시간 못 봄)" (NEXT_SESSION.md §7)
- 종료 시점 stdout/json 일괄 검토 표준화

#### 개선 옵션
- (a) tail -f log 파일 + grep ValidationError 패턴 watcher
- (b) WebSocket/SSE 기반 실시간 progress 출력 — overengineering 가능성 높음
- (c) **현행 유지** — 운영 트랙에 부합

#### 박제 결론
- 운영 정책 박제 (background + 일괄 검토 표준) — 도구 개선 트랙 후보 아님

### 한계 3 — ThreadPoolExecutor 비취소 Race

#### 증상
- measure_stability.py 의 ThreadPoolExecutor.submit() 으로 시작된 LLM call 은 timeout 도달 시 future.cancel() 호출되어도 실제 LLM API 호출은 진행 중
- timeout 처리 후에도 background 에서 API 응답 도착 가능 → 비용 발생
- 차단 조건 자동 중단 (한계 1) 구현 시 timeout race 와 결합되어 추가 race condition 발생 가능

#### 영향
- 측정 비용의 hidden tail — timeout 처리된 runs 도 API 비용 발생
- 5-12 Sonnet 1차 측정 (3건 timeout) 의 경우 timeout 처리되었지만 LLM 산출은 완료되었을 가능성 → 약 $0.44 × 3 = $1.32 비용 발생 가능성 (실측 미확인)

#### 우회 정책
- 산식 적용 timeout (§13-8-3-F) 으로 timeout 발생 자체를 회피
- 1차 측정 실패 시 즉시 2차 재산정 진입 (불필요한 1차 재시도 회피)

#### 개선 옵션
- (a) httpx-based custom HTTP client + asyncio.CancelledError 핸들링 — Anthropic SDK 의 cancellation 지원 검증 필요
- (b) LLM call 을 별도 subprocess 로 격리 후 SIGTERM 으로 강제 종료 — overengineering
- (c) **현행 유지 + timeout 산식 적용으로 race 발생 자체 최소화**

#### 박제 결론
- 운영 정책 박제 — 산식 적용 timeout 으로 race 회피
- 도구 개선은 SDK level cancellation 지원 시점에 재검토 (현 시점 후속 트랙 아님)

### 한계 4 — Bullets Omit 사각지대 (Pydantic default_factory)

#### 증상
- SlideSpec.bullets None→[] before-validator (commit `7713426`) 는 LLM 이 `bullets: None` 명시 산출 시 정상 작동
- 단 LLM 이 `bullets` 필드 자체를 **omit** 산출 시 (key 누락) Pydantic default_factory=list 가 우선 적용되어 validator 미경유
- → bullets omit 케이스의 sanity check 불가 (validator 가 None→[] 변환을 보장하지 못함)

#### 영향
- bullets omit 산출의 정량 측정 불가 — Sonnet 0/274, Haiku 0/204 의 sanity check 표시는 실제로 "omit + default_factory 적용" 케이스 포함 여부 미상
- 측정 데이터의 신뢰도 잠재 손실 — bullets null count 가 실제 LLM 결정성을 반영하지 못할 가능성

#### 우회 정책
- 현재 SlideSpec 의 다른 field (title, content) 에서 동등 산출 풍부도 관측 → bullets omit 케이스가 의도된 산출 분포 내에 있을 가능성 (정상 동작)
- Phase 2 e2e export 시 PPTX 산출물의 bullets 표시 여부로 실측 검증 가능

#### 개선 옵션
- (a) SlideSpec.bullets 의 default_factory 제거 + Optional[list] 명시 + validator 강제 — schema 변경 영향 광범위
- (b) measure_stability.py 에 omit count 별도 측정 추가 — `bullets` key 존재 여부 raw json 단계 확인
- (c) **현행 유지** — bullets omit 의 운영 영향이 검증되지 않은 시점이라 schema 변경 ROI 불명확

#### 박제 결론
- 후속 트랙 후보 (Phase 2 e2e 후 운영 영향 검증 후 결정)
- 현 시점은 한계 박제 유지 (catch 22 의 보험 가치 제약 조건 명시)

### 한계 4건 종합 운영 정책

| 한계 | 우회 정책 | 도구 개선 트랙 우선순위 |
|---|---|---|
| 1. 차단 조건 자동 중단 부재 | 수동 판단 (§13-8-3-F 차단 조건 표) | 낮음 (월 1~2회 trip 빈도) |
| 2. Background 실시간 보고 불가 | 종료 후 일괄 검토 표준 | 트랙 후보 아님 (운영 정책으로 흡수) |
| 3. ThreadPoolExecutor 비취소 race | 산식 timeout 으로 race 회피 | 낮음 (SDK cancellation 지원 시점 재검토) |
| 4. Bullets omit 사각지대 | Phase 2 e2e 실측 검증 대기 | 중간 (운영 영향 검증 후 결정) |

### 한계 종합 시사점

> "measure_stability.py 는 **측정 trip 의 baseline 산출 도구** 로 충분히 작동. 단 (a) 비용 효율 (한계 1, 3), (b) 실시간 monitoring (한계 2), (c) sanity check 완전성 (한계 4) 의 3축에서 구조적 제약 존재. 운영 정책으로 우회 가능한 영역은 정책 박제 유지, 도구 개선 트랙은 Phase 2 e2e 검증 후 ROI 평가."

---

## §13-8-3-I — Input Cascade 일반화 + Sonnet Self-cascade Pattern

### 박제 배경
Phase 1 본 측정 (5-12) 에서 Sonnet 4.6 baseline 5-10 → 5-12 갱신 시 4축 (latency / output / slide / cost) 전 지표 동반 변동 관측. 단일 측정이 아닌 **input × provider × time** 3축 함수로서의 측정 baseline 일반 명제 도출.

### Part 1 — Input Cascade 일반화 (Catch 11)

#### 일반 명제

> "측정 baseline 은 단일 값이 아닌 **input × provider × time** 3축 함수. input 변경 시 (a) latency, (b) output tokens, (c) 구조 분해 결정성 (slide_count 등), (d) cost 의 4축이 동반 변동."

#### 정량 증거 (Sonnet 4.6, 5-10 → 5-12)

| 축 | 5-10 (gpt-4o input) | 5-12 (Sonnet self-cascade) | 변동률 |
|---|---|---|---|
| latency mean | 199.4s | 317.0s | +59% |
| output_tokens mean | ~7,680 | ~13,200 | +72% |
| slide_count mean | 37 | 54.8 | +48% |
| cost per run | $0.25 | $0.44 | +76% |

→ 4축 동반 변동 패턴 관측. 변동률 +48% ~ +76% 범위 (단일 input 변경의 영향).

#### 메커니즘 가설

1. **토큰 밀도 cascade**
   - input token 수 증가 → context length 증가 → 응답 처리 시간 증가
   - input 의 정보 밀도 증가 → 산출 토큰 수 증가 (응답 풍부도 동반)
2. **구조 분해 cascade**
   - input 의 구조적 복잡도 (sections 수, sub-section 깊이) 증가 → slide_count 증가
   - 풍부한 input → 풍부한 output 의 구조 매핑
3. **Cost 누적**
   - input token cost + output token cost 동시 증가 → per-run cost 비선형 누적

#### 일반화된 측정 정책

- **Baseline 박제 시 input metadata 필수**:
  - input 출처 (어느 파일)
  - input 생성 provider + model
  - input 생성 시점 (timestamp)
  - input token 수 (가능 시)
- **Baseline 단일 값 박제 회피** — provider × input 조합별 baseline 분리 박제
- **재현 가능성 확보** — input 파일 보존 또는 backup 디렉터리 명시 (예: `_sections_sonnet_R3_backup/`)

#### Triple Track 적용 시사점

| provider | gpt-4o input baseline | Sonnet self-cascade baseline | Haiku 본 측정 baseline |
|---|---|---|---|
| gpt-4o | 172.1s (5-12 회귀) | 미측정 | 미측정 |
| Sonnet 4.6 | 199.4s (5-10) | 317.0s (5-12) | 미측정 |
| Haiku 4.5 | 139.85s (5-12, **단** gpt-4o sections input) | 미측정 | 미측정 |

→ Triple Track 의 완전한 input × provider matrix 는 9 cell, 현 측정은 4 cell (44%) 만 완료. Phase 3 후속 또는 §13-9 트랙에서 matrix 보완 가능.

### Part 2 — Sonnet Self-cascade Pattern (Catch 3 Sub-case)

#### 패턴 정의

> "**Sonnet self-cascade pattern**: Sonnet 4.6 의 풍부성 산출물을 Sonnet 4.6 의 input 으로 재투입 시 latency / output / cost 4축이 비선형 확대되는 패턴. 1회 측정 기반 관측, 일반화 검증 미완료."

#### 정량 관측

- latency: 199.4s → 317.0s (+59%)
- output_tokens: ~7,680 → ~13,200 (+72%)
- slide_count: 37 → 54.8 (+48%)
- cost: $0.25 → $0.44 (+76%)

#### 비선형 확대 검증 (단순 input cascade 와 분리)

- input cascade 일반 명제는 input 변경의 영향 (provider 무관)
- Self-cascade 는 **동일 provider 의 산출물을 재투입** 조건 — 풍부성 누적 효과의 가설적 명명
- 단순 input cascade 와 self-cascade 의 분리 검증을 위해서는 cross-cascade (gpt-4o 산출물 → Sonnet 측정, Haiku 산출물 → Sonnet 측정) 측정 필요

#### 메커니즘 가설

1. **풍부성 토큰 밀도 일치 가설**
   - Sonnet 산출물의 토큰 밀도 ≈ Sonnet 산출 분포의 mode
   - 자기 산출물을 input 으로 받으면 "익숙한 분포" 인식 → 산출 확장 (recurrent amplification)
2. **구조 매핑 가설**
   - Sonnet 의 구조 분해 패턴이 input 구조와 일치 → 1:1 매핑 산출 → slide_count 비례 확대
3. **확신도 가설**
   - 자기 산출 토큰 분포에 익숙 → 산출 확신도 증가 → 토큰 cutoff 지연 → output 풍부도 증가

#### 정식 catch 박제 조건

현 상태: **Catch 3 sub-case 후보 박제** — 1회 측정 기반, 일반화 검증 미완료.

정식 박제 진입 조건:
- condition 1: cross-cascade 측정 (gpt-4o 산출물 → Sonnet, Haiku 산출물 → Sonnet) 각 n=3 이상
- condition 2: self-cascade 반복 측정 (n=3 trip × 1주 간격) 으로 time 분산
- condition 3: 다른 topic (venfobel-vitamin 외) 에서 self-cascade pattern 재현 검증

#### 운영 시사점

- **풍부성 누적이 의도된 트랙** (예: 보고서 점진 정밀화, 다단계 편집 trip) 에서 self-cascade 는 자산
  - latency / cost 비용 증가는 산출 풍부도 향상의 대가
- **비용/지연 통제가 critical 한 트랙** 에서 self-cascade 회피
  - 옵션 A: gpt-4o input fallback (input 출처 분리)
  - 옵션 B: 명시적 input freeze (sections 변경 차단)
  - 옵션 C: input 압축 단계 추가 (풍부성 산출물 → 요약 → 재투입)

#### Cross-provider Cascade 후속 트랙 후보

| 측정 트랙 | input 출처 | 측정 provider | 가설 |
|---|---|---|---|
| Cross-cascade 1 | gpt-4o sections (5-12 복원) | Sonnet 4.6 | 5-10 baseline 199.4s 재현 |
| Cross-cascade 2 | Haiku sections (Phase 2 생성 시) | Sonnet 4.6 | 풍부성 중간 수준 → 250~280s 추정 |
| Cross-cascade 3 | Sonnet sections (5-11 풍부성) | gpt-4o | gpt-4o 의 self-cascade 부재 검증 |
| Cross-cascade 4 | Sonnet sections (5-11 풍부성) | Haiku 4.5 | Haiku 의 cross-cascade 영향 검증 |

→ Phase 3 close 후 §13-9 트랙 진입 시 우선순위 결정 가능. 측정 비용 추정: 각 trip n=3, total ~$3 (Sonnet $0.44 × 6 + Haiku $0.13 × 3 + gpt-4o $0.12 × 3).

### Part 3 — Catch 박제 우선순위 종합

#### 정식 박제 (Phase 1 close 시점)

- §13-8-3-C catch 22 정밀화: 보험 가치 + 4 가설 평가
- §13-8-3-D catch 17 sub-case: capacity vs 결정성 inverse correlation
- §13-8-3-F catch 26 sub-section: per-run-timeout 산식
- §13-8-3-I Part 1 catch 11 input cascade 일반화

#### 후보 박제 (정식 박제 진입 조건 명시)

- §13-8-3-E catch 27: Haiku ValidationError 변동 — n≥15, time 분산 필요
- §13-8-3-G catch 32: provider mismatch — 코드 의존 분석 필요
- §13-8-3-I Part 2 catch 3 sub-case Sonnet self-cascade — cross-cascade 측정 필요

#### 인프라 catch 박제 (§13-8-3-H)

- 한계 1: 차단 조건 자동 중단 부재 (개선 우선순위 낮음)
- 한계 2: background 실시간 보고 불가 (운영 정책 흡수)
- 한계 3: ThreadPoolExecutor 비취소 race (개선 우선순위 낮음)
- 한계 4: bullets omit 사각지대 (Phase 2 e2e 검증 후 결정)

### Phase 1 박제 자산 총괄

- **§13-8-3-A**: Triple Track 정량 데이터 표
- **§13-8-3-B**: Haiku 슬롯 정체성 (4축) + Sonnet baseline 갱신
- **§13-8-3-C ~ E**: catch 22/17/27 정밀화
- **§13-8-3-F**: catch 26 sub-section (per-run-timeout 산식)
- **§13-8-3-G**: catch 32 (provider mismatch) 후보 박제
- **§13-8-3-H**: measure_stability.py 한계 4건 (인프라 catch)
- **§13-8-3-I**: catch 11 input cascade 일반화 + catch 3 sub-case (Sonnet self-cascade)

총 12 catch 후보 중 4건 정식 박제, 3건 후보 박제, 4건 인프라 catch 박제, 1건은 §13-8-3 phase1_summary.md (commit `5e6536b`) 에 박제된 진단 측정 9건 ValidationError 의 4 가설 평가로 흡수.

---

## 다음 세션 진입 시 처리 사항

### 1. README-dev-2.md append + commit
- 본 파일 내용을 `D:/gpt_agent/writer_project/README-dev-2.md` 에 append (또는 신규 생성)
- commit message 권고: `docs: §13-8-3 Phase 3 박제 — Triple Track 정량 + catch 12건 정밀화`

### 2. NEXT_SESSION.md 처리
- 직전 NEXT_SESSION.md (§9 명시 일회용) archive 또는 delete
- Phase 2 진입 시 신규 NEXT_SESSION.md 작성

### 3. Phase 2 진입 결정
- §13-8-3-G 의사결정 트리 진입
- 사전 점검 1 (코드 의존 분석) → 사전 점검 2 (산출물 일관성 정책) → 사전 점검 3 (Phase 2 baseline input 결정)
