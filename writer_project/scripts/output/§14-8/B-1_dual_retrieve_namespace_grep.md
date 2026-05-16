# §14-8-B B-1 — dual-retrieve namespace 결정 logic grep

**측정 일자:** 2026-05-17
**git HEAD:** 77c24ad (feature/vertex-web-search)
**미션:** wrapper subprocess 환경에서 dual-retrieve 가 venfobel-vitamin-oa-web 를 query 하는 mechanism 박제 + fix candidate 권장

---

## § 1. grep 5 영역 + 6 키워드 결과

### 1-1. `_dual_retrieve` 함수 정의 + 호출처 박제

**정의 (단일 source of truth)**:
- `agent/vector_search.py:391` `def _dual_retrieve(query: str, *, top_k: int, ns_default: str, persist_dir: str) -> List[Any]:`

**내부 logic 핵심**:
- L398-399: `ns_web = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()` / `ns_loc = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()`
- L423: `def _call_retrieve(q: str, *, ns_name: str, k: int) -> List[Any]:`
- L451: `[CHECK][dual-retrieve][count] web=%s (ns=%s dir=%s) | local=%s (ns=%s dir=%s) | base=%s (ns=%s dir=%s)`
- L506: `[CHECK][dual-retrieve][peek] k=%d split(web=%d,local=%d) raw(web=%d,local=%d) dedupe(web=%d,local=%d)`
- L575: `[dual-retrieve] web/local empty → FALLBACK to base ns='%s' (%d hits)` ★ fallback chain
- L612: `[CHECK][dual-retrieve][merged] src=%s | ns=%s`

**호출처 (agent/vector_search.py 내부)**:
- L852: `docs1 = _dual_retrieve(sq, top_k=1, ns_default=ns, persist_dir=persist_dir)`
- L1191: `retrieved_docs = _dual_retrieve(user_q_clean, top_k=TOP_K, ...)`
- L1363, L1398, L1433: 동일 호출 패턴

→ `_dual_retrieve` 의 `ns_web` / `ns_loc` 은 **`_cfg_str("CHROMA_NAMESPACE_WEB", "")` (CFG attribute)** 직접 read.

### 1-2. venfobel-vitamin-oa namespace 의 hardcode origin

| source | line | 값 | 영향 |
|---|---|---|---|
| **`.env.openai:56-58`** | CHROMA_NAMESPACE=venfobel-vitamin-oa / -web / -local | ★ **hardcode** | provider=openai overlay 시 set |
| **`.env.anthropic:50-52`** | CHROMA_NAMESPACE=venfobel-vitamin-oa / -web / -local | ★ hardcode | provider=anthropic overlay 시 set |
| `.env.vertex:49-51` | (주석 처리) | — | 영향 없음 (정상) |
| `env_raw.txt:117-119` | (주석 처리) | — | 영향 없음 |

→ **`.env.openai` / `.env.anthropic` 가 wrapper subprocess 환경에서 load 되면 CHROMA_NAMESPACE=venfobel-vitamin-oa 가 process env 에 set**

### 1-3. 글로벌 .env L50 박제 ★

```
TOPIC_SLUG=venfobel-vitamin
```

→ 글로벌 .env 의 default TOPIC_SLUG = venfobel-vitamin
→ driver wrapper 가 env["TOPIC_SLUG"] = "ai-generated-creative-ad-platforms" 명시 set 하므로 process env 에서는 override 정합
→ 단 글로벌 .env L122-124 의 CHROMA_NAMESPACE 는 주석 처리 (정상)

### 1-4. provider overlay logic (core/config.py L106-127)

```python
def _apply_provider_overlay(*, verbose: bool) -> None:
    prov = (os.getenv("LLM_PROVIDER", "") or "").strip().lower()
    if not prov: return
    prov_file = "vertex" if prov in {"vertex", "vertexai"} else prov
    root = Path(os.getenv("PROJECT_ROOT", ...)).resolve()
    overlay_path = root / f".env.{prov_file}"
    if overlay_path.exists():
        load_dotenv(overlay_path, override=True)  # ★ override=True
```

→ **LLM_PROVIDER=vertexai 면 `.env.vertex` 만 load** (`.env.openai` 안 load)
→ `.env.vertex` 의 CHROMA_NAMESPACE 는 주석 처리 → override 영향 무

### 1-5. topic preset logic (core/config.py L130-150)

```python
def _apply_topic_preset(*, verbose: bool) -> None:
    slug = os.getenv("TOPIC_SLUG", "").strip()
    if not slug: return
    preset_path = root / "topics" / f"{slug}.env"
    if preset_path.exists():
        load_dotenv(preset_path, override=True)
```

