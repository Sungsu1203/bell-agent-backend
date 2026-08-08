# R5 — 수집→청킹→색인 사슬 정찰 (§research-1 선분 3 · 정찰 2)

> 2026-08-08 · 읽기 전용 · 비용 $0 · 코드 수정 0 · 커밋 0 · 유료 API 0
> 방법: 파일 실물 덤프 + `sqlite3 -readonly` (STANDARDS §3.2). `chromadb.PersistentClient` 미사용 (catch AG).
> 코드 검색은 전부 `command grep` (catch CG). `type grep` → 셸 함수(ugrep 심) 확인.
> **판정 없음.** 표와 실측치만. 미확인은 미확인으로 표기.

---

## 0. 대상·환경

| 항목 | 값 |
|---|---|
| 사슬 파일 | `tools/web_rag/ingest.py`(네트워크/HTML) · `ingest_docs.py`(파싱) · `ingest_vector.py`(청킹/색인) · `utils.py`(경로/ID/저장) |
| `ingest_vector.py` 총행 | 1,897 |
| web DB | `data/chroma_store/experiential-marketing-media-web/chroma.sqlite3` (416청크 / 118 source) |
| 원자료 후보 | `research/resources_*.json` 72파일 · `resources/experiential-marketing-media/web_*.json` 76파일 |
| grep | 셸 심 확인 후 전량 `command grep` |

---

## 1. 기존 앵커 5건 — 실물 확인

### 1-1. 결과 요약표

| 앵커(기존 기술) | 실물 | 판정 |
|---|---|---|
| `:1644-1647` `FILTER_BAD_DOMAINS` 2차 필터 | 실재. **단 `retrieve()` 내부**(정의 `:1534`) | ✅ 행 일치. **소속 함수가 기존 기술에 없다** |
| `:408` `split_documents` | `def split_documents(` 가 정확히 `:408` | ✅ 일치 |
| `:1090` `documents_to_chroma` 유일 내부 호출부 | `split_documents` 호출 = 전 레포 **1곳**(`:1090`) | ✅ 일치·전수 확인 |
| `:778`·`:1445`·`:1505` `chunk_size=None 전달부` | 셋 다 **함수 시그니처의 기본값 선언**이다. 전달(pass-through)은 `:1090`·`:1474`·`:1523` | ⚠️ **행은 맞고 성격 기술이 어긋난다** |
| `utils.py:1734` `CHROMA_DIR` 소비처 | `_resolve_persist_dir()` 내부 2순위 분기 `_cfg_str("CHROMA_DIR", default="")` | ✅ 일치 |

> ⚠️ off-by-one은 없었다. 어긋난 것은 **행번호가 아니라 성격 기술 2건**이다(아래 1-2·1-4).

### 1-2. `:1644-1647` — 소속 함수가 `retrieve()`다

앵커 라인을 감싸는 최상위 `def`를 역방향으로 확인한 결과:

| 행 | 소속 최상위 def | 내용 |
|---|---|---|
| `:899` | **`documents_to_chroma` (`@775`)** | `# 1.6) bad_domains 필터 (인덱싱 단계에서 무관 도메인 차단)` |
| `:1604` | **`retrieve` (`@1534`)** | 같은 env 읽기 |
| `:1644` | **`retrieve`** | fast 경로 청크별 스킵 |
| `:1702` | **`retrieve`** | 폴백 경로 청크별 스킵 (동일 로직 2벌) |

즉 `FILTER_BAD_DOMAINS` 소비처는 **총 3벌 + web_search 1벌 = 4벌**이다.

```
tools/web_rag/ingest_vector.py:899   ← 색인 단계 (문서 단위 리스트 컴프리헨션)
tools/web_rag/ingest_vector.py:1645  ← 검색 단계 fast
tools/web_rag/ingest_vector.py:1702  ← 검색 단계 폴백
agent/web_search.py:629              ← 수집 단계
```

`GUARDRAILS`의 "2차 필터"라는 표현은 이 다층 구조와 **모순되지 않는다**(1차 = `:899` 색인, 2차 = retrieve).
다만 앵커만 보고 "색인부"로 읽으면 틀린다.

**`:899` 실물 (색인 단계 1차)**
```python
897	    pre_docs_count2 = len(pre_docs)  # (옵션) 로그용
898	    # 1.6) bad_domains 필터 (인덱싱 단계에서 무관 도메인 차단)
899	    _bad_domains_str = (os.environ.get("FILTER_BAD_DOMAINS", "") or "").strip()
900	    _bad_domains = [bd.strip() for bd in _bad_domains_str.split(",") if bd.strip()]
901	    if _bad_domains:
902	        _before = len(pre_docs)
903	        pre_docs = [ d for d in pre_docs if not any(bd in <source|url>.lower() for bd in _bad_domains) ]
```

