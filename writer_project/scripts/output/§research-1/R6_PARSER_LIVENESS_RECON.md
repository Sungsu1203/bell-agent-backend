# R6 — 파서 사본 생사 · published_date 게이트 · 링크로트 · merge_refs 공유범위
## (§research-1 선분 3 · 정찰 3)

> 2026-08-08 · 코드 수정 0 · 커밋 0 · 유료 API 0 · API 키 0
> 네트워크 = §3 링크로트 실측에만 사용(HEAD/GET **상태줄만**, 본문 미독·미저장, 동시요청 3, 요청간 0.4~0.6s)
> 코드 검색 전량 `command grep` (catch CG). `type grep` → 셸 함수(ugrep 심) 확인.
> 소속 함수는 **최상위 `def` 역방향 스캔 + 들여쓰기**로 확정 (catch CF: import ≠ 실행)
> **판정 없음.** 표와 실측치만. 미확인은 미확인으로 표기.

---

## 0. 선행 확인

| 항목 | 결과 |
|---|---|
| `git log --oneline -3` | `5157c4e0` / `96094f22` / `a696777c` — R5 시점과 동일, 새 커밋 없음 |
| `git status --short` | 논문 트랙 미커밋분 상주(변동 없음). 이 세션 신규 = 산출 문서 1건 |
| STANDARDS | §1(ENV) · §3(Chroma) · §4(보호키) · §5(credential) · §6(venv) 통독 |
| GUARDRAILS | 통독. §5(공개 API 파사드) · 시그니처 고정 API 항목이 §4에 직결 |

---

# 1. 🔴 파서 사본 3벌의 생사

## 1-1. 세 앵커의 정체 먼저

| 앵커 | 실물 | 성격 |
|---|---|---|
| `ingest_docs.py:260` | `def web_results_to_documents(results)` | **분배기**(dispatcher). 자체 파싱 없음. 분기 6개로 나눔 |
| `ingest_docs.py:386` | `for tag in soup([...]): tag.decompose()` | **bs4 사본 ①** — 분기 2(`raw_content`) 인라인. 소속 = `web_results_to_documents`(@260), indent=20 |
| `ingest.py:677` | 동일 문장 | **bs4 사본 ②** — `_load_html_as_text(url, timeout)`(@642) 내부, indent=8 |

> ⚠️ **`:386`은 독립 함수가 아니다.** `:260`의 한 분기다 → **자체 호출부를 가질 수 없고**,
> `:260`의 생사에 종속된다. "3벌"은 **함수 3개가 아니라 함수 2개 + 분기 1개**다.

**미등재 4번째** — `ingest_docs.py:146` `_load_html_as_text(html, url="")`.
동명이지만 본문은 `return _clean_text(html)` **1줄**이고 `_clean_text`(`utils.py:1434`)는
NFKC 정규화 + 개행 압축뿐 — **태그 제거를 안 한다.** 분기 4-2 폴백에서만 쓰인다(`:485`).

## 1-2. 호출부 전량 — `web_results_to_documents`

`command grep -rn "web_results_to_documents" --include="*.py" .` → 24행. 주석·`__all__`·재노출을 걷어낸 **실호출 5건**:

| # | 호출부 | 소속 함수 | 분류 |
|---|---|---|---|
| 1 | `ingest_docs.py:611` | `web_page_json_to_documents`(@506) indent=4 | 내부 위임 |
| 2 | `ingest_vector.py:1845` | `seed_web_namespace`(@1789) | **1-4 참조 — 도달 불가** |
| 3 | `scripts/§14-9/fusion_observability.py:159` | 측정 스크립트 | 본선 아님 |
| 4 | `probe_ingest_dryrun.py:21` | probe | 본선 아님 |
| 5 | `probe_ingest_run.py:40` | probe | 본선 아님 |

`web_page_json_to_documents` 실호출 4건:

