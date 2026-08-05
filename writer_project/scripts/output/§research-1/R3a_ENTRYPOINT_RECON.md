# §research-1 R3-a — 진입점 정찰 (배치 2)

- 일자: 2026-08-05
- 성격: **박제(tracked)**. 읽기 전용 정찰
- 선행: `R2b_DECISION_1_3.md` (결정 1·3 확정, 결정 2 결론)
- 비용: **$0** — LLM 호출 0 · 네트워크 0 · 코드 변경 0 · `git add` 0 · 커밋 0
- python 실행 = **T2-③ 1건만** (`_canonicalize_src_for_dedup` 직접 호출, 순수 문자열 함수)

---

## 0. 한 줄 요약

> **T2가 R2b의 전제를 하나 뒤집었고, T3가 예산 판정선을 위협하고, T4가 (a)의 공수를 확정했다.**
> R3-1은 진행 가능하나, **착수 전 챗 결정 3건**이 생겼다.

| 항목 | 결과 |
|---|---|
| T1 파서 정본 | ⭕ 재수립 완료. **H3 통과 결함 실재** (현 아웃라인 무영향) |
| T2 dedup | 🔴 **가설 기각 + R2b 전제 정정 1건.** canon 단독 판정은 오답이었다 |
| T3 비용 | 🔴 **이론 상한 ≈ $1.33 — $1 판정선 초과.** 실물 앵커로는 ≈$0.33 |
| T4 state | ⭕ 확정. **선례 드라이버는 노드를 안 부른다**(graph.invoke) — R2b §2-2 ② 유지 |

> 🔴 **이 문서는 배치 3(T5·T6)에서 정정되었다. §2-5 · §3-4 · §3-5 는 stale이다.**
> 반드시 **§8 부기(배치 3)** 를 먼저 읽을 것. 정정 3건 + 신규 발견 2건이 있다.
>
> 🔴 **그리고 §9 = R3-1 실행 결과(run1~4). 판정 = FAIL(D4 ②), 조건 조정 0.**
> §8은 정찰(예측), §9는 실행(실측)이다. 상충 시 **§9가 우선.**
> 핵심 수치: **web 통과율 28건 중 1건(3.6%)** — §9-6. 실질 코퍼스는 local 302청크뿐.

---

## 1. T1 — 파서 정본 재수립

### 1-0. 출처 재수립 절차

이전 배치의 `report_builder.py:303-315` · `:307` 기재는 **폴백(`||`)이 섞인 명령의 산물**이라 근거를 폐기하고 새로 세웠다(catch BB). 이번에는 폴백 없이 2단계로 확정한다.

```
ls -l report_builder.py
  → -rw-r--r--  16218  6월  1 15:57 report_builder.py     ← writer_project 루트 (D1 일치)
sed -n '295,320p' report_builder.py                        ← 폴백 없음, 단독 실행
Read report_builder.py offset=270 limit=90                 ← 행번호 부착 대조
```

두 출력이 **같은 본문**을 냈다. 아래 라인번호는 행번호 부착 판독 기준이다.

### 1-1. 정본 라인

| 대상 | 라인 | 실물 |
|---|---|---|
| `build_final_report()` 시그니처 | `:279-284` | `-> Tuple[str, List[str]]` = `(final_path, missing_titles)` |
| 아웃라인 로드 | `:295-301` | `read_outline(..., allow_fallbacks=False)` |
| **`titles` 생성부** | **`:304-316`** | 선언 `:304`, 루프 `:305-316` |
| **H2 판정** | **`:309`** | `if not ls.startswith("##"): continue` |
| **접두 절단** | **`:314`** | `s = ls[2:].strip()` |
| 섹션 병합 루프 | `:324-335` | `_load_section_body()` → 실패 시 `missing.append(t)` `:327` |
| `_source_dirs()` | `:162-176` | — |

### 1-2. (1) H3 통과 여부 — **통과한다. 결함 실재**

`:309`는 `startswith("##")`이므로 `"### 소제목"`도 **True**가 되어 통과하고, `:314`의 `ls[2:]`가 앞 2자만 잘라 **`"# 소제목"`**을 제목으로 만든다.

- 판정 근거 = `:309`·`:314` 실물 라인 (문자열 슬라이스 논리, 실행 불요)
- **현 아웃라인 무영향** — 전제상 H3 0건. `## `로 시작하는 7줄뿐
- 🔴 **R3-1 운용 제약**: 아웃라인을 손대게 되면 **H3 금지**. 넣는 순간 `"# ..."`가 8번째 섹션 제목으로 들어가 `missing_titles`에 잡힌다 → D4 판정선 오염

### 1-3. (2) `titles` 생성부 정확한 범위 — `:304-316`

`:306-307`이 빈 줄을 건너뛰므로 아웃라인의 **마지막 줄 개행 없음**(전제)은 무해하다. `splitlines()`는 개행 없는 마지막 줄도 원소로 낸다.

### 1-4. (3) `_source_dirs()` / `CFG.REPORT_SOURCES` 기본값

```python
# report_builder.py:162-176
def _source_dirs() -> List[str]:
    raw = _get_cfg_attr("REPORT_SOURCES", None)
    if isinstance(raw, str): s = raw.strip()
    else:                    s = (os.getenv("REPORT_SOURCES") or "").strip()
    if s: ... return items or ["sections", "content", "chapters"]
    return ["sections", "content", "chapters"]
```

| | 값 | 출처 |
|---|---|---|
| `CFG.REPORT_SOURCES` 기본값 | **`""`** (빈 문자열) | `core/config.py:646` `_env_str("REPORT_SOURCES", "")` |
| 토픽 env 지정 | **없음** (grep 0건) | `topics/experiential-marketing-media.env` |
| **실효 우선순위** | **`["sections", "content", "chapters"]`** | `:175`/`:176` 양쪽 폴백 |

⚠️ `:168-172` 분기 주의 — `CFG.REPORT_SOURCES`가 `str` 타입이면(빈 문자열이어도) **ENV `REPORT_SOURCES`를 아예 안 읽는다.** `core/config.py:390`이 `REPORT_SOURCES: str`로 선언되어 있으므로 `isinstance(raw, str)`는 항상 True. ~~**ENV 경로는 실질 사문(死文)이다.**~~ R3-1에서 소스 디렉터리를 바꾸려면 ENV가 아니라 CFG를 봐야 한다. (기본값으로 진행하면 무관)

> 🔴 **정정 (W-1, 2026-08-05 실측) — 위 취소선 문장은 틀렸다.**
> **`REPORT_SOURCES`는 사문이 아니다.** 죽은 것은 `_source_dirs()` 내부의
> `else: os.getenv(...)` **폴백 분기 하나**뿐이며, ENV는
> `core/config.py:646` `_env_str("REPORT_SOURCES", "")` 를 통해 **CFG로 정상 진입한다.**
>
> 실측(별도 프로세스 2회):
> ```
> (기본)                    CFG.REPORT_SOURCES=''         → _source_dirs()=['sections','content','chapters']
> REPORT_SOURCES=sections   CFG.REPORT_SOURCES='sections' → _source_dirs()=['sections']
> ```
> → **C5 게이트가 3곳 하드코딩이었다면 ENV 변경 시 게이트만 조용히 어긋났을 것이다.**
> 그래서 `run_r3a_straight.py:_inventory_sections()`는 `_source_dirs()`를 **호출**한다.
> 소비자(`report_builder.py:185`)와 같은 소스를 봐야 어긋나지 않는다.
>
> ⚠️ 이 정정은 §9 "기록된 것은 현재가 아니다"의 **분기 판독** 판(版)이다 —
> 분기 조건(`isinstance`)만 보고 **그 값이 어디서 채워지는지(config.py:646)를 안 봤다.**

### 1-5. 🔴 부수 발견 — 저장/로드 슬러그 1차 불일치 (D4 직결)

| | 규칙 | 근거 |
|---|---|---|
| **저장** | `section_slug_candidates(title)[0]` = **`"<n>-<base>"`** (번호 **포함**) | `content_utils.py:80-89` |
| **로드 1차** | `f"{section_slugify(title)}.md"` = **`"<base>"`** (번호 **제거**) | `report_builder.py:184` + `utils/text_utils.py:259-266` |
| **로드 2차 폴백** | `find_section_path(title)` → `section_slug_candidates()` **전량 순회** | `report_builder.py:191-199` + `core/paths.py:238-243` |

→ **1차는 반드시 빗나가고, 2차 폴백이 흡수한다.**
실물 증거: `sections/venfobel-vitamin/1-executive-summary.md` — 파일명은 번호 포함인데 `section_slugify("1. Executive Summary")`는 `executive-summary`(번호 없음)를 낸다.

⚠️ **2차 폴백은 `sections/` 한 곳만 본다** (`core/paths.py:238` `sections_dir()`). `_source_dirs()`의 `content`/`chapters`는 폴백 대상이 아니다. R3-1은 `sections/`에 쓰므로 **무해**하나, 이 경로에 의존한다는 사실을 박제한다.

---

## 2. T2 — dedup 정규화 (3단, ①→②→③)

### 2-1. ① venfobel 실물 직독 — 🔴 **쌍 발견 → 가설 기각**

`sections/venfobel-vitamin/*.refs.json` **2건** (섹션 2개분).

`일반의약품-종합비타민-....refs.json` 안에서:

| marker | label | url / source |
|---|---|---|
| **1** | `종근당_팩트북.pdf (4, Index: 4, Chunk 1)` | `file:///.../%EC%A2%85...팩트북.pdf` **`#part=4&index=4&chunk=1`** |
| **5** | `종근당_팩트북.pdf (5, Index: 5, Chunk 1)` | `file:///.../%EC%A2%85...팩트북.pdf` **`#part=5&index=5&chunk=1`** |

**같은 파일, 다른 프래그먼트, 둘 다 생존.**

→ 판정 비대칭 규율 적용: **쌍이 있으므로 가설 기각**(= "같은 파일의 다른 청크가 하나로 병합된다"는 가설이 틀렸다). 이건 무증거가 아니라 **적극적 반증**이다.

참고 — 다른 섹션 파일에서는 `종근당_팩트북.pdf (4,...)`와 `종근당_전략가설(tmp).pdf (2,...)`가 나와 **다른 파일**이었다. 쌍은 위 1건이 유일하다. 표본이 섹션 2개(마커 10건)로 작으므로 **"1건뿐"을 빈도 결론으로 쓰지 않는다.**

### 2-2. ② `_canonicalize_src_for_dedup()` 본문 (`utils/refs.py:150-178`)

```python
:161  s = re.sub(r"__v_\d+_\d+$", "", s)      # 버전 접미사 제거
:164  pu = urlparse(s)
:165  if pu.scheme and pu.netloc:             # ◀ 분기 조건
:166-169   host lower / :80 :443 제거 / www. 제거      ← 플래그 무관, 항상
:170-172   path 유지(대소문자 보존), 끝슬래시 1개 제거
:174       return urlunparse((scheme, host, path, "", "", ""))   # query·fragment 제거
:176  return str(Path(s)).replace("\\","/").lower()   # ◀ 로컬 경로 분기 (전체 소문자)
```

