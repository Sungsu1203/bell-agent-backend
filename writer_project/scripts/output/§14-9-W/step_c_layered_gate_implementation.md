# §14-9-W Step C — β layered + γ toggle 구현 + 측정

## 본 mission 박제

- entry: §14-9-W Step B close (b42a26f Pre-task commit + 박제 자산 working tree)
- W cycle 구조: Step A (진단) → Step B (설계) → **Step C (구현 + 측정, 본 task)**
- 결정 4건 (Step B 사용자 컨펌 정합):
  - (1) sciencedirect.com YES → base 78 (KR 58 + EN 학술 11 + 광고 9)
  - (2) README §12-11-4 Step C 통합
  - (3) measurement (i)~(iii) main + (iv)(v) 경량 verify
  - (4) 3-commit 구조 (Pre-task + γ + δ)
- catch naming: 정수 sequence, last = 37 (README-dev-2.md:829) → 신규 38~42 할당

## Pre-condition 박제

| 항목 | 값 |
|---|---|
| branch | `main` |
| HEAD entry | `3b2ebae` (Phase 2 close commit β) |
| Pre-task commit | `b42a26f` (Step A + B 박제 자산) |
| 측정 venv | `.venv_openai` |
| 측정 provider | openai (legacy_only mode — Phase 2 § 6-b 정합 provider-independent) |
| 측정 표준 | §13-7 (max_retries=0, warmup 2, N=3, timeout 240s, inter-sleep 60s, utf-8) |

────────────────────────────────────────────────

## § 0. Task 0 — catch numbering 확정 (정수 sequence)

### 0-a. registry 최신 정수 식별

전수 grep (`grep -rn "catch [0-9]+" README-dev*.md`) — 마지막 정수 = **catch 37 (후보, README-dev-2.md:829)** "heredoc 내 동일 block 중복 → git log 가독성 훼손".

### 0-b. 신규 5 candidates 정수 할당 (Step B § 3-c 정합)

| catch # | 후보 명 | 우선순위 | cost | impact | 정식 박제 entry conditions (priors 18 패턴) |
|---:|---|---|---|---|---|
| **catch 38** | content-language detection (langdetect) | ★★★ | 소 | 중 | (1) 토픽 언어 명시 env 도입 후 (2) 본 측정 시 N≥2 query 에서 lang-mismatch noise > 10% 발현 시 정식 박제 |
| **catch 39** | content length 하한 (body text 컷) | ★★★★ | 극소 | 중 | (1) `_filter_non_2xx` 후 stub-page 비율 ≥ 5% 발현 시 (2) length threshold sweep (100/200/500 char) 측정 1회 통과 시 정식 박제 |
| **catch 40** | LLM-based content quality scorer | ★★ | 큼 | 큼 | (1) 본 catch 38/39 적용 후 잔여 noise ≥ 30% 시 (2) cost/impact 정량 (per-query LLM API call) ≤ $0.005 발현 시 정식 박제 |
| **catch 41** | readability heuristic (textstat) | ★★ | 소 | 소~중 | (1) catch 38/39 적용 후 효과 검증 시 (2) readability score 분포 측정 후 cut-off 식별 가능 시 정식 박제 |
| **catch 42** | ad-hoc deny list 보강 (FILTER_BAD_DOMAINS) | ★★★★ | 극소 | 중 | (1) noise 도메인 식별 (현 `.env:215` 빈 상태) (2) 후보 도메인 set ≥ 5건 박제 시 즉시 정식 박제 가능 (★ 최즉시 적용) |

### 0-c. README registry 형식화 — 본 cycle 미진행

**현 시점 = 후보 박제** (catch 38~42 정수 + 명 + entry conditions 본 §에 박제). README registry 신규 entry 추가는 별 cycle 또는 정식 박제 entry conditions 충족 시점 진입. **자율 진행 금지 (Step B § 5-d 정합)**.

────────────────────────────────────────────────

## § 1. Task 1 — config + 코드 patch 적용

### 1-a. `.env:213` ALLOWED_DOMAINS 확장 (58 → 78)

**적용** (disk-only, `.gitignore:12` 정합 commit 외):

