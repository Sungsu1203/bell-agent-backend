# §14-8-A Test-A/B discriminator 박제

**측정 일자:** 2026-05-16
**git HEAD:** 77c24ad (feature/vertex-web-search)
**측정 환경:** PowerShell 5.1 + `-NoProfile` spawn + `D:\gpt_agent\.venv_vertex`

---

## § 1. 측정 결과 raw (transcribed embed — local *.log 박제 자산 ignore 정책 정합)

### 1-1. Test-A — case A (.env.vertex 사전 로드) 3 runs

```
[run 1] ELAPSED=13.0908032, EXIT=, STDOUT_TAIL=[Config] LLM provider overlay 로드: D:\GPT_AGENT\writer_project\.env.vertex
[Config] 토픽 프리셋 로드: D:\GPT_AGENT\writer_project\topics\venfobel-vitamin.env
IMPORT_OK, STDERR_TAIL=
[run 2] ELAPSED=4.876761, EXIT=, STDOUT_TAIL=[Config] LLM provider overlay 로드: D:\GPT_AGENT\writer_project\.env.vertex
[Config] 토픽 프리셋 로드: D:\GPT_AGENT\writer_project\topics\venfobel-vitamin.env
IMPORT_OK, STDERR_TAIL=
[run 3] ELAPSED=4.9956476, EXIT=, STDOUT_TAIL=[Config] LLM provider overlay 로드: D:\GPT_AGENT\writer_project\.env.vertex
[Config] 토픽 프리셋 로드: D:\GPT_AGENT\writer_project\topics\venfobel-vitamin.env
IMPORT_OK, STDERR_TAIL=
```

| metric | value |
|---|---|
| run 1 (cold) | 13.09s |
| run 2 (warm) | 4.88s |
| run 3 (warm) | 5.00s |
| **median** | **5.00s** |
| IMPORT_OK literal | ★ 박제 OK (R1 fix tempfile 방식 정합) |

### 1-2. Test-B — case B (.env.vertex 미로드 + 명시 Remove-Item) 3 runs

```
[case_b] removed 0 inherited env vars (.env.vertex KEY 일치)
[run 1] ELAPSED=5.1405544, EXIT=, STDOUT_TAIL=[Config] LLM provider overlay 로드: D:\GPT_AGENT\writer_project\.env.openai
[Config] 토픽 프리셋 로드: D:\GPT_AGENT\writer_project\topics\venfobel-vitamin.env
IMPORT_OK, STDERR_TAIL=
[run 2] ELAPSED=4.9188331, EXIT=, STDOUT_TAIL=[Config] LLM provider overlay 로드: D:\GPT_AGENT\writer_project\.env.openai
[Config] 토픽 프리셋 로드: D:\GPT_AGENT\writer_project\topics\venfobel-vitamin.env
IMPORT_OK, STDERR_TAIL=
[run 3] ELAPSED=4.8854173, EXIT=, STDOUT_TAIL=[Config] LLM provider overlay 로드: D:\GPT_AGENT\writer_project\.env.openai
[Config] 토픽 프리셋 로드: D:\GPT_AGENT\writer_project\topics\venfobel-vitamin.env
IMPORT_OK, STDERR_TAIL=
```

| metric | value |
|---|---|
| run 1 | 5.14s |
| run 2 | 4.92s |
| run 3 | 4.89s |
| **median** | **4.92s** |
| IMPORT_OK literal | ★ 박제 OK |
| **removed count** | **0** (.env.vertex 의 12 KEY 중 spawn session 에 미존재) |

### 1-3. removed count 0 의 박제 (사용자 점검 박제 요청 #1)

| .env.vertex KEY | spawn session 사전 상속 여부 | removed |
|---|---|---|
| LLM_PROVIDER | ❌ | — |
| LLM_MODEL | ❌ | — |
| GCP_PROJECT_ID | ❌ | — |
| GCP_REGION | ❌ | — |
| GOOGLE_APPLICATION_CREDENTIALS | ❌ | — |
| VERTEX_REQUEST_TIMEOUT | ❌ | — |
| VERTEX_MAX_RETRIES | ❌ | — |
| GEMINI_EMBEDDING_MODEL | ❌ | — |
| RAG_EMBEDDING_MODEL | ❌ | — |
| RAG_DISTANCE_THRESHOLD | ❌ | — |
| OPENAI_API_KEY | ❌ | — |
| OPENAI_REQUEST_TIMEOUT | ❌ | — |
| OPENAI_MAX_RETRIES | ❌ | — |
| **총** | **0건 상속** | **0 removed** |