🔴 **`file:///...`는 `netloc`이 빈 문자열이라 `:165`가 False가 되어 로컬 경로 분기(`:176`)로 간다.**
`:176`은 프래그먼트를 **제거하지 않는다.** ①의 관측이 여기서 설명된다.

| 처리 | `http(s)://` 분기 (`:166-174`) | `file://` 분기 (`:176`) |
|---|---|---|
| **프래그먼트** | 🔴 **제거** | ⭕ **보존** |
| **percent-encoding** | 디코드 안 함 | 디코드 안 함 |
| **대소문자** | host만 lower, **path 보존** | **전체 lower** |
| **www** | 항상 제거 | 해당 없음 |
| **query(utm 등)** | 제거 | 보존(경로 문자열의 일부로) |

⚠️ **정규화가 두 스킴에서 정반대다.** 웹은 프래그먼트를 지우고 파일은 남긴다.

### 2-3. ② 병행 — `tools/web_rag/utils.py:749-754` 플래그 6종

| 플래그 | 기본값 |
|---|---|
| `_URL_STRIP_DEFAULT_PORTS` | `True` |
| `_URL_NORMALIZE_DEFAULT_INDEX` | `True` |
| `_URL_CANONICALIZE_TRAILING_SLASH` | `True` |
| `_URL_SORT_QUERY` | `True` |
| `_URL_CANONICALIZE_AMP` | `True` |
| `_URL_TREAT_WWW_EQUIV` | **`False`** |

- 전부 **모듈 import 시점에 `_cfg_bool()`로 1회 평가되어 동결**(`:749-754`가 모듈 최상위). 런타임 ENV 변경 무반영
- 🔴 **그러나 `utils/refs.py:150`은 이 6종을 전혀 참조하지 않는다.** 별개 체계다. `refs.py`는 `re`/`urlparse`/`Path`만 쓴다. **웹 정규화 플래그를 조정해도 refs dedup은 안 바뀐다**

### 2-4. ③ 함수 직접 호출 판정

**게이트 실증 먼저** (CLAUDE.md §1 — 선언이 아니라 실행으로):

```
$ env -u TOPIC_SLUG ../.venv_openai/bin/python probe_dedup_canon.py
  File ".../probe_dedup_canon.py", line 4, in <module>
    assert os.environ.get("TOPIC_SLUG"), "TOPIC_SLUG 미지정 — 토픽 프리셋 오적용 방지 게이트"
AssertionError: TOPIC_SLUG 미지정 — 토픽 프리셋 오적용 방지 게이트
```
`:4`에서 죽었고 **`sys.path` 조작·`utils.refs` import에 도달하지 않았다.** 게이트가 무거운 import 앞에 있음이 실증됨.

본실행 (`TOPIC_SLUG=experiential-marketing-media`, `../.venv_openai/bin/python`):
```
[Config] LLM provider overlay 로드: .../.env.openai
[Config] 토픽 프리셋 로드: .../topics/experiential-marketing-media.env
```
→ 로드된 프리셋이 §ad/§research 공유 토픽임을 육안 확인(CLAUDE.md §1).

| # | 케이스 | 입력 차이 | 반환값 | 판정 |
|---|---|---|---|---|
| **A** | `file://` 같은 파일 다른 청크 (**실물 marker 1 vs 5**) | `#part=4&index=4&chunk=1` vs `#part=5&...` | **상이** | ⭕ 둘 다 생존 |
| **B** | `file://` encoded vs decoded 동일 파일 | `%EC%A2%85...` vs `종근당_팩트북` | **상이** | 🔴 **같은 파일이 2건으로 남는다** |
| **C** | `file://` 경로 대소문자 | `/refs/` vs `/REFS/` | **동일** | ⭕ 병합 |
| **D** | 웹 www 유무 | `www.dailypharm.com` vs `dailypharm.com` | **동일** | ⭕ 병합 |
| **E** | 웹 utm 유무 | `?utm_source=x&utm_medium=y` | **동일** | ⭕ 병합 |
| **F** | 웹 끝 슬래시 | `/7806/` vs `/7806` | **동일** | ⭕ 병합 |
| **G** | 웹 프래그먼트 (A의 대조군) | `#chunk=1` vs `#chunk=8` | **동일** | 🔴 **A와 정반대** |
| **H** | 웹 path 대소문자 (C의 대조군) | `/user/` vs `/USER/` | **상이** | 🔴 **C와 정반대** |

빈/`None` 입력 → `''` (예외 없음).

관측된 키 예시:
```
file:///Users/.../refs/%EC%A2%85....pdf#part=4&index=4&chunk=1
  → file:/users/.../refs/%ec%a2%85....pdf#part=4&index=4&chunk=1
```
⚠️ `file:///` → **`file:/`** — `Path()`가 연속 슬래시를 접는다. 키 전용이라 무해하나, **이 문자열을 URL로 되쓰면 깨진다.**

### 2-5. 🔴 R2b 전제 정정 — canon 단독 판정은 오답이다

`canon()`은 dedup 키의 **일부**일 뿐이다. 실제 dedup은 `merge_refs._doc_sig` (`utils/refs.py:275-289`):

```python
:279  key = _canonicalize_src_for_dedup(src) or src.lower()
:287  head_len = int(_get_cfg_attr("DOC_SIGNATURE_HEAD_CHARS", 500))
:288  pc_head  = " ".join(str(pc).split())[:head_len]      # 본문 앞 500자
:289  return sha1(f"{key}|{pc_head}")                       # ◀ 실제 시그니처
```

→ **케이스 G의 "웹 청크는 병합된다"를 결론으로 쓰면 틀린다.** 프래그먼트가 지워져 `key`가 같아져도, **본문 앞 500자가 다르면 sha1이 달라 둘 다 생존**한다.

| 실제 병합 조건 | 결과 |
|---|---|
| `canon(src)` 동일 **AND** 본문 앞 500자 동일 | 병합 |
| `canon(src)` 동일, 본문 앞 500자 상이 | **둘 다 생존** |

🔴 **잔존 위험은 여기다** — 같은 URL의 **오버랩 청크**. `-web` 인덱스 avg 1,873자(CLAUDE.md §8.2)에서 청크 간 오버랩이 500자를 넘으면 앞 500자가 같아져 **서로 다른 청크가 조용히 1건으로 접힌다.** `DOC_SIGNATURE_HEAD_CHARS`(기본 500)가 유일한 방벽이고, 경고 로그는 없다.
→ **미확인. R3-1 실행 시 `-web` 오버랩 설정을 실측해 판정한다.** 추정으로 메우지 않는다.

### 2-6. 마커 역추적은 dedup과 무관 (D4 근거)

`build_marker_refs_map` (`utils/refs.py:434-490`)은 **`canon()`을 호출하지 않는다.**
`:468-469` `for new_idx, orig in enumerate(order, 1): doc = refs[orig-1]` — **위치 인덱스 직결**.
→ R1의 "근거 사슬이 본선에서 안 끊긴다"와 일치. D4의 원문 대조는 dedup 결과와 독립적으로 성립한다.

⚠️ **다만 조용한 탈락 2곳** (경고 없음 — R1 A-⑤ ⑤-2 계열):
- `:450` `upper = min(len(refs), max_n=20)` → `:458` `if n < 1 or n > upper: continue` — **20 초과 마커는 버려진다**
- `:471-473` `if not url: continue` — **url 없는 doc은 사이드카에서 통째로 빠진다**

→ D4의 "섹션별 마커 ≥1"은 **본문 `[[N]]` 개수가 아니라 `.refs.json` 항목 수로 센다.** 둘이 다를 수 있다.

---

## 3. T3 — `chunk_summary` 비용 상한

### 3-1. 실측 사실

| 항목 | 값 | 근거 |
|---|---|---|
| 호출 함수 | `_summarize_one()` | `utils/chunk_summary.py:67` |
| 호출 방식 | `llm.invoke(prompt)` — **단발 문자열** | `:78` |
| **모델** | `get_llm()` **기본 인스턴스**. per-call override **없음** | `:124-125` |
| 실효 모델 | **`gpt-4o`** | `.env.openai:18` `OPENAI_MODEL=gpt-4o` → `core/llm.py:327` |
| **`max_tokens`** | **미지정** (코드에 없음) | `:67-89` 전량 |
| `temperature` | 미지정 → `get_llm()` 기본 `0.3` | `core/llm.py:302` |
| **동시 실행 상한** | **`max_workers=4`** | `:117`, `:143` `ThreadPoolExecutor` |
| per-call 타임아웃 | **60초** | `:151` `fut.result(timeout=60)` |
| 마커 상한 | **20** (`build_marker_refs_map` 기본) | `utils/refs.py:434` |
| **비활성 토글** | **없음.** 조건은 `if out_path and marker_refs_map` 뿐 | `agent/section_writer.py:372` |

### 3-2. 실패 시 동작 (3중 흡수, 전부 조용함)

| 실패 지점 | 동작 |
|---|---|
| `get_llm()` 실패 | `:126-128` warning 후 **요약 전체 스킵** |
| LLM 호출 실패 | `:87-89` warning 후 **`""` 반환** |
| 60초 초과 | `:152-154` warning 후 **`""`** |
| 요약이 `""` | `:155` / `:93-94` **merge 자체를 스킵** — 사이드카에 `summary` 키가 안 생김 |

→ **부분 실패가 예외를 내지 않는다.** `summary` 없는 항목이 있어도 파이프라인은 성공으로 보인다.

### 3-3. 🔴 daemon thread — R3-1 드라이버 설계에 직결

`start_background_summarization` (`:161-191`)은 `daemon=True` 스레드(`:188`)를 띄우고 **즉시 반환**한다(`:190-191`).

→ **드라이버가 `build_final_report()` 직후 종료하면 요약이 중간에 잘린다.** 비용은 그때까지만 발생하지만 사이드카가 불완전해지고, **T3 실측치도 못 얻는다.**
→ R3-1 드라이버는 **종료 전 스레드 join 또는 대기**가 필요하다. `start_background_summarization`이 `Thread`를 반환하므로 붙잡을 수 있다. **(a) 드라이버 요구사항으로 박제.**

### 3-4. 상한 산출

**산식** (per call):
```
input  = 프롬프트 고정부(≈300자) + section_context(±200자 × 2 + 마커 ≈ 405자) + chunk_text(청크 원문 전량)
output = 1~3문장 한국어 ≈ 150자
```
`section_context` = `extract_marker_context(radius=200)` (`:51`, `:74-75`) → 최대 405자로 **코드가 상한을 건다.**
`chunk_text`는 **상한 없음** — 청크 원문 전량(`:132` `entry.get("text")`).

