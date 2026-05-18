# §14-9-W Step A — whitelist + gate-keeping 진단 (read-only audit)

## 본 mission 박제

- entry: §14-9 Phase 2 close 후속 (commit β `3b2ebae` baseline)
- 발견 (Phase 2 Task 4.5): Q4 EN 100% / Q1~Q3 KR 73~93% drop in gatekeep filter (`tools/web_rag/search.py:1827-1844`)
- §14-9 main mission 사이드 finding 으로 신설된 sub-cycle
- W cycle 구조: **Step A (진단) → Step B (설계) → Step C (구현)**
- 채택 방안: **β (layered: base + topic) + γ (toggle escape hatch) 결합**
- 후속: Phase 3 (B-B vertex metadata persistence) — W close 후 순차 진입
- precedent cross-ref:
  - §14-9 Step A / A2 (read-only audit 패턴)
  - §12-11-4 subdomain stripping 박제
  - §12-11-5 화이트리스트 확장 시도 실패 박제
  - §12-19 per-topic env override 패턴

## Pre-condition 박제

| 항목 | 값 |
|---|---|
| branch | `main` |
| HEAD (W Step A entry baseline) | `3b2ebae` (`§14-9 Step B Phase 2 — methodology 보강 (log-capture) + ★★★★☆ 2 combination + Q4 drop 진단`) |
| Phase 2 close commit α | `f858af5` (`§14-9 Step A + A1 + A2 박제 자산 (audit chain + 정정 reference 부록)`) |
| working dir | `D:\GPT_AGENT\writer_project` |
| 산출 변경 | read-only — file edit / commit 0 (production code / .env / 박제 file 모두 무수정), 신규 박제 자산 1개 (`step_a_whitelist_diagnosis.md`) |

────────────────────────────────────────────────

## § 1. Task 1 — gate 로직 + 매칭 mechanics 박제

### 1-a. gate filter 호출 사이트 (`tools/web_rag/search.py`)

**primary drop 위치** (Phase 2 Task 4.5 확정):

```python
# tools/web_rag/search.py:1827-1844 — final-stage gatekeep
if gatekeep_enabled():
    filtered = []
    for it in results:
        u = it.get("url") or it.get("source") or ""
        nu = _canon_url(u)
        if url_allowed(nu):
            filtered.append(it)
        else:
            reason = _gatekeep_drop_reason(u)
            logger.info(
                "[GATEKEEP][DROP] reason=%s host=%s url=%s",
                reason, _host_for_log(nu), nu,
            )
    results = filtered
else:
    results = _apply_gatekeep_to_results(results)  # noop branch (gatekeep off 시)
```

**secondary drop 위치** (chain 진행 중 가시화):

```python
# tools/web_rag/search.py:1630-1647 — chain backend pick 단계의 allowlist hit count
for _it in best_res:
    _u = _it.get("url") or _it.get("source") or ""
    if _u:
        nu = _canon_url(_u)
        if url_allowed(nu):
            _allowed_cnt += 1
        else:
            reason = _gatekeep_drop_reason(nu)
            logger.info("[GATEKEEP][DROP] reason=%s host=%s url=%s", ...)
```

→ chain pick 단계는 **카운팅 + 로깅 only** (early-stop 판단 `if allowlist_hits >= _min_ok` L1654). 실제 drop 은 search.py:1827-1844 단일 지점에서 적용.

### 1-b. 판정 함수 (`settings_gatekeep.is_allowed_url`, settings_gatekeep.py:325-379)

알고리즘 순서:

1. **gatekeep off 분기** (`gatekeep_enabled()` False) → `return True` (L334-335, settings_gatekeep.py:207-209)
2. **URL canonicalize** → `_canon_url(url)` 호출 (L338, normalize_url 위임)
3. **local-like 우회** → `is_local_like(_u)` True (file/data/about/blob/localhost/127/::1) 시 `return True` (L340-341)
4. **allow set 빌드** → `_normalized_allowed_domains()` (L344, lru_cache=1)
5. **빈 list 분기** → empty 시 경고 1회 + `return False` (L345-347)
6. **host 정규화** → `_normalize_host(_u)` 호출 (L350)
7. **TLD valid 검사** → `_valid_host(base)` False 시 `return False` (L356-357, _TLD_ALLOW L159-162 화이트리스트)
8. **exact match** → `if base in allow: return True` (L359-360)
9. **ALLOW_SUBDOMAINS 분기** (L363-377):
   - 활성 시 suffix 매칭 loop: `a.b.example.com → b.example.com → example.com` 순회
   - `_treat_www_equiv()` 활성 시 (URL_TREAT_WWW_EQUIV=1) 양방향 www. prefix 체크
10. **최종 fallthrough** → `return False`

### 1-c. URL/호스트 정규화 (`_normalize_host`, settings_gatekeep.py:231-307)

