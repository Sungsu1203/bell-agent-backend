# OBSERVED — 설정층 실측 대장

> 용도: 명령으로 확인된 설정층 사실만 모음. **세션 시작 시 통독하지 않는다.** 필요할 때 grep.
> 규칙: 추측 금지. 확인 명령이 없는 항목은 §3(열린 항목)에만 둔다. §3 상한 = 7개.
> 최종 갱신 2026-07-30

---

## 1. CFG 미선언 키 — 확정 6건

`core/config.py`의 `Config` dataclass에 필드가 없는 키. 파서 #2(`tools/web_rag/ingest_config._cfg_*`)는
**CFG만 보고 `os.environ`을 안 보므로**, `.env`에 무엇을 써도 경고 없이 코드 기본값으로 떨어진다.

확인 명령: `git grep -n "<KEY>" -- "core/config.py"` → 0건이면 미선언.

| 키 | `.env` | 실효 | 조치 |
|---|---|---|---|
| `RAG_CHUNK_CHARS` | 2400 | 2400 | ✅ **2026-07-30 CFG 필드 추가 — 해소.** `.env` 적용됨 |
| `RAG_CHUNK_OVERLAP` | 150 | **200** | 보류. 청크 값 실험과 함께(단일변수 통제) |
| `MAX_CHUNKS_PER_DOC` | 15(주석) | **0**(비활성) | ✅ 2026-07-30 `.env` 주석 처리. 활성화하면 긴 문서가 15조각에서 절단 |
| `ALLOW_GLOBAL_CLEAR` | 0 | **False**(차단) | ✅ 2026-07-30 `.env` 1→0 — 믿음을 실물에 맞춤. 동작 변화 0 |
| `CLEAR_GUARD_DISABLE` | 0 | False | 그대로 (우연 일치) |
| `CLEAR_ON_FIRST_VECTOR` | 0 | False | 그대로 (우연 일치) |

**반례 1건**: `MIN_CHUNK_CHARS`는 파서 #2를 타지만 **CFG 선언 있음**(`core/config.py:396`, `:575`).
→ `.env:172=50` 정상 적용. "파서 #2 = 항상 무효"가 아니라 "CFG 필드 유무가 갈림길".

---

## 2. 확정 구조

### 2-1. 두 축 — 층(쓰기) × 파서(읽기)

`.env` 4층 로드(STANDARDS §1: L4→L1→L2→L3)는 **env를 채우는 축**이고,
파서는 **채워진 것을 읽는 축**이다. 둘이 교차한다.

- 파서 #1 `core/config._env_*` — `os.environ` 직독. CFG 선언 불요. 4층 정상 작동
- 파서 #2 `tools/web_rag/ingest_config._cfg_*` — **CFG만.** CFG 필드 없으면 4층 전체가 무의미
- 파서 #3 `tools/local_rag._cfg_*` — CFG → env 폴백. 가장 견고 (표준 후보)
- 파서 #4 `agent/vector_search.py:191` — 자체 집합(`"y"` 허용)

→ **STANDARDS §1.3의 확인 절차(L4→L3→L1→runtime)는 파서 #2 키에서 1~3단이 헛수고.** 규범 결손.
→ **CLAUDE.md·STANDARDS.md 어디에도 "CFG 선언된 키만 유효"가 없다.** 규범 갱신 필요.

### 2-2. 청크 크기 결정 경로 — 실측 (2026-07-30)

```
.env RAG_CHUNK_CHARS → CFG 필드 → _cfg_int → split_documents:414 → RecursiveCharacterTextSplitter
```

- `_cfg_int` = `ingest_config.py:52` **단일 정의** (조건부 정의 아님, import 순서 무관)
- `chunk_size` 인자를 **명시로 넘기는 호출부 없음** (`ingest_vector.py:1445`·`:1505`·`:778`·`:1090` 전부 `None` 전달)
  → 설정이 유일한 결정자
- 실측: `.env=800` → 6,400자 문서가 11조각, 각 799자.
  보폭 600 = 800−200 → **`RAG_CHUNK_OVERLAP` 실효 200 실측 확인**(`.env`의 150 미적용)

### 2-3. 청킹은 재분할이 아니라 선점

| 층 | 위치 | 실효 |
|---|---|---|
| 로컬 | `local_rag._type_chunk_params:795` | 확장자별. pptx 80 / md·txt 100~1300 |
| 벡터 | `ingest_vector.split_documents:408` | `RAG_CHUNK_CHARS` = 2400 |

