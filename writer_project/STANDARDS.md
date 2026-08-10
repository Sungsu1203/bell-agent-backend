# STANDARDS — 파이프라인 공통 표준

> 측정·환경·보안 공통 규칙. 회사/논문 트랙 무관 적용. `CLAUDE.md §6`에서 이 문서를 지목(역참조).
> 원천: `scripts/output/` 작업 로그에서 재사용 규칙만 승격 (2026-07).
> 원본 박제 위치는 각 섹션 말미 "원본" 줄 참조.

---

## 1. ENV 4-layer 로드 순서

### 1.1 layer 정의 + override
| Layer | 파일 | load 시점 | override | 코드 위치 |
|------|------|----------|---------|----------|
| **L1** 글로벌 .env | `.env` | graph import 시 `_load_dotenv_once` | **False** | `core/config.py:163` |
| **L2** provider overlay | `.env.{provider}` | L1 직후 `_apply_provider_overlay` | True | `core/config.py:120` |
| **L3** topic preset | `topics/{TOPIC_SLUG}.env` | L2 직후 `_apply_topic_preset` | True | `core/config.py:143` |
| **L4** script 별도 load | 각 script start | graph import **전** | True | script L40~50 부근 |

로드 순서(실행 흐름): **L4** (script, graph import 전) → **L1** (글로벌) → **L2** (provider overlay) → **L3** (topic preset).

### 1.2 생존 규칙
- L1의 `override=False` → L4가 이미 set한 변수는 그대로 생존(script env 우선).
- L2/L3의 `override=True` → 글로벌·L4 값을 덮어씀.
- **topic preset 활성 조건**: `os.environ["TOPIC_SLUG"]`가 set돼야 함. `state.topic_slug`만 설정하면 `_apply_topic_preset` 미작동 (자주 놓치는 결손).

### 1.3 다른 작업 진행 시 ENV 확인 절차
1. **CFG 선언 확인이 0단**: `git grep -n "<KEY>" -- "core/config.py"` → 0건이면
   파서 #2(`_cfg_*`) 경로에서 `.env`는 무효. 2~4단 생략하고 코드 기본값을 본다. 
2. **L4 확인**: script의 `.env` load 명시 여부 + 어느 파일 load.
3. **L3 확인**: `topics/{TOPIC_SLUG}.env` override 여부 (TOPIC_SLUG env var 활성 필수).
4. **L1 확인**: 글로벌 `.env` base 값.
5. **runtime 확인**: `python -c "import core.config as c; print(c.CFG.<변수>)"`.

### 1.4 새 토픽 작성 표준
- `topics/_template.env` 복사 + 파일명 = `TOPIC_SLUG`와 동일.
- 필수: `TOPIC_TITLE`, `TOPIC_SLUG`, `BLOCKAGI_OBJECTIVE_1`.
- 검증용 토픽: `SKIP_VERTEX_SEARCH=0` 명시.

### 1.5 측정 driver 작성 표준
- L4 load: `.env.{provider}` only (override=True).
- `$env:TOPIC_SLUG` 명시 set (L3 활성 보장).
- env capture log 작성 (콘솔 L1~10).
- `[Config] 토픽 프리셋 로드` 메시지 확인 (L3 활성 evidence).

### 1.6 새 `.env.*` 파일 추가 시 보안 점검 절차
1. `git check-ignore -v <file>` 로 ignore 매칭 패턴 확인.
2. `git log --all --oneline -- <file>` 로 history 점검.
3. 마스킹 박제 갱신.
4. 점검 결과 박제.
- rotate 필요 trigger: gitignore 누락 발견 / history commit 발견 / remote push 노출 발견.

> 원본: `scripts/output/§14-3/env_flow_matrix.md`

---

## 2. 측정 metric 정의

### 2.1 ref source 5분류 (robustness — silent 분류 누락 방지)
분류 기준 = `state.references.docs[i].source` 값.

| source | 정의 |
|--------|------|
| `vertex_grounding` | Gemini 내부 Google Search grounding_metadata → references append |
| `web` | Naver/Tavily 등 외부 search API 명시 호출 결과 |
| `local` | ChromaDB local index retrieve 결과 |
| `other` | 명시적 source 값 있으나 위 3개 외 (예: `api`, `manual`) |
| `unknown` | source 키 부재 / None / 빈 문자열 |

- `vertex_grounding` vs `web` 핵심 차이: 전자는 LLM 응답 생성 중 자동(응답 부산물), 후자는 `web_search` 노드 명시 호출.

