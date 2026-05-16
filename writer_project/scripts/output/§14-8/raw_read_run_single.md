# §14-8-A raw read A — `run_single` subprocess 호출 패턴 박제

**source:** `writer_project/scripts/measure_phase3_patch_d88a8b9.py` L108-192
**read 시점:** 2026-05-16
**git HEAD:** 77c24ad (feature/vertex-web-search)

---

## 1. 함수 시그니처 + 진입 stage

| line | 내용 |
|---|---|
| L108 | `def run_single(state_label: str, run_id: str, config: dict, output_dir: Path) -> dict:` |
| L110-111 | output_json / output_log path 계산 |

## 2. env 구성 (sub-stage e-1 ~ e-3)

| sub | line | 행위 | 메모 |
|---|---|---|---|
| **e-1** | L113 | `env = os.environ.copy()` | **driver 현재 env 전체 상속 — standalone 과 동등한 출발점** |
| **e-2** | L117-124 | POLLUTION_VARS pop (`CHROMA_NAMESPACE`, `CHROMA_NAMESPACE_WEB`, `CHROMA_NAMESPACE_LOCAL`, `CHROMA_DIR`) | standalone shell 에는 이 unset 행위 없음 → **분기 후보 #1** |
| **e-3** | L126-134 | 명시 set: `PYTHONIOENCODING=utf-8`, `LOCAL_RAG_ALLOW_EMPTY=1`, `TOPIC_SLUG=<slug>`, `LLM_PROVIDER=vertexai`, `LLM_MODEL=gemini-2.5-flash`, `SKIP_VERTEX_SEARCH=0`, `MIRROR_STATE_TO_ENV=0` | standalone 의 `.env.vertex` 자동 로드와 **var 집합이 동일한지 미확정** → **분기 후보 #2** |

L136-140: driver-side env trace print (stdout, flush=True). 박제 OK.

## 3. cmd 구성 (sub-stage e-3b)

| line | 내용 |
|---|---|
| L142-149 | `cmd = [sys.executable, str(DRY_RUN_SCRIPT), "--topic-slug", ..., "--topic-title", ..., "--trigger", ..., "--output", str(output_json), "--recursion-limit", str(config["recursion_limit"])]` |
| L36 | `DRY_RUN_SCRIPT = PROJECT_ROOT / "scripts" / "_step3_dry_run_rag_update.py"` |

→ **자식 process = `_step3_dry_run_rag_update.py`** (IMPORT trigger 지점 확정)

## 4. subprocess 호출 (sub-stage e-4 / e-5) — **핵심 박제**

| sub | line | 내용 |
|---|---|---|
| **e-4 (호출 직전)** | L151 | `t_start = time.monotonic()` |
| | L152 | `timeout_flag = False` |
| | L153 | `exit_code: int = -999` |
| | L154 | `try:` |
| | L155 | `with open(output_log, "wb") as f_log:` |
| | L156-159 | `proc = subprocess.run(cmd, env=env, stdout=f_log, stderr=subprocess.STDOUT, timeout=config["per_run_timeout"], check=False,)` |
| **e-5 (수신 직후)** | L160 | `exit_code = proc.returncode` (정상 종료 경로) |
| | L161 | `except subprocess.TimeoutExpired:` |
| | L162 | `timeout_flag = True` |
| | L163 | `exit_code = -1` |

### 4-1. subprocess 호출 파라미터 박제

- **호출 API**: `subprocess.run()` (Popen 직접 호출 아님)
- **`capture_output`**: ❌ 사용 안 함
- **`stdout`**: `f_log` (파일 핸들, binary "wb" 모드)
- **`stderr`**: `subprocess.STDOUT` → **stderr 가 stdout 으로 redirect 되어 동일 파일에 들어감**
- **`timeout`**: `config["per_run_timeout"]` (DEFAULTS = **300.0s**)
- **`check`**: `False` (non-zero exit 도 raise 안 함)
- **`encoding`/`text`**: 미지정 → binary mode (파일 핸들이 "wb")

