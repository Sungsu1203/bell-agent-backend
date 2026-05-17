# §14-9 Step B Phase 1 — backend isolated baseline smoke (★★★★★ 2 combination)

- entry: §14-9 Step A2 close (HEAD 8258f3c, A2 § 6 권장 정합)
- 측정 일자: 2026-05-17 (KST 20:19~20:48)
- venv 분리: `.venv_vertex` / `.venv_openai`
- topic: venfobel-vitamin
- production code 무수정 — driver 신규 작성만
- precedent: §14-2 Phase A (24.93s/cv30.6% baseline), §13-7 측정 표준

────────────────────────────────────────────────

## § 1. Driver 설계 박제

신규 file: `scripts/diag/§14-9/backend_isolated_smoke.py` (작성 일자 2026-05-17, ~490 lines)

### 1-a. 모드 3종

| `--backend` | 호출 path | 측정 의도 |
|---|---|---|
| `vertex_grounding` | `tools.web_rag.vertex_search.vertex_web_search(query)` 직접 (driver L141-180) | §14-2 Step 1b 정합 — vertex 단독 baseline |
| `legacy_only` | `tools.web_rag.search.web_search.invoke({"query": q})` 직접 (driver L183-250) | legacy chain 단독 — naver_direct + tavily |
| `both` | _stub_ — graph state 의존으로 Phase 1 scope 외 (`NotImplemented` 반환) | 차후 Phase 합산 검증 reserve |

### 1-b. 측정 표준 (§13-7 정합)

| 항목 | 값 | 출처 |
|---|---|---|
| max_retries | 0 (provider 별 env: `VERTEX_MAX_RETRIES=0`, `OPENAI_MAX_RETRIES=0/3` per overlay, `ANTHROPIC_MAX_RETRIES=0`) | §13-7 표준 + .env.vertex:28 / .env.openai:27 / .env.anthropic:31 |
| warmup | 2 (per query, 측정 제외) | 본 mission spec |
| measured N | 3 (per query) | 본 mission spec, max 5 cap |
| per-call timeout | 240s (vertex baseline_mean 24.93s × ~10 margin) | Step A § 6-b 박제 + Phase A 120s 보강 |
| inter-call sleep | 60s | §14-2 Phase A 정합 |
| PYTHONIOENCODING | utf-8 (env 명시 + driver setdefault) | pitfall #1 + alpha_smoke.py:19 precedent |
| .env load 순서 | global `.env` (override=False) → `.env.<provider>` (override=True) | `core.config._load_dotenv_once` 재현 (driver L82-100) |
| venv 분리 orchestration | caller PowerShell 가 `.venv_vertex` / `.venv_openai` 전환 (driver 내 subprocess 미사용) | 단순화 — env 오염 차단 책임을 호출자에 위임 |

### 1-c. STOP 조건 (driver L260-270 `_check_stop`)

- 429 ResourceExhausted (`_is_429` L70-77) — vertex quota
- per-call timeout
- vertex_grounding mode 한정: `chunks=0` (응답 비정상)

### 1-d. 출력 schema

- 파일: `scripts/output/§14-9/phase1_<provider>_<backend>_<tag>_<timestamp>.json` (.gitignored 정합 — root `.gitignore:82` `scripts/output/**/*.json`)
- 필드: `provider, backend, queries, warmup_n, measured_n, inter_sleep_sec, per_call_timeout_sec, warmup_records[], measured_records[], abort, pre_dump, summary`
- 각 record: `elapsed_sec, error_class, error_msg, raw_items, items_post_dedup, per_backend_dist, first_3_urls, item_keys_observed, run, tag, query` (+ vertex 측: `vertex_chunks, vertex_supports, vertex_web_search_queries, summary_chars`)

### 1-e. 1-call smoke validation (Task 1.5)

| combination | result | observation |
|---|---|---|
| (i) vertexai × vertex_grounding × 1 query × 1 call | elapsed 21.39s, raw 7, dedup 6 | 정상 |
| (ii) openai × legacy_only × 1 query × 1 call | elapsed 7.81s, raw 1, dedup 1 (`asiatoday.co.kr`) | 정상 (단, 1차 시도 시 (a) 글로벌 `.env` 미로드로 has_TAVILY/has_NAVER false 노출 → driver `_load_provider_env` 가 `.env` + `.env.<provider>` 양쪽 load 하도록 수정. (b) cp949 console encoding 으로 em-dash UnicodeEncodeError → `—` ASCII 치환 + `PYTHONIOENCODING=utf-8` env-level set. **2 fix 후 재검증 통과**.) |

