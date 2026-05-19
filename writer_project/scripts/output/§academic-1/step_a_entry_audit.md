# §academic-1 Step A — Entry Audit (read-only)

## 박제 chain reference
- 직전 mission: §14-9 main close (2026-05-18, HEAD `902eecd`)
- chain 입구: `writer_project/README-dev-§14.md:294` (§14-9 close 표기)
- 직전 산출물 (§14-9 family):
  - `scripts/output/§14-9/step_a_backend_provider_matrix.md`
  - `scripts/output/§14-9-A1/credential_exposure_audit.md`
  - `scripts/output/§14-9/step_a2_fusion_and_verify.md`
  - `scripts/output/§14-9/step_b_phase2_extended_smoke.md`
  - `scripts/output/§14-9-W/step_a_whitelist_diagnosis.md`
  - `scripts/output/§14-9-W/step_b_layered_gate_design.md`
  - `scripts/output/§14-9-W/step_c_layered_gate_implementation.md`
  - `scripts/output/§14-9/step_b_phase3_metadata_persistence.md`
- 본 Step 범위: 광고대행사 시스템 → 학술 모드 통합 확장 (옵션 B) Phase 학술-1 read-only entry audit
- 변경 영역: 코드 / config / env / topic 0 (driver + 산출 .md / .json 만 신규 추가)
- driver: `scripts/§academic-1/a1_reachability.py`, `scripts/§academic-1/a2_set_diff.py`
- raw json (gitignore 대상): `scripts/output/§academic-1/a1_reachability.json`, `scripts/output/§academic-1/a2_set_diff.json`

---

## A1 — 화이트리스트 학술 도메인 reachability + 신뢰도 verify

### 방법
- DNS resolve (`socket.getaddrinfo`) + HTTPS GET (`urllib`, timeout 10s, follow redirect, User-Agent `rag-academic-audit/0.1 (read-only)`)
- HTTP 200/3xx → reachable, HTTP 4xx/5xx → 도달 자체는 성공 → reachable=True (bot 차단 응답 포함)
- DNS NXDOMAIN / TLS handshake 실패 / connect timeout → reachable=False
- 신뢰도 분류 (manual): `peer` (peer-reviewed publisher portal) · `preprint` · `aggregator` · `society` · `db_index` · `audit_only`

### 결과 요약 (n=39)
- reachable **36 / 39** · fail **3** · audit-only 2 포함
- fail breakdown:
  - `journalofadvertising.org` — DNS NXDOMAIN (저널 자체는 T&F `journalofadvertising.org` 별도 도메인 → 실제 호스팅 `tandfonline.com/loi/ujoa20`로 이전됨)
  - `earticle.net` — DNS 정상 (203.248.19.116), HTTPS SSL `CERTIFICATE_VERIFY_FAILED` (intermediate CA 누락, 서버 자체는 가동)
  - `kosac.or.kr` — DNS 정상 (119.205.197.117), HTTPS `self-signed certificate` (best-effort 추정 — 실제 한국소비자학회 공식 도메인 별도 확인 필요)
- STOP threshold "fail > 5" 미달 (3 ≤ 5) — 진행

### 표 (row 39)

