# §14-3 (NEW)-B 옵션 3: graph 내부 분기 점검 (가설 A 코드 review)

본 문서는 §14-3 (NEW)-B 트랙의 옵션 3 (graph 내부 분기 코드 review) 결과 박제.
가설 A (vertex_web_search 호출 자체가 안 됨) 의 코드 기반 확정 및 신규 식별 항목 (시나리오 10/11, TOPIC_SLUG env var 결손) 박제.

- 작업 일시: 2026-05-16
- 진단 범위: 작업 0~3 + 보강 진단 4건
- 분기 결정: **(가) Hypothesis A 코드 확정** → 트랙 1 (P-2) 진입
- 관련 commit: 03baed0 (§14-3 진행 박제: Phase 2 Step 3 close + (NEW)-B 진입 + 디버깅 표준 영구 박제)

---

## § 1. 측정 메타 + 진단 4건 raw 결과

### 1.1 작업 0: SKIP_VERTEX_SEARCH default + 본 측정 환경 활성 여부

env 파일 명시 여부:

| 파일 | SKIP_VERTEX_SEARCH | 비고 |
|------|--------------------|------|
| `.env` (글로벌) | `SKIP_VERTEX_SEARCH=1` | ★ base policy 활성 |
| `.env.vertex` | (명시 없음) | overlay 가 글로벌 값 override 못 함 |
| `.env.openai` | `SKIP_VERTEX_SEARCH=1` | OpenAI 모드 자연스러움 |

코드 grep 결과:

- `agent/web_search.py:92` — `_cfg_bool` 정의 (default=False)
- `agent/web_search.py:764` — vertex_web_search 호출 분기:
  ```python
  if attempt == 0 and query and not _cfg_bool("SKIP_VERTEX_SEARCH", False):
  ```
- `agent/web_search.py:813-814` — skip 분기 logger:
  ```python
  elif attempt == 0 and _cfg_bool("SKIP_VERTEX_SEARCH", False):
      logger.info("[web_search] Vertex skipped (SKIP_VERTEX_SEARCH=1)")
  ```
- `core/config.py:246/250` — TypedDict 정의 (중복 선언)
- `core/config.py:477` — `_env_flag("SKIP_VERTEX_SEARCH", False)` default False

### 1.2 작업 1: auto_mode 분기 진입 흐름

- `agent/web_search.py:1088` — `auto_mode = "rag_update:auto" in mission.lower()`
- `agent/supervisor.py:609` — `_rag_re` 정규식으로 trigger 분기
- planner_qs / forced_queries / auto query 생성 분기 박제

### 1.3 작업 2: _run_web_search_with_guard 호출 chain

- `agent/web_search.py:758-795` — `_run_web_search_with_guard(q)` 호출 chain
- vertex_search 진입 조건 변수 박제:
  - `attempt`: 0 (초기) → 1+ (fallback 시 증가)
  - `query`: 빈 문자열 / None 시 진입 불가
  - `SKIP_VERTEX_SEARCH`: ★ 본 검증의 핵심 변수

### 1.4 작업 3: T4/T5/T6 console.log vertex 키워드 grep

console.log 매칭 결과:

| 파일 | `vertex` 매칭 | 비고 |
|------|--------------|------|
| T4_*.console.log | L5 의 env capture `SKIP_VERTEX_SEARCH=<unset>` 만 | 호출/skip 메시지 0건 |
| T5_*.console.log | 동일 | 동일 |
| T6_*.console.log | 동일 | 동일 |

**역설**: L813-814 의 skip 분기 logger 가 console.log 에 매칭 안 됨 → 시나리오 10/11 (§3) 식별.

### 1.5 진단 보강 4건

- **진단 1**: `_step3_dry_run_rag_update.py` 의 dotenv load 흐름 (L43~46): `.env.vertex` 만 load, 글로벌 `.env` 미경유.
- **진단 2**: `core/config.py:153` `_load_dotenv_once` 흐름 — graph import 시 L163 `load_dotenv(find_dotenv(usecwd=True), override=False)` 로 글로벌 `.env` load.
- **진단 3**: console.log L1~20 env capture — `LLM_PROVIDER=vertexai`, `SKIP_VERTEX_SEARCH=<unset>` (dry-run script env capture 시점, graph 진입 전).
- **진단 4**: §12-19 진단 명령 (`python -c "from core import config; print(config.CFG.SKIP_VERTEX_SEARCH)"`) 실행 결과 — runtime `SKIP=True` (TOPIC_SLUG=venfobel-vitamin overlay 결과).

---

## § 2. 가설 A 확정 박제 (★★★★★)

### 2.1 확정 근거