> ⚠️ **파서 #1 계열(`os.environ` 직독)이다.** `_cfg_*`가 아니라 `os.environ.get`을 쓴다.
> `core/config.py:409`에 `FILTER_BAD_DOMAINS: str` 선언이 **있고** `:648`이 `_env_str(..., "")`로 채우지만,
> 소비처 4곳은 CFG를 안 보고 env를 직접 읽는다. (실효값 `''` — GUARDRAILS 기술과 일치, 재측정 아님)

### 1-3. `:408` `split_documents` — 전문 (11행)

```python
408	def split_documents(
409	    documents: List[Document],
410	    *,
411	    chunk_size: Optional[int] = None,
412	    chunk_overlap: Optional[int] = None,
413	) -> List[Document]:
414	    cs = (_cfg_int("RAG_CHUNK_CHARS", 2400) if chunk_size is None else int(chunk_size))
415	    ov = (_cfg_int("RAG_CHUNK_OVERLAP", 200) if chunk_overlap is None else int(chunk_overlap))
416	    cs = max(300, min(cs, 6000))
417	    ov = max(0, min(ov, int(cs * 0.5)))
418	    splitter = RecursiveCharacterTextSplitter(chunk_size=cs, chunk_overlap=ov)
419	    return splitter.split_documents(documents)
```

- 클램프 존재: `cs ∈ [300, 6000]`, `ov ≤ cs/2`.
- **텍스트 내용 기반 필터·제거 로직 0건.** 순수 길이 분할이다.
- 청크 메타데이터는 `RecursiveCharacterTextSplitter`가 상위 Document의 metadata를 **그대로 복제**한다
  (→ 같은 URL의 N청크가 동일 `source`를 갖는 R4 §2-b 관측과 정합).

### 1-4. `chunk_size` 4지점 — 전수

`command grep -n "chunk_size" tools/web_rag/ingest_vector.py` → 9행 전량:

| 행 | 성격 |
|---|---|
| `:411` | `split_documents` 시그니처 기본값 |
| `:414` | 기본값 해소 (`None` → `_cfg_int("RAG_CHUNK_CHARS", 2400)`) |
| `:418` | splitter 생성자 인자 |
| `:778` | `documents_to_chroma` **시그니처 기본값** |
| `:1090` | → `split_documents(...)` **전달** |
| `:1304` | 로그 문자열(무관) |
| `:1445` | `add_web_pages_json_to_chroma` **시그니처 기본값** |
| `:1474` | → `documents_to_chroma(...)` **전달** |
| `:1505` | `add_documents_to_chroma` **시그니처 기본값** |
| `:1523` | → `documents_to_chroma(...)` **전달** |

**전 레포 전수 확인** — `command grep -rn "chunk_size\|chunk_overlap" --include="*.py" .`
→ `tools/web_rag/ingest_vector.py` **외 0건**. `tests/`도 0건.

> ⇒ `chunk_size`/`chunk_overlap`에 `None` 아닌 값을 넣는 호출부가 **레포 전체에 존재하지 않는다.**
> 벡터층 청킹은 항상 `RAG_CHUNK_CHARS`(실효 2400) · `RAG_CHUNK_OVERLAP`(실효 200)로 결정된다.
> (실효값 출처 = R4 §5-b — 둘 다 CFG 미선언이라 `.env:135` `=150`은 읽히지 않고 코드 기본 200이 산다.)

### 1-5. `utils.py:1734` — `_resolve_persist_dir` 2순위

```python
1726	    # 1) 명시 persist_directory
1727	    if persist_directory is not None: ...
1733	    # 2) CFG.CHROMA_DIR
1734	    chroma_dir = (_cfg_str("CHROMA_DIR", default="") or "").strip()
1735	    if chroma_dir: ...
1741	    # 3) 기본 경로
1742	    out = (DATA_DIR / "chroma_store" / ns)
```

catch CE 기술과 일치(2순위 사문 → 3순위가 실효). **재측정 아님, 재확인만.**

---

## 2. 🔴 여섯 번째 앵커 — 파서 (HTML→텍스트 전환 지점)

### 2-1. 정의부

