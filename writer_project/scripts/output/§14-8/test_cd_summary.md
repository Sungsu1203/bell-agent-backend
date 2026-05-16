# §14-8-A Test-C/D 박제 + 분기 판정 + 다음 단계

**측정 일자:** 2026-05-16
**git HEAD:** 77c24ad (feature/vertex-web-search)
**측정 환경:** PowerShell 5.1 + `-NoProfile` spawn + `D:\gpt_agent\.venv_vertex`
**시간 예산:** 60s/run × 3 runs × 3 tests = 540s 상한

---

## § 1. 측정 결과 raw (transcribed embed — marker 추출 + sensitive 마스킹)

### 1-1. Test-C — driver env 재현 + IMPORT/build_graph 분리

| run | total | import_elapsed | build_elapsed | BUILD_OK |
|---|---|---|---|---|
| 1 (cold) | 5.36s | 4.30s | 0.23s | ✓ |
| 2 (warm) | 5.02s | 4.04s | 0.14s | ✓ |
| 3 (warm) | 4.93s | 3.97s | 0.13s | ✓ |
| **median** | **5.02s** | **4.04s** | **0.14s** | ★ |

**박제**: case A overlay 로드 정합 + 토픽 프리셋 = `ai-generated-creative-ad-platforms.env` (driver 명시 set TOPIC_SLUG 적용 ★)

### 1-2. Test-D1 — driver env 적용 + step3 runpy 호출

| run | total | invoke | summary total | refs_docs | source_dist |
|---|---|---|---|---|---|
| 1 (cold) | 55.42s | 45.14s | 51.61s | 0 | {} |
| 2 (warm) | 24.48s | 14.64s | 20.64s | 0 | {} |
| 3 (warm) | 21.93s | 12.45s | 18.50s | 0 | {} |
| **median** | **24.48s** | **14.64s** | **20.64s** | **0** | **{}** |

**STAGE marker (각 run 공통, _step3_dry_run_rag_update.py 사전 박제 발견 ★)**:
- STAGE_1_script_start: LLM_PROVIDER=vertexai (driver env 적용 박제)
- STAGE_2_dotenv_vertex_loaded: 자식이 .env.vertex 명시 로드
- STAGE_3_graph_imported: SKIP_VERTEX_SEARCH=0 (driver 명시 set 적용)
- STAGE_4_before_invoke
- STAGE_5_after_invoke
- [summary] 최종 박제

**[clear] subprocess**: `_phase_b_clear_ns.py` 호출 정상 (cleared=True, ~1.9s)

### 1-3. Test-D2 — vanilla env + step3 runpy 호출

| run | total | invoke | summary total | refs_docs |
|---|---|---|---|---|
| 1 | 23.79s | 13.02s | 20.22s | 0 |
| 2 | 22.34s | 12.55s | 18.50s | 0 |
| 3 | 23.44s | 13.69s | 19.70s | 0 |
| **median** | **23.44s** | **13.02s** | **19.70s** | **0** |

**STAGE marker 차이 (D1 대비)**:
- STAGE_1: **모든 env empty** (LLM_PROVIDER / TOPIC_SLUG / SKIP_VERTEX_SEARCH 모두 빈 값) — case B Remove-Item 정상 작동 박제 ★
- STAGE_2: **LLM_PROVIDER=vertexai** 자동 set (★ — `_step3_dry_run_rag_update.py` 가 vanilla env 에서도 `.env.vertex` 를 명시 로드 trigger 보유)
- STAGE_3: **TOPIC_SLUG=venfobel-vitamin** (.env 글로벌 default), **SKIP_VERTEX_SEARCH=1** (venfobel-vitamin.env override)
- 즉 D2 는 vanilla 진입 → 자식 script 가 .env.vertex 명시 로드 → 다른 토픽 프리셋 (venfobel-vitamin) 적용 → SKIP_VERTEX_SEARCH=1 로 vertex 우회 path 실행

**R7 박제 (D2 빠른 fail 예상) 기각** ★: D2 도 정상 완료. vanilla env 에서도 자식 script 의 `.env.vertex` 명시 로드 logic 이 vertex 인증 + .env.vertex var 전부 set.