| 호출부 | 소속 함수 | 분류 |
|---|---|---|
| `ingest_vector.py:1471` | `add_web_pages_json_to_chroma`(@1442) | 색인 본선 |
| `agent/web_search.py:1102` | **`web_search_agent`(@181)** indent=20 | **본선 노드 — preview 용** |
| `tools/local_rag.py:1594` | `ingest_local_files`(@1387) indent=12 | 본선(local) — preview 용 |
| `tools/web_rag/__init__.py:71` | 파사드 래퍼 | 재노출 |

`add_web_pages_json_to_chroma` 실호출 4건:

| 호출부 | 소속 함수 | 분류 |
|---|---|---|
| **`agent/web_search.py:1057`** | **`web_search_agent`(@181)** indent=24 (`_do_index` 클로저) | 🔴 **본선 web 색인** |
| `agent/web_search.py:1377` | `web_search_agent`(@181) indent=12 | `ingest_local_files(...)`에 **kwarg로 전달** |
| `agent/vector_search.py:1062` | `vector_search_agent`(@654) indent=20 | 동일 (kwarg 전달) |
| `tools/local_rag.py:1582` | `ingest_local_files`(@1387) indent=16 | 위 kwarg의 실제 호출 지점 |
| `tools/local_rag.py:1652` | `add_local_findings_to_chroma`(@1605) | 파사드 경유(`:1632`) |

## 1-3. 실행 경로 사슬 (본선)

```
web_search_agent  (agent/web_search.py:181)          ← graph.py:101 노드 등록
  └ :1057 add_web_pages_json_to_chroma(json_file=filtered_json, …)
      └ ingest_vector.py:1471 web_page_json_to_documents(json_file)
          └ ingest_docs.py:611 web_results_to_documents(resources)
              ├ 분기 2  :382-400  ← bs4 사본 ①  (raw_content 있을 때)
              ├ 분기 3  :403-459  ← PDF 파서
              ├ 분기 4-1 :468     → ingest._load_html_as_text(url)
              │                      └ ingest.py:677 ← bs4 사본 ②
              └ 분기 4-2 :485     → ingest_docs._load_html_as_text(raw_html, url)  (사본 ③ = _clean_text)
```

동일 사슬이 `vector_search_agent`(graph.py:100)에서도 **local 경로로** 재현되나,
local 항목은 `file://` → **분기 1**로 빠져 bs4를 타지 않는다(`ingest_docs.py:364-379`).

## 1-4. 🔴 `seed_web_namespace` 경로 — 도달 불가 2중

`web_results_to_documents`를 직접 부르는 유일한 비-probe 경로(`:1845`)다. 두 지점에서 끊긴다.

**끊김 ① — `SEED_URLS`가 존재하지 않는다**

```
agent/supervisor.py:234   seed_urls = _get_seed_urls(state)
agent/supervisor.py:235   if not seed_urls: return          ← 여기서 반환
```

| 확인 | 결과 |
|---|---|
| `core/config.py` `SEED_URLS` 선언 | **0건** (`command grep -rn "SEED_URLS" --include="*.py" .` → supervisor 자기 참조 3행 + search.py 주석 1행뿐) |
| `.env` · `.env.openai` · `.env.vertex` · `topics/experiential-marketing-media.env` | **0건 전부** |
| ⇒ `_get_seed_urls`(@188) 반환값 | `CFG.SEED_URLS` 부재 + `os.getenv("SEED_URLS","")` 빈값 → **항상 `[]`** |

**끊김 ② — 호출 시그니처가 맞지 않는다**

| | 실물 |
|---|---|
| 호출 (`supervisor.py:239`) | `_seed_web_ns(seed_urls, ns_web, persist_directory=persist_dir, topic_slug=topic_slug)` |
| 정의 (`ingest_vector.py:1789`) | `def seed_web_namespace(urls=None, *, webjson_path=None, namespace=None, collection_name=None, persist_directory=None, clear=False, embedding=None)` |
| 위치 인자 | 호출 **2개** vs 정의 **1개**(`*` 뒤는 keyword-only) |
| `topic_slug` | 정의에 **없는 키워드** |