**보수적 가정** — 한국어 1자 = 1토큰 (실제 `o200k_base`는 이보다 효율적이므로 과대추정), 청크는 `-web` avg **1,873자**(CLAUDE.md §8.2):

| | 계산 | 값 |
|---|---|---|
| input / call | 300 + 405 + 1,873 ≈ 2,578 → 여유 반올림 | **3,000 tok** |
| output / call | 150자 | **200 tok** |
| **최대 콜 수** | 7섹션 × 20마커 | **140** |
| input 총 | 140 × 3,000 | 420,000 tok |
| output 총 | 140 × 200 | 28,000 tok |

**단가** `gpt-4o` = input **$2.50 / 1M**, output **$10.00 / 1M**
⚠️ **이 단가는 실측이 아니라 기억이다.** 유료 실행 전 OpenAI 가격표로 확인할 것 — 산식만 박제하고 단가는 대입값으로 둔다.

| | 계산 | **이론 상한** |
|---|---|---|
| input | 0.42M × $2.50 | $1.05 |
| output | 0.028M × $10.00 | $0.28 |
| **합** | | **≈ $1.33** |

### 3-5. 🔴 판정 — $1 선을 `chunk_summary` 단독으로 넘는다

R2b §5의 "30분/$1 2차 판정선"을 **요약 콜만으로 초과**한다. 섹션 본문 작성 7콜(`section_writer.py:285` `chain.invoke`)과 `vector_search`는 **여기 포함되지 않았다.**

**실물 앵커로 낮춘 추정** — venfobel 실측 = **섹션당 마커 5건**(20이 아님):

| | 콜 수 | 비용 |
|---|---|---|
| 7섹션 × 5마커 | 35 | **≈ $0.33** |

→ **상한 $1.33 / 실물앵커 $0.33.** 6배 차이는 "마커 20건이 다 찬 섹션"이라는 최악 가정에서 온다.

⚠️ **이건 상한이다. 실측은 R3-1 실행 시.** 마커가 몇 개 붙는지는 writer 출력에 달렸고 지금은 모른다.

**챗 판단 필요** — 상한이 판정선을 넘으므로 셋 중 하나:
1. 그대로 진행하고 실측으로 확정 (실물앵커가 맞으면 $0.33)
2. `build_marker_refs_map`의 `max_n`을 낮춰 상한을 조인다 → **코드 변경. R3-1 STOP 게이트 저촉**
3. 요약을 끄고 (a)를 돈다 → **토글이 없어 코드 변경 필요. 동일 저촉**

→ **2·3은 R3-1 성격상 불가.** 1을 권고하되, `$1.33`을 예산 상한으로 미리 승인받고 들어가는 것이 안전하다.

---

## 4. T4 — state 조립 정찰

### 4-0. 🔴 선례 확인 — **노드를 부르는 드라이버는 없다**

`scripts/_phase_b_run_inner.py`가 그래프 밖 state 조립 선례로 보였으나, 실측:

```
:220   from graph import build_graph
:246   result_state = graph.invoke(state, config={"recursion_limit": ...})
```

→ **그래프를 통째로 돌린다. 노드 직접 호출이 아니고, supervisor를 우회하지도 않는다.**
→ **R2b §2-2 ②(state 조립 = (a) 공수의 대부분) 판정 유지.** 선례로 인용할 수 없다.
(3-b 전례도 노드 호출 검증이 아니다 — R1 A-③. 두 건 모두 인용 불가.)

다만 `:157-169` `build_initial_state()`는 **state 초기값 템플릿**으로는 유효하다:
```python
{"topic_slug", "topic_title", "messages": [], "task_history": [],
 "flags": {"pending_write_title": False, "completed_sections": []},
 "outline_fname": "outline_report.md", "references": {"queries": [], "docs": []}}
```

### 4-1. `vector_search_agent` (`agent/vector_search.py:654`)

| 키 | 필수/선택 | 읽는 라인 | 없을 때 동작 | 출처(누가 채우나) |
|---|---|---|---|---|
| `task_history` | **선택** | `:675` | 🟢 **자가치유** — 경고 후 `Task(agent="vector_search_agent", done=False)` **자동 생성** (`:677-683`) | supervisor / 드라이버 |
| — pending 태스크 | **선택** | `:687-700` | 🟢 자가치유 — 없으면 자동 append (`:695-700`) | supervisor |
| `messages` | 선택 | `:676` | 기본 `[]` | 드라이버 |
| `flags` | 선택 | `:734` | `setdefault("flags", {})` | `sanitize_state`가 보장 |
| `references` | 선택 | `get_refs(state)` `:707` | 빈 refs | 자기 자신 (누적) |
| `outline_fname` / 아웃라인 | 선택 | `get_topic_outline_text(state)` `:708` | 빈 문자열 | content_strategist / 파일 |
| `research_plan` · `planner_queries` | 선택 | `:711` | `[]` → refs 쿼리로 폴백 (`:712`) | research_planner |
| **`topic_slug`** | **사실상 필수** | `:715` | `state → CFG.TOPIC_SLUG → "default"` **3단 폴백** | 드라이버 / 토픽 env |
| `topic_title` · `topic` | 선택 | `:314`, `:734` 상대오프셋 | `"(untitled)"` | 드라이버 |
| `agent_role` · `research_loop_active` · `iteration_count` · `research_round` · `research_objectives` · `vector_seed_query` · `qa_query` · `last_user_query` · `local_ingested_once` | 선택 | 각 `.get()` | 전부 기본값 | 루프/QA 경로 전용 |

**진입부 3줄** (`:655-658`): `logger.info` → `emit_event("참고문헌 검색")` → `get_llm()` → `sanitize_state(state)`.

**NS 결정** (`:715-724`) — state가 아니라 **ENV/CFG가 정본**:
`CHROMA_NAMESPACE_WEB` / `CHROMA_NAMESPACE_LOCAL`. 토픽 env `:7-9`에 3개 다 지정돼 있다 → **드라이버가 NS를 조립할 필요 없다.**

**반환** (`:1528` / `:1566`): `{"messages", "task_history", "references"}`

🟢 **판정: `vector_search_agent`의 state 조립 공수는 낮다.** `topic_slug` + (아웃라인 파일) 만 있으면 나머지는 자가치유·폴백이 흡수한다.

### 4-2. `section_writer` (`agent/section_writer.py:191`)

| 키 | 필수/선택 | 읽는 라인 | 없을 때 동작 | 출처 |
|---|---|---|---|---|
| **`DOC_MODE`(ENV/CFG)** | **🔴 필수** | `:194` | **즉시 return** — 섹션 안 씀 | `core/config.py:462` 기본 `"report"` ⭕ |
| **아웃라인** | **🔴 필수** | `:209-221` | **content_strategist 태스크 예약 후 return** — 섹션 안 씀 | 파일 (실물 있음) |
| `task_history` | 선택 | `:202` | `[]`. pending 없어도 **진행됨**(`if pending:` 가드만) | 드라이버 |
| `messages` | 선택 | `:203` | `[]` | 드라이버 |
| **`flags.completed_sections`** | **선택(중요)** | `:229-232`, `:427` | 없으면 `[]`. **있으면 해당 섹션 skip** | **자기 자신이 갱신** (`:427-430`) |
| `flags.pending_write_title` / `requested_write_title` | 선택 | `:98-101` | 없으면 자동 선택 경로 | supervisor / **드라이버** |
| `topic_slug` | 선택 | `:119` | `None` → 기본 경로 | 드라이버 |
| `topic_title` · `topic` | 선택 | `:289` | `"(untitled)"` | 드라이버 |
| `references` | 선택 | `ref_text` 조립 | 빈 참조 → 마커 0 | vector_search |
| `last_saved_path` | (출력) | `:388` | — | 자기 자신 |

**반환**: 조기 반환 3종은 `{"messages", "task_history"}`, 정상 경로는 그 외 `flags`·`last_saved_path` 갱신 포함.

### 4-3. 추가 확인 6건

**(1) pending task 자료구조**
`Task(agent=..., done=False, description=..., done_at="")` — `core/models.Task`. **속성 접근**(`t.done`, `t.agent`)이지 dict 아님. `supervisor.py:939`가 `with_structured_output(Task)`로 생성.
검색 조건: `next((t for t in reversed(tasks) if (not t.done) and t.agent == "<노드명">), None)`.
🔴 **`description` 필드가 vector_search의 `mission`이 된다** (`:706` `mission = pending.description or ""`). R3-1 드라이버는 여기에 검색 의도를 넣어야 한다.

**(2) `completed_sections` 초기화 주체**
- 타입 선언: `core/state_types.py:68`, `:144` (`NotRequired`)
- **갱신 주체 = `section_writer` 자신** (`:427-430`) — 섹션 저장 후 자기 제목을 append
- **초기화 주체 = 드라이버**. 선례들이 전부 명시 초기화: `scripts/_phase_b_run_inner.py:165`, `scripts/_step3_dry_run_rag_update.py:221` → 둘 다 `"completed_sections": []`
- `supervisor.py:815`도 읽기만 함
→ **R3-1 드라이버가 `flags.completed_sections = []`로 시작해야 한다.** 안 하면 `.get(...) or []`로 흡수되지만, **루프 재진입 시 축적을 드라이버가 유지해야 7섹션이 순회된다.**

**(3) `_get_topic_title` 헬퍼**
🔴 **`vector_search`·`section_writer`에는 없다.** 정의는 2곳뿐이고 **둘 다 로컬 중첩 함수**다:
`agent/research_planner.py:67`, `agent/communicator.py:59`.
대상 2개 노드는 인라인으로 처리한다 — **`state.get("topic_title") or state.get("topic") or "(untitled)"`** (`vector_search.py:~968`, `section_writer.py:289`). 순서는 **`topic_title` → `topic` → 리터럴**.

**(4) `emit_event()`가 그래프 밖에서 터지는가 — ⭕ 안 터진다**
`core/events.py:20-30`. 의존 대상 = **`threading.Lock` + `collections.deque` + `time`뿐.**
FastAPI·이벤트 루프·네트워크·전역 상태 초기화 **의존 0**. 모듈 로드 시 `_EVENT_BUF`가 생성되고(`:15`) 그냥 append한다.
→ **그래프 밖 직접 호출에서 안전.** `/api/events`가 안 떠 있어도 무해(버퍼에 쌓이고 아무도 안 읽을 뿐).

**(5) `target_title` 결정 경로 — `_resolve_title()` (`section_writer.py:88-122`)**
```
1) flags.pending_write_title == True  → flags.requested_write_title      (잠금, from_lock=True)   :98-101
2) get_last_write_target(messages, tasks)  — 단 completed_sections에 있으면 무시                  :112-114
3) next_unwritten_title(outline_text, mode="report", root_dir=current_path,
                        topic_slug=..., excluded_titles=completed_sections)                        :115-121
```
🔴 **R3-1 7섹션 순회는 경로 1이 가장 결정적이다.** 드라이버가 매 회차 `flags["pending_write_title"]=True` + `flags["requested_write_title"]="<H2 제목>"`을 세팅하면 아웃라인 순서를 그대로 강제할 수 있다.
경로 3에 맡기면 **파일 존재 여부로 자동 진행**하지만 순서 제어권을 잃는다.
⚠️ 경로 1로 가면 저장 후 락이 자동 해제된다(`:393-401`) — 매 회차 재세팅 필요.

