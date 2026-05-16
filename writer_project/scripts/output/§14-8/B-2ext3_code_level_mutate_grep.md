# §14-8-B B-2ext3 — code-level mutate grep (시나리오 5, 시간 box 1 round)

**측정 일자:** 2026-05-17
**git HEAD:** 77c24ad (feature/vertex-web-search)
**미션:** 2 mystery (CFG.CHROMA_NAMESPACE_WEB=venfobel-vitamin-oa, vertex API call model=gpt-4o) code-level mutate 위치 박제

**결과 요약:** **두 mystery 단일 mechanism 으로 완전 박제 ★★★**
**원인:** `reload_config_inplace()` 의 글로벌 `.env` `override=True` 재로드 → 글로벌 `.env` 정적 default 값으로 driver-set env 덮어쓰기 → provider 분기 → `.env.openai` overlay load → CFG mutate.
**(γ) hypothesis 의 "기각 확정 (9번째 priors)" 은 **measurement gap** (envdump STAGE_3+ 미포착) — 본 cycle 에서 정정 ★.

---

## § 1. 작업 1 — (H) namespace 결정 logic 박제

### 1-1. `start_new_topic` 정의 + 호출처 (core/topic.py L93-174)

| location | line | context |
|---|---|---|
| **`core/topic.py:93`** | `def start_new_topic(state: State, title: str, outline_fname: Optional[str] = None) -> State:` | 정의 |
| **`core/topic.py:107`** | `state["topic_slug"] = slug` (slug = `topic_slug_from(title)` = `{slugify(title)}-{ts}`) | state mutate |
| **`core/topic.py:141`** | `os.environ["CHROMA_NAMESPACE"] = ns` (`MIRROR_STATE_TO_ENV=True` 시만) | env mutate (gated) |
| **`agent/supervisor.py:25`** | `from core.topic import start_new_topic, sanitize_title as _sanitize_title` | import |
| **`agent/supervisor.py:677`** | `state = start_new_topic(state_for_start, maybe_title, outline_fname=...)` | **유일 호출처** ★ |

→ **start_new_topic 의 production 호출처 = supervisor.py L677 단 1곳** ★

### 1-2. supervisor L672-681 호출 조건 — 사용자 message regex 매칭 시만

```python
# L672
new_title = extract_new_topic_title(last_text)
if new_title:
    maybe_title = _sanitize_title(new_title or "untitled report")
    state_for_start: State = cast(State, dict(state))
    state = start_new_topic(state_for_start, maybe_title, ...)
```

`extract_new_topic_title` (rag_expression.py L300-313) 의 `RE_NEW_TOPIC` 매칭:
- 매칭 형태: "새 보고서:", "write:", "작성:" 등 prefix
- wrapper trace user message: `"최신 자료로 RAG 업데이트해줘"` → **매칭 안 함** → `new_title = None`
- → **start_new_topic 호출 안 함** ★

### 1-3. supervisor `_ensure_chroma_ns` (L161-186) — state 만 mutate, env 무관

```python
topic_slug_raw = (state.get("topic_slug") or _cfg_str("TOPIC_SLUG", "") or "default")
env_ns_raw     = _cfg_str("CHROMA_NAMESPACE", "")
ns_web_raw     = _cfg_str("CHROMA_NAMESPACE_WEB", "")
ns_loc_raw     = _cfg_str("CHROMA_NAMESPACE_LOCAL", "")
...
state["chroma_ns"] = ns
state["flags"]["chroma"] = chroma  # ns/dir/ns_web/ns_local 저장
```

→ **`_ensure_chroma_ns` 는 CFG 를 read 만, env mutate 없음**. 단, **CFG 가 venfobel-vitamin-oa-web 으로 mutate 된 후 호출되면 state 에도 venfobel 전파** (간접 결과).

### 1-4. vector_search L705-710 ns 결정 logic

```python
# L705
topic_slug_raw = (state.get("topic_slug") or getattr(config.CFG, "TOPIC_SLUG", "") or "default").strip()
env_ns_raw    = (_cfg_str("CHROMA_NAMESPACE", "") or "").strip()
topic_slug    = _wr_sanitize_ns(topic_slug_raw)
env_ns        = _wr_sanitize_ns(env_ns_raw) if env_ns_raw else ""
ns: str       = env_ns or _wr_sanitize_ns(f"{topic_slug}-default")
# L715
ns_web_raw = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()
ns_loc_raw = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()
```

