# -*- coding: utf-8 -*-
"""§13-9 metric — n=5 안정성 측정 (출력 언어·표 추출·슬라이드 수 편차).

close 조건:
  - slide_spread = max - min  ≤ 2
  - all_korean = True (모든 슬라이드 제목·본문이 한국어 우세)
  - all_tables_match = True (각 run 의 TableSpec 개수 == X')

출력: 콘솔 보고 + JSON 파일 (logs/stability_<slug>_<timestamp>.json).
"""
from __future__ import annotations
import argparse
import io
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# 출처 마커 패턴 — 본문 침투 시 FAIL, notes 에 ≥1개 있어야 PASS.
URL_RE = re.compile(r"https?://\S+")
FOOTNOTE_RE = re.compile(r"\[\^[^\]]+\]")
FILE_CITE_RE = re.compile(r"\[[^\]]*\.(?:pdf|docx|xlsx|md|html?|txt|csv|hwp)\]", re.IGNORECASE)


def _count_source_markers(text: str) -> int:
    if not text:
        return 0
    return (
        len(URL_RE.findall(text))
        + len(FOOTNOTE_RE.findall(text))
        + len(FILE_CITE_RE.findall(text))
    )

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 부모 디렉토리 import 경로 보장
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.export.planner import plan_deck
from scripts.count_meaningful_tables import find_meaningful_tables


def _korean_ratio(text: str) -> float:
    """텍스트의 한국어 음절 비율 (영문자/한글 음절 중 한글 비율)."""
    if not text:
        return 1.0
    kor = sum(1 for c in text if "가" <= c <= "힯")
    eng = sum(1 for c in text if c.isascii() and c.isalpha())
    total = kor + eng
    if total == 0:
        return 1.0  # 숫자/기호만 있는 경우 — 언어 판정 무의미
    return kor / total


def _detect_lang(deck) -> tuple[str, float]:
    """deck 의 모든 텍스트(제목·body·bullets·table 셀)에 대해 한국어 비율 산출.

    return: ('ko' | 'en' | 'mixed', ratio)
      - ratio ≥ 0.7 → 'ko'
      - ratio ≤ 0.3 → 'en'
      - 그 외 → 'mixed'
    """
    parts: list[str] = []
    for s in deck.slides:
        if s.title:
            parts.append(s.title)
        if s.body:
            parts.append(s.body)
        if s.bullets:
            parts.extend(b for b in s.bullets if b)
        if s.table:
            parts.extend(s.table.header)
            for row in s.table.rows:
                parts.extend(row)
    joined = " ".join(parts)
    ratio = _korean_ratio(joined)
    if ratio >= 0.7:
        lang = "ko"
    elif ratio <= 0.3:
        lang = "en"
    else:
        lang = "mixed"
    return lang, ratio


def _count_tables(deck) -> int:
    return sum(1 for s in deck.slides if s.table is not None)


def _source_marker_locations(deck) -> tuple[int, int]:
    """deck 의 (본문 침투 마커 수, 노트 마커 수) 반환.

    본문 = bullets + body + table header/cell  (출처 마커 0개여야 PASS)
    notes = slide.notes  (입력 md 에 마커 있으면 ≥1개여야 PASS)
    """
    body_n = 0
    notes_n = 0
    for s in deck.slides:
        if s.body:
            body_n += _count_source_markers(s.body)
        if s.bullets:
            for b in s.bullets:
                body_n += _count_source_markers(b)
        if s.table:
            for h in s.table.header:
                body_n += _count_source_markers(h)
            for row in s.table.rows:
                for cell in row:
                    body_n += _count_source_markers(cell)
        if s.notes:
            notes_n += _count_source_markers(s.notes)
    return body_n, notes_n


