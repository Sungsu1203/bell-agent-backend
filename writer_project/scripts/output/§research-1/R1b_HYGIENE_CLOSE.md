# §research-1 R1b — 위생 조치 close (A·B·C·E)

- 일자: 2026-08-05
- 선행: `R1b_CREDENTIAL_AUDIT.md` (감사 → STOP → 챗 판정 통과)
- 비용 $0 · blockagi 실행 0 · 의존성 설치 0 · python 실행 0 · 유료 호출 0
- **키 값 0건 기재.** 이름·생성일·key_id 앞 8자·사유까지만
- 대조 결과는 `R1b_BLOCKAGI_COMPARE.md` 별도

---

## 0. 판정 전제 — history scrub은 기각됐다

> 키를 회전하면 유출된 옛 키는 **무효 문자열**이 된다. 이력 재작성은 그 죽은 문자열을 가릴 뿐이다.
> `filter-repo`는 **이후 모든 커밋 해시를 변경**하는데, 이 레포는 `scripts/output/` 분석 문서 ·
> `ARCHITECTURE.md` 부록 A · `R1_FINDINGS.md`(기준 HEAD `53a76a88`) · WORKBOARD ·
> catch 로그가 **커밋 해시를 근거로 참조**한다.
> → **1년치 측정 기록의 추적성이 파손되고, 얻는 것은 0.** 비용 >> 이득으로 기각.

- 두 레포(`bell-agent-backend` · `Sungsu1203/blockagi`) **모두** 적용. **재론 금지**
- 대응은 **① 키 회전 ② HEAD 정리 ③ `.gitignore` 보강** 3종으로 마감
- 박제 위치: `STANDARDS.md §5.4-a`

---

## A. `blockagi-run` HEAD 하드코딩 시크릿 제거 — ✅ 완료

### 발견 — 프롬프트 기재 1건 + **미기재 1건**

| 라인 | 변수 | 프롬프트 기재 |
|---|---|---|
| `test_google_search_tool.py:38` | `GOOGLE_API_KEY` 평문 폴백 | ⭕ 기재됨 |
| `test_google_search_tool.py:39` | **`GOOGLE_CSE_ID` 평문 폴백** | ✖ **미기재 — 이번에 추가 발견** |

프롬프트 §2가 "`cx`/검색엔진 ID 포함 유무도 함께 확인"이라 지시한 바로 그 항목이 실재했다.

### 조치

```python
# before
    # ✅ 환경변수 또는 하드코딩된 값 사용
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or "<평문 키>"
    GOOGLE_CSE_ID  = os.getenv("GOOGLE_CSE_ID")  or "<평문 CSE ID>"

# after
    # 환경변수에서만 읽는다 — 하드코딩 폴백 금지 (평문 시크릿 커밋 방지)
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GOOGLE_CSE_ID  = os.getenv("GOOGLE_CSE_ID")

    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        raise ValueError("GOOGLE_API_KEY / GOOGLE_CSE_ID 환경변수를 설정하세요.")
```

- 기존 `:41-42` 가드가 **폴백 때문에 죽어 있었다.** 폴백 제거로 **가드가 살아났다** — 미설정 시 명시적 실패
- 키 값을 다른 파일로 옮기지 않았다. **삭제만** 했다
- 편집은 `sed`로 수행 — 값을 읽어 컨텍스트에 올리지 않기 위함

### 검증

```
git grep -cE 'AIzaSy|<CSE ID>' HEAD -- .   →  exit 1 (0건)
리포 전체 워킹트리 재스캔                    →  0건
```

커밋: `0587a2b` "security: remove hardcoded Google API key/CSE ID fallbacks from test script" (레포 = `blockagi-run`)

### ⚠️ 미완 1건 — **push 미수행**

핸드오프에 push 지시가 없어 **로컬 커밋까지만** 했다.
→ **GitHub 원격의 HEAD에는 아직 평문 키가 남아 있다.** push 여부는 챗 판정 대상.

---

## B. `.gitignore` 구멍 보강 — ✅ 완료

