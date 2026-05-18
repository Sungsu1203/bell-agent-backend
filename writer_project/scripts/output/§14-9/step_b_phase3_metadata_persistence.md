# §14-9 Step B Phase 3 — vertex metadata persistence (production patch + 측정)

## 본 mission 박제

- entry: §14-9-W close (commit δ `4e450b4`) 후 → §14-9 main mission 의 마지막 sub-cycle
- 목표: vertex_grounding 의 `metadata` (backend / alt_urls / chunk_domain) 가 인덱싱 단계 drop 되는 문제 fix
- target file: `tools/web_rag/ingest_docs.py:web_results_to_documents` (prompt 의 `agent/web_search.py` 는 vertex item 생성 위치 — 실제 인덱싱 화이트리스트는 `ingest_docs.py` 에 있음)
- 결정 흡수:
  - 결정 3: driver `args.topic` 우선 override 개선 (W Step C § 6-f 박제 정합)
  - 결정 4: catch 43 (language-aware backend routing) 후보 박제만, 진입 안 함
- commit 정책: 2-commit (ε production patch + driver / ζ measurement)

## Pre-condition 박제

| 항목 | 값 |
|---|---|
| branch | `main` |
| HEAD (entry baseline) | `4e450b4` (`§14-9-W Step C — base 확장 효과 측정...`) |
| commit ε | `0ca337f` (`§14-9 Step B Phase 3 — vertex metadata persistence + driver (whitelist 확장 + fusion_observability)`) |
| 측정 venv | `.venv_vertex` |
| 측정 provider | vertexai (vertex_grounding metadata 가 primary target) |
| 측정 표준 | §13-7 (warmup 2 / N=3 / timeout 240s / inter-sleep 60s / utf-8) |

────────────────────────────────────────────────

## § 0. Task 0 — entry verify (read-only)

### 0-a. commit chain 정합 (W cycle close)

```
4e450b4 §14-9-W Step C — base 확장 효과 측정 (A/B × 7 query, 경량 EXTRA / γ off verify)
7b407bd §14-9-W Step C — β layered + γ toggle 구현 (config + 코드 patch)
b42a26f §14-9-W Step A + B 박제 자산 (whitelist 진단 + β layered / γ toggle 설계)
3b2ebae §14-9 Step B Phase 2 — methodology 보강 (log-capture) + ★★★★☆ 2 combination + Q4 drop 진단
f858af5 §14-9 Step A + A1 + A2 박제 자산 (audit chain + 정정 reference 부록)
```

### 0-b. working tree clean 단언

`git diff --stat HEAD` 부재 + `git status --short -- writer_project/agent/ writer_project/tools/ writer_project/core/ writer_project/.env writer_project/settings_gatekeep.py` 부재 — production code uncommitted 변경 0 ✓

### 0-c. A2 § 4-c 박제 cross-ref — 현 화이트리스트 (patch 전)

A2 § 4-c: "Chroma 인덱싱 단계 (web_results_to_documents) 에서 화이트리스트 (source/title/content_type) 로 100% drop" — vertex item 의 `metadata` 키가 인덱싱 단계 사라짐.

실측: `tools/web_rag/ingest_docs.py` 의 6 metadata dict literal 사이트 (L277 / L348-352 / L373 / L396-400 / L464 / L472) — 모두 `{source, title, content_type}` 3 keys 만.

────────────────────────────────────────────────

## § 1. Task 1 — `web_results_to_documents` 코드 read (read-only)

### 1-a. 함수 위치 정정 (prompt vs 실제)

**prompt 의 `agent/web_search.py` 화이트리스트 → 실제 `tools/web_rag/ingest_docs.py:236`**.

`agent/web_search.py:786-797` 은 vertex **item 생성 위치** (`combined_items.append({...metadata: {backend, alt_urls, chunk_domain}})`). 실제 인덱싱 화이트리스트는 `web_results_to_documents` (ingest_docs.py:236-478) 에서 metadata dict literal 6 사이트로 정의.

### 1-b. 현 화이트리스트 6 사이트 line ref (patch 전)

