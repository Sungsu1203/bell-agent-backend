# §academic-2 Step A entry audit

> **박제 chain reference**
> - 직전 cycle: §academic-1 close (commit `df12ffe` · branch `main`)
> - 본 audit 대상 catch: catch 50 (gatekeep `ALLOWED_DOMAINS_EXTRA` cache invalidation 결함)
> - root cause 근거 doc: `scripts/output/§academic-1/step_c_impl_measurement.md` 섹션 5 "Root cause B"
> - audit 범위: A1 (cache inspection) + A2 (topic switch flow) + A3 (fix surface estimate) — **read-only**
> - audit driver: 미사용 (grep + view 만으로 충분 — 신규 driver 작성 생략)
> - 환경: PowerShell · BOOK-DPUCVR08TC · HEAD = `df12ffe`

---

## A1 cache inspection

### 정의
- **cache 정의**: `writer_project/settings_gatekeep.py:187-203` — `_normalized_allowed_domains()`
- **형태**: `@lru_cache(maxsize=1)` (module-level function-scoped lru_cache)
- **key 구성**: 함수 인자 **0개** → 단일 slot. **topic id 포함 안 됨** (catch 50 결함 본체 기술과 정합)
- **lifetime**: process scope (lru_cache 는 module 객체 life 동안 유지)

### 본문 내부 의존
- `_normalized_allowed_domains()` 본문 (L188-203) → `get_allowed_domains()` 호출 (L190)
- `get_allowed_domains()` (`settings_gatekeep.py:138-155`):
  - L140-141: `if _RUNTIME_ALLOWED: return _RUNTIME_ALLOWED` — **상위 short-circuit** (ENV 읽기 우회)
  - L142: `_BASE_ALLOWED_DOMAINS` (코드 hard-coded base set)
  - L145-149: `_get_cfg_attr("ALLOWED_DOMAINS")` CFG 분기
  - L153: `os.getenv("ALLOWED_DOMAINS", "")`
  - L154: `os.getenv("ALLOWED_DOMAINS_EXTRA", "")` ← catch 50 표적

### invalidation 진입점
- `refresh_gatekeep_cache()` (`settings_gatekeep.py:128-134`)
  - L131: `_normalized_allowed_domains.cache_clear()`
  - L132: `_normalize_host.cache_clear()`
  - **`_RUNTIME_ALLOWED` 는 건드리지 않음** (settings_gatekeep.py 코드 검증)
- `set_runtime_allowed_domains()` (`settings_gatekeep.py:86-100`)
  - L90-92: `_RUNTIME_ALLOWED = {...}` 재대입 (빈 list 주입 시 빈 set → 효과적 clear)
  - L95-96: lru_cache 도 함께 clear (side-effect)

### `refresh_gatekeep_cache` 호출 사이트 (전수 grep)
1. `writer_project/app.py:2287-2288`
2. `writer_project/core/config.py:692-696` (reload_config_inplace 내부, §14-9-W Step C Gap 2 fix)
3. `writer_project/tools/web_rag/search.py:275-276` (module-level, import-time 1회)
4. `writer_project/tools/web_rag/search.py:1366-1371` (web_search 함수 entry, request-time)
5. `writer_project/agent/web_search.py:35` (import 만 — 호출은 별 라인)

---

## A2 topic switch flow

### env load entry point
- 측정 driver: `writer_project/scripts/§academic-1/measure_ab.py:208-241` (`load_topic_env`)
  - L222: `load_dotenv(.env, override=False)` — global .env (선재 로드 키 보호)
  - L224: `load_dotenv(topics/<slug>.env, override=True)` — 토픽 env override
  - L237: `reload_config_inplace()` 호출
- 토픽 dict: `measure_ab.py:150-172` — 순서 `business-venfobel → academic-en → academic-ko`
- 토픽 env 파일 (검증):
  - `topics/venfobel-vitamin.env:4` — `TOPIC_SLUG=venfobel-vitamin` (ALLOWED_DOMAINS_EXTRA 없음)
  - `topics/academic-influencer-marketing-consumer-behavior.env:9,16` — slug + EXTRA 29 entries
  - `topics/academic-genz-mobile-ad-acceptance.env:9,16` — slug + EXTRA 29 entries

