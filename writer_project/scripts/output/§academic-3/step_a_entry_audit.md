# §academic-3 Step A entry audit

> **박제 chain reference**
> - 직전 cycle: §academic-2 close (commit `92d43cd` · branch `main`)
> - 본 audit 대상 catch: catch 52 (ACADEMIC_DOMAINS_29 set 글로벌 학술 플랫폼 누락)
> - root cause 근거 doc: `scripts/output/§academic-2/step_c_impl_measurement.md` 섹션 4 (academic-en 잔존 분석 + 시사점 2)
> - audit 범위: A1 (current set 구성) + A2 (academic-en 잔존 도메인 분류) + A3 (보강 후보 list) — **read-only**
> - audit driver: 미사용 (`c_verification.json` 재사용 + grep/view 만으로 충분 — 신규 driver 작성 생략)
> - 환경: PowerShell · BOOK-DPUCVR08TC · HEAD = `92d43cd`

---

## Cycle decisions (사용자 컨펌 박제)

| # | 영역 | 결정 |
|---|---|---|
| Q1 | 학술 정의 | **엄격 안** — peer-review journal publisher 만 인정. HBR (hbr.org) / statista / forbes / medium / 일반 매거진 모두 제외 |
| Q2 | 보강 범위 | **보수적 안** — 10개 이내. 실측 hit 도메인 + 광고/마케팅 분야 핵심 publisher 우선. 추가 round 는 Step C 측정 후 결정 |
| Q3 | catch 53 (subdomain 분기) | **분리** — 본 cycle 은 catch 52 만 처리. `semanticscholar.org` 는 root domain 만 등재, subdomain 이슈 (`pdfs.semanticscholar.org`) 는 별도 cycle |

---

## A1 — current ACADEMIC_DOMAINS_29 set 구성

### 정의 위치

- **측정 기준 set (driver-side)**: `writer_project/scripts/§academic-1/measure_ab.py:138-146` — `ACADEMIC_DOMAINS_29` 상수 (frozenset literal, 29 entries)
- **운영 환경 inject (config-side)**: 토픽 .env 파일의 `ALLOWED_DOMAINS_EXTRA=...` 라인 (29 entries, 측정 set 과 1:1 동일)
  - `writer_project/topics/academic-_template.env:22`
  - `writer_project/topics/academic-influencer-marketing-consumer-behavior.env:16`
  - `writer_project/topics/academic-genz-mobile-ad-acceptance.env:16`
- **gatekeep merge 경로**: `writer_project/settings_gatekeep.py:168` — `out |= _as_set(os.getenv("ALLOWED_DOMAINS_EXTRA", ""))` (base 78 + EXTRA 29 + normalization 1 = `[GATEKEEP] n=108` 정합)

### 29 도메인 전수 + 카테고리 분류