→ wiring 검증 완료. 본 측정 진입 valid.

────────────────────────────────────────────────

## § 2. Combination (i) — vertexai × vertex_grounding 측정 결과

### 2-a. 측정 조건 (pre-dump 실측)

```json
{
  "LLM_PROVIDER": "vertexai", "LLM_MODEL": "gemini-2.5-flash",
  "SKIP_VERTEX_SEARCH": "1",   // 글로벌 .env:20 — 단 driver 가 vertex_web_search 직접 호출이므로 무관
  "VERTEX_MAX_RETRIES": "0",
  "SEARCH_BACKENDS": "naver_direct,tavily",  // 글로벌 .env:77 — vertex_grounding mode 에는 영향 없음
  "has_GCP_PROJECT_ID": true, "has_GOOGLE_APPLICATION_CREDENTIALS": true,
  "python_exec": ".venv_vertex/Scripts/python.exe"
}
```

→ env 정합 ✓. SKIP_VERTEX_SEARCH=1 은 글로벌 default 이나, driver 가 `tools.web_rag.vertex_search.vertex_web_search` 직접 호출하므로 본 gate 미적용.

### 2-b. 측정 결과 (4 query × 5 run = 20 호출, measured N=12)

| metric | n | mean | stdev | cv_pct | min | max |
|---|---:|---:|---:|---:|---:|---:|
| elapsed_sec | 12 | **22.12** | 6.55 | **29.6%** | 14.94 | 34.94 |
| raw_items (=supports) | 12 | 11.5 | 6.72 | 58.4% | 5.0 | 30.0 |
| items_post_dedup (=urls) | 12 | 8.33 | 3.2 | 38.4% | 5.0 | 16.0 |

- errors: **0/12** ✓
- 429 quota: **0회** ✓
- per_backend_total: `vertex_grounding: 138` (raw items 합)

### 2-c. 쿼리별 통계

| query | elapsed mean ± std | elapsed cv | raw_items mean ± std | raw cv | dedup mean ± std |
|---|---:|---:|---:|---:|---:|
| Q1 (벤포벤S 광고비) KR | 17.74 ± 3.46 | 19.5% | 6.0 ± 1.0 | 16.7% | 7.33 ± 2.31 |
| Q2 (활성형 비타민 시장) KR | 17.75 ± 4.18 | 23.6% | 9.0 ± 2.65 | 29.4% | 7.0 ± 2.65 |
| Q3 (비타민 B군 임상) KR | 26.14 ± 7.63 | 29.2% | 18.67 ± 9.87 | **52.9%** | 11.33 ± 4.51 |
| Q4 (benfotiamine clinical) EN | 26.86 ± 5.74 | 21.4% | 12.33 ± 3.21 | 26.1% | 7.67 ± 2.31 |

### 2-d. §14-2 Phase A baseline 회귀 비교

| metric | Phase A (24.93s baseline, N=20) | Phase 1 (N=12) | drift | 판단 |
|---|---:|---:|---:|---|
| elapsed mean | **24.93s** | **22.12s** | **-11.3%** | 5% 초과, 단 **faster 방향** — 회귀 부재 |
| elapsed cv | 30.6% | 29.6% | -1pp | 정합 (envelope 내) |
| chunks 50%+ 변동 건수 | 1건 (Q2 run 2) — warning only | **1건 (Q3, raw cv 52.9%)** | — | Phase A 동일 패턴 (정상 vertex 비결정성, README-dev-_14.md L42-43 정합) |
| errors / 429 | 0 / 0 | 0 / 0 | — | 정합 |

