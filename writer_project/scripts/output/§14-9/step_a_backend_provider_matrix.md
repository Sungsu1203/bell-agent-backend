# §14-9 Step A — search backend × LLM provider matrix (read-only 박제)

- entry: §12-13 close 후 자연 분기 (HEAD 8258f3c)
- branch: main, working dir: D:\gpt_agent\writer_project
- read-only — file edit / commit 0
- scope: Task 1~5 식별만, chain test (Step B) 는 별 round

---

## § 1. Search backend inventory

### 1-a. backend 목록 (5종 + 1 변종)

| key | impl | cred (env) | gate |
|---|---|---|---|
| `vertex_grounding` | `tools/web_rag/vertex_search.py:88-194` `vertex_web_search()` | `GCP_PROJECT_ID`, `GCP_REGION`, `GOOGLE_APPLICATION_CREDENTIALS` | `SKIP_VERTEX_SEARCH` + pkg `google-genai` 존재 여부 (`_GENAI_AVAILABLE`, vertex_search.py:15-32) |
| `naver_direct` | `tools/web_rag/search.py:826-899` `_search_naver_direct()` | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | credential presence (search.py:827-831) |
| `tavily` | `tools/web_rag/search.py:594-631` `_search_tavily()` | `TAVILY_API_KEY` | `CFG.HAS_TAVILY` + key (search.py:595-596) |
| `google_cse` | `tools/web_rag/search.py:633-789` `_search_google_cse()` + `_search_google_cse_with_meta()` | `GOOGLE_API_KEY` (또는 `GOOGLE_CSE_API_KEY`), `GOOGLE_CSE_ID` (또는 `GOOGLE_CSE_CX`) | key 동시 존재 (search.py:634-639) |
| `serpapi` (google) | `tools/web_rag/search.py:791-824` `_search_serpapi()` | `SERPAPI_API_KEY` | `CFG.HAS_SERPAPI` (search.py:792-794) |
| `serpapi_naver` | `tools/web_rag/search.py:901-979` `_search_serpapi_naver()` | `SERPAPI_API_KEY` (+ `SERPAPI_NAVER_*` 튜닝) | key + 쿼리 simplify (search.py:902-911) |

내부 dispatcher: `_backend_call()` `search.py:1261-1274`.
Alias 정규화: `_normalize_backend_alias()` `search.py:1276-1288` (`google` → `google_cse`, `naver` → `serpapi_naver`, etc.).

### 1-b. caller chain + entry point

```
graph.py:101  _add_node("web_search_agent", web_search_agent)
       │
       ▼
agent/web_search.py:171  web_search_agent(state)
       │
       ▼  _run_web_search_with_guard()  web_search.py:727-1054
       │
       ├── (attempt==0, !SKIP_VERTEX_SEARCH) → vertex_web_search()         vertex_search.py:88
       │        web_search.py:764-812   result → combined_items["backend"="vertex_grounding"] (L793)
       │
       └── (always)                       → web_search.invoke()            search.py:1335 (@tool)
                web_search.py:819-850     ↓
                                          _resolve_backend_chain()         search.py:1294-1331
                                          ↓ chain loop
                                          _backend_call(bk, …)             search.py:1261-1274
                                          ↓
                                  tavily / naver_direct / google_cse / serpapi*
```

LLM planner tool-call path: `web_search.py:1144` `llm_with_web = llm.bind_tools([web_search])`; planner LLM 이 `web_search` tool-call 인자(query) 만 생성, 실제 search 호출은 동일 `_run_web_search_with_guard()` 진입 (web_search.py:1147-1170).

### 1-c. fallback / selection 로직

