# §14-5 cycle close summary

## 메타
- date: 2026-05-16
- branch: feature/vertex-web-search
- HEAD (작성 시점): TBD (close commit hash 추가 후 update)
- cycle: §14-5 (state mapping read-only 진단)
- 진단 결과: ★★★★★ (c'-9-d) CONFIRMED (★ 1 turn first read)
- 컨벤션: 박제 (실측) / plan (미검증) 구분, 자율 진행 금지,
         §-numbered, 가설 매트릭스 자산 chain

## § 1. 배경

§14-4 close 박제: (c'-2) sub-gate 잠정 falsified + (c'-9) state
mapping 가설 활성 강화 + (해석-β + γ hybrid) 본 미션 정의 확정.
§14-6 = (가-η) graph hang 별 cycle 분리.

§14-5 cycle 진입: (c'-9) sub-classification 박제 + §14-3 v2 cross-ref
update. read-only 진단으로 §14-6 무관 진입 (graph 실행 안 함).
우선 추정 = (c'-9-d) source_dist 분류 helper.

## § 2. 진단 chain 요약 (★ 1 turn 으로 완료)

| 단계 | 작업 | 결과 |
|---|---|---|
| H1 | web_search.py L786 ~ 종결 read | combined_items.extend → state.references chain 박제 |
| H2 | State schema read (core/state_types.py) | List[Any] schema 차단 없음 박제 |
| H3 | graph.py web_search node 등록 | after_web_search_agent router → next node |
| **H4** | **source 분류 helper read (★ 우선 진입)** | **★★★★★ (c'-9-d) CONFIRMED at first read** |
| H5 | downstream node | 미진입 (우선순위 ↓, (c'-9-d) 확정 후) |

**H4 우선 진입 권고 정확** — first read 에 confirmed.

## § 3. ★★★★★ 핵심 박제 — (c'-9-d) CONFIRMED

### bug 1-line 정의
> `classify_source(src)` 는 src URL pattern 만 check 하고
> vertex_search.py 가 resolve 한 FINAL URL 에서 vertex 도메인이
> 사라진 상태로 들어옴 → "web" 으로 오분류. row dict 의 backend
> metadata 는 추출되지만 분류 logic 이 무시.

### 5-step 증거 chain (file:line + raw 박제)

vertex_search.py L181-183 (G5-c-2 박제):
for c in chunks_out:
if c["uri"]:
c["uri"] = _resolve_vertex_redirect(c["uri"])
→ 모든 chunks URL redirect resolve, FINAL URL 변환
web_search.py L791-793:
combined_items.append({
"source": rep_url,                      # resolved URL
"metadata": {"backend": "vertex_grounding", ...},
})
→ source = resolved URL (vertex 도메인 사라짐),
backend metadata 별도 박제
items → state.references.docs:
List[Any] schema, dict.extend 흐름 보존
_step3_dry_run_rag_update.py:109-110 _doc_to_dict:
for k in ("source", "url", "title", "content_type", "backend", ...):
row[k] = ...
→ row dict 에 source + backend 모두 추출
_step3_dry_run_rag_update.py:126-136 _classify_source:
src = str(row.get("source") or row.get("url") or "")
key = classify_source(src)                    # ★ backend 무시
dist[key] = dist.get(key, 0) + 1
row["source_class"] = key
→ row.get("source") (resolved URL) 만 사용
→ "vertexaisearch.cloud.google.com" 없음
→ return "web" (오분류)


### classify_source 본체 (양 파일 동일 logic)
```python
def classify_source(src: str) -> str:
    s = (src or "").strip()
    if "vertexaisearch.cloud.google.com" in s:
        return "vertex_grounding"
    if s.startswith("http://") or s.startswith("https://"):
        return "web"
    ...
```

→ vertex 도메인 check 은 있지만 resolve 후 사라진 URL 에는 미적용.

## § 4. (c'-11) NEW root cause 박제

(c'-9-d) bug 의 mechanism = **resolve vs classify mismatch**:

- **resolve 목적**: downstream 에서 실제 URL 사용 (citation 신뢰성)
- **classify 가정**: vertex URL 이 그대로 유지됨
- **두 가정 mismatch** = (c'-9-d) 발생 mechanism

코드 진화 과정 추정:
- _resolve_vertex_redirect 가 citation 목적 추가됨
- classify_source 의 vertex 인식 logic 미동시 update
- 두 logic 의 sync 누락

### counter-intuitive 박제 ★
- `_resolve_vertex_redirect` timeout (5s) 또는 exception 시 원본 redirect URL 반환
- 그때만 `vertexaisearch.cloud.google.com` 포함 → vertex_grounding 분류
- 즉 **resolve fail = vertex_grounding 박제, resolve success = web 오분류**
- 직관과 반대 — §14-3 v2 vertex_grounding=0 은 vertex 가 *정상* 작동 신호

## § 5. 가설 매트릭스 final
(c'-9) state mapping 누락                        [★★ CONFIRMED]
├─ (c'-9-a) state.references.docs 미할당          [기각 — refs_docs_count>0]
├─ (c'-9-b) backend metadata 손실 (chain)         [기각 잠정 — H5 미진입]
├─ (c'-9-c) downstream 활용 부재                  [부분 활성, H5 미진입]
└─ (c'-9-d) source 분류 helper 미사용 backend     [★★ CONFIRMED]
(c'-11) NEW — resolve vs classify mismatch       [활성, (c'-9-d) root cause]

§14-5 read-only 진단 미해소 잔여: (c'-9-b/-c) — H5 진입 필요 (verbose 검증 단계 또는 fix cycle entry 시).

## § 6. 본 미션 정의 (해석-β + γ hybrid) fix 방향

| fix | 변경 범위 | 본 미션 의미 | 평가 |
|---|---|---|---|
| **fix-α** classify_source backend 우선 check | _phase_b_run_inner.py + _step3_dry_run_rag_update.py (양쪽 동일 수정) | (해석-β) 즉시 달성 | minimal, 빠른 fix |
| **fix-β** metadata.original_uri 박제 + 양쪽 classify | vertex_search.py + web_search.py + classify 2 file | (해석-β + γ hybrid) 둘 다 cover | full, 본질 부합 |

### 본 세션 권고: fix-β (full fix)
근거:
- 본 미션 정의 (해석-β + γ hybrid) 부합
- (해석-γ) grounding annotation 본질 활용 = original vertex URL 보존 = metadata.original_uri
- fix-α 만으로 (해석-β) 달성 but (해석-γ) 미검증 — H5 진단 필요

단 fix-α 도 valid path (최소 변경, 회귀 위험 낮음, (해석-β) 즉시 달성).
fix cycle (§14-7) entry 시점에 사용자 결정.

## § 7. §14-3 v2 vertex_grounding=0 origin 확정 ★

§14-3 v2 측정 박제 자산과의 cross-check:

- §14-3 v2 박제 자산: `scripts/output/§14-3/(NEW)-B_phase3_step1b_v2_result.md`
- patched/reverted 10 runs source_dist 모두 `{web: N}` 또는 `{}` — vertex_grounding 박제 0건
- §14-4 standalone test (chunks=15 supports=27) 박제와 일치
- → vertex 자체 작동 + classify_source 오분류 = **§14-3 v2 결과와 완벽 정합**

★ §14-3 v2 vertex_grounding=0 의 직접 origin = (c'-9-d) **확정 박제**.

## § 8. H5 (downstream) 미진입 박제

(c'-9-d) 확정 후 H5 우선순위 ↓:
- (c'-9-b/-c) 잔여 — downstream metadata 활용 검증
- (해석-γ) grounding annotation 본질 활용 검증
- fix cycle (§14-7) entry 시점 또는 verbose 검증 단계에서 진입 가능

H5 미진입 의 영향:
- §14-5 진단 사명 부분 완료 ((c'-9-d) 확정)
- (해석-γ) 검증은 fix cycle 보강 필요

## § 9. 후속 cycle 분기 plan
§14-6 (사용자 측 PC 환경 fix — 사전 조건)

1단계: 시간 경과 (cost 0)
2~5단계: 네트워크 reset / 재부팅 / AV exception / venv 재구축
완료 신호: graph import 정상 작동
↓ (사전 조건 충족 시 다음 진입)

§14-5 verbose 검증 (별 turn, §14-6 완료 후)

graph chain 정상 환경에서 1 run
state.references.docs 의 metadata.backend 직접 박제
"web" 분류 N개 중 backend="vertex_grounding" 박제 개수
(c'-9-d) 정량 확정 + (c'-11) root cause 확정
↓

§14-7 fix cycle (★ 본 미션 critical path 종결 단계)

fix-α vs fix-β 사용자 결정
진단/fix 분리 정신 부합
본 미션 (해석-β + γ hybrid) 최종 달성


## § 10. 학습 자산

### § 10-1. 1 turn confirmed 효율성 ★
- §14-5 우선 추정 (c'-9-d) — first read 에 confirmed
- §14-4 → §14-5 chain 의 사전 박제 + 우선 추정 정확성
- read-only 진단의 박제 가치 극대화

### § 10-2. 우선 추정 정확성
- 본 세션 §14-4 close 시점 권고: "(c'-9-d) source_dist 분류 helper 가장 가능성 높음"
- §14-5 H4 first read 결과: confirmed
- 추정의 confidence 한계 (plan 차원) 인지 유지, but 정합성 박제

### § 10-3. resolve vs classify mismatch 패턴
- 코드 진화 시 logic 간 sync 누락 패턴 박제
- 향후 비슷한 패턴 진단 시 reference 가능

### § 10-4. counter-intuitive 박제
- resolve fail = vertex_grounding 박제, success = web 오분류
- 직관과 반대인 logic 발견 시 박제 정신 필요 — 추정 회피, raw 검증 우선

### § 10-5. cross-ref update 박제 process
- §14-4 close 의 §14-3 cross-ref update 동반 진행
- multi-cycle 박제 자산 chain update process 박제

## § 11. patch + cross-ref + close commit chain 박제

- §14-4 chain: 2355783 patch + revert + docs (close summary push 완료)
- §14-5 chain: TBD (cross-ref update + close summary)
- 일괄 push 정책 (ii) 유지

## § 12. 위험 신호 / 자기 비판

- (위험-A) **(c'-9-b) "기각 잠정"**: H5 미진입으로 downstream metadata 활용 미검증
- (위험-B) **(c'-11) 분류 모호**: (c'-9-d) root cause vs 별 가설 — 옵션-α 별 명명 유지 박제
- (위험-C) **(해석-γ) 미검증**: (c'-9-d) fix 만으로 (해석-β) 만 달성 가능, (해석-γ) 본질 활용은 H5 진단 + fix-β 보강 필요
- (위험-D) **(c'-9-d) sample size 1 일관성**: 코드 read 기반 정합성 추론 — verbose 검증으로 정량 확정 권장
- (위험-E) **fix cycle entry 시 본 미션 정의 적용**: fix-α vs fix-β 결정 시 (해석-β + γ hybrid) 일관 유지 필수

## § 13. 박제 자산 chain

- 본 박제: scripts/output/§14-5/cycle_close_summary.md
- §14-4 close: scripts/output/§14-4/cycle_close_summary.md
- §14-3 cross-ref: scripts/output/§14-3/(NEW)-B_phase3_step1b_v2_result.md § 14 update
- §14-4 standalone: scripts/output/§14-4/_g5c6_standalone/result.txt
- §14-4 D-1: scripts/output/§14-4/D-1_phase3_raw_reinterpretation_result.md
- v1_archive 보존: scripts/output/§14-3/v1_archive/
- 후속 cycle 박제: scripts/output/§14-6/ + scripts/output/§14-7/ (TBD)

## § 14. 분량 / 박제 trigger

- 본 문서 분량 ≈ 9.x KB (12.5KB trigger 이하)
- v2 분할 미필요
- 다음 cycle entry plan 작성 시 별 파일

---
박제 정신 유지: 모든 측정/코드 변경/commit/push 사용자 컨펌,
추정 회피·사실 검증 우선, "박제 (실측)" vs "plan (미검증)" 구분,
§-numbered task queue, 박제 자산 chain.

§14-5 read-only 진단 close. verbose 검증 = §14-6 완료 후 별 entry.

## § 15. close v2 정정 박제 (2026-05-16 추가)

§14-5 close v1 작성 후 verbose 검증 chain (옵션-C → 옵션-γ → 옵션-α)
누적 박제 결과로 다음 정정 사항 발생.

### § 15-1. (c'-9-d) → (c'-9-d') 정정

close v1 § 3 박제: "(c'-9-d) source 분류 helper backend 무시 → CONFIRMED"

정정 박제 (옵션-C 결과):
- 71/71 docs metadata_keys = ['source'] 단일 박제
- backend 가 state.references.docs 에 도달 못 함
- classify_source 가 backend check 추가해도 effect 0
- **(c'-9-d) technically true but moot**

### § 15-2. (c'-9-i) NEW CONFIRMED at first read ★★★★★

옵션-α 결과 박제 — 본 미션 origin 확정:

**bug 1-line 정의**:
agent/web_search.py L1036-1041: web_page_json_to_documents output
Document reconstruct 시 `metadata={"source": src_disp}` 명시적
hardcode → 모든 원본 metadata (backend, title, content_type,
chunk_domain) 폐기.

**raw 박제** (file:line):
```python
1035   new_docs_preview.append(
1036       type(d)(
1037           page_content=(d.page_content or "")[:500],
1038           metadata={"source": src_disp}   # ★ HARDCODED strip
1039       )
1040   )
```

**8-step chain 정정 박제**:
- Step 5: web_page_json_to_documents (메타 보존 추정)
- **Step 6: ★ web_search.py L1035-1041 HARDCODE STRIP**
- Step 7: merge_refs (보존)
- Step 8: state.references.docs (mkey={'source'} 단일)

### § 15-3. (c'-9-h) REFUTED

옵션-γ 시점 박제 (c'-9-h) URL re-fetch metadata 누락 가설 →
**REFUTED**. load_urls_as_documents 함수 자체 부재 박제.

직전 옵션-γ 박제는 함수 명명 추정 단계 — refutation 정확.

### § 15-4. (c'-9-f) Chroma metadata strip → 정정

close v1 추정: Chroma 측 metadata strip 활성
정정 박제 (옵션-α):
- documents_to_chroma metadata 보존 (source_version 추가만)
- Chroma persist/retrieve 보존
- **Chroma 무관, strip 위치는 web_search.py 내부 L1037-1041**

### § 15-5. fix 방향 재정립 ★

close v1 fix 방향:
- fix-α classify_source backend check
- fix-β metadata.original_uri

정정 박제:
- fix-α: 직전 효과 0 박제 → **fix-γ 와 조합 시 효과 회복 (재부활)**
- fix-β: 무효 유지 (state 에 metadata 없으면 효과 0)
- **fix-γ NEW**: web_search.py L1038 metadata 보존
  - 변경: `metadata={"source": src_disp}` → `metadata={**md, "source": src_disp}`
  - 1-2 lines patch

**완전 fix chain = fix-γ + fix-α (재부활) 조합**:
1. fix-γ (L1038): metadata 보존 → state.references.docs 의 backend 보존
2. fix-α (classify_source 양 파일): backend 우선 check → "vertex_grounding" 분류 회복

본 미션 (해석-β + γ hybrid) 완전 달성 path 박제.

### § 15-6. 가설 매트릭스 final v2
(c'-9) state mapping 누락
├─ (c'-9-d/-d') classify_source moot               [정정 확정]
├─ (c'-9-e) vertex graph 호출 부재                  [미박제, 본 미션 무관 박제]
├─ (c'-9-f) Chroma metadata strip                  [정정 — Chroma 무관]
├─ (c'-9-g) docs entry path                        [확정 — new_docs_preview 단일]
├─ (c'-9-h) URL re-fetch metadata 누락              [REFUTED — 함수 부재]
└─ (c'-9-i) NEW web_search.py L1037-1041 hardcode  [★★★ CONFIRMED at first read]

### § 15-7. 박제 chain 자기 정정 메커니즘 효과 박제

§14-5 cycle 의 4 단계 자기 정정 trace:
H4 (코드 read):    (c'-9-d) CONFIRMED
↓
옵션-C (json):     (c'-9-d) → (c'-9-d') moot, (c'-9-e/-f/-g) NEW
↓
옵션-γ (H5):       (c'-9-h) NEW root cause 후보
↓
옵션-α (H6):       (c'-9-h) REFUTED, (c'-9-i) CONFIRMED ★

박제 컨벤션 정신 ("추정 회피, 사실 검증 우선") 완벽 부합 학습 자산.

### § 15-8. 후속 cycle 진입

§14-7 fix cycle entry plan (별 turn):
- fix-γ + fix-α 완전 fix chain
- 본 미션 (해석-β + γ hybrid) 종결 단계
- 진단/fix 분리 정신 부합

§14-5 cycle close v2 박제 종결.