---

## § 2. 분기 판정 — **D1 정상 + D2 정상 → driver wrapper 자체 원인 확정 ★★★**

### 2-1. 판정표 (user plan 박제 정합)

| D1 | D2 | 판정 | 본 case |
|---|---|---|---|
| **정상** | **정상** | **driver wrapper 자체 원인 (subprocess.run + file redirect) → trace driver 측** | **★ 본 case** |
| 정상 | fail (빠른) | wrapper 영향 무 + invoke 가 vertex API 의존 (P2 정합) → fix-path: driver env 보강 | ❌ |
| timeout | timeout | 자식 script 자체 issue (env 무관) → trace 자식 측 dense | ❌ |
| timeout | 정상 | env 차이 원인 (사전 예상 낮음) → env 변수 isolate test | ❌ |
| timeout | fail (빠른) | wrapper 무관 + invoke vertex 의존 + env 영향 양립 → invoke vertex path 진단 | ❌ |

### 2-2. 격차 박제

| measurement | elapsed (median) | 비고 |
|---|---|---|
| Test-A (case A, IMPORT only) | 5.00s | .env.vertex 사전 로드 + standalone IMPORT |
| Test-B (case B, IMPORT only) | 4.92s | vanilla shell + standalone IMPORT |
| Test-C (driver env + build_graph) | 5.02s | + driver 명시 set 7 + build_graph() |
| **Test-D1 (driver env + step3 runpy)** | **24.48s** | invoke 포함 |
| **Test-D2 (vanilla + step3 runpy)** | **23.44s** | invoke 포함 |
| driver subprocess (§14-7) | **300s timeout** | ★ subprocess wrapper 자체가 hang |

→ **driver subprocess wrapper 호출 (300s timeout) vs runpy 직접 호출 (~24s) 의 12× 격차** → wrapper 자체 원인 확정

### 2-3. wrapper 의 hang factor 후보 (다음 단계 trace 대상)

raw_read_run_single.md § 6 의 후보 정합 + 본 결과 sharpening:

| factor | 의심도 | 근거 |
|---|---|---|
| **`stdout=f_log` + `stderr=subprocess.STDOUT` binary file handle redirect** | **★ 高** | runpy 직접 호출 시 stdout/stderr = console TTY 또는 PowerShell tempfile — 정상 24s. driver 는 binary file handle. Python 의 io buffer behavior 차이 가능성 |
| **subprocess.run() 의 timeout 메커니즘** | 中 | timeout=300s 자체가 hang 시킨다기보다는 다른 factor 가 timeout 까지 끌고 가는 구도 |
| **자식의 stderr buffer block** | ★ 高 | stderr 가 stdout 으로 redirect 되어 block-buffered (PEP 7) — 자식이 stderr 에 다량 쓰는 경우 buffer full + driver 가 안 읽으면 block (deadlock 가능) |
| **f_log 파일 핸들 lock / OS-level pipe** | 中 | Windows subprocess.run() 의 file handle redirect 가 OS-level 에서 어떻게 처리되는지 |
| ~~env 구성 차이~~ | ★ 기각 | D1/D2 양쪽 정상 — env 영향 무 |
| ~~working directory~~ | ★ 기각 | runpy 호출도 동일 cwd — 영향 무 |

### 2-4. 추가 발견 박제

**F-D1-1. `_step3_dry_run_rag_update.py` 의 사전 박제 STAGE marker 발견** ★
- STAGE_1_script_start ~ STAGE_5_after_invoke 마커가 이미 production code 에 박제
- raw_read 단계 (B-pre-2) 에서 graph.py 의 transitive 만 확인 → 자식 script 자체의 trace marker 발견 누락 박제
- → 자기 비판 § 4 reference

**F-D1-2. 자식 script 가 .env.vertex 명시 로드 보유 ★**
- D2 (vanilla) STAGE_1: env empty → STAGE_2: LLM_PROVIDER=vertexai
- 즉 `_step3_dry_run_rag_update.py` 가 자체 [env] loaded .env.vertex 호출
- 본 발견은 (가-η) 원인 진단에 영향 없으나, 자식 script 의 env 관리 책임 박제 가치

