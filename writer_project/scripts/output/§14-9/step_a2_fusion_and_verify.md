# §14-9 Step A2 — § 6-f 정정 reference 적용 + clarification verify + legacy fusion 박제

- entry: §14-9-A1 close (audit 결과 false-alarm 정정 완료) → Step A2 차단 사항 0
- branch: main / HEAD: 8258f3c / working dir: D:\GPT_AGENT\writer_project
- read-only — Task 0 (`step_a_backend_provider_matrix.md` 부록 append 1-file mutation 예외) 외 commit/edit 0
- precedent: README-dev-_14.md:270-278 §14-3 (NEW)-B 트랙 2 "직전 박제 자산 정정 reference" 패턴 정합

────────────────────────────────────────────────

## § 0. Task 0 — § 6-f 정정 reference 적용 결과

- target: `scripts/output/§14-9/step_a_backend_provider_matrix.md`
- 조치: 파일 끝 `— Step A 박제 종결` 직후 `## 부록 정정 reference (§14-9-A1 결과, 2026-05-17)` 섹션 append
- 원 § 6-f 본문 보존, 정정 reference 만 추가 → timeline 정합 유지
- commit 0, working tree mutation 1-file 만 (Pre-condition exception scope 내)

axis 분리 박제 적용:
- **(a) disk plaintext 존재**: 정합 유지
- **(b) git history 노출**: 부재 (5 prefix 모두 0 hit, `.env.*` initial commit 부터 ignored)
- **(c) convention 정합**: 위반 0건 (LLM provider key=overlay, search backend key=global, 의도된 scope)
- **(d) §12-11-7 precedent 적용**: 비해당 (노출 자체 부재로 axis 양쪽 비해당)

→ Step B 진입 전 사전 조건 "박제 정리" 해소 박제.

────────────────────────────────────────────────

## § 1. Clarification 1 confirm — vertex AI Search (Discovery Engine) 별도 통합 부재

### 1-a. 실측 grep

| pattern | 결과 |
|---|---|
| `discoveryengine` / `DiscoveryEngine` | **0 hit** |
| `vertex_ai_search` / `VertexAISearch` | **0 hit** |
| `aiplatform.*search` | **0 hit** |
| `google\.cloud\.discoveryengine` | **0 hit** |
| `DataStore` / `servingConfig` / `search_service` | **0 hit** |

### 1-b. 잡음 hit (vertex_grounding redirect 영역)

`vertexaisearch.cloud.google.com` 도메인 hit 5건 — 모두 **grounding-api-redirect URL resolve** 코드:
- `tools/web_rag/vertex_search.py:73-77` `_resolve_vertex_redirect()`
- `scripts/measure_vertex_phase_b.py:350` / `scripts/_phase_b_run_inner.py:124` / `scripts/_step3_dry_run_rag_update.py:130` — 동일 redirect substring 검사

→ Vertex AI Search (별도 Discovery Engine product) **부재**. 모두 vertex_grounding (gemini + GoogleSearch tool) 영역.

### 1-c. README-dev-_14.md cross-ref

- L1 "§14 — Vertex AI google search 점검·개선" — track 전체가 vertex_grounding 한정
- L114 "(e) gemini provider (API key) grounding 통합 — §14-1 의 B안 측정 트랙. 현재 `langchain_google_genai.ChatGoogleGenerativeAI` 만 박제, **GoogleSearch tool 미통합**" — 별도 트랙 후보로만 박제, 본 entry point 부재
- L4-5 §14-1 핵심 발견 / L20 §14-2 Step 1b 모두 vertex_grounding 영역

### 1-d. 단언

**vertex AI search (Discovery Engine) 별도 통합 부재**. vertex_grounding (gemini-2.5-flash + GoogleSearch tool via `google-genai`) **단일 통합**. `tools/web_rag/vertex_search.py:88-194` `vertex_web_search()` 가 유일 entry.

────────────────────────────────────────────────

## § 2. serpapi audit — live/dead + 도입 commit

### 2-a. 도입 commit chain (실측)

`git log --all --oneline --diff-filter=A -S "from serpapi import GoogleSearch" -- writer_project/`:
- **`3fce3e6`** `2026-01-31` "update codes" — `_search_serpapi` + `_search_serpapi_naver` 코드 도입 commit (initial commit 외 최초 진입)