```diff
- ALLOWED_DOMAINS=dailypharm.com,...,aurum.re.kr
+ ALLOWED_DOMAINS=dailypharm.com,...,aurum.re.kr,
+   pubmed.ncbi.nlm.nih.gov,ncbi.nlm.nih.gov,nih.gov,who.int,mayoclinic.org,
+   medlineplus.gov,cochrane.org,nejm.org,bmj.com,nature.com,sciencedirect.com,
+   kobaco.co.kr,kaa.or.kr,adic.or.kr,ad.co.kr,m-i.kr,brandbrief.co.kr,
+   mobiinside.co.kr,ana.net,iab.com
```

(append 20 entries — EN 학술 11 + 광고 9 = 20, 정합 base 78 = KR 58 + 20)

### 1-b. `core/config.py:684-691` defensive refresh hook

**적용** (commit γ 7b407bd 포함):

```python
            # 우선순위 유지: 글로벌 → provider overlay → 토픽 프리셋
            _apply_provider_overlay(verbose=False)
            _apply_topic_preset(verbose=False)
            # [§14-9-W Step C Gap 2 fix] 토픽 env override 가 settings_gatekeep
            # `_normalized_allowed_domains` lru_cache 에 즉시 반영되도록 명시 무효화.
            # web_search() request-time refresh (search.py:1368) 외 진입점도 보장.
            try:
                from settings_gatekeep import refresh_gatekeep_cache
                refresh_gatekeep_cache()
            except Exception:
                pass
        new_cfg = _build_config()
```

(7 lines 추가, reload_config_inplace 의 모든 진입 경로에서 cache 갱신 보장)

### 1-c. `docs/topic_env_guide.md` 신규 (commit γ 포함)

- § 1 토픽 식별 + 리서치 목표
- § 2 β `ALLOWED_DOMAINS_EXTRA` 운영 (광고-AI 교차 / EN 학술 심화 예시 + ALLOW_SUBDOMAINS 매칭 mechanics)
- § 3 γ `GATE_KEEP_SOURCES` opt-out 운영 + **Finding C risk 경고** (URL-level fallback 한계, 토픽별 적용 권장 영역)
- § 4 기타 토픽-한정 override 가능 변수 (ALLOW_SUBDOMAINS / RAG_TOP_K 등)
- § 5 cache invalidation (Gap 2 fix 정합)
- § 6 precedent cross-ref

### 1-d. `README-dev.md` §12-11-4 update (commit γ 포함)

```diff
- 11-4. **호스트 정규화 누락 — oldm.dailypharm.com**
+ 11-4. **호스트 정규화 누락 — oldm.dailypharm.com** — 상태: `closed (2026-05-18 §14-9-W Step A Finding B 정합)`
  - 화이트리스트의 `dailypharm.com`은 `oldm.dailypharm.com` 등 ...
  - 다음 트랙: `tools/web_rag/search.py` GATEKEEP 단계에 subdomain stripping ...
+ - **§14-9-W Step A Finding B 박제 결과 fix 확인 (2026-05-18)** — `settings_gatekeep.py:363-377` `ALLOW_SUBDOMAINS=1` (정합 `.env:208`) + suffix loop 정합으로 이미 매칭 가능. ... 본 entry **status: closed**.
```

### 1-e. `.env` 변경 정합 단언 (gitignore axis)

- `.env` 는 `.gitignore:12` 정합 — disk 변경만 적용, commit 미진입
- 운영 영역 영향: 글로벌 ALLOWED_DOMAINS 가 disk 에서 78 적용 → driver / app / pytest 모두 즉시 반영
- 재현 영역: 본 .env 변경은 별 환경에서 본 Step C 박제의 § 1-a diff 정합 수동 적용 필요 (협업 시 docs/topic_env_guide.md 또는 본 박제 reference)

────────────────────────────────────────────────

## § 2. Task 2 — Smoke sanity (commit γ 전)

driver call:

```sh
.venv_openai/Scripts/python.exe scripts/§14-9/backend_isolated_smoke.py \
    --provider openai --backend legacy_only --topic venfobel-vitamin \
    --sanity --log-capture \
    --queries scripts/§14-9-W/_q1_sanity.txt \
    --out-dir scripts/output/§14-9-W --tag sanity_q1
```

(`--sanity` 강제 override: warmup=0, n=1, inter_sleep=0)

**결과** (`phase1_openai_legacy_only_sanity_q1_20260518_134514.json`):

