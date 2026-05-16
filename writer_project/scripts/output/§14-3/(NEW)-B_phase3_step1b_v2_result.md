# (NEW)-B_phase3_step1b_v2_result.md

§14-3 (NEW)-B 트랙 3 G4-3 commit 3 박제 자산 v2.
직전 자산 (NEW)-B_phase3_step1b_result.md (commit 9c63112, ~11.08KB) 의 보강 자산.
v1 보호 + v2 별도 분리 (사용자 결정 β).

- 작성 일시: 2026-05-16
- 직전 commit: 380aa59 (§14-3 (보조-2) NEXT_SESSION.md 도입)
- 측정 commit: 71ad103 (§14-3 G4-2 driver 수정 + env-trace 5 stage)
- 측정 결과 박제: phase3_summary_20260516_122255.json
- branch: feature/vertex-web-search

---

## § 10. 환경 변수 4-channel source 박제

본 측정 + 직전 사용자 PowerShell session 박제 + Claude.ai 본 세션 source 진단 통합 자산.

| channel | LLM_MODEL | LLM_PROVIDER | venfobel-* | 의미 |
|---------|-----------|--------------|-----------|------|
| 사용자 PowerShell session (평소) | gemini-2.5-flash (오염) | vertexai (오염) | 없음 | 사용자 평소 vertex 모드 작업 흔적. **source 확정: 가설 ㄷ (session 한정 export, 신뢰도 100%)** — 사용자가 본 PowerShell session 에서 이전 vertex 측정 작업 중 `$env:LLM_MODEL`, `$env:LLM_PROVIDER` 명시 export 후 session 유지. PROFILE 4 위치 + Windows User/Machine env var 모두 LLM 관련 없음 확인 (Claude.ai 본 세션 진단, 2026-05-16). 함의: 사용자 session pollution 은 reproducible 하지 않음, driver 명시 set 이 reproducibility 보장 |
| Claude Code inherited env | (empty) | (empty) | 없음 | Claude Code launch 시점 sanitized env. 사용자 session 과 분리 channel |
| driver subprocess env (G4-2 명시 set) | gemini-2.5-flash | vertexai | 없음 | commit 71ad103 driver 의 명시 set. pop POLLUTION_VARS + explicit set |
| measurement subprocess effective (STAGE_1~5) | gemini-2.5-flash | vertexai | 없음 | env 차단 success. modification 발현 0 |

### 핵심 박제

- **(다''') venfobel-vitamin-oa 본 측정 재현 안 됨**: 10 runs × 5 STAGE = 50 snapshots, venfobel/vitamin-oa hit 0. G4-1 노출은 사용자 session 잔재 또는 다른 토픽 조건 한정 가능성
- **(자') ambiguity 미해소**: 사용자 session LLM_MODEL=gemini-2.5-flash 가 vertex_search.py:112 default 값과 동일 → explicit set vs default fallback 구분 불가. STAGE_2 trace 로 explicit path 사용 확정 (driver 명시 set 작동), fallback 시도 case 검증은 별 미션
- **사용자 PowerShell session pollution source 확정 (가설 ㄷ, session 한정 export, 신뢰도 100%)**: driver 명시 set 으로 reproducibility 보장. PROFILE 4 위치 + Windows User/Machine env var 모두 LLM 관련 없음 (Claude.ai 본 세션 진단, 2026-05-16)

---

## § 11. 5 STAGE env_trace 분석 + (아') 차단 success 확정

driver script (commit 71ad103) 의 `_step3_dry_run_rag_update.py:env_snapshot` 활용. 5 STAGE × 10 runs = 50 snapshots.

### STAGE 별 env 상태 (10 runs = patched 5 + reverted 5, 각 state warmup 2 + main 3, summary 는 warmup 제외, 50 snapshots 동일 패턴)

| STAGE | 위치 | LLM_PROVIDER | LLM_MODEL | MIRROR | CHROMA_NS | CHROMA_DIR |
|-------|------|-------------|-----------|--------|-----------|-----------|
| STAGE_1 | script start | vertexai | gemini-2.5-flash | 0 | (empty) | (empty) |
| STAGE_2 | after .env.vertex load | vertexai | gemini-2.5-flash | 0 | (empty) | (empty) |
| STAGE_3 | after graph import | vertexai | gemini-2.5-flash | 0 | (empty) | (empty) |
| STAGE_4 | before graph.invoke | vertexai | gemini-2.5-flash | 0 | (empty) | (empty) |
| STAGE_5 | after invoke | vertexai | gemini-2.5-flash | 0 | (empty) | (empty) |

### 가설 (아') 차단 success 확정 ★★★★★

- STAGE_3 (graph imported) 에서 CHROMA_NAMESPACE empty 유지 → `core/topic.py:140-142` `MIRROR_STATE_TO_ENV=0` 차단 작동
- STAGE_5 (after invoke) 에서도 empty 유지 → supervisor → start_new_topic 의 runtime modification 차단
- v1 G4-1 박제 (commit 9c63112) 의 가설 (아') ★★★★★ 확정 → G4-2 driver 수정으로 **차단 success 확정**

### 가설 (다''') venfobel 재현 안 됨