| # | line | 분기 |
|---:|---|---|
| 1 | L277 | empty url, item_content fallback |
| 2 | L348-352 | file:// scheme |
| 3 | L373 | raw_content path (HTML) |
| 4 | L396-400 | PDF 파서 |
| 5 | L464 | HTML 로더 |
| 6 | L472 | item.content 마지막 폴백 |

모두 `metadata={"source": ..., "title": ..., "content_type": ...}` 3 keys 만.

### 1-c. vertex item metadata 구조 (`agent/web_search.py:786-797`)

```python
combined_items.append({
    "title": "",
    "url": rep_url,
    "content": support.get("text") or "",
    "raw_content": "",
    "source": rep_url,
    "metadata": {
        "backend": "vertex_grounding",   # str
        "alt_urls": alt_urls,            # list[str] — Chroma 미지원 타입
        "chunk_domain": rep_chunk.get("domain") or "",  # str
    },
})
```

### 1-d. Chroma metadata 타입 정합

Chroma `Document.metadata` 허용 타입 — **str / int / float / bool / None** 만. list / dict 거부 (ValueError).

**조치 필요**: `alt_urls` (list) → comma-joined str 로 flatten.

### 1-e. 다른 사용처 review (backward compat)

- `tools/local_rag.py:21-22` — `metadata["source"]`, `metadata["source_version"]` 만 사용 → 기존 키 보존 영역
- `utils/refs.py` — footnote 생성, metadata 사용 (구체 박제 외 — 본 patch 영향 없음 — 기존 키 변경 없이 신규 키만 추가)
- `agent/` grep — `backend / alt_urls / chunk_domain` 사용처 = `agent/web_search.py` 1 file (vertex item 생성 측만) → consumer 부재

**단언**: backward compat 영향 0 — 기존 키 (source/title/content_type) 보존 + 신규 키 (backend/alt_urls/chunk_domain) 추가만.

────────────────────────────────────────────────

## § 2. Task 2 — 화이트리스트 확장 patch (commit ε)

### 2-a. patch scope

| 영역 | 변경 |
|---|---|
| **helper 함수 추가** | `tools/web_rag/ingest_docs.py:236` (`def web_results_to_documents` 직전) — `_promote_item_metadata(item)` 신규 (23 lines) |
| **6 metadata dict literal 사이트** | 모두 `**_promote_item_metadata(item)` spread 추가 (각 +1 line) |
| 합 | **+29 lines, -6 lines** (line ref 변동) |

### 2-b. `_promote_item_metadata` helper 본문

```python
def _promote_item_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    # §14-9 Phase 3 — vertex grounding 의 item["metadata"] (backend / alt_urls /
    # chunk_domain) 을 Document.metadata 로 promote. Chroma 가 list/dict 를 거부
    # 하므로 alt_urls 는 comma-joined str 로 flatten. 부재 키는 미포함.
    extra: Dict[str, Any] = {}
    meta = item.get("metadata")
    if not isinstance(meta, dict):
        return extra
    bk = meta.get("backend")
    if isinstance(bk, str) and bk.strip():
        extra["backend"] = bk.strip()
    cd = meta.get("chunk_domain")
    if isinstance(cd, str) and cd.strip():
        extra["chunk_domain"] = cd.strip()
    au = meta.get("alt_urls")
    if isinstance(au, (list, tuple)):
        joined = ",".join(str(u).strip() for u in au if str(u).strip())
        if joined:
            extra["alt_urls"] = joined
    elif isinstance(au, str) and au.strip():
        extra["alt_urls"] = au.strip()
    return extra
```

### 2-c. 6 site spread 적용 (예시 — site #3 raw_content path)

```diff
                if text:
                    docs.append(Document(
                        page_content=text,
-                       metadata={"source": url, "title": title or "Web", "content_type": "text/html"},
+                       metadata={"source": url, "title": title or "Web", "content_type": "text/html", **_promote_item_metadata(item)},
                    ))
                    continue
```

나머지 5 사이트 동일 패턴 (L277 / L348-352 / L396-400 / L464 / L472).

### 2-d. graceful handling 단언

