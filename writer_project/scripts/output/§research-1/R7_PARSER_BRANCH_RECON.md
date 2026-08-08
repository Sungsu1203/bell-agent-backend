# R7 — 파서 분배기 분기 조건 정찰 (§research-1 선분 3 · 정찰 4 · C 게이트)

> 2026-08-08 · 읽기 전용 · 코드 수정 0 · 커밋 0 · 유료 API 0 · 네트워크 0
> 코드 검색 전량 `command grep` (catch CG). 좁히는 단계는 **구간 통째 덤프** (§9).
> 탐침은 파이프라인이 읽는 것과 같은 파일을 읽었다 (catch CI).
> **판정 없음.** 표와 실측치만. 미확인은 미확인으로 표기.

---

## 0. 질문과 답의 형태

> `ingest_docs.py:260` 분배기가 **무엇을 보고** 갈래 ①(`:386`) / ②(`ingest.py:677`)를 고르는가.

**한 문장 답(근거는 §1~§2)**: `item["raw_content"]` 문자열의 **truthy 여부** 하나다(`:382`).
설정값·인자·백엔드 종류를 보지 않는다.

⚠️ 그런데 이 질문을 풀다가 **§2 가설의 전제 하나가 실측과 어긋났다.** §2에 별도로 적는다.

---

# 1-a. `:260` 분배기 — 분기 조건부 통째 덤프

## 1-a-1. 진입부: 조건에 쓰이는 값 4개가 여기서 확정된다

```python
291	    for item in results or []:
292	        url: str          = (item.get("source") or item.get("url") or "").strip()
293	        title: str        = (item.get("title") or "").strip()
294	        item_content: str = (item.get("content") or "").strip()
295	        raw_content: str  = (item.get("raw_content") or "").strip()
```

| 값 | 출처 | 조건에서의 역할 |
|---|---|---|
| `url` | `item["source"]` → 없으면 `item["url"]` | 분기 0 · 1 · 3 |
| `raw_content` | `item["raw_content"]` | **분기 2 — 이 정찰의 핵심** |
| `item_content` | `item["content"]` | 분기 0 · 1 · 5 |
| `title` | `item["title"]` | 조건 아님(메타에만) |

> **전부 `item` dict의 키다.** 함수 인자·CFG·env·전역 상태를 조건으로 쓰는 곳이 **0건**이다.
> ⇒ 분기 선택은 **입력 JSON 레코드의 내용만으로 결정된다.**

## 1-a-2. 분기 6개 — 조건문 원문

```python
297	        if not url:                                    ← 분기 0
298	            if item_content: …append(text/plain)…
303	            continue

305	        try:
307	            if _ingest_mod is not None:
308	                url = _ingest_mod._normalize_before_request(url)
333	                if url and _ingest_mod._is_noise_url(url):     ← 조기 드랍(kpanet 2조건 전용)
335	                    continue
338	            if url and url in _seen_urls:                      ← 중복 URL 드랍
339	                continue
343	            parsed = urlparse(url)
344	            scheme = (parsed.scheme or "").lower()
348	            if parsed.path:                                    ← PDF/PPTX 파일단위 중복 드랍
350	                if lp.endswith(".pdf") or lp.endswith(".pptx"): …

364	            if scheme == "file":                       ← 분기 1  (bs4 미경유)
365	                if not item_content: continue
370	                …append(content_type=확장자 추정)…
379	                continue

382	            if raw_content:                            ← 🔴 분기 2  (bs4 사본 ①, :386)
385	                    soup = BeautifulSoup(raw_content, "lxml")
395	                if text:
396	                    …append(content_type="text/html")…
400	                    continue

403	            if _looks_like_pdf_url(url_no_frag) and _ingest_mod is not None:   ← 분기 3
407	                pdf_bytes = _ingest_mod._fetch_binary(url_no_frag)
417	                if pdf_text and len(pdf_text.strip()) >= 30:
418	                    …append(content_type="application/pdf")…
429	                    continue

461	            html_text: str = ""                        ← 분기 4
465	            if _ingest_mod is not None and hasattr(_ingest_mod, "_load_html_as_text"):
468	                    html_text = _ingest_mod._load_html_as_text(url_no_frag)   ← 4-1: bs4 사본 ②(ingest.py:677)
476	            if not html_text:
479	                    from tools.web_rag.ingest_net import fetch_text as _fetch_text
480	                    raw_html = _fetch_text(url_no_frag)
484	                if raw_html:
485	                    html_text = _load_html_as_text(raw_html, url_no_frag)     ← 4-2: 사본 ③(_clean_text)
487	            if html_text:
488	                …append(content_type="text/html")…
492	                continue

494	            if item_content:                           ← 분기 5 (최종 폴백)
496	                …append(content_type="text/plain")…
```

