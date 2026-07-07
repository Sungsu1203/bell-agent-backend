# §14 — Vertex AI google search 점검·개선

## §14-1 현황 파악 (완료)
- 핵심 발견: vertex grounding metadata 의 90% 가 `agent/web_search.py:767` 에서 휘발
- 보고서 위치: 채팅 박제 (별도 파일 미저장) — 5개 항목 (통합 구조 / metadata 박제 / 통합·랭킹 / 한국어 쿼리 / gemini-2.5-pro provider 매칭)
- gemini-2.5-pro on vertexai 호환성 검증 완료 (us-central1, 실제 응답 확인 — `LLM_MODEL=gemini-2.5-pro` env 박제 시 ChatVertexAI 가 publisher model id 로 정상 호출)

## §14-1.5 결과 흐름 재검증 (완료)
- 시나리오 A 확정: `vertex_result["summary"]` / `raw_response` 완전 휘발 (호출처 1곳, urls 키만 접근)
- 단일 통로 (1 entry point) 확인 — `agent/web_search.py:766-769` 한 곳 패치로 전체 영향
- 사용자가 4개 쿼리 (한국어 3 + 영어 1) 실측 dump JSON 점검 후 옵션 2 (support 단위) 확정
- dump JSON: `writer_project/scripts/output/vertex_grounding_dump_20260514_194043.json` (gitignore)

## §14-2 Step 1 (완료)
- **Step 1a (commit `1135ac1`)**: `tools/web_rag/vertex_search.py` 반환값 확장
  - 신규 키: `chunks: [{uri, title, domain}]`, `supports: [{chunk_indices, text, start_index, end_index}]`, `web_search_queries: list[str]`
  - 기존 키 `summary`/`urls`/`raw_response` 보존 (호환성)
  - 부속: `scripts/dump_vertex_grounding.py`, `.gitignore` 에 `scripts/output/` 추가
- **Step 1b (commit `d88a8b9`)**: `agent/web_search.py:766` 패치
  - URL-only dict 폐기, support 단위 item 생성 (5키 + metadata)
  - support text (한국어 42~124자, 영어 평균 178자) 가 `content` 로 보존 → embedding · retrieve · rerank 정상 작동
  - `source = rep_url` (legacy backend 호환), `metadata = {backend, alt_urls, chunk_domain}` 향후 활용 대비
- **`_extract_meta` 영향 검증 시나리오 베타 확정**:
  - vertex item 의 `metadata` 키는 Chroma 인덱싱 단계 (`web_results_to_documents`) 에서 화이트리스트 (source/title/content_type) 로 100% drop
  - `_extract_meta` 까지 vertex dict 가 그대로 도달하지 않음 → URL 손실 위험 0
  - 부수 효과: alt_urls/backend/chunk_domain 도 동일하게 drop (별도 sub-task 필요)

## §14-2 Phase A — vertex_web_search 단독 baseline (완료)

### 측정 환경
- commit: `d88a8b9` (Step 1b 적용 후)
- venv: `.venv_vertex`, `.env.vertex` 로드
- model: `gemini-2.5-flash`, GCP project=`gemini-rag-search-final`, region=`us-central1`
- `VERTEX_MAX_RETRIES=0`, inter-sleep=60s, per-call-timeout=120s
- 측정 시각: 2026-05-14 20:49 KST
- 측정 스크립트: `scripts/measure_vertex_phase_a.py`
- 결과 박제: `scripts/output/phase_a_summary.md` + `phase_a_20260514_204914.json` (gitignore)

### 결과 (N=5, 4 query × 5 run = 20 호출)
- errors: **0/20**
- elapsed: mean=**24.93s**, cv=30.6% (쿼리 그룹 차이 포함)
- 쿼리 내 cv 평균: elapsed 15.0%, chunks 18.7%, supports 19.97%
- chunks 50%+ 변동: **1건** (Q2 run 2, warning 만)

### 쿼리별 통계
| query | elapsed (s) | elapsed cv | chunks cv | supports cv |
|---|---:|---:|---:|---:|
| Q1 (벤포벤S 광고비) | 18.54 | 23.4% | 21.0% | 21.1% |
| Q2 (활성형 비타민 시장) | 18.16 | 9.7% | 23.0% | 11.8% |
| Q3 (비타민 B군 임상) | 30.58 | 15.9% | 21.3% | 17.5% |
| Q4 (영어 benfotiamine) | 32.44 | 11.0% | **9.5%** | 29.5% |

### 핵심 발견
1. **vertex grounding 응답은 비결정적이지만 N=5 측정 시 cv ~19% 수준으로 안정**
   - 이전 §14-1a dump vs sanity 의 50% 변동은 N=1 한계로 인한 양 끝점 우연 측정
2. **영어 쿼리 (Q4) 가 한국어보다 ~2배 결정적** (chunks cv 9.5% vs 21.4%)
   - §15 트랙 한국어 web 인용 문제에 함의: 한국어 vertex 응답 변동성 영향
3. **§13 표준 N=3~5 가 vertex 측정에도 충분히 적용 가능** (cv < 25% 다수)
4. **vertex 단독 baseline_mean=24.93s**, recommended per-run-timeout=300s (산식 floor)

### Phase B 진입 가이드
- per-run-timeout: **480s** (보수치, §13-8-3 Sonnet baseline 동일)
- N=3 권고 (cv 양호, cost 절약)
- inter-run-sleep: 60s
- `measure_stability.py` 활용 또는 신규 스크립트 작성 결정 필요

### pro 측정 (보류)
- 추정 latency 50~75s (flash 의 2~3배), cost ~$0.04, 시간 ~45분
- Phase B 결과 보고 pro 진입 가치 평가 후 결정

## §14-2 Phase B — 풀파이프라인 patch 효과 측정 (close 2026-05-15)

### 측정 결과 요약

| 지표 | 5078a2d (patch 후, n=3) | ba44637 (patch 전, n_ok=2) |
|---|---:|---:|
| elapsed mean | 311.41s (cv 6.9%) | 269.76s (cv 10.2%) |
| refs_docs (sidecar) mean | 17.33 (cv 8.8%) | 16.5 (cv 4.3%) |
| state_references count | 26 × 3 | 26 × 2 |
| state_dist | `{local: 26}` × 3 | `{local: 26}` × 2 |
| section_count / turn_count | 7.0 / 7.0 (cv 0%) | 7.0 / 7.0 (cv 0%) |
| abort (warmup 포함, 5 runs) | 0 | 2 (turn 7 vertex 429) |

### 결론

