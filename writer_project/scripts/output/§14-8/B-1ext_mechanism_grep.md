# §14-8-B B-1ext — mechanism 추가 진단 grep

**측정 일자:** 2026-05-17
**git HEAD:** 77c24ad (feature/vertex-web-search)
**미션:** B-1 mystery (wrapper subprocess CFG.CHROMA_NAMESPACE_WEB 가 venfobel-vitamin-oa-web 로 resolve 되는 mechanism) 박제

---

## § 1. grep 4 영역 + 4 키워드 결과 (read-only, 비용 0)

### 1-1. (a) 자식 script `_step3_dry_run_rag_update.py` chroma namespace 사용처

| line | 박제 |
|---|---|
| L48-49 | env_snapshot keys: `CHROMA_NAMESPACE, CHROMA_NAMESPACE_WEB, CHROMA_NAMESPACE_LOCAL, CHROMA_DIR` ← env_trace 박제 대상만 |
| L62 | `load_dotenv(env_vertex, override=True)` ← .env.vertex 명시 로드 (vanilla env 에서도 작동, D2 STDOUT 박제 정합) |
| L170 | `ns_web = f"{args.topic_slug}-web"` ← clear subprocess 용 namespace ("ai-generated-creative-ad-platforms-web") |
| L215-224 | **state 구성 (★)**: `"topic_slug": args.topic_slug` = "ai-generated-creative-ad-platforms" |
| L230 | `result_state = graph.invoke(state, ...)` ← invoke 호출 |

→ **자식 script 에 venfobel hardcode 부재** (Q3 후보 (a) 약화)
→ state["topic_slug"] = driver 명시 인자 = "ai-generated-creative-ad-platforms" (정확)

### 1-2. (b) chroma client behavior

| source | line | 박제 |
|---|---|---|
| `utils/rag_utils.py:501` | `client = chromadb.PersistentClient(path=p)` | 일반 client init |
| `check_chunks.py:3` | `chromadb.PersistentClient(path="./data/chroma_store/venfobel-vitamin-oa-local")` | **진단 script (production 무관)** |
| `tools/diagnose_richness.py:3` | PersistentClient.start() Rust binding panic note | 진단 script |
| `scripts/output/§14-3/_phase3/_chroma_diag.py:16,17,49,50` | `chromadb.PersistentClient(path=str(nd))` + `client.list_collections()` | **진단 script (별 cycle)** |

→ **`list_collections()` production 사용 부재** (Q3 후보 (b) 약화)
→ chroma client 가 의도하지 않은 collection 자동 query 시그널 부재

### 1-3. (c) `_dual_retrieve` internal logic (agent/vector_search.py L391-450)

```python
# L398-404
ns_web = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()
ns_loc = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()
# ✅ env가 비어 있으면 ns_default 기반으로 자동 파생 (ingest 쪽 split 네임스페이스와 정합)
if not ns_web:
    ns_web = f"{ns_default}-web"
if not ns_loc:
    ns_loc = f"{ns_default}-local"
```

→ **CFG.CHROMA_NAMESPACE_WEB 우선, 빈 값이면 ns_default-web 으로 derive**
→ ns_default 는 호출 인자 — 호출처에서 결정

### 1-4. (d) ns 결정 logic (agent/vector_search.py L705-710 — 호출처)

```python
# L705-710
topic_slug_raw: str = (state.get("topic_slug") or getattr(config.CFG, "TOPIC_SLUG", "") or "default").strip()
env_ns_raw = (_cfg_str("CHROMA_NAMESPACE", "") or "").strip()
topic_slug = _wr_sanitize_ns(topic_slug_raw)
env_ns    = _wr_sanitize_ns(env_ns_raw) if env_ns_raw else ""
ns: str   = env_ns or _wr_sanitize_ns(f"{topic_slug}-default")
```

→ **ns = CFG.CHROMA_NAMESPACE (set 시) or `{topic_slug}-default` (auto-derive)**
→ topic_slug = state.get("topic_slug") (자식 script L216 에서 "ai-generated-creative-ad-platforms" set)

### 1-5. CFG auto-derive (core/config.py L440-453)

