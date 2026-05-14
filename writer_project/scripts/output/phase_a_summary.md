# §14-2 Phase A 결과 — gemini-2.5-flash N=5

## 측정 환경
- commit: `d88a8b9` (Step 1b 적용 상태)
- venv: `.venv_vertex`
- GCP project/region: `gemini-rag-search-final` / `us-central1`
- VERTEX_MAX_RETRIES=0, inter-sleep=60s, per-call timeout=120s
- 측정 시각: 2026-05-14 20:49 KST
- 결과 JSON: `scripts/output/phase_a_20260514_204914.json`
- 콘솔 로그: `scripts/output/phase_a_console_run.log`

## 쿼리별 통계 (N=5)

| query | elapsed (mean ± stdev, cv%) | chunks (mean ± stdev, cv%) | supports (mean ± stdev, cv%) | urls cv% |
|---|---|---|---|---:|
| Q1 (벤포벤S 광고비) | **18.54s** ± 4.33 (23.4%) | 6.20 ± 1.30 (21.0%) | 5.40 ± 1.14 (21.1%) | 21.0% |
| Q2 (활성형 비타민 시장) | **18.16s** ± 1.76 (9.7%) | 6.60 ± 1.52 (23.0%) | 7.60 ± 0.89 (11.8%) | 23.0% |
| Q3 (비타민 B군 임상) | **30.58s** ± 4.88 (15.9%) | 11.00 ± 2.35 (21.3%) | 17.80 ± 3.11 (17.5%) | 21.3% |
| Q4 (영어 benfotiamine) | **32.44s** ± 3.56 (11.0%) | 9.40 ± 0.89 (9.5%) | 13.20 ± 3.90 (29.5%) | 9.5% |

## 전체 통계 (N=20)

- elapsed: mean=**24.93s**, stdev=7.64, cv=30.6%, range=[13.75, 37.27]
- chunks: mean=8.30, stdev=2.52, cv=30.3%, range=[5, 14]
- supports: mean=11.00, stdev=5.52, cv=50.1%, range=[4, 22]
- runs: 20 (errors: 0)
- chunks 50%+ 변동 발생: **1건** (Q2 run 2: chunks=8 vs prev_mean=5.0, +60%)

> 전체 cv (30%) 가 쿼리별 cv (10~24%) 보다 큰 이유: 쿼리 그룹 차이 (Q1/Q2 ~18s vs Q3/Q4 ~30s) 가 분산을 부풀림. 쿼리 내 안정성은 양호.

## 변동성 평가

- 쿼리 내 elapsed cv% 평균: **15.0%** (9.7~23.4%)
- 쿼리 내 chunks cv% 평균: **18.7%** (9.5~23.0%)
- 가장 안정적 쿼리: **Q4 (영어 benfotiamine)** — chunks cv 9.5%, elapsed cv 11.0%
- 가장 불안정 (chunks): Q2 — 단 운영상 균질, 50%+ warning 1건
- 가장 불안정 (supports): Q4 — cv 29.5%, run 4 supports=20 단발 outlier
- **한국어 vs 영어**: 영어가 chunks cv 더 낮음 (9.5% vs 21~23%) — vertex 가 영어 grounding 에서 더 deterministic

## Phase B per-run-timeout 산정

- vertex 단독 baseline_mean = **24.93s** (n=20, flash)
- vertex 단독 산식: `max(300, 24.93 × 1.5) = max(300, 37.4) = 300s` — 산식 floor 적용
- 풀파이프라인 추정:
  - 5 sections × (vertex 25s + section_writer LLM 호출 + chroma indexing) ≈ section 당 60~90s
  - 총 run = 5 × 75s = ~375s + warmup overhead
- **권고 per-run-timeout = 480s** (§13-8-3 Sonnet baseline 과 동일 보수치)
- 실제 baseline 측정 후 산식 재적용 권장

## pro 진입 권고

| 항목 | flash (실측) | pro (추정) | 비고 |
|---|---|---|---|
| 단발 mean elapsed | 24.93s | ~50~75s | flash 의 2~3× (Gemini 2.5 시리즈 일반) |
| chunks cv% (쿼리 내) | 18.7% (avg) | ≤20% 예상 | flash 와 유사 가정 |
| per-call cost | ~$0.0001 | ~$0.001~0.002 | output token 33× 가격 |
| N=5 총 cost | ~$0.002 | ~$0.04 | 4q × 5run 합산 |
| N=5 총 시간 | ~25분 | ~40~50분 | inter-sleep 동일 60s |
| per-query timeout 권고 | 120s | **180s** | pro latency 고려 |

**pro 진입 권고**: ✅ 진행 가능. cost 작음 (~$0.04), latency 부담은 inter-sleep 으로 quota 방어. **N=5 동일 권고** (flash cv 와 유사 안정성 가정).

## 결정 데이터 (Phase B 진입 시 사용)

- **per-run-timeout**: 480s (보수치) — 풀파이프라인 baseline 측정 후 산식 재적용
- **N**: 3 (cost 부담 vs cv% 안정성 균형, flash 쿼리 내 cv ≤24% 라 N=3 도 통계 신뢰성 충분)
- **inter-run-sleep**: 60s (§13-7 표준 유지)
- **inter-section-sleep**: 풀파이프라인 측정 시 별도 검토 (vertex quota 방어)
- **모델 후보**:
  - 단일: flash (cost 우선) 또는 pro (품질 우선)
  - 비교: flash + pro 순차 (Phase B 결과로 §14 의사결정)

## 다음 단계 후보

1. **pro 측정 진입** (Phase A 연장, ~40분, $0.04) — flash와 직접 비교 baseline
2. **Phase B 풀파이프라인 진입** (cost 큼, $5~10, 1~2시간) — patch 효과 직접 측정
3. **patch 전 동일성 검증** (1135ac1 checkout, 5분) — Step 1b 가 vertex_search.py 에 무영향 입증
4. **§14-3 sub-task (a) 진입** — `web_results_to_documents` 화이트리스트 확장 → Phase B 측정 시 alt_urls/backend 도 측정 가능

## 박제 commit
| hash | message |
|---|---|
| `1135ac1` | §14-2 Step 1a |
| `d88a8b9` | §14-2 Step 1b (현재 HEAD) |