### 🔴 프롬프트 §3의 근거 2건이 모두 실측과 달랐다 (결론은 유효)

| 프롬프트 기재 | 실측 | 판정 |
|---|---|---|
| "구멍 1 — `env_text.txt`는 현행 패턴에 **하나도 매칭 안 됨**" | **이미 차단돼 있었다.** 루트 `.gitignore:42 env_text.txt` 명시 규칙 존재. `check-ignore` 실측 확인 | ✖ 틀림 |
| "구멍 2 — `service_account_key.json`이 **`fd340652`**에서 커밋" | `fd340652` = `feat(rag): externalize topic-specific config` — **자격증명과 무관한 커밋**.<br>실제는 **`3fce3e61`(2026-01-31, A) → `105eca9b`(2026-03-02, D)**.<br>그리고 이 파일명은 writer_project `.gitignore:40 service_account*.json`으로 **이미 차단** | ✖ 틀림 |
| `private_key_id` 이력 "10건" | **11건** | 근사 |

> **§9 적용** — 핸드오프의 "실측된 구멍"도 재검증 대상이다. 두 건 다 근거가 어긋났고,
> `check-ignore` 실행 한 번으로 드러났다. **규칙이 적혀 있는 것과 작동하는 것은 다르다**는 명제가
> 이번엔 **반대 방향**(이미 막혀 있는데 안 막혔다고 기술)으로 나왔다.

### 실제로 열려 있던 구멍 (`check-ignore` 실측)

기존 패턴 `service_account*.json`은 **접두 고정**이라 아래를 놓쳤다.

| 파일 | 조치 전 | 조치 후 |
|---|---|---|
| `bell_service_account.json` | 🔴 NOT IGNORED | `.gitignore:28 *service_account*.json` |
| `credentials.json` | 🔴 NOT IGNORED | `.gitignore:29 *credentials*.json` |
| `my-credentials.json` | 🔴 NOT IGNORED | `.gitignore:29` |
| `client_secret_123.json` | 🔴 NOT IGNORED | `.gitignore:30 *client_secret*.json` |
| `bell-sa.json` | 🔴 NOT IGNORED | `.gitignore:31 *-sa.json` |

### 반영 위치 — **루트 `.gitignore` 한 곳만**

`.gitignore`는 루트/`writer_project` 이원화되어 있고 루트가 이긴다(`ARCHITECTURE.md` 부록 A5).
슬래시 없는 패턴은 **모든 하위 디렉터리에 적용**되므로 루트 한 곳이면 레포 전역을 덮는다.
**writer_project 쪽에는 중복 추가하지 않았다.**

```gitignore
# ── Secrets / credentials ────────────────────────────────
# ⚠️ 이름 패턴으로 차단한다. 디렉터리 통째 차단은 `!` 예외 복원이 불가하기 때문 (CLAUDE.md §4).
# ⚠️ `.json` 접미사 필수 — 접미사를 빼면 tracked 분석 문서
#    (scripts/output/§14-9-A1/credential_exposure_audit.md)까지 죽는다. 실측 확인함.
writer_project/service_account*.json
# §research-1 R1b: 위 패턴은 접두 고정이라 bell_service_account.json / credentials.json /
# client_secret_*.json / *-sa.json 을 놓친다. check-ignore 실측으로 확인된 구멍을 메운다.
*service_account*.json
*credentials*.json
*client_secret*.json
*-sa.json
```

### 🔴 `.json` 접미사가 필수인 이유 (실측)

`*credential*`을 접미사 없이 쓰면 **tracked 문서 `scripts/output/§14-9-A1/credential_exposure_audit.md`가 죽는다.**
패턴을 쓰기 전에 `ls-files | grep`으로 충돌을 확인했고, `.json` 접미사로 회피했다.

### 검증 2종

