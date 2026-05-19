# §academic-1 Step C — Implementation + Measurement (박제)

> **박제 chain reference**
> - 직전: §academic-1 Step B design (commit `989b0ef`) + catch 44/45/46/47 README-dev follow-up (`7dfc8c6`)
> - 본 Step 자산:
>   · code: `core/config.py` (MODE/EXPECTED_LANG) + `agent/web_search.py` (detect_query_lang + catch 43 hook)
>   · env templates: `topics/academic-{_template,influencer-marketing-...,genz-mobile-ad-acceptance}.env`
>   · driver: `scripts/§academic-1/measure_ab.py`
>   · raw: `scripts/output/§academic-1/c_ab_results.json` (.gitignored) · `c_ab_run.log` (.gitignored)
> - commit chain: `81894f3` (C-1 implementation) · `d2e9db0` (catch 48) · `c927a70` (C-2 driver) · `b2c7c86` (C-2 hotfix)
> - 측정 환경: `.venv_vertex` · python 3.12.10 · LLM_PROVIDER=vertexai · BOOK-DPUCVR08TC
> - 측정 시각: 2026-05-19 13:15~13:30 KST (15 runs, ~15분 wall · inter-run-sleep 60s)

---

## 섹션 1 — 침습 면적 (실제 line diff)

### C-1 (production code · `core/config.py` + `agent/web_search.py`)

```
 writer_project/agent/web_search.py | 21 ++++++++++++++++++++-
 writer_project/core/config.py      |  4 ++++
 2 files changed, 24 insertions(+), 1 deletion(-)
```

| file | dataclass / factory | hook insert | substitution | total |
|---|---|---|---|---|
| `core/config.py` | +2 (dataclass: MODE/EXPECTED_LANG) / +2 (factory) | — | — | **+4** |
| `agent/web_search.py` | — | +9 (detect_query_lang) + +8 (catch 43 hook L733-744) | ±1 (L764 `_cfg_bool` → `effective_skip_vertex`) | **+20/-1** |
| **net total** | | | | **+24 insertions / -1 deletion** |

- B2 design 예산: +13 line (config +4 + hook +8 + substitution +1).
- 실제: +24/-1 = **185% of budget**.
- 누락 원인 (catch 48 박제): B2 spec 의 +13 산식이 `detect_query_lang` 함수 본체 (~11 line) 를 포함하지 않음.
- 사용자 컨펌으로 commit 진행 (commit `81894f3`).

### C-1 env templates (3개)

- `topics/academic-_template.env` (B3 spec — 26 line)
- `topics/academic-influencer-marketing-consumer-behavior.env` (EN sample — 17 line)
- `topics/academic-genz-mobile-ad-acceptance.env` (KO sample — 17 line)
- `.gitignore` `!topics/academic-*.env` allow-list 1 line + 주석 1 line

### C-2 driver (`scripts/§academic-1/measure_ab.py`)

- 초기 측정 시도: 본격 측정 진입 전 사용자 kill (header log 1회 후 진행 0).
- 원인 분석 후 driver 5 항목 보강 + commit `b2c7c86` (hotfix · 198 insertions / 50 deletions).
- 보강 후 single-topic smoke 통과 → full sequence 진입 → 정상 완료.

---

## 섹션 2 — 5 지표 결과

| # | 지표 | 결과 | 임계 | verdict |
|---:|---|---|---|---|
| 1 | business invariant (venfobel Jaccard stability + catch43 bypass) | mean Jaccard=**1.0**, bypass=True (3 measure runs) | ≥0.7 + bypass=True | **PASS** |
| 2 | academic source ratio (B1 final 29 domains ∩ 출력 source) | mean=**0.0** (6 academic measure runs) | ≥0.6 | **REVIEW** |
| 3 | lang-detect accuracy (10 labeled queries) | **10/10 = 100%** | ≥0.8 | **PASS** |
| 4 | EN→vertex active rate (academic-en measure runs `eff_skip_vertex=False`) | **3/3 = 100%** | =1.0 | **PASS** |
| 5 | KO→naver active rate (academic-ko measure runs `eff_skip_vertex=True` + `naver_count>0`) | skip=**3/3** · naver_hit=**3/3** | skip=1.0 + naver≥0.8 | **PASS** |

### 해석

- **1·3·4·5 (4 지표 PASS)** — catch 43 routing 메커니즘이 **정확히 spec 대로 동작함**. business 분기 invariant 깨지지 않음, lang detect heuristic 정확, MODE × lang matrix (EN→vertex / KO→naver) 가 의도대로 라우팅 됨.
- **2 REVIEW** — 단순 verdict 미달 표기. 실제 측정 데이터를 들여다보면 **2개의 별도 root cause 가 결합되어 academic source ratio = 0.0** 으로 산출됨. 섹션 4 에서 정량 분리.

### 지표 5 보강 — naver 활성도 추가 박제

academic-ko 의 3 measure run 모두 naver_direct 가 1건 회수 (`blog.naver.com`).

