# §14-8-B B-3 — driver-set env audit + _PROTECTED_ENV_KEYS 확정

**측정 일자:** 2026-05-17
**git HEAD:** B-2ext4 박제 후 (origin sync 가정)
**미션:** (O) protected env list snapshot/restore 의 `_PROTECTED_ENV_KEYS` tuple 확정 — driver-set env 와 `.env*` static default 의 conflict 후보 박제

---

## § 1. driver-set env keys 박제 (PowerShell wrapper grep)

### 1-1. 명시 set + POLLUTION pop 위치

PowerShell wrapper scripts (`scripts/diag/§14-8/*.ps1`) 의 `$env:` 패턴 grep:

| key | wrapper 파일:line | 값 |
|---|---|---|
| `PYTHONIOENCODING` | run_h2_envdump.ps1:48, test_c_driver_env_repro.ps1:53, test_d1_step3_with_driver_env.ps1:59 | `utf-8` |
| `LOCAL_RAG_ALLOW_EMPTY` | run_h2_envdump.ps1:49, test_c:54, test_d1:60 | `1` |
| **`TOPIC_SLUG`** | run_h2_envdump.ps1:50, test_c:55, test_d1:61 | `ai-generated-creative-ad-platforms` |
| **`LLM_PROVIDER`** | run_h2_envdump.ps1:51, test_c:56, test_d1:62 | `vertexai` |
| **`LLM_MODEL`** | run_h2_envdump.ps1:52, test_c:57, test_d1:63 | `gemini-2.5-flash` |
| **`SKIP_VERTEX_SEARCH`** | run_h2_envdump.ps1:53, test_c:58, test_d1:64 | `0` |
| **`MIRROR_STATE_TO_ENV`** | run_h2_envdump.ps1:54, test_c:59, test_d1:65 | `0` |

POLLUTION pop 4건 (run_h2_envdump.ps1 L58-59):
- `CHROMA_NAMESPACE`
- `CHROMA_NAMESPACE_WEB`
- `CHROMA_NAMESPACE_LOCAL`
- `CHROMA_DIR`

→ **driver 명시 set 7건 + POLLUTION pop 4건** (run_h2 / test_c / test_d1 모두 동등 패턴) ★

### 1-2. driver app.py 의 env set (production driver)

| key | line | 값 |
|---|---|---|
| `SSL_CERT_FILE` | app.py:111 | certifi.where() |
| `REQUESTS_CA_BUNDLE` | app.py:112 | certifi.where() |
| `LOG_LEVEL` | app.py:2252 | args.log_level.upper() |
| `LOG_FILE`, `LOG_JSON`, `LOG_TOPK`, `LOG_DASHBOARD`, `LOG_WRAP`, `DASH_SIMPLE`, `DASH_RATE_SEC`, `COMMUNICATOR_ECHO`, `HUMAN_LOGS_VERBOSE`, `HUMAN_LOGS`, `ECHO_OUTLINE`, `ECHO_SECTIONS`, `ECHO_REPORT`, `GATE_KEEP_SOURCES`, `ALLOWED_DOMAINS`, `ALLOW_SUBDOMAINS` | app.py:2254-2278 | logging/echo args |
| **`TOPIC_SLUG`** | app.py:2342 | args.topic_slug |
| `TOPIC_TITLE` | app.py:2344 | args.topic_slug.replace("-", " ") |

→ **production driver (app.py) 가 TOPIC_SLUG 명시 set** — wrapper 와 정합 ★

---

## § 2. `.env*` static default 박제

### 2-1. 충돌 후보 grep 결과