`git log --all --oneline -S "serpapi"` (3 hit):
- `3fce3e6` (2026-01-31) — 초기 도입
- `105eca9` (2026-03-02) "update codes 26-03-02 with untracked codes"
- `6b2b353` (2026-05-03) "feat(embeddings): migrate to text-multilingual-embedding-002" — 무관 (다른 변경)

§12-11-5 박제 (`README-dev.md:593-596`, 2026-05-04 시점) "backend 다양화 부재 (naver_direct + tavily만)" → serpapi 는 코드 존재했으나 **default chain 비활성 + cred 미설정** 상태 유지.

### 2-b. caller chain + cred gate

```
agent/web_search.py:_run_web_search_with_guard()
   ↓ web_search.invoke(payload)            web_search.py:821
   ↓ legacy chain loop                     search.py:1515-1680
   ↓ _backend_call("serpapi", ...)         search.py:1267
   ↓ _search_serpapi()                     search.py:791-824
         ↓ if not (api_key and CFG.HAS_SERPAPI): return []   search.py:793

   또는 _backend_call("serpapi_naver", ...) search.py:1269
   ↓ _search_serpapi_naver()                search.py:901-979
         ↓ if not api_key: return []          search.py:902-904
```

`CFG.HAS_SERPAPI=bool(_env_str("SERPAPI_API_KEY"))` (`core/config.py:560`).

### 2-c. 현 환경 cred 상태 (실측)

| 위치 | 결과 |
|---|---|
| `.env` SERPAPI_API_KEY 라인 | **부재** (`.env:77` 주석 `serpapi_naver 미사용 시` 만 존재) |
| `.env.openai` / `.env.anthropic` / `.env.vertex` | 부재 |
| `env_raw.txt:72` | 주석 (`# serpapi_naver 미사용 시`) |

→ `CFG.HAS_SERPAPI=False` (env 부재 정합).

### 2-d. 중복 / 보완 평가 (코드 + docs 박제만, 실측 없음)

| backend | 검색 source | output schema | cost / latency 차원 |
|---|---|---|---|
| `_search_serpapi` (search.py:791-824) | Google (SerpAPI 프록시) | `{title, url, content=snippet, raw_content="", source}` (search.py:809-820) | SerpAPI 유료 (사용량 기반), 자체 키 별도 |
| `_search_google_cse` (search.py:633-789) | Google (직접 CSE API) | `{title, url, content=snippet/htmlSnippet, raw_content, source}` (search.py:779-785) | Google CSE 무료 limit + 유료 |
| `_search_serpapi_naver` (search.py:901-979) | Naver (SerpAPI 프록시) | `{title, url, content, raw_content="", source}` (legacy schema) | SerpAPI 유료 |
| `_search_naver_direct` (search.py:826-899) | Naver (직접 openapi.naver.com) | `{title, url, content=description, raw_content="", source}` (search.py:879-889) | Naver 일일 quota (무료) |

→ output schema **5-key 동일** (`title, url, content, raw_content, source`). 차이는 source provider (Google 또는 Naver) 와 cost layer (SerpAPI 프록시 vs 직접) 만.

기능 중복:
- `serpapi` ↔ `google_cse` — 둘 다 Google source, fallback 관계 (서로 dead 시 backup)
- `serpapi_naver` ↔ `naver_direct` — 둘 다 Naver source, fallback 관계

기능 보완: serpapi 진영의 advantage = (1) SerpAPI 가 추가 engine (Bing/Yahoo/etc.) 도 단일 API 로 노출 (현 코드 미사용), (2) Naver 의 `webkr` 외 추가 vertical 지원 (search.py:957 `params = {"engine": "naver", ...}`).

### 2-e. live / dead 단언

| backend | 코드 가용 | cred 가용 | default chain 포함 | 활성 상태 |
|---|---|---|---|---|
| `serpapi` | ✓ (search.py:791-824) | ✗ (SERPAPI_API_KEY 부재) | ✗ (default `naver_direct,tavily`, search.py:1304) | **dead** (cred 미설정 → early-return) |
| `serpapi_naver` | ✓ (search.py:901-979) | ✗ | ✗ | **dead** |

코드는 reachable (env 토글 시 활성 가능) 이나, 현 환경에서 **실제 호출 path 0건**.

### 2-f. §12-11-5 이후 추가 commit chain (live 시) — 비해당

