# §academic-4 Step B design (read-only)

> **박제 chain reference**
> - 직전 step: §academic-4 Step A close (commit `4574a33` · branch `main` · 2026-05-21)
> - 본 design 대상: catch 51 fix S1 (Option 5 학술 전용 backend 단독 추가) 의 module + routing + 도메인 추출 + env/driver design spec
> - root cause: catch 51 redefine — "EN academic mode 학술 전용 backend 부재, vertex 단독 의존 (ad-tech bias 는 증상)"
> - design 범위: B1 (module 설계) · B2 (routing 통합 패턴) · B3 (도메인 추출 + catch 59 정적 매핑 table) · B4 (env + 측정 driver 확장) — **read-only, pseudocode/spec only**
> - 환경: PowerShell · BOOK-DPUCVR08TC · HEAD = `4574a33` · 2026-05-21

---

## 0. Decision layer 분리 + 사용자 컨펌 4 sub-decisions (Issue 4 반영)

### Decision layer 분리

| Layer | 의제 | 본 Step B 처분 |
|---|---|---|
| **high-level (pre-brainstorm 4개)** | #1 fix 접근 / #2 외부 의존 한계 / #3 PASS 임계 0.6 / #4 scope | **#1**: Step A audit A3 5 후보 비교 → S1 (Option 5 단독) 권고로 확정 진입 — 본 design 진입 자체가 처분 / **#2~#4**: Step A audit summary 박제로 해소 (외부 의존 LOW, 임계 0.6 충족 안정 마진 ~0.676, scope 본 cycle catch 51 만) |
| **low-level (audit summary 4개, 본 Step B 의제)** | (1) ss/oa key 정책 / (2) 도메인 추출 path / (3) catch 59 채택 / (4) routing 통합 패턴 | 사용자 컨펌 권고 안 박제: **1A / 우선순위 / 3A / 4A** (아래 sub-decisions 표) |

### 사용자 컨펌 4 sub-decisions 박제

| # | 영역 | 결정 | 박제 사유 |
|---:|---|---|---|
| 1 | ss/oa key 정책 | **1B (1A_prime 후속, SS authenticated pool 활성 단계)** — SS: `SEMANTIC_SCHOLAR_API_KEY` + `x-api-key` 헤더 활성 (commit 2 smoke 정합 200 OK 검증, attempt=0 1.984s, X-Cache: Miss from cloudfront authenticated pool 정합) + `SEMANTIC_SCHOLAR_SKIP=0` / OA: key 발급 필수 (`api_key=` 파라미터 + mailto polite pool) 유지 | **단계 진화 박제**: 1A (commit 1 anonymous 시도) → 1A_prime (anonymous reality check 후 SKIP=1 default + x-api-key 사전 박제) → **1B (commit 2 SS key 발급 + authenticated pool 활성)**. commit 2 smoke 정합: SS items=10, elapsed 1.984s, domains_unique 학술 도메인 (sagepub / mdpi / ssrn 등) 정합, catch 59 fallback 30% (SS multidisciplinary 분포). mailto 통일 = `sungsu.oh@bellcomm.co.kr` (회사 메일, SS key request form 정합) |
| 2 | 도메인 추출 path 우선순위 | **4-step early-return**: (1) `primary_location.landing_page_url` (OA, 전체 cover) → (2) `openAccessPdf.url` (SS, OA 한정) → (3) **DOI prefix → publisher 매핑 (catch 59)** → (4) `venue` / `source.display_name` 매칭 (ACADEMIC_DOMAINS 36 set 정합) | A2-c pilot 검증: OA entry 0/1 모두 `landing_page_url` robust (sciencedirect.com 직접) · SS entry 1 의 DOI `10.3390/*` → mdpi.com (catch 59 매핑) hit |
| 3 | catch 59 채택 | **3A — 정적 prefix → publisher 매핑 table 내장** (광고/마케팅 핵심 + 인접 STEM 35 entries cover, 신규 prefix 발견 시 logging fallback) | Crossref REST / OA works/{doi} 동적 조회 미채택 사유: 추가 latency (REST 호출 1회 × N papers) + OA credit 소비 (10 credit × N) + Step C 측정 fan-out 안정성 우선 |
| 4 | routing 통합 패턴 | **4A — fan-out 병렬** (vertex + ss + oa 동시 호출, `concurrent.futures.ThreadPoolExecutor` 권고, 에러 isolation + 전체 timeout ~30s) | A2-c latency 실측: vertex 18.157s bottleneck, ss 1.36s, oa 1.82s → fan-out overhead 사실상 0. asyncio 도입은 web_search.py 의 sync 패턴 깨므로 ThreadPoolExecutor 우선 |

### 사용자 컨펌 Step C 측정 처분

- academic-en single query 유지 (§academic-3 baseline 1:1 정합 우선)
- catch 58 multi-query 확장은 §academic-5 이전 (본 cycle scope creep 회피, STOP-B-4 정합)

---

## 1. Step A 잔여 반영 (Issue 3 baseline 명세 + Issue 5 STOP gate 정의)

### Issue 3 — pilot 정량 강도 표현 완화

**baseline 명세**:

> Step A pilot 의 ratio 추정 **~0.676** 은 (a) 1차 정량 (각 backend 첫 2 entries 의 venue/DOI 명시 검증) + (b) 정성 추정 (나머지 8 entries 분야 적합도 가정, OpenAlex MAG 후계자 + Semantic Scholar Academic Graph 학술 venue ranker 정합) 의 혼합. **Step C 측정 시 vertex+legacy+ss+oa 합집합 기준 (`measure_ab.py:420-438` 산식 정합) 으로 정량 검증 영역**. Step B design 의 정량 근거는 baseline 명세 한도 안에서만 유효.

