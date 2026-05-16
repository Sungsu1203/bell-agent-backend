# §12-13 사용자 검증 본 미션 — entry state 박제

**측정 일자:** 2026-05-17
**branch:** `feature/vertex-web-search` (origin synced)
**HEAD:** `d8f86f5` (§14-8 prior 박제 자산 commit)
**미션:** §12-13 사용자 검증 진입 전 entry state 박제 + 사용자 컨펌 대기

---

## § 1. §12-13 README 박제 상태 (README-dev.md L665-899)

### 1-1. 출처

> 출처: §12-12-1 close 직후 사용자측 검증 세션 (2026-05-04). 미션 A에서 "비타민 B1이 뭐야"(60초, 정상), "파이썬에서 리스트 컴프리헨션이 뭐야"(247초, 5회 vector→web 루프, 인덱스 8→37), "벤포벨이 뭐야"(9초, 정상)의 3건 비교 로그에서 검출.

→ **사용자 검증 세션 = §12-13 발견 원천**. 본 미션은 후속 검증 사이클.

### 1-2. 박제 본 상태 (README-dev.md L667 명시)

> __현재 상태 (2026-05-05 §12-13-1 + §12-13-4 패키지 close 세션 후)__: §12-13-1/4/5/7 close. §12-13 큐 9개 누적 중 4개 close, 5개 pending (§13-2/3/6/8/9).

본 박제 노트는 2026-05-05 시점. 그 후 §13-10 추가 + (§13-11 추가)로 큐 11개로 확장. 본 cycle 박제 시점 (2026-05-17) 다음:

### 1-3. §12-13 sub-§ status 박제 (실측, 11건)

| sub-§ | 주제 | status | priority |
|---|---|---|---|
| §12-13-1 | supervisor fast-path 토픽-적합성 가드 | **closed** (2026-05-05) | 高 |
| **§12-13-2** | web_search OBJ vs user query 분리 | **pending** | 中 |
| **§12-13-3** | after_vector → web_search 루프 카운터 | **pending** | 中 |
| §12-13-4 | communicator QA 저장 디렉토리 분리 | **closed** (2026-05-05) | 高 |
| §12-13-5 | write: ko-natural 라우팅 | **closed** (2026-05-05) | 최상 (Blocker) |
| §12-13-6 | Vertex 429 quota metric | **(a) closed** / (b)(c) pending | 中 |
| §12-13-7 | extract_write_title 괄호 보존 | **closed** (2026-05-05) | 低 |
| **§12-13-8** | router.tail outline_shown=False loop | **pending** | 低 |
| **§12-13-9** | section_writer 슬러그 괄호 제거 | **pending** | 低 (cosmetic) |
| §12-13-10 | /api/export 슬러그 fallback | **closed** (2026-05-05) | 高 |
| **§12-13-11** | llm_call metric topic_slug null | **pending** | 低 (cosmetic) |

**pending 누적: 6건 (§12-13-2, -3, -6(b)(c), -8, -9, -11)** — sub-§ 누적 11건 중 5건 close + 6건 pending.

### 1-4. README-dev-2.md 의 §12-13 mention (L1021)

> (다) §12-13 사용자 검증 본 미션 복귀

→ 본 mission entry trigger 박제. README-dev-2 의 §14-8-B 종결 박제 § 의 분기 (다) — 본 mission 진입 정합 ★.

---

## § 2. §12-13 commit history 박제

### 2-1. §12-13 관련 commit log

```
fb7f193 docs: §12-13-6 closed (a) — 검증 4단계 baseline 박제 + §12-13-11 신규
bca50d2 fix: §12-13-6 metrics flush 누락 — 파일 핸들 line-buffering 도입
26be903 fix: §12-13-6 metrics deadlock — _METRICS_LOCK Lock → RLock (재진입 허용)
216c175 fix: §12-13-6 게이트 함정 정리 — POSTHOG_DISABLED 분리, ANONYMIZED_TELEMETRY 도입
65a01eb feat: §12-13-6 (a) 부분 — Vertex LLM 호출 metric 도입 (latency/success/retry_hint)
19e27d2 docs: §12-13-10 박제 — /api/export 엔드포인트 슬러그 fallback close 후기
4afcfb3 §12-13-5 보강: early write fastpath flag 누락 → direct_qa 회귀
818ecda §12-13-1 + §12-13-4: topic-fitness guard + qa save dir split + router guard
95cd3b1 §12-13-5/7 close: ko-natural write 라우팅 회복 + extract_write_title 괄호 보존
dff31cd docs: §12-13-5~8 박제 (C 미션 우회 + 부수 하자 4건) + 사용자측 검증 세션 close
f248532 docs: §12-12 close 후기(B 검증) + §12-13 신규(supervisor 라우팅 가드)
```