→ **`-NoProfile` spawn isolation 이 완전 작동**. user $PROFILE / Windows system-wide env 어디에도 .env.vertex KEY 가 영구 set 되어 있지 않음. case B 의 "미로드" 가정이 그대로 실현됨.

---

## § 2. env_case_a vs env_case_b diff (sensitive 마스킹 적용)

### 2-1. case A only (case B 미존재) — 11건

| KEY | case A value (마스킹 적용) | 출처 |
|---|---|---|
| `LLM_PROVIDER` | `vertexai` | .env.vertex L15 |
| `LLM_MODEL` | `gemini-2.5-flash` | .env.vertex L18 |
| `GCP_PROJECT_ID` | `gem***` (Q3 마스킹: 첫 3자) | .env.vertex L21 |
| `GCP_REGION` | `us-central1` | .env.vertex L22 |
| `GOOGLE_APPLICATION_CREDENTIALS` | `service_account_vertex.json` (Q3 마스킹: 파일명만) | .env.vertex L23 |
| `VERTEX_REQUEST_TIMEOUT` | `120` | .env.vertex L26 |
| `VERTEX_MAX_RETRIES` | `0` | .env.vertex L28 |
| `GEMINI_EMBEDDING_MODEL` | `text-multilingual-embedding-002` | .env.vertex L33 |
| `RAG_EMBEDDING_MODEL` | `text-multilingual-embedding-002` | .env.vertex L34 |
| `OPENAI_REQUEST_TIMEOUT` | `10` | .env.vertex L42 |
| `OPENAI_MAX_RETRIES` | `1` | .env.vertex L43 |

### 2-2. case A only 추가 부재 박제 (.env.vertex 에 있으나 env dump 미표시)

- `OPENAI_API_KEY=` (빈 값) — `Set-Item env:OPENAI_API_KEY -Value ''` 가 effectively 제거된 것으로 보임. PowerShell 5.1 의 known 동작.
- `RAG_DISTANCE_THRESHOLD=0.65` — env dump 에 미관측 (조사 필요. case A 파싱 시 .env.vertex L36 가 정상 로드됐는지 별도 점검)

→ "loaded 12 env vars" 메시지 vs env dump 11건 일치하는데, RAG_DISTANCE_THRESHOLD 가 빠진 것 → env_case_a.json 추가 raw 점검에서 확인 (현재 박제 단계에서는 RAG_DISTANCE_THRESHOLD 가 case A env dump 에 미관측 박제만).

### 2-3. case B only (case A 미존재) — 0건

case A 가 추가 set 한 var 외에는 양 case 동일.

### 2-4. 양 case 공통 (sensitive 영역) — 박제 reference

- `PYTHONPATH = D:\gpt_agent\writer_project` (F4 fix 적용 양쪽 동일)
- `VIRTUAL_ENV = D:\gpt_agent\.venv_vertex` (venv 동일)
- `Path` (PATH) 양쪽 동일 (venv Scripts prepend 동일)
- `DOC_MODE = report`, `SKIP_WEB_SEARCH = 0` 등 system 영구 env 양쪽 동일
- `MAX_SEARCH_QUERIES_PER_ROUND = 2`, `COUNT_PREVIEW_URLS = 0` 등 사용자 setting 양쪽 동일
- `OneDrive`, `USERPROFILE`, `TEMP` 등 Windows 표준 동일

---

## § 3. 분기 판정 — **양쪽 정상 → case B 가설 기각**

### 3-1. 판정표 (user plan 박제 정합)

| 시나리오 | 결과 |
|---|---|
| Test-A 정상 (~6s) + Test-B timeout/지연 → case B 확정 | ❌ 미해당 |
| **양쪽 정상** → case B 기각 → trace 작성 진입 (당초 계획) | **★ 본 case 해당** |
| 양쪽 timeout → standalone path 도 재현 안 됨 → §14-7 fix commit 영향 검증 필요 | ❌ 미해당 |
| Test-A timeout + Test-B 정상 → 역설 (보고 후 재진단) | ❌ 미해당 |