### Issue 5 — STOP gate 정의 process lesson

**STOP-8 retry/fallback call 정의 정합**:

> STOP gate 의 호출 횟수는 **successful call 기준** (fail call 은 fallback 1회 허용, prompt 명시 영역). Step A pilot 의 SS curl 429 fail → urllib UA+backoff fallback 200 OK 는 STOP-8 (각 backend 1 successful call) 정합. catch 57 inline 박제에 이 process lesson 보강.

---

## 2. B1 — module 설계 (semantic_scholar.py + openalex.py)

### B1-1 신규 module 파일 + 함수 signature

**파일 위치**: `writer_project/tools/web_rag/semantic_scholar.py` · `writer_project/tools/web_rag/openalex.py`

**Pattern 답습**: `tools/web_rag/vertex_search.py:88-194 vertex_web_search(query)` (함수 1 + 헬퍼 1~2 + try/except import guard)

#### `semantic_scholar_search(query: str) -> Dict[str, Any]`

```
# pseudocode (Step C 영역, 실제 코드 작성 X)

def semantic_scholar_search(query: str) -> Dict[str, Any]:
    """
    Semantic Scholar Graph API v1 paper/search 호출.
    반환 형식: vertex_web_search() 정합 (chunks/supports/items 통합 chain compatibility).
    """
    t0 = time.monotonic()
    mailto = os.getenv("SEMANTIC_SCHOLAR_MAILTO", "sungsu.oh@bellcomm.co.kr")
    fields = "title,venue,year,journal,externalIds,openAccessPdf,authors"
    url = (f"https://api.semanticscholar.org/graph/v1/paper/search"
           f"?query={urlencode(query)}&limit=10&fields={fields}")
    headers = {
        "User-Agent": f"writer_project/§academic-4 (mailto:{mailto})",
        "Accept": "application/json",
    }
    # 1회 backoff 2s on 429 (Step A pilot 검증된 패턴)
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(2.0)
                continue
            return _empty_result("semantic_scholar", error=str(e), elapsed=time.monotonic()-t0)
        except Exception as e:
            return _empty_result("semantic_scholar", error=str(e), elapsed=time.monotonic()-t0)

    data = body.get("data") or []
    chunks, supports, domains = [], [], []
    for i, paper in enumerate(data):
        d = extract_domain_from_paper(paper, backend="semantic_scholar")  # B3 layer
        if not d:
            continue
        chunks.append({"uri": _paper_to_url(paper), "title": paper.get("title") or "", "domain": d})
        supports.append({"chunk_indices": [i], "text": paper.get("title") or "",
                         "start_index": 0, "end_index": 0})
        domains.append(d)

    return {
        "mode": "semantic_scholar",
        "elapsed_sec": round(time.monotonic() - t0, 3),
        "items": len(data),
        "domains": domains,
        "domains_unique": sorted(set(d for d in domains if d)),
        "chunks": chunks,
        "supports": supports,
        "web_search_queries": [query],
        "error": None,
    }
```

#### `openalex_search(query: str) -> Dict[str, Any]`

```
# pseudocode

def openalex_search(query: str) -> Dict[str, Any]:
    """
    OpenAlex /works search 호출 (mailto polite pool + api_key 필수).
    """
    t0 = time.monotonic()
    mailto = os.getenv("OPENALEX_MAILTO", "sungsu.oh@bellcomm.co.kr")
    api_key = os.getenv("OPENALEX_API_KEY", "")
    if not api_key:
        return _empty_result("openalex", error="OPENALEX_API_KEY 미설정",
                             elapsed=time.monotonic()-t0)
    url = (f"https://api.openalex.org/works"
           f"?search={urlencode(query)}&per-page=10"
           f"&mailto={mailto}&api_key={api_key}")
    # mailto/api_key 는 query param 형태 (header 도 가능, 정책 변경 시 분기)
    headers = {"Accept": "application/json"}
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(2.0); continue
            return _empty_result("openalex", error=str(e), elapsed=time.monotonic()-t0)
        except Exception as e:
            return _empty_result("openalex", error=str(e), elapsed=time.monotonic()-t0)

    results = body.get("results") or []
    chunks, supports, domains = [], [], []
    for i, work in enumerate(results):
        d = extract_domain_from_paper(work, backend="openalex")  # B3 layer
        if not d:
            continue
        url_extract = (work.get("primary_location") or {}).get("landing_page_url") or work.get("doi") or ""
        chunks.append({"uri": url_extract, "title": work.get("title") or "", "domain": d})
        supports.append({"chunk_indices": [i], "text": work.get("title") or "",
                         "start_index": 0, "end_index": 0})
        domains.append(d)

    return {
        "mode": "openalex",
        "elapsed_sec": round(time.monotonic() - t0, 3),
        "items": len(results),
        "domains": domains,
        "domains_unique": sorted(set(d for d in domains if d)),
        "chunks": chunks,
        "supports": supports,
        "web_search_queries": [query],
        "error": None,
    }
```

### B1-2 헬퍼 + 에러 처리

| 헬퍼 | 위치 | 역할 |
|---|---|---|
| `_empty_result(mode, error, elapsed)` | `semantic_scholar.py` / `openalex.py` 양쪽 module-private | 호출 실패 시 vertex 정합 빈 dict 반환 (`items=0, domains=[], error=str`) — 에러 isolation 의 backend 측 endpoint |
| `extract_domain_from_paper(paper_dict, backend)` | **shared helper, 신규 `tools/web_rag/_scholarly_domain.py` 또는 inline** | B3 의 4-step early-return logic (Sub-decision 2) |
| `_paper_to_url(paper)` | `semantic_scholar.py` private | SS paper dict → 대표 URL (`openAccessPdf.url` > `url` > `f"https://doi.org/{DOI}"`) |

