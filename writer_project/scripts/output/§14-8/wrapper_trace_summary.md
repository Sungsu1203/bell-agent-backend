# §14-8-A H1 wrapper trace summary

**측정 일자:** 2026-05-16
**git HEAD:** 77c24ad (feature/vertex-web-search)
**진단 대상:** `measure_phase3_patch_d88a8b9.py` L155-163 의 `subprocess.run()` wrapper
**측정 환경:** PowerShell 5.1 + `-NoProfile` spawn + `.venv_vertex` + .env.vertex 사전 로드 (Test-D1 정합)

---

## § 1. variant A/B/C raw 결과 (transcribed embed)

### 1-1. variant A — stdout=f_log (binary, "wb"), stderr=subprocess.STDOUT (driver 원본)

| metric | value |
|---|---|
| elapsed | 60.02s |
| timed_out | True |
| exit_code | -999 |
| f_log_size | 3320 bytes |
| close_elapsed | 0.000s (★ 즉시 close — #4 cleanup 가설 약화) |

**f_log tail 박제 (last 2000 bytes, decoded):**
```
... [graph] import done. building... | [graph] build_graph done. |
[env_trace] STAGE_3_graph_imported | LLM_PROVIDER = vertexai |
LLM_MODEL = gemini-2.5-flash | TOPIC_SLUG = ai-generated-creative-ad-platforms |
SKIP_VERTEX_SEARCH = 0 | MIRROR_STATE_TO_ENV = 0 |
CHROMA_NAMESPACE =  | CHROMA_NAMESPACE_WEB =  | CHROMA_NAMESPACE_LOCAL =  |
CHROMA_DIR = data/chroma_store |
[invoke] trigger='최신 자료로 RAG 업데이트해줘' |
[env_trace] STAGE_4_before_invoke | ... |
[gcp aiplatform FutureWarning] ...
[langchain VertexAI Deprecation] x2 |
DEBUG: research_round=0, has_refs=False, has_plan=False, rag_on_disk=False,
docs_in_state=0, ns_base=0, ns_web=0, ns_local=0, doc_total=0
```

→ **자식 STAGE_4_before_invoke 도달 + invoke 진입 + DEBUG research_round line** (invoke 내부)

### 1-2. variant B — stdout=PIPE, stderr=PIPE

| metric | value |
|---|---|
| elapsed | 60.05s |
| timed_out | True |
| exit_code | -999 |
| e.stdout_len | 2013 bytes |
| e.stderr_len | 2710 bytes |

**variant-B stdout_tail (last 2000 bytes):**
```
TAGE_1_script_start | ... STAGE_2_dotenv_vertex_loaded | ... [env diag] |
[clear] subprocess: ai-generated-creative-ad-platforms-web --output ... |
[clear] cleared=True elapsed=1.94s |
[graph] importing graph module... |
[Config] LLM provider overlay 로드: .env.vertex |
[Config] 토픽 프리셋 로드: .../topics/ai-generated-creative-ad-platforms.env |
[graph] import done. building... | [graph] build_graph done. |
STAGE_3_graph_imported | ... |
[invoke] trigger='최신 자료로 RAG 업데이트해줘' |
STAGE_4_before_invoke | ...
```

**variant-B stderr_tail (last 2000 bytes) — ★ 결정적 시그널:**
```
... [gcp + langchain deprecation warning chain] ...
DEBUG: research_round=0 ... doc_total=0 |

[web_search] Vertex failed: 404 NOT_FOUND. {'error': {'code': 404, 'message':
'Publisher Model `projects/<gcp-masked>/locations/us-central1/publishers/google/models/gpt-4o`
was not found ...'}} |

[LOCAL RAG] add_web_pages_json_to_chroma(local) 실패: No chunks added for local |

[CHECK][dual-retrieve][count] web=150 (ns=venfobel-vitamin-oa-web)
| local=349 (ns=venfobel-vitamin-oa-local) | base=0 (ns=venfobel-vitamin-oa) |

[CHECK][_call_retrieve][which] retrieve=<function retrieve at 0x...> module=tools.web_rag |

[CHECK][retrieve][args] namespace='venfobel-vitamin-oa-web' collection_name=None
persist_directory='...\chroma_store\venfobel-vitamin-oa-web' top_k=1 |

[CHECK][retrieve] ns=venfobel-vitamin-oa-web dir=... collection_count=150
```

→ **자식이 active progress 중 — invoke 내부 web_search → vertex 404 fail → LOCAL RAG 시도 → dual-retrieve namespace count → retrieve 진입**

### 1-3. variant C — stdout=DEVNULL, stderr=DEVNULL

| metric | value |
|---|---|
| elapsed | 60.03s |
| timed_out | True |
| exit_code | -999 |
| tail | N/A (DEVNULL) |

→ **A/B 와 동일하게 60s timeout. write 부담 완전 제거에도 timeout 발동**

---

## § 2. 자식 STAGE marker 도달 위치 박제 (Q1 추가 박제)

| variant | 자식 STAGE 도달 | 추가 progress 시그널 |
|---|---|---|
| **A** | STAGE_4_before_invoke 통과 | invoke 진입 + DEBUG research_round (invoke 초기) |
| **B** | STAGE_4_before_invoke 통과 | invoke 진입 + **web_search vertex 404 fail** + **dual-retrieve + retrieve 진입** ★ |
| C | (DEVNULL — marker 박제 불가) | — |

### 2-1. 결정적 시그널 — 자식 hang 아님 + active progress

variant-B stderr_tail 의 마지막 line `[CHECK][retrieve] ns=venfobel-vitamin-oa-web ... collection_count=150` → **자식이 active 하게 retrieve subprocess 호출 단계 진입**. hang 시그널 아님.

→ **자식 invoke 가 60s 안에 완료 안 됨**. 단순 timeout 부족 가능성.

### 2-2. variant A vs B 의 progress 차이

- variant A: STAGE_4 + DEBUG research_round 까지 (f_log_size = 3320 bytes)
- variant B: STAGE_4 + 추가 vertex 404 + LOCAL RAG + dual-retrieve + retrieve 진입 (총 stdout+stderr ~4.7KB)

→ **variant B 가 더 깊이 진행** — PIPE 가 file 보다 write 처리량 우월 가능성. 단 양쪽 모두 60s 안 invoke 미완료.

---

## § 3. 분기 판정 — **"역설" cell + 신규 candidate (#10)**

### 3-1. 사전 분기표 (보강-3 박제 정합)

| 결과 패턴 | 본 case 해당? |
|---|---|
| A timeout + B 정상 + C 정상 = #1 (file handle redirect) | ❌ |
| A timeout + B timeout + C 정상 = #2 (stderr buffer block) | ❌ |
| **A timeout + B timeout + C timeout = #3 / #5 / #6** | **★ 본 case** (단 자식 active progress 박제로 #3/#5/#6 sharpening 필요) |
| A 정상 + B 정상 + C 정상 = (역설) | ❌ |
| A 60s 권역 + B/C 60s 권역 = 자식 진행 단계 hang → sweep 진입 | ★ 본 case 정합 (A/B/C 모두 60.0~60.05s timeout) |
| A 정상 + B timeout = (역설) | ❌ |

### 3-2. 사전 candidate 5건 + #6 + 신규 #10 sub-classify

| # | candidate | 박제 판정 |
|---|---|---|
| **#1** | stdout=f_log binary file handle redirect | ★ **기각** — A/B/C 모두 timeout, file handle 차이 무 |
| **#2** | stderr=STDOUT block-buffer + driver 안 읽음 → deadlock | ★ **기각** — variant B (PIPE 별도) 도 timeout |
| **#3** | subprocess.run timeout 메커니즘 자체 (Windows process kill + wait hang) | △ 약화 — TimeoutExpired 정상 발동, close_elapsed=0.000s |
| **#4** | f_log file handle close 시 fsync/cleanup 비용 | ★ **기각** — variant A close_elapsed=0.000s |
| **#5** | 자식 정상 종료 후 driver wrapper 후처리 단계 hang | ★ **기각** — 자식이 active progress 중 (retrieve 단계) — 정상 종료 안 함 |
| **#6** | 자식 stdin 처리 (stdin=None → input() hang) | △ 약화 — 자식이 STAGE_4 + invoke + retrieve 까지 진행 중, stdin 호출 시그널 무 |
| **#10 (신규)** | **wrapper 환경에서 자식 invoke 가 단순히 더 느림** (subprocess.run 의 process boundary + ipc overhead 또는 vertex/network cold start) | **★ 본 case 유력** |

### 3-3. #10 (신규) 박제 근거

| metric | Test-D1 (runpy) | H1 wrapper trace (subprocess.run) |
|---|---|---|
| invoke median | **14.64s** | **60s+ (timeout)** |
| invoke cold | 45.14s | 60s+ (timeout) |
| 자식 STAGE 도달 | STAGE_5_after_invoke | STAGE_4_before_invoke + invoke 내부 progress |
| 자식 완료 시그널 | `[summary] invoke=X.Xs total=Y.Ys [saved] ...` | 부재 (60s timeout 권역에서 retrieve 진행 중) |

→ **wrapper 환경에서 자식 invoke 가 약 4× 느림 (Test-D1 14s → wrapper 60s+)**

### 3-4. (가-η) 의 정확한 root cause 재정의

**기존 (§14-7) 박제**:
- driver subprocess 300s timeout

**본 trace 결과 정합 재정의**:
- driver subprocess wrapper 환경에서 자식 invoke 가 정상 progress 하지만 wrapper-free (runpy) 대비 약 4× 느림
- driver 300s timeout 도 hang 이 아니라 **wrapper 환경에서 자식이 300s 안에도 완료 안 됨** 가능성

### 3-5. 추가 의문 — **자식 wrapper 환경 throughput 저하 원인**

| 가설 | 의심도 |
|---|---|
| **(H-α)** PowerShell `Start-Process` 의 outer wrapper + Python subprocess.run 의 inner wrapper 의 process boundary 누적 | 中 |
| **(H-β)** vertex API call 의 cold start latency (별도 process 마다 새 client init) | ★ 高 (variant-B stderr 의 vertex 404 fail line 박제) |
| **(H-γ)** chroma client 의 collection load latency (별도 process 마다 새 load) | 中 |
| **(H-δ)** wrapper 환경에서 dual-retrieve / fallback path 가 추가 실행 | ★ 高 (variant-B 의 venfobel-vitamin-oa namespace 박제 — 다른 토픽 retrieve) |
| **(H-ε)** wrapper 환경 자체 (file handle redirect, env constraint) 가 자식의 어떤 동작 분기 | 中 |

---

## § 4. 다음 단계 권장 — 보강-4 timeout sweep 진입

### 4-1. variant-A 결과 정합 박제

user plan (Q4) 박제 정합:
> variant-A 정상 → sweep 비용 절감 (skip)
> variant-A timeout → timeout 값 sub-classify → sweep 진입

→ variant-A timeout 발동 → **sweep 진입 OK**

### 4-2. sweep plan

variant-A 만 timeout 30s / 60s / 90s / 120s / 180s 측정:
- 30s: invoke 초기 단계 stop
- 60s: 본 trace 결과 (retrieve 진행 중)
- 90s/120s: 자식 wrapper 환경 throughput 측정 — invoke 완료 시점 박제
- 180s: 만약 120s 도 부족 시 — driver 300s timeout 의 의미 검증

### 4-3. driver 300s timeout 의 의미 재검증 (★ 우선)

**우선 행동**: §14-7 박제 자산 `scripts/output/§14-7/_verify/phase3_patched_run_1.console.log` 의 마지막 line 확인 → driver 자식이 300s 안에 진행한 마지막 단계 박제
- 본 trace 결과 정합 시 driver 자식도 retrieve 단계 이상 도달 진행 중일 가능성
- 만약 STAGE_5_after_invoke 도달 + 그 후 hang → cleanup 단계 hang
- 만약 retrieve / 다른 invoke 단계 정체 → wrapper throughput 저하 가설 강화

이 검증이 sweep 보다 우선 — log 박제 자산 read 만으로 가능 (추가 측정 비용 0).

---

## § 5. 자기 비판 박제

### 5-1. priors sharpening 의 점진 기각 (연속 박제)

| 진단 priors | 결과 |
|---|---|
| case B (.env.vertex 미로드) "유력" | 기각 (discriminator_summary § 3-2) |
| C timeout (build_graph hang) "의외로 유력" | 기각 (test_cd_summary § 2-1) |
| D2 빠른 fail (vertex 인증) "예상" | 기각 (test_cd_summary § 1-3) |
| driver wrapper 자체 원인 #1/#2 "★ 高 의심" | **기각** (본 trace § 3-2) |
| **wrapper 환경 throughput 저하 #10 (신규)** | **★ 본 case 유력** |

→ priors sharpening 의 점진 기각 = 측정 신뢰성 박제 정신 정합

### 5-2. (가-η) root cause 의 측정 비용 정합

- §14-3 ~ §14-7: driver wrapper 가 hang 으로 분류
- §14-8-A discriminator: case B/A 분리 → 기각
- §14-8-A Test-C/D: driver wrapper 자체 원인 확정
- §14-8-A H1 wrapper trace: **자식 invoke 가 wrapper 환경에서 throughput 저하 — hang 아닌 4× 시간 소요**
- 본 박제는 **wrapper 의 의미 자체를 재정의** (hang → throughput 저하)

### 5-3. 측정 자산 reference

| asset | size |
|---|---|
| `scripts/output/§14-8/h1_wrapper_trace.log` | 본 cycle 박제 (local, .log ignore) |
| `scripts/output/§14-7/_verify/phase3_patched_run_1.console.log` | **§14-7 박제 — 본 cycle 검증에 활용 권장** |

---

---

## § 6. #10 sub-classify 통합 박제 (§14-7 + D1 log read 결과)

**진행 순서 박제**: user plan Q3 (sweep 우선) 정합 — read-only 비용 0, sweep 진입 전 우선.

### 6-1. §14-7 phase3_patched_run_1.console.log 결과 (driver subprocess 300s timeout 시)

| metric | value |
|---|---|
| 파일 size | **1073 bytes** |
| line count | 32 |
| 자식 도달 마지막 line | `[graph] importing graph module...` (line 32) |
| STAGE 도달 | **STAGE_2 통과, STAGE_3 미도달** (graph 모듈 import 단계 stuck) |
| vertex 시그널 | **미관측** (graph import 단계에서 stuck) |
| [clear] subprocess | 정상 (cleared=True, 1.98s) |

→ **driver 300s timeout 시 자식이 graph 모듈 transitive import 단계에서 stuck** ★★★

### 6-2. D1 (case_d1_3runs.log) 결과 — vertex 시그널 분석

| run | invoke elapsed | total | summary line | vertex fail 시그널 | 정상 완료 |
|---|---|---|---|---|---|
| 1 (cold) | 45.14s | 51.61s | `[summary] invoke=45.14s total=51.61s refs_docs=0 source_dist={}` | **부재** | ✓ |
| 2 (warm) | 14.64s | 20.64s | `[summary] invoke=14.64s total=20.64s refs_docs=0 source_dist={}` | **부재** | ✓ |
| 3 (warm) | 12.45s | 18.50s | `[summary] invoke=12.45s total=18.50s refs_docs=0 source_dist={}` | **부재** | ✓ |

**D1 stderr 박제 (3 runs 공통)**:
- `gcp aiplatform FutureWarning` (deprecation)
- `LangChain ChatVertexAI / VertexAIEmbeddings Deprecation`
- → **`[web_search] Vertex failed: 404` 시그널 부재 ★**
- `DEBUG: research_round=0, has_refs=False, ... doc_total=0`

### 6-3. 본 H1 trace variant-B 의 결정적 시그널 재박제

**vertex 404 의 model 명시 ★★★**:
```
[web_search] Vertex failed: 404 NOT_FOUND.
{'error': {'code': 404, 'message':
'Publisher Model `projects/<gcp-masked>/locations/us-central1/publishers/google/models/gpt-4o`
was not found ...'}}
```

→ **wrapper subprocess 환경에서 vertex API 가 `gpt-4o` 모델 호출 시도** (gpt-4o = OpenAI 모델, vertex 에 없음 → 404 정상)

### 6-4. 3 측정 종합표

| measurement | 자식 STAGE 도달 | vertex 시그널 | 진행 종결 |
|---|---|---|---|
| **§14-7 driver subprocess** (300s timeout) | **STAGE_3 미도달** (graph import stuck) | 미관측 | hang (graph import 단계) |
| **본 H1 wrapper trace variant-A/B/C** (60s timeout) | STAGE_4 + invoke + retrieve | **vertex 404 for gpt-4o** (variant-B 박제) | 60s timeout (active progress) |
| **D1 runpy** (60s timeout) | STAGE_5_after_invoke + summary + saved | **부재** | **정상 완료** (median 14.64s invoke) |

### 6-5. #10 sub-classify 박제 — **user plan #10-a/-b 정합**

| sub-mechanism | 박제 결과 |
|---|---|
| **#10-a** Python interpreter cold start (subprocess 새 process) | 부분 기여 (~5-10s, 본 trace 의 cold variant 가 5-10s 추가 부담) |
| **#10-b** vertex 404 → dual-retrieve fallback (subprocess 환경에서만 발동) | **★ 본 case 결정적 시그널** — variant-B stderr 박제 |

### 6-6. sub-mechanism (i)/(ii)/(iii) 박제 (user plan Q3 candidate)

| sub | 박제 결과 |
|---|---|
| **(i)** subprocess 환경에서 vertex client cold init → endpoint discovery / auth resolution 차이 → gpt-4o 모델 fallback | △ 가능 — 그러나 직접 코드 trace 미박제 |
| **(ii)** `GOOGLE_APPLICATION_CREDENTIALS` 절대 path 가 subprocess 환경에서 다르게 resolve | ★ 약화 — env_diag GCP_PROJECT_ID + GCP_REGION 정상 박제 + dual-retrieve 까지 진행 |
| **(iii)** Windows subprocess + process group / file handle 차이 → vertex API 호출 path 변동 | △ 가능 — 직접 검증 미박제 |

→ **(i) 가장 유력** — vertex 404 후 자식이 LLM_MODEL fallback path 진입 가능성. 단 정확한 mechanism 은 별도 cycle 박제 필요.

### 6-7. **§14-7 vs 본 H1 trace 의 의외의 차이** (★ 추가 발견)

| metric | §14-7 (driver subprocess 300s) | 본 H1 trace variant-A (subprocess.run 60s) |
|---|---|---|
| wrapper 종류 | `measure_phase3_patch_d88a8b9.py` 의 subprocess.run | `h1_driver_wrapper_trace.py` 의 subprocess.run (동일 API) |
| 자식 도달 | STAGE_3 미도달 (graph import stuck) | STAGE_4 통과 + invoke + retrieve |
| 차이 원인 | **불명** — 동일 wrapper API 인데 다른 행동 |

→ **§14-7 의 graph import 단계 hang 은 본 trace 에서 재현 안 됨** ★
- 시간 차이 (~3 시간 전) 또는 transient 외부 요인 (chroma cold state, vertex auth cache 등) 가능
- → **wrapper hang 이 stochastic / transient 시그널** 가능성 박제

### 6-8. 분기 판정 (user plan Q4 시나리오 정합)

user plan:
> §14-7 + D1 log 모두 vertex 404 + dual-retrieve → #10-b 확정 → fix-path 직행
> D1 vertex 정상 + §14-7 vertex 404 → fix-path 직행 (vertex 404 우회)
> 둘 다 정상이거나 모호 → sweep 진입

**실제 결과**:
- §14-7: vertex 시그널 미관측 (graph import stuck)
- D1: vertex 시그널 부재 + 정상 완료
- **본 H1 trace variant-B: vertex 404 for gpt-4o ★**

→ **분기 시나리오 중 어디에도 정확 매핑 안 됨**. 가장 가까운 시나리오 = "모호 → sweep 진입" 또는 **새 시나리오 "wrapper-specific vertex 404 path 박제" → fix-path 직행 (§14-8-B 별 cycle)**.

### 6-9. 권장 다음 단계

**(우선)**: 본 cycle close — §14-8-A 종결 + 다음 cycle (§14-8-B 또는 별 cycle) 진입 분기

**시나리오 1 (fix-path 직행, sweep skip)**:
- **#10-b (vertex 404 for gpt-4o + dual-retrieve fallback) 확정 박제**
- 별 cycle 진입 — `gpt-4o` 모델이 wrapper 환경에서만 호출되는 origin 코드 진단 (production code grep)
- §14-7 graph import stuck 은 별도 stochastic 요인 박제 (re-occurrence 시 진단)

**시나리오 2 (sweep 진입, timeout sweep 30/60/90/120/180s)**:
- variant-A 만 sweep — 자식이 wrapper 환경에서 결국 완료되는지 박제
- 완료 시 → wrapper 환경 throughput 저하 (slow 하지만 끝남)
- 완료 안 됨 → 진짜 hang (vertex 404 fallback 무한 loop 등)

**시나리오 3 (병행)**:
- sweep + production code grep 동시 진입
- 비용 가장 大

---

## § 6.10 (1-a) recheck 결과 + (1-b) gpt-4o origin grep 통합 박제

### 6.10-A. (1-a) recheck — variant-A 1회 재측정 결과

| metric | 원본 variant-A | recheck variant-A | Δ |
|---|---|---|---|
| inner elapsed | 60.02s | 60.41s | +0.39s |
| outer elapsed | 60.48s | 64.64s | +4.16s (cleanup overhead) |
| f_log size | 3320 bytes | **13042 bytes** | **★ 4× 증가** |
| 자식 도달 | STAGE_4 + invoke + DEBUG research_round | STAGE_4 + invoke + retrieve + **dual-retrieve + chroma embedding mismatch + 추가 retrieve** | **★ 더 깊은 진행** |
| vertex 404 (gpt-4o) | (variant-A f_log 미관측) | (variant-A f_log 미관측) | 동일 |
| close_elapsed | 0.000s | 0.000s | 동일 |

### 6.10-B. **★★★ 핵심 추가 발견 — chroma embedding dimension mismatch** (recheck f_log tail)

```
[CHECK][retrieve] ns=venfobel-vitamin-oa-web ... collection_count=150 |
[CHECK][retrieve] ns=venfobel-vitamin-oa-web ... top_k=1 q_len=26 q_emb_dim=768 |
retrieve 실패(ns='venfobel-vitamin-oa-web'): Vector query failed due to a likely
embedding model/dimension mismatch between ingestion and retrieval.

How to fix:
   • Ensure the SAME embedding model is used for both ingestion and retrieval.
   • If you pass a custom `embedding=` here, it must match the one used to build this collection.
   • Otherwise, omit `embedding` so the vector store's existing embedding function is reused.

[CHECK][_get] src=web ns=venfobel-vitamin-oa-web k=1 raw=0 |
[CHECK][dual-retrieve][peek] k=1 split(web=1,local=0) raw(web=0,local=0) dedupe(web=0,local=0) |
[CHECK][retrieve][args] namespace='venfobel-vitamin-oa' collection_name=None
persist_directory='...\venfobel-vitamin-oa' top_k=1 |
[CHECK][retrieve] ns=venfobel-vitamin-oa ... collection_count=0
```

**해석 박제**:
- **venfobel-vitamin-oa-web namespace 의 chroma collection (count=150)** 은 OpenAI embedding 으로 build (`-oa` = openai)
- **vertex embedding (q_emb_dim=768, vertex text-multilingual-embedding-002)** 으로 retrieve 시도
- → **embedding dimension mismatch** (OpenAI 3072d/1536d vs Vertex 768d)
- chroma client 가 fallback / retry → 시간 소요 → 60s timeout 권역
- 동일 패턴 venfobel-vitamin-oa namespace (collection_count=0) 도 추가 retrieve 시도

### 6.10-C. **★★★ wrapper-specific dual-retrieve trigger** 박제

| measurement | TOPIC_SLUG | retrieve namespace | mismatch 발생? |
|---|---|---|---|
| D1 runpy | ai-generated-creative-ad-platforms | (ai-generated-creative-ad-platforms-web/local, refs_docs=0) | **부재** (정상 완료) |
| H1 wrapper trace (variant-A/B recheck) | ai-generated-creative-ad-platforms | **venfobel-vitamin-oa-web/local/base** ★ | **★ embedding mismatch** |

→ **wrapper subprocess 환경에서만 dual-retrieve 가 venfobel-vitamin-oa namespace 까지 확장** (TOPIC_SLUG 와 다른 namespace)
→ venfobel-vitamin-oa-web 은 OpenAI embedding build, retrieval 은 vertex embedding 시도 → mismatch → fallback chain → 시간 소요

### 6.10-D. (1-b) gpt-4o origin grep 결과

| source | line | 박제 |
|---|---|---|
| **`core/config.py:600`** | `OPENAI_MODEL=_env_str("OPENAI_MODEL", "gpt-4o")` | OpenAI provider 의 default |
| **`core/llm.py:86`** | `out["DefaultChatModel"] = "gpt-4o"` (openai provider 분기) | OpenAI 분기에서만 set |
| **`core/llm.py:138`** | `out["DefaultChatModel"] = "gemini-2.5-flash"` (vertexai provider 분기) | Vertex 분기 정상 default |
| **`app.py:1214`** | `model = os.getenv("OPENAI_MODEL", "gpt-4o")` | app entry default |
| **`tools/web_rag/vertex_search.py:111-112`** | `model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")` | vertex_web_search 정상 default |
| **`agent/web_search.py:50`** | `from core.llm import get_llm` | get_llm 호출 (model 미지정 → CFG 사용) |
| **`agent/web_search.py:192`** | `llm = get_llm()` | (model 인자 무 — CFG resolve) |
| **`agent/web_search.py:766`** | `vertex_result = vertex_web_search(query)` | vertex_web_search 직접 호출 |

**기각**: vertex_web_search 가 gpt-4o origin 가능성 — L112 가 LLM_MODEL or gemini-2.5-flash 정확 fallback. env LLM_MODEL=gemini-2.5-flash 박제 정합.

**유력 후보 (sharpening)**:
- get_llm() 의 fallback chain — vertex provider 시 LLM_MODEL 미인식 또는 CFG 잘못 resolve 시 DefaultChatModel="gpt-4o" 가 끼어들 가능성
- core/llm.py 의 ChatVertexAI 인스턴스화 시 model_name 변수 흐름 (L246-249, L497-499 등) — 본 cycle scope 외, 별 cycle 진단

### 6.10-E. **stochastic 후보 검증** 박제 (user plan Q2 정합)

- 원본 variant-A: STAGE_4 + invoke + DEBUG 까지 (f_log 3320 bytes)
- recheck variant-A: STAGE_4 + invoke + retrieve + dual-retrieve + mismatch + 추가 retrieve (f_log 13042 bytes, **4× 증가**)
- → 동일 wrapper 환경인데 진행도 다름 → **stochastic 후보 검증 합의** (단 1회 재측정으로 단정 보류)
- 가능 mechanism: chroma client cold state / vertex auth cache / 측정 시점 transient

### 6.10-F. (가-η) root cause 재정의 (3차 sharpening)

**1차** (§14-3 ~ §14-7): driver subprocess 300s timeout = hang
**2차** (본 wrapper trace 본문): wrapper 환경 throughput 저하 (#10)
**3차 (본 (1-a)+(1-b) 결과)**: 
- **#10-b**: wrapper subprocess 환경에서 자식이 **dual-retrieve 가 다른 토픽 namespace (venfobel-vitamin-oa) 까지 확장 → embedding dimension mismatch → fallback chain → 시간 소요**
- + (추가) gpt-4o origin path 의 vertex API 호출 (variant-B 박제) — 단 본 (1-a) recheck variant-A 에서는 미관측 (stochastic 가능성)

### 6.10-G. 본 미션 (해석-β + γ hybrid) production path 연결 박제

- §14-7 fix commit (d92394f) = vertex_grounding metadata 전파 fix
- 본 §14-8-A 결과 = vertex_grounding 도구가 실제 호출되기 전 dual-retrieve 단계에서 stuck
- → **vertex_grounding metadata fix 의 runtime 검증이 dual-retrieve mismatch path 에 차단됨**
- 즉 본 §14-8-A 진단이 **본 미션 production path 의 차단점 박제** 와 직결

---

## § 7. user 컨펌 Q list — (1-a) + (1-b) 후 최종 갱신

**Q1.** § 6.10-B/C — **★★★ chroma embedding dimension mismatch + venfobel-vitamin-oa namespace dual-retrieve trigger** 박제 합의 OK?
- 본 발견이 (가-η) root cause 의 **핵심 mechanism** ★

**Q2.** § 6.10-E — **stochastic 후보 검증** (1회 재측정으로 단정 보류, 단 진행도 차이 박제) 합의 OK?

**Q3.** § 6.10-D — gpt-4o origin grep 결과:
- vertex_web_search L112 정상 default 박제 (gpt-4o origin 아님)
- **유력 후보 (별 cycle)**: get_llm() fallback chain + core/llm.py ChatVertexAI 인스턴스화 시 model_name 흐름
- 합의 OK?

**Q4.** § 6.10-F — (가-η) root cause **3차 sharpening**:
- **#10-b 재정의: wrapper subprocess 환경에서 dual-retrieve 가 venfobel-vitamin-oa namespace 까지 확장 → embedding dimension mismatch → fallback chain → 시간 소요**
- 합의 OK?

**Q5.** § 6.10-G — **본 미션 (해석-β + γ hybrid) production path 연결**:
- §14-7 fix (d92394f) 의 runtime 검증이 dual-retrieve mismatch path 에 차단됨
- §14-8-A 진단 = **본 미션 production path 의 차단점 박제** 와 직결
- 합의 OK?

**Q6 (다음 단계)**: 본 cycle close 박제 + §14-8-B 진입 (또는 별 cycle):
- (시나리오 1) **§14-8-A close 박제** + **§14-8-B 진입** — fix-path 설계:
  - fix candidate A: dual-retrieve 의 namespace 결정 logic 진단 + venfobel-vitamin-oa namespace 호출 차단
  - fix candidate B: TOPIC_SLUG 별 namespace 격리 강화
  - fix candidate C: embedding model 일치성 검증 단계 추가
- (시나리오 2) §14-8-A 연장 — dual-retrieve namespace 결정 logic 직접 grep + 진단
- (시나리오 3) 별 cycle (§14-9?) — chroma embedding mismatch 별도 cycle 분리