→ `ns` = CFG.CHROMA_NAMESPACE (set 시) **OR** `{topic_slug}-default`. `ns_web` = CFG.CHROMA_NAMESPACE_WEB (set 시) ELSE empty (auto-derive 는 dual_retrieve L398-404 에서 `{ns_default}-web`).

### 1-5. supervisor node 정의 위치 + invoke chain step

| location | role |
|---|---|
| `agent/supervisor.py` | supervisor node 정의 (전체 L1-~1200) |
| `app.py:2380` | `state["topic_slug"] = args.topic_slug` (**driver 단일 mutate 위치** — wrapper subprocess 에는 영향 무) |
| `app.py:2342` | `os.environ["TOPIC_SLUG"] = args.topic_slug` (**driver env mutate** — 자식 spawn 전에만) |
| `core/topic.py:107` | `state["topic_slug"] = slug` (start_new_topic 내부, 본 case 호출 안 됨) |

**state["topic_slug"] mutate grep (전체)** = 위 3건뿐. **invoke chain 안 mutate 없음** ★.

### 1-6. (H) 결론

- state["topic_slug"] = "ai-generated-creative-ad-platforms" **유지** (mutate 없음)
- vector_search L710 ns 의 venfobel resolve 는 **state 가 아닌 CFG.CHROMA_NAMESPACE mutate** 에서 옴 ★

---

## § 2. 작업 2 — (I) CFG / state mutate 위치 박제

### 2-1. `os.environ["CHROMA_NAMESPACE*"]` mutate (production)

| location | mutate 조건 |
|---|---|
| `core/topic.py:141` | `MIRROR_STATE_TO_ENV=True` AND start_new_topic 호출 시 |

→ wrapper 의 driver 가 `MIRROR_STATE_TO_ENV=0` set + start_new_topic 호출 안 됨 → **본 mutate 발화 안 함** ★ (B-2ext2 envdump STAGE_2 에서 CHROMA_NAMESPACE 부재 박제 정합).

### 2-2. CFG.CHROMA_NAMESPACE_WEB mutate path (`_cfg_str` 우회 가능성 포함)

| read | mutate 가능 path |
|---|---|
| `core/config.py:480` | `_env_str("CHROMA_NAMESPACE_WEB", "")` (CFG 인스턴스 build 시 os.environ read) |
| `core/config.py:450-451` | `if not (self.CHROMA_NAMESPACE_WEB or "").strip(): self.CHROMA_NAMESPACE_WEB = f"{slug}-web"` (__post_init__ auto-derive) |
| `core/config.py:650-669` | **`reload_config_inplace()` — `_build_config()` 호출 → CFG dataclass 의 field 재할당 (in-place)** ★★★ |

→ **CFG.CHROMA_NAMESPACE_WEB 의 production mutate path = `reload_config_inplace()` 단일 진입점** ★★★.

### 2-3. `reload_config_inplace()` 호출 chain 박제 (★ root cause path)

```python
# core/config.py L650-669
def reload_config_inplace() -> Config:
    with _cfg_lock:
        if _DOTENV_READY:
            load_dotenv(find_dotenv(usecwd=True), override=True)  # ★ 글로벌 .env override=True
            _apply_provider_overlay(verbose=False)  # ★ .env.<provider> override=True
            _apply_topic_preset(verbose=False)      # ★ topics/<slug>.env override=True
        new_cfg = _build_config()
        for f in fields(CFG):
            setattr(CFG, f.name, getattr(new_cfg, f.name))  # CFG in-place 갱신
        return CFG
```

| caller | line | invoke chain 안 발화? |
|---|---|---|
| **`tools/web_rag/search.py:1367`** | `reload_config()` (`web_search()` 함수 진입 시) | **★ YES** (web_search_agent invoke 시 web_search() 호출됨) |
| **`tools/local_rag.py:252`** | `reload_config()` (`ensure_config_fresh()` — process 당 1회 가드) | **★ YES** (local_rag 함수 호출 시 1회) |
| `tools/web_rag/utils.py:168` | `_reload_config()` (refresh_runtime_config 내부) | conditional |
| `app.py:2207, 2282` | driver main path | wrapper subprocess 무관 |
| `scripts/measure_stability.py:455, 457, 463` | 측정 script | production 무관 |

→ **invoke chain 안 `reload_config()` 호출이 web_search.py 와 local_rag.py 양쪽에 존재** ★.

