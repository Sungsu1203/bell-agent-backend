# STANDARDS — 파이프라인 공통 표준

> 측정·환경·보안 공통 규칙. 회사/논문 트랙 무관 적용. `CLAUDE.md §6`에서 이 문서를 지목(역참조).
> 원천: `scripts/output/` 작업 로그에서 재사용 규칙만 승격 (2026-07).
> 원본 박제 위치는 각 섹션 말미 "원본" 줄 참조.

---

## 1. ENV 4-layer 로드 순서

### 1.1 layer 정의 + override
| Layer | 파일 | load 시점 | override | 코드 위치 |
|------|------|----------|---------|----------|
| **L1** 글로벌 .env | `.env` | graph import 시 `_load_dotenv_once` | **False** | `core/config.py:163` |
| **L2** provider overlay | `.env.{provider}` | L1 직후 `_apply_provider_overlay` | True | `core/config.py:120` |
| **L3** topic preset | `topics/{TOPIC_SLUG}.env` | L2 직후 `_apply_topic_preset` | True | `core/config.py:143` |
| **L4** script 별도 load | 각 script start | graph import **전** | True | script L40~50 부근 |

로드 순서(실행 흐름): **L4** (script, graph import 전) → **L1** (글로벌) → **L2** (provider overlay) → **L3** (topic preset).

### 1.2 생존 규칙
- L1의 `override=False` → L4가 이미 set한 변수는 그대로 생존(script env 우선).
- L2/L3의 `override=True` → 글로벌·L4 값을 덮어씀.
- **topic preset 활성 조건**: `os.environ["TOPIC_SLUG"]`가 set돼야 함. `state.topic_slug`만 설정하면 `_apply_topic_preset` 미작동 (자주 놓치는 결손).

### 1.3 다른 작업 진행 시 ENV 확인 절차
1. **CFG 선언 확인이 0단**: `git grep -n "<KEY>" -- "core/config.py"` → 0건이면
   파서 #2(`_cfg_*`) 경로에서 `.env`는 무효. 2~4단 생략하고 코드 기본값을 본다. 
2. **L4 확인**: script의 `.env` load 명시 여부 + 어느 파일 load.
3. **L3 확인**: `topics/{TOPIC_SLUG}.env` override 여부 (TOPIC_SLUG env var 활성 필수).
4. **L1 확인**: 글로벌 `.env` base 값.
5. **runtime 확인**: `python -c "import core.config as c; print(c.CFG.<변수>)"`.

### 1.4 새 토픽 작성 표준
- `topics/_template.env` 복사 + 파일명 = `TOPIC_SLUG`와 동일.
- 필수: `TOPIC_TITLE`, `TOPIC_SLUG`, `BLOCKAGI_OBJECTIVE_1`.
- 검증용 토픽: `SKIP_VERTEX_SEARCH=0` 명시.

### 1.5 측정 driver 작성 표준
- L4 load: `.env.{provider}` only (override=True).
- `$env:TOPIC_SLUG` 명시 set (L3 활성 보장).
- env capture log 작성 (콘솔 L1~10).
- `[Config] 토픽 프리셋 로드` 메시지 확인 (L3 활성 evidence).

### 1.6 새 `.env.*` 파일 추가 시 보안 점검 절차
1. `git check-ignore -v <file>` 로 ignore 매칭 패턴 확인.
2. `git log --all --oneline -- <file>` 로 history 점검.
3. 마스킹 박제 갱신.
4. 점검 결과 박제.
- rotate 필요 trigger: gitignore 누락 발견 / history commit 발견 / remote push 노출 발견.

> 원본: `scripts/output/§14-3/env_flow_matrix.md`

---

## 2. 측정 metric 정의

### 2.1 ref source 5분류 (robustness — silent 분류 누락 방지)
분류 기준 = `state.references.docs[i].source` 값.

| source | 정의 |
|--------|------|
| `vertex_grounding` | Gemini 내부 Google Search grounding_metadata → references append |
| `web` | Naver/Tavily 등 외부 search API 명시 호출 결과 |
| `local` | ChromaDB local index retrieve 결과 |
| `other` | 명시적 source 값 있으나 위 3개 외 (예: `api`, `manual`) |
| `unknown` | source 키 부재 / None / 빈 문자열 |

- `vertex_grounding` vs `web` 핵심 차이: 전자는 LLM 응답 생성 중 자동(응답 부산물), 후자는 `web_search` 노드 명시 호출.

### 2.2 진입·판정 임계
- **Tier2 dry-run 진입 조건**: `vertex_grounding count > 0` (0 → 토픽 niche 또는 Google Search index 약함 → patch 효과 측정 불가).
- **변동성 임계**: `vertex_grounding count`의 N=3간 `CV > 30%` → 토픽 unstable, patch 효과 vs noise 분리 불가 → Tier1 fallback / 재시도 결정.
- **한국어 grounding 주의**: Google Search 한국어 corpus가 영어 대비 grounding metadata를 적게 반환할 수 있음 → 한국어 토픽은 별도 검증.

