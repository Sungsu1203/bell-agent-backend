# agent/export/renderer.py
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Union

from pptx import Presentation
from pptx.util import Cm
from .spec import SlideDeckSpec, SlideSpec, TableSpec


# §13-3 v2 amendment (2026-05-08): 템플릿 재정비 후 placeholder 기반 식별로 전환.
# placeholder 식별 규칙: layout name + top 좌표 기준 (idx 단독 사용 금지 — idx 10/11/12 가
# 다른 layout 에서 DATE/FOOTER/SLIDE_NUMBER 와 충돌하므로 top 좌표가 결정 키).
EMU_PER_CM = 360000

# layout 2 (SECTION_HEADER) placeholder top 좌표 (cm)
SECTION_HEADER_NUMBER_TOP_CM = 5.0     # 챕터 번호 (예: "01")
SECTION_HEADER_TITLE_TOP_CM = 10.5     # 챕터 제목
SECTION_HEADER_SUBTITLE_TOP_CM = 13.0  # 부제 (optional)

# layout 0 (TITLE) 부제 강제 재배치 좌표 — 마스터에서 이미 정렬됐으면 no-op 안전망.
# 4개 모두 명시 필수: left/width 만 set 시 spPr 신설로 top/height master inherit 끊김 → 0 추락.
TITLE_SUBTITLE_LEFT_CM = 2.0
TITLE_SUBTITLE_TOP_CM = 9.09
TITLE_SUBTITLE_WIDTH_CM = 29.87
TITLE_SUBTITLE_HEIGHT_CM = 1.50

# layout 5 ('제목만') 표 그릴 영역 (layout 1 OBJECT 영역과 동일 좌표 — 디자인 일관성).
TABLE_AREA_LEFT_CM = 2.0
TABLE_AREA_TOP_CM = 4.0
TABLE_AREA_WIDTH_CM = 29.87
TABLE_AREA_HEIGHT_CM = 12.5

LAYOUT_TITLE_ONLY = 5  # '제목만' — 표 슬라이드 dispatch 대상


def render_deck(
    spec: SlideDeckSpec,
    *,
    template_path: Union[str, Path],
    out_path: Union[str, Path],
) -> Path:
    """SlideDeckSpec → .pptx 결정론적 렌더 (LLM 호출 0).

    layout_id 분기:
      - 0 (TITLE): idx=0 CENTER_TITLE = title, idx=1 SUBTITLE = body or topic_title
      - 1 (TITLE_CONTENT) + table: layout 5 ('제목만') 으로 dispatch + add_table
      - 1 (TITLE_CONTENT) bullets/body: idx=0 TITLE, idx=1 OBJECT 채움
      - 2 (SECTION_HEADER): placeholder 3개 (top 좌표 식별) — 번호/제목/부제
    """
    template_path = Path(template_path)
    out_path = Path(out_path)
    if not template_path.exists():
        raise FileNotFoundError(f"template_path not found: {template_path}")

    prs = Presentation(str(template_path))
    _clear_template_slides(prs)

    for s in spec.slides:
        if s.layout_id == 1 and s.table:
            # 표 슬라이드 — layout 5 ('제목만') 로 dispatch (placeholder/표 좌표 겹침 회피)
            layout = prs.slide_layouts[LAYOUT_TITLE_ONLY]
            slide = prs.slides.add_slide(layout)
            _render_title_only_with_table(slide, s)
        else:
            layout = prs.slide_layouts[s.layout_id]
            slide = prs.slides.add_slide(layout)
            if s.layout_id == 0:
                _render_title_slide(slide, s, default_subtitle=spec.topic_title)
            elif s.layout_id == 1:
                _render_content_slide(slide, s)
            elif s.layout_id == 2:
                _render_section_header_slide(slide, s)
        if s.notes:
            slide.notes_slide.notes_text_frame.text = s.notes

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    return out_path


def _clear_template_slides(prs) -> None:
    """템플릿에 미리 들어있던 starter slide 삭제 (layout 보존)."""
    sld_id_lst = prs.slides._sldIdLst
    rid_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for sld_id in list(sld_id_lst):
        rid = sld_id.get(rid_attr)
        prs.part.drop_rel(rid)
        sld_id_lst.remove(sld_id)


def _placeholder_by_idx(slide, idx: int):
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx:
            return ph
    return None


def _placeholder_by_top_cm(slide, top_cm: float, *, tol_cm: float = 0.5):
    """top 좌표 ± tol_cm 안에 있는 placeholder 1개 반환. idx 단독 식별 금지(SECTION_HEADER 의
    BODY placeholder idx 10/11/12 가 타 layout 의 DATE/FOOTER/SLIDE_NUMBER 와 충돌)."""
    target = top_cm * EMU_PER_CM
    tol = tol_cm * EMU_PER_CM
    for ph in slide.placeholders:
        try:
            if ph.top is not None and abs(ph.top - target) <= tol:
                return ph
        except Exception:
            continue
    return None


