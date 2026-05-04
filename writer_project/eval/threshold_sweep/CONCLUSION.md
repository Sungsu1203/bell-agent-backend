# §12-12-1 Conclusion — Threshold Sweep, venfobel-vitamin

**상태**: close (운영 적용 미실시)
**작성일**: 2026-05-04
**근거 산출물**: `eval/threshold_sweep/venfobel-vitamin_sweep.md` (S2 결과)

---

## 1) 문제 정의

§12-4-A (b) 2차 시도(venfobel-vitamin 임베딩 평가)에서 발견:

> 운영 `OPERATIONAL_THRESHOLD = 0.65`에서 venfobel 골드셋 기준
> precision 5% / recall 100%. cut-off로 사실상 기능 안 함.

§12-12-1은 이 발견을 바탕으로 **threshold τ를 sweep해서 운영 적용 가능한
권장값을 도출**하는 작업으로 출범.

사전 가설(README §12-12-1 박제):
- 권장값 후보 ~0.20 (rel.p75와 hardneg.median 중간)
- threshold를 운영 분포 기준값으로 내리면 retrieval 노이즈 감소

---

## 2) 측정 설계 요약

| 결정점 | 결론 |
| --- | --- |
| sweep 범위 | 0.15~0.30 step 0.025 (7 포인트) + baseline 0.60, 0.65 = 9 포인트 |
| 측정 지표 | 평가 골드셋(n=21) 재사용 + same-source hardneg 보정 |
| 토픽 일반화 | venfobel sweep 본측정 + pet-food-premium 분포 정성 비교 (S3 예정이었으나 후술 사유로 미진입) |
| 적용 방식 | 토픽별 절차 정립 디폴트 + 글로벌 default는 결과 보고 결정 |
| 회귀 방지 | 골드셋 + 운영 query / 청크수 + source분포 + set diff |

산출 도구: `tools/threshold_sweep.py` (S1).

---

## 3) 측정 결과 핵심

### 3-1. 분포

| 카테고리 | n | median | p25 | p75 | p95 |
| --- | --- | --- | --- | --- | --- |
| relevant | 21 | 0.136 | 0.117 | 0.164 | 0.307 |
| hardneg (raw) | 420 | 0.249 | 0.215 | 0.286 | 0.339 |
| hardneg (보정) | 344 | 0.251 | 0.219 | 0.290 | 0.348 |

- relevant median 0.136 vs hardneg median 0.249 → median 격차는 0.113.
- relevant p95 0.307 > hardneg p25 0.215 → **두 분포의 꼬리가 겹침**.
- 사전 박제값 ~0.20 = (rel.p75 0.164 + hardneg.median 0.249) / 2 산술적 중간.
- 산술적 중간이 분리 가능한 cut-off는 아님.

### 3-2. Sweep (보정 ON, 메인)

| τ | precision | recall | F1 |
| --- | --- | --- | --- |
| 0.150 | 0.591 | 0.619 | **0.605** ← F1 최대 |
| 0.175 | 0.395 | 0.810 | 0.531 |
| 0.200 | 0.254 | 0.857 | 0.391 |
| 0.225 | 0.156 | 0.905 | 0.266 |
| 0.250 | 0.101 | 0.905 | 0.181 |
| 0.275 | 0.075 | 0.905 | 0.139 |
| 0.300 | 0.065 | 0.905 | 0.121 |
| 0.600 | 0.058 | 1.000 | 0.109 |
| 0.650 | 0.058 | 1.000 | 0.109 |

### 3-3. 절벽

- 보정 ON: **절벽 없음** (가장 큰 jump 0.150→0.175 사이의 -0.196, CLIFF_MIN_JUMP=0.20 미만).
- 보정 OFF (raw): 절벽 없음.
- 즉 precision 곡선이 매끄럽게 단조감소. "절벽 직전" 권장값 산출 불가.

---

## 4) 발견 사항

### 4-1. 사전 가설 정정

박제된 권장값 ~0.20은 **분포 통계로는 정확**(rel.p75와 hardneg.median 중간).
그러나 τ=0.20에서 precision 25.4% (보정), 19.4% (raw). **"두 분포 중간이면
분리 잘 됨"이라는 가정이 이 토픽에서 틀림**. 산술적 중간이 분리 능력 있는
cut-off가 아닌 사례.

### 4-2. 운영 0.65 = 사실상 cut-off 없음 재확인

τ=0.60과 τ=0.65 행 동일 (recall 1.000, retrieved/q 17.38). §12-4-A (b) 박제
"운영 retrieval이 사실상 cut-off 없이 머지 중"의 정량 재확인.

### 4-3. same-source 보정 effect 정량화

τ=0.20 기준:
- precision 0.254 (보정) vs 0.194 (raw) → +30% 상대 개선
- hardneg↓ 53 vs 75 → 29% 감소

운영 의미의 precision은 raw 측정보다 높을 가능성. same-source 청크는 운영에서
"노이즈 아닌 회색지대"라 raw precision은 운영 품질 과소평가. **다만 보정 ON
기준에서도 모든 τ에서 precision < 0.6**.

### 4-4. 본질 — venfobel 분포 자체가 threshold cut-off에 부적합