- IDNA → punycode 정규화 (L264-267)
- 소문자 + trailing dot 제거 (L269)
- 명시 매핑 적용 (L272-273): `_MOBILE_HOSTS = {"m.dailypharm.com": "www.dailypharm.com", "m.newsmp.com": "www.newsmp.com", "mobile.newsmp.com": "www.newsmp.com", "m.yakup.com": "www.yakup.com"}`
- `amp.` 접두 제거 (L276-277)
- 모바일 라벨 접기 (`URL_NORMALIZE_MOBILE_TO_WWW=1` 시): 선두 `m`/`mobile` pop + `www` prefix 부여 (L279-296, `_NO_WWW_EXACT` + `*.go.kr` / `*.or.kr` 제외)
- `URL_TREAT_WWW_EQUIV=1` 시 입력측 `www.` 접두 제거 (L298-300) — allow set 도 동일 규칙으로 정규화하여 비교 일관성 유지

### 1-d. allow set 빌드 (`get_allowed_domains`, settings_gatekeep.py:138-155)

병합 순서:
1. **하드코드 base** `_BASE_ALLOWED_DOMAINS` (settings_gatekeep.py:45-66, 17 도메인 KR pharma/gov):
   ```
   mfds.go.kr, kosis.kr, index.go.kr, khidi.or.kr, hira.or.kr,
   data.go.kr, moef.go.kr, law.go.kr, dart.fss.or.kr,
   dailypharm.com, medipana.com, newsmp.com, yakup.com,
   kpanews.co.kr, pharmnews.com, medicopharma.co.kr, healtho.co.kr
   ```
2. **CFG attr** (`config.CFG.ALLOWED_DOMAINS`) — set/list/tuple/str 모두 수용 (L145-149)
3. **ENV `ALLOWED_DOMAINS`** (L153) — 글로벌 `.env:213` 으로 직접 주입
4. **ENV `ALLOWED_DOMAINS_EXTRA`** (L154) — **확장 슬롯 이미 존재** (β layered 설계의 부분 기반)

런타임 주입 우선:
- `_RUNTIME_ALLOWED` set 비어있지 않으면 위 4-병합 무시하고 단독 사용 (L140-141, `set_runtime_allowed_domains` 호출 시)

캐시:
- `_normalized_allowed_domains` @lru_cache(maxsize=1) (L187) — 변경 후 `refresh_gatekeep_cache()` (L128) 필요

### 1-e. `GATE_KEEP_SOURCES` 영향 범위 (전수 grep)

| 위치 | 역할 |
|---|---|
| `core/config.py:276,506` | `Config.GATE_KEEP_SOURCES: bool` 필드 + `_env_flag(..., False)` default off |
| `core/config.py:756` | 모듈-레벨 `Final[bool] = CFG.GATE_KEEP_SOURCES` (import 시 frozen) |
| `settings_gatekeep.py:207-209` | `gatekeep_enabled()` 동적 read — `_flag("GATE_KEEP_SOURCES", False)` (CFG.truthy → ENV) |
| `settings_gatekeep.py:334,346` | `is_allowed_url` 진입 분기 + empty list 경고 |
| `tools/web_rag/search.py:1827,1844` | final filter 호출 (primary) |
| `tools/web_rag/utils.py:1516` | `_apply_gatekeep_to_results` 호출 분기 (`if not results or not gatekeep_enabled(): return results`) |
| `agent/web_search.py:415-453` | pre-search 단계 상태 logging + 안전 폴백 (`enabled but empty → temporarily disable`) |
| `agent/web_search.py:523,1022` | runtime 단계 분기 |
| `utils/forced_queries.py:95-96,217` | forced queries 단계 active 검사 (`FORCED_QUERY_ENFORCE_GATEKEEP and GATE_KEEP_SOURCES and ALLOWED_DOMAINS`) |
| `app.py:2270-2272` | CLI `--gatekeep` args override |

현 `.env:207` 설정: **`GATE_KEEP_SOURCES=1`** (active).

### 1-f. `FILTER_BAD_DOMAINS` (deny list) 와의 관계

현 `.env:215` 설정: **빈 값** (L217 commented out — 후보 도메인 다수 보관).

| 위치 | 매칭 방식 |
|---|---|
| `core/config.py:406,642` | `_env_str("FILTER_BAD_DOMAINS", "")` 그대로 string 보관 |
| `agent/web_search.py:619-625` | `bd in url` substring 매칭 — local store retrieval 단계 noise filter |
| `tools/web_rag/ingest_vector.py:898-913,1604-1705` | ingest 단계 `bd in _src_url` substring 매칭 — 인덱싱 차단 |

**allow vs deny 우선순위**:
- 두 list 는 **다른 layer 에서 작동** — `FILTER_BAD_DOMAINS` 는 ingest/local retrieval 단계, `ALLOWED_DOMAINS` 는 web search post-filter 단계.
- search 단계에서는 `FILTER_BAD_DOMAINS` 직접 비교 없음. 즉 web_search result 가 ingest 로 진입 시 비로소 deny list 적용.

### 1-g. §12-11-4 subdomain stripping 부재 검증

**검증 결과: 부재 아님 — 이미 구현됨**.