### B1-3 라이브러리 선택 사유 (catch 57 lesson 반영)

| 후보 | 채택 여부 | 사유 |
|---|:---:|---|
| `urllib.request` (표준 라이브러리) | **채택** | Step A pilot 의 SS fallback 검증 (User-Agent 헤더 명시 200 OK). 외부 의존 0, venv 호환성 최고 |
| `requests` | 보조 | 이미 `vertex_search.py` 에서 `_resolve_vertex_redirect` 용도로 import 됨. 본 module 도입 시 양립 가능하지만 의존 일원화 측면에서 urllib 우선 |
| `httpx` | 미채택 | async 지원이 있으나 sync 호출 패턴에서 urllib 대비 이점 없음, 추가 의존 |

### B1-4 변경 면적 추정 (catch 48 컨벤션)

| 파일 | logical line | cosmetic | 비고 |
|---|---:|---:|---|
| `tools/web_rag/semantic_scholar.py` (신규) | ~+90~110 | +8 (separator + module docstring) | 함수 1 + 헬퍼 2 (`_empty_result`, `_paper_to_url`) |
| `tools/web_rag/openalex.py` (신규) | ~+90~110 | +8 | 함수 1 + 헬퍼 1 (`_empty_result` shared 또는 module-local) |
| `tools/web_rag/_scholarly_domain.py` (신규, B3 영역) | ~+80~120 | +6 | `extract_domain_from_paper` + catch 59 매핑 table |
| **B1 net logical** | **~+260~340** | +22 | catch 48 산식 정합, Step C-1 budget 산정 영역 |

---

## 3. B2 — routing 통합 패턴 (catch 43 자연 확장)

### B2-1 새 routing 매트릭스

| MODE | q_lang | vertex | semantic_scholar | openalex | legacy (Tavily+Naver) |
|---|---|:---:|:---:|:---:|:---:|
| business | (any) | skip | skip | skip | **활성** |
| academic | ko | skip (catch 43) | skip | skip | **활성** (naver_direct) |
| academic | en | **활성** | **활성 (신규)** | **활성 (신규)** | **활성** |
| academic | mixed | **활성** | **활성 (신규)** | **활성 (신규)** | **활성** |

### B2-2 분기 코드 patch 안 (`agent/web_search.py:747-755` 확장)

```
# 현재 (catch 43, §academic-1 완료)
if _get_cfg_attr("MODE", "business") == "academic":
    _q_lang = ...detect_query_lang...
    effective_skip_vertex = (_q_lang == "ko")
else:
    effective_skip_vertex = _cfg_bool("SKIP_VERTEX_SEARCH", False)

# 신규 (catch 51 fix, S1 — Option 5 자연 확장)
if _get_cfg_attr("MODE", "business") == "academic":
    _q_lang = ...detect_query_lang...
    effective_skip_vertex     = (_q_lang == "ko")
    effective_use_scholarly   = (_q_lang != "ko")     # ★ ss + oa 활성 분기
else:
    effective_skip_vertex     = _cfg_bool("SKIP_VERTEX_SEARCH", False)
    effective_use_scholarly   = False
```

### B2-3 fan-out 병렬 패턴 (`agent/web_search.py:780~870` 확장)

```
# pseudocode (B1 신규 함수 의존)
import concurrent.futures as cf

def _backend_call(name, fn, query):
    """1 backend 호출. 실패 시 빈 dict 반환 (에러 isolation)."""
    try:
        return name, fn(query)
    except Exception as e:
        logger.warning(f"[web_search] {name} failed: {e}")
        return name, {"items": 0, "domains": [], "chunks": [], "supports": [], "error": str(e)}

def _fan_out_academic_en(query):
    backends = [("vertex", vertex_web_search)]
    if effective_use_scholarly:
        backends.extend([
            ("semantic_scholar", semantic_scholar_search),
            ("openalex", openalex_search),
        ])
    results = {}
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(_backend_call, n, fn, query): n for n, fn in backends}
        for fut in cf.as_completed(futs, timeout=30):  # 전체 30s timeout
            name, res = fut.result()
            results[name] = res
    return results
```

### B2-4 dedup logic (vertex + ss + oa + legacy unique 합집합)

- 도메인 단위 dedup: `all_domains_unique = sorted(set(vertex.domains | ss.domains | oa.domains | legacy.domains))`
- URL 단위 dedup: 기존 `_norm_url` (`agent/web_search.py:574-596`) 답습 (host normalize + path normalize + `__v_{n}_{n}` suffix 제거)
- chunks 통합: vertex chunks (Web grounding) + ss chunks (paper entries) + oa chunks (work entries) 합성 list (rep_idx 인덱싱 정합 유지)

### B2-5 에러 isolation + timeout 정책

| 항목 | 정책 | 근거 |
|---|---|---|
| backend 1개 실패 시 | 빈 dict 반환, 나머지 backend 진행 | A2-c pilot 정합: SS 429 fail 후에도 OA success — 에러 isolation 의 실측 |
| 전체 timeout | **30s** (vertex 18s bottleneck + 12s margin) | A2-c latency 실측: vertex 18.157s max + ss 1.36s + oa 1.82s · 50% margin |
| backend 별 timeout | vertex 25s (기존) / ss 10s / oa 10s | ss/oa 1.5~2s 실측의 ~5x margin |
| 429 backoff | 2s × 1회 fallback (catch 57 lesson) | Step A pilot 검증 |

### B2-6 변경 면적 추정