| # | 도메인 | 카테고리 | 분야 적합도 |
|---:|---|---|---|
| 1 | `academic.oup.com` | 글로벌 publisher (Oxford UP) | peer-review · 광고/마케팅 인접 |
| 2 | `ama.org` | 글로벌 학회 (American Marketing Association) | ★광고·마케팅 특화 |
| 3 | `arxiv.org` | 글로벌 preprint repository | peer-review 아님 (preprint) |
| 4 | `dbpia.co.kr` | 한국 학술 aggregator (DBpia) | 한국 광고/마케팅 정합 |
| 5 | `doaj.org` | 글로벌 학술 검색 (Directory of OA Journals) | peer-review only directory |
| 6 | `emerald.com` | 글로벌 publisher (Emerald) | peer-review · 광고/마케팅 인접 |
| 7 | `journals.sagepub.com` | 글로벌 publisher (Sage subdomain) | peer-review |
| 8 | `jstor.org` | 글로벌 학술 archive | peer-review only archive |
| 9 | `kadpr.or.kr` | 한국 학회 (한국광고홍보학회) | ★광고·마케팅 특화 |
| 10 | `kci.go.kr` | 한국 학술 검색 (KCI) | peer-review 등재지 only |
| 11 | `kiss.kstudy.com` | 한국 학술 aggregator (KISS) | 한국 광고/마케팅 정합 |
| 12 | `link.springer.com` | 글로벌 publisher (Springer subdomain) | peer-review |
| 13 | `mmaglobal.com` | 글로벌 학회 (Mobile Marketing Assoc.) | ★광고·마케팅 특화 |
| 14 | `msi.org` | 글로벌 학회 (Marketing Science Institute) | ★광고·마케팅 특화 |
| 15 | `onlinelibrary.wiley.com` | 글로벌 publisher (Wiley subdomain) | peer-review |
| 16 | `openalex.org` | 글로벌 학술 검색 (OpenAlex) | scholarly metadata |
| 17 | `papers.ssrn.com` | 글로벌 preprint repository (SSRN subdomain) | preprint (working paper) |
| 18 | `plos.org` | 글로벌 publisher (PLOS OA) | peer-review |
| 19 | `pmc.ncbi.nlm.nih.gov` | 글로벌 학술 archive (PubMed Central) | peer-review only |
| 20 | `pubsonline.informs.org` | 글로벌 publisher (INFORMS) | ★광고·마케팅 인접 (marketing science) |
| 21 | `riss.kr` | 한국 학술 검색 (RISS) | 한국 광고/마케팅 정합 |
| 22 | `sagepub.com` | 글로벌 publisher (Sage root) | peer-review |
| 23 | `science.org` | 글로벌 publisher (Science) | peer-review |
| 24 | `semanticscholar.org` | 글로벌 학술 검색 (Semantic Scholar root) | scholarly metadata (★ subdomain 매칭 이슈 — catch 53 영역) |
| 25 | `springer.com` | 글로벌 publisher (Springer root) | peer-review |
| 26 | `ssrn.com` | 글로벌 preprint repository (SSRN root) | preprint |
| 27 | `tandfonline.com` | 글로벌 publisher (Taylor & Francis) | peer-review |
| 28 | `warc.com` | 글로벌 산업 research repository | ★광고·마케팅 특화 (peer-review 아님, industry research — §academic-1 Step B 박제 인정 도메인) |
| 29 | `wiley.com` | 글로벌 publisher (Wiley root) | peer-review |

### 카테고리별 분포 (29 합산)

| 카테고리 | n | 도메인 |
|---|---:|---|
| 한국 학회 | 1 | kadpr.or.kr |
| 한국 학술 aggregator/publisher | 2 | dbpia.co.kr, kiss.kstudy.com |
| 한국 학술 검색 엔진 | 2 | kci.go.kr, riss.kr |
| 글로벌 학회 | 4 | ama.org, mmaglobal.com, msi.org, pubsonline.informs.org |
| 글로벌 publisher (peer-review) | 11 | academic.oup.com, emerald.com, journals.sagepub.com, link.springer.com, onlinelibrary.wiley.com, plos.org, sagepub.com, science.org, springer.com, tandfonline.com, wiley.com |
| 글로벌 preprint repository | 3 | arxiv.org, papers.ssrn.com, ssrn.com |
| 글로벌 학술 archive | 2 | jstor.org, pmc.ncbi.nlm.nih.gov |
| 글로벌 학술 검색 엔진 | 3 | doaj.org, openalex.org, semanticscholar.org |
| 글로벌 산업 research repository | 1 | warc.com |
| **합** | **29** | |

### 누락 카테고리 (catch 52 root cause 정합)

- **글로벌 학술 SNS / preprint platform (peer-review 인접)**: `mdpi.com`, `researchgate.net` 부재 — academic-en 실측 hit 다수
- **한국 학술 SNS / 검색 (네이버 학술)**: `academic.naver.com` 부재 — academic-en legacy naver_direct backend hit (5/5 runs)
- **광고·마케팅 분야 특화 학술 (Q1 정합)**: `acr-journal.com` (Association for Consumer Research) 부재 — academic-en vertex hit 3/5 runs
- **Elsevier 산하 publisher**: `sciencedirect.com` 부재 — 광고/마케팅 핵심 journal 다수 (Journal of Business Research 등) Elsevier routing

---

## A2 — academic-en 잔존 도메인 분석

### Data source

- `writer_project/scripts/output/§academic-2/c_verification.json` (`.gitignored` raw 자산, §academic-2 Step C 측정 박제)
- academic-en `topic_results.academic-en.runs[]` 5 runs (warmup 2 + measure 3) 의 `all_domains_unique` + `legacy.domains_unique` 통합 합집합

