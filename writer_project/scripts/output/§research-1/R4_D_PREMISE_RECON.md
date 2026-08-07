# R4 — 후보 D 전제 실측 정찰 (§research-1 선분 3 · 정찰 1)

> 2026-08-08 · 읽기 전용 · 비용 $0 · 코드 수정 0 · 커밋 0
> 방법: `sqlite3 -readonly` 만 (STANDARDS §3.2). `chromadb.PersistentClient` 미사용 (catch AG).
> **판정 없음.** 표와 실측치만. 미확인은 미확인으로 표기.

---

## 0. 대상·환경

| 항목 | 값 |
|---|---|
| sqlite3 | 3.51.0 (macOS 동봉) |
| web DB | `data/chroma_store/experiential-marketing-media-web/chroma.sqlite3` |
| local DB | `data/chroma_store/experiential-marketing-media-local/chroma.sqlite3` |
| grep | 셸 함수(ugrep 심) 확인 — `type grep` 실행. 아래 코드 검색은 전부 `command grep` (catch CG) |

---

## 1. 세는 방식 먼저 — 중복 계상 함정 2개 대조

절차 규율 §3 요구사항. **조인 전에 원시 총계를 확정**하고, 조인 결과가 그것과 일치함을 확인했다.

| 확인 | 명령 | web | local |
|---|---|---|---|
| 원시 총계 | `SELECT COUNT(*) FROM embeddings` | **416** | **302** |
| collections 행 | `SELECT ... FROM collections` | 1 | 1 |
| segments 행 | `SELECT ... FROM segments` | **2** (VECTOR + METADATA) | **2** |
| segment별 embeddings | `GROUP BY segment_id` | METADATA 1개만 416 · VECTOR 0 | METADATA 1개만 302 · VECTOR 0 |
| metadata 원시 행 | `COUNT(*) FROM embedding_metadata` | **1,664** | **1,510** |
| metadata distinct id | `COUNT(DISTINCT id)` | **416** | **302** |
| 키 개수 | — | 4 | 5 |
| 검산 | 키수 × 청크수 | 4 × 416 = 1,664 ✅ | 5 × 302 = 1,510 ✅ |

**함정 2개 실측 결과**
- **segment 2행 함정 — 발생하지 않음.** `segments`는 컬렉션당 2행(VECTOR/METADATA)이지만
  `embeddings.segment_id`는 **METADATA segment 하나만** 가리킨다. HNSW 벡터는 sqlite 밖(`*.bin`)에 있다.
  → `embeddings` 직접 카운트가 청크 수와 1:1. 중복 없음.
- **키당 1행 함정 — 발생함, 필터로 해소.** `embedding_metadata`는 (id, key) 복합 PK라
  청크 1개가 4~5행을 차지한다. 아래 모든 집계는 **`WHERE key='source'`로 청크당 1행을 강제**했고,
  그 합이 원시 총계(416 / 302)와 일치함을 매 쿼리에서 재검산했다.

**전 키 결손 0** — `title`·`source`·`content_type`·`chroma:document` 모두 distinct_id = 416(web) / 302(local).
즉 `source`가 없는 청크는 0건.

---

## 2-a. 출처 URL이 어느 필드에 있는가 — 키 전량 덤프

### web (`-web`, 416청크)

| key | 행수 | distinct id | 내용 |
|---|---|---|---|
| `source` | 416 | 416 | **출처 URL. 프래그먼트 없음** (`#` 포함 0건 / 416) |
| `title` | 416 | 416 | 페이지 제목 |
| `content_type` | 416 | 416 | `text/html` 398 · `application/pdf` 14 · `text/plain` 4 |
| `chroma:document` | 416 | 416 | 청크 본문 (Chroma 내부 예약 키) |

`source` 표본:
```
https://airweb.co.kr/logo_portfolio/265
https://sentv.co.kr/article/view/sentv202208230074
https://dbpia.co.kr/journal/articleDetail?nodeId=NODE07541504
```

### local (`-local`, 302청크)

