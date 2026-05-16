# §14-8-B B-2ext — (F) vertex 404 (gpt-4o) fix 평가

**측정 일자:** 2026-05-17
**git HEAD:** 77c24ad (feature/vertex-web-search)
**미션:** (F) vertex 404 for gpt-4o 의 호출 path 박제 + fix candidate (F-1/F-2/F-3) 정확 설계

---

## § 1. grep 영역 + 키워드 결과

### 1-1. get_llm() 호출처 박제

| caller | line | model 인자 | 박제 |
|---|---|---|---|
| `agent/chapter_writer.py:154` | `llm = get_llm()` | 무 | default |
| `agent/communicator.py:874` | `llm = get_llm()` | 무 | default |
| `agent/content_strategist.py:35` | `llm = get_llm()` | 무 | default |
| `agent/research_planner.py:30` | `llm = get_llm()` | 무 | default |
| `agent/research_synthesizer.py:54` | `llm = get_llm()` | 무 | default |
| `agent/section_writer.py:192` | `llm = get_llm()` | 무 | default |
| `agent/supervisor.py:384` | `llm = get_llm()` | 무 | default |
| `agent/vector_search.py:647, 961` | `llm = get_llm()` | 무 | default |
| `agent/web_search.py:192` | `llm = get_llm()` | 무 | default |
| `utils/chunk_summary.py:125` | `llm = get_llm()` | 무 | default |
| **`agent/export/planner.py:108`** | **`llm = get_llm(model=model)`** | **명시** | export planner 만 |

→ **production code 의 모든 get_llm() 호출은 model 인자 무** (export/planner 외)
→ get_llm() 의 model = CFG.LLM_MODEL or DefaultChatModel = "gemini-2.5-flash" (vertex 정합)

### 1-2. os.environ["LLM_MODEL"] mutate 위치

| source | line | 박제 |
|---|---|---|
| `scripts/measure_stability.py:461` | `os.environ["LLM_MODEL"] = saved_model` | **측정 script (production 무관)** |
| `scripts/measure_vertex_phase_a.py:160, 194` | `os.environ["LLM_MODEL"] = model_name` | **측정 script (production 무관)** |

→ **production code 에서 os.environ["LLM_MODEL"] mutate 부재** ★

### 1-3. "gpt-4o" hardcode (production)

| source | line | 박제 |
|---|---|---|
| `app.py:1214` | `model = os.getenv("OPENAI_MODEL", "gpt-4o")` | **OPENAI_MODEL default** (LLM_MODEL 아님) |
| `core/llm.py:86` | `out["DefaultChatModel"] = "gpt-4o"` | **openai provider 분기 only** (vertex 분기는 L138 = gemini-2.5-flash) |
| `core/config.py:600` | `OPENAI_MODEL=_env_str("OPENAI_MODEL", "gpt-4o")` | **CFG.OPENAI_MODEL default** (CFG.LLM_MODEL 아님) |

→ **모두 OPENAI 관련만**. vertex API 호출 path 의 "gpt-4o" hardcode 부재.

### 1-4. core/llm.py get_llm() L327 model 결정 logic

```python
m = model or getattr(config.CFG, ChatModelKey, None) or DefaultChatModel
```

- vertex provider 시: ChatModelKey = "LLM_MODEL" (L135), DefaultChatModel = "gemini-2.5-flash" (L138)
- → `m = model or CFG.LLM_MODEL or "gemini-2.5-flash"`
- agent/web_search.py L192 `llm = get_llm()` → model = None
- CFG.LLM_MODEL = "gemini-2.5-flash" (wrapper env 박제)
- → **m = "gemini-2.5-flash"** (정상 path)

### 1-5. vertex_web_search 내부 (vertex_search.py L88-195) 재검토

```python
# L112
model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
# L125-129
response: Any = client.models.generate_content(
    model=model_name,
    contents=query,
    config=config,
)
```

→ env LLM_MODEL = "gemini-2.5-flash" 라면 model_name = "gemini-2.5-flash"
→ vertex generate_content 의 model = "gemini-2.5-flash" 정상

---

## § 2. (F) mechanism 평가 — **mystery 미박제 확정** ★

### 2-1. expected vs actual