```python
# L447-453
slug = _sanitize_ns(self.TOPIC_SLUG or "default")
if not (self.CHROMA_NAMESPACE or "").strip():
    self.CHROMA_NAMESPACE = slug                        # = "ai-generated-creative-ad-platforms"
if not (self.CHROMA_NAMESPACE_WEB or "").strip():
    self.CHROMA_NAMESPACE_WEB = f"{slug}-web"           # = "ai-generated-creative-ad-platforms-web"
if not (self.CHROMA_NAMESPACE_LOCAL or "").strip():
    self.CHROMA_NAMESPACE_LOCAL = f"{slug}-local"
```

→ **expected**: CFG.CHROMA_NAMESPACE_WEB = "ai-generated-creative-ad-platforms-web"

---

## § 2. mechanism mystery — expected vs actual 박제

### 2-1. expected (위 logic chain 정합)

| step | expected 값 |
|---|---|
| wrapper subprocess env TOPIC_SLUG | "ai-generated-creative-ad-platforms" (driver 명시 set) |
| wrapper subprocess env CHROMA_NAMESPACE | "" (driver POLLUTION pop) |
| CFG.TOPIC_SLUG | "ai-generated-creative-ad-platforms" |
| CFG.CHROMA_NAMESPACE_WEB (auto-derive) | "ai-generated-creative-ad-platforms-web" |
| state["topic_slug"] (자식 script L216) | "ai-generated-creative-ad-platforms" |
| vector_search ns (L710) | "ai-generated-creative-ad-platforms" (env_ns or slug) |
| dual-retrieve ns_web (L401-404) | "ai-generated-creative-ad-platforms-web" |

### 2-2. actual (wrapper recheck f_log 박제)

```
[CHECK][dual-retrieve][count] web=150 (ns=venfobel-vitamin-oa-web dir=...\chroma_store\venfobel-vitamin-oa-web)
| local=349 (ns=venfobel-vitamin-oa-local) | base=0 (ns=venfobel-vitamin-oa)
```

→ ns_web = "venfobel-vitamin-oa-web", ns_loc = "venfobel-vitamin-oa-local", ns_default = "venfobel-vitamin-oa"

### 2-3. mismatch path 추정 (mystery — 본 B-1ext 도 미해소)

| 가능 path | 의심도 |
|---|---|
| **(α)** wrapper subprocess 안에서 어딘가 `reload_config()` 호출 → CFG mutate (env 변동 후 재build) | ★ 中-高 |
| **(β)** invoke 진행 중 supervisor 가 `start_new_topic()` 호출 → state["topic_slug"] 또는 CFG.TOPIC_SLUG mutate | ★ 中 — but state.get("topic_slug")=ai-generated 면 영향 무 |
| **(γ)** **CFG 가 instantiate 시점에 .env.openai 가 어디서 load** — `_apply_provider_overlay` 가 정상이라면 .env.vertex 만 load 인데 어떤 path 가 .env.openai 도 load | ★ 中-高 — wrapper-only 발현 시그널과 정합 |
| **(δ)** vector_search 의 `_cfg_str` 가 CFG 아닌 별도 os.environ read | △ — _cfg_str 정의 추가 grep 필요 |
| **(ε)** chroma client 가 persist_dir 의 다른 namespace collection 도 발견 + dual-retrieve 가 의도하지 않은 query | 낮음 (L1-2 결과로 약화) |

### 2-4. 추가 진단 필요 (별 cycle 또는 §14-8-B 진행 중)

- `_cfg_str` 정의 grep — CFG attribute vs os.environ read 확인
- `reload_config()` 호출처 grep — invoke 진행 중 mutate 가능성
- `start_new_topic()` 호출처 grep — supervisor / communicator 의 토픽 reset 가능성
- wrapper subprocess 환경에서 `.env.openai` 의 load 가능 path 추적

---

## § 3. fix candidate 재평가 (user plan Q5 정합)

### 3-1. mechanism 박제 결과

- mystery 부분 박제만 (expected vs actual 명확화)
- **정확한 mutate path 미박제** — fix candidate 정확 선택 어려움

