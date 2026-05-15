# §14-3 (보조-1) 환경 변수 4 layer 흐름 매트릭스

본 문서는 §14-3 사이클 진행 중 환경 변수 4 layer 복합성으로 박제 자산 신뢰성 위협이 발견된 후 작성된 영구 reference 박제 자산.
향후 모든 § 진행 시 환경 변수 확인 표준 (사전 확인 컨벤션 정합).

- 작업 일시: 2026-05-16
- 진입 사유: §14-3 (NEW)-B 트랙 1+2 진행 중 layer 간 override 흐름 박제 자산 누적, 사용자 박제 "헷갈려" 직접 신호
- 핵심 변수: 13개 (시나리오 분기에 영향 주는 변수만 선정)
- 표 형식: (i) 단일 wide 9 열 채택 (가독성 부족 시 § 3.x 분리)

**보안 경고**: `.env.openai` (L25) + `.env.anthropic` (L24) 에 평문 API key 존재. 본 박제 자산은 key 값 **마스킹** 처리. 향후 rotate 정책 검토 필요 (별도 트랙).

---

## § 1. 4 layer 정의

| Layer | 파일 | load 시점 | override | 코드 위치 |
|------|------|----------|---------|----------|
| **L1** 글로벌 .env | `.env` | graph import 시 `_load_dotenv_once` | **False** | `core/config.py:163` |
| **L2** provider overlay | `.env.{provider}` | L1 직후 `_apply_provider_overlay` | True | `core/config.py:120` |
| **L3** topic preset | `topics/{TOPIC_SLUG}.env` | L2 직후 `_apply_topic_preset` | True | `core/config.py:143` |
| **L4** script 별도 load | 각 script start | graph import **전** | True | script L40~50 부근 |

- L1 의 `override=False` → L4 가 이미 set 한 변수는 유지 (script env 우선)
- L2/L3 의 `override=True` → 글로벌/L4 값 덮어쓰기
- L3 (topic preset) 활성 조건: `os.environ["TOPIC_SLUG"]` set (state.topic_slug 무관)

---

## § 2. 4 layer load 흐름 도식

```
[script start]
    ↓
[L4: script 별도 .env load]   ← .env.vertex only (override=True)
    ↓
[graph import]
    ↓
[L1: 글로벌 .env load]        ← _load_dotenv_once L163 (override=False)
    ↓
[L2: .env.{provider} overlay] ← _apply_provider_overlay (override=True)
    ↓
[L3: topics/{slug}.env preset] ← _apply_topic_preset (override=True)
    ↓
[graph runtime]
```

**주의**:
- L4 가 L1 보다 먼저 load (script 가 graph import 전 실행)
- L1 의 `override=False` 로 L4 가 set 한 변수는 graph runtime 까지 그대로 유지
- topic preset 활성은 L4 또는 L1 단계에서 `TOPIC_SLUG` env var 가 set 되어야 함

---

## § 3. 13 핵심 변수 매트릭스 (L1 + L2 × 3 + L3 × 5)

선정 기준: §14-3 사이클 동안 박제된 변수 또는 시나리오 분기에 영향 주는 변수.

표기 규칙:
- 값 표시: 명시된 값 그대로
- `(미명시)`: 변수 명시 안 됨
- `(주석)`: 주석 처리됨 (active 아님)
- `★`: 직전 layer 의 값을 override
- `***`: 평문 키 마스킹

### § 3.1 L1 + L2 (글로벌 + provider overlay)

| 변수 | L1 글로벌 | L2 vertex | L2 openai | L2 anthropic |
|------|----------|-----------|-----------|--------------|
| LLM_PROVIDER | `openai` | `vertexai` ★ | `openai` | `anthropic` ★ |
| LLM_MODEL | `gpt-4o` | `gemini-2.5-flash` ★ | (미명시, OPENAI_MODEL 별도) | (미명시, ANTHROPIC_MODEL 별도) |
| SKIP_VERTEX_SEARCH | `1` | (미명시) | `0` ★ | `1` |
| TOPIC_SLUG | `venfobel-vitamin` | (미명시) | (미명시) | (미명시) |
| TOPIC_TITLE | (주석) | (미명시) | (미명시) | (미명시) |
| TOPIC_KEYWORDS | (미명시) | (미명시) | (미명시) | (미명시) |
| CHROMA_NS_POLICY | `merge` | (미명시) | (미명시) | (미명시) |
| BLOCKAGI_OBJECTIVE_1~5 | (미명시, 주석 안내) | (미명시) | (미명시) | (미명시) |
| MAX_INDEXED_PER_ROUND | `60` | (미명시) | (미명시) | (미명시) |
| LOCAL_RAG_ALLOW_EMPTY | `1` | (미명시) | (미명시) | (미명시) |
| RAG_DISTANCE_THRESHOLD | `0.65` | `0.65` | `1.10` ★ | `1.10` ★ |
| GCP_PROJECT_ID | `gemini-rag-search-final` | `gemini-rag-search-final` | (미명시) | (미명시) |
| ANTHROPIC_API_KEY | (미명시) | (미명시) | (미명시) | `sk-ant-***` |