**(6) `save_md_draft` 출력 경로 (`content_utils.py:57-95`)**
```
mode=="report" → base_dir = get_content_dir("report", root_dir, topic_slug) = <root>/sections/<topic_slug>
                 slug     = section_slug_candidates(title)[0]        # "<n>-<base>"
                 p        = <root>/sections/<topic_slug>/<slug>.md
```
→ R3-1 산출 = **`sections/experiential-marketing-media/<n>-<slug>.md` 7건**
→ 사이드카 = 같은 경로 `.refs.json` (`section_writer.py:375` `with_suffix(".refs.json")`)
→ `report_builder`가 §1-5의 2차 폴백으로 이걸 찾아낸다.

### 4-4. (a) 공수 판정

| 구성요소 | 공수 | 근거 |
|---|---|---|
| `vector_search_agent` state | 🟢 **낮음** | 자가치유 + ENV NS + 3단 폴백 |
| `section_writer` state | 🟡 **중간** | `flags` 3키(`pending_write_title`·`requested_write_title`·`completed_sections`)를 **7회 루프에서 드라이버가 관리** |
| 7섹션 순회 제어 | 🟡 **중간** | 경로 1 재세팅 + 락 자동해제 대응 |
| `chunk_summary` 스레드 대기 | 🟡 **신규** | §3-3 — 종료 전 join 필요 |
| `build_final_report` 호출 | 🟢 **낮음** | `(topic_slug,)` 만으로 호출 가능. 나머지 기본값 |

→ **R2b의 "②가 (a) 공수의 대부분"은 유지되나, 예상보다 가볍다.** 자가치유·폴백이 많다. 실질 작업은 **`flags` 3키 루프 관리 + 스레드 대기** 2건.

---

## 5. R3-1에 미치는 영향 / 🛑 챗 결정 대기

### 5-1. 결정 대기 3건

| # | 사안 | 선택지 | 권고 |
|---|---|---|---|
| **1** | **예산** — `chunk_summary` 이론 상한 $1.33 > $1 판정선 (§3-5) | (a) 상한 승인 후 실측 (b) 코드로 조임 = STOP 저촉 | **(a)**. 실물앵커 $0.33 |
| **2** | **섹션 순회 방식** (§4-3-(5)) | (a) `requested_write_title` 강제 — 순서 확정 (b) `next_unwritten_title` 자동 — 제어권 상실 | **(a)** |
| **3** | **`-web` 오버랩 실측 시점** (§2-5) | (a) R3-1 실행 중 병행 (b) 별도 정찰 | **(a)** — $0, 실행 로그로 판정 가능 |

### 5-2. R3-1 (a) 진입 조건 갱신

| R2b §2-2 | 상태 |
|---|---|
| ① 아웃라인 확보 | ⭕ **소멸** (배치 1 — 실물 존재, H2 7건) |
| ② state 조립 | 🟡 **유지, 범위 확정** (§4-4) — `flags` 3키 루프 + 스레드 대기 |
| ③ 수집 | ⭕ **소멸** (D5 — 기존 색인 retrieve만. NS는 토픽 env `:7-9`가 이미 지정) |

### 5-3. (a) 드라이버 요구사항 (실측 기반, 박제)

1. `TOPIC_SLUG` assert를 무거운 import **앞에** — 실증 완료(§2-4)
2. venv = `../.venv_openai/bin/python`
3. 초기 state = `_phase_b_run_inner.py:157-169` 템플릿 + `topic_slug="experiential-marketing-media"`
4. 7섹션 루프: 매 회차 `flags["pending_write_title"]=True` + `flags["requested_write_title"]=<H2>` 재세팅 (락 자동해제 대응)
5. `flags["completed_sections"]`를 **루프 간 유지**
6. `section_writer` 반환 스레드를 붙잡아 **종료 전 join** (§3-3)
7. 마지막에 `build_final_report(topic_slug)` → `missing_titles` 판정
8. 아웃라인에 **H3 추가 금지** (§1-2)

---

## 6. (B) 쉬운 설명층

**T1 — 목차를 읽는 코드를 다시 확인했다.**
지난번 라인번호는 명령이 반쯤 실패한 상태에서 나온 거라 버리고 새로 세웠다. 결론은 같지만 이제 근거가 있다.
한 가지 흠이 있다. 목차에서 큰 제목(`##`)만 골라내야 하는데, **작은 제목(`###`)도 같이 걸린다.** 걸린 다음 앞 두 글자만 잘라내서 `# 제목` 같은 이상한 이름이 만들어진다. 지금 목차엔 작은 제목이 하나도 없어서 문제가 안 되지만, **목차를 손대면서 작은 제목을 넣는 순간 터진다.** 그래서 "목차에 `###` 넣지 말 것"을 규칙으로 박았다.

또 하나 — **파일을 저장할 때 이름과 찾을 때 이름이 다르다.** 저장은 `2-어쩌고.md`처럼 번호를 붙이는데, 찾을 때는 번호를 뗀 `어쩌고.md`를 먼저 본다. 당연히 못 찾는다. 다행히 못 찾으면 번호 붙은 이름도 뒤져보는 2차 검색이 있어서 결국 찾아낸다. 실제 예전 결과물에서 그렇게 돌아간 흔적을 확인했다. **동작은 하지만 1차는 늘 헛도는 구조**라는 걸 기록해 둔다.

**T2 — 중복 제거 검사. 여기서 예상이 하나 뒤집혔다.**
같은 PDF에서 서로 다른 부분을 뽑아왔을 때 그게 하나로 합쳐져 버리는지가 궁금했다. 실제 결과물을 열어보니 **같은 PDF의 4쪽짜리와 5쪽짜리가 둘 다 살아 있었다.** 합쳐지지 않는다. 확인 끝.

이유도 찾았다. 주소를 정리하는 함수가 **인터넷 주소와 내 컴퓨터 파일을 완전히 다르게 다룬다.** 인터넷 주소는 "몇 번째 조각인지"를 표시하는 꼬리표를 지워버리고, 파일 주소는 그대로 남긴다. 그래서 파일은 조각별로 구분되고 웹은 안 된다. 정반대로 동작하는 것이다.

**그런데 여기서 성급하게 결론 낼 뻔했다.** "그럼 웹 자료는 조각 구분이 사라지겠네"가 자연스러운 결론인데, **틀렸다.** 실제 중복 판정은 주소만 보는 게 아니라 **주소 + 본문 앞 500글자**를 같이 본다. 주소가 같아져도 내용이 다르면 둘 다 남는다. 주소 정리 함수만 보고 판단했으면 오답이었다. 계산 방식을 끝까지 따라가야 한다는 규칙이 정확히 이 경우다.

다만 **아직 안 끝난 위험이 하나 있다.** 웹 자료 조각은 평균 1,873글자인데, 조각끼리 앞부분이 겹치게 잘렸다면 앞 500글자가 같아져서 **서로 다른 조각이 조용히 하나로 합쳐질 수 있다.** 이건 지금 알 수 없어서 "미확인"으로 남긴다. 짐작으로 채우지 않는다.

**T3 — 요약 비용. 여기가 문제다.**
보고서를 쓰고 나면 각 인용마다 "이 출처에서 뭘 가져왔는지" 짧게 요약하는 작업이 자동으로 돈다. 이게 유료다.
최악의 경우를 계산해봤다. 섹션 7개 × 인용 20개 = **140번 호출, 약 $1.33.** 우리가 세워둔 예산선이 $1인데 **요약 작업 하나만으로 넘는다.** 게다가 이건 본문 쓰는 비용과 자료 찾는 비용이 빠진 숫자다.
다행히 최악 가정이 좀 과하다. 예전 결과물을 보니 섹션당 인용이 20개가 아니라 **5개**였다. 그 기준이면 **$0.33**이다. 진짜 값은 돌려봐야 안다.
줄이는 방법이 없진 않은데 **전부 코드를 고쳐야 하고, 이번 단계는 코드 변경 금지**다. 그래서 "$1.33까지 쓸 수 있다"고 미리 허락받고 들어가는 걸 권한다.

그리고 **놓치면 안 되는 함정**: 이 요약 작업은 **뒤에서 따로 돌아간다.** 메인 작업이 끝나고 프로그램이 그냥 종료되면 요약이 하다 말고 잘린다. 돈은 쓴 만큼만 나가지만 **결과물이 반쪽이 되고, 얼마 들었는지도 못 잰다.** 프로그램이 끝나기 전에 기다리는 코드를 반드시 넣어야 한다.

**T4 — 그래프 밖에서 부품을 직접 돌리려면 뭘 준비해야 하나.**
먼저 기대했던 게 하나 무너졌다. `_phase_b_run_inner.py`라는 기존 스크립트가 "이미 그렇게 하고 있다"처럼 보였는데, **열어보니 그래프를 통째로 돌리고 있었다.** 부품을 직접 부르는 게 아니다. 그러니까 참고 선례가 아니다. 이전에 3-b도 같은 이유로 선례가 못 됐다. **두 번 다 "될 것 같았는데 아니었다"**는 걸 기록한다.

좋은 소식도 있다. **자료 검색 부품은 준비물이 거의 없다.** 필요한 게 빠져 있으면 스스로 만들어 채운다. 검색 위치도 설정 파일에 이미 다 적혀 있다.
**글쓰기 부품이 좀 손이 간다.** 어느 섹션을 쓸지 지정하는 스위치 3개를 우리가 7번 반복하면서 직접 관리해야 한다. 한 섹션 쓰고 나면 그 스위치가 자동으로 풀려서 **매번 다시 켜줘야 한다.**

진행 표시 기능(`emit_event`)이 서버 없이도 도는지 걱정했는데, **열어보니 그냥 메모리에 기록만 남기는 것**이라 서버가 꺼져 있어도 아무 문제 없다.

정리하면 **준비물 3개 중 2개가 이미 해결됐고, 남은 하나(스위치 관리)도 생각보다 가볍다.**

---

## Self-check