| key | 행수 | distinct id | 내용 |
|---|---|---|---|
| `source` | 302 | 302 | **file:// URL + 프래그먼트.** `#` 포함 **302 / 302 (전건)** |
| `source_version` | 302 | 302 | mtime 계열 정수 11종 (파일 수와 일치) |
| `title` | 302 | 302 | |
| `content_type` | 302 | 302 | `text/plain` 229 · pptx 46 · docx 20 · xlsx 7 |
| `chroma:document` | 302 | 302 | |

`source` 실물 (꼬리):
```
…/week12_brakus_brand_experience_lecture_note.docx#part=chunk&chunk=8
…/…ms.xlsx#part=브랜드경험%20척도&index=1&chunk=4
```

> 🔴 **web과 local의 `source` 입도가 다르다.**
> web = **문서 단위**(한 URL을 여러 청크가 공유). local = **청크 단위**(`#part=…&chunk=N`이 붙어 청크마다 유일).
> → local에서 문서 단위 집계를 하려면 `#` 앞을 잘라야 한다. 아래 2-b/2-c의 local 수치는 전부 절단 후 값(`base`)이다.

---

## 2-b. URL별 청크 수 분포 — 상위 20

### web (distinct source = **118**, 청크 416, 검산 합 = 416 ✅)

| n | source |
|---|---|
| 14 | `https://illustkorea.or.kr/data/file/IL_PDS/2038850820_vS5loxHE_8205f2c6….pdf` |
| 11 | `https://syncly.kr/blog` |
| 11 | `https://atlassian.com/ko/work-management/project-management/brand-launch` |
| 10 | `https://ranktracker.com/ko/blog/tips-for-lifestyle-brands-to-make-the-most-of-visual-social-media` |
| 10 | `https://icat.kr/blog/how-to-win-instagram-ads-2025-12` |
| 10 | `https://dbpia.co.kr/journal/articleDetail?nodeId=NODE07541504` |
| 9 | `https://prime-career.com/article/9195` |
| 8 | `https://sweetspot.co.kr/contents_blog?bmode=view&idx=163874780` |
| 8 | `https://ko.wikipedia.org/wiki/소리_상표` (percent-encoded) |
| 7 | `https://jaenung.net/tree/1529` |
| 7 | `https://jaenung.net/tree/14441` |
| 7 | `https://icoda.io/ko/ai/ai-influencer-marketing-tools` |
| 7 | `https://icat.kr/blog/9-tips-insta-ads-success-2025-2025-12` |
| 7 | `https://alien711.tistory.com/entry/2025-content-marketing-trends-strategy` |
| 7 | `https://916er.com/백화점팝업-언더웨어-브…` |
| 6 | `https://mk.co.kr/news/business/10016038` |
| 6 | `https://ko.creativosonline.org/오디오-브랜딩:-강력한…` |
| 6 | `https://etoday.co.kr/news/view/2064552` |
| 6 | `https://adall.kr/blog/d5636031-30e6-4422-819b-ec7a18ac81c5` |
| 6 | `https://adall.kr/blog/4071c87b-5a8b-4a12-8bd8-7201eb0db3f2` |

평균 = 416 / 118 = **3.53 청크/URL**. 최대 14.

### local (프래그먼트 절단 후 distinct base = **11**, 청크 302, 검산 합 = 302 ✅)

파일 수가 11건뿐이라 **전수**를 싣는다.

| n | base (꼬리) |
|---|---|
| 197 | `…세네요용1.md` |
| 32 | `…어-골자.md` |
| 15 | `…초안/week2_experience_economy.pptx` |
| 15 | `…의초안.pptx` |
| 14 | `…초안/week3_schmitt_sem_lecture.pptx` |
| 12 | `…내용/week3_schmitt_sem_lecture_note.docx` |
| 8 | `…추/week12_brakus_brand_experience_lecture_note.docx` |
| 4 | `…추/brand_experience_scale_survey_items.xlsx` |
| 3 | `…설계표.xlsx` |
| 1 | `…내용/sem_expros_grid.pptx` |
| 1 | `…초안/wundt_curve_slide.pptx` |

