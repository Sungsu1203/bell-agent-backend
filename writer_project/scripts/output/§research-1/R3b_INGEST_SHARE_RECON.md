# R3b — `ingest_vector.py` 공유 범위 정찰

- 사이클: §research-1 선분 3 정찰 0
- 일자: 2026-08-07
- 성격: **읽기 전용.** 코드 수정 0건 · 파이프라인 실행 0건 · 유료 호출 0건 · Chroma 개방 0건(`sqlite3 -readonly`만)
- 산출물: 이 파일 1건
- **판정 절 없음.** 근거만 싣는다. 확인 못 한 항목은 "미확인"으로 남긴다.

## 세션 개시 재검증 (catch AR)

```
$ git log --oneline -8 && git diff --stat && git status --short
5b16cdd5 docs(§research-1): 재색인으로 청크 바뀌면 청크 ID 대조 깨짐메시지 추가
9c0dbdd7 docs(§research-1): GUARDRAILS 갱신 — 노이즈 유형 2건 추가 + 활성 토픽 공유 명시 + 상태 정정
e2a4305f docs(§research-1): 북극성 박제 — objective 기반 리서치 파이프라인 목표 재정의
dda58a70 docs(§research-1): Q-1 dist 원자료 박제
144dbe7d docs(§research-1): WORKBOARD 갱신 — 목표 재정의 + 선분 1 종결 + 이월표 재편
16de443f docs(§research-1): Q-2 종결 — 선분 1 요건 확정, 코드 반영 방식 미정
da1e4417 §research-1 R3-1 종결 — FAIL 확정 + 원인 규명 박제
07b7ec0c §research-1 R2-a: R1b 정정 2건 + .gitignore 확장 + WORKBOARD 전환 + 설계 입력 수집
```

- 워킹트리 수정 1건 = `scripts/§paper-writer-1/measure_paper.py` (+6행). **논문 트랙 미커밋분 상주 — catch AS 조건 유효.**
- untracked 20항목. `probe_*.py` 2건 포함.
- 인계 메모(`NEXT_SESSION_20260806_research-1-segment3-open.md`) 기술과 git 실물 사이 불일치 **0건**.

---

## 확인 1 — `ingest_vector.py` 실체

| 항목 | 실물 | 근거 |
|---|---|---|
| 경로 | `writer_project/tools/web_rag/ingest_vector.py` | `find . -name "ingest_vector*.py"` → **1건만** |
| 행수 | **1,897행** / 77,807 B | `wc -l` |
| mtime | 2026-06-01 15:57 | `ls -la tools/web_rag/` |
| **CLI 진입점** | **없음** | `grep -n "__main__\|argparse\|ArgumentParser\|sys.argv"` → **0건** |
| 진입 형태 | 라이브러리 모듈 (import 전용) | 위와 동일 |

### 공개 심볼 (`__all__`, `:1885~1897`)

| 함수 | 라인 | 시그니처 |
|---|---|---|
| `split_documents` | `:408` | `(documents: List[Document], *, chunk_size: Optional[int]=None, chunk_overlap: Optional[int]=None) -> List[Document]` |
| `clear_vector_store` | `:654` | `(namespace: Optional[str]=None, persist_directory: Optional[str]=None) -> str` |
| `ensure_vector_store_cleared_once` | `:744` | `(namespace, *, persist_directory=None)` |
| `documents_to_chroma` | `:775` | 본체(628행, `:775~1402`) |
| `has_any_docs` | `:1403` | `(ns: str, base_dir: str) -> bool` |
| `add_web_pages_json_to_chroma` | `:1442` | → `documents_to_chroma` 위임(`:1472`) |
| `add_documents_to_chroma` | `:1502` | **alias.** → `documents_to_chroma` 위임(`:1521`) |
| `retrieve` | `:1533` `@tool("retrieve")` | `(query, *, top_k=5, namespace=None, collection_name=None, persist_directory=None, embedding=None)` |
| `get_collection_count` | `:1715` | `(ns: str, base_dir: str) -> int` |
| `get_total_collection_count` | `:1769` | `()` |
| `seed_web_namespace` | `:1789` | → `:1820` `add_web_pages_json_to_chroma` / `:1846` `documents_to_chroma` |

### 청킹 함수 본문 (`split_documents`, `:408~419` 전량 덤프)

