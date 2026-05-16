# §14-8-A B-pre-2 — graph 모듈 top-level ENV 사용 raw read

**read 시점:** 2026-05-16
**git HEAD:** 77c24ad

---

## § 1. graph.py 자체 (직접 module-level)

| 항목 | 결과 |
|---|---|
| 파일 | `writer_project/graph.py` (190 lines) |
| `os.environ` 호출 | **0건** |
| `os.getenv` 호출 | **0건** |
| `load_dotenv` 호출 | **0건** |
| `import os` | **無** (직접 import 없음) |

→ **graph.py 자체에는 ENV 접근 없음**. 분기는 transitive import 의 module-level 부작용으로 발생해야 함.

### graph.py module-level 실행 trigger 박제

| line | 행위 | side-effect 가능성 |
|---|---|---|
| L12 | `import core.config as config` | core.config 의 module-level 실행 — **CFG dataclass 인스턴스화 시 .env 로드 가능** |
| L26-34 | `_get_cfg_attr(...)` 9회 호출 (feature toggle 평가) | `config.CFG` attribute lookup — CFG 가 이미 module-level 에서 instantiate 됐다면 추가 부작용 0 |
| L37-45 | `agent.{supervisor,communicator,content_strategist,vector_search,web_search,chapter_writer,section_writer,research_planner,research_synthesizer}` 9개 import | 각 agent module 의 top-level 부작용 (특히 web_search/vector_search) |
| L48-54 | `from core.routers import ...` | router module top-level |

## § 2. core.config (graph.py L12 import) — top-level 부작용

### 2-1. import + 함수 정의

| line | 내용 |
|---|---|
| L5 | `import os` |
| L13 | `from dotenv import load_dotenv, find_dotenv` (선택적) |
| L19 | `from core.models import AgentName` |
| L102-104 | `# ── dotenv 1회 로드 ──` + `_dotenv_loaded = False` (**module-level 전역**) |
| L153-158 | `def _load_dotenv_once()` (함수 정의, 호출은 아래에서) |

### 2-2. module-level os.getenv 호출 — **추가 확인 필요**

grep 결과:
- L113, L117, L137, L140 — `_apply_provider_overlay()` 류 함수 내부일 가능성 高 (들여쓰기 박제 추가 read 必)
- L26, L36, L198, L204 — helper 함수 내부 (들여쓰기 박제 추가 read 必)
- **L457-460 `# .env → os.environ 주입 (최초 1회) / _load_dotenv_once()`** — **위치가 함수 정의 들여쓰기 안인지 module-level 인지 확정 필요** (★)
- L657-660 `load_dotenv(find_dotenv(usecwd=True), override=True)` — 함수 내부일 가능성 高
- L676-698 — helper 함수 내부

**미해결 의문**: `CFG` 가 module-level instantiate 되는지 (즉 graph.py import 만으로 .env 가 즉시 로드되는지) 확정 미박제. H1 trace 의 STAGE 마커 사이 elapsed 차이로 간접 확인 가능.

## § 3. agent.web_search (graph.py L41 import) — top-level transitive

### 3-1. top-level import (L1-50)

| line | 내용 | side-effect 가능성 |
|---|---|---|
| L9 | `import os, re, time, json, glob, shutil, hashlib` | 무 |
| L25 | `import core.config as config` | (이미 §2 분석) |
| L27-28 | `from settings_gatekeep import ...` | settings_gatekeep top-level |
| **L29** | **`from tools.web_rag.search import web_search`** | **search.py top-level — § 4 참조** |
| **L30** | **`from tools.web_rag.vertex_search import vertex_web_search`** | **vertex_search.py top-level — § 5 참조** |
| **L43-47** | **`from tools.web_rag.ingest import (...)`** | **ingest.py top-level — § 6 참조** |
| L49 | `from tools.local_rag import ingest_local_files` | local_rag top-level |
| L50 | `from core.llm import get_llm` | core.llm top-level |

## § 4. tools.web_rag.search (web_search.py L29 transitive import)

### 4-1. top-level os.getenv — **★ module-level scope 확정**

```python
L14: import requests
L21:     os.getenv("GOOGLE_CSE_BASE_URL", "https://customsearch.googleapis.com/customsearch/v1")
```

L21 의 정확한 들여쓰기는 미확정 (raw read 추가 필요 — 변수 할당 right-hand-side 인지 함수 default 인지).

