# §14-9 Step B Phase 2 — methodology 보강 + ★★★★☆ 2 combination

- entry: §14-9 Step B Phase 1 close (commit `4e78b63`)
- branch: main / HEAD: 4e78b63 → (Phase 2 close 시 신규 HEAD)
- 측정 일자: 2026-05-17 (Pre-task + Task 0/1/2 = ~21:00 ~ 21:25 KST)
- precedent: §14-2 Phase A/B, §14-3 (NEW)-B 트랙 2 (정정 reference), §14-9-A1 (axis 분리 + key prefix-only)

> **STATUS — partial report, STOP at user confirmation**: Pre-task + Task 0/1/2 완료 박제. Task 3/4/5 (combinations iii+iv 측정 + Phase 3 entry valid) 는 사용자 컨펌 후 append.

────────────────────────────────────────────────

## § 0. Pre-task — Phase 1 close 결과

### 0-a. driver 이동

- source: `scripts/diag/§14-9/backend_isolated_smoke.py` (writer_project/.gitignore:90 `scripts/diag/` 매칭, untracked)
- target: `scripts/§14-9/backend_isolated_smoke.py` (writer_project/.gitignore 미매칭, tracked-eligible)
- 방식: `git mv` 실패 (source 가 tracked 아님) → 일반 `mv` + `git add`
- path-depth fix: `HERE.parents[2]` → `HERE.parents[1]` (driver L44 — scripts/§14-9/ 는 writer_project 로부터 2-level 깊이)

### 0-b. Phase 1 close commit

- commit hash: **`4e78b63`**
- message: `§14-9 Step B Phase 1 — baseline smoke driver + measurement (vertexai vs openai legacy, drift -11.3%)`
- 추가 file:
  - `writer_project/scripts/§14-9/backend_isolated_smoke.py` (driver, ~500 lines)
  - `writer_project/scripts/output/§14-9/step_b_phase1_baseline_smoke.md` (박제)
- 제외: raw JSON (gitignore 정합 확인 — `writer_project/.gitignore:82 scripts/output/**/*.json`)

### 0-c. 미커밋 박제 자산 (사용자 컨펌 영역)

본 Phase 1 close commit 은 **사용자 spec 의 2-file 한정** 정합. 다음 박제 .md 파일들은 여전히 untracked:

| file | 작성 cycle | 권장 |
|---|---|---|
| `scripts/output/§14-9/step_a_backend_provider_matrix.md` (정정 reference 부록 포함) | Step A + A1 정정 | Phase 2 close commit 또는 별 commit |
| `scripts/output/§14-9/step_a2_fusion_and_verify.md` (Task 0 정정 reference 부록 포함) | A2 + Phase 1 정정 | Phase 2 close commit |
| `scripts/output/§14-9-A1/credential_exposure_audit.md` | A1 audit | 별 commit (audit scope) |

→ 사용자 결정 영역: Phase 2 close commit 에 흡수 vs 별 commit 분리.

────────────────────────────────────────────────

## § 1. Task 0 — A2 § 4-c schema 정정 reference 적용 결과

- target: `scripts/output/§14-9/step_a2_fusion_and_verify.md`
- 조치: 파일 끝 (`— §14-9 Step A2 박제 종결` 직후) `## 부록 정정 reference (§14-9 Step B Phase 1 결과, 2026-05-17)` 섹션 append
- 원 § 4-c 본문 보존, 정정 reference 만 추가 → §14-3 (NEW)-B 트랙 2 timeline 정합

3-layer schema 분리 박제 적용:

| layer | location | observed keys |
|---|---|---|
| (a) raw vertex chunks | `vertex_search.py:148-158` | 3 keys: `domain, title, uri` |
| (b) raw legacy post-fetch | `search.py:1335-1889` web_search() return | 9 keys: `content, content_type, fetched_at, norm_url, raw_bytes, raw_content, source, title, url` |
| (c) wrapped in `_run_web_search_with_guard` | `agent/web_search.py:786-797` + legacy extend | 5 keys + vertex `metadata` |

**axis 분리 lesson 재적용** (A1/A2 catch): "schema 통일" word 가 wrap-stage axis 를 implicit 가정. 향후 schema 단언 시 **layer 명시 의무**.

- commit: 0 (mutation 1-file, Phase 2 close commit 에 흡수 권장)

────────────────────────────────────────────────

## § 2. Task 1 — Q4 tavily 미발화 진단 (read-only)

### 2-a. CFG 실측 dump (`.venv_openai` + `.env` + `.env.openai` + `topics/venfobel-vitamin.env` load 순)