```
# ① 목표 파일이 실제로 무시되는가 — 11건 전량 check-ignore 실측
bell_service_account.json  →  .gitignore:28:*service_account*.json    ✅
credentials.json           →  .gitignore:29:*credentials*.json        ✅
client_secret_123.json     →  .gitignore:30:*client_secret*.json      ✅
bell-sa.json               →  .gitignore:31:*-sa.json                 ✅

# ② WOULD-BREAK — tracked 파일이 새 규칙에 죽는가
git ls-files -z | tr '\0' '\n' | while read f; do git check-ignore -q "$f" && echo "WOULD-BREAK: $f"; done
→  0줄  ✅
```

⚠️ `ls-files -z | tr '\0' '\n'` 사용 — `§` 경로가 다수라 quotePath 이스케이프를 우회해야 한다 (CLAUDE.md §9).

### 잔여 구멍 1건 (승인 패턴 목록 밖 — 임의 확장하지 않음)

| 파일 | 상태 |
|---|---|
| `secrets.txt` | 🔴 여전히 NOT IGNORED |

`*.pem` · `*.p12` · `*.key` 계열도 미차단. **패턴 확장 여부는 챗 판정 대상.**

### 워킹트리 실측 — 자격증명 파일 잔존 0건

```
ls service_account*.json  →  no matches
```
§E 회전 로그의 "리포 밖 이동 완료"와 일치.

---

## C. 감사 절차 개정 — ✅ 완료

### 정본 확인

`CLAUDE.md §6`은 **포인터**(`"credential 노출 감사 3-명령 (STANDARDS §5)"`),
절차 정본은 **`STANDARDS.md §5`**. → **STANDARDS만 실질 개정**, CLAUDE는 포인터 라벨만 갱신.

### 개정 내용

| 위치 | 조치 |
|---|---|
| `STANDARDS.md §5.1` | "3-명령 감사" → **"현재 상태 감사 (2-명령)"**로 축소. `check-ignore`에 "규칙 기재 ≠ 작동" 경고 추가 |
| `STANDARDS.md §5.1-a` | **신설 — 이력 감사 3축** (파일명 / 형식 정규식 / blob 직독) |
| `STANDARDS.md §5.4-a` | **신설 — 이 레포 history scrub 기각 판정 박제** |
| `CLAUDE.md §6` | 포인터 라벨 갱신 + 1순위(파일명 축)·pathspec 함정 요약 2줄 |
| `scripts/output/§14-9-A1/credential_exposure_audit.md` | **결론 미수정.** 말미에 `§ 7. 적용 한계` 절만 추가 |

### 3축 감사 (신설 §5.1-a 요지)

| 축 | 명령 | 잡는 것 | 우선 |
|---|---|---|---|
| ① 파일명 | `git log --all --oneline --name-status -- '.env*' 'env*' '*.bak' '*secret*' '*credential*'` | **세대 무관** | 🔴 1순위 |
| ② 형식 정규식 | `git log --all -S'AIzaSy'` → 후보 커밋 | prefix 있는 키만 | 2순위 |
| ③ blob 직독 | `git show <commit>:<path> \| grep -cE '<형식>'` | **실제 존재 확정** | 필수 마감 |

**①이 1순위인 이유**: 새어나간 것은 키 한 줄이 아니라 **`.env` 파일 전체**였다.
`NAVER_CLIENT_SECRET`·`SERPAPI_API_KEY`처럼 접두어 없는 값은 ②로 **영원히 안 걸린다.**
→ 질문을 **"어느 키가 샜나"에서 "어느 파일이 커밋됐나"로** 바꾼다.

**③이 필수인 이유 (이번 세션 실사고)**:
```bash
git rev-list --all | while read c; do git grep -lE '<형식>' "$c" -- . ; done
#                                                                  ^^^  cwd 기준 pathspec
```
writer_project에서 실행해 레포 루트의 `env_text.txt`가 범위 밖으로 밀렸고, **에러 없이 0건**이 나왔다.
그것을 "이상 없음"으로 읽었다. `git show <commit>:<path>`는 pathspec이 개입하지 않는다.

