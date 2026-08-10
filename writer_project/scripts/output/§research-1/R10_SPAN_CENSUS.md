# R10 — 라벨 규모 역산용 span 통계 (§research-1 선분 3 / 작업 S4)

- 작성 2026-08-09 · 채널 = 기술 정밀
- 지시 `CC_HANDOFF_20260809_segment3_S4-S6.md` §2 + `CC_ADDENDUM_20260809_S4_probe_review.md`(1차) + `CC_ADDENDUM2_20260809_S4_probe_review2.md`(2차)
- 탐침 `probe_s4_census.py` (신규, `writer_project/.gitignore:110 probe_*` 로 untracked)
- **비용 $0** — 네트워크 0 · 유료 API 0 · 색인 0 · 파이프라인 `.py` 수정 0
- 재료 = R9 산출물 재사용 (`_s2_probe_html/` 45장 · `_s2_final.json`)

---

## 🔴 0. 결론 먼저 — STOP-1 발동. S4 는 세기까지 완주했고 여기서 정지한다

| STOP | 값 | 기준 | 판정 |
|---|---|---|---|
| **1** | (a) 고유 문구 = **922** | 600 초과 (경계 밴드 570~630) | **🔴 발동** |
| **2** | (d) T=10 loose = **0.3%** (strict 0.0%) | 20% 초과 | **미발동** (전체·결손제외 판정 일치) |
| **3** | ② `header` 포함 **53.3%** / 단독 **12.6%** | 과반 | **⚠️ 판정 보류** (기준 미정 — 챗 소관) |

**STOP-1 은 경계가 아니다.** 922 는 기준 600 의 1.54배이고 ±5% 밴드(570~630) 밖이다.
분해능 문제가 아니므로 `R9 §7-b` 전례(확정 유보)는 적용되지 않는다.

**무엇이 깨졌나** — 인계문 §2-h 의 STOP-1 취지는 *"전파 이득 소멸 → 문구 단위 라벨 전제가 깨진다"* 였다. 실측이 그대로다.

| 지표 | 값 |
|---|---|
| 잔여 레코드 | 1,241 |
| (문구,URL) 쌍 | 1,240 |
| **고유 문구** | **922** |
| **전파 배수 (쌍/문구)** | **1.345** |
| 문구 중 **1 URL 에만 나오는 것** | **708 / 922 = 76.8%** |

문구 단위 라벨의 전제는 *"한 번 판정하면 N 곳에 전파된다"* 인데 **N ≈ 1.35** 다.
그리고 역산 라벨(아래 §5)은 T=10 에서 **1,188~2,430건**이다. 3값 중 둘(1,188·1,189)은 레코드 전량 1,241 보다 **적으나 절감률이 4.3%·4.2%에 그치고**, 세 번째(2,430)는 오히려 약 2배다. **전파의 실익이 없다.**
<sub>(2026-08-09 `S4-b §3-b` 정정 — 종전 문안 *"차이가 없거나 오히려 많다"* 는 부정확했다. 결론은 유지, 근거 문장만 교체.)</sub>

**S4 는 세기까지가 범위이므로 재설계 방향은 쓰지 않는다.** 판정은 챗 소관이다.

---

## 1. 🔴 이 산출물의 한계 — 자기 채점이다 (인계문 §2-f, 서두 명시 의무)

- 규칙을 이 **45 URL** 에서 도출하고 **같은 45 URL** 로 검증한다.
- **이것은 일관성 검증이며 일반화 검증이 아니다.**
- 일반화 근거는 라벨셋이 아니라 **신규 수집분의 L2·L3**(규칙과 독립)에서 나온다.
- 추가 한계 — 45 URL 은 `R9 §7-Z` 가 이미 "근거가 가장 약한 재료"로 기록한 표본이다. **웹 전반을 진술하는 데 쓰지 않는다.**

### 1-a. 🔴 (d) 의 구조적 하한 (해석 전 필독)

잔여 모집단은 **④확정 72 를 이미 뺀** 집합이다(전수 판정 완료분). ④확정은 정의상 "본문 체인과 구조 동일" = **본문측 출현의 가장 확실한 사례**다. 그것을 뺀 모집단에서 양측 출현률을 재므로 **(d) 는 원리적으로 하향 편향** — 이라는 것이 사전 예상이었다.

**실측은 그 예상과 부호가 반대이고, 크기는 무시 가능하다.**

| 모집단 | T=10 문구 | loose 양측 | 비율 |
|---|---|---|---|
| 잔여(②③④-구분가능) | 305 | 1 | **0.328%** |
| **④확정 포함** | 352 | 1 | **0.284%** |
| 차 | — | — | **+0.044%p (상향)** |

→ **사전 논증(하향 편향)은 실측으로 확인되지 않았다.** 부호가 반대이므로 `2차 지시 Q1` 지시대로 **그대로 적고 별건으로 올린다.**
원인 추정(검증 안 함) — 양측 판정을 만든 것은 자수 10 이상 문구 **1건**뿐이라, 두 모집단 모두 분자가 1이고 분모만 다르다. 이 수치대에서는 편향 방향을 논할 정밀도가 없다.

---

## 2. catch 원장 등재 2건 (`2차 지시` 0절 요구)

| catch | 1줄 설명 |
|---|---|
| **CL** | 요약·대표값·첫 일치를 전수 대신 쓰면 답이 달라진다 — `_s2_final.json` 의 `reps` 는 범주별 **첫 출현 체인 1건**만 저장하므로 (d) 를 그것으로 계산할 수 없다. 저장 HTML 에서 체인을 **전량 재계산**해야 한다. (이미 `CLAUDE.md §9` 에 등재됨 — 본 작업이 첫 적용 사례) |
| **CM** | 판단 불가는 제3의 칸에 넣는다. 어느 쪽으로도 밀지 않는다 — ④-구분가능(구조 단서 있음)·대조군 0(판정 불가)을 크롬/본문 어느 쪽으로도 밀지 않고 **중간칸**에 두고 strict/loose 2값으로 냈다. (이미 `CLAUDE.md §9` 에 등재됨 — 본 작업이 첫 적용 사례) |
| **CN (신규 제안)** | **가드 없는 모듈은 import 만으로 전량 재실행된다** — `probe_s2_agg.py` 에 `__main__` 가드가 없어 `import probe_s2_agg` 한 번에 R9 집계가 통째로 재실행되고 `_s2_final.json` 이 덮어쓰였다(2026-08-09 실측). 값이 같아 무해했으나 **박제 파일이 조용히 재생성된다.** 확인 = `python -c "import <mod>"` 출력 0줄. |