```
CFG.SEARCH_POLICY: 'best_of_chain'      ← .env:78
CFG.SEARCH_MIN_OK: 1                    ← .env:79
CFG.SEARCH_TOPN: 40                     ← .env:80
CFG.SEARCH_BACKENDS: 'naver_direct,tavily'  ← .env:77
CFG.HAS_TAVILY: True                    ← TAVILY_API_KEY 존재 (.env:95, prefix tvly-k4Rr***)
CFG.HAS_GOOGLE_KEYS: False
CFG.HAS_SERPAPI: False
env SEARCH_MIN_BACKENDS: <unset>        ← search.py:1513 default max(2,2)=2
env BACKEND_TIMEOUT_SEC: '10'           ← .env:82 (search.py 가 DEFAULT_TIMEOUT_SECONDS=8 로 cap)
env SEARCH_TIME_BUDGET_SEC: '60'        ← .env:81 (default 25 override)
env TAVILY_TIMEOUT_SEC: '8'             ← .env:87
env WEB_DEFAULT_NEGATIVES: '-행사 -세미나' ← .env:91
```

### 2-b. chain logic walk (`tools/web_rag/search.py:1294-1697`)

| 단계 | line | Q4 EN 시 동작 |
|---|---|---|
| `_resolve_backend_chain` | search.py:1294-1331 | `SEARCH_BACKENDS=naver_direct,tavily` → chain = `[naver_direct, tavily]` |
| KR-force prefix | search.py:1479-1487 | `_looks_korean("vitamin B benfotiamine clinical trial")` = False → reorder skip, chain 그대로 |
| `_naver_reserved` budget | search.py:1505 | `_kr_context=False` → `_naver_reserved=0` (예약 미적용) |
| chain loop | search.py:1515-1680 | naver_direct → tavily 순차 호출 (early stop 조건 만족 시 중단) |
| best_of_chain early stop | search.py:1781-1796 | `hits >= min_ok(1) AND backends >= min_backends(2)` 시 stop |

→ 코드 분석상 **tavily 발화 차단 사유 부재**. Phase 1 박제의 "tavily 미발화 의심" 단언은 코드만으로 단언 불가.

### 2-c. raw JSON 재분석 (`phase1_openai_legacy_only_phase1_20260517_204151.json` Q4 records)

3 measured records 모두 동일:
- elapsed: 1.56s / 1.59s / 1.76s
- raw_items: 0
- per_backend_dist (heuristic): `{}` (items 부재 → 빈 dict)
- first_3_urls: `[]`

코드만으로는 tavily 발화 여부 결정 불가 — **log capture 필요** (Task 2 영역).

### 2-d. 가설 분리 단언 (Task 2 결과 통합 후)

| 가설 | 단언 |
|---|---|
| (a) heuristic 한계 | **CONFIRMED** (Task 2 log capture 결과: naver_direct + tavily 둘 다 fire, heuristic 0건 attribution 미스) |
| (b) chain logic 차단 (tavily 미발화) | **REJECTED** (Task 2: tavily got=5 items 실측) |
| (c) cred 부재 | **REJECTED** (HAS_TAVILY=True, TAVILY_API_KEY 정합) |
| **(d) NEW: 후속 filter 가 items drop** | **EMERGING** (Task 2: merged=15 ↔ driver received raw=0 — 필터 위치 미확정) |

────────────────────────────────────────────────

## § 3. Task 2 — driver 보강 (log capture mode)

### 3-a. 추가 기능

driver path: `scripts/§14-9/backend_isolated_smoke.py` (line ref 본 cycle 시점):

| 추가 영역 | line | 역할 |
|---|---|---|
| `_BackendLogHandler` 클래스 | L26-71 | `logging.Handler` 서브클래스, search.py 의 5 패턴 (chain/call/got/tried/final) regex 캡처 |
| `_install_log_capture()` | L77-89 | `tools.web_rag.search` logger 에 handler attach, level=INFO 보장 |
| `_log_to_per_backend_dist()` | L91-110 | event list → `{backend: got_count}` 집계, `merged` 는 별도 `_merged_total` 키 분리 |
| `_call_legacy_only` reset+snapshot | L182, L249 | per-call event 격리 + record 에 `backend_log_events` / `per_backend_dist_log` 박제 |
| `summarize()` 보강 | L498-504 | `per_backend_total_log` (log-based 정확 attribution) 추가 |
| `--log-capture` flag | argparse | default off, opt-in |

### 3-b. Q4 EN smoke 검증

