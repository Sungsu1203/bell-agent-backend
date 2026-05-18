# Topic env 운영 가이드

본 가이드는 `topics/<slug>.env` 작성 시 사용 가능한 env 변수와 권장 패턴을 정리한다. 글로벌 `.env` 와 provider overlay (`.env.<provider>`) 뒤에 `override=True` 로 로드된다 (load 순서: 글로벌 → provider overlay → topic).

§14-9-W Step C (2026-05-18) 의 β layered + γ toggle 구현에 대응하는 패턴을 포함한다.

────────────────────────────────────────────────

## 1. 토픽 식별 + 리서치 목표

| 변수 | 용도 |
|---|---|
| `TOPIC_TITLE` | 보고서 제목 (사용자 표시) |
| `TOPIC_KEYWORDS` | 콤마 분리 토픽 키워드 (검색 query 보강에 사용) |
| `TOPIC_SLUG` | 인덱스 namespace / report path / 토픽 env 선택 키 |
| `BLOCKAGI_OBJECTIVE_1` ~ `_5` | 토픽별 리서치 OBJ 5개 (researcher / writer prompt 에 주입) |

예시는 `topics/venfobel-vitamin.env` 참조.

────────────────────────────────────────────────

## 2. β — ALLOWED_DOMAINS_EXTRA (per-topic 화이트리스트 확장)

글로벌 `.env:213` 의 base 78 도메인 외에 토픽-한정 도메인을 추가할 때 사용한다. **글로벌 base 는 그대로 유지** — `os.getenv("ALLOWED_DOMAINS_EXTRA", "")` 와 set union 으로 병합 (`settings_gatekeep.py:154`).

### 2-a. 기본 형식

```sh
# topics/<slug>.env 의 한 줄 (comma-separated)
ALLOWED_DOMAINS_EXTRA=domain1.com,domain2.kr,sub.example.org
```

### 2-b. 운영 예시

#### 광고-AI 교차 토픽 (`ai-generated-creative-ad-platforms`)

```sh
# AI/tech 매체를 base 78 외에 토픽 한정 추가
ALLOWED_DOMAINS_EXTRA=techcrunch.com,theverge.com,wired.com,venturebeat.com,marketingdive.com
```

#### EN 학술 심화 토픽 (글로벌 base 의 EN 학술 10개 외 publisher 분산 필요)

```sh
# Elsevier / Springer / Wiley 등 publisher 직접 추가
ALLOWED_DOMAINS_EXTRA=tandfonline.com,wiley.com,springer.com,cell.com,lancet.com,mdpi.com
```

### 2-c. backward compatibility

`ALLOWED_DOMAINS_EXTRA` 미설정 시 빈 set union → 글로벌 base 78 만 적용. 기존 토픽 영향 0.

### 2-d. 서브도메인 자동 매칭 (ALLOW_SUBDOMAINS=1, `.env:208`)

- `nih.gov` base 등록 시 자동 매칭: `nhlbi.nih.gov`, `niddk.nih.gov`, `pubmed.ncbi.nlm.nih.gov` 등 산하 전부
- `*.example.com` 같은 와일드카드 syntax 는 미지원 — base 도메인 1개만 등록하면 ALLOW_SUBDOMAINS suffix loop 가 처리 (`settings_gatekeep.py:363-377`)

────────────────────────────────────────────────

## 3. γ — GATE_KEEP_SOURCES opt-out (per-topic gate 무력화)

글로벌 `.env:207` 의 `GATE_KEEP_SOURCES=1` (gate active) 를 토픽에서 override 하여 gate 를 무력화한다. **단발성 explore 토픽 / EN 학술 base 외 도메인 광범 활용 토픽** 에 한정 권장.

### 3-a. 기본 형식

```sh
# topics/<slug>.env 의 한 줄
GATE_KEEP_SOURCES=0
```

### 3-b. 운영 예시

```sh
# topics/_one-shot-academic-explore.env
TOPIC_TITLE=2026 학술 동향 1-shot 탐색
TOPIC_KEYWORDS=academic,exploration
TOPIC_SLUG=_one-shot-academic-explore

# ────── §14-9-W γ toggle opt-out (2026-05-18) ──────
# 본 토픽은 base 78 외 학술 publisher 분산 활용 필요 →
# gate off + URL-level fallback (dedup / HTTP probe / intermediate news / rerank) 위주.
GATE_KEEP_SOURCES=0
```