| 단계 | 위치 | 동작 |
|---|---|---|
| Vertex 우선 (attempt 0) | web_search.py:764-812 | `SKIP_VERTEX_SEARCH=0` 시 1회 호출. 실패해도 legacy 진입 (continue) |
| Legacy chain resolve | search.py:1294-1331 | `WEB_SEARCH_ENGINE` env > `CFG.SEARCH_BACKENDS`/`SEARCH_BACKENDS` env > default `naver_direct,tavily` (search.py:1304) |
| KR-context 강제 prefix | search.py:1479-1487 | `_looks_korean(query)` 일 때 `naver_direct` 를 chain 맨 앞으로 |
| Naver 예약 budget | search.py:1503-1521 | `_naver_reserved=4.0s`; 다른 backend 가 budget 초과 직전이면 skip + Naver 후순위 보장 |
| Forced Naver retry | search.py:1687-1697 | 결과 비고 KR + chain 미실행 시 1회 강제 `naver_direct` |
| Best-of-chain stop | search.py:1796-1818 | `SEARCH_POLICY=best_of_chain` (CFG default) 시 `SEARCH_MIN_OK` 만족 + min_backends 도달 후 early stop |

→ Vertex grounding 과 legacy chain 은 **병렬 합산** (web_search.py:758-853, `combined_items.extend(legacy_items)` L846-850). Legacy 내부에서만 `naver_direct ↔ tavily ↔ google_cse` 직렬 fallback.

---

## § 2. Provider × backend coupling matrix

### 2-a. `_apply_provider_overlay` 동작

`core/config.py:106-127`. 글로벌 `.env` 로드 직후 / 토픽 프리셋 직전에 1회 적용. 우선순위: **topic > overlay > 글로벌**.

```
prov = LLM_PROVIDER.lower()
prov_file = "vertex" if prov in {"vertex","vertexai"} else prov   # config.py:116
overlay = $PROJECT_ROOT/.env.<prov_file>   # 없으면 silent skip
load_dotenv(overlay, override=True)
```

확인된 overlay 파일 (실측):
- `.env.openai` (58 lines) — `LLM_PROVIDER=openai`, `OPENAI_MODEL=gpt-4o`, `SKIP_VERTEX_SEARCH=0` (L49), Chroma ns `-oa` 접미사 (L56-58)
- `.env.vertex` (51 lines) — `LLM_PROVIDER=vertexai`, `LLM_MODEL=gemini-2.5-flash`, `OPENAI_API_KEY=` (차단, L41), `VERTEX_MAX_RETRIES=0` (L28)
- `.env.anthropic` (52 lines) — `LLM_PROVIDER=anthropic`, `ANTHROPIC_MODEL=claude-haiku-4-5-20251001` (현재) 또는 `claude-sonnet-4-6` (L19 주석), `SKIP_VERTEX_SEARCH=1` (L45), `ANTHROPIC_MAX_RETRIES=0` (L31)

### 2-b. Matrix

| provider | overlay | LLM_MODEL | SKIP_VERTEX_SEARCH (overlay) | venv | embed model / dim | Chroma ns |
|---|---|---|---|---|---|---|
| openai | `.env.openai` | OPENAI_MODEL=gpt-4o | **0** (L49) | `.venv_openai` | text-embedding-3-large / 3072 | venfobel-vitamin-oa{,-web,-local} |
| vertexai | `.env.vertex` | LLM_MODEL=gemini-2.5-flash | (명시 X — 글로벌 `.env:20`=1 정합 시 1, 토글 시 0) | `.venv_vertex` | text-multilingual-embedding-002 / 768 | venfobel-vitamin{,-web,-local} (default) |
| anthropic | `.env.anthropic` | ANTHROPIC_MODEL=claude-haiku-4-5-20251001 | **1** (L45) | `.venv_openai` 동거 | OpenAI text-embedding-3-large / 3072 fallback | venfobel-vitamin-oa{,-web,-local} |

### 2-c. env keys inventory (검색 영역)