- **§14-2 Step 1b patch in-memory 효과 = 0** (정상 5/5 runs 모두 `state_dist = {'local': 26}` 동일)
- **가설 (a') 확정**: graph 가 `"write: <섹션명>"` 명령 시 web_search 노드 미호출. patch 는 dead code path.
- **abort 2회 모두 turn 7 vertex 429 quota** — 코드 결함 아님, 환경 제약. patch 안정성 차이 측정 무효.

상세 박제: `scripts/output/phase_b/phase_b_summary.md`

### 측정 인프라 (유지)

- `scripts/measure_vertex_phase_b.py` — multi-turn driver (A-1, max_turns 21, 2-subprocess orchestration)
- `scripts/_phase_b_run_inner.py` — measurement subprocess
- `scripts/_phase_b_clear_ns.py` — ns_web reset 전용 subprocess (Windows file lock 회피)
- `scripts/output/phase_b_reset_policy.md` — Chroma reset 정책 박제

§14-3 이후 multi-turn 측정 트랙에서 재활용.

### Patch 코드 처리

§14-2 Step 1b patch (`d88a8b9`) 는 dead path 에 있어도 **코드 정합성 차원에서 유지**. revert 불요. web_search 노드 활성화 시 다시 필요.

### §13-7 측정 표준 update

**Pitfall (NEW)**: Vertex API 429 quota (multi-turn 측정 5~6분 누적 후 발현). 대응 후보 (§14-3 검토): inter-section-sleep / API call throttle / 측정 단위 축소.

## 별도 sub-task (§14-3 후보)
- **(a) `web_results_to_documents` 화이트리스트 확장** — alt_urls / backend / chunk_domain 을 Document.metadata 에 보존, footnote 단계에서 vertex 식별 가능하게
- **(b) redirect URL resolve 견고화** — Q2 의 1/6 vertexaisearch URL 미해결 사례 (단발성), timeout 8~10s 상향 + retry 1회
- **(c) footnote label 정밀화** — `chunk.title = domain` 복제 우회, URL path 마지막 segment 또는 support text 앞 부분 사용
- **(d) `domain_bonus` 통합** — 현재 retrieval-only (`agent/vector_search.py:240`), web search rerank 에도 적용 (§14-1 개선 방향 후보 c)
- **(e) gemini provider (API key) grounding 통합** — §14-1 의 B안 측정 트랙. 현재 `langchain_google_genai.ChatGoogleGenerativeAI` 만 박제, GoogleSearch tool 미통합. `google-genai` SDK 의 `genai.Client(vertexai=False, api_key=...)` 경로로 별도 모듈 작성 필요
- **(e-2) deprecated 라이브러리 마이그레이션** (Phase B stderr 관측) — `ChatVertexAI`/`VertexAIEmbeddings` (LangChain 3.2.0 deprecated, 4.0.0 제거 예정) → `langchain_google_genai` 의 `ChatGoogleGenerativeAI`/`GoogleGenerativeAIEmbeddings`. 추가로 `google-cloud-storage<3.0.0` FutureWarning (google-cloud-aiplatform 향후 버전 호환) → 업그레이드 필요.

### §14-3 진입 시 우선 트랙 후보 (Phase B close 박제)

- **web_search 노드 호출 시나리오 발굴** — supervisor 라우팅 / 입력 패턴 / `"research:"` 명령 등. (a)~(d) 의 효과 측정 전제 조건. 현재 `"write: <섹션명>"` 명령 시나리오에서는 web_search 미진입 — Phase B 측정으로 확정.

## §14-1 보고서의 부정확 발견 (실측 정정)
- `chunk.web.snippet` 필드는 실제로 존재하지 않음 — vertex SDK 에서 노출하는 키는 `uri`, `title`, `domain` 3개뿐 (보고서가 가정한 snippet 은 추측)
- `confidence_scores` 는 Gemini 2.5 부터 미제공 (Google 정책 변경 추정) — `grounding_supports[]` 에 confidence 키 없음, segment + chunk_indices 만
- redirect resolve 실패 12.5% 는 Q2 단발성 (일반화 부정확) — 4개 쿼리 합산 1/48 = 2.1%
- 1:N support 매핑은 평균 1.43~2.62 로 1:1 또는 1:2 가 다수 — 1:N 의 6 chunk_indices 매핑은 Q3 (영어 임상 토픽) 에서만 1건 관찰

## 박제된 commit
| hash | message | files |
|---|---|---|
| `1135ac1` | §14-2 Step 1a: Vertex grounding metadata 추출 확장 | vertex_search.py + dump 스크립트 + .gitignore |
| `d88a8b9` | §14-2 Step 1b: Vertex grounding 결과 통합 정상화 | agent/web_search.py |
| `9fda4ec` | §14-2 Phase A 박제 | scripts/measure_vertex_phase_a.py + output/phase_a_summary.md |
| `5078a2d` | §14-2 Phase B: measurement driver + 2-subprocess clear pattern | scripts/measure_vertex_phase_b.py + _phase_b_run_inner.py + _phase_b_clear_ns.py + output/phase_b_reset_policy.md |

ba44637: detached HEAD 임시 commit (1135ac1 + driver cherry-pick, Phase B 측정 후 GC 대상).

branch: `feature/vertex-web-search` (push 미실행)

## §14-3 Phase 2 Step 3 close

- commit: 670fb09 — §14-3 Phase 2 Step 3: Tier 2 토픽 dry-run + 선정 박제 (stress test 트랙, vertex_grounding=0 패턴 박제, Tier 1 fallback 보류)
- 박제 자산: scripts/output/§14-3/topic_selection.md (12 섹션, 247 줄)

### 측정 결과 요약

Tier 2 3 토픽 (T4 영어 / T5 한국어 / T6 영어) 모두 vertex_grounding=0 완전 일관 패턴.

| 토픽 | invoke_elapsed | refs_docs | source_dist | vertex_grounding |
|------|---------------|-----------|-------------|------------------|
| T4 ai-generated-creative-ad-platforms | 93.61s | 5 | {'web': 5} | **0** |
| T5 kr-digital-ad-spend-2026-forecast | 72.11s | 3 | {'web': 3} | **0** |
| T6 programmatic-dooh-growth-drivers | 115.84s | 10 | {'web': 10} | **0** |

### 핵심 결론

- 영어/한국어 토픽 무관, 메커니즘 부재 가능성 ★★★★
- §14-2 Step 1b patch 본 검증 valid 조건 위협 (Phase A 단독 vs graph 통합 대조)
- Tier 1 fallback 결정 보류 (메커니즘 결함 위험 회피)
- 가설 A (vertex_search 호출 안 됨) 강한 의심 ★★★

### 미진입 트랙

- **Phase 2 Step 4 보류**: 선정 토픽 부재 (Tier 2 모두 grounding=0) → 진입 부적합
- **Phase 3 본 측정 보류**: valid 조건 미확보, §14-3 (NEW)-B 완료 후 재평가

## §14-3 (NEW)-B: vertex_search 호출 검증 트랙

### 진입 사유

§14-3 Phase 2 Step 3 결과 (Tier 2 3 토픽 모두 vertex_grounding=0) 가 메커니즘 결함 가능성 ★★★ 시사. Phase 3 본 측정 (5078a2d vs 1135ac1) 진입 전 가설 A/B/C 분리 검증 필수.

### 미션

- 가설 A: vertex_web_search 호출 자체가 안 됨 — 강한 의심 ★★★
- 가설 B: 호출되나 grounding metadata 비어있음 — Phase A 대조로 부분 약화 ★★
- 가설 C: §14-2 Step 1b patch 의 supports loop dead path — ★

### 진행 방식 (사용자 컨펌)

단계적 진행:
1. 옵션 3 (graph 내부 분기 점검, 코드 review) — 가설 A 우선 검증
2. 분기 결정:
   - (가) 가설 A 코드 기반 확정 → 원인 추가 분석 + 수정 plan
   - (나) 가설 A 기각 → 옵션 2 (Phase A repro) 진입, 가설 B 검증
   - (다) 미확정 → 옵션 1 (logger 추가) 진입, 직접 검증

### 완료 조건

- 가설 A/B/C 분리 검증 (확정/기각)
- vertex_search 호출 분기 + grounding metadata 흐름 박제
- Phase 3 본 측정 진입 valid 조건 확보 또는 재설계 plan 박제

## §14-3 디버깅 표준 박제 (origin)

§14-3 Phase 2 Step 3 진행 중 T4/T5 dry-run hang 진단 사이클에서 12차 누적된 박제 자산. 영구 박제 자산은 README-dev-2.md 의 "디버깅 표준 박제" 섹션 참조.

origin 박제 요약:
- 추정 기반 진단 위험성 (12차 누적 확인)
- 사전 확인 (B) 가치 박제
- Phase 1 코드 리뷰 결손 패턴 박제 (6 결손) — (NEW)-B 옵션 3 진단 결과 update (env 파일 설정 + TOPIC_SLUG env var)
- PowerShell 5.1 + Bash tool vs PowerShell tool 환경 박제
- standalone 형식 측정 신뢰성 박제

상세 → `README-dev-2.md` 의 "디버깅 표준 박제 (영구 박제, §14-3 origin)" 섹션

## §14-3 (NEW)-B 트랙 1 P-2 close

- 박제 자산: `scripts/output/§14-3/(NEW)-B_track1_P2_result.md` (10 섹션, ~8.5KB)
- 토픽 env 파일: `topics/ai-generated-creative-ad-platforms.env` (검증용, 792 bytes)
- 진입 commit: `ca148bc` (§14-3 (NEW)-B 옵션 3 close)

### 측정 결과 요약

| metric | 직전 T4 | P-2 | 변화 |
|--------|---------|-----|------|
| elapsed_sec | 99.72 | 166.08 | +66.36 (+66.5%) |
| refs_docs_count | 5 | 8 | +3 |
| source_dist.vertex_grounding | 0 | 1 | +1 ★★★★★ |

### 핵심 결론

- **분기 (가) 확정**: vertex_grounding > 0 도달
- doc[7] URL `vertexaisearch.cloud.google.com/grounding-api-redirect/` unambiguous
- §12-19 per-topic override 패턴 검증 완료 (글로벌 .env SKIP=1 base + topics/<slug>.env SKIP=0 override)
- 환경 변수 흐름 5 단계 모두 매칭 (특히 단계 4 토픽 프리셋 로드 ★)
- §14-3 (NEW)-B 트랙 1 본 미션 완료

### Phase 3 본 측정 진입 valid 조건

- vertex_grounding > 0 도달 가능 토픽 + env 파일 + 환경 변수 흐름 박제 완료
- §14-2 Step 1b patch 본 검증 (5078a2d vs 1135ac1) 진입 가능

### 신규 트랙 후보 (Phase 3 진입 전 검토)

- **chroma collection_count=0 결함 진단** 트랙 (P-3 또는 §14-3 (NEW)-C, ★★★)
  - 본 P-2 측정에서 throughout 0 발견, references state 만 정상 누적
  - Phase B 측정 시 동일 패턴 가능성
- **§14-2 측정 재검증** 트랙 (sub-step)
  - Phase A 단독 + Phase B 의 vertex 우회 상태 재해석 필요

### 다음 단계 분기 (user 결정 미박제)

- (P) Phase 3 본 측정 즉시 진입
- (Q) chroma 결함 진단 트랙 우선
- (R) §14-2 재검증 트랙 우선
- (S) 병행

## §14-3 (NEW)-B 트랙 2 close

- 박제 자산: `scripts/output/§14-3/(NEW)-B_track2_phase_b_review.md` (7 섹션, ~9.67KB)
- 진입 commit: `2d3dd1f` (트랙 1 P-2 close)
- 분기 결정: (R) §14-2 재검증 트랙 진행

### 미션 결과

§14-2 재검증:
- **§14-2 commit 식별 정정**: 직전 "5078a2d vs 1135ac1" → 정확 "5078a2d vs ba44637" (실제 patch = `d88a8b9`)
- **Phase A 가설 기각**: SKIP_VERTEX 무관, `vertex_web_search` 직접 호출
- **Phase B 재해석 정확화**: web_search 노드 미진입 (writer-lock 빠른 경로), Step 1b patch dead path
- **trigger 시나리오 박제**: `"write: <섹션명>"` (writer-lock) vs `"최신 자료로 RAG 업데이트해줘"` (web_search 진입)
- **사전 plan 정합 확정**: Phase B summary § 7 "web_search 노드 호출 시나리오 발굴" 사전 plan 과 P-2 결과 정합

### Phase 3 본 측정 plan

- **시나리오 (α)** 단발 RAG 업데이트 trigger (P-2 패턴 확장) 결정
- 측정 환경: `topics/<slug>.env` + `SKIP_VERTEX_SEARCH=0` override (P-2 패턴 정합)
- N=3 × 2 commit (5078a2d vs ba44637) = 6 run
- §13-7 측정 표준 (max_retries=0, warmup 2, timeout, sleep 60s, utf-8) 적용

### 직전 박제 자산 정정 reference

`(NEW)-B_option3_code_review.md` 끝에 "부록 정정 reference (§14-3 (NEW)-B 트랙 2 결과)" 섹션 추가:
- §14-2 commit 식별 정정
- Phase A 가설 기각
- Phase B 재해석 정확화
- Step 1b patch 본 검증 시나리오 자체 변경 필요

timeline 정합 유지 (직전 commit `ca148bc` 시점 박제 보존), 정정 reference 로 박제 자산 신뢰성 보장.

### 신규 트랙 후보 (Phase 3 진입 전 또는 병행)

- chroma collection_count=0 결함 진단 (P-3 또는 (NEW)-C, ★★★)
- (β) 혼합 시나리오 측정 트랙 (사후 e2e 효과 측정)
- Phase 3 본 측정 driver 작성 (시나리오 (α) + N=3×2 인프라)

### 다음 단계 분기 (user 결정 미박제)

- (P3-A) Phase 3 본 측정 즉시 진입 (시나리오 α + topics/<slug>.env override)
- (P3-Q) chroma 결함 진단 트랙 (P-3 또는 (NEW)-C) 우선
- (P3-S) 병행 (Phase 3 진입 + chroma 진단 별도 트랙)

────────────────────────────────────────────────

## §14-9 close (2026-05-18) — search backend × LLM provider audit + β layered gate + vertex metadata persistence

§14-9 main mission close. audit (Step A/A1/A2) → chain test (Phase 1/2) → whitelist policy 별 cycle (§14-9-W A/B/C) → vertex metadata persistence (Phase 3) 순차 진행. 별도 sub-task (a) (`web_results_to_documents` 화이트리스트 확장, 본 file:110 박제) 정식 종결.

### 미션 결과 요약

| 영역 | 결과 | commit |
|---|---|---|
| Step A — search backend + LLM provider 활용 식별 | vertex_grounding 단일 통합 확정, serpapi dead, 5 backend × 3 provider matrix 박제 | `f858af5` |
| Step A1 — credential exposure audit | 5 key prefix 0 hits in git history (.env.* gitignored from `0c59bff`), §12-11-7 precedent 비해당 | `f858af5` |
| Step A2 — § 6-f 정정 + legacy fusion + 3-layer schema | 3 axis 분리 (raw vertex 3 keys / raw legacy 9 keys / wrapped 5+meta keys), § 6-f false alarm 정정 | `f858af5` |
| Phase 1 — baseline smoke 2 combination | (i) vertexai×vertex_grounding 22.12s cv 29.6%, (ii) openai×legacy 2.16s cv 18.1%, drift -11.3% (Phase A 회귀 부재) | `4e78b63` |
| Phase 2 — methodology + 2 combination + Q4 drop 진단 | (iii) vertexai×legacy 2.04s, (iv) anthropic×legacy 2.21s, legacy chain provider-independent 확정. Q4 EN 100% drop = `search.py:1827-1844` gatekeep | `3b2ebae` |
| §14-9-W Step A — whitelist audit | gate mechanics + 4-source 결합 + refresh_gatekeep_cache 호출 사이트 4. §12-11-4 subdomain stripping **부재 아님** 확인 | `b42a26f` |
| §14-9-W Step B — β layered + γ toggle 설계 | base 78 (KR 58 + EN 학술 11 + 광고 9) + ALLOWED_DOMAINS_EXTRA extend + GATE_KEEP_SOURCES opt-out | `b42a26f` |
| §14-9-W Step C — 구현 + 측정 | `.env:213` 확장 + `core/config.py:684` refresh hook + `docs/topic_env_guide.md` 신규 + Q6 nature/ncbi + Q7 광고 base hit, γ off 시 supplement vendor noise 입증 | `7b407bd` / `4e450b4` |
| Phase 3 — vertex metadata persistence | `tools/web_rag/ingest_docs.py:_promote_item_metadata` helper + 6 metadata dict literal 사이트 spread. **A side 0% → B side 100% (any_promote, 12 records)**. Q4 (benfotiamine EN): cornell.edu + alt_urls=PubMed 정상 보존 ★★★★★ | `0ca337f` / `4b8d642` |

### sub-task 별 종결 status

| sub-task (본 file:109-115 박제) | 상태 | 종결 commit |
|---|---|---|
| **(a) `web_results_to_documents` 화이트리스트 확장** — alt_urls / backend / chunk_domain | **closed (2026-05-18 Phase 3 정합)** | `0ca337f` (production) + `4b8d642` (측정) |
| (b) redirect URL resolve 견고화 | 미진입 — Phase 3 측정에서 `vertexaisearch.cloud.google.com/grounding-api-redirect/...` 미해결 다수 관측 (Q4 console log 정합), 별 cycle 후보 |
| (c) footnote label 정밀화 | 미진입 |
| (d) `domain_bonus` 통합 (web search rerank) | 미진입 |
| (e) gemini provider grounding 통합 | 미진입 |
| (e-2) deprecated 라이브러리 마이그레이션 | 미진입 (§12-12-2 정합 영역) |

### production code 변경 면적 (§14-9 전체)

| file | 변경 |
|---|---|
| `tools/web_rag/ingest_docs.py` | `_promote_item_metadata` helper +23 lines + 6 metadata dict literal spread (각 +1 line) = **+29 -6** |
| `core/config.py` | `reload_config_inplace` 의 refresh_gatekeep_cache hook **+5 lines** (try/except + import) |
| `.env` | ALLOWED_DOMAINS 확장 58→78 (disk-only, `.gitignore:12` 정합 — commit 외) |
| `docs/topic_env_guide.md` | 신규 (β/γ 운영 가이드 + Finding C risk 경고) |
| `README-dev.md` | §12-11-4 closed 표기 update |
| `scripts/§14-9/backend_isolated_smoke.py` | setdefault → 명시 override (W Step C § 6-f 정합) |
| `scripts/§14-9/fusion_observability.py` | 신규 driver (Phase 3 측정) |

### 박제 자산 위치

- `scripts/output/§14-9/step_a_backend_provider_matrix.md`
- `scripts/output/§14-9-A1/credential_exposure_audit.md`
- `scripts/output/§14-9/step_a2_fusion_and_verify.md`
- `scripts/output/§14-9/step_b_phase2_extended_smoke.md`
- `scripts/output/§14-9-W/step_a_whitelist_diagnosis.md`
- `scripts/output/§14-9-W/step_b_layered_gate_design.md`
- `scripts/output/§14-9-W/step_c_layered_gate_implementation.md`
- `scripts/output/§14-9/step_b_phase3_metadata_persistence.md`
- raw JSON (.gitignored): `phase1_*.json` / `phase3_fusion_obs_*.json`
- console reproducibility: `scripts/§14-9-W/_main_b_q1_q7_console.txt` / `scripts/§14-9/_phase3_after_main_console.txt`

### catch 후보 박제 (README registry 무진입 — 별 cycle 형식화 영역)

| catch # | 명 | 진입 트리거 |
|---:|---|---|
| catch 38 | content-language detection (langdetect) | 토픽 언어 env 도입 + lang-mismatch noise ≥ 10% |
| catch 39 | content length 하한 (body text 컷) | `_filter_non_2xx` 후 stub-page 비율 ≥ 5% |
| catch 40 | LLM-based content quality scorer | catch 38/39 후 잔여 noise ≥ 30% + cost ≤ $0.005/query |
| catch 41 | readability heuristic (textstat) | catch 38/39 적용 후 readability score 분포 cut-off 식별 |
| catch 42 | ad-hoc deny list 보강 (`FILTER_BAD_DOMAINS`) | noise 도메인 set ≥ 5건 (W Step C γ off 측정 + Phase 3 redirect 미해결 후보 set 정합 — ★ 최즉시 적용 가능) |
| catch 43 | language-aware backend routing | 영어 토픽 priority 발생 또는 catch 38 정식 박제 후 — §academic-1 진입으로 trigger 발화 (Step C-1 구현) |
| catch 44 | kr_soc bucket 4-domain identity audit (`koads.or.kr` / `kma.or.kr` / `kabs.or.kr` + `kosac.or.kr`) | §academic-1 cycle close 이후 — KR 학회 정체성 best-effort 확정 필요 (별 cycle) |
| catch 45 | (LOW 유지) A1 fail 3건 재진입 (`journalofadvertising.org` / `earticle.net` / `kosac.or.kr`) — 특히 earticle.net SSL defer | Phase 학술-3 (KCI / RISS backend 직접 API 도입) 진입 시 재평가. **§academic-3 close 후 (2026-05-20)**: 본 cycle 의 `ACADEMIC_DOMAINS` set 보강에 `journalofadvertising.org` 등재됨, 그러나 academic-en 5 runs 자연 진입 0 확인 — 외부 의존 (vertex grounding + SSL/접속) 영역. catch 51 (vertex grounding bias) cycle 진입 시 통합 검토 대기 |
| catch 46 | academic prompt tone 분기 (writer prompt academic hint) | Phase 학술-4 진입 조건 — §academic-1 본 cycle 에서는 defer (minimal stub 또는 비도입) |
| catch 47 | mixed-lang routing 측정 별도 sub-cycle | §academic-1 본 cycle 후속 — mixed 분류 정확도 + vertex+naver 병렬 효과 정량 측정 |
| catch 48 | (lesson) Step B budget 산정 시 신규 함수 본체 line count 누락 — 향후 design step 박제 작성 시 budget 산정 check-list 보강 | §academic-1 Step C-1 에서 +13 예산 vs 실제 +24 diff (185%) STOP 발화 사례. 향후 cycle 의 Step B design 박제 시 budget = (config 변경) + (in-place hook insert) + **(신규 함수 정의 본체 line)** + (substitution net) 산식 정착 필요 |
| catch 49 | (lesson) 측정 driver SDK-level timeout 강제 부재 + probe 환경 일치 강제 lesson | §academic-1 C-3 첫 측정 시도 fail 사례 (header log 1회 후 사용자 kill). 향후 측정 driver = (A) SDK-level force-orphan timeout (daemon thread + join), (B) provider lock (`LLM_PROVIDER` 명시 + 글로벌 .env default 차단), (C) stdout flush stage marker, (D) probe (`sys.executable` venv 일치 + provider 일치) 강제 — 4 항목 default 패턴 정착 |
| catch 50 | gatekeep `_RUNTIME_ALLOWED` upstream 무효화 누락 — 토픽 전환 시 `ALLOWED_DOMAINS_EXTRA` 가 allowed set 에 반영 안 됨 (allowed domain 의 2-layer cache 구조 중 상위 layer 결함) | **close (2026-05-19) §academic-2**. §academic-1 C-3 measurement metric 2 root cause B 박제 (academic-en n=108 → academic-ko n=79, EXTRA 29 누락 drop). **2-layer 구조**: (i) 하위 `_normalized_allowed_domains` lru_cache (settings_gatekeep.py:187) — `refresh_gatekeep_cache()` hook (core/config.py:692-696, §14-9-W Step C Gap 2 fix) 으로 정상 무효화. (ii) 상위 `_RUNTIME_ALLOWED` module global (settings_gatekeep.py:19) — `get_allowed_domains()` short-circuit priority 1, `set_runtime_allowed_domains` (tools/web_rag/search.py:1417) 가 web_search 진입 시 snapshot 박제, `refresh_gatekeep_cache()` 범위 밖 → 직전 토픽 snapshot 잔존. **fix**: `clear_runtime_allowed_domains()` 신설 + `reload_config_inplace` hook (commit `3598568`, +16 line · 107% of budget +15 catch 48 lesson 미세 재현). **정량 증거**: academic-ko `[GATEKEEP] n` 79 → 108 (+29 EXTRA 회복) + `academic_source_ratio` 0.0 → 0.6667 (commit `90acb87` 측정 결과 박제). 박제 chain: `scripts/output/§academic-2/{step_a_entry_audit,step_b_design,step_c_impl_measurement}.md`. 부수 미션 (academic-en ratio) PARTIAL → catch 51/52/53 sub-cycle 후보 분리. |
| catch 51 | (**§academic-4 cycle close 영역 · verdict PARTIAL · Phase 4 commit 4 영역 (2026-05-22)**) **EN academic mode 학술 전용 backend 부재, vertex 단독 의존 (ad-tech bias 는 증상)** — cycle close 사유: 4-backend architecture 정합 작동 ✓ 검증 (catch 51 fix S1 effectiveness hit +3 영역 부분 입증, baseline 5 → 평균 8.0), 4 indicators PASS (business invariant + lang detect + en-vertex + ko-naver), 1 REVIEW (academic_source_ratio mean 0.3915 < 0.60 threshold 미달). root cause: vertex per-backend ratio 0.15~0.29 비학술 dilution 본질 영역 (forbes / medium / marketing blog 비중 ↑). 본 cycle scope (architecture) 안 처분 불가 → **§academic-5 영역 이전** (vertex academic mode 정합 보강 + 산식 layer 변경 영역 중심). 박제: `scripts/output/§academic-4/step_b_design.md` Section 10 (Step C-2 측정 결과 + verdict) + `scripts/output/§academic-5/entry_sketch.md` (다음 cycle entry sketch) | §academic-2 부수 미션 PARTIAL root cause 분리 박제. academic-en query ("consumer behavior in influencer marketing") 의 vertex grounding 결과가 industry / preprint platform / trade publication (forbes, mdpi, medium, researchgate 등) 으로 편향, 학술지 도메인 (springer / wiley / tandfonline 등 EXTRA 29 set) reach 0. **§academic-3 close 후 HIGH 격상 (2026-05-20)**: §academic-3 측정 결과 academic-en ratio 0.0 → 0.3165 (catch 52 fix 후), 임계 0.6 까지 gap **0.2835 = 47% 영역**. **§academic-4 Step A close (2026-05-21)**: description redefine — root cause 가 vertex grounding bias 자체가 아니라 **EN academic mode 의 학술 전용 backend 부재 (vertex general web grounding 단독 의존)** 임. ad-tech bias 는 vertex tool 자체 한계의 증상. A1-a (vertex `Tool(google_search=GoogleSearch())` 빈 객체, 학술 reach toggle 부재 DEAD) + A2-a (vertex 5 runs 학술 hit 8/50 = 16%) + A2-c pilot (Semantic Scholar + OpenAlex 학술 venue 직격, JBR/IJRM Elsevier + MDPI 검출) 정합. A3 5 후보 비교: ② Vertex 옵션 조정 DEAD + ④ Post-process boost DEAD (분모 unique domain set, A2-b) + ⑤ 학술 전용 backend 추가 (Semantic Scholar + OpenAlex) 정량 우월 — pilot ratio 추정 ~0.676 (임계 0.6 충족 안정 마진). 권고 시나리오 **S1 (Option 5 단독)** — catch 43 routing 자연 확장. 박제: `scripts/output/§academic-4/step_a_entry_audit.md`. Step B design 진입 대기. |
| catch 52 | **close (2026-05-20) §academic-3 — 본 미션 PASS + ratio PARTIAL, 잔존 catch 51 위임** (§academic-4 Phase 2 commit 3 영역 ACADEMIC_DOMAINS set 36 → 40 추가 보강, catch 67 정합) | §academic-2 부수 미션 PARTIAL root cause 분리 박제. §academic-2 측정 raw (academic-en all_uniq) 에서 `mdpi.com` (5 runs 모두), `researchgate.net` (3 runs), `pdfs.semanticscholar.org` (1 run), `academic.naver.com` (5 runs 모두) 등이 vertex 결과 분포에 있으나 ACADEMIC_DOMAINS_29 set 미포함 → ratio 0.0. set 보강 시 academic-en ratio 회복 가능. 코드 변경 거의 0 (env / driver set 정의 만), 효과 명확 — **최우선 sub-cycle 후보**. **§academic-3 (2026-05-20)**: Step A audit (`10541d2`) — A1 set 정의 위치 + A2 academic-en 49 도메인 분포 (Q1 엄격) + A3 보강 후보 7 entries 박제. 사용자 결정 ①~④ (`28fe7f9`): 보수적 7 entries 수용 + researchgate 학술 SNS 인정 + catch 45 분리 + set 재명명 Step B 이월. Step B design (`8d6d2e4`) + follow-up (`ddc59a4`): B1 옵션 A 단일 set + 9 카테고리 헤더 / B2 옵션 B `ACADEMIC_DOMAINS_29 → ACADEMIC_DOMAINS` / B3 §academic-2 동일 5 metric + `[GATEKEEP] n` / Risk 박제 (academic-en ratio 예상 ≈0.31 PARTIAL). Step C-1 fix (`296d09d`): measure_ab.py:137-170 set literal 재구성 + line 423 참조 site + 3 토픽 .env 36 entries (5 file +41/-15, 함수 본체/hook/신규 def 변경 0). Step C-2 측정 (`743b5b4`): business invariant Jaccard 1.0 strict 유지 + academic-ko ratio 0.6667 유지 + academic-en ratio 0.0 → **0.3165** (Step B Risk 예상 0.31 정합 ✓) + `[GATEKEEP] n` business 79 회귀 0 + academic 108 → **114** (+6 net = +7 entries - 1 base 중복 `sciencedirect.com`, **catch 52 fix 결정적 증거**). 부수 미션 ratio mean 0.4916 PARTIAL — 잔존 미달 root cause = catch 51 (vertex grounding bias) 위임 (HIGH 격상). 박제: `scripts/output/§academic-3/{step_a_entry_audit,step_b_design,step_c_impl_measurement}.md`. |
| catch 53 | (**LOW 유지** — §academic-3 close 후) `ALLOW_SUBDOMAINS` academic 모드 전용 분기 검토 — semanticscholar subdomain 등 | §academic-2 부수 미션 PARTIAL 의 부수 발화. settings_gatekeep.py:363 `_flag("ALLOW_SUBDOMAINS", False)` default OFF → `pdfs.semanticscholar.org` 등 subdomain 이 base domain (semanticscholar.org, EXTRA 안) 매칭 안 됨. academic 모드 전용 ON 검토 — 단, business 모드 invariant 정합성 검증 필요 (catch 43 routing 과 직교성 사전 확인). 본 진입 trigger 조건 = catch 52 결과 보고 후 진입 결정. **§academic-3 close 후 (2026-05-20)**: 본 측정 영향 0 — academic-en 5 runs 의 도메인 분포에 subdomain 형태 (pdfs.semanticscholar.org 등) 미진입. vertex grounding query 의 stochastic 결과에 따라 재발 가능하나, 본 측정 시점에선 우선순위 낮음. catch 51 (vertex grounding bias) cycle 진입 시 통합 검토 후보 |
| catch 54 | (LOW · 문서 결함) `measure_ab.py:13` docstring "per-run-timeout 240s" 가 실제 default `PER_RUN_TIMEOUT_S=90.0` 와 불일치 | §academic-3 Step C-2 측정 후 발견. §academic-1 C-3 default 변경 (240→90s, commit `d4d6431`) 시 코드 본문 (line 130-133 + argparse line 600) 은 갱신 완료, module-level docstring 만 stale. 측정 영향 0 (driver 실제 동작은 코드 본문 default 90s 사용). **fix 면적 = 1 line substitution**, 다음 인프라 cycle 시 정정 |
| catch 55 | (LOW · Claude Code 환경 한계) Claude Code 환경 (bash_tool/WSL) 의 `.env.<provider>` file detection false negative | §academic-3 Step C-2 측정 진입 시 발견. Claude Code 측에서 `.env.vertex` MISSING 보고 (false negative), 사용자 PowerShell session 측에서 EXISTS (3284 bytes, 2026-05-09). credentials 자체는 환경변수 `GOOGLE_APPLICATION_CREDENTIALS` (service account JSON) 으로 정합 동작. **fix 면적 = 0 (Claude Code 한계)**. Claude Code 환경 audit 시 사용자 PowerShell session 정합 cross-check 단계 추가 권장. §12-23 박제 영역 cross-reference 후보 |
| catch 56 | (LOW-MID · 인프라 cycle 후보) `measure_ab.py:608` driver args output 경로 부재 | §academic-3 Step C-2 측정 후 발견. driver 가 output 경로를 args 로 받지 않아 default 위치 (`§academic-1/c_ab_results.json`) 에 hard-coded write. 사용자가 매 cycle 마다 수동 Copy-Item 으로 cycle 별 위치로 cp 강제. 부수 영향: `§academic-1` baseline 매 측정마다 덮어쓰기. **fix 면적 = +5 line (argparse `--output-dir` arg + out_dir 분기)**, 인프라 cycle 후보 (catch 49 default 변경 패턴과 동일 영역) |
| catch 57 | (LOW-MID · audit cycle 외부 환경 lesson) audit cycle 외부 API 호출 환경 사전 점검 lesson (WebFetch 거부 + WSL bash curl + python urllib + User-Agent + mailto polite pool + backoff 우회 path 박제) | §academic-4 Step A 진입 시 A1-c (API docs 조사) + A2-c (pilot 측정) 단계 발화. Claude Code WebFetch (`api.semanticscholar.org/...` 사용자 거부 · `docs.openalex.org/...` 301 redirect-only) + Claude chat web_fetch 정책 (직접 API call 거부). 우회 path: WSL bash `curl` (mailto polite pool, OpenAlex success) + python `urllib` (User-Agent 헤더 + 2s backoff, Semantic Scholar 429 fallback success). 정합 박제 형태: audit cycle 진입 시 외부 호출 도구 (WebFetch / curl / urllib) endpoint 별 정책 사전 점검 — 특히 anonymous shared pool 호출은 `User-Agent` 헤더 명시 + `Retry-After` backoff 필수. 영향 범위: §academic-4 Step B/C (`measure_ab.py` 확장 시 ss+oa 호출 path), 본 cycle 외 모든 외부 API audit 영역. **박제 완료 (§academic-4 Step A inline, Step B/C 영역 영향)**. **§academic-4 Step C-1 commit 1 (2026-05-22) 추가 보강**: (1) **anonymous pool reality check** — SS commit 1 smoke 3 attempts 모두 429 (CloudFront ICN57-P3 throttle), A2-c pilot 200 OK (1.36s) 가 일시 상태였음 확인. SS anonymous shared pool production 부적합 박제. Sub-decision 1A → 1A' 전환 (SS skip toggle default + key 발급 후 `x-api-key` 헤더 자동 활성). (2) **mailto consistency lesson** — A2-c pilot 사용 개인 메일 (`*@gmail.com`) 과 SS API key request form 사용 회사 메일 (`sungsu.oh@bellcomm.co.kr`) 불일치 시 polite pool 효력 약화 가능성. 박제 코드 / step_b_design / README 영역 mailto 일괄 정정 시 grep -rn 으로 잔존 0 재확인 단계 강제 권고 |
| catch 58 | (LOW-MID · academic-en 측정 토픽 단일성) academic-en `c_verification.json` 측정 토픽 단일성 — 5 runs = single query (`consumer behavior in influencer marketing`) 반복, multi-query 다변화 검토 | §academic-4 Step A 진입 시 A2-a / A2-c 단계 발견. §academic-3 `c_verification.json` academic-en 의 5 runs 가 5 토픽이 아니라 **단일 query 반복**. 정합성 우려: pilot ratio ~0.676 추정이 본 single query 1 종에 한정. query 분포 다양화 (예: "social media advertising effects", "influencer authenticity perception") 시 ratio 분포 polluted 가능. 처분: Step C 측정 design 영역에서 academic-en query 다변화 (~3~5 query) 검토 — 단 §academic-3 baseline 정합성 유지 측면에서 **기존 query 1 종 + 신규 query 2~3 종 추가 (기존 단독 비교 가능 구조)** 권장. **박제 완료 (§academic-4 Step A inline, Step C design 영역 이전)** |
| catch 59 | (LOW-MID 후보 · DOI → publisher 매핑) OA PDF 미존재 paper 의 DOI → publisher 도메인 매핑 fallback (Crossref REST / OpenAlex works/doi / 정적 매핑 table 중 선택) | §academic-4 Step A 진입 시 A2-c Semantic Scholar entry 0 발견 (Journal for Current Sign, DOI `10.63075/jcs.v3i1.132`, `openAccessPdf.url=null`) — DOI 만 존재, `openAccessPdf.url` / `venue` 도메인 직접 추출 불가. 정합성 우려: Option 5 학술 도메인 인식 path 의 3 우선순위 중 (2) `openAccessPdf.url` X / (3) `venue` 매칭 X 시 (1) DOI prefix → publisher 도메인 매핑 fallback 필요. 매핑 source 후보: Crossref REST (`api.crossref.org/works/{DOI}` → `URL` 필드 publisher 도메인) / OpenAlex `works/{doi}` 의 `primary_location.landing_page_url` / 정적 DOI prefix → publisher 매핑 table (`10.1016/*` → sciencedirect.com 등). 본 cycle 처분: 후보 박제만, Step B design 시점에서 매핑 layer 채택 여부 결정 (정적 table vs REST 동적 조회 — risk-reward 비교). **§academic-4 Step B 채택 (2026-05-21)**: 3A — 정적 prefix → publisher 매핑 table 내장 (광고/마케팅 핵심 + 인접 STEM 35 entries cover, 신규 prefix 발견 시 logging fallback). Crossref REST / OA works/{doi} 동적 조회 미채택 사유: 추가 latency + OA credit 소비 + fan-out 안정성 우선. 매핑 table 박제: `scripts/output/§academic-4/step_b_design.md` B3-2 (37 entries — 광고/마케팅 10 + 광범위 8 + 사회과학 5 + STEM 8 + preprint 5 + misc 1, **Step C-1 commit 1 보강 시 `10.1177/` SAGE 메인 prefix + `10.21511/` 추가**). **effectiveness 정량 검증 (§academic-4 Step C-1 commit 1 smoke, 2026-05-22)**: OA smoke 1 call (`consumer behavior in influencer marketing`, items=10, elapsed 2.313s, cost 0.001) 의 `domains_unique[:5]` = `['businessperspectives.org', 'journals.sagepub.com', 'mdpi.com', 'sciencedirect.com', 'tandfonline.com']` — **5/5 학술 도메인 hit** (ACADEMIC_DOMAINS 정합). 특히 직전 fallback 영역 3건 (`10.1177/` ×2 + `10.21511/`) 이 본 cycle 37 entries 보강으로 **모두 hit 으로 전환** — unknown DOI prefix logging fallback 비율 0% 도달. catch 59 정적 매핑 table 정합 effectiveness 검증 완료. **채택 (§academic-4 Step B inline, Step C-1 구현 영역, commit 1 smoke effectiveness 박제)** |
| catch 60 | (LOW-MID · multi-backend integration 영역 통합 lesson) Multi-backend dedup 정합성 (60-b: subdomain/redirect 변형) + API response schema versioning (60-c: OpenAlex `host_venue` deprecated / SS Graph v1→v2) + OA credit monitor (60-d: free tier $1/day 임계 0.05%, `meta.cost_usd` log 권고) — 통합 lesson 박제 | §academic-4 Step B design 진행 중 발견. **60-a STOP gate 정밀도** (Issue 5 처분 분기 후보) 는 Step B design Section 1 정의 ("STOP gate 호출 횟수 = successful call 기준") 으로 본 cycle 안 처분 완료. **60-b**: `sciencedirect.com` vs `www.sciencedirect.com` vs `linkinghub.elsevier.com` (DOI redirect 변형) — B3 `_domain_of` 헬퍼에서 host normalize (`www.` / `m.` 제거) + redirect resolve (vertex `_resolve_vertex_redirect` 패턴 답습) 적용 시 해소 가능. Step C 측정 시 unknown publisher 패턴과 함께 모니터링. **60-c**: OpenAlex `host_venue` deprecated → `primary_location.source.display_name` (신규). SS Graph v1→v2 변경 가능성. `extract_domain_from_paper` 4-step early-return 자체가 schema 변경 robust (필드 1개 사라져도 다음 path fallback), 명시적 version check 본 cycle 미도입. **60-d**: OpenAlex free tier $1/day = 100k req/day. `?search=` list call = 10 credit. measure_ab.py 5 runs × 1 query (single, catch 58 유지) × 1 backend = 50 credit per 측정. 임계 100k 의 0.05% 영역. monitoring driver 도입 불필요, OA response `meta.cost_usd` 필드 log 박제만 권고. **후보 박제 (§academic-4 Step B inline, Step C 측정 영역 monitor)** |
| catch 61 | (**MID 활성 · §academic-4 Step C-1 commit 2 SS authenticated pool 정합 검증 완료 (2026-05-22)**) Semantic Scholar API key 발급 후 `x-api-key` 헤더 자동 활성 layer (sub-decision 1A → 1A_prime → 1B 전환 확정) | §academic-4 Step C-1 commit 1 (2026-05-22) — SS commit 1 smoke 3 attempts 모두 429 (CloudFront ICN57-P3 throttle, anonymous shared pool reality check) 후 박제. **commit 1 patch B-1**: `SEMANTIC_SCHOLAR_SKIP=1` env toggle 도입 (semantic_scholar.py 진입 첫 줄, default skip 시 즉시 `_empty_result("SS_SKIP")` 반환 — anonymous 429 fail isolation). **commit 1 patch B-2**: `SEMANTIC_SCHOLAR_API_KEY` env 주입 시 `x-api-key` 헤더 자동 추가 (request 빌드 분기, 코드 변경 불필요). **사용자 측 활성 절차**: (1) SS key 발급 응답 회신 (https://api.semanticscholar.org request form, mailto: `sungsu.oh@bellcomm.co.kr`), (2) `.env.semanticscholar` 의 `SEMANTIC_SCHOLAR_API_KEY=<발급값>` 주입 + `SEMANTIC_SCHOLAR_SKIP=0` 변경, (3) smoke 재검증 (1 successful call · authenticated pool 1 req/s 또는 1 req/min). **본 catch 영역 진입 조건**: SS key 발급 응답 회신 시점. 진입 시 ratio 0.50~0.65 → 0.60~0.75 회복 영역 (1A' 합류 단계 박제, step_b_design.md Risk 정합). 영향 범위: §academic-4 Step C-2 측정 (SS 합류 단계 ratio 재측정), 본 cycle 외 모든 SS 호출 영역 (catch 51 통합 의존). **§academic-4 Step C-1 commit 2 smoke 정합 검증 완료 (2026-05-22)**: SS key 발급 응답 회신 + `.env.semanticscholar` 의 API_KEY 주입 + SKIP=0 변경 후 smoke_ss.py 재실행 → `attempt=0 status=200 size=6796` (X-Cache: Miss from cloudfront authenticated pool 정합) / `items 10 / elapsed 1.984s / error None` / `domains_unique[:5] = ['economics.pubmedia.id', 'ijsrem.com', 'journals.sagepub.com', 'mdpi.com', 'ssrn.com']`. **catch 59 fallback 분야 분포 차이 박제**: OA 0% (10/10 hit, 영미권 주류 publisher 분포) ↔ SS 30% (7/10 hit, multidisciplinary 소형 OA 분포 — `10.63075` / `10.36948` / `10.32535` 미매핑). Step C-2 측정 후 fallback prefix 추가 매핑 cycle 결정 영역. **상태: 후보 → 활성 (1B 전환 확정)** |
| catch 62 | (LOW · process lesson) PowerShell heredoc single quote escape lesson — `1A_prime` (single quote `1A` + apostrophe) → `1A_double_prime` (double apostrophe `1A''`) 자동 변환 사례 | §academic-4 Step C-1 commit 1 (commit `942328f`) message 안 발생. PowerShell here-string `@'...'@` (single-quoted, literal) 안에서 single quote 가 leading apostrophe 와 만나 escape 변환됨 — `Sub-decision 1A → 1A'` 표기 가 `1A''` 으로 자동 박제. 의미 손상 없음 (1A' = 1A_prime, 1A'' = 1A_double_prime 모두 동일 영역), 사후 amend 불요 사용자 컨펌. **prevention 박제**: (a) underscore 표기 — `1A_prime` / `1A_post` / `1A_revised`, (b) 한국어 자연어 — `1A 후속` / `1A 보정`, (c) double quote heredoc + 백틱 escape (`@"...\`\""@`). **본 cycle 적용**: commit 2 message 부터 prime notation 회피, README catch 61 row 안 `1A → 1A_prime` 표기 정합 변경. 영향 범위: 향후 PowerShell heredoc commit message / 한국어 박제 영역 quote escape 모든 cycle. **박제 완료 (§academic-4 Step C-1 commit 2 영역, 사용자 컨펌 안 2 = catch 62 신규 entry 채택)** |
| catch 64 | (LOW · process lesson) PowerShell session `$env:*` 잔존 영역 — smoke driver `load_dotenv(.., override=True)` 강제 lesson | §academic-4 Step C-1 commit 2 1B 단계 진입 smoke 진행 중 발견. PowerShell session 안 직전 turn 의 `$env:SEMANTIC_SCHOLAR_SKIP=1` (1A_prime 단계 환경변수) 가 새 session 또는 새 sub-shell 까지 잔존 → `.env.semanticscholar` 의 `SKIP=0` 설정이 `load_dotenv()` (default `override=False`) 로 덮어쓰기 안 됨 → SS API key 활성 못 하고 SKIP fallback 으로 항상 진입. **prevention 박제**: smoke driver 안 `load_dotenv(path, override=True)` 강제 (PowerShell `$env:*` 우선순위 invert). **본 cycle 적용**: writer_project/scripts/§academic-4/smoke/smoke_ss.py + smoke_oa.py 모두 `override=True` 박제. 영향 범위: 향후 모든 smoke driver / measure driver / pytest fixture 영역의 dotenv 로딩 패턴. 사용자 측 PowerShell 절차: `Get-ChildItem env:SEMANTIC_*` 으로 잔존 영역 점검 + 새 session 진입 시 `Remove-Item env:SEMANTIC_SCHOLAR_SKIP -ErrorAction SilentlyContinue` 권고. **박제 완료 (§academic-4 Step C-1 commit 2 영역, Claude Code 자율 후보 박제 + 사용자 컨펌 영역)** + **정합 검증 완료 (Phase 4 측정 영역, 2026-05-22)** — measure_ab.py dotenv chain (commit 2 amend 영역) 정합 작동, 사용자 측 `$env:*` 직접 주입 불필요 영역 정합. Step C-2 측정 (15 runs) 전체 cycle 안 env 영역 문제 0. 사용자 측 측정 영역 ergonomics ↑ 효과 입증 |
| catch 65 | (LOW · process lesson) Claude chat / Claude Code hand-off prompt 작성 시 driver argparse signature 사전 확인 lesson — 추측 옵션 작성 회피, view 사전 점검 필수 | §academic-4 Step C-1 commit 2 STOP-C-8 영역 (2026-05-22) — Claude Code 측 사용자 측 fan-out 측정 명령 안내 시 `--mode academic --lang en --runs 1 --topic ...` 추측 옵션 사용 → `scripts/§academic-1/measure_ab.py` 실제 argparse (`--topic` + `--warmup` + `--measure` + `--sleep`, MODE/lang 은 토픽 env 안 박제) 와 불일치 → 사용자 측 실행 `unrecognized arguments` fail 발화. **prevention 박제**: hand-off prompt 안 driver 호출 명령 작성 직전 `grep -n "argparse\|add_argument" <driver path>` 1회 강제 view + TOPICS dict / config dict 안 정합 영역 사전 확인. **catch 56 (driver args output 경로 부재) 와 발화 영역 차이**: catch 56 은 driver 측 fix 영역 (argparse arg 추가), catch 65 는 prompt 측 lesson (사전 view 절차 강제). 분리 박제 정합. 영향 범위: 모든 hand-off prompt / smoke 명령 안내 / 사용자 측 PowerShell 명령 영역. **박제 완료 (§academic-4 Step C-1 commit 2 amend 영역, 사용자 컨펌 안 1 = catch 65 신규 entry 채택)** |
| catch 66 | (**MID · methodology · 신규**) ratio 산식의 OA/SS 합류 시 dilution 함정 — `academic_set ∩ all_uniq / all_uniq` 산식에서 분모 (all_uniq) 가 분자 (학술 hit) 보다 빠르게 증가하여 multi-backend 합류 후 ratio 가 오히려 ↓. catch 51 fix effectiveness 측정에 부적합 | §academic-4 Step C-1 commit 2 STOP-C-8 영역 (2026-05-22), 2차 측정 ratio 0.24 (baseline 0.3165 보다 ↓). 4-backend (vertex 17 + legacy 1 + SS 10 + OA 10 fan-out) 합집합 dilution 효과 정량 박제. design Risk 박제 예상 0.45~0.83 보수 영역 대비 큰 하향. 학술 hit 절대 수는 +1 (6, baseline ~5 대비, catch 51 fix S1 effectiveness 부분 입증) 정합. **prevention 박제**: (1) 학술 hit 절대 수 (academic_hit_count) primary metric 추가 — Phase 2 commit 3 run_single 산출 영역 신규 박제, (2) per-backend ratio 분리 측정 (vertex / legacy / ss / oa 별 분리) — Phase 2 commit 3 academic_ratio_per_backend 신규 박제, (3) ratio 산식은 ACADEMIC_DOMAINS set 완전 정합 영역 가정 시에만 정합. **처분 영역**: 부분 처분 (a) 채택 — set 보강 (catch 67 정합 +4 entries) + 산식 보강 절대 수 추가 (run_single Phase 2 영역 신규 metric), 산식 layer 변경 (all_uniq 정의 영역 — vertex 비학술 blog filter layer 추가 등) 은 §academic-5 이전 (scope creep risk 영역). **박제 완료 (§academic-4 Phase 2 commit 3 영역, 사용자 컨펌 부분 처분 a 채택)** + **정량 검증 완료 (Phase 4 측정 영역, 2026-05-22)** — `academic_ratio_per_backend` 신규 metric 영역 정합 작동, per-backend ratio 정량 박제 영역 (vertex **0.17** range 0.15~0.29 / legacy **1.0** / SS **0.44** / OA **0.80**, 5 runs academic-en 평균). **vertex 비학술 dilution 본질 영역 정량 박제** — forbes / medium / marketing blog 영역 분포가 분모 우세 증가 영역. 산식 layer 변경 영역 (`all_uniq` 정의 영역 — vertex 비학술 blog filter layer 검토) 은 §academic-5 이전 (vertex academic mode 정합 보강 영역과 통합 검토 영역) |
| catch 67 | (LOW · methodology · 신규) ACADEMIC_DOMAINS set 의 학술 영역 누락 — 대학 publication 영역 + 소형 OA 영역 미포함. ratio 산식 측정 시 학술 hit 으로 안 잡혀 dilution 영역 발화 | §academic-4 Step C-1 commit 2 2차 측정 (2026-05-22) — vertex 가 가져온 학술 영역 (`digital.hec.ca` / `docs.rwu.edu` / `knowledge.insead.edu` / `journal.seisense.com`) 4 종이 ACADEMIC_DOMAINS 36 set 안 미포함 → 학술 hit 으로 안 잡힘. set 보강 후 학술 hit 6 → 10 예상, ratio 0.24 → ~0.40 예상 (Step C-2 측정 정량 검증 영역). **prevention 박제**: (1) 학술 영역 자동 분류 algorithm 영역 (future, §academic-5 이전) — 대학 도메인 패턴 (`.edu`, `.ac.*`, `*.university.*` 등) + 학술 keyword (`journal.*`, `*.publication.*` 등) 자동 인식, (2) 정기적 set 확장 cycle 영역 — measure 결과 unknown 학술 영역 review 주기. **처분 영역**: 부분 처분 (Phase 2 commit 3 영역 +4 entries 추가 — HEC Montreal / Roger Williams Univ / INSEAD / SEISENSE Journal, ACADEMIC_DOMAINS 36 → 40), 자동 분류 algorithm 영역 (future) 은 §academic-5 이전. **박제 완료 (§academic-4 Phase 2 commit 3 영역, set 4 entries 보강 정합)** + **정량 검증 완료 (Phase 4 측정 영역, 2026-05-22)** — set +4 entries (HEC / RWU / INSEAD / SEISENSE) effectiveness 부분 입증 영역. academic-en `academic_hit_count` 평균 **8.0** (baseline 5 + commit 2 1 run 시점 6 대비 추가 +2 영역), `academic_source_ratio` 평균 0.28 (직전 1 run 0.24 대비 +0.04). vertex per-backend ratio 영역 신규 4 set entry 정합 hit 영역 확인 (예상 0.24 → ~0.40 영역은 일부 달성, 완전 도달 영역은 §academic-5 vertex 보강 + 자동 분류 algorithm 영역 의존). 자동 분류 algorithm 영역 (`.edu` / `.ac.*` 패턴 + 학술 keyword 자동 인식) 은 §academic-5 future 영역 |

### 후속 트랙 후보 (사용자 결정 영역)

1. catch 42 별 cycle — `FILTER_BAD_DOMAINS` 즉시 적용 (`purebulk` / `lifeextension` / `doublewoodsupplements` + `vertexaisearch.cloud.google.com/grounding-api-redirect/...` 후보 set)
2. catch 38/39 별 cycle — content-quality filter layer 도입
3. ~~catch 43 별 cycle — language-aware backend routing~~ → **§academic-1 Step C-1 진입 (2026-05-19)**
4. catch 44 별 cycle — kr_soc bucket identity audit (§academic-1 cycle close 후)
5. catch 45 별 cycle — A1 fail 3건 재진입 (Phase 학술-3 trigger)
6. catch 46 별 cycle — academic prompt tone 분기 (Phase 학술-4 trigger)
7. catch 47 별 cycle — mixed-lang routing 측정 sub-cycle
8. sub-task (b)~(e) 잔여 cycle — redirect URL resolve / footnote label / domain_bonus / gemini provider grounding

### close commit chain (참조)

```
4b8d642 §14-9 Step B Phase 3 — A/B 측정 (metadata 보존율 + Phase 3 박제)
0ca337f §14-9 Step B Phase 3 — vertex metadata persistence + driver (whitelist 확장 + fusion_observability)
4e450b4 §14-9-W Step C — base 확장 효과 측정 (A/B × 7 query, 경량 EXTRA / γ off verify)
7b407bd §14-9-W Step C — β layered + γ toggle 구현 (config + 코드 patch)
b42a26f §14-9-W Step A + B 박제 자산 (whitelist 진단 + β layered / γ toggle 설계)
3b2ebae §14-9 Step B Phase 2 — methodology 보강 (log-capture) + ★★★★☆ 2 combination + Q4 drop 진단
f858af5 §14-9 Step A + A1 + A2 박제 자산 (audit chain + 정정 reference 부록)
4e78b63 §14-9 Step B Phase 1 — baseline smoke driver + measurement (vertexai vs openai legacy, drift -11.3%)
```

**status: closed (2026-05-18)** — §14-9 main mission 전체 종결. sub-task (a) 정식 close, (b)~(e) 미진입 별 cycle 후보 보존.

---

## §academic-1 close (2026-05-19) — 학술 모드 통합 옵션 B (catch 43 + MODE infra)

`81894f3` C-1 (catch 43 hook + MODE/EXPECTED_LANG config + academic env templates) + `c927a70`/`b2c7c86` C-2 measurement driver (+ hotfix) + `853ed11` C-3 측정 (3 topics × 5 runs · vertex) + `2ac1689`/`79f6ba0` catch 49/50 follow-up + `d4d6431` driver default 변경 (timeout 240→90s + redirect monkey-patch opt-in).

본 미션 (catch 43 routing 메커니즘 + business invariant) 5 metric 중 4 PASS, metric 2 REVIEW (root cause A/B 박제: driver redirect monkey-patch 부작용 + gatekeep cache stale → catch 50 sub-cycle 후보). 박제: `scripts/output/§academic-1/step_{a,b}_*.md` + `step_c_impl_measurement.md`.

close commit chain (참조):
```
d4d6431 §academic-1 follow-up — measure_ab.py driver default 변경 (C-3 lesson 적용)
79f6ba0 §academic-1 follow-up — README-dev catch 50 등록 (gatekeep cache invalidation 결함)
2ac1689 §academic-1 follow-up — README-dev catch 49 등록 (driver SDK-level timeout + probe lesson)
853ed11 §academic-1 Step C-3 — measurement + 결과 박제
b2c7c86 §academic-1 Step C-2 hotfix — driver SDK-level timeout + provider lock + flush stage + probe 강화
c927a70 §academic-1 Step C-2 — measurement driver
d2e9db0 §academic-1 follow-up — README-dev catch 48 등록 (Step B budget 산정 미스 lesson)
81894f3 §academic-1 Step C-1 — implementation (catch 43 + MODE infra + academic env templates)
7dfc8c6 §academic-1 follow-up — README-dev catch index 44/45/46/47 등록
989b0ef §academic-1 Step B — design (read-only)
5349a9c §academic-1 Step A — entry audit (read-only)
```

**status: closed (2026-05-19)** — §academic-1 본 미션 (catch 43 + MODE infra + business invariant) 정식 종결. 부수 미션 (academic source ratio 정량) 미달성 → catch 50 sub-cycle 후보 보존. catch 44/45/46/47 별 cycle 후보 보존, lesson catch 48/49 정착.

---

## §academic-2 close (2026-05-19) — catch 50 fix (gatekeep `_RUNTIME_ALLOWED` upstream 무효화 해소)

`85579d2` Step A follow-up (catch 50 가설 재작성: lru_cache 협의 → `_RUNTIME_ALLOWED` upstream 광의) + `a62c6d6` Step A entry audit (A1·A2·A3 read-only) + `33f0cf0` Step B design (read-only, 후보 2 채택: `clear_runtime_allowed_domains` 신규 + `reload_config_inplace` hook) + `4b75bc5` Step B follow-up (B8 4개 사용자 결정 박제 + STOP-3/STOP-4 추가) + `3598568` Step C-1 fix 본체 (settings_gatekeep.py + core/config.py, +16 line) + `90acb87` Step C-2 측정 결과 박제 (catch 50 fix 정량 증거).

본 미션 (catch 50 — gatekeep `_RUNTIME_ALLOWED` upstream 무효화 해소) **PASS**. 정량 증거: academic-ko `[GATEKEEP] n` 79 → 108 (+29 EXTRA 회복, 5/5 runs 일관) + `academic_source_ratio` 0.0 → 0.6667 (dbpia + kiss.kstudy hit). 회귀 0 — business invariant Jaccard 1.0 strict (B8 #3 정합) + 4 metric PASS 회귀 0. 부수 미션 (academic source ratio mean ≥ 0.6) **PARTIAL** — mean 0.3333 (academic-ko 0.6667 PASS + academic-en 0.0 잔존, catch 50 외부 root cause). 박제: `scripts/output/§academic-2/step_{a_entry_audit,b_design,c_impl_measurement}.md`.

close commit chain (참조):
```
(이 commit) §academic-2 close — README §academic-2 close section + catch 50 close 표기 + catch 51/52/53 등록
90acb87 §academic-2 Step C-2 — 측정 결과 박제 (catch 50 fix 정량 증거)
3598568 §academic-2 Step C-1 — catch 50 fix 본체 (clear_runtime_allowed_domains 신설 + reload hook + __all__)
4b75bc5 §academic-2 Step B follow-up — design doc 사용자 결정 박제 (B8 4개 결정 + STOP-3/STOP-4 추가)
33f0cf0 §academic-2 Step B — design (read-only)
a62c6d6 §academic-2 Step A — entry audit (read-only)
85579d2 §academic-2 Step A follow-up — README-dev catch 50 가설 재작성 (_RUNTIME_ALLOWED upstream 무효화 누락)
```

**status: closed (2026-05-19)** — §academic-2 본 미션 (catch 50 fix: `_RUNTIME_ALLOWED` upstream 무효화 해소) 정식 종결. 부수 미션 (academic source ratio mean ≥ 0.6) PARTIAL — academic-ko 단독 PASS / academic-en 잔존 (catch 50 외부, scope creep 경고 박제 정합으로 본 cycle 안 시도 금지). sub-cycle 후보 등록: catch 52 (MID 최우선 — `ACADEMIC_DOMAINS_29` set 보강) · catch 53 (LOW-MID — `ALLOW_SUBDOMAINS` academic 분기) · catch 51 (LOW — vertex grounding bias 정량). lesson: design B5 budget 산식에 PEP 8 separator blank line 항목 포함 권장 (catch 48 lesson 미세 재현 107%, 별 sub-catch 박제 불필요).

---

## §academic-3 close (2026-05-20) — catch 52 fix (`ACADEMIC_DOMAINS` set 글로벌 학술 플랫폼 보강 7 entries)

`10541d2` Step A entry audit (A1·A2·A3 read-only — set 정의 위치 + academic-en 49 도메인 분포 분석 + 보강 후보 7 entries 박제) + `28fe7f9` Step A follow-up (사용자 결정 ①~④ 박제: 보수적 7 entries 수용 + researchgate 학술 SNS 인정 + catch 45 분리 + set 재명명 Step B 이월) + `8d6d2e4` Step B design (read-only — D1 카테고리 주석 + D2 변수 재명명 grep + D3 측정 계획 + D4 STOP/Self-check + D5 commit 정책) + `ddc59a4` Step B follow-up (사용자 결정 ①~④ + Risk 박제: academic-en ratio 예상 ≈0.31, PARTIAL 가능 박제) + `296d09d` Step C-1 fix 본체 (measure_ab.py:137-170 set literal 재구성 + line 423 참조 site + 3 토픽 .env EXTRA 36 entries + 9 카테고리 헤더, 5 file +41/-15) + `743b5b4` Step C-2 측정 결과 박제.

본 미션 (catch 52 — `ACADEMIC_DOMAINS` set 글로벌 학술 플랫폼 누락 해소) **PASS**. 정량 증거: academic-en/ko `[GATEKEEP] n` 108 → 114 (+6 net = +7 entries - 1 base 중복 `sciencedirect.com`, **catch 52 fix 결정적 증거**) + academic-en `academic_source_ratio` 0.0 → 0.3165 (HIGH 3 회수: mdpi/researchgate/academic.naver). 회귀 0 — business invariant Jaccard 1.0 strict + academic-ko ratio 0.6667 회귀 0 + 다른 4 metric PASS. 부수 미션 (academic source ratio mean ≥ 0.6) **PARTIAL** — mean 0.4916 (academic-ko 0.6667 PASS + academic-en 0.3165 잔존, 임계 0.6 미달, Step B Risk 박제 예상 0.31 정합 ✓). 박제: `scripts/output/§academic-3/step_{a_entry_audit,b_design,c_impl_measurement}.md`.

### Cycle 회고

본 cycle 은 catch 52 fix 의 본 미션 PASS + 부수 미션 PARTIAL 의 이중 verdict 로 종료. Process lesson 3개 재현:

1. **catch 48 lesson 미세 재현 (148%, §academic-2 의 107% 차수 확대)** — design D5 추정 +21 line vs actual +31 line. 사유: 9 카테고리 헤더 PEP 8 separator 8 + inline `#` 주석 stand-alone 분리. 향후 design budget 산식에 "카테고리별 separator + inline 주석 stand-alone" 항목 명시 카운트 권장.
2. **Step B Risk 박제 정확성 검증** — Step B follow-up (commit `ddc59a4`) 의 academic-en ratio 예상 ≈0.31 (HIGH 4 hit / 평균 13 도메인 가정) 이 실측 0.3165 와 거의 완벽 일치. 박제 시스템의 사전 분석 정밀도 검증 — 향후 cycle 진입 시 Risk 박제를 "PARTIAL 가능성 사전 정량" 단계로 정착 권고.
3. **catch 56 후보 발견** — Step A audit 단계에서 추가 후보 7 entries 중 `sciencedirect.com` 이 기존 base 78 set 중복 발견 → net +6 신규. `[GATEKEEP] n` +6 정합 (예상 +7 - 1). 미래 audit 의 "추가 후보 도메인 grep 사전 검증" 단계 강화 lesson.

### 잔존 영역 + 신규 catch

- **HIGH 격상**: catch 51 (vertex grounding 영문 학술 reach 정량, §academic-4 본 미션 후보) — gap 0.3165 → 0.6 = 47% 영역
- **LOW 유지**: catch 45 (`journalofadvertising` 등 A1 fail, 본 측정 자연 진입 0 확인) · catch 53 (`ALLOW_SUBDOMAINS` academic 분기, 본 측정 영향 0)
- **신규 등록**: catch 54 (docstring stale, LOW) · catch 55 (Claude Code .env detection mismatch, LOW) · catch 56 (driver args output 경로 부재, LOW-MID)

close commit chain (참조):
```
(이 commit) §academic-3 close — catch 52 fix + PARTIAL ratio 박제
743b5b4 §academic-3 Step C-2 — 측정 결과 박제 (catch 52 fix 정량 증거)
296d09d §academic-3 Step C-1 — catch 52 fix 본체
ddc59a4 §academic-3 Step B follow-up — 사용자 결정 ①~④ + Risk + PARTIAL 박제
8d6d2e4 §academic-3 Step B — design (read-only)
28fe7f9 §academic-3 Step A follow-up — 사용자 결정 ①~④ 박제
10541d2 §academic-3 Step A — entry audit (read-only)
```

**status: closed (2026-05-20)** — §academic-3 본 미션 (catch 52 fix: `ACADEMIC_DOMAINS` set 글로벌 학술 플랫폼 7 entries 보강) 정식 종결. 부수 미션 (academic source ratio mean ≥ 0.6) PARTIAL — academic-ko 단독 PASS / academic-en 0.3165 잔존 (catch 52 외부, scope creep 경고 박제 정합으로 본 cycle 안 시도 금지). sub-cycle 후보: **catch 51 HIGH 격상** (§academic-4 본 미션 후보) · catch 45/53 LOW 유지 · catch 54/55/56 신규 등록 (LOW/LOW/LOW-MID). lesson: catch 48 lesson 재정착 (148% oversize, PEP 8 separator + inline 주석 stand-alone 산식 명시 권장) + Step B Risk 박제 정확성 검증 (예상 0.31 ↔ 실측 0.3165 정합) + sciencedirect base 중복 발견 (추가 후보 도메인 grep 사전 검증 lesson).

---

## §paper-writer-2 seed 주입 트랙 close (2026-06-28) — 외부 seed reference 강제 주입 + verify 3단 폴백

### 결론 (트랙 완료)

외부 seed reference (교수님 지정 핵심 인용 18편) 를 OA/SS fan-out **전에** paper mode 회수 파이프라인에 강제 주입하는 트랙 완료. paper 가 매번 누락하던 "반드시 인용해야 할" 선행연구를 결정론적으로 References 에 포함.

구현 (`agent/web_search.py`):
- **`_load_and_hydrate_seeds(section_type, existing_chunks=None)`** — seed JSON 로드 → section slug 매칭 core 항목 (`context` 는 `SEED_INCLUDE_CONTEXT=1` 시) → `fetch_key.title` 로 `openalex_search` hydrate → verify → 정규화 `{title,authors,year,venue,doi,abstract,_backend}` 반환. `SEED_DRY=1` 시 section 무시 + `automating-abercrombie-2024` 1건만 (단위 점검용).
- **`_clean_chunk_text(chunk)`** — title/abstract/venue **+ authors 리스트 각 원소** HTML 태그 strip + 유니코드 하이픈 (U+2010/2011/2013/2014) → ASCII `-` + 연속공백 정리. seed·일반 chunk 양쪽에 `paper_section_fetch` 회수 직후 **단일 지점** 적용.
- **`paper_section_fetch` 배선** — `all_chunks` 초기화 직후·fan-out 전 seed extend → fan-out → 단일 클린징 → **출구 doi-dedup** (keep-first, seed 먼저 들어가 보존, doi 없는 chunk 통과) → return.
- **seed 선별 필터** — `priority=='core'` 항상 / `'context'` 는 flag 시 / 그 외 (`hold`·`oa_unresolved`·`oa_unindexed`) 주입 제외 (데이터는 JSON 에 보존).

### verify 3단 폴백 (catch 76 해소)

1. **doi-match**: `seed.verify_labels.doi == 회수 doi` → 채택
2. **arxiv-match**: 회수 doi 의 `10.48550/arxiv.(\d+\.\d+)` 추출 id == `seed.verify_labels.arxiv` → 채택
3. **title-jaccard ≥ 0.8**: doi/arxiv 어긋나도 제목 토큰 자카드 일치 시 채택

3단 전부 실패 → 어느 단계서 떨어졌는지 WARNING 로그 후 skip (catch 70: 무흔적 폐기 금지).

### 태깅 — `_backend="openalex"`

seed chunk 는 `_backend="openalex"` 강제 태깅 → axis3 학술 분자 (oa) 에 합류. `"seed"` 신규 backend 값 금지 — 분모만 키우고 분자 0 기여하는 dilution 함정 (catch 66 계열) 회피.

### 최종 측정 (상표 토픽, `--measure 1`, 2026-06-28)

- **seed 채택: 13/13 injectable core** (core 15 중 2 = `automatic-tm-detection-2026`·`vanheuven-phonetic-tm` 를 OA 미색인으로 `hold` 강등 → injectable 13). 위양성 (false-negative) **0**.
  - SBERT (`sbert-2019`): seed doi=ACL `10.18653/v1/D19-1410`, OA=arXiv `10.48550/arxiv.1908.10084` → **arxiv-match 로 구제** (catch 76).
  - STS-benchmark: 원본 제목 'Crosslingual'(붙임) 0건 → OA 색인 정확표기 'Cross-lingual'(하이픈) 교체 후 arxiv-match 채택.
- **References 품질**: HTML 태그·유니코드 하이픈 잔존 **0** (title/venue/abstract + authors `Yu-Kun Lai` 정규화 확인). axis1 APA PASS (1.0, n=169).
- **출구 dedup**: seed↔일반 doi 충돌 시 1건 병합·seed 보존 (오프라인 검증). 실측에선 충돌 0건.

### 측정 주의 (catch 77)

seed 효과를 **oa_ratio 로 읽지 말 것**. oa_ratio 는 vertex 수율 변동 (run 별 총 chunks 137→169, vertex 0.62→0.686) 에 희석되어 seed 11→12 증가에도 0.38→0.314 로 **오히려 하락**처럼 보임. seed 절대 기여는 일정 (+0.05, oa 0.26→0.31). **결정 지표 = 절대 채택수 (13)**, 비율 아님.

### catch 박제

- **catch 76** (MID · methodology · 신규): OpenAlex 가 출판본 DOI 대신 arXiv preprint DOI (`10.48550/arxiv.*`) 를 색인하는 경우 → doi-only verify 가 정상 seed 를 위양성 탈락 (SBERT: seed=ACL DOI `10.18653/v1/D19-1410` vs OA=arXiv `10.48550/arxiv.1908.10084`). **해소**: verify 를 3단 폴백 (doi-match → arxiv-match → title-jaccard≥0.8) 으로 확장. arxiv-match 는 회수 doi 에서 `10.48550/arxiv.(\d+\.\d+)` 추출해 seed arxiv id 와 대조. **정량 검증**: 2026-06-28 실측에서 SBERT·LaBSE·multilingual-distillation 3편이 arxiv-match 로 채택 (직전 run doi-mismatch skip → 구제). prevention: seed JSON 에 doi 와 arxiv 라벨 병기 권장 (둘 중 하나로 hydrate 검증 가능).
- **catch 77** (MID · methodology · 신규): seed 주입 효과를 axis3 oa_ratio 로 평가하면 vertex 수율 변동에 가려짐 — seed 가 oa 분자·분모 동시 증가시키나 vertex chunk 수 변동폭이 더 커서 oa_ratio 가 오히려 하락 가능 (2026-06-28: seed 11→12 증가에도 oa 0.38→0.314). **해소**: seed 효과는 **절대 채택수** (deterministic, 13/13 injectable) 로 평가. oa_ratio 는 backend 수율 비율 지표로만 사용, seed 기여 측정에 부적합. catch 66 (ratio dilution) 의 seed-track 특수 사례 — 분자 절대 수 metric 우선 원칙 재확인. **갱신 (2026-07-04, axis3 재설계): 신 산식 `academic_ratio = (OA+SS+vertex_academic)/total` 에서 vertex_web(비학술)이 분모 페널티로 명시적 처리됨 → oa_ratio dilution 은 진단용 보조지표로 강등, 판정은 academic_ratio 단일. 아래 close 섹션 참조.**

### seed JSON fetch_key.title 보정 (skip 3건, `scripts/§paper-writer-1/seeds/seed_references_trademark-similarity.json`)

OA 실제 회수 결과로만 교체 (추측 제목 생성 금지 원칙 준수):
- **sts-benchmark-2017**: `"… Semantic Textual Similarity Multilingual and Crosslingual …"` → OA 색인 정확표기 `"… Semantic Textual Similarity - Multilingual and Cross-lingual …"` 교체. arxiv `1708.00055` 유지 → **재회수 arxiv-match 채택 확인**.
- **automatic-tm-detection-2026**: 제목 일반적이라 'Pascal VOC' 오회수 + pii/venue 결합 query 도 미회수 → 2026 신간 OA 미색인 추정. `priority: core→hold`, `status="oa_unresolved"`, `_priority_original` 보존. OA 색인 확인 시 fetch_key 교체 후 core 복귀 (re-entry).
- **vanheuven-phonetic-tm**: 제목/저자 결합 query 모두 무관 회수 → OA 미색인 확인. `priority: core→hold`, `status="oa_unindexed"`, 데이터 보존. 대체 색인처 확보 시 재평가 (re-entry).

### re-entry 조건

1. `automatic-tm-detection-2026` / `vanheuven-phonetic-tm` 의 OA 색인 확인 또는 대체 DB 확보 시 → `oa_recon_note` 갱신 + `priority` core 복귀 + 재측정.
2. SS 백엔드 무응답 (ss_ratio=0, catch 74/61 계열) 해소 시 axis3 재평가. **→ 해소 (2026-07-04): catch 74 로 SS 부활 + 아래 「axis3 재설계 close」 섹션에서 재평가 완료.**
3. axis3 `combined_ratio` 구조 quirk (세 비율 평균 ≤0.333 → `≥0.5` 영구 미달) 임계 재설계는 별 task. **→ 해소 (2026-07-04): 아래 「axis3 재설계 close」 — combined-mean 폐기 → academic_ratio 단일 판정 (임계 0.50).**

### commit chain (참조)

```
(이 commit) §paper-writer-2 seed 주입 트랙 close — 코드 + JSON 보정 3건 + dev 박제 (catch 76/77)
```

**status: closed (2026-06-28)** — §paper-writer-2 seed 주입 트랙 (코드) 정식 종결. 채택 13/13 injectable core (위양성 0) + References clean (HTML/하이픈 잔존 0) + verify 3단 폴백 (catch 76) + 절대수 평가 원칙 (catch 77) 박제. 잔존 별 task: OA 미색인 2건 (hold, re-entry 조건 ①) · SS 무응답 (catch 74) · combined 임계 재설계.

---

## §paper-writer-2 catch 72 쿼리 교정 트랙 close (2026-07-04) — section_to_query topic-scoped override (상표 도메인 앵커)

### 결론 (트랙 완료)

seed 주입 트랙의 자매 트랙 — "좋은 논문 주입"(seed) 의 나머지 반쪽 "나쁜 논문 차단"(쿼리 교정) 완료. section_to_query 범용 tail 이 topic 뒤 append 되어 도메인 무관 논문을 회수하던 문제 해소. 인용 정밀도 작업 완결.

구현 (`agent/web_search.py` section_to_query):
- **topic-scoped override** — topic 소문자에 `"trademark"` 포함 시에만 발동하는 override dict 를 기존 범용 mapping 조회 前에 가드 삽입. 미포함 topic·미등록 섹션은 범용 mapping 자연 폴백 (딴 주제 영향 0, 격리 검증 완료).
- **5섹션 tail = 상표 도메인어 3~4단어** — Introduction/Theoretical Background/Proposed Framework/Research Design/Expected Contributions 각 tail 에서 방법명·generic 배제, trademark/confusion/dilution/consumer 도메인어만. 범용 mapping dict 값은 한 글자도 미변경 (추가만).

### 진단 (핵심 — 두더지 잡기)

generic·방법명 토큰은 각자 "자기 분야" 논문을 끌어옴: `model/construct`→소프트웨어, `measurement/consumer`→일반마케팅, `phonetic/semantic`→번역·언어학. **노이즈 범인은 방법명 부재가 아니라 generic 존재.** 방법 논문은 seed 담당이므로 쿼리 tail 에 방법명 불필요 — seed 트랙과 역할 분담 (쿼리=도메인 회수, seed=방법 회수).

### 최종 측정 (Proposed Framework 섹션, OA+SS raw 회수, seed·vertex 격리)

R2→R6 궤적 (동일 조건 4-way):

| 버전 | tail | OA | SS | 명백무관 |
|---|---|---:|---:|---:|
| R2 (범용, before) | measurement model construct operationalization scale | 6 | 0 | 2 |
| R3 (v1 과교정) | phonetic Levenshtein visual Jaro-Winkler semantic embedding cosine | 0 | 0 | — |
| R4 (v2 방법명완화) | similarity measurement phonetic semantic | 9 | 0 | 3 |
| R5 (v3 도메인전용) | trademark confusion dilution | 9 | 4 | **0** |

5섹션 통일 실측 (R6): 전 섹션 명백무관 **0/5**, SS 전 섹션 ≥1 (0→7/1/4/2/5). OA recall 9~10 안정.

### 측정 주의 (recall 절벽)

도메인 명사 과다 강제 시 catch 72 의 정반대 실패 = recall 0 붕괴 (R3: 희귀 방법명 5개 AND 매칭 → OA 0건). **처방은 "특정 방법명 추가"가 아니라 "generic 제거"** — 도메인어는 흔한 단어라 recall 유지, generic 만 제거하면 노이즈만 빠짐.

### catch 박제

- **catch 72** (HIGH · retrieval · 해소): section_to_query 범용 tail (generic/방법명) 이 topic 뒤 append 되어 도메인 무관 논문 회수 (소프트웨어·일반마케팅·번역·언어학). **해소**: topic-scoped override, tail=상표 도메인어 3~4단어, 방법명·generic 배제. **정량 검증**: 2026-07-04 실측 5섹션 명백무관 0/5 (R2 before 2건 → 0). prevention: 쿼리 tail 은 도메인 앵커 전용, 방법 논문은 seed 담당 (역할 분리 원칙).
- **catch 74 부분 해소** (SS 무응답): SS 0건 원인이 백엔드 고장 아닌 **장쿼리 (15단어)** 로 확정 — 12단어 통일 후 전 섹션 SS ≥1 회수 부활. 완전 해소 (OA/SS 쿼리 길이 분리) 는 별 task.
- **catch 78** (MID · cost · 신규): paper_section_fetch 가 vertex_web_search 무조건 호출 (SKIP_VERTEX_SEARCH 무시), chunk 0 기여인데 유료 Gemini 콜 발생. ※grounding 연관 미확인 — "회수 경로 한정 0 기여"로만 기록. 본 트랙 밖.

### re-entry 조건

1. 상표 외 다른 주제 논문 작성 시 → 해당 도메인용 override 추가 필요 (현재 trademark 전용, 범용 mapping 은 fallback 유지).
2. SS 회수 추가 증대 필요 시 → OA/SS 쿼리 길이 분리 (OA=장쿼리 관대, SS=단쿼리 선호). catch 74 독립 트랙.
3. Introduction tail `consumer perception` 이 일반마케팅 노이즈 유입 시 → 해당 토큰 제거 (현재 애매 2건, 명백무관 0 이라 미조정).

### commit chain (참조)

```
(이 commit) §paper-writer-2 catch 72 close — override 블록 + dev 박제 (catch 72 해소 / 74 부분 / 78 신규)
```

**status: closed (2026-07-04)** — §paper-writer-2 catch 72 쿼리 교정 트랙 정식 종결. 5섹션 명백무관 0/5 + SS 부활 (0→전섹션≥1) + recall 유지 (OA 9~10). seed 트랙과 합쳐 인용 정밀도 작업 완결. 잔존 별 task: catch 74 완전 해소 (OA/SS 쿼리 분리) · catch 78 확인 (vertex grounding 연관) · Intro tail 미세조정 (조건부).

---

## §paper-writer-2 catch 74 close (2026-07-04) — OA/SS 쿼리 길이 분리 (SS tail-only 단쿼리)

### 결론 (트랙 완료)
catch 72 부분해소로 남겨둔 SS 장쿼리 완전해소. paper_section_fetch fan-out 에서
SS 백엔드만 topic 프리픽스를 제거한 tail-only 단쿼리를 수신하도록 in-body 분기.
OA·vertex 는 full query(topic+tail) 유지. 튜플 리터럴·반환 shape 무변경.

### 진단
SS 0건 원인 = topic(9단어)+tail 합산 13~15단어 장쿼리. SS Graph API 는 장쿼리에
빈 결과. OA 는 relevance 검색이라 장쿼리 관대(9~10 유지). 백엔드별 쿼리 길이
민감도가 달라 "단일 쿼리 fan-out" 이 SS를 굶김 → 백엔드별 쿼리 분리로 해소.

### 구현 (agent/web_search.py paper_section_fetch)
- `ss_query = query.removeprefix(topic.strip()).strip() or query` (query 직후)
- fan-out 루프: `fn(ss_query if backend=="semantic_scholar" else query)`
- tail 빈 경우(범용 폴백·미등록 섹션 query==topic) → `or query` 로 full 안전 폴백
  (빈 쿼리 회귀 방지). 로그 line 은 full query 유지.

### 최종 측정 (5섹션, OA+SS raw, seed·vertex 격리, 같은 런 before/after)
| 섹션 | tail | SS_before | SS_after | noise | OA |
|---|---|---:|---:|---:|---:|
| Introduction | trademark confusion consumer perception | 7 | 5 | 0 | 10 |
| Theoretical Background | trademark confusion dilution doctrine | 1 | 6 | 0 | 9 |
| Proposed Framework | trademark confusion dilution | 4 | 4 | 0 | 9 |
| Research Design | trademark confusion survey empirical | 2 | 6 | 0 | 10 |
| Expected Contributions | trademark law consumer protection | 5 | 8 | 0 | 9 |

SS 합계 19→29. 굶주리던 섹션 회복(TheoBg 1→6·RD 2→6·EC 5→8). 노이즈 0/5,
OA full 무변경(9~10), SS_after 섹션 변별 유지(dilution군/survey군/protection군 분리).

### catch 박제
- catch 74 (MID · retrieval · 해소): SS 0건 = 장쿼리(13~15단어). 해소: SS tail-only
  단쿼리 분기. 검증 2026-07-04 5섹션 SS ≥4, 노이즈 0/5. prevention: 백엔드별
  쿼리 길이 민감도 상이 — OA 관대/SS 엄격, fan-out 시 백엔드별 쿼리 분리.

### re-entry 조건
1. OA도 축약 필요 시(현재 full 9~10로 문제없음) → OA용 쿼리도 별도 파생.
2. 다른 도메인 topic 에서 tail 이 topic 과 안 겹쳐 removeprefix 무효 시 → 분리
   로직 재확인(현재 override tail 은 topic 뒤 append 구조라 항상 유효).
3. OA 섹션 변별 저하(topic 지배로 동일 core 반복) 개선 필요 시 → 별 task
   (catch 74 밖, OA는 이번 무변경).

### commit chain (참조)

```
(이 commit) §paper-writer-2 catch 74 close — SS tail-only 분기 + dev 박제
```

**status: closed (2026-07-04)** — catch 74 완전 종결. SS tail-only 분리로 전 섹션
SS ≥4 회복 + 노이즈 0/5 + OA 무변경. catch 72(도메인 앵커)와 합쳐 상표 쿼리
파이프라인 정밀도 완결.

---

## §paper-writer-2 axis3 재설계 close (2026-07-04) — combined-mean 폐기 → academic_ratio 단일 판정

### 결론 (트랙 완료)
axis3 판정부(`scripts/§paper-writer-1/measure_paper.py` `_eval_axes`)가 두 구조적
모순으로 **영구 FAIL** 이던 것을 해소. 개별 백엔드 문턱(oa/ss/combined)을 폐기하고
학술 회수율 단일 지표 `academic_ratio` + 단일 임계 0.50 으로 재설계.

### 진단 (구 산식의 구조적 영구 FAIL — 2 모순)
- **catch 75** (combined-mean quirk): `combined = mean(oa, ss, vx)` 인데 세 비율이 같은
  분모의 분율이라 합 = 1.0 → mean 최대 **0.333** < 임계 0.50 → 어떤 분포에서도 미달.
- **모순②** (oa/ss 동시 문턱 불가): `oa ≥ 0.70 ∧ ss ≥ 0.40` 은 같은 분모라 합 1.1 > 1.0
  → 동시 성립 불가. 즉 verdict=PASS 가 산식상 봉쇄돼 있었음.

### 신 산식
```
academic_hits  = openalex + semantic_scholar + vertex_academic
academic_ratio = academic_hits / total          # total = 전체회수 (vertex_web 포함)
verdict        = PASS  if academic_ratio >= 0.50  else FAIL
```
- vertex chunk(`{uri, title, domain}`)를 **ACADEMIC_DOMAINS 도메인 필터**(`_chunk_is_academic`,
  domain 우선·uri host 폴백·www/subdomain 정규화)로 학술/비학술 가름.
- **vertex_web(비학술)은 분모에 남겨 페널티** (변별력 + 비학술 dilution 개선 유인 유지) — X안.
- 개별 `oa_pass/ss_pass/combined_pass` 폐기. 오해 네이밍 `vertex_filtered_ratio`(구: vx 와
  동일, 실제 필터 없음) 제거 → `vertex_academic_ratio`(실제 도메인 필터 반영값)로 대체.

### 공유 모듈 이관 (ACADEMIC_DOMAINS)
- 구: `scripts/§academic-1/measure_ab.py` 인라인 40개 정의 — axis3 경로 미참조였음.
- 신: `scripts/common/academic_domains.py`(§ 없는 중립 폴더) 로 **글자 무변경 이관**.
  measure_ab.py 는 `from common.academic_domains import ACADEMIC_DOMAINS` **import 전환만**
  (로직 무변경). 회귀 dry PASS: 이관 전(HEAD)/모듈/import 후 3자 대칭차집합 ∅, `is` 동일 객체.
- ⚠️ 개수 정정: 실제 **40개**(소스 주석·git·len 일치). 정찰 초기 "43" 은 오산.

### R2-b 실측 (3런, axis3 전용 하버스 · vertex 검색 5콜/런 · 본문생성 스킵)
topic = `consumer perceived trademark similarity and likelihood of confusion` (3런 동일)

| run | academic_ratio | hits/total | oa | ss | vertex_academic | vertex_web |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 0.532 | 84/158 | 60 | 24 | 0 | 74 |
| 2 | 0.549 | 89/162 | 60 | 29 | 0 | 73 |
| 3 | 0.517 | 90/174 | 60 | 29 | 1 | 84 |

- **academic_ratio mean 0.533 · min 0.517 · max 0.549 · 분산폭 0.032** → 임계 0.50 에서 3런 PASS.
- OA=60 3런 고정(seed 13 + fan-out 안정). total 변동(158~174)은 vertex 회수(73~84)+SS(24~29) 탓.
- 비용: 3런 총 vertex 15콜 ≈ 20.6k tok(gemini-2.5-flash grounding) + OA ~$0.001/콜, SS 무료 ≈ $0.06~0.09.

### vertex 학술률 정정 (핵심 발견)
- 정찰 R1 의 "vertex 학술 16%" 는 **인플루언서 토픽(measure_ab academic-en)** 값.
- **상표 토픽 vertex 학술 = 0~1.2%** (R2-b 실측, vertex_academic 0/0/1). vertex 회수는
  전부 blog/news/agency 웹(forbes/medium/intelliplans 등) → ACADEMIC_DOMAINS 미hit.
- ∴ ②안 도메인 필터의 실효는 **"vertex 학술 살림"이 아니라 "vertex 블로그 차단"**.
  vertex_web 74~84개가 분모 페널티로 academic_ratio 를 ~절반으로 누름(vertex 제거 시 OA+SS만 = 1.0).

### catch 박제
- **catch 75** (해소): combined-mean ≤0.333 quirk + 모순② → academic_ratio 단일 판정으로 제거.
- **catch 79** (LOW-MID · methodology · 신규 · **미해결, 기록만** · **2026-07-05 재정의**):
  vertex chunk 는 authors/year/doi 무필드라 `format_apa7` 통과 시 `"(n.d.). <domain>."` bare
  라인 생성(title 이 도메인 그 자체). **재정의(R1 정찰)**: `APA_REGEX` 가 `(n.d.)`·`(YYYY)` 둘 다
  매칭 + `format_apa7` 이 모든 라인에 둘 중 하나를 항상 방출 → **axis1 pass_ratio 는 구조적으로
  1.0 고정(포화 지표, 변별력 0)**. backup JSON 실측: References 169줄 중 116줄(68.6%)이 도메인
  껍데기인데도 pass_ratio 1.0. → catch 79 실효는 ~~"APA 통과율 오염"~~ **아님**. 실효 = ① 딜리버러블
  References 의 68.6% 가 도메인껍데기 오염 + ② axis1(임계 0.8)이 품질을 전혀 변별 못 하는 포화 지표.
  **axis3 트랙 밖** — axis1 재설계(author/venue/doi 실체 판정)는 **별 트랙**으로 등재. 껍데기 원천
  차단은 catch 78(vertex 스킵) 몫.
  **→ 갱신 (2026-07-05): axis3 몫(게이트 부적합)은 「axis3 기술자 재정의 (R2)」에서 기술자 강등으로
  흡수·종결. catch 79 잔여 = axis1 실체판정 별 트랙 + catch 78 껍데기 차단만.**

### re-entry 조건
1. 다른 도메인 topic 에서 vertex 학술률이 유의미(≠0)하면 → vertex_web 분모 페널티 강도 재검토.
2. 임계 0.50 이 파이프라인 개선(SS·OA 수율 ↑)으로 상시 큰 마진 PASS 되면 → 상향 재조정 검토.
3. catch 79(vertex n.d. axis1 오염) 착수 시 → axis1/References 트랙에서 별도 처리.

### 변경 파일
- `scripts/common/academic_domains.py` (신규 · ACADEMIC_DOMAINS 40 이관)
- `scripts/common/__init__.py` (신규 · 빈 패키지 마커)
- `scripts/§paper-writer-1/measure_paper.py` (axis3 재설계 + `_chunk_is_academic` + 임계 0.50 + `statistics` dead import 제거)
- `scripts/§academic-1/measure_ab.py` (ACADEMIC_DOMAINS import 전환만, 로직 무변경)

**status: closed (2026-07-04)** — axis3 재설계 종결. 구조적 영구 FAIL(catch 75 + 모순②)
제거 + 학술 회수율 단일 판정(임계 0.50) + R2-b 3런 0.517~0.549 PASS 검증. vertex 도메인
필터는 "블로그 차단" 실효로 판명. 잔존 별 task: catch 79(vertex n.d. axis1 오염, 미착수).
**⚠️ superseded by 2026-07-05 「axis3 기술자 재정의 (R2)」(아래)** — 임계 0.50 게이트 자체가
vertex-skip 후 1.000 포화로 변별력 0 판명 → 게이트 폐기·기술자 강등으로 대체.

---

## §paper-writer-2 catch 80 close (2026-07-05) — 본문 [[N]] 글로벌 승격 (섹션-로컬↔footer 오정렬 해소)

### 증상
본문 in-text 인용 `[[N]]` 은 섹션당 1-based **로컬**(writer 가 섹션별로 `enumerate` 리셋,
`agent/paper_section_writer.py:47`), footer References 는 `section_chunks_all` concat **글로벌**
1-based(`measure_paper.py:206` build + `:94` enumerate). **오프셋 보정 부재.** → 섹션 1만 offset 0
으로 우연 정합, 섹션 2~5 는 +29/+59/+117/+143 어긋나 인용이 엉뚱한 논문 지시. 실측(리포트
`paper_..._20260628_123513.md`): 섹션 2~5 인용 N 전부 ≤13 → 죄다 Introduction footer 밴드(1~29)로
오낙착. 섹션 1(6건)만 정상.

### 해결 = (b) 본문 [[N]] 글로벌 승격
`_run_one_paper` 2-지점 배선 + 헬퍼:
- `_shift_citation_markers(body, offset)`: `\[\[(\d+)\]\]` 캡처그룹 → `int(N)+offset` 재조립
  (자릿수 안전, offset==0 no-op).
- 지점①(`measure_paper.py` extend 直前): `cite_offset = len(section_chunks_all)` 스냅
  (루프 지역변수, = Σ 섹션 1..k-1 chunk 수 = 글로벌 오프셋).
- 지점②(append 直前): `body = _shift_citation_markers(body, cite_offset)`.
- (a) footer 포맷 변경(高침습) · (c) 매핑테이블(오버킬) 기각.

### 무접촉 확정
axis1(`apa_lines` 만 읽음 `measure_paper.py:230-232`, pass_ratio 1.0·n=169 불변) · axis3 · footer(
`build_apa_references`) · writer · prompts. 헬퍼는 `section_bodies` 문자열만 치환.

### 검증 (3겹 dry, 유료 0)
- **STOP-1**(삽입점): extend 直前 스냅 2-지점 확정 + 오프셋 손계산 `[0,29,59,117,143]` (backup
  per_section.chunks_count `[29,30,58,26,26]` 누적) 일치.
- **STOP-2**(regex 자릿수): `[[1]] [[12]] [[9]]`+29→`[[30]] [[41]] [[38]]` / 인접 `[[1]][[2]]`→
  `[[144]][[145]]` / 중복 둘 다 / offset=0 no-op / 마커無 0건 — 전부 PASS.
- **STOP-3**(기존 리포트 교정 검산, 재실행 아님): recon 4건 정확 일치
  `[[13]]→[[42]]`·`[[12]]→[[71]]`·`[[5]]→[[122]]`·`[[8]]→[[151]]`, 전 섹션 전량치환 누락 0,
  교정번호 전부 해당 섹션 footer 밴드 내부.

### 교차 발견 (→ catch 79 부분 해소)
catch 80 오정렬이 본문 학술인용을 **vertex 도메인껍데기**(#13 `trestlelaw.com`, #12 `gfrlaw.com`)에
오연결하고 있었음. 교정으로 실제 학술논문(Johannessen 2011, Kruger 2014 등) 연결 복원. 단 footer
껍데기 116줄 **존재 자체**는 잔존 → catch 78(vertex 스킵) 몫(catch 80 ⟂ vertex, 독립 축).

### 변경 파일
- `scripts/§paper-writer-1/measure_paper.py` (`_shift_citation_markers` 헬퍼 + `_run_one_paper` 2-지점)

### re-entry 조건
1. vertex 스킵(catch 78) 등으로 `section_chunks_all` 재구성 시 → 오프셋은 `len()` 동적이라 자동 정합
   (하드코딩 없음). 단 섹션 내 dedup 로 chunk 수 변동 시 offset 자동 반영 확인.
2. writer 가 `[[N]]` 외 인용 표기(예: `[N]`, `(N)`)를 방출하기 시작하면 → regex 확장.

**status: closed (2026-07-05)** — catch 80 종결. 섹션-로컬↔글로벌 오정렬을 본문 [[N]] 글로벌
승격으로 해소. 3겹 dry(삽입점·regex·기존리포트 교정) PASS, axis1/axis3/footer 무영향. 교차로
catch 79 인용-껍데기 오연결 부분 해소(껍데기 존재는 catch 78 잔존).

---

## §paper-writer-2 axis3 기술자 재정의 (R2, 2026-07-05) — 품질 게이트 폐기 → 파이프라인 건강 기술자 (catch 79 흡수)

### 결론 (07-04 axis3 재설계 close 를 재정의로 대체)
07-04 close 의 `academic_ratio ≥ 0.50` 단일 임계 게이트를 **폐기**. axis3 를 품질 게이트에서
**파이프라인 건강/커버리지 기술자**로 강등하고 verdict 를 3-state(PASS/WARN/FAIL)로 재배선.
outer key `axis3_backend_ratio` → **`axis3_pipeline_health`** 개명. catch 79 는 이 트랙으로 흡수
(새 catch 번호 없음).

### 게이트안 폐기 근거 (R1 + R1.5 정찰, read-only · 유료 0)
- **`academic_ratio` 는 게이트로 변별력 0**: R1.5 확정 — `backend_counts.other=0`(3런) 이라 vertex
  스킵(catch 78) 후 ratio = (oa+ss)/(oa+ss) = **정확히 1.000**(포화). 게이트가 아무것도 안 잼.
- **유일한 런간 변동이 429 노이즈**: 후보 지표 `ss/(oa+ss)` 도 3런 중 4/5 섹션 완전 평탄, 유일
  변동은 run1 Introduction SS 0↔5 — 원인은 `[semantic_scholar] 429 backoff`(axis3_run1.log:9).
  즉 품질 신호 아닌 rate-limit 아티팩트에 임계를 거는 꼴 = **catch 79/과거 combined-mean 함정 재현**.
- ∴ 품질 게이트로서 axis3 회생 불가 → 목적을 게이트→기술자로 하향. 학술 품질 실체 판정은
  **axis1 재설계(별 트랙)** 로 이관.

### 신 정의 — 3-state 파이프라인 건강 기술자
섹션별 backend 카운트(`per_section[*].backend_counts`, 신규 P1 캡처)에서 파생, **분할 severity**:
```
sections_with_zero_oa (OA=0) OR sections_with_other (other>0)  → FAIL
elif sections_with_zero_ss (SS=0)                              → WARN
else                                                           → PASS
```
- **SS=0 → WARN (게이트 아님)**: SS 0-death 는 429 백오프 소진 등 flaky 원인(R1: run1 Intro SS=0
  은 429, 단 run1 EC 는 429 맞고도 재시도 회복 SS=8 → n=1 단일사례). 자동 FAIL 금지 = R1 원칙.
- **OA=0 → FAIL**: OA 는 완전 결정론(3런 섹션별 10/12/16/13/9 불변) → 0 은 불변식 위반 = 파이프라인 완파.
- **other>0 → FAIL**: 정상선 3런 전부 0 → >0 은 미상 `_backend` 태그 누출 = 코드/설정 회귀 tripwire.
- `academic_ratio`·`academic_hits` 는 **informational 로만 유지**(판정 미참여). 구 `ACADEMIC_RATIO_THRESHOLD`
  상수 + `oa_ratio/ss_ratio/vertex_ratio/vertex_academic_ratio` 진단필드 폐기.

### 임계 정정 (3단 정합)
- 인계메모 추정치 **"임계 0.60" 은 오기** — §academic-4 트랙(catch 51/61 `academic_source_ratio` 0.60)과
  혼동한 값으로 paper-writer axis3 와 무관.
- 07-04 close 실제 커밋값 = **0.50**(`ACADEMIC_RATIO_THRESHOLD=0.50`, dcbb7f12 measure_paper.py:158).
- **현재 = 임계 자체 폐기**(게이트 삭제) → 0.50/0.60 논의 모두 무의미해짐.

### 배선 (measure_paper.py, +67/−39 · 유료 0)
- `_count_backends(chunks)` 헬퍼 신설 — aggregate(`_eval_axes`)·per-section(`_run_one_paper`) **분류
  단일 소스**(구 인라인 카운트 루프 중복 제거). vertex 는 `_chunk_is_academic` 로 학술/웹 분해.
- **P1**: `per_section[section]` 빌드에 `"backend_counts": _count_backends(chunks)` — catch 80 offset
  스냅/extend/shift 라인 무접촉, chunks read-only.
- **P2/P3**: `_eval_axes` axis3 → 섹션별 파생(`sections_with_zero_ss/oa/other`, `per_section_backends`)
  + 3-state verdict + `academic_ratio` informational.
- 개명 outer key `axis3_pipeline_health`(잔존 `axis3_backend_ratio` 참조 0 확인).
- 종합부 무배선: 크로스-axis verdict 종합기 부재(`main` :382-383 `r.update` 병합만) → WARN 3-state 안전.

### dry 검증 (오프라인 재생, measure_paper 풀런 없음 · 유료 0)
- **DV1**(저장 axis3_run{1,2,3}.json 재생): run1 → **WARN**(Intro SS=0 가시화) · run2/3 → **PASS**.
  aggregate backend_counts·academic_ratio 가 R1.5 실측(60/24·60/29·60/29+1, 0.532/0.549/0.517) 정확 재현
  = 헬퍼 충실도 교차검증.
- **DV2**(synthetic 5경로): 정상→PASS / SS=0→WARN / OA=0→FAIL / other=1→FAIL / SS=0∧OA=0→FAIL
  (FAIL>WARN 우선) — 전부 기대 일치.

### catch 79 흡수
- **catch 79 = 이 트랙으로 흡수**(별 catch 번호 없음). R1 재정의(07-04 close 섹션 참조)의 실효
  ①(References 68.6% 도메인껍데기)·②(axis1 포화) 중 **axis3 게이트 부적합분은 본 기술자 강등으로 해소**.
- 남은 **axis1 포화(author/venue/doi 실체 판정)는 별 트랙**(catch 79 잔여 = axis1 재설계), 껍데기 원천
  차단은 **catch 78(vertex 스킵)** 몫. → catch 79 의 axis3 몫 종결, axis1 몫 이관.

### 변경 파일
- `scripts/§paper-writer-1/measure_paper.py` (`_count_backends` 헬퍼 + P1 per_section backend_counts
  + P2/P3 3-state 기술자 + `axis3_pipeline_health` 개명 + `ACADEMIC_RATIO_THRESHOLD` 폐기)

### re-entry 조건
1. SS 429 견고화(retry/백오프 강화)로 SS 0-death 제거 시 → WARN 신호 발생 빈도 재평가.
2. catch 78 vertex 스킵 첫 유료 런 후 → `per_section_backends` vertex_* = 0 반영 + 기술자 verdict
   무영향(1.000 포화가 게이트 아닌 informational) 실측 검산.
3. axis1 재설계(catch 79 잔여) 착수 시 → 학술 실체 판정 축을 axis1 로, axis3 는 건강 기술자로 분리 유지.

**status: closed (2026-07-05)** — axis3 기술자 재정의 종결. 07-04 게이트(임계 0.50) 폐기 → 3-state
파이프라인 건강 기술자 강등 + `axis3_pipeline_health` 개명. R1/R1.5 정찰로 게이트 변별력 0(vertex-skip
후 1.000 포화 · 유일변동 429 노이즈) 확정, DV1/DV2 오프라인 검증 PASS. catch 79 axis3 몫 흡수·종결,
axis1 실체판정 몫은 별 트랙 이관. 잔존: catch 78(vertex 스킵 유료 배선), axis1 재설계.

---

## §paper-writer-2 catch 78 close (2026-07-05) — vertex skip 플래그를 paper fan-out에 배선 (References 껍데기 −92, 학술 100%)

### 증상 (버그)
- `paper_section_fetch`(web_search.py) fan-out 루프가 vertex_web_search 를 **무조건 호출** — `SKIP_VERTEX_SEARCH`
  를 무시. 레거시 web_search 경로(:754/:832)만 플래그 존중, paper 경로는 미존중.
- 결과: 영어 상표 토픽에서 vertex 가 law-firm 블로그 등 **비학술 껍데기**를 References 에 다량 주입
  (author/year 없는 맨 도메인 `(n.d.). arpgweb.com` 류). 유료 Gemini 콜 + 참고문헌 신뢰도 훼손.

### 배선 (3파일 단일 커밋)
- **A. `agent/web_search.py:1982`** — fan-out 리스트를 base 2튜플(oa·ss)로 빌드 →
  `_cfg_bool("SKIP_VERTEX_SEARCH", False)` 이 False 일 때만 vertex 튜플 append. **mid-loop continue 아님**
  (dead 튜플·skip 로직 분산 방지, R1 판정). `_cfg_bool` 재사용 = **신 파서 0**(catch 71 상류 CFG 파싱 차단됨).
  skip 시 레거시 :833 스타일 로그 1줄.
- **B. `topics/academic-trademark-similarity-consumer.env:21`** — `SKIP_VERTEX_SEARCH=false → true`.
  토픽 프리셋(override=True)이 최종 승자라 flip 기계적 관철(R1.5 (a) 실증).
- **C. `scripts/§paper-writer-1/measure_paper.py:121`** — 드라이버 `SKIP_VERTEX_SEARCH="0" → "1"` 정합.
  이 키는 config 최초 빌드가 드라이버 override 後(lazy import)라 **토픽 프리셋이 결정 = 드라이버 값 no-op**;
  혼동 방지 위해 토픽 값(skip)과 정합. :108 stale 주석 갱신.

### 실측 (첫 유료 런, 2026-07-05T06:59Z · exit 0)
- References **169 → 77** (−92 = vertex law-firm 껍데기 제거). `(n.d.)+맨도메인` 껍데기 잔존 **0**.
- POST 77 = OA 60 + SS 17 = **100% 학술 backend** (backend_counts total 77 완전 일치).
- axis3 검산 3층: **L1** vertex_web=0 전 5섹션 / **L2** `sections_with_zero_oa=[]` (OA 10/12/16/13/9 결정론
  baseline 일치 = OA 파이프라인 무개입) / **L3** verdict=**WARN** (SS 429 flaky: Proposed Framework·
  Expected Contributions SS=0, R1 원칙상 WARN-only 게이트 아님). 3층 전부 PASS.

### ⚠️ known divergence (차기 통합 catch 후보)
- **paper 경로 = flat flag**(`SKIP_VERTEX_SEARCH`), **레거시 academic 경로 = catch-43 language routing**
  (web_search.py:750-753, `_q_lang=="ko"` 시 skip) — 두 경로 vertex 게이팅 **상이**. 현재 무해
  (참고문헌은 paper 경로 전용 = paper_section_fetch, measure_paper.py:217 단독; R1.5 확인2로 레거시
  미개입 확정). 통합 시 catch 후보.

### catch 79 잔여 (별 트랙, 78 무관)
- axis1 APA_REGEX(measure_paper.py:148-150) `(n.d.)`/`(YYYY)` 무조건 매칭 → pass_ratio 1.0 포화.
  78 로 vertex 껍데기는 원천 차단되나 **(n.d.) 매칭 포화 자체는 axis1 몫으로 잔존**. author/venue/doi
  실체 판정 재설계는 별 트랙(vertex 무관, 독립 착수).

### 변경 파일
- `agent/web_search.py` (A) / `topics/academic-trademark-similarity-consumer.env` (B)
- `scripts/§paper-writer-1/measure_paper.py` (C) / `README-dev-§14.md` (박제)

### re-entry 조건
1. 한글/틈새 토픽 default 확정 시 → vertex 16% 학술률(mdpi/researchgate)이 진짜 문헌인지 껍데기인지
   실측 후 토픽별 flag default 결정 (상표=off 는 확정, 한글 토픽 숙제 잔존).
2. paper↔레거시 vertex 게이팅 통합 필요 시 → known divergence 항목 참조.
3. axis1 재설계(catch 79 잔여) 착수 시 → (n.d.) 포화 해소.

**status: closed (2026-07-05)** — vertex skip 플래그 paper fan-out 배선 종결. References 169→77
(껍데기 −92, 학술 100%), axis3 3층 검산 전부 PASS(vertex_web=0 / OA baseline 유지 / WARN). 커밋됨.
잔존: 한글 토픽 vertex 학술률 실측, paper↔레거시 게이팅 통합, axis1 재설계.

-------

## §paper-writer-2 catch 79 close (2026-07-06) — axis1 재설계: regex 포화 → venue OR doi 존재 3등급 실체 판정

### 한 줄
axis1 이 인용을 `(YYYY)`/`(n.d.)` 정규식 통과로 재던 포화 게이트(pass_ratio 1.000 고정, 변별력 0)를
폐기하고, chunk 최상위 필드(venue/doi) **존재**로 인용 실체를 3등급 판정하는 결정론·무료 detector 로 교체.
catch 78 이 (n.d.) 껍데기를 원천 차단한 뒤라 axis1 이 재는 대상이 순수 학술 인용뿐 → 재설계 효과 깨끗이 측정.

### 재설계 내용
- **A(조립 문자열 regex 되파싱) 폐기 → B(chunk 최상위 필드 직독) 채택**. `format_apa7` 이 year 를 항상
  `(YYYY)`|`(n.d.)` 로 뱉어 구 regex 는 무조건 매칭 = 포화. 재료(authors/year/venue/doi)가 chunk 원본
  필드로 이미 존재(OA `openalex.py:160-`, SS `semantic_scholar.py:222-`), `build_apa_references` 도 이미
  최상위 직독 중 → B 무손실.
- **detector `axis1_grade(chunk)`** (measure_paper.py): 완전체(venue AND doi) / 부분체(venue XOR doi) /
  결손(둘 다 없음). **결손만 fail**. 빈 판정 `_blank` = None·''·공백 (SS 는 venue='' 반환 = R2.5 지뢰1).
- ⭐ **doi 필수 아님**: 법학 리포지토리 정식인용(Beebe/Tushnet/Senftleben/Heymann)은 doi 없이도 학술 →
  venue OR doi. doi 필수 걸면 이번 런 부분체 34개(venue있음·doi없음) 전부 오탈락.
- **threshold 0.90**, **3-state verdict**: FAIL(ratio<0.90) / WARN(ratio≥0.90 이나 결손>0) / PASS(결손 0).
  **gate 유지**(axis3 처럼 informational 강등 아님 — R1 확정). 파생 필드: grade_dist·n_missing·missing_by_section.

### 실측 (remeasure 유료 런 2026-07-06T09:46Z, exit 0, vertex off)
- axis1 = **WARN**, pass_ratio **0.944**(=84/89), 완전체 43 / 부분체 41 / 결손 5. old 1.000 포화 대비 변별 복원.
- 오프라인 R3 설계(chunks_raw_dump.json 89개)와 **라이브 완전 일치**(등급 분포·ratio·verdict·섹션 결손 동일).
- L2: References 89(OA 60 + SS 29) = R2.5 스케일 유지, 참고문헌 무붕괴. axis2/axis3 무변경(axis3 PASS).

### known divergence (무해, 별 트랙 후보)
- **결손 5 전부 OA·정식 논문의 OA 메타 미충전**(껍데기 아님): Janis&Dinwoodie "Confusion Over Use"(3섹션
  중복)·윤선희(2005 한글)·Beebe&Germano(2019). venue/doi 둘 다 OA 가 못 채운 케이스 = axis1 "존재만"
  판정상 정당한 fail 이나 실체는 학술.
- **R2 계측 상주**: `_run_one_paper` 가 각 chunk 에 `_section` 태그(_backend 대칭 additive) + `main` 이
  `chunks_raw_dump.json` 별도 덤프(c_paper_measurement.json 무오염). detector 재튜닝 재료로 상주.

### 변경 파일 (2파일 단일 커밋)
- `scripts/§paper-writer-1/measure_paper.py` (detector 이식 + R2 계측 + 채점부 배선 + 구 regex 정정 박제)
- `README-dev-§14.md` (본 박제)

### 별 트랙 후보 (axis1 밖, 미착수)
1. **OA 메타 충전 개선**: 결손 5 전부 OA venue/doi 미충전. OA API landing_page/host_venue 재조회로 보강 여지.
2. **venue 부정합/predatory 판별**: SS Anita(2024) 제목-저널 불일치(상표법 논문인데 venue='African J of
   Biological Sci') 류. 존재는 하나 부정합 = 품질 축. axis1(존재·결정론·무료) 밖 = embedding/LLM 별 트랙.

### re-entry 조건
1. OA 메타 충전 개선 착수 시 → 결손 5(전부 OA)를 landing_page_url·host_venue 보강으로 부분체 승격 검토.
2. venue 부정합 판별 필요 시 → 별 트랙(품질 축, axis1 결정론 계약 밖).
3. threshold 0.90 재조정 필요 시 → 결손율 실분포(현 5.6%) 기준. 부분체는 구조상 pass(정상 법학인용 오탈락 0).

**status: closed (2026-07-06)** — axis1 regex 포화 → venue OR doi 3등급 실체 판정 재설계 종결.
remeasure WARN(0.944, 결손 5) = 오프라인 설계 라이브 재현, 포화 회귀 없음. 커밋됨.
잔존 별 트랙: OA 메타 충전 개선, venue 부정합/predatory 판별.


## §paper-writer-2 catch 81 close (2026-07-07) — 한 런 내부 numbering feedback loop 절단 (본문↔참조 오매칭)

catch 80 글로벌 shift 산물이 `previous_sections`로 다음 섹션 writer 프롬프트를 오염 → writer가
글로벌 `[[N]]`을 복사→재shift 하는 **한 런 내부 feedback loop**(R1 규명). 상세 박제:
`scripts/output/§paper-writer-1/catch81_R2R3_close_20260707.md` (+ R1 `catch81_numbering_feedback_loop_report_20260707.md`).

### 배선 (leak 채널 절단, 2파일)
- `agent/paper_section_writer.py:58` — `prev_text`에서 `\[\[\d+\]\]` strip (프롬프트로 나가는 **로컬 복사본만**).
  `section_bodies`(=previous_sections leak + 최종 paper_body/반환 동일 리스트 공유)는 무손상 → footer 정합 불변.
  ⚠️ `:58` fallback `or "(없음 — 첫 section)"` 보존 필수(task 원본 누락분). `_CITE_MARKER_RE` 공유는 순환(script→lib)이라 inline만 가능.
- `prompts.py:439` — [[N]] 로컬-스코프 명확화 1줄(defense-in-depth). `:450`("표기 일관성"=용어/변수 ≠[[N]])은 불변.

### R3 유료 통제런 (references 89 byte-identical = 단일변수 통제) — 4종 PASS
| 판정 | baseline 004833 | R3 020918 |
|---|---|---|
| out-of-range | 9 occ / 8 distinct | **0 / 0** |
| 2-hop 사슬 | 1 (`[[112]]` 26→59→112) | **0** |
| footer 정합 | max 112 > 89 | max 82 ≤ 89 |
| 측정축 | axis1 0.944 WARN / axis3 PASS 1.0 | **identical** |

전 섹션 인용 유지·전량 in-range(가짜-PASS 아님). 인과(R1 §2 writer 실제 복사) 확정.
관찰: 본문 마커 52→21(생성변동+복사마커 소거, 판정 무위반) / strip 후 구두점 앞 공백 잔재(leak 입력만·무해·미수정).

### 변경 파일 (종결 커밋) — measurement JSON·output 논문 제외(관행)
- `agent/paper_section_writer.py`, `prompts.py`, `catch81_R2R3_close_20260707.md`, `README-dev-§14.md`(본 엔트리).

**status: closed (2026-07-07)** — leak 채널 strip + 프롬프트 명확화로 절단, 유료 통제런 4종 PASS로 인과 확정.
re-entry: 마커 수 변동이 인용밀도에 유의미하면 재검토 / 타 토픽·섹션수에서 재출현 시 leak 잔여경로 재진단 / faithfulness는 43 aligned 중 재선정(R1 §4).
