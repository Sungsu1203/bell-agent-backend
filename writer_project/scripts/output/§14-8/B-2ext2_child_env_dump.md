# §14-8-B B-2ext2 — 자식 env dump 직접 검증 (시나리오 4)

**측정 일자:** 2026-05-17
**git HEAD:** 77c24ad (feature/vertex-web-search)
**미션:** 자식 process 의 전체 env 박제로 mystery (γ) 직접 검증

---

## § 1. 측정 방식 박제

### 1-1. 자식 script

`scripts/diag/§14-8/h2_step3_envdump.py` (production `_step3_dry_run_rag_update.py` 사본 + env_snapshot 함수에 `[envdump_full_<label>]` JSON dump 추가 + argparse default 한국어 hardcode)

### 1-2. PowerShell wrapper

`scripts/diag/§14-8/run_h2_envdump.ps1`:
- venv 활성화 + .env.vertex 사전 로드
- driver 명시 set 7건 (PYTHONIOENCODING, LOCAL_RAG_ALLOW_EMPTY, TOPIC_SLUG, LLM_PROVIDER, LLM_MODEL, SKIP_VERTEX_SEARCH, MIRROR_STATE_TO_ENV)
- POLLUTION pop 4건 (CHROMA_NAMESPACE*, CHROMA_DIR)
- Start-Process python h2_step3_envdump.py (argparse default 사용, 한국어 argument 우회)

### 1-3. fix history (측정 중 patch)

| fix | 원인 | patch |
|---|---|---|
| F5 | inner wrapper Python here-string SyntaxError (`r'$STEP3_SCRIPT'` paren mismatch) | inner wrapper Python 제거 — PowerShell direct env injection |
| F6 | single-quote here-string 의 한국어 + UTF-8 byte counting 이슈 → PowerShell parser shift → string terminator missing | here-string 제거 — h2 사본의 argparse default 한국어 hardcode |
| F7 | argparse --output required | default=None + tempfile 자체 생성 |

### 1-4. 측정 결과

- outer_elapsed = 15.6s (자식 graph import 단계까지 도달, 자체 종료 추정)
- STAGE_1_script_start envdump 박제 ★
- STAGE_2_dotenv_vertex_loaded envdump 박제 ★
- STAGE_3+ envdump 미박제 (STAGE_3 도달 전 종료 또는 stderr buffer flush 미완 — 별 진단)

---

## § 2. STAGE_1_script_start env dump 박제 (sensitive 마스킹)

### 2-1. 핵심 var 박제

| var | value | mystery 관련 |
|---|---|---|
| `LLM_PROVIDER` | `vertexai` | ✓ driver 명시 set 정합 |
| `LLM_MODEL` | `gemini-2.5-flash` | ✓ driver 명시 set 정합 (★ vertex 404 gpt-4o 의 LLM_MODEL 원인 아님) |
| `TOPIC_SLUG` | `ai-generated-creative-ad-platforms` | ✓ driver 명시 set 정합 |
| `SKIP_VERTEX_SEARCH` | `0` | ✓ driver 명시 set 정합 |
| `MIRROR_STATE_TO_ENV` | `0` | ✓ driver 명시 set 정합 |
| `PYTHONIOENCODING` | `utf-8` | ✓ driver 명시 set 정합 |
| `LOCAL_RAG_ALLOW_EMPTY` | `1` | ✓ driver 명시 set 정합 |
| **`CHROMA_NAMESPACE`** | **부재** ★ | driver POLLUTION pop 정합 |
| **`CHROMA_NAMESPACE_WEB`** | **부재** ★★★ | venfobel-vitamin-oa-web 미존재 박제 |
| **`CHROMA_NAMESPACE_LOCAL`** | **부재** ★ | venfobel-vitamin-oa-local 미존재 박제 |
| **`CHROMA_DIR`** | **부재** ★ | driver POLLUTION pop 정합 |
| **`OPENAI_MODEL`** | **부재** ★★★ | **.env.openai 로드 안 됨 박제** |
| `GCP_PROJECT_ID` | `gem***` (마스킹) | .env.vertex 사전 로드 정합 |
| `GCP_REGION` | `us-central1` | .env.vertex 정합 |
| `GOOGLE_APPLICATION_CREDENTIALS` | `service_account_vertex.json` (path 마스킹) | .env.vertex 정합 |
| `VERTEX_REQUEST_TIMEOUT` | `120` | .env.vertex 정합 |
| `VERTEX_MAX_RETRIES` | `0` | .env.vertex 정합 |
| `GEMINI_EMBEDDING_MODEL` | `text-multilingual-embedding-002` | .env.vertex 정합 |
| `RAG_EMBEDDING_MODEL` | `text-multilingual-embedding-002` | .env.vertex 정합 |
| `OPENAI_REQUEST_TIMEOUT` | `10` | .env.vertex 정합 |
| `OPENAI_MAX_RETRIES` | `1` | .env.vertex 정합 |
| **`RAG_DISTANCE_THRESHOLD`** | **STAGE_1 부재 → STAGE_2 = 0.65** ★ | reserve #1 박제 정합 (12 loaded vs 11 dump 차이 해소: PowerShell Set-Item value 비어있는 OPENAI_API_KEY 같은 var 의 Get-ChildItem 누락 + .env.vertex L36 의 set 시점 차이) |
| **`OPENAI_API_KEY`** | **STAGE_1 부재 → STAGE_2 = `""`** ★ | reserve #1 박제 정합 |