| 영역 | 키 | 정의 위치 |
|---|---|---|
| provider toggle | `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_MODEL`, `GEMINI_MODEL`, `ANTHROPIC_MODEL` | config.py:343-372, llm.py:_load_provider |
| search gate | `SKIP_WEB_SEARCH`, `SKIP_VERTEX_SEARCH`, `WEB_SEARCH_ENGINE`, `SEARCH_BACKENDS` | config.py:245-247, 318; search.py:1300-1322 |
| search policy | `SEARCH_POLICY`, `SEARCH_MIN_OK`, `SEARCH_TOPN`, `SEARCH_MIN_BACKENDS`, `SEARCH_GL`, `SEARCH_HL` | config.py:242-244; search.py:645-647, 1513 |
| vertex grounding cred | `GCP_PROJECT_ID`, `GCP_REGION`, `GOOGLE_APPLICATION_CREDENTIALS` | vertex_search.py:52-58 |
| tavily | `TAVILY_API_KEY`, `TAVILY_TIMEOUT_SEC`, `TAVILY_RETRY_ON_TIMEOUT` | search.py:595, `.env`:87-95 |
| naver_direct | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `NAVER_DIRECT_WHERE`, `NAVER_DIRECT_SORT`, `NAVER_MAX_LEN`, `NAVER_MAX_TOKENS`, `NAVER_NEGATIVE_CAP`, `NAVER_TRIM_OPERATORS` | search.py:827-865, 1112-1180 |
| google_cse | `GOOGLE_API_KEY`/`GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_ID`/`GOOGLE_CSE_CX`, `GOOGLE_CSE_BASE_URL`, `GOOGLE_CSE_GL`, `GOOGLE_CSE_LR`, `GOOGLE_TIMEOUT_SEC` | search.py:20-23, 634-660, 745-758 |
| serpapi | `SERPAPI_API_KEY`, `SERPAPI_NAVER_NUM/HL/GL/WHERE/TRY_OTHERS` | search.py:792, 912-916 |

### 2-d. coupling 단언

- **search backend chain 자체는 provider-INDEPENDENT**: `SEARCH_BACKENDS` env/CFG 가 `LLM_PROVIDER` 와 무관하게 `_resolve_backend_chain()` 에 그대로 흘러감 (search.py:1300-1322 — 어디서도 `LLM_PROVIDER` 분기 부재).
- **vertex_grounding 만 venv-coupled**: `.venv_openai` / `.venv_anthropic` 동거 venv 에는 `google-genai` 미설치 → `_GENAI_AVAILABLE=False` → `vertex_web_search()` 가 `{"summary":"","urls":[],"raw_response":None}` 빈 dict 반환 (graceful, vertex_search.py:100-107).
- **SKIP_VERTEX_SEARCH 는 provider-coupled "의도" gate**: `.env.openai` 가 SKIP=0 로 두지만, `.venv_openai` 에서는 google-genai 부재로 silent skip. `.env.anthropic` 는 SKIP=1 로 명시 차단.
- **free combination**: 모든 (provider × legacy-backend) 조합이 코드 레벨에서 자유 — venv 와 cred 정합만 갖추면 됨.

---

## § 3. LLM model 활용 방식 (coupling 형태 분류)

### 3-a. provider 별 LLM client entry

| provider | ChatCtor | DefaultChatModel | 위치 | embed ctor |
|---|---|---|---|---|
| openai | `ChatOpenAI` (langchain_openai) | `gpt-4o` | llm.py:88-92 | `OpenAIEmbeddings` (llm.py:90-92) |
| gemini | `ChatGoogleGenerativeAI` (langchain_google_genai) | `gemini-2.5-pro` | llm.py:103-107 | `GoogleGenerativeAIEmbeddings` |
| anthropic | `ChatAnthropic` (langchain_anthropic) | `claude-sonnet-4-6` | llm.py:122-124 | `OpenAIEmbeddings` fallback (llm.py:126-127) — chat only |
| vertexai | `ChatVertexAI` (langchain_google_vertexai) + kwargs strip wrapper | `gemini-2.5-flash` | llm.py:145-157 | `VertexAIEmbeddings` |