```python
def split_documents(
    documents: List[Document],
    *,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[Document]:
    cs = (_cfg_int("RAG_CHUNK_CHARS", 2400) if chunk_size is None else int(chunk_size))
    ov = (_cfg_int("RAG_CHUNK_OVERLAP", 200) if chunk_overlap is None else int(chunk_overlap))
    cs = max(300, min(cs, 6000))
    ov = max(0, min(ov, int(cs * 0.5)))
    splitter = RecursiveCharacterTextSplitter(chunk_size=cs, chunk_overlap=ov)
    return splitter.split_documents(documents)
```

- 내부 유일 호출부 = `documents_to_chroma:1090`.
- 모듈 내 자기규약(`:100`): `ingest_vector.py → ingest.py` import는 **순환 위험으로 금지** 명시.

---

## 확인 2 — 호출부 전량 (양쪽 grep 실행)

### 2-a. 두 명령 결과 대조

| 명령 | 히트 |
|---|---|
| A. `git -c core.quotePath=false grep -n "ingest_vector" -- '*.py'` | **26** |
| B. `grep -rn --include="*.py" "ingest_vector" .` (`.venv`·node_modules 제외) | **28** |

**불일치 2건 — 전부 untracked `probe_*.py`:**

```
writer_project/probe_local_dump.py:7:from tools.web_rag.ingest_vector import _get_vs, _default_chroma_dir
writer_project/probe_dist_adtrack.py:23:from tools.web_rag.ingest_vector import _get_vs, _default_chroma_dir
```

- 차집합은 이 2건이 전부다(26 + 2 = 28). B에만 있고 A에 없는 항목은 이 둘 외 없음.
- 원인 = `.gitignore:106 probe_*` 로 untracked → git grep 사각.
- ⚠️ 확장자 제한 없이 돌리면 A가 훨씬 커진다(`.md`/`.txt` 문서 인용 다수). 위 26 vs 28은 **양쪽 `*.py` 한정**으로 맞춘 값.

### 2-b. 히트 26/28건 분류 (육안)

**① 실행 호출 (함수를 실제로 부름) — 1건**

| 위치 | 내용 |
|---|---|
| `agent/supervisor.py:417` | `from tools.web_rag.ingest_vector import get_collection_count` (함수 내부 지연 import + 호출) |

**② import / 재노출 — 8건**

| 위치 | 내용 |
|---|---|
| `tools/web_rag/ingest.py:702-715` | **재노출 허브.** `documents_to_chroma` 외 12심볼을 `from .ingest_vector import (...)` |
| `tools/diagnose_chunks_deep.py:14` | `_get_vs, _default_chroma_dir` |
| `tools/diagnose_distance_threshold.py:18` | `_get_vs, _default_chroma_dir` |
| `tools/diagnose_embed_validate.py:33` | `_default_chroma_dir, _get_vs` |
| `tools/diagnose_embeddings.py:14` | `_get_vs, _get_embeddings, _default_chroma_dir` |
| `scripts/_phase_b_clear_ns.py:54` | `_default_chroma_dir` |
| `scripts/_phase_b_run_inner.py:77` | `_default_chroma_dir` |
| `scripts/§research-1/run_r3a_straight.py:358` | `_default_chroma_dir` |

**③ 드라이버(untracked) — 2건**

| 위치 | 내용 |
|---|---|
| `probe_local_dump.py:7` | `_get_vs, _default_chroma_dir` |
| `probe_dist_adtrack.py:23` | `_get_vs, _default_chroma_dir` |

**④ 문서·주석 인용(코드 무효) — 15건**

`tools/local_rag.py:22`·`:1147` / `tools/threshold_sweep.py:7` / `tools/web_rag/ingest.py:374`·`:698`·`:700`·`:747`·`:795`·`:821` / `tools/web_rag/ingest_vector.py:100` / `tools/web_rag/utils.py:86`·`:385`·`:451`·`:483`·`:781`·`:798` / `tests/test_xlsx_score_compat.py:8`
(주석·docstring 문자열. 실행 경로 아님.)

### 2-c. 재노출 경유 실제 호출부 (`ingest_vector` 문자열이 없어 2-a 검색에 안 걸림)

공개 API 이름으로 재검색한 결과. **`ingest.py`가 재노출 허브이므로 대부분의 호출부는 `from tools.web_rag.ingest import ...` 형태다.**