⚠️ **CN 은 제안이다.** 원장 등재 여부는 챗 판정.

---

## 3. 측정 (a)~(c)

### 3-a. 모집단 확정 — 양성 대조 assert 통과 (1차 A)

```
[A] 양성 대조 assert 통과 — 레코드 1241 · {'4-구분가능': 162, '2': 627, '3': 452}
[모집단] 레코드 1241 · (문구,URL) 쌍 1240 · 고유 문구 922
[참고 모집단] ④확정 포함 레코드 1313 · 쌍 1312
```

- `R9 §6-a` 박제값(②627 / ③452 / ④-구분가능162, 합 1,241)과 **전항 일치.**
- **코드를 고쳐 숫자를 맞춘 일 없음.** assert 는 첫 실행에서 바로 통과했다.
- **레코드 1,241 vs 쌍 1,240 = 차 1건.** 전량 식별했다 — `PR 매쉬업` @ `blog.theprconsulting.com/738` 이 청크 **#30·#40** 두 곳에 있고 **양쪽 다 ③**이다.
- **[J] 같은 (문구,URL)이 청크마다 다른 verdict 를 받은 쌍 = 0.** → 문구 단위 집계 전제는 유지된다.

### 3-b. (a) 고유 문구 수 = **922**

**라벨 하한이 922 다.** 기준 600 초과 → STOP-1 발동.

### 3-c. (b) 문구별 자수 히스토그램 (고유 문구 922 기준)

| 자수 구간 | 문구 수 |
|---|---|
| 1 | **0** |
| 2–3 | 175 |
| 4–5 | 198 |
| 6–7 | 153 |
| 8–9 | 91 |
| 10–14 | 110 |
| 15–19 | 47 |
| 20–29 | 68 |
| 30–49 | 57 |
| 50–99 | 20 |
| 100+ | 3 |
| 버킷 밖 `?` | **0** |
| **합계** | **922 = 10자 미만 617 + 10자 이상 305** |

- 1자 버킷 **0건**을 명시 출력했다(1차 I). `find_chains` 하한 `MIN_SPAN=2` 와 정합.
- `?` 버킷 **0건** — 버킷 설계 누락 없음.

### 3-d. (c) 문구별 출현 URL 수 분포

| 출현 URL 수 | 문구 수 |
|---|---|
| 1 | **708** |
| 2 | 159 |
| 3 | 30 |
| 4 | 15 |
| 5 | 4 |
| 6 | 3 |
| 8 | 1 |
| 9 | 2 |

- **전파 배수(쌍/문구) = 1,240 / 922 = 1.345**
- 레코드 배수(레코드/문구) = 1,241 / 922 = 1.346
- 🔴 **76.8% 가 단일 URL 문구다.** 전파가 성립하는 문구는 214건(23.2%)뿐이고, 그중에서도 5 URL 이상은 10건이다.

---

## 4. 측정 (d) — 자수 구간별 양측 출현률 (핵심)

### 4-a. 판정 축 (출현 1건 단위)

| 칸 | 정의 |
|---|---|
| **크롬측** | `cat_of_one ∈ {1,2,3}` — 구조 태그·class/id 이름으로 크롬 식별됨 |
| **본문측** | cat 4 이고 `체인토큰[:8] − 본문대조토큰 = ∅` — 본문과 구조 동일, 못 가름 |
| **중간** | cat 4 인데 차집합 있음(④-구분가능) **또는** 대조군 0 (판정 불가) — **catch CM: 어느 쪽으로도 안 민다** |

| 정의 | 양측 조건 |
|---|---|
| **D-strict (하한)** | 크롬측{1,2,3} **AND** 본문측 |
| **D-loose (상한)** | 크롬측{1,2,3}+중간 **AND** 본문측 |

**STOP 판정은 loose(상한) 기준** — 멈추는 쪽이 안전 방향 (1차 지시 E).

### 4-b. (d-전체) — 모집단 문구 922

| 자수 | 문구 | strict | % | loose | % | 페이지내 양측 |
|---|---|---|---|---|---|---|
| 2–3 | 175 | 11 | **6.3%** | 11 | **6.3%** | 11 |
| 4–5 | 198 | 1 | 0.5% | 1 | 0.5% | 1 |
| 6–7 | 153 | 0 | 0.0% | 0 | 0.0% | 0 |
| 8–9 | 91 | 0 | 0.0% | 0 | 0.0% | 0 |
| **10–14** | 110 | 0 | **0.0%** | 1 | **0.9%** | 0 |
| 15–19 | 47 | 0 | 0.0% | 0 | 0.0% | 0 |
| 20–29 | 68 | 0 | 0.0% | 0 | 0.0% | 0 |
| 30–49 | 57 | 0 | 0.0% | 0 | 0.0% | 0 |
| 50–99 | 20 | 0 | 0.0% | 0 | 0.0% | 0 |
| 100+ | 3 | 0 | 0.0% | 0 | 0.0% | 0 |

### 4-c. (d-결손제외) — 모집단 문구 878 (1차 G)

대조군 0건 URL(`brandb.net` 1건) · HTML 부재 · 0출현 쌍을 뺀 판.

| 자수 | 문구 | strict | % | loose | % | 페이지내 양측 |
|---|---|---|---|---|---|---|
| 2–3 | 173 | 11 | 6.4% | 11 | 6.4% | 11 |
| 4–5 | 192 | 1 | 0.5% | 1 | 0.5% | 1 |
| 6–7 | 144 | 0 | 0.0% | 0 | 0.0% | 0 |
| 8–9 | 87 | 0 | 0.0% | 0 | 0.0% | 0 |
| **10–14** | 104 | 0 | 0.0% | 1 | **1.0%** | 0 |
| 15–19 | 42 | 0 | 0.0% | 0 | 0.0% | 0 |
| 20–29 | 64 | 0 | 0.0% | 0 | 0.0% | 0 |
| 30–49 | 53 | 0 | 0.0% | 0 | 0.0% | 0 |
| 50–99 | 17 | 0 | 0.0% | 0 | 0.0% | 0 |
| 100+ | 2 | 0 | 0.0% | 0 | 0.0% | 0 |