_CHAPTER_NUM_RE = re.compile(r"^\s*(\d+)\.\s*(.+)$")


def _split_chapter_title(title: str) -> tuple[str, str]:
    """`'1. Executive Summary'` → `('01', 'Executive Summary')`. 매칭 안되면 ('', title)."""
    m = _CHAPTER_NUM_RE.match(title or "")
    if not m:
        return "", (title or "").strip()
    n_str, rest = m.group(1), m.group(2).strip()
    return f"{int(n_str):02d}", rest


def _render_title_slide(slide, s: SlideSpec, *, default_subtitle: str) -> None:
    title_ph = _placeholder_by_idx(slide, 0)
    subtitle_ph = _placeholder_by_idx(slide, 1)
    if title_ph is not None:
        title_ph.text = s.title
    if subtitle_ph is not None:
        subtitle_ph.text = s.body or default_subtitle
        # 마스터 부제가 left=4.2cm 어긋난 케이스 대비 강제 재배치 (이미 정렬됐으면 no-op 안전).
        # 4개 좌표 모두 명시 필수 — left/width 만 set 시 master inherit 끊겨 top/h=0 으로 추락.
        subtitle_ph.left = Cm(TITLE_SUBTITLE_LEFT_CM)
        subtitle_ph.top = Cm(TITLE_SUBTITLE_TOP_CM)
        subtitle_ph.width = Cm(TITLE_SUBTITLE_WIDTH_CM)
        subtitle_ph.height = Cm(TITLE_SUBTITLE_HEIGHT_CM)


def _render_content_slide(slide, s: SlideSpec) -> None:
    """layout 1 (TITLE_CONTENT) — bullets > body 만 처리. table 분기는 layout 5 dispatch."""
    title_ph = _placeholder_by_idx(slide, 0)
    object_ph = _placeholder_by_idx(slide, 1)
    if title_ph is not None:
        title_ph.text = s.title
    if object_ph is None:
        return
    if s.bullets:
        _fill_bullets(object_ph, s.bullets)
    elif s.body:
        object_ph.text = s.body


def _fill_bullets(placeholder, bullets) -> None:
    tf = placeholder.text_frame
    tf.clear()
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = b


def _render_title_only_with_table(slide, s: SlideSpec) -> None:
    """layout 5 ('제목만') — 제목 placeholder 만 채우고 표는 별도 add_table 로 그림."""
    title_ph = _placeholder_by_idx(slide, 0)
    if title_ph is not None:
        title_ph.text = s.title
    if not s.table or not s.table.header:
        return
    rows = len(s.table.rows) + 1
    cols = len(s.table.header)
    if cols == 0:
        return
    slide.shapes.add_table(
        rows, cols,
        Cm(TABLE_AREA_LEFT_CM), Cm(TABLE_AREA_TOP_CM),
        Cm(TABLE_AREA_WIDTH_CM), Cm(TABLE_AREA_HEIGHT_CM),
    )
    table = slide.shapes[-1].table
    for c, h in enumerate(s.table.header):
        table.cell(0, c).text = h
    for r, row in enumerate(s.table.rows):
        for c, cell in enumerate(row):
            if c >= cols:
                break
            table.cell(r + 1, c).text = cell


def _render_section_header_slide(slide, s: SlideSpec) -> None:
    """layout 2 — placeholder 3개 (top 좌표 식별):
      - top≈5.0cm  → 챕터 번호 ("01" zero-padded)
      - top≈10.5cm → 챕터 제목 (번호 prefix 제거)
      - top≈13.0cm → 부제 (s.body 또는 빈 문자열로 default text 숨김)
    """
    number_str, clean_title = _split_chapter_title(s.title)

    num_ph = _placeholder_by_top_cm(slide, SECTION_HEADER_NUMBER_TOP_CM)
    title_ph = _placeholder_by_top_cm(slide, SECTION_HEADER_TITLE_TOP_CM)
    subtitle_ph = _placeholder_by_top_cm(slide, SECTION_HEADER_SUBTITLE_TOP_CM)

    if num_ph is not None:
        num_ph.text_frame.text = number_str
    if title_ph is not None:
        title_ph.text_frame.text = clean_title or s.title
    if subtitle_ph is not None:
        # None 이어도 빈 문자열로 채워서 마스터 default text "한 줄 부제 또는 챕터 요약" 숨김.
        subtitle_ph.text_frame.text = (s.body or "")


__all__ = ["render_deck"]