- [x] **T1 인용을 실패한 명령의 폴백 출력에서 가져오지 않았다** — `ls -l` + 폴백 없는 `sed` + 행번호 부착 판독, 3중 대조(§1-0)
- [x] **T2① 판정 비대칭을 지켰다** — 쌍을 **발견**해 가설을 적극 기각. "쌍 없음"을 결론으로 쓴 곳 0건. 표본 크기(섹션 2·마커 10) 명시
- [x] **T2③ 실행 전 TOPIC_SLUG assert가 걸렸음을 확인했다** — `env -u TOPIC_SLUG`로 AssertionError 실증, `:4`에서 사망(무거운 import 미도달) 확인(§2-4)
- [x] **T4에서 3-b 전례를 노드 호출 검증으로 인용하지 않았다** — 나아가 `_phase_b_run_inner.py`도 `graph.invoke`임을 실측해 선례에서 **제외**(§4-0)
- [x] **논문 트랙 공유 파일(`core/llm.py` · `tools/` · `.gitignore`) 수정 제안 0건** — `core/llm.py`·`tools/web_rag/utils.py`는 **읽기만**. `.gitignore` 언급 0
- [x] **`git add -A` 미사용** — `git add` 자체 0회
- [x] 코드 변경 0 · 커밋 0 · 유료 API 0 · python 실행 = T2③ 1건(순수 문자열 함수)
- [x] 미확인 항목을 **미확인으로** 남김 — `-web` 오버랩(§2-5) · gpt-4o 단가(§3-4) · 실제 마커 수(§3-5)
- [x] D1~D5 확정사항 재론 0건

---

## 🛑 STOP — 챗 결정 3건 대기 (§5-1) — *배치 3에서 갱신됨, §8-6 참조*

1. **예산 상한 $1.33 승인 여부** (실물앵커 $0.33) → **§8-1에서 콜 수 정정**
2. **섹션 순회 방식** — `requested_write_title` 강제 권고
3. **`-web` 오버랩 실측을 R3-1 실행 중 병행할지** → **§8-3에서 종결(위험 부재)**

결정이 오면 (a) 드라이버 작성(§5-3 요구사항 8건)으로 진입한다. 그 시점이 **첫 코드 작성**이다.

---

# 8. 부기 — 배치 3 (T5·T6) 결과 및 정정

- 일자: 2026-08-05 (같은 날, 배치 2 직후)
- 비용: **$0** — LLM/임베딩 API 호출 0. python 실행 = 읽기 전용 4건
- 성격: **위 §1~§7의 정정 3건 + 신규 발견 2건.** 상충 시 **이 절이 우선한다**

## 8-0. 정정 3건 (선언)

| # | 정정 대상 | 기존 기재 | **정정** |
|---|---|---|---|
| **정정 1** | **§2-5** | "실제 dedup은 `utils/refs.py:275-289 _doc_sig` = `sha1(canon\|본문앞500자)`" | 🔴 **틀렸다.** `vector_search`가 import하는 `merge_refs`는 **`utils/rag_utils.py:342`**다(`vector_search.py:18-19`). `utils/refs.py:255 merge_refs`는 **외부 import 0건 · 내부 호출 0건 = 사문**. 본선 키는 **`rag_utils._doc_key_from_any`**(URL+source+part/page/fragment) |
| **정정 2** | **§3-4 / §3-5** | "최대 콜 수 = 7 × 20 = **140콜**" | 🔴 **56콜.** binding이 `build_marker_refs_map`의 20이 아니라 **`REFS_PREVIEW_MAX_DOCS`=8**이다(§8-1). 이론 상한 비용도 그만큼 하향 |
| **정정 3** | **§2-5** 잔존 위험 | "`-web` 오버랩이 500자를 넘으면 청크가 조용히 병합될 수 있다 — 미확인" | 🔴 **위험 자체가 부재.** 500자 시그니처는 **`_doc_sig`(사문) 안에만** 있다. 본선 `rag_utils`는 URL 없을 때만 시그니처 폴백인데 -web은 **폴백 진입 0건**(§8-3). 실측도 충돌 0건 |

> **왜 틀렸나** — §2-5는 `utils/refs.py` 안에서 `canon` 호출부를 따라가다 같은 파일의 `merge_refs`를 본선으로 단정했다.
> **import 문을 확인하지 않았다.** §9 "계산 방식을 확인한 뒤 해석한다"의 import 판(版)이다.

## 8-1. T5-1 — 마커 상한 binding = **8** (20 아님)

| 층 | 실효값 | 근거 |
|---|---|---|
| retrieve per-query | `RAG_TOP_K` = **6** | `core/config.py:494`. ⚠️ `vector_search.py:806`의 리터럴 `5`는 **사문** — `_cfg_str`가 `CFG.<name>` 우선이고 CFG는 항상 6 |
| refs 누적 상한 | `MERGE_REFS_MAX_DOCS` = **0 = 무제한** | `core/config.py:493` · `rag_utils.py:408` `if limit_docs and limit_docs > 0:` |
| **writer가 보는 참조** | **`REFS_PREVIEW_MAX_DOCS` = 8** | `refs.py:306` default 8 · `:320` `docs[:max_docs]`. **CFG 미선언 · ENV 미설정 → 8 확정** |
| 마커맵 필터 | `min(len(refs.docs), 20)` | `refs.py:450`·`:458` — 8 ≤ 20이라 **안 걸린다** |

→ **섹션당 마커 상한 = 8**, **7 × 8 = 56콜**.
⚠️ 잔여: writer가 정본을 어겨 `[[12]]`를 쓰면 `len(refs.docs) ≥ 12`일 때 `:458`을 **통과해** 본 적 없는 doc에 붙는다. 무경고.

## 8-2. T5-2 — 폴백 매칭 = **정확 일치**. 그러나 **오탐 실재**

- **방식** = `core/paths.py:239-243` 후보 순회 + `p.exists()` **정확 파일명 일치**. glob/prefix/부분문자열 **아님**
  - 반증 실행: `"1. Executive"` → `None` / `"1. Executive Summary 확장판"` → `None`
- **다중 히트** = 후보 순서 `["<n>-<base>", "0<n>-<base>", "<base>"]`의 **첫 히트**. 정렬 없음, 에러 없음
- **3번 vs 4번 후보 교집합 = ∅.** "모듈의 실행 사례" 공유는 무해 — 슬러그는 전체 제목 기반. **7제목 전체 쌍 충돌 0건**

🔴 **오탐은 다른 원인으로 실재한다:**
```
sections/experiential-marketing-media/감각과-감성-모듈의-실행-사례-및-설계-방식.md
  2026-08-02 · 300B · 내용: "(L0 수기 테스트용 더미 본문. 인용 마커·출처는 L1에서 검증한다.)"
```
이 파일명 = 3번 제목의 **1차 조회키**(`section_slugify`)와 정확 일치 → `_load_section_body` **1차 즉시 히트**.
→ **3번을 한 글자도 안 써도 `missing_titles==0`이 성립하고, 더미 본문이 최종 리포트에 병합된다.** D4 무력화.
→ 삭제는 SIMPLIFY 게이트("완주 전 삭제 금지") 소관 → **챗 결정 사안.** 드라이버는 **사전 점검에서 검출·보고만** 한다.

## 8-3. T5-3 — `-web` 실측 (count=416)

`data/chroma_store/experiential-marketing-media-web` — **catch AG 가드 통과**(경로 실재 확인 후 개방, 빈 DB 생성 없음).

| 항목 | 결과 |
|---|---|
| canon(src) 그룹 | 106개 (2건 이상 86개) |
| **앞500자 동일 쌍** | **0건** |
| `_doc_key_from_any` 고유 키 | **118** |
| **중복 키** | **98** |
| **빈 키(시그니처 폴백 진입)** | **0건** ← 정정 3의 근거 |
| **메타 키 분포** | `source` 416/416 · `title` 416/416 · `content_type` 416/416 — **`part`/`page`/`fragment` 0건** |

🔴 **신규 발견 A — 같은 URL 청크가 1건으로 접힌다.**
`_doc_key_from_any`는 "URL + source + (part\|page\|fragment)"인데 **-web엔 청크 구분자가 없다** → 키 = URL뿐
→ `rag_utils.merge_refs:390-392` `if key in seen_keys: continue`가 **첫 1건만 남기고 버린다.**
실측: dbpia 10→1 · sweetspot 36→1 · illustkorea 14→1. **416청크 → references 최대 118건.**
⚠️ 대조: venfobel의 `file://`는 `#part=4&index=4&chunk=1`이 **source 문자열 자체**에 박혀 구분됐다. 웹 수집 경로엔 그게 없다.

**부수 — mojibake 43건(10.3%)**, 4개 호스트 집중(atlassian 11 · syncly 11 · prime-career 12 · ranktracker 9). 한글 정상 356건(85.6%).

> ⚠️ **자기 정정**: 이 수치를 처음 **376건(90.4%)**으로 냈고 **틀렸다.** 판정 문자셋에 **공백과 `·`가 섞여** 모든 텍스트가 임계를 넘었다.
> "깨짐 376 + 정상 366 > 416"의 자기모순으로 검출해 재측정했다. **43건이 정정값이다.**
> §9의 "지표가 뭘 세는지 보고 쓴다"에 **작성자 본인이 걸린 사례**로 박제한다.

## 8-4. 🔴 T6-1 — 참조는 **전 섹션 공용 8건** (최대 발견)

**호출부** (정의 아님):
```python
agent/section_writer.py:274
    ref_text = _refs_preview_text(state, numbered=True) + _facts_block(state)
```
→ 인자는 **`state` 하나뿐.** `docs=` 인자가 없다. 함수가 `refs.py:318-320`에서 `state["references"]["docs"]`를 직접 읽는다.

**호출부 전량 4곳 모두 state 전달**: `section_writer.py:274` · `chapter_writer.py:217` · `research_planner.py:236`(max_docs=6) · `vector_search.py:82`(로깅).

**"가장 오래된 8건"인 근거 2단**
1. `rag_utils.py:379` `for d in [*base_d, *add_d]:` → **기존이 앞, 신규가 뒤**
2. `refs.py:320` `docs[:max_docs]` → **앞 8건 = 최초 8건**

**리셋 지점 0건** — `state["references"]` 대입 전량(`vector_search.py:1069/1219/1376/1445` · `web_search.py:400/1425/1449` · `research_planner.py:363`)이 **merge_refs 누적**. 비우는 코드 없음.

**영향**
- 7섹션이 **같은 최초 8건**만 본다 → 섹션별 근거 다양성 **0**
- 마커도 같은 8개 doc을 가리킨다(`build_marker_refs_map`이 동일 state·동일 인덱싱)
- **D4 "섹션별 마커 ≥1"은 충족되나 의미가 없다** — 7섹션 전부 동일 출처
- **콜 56건은 유지** — `.refs.json`이 섹션별로 생기고 `section_context`가 달라 캐시 안 됨. **같은 문서를 7번 요약한다**

→ **드라이버 설계 변경 필요.** 섹션별 refs 교체 vs `REFS_PREVIEW_MAX_DOCS` 상향 vs 현행 수용 = 챗 결정.

## 8-5. T6-2 — §4-6 종결

| 함수 | 판정 | 근거 |
|---|---|---|
| **`refs.py:275-289 _doc_sig`** | 🔴 **완전 사문** | 유일 소비자 `refs.py:255 merge_refs`가 **외부 import 0 · 내부 호출 0**. `__all__:72`에 이름만 등재 |
| **`refs.py:150 _canonicalize_src_for_dedup`** | 🟡 **조건부 현역** | `attach_auto_citations`(`:526`·`:544`·`:590`·`:619`)에서 호출. 이 함수는 `section_writer.py:333`에서 실호출 |