### 3-2. case B 가설 기각 근거

- IMPORT 자체는 case A 5.00s vs case B 4.92s 동등 (Δ = 0.08s, 측정 noise 권역)
- 양쪽 모두 IMPORT_OK literal stdout 박제 ★
- 양쪽 모두 [Config] overlay + 토픽 프리셋 로드 정상 완료
- → **(가-η) IMPORT 거동 분기 root cause 가 env 사전 로드 여부 (case A/B) 가 아님**

### 3-3. 핵심 추가 발견 (case A vs case B STDOUT 차이)

| case | [Config] overlay 로드 |
|---|---|
| case A | `.env.vertex` ★ (shell 측 LLM_PROVIDER=vertexai 가 사전 set → 자식 process 에서 .env 글로벌 로드 후 LLM_PROVIDER 값에 따라 .env.vertex overlay) |
| case B | **`.env.openai`** (★ — shell 측 LLM_PROVIDER 미set → 자식 process 에서 .env 글로벌 의 default LLM_PROVIDER 또는 .env 파일 default 가 openai 로 resolve → .env.openai overlay) |

→ **case B 는 사실상 OpenAI provider 로 IMPORT 됨**. graph 모듈 import 시 vertex 관련 코드 일부 path 가 미실행될 가능성 → IMPORT 시간 단축 효과 일부 있을 수도. 단 양쪽 elapsed 차이 0.08s 권역이므로 IMPORT 단계 자체에서는 provider 별 IMPORT 비용 차이 무시 가능.

---

## § 4. driver-only 차이 잔여 박제 (다음 단계 진단 대상)

본 discriminator 결과로 다음 사실 박제:
- standalone IMPORT 양쪽 ~5s (정상)
- driver subprocess 호출은 300s timeout (§14-7 close summary § 7)
- → **driver-only 분기 원인이 IMPORT 외 단계** 에 존재

### 후보 (사전 raw_read 박제 + 본 discriminator 결과 정합)

1. **build_graph() 호출** (graph.py L60-191) — StateGraph 구성 + node/edge 추가
2. **graph.invoke()** — 실제 RAG pipeline 실행 (vector_search / web_search / LLM call)
3. **driver-side env 의 추가 차이** — driver 의 자식 subprocess 호출 시 `os.environ.copy()` 결과 vs 본 standalone case A/B 의 env 차이 (예: driver 가 추가 set 한 `MIRROR_STATE_TO_ENV=0`, `SKIP_VERTEX_SEARCH=0`, `LOCAL_RAG_ALLOW_EMPTY=1`)
4. **자식 stdout/stderr redirect 차이** — driver 는 binary file handle redirect, standalone 은 console TTY (raw_read_run_single.md § 6 박제)
5. **`_step3_dry_run_rag_update.py` 자체의 추가 부담** — driver 의 자식 script (graph.py 가 아니라 _step3_dry_run_rag_update.py). 본 script 의 IMPORT + main() 까지의 추가 단계

---

## § 5. 다음 단계 권장

### 5-1. 당초 plan 정합: H1 trace 작성 진입

user plan 박제:
- Test-A 정상 + Test-B 정상 → "trace 작성 진입 (당초 계획)"

### 5-2. trace 범위 확장 권장 (★)

본 discriminator 결과 **IMPORT 자체가 정상** 임이 박제됨. 따라서 H1 trace 의 대상은:
- ~~IMPORT 단계만~~ (배제 — 이미 정상 확정)
- **IMPORT 후 단계** (★ 핵심)
  - graph.build_graph() 호출
  - graph.invoke() 호출
  - state references analysis 후 result save

### 5-3. 진단 자산 진입점 변경 권장

- 사전 plan: `_step3_dry_run_rag_update.py` 의 IMPORT 단계 trace
- 본 결과 정합: **`_step3_dry_run_rag_update.py` 의 IMPORT 이후 build_graph + invoke 단계 trace** (STAGE-0 ~ STAGE-N 각 단계 elapsed)
- driver-side (`measure_phase3_patch_d88a8b9.py`) 의 e-4/e-5 trace 는 유지 — 자식 process 진행 + driver timeout kill 의 timing 박제

### 5-4. 추가 진단 후보 (parallel 또는 sequel)