**두 판의 판정이 일치한다** → 2차 P5-2 의 불일치 규칙은 발동하지 않았다.

### 4-d. 편향 4건(F·G·H·I) 계상 (1차 지시 2급, self-check #20)

| 항목 | 실측 | (d) 에 미치는 방향 |
|---|---|---|
| **F** HTML 부재 | **0건** | 없음 |
| **F** 파일 있으나 0출현 | **0건** | 없음 |
| **G** 대조군 0건 URL | **1건** (`brandb.net`, 쌍 44개·문구 44개 영향) | 하향 → 결손제외판으로 분리 산출 |
| **H** 토큰화 범위 비대칭 | **원본 그대로 유지** (대조군=체인 전체 / 히트=`chain[:8]`) | 상향 |
| **I** 1자 문구 | **0건** | 없음 |

→ **F·I 가 0건이라 순효과는 G(하향) vs H(상향) 2건으로 좁혀졌고, 두 판의 판정이 같아 결론이 뒤집히지 않는다.**

### 4-e. 🔴 (d) 육안 판정표 — 양측(loose) 문구 **전건 13건** (1차 B, self-check #17)

`Q2 §6.1 A-1-a` 형식. **표본이 아니라 전건이다.** 매칭 실물 502행 전량은 `_s4_bilateral.json`.

| # | 문구 | 자수 | URL수 | chrome | body | mid | 판정 근거 (육안) |
|---|---|---|---|---|---|---|---|
| 1 | `'시그니처 사운드 마케팅'` | **14** | 1 | 0 | 1 | 1 | 🔴 **유일한 10자 이상 양측.** body 출현은 본문 산문 *"…이게 바로 '시그니처 사운드 마케팅'이에요!"* (`p → section → div#content…`). chrome 출현 **0** → strict 양측 아님. loose 만 성립 |
| 2 | `AI` | 2 | 4 | 21 | 7 | 18 | body 7건 전부 기사 본문 문장 (`p.wrap_item.item_type_text`) |
| 3 | `기획` | 2 | 1 | 1 | 1 | 1 | body = *"…내년 팝업 기획의 방향을…"* 본문 |
| 4 | `로그인` | 3 | 9 | 18 | 1 | 10 | body 1건 = *"더보기 클릭 시: 로그인 필요 안내 모달…"* — 본문 성격 애매하나 구조상 `div.layout-content-container → body` |
| 5 | `마케팅` | 3 | 2 | 18 | 10 | 21 | body 10건 전부 본문 산문 |
| 6 | `브랜드` | 3 | 3 | 4 | **46** | 13 | body 다수 = 본문 산문 전면 |
| 7 | `역사` | 2 | 3 | 3 | 1 | 1 | 본문 어휘 충돌 |
| 8 | `재능넷` | 3 | 2 | 28 | 6 | 17 | 사이트명이 본문에도 등장 |
| 9 | `전시` | 2 | 1 | 1 | 19 | 5 | body 다수 |
| 10 | `캠페인` | 3 | 1 | 1 | 35 | 3 | body 다수 |
| 11 | `콘텐츠` | 3 | 4 | 17 | 7 | 15 | 본문 어휘 충돌 |
| 12 | `팝업` | 2 | 2 | 6 | 22 | 19 | body 다수 |
| 13 | `팝업스토어` | 5 | 4 | 83 | 13 | 8 | chrome 우세, body 13 |

**육안 판정 요지** — 13건 중 **12건이 2~5자 일반 명사**이고, body 측 출현은 전부 기사 본문 문장이다. `R9 §7` 의 *"10자 미만 짧은 단어의 본문 어휘 충돌"* 패턴과 동형이다. **10자 이상은 1건**(`'시그니처 사운드 마케팅'`)이며 그마저 chrome 측 출현이 0이라 strict 로는 양측이 아니다.

→ **T=10 경계는 (d) 실측에서 지지된다.** `R9 §7` 이 ④확정 9건에서 얻은 "10자 미만 8 / 10자 이상 1" 비율이 1,241 전체 분포에서도 재현됐다.
⚠️ **단 T 값은 여기서 확정하지 않는다** (챗 소관, 2차 지시 §6).

---

## 5. 역산 라벨 — `<T` 단위 3값 병기 (1차 C, self-check #18)

인계문 §2-d 공식 `고유문구(≥T) + 출현(<T)` 의 "출현" 단위가 3가지로 해석 가능해 **전부 낸다. 채택은 챗 소관.**

| 단위 | 뜻 |
|---|---|
| **쌍** | (문구,URL) 쌍 수 |
| **레코드** | 청크×문구 레코드 수 (`R9 §3-b` 판정 단위에 가장 가까움) |
| **페이지출현** | 그 페이지의 DOM 출현 전수 |

| T | ≥T 문구 | strict | loose | `<T` 쌍 | `<T` 레코드 | `<T` 페이지출현 | **역산 라벨 [쌍 \| 레코드 \| 페이지출현]** | STOP-2 |
|---|---|---|---|---|---|---|---|---|
| 8 | 396 | 0.0% | 0.3% | 754 | 755 | 1,920 | **[1,150 \| 1,151 \| 2,316]** | 미발동 |
| **10** | **305** | **0.0%** | **0.3%** | **883** | **884** | **2,125** | **[1,188 \| 1,189 \| 2,430]** | **미발동** |
| 12 | 245 | 0.0% | 0.4% | 952 | 953 | 2,255 | [1,197 \| 1,198 \| 2,500] | 미발동 |
| 15 | 195 | 0.0% | 0.0% | 1,013 | 1,014 | 2,341 | [1,208 \| 1,209 \| 2,536] | 미발동 |
| 20 | 148 | 0.0% | 0.0% | 1,065 | 1,066 | 2,416 | [1,213 \| 1,214 \| 2,564] | 미발동 |

(결손제외판은 `_s4_census.json` `t_rows` 의 `T*-결손제외` 키. ≥T 문구만 줄고 `<T` 3값은 동일하다.)

🔴 **어느 T 를 골라도 역산 라벨이 잔여 레코드 1,241 과 같은 자릿수이거나 크다.** T 를 올릴수록 오히려 는다 — 짧은 문구가 출현 단위로 세어지기 때문이다. 이것이 STOP-1 의 실질이다.