### 5 runs all_uniq 합집합 (49 entries)

| # | 도메인 | 분류 (Q1 엄격 반영) | catch 52 후보 | catch 53 영역 |
|---:|---|---|---|---|
| 1 | `academic.naver.com` | 한국 학술 검색 (학술) | ★HIGH | – |
| 2 | `acr-journal.com` | Assoc. for Consumer Research (★광고·마케팅 학술) | ★HIGH | – |
| 3 | `mdpi.com` | OA publisher (peer-review claim, 회색 우려 — 그러나 marketing journals 다수) | ★HIGH | – |
| 4 | `researchgate.net` | 학술 SNS (peer-review 아님, 학술 paper 호스팅) | ★HIGH | – |
| 5 | `pdfs.semanticscholar.org` | Semantic Scholar PDF subdomain | – | ★YES (root 는 set 내 등재됨) |
| 6 | `councils.forbes.com` | Forbes Councils (industry 매거진 subdomain) | 제외 (Q1) | – |
| 7 | `forbes.com` | Forbes (industry 매거진) | 제외 (Q1) | – |
| 8 | `medium.com` | Medium (일반 publishing platform) | 제외 (Q1) | – |
| 9 | `mintel.com` | Mintel (시장조사 paywall) | 제외 (Q1, 회색) | – |
| 10 | `ideas.repec.org` | RePEc (Economics paper archive) | LOW (광고/마케팅 비중 낮음) | – |
| 11 | `diva-portal.org` | DiVA (북유럽 thesis repository) | LOW (광고/마케팅 비중 낮음) | – |
| 12 | `growingscience.com` | OA publisher (predatory 우려) | 제외 (Q1 회색) | – |
| 13 | `ijarsct.co.in` | IJARSCT (OA, predatory 우려) | 제외 (Q1 회색) | – |
| 14 | `ijnrd.org` | IJNRD (OA, predatory 우려) | 제외 (Q1 회색) | – |
| 15 | `irejournals.com` | IRE Journals (OA, predatory 우려) | 제외 (Q1 회색) | – |
| 16 | `jisem-journal.com` | JISEM (OA, 영향 낮음) | 제외 (Q1 회색) | – |
| 17 | `jmsr-online.com` | JMSR (OA, 영향 낮음) | 제외 (Q1 회색) | – |
| 18 | `migrationletters.com` | Migration Letters (광고/마케팅 분야 아님) | 제외 | – |
| 19 | `psychosocial.com` | Psychosocial journal (광고/마케팅 인접 가능) | LOW | – |
| 20 | `scilit.com` | Scilit (학술 metadata 검색, MDPI 산하) | LOW | – |
| 21 | `business.cornell.edu` | Cornell Business edu portal | 제외 (학술 paper 호스팅 아님) | – |
| 22 | `business.rice.edu` | Rice Business edu portal | 제외 | – |
| 23 | `researcher.manipal.edu` | Manipal researcher portal | 제외 | – |
| 24 | `sj.westsciences.com` | West Sciences (OA, 영향 낮음) | 제외 (Q1 회색) | – |
| 25 | `jcc-indonesia.id` | JCC Indonesia (광고/마케팅 비중 낮음) | 제외 | – |
| 26 | `eelet.org.uk` | EELET (광고/마케팅 비중 낮음) | 제외 | – |
| 27 | `vertexaisearch.cloud.google.com` | vertex redirect unresolved (catch 42 영역) | 제외 (FILTER_BAD_DOMAINS 후보) | – |
| 28-49 | `allindiamediasolutions.com`, `barksocial.digital`, `bbbprograms.org`, `blackmorepartnersinc.com`, `cademix.org`, `cannacompanionusa.com`, `elementhuman.com`, `eyes4research.com`, `fastercapital.com`, `flinque.com`, `forthworthjournals.org`, `gameinfluencer.com`, `gracker.ai`, `hypefy.ai`, `influenceinguides.com`, `influencity.com`, `insomemarketing.com`, `intelliplans.com`, `socialpubli.com`, `sosquared.com`, `yoloco.io`, `zigpoll.com` | ad-tech / industry blog / aggregator (학술 아님) | 제외 (Q1) | – |

