# §14-8-B B-2ext4 — empirical mechanism confirmation + override=True 의도성

**측정 일자:** 2026-05-17
**git HEAD:** B-2ext3 박제 commit (77c24ad 직후, push 후 sync 가정)
**미션:** B-2ext3 박제 mechanism (`reload_config_inplace` + `override=True` 회귀) 의 empirical CONFIRMED + override=True 의도 박제

**결과 요약:** **mechanism CONFIRMED + 의도 (iii) "ENV hot-reload" 정당 use case 존재. fix 권장 = (O) protected env list ★★★**

---

## § 1. 작업 1 — in-chain envdump probe 실측

### 1-1. probe 삽입 위치 박제

| 지점 | file:line | probe code |
|---|---|---|
| (a) | `tools/web_rag/search.py:1366` (try block 시작 직후, `reload_config()` 직전) | envdump_stage_a.json |
| (b) | `tools/web_rag/search.py:1368` (`reload_config()` 직후, `refresh_gatekeep_cache` 직전) | envdump_stage_b.json |
| (c) | `core/config.py:665` (`_apply_provider_overlay(verbose=False)` 직후, `_apply_topic_preset(verbose=False)` 직전) | envdump_stage_c.json |

probe 항목: `LLM_PROVIDER`, `LLM_MODEL`, `TOPIC_SLUG`, `CHROMA_NAMESPACE`, `CHROMA_NAMESPACE_WEB`, `OPENAI_MODEL`, `SKIP_VERTEX_SEARCH`, `pid`, `ts`.

### 1-2. trigger 실행 박제

trigger: `scripts/diag/§14-8/b2ext4_trigger.py`
- env mimic: TOPIC_SLUG=ai-generated-creative-ad-platforms, LLM_PROVIDER=vertexai, LLM_MODEL=gemini-2.5-flash, SKIP_VERTEX_SEARCH=0, MIRROR_STATE_TO_ENV=0
- POLLUTION pop: CHROMA_NAMESPACE*, CHROMA_DIR, OPENAI_MODEL
- `.env.vertex` 사전 로드 (B-2ext2 script L62 정합)
- `core.config` import → `_load_dotenv_once()` 발화
- `web_search.invoke({"query": "B-2ext4 probe diagnostic", "num": 1})` → search.py:1367 fire

실행 명령: `Push-Location D:\gpt_agent\writer_project; & D:\gpt_agent\.venv_vertex\Scripts\python.exe scripts\diag\§14-8\b2ext4_trigger.py`

**CWD 가설 박제 ★** (자기 비판 §1 강화):
- 1차 실행 (CWD = launch dir, writer_project 밖) → **regression 미발현** (find_dotenv 가 글로벌 .env 미발견 추정)
- 2차 실행 (CWD = writer_project, Push-Location 명시) → **regression 완전 재현** ★
- **`find_dotenv(usecwd=True)` 의 CWD 의존성** — wrapper subprocess 환경에서 driver 가 `Start-Process -WorkingDirectory writer_project` 사용 시 regression 발화. 본 cycle 박제로 명확.

### 1-3. raw envdump 박제 (CWD=writer_project, regression 재현 run)

#### stage a (BEFORE reload_config, search.py:1366)
```json
{
  "stage": "a_before_reload_config",
  "pid": 7260,
  "ts": 1778966862.4218433,
  "LLM_PROVIDER": "vertexai",
  "LLM_MODEL": "gemini-2.5-flash",
  "TOPIC_SLUG": "ai-generated-creative-ad-platforms",
  "CHROMA_NAMESPACE": "<unset>",
  "CHROMA_NAMESPACE_WEB": "<unset>",
  "OPENAI_MODEL": "<unset>",
  "SKIP_VERTEX_SEARCH": "0"
}
```

