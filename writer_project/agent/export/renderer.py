# agent/export/renderer.py
from __future__ import annotations
from pathlib import Path
from typing import Union
from pptx import Presentation
from pptx.util import Pt
from .spec import SlideDeckSpec, SlideSpec, TableSpec


# §13-1 inspection 결과: template layout[2] 의 TextBox 7 (챕터 제목 슬롯) 좌표.
# 첫 시도 위치 — 사용자 피드백 받아 §13-3 후속 조정.
SECTION_HEADER_TITLE_BOX = (720000, 3779999, 9000000, 646331)  # (left, top, width, height) EMU


def render_deck(
    spec: SlideDeckSpec,
    *,
    template_path: Union[str, Path],
    out_path: Union[str, Path],
) -> Path:
    """SlideDeckSpec → .pptx 결정론적 렌더 (LLM 호출 0).

    layout_id 분기:
      - 0 (TITLE): idx=0 CENTER_TITLE = title, idx=1 SUBTITLE = body or topic_title
      - 1 (TITLE_CONTENT): idx=0 TITLE = title, idx=1 OBJECT = bullets > body > table
      - 2 (SECTION_HEADER): placeholder 0개 → add_textbox 로 TextBox 7 좌표에 title 주입
    """
    template_path = Path(template_path)
    out_path = Path(out_path)
    if not template_path.exists():
        raise FileNotFoundError(f"template_path not found: {template_path}")

    prs = Presentation(str(template_path))
    _clear_template_slides(prs)

    for s in spec.slides:
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


def _render_title_slide(slide, s: SlideSpec, *, default_subtitle: str) -> None:
    title_ph = _placeholder_by_idx(slide, 0)
    subtitle_ph = _placeholder_by_idx(slide, 1)
    if title_ph is not None:
        title_ph.text = s.title
    if subtitle_ph is not None:
        subtitle_ph.text = s.body or default_subtitle


def _render_content_slide(slide, s: SlideSpec) -> None:
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
    elif s.table:
        _replace_object_with_table(slide, object_ph, s.table)


def _fill_bullets(placeholder, bullets) -> None:
    tf = placeholder.text_frame
    tf.clear()
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = b


def _replace_object_with_table(slide, placeholder, table_spec: TableSpec) -> None:
    left, top = placeholder.left, placeholder.top
    width, height = placeholder.width, placeholder.height
    placeholder.text = ""  # placeholder 텍스트 숨김 (shape 자체는 남음)
    rows = len(table_spec.rows) + 1
    cols = len(table_spec.header)
    if cols == 0:
        return
    table = slide.shapes.add_table(rows, cols, left, top, width, height).table
    for c, h in enumerate(table_spec.header):
        table.cell(0, c).text = h
    for r, row in enumerate(table_spec.rows):
        for c, cell in enumerate(row):
            if c >= cols:
                break
            table.cell(r + 1, c).text = cell


def _render_section_header_slide(slide, s: SlideSpec) -> None:
    left, top, width, height = SECTION_HEADER_TITLE_BOX
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.text = s.title
    p = tf.paragraphs[0]
    if p.runs:
        run = p.runs[0]
        run.font.size = Pt(36)
        run.font.bold = True


__all__ = ["render_deck"]
