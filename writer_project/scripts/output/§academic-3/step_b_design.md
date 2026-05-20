# §academic-3 Step B design (read-only)

> **박제 chain reference**
> - 직전 자산: §academic-3 Step A entry audit (commit `10541d2`) + Step A follow-up (commit `28fe7f9`, 사용자 결정 ①~④ 박제)
> - 본 design 대상 catch: catch 52 (ACADEMIC_DOMAINS_29 set 글로벌 학술 플랫폼 누락)
> - design 범위: D1 (set 코드 반영) + D2 (변수 재명명 영향) + D3 (측정 계획) + D4 (STOP/Self-check) + D5 (commit 정책) — **read-only**
> - design driver: 미사용 (grep + view 만으로 충분)
> - 환경: PowerShell · BOOK-DPUCVR08TC · HEAD = `28fe7f9`

---

## Cycle decisions (B1~B5 박제)

| # | 영역 | 확정 | 사유·정합 근거 |
|---:|---|---|---|
| B1 | set 구조 | **옵션 A** — 단일 set + 카테고리 주석 | inline 카테고리 헤더 주석으로 분류 가독성 확보. dict-of-sets 복잡도 회피 (set intersection 연산 변경 0) |
| B2 | 변수 재명명 | **옵션 B** — `ACADEMIC_DOMAINS_29` → `ACADEMIC_DOMAINS` | 숫자 suffix 제거 — 향후 보강 cycle 마다 재명명 부담 0. driver-side 측정 set 의 의미 안정 |
| B3 | 측정 계획 | **§academic-2 동일 5 metric + `[GATEKEEP] n` 보조 지표** | 패턴 정합 + 변경 가독성 (회귀 vs 본 미션 증거 분리) |
| B4 | STOP/Self-check | **5 STOP + 5 Self-check** (D4 명세) | §academic-2 B8 패턴 + 본 cycle 특화 (catch 53 분리, subdomain 매칭 미수정) |
| B5 | 박제 산출 | **§academic-2 패턴 5 commits** | Step B design / (follow-up 필요시) / C-1 fix / C-2 측정 / close — 변경 size 정합 |

---

## D1 — 7 entries 코드 반영 설계

### 정의 위치 (현 상태)

- `writer_project/scripts/§academic-1/measure_ab.py:137` — section 헤더 주석 `# ── B1 final 29 academic domains (§academic-1 Step B 박제 정합) ───`
- `writer_project/scripts/§academic-1/measure_ab.py:138-146` — `ACADEMIC_DOMAINS_29 = { ... }` (29 entries set literal, 9 line block)
- `writer_project/scripts/§academic-1/measure_ab.py:397` — 참조 site `academic_domains = sorted(set(all_domains_set) & ACADEMIC_DOMAINS_29)`

### Patch 미리보기 (B1 옵션 A + B2 옵션 B)

```python
# before (measure_ab.py:137-146)
# ── B1 final 29 academic domains (§academic-1 Step B 박제 정합) ───────────────
ACADEMIC_DOMAINS_29 = {
    "academic.oup.com", "ama.org", "arxiv.org", "dbpia.co.kr", "doaj.org",
    "emerald.com", "journals.sagepub.com", "jstor.org", "kadpr.or.kr",
    "kci.go.kr", "kiss.kstudy.com", "link.springer.com", "mmaglobal.com",
    "msi.org", "onlinelibrary.wiley.com", "openalex.org", "papers.ssrn.com",
    "plos.org", "pmc.ncbi.nlm.nih.gov", "pubsonline.informs.org", "riss.kr",
    "sagepub.com", "science.org", "semanticscholar.org", "springer.com",
    "ssrn.com", "tandfonline.com", "warc.com", "wiley.com",
}

# after (§academic-3 B 보강 7 entries + B1 옵션 A 카테고리 주석 + B2 옵션 B 재명명)
# ── academic domains (§academic-1 B1 final 29 + §academic-3 B 추가 7 = 36) ────
ACADEMIC_DOMAINS = {
    # Korean academic society / aggregator / search engine
    "dbpia.co.kr", "kadpr.or.kr", "kci.go.kr", "kiss.kstudy.com", "riss.kr",
    "academic.naver.com",          # §academic-3 (academic search, naver_direct hit)

    # Global academic society (advertising / marketing)
    "ama.org", "mmaglobal.com", "msi.org", "pubsonline.informs.org",
    "aom.org",                     # §academic-3 (Academy of Management root)

    # Global publisher (peer-review)
    "academic.oup.com", "emerald.com", "journals.sagepub.com",
    "link.springer.com", "onlinelibrary.wiley.com", "plos.org",
    "sagepub.com", "science.org", "springer.com", "tandfonline.com", "wiley.com",
    "mdpi.com",                    # §academic-3 (OA publisher, marketing journals)
    "sciencedirect.com",           # §academic-3 (Elsevier root, JBR / JoR cover)

    # Global preprint repository
    "arxiv.org", "papers.ssrn.com", "ssrn.com",

    # Global academic archive
    "jstor.org", "pmc.ncbi.nlm.nih.gov",

    # Global academic search engine / scholarly metadata
    "doaj.org", "openalex.org", "semanticscholar.org",

    # Global advertising / marketing journal (peer-review, Sungsu 분야 정합)
    "acr-journal.com",             # §academic-3 (Assoc. for Consumer Research)
    "journalofadvertising.org",    # §academic-3 (Journal of Advertising; catch 45 별 cycle)

    # Global academic SNS (peer-review working paper hosting)
    "researchgate.net",            # §academic-3 (working paper self-archive)

    # Global industry research repository (advertising-specific)
    "warc.com",
}
```

