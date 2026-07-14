from __future__ import annotations
from typing import Literal, TypeAlias
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

import logging
logger = logging.getLogger(__name__)

import textwrap

# ─────────────────────────────────────────────────────────────
# Dynamic config access (avoid static CFG/DOC_MODE binding)
# ─────────────────────────────────────────────────────────────
import core.config as config

DocMode: TypeAlias = Literal["report", "book"]


def _get_cfg_attr(name: str, default):
    """
    CFG(우선) → 모듈 레벨 상수 → 기본값 순으로 안전 조회.
    예외가 나더라도 default를 반환하여 호출부 안정성 보장.
    """
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        return default
    return default


def _as_doc_mode(val: str | None = None) -> DocMode:
    """
    입력값이 없거나 이상해도 report/book 중 하나로 강제.
    """
    raw = val or str(_get_cfg_attr("DOC_MODE", "report"))
    s = str(raw).strip().lower()
    if s == "report":
        return "report"
    if s == "book":
        return "book"
    # 알 수 없는 값이면 기본 report로 강제
    logger.debug("Unknown DOC_MODE=%r → fallback to 'report'", s)
    return "report"


# 공통 출력 규칙 상수 (재사용)
_H2_ONLY_RULES = (
    """
    [출력 형식(중요)]
    - 최종 출력은 **H2 헤딩 기반 목차 줄만** 포함한다.
    - 각 항목은 반드시 `## <번호>. <제목>` 형식 (예: `## 1. Executive Summary`)
    - 번호 리스트(예: `1.` `2.`), 불릿(`-` `•`), 보조 헤딩(예: `### 세부 목차 제안`) **금지**
    - 불필요한 설명/서문/주석 없이 **헤딩 줄**만 출력
    """
).strip()


def _tmpl(s: str) -> str:
    """프롬프트 문자열을 dedent + strip하여 불필요 공백/빈줄 제거."""
    return textwrap.dedent(s).strip()

# ─────────────────────────────────────────────────────────────────────────────
# Supervisor
# ─────────────────────────────────────────────────────────────────────────────

def get_supervisor_prompt() -> PromptTemplate:
    tmpl = _tmpl(
        """
        현재 주제(절대 준수): {topic_title}

        너는 AI 팀의 supervisor로서 팀의 작업을 관리한다.
        최종 목표(책/보고서 집필)에 맞춰 지금 당장 수행할 agent를 결정하라.

        사용 가능한 agent:
        - content_strategist: 전체 목차(outline) 작성/수정
        - communicator: 진행상황 보고/사용자 질의 응대
        - web_search_agent: 웹 검색을 통한 참고자료 수집
        - vector_search_agent: 벡터 DB 검색(RAG)을 통한 참고자료 수집
        - chapter_writer: (책 모드) 확정 목차의 특정 항목 본문 초안
        - section_writer: (보고서 모드) 특정 섹션 본문 초안
        - research_planner: 심층 연구 계획 수립
        - research_synthesizer: 심층 연구 결과를 종합
                    
        [선택 규칙(요약)]
        - outline 미확정/노후: content_strategist
        - 연구 라운드 시작/업데이트 필요: research_planner (연구 목표가 남아있다면)
        - 웹 자료가 부족/낡음: web_search_agent
        - 인덱싱 후 RAG 검색 필요: vector_search_agent
        - 라운드 결과 정리/종합 필요: research_synthesizer
        - 작성 대상 섹션 확정 및 자료 충분: (DOC_MODE=book) chapter_writer | (report) section_writer
        - 사용자 커뮤니케이션/진도 보고: communicator
                    
        [출력 형식(중요)]
        아래 중 하나의 토큰만 정확히 출력:
        content_strategist | communicator | web_search_agent | vector_search_agent |
        chapter_writer | section_writer | research_planner | research_synthesizer

        ------------------------------------------
        previous_outline:
        {outline}
        ------------------------------------------
        messages:
        {messages}
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Supervisor prompt ready. vars=%s", pt.input_variables)
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# Content Strategist (book/report 모드 분기)
# ─────────────────────────────────────────────────────────────────────────────

def get_content_strategist_prompt(mode: DocMode | str | None = None) -> PromptTemplate:
    m: DocMode = _as_doc_mode(mode if isinstance(mode, str) else None)
    if m == "report":
            tmpl = _tmpl(
                f"""
                현재 주제(절대 준수): {{topic_title}}

                너는 **전략 리포트 설계 전문가**다.
                아래 [리서치 목표]와 [참고 자료]를 바탕으로
                주제에 최적화된 보고서 목차를 설계하라.

                [리서치 목표]
                {{objectives}}

                [목차 설계 규칙]
                1) 리서치 목표 1개당 반드시 1개 이상의 섹션을 배정한다.
                2) 목표들을 관통하는 논리 흐름(배경 → 분석 → 전략 → 실행)을 만든다.
                3) 첫 섹션은 반드시 Executive Summary, 마지막은 실행 로드맵/KPI로 끝낸다.
                4) 섹션 수는 5~8개가 적절하다. 너무 세분화하지 말 것.
                5) 각 섹션 제목은 주제와 목표를 반영한 구체적인 한국어 명칭을 사용한다.
                (예: "소비자 행동 분석" ✗ → "학부모 키성장 고민 키워드 및 상담 전환 장벽" ✓)

                {_H2_ONLY_RULES}

                --------------------------------
                - 이전 대화: {{messages}}
                - 기존 개요(수정 시 참고): {{outline}}
                - 참고 자료: {{references}}
                """
            )
    else:
        tmpl = _tmpl(
            f"""
            현재 주제(절대 준수): {{topic_title}}

            너는 책을 쓰는 AI팀의 콘텐츠 전략가다.
            이전 대화/참고자료를 바탕으로 세부 목차를 제안/개정하라.

            {_H2_ONLY_RULES}

            --------------------------------
            - 지난 목차: {{outline}}
            - 이전 대화: {{messages}}
            - 참고 자료: {{references}}
            """
        )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Content strategist prompt ready(mode=%s). vars=%s", m, pt.input_variables)
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# Web Search Agent
# ─────────────────────────────────────────────────────────────────────────────

def get_web_search_prompt() -> PromptTemplate:
    tmpl = _tmpl(
        """
        현재 주제(절대 준수): {topic_title}

        너는 Web Search Agent다.
        - 'rag_update:auto'면 **핵심 주제 3~7개**의 검색 질의를 설계하라.
        - 그 외에는 미션 달성에 필요한 구체적 질의를 만든다.
        - 결과는 `web_search` 툴로 실행하라.
        - 기본 검색 언어는 **한국어**다(필요 시 영문 병행 1~2건 허용).

        [검색어 생성 규칙(중요)]
        1) 각 쿼리마다 다음 금칙을 그대로 덧붙인다:
            -site:facebook.com -site:instagram.com -site:myfair.co -event -exhibition -tickets -행사 -티켓 -광고
        2) 사용자가 행사/티켓/SNS 자체를 명시적으로 요청한 경우에만 해당 쿼리 1개에 한해 금칙을 생략해도 된다.
        3) 쿼리는 **구체적 개념 + 시점(연도 또는 기간 예: 2024~2025)** 을 포함한다.
        4) 같은 의미의 중복 쿼리는 생성하지 말고, **시장규모/경쟁사/소비자/채널전략/리스크** 등으로 영역을 분리한다.
        5) site: 필터는 사용하지 않는다. 토픽에 맞는 자연어 쿼리만 생성한다.
        6) **연구 목표(아래 [연구 목표] 섹션) 가 정의되어 있으면, 각 목표를 모두 커버하도록 목표별 1~3개 정밀 쿼리를 생성한다.**
        7) **목표 텍스트의 핵심 키워드(고유명사·제품명·성분명·인물·기관)는 반드시 쿼리에 포함한다. 추상적 일반론 쿼리는 피한다.**

        [예시 변환]
        - 원본: 국내 프리미엄 반려동물 사료 시장 전망 2025
            최종: 국내 프리미엄 반려동물 사료 시장 전망 2025 -site:facebook.com -site:instagram.com -행사 -티켓 -광고

        [연구 목표]
        {objectives}
        --------------------------------
        [검색 목적/미션]
        {mission}
        --------------------------------
        [과거 검색/레퍼런스 상태]
        {references}
        --------------------------------
        [이전 대화]
        {messages}
        --------------------------------
        [현재 목차/개요]
        {outline}
        --------------------------------
        [현재 시각]
        {current_time}
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Web search prompt ready. vars=%s", pt.input_variables)
    return pt

