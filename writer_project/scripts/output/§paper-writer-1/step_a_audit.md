# §paper-writer-1 Step A audit (read-only, 2026-05-24)

## entry context

- HEAD = `cb2ce1a` (§academic-4 cycle close, origin/main 정합)
- §paper-writer-1 = 학술 논문 (KCI / international) 영역, 보고서 영역 §paper-writer-2 future
- 본 turn = Step A audit 영역 (read-only, 7 영역 view + 박제)
- 사용자 결정 영역 (entry pre-brainstorm 7 영역, hand-off prompt 정합):
  - scope = 학술 논문 우선
  - language = query 영역 auto-detect (catch 43 정합) + user override
  - section = IMRD default + literature review / case study variant 구성 가능
  - citation = APA 7th default + 학회별 variant future
  - input = c_ab_results.json metadata + vertex/web_search chunks (RAG-style hybrid)
  - backend priority = OA primary + SS secondary + vertex filter (catch 66 정합)
  - iteration = section 별 iteration (기존 section_writer 답습)
- 첫 paper 영역: "consumer behavior in influencer marketing", ~5000~7000 words, IMRD default, `.md` + `.docx` 양쪽

---

## Section A-1 — 기존 section-writer 영역

### 발견 file (grep `section_writer|section-writer` --include="*.py" → 14 file hit)

핵심:
- `writer_project/agent/section_writer.py` (513 line) — section 단위 writer agent
- `writer_project/agent/chapter_writer.py` (372 line) — chapter 단위 (심층 컨설팅 포맷) agent
- `writer_project/prompts.py` (751 line) — 모든 prompt 정의 (.txt template 부재)
- `writer_project/core/config.py` / `routers.py` / `models.py` — graph routing 영역
- `writer_project/graph.py` — LangGraph 영역 supervisor → agent routing
- `writer_project/agent/supervisor.py` / `communicator.py` — supervisor + 사용자 응대

### 핵심 식별