### 카테고리 헤더 9개 (B1 옵션 A)

| # | 카테고리 | n | §academic-3 추가 |
|---:|---|---:|---|
| 1 | Korean academic society / aggregator / search engine | 6 | `academic.naver.com` |
| 2 | Global academic society (advertising / marketing) | 5 | `aom.org` |
| 3 | Global publisher (peer-review) | 13 | `mdpi.com`, `sciencedirect.com` |
| 4 | Global preprint repository | 3 | – |
| 5 | Global academic archive | 2 | – |
| 6 | Global academic search engine / scholarly metadata | 3 | – |
| 7 | Global advertising / marketing journal (Sungsu 분야 정합) | 2 | `acr-journal.com`, `journalofadvertising.org` |
| 8 | Global academic SNS (peer-review working paper hosting) | 1 | `researchgate.net` |
| 9 | Global industry research repository (advertising-specific) | 1 | – |
| **합** | | **36** | **7** |

### 7 entries 추가 line 위치 (after patch 기준)

| # | entry | category line group | priority |
|---:|---|---|---|
| 1 | `academic.naver.com` | #1 Korean (line 5 of after-set) | HIGH |
| 2 | `aom.org` | #2 Global society (line 9) | MID |
| 3 | `mdpi.com` | #3 Publisher (line 14) | HIGH |
| 4 | `sciencedirect.com` | #3 Publisher (line 15) | MID |
| 5 | `acr-journal.com` | #7 Ad/Mkt journal (line 26) | HIGH |
| 6 | `journalofadvertising.org` | #7 Ad/Mkt journal (line 27) | MID |
| 7 | `researchgate.net` | #8 Academic SNS (line 30) | HIGH |

### HIGH/MID priority 주석 정책

- **방침**: priority 주석 미포함 (set literal 본문 가독성 우선)
- priority 정보는 본 design .md (D1 표) + audit .md (A3 표) 에 박제, 코드 .py 본문에는 미반영
- 사유: priority 는 §academic-3 cycle 의 진입 시점 정보 (실측 hit 우선순위), 향후 cycle 진행 시 stale 위험 — 코드는 카테고리 분류 (안정적) 만 노출

### 측정 driver 참조 site 갱신 (measure_ab.py:397)

```python
# before
academic_domains = sorted(set(all_domains_set) & ACADEMIC_DOMAINS_29)

# after
academic_domains = sorted(set(all_domains_set) & ACADEMIC_DOMAINS)
```

### 토픽 .env 의 `ALLOWED_DOMAINS_EXTRA` 라인 갱신

- 3 토픽 .env 의 EXTRA 라인은 set 변수가 아닌 직접 도메인 list (comma-separated) → **변수 재명명 무관, 7 entries 추가만 영향**
- 추가 7 entries (alpha 순 merge):