### 2-4. `topic_slug` mutate (state / env, production)

```
state["topic_slug"] = ... :
  - app.py:2380 (driver, wrapper subprocess 무관)
  - core/topic.py:107 (start_new_topic 내부, 본 case 호출 안 됨)

os.environ["TOPIC_SLUG"] = ... :
  - app.py:2342 (driver, wrapper subprocess 무관)
```

→ **invoke chain 안 state/env topic_slug 직접 mutate 없음** ★.
→ 단, `reload_config_inplace()` 의 `load_dotenv(.env, override=True)` 가 글로벌 `.env L50: TOPIC_SLUG=venfobel-vitamin` 을 적용하여 **os.environ["TOPIC_SLUG"] 을 간접 mutate**. ★★★

### 2-5. venfobel hardcode 재확인 (env 외)

| location | 박제 |
|---|---|
| `.env.openai L56-58` (production 글로벌 .env 의 `LLM_PROVIDER=openai` overlay 시 load) | CHROMA_NAMESPACE=venfobel-vitamin-oa, _WEB=...-oa-web, _LOCAL=...-oa-local |
| `.env.anthropic L50-52` (anthropic overlay) | 동등 hardcode |
| 글로벌 `.env L50` | **★ `TOPIC_SLUG=venfobel-vitamin`** (static default) |
| `topics/venfobel-vitamin.env` | TOPIC_TITLE/KEYWORDS, MERGE_RETRIEVE_MODE=local_first, RETRIEVE_WEB_RATIO=0.33, RAG_TOP_K=10 |
| 진단/측정 script (check_chunks.py, scripts/regen_*, scripts/verify_*) | production 무관 |
| `agent/supervisor.py:132,625` | 주석 only |
| `agent/export/cli.py:79` | help text only |
| `core/llm.py:113` | 주석 only |

→ **production code 에 venfobel-vitamin* hardcode 부재** — 모든 venfobel 자원은 `.env` 또는 `topics/*.env` 의 정적 default ★.

### 2-6. `ChatVertexAI` 인스턴스화 + model 인수 mutate

| location | line | context |
|---|---|---|
| `core/llm.py:145` | `from langchain_google_vertexai import ChatVertexAI as _ChatVertexAI` | import (vertex provider 분기) |
| `core/llm.py:156` | `out["ChatCtor"] = cast(..., _strip_kwargs_for_vertex(_ChatVertexAI))` | factory |
| `core/llm.py:393-394` | `kwargs_candidates = _build_vertexai_kwargs(m, temperature, extra)` (m = model or CFG.LLM_MODEL or "gemini-2.5-flash") | kwargs build |
| `core/llm.py:138` | `out["DefaultChatModel"] = "gemini-2.5-flash"` (vertex 분기 default) | default |

→ **ChatVertexAI 의 model 인수 mutate 위치 = `get_llm()` L327 `m = model or getattr(config.CFG, "LLM_MODEL", None) or "gemini-2.5-flash"`** — CFG.LLM_MODEL 이 mutate 되면 m 도 mutate.

### 2-7. (I) 결론

- **CFG.CHROMA_NAMESPACE_WEB mutate path = `reload_config_inplace()` 단일** ★
- **invoke chain 안 호출처 = `tools/web_rag/search.py:1367` + `tools/local_rag.py:252`** ★
- mutate 메커니즘: `load_dotenv(.env, override=True)` → 글로벌 `.env L2 LLM_PROVIDER=openai`, `L50 TOPIC_SLUG=venfobel-vitamin` 이 driver-set 값을 덮어씀 → `_apply_provider_overlay` 가 `.env.openai` load → CHROMA_NAMESPACE_WEB=venfobel-vitamin-oa-web 도입 ★★★

---

## § 3. 작업 3 — vertex_grounding 호출 chain 박제

### 3-1. `agent/web_search.py:766` 호출 chain

```python
# web_search.py L764-766
if attempt == 0 and query and not _cfg_bool("SKIP_VERTEX_SEARCH", False):
    try:
        vertex_result = vertex_web_search(query)
```

→ `vertex_web_search(query)` 만 호출. **model 인수 명시 전달 무** — vertex_web_search 가 env 에서 read.

### 3-2. `vertex_web_search` 내부 model 결정 (`tools/web_rag/vertex_search.py:112`)

```python
# vertex_search.py L112, L125-129
model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
...
response: Any = client.models.generate_content(
    model=model_name,
    contents=query,
    config=config,
)
```

