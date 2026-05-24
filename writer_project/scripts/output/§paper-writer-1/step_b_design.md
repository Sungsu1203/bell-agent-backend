# §paper-writer-1 Step B design (design only, 2026-05-24)

## entry context

- 직전 HEAD: `78cccaf` (Step A audit, **origin/main push 완료 영역 — STOP-PW-1 해제 정합**)
- 본 turn 영역: Step B design 진입 영역 (design only — 신규 .py 0, 신규 함수 본체 0, design doc 박제 단독)
- 사용자 컨펌 (Step A 영역 영역 4 결정 영역 default 채택):
  - 1a input source = chunks schema 확장 (SS/OA 신규 필드 5개)
  - 2b citation layer = `utils/citations.py` 신규 분리 (APA 7th)
  - 3b section prompt = 신규 `get_paper_section_writer_prompt()` (IMRD 4 section 분리)
  - 4b backend priority = section 단위 fetch (4 section × 3 backend = 12 API call)

---

## 사전 view 7 영역 핵심 line ref + finding

| # | 영역 | line ref | finding |
|---|---|---|---|
| 1 | `agent/section_writer.py:1-50` | 1-31 import / 33-53 helper | State / `references` 영역 graph 전역 영역 공유, `target_title` 단일 section 입력 영역 |
| 2 | `prompts.py:394-465` | `get_section_writer_prompt()` 본체 영역 | Q&A 분기 영역 + `[[N]]` marker 영역 본문 안 인용 영역 + `[라벨]` 자체 합성 금지 영역 |
| 3 | `utils/refs.py:181-198` | `_auto_footnote_label` | title 우선 (80자 truncate) + URL fallback — authors/year/venue 영역 처리 영역 **0** |
| 4 | `semantic_scholar.py:204-208` | chunks strip 영역 | `{uri, title, domain}` retained — fetched `title, venue, year, journal, externalIds, openAccessPdf, authors` (line 33) 영역 영역 strip |
| 5 | `openalex.py:108-112` | chunks strip 영역 | `{uri, title, domain}` retained — works response 영역 `primary_location / abstract_inverted_index / authorships / publication_year` 등 영역 strip |
| 6 | `agent/web_search.py:786-815 / 902-919` | vertex grounding + scholarly fan-out 영역 | combined_items 영역 `content = support.text` (vertex) 또는 `content = title` (SS/OA) 영역 |
| 7 | `openalex.py:25 / 80-84` | OA rate limit 영역 | `_OA_BACKOFF_S = 2.0`, 429 single retry (range(2) 영역 max 2 attempts), per-second 영역 명시 부재 (mailto polite pool 영역 정합 영역 default ~10 req/s 영역 영역) |

---

## B-1: chunks schema 확장 design

### 기존 schema (A-5 정합)

```python
# semantic_scholar.py:204-208 / openalex.py:108-112 (동일 패턴)
chunks.append({
    "uri": u,
    "title": paper.get("title") or "",
    "domain": d,
})
```

### 신규 schema (5 필드 박제 영역)

```python
chunks.append({
    "uri": u,
    "title": paper.get("title") or "",
    "domain": d,
    # ── §paper-writer-1 신규 필드 ─────────────────────────────
    "authors": _extract_authors(paper, backend),       # list[str]
    "year": _extract_year(paper, backend),             # int | None
    "venue": _extract_venue(paper, backend),           # str | None
    "doi": _extract_doi(paper, backend),               # str | None
    "abstract": _extract_abstract(paper, backend),     # str | None
})
```

### 필드 별 추출 영역 (backend 별 source path)

