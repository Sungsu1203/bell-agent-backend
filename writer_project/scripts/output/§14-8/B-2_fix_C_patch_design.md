# §14-8-B B-2 — fix C patch 설계

**측정 일자:** 2026-05-17
**git HEAD:** 77c24ad (feature/vertex-web-search)
**미션:** fix C (embedding 일치성 검증) patch diff 설계 + 효과/한계 박제

---

## § 1. retrieve 호출 chain 박제 (B-2 spec step 1)

### 1-1. 단일 entry point 박제

```
agent/vector_search.py L66
  from tools.web_rag import retrieve
    ↓
tools/web_rag/__init__.py L83-85
  def retrieve(*args, **kwargs):
      from .ingest import retrieve as _fn
      return _call_maybe_tool(_fn, *args, **kwargs)
    ↓
tools/web_rag/ingest.py
  (re-export 또는 import 통해 ingest_vector.py 의 retrieve)
    ↓
tools/web_rag/ingest_vector.py L1534
  def retrieve(query, *, top_k=5, namespace=None, ...) — **actual definition**
```

### 1-2. _call_retrieve 호출처 박제

| caller | line | 박제 |
|---|---|---|
| `agent/vector_search.py:480` | `_get(ns_name, k_web, "web")` → `_call_retrieve(query, ns_name=ns_name, k=k)` | web/local 단계 |
| `agent/vector_search.py:518` | `_dedupe_docs(_call_retrieve(query, ns_name=ns_default, k=remaining))` | include_base fallback |
| `agent/vector_search.py:559` | `_dedupe_docs(_call_retrieve(query, ns_name=ns_default, k=top_k))` | web/local empty fallback |

→ **모든 retrieve 호출이 단일 entry (ingest_vector.py:1534) 통과** ★

### 1-3. 결론

→ fix C 의 적용 위치 = **`tools/web_rag/ingest_vector.py:1534 retrieve()`** 단일 (user plan (ii) 정합)
→ (i) `_call_retrieve` / (iii) `_dual_retrieve` 위치 적용 시 over-fix (cover 영역 동일)

---

## § 2. 기존 mismatch 처리 logic 박제 (★ 중요 발견)

### 2-1. ingest_vector.py L1656-1671 — **이미 mismatch detect + raise 작동**

```python
except Exception as e:
    emsg = (str(e) or "").lower()
    mismatch_signals = (
        "dimension" in emsg or
        ("embed" in emsg and "mismatch" in emsg) or
        ("expected" in emsg and "got" in emsg and "dimension" in emsg)
    )
    if mismatch_signals:
        raise RuntimeError(
            "Vector query failed due to a likely embedding model/dimension mismatch between "
            "ingestion and retrieval.\n\n"
            "How to fix:\n"
            ...
        ) from e
    logger.debug("[retrieve-fast] direct query failed; falling back to retriever: %s", e)
```

### 2-2. agent/vector_search.py L436-438 — **catch + log + empty 반환 작동**

```python
except Exception as e:
    logger.warning("retrieve 실패(ns='%s'): %s", ns_name, e)
    return []
```

### 2-3. wrapper trace recheck 의 시그널 정합

```
retrieve 실패(ns='venfobel-vitamin-oa-web'): Vector query failed due to a likely 
embedding model/dimension mismatch between ingestion and retrieval.
```

→ **현재 logic 이미 mismatch detect + empty 반환 정상 작동**

---

## § 3. fix C 의 정확한 추가 가치 + 한계 박제

### 3-1. fix C 의 추가 가치

| 항목 | 박제 |
|---|---|
| pre-check 로 exception 비용 회피 | query → mismatch raise → catch chain 우회 |
| 비용 절감 | exception path (raise + traceback) 비용 minor |
| log clarity | fix-C marker 로 mismatch 박제 명확화 |

### 3-2. fix C 의 한계 (★ 박제)

**한계 1**: 본 미션 60s+ timeout 완전 해결 보장 못 함
- mismatch handling 이미 작동 — fix C 는 exception 비용 미세 감소만
- wrapper 환경 60s+ timeout 의 본질 = (vertex 404 + dual-retrieve mismatch + fallback chain) combination
- fix C 는 mismatch 단독 비용 감소만 → 본질 timeout 의 일부만 fix

**한계 2**: vertex 404 (gpt-4o 모델 호출) 자체는 fix 안 됨
- variant-B stderr 의 결정적 시그널 `[web_search] Vertex failed: 404 NOT_FOUND for gpt-4o`
- fix C 는 chroma retrieve 영역만 — vertex API 호출 path 무관
- vertex 404 origin (gpt-4o 호출 mechanism) 진단 = 별 cycle reserve

**한계 3**: dual-retrieve fallback chain 시간 소요 미 fix
- web/local empty → base ns fallback (L559)
- fallback 도 같은 mismatch 가능
- fix C 는 단일 retrieve 호출의 pre-check만

### 3-3. fix C 의 효과 검증 필요 (B-4)

- B-3 patch 적용 후 B-4 driver 재측정으로 직접 검증
- 효과 충분 (timeout 회피) → 본 미션 close
- 효과 부족 → 추가 fix (fix A++/B/G) 별 cycle

---

## § 4. fix C patch diff 설계

### 4-1. patch 위치

`tools/web_rag/ingest_vector.py` retrieve() 함수 내부 L1616 (q_emb 계산 + q_dim log 직후) ~ L1618 (query 호출 직전) 사이.