| key | global `.env` | `.env.vertex` | `.env.openai` | `.env.anthropic` | topics/ai-generated.env | topics/venfobel-vitamin.env |
|---|---|---|---|---|---|---|
| `LLM_PROVIDER` | **L2 `=openai`** | L15 `=vertexai` | L15 `=openai` | L15 `=anthropic` | — | — |
| `LLM_MODEL` | **L3 `=gpt-4o`** | L18 `=gemini-2.5-flash` | — | — | — | — |
| `TOPIC_SLUG` | **L50 `=venfobel-vitamin`** | — | — | — | (preset) | (preset) |
| `SKIP_VERTEX_SEARCH` | **L20 `=1`** | — | L49 `=0` | L45 `=1` | L11 `=0` | L35 `# =0` (주석) |
| `LOCAL_RAG_ALLOW_EMPTY` | L118 `=1` | — | — | — | — | — |
| `MIRROR_STATE_TO_ENV` | (부재) | (부재) | (부재) | (부재) | (부재) | (부재) |
| `PYTHONIOENCODING` | (부재) | (부재) | (부재) | (부재) | (부재) | (부재) |
| `CHROMA_NAMESPACE` | L122 `# =kr-pet-food` (주석) | L49 `# =venfobel-vitamin-vx` (주석) | **L56 `=venfobel-vitamin-oa`** | **L50 `=venfobel-vitamin-oa`** | — | — |
| `CHROMA_NAMESPACE_WEB` | L123 `# =...-web` (주석) | L50 `# =...-vx-web` (주석) | **L57 `=venfobel-vitamin-oa-web`** | **L51 `=...-oa-web`** | — | — |
| `CHROMA_NAMESPACE_LOCAL` | L124 `# =...-local` (주석) | L51 `# =...-vx-local` (주석) | **L58 `=venfobel-vitamin-oa-local`** | **L52 `=...-oa-local`** | — | — |
| `CHROMA_DIR` | L121 `=data/chroma_store` | — | — | — | — | — |

---

## § 3. 충돌 후보 list (1.1 ∩ 2.1)

### 3-1. driver-set ∩ static default 충돌 평가

| key | driver 값 | static default | 충돌 시 결과 | 보호 필요? |
|---|---|---|---|---|
| **`LLM_PROVIDER`** | `vertexai` | global `.env L2 =openai` | **★★★ vertexai → openai flip** → .env.openai overlay → CHROMA_NAMESPACE_*+OPENAI_MODEL 도입 (B-2ext4 stage c CONFIRMED) | **★★★ MUST** |
| **`LLM_MODEL`** | `gemini-2.5-flash` | global `.env L3 =gpt-4o` | **★★★ gemini → gpt-4o flip** → vertex_web_search L112 `os.getenv("LLM_MODEL")` 직접 read → vertex 404 (B-2ext4 stage c CONFIRMED) | **★★★ MUST** |
| **`TOPIC_SLUG`** | `ai-generated-creative-ad-platforms` | global `.env L50 =venfobel-vitamin` | **★★★ ai-generated → venfobel flip** → topic preset venfobel-vitamin.env load → MERGE_RETRIEVE_MODE/RAG_TOP_K 변경 (B-2ext4 stage c CONFIRMED) | **★★★ MUST** |
| **`SKIP_VERTEX_SEARCH`** | `0` | global `.env L20 =1` | **★ 0 → 1 flip** → vertex_grounding skip → 본 cycle 의 wrapper invoke chain 에서 .env.openai L49=0 overlay 가 0 유지 (실측 B-2ext4 stage c=0). 단 LLM_PROVIDER 보호되면 .env.vertex overlay (SKIP_VERTEX_SEARCH 부재) → global .env L20=1 그대로 남음 → vertex skip. **driver 0 의도 보호 필요** | **★ MUST** |
| `MIRROR_STATE_TO_ENV` | `0` | (모든 .env 파일 부재) | flip 없음 — `.env` load 후 그대로 유지. 단 driver 가 명시 0 set 이므로 defense 보호 | **△ 권장** |
| `LOCAL_RAG_ALLOW_EMPTY` | `1` | global `.env L118 =1` | 동일값 — flip 없음 | 不要 |
| `PYTHONIOENCODING` | `utf-8` | (모든 .env 파일 부재) | flip 없음 | 不要 |
| **POLLUTION POP CHROMA_NAMESPACE\*** | (driver pop, empty) | `.env.openai/anthropic` overlay 시 도입 | **★ LLM_PROVIDER 보호 시 .env.vertex overlay → CHROMA_NAMESPACE_* 도입 안 됨 (cascading 차단)** | 不要 (LLM_PROVIDER 보호로 자동 차단) |
| `CHROMA_DIR` | (driver pop, empty) | global `.env L121 =data/chroma_store` | **△ load_dotenv override=True → CHROMA_DIR=data/chroma_store 도입.** 단 driver intent 는 pop, .env value 는 default — 도입돼도 production 정합 가능 (별 검증 필요) | △ defer |