## 1-a-3. 조건 성격표

| 분기 | 조건 | 검사 대상 | 인자/설정 개입 |
|---|---|---|---|
| 0 | `not url` | **값의 유무** | 없음 |
| 1 | `scheme == "file"` | **값의 형태**(URL scheme) | 없음 |
| **2** | **`if raw_content:`** | **값의 유무**(빈 문자열 = False) | **없음** |
| 3 | `_looks_like_pdf_url(url)` | **값의 형태**(정규식 `utils.py:592`) | 없음 |
| 4 | (조건 없음 — 위 전부 미해당 시 도달) | — | `hasattr(_ingest_mod,…)` 만 |
| 5 | `if item_content:` | 값의 유무 | 없음 |

> 🔴 **`raw_content` 조건은 길이·품질·형식을 안 본다.** 파이썬 truthy — 빈 문자열이면 False, 1글자여도 True.
> `.strip()`(`:295`)이 공백만 있는 경우를 걸러낸다.
> ⇒ **1바이트라도 들어 있으면 갈래 ①이 확정되고, 비면 갈래 ③ 또는 ②로 넘어간다.**
> 설정으로 이 선택을 바꿀 수단은 **없다**(env·CFG 참조 0건).

---

# 1-b. 그 조건값이 실제 실행에서 어떻게 채워지는가

## 1-b-1. 수집 시점 — 백엔드는 `raw_content`를 주지 않는다

`command grep -rn "raw_content" --include="*.py" .` 전량 중 **결과 조립 지점**:

| 위치 | 값 |
|---|---|
| `search.py:609` | Tavily 호출 인자 **`include_raw_content=False`** |
| `search.py:625` (tavily) | `"raw_content": ""` |
| `search.py:709` · `:783` · `:818` · `:887` (google/serpapi/naver 등) | `"raw_content": ""` |
| `agent/web_search.py:809` (vertex grounding) | `"raw_content": ""` |
| `agent/web_search.py:912` (scholarly fan-out) | `"raw_content": ""` |

> **어느 백엔드도 `raw_content`를 채워 반환하지 않는다. 전부 빈 문자열로 초기화된다.**

## 1-b-2. 채우는 곳은 별도 단계 — `_enrich_raw_content`

```python
536	def _enrich_raw_content(items, *, timeout: int = 20) -> None:
550	            # 이미 채워진 경우 스킵
551	            if it.get("raw_content"): continue
554	            if looks_like_pdf_url(u):
555	                pdf_bytes = _fetch_pdf_once(u, timeout=timeout)
556	                if pdf_bytes:
557	                    it["raw_content"] = ""      ← 🔴 PDF는 의도적으로 비운다(파서 단계로 위임)
558	                    it["raw_bytes"] = len(pdf_bytes)
559	                    it["content_type"] = … "application/pdf"
560	                else:
563	                    r = http_get(u, timeout=timeout)      ← SSL 실패 시 HTML 폴백 1회
565	                        it["raw_content"] = r.text or ""
568	            else:
570	                r = http_get(u, timeout=timeout)          ← 비-PDF: HTML 1회
572	                if r is not None: it["raw_content"] = r.text or ""
```

⇒ **`raw_content`는 검색 응답이 아니라 별도 HTTP fetch로 채워진다.**
⇒ **PDF URL은 성공하면 오히려 `""`가 된다** → 분배기에서 분기 2를 건너뛰고 **분기 3**으로 간다. 설계된 동작이다.

## 1-b-3. `web_search`(search.py) 말미 5단계 순서

```
1854	    results = _filter_non_2xx(results, …)
1855	    _enrich_raw_content(results)                 ← raw_content 채움 (메모리)
1856	    results = [… normalize_or_block_intermediate_news …]
1857	    _annotate_fetch_meta(results)                ← raw_bytes / fetched_at 기록
1860	    path = _save_results(results, query=…, base_dir=str(research_base_dir()))
1889	    return results, path
```