**오탐 규칙 추가**: `AKIA`(AWS)는 vendored 라이브러리(`PIL/ImageFont.py`)·웹수집 JSON에서 우연히 나온다.
길이 하한 정규식(`AKIA[0-9A-Z]{16}`) 확인 전에는 노출로 판정하지 않는다. **이번 6건 전부 오탐이었다.**

---

## E. 회전 로그 (사용자 콘솔 실측 — 이 세션은 기록만)

### 챗 확정 사실 (재조사 불요 — 이 세션에서 조사하지 않음)

| # | 사실 |
|---|---|
| 1 | 현행 `.env`/`topics/*.env`에 `GOOGLE_CSE_API_KEY`·`GOOGLE_API_KEY` 값 없음 |
| 2 | 따라서 `config.py:564 HAS_GOOGLE_KEYS` = `False` → google_cse 백엔드 비활성 (`search.py:634 or ""` 폴백) |
| 3 | 리포 내 개인키 파일 0건 |
| 4 | `GCP_PROJECT_ID`·`GCP_REGION`·`GOOGLE_APPLICATION_CREDENTIALS` = 시크릿 아님(ID·경로) |
| 5 | `GEMINI_API_KEY` 주석 처리됨 (Vertex 경로 전환) |
| 6 | `NAVER_CLIENT_SECRET` 변수명 정상 (`AVER_…`는 붙여넣기 절단이었음) |

⚠️ 코드 참조 유무와 값 존재 유무는 다른 층이다.
`search.py`가 `GOOGLE_CSE_API_KEY`를 읽는다는 사실은 **키가 쓰인다는 뜻이 아니다.**

### 회전 로그

| 일자 | 대상 | 종류 | 조치 | 식별·근거 | 사유 | 상태 |
|---|---|---|---|---|---|---|
| 2026-08-05 | `vertex-rag-sa` (`gemini-rag-search-final`) | 서비스계정 개인키 | **회전** (신규 발급 + 구키 삭제) | 구키 생성 2026-02-23, key_id `3f523bee…` / 신키 key_id 상이 확인 | 🔴 **`fd340652`(2026-05-01)에서 `service_account_key.json` 커밋 — 현행 키가 이력에 노출.** 날짜 대조로 확정: 키 생성(2/23) < 커밋(5/1) | ✅ 완료 |
| 2026-08-05 | `RAG-SEARCH_KEY` | GCP API 키 | **삭제** | 생성 2026-02-22 / 뒤4자리 사용자 메모 보관 | `.env` 미참조 실측 + **제한 없음(unrestricted)** + 평문 노출 이력. 콘솔 API 키 목록 유일 항목 | ✅ 완료 |
| 2026-08-05 | `writer_project/service_account.json`<br>`writer_project/service_account_vertex.json` | 개인키 파일 | **리포 밖 이동** (`~/.config/gcloud/_retired/`) | 전자 = `ai-agent-user@gemini-rag-project-new`<br>후자 = `vertex-rag-sa@…` key_id `3f523bee…` | 리포 내 자격증명 상주가 `fd340652` 사고의 직접 원인. git 추적은 안 되고 있었으나 **무시 규칙도 없어 `add -A` 시 유입 가능 상태였음** | ✅ 완료 |
| 2026-08-05 | Tavily | API 키 | 정상 확인 | `api.tavily.com/search` → **200** | `.env` 상주. 동작 확인 완료 | ✅ 완료 |
| 2026-08-05 | OpenAI `writer_agent` (2026-05-07) | API 키 | **회전 불요** | last used 2026-08-04 (본인 활동과 일치) | 생성일이 모든 오염 커밋 **이후**(최신 오염 = `fd340652` 2026-05-01). 이상 사용 흔적 없음 | 🟢 유지 |
| 2026-08-05 | OpenAI `langchain_ai` (2026-07-18) | API 키 | **회전 불요** | last used 2026-07-25 | 상동. 도서 학습용. 미사용 지속 시 정리 후보 | 🟢 유지 |
| 2026-08-05 | Naver Client Secret | 시크릿 | **보류** | `openapi.naver.com` → **200** (기존 키 유효) | ⚠️ 2026-07-31 개발자센터 **신규 신청 차단일 경과**. 재발급 가능 여부 불확실 → **재발급 시도 시 현행 키만 죽을 위험.** NAVER API HUB 이관과 함께 처리 (지원 종료 2027-06-30) | 🟡 보류 |
| 2026-08-05 | SerpAPI | API 키 | 미확인 | `.env` 미참조 | 우선도 하. 계정 잔존 시 키 삭제 권고 | ⬜ 미착수 |
| — | `gemini-rag-project-new` 프로젝트 | GCP 프로젝트 | 미확인 | `service_account.json`의 소속 프로젝트 | 현행 `GCP_PROJECT_ID`와 불일치 = 미사용 추정. 계정째 정리 여부 미정 | ⬜ 미착수 |

