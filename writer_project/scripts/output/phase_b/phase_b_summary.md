# §14-2 Phase B 풀파이프라인 측정 close 박제

close 일자: 2026-05-15

## 1. 메타 박제

| 항목 | 값 |
|---|---|
| 측정 일자 | 2026-05-15 |
| 측정 표준 | §13-7 (max_retries=0, warmup 2, per-run-timeout 900s, inter-run-sleep 60s, PYTHONIOENCODING=utf-8) |
| 환경 | LLM_PROVIDER=vertexai, LLM_MODEL=gemini-2.5-flash, `.venv_vertex` |
| GCP | project=`gemini-rag-search-final`, region=`us-central1` |
| 호출 단위 | `graph.invoke` multi-turn (1 turn = 1 섹션, max_turns=21, recursion_limit=200) |
| 토픽 | venfobel-vitamin (§12-12 정책: `local_first` + 0.33, RAG_TOP_K=10) |
| 비교 대상 | **5078a2d** (patch 후, §14-2 Step 1b + Phase B 인프라) vs **ba44637** (patch 전, 1135ac1 + driver cherry-pick 임시 commit) |
| Outline | `outlines/venfobel-vitamin/outline_report.md` 7개 섹션 |
| Reset 정책 | ns_web 만 (ns_local PDF 349 chunks 보존), 매 run 1회 (subprocess 분리) |
| 측정 자산 | `phase_b_measure_20260515_085834.json` (5078a2d), `phase_b_measure_20260515_130839.json` (ba44637), `phase_b_summary_20260515_153645.json` (통합) |

## 2. 측정 결과 비교 표 (핵심)

| 지표 | 5078a2d (patch 후) | ba44637 (patch 전) |
|---|---:|---:|
| n_ok / n_total (runs) | **3 / 3** | **2 / 3** |
| elapsed mean | 311.41s | 269.76s |
| elapsed stdev | 21.63s | 27.59s |
| elapsed cv | 6.9% | 10.2% |
| elapsed range | [286.45, 324.86] | [250.25, 289.27] |
| section_count mean / cv | 7.0 / 0% | 7.0 / 0% |
| turn_count mean / cv | 7.0 / 0% | 7.0 / 0% |
| **refs_docs (sidecar) mean** | **17.33** | **16.5** |
| refs_docs stdev / cv | 1.53 / 8.8% | 0.71 / 4.3% |
| refs_docs range | [16, 19] | [16, 17] |
| **state_references count** | **26** (all 3 runs) | **26** (정상 2 runs) / **24** (abort run, 6 sections 분) |
| **state_dist** | `{'local': 26}` × 3 | `{'local': 26}` × 2 (정상), `{'local': 24}` × 1 (abort) |
| sidecar fn local / web | 16~19 / **0** | 16~17 / **0** |
| chroma_clear 결과 | `before=1 → after=0` × 3 (`cleared=True`, fb=False) | `before=1 → after=0` × 3 (동일) |
| chroma_initial_count | 0 × 3 (cross-check 통과) | 0 × 3 |
| abort (warmup 포함, 총 5 runs) | **0 / 5** | **2 / 5** (warmup_1 + run_2, 모두 turn 7 vertex 429) |

### 부속 raw (per-run)

5078a2d:
- run1: driver=286.45s, inner=280.42s, refs_sidecar=16, refs_state=26
- run2: driver=324.86s, inner=315.02s, refs_sidecar=19, refs_state=26
- run3: driver=322.91s, inner=307.38s, refs_sidecar=17, refs_state=26

ba44637:
- run1: driver=289.27s, inner=282.69s, refs_sidecar=16, refs_state=26
- run2: driver=336.50s, inner=331.91s, refs_sidecar=10, refs_state=24, **abort turn 7**
- run3: driver=250.25s, inner=242.50s, refs_sidecar=17, refs_state=26

## 3. 핵심 발견

### Finding 1 — §14-2 Step 1b patch in-memory 효과 = 0

- 정상 종료 5 runs (5078a2d × 3 + ba44637 × 2) 모두 `state_dist = {'local': 26}` 동일
- `vertex_grounding = 0`, `web = 0`, `local = 100%`
- patch 전후 일관 재현 (state_dist cv 0%, refs_state count cv 0%)
- sidecar refs 도 동일 — fn_web = 0 (5/5 runs)

→ §14-2 Step 1b patch (commit `d88a8b9`, `agent/web_search.py:766` 의 vertex grounding 결과 통합 정상화) 의 in-memory 효과는 **본 측정 시나리오에서 0**.