| 입력 case | 결과 |
|---|---|
| `item.get("metadata")` 부재 (legacy item) | `_promote_item_metadata` → `{}` (early return at `isinstance(meta, dict)` False) |
| `metadata` 가 str / int (malformed) | `{}` (isinstance False) |
| `alt_urls` 빈 list (single-chunk vertex support) | `alt_urls` 키 미포함 (`joined` 빈 str 시 미설정) — backend + chunk_domain 만 promote |
| `alt_urls` 가 str (이미 flatten) | str 그대로 사용 |
| `backend` / `chunk_domain` 빈 str | 미포함 (`.strip()` False) |

### 2-e. unit test 결과 (실측)

```
[vertex item] _promote_item_metadata: {'backend': 'vertex_grounding', 'chunk_domain': 'pubmed.ncbi.nlm.nih.gov', 'alt_urls': 'https://nih.gov/a,https://nih.gov/b'}
[legacy item] _promote_item_metadata: {}
[malformed item] _promote_item_metadata: {}
```

unit test PASS — 3 axis (vertex / legacy / malformed) 모두 정합.

### 2-f. backward compat 단언

- 기존 키 (`source / title / content_type`) **보존 — 변경 없음**
- 신규 키 (`backend / chunk_domain / alt_urls`) **vertex item 에만 추가** (graceful — legacy item 변동 0)
- Chroma 타입 정합 — alt_urls list → comma-joined str 후 저장 (None / 빈 list 시 키 자체 부재)

────────────────────────────────────────────────

## § 3. Task 3 — driver 작업 (commit ε 흡수)

### 3-a. 신규 driver `scripts/§14-9/fusion_observability.py`

**목적**:
- `vertex_web_search(q)` 직접 호출 → vertex items 빌드 (graph state 우회)
- `tools.web_rag.search.web_search.invoke({"query": q})` → legacy items
- `web_results_to_documents(combined)` 호출 → Document.metadata key 분포 측정
- per-source vertex / legacy 분리 (vertex_urls set 기반 매칭)

**측정 메트릭**:
- `vertex_items_count` / `legacy_items_count` — combined items 분포
- `vertex_doc_count` / `legacy_doc_count` — web_results_to_documents 통과한 Document 분포
- `vertex_promoted_full` — backend + alt_urls + chunk_domain 모두 있는 Document
- `vertex_promoted_partial` — 일부만 있는 Document (alt_urls 빈 list case)
- `vertex_promote_rate_full` — full / vertex_doc_count
- `sample_vertex_meta` / `sample_legacy_meta` — 박제용 표본 (per call max 3)

**argparse** — Phase 1+2 driver 동일 표준 (provider / topic / n / warmup / timeout / inter-sleep / queries / out-dir / tag / sanity)

### 3-b. `backend_isolated_smoke.py` setdefault 개선 (결정 3 흡수)

W Step C § 6-f 박제 정합 — `.env:50 TOPIC_SLUG=venfobel-vitamin` 가 `_load_provider_env` 의 override=False load 로 선점된 경우 `setdefault` 무효 → `args.topic` 우선 override.

```diff
-    os.environ.setdefault("TOPIC_SLUG", args.topic)
+    # TOPIC_SLUG 명시 — args.topic 우선 override 정합 (§14-9-W Step C § 6-f 박제).
+    # .env:50 의 TOPIC_SLUG 가 _load_provider_env 의 override=False load 로
+    # 선점된 경우 setdefault 는 무효 → 본 cycle 부터는 명시 override.
+    os.environ["TOPIC_SLUG"] = args.topic
```

### 3-c. `_q1_q4.txt` 신규 (Phase 1 정합 query input)

Phase 1 default queries 4건 — reproducibility 자산.

────────────────────────────────────────────────

## § 4. Task 4 — A/B 측정

### 4-a. A side (patch 전 baseline)

**옵션 채택**: W Step C raw JSON (`step_c_*.json`) + Phase 2 raw JSON 의 metadata 영역 재분석 — patch 전에는 `web_results_to_documents` 호출 후 Document.metadata 가 `{source, title, content_type}` 3 keys 만 (A2 § 4-c 정합) → **promote_rate_full = 0% (확정)**, vertex item 의 `metadata` 키 100% drop.

raw JSON 재실측 불요 — A2 § 4-c 박제 (read-only audit) 정합으로 A side baseline 단언 가능.

### 4-b. B side (patch 후 main 측정)

**driver call**:

