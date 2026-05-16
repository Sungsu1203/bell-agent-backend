# §14-8-A raw read B — standalone 6.4s 재현 절차 박제

**read 시점:** 2026-05-16
**git HEAD:** 77c24ad (feature/vertex-web-search)

---

## § B-pre-1 — standalone 6.4s 측정 명령 reference 조사 결과

### 조사 대상 + 결과

| source | 조사 결과 |
|---|---|
| `README-dev.md` | "IMPORT_OK" / "from graph import build_graph" / "self-resolve" → **0건** |
| `README-dev-2.md` | "standalone" 다수 (§14-4 chunks=15 등) — but "IMPORT_OK 6.4s" 직접 명령 **0건** |
| `README-dev-§14.md` | "standalone" 1건 (L202 "standalone 형식 측정 신뢰성 박제") — 명령 **0건** |
| `scripts/output/§14-7/cycle_close_summary.md` § 7 | **유일 reference**: L93 `\| standalone (\`from graph import build_graph\`) \| IMPORT_OK 6.4s \|` |
| `scripts/output/§14-6/` 폴더 | **부재** (폴더 자체 없음) |
| `scripts/output/§14-5/` `§14-4/` `§14-3/` | "standalone" reference 있으나 IMPORT-only 측정 명령 **0건** |
| `git log --all -S "IMPORT_OK"` | **0 commit** (모든 history) |
| `git log --all -S "from graph import build_graph"` | **0 commit** (모든 history — 본 명령 패턴은 git 박제 자산에 없음) |

### 결론

**standalone 6.4s 측정의 정확한 PowerShell wrapper 명령은 박제 자산 + git history 양쪽에 모두 미박제.**

§14-7 close summary § 7 에 `from graph import build_graph` 만 명시되어 있으나, 이를 어떤 wrapper (Measure-Command / time / IPython %time 등) 로 6.4s 측정했는지 unconfirmed.

→ **canonical 명령 + remeasure baseline** 박제 path 진입 (B-3 에서 수행 — user 컨펌 후).

---

## § B-1 — PowerShell .venv_vertex 활성화 절차 박제

### 실측 location

| 항목 | 값 |
|---|---|
| **venv path (실측)** | `D:\gpt_agent\.venv_vertex\` (writer_project 의 **부모** 디렉토리) |
| **활성화 script** | `D:\gpt_agent\.venv_vertex\Scripts\Activate.ps1` |
| **CLAUDE.md 박제** | "PowerShell (Vertex): `.venv_vertex` + `LLM_PROVIDER=vertexai`" (절대 경로 미명시) |

### 사용자 측 활성화 명령 (canonical 추정)

```powershell
# cwd: D:\gpt_agent\writer_project
& "D:\gpt_agent\.venv_vertex\Scripts\Activate.ps1"
# 또는 (writer_project 가 cwd 일 때):
& ..\.venv_vertex\Scripts\Activate.ps1
```

### 활성화 후 env 변동 (PowerShell 기본 동작)

- `$env:VIRTUAL_ENV` = `D:\gpt_agent\.venv_vertex`
- `$env:PATH` = `D:\gpt_agent\.venv_vertex\Scripts;<기존 PATH>`
- `(Get-Command python).Source` → `D:\gpt_agent\.venv_vertex\Scripts\python.exe`

(실측 dump 는 B-4 에서 user 측 측정으로 박제)

### .venv 4개 박제 (실측)

| venv | path |
|---|---|
| .venv_vertex | `D:\gpt_agent\.venv_vertex` |
| .venv_openai | `D:\gpt_agent\.venv_openai` |
| .venv_anthropic | `D:\gpt_agent\.venv_anthropic` |
| .venv_lcl | `D:\gpt_agent\.venv_lcl` |

→ provider 별 venv 격리. CLAUDE.md § Environment 박제와 일치.

---

## § B-2 — .env.vertex 파일 존재 + 내용 박제

### 파일 위치 + 메타

| 항목 | 값 |
|---|---|
| path | `D:\gpt_agent\writer_project\.env.vertex` |
| size | 3284 bytes |
| line count | 51 |
| mtime | 2025-05-09 15:39 |

### `.env` 파일 family (writer_project root)

| file | size | role |
|---|---|---|
| `.env` | 9103 | 글로벌 .env (모든 provider 공통) |
| `.env.vertex` | 3284 | vertex overlay |
| `.env.openai` | 4379 | openai overlay |
| `.env.anthropic` | 4278 | anthropic overlay |
| `.env.bak` | 8920 | backup |

### 자동 로드 메커니즘 (raw_read_graph_env_usage.md § 2 reference)

- `core.config` module-level 에서 `_load_dotenv_once()` 정의
- 함수 내부에서 `load_dotenv(find_dotenv(usecwd=True), override=False)` 호출 (글로벌 .env 로드)
- provider overlay: `_apply_provider_overlay()` 류 함수에서 `LLM_PROVIDER` 값에 따라 `.env.<provider>` 를 `load_dotenv(overlay_path, override=True)` 로 추가 로드
- → **standalone 진입 시 PowerShell shell 의 `$env:LLM_PROVIDER=vertexai` 가 사전 set 되어 있어야 overlay 가 .env.vertex 를 로드**

### .env.vertex 내용 박제 (sensitive 마스킹)

```ini
# 주석 L1-12 생략
LLM_PROVIDER=vertexai                           # L15
LLM_MODEL=gemini-2.5-flash                       # L18