```
# before (3 file 공통, single line)
ALLOWED_DOMAINS_EXTRA=academic.oup.com,ama.org,arxiv.org,dbpia.co.kr,doaj.org,emerald.com,journals.sagepub.com,jstor.org,kadpr.or.kr,kci.go.kr,kiss.kstudy.com,link.springer.com,mmaglobal.com,msi.org,onlinelibrary.wiley.com,openalex.org,papers.ssrn.com,plos.org,pmc.ncbi.nlm.nih.gov,pubsonline.informs.org,riss.kr,sagepub.com,science.org,semanticscholar.org,springer.com,ssrn.com,tandfonline.com,warc.com,wiley.com

# after (§academic-3 B 추가 7 = 36 entries, alpha 순)
ALLOWED_DOMAINS_EXTRA=academic.naver.com,academic.oup.com,acr-journal.com,ama.org,aom.org,arxiv.org,dbpia.co.kr,doaj.org,emerald.com,journalofadvertising.org,journals.sagepub.com,jstor.org,kadpr.or.kr,kci.go.kr,kiss.kstudy.com,link.springer.com,mdpi.com,mmaglobal.com,msi.org,onlinelibrary.wiley.com,openalex.org,papers.ssrn.com,plos.org,pmc.ncbi.nlm.nih.gov,pubsonline.informs.org,researchgate.net,riss.kr,sagepub.com,science.org,sciencedirect.com,semanticscholar.org,springer.com,ssrn.com,tandfonline.com,warc.com,wiley.com
```

- 영향 file (3개, 모두 동일 patch):
  - `writer_project/topics/academic-_template.env:22`
  - `writer_project/topics/academic-influencer-marketing-consumer-behavior.env:16`
  - `writer_project/topics/academic-genz-mobile-ad-acceptance.env:16`

- 주석 라인 (academic-_template.env:21) 갱신:
```
# before
# ── 학술 도메인 동적 주입 (B1 final 29 entries, §academic-1 Step B 박제) ──

# after
# ── 학술 도메인 동적 주입 (36 entries = B1 29 + §academic-3 B 7) ──
```

---

## D2 — 변수 재명명 영향 범위 (B2 옵션 B)

### grep 결과 전수 사용처

| # | file:line | context | substitution 형태 |
|---:|---|---|---|
| 1 | `writer_project/scripts/§academic-1/measure_ab.py:137` | section 헤더 주석 (`# ── B1 final 29 academic domains ...`) | 주석 본문 + 숫자 substitution (29 → 36, B1 final → B1 final + §academic-3 B) |
| 2 | `writer_project/scripts/§academic-1/measure_ab.py:138` | set literal 정의 (`ACADEMIC_DOMAINS_29 = {`) | 변수명 + literal body 재구성 (카테고리 주석 + 7 entries 추가) |
| 3 | `writer_project/scripts/§academic-1/measure_ab.py:397` | 참조 site (`set intersection`) | 변수명만 |

### 박제 .md 사용처 (이력 보존 — 갱신 X)

| # | file:line | context | 조치 |
|---:|---|---|---|
| 4 | `writer_project/README-dev-§14.md:366` | catch 52 entry description | **Step C-1 commit 에서 진행 상태만 갱신** (변수명 표기는 이력으로 유지) |
| 5 | `writer_project/README-dev-§14.md:439` | §academic-2 close section catch 52 reference | 이력, **갱신 X** |
| 6 | `writer_project/scripts/output/§academic-3/step_a_entry_audit.md` (다수 라인) | 본 cycle audit 박제 | 이력, **갱신 X** |
| 7 | `writer_project/scripts/output/§academic-2/step_b_design.md:201` | 직전 cycle design 박제 | 이력, **갱신 X** |
| 8 | `writer_project/scripts/output/§academic-2/step_c_impl_measurement.md` (109/114/154/180) | 직전 cycle 측정 박제 | 이력, **갱신 X** |
| 9 | `writer_project/scripts/output/§academic-1/step_c_impl_measurement.md:153` | §academic-1 측정 박제 | 이력, **갱신 X** |

### audit summary "4 file × ~5 hunks" 정합 검증

- audit summary 추정 (step_a_entry_audit.md "추정 fix 면적"):
  - "4 file × ~7 entries = 28 substitution, 각 file 의 EXTRA 라인은 단일 line → diff hunk 4개"
  - "driver hunk 2개 (set literal + 참조 site)"
  - 합 **6 hunks** (audit 표기 "~5" 와 근사 정합)
