# §13-8-3 Phase 1 회귀 측정 결과 박제

작성일: 2026-05-12
트랙: §13-8-3 (Anthropic Haiku 4.5 평가)
대상 commit: `7713426` (fix: SlideSpec.bullets None → [] before-validator)
회귀 commit: commit 2 (본 박제 파일 첨부)

---

## 1. 회귀 본 목적

`SlideSpec.bullets` 에 `@field_validator(mode="before")` 추가 (None → [] 정규화) 가 **기존 provider (gpt-4o, Sonnet 4.6) 의 정상 흐름을 깨지 않는지** 확인. `validator no-op` (정상 List 응답 시 type pass-through) 입증이 본 commit 의 책임.

---

## 2. 회귀 결과 표

| provider | model | run | ok | latency | slide_count | tables | ValidationError | input/output tokens | cost (USD) | 판정 |
|---|---|---|---|---|---|---|---|---|---|---|
| OpenAI | `gpt-4o` | 1/1 | **True** | 172.14s | 54 | 10 | **0건** | 25,045 / 5,470 | $0.1173 | **PASS** (validator no-op 입증) |
| Anthropic | `claude-sonnet-4-6` | 1/1 | **False** | >240s (TIMEOUT) | — | — | 미상 (호출 미완) | — | — | **timeout 미달성** — Phase 1 본 측정 이월 |

- raw 산출물: `logs/stability_venfobel-vitamin_gpt4o_20260512_102240.json`, `logs/stability_venfobel-vitamin_claudesonnet46_20260512_115519.json` (untracked, 재현 불가능)

---

## 3. 회귀 판정

### gpt-4o 회귀 — PASS
- `ok=True` + `ValidationError 0건` → schema fix 가 gpt-4o 정상 흐름 무영향 입증
- Pydantic validator 동작은 deterministic → Sonnet/Haiku 도 Pydantic level 에서 동일 동작 보장

### Sonnet 4.6 회귀 — Phase 1 본 측정 이월
- TIMEOUT (240s 초과) 으로 ok=False → 사용자 박제 차단 조건 충족 ("run ok=False → 즉시 중단")
- ValidationError 발생 여부 미상 (호출 자체가 timeout — schema 검증까지 도달 못함)
- 단, validator 의 본 의도는 **Pydantic level 변환 (provider 무관)** → gpt-4o 회귀 PASS 로 schema fix 의 정상 흐름 무영향 입증 충분
- Sonnet provider 의 schema fix 효과 실증은 Phase 1 본 측정 (commit 3) 에서 Sonnet baseline 재측정 분기 채택 시 자연스럽게 cover

---

## 4. 차단 조건 재정의

### 회귀 단계 차단 조건 (gpt-4o + Sonnet)
- **ValidationError ≥ 1건** → 즉시 중단 (해당 없음, 발생 안 함)
- **run ok=False** → 즉시 중단 (Sonnet 회귀에서 실제 발동, 분기 b 채택으로 Phase 1 이월)
- slide_count / table_consistency 변동 = 회귀 무관 (차단 조건 **아님**, metadata 박제만)
- 차단 조건은 **input md 동일 가정 하에서만 유효** — input 변경 시 baseline 비교 invalid

---

## 5. 환경 상태 박제 (회귀 시점)

### Provider mismatch 상태
- `sections/venfobel-vitamin/` = **gpt-4o** 복원 상태
- `reports/venfobel-vitamin/latest.md` = **Sonnet 4.6 풍부성 산출물** (사용자 메모리 확정, mtime=2026-05-11 22:36:53)
- → **sections 와 latest.md 의 provider mismatch** (의도적/부산물 모두 가능)