| 함수 | 위치 |
|---|---|
| `web_results_to_documents(results)` | **`tools/web_rag/ingest_docs.py:260`** |
| `web_page_json_to_documents(json_file)` | **`tools/web_rag/ingest_docs.py:506`** |
| (재노출) | `ingest.py:695` `from .ingest_docs import ...` · `__init__.py:67/71` 파사드 |

`web_page_json_to_documents`는 **로딩·정렬·cap만** 하고 `:611`에서 `web_results_to_documents(resources)`를 부른다.
→ **파싱 실체는 `web_results_to_documents` 하나다.**

### 2-2. `web_results_to_documents` 분기 5개 (`:291`~`:499`)

| # | 조건 | HTML→텍스트 처리 | 행 |
|---|---|---|---|
| 0 | URL 없음 | 없음 (`item.content` 그대로) | `:297-303` |
| 1 | `scheme == "file"` | 없음 (`item.content` 그대로) | `:364-379` |
| **2** | **`raw_content` 존재** | **bs4 인라인 파싱** | **`:382-400`** |
| 3 | PDF 스멜 | `_pdf_bytes_to_text` (PyPDF2→pdfminer) | `:403-459` |
| **4** | 그 외 | **`ingest._load_html_as_text(url)` → 네트워크 fetch + bs4** | **`:461-492`** |
| 5 | 최종 폴백 | 없음 (`item.content` 그대로) | `:494-499` |

분기 2·4 앞에 `_is_noise_url()` 조기 드랍(`:333`)이 있으나, 실물은 **kpanet.or.kr 2조건 전용**이다
(`ingest.py:416-429`). 크롬과 무관.

### 2-3. 🔴 분기 2 — 인라인 파서 전문

```python
381	            # 2) raw_content 우선 (보통 HTML)
382	            if raw_content:
383	                try:
384	                    from bs4 import BeautifulSoup
385	                    soup = BeautifulSoup(raw_content, "lxml")
386	                    for tag in soup(["script", "style", "noscript"]):
387	                        tag.decompose()
388	                    text = soup.get_text(separator="\n")
389	                    text = _re.sub(r"[ \t]+", " ", text)
390	                    text = _re.sub(r"\n{3,}", "\n\n", text).strip()
391	                except Exception:
392	                    text = _re.sub(r"<[^>]+>", " ", raw_content)
393	                    text = _re.sub(r"\s{2,}", " ", text).strip()
394	
395	                if text:
396	                    docs.append(Document(
397	                        page_content=text,
398	                        metadata={"source": url, "title": ..., "content_type": "text/html", ...},
399	                    ))
400	                    continue
```

### 2-4. 🔴 분기 4 — `ingest._load_html_as_text` 전문 (`ingest.py:642-687`)

```python
667	    # 2) HTML → 텍스트 추출 (기존 정제 로직 유지)
668	    try:
669	        from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
674	            soup = BeautifulSoup(html, "lxml")
677	        for tag in soup(["script", "style", "noscript"]):
678	            tag.decompose()
679	        text = soup.get_text(separator="\n")
680	        text = _re.sub(r"[ \t]+", " ", text)
681	        text = _re.sub(r"\n{3,}", "\n\n", text)
682	        return text.strip()
683	
684	    except Exception:
685	        text = _re.sub(r"<[^>]+>", " ", html or "")
```

**두 파서는 동일 로직의 독립 사본이다** (분기 2 = 문자열 인자 / 분기 4 = URL 인자 + 네트워크).

### 2-5. 라이브러리·추출 모드 실측

| 항목 | 실측 |
|---|---|
| 사용 라이브러리 | **bs4 + lxml 파서만** |
| trafilatura / readability / html2text / newspaper | **전 레포 0건** (`command grep -rn "trafilatura\|readability\|html2text" --include="*.py" .`) |
| 추출 모드 | **본문 추출(boilerplate removal) 모드 아님.** `soup.get_text()` = **문서 전체 텍스트 노드 수집** |
| 제거 대상 태그 | `script` · `style` · `noscript` **3종뿐** |
| `nav` `header` `footer` `aside` `form` `menu` 제거 | **0건** (양쪽 파서 모두) |
| CSS/XPath 셀렉터·본문 컨테이너 지정 | **0건** |
| 후처리 | 공백·개행 압축 정규식 2줄뿐 (`[ \t]+`→` `, `\n{3,}`→`\n\n`) |