- design 실측 (D2 + D1):
  - 코드: measure_ab.py 3 hunks (line 137 주석 + line 138 literal + line 397 참조)
  - env: 3 토픽 .env 각 1 hunk (line 22/16/16 EXTRA + 1 주석 line, academic-_template.env 만 주석 변경) → 3~4 hunks
  - 합 **6~7 hunks**

- **정합 결론**: audit summary 의 "4 file × ~5 hunks" 와 design 실측 (4 file × 6~7 hunks) 차이 **+1~2 hunk** 사유 = B1 옵션 A 의 카테고리 주석 추가 + 측정 driver 의 section 헤더 주석 update. catch 48 컨벤션 정합 (design budget 산식에 "literal 재구성 line + 주석" 명시).

### 누락 위험 영역 (grep 누락 가능성 점검)

- **string concat / format / `getattr`**: grep 결과 없음 (정합)
- **다른 측정 driver**: `writer_project/scripts/` 하위 다른 driver 검토 — grep 결과 `measure_ab.py` 1개만 (정합)
- **business 모드 토픽 env**: ALLOWED_DOMAINS_EXTRA 없음 (audit A1 정합)
- **dynamic ENV inject**: `settings_gatekeep.py:168` 의 `os.getenv("ALLOWED_DOMAINS_EXTRA")` 는 string 직접 parsing → 변수 재명명 무관

→ **누락 0 컨펌** (Step C-1 commit 전 self-check 항목으로 재확인 의무)

---

## D3 — 측정 계획 (Step C-2 영역 사전 설계)

### Driver

- **measure_ab.py 재사용** (변경 0, set literal + 참조 site update 만 D1 영역)
- catch 49 4 default 자동 적용 (SDK timeout / provider lock / flush stage / probe)
- §academic-2 측정 환경 동일 (`.venv_vertex` · python 3.12.10 · `LLM_PROVIDER=vertexai` · BOOK-DPUCVR08TC)
- per-run-timeout 90s · inter-run-sleep 60s · warmup 2 + measure 3

### Runs

| topic | env | warmup | measure | 합 |
|---|---|---:|---:|---:|
| `business-venfobel` | `topics/venfobel-vitamin.env` | 2 | 3 | 5 |
| `academic-en` | `topics/academic-influencer-marketing-consumer-behavior.env` | 2 | 3 | 5 |
| `academic-ko` | `topics/academic-genz-mobile-ad-acceptance.env` | 2 | 3 | 5 |
| **합** | | | | **15** (≈ §academic-2 패턴) |

### 7 지표 (§academic-2 동일 5 metric + `[GATEKEEP] n` 보조)

| # | 지표 | 본 cycle 임계 | catch 52 영향 |
|---:|---|---|---|
| 1 | business invariant Jaccard | **=1.0 strict** (회귀 0) | 무영향 (set EXTRA 없음) |
| 2 | academic source ratio (mean) | **≥ 0.6** | ★ 본 cycle 핵심 — academic-ko 유지 + academic-en 회복 |
| 2-a | · academic-ko ratio | **≥ 0.6** (유지) | 회귀 0 검증 |
| 2-b | · academic-en ratio | **≥ 0.6** (회복) | ★ catch 52 fix 결정적 본 미션 PASS 조건 |
| 3 | lang-detect accuracy | **= 1.0** (10/10) | 무영향 |
| 4 | EN→vertex active rate | **= 1.0** (3/3) | 무영향 |
| 5 | KO→naver active rate | skip=1.0 + naver≥0.8 | 무영향 |
| 6 | `[GATEKEEP] n` (보조) | business 79 / academic-ko 115 / academic-en 115 | ★ EXTRA 36 반영 직접 증거 |

### Baseline (§academic-2 `c_verification.json` 비교)

| topic | §academic-2 metric 2 | §academic-3 PASS 조건 | §academic-2 `[GATEKEEP] n` | §academic-3 예상 |
|---|---:|---|---:|---:|
| business-venfobel | 0.0 (EXTRA 없음, 정합) | 0.0 유지 | 79 (78 base + 1 norm) | 79 (회귀 0) |
| academic-ko | 0.6667 | ≥ 0.6667 (회귀 0) | 108 (78 base + 29 EXTRA + 1 norm) | **115** (78 + 36 + 1) |
| academic-en | 0.0 | **≥ 0.6** (회복) | 108 | **115** |