| step | expected | wrapper 환경 actual |
|---|---|---|
| wrapper env LLM_MODEL | "gemini-2.5-flash" (driver 명시 set) | 정합 (env_trace 박제) |
| CFG.LLM_MODEL | "gemini-2.5-flash" | 정합 (추정) |
| get_llm() vertex 분기 m | "gemini-2.5-flash" | 정합 (L327 logic) |
| vertex_web_search L112 model_name | "gemini-2.5-flash" | 정합 (env 그대로) |
| vertex generate_content model | "gemini-2.5-flash" | **"gpt-4o" ★** (variant-B stderr) |

→ **expected vs actual mismatch — mechanism 미박제** (B-1 mystery 와 동등 수준)

### 2-2. (F-α/β/γ/δ) 가설 평가

| 가설 | 평가 결과 |
|---|---|
| (F-α) LLM_MODEL env 가 vertex_grounding 도구에 전달 안 됨 → default "gpt-4o" | **★ 기각** — vertex_search.py L112 default = "gemini-2.5-flash" 정합 |
| (F-β) provider/model 분기 path divergence (vertex 인데 openai DefaultChatModel 누출) | **★ 부분 기각** — get_llm() L327 vertex 분기 정상, openai default 누출 path 없음 |
| (F-γ) vertex_search.py 내부 호출 chain mutate | **★ 기각** — L112-129 정상 logic |
| **(F-δ 신규) wrapper 환경에서 env LLM_MODEL 이 invoke 직전 mutate** | **★ 약화** — production code 에서 os.environ["LLM_MODEL"] mutate 부재 |
| **(F-ε 신규) LangChain ChatVertexAI / 다른 vertex API path 에서 model="gpt-4o" 가 set** | **★ 가능성 — 추가 진단 필요** (외부 library) |
| **(F-ζ 신규) `[web_search] Vertex failed:` log 가 vertex_web_search 외 다른 vertex API call 의 exception 가능성** | **★ 가능성 — 추가 진단 필요** |

### 2-3. (F) mechanism 미박제 확정 박제

- 본 B-2ext grep 결과 (F-α/β/γ) 모두 기각/부분 기각
- (F-δ/ε/ζ) 추가 진단 필요 — 본 cycle scope 외
- → **(F) mechanism 본 cycle 내 박제 불가** ★

### 2-4. (F-1/F-2/F-3) fix candidate 정확 설계 어려움

| fix | 설계 가능? |
|---|---|
| (F-1) vertex API 호출 직전 model 인수 강제 (gemini-2.5-flash) | △ 가능 — vertex_search.py L125-129 model 인수 명시. 단 mechanism 미박제라 다른 vertex API call path 가 fix bypass 가능 |
| (F-2) get_llm() fallback chain default model 수정 | ★ 불요 — get_llm() default = gemini-2.5-flash 정상 |
| (F-3) vertex_grounding 호출 시 model 인수 명시 전달 | △ 가능 — agent/web_search.py L766 caller 측. 단 vertex_web_search 가 ignore 가능 (L112 env read) |

→ **mechanism 미박제 상태에서 fix 정확 설계 어려움** — fix 적용해도 다른 path 가 bypass 가능

---

## § 3. 사용자 plan 박제 정합 — **fix C fallback + (F) 별 cycle reserve**

### 3-1. user plan B-2ext 후 분기 정합

> (F) mechanism 식별 (F-α/β/γ 중) → fix candidate (F-1/F-2/F-3) 정확 설계 → B-3 진입
> **(F) mechanism 미박제 → fix C fallback + 추가 cycle reserve** ★

→ 본 B-2ext 결과 정합

### 3-2. 다음 단계 권장 — 시나리오 3건

**(시나리오 1) fix C fallback B-3 진입**
- 장점: B-3 진입 가능, 본 cycle close 진행
- 단점: fix C 의 한계 박제 (B-2 § 3.2) — vertex 404 자체 fix 안 됨, 효과 부족 risk
- 효과 부족 시: 별 cycle (§14-9?) — (F) mechanism 진단 진입

**(시나리오 2) 본 cycle close + 별 cycle 진입**
- 장점: (F) mechanism 정확 진단 후 fix 정확 설계
- 단점: 본 cycle 짧게 close, 본 미션 정량 박제 지연
- 별 cycle scope: (F-δ/ε/ζ) 추가 진단