dead 상태이므로 §12-11-5 "backend 다양화 부재" 시점 이후의 활성화 commit chain 없음. 현 박제 시점까지 dead 유지.

────────────────────────────────────────────────

## § 3. SKIP_VERTEX_SEARCH gate 도입 사유 (간소 cross-ref)

### 3-a. 도입 commit chain (실측)

`git log --all --oneline -S "SKIP_VERTEX_SEARCH"` 결과 (가장 이른 → 최근):

| commit | 일자 | 메시지 (요약) | 역할 |
|---|---|---|---|
| `f0e4195` | 2026-04-25 | "fix: CHROMA_NS 네이밍 통일 + IPv6 URL 차단 + 403 블랙리스트 + **Vertex 스킵**" | **초기 도입** (글로벌 default skip) |
| `87ee1cf` | 2026-05-06 | "feat(rag): Vertex grounded search 활성화 (venfobel-vitamin) (§12-19)" | per-topic override 도입 (`topics/venfobel-vitamin.env` SKIP=0) |
| `d3d4d97` | 2026-05-?? | "fix(config): reload_config_inplace 토픽 .env override 회귀 (§12-20)" | per-topic override 회귀 fix |
| `4888a3a` | 2026-05-?? | "feat(provider): OpenAI venv 분리 + 검색 정책 튜닝 (§12-23)" | `.env.openai:49` SKIP=0 명시 추가 |
| `2d3dd1f` | 2026-05-?? | "§14-3 (NEW)-B 트랙 1 P-2 ..." | per-topic override 패턴 검증 완료 |
| ... | ... | 후속 박제/측정 commit 다수 | gate 운영 유지 |

### 3-b. README-dev-_14.md cross-ref

| 위치 | 내용 |
|---|---|
| L107 | "**Pitfall (NEW)**: Vertex API 429 quota (multi-turn 측정 5~6분 누적 후 발현). 대응 후보 (§14-3 검토): inter-section-sleep / API call throttle / 측정 단위 축소." |
| L4 | "§14-1 핵심 발견: vertex grounding metadata 의 90% 가 `agent/web_search.py:767` 에서 휘발" — Step 1b 정상화 이전 metadata 휘발 issue |
| L224 | "§12-19 per-topic override 패턴 검증 완료 (글로벌 .env SKIP=1 base + topics/<slug>.env SKIP=0 override)" |
| L260 | "trigger 시나리오 박제: `\"write: <섹션명>\"` (writer-lock) vs `\"최신 자료로 RAG 업데이트해줘\"` (web_search 진입)" |

### 3-c. 단언

SKIP_VERTEX_SEARCH gate **도입 사유 (2축)**:
1. **Vertex API 429 quota** — multi-turn 측정 누적 시 발현 (README-dev-_14.md:107). 글로벌 default SKIP=1 로 차단 + 토픽별 SKIP=0 opt-in 패턴.
2. **§14-1 metadata 휘발** — `web_search.py:767` (당시 URL-only 통합) 에서 vertex grounding metadata 90% loss. §14-2 Step 1b (d88a8b9) 정상화 이전 시점에는 vertex 호출 의미 자체가 약했음.

운영 패턴: **per-topic opt-in** (글로벌 SKIP=1 + `topics/<slug>.env` SKIP=0 override). §14-3 (NEW)-B 트랙 1 P-2 (2d3dd1f) 에서 패턴 검증 완료.

────────────────────────────────────────────────

## § 4. Legacy fusion logic + trigger path (A2 핵심)

### 4-a. `_run_web_search_with_guard` 합산 구조 (line ref)

`agent/web_search.py:727-1054` `_run_web_search_with_guard(q, preview_limit, retries)`:

```
attempt loop (range(retries+1)):
  ┌─ 1-1. Vertex 우선 (attempt 0 only)              web_search.py:761-814
  │     if not SKIP_VERTEX_SEARCH:
  │         vertex_result = vertex_web_search(query)    L766
  │         for support in vertex_result["supports"]:    L772
  │             combined_items.append({                  L786
  │                 url=rep_url, content=support.text,
  │                 metadata={backend:"vertex_grounding", alt_urls, chunk_domain}
  │             })
  │
  └─ 1-2. Legacy multi-engine (항상)                web_search.py:816-850
        legacy_ret = web_search.invoke(payload)          L821 (@tool, search.py:1335)
        legacy_items = normalize(legacy_ret)             L826-844
        combined_items.extend(dict(it) for it in legacy_items)  L846-850

ret = combined_items                                     L853
```