| 위치 | 심볼 | 분류 |
|---|---|---|
| `agent/web_search.py:44` | `add_web_pages_json_to_chroma` import | import |
| `agent/web_search.py:1057` | `add_web_pages_json_to_chroma(...)` **호출** | 호출 |
| `agent/web_search.py:1377` | `add_web_pages_json_to_chroma=...` 주입 | 호출(인자 전달) |
| `agent/vector_search.py:37`·`:39` | `add_web_pages_json_to_chroma`, `ensure_vector_store_cleared_once` import | import |
| `agent/vector_search.py:788`·`:793`·`:795` | `ensure_vector_store_cleared_once(...)` **호출** | 호출 |
| `agent/vector_search.py:645`·`:748` | `_has_any_docs(...)` **호출** | 호출 |
| `agent/vector_search.py:1062` | `add_web_pages_json_to_chroma=...` 주입 | 호출(인자 전달) |
| `agent/supervisor.py:41`·`:45` | `seed_web_namespace`, `has_any_docs` 동적 훅 import | import |
| `agent/supervisor.py:230` | `_has_any_docs(...)` **호출** | 호출 |
| `tools/local_rag.py:1582` | `add_web_pages_json_to_chroma(...)` **호출**(주입된 콜러블) | 호출 |
| `tools/local_rag.py:1632` | `from tools.web_rag import add_web_pages_json_to_chroma as _aw` | import |
| `tools/web_rag/__init__.py:75~92` | 런타임 lazy 래퍼(`documents_to_chroma` 등 4종) | 재노출 |
| `tools/web_rag/__init__.py:14~18` | ⚠️ **`if TYPE_CHECKING:` 블록 내부** — 타입체커 전용, 런타임 미실행 | 비실행 |
| `tools/web_rag/search.py:95` | `getattr` 문자열 조회 3순위(`documents_to_chroma`→`add_documents_to_chroma`→`documents_to_chroma_compat`) | 동적 호출 |

**`agent/web_search.py:1057`·`:1377` 소속 함수 (역방향 확인)**

```
$ awk -v tgt=1057 'NR<=tgt && /^(async )?def /{n=NR; l=$0} NR==tgt{print n": "l}' agent/web_search.py
181: def web_search_agent(state: State):
$ (tgt=1377 → 동일하게 181: def web_search_agent(state: State):)
```

150~1450 구간 최상위 def 목록 = `:161 _host_of` · `:173 _item_rank` · `:181 web_search_agent` 3개뿐.
→ **두 Chroma 호출 지점은 모두 LangGraph 노드 `web_search_agent(state)` 내부**다.

---

## 확인 3 — 논문 트랙이 같은 파싱·청킹 함수를 **실행하는가**

### 3-a. 논문 트랙 진입점 식별

| 진입점 | 실물 |
|---|---|
| 드라이버 | `scripts/§paper-writer-1/measure_paper.py` (`:541 if __name__ == "__main__"` → `:433 main()`) |
| 파이프라인 import | `measure_paper.py:154` `from agent.web_search import paper_section_fetch`<br>`measure_paper.py:155` `from agent.paper_section_writer import (...)` |
| 1회 실행 본체 | `measure_paper.py:239 _run_one_paper()` |

### 3-b. 수집 → 청킹 → 색인 사슬 추적

`_run_one_paper` (`:239~306`) 전량 육안. 실행 순서:

| 단계 | 라인 | 호출 |
|---|---|---|
| fetch | `:254` | `chunks = paper_section_fetch(topic, section)` |
| 태깅 | `:260~262` | `_c["_section"] = section`; `section_chunks_all.extend(chunks)` |
| write | `:267` | `write_paper_section(..., references_chunks=chunks, ...)` |
| refs | `:290` | `build_apa_references(section_chunks_all)` |

`paper_section_fetch` (`agent/web_search.py:1988~2074`) 전량 육안. 호출하는 것:

| 라인 | 호출 |
|---|---|
| `:1994~1996` | `openalex_search` · `semantic_scholar_search` · `vertex_web_search` import |
| `:2007` | `_load_and_hydrate_seeds(...)` (seed JSON 로드 → `openalex_search` hydrate) |
| `:2024~2033` | 백엔드 fan-out → `all_chunks.append(ch2)` |
| `:2038` | `_clean_chunk_text(_ch)` |
| `:2051~2064` | doi-dedup |
| `:2067` | `_apply_venue_overrides(...)` |
| `:2074` | `return all_chunks` (dict 리스트 그대로 반환) |