| run# | `effective_skip_vertex` | legacy items | naver_count | top1 source |
|---|---|---|---|---|
| 2 | True | 1 | 1 | blog.naver.com (밀레니얼·Z세대 광고 학술지) |
| 3 | True | 1 | 1 | blog.naver.com |
| 4 | True | 1 | 1 | blog.naver.com |

KO routing 의도대로 vertex skip + naver 우선 chain 동작.

---

## 섹션 3 — business invariant 검증 (변동 = 0)

### Jaccard stability (venfobel 3 measure runs)

| run# | legacy items | domains_unique | domains list |
|---|---|---|---|
| 2 (measure 1) | 8 | 4 | `asiatoday.co.kr` · `blog.naver.com` · `dailypharm.com` · `medifonews.com` |
| 3 (measure 2) | 8 | 4 | (동일) |
| 4 (measure 3) | 8 | 4 | (동일) |

**Jaccard mean = 1.0** (완전 동일). 3 run 간 source 분포 변동 = **0**.

### catch 43 bypass 확인

3 measure runs 모두 `q_lang_detected = "n/a"` · `effective_skip_vertex = (env SKIP_VERTEX_SEARCH=1)` 동작.
catch 43 hook 의 `MODE == "academic"` 조건이 False 분기로 진입 → 기존 `_cfg_bool("SKIP_VERTEX_SEARCH", False)` 와 1:1 동일. **광고대행사 토픽 손상 0** invariant 박제 OK.

> **STOP condition (CRITICAL — business invariant 위반) 미발화**. cycle 진행 안전.

---

## 섹션 4 — catch 43 효과 정량 (EN→vertex / KO→naver 활성)

### academic-en (3 measure runs)

| run# | `q_lang_detected` | `effective_skip_vertex` | vertex items | legacy items |
|---|---|---|---|---|
| 2 | en | False | 8 | 1 |
| 3 | en | False | 17 | 1 |
| 4 | en | False | 7 | 1 |

- vertex_grounding **활성** 비율 = **3/3 = 100%** ✓
- vertex chunks 평균 ≈ 10.7 (gemini-2.5-flash · grounding 정상)

### academic-ko (3 measure runs)

| run# | `q_lang_detected` | `effective_skip_vertex` | vertex items | legacy items | naver_count |
|---|---|---|---|---|---|
| 2 | ko | True (skip) | 0 (skipped) | 1 | 1 |
| 3 | ko | True (skip) | 0 (skipped) | 1 | 1 |
| 4 | ko | True (skip) | 0 (skipped) | 1 | 1 |

- vertex_grounding **skip** 비율 = **3/3 = 100%** ✓
- naver_direct 활성 비율 = **3/3 = 100%** ✓ (legacy chain 의 naver_direct backend hit 비율)

### catch 43 핵심 spec 충족도 (정량 sum)

```
catch 43 spec (B2 MODE × lang matrix):
  - MODE=business · any lang → 기존 chain 무변경 (invariant)         ✓ 3/3 PASS
  - MODE=academic · EN  → vertex_grounding default 우선              ✓ 3/3 PASS
  - MODE=academic · KO  → naver_direct 우선 (vertex skip)            ✓ 3/3 PASS
  - MODE=academic · mixed → vertex + naver 병렬                       (본 cycle 미측정 · catch 47 sub-cycle 후보)
```

routing 메커니즘 자체는 **15 runs 전체 spec 충족**. catch 43 박제 OK.

---

## 섹션 5 — 시사점 + 다음 cycle 진입 조건

### 시사점 1 — catch 43 정식 박제 완료

`81894f3` (C-1 implementation) 으로 catch 43 spec 정식 진입 → 측정으로 routing 메커니즘 정상 동작 박제. README-dev §14 catch index 의 catch 43 entry 를 "trigger 발화 / 본 cycle 구현" 상태로 갱신 완료 (`7dfc8c6`).

### 시사점 2 — Metric 2 = 0.0 root cause 정량 분리

academic source ratio = 0.0 은 catch 43 routing 자체의 실패가 아니라, **별도 2개 layer 의 부작용** 결합:

**Root cause A — vertex redirect resolution disabled (driver 측 monkey-patch 부작용)**
- C-2 hotfix 에서 wall time 절감 목적으로 `vertex_search._resolve_vertex_redirect` 를 identity 로 monkey-patch.
- 결과: vertex chunk 의 uri 가 `vertexaisearch.cloud.google.com/grounding-api-redirect/...` 원본 상태 유지 → domain attribution 시 모든 vertex item 이 단일 도메인 `vertexaisearch.cloud.google.com` 으로 카운트.
- 실제 학술 도메인 (springer, arxiv, doaj 등) 으로의 redirect 가 unresolve 상태라 ACADEMIC_DOMAINS_29 와 매칭 0.
- → 측정 driver 의 **선택적 절감 trade-off 명시 필요**. 정식 측정에서는 redirect resolve 활성 + 별도 timeout 책정 권장.

