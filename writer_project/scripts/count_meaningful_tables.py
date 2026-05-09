# -*- coding: utf-8 -*-
"""§13-9 metric (g) — Markdown 보고서의 '유의미한 표' 개수 X' 측정.

유의미한 표 정의:
  - 2행 이상 (헤더 + 데이터 행 ≥1)
  - 2열 이상
  - 데이터 행이 모두 빈 셀이 아님

Markdown 표 구조 (GFM):
  | header1 | header2 |
  |---------|---------|
  | cell    | cell    |
  | cell    | cell    |

판별 절차:
  1. `^\\s*\\|.*\\|\\s*$` 패턴이 연속된 줄 블록 추출
  2. 두 번째 줄이 `^\\s*\\|[\\s\\-:|]*\\|\\s*$` (separator) 인지 확인
  3. 헤더(1줄) + separator(1줄) + 데이터(≥1줄) 인지 확인
  4. 컬럼 수 ≥ 2 인지 확인 (헤더 기준)
  5. 데이터 행에 비어있지 않은 셀이 1개 이상 있는지 확인
"""
from __future__ import annotations
import argparse
import io
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
SEP_RE = re.compile(r"^\s*\|[\s\-:|]*\|\s*$")


def split_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def find_meaningful_tables(text: str) -> list[dict]:
    lines = text.splitlines()
    tables: list[dict] = []
    i = 0
    n = len(lines)
    while i < n:
        if not ROW_RE.match(lines[i]):
            i += 1
            continue
        header_line = lines[i]
        if i + 1 >= n or not SEP_RE.match(lines[i + 1]):
            i += 1
            continue
        # 데이터 행 수집
        data_start = i + 2
        j = data_start
        while j < n and ROW_RE.match(lines[j]) and not SEP_RE.match(lines[j]):
            j += 1
        n_data_rows = j - data_start
        header_cells = split_cells(header_line)
        n_cols = len(header_cells)
        # 데이터 행 비어있지 않은지
        has_nonempty = False
        for k in range(data_start, j):
            cells = split_cells(lines[k])
            if any(c for c in cells):
                has_nonempty = True
                break
        meaningful = (n_data_rows >= 1) and (n_cols >= 2) and has_nonempty
        tables.append({
            "line": i + 1,
            "header": header_cells,
            "n_cols": n_cols,
            "n_data_rows": n_data_rows,
            "meaningful": meaningful,
        })
        i = max(j, i + 1)
    return tables


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("md_path")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    text = Path(args.md_path).read_text(encoding="utf-8")
    tables = find_meaningful_tables(text)
    meaningful = [t for t in tables if t["meaningful"]]
    print(f"=== {args.md_path} ({len(text):,} chars) ===")
    print(f"전체 표 후보: {len(tables)}")
    print(f"유의미한 표 (X'): {len(meaningful)}")
    if args.verbose:
        for k, t in enumerate(tables):
            tag = "OK" if t["meaningful"] else "SKIP"
            print(f"  [{tag}] line {t['line']:>5}  cols={t['n_cols']} data_rows={t['n_data_rows']}  "
                  f"header={t['header'][:3]}{'...' if len(t['header']) > 3 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