`_annotate_fetch_meta`(`:506-522`)는 **`raw_content`가 비어 있지 않을 때만** `raw_bytes`·`fetched_at`을 남긴다(`:510`).
→ **`raw_bytes`의 존재 = "이 시점 메모리에 raw_content가 있었다"의 증거.**

## 1-b-4. 🔴 저장 시점에 잘린다 — `_to_safe_json_record`

`_save_results`(`utils.py:600`)는 `:641`에서 `safe_items = [_to_safe_json_record(x) for x in items]`를 만든다.

```python
553	def _to_safe_json_record(it):
560	    d = dict(it or {})                       ← 🔴 새 dict. 원본 items는 안 바뀐다
564	    if isinstance(raw, (bytes, bytearray)):
565	        d["raw_b64"] = …; d["raw_is_binary"] = True; d.pop("raw_content", None)
570	    elif isinstance(raw, str) and _looks_binary_text(raw):
572	        d["raw_b64"] = …; d.pop("raw_content", None)
579	    else:
581	        if isinstance(raw, str) and len(raw) > 4000:
582	            d["raw_preview"] = raw[:4000]
583	            d.pop("raw_content", None)       ← 🔴 4000자 초과면 raw_content 삭제
```

## 1-b-5. 실측 — 위 메커니즘이 실제로 발동했다

`research/resources_*.json` 72파일 · 490레코드. 그중 **색인 118 source에 속한 레코드 250건**:

| 지표 | 값 |
|---|---|
| 색인 118 URL 커버 | **118 / 118** |
| `raw_content` > 0 인 URL | **0 / 118** |
| `raw_preview` > 0 인 URL | **113 / 118** |
| `raw_preview` 길이가 **정확히 4000** | **113 / 113** (= `raw[:4000]` 상한) |
| `raw_bytes` > 0 인 URL | **114 / 118** (min 14,584 · max 16,569,880) |
| `raw_bytes`·`raw_preview` **둘 다 0** | **4 / 118** |
| 전 레코드에서 살아남은 `raw_content` 길이 | 182건, min 114 · max **2,953** · **> 4000 = 0건** |

키 출현(490레코드): `raw_content` 209 · `raw_preview` **276** · `raw_b64` 5 · `raw_is_binary` 5 · `raw_bytes` 481

> ⇒ **`_to_safe_json_record:581-583`의 4000자 절단이 실제로 발동했다.**
> `raw_bytes` 14KB~16MB가 **수집 시점 메모리에는 HTML이 있었다**는 증거이고,
> 살아남은 `raw_content`가 전건 2,953자 이하인 것이 **4000 규칙이 예외 없이 적용됐다**는 증거다.

## 1-b-6. 🔴 그런데 ingest는 이 파일을 읽지 않는다

`agent/web_search.py` 내 `ret` 할당 전수(`web_search_agent` 몸통 181~940 스캔):

| 행 | 문장 |
|---|---|
| `:805` | `combined_items.append({…})` (vertex grounding) |
| `:840` | `legacy_ret = web_search.invoke(payload)` ← `from tools.web_rag.search import web_search`(`:29`) |
| `:848` | `legacy_items = list(legacy_ret[0] or [])` ← **`legacy_ret[1]`(path)은 버려진다** |
| `:867` | `combined_items.extend(…)` |
| `:908` | `combined_items.append({…})` (scholarly) |
| **`:934`** | **`ret = combined_items`** ← `ret` 할당은 **이 1곳뿐** |

이어서 return 정규화:

```python
940	                items: list[dict] = []
941	                json_path: str = ""
943	                    if isinstance(ret, tuple) and len(ret) >= 2:
944	                        items = list(ret[0] or []); json_path = str(ret[1] or "")
946	                    elif isinstance(ret, list):
947	                        items = list(ret)
948	                        json_path = ""                    ← 🔴 list 이므로 여기로 간다
957	                # 1-2) Path fallback: Save if path is missing
958	                if not json_path:
966	                        with open(forced_path, "w", encoding="utf-8") as f:
967	                            json.dump(items or [], f, ensure_ascii=False)   ← 🔴 _to_safe_json_record 미경유
968	                        json_path = str(forced_path)
```