| line | os.getenv 호출 | scope |
|---|---|---|
| L21 | `GOOGLE_CSE_BASE_URL` | **★ module-level 가능성** |
| L41 | `import core.config as config` | top-level import |
| L42 | `from core.config import CFG, reload_config` | **★ CFG 가 module-level instantiate 라면 .env 즉시 로드** |
| L229, L243, L595~ | helper / 함수 내부 | (그 외 다수, 모두 함수 내부 추정) |

### 4-2. 핵심 (★)

- **L42 `from core.config import CFG`** = CFG 인스턴스를 가져옴
- 만약 CFG 가 module-level 에서 instantiate 됐다면, **search.py import = CFG 즉시 노출 = .env 로드 trigger**
- standalone 과 driver 모두 동일하게 이 path 를 거치므로 **이 자체로는 분기 원인 아님**. 단, .env 로드 시 **driver 가 env 에 미리 set 한 값과 .env 파일 값의 우선순위** 가 IMPORT-time 분기 후보 (예: `load_dotenv(override=True)` vs `override=False`)

## § 5. tools.web_rag.vertex_search (web_search.py L30 transitive)

### 5-1. top-level

| line | 내용 | scope |
|---|---|---|
| L4 | `import os` | top-level |
| L7 | `import requests` | top-level |
| L52 | `project = os.getenv("GCP_PROJECT_ID")` | 함수 내부 추정 (line 52 + 들여쓰기) |
| L53 | `location = os.getenv("GCP_REGION", "us-central1")` | 함수 내부 추정 |
| L112 | `model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")` | 함수 내부 추정 |

→ **vertex_search.py top-level 에는 vertex SDK init 코드 없음** (예: `aiplatform.init()`, `vertexai.init()` 부재). IMPORT-time vertex 호출 부작용 0.

## § 6. tools.web_rag.ingest (web_search.py L43 transitive)

### 6-1. top-level (L1-80)

| line | 내용 | scope |
|---|---|---|
| L13 | `import os, io, json, time` | top-level |
| L18 | `import requests` | top-level |
| L29 | `from .ingest_net import (...)` | top-level |
| L42 | `from .ingest_config import (...)` | top-level — ingest_config 의 top-level 확인 필요 (별 cycle) |
| L231 | `from .utils import (...)` | top-level |
| L695 | `from .ingest_docs import ...` | top-level (line 695 이지만 코드 흐름상 top-level) |
| L702 | `from .ingest_vector import (...)` | top-level — **chroma client 호출 가능성 高** |

### 6-2. chroma 관련 (★)

- grep `chromadb`, `PersistentClient` → ingest.py L1-80 head 에는 **0건**
- **`.ingest_vector`** module (ingest.py L702) 가 chroma client 의 module-level init 을 할 가능성 — H1 trace 결과로 간접 확인

## § 7. (가-η) IMPORT 거동 분기 root cause 추가 후보 (§14-8-A raw read A 의 4건 + 본 raw read 추가)

기존 (raw_read_run_single.md § 6):
1. env 구성 차이 (POLLUTION pop + 명시 set vs standalone shell env)
2. stdout/stderr redirect 차이 (TTY vs binary file handle)
3. timeout 컨텍스트 차이 (300s vs 無)
4. working directory 차이 (driver cwd 상속)

본 raw read 추가:
5. **transitive import 부작용 — `tools.web_rag.search` L42 `from core.config import CFG`** — CFG instantiate 시 `.env` 로드. driver 가 `os.environ.copy()` 후 명시 set 한 var 와 `.env` 파일 var 의 override 관계
6. **`.ingest_vector` (ingest.py L702)** — chroma client module-level init 가능성, driver-side 에서 다른 chroma persist dir 로 trigger 시 hang 후보

→ H1 trace 의 STAGE 마커 사이 elapsed 차이로 (5), (6) 진단 가능.

## § 8. raw 확인 미완 항목 (별 cycle 또는 trace 결과 후)

- `core.config` 의 CFG instantiate 가 module-level 인지 함수 내부인지 확정 (line 별 들여쓰기 박제)
- `tools.web_rag.search` L21 `os.getenv("GOOGLE_CSE_BASE_URL", ...)` scope 확정
- `tools.web_rag.ingest_vector` top-level 의 chroma init 여부 박제
- `agent.vector_search` top-level 의 chroma client 호출 여부 박제
- `core.llm` top-level 의 vertex / openai client init 여부 박제

위 항목들은 H1 stage trace 의 STAGE 사이 elapsed 차이로 간접 확정 가능 — trace 결과 후 raw 확정.
