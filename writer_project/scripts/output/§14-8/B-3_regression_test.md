# §14-8-B B-3 — regression test 박제 ((O)+(C) 적용 후)

**측정 일자:** 2026-05-17
**git HEAD:** B-3 commit 2 직후 (`b0fae59` feat(rag) fix C)
**미션:** B-2ext4 박제 mechanism 의 (O) protected env list + (C) embedding dim strengthening fix 후 regression 검증

**결과 요약:** **regression test FULL PASS ★★★** — mystery 1+2 종결 박제

---

## § 1. 테스트 환경

- branch: feature/vertex-web-search
- HEAD: `b0fae59` (commit 2 직후, commit 3 prep)
- venv: `.venv_vertex` (D:\gpt_agent\.venv_vertex)
- trigger: `scripts/diag/§14-8/b2ext4_trigger.py` (B-2ext4 와 동일 invoke chain)
- CWD: `D:\gpt_agent\writer_project` (B-2ext4 박제 — find_dotenv(usecwd=True) regression 발화 조건)

### probe 재삽입 (temporary, B-3 commit 전 revert)

| 지점 | file:line | 출력 |
|---|---|---|
| (a) | `tools/web_rag/search.py:1367` 직전 | `envdump_stage_a_postfix.json` |
| (b) | `tools/web_rag/search.py:1367` 직후 | `envdump_stage_b_postfix.json` |
| (c) | `core/config.py:665` (`_apply_provider_overlay` 직후) | `envdump_stage_c_postfix.json` |

probe revert self-check: `git diff writer_project/tools/web_rag/search.py writer_project/core/config.py` **empty** ★

---

## § 2. raw envdump 박제 (post-fix)

### stage a (BEFORE reload_config, postfix)
```json
{
  "stage": "a_before_reload_config_postfix",
  "pid": 68416,
  "ts": 1778969064.0674524,
  "LLM_PROVIDER": "vertexai",
  "LLM_MODEL": "gemini-2.5-flash",
  "TOPIC_SLUG": "ai-generated-creative-ad-platforms",
  "CHROMA_NAMESPACE": "<unset>",
  "CHROMA_NAMESPACE_WEB": "<unset>",
  "OPENAI_MODEL": "<unset>",
  "SKIP_VERTEX_SEARCH": "0",
  "MIRROR_STATE_TO_ENV": "0"
}
```

### stage c (AFTER _apply_provider_overlay, postfix)
```json
{
  "stage": "c_after_provider_overlay_postfix",
  "pid": 68416,
  "ts": 1778969064.0814514,
  "LLM_PROVIDER": "vertexai",
  "LLM_MODEL": "gemini-2.5-flash",
  "TOPIC_SLUG": "ai-generated-creative-ad-platforms",
  "CHROMA_NAMESPACE": "<unset>",
  "CHROMA_NAMESPACE_WEB": "<unset>",
  "OPENAI_MODEL": "<unset>",
  "SKIP_VERTEX_SEARCH": "0",
  "MIRROR_STATE_TO_ENV": "0"
}
```

### stage b (AFTER reload_config returns, postfix)
```json
{
  "stage": "b_after_reload_config_postfix",
  "pid": 68416,
  "ts": 1778969064.0834525,
  "LLM_PROVIDER": "vertexai",
  "LLM_MODEL": "gemini-2.5-flash",
  "TOPIC_SLUG": "ai-generated-creative-ad-platforms",
  "CHROMA_NAMESPACE": "<unset>",
  "CHROMA_NAMESPACE_WEB": "<unset>",
  "OPENAI_MODEL": "<unset>",
  "SKIP_VERTEX_SEARCH": "0",
  "MIRROR_STATE_TO_ENV": "0"
}
```

ts 순서: a(.0674) → c(.0815, Δ=14.1ms) → b(.0835, Δ=2.0ms from c). a→c→b 정합 (c 가 reload_config 내부, b 가 외부 직후) ★

---

