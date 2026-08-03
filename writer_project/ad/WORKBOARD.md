# WORKBOARD — 회사 트랙 (광고·마케팅 writer)

> 🏢 회사 트랙 할일·활성 트랙·결정 기록. 운영 규칙은 ./GUARDRAILS.md, 공통은 ../CLAUDE.md.

---

## 지금 상태 (한 줄)
**§ad-track-1 활성.** 체험마케팅 15주 강의 E열(사례) 자동 확보 파이프라인 구축 중. 계단 3-d-1 진행.

## 활성 트랙

### §ad-track-1 — 체험마케팅과 미디어 콘텐츠 (홍익대 대학원 15주)
- **시작** 2026-07-30 / **토픽** `topics/experiential-marketing-media.env`
- **목표** 15주 설계표 E열 14칸을 **브랜드 + 캠페인 + 연도 + URL** 4요소로 채운다
- **현재** 계단 3-d-1 (①②③ 완료 / ④⑤⑥⑦⑧ 이월)
- **누적 비용** ≈ $0.25

| 계단 | 결과 |
|---|---|
| 0~2 | 환경·인덱스 구축. `-local` 302청크 / `-web` 416청크 |
| 3-a | 웹 수집 4주차(04·07·13·15). catch J~AA |
| 3-b | LLM arm 리포트 경로. **실패** — 브랜드 27회 참조에 본문 0회(catch AN), 연도 0건. $0.12 |
| 3-c | **arm Z(비-LLM) PASS.** `retrieve` → 청크 원문 + `metadata.source` 직결. 3요소 5건. $0 |
| 3-d-1 | ①git ②커밋 ③catch AT 종결. 코드 변경 0건 |

- **박제** `scripts/output/§ad-track-1/step3{a,b,c}_close_§ad-track-1.md`
- **도구** `probe_Z_extract.py`(arm Z 드라이버) · `probe_dist_adtrack.py`(거리 분포) · `scan_local_coverage.py`

## 결정 기록

| 일자 | 결정 | 근거 |
|---|---|---|
| 08-02 | **추출 경로 = arm Z (비-LLM)** | 목표물이 원문에 있으면 추출이 생성보다 낫다. LLM은 브랜드·연도를 깎는다(catch AN) |
| 08-03 | **`RAG_DISTANCE_THRESHOLD` 조정하지 않음** | 1.10에서 04·13은 100% 통과. 상향하면 04·13 최악(0.98)보다 먼 자료가 섞인다 |
| 08-03 | **NS별 임계 분기 도입하지 않음** | local 5.6% 통과는 정상 작동. 1.10~1.25 구간에 E열용 사례 없음. `ingest_vector.py`는 두 트랙 공유 |
| 08-03 | **07·15주 재수집 필요 확정** | 04·13 최대값 ≤ 07·15 최소값. 임계가 아니라 자료 이격 |
| 08-03 | 논문 트랙 미커밋분 **A안**(개별 add 유지) | stash 분실 위험(B) · 남의 트랙 커밋 월권(C) 기각 |

## 다음 (3-d-1 잔여 — 전부 $0)

| | 단계 |
|---|---|
| ④ | 게이트 위치 정찰 → catch P 재판정 |
| ⑤ | `published_date` 추출률 실측 → 구현 + diff STOP |
| ⑥ | arm Z 소스 그룹핑 개선 (catch AV 대응) |
| ⑦ | 목록 토큰 A/B 검색 dry-run → 10주 쿼리 확정 |
| ⑧ | 준확정 3건 URL 확인 → 승격 |

**3-d-2 (유료)**: ⑨-a aimatters 목록 4페이지 / ⑨-b 10주 신규 / ⑨-c 07·15 재수집(쿼리 변형 동반)

## 보류 트랙 (재개 시 승격)
- **§13-8-3** Haiku 4.5 평가, dual/triple track cost·latency 세분화 [README-dev-2.md]
- **다른 토픽 일반화 검증** pet-food-premium·height-growth 등 [README-dev-2.md]
- **§13-14-α-sonnet R2 prompt 패치** [README-dev-2.md]

## 미결 과제 (원본: README-dev.md §12)
> 요약+포인터. 상세는 원본 §12. 종결·STANDARDS 이관분 제외.

- **메타데이터 풍부화** — `published_date`·`language` 추가. [§12-1] ⚠️ **§ad-track-1 catch AY와 동일 항목.** 3-d-1 ⑤에서 착수
- **distance threshold 재튜닝 절차** [§12-2] ⚠️ **체험마케팅 토픽도 절벽 부재형**(2026-08-03 실측, 인접 최대 점프 +0.11). venfobel과 동일하게 본 절차 적용 불가
- **BM25 키워드 검색 보강** [§12-6] — 좁은 분포 토픽의 대안 mechanism. §12-2 불가 판정이 반복되어 **우선순위 유지**
- **Vertex grounded search 운영** — 영어 자료 토픽만 `SKIP_VERTEX_SEARCH=0` [§12-3]
- **`VertexAIEmbeddings` deprecation 모니터링** [§12-4] / **lazy validation 보강** [§12-5]
- **백업 파일 정리** [§12-8] / **`CLEAR_CHROMA_ON_START` 개선** [§12-9] / **ingest 큐레이션 점검** [§12-10]
- (참고) §12-11~13 sub-track 묶음, §12-14~23 대부분 `closed` → 재개 시 원본에서 open 재확인

### 신규 (§ad-track-1 발)
- **`topics/pet-food-premium.env`에 vertex 시절 `RAG_DISTANCE_THRESHOLD=0.60` 박제** — openai 오버레이로 돌리면 전량 컷. 우선도 하
- **`1982_Holbrook.pdf`가 텍스트 diff 처리**(5,717줄) — `.gitattributes`에 `*.pdf binary` 검토. 우선도 하

## 아카이브
- README-dev.md, README-dev-2.md = 기존 기획서/보고서 에이전트 개선 기록
- README-dev-§14.md = §14 vertex 백엔드 점검·개선 아카이브
