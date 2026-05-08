# agent/export/spec.py
from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class TableSpec(BaseModel):
    """슬라이드에 삽입할 테이블 정의 (Markdown table → 구조화)."""
    header: List[str] = Field(
        ...,
        description=(
            "테이블 헤더(첫 행) 셀 텍스트 리스트. "
            "Markdown 표의 `| col1 | col2 |` 부분을 분해한 결과."
        ),
    )
    rows: List[List[str]] = Field(
        ...,
        description=(
            "데이터 행. 각 row 길이는 header 와 동일해야 함. "
            "셀에 줄바꿈/긴 문장이 있어도 단일 문자열로 유지(렌더러가 폰트 축소 대응)."
        ),
    )


class SlideSpec(BaseModel):
    """슬라이드 1장의 결정론적 명세 — planner LLM 의 structured output target.

    layout_id 는 Literal[0,1,2] 로 좁혀 LLM hallucination(layout 3~10 잘못 선택) 방지.
    템플릿 매핑 (templates/agency_default.pptx, §13-1 close 결과):
      - 0 = TITLE          (CENTER_TITLE + SUBTITLE)
      - 1 = TITLE_CONTENT  (TITLE + OBJECT)
      - 2 = SECTION_HEADER (placeholder 0개 — renderer 가 textbox 직접 주입)
    """
    layout_id: Literal[0, 1, 2] = Field(
        ...,
        description=(
            "슬라이드 레이아웃 ID. 다음 3종만 허용:\n"
            "- 0: TITLE — 보고서 첫 표지(제목+부제). deck 에서 1번만 사용 권장.\n"
            "- 1: TITLE_CONTENT — 일반 본문 슬라이드(섹션 제목 + 본문/bullets/표).\n"
            "- 2: SECTION_HEADER — 챕터 구획 슬라이드(## N. 챕터 시작 시 1장)."
        ),
    )
    title: str = Field(
        ...,
        description=(
            "슬라이드 제목. layout_id 에 따른 의미:\n"
            "- 0(TITLE): 보고서 전체 제목(예: 'Venfobel-Vitamin 광고 기획 리포트')\n"
            "- 1(TITLE_CONTENT): 섹션 제목(예: '2.2 경쟁 제품 매출 동향')\n"
            "- 2(SECTION_HEADER): 챕터 제목(예: '2. 시장 환경 및 규제')"
        ),
    )
    bullets: List[str] = Field(
        default_factory=list,
        description=(
            "본문 bullet 텍스트 리스트. layout_id=1 일 때만 의미 있음. "
            "각 항목은 한 줄(과도한 줄바꿈 금지). 빈 리스트면 body 또는 table 사용. "
            "권장 길이: 슬라이드 1장당 3~6개, 항목당 80자 이내."
        ),
    )
    body: Optional[str] = Field(
        default=None,
        description=(
            "단락 본문(bullets 대안). layout_id=1 의 OBJECT placeholder 에 주입. "
            "bullets 와 body 가 모두 있으면 bullets 우선. layout_id=0 의 SUBTITLE 로도 사용."
        ),
    )
    table: Optional[TableSpec] = Field(
        default=None,
        description=(
            "표 데이터. layout_id=1 에서 bullets/body 대신 테이블을 그릴 때 지정. "
            "지정 시 renderer 는 OBJECT 영역에 add_table 로 그림."
        ),
    )
    notes: Optional[str] = Field(
        default=None,
        description=(
            "발표자 노트(slide notes). 출처 인용·footnote·보조 설명을 여기에 배치. "
            "본문에 노출되지 않으며 .pptx notes 영역에 기록."
        ),
    )
    layout_hint: Optional[str] = Field(
        default=None,
        description=(
            "(v2 reserve) layout_id 외 추가 힌트. "
            "v1 에서는 미사용(None). v2 (Gemini A/B) 에서 'compare'/'caption' 등 활용 예정."
        ),
    )


class SlideDeckSpec(BaseModel):
    """전체 deck 명세 — planner 의 최종 산출물."""
    slug: str = Field(
        ...,
        description=(
            "토픽 슬러그(예: 'venfobel-vitamin'). reports/<slug>/ 디렉토리명과 일치. "
            "출력 .pptx 파일명·메타에 사용."
        ),
    )
    topic_title: str = Field(
        ...,
        description=(
            "보고서 한국어 제목(예: '벤포벨-비타민 광고 기획 리포트'). "
            "첫 슬라이드(layout_id=0)의 CENTER_TITLE 기본값."
        ),
    )
    slides: List[SlideSpec] = Field(
        ...,
        description=(
            "슬라이드 순서 리스트. 첫 항목은 layout_id=0(TITLE) 권장. "
            "이후 챕터 시작마다 layout_id=2(SECTION_HEADER), 본문은 layout_id=1(TITLE_CONTENT)."
        ),
    )


__all__ = ["TableSpec", "SlideSpec", "SlideDeckSpec"]
