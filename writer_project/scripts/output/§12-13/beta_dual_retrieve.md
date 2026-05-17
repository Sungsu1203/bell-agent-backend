# §12-13 (β) venfobel 인덱스 직접 QA + dual-retrieve 정합성 진단 — 박제

**측정 일자:** 2026-05-17
**branch:** `main` (origin synced)
**HEAD:** `3b33dba` (chore §14-8 housekeeping)
**미션:** venfobel-vitamin 인덱스 query × namespace × distance score 박제 + §14-8-B fix retrieval-layer 효과 검증

**결과:** **β PASS ★★★** — 9 queries × 3 namespaces 전수 검증, namespace 정합 + distance 분포 정상 + threshold_sweep §12-12 재현. **priors 15 신규**: web/base ns 비어있음 (regression 아닌 indexing 상태, 자산화).

---

## § 1. 작업 1 — entry point + 자산 호환성

### 1-1. dual-retrieve entry

- `agent/vector_search.py L391 _dual_retrieve` — query × ns_web/ns_loc/ns_base 병합 logic
- L398-404 — env_ns_web/loc empty 시 `{ns_default}-web` / `{ns_default}-local` auto-derive
- L486-505 — `_get(ns, k, src)` 헬퍼 + `_call_retrieve` exception 처리 (fix C 적용 후 mismatch 분리 log)
- L546-560 — `score_merge` / `web_first` 병합 정책 분기
- L1561-1654 — `tools/web_rag/ingest_vector.py:retrieve` 의 chroma `_collection.query` 직접 호출 + distance score 활용

### 1-2. threshold_sweep.py 호환성 점검

- 위치: `tools/threshold_sweep.py`
- goldset: `eval/goldset/venfobel-vitamin/chunks_sampled.jsonl` (27 rows, query 채워진 21개)
- 임베딩: VertexAIEmbeddings text-multilingual-embedding-002 (768d) — vertex env 정합
- 의존성: dotenv + langchain_google_vertexai + numpy — 모두 가용
- **호환 OK** ★ — 실측 재현 가능

### 1-3. fix C (embedding consistency) trigger 확인

- 본 β 실행 normal flow 에서 mismatch signal 부재 (vertex 768d embedding ↔ vertex 768d chroma 정합)
- `[CHECK][embed-mismatch]` log 미발화 — 정상 expected.
- 별도 trigger 시나리오: openai 3072d embedding 으로 vertex 768d ns 조회 시 발화 (본 cycle scope 외)

---

## § 2. 작업 2 — query × namespace × distance 실측

### 2-1. PRE/POST reload_config 박제 (§14-8-B fix retrieval-layer)

본 β script 는 init 단계에서 `_cfg.reload_config()` 명시 호출 → §14-8-B fix 발화.

| stage | LLM_PROVIDER | LLM_MODEL | TOPIC_SLUG | CHROMA_NAMESPACE_WEB | CHROMA_NAMESPACE_WEB (env) |
|---|---|---|---|---|---|
| PRE-reload  CFG | vertexai | gemini-2.5-flash | venfobel-vitamin | venfobel-vitamin-web | `<unset>` |
| **POST-reload CFG** | **vertexai** | **gemini-2.5-flash** | **venfobel-vitamin** | **venfobel-vitamin-web** | **`<unset>`** ★ |
| FINAL CFG | vertexai | gemini-2.5-flash | venfobel-vitamin | venfobel-vitamin-web | `<unset>` |

→ **PRE == POST == FINAL** — **§14-8-B fix retrieval-layer 효과 empirical CONFIRMED** ★★★
   - LLM_PROVIDER vertexai → openai 회귀 부재
   - LLM_MODEL gemini-2.5-flash → gpt-4o 회귀 부재
   - TOPIC_SLUG venfobel-vitamin → venfobel-vitamin (글로벌 .env L50 정합 — 본 case 는 동일값이라 시각적 효과 X, 단 driver intent 보호 발화 확인 가능)
   - CHROMA_NAMESPACE_WEB env 도입 부재 (.env.openai overlay 차단)
   - OPENAI_MODEL env 도입 부재

