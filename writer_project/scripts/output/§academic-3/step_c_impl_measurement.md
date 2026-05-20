# §academic-3 Step C — Implementation + Measurement (박제)

> **박제 chain reference**
> - 직전: §academic-3 Step B design (commit `8d6d2e4`) + Step B follow-up (commit `ddc59a4`, Risk + PARTIAL 박제)
> - 본 Step 자산:
>   · code: `scripts/§academic-1/measure_ab.py` (set literal 재구성 + 9 카테고리 헤더 + 변수 재명명) + 3 토픽 `topics/academic-*.env` (`ALLOWED_DOMAINS_EXTRA` 36 entries 동기 갱신)
>   · driver: `scripts/§academic-1/measure_ab.py` (재사용, B3 정합)
>   · raw: `scripts/output/§academic-3/c_verification.json` (.gitignored, cp from `§academic-1/c_ab_results.json` driver staging) · `c_verification_run.log` (.gitignored, log cp 누락 — staging area `§academic-1/c_ab_run.log` 본 측정 정합)
> - commit chain (본 Step): `296d09d` (C-1 fix 본체 단일 commit) · 본 박제 (C-2 측정 결과 별 commit, §academic-2 B8 #4 결정 정합)
> - 측정 환경: `.venv_vertex` · python 3.12.10 · `LLM_PROVIDER=vertexai` · BOOK-DPUCVR08TC
> - 측정 시각: 2026-05-20 20:21~20:36 KST (15 runs, ~15분 38초 wall · inter-run-sleep 60s · per-run-timeout 90s)

---

## 섹션 1 — 침습 면적 (실제 line diff, commit `296d09d`)

```
 writer_project/README-dev-§14.md                                            |  2 +-
 writer_project/scripts/§academic-1/measure_ab.py                            | 46 +++++++++++++++++-----
 writer_project/topics/academic-_template.env                                |  4 +-
 writer_project/topics/academic-genz-mobile-ad-acceptance.env                |  2 +-
 writer_project/topics/academic-influencer-marketing-consumer-behavior.env   |  2 +-
 5 files changed, 41 insertions(+), 15 deletions(-)
```

| file | hunk | logical | cosmetic |
|---|---|---:|---:|
| `measure_ab.py` | hunk 1 (L137-170): section 헤더 주석 갱신 (1 line) + set literal 재구성 (29 → 36 entries + 9 카테고리 헤더 주석 + PEP 8 separator blank) | +31 | – |
| `measure_ab.py` | hunk 2 (L423): 참조 site 변수명 substitution (`ACADEMIC_DOMAINS_29 → ACADEMIC_DOMAINS`) | 0 (substitution net) | – |
| `topics/academic-_template.env` | hunk 1 (L21-22): 주석 line 1 갱신 + EXTRA 라인 substitution | 0 (substitution net, char +) | – |
| `topics/academic-influencer-marketing-consumer-behavior.env` | hunk 1 (L16): EXTRA 라인 substitution | 0 (substitution net, char +) | – |
| `topics/academic-genz-mobile-ad-acceptance.env` | hunk 1 (L16): EXTRA 라인 substitution | 0 (substitution net, char +) | – |
| `README-dev-§14.md` | hunk 1 (L366): catch 52 진행 상태 갱신 (Step C-1 chain hash 박제) | 0 (substitution net) | – |
| **net logical total** | | **+31** (Step B design 추정 +21 대비 +10 oversize) | 0 |

### Budget 검산 (design D5 산식 +21 vs actual +31)

- **148% of budget** (§academic-1 catch 48 발화 185% / §academic-2 +15→+16 = 107% 대비 차수 중간)
- 차이 원인:
  · 9 카테고리 헤더 주석 사이 PEP 8 separator blank line 8 추가 (가독성 우선)
  · 7 entries 의 inline `#` 주석 행이 stand-alone 1 line 으로 분리 (alpha 순 inline 대비)
- §academic-2 의 +1 oversize (PEP 8 separator 1 누락) lesson 미세 재현 — 차수 확대 (1 line → 10 line)
- **catch 48 lesson 재정착**: design budget 산식에 "literal 재구성 시 카테고리 헤더 별 separator blank line + inline 주석 stand-alone 분리" 항목 명시 권장

### syntax 검산

`ast.parse(measure_ab.py)` 통과 (Step C-1 commit 직후 Claude 측 검증) + driver 정상 실행 + `_status: "complete"` 정합.

---

## 섹션 2 — 5 지표 결과

| # | 지표 | 결과 | 임계 (B3) | verdict |
|---:|---|---|---|---|
| 1 | business invariant (venfobel Jaccard stability + catch 43 bypass) | **Jaccard mean=1.0 strict** (3 measure runs) · bypass=True | =1.0 strict | **PASS** |
| 2 | academic source ratio (B1 36 domains ∩ 출력 source) | mean=**0.4916** (6 academic measure runs) · academic-ko mean=**0.6667** · academic-en mean=**0.3165** | mean ≥ 0.6 | **REVIEW (PARTIAL — 섹션 4 분리)** |
| 3 | lang-detect accuracy (10 labeled queries) | **10/10 = 100%** | ≥ 0.8 | **PASS** |
| 4 | EN→vertex active rate (academic-en measure runs `eff_skip_vertex=False`) | **3/3 = 100%** | = 1.0 | **PASS** |
| 5 | KO→naver active rate (academic-ko measure runs `eff_skip_vertex=True` + `naver_count>0`) | skip=**3/3** · naver_hit=**3/3** | skip=1.0 + naver≥0.8 | **PASS** |

### 보조 지표 — `[GATEKEEP] enabled; allowed=... (n=N)` (catch 52 fix 정합 직접 증거)

| topic | 모든 5 runs (warmup 2 + measure 3) | n | 의미 |
|---|---:|---:|---|
| business-venfobel | 5/5 | **79** | base 78 + 1 normalization (EXTRA 0 — venfobel 토픽 정합, §academic-2 동일) |
| academic-en | 5/5 | **114** | base 78 + EXTRA 36 + 0 normalization ✓ |
| academic-ko | 5/5 | **114** | base 78 + EXTRA 36 + 0 normalization ✓ |

§academic-2 baseline (catch 50 fix 후) 대비:
- business-venfobel: n=79 → n=79 (변화 0, **회귀 0**)
- academic-en: n=108 → **n=114** (+6 EXTRA 회복, +7 신규 entries 중 `sciencedirect.com` 이 base 78 set 과 중복 = net +6)
- academic-ko: n=108 → **n=114** (동일, +6)

→ **catch 52 fix 결정적 정량 증거**: EXTRA set 의 6 도메인 net 추가가 academic 토픽 의 allowed set 에 실시간 반영. `sciencedirect.com` base 중복 발견은 본 측정의 부수 lesson (B1 final 29 + §academic-3 B 추가 7 중 base 와 1 중복 — close 시점 sciencedirect 카테고리 재배치 검토 영역).

---

## 섹션 3 — catch 52 fix 정합 박제 (본 미션 PASS)

### 본 미션 (catch 52 — `ACADEMIC_DOMAINS_29` set 글로벌 학술 플랫폼 누락 해소)

| 검증 항목 | §academic-2 (fix 전) | §academic-3 (fix 후) | 결론 |
|---|---:|---:|---|
| set 정의 entry count | 29 | **36** (29 + 7) | **PASS** — 보강 정합 |
| 변수 재명명 (B2 옵션 B) | `ACADEMIC_DOMAINS_29` | **`ACADEMIC_DOMAINS`** | **PASS** — 숫자 suffix 제거 |
| 9 카테고리 헤더 주석 (B1 옵션 A) | – (alpha 순 단일 set) | **9 헤더** | **PASS** — 가독성 정합 |
| academic-en `academic_domains_hit` (HIGH 4 신규 hit) | mdpi/researchgate/academic.naver/acr-journal 모두 0 hit (set 미등재) | **academic.naver 5/5 · mdpi 5/5 · researchgate 3/5 · acr-journal 0/5** | **PASS** — HIGH 4 중 3개 회수 (acr-journal 은 본 측정 query 분포에서 미회수, §academic-2 의 3/5 대비 query 변동성 영향) |
| academic-en `academic_source_ratio` measure 3 runs | mean=**0.0** | mean=**0.3165** (3 measure runs: 0.4286 / 0.1875 / 0.3333) | **PASS** — set 미등재 → 등재 후 회수 정합 (단, 임계 0.6 미달 — 섹션 4 분리) |
| academic-ko `academic_source_ratio` | mean=0.6667 | mean=**0.6667** | **PASS** — 회귀 0 (5/5 runs 완전 동일 `[dbpia.co.kr, kiss.kstudy.com]`) |
| business invariant Jaccard | 1.0 strict | **1.0 strict** | **PASS** — 회귀 0 |
| `[GATEKEEP] n` academic-ko | 108 | **114** | **PASS** — EXTRA 36 반영 |
| `[GATEKEEP] n` business | 79 | **79** | **PASS** — 회귀 0 |

### 본 미션 PASS 정합 박제

`ACADEMIC_DOMAINS` set 보강 (29 → 36, commit `296d09d`) 이 토픽 .env `ALLOWED_DOMAINS_EXTRA` + driver-side intersection 양쪽 동기 반영. `[GATEKEEP] n` academic 토픽 108 → 114 (+6 net) 정합 + academic-en `academic_domains_hit` 에 신규 entries (mdpi/researchgate/academic.naver) 진입 정합. **catch 52 root cause 정합 해소**.

---

## 섹션 4 — academic source ratio 정량 분리 (부수 미션 PARTIAL)

> **scope creep 경고 박제 정합 + Step B follow-up Risk 박제 정합** — 부수 미션 (academic source ratio mean ≥ 0.6) 은 mean 0.4916 으로 **임계 미달**. 본 미션 PASS 와 별도로 명시 재평가 sub-section 의무. Step B follow-up 의 Risk 박제 (예상 ≈ 0.31) 와 실측 (0.3165) **정합 ✓**.

### academic-ko (mean ratio 0.6667 — 임계 충족, 회귀 0)

| run | `q_lang` | `effective_skip_vertex` | all_domains_unique | academic_hits | ratio |
|---|---|---|---|---|---:|
| measure 2 | ko | True | `{blog.naver.com, dbpia.co.kr, kiss.kstudy.com}` | `[dbpia.co.kr, kiss.kstudy.com]` | **0.6667** |
| measure 3 | ko | True | (동일) | (동일) | **0.6667** |
| measure 4 | ko | True | (동일) | (동일) | **0.6667** |

- 결정성: 5/5 runs 완전 동일 (warmup 2 + measure 3) — naver_direct backend 가 dbpia / kiss.kstudy 안정 회수 + gatekeep 통과 (catch 50 + catch 52 fix 누적 정합)
- §academic-2 baseline 0.6667 대비 동일 — **회귀 0 PASS**

### academic-en (mean ratio 0.3165 — 임계 미달, **catch 52 외부 root cause**)

| run | `q_lang` | `vertex_items` | all_domains_unique 샘플 | academic_hits | ratio |
|---|---|---:|---|---|---:|
| measure 2 | en | 6 | `{academic.naver, eyes4research, forbes, intelliplans, mdpi, medium, researchgate}` | `[academic.naver, mdpi, researchgate]` | **0.4286** |
| measure 3 | en | 15 | (16-domain set, mdpi/researchgate/forbes/medium 외 13 ad-tech) | `[academic.naver, mdpi, researchgate]` | **0.1875** |
| measure 4 | en | 5 | `{academic.naver, forbes, intelliplans, mdpi, medium, mintel}` | `[academic.naver, mdpi]` | **0.3333** |

- mean (3 measure runs) = (0.4286 + 0.1875 + 0.3333) / 3 = **0.3165** ← Step B follow-up Risk 박제 (예상 ≈ 0.31) **정합 ✓**
- 5 runs 의 academic_hits 합집합: `{academic.naver, mdpi, researchgate}` (HIGH 3 회수) — `acr-journal` 0 hit (§academic-2 baseline 3/5 대비 본 측정 query 분포 변동)
- §academic-2 의 mean 0.0 → §academic-3 mean 0.3165 = **+0.3165 회복** (catch 52 fix 정량 증거)

#### 잔존 미달 root cause (catch 52 외부)

| 요인 | 분석 | 책임 cycle |
|---|---|---|
| 1. vertex grounding 결과 분포 자체 | academic-en query ("consumer behavior in influencer marketing") 의 vertex grounding 결과가 여전히 industry / preprint platform / trade publication (forbes / medium / mintel / intelliplans / eyes4research 등) 으로 편향. 본 측정 vertex_items 평균 8.7 / run, 그 중 학술 도메인 평균 ~2 (mdpi + researchgate) | **catch 51** (vertex grounding 학술 도메인 reach 정량, 영문 ad-tech bias) |
| 2. subdomain 매칭 정책 | 본 측정 academic-en 도메인에 subdomain 형태 등재 없음 (§academic-2 의 `pdfs.semanticscholar.org` 본 측정 미관측) → 본 측정에선 catch 53 영향 0. 향후 query 분포 변화 시 재발 가능 | **catch 53** (`ALLOW_SUBDOMAINS` academic 모드 전용 분기) — 본 측정 결과상 우선순위 낮음 |
| 3. MID 3 entries (`sciencedirect` / `journalofadvertising` / `aom`) 자연 진입 0 | 본 측정 5 runs 합집합에 MID 3 모두 0 hit. set 등재만으로는 ratio 회복 불가 — vertex grounding 이 해당 도메인을 자연 회수하지 않음 | **catch 51 (vertex bias)** + **catch 45** (`journalofadvertising.org` SSL/접속 별 영역) |

→ 본 잔존 미달은 **catch 52 scope 외부**. catch 51 / catch 45 / catch 53 sub-cycle 영역 (Step B follow-up Risk 박제 정합).

### 부수 미션 verdict

- **PARTIAL** — academic-ko 단독 임계 0.6 충족 (catch 52 fix 효과 +6 EXTRA 회복 + 회귀 0 박제), academic-en 단독 0.3165 잔존 (catch 52 fix 로 0.0 → 0.3165 회복, 그러나 임계 0.6 미달)
- mean 0.4916 (≥ 0.6 임계 미달) — 부수 미션 success 표기 **금지** (scope creep 경고 박제 + Step B follow-up Risk 박제 정합)

---

## 섹션 5 — business invariant 검증 (회귀 0)

### Jaccard stability (venfobel 3 measure runs, B8 #3 strict 1.0)

| run# | legacy items | domains_unique | domains list |
|---|---|---|---|
| measure 2 | 8 | 4 | `asiatoday.co.kr` · `blog.naver.com` · `dailypharm.com` · `medifonews.com` |
| measure 3 | 8 | 4 | (동일) |
| measure 4 | 8 | 4 | (동일) |

**Jaccard = 1.0 strict** (intersection / union, 3 runs 완전 동일). **§academic-2 baseline 정합 — 회귀 0.**

### catch 43 bypass 정합 (business mode 손상 0 invariant)

3 measure runs 모두 `q_lang_detected = "n/a"` · `effective_skip_vertex = True` (env `SKIP_VERTEX_SEARCH=1` 그대로). **catch 52 fix 가 catch 43 routing 에 부작용 0** + **`[GATEKEEP] n` business 79 회귀 0 (set 보강이 business 토픽 EXTRA 에 누설 0)**.

---

## 섹션 6 — 시사점 + close 진입 조건

### 시사점 1 — catch 52 fix 본 미션 PASS, 정량 증거 박제 완료

`ACADEMIC_DOMAINS` set 보강 (29 → 36) 이 토픽 .env + driver-side intersection 양쪽 동기 반영 정합. 정량 증거:
- `[GATEKEEP] n` 보조 지표: academic-ko/en **108 → 114** (+6 net 회복, base 와 1 중복 `sciencedirect.com` 정합)
- academic_source_ratio (academic-en): **0.0 → 0.3165** 회복 (+0.3165, HIGH 3 entries `mdpi`/`researchgate`/`academic.naver` 회수)
- academic-ko ratio 0.6667 + business Jaccard 1.0 strict 회귀 0
- 5 metric 중 4 PASS + 1 REVIEW (PARTIAL) — 회귀 0

### 시사점 2 — academic-en 잔존 ratio=0.3165 은 catch 52 외부 root cause

영문 ad-tech query 의 vertex grounding 결과 분포가 여전히 산업 매체 편향. catch 51 (vertex grounding bias) 우선 진입 권고. catch 53 (subdomain 매칭) 본 측정 영향 0 — 우선순위 낮음. catch 45 (`journalofadvertising.org` SSL/접속) 별 cycle 영역 분리. **본 §academic-3 cycle scope 외**.

### 시사점 3 — design budget +21 vs actual +31 (catch 48 lesson 재현, 148%)

§academic-2 (+15 → +16, 107%) 의 PEP 8 separator 1 누락 lesson 이 본 cycle 에서 9 카테고리 헤더 separator 8 line + inline `#` 주석 stand-alone 분리로 차수 확대 (10 line). **catch 48 lesson 재정착**: 향후 design budget 산식에 "literal 재구성 시 카테고리 헤더별 separator + inline 주석 stand-alone 분리" 항목 명시 권장.

### 시사점 4 — sciencedirect.com base 78 중복 발견 (lesson)

§academic-3 B 추가 7 entries 중 `sciencedirect.com` 이 base 78 set (`_BASE_ALLOWED_DOMAINS`) 에 이미 존재 — `[GATEKEEP] n` +6 (예상 +7 - 1) 정합. **lesson**: 향후 set 보강 cycle 의 audit 산식에 "base set vs 보강 후보 dedup pre-check" 항목 추가 권장. 본 cycle 의 net 효과는 영향 없음 (의도된 EXTRA 가 base 에 이미 있어 회로 효과 변화 0), close 시점 sciencedirect 카테고리 재배치 또는 EXTRA 제거 검토.

### Close 자격 판정

| 미션 | 결과 | verdict |
|---|---|---|
| **본 미션** — catch 52 (`ACADEMIC_DOMAINS` set 글로벌 학술 플랫폼 누락 해소) | 정량 증거 충족 (`[GATEKEEP] n` 108→114 + academic-en ratio 0.0→0.3165 + HIGH 3 entries 회수) | **PASS** |
| 부수 미션 — academic source ratio mean ≥ 0.6 | mean 0.4916 (임계 미달) · 단, academic-ko 단독 0.6667 충족 · academic-en 0.3165 잔존 (catch 52 외부) · Step B follow-up Risk 박제 (예상 0.31) 정합 | **PARTIAL** |
| 회귀 검증 — business invariant + 다른 4 지표 | Jaccard 1.0 strict · 5 metric 회귀 0 | **PASS** |

**close 권장 (사용자 결정 영역)**:
- 본 미션 PASS + 회귀 0 → §academic-3 cycle close 자격 충족
- 부수 미션 PARTIAL 은 catch 51 / catch 45 sub-cycle 후보로 분리 등록 (catch 53 본 측정 영향 0 — 우선순위 낮음, 단 별 cycle 후보 보존)
- scope creep 경고 박제 + Step B follow-up Risk 박제 정합: close 표기 시 부수 미션 success 표기 금지, 부수 미션 PARTIAL + catch 51/45/53 후보 등록 명시 의무

### 신규 catch 등록 후보 (catch 54+, close 시점 검토)

| 후보 | 영역 | 1줄 description | priority |
|---|---|---|---|
| **catch 54** | docstring stale | `measure_ab.py:13` docstring "per-run-timeout 240s" 가 §academic-1 C-3 default 변경 (90s) 후 미동기화. 코드 본문 (line 130-133 + 600) 은 갱신 완료, module-level docstring 만 stale. **fix 면적 = 1 line substitution** | LOW |
| **catch 55** | Claude Code 환경 .env detection mismatch | bash_tool/WSL 측에서 `.env.vertex` MISSING 보고, 사용자 PowerShell session 측에서 EXISTS (3284 bytes, 2026-05-09). false negative 사례 박제 — `.gitignored` private credentials 정합. **fix 면적 = 0 (Claude Code 한계, 사용자 워크플로 컨벤션 박제)**. README-dev 의 §12-23 박제 영역에 cross-reference 추가 | LOW |
| **catch 56** | driver args output 경로 부재 | `measure_ab.py:608` `out_dir = ... / "§academic-1"` hard-coded — 매 cycle 마다 사용자가 cp 해야 박제. `--output-dir` argparse 추가 시 cycle-aware staging 가능. **fix 면적 = +5 line (argparse arg + out_dir 분기)** | LOW-MID |

→ 본 §academic-3 cycle close commit 시 catch 54/55/56 등록 검토 (사용자 결정 영역).

---

## STOP-4 — Step C-2 측정 결과 사용자 컨펌 대기

본 박제 commit 후 다음 사용자 결정 필요:

1. **close 진입 여부**: 본 미션 PASS + 부수 미션 PARTIAL 정합 수용하여 §academic-3 close vs 부수 미션 회복 (catch 51 진입) 까지 본 cycle 안 시도
2. **catch 54/55/56 등록 여부**: 신규 catch 등록 검토 + 등록 시 priority
3. **sciencedirect 처리 정책**: base 78 중복 발견 — 카테고리 재배치 또는 EXTRA 제거 vs 그대로 두기 (효과 동일, 가독성 영향)
4. **close commit message 박제 내용**: 정량 결과 (`[GATEKEEP] n` academic 108→114 + academic-en ratio 0.0→0.3165) 명시 형식

자율 close 진행 금지 (STOP-4). 본 박제 commit 후 사용자 컨펌 대기.

---

## Self-check protocol

- [x] commit `296d09d` C-1 fix 본체 단일 commit (§academic-2 B8 #4 정합) — 측정 결과 본 박제 별 commit 분리
- [x] driver 재사용 (`scripts/§academic-1/measure_ab.py`, B3 정합) — 신규 driver 작성 0 (Step C-1 fix 의 set literal + 참조 site update 외 driver 본문 변경 0)
- [x] business invariant Jaccard 1.0 strict (B8 #3 정합) — 3 measure runs 완전 동일 4-domain set, §academic-2 baseline 정합
- [x] catch 52 fix 정량 증거 박제 — `[GATEKEEP] n` academic 108→114 회복 + academic-en `academic_source_ratio` 0.0→0.3165 + HIGH 3 entries (mdpi/researchgate/academic.naver) 회수
- [x] 본 미션 / 부수 미션 분리 (scope creep 경고 박제 + Step B follow-up Risk 박제 정합) — 섹션 4 명시 + close 자격 분리
- [x] Step B follow-up Risk 박제 (예상 0.31) ↔ 실측 (0.3165) 정합 ✓
- [x] catch 48 lesson 재현 박제 (design +21 vs actual +31 = 148%, §academic-2 의 107% 차수 확대)
- [x] 박제 chain reference 명시 — design commit `8d6d2e4` + follow-up `ddc59a4` + C-1 fix `296d09d` + 본 박제
- [x] raw 자산 박제 — `c_verification.json` cp (`.gitignored`) · log cp 누락 (staging area `§academic-1/c_ab_run.log` 본 측정 정합 — close 시점 cp 또는 catch 56 (driver args output 경로) 영역
- [x] 신규 catch 54/55/56 후보 등록 (close 시점 검토)