**`canon` 도달 조건** — `AUTO_FOOTNOTE` 기본 **True**(`core/config.py:503`)로 `:331` 게이트는 통과하나,
`attach_marker_citations`가 마커를 하나라도 붙이면 `refs.py:433`이 `[^N]:` 푸터를 출력 →
`attach_auto_citations:504`의 `FOOTNOTE_DEF_RE`에 걸려 **즉시 return**.
→ **마커가 0개인 섹션에서만 도달**하는 레거시 폴백.

→ **본선 dedup = `rag_utils._doc_key_from_any` 단독.** §4-6 종결.

## 8-6. T6-3 — mojibake 노출: 표본 2건 **top-10에 0건**

| 표본 | seed | top-10 중 mojibake |
|---|---|---|
| 「체험마케팅/팝업스토어」 | idx 180 | **0건** |
| 「숏폼 영상광고」 | idx 151 (illustkorea 논문) | **0건** |

> 🔴 **방법 한계 — 결과와 함께 읽을 것.**
> 실제 쿼리 임베딩은 `text-embedding-3-large` **유료 호출**이라 STOP 게이트에 저촉된다.
> 대체로 **저장된 청크 임베딩을 질의 벡터로 사용**했다(API 호출 0, dim=3072 확인).
> 1. **동일문서 편향** — 질의 벡터가 코퍼스 내 실재 청크이므로, **같은 문서의 인접 청크가 구조적으로 상위를 점한다.**
>    실측이 그대로 보여준다: 표본 1은 1~4위가 전부 `brunch.co.kr/@mentats1/725`, 표본 2는 10위 중 9건이 `illustkorea`.
>    → **상위 10칸이 seed 문서로 채워져 mojibake가 들어올 자리 자체가 줄었다.** "0건"은 이 편향 위에서 나온 값이다.
> 2. **seed 선정 실패** — 표본 1은 키워드 2개 동시 매칭 청크가 없어 폴백 선정됐고, 실제 주제(K-브랜드 미국시장)가 의도와 어긋난다.
> 3. 실쿼리 벡터는 코퍼스 밖 점이라 분포가 다르다.
>
> → **"위험 낮음"의 근거로는 약하다. 관측으로만 쓴다.** 확정하려면 유료 쿼리 임베딩 2~3건이 필요하다.

🔴 **부수 — 신규 발견 A의 실증**: 상위 결과가 동일 URL에 강하게 집중한다.
`RAG_TOP_K=6`으로 6청크를 받아도 같은 URL이면 **refs에 1건**만 남는다.
→ **§8-4의 "앞 8건"을 채우는 것조차 어렵다.** 검색 1회 = refs 1~2건이 현실적 시나리오.

## 8-7. 확인 — 최종 서지는 누적 `state["references"]`를 **읽지 않는다**

| 경로 | 서지 출처 |
|---|---|
| `report_builder.build_final_report` | **참고문헌 처리 코드 0건** (grep 0건). 섹션 `.md`를 그대로 병합할 뿐 |
| `app.py:1607-1619` (docx) | `_split_body_footnotes(content)` — **섹션 본문의 `[^N]:` 푸터에서 추출** |

→ **전역 서지 빌더가 없다.** 서지는 `attach_marker_citations`(`refs.py:433`)가 각 섹션 파일 끝에 붙인
`### 참고 문헌 / 각주` 블록으로만 존재한다.
→ **R7 두 벌 관리 불요.** 드라이버는 `state["references"]`를 서지 목적으로 따로 관리하지 않는다.

⚠️ 부작용: 최종 리포트에 `### 참고 문헌 / 각주` 블록이 **섹션당 1개 = 7개** 생기고,
§8-4 때문에 **7개 내용이 거의 동일**해진다.

## 8-8. §5-3 드라이버 요구사항 정정 1건

> **§5-3 항목 6 "`section_writer` 반환 스레드를 붙잡아 join"은 불가능하다.**
> `section_writer.py:382`가 `start_background_summarization(...)`의 **반환값을 버린다**(변수에 안 받음).
> → 드라이버는 `threading.enumerate()`에서 이름이 **`chunk-summary-`로 시작하는 스레드**를 찾아 join해야 한다.
> (스레드명 = `chunk_summary.py:187` `f"chunk-summary-{p.stem}"`)

## 8-9. 결정 대기 — 배치 3 기준 5건

| # | 사안 | 출처 |
|---|---|---|
| **1** | 🔴 **참조가 전 섹션 공용 8건** | §8-4 |
| **2** | 🔴 **같은 URL 청크 접힘** (416→118, 검색 6건→refs 1~2건) | §8-3 + §8-6 |
| **3** | **stale 더미 파일** 처리 | §8-2 |
| **4** | 예산 — 콜 상한 **56**으로 갱신 | §8-1 |
| **5** | 섹션 순회 = `requested_write_title` 강제 | 배치 2 이월 |

**#1과 #2는 물려 있다** — 참조가 공용인데 접힘까지 겹치면 7섹션이 사실상 1~2개 출처로 쓰인다.
완주해도 D4가 **형식만** 통과한다.

**종결된 것**: §4-6 dedup(§8-5) · 앞500자 충돌 위험(정정 3) · 3·4번 제목 충돌(§8-2) · 최종 서지 이중관리(§8-7).

## 8-10. (B) 쉬운 설명층 — 배치 3

**가장 큰 발견: 7개 섹션이 전부 똑같은 자료 8개를 본다.**
글 쓰는 AI에게 참고자료를 줄 때 **그 섹션용으로 찾은 자료**가 아니라 **지금까지 모은 목록의 맨 앞 8개**를 준다. 새로 찾은 건 목록 **뒤에** 붙으므로 앞 8개는 처음 한 번 찾은 것에서 영원히 안 바뀐다. 1번 섹션이 본 8개를 7번 섹션도 그대로 본다.
"각 섹션에 인용이 1개 이상 붙는다"는 합격 기준은 통과하지만 **통과해도 의미가 없다.** 그리고 **같은 문서를 7번 다시 요약한다** — 섹션마다 요약 파일이 따로 생겨 재사용이 안 된다.

**두 번째: 같은 웹페이지에서 가져온 조각들이 하나로 접힌다.**
웹 자료에는 "몇 번째 조각인지" 표시가 **아예 없다.** 416개 전부 확인했다. 그래서 같은 페이지에서 10조각을 가져와도 **1개만 남고 9개가 버려진다.** 검색해보니 상위 결과가 거의 같은 페이지에서 나온다 — 6개를 찾아와도 실제로는 1~2개만 남는다는 뜻이다. 위의 "앞 8개"를 채우는 것조차 어렵다.
PDF는 주소에 "4쪽 1번 조각"이 박혀 있어 구분되는데, 웹에서 긁은 건 그게 없다.

**세 번째: 지난 분석에서 지목한 중복 제거 코드는 안 돌아가는 코드였다.**
"주소 + 본문 앞 500자로 판정한다"고 했는데 **그 함수를 부르는 곳이 없다.** 이름만 공개 목록에 있고 실제로는 죽은 코드다. 걱정하던 "앞부분이 겹쳐서 조각이 합쳐질 위험"은 **애초에 존재하지 않았다.**

**네 번째: 폴더에 테스트용 가짜 파일이 남아 있다.**
8월 2일에 만든 300바이트짜리 "테스트용 더미 본문"인데, 이름이 하필 3번 섹션이 찾는 이름과 정확히 같다. 그래서 **3번을 안 써도 시스템은 "있다"고 판단하고 그 가짜 본문을 최종 보고서에 끼워 넣는다.** 지우면 되지만 "완주 전엔 지우지 마라"가 규칙이라 판단을 올린다.

**그리고 제가 낸 숫자 하나를 스스로 정정했다.**
글자 깨진 자료를 세면서 처음에 **376개(90%)**라고 냈는데, 판정 기준에 **공백을 실수로 포함**시켜 모든 글이 깨진 걸로 계산됐다. "깨진 게 376개인데 멀쩡한 게 366개"라는 앞뒤 안 맞는 숫자가 나와서 잡았다. **43개가 맞다.**

**마지막으로 검색 실험의 한계를 분명히 해둔다.**
깨진 자료가 검색 상위에 뜨는지 봤더니 0건이었는데, **이 실험은 진짜 질문 대신 이미 저장된 자료 하나를 질문 삼아** 돌린 것이다(진짜 질문은 유료라서). 그러면 **같은 문서의 옆 조각들이 상위를 다 차지한다.** 실제로 10칸 중 9칸이 같은 문서였다. 깨진 자료가 들어올 자리 자체가 없었던 것이다. **"안전하다"의 근거로는 약하다.**

---

---

# 9. 부기 — R3-1 실행 (run1~4) 및 T13~T16

- 일자: 2026-08-05
- 판정: **R3-1 = FAIL (D4 ②).** 조건 조정 0건으로 종결
- 성격: §8이 정찰 결과라면 §9는 **실행 결과**. run1~4 전량 유료 실행분
- 드라이버: `scripts/§research-1/run_r3a_straight.py` (untracked)

## 9-0. run1~4 궤적표

| | 본선 retrieve | vector_search 반환 지점 | refs.docs | `[[N]]` | 사이드카 | 요약콜 | 원인 |
|---|---|---|---|---|---|---|---|
| **run1** | 0회 (§1만 스모크) | — | 0 | 17 (전부 고아) | **0** | 0 | `flags.smoke_retrieve_done` 이월 → §2~7 스모크 스킵 |
| **run2** | **0회** | `:1528`/`:1566` 정상 | 0 | 17 (전부 고아) | **0** | 0 | **쿼리 0개** (`(summary) total 0 queries`). 쿼리 소스 4관문 전부 빔 |
| **run3** | **7회** | **`:1305`×5 / `:1342`×2** | 0,2,2,2,3,2,0 | **0** | **0** | 0 | Direct QA 조기 반환 + `[이전 대화]`에 QA 산문 유입 |
| **run4 (B안)** | **7회** | (우회 — 호출 없음) | 0,2,2,2,3,2,0 | **12** (고아 1) | **5** | **11** | §1·§7 거리 필터 전량 탈락 / §7 고아 마커 |

**각 회차의 수정은 직전 원인을 정확히 제거했고 효과도 측정됐다.** 그러나 매번 다음 관문에서 다른 방식으로 멈췄다.

## 9-1. T13 — 어느 return 이 발화했는가

🔴 **지시된 방법(리터럴 키 집합)으로는 안 갈렸다** — 후보 4개가 전부 동일:
`{messages, next_agent, qa_direct_reply, references, task_history}`

로그 마커로 판별:

