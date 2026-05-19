# §academic-2 Step B design (clear_runtime_allowed_domains hook 도입)

> **박제 chain reference**
> - 직전: §academic-2 Step A entry audit (commit `a62c6d6`) + catch 50 가설 재작성 (commit `85579d2`)
> - 본 cycle 본 미션: catch 50 (gatekeep `_RUNTIME_ALLOWED` upstream 무효화 누락) 해소 — 토픽 전환 사이 `ALLOWED_DOMAINS_EXTRA` 가 새 토픽 web_search 진입 시점에 정상 반영되도록
> - 부수 미션: §academic-1 metric 2 (academic source ratio mean 0.0 REVIEW) 정량 회복 — fix 후 measurement 로 검증
> - 채택 후보: Step A A3 후보 **2** (clear_runtime_allowed_domains 신규 + reload_config_inplace hook)
> - 본 박제: read-only design. agent/ core/ 코드 수정 금지 (Step C 의 사용자 컨펌 후 영역)
> - **사용자 결정 박제 (2026-05-19 follow-up)**: docstring 6-line 명시 / **§academic-1 `scripts/§academic-1/measure_ab.py` 재사용** (신규 driver 작성 0) / business invariant Jaccard mean 1.0 strict / commit 분리 = fix 본체 단일 commit + 측정 결과 별도 + close 별도 — 상세는 B8

---

## B1 — design scope (본 미션 / 부수 미션 분리)

### 본 미션 (반드시 해소)
- `_RUNTIME_ALLOWED` global 이 토픽 전환 시점에 invalidate 되도록 hook 신설
- `set_runtime_allowed_domains` 의 "agent-driven runtime override" semantic 보존
- `refresh_gatekeep_cache` 기존 의도 (lru_cache 만 invalidate) 보존 — 다른 호출 site 의 부작용 0

### 부수 미션 (Step C 측정으로 검증)
- §academic-1 metric 2 (academic source ratio) 임계 0.6 회복
- business invariant (venfobel Jaccard 1.0) 회귀 없음

### 비범위 (defer)
- catch 47 mixed-lang routing 측정 (별 cycle)
- catch 46 academic prompt tone 분기 (별 cycle)
- vertex redirect resolve trade-off (driver default 90s — d4d6431 commit 으로 완료)

---

## B2 — `clear_runtime_allowed_domains()` 함수 spec

### 위치
`writer_project/settings_gatekeep.py:100` 직후 (현재 `set_runtime_allowed_domains` 함수 종단 다음 line) — 의도 인접성 (RUNTIME 관련 함수 cluster).

### Signature
```python
def clear_runtime_allowed_domains() -> None:
    """런타임 주입된 허용 도메인 set 을 초기화 (토픽 전환 hook).

    `set_runtime_allowed_domains` 가 박제한 snapshot 을 명시적으로 비워
    다음 `get_allowed_domains()` 호출이 ENV/CFG 로부터 fresh 재계산하도록 한다.

    부수 효과: `_normalized_allowed_domains` lru_cache 도 함께 clear
    (RUNTIME 변경은 lru_cache 정합성에도 영향이므로 invariant 보존).
    """
    global _RUNTIME_ALLOWED
    _RUNTIME_ALLOWED = set()
    try:
        _normalized_allowed_domains.cache_clear()
    except Exception:
        pass
```

### 본문 line count (catch 48 산식 분리)
- def signature 1 line
- docstring 6 line (1 line 으로 압축 시 -5 — 본 spec 은 명시적 6 line 채택)
- global 선언 1 line
- 본문 (`_RUNTIME_ALLOWED = set()`) 1 line
- side-effect try/except 4 line
- **합계: 함수 본체 12 line + def 1 line = 13 line**

### 압축 옵션 (docstring 1-line 으로 단축 시)
- def + 1-line docstring + global + clear + try/except = **+8 line**
- 절감 −5 line 대가로 의도 박제 (docstring) 손실 → **명시 6-line docstring 채택 권장** (catch 50 박제 chain 의 부족하지 않은 readability 가 다른 cycle 의 reader 에게 의도 전달)

### lru_cache invalidate side-effect 포함 결정
- **포함 채택** — RUNTIME clear 후 lru_cache 가 prev RUNTIME snapshot 으로 박제되어 있으면 invariant 깨짐. clear 직후 lru_cache 도 clear 가 정합.
- 단, 본 hook 의 호출 site (B3) 가 `reload_config_inplace` 이고 그 함수가 이미 `refresh_gatekeep_cache()` 를 호출 (core/config.py:692-696) → lru_cache 는 두 번 clear (clear 는 idempotent 라 무해). side-effect 명시는 함수 단독 호출 안전성을 위한 defensive.