**F-D1-3. vertex search 비용 1-2s 권역 박제**
- D1 (SKIP=0, vertex search 진행): invoke median 14.64s
- D2 (SKIP=1, vertex 우회): invoke median 13.02s
- Δ = ~1.6s — vertex_web_search 호출 비용

**F-D1-4. refs_docs=0 박제 (양 case 동일)**
- topic = ai-generated-creative-ad-platforms (D1) 또는 venfobel-vitamin (D2) 의 chroma 에 데이터 부재
- → 본 §14-8 진단과 무관 (별도 §14-3 (NEW)-B 이슈)

---

## § 3. 다음 단계 권장 — **trace driver 측 (wrapper hang 진단)**

### 3-1. 진단 대상 (정확화)

`measure_phase3_patch_d88a8b9.py` 의 `run_single()` L155-159 의 `subprocess.run()` 호출:
```python
with open(output_log, "wb") as f_log:
    proc = subprocess.run(
        cmd, env=env, stdout=f_log, stderr=subprocess.STDOUT,
        timeout=config["per_run_timeout"], check=False,
    )
```

### 3-2. trace 작성 plan (당초 H1 trace 의 driver 측 부분 직진)

**diag/§14-8/h1_driver_wrapper_trace.py** (driver 사본):
- `measure_phase3_patch_d88a8b9.py` 사본
- `per_run_timeout = 60`
- L155 직전: `print("[DRIVER-e4-pre] about to subprocess.run", flush=True, file=sys.stderr)`
- L156-159 사이: `subprocess.run` 호출 시 추가 `except TimeoutExpired as e:` 처리 → `e.stdout`/`e.stderr` 출력
- L160 직후: `print("[DRIVER-e5-post] subprocess returned", flush=True, file=sys.stderr)`
- TimeoutExpired catch 시 자식 process group kill + f_log 즉시 close + tail read 박제

**핵심 검증 시그널**:
- driver 가 timeout 시 자식의 f_log tail (마지막 print 단계) 박제 → 자식이 STAGE_1~5 어디까지 도달했는지 확인
- STAGE_5_after_invoke 까지 도달 + driver hang → driver-side cleanup hang (자식은 정상)
- STAGE_5 미도달 → 자식이 wrapper 환경에서만 stuck

### 3-3. 단계화 (당초 plan 정합)

본 §14-8-A 의 다음 단계:
1. **§14-8-A 2단계 (trace 작성)** — `h1_driver_wrapper_trace.py` + `.gitignore` 갱신 무관 (이미 scripts/diag/ 처리)
2. **§14-8-A 3단계 (trace 실행)** — 60s timeout 으로 1회 실행 → tail 박제
3. **§14-8-A 4단계 (분기 판정)**:
   - 자식 STAGE_5 도달 + driver hang → driver cleanup 또는 file close hang
   - 자식 STAGE_X 미도달 → buffer deadlock 가설 (stderr block-buffer + driver 안 읽음)
4. **§14-8-A 5단계 (fix-path)** — 가설 정합 fix 적용

### 3-4. 진단 비용 절감 박제

당초 plan (trace 자식측 build_graph + invoke) 보다 본 결과로 **trace 자식측 불요** 확정:
- 자식 script 는 STAGE marker 보유 + runpy 호출 시 정상 완료
- → trace 는 **driver 측 only** 로 충분

---

## § 4. 자기 비판 박제

### 4-1. raw_read B-pre-2 의 누락 박제

- `raw_read_graph_env_usage.md` § 8 미완 항목에 "core.llm top-level 의 vertex / openai client init 여부 박제" 등 후속 점검 박제했으나, **`_step3_dry_run_rag_update.py` 자체의 env_trace STAGE marker 박제는 raw read 단계에서 미발견**
- 본 발견은 D1 결과로 우연 발견 — raw_read_run_single.md § 7 의 "trace 진입점 변경 권장" 에 자식 script 의 사전 trace 자산 점검 항목 추가가 필요
- → §14-8-Z reserve list 추가: "자식 script (_step3_dry_run_rag_update.py) 의 사전 박제 trace marker 활용 plan 박제"