평균 = 302 / 11 = **27.5 청크/파일**. 최대 197.

---

## 2-c. 청크 1개 URL vs 2개 이상 URL

### web — 히스토그램 전량

| 청크수 | 그런 source 건수 | 청크 소계 |
|---|---|---|
| 1 | **20** | 20 |
| 2 | 30 | 60 |
| 3 | 25 | 75 |
| 4 | 17 | 68 |
| 5 | 6 | 30 |
| 6 | 5 | 30 |
| 7 | 6 | 42 |
| 8 | 2 | 16 |
| 9 | 1 | 9 |
| 10 | 3 | 30 |
| 11 | 2 | 22 |
| 14 | 1 | 14 |
| **합** | **118** | **416** ✅ |

- 청크 **1개**인 URL = **20건 / 118 (16.9%)** → 청크 20건 (전체의 4.8%)
- 청크 **2개 이상**인 URL = **98건 / 118 (83.1%)** → 청크 396건 (전체의 95.2%)

### local (base 기준)

| 청크수 | base 건수 |
|---|---|
| 1 | **2** |
| 3 | 1 |
| 4 | 1 |
| 8 | 1 |
| 12 | 1 |
| 14 | 1 |
| 15 | 2 |
| 32 | 1 |
| 197 | 1 |
| **합** | **11** (청크 302 ✅) |

- 1개 = 2건 / 11 · 2개 이상 = 9건 / 11

> ⚠️ **local의 `source` 원본(절단 전) 기준으로는 distinct = 302 = 청크수**, 즉 "1 source = 1 청크"가 302건 전건이다.
> 절단 여부에 따라 수치가 302건 ↔ 2건으로 뒤집힌다. 어느 쪽을 쓰는지 명시 없이 인용하면 안 되는 지점.

---

## 2-d. 청크 1개 URL들의 `document` 길이 분포

### web — 1청크 source 20건 전량 (전수, `head` 없음)

| doclen | source |
|---|---|
| 2324 | `https://aimkt.biz/casestudy` |
| 2184 | `https://airweb.co.kr/logo_portfolio/353` |
| 2174 | `https://sweetspot.co.kr/content?bmode=view&idx=163874780&q=…` |
| 2154 | `https://brunch.co.kr/@swesone/254` |
| 2097 | `https://airweb.co.kr/logo_portfolio/265` |
| 2011 | `https://airweb.co.kr/logo_portfolio/412` |
| 1943 | `https://airweb.co.kr/logo_portfolio/43` |
| 1800 | `https://brunch.co.kr/@mobiinside/6874` |
| 1737 | `https://publy.co/content/3513` |
| 1317 | `https://accio.com/business/ko/팝업스토어트렌…` |
| 1053 | `https://cnecbiz.com/newsletters` |
| 917 | `https://sharex.fastcampus.co.kr/dgn_online_pxbx` |
| 912 | `https://brandb.net/archive/the-sound-of-leffe-2024-06` |
| 303 | `https://newneek.co/@goldenax/article/39444` |
| 227 | `https://shareit.kr/story/470` |
| 152 | `https://brunch.co.kr/@johnismad/20` |
| 122 | `https://webzine.seoulmetro.co.kr/newshome/mtnmain.php?aid=2772&mtnkey=articleview` |
| 116 | `https://marketcast.co.kr/entry/AI마케팅-시리즈4…` |
| 110 | `https://bizon.kookmin.ac.kr/bizon/society-culture/society/society-culture.do?articleNo=591` |
| 52 | `https://live.lge.co.kr/2407-lg-sound-designer` |

**분해 근거가 되는 상수 (OBSERVED §2-2 실측 재인용, 이번 세션 재측정 아님)**
- `RAG_CHUNK_CHARS` 실효 **2400** · `RAG_CHUNK_OVERLAP` 실효 **200** → 보폭 2200
- ⇒ **원문 2400자 미만이면 분할 없이 1청크**가 산출된다.