바인딩 확정: `supervisor.py:41` `from tools.web_rag.ingest import seed_web_namespace`
→ `ingest.py:702-715`가 `.ingest_vector`에서 가져온다. `ingest.py`는 `.search`를 **import하지 않는다**
(`command grep -n "from .search" tools/web_rag/ingest.py` → 0건).
⇒ `search.py:202`의 동명 `seed_web_namespace(urls, namespace) -> int`(2위치인자)는 **이 경로가 아니다.**

`supervisor.py:243`의 `except Exception`이 이 호출을 감싼다 → 실패해도
`logger.warning("… seeding skipped/failed: %s")` 한 줄만 남는다.

> ⚠️ **끊김 ①이 먼저 걸리므로 ②는 현재 발현되지 않는다.** `SEED_URLS`를 넣으면 그때 ②가 드러난다.
> **판정하지 않는다** — 위 4개 사실만 기재.

## 1-5. 어느 분기가 실제로 돌았는가 — 색인 실물 역산

`content_type`은 분기마다 고정값이 박힌다. R4 §2-a의 web 416청크 분포와 대조:

| content_type | 청크 | 그 값을 넣는 분기 |
|---|---|---|
| `text/html` | **398** | 분기 2(`:398`) **또는** 분기 4(`:490`) — 둘 다 `"text/html"` |
| `application/pdf` | 14 | 분기 3(`:424`) |
| `text/plain` | 4 | 분기 0(`:301`) · 분기 1(`:369`, 확장자 추정) · 분기 5(`:498`) 중 하나 |