**(시나리오 3) fix C 적용 + 별 cycle (F) 평가 reserve**
- 장점: fix C 효과 직접 측정 + (F) 추가 진단 reserve
- 단점: fix C 효과 부족 시 별 cycle (F) 진입 — 시간 분산

### 3-3. Claude Code 측 권장

**시나리오 1** (fix C fallback B-3 진입) — 사용자 plan 정합 + 본 cycle close 진행:
- fix C 의 한계 명확 박제 + B-4 측정으로 효과 직접 검증
- 효과 충분 → 본 미션 close
- 효과 부족 → 별 cycle (F) 진입 — mechanism 정확 진단

또는 **시나리오 2** (본 cycle close + 별 cycle 진입) — root cause level fix 우선:
- (F) mechanism 진단 비용 大 + 본 cycle 짧게 close
- 본 미션 정량 박제 지연 — 단 정확한 fix 보장

---

## § 4. 추가 발견 박제 (자기 비판 §1 강화)

### 4-1. priors 기각 8번째 (B-2ext)

- **(F-β) "★ 가장 유력" priors (B-1ext § 5)** → **부분 기각** (get_llm() vertex 분기 정상)
- priors 기각 누적: 8건
  1. case B 유력
  2. C timeout 의외로 유력
  3. D2 빠른 fail 예상
  4. driver wrapper #1/#2 高 의심
  5. vertex 404 gpt-4o (분기표 외)
  6. chroma embedding mismatch (분기표 외)
  7. fix C 추가 가치 (이미 mismatch handling 작동)
  8. **(F-β) provider/model 분기 path divergence** → 부분 기각

### 4-2. mystery 누적 박제

| mystery | 박제 상태 |
|---|---|
| (B-1ext) wrapper subprocess CFG.CHROMA_NAMESPACE_WEB venfobel resolve | 미박제 |
| (B-2ext) wrapper env vertex API call model = gpt-4o | 미박제 |

→ **두 mystery 모두 wrapper subprocess 환경 specific** — 동일 근본 mechanism 가능성 (별 cycle 합쳐 진단)

### 4-3. mystery 의 공통 hypothesis

- 두 mystery 모두 wrapper 환경에서만 발생 (D1 runpy 환경에는 없음)
- 두 mystery 모두 CFG / env 값이 다른 값으로 mutate 되는 path 가 있음
- 공통 hypothesis: **wrapper subprocess 환경에서 .env.openai 가 어디서 load** (B-1ext (γ) + 본 cycle)
  - CHROMA_NAMESPACE = venfobel-vitamin-oa (.env.openai L56) 가 set
  - OPENAI_MODEL = gpt-4o (CFG.OPENAI_MODEL default — but LLM_MODEL 와 다름)
  - 단 LLM_MODEL → gpt-4o mutate 경로는 미박제

---

## § 5. user 컨펌 Q list

**Q1.** § 1 grep 결과 박제 — production code 에서 LLM_MODEL=gpt-4o mutate 또는 hardcode **부재** 합의 OK?

**Q2.** § 2 — **(F) mechanism 본 cycle 내 박제 불가** 확정 합의 OK?
- (F-α/β/γ) 모두 기각/부분 기각
- (F-δ/ε/ζ) 추가 진단 필요

**Q3.** § 2.4 — fix (F-1/F-2/F-3) 정확 설계 어려움 (mechanism 미박제 → fix bypass 가능) 합의 OK?

**Q4.** § 3 다음 단계 시나리오:
- **(시나리오 1) fix C fallback B-3 진입** (Claude Code 1순위 권장 — 사용자 plan 정합)
- (시나리오 2) 본 cycle close + 별 cycle 진입 (root cause level fix 우선)
- (시나리오 3) fix C 적용 + (F) reserve (병행)

**Q5.** § 4 자기 비판 강화 박제:
- priors 기각 8번째 ((F-β) 부분 기각)
- 두 mystery (B-1 venfobel namespace + B-2 gpt-4o model) 의 공통 hypothesis = wrapper 환경 .env.openai load 가능성
- 별 cycle (§14-9?) 진입 시 공통 mechanism 진단 우선 권장
- 합의 OK?
