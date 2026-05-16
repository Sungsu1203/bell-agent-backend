# §14-8-A close summary

**측정 일자:** 2026-05-16 ~ 2026-05-17
**git HEAD (close 시점):** 77c24ad (feature/vertex-web-search)
**cycle:** §14-8-A — (가-η) sub-classification 진단

---

## § 1. cycle 박제 메타

### 1-1. 미션
- (가-η) standalone (`from graph import build_graph` 6.4s IMPORT_OK) vs driver subprocess (300s timeout) 분기 root cause 진단
- 본 미션 (해석-β + γ hybrid) production path 의 runtime 검증 차단 mechanism 박제

### 1-2. 진행 단계 (raw 확인 + 측정 + 진단)
| 단계 | asset | 결과 |
|---|---|---|
| 1단계 raw 확인 A | raw_read_run_single.md | driver subprocess 호출 패턴 박제 (subprocess.run + stdout=f_log + stderr=STDOUT + TimeoutExpired 미 as e) |
| 1단계 raw 확인 B | raw_read_graph_env_usage.md + raw_read_standalone_repro.md | graph.py ENV 사용 0건 + transitive 후보 박제 + standalone 측정 plan |
| Test-A/B discriminator | discriminator_summary.md | case A/B 양쪽 정상 (~5s) → case B (env 사전 로드 차이) 기각 |
| Test-C/D | test_cd_summary.md | C 정상 (build_graph 0.14s) + D1/D2 정상 (~24s) → driver wrapper 자체 원인 확정 |
| H1 wrapper trace (variant A/B/C) | wrapper_trace_summary.md | A/B/C 모두 60s timeout, 자식 active progress → #10 (wrapper 환경 throughput 저하) |
| §14-7 log + D1 log 통합 박제 | wrapper_trace_summary.md § 6 | §14-7 graph import stuck + D1 vertex 부재 + variant-B vertex 404 |
| (1-a) recheck + (1-b) gpt-4o origin grep | wrapper_trace_summary.md § 6.10 | **★ chroma embedding dimension mismatch + venfobel-vitamin-oa dual-retrieve trigger** |

---

## § 2. root cause 박제 (현재 박제)

### 2-1. (가-η) 3차 sharpening 결과 (Q4 user plan 정합)