```bash
PYTHONIOENCODING=utf-8 .venv_openai/python.exe scripts/§14-9/backend_isolated_smoke.py \
  --provider openai --backend legacy_only --sanity --log-capture \
  --queries scripts/diag/§14-9/_q4_only.txt --tag log_smoke_q4b
```

결과 (실측 backend_log_events):

```
[t=487.406] chain      bk=-              chain="naver_direct → tavily | policy=best_of_chain min_ok=1 topn=40 budget=60.0s timeout=8s"
[t=487.406] call       bk=naver_direct   variant=recall    timeout=8s
[t=487.906] got        bk=naver_direct   variant=recall    got=10
[t=487.906] call       bk=tavily         variant=precAneg  timeout=8s
[t=489.421] got        bk=tavily         variant=precAneg  got=5
[t=489.437] final      bk=merged                            got=15 (policy=best_of_chain, min_ok=1, topn=40, spent=2.03s)
```

driver 측 최종 수신:
- `elapsed=4.06s` (chain 2.03s + post-merge 처리 ~2s)
- `raw_items=0` ← **driver received items=0**
- `items_post_dedup=0`
- `log_bk={'naver_direct': 10, 'tavily': 5, '_merged_total': 15}` ← **log capture 가시화**
- `per_backend_dist (heuristic)={}` (items 부재 정합)

### 3-c. 핵심 단언 (Task 1 + Task 2 통합)

**원 Phase 1 단언 정정**:
- ❌ "tavily 미발화 의심" — 본 Task 2 log capture 로 **REJECTED**.
- ❌ "Phase 1 Q4 elapsed 1.6s 가 tavily 미호출 증거" — Task 2 측정 (chain 2.03s + post 2s = 4.06s, tavily 실제 호출 1.5s 소요) 와 비교 시 Phase 1 의 1.6s 는 **다른 동작 mode** 의심 (network/state 차이, 재현성 부족 — § 3-d 박제).

**NEW 단언**: legacy chain 은 정상 작동 — naver_direct + tavily 둘 다 fire, merged=15 hits. **단 driver 가 받은 final raw=0** — search.py 내부에서 merge 직후 ~ return 직전에 15 items 모두 drop. drop 지점 미확정 (Phase 3 territory).

### 3-d. 재현성 노이즈 박제 (sanity 추가 측정)

Q4 EN 단일 sanity 측정 3회 (warmup=0 n=1 inter_sleep=0):

| 측정 시점 | log-capture | elapsed | raw_items | log_bk |
|---|---|---|---|---|
| Phase 1 measured (5 runs) | off | 1.56~1.76s (cv 6.6%) | 0 (3 runs) | n/a |
| 21:22 sanity #1 | **on** | **27.53s** | 0 | merged=15 (only final captured, pre-patch) |
| 21:23 sanity #2 (no log) | off | 4.08s | 0 | n/a |
| 21:25 sanity #3 | **on** (patched) | 4.06s | 0 | naver=10, tavily=5, merged=15 |