- **Test-C** (선택적) — driver 가 자식을 호출하는 정확한 env 구성 (`POLLUTION_VARS` pop + 명시 set 7개) 을 standalone session 에 재현하여 IMPORT 측정 — driver-only env 차이의 IMPORT 영향 검증
- **Test-D** (선택적) — `_step3_dry_run_rag_update.py` 자체를 standalone 으로 실행하여 IMPORT + main() 진행 측정 — driver wrapper 없이 자식 script 단독 거동 박제

---

## § 6. 박제 자산 chain (§14-8-A 완료 단계)

| asset | 상태 | git 추적 |
|---|---|---|
| `scripts/output/§14-8/raw_read_run_single.md` | ✅ | ★ md (추적) |
| `scripts/output/§14-8/raw_read_graph_env_usage.md` | ✅ | ★ md (추적) |
| `scripts/output/§14-8/raw_read_standalone_repro.md` | ✅ | ★ md (추적) |
| `scripts/output/§14-8/case_a_3runs.log` | ✅ local 박제 | ❌ .log ignore — 본 md § 1-1 transcribed embed |
| `scripts/output/§14-8/case_b_3runs.log` | ✅ local 박제 | ❌ .log ignore — 본 md § 1-2 transcribed embed |
| `scripts/output/§14-8/env_case_a.json` | ✅ local 박제 | ❌ .json ignore — 본 md § 2-1 transcribed (마스킹) |
| `scripts/output/§14-8/env_case_b.json` | ✅ local 박제 | ❌ .json ignore — 본 md § 2-3 (case B only 0건 박제) |
| `scripts/output/§14-8/discriminator_summary.md` | ✅ (본 file) | ★ md (추적) |
| `scripts/diag/§14-8/test_a_case_a_measure.ps1` | ✅ local 박제 | ❌ scripts/diag/ ignore |
| `scripts/diag/§14-8/test_b_case_b_measure.ps1` | ✅ local 박제 | ❌ scripts/diag/ ignore |

---

## § 7. 박제 fix history (실행 중 patch 박제)

| fix | 원인 | 적용 |
|---|---|---|
| **F1 (venv activation)** | `& $VENV_ACTIVATE` 가 sub-scope — caller scope 에 env 미반영 → Windows Store python stub 사용 | `& $VENV_ACTIVATE` → `. $VENV_ACTIVATE` (dot-source) |
| **F2 (§ path 인코딩)** | PowerShell 5.1 의 BOM 없는 UTF-8 .ps1 의 § 를 CP949 로 잘못 디코딩 → `짠14-8` 경로 | `'§14-8'` → `"$([char]0xA7)14-8"` (ASCII escape) |
| **R1 적중 (quote escape)** | `Start-Process -ArgumentList @('-c', "...")` 가 multi-token element 자동 quote 안 함 → python -c 가 첫 토큰 `from` 만 받음 → SyntaxError | tempfile script 방식 (-c 회피) |
| **F4 (sys.path)** | tempfile 이 `%TEMP%` 에 있어 sys.path[0] = tempfile dir → `from graph` 실패 | `$env:PYTHONPATH = $PROJECT_ROOT` + `Start-Process -WorkingDirectory $PROJECT_ROOT` 이중 안전 |

→ 4건 fix 적용 후 양 측정 정상 완료. 박제 자산 chain self-contained.

---

## § 8. user 컨펌 요청 (5건 완료 1회 컨펌)

1. **§ 3.1 분기 판정** — 양쪽 정상 → case B 기각 → trace 작성 진입 합의 OK?
2. **§ 5.2 trace 범위 확장** — IMPORT 만 아니라 **build_graph + invoke 단계 trace** 진입 권장. 합의 OK?
3. **§ 5.4 Test-C / Test-D 추가** — 선택 진입 OK 또는 trace 직행?
4. **§ 7 fix 4건** — 측정 중 patch 적용 박제 합의 OK? .gitignore + 두 스크립트 변경 사항 .git diff 박제 필요?
5. **§ 2-2 RAG_DISTANCE_THRESHOLD 미관측** — case A 의 .env.vertex 파싱 추가 점검 진입 OK 또는 별도 cycle 처리?

본 컨펌 후 §14-8-A 2단계 — H1 trace 작성 (build_graph + invoke 까지 stage trace 박제 범위) 진입.
