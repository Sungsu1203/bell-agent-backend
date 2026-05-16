# §14-3 (NEW)-B 트랙 1 P-2 result: 분기 (가) 확정 박제

본 문서는 §14-3 (NEW)-B 트랙 1 P-2 (script 변경 없이 환경 변수 명시 설정 방식) 의 결과 박제.
가설 A (vertex_web_search 호출 분기 차단) + base policy + per-topic override 패턴 검증 완료.

- 작업 일시: 2026-05-16
- 진입 조건: §14-3 (NEW)-B 옵션 3 분기 (가) 확정 (commit ca148bc)
- **결론: 분기 (가) ★★★★★ 확정 — vertex_grounding > 0 도달 (0 → 1)**
- 트랙 1 본 미션 완료, Phase 3 본 측정 진입 valid 조건 확보

---

## § 1. 측정 메타 + raw 결과

### 1.1 측정 환경

- driver: `scripts/_step3_dry_run_rag_update.py` (single-shot graph.invoke)
- provider: vertexai (LLM_MODEL=gemini-2.5-flash, GCP_REGION=us-central1)
- recursion_limit: 100
- env 명시: `$env:PYTHONIOENCODING=utf-8`, `$env:LOCAL_RAG_ALLOW_EMPTY=1`, `$env:TOPIC_SLUG=ai-generated-creative-ad-platforms` ★

### 1.2 env 파일 박제 (gitignore 정책 정합, full content 인라인)

**박제 정책**:
- 위치: `topics/ai-generated-creative-ad-platforms.env` (792 bytes, 14 lines)
- gitignore 정책: `.gitignore` L76 `topics/*.env` 의 의도된 local-only 정책 대상 (사용자 운영 자산 보호)
- 본 박제 자산은 reproduction 완전성을 위한 **인라인 박제**
- 향후 측정자 reproduction 시 아래 14 lines 그대로 작성

**박제 항목 (7)**:
- 주석 4줄 (origin / 검증용 / SKIP=0 의도)
- TOPIC_TITLE / TOPIC_SLUG / TOPIC_KEYWORDS
- `SKIP_VERTEX_SEARCH=0` (글로벌 .env =1 override)
- BLOCKAGI_OBJECTIVE_1 (planner_qs valid 조건 placeholder)

**full content** (UTF-8, 14 lines):

```env
# §14-3 (NEW)-B 트랙 1 P-2 검증용 토픽
# 운영 토픽 아님 — Step 1b patch 본 검증 valid 조건 확보 목적
# SKIP_VERTEX_SEARCH=0 override 로 글로벌 .env 의 =1 base policy 회피
# origin: scripts/output/§14-3/(NEW)-B_option3_code_review.md

TOPIC_TITLE=AI 생성 광고 크리에이티브 플랫폼 동향
TOPIC_SLUG=ai-generated-creative-ad-platforms
TOPIC_KEYWORDS=AI,generative,creative,ad,platform

# (NEW)-B 트랙 1 P-2: 글로벌 .env 의 SKIP_VERTEX_SEARCH=1 override
SKIP_VERTEX_SEARCH=0

# planner_qs 생성 valid 조건 확보 placeholder (OBJECTIVE 의존 여부 미확정, 추정 회피 박제)
BLOCKAGI_OBJECTIVE_1=AI 생성 광고 크리에이티브 플랫폼의 2025-2026 최신 동향 + 시장 점유율 + 주요 플레이어 + 광고 효과 사례
```

**박제 정책 박제 (사전 결손 식별)**:
- `topics/*.env` 가 의도된 local-only 정책 (사용자 운영 자산 보호)
- 검증용 토픽도 운영 토픽과 동일 정책 적용
- 박제 자산 reproduction 메커니즘 = 박제 자산 인라인 박제 + 측정자 재작성
- 향후 다른 § 의 검증/측정 토픽 작업 시 동일 패턴 적용
- 본 결손은 Phase 1 코드 리뷰 결손 아님 (gitignore 정책 검토는 Phase 1 범위 외), §14-3 (NEW)-B 트랙 1 P-2 의 **사전 결손** 박제

### 1.3 pre-clear standalone (sub-task 2)

- exit code: 0
- ns: `ai-generated-creative-ad-platforms-web`
- method: `shutil.rmtree`
- before: files=1 bytes=188,416 → after: files=0 bytes=0
- elapsed: 1.95s
- fallback_used: false, errors: []

### 1.4 T4 P-2 dry-run 명령

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:LOCAL_RAG_ALLOW_EMPTY="1"
$env:TOPIC_SLUG="ai-generated-creative-ad-platforms"