## § 3. pre/post-fix flip 비교 + pass/fail 판정

### 3-1. flip 비교표

| field | pre-fix stage a | pre-fix stage c | post-fix stage a | **post-fix stage c** | judgment |
|---|---|---|---|---|---|
| `LLM_PROVIDER` | vertexai | **openai (flip)** | vertexai | **vertexai (preserved)** ★ | **PASS** ✓ |
| `LLM_MODEL` | gemini-2.5-flash | **gpt-4o (flip)** | gemini-2.5-flash | **gemini-2.5-flash (preserved)** ★★★ | **PASS** ✓ |
| `TOPIC_SLUG` | ai-generated-... | **venfobel-vitamin (flip)** | ai-generated-... | **ai-generated-... (preserved)** ★ | **PASS** ✓ |
| `SKIP_VERTEX_SEARCH` | 0 | 0 | 0 | **0 (preserved)** ★ | **PASS** ✓ |
| `MIRROR_STATE_TO_ENV` | 0 | (미측정) | 0 | **0 (preserved)** ★ | **PASS** ✓ |
| `CHROMA_NAMESPACE` | `<unset>` | **venfobel-vitamin-oa (introduced)** | `<unset>` | **`<unset>` (cascading blocked)** ★★★ | **PASS** ✓ |
| `CHROMA_NAMESPACE_WEB` | `<unset>` | **venfobel-vitamin-oa-web (introduced)** | `<unset>` | **`<unset>` (cascading blocked)** ★★★ | **PASS** ✓ |
| `OPENAI_MODEL` | `<unset>` | **gpt-4o (introduced)** | `<unset>` | **`<unset>` (cascading blocked)** ★★★ | **PASS** ✓ |

### 3-2. mission 4.2 pass 항목 박제

| pass 항목 | 박제 |
|---|---|
| **(a) protected key preservation** | LLM_PROVIDER, LLM_MODEL, TOPIC_SLUG, SKIP_VERTEX_SEARCH, MIRROR_STATE_TO_ENV — stage c == stage a 박제 ✓ |
| **(b) 비-protected overlay 정상 (cascading 차단)** | CHROMA_NAMESPACE/CHROMA_NAMESPACE_WEB/OPENAI_MODEL — 모두 `<unset>` (venfobel-vitamin-oa* / gpt-4o introduction 부재) ✓ |
| **(c) end-to-end vertex_grounding** | trigger output 의 `web_search returned: type=tuple` 박제 — exception 없이 정상 완료. LLM_MODEL=gemini-2.5-flash 보존되어 vertex_web_search L112 가 정상 model 로 호출. (별도 vertex API 응답 grounding annotation 검증은 wrapper run 단계에서 별 cycle 가능) |
| **(d) dual-retrieve namespace 정합** | `FINAL CFG | CHROMA_NAMESPACE_WEB=ai-generated-creative-ad-platforms-web` 박제 — venfobel regression 없이 topic-derived ns 정합 ✓ |

### 3-3. trigger 마지막 output 박제 (FINAL state)

```
[trigger] FINAL os.environ | LLM_PROVIDER=vertexai | LLM_MODEL=gemini-2.5-flash | TOPIC_SLUG=ai-generated-creative-ad-platforms | CHROMA_NAMESPACE_WEB=<unset>
[trigger] FINAL CFG | LLM_PROVIDER=vertexai | LLM_MODEL=gemini-2.5-flash | TOPIC_SLUG=ai-generated-creative-ad-platforms | CHROMA_NAMESPACE_WEB=ai-generated-creative-ad-platforms-web
[trigger] DONE
```

- `os.environ.CHROMA_NAMESPACE_WEB = <unset>` — 환경변수 부재 (driver pop 유지) ✓
- `CFG.CHROMA_NAMESPACE_WEB = ai-generated-creative-ad-platforms-web` — `__post_init__` auto-derive (config.py L450-451) ✓
- topic-defined ns 정상, venfobel regression 부재 ★