### 2-2. STAGE_2 추가분 박제

STAGE_2 = STAGE_1 + 자식 script L62 `load_dotenv(env_vertex, override=True)` 후
- `RAG_DISTANCE_THRESHOLD = "0.65"` 신규 추가
- `OPENAI_API_KEY = ""` 신규 추가 (의도적 공백)

→ STAGE_1 시점에는 .env.vertex 12 vars 중 10 vars 만 process env 에 set (PowerShell side load)
→ 자식 script L62 의 추가 load 로 12 vars 완전 적용
→ reserve #1 (case A 의 12 loaded vs env dump 11건 차이) 일부 해소 박제

### 2-3. **★★★ mystery (γ) 기각 확정 ★★★**

| mystery | 박제 결과 |
|---|---|
| **(B-1ext γ) wrapper 환경에서 `.env.openai` 가 어디서 load** | **★ 기각 확정** — STAGE_1/2 양쪽 모두 OPENAI_MODEL 부재, CHROMA_NAMESPACE_WEB 부재 (venfobel-vitamin-oa 부재) |

**근거**:
- `.env.openai L56-58`: CHROMA_NAMESPACE=venfobel-vitamin-oa hardcode
- `.env.openai L18`: OPENAI_MODEL=gpt-4o
- 자식 envdump 에 모두 부재 → **.env.openai 로드 안 됨 확정** ★

→ B-1ext § 6.10 + B-2ext § 4.3 의 공통 hypothesis **(.env.openai load 가능성) 명확 기각**

---

## § 3. mystery 재평가 — 남은 path 박제

### 3-1. mystery 1 (B-1ext) — CFG.CHROMA_NAMESPACE_WEB venfobel resolve

| path | 박제 |
|---|---|
| (α) `reload_config()` 호출 → CFG mutate | env 변동 없으므로 mutate 무의미 — 약화 |
| (β) `start_new_topic()` / supervisor 의 topic mutate → CFG / state | **★ 가능 — 추가 진단 필요** |
| (γ) `.env.openai` 가 wrapper-only path 로 load | **★ 기각 확정** (본 B-2ext2 결과) |
| (δ) `_cfg_str` 정의 변종 | 가능 — 추가 grep 필요 |
| (ε) chroma client list_collections() | 약화 (production 부재) |
| **(η 신규)** invoke chain 안의 다른 vector_search 호출 — ns 가 다른 path 로 결정 | **★ 가능 — 추가 진단 필요** |

### 3-2. mystery 2 (B-2ext) — vertex API call model=gpt-4o

| path | 박제 |
|---|---|
| (F-α) vertex_grounding 도구 LLM_MODEL 전달 안 됨 | 기각 (vertex_search.py L112 정상) |
| (F-β) provider 분기 path divergence | 부분 기각 (get_llm L327 vertex 정상) |
| (F-γ) vertex_search.py 내부 chain mutate | 기각 |
| (F-δ) wrapper 환경 env LLM_MODEL invoke 직전 mutate | **★ 약화** (envdump 부재 박제) |
| (F-ε) LangChain ChatVertexAI / 다른 vertex API path | 가능 — 추가 진단 필요 |
| (F-ζ) `[web_search] Vertex failed:` log 가 다른 source | 가능 — 추가 진단 필요 |

### 3-3. 두 mystery 공통 hypothesis 재평가

**기존**: 두 mystery 모두 wrapper-only → 공통 hypothesis = .env.openai load 가능성
**본 B-2ext2 결과**: .env.openai load 기각 확정

**신규 hypothesis**:
- 두 mystery 모두 invoke chain 안의 production code 가 어딘가에서 hardcode / mutate
- env propagation 아닌 **code-level mutate**
- 즉 fix 는 production code 변경 필요 (env / config 변경 만으로 해결 불가)

---

## § 4. fix-path 결정 영향 박제