### 2.2 진입·판정 임계
- **Tier2 dry-run 진입 조건**: `vertex_grounding count > 0` (0 → 토픽 niche 또는 Google Search index 약함 → patch 효과 측정 불가).
- **변동성 임계**: `vertex_grounding count`의 N=3간 `CV > 30%` → 토픽 unstable, patch 효과 vs noise 분리 불가 → Tier1 fallback / 재시도 결정.
- **한국어 grounding 주의**: Google Search 한국어 corpus가 영어 대비 grounding metadata를 적게 반환할 수 있음 → 한국어 토픽은 별도 검증.

**측정 설계 catch 포인터** (2026-08-10) — 아래 2건은 **`../CLAUDE.md §9` 에 이미 등재**돼 있다.
중복 등재하지 않고 소재만 가리킨다.
- **catch CL** (`CLAUDE.md:305`) — 요약·대표값·첫 일치를 전수 대신 쓰면 답이 달라진다.
  판정에 쓰는 값이 **전수인지 표본인지**를 먼저 밝힌다.
- **catch CM** (`CLAUDE.md:323`) — 판단 불가는 **제3의 칸**에 넣는다. 어느 쪽으로도 밀지 않는다.
  미확정 칸의 크기가 결론을 바꿀 만하면 닫으러 가되, **기준이 아니라 자료를 바꾼다**.

> 원본: `scripts/output/§14-3/metric_definitions.md`

---

## 3. Chroma reset 정책 (reset · 읽기 접근)

### 3.1 reset 정책

- **reset 책임 = driver**. graph의 `ensure_vector_store_cleared_once`는 `_CLEARED_ONCE_KEYS`/`_CLEARED_RUNTIME_KEYS` 가드로 **process당 1회만** 동작 → multi-invoke 측정 환경에선 사실상 no-op.
- **reset 단위 = `ns_web`만, `ns_local`(PDF chunks) 보존**:
  1. 매 run 재인덱싱 시 누적 오버헤드 (예: 5 sections × 3 runs × 2 commits = 30회 = +15분).
  2. PDF chunks는 patch 영향 없음 (vertex grounding 변경은 web/vertex 경로만).
  3. `local_first + 0.33` 정책 유지 → 측정 동질성 보장.
- **reset 시점 = multi-turn 시퀀스 1회 전체 시작 전 1번** (`_run_single` 진입 직후, `graph.invoke` 전). 매 turn마다 reset하면 앞 turn의 web search 결과가 다음 turn retrieve에서 사라져 invariance 붕괴.
- **격리 방식** (측정 시작 전 확정):
  - (권고) **subprocess 분리** — graph/LLM/Chroma handle 완전 격리, spawn overhead ~3~5s는 측정 elapsed에서 제외.
  - (대안) in-process guard 우회 시 clear 대상 3종: `_CLEARED_ONCE_KEYS` · `_CLEARED_RUNTIME_KEYS` · `_VS_CACHE` (해당 `(persist_dir, ns_web)` key discard/pop 후 `clear_vector_store`).
- 측정 박제 시 "ns_web reset 정책: …" 명시.

> 원본: `scripts/output/§14-2/phase_b_reset_policy.md` (실경로 `scripts/output/phase_b_reset_policy.md`)

### 3.2 읽기 접근 — PersistentClient는 쓰기를 만든다

- **읽기 전용 조회는 `sqlite3 <path> -readonly`.** `chromadb.PersistentClient(path=...)`는
  경로가 존재하지 않으면 **그 자리에 빈 DB를 생성**한다. 조회하려다 오염원을 만든다.
- 전례 2건 (catch AG): 2026-07-31 09:46 · 2026-08-02 09:13. 둘 다 루트 경로 오지정.
  격리 파일 `data/chroma_store/_stray_*.sqlite3.bak` — 사고 기록물이므로 삭제 금지.
- **사고 구분자는 `collections` 개수다.**
  - `collections` = 0 → 경로 오지정 (컬렉션 생성조차 안 됨)
  - `collections` ≥ 1 이고 `embeddings` = 0 → 색인 시도 중 중단
  - ⚠️ **파일 크기는 구분자가 아니다.** 빈 Chroma 스키마는 항상 188,416B이며,
    세 파일이 같은 크기인 것은 "셋 다 데이터 0"만 뜻한다.
- ⚠️ `PersistentClient` 자체는 **macOS에서 정상 작동한다** (2026-08-02 실측 `count=416`).
  `tools/diagnose_richness.py` 주석의 panic 기술은 Windows 시절(2026-05-06) 기록이다 — catch BA.
  우회는 유지하되 "막혀 있다"로 읽지 말 것.
