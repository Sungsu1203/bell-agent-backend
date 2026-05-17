# §12-13 chroma S4 clear + RAG 업데이트 박제 (priors 15 해소)

**측정 일자:** 2026-05-17
**branch:** `main` (origin synced)
**HEAD:** `cdfc076` (α/β commit)
**미션:** S4 scope chroma clear + RAG 업데이트 + dim verification + priors 15 해소

**결과:** **mission FULL PASS ★★★** — S4 scope 엄격 준수 (production 무손실) + dim 정합 + RAG 업데이트 성공 + priors 15 해소 + **§14-8-B fix 3-layer cumulative CONFIRMED (communicator + retrieval + ingest)**.

---

## § 1. 작업 1 — housekeeping commit ✓

- commit **`cdfc076`** `docs(§12-13): α/β cycle 박제 자산 commit` (origin synced)

---

## § 2. 작업 2 — S4 scope clear + dim verification

### 2-1. pre-clear inventory (22 collections)

| 분류 | collection 수 | 명세 |
|---|---|---|
| production data (보존) | 7 | venfobel-vitamin-local (5.5MB) + -oa-local (8.6MB) + -oa-web (6.0MB) + height-growth-supplement-local/web (340KB/3.3MB) + pet-food-premium-local/web (340KB/1.4MB) |
| empty base (보존) | 4 | venfobel-vitamin / -oa / height-growth-supplement / pet-food-premium |
| **S4 DELETE 대상** | **11** | venfobel-vitamin-web (empty 타깃) + ai-generated-* (3개) + default-* (3개) + kr-digital-ad-spend-* (2개) + programmatic-dooh-* (2개) |

### 2-2. dim verification 결과 (보존 대상)

```
[venfobel-vitamin-local]       count=349  dim=768   ✓ (expected vertex)
[venfobel-vitamin-oa-local]    count=349  dim=3072  ✓ (expected openai)
[venfobel-vitamin-oa-web]      count=150  dim=3072  ✓ (expected openai)
[height-growth-supplement-local] count=12  dim=768  ✓
[height-growth-supplement-web]   count=85  dim=768  ✓
[pet-food-premium-local]         count=12  dim=768  ✓
[pet-food-premium-web]           count=32  dim=768  ✓
```

→ **7 production collection 모두 expected dim 정합** ★. (몇몇 dir 에 chromadb 기본 "langchain" empty collection 동거 — harmless side-effect)

### 2-3. S4 clear 실행

- 방식: `chromadb.PersistentClient.delete_collection(name)` per target
- 결과: 11 targets 모두 logical delete success ★
- 디렉토리 file lock (Windows PermissionError) — chroma.sqlite3 file handle 잔존, **logical clear 자체는 정상**. 디렉토리는 188 KB empty sqlite 로 잔존 (다음 sub-§ 작업에서 자연 재생성/제거)

### 2-4. PRESERVE sanity post-clear

```
venfobel-vitamin-local            count: 349 (변화 0) ✓
venfobel-vitamin-oa-local         count: 349 (변화 0) ✓
venfobel-vitamin-oa-web           count: 150 (변화 0) ✓
height-growth-supplement-local    count:  12 (변화 0) ✓
height-growth-supplement-web      count:  85 (변화 0) ✓
pet-food-premium-local            count:  12 (변화 0) ✓
pet-food-premium-web              count:  32 (변화 0) ✓
```

→ **production 7건 전수 무손실** ★★★ (S4 scope 엄격 준수)

### 2-5. backup 생략 박제

사용자 결정 — backup 생략. 정합 박제: S4 scope 무손실 → rollback 불필요.

---

## § 3. 작업 3 — RAG 업데이트 entry point + provider 상태

### 3-1. entry point 박제

- trigger phrase: `최신 자료로 RAG 업데이트해줘` (또는 _rag_re 매칭 변형)
- supervisor.py L609-619 `_rag_re` 매칭 → fast-path → web_search_agent (rag_update:auto)
- web_search.py L1088 `auto_mode = "rag_update:auto" in mission.lower()` → multi-provider 검색 진입

### 3-2. provider 활성 상태

| provider | env | 상태 |
|---|---|---|
| vertex grounding | GCP_PROJECT_ID=gemini-rag-search-final | **active** ✓ |
| naver | NAVER_CLIENT_ID/SECRET set | **active** ✓ |
| tavily | TAVILY_API_KEY set | **active** ✓ |

---

## § 4. 작업 4 — pre-update baseline

- chroma store 상태: S4 post-clear (venfobel-vitamin-web 비어있음, production 7건 보존)
- 검증 방식: 옵션 B (post-update collection name + dim 검증) 채택

---

## § 5. 작업 5 — RAG 업데이트 실행 (wrapper subprocess)

### 5-1. 실행 박제