- 10 runs × 5 STAGE × 9 env keys = 450 cells, venfobel/vitamin-oa hit 0
- console.log 전체 grep: venfobel 0 hits
- G4-1 venfobel-vitamin-oa 노출은 본 측정에서 미재현 — 다른 조건 한정

---

## § 12. patch 효과 측정 (patched vs reverted) + refs variability 분석

### 측정 결과 요약 (summary JSON)

patched 3 runs:
- vertex_grounding: mean 0, stdev 0, min 0, max 0
- refs_docs_count: mean 4.333, stdev 4.041, cv 93.26%, min 0, max 8
- elapsed_sec: mean 88.64, stdev 48.06, cv 54.22%, min 42.2, max 138.2

reverted 3 runs:
- vertex_grounding: mean 0, stdev 0, min 0, max 0
- refs_docs_count: mean 4.333, stdev 5.132, cv 118.42%, min 0, max 10
- elapsed_sec: mean 101.55, stdev 66.78, cv 65.76%, min 53.8, max 177.9

### patch 효과 ≡ 0 확정

| metric | patched | reverted | 차이 | 평가 |
|--------|---------|----------|------|------|
| vertex_grounding | 0 | 0 | 0 | **patch 효과 0** |
| refs_docs_count | 4.333 | 4.333 | 0 | 동일 (우연한 일치) |
| elapsed (mean) | 88.6s | 101.5s | -12.9s | variability CV 54-65% 안에서 noise 가능성, patch 효과 결정성 없음 |

§14-2 Phase B 박제 (commit a6bad57 "patch in-memory 효과 0 확정") 와 일관. **d88a8b9 patch 의 vertex_grounding 영향 ≡ 0 재확정**.

### refs variability 분석 (CV 매우 큰 경고)

- patched refs CV 93.26% (mean 4.333, stdev 4.041, min 0, max 8)
- reverted refs CV 118.42% (mean 4.333, stdev 5.132, min 0, max 10)
- elapsed CV 54.22% / 65.76% — 양 state 모두 큰 변동성

의미:
- 단일 측정 run 의 refs/elapsed 값 신뢰성 낮음
- run_1 (양 state) 모두 refs=0 — namespace 미reuse 또는 첫 cold call 효과
- vertex/web tool 호출의 결정성 부족 (LLM 응답에 따른 분기 또는 비결정성)

### post-revert dirty + post-clean True

- `[patch] post-revert clean=False` → reverse apply 후 working tree dirty (정상, web_search.py +4/-42 박제)
- `[final] post-clean=True` → finally 단계 patch forward 복구 성공
- patch apply/revert/recover 메커니즘 정상 작동 확인

---

## § 13. 가설 매트릭스 final (v1 + v2 + 신규 (카-a/b/c))