### academic-en 도메인 분포 요약

| 분류 | n | 비고 |
|---|---:|---|
| **catch 52 후보 (★HIGH, Q1 정합)** | **4** | `academic.naver.com` · `acr-journal.com` · `mdpi.com` · `researchgate.net` |
| catch 53 영역 (subdomain) | 1 | `pdfs.semanticscholar.org` (root `semanticscholar.org` 는 set 내 등재) |
| LOW priority (광고/마케팅 비중 낮음) | 4 | `ideas.repec.org` · `diva-portal.org` · `psychosocial.com` · `scilit.com` |
| 제외 (Q1 엄격 — 매거진/predatory/edu portal) | 18 | forbes / medium / mintel / IJARSCT 등 18개 |
| 제외 (ad-tech / industry blog) | 22 | 학술 정의 외 |
| **합** | **49** | |

→ Q1 엄격 정책 반영 시 catch 52 후보는 **최대 4개 (HIGH) + 회색 4개 (LOW)**. 정합 hit 도메인이 set 미등재로 인해 academic-en `academic_source_ratio = 0.0` 잔존 — **catch 52 root cause 가설 정합**.

---

## A3 — expansion candidate list + 선정 기준

### 선정 기준

| # | 기준 | 가중 |
|---|---|---|
| 1 | peer-review journal publisher / 학술 검색 / 학술 SNS 여부 (Q1) | **필수** |
| 2 | 광고·마케팅 분야 적합도 (Sungsu 임용 분야 정합) | HIGH |
| 3 | 한국 임용 심사 관행 정합 (한국 KCI / 학회 도메인 가중) | MID |
| 4 | §academic-2 academic-en 실측 hit 유무 | HIGH |
| 5 | catch 53 (subdomain) 영역 분리 (Q3) | **필수 분리** |

### 후보 list (Q1 엄격 + Q2 보수적 10개 이내)

| # | 후보 | 카테고리 | 실측 hit | priority | catch 53 영역 | 비고 |
|---:|---|---|---|---|---|---|
| 1 | `mdpi.com` | OA publisher (peer-review) | ★5/5 runs | **HIGH** | – | marketing journals 다수 (Behavioral Sciences, Journal of Theoretical & Applied Electronic Commerce Research 등). Q1 회색 우려는 있으나 peer-review claim + 광고/마케팅 정합 강함 |
| 2 | `researchgate.net` | 학술 SNS | ★4/5 runs | **HIGH** | – | peer-review 아니나 학술 paper 호스팅. Q1 엄격 정책 경계선 — 학술 검색 SNS 로 인정 여부 사용자 컨펌 영역 |
| 3 | `academic.naver.com` | 한국 학술 검색 | ★5/5 runs (legacy naver_direct) | **HIGH** | – | 한국 임용 정합 + naver backend 안정 회수. Q1 한국 학술 검색 엔진 카테고리 |
| 4 | `acr-journal.com` | ★광고·마케팅 학술 (Association for Consumer Research) | ★3/5 runs | **HIGH** | – | Sungsu 광고/마케팅 임용 분야 직접 정합 + peer-review |
| 5 | `sciencedirect.com` | Elsevier publisher root | 0/5 runs | **MID** | – | Journal of Business Research / Journal of Retailing 등 광고/마케팅 핵심 publisher Elsevier 산하. 실측 hit 없으나 누락 시 향후 academic-en query 분포 변화 시 추가 손실 가능 |
| 6 | `journalofadvertising.org` | ★광고·마케팅 학술 (Journal of Advertising) | 0/5 runs | **MID** | – | catch 45 (A1 fail) 재검 영역 — §academic-1 Step A 에서 SSL/접속 이슈 박제. peer-review + Sungsu 분야 직접 정합. catch 45 status 함께 재평가 권장 |
| 7 | `aom.org` | 글로벌 학회 (Academy of Management) root | 0/5 runs | **MID** | – | marketing/management 학술 학회. journal.aom.org subdomain 매칭은 catch 53 영역 (별 cycle) — root only 등재 권장 |
| 8 | `apa.org` | 글로벌 학회 (American Psychological Assoc.) | 0/5 runs | LOW | – | 광고/마케팅 인접 (소비자 심리). 보수적 안 (Q2) 정합 시 omit, 적극적 안 일 때 포함 |
| 9 | `journals.aom.org` | AOM journal subdomain | 0/5 runs | (★catch 53 영역) | **★YES** | aom.org root 등재 + subdomain 매칭 활성화 시 자동 cover — 본 cycle 등재 보류 권장 (Q3 catch 53 분리) |
| 10 | `pdfs.semanticscholar.org` | Semantic Scholar subdomain | ★1/5 runs | (★catch 53 영역) | **★YES** | root `semanticscholar.org` 이미 set 내 등재. subdomain 매칭 OFF 가 본질적 root cause → catch 53 cycle 분리 |