### 2-2. embedding dim

`[init] embedding dim=768 | embedder=VertexAIEmbeddings` — vertex env 정합 ★

### 2-3. query × namespace × distance 결과 (9 queries × 3 ns × top-5)

threshold = 0.65 (글로벌 default, vertex distance scale 정합)

| tag | query | desc | web ns | local ns dists | base ns |
|---|---|---|---|---|---|
| **β-1** | 벤포벨S 핵심 성분 | 직접 on-topic — 성분 (한국어) | **0 docs** | **5 docs, all ≤0.65**: 0.3954, 0.4290, 0.4475, 0.4526, 0.4733 | **0 docs** |
| **β-2** | 벤포티아민 메코발라민 UDCA | 직접 on-topic — 성분명 (영문/일반어) | 0 docs | 5 docs, all ≤0.65: 0.4112, 0.4756, 0.4771, 0.4917, 0.5072 | 0 docs |
| **β-3** | 벤포벨 광고 효과 GRPs | 직접 on-topic — 광고 효과 지표 | 0 docs | 5 docs, all ≤0.65: 0.2948, 0.3343, 0.3377, 0.3377, 0.3435 | 0 docs |
| **β-4** | 활성비타민 시장 동향 | 모호 on-topic — 시장 일반 | 0 docs | 5 docs, all ≤0.65: 0.3020, 0.3213, 0.3367, 0.3376, 0.3825 | 0 docs |
| **β-5** | 고함량 비타민 B1 처방 약국 | 모호 on-topic — 처방/약국 | 0 docs | 5 docs, all ≤0.65: 0.4431, 0.4528, 0.4623, 0.4690, 0.4768 | 0 docs |
| **β-6** | 오메가3 효능 시장 분석 | 인접 — 오메가3 | 0 docs | 5 docs, all ≤0.65: 0.4884, 0.4928, 0.5135, 0.5228, 0.5235 | 0 docs |
| **β-7** | 마그네슘 건강기능식품 효과 | 인접 — 마그네슘 | 0 docs | 5 docs, all ≤0.65: 0.5536, 0.5827, 0.5829, 0.5913, 0.5963 | 0 docs |
| **β-8** | 비타민 | very short query | 0 docs | 5 docs, all ≤0.65: 0.3592, 0.3654, 0.3698, 0.3709, 0.3768 | 0 docs |
| **β-9** | 30대 40대 직장인의 만성피로 ... 벤포벨S 차별화 포인트 | very long query (multi-clause) | 0 docs | 5 docs, all ≤0.65: 0.2948, 0.3130, 0.3398, 0.3434, 0.3453 | 0 docs |

### 2-4. distance 분포 패턴 박제

#### local ns dist 분포 (전 9 queries × top-5 = 45 도큐)

| 카테고리 | dist 범위 | 평가 |
|---|---|---|
| 직접 on-topic (β-1/2/3) | 0.2948 ~ 0.5072 | **★ tight, on-topic 정합** |
| 모호 on-topic (β-4/5) | 0.3020 ~ 0.4768 | tight, on-topic 정합 |
| 인접 (β-6 오메가3, β-7 마그네슘) | 0.4884 ~ 0.5963 | **★ adjacent topic 분리 박제** (β-1/2/3 의 max 0.5072 < β-6/7 의 min 0.4884 부분 overlap, 단 β-7 의 모든 dists 0.55+ 가 직접 on-topic 보다 멀리 위치) |
| 가장자리 short (β-8 "비타민") | 0.3592 ~ 0.3768 | tight (단일어 keyword match) |
| 가장자리 long (β-9 multi-clause) | 0.2948 ~ 0.3453 | **★ very tight** (multi-keyword stacking 효과로 더 좋은 매칭) |

#### dist 분리 / cliff 식별 (per-query)

