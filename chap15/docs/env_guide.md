1) LLM · API 설정

OPENAI_API_KEY

값: OpenAI API 키 (필수)

기본값: 없음 → 미설정 시 get_llm()가 RuntimeError 발생

언제: 로컬/CI 모두 반드시 설정.

OPENAI_MODEL

값: 예) gpt-4o (기본), gpt-4o-mini 등

기본값: gpt-4o

OPENAI_BASE_URL / OPENAI_API_BASE

값: 커스텀 API 엔드포인트

기본값: 미설정(공식)

OPENAI_ORG_ID / OPENAI_ORGANIZATION

값: 조직 ID

기본값: 미설정

테스트에서 외부 호출을 막고 싶으면 get_llm을 monkeypatch 해주세요(이미 테스트 코드 예시 제공).

2) 문서 모드 · 라이터

DOC_MODE

값: report(섹션 단위) / book(챕터 단위)

기본값: 프로젝트 config 기본값(없으면 report로 가정)

WRITER_AGENT

값: section_writer 또는 chapter_writer 등

기본값: config 지정값

AUTO_FOOTNOTE

값: 1/true/yes/on → 자동 각주 삽입 시도, 그 외는 비활성

기본값: 1

언제: 초안 저장 전, 인용 자동 추가.

3) RAG / 검색 · 인덱싱

RAG_TOP_K

값: 정수 (검색 결과 상위 N개)

기본값: 6

SKIP_WEB_SEARCH

값: 1/true/yes/on → 웹 검색 건너뛰고 로컬 인덱스만 사용

기본값: 0

언제: 오프라인·내부파일만 쓸 때.

LOCAL_RAG_GLOBS

값: 로컬 파일 ingest 글롭 패턴들 | 로 구분