### ⚠️ 회전 로그 1행에 대한 실측 주석 (원표 미변경)

위 표 1행의 근거 `fd340652`는 **이 세션 실측에서 다른 커밋으로 확인됐다** (§B 참조).

| 표 기재 | 실측 |
|---|---|
| `fd340652` (2026-05-01) | `fd340652` = `feat(rag): externalize topic-specific config` — 자격증명 파일 무관 |
| — | `service_account_key.json` 실제: **`3fce3e61`(2026-01-31) 추가 → `105eca9b`(2026-03-02) 삭제** |

→ **회전 판단 자체는 바뀌지 않는다.** 키 생성(2026-02-23)이 삭제 커밋(2026-03-02)보다 **앞서므로**
노출 구간에 걸린다. 오히려 노출 시점이 기재보다 **2개월 이르다.**
표는 사용자 실측 결과이므로 **원문을 수정하지 않고 주석으로만 병기**한다.

### 별건 이월 — `ad/WORKBOARD.md` 등재 후보

| 항목 | 기한 | 비고 |
|---|---|---|
| **NAVER Search API → API HUB 이관** | 2027-06-30 (지원 종료) | NCP 계정 신규 가입 필요. 인증 체계 변경(개발자센터 Client ID/Key → API HUB Key). 프로모션 2026-09-30 |
| SerpAPI 계정 정리 | — | 우선도 하 |
| `gemini-rag-project-new` 프로젝트 정리 | — | 우선도 하 |
| `secrets.txt`·`*.pem`·`*.key` 차단 패턴 확장 | — | §B 잔여 구멍 |
| `blockagi-run` push (원격 HEAD 정리) | — | §A 미완 |

⚠️ 이 절은 **기록만.** `ad/WORKBOARD.md` 실제 갱신은 R1b 종료 후 챗 판정.

---

## (B) 쉬운 설명층

**A — 비밀번호를 코드에서 뺐다.**
포크 리포의 테스트 파일에 구글 검색 키가 **글자 그대로** 적혀 있었다. 원래 "환경변수 없으면 이 값 쓰기"라는 안전망 형태였는데, 그 안전망 때문에 **바로 아래 있던 "키 없으면 멈춰라" 검사가 무용지물**이었다. 안전망을 걷어내니 검사가 살아났다. 이제 키 없이 돌리면 **바로 멈춘다.**
프롬프트는 키 1개만 지적했는데 **검색엔진 ID도 같이 박혀 있어서** 둘 다 뺐다.
⚠️ 다만 **GitHub에는 아직 안 올렸다** — 올리라는 지시가 없어서 로컬에만 반영했다.

**B — 앞으로 실수로 커밋되지 않게 막았다.**
자격증명 파일을 걸러내는 규칙이 `service_account`로 **시작하는** 이름만 잡고 있었다. 그래서 `credentials.json`이나 `bell_service_account.json` 같은 이름은 그냥 통과했다. 4개 패턴을 추가해 막았다.

**여기서 조심한 것 하나**: `credential`이 들어간 이름을 다 막으면, 우리가 **일부러 보관 중인 감사 문서**(`credential_exposure_audit.md`)까지 사라진다. 그래서 `.json`으로 끝나는 것만 막도록 했고, 실제로 기존 파일이 하나도 안 죽는지 전량 검사했다 — 0건.