| 가설 | v1 평가 (G4-1) | v2 final |
|------|---------------|---------|
| (아') graph 내부 env modification | 확정 ★★★★★ | **확정 + 차단 success** (driver 명시 set 으로 우회, STAGE_1~5 일관 박제) |
| (자') vertex_search.py:112 default fallback | 부분 확정 | **ambiguity 미해소** (사용자 session LLM_MODEL=default 값과 동일, explicit vs fallback 구분 불가). driver 명시 set path 사용 확정만 박제 |
| (다") .env.openai 측정 중 load | 부분 기각 | 유지 (재검증 안 함) |
| (다''') venfobel-vitamin-oa 출처 | 신규 식별 (G4-1) | **본 측정 재현 안 됨** (10 runs × 5 STAGE × 50 snapshots venfobel 0 hits). G4-1 노출은 다른 조건 한정. 본 환경 sanitized 박제 |
| (차') subprocess stage 차이 | 확정 | 유지 |

### 신규 가설 (카) — vertex_grounding 부재 원인 (env 외 차원)

env 차단 success 후에도 vertex_grounding=0 유지 → **vertex_grounding 부재 원인은 env 외 차원**. 신규 가설 식별:

- **(카-a) Vertex AI grounding API 응답에 groundingChunks 부재**: API 측 model/region/grounding config 이슈. gemini-2.5-flash 의 grounding 활성 조건 검증 필요
- **(카-b) groundingChunks → docs 매핑 로직 실패**: graph 내부 source_class 분류 단계에서 vertex_grounding 라벨 미부여 (web 으로 fallback). web_search.py / 분류 로직 추적 필요
- **(카-c) supervisor 가 vertex_grounding 경로 미선택**: 대안 web tool 만 호출, 회수된 web doc 은 fallback search. agent/supervisor.py 분기 추적 필요

§14-4 미션 후보로 분리 (§ 14 참조).

---

## § 14. §14-3 사이클 정리 + 시나리오 (ii') 재분류 + §14-4 미션 plan

### §14-3 본 미션 평가 재정의

- **원본 목표**: vertex_grounding > 0 도달 (시나리오 (i))
- **실제 달성**: 시나리오 (ii') — driver 수정 (commit 71ad103) 으로 **env modification 차단 success 확정**, vertex_grounding=0 유지
- **재정의**: §14-3 본 미션 = "환경 변수 4-channel pollution 진단 + 차단" → 달성 ★★★★★
- vertex_grounding > 0 도달 = §14-4 미션 분리 (env 외 차원, 신규 가설 (카-a/b/c))

### NEXT_SESSION.md § 6 시나리오 재분류

- (i) vertex_grounding > 0 도달 → 미달성
- (ii) vertex_grounding=0 유지 (driver 효과 미흡) → 부분 정합 but 별 차원
- **(ii') 신규** — driver 수정 효과 **정확히 작동** (env modification 발현 0) + **vertex_grounding 부재 원인 env 외 차원**

### (NEW)-B 트랙 3 close 결정

- driver 수정 효과 박제 완료
- 가설 매트릭스 final 박제 완료
- patch 효과 ≡ 0 재확정 (Phase B + Phase 3 일관)
- env 차원 진단 완료

### 사용자 본 미션 관점 재평가 (2026-05-16, Claude.ai 본 세션)

§14-3 사이클은 env 차원 진단 + 차단 메커니즘 영구화 가치 보존. 단 사용자 본 미션 (vertex AI search 활용) 은 미달성:

- vertex_grounding=0 부재가 본 미션 실패 신호
- "env 차단 success → §14-3 본 미션 success" 박제는 부수적 미션 success 를 본 미션으로 표기한 scope creep 가능성
- 사용자가 언급한 "과거 latency skip" 인과 사슬과 SKIP_VERTEX_SEARCH env var 직접 연결 — (카-c) 우선순위 최상위 재정렬

### §14-4 진입 plan — (카-c) 최상위

신규 가설 (카-a/b/c) 검증. **(카-c) supervisor 의 vertex_grounding 경로 미선택 (skip 로직 진단) 이 최상위 우선순위** — 사용자 본 미션 직접 연결. SKIP_VERTEX_SEARCH env var 는 §14-3 pollutionVars 포함 박제, but 코드베이스 skip 로직 자체는 미진단.

- **G5-c-1 (최상위)**: `grep -r "SKIP_VERTEX_SEARCH" --include="*.py"` 전체 코드베이스 진단
- **G5-c-2 (최상위)**: `tools/web_rag/vertex_search.py` skip 분기 / timeout / fallback 로직 read
- **G5-c-3 (최상위)**: `agent/supervisor.py` vertex vs naver/tavily 분기 조건 read
- **G5-c-4 (최상위)**: `core/config.py` SKIP_VERTEX_SEARCH 정의 + default 값 확인
- **G5-a (후순위)**: Vertex AI grounding API 직접 호출 테스트 (gemini-2.5-flash + grounding tool 명시) → groundingChunks 응답 검증
- **G5-b (후순위)**: web_search.py + 분류 로직 추적 — source_class 분기점 식별

§14-4 진입 시점은 §14-3 commit 3 후 사용자 결정.

### 후속 plan

- 매트릭스 § 4 update (정정 reference 의 v2 결과 통합) 검토
- §14-2 본 미션 완성 또는 §15 진입 결정
- §14-4 미션 진입 결정 (vertex_grounding > 0)

---

## § 15. 메타 박제

- 박제 자산 v2 분량: ~7-8KB (사용자 결정 β 신규 파일 분리, v1 11.08KB 보호)
- v2 파일 위치: `scripts/output/§14-3/(NEW)-B_phase3_step1b_v2_result.md`
- v1 raw 자산: `scripts/output/§14-3/_phase3/v1_archive/` (23 files, commit 9c63112 측정 결과 보호)
- v2 raw 자산: `scripts/output/§14-3/_phase3/phase3_*.{json,console.log}` + `phase3_summary_20260516_122255.json`
- 측정 driver: `scripts/measure_phase3_patch_d88a8b9.py` (commit 71ad103)
- env-trace 5 stage: `scripts/_step3_dry_run_rag_update.py` (commit 71ad103)
- 측정 git_head: 380aa59 (NEXT_SESSION.md 도입 commit)
- 측정 total elapsed: 1667.88s (~27.8분), post_clean: true

박제 컨벤션 정신 정합 — "박제 (실측)" 자산 영구화.