→ **`vertex_web_search` 는 `os.getenv("LLM_MODEL", ...)` 직접 read** (CFG 또는 get_llm() 우회) ★★★.
→ 즉 **`os.environ["LLM_MODEL"]` 가 mutate 되면 vertex_grounding 의 model 인수도 mutate**.

### 3-3. `os.environ["LLM_MODEL"]` mutate path

| location | mutate 가능? |
|---|---|
| `core/config.py:660` `load_dotenv(find_dotenv(usecwd=True), override=True)` (reload_config_inplace 내부) | **★ YES** — 글로벌 `.env L3: LLM_MODEL=gpt-4o` 가 적용됨 |
| `core/config.py:664` `_apply_provider_overlay` (override=True) | YES — `.env.openai`/`.env.vertex` 의 LLM_MODEL (vertex 는 gemini-2.5-flash) |
| `scripts/measure_*.py` `os.environ["LLM_MODEL"] = ...` | production 무관 |

→ 글로벌 `.env L3 LLM_MODEL=gpt-4o` (driver 가 `gemini-2.5-flash` 로 명시 set 했지만) **reload_config_inplace 후 덮어쓰기** ★★★.
→ `_apply_provider_overlay` 가 직후에 호출되어 `.env.openai` (LLM_MODEL 키 없음) 또는 `.env.vertex` (gemini-2.5-flash) 를 load. **하지만 reload 시 LLM_PROVIDER 도 vertexai→openai 로 바뀜** → `.env.openai` overlay → LLM_MODEL 은 덮어쓰지 않음 (`.env.openai` 에 LLM_MODEL 키 없음) → **L3 의 gpt-4o 유지** ★.

### 3-4. ChatVertexAI default model fallback 위치

- vertex 분기 (core/llm.py L133-159):
  - L135: `out["ChatModelKey"] = "LLM_MODEL"`
  - L138: `out["DefaultChatModel"] = "gemini-2.5-flash"`
- get_llm() L327: `m = model or getattr(config.CFG, "LLM_MODEL", None) or "gemini-2.5-flash"`
- **하지만 vertex_web_search 는 get_llm() 을 호출하지 않음** — 직접 google-genai client 사용 + `os.getenv("LLM_MODEL")` 직접 read.

### 3-5. (F-β) 표기 명확화

| 표기 | 본 cycle 결과 |
|---|---|
| (F-α) LLM_MODEL env 가 vertex_grounding 도구에 전달 안 됨 | **기각** |
| (F-β) provider 분기 path divergence | **부분 기각 정정** — get_llm() L327 vertex 분기는 정상이지만, **env-mutation 차원의 divergence 존재** (reload_config_inplace 가 LLM_PROVIDER 를 vertexai→openai 로 mutate 시 `.env.openai` overlay 가 load 되고, LLM_MODEL 은 글로벌 `.env L3 gpt-4o` 유지). **즉 (F-β) 는 "code 분기 divergence" 가 아니라 "env mutate 후 분기 divergence" 로 정확화** ★ |
| (F-γ) vertex_search.py 내부 chain mutate | **기각** (L112 default = gemini-2.5-flash, 정상 logic) |
| (F-δ) wrapper env LLM_MODEL invoke 직전 mutate | **★ CONFIRMED** — `reload_config_inplace()` 가 invoke 진행 중 글로벌 `.env L3 LLM_MODEL=gpt-4o` 로 mutate ★★★ |
| (F-ε) LangChain ChatVertexAI / 다른 vertex API path | **기각** — vertex_web_search 는 google-genai 사용 (LangChain 미사용) |
| (F-ζ) `[web_search] Vertex failed:` log 다른 source | **기각** — agent/web_search.py L812 `logger.warning("[web_search] Vertex failed: %s", e)` 가 동일 source |

→ **mystery 2 root cause = (F-δ) — `reload_config_inplace()` 가 글로벌 `.env L3 LLM_MODEL=gpt-4o` 를 덮어씀** ★★★.

---

## § 4. 작업 4 — 추가 grep 결과

### 4-1. `RAG_NAMESPACE` / `RAG_COLLECTION`

| location | 박제 |
|---|---|
| `scripts/output/§14-8/§14-8-A_close_summary.md:139` | 주석 — production 부재 |

→ **production code 에 `RAG_NAMESPACE` / `RAG_COLLECTION` 사용 부재** ★.

### 4-2. `collection_name=` parameter