| 필드 | SS source path | OA source path |
|---|---|---|
| `authors` | `paper.authors` (list of `{authorId, name}`) → `[a.name for a in authors]` | `work.authorships` (list of `{author: {display_name}}`) → `[a.author.display_name for a in authorships]` |
| `year` | `paper.year` (int) | `work.publication_year` (int) |
| `venue` | `paper.venue` (str) 또는 `paper.journal.name` | `work.primary_location.source.display_name` (catch 60-c 정합 — `host_venue` deprecated 영역 영역) |
| `doi` | `paper.externalIds.DOI` (str) | `work.doi` (str, `https://doi.org/{doi}` 형태 영역) — strip prefix 영역 |
| `abstract` | SS API 영역 `abstract` 필드 영역 fetch field 영역 추가 영역 필요 (`_SS_FIELDS` 영역 `abstract` append) | `work.abstract_inverted_index` (dict[word, list[int]]) → 재조립 영역 (helper 영역 영역) |

### backward compat 영역

- 기존 consumer (`utils/refs.py` `_auto_footnote_label` 등) 영역:
  - `_auto_footnote_label(meta, url)` 영역 `meta.title` 영역 만 사용 영역 → 신규 필드 0 영향 영역
  - 신규 필드 부재 시 (예: combined_items 안 metadata 영역 영역 짧은 영역 영역) default `None` 또는 `[]` 영역 박제 영역 정합
- 기존 c_ab_results.json (§academic-1 ~ §academic-4 영역) 영역 영역:
  - `items` 영역 COUNT (int) 영역 영역 영역 — 신규 chunks 필드 영역 영향 0 (chunks 영역 영역 c_ab_results.json 영역 직접 박제 영역 0)
  - measure_ab.py 영역 영역 chunks 영역 통한 영역 metric 영역 추출 영역 없음 → backward compat 영역 자연 영역 정합

### migration 영역

- 신규 필드 영역 부재 영역 chunks 영역 (legacy 영역 영역) 영역 처리 영역: consumer 영역 영역 `chunks.get("authors", [])` 등 영역 default 영역 영역 영역 — 강제 영역 영역 가드 영역 0
- `_extract_*` helper 영역 backend 별 분기 영역 영역 — extract failure 영역 None / [] 반환 영역 정합 영역

---

## B-2: `utils/citations.py` design

### 신규 모듈 구조 (function signature sketch only, 본체 0)

```python
# utils/citations.py (신규 file)
"""§paper-writer-1 Step C — APA 7th citation formatter.

기존 utils/refs.py footnote layer (= [[N]] marker → URL footer 영역 영역)
대비 영역 → 학술 paper 영역 APA 7th 영역 영역 영역 분리 영역 모듈 영역.

future hook: MLA / Chicago / KCI 영역 추가 영역 정합 영역 동일 signature 패턴 영역.
"""
from typing import Sequence

def format_apa7(
    authors: list[str],
    year: int | None,
    title: str,
    venue: str | None,
    doi: str | None,
) -> str:
    """APA 7th edition citation 영역 영역 1 영역 영역.

    영역 영역 영역 영역 (예시):
    Smith, J. A., & Doe, B. C. (2024). Consumer behavior in influencer marketing.
        *Journal of Marketing Research*, 61(2), 123-145. https://doi.org/10.1177/00222437...

    Returns:
        영역 영역 APA 7th 영역 영역 영역 영역 영역 영역.
        영역 영역 영역 영역 영역 영역 영역 (예: authors=[]) → 영역 영역 영역 영역 영역 영역 (제목 영역 영역 영역).
    """
    ...

def _format_authors_apa7(authors: list[str]) -> str:
    """authors list 영역 APA 7th 영역 영역 영역 영역.

    - 1명: 'Last, F. M.'
    - 2명: 'Last1, F. M., & Last2, F. M.'
    - 3-20명: 'Last1, F. M., Last2, F. M., ..., & LastN, F. M.'
    - 21명 이상: first 19 + ', ... ' + last (et al. 영역 영역 영역 21+ 영역 영역 영역)
    """
    ...

def _format_doi_url(doi: str) -> str:
    """DOI 영역 영역 영역 URL 영역 영역 (https://doi.org/{doi} 영역).

    - 입력 영역 영역 영역 영역 (예: '10.1177/00222437...' 또는 'https://doi.org/...').
    - 영역 영역 영역 영역 (영역 영역 영역 영역 영역 영역 영역 'https://doi.org/' prefix 영역).
    """
    ...
```