**대조**

| 구분 | 청크수 | min | max | avg |
|---|---|---|---|---|
| 1청크 source | 20 | 52 | **2324** | 1,185 |
| 2청크+ source | 396 | 72 | **2400** | 1,876 |

- 1청크 20건의 doclen **최댓값 = 2324 < 2400**. **2400을 넘는 1청크 URL은 0건.**
- 20건 내 분포: ≥1300자 10건 / <1300자 10건.
- 2청크+ 그룹의 max가 정확히 2400에서 멈춘다(= splitter 상한).

**web 전체 청크 길이 버킷**

| 버킷 | 청크수 |
|---|---|
| <500 | 40 |
| 500–999 | 39 |
| 1000–1999 | 69 |
| 2000–2399 | **267** |
| ≥2400 | 1 |

### local (base 기준)

| 구분 | 청크수 | min | max | avg |
|---|---|---|---|---|
| 1청크 base | 2 | 509 | 559 | 534 |
| 2청크+ base | 300 | 60 | 1415 | 248 |

1청크 base 2건: `sem_expros_grid.pptx` (559자) · `wundt_curve_slide.pptx` (509자).

**local 전체 청크 길이 버킷**

| 버킷 | 청크수 | min | max |
|---|---|---|---|
| <100 | 1 | 60 | 60 |
| 100–299 | **238** | 101 | 299 |
| 300–599 | 48 | 300 | 591 |
| 600–1299 | 12 | 633 | 1216 |
| ≥1300 | 3 | 1413 | 1415 |

---

## 3. 추가 실측 — 조각ID(embedding_id) 실물 구조

후보 D의 대상이 조각ID이므로 ID 자체를 덤프했다. **요청 4건 밖의 보충 자료.**

| 확인 | web | local |
|---|---|---|
| `embedding_id` 총수 / distinct | 416 / **416** (전건 유일) | 302 / **302** (전건 유일) |
| 형식 | `<sha1 40자>-<6자리 카운터>` | 동일 |
| distinct **prefix**(앞 40자) | **118** = distinct source 수와 일치 | **302** = 청크수와 일치 |
| prefix 하나에 source가 2개 이상 | **0건** | (prefix가 청크당 유일이므로 해당 없음) |
| 접미 카운터 분포 | 1~14 (source별 청크수만큼 증가) | **`000001` 302건 전건** |

같은 URL 10청크의 실물 (dbpia):
```
6ab86a700428b3091dc84f5a6783fa8fe67f787a-000001
6ab86a700428b3091dc84f5a6783fa8fe67f787a-000002
…
6ab86a700428b3091dc84f5a6783fa8fe67f787a-000010
```

ID 생성부 = `tools/web_rag/utils.py` (seed = 정규화 source [+`source_version`] [+content sha] → sha1 → `-{counter:06d}` → `cap_id`).
`RAG_ID_INCLUDE_MTIME` 기본 True · `RAG_ID_INCLUDE_CONTENT_SHA` 기본 False (둘 다 CFG 미선언 — §5-b 표 참조).

## 3-b. 접힘 여부와 직접 맞닿는 관측 2건

| 관측 | web | local |
|---|---|---|
| 동일 `document` 텍스트가 2건 이상 | 416 청크 중 **distinct 415** → 중복 1쌍 | 302 중 distinct 301 → 중복 1쌍 |
| 그 중복쌍의 source | `https://aimatters.co.kr/ai-campaign-case` 와 `…/ai-campaign-case/page/3` — **서로 다른 URL, 본문 277자 동일** (사이트크롬 푸터. catch CA 계열) | 미조사 |
| 한 source에 title이 2개 이상 | **0건** | 미조사 |

즉 web에서 **본문이 완전히 같아도 URL이 다르면 별개 행으로 남아 있다**(접히지 않았다).
같은 URL 안에서 동일 본문이 중복된 사례는 이번 쿼리 범위에서 **미조사**.

---

## 4. 미확인 항목 (판정 보류)