GCP_PROJECT_ID=<masked-gcp-project-id>           # L21
GCP_REGION=us-central1                            # L22
GOOGLE_APPLICATION_CREDENTIALS=D:\GPT_AGENT\writer_project\service_account_vertex.json  # L23

VERTEX_REQUEST_TIMEOUT=120                       # L26
VERTEX_MAX_RETRIES=0                              # L28

GEMINI_EMBEDDING_MODEL=text-multilingual-embedding-002  # L33
RAG_EMBEDDING_MODEL=text-multilingual-embedding-002      # L34
RAG_DISTANCE_THRESHOLD=0.65                              # L36

OPENAI_API_KEY=                                  # L41 (의도적 공백 — vertex 모드에서 OpenAI 경로 차단)
OPENAI_REQUEST_TIMEOUT=10                        # L42
OPENAI_MAX_RETRIES=1                              # L43

# Chroma namespace 라인 L49-51 은 주석 상태 (auto 파생 유지)
```

### **★ 핵심 분기 후보 추가 발견** (B-2 결과)

`.env.vertex` 에 set 되는 var (driver 의 `env["..."] = ...` 명시 set 과 비교):

| var | .env.vertex | driver 명시 set | 차이 |
|---|---|---|---|
| `LLM_PROVIDER` | vertexai | vertexai | 동일 |
| `LLM_MODEL` | gemini-2.5-flash | gemini-2.5-flash | 동일 |
| **`GCP_PROJECT_ID`** | <masked> | **미set** | **★ driver 환경에서 사라질 가능성** |
| **`GCP_REGION`** | us-central1 | **미set** | **★ driver 환경에서 사라질 가능성** |
| **`GOOGLE_APPLICATION_CREDENTIALS`** | D:\GPT_AGENT\writer_project\service_account_vertex.json | **미set** | **★ driver 환경에서 사라질 가능성** |
| **`VERTEX_REQUEST_TIMEOUT`** | 120 | **미set** | ★ |
| **`VERTEX_MAX_RETRIES`** | 0 | **미set** | ★ |
| `OPENAI_API_KEY` | "" (의도적 공백) | **미set** | ★ |
| `RAG_EMBEDDING_MODEL` | text-multilingual-embedding-002 | **미set** | ★ |

→ **driver 의 `os.environ.copy()` 가 standalone shell 의 `.env.vertex` 로드 결과 (즉 `$env:GCP_PROJECT_ID` 등) 를 복사하는지가 분기 핵심**.

- **case A**: driver 가 standalone 과 동일 shell 에서 (.env.vertex 가 이미 로드된 상태에서) `python measure_phase3_patch_d88a8b9.py` 호출 → `os.environ.copy()` 가 .env.vertex 값 포함 → 자식 subprocess 도 동일 var 포함 → **분기 원인 아님**
- **case B**: driver 가 다른 shell / .env.vertex 사전 로드 안 된 상태에서 호출 → `os.environ.copy()` 가 .env.vertex var 미포함 → 자식 subprocess 도 미포함 → 자식이 `from core.config import CFG` 시 .env.vertex 로드는 자식 process 내부에서 진행 (`_load_dotenv_once()`) → 정상이어야 함
- **case C**: driver 가 .env.vertex 사전 로드 + 자식이 또 `_load_dotenv_once()` 호출 → **double load** 발생 → `load_dotenv(override=False)` 라 두 번째는 no-op, but 만약 `override=True` path 거치면 racing 가능

→ B-4 에서 user 측 측정 시 **driver 호출 직전 PowerShell `$env:GCP_PROJECT_ID` 등 .env.vertex var 가 set 되어 있는지** 확인 必.

---

## § B-3 — standalone 측정 명령 (user 컨펌 필요)

### canonical 명령 (B-pre-1 미발견 → 신규 baseline 박제 path)

```powershell
# Step 1: cwd 이동 + venv 활성화 + provider set
cd D:\gpt_agent\writer_project
& D:\gpt_agent\.venv_vertex\Scripts\Activate.ps1
$env:LLM_PROVIDER = "vertexai"