### 3-2. `_PROTECTED_ENV_KEYS` 확정

```python
_PROTECTED_ENV_KEYS = (
    "LLM_PROVIDER",         # MUST — overlay 분기 결정
    "LLM_MODEL",            # MUST — vertex_web_search 직접 read
    "TOPIC_SLUG",           # MUST — topic preset 분기 결정
    "SKIP_VERTEX_SEARCH",   # MUST — vertex grounding gate
    "MIRROR_STATE_TO_ENV",  # 권장 — driver intent 보호 (defense-in-depth)
)
```

**5개 key** 로 확정. 박제 근거:
- LLM_PROVIDER, LLM_MODEL, TOPIC_SLUG: B-2ext4 stage a→c empirical flip CONFIRMED
- SKIP_VERTEX_SEARCH: global `.env L20 =1` vs driver `0` mismatch + vertex_grounding 핵심 gate
- MIRROR_STATE_TO_ENV: empirical regression 부재 but driver 명시 set + start_new_topic 분기 결정 — defense

### 3-3. defer / 별 cycle 항목

- **CHROMA_DIR**: load_dotenv override=True 시 도입되지만 production 정합 가능 — 별 검증 필요 시 reserve 추가
- **POLLUTION POP CHROMA_NAMESPACE_*** : LLM_PROVIDER 보호로 cascading 차단됨 — explicit 보호 不要

---

## § 4. (O) snapshot/restore semantics 결정

### 4-1. 의미 정합

| snapshot[k] | restore 시 동작 | 의미 |
|---|---|---|
| str value | `os.environ[k] = value` (override) | **driver 명시 intent 보호** |
| None (k 가 os.environ 에 부재) | skip (else branch 없음) | **.env 값 허용 (hot-reload 의도 보존)** ★ |

§12-20 hot-reload 의도 정합:
- protected key 가 unset 상태 → reload 시 .env 값 픽업 가능 (개발자가 .env 편집 후 reload 의도)
- protected key 가 set 상태 → driver 명시 set, .env 정적 default 보다 우선 보호 (driver intent 정합)

### 4-2. snapshot 시점

`reload_config_inplace()` 의 `load_dotenv(.env, override=True)` **직전** 에 snapshot.
restore 는 `load_dotenv()` **직후** + `_apply_provider_overlay/topic_preset` **직전**.

→ provider overlay 와 topic preset 은 driver-restored LLM_PROVIDER/TOPIC_SLUG 기반 정상 분기 ★

### 4-3. patch 위치 (core/config.py L660 부근)

```python
def reload_config_inplace() -> Config:
    global CFG
    with _cfg_lock:
        if _DOTENV_READY:
            # [§14-8-B fix O] driver-set env protection — driver intent (env 명시 set) 보호
            _saved = {k: os.environ.get(k) for k in _PROTECTED_ENV_KEYS}
            try:
                load_dotenv(find_dotenv(usecwd=True), override=True)
            except Exception:
                pass
            # restore: driver 가 set 한 값 보호. None 인 경우 .env 값 허용 (hot-reload 의도)
            for _k, _v in _saved.items():
                if _v is not None:
                    os.environ[_k] = _v
            _apply_provider_overlay(verbose=False)
            _apply_topic_preset(verbose=False)
        new_cfg = _build_config()
        for f in fields(CFG):
            setattr(CFG, f.name, getattr(new_cfg, f.name))
        return CFG
```

---

## § 5. 결정 + 다음 단계

| 항목 | 결정 |
|---|---|
| `_PROTECTED_ENV_KEYS` | `("LLM_PROVIDER", "LLM_MODEL", "TOPIC_SLUG", "SKIP_VERTEX_SEARCH", "MIRROR_STATE_TO_ENV")` (5건) |
| snapshot/restore semantics | None → skip (.env 허용), value → restore (driver intent) |
| patch 위치 | `core/config.py reload_config_inplace L660` |
| 다음 단계 | commit 1: feat(config) — (O) protected list 적용 |
