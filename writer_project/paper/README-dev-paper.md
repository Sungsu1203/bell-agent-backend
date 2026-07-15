# 논문 트랙 아카이브 — §academic + §paper-writer

## §academic-1 close (2026-05-19) — 학술 모드 통합 옵션 B (catch 43 + MODE infra)

`81894f3` C-1 (catch 43 hook + MODE/EXPECTED_LANG config + academic env templates) + `c927a70`/`b2c7c86` C-2 measurement driver (+ hotfix) + `853ed11` C-3 측정 (3 topics × 5 runs · vertex) + `2ac1689`/`79f6ba0` catch 49/50 follow-up + `d4d6431` driver default 변경 (timeout 240→90s + redirect monkey-patch opt-in).

본 미션 (catch 43 routing 메커니즘 + business invariant) 5 metric 중 4 PASS, metric 2 REVIEW (root cause A/B 박제: driver redirect monkey-patch 부작용 + gatekeep cache stale → catch 50 sub-cycle 후보). 박제: `scripts/output/§academic-1/step_{a,b}_*.md` + `step_c_impl_measurement.md`.

close commit chain (참조):
```
d4d6431 §academic-1 follow-up — measure_ab.py driver default 변경 (C-3 lesson 적용)
79f6ba0 §academic-1 follow-up — README-dev catch 50 등록 (gatekeep cache invalidation 결함)
2ac1689 §academic-1 follow-up — README-dev catch 49 등록 (driver SDK-level timeout + probe lesson)
853ed11 §academic-1 Step C-3 — measurement + 결과 박제
b2c7c86 §academic-1 Step C-2 hotfix — driver SDK-level timeout + provider lock + flush stage + probe 강화
c927a70 §academic-1 Step C-2 — measurement driver
d2e9db0 §academic-1 follow-up — README-dev catch 48 등록 (Step B budget 산정 미스 lesson)
81894f3 §academic-1 Step C-1 — implementation (catch 43 + MODE infra + academic env templates)
7dfc8c6 §academic-1 follow-up — README-dev catch index 44/45/46/47 등록
989b0ef §academic-1 Step B — design (read-only)
5349a9c §academic-1 Step A — entry audit (read-only)
```

**status: closed (2026-05-19)** — §academic-1 본 미션 (catch 43 + MODE infra + business invariant) 정식 종결. 부수 미션 (academic source ratio 정량) 미달성 → catch 50 sub-cycle 후보 보존. catch 44/45/46/47 별 cycle 후보 보존, lesson catch 48/49 정착.

---

## §academic-2 close (2026-05-19) — catch 50 fix (gatekeep `_RUNTIME_ALLOWED` upstream 무효화 해소)

`85579d2` Step A follow-up (catch 50 가설 재작성: lru_cache 협의 → `_RUNTIME_ALLOWED` upstream 광의) + `a62c6d6` Step A entry audit (A1·A2·A3 read-only) + `33f0cf0` Step B design (read-only, 후보 2 채택: `clear_runtime_allowed_domains` 신규 + `reload_config_inplace` hook) + `4b75bc5` Step B follow-up (B8 4개 사용자 결정 박제 + STOP-3/STOP-4 추가) + `3598568` Step C-1 fix 본체 (settings_gatekeep.py + core/config.py, +16 line) + `90acb87` Step C-2 측정 결과 박제 (catch 50 fix 정량 증거).