로컬이 먼저 1300 이하로 쪼개므로 벡터층 2400은 통과. → 로그의 web 1,800자 vs local 260자 원인.
⚠️ **`RAG_CHUNK_CHARS`를 내리면 웹만 작아진다.** 로컬을 키우는 레버가 아니다.

---

## 3. 열린 항목 (상한 7)

새 항목을 넣으려면 기존 것을 닫거나 버린다.

| # | 항목 | 다음 한 걸음 |
|---|---|---|
| 1 | `RAG_CHUNK_CHARS` 값 선택 (2400 유지 중) | 유료 재적재 + 검색 품질 비교. 별건 결정 |
| 2 | 로컬 260 vs 웹 1,800 격차 | 로컬 쪽 레버는 `local_rag._type_chunk_params`. 미조사 |
| 3 | `_cfg_int` 키 17개 — 대부분 CFG 미선언 추정 | 필요해지면 `git grep -n "_cfg_int" -- "tools/web_rag/ingest_vector.py"` 1회로 명단 확보 가능 |
| 4 | CRLF 전 줄 파일 2건 (`agent/vector_search.py` 1568 / `tools/local_rag.py` 1656) | `.gitattributes` 명문화 + **단독 커밋.** 기능 변경과 절대 미혼합 |
| 5 | `scripts/output/*` gitignore 미적용 (CLAUDE.md §4는 ignore라 서술, 실제는 관행만) | `.gitignore` 1줄 or 문서 정정 |
| 6 | `MIRROR_STATE_TO_ENV` 상태 미확인 | 켜져 있으면 런타임 state가 env를 덮음 → 설정 스냅샷에 시점 표기 필요 |

---

## 4. 방법 규칙 (실피해로 확정된 것만)

- **설정 키는 대문자 키 문자열로 검색한다.** 코드 변수명으로 하지 않는다.
  양방향으로 샌다 — 변수명으로 `.env`를 찾으면 부재 오판, 변수명으로 코드를 찾으면 소비처 누락.
- **전수 분류에 `head` 금지.** 필터를 걸면 좁힌 만큼 안 보인다.
- **zsh: grep 옵션·`*` 포함 경로는 따옴표 필수** (`--include="*.py"`). CLAUDE.md §3.
  따옴표 없으면 `zsh: no matches found`로 **명령이 실행되지 않는다** — 이 메시지는 "0건"이 아니다.
- **설정값 확인은 `repr()`** — `'0'`(문자열, 위험) vs `False`(정상).
- **부재 판정(0건) 전에** 검색어가 실제 키 이름인지, 명령이 실제로 실행됐는지 역확인.
- 동명 심볼이 흔한 레포다. 만나면 정의 위치를 먼저 확정.
- **`.env` 키를 추가·삭제하면 `env_raw.txt`도 같은 커밋에서.** 값은 동기화 대상 아님(템플릿).
  단, 안전 스위치 계열은 값도 맞춘다. `.env`는 untracked라 명단의 git 기록은 `env_raw.txt`가 유일.

---

## 5. 변경 이력

| 날짜 | 내용 | 커밋 |
|---|---|---|
| 2026-07-30 | STANDARDS.md 줄번호 정정 | — |
| 2026-07-30 | `.env` 고아 키 3건 삭제(`LOCAL_RAG_MIN_CHARS`·`LOCAL_RAG_MIN_CHUNK_CHARS`·`LOCAL_RAG_CHUNK_MODE`, `.py` 소비자 0건) + README·docstring 정정 | `85e16cf8` 등 |
| 2026-07-30 | `RAG_CHUNK_CHARS` CFG 필드 추가 (기본 2400 유지 = 동작 변화 0) | — |
| 2026-07-30 | `.env` 2줄: `ALLOW_GLOBAL_CLEAR` 1→0, `MAX_CHUNKS_PER_DOC` 주석 (동작 변화 0) | 없음(untracked) |
| 2026-07-30 | STANDARDS §1.3 0단 추가 + CLAUDE 파일지도 + OBSERVED 신설 | `47bafc58` |
| 2026-07-30 | `env_raw.txt` 고아 키 3건 삭제 — `.env`와 키 명단 재일치(133→130). 자격증명 3키 플레이스홀더/빈값 재확인 | (동기화 커밋) |
> ⚠️ `.env`는 untracked. `.env` 변경은 이 표에만 남는다 — 만졌으면 같은 커밋에 한 행.