Singleton: `_LLM` (llm.py:10), provider 캐시 `_LOADED[prov]` (llm.py:12, 68-70).
Entry: `get_llm()` llm.py:300-414 — 1) ctor 후보 kwargs 시도, 2) provider 별 timeout/max_retries 명시 (`_build_openai_kwargs`/`_build_anthropic_kwargs`/`_build_vertexai_kwargs` 234-298).

Model selection 우선순위 (llm.py:327): `직접 인자 model > CFG.<ChatModelKey> > DefaultChatModel`.
- openai: `CFG.OPENAI_MODEL` (env `OPENAI_MODEL`, default `gpt-4o`)
- vertex: `CFG.LLM_MODEL` (env `LLM_MODEL`, default `gemini-2.5-flash`)
- anthropic: `CFG.ANTHROPIC_MODEL` (env `ANTHROPIC_MODEL`, default `claude-sonnet-4-6`)
- gemini: `CFG.GEMINI_MODEL` (env `GEMINI_MODEL`, default `gemini-2.5-pro`)

### 3-b. search 호출 시점의 LLM coupling 분류

| 분류 | backend | 호출 형태 | LLM 결합 |
|---|---|---|---|
| **(i) LLM agent tool call — Vertex grounding 형** | `vertex_grounding` | `genai.Client(...).models.generate_content(model=gemini-2.5-flash, tools=[Tool(google_search=GoogleSearch())])` (vertex_search.py:115-129) | 검색 = LLM call. Gemini 가 query 받아 GoogleSearch tool 실행 + summary 작성. `writer_project` 의 `get_llm()` singleton 과 **무관** — 자체 `genai.Client` 사용 (vertex_search.py:62-68). |
| **(ii) 독립 SDK / HTTP call — 결과만 LLM context 주입** | `naver_direct` | `requests.get(openapi.naver.com)` (search.py:867-868) | LLM 0 |
| (ii) | `tavily` | `TavilyClient.search()` (search.py:604-612) | LLM 0 |
| (ii) | `google_cse` | `requests.get(customsearch.googleapis.com)` (search.py:760) | LLM 0 |
| (ii) | `serpapi*` | `serpapi.GoogleSearch(params).get_dict()` (search.py:805-806) | LLM 0 |

LLM planner 의 tool-call 경로 (web_search.py:1144-1170):
- `llm.bind_tools([web_search])` — planner LLM (=`get_llm()` singleton 의 현 provider) 이 query 만 emit
- 실제 search execution 은 `_run_web_search_with_guard()` 동일 진입 → (i)+(ii) 동일 합산
- 따라서 planner LLM 은 search result 를 직접 받지 않음 — query dispatch 만 함. **결합 분류 변경 없음**.

(i) 의 axis 의미: vertex_grounding 의 결과는 항상 `gemini-2.5-flash` (또는 `CFG.LLM_MODEL`) 의 출력. `LLM_PROVIDER=openai` 이면서 vertex_grounding 사용 시, 검색단 LLM 과 downstream writer LLM 이 **다른 모델** (gemini × gpt-4o). (ii) 는 검색단 LLM 부재이므로 writer LLM 만 분석 대상.

---

## § 4. β/γ 박제 cross-reference

### 4-a. β (`scripts/output/§12-13/beta_dual_retrieve.md`)

- L26-27: 임베딩 = VertexAIEmbeddings 768d, dotenv + langchain_google_vertexai + numpy 가용
- L44-48: CFG 확정 — LLM_PROVIDER=vertexai, LLM_MODEL=gemini-2.5-flash, TOPIC_SLUG=venfobel-vitamin
- L99-103: namespace 별 hit — `-web` 0docs / `-local` 5docs (vertex env web 인덱싱 부재 — priors 15)
- search backend invocation **부재** — β 는 순수 Chroma retrieval 측정, web_search 트래픽 0