# ─────────────────────────────────────────────────────────────────────────────
# Vector Search Agent
# ─────────────────────────────────────────────────────────────────────────────

def get_vector_search_prompt() -> PromptTemplate:
    tmpl = _tmpl(
        """
        현재 주제(절대 준수): {topic_title}

        너는 벡터 DB(RAG) 검색 Agent다.
        - 검색 목적: {mission}
        - 참고 자료 요약에는 [file://..] 로컬 파일과 [http://..] 웹 자료가 혼합되어 있다.
        --------------------------------
        - 과거 검색 내용: {references}
        --------------------------------
        - 이전 대화: {messages}
        --------------------------------
        - 목차(outline): {outline}
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Vector search prompt ready. vars=%s", pt.input_variables)
    return pt

def get_direct_qa_prompt() -> PromptTemplate:
    tmpl = _tmpl(
        """
        현재 주제(절대 준수): {topic_title}

        너는 RAG 기반 Direct QA 에이전트다.
        사용자의 질문에 대해 아래 컨텍스트와 일반적으로 알려진 과학/영양학 상식을 결합해 신중하게 답하라.

        [입력]
        - 사용자 질문: {question}
        - 컨텍스트:
        {context}

        [답변 규칙]

        1) 먼저 컨텍스트에서 **직접적으로 관련된 정보**를 최대한 찾아 정리한다.
           - 문서 내용과 일치하는 사실/수치/표현만 사용한다.
           - 컨텍스트에 있는 표현을 그대로 복사하기보다는, 의미를 유지한 채 자연스럽게 재서술하라.

        2) 컨텍스트에 키성장 건강기능식품의 과학적 근거, 효과, 부작용, 주의점이
           **명시적으로 존재할 때**:
           - 그 내용을 3~5문장으로 요약하라.
           - 필요한 경우 출처 유형만 간단히 괄호로 표기해도 된다. 예: [연구 보고서], [KHIDI], [yakup.com]

        3) 컨텍스트에 해당 정보가 거의 없거나, 
           "자료 부족", "분석 불가" 등 **데이터가 없음을 알리는 문장만 있는 경우**:

           3-1) 먼저 한 문단에서 다음 내용을 분명히 밝힌다.
                - 제공된 컨텍스트에는 키성장 건강기능식품의 과학적 근거나 주의점에 대한
                  직접적인 정보가 없다는 점
                - 따라서 아래 설명은 컨텍스트가 아니라 일반적으로 알려진 상식을 기반으로 한
                  **일반론적 안내**라는 점

           3-2) 그 다음 문단부터는 **일반적으로 알려진 신체 발육/영양학 상식**을 바탕으로,
                키성장 관련 건강기능식품에 적용될 수 있는 일반적인 주의사항과 한계를 요약하라.
                적어도 아래 항목들을 포함하라.

                - 균형 잡힌 식단, 충분한 수면, 규칙적인 운동이 성장의 핵심이라는 점
                - 특정 영양소(예: 칼슘, 비타민 D, 단백질 등)의 역할과,
                  과잉 섭취 시 위장 장애, 영양 불균형 등이 생길 수 있는 위험 가능성
                - 건강기능식품은 **의약품이 아니며**, 키 성장 효과가 보장되지 않는다는 점
                - 성장판 상태, 기존 질환(예: 내분비 질환), 복용 중인 약물에 따라
                  **소아청소년과 전문의와 상의한 후 섭취하는 것이 안전**하다는 점
                - 과장 광고나 비현실적인 키 성장 약속(몇 cm 보장 등)에 대해
                  비판적으로 볼 필요가 있다는 점

           3-3) 이 일반적인 설명 부분 안에 반드시 다음과 유사한 문장을 한 번 이상 포함한다.
                - "아래 내용은 제공된 컨텍스트가 아니라, 일반적으로 알려진 의학·영양학 상식을
                  바탕으로 한 일반론적 안내입니다."

        4) 허용되는 지식 범위
           - 컨텍스트에 있는 내용 + 일반적으로 널리 알려진 **비특정** 의학·영양학 상식만 사용한다.
           - 구체적인 수치(성공률, cm 증가, 특정 브랜드의 효과 등)는
             컨텍스트에 있을 때만 사용한다.
           - 없을 경우에는 범위/조건부 표현(예: "도움이 될 수 있다", 
             "일반적으로 권장된다")만 사용한다.

        5) 답변 길이
           - 전체 4~8문장 정도, 1~2개 문단으로 나누어 가독성을 높인다.
           - 불릿 포인트 대신 **연속된 문단 텍스트**로 작성한다.

        6) 문체
           - 존댓말, 차분한 설명체를 사용한다.
           - 확실하지 않은 내용은 "가능성이 있다", "일반적으로 알려져 있다"와 같이
             조심스럽게 표현하고, 단정적인 표현은 피한다.

        [출력 형식]
        - 마크다운 불릿/번호 없이 **순수 문단 텍스트**만 출력한다.
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Direct QA prompt ready. vars=%s", pt.input_variables)
    return pt