> 원본: `scripts/output/§14-3/metric_definitions.md`

---

## 3. Chroma reset 정책

- **reset 책임 = driver**. graph의 `ensure_vector_store_cleared_once`는 `_CLEARED_ONCE_KEYS`/`_CLEARED_RUNTIME_KEYS` 가드로 **process당 1회만** 동작 → multi-invoke 측정 환경에선 사실상 no-op.
- **reset 단위 = `ns_web`만, `ns_local`(PDF chunks) 보존**:
  1. 매 run 재인덱싱 시 누적 오버헤드 (예: 5 sections × 3 runs × 2 commits = 30회 = +15분).
  2. PDF chunks는 patch 영향 없음 (vertex grounding 변경은 web/vertex 경로만).
  3. `local_first + 0.33` 정책 유지 → 측정 동질성 보장.
- **reset 시점 = multi-turn 시퀀스 1회 전체 시작 전 1번** (`_run_single` 진입 직후, `graph.invoke` 전). 매 turn마다 reset하면 앞 turn의 web search 결과가 다음 turn retrieve에서 사라져 invariance 붕괴.
- **격리 방식** (측정 시작 전 확정):
  - (권고) **subprocess 분리** — graph/LLM/Chroma handle 완전 격리, spawn overhead ~3~5s는 측정 elapsed에서 제외.
  - (대안) in-process guard 우회 시 clear 대상 3종: `_CLEARED_ONCE_KEYS` · `_CLEARED_RUNTIME_KEYS` · `_VS_CACHE` (해당 `(persist_dir, ns_web)` key discard/pop 후 `clear_vector_store`).
- 측정 박제 시 "ns_web reset 정책: …" 명시.

> 원본: `scripts/output/§14-2/phase_b_reset_policy.md` (실경로 `scripts/output/phase_b_reset_policy.md`)

---

## 4. `_PROTECTED_ENV_KEYS`

reload 시 `.env` 정적 default가 driver-set 값을 flip하는 것을 차단 (안 하면 provider/model/topic이 뒤집힘).

### 4.1 보호 5키
```python
_PROTECTED_ENV_KEYS = (
    "LLM_PROVIDER",         # MUST — overlay 분기 결정
    "LLM_MODEL",            # MUST — vertex_web_search 가 os.getenv 로 직접 read
    "TOPIC_SLUG",           # MUST — topic preset 분기 결정
    "SKIP_VERTEX_SEARCH",   # MUST — vertex grounding gate
    "MIRROR_STATE_TO_ENV",  # 권장 — driver intent 보호 (defense-in-depth)
)
```

### 4.2 snapshot / restore 원칙·시점
- **의미**: snapshot 값이 str이면 restore(driver 명시 intent 보호), `None`이면 skip(.env 값 허용 = hot-reload 의도 보존).
- **시점**: `reload_config_inplace()`의 `load_dotenv(override=True)` **직전** snapshot, **직후 + `_apply_provider_overlay`/`_apply_topic_preset` 직전** restore.
- → overlay·preset이 driver-restored `LLM_PROVIDER`/`TOPIC_SLUG` 기반으로 정상 분기.
- patch 위치: `core/config.py reload_config_inplace` (L667).

> 원본: `scripts/output/§14-8/B-3_audit.md` (§3-2 `_PROTECTED_ENV_KEYS` 확정 부분)

---

## 5. credential 노출 감사

### 5.1 3-명령 감사
1. `git ls-files <env files>` → tracked 여부 (empty = 미tracked).
2. `git check-ignore -v <file>` → ignore 매칭 규칙·source 확인.
3. `git log --all --oneline -S "<prefix>"` → key prefix별 history 노출 여부 (0 hit = 미노출).

### 5.2 마스킹 규칙
- 박제 시 key 값 전체 노출 금지 — **prefix 4~8자 + `***`만**.

### 5.3 provider 키 분리 convention
- LLM provider 키(openai/anthropic 등) = `.env.{provider}` overlay 위치.
- search backend 키(tavily/naver 등) = 글로벌 `.env` 위치 (LLM_PROVIDER와 decoupled).

### 5.4 rotation·scrub 판단
- rotation 판단 전 **live/idle 분류** 선행 (노출 자체가 부재하면 rotation 의무 없음).
- rotate trigger: gitignore 누락 / history commit 발견 / remote push 노출.
- **STOP 게이트**: history scrub(`git filter-repo` 등)은 **rotation 완료 + collaborator 0명 또는 사전 동의 + 백업 push** 이후에만. read-only 감사 단계에서 실행 금지.

> 원본: `scripts/output/§14-9-A1/credential_exposure_audit.md` (§1-b/1-c 감사 명령 + §2 convention + §3 rotation 체크리스트)
