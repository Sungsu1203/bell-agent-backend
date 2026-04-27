from __future__ import annotations
from typing import Literal, TypeAlias
from langchain_core.prompts import PromptTemplate

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

        [예시 변환]
        - 원본: 국내 프리미엄 반려동물 사료 시장 전망 2025
            최종: 국내 프리미엄 반려동물 사료 시장 전망 2025 -site:facebook.com -site:instagram.com -행사 -티켓 -광고

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
        - 수치·연도·점유율 등 **확정 수치**는 참고자료에 있을 때만 인용(출처명 표기: [DailyPharm], [종근당_팩트북.pdf] 등)
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
        - 인용은 재서술, 출처명은 대괄호(예: [DailyPharm]), 수치/통계에는 반드시 출처를 표기할 것.

        [참고 자료 활용 규칙]
        - {topic_title}과 직접 관련 없는 출처는 인용하지 말 것
        - 해외의 무관한 시장, 무관한 제품군 출처는 배제할 것
        - 수치 인용 시 반드시 본문에 출처 표기할 것

        [Executive Summary 규칙 - {target_title}에 Executive Summary가 포함된 경우]
        - 시장 규모 및 성장률 수치 반드시 포함
        - 주요 경쟁 브랜드 현황 언급
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