### latest.md 갱신 인과 (사용자 메모리 확정)
- 시점: 2026-05-11 저녁
- 의도: Sonnet 이 gpt-4o 대비 풍부한 리포트 산출하는지 테스트
- 결과: latest.md 가 Sonnet 산출물로 갱신, sections 는 별도로 gpt-4o 로 복원
- **§13-14-α A2+B fix 와 무관** — A2+B 는 in-memory normalization (sections/*.md 무수정, README-dev.md line 2924), latest.md 갱신 인과 아님

### Sonnet baseline 측정 (5-10) vs 본 회귀 (5-12) input 차이
| 항목 | Sonnet baseline (5-10 08:01) | 본 회귀 (5-12) |
|---|---|---|
| md_source_markers | 54 | 24 |
| x_prime (유의미한 표) | 1 | 19 |
| md_chars | (baseline JSON 미기록) | 34,126 |

→ input md 가 명백히 다름 → baseline 비교 stale. gpt-4o 회귀 54 slides 는 Sonnet 풍부성 cascade 양상 (회귀 무관 사실)

---

## 6. bullets null 카운트 추적 한계 (옵션 C 박제)

- 회귀 단계에서 bullets null 카운트 직접 추적 **불가** (validator silent + measure_stability.py 통계만 저장, deck 자체 미보존)
- ValidationError 0건 = 두 경우 구분 안 됨:
  - (1) bullets 모두 정상 `List[str]` → validator no-op
  - (2) bullets 일부 `null` → validator None→[] 변환 성공
- 두 경우 모두 회귀 PASS 이긴 하나, 정확한 카운트 미상
- **옵션 C 채택**: 회귀 단계는 통계만, Haiku 본 측정 (commit 3) 직전 instrument 추가 (`spec.py` module-level counter + 측정 종료 시 보고)
- Haiku 진단 측정 (`logs/anthropic_tokens_*haiku*`) 기준 43 slides 중 9 null (≈20%) → instrument 가치 큼

---

## 7. catch 자산 실증 (본 회귀 단계)

기존 사용자 메모리 박제 catch 자산이 본 회귀에서 실제 발동:

### catch 자산 1 — `measure_stability.py` ThreadPoolExecutor 비취소
- Sonnet 회귀 240s timeout 시 `future.result(timeout=240)` 만 raise — background LLM 호출은 cancel 불가, SDK timeout (600s) 까지 계속 진행 가능
- 안전 마진: §13-8 phase 2 박제 (`measure_stability.py:54~62`) — OTPM Tier 1 (8K/min) 한도 안에서 inter-run-sleep 60s 로 budget refresh

### catch 자산 2 — wall-clock timeout vs SDK timeout 분리 운영
- wall-clock: `--per-run-timeout 240s` (측정 도구의 future cut)
- SDK: `ANTHROPIC_REQUEST_TIMEOUT=600s` (`.env.anthropic`)
- 두 timeout 의 책임 분리 — 측정 도구는 wall-clock 으로 자체 보호, SDK 는 connection-level timeout 유지

### catch 자산 3 — ChatAnthropic `max_retries` 기본 2 → §13-7 표준 0 override
- `.env.anthropic` 의 `ANTHROPIC_MAX_RETRIES=0` 명시
- core/llm.py `_build_anthropic_kwargs` 가 CFG 값 직접 전달 → latency retry sleep 오염 차단
- 본 회귀 Sonnet TIMEOUT 도 max_retries=0 검증 (retry 누적 가능성 차단됨, timeout 원인은 다른 곳)

---

## 8. Phase 1 본 측정 (commit 3) 진입 직전 결정 사항

### per-run-timeout 적정값 권고 (catch 26 sub-section)
- 원칙: `max(300, baseline_mean × 1.5)`
- Sonnet 재측정 시: **300~400s** (baseline mean 200s × 1.5 = 300, 마진 +50%)
- Haiku 본 측정 시: **300s** 보수적 (Haiku 가 빨라도 안전 마진)

### Sonnet baseline 재측정 분기 (X/Y/Z, commit 2 완료 후 사용자 결정)
- X. Sonnet baseline 재측정 (~$0.5, ~17분) + Haiku 본 측정
- Y. Haiku 본 측정만, stale baseline 명시 박제
- Z. Sonnet + gpt-4o 모두 재측정 + Haiku

### Haiku 본 측정 input 분기 (A/B/C, commit 2 완료 후 사용자 결정)
- A. 현 `latest.md` (Sonnet 산출물) 그대로 → "Haiku 가 Sonnet 풍부 입력 처리" 측정
- B. `latest.md` 를 gpt-4o 산출물로 복원 → "Haiku 가 gpt-4o baseline 입력 처리" 측정
- C. 5-10 Sonnet 측정 시점 input 복원 → 가장 정확한 apples-to-apples

---

## 9. Phase 2 진입 전 부수 점검 (commit 2 차단 조건 아님)

- `bell.export.pptx` 또는 동등 모듈이 sections 만 / latest.md 만 / 둘 다 읽는지 view → sections (gpt-4o) vs latest.md (Sonnet) provider mismatch 의 e2e PPTX export 영향 평가

---

## 10. Phase 0 trace 보존 (사용자 박제)

Phase 0 은 prior session 에서 선행 완료:
- `scripts/measure_stability.py:320` — `_PRICE` dict 에 `claude-haiku-4-5` 등록 + prefix-matching 로직 (line 327~333, datestamp suffix 포함 `claude-haiku-4-5-20251001` 정상 매칭)
- `scripts/_measure_anthropic_tokens.py:72` — `--model` argparse required=True (헤더 docstring §13-8-3 (2026-05-10) 박제)
- catch 24 점검 — `_measure_anthropic_tokens.py` 외부 호출자 없음 (CLI 단독 실행 도구)

따라서 Phase 0 추가 commit 불필요. trace 보존만.