### 4-2. 진단 priors sharpening 의 점진 기각 박제

| 진단 priors | 박제 | 결과 |
|---|---|---|
| case B (.env.vertex 미로드 driver shell) | "유력" 박제 | 기각 (discriminator_summary § 3-2) |
| C timeout (build_graph hang) | "의외로 유력" 박제 | 기각 (test-C 정상) |
| D2 빠른 fail (vertex 인증 부재) | "예상" 박제 (P2) | 기각 (D2 정상) |
| driver wrapper 자체 원인 | (분기표 1번째 cell) | **★ 확정** |

→ 진단 priors 의 점진 기각 = 측정 신뢰성 + 분기표 모든 cell 동등 가능성 박제 정신 정합

### 4-3. 측정 비용 정합

- Test-A/B + Test-C/D 총 측정 비용: 5runs × ~5s + 3runs × ~5s + 3runs × ~30s + 3runs × ~22s = 약 240s
- 60s timeout 가설 정합 (모든 case 정상 완료, timeout 발동 0건)
- driver subprocess 의 300s timeout 과 본 측정의 60s 격차 → driver wrapper 자체 원인 확정 핵심 근거

---

## § 5. §14-8-Z reserve list (close 시 박제만, 본 cycle 진단 비용 회피)

1. **case A 의 .env.vertex 파싱 12 loaded vs env dump 11건 차이** — PowerShell Set-Item / Get-ChildItem quirk 가능 (Q5 박제)
2. **자식 script (_step3_dry_run_rag_update.py) 의 사전 박제 trace marker 활용 plan 박제** — 본 cycle 4-1 박제
3. **STDOUT 한국어 깨짐** — PowerShell tool → CP949 → UTF-8 디코딩 issue. 박제 자산 가독성 영향. 핵심 marker (ASCII) 박제는 정상.
4. **F-D1-4 refs_docs=0** — 별도 §14-3 (NEW)-B chroma collection_count=0 트랙

---

## § 6. 박제 자산 chain (§14-8-A Test-C/D 완료 단계)

| asset | 상태 | git 추적 |
|---|---|---|
| `scripts/output/§14-8/raw_read_run_single.md` | ✅ | ★ md |
| `scripts/output/§14-8/raw_read_graph_env_usage.md` | ✅ | ★ md |
| `scripts/output/§14-8/raw_read_standalone_repro.md` | ✅ | ★ md |
| `scripts/output/§14-8/discriminator_summary.md` | ✅ | ★ md |
| `scripts/output/§14-8/test_cd_summary.md` | ✅ (본 file) | ★ md |
| `scripts/output/§14-8/case_{a,b,c}_3runs.log` | local | ❌ ignore |
| `scripts/output/§14-8/case_{d1,d2}_3runs.log` | local | ❌ ignore |
| `scripts/output/§14-8/env_case_{a,b,c,d1,d2}.json` | local | ❌ ignore |
| `scripts/diag/§14-8/test_{a,b,c,d1,d2}_*.ps1` | local | ❌ ignore |

---

## § 7. user 컨펌 Q list

**Q1.** § 2.1 분기 판정 — **D1 정상 + D2 정상 → driver wrapper 자체 원인 확정** 합의 OK?

**Q2.** § 2.3 wrapper hang factor — 후보 #1 (binary file handle redirect) + #3 (stderr buffer block) 양쪽 가장 의심. trace 진입 권장 합의?

**Q3.** § 3.2 trace 작성 plan — `h1_driver_wrapper_trace.py` (driver 사본 + TimeoutExpired 처리 + f_log tail 박제). 추가 권장 사항?

**Q4.** § 3.4 — trace 자식측 (build_graph + invoke) **불요 확정** 합의?
- 자식 STAGE marker 이미 보유 + runpy 호출 시 정상 완료
- 자식측 추가 trace 미필요

**Q5.** § 5 reserve list 4건 — 본 cycle close 시 박제만 진행 합의?

본 컨펌 후 §14-8-A 2단계 (h1_driver_wrapper_trace.py 작성) 진입 또는 plan 조정.