---

## B3 — `reload_config_inplace` hook spec (core/config.py)

### 위치
`writer_project/core/config.py:696` (현재 `refresh_gatekeep_cache()` 호출 직후) — 동일 try/except 블록 내 인접 호출.

### 변경 diff (preview)
```python
# 현재 (L692-696):
try:
    from settings_gatekeep import refresh_gatekeep_cache
    refresh_gatekeep_cache()
except Exception:
    pass

# 변경 후:
try:
    from settings_gatekeep import refresh_gatekeep_cache, clear_runtime_allowed_domains
    refresh_gatekeep_cache()
    clear_runtime_allowed_domains()
except Exception:
    pass
```

### hook insert line count (catch 48 산식)
- import line 변경: 0 (기존 import 의 `, clear_runtime_allowed_domains` 추가) — **net 0 line** (in-place edit)
- 호출 line 추가: **+1 line** (`clear_runtime_allowed_domains()`)

### 위치 선정 사유
- `refresh_gatekeep_cache()` 직후 → 동일 try/except 보호 (실패 시 silent fallback, 기존 §14-9-W Step C 컨벤션 정합)
- 동일 import 블록 → settings_gatekeep 모듈 의존성 cluster 유지
- `_apply_topic_preset` (L688) 직후 + 새 CFG mutation (L697-699) 사이 → 토픽 env 적용 후 / CFG 변경 후 둘 다 정합

---

## B4 — `__all__` 등록 (기타)

### 위치
`writer_project/settings_gatekeep.py:385-396` `__all__` list

### 변경
```python
# L388 `set_runtime_allowed_domains` 다음 line 에 추가:
"set_runtime_allowed_domains",
"clear_runtime_allowed_domains",   # ← +1 line
"gatekeep_enabled",
```

### 등록 사유
- 본 hook 이 `core/config.py` (외부 모듈) 에서 import 됨 → public API 박제 정합
- 향후 다른 진입점 (예: pytest fixture, 외부 script) 에서 직접 호출 가능성 보장

### 기타 line count: **+1 line**

---

## B5 — Total budget 산정 (catch 48 산식 검산)

| 항목 | line | 위치 |
|---|---|---|
| hook insert | **+1** | `core/config.py:696` (refresh_gatekeep_cache() 직후 `clear_runtime_allowed_domains()` 호출) |
| 함수 본체 (def + docstring + global + clear + side-effect try/except) | **+13** | `settings_gatekeep.py:100~` |
| config 변경 | 0 | (없음 — env / CFG dataclass field 변경 없음) |
| 기타 (`__all__` 등록 1 line + core/config.py import 줄 수정 net 0) | **+1** | `settings_gatekeep.py:385-396` |
| **net total** | **+15 line / -0** | |

### Step A A3 산정 (+7) 과의 diff
- Step A audit 의 후보 2 산정 = +7 (docstring 압축 1-line 가정)
- Step B 정식 spec = +15 (docstring 명시 6-line 채택 + side-effect try/except 4-line 포함)
- diff +8 (catch 48 lesson 재현 — Step A 의 산정은 spec 상세화 전 추정치). 실제 spec 박제 후 commit message 에 정합 명시 필요.

### 사용자 결정 #1 (Step C 진입 전)
- docstring 명시 6-line 채택 (권장) 또는 1-line 압축 (−5 line, +10 total)
- 권장 사유: 본 cycle catch 50 chain reader (향후 §academic 후속 cycle 또는 다른 cycle 작업자) 가 의도 (RUNTIME upstream + lru_cache 정합) 파악에 필요

---

## B6 — 부작용 + 회귀 위험 평가

### `set_runtime_allowed_domains` agent-driven override semantic 보존 검증
- 본 cycle 은 `reload_config_inplace` 한 site 에서만 `clear_runtime_allowed_domains` 호출 (다른 site = 0).
- agent 가 미래 `set_runtime_allowed_domains(custom_set)` 호출 후 토픽 전환이 없는 경우 → RUNTIME 보존 (`reload_config_inplace` 호출 없음 → clear 호출 안 됨) ✓.
- agent override 후 토픽 전환이 발생하면 → RUNTIME clear 됨 (의도 — agent override 는 토픽 단위 valid). 만약 agent override 가 토픽 전환을 가로질러 유지되어야 하면, agent 가 토픽 전환 hook 후 재주입해야 함 (기존 의도와 정합 — `set_runtime_allowed_domains` 는 caller 책임).

