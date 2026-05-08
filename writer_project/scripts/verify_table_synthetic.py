# -*- coding: utf-8 -*-
"""§13-10 verification — 합성 spec 으로 표 스타일 적용 동작 빠른 확인 (LLM 호출 0)."""
from __future__ import annotations
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from agent.export.renderer import render_deck
from agent.export.spec import SlideDeckSpec, SlideSpec, TableSpec

TEMPLATE = Path("templates/agency_default.pptx")


def main() -> None:
    # 케이스 1: 일반 표 (4행 3열, 텍스트 길이 다양)
    spec_normal = SlideDeckSpec(
        slug="table_synth_normal",
        topic_title="§13-10 표 스타일 검증 (4행 3열)",
        slides=[
            SlideSpec(layout_id=1, title="브랜드별 매출 (2024)",
                      table=TableSpec(
                          header=["브랜드", "매출(억원)", "전년 대비 매출 동향 및 분석"],
                          rows=[
                              ["벤포벨", "100", "+5% 성장, 약국 채널 견조"],
                              ["임팩타민", "80", "-2% 감소, 시장 경쟁 격화"],
                              ["아로나민", "120", "+8% 성장, 온라인 채널 확대"],
                          ],
                      )),
        ],
    )
    out1 = Path("reports/_cli_test/table_synth_normal.pptx")
    render_deck(spec_normal, template_path=TEMPLATE, out_path=out1)
    print(f"[ok] {out1} ({out1.stat().st_size:,} B)")

    # 케이스 2: 큰 표 (10행 4열) — fallback 폰트 트리거
    rows_big = [[f"항목{i}", f"카테고리{i%3}", f"값{i*10}", f"비고텍스트 {i}번 항목 메모"]
                for i in range(10)]
    spec_big = SlideDeckSpec(
        slug="table_synth_big",
        topic_title="§13-10 큰 표 fallback 검증 (10행 4열)",
        slides=[
            SlideSpec(layout_id=1, title="대량 항목 표 (10행)",
                      table=TableSpec(
                          header=["항목", "카테고리", "값", "비고"],
                          rows=rows_big,
                      )),
        ],
    )
    out2 = Path("reports/_cli_test/table_synth_big.pptx")
    render_deck(spec_big, template_path=TEMPLATE, out_path=out2)
    print(f"[ok] {out2} ({out2.stat().st_size:,} B)")


if __name__ == "__main__":
    main()