- ⚠️ `diagnose_richness.py`의 `namespaces=N`은 **`-web`/`-local` 접미사 이름 필터**다.
  내용 판정이 아니므로 "빈 NS의 증거"로 쓰면 틀린다.
- 🔴 **import 는 실행이다 (catch CN, 2026-08-09 §research-1 S4-c)** — `__main__` 가드가 없는 probe
  모듈을 `import` 하면 모듈 본문이 전부 돌아 **산출물이 덮어써진다.** 실물 — `import probe_s2_agg`
  한 번에 R9 집계가 재실행되고 `_s2_final.json` 이 재생성됐다. 확인 = `python -c "import <mod>"`
  출력 **0줄**.
  · **부수 관측(양성 정보)** — 재생성분 sha256 이 동일해 **R9 파이프라인이 결정론적**임이 확인됐다.
  · ⚠️ 단 **원본 byte 일치는 미증명**이다(사전 해시·백업 부재, 크기 일치만 확보). 크기 일치를
    동일성으로 읽지 않는다(§3.2 상단·`STANDARDS §3.2` 빈 Chroma 188,416B 전례).
  · `catch AG`(`PersistentClient` 가 경로 오지정 시 빈 DB 를 **만든다**)와 **동형** — 둘 다
    *"조회하려다 오염원을 만든다"*.

> 원본: `scripts/output/§ad-track-1/step3c_close_§ad-track-1.md` §1.2~1.3

---

## 4. `_PROTECTED_ENV_KEYS`

reload 시 `.env` 정적 default가 driver-set 값을 flip하는 것을 차단 (안 하면 provider/model/topic이 뒤집힘).

### 4.1 보호 5키
```python
_PROTECTED_ENV_KEYS = (
    "LLM_PROVIDER",         # MUST — overlay 분기 결정
    "LLM_MODEL",            # MUST — vertex_web_search 가 os.getenv 로 직접 read
    "TOPIC_SLUG",           # MUST — topic preset 분기 결정
    "SKIP_VERTEX_SEARCH",   # MUST — vertex grounding gate
    "MIRROR_STATE_TO_ENV",  # 권장 — driver intent 보호 (defense-in-depth)
)
```

### 4.2 snapshot / restore 원칙·시점
- **의미**: snapshot 값이 str이면 restore(driver 명시 intent 보호), `None`이면 skip(.env 값 허용 = hot-reload 의도 보존).
- **시점**: `reload_config_inplace()`의 `load_dotenv(override=True)` **직전** snapshot, **직후 + `_apply_provider_overlay`/`_apply_topic_preset` 직전** restore.
- → overlay·preset이 driver-restored `LLM_PROVIDER`/`TOPIC_SLUG` 기반으로 정상 분기.
- patch 위치: `core/config.py reload_config_inplace` (L667).

> 원본: `scripts/output/§14-8/B-3_audit.md` (§3-2 `_PROTECTED_ENV_KEYS` 확정 부분)

---

## 5. credential 노출 감사

### 5.1 현재 상태 감사 (2-명령)
1. `git ls-files <env files>` → tracked 여부 (empty = 미tracked).
2. `git check-ignore -v <file>` → ignore 매칭 규칙·source 확인.
   ⚠️ **규칙이 파일에 적혀 있는 것과 작동하는 것은 다르다.** 반드시 실행해 매칭 규칙:라인을 눈으로 본다.

### 5.1-a 🔴 이력 감사 — **3축** (§research-1 R1b 개정, 2026-08-05)

> **구 절차는 `git log -S "<현행 키 prefix>"` 단일 축이었고, 그것이 실제 노출을 놓쳤다.**
> 특정 키 값으로 검색하면 **"그 키"의 노출만** 판정된다. 이전 세대의 키는 원리적으로 안 걸린다.

| 축 | 명령 | 잡는 것 | 우선 |
|---|---|---|---|
| **① 파일명** | `git log --all --oneline --name-status -- '.env*' 'env*' '*.bak' '*secret*' '*credential*'` | **세대 무관.** 키 형식과 무관하게 파일 단위로 포착 | 🔴 **1순위** |
| **② 형식 정규식** | `git log --all -S'AIzaSy'` 등 → 후보 커밋 추출 | prefix가 있는 키만 | 2순위 |
| **③ blob 직독** | `git show <commit>:<path> \| grep -cE '<형식>'` | ①②가 지목한 blob의 **실제 키 존재 확정** | 필수 마감 |