- 현 `.env:208`: **`ALLOW_SUBDOMAINS=1`** 설정 정합.
- settings_gatekeep.py:363-377 loop: subdomain → parent traversal 매칭 (`oldm.dailypharm.com → dailypharm.com` 비교 가능).
- `_MOBILE_HOSTS` 명시 매핑 (L214-220) + 모바일 라벨 접기 (L279-296) 로 m./mobile./amp. 변형도 정규화.

`oldm.dailypharm.com` 의 매칭 흐름:
1. `_normalize_host("https://oldm.dailypharm.com/path")` → `host = "oldm.dailypharm.com"`
2. `_MOBILE_HOSTS` 매핑 비대상 (oldm prefix 부재) — 변환 skip
3. 모바일 라벨 접기: `m`/`mobile` 라벨이 선두에 없음 (`oldm` 은 한 단어) — skip
4. `base = "oldm.dailypharm.com"` → `base in allow` False
5. ALLOW_SUBDOMAINS 분기 진입 → parts = `["oldm", "dailypharm", "com"]`
6. i=0 → cand=`"dailypharm.com"` → `allow` 에 있음 → **`return True`**

→ §12-11-4 의 sub-domain stripping 의도는 현 ALLOW_SUBDOMAINS 분기로 달성. 별도 fix 통합 불요 (W Step C 에서 재확인 필요한 영역 아님).

────────────────────────────────────────────────

## § 2. Task 2 — ALLOWED_DOMAINS 현 구성 분석 + 분류

### 2-a. `.env:213` 55-domain dump (실측)

```
dailypharm.com, medipana.com, kpanews.co.kr, pharmnews.com, yakup.com,
medicopharma.co.kr, hitnews.co.kr, medifonews.com, pharmstoday.com,
dailymedi.com, whosaeng.com, kmpnews.co.kr, k-health.com, hidoc.co.kr,
newsis.com, healtho.co.kr, consumernews.co.kr, ckdpharm.com, chongkundang.com,
hankyung.com, sedaily.com, mk.co.kr, hankyoreh.com, chosunbiz.com,
asiatoday.co.kr, mediapen.com, dongascience.com, nspna.com, edaily.co.kr,
betanews.net, goodkyung.com, weekly.hankooki.com, kosis.kr, index.go.kr,
data.go.kr, moef.go.kr, mfds.go.kr, hira.or.kr, khidi.or.kr, krei.re.kr,
scienceon.kisti.re.kr, repository.kisti.re.kr, dart.fss.or.kr, krx.co.kr,
law.go.kr, lkp.news, news.naver.com, m.news.naver.com, search.naver.com,
naver.com, securities.miraeasset.com, boryung.co.kr, w4.kirs.or.kr,
ssl.pstatic.net, dez1irdmysogu.cloudfront.net, nabo.go.kr, geumcheon.go.kr,
aurum.re.kr
```

(실측 count: **58 entries** — 박제용 어림 "55개" 표기 정정. 본 § 5 base 후보 추출에서는 실측 list 사용.)

### 2-b. 6-category 분류

| # | 카테고리 | 도메인 | 비고 |
|---:|---|---|---|
| 1 | **의약 산업/제약사** (3) | ckdpharm.com, chongkundang.com, boryung.co.kr | 종근당 + 보령 |
| 2 | **의약 매체/뉴스** (16) | dailypharm.com, medipana.com, kpanews.co.kr, pharmnews.com, yakup.com, medicopharma.co.kr, hitnews.co.kr, medifonews.com, pharmstoday.com, dailymedi.com, whosaeng.com, kmpnews.co.kr, k-health.com, hidoc.co.kr, healtho.co.kr, consumernews.co.kr | KR pharma media core |
| 3 | **정부/공공기관** (15) | kosis.kr, index.go.kr, data.go.kr, moef.go.kr, mfds.go.kr, hira.or.kr, khidi.or.kr, krei.re.kr, scienceon.kisti.re.kr, repository.kisti.re.kr, dart.fss.or.kr, krx.co.kr, law.go.kr, nabo.go.kr, geumcheon.go.kr, aurum.re.kr, w4.kirs.or.kr | KR gov/공공 — 통계/규제/연구/공시 |
| 4 | **학술/연구** (2 — partial overlap) | scienceon.kisti.re.kr, repository.kisti.re.kr | KR KISTI 만 — **EN 학술 0건** |
| 5 | **광고/마케팅 매체** (0) | (없음) | **부재** — 광고대행사 운영 토픽에서 빈 슬롯 |
| 6 | **기타/일반 뉴스/네이버** (16) | hankyung.com, sedaily.com, mk.co.kr, hankyoreh.com, chosunbiz.com, asiatoday.co.kr, mediapen.com, dongascience.com, nspna.com, edaily.co.kr, betanews.net, goodkyung.com, weekly.hankooki.com, newsis.com, lkp.news, news.naver.com, m.news.naver.com, search.naver.com, naver.com, securities.miraeasset.com, ssl.pstatic.net, dez1irdmysogu.cloudfront.net | KR 종합 매체 + naver 계열 + 보조 (pstatic / cloudfront) |