### 3-2. user plan 박제 정합 — **fix C (embedding 일치성 검증) fallback 권장**

> mechanism 미박제 상태에서 fix 선택 risk (잘못된 fix → 본 미션 재측정 실패 → re-cycle 비용)
> B-1 연장에도 mechanism 미박제 시 → (C) embedding 일치성 검증 fallback (mechanism 무관 적용 가능)

→ **본 B-1ext 결과 → fix C fallback 권장 정합**

### 3-3. fix C 의 정확한 적용 위치 (B-2 진입 시 sharpening)

| candidate 위치 | 박제 |
|---|---|
| `agent/vector_search.py _call_retrieve` (L423) | retrieve 직전 ingestion / retrieval embedding dim 일치 검증 추가 |
| `tools/web_rag/ingest_vector.py` 의 retrieve 함수 (L1613 박제: `[CHECK][retrieve] ns=... q_emb_dim=%s`) | q_emb_dim log 사전 박제 — 검증 점 확실 |
| `_dual_retrieve` (L391-450) | 호출 전 ingestion/retrieval embedding 일치 검증 + mismatch namespace skip |

### 3-4. fix C 의 영향

- **즉시 적용 가능** (mechanism 무관)
- production code 변경 — §14-7 fix commit d92394f 와 동등 spec 범위
- retrieve 비용 증가 negligible (embedding dim 비교만)
- mismatch namespace 강제 skip → wrapper 환경에서 timeout 회피
- runpy 환경에는 영향 무 (mismatch 없으므로 skip 안 됨)

---

## § 4. 추가 후보 (a)/(b) 약화 박제

| 후보 | 박제 결과 | 변경 |
|---|---|---|
| (a) 자식 script chroma namespace hardcode | venfobel hardcode 부재, state 구성 정확 | **약화** |
| (b) chroma client list_collections() 자동 query | production 사용 부재 | **약화** |
| (c) dual-retrieve CFG 우회 + list_collections() | _dual_retrieve 가 CFG read 정확, list_collections 호출 부재 | **약화** |
| (d) vertex_web_search ingest path | 추가 grep 필요 (별 cycle) | △ |
| (e) wrapper 환경 .env.openai load path | **(γ) 와 정합 — 가장 의심** | ★ |

→ Q3 박제 (a) 가장 의심 **기각**. (γ)+(e) 통합 = "wrapper 환경에서 .env.openai 가 어디서 load" 가 가장 유력.

---

## § 5. 본 B-1ext 결론 박제 (Q5 user plan 정합)

| 항목 | 박제 |
|---|---|
| mechanism 박제 | **부분** (expected vs actual 명확, 정확한 mutate path 미박제) |
| mystery path 후보 | (α) reload_config / (β) start_new_topic / **(γ) .env.openai load** / (δ) _cfg_str / (ε) chroma client |
| 가장 유력 path | **(γ) wrapper 환경에서 .env.openai 가 어디서 load** ★ |
| 추가 진단 필요 | _cfg_str, reload_config, start_new_topic, .env.openai load path |
| **fix candidate 권장** | **★ (C) embedding 일치성 검증 fallback** (mechanism 무관 적용 가능, user plan Q5 정합) |

---

## § 6. user 컨펌 Q list

**Q1.** § 1 grep 4 영역 결과 박제 합의 OK?

**Q2.** § 2 mismatch path 추정 5건 — (γ) 가장 유력 합의 OK?

**Q3.** § 4 추가 후보 약화 — (a) 가장 의심 **기각** + (γ)+(e) 통합 가장 유력 합의 OK?

**Q4.** § 3.2 — **fix candidate C (embedding 일치성 검증) fallback 권장** 합의 OK?

**Q5.** § 3.3 — fix C 정확한 적용 위치:
- (i) `agent/vector_search.py _call_retrieve` L423 직전 검증
- (ii) `tools/web_rag/ingest_vector.py` retrieve 함수 (q_emb_dim log 박제 점)
- (iii) `_dual_retrieve` (L391-450) 의 mismatch namespace 강제 skip
- 또는 통합

**Q6.** 다음 단계 — **§14-8-B B-2 (fix patch 설계) 진입** OK?
