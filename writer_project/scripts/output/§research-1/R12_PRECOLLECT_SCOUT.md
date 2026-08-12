# R12 — S7 수집 착수 전 설계 확정 정찰 ($0 · 읽기 전용)

- **실행일 2026-08-12** · 채널 = 기술 정밀 · 실비용 **$0**
- 계보 `CC_S7_20260812_precollect_scout.md`(지시서) ← `R2c_NORTH_STAR.md §6-c`(미결 4건) + `R11_QUERY_FREEZE.md §10`(게이트 8항)
- 성격 = **정찰. 수집·색인·API·LLM 호출 전부 0**
- 🔴 **판정·권고 없음.** 값만 낸다. 다만 *값이 판정을 강제하는 경우*는 사실로 기술한다(지시서 §7 단서)

---

## 🔴 0. 먼저 — STOP 조건 발동 2건

| # | 조건 | 결과 |
|---|---|---|
| **1** | 3-a 가 기존 색인 118 과 **동일 NS** | 🔴 **발동.** 동일 NS 확정 (§4-a) |
| 2 | 3-b 진입점 부재 | **미발동** — 진입점 존재 (§4-b). 단 **NS 인자가 무시**되는 제약 있음 |
| 3 | 1-d 점화 증거 로그 특정 불가 | **미발동** — 특정 완료 (§2-d) |
| 4 | `Q_FROZEN` 해시 불일치 | **미발동** — 일치 |
| 5 | 게이트 8항 플레이스홀더 1건 이상 | **미발동** — 0건(양성 대조 7/7) |
| 6 | 실비용 $0 초과 | **미발동** — $0 |
| 7 | 인용 행번호 5건 이상 어긋남 | **미발동** — **3건** (§9) |

### 0-a. 🔴 지시서가 예상하지 못한 발견 3건 — 값이 판정을 강제한다

지시서의 미결 목록에 없었으나, **수집 설계를 바꿔야 성립하는 사실**이 3건 나왔다.

| # | 발견 | 강제되는 결과 |
|---|---|---|
| **A** | `--gatekeep` 은 **작동하지 않는다.** `app.py:2270` 이 `os.environ` 에 쓴 값을 `app.py:2282 → config.py:681 load_dotenv(override=True)` 가 **되돌린다.** `GATE_KEEP_SOURCES` 는 `_PROTECTED_ENV_KEYS` **5키에 없다** | 미결 1 의 선택지 2개 중 **1개가 실물로 소멸.** `.env` 만이 유효 |
| **B** | 우리 17개를 주입해도 **LLM 생성 쿼리가 추가로 집행된다.** `web_search.py:1226` 의 LLM 호출은 **무조건**이고 주입 여부와 무관하다. 실효 상한 `MAX_SEARCH_QUERIES_PER_ROUND = 6` | 억제하지 않으면 코퍼스가 **17쿼리 산물이 아니게 된다** → `R11 §8` 문장이 거짓이 됨 |
| **C** | Tavily 는 **쿼리당 최대 5건**(`search.py:607 min(num,5)`)이고 `include_raw_content=False` | 17쿼리 × 5 = **최대 85 URL**. raw_content 는 별도 자체 GET(`_enrich_raw_content`)이 채운다 |

---

## 1. 실행 환경 캡처 (STANDARDS §7 / catch CO)

```
cwd     /Users/ohsungsu/dev/bell-agent/bell-agent-backend/writer_project
venv    ../.venv_openai/bin/python
python  3.11.6
bs4     4.14.2
lxml    6.0.2
libxml2 2.14.6   (LIBXML_VERSION == LIBXML_COMPILED_VERSION)
libxslt 1.1.43
```

catch AR 재검증 — HEAD **`03bbde70`**, 지시서 §0 기재(`03bbde70`)와 **일치**. 워킹트리 미커밋분 = 논문 트랙 `scripts/§paper-writer-1/measure_paper.py` 1건(이번 차수 무접촉).

> ⚠️ 검색 cwd 는 **전부 `writer_project/`** 다. `.env*` 등 ignore 대상은 **파일 지목 + `command grep`** 으로 확인했다(`catch CG`).

---

## 2. 미결 1 — `GATE_KEEP_SOURCES` 점화 수단

### 2-a. 우선순위 — 🔴 `--gatekeep` 은 무효다 (실행 검증)

**사슬 실측**

| 단계 | 파일:행 | 동작 |
|---|---|---|
| 1 | `app.py:2269-2270` | `--gatekeep` → `os.environ["GATE_KEEP_SOURCES"]="1"` |
| 2 | `app.py:2282` | `config.reload_config()` |
| 3 | `core/config.py:681` | `load_dotenv(find_dotenv(usecwd=True), override=True)` → **`.env:208 GATE_KEEP_SOURCES=0` 이 os.environ 을 되돌림** |
| 4 | `core/config.py:679`·`685-687` | 복원 루프는 `_PROTECTED_ENV_KEYS` 만 되살림 — **이 키는 미포함** |
| 5 | `core/config.py:700` `_build_config()` | `_env_flag(...)` 가 `"0"` 을 읽음 → `CFG.GATE_KEEP_SOURCES=False` |
| 6 | `core/config.py:717 truthy()` | `hasattr(CFG,name)` True → **CFG 값 우선.** ENV 는 보지 않음 |
| 7 | `settings_gatekeep.py:223` | `gatekeep_enabled()` → False |
| 8 | `web_search.py:431-433` | `GATE_KEEP_SOURCES = False` 로 확정 |