| # | 미확인 | 왜 이번에 못 정했나 |
|---|---|---|
| 1 | "접힌다"의 **정의** — 색인 시 dedup / 검색 시 URL 대표 1건 반환 / writer 단계 병합 중 무엇을 가리키는지 | 후보 D 원문을 이 세션에서 읽지 않았다. 색인 실물만 봤다 |
| 2 | **retrieve 반환 단계**에서 같은 URL 청크가 합쳐지는지 | 검색 경로 실행이 필요(읽기 전용 범위 밖). 색인층은 안 합친다는 것만 관측됨 |
| 3 | web 1청크 20건이 "원문이 짧아서"인지 **수집 단계에서 잘려서**인지 | 원문 길이 원자료가 없다. 색인에 남은 doclen만 있고 전부 2400 미만이라 splitter 기준과는 모순 없음 |
| 4 | local `source` 프래그먼트를 **누가 붙이는지** (local_rag 청킹부 추정) | 코드 미확인 |
| 5 | 같은 URL 내부의 동일 본문 중복 | 미조사 |

---

# 5. OBSERVED 대장 정합 (읽기 전용 · 판정 금지 · 편집 없음)

## 5-a. `_cfg_str` 정의 위치 — `utils.py:121`의 정체

**결론 표기: OBSERVED §2-1의 "파서 4종" 분류 자체가 실물과 안 맞는다. 5번째가 아니라 25번째 계열이다.**

`command grep -rn "def _cfg_str\|def _cfg_int\|def _cfg_bool\|def _cfg_float" --include="*.py" .` → **정의부 60행 / 25개 파일.**
`_cfg_*`를 **import로 가져다 쓰는 곳은 전 레포에서 2곳뿐**(`ingest_vector.py:50`이 `ingest_config`에서, `scripts/§research-1/run_r3a_straight.py:377`이 `utils.refs`에서). 나머지는 전부 **파일마다 자기 사본을 재정의**한다.

### `tools/web_rag/utils.py:121~` 실물

```python
# ─────────────────────────────────────────────────────────────
# CFG helper shims (define only if missing to avoid redeclare)
# ─────────────────────────────────────────────────────────────
if "_cfg_str" not in globals():          # ← :121
    def _cfg_str(key: str, default: str = "") -> str:   # ← :122
        try:
            v = getattr(CFG, key)
            return (str(v).strip() if v is not None else default)
        except Exception:
            return default
```

| 항목 | 실측 |
|---|---|
| `:121` = **조건부 가드**(`if "_cfg_str" not in globals():`), `:122` = `def` | off-by-one 주의 |
| 동작 | `getattr(CFG, key)` — **CFG 전용. `os.environ` 폴백 없음** |
| CFG 출처 | `utils.py:45` `from core.config import CFG` (`ingest_config`에서 재수입한 것이 아님) |
| 같은 파일 내 `_cfg_bool` | **`:742`에 무조건 정의** (가드 없음, 시그니처도 `*, default` 키워드 전용) — 같은 파일 안에서 `_cfg_str/int/float`(가드 있음)과 규약이 다르다 |
| OBSERVED §2-1 파서 #2(`ingest_config._cfg_*`)와의 관계 | **본문 로직 동일**(CFG-only). 그러나 **import 관계 없음 — 독립 사본**이다 |

### OBSERVED §2-1 4분류 vs 실물

| OBSERVED 기술 | 실측 |
|---|---|
| #1 `core/config._env_*` — os.environ 직독 | 유효 (별개 계열) |
| #2 `tools/web_rag/ingest_config._cfg_*` | `ingest_config.py:36/44/52`에 실재. **`ingest_vector.py`가 유일하게 import해 쓰는 사본** |
| #3 `tools/local_rag._cfg_*` — CFG→env 폴백 | `local_rag.py:165/177/191/205`에 실재 (함수 내부 중첩 정의) |
| #4 `agent/vector_search.py:191` — 자체 집합 | `:191` = `_cfg_bool`. 같은 파일 `:166/:177/:184`에 str/int/float도 있음 |
| — | **미등재 사본 21개 파일** — `tools/web_rag/utils.py`, `tools/metrics.py`, `report_builder.py`, `rag_expression.py`, `core/paths.py`, `core/state_io.py`, `core/topic.py`, `core/routers.py`, `utils/text_utils.py`, `utils/outline.py`, `utils/refs.py`, `utils/forced_queries.py`, `agent/research_planner.py`, `agent/research_synthesizer.py`, `agent/supervisor.py`, `agent/section_writer.py`, `agent/web_search.py`, `agent/chapter_writer.py`, `agent/export/planner.py`, `scripts/§research-1/run_r3a_straight.py` 등 |