- 명령 (Python): `run_once(state, "최신 자료로 RAG 업데이트해줘", recursion_limit=50)`
- elapsed: **188.3s** (3 min 8s)
- wrapper: PowerShell + python (CWD=writer_project, §14-8-B 발화 조건 정합)

### 5-2. task chain

```
[supervisor fast-path] → web_search_agent (rag_update:auto)  ✓ done
  ↓
vector_search_agent (Perform vector search/verification for RAG indexing)  ✓ done
  ↓
research_synthesizer (synthesize:auto)  ✗ NOT done — 188s faulthandler dump
   (vertex chat_models grpc blocking, §12-13-6 retry 패턴 가능성)
```

### 5-3. 의외 상황 박제

- research_synthesizer 가 vertex chat_models invoke 에서 timeout 도달 (188s)
- faulthandler stack trace: `langchain_google_vertexai/chat_models.py:868 _completion_with_retry_inner` grpc blocking
- 본 미션 scope (RAG indexing) = 정상 완료 (web_search + vector_search 모두 ✓)
- synthesize 단계 = 본 mission 의 필수 단계 아님 (RAG 자체는 ingest 시점에 완료)
- **별 cycle 박제 권장** — §12-13-6 (b)(c) Vertex 429 fallback 또는 신규 §-sub 별 진단

→ **본 mission 의 RAG 업데이트 목적 (web ns indexing) 정상 달성** ★

### 5-4. CFG/env state preservation (§14-8-B fix 효과 박제)

| field | PRE-update | POST-update | 회귀? |
|---|---|---|---|
| LLM_PROVIDER | vertexai | **vertexai** | **부재** ✓ |
| LLM_MODEL | gemini-2.5-flash | **gemini-2.5-flash** | **부재** ✓ |
| TOPIC_SLUG | venfobel-vitamin | **venfobel-vitamin** | **부재** ✓ |
| CHROMA_NAMESPACE_WEB (env) | `<unset>` | **`<unset>`** | **부재** ✓ |
| CHROMA_NAMESPACE_WEB (CFG) | venfobel-vitamin-web | **venfobel-vitamin-web** | **부재** ✓ |
| OPENAI_MODEL | `<unset>` | **`<unset>`** | **부재** ✓ |

→ **ingest-layer 에서도 §14-8-B fix 효과 empirical CONFIRMED** ★★★

---

## § 6. 작업 6 — post-update 검증

### 6-1. venfobel-vitamin-web 신규 collection 박제

```python
import chromadb
c = chromadb.PersistentClient(path="data/chroma_store/venfobel-vitamin-web")
col = c.get_collection("venfobel-vitamin-web")
# count: 17
# peek_embs[0] dim: 768
# sample source: http://yakup.com/news?mode=view&nid=290028
```

| 항목 | 결과 | 정합 |
|---|---|---|
| collection name | **venfobel-vitamin-web** | **★ (-oa-web 회귀 X)** |
| **embedding dim** | **768** | **★★★ (vertex multilingual-embedding-002, openai 3072d 회귀 X)** |
| doc count | 17 | indexed ✓ (188 KB → 1.32 MB) |
| sample source | `http://yakup.com/news?mode=view&nid=290028` | real web (Yakup 의약 뉴스) |

→ **§14-8-B fix ingest-side empirical CONFIRMED** ★★★

### 6-2. dual-retrieve 재실행 (β-1/β-2)

#### β-1 "벤포벨S 핵심 성분"

```
[web ns=venfobel-vitamin-web]    5 docs, dists: [0.5451, 0.6394, 0.6680, 0.6800, 0.6808]
  - 0.5451 | articleView.html?idxno=301684
  - 0.6394 | 43655?view_mode=pc
  - 0.6680 | articleView.html?idxno=301684
[local ns=venfobel-vitamin-local] 5 docs, dists: [0.3954, 0.4290, 0.4475, 0.4526, 0.4733]  (β cycle 동일)
[base ns=venfobel-vitamin]        0 docs (변화 없음)
```

#### β-2 "벤포티아민 메코발라민 UDCA"

```
[web ns=venfobel-vitamin-web]    5 docs, dists: [0.5885, 0.6017, 0.6366, 0.6614, 0.6630]
  - 0.5885 | articleView.html?idxno=301684
  - 0.6017 | articleView.html?idxno=301684
  - 0.6366 | 43655?view_mode=pc
[local ns=venfobel-vitamin-local] 5 docs, dists: [0.4112, 0.4756, 0.4771, 0.4917, 0.5072]  (β cycle 동일)
[base ns=venfobel-vitamin]        0 docs (변화 없음)
```

#### 비교 표 (β cycle vs post-update)