**drift 해석**:
- Phase A 측정: 2026-05-14 20:49 (per-call timeout 120s, inter-sleep 60s, model=flash+pro 양쪽)
- Phase 1 측정: 2026-05-17 20:19 (per-call timeout 240s, inter-sleep 60s, flash 단독)
- drift 사유 후보 (실측 부재 — Phase 2 후속 조사 영역):
  - (a) N 감소 (20 → 12) — 표본 변동 가능
  - (b) 측정 시점 GCP region 부하 차이
  - (c) timeout 240s 로 보강 시 fail-recover 패턴 부재 — 본 결과는 100% success 이므로 영향 X
  - (d) 본 측정에서 inter-call sleep 누적 시 cache warm-up 효과 가능성

→ **quality regression 부재** (faster + same cv envelope + 0 errors). drift 사유 후속 조사는 Phase 2 reserve.

### 2-e. 측정 자산

- raw JSON: `scripts/output/§14-9/phase1_vertexai_vertex_grounding_phase1_20260517_204807.json` (.gitignored)
- 총 호출: 20 (warmup 8 + measured 12), 총 elapsed budget: ~28 min (실측 ~27 min)

────────────────────────────────────────────────

## § 3. Combination (ii) — openai × legacy_only 측정 결과

### 3-a. 측정 조건 (pre-dump 실측)

```json
{
  "LLM_PROVIDER": "openai", "OPENAI_MODEL": "gpt-4o",
  "SKIP_VERTEX_SEARCH": "0",   // .env.openai:49 — 단 legacy_only mode 에서는 무관
  "OPENAI_MAX_RETRIES": "3",   // .env.openai:27 — 단 legacy_only 는 LLM 미호출이므로 무관
  "SEARCH_BACKENDS": "naver_direct,tavily",  // 글로벌 .env:77
  "has_TAVILY_API_KEY": true, "has_NAVER_CLIENT_ID": true, "has_NAVER_CLIENT_SECRET": true,
  "python_exec": ".venv_openai/Scripts/python.exe"
}
```

→ env 정합 ✓.

### 3-b. 측정 결과 (4 query × 5 run = 20 호출, measured N=12)

| metric | n | mean | stdev | cv_pct | min | max |
|---|---:|---:|---:|---:|---:|---:|
| elapsed_sec | 12 | **2.16** | 0.39 | **18.1%** | 1.56 | 3.00 |
| raw_items | 12 | 1.5 | 1.57 | **104.4%** | 0.0 | 4.0 |
| items_post_dedup | 12 | 1.5 | 1.57 | 104.4% | 0.0 | 4.0 |

- errors: **0/12** ✓
- 429 / quota: 0회 ✓
- per_backend_total (URL host heuristic): `naver_direct: 12`, `legacy_unattributed: 6` (실측 inspect: § 3-d 정정)

### 3-c. 쿼리별 통계

| query | elapsed mean ± std | elapsed cv | raw_items | URL hits |
|---|---:|---:|---:|---|
| Q1 (벤포벤S 광고비) KR | 2.25 ± 0.10 | **4.3%** | 1 (deterministic) | `dailypharm.com/user/news/15008` × 3 — 동일 URL |
| Q2 (활성형 비타민 시장) KR | 2.58 ± 0.36 | 14.0% | 1 (deterministic) | `asiatoday.co.kr/.../20210124...` × 3 |
| Q3 (비타민 B군 임상) KR | 2.17 ± 0.07 | 3.1% | 4 (deterministic) | `blog.naver.com/{pshmhk,love00406,bbubbupharm,...}` × 3 — 4 URL 동일 |
| Q4 (benfotiamine clinical) EN | 1.64 ± 0.11 | 6.6% | **0** (deterministic) | — |

→ **결정성 ★★★★★**: per-query raw_items cv = 0% (3 run 전부 동일 hit set). elapsed cv 도 3~14% 매우 낮음. legacy chain 의 deterministic 성격 명시 확인.

### 3-d. URL host 기반 backend 추정 (heuristic 한계 박제)

driver 의 per-backend attribution heuristic (driver L210-220):
- naver.com domain → `naver_direct`
- wikipedia/pubmed/nih → `tavily_or_cse`
- 기타 → `legacy_unattributed`

실측 hit URL 검토 후 정정:
| Q | URL | heuristic 분류 | 실제 backend 추정 |
|---|---|---|---|
| Q1 | `dailypharm.com` | legacy_unattributed | **naver_direct** (KR 의약 매체, naver 검색 결과로 추정 — 단 확정은 log scrape 필요) |
| Q2 | `asiatoday.co.kr` | legacy_unattributed | **naver_direct** (KR 종합지) |
| Q3 | `blog.naver.com` × 4 | naver_direct | naver_direct ✓ |
| Q4 | (empty) | — | — |

