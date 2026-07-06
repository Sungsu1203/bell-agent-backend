# catch 81 — 본문↔참조 번호 오매칭 규명 박제 (R1 종료)

**작성일**: 2026-07-07
**성격**: READ-ONLY 규명 결과 박제. 코드 수정 0, 유료 API 0. 수정 배선은 R2.
**대상 산출물**: `scripts/output/§paper-writer-1/paper_consumer_perceived_trademark_similarity_and_likelihood_of_co_20260706_004833.md`
(본문 52개 `[[N]]` 마커 중 9 occurrence / 8 distinct 가 오매칭)

---

## 계보 한 줄

- **catch 80** = 한 런 내 섹션-로컬 `[[N]]` → 글로벌 승격 (섹션↔footer 정합). 종결 `dcbb7f12`.
- **catch 81** = catch 80의 글로벌 shift 결과물이 `previous_sections`를 통해 **다음 섹션 writer 프롬프트를 오염**시키는 **한 런 내부 feedback loop**. catch 80과 문제 층위가 다름 — catch 80은 "한 런 내부 정합", catch 81은 "그 정합 산물이 같은 런의 후속 섹션 생성을 오염".

> ⚠️ 진단 계보 주의: 이 트랙은 애초 **citation-claim faithfulness**([[58]] Beebe mismatch)에서 출발했고, 이후 "cross-run frozen prose(169체계)" 가설을 거쳐 최종 "**한 런 내부 numbering feedback loop**"로 귀결됐다. 진단이 5겹 뒤집혔으므로 아래 **항목 5 폐기 가설 묘비명**을 반드시 함께 읽을 것. 확정 결론만 보고 폐기 가설을 모르면 같은 헛발질이 재발한다.

---

## 1. 확정 메커니즘 (라인 참조 포함)

**한 런 내부 feedback loop: shift → leak → 재사용(유도) → 재shift.**

배관 (전부 코드 확인):

| 단계 | 위치 | 동작 |
|---|---|---|
| ① 글로벌 shift | `measure_paper.py:277` | `_shift_citation_markers(body, cite_offset)` — 섹션 body의 로컬 `[[N]]`을 `[[N+offset]]` 글로벌로 재작성 |
| ② append | `measure_paper.py:278` | 시프트된 body를 `section_bodies`에 축적 (**글로벌 마커 상태로**) |
| ③ previous_sections 축적 | `measure_paper.py:273` | `previous_sections="\n\n".join(section_bodies)` — 글로벌 마커 실림 |
| ④ 키워드 전달 | `measure_paper.py:267` | `write_paper_section(..., previous_sections=...)` |
| ⑤ 마커 정제 0 | `paper_section_writer.py:58` | `prev_text = (previous_sections or "").strip()` — **공백 strip만**, `[[N]]` 정제/마스킹 0건 |
| ⑥ 프롬프트 verbatim 렌더 | `prompts.py:465` (블록) + `:450` (인라인) | `{previous_sections}` placeholder에 글로벌 마커 **원문 그대로** 렌더 (단일 human 프롬프트, 요약·잘림 없음) |

→ 다음 섹션 writer는 직전 섹션들의 **글로벌 시프트 마커**(`[[26]]` 등)를 프롬프트에서 원문 그대로 본다. 로컬 `[1..K]`만 쓰라는 `[citation 규칙]`(`prompts.py:439`)과 충돌.

### 데이터 증거 (로컬 .md 파싱, 무료)

섹션별 offset·K·범위 (from `c_paper_measurement.json`):

| 섹션 | chunks(K) | offset | 글로벌 범위 |
|---|---|---|---|
| Introduction | 15 | 0 | 1..15 |
| Theoretical Background | 18 | 15 | 16..33 |
| Proposed Framework | 20 | 33 | 34..53 |
| Research Design (Proposed) | 19 | 53 | 54..72 |
| Expected Contributions | 17 | 72 | 73..89 |
| **총 chunks / footer 항목** | **89** | | |

오매칭 8 distinct 전수 — 각 마커의 **writer raw 값(=최종−offset)이 직전 섹션들 글로벌 마커의 부분집합**:

| 섹션 | 마커 | raw(=M−off) | K | 복사 출처 |
|---|---|---|---|---|
| PropFw | `[[55]]` | 22 | 20 | TheoBg `[[22]]` |
| PropFw | `[[57]]` | 24 | 20 | TheoBg `[[24]]` |
| PropFw | `[[58]]` | 25 | 20 | TheoBg `[[25]]` |
| PropFw | `[[59]]` | 26 | 20 | TheoBg `[[26]]` |
| PropFw | `[[62]]` | 29 | 20 | TheoBg `[[29]]` |
| ResDes | `[[112]]` | 59 | 19 | PropFw `[[59]]` |
| Expected | `[[98]]` | 26 | 17 | TheoBg `[[26]]` |
| Expected | `[[101]]` | 29 | 17 | TheoBg `[[29]]` |

- **8/8 전부 복사 출처 존재.** "어느 섹션에도 없는 = 별도 원인" 케이스 0건 → **이 산출물의 오매칭은 단일 메커니즘**.
- **`[[112]]` = 2-hop 복리 성장** (단일 런 완결):
  ```
  TheoBg  : writer local 11 → +offset15 → [[26]]   (K=18 내, 정상)
  PropFw  : writer가 "26" 재사용 → +offset33 → [[59]]   (K=20 초과, 오염 1세대)
  ResDes  : writer가 "59" 재사용 → +offset53 → [[112]]  (K=19 초과, 오염 2세대)
  ```
  → `[[112]] > 89`은 89-초과 체계의 잔재가 아니라, 정상 마커(26)가 hop마다 큰 offset을 먹으며 26→59→112로 커진 결과.