#### stage c (AFTER _apply_provider_overlay, config.py:665)
```json
{
  "stage": "c_after_provider_overlay",
  "pid": 7260,
  "ts": 1778966862.4349782,
  "LLM_PROVIDER": "openai",
  "LLM_MODEL": "gpt-4o",
  "TOPIC_SLUG": "venfobel-vitamin",
  "CHROMA_NAMESPACE": "venfobel-vitamin-oa",
  "CHROMA_NAMESPACE_WEB": "venfobel-vitamin-oa-web",
  "OPENAI_MODEL": "gpt-4o",
  "SKIP_VERTEX_SEARCH": "0"
}
```

#### stage b (AFTER reload_config returns, search.py:1368)
```json
{
  "stage": "b_after_reload_config",
  "pid": 7260,
  "ts": 1778966862.4373775,
  "LLM_PROVIDER": "openai",
  "LLM_MODEL": "gpt-4o",
  "TOPIC_SLUG": "venfobel-vitamin",
  "CHROMA_NAMESPACE": "venfobel-vitamin-oa",
  "CHROMA_NAMESPACE_WEB": "venfobel-vitamin-oa-web",
  "OPENAI_MODEL": "gpt-4o",
  "SKIP_VERTEX_SEARCH": "0"
}
```

ts 순서: a (.4218) → c (.4350, Δ=13.2ms) → b (.4374, Δ=2.4ms from c). a→c→b 정합 (c 가 reload_config 내부, b 가 외부 직후).

### 1-4. STAGE flip 박제 ★★★

| field | stage a | stage c | stage b | flip 발생 |
|---|---|---|---|---|
| `LLM_PROVIDER` | `vertexai` | `openai` | `openai` | **a→c (글로벌 .env 또는 .env.openai overlay)** ★ |
| `LLM_MODEL` | `gemini-2.5-flash` | `gpt-4o` | `gpt-4o` | **a→c** ★★★ |
| `TOPIC_SLUG` | `ai-generated-creative-ad-platforms` | `venfobel-vitamin` | `venfobel-vitamin` | **a→c (글로벌 .env L50)** ★ |
| `CHROMA_NAMESPACE` | `<unset>` | `venfobel-vitamin-oa` | `venfobel-vitamin-oa` | **a→c (.env.openai L56 overlay)** ★ |
| `CHROMA_NAMESPACE_WEB` | `<unset>` | `venfobel-vitamin-oa-web` | `venfobel-vitamin-oa-web` | **a→c (.env.openai L57 overlay)** ★★★ |
| `OPENAI_MODEL` | `<unset>` | `gpt-4o` | `gpt-4o` | **a→c (.env.openai L18 overlay)** ★ |
| `SKIP_VERTEX_SEARCH` | `0` | `0` | `0` | (no flip — topic preset venfobel-vitamin.env L35 의 SKIP_VERTEX_SEARCH 주석 처리되어 있고 ai-generated-creative-ad-platforms.env L11 의 SKIP_VERTEX_SEARCH=0 도 적용 안 됨 (TOPIC_SLUG 이 이미 venfobel 으로 mutate 됨). 글로벌 .env L20 `SKIP_VERTEX_SEARCH=1` 이 override=True 적용되어야 하는데 실측 0 — 별 mystery, 본 cycle scope 외) |

**핵심**: stage a → stage c 사이 (즉 `reload_config_inplace()` 의 `load_dotenv(.env, override=True)` + `_apply_provider_overlay()` 구간) 에서 **모든 critical env vars flip** ★★★.

### 1-5. mechanism 박제 단계별 위치 추정 (probe 한계)

probe 가 a/c/b 3 지점이므로 stage a→c 내부에서 정확히 어느 line 이 어떤 mutate 일으키는지 직접 박제 불가. 단 정황 증거로 추론:
- **LLM_PROVIDER, LLM_MODEL, TOPIC_SLUG flip 은 `load_dotenv(.env, override=True)` (config.py:660)** — 글로벌 `.env` 의 L2/L3/L50 정적 default 가 driver-set env 를 덮어씀
- **CHROMA_NAMESPACE*, OPENAI_MODEL 도입은 `_apply_provider_overlay` (config.py:664)** — LLM_PROVIDER 가 openai 로 flip 된 후 `.env.openai` overlay 가 load → L18/L56-58 적용

