# §14-9-A1 — credential exposure audit (read-only)

- entry: §14-9 Step A § 6-f Auxiliary safety finding (`.env` / `.env.openai` / `.env.anthropic` 평문 key 존재 박제)
- precedent: §12-11-7 (oauth_client_info.json scrub deferred) — README-dev.md:603-611
- convention: README-dev.md:1924 "Provider 분기 키 분리 convention 운영 중: `.env.anthropic` ANTHROPIC_API_KEY (글로벌 .env 미보관)"
- branch: main / HEAD: 8258f3c / remote: `https://github.com/Sungsu1203/bell-agent-backend.git` (private)
- read-only — file edit / commit / rotation 0
- 표기 규칙: key 값 전체 노출 금지 — prefix 4~8 char + `***` 만

---

## § 1. 노출 자산 inventory + git history 단언

### 1-a. local file 노출 line + prefix

| file:line | env name | prefix | provider | 사용처 (코드 ref) |
|---|---|---|---|---|
| `.env:95` | `TAVILY_API_KEY` | `tvly-k4Rr***` | tavily (search backend) | `tools/web_rag/search.py:595` `_search_tavily` |
| `.env:98` | `NAVER_CLIENT_ID` | `XZyYVP0K***` | naver_direct (search backend) | `tools/web_rag/search.py:827` `_search_naver_direct` |
| `.env:99` | `NAVER_CLIENT_SECRET` | `nBh0wwSa***` | naver_direct (search backend) | `tools/web_rag/search.py:828` |
| `.env.openai:25` | `OPENAI_API_KEY` | `sk-proj-9BjS***` | openai (LLM provider) | `core/llm.py:88-92` `ChatOpenAI` ctor + `core/llm.py:330` `getattr(CFG, APIKeyName)` |
| `.env.anthropic:24` | `ANTHROPIC_API_KEY` | `sk-ant-api03-hPXe***` | anthropic (LLM provider) | `core/llm.py:122-124` `ChatAnthropic` ctor + `core/llm.py:330` |

(참조: `.env.vertex:41` `OPENAI_API_KEY=` 명시 차단 — 빈 값. cred 부재로 audit 대상 아님.)

### 1-b. git tracking status (실측 명령)

명령 1: `git ls-files writer_project/.env writer_project/.env.openai writer_project/.env.anthropic writer_project/.env.vertex writer_project/.env.bak`
→ **empty result** (단 한 file 도 tracked 아님)

명령 2: `git check-ignore -v <files>` (실측):
| file | matched rule | source |
|---|---|---|
| `writer_project/.env` | `.env` | `writer_project/.gitignore:12` |
| `writer_project/.env.openai` | `.env.*` | `.gitignore:17` (root) |
| `writer_project/.env.anthropic` | `.env.*` | `.gitignore:17` (root) |
| `writer_project/.env.vertex` | `.env.*` | `.gitignore:17` (root) |
| `writer_project/.env.bak` | `*.bak` | `writer_project/.gitignore:43` |

→ **5 file 모두 정합 ignore 매칭**. `.env.*` 패턴은 **initial commit `0c59bff`** 부터 존재 (git log -S 확인).

### 1-c. git history scan — key 값 자체 노출 여부

명령: `git log --all --oneline -S "<prefix>"` (각 prefix 별 실측):
| prefix searched | hits in history | 결론 |
|---|---|---|
| `tvly-k4Rrm` | 0 | 미노출 |
| `XZyYVP0K` | 0 | 미노출 |
| `nBh0wwSac` | 0 | 미노출 |
| `sk-proj-9BjSi` | 0 | 미노출 |
| `sk-ant-api03-hPXeRy` | 0 | 미노출 |

→ **5 key 모두 git history 전 구간 노출 0건**. 단 다음 file 들은 변수명/마스킹값 박제 (실키 부재):
- `writer_project/env_raw.txt` (tracked) — placeholder template (`<absolute-path-...>` 형식), 실키 부재.
- `writer_project/scripts/output/§14-3/env_flow_matrix.md` (tracked) — 명시 마스킹 (`***`), L230-231 `.env.openai L25: OPENAI_API_KEY=sk-proj-***` / `.env.anthropic L24: ANTHROPIC_API_KEY=sk-ant-***` 형식 박제.

### 1-d. live/dead 판정