→ **vertex × legacy 병렬 합산** — 두 source 가 같은 `combined_items` 리스트에 append/extend. dedup/merge 는 후속 단계.

### 4-b. Legacy 내부 직렬 fallback

`tools/web_rag/search.py:web_search()` (`search.py:1335-1889`) 내부:

```
chain = _resolve_backend_chain(engine, num=num, googleish=...)   search.py:1294-1331
                                                                  default = "naver_direct,tavily"
KR-context 시 chain 앞에 "naver_direct" 강제                       search.py:1479-1487

chain loop:                                                       search.py:1515-1680
  for bk in chain:
    if naver_reserved && bk not in naver_set && budget tight:
        skip (naver 예약)                                          L1517-1521
    if bk in ("google","google_cse","tavily","serpapi"):
        results = _backend_call(bk, base_query, ...)                L1529-1537
    elif bk in ("naver","serpapi_naver","naver_direct"):
        for variant in [("recall", q_rec), ("prec", q_pre)]:        L1538-1552
            results = _backend_call(bk, variant_q, ...)
    tried.append((bk, len(results), results))                       L1674
    if best_of_chain && hits >= MIN_OK && backends >= MIN_BACKENDS:
        early stop                                                   L1781-1796

if not results && KR && naver_in_chain && !naver_called:
    forced naver_direct retry                                        L1687-1697

retry loop (1회 추가, 적용 backend 동일)                              L1719-1796
```

→ **legacy 내부만 직렬 fallback**. `SEARCH_POLICY=best_of_chain` (CFG default, config.py:473) 시 MIN_OK 만족하면 early stop.

### 4-c. Legacy backend output schema (5-key 통일)

`tools/web_rag/search.py` 의 각 `_search_*` 함수 반환:

| backend | location | schema |
|---|---|---|
| `_search_tavily` | search.py:594-631 | `{title, url=_canon_url, content[:2000], raw_content="", source=_canon_url}` |
| `_search_google_cse` | search.py:633-789 | `{title, url=_canon_url, content=snippet/htmlSnippet, raw_content="", source=_canon_url}` |
| `_search_serpapi` | search.py:791-824 | `{title, url=_canon_url, content=snippet, raw_content="", source=_canon_url}` |
| `_search_naver_direct` | search.py:826-899 | `{title=_clean(...), url=_canon_url, content=_clean(description), raw_content="", source=link}` |
| `_search_serpapi_naver` | search.py:901-979 | `{title, url, content, raw_content, source}` (동일 5-key) |
| **vertex_grounding** (호출 측에서 wrap) | web_search.py:786-797 | `{title="", url=rep_url, content=support.text, raw_content="", source=rep_url, metadata={backend, alt_urls, chunk_domain}}` |

→ **5-key 동일 schema**. vertex 만 `metadata` 키 추가 (web_search.py:792-796).

(주의 박제: README-dev-_14.md:24-26 — `metadata` 키는 Chroma 인덱싱 단계 `web_results_to_documents` 화이트리스트 (source/title/content_type) 로 drop. `_extract_meta` 까지 vertex dict 가 그대로 도달하지 않음. alt_urls/backend/chunk_domain 도 동일 drop — §14-3 sub-task (a) 후보로 박제됨.)

### 4-d. cross-backend dedup / rerank / merge 로직

`_run_web_search_with_guard()` 합산 후 처리 (web_search.py:914-963):

| 단계 | 코드 line | 동작 |
|---|---|---|
| (a) **연식 필터** | L918-921 | `_extract_year_from_url(item.url) >= YEAR_FLOOR(=2019)` (URL 상 연도만; 미검출 통과) |
| (b) **rerank** | L923-932 | `sorted([(i,it)...], key=lambda p: _item_rank(p[1], idx=p[0]), reverse=True)` — 권위/잡음 가중치 + 연식 |
| (c) **dedup** | L934-945 | key = `_norm_url(item.url or item.source)` — **URL 기반** (title 미사용). 중복 제거. |
| (d) **cap** | L946-960 | `_round_cap - _round_added_urls` 잔여 예산 + `WEB_DEDUP_REMAIN_MIN` 하한 |
| (e) JSON 저장 | L961 | dedup 결과 `Path(json_path).write_text(json.dumps(...))` |
| (f) gatekeep | L968 | `_filter_json_by_domain(json_path)` — ALLOWED_DOMAINS 정합 |
| (g) **indexing** | L971-1015 | `add_web_pages_json_to_chroma(filtered_json, namespace=ns, clear=False)` — upsert mode |

