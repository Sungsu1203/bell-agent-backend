# WORKBOARD — 회사 트랙 (광고·마케팅 writer)

> 🏢 회사 트랙 할일·활성 트랙·결정 기록. 운영 규칙은 ./GUARDRAILS.md, 공통은 ../CLAUDE.md.

---

## 지금 상태 (한 줄)
**§research-1 활성.** 연구 루프(Plan↔Evaluate) 구조 재설계. R1 정찰 종료 → R2 설계 착수.
§ad-track-1은 **완료(E열 미충족, 미스매치 판정)**로 이동.

## 활성 트랙

### §research-1 — 연구 루프 구조 재설계
- **시작** 2026-08-03 / **토픽** `topics/experiential-marketing-media.env` (ad/research 트랙 공유)
- **venv** `../.venv_openai/bin/python`
- **현재** R1·R1b 종료 → **R2 설계(챗 소관)**. 누적 비용 **$0** (전량 읽기 전용)

| 단계 | 결과 |
|---|---|
| R1 | 그래프·fast-path·근거사슬 정찰. **계기판 기발견**(9노드 `emit_event` + `/api/events`·`/api/state`) → 계측기 삽입 작업 소멸 |
| R1b 감사 | credential 이력 오염 발견 → STOP → 키 회전(사용자) + HEAD 정리 + `.gitignore` 보강 + 감사 절차 3축 개정 |
| R1b 대조 | 원형 BlockAGI Plan↔Evaluate 배선 실측 |
| R2-a | 설계 입력 수집 + R1b 정정 2건 |

**🔴 R1의 3대 발견**
1. **근거 사슬은 본선에서 안 끊긴다.** X는 `research_synthesizer` 곁가지 1곳뿐이고 소비처가 0건.
   본선은 `[[N]]` 인덱스 + `.refs.json`(URL + 청크 풀텍스트)로 살아 있다
2. **Evaluate→Plan 되먹임 배선이 없다.** 목표는 env 5개 고정 순회(`research_planner.py:227`)
3. **원인은 배선이 아니라 출력 형식.** 원형은 Evaluate 출력에 JSON 스키마를 강제하고
   `json.loads` → dataclass로 필드를 꺼낸다. 우리는 마크다운 자유 서술이라 추출 불가
   → **R2 과제가 "슬롯 1개 추가"에서 "출력 스키마 + 파서 + 슬롯"으로 확대됨**

**우리가 원형보다 나은 2건** (이식 불요): 루프 종료(`no_new_url_streak` 보유) · citation 보증(`.refs.json`)

- **박제** `scripts/output/§research-1/R1_FINDINGS.md` · `R1b_{CREDENTIAL_AUDIT,HYGIENE_CLOSE,BLOCKAGI_COMPARE}.md` · `R2a_DESIGN_INPUTS.md`
- **대조 자산** `~/dev/blockagi-ref`(upstream, 읽기전용) · `~/dev/blockagi-run`(포크, `ahead 1` 미push)

## 완료 트랙

### §ad-track-1 — 체험마케팅과 미디어 콘텐츠 (홍익대 대학원 15주) — **완료(E열 미충족)**

> **종결 판정**: 목표(E열 14칸)에 도달하지 못했다. arm Z로 3요소 5건 + 준확정 3건까지가 실적이다.
> 미충족 사유는 수집 부족이 아니라 **파이프라인과 목표의 미스매치**로 판정됐다 —
> 리포트 생성 경로는 브랜드·연도를 깎고(catch AN), 추출 경로는 소스 그룹핑·`published_date`가 없다.
> 잔여 계단(3-d-1 ④~⑧, 3-d-2 ⑨)은 아래 **이월** 표로 이관.
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
| 08-05 | **history scrub(`filter-repo`) 기각 — 재론 금지** | 회전하면 옛 키는 무효 문자열. scrub은 죽은 문자열을 가릴 뿐인데 **모든 커밋 해시가 바뀌어** 1년치 박제의 추적성이 파손된다. 두 레포 모두 적용 [STANDARDS §5.4-a] |
| 08-05 | **`blockagi-run` push 하지 않음** | 키가 콘솔에서 이미 삭제돼 무효. B-2 보류로 실익 0. 재사용 사유 발생 시 push |
| 08-05 | **credential 감사 = 파일명 축 1순위** | 구 절차(현행 키 prefix 검색)가 이전 세대 키를 원리적으로 놓쳤다. prefix 없는 키(naver·serpapi)는 정규식으로 검출 불가 [STANDARDS §5.1-a] |
| 08-05 | **§ad-track-1 완료 처리(E열 미충족)** | 미충족 사유 = 수집 부족이 아니라 파이프라인·목표 미스매치. 잔여 계단은 이월 |

