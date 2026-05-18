# §14-9-W Step B — β layered + γ toggle 설계 (gap 보강 + design 박제)

## 본 mission 박제

- entry: §14-9-W Step A close (`3b2ebae` 후 working tree audit 박제 완료, untracked)
- W cycle 구조: Step A (진단, 완료) → **Step B (설계, 본 task)** → Step C (구현 + 측정)
- 4 결정 박제 (Step A 결과 + 사용자 컨펌 완료):
  - 결정 1: base list = KR 58 (현 .env 유지) + EN 학술 10 + 광고-마케팅 9 = **77 도메인**
  - 결정 2: topic list = (a) `ALLOWED_DOMAINS_EXTRA` extend (코드 변경 0)
  - 결정 3: γ toggle = (a) on opt-out + Finding C risk 명시 박제
  - 결정 4: scope = (a) β + γ 1-cycle
- Gap 1+2 (Step A 미박제): Task 0 흡수 (사용자 (Y) 결정)
- 향후 content-quality filter 보강 = 별 트랙 candidates 박제 (Step B 산출)

## Pre-condition 박제

| 항목 | 값 |
|---|---|
| branch | `main` |
| HEAD | `3b2ebae` (Phase 2 close commit β) |
| Step A 박제 file | `scripts/output/§14-9-W/step_a_whitelist_diagnosis.md` (untracked, 513 lines) |
| working dir | `D:\GPT_AGENT\writer_project` |
| 산출 변경 | read-only — file edit / commit 0, 신규 박제 자산 1개 (`step_b_layered_gate_design.md`) |

────────────────────────────────────────────────

## § 0. Task 0 — Gap 1+2 보강 진단 (read-only)

### 0-a. Gap 1 — 3-source 도메인 결합 mechanics

**`get_allowed_domains()` 본문** (`settings_gatekeep.py:138-155`):

```python
def get_allowed_domains() -> Set[str]:
    """런타임 주입 > CFG > ENV 순으로 허용 도메인 해석."""
    if _RUNTIME_ALLOWED:                                          # L140
        return _RUNTIME_ALLOWED                                   # ← runtime 단독 반환
    out: Set[str] = set(x.strip().lower()                         # L142
                        for x in _BASE_ALLOWED_DOMAINS)           # ← source 1: hardcode 17
    try:
        raw = _get_cfg_attr("ALLOWED_DOMAINS", None)              # L145: source 2a (CFG)
        if isinstance(raw, (set, list, tuple)):
            out |= {str(x).strip().lower()                        # L147: union
                    for x in raw if str(x).strip()}
        elif isinstance(raw, str) and raw.strip():
            out |= _as_set(raw)                                   # L149: union
    except Exception:
        pass
    out |= _as_set(os.getenv("ALLOWED_DOMAINS", ""))              # L153: source 2b (ENV direct)
    out |= _as_set(os.getenv("ALLOWED_DOMAINS_EXTRA", ""))        # L154: source 3 (EXTRA)
    return out
```

**결합 알고리즘 단언**:

```
runtime_override 존재 시:
  result = _RUNTIME_ALLOWED                                 # 단독 (다른 source 무시)
else:
  result = _BASE_ALLOWED_DOMAINS                            # source 1 (hardcode)
         ∪ CFG.ALLOWED_DOMAINS                              # source 2a (CFG attr — 빌드 시 ENV 에서 split)
         ∪ os.getenv("ALLOWED_DOMAINS")                     # source 2b (ENV direct dynamic read)
         ∪ os.getenv("ALLOWED_DOMAINS_EXTRA")               # source 3 (extend slot)
```

**4-way union** — 모두 set `|=` 병합, 우선순위 부재 (set 의 특성 — 중복은 자동 제거).

**중요 관찰**:
- CFG (source 2a) 와 ENV direct (source 2b) 의 ALLOWED_DOMAINS 는 **같은 ENV 값에서 빌드** — CFG 는 `_build_config()` (core/config.py:507) 시점 1회 snapshot, ENV direct 는 `get_allowed_domains()` 호출마다 dynamic read.
- 토픽 env load 후 `reload_config_inplace()` 미호출 시 CFG snapshot 은 stale, **ENV direct 는 즉시 반영** (settings_gatekeep.py:153 `os.getenv` dynamic).
- 즉 **β 의 `ALLOWED_DOMAINS_EXTRA` 도 `os.getenv()` direct read 라 reload 불필요** (cache invalidation 만 필요).

### 0-b. Gap 1 단언 — 추가 위치 결정 input