형식 정규식(길이 하한을 반드시 붙여 placeholder와 구분):
`AIzaSy[A-Za-z0-9_-]{30,}` · `sk-proj-[A-Za-z0-9_-]{40,}` · `sk-ant-api03-[A-Za-z0-9_-]{40,}` · `tvly-[A-Za-z0-9]{20,}`

**⚠️ ①이 1순위인 이유 — prefix 없는 키는 ②로 영원히 안 걸린다.**
실제 사고에서 새어나간 것은 키 한 줄이 아니라 **`.env` 파일 전체**였다.
`NAVER_CLIENT_SECRET` · `SERPAPI_API_KEY` 처럼 식별 가능한 접두어가 없는 값은
정규식으로 찾을 방법이 없다. → **"어느 키가 샜나"가 아니라 "어느 파일이 커밋됐나"로 묻는다.**

**⚠️ ③이 필수인 이유 — pathspec 함정 (실사고, §9 계열)**

```bash
git rev-list --all | while read c; do git grep -lE '<형식>' "$c" -- . ; done
#                                                                  ^^^
#  `-- .` 는 cwd 기준. writer_project/ 에서 실행하면 레포 루트의 env_text.txt 는 범위 밖.
#  → 에러 없이 0건. 그것을 "이상 없음"으로 읽었다.
```

`git show <commit>:<path>` 는 pathspec이 개입하지 않는다. **판정은 이 명령으로 마감한다.**
CLAUDE.md §9 "도구 출력은 계산 방식을 확인한 뒤 해석한다"의 재현 사례.

**⚠️ 오탐 걸러내기** — `AKIA`(AWS) 는 vendored 라이브러리·웹수집 JSON에서 우연히 나온다.
길이 하한 정규식(`AKIA[0-9A-Z]{16}`)으로 형식을 확인하기 전에는 노출로 판정하지 않는다.

### 5.2 마스킹 규칙
- 박제 시 key 값 전체 노출 금지 — **prefix 4~8자 + `***`만**.

### 5.3 provider 키 분리 convention
- LLM provider 키(openai/anthropic 등) = `.env.{provider}` overlay 위치.
- search backend 키(tavily/naver 등) = 글로벌 `.env` 위치 (LLM_PROVIDER와 decoupled).

### 5.4 rotation·scrub 판단
- rotation 판단 전 **live/idle 분류** 선행 (노출 자체가 부재하면 rotation 의무 없음).
- rotate trigger: gitignore 누락 / history commit 발견 / remote push 노출.
- **STOP 게이트**: history scrub(`git filter-repo` 등)은 **rotation 완료 + collaborator 0명 또는 사전 동의 + 백업 push** 이후에만. read-only 감사 단계에서 실행 금지.

#### 5.4-a 🔴 이 레포의 history scrub 판정 = **기각** (§research-1 R1b, 2026-08-05 박제)

> 키를 회전하면 유출된 옛 키는 **무효 문자열**이 된다. 이력 재작성은 그 죽은 문자열을 가릴 뿐이다.
> `filter-repo`는 **이후 모든 커밋 해시를 변경**하는데, 이 레포는 `scripts/output/` 분석 문서 ·
> `ARCHITECTURE.md` 부록 A · `R1_FINDINGS.md`(기준 HEAD `53a76a88`) · WORKBOARD ·
> catch 로그가 **커밋 해시를 근거로 참조**한다.
> → **1년치 측정 기록의 추적성이 파손되고, 얻는 것은 0.** 비용 >> 이득으로 기각.

- 이 판정은 `bell-agent-backend` · `Sungsu1203/blockagi`(포크) **양쪽 모두**에 적용된다.
- **재론 금지.** 대응은 ① 키 회전 ② HEAD 정리 ③ `.gitignore` 보강 3종으로 마감한다.
- 조건이 바뀌는 경우(레포 public 전환 등)에만 재검토.

> 원본: `scripts/output/§14-9-A1/credential_exposure_audit.md` (§1-b/1-c 감사 명령 + §2 convention + §3 rotation 체크리스트)

## 6. provider별 venv 분리

| venv | 용도 | 의존성 |
|---|---|---|
| `../.venv_vertex` | 논문/vertex 트랙 | `requirements.vertex.txt` |
| `../.venv_openai` | ad/openai 트랙 (2026-07-31 신설 — catch I) | `requirements.openai.txt` |
| `../.venv_emb` | 로컬 임베딩 전용 (e5-large) | — |