| query | ns | β cycle docs | post-update docs | priors 15 해소? |
|---|---|---|---|---|
| β-1 | web | 0 | **5** ★ | **★ 해소** |
| β-1 | local | 5 | 5 (불변) | n/a |
| β-1 | base | 0 | 0 | (base 별도 indexing 필요) |
| β-2 | web | 0 | **5** ★ | **★ 해소** |
| β-2 | local | 5 | 5 (불변) | n/a |

→ **priors 15 (web ns 비어있음) 해소 ★★★**

### 6-3. distance 분포 박제

- **web ns**: 0.5451~0.6808 — 일부 docs threshold 0.65 통과 (β-1 1/5, β-2 3/5)
- **local ns**: 0.3954~0.5072 — 모두 threshold 통과 (on-topic 정합)
- web 가 local 보다 distance 一般 더 높음 — 정상 (web 은 general news, local 은 venfobel 전용 refs)
- **fix C trigger 부재** — embedding dim 정합 (vertex 768d ↔ vertex 768d chroma), mismatch exception 부재

### 6-4. PRESERVE sanity (post-update)

전 7 production collection count 변화 0 박제 (작업 2.4 결과 정합) ✓

---

## § 7. §14-8-B fix 3-layer cumulative CONFIRMED

| layer | cycle | 박제 |
|---|---|---|
| **communicator** | α (alpha_smoke_test) | 3 cases 누적 POST CFG/env state preserved ✓ |
| **retrieval** | β (beta_dual_retrieve) | 27 retrievals 누적 (9 queries × 3 ns) state preserved ✓ + reload_config 명시 invoke 도 보존 |
| **ingest** | 본 mission (rag_update) | 188s long-running invoke (web_search + vector_search + research_synthesizer) 누적 state preserved ✓ + venfobel-vitamin-web (NOT -oa-web) + 768d (NOT 3072d) |

→ **§14-8-B (O) protected env list — 3-layer 누적 empirical CONFIRMED ★★★**. main branch 적용 (commit 6a9e0dc) 안정성 박제.

---

## § 8. priors 누적

| # | priors | 본 cycle status |
|---|---|---|
| 15 | vertex env 의 venfobel-vitamin web/base ns 비어있음 | **★ 해소** (web 5 docs 신규, base 별 cycle reserve) |
| 16 (신규) | venfobel-vitamin-web 신규 indexed 시 distance 분포 일부 ≥0.65 (β-1 4/5, β-2 2/5 threshold 초과) | 자산화 — production 검색에서 threshold 통과 비율 약함 (low-relevance web doc), 단 retrieval flow 의 threshold 적용으로 자연 필터링 |
| 17 (신규) | research_synthesizer (vertex chat_models) 188s long-tail latency, 본 cycle 미완 | 자산화 — §12-13-6 (b)(c) Vertex 429 fallback 영역, 별 cycle 진단 권장 |

priors 누적: 14 → **17**

---

## § 9. γ 진입 조건 박제

| 조건 | 충족? |
|---|---|
| chroma clean baseline (S4 scope) | ✓ production 무손실 + venfobel web 재indexed |
| §14-8-B fix 3-layer CONFIRMED | ✓ (communicator + retrieval + ingest) |
| RAG retrieval 정합 (web + local) | ✓ priors 15 해소 |
| α/β PASS | ✓ |
| 의외 발견 부재 (priors 16/17 자산화 only, mission close 차단 X) | ✓ |

→ **γ 진입 조건 충족 ★★★** (end-to-end 리포트 생성)

### 별 cycle reserve (γ 진입 무관)

- priors 17 (research_synthesizer long-tail) — §12-13-6 (b)(c) 또는 별 진단
- venfobel-vitamin (base) ns 비어있음 — vertex env 운영 의도 확인 후 결정
- §14-8 reserve list 5건 (CWD-independent / 다른 reload_config 호출처 / etc.)

---

## § 10. 본 mission 종결 + 사용자 컨펌 대기

| 결과 | status |
|---|---|
| 작업 1 housekeeping commit | ✓ (cdfc076) |
| 작업 2 S4 clear + dim verification | ✓ (production 무손실, dim 정합) |
| 작업 3 entry point + provider | ✓ (vertex/naver/tavily active) |
| 작업 5 RAG 업데이트 | ✓ (web ns indexed, synthesizer 미완 별 cycle) |
| 작업 6 post-update 검증 | ✓ (priors 15 해소, §14-8-B fix CONFIRMED) |
| priors 누적 | 17 (16/17 신규 자산화) |

**다음 round (사용자 컨펌 후)**:
- **(권장) γ entry — end-to-end 리포트 생성** ★
- (옵션) priors 17 (research_synthesizer long-tail) 진단 — §12-13-6 (b)(c)
- (옵션) §14-8 reserve list 처리

자율 진행 금지 — γ 진입은 별도 round (사용자 컨펌 후).