### 2-c. Phase 2 raw JSON cross-ref (Q1-Q4 통과/차단 도메인 추정)

Phase 2 `step_b_phase2_extended_smoke.md` § 5.5-d 실측 (3-combination 통합):

| Q | query (lang) | per_backend log | post-gatekeep raw | drop scope | 통과 추정 도메인 |
|---|---|---|---:|---|---|
| Q1 | 벤포벨S 핵심성분 (KR) | naver=10, tavily=5 | 1~2 / 15 | 13~14 dropped | dailypharm / kpanews 추정 |
| Q2 | 활성형 비타민 (KR) | naver=10, tavily=5 | 1 / 15 | 14 dropped | dailypharm / yakup 추정 |
| Q3 | 비타민 B군 (KR) | naver=10, tavily=5 | 3~4 / 15 | 11~12 dropped | dailypharm / hidoc / asiatoday 추정 |
| Q4 | **vitamin B benfotiamine clinical trial (EN)** | naver=10, tavily=5, _merged_total=15 | **0 / 15** | **15 dropped (100%)** | **0건 — 통과 도메인 없음** |

(차단된 EN 도메인은 raw JSON `.gitignored` 자산에 보관 — line ref:Phase 2 § 5-d `phase1_anthropic_legacy_only_phase2_20260517_220008.json`. 5/15 tavily 결과의 host 분포는 본 read-only audit 범위에서 ★★★★ 단계 — `pubmed.ncbi.nlm.nih.gov / nih.gov / mdpi / sciencedirect / who.int / wikipedia / 또는 .edu / .gov US` 등 EN 학술 도메인으로 추정. 정량 확인은 raw JSON 직접 inspect 필요.)

### 2-d. β 설계 input — base list 후보 도메인 식별

**KR 쪽 base 후보** (현 .env 유지 + 의도된 운영 정책):
- 카테고리 3+4 (정부/공공기관/학술) = 약 17 도메인 — **현 base 17 (`_BASE_ALLOWED_DOMAINS`, settings_gatekeep.py:45-66)** 의 9개 (mfds/kosis/index/khidi/hira/data/moef/law/dart) + KISTI/krx/krei/nabo/geumcheon/aurum/w4.kirs/repository.kisti
- 카테고리 2 (의약 매체) = 16 도메인 — base 보강 후보 (현 base 8개 of 16, 추가 후보 8: hitnews/medifonews/pharmstoday/dailymedi/whosaeng/kmpnews/k-health/hidoc/consumernews)

**EN 학술 base 후보** (현 .env 부재 확정):
- `pubmed.ncbi.nlm.nih.gov`, `ncbi.nlm.nih.gov` — PubMed (US NIH)
- `nih.gov`, `nhlbi.nih.gov`, `niddk.nih.gov` — NIH 직접 산하
- `who.int` — WHO
- `cdc.gov`, `fda.gov` — US 보건/규제 (KR mfds 대응)
- `clinicaltrials.gov` — US clinical trial registry
- `mayoclinic.org` — Mayo Clinic 가이드
- `nature.com`, `sciencedirect.com`, `springer.com`, `mdpi.com`, `tandfonline.com`, `cell.com`, `lancet.com`, `nejm.org`, `bmj.com`, `cochranelibrary.com` — 학술 publisher
- `.edu`, `.gov` (kr 외) — TLD 단위 — 단 `_TLD_ALLOW` (settings_gatekeep.py:159-162) 에 `edu`/`gov` 이미 포함되나, `get_allowed_domains()` 의 entry 는 host 단위 — TLD wildcard 매칭은 부재 (β Step B 에서 wildcard 도입 여부 결정 필요)

**광고/마케팅 base 후보** (광고대행사 토픽 슬롯):
- `adweek.com`, `adage.com`, `wpp.com`, `marketingweek.com` (EN)
- `kobaco.co.kr`, `kmac.co.kr`, `koreabranding.co.kr` (KR)
- 현 .env 부재 단언 → β topic-level 옵션 후보

### 2-e. **EN 학술 도메인 부재 단언** (Q4 100% drop 사유 정합)

- 카테고리 4 (학술/연구) 의 KR-only 구성 (KISTI 2건) → EN 학술 0건
- ALLOW_SUBDOMAINS=1 의 suffix 매칭 도 base set 에 `ncbi.nlm.nih.gov` 등 부재 → 매칭 불가
- **fundamental cause 재확인**: Phase 2 § 6-d 박제 정합 — "글로벌 `.env:213 ALLOWED_DOMAINS` 의 KR-pharma-centric 구성 + `GATE_KEEP_SOURCES=1` 운영 정책"

────────────────────────────────────────────────

## § 3. Task 3 — 토픽 env load 순서 + per-topic override 패턴 박제

### 3-a. env load 순서 (`core/config.py:153-169` `_load_dotenv_once`)