| 파일 | logical line | cosmetic | 비고 |
|---|---:|---:|---|
| `agent/web_search.py:747-755` 분기 확장 | ~+5 | +1 | `effective_use_scholarly` 변수 추가 |
| `agent/web_search.py:780~870` fan-out 통합 | ~+50~70 | +5 | `_fan_out_academic_en` + ThreadPoolExecutor block + 통합 layer |
| import 추가 | +2 | – | `from tools.web_rag.semantic_scholar import semantic_scholar_search` 등 |
| **B2 net logical** | **~+55~75** | +6 | – |

---

## 4. B3 — 도메인 추출 path + catch 59 정적 매핑 table

### B3-1 `extract_domain_from_paper(paper, backend)` 4-step early-return

```
# pseudocode (shared helper, 신규 tools/web_rag/_scholarly_domain.py)

def extract_domain_from_paper(paper: Dict[str, Any], backend: str) -> str | None:
    """
    학술 paper dict 에서 도메인 추출 (4-step 우선순위, early-return).
    backend: "semantic_scholar" or "openalex" — schema 분기.
    """
    # (1) primary_location.landing_page_url — OpenAlex 전체 cover
    if backend == "openalex":
        pl = paper.get("primary_location") or {}
        url = pl.get("landing_page_url") or pl.get("pdf_url") or ""
        d = _domain_of(url)
        if d:
            return d

    # (2) openAccessPdf.url — Semantic Scholar OA 한정
    if backend == "semantic_scholar":
        oa_pdf = (paper.get("openAccessPdf") or {}).get("url") or ""
        d = _domain_of(oa_pdf)
        if d:
            return d

    # (3) DOI prefix → publisher 매핑 (catch 59 정적 table)
    doi = ""
    if backend == "openalex":
        doi = (paper.get("doi") or "").replace("https://doi.org/", "")
    elif backend == "semantic_scholar":
        doi = ((paper.get("externalIds") or {}).get("DOI") or "")
    if doi:
        d = doi_prefix_to_domain(doi)  # catch 59 table lookup
        if d:
            return d

    # (4) venue / source.display_name 매칭 (ACADEMIC_DOMAINS 36 set 정합)
    if backend == "openalex":
        src_name = ((paper.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
    else:
        src_name = paper.get("venue") or (paper.get("journal") or {}).get("name") or ""
    d = venue_name_to_domain(src_name)  # venue → known 36 set 매핑
    if d:
        return d

    # 미매핑 paper: logging fallback (Step C 측정에서 unknown prefix 수집 cycle)
    if doi:
        logger.info(f"[catch59] unknown DOI prefix: {doi[:30]} (backend={backend})")
    return None
```

### B3-2 catch 59 정적 매핑 table (37 entries — 광고/마케팅 핵심 + 인접 STEM)

> **§academic-4 Step C-1 commit 1 보강 (2026-05-21)**: 사용자 측 OA smoke 의 catch 59 logging fallback 에서 발견된 unknown prefix 2건 추가 — `10.1177/` (SAGE Publications 메인 prefix, CRITICAL 누락 — JoM 등 cover) + `10.21511/` (Business Perspectives, minor 소형 OA). 35 → **37 entries**.

```
# tools/web_rag/_scholarly_domain.py module-level constant

DOI_PREFIX_TO_DOMAIN: Dict[str, str] = {
    # ── 광고/마케팅 핵심 publisher (10) ───────────────────────────────────
    "10.1016/":   "sciencedirect.com",          # Elsevier (JBR, IJRM, JR 등)
    "10.1086/":   "journals.uchicago.edu",      # Univ. of Chicago Press (JCR)
    "10.1080/":   "tandfonline.com",            # Taylor & Francis (Journal of Advertising 일부)
    "10.1207/":   "tandfonline.com",            # T&F older format
    "10.1509/":   "journals.sagepub.com",       # SAGE (Journal of Marketing 일부)
    "10.1177/":   "journals.sagepub.com",       # SAGE 메인 prefix (JoM 등, CRITICAL — Step C-1 commit 1 추가)
    "10.1108/":   "emerald.com",                # Emerald (Journal of Product & Brand Mgmt 등)
    "10.1287/":   "pubsonline.informs.org",     # INFORMS (Marketing Science)
    "10.5465/":   "journals.aom.org",           # Academy of Management (AMJ/AMR)
    "10.4135/":   "sk.sagepub.com",             # SAGE Knowledge (handbook/encyclopedia)
    # ── 광범위 OA / 학술지 publisher ──────────────────────────────────────
    "10.3390/":   "mdpi.com",                   # MDPI (catch 52 36 set 정합)
    "10.1111/":   "onlinelibrary.wiley.com",    # Wiley (광범위)
    "10.1002/":   "onlinelibrary.wiley.com",    # Wiley (광범위 alt prefix)
    "10.1007/":   "link.springer.com",          # Springer
    "10.1057/":   "palgrave.com",               # Palgrave / Macmillan (Springer 산하)
    "10.1093/":   "academic.oup.com",           # Oxford University Press
    "10.1037/":   "psycnet.apa.org",            # APA (Journal of Marketing Research 인접)
    "10.4324/":   "taylorfrancis.com",          # T&F Books
    # ── 사회과학 / 경제 / 통계 ────────────────────────────────────────────
    "10.1257/":   "aeaweb.org",                 # American Economic Association
    "10.1162/":   "direct.mit.edu",             # MIT Press
    "10.1561/":   "nowpublishers.com",          # Foundations & Trends
    "10.1146/":   "annualreviews.org",          # Annual Reviews
    "10.1525/":   "online.ucpress.edu",         # UC Press
    # ── STEM / IT (마케팅 인접 — UX/HCI/AI) ──────────────────────────────
    "10.1145/":   "dl.acm.org",                 # ACM
    "10.1109/":   "ieeexplore.ieee.org",        # IEEE
    "10.1126/":   "science.org",                # Science (catch 52 36 set 정합)
    "10.1038/":   "nature.com",                 # Nature publishing
    "10.1073/":   "pnas.org",                   # PNAS
    "10.1136/":   "bmj.com",                    # BMJ
    "10.1186/":   "biomedcentral.com",          # BMC (BioMed Central)
    "10.1371/":   "plos.org",                   # PLOS (catch 52 36 set 정합)
    # ── Preprint / Repository ─────────────────────────────────────────────
    "10.48550/":  "arxiv.org",                  # arXiv (catch 52 36 set 정합)
    "10.2139/":   "ssrn.com",                   # SSRN working papers (catch 52 36 set 정합)
    "10.31234/":  "osf.io",                     # PsyArXiv
    "10.31219/":  "osf.io",                     # OSF Preprints
    "10.31235/":  "osf.io",                     # SocArXiv
    # ── Misc (1) ──────────────────────────────────────────────────────────
    "10.21511/":  "businessperspectives.org",   # Business Perspectives (소형 OA, Step C-1 commit 1 추가)
}

def doi_prefix_to_domain(doi: str) -> str | None:
    """DOI prefix lookup (longest-prefix-first)."""
    for prefix, domain in sorted(DOI_PREFIX_TO_DOMAIN.items(),
                                  key=lambda kv: -len(kv[0])):
        if doi.startswith(prefix):
            return domain
    return None
```