### 기존 `utils/refs.py` 영역 연동 영역

- footnote layer (`utils/refs.py` 영역 `attach_auto_citations` / `attach_marker_citations`) 영역 = `[[N]]` marker 영역 본문 안 영역 URL footer 영역 영역 영역 박제 영역
- APA citation 영역 = paper 영역 footer (References section) 영역 영역 박제 영역 영역
- **두 layer 영역 분리 영역 정합 영역**:
  - 본문 안 marker 영역 `[[N]]` 영역 영역 → 기존 footnote 영역 답습 영역 (단순 URL 영역 영역)
  - References section 영역 footer 영역 영역 → APA 7th 영역 (authors + year + title + venue + DOI 영역)
  - 두 layer 영역 같은 chunks 영역 영역 영역 같은 N 영역 영역 영역 (chunks index 영역 영역 동기 영역) — paper writer prompt 영역 영역 `[[N]]` 영역 정합 영역 + post-process 영역 APA footer 영역 영역 영역

### future hook 영역

```python
def format_mla(authors: list[str], title: str, venue: str | None, year: int | None, doi: str | None) -> str: ...
def format_chicago(authors: list[str], year: int | None, title: str, venue: str | None, doi: str | None) -> str: ...
def format_kci(authors: list[str], year: int | None, title: str, venue: str | None, doi: str | None, kci_id: str | None) -> str: ...
```

- signature 동일 패턴 영역 (style 영역 영역 분기 영역 영역 dispatcher 영역 영역 영역 영역 영역 정합 영역)
- future cycle 영역 영역 추가 영역 영역 — §paper-writer-1 본 cycle 영역 영역 APA 7th 영역 default 영역 단독 영역

---

## B-3: `get_paper_section_writer_prompt()` design

### 기존 `get_section_writer_prompt()` (prompts.py:394-465) 답습 + 학술 분기 신규

### 신규 함수 signature

```python
# prompts.py 영역 신규 영역
def get_paper_section_writer_prompt() -> PromptTemplate:
    """§paper-writer-1 — 학술 paper IMRD 4 section 영역 영역 영역.

    기존 get_section_writer_prompt() (보고서 / Q&A 영역) 영역 분리 영역.
    placeholder 신규: {section_type} + {previous_sections}
    """
    ...
```

### IMRD 4 section 분기 영역 (single prompt + section_type 분기)

placeholder 영역:
- `{topic_title}` (기존 영역 영역) — 본 paper 영역 영역 topic 영역
- `{target_title}` (기존 영역 영역) — 본 section 영역 영역 영역 (예: "1. Introduction")
- `{outline}` (기존 영역 영역) — IMRD 4 section 영역 영역 영역
- `{references}` (기존 영역 영역) — section 영역 fetch chunks (B-4 fetch flow 영역 정합) — APA 7th 영역 영역 영역 영역 (`authors / year / title / venue / doi`)
- `{messages}` (기존 영역 영역)
- **{section_type}** (신규 영역) — "Introduction" / "Methods" / "Results" / "Discussion"
- **{previous_sections}** (신규 영역) — section 영역 영역 영역 context 영역 (영역 영역 written 영역 section 영역 markdown 영역 영역 영역 영역 — 영역 영역 영역 영역 영역 영역 영역 + 영역 영역 영역 영역)

### section 별 system instruction (prompt 내부 분기)

```
[section type guide — {section_type}]
- Introduction: 영역 영역 영역 background + research gap + 영역 영역 영역 영역 영역 영역 (research question)
- Methods: 영역 영역 영역 theory framework + design / sample / measurement + 영역 영역 영역 영역
- Results: 영역 영역 영역 영역 영역 영역 영역 영역 (영역 / 영역 / 영역 영역 영역) + 영역 영역 영역 영역 영역
- Discussion: 영역 영역 영역 영역 영역 영역 영역 + implications + limitations + future research
```

### citation 영역 영역 정합 영역