```
1) load_dotenv(find_dotenv(usecwd=True), override=False)
                                          ─────────────── (글로벌 .env, 기존 os.environ 우선)
2) _apply_provider_overlay(verbose=True)
                                          ─────────────── .env.<provider> override=True
   (settings_gatekeep.py:117-127: prov='vertex' 매핑, .env.vertex / .env.openai / .env.anthropic 후보)
3) _apply_topic_preset(verbose=True)
                                          ─────────────── topics/<slug>.env override=True
   (settings_gatekeep.py:130-150: TOPIC_SLUG 환경변수 기반)
```

**우선순위 (강함 → 약함)**:
```
topics/<slug>.env > .env.<provider> > 글로벌 .env > os.environ 외부값
```

### 3-b. `reload_config_inplace` 의 동일 순서 보존 (`core/config.py:663-684`)

```python
def reload_config_inplace() -> Config:
    with _cfg_lock:
        if _DOTENV_READY:
            # _PROTECTED_ENV_KEYS snapshot (LLM_PROVIDER, LLM_MODEL, TOPIC_SLUG,
            #                                SKIP_VERTEX_SEARCH, MIRROR_STATE_TO_ENV)
            _saved_env = {k: os.environ.get(k) for k in _PROTECTED_ENV_KEYS}
            try:
                load_dotenv(find_dotenv(usecwd=True), override=True)
            except Exception:
                pass
            # restore (None 은 skip — .env 값 허용)
            for _k, _v in _saved_env.items():
                if _v is not None:
                    os.environ[_k] = _v
            _apply_provider_overlay(verbose=False)
            _apply_topic_preset(verbose=False)
        ...
```

→ §14-8-B fix O 정합 (driver subprocess 의 명시 env 가 .env override 로 회귀하던 문제 차단).

### 3-c. ALLOWED_DOMAINS / GATE_KEEP_SOURCES 의 토픽 env override 가능성

| key | 토픽 env override 가능? | mechanics |
|---|---|---|
| `ALLOWED_DOMAINS` | ★★★ **부분 가능 (replace only)** | topics/<slug>.env 에 `ALLOWED_DOMAINS=...` 라인 추가 → `load_dotenv(override=True)` 로 글로벌 값 완전 replace. **extend 불가능** — 글로벌 list 무시됨. |
| `ALLOWED_DOMAINS_EXTRA` | ★★★★★ **완전 가능 (extend)** | settings_gatekeep.py:154 `out \|= _as_set(os.getenv("ALLOWED_DOMAINS_EXTRA", ""))` — 글로벌 `ALLOWED_DOMAINS` + `_BASE_ALLOWED_DOMAINS` 와 set union. **β layered 의 토픽 슬롯 이미 존재**. |
| `GATE_KEEP_SOURCES` | ★★★★★ **완전 가능** | settings_gatekeep.py:209 `_flag("GATE_KEEP_SOURCES", False)` dynamic CFG.truthy → ENV. 토픽 env 의 `GATE_KEEP_SOURCES=0` 한 줄로 무력화. |
| `ALLOW_SUBDOMAINS` | ★★★★★ **완전 가능** | settings_gatekeep.py:363 `_flag("ALLOW_SUBDOMAINS", False)` dynamic. |
| `URL_TREAT_WWW_EQUIV` | ★★★★★ **완전 가능** | settings_gatekeep.py:223 `_treat_www_equiv()` dynamic. |

**주의 — CFG snapshot frozen issue**:
- `core/config.py:757` `ALLOWED_DOMAINS: Final[Set[str]] = CFG.ALLOWED_DOMAINS` — module import 시 frozen set
- 토픽 env load 후 `reload_config_inplace()` 호출하지 않으면 모듈-레벨 `Final` 값은 stale
- 그러나 `settings_gatekeep.get_allowed_domains()` 는 dynamic — `os.getenv()` 직접 read → **gatekeep 동작에는 영향 없음** (refresh_gatekeep_cache 호출 시 lru_cache 무효화)

### 3-d. settings_gatekeep.py 의 cache 무효화 호출 사이트

| 위치 | 동작 |
|---|---|
| `tools/web_rag/search.py:275-276` | 모듈 import 직후 1회 refresh |
| `tools/web_rag/search.py:1368` | 측정 시 reload_config() 직후 refresh |
| `app.py:2287-2288` | CLI --gatekeep args 처리 후 refresh |
| `agent/web_search.py:35,434` | 안전 폴백 — enabled but empty 시 refresh |

→ 토픽 env load 시 cache 자동 갱신은 부재. **W Step C 에서 cache invalidation 호출 추가 필요 가능성** (β layered 구현 시 토픽 진입 hook 명시).

### 3-e. β 설계 input — base+topic 분리 mechanics

**현 구조 (재사용 가능)**:
- `_BASE_ALLOWED_DOMAINS` (settings_gatekeep.py:45-66, 17 도메인 하드코드)
- `ALLOWED_DOMAINS` (글로벌 .env, replace)
- `ALLOWED_DOMAINS_EXTRA` (토픽/추가 slot, extend union)