- ⚠️ `.venv_vertex`에 `langchain_openai`가 없다. `LLM_PROVIDER=openai`로 실행하면
  임베딩 생성자에서 실패한다. **provider와 venv는 반드시 짝을 맞춘다.**
- `.env` 파일도 provider별 분리 (§1.5 측정 driver 작성 표준 연동).
- macOS·Windows 공통 동작. 플랫폼 전용 아님.
- 🔴 **착수 전 venv 를 트랙 규약과 대조한다 (catch CO, 2026-08-10 §research-1 S4-c)** — §research-1 은
  ad 트랙(`experiential-marketing-media`)이므로 `.venv_openai` 가 정본인데 S4·S4-b 를 `.venv_vertex`
  로 돌렸다. **산출물 서두에 실행 환경 캡처 칸이 없어 3차수 뒤에야 발견**됐다.
  · 영향은 **관측되지 않았다** — 두 venv 의 python 3.11.6 / bs4 4.14.2 / lxml 6.0.2 / libxml2 2.14.6
    **직접 확인** + `body_meta` 43 URL 실측 동일 + R9 집계 전항 재현. "영향 0" 이 아니라
    **"영향 관측되지 않음"** 으로 적는다.
  · ⚠️ 파서만 쓰는 작업이라 무해했다. **LLM 호출이 개입하면 실패 원인이 된다.** → §7 연동.

> 원본: `scripts/output/§ad-track-1/step2_close_§ad-track-1.md` (catch I) ·
> `scripts/output/§research-1/R10c_POWER_CONTROL.md` §0 (catch CO)

---

## 7. 측정 산출물 서두 필수 기재

모든 측정 산출물 서두에 **실행 환경을 캡처**한다.

- **cwd** · **venv 경로** · **python / 주요 라이브러리 버전**(파서를 쓰면 `bs4`·`lxml`·`libxml2`)

> 근거: `catch CO` — 환경 캡처 칸이 없어 venv 트랙 규약 위반이 **3차수 뒤에야** 발견됐다.
> S4 계열에서는 무해했으나(파서 스택 동일함을 사후 직접 확인) **LLM 호출이 개입하는 작업에서는
> 실패 원인이 된다.** §1.5 측정 driver 작성 표준 · §6 provider별 venv 분리와 연동.
>
> ⚠️ 사후에 "영향 없음"을 확인했더라도 **"영향 0"이 아니라 "영향 관측되지 않음"**으로 적는다.
> 캡처가 없었다는 절차 결함 자체는 남는다.

## 8. 침묵 실패 대비 — 대조 쌍 의도 설계

**0건이 나올 수 있는 산출 경로는 같은 값을 다른 경로로도 산출**하도록 짠다.
두 값이 어긋나면 침묵 실패가 드러난다.

> 근거: §research-1 S4-h — **리스트를 기대하는 순회 함수에 문자열을 넘기면** 파이썬이 `str` 을
> 이터러블로 취급해 **글자 단위로 순회**한다. 그러면 다중 문자 항목이 하나도 걸리지 않아
> **예외 없이 0건**이 나온다(`hint_detail(el)` vs `hint_detail([el])`). 산출은
> `매칭 URL 0 / 43` 이라는 완전히 그럴듯한 값이었다.
> 같은 실행의 다른 경로 값(**188**)과 모순이라 발견됐다. **그 경로가 없었으면 조용히 마감되고
> STOP 게이트도 발동하지 않았다**(전수 총계가 505 아닌 317이 되어 계층 하나가 통째로 사라짐).
>
> ⚠️ 이번 발견은 **우연히 두 경로가 있었기 때문**이다. 우연에 기대지 않는다.
> `CLAUDE.md §9` *"양성 대조 없는 0건은 근거가 아니다"* 의 **실행 절차판**이다.
>
> **절차 2항**
> 1. 0건을 산출한 경로에는 **반드시 걸려야 하는 입력**을 하나 넣어 1건 이상 나오는지 확인한다.
> 2. 동일 대상에 대한 두 경로의 값이 있으면 **대조한다.** 없으면 만든다.
>
> 인접 자산 — `ad/README-dev-2.md` "디버깅 표준 박제(영구 박제, §14-3 origin)" 의
> *추정 기반 진단 위험성* · *사전 확인(B) 가치* 와 같은 계열.
> (숫자 catch 네임스페이스라 별도 관리 — `ad/GUARDRAILS.md` 파일 지도 참조)

> 원본: `scripts/output/§research-1/R10i_SCOPE_CLOSE.md` §7 · `R10c_POWER_CONTROL.md` §0