| location | 박제 |
|---|---|
| `tools/web_rag/ingest_vector.py:324,1477,1526,1814,1840` | Chroma `collection_name` 파라미터, ns 우선 사용 |
| `tools/sample_chunks_for_eval.py:66` | 측정 script |
| `scripts/_phase_b_run_inner.py:83` | 측정 script |
| `tools/web_rag/ingest_vector.py:1578` | `_resolve_ns(namespace=namespace, collection_name=collection_name)` — explicit > resolve |

→ `collection_name` 은 ingest_vector.py 내부 ns resolution helper 의 explicit arg. **invoke chain 안 venfobel hardcode 부재**.

### 4-3. `chromadb.PersistentClient` 인스턴스화 위치

| location | 박제 |
|---|---|
| `utils/rag_utils.py:501` | `client = chromadb.PersistentClient(path=p)` — 일반 client init (path 는 caller 결정) |
| `check_chunks.py:3` | 진단 script |
| `scripts/output/§14-3/_phase3/_chroma_diag.py:16,49` | 진단 script |

→ production 단일 인스턴스화 = `utils/rag_utils.py:501`. **venfobel hardcode 부재**.

### 4-4. `LLM_PROVIDER` 사용처

| location | 박제 |
|---|---|
| `core/config.py:107-127` | `_apply_provider_overlay` — **`.env.<LLM_PROVIDER>` file load 의 분기 결정** ★★★ |
| `core/config.py:595` | `LLM_PROVIDER=_env_str("LLM_PROVIDER", "openai").lower()` (CFG 인스턴스 build) |
| `core/llm.py:41` | `_provider()` — get_llm() 의 분기 결정 |
| `core/llm.py:82-161` | provider 분기 (openai/gemini/anthropic/vertexai) |
| `agent/section_writer.py:278` | `_llm_provider = _cfg_str("LLM_PROVIDER", "")` |
| `agent/export/planner.py:126` | export planner |
| `tools/web_rag/vertex_search.py:14,105` | docstring + log msg |
| `tools/web_rag/ingest_vector.py:796` | `getattr(CFG, "LLM_PROVIDER", "")` |

→ **`LLM_PROVIDER` mutate 가 가장 큰 영향을 갖는 위치 = `_apply_provider_overlay` (overlay file 선택 분기)** ★★★.
→ **글로벌 `.env L2 LLM_PROVIDER=openai` 가 reload 시 driver-set `vertexai` 를 덮어쓰면 → `.env.openai` overlay 가 load** → CHROMA_NAMESPACE* 가 venfobel-vitamin-oa* 로 set ★★★.

---

## § 5. 두 mystery 통합 mechanism 박제 (★ root cause)

### 5-1. 시간축 박제

| 단계 | 시점 | 상태 |
|---|---|---|
| **T0** | driver wrapper spawn 직전 | env: TOPIC_SLUG=ai-generated..., LLM_PROVIDER=vertexai, LLM_MODEL=gemini-2.5-flash, MIRROR_STATE_TO_ENV=0, CHROMA_NAMESPACE* pop 됨 |
| **T1 (STAGE_1)** | 자식 python 진입 | T0 env 그대로 (B-2ext2 envdump 정합) |
| **T2 (STAGE_2)** | `load_dotenv(.env.vertex, override=True)` (script L62) | + RAG_DISTANCE_THRESHOLD=0.65, OPENAI_API_KEY="" 추가. LLM_PROVIDER/LLM_MODEL/TOPIC_SLUG 유지 |
| **T3** | `import core.config` → `_load_dotenv_once()` | global `.env` load(override=**False**, 무변) → `.env.vertex` overlay → `topics/ai-generated-creative-ad-platforms.env` preset. CFG.TOPIC_SLUG=ai-generated..., CFG.CHROMA_NAMESPACE auto-derive = ai-generated-creative-ad-platforms |
| **T4** | `graph.invoke(state)` 시작 | (envdump 미포착 — STAGE_3+ gap) |
| **T5 ★★★** | `web_search_agent` 안에서 `tools/web_rag/search.py:1367` `reload_config()` 호출 | `reload_config_inplace()` 발화: `load_dotenv(.env, override=**True**)` → **LLM_PROVIDER=vertexai→openai, LLM_MODEL=gemini-2.5-flash→gpt-4o, TOPIC_SLUG=ai-generated→venfobel-vitamin, SKIP_VERTEX_SEARCH=0→1 모두 덮어쓰기** ★★★ |
| **T6** | `_apply_provider_overlay(verbose=False)` (LLM_PROVIDER=openai) | `.env.openai` load(override=True) → CHROMA_NAMESPACE=venfobel-vitamin-oa, _WEB=...-oa-web, _LOCAL=...-oa-local, OPENAI_MODEL=gpt-4o ★★★ |
| **T7** | `_apply_topic_preset(verbose=False)` (TOPIC_SLUG=venfobel-vitamin) | `topics/venfobel-vitamin.env` load(override=True) → TOPIC_TITLE/KEYWORDS, MERGE_RETRIEVE_MODE=local_first, RETRIEVE_WEB_RATIO=0.33, RAG_TOP_K=10, BLOCKAGI_OBJECTIVE_1~5 |
| **T8** | `_build_config()` 재build + CFG field 재할당 | CFG.CHROMA_NAMESPACE_WEB="venfobel-vitamin-oa-web", CFG.LLM_PROVIDER="openai", CFG.TOPIC_SLUG="venfobel-vitamin", CFG.LLM_MODEL="gpt-4o" 등 |
| **T9** | `vertex_web_search(query)` 호출 시 L112 `model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")` | **"gpt-4o"** ★ → Vertex generate_content(model="gpt-4o") → **404 NOT FOUND** ★★★ |
| **T10** | `vector_search_agent` L715 `_cfg_str("CHROMA_NAMESPACE_WEB", "")` | **"venfobel-vitamin-oa-web"** ★★★ → dual-retrieve 의 ns_web 으로 사용 |