**β 안 — 신규 명명 후보** (W Step B 결정 영역):
- 옵션 (a): 기존 `ALLOWED_DOMAINS_EXTRA` 슬롯 그대로 사용 — 코드 변경 0줄, 토픽 env 만 추가
- 옵션 (b): 신규 `ALLOWED_DOMAINS_TOPIC` 명명 도입 — settings_gatekeep.py:153-155 에 1줄 추가
- 옵션 (c): `_BASE_ALLOWED_DOMAINS` 확장 (EN 학술 + 광고 기본 포함) + 토픽 env 는 `_EXTRA` 사용 — 하드코드 base 의 KR 편향 시정

**코드 변경 영역 정량**:
- 옵션 (a): 0줄 (토픽 env 만 추가)
- 옵션 (b): +1줄 (settings_gatekeep.py:155)
- 옵션 (c): +N줄 (hardcode 확장 N≈10~20 EN 도메인)

────────────────────────────────────────────────

## § 4. Task 4 — γ toggle escape hatch 메커니즘 설계 input

### 4-a. `GATE_KEEP_SOURCES` 전수 grep hit list (§ 1-e 재게재)

10개 사이트 — 동적 read (settings_gatekeep.py:209) 통일.

### 4-b. γ 토픽별 override 가능성

**가능** — settings_gatekeep.py:207-209 `gatekeep_enabled()` 의 dynamic 패턴.

토픽 env 예시:
```sh
# topics/<en-academic-topic>.env
GATE_KEEP_SOURCES=0    # 토픽-한정 gate off
```

영향 범위:
- `is_allowed_url` 의 early return True (settings_gatekeep.py:334)
- search.py:1827 분기 False → `_apply_gatekeep_to_results` 의 noop branch (utils.py:1516 `if not gatekeep_enabled(): return results`)
- search.py:1641 의 카운팅도 reason='gatekeep_disabled' 로 통과 (settings_gatekeep.py:404-405)

다른 영역 영향:
- `agent/web_search.py:432-443` 안전 폴백 — 의도된 off 시 정상 작동
- `utils/forced_queries.py:217` — `FORCED_QUERY_ENFORCE_GATEKEEP and GATE_KEEP_SOURCES and ALLOWED_DOMAINS` 조건 부정합 → forced queries gating 무력화 (의도 부합)

### 4-c. γ off 시 fallback quality 신호

| 신호 | 위치 | 동작 |
|---|---|---|
| **dedup** | `tools/web_rag/search.py:1825` `_canon_and_dedupe` | URL canonicalize + 추적 파라미터/fragment 제거 + 모바일 접기 |
| **HTTP probe (non-2xx drop)** | `tools/web_rag/search.py:1854` `_filter_non_2xx` | timeout=`WEB_FETCH_PROBE_TIMEOUT` (default 6s), limit=`WEB_FETCH_PROBE_LIMIT` (default topn=40) |
| **intermediate news block** | `tools/web_rag/search.py:1856` `normalize_or_block_intermediate_news` | 뉴스 aggregator redirect 차단 |
| **권위/잡음 rerank** | `agent/web_search.py:914-963` | LLM-free deterministic rerank (A2 § 4-g 박제 — schema 통일 후 dedup/rerank 결정성 ✓) |
| **YEAR_FLOOR** | (search.py 별 위치 — 본 audit scope 외) | 2019 미만 게시물 컷 |
| **content-type pretag** | `tools/web_rag/search.py:1826` `_pretag_content_type` | PDF/HTML annotation (drop 없음, downstream 활용용) |

**충분성 평가**:
- dedup + HTTP probe + intermediate news block + rerank 의 4단 fallback 은 **URL-quality 신호 위주** — content-quality (예: SEO spam, AI generated) 신호 부재.
- gate off 후 retrieval 단계에서 `FILTER_BAD_DOMAINS` (현재 빈 값) 가 noise filter 역할 — README-dev.md:344,351,555 의 precedent 정합 (height-growth-supplement 토픽 100% 오염 사례) → **gate off 시 운영 노이즈 회귀 위험** ★★★.
- γ default off 운영은 **README-dev.md:556 "토픽 .env 에 GATE_KEEP_SOURCES=1 명시 의무화 검토" 와 반대 방향** — 정책 충돌 위험.

### 4-d. γ default 후보 (W Step B 결정 영역)

| 후보 | 운영 시나리오 | 위험 |
|---|---|---|
| (a) **on 유지 + 토픽 opt-out** | 일반 토픽 default gate on, EN/광고 토픽만 `GATE_KEEP_SOURCES=0` | ★ 토픽별 opt-out 명시 의무화 (README-dev 정합) |
| (b) **off 유지 + 토픽 opt-in** | 기본 off, 보안 민감 토픽만 `GATE_KEEP_SOURCES=1` | ★★★ height-growth-supplement 사례 회귀 위험 |
| (c) **on 유지 + ALLOWED_DOMAINS_EXTRA 토픽별** | gate 유지하고 base+extra 양축 — γ 도입 불요 | (β 단독 안 — γ 부재 시) |