### 3-c. 공유 함수 실행 여부

| 대상 | 결과 | 근거 |
|---|---|---|
| `split_documents` | **실행 없음** | `paper_section_fetch`·`_run_one_paper` 경로에 호출 0 |
| `documents_to_chroma` 계열 | **실행 없음** | 동일 |
| `retrieve` | **실행 없음** | 동일 |
| `agent/paper_section_writer.py` | **실행 없음** | `grep -n "chroma\|Chroma\|retrieve\|ingest\|vector"` → **0건** |
| `scripts/§paper-writer-1/**.py` | **실행 없음** | `grep -rn "chroma\|Chroma\|retrieve\|documents_to_chroma\|ingest\|vector_search"` → **0건** |
| `scripts/§academic-1/**.py` · `scripts/§academic-4/**` | **실행 없음** | 동일 grep → **0건** |

⚠️ **import는 일어난다 — 실행과 구분할 것.**
`measure_paper.py:154`가 `agent.web_search`를 import하면 `agent/web_search.py:44`의
`add_web_pages_json_to_chroma` 모듈 레벨 import가 함께 실행되고, 그 결과
`ingest.py:702` → `ingest_vector` 모듈이 **로드된다**.
그러나 호출 지점(`:1057`·`:1377`)은 `web_search_agent(state)` 내부이고
논문 드라이버는 그 노드를 부르지 않는다(확인 2-c).

**→ 논문 트랙에서 공유 파싱·청킹 함수 실행: 없음. 모듈 로드만 발생.**

---

## 확인 4 — persist 경로·컬렉션명 결정 지점

### 4-a. 컬렉션명(=namespace) 결정 — `ingest_vector.py:213~235` 전량 덤프

```python
def _resolve_ns(namespace=None, collection_name=None) -> str:
    if namespace and namespace.strip():          # 1) 함수 인자
        return namespace.strip()
    if collection_name and collection_name.strip():  # 2) 함수 인자
        return collection_name.strip()
    env_ns = (getattr(CFG, "CHROMA_NAMESPACE", "") or "").strip()   # 3) CFG
    if env_ns:
        return env_ns
    topic_slug = (getattr(CFG, "TOPIC_SLUG", "") or "").strip()     # 4) CFG
    if topic_slug:
        return f"{topic_slug}-default"
    return "default"                                                # 5) 상수
```

| 순위 | 무엇 | 결정 지점 |
|---|---|---|
| 1 | **함수 인자** `namespace` | `ingest_vector.py:225` |
| 2 | **함수 인자** `collection_name` | `ingest_vector.py:227` |
| 3 | **CFG** `CHROMA_NAMESPACE` | `ingest_vector.py:229` |
| 4 | **CFG** `TOPIC_SLUG` + `-default` 접미 | `ingest_vector.py:232~234` |
| 5 | **상수** `"default"` | `ingest_vector.py:235` |

⚠️ **4순위는 `TOPIC_SLUG`가 set된 상태에서는 도달 불가.**
`core/config.py:443~456`이 `CHROMA_NAMESPACE`를 자동 파생하기 때문:

```python
# core/config.py:450~456
slug = _sanitize_ns(self.TOPIC_SLUG or "default")
if not (self.CHROMA_NAMESPACE or "").strip():
    self.CHROMA_NAMESPACE = slug
if not (self.CHROMA_NAMESPACE_WEB or "").strip():
    self.CHROMA_NAMESPACE_WEB = f"{slug}-web"
if not (self.CHROMA_NAMESPACE_LOCAL or "").strip():
    self.CHROMA_NAMESPACE_LOCAL = f"{slug}-local"
```

→ `TOPIC_SLUG`만 있어도 3순위가 항상 채워진다. 파생 결과는 `-default`가 아니라 **slug 그대로**.

### 4-b. persist 경로 결정 — `tools/web_rag/utils.py:1696~1744`

```python
def _resolve_persist_dir(namespace, persist_directory) -> str:
    ns = sanitize_ns(namespace)
    if persist_directory is not None:                        # 1) 함수 인자
        ...; return str(out)
    chroma_dir = (_cfg_str("CHROMA_DIR", default="") or "").strip()   # 2) CFG
    if chroma_dir:
        ...; return str(out)
    out = (DATA_DIR / "chroma_store" / ns)                    # 3) 상수 경로
    out.mkdir(parents=True, exist_ok=True)
    return str(out)
```