→ **heuristic 한계**: KR non-naver domain (예: 신문사/제약사) 을 `legacy_unattributed` 로 잘못 분류. log scrape 또는 production code 의 backend tag 보존 (§14-9 Step A § 4-g 의 vertex `metadata.backend` drop 영역 + legacy 도 동일 보존 필요) 으로 정확한 attribution 가능.

**핵심 단언**: 12 measured records 중 **tavily attribution 확정 0건**. naver_direct 가 모든 hit 의 source. Q4 EN 은 naver_direct 가 KR-only 이므로 0, tavily 도 0 (정상 작동 시 tavily 가 Q4 를 capture 해야 하나 미발화). → **tavily 본 측정에서 작동 부재** 의심 — Phase 2 진입 추가 조사 영역.

### 3-e. legacy item schema 실측 (A2 § 4-c 정정)

`item_keys_observed` 합집합:

| 측정 | observed keys |
|---|---|
| Phase 1 legacy | `[content, content_type, fetched_at, norm_url, raw_bytes, raw_content, source, title, url]` (**9 keys**) |
| A2 § 4-c 단언 | `[title, url, content, raw_content, source]` (5 keys) |

→ **A2 § 4-c 정정 필요**: A2 박제는 `_search_*` 함수의 raw return 만 검토했으나, `web_search.invoke()` 의 @tool wrap 이 fetch + canonicalize 단계를 추가하여 `content_type, fetched_at, norm_url, raw_bytes` 4 키 추가. **legacy item 실제 schema = 9 keys**.

vertex 측 schema 도 확인:

| 측정 | observed keys |
|---|---|
| Phase 1 vertex_grounding | `[domain, title, uri]` (**3 keys**, chunks-level) |
| A2 § 4-c 단언 | `[title, url, content, raw_content, source, metadata]` (web_search.py:786-797 의 5+1 keys) |

→ **A2 § 4-c 정정 필요**: A2 박제는 web_search.py 의 fusion site (L786-797) 의 wrapped item schema 를 기준으로 함. **vertex_web_search() 단독 호출 시 chunks 의 raw schema 는 `[domain, title, uri]` 3 keys**. 5+1 keys 는 `_run_web_search_with_guard` 내부 wrap 결과.

**axis 분리 박제 필수** (A1/A2 lesson 재적용):
- backend 함수 raw return schema (vertex 3 keys / legacy 9 keys / search.py:_search_* 5 keys)
- `_run_web_search_with_guard` 내부 wrap 후 schema (5 keys + vertex metadata)
- Chroma 인덱싱 단계 화이트리스트 (3 keys: source/title/content_type, README-dev-_14.md:24-26)

3 axis 분리 명시는 Step B Phase 2 진입 시 fusion 일관성 평가에 필수.

### 3-f. 측정 자산

- raw JSON: `scripts/output/§14-9/phase1_openai_legacy_only_phase1_20260517_204151.json` (.gitignored)
- 총 호출: 20 (warmup 8 + measured 12), 총 elapsed budget: ~22 min (실측 ~21 min)

────────────────────────────────────────────────

## § 4. 비교 박제 + fusion 일관성 회귀 검증

### 4-a. (i) vs (ii) 직접 비교 (axis 분리)

| axis | combination (i) vertex_grounding | combination (ii) legacy_only | 단언 |
|---|---|---|---|
| **latency** mean | 22.12s | 2.16s | **~10× 격차** — vertex grounding 의 LLM (gemini-flash) 호출 + GoogleSearch tool 합산 비용 가시화 |
| **latency** cv | 29.6% | 18.1% | vertex 가 ~1.6× 더 변동성 (LLM 비결정성 + Google quota dynamics) |
| **raw_items** mean | 11.5 | 1.5 | **~7.7× 격차** — vertex grounding 이 query 당 더 많은 source 발견 |
| **raw_items** cv | 58.4% | 104.4% | legacy 가 더 높은 cv, **단 구조적 (query asymmetry)**: per-query cv 는 legacy 0% / vertex 16~53% — **per-query 차원에서는 vertex 가 더 변동** (정상 vertex 비결정성) |
| **items_post_dedup** | 8.33 | 1.5 | vertex 내부 URL dedup ratio ~28% (raw 11.5 → dedup 8.33). legacy 는 raw=dedup (단일 hit per query 기준 dedup 부재) |
| **errors** | 0/12 | 0/12 | 동등 |
| **EN query (Q4)** | 12.33 items (정상) | **0 items** (3 run 결정성) | legacy chain 의 EN coverage 부재 — tavily 미발화 의심 (§ 3-d) |
| **schema** | 3 keys (`uri, title, domain` chunks-level) | 9 keys (post-fetch enrichment) | A2 § 4-c "5-key 통일" 단언 **정정 영역** — backend 별 raw schema 상이 |