→ TOPIC_SLUG 별 `topics/<slug>.env` load (override=True)
→ topics/ai-generated-creative-ad-platforms.env 에 **CHROMA_NAMESPACE hardcode 없음 박제** (file read 결과)
→ 토픽 프리셋 영향 무

### 1-6. CFG auto-derive (core/config.py L440-453)

```python
# ── CHROMA_NAMESPACE 자동 파생 ──
if not (self.CHROMA_NAMESPACE or "").strip():
    self.CHROMA_NAMESPACE = slug  # = TOPIC_SLUG
if not (self.CHROMA_NAMESPACE_WEB or "").strip():
    self.CHROMA_NAMESPACE_WEB = f"{slug}-web"
if not (self.CHROMA_NAMESPACE_LOCAL or "").strip():
    self.CHROMA_NAMESPACE_LOCAL = f"{slug}-local"
```

→ CFG.CHROMA_NAMESPACE_WEB 가 set 되어 있지 않으면 `{slug}-web` 으로 auto-derive
→ wrapper 환경에서 TOPIC_SLUG=ai-generated-creative-ad-platforms 라면 `ai-generated-creative-ad-platforms-web` 정상

### 1-7. core/topic.py L141 — MIRROR_STATE_TO_ENV

```python
if _cfg_bool("MIRROR_STATE_TO_ENV", True):
    os.environ["CHROMA_NAMESPACE"] = ns
    os.environ["CHROMA_DIR"] = chroma_dir
```

→ MIRROR_STATE_TO_ENV=True 면 start_new_topic() 호출 시 process env mutate
→ **driver wrapper env: MIRROR_STATE_TO_ENV=0 명시 set** → mutate 비활성
→ 본 path 영향 무

---

## § 2. **미해결 mechanism 박제 (★ 추가 진단 필요)**

### 2-1. mystery 박제

| step | 박제 |
|---|---|
| wrapper subprocess env | LLM_PROVIDER=vertexai, TOPIC_SLUG=ai-generated-creative-ad-platforms, MIRROR_STATE_TO_ENV=0, CHROMA_NAMESPACE=(빈 값) |
| _apply_provider_overlay | .env.vertex load (CHROMA_NAMESPACE 주석 처리) |
| _apply_topic_preset | topics/ai-generated-creative-ad-platforms.env load (CHROMA_NAMESPACE hardcode 없음) |
| CFG.CHROMA_NAMESPACE_WEB | (expected: ai-generated-creative-ad-platforms-web) |
| **dual-retrieve 실제 query namespace** | **venfobel-vitamin-oa-web** ★ |

→ **expected vs actual 의 mismatch — mechanism 미박제**

### 2-2. 가능 추가 후보 (B-1 추가 진단 또는 별 cycle)

| 후보 | 의심도 |
|---|---|
| **(a)** 자식 script (`_step3_dry_run_rag_update.py`) 가 chroma namespace 명시 hardcode | ★ 高 — 자식 script read 필요 |
| **(b)** chroma client 가 persist directory scan → 모든 collection list → 의도하지 않은 collection query | 中 |
| **(c)** dual-retrieve 가 CFG attribute 우회 + chroma client 의 list_collections() 호출 | 中 |
| **(d)** dual-retrieve 가 vertex_web_search 결과를 venfobel-vitamin-oa-web 에 ingest 시도 | 中 |
| **(e)** wrapper 환경에서 .env.openai 가 load 되는 path (provider overlay 외) 존재 | 中 |

### 2-3. 자식 script (`_step3_dry_run_rag_update.py`) 추가 grep 필요 reserve

- 자식 script 의 chroma namespace 명시 처리
- venfobel hardcode 가능성
- dual-retrieve 호출처 + namespace 인자 전달

→ **B-1 추가 진단** 또는 **B-2 진입 시 추가 grep**

---

## § 3. fix candidate 3건 + 신규 후보 박제

### 3-A. fix candidate A — dual-retrieve namespace 차단

| 항목 | 박제 |
|---|---|
| 위치 | agent/vector_search.py:391 _dual_retrieve |
| patch | dual-retrieve 자체 비활성화 또는 namespace mismatch 시 skip |
| 영향 | production code 변경 大 — 비권장 |
| 의심도 | 낮음 (본질 fix 아님) |

### 3-B. fix candidate B — TOPIC_SLUG 별 namespace 격리 강화