### 4-2. patch diff (proposed)

```diff
--- a/tools/web_rag/ingest_vector.py
+++ b/tools/web_rag/ingest_vector.py
@@ -1607,7 +1622,7 @@ def retrieve(
     try:
         q_emb = emb_fn.embed_query(q) if hasattr(emb_fn, "embed_query") else emb_fn(q)
         n = max(1, int(top_k or 5))
         # ✅ [CHECK] query embedding 차원 확인 (dimension mismatch는 보통 예외지만, 이상치 탐지용)
         try:
             q_dim = len(q_emb) if hasattr(q_emb, "__len__") else None
             logger.warning("[CHECK][retrieve] ns=%s dir=%s top_k=%d q_len=%d q_emb_dim=%s",
                            ns, pd, n, len(q), q_dim)
         except Exception:
-            pass
+            q_dim = None
+
+        # ★ §14-8-B fix C: collection embedding dim 사전 검증 (mismatch 시 query 우회 + empty 반환)
+        # 효과: exception 비용 회피 (query → mismatch raise → catch 우회)
+        # 영향: runpy 환경 무영향 (mismatch 없음 → skip 발동 안 함), wrapper 환경 mismatch 시 빠른 skip
+        # 박제: scripts/output/§14-8/B-2_fix_C_patch_design.md
+        try:
+            if q_dim is not None:
+                peek = vs._collection.peek(limit=1)
+                peek_embs = (peek or {}).get("embeddings") or []
+                if peek_embs and isinstance(peek_embs, list) and len(peek_embs) > 0:
+                    first_emb = peek_embs[0]
+                    coll_dim = len(first_emb) if hasattr(first_emb, "__len__") else None
+                    if coll_dim is not None and coll_dim != q_dim:
+                        logger.warning(
+                            "[fix-C][retrieve] embedding dim mismatch (ns=%s coll_dim=%d q_dim=%d) — skip query, return empty",
+                            ns, coll_dim, q_dim
+                        )
+                        return []
+        except Exception as e:
+            logger.debug("[fix-C][retrieve] dim pre-check skipped: %s", e)

         res = vs._collection.query(
             query_embeddings=[q_emb],
             n_results=n,
             include=cast(Include, ["documents", "metadatas", "distances"]),
         )
```

### 4-3. patch 메타

| metric | value |
|---|---|
| 추가 lines | ~18 (comment 포함) |
| 변경 lines | 1 (`pass` → `q_dim = None`, q_dim 초기화) |
| 영향 함수 | `retrieve()` (단일) |
| 영향 caller | 모든 retrieve 호출 (단일 entry) |
| §14-7 d92394f 와 spec 범위 정합 | ★ (11/-5 lines, 본 fix 19/-1) |

### 4-4. patch logic 박제

1. `q_dim` 변수 초기화 (try 안에서 set 됐던 것을 except 에도 보장)
2. `vs._collection.peek(limit=1)` 호출 — collection 의 첫 doc embedding 1건 fetch
3. peek embeddings[0] 의 dim 추출
4. q_dim vs coll_dim 비교 → mismatch 시:
   - log warning (fix-C marker)
   - empty `[]` return (query 우회)
5. peek 실패 / collection empty 시: silent skip (debug log) → 기존 logic 그대로 진행

### 4-5. 사이드 이펙트 검토

| 항목 | 영향 |
|---|---|
| runpy 환경 (D1) | 영향 무 — mismatch 없으면 skip 발동 안 함 |
| wrapper 환경 (driver subprocess) | 빠른 empty return — 기존 exception path 회피 |
| empty collection (count=0) | peek embeddings 빈 list → skip 발동 안 함 → 기존 logic 진행 |
| chroma client 의 peek() API 가능성 | chromadb 표준 API — risk 낮음 |
| performance | peek(limit=1) 1회 추가 호출 — milliseconds |
| 회귀 risk | 낮음 — mismatch 시 empty 반환은 기존 logic 과 동일 결과 |

---

## § 5. user 컨펌 Q list

**Q1.** § 1 retrieve 호출 chain (ingest_vector.py:1534 단일 entry) 박제 합의 OK?

**Q2.** § 2 — 기존 mismatch handling (L1656-1671 + L436-438) **이미 작동** 박제 합의 OK?

**Q3.** § 3.2 fix C 한계 3건:
- (1) 본 미션 60s+ timeout 완전 해결 보장 못 함
- (2) vertex 404 (gpt-4o) 자체 fix 안 됨
- (3) dual-retrieve fallback chain 시간 소요 미 fix
- 합의 OK?

**Q4.** § 4 patch diff (proposed) — 18/-1 lines, ingest_vector.py L1616 직후 추가:
- (a) 그대로 진입 OK
- (b) logic 보강 (예: dual-retrieve cache for mismatch namespace 추가)
- (c) 위치 변경 (예: dual-retrieve L391-450 에 추가 cache logic)

**Q5.** 다음 단계 — **§14-8-B B-3 (patch 적용 + commit) 진입** OK?
- B-3: patch 적용 (production code edit) + git diff 박제
- B-4: patched driver 재측정 (variant-A 1회 + driver 측정 1회)
- B-5: 효과 검증 + 본 미션 정량 박제 (또는 효과 부족 시 추가 fix 별 cycle)