1. `.env` (글로벌) 에 `SKIP_VERTEX_SEARCH=1` 명시
2. `.env.vertex` 에 `SKIP_VERTEX_SEARCH` 미명시 → overlay 가 글로벌 값 override 안 함
3. `core/config.py:163` `load_dotenv(.., override=False)` 로 graph import 시 글로벌 `.env` load → os.environ 에 SKIP=1 set
4. runtime 시점 `_cfg_bool("SKIP_VERTEX_SEARCH", False)` = `True`
5. `agent/web_search.py:764` 호출 분기: `not True = False` → vertex_web_search 호출 분기 **진입 불가**

### 2.2 검증된 분기

| 분기 | 평가 | 근거 |
|------|------|------|
| L764 vertex 호출 분기 | 진입 불가 | SKIP=1 활성 |
| L813-814 skip 분기 | 진입 추정 | But logger 매칭 0건 → 시나리오 10/11 |

### 2.3 분기 결정

**분기 (가) Hypothesis A 코드 확정** — 원인 분석 + 수정 plan 진입 권고.

---

## § 3. 시나리오 10/11 신규 식별 (★★★★)

### 3.1 logger 박제 모순

L813-814 skip 분기에 logger 박제 존재:
```python
logger.info("[web_search] Vertex skipped (SKIP_VERTEX_SEARCH=1)")
```

그러나 T4/T5/T6 console.log 에 매칭 0건.

### 3.2 신규 가설

- **시나리오 10**: `web_search` 노드 진입 자체 안 됨 (graph 라우팅 결함 또는 conditional edge)
  - 검증 방법: supervisor → web_search 라우팅 로그 / graph trace
- **시나리오 11**: logger handler 결함 (다른 stream redirect / suppressed / file handler)
  - 검증 방법: logger 설정 review / handler list inspect

### 3.3 추가 검증 트랙

§14-3 (NEW)-B 의 sub-step 또는 별도 § 분리 — 트랙 1 (P-2) 결과 분기 후 진입.

---

## § 4. TOPIC_SLUG env var 미설정 결손 박제 (★★★★)

### 4.1 결손 내용

- `_step3_dry_run_rag_update.py:194` 에서 `state["topic_slug"]` 만 설정
- `os.environ["TOPIC_SLUG"]` 미설정
- core.config `_apply_topic_preset` 미작동 (os.getenv("TOPIC_SLUG") 빈 문자열)
- `topics/<slug>.env` load 안 됨

### 4.2 운영 사례와 단절

§12-19 트랙 (README-dev.md L1073~1148) 의 venfobel-vitamin override 패턴:
- `topics/venfobel-vitamin.env` 에 `SKIP_VERTEX_SEARCH=0` 추가 → 글로벌 base override
- dry-run script 가 이 패턴을 활용 못 함

### 4.3 영향

T4/T5/T6 모든 dry-run 이 글로벌 `.env` 의 SKIP=1 그대로 활성 상태로 실행됨.

---

## § 5. SKIP_VERTEX_SEARCH 의 정확한 의미 박제 (★★★★★)

### 5.1 base policy 의도

`SKIP_VERTEX_SEARCH=1` 글로벌 base 는 다음 의도로 설정:

- **origin 1**: 2026-05-02 conversation (chat id 27886ba3) — 한국어 latency 최적화 + 영어 토픽 override 패턴
- **origin 2**: §12-19 트랙 (README-dev.md L1073~1148) — venfobel-vitamin 운영 사례 + 알려진 bug + 진단 명령

### 5.2 §12-19 트랙 영구 박제 reference

| 위치 | 내용 |
|------|------|
| README-dev.md L1078 | `topics/venfobel-vitamin.env` 끝에 `SKIP_VERTEX_SEARCH=0` 추가 → 글로벌 override |
| README-dev.md L1079 | 코드 변경 0줄, `agent/web_search.py:764` 토글 활용 |
| README-dev.md L1134-1148 | 글로벌 .env override=True 재로드 시 토픽 override 회귀 결함 + 진단 명령 |

### 5.3 결론

`SKIP_VERTEX_SEARCH=1` base 는 의도된 설정. vertex 가 필요한 토픽은 `topics/<slug>.env` 에서 `SKIP_VERTEX_SEARCH=0` 명시 override 가 운영 패턴.

---

## § 6. 부수 효과 박제 (★★★★★) — 정확화

### 6.1 §14-3 Tier 2 결과 재해석

- 메커니즘 결함 **아님**
- base policy (SKIP=1) + TOPIC_SLUG env var 미설정 결과
- 직전 박제 36 (메커니즘 부재 가능성 ★★★★) **부분 수정**

### 6.2 §14-2 Phase B 측정 재해석

- mean 294.75s 의 정상 측정 결과 = vertex 호출 안 한 상태
- Step 1b patch (5078a2d) 본 검증 = 양쪽 commit 모두 vertex 우회 측정
- patch 효과 측정 불가 = **재측정 필요**

### 6.3 Phase B 미스터리 재해석

- 직전 박제 ("PowerShell vs Bash tool 경유 차이로 정상/hang 분기") 부분 **약화**
- 사실: Phase B 정상 = vertex 우회 상태, mechanism 결함 발현 안 됨
- 진짜 mechanism 결함 검증은 vertex 호출 활성 상태에서 재진행 필요