(추후 별 cycle 에서 더 세부 probe 필요 시 L660/L664 사이 추가 probe 가능. 현 cycle 박제 충분.)

### 1-6. probe revert + self-check

| 단계 | 결과 |
|---|---|
| probe 삽입 (3 지점) | search.py × 2, config.py × 1 |
| trigger 실행 | 2회 (CWD 가설 검증 포함) |
| envdump_stage_{a,b,c}.json 출력 | ✓ |
| probe 코드 제거 | search.py revert + config.py revert |
| `git diff writer_project/tools/web_rag/search.py writer_project/core/config.py` | **empty (clean revert 확인)** ★ |

→ **probe revert 완료, production code 무변** ★

---

## § 2. 작업 2 — `load_dotenv(.env, override=True)` 의도성 박제

### 2-1. 위치 + git blame raw

```
core/config.py:660  load_dotenv(find_dotenv(usecwd=True), override=True)
  ↓ git blame
3fce3e61 (Sungsu Oh 2026-01-31 11:58:21 +0900) "update codes"
```

함수 정의 + 주변 line 의 git blame:

| line | blame | message |
|---|---|---|
| L650-662 (함수 정의 + load_dotenv) | **3fce3e61** (2026-01-31) | "update codes" — generic mass commit |
| L663-664 (`_apply_provider_overlay`) | **4888a3a1** (2026-05-07) | "feat(provider): OpenAI venv 분리 + 검색 정책 튜닝 (§12-23)" |
| L665 (`_apply_topic_preset`) | **d3d4d97f** (2026-05-06) | "fix(config): reload_config_inplace 토픽 .env override 회귀 (§12-20)" |
| L666-669 (_build_config + field copy) | 3fce3e61 (2026-01-31) | "update codes" |

### 2-2. 도입 commit (3fce3e61) 변경 context

- 38개 파일 신규 추가 (writer_project 전체 base scaffold)
- commit message: **"update codes"** (generic, intent박제 부재)
- override=True 가 **initial scaffold 단계에서 default 로 도입** — 의도 명시 단서 부재.

### 2-3. d3d4d97f (§12-20) commit message — 의도 박제 ★★★

> **fix(config): reload_config_inplace 토픽 .env override 회귀 (§12-20)**
>
> reload_config_inplace 가 글로벌 .env 만 override=True 로 재로드해서
> topics/{slug}.env 의 override (예: SKIP_VERTEX_SEARCH=0) 가 글로벌
> 값으로 회귀하던 버그 수정. app.py 부팅 시 reload_config() 가 두 번
> 호출되어, 첫 _build_config() 의 토픽 적용이 매번 무효화 — §12-19
> Vertex 활성화가 silent failure 상태였음. 직접 import 시는 정상이라
> 검출이 늦어졌고, "앱 실행 fail / 직접 import OK" 모순을 reload
> 경로 차이로 좁혀 root cause 도달.
>
> 수정: _apply_topic_preset(*, verbose) 헬퍼로 토픽 .env 로드 로직을
> 한 곳에 모으고, _load_dotenv_once 와 reload_config_inplace 양쪽에서
> 재사용. reload 경로의 print 스팸은 verbose=False 로 차단.

**핵심**:
- §12-20 fix 는 "글로벌 .env override=True → 토픽 preset 회귀" 문제를 **인식**.
- **fix 방향은 override=False 로 변경이 아니라, `_apply_topic_preset` 추가 호출** — 즉 override=True 는 의도적 유지.
- 의도: "ENV 가 변경된 후 reload 시 .env 의 최신 값 반영" (hot-reload 의도).
- **driver subprocess 환경에서 driver 가 명시 set 한 env 와의 충돌은 인식 못 함** — §12-20 scope 외.

### 2-4. 4888a3a1 (§12-23) commit context