& "D:\GPT_AGENT\.venv_vertex\Scripts\python.exe" `
  "...\_step3_dry_run_rag_update.py" `
  --topic-slug "ai-generated-creative-ad-platforms" `
  --topic-title "AI 생성 광고 크리에이티브 플랫폼 동향" `
  --trigger "최신 자료로 RAG 업데이트해줘" `
  --output "...\T4_P2_*.json" `
  --recursion-limit 100 `
2>&1 | Tee-Object -FilePath "...\T4_P2_*.console.log"
```

raw 산출물 (gitignore 자동 적용):
- `scripts/output/§14-3/_dry_run/T4_P2_ai-generated-creative-ad-platforms.json` (gitignore L82)
- `scripts/output/§14-3/_dry_run/T4_P2_ai-generated-creative-ad-platforms.console.log` (gitignore L85)
- `scripts/output/§14-3/_dry_run/clear_T4_P2.json` (gitignore L82)

---

## § 2. 분기 (가) 확정 근거 (★★★★★)

| 박제 항목 | 값 |
|----------|-----|
| vertex_grounding count | **1** (직전 T4: 0) |
| doc[7] source URL | `https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE1Xmigy6nlN...` |
| doc[7] source_class | `vertex_grounding` |
| doc[7] page_content_len | 500 |

URL 패턴 `vertexaisearch.cloud.google.com/grounding-api-redirect/` 은 Vertex AI Gemini grounding API 의 unambiguous redirect URL → vertex grounding metadata 실제 캡처 확정.

§14-3 (NEW)-B 트랙 1 P-2 **본 미션 완료**.

---

## § 3. 환경 변수 흐름 5 단계 검증 결과

| 단계 | 매칭 박제 | 결과 |
|------|----------|------|
| 1 | `[env] loaded D:\...\.env.vertex` (dry-run script L46) | ✓ |
| 2 | 글로벌 .env load (verbose=False, silent) | (간접) |
| 3 | `[Config] LLM provider overlay 로드: D:\...\.env.vertex` | ✓ |
| 4 | `[Config] 토픽 프리셋 로드: D:\...\topics\ai-generated-creative-ad-platforms.env` | ✓ ★ |
| 5 | SKIP runtime=False → vertex 호출 분기 진입 | ✓ (vertex_grounding=1 결과로 추정) |

### 3.1 부수 박제 — clear subprocess env propagate

clear subprocess (`_phase_b_clear_ns.py`) 의 stdout_tail 에도 토픽 프리셋 로드 메시지 매칭:
```
[Config] 토픽 프리셋 로드: D:\GPT_AGENT\writer_project\topics\ai-generated-creative-ad-platforms.env
```
→ parent process 의 `$env:TOPIC_SLUG` 가 child process 에 자연스럽게 propagate 확인.

---

## § 4. 직전 T4 vs P-2 비교

| metric | 직전 T4 | P-2 | 변화 |
|--------|---------|-----|------|
| elapsed_sec (total) | 99.72 | 166.08 | +66.36 (+66.5%) |
| invoke_elapsed_sec | (n/a) | 159.62 | — |
| abort_reason | null | null | — |
| refs_docs_count | 5 | 8 | +3 |
| source_dist.web | 5 | 7 | +2 |
| source_dist.vertex_grounding | **0** | **1** | **+1** ★★★★★ |

elapsed +66.5% 증가는 vertex grounding API 호출 added latency 정합 (Vertex AI Gemini grounding 단일 attempt latency 예상치 60~80s).

---

## § 5. §12-19 per-topic override 패턴 검증 완료

검증된 흐름:
- 글로벌 `.env`: `SKIP_VERTEX_SEARCH=1` (base policy 활성)
- `topics/<slug>.env`: `SKIP_VERTEX_SEARCH=0` (per-topic override 적용)
- runtime: SKIP=False → vertex 호출 분기 (L764) 진입 → grounding metadata 캡처

§12-19 운영 사례 (venfobel-vitamin 패턴) 와 정합. README-dev.md L1073~1148 §12-19 트랙 reference.

---

## § 6. 부수 발견 박제 (Claude Code 자율 식별)

### 6.1 PowerShell 5.1 NativeCommandError stderr wrapping

Vertex deprecation warning (google-cloud-storage < 3.0.0, ChatVertexAI/VertexAIEmbeddings deprecation 등) 이 stderr 로 출력되어 `2>&1` redirect 시 ErrorRecord wrapping 발현. exit 0 정상 종료.

