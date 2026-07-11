# WORKBOARD — 회사 트랙 (광고·마케팅 writer)

> 🏢 회사 트랙 할일·활성 트랙·결정 기록. 운영 규칙은 ./GUARDRAILS.md, 공통은 ../CLAUDE.md.
> 상태: 골격(A안). 회사 트랙 작업 재개 시 채울 것.

---

## 지금 상태 (한 줄)
논문 트랙으로 작업 이동 중. 회사 트랙은 보류 상태 — 이 문서는 "잊지 않기 위한 자리 확보"용.

## 활성/보류 트랙
- 회사 트랙 전체 **보류 중** (논문 트랙 작업 이동). 재개 시 아래 "다음 트랙 후보"·"미결 과제"에서 승격.

## 다음 트랙 후보 (원본: README-dev-2.md "다음 트랙 후보")
- **(권고 1순위) §13-8-3** — Anthropic Haiku 4.5 평가, dual/triple track cost·latency trade-off 세분화. [README-dev-2.md]
- **(권고 2순위) 다른 토픽 일반화 검증** — pet-food-premium·height-growth 등 provider·topic-agnostic 확장. [README-dev-2.md]
- **(권고 3순위) §13-14-α-sonnet R2 prompt 패치** — Sonnet 4.6 §2 systematic 누락 양상 분석. [README-dev-2.md]

## 결정 기록 (TODO)
- (주요 의사결정을 여기에 누적)

## 미결 과제 (원본: README-dev.md §12 "알려진 후속 후보")
> 요약+포인터. 상세·가설·측정 근거는 원본 §12. 종결(`closed`)·STANDARDS 이관분은 제외.
- **메타데이터 풍부화** — `published_date`·`language` 추가로 시간 가중치/언어 필터 가능. [README-dev.md §12-1]
- **distance threshold 재튜닝 절차** — 새 토픽 시 분포 측정 후 절벽 직전 값 선택. ⚠️한계: 좁은 분포(venfobel) 토픽은 절벽 미식별 → 적용 불가. [README-dev.md §12-2]
- **Vertex grounded search 운영** — 영어 자료 위주 토픽만 `SKIP_VERTEX_SEARCH=0` override 권장(augmentation). [README-dev.md §12-3]
- **`VertexAIEmbeddings` deprecation 모니터링** — LangChain 4.0 전 마이그레이션 보류(과거 회귀 이력); 후보 (a)gemini-embedding-001 평가 (b)import만 교체 (c)warning suppress. [README-dev.md §12-4]
- **VertexAIEmbeddings lazy validation 보강** — ctor 통과하나 첫 호출 시 인증 에러 가능 → 그 시점 처리. [README-dev.md §12-5]
- **BM25 키워드 검색 보강** — 좁은 도메인+임베딩 변별 부족 토픽에서 threshold cut-off 미작동 확인 → keyword mechanism 가치 큼(우선순위 상향). [README-dev.md §12-6]
- **백업 파일 정리** — `*.bak`/`*.broken` git tracked 백업 정리 검토. [README-dev.md §12-8]
- **`CLEAR_CHROMA_ON_START` 메커니즘 개선** — 늦은 청소 문제 → app.py 시작 즉시 청소로 이전 검토. [README-dev.md §12-9]
- **ingest 큐레이션 점검** — height-growth 토픽 오염 사례(local 100%/web 40%) → `GATE_KEEP_SOURCES` 미적용 원인 점검. [README-dev.md §12-10]
- (참고) §12-11~13은 sub-track 묶음(venfobel 발견사항·cleanup 큐·라우팅 가드), §12-14~23은 대부분 `closed` → 재개 시 원본 §12에서 open 여부 재확인.

## 재진입 조건
- 회사 트랙 재개 시: 위 미결 항목 중 우선순위 선택 → 원본 §12 상세 확인 → 활성 트랙으로 승격.

## 아카이브
- README-dev.md, README-dev-2.md = 기존 기획서/보고서 에이전트 개선 기록.
- README-dev-§14.md = §14 vertex 백엔드 점검·개선 아카이브.