---

## 2. 필요조건 vs 인과 (이 구분을 흐리지 말 것)

- **코드로 확정된 것 = 필요조건**: 글로벌 마커가 writer 프롬프트에 verbatim 렌더됨(§1 배관 ①~⑥) + 프롬프트가 표기 일관성을 지시함(§3). → writer가 그 숫자를 **재사용하는 것이 가능하고 유도됨**. 그리고 오매칭 8/8 raw 값이 실제로 직전 섹션 글로벌의 부분집합(§1 표).
- **아직 미확정 = 인과**: writer가 그 토큰을 **실제로 복사**하는지 vs 우연 hallucinate한 숫자가 일치하는지. → **통제된 생성 런(유료)에서만 최종 확정.** 단 `[[112]]`의 26→59→112 **2-hop 사슬**은 우연으로는 사실상 불가능한 정합이라, "우연" 가설을 극히 약하게 만든다.

---

## 3. 부수 발견 (인과 심증 강화, 증명 아님)

- `prompts.py:450`: `{previous_sections}`를 렌더하면서 **"...표기(notation)를 본 section 에서 일관되게 유지한다"** 고 명시 지시. → writer가 직전 섹션의 `[[N]]` 마커를 **재사용하도록 능동 유도**하는 문구. 오매칭 8/8이 직전 섹션 글로벌의 부분집합인 패턴과 정합.
- 다만 이는 **프롬프트-텍스트 정황**이지 인과 확정이 아니다 (§2 경계 유지).

---

## 4. `[[58]]` Beebe — faithfulness 표적에서 공식 제외

- `[[58]]`(시각지각 문장 ↔ Beebe "Search and Persuasion in Trademark Law" 검색비용 abstract mismatch)은 **citation-claim faithfulness 문제가 아님이 확정**.
- 근거: `[[58]]` = PropFw raw 25 (= TheoBg `[[25]]` 재사용) → **번호 체계 feedback loop의 증상**. writer가 Beebe를 "의미로 골라 붙인" 게 아니라, 오염된 번호(25→58)가 재편된 참조 목록에서 우연히 Beebe에 착지한 것.
- **faithfulness 트랙 재개 시 표적은 43개 aligned 마커 중에서 재선정할 것.** `[[58]]`은 제외.

---

## 5. ⭐ 폐기 가설 묘비명 (누락 절대 금지)

| # | 폐기 가설 | refute 근거 (1줄) |
|---|---|---|
| ❌1 | "169체계 cross-run 동결" | `[[112]]`는 169 잔재 아니라 **단일 런 2-hop 복리**(26→59→112). |
| ❌2 | "frozen prose / 본문↔참조 시점 분리" | prose는 **매 런 LLM 재생성**(`write_paper_section`=`get_llm()`+`chain.invoke`, `read_text`·`open(`·cache 0건; measure_paper.py는 draft를 write-only 산출만, 되읽기 0). |
| ❌3 | "writer 순수 환각(랜덤)" | 로컬 `≤K`는 정상이고 out-of-range raw가 **직전 섹션 글로벌의 부분집합**(8/8) = 순수 랜덤 아님. |
| ❌4 | "offset 산술 오류(경로 B)" | 동일 섹션의 in-range 마커(예 PropFw `[[40]][[45]][[53]]`=local 7·12·20)가 offset=33의 **정확성을 증명** → 같은 offset이 다른 마커만 틀릴 수 없음. writer가 실제 K-초과 값을 뱉은 것. |
| ❌5 | "dedup / SS 429 rate-limit가 오매칭 증폭 요인" | 이 measure 경로엔 catch 78 vertex-shell 제거·dedup·재활용이 **작동 안 함**(`SKIP_VERTEX_SEARCH=1`, draft 재활용 0) → 오매칭과 무관. |

---

## 6. dedup 잔존 이슈 분리 (혼동 방지)

- dedup 부재는 **실재**: 89 chunk = **53 고유** (Beebe "Search and Persuasion in Trademark Law" 5회 등 중복 다수).
- 단 이는 **이 catch 오매칭의 원인도 증폭 요인도 아님** (§5-❌5). 오매칭은 89개 footer 자체가 아니라 writer의 번호 재사용에서 발생.
- → dedup은 **별개의 참조품질 이슈로 잔존**. R2 또는 별 catch에서 독립 판단.

---

## 7. R2 수정 방향 후보 (확정 아님, 기록만)

| 후보 | 내용 | 평가 |
|---|---|---|
| 고리③ 차단 | `previous_sections` 전달 전 `[[N]]` strip + `prompts.py:450` 표기-일관성 지시 조정 | 국소·1런 검증 가능. **유력** |
| shift 지연 | 전체 섹션 생성 후 일괄 shift (생성 시엔 로컬만 노출) | catch 80 근본 재설계, 큼. 별 트랙 후보 |
| 로컬 복원 / 프롬프트-only | previous_sections 마커를 로컬로 되돌리거나 프롬프트만 손질 | 각각 복잡·비결정적. 열위 |

- 인과(§2)가 유료 통제런으로 확정되기 전이라도, **고리③ 차단**은 필요조건을 끊으므로 유효한 국소 실험. 단 이는 R2 판단 — 이 박제는 규명·기록까지.

---

## R1 종료 조건 충족

메커니즘 = 한 런 내부 **shift → leak → 재사용(유도) → 재shift**. leak 채널 필요조건(전달 O × 렌더 O × 마커 글로벌 O) 코드로 완비. 인과(writer 실제 복사)는 유료 통제런 몫으로 분리. → **R1 규명 종료. R2 = 수정 설계.**