| 순위 | 무엇 | 결정 지점 |
|---|---|---|
| 1 | **함수 인자** `persist_directory` | `utils.py:1727~1731` |
| 2 | **CFG** `CHROMA_DIR` | `utils.py:1734~1739` |
| 3 | **상수** `DATA_DIR / "chroma_store" / <ns>` | `utils.py:1742~1744` |

`DATA_DIR` 정의 = `utils.py:314` — `_cfg_str("WEB_RAG_DATA_DIR", "")` 있으면 그 값, 없으면 `PROJECT_ROOT / "data"`.

**래퍼 2종**

| 함수 | 라인 | 동작 |
|---|---|---|
| `_default_chroma_dir(namespace)` | `ingest_vector.py:262~263` | `_resolve_persist_dir(namespace, None)` 단순 위임 |
| `_resolve_persist_dir_strict(ns, pd)` | `ingest_vector.py:237~259` | split 모드(`CHROMA_NAMESPACE_WEB`·`_LOCAL` 둘 다 set)에서 ns가 web/local이면 **인자 `persist_directory`를 무시하고** ns 고유 디렉터리로 강제(`:252` `pd_expected`, 불일치 시 `:254` WARNING) |

### 4-c. env 계층 판정 (STANDARDS §1)

> 🔴 **2026-08-07 정정 — 최초 작성분의 "L1/L2 0건"은 오류였다.**
> 원인: `grep -rn "CHROMA" --include=".env*" .` 는 **재귀 모드에서 숨김파일(`.env*`)을 건너뛴다.**
> 에러 없이 0을 반환해 "정의 없음"으로 읽혔다(§9 · catch BB 유형).
> 재검증은 **파일별 직접 grep**(`grep -nF "CHROMA" .env` 등)으로 했다. 아래 표는 정정본이다.
> 양성 대조: 같은 파일에 `TOPIC` 7건이 잡히므로 검색 자체는 작동한다.

| 키 | CFG 선언 | `.env`(L1) | `.env.<provider>`(L2) | `topics/*.env`(L3) |
|---|---|---|---|---|
| `CHROMA_NAMESPACE` | ✅ `core/config.py:250`, `:484` | `:126` **주석** | 🔴 `.env.openai:56`·`.env.anthropic:50` **활성** / `.env.vertex:48` 주석 | `topics/experiential-marketing-media.env:7` |
| `CHROMA_NAMESPACE_WEB` | ✅ `:251`, `:485` | `:127` **주석** | 🔴 `openai:57`·`anthropic:51` **활성** / `vertex:49` 주석 | 같은 파일 `:8` |
| `CHROMA_NAMESPACE_LOCAL` | ✅ `:253`, `:486` | `:128` **주석** | 🔴 `openai:58`·`anthropic:52` **활성** / `vertex:50` 주석 | 같은 파일 `:9` |
| `TOPIC_SLUG` | ✅ `:300`, `:540` | 🔴 `:53` **활성** = `academic-trademark-similarity-consumer` | 0건 | 두 토픽 파일 모두 정의 |
| **`CHROMA_DIR`** | 🔴 **0건 (미선언)** | 🔴 `:125` **활성** = `data/chroma_store` | 0건 | 0건 |

- L1/L2 존재 파일: `.env`(224행) · `.env.openai`(58) · `.env.vertex`(50) · `.env.anthropic`(52) · `.env.openalex`(1) · `.env.semanticscholar`(4) + `.bak` 2 · `.example` 2.
  `CHROMA` 출현 = `.env` 10 · `openai` 3 · `vertex` 3 · `anthropic` 3 · 나머지 0.
- ⚠️ **`.env.openai:56~58`이 L2에서 venfobel NS로 덮는다**는 사실은 이미 `ad/GUARDRAILS.md:43`에
  `NS 격리 3키 필수 — .env.openai:56-58이 venfobel NS로 덮으므로 L3에서 탈환`으로 박제돼 있었다.
  최초 작성분의 "0건"은 이 기존 박제와도 충돌했다.