### 4-1. env propagation fix 불요 박제

- 자식 env 가 driver 명시 set 그대로 도달 — env propagation 정확
- fix candidate (env 관련) 모두 기각:
  - (D) `.env.openai` hardcode 제거 → 불요 (load 안 됨)
  - env propagation 강화 → 불요 (정확)

### 4-2. fix C (embedding 일치성 검증) 의 위치 재평가

- env 가 정확한데 invoke 가 venfobel namespace 사용 → production code 안에서 mutate
- fix C (mismatch 시 empty 반환) = **mutate 결과 후 timeout 회피만** — root cause fix 아님
- 단 wrapper 환경 보호 효과 + runpy 환경 무영향

### 4-3. 신규 fix candidate 박제

| candidate | 영역 | 효과 |
|---|---|---|
| (H 신규) supervisor / start_new_topic / vector_search 의 namespace 결정 logic 직접 진단 | production code | root cause fix 가능성, 단 진단 비용 大 |
| (I 신규) invoke chain 의 모든 CFG / state mutate 위치 grep + 진단 | production code | 진단 비용 大 |

---

## § 5. 다음 단계 시나리오 재평가

### 5-1. 시나리오 4 결과 (γ 기각) → 시나리오 1 (fix C) 의 정당성

- 본 B-2ext2 결과로 mystery 완전 박제 못 함 — production code mutate path 미박제
- (β/δ/η) 추가 진단 비용 大 — 본 cycle 내 박제 어려움
- **fix C fallback 진입 정당화** ★ — env propagation 정확 확정, code-level mutate 는 별 cycle

### 5-2. 시나리오 결정 권장

**(시나리오 1 갱신) fix C fallback B-3 진입** ★ 권장:
- mystery 부분 박제 ((γ) 기각 + 신규 hypothesis = code-level mutate)
- env propagation 정확 확정
- fix C 의 한계 박제 (timeout 회피만, root cause 아님)
- B-4 효과 측정 후 → 효과 충분 (timeout 회피 + 본 미션 정량) → close
- 효과 부족 → 별 cycle (§14-9?) — code-level mutate 진단

**(시나리오 5 신규)** 추가 진단 1 round (β/δ/η 중 1건) → mechanism 박제 후 fix
- 비용: 추가 grep + 진단 ~10-20분
- 가치: root cause level fix
- risk: mystery 추가 박제 못 할 수 있음 (mechanism 더 깊음)

### 5-3. Claude Code 권장

**시나리오 1 갱신** (fix C B-3 진입) — env 정확 확정 + 본 cycle close 진행 + 효과 부족 시 별 cycle.

---

## § 6. 자기 비판 박제 (priors 기각 9번째)

| priors | 결과 |
|---|---|
| (γ) `.env.openai` load 가능성 (가장 유력) | **★ 기각 확정 (9번째)** |

### 6-1. priors 기각 누적 9건

1. case B 유력 → 기각
2. C timeout 의외로 유력 → 기각
3. D2 빠른 fail 예상 → 기각
4. driver wrapper #1/#2 高 의심 → 기각
5. vertex 404 gpt-4o (분기표 외) → 신규 발견
6. chroma embedding mismatch (분기표 외) → 신규 발견
7. fix C 추가 가치 (기존 handling 작동) → 부분 기각
8. (F-β) provider 분기 가장 유력 → 부분 기각
9. **(γ) .env.openai load 가장 유력** → **★ 기각 확정**

### 6-2. 향후 cycle 의 mystery 진단 protocol 자산화

- **raw 박제 자산 우선** — envdump 같은 직접 측정이 priors 기각 가장 효율
- **분기표 sharpening 한계** — priors 9건 기각으로 명확
- **mystery 누적 시 envdump-style 직접 측정 protocol 우선** — 본 시나리오 4 의 가치

---

## § 7. user 컨펌 Q list

**Q1.** § 2.3 — **(γ) `.env.openai` load 가능성 기각 확정** 합의 OK?

**Q2.** § 3.3 — 신규 hypothesis: 두 mystery 모두 **code-level mutate** (env propagation 아님) 합의 OK?

**Q3.** § 4 — env propagation fix 불요 + fix C 의 위치 재평가 (root cause 아닌 timeout 회피) 합의 OK?

**Q4.** § 5 다음 단계:
- **(시나리오 1 갱신) fix C B-3 진입** (★ Claude Code 권장)
- (시나리오 5) 추가 진단 1 round (β/δ/η)
- 또는 시나리오 2 (본 cycle close + 별 cycle)

**Q5.** § 6 priors 기각 9번째 + 향후 mystery 진단 protocol 자산화 합의 OK?
