# R13 — S8 NS 분리 수단 확정 정찰 ($0 · 읽기 전용)

- **실행일 2026-08-12** · 채널 = 기술 정밀 · 실비용 **$0**
- 계보 `CC_S8_20260812_ns_split_scout.md`(지시서) ← `R12_PRECOLLECT_SCOUT.md §4-b`·`§4-d`·`§2-a`
- 성격 = **정찰. 색인·수집·API·LLM 호출 0 · 파일 쓰기 0**
- 🔴 **판정·권고 없음.** 후보를 고르지 않는다. 다만 *값이 선택지를 소멸시키는 경우*는 사실로 기술한다(지시서 §5 단서)

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
TOPIC_SLUG  experiential-marketing-media   ← 전 스크립트에 assert 선행 (R12 deviation 1 재발 방지)
```

catch AR 재검증 — HEAD **`4bedc840`**, 지시서 기재와 **일치**. 워킹트리 `M` = 논문 트랙 `measure_paper.py` 1건(무접촉).

> 검색 cwd 는 전부 `writer_project/`. `.env*`·`topics/*.env` 는 **파일 지목 + `command grep`**, zsh glob 은 전량 인용(`--include="*.py"`).

---

## 2. 🔴 후보 5개 비교표

| 후보 | ① 성립하는가 | ② 부작용 | ③ 되돌릴 수 있는가 |
|---|---|---|---|
| **① `CHROMA_NAMESPACE_LOCAL` 비워 split 해제** | 🔴 **`.env`·프리셋·env 경로로는 불성립** (실증). `__post_init__` 이 빈 값을 `{slug}-local` 로 **자동 충전**. CFG 직접 주입으로만 가능 → **기전이 ④와 같아짐** | split off 시 web 문서가 `-web` 이 아니라 **base NS**(`experiential-marketing-media`, 현재 **0청크**)로 간다. retrieve 측 local 은 자동 파생으로 **도달 유지**(실측) | (CFG 주입 경로일 때) 프로세스 한정 |
| **② 새 프리셋 파일 복사 + `TOPIC_SLUG` 교체** | ✅ **성립** | 슬러그가 NS 외 **다수 경로**를 파생(`resources/<slug>/` · `eval/goldset/<slug>/` · state·planner·synthesizer). 프리셋 **13키 전량 복제** 필요. 누락 시 `.env.openai` venfobel NS 로 회귀(실증) | 파일 삭제 + `TOPIC_SLUG` 원복. **비파괴** |
| **③ 기존 프리셋 임시 편집** | ✅ 성립 | 🔴 **ad 트랙 공유 파일.** 게다가 `writer_project/.gitignore:75 topics/*.env` 로 **ignored** → `git diff` 원복 불가 · `git status` 미노출 · `git add` 거부 | **git 근거 없음.** 수동 백업이 유일 |
| **④ 드라이버에서 CFG 속성 직접 주입** | ✅ **성립 (실증)** | `reload_config()` 를 부르면 **소멸**(1회성, 실증). 파일 **무변경** | 프로세스 종료로 자동. `setattr` 원복도 즉시 |
| **⑤ `_PROTECTED_ENV_KEYS` 확장** | ❌ **불가** | 모듈 최상위 **하드코딩 튜플**. ENV 확장 코드 **0건**(양성 대조 병기) | — (코드 수정은 범위 밖) |

### 2-a. STOP 조건 판정

| # | 조건 | 결과 |
|---|---|---|
| 1 | 후보 5개 **전부** 불성립 | **미발동** — ②③④ 성립 |
| 2 | 2-e NS 지정 retrieve **불가** | **미발동** — 성립(§5-e 실증) |
| 3 | seen-hash **전역 작용** | **미발동** — **NS 단위**(§5-c) |
| 4 | `Q_FROZEN` 해시 불일치 | **미발동** — `06e5f818…03a8` 불변 |
| 5 | 실비용 $0 초과 / 쓰기 발생 | **미발동** — 쓰기 **0건** 실증(§10) |
| 6 | 인용 행번호 5건 이상 어긋남 | **미발동** — **0건** |

### 2-b. 🔴 값이 선택지를 소멸시킨 것 2건

1. **후보 ① 은 독립 후보가 아니다.** `.env`/프리셋에서 `CHROMA_NAMESPACE_LOCAL` 을 지우거나 비워도 `core/config.py:414 __post_init__` 의 자동 파생 블록(`:450-456`)이 `{slug}-local` 로 되채운다. 성립하는 유일한 경로는 `_build_config()` **이후** `setattr(CFG, …, "")` 이며, 그것은 **후보 ④의 기전 그 자체**다.
2. **후보 ⑤ 는 불가.** `_PROTECTED_ENV_KEYS` 는 `core/config.py:661-667` 튜플 리터럴이고, 코드베이스 전체 참조가 **정의 1 + 사용 1 = 2곳뿐**이다. ENV·설정으로 확장하는 경로가 없다.

---

## 3. 후보별 상세

### 3-a. 후보 ① — split 모드 해제

| # | 확인 | 결과 |
|---|---|---|
| 1 | `split_mode` 판정 조건 | `ingest_vector.py:1459` `split_mode = bool(ns_web_env and ns_loc_env)` — 🔴 **둘 다 설정**이 조건. 한쪽만으로는 서지 않는다. 동일 판정이 `:246`(`_resolve_persist_dir_strict`) · `:350`(`_resolve_ns_for_docs`) · `:809` 에도 있다 |
| 2 | split off 면 `namespace=` 인자가 살아나는가 | ✅ **실증.** `_resolve_ns_for_docs('MY-EXPLICIT-NS', is_web=True)` → split on 이면 `'experiential-marketing-media-web'`(인자 무시), split off 면 **`'MY-EXPLICIT-NS'`**(인자 생존, `split_applied=False`) |
| 3 | split off 면 `persist_directory` 인자가 살아나는가 | ✅ 코드상 성립 — `_resolve_persist_dir_strict:252` 의 강제 분기는 `if split_mode and ns in (ns_web, ns_loc):` 이므로 split off 면 `_resolve_persist_dir(ns, persist_directory)` 로 내려가 인자를 존중한다. **(추론 — 실행 미검증. 이 함수는 `mkdir` 부작용이 있어 호출하지 않았다, §10 참조)** |
| 4 | 🔴 retrieve 파급 — local NS 가 없으면 깨지는가 | ✅ **깨지지 않는다(실증).** `vector_search.py:398-404` 가 `_cfg_str(CHROMA_NAMESPACE_LOCAL)` 이 비면 **`f"{ns_default}-local"` 로 자동 파생**. `LOC=""` 주입 후 해석값 = `('…-web', '…-local')` — 기준선과 **동일** |
| 5 | local 색인 302청크는 어떻게 되는가 | **그대로 접근 가능.** #4 의 자동 파생이 `experiential-marketing-media-local` 을 그대로 가리킨다. `_split_k`(`vector_search.py:360`)는 NS 와 무관하게 `RETRIEVE_WEB_RATIO` 만 쓰므로 영향 없다 |
| 6 | 되돌리기 | CFG 주입 경로면 프로세스 한정 → **비가역 변화 없음.** 단 **색인이 실제로 실행되면** web 문서가 base NS 로 들어가 데이터가 남는다(그 시점부터 비가역) |

> 🔴 **#2 가 후보 ①의 유일한 이점**(`namespace=` 인자 부활)인데, 그것을 얻으려면 `.env` 로는 안 되고 CFG 주입이 필요하다. **CFG 주입이 가능하면 `CHROMA_NAMESPACE_WEB` 을 직접 바꾸는 편이 경로가 짧다**(사실 기술이며 권고 아님).

**실증 로그 (드라이런, 순수 함수만 호출)**
```
[기준선]         _resolve_ns_for_docs(base)   = 'experiential-marketing-media-web'   split_applied=True
                 _resolve_ns_for_docs(MY-…)   = 'experiential-marketing-media-web'   split_applied=True   ← 인자 무시
[LOC='' 주입]    _resolve_ns_for_docs(base)   = 'experiential-marketing-media'       split_applied=False
                 _resolve_ns_for_docs(MY-…)   = 'MY-EXPLICIT-NS'                     split_applied=False  ← 인자 생존
```

**자동 충전 실증 (프리셋 없는 슬러그로 격리)**
```
TOPIC_SLUG=zz-no-preset-xyz  +  CHROMA_NAMESPACE_LOCAL=""
  → _build_config().CHROMA_NAMESPACE_LOCAL = 'zz-no-preset-xyz-local'
  → split_mode = True        ← 비웠는데 다시 켜진다
```
⚠️ **자체 정정 1건** — 1차 시도는 `TOPIC_SLUG=experiential-marketing-media` + `CHROMA_NAMESPACE_LOCAL=""` 였는데, **토픽 프리셋이 `override=True` 로 그 키를 되설정**해 env 비우기가 `_build_config` 에 도달조차 못 했다. 그래서 프리셋 없는 슬러그로 계층을 분리해 재측정했다. → **방어가 2겹이다: (1) 프리셋 재설정 (2) `__post_init__` 자동 충전.**

### 3-b. 후보 ② — 새 프리셋 파일 + `TOPIC_SLUG` 교체

| # | 확인 | 결과 |
|---|---|---|
| 1 | 프리셋 전문 키 목록 | **13키** — `TOPIC_TITLE` · `TOPIC_SLUG` · `CHROMA_NAMESPACE`(+`_WEB`/`_LOCAL`) · `LOCAL_RAG_GLOBS` · `RETRIEVE_WEB_RATIO` · `BLOCKAGI_OBJECTIVE_1~5` · `SKIP_VERTEX_SEARCH` |
| 2 | 🔴 `TOPIC_SLUG` 소비처 전수 | 코드베이스 **130건**. NS 외 파생: `core/config.py:450`(NS 3키 파생) · `tools/local_rag.py:1404`·`1426`(`research_resources_dir`)·`1576`(`_compute_effective_ns`)·`1617` · `tools/topic_config.py:103` · `core/state_io.py:116` · `core/routers.py:188`·`988` · `agent/research_planner.py:86` · `agent/research_synthesizer.py:71` · `agent/supervisor.py:166` · `agent/vector_search.py:715` · `agent/web_search.py:227` · `app.py:495`·`2220`·`2342` |
| 3 | 경로 파생 | `resources/<slug>/`(수집 산출물) · `data/chroma_store/<ns>/` · `eval/goldset/<slug>/`·`eval/results/`(`tools/sample_chunks_for_eval.py:38` · `tools/eval_embedding_models.py:50-51`) |
| 4 | tracked 인가 | 🔴 **untracked.** `git ls-files --error-unmatch` → `did not match any file(s) known to git`. **양성 대조** — 같은 명령이 `topics/academic-trademark-similarity-consumer.env` 는 정상 반환. tracked 프리셋은 **6건**(`_example.config.json` · `_template.env.example` · `academic-*` 4건), 실파일은 **12건** |
| 5 | 새 슬러그가 `.env.openai` venfobel 을 이기는가 | ✅ **실증.** 로드 순서 `.env`(override=False) → `.env.<provider>`(override=True) → `topics/<slug>.env`(override=True). 프리셋이 **최후**. ⚠️ 단 **프리셋 파일이 없으면 방어가 통째로 무너진다** — `TOPIC_SLUG=zz-no-preset-xyz` 실행에서 CFG NS 3키가 전부 **`venfobel-vitamin-oa*`** 로 나왔다 |
| 6 | `§ad-track-1` 공유 영향 | **원본 무접촉이면 영향 0.** 새 파일을 만드는 방식이므로 기존 프리셋을 읽는 ad 트랙 경로는 그대로다. 단 **①·②·③ 전부 `BLOCKAGI_OBJECTIVE_1~5` 를 복제**해야 objective 기반 동작이 유지된다(프리셋 유일 소스) |

⚠️ **#2 의 함의** — 슬러그를 바꾸면 **수집 산출물 경로(`resources/<slug>/`)도 함께 갈린다.** 이는 X·Y 원자료를 섞이지 않게 하는 부수 효과이기도 하고, 기존 `resources/experiential-marketing-media/` 43건과 분리된다는 뜻이기도 하다. **사실 기술이며 판정 아님.**

### 3-c. 후보 ③ — 기존 프리셋 임시 편집

| # | 확인 | 결과 |
|---|---|---|
| 1 | 🔴 `§ad-track-1` 공유 영향 | **공유 파일이다.** `CLAUDE.md`(트랙 상수)가 `§ad-track` 토픽으로 `topics/experiential-marketing-media.env` 를 명시하고, `R2c` 도 §research-1 이 ad 트랙과 토픽을 공유한다고 기록. 편집 중 ad 트랙 실행이 있으면 **그 실행이 오염된다** |
| 2 | tracked 면 `git diff` 로 원복 가능한가 | 🔴 **불가.** `git check-ignore -v` → `writer_project/.gitignore:75  topics/*.env`. `git add --dry-run` 실물 = `The following paths are ignored…` **거부** |
| 3 | 편집 중 실수로 커밋될 위험 | **낮다** — `git status --short -- topics/` **0줄**(미노출), `git add` 자체가 거부됨. ⚠️ 그러나 **같은 이유로 변경 이력이 남지 않아 원복 근거가 없다.** 위험이 "오커밋"에서 "무기록"으로 바뀐 것이지 사라진 것이 아니다 |

### 3-d. 🔴 후보 ④ — CFG 속성 직접 주입 (신규 후보)

| # | 확인 | 결과 · 근거 행 |
|---|---|---|
| 1 | 🔴 **호출 시점인가 import 시점인가** | ✅ **호출 시점.** `ingest_vector.py:1457-1458` 이 함수 **본문 안**에서 `getattr(CFG, "CHROMA_NAMESPACE_WEB", "")` 를 매번 읽는다. 모듈 최상위 캐시 상수 **0건**(§9-1 양성 대조) |
| 2 | 다른 2곳 동일 확인 | ✅ `_resolve_ns_for_docs` **`:348-349`** · `_resolve_persist_dir_strict` **`:244-245`** — 둘 다 함수 본문 내 `getattr(CFG, …)` |
| 3 | 모듈 상단 캐시 상수 | **0건.** `ingest_vector.py` 의 CFG 참조 **24건 전량이 함수 본문 내부**. 최상위 대입은 `from .ingest_config import CFG`(`:51`) 하나뿐 |
| 4 | 🔴 `setattr` 후 NS 가 바뀌는가 | ✅ **실증.** `setattr(CFG,"CHROMA_NAMESPACE_WEB","…-web-y")` → `_resolve_ns_for_docs` 반환이 `'…-web'` → **`'…-web-y'`** 로 즉시 변경 |
| 5 | `reload_config()` 를 안 부르면 유지되는가 | ✅ **유지.** 부르면 **소멸**(실증: `'…-web-y'` → `'…-web'`). 즉 **1회성 주입** |

**전제 검증 — CFG 객체 동일성**
```
tools/web_rag/ingest_config.py:13   from core.config import CFG   # 실제 CFG 객체
core.config.CFG is ingest_config.CFG  →  True   (id=4348785616)
```
`reload_config_inplace` 는 `setattr(CFG, f.name, …)` 로 **같은 객체를 제자리 갱신**하므로 동일성이 유지된다. → 어느 모듈에서 주입해도 전 모듈에 보인다.

**실증 로그**
```
[기준선]        _resolve_ns_for_docs(base) = 'experiential-marketing-media-web'
[WEB 주입 후]   _resolve_ns_for_docs(base) = 'experiential-marketing-media-web-y'    ← 즉시 반영
[reload 후]     CFG.CHROMA_NAMESPACE_WEB   = 'experiential-marketing-media-web'      ← 1회성
```

### 3-e. 후보 ⑤ — `_PROTECTED_ENV_KEYS` 경로 (참고)

| # | 확인 | 결과 |
|---|---|---|
| 1 | 하드코딩인가 | 🔴 **하드코딩 튜플.** `core/config.py:661-667`, 5키(`LLM_PROVIDER`·`LLM_MODEL`·`TOPIC_SLUG`·`SKIP_VERTEX_SEARCH`·`MIRROR_STATE_TO_ENV`) |
| 2 | ENV 확장 가능한가 | ❌ **불가.** 코드베이스 전체 참조 = **정의(`:661`) + 사용(`:679`) 2곳뿐.** 확장·병합·오버라이드 코드 0건 |

→ **`CHROMA_NAMESPACE_WEB` 에 적용할 방법이 없다.** 코드 수정은 범위 밖이므로 **"불가"로 마감**한다.

---

## 4. NS 이름·격리 제약

| # | 항목 | 결과 |
|---|---|---|
| **2-a** | NS 이름 제약 | `utils.py:334 sanitize_ns` — 허용 문자 **한글(AC00–D7A3)/A–Za–z0–9/`.`/`_`/`-`**, 경로구분자·기타 → `_`, 연속 `_` 압축, 선두·말미 `.-_` 제거, **소문자 강제**(`NAMESPACE_LOWERCASE` 기본 True), **길이 캡 120**(`NAMESPACE_MAX_LENGTH`), 빈 값 폴백 `ns_default`. 실측: `…-web-y`/`…-web-x`(34자) **무변형 통과** ✅ · `EMM-Web-Y`→`emm-web-y` · `emm/web/y`→`emm_web_y` · 130자→**120자 절단** |
| **2-b** | 🔴 persist_dir 분리 | ✅ **NS 가 다르면 디렉터리도 갈린다.** `utils.py:1696 _resolve_persist_dir` 우선순위 = ①인자 ②`CFG.CHROMA_DIR` ③`DATA_DIR/chroma_store/<ns>`. `_attach_leaf` 가 base 에 `/<ns>` 를 붙인다. 현재 `CHROMA_DIR=data/chroma_store`(base) → `data/chroma_store/<ns>/`. **기존 `experiential-marketing-media-web/` 은 새 NS 색인 시 무접촉** |
| **2-c** | 🔴 seen-hash 작용 범위 | ✅ **NS 단위. 전역 아님.** `utils.py:388 _seen_hash_path` = `<persist_dir>/<sanitize_ns(ns)>.__seen_sources__.json` — **파일명과 디렉터리 양쪽**이 NS 로 갈린다. → **X·Y 를 다른 NS 에 넣으면 충돌하지 않는다.** ⚠️ 부수 실측: 현재 seen-hash 파일은 **`venfobel-vitamin-web` 1건뿐**이고 `experiential-marketing-media-web` 에는 **없다** → 기존 118 NS 는 조기 종료가 **애초에 발동하지 않는다** |
| **2-d** | seen-hash 저장 위치 | `data/chroma_store/<ns>/<ns>.__seen_sources__.json` (실물 1건 확인) |
| **2-e** | 🔴 NS 지정 retrieve | ✅ **성립(실증).** `vector_search.py:391 _dual_retrieve(query,*,top_k,ns_default,persist_dir)` 가 `:398-399` 에서 `_cfg_str(CHROMA_NAMESPACE_WEB/LOCAL)` 을 읽고, **비면 `f"{ns_default}-web"`/`-local` 로 파생**(`:400-404`). `_cfg_str`(`:166-175`)은 `getattr(config.CFG, …)` **라이브 읽기** → **후보 ④ 주입이 retrieve 에도 그대로 먹는다** |

**2-e 실증 로그** (`_dual_retrieve` 해석부 축자 재현, 컬렉션 개방 없음)
```
ns_default='experiential-marketing-media'
  [기준선]        ('experiential-marketing-media-web',   'experiential-marketing-media-local')
  [WEB 주입 후]   ('experiential-marketing-media-web-y', 'experiential-marketing-media-local')   ← Y 겨냥 성립
  [LOC='']        ('experiential-marketing-media-web',   'experiential-marketing-media-local')   ← local 자동 파생
```

> 🔴 **2-e 의 함의(사실)** — X·Y 를 겨냥해 나눠 조회하려면 **조회 시점에도 같은 주입을 반복**해야 한다. `ns_default` 인자만으로는 web NS 를 겨냥할 수 없다(CFG 값이 비어 있지 않으면 CFG 가 이긴다).

---

## 5. Y 크롬 제거 구현 자리

### 5-a. bs4 사용처 전수 — 프로덕션 **3곳**, `decompose` 는 **2곳**

| 위치 | 소속 함수 | decompose | 색인 본선 |
|---|---|---|---|
| `ingest_docs.py:385` | `web_results_to_documents`(**260-504**) | ✅ `:387` | 🔴 **탄다** |
| `ingest.py:675` | `_load_html_as_text(url, timeout)`(**642-716**) | ✅ `:678` | 조건부(§5-b) |
| `tools/local_rag.py:497`·`499` | (로컬 경로) | ❌ 없음 | 웹 색인과 무관 |

`decompose()` 전수 = **2건**(`ingest.py:678` · `ingest_docs.py:387`) — 지시서의 *"bs4 2곳 대칭"* 과 일치 ✅ (양성 대조 §9-4)

🔴 **3-a 판정 — 둘 다 살아 있다. 사문 없음.**
- `ingest_docs.py:385` → 색인 진입점 `ingest_vector.py:1471 web_page_json_to_documents(json_file)` → 그 함수(`ingest_docs.py:506-613`)는 **로더·정렬기일 뿐**이고 `:611` 에서 `web_results_to_documents(resources)` 로 **위임**한다. → 본선 확정
- `ingest.py:675` → 유일 실호출 `ingest_docs.py:468 _ingest_mod._load_html_as_text(url_no_frag)` — `web_results_to_documents` **내부**에서 호출된다

⚠️ **R12 §5-b 의 기술 보강** — R12 는 메타 조립 리터럴 6곳을 `ingest_docs.py` 소재로 적었는데, **전부 `web_results_to_documents`(260-504) 안**이다. `web_page_json_to_documents` 는 Document 를 직접 만들지 않는다. R12 기술이 틀린 것은 아니나 **함수 귀속이 빠져 있었다.**

### 5-b. 🔴 두 경로의 진입 조건 — **배타적이다**

`web_results_to_documents` item 루프의 분기 순서:
```
:297  if not url:            → item_content 로 doc, continue
:364  # 1) file:// scheme    → item_content 로 doc, continue
:382  # 2) if raw_content:   → bs4(:385) + decompose(:387) → :396 doc → :400 continue   ★ 여기서 빠져나감
      # 3) PDF 경로
:464  # 4-1) ingest._load_html_as_text(url)  → bs4 ingest.py:675-678                    ★ raw_content 가 비어야 도달
:476  # 4-2) ingest_net.fetch_text + _clean_text(bs4 없음)
:495  # 5) item.content 폴백 (content_type=text/plain)
```

→ **`raw_content` 유무가 가른다.** 있으면 `:400 continue` 로 빠져 `:464` 에 **도달하지 않는다.**

- **실측 대조** — `R12 §5-c` 전수: `*_filtered.json` 69/69 전건이 `raw_content` **보유**(빈 항목 0) → **전건이 `ingest_docs.py:385` 경로.**
- ⚠️ 예외 = **PDF**. `search.py:_enrich_raw_content` 가 PDF 는 `raw_content=""` 로 두므로(`R12 §7 6-c`) `:382` 를 건너뛴다. 기존 색인의 `application/pdf` **14청크**가 이에 해당.
- 지시서 지적대로 **`content_type` 메타로는 못 가른다**(둘 다 `text/html`). **가르는 것은 호출자가 아니라 `raw_content` 유무**다.

### 5-c. 크롬 제거 ENV 플래그 — **없음. 신설 필요**

두 bs4 블록 주변(`ingest_docs.py:370-400` · `ingest.py:660-700`)에 `_cfg_bool`/`getenv`/`CFG.` **0건**.
`:382 if raw_content:` 외에 조건 분기가 없어 **켜고 끌 자리가 존재하지 않는다.**
**양성 대조** — 같은 파일 `ingest_docs.py` 의 `_cfg_bool` 총 **2건**(`:589 LOCAL_PRIORITY_SORT`, `:593 LOCAL_RAG_MAX_DOCS`) 검출 → 검색기 유효.

→ **사실 기술: X·Y 분기를 ENV 로 하려면 플래그 신설이 선행 조건이다.**

### 5-d. 현재 제거 로직 — `script`·`style`·`noscript` **3종뿐**

```python
soup = BeautifulSoup(raw_content, "lxml")
for tag in soup(["script", "style", "noscript"]):
    tag.decompose()
text = soup.get_text(separator="\n")
text = _re.sub(r"[ \t]+", " ", text)
text = _re.sub(r"\n{3,}", "\n\n", text).strip()
```
- 다른 제거 로직 **0건**(`.extract()` 전수 0건, `decompose()` 2곳이 전부)
- 예외 폴백(`except`)은 `re.sub(r"<[^>]+>", " ", raw_content)` — **태그만 벗기고 크롬은 그대로 남긴다**
- ⚠️ `nav`·`header`·`footer`·`aside` 등 **구조적 크롬은 전혀 제거되지 않는다.** `R12 §5-a` 샘플(airweb.co.kr)이 내비게이션·푸터로 가득한 이유가 이것이다

### 5-e. 분기 vs 복제 판단 재료

| 함수 | 크기 | 프로덕션 실호출 |
|---|---|---|
| `web_results_to_documents` (`ingest_docs.py:260-504`) | **245행** | **2곳** — `ingest_docs.py:611` · `ingest_vector.py:1845` |
| `_load_html_as_text` (`ingest.py:642-716`) | **75행** | **1곳** — `ingest_docs.py:468` |

⚠️ **`ingest_vector.py:1845` 는 R12 가 다루지 않은 두 번째 프로덕션 호출자다.** 복제 갈래를 택하면 **두 호출자 모두** 고려 대상이 된다.
⚠️ 동명이인 주의 — `_load_html_as_text` 가 **두 개**다. `ingest.py:642`(`url` 받아 fetch, bs4 有) vs `ingest_docs.py:146`(`html` 문자열 받음, **bs4 無**, `_clean_text` 만). 시그니처가 다르다.

---

## 6. 수집 직후 게이트 측정 방법

| # | 항목 | 결과 |
|---|---|---|
| **4-a** | `*_filtered.json` 단독 도메인 분포 | ✅ **가능.** 항목 필드 = `title` · **`url`** · `content` · `raw_content` · **`source`** · `content_type` · **`norm_url`** · `raw_bytes` · `fetched_at`. 도메인은 `urlparse(it["url"]).netloc`(fallback `source`). `norm_url` 은 정규화본이라 대조축으로 병용 가능 |
| **4-b** | 껍데기 판별 기준 | R12 산출식 = `2800 <= len(raw_content) < 2900` **버킷 카운트**. 실측 62/69 가 이 구간. 🔴 **이것은 관측된 군집이지 원리 기준이 아니다** — 실체는 *네이버 블로그 iframe 셸*이며, 원리적 판별은 `'<iframe' in raw_content and len(raw_content) < N` 또는 **`</head>` 도달 + 본문 텍스트 길이** 조합이 더 안전하다. 재사용 시 **버킷 상수를 그대로 옮기지 말 것** |
| **4-c** | `raw_content` 길이 분포 | ✅ **가능.** R12 실측 = `min 2800 / p50 2813 / p90 20680 / max 217749`(n=69). 백분위·버킷 모두 산출 가능. 절단 여부는 **`</head>` 도달률**과 `raw_bytes` 대조로 검증(R12 에서 69/69 도달 확인) |
| **4-d** | `ALLOW_SUBDOMAINS` 파급 | 실효값 **True**(CFG 실측). 경로 = `settings_gatekeep.py:377-387` — `base in allow` 실패 시 호스트를 `.` 로 쪼개 **상위 도메인을 순회**한다. `blog.naver.com` → parts `['blog','naver','com']` → i=0 → cand **`naver.com`** → `.env:214` 목록에 존재 → **통과**. 🔴 즉 `naver.com` 1개 항목이 **모든 네이버 서브도메인**을 연다 |

⚠️ **허용 도메인 무접촉 유지.** `catch CA` 대로 **먼저 재고 그다음에 정한다** — 이 차수에서 조정하지 않았다.

---

## 7. 인용 행번호 재확인 — 어긋남 **0건**

| 지시서 인용 | 실물 | 판정 |
|---|---|---|
| `ingest_vector.py:1457-1461` split_mode 판정 | `:1457` ns_web_env / `:1458` ns_loc_env / `:1459` split_mode / `:1461` ns_probe | ✅ 일치 |
| `ingest_vector.py:1463-1470` seen-hash 조기 종료 | `:1463` load_seen… / `:1464` compute_incoming… / `:1465` new_sources / `:1466` if not new_sources / `:1470` return (0,0) | ✅ 일치 |
| `_resolve_ns_for_docs(:343-351)` | `:343` def / `:348-349` getattr / `:350` 분기 / `:351` return | ✅ 일치 |
| `_resolve_persist_dir_strict(:237-)` | `:237` def | ✅ 일치 |
| `vector_search.py:391 _dual_retrieve` · `:360 _split_k` | 동일 | ✅ 일치 |
| `config.py:661-667 _PROTECTED_ENV_KEYS` | 동일 (5키) | ✅ 일치 |
| `ingest_docs.py:385-386` · `ingest.py:677` | `:385` soup / `:386-387` for·decompose / `ingest.py:675` soup / `:677-678` for·decompose | ✅ 일치(R12 판정과 정합) |
| `.env.openai:56-58` venfobel NS 3키 | 동일 | ✅ 일치 |

🔴 **코드 변경 징후 0건.** STOP 6 미발동.

---

## 8. 0건 보고 목록 — 전건 양성 대조 병기

cwd = `writer_project/` (전건 동일). 재귀 검색은 `command grep` + **glob 인용**.

| # | 0건 주장 | 🔴 양성 대조 |
|---|---|---|
| 1 | `ingest_vector.py` 모듈 최상위 NS 캐시 상수 **0건** | 동일 파일·동일 패턴으로 CFG 참조 **24건** 검출(전부 함수 본문 내) ✅ |
| 2 | `_PROTECTED_ENV_KEYS` ENV 확장 코드 **0건** | 동일 명령이 정의 `:661` + 사용 `:679` **2건** 검출 → 검색기 유효 ✅ |
| 3 | 크롬 제거 ENV 플래그 **0건** | 동일 파일 `ingest_docs.py` 에서 `_cfg_bool` **2건** 검출 ✅ |
| 4 | `.extract()` **0건** / `decompose()` **2곳뿐** | 동일 명령·동일 경로로 `get_text(` **9건** 검출 ✅ |
| 5 | `topics/experiential-marketing-media.env` **untracked** | 동일 명령이 `academic-trademark-similarity-consumer.env` 는 **tracked 로 반환** ✅ |
| 6 | `git status --short -- topics/` **0줄**(미노출) | 같은 명령이 직전 차수에 `R12_…md` 를 `??` 로 노출했음 ✅ |
| 7 | `experiential-marketing-media-web` seen-hash 파일 **0건** | 동일 `find` 가 `venfobel-vitamin-web.__seen_sources__.json` **1건** + `chroma.sqlite3` **7건** 검출 ✅ |
| 8 | chroma_store 신규 디렉터리 **0건** | 사전/사후 `ls` 스냅샷 `diff` **0줄**. 목록 자체는 **10 항목**을 정상 열거 ✅ |

---

## 9. Deviation 자진 보고 — **0건**

이번 차수 신규 deviation 0건. 아래 2건은 deviation 이 아니라 **규율 작동·자체 정정** 사례다.

1. **자체 정정 1건** — 후보 ① 1차 측정이 **토픽 프리셋의 `override=True`** 에 가려 무효였다. 프리셋 없는 슬러그(`zz-no-preset-xyz`)로 계층을 분리해 재측정했고, 그 과정에서 **방어가 2겹**임이 드러났다(§3-a).
2. **회피 1건** — `_resolve_persist_dir` · `_resolve_persist_dir_strict` · `_default_chroma_dir` · `_seen_hash_path` 는 **전부 `mkdir(parents=True, exist_ok=True)` 부작용**이 있다. 새 NS 로 호출하면 **디렉터리가 생성된다**(= 쓰기). 지시서 §6-1·§6-3 및 STOP 5 를 지키기 위해 **순수 함수만 호출**했고, 그 결과 §3-a #3 은 **추론(실행 미검증)** 으로 남겼다 — 표에 그렇게 표기했다.

> ⚠️ **#2 는 다음 차수에 인계할 값이다.** *"드라이런이니 안전하다"* 가 이 코드베이스에서는 성립하지 않는다. NS 해석 계열 함수 중 `_resolve_ns` · `_resolve_ns_for_docs` · `_is_web_source` · `sanitize_ns` 만 순수하다.

**새 catch 번호 부여 0건** (지시서 §9 준수).

---

## 10. 실비용 — **$0 실측 · 쓰기 0건**

| 항목 | 건수 |
|---|---|
| 검색 API · LLM · 임베딩 호출 | **0** |
| Chroma 개방/쓰기 | **0** (이번 차수는 sqlite3 조회조차 하지 않음 — 값은 R12 실측 재인용) |
| 파일 쓰기 | **0** |
| 네트워크 | **0** |

**무변경 증명 (self-check #102·#103)**
```
$ diff <사전 ls data/chroma_store> <사후 ls data/chroma_store>
  (0줄)   ← 신규 NS 디렉터리 생성 없음

$ ls -la data/chroma_store/experiential-marketing-media*/chroma.sqlite3
  8월  6 21:04  …-local/chroma.sqlite3
  8월  6 21:04  …-web/chroma.sqlite3      ← mtime 무변동(기존 색인 무접촉)
  8월  5 20:24  …/chroma.sqlite3