────────────────────────────────────────────────

## § 5. Task 5 — β+γ 설계 input 종합 + W Step B 진입 valid 조건

### 5-a. β layered 설계 input

**base list 최종 후보 (양축)**:

KR 축 (현 .env:213 → `_BASE_ALLOWED_DOMAINS` 후보):
- 정부/공공/규제 (15): kosis, index.go.kr, data.go.kr, moef, mfds, hira, khidi, krei, scienceon.kisti, repository.kisti, dart.fss, krx, law.go.kr, nabo.go.kr, geumcheon.go.kr, aurum.re.kr, w4.kirs.or.kr
- 의약 매체 core (8 현 base 유지 + 8 보강 후보): pharmstoday, dailymedi, whosaeng, kmpnews, k-health, hidoc, hitnews, medifonews
- 일반 매체 (선택적 — 광고 토픽 base 후보): hankyung, sedaily, mk, chosunbiz, dongascience

EN 축 (현 .env 부재 — β 신규 추가 후보):
- 학술 publisher: nature.com, sciencedirect.com, mdpi.com, springer.com, cell.com, lancet.com, nejm.org, bmj.com, cochranelibrary.com, tandfonline.com
- 학술 portal: pubmed.ncbi.nlm.nih.gov, ncbi.nlm.nih.gov, clinicaltrials.gov
- 가이드: mayoclinic.org, healthline.com (★ 의약 가이드 SEO 평가 필요)
- 보건 기관: nih.gov, cdc.gov, fda.gov, who.int

광고/마케팅 축 (광고대행사 운영 토픽 base 후보):
- KR: kobaco.co.kr, kmac.co.kr, koreabranding.co.kr
- EN: adweek.com, adage.com, marketingweek.com

**topic list 형식 후보**:

| 옵션 | 형식 | 장단점 |
|---|---|---|
| (a) **extend (`ALLOWED_DOMAINS_EXTRA`)** | 기존 글로벌 base + topic union | 코드 변경 0줄, 토픽 env 만 추가. union 으로 글로벌 KR 매체 유지 + topic 보강 — **★★★★★ 권장** |
| (b) **replace (`ALLOWED_DOMAINS`)** | 토픽 env 가 글로벌 list 완전 replace | 토픽 종속 컨트롤 강력. 단 글로벌 base 누락 시 KR 매체 무력화 — **위험** |
| (c) **hybrid (`ALLOWED_DOMAINS_BASE` + `ALLOWED_DOMAINS_TOPIC`)** | 신규 env 명명 + settings_gatekeep.py 보강 | 명시성 ↑, 코드 변경 +1~3줄. 기존 `_EXTRA` 와 동일 의미 — 명명 차별성 외 가치 ↓ |

**load 순서 변경 필요 여부**:
- 현 순서 (글로벌 → provider overlay → topic) 그대로 활용 가능 — β 구현 시 **변경 0**.
- `refresh_gatekeep_cache()` 호출 추가 필요 — 토픽 진입 시 hook (예: `reload_config_inplace` 직후) — **+1줄**.

**코드 변경 영역 정량** (옵션 (a) extend 가정):
- settings_gatekeep.py: 0줄 (기존 L154 `ALLOWED_DOMAINS_EXTRA` 그대로 활용)
- core/config.py: 0줄 (CFG.ALLOWED_DOMAINS 직접 활용 안 함)
- topics/<slug>.env: +1~3줄 (`ALLOWED_DOMAINS_EXTRA=pubmed.ncbi.nlm.nih.gov,nature.com,...`)
- `_BASE_ALLOWED_DOMAINS` 확장 (옵션): 0~20줄 (KR 외 가능성에 따라)
- refresh hook 호출 (옵션): 0~1줄

### 5-b. γ toggle 설계 input

**토픽별 override 가능 여부**: ★★★★★ 완전 가능 (Task 4-b).

**off 시 fallback quality 신호 충분성**: ★★ 보통 — content-quality filter 부재, URL-quality 위주 (Task 4-c).

**default 정책 후보**: 옵션 (a) "on 유지 + 토픽 opt-out" 권장 (README-dev.md:556 정합).

### 5-c. §12-11-4 subdomain fix 통합 영역

- **부재 아님 확인** (Task 1-g) — `ALLOW_SUBDOMAINS=1` 현 .env 정합 + suffix 매칭 loop (settings_gatekeep.py:363-377) 구현됨.
- W Step C 통합 영역 **아님** — 별 sub-track 도 불요.
- 단 README-dev.md:189 의 `FILTER_BAD_DOMAINS` 의 substring 매칭 (agent/web_search.py:619-625) 와 ALLOW_SUBDOMAINS suffix 매칭의 **비대칭** 박제는 별 track 후보 (W cycle scope 외).

### 5-d. W Step B 진입 valid 조건