- L3 확인:
  ```
  topics/academic-trademark-similarity-consumer.env:9:TOPIC_SLUG=academic-trademark-similarity-consumer
  topics/experiential-marketing-media.env:3:TOPIC_SLUG=experiential-marketing-media
  topics/experiential-marketing-media.env:7:CHROMA_NAMESPACE=experiential-marketing-media
  topics/experiential-marketing-media.env:8:CHROMA_NAMESPACE_WEB=experiential-marketing-media-web
  topics/experiential-marketing-media.env:9:CHROMA_NAMESPACE_LOCAL=experiential-marketing-media-local
  ```
  🔴 **논문 토픽 파일에는 `CHROMA_*` 3키가 없다.** `TOPIC_SLUG` 1건만.

**→ 결정 층 = L1·L2·L3 3층 전부에 정의가 존재한다** (정정 전 기술 "L3 단독"은 폐기).
`CHROMA_NAMESPACE` 3키는 L2(`.env.openai`·`.env.anthropic`)가 **활성으로 venfobel NS를 넣고**,
L3 topic preset이 `override=True`로 다시 덮는다(STANDARDS §1.2). 최종 승자는 L3.

⚠️ **`CHROMA_DIR` 경로(2순위)는 CFG 경유로 도달 불가 — 정정 후 오히려 강해진다.**
`.env:125`에 `CHROMA_DIR=data/chroma_store`가 **주석이 아니라 활성 상태로 존재**하는데도
아래 이유로 **읽히지 않는다.** 값이 없어서 무시되는 게 아니라, 값이 있는데 무시된다.
`_cfg_str`(`utils.py:121~127`)은 `getattr(CFG, key)`만 읽고 `os.environ`을 보지 않는다:

```python
if "_cfg_str" not in globals():
    def _cfg_str(key: str, default: str = "") -> str:
        try:
            v = getattr(CFG, key)
            return (str(v).strip() if v is not None else default)
        except Exception:
            return default
```

`Config`는 `@dataclass(frozen=False)`(`core/config.py:228~229`)이고 클래스 레벨 `__getattr__`이 없다
(`:743 def __getattr__`은 **모듈 레벨** 하위호환 훅으로, CFG 인스턴스 직접 접근에는 미적용).
`CHROMA_DIR` 필드 선언 0건 → `getattr` AttributeError → `except` → `default=""` 반환.

부수 관측: `core/topic.py:142`가 런타임에 `os.environ["CHROMA_DIR"] = chroma_dir`를 세팅하지만,
위 경로상 `_cfg_str`이 읽지 않는다. `utils.py:160 refresh_runtime_config()`는 정의만 있고
**호출부 0건**(`grep -rn "refresh_runtime_config(" --include="*.py"` → 정의 외 0건).
CFG 재빌드 경로는 **미확인**.

---

## 확인 5 — 색인 실물 (`sqlite3 -readonly`)

### 5-a. persist 디렉토리 목록

```
$ ls -la writer_project/data/chroma_store
drwxr-xr-x  _empty_ns_20260802.bak        (8월  1 15:36)
-rw-r--r--  _stray_20260731.sqlite3.bak   188,416 B
-rw-r--r--  _stray_20260802.sqlite3.bak   188,416 B
drwxr-xr-x  base                          (7월 26 23:04)
drwxr-xr-x  experiential-marketing-media        (8월  5 20:24)
drwxr-xr-x  experiential-marketing-media-local  (8월  6 21:04)
drwxr-xr-x  experiential-marketing-media-web    (8월  6 21:04)
drwxr-xr-x  venfobel-vitamin                    (6월  1 18:43)
drwxr-xr-x  venfobel-vitamin-local              (6월  1 18:43)
drwxr-xr-x  venfobel-vitamin-web                (6월  1 18:43)
```

- `base/` = **빈 디렉토리** (`ls -la base/` → `.`/`..`만).
- 🔴 **`academic-trademark-similarity-consumer*` 디렉토리 없음** — `ls -d *trademark*` → `no matches found`.

### 5-b. 컬렉션명 · 건수 · dim

계산 방식(§9 — 지표가 무엇을 세는지 먼저):
```sql
SELECT c.name, c.dimension,
       (SELECT COUNT(*) FROM embeddings e
        JOIN segments s ON e.segment_id = s.id
        WHERE s.collection = c.id) AS n
FROM collections c;
```
`dimension`은 `collections` 테이블 컬럼(`.schema collections` 확인). 건수는 `embeddings`를 `segments.collection`으로 귀속시켜 센 값.