### § 3.2 L3 topic preset (5 토픽)

| 변수 | venfobel-vitamin | pet-food-premium | height-growth | ai-gen-creative (P-2) | _template |
|------|------------------|------------------|---------------|-----------------------|-----------|
| LLM_PROVIDER | (미명시) | (미명시) | (미명시) | (미명시) | (미명시) |
| LLM_MODEL | (미명시) | (미명시) | (미명시) | (미명시) | (미명시) |
| SKIP_VERTEX_SEARCH | (주석 L35) | (미명시) | (미명시) | `0` ★ | (미명시) |
| TOPIC_SLUG | `venfobel-vitamin` (env 자체) | `pet-food-premium` | `height-growth-supplement` | `ai-generated-creative-ad-platforms` | (빈값) |
| TOPIC_TITLE | 종근당 벤포벨S 2026... | 국내 프리미엄 반려동물... | 키성장 건강기능식품... | AI 생성 광고 크리에이티브... | (빈값) |
| TOPIC_KEYWORDS | venfobel,벤포벨,비타민... | (미명시) | (미명시) | AI,generative,creative... | (미명시) |
| CHROMA_NS_POLICY | (미명시) | (미명시) | (미명시) | (미명시) | (미명시) |
| BLOCKAGI_OBJECTIVE_1~5 | 5건 정의 | 5건 정의 | 3건 정의 | 1건 placeholder | 3건 빈 키 |
| MAX_INDEXED_PER_ROUND | (미명시) | (미명시) | (미명시) | (미명시) | (미명시) |
| LOCAL_RAG_ALLOW_EMPTY | (미명시) | (미명시) | (미명시) | (미명시) | (미명시) |
| RAG_DISTANCE_THRESHOLD | (미명시) | `0.60` ★ | (미명시) | (미명시) | (미명시) |
| GCP_PROJECT_ID | (미명시) | (미명시) | (미명시) | (미명시) | (미명시) |
| ANTHROPIC_API_KEY | (미명시) | (미명시) | (미명시) | (미명시) | (미명시) |

추가 venfobel-vitamin 만의 변수 (본 매트릭스 미포함, 메모):
- `MERGE_RETRIEVE_MODE=local_first` (L48)
- `RETRIEVE_WEB_RATIO=0.33` (L49)
- `RAG_TOP_K=10` (L56)

---

## § 4. 시나리오별 runtime 흐름 추적 (4 시나리오)

### 시나리오 A: §14-2 Phase B 측정 (5078a2d vs ba44637)

- script: `measure_vertex_phase_b.py`
- L4 load: `.env.vertex` only (L53-61)
- TOPIC_SLUG (L64): `"venfobel-vitamin"` hard-coded → L3 preset 활성
- runtime SKIP_VERTEX_SEARCH: **1** (L1 base 활성, venfobel.env 주석 처리로 override 안 됨)
- runtime LLM_PROVIDER: `vertexai`
- runtime LLM_MODEL: `gemini-2.5-flash`
- **결과**: vertex 호출 가능 환경. 그러나 시나리오가 `"write: <섹션명>"` writer-lock 흐름 → web_search 노드 미진입 → vertex_grounding=0

### 시나리오 B: §14-3 (NEW)-B 트랙 1 P-2

- script: `_step3_dry_run_rag_update.py`
- L4 load: `.env.vertex` only
- $env:TOPIC_SLUG = `ai-generated-creative-ad-platforms` (PowerShell session) → L3 preset 활성 ★
- runtime SKIP_VERTEX_SEARCH: **0** (L3 ai-gen.env override)
- runtime LLM_PROVIDER: `vertexai`
- **결과**: vertex 호출 분기 진입 → vertex_grounding=1 도달 ✓