### Finding 2 — 가설 (a') 확정: graph 가 write 명령 시 web_search 노드 미호출

**근거**:
- supervisor 로그 (per turn): `research_round=0 → 1 promote (basis: rag_on_disk)`, `has_refs=False/True`, `has_plan=False`, `rag_on_disk=True`, `docs_in_state=0/7/14/...`, `ns_base=0, ns_web=0, ns_local=349`
- 매 turn `"write: <섹션명>"` 명시 명령 → supervisor 가 writer 락 잡고 vector_search → section_writer 흐름. web_search 노드 라우팅 분기 미진입.
- ns_web persist dir 종료 시 `chroma.sqlite3` (188 KB, 빈 collection metadata) 1개. chunks indexing 0건.
- `state.references.docs` source 100% `file://` PDF (local).

**해석**: §14-2 Step 1b patch (`web_results_to_documents` 화이트리스트 통과 정상화) 는 web_search 노드가 실행될 때만 의미. **본 측정의 writer-lock 명시 명령 시나리오에서는 dead code path**.

### Finding 3 — abort 원인 vertex API 429 quota (코드 결함 아님)

- ba44637 측정에서 abort 2회: `warmup_ba44637_1` (turn 7) + `ba44637_run2` (turn 7)
- 둘 다 마지막 섹션 (`"실행 로드맵 및 핵심 성과 지표(KPI)"`) 시작 시점 `ResourceExhausted: 429`
- 약 5~6분 누적 vertex 호출 후 quota window hit (Vertex AI 의 RPM/TPM 한도)
- 5078a2d 에서 abort 0인 것은 quota window 가 다른 시점, 또는 누적 cadence 우연 차이
- **코드 결함 아님, 환경 제약**. patch 안정성 차이 측정 무효 — 같은 quota 환경에서 발현 시점 다를 뿐.

## 4. Sidecar vs In-memory 차이

| 단위 | 5078a2d 정상 | ba44637 정상 | 차이 해석 |
|---|---:|---:|---|
| `state.references.docs` (in-memory) | 26 × 3 | 26 × 2 | 매 turn 누적 retrieve, cv 0% |
| sidecar `*.refs.json` (citation 된 docs) | 16~19 | 16~17 | footnote 인용 단계 통과한 subset |
| 차이 | 7~10 | 9~10 | 정상 동작 — 모든 retrieved docs 가 LLM 본문 citation 까지 도달하지 않음 (AUTO_FOOTNOTE_VERIFY 의 marker 매칭 통과 docs 만 sidecar 진입) |

## 5. 측정 인프라 박제 가치

§14-3 이후 multi-turn 측정 트랙에서 재활용 가능 — 인프라 유지:

| 자산 | 역할 |
|---|---|
| `scripts/measure_vertex_phase_b.py` | multi-turn driver (A-1 패턴, max_turns 21, completed_sections 종료 판정, --mode dry/measure/summary, 2-subprocess orchestration) |
| `scripts/_phase_b_run_inner.py` | measurement subprocess — graph.invoke multi-turn + state.references.docs 직렬화 + per-turn refs_docs_count 박제 |
| `scripts/_phase_b_clear_ns.py` | ns_web reset 전용 subprocess (Windows file lock 회피, LangChain 미 import) |
| `scripts/output/phase_b_reset_policy.md` | Chroma reset 정책 박제 (filesystem-based, ns_web 만, run 단위) |

## 6. §13-7 측정 표준 update 박제

### Pitfall (NEW) — Vertex API 429 quota 한계 (multi-turn 측정)

**발현 패턴**:
- 5~6분 누적 vertex 호출 후 마지막 turn 시작 시 429
- ba44637 측정: 5 runs 중 2회 (warmup_1, run_2) 모두 turn 7 진입 시점
- 5078a2d 측정: 동일 timeout/sleep 설정에서 abort 0회 — quota window 의 우연성

**대응 후보** (§14-3 후속 검토):
- (a) inter-section-sleep 명시 (현재 sleep 은 inter-run 만)
- (b) vertex API call rate throttle (호출 간격 명시)
- (c) 측정 단위 축소 (5 sections 등 — 단 outline 변경 부담)

### Cosmetic — main driver env diag 정합성

- v1 dry-run 시 main driver process 의 `[env diag]` 가 모두 `<unset>` 표시 (subprocess 만 .env.vertex 로드)
- v2 부터 main driver 도 .env.vertex 명시 로드 → 진단 정합성 확보