| key | live/dead | 근거 |
|---|---|---|
| `TAVILY_API_KEY` (.env:95) | **live** | default backend chain `naver_direct,tavily` (`core/config.py:558` SEARCH_BACKENDS, `search.py:1304` default_chain). `CFG.HAS_TAVILY=True` (config.py:561). 매 web_search round 마다 `_search_tavily` 후보 호출. |
| `NAVER_CLIENT_ID/SECRET` (.env:98-99) | **live** | default chain 정합. KR-context 시 chain 맨 앞 강제 (`search.py:1479-1487`). `_search_naver_direct:827-831` credential 동시 존재 시 호출. |
| `OPENAI_API_KEY` (.env.openai:25) | **live (LLM_PROVIDER=openai 시)** | 현 글로벌 `.env:2` `LLM_PROVIDER=openai` → `_load_provider()` openai branch (llm.py:82-95) → `ChatOpenAI(api_key=CFG.OPENAI_API_KEY)` ctor 명시 전달. anthropic embedding fallback 경로 (llm.py:481-494) 도 동일 key 참조. |
| `ANTHROPIC_API_KEY` (.env.anthropic:24) | **idle (eval-only)** | `LLM_PROVIDER=anthropic` 활성 시에만 호출. README-dev.md:1915 `§13-8 closed (2026-05-10, deferred 재진입 조건 명시)` → 현재 idle. 재진입은 §13-8-3 별 cycle. README-dev.md:1921 명시 `API key 명: writer-project-eval-13-8` (eval/운영 분리 dedicated key). |

---

## § 2. Convention compliance audit

### 2-a. README-dev.md:1924 정합 검증

convention 정의 (literal): _"Provider 분기 키 분리 convention 운영 중: `.env.anthropic` ANTHROPIC_API_KEY (글로벌 .env 미보관)"_

검증 대상: **LLM provider key** (openai / anthropic / gemini / vertex). search backend key (tavily / naver / google_cse / serpapi) 는 LLM_PROVIDER 와 decoupled (§14-9 Step A § 2-d 박제) — convention 본문은 LLM provider scope 만 지정.

| key | scope | 현 위치 | convention 정합 |
|---|---|---|---|
| `OPENAI_API_KEY` | LLM provider (openai) | `.env.openai:25` (overlay) — `.env:13` 주석 차단 (`# OPENAI_API_KEY=`) | **PASS** ✓ |
| `ANTHROPIC_API_KEY` | LLM provider (anthropic) | `.env.anthropic:24` (overlay) — `.env:15-17` 명시 주석 ("ANTHROPIC_API_KEY 는 .env.anthropic overlay 에 보관") | **PASS** ✓ |
| `GEMINI_API_KEY` | LLM provider (gemini) | `.env:4-5` 주석 (Vertex AI 경로 unused) — 실값 부재 | **PASS** ✓ (실값 없음) |
| `GOOGLE_APPLICATION_CREDENTIALS` | LLM provider (vertex AI) | `.env:8` (글로벌) — service account json path | **편차** (글로벌 .env 위치, 단 path 만이지 key 자체는 별 file). convention 본문 LLM API key 정의에 path-credential 미포함. **위반 아님**. |
| `TAVILY_API_KEY` | search backend | `.env:95` (글로벌) | **PASS** ✓ (convention scope 외) |
| `NAVER_CLIENT_ID/SECRET` | search backend | `.env:98-99` (글로벌) | **PASS** ✓ (convention scope 외) |

→ **convention 정합 항목 0 위반**.

### 2-b. .gitignore 현 상태 박제

`writer_project/.gitignore`:
- L12 `.env` (writer_project/.env 만 매칭)
- L13 `*.env.local`
- L43 `*.bak`
- L76 `topics/*.env` (NDA / client assets, §14-2 478cdb1 commit)

`root .gitignore` (D:\gpt_agent\.gitignore):
- L16 `.env`
- L17 `.env.*` ★ (writer_project/.env.openai / .env.anthropic / .env.vertex 모두 매칭) — **initial commit `0c59bff`** 부터 존재
- L18 `!.env.full.template` (exception)
- L21 `writer_project/service_account*.json`
- L56 `oauth_client_info.json` (§12-11-7 추가, commit `d296f5c`)

→ `.env.*` 패턴이 **initial commit 시점부터** root .gitignore 에 존재 → `.env.<provider>` 파일은 **단 한 번도 tracked 된 적 없음**. 본 audit 의 핵심 단언 근거.

### 2-c. 위반 항목 별 이전 위치 권장