`ingest_docs.py:146`에도 동명 `_load_html_as_text(html, url)`가 있으나 본문은 `_clean_text(html)` **1줄**이고
(`utils.py:1434` = NFKC 정규화 + 개행 압축, **태그 제거조차 안 한다**), 분기 4의 4-2 폴백에서만 쓰인다.
독스트링이 *"필요시 BeautifulSoup 기반 정제 로직을 단계적으로 이관한다"*로 **미이관 상태를 명시**한다.

### 2-6. 크롬이 살아남는지 — 사슬 전 구간 필터 목록

수집된 HTML이 청크가 되기까지 통과하는 **모든** 필터를 순서대로 나열하면:

| 순서 | 위치 | 단위 | 기준 | 크롬 제거 가능? |
|---|---|---|---|---|
| 1 | `ingest_docs.py:386` / `ingest.py:677` | 태그 | `script`/`style`/`noscript` | ✖ nav·푸터는 대상 아님 |
| 2 | `ingest_docs.py:333` `_is_noise_url` | URL | kpanet 2조건 | ✖ |
| 3 | `ingest_docs.py:338` `_seen_urls` | 문서 | 정규화 URL 중복 | ✖ |
| 4 | `ingest_vector.py:888` `RAG_MIN_DOC_CHARS` | **문서** | 200자 미만 드랍 | ✖ 크롬은 본문과 **같은 문서 안**에 있다 |
| 5 | `ingest_vector.py:891` `RAG_MIN_DOC_TOKENS` | **문서** | 30토큰 미만 드랍 | ✖ 동일 |
| 6 | `ingest_vector.py:899` `FILTER_BAD_DOMAINS` | 문서 | 도메인 문자열 | ✖ (실효 `''`로 무작동이기도 함) |
| 7 | `ingest_vector.py:408` `split_documents` | — | 순수 길이 분할 | ✖ 필터 아님 |
| 8 | `ingest_vector.py:1115` `_merge_short_chunks` | 청크 | **PPTX 한정** 병합 | ✖ web 무관 |
| 9 | `ingest_vector.py:1132·1137·1140` `MIN_CHUNK_*` | 청크 | 길이 하한(120/40/80) | ✖ 하한이지 내용 판정 아님 |

> **문서 단위 필터(4·5·6)와 청크 단위 필터(8·9) 사이에 "문서 내부 구간을 잘라내는" 층이 없다.**
> 크롬은 문서 안 · 청크 안에 섞여 있으므로 어느 쪽에도 걸리지 않는다.
> → 실측상 **HTML→텍스트 전환 시점(순서 1)이 크롬이 텍스트로 확정되는 유일한 지점**이다.
> 그 뒤 사슬 전체에 태그 정보는 **남아 있지 않다**(`get_text()` 이후 평문).

### 2-7. 파서 단계 지표 — 크롬 관련 부수 관측

R4 §3-b가 관측한 web 중복쌍(`aimatters.co.kr/ai-campaign-case` vs `.../page/3`, 본문 277자 동일)은
2-6 표의 어느 필터로도 안 걸린다: 문서 단위 URL이 다르고(3·6 통과), 277자 > 200자(4 통과),
청크 길이 하한도 통과(9). **관측과 코드가 정합한다.**

---

## 3. `"source"` 키 사용처 (D 잔여)

`command grep -rn '"source"' --include="*.py" .` → **132행**(tests·scripts·probe 제외 기준).
그중 **dedup·grouping·merge 키로 쓰는 자리**만 추린 전수:

| # | 위치 | 용도 | 키 구성 | web 문서 단위로 접히나 |
|---|---|---|---|---|
| 1 | `utils/rag_utils.py:342` `merge_refs` → `:234` `_doc_key_from_any` | refs 병합 dedup | `norm_url` + `\|src:` + `##part\|page\|fragment` | ⚠️ **아래 3-1** |
| 2 | `utils/refs.py:255` `merge_refs` → `:275` `_doc_sig` | refs 병합 dedup | `canon(src)` + `\|` + **본문 앞 500자** sha1 | ✖ 본문이 다르면 별개 |
| 3 | `core/routers.py:77` `_merge_docs_unique` | refs/references 합치기 | `id` → `source` → `url` → `title` **첫 비어있지 않은 값** | 🔴 **접힌다** |
| 4 | `agent/vector_search.py:314` `_dedupe_docs` | 검색 결과 dedup | `(norm_url, title.lower())` | 🔴 **접힌다** |
| 5 | `tools/web_rag/utils.py:1245` `_dedupe_keep_order_dicts` | 검색 **결과 dict** dedup | `_normalize_url(url\|source)` | 🔴 접힌다 (단 **색인 전 수집물**이 대상) |
| 6 | `tools/web_rag/ingest_vector.py:1020` | 저장버전 조회 | `{"source": {"$in": urls}}` | — (조회) |
| 7 | `tools/web_rag/ingest_vector.py:1083` | 버전 불일치 시 삭제 | `{"source": {"$eq": s}}` | 🔴 **문서 단위 일괄 삭제** |
| 8 | `tools/threshold_sweep.py:460` | 평가 goldset 그룹핑 | `normalize_source(...)` | (평가 도구, 본선 아님) |

