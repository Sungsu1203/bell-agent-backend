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
| catch 45 | A1 fail 3건 재진입 (`journalofadvertising.org` / `earticle.net` / `kosac.or.kr`) — 특히 earticle.net SSL defer | Phase 학술-3 (KCI / RISS backend 직접 API 도입) 진입 시 재평가 |
| catch 46 | academic prompt tone 분기 (writer prompt academic hint) | Phase 학술-4 진입 조건 — §academic-1 본 cycle 에서는 defer (minimal stub 또는 비도입) |
| catch 47 | mixed-lang routing 측정 별도 sub-cycle | §academic-1 본 cycle 후속 — mixed 분류 정확도 + vertex+naver 병렬 효과 정량 측정 |
| catch 48 | (lesson) Step B budget 산정 시 신규 함수 본체 line count 누락 — 향후 design step 박제 작성 시 budget 산정 check-list 보강 | §academic-1 Step C-1 에서 +13 예산 vs 실제 +24 diff (185%) STOP 발화 사례. 향후 cycle 의 Step B design 박제 시 budget = (config 변경) + (in-place hook insert) + **(신규 함수 정의 본체 line)** + (substitution net) 산식 정착 필요 |
| catch 49 | (lesson) 측정 driver SDK-level timeout 강제 부재 + probe 환경 일치 강제 lesson | §academic-1 C-3 첫 측정 시도 fail 사례 (header log 1회 후 사용자 kill). 향후 측정 driver = (A) SDK-level force-orphan timeout (daemon thread + join), (B) provider lock (`LLM_PROVIDER` 명시 + 글로벌 .env default 차단), (C) stdout flush stage marker, (D) probe (`sys.executable` venv 일치 + provider 일치) 강제 — 4 항목 default 패턴 정착 |
| catch 50 | gatekeep `ALLOWED_DOMAINS_EXTRA` cache invalidation 결함 — 토픽 전환 시 EXTRA 가 `_normalized_allowed_domains` lru_cache 에 반영 안 됨 | §academic-1 C-3 measurement metric 2 root cause B 박제. academic-en (gatekeep n=108) → academic-ko (n=79, EXTRA 29 누락) drop 사례. `reload_config_inplace` 가 `refresh_gatekeep_cache()` 호출함에도 토픽 전환 사이 cache 무효화 누락 — sub-cycle 진입 필요 (academic 모드 multi-topic 운영의 source ratio 직접 영향) |

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

`81894f3` C-1 (catch 43 hook + MODE/EXPECTED_LANG config + academic env templates) + `c927a70`/`b2c7c86` C-2 measurement driver (+ hotfix) + C-3 측정 (3 topics × 5 runs · vertex). 본 미션 (catch 43 routing 메커니즘 + business invariant) 5 metric 중 4 PASS, metric 2 REVIEW (root cause A/B 박제: driver redirect monkey-patch + gatekeep cache stale → catch 50 sub-cycle 후보). 박제: `scripts/output/§academic-1/step_{a,b}_*.md` + `step_c_impl_measurement.md`. **본 cycle 본 미션 달성, 부수 미션 (academic source ratio 정량) 미달성 — catch 50 신규 등록 후 cycle close (사용자 컨펌 영역).**