```sh
.venv_vertex/Scripts/python.exe scripts/§14-9/fusion_observability.py \
    --provider vertexai --topic venfobel-vitamin \
    --warmup 2 --n 3 --timeout 240 --inter-sleep 60 \
    --queries scripts/§14-9/_q1_q4.txt \
    --tag phase3_after_main --out-dir scripts/output/§14-9
```

raw JSON: `phase3_fusion_obs_vertexai_phase3_after_main_20260518_160848.json` (.gitignored, 4 query × 5 calls = 20 calls)

### 4-c. 측정 표준 정합 단언

| 표준 | 적용 값 | 정합 |
|---|---|---|
| max_retries | 0 (vertex chain 정합) | ✓ |
| warmup | 2 | ✓ |
| N | 3 | ✓ |
| per-call timeout | 240s | ✓ |
| inter-run sleep | 60s | ✓ |
| PYTHONIOENCODING | utf-8 | ✓ |
| n_errors | 0 (12 measured records) | ✓ |
| 429 quota | 0 | ✓ |
| cv > 50% (Q3 vertex precedent 외) | Q3 elapsed cv 50.0% (Phase A Q3 52.9% precedent 정합 영역 — STOP 미진입) | ✓ |

### 4-d. per-query 측정 결과 (B side, measured n=3)

| Q | v_items mean | v_doc mean | v_doc cv | promote_full mean | partial mean | **any_promote** | promote_rate_full mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| Q1 (벤포벨S 종근당 광고비 2024) | 6.0 | 0.33 | 173.2% (low absolute) | 0.0 | 0.33 | **100%** ✓ | 0.0% |
| Q2 (활성형 비타민 시장 규모 한국) | 10.33 | 1.33 | 43.3% | 0.0 | 1.33 | **100%** ✓ | 0.0% |
| Q3 (비타민 B군 임상시험 효능) | 24.0 | 4.33 | 13.3% | 2.0 | 2.33 | **100%** ✓ | 46.7% |
| Q4 (vitamin B benfotiamine clinical trial) | 13.0 | 2.0 | 86.6% | 1.67 | 0.33 | **100%** ✓ | 91.7% |

**핵심 단언**: **any_promote (full + partial) = 100% for all queries** (12 measured records 합산: vertex_doc_total 24, full 11, partial 13, **promote 0 = 부재**).

→ patch 효과 ★★★★★ 확정 — 모든 vertex item 의 metadata 가 Document.metadata 로 promote.

### 4-e. promote_full vs partial axis 분리 박제

| 분류 | 정의 | 의미 |
|---|---|---|
| **promote_full** | `backend AND alt_urls AND chunk_domain` 모두 보존 | multi-chunk vertex support (`alt_urls` 비빈 list) |
| **promote_partial** | `backend OR alt_urls OR chunk_domain` 일부만 보존 | single-chunk vertex support (`alt_urls` 빈 list — `_promote_item_metadata` 가 alt_urls 키 미포함) |
| **promote_zero** | 모두 부재 | (patch 후 실측 부재 — 모든 vertex doc 에서 최소 backend + chunk_domain 보존) |

Q1/Q2 의 promote_full = 0% 는 **single-chunk supports 사유** (alt_urls=[]) — 실 측정에서는 vertex item 자체가 single chunk 만 반환한 경우 = **patch 결함 아닌 의도된 동작**.

Q3 의 promote_full 46.7% — multi-chunk supports 비율이 절반 가까이 발현.

Q4 의 promote_full **91.7%** ★★★★★ — benfotiamine 의 vertex_grounding chunk_indices 가 multi 인 비율 높음.

### 4-f. ★★★ sample vertex meta inspection (실측)

**Q4 (vitamin B benfotiamine clinical trial) 첫 run sample 2건**:

```python
# Sample 1: cornell.edu (1차) + PubMed (alt_url)
{
    'source': 'https://impact.weill.cornell.edu/summer-2025/discovery/benfotiamine-boosts',
    'title': 'Web',
    'content_type': 'text/html',
    'backend': 'vertex_grounding',
    'chunk_domain': 'cornell.edu',
    'alt_urls': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC10682628/',
}

# Sample 2: emory.edu (1차) + 2 alt_urls (PMC + uiowa.edu)
{
    'source': 'https://goizuetabrainhealth.emory.edu/news/early-alzheimers-clinical-trial.html',
    'title': 'Web',
    'content_type': 'text/html',
    'backend': 'vertex_grounding',
    'chunk_domain': 'emory.edu',
    'alt_urls': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC7880246/,https://medicine.uiowa.edu/news/2024/09/university-iowa-health-care-evaluating-synthetic-version-vitamin-b1-treatment',
}
```