| 차 | 박제 |
|---|---|
| 1차 (§14-3 ~ §14-7) | driver subprocess 300s timeout = hang |
| 2차 (wrapper_trace 본문) | wrapper 환경 throughput 저하 (#10) |
| **3차 (현재 박제)** | **wrapper subprocess 환경에서 dual-retrieve 가 venfobel-vitamin-oa namespace 까지 확장 → embedding dimension mismatch (OpenAI build vs Vertex retrieve 768d) → fallback chain → 시간 소요** |

→ "dominant vs contributing" 단정 보류 (Q4 정합). 단 본 미션 차단점 명확.

### 2-2. 결정적 시그널 박제

**시그널 1**: H1 wrapper trace recheck f_log tail (13042 bytes):
```
retrieve 실패(ns='venfobel-vitamin-oa-web'): Vector query failed due to a likely
embedding model/dimension mismatch between ingestion and retrieval.
```

**시그널 2**: H1 wrapper trace variant-B stderr_tail:
```
[CHECK][dual-retrieve][count] web=150 (ns=venfobel-vitamin-oa-web) |
local=349 (ns=venfobel-vitamin-oa-local) | base=0 (ns=venfobel-vitamin-oa)
```

→ TOPIC_SLUG=ai-generated-creative-ad-platforms 임에도 venfobel-vitamin-oa namespace 까지 dual-retrieve 확장.

### 2-3. 본 미션 (해석-β + γ hybrid) production path 차단점

- §14-7 fix commit (d92394f) = vertex_grounding metadata propagation fix
- 본 §14-8-A 결과 = vertex_grounding 도구가 실제 호출되기 **전** dual-retrieve 단계에서 stuck
- → **vertex_grounding metadata fix 의 runtime 검증이 dual-retrieve mismatch path 에 차단됨**
- §14-8-A 진단 자산이 **본 미션 fix-path 직접 지원**

---

## § 3. 박제 자산 chain (8건 self-contained)

| # | asset | role | git |
|---|---|---|---|
| 1 | `scripts/output/§14-8/raw_read_run_single.md` | driver L108-192 subprocess 호출 패턴 박제 | ★ md |
| 2 | `scripts/output/§14-8/raw_read_graph_env_usage.md` | graph.py ENV 사용 0 + transitive 후보 박제 | ★ md |
| 3 | `scripts/output/§14-8/raw_read_standalone_repro.md` | standalone 6.4s 측정 명령 + .env.vertex + .venv_vertex 박제 | ★ md |
| 4 | `scripts/output/§14-8/discriminator_summary.md` | Test-A/B (case B 기각) | ★ md |
| 5 | `scripts/output/§14-8/test_cd_summary.md` | Test-C/D (driver wrapper 자체 원인 확정) | ★ md |
| 6 | `scripts/output/§14-8/wrapper_trace_summary.md` | H1 wrapper trace + §14-7/D1 log 통합 + (1-a)+(1-b) | ★ md |
| 7 | `scripts/output/§14-8/§14-8-A_close_summary.md` | 본 file — cycle close 박제 | ★ md |
| 8 | local *.log + *.json | case_{a,b,c,d1,d2}, env_case_{a,b,c,d1,d2}, h1_wrapper_trace, h1_wrapper_trace_recheck | ❌ (transcribed embed) |

추가 측정 인프라 (local-only):
- `scripts/diag/§14-8/test_{a,b,c,d1,d2}_*.ps1` (5건)
- `scripts/diag/§14-8/h1_driver_wrapper_trace.py` + `run_h1_wrapper_trace.ps1` + `run_h1_recheck.ps1`

---

## § 4. priors 기각 박제 (6건)

| # | priors | 박제 결과 |
|---|---|---|
| 1 | case B (.env.vertex 미로드 driver shell) "유력" | 기각 (discriminator_summary § 3-2) |
| 2 | C timeout (build_graph hang) "의외로 유력" | 기각 (test_cd_summary § 2-1, build_elapsed 0.14s) |
| 3 | D2 빠른 fail (vertex 인증 부재 P2) "예상" | 기각 (test_cd_summary § 1-3, D2 정상 완료) |
| 4 | driver wrapper #1/#2 (file handle / stderr buffer) "高 의심" | 기각 (wrapper_trace § 3-2, A/B/C 모두 timeout) |
| 5 | vertex 404 for gpt-4o (분기표 cover 영역 외) | **신규 발견** (variant-B stderr, gpt-4o origin grep 진행 중) |
| 6 | chroma embedding mismatch (분기표 cover 영역 외 2회) | **신규 발견** (recheck f_log) |

### 4-1. 자기 비판 강화 박제 (분기표 cover 영역 외 시그널 2회 발생)

- 측정 전 분기표 가설 공간 sharpening 으로 좁아질수록, actual cause 가 그 공간 밖에 있을 위험 누적
- 본 cycle: 5번 (vertex 404) + 6번 (chroma mismatch) 모두 분기표 외 시그널
- 향후 cycle: 분기표 작성 시 "이 분기표 밖" cell 명시 + 첫 측정 후 cover 영역 외 시그널 확인

---

## § 5. reserve list (6건 — §14-8 close 시 후속 cycle enqueue)

| # | 항목 | 진단 비용 / 우선순위 |
|---|---|---|
| 1 | **§14-7 graph import stuck 재현** (driver subprocess 300s vs 본 H1 trace 60s 행동 차이) | stochastic 가능성 검증 — 별 cycle 또는 §14-8-B 진입 후 추가 측정 |
| 2 | **stochastic 후보 검증 추가 측정** (variant-A 다회 측정) | wrapper hang 의 stochastic vs systematic 분리 |
| 3 | **gpt-4o origin (get_llm fallback chain)** | 별 cycle — core/llm.py L246-249/L497-499 의 model_name 변수 흐름 |
| 4 | **case A 의 12 loaded vs env dump 11건 차이** (PowerShell Set-Item / Get-ChildItem quirk) | 낮은 우선순위 |
| 5 | **STDOUT 한국어 깨짐** (PowerShell CP949 ↔ UTF-8 디코딩) | 낮은 우선순위, 박제 자산 가독성 영향 |
| 6 | **refs_docs=0** (별 §14-3 (NEW)-B chroma collection_count=0 트랙) | 별 cycle 진행 중 |

---

## § 6. 본 cycle 측정 비용 박제

| measurement | 비용 |
|---|---|
| Test-A/B (case A/B IMPORT) | ~5s × 6 = 30s |
| Test-C (build_graph) | ~5s × 3 = 15s |
| Test-D1/D2 (runpy step3) | ~25s × 6 = 150s |
| H1 wrapper trace (variant A/B/C) | 60s × 3 = 180s |
| H1 recheck (variant-A) | 60s |
| **총 측정 비용** | **약 435s (7.25분)** |
| 박제 자산 작성 비용 | (Claude Code 측 read/write/edit) |

→ §14-7 cycle 의 300s timeout 1회 measurement 대비 효율적 진단 (priors 점진 기각 + 신규 cause 박제)

---

## § 7. §14-8-B 진입 plan (Q6 user plan 정합)

### 7-1. B-1 (첫 단계) — **dual-retrieve namespace 결정 logic grep**

**대상**:
- `tools/web_rag/` 영역 (retrieve.py / search.py / 기타 retrieve 함수)
- `agent/web_search.py` (dual-retrieve 호출처)
- `core/config.py` (CHROMA_NAMESPACE / RAG_NAMESPACE 관련)
- 자식 script (`_step3_dry_run_rag_update.py`) 의 retrieve 호출처

**박제 대상**:
- venfobel-vitamin-oa namespace 가 어디서 결정되는가
- TOPIC_SLUG 와 다른 namespace 의 결정 logic
- fallback chain 의 진입 조건
- embedding model 호환성 검증 부재 지점

**박제 → `scripts/output/§14-8/B-1_dual_retrieve_namespace_grep.md`**

### 7-2. B-2 ~ B-5 (B-1 결과 후 사용자 컨펌)

| 단계 | 내용 |
|---|---|
| B-2 | fix patch 설계 (3 candidate) |
| B-3 | patch 적용 (production code edit, 사용자 컨펌 후) |
| B-4 | patched driver 재측정 (variant-A 1회 + driver 측정 1회) |
| B-5 | runtime 검증 + 본 미션 (해석-β + γ hybrid) 정량 박제 |

### 7-3. fix candidate (B-2 사전 박제)

- **fix candidate A**: dual-retrieve 의 namespace 결정 logic 진단 + venfobel-vitamin-oa namespace 호출 차단
- **fix candidate B**: TOPIC_SLUG 별 namespace 격리 강화
- **fix candidate C**: embedding model 일치성 검증 단계 추가

---

## § 8. cycle close 박제

§14-8-A cycle 박제 종결.
- root cause = wrapper subprocess 환경에서 dual-retrieve namespace 확장 → chroma embedding dimension mismatch → fallback chain → 시간 소요 (현재 박제)
- 자산 chain 8건 self-contained
- priors 6건 기각 (분기표 cover 영역 외 2회 발견 = 자기 비판 강화 박제)
- reserve list 6건 후속 cycle enqueue
- **본 미션 (해석-β + γ hybrid) production path 차단점 박제** ★
- §14-8-B 진입 — fix-path 설계 + 적용

---

end
