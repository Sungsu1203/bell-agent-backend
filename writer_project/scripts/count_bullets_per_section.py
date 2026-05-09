# -*- coding: utf-8 -*-
"""§13-9 Round 3 사전 위험 측정 — md 의 각 ### 섹션 안 bullet 줄 수 분포.

위험 시나리오: bullet 8개 초과 섹션이 있으면 (A) ### 1:1 분할 금지 강제 시
시각적 한계 침범 가능. 발견 시 §13-9 close 후 §13-11 분량 적정화에서 처리.
"""
from __future__ import annotations
import argparse
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

H2_RE = re.compile(r"^##\s+(.+)$")
H3_RE = re.compile(r"^###\s+(.+)$")
H4PLUS_RE = re.compile(r"^####+\s")
BULLET_RE = re.compile(r"^\s*-\s+\S")  # `- ` 또는 `  - ` (들여쓰기 포함)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("md_path")
    args = p.parse_args()

    text = Path(args.md_path).read_text(encoding="utf-8")
    lines = text.splitlines()

    sections: list[dict] = []
    cur_h3: dict | None = None
    cur_h2: str = ""

    for ln_no, line in enumerate(lines, start=1):
        h2 = H2_RE.match(line)
        h3 = H3_RE.match(line)
        if h2:
            if cur_h3:
                sections.append(cur_h3)
                cur_h3 = None
            cur_h2 = h2.group(1).strip()
            continue
        if h3:
            if cur_h3:
                sections.append(cur_h3)
            cur_h3 = {
                "h2": cur_h2,
                "h3": h3.group(1).strip(),
                "line": ln_no,
                "bullets": 0,
                "lines_text": 0,
            }
            continue
        if cur_h3 is None:
            continue
        if H4PLUS_RE.match(line):
            continue  # h4 이상은 통계 외 (단순 카운트)
        if BULLET_RE.match(line):
            cur_h3["bullets"] += 1
            cur_h3["lines_text"] += 1
        elif line.strip():
            cur_h3["lines_text"] += 1

    if cur_h3:
        sections.append(cur_h3)

    print(f"=== {args.md_path} (### 섹션 {len(sections)}개) ===")
    print(f"{'idx':<4} {'h2':<25} {'h3':<35} {'bullets':>8} {'lines':>6}")
    over_8 = []
    over_6 = []
    for i, s in enumerate(sections, start=1):
        flag = ""
        if s["bullets"] > 8:
            flag = " ⚠ >8"
            over_8.append(s)
        elif s["bullets"] > 6:
            flag = " ! >6"
            over_6.append(s)
        print(f"{i:<4} {s['h2'][:24]:<25} {s['h3'][:34]:<35} "
              f"{s['bullets']:>8} {s['lines_text']:>6}{flag}")

    print(f"\n요약:")
    print(f"  총 ### 섹션: {len(sections)}")
    print(f"  bullet >8 (시각 위험): {len(over_8)}")
    print(f"  bullet 7~8 (경계): {len(over_6)}")
    print(f"  최대 bullet: {max((s['bullets'] for s in sections), default=0)}")
    print(f"  bullet 합계: {sum(s['bullets'] for s in sections)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