### `refresh_gatekeep_cache` 기존 호출 site 영향 = 0
- `app.py:2287-2288`: `refresh_gatekeep_cache()` 단독 호출 → RUNTIME 건드리지 않음 (기존 의도 유지) ✓
- `tools/web_rag/search.py:275-276` (module-level import-time): 동상 ✓
- `tools/web_rag/search.py:1366-1371` (request-time `reload_config()` + `refresh_gatekeep_cache()`):
  - `reload_config()` → `reload_config_inplace()` 호출 → **본 hook 의 신규 `clear_runtime_allowed_domains()` 도 실행**
  - 직후 `refresh_gatekeep_cache()` 호출 (idempotent)
  - 직후 L1413 `get_allowed_domains()` → RUNTIME 비어있음 → ENV/CFG 로부터 fresh 빌드 → 새 EXTRA 반영 ✓
  - 직후 L1417 `set_runtime_allowed_domains()` → fresh 값으로 RUNTIME 박제 ✓
- `agent/web_search.py:35` (import 만): 동상 ✓

### catch 47 (mixed-lang) 영향 = 0
- 본 fix 는 allowed domain set 정합 — query lang routing 과 직교. catch 47 sub-cycle 진입 시 본 fix 위에 별도 layer 로 도입 가능.

### catch 43 (MODE × lang matrix) 영향 = 0
- `effective_skip_vertex` 결정 (agent/web_search.py:733-744) 은 RUNTIME / allowed set 과 직교. business invariant Jaccard 1.0 보존 예상.

### 회귀 risk: ★☆☆ 낮음
- 변경 line 총 +15, hook site 단일 (`reload_config_inplace`), 다른 호출 site 영향 0.
- 단, `reload_config_inplace` 의 try/except 블록 (L692-696) 이 silent fallback 이라 hook 실패 시 stale RUNTIME 잔존 가능 — exception path 도 정합 (기존 §14-9-W Step C 컨벤션 따름).

---

## B7 — Step C 측정 plan (검증 spec)

### 측정 환경 standards (catch 49 lesson 정합, §academic-1 C-3 driver 재사용)