**위반 항목 0건** — 본 cycle 권장 사항 0.

(부가 메모) `GOOGLE_APPLICATION_CREDENTIALS=...service_account_vertex.json` (.env:8) 의 path 자체는 sensitive 가 아니나, 가리키는 file (`service_account_vertex.json`) 은 root `.gitignore:21` `service_account*.json` 으로 차단. local file 만 sensitive cred 보관 — convention 일관.

---

## § 3. Rotation 우선순위 + history scrub 판단

### 3-a. §12-11-7 precedent 정합 평가

| §12-11-7 분류 axis | 본 cycle 적용 결과 |
|---|---|
| credential 노출 여부 (commit 진입) | **노출 0** — git log -S 5 key prefix 전부 0 hit |
| dead vs live credential | live 4 + idle 1 (모두 **현재 사용중 또는 사용 가능**) |
| rotation 필요성 | **미해당** — 노출 자체가 부재하므로 rotation 의무 없음 |
| history scrub 필요성 | **미해당** — history 에 prefix 단 한 line 도 부재 |
| collaborator 가시성 risk | **미해당** — repo private (Sungsu1203/bell-agent-backend) 이며 동시에 history 부재로 collaborator 도 키 값 접근 불가 |

→ §12-11-7 precedent ("dead credential rotation 후 scrub deferred") 는 본 cycle **비해당**. 본 finding 의 정확한 분류는: _"convention 정합 plaintext local credential — git 노출 부재, 별 cycle action 0"_.

### 3-b. key 별 action matrix

| key | provider | status | rotation | scrub | 근거 |
|---|---|---|---|---|---|
| `.env:95 TAVILY_API_KEY` (tvly-k4Rr***) | tavily search | live | **no** | **n/a** | gitignored + history 0 hit |
| `.env:98 NAVER_CLIENT_ID` (XZyYVP0K***) | naver search | live | **no** | **n/a** | gitignored + history 0 hit |
| `.env:99 NAVER_CLIENT_SECRET` (nBh0wwSa***) | naver search | live | **no** | **n/a** | gitignored + history 0 hit |
| `.env.openai:25 OPENAI_API_KEY` (sk-proj-9BjS***) | openai LLM | live (현 default LLM_PROVIDER) | **no** | **n/a** | .env.* gitignored from `0c59bff` initial commit + history 0 hit |
| `.env.anthropic:24 ANTHROPIC_API_KEY` (sk-ant-api03-hPXe***) | anthropic LLM | idle (eval, §13-8 closed) | **no** | **n/a** | dedicated eval key `writer-project-eval-13-8` (README-dev.md:1921) + history 0 hit |

### 3-c. 잔여 risk 평가 (정합성 메모)

§12-11-7 L611 framing 적용:
- "권한 한정 노출 → 잔여 risk 미미" — 본 cycle 은 노출 자체가 부재이므로 **잔여 risk 0**
- 단, **local working tree 가 외부 노출되는 시나리오** (e.g., laptop 도난, 스크린샷 공유) 에서는 plaintext key 가 그대로 노출됨 — 이는 dotenv 사용의 본질적 한계이며 별 cycle scope 외 (운영 보안 layer)
- §14-9 Step A 의 finding 자체는 **사실 (plaintext local)** 이지만 **risk 평가 (commit 노출) 는 오류**. 본 audit 의 정정 박제.

---

## § 4. Action plan (사용자 실행용)

### 4-a. 본 cycle 결론

**사용자 실행 action: 0건**. 본 audit 의 단언:
1. 5 key 모두 git history 노출 부재 — rotation 의무 부재
2. convention 정합 (LLM provider key = overlay, search backend key = global) — 이전 의무 부재
3. .gitignore 정합 (initial commit 부터) — 신규 ignore rule 추가 의무 부재
4. §12-11-7 precedent 비해당 — `git filter-repo` 등 history rewrite 시도 의무 부재

### 4-b. (참고) 만일 향후 노출 발생 시 — provider 별 rotation 진입 경로

본 audit cycle 에서는 실행 X. 향후 별 cycle 대비 reference 박제:

| provider | rotation console path | destination file | 검증 명령 |
|---|---|---|---|
| openai | https://platform.openai.com/api-keys → revoke 후 신규 발급 | `.env.openai:25` 갱신 | `python -c "import openai; ..."` |
| anthropic | https://console.anthropic.com/settings/keys → revoke 후 신규 발급 (`writer-project-eval-13-8` 명 유지) | `.env.anthropic:24` 갱신 | (별 cycle) |
| tavily | https://app.tavily.com/home (Pay-as-you-go 회사카드, .env:95 주석 참조) → revoke 후 신규 발급 | `.env:95` 갱신 | smoke: `_search_tavily("test", num=1)` |
| naver | https://developers.naver.com/apps → 앱 별 client_secret 재발급 | `.env:98-99` 갱신 | smoke: `_search_naver_direct("뉴스", num=1)` |

### 4-c. (참고) history scrub 명령 박제 — §12-11-7 precedent

본 cycle 비해당. 향후 별 cycle 대비:

```bash
# 전제: rotation 완료 + collaborator 0명 또는 사전 동의 + 백업 push
git filter-repo --path writer_project/.env --invert-paths --force
# 또는 특정 string 만:
git filter-repo --replace-text replacements.txt --force
# 결과 force push: git push --force --all (collaborator 영향 — 사전 안내 의무)
```

**STOP 박제**: 위 명령은 본 cycle 에서 **실행 금지** (Pre-condition: read-only). 또한 §12-11-7 L611 정합성 메모대로 "외부 익명 접근 차단 + 권한 한정 노출 → 잔여 risk 미미" 정합 시 우선순위 낮음.

### 4-d. 글로벌 .env 의 violation 항목 제거 절차

**violation 항목 0건** — 절차 불요.

---

## § 5. §14-9 Step A2 entry valid 조건

### 5-a. 본 audit 결과 차단 사항

**없음**. Step A2 즉시 진입 가능.

### 5-b. 정합 단언

1. credential 노출 부재 (§ 1-c 박제) → rotation / scrub 사전 조건 비해당
2. convention 정합 (§ 2-a 박제) → 글로벌 .env 정리 의무 부재
3. .gitignore 정합 (§ 2-b 박제) → ignore rule 추가 의무 부재
4. live/idle credential 5개 모두 working tree 정상 (§ 1-d 박제) → Step A2 backend isolated smoke 가 의존하는 credential set 정상 사용 가능

### 5-c. §14-9 Step A § 6-f 정정 박제

Step A § 6-f (`step_a_backend_provider_matrix.md` 작성 시점) 의 단언:
> 🔴 **Auxiliary safety finding**: `.env.openai:25`, `.env.anthropic:24`, `.env:95` 등에 plaintext API 키가 **커밋되어 있음**.

→ **부분 오류**. 정정:
- ✅ 사실: 5 file 에 plaintext key 존재 (local working tree)
- ❌ 오류: "커밋되어 있음" — 실제로는 **단 한 commit 도 진입 적 없음** (§ 1-c 박제)
- 정확 단언: _"local working tree 에 plaintext key 존재, git history 노출 0건 (initial commit 부터 .gitignore 정합)"_

본 정정은 §14-9 Step A 박제의 **수정 권한 영역 외** — Step A 박제는 그대로 유지하고 본 A1 audit 가 정정 박제 자산 역할.

### 5-d. Step A2 진입 권장 사항

본 cycle 결론 → Step A2 (`scripts/diag/§14-9/backend_isolated_smoke.py` 신규 driver) 진입은 다음 사전 조건 만으로 충분:
- 5 credential 정합 (live 4 + idle 1) ✓
- venv 가용 (`.venv_vertex` + `.venv_openai`) — §14-9 Step A § 6-a 박제
- PYTHONIOENCODING / max_retries / provider-isolated venv convention — §14-9 Step A § 6-b 박제
- pitfall #3 / #4 정합 — §14-9 Step A § 6-c 박제

---

## § 6. 결론 요약

1. **5 credential 모두 git history 노출 0건** — `.env.*` gitignore pattern 이 initial commit `0c59bff` 부터 존재.
2. **convention 정합 위반 0건** — LLM provider key 는 overlay 위치, search backend key 는 글로벌 위치 (각각 의도된 convention scope).
3. **§12-11-7 precedent 비해당** — 본 cycle 은 dead/live credential rotation/scrub 분류 모두 비해당. 별 cycle action 0.
4. **§14-9 Step A § 6-f Auxiliary finding 정정** — "커밋되어 있음" 단언은 오류. local plaintext + git 미노출 정합.
5. **§14-9 Step A2 즉시 진입 가능** — 본 audit 결과 차단 사항 0.

— §14-9-A1 박제 종결 (자율 진행 중지, 사용자 컨펌 대기).