---

## § 4. mystery 종결 박제

| mystery | pre-fix status | post-fix status | 박제 |
|---|---|---|---|
| **mystery 1** (CHROMA_NAMESPACE_WEB=venfobel-vitamin-oa 회귀) | CONFIRMED (B-2ext4 stage c) | **★★★ resolved** | CHROMA_NAMESPACE_WEB `<unset>` 유지, CFG 는 topic-derived |
| **mystery 2** (vertex API model=gpt-4o → 404) | CONFIRMED (B-2ext4 stage c) | **★★★ resolved** | LLM_MODEL=gemini-2.5-flash 보존, vertex_web_search L112 가 정상 model 사용 |

→ **§14-8-B 의 두 mystery 모두 (O) protected env list 단일 patch 로 종결** ★★★

---

## § 5. (O)+(C) 적용 자산 박제

| asset | 위치 |
|---|---|
| (O) protected env list | `core/config.py` `_PROTECTED_ENV_KEYS` + `reload_config_inplace` snapshot/restore (commit `6a9e0dc`) |
| (C) embedding dim mismatch 분리 log | `agent/vector_search.py:_call_retrieve` + `tools/web_rag/ingest_vector.py:1656` (commit `b0fae59`) |
| audit | `scripts/output/§14-8/B-3_audit.md` |
| regression test | 본 문서 `B-3_regression_test.md` |
| envdump pre-fix (B-2ext4) | `envdump_stage_{a,b,c}.json` (B-2ext4 cycle 박제 자료) |
| envdump post-fix (B-3) | `envdump_stage_{a,b,c}_postfix.json` ★ |
| trigger script (reusable) | `scripts/diag/§14-8/b2ext4_trigger.py` (regression infra) |

---

## § 6. 자기 비판 박제 (priors 14 가능성 확인)

- (가) 분기 적중 — audit + (O) + (C) + regression test pass 정합. 분기 (나)/(다) 발생 안 함.
- (다) 가능성 확인: audit 결과 의외 발견 없음 — `_PROTECTED_ENV_KEYS` 5건 (LLM_PROVIDER/LLM_MODEL/TOPIC_SLUG/SKIP_VERTEX_SEARCH/MIRROR_STATE_TO_ENV) 정합. driver-set 7건 중 LOCAL_RAG_ALLOW_EMPTY/PYTHONIOENCODING 는 flip 위험 부재 (audit § 3.1).

### priors 정정 / 신규 (B-2ext4 까지 누적 13 → 본 cycle 시점)

| # | priors | status |
|---|---|---|
| 14 (potential) | audit 결과 의외 발견 (다른 root cause) | **★ 부재 박제** — (다) 분기 발생 안 함. (O) primary fix 적중. |

→ 14번째 priors 는 "예상되는 의외 발견 후보" 였으나 audit 박제로 부재 확정. 본 cycle 결정 단순화 ★.

---

## § 7. defer / reserve (B-3 close 시 통합)

§5 close 박제에서 reserve list 통합:
- **CWD-independent .env resolution** — `find_dotenv(usecwd=True)` 의 CWD 의존성. (O) 가 protected key 만 보호하므로 비-protected key 의 CWD-dependent flip 가능성 잔존 (별 진단 필요)
- **다른 `reload_config()` 호출처 audit** — `tools/local_rag.py:252`, `tools/web_rag/utils.py:168`. 현재 search.py:1367 외 호출처에서도 (O) 보호 정상 작동 확인 (CFG 가 단일 시점에 동기화). 별 cycle 검증 권장.
- **protected list 외부화 / config 화** — runtime mutable 시 (현재 module-level tuple). 본 cycle scope 외.

→ §5 close summary 에서 reserve list 통합 박제 예정.

---

## § 8. 본 cycle 결정

- (가) **regression test FULL PASS → §14-8-B close 진입** ★

→ B-3 commit 3 (본 regression test 박제), 4 (README close + push) 순차 진행.