**총 37 entries** (광고/마케팅 핵심 **10** + 광범위 publisher 8 + 사회과학/경제 5 + STEM 7 + preprint 5 + **misc 1** = 37). 30~50 entries 목표 정합. Step C-1 commit 1 시점 사용자 측 OA smoke 의 logging fallback 발견 2 entries (`10.1177/` SAGE 메인 + `10.21511/` Business Perspectives) 보강.

### B3-3 pilot raw 검증 정합

| backend | first entry DOI | catch 59 매핑 결과 | 도메인 추출 path 활성화 |
|---|---|---|---|
| Semantic Scholar #0 | `10.63075/jcs.v3i1.132` | **unknown prefix** | path (4) `venue` 매칭 실패 → logging fallback (Step C 보강 cycle 대상) |
| Semantic Scholar #1 | `10.3390/jtaer20020111` | **mdpi.com** ✓ (catch 52 36 set hit) | path (3) DOI prefix 매핑 |
| OpenAlex #0 | `10.1016/j.jbusres.2016.04.181` | **sciencedirect.com** ✓ (catch 52 36 set hit) | path (1) `landing_page_url` direct (DOI redirect 동등) |
| OpenAlex #1 | `10.1016/j.ijresmar.2015.06.004` | **sciencedirect.com** ✓ (catch 52 36 set hit) | path (1) `landing_page_url` direct |