> ⇒ `ret`은 **항상 list**이므로 `json_path`는 **항상 `""`**, 따라서 **fallback writer(`:966-967`)가 항상 발동한다.**
> 이 writer는 `_to_safe_json_record`를 거치지 않는다 → **`raw_content`가 보존된다.**

**런타임 실증 — `logs/run_full.log` (864KB, 2026-06-01 ~ 2026-08-01)**

라운드마다 **두 파일이 모두** 생성된다:
```
:93   [tools.web_rag.utils]  [web_search] results saved → …/research/resources_2026_06_01_175015_….json (items=4)
:105  [agent.web_search]     [web_search] saved -> …/resources/venfobel-vitamin/web_1780303815_e116e749.json
:104  [agent.web_search]     [web_search][fallback save] path=…/resources/venfobel-vitamin/web_1780303815_e116e749.json items=4
```
그리고 **ingest가 읽는 것은 후자뿐**이다:
```
:109  [tools.web_rag.ingest_docs] web_page_json_to_documents: 4 docs from …/web_1780303815_e116e749_filtered.json
```

| 확인 | 값 |
|---|---|
| `[fallback save]` 로그 | **전 라운드 발생** (venfobel 5건 · experiential-marketing-media 다수) |
| `web_page_json_to_documents: … docs from` 총 | **65행** |
| 그중 `_filtered.json` | **61행** |
| 나머지 4행 | `local_2026_06_01_175059.json` · `local_2026_08_01_153636.json` (local 경로) |
| `research/resources_*.json`을 읽은 로그 | **0행** |

> ⇒ **`research/resources_*.json`은 스냅샷 전용이고 ingest 입력이 아니다.**
> R5 §4-2가 이 파일의 `raw_content` 0자를 근거로 삼은 것은 **파이프라인이 안 읽는 파일을 잰 것**이다(catch CI 계열).
> `resources/<slug>/web_*.json`(fallback writer 산출)의 `raw_content`는 R5 실측에서 **138/138 존재, 최대 217,749자**였다.

## 1-b-7. 최종 사슬

```
백엔드 응답            raw_content = ""                     (search.py:625/709/783/818/887, web_search.py:809/912)
   ↓
_enrich_raw_content   HTTP fetch → raw_content = 전체 HTML   (search.py:1855)   ※ PDF는 의도적으로 "" (:557)
   ↓
_annotate_fetch_meta  raw_bytes / fetched_at 기록            (search.py:1857)
   ↓
_save_results         ┌ 사본을 만들어 4000자 초과분 pop      (utils.py:641 → :581-583)
                      └ → research/resources_*.json          ✖ ingest 미사용 (막다른 길)
   ↓ (원본 items는 그대로)
return results, path  path 는 web_search.py:848 에서 버려짐   (search.py:1889)
   ↓
ret = combined_items (list) → json_path = ""                 (web_search.py:934 → :948)
   ↓
fallback writer       json.dump(items) — 절단 없음            (web_search.py:966-967)
                      → resources/<slug>/web_<ts>_<sig>.json  ✅ raw_content 보존
   ↓
_filter_json_by_domain  재읽기 → json.dumps(filtered)         (web_search.py:536-557)
                      → …_filtered.json                       ✅ 보존
   ↓
add_web_pages_json_to_chroma → web_page_json_to_documents → web_results_to_documents
   ↓
:295 raw_content = item["raw_content"]  →  :382 if raw_content:
```

## 1-b-8. 조건값이 각 갈래로 가는 경우

| `raw_content` 상태 | 원인 | 도달 갈래 |
|---|---|---|
| 전체 HTML (truthy) | `_enrich_raw_content` HTML fetch 성공 | **① `:386`** |
| `""` (falsy) | PDF URL + `try_fetch_pdf` 성공 → **의도적 공백**(`:557`) | ③ PDF 파서 `:403` |
| `""` | `http_get` 실패/예외 (`:566` `:573` 무시) | **② `ingest.py:677`** (분기 4-1) |
| `""` | URL이 `file://` | ① 이전에 분기 1에서 종료 |

**색인 118 URL에 대한 간접 지표** (`raw_bytes` = enrich 성공 흔적, §1-b-5 표)

| | 건수 | 시사하는 갈래 |
|---|---|---|
| `raw_bytes` > 0 | **114 / 118** | ① 또는 ③ |
| `raw_bytes` = 0 이고 `raw_preview` = 0 | **4 / 118** | ② 또는 ⑤ |