---

## 6. ② 627 의 태그별 내역 (인계문 §2-e — "이 값은 지금 모른다")

레코드 627 기준. 한 체인에 구조 태그가 여럿 있을 수 있어 **3가지로 낸다.**

| 세는 법 | 내역 |
|---|---|
| **중복허용** (체인에 그 태그가 있으면 1) | `header` **334** · `nav` 297 · `footer` 264 · `aside` 45 |
| **조합배타** | `footer` 214 · `header+nav` 207 · **`header` 단독 79** · `nav` 34 · `aside+nav` 27 · `footer+header+nav` 26 · `footer+header` 21 · `aside` 16 · `footer+nav` 1 · `aside+footer+nav` 1 · `aside+footer+header+nav` 1 |
| **최근접**(가장 안쪽 구조 태그) | `nav` 285 · `footer` 227 · **`header` 98** · `aside` 17 |

### 6-a. STOP-3 — ⚠️ 판정 보류

| 기준 후보 | 값 | 과반 여부 |
|---|---|---|
| **포함** (중복허용) | 334 / 627 = **53.3%** | ✅ 과반 |
| **단독** (조합배타) | 79 / 627 = **12.6%** | ❌ |
| (참고) 최근접 | 98 / 627 = 15.6% | ❌ |

🔴 **어느 것을 기준으로 삼느냐로 판정이 뒤집힌다.** 인계문·1차 지시 모두 이를 미정으로 남겼으므로 **CC 는 확정하지 않는다. 값만 넘긴다.**

**관측 1건 (판정 아님)** — `header` 334 중 **207건이 `nav` 와 동반**한다(`header+nav`, `footer+header+nav`, `aside+footer+header+nav` 합 234 중 `header+nav` 207). 인계문 §2-e 가 우려한 것은 *`<article>` 내부의 `<header>`(기사 제목)* 인데, `nav` 동반 header 는 전형적 사이트 헤더다. **`header` 단독 79 가 우려 대상에 더 가깝다** — 다만 이는 구조 추론이며 **실측하지 않았다.** `<article>` 조상 유무를 세면 $0 로 닫힌다(다음 세션 후보).

---

## 7. Self-check

### 7-a. 인계문 §6 (#1~14)

| # | 항목 | 결과 |
|---|---|---|
| 1 | 유료 API 호출 | **S4 = 0.** 네트워크 호출 0, 임베딩 0, LLM 0. 실측 비용 **$0** |
| 2 | 파이프라인 `.py` 수정 | **0건.** `git diff --name-status` → `writer_project/scripts/§paper-writer-1/measure_paper.py` 1건뿐이며 **세션 시작 시점부터 있던 논문 트랙 기존 수정분**(초기 `git status` 스냅샷에 존재). 이번 작업이 만든 변경 아님 |
| 3 | `prompts.py` 무수정 | `git status --short "**/prompts.py"` → **0줄** |
| 4 | `web_search.py:848` 무접촉 | `git status --short "**/web_search.py"` → **0줄** |
| 5 | 신규 탐침 커밋 제외 | `probe_s4_census.py` → `git check-ignore` = `writer_project/.gitignore:110 probe_*` ✅. ⚠️ **인계문 기재 `:106` 은 오기** — 실물은 `:110` |
| 6 | 재귀 grep 0건 미사용 | 해당 1건 — `grep -rn "build_body_ctx(" --include="probe_*.py" .` 심 grep **0건** vs `command grep` **4건**(cwd=`writer_project/`). catch CG 재현. **0건을 부재 근거로 쓰지 않고 `command grep` 결과를 채택** |
| 7 | 정규식으로 판정 안 함 | 후보 추출만 substring, 판정은 §4-e 전건 육안 + `_s4_bilateral.json` 502행 전량 덤프 |
| 8 | (d) 산출이 T 확정보다 선행 | ✅ **T 를 확정하지 않았다.** (d) 표 → T 후보표 순으로 산출하고 확정은 챗에 넘김 |
| 9 | 한계(자기 채점) 명시 | §1 서두 |
| 10 | Z'' 문안 무수정 | **해당 없음** (S6 미착수) |
| 11 | 배분 무교정 | **해당 없음** (S6 미착수) |
| 12 | STOP 경계 확정 금지 | STOP-1 = 밴드 밖이라 확정 발동 / STOP-2 = 두 판 일치 미발동 / **STOP-3 = 보류** |
| 13 | deviation 자진 보고 | §8 |
| 14 | 한 작업씩 후 정지 | ✅ **S5·S6 착수 0.** 유료 구간 진입 0 |

### 7-b. 1차 지시 §4 (#15~22)

| # | 항목 | 결과 |
|---|---|---|
| 15 | 양성 대조 assert 통과 | `1241 / 627 / 452 / 162` **첫 실행 통과.** 코드를 고쳐 숫자를 맞춘 일 **없음** |
| 16 | 대조군 로직 복제 0 | `import probe_s2_agg as A` → `A.build_body_ctx(...)` · `A.MIN_CTL` · `A.tokens`. 로컬 복제 삭제. 추출 후 R9 재현 확인 = §9-b |
| 17 | (d) 육안 판정표 | §4-e, **전건 13문구** (표본 아님). 매칭 실물 502행 = `_s4_bilateral.json` |
| 18 | `<T` 3값 병기 | §5 표 — 쌍 / 레코드 / 페이지출현 |
| 19 | STOP 3건 3상태 | §0 표. STOP-3 은 경계가 아니라 **기준 미정에 의한 보류** |
| 20 | 편향 4건 계상 | §4-d. (d) 두 벌(전체 §4-b / 결손제외 §4-c) |
| 21 | catch CL·CM 등재 | §2 (+ CN 신규 제안) |
| 22 | `import probe_s2_tagmap` 부작용 | **0줄** 실측 (§9-a) |

### 7-c. 2차 지시 §4 (#23~28)