### 2-2. last §12-13 commit + 그 이후

- last §12-13 commit: `fb7f193` (§12-13-6 (a) closed + §12-13-11 신규 박제)
- 그 이후: `9fda4ec` (§14-2 Phase A) → … → 본 HEAD `d8f86f5` (§14-8 prior 박제 commit, §14-8-B close 직후)
- 즉 §12-13 last cycle (`fb7f193`) **이후 §14 cycle 전체** (envdump-style mystery 진단 + §14-8-B mystery 1+2 종결) 가 진행됨.

### 2-3. §14-8 fix 의 §12-13 사용자 검증 영향

- **§14-8 fix (O) protected env list** → driver subprocess 환경에서의 LLM_PROVIDER/LLM_MODEL/TOPIC_SLUG 회귀 차단
- → **사용자 검증이 vertex provider 환경에서 정상 작동 가능 ★** (이전에는 wrapper subprocess 내 reload_config_inplace 가 회귀 발화)
- 즉 §12-13 발견 회귀 케이스 (예: 인덱스 8→37 오염, "파이썬 리스트 컴프리헨션" off-topic loop) 의 일부는 §14-8-B fix 와 별개 원인이지만, **vertex 환경 사용자 검증 자체가 §14-8 fix 후에야 가능**.

---

## § 3. 사용자 검증 campaign sub-§ 후보 + 권장 entry

### 3-1. CLAUDE.md 명시 (Current focus §12-13)

> - 사용자 검증 우선: **일반 LLM Q&A 헬스체크, venfobel 인덱스 직접 QA, end-to-end 리포트 생성**
> - 백엔드 최적화(§12-12 큐)는 deprioritized

→ 본 미션 entry trigger 정확화 ★. CLAUDE.md 의 3 영역 = 사용자 검증 campaign 의 sub-§ 후보.

### 3-2. 권장 sub-§ entry — 우선순위

| sub-§ 후보 | 영역 | 우선순위 | 설명 |
|---|---|---|---|
| **(α) 일반 LLM Q&A 헬스체크** | supervisor → communicator routing for off-topic queries | **★ 1순위** | §12-13-1 fix (topic-fitness guard) 검증 + §14-8 fix 효과 (vertex provider 정상) 통합 검증. 짧은 cycle 가능 |
| **(β) venfobel 인덱스 직접 QA** | vector_search → dual-retrieve | **★ 2순위** | §14-8-B fix 의 핵심 효과 (`ns=venfobel-vitamin-oa` 회귀 차단) 검증. 사용자 의도 ↔ retrieval 정합성 확인 |
| **(γ) end-to-end 리포트 생성** | full pipeline (supervisor → content_strategist → research_planner → web_search → vector_search → section_writer → communicator) | 3순위 | 본 cycle 의 complete 검증. 시간 비용 高, sub-§ 결과 정합 시 마지막 단계 권장 |

### 3-3. pending sub-§ 처리 시점

| pending sub-§ | 처리 권장 시점 |
|---|---|
| **§12-13-2** (web_search OBJ vs user query) | (α)/(β) 검증 중 재발 시 즉시 처리 — §12-13-1 다층 방어선이 이미 차단 |
| **§12-13-3** (loop counter) | (β) 검증 중 재발 시 처리 — 다층 방어선 보호 |
| **§12-13-6 (b)(c)** (Vertex 429 fallback) | metric 추세 누적 후 결정 (CLAUDE.md "deprioritized") |
| **§12-13-8** (router.tail outline_shown) | (γ) 진행 시 부수 정리 |
| **§12-13-9** (section_writer 슬러그 괄호) | cosmetic, (γ) 끝에 batch |
| **§12-13-11** (llm_call topic_slug null) | metric 후처리 정리 시 |