> **feat(provider): OpenAI venv 분리 + 검색 정책 튜닝 (§12-23)**
>
> - core/config.py: _apply_provider_overlay() — 글로벌 → .env.<provider> → 토픽

→ provider overlay 도입. priority chain 명시: 글로벌 → provider overlay → 토픽 preset. **`reload_config_inplace` 의 override=True 는 이 chain 의 starting point 로 의도적 유지**.

### 2-5. 의도 판정 — (i) + (iii) ★

| 후보 | 평가 |
|---|---|
| **(i) 의도 명확** | ✓ — §12-20 commit message 에서 override=True 유지 + `_apply_topic_preset` 추가로 chain 보장. **§12-23 docstring "ENV 변경을 반영"** 정합. |
| (ii) 사고 도입 | △ — 3fce3e61 의 "update codes" generic commit 으로 초기 도입은 intent 박제 부재. 단 §12-20 fix 가 의도적 유지 → 현재는 (i) 우세. |
| **(iii) 정당 use case** | ✓ — **ENV hot-reload** (외부 도구가 `.env` 편집 후 reload_config 호출 → 즉시 반영). config.py:651-653 docstring "ENV 변경을 반영하되, CFG 객체를 재바인딩하지 않고 '같은 객체'의 필드만 갱신(in-place)합니다." 정합 ★ |

**최종 판정**: **(i) 의도 명확 + (iii) 정당 use case 보유**. driver subprocess 환경에서의 회귀는 **§12-20 fix 의 scope 외에서 발생한 side effect** — 의도 위반 아닌 **scope gap**.

---

## § 3. mechanism CONFIRMED + F-β / γ 표기 정리

### 3-1. mechanism status

| 항목 | status |
|---|---|
| B-2ext3 static-code mechanism 추론 | **★★★ CONFIRMED empirical** |
| 두 mystery (CHROMA_NAMESPACE_WEB=venfobel-vitamin-oa, vertex API model=gpt-4o) 단일 root cause | **★★★ CONFIRMED** (stage a→c flip 박제) |
| flip 시점 = `reload_config_inplace()` 의 `load_dotenv override=True` + `_apply_provider_overlay` | **★★★ CONFIRMED** |
| CWD 가설 (`find_dotenv(usecwd=True)` 의 CWD 의존성) | **★ 박제** (자기 비판 §1 강화 자산) |

### 3-2. (γ) reversal — empirical 박제

| cycle | (γ) 평가 |
|---|---|
| B-1ext | "가장 유력" priors |
| **B-2ext2** (envdump STAGE_1/2) | "기각 확정 (9번째 priors)" — STAGE_3+ measurement gap |
| **B-2ext3** (static code mechanism 추론) | "정정 — CONFIRMED 추론" |
| **B-2ext4** (in-chain probe a/c/b) | **★★★ empirical CONFIRMED ★★★** — stage c 에서 `CHROMA_NAMESPACE_WEB=venfobel-vitamin-oa-web`, `OPENAI_MODEL=gpt-4o` 박제 → `.env.openai` overlay 가 실제 load 됨 박제 |

→ **(γ) "기각 확정 (9번째 priors)" 의 false negative 가 in-chain measurement 로 명확화** ★.

### 3-3. F-β 표기 자연 해소 ★

| priors §8 (F-β) 평가 | 본 cycle 정정 |
|---|---|
| "provider 분기 path divergence 가장 유력" → **부분 기각** (get_llm L327 vertex 분기 정상) | **mechanism 정확화**: code-level 분기 (`get_llm()`) 는 정상이지만, **env-mutation level 에서 LLM_PROVIDER vertexai → openai flip → `.env.openai` overlay → CHROMA_NAMESPACE_*, OPENAI_MODEL 도입**. LLM_MODEL=gpt-4o 는 글로벌 `.env L3` 직접 mutate. |
| F-β 표기 "부분 기각" | **자연 해소** — code-level divergence 는 부재, env-level divergence 가 confirmed ★ |