> ⚠️ `core/state_io.py`·`utils/refs.py`의 `_cfg_*`는 시그니처가 `(name, env, default)` **3인자**다.
> 이름은 같지만 규약이 다르다 — CLAUDE.md §9 "동명 심볼" 계열. **어느 사본인지 확정 없이 인용 불가.**

## 5-b. OBSERVED §3 열린항목 #3 — 지시받은 명령 실행

```
command grep -n "_cfg_int\|_cfg_str" tools/web_rag/ingest_vector.py   →  20행
command grep -nE "_cfg_int|_cfg_str" tools/web_rag/ingest_vector.py   →  20행  (형식 대조 일치)
grep(심)  동일 명령                                                    →  20행  (이 파일은 tracked, 심/실물 차이 없음)
```

`_cfg_bool`까지 포함한 **호출부 25행 / distinct 키 24개.** (`_cfg_int` 15키 · `_cfg_bool` 8키 · `_cfg_str` 1키)
사용 사본 = `ingest_config` (`ingest_vector.py:50`에서 import) = **CFG 전용, env 폴백 없음.**

### CFG 선언 여부 × `.env` 기재 여부 (24키 전수 + `CHROMA_DIR`)

확인 명령: `command grep -c "\b<KEY>\b" core/config.py` / `command grep -n "^[[:space:]]*<KEY>=" .env`

**A. CFG 선언 있음 (= `.env` 유효) — 8키**

| 키 | 호출부 | 코드 기본값 |
|---|---|---|
| `RAG_CHUNK_CHARS` | `:414` | 2400 |
| `CLEAR_CHROMA_ON_START` | `:752` | False |
| `RAG_MIN_DOC_CHARS` | `:879` | 200 |
| `RAG_MIN_DOC_TOKENS` | `:880` | 30 |
| `PPTX_MIN_MERGED_CHARS` | `:1115` | 160 |
| `MIN_CHUNK_CHARS` | `:1132` | 120 |
| `MIN_CHUNK_PPTX` | `:1137`, `:1159` | 40 |
| `MIN_CHUNK_PDF` | `:1140`, `:1160` | 80 |

**B. 🔴 CFG 미선언 + `.env`에 값이 적혀 있음 (= 값이 읽히지 않음) — 13키**

| 키 | `.env` | 코드 기본값(실효) | 호출부 | OBSERVED §1 등재 |
|---|---|---|---|---|
| `INDEX_TIMEOUT_SEC` | `:121` `=300` | **60** | `:1283` | ✗ 신규 |
| `ALLOW_GLOBAL_CLEAR` | `:120` `=0` | False | `:674` | ✅ 등재 |
| `CLEAR_GUARD_DISABLE` | `:130` `=0` | False | `:333` | ✅ 등재 |
| `CLEAR_ON_FIRST_VECTOR` | `:131` `=0` | False | `:753` | ✅ 등재 |
| `MAX_CHUNKS_PER_DOC` | `:134` `=15` | **0**(비활성) | `:1170` | ✅ 등재 |
| `RAG_CHUNK_OVERLAP` | `:135` `=150` | **200** | `:415` | ✅ 등재 |
| `RAG_ID_INCLUDE_MTIME` | `:159` `=1` | True | `:863`,`:999`,`:1268` | ✗ 신규 |
| `RAG_DELETE_OLD_ON_VERSION_MISMATCH` | `:160` `=1` | True | `:1076` | ✗ 신규 |
| `CHROMA_MAX_BATCH` | `:162` `=64` | **16** | `:1235` | ✗ 신규 |
| `ENABLE_XLSX_META_SUMMARY` | `:165` `=1` | True | `:979` | ✗ 신규 |
| `XLSX_SCAN_MAX_ROWS` | `:166` `=200` | 200 (우연 일치) | `:980` | ✗ 신규 |
| `XLSX_SCAN_MAX_COLS` | `:167` `=20` | 20 (우연 일치) | `:981` | ✗ 신규 |
| `XLSX_META_MAX_DOCS` | `:168` `=5` | 5 (우연 일치) | `:982` | ✗ 신규 |