- **section iteration pattern**: `section_writer.py` 는 `target_title` 단일 section 입력 → LLM call 1회 → markdown 본문 1 section 반환. `outline` 안 next unwritten section 영역 `utils.outline.next_unwritten_title` 영역 picker 영역
- **prompt template 위치**: `writer_project/prompts.py:394` `get_section_writer_prompt()` / `:323` `get_chapter_writer_prompt()`. 모든 prompt 가 `PromptTemplate.from_template` (LangChain) 영역, placeholder 공통: `{topic_title}` / `{target_title}` / `{outline}` / `{references}` / `{messages}`
- **reference 공유 mechanism**: `core/state_types.State` 안 `references` field 영역 graph 전역 영역 공유. `utils/refs.py` 의 `attach_auto_citations` / `attach_marker_citations` / `build_marker_refs_map` 영역 본문 안 `[[N]]` marker → footnote URL footer 자동 변환
- **citation integration**: 기존 section_writer prompt 영역 `[[N]]` marker 영역 만 허용 (`[라벨]` 자체 합성 금지, file:// http:// 본문 직접 삽입 금지). footnote 본격 박제 영역은 `utils/refs.py` post-process layer 영역 단독 영역
- **doc mode 분기**: `prompts.py` 안 `report` / `book` 두 mode 만 정의 영역, 학술 paper mode 영역 부재

---

## Section A-2 — 기존 prompt templates 영역

### 발견

- `find ... -name "*.txt" -path "*/prompt*"` → **0 file**
- `find ... -name "*.txt" -path "*template*"` → **0 file**
- 모든 prompt 영역 `writer_project/prompts.py` 단일 파일 (751 line) 안 정의
- grep `INTRODUCTION|METHOD|RESULTS|DISCUSSION|LITERATURE REVIEW` → 3 file hit (전부 `tools/web_rag/search.py` + `utils.py` 안 학술 키워드 매칭 영역, prompt 본체 영역 0)

### 핵심 식별

- **existing prompt 목록** (line 정합):
  - `get_supervisor_prompt()` :69
  - `get_content_strategist_prompt()` :118 (DocMode 분기 영역 — report/book)
  - `get_web_search_prompt()` :173
  - `get_chapter_writer_prompt()` :323 (Executive Brief / Key Findings / Analytical Insights / Strategic Options / Action Recommendations / Risks & Mitigations / KPIs & Next Steps / Exhibits 컨설팅 포맷)
  - `get_section_writer_prompt()` :394 (보고서 단편 section 영역, Q&A 모드 분기 영역)
  - `get_communicator_prompt()` :466
  - `get_research_planner_prompt()` :487
- **placeholder pattern**: `{topic_title}` (절대 준수 영역), `{target_title}` (작성 대상 section 영역), `{outline}` (전체 목차 영역), `{references}` (RAG 영역 참고 자료 영역), `{messages}` (이전 대화 영역)
- **section 분기**: 현재 prompt 영역 IMRD / literature review / case study 분기 영역 **부재**. 보고서 (chapter/section writer) + Q&A 두 모드 영역 만
- **학술 모드**: catch 46 (academic prompt tone 분기) LOW 유지 영역 정합 — §paper-writer-1 본 cycle 안 신규 paper writer prompt 영역 정의 영역 필요 (Step B design 영역)

---

## Section A-3 — citation formatter 영역

### 발견 (grep `APA|MLA|Chicago|citation|footnote|bibliography` --include="*.py" → 9 file hit)

핵심:
- `writer_project/utils/refs.py` — `_auto_footnote_label` / `_collect_footnotes_from_refs` / `attach_auto_citations` / `attach_marker_citations` (footnote post-process layer)
- `writer_project/tools/web_rag/_scholarly_domain.py` — DOI → publisher 도메인 매핑 (catch 59 정합, 37+2 entries)
- `writer_project/agent/export/spec.py:113` — slide notes 영역 footnote 보조 설명 영역 (citation 본격 영역 영역 아님)
- `writer_project/scripts/measure_*` — 측정 driver 영역 영역 (citation 본격 영역 아님)

### 핵심 식별

- **기존 citation format**: markdown footnote (`[^N]: <url> (<label>)`) 영역 단독 영역. APA / MLA / Chicago 영역 명시 영역 0 hit (학회 style template 영역 부재 영역)
- **DOI / venue / authors 박제**:
  - `utils/refs.py:181` `_auto_footnote_label` — meta.title 우선, fallback URL last segment (80자 truncate). **authors / year / venue 영역 처리 영역 0**
  - DOI 영역 활용 영역: `tools/web_rag/_scholarly_domain.py` 안 publisher 도메인 매핑 영역 만 (catch 59 정합), citation 영역 영역 본격 활용 영역 0
- **footnote 자동 generation**: `attach_auto_citations` 가 본문 안 `[[N]]` marker → URL footer 자동 변환 영역 정합 작동 영역
- **§paper-writer-1 영역 활용 핵심**:
  - 기존 footnote layer 영역 APA 7th 영역 부적합 — APA 7th 영역 `Author, A. A., & Author, B. B. (Year). Title. *Venue*, vol(issue), pp-pp. https://doi.org/...` 영역 정합 영역 필요
  - 신규 APA citation layer 영역 정의 영역 필요 (authors + year + title + venue + DOI 5 필드 영역) — Step B design 영역 영역

---

## Section A-4 — c_ab_results.json schema 영역 ⚠️ **CRITICAL FINDING**

### 위치 + 영역

- `writer_project/scripts/output/§academic-1/c_ab_results.json` (1920 line)
- 상위 schema: `generated_at_utc` + `standards` + `host` + `python` + `env_probe` + `dry_run` + `topic_results`
- `topic_results`: 3 topics (`business-venfobel` / `academic-en` / `academic-ko`) × 5 runs 각각 (2 warmup + 3 measure)

### 각 run 안 per-backend (vertex / legacy / semantic_scholar / openalex) schema

```
{
  "mode": "vertex" | "legacy" | "semantic_scholar" | "openalex",
  "skipped_by_catch43": bool,        # catch 43 routing skip 여부
  "items": int,                       # ★ entries 개수 COUNT (NOT array)
  "domains": list[str],               # host 영역 list (item 별)
  "domains_unique": list[str],
  "backend_signals": list[str],       # tavily_or_other | naver_direct
  "naver_count": int,
  "error": str | null,
  "elapsed_sec": float
}
```

### 각 run summary

`all_domains_unique` / `academic_domains_hit` / `academic_source_ratio` / `academic_hit_count` / `academic_ratio_per_backend` (catch 66 정합 신규 metric) / `ts_utc` / `phase` / `run_index`

### ⚠️ CRITICAL FINDING

- **`items` 영역 = backend response 영역 COUNT (int) 영역**, raw entries (title / DOI / authors / abstract / venue) **미박제 영역**
- 정량 grep 영역 검증: `title|doi|authors|abstract|venue` (case-insensitive) → c_ab_results.json 안 **0 hit**
- **영향**: §paper-writer-1 영역 input source 영역 c_ab_results.json **단독 직접 활용 영역 불가능 영역** — backend behavior verification metadata 만 박제 영역, 본문 작성 영역 content (title/abstract 등) 0
- **정합 대응**:
  - paper-writer pipeline 안 vertex_web_search + scholarly fan-out **live re-run 영역 필요** (RAG-style hybrid) — 기존 section_writer 영역 답습 영역 정합
  - c_ab_results.json 영역 활용 영역 = backend priority baseline (catch 66 per-backend ratio 영역 input), NOT content source
  - 추가 영역: SS / OA backend API call 직접 영역 abstract / authors / venue / year / DOI 영역 fetch layer 영역 신규 정의 영역 필요 (A-5 finding 참조)

---

## Section A-5 — vertex_web_search / web_search chunks 영역

### 발견 (grep `chunks|supports|chunk_id|support_id` --include="*.py" agent/ → 2 file)

- `writer_project/agent/web_search.py` (1600+ line) — 통합 web_search agent
- `writer_project/agent/vector_search.py` — RAG retrieve agent (vertex grounding 호출 영역 영역 아님)

### vertex grounding schema (web_search.py:786-815)

```python
vertex_result = {
  "chunks": list[{uri, domain, ...}],
  "supports": list[{text, chunk_indices: list[int]}],
  "web_search_queries": list[str],
}
# combined_items 박제 영역 (line 805-816):
{
  "title": "",                       # vertex 영역 title 영역 부재 영역
  "url": rep_url,
  "content": support.get("text"),    # vertex grounding 안 본문 발췌 영역
  "raw_content": "",
  "source": rep_url,
  "metadata": {"backend": "vertex_grounding", "alt_urls": [...], "chunk_domain": ...},
}
```

### scholarly fan-out schema (web_search.py:902-919)

```python
sch_result = {
  "chunks": list[{uri, title, domain}],   # ← SS/OA chunks 영역
  "supports": list[{chunk_indices, text: title, start_index, end_index}],
  ...
}
# combined_items 박제 영역:
{
  "title": ch.get("title") or "",
  "url": u,
  "content": ch.get("title") or "",   # ★ content = title 영역 (abstract 영역 0)
  "raw_content": "",
  "source": u,
  "metadata": {"backend": name, "chunk_domain": ...},
}
```

### ⚠️ **활용 한계 영역**

- SS Graph API 영역 fetch fields 영역 (`semantic_scholar.py:33`): `title, venue, year, journal, externalIds (DOI), openAccessPdf, authors`
- **단 chunks 영역 정합 안 retained = `uri, title, domain` 단독 영역** (semantic_scholar.py:204-208)
- → authors / year / venue / DOI 영역 **API 영역 fetch 되나 pipeline 영역 strip 영역**
- OA 영역 동일 패턴 (`openalex.py` 영역 fields 영역 fetch 영역, chunks 영역 retained 영역 한정 영역 정합)
- **§paper-writer-1 영역 영향**:
  - 본문 작성 영역 abstract / full text 영역 영역 영역 **현재 pipeline 부재** — 신규 fetch layer 영역 필요
  - APA 7th citation 영역 영역 (authors + year + venue + DOI) 영역 영역 chunks 영역 schema 확장 영역 필요 (chunks 안 `authors`, `year`, `venue`, `doi` 영역 신규 필드 영역 박제)
  - Step B design 영역 채택 영역: 옵션 영역 (a) scholarly backend 영역 chunks schema 영역 확장 영역 (SS/OA 동시) / (b) 별도 metadata fetcher layer 영역 신규 정의 영역 / (c) section 별 fetch 영역 캐싱 layer 영역

---

## Section A-6 — Bell Agent ChromaDB 영역 (활용 가능 여부)

### 발견 (grep `chromadb|ChromaDB|chroma_client` --include="*.py" → 9 file hit)

- `writer_project/tools/web_rag/ingest_vector.py` — Chroma wrapper 본체 (`_get_vs` :319, `_resolve_ns` 안 collection_name resolve)
- `writer_project/check_chunks.py` — debug script
- `writer_project/app.py` — 영역 진입 영역
- `writer_project/tools/{metrics,diagnose_richness}.py` — debug + metric 영역
- `writer_project/scripts/{_phase_b_run_inner.py,_phase_b_clear_ns.py,output/§14-3/_phase3/_chroma_diag.py}` — phase B 측정 driver

### 핵심 식별

- **collection 영역**: 동적 영역 (`_resolve_ns` 영역 namespace 영역 → `collection_name=ns` 영역). 토픽 별 collection 분리 영역 (예: 토픽 영역 기반 namespace 영역 — `business-venfobel` / `academic-en` 등 영역)
- **학술 collection 영역 존재 영역 여부**: **현재 영역 영역 web_search 결과 영역 chunk 단위 영역 ingestion 영역 (vertex chunks + 학술 backend chunks 영역 통합 영역)** — paper 단위 영역 pre-indexed 학술 corpus 영역 분리 영역 **부재 영역**
- **§paper-writer-1 영역 영향**:
  - ChromaDB 영역 자체 영역 paper-writer 영역 input source 영역 영역 활용 영역 **0** (paper pre-indexed corpus 영역 부재 영역)
  - section_writer pipeline 영역 답습 영역 — live web_search → ChromaDB ingest → retrieve chain 영역 정합 영역
  - future cycle (§paper-writer-3+) 영역 학술 corpus 영역 pre-ingest 영역 영역 별 cycle 후보 영역 (KCI / Semantic Scholar bulk download 영역 영역)

---

## Section A-7 — catch index 영역 §paper-writer-1 영역 활용 영역 정합

### 활용 catch (active)

- **catch 43** (language-aware backend routing) — query auto-detect 영역 활용. 영어 query → vertex + SS + OA fan-out, 한국어 query → naver + vertex (`agent/web_search.py:877-879` 분기 영역)
- **catch 51** (4-backend architecture 정합, EN academic 영역 PARTIAL 영역) — paper-writer-1 영역 backend priority 영역 핵심 활용. §academic-4 cycle 안 fix S1 (SS + OA scholarly fan-out 영역 정합 작동, mean ratio 0.3915 < 0.6 PARTIAL)
- **catch 59** (DOI prefix → publisher 매핑 37+2 entries) — paper-writer-1 영역 citation 영역 핵심 활용. APA 7th venue field 영역 정합 영역 (단 `_scholarly_domain.extract_domain_from_paper` 영역 정합 영역 publisher domain 영역 단독 영역, journal name 영역 별도 영역 SS `journal.name` field 영역 영역 활용 영역)
- **catch 61** (SS authenticated pool 활성, 1B 전환 확정) — paper-writer-1 영역 SS 영역 본격 활용 (anonymous 429 fail isolation 해소 영역). `.env.semanticscholar` 영역 `SEMANTIC_SCHOLAR_API_KEY` + `SEMANTIC_SCHOLAR_SKIP=0` 영역 정합 영역 가정 영역
- **catch 66** (per-backend ratio finding, methodology) — backend priority 영역 핵심 finding 영역:
  - vertex 0.17 (range 0.15~0.29, 비학술 dilution 본질 영역) → **filter 영역**
  - legacy 1.0 (단 ko 단독 영역) → ko query 영역 단독 영역
  - SS 0.44 → **secondary**
  - OA 0.80 → **primary**
  - hand-off 영역 결정 영역 정합 (OA primary + SS secondary + vertex filter)
- **catch 67** (set 보강 4 entries — 대학 publication + 소형 OA) — paper-writer-1 영역 학술 hit 영역 정합 (academic_hit_count 평균 8.0 영역)

### 활용 lesson catch (process)

- **catch 48** (line budget 산식, neutral 함수 본체 + separator + inline 주석 stand-alone 영역 포함 영역) — Step B design 영역 진입 시 신규 함수 본체 line 산식 강제 영역, 본 Step A 영역 read-only 영역 적용 불요
- **catch 49** (measurement driver SDK-level timeout + probe + provider lock + flush stage marker) — Step C 영역 진입 시 (예: paper output quality 측정 영역) 활용
- **catch 56** (driver args output 경로 부재) — paper-writer driver 영역 신규 정의 영역 argparse `--output-dir` 강제 권장 영역
- **catch 62** (PowerShell heredoc apostrophe escape) — 본 cycle commit message 영역 prime notation 회피 (예: `1A_prime` / `1A_post` / 한국어 자연어 표기 영역) — **본 turn commit message 영역 적용 영역**
- **catch 65** (hand-off prompt 영역 driver argparse 사전 view) — Step B/C 영역 driver 영역 신규 정의 영역 발화 가능 영역

### 비활용 catch (본 cycle 영역 영역 0)

- catch 44 / 45 / 47 (KR 학회 identity / KR A1 fail / mixed-lang) — §paper-writer-1 영역 영문 학술 우선 영역, KR 영역 별도 cycle (§paper-writer-1 close 후 KR cycle 진입 영역 가능)
- catch 46 (academic prompt tone 분기) — §paper-writer-1 영역 신규 paper writer prompt 영역 본격 정의 영역 영역, lesson 영역 보다 본 cycle 안 본격 진입 영역 (Step B design 영역 영역)
- catch 52 / 53 / 54 / 55 / 57 / 58 / 60 / 64 — 본 cycle 영역 영역 영향 0 (process lesson 영역 영역)

---

## Step B design 영역 entry point (사용자 컨펌 대기 영역)

### 사용자 컨펌 영역 (Step B 진입 영역 4 영역)

1. **input source 영역 RAG-style hybrid 영역 — 채택 형태 영역**
   - A-4 critical finding 정합: c_ab_results.json 단독 활용 불가 → paper-writer pipeline 안 vertex + SS + OA **live re-run 영역 필수**
   - A-5 한계 영역 정합: SS/OA chunks 영역 현재 `uri/title/domain` strip 영역 → APA 7th 영역 (authors + year + venue + DOI) 영역 추가 fetch / 또는 chunks schema 확장 영역 필요
   - **옵션 영역**: (a) scholarly backend 영역 chunks schema 영역 확장 (가장 적은 면적, SS/OA 동시) / (b) 별도 metadata fetcher layer 영역 신규 정의 영역 / (c) section 별 fetch 영역 캐싱 layer 영역
   - **default 권장 영역**: 옵션 (a) — chunks 영역 신규 필드 `authors / year / venue / doi / abstract` 영역 박제 영역 (SS/OA 측 fetch fields 영역 이미 영역 추가 영역 0)

2. **citation layer 영역 — APA 7th 영역**
   - 기존 `utils/refs.py` footnote layer 영역 APA 7th 영역 부적합 → 신규 APA citation formatter layer 영역 정의 영역 필요
   - **옵션 영역**: (a) `utils/refs.py` 안 APA 분기 영역 신규 함수 영역 추가 영역 / (b) `utils/citations.py` 신규 영역 분리 영역 (style 별 확장 영역 정합)
   - **default 권장 영역**: 옵션 (b) — 학회별 variant future 영역 정합 영역 (MLA / Chicago / KCI 학술지 영역 별 영역 분기 영역 확장 영역 정합 영역)
   - **컨펌 영역**: 본 cycle 안 APA 7th 영역 default 영역 단독 영역 채택 영역 (학회별 variant future) vs 신규 layer 영역 다중 style 영역 기본 정의 영역

3. **section iteration pattern 영역 — IMRD 4 section 영역**
   - 기존 `section_writer.py` agent 영역 답습 영역 — IMRD 4 section (Introduction / Methods / Results / Discussion) 각 영역 별 LLM call 영역 + previous_sections 영역 context 영역 공유 영역
   - **옵션 영역**: (a) 기존 `get_section_writer_prompt()` 영역 학술 분기 영역 추가 영역 (보고서 / Q&A 분기 영역 + 학술 영역 분기 영역) / (b) 신규 `get_paper_section_writer_prompt()` 영역 분리 영역 정의 영역
   - **default 권장 영역**: 옵션 (b) — 학술 paper 영역 IMRD section 영역 별 영역 (Introduction prompt / Methods prompt / Results prompt / Discussion prompt) 영역 분리 영역 영역 정합 영역
   - **컨펌 영역**: IMRD 4 section 영역 각 영역 별 prompt 영역 분리 영역 vs 단일 prompt + section type placeholder 영역

4. **backend priority 영역 (catch 66 정합) — query 단위 영역 vs section 단위 영역**
   - OA primary (0.80) + SS secondary (0.44) + vertex filter (0.17) — hand-off 영역 결정 영역 정합 영역
   - **옵션 영역**: (a) query (= paper topic) 단위 영역 영역 단일 fetch 영역 (modular 영역) / (b) section 단위 영역 영역 (Introduction / Methods 별 영역 영역 fetch 영역)
   - **default 권장 영역**: 옵션 (b) — section 별 영역 영역 학술 backend 영역 (예: Methods → SS theory query / Results → OA empirical query 영역) 영역 query 정합 영역 정합 영역
   - **컨펌 영역**: section 단위 영역 fetch 영역 단가 영역 (4 section × 3 backend = 12 API call 영역 영역) 영역 vs query 단위 영역 단순 영역 (1 query × 3 backend = 3 API call 영역)

### STOP gates 영역

- **STOP-PW-1** (paper-writer Step A audit commit 영역 push 보류) — Step A audit 영역 정합성 점검 영역 + Step B design 영역 entry 영역 사용자 컨펌 영역 (위 4 영역) 후 해제 영역
- 신규 cycle 영역 영역 STOP gate prefix = `PW` (paper-writer 영역) — §academic 영역 prefix `C` 영역 영역 분리 영역 정합

### Step A line budget 보고 (catch 48 정합)

- `step_a_audit.md` 영역 라인 카운트 = (본 파일 wc -l 영역 commit 후 검증 영역, 예상 ~210 line 영역, 목표 +150~250 line 영역 정합)
- read-only audit 영역 영역 신규 함수 / hook / config 변경 영역 **0**
- commit 영역 변경 면적 = step_a_audit.md 신규 영역 단독 영역

---

## Self-check 영역

- [x] A-1 ~ A-7 각 영역 영역 view + finding 박제
- [x] critical finding 영역 명시 (A-4 c_ab_results.json 영역 entries schema 영역 + A-5 scholarly chunks strip 영역)
- [x] step_a_audit.md 신규 파일 박제 (~+210 line, 목표 +150~250 정합)
- [x] §paper-writer-1 cycle 영역 catch 활용 영역 박제 (catch 43 / 51 / 59 / 61 / 66 / 67 active + 48 / 49 / 56 / 62 / 65 lesson)
- [x] catch 48 budget check 보고 (read-only, 면적 변경 0)
- [x] commit message HEREDOC catch 62 정합 (prime notation 회피 — `1A_prime` 표기 영역)
- [x] STOP-PW-1 박제 (push 보류 영역)