| persist 디렉토리 | 컬렉션명 | dim | 건수 |
|---|---|---|---|
| `experiential-marketing-media` | `experiential-marketing-media` | `NULL` | **0** |
| `experiential-marketing-media-local` | `experiential-marketing-media-local` | **3072** | **302** |
| `experiential-marketing-media-web` | `experiential-marketing-media-web` | **3072** | **416** |
| `venfobel-vitamin` | `venfobel-vitamin` | `NULL` | **0** |
| `venfobel-vitamin-local` | `venfobel-vitamin-local` | **768** | **810** |
| `venfobel-vitamin-web` | `venfobel-vitamin-web` | **768** | **47** |
| `_empty_ns_20260802.bak` | `experiential-marketing-media` | `NULL` | **0** |
| `_stray_20260731.sqlite3.bak` | (collections 0행) | — | embeddings **0** |
| `_stray_20260802.sqlite3.bak` | (collections 0행) | — | embeddings **0** |

**교차검증 — 조인이 행을 흘리지 않는지 확인** (`SELECT COUNT(*) FROM embeddings`):

| 파일 | 조인 결과 | 원시 총계 | 일치 |
|---|---|---|---|
| `experiential-marketing-media-local` | 302 | 302 | ✅ |
| `experiential-marketing-media-web` | 416 | 416 | ✅ |
| `venfobel-vitamin-local` | 810 | 810 | ✅ |
| `venfobel-vitamin-web` | 47 | 47 | ✅ |
| `experiential-marketing-media` | 0 | 0 | ✅ |
| `venfobel-vitamin` | 0 | 0 | ✅ |

컬렉션당 segment는 2행(`VECTOR` + `METADATA`)이지만 `embeddings.segment_id`가 한쪽만 가리켜 중복 계상 없음:
```
$ sqlite3 -readonly experiential-marketing-media-web/chroma.sqlite3 "SELECT s.id, s.scope, s.collection FROM segments s;"
7aaa08ab-...|VECTOR|07633a9c-...
cf5a24b9-...|METADATA|07633a9c-...
```

- 컬렉션은 **파일당 1개**. `-web`/`-local` 접미 컬렉션은 각자 별도 sqlite 파일에 있다.
- 302 / 416 은 CLAUDE.md §8.2 기재값(local 302 · web 416)과 일치.
- ⚠️ `_stray_*.bak` 2건은 파일 크기가 188,416 B로 서로 같으나, **동일성 판정은 하지 않았다**(§9 — 크기 일치는 근거가 아니다). 확인한 것은 두 파일 모두 `collections` 0행 · `embeddings` 0건이라는 점뿐.

---

## 확인 6 — 논문 트랙의 색인 재사용 / 재수집

### 6-a. 드라이버의 색인 로드·재구축 분기

`measure_paper.py:433~538 main()` 전량 육안.

| 라인 | 내용 |
|---|---|
| `:435~449` | argparse — `--topic --sections --output-dir --warmup --measure --sleep --timeout --dry-run`. **색인 관련 인자 0개** |
| `:468~470` | `--dry-run` → Stage 2에서 exit |
| `:474~489` | `for run_i in range(warmup + measure): r = _run_one_paper(...)` — **분기 없이 매 run 직접 호출** |
| `:502~535` | 결과 JSON/덤프 저장 |

**색인 로드 분기: 없음. 색인 재구축 분기: 없음.**
`grep -rn "chroma\|Chroma\|retrieve\|ingest\|vector_search" scripts/§paper-writer-1/ --include="*.py"` → **0건** (확인 3-c).

### 6-b. 매 run 실제 동작

| 라인 | 동작 |
|---|---|
| `measure_paper.py:254` | run마다 `paper_section_fetch(topic, section)` 재호출 (섹션 수만큼) |
| `web_search.py:2024~2026` | run마다 `openalex_search` / `semantic_scholar_search` / `vertex_web_search` **외부 API 재호출** |
| `web_search.py:2007` → `:1809 _load_and_hydrate_seeds` | seed JSON 파일 로드(`:1836 path.read_text`) 후 **`openalex_search`로 매번 재hydrate**(`:1819` docstring) |

**응답 캐시 여부**: `grep -n "cache\|Cache\|\.json\b\|read_text\|pickle" tools/web_rag/openalex.py tools/web_rag/semantic_scholar.py` → **0건**.

### 6-c. 정리