> **driver 재사용 결정 박제 (B8 사용자 결정 #2 정합)**: §academic-1 의 `scripts/§academic-1/measure_ab.py` 를 본 cycle Step C-2 측정에 **그대로 재사용**. 본 cycle 신규 driver 작성 = **0**. 신규 측정 driver 의 catch 49 lesson 재구현 / probe 재정착 / standards 재산정 일체 회피.

- `.venv_vertex` + `LLM_PROVIDER=vertexai`
- max_retries=0 / warmup=2 / measure=3 (per topic) / per-run-timeout 90s (d4d6431 commit 정합) / inter-run-sleep 60s
- PYTHONIOENCODING=utf-8
- driver: `scripts/§academic-1/measure_ab.py` (위 driver 재사용 결정 박제 정합)

### 측정 지표 (5 metric 재현)
| # | 지표 | 검증 기준 (catch 50 fix 후) |
|---:|---|---|
| 1 | business invariant (venfobel Jaccard) | mean ≥ 0.7 + catch 43 bypass=True (§academic-1 PASS 1.0 유지 회귀 검증) |
| 2 | **academic source ratio** | **mean ≥ 0.6 (회복 검증)** — fix 핵심 metric |
| 3 | lang-detect accuracy | 10/10 = 100% (§academic-1 PASS 회귀 검증) |
| 4 | EN→vertex active | 3/3 = 100% (§academic-1 PASS 회귀 검증) |
| 5 | KO→naver active | skip 3/3 + naver_hit 3/3 (§academic-1 PASS 회귀 검증) |

### 추가 보조 지표 (RUNTIME invariant 검증)
- 각 topic 진입 시 `[GATEKEEP] allowed=... (n=N)` 로그 captures — academic-en n / academic-ko n 둘 다 ≥ 107 (78 base + 29 EXTRA, normalization 포함 시 ~108)
- venfobel n 78 부근 (EXTRA 없음 정합)
- `[GATEKEEP][DROP]` 로그에서 academic 도메인 (`kci.go.kr`, `dbpia.co.kr`, `kiss.kstudy.com` 등 ACADEMIC_DOMAINS_29 set) drop 0 검증

### 박제 chain
- raw: `scripts/output/§academic-2/c_verification.json` (.gitignored)
- run log: `scripts/output/§academic-2/c_verification_run.log` (.gitignored)
- 정식 박제: `scripts/output/§academic-2/step_c_impl_measurement.md`

---

## B8 — Step C 진입 조건 (사용자 결정 박제 — 2026-05-19)

본 Step B design 박제 commit (`33f0cf0`) 후 사용자 결정 완료:

1. **docstring 정책** (B5 사용자 결정 #1): **6-line 명시** 채택 (총 +15 line). 사유: 코드 인라인 의도 명확화 우선 (catch 50 chain reader / 향후 cycle 작업자 의도 파악).
2. **Step C 측정 driver**: **기존 `scripts/§academic-1/measure_ab.py` 재사용** 채택. 신규 driver 작성 0. 박제 정합: 본 design B7 "driver 재사용 결정 박제" 1줄 명시 추가 (본 follow-up commit).
3. **business invariant 회귀 검증**: **Jaccard mean 1.0 strict** 채택. 사유: 부작용 즉시 감지 우선 — 임계 ≥0.7 완화 시 회귀 감지 지연 risk.
4. **fix 적용 commit 분리**:
   - **fix 본체** = 단일 commit (B2 함수 + B3 hook + `__all__` 묶음 — `settings_gatekeep.py` + `core/config.py` 동시)
   - **측정 결과** = 별도 commit (`scripts/output/§academic-2/step_c_*.md`)
   - **close** = 별도 commit (README §academic-2 track close 표기)

본 결정 박제 정합 — Step C 진입 OK (사용자 컨펌 OK).

---

## Self-check protocol

- [x] catch 48 lesson budget 산식 (4 항목 별도 카운트) 적용 — B5 표에 hook + 함수 본체 + config + 기타 명시
- [x] 본 미션 / 부수 미션 분리 (scope creep 경고 memory 정합) — B1 명시
- [x] read-only — agent/ core/ 코드 수정 없음, 본 박제 file (`step_b_design.md`) 신규만
- [x] catch 50 가설 재작성 (commit `85579d2`) 정합 — 본 design 의 hook 위치·함수 spec 가 가설 정합
- [x] §14-9-W Step C 컨벤션 (try/except silent fallback) 정합 — B3 diff preview 정합
- [x] 권장안 사유 명시 (B6 부작용 평가, B2 docstring 채택 사유) — agent-driven override semantic 보존 + reader readability
- [x] git status 깨끗 (본 design.md 외 변경 없음) — `git status --short` 결과 `writer_project/scripts/output/§academic-2/step_b_design.md` 만 신규 untracked (다른 untracked 는 cycle 진입 시점부터 잔존)

---

## STOP — Step C 진행 중 자율 진행 한계 (2026-05-19 사용자 추가 명시)

### STOP-1 (해소됨 — 2026-05-19)
- B8 의 4개 사용자 결정 (docstring / driver 재사용 / 회귀 임계 / commit 분리) 컨펌 완료
- Step C-1 진입 OK (단, 사용자 측 `git push origin main` 별도 처리 후)

### STOP-2 (해소됨 — Step A audit 단계)
- catch 50 가설 재작성 사용자 컨펌 완료 (commit `85579d2`)

### STOP-3 (활성 — Step C-1 fix 구현 완료 후)
- `settings_gatekeep.py` (B2 함수 + B4 `__all__`) + `core/config.py` (B3 hook) 수정 후 `git diff` + budget 산정 자체 검산 (catch 48 산식 정합 = net +15) 보고
- diff 사용자 컨펌 전까지 fix 본체 commit 금지
- 자율 측정 driver 실행 금지 (STOP-3 통과 후 진입)

### STOP-4 (활성 — Step C-2 측정 실행 완료 후)
- §academic-1 driver (`scripts/§academic-1/measure_ab.py`) 실행 → 5 metric + `[GATEKEEP] n` 보조 지표 결과 raw 박제 후 사용자 컨펌
- 본 미션 (metric 2 academic source ratio ≥ 0.6) + business invariant (Jaccard mean 1.0 strict) 둘 다 충족 검증
- 결과 컨펌 전까지 측정 결과 박제 doc commit 금지
- **자율 close 진행 금지** — STOP-4 통과 후 close commit 진입 (README §academic-2 track close 표기)

### close 진입 조건 (STOP-4 통과 후)
- step_c_impl_measurement.md 박제 완료
- 5 metric 결과 정합 + 부수 미션 (academic source ratio 회복) 정량 박제
- 사용자 close 컨펌 후 별도 commit ("§academic-2 close — README §academic-2 track 정식 close 표기")