| # | 항목 | 결과 |
|---|---|---|
| 23 | `probe_s2_agg.py` 수정 내역 | `keep_nodes=False` 신설 · `__main__` 가드 신설 · `THRESHOLDS`/`MIN_CTL` 모듈 상수화 · `load()`/`chrome_keys_of()`/`build_body_ctx()` 추출. **diff 전문 = §9-c** |
| 24 | **R9 재현 확인** | ✅ **전항 일치** — ②627 / ③452 / ④구분가능162 / ④확정72 / MISS 51(SPLIT 9 + DRIFT 42) / span 1,364 / ④확정 보유 청크 11건 동일. **원본 실행 출력과 diff 0줄, `_s2_final.json` sha256 동일.** 출력 = §9-b |
| 25 | P2 내용 assert | **개수 불일치 0 · 내용 불일치 0.** assert 완화 **없음**. `find_chains` 술어 인용 = §9-d |
| 26 | 예외 가드 3곳 | `trow` 조회 → `.get()` + 부재 시 `판정 불가 (≥T 문구 0건)` 명시 / 참고값·② 비율 → `pct()` 분모 0 가드(`n/a (모집단 0)`) / **덤프 2개를 STOP 출력보다 먼저 기록** (실행 로그에 `← STOP 출력보다 먼저 기록됨` 확인) |
| 27 | STOP 3건 최종 | STOP-1 밴드(570~630) 적용 → 922 는 밴드 밖 **확정 발동** / **STOP-2 두 판 일치**(둘 다 미발동) → 불일치 규칙 미발동 / STOP-3 보류 유지 |
| 28 | `_s4_bilateral.json` | **277,514 B** (`_s4_census.json` 165,872 B). **절단 0행** — 502행 전부 전문 보존. 정책 = 전문 ≤400자, 초과 시 매칭 위치 ±40자 |

---

## 8. deviation (자진 보고)

| # | 내용 | 판단 |
|---|---|---|
| 1 | 🔴 **`probe_s2_agg.py` 를 수정했다** — `__main__` 가드·`keep_nodes` 신설, 함수 추출. 1차 지시 D-3 이 명시 허용(`probe_*` 는 커밋 대상 아님)하나 **원본 수정 이력이므로 전건 기재**한다. 증거 3종 = §9-b(재현) · §9-c(diff) · P1-1(기본값·호출부) | 지시 범위 내 |
| 2 | 🔴 **가드 없는 상태에서 `import probe_s2_agg` 를 1회 실행해 `_s2_final.json` 이 덮어써졌다** (P3 이전, L 실측 중). 재생성 결과가 원본과 **sha256 동일**이라 실질 피해 0. 이 사고가 catch CN 제안의 근거다 | 사고. 무해 확인 |
| 3 | 인계문 §2-c 는 (d) 를 단일값으로 규정했으나 **strict/loose 2값**으로 냈다 | 1차 지시 0절에서 채택 확인됨 |
| 4 | 지시에 없는 **참고 모집단(④확정 포함)** 을 추가 산출했다 | 1차 지시 0절·2차 지시 §5 에서 유지 확인됨. STOP 판정 비사용 |
| 5 | 인계문 §2-c 는 (a)~(d) 를 요구했고 **②태그 내역을 3가지 세는 법**으로 확장했다 | STOP-3 기준이 미정이라 한 값만 내면 판정이 임의가 된다 |
| 6 | P3 명령 출력이 지시 문안의 "6줄"이 아니라 **5줄**이었다 | 마지막 `print` 가 3객체를 한 줄에 내기 때문. `print` 문 5개 = 5줄이 정상 |
| 7 | §6-a 의 `header+nav` 동반 관측은 **구조 추론이며 실측 아님**. `<article>` 조상 유무는 세지 않았다 | STOP 발동 후 범위 확대를 피함 |

### 8-a. 미수행 (지시 범위 밖으로 판단)

- **S5·S6 착수 0** (사용자 지시 — "S4만 수행하고 멈춰라")
- **표본 추출·라벨 부착 0** (인계문 §2-i — S4 는 세기까지)
- **T 확정값 · 조건 A 의 N 값 · 표본 규모 채택 · STOP-3 기준** — 4건 전부 챗 소관, 값만 실었다
- **규칙 R 문안 0** (라벨 봉인 커밋 이후)

---

## 9. 부록

### 9-a. import 부작용 실측 (1차 L · 2차 P3)

```
$ python -c "import probe_s2_tagmap"          → 출력 0줄, exit 0
$ python -c "import probe_s2_agg"  (가드 전)  → 출력 56줄 🔴 R9 전량 재실행
$ python -c "import probe_s2_agg"  (가드 후)  → 출력 0줄, exit 0

$ python -c "import probe_s2_tagmap as P, probe_s2_agg as A; \
    print('MIN_SPAN', P.MIN_SPAN); print('MIN_CTL', A.MIN_CTL); \
    print(A.build_body_ctx); print(A.tokens); print(P.find_chains, P.cat_of_one, P.norm)"
MIN_SPAN 2
MIN_CTL 3
<function build_body_ctx at 0x110cff9c0>
<function tokens at 0x110cff880>
<function find_chains at 0x110cff240> <function cat_of_one at 0x110cff2e0> <function norm at 0x110cff1a0>
```

**심볼 4개 전부 존재. R9 진행 로그 0줄.**

`build_body_ctx` 기본값·호출부 (cwd = `writer_project/`):

```
$ command grep -n "def build_body_ctx" probe_s2_agg.py
74:def build_body_ctx(url_chunks, frag, full, keep_nodes=False)   ← 기본값 있음

$ command grep -rn "build_body_ctx(" --include="probe_*.py" .
./probe_s2_agg.py:130:    body_ctx = build_body_ctx(url_chunks, frag, full)      ← 기본 경로
./probe_s4_census.py:142: body_ctx, nodes = A.build_body_ctx(..., keep_nodes=True)

$ grep -rn "build_body_ctx(" --include="probe_*.py" .   ← 심 grep
0건   🔴 catch CG — probe_* 는 gitignore 대상이라 재귀 탐색에서 빠진다
```

### 9-b. R9 재현 출력 (2차 P1-2 / self-check #24)

수정 후 `probe_s2_agg.py` 재실행 결과 (말미):

```
------------------------------------------------------------------------
span 합계  ④확정=72  ④구분가능=162  ④미확정=0

④확정 span 을 하나라도 가진 청크 = 11건 [4, 20, 22, 28, 35, 41, 43, 45, 56, 58, 59]
④미확정 span 을 가진 청크        = 0건 []
```