→ **두 mystery 동일 mechanism (T5 의 `reload_config_inplace`) 으로 통합 박제** ★★★

### 5-2. state["topic_slug"] vs CFG.TOPIC_SLUG 차이

- state["topic_slug"] = "ai-generated-creative-ad-platforms" — **mutate 없음** (start_new_topic 호출 안 됨)
- CFG.TOPIC_SLUG = "venfobel-vitamin" — **T5-T8 에서 mutate**
- vector_search L705 reads **state.get("topic_slug")** = "ai-generated..." ← state 우선 → topic_slug 변수 = "ai-generated..."
- vector_search L706 reads `_cfg_str("CHROMA_NAMESPACE")` → CFG.CHROMA_NAMESPACE = "venfobel-vitamin-oa" → env_ns="venfobel-vitamin-oa"
- vector_search L710 `ns = env_ns or {topic_slug}-default` → **env_ns 우선 → ns="venfobel-vitamin-oa"** ★
- → 실측 log `[CHECK][dual-retrieve][count] ... base=0 (ns=venfobel-vitamin-oa)` 완전 정합 ★

### 5-3. (γ) 가설 재평가 — **measurement gap 인정** ★

| 시점 | (γ) 평가 | 정확성 |
|---|---|---|
| B-1ext (priors 5-6번째) | "(γ) wrapper 환경에서 .env.openai 가 어디서 load" 가설 제안 | **방향 정확** |
| B-2ext2 envdump STAGE_1/2 | OPENAI_MODEL/CHROMA_NAMESPACE_WEB 부재 → "(γ) **기각 확정** (9번째 priors)" | **잘못된 기각** — STAGE_3+ (invoke 안의 reload_config_inplace 발화 후) 미포착 |
| B-2ext3 (본 cycle) | (γ) **정정 확인** — `.env.openai` 는 실제로 load 되지만 **자식 script L62 가 아닌 invoke 안의 reload_config_inplace 에서 발화**. envdump 측정 시점이 발화 전이라 측정에서 누락됨 ★★★ | **(γ) 확정 (정정)** |

→ B-2ext2 의 "priors 기각 9번째" 는 **measurement gap 에 의한 false negative** — 본 cycle 에서 정정 ★.

### 5-4. (B-1ext α) 가설 재평가

- (α) "wrapper subprocess 안에서 어딘가 reload_config() 호출 → CFG mutate" — **CONFIRMED** ★ (tools/web_rag/search.py:1367 + tools/local_rag.py:252)
- (α) 와 (γ) 는 독립이 아니라 **단일 mechanism 의 두 측면** — (α) reload trigger + (γ) overlay 결과.

---

## § 6. 분기표 안 vs 밖

### 6-1. 본 mission 분기표 안 (직접 박제 대상)

- (가-mechanism 박제) → B-3 fix-path 정확 설계 진입 — **본 cycle 결과: 가** ★