- **catch 52 fix 결정적 정량 증거**: `[GATEKEEP] n` academic-en/ko 108 → 115 (+7 EXTRA 반영) + academic-en `academic_source_ratio` 0.0 → ≥0.6 (실측 hit 4개 mdpi/researchgate/academic.naver/acr-journal 가 set 등재 후 ratio 분자 진입)
- **academic-en ratio 예상 계산**:
  - §academic-2 measure 3 runs all_uniq 평균 ~13 도메인 / run · 그 중 4 도메인 (mdpi / researchgate / academic.naver / acr-journal) 평균 hit
  - 예상 ratio ≈ 4/13 = **0.308** ← ★ **PASS 임계 0.6 미달 위험**
  - 추가 hit 가능성: sciencedirect / journalofadvertising / aom (MID, 실측 hit 0) — academic-en query 분포에 자연 진입 여부 측정 후 결정
- **PARTIAL 발화 가능성**: §academic-2 측정 raw 의 academic-en 분포가 5 runs 평균 13 도메인 + HIGH 4 hit 가정 시 ratio ≈ 0.3 → 임계 0.6 미달 → PARTIAL · scope creep 경고 박제 정합으로 **본 미션 PASS 표기 금지**, 임계 재조정 vs catch 53 / catch 51 cycle 진입 결정 필요

### 측정 결과 박제 위치

- `writer_project/scripts/output/§academic-3/step_c_impl_measurement.md`
- raw 자산: `writer_project/scripts/output/§academic-3/c_verification.json` (`.gitignored`, §academic-2 패턴 정합)

---

## D4 — STOP gates & Self-check

### STOP gates (Step C 영역, 5개)