### 6.4 logger 박제 chain 정확화

- L764 호출 분기 = silent (logger 부재 박제 67 유지)
- L813-814 skip 분기 = logger 존재 (`[web_search] Vertex skipped (SKIP_VERTEX_SEARCH=1)`)
- console.log 부재 = 시나리오 10/11 (§3)

---

## § 7. Phase 1 코드 리뷰 결손 6건 누적 박제

§14-3 진행 중 식별된 Phase 1 결손 6건 (env 파일 설정 + dry-run script TOPIC_SLUG 결손 포함).

상세 박제 + 향후 코드 리뷰 표준 항목 → `README-dev-2.md` 의 "디버깅 표준 박제 (영구 박제, §14-3 origin)" 섹션의 "Phase 1 코드 리뷰 결손 패턴 박제" 항목 참조.

---

## § 8. 분기 결정 (가) + 트랙 1 진입 plan (P-2)

### 8.1 분기 결정 (가) 확정

- SKIP_VERTEX_SEARCH=1 활성으로 vertex 호출 안 됨
- base policy 정합 (§12-19 운영 사례와 일관)
- 메커니즘 결함 아님 (Tier 2 결과 재해석)

### 8.2 트랙 1 진입 plan (P-2)

방향: **script 변경 없이 환경 변수 명시 설정** (글로벌 base policy 유지).

작업 흐름:

1. `topics/ai-generated-creative-ad-platforms.env` 작성 (Tier 2 T4 토픽)
   - 내용: `SKIP_VERTEX_SEARCH=0` 명시 (글로벌 .env override)
   - (선택) `TOPIC_TITLE`, `LLM_PROVIDER` 등 토픽별 메타 추가

2. dry-run 실행 명령 보강:
   ```powershell
   $env:PYTHONIOENCODING="utf-8"
   $env:LOCAL_RAG_ALLOW_EMPTY="1"
   $env:TOPIC_SLUG="ai-generated-creative-ad-platforms"  # ★ 신규
   & "...python.exe" "..._step3_dry_run_rag_update.py" `
     --topic-slug "ai-generated-creative-ad-platforms" `
     --topic-title "..." `
     --trigger "..." `
     --output "..." `
     --recursion-limit 100 `
   2>&1 | Tee-Object -FilePath "..."
   ```
   - `$env:TOPIC_SLUG` 명시로 core.config `_apply_topic_preset` 활성
   - `topics/<slug>.env` 의 SKIP=0 override 적용

3. T4 dry-run 재실행 → vertex_grounding > 0 도달 확인

4. console.log 의 vertex 호출 분기 진입 여부 검증 (L764 silent 이나 LLM 호출 latency 변화로 추정 가능)

### 8.3 P-2 결과 분기

| 결과 | 다음 단계 |
|------|----------|
| (가) vertex_grounding > 0 도달 | §14-2 Step 1b patch 본 검증 valid 조건 확보, Phase 3 진입 가능 |
| (나) vertex_grounding = 0 유지 | 시나리오 10/11 검증 트랙 진입 |
| (다) vertex 호출되나 grounding 0 | 가설 B (Phase A 단독 vs graph 통합 대조) 활성 검증 |

---

## § 9. §14-2 측정 재검증 트랙 plan (별도 sub-step)

### 9.1 미션

- Phase A 단독 baseline 측정의 SKIP_VERTEX 우회 사실 확인
- Phase B 측정 결과 재해석 (vertex 우회 상태)
- Step 1b patch 본 검증 재측정 필요성 판단

### 9.2 방법

- Phase A `dump_vertex_grounding.py` 코드 review + env load 흐름 박제
- Phase B `measure_vertex_phase_b.py` 의 env capture 결과 재확인
- Step 1b patch 영향 분석: vertex_grounding 누적이 측정됐는지 검증

### 9.3 진입 조건

- §14-3 (NEW)-B 트랙 1 (P-2) 완료 후 진입
- 또는 §14-2 보조 트랙으로 분리 (의사결정 필요)

---

## 부록 A. 참고 파일

- `agent/web_search.py:764, 813-814, 1088`
- `agent/supervisor.py:608-619`
- `core/config.py:106-128, 153, 163, 167, 246, 250, 477`
- `scripts/_step3_dry_run_rag_update.py:43-46, 194`
- `.env`, `.env.vertex`, `.env.openai`
- `README-dev.md:1073-1148` (§12-19 트랙)
- `README-dev-§14.md` (§14-3 진행 + (NEW)-B 트랙)
- `scripts/output/§14-3/topic_selection.md` (Tier 2 dry-run 결과)
- `scripts/output/§14-3/_dry_run/T4_*.json, T5_*.json, T6_*.json`
- `scripts/output/§14-3/_dry_run/T4_*.console.log, T5_*.console.log, T6_*.console.log`
