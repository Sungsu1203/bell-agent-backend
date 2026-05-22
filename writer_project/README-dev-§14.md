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
