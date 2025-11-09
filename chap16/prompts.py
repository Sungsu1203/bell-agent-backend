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

            너는 **보고서 기획자**다. 이전 대화와 참고자료를 바탕으로
            **실무 보고서 개요**를 작성하라.

            권장 구조(필요 시 조정):
            1. Executive Summary
            2. Background & Objectives
            3. Scope & Methodology
            4. Key Findings (데이터/사례 중심)
            5. Analysis & Insights
            6. Recommendations (Action Items)
            7. Risks & Mitigations
            8. Implementation Plan & Timeline
            9. Appendix (Data, Glossary, References)

            {_H2_ONLY_RULES}

            --------------------------------
            - 이전 대화: {{messages}}
            - 기존 개요: {{outline}}
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
        1) 각 쿼리마다 다음 바이어스를 괄호로 그대로 덧붙인다:
            (site:mfds.go.kr OR site:khidi.or.kr OR site:hira.or.kr OR site:kosis.kr OR site:index.go.kr OR site:kpanet.or.kr OR site:dailypharm.com OR site:medipana.com)
        2) 각 쿼리마다 다음 금칙을 그대로 덧붙인다:
            -site:facebook.com -site:instagram.com -site:myfair.co -event -exhibition -tickets -행사 -티켓 -광고
        3) 사용자가 행사/티켓/SNS 자체를 명시적으로 요청한 경우에만 해당 쿼리 1개에 한해 금칙을 생략해도 된다.
        4) 쿼리는 **구체적 개념 + 시점(연도 또는 기간 예: 2024~2025)** 을 포함한다.
        5) 같은 의미의 중복 쿼리는 생성하지 말고, **정책/시장규모/공급망/기술동향/리스크** 등으로 영역을 분리한다.

        [예시 변환]
        - 원본: 한국 전기차 배터리 산업 현황 2025
            최종: 한국 전기차 배터리 산업 현황 2025 (site:mfds.go.kr OR site:kosis.kr OR site:dailypharm.com) -site:facebook.com -site:instagram.com -site:myfair.co -event -exhibition -tickets -행사 -티켓 -광고

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
        - 문서의 첫 줄은 반드시 타깃 헤딩 한 줄: `## <번호>. <제목>`
        - 상위 헤딩(##)은 **딱 한 번**만 사용. 소제목은 `###` 이하로만 사용
        - 불필요한 서문/메타 설명 없이 **본문만** 출력
        - 금지: 전체 목차 재출력, 결론만 출력, 근거 없는 주장, 표제만 나열

        [작성 규칙]
        - 대상: 의사결정자/실무자
        - 구성: 배경/핵심 요점/근거(데이터·사례)/시사점
        - 표/목록: Markdown
        - 길이: 800~1,500 단어(요약은 400~800)
        - 마지막: **Actionable Recommendations** 3~5개
                   제안은 **'벤포벨' 브랜드의 경쟁 우위 확보**나 **활성 비타민 시장 공략**에 **직접적으로** 관련되어야 하며, **일반적인 경영/생산 조언은 피한다.**
        - 인용은 재서술, 출처명은 대괄호(예: [DailyPharm])
                 
        [특수 규칙: Q&A 모드]
        - 만약 {target_title}이 "Q&A:"로 시작한다면, 보고서 스타일을 무시하고
        - 사용자 질문에 대해 참고 자료({references})를 활용한 간결하고 직접적인 답변만 제공할 것.
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
        역할: Research Analyst. 아래 목표를 달성하기 위해 **정밀 검색 질의 5~8개**만 작성한다.

        - 목표: {objective}
        - 기존 레퍼런스 개요: {references}

        엄격한 작성 규칙:
        1) **반드시 한국어**로만 작성한다. 영어 단어/문장/관용 템플릿/라벨 금지.
            (예: (untitled), draft, v1 같은 접두 라벨 **금지**)
        2) 각 질의는 **주제어(정확히 '{topic_title}')**와 **국내 맥락 키워드(한국|국내|대한민국 중 1+)**를 반드시 포함한다.
        3) **주제 범위 확장 금지**: 거시·범산업·글로벌 포괄 문구(예: '글로벌 시장 전망', '산업 전반 트렌드') 사용 금지.
        4) 다음 **영어 템플릿 문구**는 절대 포함하지 않는다(완전 금지):
            global market growth forecast, industry trends and market size projections, emerging markets and growth opportunities,
            market analysis and future growth potential, sector-specific growth rate predictions, economic factors influencing market expansion,
            competitive landscape and market share analysis
        5) **권위 도메인 우선**으로 도메인 필터를 포함한다(가능하면 아래 조합 활용):
            (site:mfds.go.kr OR site:khidi.or.kr OR site:hira.or.kr OR site:kosis.kr OR site:index.go.kr OR site:kpanet.or.kr OR site:go.kr OR site:re.kr OR site:dailypharm.com OR site:medipana.com)
            **주의:** `site:go.kr` 또는 `site:re.kr`는 **약학/보건/통계 관련성이 매우 높을 때만** 사용한다. 일반적인 시청/지자체/농축산 분야 키워드 검색 시에는 사용하지 않는다.
            **기본 네거티브(전역 적용)**는 최소화한다: `-행사 -세미나 -박람회`
            **네거티브 키워드 사용 유도:** 네이버에서 불필요한 쇼핑/개인 블로그/체험단 결과를 차단하기 위해 **`-체험단 -블로그 -가격비교`**와 같은 네거티브 키워드를 **선택적으로** 포함하도록 한다.
        6) **최신성 확보**: 가능하면 **연도 범위**를 포함한다(예: 2023..2025 또는 2024..2025).
            - 연도는 4자리만 사용(‘24’처럼 축약 금지), 중복 연도·불필요한 텍스트 금지.
        7) **정보 의도 분화**: 아래 중 최소 4가지를 고르게 반영하며, **객관적 정보**를 검색할 때는 쿼리 끝에 **'뉴스', '자료', '통계', '보고서'**와 같은 키워드를 추가하여 의도를 명확히 한다.
            - 시장규모/판매액/점유율 (예: 시장규모, 판매액, 매출, 점유율, CAGR, 성장률)
            - 분류/품목/성분 (예: OTC, 일반의약품, 제산제, 위장약, H2RA, PPI, 제품/브랜드, 벤포티아민)
            - 유통/가격/규제 (예: 약국외판매, 안전상비의약품, 허가/신고, 급여/비급여, 가격)
            - 경쟁/채널/소비행태 (예: 상위 브랜드, 유통채널, 소비자 조사)
            - 리스크/정책/가이드라인 (예: 리스크, 규제 변화, 가이드/고시)
            ※ {references}에 **브랜드/회사/성분 고유명사**가 보이면 해당 명사를 1~2개 질의에 포함한다(예: 종근당, 벤포벨, 벤포티아민 등).
        8) **정밀 연산자 사용:**
            - **네이버 연산자**(`"`, `+`, `-`, `|`)를 적극 활용하여 쿼리 정확도를 높인다.
            - **구문 검색:** **`"핵심 키워드"`** (큰따옴표)로 정확히 일치하는 문구를 검색한다. (예: `"벤포벨 시장 점유율"`)
            - **필수 포함:** **`+필수단어`** (플러스 기호와 단어 사이 공백 없음)를 사용하여 **핵심 브랜드/성분/시점**을 강제한다. (예: `+종근당 +2025`)
            - **제외:** **`-제외단어`** (마이너스 기호와 단어 사이 공백 없음)를 사용하여 광고/노이즈를 제거한다. (예: `-체험기 -가격비교`)
            - **금지:** Google식 연산자(`site:`, `filetype:`, `AND/OR/NOT`), 와일드카드, 중첩 괄호 사용은 엄격히 금지한다.
            - **OR 연산**은 네이버 친화적인 **`|`** 기호를 사용한다 (예: `(벤포벨 | 메가비타)`)
        9) **중복 억제/길이 제한**:
            - 의미가 겹치는 질의 금지(단어만 바꾼 변형 금지).
            - 각 질의는 60~160자 이내로 간결하게 작성.
        10) **출력 형식**: 부호/번호/설명/머리말 없이, **한 줄에 쿼리 1개만**. 여분 텍스트 금지.
                    
        # 예시(참고용, 출력에 포함 금지):
        # 한국 피로회복 비타민 시장규모 (2023 OR 2024 OR 2025)
        # 벤포티아민 성분 품목/허가 현황 site:mfds.go.kr
        # 벤포벨 매출/점유 관련 공시/보도자료 (2024 OR 2025) site:konex.or.kr OR site:dart.fss.or.kr

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
        목표: 아래 '근거 스니펫'을 바탕으로 **라운드별 요약(Findings)** 작성.
        - 형식: 1) 핵심 요점(3~6불릿) 2) 근거 요약 3) 함의/추가 조사 포인트(2~4)
        - 과장 금지, 간결하게. 소스명은 대괄호로만 표기.
        근거 스니펫:
        {snippets}
        """
    )
    pt = PromptTemplate.from_template(tmpl)
    logger.debug("Research synthesizer prompt ready. vars=%s", pt.input_variables)
    return pt