| 조건 | 평가 |
|---|---|
| 본 Step A 박제 정합 | ✓ (Task 1~5 모두 완료 + line ref 정밀) |
| Phase 2 Task 4.5 drop location 단언 cross-ref | ✓ (Phase 2 § 5.5-d 정합) |
| read-only 정합 | ✓ (file edit 0, .env 무수정, commit 0, 신규 자산 1) |
| §12-11-4 / §12-11-5 / §12-19 precedent cross-ref | ✓ (§ 1-g + § 3-a + § 4-d) |
| 사용자 결정 영역 정리 | 4건 (아래) |

**W Step B 진입 시 해소 필요 사용자 결정 영역**:

1. **base list 최종 도메인 set**:
   - KR base 의 (`_BASE_ALLOWED_DOMAINS` 하드코드 확장 vs `.env:213` 만 보강)
   - EN 학술 base 후보 set 확정 (publisher / portal / 가이드 / 보건 기관 — 각 카테고리에서 선별 도메인)
   - 광고/마케팅 base 후보 set 확정 (광고대행사 토픽 적용 여부)

2. **topic list 형식**:
   - (a) `ALLOWED_DOMAINS_EXTRA` (extend) — **★★★★★ 권장 (코드 변경 0줄)**
   - (b) `ALLOWED_DOMAINS` (replace)
   - (c) `ALLOWED_DOMAINS_BASE` + `ALLOWED_DOMAINS_TOPIC` (hybrid)

3. **γ toggle default**:
   - (a) **on 유지 + 토픽 opt-out** — **★★★★★ 권장 (README-dev.md:556 정합)**
   - (b) off 유지 + 토픽 opt-in
   - (c) γ 도입 불요 (β 단독)

4. **scope 통합 vs 분리**:
   - (a) β + γ 동시 도입 (W Step B 1-cycle)
   - (b) β 우선 → 운영 관찰 후 γ 별 cycle
   - subdomain fix 통합 여부: **부재 아님 — 통합 불요** (§ 5-c)

────────────────────────────────────────────────

## § 6. STOP 정합 (W Step A 한정)

- file edit 시도: 0 ✓
- 실행 (driver call / 측정) 시도: 0 ✓
- 추정 단언 (line ref 없이): 0 ✓ — 모든 단언 line ref 동반 (settings_gatekeep.py / search.py / core/config.py / `.env:213` / agent/web_search.py / utils.py / utils/forced_queries.py)
- axis-ambiguous word 사용 시 axis 명시 누락: 0 ✓ — "drop", "filter", "allowed", "match" 등 사용 시 axis (search-stage / index-stage / disk / git / convention) 명시
- API key / sensitive .env 값 박제: 0 ✓ — 도메인 list 만 박제, FILTER_BAD_DOMAINS commented 값도 raw 노출 회피
- NDA-bound URL 박제: 0 ✓ — `.env:213` 의 도메인 list 는 광고대행사 운영 토픽 라이브러리 기준 공개 영역

────────────────────────────────────────────────

## § 7. precedent cross-ref 정리

| precedent | 본 Step A 정합 위치 |
|---|---|
| §14-9 Step A (read-only audit 패턴) | 본 자산 전체 구조 |
| §14-9 Step A2 (정정 reference 부록 패턴) | Phase 1/2 박제 cross-ref 명시 |
| §14-9-A1 (axis-separated audit) | § 1-g (subdomain stripping axis), § 2-c (raw JSON axis vs disk axis) |
| §12-11-4 (subdomain stripping 박제) | § 1-g — 부재 아님 확인 |
| §12-11-5 (화이트리스트 확장 시도 실패) | § 5-d — base list 후보 확정 시 cross-ref 필요 |
| §12-19 (per-topic env override 패턴) | § 3-a/b/c — load 순서 + override mechanics |
| §14-8-B fix O (driver intent snapshot) | § 3-b — _PROTECTED_ENV_KEYS 정합 |
| README-dev.md:189-190 (GATE_KEEP_SOURCES + ALLOWED_DOMAINS) | § 1-e + § 5-d |
| README-dev.md:344,351 (FILTER_BAD_DOMAINS 후보 도메인) | § 1-f |
| README-dev.md:555-556 (height-growth-supplement 토픽 100% 오염) | § 4-c, § 5-b (γ default 정책) |
| Phase 2 § 5.5-d (Q4 drop location) | § 1-a + § 2-c |
| Phase 2 § 6-d (fundamental cause) | § 2-e |

────────────────────────────────────────────────

## § 8. W Step B entry 준비 — 사용자 컨펌 대기 영역

본 Step A 박제 완료 → **W Step B (β+γ 설계 확정 + topic env patch 안)** 진입 valid.

사용자 결정 필요 (§ 5-d 의 4건):

1. base list 최종 도메인 set (KR 확장 + EN 학술 추가 + 광고/마케팅 추가)
2. topic list 형식 (extend / replace / hybrid)
3. γ toggle default (on opt-out / off opt-in / γ 불요)
4. scope 통합 (β+γ 1-cycle vs β 우선 후 γ 별 cycle)

본 자산은 read-only audit — production code / .env / 박제 file 무수정. W Step B 진입 시 사용자 결정 영역 해소 후 patch design + dry-run 진입.