```
_PROTECTED_ENV_KEYS = ('LLM_PROVIDER','LLM_MODEL','TOPIC_SLUG','SKIP_VERTEX_SEARCH','MIRROR_STATE_TO_ENV')
                       ← GATE_KEEP_SOURCES 없음 (core/config.py:661-667)
```

**실행 검증** (in-process, 파일 무변경)

```
== app.py:2270 모사 — --gatekeep ==
직후(reload 전)     os.environ='1'  CFG=False  truthy=False  gatekeep_enabled=False
reload_config() 후  os.environ='0'  CFG=False  truthy=False  gatekeep_enabled=False
                              ↑ 되돌아감
```

**양성 대조 2종 — 기전 자체는 정상이다**

| 대조 | 결과 |
|---|---|
| 보호키 `TOPIC_SLUG` 를 같은 reload 에 통과 | **생존** (`experiential-marketing-media` 유지) → 복원 루프는 작동한다. 문제는 **이 키가 목록에 없다는 것** |
| `.env` 경로 모사 (`_build_config()` 직결, env `'0'`/`'1'` 왕복) | `'0'`→False / **`'1'`→True** → **`.env` 경로는 정상 점화된다** |

> 🔴 **따라서 "둘 중 하나를 고른다"는 전제가 성립하지 않는다.** 유효한 수단은 `.env` **1개**다.
> ⚠️ 대칭으로 **`--no-gatekeep` 도 무효**다(`.env` 가 1이면 1로 되돌아옴). 플래그는 양방향 모두 죽어 있다.

### 2-b. 적용 범위

- `--gatekeep` 은 `os.environ` 에 쓰므로 **프로세스 전역**이 의도였으나, 위 사유로 **도달하지 못한다.**
- 우리 진입점 `web_search_agent` 는 `:425` 에서 CFG 를 읽고 `:431` 에서 `gatekeep_enabled()` 로 **덮어쓴다.** 둘 다 같은 `.env` 값에 수렴한다.
- 우리가 `app.py` 를 경유하지 않고 `web_search_agent(state)` 를 직접 호출하면 `app.py:2269-2272` 자체를 안 탄다 → **`.env` 값이 그대로 유일 소스**가 된다.

### 2-c. L3 프리셋 간섭 — **없음**

- `topics/experiential-marketing-media.env` 에 `GATE_KEEP_SOURCES` **0건**(파일 지목 `command grep`).
- `_apply_topic_preset`(`config.py:130-150`)은 `load_dotenv(preset_path, override=True)` 뿐 — **파일에 없는 키는 손대지 않는다.** 따라서 `.env:208` 이 그대로 실효.
- 로드 순서 실측(`config.py:161-169`): `.env`(override=**False**) → `.env.<provider>`(override=True) → `topics/<slug>.env`(override=True). **프리셋이 최후 — preset wins 확인.**

### 2-d. 🔴 점화 증거 로그 — 특정 완료

| 로그 | 위치 | 형태 |
|---|---|---|
| **정본(노드)** | `web_search.py:458` | `[GATEKEEP] enabled; allowed=%s (n=%d)` |
| 꺼짐(노드) | `web_search.py:460` | `[GATEKEEP] Disabled. (GATE_KEEP_SOURCES=0)` |
| 부팅(app) | `app.py:2323` | `[GATEKEEP] enabled; allowed=%s` — **`n=` 없음** |
| 필터 실동작 | `web_search.py:556`·`560-561` | `[GATEKEEP] filtered: kept=%d blocked=%d file=%s` |

🔴 **`probe_A2/B1.log` 의 `enabled(n=79)` 는 `web_search.py:458` 산출이다.** `n=` 접미가 app 판(`:2323`)에는 없으므로 **두 로그는 구분 가능**하다.

**수치 재현 성공** — 현재 설정으로 `get_allowed_domains()` = **79**. `_BASE_ALLOWED_DOMAINS` 17 ∪ `.env:214` 78 = **79**(중복 16). 과거 로그의 79 와 **일치** → 그때와 허용목록이 같다는 방증.

> ⚠️ **가장 강한 증거는 `:560` 이다.** `:458` 은 *"켜졌다"* 만 말하고, `:560 kept=/blocked=` 는 **필터가 실제로 파일을 갈랐음**을 말한다. `catch CU` 가 요구한 "실동작"에 대응하는 것은 후자다.
> ⚠️ 단 `blocked=0` 이면 `:559 if blocked:` 때문에 **`:560` 이 안 찍힌다.** `kept>0 & blocked=0` 인 라운드는 무로그다 → **`*_filtered.json` 파일 생성 자체**를 병행 증거로 쓴다.

### 2-e. 부작용 — `*_filtered.json` 생성 외 2건

| 위치 | 동작 |
|---|---|
| `web_search.py:533-534` | off 면 원본 경로 그대로 반환 (= filtered 미생성) |
| `web_search.py:1103-1107` | **on 이면 preview docs 도 `_allowed()` 로 재차 필터** |
| — | 저장 경로·색인 대상 NS 변경 **없음**. 색인은 `filtered_json` 을 받으므로 **간접적으로 색인 내용이 바뀐다** |

⚠️ **부수 관측** — `ALLOW_SUBDOMAINS` 실효값 **True**. `blog.naver.com` 이 `naver.com` 항목으로 통과한다(§5-c 실측과 정합).

---

## 3. 미결 2 — `references` 기적재분 배제

### 3-a. 배제 판정 로직 실물 — **비대칭이다**