→ dedup key = **URL** (정규화), rerank = **권위/잡음 가중치 + 연식** (LLM-free, deterministic). cross-backend 통합은 dict list 차원에서만 — 별도 LLM synthesis 부재.

### 4-e. dual-retrieve (web + local) 와의 분리

cross-ref `scripts/output/§12-13/beta_dual_retrieve.md`:
- β 박제는 web=0 + local=5 (vertex env, venfobel-vitamin-local 인덱스) 케이스의 **retrieval-only** 측정
- `agent/vector_search.py` (1577 lines) 가 dual-retrieve 담당 — web_search 후 indexing 된 결과 + local 인덱스 결합
- web_search_agent 의 fusion = **indexing 단계 까지** (Chroma ns 별 upsert)
- vector_search_agent 의 fusion = **retrieval 단계** (web ns + local ns merge per `MERGE_RETRIEVE_MODE`/`RETRIEVE_WEB_RATIO`, CFG.MERGE_RETRIEVE_MODE default `web_first`)

→ 본 § 4 의 fusion 박제는 **web_search agent 내부 (search → dedup → index)** 한정. retrieval-stage fusion 은 별 모듈 (vector_search) 영역. β 박제는 후자 측정.

### 4-f. trigger path 활성 박제

`agent/supervisor.py` 의 web_search_agent schedule 지점 (실측 grep):

| line | trigger 조건 | schedule | web_search 진입 |
|---|---|---|---|
| supervisor.py:584-585 | `force_queries` 감지 (`extract_forced_queries_from_messages`) | `Task(agent="web_search_agent", description="rag_update:auto")` | ✓ |
| supervisor.py:608-619 | regex `(최신|업데이트|update|latest).*?(자료|리소스|레퍼런스|...).*?(rag|벡터|vector|...)` (line 609) | 기존 writer 정리 + web_search_agent schedule | ✓ ("최신 자료로 RAG 업데이트해줘") |
| supervisor.py:695-704 | new topic boot + refs 비어있음 | content_strategist + web_search_agent schedule | ✓ |
| supervisor.py:720-733 | `extract_write_title(last_text)` + `has_on_disk` (RAG ready) | section_writer + vector_search_agent (web_search **미진입**) | ✗ ("write: <섹션명>") |
| graph.py:128-179 | planner / vector / tail router 조건부 라우팅 | 조건부 web_search_agent 재진입 가능 | ⚠ (조건 의존) |

§14-3 (NEW)-B 트랙 2 박제 (README-dev-_14.md:259-260) 정합:
- `"write: <섹션명>"` → writer-lock fast path → **web_search 노드 미진입** → Step 1b patch dead path
- `"최신 자료로 RAG 업데이트해줘"` → RAG-update fast path → **web_search 진입** → fusion path 활성

### 4-g. fusion 패턴 단언

- **vertex 쪽**: §14-2 Step 1b (`d88a8b9`) 박제 정합 — 옵션 (a) "LLM synthesis 폐기, support 단위 추출 → 동등 결합" 적용 완료. URL-only loss 해소.
- **legacy 쪽**: **옵션 (a) 와 동일한 정신** (LLM-free, dict list 동등 결합). 차이점은:
  - legacy items 는 backend 별 직렬 호출 (chain) 결과를 단순 extend
  - vertex items 는 단발 호출의 supports 펼침
  - 모두 5-key schema 정합 → 차후 dedup/rerank/index 가 통합 처리
- **전체 fusion 일관성 평가**: ★★★★☆
  - ✓ schema 통일 (5-key) — vertex `metadata` 만 추가, 인덱싱 단계 drop 정합
  - ✓ dedup key URL 통일 — provider 무관 작동
  - ✓ rerank LLM-free deterministic — vertex/legacy 차별 없음
  - ⚠ vertex `metadata.backend="vertex_grounding"` 가 인덱싱 단계 drop 됨 (README-dev-_14.md:26) — vertex/legacy 구분 trace 박제는 web_search.py 로그 단계까지만 보존 (§14-3 sub-task (a) 영역)