§12-4-A (b) 결론(gemini-001이 ranking은 우세하나 gap_ratio 0.94×로 분포 변별
폭은 좁음)과 정합. 운영 모델(text-multilingual-embedding-002)에서도 같은 현상.

→ threshold cut-off가 안 통하는 본질이 **임베딩 모델 특성**이 아니라
**이 토픽의 데이터 특성**. 좁은 도메인 + multi-chunk source 81% + relevant/hardneg
꼬리 중첩.

---

## 5) 시나리오 판정

사전 박제 시나리오 1/2/3 매칭:

| 시나리오 | 사전 정의 | 실측 |
| --- | --- | --- |
| 1 | 절벽 식별 가능 → 글로벌 default 변경 | ❌ |
| 2 | 절벽 없지만 분포 비율로 권장값 산출 | △ 부분 |
| 3 | 측정 자체 무의미 | △ 부분 |

진실은 **2와 3 사이**. 측정은 됐고 권장값 후보(F1 최대 τ=0.150)는 산출됐으나
그 권장값의 precision도 0.591에 그침. recall 손실 38%(21개 정답 중 8개 cut-off
손실)와 trade off.

---

## 6) Close 결정

### 6-1. 결정 — 운영 적용 미실시

- 권장 후보 τ=0.150은 precision 0.591 / recall 0.619.
- 운영 0.65 (cut-off 사실상 없음, recall 1.000)와 비교 시 **recall 38% 손실
  대비 precision 개선의 trade off가 운영 가치 없음**.
- 더 보수적인 τ(0.20~0.30) 구간은 precision < 0.30으로 더 떨어져 가치 없음.
- venfobel 토픽 override 변경하지 않음. 글로벌 default 0.65 유지.

### 6-2. §12-12-1 close 사유 박제

> venfobel 토픽 분포 특성상 distance threshold cut-off는 retrieval 분리
> mechanism으로 부적합. F1 최대값 τ=0.150도 운영 적용 가치 없음. 본 작업
> close, 운영 cut-off는 현 상태(글로벌 0.65) 유지.

### 6-3. 향후 다른 토픽 발견 시 대응

§12-12-1을 단순 done이 아닌 close로 두는 이유: **다른 토픽에서 절벽이 식별되면
재진입 가치 있음**. 재진입 조건은 §6-4 참조.

---

## 6-4) 재진입 조건

§12-12-1 또는 후속 §12-12-1b를 다시 열어야 하는 조건 세 가지:

**(R1) 다른 토픽에서 절벽 식별**
- §12-12-4 (pet-food-premium 일반화 검증) 또는 새 토픽에서
  threshold sweep 시 precision jump ≥ 0.20 (CLIFF_MIN_JUMP) 식별되면
  해당 토픽 한정으로 토픽 override 적용 + 본 작업 재진입.
- 단 venfobel 결과를 글로벌화하지 않는다 — 토픽별 측정 후 토픽별 적용.

**(R2) 임베딩 모델 변경**
- §12-12-2 (VertexAIEmbeddings deprecation 마이그레이션) 시
  새 모델로 venfobel 골드셋 재측정 필수. 새 모델의 분포 변별 폭이 다르면
  결과 달라질 수 있음.

**(R3) 골드셋 보강**
- venfobel 골드셋 21건이 분포 측정에 충분치 않을 가능성.
  §12-12-3 (web 인덱스 보강) 후 web tier 골드셋 추가하면 재측정 가치 있음.
  단 현 결과(절벽 없음)는 분포 폭의 본질적 좁음에서 나온 결과라 골드셋 양
  증가만으로 절벽이 생길 가능성은 낮음 — R3 단독으로는 우선순위 낮음.

---

## 7) 후속 분기 (§12-12-1 외부)

본 작업이 close됨에 따라, **venfobel 같은 좁은 분포 토픽에서 retrieval 품질을
개선하는 다른 mechanism**이 별도 관심사로 분기. README §12 본 절의 기존 항목
두 건과 연결:

### 7-1. §12-2 (distance threshold 재튜닝 절차)

§12-2의 절차 — "분포 측정 후 절벽 직전 값 선택"은 venfobel 같은 토픽에서
**절벽 자체가 없으므로 절차 적용 불가**. §12-2 본문에 한계 명시 추가 필요.
(본 close commit에서 README §12-2에 보강 메모 추가.)

### 7-2. §12-6 (BM25 키워드 검색 보강)

§12-6은 "정확 매칭 약한 부분 보완"으로 박혀있음. venfobel처럼 좁은 도메인
+ 임베딩 분포 변별 부족 토픽에서는 **BM25 같은 keyword-based mechanism이
distance threshold보다 효과적일 가능성**. 본 결과는 §12-6 우선순위 데이터
포인트로 박제.
(본 close commit에서 README §12-6에 보강 메모 추가.)

---

## 8) 산출물

- `tools/threshold_sweep.py` — sweep 측정 도구 (S1, 신규)
- `eval/threshold_sweep/venfobel-vitamin_sweep.md` — sweep 결과 (S2)
- `eval/threshold_sweep/CONCLUSION.md` — 본 문서 (close 박제)

## 9) 처리 commit

- A: `feat(eval): add threshold_sweep tool + venfobel sweep result`
- B: `docs(readme): close §12-12-1 — threshold cut-off unsuitable for narrow-distribution topics`