원본 실행 출력과의 diff:

```
$ diff agg_baseline.out agg_p12.out
(차이 없음 — 0줄)
```

`_s2_final.json` sha256 (수정 전 = 수정 후):

```
5c804500524314158ea1a930dc59fedf2347a8e3a9077591f3beff089d1c6d28
```

`R9 §6-a` 전항 대조:

```
실측 {'2': 627, '3': 452, '4-구분가능': 162, '4확정': 72, 'DRIFT': 42, 'SPLIT': 9}
R9   {'2': 627, '3': 452, '4-구분가능': 162, '4확정': 72, 'DRIFT': 42, 'SPLIT': 9}
span 합계 1364 (R9 1364)   MISS 51 (R9 51)
전항 일치
```

### 9-c. `probe_s2_agg.py` diff 전문 (2차 P1-3 / self-check #23)

**H 확인** — 아래 diff 에서 대조군 토큰은 `for ch in chosen: tok |= tokens(ch)`(체인 **전체**), 히트 토큰은 `main()` 의 `tokens(rep)`(= `reps['4']` = `probe_s2_tagmap.classify` 가 `h["chain"][:8]` 로 저장)로 **원본과 동일하게 비대칭**이다. 변경 없음.

```diff
--- probe_s2_agg.py (2026-08-09 16:43:56, 수정 전 사본)
+++ probe_s2_agg.py (2026-08-09 16:45:03, 수정 후)
@@ -9,6 +9,15 @@
      차집합이 공집합이면 = 본문과 구조 동일 → **④ 확정**.
      차집합이 있으면 크롬만 가진 컨테이너가 존재하므로 단서가 될 수 있다
      → **④-구분가능**으로 분리한다(STOP 합계에서 뺀다).
+
+⚠️ 2026-08-09 S4 리팩터 (동작 무변경, 순수 추출).
+   사유 = `CC_ADDENDUM_20260809_S4_probe_review.md` D
+   ("대조군 선정 로직을 복제하지 말고 import 한다").
+   - 모듈 본문 실행부 → `main()` + `__main__` 가드.
+     🔴 이전에는 가드가 없어 `import probe_s2_agg` 만으로 전량 재실행 +
+     `_s2_final.json` 덮어쓰기가 일어났다(2026-08-09 실측).
+   - 대조군 선정부 → `build_body_ctx()` 로 추출. `MIN_CTL` → 모듈 상수.
+   - 추출 후 스크립트 재실행으로 R9 값 재현을 확인했다(D-4).
 """
 from __future__ import annotations
 
@@ -20,14 +29,29 @@
 import probe_s2_tagmap as P
 
 OUT = P.OUT
-raw = json.loads((OUT / "_s2_tagmap_raw.json").read_text(encoding="utf-8"))
-rows, full, frag = P.parse_r8()
 
-url_chunks: dict[str, list[int]] = {}
-for n, r in rows.items():
-    url_chunks.setdefault(r["url"], []).append(n)
+# 40 추가 (2026-08-09) — brunch 는 문장을 <br>/<span> 으로 잘게 쪼개 렌더링해
+# 본문 최대 행이 67자다. 80 에서 0건이 난 것은 "본문 없음"이 아니라
+# "본문 노드가 전부 짧음"이었다. 임계 설계 탓이지 페이지 탓이 아니다.
+THRESHOLDS = (200, 120, 80, 40)
 
+# 🔴 "≥1건이면 만족"으로 멈추지 않는다 (2026-08-09 2차 정정).
+# #45 는 임계 200 에서 1건이 잡혀 폴백이 멈췄으나 120 으로 내리면 14건이었다.
+# 대조군이 얇으면 본문 토큰 집합이 작아져 차집합이 남기 쉽고,
+# 판정이 ④확정 → ④-구분가능 쪽으로 기운다. 즉 **④를 과소 계상**한다.
+# 방향이 STOP 기준과 반대이므로 최소 두께 MIN_CTL 을 요구한다.
+MIN_CTL = 3
 
+
+def load():
+    raw = json.loads((OUT / "_s2_tagmap_raw.json").read_text(encoding="utf-8"))
+    rows, full, frag = P.parse_r8()
+    url_chunks: dict[str, list[int]] = {}
+    for n, r in rows.items():
+        url_chunks.setdefault(r["url"], []).append(n)
+    return raw, rows, full, frag, url_chunks
+
+
 def tokens(chain):
     """체인을 태그·class·id 토큰 집합으로."""
     out = set()
@@ -37,112 +61,131 @@
     return out
 
 
-# ── (1) 본문 대조군 (임계 폴백) ────────────────────────────────
-body_ctx = {}
-for u in sorted(url_chunks):
-    p = P.HTMLDIR / (P.slug(u) + ".html")
-    if not p.exists():
-        continue
-    soup = BeautifulSoup(p.read_text(encoding="utf-8"), "lxml")
-    nodes = P.text_nodes(soup)
+def chrome_keys_of(u, url_chunks, frag, full):
+    """URL 이 보유한 청크 전체의 크롬 문구 집합 (대조군 제외 열쇠 원본)."""
     ck = set()
     for n in url_chunks[u]:
         ck |= set(frag.get(n, []))
         if n in full:
             ck |= {P.norm(x) for x in full[n].split("\n") if P.norm(x)}
-    keys = [k for k in ck if len(k) >= P.MIN_KEY]
+    return ck
 
-    # 40 추가 (2026-08-09) — brunch 는 문장을 <br>/<span> 으로 잘게 쪼개 렌더링해
-    # 본문 최대 행이 67자다. 80 에서 0건이 난 것은 "본문 없음"이 아니라
-    # "본문 노드가 전부 짧음"이었다. 임계 설계 탓이지 페이지 탓이 아니다.
-    #
-    # 🔴 "≥1건이면 만족"으로 멈추지 않는다 (2026-08-09 2차 정정).
-    # #45 는 임계 200 에서 1건이 잡혀 폴백이 멈췄으나 120 으로 내리면 14건이었다.
-    # 대조군이 얇으면 본문 토큰 집합이 작아져 차집합이 남기 쉽고,
-    # 판정이 ④확정 → ④-구분가능 쪽으로 기운다. 즉 **④를 과소 계상**한다.
-    # 방향이 STOP 기준과 반대이므로 최소 두께 MIN_CTL 을 요구한다.
-    MIN_CTL = 3
-    cands = []
-    for th in (200, 120, 80, 40):
-        got = []
-        for t, node in nodes:
-            if len(t) < th or any(k in t for k in keys):
-                continue
-            got.append(P.chain_of(node))
-            if len(got) >= 8:
+
+def build_body_ctx(url_chunks, frag, full, keep_nodes=False):
+    """④ 판정용 같은-페이지 본문 대조군을 URL 별로 만든다.
+
+    ⚠️ 토큰화 범위는 **비대칭**이다 (원본 유지 — addendum H).
+      · 대조군 : `tokens(ch)`             = 체인 **전체**
+      · 히트   : `tokens(reps['4'])`      = `probe_s2_tagmap.classify` 가
+                 `h["chain"][:8]` 로 잘라 저장한 값
+    대조군 토큰이 더 커져 `extra` 가 줄고 → ④확정 쪽으로 기운다.
+    R9 박제값이 이 비대칭 위에서 나왔으므로 **고치지 않고 기록만 한다.**
+
+    keep_nodes=True 면 파싱한 텍스트 노드도 함께 돌려준다(재파싱 회피).
+    """
+    body_ctx, nodes_all = {}, {}
+    for u in sorted(url_chunks):
+        p = P.HTMLDIR / (P.slug(u) + ".html")
+        if not p.exists():
+            continue
+        soup = BeautifulSoup(p.read_text(encoding="utf-8"), "lxml")
+        nodes = P.text_nodes(soup)
+        if keep_nodes:
+            nodes_all[u] = nodes
+        keys = [k for k in chrome_keys_of(u, url_chunks, frag, full)
+                if len(k) >= P.MIN_KEY]
+
+        cands = []
+        for th in THRESHOLDS:
+            got = []
+            for t, node in nodes:
+                if len(t) < th or any(k in t for k in keys):
+                    continue
+                got.append(P.chain_of(node))
+                if len(got) >= 8:
+                    break
+            cands.append((th, got))
+            if len(got) >= MIN_CTL:
                 break
-        cands.append((th, got))
-        if len(got) >= MIN_CTL:
-            break
-    # MIN_CTL 을 채운 첫 임계. 어느 임계도 못 채우면 가장 많이 나온 것.
-    chosen, used_th = [], None
-    for th, got in cands:
-        if len(got) >= MIN_CTL:
-            chosen, used_th = got, th
-            break
-    else:
-        th, got = max(cands, key=lambda x: len(x[1]))
-        if got:
-            chosen, used_th = got, th
-    tok = set()
-    for ch in chosen:
-        tok |= tokens(ch)
-    body_ctx[u] = {"n": len(chosen), "th": used_th, "tok": tok,
-                   "chains": [c[:6] for c in chosen[:3]]}
+        # MIN_CTL 을 채운 첫 임계. 어느 임계도 못 채우면 가장 많이 나온 것.
+        chosen, used_th = [], None
+        for th, got in cands:
+            if len(got) >= MIN_CTL:
+                chosen, used_th = got, th
+                break
+        else:
+            th, got = max(cands, key=lambda x: len(x[1]))
+            if got:
+                chosen, used_th = got, th
+        tok = set()
+        for ch in chosen:
+            tok |= tokens(ch)
+        body_ctx[u] = {"n": len(chosen), "th": used_th, "tok": tok,
+                       "chains": [c[:6] for c in chosen[:3]]}
+    return (body_ctx, nodes_all) if keep_nodes else body_ctx
 
-no_ctl = [u for u in body_ctx if not body_ctx[u]["n"]
-          and any(n in frag or n in full for n in url_chunks[u])]
-print(f"[대조군] 임계 폴백 후 0건 URL = {len(no_ctl)}")
-for u in no_ctl:
-    print(f"   청크{[n for n in url_chunks[u] if n in frag or n in full]}  {u[:75]}")
-print(f"[대조군] 임계별 URL 수 = "
-      f"{ {th: sum(1 for v in body_ctx.values() if v['th'] == th) for th in (200,120,80)} }")
 
-# ── (2) ④ 확정 / 구분가능 / 미확정 ────────────────────────────
-out = {}
-for k, ch in raw["chunks"].items():
-    n = int(k)
-    if ch["status"] != "OK":
-        continue
-    u = ch["meta"]["url"]
-    ctx = body_ctx.get(u, {"n": 0, "tok": set()})
-    recs = []
-    for s in ch["spans"]:
-        v = s["verdict"]
-        if v != "4":
-            recs.append({**s, "final": v})
+def main():
+    raw, rows, full, frag, url_chunks = load()
+    body_ctx = build_body_ctx(url_chunks, frag, full)
+
+    no_ctl = [u for u in body_ctx if not body_ctx[u]["n"]
+              and any(n in frag or n in full for n in url_chunks[u])]
+    print(f"[대조군] 임계 폴백 후 0건 URL = {len(no_ctl)}")
+    for u in no_ctl:
+        print(f"   청크{[n for n in url_chunks[u] if n in frag or n in full]}  {u[:75]}")
+    print(f"[대조군] 임계별 URL 수 = "
+          f"{ {th: sum(1 for v in body_ctx.values() if v['th'] == th) for th in (200,120,80)} }")
+
+    # ── (2) ④ 확정 / 구분가능 / 미확정 ────────────────────────────
+    out = {}
+    for k, ch in raw["chunks"].items():
+        n = int(k)
+        if ch["status"] != "OK":
             continue
-        rep = s["reps"].get("4", [])
-        if not ctx["n"]:
-            recs.append({**s, "final": "4-미확정"})
-            continue
-        extra = tokens(rep) - ctx["tok"]
-        recs.append({**s, "final": "4확정" if not extra else "4-구분가능",
-                     "extra": sorted(extra)[:6]})
-    out[n] = {"meta": ch["meta"], "src": ch["src"], "spans": recs,
-              "body_n": ctx["n"], "body_th": ctx.get("th")}
+        u = ch["meta"]["url"]
+        ctx = body_ctx.get(u, {"n": 0, "tok": set()})
+        recs = []
+        for s in ch["spans"]:
+            v = s["verdict"]
+            if v != "4":
+                recs.append({**s, "final": v})
+                continue
+            rep = s["reps"].get("4", [])
+            if not ctx["n"]:
+                recs.append({**s, "final": "4-미확정"})
+                continue
+            extra = tokens(rep) - ctx["tok"]
+            recs.append({**s, "final": "4확정" if not extra else "4-구분가능",
+                         "extra": sorted(extra)[:6]})
+        out[n] = {"meta": ch["meta"], "src": ch["src"], "spans": recs,
+                  "body_n": ctx["n"], "body_th": ctx.get("th")}
 
-(OUT / "_s2_final.json").write_text(
-    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
+    (OUT / "_s2_final.json").write_text(
+        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
 
-print("\n{:>4} {:>7} {:>6} {:>7} {:>9} {:>8} {:>6} {:>6}".format(
-    "청크", "spans", "④확정", "④구분가", "④미확정", "①②③", "SPLIT", "DRIFT"))
-print("-" * 72)
-tot = {"4확정": 0, "4-구분가능": 0, "4-미확정": 0}
-for n in sorted(out):
-    sp = out[n]["spans"]
-    c = lambda v: sum(1 for x in sp if x["final"] == v)  # noqa: E731
-    for kk in tot:
-        tot[kk] += c(kk)
-    print("{:>4} {:>7} {:>6} {:>7} {:>9} {:>8} {:>6} {:>6}  body={}@{}".format(
-        n, len(sp), c("4확정"), c("4-구분가능"), c("4-미확정"),
-        c("1") + c("2") + c("3"), c("SPLIT"), c("DRIFT"),
-        out[n]["body_n"], out[n]["body_th"]))
-print("-" * 72)
-print(f"span 합계  ④확정={tot['4확정']}  ④구분가능={tot['4-구분가능']}  "
-      f"④미확정={tot['4-미확정']}")
+    print("\n{:>4} {:>7} {:>6} {:>7} {:>9} {:>8} {:>6} {:>6}".format(
+        "청크", "spans", "④확정", "④구분가", "④미확정", "①②③", "SPLIT", "DRIFT"))
+    print("-" * 72)
+    tot = {"4확정": 0, "4-구분가능": 0, "4-미확정": 0}
+    for n in sorted(out):
+        sp = out[n]["spans"]
+        c = lambda v: sum(1 for x in sp if x["final"] == v)  # noqa: E731
+        for kk in tot:
+            tot[kk] += c(kk)
+        print("{:>4} {:>7} {:>6} {:>7} {:>9} {:>8} {:>6} {:>6}  body={}@{}".format(
+            n, len(sp), c("4확정"), c("4-구분가능"), c("4-미확정"),
+            c("1") + c("2") + c("3"), c("SPLIT"), c("DRIFT"),
+            out[n]["body_n"], out[n]["body_th"]))
+    print("-" * 72)
+    print(f"span 합계  ④확정={tot['4확정']}  ④구분가능={tot['4-구분가능']}  "
+          f"④미확정={tot['4-미확정']}")
 
-ck4 = {n for n in out if any(x["final"] == "4확정" for x in out[n]["spans"])}
-ckU = {n for n in out if any(x["final"] == "4-미확정" for x in out[n]["spans"])}
-print(f"\n④확정 span 을 하나라도 가진 청크 = {len(ck4)}건 {sorted(ck4)}")
-print(f"④미확정 span 을 가진 청크        = {len(ckU)}건 {sorted(ckU)}")
+    ck4 = {n for n in out if any(x["final"] == "4확정" for x in out[n]["spans"])}
+    ckU = {n for n in out if any(x["final"] == "4-미확정" for x in out[n]["spans"])}
+    print(f"\n④확정 span 을 하나라도 가진 청크 = {len(ck4)}건 {sorted(ck4)}")
+    print(f"④미확정 span 을 가진 청크        = {len(ckU)}건 {sorted(ckU)}")
+
+
+if __name__ == "__main__":
+    main()
```