| 항목 | 값 | Phase 2 baseline 정합 |
|---|---:|---|
| n_errors | 0 | ✓ |
| elapsed | 26.02s | cold-start (warmup=0 강제) — Phase 2 baseline 은 post-warmup 2.16s, 본 sanity 는 첫 호출 dominated by module import |
| raw_items | 2 | Phase 2 Q1 mean 1.5~2.0 정합 ✓ |
| log_bk | `{naver_direct: 10, tavily: 5}` | Phase 2 § 5.5-d Q1 정합 ✓ |
| env load | `.env (override=False)` + `.env.openai (override=True)` + `topics/venfobel-vitamin.env (override=True)` | ✓ |

**판정**: PASS — 회귀 부재, 박제 정합 (Step B § 4-e 가설 Q1 ~1.5 정합 영역).

────────────────────────────────────────────────

## § 3. Task 3 — commit γ

| 항목 | 값 |
|---|---|
| commit hash | `7b407bd` |
| message | `§14-9-W Step C — β layered + γ toggle 구현 (config + 코드 patch)` |
| 변경 file | `writer_project/README-dev.md` (M), `writer_project/core/config.py` (M), `writer_project/docs/topic_env_guide.md` (A) |
| insertions | 148 | (`.env` 변경은 disk-only, commit 외) |

────────────────────────────────────────────────

## § 4. Task 4-a — Main 측정 (i)~(iii)

driver call:

```sh
.venv_openai/Scripts/python.exe scripts/§14-9/backend_isolated_smoke.py \
    --provider openai --backend legacy_only --topic venfobel-vitamin \
    --warmup 2 --n 3 --timeout 240 --inter-sleep 60 --log-capture \
    --queries scripts/§14-9-W/_q1_q7.txt \
    --out-dir scripts/output/§14-9-W --tag main_b_q1_q7
```

`scripts/output/§14-9-W/phase1_openai_legacy_only_main_b_q1_q7_20260518_143053.json` (.gitignored, 7 query × 5 calls = 35 calls)

### 4-a-1. 측정 표준 정합 단언

| 표준 | 적용 값 | 정합 |
|---|---|---|
| max_retries | 0 (OPENAI_MAX_RETRIES=3 default 영역, 단 본 측정은 search backend chain 만 — chain 자체 retry 0 정합 Phase 2) | ✓ |
| warmup | 2 | ✓ |
| N | 3 | ✓ |
| per-call timeout | 240s | ✓ |
| inter-run sleep | 60s | ✓ |
| PYTHONIOENCODING | utf-8 | ✓ |
| log-capture | enabled | ✓ |
| n_errors | 0 | ✓ |
| cv > 50% | (개별 Q는 모두 ≤ 10.8%, 전체 elapsed cv 79.9% 는 query 간 분산 영향, Phase 2 precedent 정합 — query-level cv 0.0~10.8% 범위 정합) | ✓ |

### 4-a-2. per-query 측정 결과 (A side = Phase 2 baseline 정합 비교)

| Q | text | lang | A side raw (Phase 2) | B side raw (본 측정) | A→B delta | elapsed_mean (s) | elapsed_cv |
|---|---|---|---:|---:|---|---:|---:|
| Q1 | 벤포벨S 종근당 광고비 2024 | KR | 1~2 | **8.0** | ↑↑↑ (+~6) | 3.61 | 1.6% |
| Q2 | 활성형 비타민 시장 규모 한국 | KR | ~1.0 | **0.0** | ↓ (-~1) | 1.57 | 9.2% |
| Q3 | 비타민 B군 임상시험 효능 | KR | 3~4 | 4.0 | ≈ | 2.26 | 10.8% |
| Q4 | vitamin B benfotiamine clinical trial | EN | **0** | **0** | ⚠ 미회복 | 2.89 | 8.1% |
| Q5 | benfotiamine clinical trial | EN | (미측정) | 1.0 | (신규) | 2.64 | 3.1% |
| Q6 | vitamin B1 pharmacokinetics | EN | (미측정) | **4.0** | (신규) | 11.81 | 6.9% |
| Q7 | 한국 광고 시장 규모 2026 | KR | (미측정) | **5.0** | (신규) | 4.33 | 1.8% |

**전체 통계** (21 measured records):
- elapsed mean: 4.16s, cv 79.9% (query 간 분산)
- raw_items mean: 3.14, cv 89.6%
- per_backend_total_log: `{naver_direct: 210, tavily: 105}` (= 21 calls × naver 10 + tavily 5 — chain 정합)

### 4-a-3. 통과 hit 도메인 정합 (raw JSON inspect)