박제: 기존 박제 chain (PowerShell 5.1 환경 박제) 정합 자산.

### 6.2 `[smoke] all queries miss + [ALERT] 결과 0건 쿼리 비율 100%` (★★★)

- chroma collection_count=0 throughout 측정 (web/local/base 모두 0)
- `web_rag.retrieve` 가 chroma 에 저장 못 함
- 그러나 references state 에는 정상 누적 (refs_docs=8) → 측정 결과 자체는 valid
- **신규 진단 트랙 후보** — § 7 박제

### 6.3 vertex_grounding=1 단일 attempt

8 refs 중 1건만 vertex grounding URL. Vertex grounding 은 single attempt, 나머지는 fallback web search (Naver/Tavily) 결과. 정상 동작 박제.

Phase 3 본 측정 시 변동성 분석 plan 활용 필요 — § 8 박제.

---

## § 7. chroma collection_count=0 신규 트랙 후보 (★★★)

본 P-2 측정에서 chroma collection_count=0 throughout 발견:
- `web_rag.retrieve` 가 chroma 에 저장 못 함
- Phase B 측정 시 동일 패턴 가능성 (재확인 필요)
- references state 에는 정상 누적 → 본 P-2 결과 (vertex_grounding=1) valid

신규 트랙 후보:
- **P-3** (현 §14-3 (NEW)-B 의 sub-step) 또는
- **§14-3 (NEW)-C** (별도 트랙 분리)

미션: chroma collection_count=0 원인 진단 + Phase 3 본 측정의 noise 영향 평가.

분리 결정 미정 — sub-task 4+5 commit 후 user 결정.

---

## § 8. vertex_grounding=1 단일 attempt 의 Phase 3 영향 박제

Phase 3 본 측정 (5078a2d vs 1135ac1):
- N=3 × 2 commit = 6 run
- 각 run 의 vertex_grounding count 가 1 으로 고정인지 변동성 있는지 미확정
- 변동성 분석 plan (직전 박제 chain 의 측정 표준) 활용 필요

박제 표준:
- vertex_grounding count 의 N=3 간 std / CV 측정
- CV > 30% 시 측정 무효 판정 (기존 측정 신뢰성 박제)
- patch 효과 vs 변동성 noise 분리 분석

---

## § 9. §14-2 측정 재검증 트랙 reference

직전 박제 자산 (`(NEW)-B_option3_code_review.md` § 9) 의 §14-2 측정 재검증 트랙:
- §14-2 Phase A 단독 측정의 SKIP_VERTEX 우회 사실 확인
- §14-2 Phase B 측정 결과 재해석 (vertex 우회 상태 측정)
- Step 1b patch 본 검증 재측정 필요성 판단

§14-3 (NEW)-B 트랙 1 P-2 완료 후 진입 옵션:
- Phase 3 본 측정 직진 (chroma 결함 + §14-2 재검증 sub-step 병행)
- 또는 sub-step 우선 진행

분리 결정 미정 — sub-task 4+5 commit 후 user 결정.

---

## § 10. 다음 단계 plan (user 결정 미박제)

§14-3 (NEW)-B 트랙 1 P-2 close 후 분기:

| 분기 | 내용 |
|------|------|
| (P) | Phase 3 본 측정 즉시 진입 (5078a2d vs 1135ac1, N=3×2) |
| (Q) | chroma 결함 진단 트랙 (P-3 또는 (NEW)-C) 우선 |
| (R) | §14-2 재검증 트랙 (sub-step) 우선 |
| (S) | 병행 (Phase 3 진입 + 진단 트랙 분리 박제) |

사용자 결정 미박제 — commit 후 별도 user 컨펌 받고 결정.

---

## 부록 A. 참고 파일

- `topics/ai-generated-creative-ad-platforms.env` (792 bytes, 검증용 토픽 env 파일)
- `scripts/_step3_dry_run_rag_update.py` (dry-run driver)
- `scripts/_phase_b_clear_ns.py` (pre-clear)
- `scripts/output/§14-3/(NEW)-B_option3_code_review.md` (직전 commit 박제, 옵션 3 결과)
- `scripts/output/§14-3/topic_selection.md` (Tier 2 dry-run 결과)
- `scripts/output/§14-3/_dry_run/T4_P2_*.json` + `*.console.log` (gitignore 적용 raw)
- `README-dev-§14.md` (§14-3 (NEW)-B 진행 박제)
- `README-dev-2.md` (디버깅 표준 영구 박제)
- `README-dev.md` L1073~1148 (§12-19 트랙 origin)