| 후보 | 판별 마커 | run3 |
|---|---|---|
| `:1026` | `[vector_search][smoke→communicator]` | **0회** |
| **`:1305`** | `[DIRECT QA] Summary generated and returning...` | **5회** (§2~6, `qa_direct_reply=True`) |
| `:1317` | `summary_failed_min_qa` | 0회 |
| **`:1342`** | `MIN QA emit` | **2회** (§1·§7, `False`) |

→ 🔴 **T10-2(§8-6)와 모순이 아니라 분석 범위 밖이었다.** T10-2는 `:926` 게이트(→`:1026`)만 봤고, 발화한 것은 그 아래 **user_q 기반 Direct QA 블록**이다.
**작성자가 "확정과 관측이 어긋난다"고 쓴 것은 틀렸다.**

## 9-2. T13-2 — 관문 2는 사용자 질의와 **같은 변수**다

```python
:1144  user_q = "" if skip_direct_qa else _extract_user_query(last_human.content) ... else ""
:1160  if (not user_q_clean) and state.get("vector_seed_query") and (forced_seed or not research_loop_active):
:1161      user_q = str(state.get("vector_seed_query") or "").strip()   ← :1144 와 동일 변수
```
중첩 구조 — **retrieve 와 Direct QA 가 같은 블록**:
```
:1185 [ 4] if user_q_clean and not noise and ok_query and key not in ran_queries:
:1190 [12]     _dual_retrieve(...)                        ← 본선 retrieve
:1238 [12]     if _has_writer_pending and pending_write_title:
:1243 [16]         return {messages, task_history, references}   ← QA 를 건너뛰는 유일 분기
:1245 [12]     if ALLOW_SUMMARY:   (실효 True — ENV ALLOW_SUMMARY=1 / ALLOW_LOCAL_SUMMARY=1)
:1305 [28]         return {... next_agent:"communicator"}
```
→ **"관문 1 위조 회피"라는 구분은 다운스트림에서 성립하지 않는다.**

## 9-3. T13-3 — writer 는 자료를 **받았다**

run3 로그 실물(`Docs:` 5회 = §2~6):
```
§2  - [1] 경험경제-파인앤길모어-상세내용1.md (Chunk 187) — …
    - [2] 경험경제-파인앤길모어-상세내용1.md (Chunk 186) — …
§3  - [1] week3_schmitt_sem_lecture.pptx (6, Index: 6, Chunk 1) — SENSE 감각 … FEEL … THINK …
```
프롬프트 `get_section_writer_prompt()`(`prompts.py:496-`)의 `[[N]]` 지시문은 **참조 유무 조건 분기 없음**.
⚠️ `prompts.py:435-460`의 상세 마커 규칙은 **논문 트랙**(`get_paper_section_writer_prompt` `:394`) 소속 — 우리 프롬프트에 없다.
🔴 `[이전 대화]`에 **Direct QA 답변 산문**이 유입(`'role': 'qa'` 마킹 5건).

## 9-4. run4 (B안) — **파이프라인 첫 작동**

`vector_search_agent` 우회, `_dual_retrieve` → `merge_refs` → `section_writer` 직결.

| 관측 | run3 | **run4** |
|---|---|---|
| `[이전 대화]` | SystemMessage + QA AIMessage (마킹 5) | **SystemMessage 1건, 마킹 0** |
| 사이드카 | 0개 | **5개** |
| `[[N]]` / 출처연결 | 0 / 0 | **12 / 11** |
| 요약 콜 | 0 | **11** (완결값) |
| 접힘률 | 40~50% | **0%** |
| usage | 21,299 tok / 12 req | 18,372 tok / **7 req** |
| 벽시계 | 60.6s | 83.8s |

🔴 **판별축 결론**: run3 마커 0 의 원인 = **`[이전 대화]`의 QA 산문**.
→ **catch BJ("writer/프롬프트 별건") 불성립으로 종결.** 삭제하지 않고 원인 경로로 남긴다.

**R-8 로컬 자료 진입 유지** — 사이드카 11건 중 **10건 로컬**(md·pptx·docx·xlsx), 1건 웹.
`_split_k(6)=(web 4, local 2)` 이득 보존.

## 9-5. 🔴 T16 — §1·§7 은 "0건 반환"이 아니라 **"거리 필터 전량 탈락"**

`ingest_vector.py:1641-1642` 가 탈락분 `dist` 를 DEBUG 로 남겨 전량 관측됐다(31건).

| § | q_len | raw web | raw loc | 통과 web | 통과 loc | 탈락 | 탈락 거리값 (임계 **1.100**) |
|---|---|---|---|---|---|---|---|
| **1** | 20 | 4 | 2 | **0** | **0** | 6 | 1.373 · 1.376 · 1.382 · 1.387 · 1.395 · 1.435 |
| 2 | 26 | 4 | 2 | 0 | 2 | 4 | 1.257 · 1.269 · 1.279 · 1.298 |
| 3 | 27 | 4 | 2 | 0 | 2 | 4 | 1.254 · 1.262 · 1.269 · 1.269 |
| 4 | 33 | 4 | 2 | 0 | 2 | 4 | **1.319** · 1.333 · 1.361 · 1.367 |
| 5 | 19 | 4 | 2 | **1** | 2 | 3 | 1.151 · 1.162 · 1.172 |
| 6 | 23 | 4 | 2 | 0 | 2 | 4 | **1.126** · 1.143 · 1.145 · 1.148 |
| **7** | 18 | 4 | 2 | **0** | **0** | 6 | 1.289 · 1.298 · 1.304 · 1.306 · 1.307 · 1.307 |

**chroma 반환은 전 섹션 동일(web 4 + local 2 = 6건).** 갈리는 것은 거리 필터 통과 여부뿐.

🔴 **임계 조정으로 풀 문제가 아니다** — 실측이 그렇게 말한다:
- **§4(1.319)가 §7(1.289)보다 먼데 §4 는 통과 2건.** "§1·§7이 유별나게 멀어서"가 아니다
- §6 최저 탈락 1.126 — 임계에서 **+0.026**

⚠️ 임계·TOP_K **조정 0건**(C7-a 유지). 값만 읽었다.

## 9-6. 🔴 web 통과율 — §research-1 전제에 직접 걸린다

| 소스 | raw (7섹션 합) | 통과 | **통과율** |
|---|---|---|---|
| **web** (`-web` 416청크) | 28 (4×7) | **1** (§5 단독) | **3.6%** |
| **local** (`-local` 302청크) | 14 (2×7) | **10** | **71.4%** |

→ **실질 코퍼스는 local 302청크뿐이다.** `-web` 416청크는 거리 기준에서 사실상 기여하지 않는다.
§8-3의 mojibake 43건(10.3%)과 별개 축이며, **누적 인덱스가 있다는 전제 자체를 재검토 대상으로 만든다.**
(판정선 재검토는 챗 소관 — 이 문서는 수치만 박제한다.)

## 9-7. 실패 성격 분리 — §1 ≠ §7

D4 판정은 **FAIL 그대로**. 단 두 섹션을 같은 실패로 묶지 않는다.

> 🔴 **이 절의 §1 기술은 §9-13-c 로 대체됐다(챗 §8-30 정정).**
> §1 을 "근거 없어 인용 안 함"으로 읽은 것은 틀렸다 — §1 은 refs 0 에서 **가장 완전한 조작**을 하고
> **마커 0 이라 전 검사를 통과했다.** 아래 표는 정정 전 기술로 남긴다.

| | 성격 | 파이프라인 |
|---|---|---|
| **§1 마커 0** | ~~영문 쿼리 + 요약 섹션. 구조·설계 불일치.~~ `attach_auto_citations: no refs; skipping` → **§9-13-c 참조** | **정상** |
| **§7 마커 0(사이드카)** | 처방형. 코퍼스 부재. **R2b §2-3-a 예측 적중** | **정상** |
| **§7 고아 1** | 🔴 **진짜 결함 (catch BC)** — refs 0 인데 `[[1]]` 발행 | — |

**동일 입력(refs 0)에서 §1은 인용을 안 했고 §7은 발행했다. 갈린다는 것이 보장 부재의 증거다.**

**§7 무근거 3건 — 원문 박제**
> 최신 데이터에 따르면, 체험마케팅 시장은 **연평균 12%의 성장률**을 보이고 있으며, 주요 경쟁 브랜드로는 **Nike, Coca-Cola, Samsung** 등이 있습니다.

> 참고 자료에 따르면, 성공적인 체험마케팅 캠페인은 평균적으로 **브랜드 인지도를 20% 이상 증가**시킬 수 있습니다**[[1]]**.

⚠️ 두 문장 모두 **"최신 데이터에 따르면" · "참고 자료에 따르면"** 이라는 출처 귀속 표현을 달고 있다. 참고 자료는 **0건**이었다.

## 9-8. D4 최종 판정

| | 결과 |
|---|---|
| ① `missing_titles == 0` | ⭕ PASS (run2·3·4 전부) |
| ② 섹션별 마커 ≥1 + 고아 0 | 🔴 **FAIL** — §1 마커0 / §7 사이드카0 + 고아1 |
| ③ 원문 대조 표본 | **run4에서 처음 가능** — 사이드카 3건 대조 대기(§9-9) |
| [C4] 미열람 doc 인용 0 | ⭕ PASS (run1~4 전부) |

## 9-9. D4 ③ 대조 대상 (챗 소관)

```
① sections/experiential-marketing-media/_FAILED_20260805-run4_6-미디어-형식별-체험-설계와-최신-동향.refs.json   6,662B / 마커 2 / summary 2
② sections/experiential-marketing-media/_FAILED_20260805-run4_5-체험-효과의-측정과-관리-전략.refs.json          10,855B / 마커 3 / summary 3
③ sections/experiential-marketing-media/_FAILED_20260805-run4_3-감각과-감성-모듈의-실행-사례-및-설계-방식.refs.json 6,276B / 마커 2 / summary 2
```
원 지정 ①(§7)은 **사이드카 부재로 대조 불가** → §9-7의 원문 박제로 대체.

## 9-10. 작성자 자기정정 3건 (박제)

1. **mojibake 376 → 43** (§8-3) — 판정 문자셋에 공백·`·` 혼입
2. **"확정과 관측이 어긋난다"** (§9-1) — 모순이 아니라 분석 범위 밖
3. **"D-3 tie-break 결함"** — **결함 없음.** §1 마커 0 / §7 마커 1 로 동점이 아니었다.
   D4 판정줄의 `not markers **or** not sidecar_keys`(OR) 목록을 마커 수 목록으로 오독.
   → **없는 버그를 고치지 않은 것**이 결과적으로 옳았다.

## 9-11. 계측기 관련 — §9 승격 후보

🔴 **계측기가 관측 대상을 파괴한 사례** (T7-1):
C9(접힘률) 용 로그 프로브가 `agent.vector_search` 에 붙은 순간 `logging.lastResort` 가 꺼졌고,
root 에 핸들러가 없어 **warning 이 전부 사라졌다.** C9 가 측정하려던 현상의 원인 로그를 C9 프로브가 지웠다.