### 9-d. `find_chains` 술어 인용 (2차 P2-2 / self-check #25)

`probe_s2_tagmap.py:178-183` 원문:

```python
    key = norm(span)
    if len(key) < MIN_SPAN:
        return []
    return [{"direct": node.parent.name if node.parent else "?",
             "chain": chain_of(node)}
            for ntext, node in soup_nodes if key in ntext]
```

- 정규화 시점 — `key = norm(span)`. `ntext` 는 `text_nodes()`(`:255 t = norm(str(node))`)가 **이미 norm 적용**한 값
- 길이 하한 — `len(key) < MIN_SPAN(=2)` → `[]`
- 중복 처리 — **없음**. `soup_nodes` 원순서 그대로

`probe_s4_census.py` 재구성 술어:

```python
key = P.norm(sp)
texts = [t for t, _n in nodes[u] if key in t] if len(key) >= P.MIN_SPAN else []
```

→ **문자 단위로 동일.** 같은 `nodes[u]` 를 같은 순서로 순회하고 같은 `key in t` 술어를 쓴다.
검증 2중: 개수 assert(`len(texts) == len(hits)`) + 내용 assert(`key in P.norm(t)`) — **둘 다 불일치 0건.**

### 9-e. 산출물

| 파일 | 크기 | 추적 |
|---|---|---|
| `R10_SPAN_CENSUS.md` (이 문서) | — | **커밋 대상** |
| `_s4_census.json` | 165,872 B | `.gitignore:84 scripts/output/**/*.json` |
| `_s4_bilateral.json` | 277,514 B | `.gitignore:84` |
| `probe_s4_census.py` | — | `writer_project/.gitignore:110 probe_*` |
| `probe_s2_agg.py` (수정) | — | `writer_project/.gitignore:110 probe_*` |

---

## 10. 챗으로 넘기는 4건 (CC 확정하지 않음)

1. **T 확정값** — (d) 는 T=10 을 지지하나(§4-e) 확정은 챗
2. **조건 A 의 N 값** (제거 후 최소 길이 게이트) — S4 + Y 색인 실측 후
3. **표본 규모 숫자** — 역산 라벨 3값 중 채택 (§5)
4. **STOP-3 판정 기준** — `header` 포함(53.3%, 과반) vs 단독(12.6%, 과반 아님) (§6-a)

**+ STOP-1 발동에 따른 재설계 방향** — 인계문 §2-h 는 "중단 후 재설계"로 규정했다. 재설계는 이 문서 범위 밖이다.
