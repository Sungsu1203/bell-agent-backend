# §academic-1 Step B — Design (read-only)

> **박제 chain reference**
> - 직전 close: §14-9 `track close` (commit `902eecd`, README-dev-§14.md:294, 2026-05-18)
> - Step A 산출: `scripts/output/§academic-1/step_a_entry_audit.md` (clean pass, 5결정 사용자 컨펌 반영)
>   · driver: `scripts/§academic-1/a1_reachability.py` / `scripts/§academic-1/a2_set_diff.py`
>   · raw: `scripts/output/§academic-1/a1_reachability.json` / `a2_set_diff.json` (gitignored)
> - 본 Step 산출: 이 파일 (read-only design, **코드/config/env/topic 변경 0**)
> - 다음 step (자율 진입 금지): §academic-1 Step C — implementation (catch 43 + MODE config layer)
> - 기준 HEAD: `902eecd` / branch: `main`
> - 사용자 결정 (Step A end):
>   #1 A1 fail 3건(`journalofadvertising.org`, `earticle.net`, `kosac.or.kr`) → 본 cycle 도입 X · catch 45 로 박제
>   #2 kr_soc bucket 본 cycle 채택 = `kadpr.or.kr` 1개 / 나머지(`koads`, `kma`, `kabs`) → catch 44 박제
>   #3 도입 layer = MODE 분기 `ALLOWED_DOMAINS_EXTRA` 동적 주입 (`.env` 직접 확장 X)
>   #4 catch 43 hook 후보 A (L733-L744 진입부) 채택
>   #5 MODE field 도입 위치 = `core/config.py:472-490` RAG/검색 블록 인접 (L477 인근)

---

## B0 — add-only 32 vs 예상 34 차이 원인

**결론 (1줄)**: `a2_set_diff.py:66` 의 `bucket != "audit_only"` 필터가 reachable 36 중 `academia.edu` / `researchgate.net` 2건을 차감해 `a1_reachable=34` 가 되며, 거기서 overlap 2 (`iab.com`, `nature.com`) 가 또 차감되어 add-only=32 가 산출됨. set diff 로직에 bug 없음 — spec 그대로의 의도된 동작 (audit_only 는 default whitelist 진입 금지 분류).

**Evidence**:
- `a1_reachability.json` n_reachable=36 / n_fail=3 / n_total=39
- `a2_set_diff.py:66` → `a1_reachable = {r for r in results if r["reachable"] and r["bucket"] != "audit_only"}` → 34
- `a2_set_diff.json` "overlap": ["iab.com", "nature.com"] → 2
- 34 − 2 = 32 ✓ (audit_only 2건은 별도 `audit_only` set 으로 분리 보관 — `a2_set_diff.json:audit_only`)

**STOP condition (B0)** 미발생 — set diff 로직 bug 가능성 0.

---

## B1 — 최종 도메인 set 확정 + catch 박제

### 산식
```
a1_reachable (non audit_only) = 34
  - overlap (이미 .env/_BASE 에 포함) = 2     · iab.com, nature.com
  = add_only (Step A 산출) = 32
  - kr_soc 차감 (결정 #2) = 3                · koads.or.kr, kma.or.kr, kabs.or.kr
  = 최종 도입 후보 (이번 cycle) = 29
```
- `kadpr.or.kr` 는 add-only 32 안에 포함되어 있으며 차감 대상 아님 (`kadpr` 만 본 cycle 진입).
- A1 fail 3건은 reachable=False 라 a1_reachable 36→34 단계에서 이미 제외 — 결정 #1 은 add-only 32 수치에 영향 0 (catch 박제만 발생).