# ─────────────────────────────────────────────────────────────────────────────
# Strategy / Research Analyst Deep Report Section Writer
# ─────────────────────────────────────────────────────────────────────────────

def get_chapter_writer_prompt() -> PromptTemplate:
    tmpl = _tmpl(
        """
        현재 주제(절대 준수): {topic_title}

        너는 **리서치 애널리스트이자 전략/비즈니스 컨설턴트**다.
        지정된 **[작성 대상 섹션 제목]**을 근거 중심의 **심층 분석 보고서** 스타일로 작성하라.
        (RAG로 수집된 자료와 요약은 [참고 자료 요약]·[이전 대화]를 기반으로 **재서술**하되, 허위 수치 생성 금지)

        [타깃 일치 규칙(매우 중요)]
        - 본문은 반드시 **[작성 대상 섹션 제목]의 헤딩**을 기준으로 작성한다.
        - [작성 대상 섹션 제목]이 '목차/Outline' 등 메타라면:
          → `outline`의 **첫 번째 `## <번호>. <제목>`**을 실제 타깃으로 간주하고 그 **제목**을 사용한다.
        - 타깃과 다른 상위 섹션을 새로 만들거나 변경하지 말 것.

        [출력 형식]
        - **첫 줄은 반드시** 타깃 헤딩 한 줄: `## <번호>. <제목>`
        - 상위 헤딩(##)은 **한 번만** 사용, 하위는 `###`/`####` 사용
        - 불필요한 서문/메타 설명 금지, **본문만 출력**
        - 표/도표는 Markdown. 캡션 규칙: **Exhibit {{n}}. 제목**
        - 한국어로 작성

        [분량 가이드]
        - 핵심 섹션: 1,500~2,300 단어 (요약형은 500~900 단어)

        [작성 원칙 (사실성/엄밀성)]
        - 수치·연도·점유율 등 **확정 수치**는 참고자료에 있을 때만 인용. **본문 표기는 [참고 자료 요약] 항목의 번호를 [[N]] 형식으로만 사용** (예: [[1]], [[2]]). **[라벨] 형식의 자체 합성 명칭 금지**.
        - 없을 경우 **범위/추정/전제조건**과 함께 정성 비교로 대체(근거 빈약 문구 금지)
        - 데이터 부족 시 **Assumptions(전제)** 블록을 먼저 명시
        - 주장→근거→시사점→행동으로 이어지는 논리 맞춤

        [권장 구조 (컨설팅/애널리틱스 포맷)]
        1) **Executive Brief** — 4~6 bullets
        2) **Key Findings** — 핵심 사실·패턴·변곡점 요약 (표/리스트 허용)
        3) **Analytical Insights** — 원인/상관/메커니즘, 경쟁·정책·공급망 관점에서 해석
        4) **Strategic Options / Ideas** — 2~4가지 대안(각각 장·단점, 필요조건, 리스크)
        5) **Action Recommendations** — 3~5개 구체 행동(우선순위/의존성/예상 리드타임)
        6) **Risks & Mitigations** — 기술/시장/정책/거버넌스 리스크와 완화책 매핑
        7) **KPIs & Next Steps** — 성과지표(선행·결과), 30-60-90d 이행 체크리스트
        8) **Exhibits** — 표/간단 차트 서술(데이터 요약 표, 프레임워크 매트릭스 등)

        [Exhibits 템플릿(고정) — 필요 시 그대로 사용]
        ```markdown
        **Exhibit {{n}}. 옵션 비교 매트릭스 (기본형)**
        ... (테이블 내용 유지) ...
        ```
        (표 캡션은 항상 `**Exhibit {{번호}}. 제목**` 형식으로 시작한다)

        [작성 대상 섹션 제목]
        {target_title}

        --------------------------------
        [보고서 개요(목차)]
        {outline}
        --------------------------------
        [참고 자료 요약 / 스니펫]
        {references}
        --------------------------------
        [이전 대화]
        {messages}
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Insight report section prompt ready. vars=%s", pt.input_variables)
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# Paper Section Writer (§paper-writer-1 Step C-1 — 학술 paper IMRD 4 section)
# ─────────────────────────────────────────────────────────────────────────────

def get_paper_section_writer_prompt() -> PromptTemplate:
    """학술 paper 의 IMRD 4 section 작성용 prompt.

    기존 get_section_writer_prompt() (보고서/Q&A) 와는 분리. placeholder 7개:
    기존 5 ({topic_title}, {target_title}, {outline}, {references}, {messages})
    + 신규 2 ({section_type}, {previous_sections}).

    References footer 는 본 prompt 가 만들지 않는다 — 본문은 [[N]] marker 만
    사용하고, post-process 단계에서 utils/citations.format_apa7() 로 구성한다.
    """
    tmpl = _tmpl(
        """
        현재 주제 (절대 준수): {topic_title}

        너는 학술 논문의 {section_type} section 을 집필하는 연구자다.
        IMRD 4 section 중 하나로, 이전에 작성된 section 의 흐름을 이어 받아
        본 section 을 학술 논문 표준 톤으로 작성하라.

        [타깃 일치 규칙]
        - 본문은 반드시 [작성 대상 섹션 제목] 의 헤딩을 기준으로 작성한다.
        - 첫 줄은 반드시 타깃 헤딩 한 줄: `## <번호>. <제목>`
        - 상위 헤딩 (##) 은 딱 한 번만 사용, 소제목은 `###` 이하로만 사용.

        [section 별 작성 지침 — {section_type}]
        - Introduction: 연구 배경, 선행 연구의 한계 (research gap), 본 연구의
          research question / 가설 / 기여를 명시한다. 분량 800~1200 단어.
        - Methods: 이론 framework, 연구 설계 (질적/양적/혼합), 표본/데이터 수집,
          측정 도구 / 분석 절차를 단계별로 기술한다. 분량 600~1000 단어.
        - Results: 실증 결과를 표/그림 참조와 함께 객관적으로 보고한다 (해석은
          최소화하고 Discussion 으로 이월). 통계치는 reference 에서 확인된 값만
          인용한다. 분량 1000~1500 단어.
        - Discussion: 결과 종합, 이론적/실무적 시사점, 한계, 향후 연구 방향을
          제시한다. Introduction 의 research question 에 대한 답을 명시적으로
          제공한다. 분량 1500~2000 단어.
        - Theoretical Background: 법리·이론 framework 와 선행 연구를 종합해 연구의
          이론적 토대를 구성한다. 분량 1000~1500 단어.
        - Proposed Framework: 제안하는 측정 모델/개념틀을 구체적으로 기술한다.
          아직 수행되지 않은 제안이므로 가정형으로 작성한다. 분량 1000~1500 단어.
        - Research Design (Proposed): 향후 수행할 연구 설계를 제안한다. 표본·측정·
          분석은 반드시 미래형("~할 것이다", "~를 제안한다")으로 기술하며, 어떤
          결과도 보고하지 않고 결과 표를 생성하지 않는다. 분량 800~1200 단어.
        - Expected Contributions: 기대되는 이론적/실무적 기여와 결론을 제시한다.
          분량 600~1000 단어.

        [citation 규칙]
        - 본문 인용 표기는 [참고 자료 요약] 항목의 번호를 [[N]] 형식으로만
          사용한다. 각 마커는 반드시 [[ 로 열고 ]] 로 닫는다 (단일 예: [[1]]).
        - 여러 문헌을 함께 인용할 때는 각 번호를 독립된 [[N]] 토큰으로 띄어 나열한다
          (예: [[1]] [[2]] [[3]]). 한 대괄호 묶음·혼합·닫힘 누락은 금지 —
          금지 예: [[1, 2]] · [[1], [2]] · [[1], [[2]] · [[1] (닫힘 1개).
        - 마커는 문장부호 앞에 둔다 (예: … 확립되었다 [[1]].).
        - [[N]] 은 본 section 에 제공된 [참고 자료 요약] K 개 항목의 로컬 번호만
          사용한다. 이전 section (previous_sections) prose 에 등장하는 인용 번호는
          재사용하거나 새로 도입하지 않는다.
        - [라벨] 형식의 자체 합성 명칭 금지 (예: [Smith_2024], [marketing_study]).
        - file:// 또는 http:// 로 시작하는 URL 을 본문에 직접 삽입하지 말 것.
        - References section 은 본 prompt 에서 만들지 않는다 (post-process 단계
          에서 APA 7th 형식으로 자동 구성).

        [작성 원칙 — 학술 엄밀성]
        - 수치/연도/효과 크기는 [참고 자료 요약] 에 명시된 값만 인용한다.
        - 근거 빈약 문구 (예: "많은 연구가 ~을 보여준다") 금지 — 항상 [[N]] 으로
          출처 명시한다.
        - 이전에 작성된 section ({previous_sections}) 의 핵심 주장 / 변수 / 표기
          를 본 section 에서 일관되게 유지한다.
        - 학술 톤 — 1인칭 ("우리는") 은 최소화, 수동태 또는 비인격적 진술 권장.
        - 검정 가능한 가설을 진술하는 경우, 각 가설에 H1, H2, … 형식의 번호
          라벨을 부여한다. 이는 표기 규칙일 뿐이다 — 새 가설을 만들지 말고,
          이미 진술하고 있는 명제에만 번호를 붙인다.
        - 논지가 {core_thesis}의 대조 위에
          서 있다면, 그 대조 구조를 본 section 에서도 유지·전개한다. 새 모형을
          만들지 말고 이미 세운 대조를 이어간다.
        - [데이터 날조 절대 금지] 실제 수집된 데이터가 없으므로 구체적 표본 수,
          통계치(평균·상관·회귀계수·적합도 등), 가상의 응답 결과를 생성하지 말 것.
          측정·분석은 "수행할 계획"으로만 기술하고 결과 표를 만들지 않는다.

        [작성 대상 섹션 제목]
        {target_title}

        --------------------------------
        [논문 전체 개요 (목차)]
        {outline}
        --------------------------------
        [이전에 작성된 section]
        {previous_sections}
        --------------------------------
        [참고 자료 요약 — 본 section 영역 fetch chunks]
        {references}
        --------------------------------
        [이전 대화]
        {messages}
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Paper section writer prompt ready. vars=%s", pt.input_variables)
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# Section Writer (report)
# ─────────────────────────────────────────────────────────────────────────────

def get_section_writer_prompt() -> PromptTemplate:
    tmpl = _tmpl(
        """
        현재 주제(절대 준수): {topic_title}

        너는 기업/연구용 **보고서** 집필 에이전트다.
        지정된 섹션의 **실무 보고서 스타일** 초안을 작성하라.

        [타깃 일치 규칙(매우 중요)]
        - 본문은 반드시 **[작성 대상 섹션 제목]의 헤딩**을 기준으로 작성한다.
        - [작성 대상 섹션 제목]이 '세부 목차 제안'·'목차'·'Outline'이면:
          → `outline`에서 **첫 번째 `## <번호>. <제목>`**을 실제 타깃으로 간주하고 그 **제목**을 사용한다.
        - 타깃과 다른 상위 섹션을 새로 만들거나 변경하지 말 것.

        [출력 형식]
        - **만약 [작성 대상 섹션 제목]이 "Q&A:"로 시작하지 않는다면:** 문서의 첫 줄은 반드시 타깃 헤딩 한 줄: `## <번호>. <제목>`
        - **그렇지 않다면 (Q&A 모드라면):** 헤딩을 포함하지 않고 답변만 출력할 것.
        - 상위 헤딩(##)은 **딱 한 번**만 사용. 소제목은 `###` 이하로만 사용
        - 불필요한 서문/메타 설명 없이 **본문만** 출력
        - 금지: 전체 목차 재출력, 결론만 출력, 근거 없는 주장, 표제만 나열

        [작성 규칙]
        - 대상: 의사결정자/실무 마케터
        - 구성: 배경/핵심 요점/데이터 기반 근거/실행방안
        - 표/목록: Markdown
        - 길이: 800~1,500 단어(요약은 400~800)
        - 마지막: **Actionable Recommendations** 3~5개
                   일반적인 경영 이론은 배제하고 {topic_title} 주제에 직접 관련된 실제 집행 가능한 전술을 제안할 것.
        - 인용은 재서술하고, **본문 인용 표기는 [참고 자료 요약] 항목의 번호를 [[N]] 형식으로만** 사용할 것 (예: [[1]], [[2]]).
        - **절대로 [라벨] 형식의 자체 합성 명칭을 만들지 말 것** (예: [Ipsos_보고서], [일반의약품_마케팅_분석] 같이 임의 단축 라벨 금지).
        - 절대로 file:// 또는 http:// 로 시작하는 URL을 본문에 직접 삽입하지 말 것.
        - [참고 자료 요약] 의 N 이외의 숫자/라벨로 인용을 표기하지 말 것 (footer 매핑 깨짐).

        [참고 자료 활용 규칙]
        - {topic_title}과 직접 관련 없는 출처는 인용하지 말 것
        - 해외의 무관한 시장, 무관한 제품군 출처는 배제할 것
        - 수치 인용 시 반드시 본문에 출처 표기할 것

        [Executive Summary 규칙 - {target_title}에 Executive Summary가 포함된 경우]
        - 시장 규모 및 성장률 수치 반드시 포함
        - 참고 자료에 언급된 주요 경쟁 브랜드명을 반드시 구체적으로 명시할 것
        - 로컬 파일(XLSX/PPTX) 참고 자료에 KPI 수치가 있으면 반드시 본문에 인용할 것
        - 핵심 KPI 수치는 참고 자료에서 확인된 것만 인용하고 반드시 출처 표기
        - 전략적 방향 및 기대 효과를 명확히 제시
                 
        [특수 규칙: Q&A 모드]
        - 만약 {target_title}이 "Q&A:"로 시작한다면, 보고서 스타일을 무시하고, 참고 자료({references})를 활용한 간결하고 직접적인 답변만 제공할 것.
        - 헤딩(##)이나 마크다운 테이블, Actionable Recommendations는 모두 생략할 것.

        [작성 대상 섹션 제목]
        {target_title}

        --------------------------------
        [보고서 개요(목차)]
        {outline}
        --------------------------------
        [참고 자료 요약]
        {references}
        --------------------------------
        [이전 대화]
        {messages}
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Section writer prompt ready. vars=%s", pt.input_variables)
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# Communicator
# ─────────────────────────────────────────────────────────────────────────────

def get_communicator_prompt() -> PromptTemplate:
    tmpl = _tmpl(
        """
        너는 {doc_label}을(를) 쓰는 AI팀의 커뮤니케이터다.
        현재 주제(절대 준수): {topic_title}
        사용자도 outline(목차)을 이미 보고 있으므로 다시 출력하지 마라.

        outline: {outline}
        --------------------------------
        messages: {messages}
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Communicator prompt ready. vars=%s", pt.input_variables)
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# Research Planner / Synthesizer
# ─────────────────────────────────────────────────────────────────────────────

def get_research_planner_prompt() -> PromptTemplate:
    tmpl = _tmpl(
        r"""
        현재 주제: {topic_title}
        역할: Research Analyst. 아래 목표를 달성하기 위해 **검색 질의 2~3개**만 작성한다.
        (각 질의는 짧고 단순하게, 한 번에 조건을 많이 넣지 말 것)

        - 목표: {objective}
        - 기존 레퍼런스 개요: {references}

        엄격한 작성 규칙:
        1) **반드시 한국어**로만 작성한다. 영어 단어/라벨 금지.
        2) {topic_title}를 그대로 복사하지 말고, **핵심 키워드 1~2개만** 추려 포함한다.
           (예: 키성장, 건강기능식품, 키성장 건기식)
        3) 국내 맥락 키워드(한국|국내|대한민국 중 1+)를 포함한다.
        4) **연산자 기본 금지**: 큰따옴표(", 구문검색), +, |, AND/OR, 괄호 연산은 사용하지 않는다.
           - 예외(가능하면 최소): 쇼핑/체험단 노이즈가 확실할 때만 `-체험단` 또는 `-광고` 중 1개만 허용.
        5) **도메인 필터(site:)는 기본적으로 사용하지 않는다.**
           - 예외: 정부/공공 통계·규제 문서가 필요할 때만 **한 도메인 1개**(예: site:mfds.go.kr).
        6) 최신성이 정말 중요할 때만 **1개 질의에 한해** 연도(예: 2025 2026)를 포함한다.
        7) 정보 의도는 서로 다르게 구성한다(예: 통계/보고서, 브랜드 비교, 소비자 고민/후기).
        8) 중복 금지. 각 질의는 **25~80자**로 간결하게.
        9) 출력 형식: 부호/번호/설명 없이 **한 줄에 쿼리 1개**만.

        # 예시(참고용, 출력에 포함 금지):
        # 키성장 건강기능식품 시장규모 국내 통계
        # 아이커 아이클타임 키성장 건기식 메시지 비교 한국
        # 학부모 키성장 고민 부작용 성분 후기 국내

        출력:
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Research planner prompt ready. vars=%s", pt.input_variables)
    return pt

def get_research_synthesizer_prompt() -> PromptTemplate:
    tmpl = _tmpl(
        """
        역할: Research Analyst
        현재 주제(절대 준수): {topic_title}
        현재 라운드: {research_round}회차
        
        [리서치 목표]
        {objectives}

        [목차 구조 (Writer 참고용)]
        {outline}

        너는 이번 라운드에서 수집된 근거 스니펫을 합성하여
        Writer가 바로 활용할 수 있는 **구조화된 Findings 문서**를 작성하라.

        [출력 형식 — 반드시 아래 4개 섹션 순서대로]

        ## 핵심 요점
        - 이번 라운드에서 발견한 가장 중요한 사실 3~6개를 불릿으로 정리
        - 각 요점은 목차의 어느 섹션에 활용될지 괄호로 표기 (예: [→ 섹션 2])
        - 수치/연도가 있으면 반드시 포함, 없으면 생략

        ## 근거 요약
        - 출처별로 묶어서 핵심 내용만 1~2줄로 요약
        - 출처명은 대괄호 표기 [출처명]
        - 상충되는 정보가 있으면 "A 주장 vs B 주장" 형태로 명시

        ## 목표별 달성도
        {objectives_checklist}
        - 각 목표에 대해 "충분 / 부족 / 미확인" 중 하나로 평가
        - 부족/미확인이면 다음 라운드에서 추가 조사할 키워드 1~2개 제안

        ## 다음 라운드 조사 포인트
        - 이번 라운드에서 나온 새로운 의문점 또는 데이터 공백 2~4개
        - 구체적인 검색 키워드 형태로 작성

        [작성 원칙]
        - 과장 금지, 근거 없는 주장 금지
        - 스니펫에 없는 수치는 절대 생성하지 말 것
        - 자료가 부족한 항목은 "(자료 부족)" 명시

        [근거 스니펫]
        {snippets}
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Research synthesizer prompt ready. vars=%s", pt.input_variables)
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# PPTX planner (§13-4)
# ─────────────────────────────────────────────────────────────────────────────

def get_pptx_planner_prompt() -> ChatPromptTemplate:
    """Markdown 보고서 → SlideDeckSpec 변환용 프롬프트 (§13-9 안정화).

    §13-9 변경 (2026-05-09):
      - PromptTemplate (단일 human) → ChatPromptTemplate (system + human) 분리
      - 강제 규칙은 system 으로 이동 (gpt-4o system 준수율 활용)
      - few-shot 예시 1건을 system 안 fenced block 으로 추가
        (langchain with_structured_output 와 호환 위해 message pair 가 아닌 텍스트 예시)

    헤딩 깊이 → layout_id 매핑은 결정론적 (LLM 자율 결정 회피).
    템플릿 layout (templates/agency_default.pptx, §13-1 / v3 close):
      - 0 = TITLE          (CENTER_TITLE + SUBTITLE)
      - 1 = TITLE_CONTENT  (TITLE + OBJECT)
      - 2 = SECTION_HEADER (placeholder 3개: 번호/제목/부제)
    """
    system_text = _tmpl(
        """
        역할: 광고 에이전시 발표용 PowerPoint 슬라이드 deck 기획자.
        Markdown 보고서를 입력받아 SlideDeckSpec 으로 변환한다.

        [입력 구조 사전 측정 — 슬라이드 수 결정]
        이 입력 md 에는 ## 챕터 {n_h2_chapters}개, ### 섹션 {n_h3_sections}개가 있다.
        따라서 출력 deck 의 슬라이드 구성은 **정확히** 다음과 같다:
          - TITLE 슬라이드 1장
          - SECTION_HEADER 슬라이드 {n_h2_chapters}장 (## 챕터 1:1 매핑)
          - TITLE_CONTENT 슬라이드 {n_h3_sections}장 (### 섹션 1:1 매핑)
        총 슬라이드 수 = **정확히 {n_total_slides}장**.
        압축(여러 ### 합치기), 분할(하나의 ###을 여러 슬라이드로 쪼개기), 생략(### 빼기),
        추가(없는 슬라이드 만들기) 모두 **금지**. 슬라이드 수가 {n_total_slides} 이외면 위반.

        [절대 강제 규칙 — 위반 금지]
        1. **출력 언어는 모두 한국어**. 입력 md 가 영어 단어·고유명사를 포함해도
           슬라이드 제목·본문·bullets·표 헤더·셀은 모두 한국어로 작성.
           고유명사 (브랜드·인명·약어) 는 원문 표기 유지 가능 (예: "Venfobel", "OTC").
        2. **Markdown 표는 반드시 TableSpec 으로 보존**. `| col | col |` 형태가 입력에
           있으면 layout_id=1 + table 슬라이드로 추출. **임의 압축·bullet 변환 금지**.
           (참고: 매핑 규칙상 표가 등장하는 ### 섹션이 곧 그 슬라이드의 table.)
        3. **출처 정보는 반드시 슬라이드 노트(`notes`)로 이동**. 본문(bullets/body/table 셀)에
           `[파일명]`, `[^N]`, URL, "출처:" 등 인용 표시가 있으면 **삭제하지 말고 추출하여**
           해당 슬라이드의 notes 필드로 옮긴다. notes 형식 예: "출처: [종근당_팩트북.pdf] / [^1] 매출 통계".
           본문에 마커가 0개이고 동시에 노트도 비어있으면 위반 — 노트로 옮겼는지 확인.

        [헤딩 → layout_id 결정론 매핑]
        1. 첫 슬라이드는 반드시 layout_id=0 (TITLE):
           - title = topic_title (한국어)
           - body = 부제 또는 생성일 (예: "2026-05-08 / RAG Writer")
        2. `## N.` 헤딩(챕터) 등장 시 layout_id=2 (SECTION_HEADER) 슬라이드 1장 추가:
           - title = `## N.` 줄의 챕터 제목. **영어면 자연스러운 한국어로 번역** (의미 보존).
             예: "Executive Summary" → "핵심 요약", "Market Trends" → "시장 동향".
             고유명사·브랜드명만 원문 유지.
        3. `### N.M.` 헤딩은 **각각 정확히 1개의 layout_id=1 (TITLE_CONTENT) 슬라이드에 1:1 매핑**:
           - 입력 md 의 ### 헤딩 {n_h3_sections}개 → 본문 슬라이드 **정확히 {n_h3_sections}개**.
           - **여러 ### 헤딩을 한 슬라이드로 합치지 말 것** — 압축 합병 금지.
           - **하나의 ### 본문을 여러 슬라이드로 쪼개지 말 것** — 분할 금지.
           - 본문이 길면 핵심만 한국어로 요약 (bullets 6개 이내, body 200자 이내, 또는 표) —
             분량을 줄여서 한 슬라이드에 맞추되 슬라이드 개수를 늘리지 말 것.
           - title = 섹션 제목 (한국어, 영어면 번역. 없으면 의미 있는 한국어 한 줄).
           - bullets / body / table 중 하나 사용.

        [layout_id=1 OBJECT 우선순위]
        - 마크다운 표가 입력에 있으면 → **table 필수** (강제 규칙 2)
        - 표 없고 짧은 항목 3~6개 추출 가능 → bullets
        - 단락 본문만 있어 bullet 분해 부적절 → body (200자 이내)

        [압축 규칙]
        - **압축은 한 슬라이드 안에서만** (본문 분량을 핵심만 요약). 슬라이드 개수 변경 금지.
          여러 ### 헤딩을 한 슬라이드로 합치는 것도, 하나의 ### 을 여러 슬라이드로 쪼개는 것도 금지.
        - bullets 3~8개, 항목당 150자 이내.
        - body 400자 이내.
        - 원문 그대로 복사 금지 — 핵심만 한국어로 요약 (단 아래 정보 보존 우선순위 준수).

        [정보 보존 우선순위 — 압축 시 살릴 내용 결정 기준]
        1. **수치·정량 데이터** (예: "58%", "800억 원", "1,754 GRPs", "2위"): 최우선 보존.
        2. **고유명사·브랜드명·약어** (예: "벤포벨S", "아로나민", "메코발라민", "UDCA", "OTC"): 원문 표기 유지.
        3. **md 의 `**KEY**: 설명` 패턴은 KEY 와 설명 둘 다 보존**:
           - md: `- **만성피로 인식**: 3040 직장인 중 상당수가 만성피로를 인식하고 있으며, ...`
           - 슬라이드 bullet 출력 = "만성피로 인식: 3040 직장인 중 상당수가 만성피로 인식, 건강 관리 주요 이슈"
           - **키워드만 추출 금지** (= "만성피로 인식" 만 출력하지 말 것). 설명문은 압축하되 의미 있는 문장 1개로 보존.
        4. **단락(평문) 본문**: 핵심 1~2 문장으로 압축 + body 또는 bullets 3~5개로 분해. 단어/구만 뽑지 말 것.
        5. 후순위 (생략 가능): 부사·접속사·중복 표현, 정성적 일반화 ("효과적입니다", "중요합니다").

        [layout_hint]
        - v1 에서는 항상 None.

        [Few-shot 예시 — 표 보존 + 출처 노트 분리]
        ```
        입력 Markdown (### 섹션 1개):
          ### 1.1 경쟁 제품 매출 동향

          | 브랜드 | 2024 매출(억원) | YoY |
          |---|---|---|
          | 벤포벨 | 100 | +5% |
          | 임팩타민 | 80 | -2% |
          | 아로나민 | 120 | +8% |

          [종근당_팩트북.pdf]
          [^1]: 2024 약국 매출 통계  https://example.com/report.pdf

        기대 SlideSpec (정확히 1슬라이드 — 표 보존 + 출처 노트로 이동):
          {{
            "layout_id": 1,
            "title": "경쟁 제품 매출 동향 (2024)",
            "table": {{
              "header": ["브랜드", "2024 매출(억원)", "YoY"],
              "rows": [
                ["벤포벨", "100", "+5%"],
                ["임팩타민", "80", "-2%"],
                ["아로나민", "120", "+8%"]
              ]
            }},
            "bullets": null,
            "body": null,
            "notes": "출처: [종근당_팩트북.pdf] / [^1] 2024 약국 매출 통계 https://example.com/report.pdf"
          }}
        ```
        핵심:
        - ### 1개 → 슬라이드 정확히 1개 (분할·합병 X). 매핑 규칙 3 준수.
        - 표를 bullets 로 압축하지 않음 (강제 규칙 2).
        - `[종근당_팩트북.pdf]`, `[^1]`, URL `https://...` — 본문(table 셀)에서 제거하고 **모두 notes 로 이동**
          (강제 규칙 3 — 삭제 X, 이동만). 노트가 비어있으면 위반.
        - 표 헤더·셀 모두 한국어 (강제 규칙 1).
        ```

        [Few-shot 예시 2 — bullet 압축 보존 패턴 (KEY + 설명 둘 다 살림)]
        ```
        입력 Markdown (### 섹션 1개):
          ### 4.4 실행방안

          1. **차별화된 메시지 개발**: 벤포벨S의 고유한 활성형 비타민 B1의 효능을 강조하는 메시지를 개발하여 소비자에게 명확한 가치를 전달합니다.
          2. **타겟 마케팅 강화**: 3040 직장인과 같은 주요 소비자 그룹을 대상으로 한 맞춤형 마케팅 전략을 통해 브랜드 인지도를 강화합니다.
          3. **다채널 광고 캠페인**: TV, 온라인, 소셜 미디어 등 다양한 채널을 활용하여 브랜드 메시지를 일관되게 전달합니다.

        기대 SlideSpec (정확히 1슬라이드 — bullet 의 KEY + 설명 둘 다 보존):
          {{
            "layout_id": 1,
            "title": "벤포벨S 실행방안 — 메시지·타겟·채널 전략",
            "bullets": [
              "차별화된 메시지 개발: 활성형 비타민 B1 효능 강조 메시지로 소비자에게 명확한 가치 전달",
              "타겟 마케팅 강화: 3040 직장인 등 주요 소비자 그룹 대상 맞춤형 마케팅으로 브랜드 인지도 강화",
              "다채널 광고 캠페인: TV·온라인·소셜 미디어 등 다양한 채널 활용으로 브랜드 메시지 일관 전달"
            ],
            "body": null,
            "table": null,
            "notes": ""
          }}
        ```
        핵심:
        - md 의 `**KEY**: 설명` 패턴 → 슬라이드의 `KEY: 압축 설명` 으로 보존. **KEY 만 추출하지 말 것**.
        - 설명은 핵심 명사·동사·수치 위주로 압축 (조사·접속사·중복 표현 생략). 의미 있는 문장 1개 유지.
        - 정보 보존 우선순위 1~3 (수치·고유명사·KEY+설명) 모두 살림.
        """
    )
    human_text = _tmpl(
        """
        다음 Markdown 보고서를 SlideDeckSpec 으로 산출하라.

        slug = {slug}
        topic_title = {topic_title}

        구조:
        - slides 의 첫 항목은 layout_id=0 (TITLE).
        - 이후 ## 챕터 {n_h2_chapters}개와 ### 섹션 {n_h3_sections}개를 순서대로 1:1 매핑.
        - 출력 slides 길이 = 정확히 {n_total_slides} (1 + {n_h2_chapters} + {n_h3_sections}).

        [입력 보고서]
        {md_text}
        """
    )
    pt = ChatPromptTemplate.from_messages([
        ("system", system_text),
        ("human", human_text),
    ])
    logger.debug("PPTX planner prompt ready. vars=%s", pt.input_variables)
    return pt