### 권장 안 — 보수적 (Q2 정합, 10개 이내)

| 순위 | 도메인 | 사유 |
|---:|---|---|
| 1 | `mdpi.com` | 실측 hit 5/5 + peer-review |
| 2 | `researchgate.net` | 실측 hit 4/5 + 학술 SNS |
| 3 | `academic.naver.com` | 실측 hit 5/5 + 한국 임용 정합 |
| 4 | `acr-journal.com` | 실측 hit 3/5 + 광고/마케팅 학술 직접 정합 |
| 5 | `sciencedirect.com` | Elsevier root + 광고/마케팅 핵심 publisher cover |
| 6 | `journalofadvertising.org` | catch 45 재검 + Sungsu 분야 직접 정합 |
| 7 | `aom.org` | Academy of Management root |

→ **권장 보수적 안 = 7 entries (Q2 10개 이내 정합)**. 보강 후 ACADEMIC_DOMAINS_29 → **ACADEMIC_DOMAINS_36** (재명명 권장 — Step B design 영역).

### 보수적 안 (7) vs 적극적 안 (15+) 비교

| 항목 | 보수적 안 (7) | 적극적 안 (15+) |
|---|---|---|
| 즉시 hit 회복 | mdpi/researchgate/academic.naver/acr-journal 4개 (HIGH) | 동일 4개 + 회색 (psychosocial, scilit, ideas.repec) 포함 시 5~7개 |
| 측정 cycle 비용 | 1회 cycle 충분 (Step B 박제 size 작음) | 추가 round 필요 + Q1 정합 검토 부담 |
| Q1 엄격 정책 적합도 | 7/7 직접 정합 | LOW priority 4개 정합 회색 |
| 한국 임용 정합 | academic.naver 1개 (★) | 동일 |
| catch 53 분리 정합 | journals.aom.org / pdfs.semanticscholar 모두 보류 | 동일 (catch 53 결정 영역) |
| **추천** | ★ Q2 정합 + Step C 측정 후 추가 round 결정 | × Q2 정합 위반 |

→ **권장 안 = 보수적 (7 entries, Q2 정합)**.

### Q1 정합 STOP-4 self-check

- [x] HBR (hbr.org): 후보 list 포함 없음 ✓
- [x] statista.com: 후보 list 포함 없음 ✓
- [x] forbes.com / councils.forbes.com: A2 분류 "제외 (Q1)" + 후보 list 포함 없음 ✓
- [x] medium.com: A2 분류 "제외 (Q1)" + 후보 list 포함 없음 ✓
- [x] mintel.com / fastercapital.com / hypefy.ai 등 industry 매거진: A2 분류 "제외 (Q1)" + 후보 list 포함 없음 ✓

---

## Audit summary

### catch 52 root cause 정합 여부

- **정합 ✓** — §academic-2 Step C 박제 (섹션 4 root cause 분리) 의 "ACADEMIC_DOMAINS_29 set vs vertex 결과 set 의 미스매치" 가설이 A2 실측 분포 분석으로 재확인됨.
- 실측 hit 4개 (mdpi / researchgate / academic.naver / acr-journal) 가 set 미등재로 인해 `academic_domains_hit = []` 잔존 → `academic_source_ratio = 0.0` 정합.

### Step B 진입 조건 충족 여부