### propagation chain (driver → config → gatekeep)

```
[driver layer]  measure_ab.py:208 load_topic_env()
                ├─ L222 load_dotenv(.env, override=False)
                ├─ L224 load_dotenv(topics/<slug>.env, override=True)
                │       → os.environ[ALLOWED_DOMAINS_EXTRA] = <topic value>
                │       → os.environ[TOPIC_SLUG] = <new slug>
                └─ L237 reload_config_inplace()
                          │
[config layer]            ▼  core/config.py:667 reload_config_inplace()
                ├─ L677 _saved_env = snapshot(_PROTECTED_ENV_KEYS)
                │       (TOPIC_SLUG, LLM_PROVIDER, LLM_MODEL, SKIP_VERTEX_SEARCH, MIRROR_STATE_TO_ENV)
                │       — ALLOWED_DOMAINS_EXTRA 는 PROTECTED 가 아님
                ├─ L679 load_dotenv(find_dotenv(usecwd=True), override=True)
                │       → .env 의 키만 override (EXTRA 는 .env 에 없으므로 무변경)
                ├─ L683-685 restore _saved_env (TOPIC_SLUG 등 driver 의도 복원)
                ├─ L687 _apply_provider_overlay() → .env.vertex override=True
                │       (.env.vertex 에 EXTRA 없음 → 무변경)
                ├─ L688 _apply_topic_preset() → topics/<TOPIC_SLUG>.env override=True
                │       → os.environ[ALLOWED_DOMAINS_EXTRA] 재확정
                ├─ L697 _build_config() + L698-699 in-place CFG mutation
                └─ L692-696 refresh_gatekeep_cache()
                          │
[gatekeep layer]          ▼  settings_gatekeep.py:128 refresh_gatekeep_cache()
                ├─ L131 _normalized_allowed_domains.cache_clear()  ← lru_cache invalidate ✓
                └─ L132 _normalize_host.cache_clear()
                          (※ _RUNTIME_ALLOWED 는 건드리지 않음 — A3 후보 1·2 의 표적)

[request-time]  measure_ab.py:350 web_search.invoke()
                ├─ tools/web_rag/search.py:1367 reload_config() → reload_config_inplace (재호출)
                ├─ tools/web_rag/search.py:1368-1369 refresh_gatekeep_cache() (재호출)
                ├─ tools/web_rag/search.py:1413 allowed_domains = sorted(get_allowed_domains())
                │       → settings_gatekeep.py:140-141 short-circuit
                │         if _RUNTIME_ALLOWED: return _RUNTIME_ALLOWED   ← stale snapshot 가능
                ├─ tools/web_rag/search.py:1415-1416 logger "[GATEKEEP] allowed=... (n=N)"
                └─ tools/web_rag/search.py:1417 set_runtime_allowed_domains(allowed_domains)
                        → _RUNTIME_ALLOWED 재대입 (이 시점에서 stale 이면 stale 채로 박힘)
```

### cache build 시점 vs env 로드 시점 ordering
- env load (`_apply_topic_preset`, L688) **선행** → refresh (L692-696) **후행**: lru_cache 관점에서는 정합 (clear 후 next read 시 fresh 빌드)
- 그러나 `_RUNTIME_ALLOWED` 는 `refresh_gatekeep_cache` 가 건드리지 않으므로, `set_runtime_allowed_domains` (search.py:1417) 가 직전 토픽의 snapshot 으로 채워두면, 새 토픽 web_search 진입 시 `get_allowed_domains` 가 ENV 를 우회한 채 stale RUNTIME 을 반환 → 새 토픽의 `ALLOWED_DOMAINS_EXTRA` 무시.

### 정리
- catch 50 entry 의 "cache invalidation 결함" 표현은 `_normalized_allowed_domains` lru_cache 를 지칭. **이 lru_cache 자체의 invalidation hook 은 §14-9-W Step C 에서 추가되어 작동** (core/config.py:692-696).
- 그러나 `_RUNTIME_ALLOWED` 라는 **상위 layer (priority 1) 의 cache-like global state** 가 invalidation 범위 밖. 이 global 이 `web_search.invoke` 시점에 직전 토픽 snapshot 으로 채워져 새 토픽 ENV 변경을 가린다.
- 즉 결함의 본체는 "lru_cache 무효화 누락" 이 아니라 **"upstream `_RUNTIME_ALLOWED` 가 토픽 전환 사이 invalidate 안 됨"**.