→ **PubMed alt_urls 정상 보존** ✓ — Phase 3 mission 의 핵심 목표 달성. Q4 EN supplement 영역 query 에서 vertex_grounding 이 PubMed / .edu 학술 도메인을 multi-chunk 로 반환하고, 모두 Document.metadata 에 보존.

**Q3 (비타민 B군 임상시험 효능) sample**:

```python
{
    'source': 'https://my-doctor.io/healthLab/info/1951/...',
    'backend': 'vertex_grounding',
    'chunk_domain': 'my-doctor.io',
    'alt_urls': 'https://news.hidoc.co.kr/news/articleView.html?idxno=32578',
}
```

→ KR pharma multi-chunk 도 정합 보존 ✓

### 4-g. A/B 비교 종합

| metric | A side (patch 전) | B side (patch 후) | delta |
|---|---:|---:|---|
| vertex_doc 의 backend / alt_urls / chunk_domain 보존율 | **0%** (A2 § 4-c 정합 박제) | **100%** (any_promote) | **+100pp** ★★★★★ |
| Document.metadata key set | `{source, title, content_type}` 만 | `{source, title, content_type, backend, chunk_domain, alt_urls?}` | +3 keys (alt_urls 조건부) |
| Chroma 인덱싱 호환 | 영향 없음 (3 keys 모두 str) | 영향 없음 (신규 키 모두 str) | ✓ |
| legacy item 영향 | (없음) | (없음 — graceful) | 영향 0 |

────────────────────────────────────────────────

## § 5. catch 43 (language-aware backend routing) 후보 박제 (결정 4 정합)

### 5-a. 발견 배경

- §14-9-W Step C § 4-a-5 (Q4 / Q5 EN supplement 미달 정합)
- 검색 엔진 자체의 EN 학술 반환 부족 (naver_direct + tavily) — base 78 화이트리스트 확장으로 회복 불가
- **본 Phase 3 측정**: vertex_grounding 은 Q4 (EN benfotiamine) 에 cornell.edu / emory.edu / PubMed 등 학술 multi-chunk 정확 반환 → **provider 분기 시 회복 가능 영역**

### 5-b. catch 43 후보 명 + 방향

**catch 43 후보** — "language-aware backend routing"

방향:
- query 언어 감지 (catch 38 langdetect 정합) → vertex_grounding (EN) / legacy chain (KR) 분기
- `SKIP_VERTEX_SEARCH` 의 conditional override (EN query 시 vertex 강제 활성)
- 또는 vertex + legacy 양쪽 호출 (현 `_run_web_search_with_guard` 가 기본 양쪽 호출, but SKIP_VERTEX_SEARCH=0 정합 필수)

### 5-c. 형식화 entry conditions (priors 18 패턴)

(1) **트리거 조건**:
- (a) 영어 토픽 신설 운영 priority 발생 (NDA-bound 영어 시장 분석 토픽 등)
- (b) multiple query (≥ 5건) 의 KR 토픽 환경에서 EN sub-query 빈도 증가 evidence
- (c) catch 38 (language detection) 정식 박제 후

(2) **정량 평가**:
- KR vs EN query 의 vertex_grounding hit 비율 측정 (본 Phase 3 데이터 + 추가 측정)
- legacy chain 의 EN query raw_items 분포 (§14-9-W Step C Q4 raw=0 정합)
- cost 정량 (vertex API call 비용 vs legacy free)

### 5-d. 현 시점 단언

**후보 박제만** — README registry 무진입 (자율 진행 STOP cond 정합). 본 자산의 § 5 cross-ref 박제 후 별 cycle 진입 시 (a)(b)(c) 트리거 조건 충족 시점에 정식 박제.

────────────────────────────────────────────────

## § 6. §14-9 전체 close 단언

### 6-a. §14-9 main mission flow 정합

