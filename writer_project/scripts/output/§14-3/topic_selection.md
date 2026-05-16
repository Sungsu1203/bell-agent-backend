# §14-3 Phase 2 Step 3: Tier 2 토픽 dry-run + 선정 박제 (stress test 트랙)

close 일자: 2026-05-15

## 1. 측정 메타

| 항목 | 값 |
|---|---|
| commit | `a8ba7ca` (Step 2 박제 후, dry-run 시 HEAD) |
| 환경 | `.venv_vertex` + `.env.vertex` (LLM_PROVIDER=vertexai, LLM_MODEL=gemini-2.5-flash) |
| GCP | project=`gemini-rag-search-final`, region=`us-central1` |
| trigger | `최신 자료로 RAG 업데이트해줘` (Step 2 박제, _rag_re 매칭 candidate #1) |
| env 박제 | `PYTHONIOENCODING=utf-8`, `VERTEX_MAX_RETRIES=0`, `SKIP_VERTEX_SEARCH=<unset>`, `LOCAL_RAG_ALLOW_EMPTY=1` (새 토픽 ns_local=0 우회) |
| driver | `scripts/_step3_dry_run_rag_update.py` (Step 3 신규 자산, graph.invoke 1회 단발) |
| clear infra | `scripts/_phase_b_clear_ns.py` (Step 3 `--ns` 인자 추가, back-compat) |
| recursion_limit | 100 |
| N | 1 per topic (Tier 2 dry-run, warmup 0) |

## 2. Tier 2 3 토픽 raw 결과

| 항목 | T4 (AI 광고 크리에이티브) | T5 (한국 디지털 광고비) | T6 (Programmatic DOOH) |
|---|---:|---:|---:|
| topic_slug | `ai-generated-creative-ad-platforms` | `kr-digital-ad-spend-2026-forecast` | `programmatic-dooh-growth-drivers` |
| topic_title | AI 생성 광고 크리에이티브 플랫폼 동향 | 한국 디지털 광고비 2026 전망 | Programmatic DOOH 성장 동인 |
| invoke_elapsed_sec | 93.61 | 72.11 | 115.84 |
| total elapsed_sec | 99.72 | 78.20 | 122.41 |
| refs_docs_count | 5 | 3 | 10 |
| **source_dist** | `{'web': 5}` | `{'web': 3}` | `{'web': 10}` |
| **vertex_grounding** | **0** | **0** | **0** |
| messages_count | 10 | 10 | 10 |
| tasks_count | 3 | 3 | 3 |
| abort_reason | None | None | None |
| ns_web (clear 대상) | ai-generated-creative-ad-platforms-web | kr-digital-ad-spend-2026-forecast-web | programmatic-dooh-growth-drivers-web |
| ns 실제 사용 (graph 내부) | default-web / default-local / default | 동일 | 동일 |

### Per-run raw refs (sample)

**T4** (모두 https:// URL):
- `http://www.ftoday.co.kr/news/articleView.html?idxno=351003`
- `https://advertising.amazon.com/ko-kr/generative-ai-ad-solutions`
- `https://featureless.tistory.com/m/825`
- `https://woohamzip.tistory.com/280`
- `https://www.adgenai.com/ko-blog-posts/best-ad-creation-software`

**T5** (모두 https:// URL):
- `https://ad.co.kr/mobile/magazine/592246`
- `https://www.lever.me/blog/3169`
- `https://www.madtimes.co.kr/news/articleView.html?idxno=25978`

**T6** (모두 https:// URL):
- `https://dataintelo.com/report/programmatic-dooh-platform-market`
- `https://market.us/report/programmatic-dooh-platform-market`
- `https://www.marketgrowthreports.com/market-reports/digital-ooh-dooh-market-106323`
- `https://www.marketresearchfuture.com/ko/reports/programmatic-digital-out-of-home-market-32921`
- `https://www.thehypeloop.com/blog/what-will-the-dooh-market-size-growth-be-in-2025`
- `https://broadsign.com/blog/out-of-home-in-2025-advertising-trends-to-watch-from-industry-experts`
- `https://newdigitalage.co/dooh/how-will-programmatic-dooh-evolve-in-2025`
- `https://nt.technology/en/blog-en/programmatic-advertising-trends`
- `https://www.aidigital.com/blog/programmatic-dooh`
- `https://www.forbes.com/councils/forbestechcouncil/2025/02/26/why-dooh-programmatic-advertising-is-gaining-momentum-in-2025`

**18 refs 전체 통합 `vertexaisearch.cloud.google.com` 포함: 0**

## 3. vertex_grounding=0 패턴 박제

### 영어/한국어 토픽 무관 완전 일관

- T4: 한국+영어 혼합 토픽 → vertex=0
- T5: 한국어 중심 토픽 → vertex=0
- T6: 영어 중심 토픽 (Programmatic DOOH) → vertex=0
- 3 토픽 모두 동일 trigger (`최신 자료로 RAG 업데이트해줘`)
- 3 토픽 모두 동일 env (`SKIP_VERTEX_SEARCH=<unset>`, `VERTEX_MAX_RETRIES=0`)

### console.log vertex 로그 분석

3 토픽 console.log 의 `vertex|grounding|chunks|supports` 키워드 매칭:
- env diag 의 `LLM_PROVIDER=vertexai`, `SKIP_VERTEX_SEARCH=<unset>` 만
- `[Config] LLM provider overlay 로드: .env.vertex`
- `ChatVertexAI`/`VertexAIEmbeddings` deprecation warnings (langchain)
- **`vertex_web_search` / `vertex chunks` / `vertex supports` 등 함수 호출 후 로그 0건**

→ `agent/web_search.py:766` 의 `vertex_web_search(query)` 호출은 **logger 미박제 (silent)** 라 진입 여부 직접 박제 불가.

## 4. 가설 A/B/C/D 평가 표

| 가설 | 평가 | 근거 |
|---|---|---|
| **A: vertex_web_search 호출 안 됨** | **★★★ 강한 의심** | console.log vertex 호출 후 로그 0건 + 3 토픽 vertex=0 일관 패턴. graph 내부 분기 (auto_mode/planner_qs/자동 query 생성) 에서 vertex 우회 가능성. logger 미박제로 직접 검증 X |
| **B: grounding metadata 비어있음** | **★★ 중간 의심** | 가설 A 와 구분 불가 — 호출됐다면 supports=[] 또는 chunks=[] 케이스. Phase A 단독 baseline (§ 4) 과 대조하면 가능성 낮음 |
| **C: §14-2 Step 1b patch dead path** | **★ 부분 — patch 자체 정상, effective dead path** | L766-794 코드 review 결과 patch 정상 (supports loop, chunk_indices valid, rep_url 검증, backend="vertex_grounding" 박제). vertex_result.supports=[] 시 effective dead path 이나 코드 결함 아님 |
| **D: source 분류 결손 (vertex 가 'web' 으로 잘못 분류)** | **✗ 기각** | T4/T5/T6 18 refs 전체 source 가 일반 http(s):// URL, `vertexaisearch.cloud.google.com` 포함 0/18. `classify_source @ _phase_b_run_inner:122` 의 'web' 분류 정확 |

### 핵심 미확정 영역

- **A vs B 분리 검증 불가** — web_search.py L766 호출 위치에 logger 박제 없음
- 후속 트랙 (§ 9) 에서 logger 추가 또는 minimal repro 로 분리 검증 필수

## 5. Phase A 단독 vs graph 통합 vertex grounding 대조

### Phase A 단독 baseline (`9fda4ec` commit, README-dev-§14 박제)

- **호출 단위**: `vertex_web_search(query)` 직접 호출 (graph 미통과)
- **결과**: 4 query × 5 run = 20 호출, errors 0/20
- chunks **mean=N>0 안정** (쿼리별 cv 9.5%~23.0%)
- supports **mean=N>0 안정** (cv 11.8%~29.5%)
- elapsed mean=24.93s

### graph 통합 (Step 3 dry-run)

- **호출 단위**: `graph.invoke(state, ...)` 단발 (supervisor → web_search_agent → ...)
- **결과**: 3 topic × 1 run = 3 호출, errors 0/3
- vertex_grounding 분류 **0/3 (완전 일관)**
- web 분류 (Tavily/Naver fetch 결과) 만 누적

### 대조의 의미

- Phase A 가 vertex_web_search 의 정상 동작 baseline 박제 (chunks/supports > 0)
- Phase A → Step 3 의 호출 환경 차이: graph 통과 / state injection / web_search 노드 내부 호출 분기
- **메커니즘 결함 가능성 ★★★** — 토픽 부적합 (vertex grounding 사용 불가능 토픽) 단독으로는 일관 0 설명 어려움
- Tier 1 fallback 의 전제 가정 ("토픽 부적합") 이 메커니즘 결함 가능성으로 약화

## 6. 외부 API 429 quota 박제 (T6)

T6 console.log 발견:
```
[fetch_text] url=https://newdigitalage.co/dooh/how-will-programmatic-dooh-evolve-in-2025
  status=429 error=429 Client...
```

- 2회 발현 (동일 URL, retry 가정)
- **vertex 429 아님** — `[fetch_text]` 는 외부 web fetch (Tavily / Naver / 기타 search backend) 의 HTTP fetch 단계
- §14-2 Phase B 의 vertex API 429 (Vertex RPM/TPM quota) 와 **다른 종류의 quota**
- T6 의 10 refs 중 1 ref 가 fetch 부분 실패 후 fallback content (page_content_len=65) — fetch quota 영향
- Phase 3 본 측정 진입 시 외부 fetch 429 도 abort/retry 분기 검토 필요

### §13-7 측정 표준 update (NEW pitfall)

- **외부 web fetch 429** (Tavily/Naver 등) — graph 통합 측정 시 발현 가능. inter-run-sleep 60s 로도 회피 안 됨 (외부 API 의 RPM 제한 별도 quota window)
- 대응 후보: fetch backend 다중화 / fallback / rate limit 박제

## 7. Tier 1 fallback 결정 보류 박제 + 사유

### 결정: **Tier 1 fallback 보류**

### 사유

1. **메커니즘 결함 가능성 ★★★ 우선 분리 검증 필요**
   - Phase A 단독 baseline 의 vertex chunks/supports 정상 반환과 graph 통합 0 의 강한 대조
   - 토픽 부적합 단독으로는 3 토픽 일관 0 설명 약함
2. **Tier 1 fallback 의 전제 (토픽 적합도 차이) 약화**
   - 메커니즘 결함 시 Tier 1 토픽으로 갈아끼워도 vertex_grounding=0 가능
   - 즉 fallback 전 vertex 호출 검증 (가설 A) 우선
3. **§14-2 Step 1b patch 본 검증 (Phase 3) 진입 부적합**
   - 현재 상태로는 patch 전/후 모두 vertex=0 비교 → 차이 검출 불가
   - vertex 호출 정상화 후에야 Phase 3 진입 의미

### 보류 해제 조건

- 후속 트랙 (§ 9) 의 가설 A 검증 완료
- 가설 A 확정 (vertex 호출 안 됨) → 호출 활성화 patch 후 Phase 3 진입 또는 Tier 1 fallback 재평가
- 가설 A 기각 (호출됐으나 결과 0) → 가설 B (grounding metadata 0) 추가 검증

## 8. 측정 valid 조건 박제 + Phase 3 진입 전 vertex 검증 필수

### Phase 3 본 측정 valid 조건

다음 모두 충족 시에만 Phase 3 진입 (5078a2d patch 후 vs 1135ac1 patch 전 비교 측정):

1. **graph 통합 시 vertex_web_search 호출 직접 박제** — logger 또는 console.log 에서 호출 시점 확인
2. **vertex_result.supports / chunks 누적 박제** — N>0 확인 (Phase A baseline 수준)
3. **state.references.docs 에 source='vertex_grounding' ref append 박제** — classify_source 의 'vertex_grounding' 분류 N>0
4. **위 3 조건이 patch 후 commit (5078a2d) 에서 만족** — patch 전 commit (1135ac1) 측정 의미
5. **외부 fetch 429 quota 영향 분리** — vertex 호출 결과와 외부 fetch 결과 분리 박제

### 본 측정 부적합 시그널 (NEW)

- vertex_grounding=0 인 측정 시나리오 = patch 효과 측정 무효 (5078a2d vs 1135ac1 모두 0 비교)
- Phase B (§14-2) 의 결론 ("patch in-memory 효과 0") 과 동일한 dead path 재현 가능성

## 9. 후속 트랙 정의 박제 (§14-3 보조 트랙)

본 박제 + Step 3 commit 후 사용자 컨펌받고 진입.

### 미션

가설 A (vertex_web_search 호출 안 됨) + 가설 B (grounding metadata 비어있음) + 가설 C (patch dead path) 분리 검증.

### 방법

**(a) `agent/web_search.py:766` 직전/직후 logger 추가** — 가설 A 직접 검증
- 직전: `logger.info("[web_search] vertex_web_search call: q=%s", query[:80])`
- 직후: `logger.info("[web_search] vertex_result: chunks=%d supports=%d", len(v_chunks), len(v_supports))`
- 영향: 최소 (logger 만, 동작 변경 없음)
- 산출물: Step 3 dry-run 재실행 시 console.log 에 vertex 호출 흔적 박제

**(b) Phase A `dump_vertex_grounding.py` 활용 minimal repro** — Phase A baseline 재확인
- 새 토픽 query (T4/T5/T6 자동 생성 query 추출) 로 vertex 단독 호출
- 결과 chunks/supports > 0 박제 → 가설 B 직접 검증
- graph 우회 (단독 호출) 시 정상 반환 확인

**(c) graph 통합 시 web_search 노드 진입 점검** — 가설 A 의 graph 내부 분기 검증
- web_search.py 의 `auto_mode = "rag_update:auto" in mission.lower()` 분기 동작 확인
- planner_qs / forced_queries / 자동 쿼리 생성 분기 진입 박제
- vertex 호출 분기 진입 여부 (`if attempt == 0 and query and not SKIP_VERTEX_SEARCH`) 확인

### 별도 §

- **§14-3 보조 트랙** 또는 **§14-3-A** 류 박제
- Phase 3 본 측정 진입 전 완료 필수

### Step 3 본 commit 후 user 컨펌으로 별도 트랙 진입

본 박제는 트랙 정의만 commit. 실제 작업 시작은 별도 user 컨펌.

## 10. 측정 자산

| 항목 | 위치 |
|---|---|
| Step 3 dry-run script (신규) | `scripts/_step3_dry_run_rag_update.py` |
| Step 3 clear script patch (--ns 인자 추가) | `scripts/_phase_b_clear_ns.py` |
| T4 raw JSON | `scripts/output/§14-3/_dry_run/T4_ai-generated-creative-ad-platforms.json` (gitignore) |
| T5 raw JSON | `scripts/output/§14-3/_dry_run/T5_kr-digital-ad-spend-2026-forecast.json` (gitignore) |
| T6 raw JSON | `scripts/output/§14-3/_dry_run/T6_programmatic-dooh-growth-drivers.json` (gitignore) |
| T4/T5/T6 console.log | `scripts/output/§14-3/_dry_run/T*.console.log` (gitignore, UTF-16 LE) |
| ns_web clear 결과 (per topic + pre_T5 default-web) | `scripts/output/§14-3/_dry_run/_clear/*.json` (gitignore) |

## 11. 환경 박제 (NEW pitfalls)

- **PowerShell 5.1 `Tee-Object`** 가 `-Encoding` parameter 미지원 (PowerShell 7+ 전용) — `NamedParameterNotFound` ParameterBindingException
- **PowerShell 5.1 Tee-Object default encoding**: UTF-16 LE BOM (`FF FE`) — WSL bash 도구에서 mojibake. 측정 결과 해석 영향 없음 (시나리오 8 기각 사전 박제)
- **PowerShell `Get-Content -Raw | ConvertFrom-Json`**: ANSI (CP949) 로 읽음 → UTF-8 한국어 JSON 깨짐 → ConvertFrom-Json fail. Read tool 또는 Python json 모듈 직접 사용 권장
- **WSL bash `python3` 의 § 문자 cwd 처리**: file path 의 § 가 mojibake (`��`) — direct absolute path 권장
- **Bash tool import-heavy Python**: cygwin `TP_NUM_C_BUFS too small: 50` fatal — PowerShell 직접 호출 권장 (graph import 같은 heavy lib loading)
- **LOCAL_RAG_ALLOW_EMPTY=1**: 새 토픽 dry-run 시 `tools/local_rag.py:1358` 의 RuntimeError 우회 필수 (ns_local=0 abort 회피)

## 12. 시나리오 가설 평가 history (디버깅 트레이스)

T5 dry-run hang 디버깅 과정에서 평가된 가설들:

| 가설 | 최종 평가 | 처리 |
|---|---|---|
| 시나리오 1: clear 가 collection 비움 (삭제 X) | 부분 — shutil.rmtree 후 mkdir 재생성 박제 | 본 측정에 영향 없음 |
| 시나리오 4: 한국어 인코딩 | ✗ 기각 | T4/T5 한국어 trigger 모두 통과 |
| 시나리오 7: 일괄 실행 buffer | **★★★ 강화** | T5 일괄 pipeline (pre-clear + sleep + dry-run) fail, standalone retry success. PowerShell session 누적 영향 박제 |
| 시나리오 8: Tee-Object UTF-16 LE 인코딩 충돌 | ✗ 기각 | T4/T5 모두 UTF-16 LE 동일, T4 success |
| 시나리오 9: PowerShell 5.1 vs 7 `-Encoding` incompatibility | 확정 | `Tee-Object -Encoding UTF8` PowerShell 5.1 미지원 |
| graph import 비결정적 race | 미확정 → 시나리오 7 로 통합 | standalone 형식 유지 권장 |