| 질문 | 실측 |
|---|---|
| 기존 색인을 재사용하는가 | **Chroma 색인을 읽지도 쓰지도 않는다** (확인 3-c, 6-a) |
| 매번 재수집하는가 | **매 run 외부 API 재호출** (6-b). 백엔드 응답 캐시 0건 |
| 논문 토픽 색인 실물 | **존재하지 않음** — `chroma_store`에 `academic-trademark-*` 디렉토리 0건 (5-a) |

---

## 미확인 항목

| # | 항목 | 사유 |
|---|---|---|
| 1 | `CFG` 런타임 재빌드 경로 | `refresh_runtime_config()` 호출부 0건 확인까지만. `core/topic.py:142`의 `os.environ["CHROMA_DIR"]`이 어떤 경로로든 반영되는지는 **정적 추적 미완** |
| 2 | `tools/web_rag/search.py:95` 동적 `getattr` 조회의 실제 해석 대상 | 문자열 3순위 조회. 런타임 실행 없이는 어느 이름이 잡히는지 미확정 |
| 3 | `_stray_*.sqlite3.bak` 2건의 내용 동일성 | 크기만 같음. 해시 대조 미실시 |
| 4 | `_empty_ns_20260802.bak` / `base/` 의 생성 경위 | 파일 시스템 관측만. git 이력 미추적 |
| 5 | `venfobel-vitamin*` 3디렉토리(dim 768)의 현행 사용처 | 이번 정찰 범위 밖 |
| 6 | `ingest_docs.py`(30,393 B)의 파싱 단계 내용 | 이번 정찰은 `ingest_vector.py` 공유 범위 한정. 크롬 제거 위치 후보로서의 검토는 **대상 아님**(지시) |

---

## 실행한 명령 (재현용)

```bash
# 세션 개시 재검증
git log --oneline -8 && git diff --stat && git status --short

# 확인 1
find . -name "ingest_vector*.py" -not -path "*/.venv*"
wc -l tools/web_rag/ingest_vector.py
grep -n "__main__\|argparse\|ArgumentParser\|sys.argv" tools/web_rag/ingest_vector.py

# 확인 2 (양쪽)
git -c core.quotePath=false grep -n "ingest_vector" -- '*.py'
grep -rn --include="*.py" "ingest_vector" . | grep -v "/\.venv" | grep -v node_modules
grep -rnE --include="*.py" "documents_to_chroma|add_documents_to_chroma|add_web_pages_json_to_chroma|seed_web_namespace|split_documents|clear_vector_store|ensure_vector_store_cleared_once|has_any_docs" .
awk -v tgt=1057 'NR<=tgt && /^(async )?def /{n=NR;l=$0} NR==tgt{print n": "l}' agent/web_search.py

# 확인 3
grep -rn "chroma\|Chroma\|retrieve\|documents_to_chroma\|ingest\|vector_search" \
  "scripts/§academic-1/" "scripts/§academic-4/" "scripts/§paper-writer-1/" --include="*.py"
grep -n "chroma\|Chroma\|retrieve\|ingest\|vector" agent/paper_section_writer.py

# 확인 4
git -c core.quotePath=false grep -n "CHROMA_NAMESPACE\|CHROMA_DIR\|TOPIC_SLUG" -- "writer_project/core/config.py"
# 🔴 아래 재귀형은 숨김파일을 건너뛰어 거짓 0을 낸다 — 쓰지 말 것
#   grep -rn "CHROMA" --include=".env*" .
# 정정된 형태 = 파일별 직접 grep
for f in .env .env.vertex .env.openai .env.anthropic; do grep -nF "CHROMA" "$f"; done
grep -n "CHROMA\|TOPIC_SLUG" topics/experiential-marketing-media.env topics/academic-trademark-similarity-consumer.env

# 확인 5 (읽기 전용)
sqlite3 -readonly <f> ".tables"
sqlite3 -readonly <f> ".schema collections"
sqlite3 -readonly <f> "SELECT c.name, c.dimension, (SELECT COUNT(*) FROM embeddings e JOIN segments s ON e.segment_id=s.id WHERE s.collection=c.id) FROM collections c;"
sqlite3 -readonly <f> "SELECT COUNT(*) FROM embeddings;"

# 확인 6
grep -n "cache\|Cache\|\.json\b\|read_text\|pickle" tools/web_rag/openalex.py tools/web_rag/semantic_scholar.py
```