```
§14-9 Step A          — search backend + LLM provider audit (commit f858af5 부분)
  └─ §14-9-A1         — credential exposure audit
  └─ §14-9-A2         — § 6-f 정정 + clarification + legacy fusion 박제 (commit f858af5)
§14-9 Step B          — chain test + production patch
  ├─ Phase 1          — backend isolated smoke baseline (commit 4e78b63)
  ├─ Phase 2          — methodology + 2 combination + Q4 drop 진단 (commit 3b2ebae)
  └─ Phase 3          — vertex metadata persistence (본 cycle, commit ε + ζ)
§14-9-W (side cycle)  — whitelist + gate-keeping policy
  ├─ Step A           — read-only audit (commit b42a26f)
  ├─ Step B           — β layered + γ toggle 설계 (commit b42a26f)
  └─ Step C           — 구현 + 측정 (commit 7b407bd + 4e450b4)
```

### 6-b. close 단언 체크리스트

| 영역 | 상태 |
|---|---|
| Step A / A1 / A2 박제 (audit chain) | ✓ commit `f858af5` |
| Step B Phase 1 / Phase 2 (chain test + methodology) | ✓ commit `4e78b63` / `3b2ebae` |
| §14-9-W Step A / B / C (whitelist policy review + 구현 + 측정) | ✓ commit `b42a26f` / `7b407bd` / `4e450b4` |
| Step B Phase 3 (vertex metadata persistence + measurement) | ✓ commit `0ca337f` (ε) + 본 commit ζ |
| 후속 candidates 박제 (catch 38~43) | ✓ — README registry 무진입 (별 cycle 형식화) |

### 6-c. production patch 면적 정량 (§14-9 전체)

| commit | patch 영역 | line delta |
|---|---|---:|
| `f858af5` | 박제 only | +989 -0 |
| `4e78b63` | driver 신규 | +N |
| `3b2ebae` | driver 보강 + 박제 | +584 -3 |
| `b42a26f` | 박제 only | +1038 -0 |
| `7b407bd` | `core/config.py` (+5) + `docs/topic_env_guide.md` (+신규) + `README-dev.md` §12-11-4 update | +148 -1 |
| `4e450b4` | 박제 + console + 측정 reproducibility | +601 -0 |
| `0ca337f` | `ingest_docs.py` whitelist 확장 (+29 -6) + driver (신규 + setdefault 개선) | +445 -6 |

production code 변경: **`ingest_docs.py` (helper +6 sites spread, 본질 1 module) + `core/config.py` (1줄 hook 추가)** — 본 cycle 의 production patch 영역.

### 6-d. 후속 candidates catch 38~43 cross-ref

| catch # | 명 | 박제 시 |
|---:|---|---|
| catch 38 | content-language detection | W Step C § 0-b |
| catch 39 | content length 하한 | W Step C § 0-b |
| catch 40 | LLM-based content quality scorer | W Step C § 0-b |
| catch 41 | readability heuristic | W Step C § 0-b |
| catch 42 | ad-hoc deny list 보강 (`FILTER_BAD_DOMAINS`) | W Step C § 0-b (★ 최즉시 적용 가능) |
| **catch 43** | **language-aware backend routing** | **본 자산 § 5 (NEW)** |

본 자산 close 시점 = §14-9 main mission close. README-dev §14 track close 표기 update **권장** (별 mini-task 또는 commit ζ 흡수 — 사용자 컨펌 영역).

────────────────────────────────────────────────

## § 7. STOP 정합 (Phase 3 한정)

- Task 2 화이트리스트 확장 시 nested dict / unsupported type 추가: 0 ✓ — `_promote_item_metadata` 가 str/None 만 promote, alt_urls list 는 comma-joined str flatten
- Task 2 patch 후 footnote / Document.metadata 사용처 회귀: 0 ✓ — 기존 키 보존 + 신규 키 추가만, local_rag.py / utils/refs.py 영향 없음
- Task 4 측정 cv > 50% (Q3 precedent 외): 0 ✓ — Q3 elapsed cv 50.0% 는 Phase A Q3 52.9% precedent 정합 영역
- Task 4 429 quota: 0 ✓ — 12 measured records 전체
- raw JSON tracked 시도: 0 ✓ — `phase3_*.json` .gitignored 정합
- 자율적 catch 43 README registry entry 추가: 0 ✓ — § 5 cross-ref 박제만
- 자율적 §14-9 close 단언 (Phase 3 측정 미완 상태): 0 ✓ — measurement 완료 후 § 6 단언
- production code 수정 영역 외 mutation: 0 ✓ — `ingest_docs.py` whitelist (+29 -6) + driver (`backend_isolated_smoke.py` setdefault +5 / `fusion_observability.py` 신규) 만
- axis-ambiguous: 0 ✓ — vertex/legacy, full/partial/any, A/B side, before/after patch 모두 명시

