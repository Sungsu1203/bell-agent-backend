# §academic-2 Step C — Implementation + Measurement (박제)

> **박제 chain reference**
> - 직전: §academic-2 Step B design (commit `33f0cf0`) + design follow-up B8 결정 박제 (commit `4b75bc5`)
> - 본 Step 자산:
>   · code: `settings_gatekeep.py` (clear_runtime_allowed_domains + `__all__`) + `core/config.py` (reload_config_inplace hook)
>   · driver: `scripts/§academic-1/measure_ab.py` (재사용, B8 #2 결정 정합 — 신규 driver 작성 0)
>   · raw: `scripts/output/§academic-2/c_verification.json` (.gitignored) · `c_verification_run.log` (.gitignored — driver hard-coded path `§academic-1/c_ab_*` 로부터 cp)
> - commit chain (본 Step): `3598568` (C-1 fix 본체 단일 commit) · 본 박제 (C-2 측정 결과 별 commit, B8 #4 결정 정합)
> - 측정 환경: `.venv_vertex` · python 3.12.10 · `LLM_PROVIDER=vertexai` · BOOK-DPUCVR08TC
> - 측정 시각: 2026-05-19 22:04~22:44 KST (15 runs, ~40분 wall · inter-run-sleep 60s · per-run-timeout 90s)

---

## 섹션 1 — 침습 면적 (실제 line diff, commit `3598568`)

```
 writer_project/core/config.py       |  3 ++-
 writer_project/settings_gatekeep.py | 19 +++++++++++++++++--
 2 files changed, 19 insertions(+), 3 deletions(-)
```

| file | hunk | logical | cosmetic |
|---|---|---:|---:|
| `settings_gatekeep.py` | hunk 1 (L102-): `clear_runtime_allowed_domains` 함수 신설 (def 1 + docstring 6 + global 1 + body 1 + try/except 4 + separator blank 1) | +14 | ±2 (L95+L98 trailing whitespace trim) |
| `settings_gatekeep.py` | hunk 2 (L389): `__all__` 등록 `"clear_runtime_allowed_domains",` | +1 | 0 |
| `core/config.py` | hunk 3 (L693-694): import 보강 (in-place) + 호출 line 추가 | +1 | 0 |
| **net logical total** | | **+16** | 2 line trim |

### Budget 검산 (design B5 산식 +15 vs actual +16)

- 107% of budget — separator blank line 1줄 design B5 산정 누락 (PEP 8 convention).
- §academic-1 Step C-1 의 catch 48 발화 (+13 예산 vs 실제 +24 = 185%) 대비 차수 적음 → 별도 sub-catch 박제 불필요, commit `3598568` message 에 lesson 미세 재현 명시.
- 향후 design step budget 산식에 separator blank line 항목 포함 권장.

### syntax 검산
`ast.parse` 통과 (settings_gatekeep.py + core/config.py).

---

## 섹션 2 — 5 지표 결과

| # | 지표 | 결과 | 임계 (B7) | verdict |
|---:|---|---|---|---|
| 1 | business invariant (venfobel Jaccard stability + catch 43 bypass) | **Jaccard mean=1.0 strict** (3 measure runs) · bypass=True | **=1.0 strict (B8 #3)** + bypass=True | **PASS** |
| 2 | academic source ratio (B1 final 29 domains ∩ 출력 source) | mean=**0.3333** (6 academic measure runs) · academic-ko mean=**0.6667** · academic-en mean=**0.0** | mean ≥ 0.6 | **REVIEW (PARTIAL — 섹션 4 분리)** |
| 3 | lang-detect accuracy (10 labeled queries) | **10/10 = 100%** | ≥ 0.8 | **PASS** |
| 4 | EN→vertex active rate (academic-en measure runs `eff_skip_vertex=False`) | **3/3 = 100%** | = 1.0 | **PASS** |
| 5 | KO→naver active rate (academic-ko measure runs `eff_skip_vertex=True` + `naver_count>0`) | skip=**3/3** · naver_hit=**3/3** | skip=1.0 + naver≥0.8 | **PASS** |

### 보조 지표 — `[GATEKEEP] enabled; allowed=... (n=N)` (catch 50 fix 정합 직접 증거)

| topic | 모든 5 runs (warmup 2 + measure 3) | n | 의미 |
|---|---:|---:|---|
| business-venfobel | 5/5 | **79** | base 78 + 1 normalization (EXTRA 없음 — venfobel 토픽 정합) |
| academic-en | 5/5 | **108** | base 78 + EXTRA 29 + 1 normalization ✓ |
| academic-ko | 5/5 | **108** | base 78 + EXTRA 29 + 1 normalization ✓ |

§academic-1 측정 결과 (catch 50 결함 상태) 대비:
- academic-en: n=108 → n=108 (변화 0, 회귀 0)
- **academic-ko: n=79 → n=108 (+29 회복) — catch 50 fix 의 결정적 정량 증거**

---

## 섹션 3 — catch 50 fix 정합 박제 (본 미션 PASS)

### 본 미션 (catch 50 — gatekeep `_RUNTIME_ALLOWED` upstream 무효화 누락 해소)

| 검증 항목 | §academic-1 (fix 전) | §academic-2 (fix 후) | 결론 |
|---|---:|---:|---|
| academic-ko gatekeep allowed n (`[GATEKEEP] n=N`) | **79** | **108** | **PASS** — EXTRA 29 도메인 반영 정합 |
| academic-ko source domain set | (n=79 상태에서 academic 도메인 drop 다수) | `{blog.naver.com, dbpia.co.kr, kiss.kstudy.com}` | **PASS** — dbpia / kiss.kstudy 가 gatekeep 통과 |
| academic-ko `academic_source_ratio` | mean=**0.0** | mean=**0.6667** (5/5 runs strict) | **PASS** — 임계 0.6 충족 |
| academic-en gatekeep n | 108 | 108 | **회귀 0** |
| business invariant Jaccard | 1.0 (3 measure runs) | **1.0 strict** (3 measure runs · B8 #3 정합) | **회귀 0** |

### 본 미션 PASS 정합 박제

`clear_runtime_allowed_domains()` 신설 + `reload_config_inplace` hook (commit `3598568`) 이 토픽 전환 시 `_RUNTIME_ALLOWED` global 을 invalidate → `get_allowed_domains()` 의 short-circuit 우회 → ENV 의 새 `ALLOWED_DOMAINS_EXTRA` 가 fresh 반영. **catch 50 root cause 정합 해소**.

---

## 섹션 4 — academic source ratio 정량 분리 (부수 미션 PARTIAL)

> **scope creep 경고 박제 정합** — 부수 미션 (academic source ratio mean ≥ 0.6) 은 mean 0.3333 으로 **임계 미달**. 본 미션 PASS 와 별도로 명시 재평가 sub-section 의무.

### academic-ko (mean ratio 0.6667 — 임계 충족)

| run | `q_lang` | `effective_skip_vertex` | all_domains_unique | academic_hits | ratio |
|---|---|---|---|---|---:|
| measure 1 | ko | True | `{blog.naver.com, dbpia.co.kr, kiss.kstudy.com}` | `[dbpia.co.kr, kiss.kstudy.com]` | **0.6667** |
| measure 2 | ko | True | (동일) | (동일) | **0.6667** |
| measure 3 | ko | True | (동일) | (동일) | **0.6667** |

- 결정성: 5/5 runs 완전 동일 (warmup 2 + measure 3) — naver_direct backend 가 dbpia / kiss.kstudy 안정적 회수 + gatekeep 통과 (catch 50 fix 정합)
- 임계 충족: **0.6667 ≥ 0.6 ✓**

### academic-en (mean ratio 0.0 — 임계 미달, **catch 50 외부 root cause**)

| run | `q_lang` | `vertex_items` | all_domains_unique 샘플 | academic_hits |
|---|---|---:|---|---|
| measure 1 | en | 12 | `{academic.naver.com, acr-journal.com, allindiamediasolutions.com, eelet.org.uk, eyes4research.com, forbes.com, hypefy.ai, mdpi.com, medium.com, pdfs.semanticscholar.org, researchgate.net, scilit.com}` | `[]` |
| measure 2 | en | 8 | `{academic.naver.com, allindiamediasolutions.com, eyes4research.com, forbes.com, intelliplans.com, mdpi.com, medium.com, mintel.com, researchgate.net}` | `[]` |
| measure 3 | en | 17 | (18-domain set, mdpi/forbes/medium 외 ad-tech 다수) | `[]` |

#### root cause 분리 (catch 50 외부)

1. **vertex grounding 결과 분포 자체**: 영문 ad-tech query ("consumer behavior in influencer marketing") 에 대한 vertex grounding 이 학술지 도메인 (`springer.com`, `wiley.com`, `tandfonline.com` 등 EXTRA 29 set) 으로 가지 않고 industry / preprint platform / trade publication (forbes, mdpi, medium, researchgate) 으로 가는 것이 본질
2. **ACADEMIC_DOMAINS_29 set vs vertex 결과 set 의 미스매치**: `mdpi.com` / `researchgate.net` 등은 학술 인접하나 B1 final 29 set 에 미포함 (B1 cycle 의 design 결정 — peer-reviewed 학회지 우선 정책)
3. **subdomain 매칭 정책**: `pdfs.semanticscholar.org` 는 base domain `semanticscholar.org` (EXTRA 안) 와 매칭되지 않음 (`ALLOW_SUBDOMAINS` default OFF, settings_gatekeep.py:363)

→ 본 잔존 미달은 **catch 50 scope 외부**. 별 sub-cycle 후보:
- catch 51 후보 — academic-en query 의 vertex grounding 학술 도메인 reach 정량 (vertex grounding bias 측정)
- catch 52 후보 — ACADEMIC_DOMAINS_29 set 보강 (mdpi / researchgate / academic.naver.com 등 후보 검토)
- catch 53 후보 — `ALLOW_SUBDOMAINS` 정책 academic 모드 전용 분기 검토

### 부수 미션 verdict

- **PARTIAL** — academic-ko 단독 임계 0.6 충족 (catch 50 fix 효과 본격 박제), academic-en 단독 0.0 잔존 (별 root cause)
- mean 0.3333 (≥ 0.6 임계 미달) — 부수 미션 success 표기 **금지** (scope creep 경고 박제 정합)

---

## 섹션 5 — business invariant 검증 (회귀 0)

### Jaccard stability (venfobel 3 measure runs, B8 #3 strict 1.0)

| run# | legacy items | domains_unique | domains list |
|---|---|---|---|
| measure 1 | 8 | 4 | `asiatoday.co.kr` · `blog.naver.com` · `dailypharm.com` · `medifonews.com` |
| measure 2 | 8 | 4 | (동일) |
| measure 3 | 8 | 4 | (동일) |

**Jaccard = 1.0 strict** (intersection / union, 3 runs 완전 동일). **B8 #3 (Jaccard mean 1.0 strict) 정합 — 회귀 0.**

### catch 43 bypass 정합 (business mode 손상 0 invariant)

3 measure runs 모두 `q_lang_detected = "n/a"` · `effective_skip_vertex = True` (env `SKIP_VERTEX_SEARCH=1` 그대로) — catch 43 hook 의 `MODE != "academic"` 분기로 진입, business 토픽 손상 0. **catch 50 fix 가 catch 43 routing 에 부작용 0**.

---

## 섹션 6 — 시사점 + close 진입 조건

### 시사점 1 — catch 50 fix 본 미션 PASS, 정량 증거 박제 완료

`clear_runtime_allowed_domains()` 신설 + `reload_config_inplace` hook 이 `_RUNTIME_ALLOWED` upstream invalidate 정합 동작. 정량 증거:
- `[GATEKEEP] n` 보조 지표: academic-ko **79 → 108** (+29 EXTRA 회복)
- academic_source_ratio (academic-ko): **0.0 → 0.6667** 회복
- business invariant Jaccard 1.0 strict — 회귀 0
- 다른 4 지표 PASS — 회귀 0

### 시사점 2 — academic-en 잔존 ratio=0.0 은 catch 50 외부 root cause

영문 ad-tech query 의 vertex grounding 결과 분포가 ACADEMIC_DOMAINS_29 set 과 미스매치. catch 51/52/53 sub-cycle 후보 분리. 본 §academic-2 cycle scope 외.

### 시사점 3 — design budget +15 vs actual +16 (catch 48 lesson 미세 재현)

PEP 8 separator blank line (top-level function 사이) design 산식 누락. 107% — §academic-1 catch 48 발화 (185%) 대비 차수 적음. 별 sub-catch 불필요, 향후 design step budget 산식에 separator blank 항목 포함 권장.

### Close 자격 판정

| 미션 | 결과 | verdict |
|---|---|---|
| **본 미션** — catch 50 (gatekeep `_RUNTIME_ALLOWED` upstream 무효화 해소) | 정량 증거 충족 (`[GATEKEEP] n` academic-ko 79→108 회복 + academic-ko ratio 0.0→0.6667) | **PASS** |
| 부수 미션 — academic source ratio mean ≥ 0.6 | mean 0.3333 (임계 미달) · 단, academic-ko 단독 0.6667 충족 · academic-en 0.0 잔존 (catch 50 외부) | **PARTIAL** |
| 회귀 검증 — business invariant + 다른 4 지표 | Jaccard 1.0 strict · 5 metric 회귀 0 | **PASS** |

**close 권장 (사용자 결정 영역)**:
- 본 미션 PASS + 회귀 0 → §academic-2 cycle close 자격 충족
- 부수 미션 PARTIAL 은 catch 51/52/53 sub-cycle 후보로 분리 등록 (별 cycle)
- scope creep 경고 박제 정합: close 표기 시 부수 미션 success 표기 금지, 부수 미션 PARTIAL + catch 51-53 후보 등록 명시 의무

---

## STOP-4 — Step C-2 측정 결과 사용자 컨펌 대기

본 박제 commit 후 다음 사용자 결정 필요:

1. **close 진입 여부**: 본 미션 PASS + 부수 미션 PARTIAL 정합 수용하여 §academic-2 close vs 부수 미션 회복 (academic-en) 까지 본 cycle 안 시도
2. **catch 51/52/53 후보 등록**: vertex grounding bias / ACADEMIC_DOMAINS_29 보강 / `ALLOW_SUBDOMAINS` 정책 — README-dev catch index 등록 여부 + 등록 시 우선순위
3. **close commit message 박제 내용**: 정량 결과 ([GATEKEEP] n academic-ko 79→108 + ratio 0.0→0.6667) 명시 형식

자율 close 진행 금지 (STOP-4). 본 박제 commit 후 사용자 컨펌 대기.

---

## Self-check protocol

- [x] commit `3598568` C-1 fix 본체 단일 commit (B8 #4 정합) — 측정 결과 본 박제 별 commit 분리
- [x] driver 재사용 (`scripts/§academic-1/measure_ab.py`, B8 #2 정합) — 신규 driver 작성 0
- [x] business invariant Jaccard 1.0 strict (B8 #3 정합) — 3 measure runs 완전 동일 4-domain set
- [x] catch 50 fix 정량 증거 박제 — `[GATEKEEP] n` academic-ko 79→108 회복 + academic_source_ratio 0.0→0.6667
- [x] 본 미션 / 부수 미션 분리 (scope creep 경고 박제 정합) — 섹션 4 명시 + close 자격 분리
- [x] 박제 chain reference 명시 — design commit `33f0cf0` + follow-up `4b75bc5` + C-1 fix `3598568` + 본 박제
- [x] raw 자산 박제 — `c_verification.json` + `c_verification_run.log` (driver hard-coded path `§academic-1/c_ab_*` 로부터 cp, `.gitignored`)
- [x] git status 깨끗 (본 박제 file 외 변경 없음) — `git status --short -- writer_project/scripts/output/§academic-2/` 결과 `step_c_impl_measurement.md` 만 untracked. raw 자산 `c_verification.{json,log}` 은 `.gitignored` (정합)
