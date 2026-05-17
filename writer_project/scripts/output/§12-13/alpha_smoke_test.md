# §12-13 (α) 일반 LLM Q&A 헬스체크 — smoke test 박제

**측정 일자:** 2026-05-17
**branch:** `main` (origin synced)
**HEAD:** `3b33dba` (chore §14-8 .gitignore + M2 merge log)
**미션:** §12-13-1 (topic-fitness guard) + §12-13-5 (write fast-path) + §14-8-B (protected env list) 통합 검증

**결과:** **α 3 cases ALL PASS ★★★** — §12-13 사용자 검증 본 미션 첫 단계 정상.

---

## § 1. 작업 1 — housekeeping commit

| commit | content |
|---|---|
| **`3b33dba`** | `chore(§14-8): .gitignore scripts/diag/ + M2 merge log` — .gitignore 의 scripts/diag/ 추가 + M2_merge_log.md (160 insertions) |

push: `f5f363b..3b33dba  main -> main` (origin synced)

---

## § 2. 작업 2 — α smoke test 실행

### 2-1. 측정 환경

- venv: `.venv_vertex` (D:\gpt_agent\.venv_vertex)
- CWD: `D:\gpt_agent\writer_project` (★ wrapper subprocess 패턴 정합 — §14-8 regression 발화 조건 충족)
- driver-set env: TOPIC_SLUG=venfobel-vitamin, LLM_PROVIDER=vertexai, LLM_MODEL=gemini-2.5-flash, SKIP_VERTEX_SEARCH=0, MIRROR_STATE_TO_ENV=0
- POLLUTION pop: CHROMA_NAMESPACE/_WEB/_LOCAL/CHROMA_DIR/OPENAI_MODEL
- AUTO_WRITE_AFTER_RAG=0, AUTO_WRITE_DURING_RESEARCH=0 (smoke 안정 추가)
- script: `scripts/diag/§12-13/alpha_smoke.py` (raw output: `scripts/output/§12-13/alpha_smoke_results.json`)

PowerShell wrapper:
```powershell
Push-Location D:\gpt_agent\writer_project
& D:\gpt_agent\.venv_vertex\Scripts\python.exe scripts\diag\§12-13\alpha_smoke.py
```

### 2-2. PRE-test CFG 박제

```
[init] PRE-import CFG check | LLM_PROVIDER=vertexai | LLM_MODEL=gemini-2.5-flash
                            | TOPIC_SLUG=venfobel-vitamin | CHROMA_NAMESPACE_WEB=venfobel-vitamin-web
```

→ vertex env 정상 build (provider overlay + topic preset load 박제):
```
[Config] LLM provider overlay 로드: D:\GPT_AGENT\writer_project\.env.vertex
[Config] 토픽 프리셋 로드: D:\GPT_AGENT\writer_project\topics\venfobel-vitamin.env
```

---

## § 3. case 별 결과 박제

### 3-1. α-1: topic-neutral 일반 Q&A — off-topic guard

| 항목 | 값 |
|---|---|
| input | `광고 카피라이팅의 핵심 원칙을 짧게 한 문단으로 설명해줘` |
| elapsed | **18.6s** |
| task_history tail | `[('communicator', True, 'off_topic:qa_like')]` ★ **§12-13-1 guard 발화** |
| response len | 407 chars |
| qa_direct | False |

response head:
> 광고 카피라이팅의 핵심 원칙은 타겟 고객의 공감을 얻고 행동을 유발하는 데 있습니다. 명확하고 간결한 언어로 제품의 핵심적인 이점(Benefit)을 전달하며, ... 궁극적으로는 브랜드에 대한 신뢰를 구축하고 긍정적인 감정적 연결을 만드는 것이 성공적인 카피의 목표입니다.

POST CFG/env:
```
CFG | LLM_PROVIDER=vertexai | LLM_MODEL=gemini-2.5-flash | TOPIC_SLUG=venfobel-vitamin | CHROMA_NAMESPACE_WEB=venfobel-vitamin-web
env | LLM_PROVIDER=vertexai | LLM_MODEL=gemini-2.5-flash | TOPIC_SLUG=venfobel-vitamin | CHROMA_NAMESPACE_WEB=<unset>
```

→ **PASS ★** — §12-13-1 topic-fitness guard 정확 발화 (`off_topic:qa_like` task 등록), vertex provider 정상 응답, **regression 부재** (§14-8-B fix 정합).

### 3-2. α-2: topic-context Q&A — venfobel index retrieval

| 항목 | 값 |
|---|---|
| input | `벤포벨S 광고 메시지에서 강조해야 할 핵심 셀링 포인트는?` |
| elapsed | **14.6s** |
| task_history tail | `[('vector_search_agent', True, 'qa_query:...'), ('communicator', True, '사용자 질의에 대한 요약 답변 전달')]` |
| response len | 207 chars |
| qa_direct | False |