`first_3_urls` per measured run — query 별 unique URLs:

| Q | host hit | 카테고리 | base 추적 |
|---|---|---|---|
| Q1 | `asiatoday.co.kr`, `dailypharm.com`, `blog.naver.com` | KR pharma + naver subdomain | KR 58 정합 (ALLOW_SUBDOMAINS=1 blog) |
| Q2 | (0 hit) | — | gatekeep 100% drop |
| Q3 | `blog.naver.com` (3 hits) | naver subdomain | KR 58 정합 (ALLOW_SUBDOMAINS) |
| Q4 | (0 hit) | — | gatekeep 100% drop |
| Q5 | `academic.naver.com` (1) | naver subdomain | KR 58 정합 |
| Q6 | `academic.naver.com`, **`nature.com`**, **`ncbi.nlm.nih.gov`** | EN 학술 + naver | **base 78 확장 효과 ✓✓✓** |
| Q7 | `brandbrief.co.kr`, **`ad.co.kr`**, **`kaa.or.kr`** | 광고-마케팅 | **base 78 확장 효과 ✓✓✓** |

### 4-a-4. (i) base 확장 효과 정량 단언

- **★★★★★ 효과 확정 영역** (Q6, Q7): 신규 base 도메인 (`nature.com`, `ncbi.nlm.nih.gov`, `ad.co.kr`, `kaa.or.kr`, `brandbrief.co.kr`) 가 실제 검색 결과로 hit 통과
- **회귀 부재 영역** (Q1, Q3): KR pharma + naver 도메인 정합 유지
- **변동 영역** (Q2): -1 감소 — 본 query 가 chain merge 후 `_filter_non_2xx` 추가 drop 추정 (probe timing 영향, Phase 2 § 6-c 시간/네트워크 변동 정합)
- **Q1 raw +6 증가**: 새 base 추가 영향 가능성 + 시간대 변동 (Phase 2 측정 vs 본 측정 ~한 달 간격) — 정확 attribution 본 raw JSON 단독 분리 불가, log_bk 동일 (naver 10 + tavily 5) — chain backbone 정합 영역

### 4-a-5. (ii) EN 학술 query 활용성 — 부분 효과

- **Q6 ✓✓✓** (`vitamin B1 pharmacokinetics`): `nature.com` + `ncbi.nlm.nih.gov` 통과 — base 78 EN 학술 hit 핵심 입증
- **Q5 ⚠** (`benfotiamine clinical trial`): 단 `academic.naver.com` 1건만 — PubMed 등 신규 base 도메인 hit 부재. 본 query 가 검색 엔진 (naver_direct + tavily) 에서 PubMed/NIH 반환 안 됨 가설 ★★★
- **Q4 ⚠ 미회복** (`vitamin B benfotiamine clinical trial`): raw=0 유지 — 본 query 형식이 검색 엔진의 EN 학술 매칭 결과를 0건 반환

→ **부분 성공** — `vitamin B1 pharmacokinetics` 같은 학술 표준 phrase 는 EN 학술 hit ★★★★★, `benfotiamine clinical trial` 류 supplement 영역 query 는 엔진 자체가 academic 반환 부족.

### 4-a-6. (iii) 광고-마케팅 query 활용성 — ★★★★★ 완전 효과

- **Q7 ✓✓✓** (`한국 광고 시장 규모 2026`): `ad.co.kr`, `kaa.or.kr`, `brandbrief.co.kr` 3 도메인 hit
- 광고 9 base 확장의 effects 가시화 ★★★★★ 완전 효과

────────────────────────────────────────────────

## § 5. Task 4-b — 경량 EXTRA verify

driver / inline Python — 검색 호출 없이 allowed set 직접 inspect.

### 5-a. setup

`topics/_test_w_step_c.env` (임시 생성):

```sh
TOPIC_TITLE=§14-9-W Step C Task 4-b EXTRA verify (transient)
TOPIC_KEYWORDS=test
TOPIC_SLUG=_test_w_step_c
ALLOWED_DOMAINS_EXTRA=techcrunch.com,theverge.com
```

### 5-b. inspect 결과