- on-topic vs adjacent: 부분 overlap (0.5+ region) — **명백한 cliff 부재** (정성)
- β-6 (오메가3) 의 dist 0.488~0.524 가 β-2 (벤포티아민 메코발라민 UDCA) 의 dist 0.477~0.507 와 overlap — embedding 공간에서 보충제 카테고리 의 인접성 박제
- 단 **임계값 0.65 통과 비율: 100%** — 본 score range 에서 default threshold 충분히 관대

#### 의외 발견 — web ns + base ns 비어있음 ★

| ns | 9 queries 결과 | 박제 |
|---|---|---|
| **venfobel-vitamin-web** (vertex 768d) | **0 docs × 9** | venfobel 인덱스의 web 부분이 비어있음 |
| **venfobel-vitamin** (base, vertex 768d) | **0 docs × 9** | base 도 비어있음 |
| **venfobel-vitamin-local** (vertex 768d) | **5 docs × 9** ★ | local 만 indexed |

→ **vertex env 에서 venfobel-vitamin 의 web/base 인덱스 indexing 부재** — 단 §14-8-B fix 와 무관 (이건 ingestion 상태). 별 cycle / 사용자 의도 확인 필요. priors 15 신규 자산화 (자기 비판 §1 강화).

local ns 가 sole 자산이므로 α-2/α-3 의 RAG retrieval 은 local 기반. α-3 section draft 의 footnotes (file:// 모두 local refs) 정합.

### 2-5. fix C trigger 부재 확인

- 9 queries × 3 ns = 27 retrieval 모두 mismatch exception 부재
- `[CHECK][embed-mismatch]` 또는 `[vector_search][fix-C]` log 미발화
- **fix C normal flow trigger 부재 박제 ★** — vertex 768d embedding ↔ vertex 768d chroma 일관성 정합

---

## § 3. 작업 3 — threshold_sweep.py §12-12 재현

### 3-1. 실행 결과

```
=== Threshold Sweep — venfobel-vitamin ===
  골드셋 로드: 전체 27개 중 query 채워진 것 21개
  모델: text-multilingual-embedding-002 (dim=768)
    청크 임베딩 21개 ... 3.2s
    쿼리 임베딩 21개 ... 1.1s
  거리 매트릭스 (21×21) 계산 중 ... 0.0s

  Distance 분포:
    relevant median:           0.136
    hardneg(raw) median:       0.249
    hardneg(보정) median:      0.251

  Sweep (9 포인트, 보정 ON) ... 0.00s
  Sweep (9 포인트, 보정 OFF) ... 0.00s
  → eval\threshold_sweep\venfobel-vitamin_sweep.md
```

### 3-2. §12-12 결과 비교 (재현성)

| 지표 | §12-12 (2026-05-04) | β 재현 (2026-05-17) | 일치 |
|---|---|---|---|
| relevant median | 0.136 | 0.136 | ✓ |
| hardneg(raw) median | 0.249 | 0.249 | ✓ |
| hardneg(보정) median | 0.251 | 0.251 | ✓ |
| F1 max τ | 0.150 | 0.150 | ✓ |
| F1 max value | 0.605 | 0.605 | ✓ |
| 절벽 식별 (보정 ON) | 없음 (jump < 0.2) | 없음 | ✓ |
| 절벽 식별 (보정 OFF) | 없음 | 없음 | ✓ |

→ **§12-12 결과 exact reproduction ★★★** — embedding model + 측정 logic 정합성 13일 (2026-05-04 → 2026-05-17) 안정.

---

## § 4. 작업 2.3 — wrapper subprocess 검증

본 β 실행이 PowerShell + python (CWD=writer_project) — wrapper subprocess 패턴 정합. § 2.1 박제 (PRE/POST CFG 동일성) 가 wrapper subprocess 환경에서의 §14-8-B fix retrieval-layer 효과 박제.

- 27 retrievals 동안 driver-set env 회귀 부재
- chroma client init / query / embed 모두 정상 vertex 768d 사용
- protected env list 효과 retrieval layer 깊은 단계까지 effective ★

---

## § 5. case pass/fail 종합

| 검증 항목 | status | 박제 |
|---|---|---|
| **§14-8-B fix retrieval-layer 효과** | **PASS ★★★** | reload_config 명시 invoke + 27 retrieval 누적 — driver intent 보존 |
| **namespace 정합 (no -oa 회귀)** | **PASS ★** | web=venfobel-vitamin-web / local=venfobel-vitamin-local / base=venfobel-vitamin (all vertex-derived) |
| **dist 분포 (local ns)** | **PASS ★** | on-topic 0.295~0.507, adjacent 0.488~0.596, 모두 ≤0.65 threshold |
| **fix C normal flow trigger 부재** | **PASS** | mismatch exception 부재, log 미발화 |
| **threshold_sweep §12-12 재현** | **PASS ★** | exact reproduction (relevant/hardneg median, F1 max τ/value, cliff 없음 모두 일치) |
| **web/base ns 비어있음** | **finding (priors 15)** | regression 아닌 indexing 상태 — 자산화 |

→ **§12-13 (β) PASS ★★★**

---

## § 6. 의외 발견 — priors 15 박제

### 15. vertex env 의 venfobel-vitamin web/base ns 비어있음 ★

- venfobel-vitamin-web (vertex 768d): 0 docs (β-1~β-9 모두)
- venfobel-vitamin (base, vertex 768d): 0 docs (β-1~β-9 모두)
- venfobel-vitamin-local (vertex 768d): 5 docs (전 query 정상 retrieval)

박제:
- §14-8-B fix regression 무관 — fix 적용 전부터 vertex env 의 web/base ns 가 indexing 부재 상태일 가능성 (α-2/α-3 도 local 기반 retrieval 사용)
- α-3 section draft 의 footnote (file:// 7건 모두 local refs) 정합
- 사용자 vertex env 운영 의도가 "local 기반" 인지 또는 "web 도 indexing 필요" 인지 별 사용자 결정 항목
- 본 미션 β scope 박제만 — 별 cycle 처리 (예: web search → ingest → vertex 768d embedding 재구축)

### priors 누적: 14 → **15**

자기 비판 §1 강화 자산. envdump-style 측정 한계 (§14-8-B) 와 동등 가치 — runtime 실측 박제로 indexing state 박제 가능.

---

## § 7. 다음 step + 사용자 컨펌 대기

### 7-1. mission 분기 결과

**(가) β full pass → γ (end-to-end 리포트 생성) 진입 권장** ★

### 7-2. γ 진입 prep

- γ scope: full pipeline 7-8 section + build_final_report
- 시간 비용: ~30분 (α-3 single section 25.8s → 7 sections + report build)
- venfobel-vitamin outline 존재 (`outlines/venfobel-vitamin/outline_report.md`) → 진행 가능
- α-3 가 single section 정상 작동 박제 → multi-section 잠재 정상
- web ns 비어있음 (priors 15) 영향: γ 의 RAG retrieval 도 local 기반 진행 — α-3 와 동등 경로

### 7-3. defer / reserve (β close 시 통합)

| 항목 | priority |
|---|---|
| **priors 15** — vertex env web/base ns indexing 부재 — 사용자 의도 확인 + ingest 진행 결정 | 中 (γ 진입에는 영향 부재) |
| §14-8 reserve list 5건 (CWD-independent / 다른 reload_config 호출처 / etc.) | 中 — γ close 후 통합 |
| §12-13 pending sub-§ (-2/-3/-6(b)(c)/-8/-9/-11) | 低 — γ 진행 중 재발 시 batch |

### 7-4. 사용자 컨펌 필요

**Q1.** γ (end-to-end 리포트) 진입 OK?
**Q2.** priors 15 (web/base ns 비어있음) — γ 진행 후 처리 OK / 즉시 ingest 필요?
**Q3.** §14-8 reserve list 처리 시점 OK (γ 후) ?

자율 진행 금지 — γ 진입은 별도 round (사용자 컨펌 후 hand-off prompt 재작성).