────────────────────────────────────────────────

## § 5. Anthropic provider × search 경로 검증

### 5-a. 코드 레벨 단언

| 영역 | 실측 결과 |
|---|---|
| `LLM_PROVIDER == "anthropic"` 분기 코드 | 5건 — 모두 LLM/embedding ctor 영역 (`core/llm.py:111,115,360,391,478`, `app.py:1215`) |
| supervisor 의 provider gate | **부재** — supervisor.py:608-619 RAG-update trigger 가 provider 무관 작동 |
| web_search_agent 의 provider gate | **부재** — `agent/web_search.py:171+` `web_search_agent(state)` 가 provider 무관 진입 |
| `.env.anthropic:45` `SKIP_VERTEX_SEARCH=1` | vertex_grounding 만 차단. legacy chain (naver_direct + tavily) 진입 가능 |
| `web_search.py:1144 llm.bind_tools([web_search])` | `llm = get_llm()` → ChatAnthropic (LLM_PROVIDER=anthropic 시). ChatAnthropic 은 `bind_tools` 지원 → planner LLM 이 query dispatch 가능 |

### 5-b. 실 동작 path (LLM_PROVIDER=anthropic + RAG-update trigger 시 예상)

```
supervisor.py:608-619  RAG-update regex match
   ↓ Task(agent="web_search_agent", description="rag_update:auto")
web_search.py:171  web_search_agent(state)
   ↓ _run_web_search_with_guard(q)                     web_search.py:727+
   ┌─ vertex_grounding: SKIP_VERTEX_SEARCH=1 → 차단    web_search.py:764
   └─ legacy chain: naver_direct + tavily 진입         web_search.py:821
   ↓ combined_items (legacy only)
   ↓ dedup / rerank / cap / index                      web_search.py:914+
```

→ anthropic provider 활성 시 **vertex 차단 + legacy 활성** 패턴. RAG retrieval-only 이 아니라 web_search 도 작동.

### 5-c. README cross-ref + design intent 평가

| README ref | 내용 |
|---|---|
| README-dev.md:3181 | "임베딩은 `RAG_EMBEDDING_MODEL` overlay 로 provider 자동 매칭 (anthropic 사용 시 `.env.anthropic` 가 `text-embedding-3-large` 3072d 강제 → `venfobel-vitamin-oa-*` 인덱스와 일치)" — embedding 영역 정합만 박제, **search 영역 RAG-only intent 명시 없음** |
| README-dev.md:1915-1924 §13-8 close | anthropic = eval-only 트랙, deferred 재진입 조건 명시. search 경로 별도 단언 없음 |
| README-dev.md:1928-1932 §13-8-pre | timeout / slide count 시나리오 — plan_deck/section_writer 영역만. web_search 영역 미언급 |

### 5-d. 단언

- **코드 정합**: anthropic provider × web_search node = **ALLOWED** (legacy chain 활성, vertex 만 차단)
- **README explicit design intent**: "anthropic = RAG-only" 단언 **부재**. mission prompt 의 "design intent" 표현은 inference 추정.
- **결론**: 만일 anthropic eval 트랙 (§13-8-3 등) 진입 시 RAG-only 가 의도였다면, 현 코드는 그 intent 를 **enforce 하지 않음**. 추가 gate (예: `LLM_PROVIDER=anthropic` 시 web_search 자동 skip, 또는 `.env.anthropic:SKIP_WEB_SEARCH=1` 추가) 도입 필요. 본 cycle 은 read-only 박제만.

────────────────────────────────────────────────

## § 6. §14-9 Step B 진입 권장 사항

### 6-1. fusion 일관성 평가 (Task 4 단언 기반)

- vertex × legacy fusion ★★★★☆ — schema/dedup/rerank 통일, vertex `metadata` drop 만 minor
- legacy 내부 fusion ★★★★★ — chain order + dedup + rerank 결정성 + cred-gated graceful degrade
- Step B test matrix 진입 valid

### 6-2. README-dev.md:1924 convention axis 보강 박제 권장

원 convention (README-dev.md:1924):
> "Provider 분기 키 분리 convention 운영 중: `.env.anthropic` ANTHROPIC_API_KEY (글로벌 .env 미보관)"

**문제**: scope 모호 — LLM provider key 만 지칭하는지, search backend key 도 포함되는지 단언 부재. §14-9 Step A § 6-f false-alarm 의 원인 중 하나.

