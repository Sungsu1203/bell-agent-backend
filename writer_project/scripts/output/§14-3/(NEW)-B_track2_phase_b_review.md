# §14-3 (NEW)-B 트랙 2: §14-2 재검증 박제

본 문서는 §14-3 (NEW)-B 트랙 2 (§14-2 재검증, Phase A/B 측정 자산 재해석) 의 결과 박제.
직전 트랙 1 P-2 close (commit 2d3dd1f) 의 분기 (R) 결정에 따라 진입.

- 작업 일시: 2026-05-16
- 진입 commit: 2d3dd1f (§14-3 (NEW)-B 트랙 1 P-2 close)
- **결론**: 시나리오 (α) 단발 RAG 업데이트 trigger 결정 + 직전 박제 자산 정정 reference 박제

---

## § 1. 측정 메타 + sub-task 1+2 raw 결과

### 1.1 §14-2 박제 자산 위치 식별

| 위치 | 내용 |
|------|------|
| `scripts/output/phase_b/` | 측정 결과 JSON × 6 (5078a2d_run1~3 + ba44637_run1~3) + `phase_b_summary.md` (close 박제) + `phase_b_summary_*.json` + warmup/snapshot/_inner |
| `scripts/output/phase_b_dry_run/` | dry-run 박제 |
| `scripts/output/§14-3/` | 본 트랙 자산 |

### 1.2 §14-2 측정 driver/script

- `scripts/measure_vertex_phase_a.py` (13,413 bytes) — Phase A baseline 측정
- `scripts/dump_vertex_grounding.py` (5,417 bytes) — Phase A 응답 구조 덤프
- `scripts/measure_vertex_phase_b.py` (36,475 bytes) — Phase B 풀파이프라인 driver
- `scripts/_phase_b_run_inner.py` (11,882 bytes) — Phase B subprocess inner
- `scripts/_phase_b_clear_ns.py` (5,793 bytes) — ns reset

### 1.3 §14-2 commit chain (git log raw)

```
2f117ea §14-2 Phase B post-close addendum: 측정 시나리오 명시화
a6bad57 §14-2 Phase B close: 측정 완료, patch in-memory 효과 0 확정
5078a2d §14-2 Phase B: measurement driver + 2-subprocess clear pattern
9fda4ec §14-2 Phase A 박제: vertex baseline + 측정 스크립트
d88a8b9 §14-2 Step 1b: Vertex grounding 결과 통합 정상화  ← 실제 patch
1135ac1 §14-2 Step 1a: Vertex grounding metadata 추출 확장  ← Step 1a baseline
```

---

## § 2. §14-2 commit 식별 정정 (★★★★★)

### 2.1 직전 박제 자산 부정확

`(NEW)-B_option3_code_review.md` § 6.2 / § 9 / commit message 등에 박제된 **"5078a2d vs 1135ac1"** patch 비교 표현 → **부정확**.

### 2.2 정확한 commit 식별 (`phase_b_summary.md` § 1 박제)

| 역할 | commit | 내용 |
|------|--------|------|
| **patch 후** | `5078a2d` | §14-2 Phase B — measurement driver + 2-subprocess clear pattern (d88a8b9 patch 적용 상태 + driver) |
| **patch 전** | `ba44637` | 1135ac1 + driver cherry-pick 임시 commit (detached HEAD, GC 대상) |
| **실제 patch commit** | `d88a8b9` | §14-2 Step 1b — Vertex grounding 결과 통합 정상화 |
| **Step 1a baseline** | `1135ac1` | §14-2 Step 1a — Vertex grounding metadata 추출 확장 |

정확한 patch 비교: **5078a2d (patch 후) vs ba44637 (patch 전, 1135ac1 + driver cherry-pick)**.

---

## § 3. Phase A 가설 기각 (★★★★)

### 3.1 Phase A 코드 박제

**`measure_vertex_phase_a.py`**:
- L41-51: `.env.vertex` only load (`override=True`)
- L53: `from tools.web_rag.vertex_search import vertex_web_search` — **직접 호출**
- `agent/web_search.py:764` SKIP_VERTEX_SEARCH 체크 분기 **미경유**

**`dump_vertex_grounding.py`**: 동일 패턴 (L33 `.env.vertex` only, L40 vertex_web_search 직접 호출).