예: docs/**/*.pdf|notes/*.md ( <topic-slug> 치환 지원 )

기본값: 공백

언제: SKIP_WEB_SEARCH=1일 때 유효.

ALLOW_LOCAL_SUMMARY

값: 1/true/yes/on → vector_search가 로컬 문서만으로 1문단 요약 생성

기본값: 0

언제: 빠른 내부 질의 응답을 바로 반환하고 싶을 때.

AUTO_WRITE_DURING_RESEARCH

값: 1/true/yes/on → 리서치 라운드 중에도 집필 스케줄링 허용

기본값: 0

(암묵적) CLEAR_ON_FIRST_VECTOR / CLEAR_CHROMA_ON_START

도큐먼트에 언급된 내부 플래그(실제 동작은 ensure_vector_store_cleared_once(...)가 관리).

동일 NS에서 1회만 벡터스토어 클리어.

4) 연구 라운드(Research Loop) · 목표

BLOCKAGI_AGENT_ROLE

값: 예) research analyst

기본값: 공백

언제: research analyst일 때 연구 루프 가동 조건 중 하나.

ITERATION_COUNT

값: 정수(연구 라운드 최대 횟수)

기본값: 0 (비활성)

BLOCKAGI_OBJECTIVE_1..9

값: 문자열(개별 연구 목표)

기본값: 없음 (비워도 됨)

BLOCKAGI_OBJECTIVES

값: JSON 배열 문자열 (예: ["목표A","목표B"])

기본값: 없음

우선순위: OBJECTIVE_1..9 → OBJECTIVES(JSON) → state에 이미 있으면 그대로.

5) 대시보드(진행 상황) · 로깅

SHOW_DASHBOARD

값: 1/true/yes/on → Supervisor가 라우팅/상태를 대시보드 형식으로 로그 출력

기본값: 0

DASH_WRAP

값: 정수(문자열 줄폭, 기본 88)

LOG_DASHBOARD

값: 1/true/yes/on → Communicator에서 “최근 대시보드 로그가 찍혔으면 간단 메시지로 축약”

기본값: 1

DASH_RATE_SEC

값: float(초). 최근 dash_last_ts로부터 이 시간 내면 간단 모드

기본값: 6

dash_last_ts는 코드에서 state.flags로 관리(대시보드 찍힐 때 supervisor가 넣는 방식으로 확장 가능).

6) 콘솔 에코(원문 출력)

ECHO_OUTLINE

값: 1/true/yes/on → Communicator가 목차 원문을 콘솔에 예쁘게 에코

기본값: 0

ECHO_SECTIONS

값: 1/true/yes/on → Section Writer가 저장된 섹션 원문을 콘솔에 에코

기본값: 0

ECHO_CHAPTERS

값: 1/true/yes/on → Chapter Writer가 저장된 챕터 원문을 콘솔에 에코

기본값: 0

보조: ECHO_SECTIONS=1이면 챕터도 에코되도록 코드가 묶여 있음.

7) 진행률 카운트(섹션/챕터)

중요: TypedDict 경고 회피를 위해 항상 state["flags"] 밑에 저장/조회합니다.

state.flags.sections_done / state.flags.sections_total

섹션 저장 직후 섹션 라이터가 갱신.

sections_total은 목차에서 H2/체크박스 수를 우선 추정, 없으면 기본 8.

state.flags.chapters_done / state.flags.chapters_total

챕터 저장 직후 챕터 라이터가 갱신.

chapters_total: 없으면 CHAPTERS_TOTAL_DEFAULT 사용.

CHAPTERS_TOTAL_DEFAULT

값: 정수

기본값: 12

Communicator는 진입 시 아래처럼 표시(이미 코드 반영됨):

f = state.get("flags") or {}
done = int(f.get("sections_done") or 0)
total = int(f.get("sections_total") or 0)
if total > 0:
    logger.info("[Communicator] 진행률: %d / %d", done, total)

8) 로컬 Ingest · 경로 치환

LOCAL_RAG_GLOBS에서 <topic-slug> 토큰 지원

예: content/<topic-slug>/refs/*.md

윈도우/유닉스 경로 구분자는 코드에서 정규화.

9) 추천 세팅(운영 / 개발 / 테스트)
운영(.env)
# LLM
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# 문서 모드(리포트)
DOC_MODE=report
WRITER_AGENT=section_writer

# RAG
RAG_TOP_K=8
SKIP_WEB_SEARCH=0
ALLOW_LOCAL_SUMMARY=0
AUTO_WRITE_DURING_RESEARCH=0

# 연구 루프
BLOCKAGI_AGENT_ROLE=
ITERATION_COUNT=0

# 대시보드/로깅
SHOW_DASHBOARD=1
LOG_DASHBOARD=1
DASH_RATE_SEC=6
DASH_WRAP=88

# 콘솔 에코
ECHO_OUTLINE=0
ECHO_SECTIONS=0
ECHO_CHAPTERS=0

# 진행률 디폴트(책 모드 전환 대비)
CHAPTERS_TOTAL_DEFAULT=12

내부 문서만 쓰는 오프라인 리서치
SKIP_WEB_SEARCH=1
LOCAL_RAG_GLOBS=content/<topic-slug>/refs/**/*.pdf|notes/**/*.md
ALLOW_LOCAL_SUMMARY=1

리서치 라운드 집중 모드(자동 반복)
BLOCKAGI_AGENT_ROLE=research analyst
ITERATION_COUNT=3
SHOW_DASHBOARD=1
LOG_DASHBOARD=1

개발/테스트
# 외부 호출 방지: pytest에서 get_llm, prompts를 monkeypatch로 대체
AUTO_FOOTNOTE=0
ECHO_SECTIONS=0
ECHO_CHAPTERS=0
LOG_DASHBOARD=1
DASH_RATE_SEC=6
CHAPTERS_TOTAL_DEFAULT=4

10) 자주 겪는 이슈 & 해결

“OPENAI_API_KEY가 설정되지 않았습니다.”
→ .env에 키 넣고, 로컬 셸에서 set/export 확인. 테스트는 get_llm monkeypatch.

TypedDict 경고(진행률 카운트)
→ state["flags"] 안에만 쓰세요(이미 코드 반영: section/chapter_writer).

Communicator가 장황함
→ LOG_DASHBOARD=1 + state.flags.dash_last_ts=time.time()를 찍어두면, DASH_RATE_SEC 내 간단 모드로 응답.

로컬 파일만 검색하고 싶다
→ SKIP_WEB_SEARCH=1 + LOCAL_RAG_GLOBS를 지정.