본 미션 (catch 50 — gatekeep `_RUNTIME_ALLOWED` upstream 무효화 해소) **PASS**. 정량 증거: academic-ko `[GATEKEEP] n` 79 → 108 (+29 EXTRA 회복, 5/5 runs 일관) + `academic_source_ratio` 0.0 → 0.6667 (dbpia + kiss.kstudy hit). 회귀 0 — business invariant Jaccard 1.0 strict (B8 #3 정합) + 4 metric PASS 회귀 0. 부수 미션 (academic source ratio mean ≥ 0.6) **PARTIAL** — mean 0.3333 (academic-ko 0.6667 PASS + academic-en 0.0 잔존, catch 50 외부 root cause). 박제: `scripts/output/§academic-2/step_{a_entry_audit,b_design,c_impl_measurement}.md`.

close commit chain (참조):
```
(이 commit) §academic-2 close — README §academic-2 close section + catch 50 close 표기 + catch 51/52/53 등록
90acb87 §academic-2 Step C-2 — 측정 결과 박제 (catch 50 fix 정량 증거)
3598568 §academic-2 Step C-1 — catch 50 fix 본체 (clear_runtime_allowed_domains 신설 + reload hook + __all__)
4b75bc5 §academic-2 Step B follow-up — design doc 사용자 결정 박제 (B8 4개 결정 + STOP-3/STOP-4 추가)
33f0cf0 §academic-2 Step B — design (read-only)
a62c6d6 §academic-2 Step A — entry audit (read-only)
85579d2 §academic-2 Step A follow-up — README-dev catch 50 가설 재작성 (_RUNTIME_ALLOWED upstream 무효화 누락)
```

**status: closed (2026-05-19)** — §academic-2 본 미션 (catch 50 fix: `_RUNTIME_ALLOWED` upstream 무효화 해소) 정식 종결. 부수 미션 (academic source ratio mean ≥ 0.6) PARTIAL — academic-ko 단독 PASS / academic-en 잔존 (catch 50 외부, scope creep 경고 박제 정합으로 본 cycle 안 시도 금지). sub-cycle 후보 등록: catch 52 (MID 최우선 — `ACADEMIC_DOMAINS_29` set 보강) · catch 53 (LOW-MID — `ALLOW_SUBDOMAINS` academic 분기) · catch 51 (LOW — vertex grounding bias 정량). lesson: design B5 budget 산식에 PEP 8 separator blank line 항목 포함 권장 (catch 48 lesson 미세 재현 107%, 별 sub-catch 박제 불필요).

---

## §academic-3 close (2026-05-20) — catch 52 fix (`ACADEMIC_DOMAINS` set 글로벌 학술 플랫폼 보강 7 entries)

`10541d2` Step A entry audit (A1·A2·A3 read-only — set 정의 위치 + academic-en 49 도메인 분포 분석 + 보강 후보 7 entries 박제) + `28fe7f9` Step A follow-up (사용자 결정 ①~④ 박제: 보수적 7 entries 수용 + researchgate 학술 SNS 인정 + catch 45 분리 + set 재명명 Step B 이월) + `8d6d2e4` Step B design (read-only — D1 카테고리 주석 + D2 변수 재명명 grep + D3 측정 계획 + D4 STOP/Self-check + D5 commit 정책) + `ddc59a4` Step B follow-up (사용자 결정 ①~④ + Risk 박제: academic-en ratio 예상 ≈0.31, PARTIAL 가능 박제) + `296d09d` Step C-1 fix 본체 (measure_ab.py:137-170 set literal 재구성 + line 423 참조 site + 3 토픽 .env EXTRA 36 entries + 9 카테고리 헤더, 5 file +41/-15) + `743b5b4` Step C-2 측정 결과 박제.

본 미션 (catch 52 — `ACADEMIC_DOMAINS` set 글로벌 학술 플랫폼 누락 해소) **PASS**. 정량 증거: academic-en/ko `[GATEKEEP] n` 108 → 114 (+6 net = +7 entries - 1 base 중복 `sciencedirect.com`, **catch 52 fix 결정적 증거**) + academic-en `academic_source_ratio` 0.0 → 0.3165 (HIGH 3 회수: mdpi/researchgate/academic.naver). 회귀 0 — business invariant Jaccard 1.0 strict + academic-ko ratio 0.6667 회귀 0 + 다른 4 metric PASS. 부수 미션 (academic source ratio mean ≥ 0.6) **PARTIAL** — mean 0.4916 (academic-ko 0.6667 PASS + academic-en 0.3165 잔존, 임계 0.6 미달, Step B Risk 박제 예상 0.31 정합 ✓). 박제: `scripts/output/§academic-3/step_{a_entry_audit,b_design,c_impl_measurement}.md`.

### Cycle 회고

본 cycle 은 catch 52 fix 의 본 미션 PASS + 부수 미션 PARTIAL 의 이중 verdict 로 종료. Process lesson 3개 재현:

1. **catch 48 lesson 미세 재현 (148%, §academic-2 의 107% 차수 확대)** — design D5 추정 +21 line vs actual +31 line. 사유: 9 카테고리 헤더 PEP 8 separator 8 + inline `#` 주석 stand-alone 분리. 향후 design budget 산식에 "카테고리별 separator + inline 주석 stand-alone" 항목 명시 카운트 권장.
2. **Step B Risk 박제 정확성 검증** — Step B follow-up (commit `ddc59a4`) 의 academic-en ratio 예상 ≈0.31 (HIGH 4 hit / 평균 13 도메인 가정) 이 실측 0.3165 와 거의 완벽 일치. 박제 시스템의 사전 분석 정밀도 검증 — 향후 cycle 진입 시 Risk 박제를 "PARTIAL 가능성 사전 정량" 단계로 정착 권고.
3. **catch 56 후보 발견** — Step A audit 단계에서 추가 후보 7 entries 중 `sciencedirect.com` 이 기존 base 78 set 중복 발견 → net +6 신규. `[GATEKEEP] n` +6 정합 (예상 +7 - 1). 미래 audit 의 "추가 후보 도메인 grep 사전 검증" 단계 강화 lesson.

### 잔존 영역 + 신규 catch

- **HIGH 격상**: catch 51 (vertex grounding 영문 학술 reach 정량, §academic-4 본 미션 후보) — gap 0.3165 → 0.6 = 47% 영역
- **LOW 유지**: catch 45 (`journalofadvertising` 등 A1 fail, 본 측정 자연 진입 0 확인) · catch 53 (`ALLOW_SUBDOMAINS` academic 분기, 본 측정 영향 0)
- **신규 등록**: catch 54 (docstring stale, LOW) · catch 55 (Claude Code .env detection mismatch, LOW) · catch 56 (driver args output 경로 부재, LOW-MID)

close commit chain (참조):
```
(이 commit) §academic-3 close — catch 52 fix + PARTIAL ratio 박제
743b5b4 §academic-3 Step C-2 — 측정 결과 박제 (catch 52 fix 정량 증거)
296d09d §academic-3 Step C-1 — catch 52 fix 본체
ddc59a4 §academic-3 Step B follow-up — 사용자 결정 ①~④ + Risk + PARTIAL 박제
8d6d2e4 §academic-3 Step B — design (read-only)
28fe7f9 §academic-3 Step A follow-up — 사용자 결정 ①~④ 박제
10541d2 §academic-3 Step A — entry audit (read-only)
```

**status: closed (2026-05-20)** — §academic-3 본 미션 (catch 52 fix: `ACADEMIC_DOMAINS` set 글로벌 학술 플랫폼 7 entries 보강) 정식 종결. 부수 미션 (academic source ratio mean ≥ 0.6) PARTIAL — academic-ko 단독 PASS / academic-en 0.3165 잔존 (catch 52 외부, scope creep 경고 박제 정합으로 본 cycle 안 시도 금지). sub-cycle 후보: **catch 51 HIGH 격상** (§academic-4 본 미션 후보) · catch 45/53 LOW 유지 · catch 54/55/56 신규 등록 (LOW/LOW/LOW-MID). lesson: catch 48 lesson 재정착 (148% oversize, PEP 8 separator + inline 주석 stand-alone 산식 명시 권장) + Step B Risk 박제 정확성 검증 (예상 0.31 ↔ 실측 0.3165 정합) + sciencedirect base 중복 발견 (추가 후보 도메인 grep 사전 검증 lesson).

---

## §paper-writer-2 seed 주입 트랙 close (2026-06-28) — 외부 seed reference 강제 주입 + verify 3단 폴백

### 결론 (트랙 완료)

외부 seed reference (교수님 지정 핵심 인용 18편) 를 OA/SS fan-out **전에** paper mode 회수 파이프라인에 강제 주입하는 트랙 완료. paper 가 매번 누락하던 "반드시 인용해야 할" 선행연구를 결정론적으로 References 에 포함.

구현 (`agent/web_search.py`):
- **`_load_and_hydrate_seeds(section_type, existing_chunks=None)`** — seed JSON 로드 → section slug 매칭 core 항목 (`context` 는 `SEED_INCLUDE_CONTEXT=1` 시) → `fetch_key.title` 로 `openalex_search` hydrate → verify → 정규화 `{title,authors,year,venue,doi,abstract,_backend}` 반환. `SEED_DRY=1` 시 section 무시 + `automating-abercrombie-2024` 1건만 (단위 점검용).
- **`_clean_chunk_text(chunk)`** — title/abstract/venue **+ authors 리스트 각 원소** HTML 태그 strip + 유니코드 하이픈 (U+2010/2011/2013/2014) → ASCII `-` + 연속공백 정리. seed·일반 chunk 양쪽에 `paper_section_fetch` 회수 직후 **단일 지점** 적용.
- **`paper_section_fetch` 배선** — `all_chunks` 초기화 직후·fan-out 전 seed extend → fan-out → 단일 클린징 → **출구 doi-dedup** (keep-first, seed 먼저 들어가 보존, doi 없는 chunk 통과) → return.
- **seed 선별 필터** — `priority=='core'` 항상 / `'context'` 는 flag 시 / 그 외 (`hold`·`oa_unresolved`·`oa_unindexed`) 주입 제외 (데이터는 JSON 에 보존).

### verify 3단 폴백 (catch 76 해소)

1. **doi-match**: `seed.verify_labels.doi == 회수 doi` → 채택
2. **arxiv-match**: 회수 doi 의 `10.48550/arxiv.(\d+\.\d+)` 추출 id == `seed.verify_labels.arxiv` → 채택
3. **title-jaccard ≥ 0.8**: doi/arxiv 어긋나도 제목 토큰 자카드 일치 시 채택

3단 전부 실패 → 어느 단계서 떨어졌는지 WARNING 로그 후 skip (catch 70: 무흔적 폐기 금지).

### 태깅 — `_backend="openalex"`

seed chunk 는 `_backend="openalex"` 강제 태깅 → axis3 학술 분자 (oa) 에 합류. `"seed"` 신규 backend 값 금지 — 분모만 키우고 분자 0 기여하는 dilution 함정 (catch 66 계열) 회피.

### 최종 측정 (상표 토픽, `--measure 1`, 2026-06-28)

- **seed 채택: 13/13 injectable core** (core 15 중 2 = `automatic-tm-detection-2026`·`vanheuven-phonetic-tm` 를 OA 미색인으로 `hold` 강등 → injectable 13). 위양성 (false-negative) **0**.
  - SBERT (`sbert-2019`): seed doi=ACL `10.18653/v1/D19-1410`, OA=arXiv `10.48550/arxiv.1908.10084` → **arxiv-match 로 구제** (catch 76).
  - STS-benchmark: 원본 제목 'Crosslingual'(붙임) 0건 → OA 색인 정확표기 'Cross-lingual'(하이픈) 교체 후 arxiv-match 채택.
- **References 품질**: HTML 태그·유니코드 하이픈 잔존 **0** (title/venue/abstract + authors `Yu-Kun Lai` 정규화 확인). axis1 APA PASS (1.0, n=169).
- **출구 dedup**: seed↔일반 doi 충돌 시 1건 병합·seed 보존 (오프라인 검증). 실측에선 충돌 0건.

### 측정 주의 (catch 77)

seed 효과를 **oa_ratio 로 읽지 말 것**. oa_ratio 는 vertex 수율 변동 (run 별 총 chunks 137→169, vertex 0.62→0.686) 에 희석되어 seed 11→12 증가에도 0.38→0.314 로 **오히려 하락**처럼 보임. seed 절대 기여는 일정 (+0.05, oa 0.26→0.31). **결정 지표 = 절대 채택수 (13)**, 비율 아님.

### catch 박제

- **catch 76** (MID · methodology · 신규): OpenAlex 가 출판본 DOI 대신 arXiv preprint DOI (`10.48550/arxiv.*`) 를 색인하는 경우 → doi-only verify 가 정상 seed 를 위양성 탈락 (SBERT: seed=ACL DOI `10.18653/v1/D19-1410` vs OA=arXiv `10.48550/arxiv.1908.10084`). **해소**: verify 를 3단 폴백 (doi-match → arxiv-match → title-jaccard≥0.8) 으로 확장. arxiv-match 는 회수 doi 에서 `10.48550/arxiv.(\d+\.\d+)` 추출해 seed arxiv id 와 대조. **정량 검증**: 2026-06-28 실측에서 SBERT·LaBSE·multilingual-distillation 3편이 arxiv-match 로 채택 (직전 run doi-mismatch skip → 구제). prevention: seed JSON 에 doi 와 arxiv 라벨 병기 권장 (둘 중 하나로 hydrate 검증 가능).
- **catch 77** (MID · methodology · 신규): seed 주입 효과를 axis3 oa_ratio 로 평가하면 vertex 수율 변동에 가려짐 — seed 가 oa 분자·분모 동시 증가시키나 vertex chunk 수 변동폭이 더 커서 oa_ratio 가 오히려 하락 가능 (2026-06-28: seed 11→12 증가에도 oa 0.38→0.314). **해소**: seed 효과는 **절대 채택수** (deterministic, 13/13 injectable) 로 평가. oa_ratio 는 backend 수율 비율 지표로만 사용, seed 기여 측정에 부적합. catch 66 (ratio dilution) 의 seed-track 특수 사례 — 분자 절대 수 metric 우선 원칙 재확인. **갱신 (2026-07-04, axis3 재설계): 신 산식 `academic_ratio = (OA+SS+vertex_academic)/total` 에서 vertex_web(비학술)이 분모 페널티로 명시적 처리됨 → oa_ratio dilution 은 진단용 보조지표로 강등, 판정은 academic_ratio 단일. 아래 close 섹션 참조.**

### seed JSON fetch_key.title 보정 (skip 3건, `scripts/§paper-writer-1/seeds/seed_references_trademark-similarity.json`)

OA 실제 회수 결과로만 교체 (추측 제목 생성 금지 원칙 준수):
- **sts-benchmark-2017**: `"… Semantic Textual Similarity Multilingual and Crosslingual …"` → OA 색인 정확표기 `"… Semantic Textual Similarity - Multilingual and Cross-lingual …"` 교체. arxiv `1708.00055` 유지 → **재회수 arxiv-match 채택 확인**.
- **automatic-tm-detection-2026**: 제목 일반적이라 'Pascal VOC' 오회수 + pii/venue 결합 query 도 미회수 → 2026 신간 OA 미색인 추정. `priority: core→hold`, `status="oa_unresolved"`, `_priority_original` 보존. OA 색인 확인 시 fetch_key 교체 후 core 복귀 (re-entry).
- **vanheuven-phonetic-tm**: 제목/저자 결합 query 모두 무관 회수 → OA 미색인 확인. `priority: core→hold`, `status="oa_unindexed"`, 데이터 보존. 대체 색인처 확보 시 재평가 (re-entry).

### re-entry 조건

1. `automatic-tm-detection-2026` / `vanheuven-phonetic-tm` 의 OA 색인 확인 또는 대체 DB 확보 시 → `oa_recon_note` 갱신 + `priority` core 복귀 + 재측정.
2. SS 백엔드 무응답 (ss_ratio=0, catch 74/61 계열) 해소 시 axis3 재평가. **→ 해소 (2026-07-04): catch 74 로 SS 부활 + 아래 「axis3 재설계 close」 섹션에서 재평가 완료.**
3. axis3 `combined_ratio` 구조 quirk (세 비율 평균 ≤0.333 → `≥0.5` 영구 미달) 임계 재설계는 별 task. **→ 해소 (2026-07-04): 아래 「axis3 재설계 close」 — combined-mean 폐기 → academic_ratio 단일 판정 (임계 0.50).**

### commit chain (참조)

```
(이 commit) §paper-writer-2 seed 주입 트랙 close — 코드 + JSON 보정 3건 + dev 박제 (catch 76/77)
```

**status: closed (2026-06-28)** — §paper-writer-2 seed 주입 트랙 (코드) 정식 종결. 채택 13/13 injectable core (위양성 0) + References clean (HTML/하이픈 잔존 0) + verify 3단 폴백 (catch 76) + 절대수 평가 원칙 (catch 77) 박제. 잔존 별 task: OA 미색인 2건 (hold, re-entry 조건 ①) · SS 무응답 (catch 74) · combined 임계 재설계.

---

## §paper-writer-2 catch 72 쿼리 교정 트랙 close (2026-07-04) — section_to_query topic-scoped override (상표 도메인 앵커)

### 결론 (트랙 완료)

seed 주입 트랙의 자매 트랙 — "좋은 논문 주입"(seed) 의 나머지 반쪽 "나쁜 논문 차단"(쿼리 교정) 완료. section_to_query 범용 tail 이 topic 뒤 append 되어 도메인 무관 논문을 회수하던 문제 해소. 인용 정밀도 작업 완결.

구현 (`agent/web_search.py` section_to_query):
- **topic-scoped override** — topic 소문자에 `"trademark"` 포함 시에만 발동하는 override dict 를 기존 범용 mapping 조회 前에 가드 삽입. 미포함 topic·미등록 섹션은 범용 mapping 자연 폴백 (딴 주제 영향 0, 격리 검증 완료).
- **5섹션 tail = 상표 도메인어 3~4단어** — Introduction/Theoretical Background/Proposed Framework/Research Design/Expected Contributions 각 tail 에서 방법명·generic 배제, trademark/confusion/dilution/consumer 도메인어만. 범용 mapping dict 값은 한 글자도 미변경 (추가만).

### 진단 (핵심 — 두더지 잡기)

generic·방법명 토큰은 각자 "자기 분야" 논문을 끌어옴: `model/construct`→소프트웨어, `measurement/consumer`→일반마케팅, `phonetic/semantic`→번역·언어학. **노이즈 범인은 방법명 부재가 아니라 generic 존재.** 방법 논문은 seed 담당이므로 쿼리 tail 에 방법명 불필요 — seed 트랙과 역할 분담 (쿼리=도메인 회수, seed=방법 회수).

### 최종 측정 (Proposed Framework 섹션, OA+SS raw 회수, seed·vertex 격리)

R2→R6 궤적 (동일 조건 4-way):

| 버전 | tail | OA | SS | 명백무관 |
|---|---|---:|---:|---:|
| R2 (범용, before) | measurement model construct operationalization scale | 6 | 0 | 2 |
| R3 (v1 과교정) | phonetic Levenshtein visual Jaro-Winkler semantic embedding cosine | 0 | 0 | — |
| R4 (v2 방법명완화) | similarity measurement phonetic semantic | 9 | 0 | 3 |
| R5 (v3 도메인전용) | trademark confusion dilution | 9 | 4 | **0** |

5섹션 통일 실측 (R6): 전 섹션 명백무관 **0/5**, SS 전 섹션 ≥1 (0→7/1/4/2/5). OA recall 9~10 안정.

### 측정 주의 (recall 절벽)

도메인 명사 과다 강제 시 catch 72 의 정반대 실패 = recall 0 붕괴 (R3: 희귀 방법명 5개 AND 매칭 → OA 0건). **처방은 "특정 방법명 추가"가 아니라 "generic 제거"** — 도메인어는 흔한 단어라 recall 유지, generic 만 제거하면 노이즈만 빠짐.

### catch 박제

- **catch 72** (HIGH · retrieval · 해소): section_to_query 범용 tail (generic/방법명) 이 topic 뒤 append 되어 도메인 무관 논문 회수 (소프트웨어·일반마케팅·번역·언어학). **해소**: topic-scoped override, tail=상표 도메인어 3~4단어, 방법명·generic 배제. **정량 검증**: 2026-07-04 실측 5섹션 명백무관 0/5 (R2 before 2건 → 0). prevention: 쿼리 tail 은 도메인 앵커 전용, 방법 논문은 seed 담당 (역할 분리 원칙).
- **catch 74 부분 해소** (SS 무응답): SS 0건 원인이 백엔드 고장 아닌 **장쿼리 (15단어)** 로 확정 — 12단어 통일 후 전 섹션 SS ≥1 회수 부활. 완전 해소 (OA/SS 쿼리 길이 분리) 는 별 task.
- **catch 78** (MID · cost · 신규): paper_section_fetch 가 vertex_web_search 무조건 호출 (SKIP_VERTEX_SEARCH 무시), chunk 0 기여인데 유료 Gemini 콜 발생. ※grounding 연관 미확인 — "회수 경로 한정 0 기여"로만 기록. 본 트랙 밖.

### re-entry 조건

1. 상표 외 다른 주제 논문 작성 시 → 해당 도메인용 override 추가 필요 (현재 trademark 전용, 범용 mapping 은 fallback 유지).
2. SS 회수 추가 증대 필요 시 → OA/SS 쿼리 길이 분리 (OA=장쿼리 관대, SS=단쿼리 선호). catch 74 독립 트랙.
3. Introduction tail `consumer perception` 이 일반마케팅 노이즈 유입 시 → 해당 토큰 제거 (현재 애매 2건, 명백무관 0 이라 미조정).

### commit chain (참조)

```
(이 commit) §paper-writer-2 catch 72 close — override 블록 + dev 박제 (catch 72 해소 / 74 부분 / 78 신규)
```

**status: closed (2026-07-04)** — §paper-writer-2 catch 72 쿼리 교정 트랙 정식 종결. 5섹션 명백무관 0/5 + SS 부활 (0→전섹션≥1) + recall 유지 (OA 9~10). seed 트랙과 합쳐 인용 정밀도 작업 완결. 잔존 별 task: catch 74 완전 해소 (OA/SS 쿼리 분리) · catch 78 확인 (vertex grounding 연관) · Intro tail 미세조정 (조건부).

---

## §paper-writer-2 catch 74 close (2026-07-04) — OA/SS 쿼리 길이 분리 (SS tail-only 단쿼리)

### 결론 (트랙 완료)
catch 72 부분해소로 남겨둔 SS 장쿼리 완전해소. paper_section_fetch fan-out 에서
SS 백엔드만 topic 프리픽스를 제거한 tail-only 단쿼리를 수신하도록 in-body 분기.
OA·vertex 는 full query(topic+tail) 유지. 튜플 리터럴·반환 shape 무변경.

### 진단
SS 0건 원인 = topic(9단어)+tail 합산 13~15단어 장쿼리. SS Graph API 는 장쿼리에
빈 결과. OA 는 relevance 검색이라 장쿼리 관대(9~10 유지). 백엔드별 쿼리 길이
민감도가 달라 "단일 쿼리 fan-out" 이 SS를 굶김 → 백엔드별 쿼리 분리로 해소.

### 구현 (agent/web_search.py paper_section_fetch)
- `ss_query = query.removeprefix(topic.strip()).strip() or query` (query 직후)
- fan-out 루프: `fn(ss_query if backend=="semantic_scholar" else query)`
- tail 빈 경우(범용 폴백·미등록 섹션 query==topic) → `or query` 로 full 안전 폴백
  (빈 쿼리 회귀 방지). 로그 line 은 full query 유지.

### 최종 측정 (5섹션, OA+SS raw, seed·vertex 격리, 같은 런 before/after)
| 섹션 | tail | SS_before | SS_after | noise | OA |
|---|---|---:|---:|---:|---:|
| Introduction | trademark confusion consumer perception | 7 | 5 | 0 | 10 |
| Theoretical Background | trademark confusion dilution doctrine | 1 | 6 | 0 | 9 |
| Proposed Framework | trademark confusion dilution | 4 | 4 | 0 | 9 |
| Research Design | trademark confusion survey empirical | 2 | 6 | 0 | 10 |
| Expected Contributions | trademark law consumer protection | 5 | 8 | 0 | 9 |

SS 합계 19→29. 굶주리던 섹션 회복(TheoBg 1→6·RD 2→6·EC 5→8). 노이즈 0/5,
OA full 무변경(9~10), SS_after 섹션 변별 유지(dilution군/survey군/protection군 분리).

### catch 박제
- catch 74 (MID · retrieval · 해소): SS 0건 = 장쿼리(13~15단어). 해소: SS tail-only
  단쿼리 분기. 검증 2026-07-04 5섹션 SS ≥4, 노이즈 0/5. prevention: 백엔드별
  쿼리 길이 민감도 상이 — OA 관대/SS 엄격, fan-out 시 백엔드별 쿼리 분리.

### re-entry 조건
1. OA도 축약 필요 시(현재 full 9~10로 문제없음) → OA용 쿼리도 별도 파생.
2. 다른 도메인 topic 에서 tail 이 topic 과 안 겹쳐 removeprefix 무효 시 → 분리
   로직 재확인(현재 override tail 은 topic 뒤 append 구조라 항상 유효).
3. OA 섹션 변별 저하(topic 지배로 동일 core 반복) 개선 필요 시 → 별 task
   (catch 74 밖, OA는 이번 무변경).

### commit chain (참조)

```
(이 commit) §paper-writer-2 catch 74 close — SS tail-only 분기 + dev 박제
```

**status: closed (2026-07-04)** — catch 74 완전 종결. SS tail-only 분리로 전 섹션
SS ≥4 회복 + 노이즈 0/5 + OA 무변경. catch 72(도메인 앵커)와 합쳐 상표 쿼리
파이프라인 정밀도 완결.

---

## §paper-writer-2 axis3 재설계 close (2026-07-04) — combined-mean 폐기 → academic_ratio 단일 판정

### 결론 (트랙 완료)
axis3 판정부(`scripts/§paper-writer-1/measure_paper.py` `_eval_axes`)가 두 구조적
모순으로 **영구 FAIL** 이던 것을 해소. 개별 백엔드 문턱(oa/ss/combined)을 폐기하고
학술 회수율 단일 지표 `academic_ratio` + 단일 임계 0.50 으로 재설계.

### 진단 (구 산식의 구조적 영구 FAIL — 2 모순)
- **catch 75** (combined-mean quirk): `combined = mean(oa, ss, vx)` 인데 세 비율이 같은
  분모의 분율이라 합 = 1.0 → mean 최대 **0.333** < 임계 0.50 → 어떤 분포에서도 미달.
- **모순②** (oa/ss 동시 문턱 불가): `oa ≥ 0.70 ∧ ss ≥ 0.40` 은 같은 분모라 합 1.1 > 1.0
  → 동시 성립 불가. 즉 verdict=PASS 가 산식상 봉쇄돼 있었음.

### 신 산식
```
academic_hits  = openalex + semantic_scholar + vertex_academic
academic_ratio = academic_hits / total          # total = 전체회수 (vertex_web 포함)
verdict        = PASS  if academic_ratio >= 0.50  else FAIL
```
- vertex chunk(`{uri, title, domain}`)를 **ACADEMIC_DOMAINS 도메인 필터**(`_chunk_is_academic`,
  domain 우선·uri host 폴백·www/subdomain 정규화)로 학술/비학술 가름.
- **vertex_web(비학술)은 분모에 남겨 페널티** (변별력 + 비학술 dilution 개선 유인 유지) — X안.
- 개별 `oa_pass/ss_pass/combined_pass` 폐기. 오해 네이밍 `vertex_filtered_ratio`(구: vx 와
  동일, 실제 필터 없음) 제거 → `vertex_academic_ratio`(실제 도메인 필터 반영값)로 대체.

### 공유 모듈 이관 (ACADEMIC_DOMAINS)
- 구: `scripts/§academic-1/measure_ab.py` 인라인 40개 정의 — axis3 경로 미참조였음.
- 신: `scripts/common/academic_domains.py`(§ 없는 중립 폴더) 로 **글자 무변경 이관**.
  measure_ab.py 는 `from common.academic_domains import ACADEMIC_DOMAINS` **import 전환만**
  (로직 무변경). 회귀 dry PASS: 이관 전(HEAD)/모듈/import 후 3자 대칭차집합 ∅, `is` 동일 객체.
- ⚠️ 개수 정정: 실제 **40개**(소스 주석·git·len 일치). 정찰 초기 "43" 은 오산.

### R2-b 실측 (3런, axis3 전용 하버스 · vertex 검색 5콜/런 · 본문생성 스킵)
topic = `consumer perceived trademark similarity and likelihood of confusion` (3런 동일)

| run | academic_ratio | hits/total | oa | ss | vertex_academic | vertex_web |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 0.532 | 84/158 | 60 | 24 | 0 | 74 |
| 2 | 0.549 | 89/162 | 60 | 29 | 0 | 73 |
| 3 | 0.517 | 90/174 | 60 | 29 | 1 | 84 |

- **academic_ratio mean 0.533 · min 0.517 · max 0.549 · 분산폭 0.032** → 임계 0.50 에서 3런 PASS.
- OA=60 3런 고정(seed 13 + fan-out 안정). total 변동(158~174)은 vertex 회수(73~84)+SS(24~29) 탓.
- 비용: 3런 총 vertex 15콜 ≈ 20.6k tok(gemini-2.5-flash grounding) + OA ~$0.001/콜, SS 무료 ≈ $0.06~0.09.

### vertex 학술률 정정 (핵심 발견)
- 정찰 R1 의 "vertex 학술 16%" 는 **인플루언서 토픽(measure_ab academic-en)** 값.
- **상표 토픽 vertex 학술 = 0~1.2%** (R2-b 실측, vertex_academic 0/0/1). vertex 회수는
  전부 blog/news/agency 웹(forbes/medium/intelliplans 등) → ACADEMIC_DOMAINS 미hit.
- ∴ ②안 도메인 필터의 실효는 **"vertex 학술 살림"이 아니라 "vertex 블로그 차단"**.
  vertex_web 74~84개가 분모 페널티로 academic_ratio 를 ~절반으로 누름(vertex 제거 시 OA+SS만 = 1.0).

### catch 박제
- **catch 75** (해소): combined-mean ≤0.333 quirk + 모순② → academic_ratio 단일 판정으로 제거.
- **catch 79** (LOW-MID · methodology · 신규 · **미해결, 기록만** · **2026-07-05 재정의**):
  vertex chunk 는 authors/year/doi 무필드라 `format_apa7` 통과 시 `"(n.d.). <domain>."` bare
  라인 생성(title 이 도메인 그 자체). **재정의(R1 정찰)**: `APA_REGEX` 가 `(n.d.)`·`(YYYY)` 둘 다
  매칭 + `format_apa7` 이 모든 라인에 둘 중 하나를 항상 방출 → **axis1 pass_ratio 는 구조적으로
  1.0 고정(포화 지표, 변별력 0)**. backup JSON 실측: References 169줄 중 116줄(68.6%)이 도메인
  껍데기인데도 pass_ratio 1.0. → catch 79 실효는 ~~"APA 통과율 오염"~~ **아님**. 실효 = ① 딜리버러블
  References 의 68.6% 가 도메인껍데기 오염 + ② axis1(임계 0.8)이 품질을 전혀 변별 못 하는 포화 지표.
  **axis3 트랙 밖** — axis1 재설계(author/venue/doi 실체 판정)는 **별 트랙**으로 등재. 껍데기 원천
  차단은 catch 78(vertex 스킵) 몫.
  **→ 갱신 (2026-07-05): axis3 몫(게이트 부적합)은 「axis3 기술자 재정의 (R2)」에서 기술자 강등으로
  흡수·종결. catch 79 잔여 = axis1 실체판정 별 트랙 + catch 78 껍데기 차단만.**

### re-entry 조건
1. 다른 도메인 topic 에서 vertex 학술률이 유의미(≠0)하면 → vertex_web 분모 페널티 강도 재검토.
2. 임계 0.50 이 파이프라인 개선(SS·OA 수율 ↑)으로 상시 큰 마진 PASS 되면 → 상향 재조정 검토.
3. catch 79(vertex n.d. axis1 오염) 착수 시 → axis1/References 트랙에서 별도 처리.

### 변경 파일
- `scripts/common/academic_domains.py` (신규 · ACADEMIC_DOMAINS 40 이관)
- `scripts/common/__init__.py` (신규 · 빈 패키지 마커)
- `scripts/§paper-writer-1/measure_paper.py` (axis3 재설계 + `_chunk_is_academic` + 임계 0.50 + `statistics` dead import 제거)
- `scripts/§academic-1/measure_ab.py` (ACADEMIC_DOMAINS import 전환만, 로직 무변경)

**status: closed (2026-07-04)** — axis3 재설계 종결. 구조적 영구 FAIL(catch 75 + 모순②)
제거 + 학술 회수율 단일 판정(임계 0.50) + R2-b 3런 0.517~0.549 PASS 검증. vertex 도메인
필터는 "블로그 차단" 실효로 판명. 잔존 별 task: catch 79(vertex n.d. axis1 오염, 미착수).
**⚠️ superseded by 2026-07-05 「axis3 기술자 재정의 (R2)」(아래)** — 임계 0.50 게이트 자체가
vertex-skip 후 1.000 포화로 변별력 0 판명 → 게이트 폐기·기술자 강등으로 대체.

---

## §paper-writer-2 catch 80 close (2026-07-05) — 본문 [[N]] 글로벌 승격 (섹션-로컬↔footer 오정렬 해소)

### 증상
본문 in-text 인용 `[[N]]` 은 섹션당 1-based **로컬**(writer 가 섹션별로 `enumerate` 리셋,
`agent/paper_section_writer.py:47`), footer References 는 `section_chunks_all` concat **글로벌**
1-based(`measure_paper.py:206` build + `:94` enumerate). **오프셋 보정 부재.** → 섹션 1만 offset 0
으로 우연 정합, 섹션 2~5 는 +29/+59/+117/+143 어긋나 인용이 엉뚱한 논문 지시. 실측(리포트
`paper_..._20260628_123513.md`): 섹션 2~5 인용 N 전부 ≤13 → 죄다 Introduction footer 밴드(1~29)로
오낙착. 섹션 1(6건)만 정상.

### 해결 = (b) 본문 [[N]] 글로벌 승격
`_run_one_paper` 2-지점 배선 + 헬퍼:
- `_shift_citation_markers(body, offset)`: `\[\[(\d+)\]\]` 캡처그룹 → `int(N)+offset` 재조립
  (자릿수 안전, offset==0 no-op).
- 지점①(`measure_paper.py` extend 直前): `cite_offset = len(section_chunks_all)` 스냅
  (루프 지역변수, = Σ 섹션 1..k-1 chunk 수 = 글로벌 오프셋).
- 지점②(append 直前): `body = _shift_citation_markers(body, cite_offset)`.
- (a) footer 포맷 변경(高침습) · (c) 매핑테이블(오버킬) 기각.

### 무접촉 확정
axis1(`apa_lines` 만 읽음 `measure_paper.py:230-232`, pass_ratio 1.0·n=169 불변) · axis3 · footer(
`build_apa_references`) · writer · prompts. 헬퍼는 `section_bodies` 문자열만 치환.

### 검증 (3겹 dry, 유료 0)
- **STOP-1**(삽입점): extend 直前 스냅 2-지점 확정 + 오프셋 손계산 `[0,29,59,117,143]` (backup
  per_section.chunks_count `[29,30,58,26,26]` 누적) 일치.
- **STOP-2**(regex 자릿수): `[[1]] [[12]] [[9]]`+29→`[[30]] [[41]] [[38]]` / 인접 `[[1]][[2]]`→
  `[[144]][[145]]` / 중복 둘 다 / offset=0 no-op / 마커無 0건 — 전부 PASS.
- **STOP-3**(기존 리포트 교정 검산, 재실행 아님): recon 4건 정확 일치
  `[[13]]→[[42]]`·`[[12]]→[[71]]`·`[[5]]→[[122]]`·`[[8]]→[[151]]`, 전 섹션 전량치환 누락 0,
  교정번호 전부 해당 섹션 footer 밴드 내부.

### 교차 발견 (→ catch 79 부분 해소)
catch 80 오정렬이 본문 학술인용을 **vertex 도메인껍데기**(#13 `trestlelaw.com`, #12 `gfrlaw.com`)에
오연결하고 있었음. 교정으로 실제 학술논문(Johannessen 2011, Kruger 2014 등) 연결 복원. 단 footer
껍데기 116줄 **존재 자체**는 잔존 → catch 78(vertex 스킵) 몫(catch 80 ⟂ vertex, 독립 축).

### 변경 파일
- `scripts/§paper-writer-1/measure_paper.py` (`_shift_citation_markers` 헬퍼 + `_run_one_paper` 2-지점)

### re-entry 조건
1. vertex 스킵(catch 78) 등으로 `section_chunks_all` 재구성 시 → 오프셋은 `len()` 동적이라 자동 정합
   (하드코딩 없음). 단 섹션 내 dedup 로 chunk 수 변동 시 offset 자동 반영 확인.
2. writer 가 `[[N]]` 외 인용 표기(예: `[N]`, `(N)`)를 방출하기 시작하면 → regex 확장.

**status: closed (2026-07-05)** — catch 80 종결. 섹션-로컬↔글로벌 오정렬을 본문 [[N]] 글로벌
승격으로 해소. 3겹 dry(삽입점·regex·기존리포트 교정) PASS, axis1/axis3/footer 무영향. 교차로
catch 79 인용-껍데기 오연결 부분 해소(껍데기 존재는 catch 78 잔존).

---

## §paper-writer-2 axis3 기술자 재정의 (R2, 2026-07-05) — 품질 게이트 폐기 → 파이프라인 건강 기술자 (catch 79 흡수)

### 결론 (07-04 axis3 재설계 close 를 재정의로 대체)
07-04 close 의 `academic_ratio ≥ 0.50` 단일 임계 게이트를 **폐기**. axis3 를 품질 게이트에서
**파이프라인 건강/커버리지 기술자**로 강등하고 verdict 를 3-state(PASS/WARN/FAIL)로 재배선.
outer key `axis3_backend_ratio` → **`axis3_pipeline_health`** 개명. catch 79 는 이 트랙으로 흡수
(새 catch 번호 없음).

### 게이트안 폐기 근거 (R1 + R1.5 정찰, read-only · 유료 0)
- **`academic_ratio` 는 게이트로 변별력 0**: R1.5 확정 — `backend_counts.other=0`(3런) 이라 vertex
  스킵(catch 78) 후 ratio = (oa+ss)/(oa+ss) = **정확히 1.000**(포화). 게이트가 아무것도 안 잼.
- **유일한 런간 변동이 429 노이즈**: 후보 지표 `ss/(oa+ss)` 도 3런 중 4/5 섹션 완전 평탄, 유일
  변동은 run1 Introduction SS 0↔5 — 원인은 `[semantic_scholar] 429 backoff`(axis3_run1.log:9).
  즉 품질 신호 아닌 rate-limit 아티팩트에 임계를 거는 꼴 = **catch 79/과거 combined-mean 함정 재현**.
- ∴ 품질 게이트로서 axis3 회생 불가 → 목적을 게이트→기술자로 하향. 학술 품질 실체 판정은
  **axis1 재설계(별 트랙)** 로 이관.

### 신 정의 — 3-state 파이프라인 건강 기술자
섹션별 backend 카운트(`per_section[*].backend_counts`, 신규 P1 캡처)에서 파생, **분할 severity**:
```
sections_with_zero_oa (OA=0) OR sections_with_other (other>0)  → FAIL
elif sections_with_zero_ss (SS=0)                              → WARN
else                                                           → PASS
```
- **SS=0 → WARN (게이트 아님)**: SS 0-death 는 429 백오프 소진 등 flaky 원인(R1: run1 Intro SS=0
  은 429, 단 run1 EC 는 429 맞고도 재시도 회복 SS=8 → n=1 단일사례). 자동 FAIL 금지 = R1 원칙.
- **OA=0 → FAIL**: OA 는 완전 결정론(3런 섹션별 10/12/16/13/9 불변) → 0 은 불변식 위반 = 파이프라인 완파.
- **other>0 → FAIL**: 정상선 3런 전부 0 → >0 은 미상 `_backend` 태그 누출 = 코드/설정 회귀 tripwire.
- `academic_ratio`·`academic_hits` 는 **informational 로만 유지**(판정 미참여). 구 `ACADEMIC_RATIO_THRESHOLD`
  상수 + `oa_ratio/ss_ratio/vertex_ratio/vertex_academic_ratio` 진단필드 폐기.

### 임계 정정 (3단 정합)
- 인계메모 추정치 **"임계 0.60" 은 오기** — §academic-4 트랙(catch 51/61 `academic_source_ratio` 0.60)과
  혼동한 값으로 paper-writer axis3 와 무관.
- 07-04 close 실제 커밋값 = **0.50**(`ACADEMIC_RATIO_THRESHOLD=0.50`, dcbb7f12 measure_paper.py:158).
- **현재 = 임계 자체 폐기**(게이트 삭제) → 0.50/0.60 논의 모두 무의미해짐.

### 배선 (measure_paper.py, +67/−39 · 유료 0)
- `_count_backends(chunks)` 헬퍼 신설 — aggregate(`_eval_axes`)·per-section(`_run_one_paper`) **분류
  단일 소스**(구 인라인 카운트 루프 중복 제거). vertex 는 `_chunk_is_academic` 로 학술/웹 분해.
- **P1**: `per_section[section]` 빌드에 `"backend_counts": _count_backends(chunks)` — catch 80 offset
  스냅/extend/shift 라인 무접촉, chunks read-only.
- **P2/P3**: `_eval_axes` axis3 → 섹션별 파생(`sections_with_zero_ss/oa/other`, `per_section_backends`)
  + 3-state verdict + `academic_ratio` informational.
- 개명 outer key `axis3_pipeline_health`(잔존 `axis3_backend_ratio` 참조 0 확인).
- 종합부 무배선: 크로스-axis verdict 종합기 부재(`main` :382-383 `r.update` 병합만) → WARN 3-state 안전.

### dry 검증 (오프라인 재생, measure_paper 풀런 없음 · 유료 0)
- **DV1**(저장 axis3_run{1,2,3}.json 재생): run1 → **WARN**(Intro SS=0 가시화) · run2/3 → **PASS**.
  aggregate backend_counts·academic_ratio 가 R1.5 실측(60/24·60/29·60/29+1, 0.532/0.549/0.517) 정확 재현
  = 헬퍼 충실도 교차검증.
- **DV2**(synthetic 5경로): 정상→PASS / SS=0→WARN / OA=0→FAIL / other=1→FAIL / SS=0∧OA=0→FAIL
  (FAIL>WARN 우선) — 전부 기대 일치.

### catch 79 흡수
- **catch 79 = 이 트랙으로 흡수**(별 catch 번호 없음). R1 재정의(07-04 close 섹션 참조)의 실효
  ①(References 68.6% 도메인껍데기)·②(axis1 포화) 중 **axis3 게이트 부적합분은 본 기술자 강등으로 해소**.
- 남은 **axis1 포화(author/venue/doi 실체 판정)는 별 트랙**(catch 79 잔여 = axis1 재설계), 껍데기 원천
  차단은 **catch 78(vertex 스킵)** 몫. → catch 79 의 axis3 몫 종결, axis1 몫 이관.

### 변경 파일
- `scripts/§paper-writer-1/measure_paper.py` (`_count_backends` 헬퍼 + P1 per_section backend_counts
  + P2/P3 3-state 기술자 + `axis3_pipeline_health` 개명 + `ACADEMIC_RATIO_THRESHOLD` 폐기)

### re-entry 조건
1. SS 429 견고화(retry/백오프 강화)로 SS 0-death 제거 시 → WARN 신호 발생 빈도 재평가.
2. catch 78 vertex 스킵 첫 유료 런 후 → `per_section_backends` vertex_* = 0 반영 + 기술자 verdict
   무영향(1.000 포화가 게이트 아닌 informational) 실측 검산.
3. axis1 재설계(catch 79 잔여) 착수 시 → 학술 실체 판정 축을 axis1 로, axis3 는 건강 기술자로 분리 유지.

**status: closed (2026-07-05)** — axis3 기술자 재정의 종결. 07-04 게이트(임계 0.50) 폐기 → 3-state
파이프라인 건강 기술자 강등 + `axis3_pipeline_health` 개명. R1/R1.5 정찰로 게이트 변별력 0(vertex-skip
후 1.000 포화 · 유일변동 429 노이즈) 확정, DV1/DV2 오프라인 검증 PASS. catch 79 axis3 몫 흡수·종결,
axis1 실체판정 몫은 별 트랙 이관. 잔존: catch 78(vertex 스킵 유료 배선), axis1 재설계.

---

## §paper-writer-2 catch 78 close (2026-07-05) — vertex skip 플래그를 paper fan-out에 배선 (References 껍데기 −92, 학술 100%)

### 증상 (버그)
- `paper_section_fetch`(web_search.py) fan-out 루프가 vertex_web_search 를 **무조건 호출** — `SKIP_VERTEX_SEARCH`
  를 무시. 레거시 web_search 경로(:754/:832)만 플래그 존중, paper 경로는 미존중.
- 결과: 영어 상표 토픽에서 vertex 가 law-firm 블로그 등 **비학술 껍데기**를 References 에 다량 주입
  (author/year 없는 맨 도메인 `(n.d.). arpgweb.com` 류). 유료 Gemini 콜 + 참고문헌 신뢰도 훼손.

### 배선 (3파일 단일 커밋)
- **A. `agent/web_search.py:1982`** — fan-out 리스트를 base 2튜플(oa·ss)로 빌드 →
  `_cfg_bool("SKIP_VERTEX_SEARCH", False)` 이 False 일 때만 vertex 튜플 append. **mid-loop continue 아님**
  (dead 튜플·skip 로직 분산 방지, R1 판정). `_cfg_bool` 재사용 = **신 파서 0**(catch 71 상류 CFG 파싱 차단됨).
  skip 시 레거시 :833 스타일 로그 1줄.
- **B. `topics/academic-trademark-similarity-consumer.env:21`** — `SKIP_VERTEX_SEARCH=false → true`.
  토픽 프리셋(override=True)이 최종 승자라 flip 기계적 관철(R1.5 (a) 실증).
- **C. `scripts/§paper-writer-1/measure_paper.py:121`** — 드라이버 `SKIP_VERTEX_SEARCH="0" → "1"` 정합.
  이 키는 config 최초 빌드가 드라이버 override 後(lazy import)라 **토픽 프리셋이 결정 = 드라이버 값 no-op**;
  혼동 방지 위해 토픽 값(skip)과 정합. :108 stale 주석 갱신.

### 실측 (첫 유료 런, 2026-07-05T06:59Z · exit 0)
- References **169 → 77** (−92 = vertex law-firm 껍데기 제거). `(n.d.)+맨도메인` 껍데기 잔존 **0**.
- POST 77 = OA 60 + SS 17 = **100% 학술 backend** (backend_counts total 77 완전 일치).
- axis3 검산 3층: **L1** vertex_web=0 전 5섹션 / **L2** `sections_with_zero_oa=[]` (OA 10/12/16/13/9 결정론
  baseline 일치 = OA 파이프라인 무개입) / **L3** verdict=**WARN** (SS 429 flaky: Proposed Framework·
  Expected Contributions SS=0, R1 원칙상 WARN-only 게이트 아님). 3층 전부 PASS.

### ⚠️ known divergence (차기 통합 catch 후보)
- **paper 경로 = flat flag**(`SKIP_VERTEX_SEARCH`), **레거시 academic 경로 = catch-43 language routing**
  (web_search.py:750-753, `_q_lang=="ko"` 시 skip) — 두 경로 vertex 게이팅 **상이**. 현재 무해
  (참고문헌은 paper 경로 전용 = paper_section_fetch, measure_paper.py:217 단독; R1.5 확인2로 레거시
  미개입 확정). 통합 시 catch 후보.

### catch 79 잔여 (별 트랙, 78 무관)
- axis1 APA_REGEX(measure_paper.py:148-150) `(n.d.)`/`(YYYY)` 무조건 매칭 → pass_ratio 1.0 포화.
  78 로 vertex 껍데기는 원천 차단되나 **(n.d.) 매칭 포화 자체는 axis1 몫으로 잔존**. author/venue/doi
  실체 판정 재설계는 별 트랙(vertex 무관, 독립 착수).

### 변경 파일
- `agent/web_search.py` (A) / `topics/academic-trademark-similarity-consumer.env` (B)
- `scripts/§paper-writer-1/measure_paper.py` (C) / `README-dev-§14.md` (박제)

### re-entry 조건
1. 한글/틈새 토픽 default 확정 시 → vertex 16% 학술률(mdpi/researchgate)이 진짜 문헌인지 껍데기인지
   실측 후 토픽별 flag default 결정 (상표=off 는 확정, 한글 토픽 숙제 잔존).
2. paper↔레거시 vertex 게이팅 통합 필요 시 → known divergence 항목 참조.
3. axis1 재설계(catch 79 잔여) 착수 시 → (n.d.) 포화 해소.

**status: closed (2026-07-05)** — vertex skip 플래그 paper fan-out 배선 종결. References 169→77
(껍데기 −92, 학술 100%), axis3 3층 검산 전부 PASS(vertex_web=0 / OA baseline 유지 / WARN). 커밋됨.
잔존: 한글 토픽 vertex 학술률 실측, paper↔레거시 게이팅 통합, axis1 재설계.

-------

## §paper-writer-2 catch 79 close (2026-07-06) — axis1 재설계: regex 포화 → venue OR doi 존재 3등급 실체 판정

### 한 줄
axis1 이 인용을 `(YYYY)`/`(n.d.)` 정규식 통과로 재던 포화 게이트(pass_ratio 1.000 고정, 변별력 0)를
폐기하고, chunk 최상위 필드(venue/doi) **존재**로 인용 실체를 3등급 판정하는 결정론·무료 detector 로 교체.
catch 78 이 (n.d.) 껍데기를 원천 차단한 뒤라 axis1 이 재는 대상이 순수 학술 인용뿐 → 재설계 효과 깨끗이 측정.

### 재설계 내용
- **A(조립 문자열 regex 되파싱) 폐기 → B(chunk 최상위 필드 직독) 채택**. `format_apa7` 이 year 를 항상
  `(YYYY)`|`(n.d.)` 로 뱉어 구 regex 는 무조건 매칭 = 포화. 재료(authors/year/venue/doi)가 chunk 원본
  필드로 이미 존재(OA `openalex.py:160-`, SS `semantic_scholar.py:222-`), `build_apa_references` 도 이미
  최상위 직독 중 → B 무손실.
- **detector `axis1_grade(chunk)`** (measure_paper.py): 완전체(venue AND doi) / 부분체(venue XOR doi) /
  결손(둘 다 없음). **결손만 fail**. 빈 판정 `_blank` = None·''·공백 (SS 는 venue='' 반환 = R2.5 지뢰1).
- ⭐ **doi 필수 아님**: 법학 리포지토리 정식인용(Beebe/Tushnet/Senftleben/Heymann)은 doi 없이도 학술 →
  venue OR doi. doi 필수 걸면 이번 런 부분체 34개(venue있음·doi없음) 전부 오탈락.
- **threshold 0.90**, **3-state verdict**: FAIL(ratio<0.90) / WARN(ratio≥0.90 이나 결손>0) / PASS(결손 0).
  **gate 유지**(axis3 처럼 informational 강등 아님 — R1 확정). 파생 필드: grade_dist·n_missing·missing_by_section.

### 실측 (remeasure 유료 런 2026-07-06T09:46Z, exit 0, vertex off)
- axis1 = **WARN**, pass_ratio **0.944**(=84/89), 완전체 43 / 부분체 41 / 결손 5. old 1.000 포화 대비 변별 복원.
- 오프라인 R3 설계(chunks_raw_dump.json 89개)와 **라이브 완전 일치**(등급 분포·ratio·verdict·섹션 결손 동일).
- L2: References 89(OA 60 + SS 29) = R2.5 스케일 유지, 참고문헌 무붕괴. axis2/axis3 무변경(axis3 PASS).

### known divergence (무해, 별 트랙 후보)
- **결손 5 전부 OA·정식 논문의 OA 메타 미충전**(껍데기 아님): Janis&Dinwoodie "Confusion Over Use"(3섹션
  중복)·윤선희(2005 한글)·Beebe&Germano(2019). venue/doi 둘 다 OA 가 못 채운 케이스 = axis1 "존재만"
  판정상 정당한 fail 이나 실체는 학술.
- **R2 계측 상주**: `_run_one_paper` 가 각 chunk 에 `_section` 태그(_backend 대칭 additive) + `main` 이
  `chunks_raw_dump.json` 별도 덤프(c_paper_measurement.json 무오염). detector 재튜닝 재료로 상주.

### 변경 파일 (2파일 단일 커밋)
- `scripts/§paper-writer-1/measure_paper.py` (detector 이식 + R2 계측 + 채점부 배선 + 구 regex 정정 박제)
- `README-dev-§14.md` (본 박제)

### 별 트랙 후보 (axis1 밖, 미착수)
1. **OA 메타 충전 개선**: 결손 5 전부 OA venue/doi 미충전. OA API landing_page/host_venue 재조회로 보강 여지.
2. **venue 부정합/predatory 판별**: SS Anita(2024) 제목-저널 불일치(상표법 논문인데 venue='African J of
   Biological Sci') 류. 존재는 하나 부정합 = 품질 축. axis1(존재·결정론·무료) 밖 = embedding/LLM 별 트랙.

### re-entry 조건
1. OA 메타 충전 개선 착수 시 → 결손 5(전부 OA)를 landing_page_url·host_venue 보강으로 부분체 승격 검토.
2. venue 부정합 판별 필요 시 → 별 트랙(품질 축, axis1 결정론 계약 밖).
3. threshold 0.90 재조정 필요 시 → 결손율 실분포(현 5.6%) 기준. 부분체는 구조상 pass(정상 법학인용 오탈락 0).

**status: closed (2026-07-06)** — axis1 regex 포화 → venue OR doi 3등급 실체 판정 재설계 종결.
remeasure WARN(0.944, 결손 5) = 오프라인 설계 라이브 재현, 포화 회귀 없음. 커밋됨.
잔존 별 트랙: OA 메타 충전 개선, venue 부정합/predatory 판별.


## §paper-writer-2 catch 81 close (2026-07-07) — 한 런 내부 numbering feedback loop 절단 (본문↔참조 오매칭)

catch 80 글로벌 shift 산물이 `previous_sections`로 다음 섹션 writer 프롬프트를 오염 → writer가
글로벌 `[[N]]`을 복사→재shift 하는 **한 런 내부 feedback loop**(R1 규명). 상세 박제:
`scripts/output/§paper-writer-1/catch81_R2R3_close_20260707.md` (+ R1 `catch81_numbering_feedback_loop_report_20260707.md`).

### 배선 (leak 채널 절단, 2파일)
- `agent/paper_section_writer.py:58` — `prev_text`에서 `\[\[\d+\]\]` strip (프롬프트로 나가는 **로컬 복사본만**).
  `section_bodies`(=previous_sections leak + 최종 paper_body/반환 동일 리스트 공유)는 무손상 → footer 정합 불변.
  ⚠️ `:58` fallback `or "(없음 — 첫 section)"` 보존 필수(task 원본 누락분). `_CITE_MARKER_RE` 공유는 순환(script→lib)이라 inline만 가능.
- `prompts.py:439` — [[N]] 로컬-스코프 명확화 1줄(defense-in-depth). `:450`("표기 일관성"=용어/변수 ≠[[N]])은 불변.

### R3 유료 통제런 (references 89 byte-identical = 단일변수 통제) — 4종 PASS
| 판정 | baseline 004833 | R3 020918 |
|---|---|---|
| out-of-range | 9 occ / 8 distinct | **0 / 0** |
| 2-hop 사슬 | 1 (`[[112]]` 26→59→112) | **0** |
| footer 정합 | max 112 > 89 | max 82 ≤ 89 |
| 측정축 | axis1 0.944 WARN / axis3 PASS 1.0 | **identical** |

전 섹션 인용 유지·전량 in-range(가짜-PASS 아님). 인과(R1 §2 writer 실제 복사) 확정.
관찰: 본문 마커 52→21(생성변동+복사마커 소거, 판정 무위반) / strip 후 구두점 앞 공백 잔재(leak 입력만·무해·미수정).

### 변경 파일 (종결 커밋) — measurement JSON·output 논문 제외(관행)
- `agent/paper_section_writer.py`, `prompts.py`, `catch81_R2R3_close_20260707.md`, `README-dev-§14.md`(본 엔트리).

**status: closed (2026-07-07)** — leak 채널 strip + 프롬프트 명확화로 절단, 유료 통제런 4종 PASS로 인과 확정.
re-entry: 마커 수 변동이 인용밀도에 유의미하면 재검토 / 타 토픽·섹션수에서 재출현 시 leak 잔여경로 재진단 / faithfulness는 43 aligned 중 재선정(R1 §4).

---

## §paper-writer-2 catch 82 close (2026-07-10) — OA venue 단일경로 드롭 → type-aware locations[] fallback (venue 결손 5→0, axis1 WARN→PASS)

한 줄: OA venue를 `primary_location.source` 단일경로로만 읽어, 저널이 뒤 `locations[]`에 있으면 통째 드롭.
type-aware fallback + 수동 override 3건으로 회수. catch 80 close known divergence "OA 메타 충전 개선"의 직접 후속.
상세 박제: `scripts/output/§paper-writer-1/catch82_OA충전_R1R2R3_close_20260710.md` (R1 X/Y 판정 / R2 검수표 파트A·B / R3 dry+유료런).

### 배선 (2파일 + override + 박제)
- `tools/web_rag/openalex.py` — `_extract_venue()` 신설(+52/-3): (1)`primary_location.source`[type≠repo]
  (2)`locations[]` 순회 첫 저널 source (3)없으면 primary 리포명 보존(regression 0) (4)없으면 None.
  `:157-159` 인라인 → `_extract_venue(work)` 교체. ★raw_source_name 미채택(filename·vol번호·vendor-id·citation-dump garbage).
- `agent/web_search.py` — `_VENUE_OVERRIDES` 3건(+40): IEEE SMC / Cardozo Law Review / 인권과 정의(윤선희,
  KCI arti_id ART001008024). `paper_section_fetch` 출구 1지점. ★기존 work venue 필드 채움만(신규 ref 0).

### 실측 (유료 통제런 2026-07-10, exit 0, vertex off) — 단일변수 통제
- axis1: 결손 5→**0**, pass_ratio 0.944→**1.0 PASS**(complete 44/partial 45/missing 0).
- axis2 무이동 / axis3 무이동(학술 100% 89/89, `vertex_web=0`). references **89 불변**(신규 ref 0)=denominator 통제.
- override 5 chunk 착지 dry 오라클 일치. venue garbage 0.
- partial 45 잔존 = doi 결손(39) 무접촉(정상). Cortés(책) venue-None 정상(DOI 보유 → partial 등급).

### 반증·정정 박제
- "blanket host_venue 오독" 가설 **폐기** — 코드는 이미 신 스키마 읽음. 실제 기제 = 신 스키마의 **잘못된 단일 위치**(primary만, locations[] 미순회).
- arXiv/SSRN 프리프린트 = venue 표시 유지(OA에 저널 source 부재 = 데이터 문제, 규범선택 아님).
- ★baseline 정정: 77(catch 78 직후)은 stale, catch 74 SS 복구로 현 baseline **89**(OA60+SS29).
- ★라인 정정: 토픽 .env SKIP_VERTEX_SEARCH 값 = `:22`(:21은 주석). off-by-one 실파일 기준 정정.

### known divergence / 별 트랙 (미착수, 기록만)
- 윤선희 계열 KCI 커버리지: OA 완전결손. KCI 백엔드는 1건 위한 과투자 → 수동 override로 처리, 백엔드 미착수.
- IEEE SMC·Cardozo: raw_source_name에만 생존(clean)이나 자동 파싱 garbage 위험 → 수동 override 채택.
- doi 결손 39건: 별 트랙(venue와 기제 상이). / catch 80 "venue 부정합/predatory"(품질 축) 잔존.

### 변경 파일 (단일 커밋) — measurement JSON·output 논문 제외(관행)
- `tools/web_rag/openalex.py`, `agent/web_search.py`, `catch82_OA충전_R1R2R3_close_20260710.md`, `README-dev-§14.md`(본 엔트리).

**status: closed (2026-07-10)** — OA venue fallback 배선 + override 3건으로 결손 5→0, axis1 PASS. 단일변수 통제(ref 89 불변·axis2/3 무이동) 확인.
re-entry: raw_source_name 자동 파싱 필요해지면 guard 재설계(clean conference 화이트리스트) / KCI 커버리지 트랙 착수 시 override 3건 재검토 / 타 토픽서 repo-primary 패턴 재출현 시 REPO_TYPES 보강.

---

## §paper-writer-2 catch 83 close (2026-07-12) — citation-claim faithfulness rank: pool 재설계 + 마커 2단 교정 + full 근거 재조회 (근거길이 병목 인과입증, Beebe 총론성 미해소)

한 줄: 본문 인용이 근거를 의미상 왜곡 안 했나 = 상위층 품질축. 절대코사인 negative result → **상대 rank** 전환.
직전 rank 코드의 두 버그(정규식 다중묶음 누락 · pool을 fetch-출처로 오독)를 잡고, 240자 절단을 full로 풀어
"근거 길이가 rank를 좌우한다"를 **인과로 입증**(표적 [[5]] 0.077→0.615). Beebe 총론성만 미해소=별도 catch 후보.
박제 산출: `scripts/output/§paper-writer-1/rank_faithfulness_chunks_{raw,full_abstract}_dump.json`(240 vs full 대조).

### 배선 (2파일 신규 + dump + venv)
- `rank_faithfulness.py`(신규 283L) — 미실행 상태였던 rank 코드를 6종 수정:
  (1)`_MARK_RE` **2단 교정**(바깥 `[[.*?]]` 덩어리→내부 `\d+`, 다중묶음 포착; 페어추출·문장정제 **두 곳** 다).
  (2)pool 정의 재설계: `cited["section"]!=sec` misaligned 배제 **폐기** → **P∪{C} 합집합 rank**, m=|합집합|.
  (3)입력 repoint(20260710 논문 + chunks dump 인자화). (4)Beebe [[58]] 강제편입 특례를 **본 로직에 흡수**(분모 off-by-one 교정).
  (5)pool **identity dedup**(Beebe 5중 등재 자기복제 코사인 1.0 편향 차단). (6)tie **average-rank**(0.5).
  +최적화 2건: identity→embedding 캐시(중복 인코딩 제거), 섹션 `sims=emat@q` 1회.
- `refetch_abstracts.py`(신규 188L) — **order-preserving full backfill + fallback B**: old 89 identity/order 고정,
  abstract만 full로. fetch 미매칭 시 240 유지(`abstract_source` 태그로 혼재 명시). `_trunc240`→`_keep_abstract` 개명.
- `chunks_full_abstract_dump.json`(신규, gitignore 예외) — full 65건 전량 업그레이드(fallback 0 → rank pool 100% full).
- `.venv_emb` 신설(vertex 격리) — e5-large용. **버전 박제**: torch 2.2.2 / transformers 4.40.2 /
  sentence-transformers 2.7.0 / tokenizers 0.19.1 / safetensors 0.8.0 / numpy 1.26.4.

### 실측 (로컬 e5-large, 유료 0; OA/SS 재조회 $0 vertex off) — 240 vs full 단일변수 대조
- **표적1 [[5]] "인지과학+상표법" EC→Intro**: 240 pct **0.077**(rank 13/14) → full **0.615**(6/14). **+0.538. 인과 확정.**
  (같은 문장·pool, abstract만 240→full. 육안: 인지과학 논지 char 567~908, e5 반영권 내.)
- **표적2 Beebe [[2]] TB/PF**: 240 {0.5~0.909} → full {0.643~0.909, Intro 1.0}. **하위 안 됨. 미달.**
- **표적3 강제편입**: median 0.88/0.85, min0~max1.0 섞임. **충족**(구조편향 없음).
- bundle: 단독 median 0.95→**1.0**(주근거), 묶음 0.73→0.69(방증). cited_cos median 0.79 불변(절대 포화 재확인).

### 반증·정정 박제 (★ = 사용자 지정 필수)
1. **★정규식 착시 계보(항목4)**: 구 `_MARK_RE=\[\[(\d+)\]\]`는 단독만 인식. 실본문은 `[[1], [2], [7]]` 다중묶음 지배
   (catch 81 후 표기전환). **세 겹 착시** — T3 시뮬이 "PF·EC 인용 0"으로 오판→catch 83(인용소실) 가설. 사용자
   본문 육안 반증→재계수: 0710 마커 16→**58**(37% 누락), rank도 0706 기준 82중 30건(37%) 흘리던 중이었음.
   교훈: Y(측정도구 한계)를 경계하자던 트랙이 마커 계수 단계에서 Y에 걸림. **가설 전 계수부터 교정.**
2. **★over512 가설 반증(항목5)**: "full 2000자 초과→e5 512토큰 절단→rank 하위 몰림" 가설을 **사전 검증항목으로 박음.**
   결과 반증 — over512(n=10) median **0.8**, 하위 안 몰림. Beebe(2475자) over512인데도 상위. → **abstract chunking 불필요.**
   Beebe 실패 진범 = 512절단 아닌 **abstract 총론성**(앞 2000자 전부 총론). 검증항목 사전박기가 헛다리를 데이터로 차단.
3. **★negative result 계보 정정(항목7)**: 직전 절대코사인 실험(negative_result_..._20260706)도 **구 정규식 = 37% 페어
   누락 상태**에서 측정됐음. 결론(도메인 포화→절대임계 부적합)은 **유효**(rank 전환 정당)하나, 표본이 43이 아닌
   실제 더 많았을 것 = 기록 정정 필요. **full 파일럿에서도 cited_cos median 0.792 / std 0.033**(240의 0.791/0.037과
   사실상 동일)로 **도메인 포화 재확인** — 근거를 full로 늘려도 절대 코사인은 여전히 좁은 띠, 결론 재입증됨.
4. 환경유실 **3사례**(macOS 이전 "코드만 옮기고 환경은 누락"): subagent 3종 / SSL 루트 인증서 / 임베딩 스택.
5. rank 메커니즘 작동 확정 — 방증·주제이탈 인용을 하위로 정확히 포착(bundle 태그·최저 8건). full이 근거길이 병목 해소.

### known divergence / 별 트랙 (미해소, catch 후보 등록)
- **★표적2 총론성 = catch 후보**: "총론 문헌 반복인용은 rank로 판별 불가 — 정상 인용 가능성 배제 못 함.
  원래 발단(Beebe 5회 중복 등재 = 장식 인용 의심) **미해소**. abstract chunking 무효(총론 쪼개도 총론).
  LLM 직접 정합 판정 등 **rank 밖 축** 필요." → 상위층 faithfulness의 다음 표적.
- cited_no_abstract 17건(29%) 미개선 — 재조회로 empty 24 못 채움(OA/SS 미보유). 커버리지 한계.
- `extract_pairs.py:38/:91/:95`에 동일 구 `_MARK_RE` 버그 잔존 — rank는 자체추출로 무관, 재사용 시 교정 필요.

### 변경 파일 (단일 커밋) — measurement/rank JSON·논문 제외(관행), full dump만 gitignore 예외
- `rank_faithfulness.py`, `refetch_abstracts.py`, `extract_pairs.py`, `emb_cosine.py`(계보 자산 박제),
  `chunks_full_abstract_dump.json`(표준 근거 스냅샷), `.gitignore`(예외), `README-dev-paper.md`(본 엔트리).

**status: closed (2026-07-12)** — rank 작동 확정(pool 재설계·정규식 교정·full 근거). 근거길이 병목 인과입증(0.077→0.615).
re-entry: 표적2 총론성 → LLM 정합축 catch 착수 / cited_no_abstract 커버리지 개선 시 KCI·타 백엔드 / e5→BGE-m3 업그레이드는 rank 민감도 낮아 후순위 / 240 잔재 재발 시 abstract_source 태그로 혼재 감사.

## §paper-writer-2 catch 84 close (2026-07-14) — [[N]] 마커 형식 불일치: 상류(프롬프트) 표준화로 종결

한 줄: writer 가 [[N]] 복수 인용 형식을 자작(`[[1], [5]]` / `[[1], [[2]]` / `[[1].`),
파이프라인은 정본 `[[N]]` 전제 → shift/strip 오매핑 → 산출물 오염 + citation 측정 무효.
하류 정규식 4연패 후 **프롬프트 형식 명시(상류)**로 종결.

### 원인
- 프롬프트 `[citation 규칙]` 에 복수 인용·구두점·malformed 규정 부재 → writer 형식 자유해석.
  (예시 `(예: [[1]], [[2]])` 를 "쉼표로 묶어라"로 오해.)
- 하류 shift(`measure_paper.py:225`)·strip(`paper_section_writer.py:65`)·extract 전부 `\[\[(\d+)\]\]` 정본 전제.
  → 로컬 번호 묶음이 shift 안 됨 → 뒤 섹션 인용이 footer 오정렬(산출물 오염).

### ⚠️ 하류 정규식으로 고치지 말 것 (4연패 기록)
- `\[\[.*?\]\]`("rank_faithfulness.py:45 검증본")조차 malformed `[[N].`(단일 닫힘) 앞에서
  **over-match → 그 사이 prose 를 통째 삭제**(육안 확인 — run_before_H 에서 문장 소실).
- catch 84 시도 계보: (1)strict 미탐(catch 83) → (2)`[[a],[b]]` 오탐 → (3)변종 `[[a],[[b]]` 미탐
  → (4)`.*?` over-strip. **정규식은 사양(spec) 확정 후.**
- **정본은 프롬프트가 강제한다(상류).** 하류는 `\[\[(\d+)\]\]` 유지(원복 완료).

### 해결: prompts.py `[citation 규칙]` 명시
- 복수 = 독립 토큰 띄어 나열 `[[1]] [[2]] [[3]]`. 묶음·혼합·닫힘누락 금지(구체 예시 명시).
- 마커는 문장부호 앞. 각 마커 `[[` 열고 `]]` 닫기.
- 검증: 재생성 후 **육안 전수**(`[` 문자 전부 컨텍스트 덤프) → 정본 외 **0오염** 확인.

### ⭐ 파생 1 — §paper-writer-2 다양성 트랙 **전제 무효화**
- self-pool 앵커링 진단(EC/PF 0% = writer 가 자기 pool 무시)은 **shift 버그의 측정 아티팩트**였음.
  정상 shift 시 self-pool **구조적 100%**(writer 는 자기 섹션 로컬 refs 만 받고, "이전 섹션 번호
  재사용 금지" 프롬프트 명시 → 원리상 항상 ~100%). writer 는 줄곧 자기 pool 인용.
- → 앵커링(a) 문제 **부재**. 축약 설계(B-1/B-2) **폐기**(없는 병에 대한 처방).
- 오염 제거 후 실측 다양성(run_newbase/run_objstab): 고유 48~53 / 상위5 집중도 23~29% /
  미사용 40~46% = **양호**. (미사용은 retrieval 품질 별 트랙으로 이관.)

### ⭐ 파생 2 — objective 안정화 (신 트랙)
- objective→perceived 코어가 **무처방 시 flatten**(프롬프트 미세 변화에 붕괴: run_before_H 44 vs
  run_newbase 7). temp=0 단일점의 프롬프트 민감성.
- **objective 유지 지시 1줄이 유일 안정책** — H4-H6 매개 복원, objective 43 유지.
  산출물: `archive/run_objstab_20260714.md`(안정) vs `archive/run_newbase_20260714.md`(flatten 대조).
- **폐기 처방**: (A) 억압형(objective 43→18) / full abstract(44→8).
  ⚠️ **full abstract 는 rank 트랙 전용. writer 에 넣지 말 것**(생성 회귀 + Vertex 429 리스크).

### ⭐ 방법론 교훈 (반복 확인)
1. **정규식 4연패의 공통 원인 = writer 가 무엇을 쓰는지 모른 채 패턴 설계.**
   → 형태 전수 조사(육안) 먼저. 정규식은 사양 확정 뒤에.
2. **카운트 검증은 over-strip 을 못 잡는다. 육안이 잡았다.**
   (prose 삭제가 정규식 카운트에는 안 보임 — 잔여 브래킷 수만으론 통과.)
3. **하류에서 퍼내지 말고 상류에서 잠근다.**
   writer 는 표기 지시를 잘 따른다(번호 지시·마커 형식 모두 1회 성공).
4. **측정기가 고장 난 채로 처방을 비교하면 비교 결과가 전부 무효.**
   → 처방 실험 전에 측정기부터 검증할 것.

### 무효 / 유효 결론 구분
| 구분 | 결론 | 근거 |
|---|---|---|
| ❌ 무효 (citation 기반, shift 오염) | (A) 효과 +9 / 번호지시 다양성 20→28 / full abstract 28→25 / self-pool 전 수치 / 미사용률 69%·72% / 집중도 47→38→52% | shift 버그가 로컬 인용을 오매핑 → citation 지표 전부 신뢰 불가 |
| ✅ 유효 (prose 기반, 마커 무관) | objective: (A) 43→18 붕괴 / full 44→8 붕괴 / 짝 처방 44→67 강화 · 모형 구조 판정 전부 · H 구조 | 단어수·문면 기반, [[N]] shift 와 독립 |

### catch 85 (paper_section_writer.py:65 prev strip 묶음 미처리) — 상류 표준화로 자동 해소
- 원래 문제: strip 이 변종 마커 `[[a], [[b]]` 를 부분만 지워 previous_sections 에 잔해 누출.
- ⚠️ **별도 수정 불요.** 상류(프롬프트)가 정본 `[[N]]` 을 강제하므로 변종이 애초에 생성되지 않는다.
  → `:65` 의 원래 정규식 `\[\[\d+\]\]` 로 충분.
- ⚠️ **`:65` 를 `\[\[.*?\]\]` 로 "고치지 말 것"** — malformed `[[N].` 앞에서 over-match →
  prev 의 prose 문장을 통째로 삭제한다(육안 확인됨. run_before_H 에서 문장 소실).
- status: 상류 표준화에 흡수됨. 별도 트랙 불요.

### 배선 (커밋 대상)
- `prompts.py` — `[citation 규칙]` 마커 형식 명시 + `[작성 원칙]` 번호 지시 + objective 유지 지시.
- `agent/paper_section_writer.py` — WRITER_SEED **조건부** bind(측정 시 temp=0+seed, 미설정 시 프로덕션 temp=0.3 불변).
- 하류 정규식 5곳(`measure_paper:225`·`extract_pairs:38`·`chunk_summary:29`·`refs:357`·`paper_section_writer:65`) = `\[\[(\d+)\]\]` **원복 유지**(수정 금지).

**status: closed (2026-07-14)** — 마커 오염 상류 표준화로 종결, 다양성 트랙 전제 무효화, objective 안정화 신 트랙 개시.
re-entry: objective 안정 baseline(run_objstab) 확정 후 다음 품질축 / 미사용 retrieval 품질 별 트랙 / full abstract writer 주입 금지 재확인.

## §paper-writer-2 core_thesis 파라미터화 (2026-07-14) — 논문별 핵심 논지를 topics/*.env 로 주입

한 줄: objective 유지 지시의 trademark 특정 문안("objective vs perceived")을 `{core_thesis}`
placeholder 로 빼고 `topics/<slug>.env` 의 `CORE_THESIS` 로 주입. 하드코딩 부채 → 논문별 설정.

### 【1】 배선·검증
- `prompts.py` [작성 원칙]: `- 논지가 {core_thesis}의 대조 위에 서 있다면, 그 대조 구조를 …
  이미 세운 대조를 이어간다.` (input_variables 7→8).
- `topics/*.env`: `CORE_THESIS=objective(객관적) 유사성과 perceived(지각된) 유사성` (⚠️ "의 대조"
  제외 — template 이 담는다).
- `agent/paper_section_writer.py`: `write_paper_section(core_thesis="")` 시그니처+invoke, LangGraph
  래퍼 `state.get`. `measure_paper.py`·`diversity_rewrite.py`: `os.environ.get("CORE_THESIS", "")` 전달.
- config 로더 `core/config.py:130 _apply_topic_preset` 가 writer 경로에서 **이미 작동**(신 인프라 0).
- paper writer = **프로덕션 그래프 미배선**(연구 전용) → 파라미터화가 프로덕션에 안 번짐.
- ⭐ **검증 = 유료 0.** 치환 후 최종 렌더 문자열이 inline 커밋본과 **5섹션 byte-identical**(SHA-256
  대조, run_objstab 실제 입력 재구성). temp=0+seed 결정론(Phase 1-b 입증)상 출력 동일 보장 → 유료 런 불요.

### 【2】 ⭐ 발견 — 핵심어 반복이 효과 강도를 만든다
동일 개념 호명·동일 위치, "대조" 반복 횟수만 변경 → objective 안정화가 무너진다:
| 문안 | "대조" 횟수 | objective 단독 | 모형 | 산출물 |
|---|---|---|---|---|
| run_objstab (특정 inline) | 3회 | 43 | H4-H6 objective→perceived 매개 ✅ | run_objstab_20260714.md |
| run_paramz (초안2, 넓게) | 1회 | 15 | flatten ❌ | (지시대명사 2개 변경만으로 붕괴) |
| run_generic (범용 문안) | 0회 | 11 | flatten ❌ | Phase 3 |
| run_newbase (무처방) | — | 7 | flatten | run_newbase_20260714.md |

→ **반복은 수식이 아니라 부품이다.** 지시대명사 2개("그 대조 구조"→"그 구조", "이미 세운 대조"→
"이미 세운 것")만 바꿔도 objective 43→15, 매개 소실.
- 병기 교훈: **구체적이면 먹고 추상적이면 안 먹는다.** (번호 지시·마커 형식·objective 호명 = 구체 →
  성공 / (A) 억압형·"이론 모형 유지" 범용 = 추상 → 실패.) 이제 **+ 구체적 호명의 반복도 강도에 기여.**

### 【3】 ⚠️ 잔존 부채 — 대조형 논지 전용
- template 에 "대조"가 하드코딩됨. 비대조형 논문(매개형·통합형)에선 비문:
  `CORE_THESIS="A가 B를 매개하는 구조"` → "매개하는 구조**의 대조** 위에" ❌.
- 그때 template 문안을 조정해야 하는데, **문안 변경은 효과를 죽일 수 있다**(초안 2 전례: 지시대명사
  2개 변경으로 objective 43→15). → **반드시 검증 런을 돌릴 것.** "의미가 같으니 괜찮겠지" 금지.
- 부채는 줄었다(trademark 제거) 남았다("대조" 잔류). ⭐ **모르고 남기는 부채 ≠ 알고 남기는 부채.**
  이 노트가 그 차이다.

### 별 트랙 (catch 후보 등록)
- **topic 소스 이원화**: `measure_paper.py:434 --topic`(CLI, 기본값 "consumer behavior in influencer
  marketing" 광고 유물 footgun) ↔ `TOPIC_TITLE/QUERY`(env). topic 은 fetch query seed(:254)이기도
  하므로, env 통일 시 fetch query 변경 → pool 재생성·검증 필요(유료). core_thesis 와 분리 처리.

**status: closed (2026-07-14)** — core_thesis 파라미터화 커밋(byte-identical 검증, 유료 0). 대조형 전용 부채 명시.

## §paper-writer-2 catch 86 (2026-07-15) — writer 경로 temp=0.3 비결정론: 렌더 byte-identical 회귀검증 불성립

한 줄: writer LLM 은 `WRITER_SEED` 미설정 시 temp=0.3(비결정론)로 돌아, 산출물 SHA-256 대조는
코드 변경과 무관하게 오탐할 수 있다. topic-unify Phase 1 은 렌더 byte 대조 대신 **writer 입력 불변**
(SHA/git-stat) 정적 증명으로 회귀 0 을 세웠다.

### 원인
- `agent/paper_section_writer.py:73-78`: `WRITER_SEED` 설정 시에만 `temp=0+seed` bind, 미설정 시
  프로덕션 기본 `get_llm()` temp=0.3(비결정론) fallback.
- `archive/run_objstab_20260714.md` 도 seed 없이 생성 → 재생성본과 byte 대조 시 코드 무관 변동 발생 가능
  = SHA 불일치가 회귀 신호인지 seed 노이즈인지 분간 불가.

### 대체 검증 (topic-unify Phase 1 적용)
- 렌더 byte 대조 대신 **writer 입력 6종 불변** 정적 증명: topic 문자열(pool `d["topic"]` == 새 default
  SHA-256 일치)·pool chunks(mtime·git diff 불변, 재-fetch 0)·`prompts.py`·`paper_section_writer.py`·
  `web_search.py`(git diff 공백)·`CORE_THESIS`(env 불변). 입력 경로가 안 움직이면 산출 분포 불변 → 회귀 0.
- 이 방식은 실경험 SHA 대조보다 **견고**: seed 부재·temp=0.3 노이즈에 영향받지 않는다.

### ⚠️ 근원 — core_thesis 논법을 writer 에 복사 금지
- core_thesis 검증(temp=0+seed, 결정론 context)은 "입력 동일 → 출력 byte 동일" 이 성립.
- 일반 writer 경로(temp=0.3, seed 無)는 **"입력 불변 → 분포 불변"까지만** 성립(byte 동일 아님).
- temp 비대칭(core_thesis 검증 = seed 有 ↔ 기본 writer = seed 無)을 무시하고 byte-identical 논법을
  그대로 옮기면 오검증. writer 산출물 회귀 판정은 **입력 불변 정적 증명**으로 한다.

**status: noted (2026-07-15)** — topic-unify Phase 1 회귀검증 방법 확정(커밋 `82257557`, push 완료).
향후 writer 산출물 회귀는 seed 고정 없이는 byte 대조 금지, 입력 불변 증명 우선.