### 최종 도메인 set (29) — env paste-ready CSV
```
academic.oup.com,ama.org,arxiv.org,dbpia.co.kr,doaj.org,emerald.com,journals.sagepub.com,jstor.org,kadpr.or.kr,kci.go.kr,kiss.kstudy.com,link.springer.com,mmaglobal.com,msi.org,onlinelibrary.wiley.com,openalex.org,papers.ssrn.com,plos.org,pmc.ncbi.nlm.nih.gov,pubsonline.informs.org,riss.kr,sagepub.com,science.org,semanticscholar.org,springer.com,ssrn.com,tandfonline.com,warc.com,wiley.com
```
- 카운트 검증: 29 entries (`academic.oup.com` … `wiley.com`, alphabetical sort)
- 분포: core 17 · ad_en 6 · kr_db 5 · kr_soc 1
- 주입 layer: `ALLOWED_DOMAINS_EXTRA` (결정 #3) — 학술 토픽 env 에서 동적 주입, 기존 `.env:213 ALLOWED_DOMAINS` 78 entries **무손상**

### catch 박제 3건 (README-dev-§14 catch index 갱신 plan)

| catch | 사유 | trigger | 본 cycle 처리 |
|---|---|---|---|
| catch 43 | language-aware backend routing | 영어 토픽 priority 발생 — **본 §academic-1 진입으로 trigger 발화** | **본 cycle 구현 (Step C)** |
| catch 44 | kr_soc bucket 4-domain identity audit pending | `koads.or.kr` / `kma.or.kr` / `kabs.or.kr` (학회 정체성 best-effort 미확정) — 별도 cycle 후보 | defer · README-dev catch 44 신규 등록 |
| catch 45 | A1 fail 3건 재진입 — 특히 `earticle.net` SSL defer | Phase 학술-3 (KCI/RISS backend) 진입 시 재평가 | defer · README-dev catch 45 신규 등록 |

> 비고 — README-dev-§14.md:357 에 catch 43 은 이미 사전 등록되어 있음 (trigger="영어 토픽 priority 발생 또는 catch 38 정식 박제 후"). 본 §academic-1 진입이 첫번째 trigger 충족.

**STOP condition (B1)** 미발생 — 최종 카운트 29 ≥ 25 임계.

---

## B2 — catch 43 구현 spec (핵심)

### 2-1. heuristic 함수 spec

**시그니처**
```python
from typing import Literal

def detect_query_lang(query: str) -> Literal["en", "ko", "mixed"]:
    """Heuristic Korean-ratio classifier. 본 cycle: kor_ratio 단일 지표."""
```

**알고리즘 (pseudo-code)**
```python
def detect_query_lang(query: str) -> Literal["en", "ko", "mixed"]:
    if not query:
        return "en"  # 빈 query 는 escalation 대상이지만 lang 분기상 영문 backend default

    # 분류 대상 문자만 추출 (영문 + 한글; 숫자/공백/기호 제거)
    stripped = "".join(c for c in query if c.isalpha() or '가' <= c <= '힣')
    if not stripped:
        return "en"  # 영숫자 비율 > 0.9 등 edge case · escalation flag

    kor_chars = sum(1 for c in stripped if '가' <= c <= '힣')
    kor_ratio = kor_chars / len(stripped)

    if kor_ratio > 0.7:
        return "ko"
    if kor_ratio < 0.3:
        return "en"
    return "mixed"
```

**edge case 처리**
| 조건 | 분류 | escalation flag |
|---|---|---|
| `query == ""` | `"en"` (default 보수) | True |
| `len(query) < 5` | heuristic 그대로 | True (sample 부족) |
| `stripped == ""` (영숫자 비율 > 0.9) | `"en"` | True |
| 정상 | heuristic | False |

`escalation flag` 는 본 cycle 에서 **logger 레벨에만 노출** (`logger.debug("[lang] escalation candidate q=%r", q)`) — backend 동작 분기 무영향. Phase 학술-2+ 에서 `langdetect` 패키지 도입 검토.

### 2-2. escalation 조건 (본 cycle 처리 정책)

| trigger | 본 cycle 동작 |
|---|---|
| edge case 발생 (위 표) | logger.debug 만 (분기 영향 X) |
| 운영자 hint = `EXPECTED_LANG` env set | heuristic override (2-5 참조) |
| heuristic 정확도 issue (sample 10건 중 < 7건 일치) — B5 측정 결과 | Phase 학술-2 에서 `langdetect` 패키지 도입 (TODO 주석 1줄 stub) |

```python
# TODO(catch 43 escalation): heuristic 정확도 < 0.7 시 langdetect 도입 — Phase 학술-2 재평가
```

### 2-3. hook L733-L744 변경 spec (diff preview)

**현 코드** (`agent/web_search.py:727-744` · read-only re-inspect 확인 완료):
```python
def _run_web_search_with_guard(q: str, preview_limit: int = 5, retries: int = 2) -> bool:
    nonlocal chunk_total
    if SKIP_WEB:
        logger.info("[WEB SEARCH AGENT] SKIP_WEB_SEARCH=1 -> web search skipped.")
        return False

    q = (q or "").strip()
    if not q:
        return False

    norm_q = _normalize_query(q)
    if norm_q != (q or ""):
        logger.debug("[web_search][normalized] %s  <-  %s", norm_q, q)
    if not norm_q:
        logger.info("[web_search] empty-after-normalize -> skip")
        return False
```

**Step C 적용 시 diff preview** (이번 Step 은 preview 만, 실제 적용 X):
```diff
@@ agent/web_search.py · _run_web_search_with_guard @@
     q = (q or "").strip()
     if not q:
         return False

+    # catch 43 — language-aware backend routing (per-query, MODE=academic 만 활성)
+    if _get_cfg_attr("MODE", "business") == "academic":
+        _lang_override = _get_cfg_attr("EXPECTED_LANG", "auto")
+        _q_lang = _lang_override if _lang_override in ("en", "ko", "mixed") else detect_query_lang(q)
+        effective_skip_vertex = (_q_lang == "ko")  # ko → naver_direct 우선, vertex skip
+        logger.info("[catch43] lang=%s skip_vertex=%s q=%r", _q_lang, effective_skip_vertex, q[:60])
+    else:
+        effective_skip_vertex = _cfg_bool("SKIP_VERTEX_SEARCH", False)
+
     norm_q = _normalize_query(q)
```
- 침습 line 수: **+8 line** (insert only · 기존 line 변경 0)
- 침습 area: 단일 함수 (`_run_web_search_with_guard`) 진입부 — caller / config build / env reader 무변경
- L764 의 `_cfg_bool("SKIP_VERTEX_SEARCH", False)` 호출은 그대로 두되, 향후 `effective_skip_vertex` 변수로 치환 (Step C 마이크로 변경 1 line)

> **B2 STOP condition** 검증 — 침습 area = +8 line < 10 line 임계. 통과.

### 2-4. MODE × lang matrix (사용자 결정 #5 확정)

| MODE | lang | active backend (priority) | 본 cycle 구현 |
|---|---|---|---|
| `academic` | `en` | vertex_grounding (default 우선) → legacy multi-engine (Tavily EN-filter) | **YES** |
| `academic` | `ko` | naver_direct 우선 (vertex skip via effective_skip_vertex) → vertex_grounding fallback | **YES** — naver backend 활성 (kci.go.kr / riss.kr 등 KR DB 는 Phase 학술-3 에서 직접 API 도입) |
| `academic` | `mixed` | vertex + naver 병렬 (현 chain 의 vertex 우선 + legacy 병렬 동작 그대로 채택) | **YES** |
| `business` | any | 현 chain 무변경 — vertex (SKIP_VERTEX_SEARCH 따름) → legacy 병렬 | **invariant** (광고대행사 기존 토픽 무손상) |

> matrix 핵심: `MODE=business` 분기는 catch 43 hook 진입 자체를 skip → `effective_skip_vertex = _cfg_bool("SKIP_VERTEX_SEARCH", False)` 그대로 (현 동작과 1:1 동일).

### 2-5. EXPECTED_LANG env override spec

| 값 | 동작 |
|---|---|
| `auto` (default) | `detect_query_lang(q)` 결과 사용 |
| `en` | heuristic skip, 강제 en backend |
| `ko` | heuristic skip, 강제 ko backend |
| `mixed` | heuristic skip, 강제 mixed (vertex + naver 병렬) |
| (그 외 / 미설정) | `auto` 와 동일 |

- 토픽 env (B3 참조) 에 명시 가능 — 운영자가 토픽 단위로 hint 부여.
- catch 43 hook 내부에서 `_get_cfg_attr("EXPECTED_LANG", "auto")` 로 읽음.

---

## B3 — `topics/academic-_template.env` 구조

### Template 전체 spec (paste-ready)

```dotenv
# topics/academic-_template.env
# §academic-1 Phase 학술-1 — 학술 모드 토픽 template
# 새 학술 토픽은 이 파일을 복사해 `topics/academic-<slug>.env` 로 저장.

# ── 모드 분기 (§academic-1 신규) ──
MODE=academic                          # business (default) / academic — invariant: 미설정 시 business
EXPECTED_LANG=auto                     # auto | en | ko | mixed — catch 43 lang override

# ── 토픽 식별 ──
TOPIC_TITLE=
TOPIC_SLUG=                            # 파일명 - "academic-" prefix 제외 부분과 동일 권장

# ── 리서치 목표 (기존 컨벤션 유지) ──
BLOCKAGI_OBJECTIVE_1=
BLOCKAGI_OBJECTIVE_2=
BLOCKAGI_OBJECTIVE_3=

# ── 학술 도메인 동적 주입 (B1 최종 set · 29 entries) ──
ALLOWED_DOMAINS_EXTRA=academic.oup.com,ama.org,arxiv.org,dbpia.co.kr,doaj.org,emerald.com,journals.sagepub.com,jstor.org,kadpr.or.kr,kci.go.kr,kiss.kstudy.com,link.springer.com,mmaglobal.com,msi.org,onlinelibrary.wiley.com,openalex.org,papers.ssrn.com,plos.org,pmc.ncbi.nlm.nih.gov,pubsonline.informs.org,riss.kr,sagepub.com,science.org,semanticscholar.org,springer.com,ssrn.com,tandfonline.com,warc.com,wiley.com

# ── 게이트키핑/백엔드 toggle ──
GATE_KEEP_SOURCES=1                    # 기존 .env 와 동일 — 학술 모드에서도 ON 유지
SKIP_VERTEX_SEARCH=false               # academic default 활성 (catch 43 hook 이 per-query 재계산)

# ── Phase 학술-4 territory (defer · 주석 처리만) ──
# OUTPUT_FORMAT=                       # academic report 형식 분기 — Phase 학술-4 에서 도입
# CITATION_STYLE=                      # APA / Chicago etc. — Phase 학술-4 에서 도입
```

### Field 별 설명

| field | default | 본 cycle 활성 | 비고 |
|---|---|---|---|
| `MODE` | (unset → business) | YES (academic) | B4 layer 1 (config) 분기 진입 trigger |
| `EXPECTED_LANG` | `auto` | YES | catch 43 override |
| `TOPIC_TITLE` / `TOPIC_SLUG` | (empty) | 기존 컨벤션 동일 | — |
| `BLOCKAGI_OBJECTIVE_{1,2,3}` | (empty) | 기존 동일 | — |
| `ALLOWED_DOMAINS_EXTRA` | (empty) | YES — 29 entries | `get_allowed_domains()` 가 `_BASE ∪ ENV.ALLOWED_DOMAINS ∪ ENV.ALLOWED_DOMAINS_EXTRA` 로 union (`settings_gatekeep.py:138-155`) |
| `GATE_KEEP_SOURCES` | `1` (.env 와 동일) | invariant | — |
| `SKIP_VERTEX_SEARCH` | `false` | invariant 의도 | 실제 backend 선택은 catch 43 의 `effective_skip_vertex` 가 per-query 재계산 |
| `OUTPUT_FORMAT` / `CITATION_STYLE` | — | defer (주석) | Phase 학술-4 |

### 명명 컨벤션

- **Template 파일**: `topics/academic-_template.env`
- **실제 학술 토픽**: `topics/academic-<topic-slug>.env`
  · 예: `topics/academic-ad-platforms-en.env`, `topics/academic-marketing-roi-ko.env`
- **기존(광고대행사) 토픽**: 명명 변경 없음 — `topics/<slug>.env` 그대로
- **invariant**: 토픽 파일에 `MODE` 가 없으면 → `cfg.MODE = "business"` 로 polyfill → 기존 토픽 전수 무손상

---

## B4 — MODE infra 5층 분기 spec

> **핵심 invariant** (1줄): `MODE` 미설정 → `cfg.MODE = "business"` polyfill → 광고대행사 기존 토픽 env / chain / 출력 분포 변동 = 0.

### 5층 표

| # | layer | 위치 | 분기 logic | 본 cycle 상태 |
|---|---|---|---|---|
| 1 | **config** | `core/config.py:236-260` (dataclass) + `core/config.py:472-490` (factory · L477 인접) | `MODE = _env_str("MODE", "business")` 읽기, `cfg.MODE` 주입 | **활성** |
| 2 | **backend select** | `agent/web_search.py:764` (vertex 진입 branch) + L820 (legacy 진입 branch) | `cfg.MODE` 따라 active backend filter (현 cycle 은 set 무변경) | **stub** (Phase 학술-2 KCI/SS API 도입 시 활성) |
| 3 | **query route** | `agent/web_search.py:733-744` (`_run_web_search_with_guard` 진입부) | catch 43 hook — lang detect + `effective_skip_vertex` reorder | **활성 (본 cycle 핵심)** |
| 4 | **prompt** | (식별 필요 — Step C 진입 직전 재탐색) | academic 모드 1줄 hint 추가 | **minimal stub** (defer 격하 가능 — 아래 STOP 논점) |
| 5 | **output** | `tools/_writer_*` / format dispatcher (미식별) | format 분기 (APA / Chicago / inline) | **defer (Phase 학술-4)** |

### Layer 1 (config) — 활성 · diff preview

**dataclass 추가** (`core/config.py:236-260` 의 RAG/검색 블록 인접):
```diff
@@ core/config.py · @dataclass Config (L236-) @@
     # RAG/검색 (네임스페이스/머지/탑K 등)
+    MODE: str                            # business (default) / academic — §academic-1
+    EXPECTED_LANG: str                   # auto | en | ko | mixed
     SEARCH_POLICY: str
     ...
     SKIP_VERTEX_SEARCH: bool
```

**factory build 추가** (`core/config.py:472-490` 의 RAG/검색 블록 시작):
```diff
@@ core/config.py · _build_config (L472-) @@
         # RAG/검색
+        MODE=_env_str("MODE", "business"),
+        EXPECTED_LANG=_env_str("EXPECTED_LANG", "auto"),
         SEARCH_POLICY=_env_str("SEARCH_POLICY", "best_of_chain"),
```
- 침습 line: dataclass **+2** / factory **+2** / 총 **+4 line** (insert only)
- invariant: env 에 `MODE` 없으면 `_env_str` default = `"business"` → 기존 토픽 cfg 변동 0

### Layer 2 (backend select) — stub

본 cycle 변경 0. `effective_skip_vertex` (catch 43 도출값) 가 L764 의 `_cfg_bool("SKIP_VERTEX_SEARCH", False)` 호출을 치환 (Step C 마이크로 변경 1 line · B2 끝 부분 참조). backend set (vertex / tavily / naver) 자체는 무변경 — Phase 학술-2 에서 KCI API 등 신규 backend 도입 시 정식 활성.

```diff
@@ agent/web_search.py:764 @@
-                if attempt == 0 and query and not _cfg_bool("SKIP_VERTEX_SEARCH", False):
+                if attempt == 0 and query and not effective_skip_vertex:
```
- 침습 line: **±1 line** (단일 변수 치환)

### Layer 3 (query route) — 활성 (B2 핵심)

B2.2-3 의 diff preview 그대로. **+8 line insert only** + 위 layer 2 의 ±1 line = catch 43 총 침습 **+9 line / -1 line / 단일 함수**.

### Layer 4 (prompt) — minimal stub (defer 가능성 검토)

- 본 cycle 의도: writer prompt 진입부에 `MODE=academic` 시 1줄 hint 추가 (예: "[학술 모드] 인용은 가능한 한 peer-reviewed 출처를 우선해 표기.")
- **위험 검토**: prompt 편집 layer 의 침습 area 가 식별 단계에서 +1 line 을 초과할 가능성 — Step C 진입 직전 재탐색 후 +3 line 초과 시 **defer 격하** (Phase 학술-4 로 이관). **B5 측정 결과 학술 source ratio 가 hint 없이도 만족 시 defer 우선 권장**.
- defer 시: B5 측정은 hint 없는 상태로 baseline 측정 — academic 모드 backend 분기 + ALLOWED_DOMAINS_EXTRA 만으로 학술 source ratio 변동 측정.

### Layer 5 (output) — defer

Phase 학술-4 territory. 본 cycle 변경 0. 진입 조건: B5 측정 후 학술 출력 형식 요구가 정량적으로 발생 시 (예: 사용자가 APA 등 형식 명시 요구).

### B4 STOP condition 검토

- Layer 2 활성 필요 case 발견? — **NO** (현 backend set 으로 catch 43 만으로 충분 · A2 add-only 29 도메인 모두 vertex / tavily / naver 중 하나로 도달 가능)
- Layer 4 침습 큼? — **검토 필요** · Step C 진입 직전 재탐색 — 본 Step 에서는 minimal stub 으로 표기, defer 격하 옵션 명시

---

## B5 — Step C A/B 측정 plan

### 측정 환경 standards (박제 정합)

- `max_retries=0`
- warmup runs = **2** (cold-start 캐시 영향 배제)
- per-run-timeout = **240s**
- inter-run-sleep = **60s** (vertex/tavily rate-limit margin)
- `PYTHONIOENCODING=utf-8` (Windows cp949 회피)
- 격리 venv:
  · `.venv_vertex` (Vertex grounding 토픽)
  · `.venv_openai` (OpenAI 토픽)
  · `.venv_anthropic` (Anthropic 토픽 · 필요 시)
- 동시 실행 금지 (single-process serial · vertex quota 보호)

### 측정 지표

| 지표 | 측정 방법 | 합격 기준 |
|---|---|---|
| **business baseline 무손상 invariant** | 기존 광고대행사 토픽 1개 — `MODE` 미설정 상태로 실행, 출력 source 도메인 분포를 §14-9 close 시점 박제와 비교 | 분포 차이 = 0 (동일 query 동일 seed) |
| **academic source ratio** | academic 토픽 실행 후 최종 출력의 `[Sources]` 섹션 도메인 중 B1 final 29 set ∩ 출현 도메인 ratio | ≥ 0.6 (60% 이상 학술 출처) |
| **catch 43 lang detect 정확도** | sample 10 query 라벨 (수동) vs `detect_query_lang` 분류 일치율 | ≥ 0.8 (8/10) · 미달 시 escalation TODO 발화 |
| **EN query → vertex_grounding 활성 비율** | `MODE=academic` + EN query 5건 실행 시 vertex 호출 비율 | 1.0 (100% · `effective_skip_vertex=False` invariant 확인) |
| **KO query → naver_direct 우선 비율** | `MODE=academic` + KO query 5건 실행 시 vertex 우회 비율 | ≥ 0.8 (4/5 · 1건은 mixed 분류 가능) |

### Sample 토픽 후보 (사용자 결정 trigger)

| 카테고리 | 후보 토픽 | 선정 trigger |
|---|---|---|
| business baseline (1개 필수) | (A) `topics/venfobel-vitamin.env` — venfobel index 가장 안정 / (B) `topics/height-growth-supplement.env` — supplement 도메인 baseline / (C) `topics/ai-generated-creative-ad-platforms.env` — EN 혼재 가능성 (lang detect 가 잘못 분류해도 invariant 유지 검증) | **사용자 결정 필요** — (C) 권장 (광고대행사 본 도메인 + EN 혼재로 catch 43 의 business 분기 invariant 동시 검증) |
| academic target — EN (1개 필수) | (D) "advertising effectiveness measurement: meta-analysis since 2015" (광고/마케팅 EN) / (E) "consumer attention metrics in digital ad platforms" | **사용자 결정 필요** — 둘 다 ad_en bucket 활용도 높음 |
| academic target — KO (1개 권장) | (F) "디지털 광고 효과성 측정 메타분석 (2015 이후)" / (G) "소비자 주의 측정 지표 in 디지털 광고 플랫폼" | **사용자 결정 필요** — KO backend 분기 검증 |
| academic target — mixed (0~1개, optional) | (H) "광고 effectiveness measurement 메타-analysis" — kor_ratio ≈ 0.4 가정 | **사용자 결정 필요** — mixed 분기 본 cycle 진입 여부 |

> 사용자 결정 trigger: 본 Step 컨펌 시 (A/B/C) 1개 + (D/E) 1개 + (F/G) 1개 + (H) 0~1개 = **3~4개 sample 확정 후 Step C 진입**.

### B5 STOP condition

- 측정 standards 적용 불가 case: venv 격리 미작동 / quota 도달 / per-run-timeout 240s 초과 빈발 → standards 재정의 (warmup runs 증가 또는 timeout 조정)
- baseline 분포 차이 > 0 (business invariant 위반) → Step C 의 catch 43 / MODE polyfill 코드 즉시 rollback
- catch 43 lang detect 정확도 < 0.7 → escalation TODO 발화 (langdetect 패키지 도입 검토 진입)

---

## Self-check protocol

- [x] step_b_design.md 6 섹션 (B0~B5) 작성
- [x] B0 결론 1~2줄 + evidence (`a2_set_diff.py:66` 필터 + 산식 검증)
- [x] B1 최종 set CSV paste-ready (29 entries) + 카운트 명시 (32 − 3 = 29) + catch 3건 (43/44/45) plan
- [x] B2 함수 pseudo-code + escalation 조건 + hook diff preview (+8 line) + MODE×lang matrix + EXPECTED_LANG override spec
- [x] B3 env template 전 field + 명명 컨벤션 (`topics/academic-<slug>.env`)
- [x] B4 5층 표 + 각 layer 활성/stub/defer 명시 + invariant 1줄 (`MODE` 미설정 → `business` polyfill)
- [x] B5 측정 spec (standards + 5 지표) + sample 후보 ≥ 2 (business 1 + academic EN 1 + KO 1 + mixed optional 1 = 3~4)
- [x] 코드 / config / env / topic 변경 0 (`git diff --stat HEAD` 빈 출력 — 본 Step 산출은 md 1개만)
- [x] 박제 chain reference (Step A 산출물 + §14-9 close + commit `902eecd`) 상단 명시

---

## STOP — Step B 자율 진입 금지

- 본 Step 산출: `scripts/output/§academic-1/step_b_design.md` (이 파일 1개)
- 코드 / config / env / topic 변경 **0** — `git diff --stat HEAD` 비어있음 (untracked 만 추가)
- commit message: `§academic-1 Step B — design (read-only)`
- 사용자 결정 필요 항목 (Step C 진입 전):
  1. **B4 layer 4 (prompt) 본 cycle 활성 여부** — minimal stub 으로 진입 vs defer 격하 (Phase 학술-4)
  2. **B5 sample 토픽 확정** — business 1 (A/B/C 중 1개, 권장: C) + academic EN 1 (D/E 중 1개) + academic KO 1 (F/G 중 1개) + mixed 0~1 (H)
  3. **Step C 진입 venv 우선순위** — `.venv_vertex` first (catch 43 핵심 검증 위주) vs `.venv_openai` first (provider 무관 invariant 검증 위주)
  4. **catch 44 / 45 README-dev catch index 신규 등록 시점** — Step C 시작과 동시 등록 vs Step C close 시 등록

**Step C 자율 진입 금지. 사용자 컨펌 대기.**