- **충족 ✓** — A1 (현재 set 구성 + 누락 카테고리) + A2 (실측 분포 + Q1 분류) + A3 (보강 후보 7 entries + 권장 안) 모두 read-only 박제 완료.
- Step B 영역 (사용자 컨펌 후): set 재명명 (29 → 36) · 측정 driver vs config-side inject 동기화 정책 (3개 .env 파일 + measure_ab.py:138 일관 update) · budget 산정 (catch 48 컨벤션).

### 추정 fix 면적 (catch 48 컨벤션, 영역별 분리)

| 영역 | 추정 변경 | 비고 |
|---|---|---|
| set 상수 보강 (config / driver 영역) | +7 entries × 3 토픽 env (academic-_template / academic-influencer-marketing-consumer-behavior / academic-genz-mobile-ad-acceptance) + 1 driver set (measure_ab.py:138-146) | 4 file × 7 entries = 28 substitution. 각 file 의 EXTRA 라인은 단일 line (comma-separated) → diff hunk 4개 |
| 함수 본체 영향 | **없음** (set 사용처 `out |= _as_set(...)` 의 합집합 연산만 영향) | settings_gatekeep.py `get_allowed_domains()` 본문 변경 0 |
| hook 변경 | **없음** | `clear_runtime_allowed_domains` / `reload_config_inplace` 등 §academic-2 fix hook 그대로 |
| 신규 함수 정의 본체 | **없음** | catch 48 lesson: 신규 함수 없음 → budget 산식에서 "신규 def" 항목 0 |
| test fixture / 측정 driver | **없음** (measure_ab.py 의 set literal update 만으로 driver 측정 자동 갱신) | driver 의 `ACADEMIC_DOMAINS_29` → `ACADEMIC_DOMAINS_36` 재명명 시 driver 본문 참조 site (measure_ab.py:397) 도 함께 update — driver hunk 2개 |
| README-dev catch index | catch 52 entry + (catch 45 재검 결과 박제) | README-dev-§14.md catch index 영역 update 별 commit |

**예상 net diff**: +7 entries × 3 env file (substitution) + 1 driver set literal substitution + 1 driver 참조 site rename = **~5 hunks, 단순 substitution 위주, +0 logical line (substitution net)**.

### STOP gate self-check

- [x] **STOP-1** — audit .md draft 작성, commit 미진행 ✓
- [x] **STOP-2** — audit 결과가 catch 52 root cause 가설 (§academic-2 섹션 4) 과 정합 ✓
- [x] **STOP-3** — agent/, core/, settings_gatekeep.py 코드 미수정 ✓ (read-only audit 완료)
- [x] **STOP-4** — A3 후보 list 에 HBR/statista/forbes/medium 등 Q1 제외 도메인 0건 ✓
- [x] **STOP-5** — 권장 보수적 안 = 7 entries ≤ 10 (Q2 정합) ✓

### Self-check (사용자 hand-off 명시 check-list)