**C. CFG 미선언 + `.env`에도 없음 (코드 기본값만) — 3키**
`CHROMA_MAX_ID_CHARS`(128, `:1226`) · `RAG_ID_INCLUDE_CONTENT_SHA`(False, `:1269`) · `CHROMA_QUARANTINE_DIR`(`""`, `:1285`)

### `CHROMA_DIR` — 프롬프트가 예시로 든 키

| 확인 | 결과 |
|---|---|
| `core/config.py` 선언 | **0건** (미선언) |
| `.env` | `:125` `CHROMA_DIR=data/chroma_store` |
| `_cfg_str`로 읽는 곳 | **`ingest_vector.py`가 아니라 `tools/web_rag/utils.py:1734`** — `_cfg_str("CHROMA_DIR", default="")` |
| 그 `_cfg_str` = | 위 5-a의 `utils.py:122` 사본 (CFG 전용) → **CFG 필드 없음 ⇒ 항상 `""` 반환** |
| 다른 소비처 | `tools/local_rag.py:1558` `getattr(CFG, "CHROMA_DIR", "")` (동일 결과) · **`core/topic.py:142` `os.environ["CHROMA_DIR"] = chroma_dir`** (런타임 주입, 5-c와 연결) |

**수치 요약: `ingest_vector.py`의 24키 중 CFG 미선언 = 16키. 그중 `.env`에 값이 적혀 무효화되는 것 = 13키.**
OBSERVED §1이 확정 등재한 6건 중 이 파일에서 여전히 미선언인 것은 5건 → **신규 8건**(위 표 "✗ 신규").
OBSERVED §3 #3의 "키 17개" 추정치는 **실측 24개**(`_cfg_int`만 세면 15개)와 다르다.

## 5-c. `MIRROR_STATE_TO_ENV` 실효값 (STANDARDS §4.1 보호 5키)

| 층 | 확인 명령 | 결과 |
|---|---|---|
| `.env` | `command grep -n MIRROR_STATE_TO_ENV .env` | **0건 (부재)** |
| `.env.vertex` / `.env.openai` / `.env.anthropic` | 동일 | **0건** |
| `env_raw.txt` | 동일 | **0건** |
| `topics/*.env` | `command grep -rn … topics/` | **0건** |
| 심 grep 대조 | `grep -rn … --include=".env*" .` | 0건 (catch CG 재현 — `.env`는 심에서 안 보임. `command grep`으로도 0건이므로 **실제 부재 확정**) |
| CFG 선언 | `core/config.py:378` `MIRROR_STATE_TO_ENV: bool` | 있음 |
| 파서 | `core/config.py:634` `_env_flag("MIRROR_STATE_TO_ENV", True)` | 파서 #1(env 직독), **기본 True** |
| 보호키 등록 | `core/config.py:666` | 등록됨 (STANDARDS §4.1과 일치) |

**런타임 실측** (`../.venv_vertex/bin/python -c "import core.config as c; print(repr(c.CFG.MIRROR_STATE_TO_ENV))"`)

| 실행 | `os.environ` | `CFG` |
|---|---|---|
| TOPIC_SLUG 미지정 | `None` | **`True`** |
| `TOPIC_SLUG=experiential-marketing-media` | `None` | **`True`** |