```
web_search.py:301-307   references = state.get("references") or {"queries": [], "docs": []}
                        _existing_qs = { (q or "").strip().lower() for q in references["queries"] ... }
                                        ↑ strip + lower 뿐

web_search.py:1155      nq = re.sub(r"\s+", " ", _normalize_planner_q(q))    ← 불릿·번호·따옴표 제거 + 공백 축약
web_search.py:1158-1159 lk = nq.lower();  if lk in seen_norm or lk in _existing_qs: continue
```

🔴 **저장 측과 비교 측의 정규화 강도가 다르다.**
- 들어오는 쿼리 = `_normalize_planner_q` **경유**(불릿/번호/따옴표 제거) + 연속공백 1칸 축약 + lower
- 기적재 쿼리 = `strip().lower()` **만**

→ 완전일치가 아니라 **"정규화된 신규" vs "생짜 소문자 기존"** 비교다. 기존 항목에 불릿·이중공백이 있으면 **매칭 실패(=배제 안 됨)**, 없으면 매칭. 대소문자·양끝 공백은 양쪽 다 흡수된다.

⚠️ 단 `:1182`·`:1219`·`:1252` 등 **실행 성공 시 되먹임 등록은 정규화된 값**(`q.lower()`, `lk`)으로 들어간다 → 같은 실행 내 2회차부터는 대칭이 회복된다.

### 3-b. `references` 가 채워지는 곳

| 위치 | 동작 |
|---|---|
| `web_search.py:301-302` | `state.get("references")` 를 **상속**. 없으면 `{"queries": [], "docs": []}` |
| `web_search.py:1425`·`1449` | 실행 말미에 `_s["references"]` 로 **되쓰기** |

**영속 저장소 없음** — `*state*.json` 류 파일 **0건**(§10 양성 대조 병기). `references` 는 **in-memory State 전용**이다.

> 🔴 **따라서 우리가 새 state 를 만들면 `references` 는 비어 있고, 배제는 0건이다.**

### 3-c. 동결 17줄 중 배제 대상 — **0건 (조건부)**

- 우리가 `web_search_agent({...})` 에 state 를 **직접 구성**하는 이상(`R11 §2-a` 호출형), `references` 키를 넣지 않으면 `_existing_qs` = **공집합** → 17줄 전량 생존.
- **확인 경로** = 우리가 만드는 dict 그 자체(외부 조회 불요). 서버 경유 시에는 `/api/state`(`app.py:1231`) 이나, 이번 설계는 서버를 안 탄다.
- ⚠️ 단 **`seen_norm` 에 의한 자체 중복 제거는 별개로 작동**한다. 17줄이 서로 중복이 아님은 `R11 §3`·§7-8 에서 확인된 바(17 distinct).

### 3-d. 집행 쿼리 수 로깅 자리 — **있음 (2곳, 단 한계 있음)**

| 위치 | 내용 |
|---|---|
| `web_search.py:1176` | `[WEB SEARCH AGENT] planner queries: %s` — **목록 전량 출력** |
| `web_search.py:1184`·**`:1191`(중복 출력)** | `[WEB SEARCH AGENT] planner queries executed: %s/%s` — `ran_planner / len(planner_qs)` |

🔴 **분모가 17 이 아니라 "배제 후 잔량"이다.** 5개가 배제되면 로그는 `12/12` 로 찍히고 **배제 사실이 보이지 않는다.**
→ 17 검증은 **`:1176` 의 목록을 주입한 17줄과 대조**해야 성립한다. 개수 로그(`:1184`)만으로는 불가.

