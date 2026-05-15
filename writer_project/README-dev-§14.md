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