- `[[N]]` marker 영역 답습 영역 (기존 utils/refs.py 영역 영역 정합) — 본문 안 영역 영역 영역 단순 영역 영역 영역
- references 영역 footer 영역 영역 영역 APA 7th 영역 영역 영역 영역 (post-process 영역 hook 영역) — paper writer prompt 영역 영역 References section 영역 영역 영역 영역 영역 (영역 영역 chunks index 영역 영역 영역 영역 영역 영역 영역)

### 분량 영역 영역 (영역 영역 영역 IMRD 영역 정합)

- Introduction: 800~1200 words
- Methods: 600~1000 words
- Results: 1000~1500 words
- Discussion: 1500~2000 words
- 영역 영역 ~5000~7000 words (사용자 컨펌 영역 영역 정합)

---

## B-4: section 단위 fetch flow design

### entry

- paper topic: "consumer behavior in influencer marketing"
- outline: IMRD 4 section (Introduction / Methods / Results / Discussion)

### fetch logic (section iteration)

```python
def section_to_query(topic: str, section_type: str) -> str:
    """IMRD section 영역 영역 영역 영역 영역 영역 영역 영역 query 영역 영역."""
    if section_type == "Introduction":
        return f"{topic} background literature review"
    if section_type == "Methods":
        return f"{topic} theory framework methodology"
    if section_type == "Results":
        return f"{topic} empirical findings data"
    if section_type == "Discussion":
        return f"{topic} synthesis implications limitations"
    return topic

# section iteration loop (sketch)
for section in ["Introduction", "Methods", "Results", "Discussion"]:
    query = section_to_query(topic, section)
    chunks_oa = openalex_search(query)              # primary (ratio 0.80)
    chunks_ss = semantic_scholar_search(query)      # secondary (ratio 0.44)
    chunks_vertex = vertex_web_search(query)        # filter only (ratio 0.17)
    section_chunks = merge_dedupe(chunks_oa, chunks_ss, chunks_vertex)
    section_text = paper_section_writer(section, section_chunks, previous_sections)
    paper.append(section_text)
    previous_sections.append(section_text)
```

### dedup 영역 (영역 영역 영역 영역 영역 영역 영역 영역)

- key 영역: `doi` 우선 (가장 영역 unique 영역), fallback `uri` (canonicalize 영역)
- canonicalize 영역 = `utils/refs.py` 영역 `_canonicalize_src_for_dedup` 영역 답습 영역

### rate limit 영역 정합 영역

- SS authenticated pool (catch 61 영역 영역): ~1 req/s 영역 (영역 영역 영역 영역 영역 영역 영역 영역 영역 12 API call 영역 영역 ~12s 영역 + backoff)
- OA polite pool (mailto + api_key 영역): ~10 req/s 영역 (영역 영역 영역 영역 영역 영역), `_OA_BACKOFF_S = 2.0`, 429 single retry — 12 API call 영역 영역 ~2~5s 영역
- vertex grounding (Google Search grounding 영역): SDK 영역 영역 영역 영역 (현재 영역 영역 영역 명시 영역 부재 영역, vertex_web_search 영역 timeout 영역 정합)
- section 영역 영역 영역 영역 영역 영역 영역 영역 (각 영역 영역 영역 fetch 영역 ~3~5s 영역) — 총 영역 영역 ~15~25s 영역 영역

### 12 API call 영역 영역 단가 영역

- 측정 영역 baseline 영역 catch 49 영역 정합 영역 — Step C 영역 영역 영역 영역 driver 영역 영역 timeout 240s 영역 영역 정합 영역
- OA cost monitor (catch 60-d 영역): 12 call × 1 page-list = 120 credit 영역 (free tier 100k/day 영역 영역 0.12% 영역) — 영역 영역 영역 영역 영역

---

## B-5: 신규 module / function list (Step C 진입 영역 정합)