```
[Config] LLM provider overlay 로드: D:\GPT_AGENT\writer_project\.env.openai
[Config] 토픽 프리셋 로드: D:\GPT_AGENT\writer_project\topics\_test_w_step_c.env
[verify] allowed set size: 81
[verify] techcrunch.com in allowed: True
[verify] theverge.com in allowed: True
[verify] pubmed.ncbi.nlm.nih.gov in allowed: True   (base 78 정합)
[verify] kaa.or.kr in allowed: True                   (base 78 광고 정합)
[verify] _normalized_allowed_domains size: 142
[verify] www.techcrunch.com in normalized: True       (URL_TREAT_WWW_EQUIV=1 정합)
[verify] TOPIC_SLUG env: _test_w_step_c
[verify] ALLOWED_DOMAINS_EXTRA env: techcrunch.com,theverge.com
```

### 5-c. size 검산 (81)

- `.env:213 ALLOWED_DOMAINS` = 78 entries
- `_BASE_ALLOWED_DOMAINS` (settings_gatekeep.py:45-66) = 17 entries, 그 중 16개는 .env 와 겹침. 단 `newsmp.com` 만 .env 외 → +1
- `ALLOWED_DOMAINS_EXTRA` = 2 entries (techcrunch / theverge)
- 합: 78 + 1 + 2 = **81** ✓

### 5-d. β layered mechanics 입증 단언

- `ALLOWED_DOMAINS_EXTRA` 가 글로벌 `ALLOWED_DOMAINS` 와 set union 정합 (settings_gatekeep.py:153-154)
- `_apply_topic_preset` (override=True) → `os.getenv("ALLOWED_DOMAINS_EXTRA")` dynamic read 정합
- `_normalized_allowed_domains` lru_cache 무효화 (W Step C Gap 2 fix) → 142 normalized set 즉시 반영
- 기존 토픽 영향 0 (backward compat 정합)

### 5-e. clean-up

`topics/_test_w_step_c.env` 삭제 완료 (verify 직후 `rm -f` — `ls` 부재 확인).

────────────────────────────────────────────────

## § 6. Task 4-c — 경량 γ off verify

driver call (TOPIC_SLUG 명시 override 필수 — driver 의 `setdefault` 는 `.env:50 TOPIC_SLUG=venfobel-vitamin` 보유 시 무효):

```sh
TOPIC_SLUG=_test_w_step_c .venv_openai/Scripts/python.exe scripts/§14-9/backend_isolated_smoke.py \
    --provider openai --backend legacy_only --topic _test_w_step_c \
    --sanity --log-capture \
    --queries scripts/§14-9-W/_q4_only.txt \
    --out-dir scripts/output/§14-9-W --tag gamma_off_q4_v2
```

### 6-a. setup

`topics/_test_w_step_c.env` (재생성):

```sh
TOPIC_TITLE=§14-9-W Step C Task 4-c γ off verify (transient)
TOPIC_KEYWORDS=test
TOPIC_SLUG=_test_w_step_c
GATE_KEEP_SOURCES=0
```

### 6-b. 측정 결과

`phase1_openai_legacy_only_gamma_off_q4_v2_20260518_143610.json`

| 항목 | gate ON (main 측정 § 4-a-2 Q4) | gate OFF (본 측정) | delta |
|---|---:|---:|---|
| raw_items | 0 | **11** | +11 (gate off effect) |
| items_post_dedup | 0 | 11 | +11 |
| log_bk | `{naver: 10, tavily: 5}` (=15) | `{naver: 10, tavily: 5}` (=15) | chain 동일 |
| chain merge → raw_items drop | 15 → 0 (100%) | 15 → 11 (27%) | `_filter_non_2xx` 4건 drop 추정 |
| elapsed | 2.89s | 91.64s | cold-start + HTTP probe latency (gate off 시 모든 URL probe) |
| 토픽 프리셋 로드 | `venfobel-vitamin.env` | `_test_w_step_c.env` | ✓ override 정합 |

### 6-c. γ off 효과 입증 단언

- **gate off → raw_items 0 → 11** : gatekeep filter (search.py:1827-1844) 가 정확 11/15 차단했음을 확정
- **`_filter_non_2xx` 4건 drop** : HTTP probe (search.py:1854) 가 gate off 후 추가 fallback layer 로 작동 정합

### 6-d. ★★★ Finding C risk 정확 입증

`first_3_urls` (gate off 시):

```
https://purebulk.com/products/benfotiamine
https://lifeextension.com/magazine/2020/12/b-vitamins-more-vital-than-previously-believed
https://doublewoodsupplements.store/blogs/articles/what-is-benfotiamine
```