| # | domain | bucket | reachable | dns | http_code | 신뢰도 | 1줄 노트 |
|---|---|---|---|---|---|---|---|
| 1 | arxiv.org | core | OK | ✓ | 200 | preprint | Cornell arXiv preprint server |
| 2 | semanticscholar.org | core | OK | ✓ | 200 | db_index | Allen AI semantic search index |
| 3 | openalex.org | core | OK | ✓ | 200 | db_index | OpenAlex open scholarly graph |
| 4 | jstor.org | core | OK | ✓ | 200 | aggregator | ITHAKA JSTOR 다분야 아카이브 |
| 5 | springer.com | core | OK | ✓ | 200 | peer | Springer Nature root |
| 6 | link.springer.com | core | OK | ✓ | 200 | peer | Springer 저널 portal |
| 7 | wiley.com | core | OK | ✓ | 200 | peer | Wiley root |
| 8 | onlinelibrary.wiley.com | core | OK | ✓ | 403 | peer | Wiley Online Library (bot 차단 응답이나 도달) |
| 9 | plos.org | core | OK | ✓ | 200 | peer | PLOS open-access |
| 10 | science.org | core | OK | ✓ | 403 | peer | AAAS Science (bot 차단 응답이나 도달) |
| 11 | pmc.ncbi.nlm.nih.gov | core | OK | ✓ | 200 | aggregator | NIH PubMed Central |
| 12 | sagepub.com | core | OK | ✓ | 200 | peer | SAGE root |
| 13 | journals.sagepub.com | core | OK | ✓ | 403 | peer | SAGE 저널 portal (bot 차단) |
| 14 | tandfonline.com | core | OK | ✓ | 403 | peer | Taylor & Francis Online (bot 차단) |
| 15 | doaj.org | core | OK | ✓ | 200 | db_index | Directory of Open Access Journals |
| 16 | nature.com | core | OK | ✓ | 200 | peer | Nature Portfolio |
| 17 | ssrn.com | core | OK | ✓ | 403 | preprint | SSRN preprint network (bot 차단) |
| 18 | papers.ssrn.com | core | OK | ✓ | 403 | preprint | SSRN paper subdomain (bot 차단) |
| 19 | emerald.com | core | OK | ✓ | 403 | peer | Emerald Publishing (bot 차단) |
| 20 | ama.org | ad_en | OK | ✓ | 200 | society | American Marketing Association |
| 21 | journalofadvertising.org | ad_en | **FAIL** | ✗ | gaierror | peer | DNS NXDOMAIN — 실저널 `tandfonline.com/loi/ujoa20`로 이전 (#14 대체 가능) |
| 22 | warc.com | ad_en | OK | ✓ | 200 | db_index | WARC marketing knowledge base (paywall) |
| 23 | msi.org | ad_en | OK | ✓ | 200 | society | Marketing Science Institute |
| 24 | pubsonline.informs.org | ad_en | OK | ✓ | 403 | peer | INFORMS journals · Marketing Science 포함 |
| 25 | academic.oup.com | ad_en | OK | ✓ | 403 | peer | Oxford Academic · JCR/JoC 등 포함 |
| 26 | mmaglobal.com | ad_en | OK | ✓ | 200 | society | Mobile Marketing Association |
| 27 | iab.com | ad_en | OK | ✓ | 200 | society | Interactive Advertising Bureau (이미 .env 포함) |
| 28 | kci.go.kr | kr_db | OK | ✓ | 200 | db_index | 한국연구재단 KCI |
| 29 | riss.kr | kr_db | OK | ✓ | 200 | db_index | KERIS RISS 학술정보 |
| 30 | dbpia.co.kr | kr_db | OK | ✓ | 200 | aggregator | DBpia |
| 31 | kiss.kstudy.com | kr_db | OK | ✓ | 200 | aggregator | KISS 한국학술정보 |
| 32 | earticle.net | kr_db | **FAIL** | ✓ (203.248.19.116) | ssl_verify_fail | aggregator | SSL intermediate CA 누락 — 서버 가동 중, RAG 진입 시 verify 우회 정책 검토 필요 |
| 33 | kadpr.or.kr | kr_soc | OK | ✓ | 200 | society | 한국광고홍보학회 (KADPR) — 확정 |
| 34 | koads.or.kr | kr_soc | OK | ✓ | 200 | society | best-effort — 한국광고학회 공식 여부 추후 audit |
| 35 | kma.or.kr | kr_soc | OK | ✓ | 200 | society | 한국마케팅협회로 추정 (학회 아닐 가능성) — 추후 audit |
| 36 | kosac.or.kr | kr_soc | **FAIL** | ✓ (119.205.197.117) | ssl_self_signed | society | self-signed cert · 실제 한국소비자학회 도메인 추후 audit |
| 37 | kabs.or.kr | kr_soc | OK | ✓ | 200 | society | best-effort — 한국방송학회 공식 여부 추후 audit |
| 38 | researchgate.net | audit_only | OK | ✓ | 403 | audit_only | 사용자 업로드 비-peer-reviewed 多 · default 제외 |
| 39 | academia.edu | audit_only | OK | ✓ | 200 | audit_only | 사용자 업로드 비-peer-reviewed 多 · default 제외 |

raw: `scripts/output/§academic-1/a1_reachability.json`

---

## A2 — 기존 ALLOWED_DOMAINS vs 신규 후보 매트릭스

### 코드 내 list 정의 위치
| source | path | line | count | mechanics |
|---|---|---|---|---|
| 1차 source (env) | `writer_project/.env` | L213 | **78** | `ALLOWED_DOMAINS=` CSV (KR 의약 + 학술 + 광고/마케팅 혼재) |
| 2차 source (hardcoded base) | `writer_project/settings_gatekeep.py` | L45–L66 | **17** | `_BASE_ALLOWED_DOMAINS: tuple[str, ...]` — 공공 9 + 의약 8 |
| 해석 함수 | `writer_project/settings_gatekeep.py` | L138–L155 `get_allowed_domains()` | union | 런타임 주입 > CFG > BASE ∪ ENV `ALLOWED_DOMAINS` ∪ ENV `ALLOWED_DOMAINS_EXTRA` |
| CFG 등록 | `writer_project/core/config.py` | L507 | — | `ALLOWED_DOMAINS=_split_csv_set(_env_str("ALLOWED_DOMAINS", ""))` |
| 정규화 사이트 | `writer_project/agent/web_search.py` | L416–L441 | — | `_normalize_domains(get_allowed_domains())` 호출 |

존재하는 총합: **79개 union** (.env 78 + BASE 17 − overlap 16 = 79). README-dev `§14-9-W Step B` 표기 "base 78" 은 .env 의 78 (KR 의약 58 + EN 학술 11 + 광고/마케팅 9) 을 가리킨다.

### A1 reachable 통과 set 연산 (audit_only 2 / fail 3 제외, n=34)

#### (1) 중복 set — 이미 포함 (2)
| domain | bucket | 출처 | 노트 |
|---|---|---|---|
| nature.com | core | ENV (.env:213) | §14-9-W Step C 패치로 .env 에 이미 추가됨 |
| iab.com | ad_en | ENV (.env:213) | §14-9-W Step C 패치로 .env 에 이미 추가됨 |

→ 충돌 아님 (단순 set membership 중복) · 본 사이클에서 추가 작업 없음

#### (2) 추가 only set — 신규 (32)
| bucket | domain |
|---|---|
| core (18) | arxiv.org, semanticscholar.org, openalex.org, jstor.org, springer.com, link.springer.com, wiley.com, onlinelibrary.wiley.com, plos.org, science.org, pmc.ncbi.nlm.nih.gov, sagepub.com, journals.sagepub.com, tandfonline.com, doaj.org, ssrn.com, papers.ssrn.com, emerald.com |
| ad_en (6) | ama.org, warc.com, msi.org, pubsonline.informs.org, academic.oup.com, mmaglobal.com |
| kr_db (4) | kci.go.kr, riss.kr, dbpia.co.kr, kiss.kstudy.com |
| kr_soc (4) | kadpr.or.kr, koads.or.kr, kma.or.kr, kabs.or.kr |

(합 18 + 6 + 4 + 4 = 32 일치. sagepub.com / journals.sagepub.com 및 ssrn.com / papers.ssrn.com 은 root·subdomain 모두 화이트리스트화 — `_normalize_host` (settings_gatekeep.py) 가 분리 정규화하므로 별도 entry 필요)

#### (3) 충돌 case (0)
- A1 reachable 34 중 기존 ALLOWED_DOMAINS 79 와 set 충돌 없음 (의약 우선순위 vs 학술 우선순위 분기 codepath 부재 — 모두 단일 union)
- STOP threshold "충돌 > 3" 미달 (0 ≤ 3) — 진행
- 다만 학술 모드 진입 시 의약 도메인 weighting 이 cross-domain 잡음으로 작용할 가능성은 별 cycle 검토 사안 (본 audit 범위 아님)

### 합집합 검증 (self-check)
- overlap (2) ∪ add-only (32) ∪ audit-only 분류 노트 (2) ∪ fail (3) ∪ kr_db sagepub root 와 subdomain 표기 중복 정리 = A1 reachable 36 (excl. fail) + fail 3 = 39 → A1 전체 도메인 set 와 일치

raw: `scripts/output/§academic-1/a2_set_diff.json`

---

## A3 — catch 43 hook point inspection

### 4 hook point 명세

| # | 역할 | file | function | line | 비고 |
|---|---|---|---|---|---|
| 1 | **query chain entry** (LangGraph node) | `writer_project/agent/web_search.py` | `web_search_agent(state)` | **L171** | state.flags.qa_direct_reply skip → llm planner → forced queries → `_run_web_search_with_guard(q)` 반복 호출 (L1100/1137/1170/1212) |
| 2 | **backend selection logic** (per-query Vertex-first) | `writer_project/agent/web_search.py` | `_run_web_search_with_guard(q)` inner | **L764** | `if attempt == 0 and query and not _cfg_bool("SKIP_VERTEX_SEARCH", False):` — Vertex 우선, legacy multi-engine (L821) 항상 fallback |
| 3a | **SKIP_VERTEX_SEARCH env layer (reader)** | `writer_project/agent/web_search.py` | `_cfg_bool` | **L92** | `_get_cfg_attr` (L55–L67) 경유 config.CFG → config → default |
| 3b | **SKIP_VERTEX_SEARCH env layer (config build)** | `writer_project/core/config.py` | `make_config()` body | **L477** | `SKIP_VERTEX_SEARCH=_env_flag("SKIP_VERTEX_SEARCH", False)` — `_env_flag` (L29) 가 `os.getenv` 직독 |
| 4 | **catch 43 hook 후보 (lang detect + backend reorder)** | `writer_project/agent/web_search.py` | `_run_web_search_with_guard(q)` body 진입부 | **L733–L744 (after `norm_q` 결정, before `for attempt in range(retries + 1):` 루프)** | per-query lang heuristic → 학술 모드 + EN query 시 SKIP_VERTEX_SEARCH 일시 override / backend 순서 재배치. 침습 면적 최소 (한 함수 내부 5–10 line 추가) |

### 침습 area 평가
- 후보 A (L733–L744 hook · 권장): per-query 결정, 함수 내부 캡슐화, 외부 호출자 무변경. 신호: `_cfg_bool` 호출 대신 local override flag (e.g. `effective_skip_vertex = _cfg_bool(...) or _academic_en_override(query, state)`) 한 줄.
- 후보 B (L171 web_search_agent 입구 hook): agent-wide, mission/state 기반 academic flag 1회 결정. 단점 — 모든 query 일괄 적용이라 KR/EN 혼재 한 토픽에서 grain 부족.
- 후보 C (L764 condition 자체 수정): 가장 깊은 위치, side-effect 분리도 낮음. 비추천 — race condition / 향후 backend 추가 시 cascade 수정 부담.

**권장: 후보 A.** chain entry (L171) 와 backend selection (L764) 사이의 단일 함수 (`_run_web_search_with_guard`) 내부에서 결정 → 호출자/config 양쪽 모두 무변경.

---

## A4 — MODE env backward-compat 영향 면적

### 현재 토픽 env 파일 list (5)
| path | MODE 라인 존재? |
|---|---|
| `writer_project/topics/_template.env` | ✗ |
| `writer_project/topics/height-growth-supplement.env` | ✗ |
| `writer_project/topics/pet-food-premium.env` | ✗ |
| `writer_project/topics/venfobel-vitamin.env` | ✗ |
| `writer_project/topics/ai-generated-creative-ad-platforms.env` | ✗ |

### 영향 받는 코드 분기 후보 (env load 지점 + cfg 객체)
| layer | path | line / symbol | MODE 도입 시 영향 |
|---|---|---|---|
| ENV 로드 1단계 (global) | `writer_project/core/config.py` | L153–L169 `_load_dotenv_once` | global `.env` 로드 직후 MODE 미설정이면 default 적용 가능 — 단, 1단계 후 provider/topic overlay 가 덮어쓰므로 단독 invariant 점은 아님 |
| ENV 로드 2단계 (provider overlay) | `writer_project/core/config.py` | L106–L127 `_apply_provider_overlay` | `.env.vertex` / `.env.openai` / `.env.anthropic` 에 MODE 없음 (검증 완료) → overlay 가 MODE 를 덮지 않음 |
| ENV 로드 3단계 (topic overlay, 최후승) | `writer_project/core/config.py` | L130–L150 `_apply_topic_preset` | 5 topic env 모두 MODE 없음 (검증 완료) → topic overlay 도 덮지 않음 |
| **Config build (★ invariant 유지 후보)** | `writer_project/core/config.py` | **L472–L490 RAG/검색 블록 (e.g. L477 SKIP_VERTEX_SEARCH 인근에 한 줄 추가)** | `MODE=_env_str("MODE", "business")` + whitelist `{"business","academic"}` validation (잘못된 값 → "business" fallback) → CFG.MODE 단일 source of truth |
| Config dataclass 선언 | `writer_project/core/config.py` | L236– (Config 본체) | `MODE: str` 한 줄 추가 |
| 동적 reader | `writer_project/agent/web_search.py` | L92 `_cfg_bool` / 신규 `_cfg_str` (필요 시) | `_get_cfg_attr("MODE", "business")` 호출로 catch 43 hook 등 소비처에서 일관 read |

### 광고대행사 기존 토픽 env 무변경 작동 보장
- 9 env 파일 (global + 3 provider overlay + 5 topic) 중 MODE 라인 0건 → load 3 stage 어디서도 MODE 가 set 되지 않음
- L477 인근 신규 `MODE=_env_str("MODE", "business")` 가 유일한 source → 미설정 시 항상 "business" 보장
- 학술 모드 진입은 `MODE=academic` 을 topic env 한 줄 추가 (e.g. `topics/academic-thesis.env`) 로만 활성 → 기존 4 토픽 우회

### invariant 유지 후보 — 1개 (단일 진입점)
- **권장: `core/config.py:472–490` RAG/검색 블록 내, 가급적 L477 `SKIP_VERTEX_SEARCH` 인접에 `MODE` 한 줄 신설.** 이유:
  1. Config build 함수는 reload_config_inplace (L663–L700) 가 dotenv 재로드 후 한 번 호출하는 단일 site
  2. provider/topic overlay 적용 *이후* 평가되므로 우선순위 모순 없음
  3. CFG.MODE 가 글로벌 진실 source — 모든 소비처는 _get_cfg_attr 경유 → 다단계 분기 불필요

### STOP threshold 평가
- backward-compat 영향 면적: env load 3 stage 모두 영향 0건 (현존 9 env 파일 무변경)
- invariant 유지 후보: 1개 명시 (config.py:477 인접)
- STOP 조건 "광범위 / 후보 0개" 미해당 — 진행

---

## Self-check protocol
- [x] step_a_entry_audit.md 4 섹션 작성 완료
- [x] A1 표 row 수 = 39 (≥ 35, researchgate/academia 포함)
- [x] A2 set 합집합 = overlap (2) + add-only (32) + audit-only (2) + fail (3) = 39, A1 reachable 34 + audit-only 2 + fail 3 = 39 일치
- [x] A3 4개 hook point 모두 file path + 라인 ref 명시 (L171 · L764 · L92/L477 · L733–L744)
- [x] A4 invariant 유지 후보 1개 명시 (config.py:472–490 RAG/검색 블록, L477 인접)
- [x] 코드 / config / env / topic 변경 0 — `git diff --stat HEAD` empty 확인 (HEAD `902eecd`)
- [x] 박제 chain reference 본 .md 상단 명시 (§14-9 close + 8 산출물 list)

## STOP — Step A 완료 후 자동 진행 금지
Self-check 통과 + commit ready. **Step B 자율 진입 금지.** 사용자 컨펌 대기.

### 사용자 결정 필요 항목
1. A1 fail 3건 (`journalofadvertising.org` / `earticle.net` / `kosac.or.kr`) 처리 정책 — 제외? 대체? SSL 우회?
2. kr_soc bucket 4 best-effort 도메인 (`koads.or.kr` / `kma.or.kr` / `kosac.or.kr` / `kabs.or.kr`) 추후 audit cycle 별도 진입?
3. A2 add-only 32 도입 layer — 즉시 `.env:213 ALLOWED_DOMAINS` 확장? 아니면 MODE 분기 후 `ALLOWED_DOMAINS_EXTRA` 동적 주입?
4. A3 hook 후보 A (L733–L744) 채택 여부 — 또는 B/C 재검토?
5. A4 MODE field 도입 위치 (config.py:477 인접) 확정 여부 + 학술 모드 진입 토픽 env 명명 (`academic-*.env`?)