> ⇒ **398청크(95.7%)가 bs4 사본 ① 또는 ②를 통과했다.** 둘은 **문자 단위로 동일한 로직**이므로
> (제거태그 3종 · `get_text(separator="\n")` · 정규식 2줄), 어느 쪽이든 **bs4 경로는 살아 있다.**
>
> ⚠️ **①과 ②를 색인 메타만으로는 가를 수 없다.** 두 분기가 같은 `content_type`을 쓴다.
> R5 §4-2의 방증(색인 118 source의 `research/resources_*.json` 내 `raw_content` = 0자 전건)은
> **분기 4 우세**를 시사하나, 색인에 실제로 투입된 파일이 그 파일들이었는지가 미확인이다
> (R5 §6 #8 — 색인 생성 시점 미확정). **여기서는 판정하지 않는다.**

## 1-6. 생사 표 (요청 형식)

| 사본 | 위치 | 파일 | 로드 | **실행** | 근거 |
|---|---|---|---|---|---|
| 분배기 `web_results_to_documents` | `ingest_docs.py:260` | O | O | **O** | 본선 사슬 1-3. 색인 416청크 전량이 이 함수를 통과 |
| **bs4 사본 ①** | `ingest_docs.py:386` | O | O | **O 또는 사문(양자택일 미확정)** | ①②를 색인 메타로 못 가름 (1-5) |
| **bs4 사본 ②** | `ingest.py:677` | O | O | **O 또는 사문(양자택일 미확정)** | 동일 |
| — 둘의 합 | — | — | — | **O 확정** | `text/html` 398청크는 반드시 ① 또는 ②를 통과 |
| 사본 ③ `_clean_text` | `ingest_docs.py:146` | O | O | **미확인** | 분기 4-2는 분기 4-1 실패 시에만. 실패 로그 미조사 |
| `seed_web_namespace` 경로 | `ingest_vector.py:1845` | O | O | **X (도달 불가 2중)** | 1-4 |
| `search.py:202` 동명 함수 | `tools/web_rag/search.py:202` | O | — | **X (호출부 0건)** | `command grep` 전량 → 정의·주석·`__all__`뿐 |

> **A 수리 규모에 대응하는 숫자**: 고쳐야 할 bs4 지점은 **최대 2곳**(`ingest_docs.py:386` · `ingest.py:677`).
> 둘 중 하나만 고치면 나머지 분기로 들어온 페이지는 안 걸린다.
> 사본 ③(`:146`)은 태그를 아예 안 지우므로 **크롬 제거 훅을 넣을 자리가 아니다**(입력에 태그가 남아 있다).
> **어느 쪽을 고칠지·둘 다 고칠지는 판정하지 않는다.**

---

# 2. published_date 획득 가능성 (C 게이트)

## 2-1. 현행 코드에 날짜 추출이 존재하는가 — 전무

`command grep -rniE "og:|article:published|published_date|datePublished|soup\.find|find_all" --include="*.py" .`

| 결과 | |
|---|---|
| 전 레포 히트 | **4행 — 전부 무관**(`edit_log`·`backend_agg_log`·`output_log` 변수명이 `og:`/`_log` 패턴에 우연 매치) |
| 실제 메타태그 접근 | **0건** |
| `soup.find` / `find_all` | **0건** — bs4를 쓰면서 셀렉터를 한 번도 안 쓴다 |

**검색 API 경유 대안도 없다**

| 경로 | 실측 |
|---|---|
| `_promote_item_metadata`(`ingest_docs.py:236-257`) | 승격 키 **3개뿐** — `backend` · `chunk_domain` · `alt_urls`. 날짜 없음 |
| `tools/web_rag/search.py` 결과 dict 생성부(`:626` `:710` `:784` `:819` `:888` `:930`) | 키 = `title`/`url`/`source`/`content`. **날짜 키 0건** |
| `search.py`의 `date` 문자열 | 5행 — 전부 `datetime` import·`NAVER_DIRECT_SORT=date`(정렬 파라미터)·`round_id` 타임스탬프. **결과 필드 아님** |

## 2-2. `soup` 객체 수명 구간 — 덤프

**사본 ① `ingest_docs.py:382-400`**
```python
382	            if raw_content:
383	                try:
384	                    from bs4 import BeautifulSoup
385	                    soup = BeautifulSoup(raw_content, "lxml")     ← DOM 생성. <head> 살아 있음
386	                    for tag in soup(["script", "style", "noscript"]):
387	                        tag.decompose()
388	                    text = soup.get_text(separator="\n")          ← 여기서 평문 확정
389	                    text = _re.sub(r"[ \t]+", " ", text)
390	                    text = _re.sub(r"\n{3,}", "\n\n", text).strip()   ← 이후 soup 참조 0
391	                except Exception:
392	                    text = _re.sub(r"<[^>]+>", " ", raw_content)      ← 폴백엔 DOM 자체가 없음
396	                    docs.append(Document(
397	                        page_content=text,
398	                        metadata={"source": url, "title": …, "content_type": "text/html",
399	                                  **_promote_item_metadata(item)},   ← 메타 조립 지점
```
→ **DOM 존재 구간 = `:385` ~ `:390` (6행).** 메타 조립 지점(`:396-399`)이 **같은 함수 안**에 있다.

**사본 ② `ingest.py:667-687`**
```python
669	        from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
675	            soup = BeautifulSoup(html, "lxml")                    ← DOM 생성
677	        for tag in soup(["script", "style", "noscript"]):
678	            tag.decompose()
679	        text = soup.get_text(separator="\n")
680	        text = _re.sub(r"[ \t]+", " ", text)
681	        text = _re.sub(r"\n{3,}", "\n\n", text)
682	        return text.strip()                                       ← str 하나만 반환하고 종료
```
→ **DOM 존재 구간 = `:675` ~ `:682` (8행).** 메타 조립 지점은 **다른 파일·다른 함수**(`ingest_docs.py:488-491`)다.

## 2-3. 답 — **조건부 접근 가능.** 조건이 두 분기에서 다르다

| | 사본 ① (`ingest_docs.py:386`) | 사본 ② (`ingest.py:677`) |
|---|---|---|
| `<head>` 메타에 **접근** 가능한가 | ✅ `:385`~`:390` 구간에서 `soup`가 살아 있다 | ✅ `:675`~`:682` 구간 |
| 접근 시점이 `get_text()` **이전**인가 | ✅ `:385`에서 이미 파싱 완료. `get_text()`는 `:388` | ✅ `:675` 생성, `get_text()`는 `:679` |
| **반출 경로**가 있는가 | ✅ 같은 함수 `:398` 메타 dict에 키 추가로 나갈 수 있다 | 🔴 **없다.** 함수 계약이 `(url, timeout) -> str` (`:642`, docstring `:646-650`에 계약 명시) |
| 반출에 필요한 변경 | 메타 dict 1키 추가 | **반환 타입 변경 + 호출부(`ingest_docs.py:468`) 수신 변경** |
| 폴백 경로(`try` 실패 시) | 🔴 **불가** — `:392`는 정규식 태그 제거라 DOM이 없다 | 🔴 불가 — `:685` 동일 |

**하류 적재 가능성 (참고)**

| 확인 | 실측 |
|---|---|
| Chroma 메타에 신규 스칼라 키를 실을 수 있는가 | ✅ 전례 있음 — local ns는 `source_version`을 포함해 **5키**(R4 §2-a), web은 4키 |
| list/dict 값 | 🔴 거부 — `_promote_item_metadata:238` 주석이 명시(`alt_urls`를 comma-join으로 flatten하는 이유) |
| ⇒ `published_date`를 **str**로 넣으면 저장층은 통과 | 코드 근거상 그렇다. **실행 검증 안 함** |

> ⚠️ **미확인**: 118 URL 중 몇 건이 실제로 `<head>`에 날짜 메타(`article:published_time`·`og:` 계열·
> JSON-LD `datePublished`)를 갖고 있는지는 **본문을 받아야 알 수 있다.**
> 이번 정찰은 본문 미독 규율을 지켰으므로 **회수율 0% 실측 없음.**

---

# 3. 🔴 링크로트 실측 (재수집 재현성)

## 3-1. 방법·규율

| 항목 | 값 |
|---|---|
| 대상 | 색인 118 distinct source (= `research/resources_*.json`에 전건 존재, R5 §4-2) |
| 1차 | `requests.head(timeout=15, allow_redirects=True)` · 동시요청 **3** · 요청간 `sleep(0.4)` |
| 2차(양성 대조) | 실패 17건만 `requests.get(stream=True)` → **상태줄 수신 후 즉시 `close()`. 본문 미독·미저장** |
| 헤더 | 일반 브라우저 UA 1개. **인증·API 키 0** |
| 저장물 | 상태코드·리다이렉트 수만 (`linkrot.json` — 스크래치패드, 레포 밖) |

## 3-2. 🔴 HEAD 결과를 그대로 읽으면 틀린다

| HEAD 결과 | 건수 |
|---|---|
| 200 | 101 |
| 404 | **14** |
| SSL 오류 | 3 |

**404 14건이 전부 `brunch.co.kr` 한 호스트다** (`brunch.co.kr` 총 14건 / 404 14건 / 200 0건).
호스트 단위 완전 일치라 메서드 거부를 의심할 근거가 됐고, GET 대조를 실행했다.

| URL | HEAD | GET |
|---|---|---|
| `brunch.co.kr/@mentats1/725` | 404 (redirects=1) | **200 (redirects=4)** |
| `brunch.co.kr/@johnismad/20` | 404 (redirects=1) | **200 (redirects=4)** |
| (대조군) `ko.wikipedia.org/wiki/소리_상표` | 200 | 200 |

→ 실패 17건 **전량**에 GET 재확인:

| 전이 | 건수 |
|---|---|
| HEAD 404 → **GET 200** | **14 (brunch 전건)** |
| HEAD SSLError → GET SSLError | 3 |

> 🔴 **`brunch.co.kr`의 404는 링크로트가 아니라 HEAD 메서드 거부다.**
> 파이프라인 실제 수집은 `ingest_net.fetch_text:151` `sess.get(...)` = **GET**이므로
> 이 14건은 현행 코드 기준으로 살아 있다.
> (CLAUDE.md §9 "도구 출력은 계산 방식을 확인한 뒤 해석한다" 계열 — HEAD는 GET의 대리 지표다.)

## 3-3. 최종 실측표 (GET 기준)

| 분류 | URL | 비율 | 그 URL의 색인 청크 | 청크 비율 |
|---|---|---|---|---|
| **200** | **115** | **97.5%** | **413** | **99.3%** |
| SSL 오류 | 3 | 2.5% | 3 | 0.7% |
| 4xx/5xx (GET 기준) | **0** | 0% | 0 | 0% |
| timeout | **0** | 0% | 0 | 0% |
| **합** | 118 | | 416 | |

리다이렉트 발생 = 79 / 118 (HEAD 기준).

**SSL 실패 3건 전량**

| 청크 | URL |
|---|---|
| 1 | `webzine.seoulmetro.co.kr/newshome/mtnmain.php?aid=2772&mtnkey=articleview` |
| 1 | `shareit.kr/story/470` |
| 1 | `marketcast.co.kr/entry/AI마케팅-시리즈4편-…` |

셋 다 색인 청크 1개씩. 현행 코드에 대응 장치 존재 — `ingest_net.py:140` `SSL_QUARANTINE` 스킵,
`ingest_docs.py:436-448` `_PdfSslError` → `_record_retry_candidate(reason="ssl_error")`.

## 3-4. 이 수치가 말하지 **않는** 것

| # | 미확인 |
|---|---|
| 1 | **200 = 같은 내용**이 아니다. 본문을 안 읽었으므로 내용 동일성은 **전건 미확인** |
| 2 | soft-404(200을 주면서 "삭제됨" 페이지) 판별 안 함 |
| 3 | 동적 렌더링 페이지가 `requests` 단독으로 본문을 주는지 미확인 |
| 4 | 79건의 리다이렉트 종착지가 **원문인지 목록/홈인지** 미확인 |
| 5 | 재수집 시 청크 수·경계가 416과 같아지는지 미확인 (R5 §6 #5 유지) |

---

# 4. `merge_refs` 공유 범위 (D 준비)

## 4-1. 정의 2벌 — 시그니처가 다르다

GUARDRAILS(README-dev §5 포인터)는 `merge_refs()`를 **시그니처 고정 공통 API**로 명시한다. 실물:

| | `utils/rag_utils.py:342` | `utils/refs.py:255` |
|---|---|---|
| 시그니처 | `(existing, new_queries, new_docs, *, preserve_extra, limit_queries, limit_docs, sort_docs_by_score)` | `(existing, new_queries, new_docs)` |
| dedup 키 | `_doc_key_from_any`(`:234`) — `norm_url\|src:…##part` | `_doc_sig`(`:275`) — `canon(src)\|본문앞500자` sha1 |
| 반환 | `Refs` (TypedDict cast) | `dict` |
| **본선 import** | **8곳 전량** | **0곳** |

⇒ 위치 인자 3개는 공통이나 **keyword-only 4개가 한쪽에만 있다.** "시그니처 고정"의 실효 범위는
위치 인자 3개까지다. (R5 §3-1 재확인 — `refs.py` 사본은 사문, R2c의 `_canonicalize_src_for_dedup` 판정과 정합)

## 4-2. 호출부 8곳 — 소속 함수 전량

| # | 호출부 | 소속 최상위 함수 | graph 등록 |
|---|---|---|---|
| 1 | `agent/research_planner.py:363` | `research_planner`(@27-457) | `graph.py:104` |
| 2 | `agent/vector_search.py:1066` | `vector_search_agent`(@654-1568) | `graph.py:100` |
| 3 | `agent/vector_search.py:1216` | 동상 | 〃 |
| 4 | `agent/vector_search.py:1373` | 동상 | 〃 |
| 5 | `agent/vector_search.py:1442` | 동상 | 〃 |
| 6 | `agent/web_search.py:400` | `web_search_agent`(@181-1652) | `graph.py:101` |
| 7 | `agent/web_search.py:1451` | 동상 | 〃 |
| 8 | `agent/web_search.py:1470` | 동상 | 〃 |

> **8곳 전량이 그래프 노드 함수 3개의 몸통 안에 있다.** 모듈 최상위 호출 0건.
> ⇒ 그 노드를 실행하지 않으면 `merge_refs`는 **한 번도 불리지 않는다.**

## 4-3. 🔴 논문 트랙 — 파일 / 로드 / 실행 3분류 (catch CF)

논문 드라이버 = `scripts/§paper-writer-1/measure_paper.py`. import 전량 중 프로젝트 모듈은 3개뿐:

```
:56   from common.academic_domains import ACADEMIC_DOMAINS
:154  from agent.web_search import paper_section_fetch      ← 🔴 merge_refs가 있는 그 모듈
:155  from agent.paper_section_writer import (…)
```

| 축 | 판정 | 근거 |
|---|---|---|
| **파일** | **공유 O** | `agent/web_search.py` 한 파일을 양 트랙이 쓴다 |
| **로드** | **공유 O** | `:154` import 시 모듈 최상위 `web_search.py:21 from utils.rag_utils import merge_refs`가 실행된다. 심볼이 논문 프로세스 메모리에 올라온다 |
| **실행** | **공유 X** | 아래 3근거 |

**실행 X의 근거 3건**

| # | 확인 | 결과 |
|---|---|---|
| 1 | `paper_section_fetch`(`web_search.py:1988-2074`) 본문에서 `merge_refs` / `web_search_agent` / `add_web_pages` / `web_page_json` / `_to_documents` 검색 | **히트 0** |
| 2 | `web_search.py` 최상위 def 29개 전수 스캔 — `merge_refs(` 를 포함한 함수 | **`web_search_agent`(@181-1652) 단 1개** |
| 3 | 논문 드라이버가 `graph.py` / `build_graph` / `graph.invoke`를 import·호출 | **0건** (`command grep -n "build_graph\|graph.invoke\|import graph"` → 0행) |

보강 — `agent/paper_section_writer.py` import 전량 = `langchain_core` · `core.llm` · `prompts` · `utils.citations`.
**`utils.rag_utils` · `merge_refs` 0건.** `scripts/§paper-writer-1/` 전체도 0건.

> ⇒ **R3b가 ingest 축에서 낸 결론(파일 O / 로드 O / 실행 X)이 `merge_refs` 축에서도 같은 모양으로 재현된다.**
> 단 R3b와 근거의 성격이 다르다 — R3b는 `academic-trademark-*` 디렉토리 **부재**라는 물리 증거였고,
> 여기는 **함수 경계 스캔**이다. 물리 증거는 없다. **실행 로그 확인 안 함 — 그만큼 약하다.**

## 4-4. D 대상 지점의 공유 범위 (요약표)

| 지점 | ad/§research-1 | 논문 | 근거 |
|---|---|---|---|
| `utils/rag_utils.py:234` `_doc_key_from_any` | **실행 O** (3노드 경유) | **실행 X** | 4-2 · 4-3 |
| `utils/rag_utils.py:342` `merge_refs` | 실행 O | 실행 X | 〃 |
| `utils/refs.py:255` `merge_refs` | **사문** | 사문 | 4-1 |

---

# 5. 미확인 항목 (판정 보류)

| # | 미확인 | 왜 이번에 못 정했나 |
|---|---|---|
| 1 | bs4 사본 **①과 ② 중 어느 쪽**이 398청크를 만들었는지 | 두 분기가 같은 `content_type`을 쓴다. 색인 메타로 못 가름 (1-5) |
| 2 | 사본 ③(`ingest_docs.py:146`) 실행 여부 | 분기 4-1 실패 시에만 도달. 실패 로그 미조사 |
| 3 | `SEED_URLS` 주입 시 시그니처 오류가 실제로 나는지 | 실행 안 함. 정적 시그니처 대조까지만 (1-4) |
| 4 | 118 URL의 **날짜 메타 실제 보유율** | 본문 미독 규율 준수 → 회수율 실측 없음 (2-3) |
| 5 | GET 200 URL의 **내용 동일성** | 본문 미독 (3-4 #1) |
| 6 | 리다이렉트 79건의 종착지 성격 | 미조사 (3-4 #4) |
| 7 | 논문 트랙 "실행 X"의 **런타임 증거** | 함수 경계 스캔까지만. 실행 로그·트레이스 미확인 (4-3) |
| 8 | `tools/web_rag/search.py:202` 동명 `seed_web_namespace`의 존재 이유 | 호출부 0건인 것만 확인. 이력 미조사 |
| 9 | R5 이월 — 색인 118건 생성 시점 | 이번에도 미해소 |
| 10 | `search.py`가 백엔드 응답의 날짜 필드를 **버리는지 애초에 안 받는지** | 결과 dict 생성부만 확인. 백엔드 원응답 미조사 |

---

# 6. 실행한 명령 (재현용)

```bash
type grep
git log --oneline -3 && git status --short

# §1 호출부 전량 + 소속 함수 역방향 확정
command grep -rn "web_results_to_documents"      --include="*.py" .
command grep -rn "web_page_json_to_documents("   --include="*.py" .
command grep -rn "add_web_pages_json_to_chroma"  --include="*.py" .
command grep -rn "_load_html_as_text"            --include="*.py" .
command grep -rn "seed_web_namespace"            --include="*.py" .
command grep -n  "from .search" tools/web_rag/ingest.py        # → 0건 (바인딩 확정)
command grep -rn "SEED_URLS" --include="*.py" .
command grep -n  "SEED_URLS" .env .env.openai .env.vertex topics/experiential-marketing-media.env
../.venv_vertex/bin/python -c "…최상위 def 역방향 스캔 + indent 출력…"

# §2 날짜 추출 부재 확인
command grep -rniE "og:|article:published|published_date|datePublished|soup\.find|find_all" --include="*.py" .
command grep -n "\"published\|'published\|date" tools/web_rag/search.py

# §3 링크로트 (네트워크. API 키 0)
#   1차 HEAD 118건 (workers=3, sleep 0.4)
#   2차 실패 17건만 GET(stream=True) → 상태줄 수신 후 즉시 close. 본문 미독·미저장
../.venv_vertex/bin/python <scratchpad>/linkrot.py

# §4 merge_refs 공유범위
command grep -rn "merge_refs" --include="*.py" .
command grep -n "^from \|^import " "scripts/§paper-writer-1/measure_paper.py"
command grep -n "^from \|^import " agent/paper_section_writer.py
command grep -rn "merge_refs\|rag_utils" agent/paper_section_writer.py "scripts/§paper-writer-1/"
command grep -n "build_graph\|graph.invoke\|import graph" "scripts/§paper-writer-1/measure_paper.py"
../.venv_vertex/bin/python -c "…web_search.py 최상위 def 29개 전수 + merge_refs 포함 여부…"
```

**부작용** — 코드 수정 0 · 커밋 0 · 유료 API 0 · API 키 0 · `PersistentClient` 미호출 ·
Chroma 쓰기 0 · 프로젝트 모듈 import 0(표준 라이브러리 + `requests`만).
네트워크는 §3 한정, **GET 본문을 읽지도 저장하지도 않았다**(`stream=True` 후 즉시 `close()`).
파일 생성 = 이 문서 1건 + 스크래치패드 3건(레포 밖).
