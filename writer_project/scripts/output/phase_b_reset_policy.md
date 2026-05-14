# §14-2 Phase B — Chroma reset 정책 박제

생성: 2026-05-15 (dry-run 후속)

## 배경
- dry-run (commit `9fda4ec`) 진입 시 supervisor diag: `ns_web=112`, `ns_local=349` 누적 관측.
- 누적 web chunks 가 patch 전후 비교 측정의 절대값 신뢰성을 떨어뜨림.
- 정책 결정 위해 코드 lifecycle 조사.

## 조사 결과

### Chroma reset 함수 (writer_project/tools/web_rag/ingest_vector.py)

| 함수 | 위치 | 동작 | 사용 적합성 |
|---|---|---|---|
| `ensure_vector_store_cleared_once(ns, pd)` | :744 | `CLEAR_CHROMA_ON_START` / `CLEAR_ON_FIRST_VECTOR` env 켜진 경우에만, 그리고 `_CLEARED_ONCE_KEYS` 가드로 **process 당 1회만** clear | driver multi-invoke 와 부적합 (첫 invoke 만 clear) |
| `clear_vector_store(ns, pd)` | :654 | namespace+persist_dir 지정 clear. `_clear_once_guard` runtime 가드 존재 — 동일 (pd, ns) 중복 차단 | runtime guard 우회 필요 또는 subprocess 분리 |
| `delete_seen_source_hashes(ns, pd)` | :666 caller | stored_urls(seen-hash) 캐시도 함께 삭제 | clear_vector_store 가 내부 호출 |

### Namespace 구조
- `.env:121`: `CHROMA_DIR=data/chroma_store`
- `CHROMA_NAMESPACE_WEB` / `CHROMA_NAMESPACE_LOCAL` 로 split 운영
- `topics/<slug>.env` 에 topic 별 ns 박힘 (자동 로드 확인 완료, dry-run 로그)
- venfobel-vitamin 현황: `ns_local=349` (PDF chunks, 보존 대상), `ns_web=112` (web/vertex 결과 누적, reset 대상)

### graph 자체의 reset 호출 위치
- `agent/vector_search.py:787-794`: `ensure_vector_store_cleared_once` 를 ns_base/ns_web/ns_loc 각각 호출
- 그러나 `_CLEARED_ONCE_KEYS` 가드 + `_CLEARED_RUNTIME_KEYS` 가드로 **driver process 내 첫 호출만 동작**
- multi-invoke 측정 환경에서는 effectively no-op

## 결정 정책

### 1. Reset 위치
**driver 책임** — graph 의 cleared_once 메커니즘은 process-once 만 보장. multi-invoke driver 매 run 시 reset 보장 안 됨.

### 2. Reset 단위
**`ns_web` 만 reset** — `ns_local` (PDF chunks 349개) 은 보존.
- 이유 1: 매 run 마다 PDF 재인덱싱하면 +30초 누적 (5 sections × 3 runs × 2 commits = 30회 = +15분)
- 이유 2: PDF chunks 는 patch 영향 없음 (vertex grounding 통합 변경은 web/vertex 경로만)
- 이유 3: §12-12 정책 (`local_first + 0.33`) 유지 — local PDF 가 우선이므로 측정 동질성 보장

### 3. Reset 시점
**multi-turn 시퀀스 1회 전체 시작 전** (driver 의 `_run_single` 함수 진입 직후, graph.invoke 호출 전).
- 매 turn 마다 reset 하면 첫 turn 의 web search 결과가 두 번째 turn 의 retrieve 에서 사라짐 → invariance 깨짐
- 1 run = 1 multi-turn 시퀀스 = 1 reset

### 4. Runtime guard 우회
2가지 옵션 (구현 시 결정):

| 옵션 | 방식 | 장단점 |
|---|---|---|
| (a) 모듈 reload | `_CLEARED_ONCE_KEYS.clear()` + `_CLEARED_RUNTIME_KEYS.clear()` + `_VS_CACHE.clear()` 직접 호출 | 단순. 단 internal state 직접 manipulation. |
| (b) subprocess 분리 | 매 run 별 `subprocess.run([python, driver_inner.py, ...])` | 완전 격리 (graph cache, LLM cache, Chroma handle 모두 새로 생성). 단 process spawn overhead ~3~5s. 측정 정확. |

**권고: (b) subprocess 분리** — Phase A 의 baseline_mean=25s 와 동등한 측정 정밀도 확보. process spawn 오버헤드는 측정 elapsed 에서 제외하면 됨.

### 5. 누적 trade-off (대안 정책)
**'누적 그대로 측정' 옵션도 valid** — patch 전후 둘 다 동일 누적 상태면 차이 측정은 유효 (ns_web=112 + run 누적 분).
- 장점: reset 책임 driver 에서 해제. 단순.
- 단점: 절대값 신뢰성 ↓. 측정 결과 해석에 "누적 baseline" 주석 필요.
- patch 전후 측정 사이 ns_web reset 1회만 보장하면 비교 측정 유효.

**최종 권고: subprocess 분리 + ns_web reset (run 단위)** — 정확도 우선.

## Driver 구현 sketch (참고용, 구현은 별도 task)

```python
# 매 run 시작 (multi-turn 시퀀스 전):
def _reset_ns_web(persist_dir: str, ns_web: str):
    """driver process 내 runtime guard 우회 + ns_web 만 reset."""
    from tools.web_rag.ingest_vector import (
        clear_vector_store, _CLEARED_ONCE_KEYS, _CLEARED_RUNTIME_KEYS, _VS_CACHE
    )
    # runtime guard 직접 invalidate
    key = (persist_dir, ns_web)
    _CLEARED_ONCE_KEYS.discard(key)
    _CLEARED_RUNTIME_KEYS.discard(key)
    _VS_CACHE.pop(key, None)
    clear_vector_store(namespace=ns_web, persist_directory=persist_dir)
```

또는 subprocess 옵션:
```python
# driver_outer.py 가 driver_inner.py 를 N회 subprocess.run
subprocess.run([python_exe, str(driver_inner_path), "--label", label, ...],
               check=False, timeout=per_run_timeout_s)
```

## 후속
- 본 측정 시작 전 (option (b) subprocess vs (a) in-process) 최종 확정
- 측정 결과 박제 시 "ns_web reset 정책: ..." 명시