────────────────────────────────────────────────

## § 8. precedent cross-ref 정리

| precedent | 본 Phase 3 정합 위치 |
|---|---|
| A2 § 4-c (현 화이트리스트 박제 — 100% drop) | § 0-c, § 1-a/b, § 4-a, § 4-g |
| Phase 1 § 2-d (Phase A 회귀 부재) | § 4-c (Q3 cv precedent 영역) |
| Phase 2 § 5.5-d (search.py:1827-1844 drop layer) | § 4-g (drop layer 분리: search-stage vs index-stage) |
| Phase 2 § 6-b (legacy chain provider-independent) | § 3-a (driver vertex_web_search 직접 호출 정합) |
| §14-9-W Step A / B / C | § 5-a (Q4/Q5 EN supplement 미달 발견 배경) |
| §14-9-W Step C § 6-f (driver setdefault 패턴) | § 3-b (결정 3 흡수) |
| §13-7 (측정 표준) | § 4-c |
| §14-2 후속 sub-task (a) (alt_urls / backend / chunk_domain 보존 backlog) | § 0-c, § 2-a (본 cycle 로 종결) |
| README-dev-§14.md:24 (vertex metadata 100% drop) | § 1-a (실제 함수 위치 정정) |
| README-dev-§14.md:110 (B-B sub-task whitelist 확장) | § 1-b (6 사이트 line ref) |
| priors 18 entry conditions 패턴 | § 5-c (catch 43 trigger) |

────────────────────────────────────────────────

## § 9. commit 정합 정리 (2-commit 구조)

| commit | hash | scope |
|---|---|---|
| **ε** | `0ca337f` | `§14-9 Step B Phase 3 — vertex metadata persistence + driver (whitelist 확장 + fusion_observability)` — `tools/web_rag/ingest_docs.py` (+29 -6) + `scripts/§14-9/fusion_observability.py` 신규 + `scripts/§14-9/backend_isolated_smoke.py` setdefault 개선 + `_q1_q4.txt` 신규 |
| **ζ** | (본 박제 commit, 후속) | `§14-9 Step B Phase 3 — A/B 측정 (metadata 보존율 + Phase 3 박제)` — `scripts/output/§14-9/step_b_phase3_metadata_persistence.md` + (선택) reproducibility console |

raw JSON 2 files (.gitignored, commit 외):
- `phase3_fusion_obs_vertexai_sanity_phase3_after_20260518_152056.json` (sanity)
- `phase3_fusion_obs_vertexai_phase3_after_main_20260518_160848.json` (main)

────────────────────────────────────────────────

## § 10. 사용자 컨펌 대기 영역

본 Phase 3 close = **§14-9 main mission 전체 close**.

1. **README-dev §14 track close 표기 update** — 본 commit ζ 흡수 vs 별 mini-task (사용자 컨펌)
2. **catch 42 (`FILTER_BAD_DOMAINS` 보강) 별 cycle 진입 시점** — W Step C γ off 측정의 `purebulk / lifeextension / doublewoodsupplements` 후보 도메인 set + 본 Phase 3 의 추가 candidates 식별 (`vertexaisearch.cloud.google.com/grounding-api-redirect/...` 미해결 redirect 등)
3. **catch 43 (language-aware backend routing) 별 cycle 진입 시점** — 영어 토픽 priority 발생 또는 catch 38 정식 박제 후
4. **§14-9 close 후 다음 트랙** — 사용자 결정 영역

본 자산은 measurement + 박제 + Phase 3 close 단언 — `commit ε (0ca337f)` + commit ζ (후속) 정합. §14-9 main mission close 진입 valid.