### 4-b. γ (`scripts/output/§12-13/gamma_end_to_end.md`)

- L14: `.venv_vertex`
- L26: `actual_dim=768` (vertex multilingual)
- L166: **"priors 17 의 발화 영역은 RAG update auto mode (web_search_agent + vector_search_agent + research_synthesizer) — γ pipeline 과 분리된 path"** — γ 는 vector-only end-to-end, web_search 트래픽 0
- L175-176: gemini-2.5-flash latency ~4분 / C 미션 (~31분) 대비 87% 단축

### 4-c. RAG update auto mode (`scripts/output/§12-13/rag_update_log.md`)

실제 web_search backend 호출 흔적은 RAG update 박제에만 존재:
- L74: `web_search.py L1088 auto_mode = "rag_update:auto" in mission.lower()` → multi-provider 진입 분기
- L80-82: provider 상태 — `vertex grounding active`, `naver active`, `tavily active`
- L109-118: `research_synthesizer` (vertex chat_models) 188s long-tail — priors 17 자산 (§12-13-6 (b)(c) reserve)
- L114-115: `langchain_google_vertexai/chat_models.py:868 _completion_with_retry_inner` grpc blocking 노출

### 4-d. routing trace 패턴 (코드 lookup)

| signal | 출처 | 의미 |
|---|---|---|
| `[web_search] Vertex success (chunks=N supports=M items=K queries=...)` | web_search.py:801-805 | vertex_grounding 정상 호출 + items 합산 |
| `[web_search] Vertex skipped (SKIP_VERTEX_SEARCH=1)` | web_search.py:813-814 | provider overlay 의도 gate |
| `[web_search] legacy multi-engine search used` | web_search.py:822 | legacy chain 진입 |
| `[web_search][chain] %s | policy=%s ...` | search.py:1496-1497 | chain 확정 + budget |
| `[web_search][backend tried] %-18s got=%2d in %.2fs` | search.py:1674 | per-backend hit + latency |

→ Step B 시 위 5종 log 만 grep 으로 isolate 하면 trace 박제 가능.

### 4-e. 실측 단언 (priors 18 정신)

- β/γ 박제 자체로는 search backend behavior 단언 부재 → Step B 실측 필요
- RAG update 박제만 backend × provider 활성 상태 직접 박제 — 단 1회 실측만 존재, latency / cross-provider 비교 부재
- vertex_grounding × non-vertex venv 의 graceful degrade (빈 dict) 실측 부재 — 코드 가정만 (`_GENAI_AVAILABLE=False` 경로, vertex_search.py:102-107)

---

## § 5. Chain test 가능성 평가

코드-레벨 가능 조합 (venv + cred 정합 가정):

| LLM provider × search backend | 가능? | 근거 |
|---|---|---|
| openai × naver_direct | ✓ | (ii) decoupled. `.venv_openai` + NAVER_CLIENT_* + `.env.openai` |
| openai × tavily | ✓ | (ii) decoupled. TAVILY_API_KEY 글로벌 `.env:95` 존재 |
| openai × google_cse | ✓ (cred 시) | `CFG.HAS_GOOGLE_KEYS` 확인 필요 (search.py:640) |
| openai × serpapi* | ✓ (cred 시) | `CFG.HAS_SERPAPI` 확인 (search.py:793) |
| openai × vertex_grounding | ⚠ partial | `.venv_openai` 에 google-genai 부재 → 빈 dict graceful degrade. `.venv_vertex` 에서 LLM_PROVIDER=openai 토글 시 `.env.openai:41` OPENAI_API_KEY 가 vertex overlay 의 L41 차단을 풀어주는 양상; GCP creds 별도 정합 필요. |
| vertexai × naver_direct | ✓ | langchain-openai 부재해도 search 호출 자체는 requests 만 사용 — `.venv_vertex` 정합 |
| vertexai × tavily | ✓ | tavily SDK 의 venv 가용성 확인 필요 (실측 영역) |
| vertexai × vertex_grounding | ✓ (current default) | `.venv_vertex` + `.env.vertex` 정합 |
| vertexai × google_cse / serpapi | ✓ (cred 시) | venv 의존 부재 (HTTP/SDK) |
| anthropic × naver_direct | ✓ | (ii) decoupled. `.venv_openai` 동거 + `.env.anthropic` |
| anthropic × tavily | ✓ | 동일 |
| anthropic × vertex_grounding | ✗ blocked | `.env.anthropic:45` SKIP=1 명시 + venv 의 google-genai 부재 (이중 차단) |