⇒ **미러링은 켜져 있다** (설정 부재 → 기본 True). 소비처 = `core/topic.py:140` `if _cfg_bool("MIRROR_STATE_TO_ENV", True):` → `:142` `os.environ["CHROMA_DIR"] = chroma_dir`.
명시적으로 끄는 코드는 측정 드라이버 2곳뿐: `scripts/measure_phase3_patch_d88a8b9.py:134` (`="0"`) · `scripts/_step3_dry_run_rag_update.py:47`(보호키 명단).

> ⚠️ **부수 실측 — catch AB 재현.** 위 첫 실행에서 `TOPIC_SLUG` 없이 돌리자
> `[Config] 토픽 프리셋 로드: topics/academic-trademark-similarity-consumer.env` 가 떴다.
> CLAUDE.md §1의 "미지정 시 논문 프리셋 로드" 기술이 **현재도 유효함**을 확인.
> 또한 두 실행 모두 provider overlay = **`.env.openai`** 였다(`.env`의 `LLM_PROVIDER` 기본값 기준).

## 5-d. §3-5 "닫힘" 표기 vs §3 표에 #5 잔존

| 확인 | 실측 |
|---|---|
| §5 마지막 행 | `:114` `| 2026-07-31 | … §3-5 닫힘 | 2465193b |` |
| §3 표 현재 #5 | `:79` `| 5 | MIRROR_STATE_TO_ENV 상태 미확인 | … |` — **잔존** |
| 커밋 `2465193b` 실제 diff | 구 **#5** = "`scripts/output/*` gitignore 미적용" **삭제** + 구 **#6**(`MIRROR_STATE_TO_ENV`)을 **#5로 번호 이동** |

⇒ **불일치의 정체 = 번호 재사용.** "닫힘"이 가리킨 §3-5와 지금 표에 있는 §3-5는 **다른 항목**이다.
내용상 모순은 없고, **표기가 오독을 유발하는 상태**다. (판정·수정은 하지 않음.)

### 부수 불일치 2건

| # | 불일치 | 실측 |
|---|---|---|
| 1 | 헤더 `> 최종 갱신 2026-07-30` | OBSERVED.md 최종 커밋 = `bb20cd38` **2026-07-31** (`docs(observed): §4 백틱 오류 수정 + §5 fc7a2a12 누락 행 보충`) |
| 2 | §4 자체검증 규칙 `grep -c '^\|.*PENDING' OBSERVED.md` → **1** 이라고 명시 | 실행 결과 **0**. §5 최종 행의 `PENDING`이 `2465193b`로 채워졌고 새 `PENDING` 행이 없어서. 규칙 문구가 "항상 1"을 요구하는 형태 |

---

## 6. 실행한 명령 (재현용)

```bash
# 색인 (읽기 전용)
sqlite3 -readonly data/chroma_store/experiential-marketing-media-web/chroma.sqlite3 \
  "SELECT COUNT(*) FROM embeddings;"
sqlite3 -readonly <DB> "SELECT key, COUNT(*), COUNT(DISTINCT id) FROM embedding_metadata GROUP BY key;"
sqlite3 -readonly <DB> "SELECT COUNT(*) n, string_value FROM embedding_metadata WHERE key='source' GROUP BY string_value ORDER BY n DESC;"
# local 은 프래그먼트 절단 필수
#   CASE WHEN instr(string_value,'#')>0 THEN substr(string_value,1,instr(string_value,'#')-1) ELSE string_value END

# 설정층 (grep 심 회피)
type grep
command grep -n "_cfg_int\|_cfg_str" tools/web_rag/ingest_vector.py
command grep -rn "MIRROR_STATE_TO_ENV" --include="*.py" .
TOPIC_SLUG=experiential-marketing-media ../.venv_vertex/bin/python -c \
  "import core.config as c; print(repr(c.CFG.MIRROR_STATE_TO_ENV))"
```

**부작용 0** — 쓰기 명령 없음, `PersistentClient` 미호출, API 호출 0, 파일 수정은 이 문서 생성뿐.