| 항목 | 박제 |
|---|---|
| 위치 | core/config.py L440-453 auto-derive logic 강화 |
| patch | CFG.CHROMA_NAMESPACE_WEB 가 TOPIC_SLUG 와 mismatch 시 강제 derive |
| 영향 | core/config.py 변경 — 영향 평가 필요 |
| 의심도 | 中 — mechanism 명확 후 적용 |

### 3-C. fix candidate C — embedding model 일치성 검증 단계 추가

| 항목 | 박제 |
|---|---|
| 위치 | agent/vector_search.py _call_retrieve 또는 tools/web_rag/ingest_vector.py |
| patch | retrieve 직전에 ingestion embedding dim vs retrieval embedding dim 일치 검증 → mismatch 시 빠른 fail/skip |
| 영향 | retrieve 비용 증가 (negligible) |
| 의심도 | ★ 中-高 (직접 mismatch 차단, mechanism 무관) |

### 3-D (신규 후보) — `.env.openai` / `.env.anthropic` 의 CHROMA_NAMESPACE hardcode 제거

| 항목 | 박제 |
|---|---|
| 위치 | .env.openai L56-58, .env.anthropic L50-52 |
| patch | venfobel-vitamin-oa hardcode 제거 → CFG auto-derive 활용 |
| 영향 | .env 파일 수정 — 다른 토픽 사용 시 영향 |
| 의심도 | ★ 中 — origin 정확히 차단, 단 wrapper 환경에서 .env.openai 가 어떻게 load 되는지 미확정 |

### 3-E (신규 후보) — chroma persist directory 격리 강화

| 항목 | 박제 |
|---|---|
| 위치 | tools/web_rag/ingest_vector.py 의 persist_dir 결정 logic |
| patch | TOPIC_SLUG 별 persist_dir 격리 강화 + 다른 namespace 의 collection 무시 |
| 영향 | chroma data 구조 변경 가능성 |
| 의심도 | 中 |

---

## § 4. 권장 다음 단계 (B-1 후 사용자 컨펌)

### 4-1. mechanism 완전 박제 필요 (★ 우선)

본 B-1 grep 결과 **mystery 박제 미해소**:
- wrapper subprocess CFG.CHROMA_NAMESPACE_WEB 가 venfobel-vitamin-oa-web 로 set 되는 정확한 mechanism 미확정
- fix candidate 선택은 mechanism 확정 후 정확

### 4-2. **B-1 연장 권장** — 추가 진단 1건

자식 script (`_step3_dry_run_rag_update.py`) 의 chroma namespace 명시 hardcode 박제 — read-only, 추가 측정 비용 0

박제 → `scripts/output/§14-8/B-1_step3_namespace_check.md`

### 4-3. 또는 sub-cycle 진입

본 cycle close 후 별 sub-cycle (§14-8-B-mechanism) 진입 — chroma namespace mechanism 정확한 진단 후 fix 설계

### 4-4. fix-path 직행 (mechanism 무관 fix)

fix candidate C (embedding model 일치성 검증) 는 mechanism 무관하게 mismatch 차단 — 즉시 fix 가능
- 단 production code 변경 — 본 미션 정신 정합 검토 필요 (§14-7 fix commit d92394f 와 동등)

---

## § 5. user 컨펌 Q list

**Q1.** § 1 grep 결과 (venfobel-vitamin namespace 의 hardcode origin = .env.openai/anthropic + 글로벌 .env TOPIC_SLUG) 박제 합의 OK?

**Q2.** § 2.1 mystery — wrapper subprocess CFG.CHROMA_NAMESPACE_WEB venfobel resolve mechanism **미박제** 합의 OK?

**Q3.** § 2.2 추가 후보 5건 (a~e) 중 (a) 자식 script chroma namespace hardcode 가장 의심 합의 OK?

**Q4.** § 3 fix candidate 5건 (A/B/C/D/E) 중 우선:
- **(C) embedding 일치성 검증** (mechanism 무관, 즉시 적용 가능)
- **(D) .env.openai/anthropic hardcode 제거** (origin 차단, 단 mechanism 미확정)
- **(B) CHROMA_NAMESPACE_WEB auto-derive 강화** (mechanism 확정 후)
- 또는 (A/E)

**Q5.** § 4 다음 단계:
- **(시나리오 1)** § 4.2 B-1 연장 — 자식 script chroma namespace grep 박제
- **(시나리오 2)** § 4.3 sub-cycle 진입 — mechanism 완전 진단 후 fix
- **(시나리오 3)** § 4.4 fix-path 직행 (fix C — embedding 일치성 검증)
- **(시나리오 4)** 병행