| 위치 | 영역 | 예상 line |
|---|---|---|
| `utils/citations.py` (신규 file) | `format_apa7()` + helper 2 + module docstring + import | ~80 |
| `prompts.py` (기존 file 영역 영역) | `get_paper_section_writer_prompt()` 신규 함수 영역 | ~150 |
| `tools/web_rag/semantic_scholar.py` (기존 file 영역) | chunks schema 확장 (5 필드 추가 영역) + `_SS_FIELDS` 영역 `abstract` 추가 영역 + `_extract_*` helper 영역 영역 | ~30 |
| `tools/web_rag/openalex.py` (기존 file 영역) | chunks schema 확장 (5 필드 추가 영역) + `_extract_*` helper 영역 영역 (`abstract_inverted_index` 재조립 영역 포함 영역) | ~40 |
| `agent/web_search.py` (기존 file 영역) | section-aware fetch hook 영역 (`section_to_query` + section 별 fan-out 영역 entry) + combined_items 안 신규 필드 영역 박제 영역 | ~50 |
| `agent/section_writer.py` 또는 신규 `agent/paper_section_writer.py` | paper mode 분기 영역 (`{section_type}` placeholder 정합 영역 + `previous_sections` 영역 영역 영역) | ~100 |
| **합계** | | **~450 line** |

### catch 48 정합 영역 산식 영역 영역 (Step C 영역 영역 영역 영역 정밀화 영역 영역)

- (config 변경) = 0 (B-1 영역 영역 영역 영역 영역 영역 영역 default 영역)
- (in-place hook insert) ~ +50 (web_search.py + section_writer.py 영역)
- (신규 함수 정의 본체) ~ +330 (`format_apa7` + helper + `get_paper_section_writer_prompt` + `_extract_*` helper 영역)
- (substitution net) ~ +70 (chunks schema 확장 영역 영역 SS/OA)
- 합계 ~ +450 (영역 ±15% 영역 영역 영역)

### commit 분할 영역 (옵션 B 2-분할 영역 정합)

- **commit 1 (Step C-1)**: 모듈 본체 영역
  - `utils/citations.py` 신규 file (+80)
  - `tools/web_rag/semantic_scholar.py` chunks 확장 (+30)
  - `tools/web_rag/openalex.py` chunks 확장 (+40)
  - `prompts.py` `get_paper_section_writer_prompt()` 신규 (+150)
  - 영역 ~+300 line
- **commit 2 (Step C-2)**: 시스템 통합 영역
  - `agent/web_search.py` section-aware fetch hook (+50)
  - `agent/section_writer.py` paper mode 분기 (또는 신규 `agent/paper_section_writer.py` 신규 file, +100)
  - 영역 ~+150 line

---

## B-6: 측정 design (Step C 영역 영역 영역)

### 신규 측정 driver

- 위치: `writer_project/scripts/§paper-writer-1/measure_paper.py` (Step C 영역 영역 영역 정의 영역)
- 기존 `scripts/§academic-1/measure_ab.py` 영역 답습 영역 (catch 49 / 56 / 65 정합)

### argparse signature 사전 design (catch 65 정합 영역)

```python
parser.add_argument("--topic", type=str,
                    default="consumer behavior in influencer marketing")
parser.add_argument("--sections", type=str, nargs="+",
                    default=["Introduction", "Methods", "Results", "Discussion"])
parser.add_argument("--output-dir", type=str,
                    default="writer_project/scripts/output/§paper-writer-1")
parser.add_argument("--warmup", type=int, default=1)
parser.add_argument("--measure", type=int, default=1)
parser.add_argument("--sleep", type=float, default=2.0)
parser.add_argument("--timeout", type=float, default=240.0)
```

### 측정 axis (3 영역)

1. **APA 7th citation 정합 영역** (regex 영역 검증 영역):
   - References section 영역 영역 영역 영역 영역: `^[A-Z][^,]+,\s+[A-Z]\.\s*[A-Z]?\.?(?:,\s+&?\s*)?.*\(\d{4}\)\.\s+.+\.\s+\*.+\*.*\.\s+https://doi\.org/.+$`
   - threshold: 영역 영역 영역 영역 영역 영역 ≥ 0.8 영역 (영역 영역 영역 영역 영역 영역 영역 영역)