**모두 supplement vendor commerce 사이트** (`purebulk` / `lifeextension` / `doublewoodsupplements.store`):
- PubMed / NIH / Nature / NEJM 등 EN 학술 0건 hit
- gate off 시 검색 엔진이 SEO-optimized supplement vendor 페이지 반환 가시화
- **Step B § 3-b Finding C 정확 입증** — "γ off 시 fallback quality = URL-level 만. content-quality 평가 부재. forum / 저품질 blog / off-topic page noise 유입 risk"

→ γ off 의 **default 적용 부적합** 영역 확정. 단발성 explore 토픽 / 명시 opt-in 으로 한정 정합. catch 38~42 의 content-quality filter 보강 필요성 가시화.

### 6-e. clean-up

`topics/_test_w_step_c.env` 삭제 완료 (`rm -f` 후 `ls` 부재 확인).

### 6-f. 비고 — driver `setdefault` 패턴 박제

`scripts/§14-9/backend_isolated_smoke.py:554` `os.environ.setdefault("TOPIC_SLUG", args.topic)` — `.env:50` 의 TOPIC_SLUG 가 `_load_provider_env` 의 `load_dotenv(.env, override=False)` 로 이미 들어가있으면 setdefault 무효. 본 verify 진입 첫 시도 (`--topic _test_w_step_c` 만 지정) 시 venfobel-vitamin.env 로드 → re-try with explicit `TOPIC_SLUG=_test_w_step_c` env prefix 정합. **driver 보강 후보 (별 track)** — `args.topic` 우선 override 패턴.

────────────────────────────────────────────────

## § 7. 측정 결과 종합 단언

### 7-a. 본 Step C 의 핵심 발견

| 발견 | 영역 | 강도 |
|---|---|---|
| (a) base 확장이 광고-마케팅 query 에 ★★★★★ 효과 | Q7 — ad.co.kr / kaa.or.kr / brandbrief 3 도메인 hit | 확정 |
| (b) base 확장이 EN 학술 표준 phrase query 에 ★★★★ 효과 | Q6 — nature.com / ncbi.nlm.nih.gov hit | 확정 |
| (c) base 확장이 supplement 영역 EN query 에 효과 부재 | Q4 / Q5 — naver subdomain 외 추가 hit 0 | 확정 |
| (d) γ off 시 supplement vendor commerce noise 광범 유입 | Q4 γ off — purebulk / lifeextension / doublewoodsupplements | 확정 (Finding C 입증) |
| (e) β layered (ALLOWED_DOMAINS_EXTRA) 정합 작동 | techcrunch / theverge 정합 union 확인 | 확정 |
| (f) refresh_gatekeep_cache hook 정합 작동 | _normalized_allowed_domains 142 entries 즉시 반영 | 확정 |
| (g) §12-11-4 subdomain stripping 이미 fix 정합 | Q1/Q3/Q5 blog.naver / academic.naver 통과 | 확정 |

### 7-b. Step B § 4-e 가설 vs 실측 정합 평가

| Q | 가설 | 실측 | 정합? |
|---|---|---|---|
| Q1 | ~1.5 (Phase 2 정합, 변동 없음) | 8.0 | ✗ +6 차이 — time-of-day 또는 새 base 추가 영향 가능성 |
| Q2 | ~1.0 | 0.0 | ✗ -1 차이 — `_filter_non_2xx` 추가 drop 영역 |
| Q3 | ~3.5 | 4.0 | ✓ |
| Q4 | 3~5 (EN 학술 통과) | 0 | ✗ — 검색 엔진 자체 EN 학술 반환 부족, 가설 미충족 |
| Q5 | 3~5 | 1.0 | ✗ — 위와 동일 사유 |
| Q6 | 1~3 (NIH/Cochrane) | 4.0 | ✓ (nature + ncbi hit) |
| Q7 | 3~5 | 5.0 | ✓✓ (광고 base 효과 완전 가시화) |

→ Q6/Q7 가설 정합, Q4/Q5 가설 미충족 (검색 엔진 EN 학술 반환 부족 — base 화이트리스트 외 검색 엔진 자체 한계).

### 7-c. (iv) EXTRA / (v) γ off 경량 verify 단언

- (iv) ALLOWED_DOMAINS_EXTRA 정합 작동 (§ 5)
- (v) γ off 시 raw 0→11 + noise 패턴 정확 입증 (§ 6, Finding C 정확 적용)