→ pilot raw 4 entries 중 3 entries (75%) catch 52 ACADEMIC_DOMAINS 36 set 자동 hit · 1 entry (SS #0, unknown prefix) catch 59 logging fallback 대상.

### B3-4 변경 면적 추정

| 파일 | logical line | cosmetic | 비고 |
|---|---:|---:|---|
| `tools/web_rag/_scholarly_domain.py` (신규) | ~+80~120 | +6 | `extract_domain_from_paper` + table + `doi_prefix_to_domain` + `venue_name_to_domain` |
| **B3 net logical** | **~+80~120** | +6 | B1-4 신규 module 면적과 합치 |

---

## 5. B4 — env + 측정 driver 확장

### B4-1 신규 env file 2개

#### `.env.openalex` (신규)

```
# OpenAlex API key (2026-02-13~ 필수) — 사용자 별도 발급 (30초)
OPENALEX_API_KEY=<placeholder>
OPENALEX_MAILTO=sungsu.oh@bellcomm.co.kr
```

#### `.env.semanticscholar` (신규, 1A' 정합)

```
# Semantic Scholar — 1A' 정합: anonymous pool reality check 후 SKIP default
SEMANTIC_SCHOLAR_MAILTO=sungsu.oh@bellcomm.co.kr
SEMANTIC_SCHOLAR_SKIP=1
# key 발급 후 활성 절차 (catch 61 후보):
#   1) SEMANTIC_SCHOLAR_API_KEY=<발급값>  추가
#   2) SEMANTIC_SCHOLAR_SKIP=0           변경
# → semantic_scholar.py 의 x-api-key 헤더 자동 활성 (코드 변경 불필요)
# SEMANTIC_SCHOLAR_API_KEY=<placeholder>
```

#### env 로딩 정합

- 기존 `.env.vertex` / `.env.openai` / `.env.anthropic` 패턴 답습 (provider 별 별 파일).
- `.env.openalex` / `.env.semanticscholar` 는 **provider-agnostic backend layer** 이므로 LLM_PROVIDER 토글과 직교 — 모든 venv 에서 동시 로딩 가능.
- **driver layer 영역 (commit 2 amend 구현 완료)**: `scripts/§academic-1/measure_ab.py` main() 진입 직후 `load_dotenv(PROJECT_ROOT / ".env.openalex", override=True)` + `.env.semanticscholar` chain 추가 (~+8 line, catch 64 lesson 정합 `override=True`). Step C-2 측정 시 사용자 측 `$env:*` 직접 주입 불필요 영역 진입.
- **app-wide 영역 (§academic-5 이전)**: `core/config.py` 의 env 로딩 chain 에 본 2 file 추가 — 광범위 통합 영역 (모든 venv / pytest / driver 영역 자동 로딩), 본 cycle scope 외.

### B4-2 measure_ab.py 확장 spec

기존 (`scripts/§academic-1/measure_ab.py:410-438 run_single()`):

```
vertex_rec = call_vertex(...)
legacy_rec = call_legacy(...)
all_domains = vertex.domains + legacy.domains
all_domains_set = sorted(set(all_domains))
academic_domains = sorted(set(all_domains_set) & ACADEMIC_DOMAINS)
academic_ratio = len(academic_domains) / len(all_domains_set)
```

신규 spec:

```
vertex_rec = call_vertex(query, timeout_s, dry_run) if not eff_skip else {...skip stub...}
legacy_rec = call_legacy(query, timeout_s, dry_run)
# ★ 신규: ss + oa 활성 분기 (catch 43 자연 확장 정합)
ss_rec = (call_semantic_scholar(query, timeout_s, dry_run)
          if mode == "academic" and q_lang != "ko" else {...skip stub...})
oa_rec = (call_openalex(query, timeout_s, dry_run)
          if mode == "academic" and q_lang != "ko" else {...skip stub...})

all_domains = (list(vertex_rec.get("domains", []))
             + list(legacy_rec.get("domains", []))
             + list(ss_rec.get("domains", []))
             + list(oa_rec.get("domains", [])))
all_domains_set = sorted(set(d for d in all_domains if d))
academic_domains = sorted(set(all_domains_set) & ACADEMIC_DOMAINS)
academic_ratio = (len(academic_domains) / len(all_domains_set)) if all_domains_set else 0.0

return {
    ...기존 키 유지...,
    "vertex": vertex_rec,
    "legacy": legacy_rec,
    "semantic_scholar": ss_rec,   # ★ 신규
    "openalex": oa_rec,           # ★ 신규
    "all_domains_unique": all_domains_set,
    "academic_domains_hit": academic_domains,
    "academic_source_ratio": round(academic_ratio, 4),
    "ts_utc": ...,
}
```

### B4-3 per-backend latency / domains 보존 (Step C `c_verification.json` 정합)

| backend | elapsed_sec | items | domains | domains_unique | error |
|---|:---:|:---:|:---:|:---:|:---:|
| vertex | O (`call_vertex`) | O | O | O | O |
| legacy | O (`call_legacy`) | O | O | O | O |
| **semantic_scholar** | O (신규 `call_semantic_scholar`) | O | O | O | O |
| **openalex** | O (신규 `call_openalex`) | O | O | O | O |

→ Step C `c_verification.json` schema 확장. §academic-3 baseline (`vertex` / `legacy` 2개) + 신규 (`semantic_scholar` / `openalex` 2개) 4-backend 동시 박제 — academic-en single query 5 runs 의 분포 변화 정량 비교 정합 (catch 58 처분 정합: single query 유지).

### B4-4 catch 58 처분 (single query 유지)

- 본 cycle measure_ab.py 변경 X 영역 (catch 58 multi-query 확장은 §academic-5 이전).
- 단, run_single() 내 ss/oa 호출 분기 추가 (mode="academic" AND q_lang!="ko") 는 **driver 단순 확장** 영역으로 catch 58 처분과 직교.

### B4-5 변경 면적 추정

| 파일 | logical line | cosmetic | 비고 |
|---|---:|---:|---|
| `.env.openalex` (신규) | +2 | +1 | placeholder + mailto |
| `.env.semanticscholar` (신규) | +1 | +1 | mailto only (key 추후) |
| `scripts/§academic-1/measure_ab.py` 확장 | ~+30~40 | +3 | `call_semantic_scholar` + `call_openalex` 함수 (`call_vertex`/`call_legacy` 패턴 답습) + `run_single` 분기 |
| `core/config.py` env loading chain | ~+4~6 | – | `.env.openalex` / `.env.semanticscholar` 추가 |
| **B4 net logical** | **~+37~49** | +5 | – |

---

## 6. catch 60 후보 박제 (Step B 진행 중 발견)

> 본 design 진행 중 점검한 4 영역 (60-a / 60-b / 60-c / 60-d) 의 처분.

### 60-a — STOP gate 정밀도 (Issue 5 처분 분기 가능)

- **처분**: 본 design 의 Section 1 (Issue 5) 정의 — "STOP gate 호출 횟수 = successful call 기준" — 으로 해소. 별도 catch 박제 불필요. **본 cycle 안 처분 완료**.

### 60-b — Multi-backend dedup 정합성 (prefix 변형 / subdomain edge case)

- **발화 영역**: `sciencedirect.com` vs `www.sciencedirect.com` vs `linkinghub.elsevier.com` (DOI redirect 변형) — pilot raw OA `landing_page_url = https://doi.org/10.1016/j.jbusres.2016.04.181` 의 실제 redirect chain 검증 필요.
- **처분 안**: B3 `_domain_of` 헬퍼에서 host normalize (`www.` / `m.` 제거) + redirect resolve (vertex `_resolve_vertex_redirect` 패턴 답습) 적용 시 해소 가능. **catch 60 후보 박제** (Step C 측정 시 unknown publisher 패턴과 함께 모니터링).

### 60-c — API response schema versioning 대응 layer

- **발화 영역**: OpenAlex `host_venue` (deprecated, 2025) → `primary_location.source.display_name` (신규). Semantic Scholar Graph API v1 도 향후 v2 변경 가능성.
- **처분 안**: `extract_domain_from_paper` 의 4-step early-return 자체가 schema 변경에 robust (필드 1개 사라져도 다음 path fallback). 단 `primary_location` 자체가 사라지면 affect → 명시적 schema version 체크는 본 cycle 미도입. **catch 60 후보 박제** (Step C 측정 후 재평가).

### 60-d — OA credit 소비 monitor (free tier $1/day)

- **발화 영역**: OpenAlex free tier $1/day = 100k req/day. `?search=` list call = 10 credit. measure_ab.py 5 runs × 1 query (single, catch 58 유지) × 1 backend = 50 credit per 측정. **임계 100k 의 0.05% 영역**, free tier 충분.
- **처분 안**: 본 cycle 안에서 monitoring driver 도입 불필요 (사용량 임계 영역 거의 무한대). 단 Step C 측정 시 OA response 의 `meta.cost_usd` 필드 log 박제 권고. **catch 60 후보 박제** (Step C 측정 driver 의 부수 출력 영역).

---

## 7. commit 2 — onboarding + smoke driver 자산화 (§academic-4 Step C-1 commit 2 보강)

### 7-1 env onboarding (STOP-C-7 정합, `.env.*.example` 패턴 채택)

표준 onboarding 패턴 — `.env.*.example` (placeholder template, commit 영역) → 사용자 측 cp 후 실제 key 값 주입 (`.env.<provider>` untracked 유지):

```
cp writer_project/.env.openalex.example writer_project/.env.openalex
# edit writer_project/.env.openalex 만 → OPENALEX_API_KEY=<발급값> 주입
#                                       OPENALEX_MAILTO=sungsu.oh@bellcomm.co.kr 확인

cp writer_project/.env.semanticscholar.example writer_project/.env.semanticscholar
# edit writer_project/.env.semanticscholar 만 →
#   1B 단계 (commit 2 활성): SEMANTIC_SCHOLAR_API_KEY=<발급값> 주입 + SKIP=0
#   1A_prime fallback: SEMANTIC_SCHOLAR_SKIP=1 (anonymous pool throttle isolation 시점)
```

`.gitignore` 정합 — `.env.*` ignore 패턴 + `!.env.*.example` negation 1 line 추가 (line 19), `.env.<provider>` 실제 key 파일은 untracked 유지.

**⚠️ STOP-C-7 lesson 보강 (§academic-4 commit 2 영역, 사용자 실수 사전 차단 영역)**:
- `.example` 파일은 **commit 영역 placeholder template 전용** — 실제 key 값 절대 박제 금지
- 사용자 측 IDE/linter 가 자동으로 `.example` 파일에 실제 key 박제할 risk → onboarding 패턴 `cp .env.*.example .env.<provider>` 직후 `.env.<provider>` 만 edit, `.env.*.example` 은 read-only 보존 권고
- commit staging 직전 `git diff --cached writer_project/.env.*.example` 1 회 확인 — placeholder (`KEY=` empty) 정합 검증 단계 강제
- 실제 key 박제 사고 발생 시 즉시 revoke + 재발급 영역 (commit/push 진입 전 staging 영역 검사 필수)

### 7-2 smoke driver 자산화 (writer_project/scripts/§academic-4/smoke/)

| driver | 용도 |
|---|---|
| `smoke_ss.py` | SS skip 토글 검증 (default 1) + catch 61 진입 시 authenticated pool 재검증 |
| `smoke_oa.py` | OA mailto polite pool + api_key 활성 검증 + cost_usd 박제 |

실행 (사용자 측 PowerShell, **cwd 무관** — driver 안 `Path(__file__).resolve().parents[3]` 으로 writer_project root 자동 해소):

```powershell
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"

# SS smoke (1B 단계 activate 또는 1A_prime SKIP 검증)
# 사전: writer_project/.env.semanticscholar 안 SEMANTIC_SCHOLAR_API_KEY + MAILTO + SKIP 주입 정합
.venv_vertex\Scripts\python.exe writer_project/scripts/§academic-4/smoke/smoke_ss.py

# OA smoke (mailto polite pool + api_key 활성 검증)
# 사전: writer_project/.env.openalex 안 OPENALEX_API_KEY + MAILTO 주입 정합
.venv_vertex\Scripts\python.exe writer_project/scripts/§academic-4/smoke/smoke_oa.py
```

driver 정합 패턴 (commit 2 update, **catch 64 lesson 정합**):
- `WRITER_PROJECT_DIR = Path(__file__).resolve().parents[3]` — cwd 무관 절대 경로
- `load_dotenv(WRITER_PROJECT_DIR / '.env.<provider>', override=True)` — **override=True 필수**: PowerShell session 잔존 `$env:*` (catch 64 lesson) 을 `.env.<provider>` 값으로 덮어쓰기. 잔존 영역 사례: 이전 turn 의 `$env:SEMANTIC_SCHOLAR_SKIP=1` 가 새 session 까지 잔존 시 `.env` 의 `SKIP=0` 가 무시됨.

1B 단계 진입 후 SS key 재 smoke / OA mailto polite pool 정합 — 본 smoke driver 재실행 만 으로 검증 가능 (코드 변경 X).

### catch 60 등록 결정

- **60-a 처분 완료** (본 design 안 해소)
- **60-b / 60-c / 60-d 후보 박제** (Step C 측정 후 재평가, 본 cycle 의 catch 60 entry 등록은 사용자 컨펌 시점에 결정)

---

## 7. Design summary + Step C 진입 조건

### 변경 면적 총합 (catch 48 컨벤션)

| Step B 영역 | logical line | cosmetic | 파일 |
|---|---:|---:|---:|
| B1 module 설계 (semantic_scholar.py + openalex.py) | ~+180~220 | +16 | 2 |
| B3 도메인 추출 + catch 59 table (`_scholarly_domain.py`) | ~+80~120 | +6 | 1 |
| B2 routing 통합 patch (`agent/web_search.py`) | ~+55~75 | +6 | 1 |
| B4 env + driver 확장 (`measure_ab.py` + `.env.*` + `core/config.py`) | ~+37~49 | +5 | 4 |
| **Step C-1 net logical 합** | **~+352~464** | +33 | **8 file 변경 (3 신규 + 5 기존)** |

§academic-3 의 +31 line (set 보강) 과 비교: 본 cycle 은 신규 module 2 + helper module 1 영역으로 면적 차수 다름 (~12x). Step C-1 commit chain 분할 가능성 검토 영역 (single commit vs B1/B2/B3/B4 분할).

### Step C 진입 조건

- ✅ design spec 완성 (B1~B4 4 영역)
- ✅ 사용자 컨펌 4 sub-decisions 박제 (1A / 우선순위 / 3A / 4A)
- ✅ Issue 3 baseline 명세 + Issue 5 STOP gate 정의 보강
- ✅ catch 59 정적 매핑 table 35 entries 박제
- ✅ catch 60 후보 4 영역 점검 (60-a 처분 / 60-b/c/d 후보 보존)
- ✅ pilot raw 4 entries 도메인 추출 path 검증 (3/4 hit + 1 logging fallback)
- 사용자 컨펌 영역 (Step C-1 진입 전):
  - OpenAlex API key 발급 + `.env.openalex` 의 placeholder 실제 값 주입 (30초)
  - Step C-1 commit 분할 정책 (single vs B1/B2/B3/B4 분할)
  - Step C-2 측정 spec (single query 유지, 5 runs × 3 topic 답습)

### Risk 박제 (PARTIAL 가능성 사전 정량)

§academic-3 Step B follow-up 의 "Risk 박제" 패턴 답습 (예상 0.31 ↔ 실측 0.3165 정합 사례):

- **본 cycle 예상 academic-en ratio (1B 활성 단계 update, commit 2 SS+OA 정량 근거 반영)**:
  · 1B 단계 (SS authenticated pool + OA polite pool 합류): vertex+legacy+ss+oa 합집합 → **실측 예상 0.45~0.83** (PARTIAL 가능성 ~25~35%, **보수 영역**)
  · 보수 영역 사유: commit 2 SS smoke domains_unique 안 학술 분야 분포가 multidisciplinary (`economics.pubmedia.id` / `ijsrem.com` / `ssrn.com` 등) 영역까지 확장 — 분자 (ACADEMIC_DOMAINS 정합 도메인) 비율은 OA 단독 (5/5 = 100%) 대비 SS 합류 시 dilution. catch 59 logging fallback 비율 차이: OA 0% (10/10 hit) ↔ SS 30% (7/10 hit, `10.63075` / `10.36948` / `10.32535` 소형 OA prefix 미매핑). Step C-2 측정 후 fallback prefix 보강 cycle 영역에서 추가 매핑 검토.
  · 비교 baseline: §academic-3 close 시점 ratio 0.3165 (vertex+legacy 만) → 본 cycle 1B 단계 예상 하한 0.45 도 +0.13 marginal 개선, 임계 0.6 충족 영역은 중간~상한 영역 (~0.60~0.83) 의존
- **PARTIAL 발생 시 root cause 분리 영역**:
  · SS skip 단계 dilution (학술 venue 7~10 entries 손실 → academic_set 축소, OA 단독으로는 보완 마진 좁음)
  · ss/oa 도메인 unique 가 dedup 후 7~10 entries (vertex 5 dilution 효과)
  · catch 59 unknown DOI prefix logging fallback 비율 (commit 1 smoke 시점 0% — 직전 fallback 3건 `10.1177/` ×2 + `10.21511/` 모두 본 cycle hit 으로 전환, 37 entries 정합 effectiveness 검증)
  · OA credit fail / SS 429 fail 시 dilution
- **PARTIAL 대응 권고**: (1) SS key 발급 가속화 → 1A' 활성 단계 진입, (2) catch 60-b/c (dedup 정합성 + schema version) 점검, (3) 미달 시 catch 58 (multi-query) §academic-5 이전 가속화

### catch 표기 inline reference

- **catch 51** (EN academic mode 학술 전용 backend 부재, Option 5 S1 권고) — 본 cycle 대상
- **catch 52** (ACADEMIC_DOMAINS_29 set 보강, §academic-3 완료) — 본 cycle 의존 (36 set 매칭 + catch 59 정합 검증)
- **catch 43** (language-aware backend routing, §academic-1 완료) — 본 cycle 자연 확장
- **catch 57** (audit cycle 외부 환경 사전 점검 lesson + anonymous pool reality check + mailto consistency) — Issue 5 STOP gate 정의 보강 + commit 1 smoke 3 attempts 429 재현 → SS anonymous shared pool production 부적합 박제
- **catch 58** (academic-en 측정 토픽 단일성, §academic-5 이전) — 본 cycle 측정 driver 변경 X
- **catch 59** (DOI publisher 매핑, 3A 정적 table 채택) — 본 design B3 박제 (37 entries, 10.1177/ SAGE 메인 + 10.21511/ 보강 정합)
- **catch 60 후보** (60-b dedup 정합성 / 60-c schema versioning / 60-d OA credit monitor) — Step C 측정 후 재평가
- **catch 61 후보** (SS authenticated pool 활성 layer, `SEMANTIC_SCHOLAR_API_KEY` + `x-api-key` 헤더 박제) — SS key 발급 응답 회신 시 진입, 본 cycle Sub-decision 1A' default skip 단계의 후속

### scope creep 가드 (STOP-B-3 정합)

- catch 45 (Journal of Advertising 영역) · catch 53 (semanticscholar.org subdomain 매칭) — 본 cycle 미진입 정합.

---

*draft 완성 — 사용자 컨펌 대기 (STOP-B-1 정합, commit 금지)*