2. **IMRD section 정합 영역**:
   - 4 section 영역 영역 영역 영역 (`## 1. Introduction` / `## 2. Methods` / `## 3. Results` / `## 4. Discussion`)
   - 면적 영역 영역 영역 (B-3 영역 영역 영역 영역 ±20% 영역)
   - threshold: 4/4 section PASS + 면적 영역 ±20% 영역 4/4 PASS
3. **academic_source_ratio 영역 정합 영역** (catch 66 정합):
   - per-backend ratio 영역 박제 영역 (OA / SS / vertex 영역 영역 영역)
   - threshold: OA ratio ≥ 0.70 + SS ratio ≥ 0.40 + 영역 ratio ≥ 0.50 영역 (영역 영역 §academic-4 영역 영역 정합 영역)

### 측정 영역 영역 박제 영역

- `c_paper_measurement.json` 영역 (영역 영역 `c_ab_results.json` 영역 패턴 영역)
- `paper_output_{topic_slug}_{ts}.md` (paper 영역 영역 영역 영역 영역)
- `paper_output_{topic_slug}_{ts}.docx` (영역 영역 영역 영역 영역 영역 영역)

---

## B-7: STOP gates 박제

| gate | 상태 | 영역 영역 영역 |
|---|---|---|
| STOP-PW-1 | **해제 영역 (본 turn 영역)** | Step A audit 영역 push 영역 (`78cccaf → origin/main` 영역 영역) |
| STOP-PW-2 | **활성 영역 (본 turn 영역)** | Step B design commit 영역 push 보류 영역 — Step C entry 영역 영역 영역 영역 영역 영역 영역 |
| STOP-PW-3 | 영역 영역 | Step C 영역 영역 영역 영역 영역 영역 영역 — 측정 PASS 영역 영역 영역 영역 영역 |

---

## Self-check 영역

- [x] STOP-PW-1 해제: `78cccaf → origin/main` push 완료 영역
- [x] 사전 view 7 영역 완료 (line ref + finding 영역 영역 영역 표 영역 박제 영역)
- [x] `step_b_design.md` 박제 (목표 250~400 영역 영역 — 본 파일 영역 영역 영역 영역 commit 후 wc -l 검증 영역)
- [x] B-1 chunks schema 확장 design (5 필드 + backward compat + migration)
- [x] B-2 `utils/citations.py` design (APA 7th signature + helper 2 + future hook)
- [x] B-3 `get_paper_section_writer_prompt()` design (IMRD 4 section 분기 + placeholder 신규 2)
- [x] B-4 section 단위 fetch flow design (`section_to_query` + dedup + rate limit 정합)
- [x] B-5 신규 module/function list (~450 line + commit 2-분할 영역)
- [x] B-6 측정 design (driver argparse + axis 3 영역)
- [x] B-7 STOP-PW-2/3 박제
- [x] commit message catch 62 정합 영역 (prime notation 회피 영역, 영역 영역 영역 영역 영역 영역 영역 underscore + 한국어 자연어 영역)
- [x] STOP-PW-2 push 보류 영역

---

## Step C entry 영역 영역 영역 영역 영역

### commit 2-분할 영역 정합 영역

- commit 1 (Step C-1): 모듈 본체 (~+300 line — citations.py + chunks schema + paper section prompt)
- commit 2 (Step C-2): 시스템 통합 (~+150 line — web_search.py hook + section_writer 분기)

### 측정 driver 영역 영역 영역 영역

- `scripts/§paper-writer-1/measure_paper.py` 영역 Step C-1 영역 영역 영역 commit 영역 영역 영역 영역 (driver 영역 영역 영역 영역 영역 영역 영역 영역 commit 영역 영역 영역 영역 영역 영역)

### Step C 진입 전 사용자 컨펌 영역

1. commit 2-분할 영역 영역 영역 영역 영역 영역 단일 영역 영역 영역 영역 영역 영역 영역
2. measure_paper.py 영역 commit 1 영역 영역 영역 영역 영역 영역 commit 영역 영역 영역 영역 영역
3. catch 48 line budget ~450 영역 영역 ±15% 영역 영역 영역 영역 영역 영역 영역 영역 영역 영역