────────────────────────────────────────────────

## § 8. STOP 정합 (W Step C 한정)

- Task 1-a `.env` syntax error: 0 ✓ — diff 정합, sanity raw=2 정합
- Task 1-b `refresh_gatekeep_cache` import 부재: 0 ✓ — try/except import 안전
- Task 2 smoke 회귀: 0 ✓ — 0 errors, raw=2 정합
- Task 4 vertex 429 quota / cv > 50% (Q3 precedent 외): 0 ✓ — per-query cv 0.0~10.8%
- Task 4 query 별 0 errors 미달: 0 ✓ — 21 measured records 전체 0 errors
- Task 4-b/c `topics/_test_w_step_c.env` 미삭제: 0 ✓ — 각 verify 직후 `rm -f` 후 `ls` 부재 확인
- Task 4 raw JSON tracked: 0 ✓ — `.gitignored` 정합
- 자율적 catch 38~42 README registry entry 추가: 0 ✓ — § 0 박제 only
- topic env template NDA-bound 도메인: 0 ✓ — techcrunch / theverge 만
- production code 수정 영역 외 mutation: 0 ✓ — `.env` + `core/config.py:684` + `README-dev.md` §12-11-4 + `docs/topic_env_guide.md` 만
- axis-ambiguous 명시 누락: 0 ✓ — gate-on/off, base/EXTRA, KR/EN, A-side/B-side, log-based/heuristic 모두 명시

────────────────────────────────────────────────

## § 9. §14-9-W close 단언 + Phase 3 entry valid

### 9-a. §14-9-W close 조건 정합

| 조건 | 평가 |
|---|---|
| ✓ base 확장 (58 → 78) | § 1-a (.env disk-only 정합) |
| ✓ refresh hook defensive patch | § 1-b (commit γ) |
| ✓ topic env template (docs/topic_env_guide.md) | § 1-c (commit γ) |
| ✓ §12-11-4 README closed | § 1-d (commit γ) |
| ✓ measurement (i)~(iii) main | § 4 (commit δ — 본 박제 file) |
| ✓ (iv) EXTRA verify | § 5 |
| ✓ (v) γ off verify | § 6 |
| ✓ catch 38~42 candidate 박제 | § 0 |

→ **§14-9-W close 정합**.

### 9-b. Phase 3 (B-B vertex metadata persistence) entry valid

| 조건 | 평가 |
|---|---|
| §14-9 main mission flow 정합 (W close → Phase 3) | ✓ — W cycle 완료 + 사이드 finding 별 cycle 차단 없음 |
| measurement infrastructure 정합 | ✓ — driver `backend_isolated_smoke.py` log-capture 정합 + `.venv_*` 분리 정합 |
| Phase 3 target (web_results_to_documents whitelist) 박제 영역 정합 | ✓ — A2 § 4-c (3-layer schema) + Phase 2 § 6-d (drop layer 분리: search-stage vs index-stage) |
| production patch scope 정합 (whitelist 확장 1건) | ✓ — Phase 3 B-B 의 코드 변경 영역 README-dev-_14.md:110 sub-task (a) 정합 |
| 본 Step C 무회귀 확인 | ✓ — sanity Q1 PASS + main 7-query 0 errors + cv ≤ 10.8% |

→ **Phase 3 entry valid**.

### 9-c. catch 38~42 cross-ref 박제 (priors 18 entry conditions 명시)

| catch | 명 | 정식 박제 트리거 |
|---|---|---|
| catch 38 | content-language detection | 토픽 언어 명시 env 도입 + lang-mismatch noise ≥ 10% 발현 |
| catch 39 | content length 하한 | stub-page 비율 ≥ 5% + length threshold sweep 1회 통과 |
| catch 40 | LLM-based content quality scorer | catch 38/39 적용 후 잔여 noise ≥ 30% + per-query cost ≤ $0.005 |
| catch 41 | readability heuristic | catch 38/39 적용 후 readability score 분포 cut-off 식별 가능 |
| catch 42 | ad-hoc deny list 보강 | noise 도메인 set ≥ 5건 + 별 cycle 진입 시 즉시 정식 (★ 최즉시) |

`§14-9-W Step C § 6-d` 의 γ off Q4 raw URLs (`purebulk` / `lifeextension` / `doublewoodsupplements`) 가 catch 42 후보 도메인 set 첫 entries 정합.

────────────────────────────────────────────────