### 3.2 결론

| 직전 가설 | 결과 |
|----------|------|
| "Phase A 단독 측정의 SKIP_VERTEX 우회 사실 확인 필요" | **기각** |

근거: Phase A 는 `tools/web_rag/vertex_search.py` 의 `vertex_web_search` 함수 직접 호출. agent layer 의 L764 SKIP 분기 우회와 본질적으로 **무관**. Phase A baseline 측정값 (chunks, supports 등) valid (vertex 호출 항상 발생).

---

## § 4. Phase B 재해석 정확화 (★★★★★)

### 4.1 Phase B 코드 박제

**`measure_vertex_phase_b.py`**:
- L53-61: `.env.vertex` only, override=True (driver process)
- L64: `TOPIC_SLUG = "venfobel-vitamin"` hard-coded
- subprocess (`_phase_b_run_inner.py`) 내부에서 graph.invoke → `core.config._load_dotenv_once` 가 글로벌 `.env` load (override=False)

**`topics/venfobel-vitamin.env`** L35: `# SKIP_VERTEX_SEARCH=0` — **주석 처리됨, active 아님**

→ 글로벌 `.env` 의 `SKIP_VERTEX_SEARCH=1` 그대로 활성.

### 4.2 Phase B summary.md 의 결정적 Finding 2

> "graph 가 write 명령 시 web_search 노드 미호출"
> - 매 turn `"write: <섹션명>"` 명시 명령 → supervisor 가 writer 락 잡고 vector_search → section_writer 흐름
> - **web_search 노드 라우팅 분기 미진입**
> - state.references.docs source 100% `file://` PDF (local)
> - `state_dist = {'local': 26}` × 5 runs (vertex_grounding=0, web=0, local=100%)

**Phase B post-close addendum**:
> "vector_search → section_writer 빠른 경로 (의도된 설계), web_search 노드 건너뜀, 이미 임베딩된 자료 전제 (ns_web=0 + ns_local=349 상태)"

### 4.3 정확화 (직전 박제 정정)

| 직전 박제 ((NEW)-B 옵션 3 § 6.2) | 정확화 |
|----------|------|
| "Phase B 재해석: vertex 우회 측정 (SKIP=1 활성)" | **부정확** — vertex_grounding=0 은 SKIP_VERTEX_SEARCH 와 **무관**. **web_search 노드 자체 미진입** (writer-lock 흐름) |
| "Step 1b patch 본 검증 valid 조건 위협" | **부분 확정** — Step 1b patch (`agent/web_search.py:766` 화이트리스트) 가 web_search 노드 코드 → Phase B 시나리오 (write 명령) 에서 **dead path** |

### 4.4 latency 구성 재해석

- 5078a2d 311.41s mean / ba44637 269.76s mean (≒ 사용자 메모리 294.75s 평균값 정합)
- vertex 호출 latency **포함 안 됨** (web_search 노드 미진입)
- vector_search (chromadb local) + section_writer (LLM 7 섹션) latency 중심

---

## § 5. trigger 시나리오 박제 (★★★★)

### 5.1 시나리오별 web_search 노드 진입 차이

| 시나리오 | trigger | web_search 진입 | vertex 호출 |
|---------|---------|----------------|-------------|
| 기존 Phase B | `"write: <섹션명>"` × 7 | ✗ (writer-lock) | ✗ |
| §14-3 (NEW)-B 트랙 1 P-2 | `"최신 자료로 RAG 업데이트해줘"` 단발 | ✓ ★ | ✓ (vertex_grounding=1) |

### 5.2 Phase B summary 의 사전 plan 박제 정합 (★★★★★)

Phase B summary § 7 "§14-3 후보 우선순위 영향" 박제:
> "§14-3 진입 시 우선 트랙 후보 (NEW): web_search 노드 호출 시나리오 발굴 — supervisor 라우팅 / 입력 패턴 / `"research:"` 명령 등. 이게 (a)~(d) 의 효과 측정 전제 조건"

→ P-2 (NEW)-B 트랙 1 실행 결과 (vertex_grounding=1) = Phase B summary 사전 plan 박제 **정합 확정**.

---

## § 6. 시나리오 (α) Phase 3 본 측정 plan 박제

### 6.1 본 미션