response head:
> 벤포벨S 광고 메시지에서 강조해야 할 핵심 셀링 포인트는 '제품의 효과'에 대한 전달력을 강화하는 것입니다. 현재 TV/온라인 광고는 메시지 전달력, 관련성, 차별성, 신뢰성 측면에서 경쟁사 대비 우수하거나 높은 수준을 보이고 있습니다. 그러나 벤포벨만의 독자적인 기능적 이미지를 명확히 형성하고 제품의 강력함을 부각하여, 소비자의 인지 및 구매 확대를 유도해야 합니다.

POST CFG/env: 동일 (vertexai / gemini-2.5-flash / venfobel-vitamin / venfobel-vitamin-web)

→ **PASS ★** — vector_search_agent 가 venfobel 인덱스 정상 retrieval + communicator summary. **CHROMA_NAMESPACE_WEB=venfobel-vitamin-web** (vertex-derived ns, **-oa 회귀 없음**) ★. dual-retrieve namespace 정합 검증.

### 3-3. α-3: explicit write routing edge — §12-13-5 fast-path

| 항목 | 값 |
|---|---|
| input | `write: 도입부 (벤포벨S 광고 콘셉트)` |
| elapsed | **25.8s** |
| task_history tail | `[('section_writer', True, 'write: 도입부 (벤포벨S 광고 콘셉트)'), ('vector_search_agent', True, 'qa_query:write: 도입부 ...'), ('communicator', True, "'도입부 (벤포벨S 광고 콘셉트)' 초안 완료 보고 ...")]` |
| saved | `D:\GPT_AGENT\writer_project\sections\venfobel-vitamin\도입부-벤포벨s-광고-콘셉트.md` ★ |
| section draft | 4 paragraph + 7 footnote citations (5 unique refs: 종근당 팩트북, Ipsos 광고효과조사, 일반의약품 마케팅 등) |

response head (communicator):
> 네, '도입부 (벤포벨S 광고 콘셉트)' 초안은 성공적으로 저장되었습니다. 이제 다음으로 어떤 섹션 작업을 진행해 드릴까요? 목차를 참고하시어 말씀해주시면 됩니다. 최종 저장 경로: `D:\GPT_AGENT\writer_project\sections\venfobel-vitamin\도입부-벤포벨s-광고-콘셉트.md`

section draft 핵심 인용 정합성 (sample):
> 벤포벨S의 핵심 경쟁 우위는 '복합 성분'에 있습니다 [6]. 국내 최초로 말초신경병증 치료 성분인 메코발라민(500 μg)과 간 기능 개선 성분인 UDCA(우르소데옥시콜산 60mg)를 고함량으로 동시에 함유하여, 피로 회복과 간 건강을 동시에 강조하는 전략으로 성공적인 차별화를 이루었습니다 [6].

POST CFG/env: 동일 (vertexai / gemini-2.5-flash / venfobel-vitamin / venfobel-vitamin-web)

→ **PASS ★** — §12-13-5 explicit write fast-path 정확 발화 → section_writer 정상 진입 + 본문 + footnote 정상 생성 + 정상 저장. vertex API 정상 호출 (model=gemini-2.5-flash, **404 부재**) ★.

---

## § 4. wrapper subprocess 검증 (§14-8-B fix 효과 박제)

본 smoke test = **PowerShell wrapper + python subprocess (CWD=writer_project)** — `scripts/diag/§14-8/b2ext4_trigger.py` 패턴 동일 + §14-8-B regression 발화 조건 정합.

### 4-1. protected env list 효과 박제 (3 cases 누적)

| field | PRE (init) | α-1 POST | α-2 POST | α-3 POST | regression 발생? |
|---|---|---|---|---|---|
| `LLM_PROVIDER` | vertexai | vertexai | vertexai | vertexai | **부재 ★** (openai 회귀 X) |
| `LLM_MODEL` | gemini-2.5-flash | gemini-2.5-flash | gemini-2.5-flash | gemini-2.5-flash | **부재 ★★★** (gpt-4o 회귀 X) |
| `TOPIC_SLUG` | venfobel-vitamin | venfobel-vitamin | venfobel-vitamin | venfobel-vitamin | **부재 ★** (default 회귀 X) |
| `CHROMA_NAMESPACE_WEB` (env) | `<unset>` | `<unset>` | `<unset>` | `<unset>` | **부재 ★★★** (.env.openai overlay 차단) |
| `CHROMA_NAMESPACE_WEB` (CFG) | venfobel-vitamin-web | venfobel-vitamin-web | venfobel-vitamin-web | venfobel-vitamin-web | **부재 ★** (-oa 회귀 X) |

→ **§14-8-B fix (O) protected env list 효과 empirical CONFIRMED ★★★**

### 4-2. vertex API 정상 호출 박제 (α-3 detail)

- α-3 의 section_writer 호출에서 vertex_web_search 가 호출됐을 가능성 있음 (research/grounding) — 본문 생성 정상 완료 (vertex 404 부재 박제)
- LLM init log (capture):
  - `[LLM] init provider=vertexai | model=gemini-2.5-flash | project=gemini-rag-search-final | region=us-central1 | temp=0.30`
  - LangChain deprecation warning (ChatVertexAI / VertexAIEmbeddings) — 별 cycle 대응 영역 (§14 reserve)