def measure_run(md_path: Path, *, slug: str, topic_title: str, n: int = 5) -> dict:
    md_text = md_path.read_text(encoding="utf-8")
    pre = find_meaningful_tables(md_text)
    x_prime = sum(1 for t in pre if t["meaningful"])
    md_source_markers = _count_source_markers(md_text)
    print(f"=== 사전 측정 ===")
    print(f"  md: {md_path}  ({len(md_text):,} chars)")
    print(f"  유의미한 표 X' = {x_prime}")
    print(f"  입력 md 출처 마커 (URL+footnote+파일인용): {md_source_markers}")

    runs: list[dict] = []
    for i in range(n):
        t0 = time.monotonic()
        try:
            deck = plan_deck(md_text, slug=slug, topic_title=topic_title)
            lat = time.monotonic() - t0
            slide_count = len(deck.slides)
            lang, ratio = _detect_lang(deck)
            table_count = _count_tables(deck)
            body_n, notes_n = _source_marker_locations(deck)
            entry = {
                "run": i + 1,
                "slide_count": slide_count,
                "table_count": table_count,
                "lang": lang,
                "kor_ratio": round(ratio, 3),
                "src_in_body": body_n,
                "src_in_notes": notes_n,
                "latency_s": round(lat, 2),
                "ok": True,
            }
            print(f"  run {i+1}: slides={slide_count}  tables={table_count}  "
                  f"lang={lang} (kor={ratio:.2f})  src(body={body_n},notes={notes_n})  "
                  f"lat={lat:.1f}s")
        except Exception as err:
            lat = time.monotonic() - t0
            entry = {
                "run": i + 1,
                "ok": False,
                "error_class": type(err).__name__,
                "error_msg": str(err)[:200],
                "latency_s": round(lat, 2),
            }
            print(f"  run {i+1}: FAIL ({type(err).__name__}: {err})")
        runs.append(entry)

    ok_runs = [r for r in runs if r.get("ok")]
    if ok_runs:
        slide_counts = [r["slide_count"] for r in ok_runs]
        slide_spread = max(slide_counts) - min(slide_counts)
        all_korean = all(r["lang"] == "ko" for r in ok_runs)
        all_tables_match = all(r["table_count"] == x_prime for r in ok_runs)
        # 출처 metric: 본문 침투 0 + (입력 md 에 마커 있으면 노트 ≥1)
        all_body_clean = all(r["src_in_body"] == 0 for r in ok_runs)
        if md_source_markers > 0:
            all_notes_have_src = all(r["src_in_notes"] >= 1 for r in ok_runs)
        else:
            all_notes_have_src = True  # 입력 자체에 마커 없으면 metric 무관 PASS
        source_consistency = all_body_clean and all_notes_have_src
    else:
        slide_spread = None
        all_korean = False
        all_tables_match = False
        all_body_clean = False
        all_notes_have_src = False
        source_consistency = False

    passed = (
        len(ok_runs) == n
        and slide_spread is not None
        and slide_spread <= 2
        and all_korean
        and all_tables_match
        and source_consistency
    )

    summary = {
        "md_path": str(md_path),
        "slug": slug,
        "topic_title": topic_title,
        "n": n,
        "x_prime": x_prime,
        "md_source_markers": md_source_markers,
        "runs": runs,
        "slide_spread": slide_spread,
        "lang_consistency": all_korean,
        "table_consistency": all_tables_match,
        "source_body_clean": all_body_clean,
        "source_notes_present": all_notes_have_src,
        "source_consistency": source_consistency,
        "ok_runs": len(ok_runs),
        "pass": passed,
    }
    return summary


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--md", required=True, help="입력 .md 경로")
    p.add_argument("--slug", required=True)
    p.add_argument("--topic-title", required=True)
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--out", default=None, help="결과 JSON 저장 경로 (default: logs/stability_<slug>_<ts>.json)")
    args = p.parse_args()

    summary = measure_run(Path(args.md), slug=args.slug, topic_title=args.topic_title, n=args.n)
    print(f"\n=== close 조건 평가 ===")
    print(f"  ok_runs:           {summary['ok_runs']}/{summary['n']}")
    print(f"  slide_spread:      {summary['slide_spread']}  (≤2 통과)")
    print(f"  lang_consistency:  {summary['lang_consistency']}  (True 통과)")
    print(f"  table_consistency: {summary['table_consistency']}  (True 통과, X'={summary['x_prime']})")
    print(f"  src_body_clean:    {summary['source_body_clean']}  (True 통과 — 본문 마커 0)")
    print(f"  src_notes_present: {summary['source_notes_present']}  (True 통과 — 노트 마커 ≥1)")
    print(f"  PASS: {summary['pass']}")

    if args.out:
        out = Path(args.out)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = Path("logs") / f"stability_{args.slug}_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out}")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