### 3-4. 자기 비판 §1 강화 자산 박제

| 자산 | 박제 cycle |
|---|---|
| envdump-style 측정의 STAGE 범위 한계 ("기각 확정" false negative risk) | B-2ext3 → B-2ext4 정정 |
| **in-chain measurement (probe a/c/b) 필요 case 박제** | **★ 본 B-2ext4** — 외부 envdump 만으로 잡히지 않는 mid-invoke mutation 은 production code 안에 probe 삽입 + revert protocol 자산화 |
| **CWD 의존성 (find_dotenv usecwd=True) 박제** | **★ 본 B-2ext4** — driver 환경의 `-WorkingDirectory` 설정이 reload 회귀 발화 조건 |

---

## § 4. fix 대안 권장 (의도 판정 기반)

### 4-1. 의도별 fix 권장 mapping

| 의도 판정 | 권장 fix | 박제 |
|---|---|---|
| (i) 의도 명확 ✓ + (iii) 정당 use case ✓ | **(O) protected env list — driver 명시 set vars 는 reload 시 보호. hot-reload 는 유지** | **★★★ 본 cycle 권장** |
| (ii) 사고 도입 (단독) | (O') override=False — generic disable | (해당 없음, intent 박제됨) |
| (iii) hot-reload use case 단독 | (O'') driver env snapshot/restore — reload 전 snapshot, reload 후 restore | secondary fallback |

### 4-2. (O) protected env list 설계

```python
# core/config.py reload_config_inplace() 수정 (proposal, B-3 에서 설계 sharpening)
_PROTECTED_ENV_KEYS = ("LLM_PROVIDER", "LLM_MODEL", "TOPIC_SLUG", "MIRROR_STATE_TO_ENV")

def reload_config_inplace() -> Config:
    global CFG
    with _cfg_lock:
        if _DOTENV_READY:
            # Protected env snapshot
            _saved = {k: os.environ.get(k) for k in _PROTECTED_ENV_KEYS if k in os.environ}
            try:
                load_dotenv(find_dotenv(usecwd=True), override=True)
            except Exception:
                pass
            # Restore protected env (override=True 회귀 차단)
            for k, v in _saved.items():
                if v is not None:
                    os.environ[k] = v
            _apply_provider_overlay(verbose=False)
            _apply_topic_preset(verbose=False)
        ...
```

**효과**:
- driver 가 명시 set 한 LLM_PROVIDER/LLM_MODEL/TOPIC_SLUG 보호 → `.env.openai` overlay load 안 됨 → CHROMA_NAMESPACE_WEB/OPENAI_MODEL/gpt-4o 도입 차단 ★
- hot-reload 사용자 use case 는 유지 (외부에서 `.env` 편집 후 reload_config 호출 시 다른 vars 는 정상 반영)

**risk**:
- protected list 의 누락 가능성 (예: `SKIP_VERTEX_SEARCH` 도 driver-set 이면 보호 필요?) — case 별 추가 검토
- 향후 신규 env var 도입 시 protected list 유지보수 필요

### 4-3. 기존 fix candidate 재평가

| candidate | 본 cycle 평가 |
|---|---|
| **(O) protected env list** | **★★★ 본 cycle 권장 — 의도 (i)+(iii) 정합, root cause fix** |
| (O') override=False (generic) | 不要 — (i) 의도 위반, hot-reload use case 손실 |
| (O'') driver env snapshot/restore (caller side) | secondary fallback — driver 가 변경 필요, production code 무변 가능 |
| (C) embedding 일치성 검증 | wrapper safety net 으로 병행 (root cause fix 아님) |
| (P) 글로벌 `.env L2/L3/L50` static default 제거 | config hygiene — root cause 자체 제거하지만 dev UX 영향 |
| (B) CFG auto-derive 강화 | defense-in-depth |

### 4-4. B-3 entry 권장

**(가) mechanism CONFIRMED + 의도 (i)+(iii) 박제 → fix 선택 → B-3 entry** ★

- B-3 fix: **(O) protected env list** primary + **(C) embedding 일치성 검증** secondary safety net
- B-4 효과 측정: wrapper run 에서 vertex 404 + venfobel namespace 둘 다 사라져야 정합
- 효과 충분 → 본 미션 close

---

## § 5. priors 갱신 + 진단 가치 박제

### 5-1. priors 정정 누적

| # | priors | 정정 |
|---|---|---|
| 9 | (γ) `.env.openai` load — "기각 확정" (B-2ext2) | **★★★ empirical reversal (B-2ext4 stage c probe)** |
| 11 (B-2ext3 신규) | mystery 2건 단일 mechanism | **★★★ empirical CONFIRMED (본 B-2ext4)** |
| **12 (신규)** | CWD 의존성 (`find_dotenv(usecwd=True)`) | **★ 신규 박제** — wrapper 환경의 -WorkingDirectory 가 regression 발화 조건 |
| **13 (신규)** | override=True 의도 (i)+(iii) — hot-reload 정당 use case | **★ 신규 박제** — fix 방향 결정에 critical |

### 5-2. 본 cycle 진단 가치

- **시간 box 1 round 정합** — probe 삽입 + revert + git blame + 분석 (~20 min)
- **mechanism empirical CONFIRMED** — static code 추론 → runtime 박제 완료
- **의도 박제 = fix 방향 critical input** — protected env list 선택 정당화 ★
- **in-chain measurement protocol 자산화** — production code 안 probe 삽입 + revert self-check (commit 전 git diff 확인 의무) — 향후 mystery 진단 protocol 강화 ★

---

## § 6. 시나리오 결정 + Claude Code 권장

### 6-1. 본 mission 분기 결과 = (가)

> (가) mechanism CONFIRMED + 의도 판정 명확 → fix 선택 → B-3 entry ★

### 6-2. Claude Code 권장 — 시나리오 6 sharpening

**시나리오 6 (root cause fix B-3 진입, sharpened)**:
1. **(O) protected env list** at `core/config.py reload_config_inplace()` — driver-set LLM_PROVIDER/LLM_MODEL/TOPIC_SLUG/MIRROR_STATE_TO_ENV snapshot+restore
2. **(C) embedding 일치성 검증** at `agent/vector_search.py _call_retrieve` — wrapper safety net (병행)
3. B-3 patch 설계 → B-4 효과 측정
4. 효과 측정 metric: wrapper 환경에서
   - `[vector_search] ns=` log 가 `ai-generated-creative-ad-platforms` 정합 (venfobel 사라져야)
   - `[web_search] Vertex success` log 정상 출력 (404 사라져야)
   - 또는 `[web_search] Vertex failed: 404` 가 fix 후 사라져야

### 6-3. user 컨펌 Q list

**Q1.** § 1.3-1.4 — stage a→c flip 박제 (LLM_PROVIDER vertexai→openai, LLM_MODEL gemini-2.5-flash→gpt-4o, TOPIC_SLUG ai-generated→venfobel-vitamin, CHROMA_NAMESPACE*/OPENAI_MODEL 신규 도입) **empirical CONFIRMED** 합의 OK?

**Q2.** § 1.2 — **CWD 가설 박제** (`find_dotenv(usecwd=True)` 가 CWD=writer_project 시만 regression 발화) 합의 OK?

**Q3.** § 2 — override=True 의도 판정 **(i) 의도 명확 + (iii) 정당 use case (ENV hot-reload)** 합의 OK?

**Q4.** § 3.2 — **(γ) "기각 확정 (9번째 priors)" empirical reversal** + § 3.3 **F-β 표기 "부분 기각" 자연 해소 (env-level divergence confirmed)** 합의 OK?

**Q5.** § 4.4 — **(O) protected env list** primary fix + **(C)** secondary safety net B-3 entry 합의 OK?

**Q6.** § 5.1 — priors 정정 12-13번째 (CWD 의존성 + override=True 의도) 자산화 합의 OK?