### 6-2. 분기표 밖 cell (자기 비판 §1 박제)

| 항목 | 박제 |
|---|---|
| **envdump-style 측정의 한계** | STAGE_1/2 만 포착, STAGE_3+ 미포착 → invoke 안 mutation 측정 불가 ★ |
| **"priors 기각 확정" 의 위험성** | 9번째 priors (γ 기각) 가 measurement gap 에 의해 false negative 였음 — **"기각 확정" 단언 전 측정 범위 검증 필수** ★ |
| **multi-step env mutation chain** | 단일 envdump 로 mutation chain 의 모든 step 포착 불가 — **STAGE-aware envdump** (각 reload_config() 호출 직후 envdump) 가 정확 ★ |
| **load_dotenv(override=True) 의 의도하지 않은 회귀** | driver wrapper 가 명시 set 한 env vars 가 production code 의 reload_config_inplace 에서 글로벌 .env 정적 default 로 회귀 — **driver convention 의 implicit 가정이 production code 와 충돌** ★ |

---

## § 7. fix candidate 재평가 (mechanism 박제 기반)

### 7-1. mechanism 박제 결과 새 fix candidate

| candidate | 위치 | 효과 | 평가 |
|---|---|---|---|
| **(O 신규 ★★★)** `reload_config_inplace()` 의 global `.env` 재로드를 `override=False` 로 변경 또는 wrapper-protected env list 도입 | `core/config.py:660` | **root cause fix** — driver-set env 보호. wrapper/runpy 동일 거동 보장 | ★★★ 최우선 |
| **(P 신규)** 글로벌 `.env L2 LLM_PROVIDER=openai`, `L50 TOPIC_SLUG=venfobel-vitamin` 제거 또는 placeholder 화 (예: `# LLM_PROVIDER=` 주석) | 글로벌 `.env` | implicit default 제거 — driver convention 강제 | 中 — `.env` 의 dev UX 영향 |
| (B) CFG.CHROMA_NAMESPACE_WEB auto-derive 강화 (TOPIC_SLUG mismatch 시 우선 derive) | `core/config.py:440-453` | mutate 발생해도 final value 정합 보장 | 中 — root cause 우회만 |
| (M) `_apply_provider_overlay` 가 driver-protected env 존중 | `core/config.py:106-127` | partial fix | 中 |
| **(C) embedding 일치성 검증** | `agent/vector_search.py _call_retrieve` | **mutate 결과 후 timeout 회피만** (root cause 아님) | ★ wrapper safety net 으로 유지 |
| (F-1/F-2/F-3) vertex 404 fix | vertex_search.py / web_search.py / core/llm.py | (O) fix 적용 시 자동 해소 | bypass |
| (D) `.env.openai` hardcode 제거 | `.env.openai L56-58` | (O) fix 시 무관 (overlay 자체가 load 안 됨) | 不要 |

### 7-2. 우선순위

1. **(O ★★★)** `reload_config_inplace()` override=False or protected env list — **root cause fix, 단일 patch 로 두 mystery 동시 해소**
2. **(C)** embedding 일치성 검증 — wrapper safety net (B-2 § 3.2 한계 박제 그대로 유지)
3. (P) 글로벌 `.env` static default 제거 — config hygiene
4. (B) CFG auto-derive 강화 — defense-in-depth

### 7-3. (가) B-3 entry 권장

- B-3 fix-path = (O) `reload_config_inplace()` 수정 + (C) 적용 dual-path
- 또는 (C) 적용 + (O) 별 patch (시간 분산)

---

## § 8. priors 기각 정정 + 진단 가치 박제

### 8-1. priors 기각 누적 정정

| # | priors | 기존 평가 | 본 cycle 정정 |
|---|---|---|---|
| 1 | case B 유력 | 기각 | (유지) |
| 2 | C timeout 의외로 유력 | 기각 | (유지) |
| 3 | D2 빠른 fail 예상 | 기각 | (유지) |
| 4 | driver wrapper #1/#2 高 의심 | 기각 | (유지) |
| 5 | vertex 404 gpt-4o (분기표 외) | 신규 발견 | (유지) |
| 6 | chroma embedding mismatch (분기표 외) | 신규 발견 | (유지) |
| 7 | fix C 추가 가치 (기존 handling 작동) | 부분 기각 | (유지) |
| 8 | (F-β) provider 분기 가장 유력 | 부분 기각 | **★ 정정** — env-mutation level 에서 confirmed (정확화) |
| 9 | (γ) `.env.openai` load 가장 유력 | 기각 확정 (9번째 priors) | **★ 정정 — false negative, measurement gap (STAGE_3+ 미포착) 에 기인. (γ) 실제 CONFIRMED** ★★★ |
| 10 | (B-1ext β) supervisor start_new_topic mutate path | 기각 (직전 B-2ext3) | (유지) — start_new_topic 호출 안 됨 |
| **11 (신규)** | **mystery 2건 단일 mechanism 박제 (`reload_config_inplace` + global `.env` override=True)** | — | **★ CONFIRMED (본 cycle)** |