### 4-3. dual-retrieve namespace 정합 박제 (α-2)

- CFG.CHROMA_NAMESPACE_WEB = `venfobel-vitamin-web` (vertex 인덱스, OpenAI 3072d 와 분리된 768d Vertex 인덱스)
- α-2 vector_search_agent 정상 retrieval — venfobel 인덱스 직접 QA 정확 작동
- **`-oa` suffix 회귀 부재 → cascading 회귀 차단** ★

---

## § 5. case pass/fail 종합

| case | status | 주요 박제 |
|---|---|---|
| **α-1** | **PASS ★** | §12-13-1 off_topic guard 발화, vertex 일반 Q&A 정상 |
| **α-2** | **PASS ★** | vector_search retrieval 정상, venfobel-vitamin-web ns 정합 |
| **α-3** | **PASS ★** | §12-13-5 write fast-path 정상, section 본문+footnote 완성 |
| **wrapper subprocess 검증** | **PASS ★★★** | §14-8-B fix (O) protected env list — 3 cases 누적 regression 부재 |
| **§14-8-B regression** | **부재 ★** | LLM_PROVIDER/MODEL/TOPIC_SLUG/CHROMA_NAMESPACE_WEB 4 field 동일 보존 |
| **vertex 404** | **부재 ★** | LLM_MODEL=gemini-2.5-flash 정상 호출 |

→ **§12-13 (α) FULL PASS ★★★** — §12-13-1 + §12-13-5 + §14-8-B 통합 검증 정합.

---

## § 6. 의외 발견 / priors 15 후보 박제

### 6-1. LangChain deprecation warning (별 cycle)

- `ChatVertexAI` / `VertexAIEmbeddings` LangChain 3.2.0 deprecated, 4.0.0 제거 예정 (`langchain-google-genai` 마이그레이션 필요)
- 본 cycle scope 외 — §14 reserve list 통합 권장 (이미 README-dev-§14.md L115 박제됨)

### 6-2. priors 15 후보 부재

- α 3 cases all PASS — 의외 발견 부재
- priors 14 누적 유지

---

## § 7. 다음 sub-§ 진입 권장 + 발견 사항

### 7-1. mission 분기

**(가) α full pass → β (venfobel index 직접 QA) 진입 권장** ★

### 7-2. β 진입 박제 항목 (다음 round hand-off prep)

- β = venfobel 인덱스 직접 QA + dual-retrieve 정합성 진단
- 본 α 의 α-2 가 부분 cover (venfobel 인덱스 retrieval 정상)
- β scope: 다양한 query × namespace × distance threshold 박제 — 추후 별 mission

### 7-3. γ 진입 후보 박제

- γ = end-to-end 리포트 생성 — full pipeline 검증
- α-3 가 single section write 정확 작동 → γ 의 multi-section + report build 잠재 정상
- γ scope: 전체 outline 7-8 section 작성 + build_final_report — 시간 비용 高 (~30분), 별 mission

### 7-4. pending sub-§ 재발 박제

- **§12-13-2** (web_search OBJ vs user query): α 3 cases 에서 web_search 진입 부재 (다층 방어선 보호) — 재발 부재
- **§12-13-3** (loop counter): web_search 미진입으로 영향 부재
- **§12-13-6 (b)(c)** (Vertex 429 fallback): α 3 cases 에서 429 retry 부재 — metric 추세 변화 부재
- **§12-13-8** (router.tail outline_shown): α-3 에서 outline 표시 분기 미발화 (write fast-path 정상)
- **§12-13-9** (section_writer 슬러그 괄호): α-3 saved path `도입부-벤포벨s-광고-콘셉트.md` — **괄호 제거 재현됨** ★. cosmetic, β/γ 정리 시 batch 가능
- **§12-13-11** (llm_call topic_slug null): metric 라인 확인 본 cycle 외

→ 발견된 §12-13-9 재현은 cosmetic, 본 mission close 차단 사유 아님.

---

## § 8. 본 mission 종결 + 사용자 컨펌 대기

| 항목 | 결과 |
|---|---|
| housekeeping commit | **`3b33dba` push ✓** |
| α-1 | **PASS** |
| α-2 | **PASS** |
| α-3 | **PASS** |
| wrapper subprocess (§14-8-B fix) | **PASS ★★★** |
| §12-13-1 fix | **검증 완료** (off_topic guard 발화) |
| §12-13-5 fix | **검증 완료** (write fast-path 정상) |
| §14-8-B fix | **검증 완료** (protected env list, regression 부재) |

**다음 round 진입 (사용자 컨펌 후 별도 hand-off prompt)**:
- **(권장) β: venfobel 인덱스 직접 QA + dual-retrieve 정합성 진단**
- (옵션) γ: end-to-end 리포트 생성 (시간 비용 高, β 후 권장)
- (옵션) §12-13-9 cosmetic 처리 (low priority)
- (옵션) §14-8 reserve list 처리 (CWD-independent .env, 다른 reload_config 호출처 audit 등)

자율 진행 금지 — β 진입은 별도 round (사용자 컨펌 후).