**보강 권장 axis**:
```
"Provider 분기 키 분리 convention":
- LLM provider key (OpenAI/Anthropic/Gemini): .env.<provider> overlay (분리)
- search backend key (Tavily/Naver/Google CSE/SerpAPI, provider-agnostic): global .env (의도된 scope)
- platform credential (GCP service account path): global .env (path-only; key 자체는 별 file, .gitignore 정합)
```

**적용 방안**:
- (a) README-dev.md:1924 본문 update — 한 줄 → 3-line axis 표기
- (b) 신규 박제 자산 (별 file) — convention 단일점 박제, README 에서 link 만
- → **사용자 판단**

### 6-3. Step B test matrix scope 권장

§14-9 Step A § 5 chain test 가능성 표 + 본 A2 박제 합산 후 권장 scope:

| 우선순위 | combination | 측정 의미 |
|---|---|---|
| ★★★★★ | vertexai × vertex_grounding (current default) | regression baseline — §14-2 Phase A 패턴 재활용 |
| ★★★★★ | openai × naver_direct + tavily | LLM_PROVIDER 토글 영향 측정 — 가장 단순 cross-provider case |
| ★★★★☆ | vertexai × naver_direct + tavily (vertex 차단 시) | per-topic SKIP=1 override 시 운영 패턴 |
| ★★★★☆ | anthropic × legacy chain | § 5-d 단언 검증 — 의도 mismatch 가시화 |
| ★★★☆☆ | openai × vertex_grounding via `.venv_vertex` | venv coupling 우회 가능성 측정 (cred 전제) |
| ★★☆☆☆ | google_cse / serpapi 활성화 (cred 토글) | dead backend live 화 cost 평가 |
| ★☆☆☆☆ | gemini provider (API key) | 미통합 (§14 sub-task (e)) — Step B 범위 외 |

### 6-4. driver 재활용 / 신규 작성 판단

**재활용 가능** (Step A § 6-a 박제 정합):
- `scripts/dump_vertex_grounding.py` — single-shot 패턴 (vertex 영역만)
- `scripts/diag/§14-8/h1_driver_wrapper_trace.py` — subprocess wrapper + STAGE marker
- `scripts/diag/§12-13/alpha_smoke.py` — env mimic + load_dotenv override + RoutingCaptureHandler

**신규 작성 권장**:
- `scripts/diag/§14-9/backend_isolated_smoke.py` — backend × provider × venv matrix smoke (Step A § 6-d 박제 정합)
- `scripts/diag/§14-9/fusion_observability.py` — `_run_web_search_with_guard` 진입 후 vertex/legacy items 분리 trace (web_search.py 의 logger 캡처) — 본 A2 § 4-g 의 vertex metadata drop 가시화 자산
- (optional) `scripts/diag/§14-9/anthropic_search_gate.py` — § 5-d 의 의도 mismatch 검증 trace (anthropic + web_search trigger 시 legacy chain 호출 실측)

### 6-5. Step B 진입 valid 조건 정합 (요약)

- ✓ Step A § 6-a/b/c 박제 (driver pattern / convention / pitfall) 정합
- ✓ Step A § 6-f false-alarm 정정 완료 (§14-9-A1 + 본 A2 § 0 부록 append)
- ✓ vertex_grounding 단일 통합 확정 (§ 1-d)
- ✓ serpapi dead 단언 (§ 2-e) — Step B scope 에서 cred 토글 우선순위 ★★☆ 로 후순위
- ✓ SKIP_VERTEX_SEARCH gate 사유 양축 박제 (§ 3-c) — per-topic opt-in 패턴
- ✓ legacy fusion 박제 (§ 4-a~f) — schema/dedup/rerank/trigger 모두 확정
- ✓ anthropic × search 코드 ALLOWED + design intent 비명시 (§ 5-d) — Step B 매트릭스 ★★★★☆ 항목으로 의도 mismatch 가시화 진입

→ **§14-9 Step B 즉시 진입 가능**. 신규 driver 작성 우선 (`backend_isolated_smoke.py`), 통합 fusion trace 는 Step B 후반.

────────────────────────────────────────────────

## § 7. 결론 요약