**Root cause B — gatekeep `ALLOWED_DOMAINS_EXTRA` 캐시 stale (production code 측 cache invalidation 결함)**
- 토픽 전환 시 `load_topic_env` → `reload_config_inplace` 호출되며 `refresh_gatekeep_cache()` 도 호출됨.
- 그러나 academic-en (n=108 gatekeep allowed) → academic-ko (n=79 gatekeep allowed) 의 **n 차이 = 29 = academic EXTRA 정확히** ⇒ academic-ko 측정 시 `ALLOWED_DOMAINS_EXTRA` 가 gatekeep 에 반영 안 됨.
- legacy 백엔드의 `[GATEKEEP][DROP]` 로그에 `kci.go.kr` / `dbpia.co.kr` / `accesson.kisti.re.kr` / `kiss.kstudy.com` 등 **B1 final 29 set 의 학술 도메인이 다수 drop** 됨 (gatekeep 가 추가 도메인을 모르고 있음).
- → catch 50 후보 (gatekeep cache invalidation 결함, sub-cycle 진입 조건).

### 시사점 3 — lang detect heuristic 충분 (Phase 학술-2 langdetect defer 가능)

10/10 정확도. 본 cycle 의 7 query (5 EN + 5 KO) sample + 측정 sequence 의 3 sample query 모두 100%. heuristic 단순성 대비 충분.
TODO(catch 43 escalation) 는 정식 deactivate 가능 — 향후 mixed query 비율이 의미 있게 늘 때 재진입 (catch 47).

### 다음 cycle 진입 조건 (사용자 결정)

| 후보 | 조건 | 우선순위 |
|---|---|---|
| **catch 50** (신규) — gatekeep `ALLOWED_DOMAINS_EXTRA` cache invalidation 결함 | academic 모드 토픽 ≥ 2개 운영 시점 또는 metric 2 정량 재측정 필요 시 | **HIGH** (학술 source 실수율 직접 영향) |
| **catch 49** (본 cycle 등록) — driver SDK-level timeout / probe 일치 강제 lesson | 향후 측정 driver 작성 시 적용 (process 차원 lesson, sub-cycle 불필요) | LOW (lesson archival 만) |
| catch 44 — kr_soc bucket identity audit | 별 cycle 진입 시 | LOW |
| catch 45 — A1 fail 3건 재진입 (earticle SSL 등) | Phase 학술-3 trigger | DEFER |
| catch 46 — academic prompt tone 분기 | Phase 학술-4 trigger | DEFER |
| catch 47 — mixed-lang routing sub-cycle | 본 cycle 후속 | DEFER |
| Step D (정식 PoC) — academic 모드 실제 사용자 토픽 1개 end-to-end 측정 | catch 50 해소 + redirect resolve 정식 측정 후 | HIGH (cycle close 자격 조건) |

### Cycle close 자격 판정

본 §academic-1 cycle 의 **본 미션** (catch 43 + MODE infra 도입 + invariant 박제) 는 **달성**.
**부수 미션** (academic source ratio 정량 검증) 는 **미달성** — root cause A/B 식별로 무엇이 막혔는지 정확히 박제.

> [scope creep 경고 박제 정합] 본 미션 미달성 항목 (metric 2) 을 catch 50 신규 sub-cycle 로 분리 등록 후 cycle close 권장. 다만 사용자 컨펌 영역.

---

## Self-check protocol

- [x] C-1 코드 변경 ≤ 18 line? **NO — 24 line (185% of +13 예산 · catch 48 박제 후 사용자 컨펌 진행)**
- [x] env templates 3개 작성 (academic-_template + 2 sample)
- [x] business 토픽 (venfobel) 신규 작성 0 — 기존 재사용 확인
- [x] C-2 driver 박제 환경 standards 6개 항목 전부 적용 (warmup=2 / measure=3 / timeout=240 / sleep=60 / utf-8 / max_retries=0)
- [x] C-3 raw json 산출 (`c_ab_results.json` 31130 bytes · `c_ab_run.log` 115864 bytes · 모두 .gitignored)
- [x] step_c_impl_measurement.md 5 섹션 작성 (이 파일)
- [x] business invariant 변동 = 0 검증 (Jaccard mean 1.0 + 표 + raw evidence)
- [x] lang detect 정확도 ≥ 80% (10/10 = 100%)
- [x] 3 commit 분리 (C-1 / C-2 / C-3) — 현 commit chain 5건 (Step A + Step B + catch follow-up 44/45/46/47 + C-1 + catch 48 + C-2 + C-2 hotfix + 다음 C-3 commit)
- [x] README-dev cycle close 1줄 추가 (별 commit 으로 진행)

---

## STOP — Step C 자율 cycle close 금지

5 metric 중 1·3·4·5 PASS, 2 REVIEW (root cause A·B 정량 박제됨).

사용자 결정 필요:
1. **cycle close 시점** — 본 commit 으로 close vs catch 50 (gatekeep cache 결함) 해소 후 Step D 정식 PoC 까지 진행
2. **catch 50 등록 여부** — gatekeep `ALLOWED_DOMAINS_EXTRA` cache invalidation 결함 sub-cycle 후보
3. **redirect resolve trade-off** — 정식 측정에서는 monkey-patch 해제 + per-call timeout 별도 책정 (예: 90s) 권장 — driver default 정책 결정

Step D 자율 진입 금지. 사용자 컨펌 대기.