→ **provider-coupled forced 조합 부재**. 본 Step B 는 cross-combination test 가능. 단:
- vertex_grounding 의 venv coupling 은 회피 불가 — `.venv_vertex` 외에서는 항상 empty
- `.env.anthropic` 의 SKIP=1 은 overlay-level 의도이며 test 시 명시 override (env mutate) 가능

---

## § 6. Step B 권장 사항

### 6-a. test infrastructure 재활용 가능성 (Task 5 결과)

| 자산 | 위치 | 재활용 형태 |
|---|---|---|
| `dump_vertex_grounding.py` | `scripts/dump_vertex_grounding.py:1-120+` | single-shot Vertex 호출 + query 리스트 + JSON dump 패턴 → backend isolated test 의 골격 |
| `h1_driver_wrapper_trace.py` | `scripts/diag/§14-8/h1_driver_wrapper_trace.py:1-194` | subprocess wrapper + STAGE marker (`[WRAPPER-pre]/-postrun/-tail/-close/-return`, stderr+flush=True) + variant 분기 — backend latency 비교 driver 패턴 |
| `alpha_smoke.py` | `scripts/diag/§12-13/alpha_smoke.py:1-156` | env mimic (driver subprocess 정합) + `load_dotenv(.env.vertex, override=True)` + PYTHONIOENCODING + sys.path insert + RoutingCaptureHandler logger 캡처 |
| `core/config.reload_config_inplace` | `core/config.py:663-688` | runtime CFG mutate 후 protected env list 유지 (§14-8-B fix O) — driver 시점 env 보장 |

### 6-b. measurement convention transfer

| convention | 현 위치 | search backend test 로의 적용 |
|---|---|---|
| `provider-isolated venv` | `.venv_vertex` / `.venv_openai` | (i) 는 `.venv_vertex` 필수, (ii) 는 양쪽 venv 모두 가능. 신규 driver 시 venv 명시 박제 의무 |
| `PYTHONIOENCODING=utf-8` | alpha_smoke.py:19, h1:60 | kr 쿼리 처리 필수 — naver_direct / vertex_grounding 입력에서 발화 가능 |
| `max_retries=0` | llm.py:_build_vertexai_kwargs (L290-298), `_build_anthropic_kwargs` (L274-275) | LLM ctor 에는 명시되어 있으나 **search backend client ctor 에는 명시 부재** — tavily.TavilyClient(api_key=...) (search.py:604), requests.Session (via `get_requests_session`), serpapi.GoogleSearch (search.py:805) 모두 retry-equivalent 옵션 노출 시 명시 cap 0 권장 (latency 측정 무결성) |
| `recovery 후 protected env restore` | config.py:_PROTECTED_ENV_KEYS L655-661 | driver intent snapshot pattern (§14-8-B fix O) — backend test 시 SEARCH_BACKENDS / SKIP_VERTEX_SEARCH 도 protected 목록 추가 고려 |

### 6-c. pitfall registry cross-ref