1. **§ 6-f 정정 reference append 완료** (Task 0, 1-file mutation, timeline 정합 유지) — Step B 진입 전 박제 정리 해소.
2. **vertex_grounding 단일 통합 확정** — Vertex AI Search (Discovery Engine) 별도 통합 부재.
3. **serpapi 코드 reachable / cred 부재 / default 비활성** → dead. Step B 후순위.
4. **SKIP_VERTEX_SEARCH gate 사유**: vertex 429 quota (README-dev-_14.md:107) + §14-1 metadata 휘발. per-topic opt-in 패턴 (§12-19 ~ §14-3).
5. **Legacy fusion 패턴**: vertex × legacy 병렬 합산 (web_search.py:758-853) + legacy 내부 직렬 fallback (search.py:1294-1331) + LLM-free deterministic dedup/rerank (web_search.py:914-963). 5-key schema 통일.
6. **Trigger path 활성**: `"write: <섹션명>"` → web_search 미진입 / `"최신 자료로 RAG 업데이트해줘"` → web_search 진입 (§14-3 (NEW)-B 트랙 2 박제 정합).
7. **Anthropic × search**: 코드 ALLOWED (legacy chain 활성). README explicit "RAG-only intent" 단언 부재 — Step B 매트릭스에서 의도 mismatch 가시화 진입 권장.
8. **convention axis 보강 권장** (§ 6-2) — README-dev.md:1924 의 LLM/search/platform key 분리 명시.
9. **Step B 즉시 진입 valid** — driver 재활용 + `backend_isolated_smoke.py` 신규 작성 권장.

— §14-9 Step A2 박제 종결 (자율 진행 중지, 사용자 컨펌 대기).

---

## 부록 정정 reference (§14-9 Step B Phase 1 결과, 2026-05-17)

**정정 대상**: § 4-c "Legacy backend output schema (5-key 통일)"

**정정 내용**: 실측 3-layer schema 분리 (Phase 1 driver `backend_isolated_smoke.py` `item_keys_observed` 실측 박제):

| layer | location | observed keys |
|---|---|---|
| **(a)** raw vertex chunks | `tools/web_rag/vertex_search.py` 의 `vertex_web_search()` 반환 `chunks` 항목 (vertex_search.py:148-158) | **3 keys**: `domain, title, uri` |
| **(b)** raw legacy post-fetch | `tools/web_rag/search.py` 의 `web_search.invoke()` 반환 items (search.py:1335-1889 의 후처리 후) | **9 keys**: `content, content_type, fetched_at, norm_url, raw_bytes, raw_content, source, title, url` |
| **(c)** wrapped in `_run_web_search_with_guard` | `agent/web_search.py:786-797` (vertex side wrap) + `web_search.py:846-850` (legacy items extend) | **5 keys + vertex `metadata`** (title, url, content, raw_content, source [, metadata]) |

**정정 사유**: A2 § 4-c 의 "5-key 통일" 단언은 **layer (c) wrapped 기준 정합**. fundamental error 아님, **scope precision** 정정 (어느 layer 기준인지 명시 누락). A2 § 4-c 표는 `_search_*` 함수의 의도된 반환 스키마를 기록했으나 (5 keys), 실측 (b) layer 는 `web_search.invoke()` 의 후처리 (fetch + canonicalize + raw_bytes 보존) 가 추가되어 9 keys. (a) layer 는 vertex_grounding 의 `chunks` 가 raw structure 그대로 — wrap 전이라 3 keys.

→ fusion logic 의 dedup/rerank (web_search.py:914-963) 는 layer (c) 기준 작동 (URL key, idx-based rerank) → A2 § 4-d~g 의 결론 변동 없음. **§ 4-g ★★★★☆ 별점 유지** (단, axis 분리 박제 누락이 ★ 의 0.5점 감점 사유였음을 본 정정으로 명시).

**Evidence cross-ref**: `scripts/output/§14-9/step_b_phase1_baseline_smoke.md` § 3-e + § 4-c (raw JSON `item_keys_observed` 실측).

**precedent**: §14-3 (NEW)-B 트랙 2 "직전 박제 자산 정정 reference" 패턴 정합 (timeline 보존, 원 § 4-c 본문 보존, 정정 reference 만 추가).

**axis 분리 lesson 재적용** (A1/A2 catch): "schema 통일" word 가 wrap-stage axis 를 implicit 가정. 향후 schema 단언 시 **layer 명시 의무** (raw backend / wrapped fusion / post-index 화이트리스트 — 3 axis).