| # | 발화 조건 | 대응 |
|---:|---|---|
| STOP-1 | set 외 영역 코드 수정 시도 (settings_gatekeep.py / core/config.py / agent/* 본체) | 즉시 중단 — 본 cycle 은 set literal + 참조 site + env EXTRA 라인만 변경 |
| STOP-2 | 변수 재명명 시 grep `ACADEMIC_DOMAINS_29` 결과 잔존 (코드 영역) | Step C-1 commit 전 즉시 grep 재실행 + 누락 0 컨펌. 박제 .md 의 이력 reference 는 STOP-2 영역 외 (D2 정합) |
| STOP-3 | business invariant 회귀 (Jaccard < 1.0 strict 또는 `[GATEKEEP] n` business ≠ 79) | 측정 중 발화 시 fix rollback + 원인 분석 |
| STOP-4 | subdomain 매칭 로직 (catch 53 영역) 건드림 | `settings_gatekeep.py:363` `ALLOW_SUBDOMAINS` flag 본 cycle 미변경. `pdfs.semanticscholar.org` 매칭은 catch 53 별 cycle 영역 |
| STOP-5 | 측정 commit 전 사용자 컨펌 누락 | Step C-2 박제 commit 후 push 금지, 사용자 컨펌 후 close 진입 |

### Self-check (Step C-1 commit 전, 5개)

| # | 항목 | 검증 방법 |
|---:|---|---|
| ① | 7 entries 정확히 추가 (HIGH 4 + MID 3, 누락 0) | grep 으로 7 도메인 각각 measure_ab.py + 3 env file 모두 등재 컨펌 |
| ② | 변수 재명명 누락 0 | `grep -rn "ACADEMIC_DOMAINS_29" writer_project/scripts writer_project/topics` 결과 코드 영역 0건 |
| ③ | README-dev §14 catch 52 진행 상태 갱신 | `Step A audit 완료 ...` → `Step C-1 fix 완료 (commit ...)` 등 갱신 (catch 표기 1줄 description 병기) |
| ④ | 카테고리 주석 추가 (B1 옵션 A 정합) | measure_ab.py:138-... set literal 본문에 9 카테고리 헤더 주석 포함 검증 |
| ⑤ | catch 표기 1줄 description 병기 | commit message + README-dev entry 모두 `catch 52 (ACADEMIC_DOMAINS_29 set 글로벌 학술 플랫폼 누락)` 형태 |

---

## D5 — 박제 산출 (commit 정책)

### §academic-2 패턴 정합 — 5 commits

| # | commit subject | 자산 | 변경 size 추정 |
|---:|---|---|---|
| 1 | `§academic-3 Step B — design (read-only)` | `scripts/output/§academic-3/step_b_design.md` (본 doc) | 단일 .md, +200~300 line (insertion only) |
| 2 (필요시) | `§academic-3 Step B follow-up — ...` | B1~B5 결정 후속 박제 (audit.md ↔ design.md 간 정합 보강) | 작은 patch |
| 3 | `§academic-3 Step C-1 — catch 52 fix 본체 (set 보강 + ACADEMIC_DOMAINS 재명명)` | measure_ab.py + 3 토픽 .env | **추정 +21 logical line (set literal 재구성) + 3 substitution (변수명/참조/주석) + 3 env EXTRA 라인 substitution (net 0 logical, char count +)** |
| 4 | `§academic-3 Step C-2 — 측정 결과 박제 (catch 52 fix 정량 증거)` | `step_c_impl_measurement.md` + raw `.json/.log` (gitignored) | 단일 .md, ~150~200 line |
| 5 | `§academic-3 close — catch 52 (ACADEMIC_DOMAINS_29 set 글로벌 학술 플랫폼 누락) fix` | README-dev-§14.md 갱신 (catch 52 close section + 신규 catch 등록 가능) | README +20~50 line |

### Budget 산정 (catch 48 컨벤션)

| 산식 항목 | 추정 line |
|---|---:|
| (a) config 변경 (3 토픽 .env EXTRA 라인 substitution) | 0 logical net (char +) |
| (b) in-place hook insert | 0 |
| (c) 신규 함수 정의 본체 | 0 (catch 48 lesson 정합 — 신규 def 없음) |
| (d) substitution net (변수 재명명 + 참조 + 주석 헤더 update) | +3 substitution (net 0 logical) |
| (e) literal 재구성 (B1 옵션 A 카테고리 주석 + 7 entries 추가) | **+21** (기존 9 line → 새 ~30 line) |
| **합 (Step C-1 logical net)** | **+21** |

- **catch 48 lesson 정합**: 신규 def 0 / hook 0 — substitution + literal 재구성 만으로 fix 면적 산정. §academic-2 (+15 → 실제 +16, 107%) 대비 fix 면적 ~40% 큼 (literal 재구성 사유). 실측 대비 design budget oversize 15% 이내 권장.

### Push 정책

- 본 design commit + Step B follow-up (필요시) → local 만, 사용자 컨펌 후 push
- §academic-2 동일 패턴 (close commit 후 일괄 push)

---

## Design summary

### 추정 fix 면적 (catch 48 컨벤션)

- **4 file × 6~7 hunks** (measure_ab.py 3 + 3 토픽 .env 3~4)
- logical net **+21 line** (literal 재구성 + 카테고리 주석)
- 함수 본체 / hook / 신규 def / test fixture 변경 **0**
- READ ME-dev-§14.md 별 commit (Step C-1 + close)

### catch 52 fix 면적 정합성

- audit summary 추정 "4 file × ~5 hunks" vs design 실측 "4 file × 6~7 hunks" — **+1~2 hunk 차이** 사유:
  - B1 옵션 A 의 카테고리 주석 9 헤더 추가
  - section 헤더 주석 (measure_ab.py:137) 본문 update
- 차이 catch 48 컨벤션 정합 — design budget 산식에 명시 (산식 (e) literal 재구성)

### Step C 진입 조건 충족 여부

| 진입 조건 | 충족 |
|---|:---:|
| set 보강 후보 7 entries 확정 (Step A audit + follow-up) | ✓ |
| 변수 재명명 정책 확정 (B2 옵션 B `ACADEMIC_DOMAINS`) | ✓ |
| set 구조 결정 (B1 옵션 A 단일 set + 카테고리 주석) | ✓ |
| 측정 계획 박제 (B3 §academic-2 패턴 + `[GATEKEEP] n`) | ✓ |
| STOP gates + Self-check 박제 (B4) | ✓ |
| commit 정책 박제 (B5 §academic-2 패턴 5 commits) | ✓ |
| fix 면적 budget 산식 (catch 48 컨벤션) | ✓ +21 logical |
| business invariant 보호 strategy (STOP-3) | ✓ |
| subdomain 영역 분리 (STOP-4 catch 53) | ✓ |

→ **Step C 진입 자격 충족**. 본 design commit + 사용자 컨펌 후 Step C-1 진입.

### Risk 박제 (D3 PARTIAL 발화 가능성)

- **academic-en ratio 임계 0.6 미달 위험**: §academic-2 raw (academic-en) 5 runs 평균 ~13 도메인 / HIGH 4 hit 가정 시 ratio ≈ **0.31** → 임계 미달 가능
- 발화 시 대응:
  · 본 미션 PASS 표기 금지 (scope creep 경고 박제 정합)
  · 정량 증거로 `[GATEKEEP] n` academic-en 108 → 115 (+7 EXTRA 반영) 박제 — set 보강 자체는 정합 동작
  · 잔존 ratio 임계 미달 root cause = catch 51 (vertex grounding bias) + catch 53 (subdomain 매칭) 분리
  · §academic-3 cycle 종결 verdict = PARTIAL (catch 52 set 보강 PASS · 부수 academic-en ratio PARTIAL 잔존)

### STOP-1 (resolved 2026-05-20) — Step B design 컨펌 대기 (이력 보존)

본 design draft commit 전 사용자 결정 영역 (resolved, 아래 "사용자 결정 박제 (확정)" 섹션 참조):

1. **D1 카테고리 주석 9 헤더 형태**: 정합 vs 단순 alpha 순 (no 헤더) 선택
2. **D1 priority 주석 (HIGH/MID) 코드 본문 포함 여부**: 본 design 미포함 정책 vs 코드 본문 inline 박제
3. **D3 PASS 임계 0.6 유지 vs 조정**: academic-en ratio 예상 0.31 → 임계 0.6 미달 위험. 임계 유지 (PARTIAL 수용) vs 임계 조정 (`[GATEKEEP] n` 회복만 PASS 조건) 결정
4. **D5 Step B follow-up commit 필요 여부**: B1~B5 결정 박제는 본 design .md 에 이미 포함 — follow-up commit 생략 vs §academic-2 패턴 정합 (4b75bc5 follow-up) 위해 추가

자율 Step C-1 진입 금지 (STOP-1). 본 draft commit 후 사용자 컨펌 대기 → **resolved 2026-05-20**.

---

### 사용자 결정 박제 (확정, 2026-05-20)

> Step B design draft commit `8d6d2e4` 직후 사용자 컨펌 영역 4개 모두 결정. Step C-1 진입 자격 충족 (단, PARTIAL Risk 박제 정합 정착).

| # | 결정 영역 | 확정 | 사유·정합 근거 |
|---:|---|---|---|
| ① | D1 카테고리 주석 | **9 헤더 채택** (B1 옵션 A 정합) | Korean / Global society / Publisher / Preprint / Archive / Search / Ad-Mkt journal / Academic SNS / Industry research 의 9 카테고리 헤더. alpha 순 미채택 — B1 옵션 A 의도 정합 + 미래 보강 cycle (catch 51/53 등) 비용 절감 (카테고리 분류 안정, 추가 entry 의 소속 명확) |
| ② | D1 priority (HIGH/MID) 주석 | **미포함** (현 design 정책 유지) | priority 는 §academic-3 audit 시점 분류 (실측 hit 우선순위) — 시간 지나면 의미 흐려짐. 추적성은 design .md (D1 표) + audit .md (A3 표) + `git blame` 으로 충분. 코드 본문은 카테고리 (안정) 만 노출 |
| ③ | D3 PASS 임계 | **0.6 유지 + PARTIAL 수용** | 평가 기준 일관성 유지 (§academic-2 패턴 정합). 임계 조정 (`[GATEKEEP] n` 회복만 PASS) 미채택 — set 보강 자체는 `[GATEKEEP] n` 108 → 115 로 정합 박제, 그러나 academic-en ratio 임계 0.6 미달은 catch 52 외부 root cause (catch 51/53) 영역 — verdict 분리로 책임 영역 박제 |
| ④ | D5 Step B follow-up commit | **진행** | §academic-2 `4b75bc5` (B8 follow-up) 패턴 정합. B1~B5 결정 + Risk 박제 + PARTIAL verdict 의미 명시는 design 본문 외 후속 영역 (이력 보존 + STOP-2 정합) |

---

### Risk 박제 — PARTIAL verdict 의미 분리 (STOP-4 정합)

> §academic-2 측정 raw 분포 기반 사전 추정. catch 52 책임 영역 vs catch 51/53 책임 영역 명확히 분리하여 scope creep 경고 박제 정합.

#### 사전 추정 — academic-en ratio ≈ 0.31

- §academic-2 c_verification.json `academic-en` measure 3 runs `all_uniq` 평균 ~13 도메인 / run
- HIGH 4 (mdpi / researchgate / academic.naver / acr-journal) 실측 hit 평균 4 도메인 / run
- 예상 ratio = 4 / 13 ≈ **0.308** ← 임계 0.6 미달
- MID 3 (sciencedirect / journalofadvertising / aom) 실측 hit 0 — academic-en query 분포에 자연 진입 여부 불확정 (측정 후 확정)

#### catch 52 책임 영역 (본 cycle 본 미션 PASS 조건)

| 정량 증거 | 임계 | 의미 |
|---|---|---|
| `[GATEKEEP] n` business 79 / academic-ko 115 / academic-en 115 | business=79 (회귀 0) · academic n=115 (=78 base + 36 EXTRA + 1 norm) | ★ catch 52 set 보강 정합 직접 증거 — EXTRA 36 반영 |
| academic-ko ratio | ≥ 0.6667 (유지) | 회귀 0 검증 |
| business invariant Jaccard | = 1.0 strict | 회귀 0 검증 |
| `academic_domains_hit` 의 HIGH 4 entry 회수 | hit ≥ 1 / 5 runs | catch 52 set 등재 후 ratio 분자 진입 정합 |

→ 위 4 정량 증거 충족 시 **catch 52 본 미션 PASS** — set 보강 정합 박제. ratio 임계 0.6 미달은 별 cycle 영역.

#### 잔존 영역 (catch 52 외부 — 별 cycle 후보)

| catch | 책임 영역 | 1줄 description |
|---|---|---|
| **catch 51** | vertex grounding 학술 도메인 reach 정량 (영문 ad-tech bias) | academic-en query ("consumer behavior in influencer marketing") 의 vertex grounding 결과 분포가 industry / preprint / trade publication (forbes / medium / mintel 등) 으로 편향 — 학술지 도메인 reach 자체 가 0 또는 낮음. **외부 의존 (vertex 검색 엔진 정책) — 우리 제어 면적 작음** |
| **catch 53** | `ALLOW_SUBDOMAINS` academic 모드 전용 분기 검토 | `pdfs.semanticscholar.org` 등 subdomain 이 base domain (`semanticscholar.org`) 매칭 안 됨. `settings_gatekeep.py:363` `ALLOW_SUBDOMAINS=False` default → academic 모드 전용 ON 검토 (business 모드 invariant 정합성 사전 검증 필요) |

#### PARTIAL verdict 처리 정책

- **본 미션 (catch 52)**: PASS — `[GATEKEEP] n` 회복 + academic-ko 회귀 0 + business invariant 회귀 0 정합
- **부수 미션 (academic-en ratio ≥ 0.6)**: PARTIAL (예상 ≈ 0.31, 임계 미달) — scope creep 경고 박제 정합으로 본 cycle 안 시도 금지
- **§academic-3 close 표기**: 본 미션 PASS + 부수 미션 PARTIAL + catch 51/53 sub-cycle 후보 등록 (§academic-2 close 패턴 정합)
- **임계 미달 시 임계 재조정 금지**: 평가 기준 일관성 유지 (결정 ③ 정합)

#### Step C 측정 후 분기 결정 영역

- academic-en ratio 측정 결과 ≥ 0.6 → 부수 미션 PASS (예상 외 결과, MID 3 자연 진입 가정)
- ratio 0.3 < x < 0.6 → 부수 미션 PARTIAL (예상 정합) · catch 51/53 cycle 진입 결정 사용자 영역
- ratio < 0.3 → 부수 미션 FAIL (예상 미달) · catch 52 set 보강 외 외부 root cause 강함 → catch 51 우선 진입 권고
- 단, **catch 52 본 미션 PASS 판정은 ratio 결과와 독립** (정량 증거 4개 충족이 본 미션 PASS 조건)