- **pitfall #3 (`.env.openai` vs `.env.vertex` asymmetry)** — provider 전환 시 env file 정합:
  - `.env.openai:49` SKIP_VERTEX_SEARCH=0 명시 / `.env.anthropic:45` SKIP=1 명시 / `.env.vertex` 명시 부재 → 글로벌 `.env:20` SKIP=1 의존 + 토글 양상 (현 글로벌 `.env:2` LLM_PROVIDER=openai 상태에서 vertex 토글 시 SKIP 회귀 가능성).
  - `.env.vertex:41` OPENAI_API_KEY="" 명시 차단 — vertex venv 에서 openai LLM 무용지물화 (의도) 이지만 cross-provider chain test 진입 시 사전 unset 또는 toggle 필요.
  - `.env.openai:56-58` Chroma ns `-oa` override / `.env.vertex` 는 default ns 사용 — search test 에는 무관하나 RAG update 통합 시 인덱스 분리 정합 필요.
  - **Step B mitigation**: driver 시점 명시 env-set + `_PROTECTED_ENV_KEYS` 등록 + smoke 가시화 (CFG dump line) — alpha_smoke.py:64-65 패턴 그대로 transfer.

- **pitfall #4 (`max_retries` default 충돌)** — search backend client ctor risk:
  - LLM 측: Vertex langchain default 6 retry → quota 누적 패턴 (llm.py:286-298 박제). Anthropic langchain default 2 (llm.py:264-275 박제). OpenAI `OPENAI_MAX_RETRIES` env 노출.
  - Search 측: tavily SDK 의 retry 정책 명시 부재 (search.py:594-631). google-genai 의 `client.models.generate_content` retry 정책 명시 부재 (vertex_search.py:125-129). requests 세션은 `tools.web_rag.ingest.get_requests_session` 통해 공용 — 정책 별도 박제 필요.
  - **Step B mitigation**: 각 backend client ctor 호출 직전 retry-equivalent 옵션 0 cap 명시 + cap 적용 사실 박제 (RecordedSecond-line). 측정 직전 `os.environ` snapshot 도 권장.

### 6-d. 신규 driver 설계 권장

target: `scripts/diag/§14-9/backend_isolated_smoke.py` (별 round 작성).

설계 핵심:
- entry: CLI flag `--provider {openai,vertexai,anthropic}` + `--backend {vertex_grounding,naver_direct,tavily,google_cse}`
- `_search_*` 함수 직접 호출 (search.py 의 module-private 함수) + JSON dump
- 입력 query set: kr (`벤포벨S 핵심 성분`, `활성형 비타민 시장 규모 한국`) + en (`vitamin B benfotiamine clinical trial`)
- 출력 박제: backend / provider / venv / hits / latency / cred-skip / max_retries 명시 + raw items[:3]
- 골격 재활용: `dump_vertex_grounding.py:_run_one`/`main` + `h1_driver_wrapper_trace.py` STAGE marker 패턴
- 통합 test 는 `agent/web_search.py:_run_web_search_with_guard` 진입으로 별도 driver (Step B 후반)

### 6-e. STOP / boundary 단언

- 본 박제는 read-only — code edit / commit 0건 (전제 만족)
- chain test 가능성 부재 영역 부재 — 모든 (provider × backend) 조합 가능 (§ 5 표). Step B scope 재정의 불요.
- code 구조 가정 충돌 영역 부재 — 모든 단언이 line ref 동반 (priors 18 정신).

### 6-f. 🔴 Auxiliary safety finding (본 mission scope 외 박제)

read-through 도중 노출된 cred 평문 commit:
- `.env.openai:25` — `sk-proj-9BjSi...` (OpenAI key)
- `.env.anthropic:24` — `sk-ant-api03-hPXeRy...` (Anthropic key)
- `.env:95` — `tvly-k4RrmTtW...` (Tavily key)
- `.env:98-99` — Naver client id/secret

→ 본 Step A scope 외. Step B 진입 전 또는 별 cycle 에서 (1) 키 rotation (2) `.gitignore` 보강 (3) git history rewrite 평가 권장. README-dev.md L21-25 박제에도 OpenAI 키 평문 노출 박제 흔적 있음 — 본 발견은 신규.