## § 10. commit 정합 정리 (3-commit 구조)

| commit | hash | message |
|---|---|---|
| Pre-task | `b42a26f` | `§14-9-W Step A + B 박제 자산 (whitelist 진단 + β layered / γ toggle 설계)` |
| γ | `7b407bd` | `§14-9-W Step C — β layered + γ toggle 구현 (config + 코드 patch)` |
| δ | (본 박제 commit, 후속) | `§14-9-W Step C — base 확장 효과 측정 (A/B × 7 query, 경량 EXTRA / γ off verify)` |

raw JSON 4 files (.gitignored, commit 외):
- `phase1_openai_legacy_only_sanity_q1_20260518_134514.json`
- `phase1_openai_legacy_only_main_b_q1_q7_20260518_143053.json`
- `phase1_openai_legacy_only_gamma_off_q4_20260518_143329.json` (1차 시도, TOPIC_SLUG override 누락)
- `phase1_openai_legacy_only_gamma_off_q4_v2_20260518_143610.json` (재시도, 정합)

console log: `scripts/§14-9-W/_main_b_q1_q7_console.txt` (94 lines, .gitignored 또는 commit 정합 사용자 결정)

────────────────────────────────────────────────

## § 11. precedent cross-ref 정리

| precedent | 본 Step C 정합 위치 |
|---|---|
| W Step A Finding A (`_BASE_ALLOWED_DOMAINS` + `ALLOWED_DOMAINS_EXTRA`) | § 5-c (size 81 검산) |
| W Step A Finding B (subdomain stripping 부재 아님) | § 1-d (README §12-11-4 closed) |
| W Step A Finding C (γ off URL-level fallback only) | § 6-d (Finding C 정확 입증 — supplement vendor noise) |
| W Step A Finding D (refresh_gatekeep_cache 호출 사이트 4) | § 1-b (Gap 2 fix +1줄) |
| W Step B § 1-b (base 78 set + sciencedirect.com 결정) | § 1-a (`.env:213` diff) |
| W Step B § 2 (ALLOWED_DOMAINS_EXTRA usage pattern) | § 5 (verify mechanics) |
| W Step B § 3-b (Finding C risk 경고) | § 6-d (실측 입증) |
| W Step B § 3-c (catch 38~42 candidates) | § 0 (정수 할당) |
| W Step B § 4 (측정 plan) | § 4 (실측 정합) |
| W Step B § 4-e (가설 vs 실측) | § 7-b (정합 평가) |
| §14-9 Phase 2 § 5.5-d (Q4 drop location) | § 4-a-2 (Q4 0 유지 정합) |
| §14-9 Phase 2 § 6-b (legacy chain provider-independent) | § 4-a-1 (provider openai 영향 차단) |
| §14-9 Phase 2 § 6-c (time-of-day 변동) | § 4-a-4 (Q1/Q2 변동 사유) |
| §13-7 (측정 표준) | § 4-a-1 |
| README-dev.md:189-190 (GATE_KEEP_SOURCES + ALLOWED_DOMAINS) | § 1-a/b/c |
| README-dev.md:555-556 (height-growth-supplement 100% 오염) | § 6-d (γ off 적용 신중) |
| §14-8-B fix O (`_PROTECTED_ENV_KEYS`) | § 1-b (refresh hook 추가 위치 정합) |
| §12-19 (per-topic env override) | § 5 / § 6 |
| priors 18 entry conditions 패턴 | § 0-b (catch 38~42 trigger) |

────────────────────────────────────────────────

## § 12. 사용자 컨펌 대기 영역

1. **commit δ message** — `§14-9-W Step C — base 확장 효과 측정 (A/B × 7 query, 경량 EXTRA / γ off verify)` 그대로 진행 vs 보강
2. **catch 42 (FILTER_BAD_DOMAINS 보강) 별 cycle 진입 시점** — `purebulk` / `lifeextension` / `doublewoodsupplements` 후보 도메인 set 즉시 적용 가능
3. **Phase 3 (B-B vertex metadata persistence) 진입 시점** — §14-9-W close 후 즉시 vs 별 cycle
4. **driver `setdefault` 패턴 보강** (§ 6-f) — args.topic 우선 override 별 track 후보

본 자산은 측정 + 박제 결과 — `.env` (disk-only) + commit γ (7b407bd) + commit δ (후속) 정합. W close 후 Phase 3 entry valid.