- [x] 모든 위치 표기 `file:line` 실제 형식 — `settings_gatekeep.py:45/168` · `measure_ab.py:138-146/397` · `topics/*.env:16,22` 등
- [x] A1 의 29개 도메인 list 실제 코드 추출 (measure_ab.py:138-146 직접 read, 추정 없음)
- [x] A2 분포가 `c_verification.json` 실측 기반 (5 runs × academic-en, 가설 없음)
- [x] A2 회색 분류가 Q1 엄격 정책 반영 (forbes/medium/mintel/predatory journal 등 제외)
- [x] A3 후보 list 에 catch 53 (subdomain) 영역 분리 명시 (#9, #10 + 권장 안 보류 처리)
- [x] A3 보수적 안 7 entries ≤ 10 (Q2 정합)
- [x] A3 후보가 peer-review publisher 기준 충족 (Q1 정합) — researchgate.net 만 학술 SNS 경계선, 사용자 컨펌 영역으로 명시
- [x] catch 표기 시 1줄 description 병기 — catch 52 / catch 53 / catch 45 / catch 48 / catch 42 모두 description 동반
- [x] catch 48 컨벤션 — fix 면적 영역별 분리 추정 (set/함수 본체/hook/신규 def/test/README 6 영역 분리)

---

## 박제 chain

- 직전 cycle close: §academic-2 commit `92d43cd`
- 본 audit 자산: `writer_project/scripts/output/§academic-3/step_a_entry_audit.md` (본 file, draft 단계)
- raw 자산 재사용: `writer_project/scripts/output/§academic-2/c_verification.json` (.gitignored)
- 신규 driver 작성: **없음** (audit driver 미사용)

### STOP-1 (resolved 2026-05-20) — Step A audit 결과 컨펌 대기 (이력 보존)

본 draft commit 전 사용자 결정 영역 (resolved, 아래 "사용자 결정 박제 (확정)" 섹션 참조):

1. **권장 보수적 안 (7 entries) 수용 여부**: mdpi / researchgate / academic.naver / acr-journal / sciencedirect / journalofadvertising / aom.org — 전수 수용 vs 일부 제외
2. **researchgate.net 학술 SNS 인정 여부**: Q1 엄격 정책 (peer-review only) 경계선 — 인정 시 학술 SNS 카테고리 신설, 제외 시 보수적 안 6 entries 로 축소
3. **catch 45 (`journalofadvertising.org`) 재검 진입 여부**: 본 cycle 안 동시 처리 vs 별 cycle 분리. SSL/접속 이슈 (§academic-1 Step A 박제) 가 ALLOWED_DOMAINS_EXTRA 등재 후에도 retrievable 여부 측정 필요
4. **set 재명명 (29 → 36) 정합 여부**: Step B design 영역 — 측정 driver `ACADEMIC_DOMAINS_29` literal + README-dev 박제 + 토픽 env comment 모두 일관 update 정책

자율 Step B 진입 금지 (STOP-1). 본 draft commit 후 사용자 컨펌 대기 → **resolved 2026-05-20**.

---

### 사용자 결정 박제 (확정, 2026-05-20)

> Step A audit draft commit `10541d2` 직후 사용자 컨펌 영역 4개 모두 결정. Step B 진입 자격 충족.

| # | 결정 영역 | 확정 | 사유·정합 근거 |
|---:|---|---|---|
| ① | 보수적 안 7 entries 수용 범위 | **전수 수용** (HIGH 4 + MID 3) | HIGH: `mdpi.com` · `researchgate.net` · `academic.naver.com` · `acr-journal.com` (실측 hit + Q1 정합). MID: `sciencedirect.com` · `journalofadvertising.org` · `aom.org` (광고/마케팅 핵심 publisher cover) — Q2 보수적 (10개 이내) 정합 |
| ② | `researchgate.net` 학술 SNS 인정 | **인정** | Q1 엄격 정책 (peer-review only) 정합 — peer-review 논문 공유 플랫폼으로 분류. 광고/마케팅 분야 working paper 관행 정합 (학자 self-archive 관행 보편). 학술 SNS 카테고리 신설 (catch 52 fix scope 안) |
| ③ | catch 45 (`journalofadvertising.org`) 재검 진입 | **분리** (본 cycle 은 catch 52 만) | scope creep 방지 (catch 45 = SSL/접속 이슈 별 root cause, ALLOWED_DOMAINS_EXTRA 등재로 자동 해소 안 됨). catch 45 별 cycle 후보로 보존, 본 cycle 의 `journalofadvertising.org` 추가는 set 등재만 수행 (retrievable 검증은 catch 45 cycle scope) |
| ④ | set 재명명 (`ACADEMIC_DOMAINS_29` → `_36` 또는 숫자 제거) | **Step B design 영역 이월** | Step B 의 substitution net 산정 + driver `measure_ab.py:138-146` literal + 참조 site (`measure_ab.py:397`) + README-dev 박제 + 토픽 env comment 일관 update 정책 결정 영역. catch 48 컨벤션 (budget 산식 신규 def 항목) 정합 |

### Step B 진입 자격

- catch 52 root cause + 보강 후보 7 entries 확정 → Step B (design) 진입 자격 충족
- Step B design 박제 영역:
  - set 재명명 정책 (결정 ④ 영역)
  - substitution 면적 정밀 산정 (catch 48 budget 컨벤션)
  - 측정 driver vs config-side inject 동기화 정책 (4 file 일관 update)
  - business invariant + academic-ko 회귀 0 검증 strategy (catch 52 fix 후 §academic-2 PASS 정합 유지)