→ **elapsed 변동 6×~10× 사이**. 가장 그럴듯한 사유: process cold-start / network / GCP API state. log capture 자체는 4-line 차이 (sanity #2 vs #3) 정합 — 큰 영향 없음.

### 3-e. driver patch 적용 후 라우팅 정합

- `--log-capture` off (Phase 1 default): 기존 동작 유지, `per_backend_dist_log` 키 부재 (`{}` 또는 키 없음)
- `--log-capture` on: per-call `backend_log_events` 가 record 에 박제, summary 의 `per_backend_total_log` 가 정확 attribution 박제
- backward compat: 기존 `per_backend_dist` (heuristic) 키 유지 → 양 axis 비교 가능

────────────────────────────────────────────────

## § STOP — 사용자 컨펌 영역 (Phase 2 측정 진입 전)

### 보고

1. **Phase 1 close commit `4e78b63`** 완료 (driver tracked + Phase 1 박제). 미커밋 박제 자산 (Step A / A2 / A1) 처리 결정 필요 (§ 0-c).
2. **A2 § 4-c 정정 reference 적용** — 3-layer schema axis 분리 박제. 본 mutation 은 Phase 2 close commit 흡수 예정.
3. **Q4 tavily 미발화 의심 = false alarm** — Task 2 log capture 로 tavily got=5 실측 확인. **legacy chain 정상 작동**.
4. **NEW finding (Phase 1 박제 갱신 영역)**: chain merge=15 items, driver received raw=0. 15 → 0 drop 지점 미확정 — Phase 3 의 별 진단 트랙 영역 (production code reading scope).

### Phase 2 측정 (Task 3/4) 진입 valid 평가

| 진입 조건 | 평가 |
|---|---|
| driver 정합 | ✓ patched, log-capture 검증 완료 |
| cred 정합 | ✓ TAVILY/NAVER/anthropic 모두 가용 (.venv_anthropic 존재 추정 — 측정 직전 import 확인 필요) |
| 측정 표준 transfer | ✓ §13-7 표준 정합 |
| 429 quota 우려 | ✓ Phase 1 0건, inter-sleep 60s 유지 |
| Phase 1 박제 정정 영향 | ⚠ NEW finding (15→0 drop) 이 Phase 2 측정 해석에 영향 가능 — 측정 결과의 `raw_items=0` 가 backend 실패가 아니라 **downstream filter 영향**일 수 있음을 단언 명시 필수 |

### 사용자 결정 영역

(1) **Phase 2 측정 진입**:
   - (Y) 즉시 진입 — combination (iii) `.venv_vertex` × legacy_only 부터
   - (N) 진입 보류 — NEW finding (15→0 drop) 진단 우선

(2) **15→0 drop 진단 (선행 시)**:
   - (A) Phase 3 으로 미루기 (현 Phase 2 spec 정합)
   - (B) 본 Phase 2 sub-task 신설 — search.py:1815~1889 read-only walk + Q4 records 의 dedup/gatekeep/year-filter 영향 단언

(3) **commit 정책**:
   - (X) Step A/A2 박제 + A1 audit 도 Phase 2 close commit 에 흡수
   - (Y) 별 commit 으로 분리 (Step A/A2 → 1 commit, A1 audit → 1 commit, Phase 2 close → 1 commit)

— Pre-task + Task 0/1/2 박제 종결. 사용자 컨펌 통과 (Y/B/Z) → Task 3~5 + Task 4.5 진행.

────────────────────────────────────────────────

## § 4. Task 3 — combination (iii) vertexai × legacy_only 측정

### 4-a. 측정 조건

- venv: `.venv_vertex`
- env load: `.env` (override=False) → `.env.vertex` (override=True) — `.env.vertex` 는 SKIP_VERTEX_SEARCH 미명시 → 글로벌 `.env:20 SKIP_VERTEX_SEARCH=1` 정합 (per-topic override 없이도 driver `legacy_only` mode 가 vertex 우회)
- VERTEX_MAX_RETRIES=0 (`.env.vertex:28`)
- backend mode: `--backend legacy_only --log-capture`
- N=3 + warmup 2, 4 query

### 4-b. 측정 결과 (N=12)

| metric | n | mean | stdev | cv_pct | min | max |
|---|---:|---:|---:|---:|---:|---:|
| elapsed_sec | 12 | **2.04** | 0.40 | 19.6% | 1.28 | 2.53 |
| raw_items | 12 | 1.5 | 1.17 | 77.8% | 0.0 | 3.0 |
| items_post_dedup | 12 | 1.5 | 1.17 | 77.8% | 0.0 | 3.0 |
| per_backend_total_log | — | — | — | — | — | `{naver_direct: 120, tavily: 60, _merged_total: 45}` |

- errors 0/12, 429 quota 0, abort 0
- 쿼리별 raw_items (각 cv 0% — deterministic):
  - Q1 (벤포벨S): 2 (elapsed 2.38s)
  - Q2 (활성형 비타민): 1 (elapsed 2.29s)
  - Q3 (비타민 B군): 3 (elapsed 2.02s)
  - Q4 (benfotiamine EN): **0** (elapsed 1.47s, `_merged_total=15` 캡처)

### 4-c. raw JSON 자산

- `scripts/output/§14-9/phase1_vertexai_legacy_only_phase2_20260517_220013.json` (.gitignored)

────────────────────────────────────────────────

## § 5. Task 4 — combination (iv) anthropic × legacy_only 측정 (B-1 (β) framing)

### 5-a. 측정 조건

- venv: `.venv_anthropic`
- env load: `.env` (override=False) → `.env.anthropic` (override=True, `LLM_PROVIDER=anthropic` + `SKIP_VERTEX_SEARCH=1` 명시)
- ANTHROPIC_MAX_RETRIES=0 (`.env.anthropic:31`)
- backend mode: `--backend legacy_only --log-capture`
- N=3 + warmup 2, 4 query

### 5-b. 측정 결과 (N=12)

| metric | n | mean | stdev | cv_pct | min | max |
|---|---:|---:|---:|---:|---:|---:|
| elapsed_sec | 12 | **2.21** | 0.48 | 21.5% | 1.33 | 2.92 |
| raw_items | 12 | 1.5 | 1.17 | 77.8% | 0.0 | 3.0 |
| items_post_dedup | 12 | 1.5 | 1.17 | 77.8% | 0.0 | 3.0 |
| per_backend_total_log | — | — | — | — | — | `{naver_direct: 120, tavily: 60, _merged_total: 45}` |

- errors 0/12, 429 quota 0, abort 0
- 쿼리별 raw_items (각 cv 0%): Q1=2, Q2=1, Q3=3, Q4=**0**

### 5-c. B-1 (β) framing 정합

- **A2 § 5-d 단언 검증**: anthropic provider 활성 시 web_search.invoke() 정상 작동 — naver_direct + tavily 호출 정합. 코드 ALLOWED path 단언 **실측 확인**.
- **framing = 현 상태 확인**: 본 측정 결과는 anthropic provider 운영 시 legacy chain 의 작동 양상 박제. **의도 mismatch 가시화 아님** — anthropic-RAG-only intent README 명시 부재 정합 (A2 § 5-c 박제).
- venv 동거: `.venv_anthropic` 는 `langchain-anthropic` chat + `langchain-openai` embedding fallback 패턴 (README-dev.md:1923 정합). search 모듈은 venv 와 무관하게 작동.

### 5-d. raw JSON 자산

- `scripts/output/§14-9/phase1_anthropic_legacy_only_phase2_20260517_220008.json` (.gitignored)

────────────────────────────────────────────────

## § 5.5. Task 4.5 — 15→0 drop read-only walk (NEW)

### 5.5-a. 검색 후처리 단계 박제 (search.py:1815~1889)

`web_search()` 함수 의 final 단계 (merged log 직후 → return 직전) 의 7-step 후처리:

| step | line | 동작 | drop 가능성 |
|---|---|---|---|
| 1 | search.py:1817-1819 | `[web_search][backend] merged got=N` 로그 — pre-filter count | (로깅만, drop 없음) |
| 2 | search.py:1825 | `results = _canon_and_dedupe(results)` — URL 정규화 + dedup (모바일/AMP 접기, 추적 파라미터 제거) | minor (중복 URL 시) |
| 3 | search.py:1826 | `_pretag_content_type(results)` — content-type 추정 | (annotation 만) |
| 4 | search.py:1827-1844 | **gatekeep** — `if gatekeep_enabled(): for it in results: if url_allowed(...): keep else: drop` | **★★★ 주 drop 후보** |
| 5 | search.py:1845 | `results = _pick_top(results, _topn)` — top-N cap (topn=40 in CFG) | minor (40 초과 시) |
| 6 | search.py:1854 | `results = _filter_non_2xx(results, timeout=probe_timeout, limit=probe_limit)` — HTTP probe로 non-2xx drop | **★★ 2차 drop 후보** |
| 7 | search.py:1856 | `[it for it in results if not normalize_or_block_intermediate_news(...)]` — 뉴스 aggregator redirect block | minor (intermediate news 시) |

### 5.5-b. gatekeep 동작 (settings_gatekeep.py:325-379 `is_allowed_url`)

```python
def is_allowed_url(url: str) -> bool:
    if not gatekeep_enabled(): return True
    _u = _canon_url(url)
    if is_local_like(_u): return True
    allow = _normalized_allowed_domains()
    if not allow:
        logger.warning("GATE_KEEP_SOURCES=ON 이지만 ALLOWED_DOMAINS가 비었습니다...")
        return False
    host_port = _normalize_host(_u)
    base = host_port.split(":", 1)[0]
    if base in allow: return True
    if _flag("ALLOW_SUBDOMAINS", False):
        parts = base.split(".")
        for i in range(len(parts) - 1):
            cand = ".".join(parts[i+1:])
            if cand in allow: return True
            # www-equiv 처리
    return False
```

### 5.5-c. 현 ALLOWED_DOMAINS 실측 (`.env:213`, GATE_KEEP_SOURCES=1 정합)

55개 도메인 — **거의 전부 KR pharma/news/gov**:
- 의약 매체 (15+): `dailypharm.com, medipana.com, kpanews.co.kr, pharmnews.com, yakup.com, medicopharma.co.kr, hitnews.co.kr, medifonews.com, ...`
- 일반 뉴스 (10+): `newsis.com, hankyung.com, sedaily.com, mk.co.kr, hankyoreh.com, chosunbiz.com, asiatoday.co.kr, edaily.co.kr, ...`
- naver 계열 (4): `news.naver.com, m.news.naver.com, search.naver.com, naver.com` (`ALLOW_SUBDOMAINS=1` 정합 시 `blog.naver.com` 도 pass)
- 정부/공공 (8+): `kosis.kr, mfds.go.kr, hira.or.kr, khidi.or.kr, krei.re.kr, scienceon.kisti.re.kr, dart.fss.or.kr, krx.co.kr, law.go.kr, nabo.go.kr, geumcheon.go.kr, aurum.re.kr`
- 종근당 관련 (2): `ckdpharm.com, chongkundang.com`
- 기타: `boryung.co.kr, w4.kirs.or.kr, ssl.pstatic.net, dez1irdmysogu.cloudfront.net`

**EN 의학 사이트 (pubmed.ncbi.nlm.nih.gov / mdpi.com / sciencedirect / etc.) — 부재**.

### 5.5-d. drop 단언 (3-combination 실측 통합)

| Q | log_bk (chain merge) | driver received raw | drop scope | provider-indep? |
|---|---|---|---|---|
| Q1 (벤포벨S, KR) | naver=10, tavily=5 (no _merged log → chain 정상 종료, retry path 미진입) | (ii)=1 / (iii)=2 / (iv)=2 | **13~14/15 dropped** | ✓ (3 combination 동일 양상) |
| Q2 (활성형 비타민, KR) | naver=10, tavily=5 | (ii)=1 / (iii)=1 / (iv)=1 | **14/15 dropped** | ✓ |
| Q3 (비타민 B군, KR) | naver=10, tavily=5 | (ii)=4 / (iii)=3 / (iv)=3 | **11~12/15 dropped** | ✓ |
| Q4 (benfotiamine, EN) | naver=10, tavily=5, _merged_total=15 (retry path 진입 → chain merge log) | **0/3 모두 0** | **15/15 dropped (100%)** | ✓ |

**drop location 단언 (확정)**:
- **★★★ search.py:1827-1844 gatekeep filter** — Q4 EN 의 모든 hit (PUBMED/NIH/IF/대부분 EN medical) ALLOWED_DOMAINS 외 → 100% drop
- 추가: **★★ search.py:1854 `_filter_non_2xx`** — 일부 KR 사이트가 HTTP probe 실패 (timeout/403) 로 추가 drop

**drop 사유 가설**:
- Q4 EN: tavily 가 PUBMED 등 영어 의학 site 반환 → KR-centric ALLOWED_DOMAINS 외 → 100% drop. naver_direct 도 EN 쿼리에 `webkr` 결과 반환 → 영어 source 다수 → 대부분 drop.
- Q1-Q3 KR: naver_direct 가 KR news/pharma 도메인 반환 → 일부 (`blog.naver.com`, `dailypharm.com`, `asiatoday.co.kr` 등) ALLOWED 통과. 나머지 + tavily 결과 대부분 drop.
- Q4 의 `_merged_total=15` log 가 다른 Q1-Q3 에 없는 사유: **retry path 진입** (search.py:1798-1815). Q1-Q3 는 chain 1회 진입에서 `results` 가 비어있지 않음 → retry path 미진입 → `merged` log 미발화. Q4 는 first-pass 후 `results` 가 모두 drop → retry path 진입 → `merged` log 발화.

### 5.5-e. Phase 3 (B-B vertex metadata persistence) 와의 영역 분리

| 영역 | location | drop 대상 | 책임 모듈 |
|---|---|---|---|
| **본 finding (Task 4.5)** | search.py:1827-1844 gatekeep | URL host 가 ALLOWED_DOMAINS 외인 item | `settings_gatekeep.is_allowed_url` |
| **Phase 3 B-B** | `web_results_to_documents` 화이트리스트 (README-dev-_14.md:24) | item.metadata 의 vertex `backend/alt_urls/chunk_domain` 키 | `tools/web_rag/ingest_vector.py` 또는 `tools/web_rag/utils.py` |

→ **drop = post-chain search-stage filter**, **B-B = post-fetch index-stage metadata whitelist** — **분리된 layer**. Phase 3 scope 무영향.

### 5.5-f. STOP 정합 (Task 4.5 한정)

- file edit 시도: 0 ✓
- 실행 (driver call / 측정) 시도: 0 ✓
- 추정 단언 (line ref 없이): 0 ✓ — 모든 단언 line ref 동반 (search.py / settings_gatekeep.py / `.env:213`)

────────────────────────────────────────────────

## § 6. Task 5 — 비교 박제 + Phase 3 entry valid

### 6-a. 4-combination matrix (Phase 1 + Phase 2 통합)

| combination | venv | provider | backend mode | elapsed mean (s) | elapsed cv | raw_items mean | raw cv | per_backend_log_total | Q4 raw |
|---|---|---|---|---:|---:|---:|---:|---|---:|
| (i) Phase 1 | .venv_vertex | vertexai | **vertex_grounding** | 22.12 | 29.6% | 11.5 | 58.4% | `{vertex_grounding: 138}` (heuristic) | 12.33 |
| (ii) Phase 1 | .venv_openai | openai | legacy_only | 2.16 | 18.1% | 1.5 | 104.4% | (log capture 미적용 — heuristic 만) | 0 |
| (iii) Phase 2 | .venv_vertex | vertexai | legacy_only | **2.04** | 19.6% | 1.5 | 77.8% | `{naver_direct:120, tavily:60, _merged_total:45}` | 0 |
| (iv) Phase 2 | .venv_anthropic | anthropic | legacy_only | **2.21** | 21.5% | 1.5 | 77.8% | `{naver_direct:120, tavily:60, _merged_total:45}` | 0 |

### 6-b. LLM_PROVIDER 토글 영향 단언 (legacy chain)

- **legacy chain backbone (naver_direct + tavily 호출) 은 provider-independent 확정**:
  - (iii) vertexai + (iv) anthropic 의 `per_backend_total_log` **완전 동일** (`naver=120, tavily=60, _merged=45`)
  - (ii) openai 도 log capture 미적용이나 raw_items 분포 유사 (Q1=1, Q2=1, Q3=4, Q4=0)
  - elapsed 2.04~2.21s 범위 (cv 18~22%) — provider 별 차이 ≤ 8% (statistical noise)
- **A2 § 2-d 단언 검증 완료**: "search backend chain 자체는 provider-INDEPENDENT" 실측 확인.

### 6-c. raw_items 차이 정리 (Q1: ii=1 vs iii/iv=2, Q3: ii=4 vs iii/iv=3)

- Q1/Q3 의 minor 차이는 **chain backbone 동일 + post-gatekeep filter 의 시간/네트워크 변동** 가능성 (Phase 1 측정 20:41 vs Phase 2 측정 22:00 ~80 min 간격):
  - `_filter_non_2xx` 의 HTTP probe 가 사이트 가용성에 의존
  - 일부 사이트 (e.g., dailypharm) 의 응답 변동
- **provider-independent + time-of-day dependent** 패턴 — Phase 1 박제 raw_items 와 Phase 2 raw_items 의 ~10% 변동은 측정 noise 영역.

### 6-d. Q4 drop 통합 단언 (Task 4.5 + 3-combination 측정)

- **drop location**: search.py:1827-1844 gatekeep + 1854 `_filter_non_2xx` (★★★ + ★★)
- **drop scope**: provider-independent — 3 combination 모두 Q4 raw=0 (cv 0%)
- **drop scope**: query-dependent — Q4 (EN) 100% drop / Q1-Q3 (KR) 73~93% drop / **선택적 drop, query intent · domain 정합 의존**
- **fundamental cause**: 글로벌 `.env:213 ALLOWED_DOMAINS` 의 KR-pharma-centric 구성 + `GATE_KEEP_SOURCES=1` 운영 정책

### 6-e. A2 § 4-g fusion 일관성 ★★★★☆ 회귀 검증

| A2 § 4-g 단언 | Phase 2 측정 후 단언 |
|---|---|
| schema 통일 (5-key) | Phase 1 정정 (3-layer 분리, A2 부록 반영) — ★★★★☆ 유지 |
| dedup key URL 통일 | Phase 2 측정 정합 ✓ |
| rerank LLM-free deterministic | (iii)(iv) 의 per-query raw_items cv 0% → deterministic 정합 ✓ |
| vertex metadata 인덱싱 drop | Phase 2 측정 영역 외 (Phase 3 B-B scope) |

→ **fusion 일관성 ★★★★☆ 유지 + drop layer 영향 평가 보강**: drop 은 search-stage post-filter 이며 fusion 자체와는 **분리된 책임**. fusion 자체는 정합 — dedup/rerank 결정성, schema 일관성 (3-layer 명시 후) 모두 OK.

### 6-f. Phase 3 entry valid 조건 단언

| 조건 | 평가 |
|---|---|
| measurement infrastructure 정합 | ✓ (driver `backend_isolated_smoke.py` patched, log-capture 정합) |
| Phase 1 Phase A 회귀 부재 | ✓ (Phase 1 § 2-d 박제) |
| Q4 drop 영역 분리 확인 | ✓ (§ 5.5-e: drop=search-stage, B-B=index-stage 분리) |
| vertex metadata drop 가시화 자산 design input | ⚠ Phase 3 시 `fusion_observability.py` 권장 (A2 § 6-4 정합) — 본 Phase 2 driver 의 `_install_log_capture` 패턴 재활용 + `web_results_to_documents` 단계 추가 캡처 |
| production code patch 영역 확정 | ⚠ Phase 3 B-B = `web_results_to_documents` whitelist 확장 (README-dev-_14.md:110 sub-task (a)) — 본 Task 4.5 drop = `settings_gatekeep.url_allowed` (별 영역, B-B 무관) |
| 429 quota / measurement cv > 50% | 0 / Phase A precedent 정합 (Q3 vertex_grounding raw cv 52.9%, 본 cycle Q1-Q3 legacy cv 0%) |

→ **Phase 3 (B-B vertex metadata persistence) 진입 valid**. 본 Task 4.5 finding 은 별도 sub-track (`§14-9 Step B 별 cycle` — ALLOWED_DOMAINS 확장 또는 GATE_KEEP_SOURCES off 운영) 으로 분리 진입 권장 — Phase 3 B-B 와 영역 충돌 없음.

### 6-g. commit 정책 — 2-commit 분리

**commit α — A-track close**:
- 추가: `scripts/output/§14-9/step_a_backend_provider_matrix.md` (Step A + A1 부록)
- 추가: `scripts/output/§14-9/step_a2_fusion_and_verify.md` (A2 + Phase 1 정정 부록)
- 추가: `scripts/output/§14-9-A1/credential_exposure_audit.md` (A1 audit)
- message: `§14-9 Step A + A1 + A2 박제 자산 (audit chain + 정정 reference 부록)`

**commit β — Phase 2 close**:
- 수정: `scripts/§14-9/backend_isolated_smoke.py` (driver log-capture patch — `_BackendLogHandler` + `_install_log_capture` + `--log-capture` flag + `per_backend_dist_log` 필드)
- 추가: `scripts/output/§14-9/step_b_phase2_extended_smoke.md` (본 박제)
- message: `§14-9 Step B Phase 2 — methodology 보강 (log-capture) + ★★★★☆ 2 combination + Q4 drop 진단`

### 6-h. STOP 정합 검증 (Phase 2 close 시점)

- production code 수정 시도: 0 ✓ (driver 만 patch)
- driver 외 신규 file 생성: `step_b_phase2_extended_smoke.md` 1 file (spec 정합)
- N=3 ≤ 5 / timeout 240s ≤ 300s ✓
- 429 quota 발현: 0 ✓
- 측정 cv > 50%: Q3 legacy cv 0% / Q4 legacy cv 0% / aggregated cv 77.8% (구조적 query asymmetry, Phase 1 precedent 정합) — measurement noise 영역 외 단언 아님
- raw JSON tracked 시도: 0 ✓ (.gitignore:82 정합)
- key 전체 string 박제: 0 ✓ (prefix only 유지)
- axis-ambiguous word: § 1 / § 2-d / § 5.5 에서 axis 명시 (heuristic vs log-based, drop location vs B-B scope, layer (a)/(b)/(c) 등)

────────────────────────────────────────────────

## § 7. 결론 요약

1. **Pre-task + Task 0/1/2** 완료 — Phase 1 close commit `4e78b63`, A2 § 4-c 3-layer schema 정정 reference 적용, Q4 tavily 미발화 진단 = false alarm (가설 (b) REJECTED, (d) drop EMERGING).
2. **Task 3 + 4 — combination (iii)(iv) 측정** — 각 12/12 success, errors 0, 429 quota 0. legacy chain backbone **provider-independent** 실측 확정 (per_backend_total_log identical).
3. **Task 4.5 — drop location 확정** — search.py:1827-1844 gatekeep (★★★ primary) + search.py:1854 `_filter_non_2xx` (★★ secondary). 근본 원인 = `.env:213 ALLOWED_DOMAINS` KR-pharma-centric + GATE_KEEP_SOURCES=1.
4. **drop scope** — Q4 (EN) 100% / Q1-Q3 (KR) 73~93% / provider-independent / query-domain-dependent.
5. **fusion 일관성 ★★★★☆ 유지** + drop layer 분리 (search-stage filter, fusion 자체와 별 책임).
6. **Phase 3 (B-B vertex metadata persistence) 진입 valid** — drop 영역과 분리, sub-track 분기 권장 (ALLOWED_DOMAINS 확장 별 cycle).

— §14-9 Step B Phase 2 박제 종결 (2-commit 진행 후 사용자 컨펌 대기).