# Step 2: env dump (B-4 자산 동시 박제)
Get-ChildItem env: | ConvertTo-Json | Out-File scripts/output/§14-8/h2_env_standalone.json -Encoding utf8

# Step 3: 측정 3회 (IMPORT-only)
1..3 | ForEach-Object {
    $i = $_
    $sw = [Diagnostics.Stopwatch]::StartNew()
    python -c "from graph import build_graph; print('IMPORT_OK')"
    $sw.Stop()
    "[run $i] elapsed = $($sw.Elapsed.TotalSeconds) s"
} | Tee-Object -FilePath scripts/output/§14-8/standalone_baseline_remeasure.log
```

### 측정 박제 plan

- 3회 측정 → median 박제 (신규 baseline)
- 결과 file: `scripts/output/§14-8/standalone_baseline_remeasure.md`
- 직전 §14-7 close summary 의 "6.4s" 와 비교 (5s ~ 10s 권역 정합 시 baseline 합의)

### user 컨펌 사항

- **Q1.** 위 canonical 명령으로 측정 진행 OK?
- **Q2.** Claude Code 측에서 측정 실행 (PowerShell 도구 사용) 또는 user 측에서 실행?
- **Q3.** invoke 까지 포함 (build_graph 호출 후 graph.invoke) 측정 추가 필요? — **현 박제는 IMPORT-only 만**. invoke 까지 timeout 측정은 별 trace 단계 (H1) 에서 진행.

---

## § B-4 — 측정 시점 $env:* dump (user 컨펌 후 측정)

### dump 대상 var

```powershell
$VARS = @(
    "LLM_PROVIDER", "LLM_MODEL",
    "CHROMA_NAMESPACE", "CHROMA_NAMESPACE_WEB", "CHROMA_NAMESPACE_LOCAL", "CHROMA_DIR",
    "GCP_PROJECT_ID", "GCP_REGION", "GOOGLE_APPLICATION_CREDENTIALS",
    "VERTEX_REQUEST_TIMEOUT", "VERTEX_MAX_RETRIES",
    "OPENAI_API_KEY", "OPENAI_REQUEST_TIMEOUT", "OPENAI_MAX_RETRIES",
    "PYTHONIOENCODING", "PYTHONPATH",
    "VIRTUAL_ENV", "TOPIC_SLUG",
    "SKIP_VERTEX_SEARCH", "MIRROR_STATE_TO_ENV", "LOCAL_RAG_ALLOW_EMPTY"
)
$dump = @{}
foreach ($v in $VARS) { $dump[$v] = (Get-Item "env:$v" -ErrorAction SilentlyContinue).Value }
$dump["__cwd"] = (Get-Location).Path
$dump["__python"] = (Get-Command python).Source
$dump | ConvertTo-Json -Depth 3 | Out-File scripts/output/§14-8/h2_env_standalone.json -Encoding utf8
```

### 박제 자산

- `scripts/output/§14-8/h2_env_standalone.json` — H2 (env diff) 단계 사전 자산
- → driver 측 동일 dump 와 diff 가능 (H2 단계)

---

## § B summary — user 컨펌 요청 사항

| step | 진행 상태 |
|---|---|
| B-pre-1 (reference 조사) | **완료** — 미발견 확정, canonical path 진입 |
| B-pre-2 (graph env usage raw read) | **완료** — `raw_read_graph_env_usage.md` 박제 |
| B-1 (.venv_vertex 활성화 절차) | **완료** — path 박제 |
| B-2 (.env.vertex 내용 박제) | **완료** — driver 미set var 6건 발견 |
| **B-3 (standalone 측정 실행)** | **컨펌 대기** — canonical 명령 박제 only |
| **B-4 (env dump 실행)** | **컨펌 대기** — script 박제 only |

### 사용자 컨펌 Q list

- **Q1.** B-3 canonical 명령 (`python -c "from graph import build_graph; print('IMPORT_OK')"` × 3회 + Stopwatch) 진행 OK?
- **Q2.** 측정 실행 주체 — Claude Code (PowerShell 도구) vs user 측?
- **Q3.** B-4 env dump 실행 — Claude Code vs user? (PowerShell 도구로 가능)
- **Q4.** B-2 § 핵심 발견 — driver 미set var 6건 (GCP_PROJECT_ID 등) 의 분기 후보 (case A/B/C) 박제 합의 OK?