## 7. §14-3 후보 우선순위 영향

기존 §14-3 후보:
- (a) `web_results_to_documents` 화이트리스트 확장
- (b) redirect URL resolve 견고화
- (c) footnote label 정밀화
- (d) `domain_bonus` 통합
- (e) ChatVertexAI deprecated 마이그레이션

### Phase B close 영향

- **(a)~(d) 모두 web_search 노드 활성 시나리오 전제** — patch 가 dead path 라 효과 측정 어려움. (a)~(d) 진입 전 supervisor 라우팅 트랙 묶음 필수.
- **(e) 추가 박제** — `google-cloud-storage<3.0.0` deprecated FutureWarning 도 stderr 에서 관측. ChatVertexAI/VertexAIEmbeddings 와 함께 별도 트랙으로 진행 가능.

### §14-3 진입 시 우선 트랙 후보 (NEW)

- **web_search 노드 호출 시나리오 발굴** — supervisor 라우팅 / 입력 패턴 / `"research:"` 명령 등
- 이게 (a)~(d) 의 효과 측정 전제 조건. 현재 `"write: <섹션명>"` 명령 시나리오에서는 web_search 미진입.

## 8. 측정 자산 commit 박제

| 항목 | 위치 |
|---|---|
| Phase B 인프라 commit | `5078a2d` (§14-2 Phase B: measurement driver + 2-subprocess clear pattern) |
| 측정 결과 JSON | `scripts/output/phase_b/*.json` (.gitignore 보호, untracked 유지) |
| 측정 console log | `scripts/output/phase_b/_inner/*.console.log` (gitignore) |
| ba44637 임시 commit | detached HEAD, GC 대상 (reflog 만 보유) |

## 9. Patch 코드 처리

§14-2 Step 1b patch (`d88a8b9`, `agent/web_search.py:766` 화이트리스트 통과) 는 dead path 에 있어도 **코드 정합성 차원에서 유지**. revert 불요. 추후 web_search 노드 활성화 시 다시 필요 (vertex grounding 결과 통합 정상화 자체는 정합 변경).

## §14-2 Phase B post-close addendum (2026-05-15, 사용자 기억 확인)

### 측정 시나리오 명시화

"write: <섹션명>" 명령의 의도된 동작 (사용자 기억 확인):
- vector_search → section_writer **빠른 경로** (의도된 설계)
- web_search 노드 건너뜀
- 이미 임베딩된 자료 전제 (ns_web=0 + ns_local=349 상태)
- venfobel-vitamin 토픽은 ns_web 비어있어 web/vertex footnote 안 붙는 게 정상

### §14-2 Step 1b patch 의 의미 재해석

- patch 가 dead path 가 **아님**
- Phase B 측정 시나리오가 patch 검증에 **부적합**
- Phase B 는 "빠른 경로" 시나리오만 커버, web_search 활성 시나리오 미커버

### 진짜 검증 조건 (사용자 기억 단서)

"최신 자료로 RAG 업데이트" 류 명령 (정확한 트리거 미확인) 시:
- ChromaDB 전체 재인덱싱
- web_search 부터 다시 실행되는 정상 경로
- ns_web 채워지는 흐름
- 이 시나리오에서 §14-2 Step 1b patch 효과 본 검증 가능

### §14-3 진입 단계 (재정의)

1. "RAG 업데이트" 명령 핸들러 코드 리뷰
   - `agent/supervisor.py`: task 라우팅 조건
   - `agent/rag_expression.py`: `extract_*_title` 패턴 (`extract_write_title` 형식)
   - `agent/web_search.py`: 진입 조건
   - `ingest_vector.py` / `tools/web_rag/`: 재인덱싱 entry
2. supervisor 라우팅 조건 식별 (`write:` vs `research:` vs `update:` 등)
3. web_search 진입 시나리오 driver 작성 (Phase B 인프라 재활용 가능)
4. 그 시나리오에서 N=3 재측정 → §14-2 Step 1b patch 효과 본 검증

### Phase B 인프라 활용 가능 자산

- `scripts/measure_vertex_phase_b.py`: multi-turn A-1 driver (명령어만 변경 시 재활용)
- `scripts/_phase_b_clear_ns.py`: 2-subprocess clear 패턴
- `scripts/_phase_b_run_inner.py`: measurement subprocess
- §13-7 측정 표준 적용 검증 완료
- vertex 429 quota pitfall 박제 (multi-turn 5~6분 누적 호출 한계)