### 4-2. TimeoutExpired exception handling 박제 — **핵심 결함 확인**

```python
except subprocess.TimeoutExpired:
    timeout_flag = True
    exit_code = -1
```

- **`as e:` 미사용** → `TimeoutExpired` instance 의 `e.stdout` / `e.stderr` 접근 불가
- **`e.stdout` / `e.stderr` 출력 처리 全無** → timeout 시 자식이 stderr 에 마지막 trace 를 어디까지 썼는지 확인할 방법은 **오로지 `f_log` 파일** 뿐
- **자식 process 종료 처리 명시 無** → `subprocess.run()` 의 timeout 발동 시 내부적으로 자식을 `kill()` 하고 wait. 그 사이 자식의 **C-runtime / Python io buffer 에 머물던 stderr 출력은 flush 못 한 채 손실** 가능성 高

### 4-3. stderr buffered 출력 처리 유무

- driver 측: `flush=True` 로 자체 print 는 즉시 flush (L137, L140)
- 자식 측: **`stderr=subprocess.STDOUT`** 이므로 자식의 `sys.stderr.write()` 도 결국 `f_log` 파일로 감
- **결정적 위험**: 자식이 `print(..., file=sys.stderr)` 만 쓰고 `flush=True` 안 하면 → Python io buffer (line-buffered 가 보통이지만 redirect 된 stderr 는 **block-buffered** 가 됨, PEP 7) → timeout kill 시 **buffer 內 미flush 데이터 손실**

→ **§14-8 H1 trace 작성 시 모든 print 에 `flush=True` + `file=sys.stderr` 필수** (사용자 plan 의 5번 컨펌 박제와 일치)

## 5. 정상 종료 경로 (sub-stage e-6 ~ e-7)

| sub | line | 내용 |
|---|---|---|
| **e-6** | L165 | `elapsed = round(time.monotonic() - t_start, 2)` |
| **e-7** | L167-181 | output_json 존재 시 metric 추출 (`elapsed_sec`, `invoke_elapsed_sec`, `abort_reason`, `refs_docs_count`, `source_dist`) |
| **e-8** | L183-192 | return dict (`run_id`, `state`, `exit_code`, `elapsed_sec_driver`, `timeout`, `json_path`, `log_path`, `metrics`) |

## 6. (가-η) IMPORT 거동 분기 root cause 후보 정리

raw read 결과 driver-side 에서 가능한 분기 후보:

1. **env 구성 차이 (e-1 → e-2 → e-3)** — standalone shell 의 env vs `os.environ.copy() → POLLUTION pop → 명시 set` 의 결과 차이
2. **stdout/stderr redirect 차이** — standalone 은 console TTY, driver 자식은 binary file handle 로 redirect (`stderr=STDOUT`)
   - TTY 와 file 의 buffer mode 차이가 IMPORT-time 의 어떤 모듈 (예: vertex SDK 의 logging) 동작에 영향을 줄 수 있음
3. **timeout 컨텍스트** — standalone 은 timeout 無, driver 는 300s 강제 → 자식이 timeout 직전까지 어디서 stuck 되는지 trace 필요
4. **working directory** — driver subprocess 호출에 `cwd` 명시 안 함 → driver 자신의 cwd 상속. standalone 도 동일 cwd 에서 띄우는지 raw read B 에서 박제 필요

## 7. trace 진입점 합의 보강

- **driver (`measure_phase3_patch_d88a8b9.py`) trace**: e-4 직전 + e-5 직후 + TimeoutExpired catch 시 `e.stdout` 출력 (변경 1: `except ... as e:`)
- **자식 (`_step3_dry_run_rag_update.py`) trace**: 첫 line `[STAGE-0]` + IMPORT 단계별
- **양쪽 동시 trace 필요** — driver-side 만으로는 자식 IMPORT 내부 진행도 미상, 자식-side 만으로는 driver 의 subprocess kill 타이밍 미상