### 시나리오 C: §14-3 Phase 3 본 측정 plan (시나리오 α)

- script: 신규 driver 또는 `_step3_dry_run_rag_update.py` wrapper (미정)
- L4 load: `.env.vertex` only
- $env:TOPIC_SLUG = (Phase 3 토픽, 미정 — ai-gen 재사용 또는 신규)
- runtime SKIP_VERTEX_SEARCH: **0** (L3 토픽 .env override 전제)
- 측정 N=3 × 2 commit (5078a2d vs ba44637)
- §13-7 표준 적용

### 시나리오 D: Phase A baseline

- script: `measure_vertex_phase_a.py`, `dump_vertex_grounding.py`
- L4 load: `.env.vertex` only
- vertex 호출: `tools/web_rag/vertex_search.py` 의 `vertex_web_search` 직접 호출
- agent layer (L764 SKIP 분기) **미경유**
- **결과**: SKIP_VERTEX_SEARCH 와 무관, vertex 호출 항상 발생

---

## § 5. 알려진 결함 / 주의 사항

### 5.1 §12-19 트랙 박제 (README-dev.md L1073~1148)

- 글로벌 .env 의 `override=True` 재로드 시 토픽 override 회귀 결함
- `reload_config_inplace()` 사용 시 `_apply_topic_preset` 재호출 필수
- venfobel-vitamin 운영 사례: `topics/venfobel-vitamin.env` 끝에 `SKIP_VERTEX_SEARCH=0` 추가하여 글로벌 override (현재 주석 처리됨, L35)

### 5.2 §14-3 (NEW)-B 옵션 3 박제 (commit ca148bc)

- dry-run script 의 `TOPIC_SLUG` env var 미설정 결손 (Phase 1 결손 6번째)
- `state.topic_slug` 만 설정, `os.environ["TOPIC_SLUG"]` 미설정 시 `_apply_topic_preset` 미작동
- 회피: `$env:TOPIC_SLUG=...` 명시 (PowerShell session 또는 script 내 명시)

### 5.3 §14-3 (NEW)-B 트랙 2 박제 (commit a975d47)

- Phase A 가 `vertex_web_search` 직접 호출 — SKIP_VERTEX_SEARCH 무관
- Phase B 가 writer-lock 시나리오 — web_search 노드 미진입, patch dead path

### 5.4 보안 정책 박제 (commit 시점 사전 점검 결과)

발견:
- `.env.openai` L25: `OPENAI_API_KEY=sk-proj-***` 평문
- `.env.anthropic` L24: `ANTHROPIC_API_KEY=sk-ant-***` 평문
- 본 매트릭스 자산은 마스킹 처리 (전체 키 미박제)

gitignore 정책 점검 (commit 시점):
- `.env` / `.env.vertex` / `.env.openai` / `.env.anthropic` 전부 gitignored ✓
- git history 에 commit 된 적 없음 (`git log --all -- .env.*` 결과 empty) ✓
- GitHub push 노출 위험 없음 ✓

매칭 패턴 (정확화):
- `writer_project/.gitignore:12` `.env` — 글로벌 .env 매칭
- 부모 `.gitignore:17` `.env.*` — `.env.vertex` / `.env.openai` / `.env.anthropic` overlay 매칭
- `writer_project/.gitignore:76` `topics/*.env` — 토픽 preset 매칭
- `writer_project/.gitignore:77` `!topics/_template.env.example` — template 예외 (commit 가능)

향후 `.env.*` 파일 추가 시 점검 절차:
1. `git check-ignore -v <file>` 로 ignore 매칭 패턴 확인
2. `git log --all --oneline -- <file>` 로 history 점검
3. 본 매트릭스 § 5.4 매칭 패턴 박제 갱신
4. 점검 결과 박제

향후 키 폐기 (rotate) 필요 trigger:
- gitignore 누락 발견 시
- history 에 commit 발견 시
- GitHub / 다른 remote 에 push 발견 시

### 5.5 LLM_MODEL 변수 분리