$ shasum -a 256 scripts/output/§research-1/Q_FROZEN_20260809.txt
  06e5f81828d0f287e324760a455ab5dc05d1edeb109d951101b155a8218b03a8   ← 불변

$ git status --short   (레포 루트)
   M writer_project/scripts/§paper-writer-1/measure_paper.py    ← 논문 트랙 상주분, 무접촉
   ?? 46건                                                      ← 착수 시와 동일
```
- **NS·프리셋·`.env` 실제 변경 0** — CFG 주입은 전부 `try/finally` 로 원복했고 원복을 `assert` 로 확인
- `web_search.py:848` 무접촉 · `prompts.py` 무수정 · `GATE_KEEP_SOURCES` 점화 안 함 · `seed_web_namespace` 미사용
- 임시 스크립트는 **스크래치패드**에 작성 — 워킹트리 `??` 목록 불변

---

## 11. 값이 부족해 판정이 불가능한 항목 — **1건**

| 항목 | 부족한 이유 |
|---|---|
| **§3-a #3** (split off 시 `persist_directory` 인자 부활) | `_resolve_persist_dir_strict` 가 `mkdir` 부작용을 가져 **읽기 전용 차수에서 호출할 수 없었다.** 코드상 분기(`:252 if split_mode and ns in (ns_web, ns_loc):`)는 명확하나 **실행 검증은 미완**이다. 후보 ① 을 택하지 않는 한 판정에 영향 없다 |

그 밖 후보 5개의 성립·부작용·원복 3칸은 **전부 채웠다**(공란 0).

---

## 12. 이번 차수가 하지 않은 것

```
❌ NS 분리 수단의 선택        ❌ Y 크롬 제거 구현
❌ 허용 도메인 조정            ❌ 수집·색인 착수
❌ 새 catch 번호 · 원장 편집   ❌ 커밋·push (지시받은 뒤)
❌ NS·프리셋·.env 실제 변경
```

**커밋 대기 상태.** `git add -A` **금지**(논문 트랙 미커밋분 상주 — `CLAUDE.md §4` catch AS). 개별 `git add` + `git diff --staged --name-status` 확인 후, **지시받은 뒤** 진행한다.