**그리고 프롬프트가 알려준 "구멍" 두 개는 사실 둘 다 이미 막혀 있었다.** 명령 한 번 돌려보니 드러났다. 진짜 구멍은 다른 데 있었다.

**C — 점검 방법을 바꿨다.**
예전 방식은 "**지금 쓰는 키**의 앞글자로 과거 기록 검색"이었다. 그래서 **옛날에 쓰다 버린 키**는 아무리 뒤져도 안 나왔다. 이번에 새어나간 게 딱 그것이었다.

새 방식은 질문을 바꿨다 — "**어느 키가 샜나**"가 아니라 "**어느 파일이 올라갔나**". 설정 파일 이름으로 찾으면 안에 뭐가 들었든 다 걸린다. 네이버 키처럼 **생김새로 알아볼 수 없는 값**은 이 방법 아니면 못 찾는다.

덧붙여, 이번에 제가 **"이상 없음"이라고 한 번 잘못 보고**했다. 검색 명령이 하위 폴더만 뒤지도록 잘못 지정돼 있었고, 문제 파일은 한 단계 위에 있었다. **에러도 안 나고 그냥 "0건"이 나왔다.** 이 함정을 절차서에 못 박아 뒀다.

**E — 키 교체 결과를 장부에 남겼다.**
사용자가 콘솔에서 직접 처리한 내역이다. 서비스계정 키는 새로 발급하고 옛것을 지웠고, 안 쓰는 구글 키는 삭제, 개인키 파일 2개는 리포 바깥으로 옮겼다. 오픈AI 키 2개는 **오염 커밋보다 나중에 만들어진 것**이라 교체하지 않아도 된다.
네이버만 보류다 — 재발급 신청 창구가 이미 닫혀서, **섣불리 새로 받으려다 지금 쓰는 것마저 죽을 수 있다.** 2027년 6월까지 옮겨야 하는 별건으로 넘겼다.

---

## Self-check

- [x] **키 값을 파일·커밋 메시지·보고서에 적지 않았다.** 모든 diff/grep에 마스킹 파이프 적용
- [x] 회전 로그 표를 **주어진 그대로** 수록했다 (상태 임의 변경 0). 실측 불일치는 **원표 미변경 + 별도 주석**으로 병기
- [x] 콘솔 접근·키 삭제를 시도하지 않았다
- [x] `git grep -c 'AIzaSy' HEAD` → `blockagi-run` **0건** 확인
- [x] `git check-ignore -v`로 무시 규칙을 **실측 검증**했다 (규칙 기재만으로 판정하지 않았다)
- [x] `WOULD-BREAK` **0건** — 기존 정상 파일이 새 패턴에 죽지 않았다
- [x] `.gitignore`를 **루트 한 곳에만** 수정했다 (이원화 중복 회피)
- [x] 감사 절차를 **정본(`STANDARDS.md §5`) 한 곳에만** 기술했다. `CLAUDE.md §6`은 포인터 유지
- [x] 선행 감사 문서(`§14-9-A1`) 기존 결론을 **고치지 않고** `§ 7 적용 한계` 절만 추가
- [x] **이력 재작성(`filter-repo`·force-push) 미수행 — 두 레포 모두**
- [x] blockagi 의존성 설치 0 · 실행 0 · 유료 호출 0 · python 실행 0
- [x] `blockagi-ref` 미수정
- [x] `git add`에 `-A`를 쓰지 않았다
- [x] 라인번호·커밋해시를 실물 명령으로 재확인했다 — 프롬프트 기재값 3건의 오류를 적발

---

## 🛑 판정 대기

| # | 항목 |
|---|---|
| 1 | `blockagi-run` push 여부 (원격 HEAD에 평문 키 잔존) |
| 2 | `secrets.txt`·`*.pem`·`*.key` 차단 패턴 확장 여부 |
| 3 | `ad/WORKBOARD.md`에 별건 5종 등재 |
