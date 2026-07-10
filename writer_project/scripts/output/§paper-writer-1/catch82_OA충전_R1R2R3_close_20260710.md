# catch 82 — OA venue 단일경로 드롭 → type-aware locations[] fallback (R1·R2·R3 close)

**날짜**: 2026-07-10 · **status**: closed · **결과**: venue 결손 5→0, axis1 0.944 WARN → 1.0 PASS

---

## 증상 / 원인 (R1 확정)

OA(OpenAlex) backend 참조 60건 중 7건 venue=None. `tools/web_rag/openalex.py:157-159`가
venue를 **`primary_location.source.display_name` 단일경로**로만 읽음. OA는 법학·preprint 논문의
`primary_location`을 흔히 **리포지토리 사본**(source=None 또는 type=repository)에 걸어두므로,
저널이 `locations[]` 뒤칸에 구조화되어 있어도 통째 드롭.

**반증 박제**: "blanket host_venue 오독"(구 스키마 통짜 읽기) 가설 **폐기** — 코드는 이미 신 스키마
(`primary_location.source`)를 읽고 있었다. 실제 기제 = **신 스키마의 잘못된 단일 위치**(primary만,
locations[] 미순회). 60건 전부 None이 아니라 7건만 결손인 점이 blanket 오독을 배제.

### R1 X/Y 판정 (OA 원 응답 실물 대조, 무료 공개 API)
| work (year) | primary.source | 실제 OA 보유 | 판정 |
|---|---|---|---|
| Confusion Over Use (2007) ×3 | null | loc[].source='Iowa law review'(구조화) | **Y**(파이프라인 드롭) |
| Testing for Dilution / Beebe (2019) | null | loc[].source='The University of Chicago Law Review' | **Y** |
| Trademark retrieval phonetic / IEEE (2014) | null | raw_source_name='2014 IEEE Int'l Conf SMC'(source null) | X-cheap(raw만) |
| Online Dispute Resolution / Cortés (2010) | null | type=book, 저널 source 없음 | X-book(None 정상) |
| 상표의 유사 여부 / 윤선희 (2005) | null | source·raw 전무(KCI, OA 완전결손) | X-hard |

지뢰: host_venue → primary_location.source 스키마 마이그레이션 확인. source.type 전 코퍼스 =
`repository`/`journal` 2종뿐(`conference` 0건 → IEEE 학회가 raw로만 생존한 이유).

---

## 설계 (R2 safe-core, 오프라인 검증 60 chunk / garbage 0)

`_extract_venue(work)` 4단 fallback:
1. `primary_location.source.display_name` — type이 리포 계열(`{repository, ebook platform}`)이 **아닐 때만**
2. `locations[]` 전체 순회(인덱스 무가정) → 리포 계열 아닌 첫 구조화 source
3. 없으면 `primary_location.source` 리포명이라도 보존 (arXiv/SSRN = 기존 동작, **regression 0**)
4. 그것도 없으면 None (책·진짜 결손)

**★raw_source_name 폴백 미채택**: 오프라인 전수 검증서 garbage 다수 —
filename(`9781136943508.pdf`), vol번호(`40`), vendor-id(`MODID-943f…:Taylor &amp; Francis`),
citation-dump(`Senftleben, M R F 2009, '…', vol.40, no.1, pp.45-77`). 일반 guard로
IEEE clean 문자열과 분리 불가 → 폐기하고 3건 수동 override로 처리.

**블랙리스트 선택 근거**: 화이트리스트(journal/conference만 허용)는 예상외 type에서 회귀 위험.
블랙리스트(repo 계열만 스킵)가 안전. 전 코퍼스 실측 type 2종(repository/journal)으로 커버 확인.

### R2 검수표 요약
- 파트 A(safe-core 변화): 7 unique work / 25 chunk = repo→journal 교정 21 + None→journal 회수 4.
  전부 실게재지 일치(Michigan/Fordham IP/Texas/Iowa/Indiana/Chicago LR). 엉뚱한 저널 0.
- 파트 B(보존건 11): **structured 저널숨음 0**(safe-core가 놓친 구조화 저널 없음). raw에만 실저널
  생존 4건(Cardozo·IEEE·IIC·SemEval) = override/미회수 판단 근거. arXiv 프리프린트 = 표시 유지.

---

## 수동 override 3건 (safe-core 미회수분)

`agent/web_search.py` `_VENUE_OVERRIDES` — (title+year) 매칭으로 **기존 chunk venue 필드 채움만**
(신규 참조 생성 0, denominator 불변). `paper_section_fetch` 출구 1지점 호출.

| work | override venue | 근거 |
|---|---|---|
| Trademark retrieval phonetic (2014, Anuar) | `2014 IEEE International Conference on Systems, Man, and Cybernetics (SMC)` | OA raw_source_name clean 생존 |
| Initial Interest Confusion (2005, Rothman) | `Cardozo Law Review` | OA raw + 실게재지(vol.27) 확인 |
| 상표의 유사 여부 판단… (2005, 윤선희) | `인권과 정의` | **KCI** arti_id ART001008024 직접 확인(대한변협 제347호, pp.99-121) |

---

## 실측 (R3 유료 통제런, 2026-07-10, exit 0, vertex off)

### DRY 오라클 (캐시 기반, 유료 0) — 유료런 전 게이트
chunk 60→60(신규 ref 0), override 5 chunk, garbage 0, target 5 work 전건 일치. → 유료런 진입.

### 유료런 결과
- **axis1_apa**: 결손 5→**0**, pass_ratio 0.944→**1.0 PASS** (complete 44 / partial 45 / missing 0).
- **axis2_imrd**: PASS 5섹션 전부 **무이동**.
- **axis3_pipeline_health**: 학술 100%(89/89), `vertex_web=0`·`vertex_academic=0` **무이동**.
- override 5 chunk 착지 = dry 오라클 일치(IEEE×1 / Cardozo×3 / 인권과 정의×1). venue garbage 0.
- **단일변수 통제**: references 89 불변(backend openalex 60 + semantic_scholar 29 = R1 baseline 동일).
- partial 45 잔존 = doi 결손(39) 무접촉 탓(정상). Cortés(책) venue-None 정상(DOI 보유 → partial 등급).

---

## 정정 박제
- **baseline 정정**: "77"(catch 78 vertex-off 직후)은 stale. catch 74 SS 복구로 현 baseline **89**(OA60+SS29).
- **라인 정정**: 토픽 .env(academic-trademark-similarity-consumer.env) SKIP_VERTEX_SEARCH 값 = **:22**
  (:21은 주석 `# catch 78 …`). off-by-one 실파일 기준 정정.

## known divergence / 별 트랙 (미착수, 기록만)
- 윤선희 계열 **KCI 커버리지**: OA 완전결손. KCI 백엔드는 1건 위한 과투자 → 수동 override 처리, 백엔드 미착수.
- IEEE SMC·Cardozo: raw_source_name에만 생존(clean)이나 자동 파싱 garbage 위험 → 수동 override 채택.
- **doi 결손 39건**: 별 트랙(venue와 기제 상이).
- catch 80 "venue 부정합/predatory"(품질 축) 잔존.

---

**변경 파일 (단일 커밋, measurement JSON·output 논문 제외)**:
`tools/web_rag/openalex.py`, `agent/web_search.py`, 본 close .md, `README-dev-§14.md`(catch 82 엔트리).
