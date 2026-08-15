# prompts_research.py — §research-1 리서치 리포트 프롬프트 (R41 신설)
"""심층 리서치 리포트 전용 프롬프트.

기존 `prompts.py` 의 `get_content_strategist_prompt`(report/book) ·
`get_section_writer_prompt`(보고서/Q&A) 는 **광고 기획서·보고서** 성격이며
§ad-track 이 쓰고 있다. 이 모듈은 그것을 건드리지 않고 **별도로** 둔다
(`agent/paper_section_writer.py` 가 논문용으로 분리된 것과 같은 형태).

분기는 이 파일이 하지 않는다 — 노드(`agent/content_strategist.py` ·
`agent/section_writer.py`)가 프리셋 키를 보고 어느 프롬프트를 쓸지 고른다.
`prompts.py:_get_cfg_attr` 에는 ENV 폴백이 없어(R41 Phase 0 §2-c 실측)
프롬프트 파일 안에서는 프리셋 키가 보이지 않기 때문이다.

문안 정본 = `scripts/output/§research-1/PROMPT_DRAFT_R41.md` (챗 작성).
"""
from __future__ import annotations

import logging

from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 아웃라인 (content_strategist 리서치 분기)
#   변수 2개 — {objectives} · {topic_title}
#   호출부가 messages/outline/references 도 함께 넘기지만 PromptTemplate 은
#   여분 키를 무시한다(R41 Phase 1 실측). 누락 키만 KeyError 를 낸다.
# ─────────────────────────────────────────────────────────────────────────────

_RESEARCH_OUTLINE_TMPL = """당신은 리서치 리포트의 목차를 설계한다.

아래 리서치 목표 각각에 대해, **정확히 하나씩** 섹션을 만든다.

리서치 목표:
{objectives}

규칙:
1. 섹션 수는 리서치 목표 수와 정확히 같다. 더 만들지도, 합치지도 않는다.
2. 섹션 순서는 리서치 목표 순서를 따른다.
3. 요약·개요·서론·결론·제언·실행 로드맵·KPI 등 목표에 대응하지 않는 섹션을
   앞이나 뒤에 덧붙이지 않는다.
4. 각 섹션 제목은 그 목표가 무엇을 밝히려는지 드러내되 짧게 쓴다.
   - 목표 문장을 그대로 옮기지 않는다.
   - 한 줄 이내, 문장이 아니라 구(句)로 쓴다.
   - 물음표·마침표·따옴표·괄호를 쓰지 않는다.
5. 출력은 H2 헤딩(`## 제목`)만으로 구성한다. 설명·본문·번호를 붙이지 않는다.

주제: {topic_title}"""


def get_research_outline_prompt() -> PromptTemplate:
    """리서치 리포트 아웃라인 프롬프트 — objective 당 섹션 1개를 강제한다."""
    pt = PromptTemplate.from_template(_RESEARCH_OUTLINE_TMPL)
    logger.debug("Research outline prompt ready. vars=%s", pt.input_variables)
    return pt


# ─────────────────────────────────────────────────────────────────────────────
# 본문 (section_writer 리서치 분기)
#   변수 3개 — {target_title} · {references} · {outline}
#   ⚠️ 문안 초안의 {section_title} 은 실물 변수명 {target_title} 로 맞췄다
#      (agent/section_writer.py 의 chain.invoke 키. PROMPT_DRAFT_R41 §2 「변수 이름 주의」).
#   [R43] 「인용」 절 4행 = prompts.py:524-527 원형 축자 이식(dedent 후 byte 동일).
#      하류 규약이다 — utils/refs.py:357 _MARKER_RE = r"\[\[(\d+)\]\]" 가 그것을 읽어
#      각주(attach_marker_citations)와 .refs.json 사이드카(build_marker_refs_map)를 만든다.
#      ⚠️ 원형이 가리키는 라벨은 「[참고 자료 요약]」이나 이 템플릿의 실물 헤딩은 「## 참고자료」다
#         (R43 §4-2-b 보고분. 원형 무수정 원칙에 따라 그대로 뒀다).
# ─────────────────────────────────────────────────────────────────────────────