### 3-c. ⚠ γ off 시 risk 경고 (Step B § 3-b Finding C 정합)

> **γ off 시 fallback quality = URL-level 만**. content-quality 평가 부재. forum / 저품질 blog / off-topic page noise 유입 risk 있음.
>
> 적용 권장 영역:
> - ✓ 단발성 explore 토픽 (1-shot research, 폐기 가능)
> - ✓ EN 학술 base 외 publisher 분산 필요 토픽
> - ✗ NDA-bound 운영 토픽 (예: venfobel-vitamin) — 적용 신중
> - ✗ 장기 운영 토픽 default — `README-dev.md:556` 정합 (GATE_KEEP_SOURCES=1 명시 의무화)

### 3-d. fallback quality 신호 (gate off 시 작동)

| 신호 | 위치 | 한계 |
|---|---|---|
| dedup | `tools/web_rag/search.py:1825` `_canon_and_dedupe` | URL-level 만 |
| HTTP probe | `tools/web_rag/search.py:1854` `_filter_non_2xx` | HTTP status 200 SEO spam 통과 |
| intermediate news block | `tools/web_rag/search.py:1856` | aggregator redirect 만 |
| 권위/잡음 rerank | `agent/web_search.py:914-963` | 순서만 — quality 평가 아님 |
| YEAR_FLOOR | (search.py) | 시간 기반 (2019 미만 컷) |

content-quality filter (language / length / readability / LLM-scorer) 는 미구현 — catch 38~42 후보 (별 cycle).

────────────────────────────────────────────────

## 4. 기타 토픽-한정 override 가능 변수

| 변수 | 기본값 (.env) | 토픽-한정 override 사례 |
|---|---|---|
| `ALLOW_SUBDOMAINS` | 1 | 0 으로 strict mode 운영 시 |
| `URL_TREAT_WWW_EQUIV` | 1 | 0 으로 강도 운영 시 |
| `MERGE_RETRIEVE_MODE` | `local_first` / `web_first` | 토픽 RAG mix 정책 |
| `RETRIEVE_WEB_RATIO` | 0.67 (web_first) / 0.33 (local_first) | 토픽 분포 특성 정합 |
| `RAG_TOP_K` | 6 | 청크 분포 다양성 필요 시 10 (venfobel 정합) |
| `SKIP_VERTEX_SEARCH` | 0 | vertex 429 quota / metadata 휘발 시 1 (§14-1) |

가능 변수의 정합 검증은 코드 (`core/config.py` 의 `_env_*` 헬퍼) 기준. 새 변수 추가 시 본 가이드 update 권장.

────────────────────────────────────────────────

## 5. cache invalidation (Gap 2 fix)

- `settings_gatekeep._normalized_allowed_domains` 는 `@lru_cache(maxsize=1)` — env 변경 후 명시 무효화 필요.
- §14-9-W Step C (2026-05-18) 의 `core/config.py:684` 직후 `refresh_gatekeep_cache()` 호출로 `reload_config_inplace()` 의 모든 진입 경로에서 자동 갱신 보장.
- 추가 진입점 (예: pytest fixture, 외부 script) 에서 env 수정 시 `settings_gatekeep.refresh_gatekeep_cache()` 명시 호출 권장.

────────────────────────────────────────────────

## 6. precedent cross-ref

- §14-9-W Step A — gate mechanics + ALLOW_SUBDOMAINS 검증 (`scripts/output/§14-9-W/step_a_whitelist_diagnosis.md`)
- §14-9-W Step B — β layered + γ toggle 설계 (`scripts/output/§14-9-W/step_b_layered_gate_design.md`)
- §14-9-W Step C — 본 가이드 + .env 확장 + refresh hook (`scripts/output/§14-9-W/step_c_layered_gate_implementation.md`)
- §12-19 — per-topic env override 패턴 (precedent)
- README-dev.md:555-556 — height-growth-supplement 100% 오염 사례 (γ off 적용 신중 사유)