---

## A3 fix surface estimate

> budget 산정 컨벤션 (catch 48): `hook insert` + `함수 본체` + `config 변경` + `기타 (__all__ / docstring 등)` 항목별 별도 카운트.

| 후보 | 위치 | hook 방식 | 침습 면적 (line) | 부작용 위험 |
|---|---|---|---|---|
| **1** | `settings_gatekeep.py:128-134` `refresh_gatekeep_cache()` 본문 | 기존 함수에 `_RUNTIME_ALLOWED.clear()` 1줄 추가 (+ global 선언) | hook insert 0 + 함수 본체 **+2** + config 0 + 기타 0 = **+2** | ★★☆ `refresh_gatekeep_cache` 호출 사이트 5개 모두에서 RUNTIME 까지 초기화 — `set_runtime_allowed_domains` (agent-driven runtime override 의도) 의 기존 semantic 과 결합 시 부작용 가능. 단, grep 상 `set_runtime_allowed_domains` 호출 site 는 `tools/web_rag/search.py:1417` 단일 → 실제 영향 한정. |
| **2** | (a) `settings_gatekeep.py` 본문 신규 함수 + (b) `settings_gatekeep.py:385` `__all__` 등록 + (c) `core/config.py:694` 후 신규 hook 호출 | 신규 `clear_runtime_allowed_domains()` 정의 + `reload_config_inplace` 에서 명시 호출 | hook insert (c) **+2** (try/except) + 함수 본체 (a) **+4** (def 시그니처 + docstring 1줄 + global + clear) + config 0 + 기타 (b) **+1** (`__all__`) = **+7** | ★☆☆ 의도 명시적 (신규 entry point) — `refresh_gatekeep_cache` 기존 semantic 보존. 다만 향후 다른 진입점 (app.py, search.py 등) 에서 토픽 전환 hook 누락 시 RUNTIME stale risk 잔존 — 단일 hook site (reload_config_inplace) 보장 시 충분. |
| **3** | `settings_gatekeep.py:140-141` `get_allowed_domains()` 상단 short-circuit 제거 → ENV/CFG union | 정책 변경 (short-circuit → merge) | hook insert 0 + 함수 본체 **+1 / -2** (net **-1**) + config 0 + 기타 0 = **net -1** | ★★★ §14-9-W cycle 의 "런타임 주입 > CFG > ENV" priority 의도 자체 변경 — `set_runtime_allowed_domains` docstring (L87 "에이전트가 계산한 허용 도메인을 런타임으로 주입") 과 충돌. 다른 cycle 박제 부정합. **권장 안 함**. |

### 권장안: 후보 **2** (`clear_runtime_allowed_domains` + `reload_config_inplace` hook)

**사유**:
1. **semantic 분리**: `refresh_gatekeep_cache` 의 기존 의도 ("lru_cache 무효화") 와 새 hook 의 의도 ("RUNTIME global invalidate") 가 별도 entry 로 명시적 분리 → 향후 코드 reader 가 의도 파악 용이.
2. **agent-driven runtime override 의도 보존**: 후보 1·3 과 달리 `set_runtime_allowed_domains` 의 "agent 가 동적으로 set 후 단독 사용" semantic 을 망가뜨리지 않음. RUNTIME 의 사용 의도 (agent 결정 우선) 와 invalidation 의도 (토픽 전환 시 초기화) 가 분리 가능.
3. **침습 면적 적정**: 총 +7 line (catch 48 산식 4 항목 명시) — Step B design 박제 정합 budget.
4. **hook 호출 site 단일화**: `reload_config_inplace` 한 자리에 두면 `app.py:2287`, `search.py:1366-1371` 등 부수 호출 site 는 그대로 lru_cache 만 invalidate (기존 의도 유지) — 다른 cycle 영향 최소.