> **처방: 계측기를 붙였으면 붙이기 전후의 출력을 대조한다. 관측 장치가 다른 관측을 지울 수 있다.**

부수 — **패턴 검색은 이미 아는 것만 찾는다.** 좁히는 단계에서는 구간을 통째로 덤프해 육안으로 본다.
373B 아웃라인 · mojibake 합계 모순 · `(summary) total 0 queries` 3건이 전부 이 방식에서 나왔다.

## 9-12. catch 갱신 (T20-2)

| catch | 상태 | 내용 |
|---|---|---|
| **BC** | **원인 확정** | `[[N]]` 발행 + "~에 따르면" 류 출처 귀속 + 근거 부재. **원인 = 명시적 지시.** "보장 부재" 표현 **폐기** — 보장이 없어서가 아니라 **지시가 요구해서**다 |
| **BJ** | **불성립 종결** | run3 마커 0 = `[이전 대화]` QA 산문. writer/프롬프트 별건 아님 (§9-4). 삭제하지 않고 원인 경로로 보존 |
| **BK** | 확정 | web 3.6%(28→1) vs local 71.4%(14→10). `RETRIEVE_WEB_RATIO=0.65`가 web에 4/6 배분. ⚠️ "local에 4를 주면 20건"은 **추론** — 하위 순위 통과율 미측정 |
| **BL** | 기록 | `chunk_summary` 섹션 간 캐시 없음. 동일 청크(`체험마케팅_15주_강의설계표.xlsx Index:1 Chunk 2`)가 §6·§3에 **각각 다른 요약**으로 부착. 유료 콜 중복 |
| **BN** | **원인 확정** | 지시문 **1행 어구 직접 이식**. `"시장 규모 및 성장률"` → §6·§3 본문에 동일 어구 불릿으로 출현 |
| **BO** | 신규 | **규칙 합성** — "수치 필수"(1행) + "출처 표기 필수"(4행) → **지어내고 마커 붙이기**. §7 `[[1]]` 고아가 이 합성의 산물 |
| **BP** | 신규 | **분량 강제 > 근거 분량.** 프롬프트 `- 길이: 800~1,500 단어`. §6 근거 총량 = 1,392자(181+1,211) |
| **BQ** | 신규 | **모델 입력 = snip 350자 ≠ 대조 대상 = 청크 원문.** 7건 중 5건 절단, 최저 15%(2,379→350) |
| **BR** | 신규 · 우선도 **상** | **프롬프트 장르 미스매치.** `get_section_writer_prompt`는 **광고 시장조사 보고서 틀**(시장 규모 · 경쟁 브랜드 · KPI · Actionable Recommendations). 코퍼스는 **대학원 강의자료**. 근거가 완벽해도 **없는 것을 요구**한다. §ad-track-1 미스매치 판정과 동일 계열 |

---

## 9-13. 🔴 프롬프트 원인 규명 (T19) — catch BC 의 발생원

> **결론: 환각이 아니라 지시 이행이다.** R3-1 은 이미 FAIL 확정이므로 **수정하지 않는다**(§9-13-e).

### 9-13-a. ES 블록은 **7/7 주입**된다. 절단 분기 0건

`prompts.py:534-539` (`get_section_writer_prompt`):
```
[Executive Summary 규칙 - {target_title}에 Executive Summary가 포함된 경우]
- 시장 규모 및 성장률 수치 반드시 포함
- 참고 자료에 언급된 주요 경쟁 브랜드명을 반드시 구체적으로 명시할 것
- 로컬 파일(XLSX/PPTX) 참고 자료에 KPI 수치가 있으면 반드시 본문에 인용할 것
- 핵심 KPI 수치는 참고 자료에서 확인된 것만 인용하고 반드시 출처 표기
- 전략적 방향 및 기대 효과를 명확히 제시
```
**run4 로그 실측 — `[Executive Summary 규칙` 출현 7회, 7섹션 전부 `True`.**

🔴 **조건이 자연어 헤더라 코드가 판정하지 않는다.**
`PromptTemplate.from_template()` 단일 문자열이며 `{target_title}`은 **치환 변수일 뿐 조건문이 아니다.**
이 블록을 제거하는 `if`/`replace`/`partial` — `prompts.py` **0건**, `agent/section_writer.py` **0건**.

🔴 **내부 모순**: 1행("수치 **반드시 포함**") vs 4행("**확인된 것만** 인용 + 출처 표기").
🔴 **프롬프트 전체에 생략 허용 문구 0건** — "근거 없으면 쓰지 마라"가 한 줄도 없다.

### 9-13-b. §1 본문 ↔ ES 규칙 1:1 대응표

§1 은 **refs.docs = 0 / 마커 = 0 / 사이드카 없음**이었다.

| ES 규칙 행 | §1 본문 산출 | 준수 |
|---|---|---|
| 시장 규모 및 성장률 수치 **반드시 포함** | "약 **1,200억 달러**", "연평균 성장률은 **12%**" | ⭕ 이행 |
| 주요 경쟁 브랜드명 **반드시 구체적으로** | "**나이키, 코카콜라, 디즈니**" | ⭕ 이행 |
| 로컬 XLSX/PPTX KPI 수치 있으면 반드시 인용 | 대상 refs 0건 | — |
| 핵심 KPI는 **참고 자료에서 확인된 것만** + **출처 표기** | "**20%, 15%, 25%**" 제시, **출처 표기 0** | 🔴 위반 |
| 전략적 방향 및 기대 효과 명확히 제시 | 4·5문단 | ⭕ 이행 |

**동일 블록이 비-ES 섹션에도 주입된 결과** — §6 `연평균 6.5% / 1,500억 달러` · §3 `연평균 10% 이상` · §7 `연평균 12% / Nike·Coca-Cola·Samsung`.
⚠️ §6-2·§3-2 가 마커를 붙인 xlsx 청크 **1,211자 전문 어디에도** 6.5% · 10% · 1,500억 달러는 없다.

### 9-13-c. 🔴 §1 판정 정정 — **검사망 최대 사각** (챗 §8-30)

**챗이 §1 을 "근거 없어 인용 안 함 — 정직"으로 판정한 것은 틀렸다.** 본 문서 §9-7 의 해당 기술도 이 절로 대체한다.

| | §1 | §7 |
|---|---|---|
| refs | 0 | 0 |
| 조작 | **1,200억 달러 · 12% · 나이키/코카콜라/디즈니 · KPI 20/15/25%** | 12% · Nike/Coca-Cola/Samsung · 20% 이상 |
| 마커 | **0** | 1 (고아) |
| C3 고아 검사 | **통과** | 적발 |
| C4 미열람 검사 | **통과** | 통과 |
| 원문 대조(D4 ③) | **대상 아님**(사이드카 없음) | 대상 아님 |

🔴 **§1 은 refs 0 에서 가장 완전한 조작을 하고도 전 검사를 통과했다.**
**§7 은 마커를 1개 붙였기 때문에 적발됐다.** 마커를 안 붙였으면 §7 도 D4 ② 를 깨끗이 통과했을 것이다.

> **마커 부재를 "근거 존중"으로 읽지 말 것. 검사망의 최대 사각이다.**
> 현행 D4 ②·C3·C4 는 **마커를 붙인 조작만** 잡는다. 마커 없는 조작은 전부 통과한다.

### 9-13-d. snip 350자 — 모델 입력 ≠ 대조 대상 (catch BQ)

`refs.py:332` `snip = str(txt).replace("\n", " ")[:snippet_len]`, `REFS_PREVIEW_SNIPPET` 실효 **350**.

| § | marker | label | 원문 자수 | 모델이 본 | 전달률 |
|---|---|---|---|---|---|
| 3 | 1 | week3_schmitt_sem_lecture.pptx | 549 | 350 | 64% |
| 3 | 2 | 체험마케팅_15주_강의설계표.xlsx | 1,211 | 350 | **29%** |
| 5 | 1 | 경험경제…md (Chunk 127) | 129 | 129 | 100% |
| 5 | 2 | week2_experience_economy.pptx | 527 | 350 | 66% |
| 5 | 3 | 고객 리뷰…(웹) | 2,379 | 350 | **15%** |
| 6 | 1 | 경험경제…md (Chunk 175) | 181 | 181 | 100% |
| 6 | 2 | 체험마케팅_15주_강의설계표.xlsx | 1,211 | 350 | **29%** |

**D4 ③ 대조 시 신뢰도 주의** — §5-3(15%)은 극단 절단분이다.
⚠️ **snip 350자는 조작을 설명하지 않는다.** xlsx 1,211자 **전문**에도 해당 수치는 없다.

### 9-13-e. 호출부 1곳 — **챗 UI 공유** (수정 금지 사유)

```
prompts.py:496                 정의
agent/section_writer.py:20     import
agent/section_writer.py:277    chain = get_section_writer_prompt() | llm | StrOutputParser()   ← 실호출 유일
```
→ **`section_writer` 노드는 그래프(챗 UI)와 드라이버가 공유한다.** 프롬프트 수정은 챗 UI 결과물을 바로 바꾼다.
(`chapter_writer` `:323` · 논문 트랙 `:394` 는 별개 함수 — 영향 없음)

🔴 **수정하지 않는 이유** — R3-1 은 FAIL 확정이며 수습이 아니라 **다음 사이클 설계 사안**이다(§7 채널 분리 — 설계는 챗 소관).
수정 범위가 성격이 다른 3갈래로 갈린다:

| | 범위 | 성격 |
|---|---|---|
| **A** | ES 블록 무조건 주입 | **구조 결함** — 챗 UI 에도 버그. 개선 대상 |
| **B** | 내부 모순 · 생략 허용 부재 · 분량 강제 | **정책** — 출력 성격이 바뀐다 |
| **C** | 광고 시장보고서 틀 자체 (catch BR) | 🔴 **챗 UI 본래 용도일 수 있음. 건드리지 말 것** |

→ **결정 4로 챗에서 다룬다.**

---

## Self-check — 배치 3

- [x] 정정 3건을 **§8-0에 선언**하고 원 위치(§0)에 stale 경고 배치
- [x] T6-3 **방법 한계(동일문서 편향)를 결과 표 바로 옆**에 명시(§8-6) — 지시 준수
- [x] mojibake 376→43 **자기 정정을 은폐하지 않고 박제**(§8-3)
- [x] T6-1은 **정의가 아니라 호출부**로 판정(`section_writer.py:274`) — 지시 준수
- [x] catch AG 가드(경로 실재 확인 후 chroma 개방) 실행 — 빈 DB 생성 0
- [x] TOPIC_SLUG assert를 **무거운 import 앞**에 두고, `env -u`로 AssertionError 실증 (T5-2·T5-3 각 1회)
- [x] 코드 변경 0 · 커밋 0 · 유료 API 0 · 임베딩 호출 0
- [x] 논문 트랙 공유 파일 수정 제안 0건 · `git add -A` 미사용