## 이월 — §ad-track-1 잔여 계단 (재개 시)

| | 단계 | 비용 |
|---|---|---|
| ④ | 게이트 위치 정찰 → catch P 재판정 | $0 |
| ⑤ | `published_date` 추출률 실측 → 구현 + diff STOP | $0 |
| ⑥ | arm Z 소스 그룹핑 개선 (catch AV 대응) | $0 |
| ⑦ | 목록 토큰 A/B 검색 dry-run → 10주 쿼리 확정 | $0 |
| ⑧ | 준확정 3건 URL 확인 → 승격 | $0 |
| ⑨ | a) aimatters 목록 4페이지 / b) 10주 신규 / c) 07·15 재수집(쿼리 변형 동반) | **유료** |

## 별건 이월 — credential·외부 서비스 (§research-1 R1b 발)

| # | 항목 | 기한 | 우선도 |
|---|---|---|---|
| 1 | **NAVER Search API → API HUB 이관** — NCP 계정 신규 가입 + 인증 체계 변경(개발자센터 Client ID/Key → API HUB Key) | **2027-06-30 지원 종료** (프로모션 2026-09-30) | 중 |
| 2 | **Naver Client Secret 회전** — 1번과 동시 처리 | 상동 | 중 |
| 3 | SerpAPI 계정 정리 (`.env` 미참조) | — | 하 |
| 4 | `gemini-rag-project-new` 프로젝트/계정 정리 | — | 하 |
| 5 | `blockagi-run` push (평문 키 제거 커밋, `ahead 1`) | blockagi 재사용 시 | 하 |

⚠️ 2번을 단독 선행하지 말 것 — **개발자센터 신규 신청 차단일(2026-07-31)이 지나** 재발급 가능
여부가 불확실하다. 섣불리 회전하면 **현행 키만 죽을 수 있다.** 현행 키는 200 응답으로 유효 확인됨.

> 회전 완료분·미착수분 상세 = `scripts/output/§research-1/R1b_HYGIENE_CLOSE.md` §E

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
- 🔴 **`published_date` 메타데이터 추가 (catch AY)** — §12-1과 동일 항목. **우선도 상.**
  ⚠️ **누적 인덱스의 선행 조건이다.** §research-1 R2 설계에서 다시 걸린다
- **arm Z 소스 그룹핑 개선 (catch AV)** — 우선도 중. 이월 ⑥과 동일
- **`topics/pet-food-premium.env`에 vertex 시절 `RAG_DISTANCE_THRESHOLD=0.60` 박제** — openai 오버레이로 돌리면 전량 컷. 우선도 하
- **`1982_Holbrook.pdf`가 텍스트 diff 처리**(5,717줄) — `.gitattributes`에 `*.pdf binary` 검토. 우선도 하

### 신규 (§research-1 발)
- **`.gitignore` 차단 잔여** — `api_secrets.txt` 류 접미 변형 · `*.p12` · `*.pfx` · `id_rsa` 계열 미차단.
  현행 차단분은 루트 `.gitignore:21-36`. 우선도 하

## 아카이브
- README-dev.md, README-dev-2.md = 기존 기획서/보고서 에이전트 개선 기록
- README-dev-§14.md = §14 vertex 백엔드 점검·개선 아카이브