**잔존 risk** (Step B 에서 다룰 항목):
- `web_search.invoke` (search.py:1366-1371) 의 reload_config + refresh_gatekeep_cache 재호출 chain 이 `reload_config_inplace` 의 hook 을 재실행 → RUNTIME 한 번 더 clear → L1413 에서 ENV 로부터 fresh 재계산 → L1417 에서 재주입 ✓ (정합).
- 단, `set_runtime_allowed_domains` 의 미래 사용처 (현재는 search.py:1417 단일) 추가 시, RUNTIME 이 의도적으로 stale 유지되어야 하는 경로 (예: 사용자 강제 override) 와 충돌 가능 — Step B 설계 시 명시.

---

## Audit summary

### catch 50 root cause 가설 정합: **부분 정합 + 보강 layer 발견**

| 항목 | 박제 doc 가설 | A1·A2 실측 |
|---|---|---|
| 결함 위치 | "gatekeep `ALLOWED_DOMAINS_EXTRA` cache invalidation 결함 — `_normalized_allowed_domains` lru_cache 에 반영 안 됨" | lru_cache 자체의 invalidation hook 은 §14-9-W Step C 에서 추가되어 작동 (`core/config.py:692-696`) — 정합 |
| 무효화 누락 사실 | "`reload_config_inplace` 가 `refresh_gatekeep_cache()` 호출함에도 토픽 전환 사이 cache 무효화 누락" | `_normalized_allowed_domains` 는 무효화됨. 다만 **upstream `_RUNTIME_ALLOWED` global 이 `refresh_gatekeep_cache` 범위 밖** → 토픽 전환 사이 stale snapshot 잔존 — **가설에 추가 layer 발견** |
| 증거 (n=108/79 drop) | step_c_impl_measurement.md L155-160 (raw 측정 데이터 인용) | 본 audit 시점 `c_ab_run.log` 는 dry_run 만 잔존 (실측 raw 부재) — 정량 재현 불가, 박제 doc 진술 신뢰 |

**STOP-2 trigger 여부**: ◐ 부분 trigger.
- 가설의 "cache invalidation 결함" 진술은 lru_cache 만 가리키는 협의 해석으로는 부정확하나, 광의 해석 ("gatekeep allowed set 의 cache-like state 가 토픽 전환 사이 stale") 으로는 정합.
- 본 audit 의 보강 발견 (`_RUNTIME_ALLOWED` 별도 layer) 은 박제 doc 가설을 **반증** 하지 않고 **세분화** 함.
- 자율 수정 / Step B 자체 진입 금지 (STOP-2) — 사용자 판단으로 (a) 본 audit 정합 수용 후 Step B 진입 또는 (b) 가설 재작성 후 catch 50 entry 갱신 결정 필요.

### Step B 진입 조건 충족 여부: **YES (사용자 컨펌 후)**

- A1 cache definition + invalidation entry 식별 완료
- A2 topic switch propagation chain 추적 완료 (driver → config → gatekeep + request-time)
- A3 fix surface 후보 3개 + 권장안 1개 + 침습 면적 catch 48 산식 적용

---

## Self-check protocol

- [x] 모든 위치 표기가 `file:line` 실제 형식 — settings_gatekeep.py:187-203 / settings_gatekeep.py:128-134 / settings_gatekeep.py:138-155 / core/config.py:667-700 / measure_ab.py:208-241 / tools/web_rag/search.py:1366-1417 등 전부 실측
- [x] A1 cache 정의 위치가 실제 코드에서 grep 으로 확인 (grep `_normalized_allowed_domains` → `settings_gatekeep.py:187-203` 정합)
- [x] A3 후보별 침습 면적이 catch 48 컨벤션 (4 항목 별도 카운트) 따름 — hook + 함수 본체 + config + 기타 모두 명시
- [x] git status 깨끗 — 본 박제 file (`scripts/output/§academic-2/step_a_entry_audit.md`) 외 변경 없음 (audit 진입 시점부터 잔존하던 untracked 외 신규 변경 0 · `git status --short` 정합 확인)
- [x] catch 표기 시 1줄 description 병기 — "catch 50 (gatekeep `ALLOWED_DOMAINS_EXTRA` cache invalidation 결함)" 본문 일관 적용
