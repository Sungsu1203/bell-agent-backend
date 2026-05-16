# §14-3 Phase 3 (G4-1) 진단 박제: 가설 (아') 확정 + (다") 부분 기각 + 매트릭스 § 4 정정 reference

본 문서는 §14-3 Phase 3 (commit 738ad4f 직후) 측정 + 진단 (G2) 결과 박제.

- 작업 일시: 2026-05-16
- 측정 시점: 2026-05-16 08:24:32 ~ 08:57:18 (32.8분)
- 측정 commit: HEAD 738ad4f (§14-3 (보조-1) 매트릭스 commit)
- **결론**: patch 효과 측정 무효 + 가설 (아') 확정 + (다") 부분 기각

---

## § 1. 측정 메타 + raw 결과

| 항목 | 값 |
|------|-----|
| driver | `scripts/measure_phase3_patch_d88a8b9.py` (324 lines) |
| architecture | patch-based (d88a8b9 패치 apply/revert) |
| 토픽 | `ai-generated-creative-ad-platforms` (P-2 재활용) |
| trigger | `"최신 자료로 RAG 업데이트해줘"` |
| N | 3 runs × 2 state + warmup 2 = 10 runs |
| §13-7 표준 | max_retries=0, warmup 2, timeout 300s, sleep 60s, UTF-8 |
| 총 elapsed | 1,965.98s ≈ 32.8분 |
| exit codes | 모두 0 (10/10) |
| post-clean | True ✓ (working tree 정합, try/finally 동작) |
| patch apply/revert | 정상 작동 |

---

## § 2. per-state per-run 결과

### 2.1 patched state (현재 브랜치, d88a8b9 적용 상태)

| run | exit | elapsed | vertex_grounding | refs | source_dist |
|-----|------|---------|------------------|------|-------------|
| warmup_1 | 0 | 173.6s | 0 | 9 | (warmup) |
| warmup_2 | 0 | 103.2s | 0 | 9 | (warmup) |
| run_1 | 0 | 175.8s | 0 | 9 | `{other:1, local:8}` |
| run_2 | 0 | 122.4s | 0 | 9 | `{other:1, local:8}` |
| run_3 | 0 | 78.4s | 0 | 9 | `{other:1, local:8}` |

summary: vertex_grounding mean=0 CV=0%, elapsed mean=125.53s **CV=38.84%**, refs mean=9.0 CV=0%

### 2.2 reverted state (d88a8b9 revert 상태)

| run | exit | elapsed | vertex_grounding | refs | source_dist |
|-----|------|---------|------------------|------|-------------|
| warmup_1 | 0 | 133.1s | 0 | 10 | (warmup) |
| warmup_2 | 0 | 133.9s | 0 | 9 | (warmup) |
| run_1 | 0 | 117.2s | 0 | 9 | `{other:1, local:8}` |
| run_2 | 0 | 105.0s | 0 | 9 | `{other:1, local:8}` |
| run_3 | 0 | 183.6s | 0 | 10 | `{other:1, web:1, local:8}` |

summary: vertex_grounding mean=0 CV=0%, elapsed mean=135.26s **CV=31.25%**, refs mean=9.33 CV=6.19%

---

## § 3. Critical Surprising Findings (★★★★★)

### Finding 1 — vertex_grounding=0 in BOTH states

- 양쪽 모두 vertex_grounding=0 (10 runs)
- **patch 효과 측정 무효**
- 직전 P-2 (commit 2d3dd1f) 의 vertex_grounding=1 결과와 불일치

### Finding 2 — source_dist 패턴이 P-2 와 완전 다름

| 측정 | source_dist | 비고 |
|------|-------------|------|
| P-2 (단발) | `{web: 7, vertex_grounding: 1}` | web 위주 + vertex 1건 |
| Phase 3 patched | `{other: 1, local: 8}` × 3 | **local 위주, vertex=0** |
| Phase 3 reverted | 동일 + run 3 `web=1` | **local 위주, vertex=0** |

### Finding 3 — 변동성 CV 31-38%

- 측정 신뢰성 표준: CV > 30% 시 측정 무효 판정
- patched CV 38.84%, reverted CV 31.25% — 둘 다 임계 초과
- elapsed range patched [78.4, 175.8], reverted [105.0, 183.6]

### Finding 4 — 8 docs = venfobel 종근당_팩트북.pdf

console.log + JSON dump 결과:
- 모든 `class=local` docs source: `file:///D:/GPT_AGENT/writer_project/refs/종근당_팩트북.pdf#part=N&index=N&chunk=N`
- venfobel 토픽 자산이 ai-gen 토픽 측정에서 retrieve
- chroma `venfobel-vitamin-oa-local count=349` ns 매칭

---

## § 4. 진단 결과 (가설 매트릭스)

| 가설 | 평가 | 근거 |
|------|------|------|
| (가) chroma ns_local 누적 | **기각** | ai-gen-local count=0, PersistentClient ns 격리 |
| (가') chroma 외부 read | **부분 확정** | venfobel-vitamin-oa-local 의 chunks 가 retrieve. CHROMA_NAMESPACE override 결과 |
| (나') source_class 분류 결함 | **기각** | `_classify_source` (`_step3_dry_run_rag_update.py:108`) 정확 |
| (다') graph state 변경 | (다") 로 재분류 | — |
| (라') vertex API quota | **부분 확정** | 404 NOT_FOUND, 모델명 결함 (quota 아님) |
| (마') PowerShell session pollution | **기각** | PowerShell tool 매 호출 fresh process (PID 50564, 10:10:57 시작 확인) |
| (바') overlay 순서 결함 | **기각** | `core/config.py:106-128` ONE overlay only |
| (사') TOPIC_SLUG → openai overlay | **기각** | `_apply_topic_preset` 만 load |
| **(아')** graph 내부 env modification | **확정 ★★★★★** | `core/topic.py:140-143` |
| (자') vertex_search.py 동적 env read | **부분 확정** | L112 `os.getenv("LLM_MODEL")` direct read, CFG 캐시 무시 |
| (다") `.env.openai` 측정 중 load | **부분 기각** | 명시 load 코드 부재 (grep 결과), 그러나 venfobel-vitamin-oa 값 출처 미스터리 |
| (차') subprocess stage 차이 | **확정** | env capture L1 vs vertex 호출 시점 LLM_MODEL 다름 |

---

## § 5. 핵심 메커니즘 박제 (★★★★★)

### 5.1 `core/topic.py:140-143` (smoking gun)

```python
if _cfg_bool("MIRROR_STATE_TO_ENV", True):  # default True
    os.environ["CHROMA_NAMESPACE"] = ns
    os.environ["CHROMA_DIR"] = chroma_dir
    logger.debug("[topic] mirrored CHROMA_* to env (ns=%s dir=%s)", ns, chroma_dir)
```

**call chain**:
- `agent/supervisor.py:25`: `from core.topic import start_new_topic`
- supervisor 가 새 토픽 진입 시 runtime 시점 `os.environ["CHROMA_NAMESPACE"]` 동적 변경

### 5.2 `tools/web_rag/vertex_search.py:112`

```python
model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
```

- vertex API 호출 직전 `os.environ["LLM_MODEL"]` 직접 read
- CFG.LLM_MODEL 캐시 무시 → env 변경 시 즉시 반영

### 5.3 env modification 위치 list (전체)

| 위치 | 패턴 | 영향 |
|------|------|------|
| `app.py:111-112` | `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE` | TLS cert |
| `app.py:2252-2278` | LOG_*, DASH_*, GATE_*, ALLOWED_DOMAINS | CLI mirror |
| `app.py:2342-2344` | `TOPIC_SLUG`, `TOPIC_TITLE` | CLI 진입 |
| **`core/topic.py:141-142`** ★ | `CHROMA_NAMESPACE`, `CHROMA_DIR` | **runtime 동적 변경** |
| `scripts/measure_stability.py:450, 461` | GCP_REGION, LLM_MODEL | 측정 driver only |

---

## § 6. P-2 vs Phase 3 충돌 원인 식별

| 측정 | env 상태 | vertex_grounding | 메커니즘 |
|------|----------|------------------|----------|
| P-2 (commit 2d3dd1f, 단발) | 깨끗 | 1 | 정상 |
| Phase 3 (HEAD 738ad4f, 32.8분) | dirty (LLM_MODEL=gpt-4o, CHROMA_NAMESPACE=venfobel-vitamin-oa) | 0 | core/topic.py mirror + 미식별 메커니즘 |

매트릭스 § 4 시나리오 C plan 박제 vs 실측:
- plan: `LLM_MODEL=gemini-2.5-flash`, `CHROMA_NAMESPACE=ai-gen-*`
- 실측: `LLM_MODEL=gpt-4o`, `CHROMA_NAMESPACE=venfobel-vitamin-oa`

---

## § 7. `.env.openai` load 메커니즘 grep 결과 (가설 (다") 정확화)

### 7.1 grep 결과

```
.env.openai 명시 load: No matches found  ← 코드 부재
```

전체 `.py` 파일에서 `.env.openai` 직접 load 하는 코드 **없음**. 단 `core/config.py:120` 의 `_apply_provider_overlay` 가 `LLM_PROVIDER` 값에 따라 `.env.{provider}` 동적 load.

### 7.2 LLM_PROVIDER 변경 위치

| 위치 | 패턴 |
|------|------|
| `core/config.py:595` | `_env_str("LLM_PROVIDER", "openai").lower()` (read only) |
| `scripts/measure_stability.py:459` | `os.environ["LLM_PROVIDER"] = saved_provider` (측정 driver only) |
| `scripts/regen_pptx_13_14_1.py:25` | `os.environ.setdefault("LLM_PROVIDER", "openai")` (별도 script) |

운영 코드 (graph/agent/tools) 에서 LLM_PROVIDER 동적 변경 **없음**.

### 7.3 가설 (다") 평가

`.env.openai` 명시 load 부재 → **가설 (다") 부분 기각**.

그러나 측정 결과 `venfobel-vitamin-oa-web` 정확 매칭 (`.env.openai:57` 의 값) → **값 출처 미스터리 유지**.

**신규 가설 (다''')** — 측정 시점 PowerShell session 의 부모 process env (Claude Code orchestration layer) 가 dirty 했을 가능성, 또는 측정 driver 의 PowerShell launch 시 어떤 prefile 이 .env.openai 의 변수를 set. 추가 진단 필요.

---

## § 8. 매트릭스 § 4 정정 reference

### 8.1 정정 사유

매트릭스 commit 738ad4f 의 § 4 시나리오 C plan 박제:
- runtime LLM_MODEL: `gemini-2.5-flash`
- runtime CHROMA_NAMESPACE: ai-gen-* (자동 파생)

본 Phase 3 측정의 실측:
- runtime LLM_MODEL: **gpt-4o** ★
- runtime CHROMA_NAMESPACE: **venfobel-vitamin-oa** ★

→ plan 박제와 실측이 충돌. plan 박제는 "추정 검증 안 됨" 상태였음.

### 8.2 향후 박제 표준 추가

박제 자산 작성 시 다음 구분 명시:
- **박제 (실측)**: 측정/grep/Read 로 검증된 사실
- **plan (미검증)**: 의도된 동작, 실측 미수행

매트릭스 § 4 시나리오 C 는 plan 박제였음 → 향후 시나리오 박제 시 "plan" 명시 + 실측 시 박제 승격.

---

## § 9. 다음 단계 plan (commit 2 + commit 3 분리)

### commit 2: driver 수정

**driver `measure_phase3_patch_d88a8b9.py` env 처리 보강**:

```python
# 기존 (오염 가능)
env = os.environ.copy()
env["TOPIC_SLUG"] = config["topic_slug"]
# ...

# 신규 (G4 보강)
env = os.environ.copy()

# pop pollution vars
for k in ("CHROMA_NAMESPACE", "CHROMA_NAMESPACE_WEB", "CHROMA_NAMESPACE_LOCAL",
         "CHROMA_DIR"):
    env.pop(k, None)

# 명시 set
env["PYTHONIOENCODING"] = "utf-8"
env["LOCAL_RAG_ALLOW_EMPTY"] = "1"
env["TOPIC_SLUG"] = config["topic_slug"]
env["LLM_PROVIDER"] = "vertexai"
env["LLM_MODEL"] = "gemini-2.5-flash"
env["SKIP_VERTEX_SEARCH"] = "0"
env["MIRROR_STATE_TO_ENV"] = "0"  # ★ core/topic.py:140 의 mirror 차단
```

**dry-run script `_step3_dry_run_rag_update.py` env-trace 추가**:
- STAGE_1 (script start, before any load)
- STAGE_2 (after .env.vertex load)
- STAGE_3 (before graph.invoke)

이는 재측정 시 env 동적 변경 직접 박제 가능.

### commit 3: 재측정 + 박제

- 깨끗한 env 로 N=3 × 2 state 재측정
- env-trace 결과 분석 + 박제
- patch 효과 측정 (vertex_grounding mean 차이)
- 박제 자산 v2 `(NEW)-B_phase3_step1b_result_v2.md` 또는 본 자산 확장

### 자기 정정 메커니즘 박제

- 직전 가설 (마') PowerShell pollution 확정 → 추가 진단으로 부분 기각
- 가설 (아') 신규 식별 + 확정
- 가설 (다") 부분 기각 + (다''') 신규 식별
- 박제 컨벤션 정신 정합 (사전 확인 + 자기 정정)

---

## 부록 A. 참고 파일

- `scripts/measure_phase3_patch_d88a8b9.py` (Phase 3 driver, 324 lines)
- `scripts/_step3_dry_run_rag_update.py` (dry-run wrapper, _classify_source L108)
- `scripts/output/§14-3/_phase3/phase3_summary_20260516_085718.json` (raw, gitignored)
- `scripts/output/§14-3/_phase3/phase3_*.json/*.console.log` (per-run raw, gitignored)
- `scripts/output/§14-3/_phase3/_chroma_diag.py` (chroma collection diag)
- `scripts/output/§14-3/_phase3/_env_stage_diag.py` (env stage diag)
- `core/topic.py:100-145` (start_new_topic, MIRROR_STATE_TO_ENV)
- `core/config.py:106-167, 440-481, 650-669` (overlay/preset/CHROMA derive/reload)
- `tools/web_rag/vertex_search.py:88-130` (vertex API call, L112 LLM_MODEL read)
- `agent/supervisor.py:25` (start_new_topic import)
- `.env.vertex`, `.env.openai`, `.env.anthropic` (provider overlays)
- `scripts/output/§14-3/env_flow_matrix.md` (commit 738ad4f, § 4 정정 대상)
- `scripts/output/§14-3/(NEW)-B_track1_P2_result.md` (P-2 박제, vertex_grounding=1 정합)