⚠️ **이것은 시사이지 확정이 아니다.** `raw_bytes`는 `_save_results` 사본에서 읽은 값이고,
실제로 ingest에 들어간 fallback 파일은 **색인 118건분이 디스크에 남아 있지 않다**(§3 #1).

## 1-b-9. 🔴 잔여 확인 — `*_filtered.json`은 남는다 (측정 설계 입력)

### (a-1) 삭제·정리 코드 — 없다

`command grep -rn "_filtered" --include="*.py" .` → **2행뿐**:

| 행 | 내용 |
|---|---|
| `agent/web_search.py:552` | `out = p.with_name(p.stem + "_filtered" + p.suffix)` — **생성** |
| `scripts/§paper-writer-1/measure_paper.py:12` | 주석의 `vertex_filtered_ratio` (무관) |

`os.remove` / `.unlink()` / `shutil.rmtree` 전량(레포 14행) 중 대상 확인:

| 위치 | 삭제 대상 | `*_filtered.json` 관련 |
|---|---|---|
| `ingest.py:752` · `:784` · `ingest_vector.py:112` | `stored_urls__<kind>__<ns>.json` 캐시 | ✖ |
| `utils.py:534` | seen-hash 파일 | ✖ |
| `agent/web_search.py:520` | `_move_with_fallback`의 **원본**(copyfile 성공 후) | ✖ (필터 전 파일) |
| `ingest_vector.py:705` · `:822` | Chroma persist 디렉터리 | ✖ |
| `tools/metrics.py:144` · `scripts/*` | 메트릭·측정 드라이버 | ✖ |

> ⇒ **`*_filtered.json`을 지우는 코드가 레포에 없다.** 쓰기만 하고 방치한다.

### (a-2) 디스크 잔존 실측

| 항목 | 값 |
|---|---|
| 총 건수 | **43** |
| 토픽별 | `experiential-marketing-media` **38** · `venfobel-vitamin` **5** |
| mtime 범위 | 2026-06-01 17:50:15 ~ **2026-08-01 15:38:31** |
| 크기 min / max / 합 | 2 B / **18,456,699 B** / 19,949,286 B |
| 빈 배열(`[]`) 파일 | **11 / 43** (GATEKEEP kept=0) |
| 총 항목 수 | **80** |

> ⚠️ **로그와 정합한다** — `run_full.log`의 날짜는 06-01·08-01뿐이고, 잔존 파일의 mtime도 같은 두 날이다.
> 07-31분이 없는 이유는 **삭제가 아니라 그 라운드 자체가 이 디스크 상태에 남아 있지 않기 때문**이다.
> 다만 "왜 없는가"는 여전히 미확인(§3 #1).

### (b) 잔존 파일의 `raw_content` 실측 — 절단 흔적 없음

80항목 전수:

| 지표 | 값 |
|---|---|
| `raw_content` 키 보유 | **80 / 80** |
| 길이 min / 중앙값 / max | 0 / 2,813 / **7,962,687** |
| `== 0` | 1 |
| `1 ~ 4000` | 64 |
| **`> 4000`** | **15** ← 절단이 걸렸다면 0이어야 한다 |
| **`== 4000` 정확히** | **0** ← 절단 흔적 |
| `raw_preview` 키 보유 | **0** |
| `raw_b64` / `raw_is_binary` 키 | **0** |

키 출현(80항목): `title`·`url`·`content`·`raw_content`·`source`·`content_type`·`norm_url`·`raw_bytes` 각 80 · `fetched_at` 79.

상위 5건:

| raw_content 길이 | 파일 | URL |
|---|---|---|
| 7,962,687 | `web_1780303828_44d99f9b_filtered.json` | `mfds.go.kr/brd/m_218/down.do?brd_id=data0013` |
| 217,749 | `web_1785566188_b3c8435f_filtered.json` | `blog.naver.com/PostView.nhn?blogId=bizwebkor…` |
| 174,503 | `web_1780303815_e116e749_filtered.json` | `dailypharm.com/user/news/7806` |
| 174,412 | 〃 | `dailypharm.com/Users/News/NewsView.html?dpse…` |
| 118,001 | 〃 | `newsmp.com/news/articleView.html?idxno=231726` |

> ⇒ **§1-b-7 사슬의 실물 확인.** `> 4000`이 15건 살아 있고 `raw_preview`가 0건이므로
> 이 파일들은 `_to_safe_json_record`를 **거치지 않았다**. 같은 라운드의
> `research/resources_*.json` 쪽은 `raw_preview` 276건 · `> 4000` 0건이었다(§1-b-5).
> **두 writer의 산출물이 같은 항목에 대해 정반대 형태로 남아 있다.**

### 측정 설계에 들어가는 값

| 항목 | 값 |
|---|---|
| `*_filtered.json` 재사용 가능성 | 파일은 **지워지지 않는다** — 새 라운드를 돌리면 그 라운드 파일이 **남는다** |
| 현존 43건으로 색인 118 재현 | **불가** — 이 43건의 URL과 색인 118의 교집합은 R5 §4-2 기준 **0** |
| 드리프트 없는 대조 | **새 수집 1회로 만든 `*_filtered.json`을 보존하면**, 같은 파일에서 색인 2벌(현행/크롬제거)을 만들 수 있다 |
| ⚠️ 전제 | `catch CK`(§4 신설) — `:848` path 폐기가 유지되는 동안만 성립 |

---

# 1-c. 두 갈래를 실행 흔적으로 가를 다른 단서가 있는가

## 1-c-1. 메타데이터

| 키 | 갈래 ① (`:396-399`) | 갈래 ② (`:488-491`) | 구분 가능? |
|---|---|---|---|
| `content_type` | `"text/html"` | `"text/html"` | ✖ **동일** |
| `source` / `title` | 동일 형식 | 동일 형식 | ✖ |
| `_promote_item_metadata` 승격 3키 | `backend`·`chunk_domain`·`alt_urls` | 동일 호출 | ✖ |
| **추가 구분 키** | **없음** | **없음** | ✖ |

R4 §2-a 실측 — web 청크 메타 키는 `source`·`title`·`content_type`·`chroma:document` **4종뿐**.
`raw_bytes`·`fetched_at`·`raw_preview`는 **item에만 있고 Document.metadata로 승격되지 않는다**.

## 1-c-2. 로그 문자열

| 갈래 | 성공 시 로그 | 실패 시 로그 |
|---|---|---|
| **① `:382-400`** | **없음 (0건)** | 없음 (`except`가 정규식 폴백으로 조용히 전환, `:391-393`) |
| ③ PDF `:403-459` | 없음 | `:409` `[ingest][pdf] no bytes fetched…` · `:431` `[ingest][pdf] empty/too-short text…` · `:446` `[INGEST][SSL]…` · `:457` `[web_rag] DNS failure…` · `:459` `[web_rag] PDF parse failed; fallback to HTML` |
| **② 4-1 `:465-473`** | **없음** | `:470` `[ingest_docs] ingest._load_html_as_text failed; fallback to local: %s` · `ingest.py:661` `[_load_html_as_text] fetch_text failed url=%s` |
| 4-2 `:476-485` | 없음 | 없음 |
| 공통 | `:503` `web_results_to_documents: %d docs built` (**갈래 무관 총계**) | `:501` `web_results_to_documents item fail (%s)` |

> 🔴 **성공 경로에 로그가 하나도 없다.** 갈래 ①·②·③ 모두 성공하면 침묵한다.
> 존재하는 것은 **실패 로그뿐**이고, 그것도 갈래 ①에는 없다.
> ⇒ **로그로는 "무엇이 실패했나"만 알 수 있고 "무엇이 성공했나"는 알 수 없다.**

**실측** — `logs/run_full.log` 전량 검색

| 문자열 | 파일 히트 |
|---|---|
| `_load_html_as_text` | **0** |
| `PDF parse failed` | **0** |
| `web_results_to_documents:` | 1 (총계 로그) |
| `[fallback save]` | 1 |
| `GATEKEEP` | 1 |

⚠️ `_load_html_as_text` 0건은 **"갈래 ②를 안 탔다"가 아니다.** 그 로그는 **실패 시에만** 찍힌다.
성공했어도 0건이고, 애초에 안 갔어도 0건이다. **구분 불가.**

## 1-c-3. 예외 메시지·부작용

| 단서 | 갈래 ① | 갈래 ② | 구분 가능? |
|---|---|---|---|
| 네트워크 요청 발생 | **없음**(메모리의 HTML 파싱) | **있음**(`ingest_net.fetch_text` → `sess.get`) | ⭕ **원리상 가능** — 단 사후 관측 수단이 이 레포에 없다 |
| 소요 시간 | 빠름 | 느림(HTTP 왕복) | ⭕ 원리상 — 측정치 없음 |
| `bs4` 경고 필터 | 없음 | `XMLParsedAsHTMLWarning` 억제(`ingest.py:669-674`) | ⭕ **XML 문서일 때만** 차이가 드러난다. 관측 사례 없음 |

## 1-c-4. 요약

| 단서 유형 | 갈래 ①/② 구분 |
|---|---|
| 색인 메타데이터 | ✖ 불가 (`content_type` 동일, 추가 키 0) |
| 로그 | ✖ 불가 (성공 로그 부재) |
| 예외 메시지 | ✖ 불가 (①의 except는 조용히 정규식 폴백) |
| 네트워크 발생 여부 | ⭕ 원리상 가능 · **관측 수단 없음** |
| **입력 JSON의 `raw_content`** | ⭕ **가능 — 유일하게 실효적인 단서** |

> ⇒ 갈래를 사후에 가르려면 **그 라운드가 ingest에 넣은 `*_filtered.json`을 봐야 한다.**
> R6 §1-5가 `content_type`으로 못 가른다고 한 것과 일치하며, 여기서 **가를 수 있는 단서 1개를 특정**했다.

---

# 2. ⚠️ §2 가설 검증 결과 — 전제 하나가 어긋났다

> 지시문 가설: *"raw_content가 비면 ①은 파싱할 HTML이 없다 → ②가 본선"*
> 그리고 지시문 자체의 경고: *"저장된 산출물이 0자인 것과 수집 시점 메모리가 0자인 것은 다르다."*

| 층 | 실측 | 상태 |
|---|---|---|
| 수집 시점 메모리 | `raw_bytes` 14,584~16,569,880 (114/118) → **HTML이 있었다** | ✅ 확인 |
| `research/resources_*.json` 저장물 | `raw_content` 0 / `raw_preview` 정확히 4000 (113/118) → **저장 시점 절단** | ✅ 확인 |
| **그 파일이 ingest 입력인가** | 🔴 **아니다.** 로그 65행 중 ingest 입력은 전부 `*_filtered.json`(fallback writer 계보). `research/resources_*` 읽기 **0행** | ✅ 확인 |
| 실제 ingest 입력의 `raw_content` | fallback writer는 `_to_safe_json_record` 미경유 → **보존**. R5가 잰 `web_*.json` 138/138 존재(최대 217,749자) | ✅ 확인 |

> ⇒ **가설의 관측 근거(R5의 0자)는 파이프라인이 읽지 않는 파일에서 나왔다.**
> 지시문이 경고한 "저장물 ≠ 메모리"보다 한 겹 더 있었다 — **"저장물이 여럿이고, 그중 하나만 읽힌다."**
> 코드 경로상 **①이 기본이고 ②는 enrich 실패 시의 폴백**이라는 그림이 나오지만,
> **색인 118건에 대한 직접 확인은 불가하다**(§3 #1). **확정으로 올리지 않는다.**

### C 게이트 비용에 미치는 영향 (계산만, 판정 없음)

| 시나리오 | 조건 | published_date 비용 |
|---|---|---|
| 갈래 ①이 본선 | `_enrich_raw_content` HTML fetch 성공 | `ingest_docs.py:385~390` 구간에서 `soup`에 접근, `:398` 메타 dict에 1키 추가 |
| 갈래 ②로 떨어짐 | enrich 실패 | `ingest.py:642`의 `-> str` 계약 변경 + 호출부 `ingest_docs.py:468` 수신부 변경 |
| PDF | `looks_like_pdf_url` 참 | 분기 3 — **양쪽 다 해당 없음.** 별도 경로 |

⚠️ **두 갈래는 배타적이지 않다.** 같은 라운드 안에서 URL마다 다른 갈래로 간다.
`raw_bytes` 지표 기준 색인 118 중 **114 : 4** 로 갈릴 가능성이 있으나 §3 #1 때문에 미확정.

---

# 3. 미확인 항목 (판정 보류)

| # | 미확인 | 왜 이번에 못 정했나 |
|---|---|---|
| 1 | 🔴 **색인 118건이 실제로 어느 갈래로 들어왔는가** | 그 라운드의 `web_*_filtered.json`이 디스크에 없다. `logs/run_full.log`의 날짜는 **2026-06-01과 2026-08-01뿐**(`command grep -oE "^2026-[0-9]{2}-[0-9]{2}" \| sort -u`), 색인 생성 추정 시점 07-31이 **로그에 없다**.<br>⚠️ §1-b-9로 **원인 하나는 소거됐다** — 삭제 코드가 없으므로 "정리되어 사라졌다"는 아니다. 남은 갈래: ①07-31 라운드가 다른 경로/디스크 상태에서 돌았다 ②색인이 07-31이 아닌 다른 시점 산출이다. **둘 다 미확인** |
| 2 | 현존 `web_*.json` 17 URL이 색인 118과 교집합 0인 이유 | R5 §6 #9 이월. 이번에도 미해소 |
| 3 | `_enrich_raw_content`의 URL별 성공/실패 실물 | `http_get` 실패는 `:566`/`:573`에서 조용히 무시된다. 로그 0건 |
| 4 | `raw_bytes`·`raw_preview` 둘 다 0인 4건의 원인 | enrich 실패 / 응답 빈 문자열 / 비-2xx 필터 통과 후 실패 등 구분 불가 |
| 5 | `_save_results` 산출물이 `resources/<slug>/`로 이동되지 않고 `research/`에 72건 남은 이유 | `web_search.py:988`의 abspath 비교상 이동이 일어나야 하나, 실제로는 `json_path`가 이미 `res_dir` 아래(fallback 산출)라 비교가 같아져 이동이 생략된 것으로 보인다. **로그로 재확인 안 함** |
| 6 | 갈래 ①의 `except`(`:391`) 정규식 폴백이 실제로 발동한 사례 | 로그가 없어 관측 불가 |
| 7 | 118 URL의 `<head>` 날짜 메타 **실제 보유율** | R6 §2 이월. 본문 미독 규율로 이번에도 미측정 |
| 8 | `_looks_binary_text` 판정으로 `raw_b64`가 된 5건의 정체 | 이번 범위 밖 |

---

# 4. 실행한 명령 (재현용)

```bash
type grep

# 1-a 분배기 구간 통째 덤프 (Read 도구)
#   ingest_docs.py 286-325 / 291-505 전 구간 · utils.py 550-599 · search.py 500-584, 1840-1889
#   web_search.py 835-894, 920-1029

# 1-b 조건값 추적
command grep -rn "raw_content" --include="*.py" .
command grep -rn "def _to_safe_json_record\|def _enrich_raw_content\|def _annotate_fetch_meta" --include="*.py" .
command grep -n "from tools.web_rag.search import web_search" agent/web_search.py
../.venv_vertex/bin/python -c "…web_search_agent(181~940) 내 ret/combined_items 할당 전수…"

# 1-b-5 저장물 키 센서스 (표준 라이브러리 json 만, 프로젝트 모듈 import 0)
../.venv_vertex/bin/python -c "…research/resources_*.json vs resources/<slug>/web_*.json 키·길이 롤업…"

# 1-b-6 런타임 실증
command grep -n "fallback save" logs/run_full.log
command grep -n "web_page_json_to_documents:" logs/run_full.log
command grep -c "docs from .*_filtered.json" logs/run_full.log
command grep -oE "^2026-[0-9]{2}-[0-9]{2}" logs/run_full.log | sort -u

# 1-c 갈래 판별 단서
command grep -n "logger\." tools/web_rag/ingest_docs.py
for s in "_load_html_as_text" "PDF parse failed" "GATEKEEP"; do command grep -rl "$s" logs/; done

# 1-b-9 잔여 확인
command grep -rn "_filtered" --include="*.py" .
command grep -rnE "os\.remove|\.unlink\(|shutil\.rmtree|os\.rmdir" --include="*.py" .
find . -name "*_filtered.json" | wc -l
../.venv_vertex/bin/python -c "…43파일 80항목 raw_content 길이·키 전수…"
```

**부작용 0** — 코드 수정 0 · 커밋 0 · 유료 API 0 · 네트워크 요청 0 · `PersistentClient` 미호출 ·
Chroma 접근 0 · 프로젝트 모듈 import 0(표준 라이브러리 `json`/`glob`/`collections`만).
파일 생성 = 이 문서 1건.
