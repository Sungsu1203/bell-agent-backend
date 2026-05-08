# -*- coding: utf-8 -*-
"""§13 fix - SLIDE_NUMBER placeholder XML 구조 확인 (auto-field 보존 여부)."""
from __future__ import annotations
import io
import sys
from pathlib import Path
from lxml import etree

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn

TEMPLATE = Path("templates/agency_default.pptx")


def main() -> None:
    prs = Presentation(str(TEMPLATE))
    for layout_idx in (0, 1, 5):
        layout = prs.slide_layouts[layout_idx]
        print(f"\n=== layout[{layout_idx}] name={layout.name!r} — SLIDE_NUMBER placeholder XML ===")
        for ph in layout.placeholders:
            try:
                # SLIDE_NUMBER type id == 13
                if int(ph.placeholder_format.type) == 13:
                    xml = etree.tostring(ph._element, pretty_print=True).decode("utf-8")
                    print(xml)
                    break
            except Exception:
                continue


if __name__ == "__main__":
    main()