_RESEARCH_SECTION_TMPL = """당신은 리서치 리포트의 한 섹션을 쓴다.

이 리포트는 사실을 모아 정리하고, 거기서 무엇이 읽히는지를 밝히는 문서다.
설득하거나 권고하는 문서가 아니다.

## 이 섹션이 다룰 것

제목: {target_title}

## 쓰는 방식

**사실 중심**
- 참고자료에서 확인되는 것만 쓴다.
- 사실을 먼저 쓰고, 그 사실들에서 읽히는 바를 뒤에 쓴다.
- 일반론·배경 설명으로 분량을 채우지 않는다.

**인용**
- 인용은 재서술하고, **본문 인용 표기는 [참고 자료 요약] 항목의 번호를 [[N]] 형식으로만** 사용할 것 (예: [[1]], [[2]]).
- **절대로 [라벨] 형식의 자체 합성 명칭을 만들지 말 것** (예: [Ipsos_보고서], [일반의약품_마케팅_분석] 같이 임의 단축 라벨 금지).
- 절대로 file:// 또는 http:// 로 시작하는 URL을 본문에 직접 삽입하지 말 것.
- [참고 자료 요약] 의 N 이외의 숫자/라벨로 인용을 표기하지 말 것 (footer 매핑 깨짐).
- 참고자료에서 확인되지 않는 수치·연도·기업명·제품명·인용문을 쓰지 않는다.
  기억이나 추론으로 채우지 않는다.
- 참고자료의 내용을 넘어서는 서술이 필요하면, 그것이 자료에 근거하지 않았음을 문장에서 밝힌다.

**자료의 범위**
- 섹션 끝에 이 섹션이 근거한 참고자료의 건수를 적는다.
  자료가 많든 적든 항상 적는다. 예: "이 섹션은 참고자료 3건에 근거한다."
- 그 건수로 다룰 수 있는 범위를 넘어서지 않는다.
  자료 3건으로 전반적 추세를 단정하지 않는다.
- 해당하는 참고자료가 하나도 없으면 "확인된 자료 없음" 이라고 쓰고 그 섹션을 끝낸다.
  자료 없이 본문을 만들어내지 않는다.
- **짧은 섹션은 결함이 아니다. 자료 없이 긴 섹션을 쓰는 것이 결함이다.**

**분량**
- 분량은 확보된 자료의 양에 따른다. 고정 목표가 없다.
- 자료가 적으면 짧게, 많으면 길게 쓴다. 분량을 맞추려 내용을 늘리지 않는다.

**어조**
- 서술 중심으로 쓴다. 단정하지 않는다.
- 자료가 한 방향을 가리키면 그렇게 쓰되, 자료가 갈리면 갈린다고 쓴다.
- 추정은 추정임을 밝힌다. "~로 보인다" 와 "~이다" 를 구분해 쓴다.
- 판단이 필요한 대목에서는 판단의 근거와 한계를 함께 적는다.

**마무리**
- 섹션 끝에 이 섹션에서 읽히는 시사점을 적는다.
- 시사점은 무엇을 하라는 권고가 아니라, 확인된 사실이 무엇을 뜻하는지에 대한 서술이다.

## 참고자료

{references}

## 리포트 전체 목차

{outline}"""


def get_research_section_writer_prompt() -> PromptTemplate:
    """리서치 리포트 본문 프롬프트 — 인용 강제 · 자료 부족 시 명시 · 분량 가변."""
    pt = PromptTemplate.from_template(_RESEARCH_SECTION_TMPL)
    logger.debug("Research section writer prompt ready. vars=%s", pt.input_variables)
    return pt


__all__ = ["get_research_outline_prompt", "get_research_section_writer_prompt"]