→ **사용자 검증 campaign 진행 자체** 가 본 mission entry. pending sub-§ 는 검증 중 재발 시 또는 cycle 끝에 batch 처리.

---

## § 4. branch 정책 (사용자 결정 항목)

### 4-1. 현 branch 상태

- 현재 branch: `feature/vertex-web-search`
- HEAD: `d8f86f5` (origin synced)
- main 보다 앞선 commits: **32 commits** (§14-1 to §14-8-B 전체 + §14-8 prior 박제)

### 4-2. branch 정책 결정 후보

| 후보 | 장점 | 단점 |
|---|---|---|
| **(M1) feature 유지 + §12-13 진행** | (a) 검증 결과로 §14-x fix 자산의 정합성 사후 확정 가능 (b) main merge 위험 분산 | feature branch 가 더 커져 merge 비용 증가 |
| **(M2) main merge 먼저 + main 에서 §12-13** | (a) §14-x fix 자산 main 즉시 반영 (b) deploy 가능 상태 도달 | main merge 가 큰 변경 (~32 commits) — review 비용 |
| **(M3) main merge 후 feature 새로 cut (§12-13 전용)** | (a) §14-x close + §12-13 cycle 분리 (b) commit 흐름 clean | branch 작업 추가 |

→ **사용자 결정 필요** ★

### 4-3. Claude Code 권장

- §14-8-B 종결이 명확하고 regression test FULL PASS — main merge 가능 상태
- 단 §14-8 reserve list 5건 미처리 (defer) — main merge 후에도 별 cycle 진행 가능
- §12-13 사용자 검증은 production-style 검증이므로 main 상태에서 진행이 자연스러움
- **권장: (M2) main merge 먼저 + main 에서 §12-13 진행** — 단 user 컨펌 필요

---

## § 5. user 컨펌 필요 항목 list

본 mission 후 사용자 결정 사항 (Claude Code 자율 진행 금지):

**Q1. 사용자 검증 campaign sub-§ entry 결정**:
- **(α) 일반 LLM Q&A 헬스체크** (★ 1순위 권장)
- (β) venfobel 인덱스 직접 QA (2순위)
- (γ) end-to-end 리포트 생성 (3순위, 시간 비용 高)
- 또는 다른 entry

**Q2. branch 정책 결정**:
- (M1) feature/vertex-web-search 유지 + §12-13 진행
- **(M2) main merge 먼저 + main 에서 §12-13 진행** (★ Claude Code 권장)
- (M3) main merge 후 §12-13 전용 feature branch cut

**Q3. pending sub-§ 처리 시점**:
- (Wait) 검증 cycle 중 재발 시 batch 처리 (★ 권장 — 다층 방어선 보호)
- (Pre) 검증 진입 전 우선 처리

**Q4. §14-8 reserve list 5건 처리 시점**:
- (Defer) §12-13 검증 후 또는 별 cycle
- (Pre) §12-13 진입 전 처리

**Q5. 검증 환경 박제 (참고용)**:
- venv: `.venv_vertex` (CLAUDE.md 표준)
- LLM_PROVIDER: vertexai
- LLM_MODEL: gemini-2.5-flash
- TOPIC: venfobel-vitamin (default) 또는 ai-generated-creative-ad-platforms (test topic)

---

## § 6. 본 mission 종결 + 다음 round 분기

본 mission = **housekeeping commit 5 + §12-13 entry state 박제 + 사용자 컨펌 대기**.

다음 round 진입 (별도 hand-off prompt 재작성):
- **(가) §12-13 sub-§ (α) 진입 권장** — 일반 LLM Q&A 헬스체크 + §14-8 fix 통합 검증
- (나) (β) venfobel 직접 QA 진입
- (다) (γ) end-to-end 리포트 진입
- (라) §12-13 외 다른 mission 우선 — branch 정책 or reserve list 처리