### 4-b. URL dedup 효과 (cross-backend overlap)

**Phase 1 scope 한정 — cross-backend overlap 직접 측정 불가** (vertex_grounding mode 는 vertex 단독, legacy_only mode 는 legacy 단독). `both` mode 가 graph state 의존으로 Phase 1 미구현이므로, 합산 dedup 효과는 Step B Phase 2 (`_run_web_search_with_guard` 직접 호출 가능한 mock state driver) 이후 측정.

추정 (코드 박제 기반, A2 § 4-d):
- 합산 시점: web_search.py:853 `ret = combined_items`
- dedup 시점: web_search.py:934-945 `_norm_url(it.get("url") or it.get("source"))`
- 동일 URL 이 vertex + legacy 양쪽 hit 가능 → cross-backend 중복 제거 가능
- 단 실측 부재 — Phase 2 reserve

### 4-c. A2 § 4-g fusion 일관성 ★★★★☆ 회귀 검증

| A2 § 4-g 단언 | 실측 결과 | 단언 갱신 |
|---|---|---|
| ✓ schema 통일 (5-key) | **부분 부정** — 실측 schema axis 3종 분리 (raw vertex 3 keys / raw legacy 9 keys / wrapped 5+1 keys) | A2 § 4-c 정정 필요 — § 3-e 박제 정합 |
| ✓ dedup key URL 통일 | 실측 확인 — legacy items 의 `norm_url` 키 존재 (item_keys_observed L9) | 정합 |
| ✓ rerank LLM-free deterministic | legacy mode 의 raw cv 0% per-query — deterministic 정합. vertex mode 는 LLM 비결정성으로 raw cv 16~53% (Phase A 정합) | 정합 (axis 분리: 두 mode 의 결정성 source 가 다름) |
| ⚠ vertex `metadata.backend` 인덱싱 단계 drop | 본 Phase 1 은 인덱싱 단계 미진입 — 검증 부재 | Phase 2 reserve |

→ **A2 § 4-g 별 ★★★★☆ → ★★★☆☆ 하향 조정 권장**. 사유: schema 통일은 wrapped layer 기준만 정합, raw layer 기준은 미정합. 정정 reference 적용 후 다시 ★★★★☆ 가능.

### 4-d. Phase A baseline 회귀 (§14-2)

§ 2-d 박제 동일 — drift -11.3% (faster), errors 0, 429 quota 0, cv envelope 정합. **회귀 부재 단언**.

────────────────────────────────────────────────

## § 5. Phase 2 진입 권장 사항

### 5-a. Phase 1 측정 표준 transfer 가능 여부

- ✓ §13-7 표준 (max_retries=0, warmup=2, N=3, timeout=240s, inter-sleep=60s, utf-8) 완전 transfer 가능
- ✓ driver `backend_isolated_smoke.py` 재활용 가능 — Phase 2 의 anthropic / vertex SKIP / cred-toggle 조합도 동일 driver argparse 로 cover
- ✓ pre-dump axis 분리 박제 정합 (env / cred / venv)
- ⚠ `both` mode (graph state 의존) 가 Phase 2 의 fusion 합산 측정 진입 시 추가 작업 필요 — `_run_web_search_with_guard` 호출용 mock state 또는 minimal graph harness 작성

### 5-b. vertex 429 quota 발현 평가