---

## § 7. 결론 요약

1. **5개 backend** (vertex_grounding, naver_direct, tavily, google_cse, serpapi*) 식별 — entry point `agent/web_search.py:_run_web_search_with_guard` 단일점.
2. **Vertex 와 legacy chain 은 병렬 합산**, legacy 내부에서만 직렬 fallback (search.py:1294-1331 + 1503-1697).
3. **provider × backend coupling 은 매우 약함** — vertex_grounding 만 venv-coupled (google-genai 의존). 그 외 모든 (ii) backend 는 LLM_PROVIDER 와 완전 decoupled.
4. **LLM coupling axis 2종**: (i) vertex_grounding = LLM (gemini-2.5-flash) + tool 결합 / (ii) 그 외 = 독립 SDK·HTTP. Step B chain test 는 이 분류 위에 설계.
5. **Step B 진입 가능** — 기존 driver pattern (dump_vertex_grounding / h1 / alpha_smoke) 재활용 가능. `scripts/diag/§14-9/backend_isolated_smoke.py` 신규 driver 권장.
6. **사전 정합**: pitfall #3 (env 비대칭) + pitfall #4 (search client retry 미명시) + auxiliary cred 평문 commit — Step B 진입 전 박제 정리.

— Step A 박제 종결 (자율 진행 중지, 사용자 컨펌 대기).

---

## 부록 정정 reference (§14-9-A1 결과, 2026-05-17)

**정정 대상**: § 6-f "🔴 Auxiliary safety finding — `.env.openai:25` / `.env.anthropic:24` / `.env:95,98-99` 평문 API key **commit 발견**" 단언.

**정정 내용**:

| axis | 원 § 6-f 단언 | §14-9-A1 실측 결과 | 정정 후 단언 |
|---|---|---|---|
| disk plaintext 존재 | ✓ commit 시점 plaintext | ✓ — 5 file 모두 disk 상 평문 key 보유 | 정합 (단언 유지) |
| git history 노출 | ❌ "커밋되어 있음" 단언 | ✗ — `git ls-files writer_project/.env*` empty / `git check-ignore -v` 5 file 정합 매칭 / `git log -S "<prefix>"` 5 prefix 모두 0 hit / `.env.*` 패턴 initial commit `0c59bff` 부터 존재 | **부재 — 단 한 commit 도 진입 적 없음** |
| convention 정합 | ❌ "위반 흔적" 단언 | ✓ — README-dev.md:1924 정합 (LLM provider key=overlay, search backend key=global, 둘 다 의도된 scope) | **위반 0건** |
| §12-11-7 precedent 적용 | "Step B 진입 전 rotation / history scrub 권장" | dead/live rotation/scrub axis **양쪽 모두 비해당** (노출 자체 부재) | **별 cycle action 0** |

**정정 사유**: 원 § 6-f 의 "발견" / "노출" word 가 두 axis 를 conflate — **(a) file 존재 (disk plaintext)** ↔ **(b) git 노출 (commit history 잔존)**. (a) 는 dotenv 본질적 한계 (해소 의무 없음), (b) 가 실제 risk axis 인데 § 6-f 는 둘을 합쳐 단언함. 향후 audit reference 시 두 axis 분리 단언 패턴 필수 — §14-9-A1 lesson.

**Evidence cross-ref**: `scripts/output/§14-9-A1/credential_exposure_audit.md` § 1-c / § 2-b 전체.

**precedent**: README-dev-_14.md:270-278 §14-3 (NEW)-B 트랙 2 "직전 박제 자산 정정 reference" 패턴 — timeline 정합 유지 (원 § 6-f 본문 보존, 정정 reference 로 박제 자산 신뢰성 보장).

**Step B 진입 영향**: § 6-f 의 "Step B 진입 전 박제 정리" 사전 조건은 **해소** — 본 정정 reference 자체가 정리 완료를 박제.