### 3-1. #1이 실질 경로다 — 호출부 전수

`merge_refs` 호출부 8곳 전량이 **`utils.rag_utils`** 쪽을 import한다:

```
agent/research_planner.py:17,363     from utils.rag_utils import merge_refs
agent/vector_search.py:19  → :1066, :1216, :1373, :1442
agent/web_search.py:21     → :400, :1451, :1470
```

`utils/refs.py:255`의 `merge_refs`를 import하는 본선 코드는 **0건**이다(#2는 사문).
⇒ **R2c §3의 "`_canonicalize_src_for_dedup`은 사문" 기술과 정합.** 그 함수는 `refs.py` 내부
(`:209`·`:235`·`:279`·`:619`)에서만 호출되고, 그중 `:279`가 사문 `merge_refs`다.
`:209`·`:235`·`:619`의 소비 여부는 **이번 정찰 범위 밖 — 미확인.**

**`_doc_key_from_any` 전문 요지 (`rag_utils.py:234-273`)**
```python
url_raw = meta.get("url") or meta.get("source")
src_raw = meta.get("source")
part    = meta.get("part") or meta.get("page") or meta.get("fragment")
base    = f"{norm_url}|src:{src_key}" if src_key else norm_url
return f"{base}##{part_key}" if part_key else base
```

| 계열 | `part`/`page`/`fragment` 메타 | 키 결과 |
|---|---|---|
| **web 청크** | R4 §2-a 실측 — web 메타 키는 `source`·`title`·`content_type`·`chroma:document` **4종뿐**. `part`/`page`/`fragment` **부재** | `norm_url\|src:...` → 🔴 **같은 URL의 N청크가 1건으로 접힌다** |
| **local 청크** | `source` 자체에 `#part=…&chunk=N`이 박혀 있다(302/302 전건) | `src_key`가 청크마다 달라 접히지 않는다 |

> ⇒ **D의 전제 "같은 URL이면 1건으로 접힘"은 색인층이 아니라 `merge_refs` 층에서 성립한다.**
> R4가 "저장층 접힘 없음"을 확정했고, 이번 정찰이 **접히는 층의 실물 위치**를 찾았다.
> 대상은 `utils/rag_utils.py:234` `_doc_key_from_any` — `part` 메타가 없는 web 계열 전량.
> **판정은 하지 않는다.** 아래 미확인 참조.

### 3-2. #3·#4·#7 보충

- **#3 `core/routers.py:88-90`** — `str(x.get("id") or x.get("source") or ...)`.
  `id` 키가 있으면 그것이 우선이나, **web Document 메타에 `id` 키는 없다**(R4 §2-a 4종).
  → `source`로 떨어져 접힌다.
- **#4 `agent/vector_search.py:314-325`** — `(normalized_url, title.lower())`.
  R4 §3-b 실측 *"한 source에 title이 2개 이상 = 0건"* ⇒ **URL만으로 접히는 것과 동치**.
- **#7 `ingest_vector.py:1083`** — `source_version` 불일치 시 `where={"source": {"$eq": s}}` 일괄 delete.
  web은 `source_version` 키가 **없으므로**(R4 §2-a: web 4키 / local 5키) 이 경로는 web에서 미발동으로 보인다.
  **실행 확인 안 함 — 미확인.**

---

## 4. 재색인 비용 실측 입력

### 4-1. `-web` 재구축 경로 — 진입점 3개

| 진입점 | 입력 | 위치 |
|---|---|---|
| `add_web_pages_json_to_chroma(json_file)` | **web.json 1개 파일 경로** | `ingest_vector.py:1442` |
| `add_documents_to_chroma(documents)` | 이미 만들어진 Document 리스트 | `:1502` (별칭) |
| `documents_to_chroma(documents)` | 동일 | `:775` |

`add_web_pages_json_to_chroma`의 흐름 (`:1454-1494`):
```
seen-hash 게이트 (load_seen_source_hashes / compute_incoming_hashes)
  → 변경분 0이면 즉시 return (0,0)
  → web_page_json_to_documents(json_file)     ← §2 파서 진입
  → documents_to_chroma(...)
  → added>0 이면 save_seen_source_hashes
```
`clear_vector_store()`(`:654`)는 `delete_seen_source_hashes`를 **먼저 호출**하므로(`:666`),
ns를 지우면 seen-hash 게이트도 함께 풀린다.

### 4-2. 🔴 원자료는 남아 있으나 **본문이 없다**

| 자산 | 파일 수 | distinct URL | 색인 118 source와 교집합 |
|---|---|---|---|
| `research/resources_*.json` | 72 | **184** | **118 / 118 (전건)** |
| `resources/experiential-marketing-media/web_*.json` | 76 | 17 | **0** |

→ **URL 목록은 100% 보존돼 있다.** 그러나 본문은 아니다:

| 지표 | 값 |
|---|---|
| 색인 118 source의 `chroma:document` 총 글자수 | **766,607자** |
| 같은 118 source의 `research/resources_*.json` 내 `raw_content` 총 글자수 | **0자** (전건 부재) |
| 같은 118 source의 `content` 길이 | **37 ~ 215자** (검색 스니펫) |
| `raw_content ≥ 색인글자수의 80%` 인 source | **0 / 118** |

상위 5건 대조:

| 색인 글자수 | 청크수 | `raw_content` | `content` | source |
|---|---|---|---|---|
| 22,777 | 11 | 0 | 116 | `atlassian.com/ko/work-management/.../brand-launch` |
| 22,696 | 11 | 0 | 37 | `syncly.kr/blog` |
| 21,459 | 10 | 0 | 121 | `dbpia.co.kr/journal/articleDetail?nodeId=NODE07541504` |
| 20,981 | 10 | 0 | 81 | `icat.kr/blog/how-to-win-instagram-ads-2025-12` |
| 20,722 | 14 | 0 | 134 | `illustkorea.or.kr/data/file/IL_PDS/2038850820_...pdf` |

> ⇒ 이 118건은 §2 표의 **분기 4**(네트워크 fetch)로 색인됐다. 분기 2(`raw_content`)였다면
> json에 원문이 남아 있어야 한다. `raw_content`가 있는 76개 `web_*.json`(최대 217,749자)은
> **다른 17개 URL**이고 색인과 교집합 0이다.

**⇒ `-web` 재색인은 "기존 원자료 재사용"이 아니라 "URL 재사용 + HTML 재수집"이다.**

### 4-3. 재수집의 성격 — 유료인가

| 단계 | 실측 |
|---|---|
| 검색 API(Tavily/Naver/vertex) | **불필요.** URL 118건이 이미 파일에 있다 |
| HTML fetch | `ingest_net.fetch_text`(`:129`) = `requests.Session().get()`. **API 키 사용 0건** (`command grep -c "API_KEY\|api_key" tools/web_rag/ingest_net.py` → 0) |
| 임베딩 | 유료. 아래 4-5 |

> ⚠️ **재현성은 보장되지 않는다.** 링크 로트·동적 렌더링·차단 페이지(`_is_block_page`)로
> 재수집 결과가 2026-08-01 시점과 다를 수 있다. **정량 미확인.**

### 4-4. 배치 구조 실측 — `CHROMA_MAX_BATCH=16`은 바인딩하지 않는다

`documents_to_chroma:1235-1256`의 배치 규칙:
```python
1235	MAX_BATCH = _cfg_int("CHROMA_MAX_BATCH", 16)   # CFG 미선언 → .env:162 `=64` 무효, 실효 16
1236	MAX_TEXT_SUM = 18000                            # 🔴 하드코딩. env 없음
1245	if batch_docs and (len(batch_docs) >= MAX_BATCH or text_sum + l > MAX_TEXT_SUM):
```

실제 416청크 길이(sqlite 반환 순서)로 이 알고리즘을 그대로 돌린 결과:

| 항목 | 값 |
|---|---|
| 총 청크 | 416 · 총 글자 766,607 · 평균 **1,842자** |
| **배치 수** | **46** |
| 배치 크기 분포 | 2×1, 7×3, 8×15, 9×12, 10×8, 11×2, 12×4, 15×1 |
| `MAX_BATCH=16`에 정확히 걸린 배치 | **0 / 46** |
| `CHROMA_MAX_BATCH`를 64로 올렸을 때 | **배치 46 — 변화 없음** |

> 🔴 **바인딩 제약은 `CHROMA_MAX_BATCH`가 아니라 하드코딩 `MAX_TEXT_SUM = 18000`이다.**
> 평균 1,842자 × 16 = 29,472자 > 18,000이므로 크기 상한에 닿기 전에 글자 상한이 먼저 끊는다.
> ⇒ **`.env`나 CFG로 배치 수를 바꿀 수 없다.**
> ⚠️ 이 시뮬레이션은 sqlite 행 순서 = 색인 삽입 순서라는 **가정 위에 있다. 미검증.**
> 순서가 다르면 배치 경계가 달라진다(총 배치 수는 ±수 건 수준으로 예상되나 미확인).

### 4-5. `INDEX_TIMEOUT_SEC=60` — 중단 임계가 아니다

`_batched_add`(`:618-652`) 전문 확인 결과:

```python
646	    elapsed = time.time() - t0
647	    if elapsed > max_seconds:
648	        logger.warning("[INDEX][WARN] batched_add took %.2fs (> %ss) for %d docs", ...)
652	    return len(docs)
```

| 경로 | `INDEX_TIMEOUT_SEC` 역할 |
|---|---|
| 정상 배치 경로 (`:1292-1299`) | **사후 경고 로그만.** 중단·재시도 없음 |
| 단건 폴백 경로 (`:1310-1315`) | **누적 시간 상한으로 실제 중단**(`break`) |

> ⇒ 정상 경로에서 60초는 **소요 추정의 근거가 아니다.** 배치 1건당 60초를 넘으면 경고만 찍힌다.
> 총 소요 = 46회 임베딩 왕복 + Chroma upsert. **실측 없음 — 시간 추정치는 내지 않는다.**

### 4-6. 임베딩 비용 입력 (계산은 하지 않음)

| 층 | 값 |
|---|---|
| L1 `.env:2` | `LLM_PROVIDER=openai` |
| L1 `.env:151` | `RAG_EMBEDDING_MODEL=text-multilingual-embedding-002` |
| **L2 `.env.openai:35`** (override=True) | **`RAG_EMBEDDING_MODEL=text-embedding-3-large`** ← 승자 |
| L3 `topics/experiential-marketing-media.env` | 미기재 (GUARDRAILS 지침대로 L3에 안 씀) |
| 재임베딩 대상 | **766,607자 / 416청크 / 46 API 왕복** |
| 문자→토큰 환산 | **미측정.** 한국어 비중이 높아 환산비 미확정 |

⚠️ provider를 vertex로 고정하면 `.env.vertex:33`이 `text-multilingual-embedding-002`(768d)로 바뀐다.
**차원이 다르므로 기존 ns에 섞어 쓸 수 없다** — 인계 메모 §3-b의 "provider 고정" 조건과 같은 이야기다.

---

## 5. 프롬프트 §0 질문에 대응하는 실측 (판정 아님)

> "크롬 제거를 넣을 자리는 파서인가 청킹인가 색인인가."

각 층에서 **무엇이 가능한지**만 표로 적는다. 선택은 하지 않는다.

| 층 | 그 시점에 존재하는 정보 | 크롬 식별 가능성 |
|---|---|---|
| **파서** `ingest_docs.py:386` / `ingest.py:677` | **HTML DOM 전체** (`soup` 객체). 태그·클래스·id·구조 | 태그 기반 제거가 **여기서만 가능** |
| 파서 직후 | 평문 문자열 | 태그 정보 소실. 패턴 매칭만 가능 |
| 문서 필터 `ingest_vector.py:888-913` | 문서 단위 평문 + 메타 4키 | 문서 통째 드랍만 가능. **부분 제거 수단 없음** |
| **청킹** `:408` | 평문 | 순수 길이 분할. 필터 훅 자체가 없다 |
| 청크 필터 `:1132-1160` | 청크 평문 + 메타 | 길이 하한만. 술어 추가는 가능하나 태그 정보 없음 |
| **색인** `:1272-1299` | ID·배치 | 내용 판정 없음 |

부수 관측 — **B(플레이스홀더 `🟨`)의 후보 자리는 A와 다르다.**
`🟨`는 local(pptx) 계열이고 local은 파서 분기 1(`file://`, `item.content` 직통)로 들어와
**bs4를 아예 안 탄다.** 인계 메모 §1의 *"A의 제거 자리에 술어 1개 추가로 끝날 때만"* 조건이
성립하려면 그 자리가 **파서가 아니라 청크 필터층**이어야 한다. **미확인 — 설계 단계 입력.**

---

## 6. 미확인 항목 (판정 보류)

| # | 미확인 | 왜 이번에 못 정했나 |
|---|---|---|
| 1 | `_doc_key_from_any` 접힘이 **실제 파이프라인 출력에 나타나는지** | 실행이 필요(읽기 전용 범위 밖). 코드 구조만 확인 |
| 2 | `refs.py:209`·`:235`·`:619`의 `_canonicalize_src_for_dedup` 소비 경로 | 이번 범위 밖. `:279`(merge_refs)가 사문인 것만 확정 |
| 3 | `ingest_vector.py:1083` 문서단위 delete가 web에서 발동하는지 | `source_version` 부재로 미발동 **추정**. 실행 확인 안 함 |
| 4 | 4-4 배치 시뮬레이션의 **순서 가정** | sqlite 행 순서 = 삽입 순서라는 가정. 미검증 |
| 5 | 재수집 시 118 URL 중 몇 건이 살아 있는지 | 네트워크 요청이 필요 — 읽기 전용 범위 밖 |
| 6 | 766,607자의 **토큰 환산** | 토크나이저 실행 안 함 |
| 7 | 재색인 **소요 시간** | 실측 없음. `INDEX_TIMEOUT_SEC`은 근거가 못 된다(4-5) |
| 8 | 색인 118건이 언제 만들어졌는지 | `chroma.sqlite3` mtime = 2026-08-06 21:04이나 이는 이후 probe 접근 흔적일 수 있다. **미확정** |
| 9 | `resources/…/web_*.json`의 17 URL이 어느 경로 산출물인지 | 색인과 교집합 0인 것만 확인 |
| 10 | `published_date`(후보 C)를 파서에서 얻을 수 있는지 | 인계 메모 §1이 부속 질문으로 남긴 항목. **이번 지시에 없어 조사 안 함** |

---

## 7. 실행한 명령 (재현용)

```bash
type grep                                     # 셸 심 확인 (catch CG)

# 앵커 실물 — 구간 통째 덤프 (Read 도구, ±30행)
#   ingest_vector.py 1614-1677 / 378-439 / 1058-1121 / 748-809 / 1415-1539 / 618-677 / 866-935 / 1216-1320
#   utils.py 1694-1765 / ingest_docs.py 126-205, 255-434, 434-613 / ingest.py 640-729

# 앵커 소속 함수 역추적 (들여쓰기 아닌 최상위 def 기준)
../.venv_vertex/bin/python -c "…최상위 def 스캔…"

# 전수 확인
command grep -rn "split_documents" --include="*.py" .
command grep -rn "chunk_size\|chunk_overlap" --include="*.py" .
command grep -rn "_bad_domains\|FILTER_BAD_DOMAINS" --include="*.py" .
command grep -rn "BeautifulSoup\|bs4\|trafilatura\|readability\|html2text" --include="*.py" .
command grep -rn '"source"' --include="*.py" .
command grep -rn "merge_refs\|_canonicalize_src_for_dedup" --include="*.py" .

# 색인 (읽기 전용, PersistentClient 미사용)
sqlite3 -readonly data/chroma_store/experiential-marketing-media-web/chroma.sqlite3 \
  "SELECT DISTINCT string_value FROM embedding_metadata WHERE key='source';"
sqlite3 -readonly <DB> "SELECT s.string_value, COUNT(*), SUM(LENGTH(d.string_value))
  FROM embedding_metadata s JOIN embedding_metadata d ON s.id=d.id AND d.key='chroma:document'
  WHERE s.key='source' GROUP BY s.string_value;"
sqlite3 -readonly <DB> "SELECT LENGTH(string_value) FROM embedding_metadata WHERE key='chroma:document';"

# 원자료 대조 (json 표준 라이브러리만, 프로젝트 모듈 import 0)
../.venv_vertex/bin/python -c "…research/resources_*.json vs 색인 source 교집합…"
../.venv_vertex/bin/python -c "…_yield_batches 알고리즘 재현…"

# 설정층
command grep -n "RAG_EMBEDDING_MODEL\|LLM_PROVIDER" .env .env.openai .env.vertex topics/experiential-marketing-media.env
```

**부작용 0** — 쓰기 명령 없음, `PersistentClient` 미호출, 네트워크 요청 0, 유료 API 0,
프로젝트 모듈 import 0(표준 라이브러리 `json`/`glob`만), 파일 수정은 이 문서 생성 + 스크래치패드 3파일뿐.