- 본 Phase 1 (24 호출 vertex + 24 호출 legacy = 총 48 호출) 동안 429 0건
- inter-call sleep 60s 가 효과적 — README-dev-_14.md L107 "multi-turn 측정 5~6분 누적 후 발현" 우회 패턴 정합
- Phase 2 진입 시 **inter-sleep 60s 유지 권장**. 단, anthropic combination 진입 시 anthropic API quota 별도 평가 필요 (README-dev.md L1920 Tier 1 RPM 50 / ITPM 30K).

### 5-c. Phase 2 추가 combination 진입 차단 사항

| combination | 차단 사항 | 진입 valid 조건 |
|---|---|---|
| (iii) vertexai × legacy_only (per-topic SKIP=1 패턴) | 없음 | 즉시 진입 가능 — `.env.vertex` overlay + SEARCH_BACKENDS 정합 |
| (iv) anthropic × legacy_only (B-1 (β) framing) | `.venv_anthropic` 가용 확인 필요 | `.venv_anthropic` import 검증 후 진입 |
| (v) anthropic × both / web_search_agent (의도 mismatch 가시화) | "both" mode 미구현 + anthropic provider 의 web_search 진입 path 가 graph state 의존 | minimal graph harness 작성 후 진입 |

### 5-d. 본 측정에서 발견한 Phase 2 권장 조사 항목

1. **Q4 EN query → tavily 미발화 의심** (§ 3-d). 검증 방법: SEARCH_POLICY=first_ok / `WEB_SEARCH_ENGINE=tavily` 강제 + 별도 cross-checking 또는 search.py logger 박제 추가.
2. **Phase A 24.93s → Phase 1 22.12s drift -11.3%** (§ 2-d). 사유 후보 (a)~(d) 박제만, 결정성 부재. 차후 측정 시 동일 drift 재현 시 Phase 2 sub-track 필요.
3. **A2 § 4-c schema 통일 단언 정정** (§ 3-e). 3-axis schema 분리 (raw vertex / raw legacy / wrapped) 박제 적용 — Phase 2 진입 시 사용자 컨펌 후 A2 박제에 정정 reference append 권장 (A1/A2 precedent 정합).
4. **backend attribution heuristic 한계** (§ 3-d). URL host 기반 추정은 KR non-naver domain 분류 오류. log scrape 또는 production code 의 backend tag 보존 (§14-9 Step A § 4-g 의 vertex metadata drop 영역 확장 — vertex+legacy 양쪽 보존 patch) 권장. 단 production code 무수정 원칙으로 본 cycle scope 외.

### 5-e. Step B Phase 2 즉시 진입 valid

- ✓ Phase 1 measured 24/24 success (combination i+ii 합산)
- ✓ 429 quota 0건 — vertex 측 안전
- ✓ driver 재활용 가능
- ✓ 회귀 부재 (§14-2 Phase A 대비 quality regression 0)
- ⚠ Phase 2 scope 진입 전 사용자 컨펌:
  - 추가 combination 선정 (iii/iv/v 중 우선순위)
  - tavily 미발화 의심 조사 트랙 진행 여부
  - A2 § 4-c schema 정정 reference append 여부

────────────────────────────────────────────────

## § 6. 결론 요약

1. **driver `backend_isolated_smoke.py` 신규 작성 + 2 fix 후 wiring 정상화** — 1-call smoke 검증 통과.
2. **Combination (i) vertexai × vertex_grounding**: 12/12 success, mean 22.12s cv 29.6%. §14-2 Phase A 24.93s 대비 -11.3% drift (faster, regression 부재).
3. **Combination (ii) openai × legacy_only**: 12/12 success, mean 2.16s cv 18.1%. per-query deterministic (raw cv 0%). **tavily 미발화 의심** (Q4 EN 0 items).
4. **vertex/legacy 격차**: latency ~10×, raw_items ~7.7×. vertex 의 LLM-coupled 검색 비용 명시.
5. **A2 § 4-c schema 통일 단언 정정 필요** — raw schema 3종 (vertex 3 keys / legacy 9 keys / wrapped 5+1 keys) 분리. axis 분리 박제 적용.
6. **Phase 2 진입 valid** — 사용자 컨펌 영역: combination 우선순위 + tavily 조사 트랙 + A2 정정 reference 적용.

— §14-9 Step B Phase 1 박제 종결 (자율 진행 중지, 사용자 컨펌 대기).