⚠️ 추가 감산 경로 — `:1178 _cap_reached()` 가 참이면 잔여 쿼리를 **건너뛰고 `:1179` 로그**를 남긴다(§5-#2 · §4-c 참조).

---

## 4. 🔴 미결 3 — 수집 → 색인 자동 연결 (최대 미결)

### 4-a. 🔴 자동 색인이 쓰는 NS — **기존 색인 118 과 동일하다 (STOP 1 발동)**

**해석 사슬**

```
web_search.py:227-232   topic_slug = CFG.TOPIC_SLUG = "experiential-marketing-media"
                        env_ns     = CFG.CHROMA_NAMESPACE = "experiential-marketing-media"
                        ns         = env_ns or topic_slug  →  "experiential-marketing-media"
                        persist_dir= _wr_resolve_persist_dir(ns, _default_chroma_dir(ns))

web_search.py:1057-1062 add_web_pages_json_to_chroma(json_file=filtered_json, namespace=ns,
                                                     clear=False, persist_directory=persist_dir)

ingest_vector.py:1457-1461  ns_web_env = CFG.CHROMA_NAMESPACE_WEB = "experiential-marketing-media-web"
                            ns_loc_env = CFG.CHROMA_NAMESPACE_LOCAL = "...-local"
                            split_mode = True
                            ns_probe   = ns_web_env        ← web json 은 web ns 로 강제
ingest_vector.py:930        ns_eff, _ = _resolve_ns_for_docs(ns_base, is_web_flag)   ← 쓰기도 동일 강제
```

**기존 색인 실측** (`sqlite3 -readonly`, STANDARDS §3)

| 컬렉션 | 청크 | distinct `source` |
|---|---|---|
| `experiential-marketing-media-web` | **416** | 🔴 **118** |
| `experiential-marketing-media-local` | 302 | — |
| `experiential-marketing-media` (base) | 0 | — |

→ **자동 색인 목적지 = `experiential-marketing-media-web` = 기존 118 URL 이 사는 바로 그 컬렉션.** `clear=False`(`:1060`) 이므로 **upsert 혼합**된다.

🔴 **지시서 §3-a 의 우려가 실현됐다.** 그대로 돌리면 X 가 신·구 혼합이 되어 대조가 무효다.

### 4-b. `*_filtered.json` 직접 색인 진입점 — **있음. 단 NS 인자가 무시된다**

| 항목 | 값 |
|---|---|
| 함수 | `add_web_pages_json_to_chroma(json_file, *, chunk_size, chunk_overlap, namespace, collection_name, persist_directory, embedding, clear) -> Tuple[int,int]` |
| 파일:행 | `tools/web_rag/ingest_vector.py:1442` — 모듈 최상위 공개 함수 |
| 래퍼 | `tools/web_rag/__init__.py:79` (→ `.ingest` 경유) |

→ **재색인 갈래는 성립한다.** 그러나:

🔴 **`namespace=` 인자로 별도 NS 를 지정해도 split 모드에서는 무시된다.**
- `_resolve_ns_for_docs`(`:343-351`): `ns_web`·`ns_loc` 이 **둘 다 설정**되고 `is_web` 판정이 나면 **`ns_web` 을 반환** — `base_ns` 를 버린다.
- `_resolve_persist_dir_strict`(`:237-`): split 모드에서 **`persist_directory` 인자를 무시**하고 ns 고유 디렉터리로 강제 라우팅.
- `_is_web_source`(`:353-`): `http(s)://` → `is_web=True`. 우리 자료는 전량 http(s).

> **따라서 Y 를 별도 NS 로 만들려면 `namespace=` 가 아니라 `CHROMA_NAMESPACE_WEB` **환경변수 자체**를 바꿔야 한다.** (또는 `CHROMA_NAMESPACE_LOCAL` 을 비워 split 모드를 해제 — 부작용 큼)

**부수 — seen-hash 조기 종료** (`ingest_vector.py:1463-1470`)
`load_seen_source_hashes` 로 **source→hash 가 전부 동일하면 `return (0,0)`** 하고 빌드를 건너뛴다. 같은 URL·같은 내용 재색인은 **자동으로 no-op** 이 된다. → Y 를 같은 NS 에 다시 넣으려 하면 조용히 스킵될 수 있다.

### 4-c. 자동 색인 차단 — **가능하다**

```
web_search.py:1053   if MAX_INDEXED_PER_ROUND > 0:        ← 색인 블록 전체의 게이트
web_search.py:1098   else: logger.info("[WEB INDEXING SKIP] MAX_INDEXED_PER_ROUND=0. Indexing skipped.")
```

→ **`MAX_INDEXED_PER_ROUND=0` 이면 수집만 하고 색인을 건너뛴다.** 전용 로그도 있다.

⚠️ **동시 부작용 1건 — 같은 상수가 라운드 캡도 겸한다.**
```
web_search.py:569    _round_cap = int(MAX_INDEXED_PER_ROUND or 0)   # 0 means unlimited
web_search.py:571-572 _cap_reached() = (_round_cap > 0 and _round_added_urls >= _round_cap)
```
0 으로 두면 `_cap_reached()` 가 **영구 False** → URL 상한이 **무제한**이 된다.
현재 실효값은 **60**(`.env:173`)이므로, 0 으로 바꾸면 *색인 차단*과 *캡 해제*가 **동시에** 일어난다.

> 값의 함의(사실): `MAX_INDEXED_PER_ROUND=0` 은 **"수집 → 정지 → 2벌 색인"을 성립시키는 유일한 코드상 스위치**이며, 동시에 17쿼리 전량이 캡에 걸리지 않고 집행되게 만든다.

### 4-d. NS 격리 3키 실동작 — **L3 탈환 불요**

| 파일 | `CHROMA_NAMESPACE` |
|---|---|
| `.env:126-128` | 주석 처리(비활성) |
| **`.env.openai:56-58`** | `venfobel-vitamin-oa` (+`-web`/`-local`) |
| `.env.anthropic:50-52` | `venfobel-vitamin-oa` |
| **`topics/experiential-marketing-media.env:7-9`** | `experiential-marketing-media` (+`-web`/`-local`) |

**CFG 실효값 실측**(`TOPIC_SLUG` 명시):
```
CHROMA_NAMESPACE        = 'experiential-marketing-media'
CHROMA_NAMESPACE_WEB    = 'experiential-marketing-media-web'
CHROMA_NAMESPACE_LOCAL  = 'experiential-marketing-media-local'
```
→ 🔴 **토픽 프리셋이 `.env.openai` 의 venfobel 을 이긴다**(로드 순서 §2-c). **탈환이 필요한 키는 0건.**
⚠️ 단 **`TOPIC_SLUG` 미지정이면 이 방어가 통째로 무너진다** — §10 deviation 1 참조.

### 4-e. 임베딩 비용 산정 근거

| 항목 | 값 | 근거 |
|---|---|---|
| 호출 단위 | **청크(split) 단위** | `ingest_vector.py:1090 split_documents(...)` → `documents_to_chroma` 가 splits 를 임베딩 |
| chunk_size | **2400 자** | `.env:133 RAG_CHUNK_CHARS=2400` (코드 기본 2400, `ingest_vector.py:414`) |
| chunk_overlap | **150 자** | `.env:135 RAG_CHUNK_OVERLAP=150` (코드 기본 200 — **.env 가 이김**) |
| 모델 | **`text-embedding-3-large`** | `CFG.RAG_EMBEDDING_MODEL` 실측 |
| 차원 | **3072** | 모델 사양. `R11 §6` 기재 dim 3072 와 정합 |
| 실측 비율 | 기존 `-web`: **118 URL → 416 청크 = 3.53 청크/URL** | sqlite3 실측 |

> 🔴 **지시서 6-d 의 `text-multilingual-embedding-002 · 768d` 는 stale 이다.** 그것은 vertex 계열이고, 현재 `LLM_PROVIDER=openai` · `SKIP_VERTEX_SEARCH=True` 다.

### 4-f. 기존 색인 118 의 NS·persist_dir

```
NS           experiential-marketing-media-web
persist_dir  writer_project/data/chroma_store/experiential-marketing-media-web/
청크          416   ·   distinct source 118   ·   content_type: text/html 398 / application/pdf 14 / text/plain 4
```
(`CHROMA_DIR=data/chroma_store`, `.env:125`)

---

## 5. 미결 4 — `published_date` 스펙

### 5-a. 현재 청크 메타데이터 스키마 — **3키뿐**

`sqlite3 -readonly` 전수: `embedding_metadata` 의 key 종류 = **`title`(416) · `source`(416) · `content_type`(416)** + Chroma 내부 `chroma:document`(416).

**샘플 1건 전문**
```
source       https://airweb.co.kr/logo_portfolio/265
title        따뜻한 음악 소통, 오디오 콘텐츠 플랫폼 로고 디자인
content_type text/html
document     (본문 — 사이트 내비게이션·푸터가 다수 포함)
```

🔴 **`published_date` 없음. 조각ID 없음.** 416/416 전건이 위 3키만 보유.

### 5-b. 메타를 추가할 자리

**조립 지점은 리터럴 dict 5곳**(`tools/web_rag/ingest_docs.py`)
```
:301  로컬 텍스트   {"source":"", "title":..., "content_type":"text/plain", **_promote_item_metadata(item)}
:372  로컬 파일     {..., "content_type": ctype, ...}
:398  웹 HTML(bs4)  {"source":url, "title":..., "content_type":"text/html", **_promote_item_metadata(item)}
:421  PDF           {..., "content_type":"application/pdf", ...}
:490  웹 HTML       {"source":url, "title":..., "content_type":"text/html", **_promote_item_metadata(item)}
:498  웹 텍스트     {"source":url, "title":..., "content_type":"text/plain", **_promote_item_metadata(item)}
```

**bs4 2곳 대칭 재확인** — 지시서 기재대로 실물 일치:
| 위치 | 실물 |
|---|---|
| `ingest_docs.py:385-386` | `soup = BeautifulSoup(raw_content,"lxml")` / `for tag in soup(["script","style","noscript"]): tag.decompose()` |
| `ingest.py:675-677` | 동일 2행 |
→ **`:386` 은 태그 제거 행이 맞다**(지시서 기재 정확. `CLAUDE.md §9` catch CL 의 기존 판정과 정합).

**확장 통로 = `_promote_item_metadata`**(`ingest_docs.py:236-257`) — 그러나 **화이트리스트**다. 승격 키는 `backend` · `chunk_domain` · `alt_urls` **3개뿐**이고, `item["metadata"]` 하위만 본다. → **현 상태로는 `published_date` 가 통과할 통로가 없다.**

### 5-c. 🔴 `raw_content` 에 발행일이 실제로 있는가 — **전수 8.7%**

**대상 = 전수**(표본 아님). `resources/experiential-marketing-media/*_filtered.json` **38파일 · 항목 69건 전량**.

| 신호 | 검출 | 비율 |
|---|---|---|
| **구조화 메타 보유(합집합)** | **6 / 69** | **8.7%** |
| └ `article:published_time` | 6 | 8.7% |
| └ `og:published_time` | 0 | 0% |
| └ JSON-LD `datePublished` | 0 | 0% |
| └ `meta name=date/pubdate/DC.date` | 0 | 0% |
| └ `<time datetime=>` | 0 | 0% |
| 본문 날짜 문자열(느슨) | 7 / 69 | 10.1% |

**🔴 이 8.7% 는 일반화할 수 없다 — 코퍼스가 2도메인뿐이다**

| 도메인 | 항목 | ~2800자 껍데기 |
|---|---|---|
| `blog.naver.com` | 63 | **62** |
| `mk.co.kr` | 6 | 0 |

- **distinct URL = 17** (항목 69는 파일 간 중복 포함). 도메인 **2개**.
- **발행일 보유 6건 = mk.co.kr 6건과 정확히 일치.** 즉 *"8.7%"* 가 아니라 **"매체사 100% / 네이버블로그 0%"** 가 실체다(`catch CI` — 한 호스트 쏠림).
- ⚠️ **절단 아님을 확인**: `</head>` 도달 **69/69**, 꼬리가 `</body></html>` 정상 종료, `raw_bytes` 와 정합. 2800자 뭉침은 **네이버 블로그 iframe 껍데기**의 실제 크기다(본문은 iframe 너머에 있어 raw_content 에 없음).

> **표본 한계 명기** — 이 코퍼스는 8/1 수집분이며 **동결 17쿼리의 산물이 아니다.** 신규 수집의 도메인 구성은 다를 수 있다. 위 수치는 **현존 자료 전수**이지 **미래 수집의 예측치가 아니다.**

### 5-d. 조각ID 현황 — **부재**

`published_date|publish_date|datePublished|pub_date` — 코드베이스 재귀 **0건**(양성 대조 §10).
`chunk_id|chunk_index|piece_id|chunk_no` — **4건 전부 `tools/sample_chunks_for_eval.py`**(평가용 샘플러가 실행 시점에 자체 생성). **색인 파이프라인·저장 메타에는 없음**(§5-a sqlite 실측과 정합).

→ 둘 다 §5-b 의 같은 리터럴 dict 자리에서 **함께 붙일 수 있다.**

### 5-e. retrieve 단에서 메타를 읽는 경로 — **읽지만, 지정 키만 읽는다**

```
vector_search.py:215-220  _raw_title(d)  → meta.get("title")
vector_search.py:226-229  _doc_url(d)    → meta.get("source") or meta.get("url") or meta.get("path")
vector_search.py:232-237  _doc_score(d)  → meta.get("score")
vector_search.py:615·619  meta.get("_retrieved_src") / meta.get("_retrieved_ns")   ← 런타임 주입값
```

→ **명시 키 접근이며 passthrough 가 아니다.** `published_date` 를 붙여도 **현재 소비처는 0건**이므로 retrieve·writer 어디에도 나타나지 않는다. 쓰려면 **소비 측 코드 추가가 별도로 필요**하다.

---

## 6. `R11 §10` 게이트 8항 실측

| # | 항목 | 실측 | 판정 근거 |
|---|---|---|---|
| 1 | `GATE_KEEP_SOURCES` 실효값 | 🔴 **False (꺼짐)** | `.env:208=0` · CFG=False · `gatekeep_enabled()`=False. 점화 수단은 **`.env` 만 유효**(§2-a) |
| 2 | 허용 도메인 비면 라운드 자동 비활성화 | **미발동 조건** | `get_allowed_domains()` = **79건** (비어 있지 않음). `web_search.py:442-453` 의 자동 해제는 걸리지 않는다 |
| 3 | `SKIP_WEB_SEARCH` | **False** | `.env:206=0` · CFG=False. `:739` `if SKIP_WEB:` 실물 확인 · `:1175` 확인 |
| 4 | `references` 기적재분 배제 | **0건 예상(조건부)** | 새 state 구성 시 `references` 공집합 → 배제 0. 검증은 `:1176` 목록 대조로만 가능(§3-d) |
| 5 | 수집→색인 자동 연결 | 🔴 **연결됨. 동일 NS** | `:1053-1062` → `experiential-marketing-media-web`(=기존 118). `MAX_INDEXED_PER_ROUND=0` 으로 차단 가능(§4-c) |
| 6 | 주입 키 `:1148`·`:1149` **or 연쇄** | **실물 확인** | `:1148 plan_from_state = (state.get("research_plan") or {}).get("queries") or []` / `:1149 raw_planner_qs = list(plan_from_state or []) or list(state.get("planner_queries") or [])` → **1순위가 비어야 2순위**. 둘 다 채우지 않는다 |
| 7 | 실행 후 주입 키 소거 → 1회성 | **실물 확인** | `:1187 state["planner_queries"]=[]` · `:1188-1190 rp["queries"]=[]` |
| 8 | 17줄 플레이스홀더 재확인 | **0건 ✅** | 해시 `06e5f818…03a8` **불변** · 17줄 단언 통과 · 7패턴 검사 0건 · **양성 대조 7/7 검출**(§10) |

---

## 7. 비용 산정 재료

| # | 항목 | 실측값 |
|---|---|---|
| **6-a** | 검색 호출 단위 | `tools/web_rag/search.py:1336` `web_search(query: str, *, engine: Optional[str]=None, num: int=10)`. **쿼리 1개 = 검색 API 1콜.** 🔴 `num` 기본 10 이지만 tavily 경로가 `search.py:607 max_results = max(1, min(num, 5))` 로 **5 로 깎는다** → **쿼리당 최대 5건** |
| **6-b** | 엔진·과금 | **Tavily 단독.** `HAS_TAVILY=True` + `TAVILY_API_KEY` 보유 / `HAS_SERPAPI=False` · `SERPAPI_API_KEY` 없음 / `GOOGLE_API_KEY` 없음 / `SKIP_VERTEX_SEARCH=True`. 무료 쿼터 여부는 **코드에서 알 수 없음**(계정 속성) |
| **6-c** | 페이지 fetch 비용 | **검색 API 과금 없음.** `search.py:1855 _enrich_raw_content(results)` → `:536-573` 가 **자체 `http_get(u)` 1회/URL**. `include_raw_content=False`(`:609`) 이므로 raw_content 는 전부 이 자체 fetch 산물. PDF 는 `_fetch_pdf_once` → `raw_content=""` + `raw_bytes` 기록 |
| **6-d** | 임베딩 | **`text-embedding-3-large` · 3072d.** 호출 단위 = **청크**(2400자/overlap 150). 실측 비율 3.53 청크/URL |
| **6-e** | 🔴 LLM 호출 | **생성이 아니라 실제 호출이다.** `:202 llm = get_llm()` 은 생성(비용 0)이나, **`:1226 (web_search_system_prompt \| llm_with_web).invoke(inputs)` 가 실제 호출**이다. `SKIP_WEB` 이 아닌 한 **무조건 1회** 실행되며 **주입 쿼리 유무와 무관**하다. 모델 `gpt-4o` |

### 7-a. 🔴 6-e 의 파생 — LLM 이 만든 쿼리가 추가 집행된다

```
web_search.py:1224   if not SKIP_WEB:
web_search.py:1226       search_plans = (prompt | llm_with_web).invoke(inputs)     ← 무조건 LLM 호출
web_search.py:1228       for args in iter_tool_calls(search_plans, "web_search"):
web_search.py:1232           if ran >= MAX_SEARCH_QUERIES_PER_ROUND: break
web_search.py:1248           if lk in _existing_qs: continue                       ← 17개와 문자열이 다르면 통과
web_search.py:1251           if _run_web_search_with_guard(q): ran += 1            ← 집행됨
```

| 항목 | 값 |
|---|---|
| `MAX_SEARCH_QUERIES_PER_ROUND` 실효값 | **6** (`CFG`, `config.py:571` 기본 6 · `min_=0, max_=50`) |
| ⚠️ 기본값 불일치 | `web_search.py:345`·`:1675` 는 로컬 기본 **3**, `config.py:571` 은 **6** — `.env` 3파일 전부 **미설정** → CFG 값 **6** 이 실효 |
| 억제 가능 여부 | **가능.** `min_=0` 이므로 `MAX_SEARCH_QUERIES_PER_ROUND=0` 이면 `:1232` 가 첫 회차에 즉시 break → **집행 0** |
| 잔여 비용 | `:1226` LLM 호출 **1회는 그대로 발생**(억제 수단 없음, `SKIP_WEB` 제외) |

> **사실 기술(판정 아님)** — 억제하지 않으면 1라운드 코퍼스에 **동결 17쿼리 + LLM 생성 최대 6쿼리**의 산물이 섞인다. 이 경우 `R11 §8` 의 *"본 코퍼스는 동결 쿼리 17개의 1라운드 수집분"* 진술이 **성립하지 않는다.**

### 7-b. 수집 규모 상한 (산술)

```
검색 API 콜   = 17 (동결)  [+ 최대 6 (LLM 생성, 미억제 시)]
URL 상한      = 17 × 5 = 85  [+ 6 × 5 = 30]
자체 GET      = URL 수만큼 1회씩 (과금 없음)
LLM 호출      = 1 (gpt-4o, :1226)
임베딩        = (색인 시) 청크 수 ≈ URL 수 × 3.53   ← 기존 색인 실측 비율
라운드 캡     = MAX_INDEXED_PER_ROUND=60  ← 85 < 60 아님. 🔴 60에서 잘린다
```
🔴 **현 설정(60)으로는 17쿼리를 다 돌기 전에 `_cap_reached()` 가 발동할 수 있다**(`:1178-1180`). 85 잠재 URL > 60 캡.

---

## 8. 인용 행번호 재확인 — 어긋남 **3건** (STOP 7 임계 5건 **미달**)

| # | 인용 | 실물 | 차이 |
|---|---|---|---|
| 1 | `web_search.py:1160` (references 배제) | **`:1159`** `if lk in seen_norm or lk in _existing_qs:` | **-1** |
| 2 | `web_search.py:303-308` (`_existing_qs`) | **`303-307`** (`}` 가 307) | **경계 1줄 과다** |
| 3 | `web_search.py:204` (`get_llm()`) | **`:202`** | **-2** |

**일치 확인분(어긋남 없음)** — `core/config.py:278`·`511`·`771` / `app.py:2232-2234`·`2269-2272` / `settings_gatekeep.py:223` / `web_search.py:431`·`442-453`·`533-534`·`552`·`739`·`1049`·`1053-1060`·`1148`·`1149`·`1175`·`1181`·`1187-1190` / `ingest_vector.py:1442` / `search.py:1336` / `ingest_docs.py:386` / `ingest.py:677`

> ⚠️ #2 는 지시서 §0-b 가 예고한 **"범위 추출 경계 1줄 과다"** 유형이다.
> 🔴 **코드 변경 징후는 없다.** 3건 모두 소폭이고, 대량 일치분이 옆에 있다.

**내용 정정 1건** — 지시서 §6 6-d 의 `text-multilingual-embedding-002 · 768d` → 실물 **`text-embedding-3-large` · 3072d**(§4-e).

---

## 9. 0건 보고 목록 — 전건 양성 대조 병기

cwd = `writer_project/` (전건 동일). 재귀 검색은 `command grep` 병행(`catch CG`).

| # | 0건 주장 | 검색 방식 | 🔴 양성 대조 |
|---|---|---|---|
| 1 | `published_date` 계열 코드 소비처 **0건** | `command grep -rn "published_date\|publish_date\|datePublished\|pub_date" --include="*.py" .` | **동일 명령·동일 경로**로 `content_type` → **45건**, `raw_content` → **41건** 검출 ✅ |
| 2 | 조각ID 색인 경로 **0건** | 위와 동일 패턴(`chunk_id` 외 3종) | 위와 동일. 실제로 `sample_chunks_for_eval.py` **4건은 검출됨** → 검색기 생존 확인. 색인 경로에만 부재 |
| 3 | 17줄 플레이스홀더 **0건** | 7패턴 정규식 전량 스캔(17줄 길이 단언 선행) | 합성 7줄(`{topic}` `<TOPIC>` `[[3]]` `TODO` `{{q}}` `%s` `TOPIC_QUERY`) → **7/7 검출** ✅ |
| 4 | 발행일 구조화 메타 — `og:published_time`·JSON-LD·`<time>`·`meta[name=date]` 각 **0건** | raw_content 전수 정규식 | 합성 HTML 1건 → `article:published_time`·`datePublished`·`time[datetime]` **3/3 검출**, 음성 대조(무날짜) **0건** ✅ |
| 5 | `topics/experiential-marketing-media.env` 에 `GATE_KEEP_SOURCES` **0건** | 파일 지목 `command grep` | **동일 파일**에서 `CHROMA_NAMESPACE` **3건** 검출 ✅ (ignore 여부와 무관하게 읽힘 확인) |
| 6 | `MAX_SEARCH_QUERIES_PER_ROUND` — `.env` 3파일 **0건** | 파일 지목 `command grep` | 동일 명령이 `.env` 에서 `MAX_INDEXED_PER_ROUND` **1건** 검출 ✅ |
| 7 | `references` 영속 저장 파일 **0건** | `find . -maxdepth 3 -name "*state*.json"` | 동일 `find` 로 `data/chroma_store/**` 하위 실재 파일 다수 확인(§4-f sqlite 개방 성공) ✅ |

---

## 10. Deviation 자진 보고 — **2건**

**1. 🔴 `TOPIC_SLUG` 미지정 실행 1회 (catch AB 실연)**
- **무엇** — 첫 도메인 집계에서 `TOPIC_SLUG` 없이 `import core.config` 를 실행했다. 콘솔에 `[Config] 토픽 프리셋 로드: topics/academic-trademark-similarity-consumer.env` 가 찍혔다 — **논문 트랙 프리셋이 로드됐다.**
- **영향** — 해당 실행의 산출은 `.env` 파일 **직접 파싱값**(ALLOWED_DOMAINS 78 · `_BASE` 17 · 합집합 79)이라 프리셋 무관. **오염 없음.** 이후 CFG 를 읽는 모든 실행은 `TOPIC_SLUG=experiential-marketing-media` 를 명시했고, 재측정에서도 **79 로 동일**했다.
- **처리** — 이후 전 실행에 `TOPIC_SLUG` 명시 + 스크립트에 `assert os.environ.get("TOPIC_SLUG")` 선행(`CLAUDE.md §1`).
- ⚠️ **부수 가치** — 이 사고가 §4-d 의 *"`TOPIC_SLUG` 미지정 시 NS 방어가 무너진다"* 를 **실물로 입증**했다.

**2. zsh glob 미인용으로 재귀 grep 1회 무효**
- **무엇** — `--include=*.py` 를 따옴표 없이 써서 zsh 가 `no matches found` 로 명령을 죽였다.
- **영향** — `published_date` 검색이 **0건처럼 보였다.** 🔴 **양성 대조가 이를 잡았다** — 같은 명령의 `content_type` 이 **0건**으로 나와 즉시 무효임이 드러났다(정상값 45).
- **처리** — `--include="*.py"` 로 재실행. §9 표는 재실행 결과다.
- ⚠️ `CLAUDE.md §3`(zsh `*` 인용) + §9(양성 대조 없는 0건 금지)가 **둘 다 작동한 사례**다. 양성 대조가 없었으면 *"published_date 0건"* 은 맞는 결론이지만 **틀린 근거**로 보고될 뻔했다.

**신규 catch 번호 부여 0건** (지시서 §11 준수).

---

## 11. 실비용 — **$0 실측**

| 항목 | 건수 |
|---|---|
| 검색 API 호출 | **0** |
| LLM 호출 | **0** (`get_llm()` 조차 호출 안 함 — `web_search_agent` 미실행) |
| 임베딩 호출 | **0** |
| Chroma 쓰기 | **0** (전량 `sqlite3 -readonly`) |
| 네트워크 GET | **0** |

**무변경 증명 (self-check #94)**
```
$ shasum -a 256 scripts/output/§research-1/Q_FROZEN_20260809.txt
  06e5f81828d0f287e324760a455ab5dc05d1edeb109d951101b155a8218b03a8   ← 지시서 §8-5 와 일치

$ git status --short -- agent/web_search.py prompts.py core/config.py \
                        scripts/output/§research-1/Q_FROZEN_20260809.txt tools/web_rag/
  (0줄)

$ git log --oneline -1
  03bbde70   ← 착수 시와 동일
```
- `web_search.py:848` **무접촉**(읽기만) · `prompts.py` **무수정** · `GATE_KEEP_SOURCES` **점화 안 함** · `seed_web_namespace` **미사용**
- 임시 스크립트는 **스크래치패드**에 작성 — 워킹트리 `??` 목록 **불변**(`catch AS` 가독성 유지)

---

## 12. 값이 부족해 판정이 불가능한 항목 — **1건**

지시서 §7 은 *"값이 부족해 판정이 불가능해 보이면 그 사실을 보고"* 를 요구한다.

| 항목 | 부족한 이유 |
|---|---|
| **5-c 발행일 비율의 신규 수집 예측** | 현존 코퍼스가 **distinct URL 17 · 도메인 2개**뿐이고, 그나마 **동결 17쿼리의 산물이 아니다**(8/1 수집분). 8.7% 는 **현존 자료 전수로는 정확**하나 **신규 수집의 예측치로는 근거가 없다.** 닫으려면 유료 수집이 선행돼야 하므로 **이 차수에서는 닫을 수 없다**(`catch CM` — 미확정으로 남기고 어느 쪽으로도 밀지 않는다) |

그 밖 미결 1·2·3 은 **판정에 필요한 값이 전부 확보**됐다.

---

## 13. 이번 차수가 하지 않은 것

```
❌ 수집·색인 착수            ❌ GATE_KEEP_SOURCES 점화
❌ 미결 4건의 판정            ❌ 새 catch 번호 부여
❌ 커밋·push                 ❌ 원장 문서(CLAUDE.md 등) 수정
❌ web_search.py:848 접촉     ❌ prompts.py 수정
```

**커밋 대기 상태.** `git add -A` **금지**(논문 트랙 미커밋분 상주 — `CLAUDE.md §4` catch AS). 개별 `git add` + `git diff --staged --name-status` 확인 후 커밋하되, **지시받은 뒤** 진행한다.