§14-2 Step 1b patch (d88a8b9) 본 검증: 5078a2d (patch 후) vs ba44637 (patch 전) 의 vertex_grounding 비교.

### 6.2 시나리오 결정: (α) 단발 RAG 업데이트 trigger

대안 평가:

| 시나리오 | 평가 | 결과 |
|---------|------|------|
| **(α)** 단발 RAG 업데이트 trigger (P-2 패턴 확장) | 직접 측정, P-2 검증 확장, 시간 효율 ★★★, 분석 단순, 변동성 noise 낮음 | **선정** |
| (β) 혼합 시나리오 (RAG 업데이트 → write multi-turn) | e2e valid, 분석 복잡, 시간 ↑↑ | 사후 별도 트랙 후보 |
| (γ) Phase B 그대로 유지 | dead path 측정, 무가치 (양쪽 모두 vertex_grounding=0 예상) | 기각 |

### 6.3 Phase 3 본 측정 plan

- trigger: `"최신 자료로 RAG 업데이트해줘"`
- 측정 환경: `topics/<slug>.env` + `SKIP_VERTEX_SEARCH=0` override (P-2 패턴 정합)
- 측정 토픽: `ai-generated-creative-ad-platforms` (P-2 검증된) 또는 신규 토픽
- N=3 × 2 commit = 6 run
- §13-7 측정 표준 (max_retries=0, warmup 2, timeout, sleep 60s, utf-8) 적용
- 측정 metric: `vertex_grounding` count, `elapsed_sec`, `refs_docs`, `source_dist`

### 6.4 추가 검토 항목

- vertex_grounding count 의 N=3 간 std / CV 측정 (P-2 단일 attempt 의 변동성 분석)
- patch 효과 vs 변동성 noise 분리 분석
- 직전 Phase B 의 §13-7 측정 인프라 (driver / inner / clear) 재사용 가능성 — 그러나 시나리오 변경으로 driver 자체 수정 또는 별도 driver 필요

---

## § 7. Phase 3 본 측정 진입 valid 조건 + 신규 트랙 후보

### 7.1 valid 조건 (확보 완료)

- 시나리오 (α) 단발 RAG 업데이트 trigger 결정 ✓
- web_search 노드 진입 시나리오 + vertex 활성 환경 확보 ✓ (P-2)
- 측정 토픽 + env 파일 (P-2 패턴 정합) 확보 ✓

### 7.2 신규 트랙 후보 (Phase 3 진입 전 또는 병행)

| 트랙 | 미션 | 우선순위 |
|------|------|---------|
| chroma collection_count=0 결함 진단 (P-3 또는 (NEW)-C) | P-2 발견 결함, web_rag.retrieve 가 chroma 에 저장 못 함 | ★★★ Phase 3 신뢰성 |
| (β) 혼합 시나리오 측정 트랙 | 사후 e2e 효과 측정 | (사후) |
| Phase 3 본 측정 driver 작성 | 시나리오 (α) + N=3×2 측정 인프라 | Phase 3 진입 직전 |

### 7.3 직전 박제 자산 정정 reference

- `(NEW)-B_option3_code_review.md` 의 부정확 박제 (§ 2 commit 식별, § 3 Phase A 가설, § 4 Phase B 재해석) 정정 = 본 박제 자산
- `(NEW)-B_option3_code_review.md` 끝에 정정 reference 추가 (본 commit 변경 사항)

---

## 부록 A. 참고 파일

- `scripts/measure_vertex_phase_a.py` (Phase A baseline)
- `scripts/dump_vertex_grounding.py` (Phase A 응답 덤프)
- `scripts/measure_vertex_phase_b.py` (Phase B driver)
- `scripts/_phase_b_run_inner.py` (Phase B inner subprocess)
- `scripts/output/phase_b/phase_b_summary.md` (Phase B close 박제, authoritative)
- `scripts/output/§14-3/(NEW)-B_option3_code_review.md` (옵션 3, 정정 reference 추가됨)
- `scripts/output/§14-3/(NEW)-B_track1_P2_result.md` (트랙 1 P-2 close)
- `topics/venfobel-vitamin.env` (Phase B 측정 토픽, L35 SKIP 주석 처리)
- `.env`, `.env.vertex` (env 흐름 박제)
- `agent/web_search.py:764, 766, 813-814` (SKIP 분기 + Step 1b patch)