| 추가 위치 | 효과 | 코드 변경 | 운영 친화 |
|---|---|---|---|
| **(A) `.env:213 ALLOWED_DOMAINS` 확장** | source 2a + 2b 양쪽에 자동 반영 (CFG 빌드 + ENV direct) | 0 줄 | ★★★★★ — config-only |
| (B) `_BASE_ALLOWED_DOMAINS` (settings_gatekeep.py:45-66) 확장 | source 1 union — 모든 토픽 강제 적용 | +10~20 줄 | ★★ — 코드 commit 필요, 토픽 opt-out 불가 |
| (C) topic env `ALLOWED_DOMAINS_EXTRA` | source 3 union — 토픽 한정 | 0 줄 (env-only) | ★★★★★ — topic-only |

**Step B 결정 1 (base 77 확장) → (A) `.env` 확장 권장**. EN/광고 base 가 글로벌 적용 의도 (`.env` 가 운영 default) 정합. (B) 코드 union 은 토픽 opt-out 차단 → γ off 시에도 base 강제 — 의도 mismatch.

### 0-c. Gap 2 — `refresh_gatekeep_cache` 호출 위치 전수 grep

```bash
grep -rn "refresh_gatekeep_cache" --include="*.py"
```

결과 5 hits (test/박제 file 제외):

| # | 위치 | axis | 시점 |
|---:|---|---|---|
| 1 | `settings_gatekeep.py:128` | (선언) | `def refresh_gatekeep_cache()` 본문 |
| 2 | `agent/web_search.py:35-38` | **module-load** | `import settings_gatekeep` 시 1회 (`if _refresh_gk_cache is not None: _refresh_gk_cache()`) |
| 3 | `tools/web_rag/search.py:275-276` | **module-load** | import 시 1회 |
| 4 | `app.py:2287-2288` | **startup (driver-mode)** | CLI args 처리 + `config.CFG = config.reload_config()` 직후 |
| 5 | `tools/web_rag/search.py:1368-1369` | **request-time** | `web_search()` 함수 진입 시 `reload_config()` 직후 |

### 0-d. Gap 2 단언 — 토픽 switch 보장 영역

**호출 시점 axis 별 보장 영역**:

| axis | 보장 영역 | 미보장 영역 |
|---|---|---|
| module-load (#2,#3) | 모듈 import 1회 — startup 시 .env 반영 | ⚠ 이후 .env / topic env 변경 미반영 |
| startup driver-mode (#4) | `app.py` CLI 진입점에서 토픽 args 반영 후 1회 | ⚠ driver 미경유 진입점 (예: pytest, script 직접 실행) |
| **request-time (#5)** | `web_search()` 호출마다 `reload_config()` + refresh — **토픽 switch 보장** | ⚠ web_search() 외 진입점 (예: forced_queries.py:217, vector_search.py 단독 호출) |

**reload_config_inplace 내부 호출 부재 단언** (core/config.py:663-688):
- `_apply_provider_overlay` + `_apply_topic_preset` 후 `_build_config()` 만 호출, **refresh_gatekeep_cache 호출 없음** ⚠
- 즉 토픽 env load 후 `reload_config()` 만 부르면 CFG 는 갱신되나 settings_gatekeep `_normalized_allowed_domains` cache 는 stale 유지

### 0-e. Gap 2 단언 — β + γ 실작동 가능 여부

| 시나리오 | refresh 보장? | 실작동? |
|---|---|---|
| **web_search() 통상 호출** (driver 또는 app.py 경유) | ✓ search.py:1368 request-time refresh | ✓ **β + γ 즉시 반영** |
| forced_queries.py 단독 호출 | ✗ (search.py:1368 미경유) | ⚠ stale cache 시 base 만 적용 — topic EXTRA 무시 가능 |
| pytest 환경 (import-only) | ✓ module-load #2/#3 | ✓ test fixture 의 env 변경 후 refresh 미호출 시 stale |
| reload_config_inplace 단독 호출 후 | ✗ (refresh 호출 없음) | ⚠ cache stale, gate 판정 stale set 사용 |

**Step C 권장 (defensive)**:
- **reload_config_inplace 내부에 `refresh_gatekeep_cache()` 호출 추가** (core/config.py:684 `_apply_topic_preset(verbose=False)` 직후) — **+1줄 (try/except)**
- 또는 외부 호출처가 항상 reload + refresh 쌍으로 호출하도록 보장 (현 search.py:1366-1369 패턴)
- 권장: **양쪽 모두** (defensive + 호출처 책임 명시)

### 0-f. Gap 결과 → Task 1 추가 위치 결정 input

- 결정 1 (base 77 확장) 추가 위치 = **(A) `.env:213 ALLOWED_DOMAINS` 확장** 확정 (코드 변경 0줄)
- Step C 의 cache refresh hook = **`reload_config_inplace` 내부 1줄 추가** (defensive, β + γ 모든 경로 보장)

────────────────────────────────────────────────

## § 1. Task 1 — base list 최종 박제 + 추가 위치 결정

### 1-a. 추가 위치 단언 (Task 0 결과)

- **`.env:213 ALLOWED_DOMAINS` 확장** (옵션 A) 확정
- `_BASE_ALLOWED_DOMAINS` (옵션 B) **미채택** — 토픽 opt-out 차단 회피
- 코드 변경: 0 줄 (Step C 의 .env 1줄 patch + cache refresh hook 1줄)

### 1-b. base 도메인 최종 set 박제 (사용자 컨펌 set, 77 도메인)

#### KR base 58 (현 `.env:213` 유지, 변경 없음)

(Step A § 2-a dump 정합 — KR pharma/news/gov/광고 미포함/기타)

#### EN 학술 추가 10

| # | 도메인 | 카테고리 | 비고 |
|---:|---|---|---|
| 1 | `pubmed.ncbi.nlm.nih.gov` | NIH portal | Phase 2 Q4 (benfotiamine clinical trial) 1순위 통과 후보 |
| 2 | `ncbi.nlm.nih.gov` | NIH portal | PMC full-text 포함 |
| 3 | `nih.gov` | US 보건 기관 | NHLBI/NIDDK 등 산하 subdomain 자동 (ALLOW_SUBDOMAINS=1 정합) |
| 4 | `who.int` | WHO | 글로벌 가이드라인 |
| 5 | `mayoclinic.org` | 의약 가이드 | 환자/임상 가이드 |
| 6 | `medlineplus.gov` | US 정부 환자 정보 | NIH 공식 환자 포털 |
| 7 | `cochrane.org` | 학술 review | Cochrane systematic review |
| 8 | `nejm.org` | publisher | New England Journal of Medicine |
| 9 | `bmj.com` | publisher | British Medical Journal |
| 10 | `nature.com` | publisher | Nature publishing group |

**11번째 후보 (보류)**: `sciencedirect.com` — Elsevier portal, 사용자 선호 시 Step C 진입 전 확정 추가.

#### 광고-마케팅 추가 9

| # | 도메인 | 카테고리 | 비고 |
|---:|---|---|---|
| 1 | `kobaco.co.kr` | KR 공공 | 한국방송광고진흥공사 |
| 2 | `kaa.or.kr` | KR 협회 | 한국광고주협회 |
| 3 | `adic.or.kr` | KR 협회 | 한국광고총연합회 |
| 4 | `ad.co.kr` | KR 매체 | 광고정보센터 |
| 5 | `m-i.kr` | KR 매체 | 매드타임스 |
| 6 | `brandbrief.co.kr` | KR 매체 | 브랜드브리프 |
| 7 | `mobiinside.co.kr` | KR 매체 | 모비인사이드 |
| 8 | `ana.net` | EN 협회 | Association of National Advertisers |
| 9 | `iab.com` | EN 협회 | Interactive Advertising Bureau |

**합산 검산**: 58 (KR) + 10 (EN 학술) + 9 (광고) = **77 도메인** ✓

#### ALLOW_SUBDOMAINS=1 자동 매칭 검증

(settings_gatekeep.py:363-377 suffix loop)

- `pubmed.ncbi.nlm.nih.gov` base 등록 시 자동 매칭: `*.pubmed.ncbi.nlm.nih.gov` (서브도메인) — but PubMed 본 도메인은 sub 가 거의 없음. 효과 ★★
- `nih.gov` base 등록 시 자동 매칭: `nhlbi.nih.gov`, `niddk.nih.gov`, `nlm.nih.gov`, `pubmed.ncbi.nlm.nih.gov` 등 NIH 산하 전부. **★★★★★ 광역 효과**
- `ana.net` base 등록 시 자동 매칭: `*.ana.net` (서브도메인 한정, ana.net 본체 사이트). 효과 ★★

→ `nih.gov` + `pubmed.ncbi.nlm.nih.gov` 양쪽 박제는 **suffix loop 정합 redundant** — Step C 진입 전 정리 검토 영역. 단 명시성 위해 양쪽 유지 권장 (운영 가독성 ↑).

### 1-c. `.env` update 박제

`.env:213` 현 syntax (실측, settings_gatekeep.py:208 `URL_TREAT_WWW_EQUIV=1` overlay 적용 후):

```
ALLOWED_DOMAINS=dailypharm.com,medipana.com,kpanews.co.kr,pharmnews.com,yakup.com,medicopharma.co.kr,hitnews.co.kr,medifonews.com,pharmstoday.com,dailymedi.com,whosaeng.com,kmpnews.co.kr,k-health.com,hidoc.co.kr,newsis.com,healtho.co.kr,consumernews.co.kr,ckdpharm.com,chongkundang.com,hankyung.com,sedaily.com,mk.co.kr,hankyoreh.com,chosunbiz.com,asiatoday.co.kr,mediapen.com,dongascience.com,nspna.com,edaily.co.kr,betanews.net,goodkyung.com,weekly.hankooki.com,kosis.kr,index.go.kr,data.go.kr,moef.go.kr,mfds.go.kr,hira.or.kr,khidi.or.kr,krei.re.kr,scienceon.kisti.re.kr,repository.kisti.re.kr,dart.fss.or.kr,krx.co.kr,law.go.kr,lkp.news,news.naver.com,m.news.naver.com,search.naver.com,naver.com, securities.miraeasset.com,boryung.co.kr,w4.kirs.or.kr,ssl.pstatic.net,dez1irdmysogu.cloudfront.net,nabo.go.kr,geumcheon.go.kr,aurum.re.kr
```

**syntax 특징**:
- comma-separated single line (전체 1줄)
- `securities.miraeasset.com` 앞 한 칸 공백 1개 — `_as_set()` (settings_gatekeep.py:113-124) 의 `.strip()` 으로 자동 제거 정합
- 줄바꿈 없음 (line continuation 미사용)

**Step C 진입 시 patch 형태 (단언)**:

```diff
- ALLOWED_DOMAINS=dailypharm.com,...,aurum.re.kr
+ ALLOWED_DOMAINS=dailypharm.com,...,aurum.re.kr,pubmed.ncbi.nlm.nih.gov,ncbi.nlm.nih.gov,nih.gov,who.int,mayoclinic.org,medlineplus.gov,cochrane.org,nejm.org,bmj.com,nature.com,kobaco.co.kr,kaa.or.kr,adic.or.kr,ad.co.kr,m-i.kr,brandbrief.co.kr,mobiinside.co.kr,ana.net,iab.com
```

(append 단일 diff — 1 line modification, 19 entries 추가)

────────────────────────────────────────────────

## § 2. Task 2 — `ALLOWED_DOMAINS_EXTRA` extend mechanism 설계

### 2-a. usage pattern 박제

**topic env (`topics/<slug>.env`) 활용 형식**:

```sh
# topics/<slug>.env 마지막 부분에 추가
ALLOWED_DOMAINS_EXTRA=domain1.com,domain2.kr,subdomain.example.org
```

**load flow** (Step A § 3-a 정합):

```
1) load_dotenv(.env, override=False)                  → ALLOWED_DOMAINS set (글로벌 base 77)
2) _apply_provider_overlay(.env.<provider>, True)     → provider 별 overlay (보통 LLM/API 만)
3) _apply_topic_preset(topics/<slug>.env, True)       → ALLOWED_DOMAINS_EXTRA set (토픽 추가)
```

**최종 allowed set** (settings_gatekeep.get_allowed_domains() 결합):

```
allowed = _BASE_ALLOWED_DOMAINS (17 hardcode)
        ∪ os.getenv("ALLOWED_DOMAINS") (글로벌 base 77)
        ∪ os.getenv("ALLOWED_DOMAINS_EXTRA") (토픽 추가)
        = base 77 + 토픽 추가 (hardcode 17 은 77 의 subset → 추가 효과 없음)
```

### 2-b. 토픽별 EXTRA 권장 박제 (예시, 본 cycle 결정 안 함)

| 토픽 | base 77 충분? | EXTRA 후보 | 비고 |
|---|---|---|---|
| **venfobel-vitamin** | ✓ | (없음) | 운영 default — NDA-bound, base 77 (EN 학술 + KR pharma) 정합 |
| **ai-generated-creative-ad-platforms** (광고 토픽) | ⚠ AI/tech 매체 부족 | techcrunch.com, theverge.com, wired.com, venturebeat.com, marketingdive.com | 광고-AI 교차 영역 |
| **height-growth-supplement** | ⚠ 건강 일반 매체 부족 | hidoc.co.kr (이미 포함), nutristore.com, examine.com | examine.com 은 SEO 평가 필요 |

본 cycle 결정 안 함 — Step C 측정 후 또는 토픽 진입 시점 확정 박제.

### 2-c. backward compatibility 단언

- `ALLOWED_DOMAINS_EXTRA` 미설정 시 `os.getenv("ALLOWED_DOMAINS_EXTRA", "")` → 빈 문자열 → `_as_set("")` → 빈 set → union 변동 0
- 기존 토픽 영향 0 (venfobel-vitamin 외 모든 토픽 동일)
- 글로벌 base 만 사용하는 토픽도 영향 없음

────────────────────────────────────────────────

## § 3. Task 3 — γ toggle 설계 + risk 박제 + content-quality 후속 candidates

### 3-a. default + opt-out 패턴

- **default**: `GATE_KEEP_SOURCES=1` (현 `.env:207` 유지)
- **opt-out 방식**: topic env 의 `GATE_KEEP_SOURCES=0` 한 줄

**topic env 예시 (opt-out 토픽)**:

```sh
# topics/<en-academic-explore-topic>.env
# ────── §14-9-W γ toggle opt-out ──────
# 본 토픽은 EN 학술 base 외 도메인 (예: 학술 publisher 분산) 활용 필요 →
# gate off + content-quality fallback (URL-level dedup + HTTP probe + rerank) 위주 운영.
GATE_KEEP_SOURCES=0
```

**메커니즘** (Step A § 4-b 정합):
- settings_gatekeep.py:209 `gatekeep_enabled() = _flag("GATE_KEEP_SOURCES", False)` dynamic CFG.truthy → ENV
- 토픽 env override=True load 후 `os.environ["GATE_KEEP_SOURCES"]="0"` 설정 → 다음 `is_allowed_url()` 호출 시 즉시 early `return True` (L334-335)
- cache 영향 없음 (gate flag 는 cache 미사용, allowed set cache 만 `_normalized_allowed_domains` lru)

### 3-b. ⚠ γ off 시 risk 박제 (Finding C 정합)

**(Finding C, Step A § 4-c 정합)**:

| 신호 | 작동 | 한계 |
|---|---|---|
| dedup (`_canon_and_dedupe`, search.py:1825) | ★ URL-level 정규화 + 중복 제거 | 본문 quality 평가 부재 |
| HTTP probe (`_filter_non_2xx`, search.py:1854) | ★ HTTP status code (200~299 만) | 200 OK 의 SEO spam page 통과 |
| intermediate news block (`normalize_or_block_intermediate_news`, search.py:1856) | ★ aggregator redirect 차단 | content 자체 noise 차단 못함 |
| 권위/잡음 rerank (web_search.py:914-963) | ★ deterministic 순서 | content quality 평가 아님 — 순위만 |
| YEAR_FLOOR | ★ 시간 기반 (2019 미만 컷) | recent SEO spam 통과 |

**노이즈 콘텐츠 risk** ★★★:
- gate off 시 모든 도메인 통과 → forum / 저품질 blog / off-topic page 도 인덱싱 candidates 진입
- README-dev.md:555 height-growth-supplement 토픽 precedent — 100% 오염 (광고 운영 제안서 인덱싱) 사례 회귀 위험

**γ off 적용 권장 영역**:
- ✓ **단발성 explore 토픽** (1-shot research, 폐기 가능)
- ✓ **EN 학술 토픽** (base 77 의 EN 학술 10 외 publisher 분산 필요)
- ✗ **venfobel-vitamin** (NDA-bound, 운영 default) — γ off 신중
- ✗ **장기 운영 토픽 기본 default** — README-dev.md:556 정합 (`GATE_KEEP_SOURCES=1` 명시 의무화)

### 3-c. 향후 content-quality filter 보강 별 트랙 candidates

§14-9-W close 후 별 트랙 또는 catch 박제 후보:

| # | 후보 | 설명 | cost | impact | 우선순위 |
|---:|---|---|---|---|---|
| (1) | **content-language detection** | 토픽 언어 정합 (KR 토픽에 EN 페이지 유입 필터) | 소 (langdetect 라이브러리, ~2MB) | 중 (EN noise 차단 보조) | ★★★ |
| (2) | **content length 하한** | body text 100~500 char 미만 stub page 차단 | 극소 (len check, +5줄) | 중 (SEO stub 차단) | ★★★★ |
| (3) | **LLM-based content quality scorer** | content snippet quality 정성 평가 | 큼 (LLM API cost ~$0.01/query) | 큼 (정확도 ↑) | ★★ (cost 평가 필요) |
| (4) | **readability heuristic** | paragraph / 구조 기반 readability score | 소 (textstat 라이브러리) | 소~중 | ★★ |
| (5) | **ad-hoc deny list 보강 (`FILTER_BAD_DOMAINS`)** | 알려진 저품질 도메인 substring deny | 극소 (config) | 중 | ★★★★ (현재 .env:215 비어 있음 — 즉시 적용 가능) |

**본 cycle 미진입 — 별 트랙 catch 후보로 박제**. § 5-d 에서 catch 명명 부여.

────────────────────────────────────────────────

## § 4. Task 4 — W Step C 측정 plan 박제

### 4-a. measurement objective

| # | objective | scope |
|---:|---|---|
| (i) | **base 확장 효과 정량** | 현 ALLOWED_DOMAINS (58) vs 확장 (77) drop rate 비교 |
| (ii) | **EN 학술 query 활용성** | PubMed/NIH 등 새 base 도메인 실제 검색 결과 통과 정합 |
| (iii) | **광고-마케팅 query 활용성** | KOBACO/KAA 등 새 base 도메인 통과 정합 |
| (iv) | (선택) **ALLOWED_DOMAINS_EXTRA 활용 효과** | 토픽 env EXTRA 추가 시 drop rate 추가 변동 |
| (v) | (선택) **γ off 효과 검증** | EN 학술 토픽에서 GATE_KEEP_SOURCES=0 시 raw_items 차이 |

본 cycle 우선 scope: (i)~(iii). (iv)(v) 는 toggle 검증용 후속.

### 4-b. driver + query set

**driver**: `scripts/§14-9/backend_isolated_smoke.py` (Phase 1+2 재활용, log-capture 필수)
- log-capture 패턴 정합 (Phase 2 § 3-b `_BackendLogHandler` + 5 regex)
- 변경 없음 — driver 그대로 활용 (β + γ 는 .env / topic env 변경만)

**query set (7 query)**:

| Q | text | lang | objective |
|---|---|---|---|
| Q1 | (Phase 2 정합) 벤포벨S 핵심 성분 | KR | baseline regression check |
| Q2 | (Phase 2 정합) 활성형 비타민 | KR | baseline regression check |
| Q3 | (Phase 2 정합) 비타민 B군 | KR | baseline regression check |
| Q4 | (Phase 2 정합) vitamin B benfotiamine clinical trial | EN | **EN 학술 통과 검증 핵심** (Phase 2 100% drop → 회귀 또는 통과 측정) |
| Q5 | benfotiamine clinical trial | EN | **PubMed 단독 검증** (간결 query) |
| Q6 | vitamin B1 pharmacokinetics | EN | **NIH/Cochrane 검증** |
| Q7 | 한국 광고 시장 규모 2026 | KR | **KOBACO/adic 검증** |

**A/B 측정 기준**:
- A: ALLOWED_DOMAINS = 현 58 (Phase 2 baseline)
- B: ALLOWED_DOMAINS = 확장 77 (Step C patch 적용)

A 는 Phase 2 raw JSON 재활용 가능 (Q1-Q4 분), B 는 새 측정. Q5-Q7 은 A 도 새 측정 필요 (Phase 2 미측정).

### 4-c. baseline 데이터

**Phase 2 raw JSON 재활용 가능 자산** (.gitignored):
- `scripts/output/§14-9/phase1_vertexai_grounding_*.json` (vertex_grounding mode)
- `scripts/output/§14-9/phase1_openai_legacy_only_*.json` (Phase 1 (ii))
- `scripts/output/§14-9/phase2_vertexai_legacy_only_*.json` (Phase 2 (iii))
- `scripts/output/§14-9/phase1_anthropic_legacy_only_phase2_20260517_220008.json` (Phase 2 (iv))

**Step C 측정 추가 자산**:
- A 측정 (ALLOWED_DOMAINS=58, Q5-Q7 신규): `scripts/output/§14-9-W/baseline_a_q5_q7_*.json`
- B 측정 (ALLOWED_DOMAINS=77, Q1-Q7 전체): `scripts/output/§14-9-W/extended_b_q1_q7_*.json`

### 4-d. 측정 표준 정합 (§13-7)

| 표준 | 값 | 정합 |
|---|---|---|
| max_retries | 0 | §14-9 Phase 2 정합 |
| warmup | 2 | §13-7 |
| N | 3 | §13-7 |
| timeout | 240s | §14-9 Phase 2 정합 |
| inter-run sleep | 60s | §13-7 (provider quota 방어) |
| PYTHONIOENCODING | utf-8 | encoding 안정성 (`—` 문자 회피 정합) |
| log-capture | enabled | per-backend dist + drop reason 정확 attribution |
| provider | openai (legacy_only) | 기본 — provider 영향 차단 (Phase 2 § 6-b 정합 — legacy chain provider-independent) |

**검증 지표**:
- per_backend_total_log (chain merge log capture)
- post-gatekeep raw_items count (per Q)
- drop rate (= 1 - raw_items / merge_total)
- elapsed_mean / elapsed_cv (regression check, Phase 2 mean 2.04~2.21s 범위)

### 4-e. 예상 결과 단언 (가설 — 실측 후 검증)

| Q | base 58 (A) raw mean | base 77 (B) raw mean | 가설 |
|---|---:|---:|---|
| Q1 | ~1.5 (Phase 2 정합) | ~1.5 | KR 토픽 — 변동 없음 (회귀 0) |
| Q2 | ~1.0 | ~1.0 | KR — 변동 없음 |
| Q3 | ~3.5 | ~3.5 | KR — 변동 없음 |
| Q4 | **0** (Phase 2 정합) | **3~5** | **EN 학술 통과 — primary objective** |
| Q5 | 0 (예상) | 3~5 | EN 학술 통과 |
| Q6 | 0 (예상) | 1~3 | EN 학술 + Cochrane 통과 |
| Q7 | ~1 (예상, KR news 일부) | ~3~5 | 광고 매체 통과 |

**가설 미충족 시 진단 영역**:
- Q4 raw=0 유지 시 — naver_direct / tavily 가 base 77 의 EN 학술 도메인 실제 반환 못함 (search engine 자체 한계) → § 3-a content-quality filter / γ off 검토 영역
- elapsed regression (>20% drift) — base 확장이 `_filter_non_2xx` 또는 dedup 성능 영향 (lru cache miss) → measurement noise 분리 필요

────────────────────────────────────────────────

## § 5. Task 5 — W Step C 진입 valid 단언 + cleanup

### 5-a. Step C 의 구체 task list 박제

본 Step B 산출 기반으로 Step C 가 수행할 작업:

| # | task | scope | 영향 file |
|---:|---|---|---|
| 1 | **`.env:213` patch** — ALLOWED_DOMAINS 확장 (58 → 77) | config | `.env` (1 line modification, append 19 entries) |
| 2 | **`refresh_gatekeep_cache` hook 추가** (Gap 2 defensive) | 코드 | `core/config.py:684` `_apply_topic_preset` 직후 (+1줄 try/except) |
| 3 | **topic env template docs** — venfobel-vitamin / 광고 토픽 1 case 예시 | docs | `topics/<slug>.env` 또는 README 부록 |
| 4 | **README §12-11-4 update** — subdomain stripping 이미 fix 박제 update | docs | `README-dev.md` (§12-11-4 entry) |
| 5 | **측정 실행** — § 4 plan 정합 (A + B 측정) | driver | `scripts/§14-9/backend_isolated_smoke.py` 재활용 |
| 6 | **결과 박제** — Step C 산출 자산 | docs | `scripts/output/§14-9-W/step_c_layered_gate_implementation.md` |
| 7 | **commit** | git | `§14-9-W Step C — β layered + γ toggle 구현 + base 확장 (58→77) 측정` |

### 5-b. Step C scope 확정 단언

| 영역 | 변경 영역 | line 추정 |
|---|---|---|
| **production code 변경** | `core/config.py:684` (refresh hook, +1줄 try/except) | +5 줄 (try/except/import block) |
| **config 변경** | `.env:213` (58 → 77 도메인) | 1 line modification |
| **docs 변경** | README + topic env template (선택) | +20~50 줄 (§12-11-4 update + topic template 부록) |
| **driver 사용** | `backend_isolated_smoke.py` 재활용 — patch 0 | 0 |

총 코드 변경 영역: **≤ 5 줄 production + 1 line config + 20~50 줄 docs**.

### 5-c. §12-11-4 README update 권장 (mini-task 후보)

Step A § 1-g + § 5-c Finding B 정합:
- **현 README-dev.md §12-11-4 박제**: "호스트 정규화 누락 — `oldm.dailypharm.com` 등 subdomain 처리 부재" (미해결)
- **update 단언**: "§14-9-W Step A 박제로 fix 확인 — `settings_gatekeep.py:208` `ALLOW_SUBDOMAINS=1` + suffix loop (settings_gatekeep.py:363-377). Step A § 1-g cross-ref."
- update 위치: README-dev.md §12-11-4 entry 내부 (status: `closed (2026-05-18 §14-9-W Step A audit 정합)` 추가)

**Step C 첫 동작 또는 별 cleanup cycle** — Step C task #4 정합.

### 5-d. content-quality 후속 트랙 catch 박제 (§ 3-c 정합)

§14-9-W close 후 catch 박제 후보 (별 cycle 진입 결정 사용자 영역):

| catch # | 후보 | 우선순위 | cost | impact |
|---:|---|---|---|---|
| catch ad-1 | **content-language detection** (langdetect) | ★★★ | 소 | 중 |
| catch ad-2 | **content length 하한** (body text 100~500 char 컷) | ★★★★ | 극소 | 중 |
| catch ad-3 | **LLM-based content quality scorer** | ★★ | 큼 ($0.01/query) | 큼 |
| catch ad-4 | **readability heuristic** (textstat) | ★★ | 소 | 소~중 |
| catch ad-5 | **ad-hoc deny list 보강 (FILTER_BAD_DOMAINS)** | ★★★★ | 극소 | 중 |

**우선순위 정합 — 첫 진입 권장 순서**:
1. catch ad-5 (`FILTER_BAD_DOMAINS` 보강) — 현 `.env:215` 비어 있음, .env:217 commented out 의 후보 도메인 (gminsights / fortunebusinessinsights / mordorintelligence 등 SEO 시장 리포트) 즉시 적용 가능
2. catch ad-2 (content length 하한) — production code patch 극소
3. catch ad-1 (language detection) — 라이브러리 추가 필요
4. catch ad-4 (readability) — 효과 평가 후
5. catch ad-3 (LLM scorer) — cost/impact 정량 평가 후

각 catch 의 § / catch 명명은 W Step C close 후 별 cycle 진입 시 사용자 확정 영역.

### 5-e. Step C 진입 valid 조건 단언

| 조건 | 평가 |
|---|---|
| 본 Step B 박제 정합 | ✓ (Task 0~5 모두 완료 + line ref 정밀) |
| Step A 박제 cross-ref | ✓ (Finding A/B/C/D — § 0, § 1-c, § 3-b, § 5-c) |
| Phase 2 Task 4.5 박제 cross-ref | ✓ (§ 4-a/c/d/e + § 0-d) |
| read-only 정합 | ✓ (file edit 0, .env 무수정, commit 0, 신규 자산 1) |
| 사용자 결정 4건 완료 | ✓ (base list + topic 형식 + γ default + scope) |
| Step C scope 확정 | ✓ (§ 5-b — ≤ 5줄 production + 1줄 config + 20~50줄 docs) |
| 측정 plan 박제 | ✓ (§ 4 — driver / query / baseline / 표준) |

→ **Step C 진입 valid**.

────────────────────────────────────────────────

## § 6. STOP 정합 (W Step B 한정)

- file edit 시도: 0 ✓
- 실행 (driver call / 측정) 시도: 0 ✓
- 추정 단언 (line ref 없이): 0 ✓ — 모든 단언 line ref 동반
- axis-ambiguous 명시 누락: 0 ✓ — drop / filter / cache / config / runtime axis 모두 명시
- 도메인 list dump 시 PII / NDA-bound URL: 0 ✓ — 공개 도메인만 (PubMed/NIH/KOBACO 등)
- 도메인 list 변경 / 추가 / 삭제 (Task 1-b 사용자 컨펌 set 외): 0 ✓ — 77 set 정확 정합
- 자율적 Step C 진입 시도: 0 ✓ — 본 Step B 는 설계만, Step C 진입 valid 조건 박제로 종결

────────────────────────────────────────────────

## § 7. precedent cross-ref 정리

| precedent | 본 Step B 정합 위치 |
|---|---|
| W Step A Finding A (`_BASE_ALLOWED_DOMAINS` + `ALLOWED_DOMAINS_EXTRA` 슬롯) | § 0-a, § 1-a, § 2-a |
| W Step A Finding B (`ALLOW_SUBDOMAINS=1` 정합, §12-11-4 부재 아님) | § 1-b/SUBDOMAINS, § 5-c |
| W Step A Finding C (γ off 시 content-quality fallback URL-only) | § 3-b, § 3-c |
| W Step A Finding D (refresh_gatekeep_cache 호출 사이트 4) | § 0-c/d/e |
| §14-9 Phase 2 Task 4.5 (search.py:1827-1844 primary drop) | § 4-a, § 4-e |
| §14-9 Phase 2 § 6-b (legacy chain provider-independent) | § 4-d (provider 영향 차단) |
| §14-9 Phase 2 § 6-d (fundamental cause = KR-centric base + GATE on) | § 1-b, § 4-a |
| §14-8-B fix O (`_PROTECTED_ENV_KEYS` snapshot/restore) | § 0-c (axis #4) |
| §13-7 (측정 표준) | § 4-d |
| §12-19 (per-topic env override) | § 0-a (load flow), § 2-a |
| §12-11-4 (subdomain stripping — closed 정합) | § 5-c (README update 권장) |
| §12-11-5 (화이트리스트 확장 시도 실패 precedent) | § 1-b (base 77 확장 — 측정 검증 valid 후 commit) |
| README-dev.md:555-556 (height-growth-supplement 100% 오염) | § 3-b (γ off 적용 신중) |
| README-dev.md:344,351 (`FILTER_BAD_DOMAINS` 후보 도메인) | § 5-d catch ad-5 |

────────────────────────────────────────────────

## § 8. W Step C entry 준비 — 사용자 컨펌 대기 영역

본 Step B 박제 완료 → **W Step C (β layered + γ toggle 구현 + 측정)** 진입 valid.

**진입 전 사용자 확정 영역**:

1. **EN 학술 11번째 후보** `sciencedirect.com` 추가 여부 — § 1-b 보류 항목
2. **§12-11-4 README update mini-task 통합** — Step C task #4 로 진입 or 별 cleanup cycle
3. **measurement scope** — (i)~(iii) 기본 vs (iv)(v) 토글 검증 포함
4. **commit 정책** — Step C 1-commit (`§14-9-W Step C — β layered + γ toggle 구현 + base 확장 (58→77) 측정`) vs 2-commit (config patch + 측정 분리)

본 자산은 read-only design 박제 — production code / `.env` / 박제 file 무수정. W Step C 진입 시 사용자 결정 영역 해소 후 patch + 측정 진입.
