# §14-7 fix cycle close summary

## § 1. 박제 메타
- branch: feature/vertex-web-search
- commit chain (§14-7):
  - d92394f feat(§14-7): fix vertex_grounding metadata propagation
  - + (NEW) docs(§14-7): close summary + Step 3 timeout 박제
- 진행 일자: 2026-05-16
- 박제 자산 directory: scripts/output/§14-7/

## § 2. cycle 목적
§14-5 cycle 진단 결과 (c'-9-i) CONFIRMED root cause 의 fix path 실행.
- (c'-9-i): agent/web_search.py L1037-1041 hardcode metadata strip
- fix path: fix-γ + fix-α 재부활 완전 fix chain
- 본 미션 (해석-β + γ hybrid) 코드 차원 달성

## § 3. Step 0 사전 검증 박제 (회귀 0)

### S0-1. naver/tavily/Google CSE 의 backend metadata 박제 부재
- search.py L702-711 (Google CSE) + L957 (naver): parsed dict = {title, url, content, raw_content, source} 만
- metadata["backend"] 박제 부재
- → fix-α 의 backend check 가 vertex_grounding only 발화, legacy 회귀 0

### S0-2. strict metadata check 0건
- grep "metadata.keys()" / "metadata == " / "len(metadata)" 0건
- fix-γ 의 metadata 확장 무 영향

### S0-3. L1039 indent = 32 spaces 실측 박제
- 자기 비판 §1 (raw indent cross-check 한계) 교훈 적용
- Claude Code 실측 박제 우선

### S0-4. classify_source 양 파일 정확 위치
- _phase_b_run_inner.py:120 classify_source, callsite L143
- _step3_dry_run_rag_update.py:126 _classify_source, callsite L148

### S0-5. 판정 = α (회귀 0, fix 진입 안전)

## § 4. Step 1+2 fix patch 박제 (commit d92394f)

3 files changed, +11/-5 lines

### fix-γ (agent/web_search.py L1039)
- Before: `metadata={"source": src_disp}`
- After: `metadata={**md, "source": src_disp}`
- 효과: 원본 Document 의 backend / title / content_type / chunk_domain / alt_urls 등 모든 metadata 보존

### fix-α (classify_source 양 파일)
- 시그니처: `def classify_source(src: str, backend: str = "") -> str:`
- 함수 첫 라인: `if backend == "vertex_grounding": return "vertex_grounding"`
- 호출 측: `backend = str(row.get("backend") or ""); key = classify_source(src, backend)`

### fix dependency 박제
- fix-γ 단독: backend metadata 보존, but classify_source 가 URL pattern → "web" → 효과 0
- fix-α 단독: backend check, but state.docs 에 backend 없음 → 효과 0
- ★ fix-γ + fix-α 조합 = 완전 fix chain

## § 5. Step 3 verbose run 박제 — timeout 재발

### S3 결과
- exit: timeout (300s)
- vertex_grounding count: 미측정
- mkey_union: 미측정
- 정량 박제 미달성

### (가-η) 재발 박제 확정
- §14-4 verbose run (15:37 + 17:07): timeout × 2
- §14-6 self-resolve 박제: standalone IMPORT_OK 6.4s
- §14-7 verbose run (20:55): timeout 재발
- ★ §14-6 self-resolve = standalone 환경만 의 transient/partial
- ★ driver subprocess 환경 미해소

### 박제 자산
- scripts/output/§14-7/_verify/phase3_patched_run_1.console.log
- scripts/output/§14-7/_verify/phase3_summary_20260516_210109.json

## § 6. 본 미션 달성 박제 — 코드 차원 완전, runtime 잔여

### (해석-β) production path vertex_grounding > 0
- 코드 차원: ★ (c'-9-i) 의 직접 fix, fix-γ + fix-α 완전 chain
- runtime: 미수행 ((가-η) 차단)

### (해석-γ) grounding annotation 본질 활용
- 코드 차원: ★ L1039 {**md, ...} 가 backend / alt_urls / chunk_domain / title / content_type 모두 보존
- runtime: 미수행

### (해석-β + γ hybrid) — 코드 차원 종결, runtime 검증 = §14-8 의존

## § 7. (가-η) sub-classification 잔여 박제

### standalone 환경 vs driver subprocess 환경
| 환경 | 결과 |
|---|---|
| standalone (`from graph import build_graph`) | IMPORT_OK 6.4s |
| driver subprocess (`measure_phase3_patch_d88a8b9.py`) | 300s timeout |

### 차이점 후보 (sub-classification)
- env vars 차이 (driver set 추가 변수)
- working directory 차이
- PYTHONPATH 차이
- subprocess 의 stdout/stderr capture 차이
- graph chain 풀 호출 시점 (import OK but invoke hang?)

### §14-8 진단 plan (별 cycle)
- H1: driver hang 단계 식별 (env trace / clear / invoke / save 어느 단계?)
- H2: env diff 박제
- H3: mini driver isolation
- 본 미션 verbose 재시도 가능 환경 복귀 = §14-8 close 박제

## § 8. 박제 자산 chain update

- scripts/output/§14-7/cycle_close_summary.md (본 file)
- scripts/output/§14-7/_verify/phase3_patched_run_1.console.log
- scripts/output/§14-7/_verify/phase3_summary_20260516_210109.json
- 기존 §14-3 / §14-4 / §14-5 자산 chain self-contained

## § 9. 후속 cycle entry — §14-8

### §14-8 목적
(가-η) sub-classification 진단 — standalone vs driver subprocess 환경 차이 진단.

### §14-8 entry 조건
- §14-7 close + push 완료 후
- 별 turn entry plan 작성

### §14-8 close 후 진행
- 본 미션 verbose 재시도 가능 환경 복귀
- §14-7 fix patch (d92394f) 의 runtime 정량 박제
- (해석-β + γ hybrid) 완전 달성 박제 최종 종결

## § 10. 학습 자산 박제

### 자기 비판 §1 교훈 적용
- Raw indent cross-check 한계 → Claude Code 실측 read 우선 박제 (S0-3 indent 32-space)
- 본 cycle 에 일관 적용

### fallback plan 정신 부합
- §14-5 turn 사전 박제 fallback plan ("Step 3 hang 시 patch 보존 + commit + 별 cycle 정량 박제")
- §14-7 Step 3 timeout 시 D-3 fallback 직접 적용
- patch revert 미진행, commit 보존, 별 cycle 분리

### 진단/fix 분리 정신
- §14-5 = 진단 cycle (root cause 박제)
- §14-7 = fix cycle (patch 박제)
- §14-8 = 환경 cycle ((가-η) 진단)
- 박제 chain self-contained, 각 cycle 본질 분리

### 사용자 우려 직접 박제
- 사용자 직전 turn 우려 (naver/tavily 영향)
- Step 0 사전 검증으로 회귀 0 박제 직접 해소
- 사용자 우려 → 사전 검증 → 박제 해소 = ★ 협업 박제 정신

## § 11. cycle close 박제

§14-7 fix cycle 박제 종결.
- 코드 차원 본 미션 달성 박제 ★
- runtime 정량 박제 = §14-8 의존
- 박제 자산 chain self-contained

---
end