- L1: `LLM_MODEL=gpt-4o` (글로벌 활성)
- L2 vertex: `LLM_MODEL=gemini-2.5-flash` ★ (override)
- L2 openai: `OPENAI_MODEL=gpt-4o` (별도 변수, LLM_MODEL 미명시)
- L2 anthropic: `ANTHROPIC_MODEL=claude-haiku-4-5-20251001` (별도 변수)
- runtime LLM_MODEL 값은 provider 별 fallback 로직 (code review 필요, 본 매트릭스 미포함)

---

## § 6. chroma 진단 결과 통합 (축약)

§14-3 (NEW)-B 트랙 1 P-2 측정 시 chroma `collection_count=0` throughout 발견. 그러나 references state 정상 누적 (refs_docs=8) → 측정 valid.

상세 박제 → `(NEW)-B_track1_P2_result.md` § 6.2 + § 7.

핵심 박제:
- `web_rag.retrieve` 가 chroma 에 저장 못 함 (저장 흐름 부분 결함)
- vertex_grounding doc 은 chroma 저장 흐름과 분리 (vertex API 직접 결과)
- references state 누적은 정상 → 측정 metric 산출 가능

Phase 3 영향도 **★ (낮음)** 평가:
- patch 효과 측정 = 양쪽 commit (5078a2d / ba44637) 차이
- 공통 환경 조건은 noise 아님
- chroma 결함이 양쪽 동일 발현 시 측정 valid 유지

환경 변수 chroma 관련 시나리오 영향:
- `CHROMA_NS_POLICY=merge` (글로벌) — venfobel.env `MERGE_RETRIEVE_MODE=local_first` 별도 변수 override
- `MAX_INDEXED_PER_ROUND=60` (글로벌, 토픽 override 없음)
- 시나리오 B (P-2) / C (Phase 3 plan) 동일 chroma 환경 → 결함 발현 동일 예상

신규 진단 트랙 후보 (사후): (NEW)-B 트랙 3 (chroma 진단) 미시작 보존 — 본 매트릭스 § 6 통합으로 자연 해소. Phase 3 본 측정 시 noise 실 발현 시 별도 진단 트랙 재진입 가능.

---

## § 7. 향후 reference 표준

### 7.1 다른 § 진행 시 환경 변수 확인 절차

1. **L4 확인**: script 의 `.env` load 명시 여부 + 어느 파일 load
2. **L3 확인**: `topics/{TOPIC_SLUG}.env` 의 변수 override 여부 (TOPIC_SLUG env var 활성 필수)
3. **L1 확인**: 글로벌 `.env` 의 base 값
4. **runtime 확인**: `python -c "import core.config as c; print(c.CFG.{변수})"` (§12-19 진단 명령)
5. 본 매트릭스 § 3 + § 4 참조

### 7.2 새 토픽 작성 시 표준

- `topics/_template.env` 복사 + 이름은 `TOPIC_SLUG` 와 동일
- 필수: TOPIC_TITLE, TOPIC_SLUG, BLOCKAGI_OBJECTIVE_1
- 검증용 토픽 (예: P-2 ai-gen): SKIP_VERTEX_SEARCH=0 명시
- 운영 토픽: 측정 표준에 따라 변수 조정

### 7.3 측정 driver 작성 시 표준

- L4 load: `.env.{provider}` only (override=True)
- `$env:TOPIC_SLUG` 명시 set (L3 활성 보장)
- env capture log 작성 (L1~10 console)
- `[Config] 토픽 프리셋 로드` 메시지 확인 (L3 활성 evidence)

---

## 부록 A. 참고 파일

- `.env`, `.env.vertex`, `.env.openai`, `.env.anthropic` (4 layer 파일)
- `topics/*.env` (5 토픽 preset)
- `core/config.py:106-167` (overlay/preset 로직)
- `scripts/output/§14-3/(NEW)-B_option3_code_review.md` (옵션 3, env 흐름 5 단계 박제)
- `scripts/output/§14-3/(NEW)-B_track1_P2_result.md` (P-2, chroma 결함 발견 + § 1.2 env 인라인 박제)
- `scripts/output/§14-3/(NEW)-B_track2_phase_b_review.md` (트랙 2, Phase A/B 재해석)
- `scripts/output/phase_b/phase_b_summary.md` (Phase B close 박제, authoritative)
- `README-dev.md:1073-1148` (§12-19 트랙)
- `README-dev-§14.md` (§14-3 진행 박제)
- `README-dev-2.md` (디버깅 표준 영구 박제)