### 8-2. 본 cycle 의 진단 가치

- **시간 box 1 round 정합** — grep + read + 분석으로 mechanism 완전 박제 (~30 min 비용)
- **root cause level 박제** — 두 mystery 단일 mechanism 통합 ★★★
- **measurement protocol 자산화** — envdump 의 STAGE 범위 한계 박제 → 향후 mystery 진단 시 "envdump-style 직접 측정 우선" priors 도 보완 필요 (각 reload_config() 호출 직후 envdump 추가)
- **(γ) priors 정정** — "기각 확정" 의 false negative 가능성 인정 → 자기 비판 §1 강화 (10건 → 정정 포함 11건)

---

## § 9. 시나리오 결정 + Claude Code 권장

### 9-1. 사용자 plan 분기 정합

> mechanism 박제 → fix-path 정확 설계 (B/D/E/F 또는 신규) → B-3 진입
> mystery 미박제 → fix C fallback (A 옵션) → B-3 진입

→ **본 cycle 결과 = mechanism 완전 박제** → **(가) 분기 — fix-path 정확 설계 후 B-3 진입** ★

### 9-2. Claude Code 권장 — **신규 (시나리오 6 — root cause fix)**

**시나리오 6 (root cause fix B-3 진입)**:
- (O) `reload_config_inplace()` override=True → override=False (또는 protected env list) — root cause fix
- (C) embedding 일치성 검증 — wrapper safety net 으로 병행 적용
- B-4 효과 측정 — wrapper 환경에서 vertex 404 + venfobel namespace 둘 다 사라져야 정합
- 효과 충분 → 본 미션 close + priors 정정 11번째 박제

**시나리오 6 risk**:
- (O) 의 override=False 변경이 다른 production flow 에 회귀 유발 가능 (예: 토픽 변경 시 .env 재 read 안 됨)
- → mitigation: protected env list (LLM_PROVIDER, LLM_MODEL, TOPIC_SLUG 등) 만 보호 + 나머지는 기존 override=True 유지

**시나리오 1 (기존 — fix C fallback)** 도 진행 가능:
- (C) 단독 적용 — wrapper timeout 회피만, root cause 잔존
- 효과 부족 시 별 cycle 에서 (O) 적용

### 9-3. user 컨펌 Q list

**Q1.** § 5.1 시간축 박제 — **두 mystery (CFG.CHROMA_NAMESPACE_WEB=venfobel-vitamin-oa, vertex API gpt-4o) 단일 mechanism (`reload_config_inplace` at T5) 으로 통합 박제** 합의 OK?

**Q2.** § 5.3 — **(γ) priors 기각 9번째 정정** (false negative, measurement gap by envdump STAGE_3+ 미포착) 합의 OK?

**Q3.** § 6.2 분기표 밖 cell — **envdump-style 측정 한계 (단일 envdump 의 STAGE 범위 한계, "기각 확정" 단언 risk)** 자산화 합의 OK?

**Q4.** § 7 fix candidate 우선순위:
- **(O ★★★) `reload_config_inplace()` override=True → override=False (또는 protected env list)** — root cause fix
- **(C) embedding 일치성 검증** — wrapper safety net (병행)
- (P) 글로벌 `.env` static default 제거 — config hygiene
- (B) CFG auto-derive 강화 — defense-in-depth

합의 OK?

**Q5.** § 9.2 — **시나리오 6 (root cause fix B-3 진입)** Claude Code 권장 합의 OK?
- (O) + (C) dual-path
- (시나리오 1 fix C 단독) 도 진행 가능 — 효과 부족 risk 박제

**Q6.** § 8 priors 정정 11번째 (mystery 2건 단일 mechanism 박제) + 진단 가치 박제 합의 OK?
