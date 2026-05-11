# scripts/lint_report_consistency.py
# §13-14-γ: 운영 산출물 (sections/.md + latest.md + pptx) 의 일관성 측정 linter.
# LLM 호출 0 — 측정만. dual track (gpt-4o / Sonnet 4.6) 모두 지원.
#
# 모듈 구성:
#   - md_measure  : sections/.md + latest.md 의 H2 양상 / H3 / bullet 측정
#   - pptx_measure: 슬라이드 layout / SECTION_HEADER sid / TITLE_CONTENT bullet 측정
#                   (extract_pptx_text.py 의 zip+ET 패턴 재사용, python-pptx 불요)
#   - compare     : md ↔ pptx cascade 안정도 + 누락률
#   - report      : 결함 양상 표 + 다중 라운드 CV
#   - CLI         : argparse 인자 (--rounds, --md, --outline, --sections-dir, --output)
#
# 사용:
#   single round:
#     python scripts/lint_report_consistency.py \
#       --pptx reports/venfobel-vitamin/20260511_13-14-alpha_round1.pptx \
#       --outline outlines/venfobel-vitamin/outline_report.md
#   3 rounds (cascade 안정도 + CV):
#     python scripts/lint_report_consistency.py \
#       --rounds reports/venfobel-vitamin/A.pptx reports/venfobel-vitamin/B.pptx reports/venfobel-vitamin/C.pptx \
#       --outline outlines/venfobel-vitamin/outline_report.md \
#       --output scripts/_lint_3round_report.md

from __future__ import annotations
import argparse
import io
import re
import statistics
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


# ─────────────────────────────────────────────────────────────────────────────
# md_measure
# ─────────────────────────────────────────────────────────────────────────────

_H2_RE = re.compile(r"^\s*##\s+(.+?)\s*$", re.M)
_H3_RE = re.compile(r"^\s*###\s+(.+?)\s*$", re.M)
_H2_SID_PREFIX_RE = re.compile(r"^\s*##\s+(\d+)\.\s+\S")  # ## 1. <title>
_BULLET_RE = re.compile(r"^\s*[-*•]\s+\S|^\s*\d+\.\s+\S")


@dataclass
class MdSection:
    file_name: str
    first_line: str
    h2_present: bool
    h2_sid_prefix: bool
    h2_plaintext_title_only: bool   # H2 없이 첫 줄이 평문 제목 한 줄
    h2_plaintext_paragraph: bool    # H2 없이 첫 줄이 도입부 평문
    h3_count: int
    h3_titles: list[str]
    bullet_counts_per_h3: list[int]


def measure_md_section(path: Path) -> MdSection:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    first_line = next((ln for ln in lines if ln.strip()), "")

    h2_present = bool(_H2_RE.search(text))
    h2_sid_prefix = bool(_H2_SID_PREFIX_RE.match(first_line) if first_line else False)
    # H2 없고 첫 줄이 짧으면 평문 제목, 길면 도입부
    h2_plaintext_title_only = False
    h2_plaintext_paragraph = False
    if not h2_present and first_line:
        # 평문 제목 추정: < 50 chars + 마침표 없음 + bullet 시작 아님
        clean = first_line.strip()
        is_short = len(clean) < 50
        no_period = not clean.endswith((".", "다.", "다", "."))
        not_bullet = not _BULLET_RE.match(clean)
        if is_short and no_period and not_bullet:
            h2_plaintext_title_only = True
        else:
            h2_plaintext_paragraph = True

    # H3 + bullet 측정
    h3_titles: list[str] = []
    bullet_counts: list[int] = []
    cur_bullets = 0
    in_h3 = False
    for ln in lines:
        stripped = ln.strip()
        h3_match = re.match(r"^###\s+(.+?)\s*$", ln)
        if h3_match:
            if in_h3:
                bullet_counts.append(cur_bullets)
            h3_titles.append(h3_match.group(1).strip())
            cur_bullets = 0
            in_h3 = True
            continue
        if in_h3 and _BULLET_RE.match(ln):
            cur_bullets += 1
    if in_h3:
        bullet_counts.append(cur_bullets)

    return MdSection(
        file_name=path.name,
        first_line=first_line,
        h2_present=h2_present,
        h2_sid_prefix=h2_sid_prefix,
        h2_plaintext_title_only=h2_plaintext_title_only,
        h2_plaintext_paragraph=h2_plaintext_paragraph,
        h3_count=len(h3_titles),
        h3_titles=h3_titles,
        bullet_counts_per_h3=bullet_counts,
    )


def measure_md_full(path: Path) -> dict:
    """latest.md (merged) 측정."""
    text = path.read_text(encoding="utf-8")
    h2_titles = _H2_RE.findall(text)
    h3_titles = _H3_RE.findall(text)
    n_h2_with_sid = sum(1 for t in h2_titles if re.match(r"^\d+\.\s+\S", t.strip()))
    return {
        "path": str(path),
        "size_chars": len(text),
        "n_h2": len(h2_titles),
        "n_h3": len(h3_titles),
        "n_h2_with_sid": n_h2_with_sid,
        "h2_titles": h2_titles,
        "h3_titles": h3_titles,
    }


# ─────────────────────────────────────────────────────────────────────────────
# pptx_measure  (extract_pptx_text.py 패턴 재사용)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Slide:
    idx: int                # 1-based
    layout_name: str
    layout_id_hint: int     # 0=TITLE / 1=TITLE_CONTENT / 2=SECTION_HEADER / -1=other (TITLE_TABLE 등)
    title: str
    body_paragraphs: list[str]
    n_tables: int
    has_sid_prefix: bool    # title 이 "01" 또는 "1." 또는 "1." 형식 보유


def _classify_layout(name: str) -> int:
    n = (name or "").upper()
    if "SECTION_HEADER" in n or "SECTION HEADER" in n:
        return 2
    if "TITLE_CONTENT" in n or "TITLE AND CONTENT" in n or "CONTENT" in n:
        return 1
    if "TITLE" in n and "TABLE" not in n and "CONTENT" not in n:
        return 0
    return -1


def _has_sid(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return False
    # "01", "02"... (Sonnet 양상)
    if re.match(r"^\d{1,2}$", t):
        return True
    # "1. <X>" (gpt-4o 양상)
    if re.match(r"^\d+\.\s+\S", t):
        return True
    # "1 <X>" 같은 변종
    if re.match(r"^\d+\s+\S", t):
        return True
    return False


def _extract_layout_map(z: zipfile.ZipFile) -> dict[str, str]:
    """slide.xml 의 rels → slideLayout 매핑. layout name 회수."""
    # slide{i}.xml.rels 에서 slideLayout target 추출 → ppt/slideLayouts/slideLayout{N}.xml
    # slideLayout 의 <p:cSld name="..."/> 에서 name 회수
    slide_to_layout: dict[str, str] = {}
    layout_name_cache: dict[str, str] = {}

    namelist = z.namelist()
    for n in namelist:
        if not (n.startswith("ppt/slides/_rels/slide") and n.endswith(".xml.rels")):
            continue
        try:
            rxml = z.read(n)
            root = ET.fromstring(rxml)
            target = None
            for rel in root.iter():
                if rel.tag.endswith("Relationship"):
                    tp = rel.attrib.get("Type", "")
                    if "slideLayout" in tp:
                        target = rel.attrib.get("Target", "")
                        break
            if not target:
                continue
            # Target = "../slideLayouts/slideLayout7.xml" → "ppt/slideLayouts/slideLayout7.xml"
            layout_path = target.replace("../", "ppt/")
            if layout_path not in layout_name_cache:
                if layout_path in namelist:
                    lxml = z.read(layout_path)
                    lroot = ET.fromstring(lxml)
                    csld = lroot.find(f"{{{P_NS}}}cSld")
                    name = (csld.attrib.get("name") if csld is not None else "") or ""
                    layout_name_cache[layout_path] = name
                else:
                    layout_name_cache[layout_path] = ""
            slide_name = n.replace("/_rels/", "/").replace(".rels", "")
            slide_to_layout[slide_name] = layout_name_cache[layout_path]
        except Exception:
            pass
    return slide_to_layout


def _extract_slide_content(xml_bytes: bytes) -> tuple[list[str], list[list[list[str]]]]:
    """(texts list, tables list) — extract_pptx_text.py 와 동일 패턴."""
    root = ET.fromstring(xml_bytes)
    texts: list[str] = []
    for t in root.iter(f"{{{A_NS}}}t"):
        s = t.text or ""
        if s:
            texts.append(s)
    tables: list[list[list[str]]] = []
    for tbl in root.iter(f"{{{A_NS}}}tbl"):
        rows = []
        for tr in tbl.iter(f"{{{A_NS}}}tr"):
            cells = []
            for tc in tr.iter(f"{{{A_NS}}}tc"):
                parts = []
                for t in tc.iter(f"{{{A_NS}}}t"):
                    s = t.text or ""
                    if s:
                        parts.append(s)
                cells.append("".join(parts))
            rows.append(cells)
        if rows:
            tables.append(rows)
    return texts, tables


def measure_pptx(path: Path) -> dict:
    p = path
    slides: list[Slide] = []
    layout_counts: dict[str, int] = {}

    with zipfile.ZipFile(str(p)) as z:
        names = z.namelist()
        slide_files = sorted(
            [n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")],
            key=lambda n: int(re.search(r"slide(\d+)\.xml", n).group(1)),
        )
        slide_to_layout = _extract_layout_map(z)

        for i, sf in enumerate(slide_files, 1):
            xml = z.read(sf)
            texts, tables = _extract_slide_content(xml)
            layout_name = slide_to_layout.get(sf, "")
            layout_id = _classify_layout(layout_name)
            layout_counts[layout_name] = layout_counts.get(layout_name, 0) + 1
            title = texts[0] if texts else ""
            body = texts[1:] if len(texts) > 1 else []
            slides.append(Slide(
                idx=i,
                layout_name=layout_name,
                layout_id_hint=layout_id,
                title=title,
                body_paragraphs=body,
                n_tables=len(tables),
                has_sid_prefix=_has_sid(title),
            ))

    # section grouping: SECTION_HEADER → body until next SECTION_HEADER
    section_groups: list[dict] = []
    cur_group: dict | None = None
    for s in slides:
        if s.layout_id_hint == 2:  # SECTION_HEADER
            if cur_group is not None:
                section_groups.append(cur_group)
            cur_group = {
                "header_slide_idx": s.idx,
                "header_title": s.title,
                "header_has_sid": s.has_sid_prefix,
                "body": [],
            }
        elif cur_group is not None:
            cur_group["body"].append({
                "idx": s.idx,
                "layout": s.layout_name,
                "title": s.title,
                "bullets": len(s.body_paragraphs),
                "has_table": s.n_tables > 0,
            })
    if cur_group is not None:
        section_groups.append(cur_group)

    return {
        "path": str(p),
        "size_bytes": p.stat().st_size,
        "n_slides": len(slides),
        "layout_counts": layout_counts,
        "slides": slides,
        "section_groups": section_groups,
    }


# ─────────────────────────────────────────────────────────────────────────────
# outline measure
# ─────────────────────────────────────────────────────────────────────────────

def measure_outline(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    h2_titles = _H2_RE.findall(text)
    return {
        "path": str(path),
        "n_h2": len(h2_titles),
        "h2_titles": h2_titles,
    }


# ─────────────────────────────────────────────────────────────────────────────
# compare
# ─────────────────────────────────────────────────────────────────────────────

def compare_md_pptx(md_full: dict, pptx_m: dict, outline_m: dict) -> dict:
    """md ↔ pptx 일관성 측정."""
    n_h2_md = md_full["n_h2"]
    n_h3_md = md_full["n_h3"]
    n_h2_outline = outline_m["n_h2"]
    n_section_headers = sum(1 for sg in pptx_m["section_groups"])
    n_section_headers_with_sid = sum(1 for sg in pptx_m["section_groups"] if sg["header_has_sid"])

    # 누락률: expected = 1 TITLE + n_h2_md SECTION_HEADER + n_h3_md TITLE_CONTENT
    expected_slides = 1 + n_h2_md + n_h3_md
    actual_slides = pptx_m["n_slides"]
    missing = expected_slides - actual_slides
    miss_rate = (missing / expected_slides * 100) if expected_slides else 0.0

    # § 별 본문 슬라이드 수
    per_section_body = [(sg["header_title"], len(sg["body"])) for sg in pptx_m["section_groups"]]

    return {
        "n_h2_md": n_h2_md,
        "n_h3_md": n_h3_md,
        "n_h2_outline": n_h2_outline,
        "n_section_headers": n_section_headers,
        "n_section_headers_with_sid": n_section_headers_with_sid,
        "expected_slides": expected_slides,
        "actual_slides": actual_slides,
        "missing": missing,
        "miss_rate_pct": round(miss_rate, 2),
        "per_section_body": per_section_body,
        "outline_h2_match_section_header": n_h2_outline == n_section_headers,
    }


# ─────────────────────────────────────────────────────────────────────────────
# multi-round report
# ─────────────────────────────────────────────────────────────────────────────

def cv_pct(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = statistics.mean(values)
    if m == 0:
        return 0.0
    return round(100.0 * statistics.stdev(values) / m, 2)


def render_round_report(round_idx: int, pptx_m: dict, cmp_m: dict) -> str:
    out: list[str] = []
    out.append(f"## Round {round_idx}: `{Path(pptx_m['path']).name}`")
    out.append(f"")
    out.append(f"- size: {pptx_m['size_bytes']} bytes")
    out.append(f"- n_slides: {pptx_m['n_slides']} (expected {cmp_m['expected_slides']}, missing {cmp_m['missing']} → {cmp_m['miss_rate_pct']}%)")
    out.append(f"- layout 분포: {pptx_m['layout_counts']}")
    out.append(f"- SECTION_HEADER: {cmp_m['n_section_headers']} (sid prefix 보유 {cmp_m['n_section_headers_with_sid']}/{cmp_m['n_section_headers']})")
    out.append(f"- outline H2 vs SECTION_HEADER 매칭: {cmp_m['outline_h2_match_section_header']}")
    out.append(f"")
    out.append(f"§ 별 본문 슬라이드 수 (SECTION_HEADER 제외):")
    out.append(f"")
    out.append(f"| § | header title | body slides |")
    out.append(f"|---|---|---|")
    for i, (title, n) in enumerate(cmp_m['per_section_body'], 1):
        out.append(f"| §{i} | {title} | {n} |")
    out.append(f"")
    return "\n".join(out)


def render_multi_round_report(rounds: list[tuple[dict, dict]], md_full: dict | None = None) -> str:
    """rounds = [(pptx_m, cmp_m), ...]"""
    out: list[str] = []
    out.append(f"# §13-14-γ linter — 다중 라운드 종합 측정")
    out.append(f"")
    if md_full:
        out.append(f"## md ground truth")
        out.append(f"")
        out.append(f"- latest.md: {md_full['path']}")
        out.append(f"- size: {md_full['size_chars']} chars")
        out.append(f"- n_h2: {md_full['n_h2']} (sid 보유 {md_full['n_h2_with_sid']})")
        out.append(f"- n_h3: {md_full['n_h3']}")
        out.append(f"")

    # 기본 측정값 표
    out.append(f"## 라운드별 기본 측정값")
    out.append(f"")
    out.append(f"| round | file | n_slides | size KB | n_section_headers | sid 보유 | missing | miss % |")
    out.append(f"|---|---|---|---|---|---|---|---|")
    for i, (pm, cm) in enumerate(rounds, 1):
        out.append(
            f"| R{i} | {Path(pm['path']).name} | {pm['n_slides']} | "
            f"{round(pm['size_bytes']/1024,1)} | {cm['n_section_headers']} | "
            f"{cm['n_section_headers_with_sid']}/{cm['n_section_headers']} | "
            f"{cm['missing']} | {cm['miss_rate_pct']}% |"
        )
    out.append(f"")

    # cascade 안정도 (3 라운드 §별 본문 슬라이드 수 CV)
    if len(rounds) >= 2:
        out.append(f"## §별 본문 슬라이드 수 — cascade 안정도 (3 라운드 CV)")
        out.append(f"")
        # § 수 추출
        max_secs = max(len(cm['per_section_body']) for _, cm in rounds)
        header_row = "| § | " + " | ".join([f"R{i+1}" for i in range(len(rounds))]) + " | mean | CV % |"
        out.append(header_row)
        out.append("|---" * (len(rounds) + 3) + "|")
        for sec_idx in range(max_secs):
            vals: list[int] = []
            for _, cm in rounds:
                if sec_idx < len(cm['per_section_body']):
                    vals.append(cm['per_section_body'][sec_idx][1])
                else:
                    vals.append(0)
            m = statistics.mean(vals) if vals else 0
            c = cv_pct([float(v) for v in vals])
            cells = " | ".join(str(v) for v in vals)
            out.append(f"| §{sec_idx+1} | {cells} | {m:.1f} | {c} |")
        out.append(f"")

        # 풍부함 일관성
        out.append(f"## 풍부함 일관성 — CV across rounds")
        out.append(f"")
        slides_vec = [pm['n_slides'] for pm, _ in rounds]
        size_vec = [pm['size_bytes']/1024 for pm, _ in rounds]
        title_table_vec = [pm['layout_counts'].get('TITLE_TABLE', 0) for pm, _ in rounds]
        title_content_vec = [pm['layout_counts'].get('TITLE_CONTENT', 0) for pm, _ in rounds]
        miss_vec = [cm['miss_rate_pct'] for _, cm in rounds]
        out.append(f"| metric | values | mean | CV % |")
        out.append(f"|---|---|---|---|")
        for label, vec in [
            ("n_slides", slides_vec),
            ("pptx KB", size_vec),
            ("TITLE_TABLE", title_table_vec),
            ("TITLE_CONTENT", title_content_vec),
            ("miss_rate %", miss_vec),
        ]:
            out.append(f"| {label} | {vec} | {statistics.mean(vec):.2f} | {cv_pct([float(v) for v in vec])} |")
        out.append(f"")

    # 라운드별 상세
    for i, (pm, cm) in enumerate(rounds, 1):
        out.append(render_round_report(i, pm, cm))

    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# sections/ 양상 보고 (gpt-4o 결함 양상 자동 검출용)
# ─────────────────────────────────────────────────────────────────────────────

def render_md_sections_report(sections_dir: Path) -> str:
    out: list[str] = []
    out.append(f"# md sections/ 양상")
    out.append(f"")
    out.append(f"- 디렉토리: {sections_dir}")
    out.append(f"")
    out.append(f"| 파일 | H2 보유 | sid prefix | 평문 제목 한 줄 | 평문 도입부 | H3 갯수 | bullets per H3 | first_line |")
    out.append(f"|---|---|---|---|---|---|---|---|")
    for f in sorted(sections_dir.glob("*.md")):
        m = measure_md_section(f)
        out.append(
            f"| {m.file_name} | {'✓' if m.h2_present else '✗'} | "
            f"{'✓' if m.h2_sid_prefix else '✗'} | "
            f"{'✓' if m.h2_plaintext_title_only else '-'} | "
            f"{'✓' if m.h2_plaintext_paragraph else '-'} | "
            f"{m.h3_count} | {m.bullet_counts_per_h3} | "
            f"{(m.first_line[:40] + ('...' if len(m.first_line)>40 else ''))} |"
        )
    out.append(f"")
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="§13-14-γ linter — md/pptx/outline 일관성 측정 (LLM 호출 0)"
    )
    p.add_argument("--pptx", help="단일 pptx 측정")
    p.add_argument("--rounds", nargs="+", help="다중 라운드 pptx 목록 (3 라운드 + CV)")
    p.add_argument("--rounds-md", nargs="+", help="라운드별 latest.md 1:1 매칭 (--rounds 와 동일 갯수, 누락률 측정용)")
    p.add_argument("--md", help="latest.md (merged) 경로 (단일 라운드용)")
    p.add_argument("--outline", help="outline_report.md 경로")
    p.add_argument("--sections-dir", help="sections/<slug>/ 디렉토리 (md 양상 보고)")
    p.add_argument("--output", help="보고서 markdown 출력 경로 (생략 시 stdout)")
    args = p.parse_args(argv)

    if not args.pptx and not args.rounds and not args.sections_dir:
        p.print_help()
        return 1

    chunks: list[str] = []

    # sections/ 양상 보고
    if args.sections_dir:
        sd = Path(args.sections_dir)
        if sd.exists():
            chunks.append(render_md_sections_report(sd))

    # outline
    outline_m = None
    if args.outline:
        op = Path(args.outline)
        if op.exists():
            outline_m = measure_outline(op)

    # md latest
    md_full = None
    if args.md:
        mp = Path(args.md)
        if mp.exists():
            md_full = measure_md_full(mp)

    # pptx 단일
    if args.pptx:
        pp = Path(args.pptx)
        if not pp.exists():
            print(f"[ERROR] pptx not found: {pp}", file=sys.stderr)
            return 2
        pptx_m = measure_pptx(pp)
        if not outline_m:
            # outline 없으면 빈 dict
            outline_m = {"n_h2": 0, "h2_titles": []}
        if not md_full:
            # md 없으면 n_h2=section_headers, n_h3=actual-section_headers-1 추정
            md_full = {
                "path": "(synthesized)",
                "size_chars": 0,
                "n_h2": pptx_m["n_slides"] and len(pptx_m["section_groups"]) or 0,
                "n_h3": max(0, pptx_m["n_slides"] - 1 - len(pptx_m["section_groups"])),
                "n_h2_with_sid": 0,
                "h2_titles": [], "h3_titles": [],
            }
        cmp_m = compare_md_pptx(md_full, pptx_m, outline_m)
        chunks.append(render_round_report(1, pptx_m, cmp_m))

    # pptx 다중 (rounds)
    if args.rounds:
        rounds_md_paths = args.rounds_md or []
        if rounds_md_paths and len(rounds_md_paths) != len(args.rounds):
            print(f"[WARN] --rounds ({len(args.rounds)}) vs --rounds-md ({len(rounds_md_paths)}) 갯수 불일치 — 1:1 매칭 skip", file=sys.stderr)
            rounds_md_paths = []
        rounds_data: list[tuple[dict, dict]] = []
        for i, ppath in enumerate(args.rounds):
            pp = Path(ppath)
            if not pp.exists():
                print(f"[WARN] pptx skipped (not found): {pp}", file=sys.stderr)
                continue
            pm = measure_pptx(pp)
            om = outline_m or {"n_h2": 0, "h2_titles": []}
            # 라운드별 latest.md 우선, 없으면 글로벌 --md, 없으면 synthesize
            mf = None
            if rounds_md_paths and i < len(rounds_md_paths):
                mp = Path(rounds_md_paths[i])
                if mp.exists():
                    mf = measure_md_full(mp)
            if mf is None:
                mf = md_full or {
                    "path": "(synthesized)", "size_chars": 0,
                    "n_h2": len(pm["section_groups"]),
                    "n_h3": max(0, pm["n_slides"] - 1 - len(pm["section_groups"])),
                    "n_h2_with_sid": 0, "h2_titles": [], "h3_titles": [],
                }
            cm = compare_md_pptx(mf, pm, om)
            rounds_data.append((pm, cm))
        chunks.append(render_multi_round_report(rounds_data, md_full=md_full))

    text = "\n\n".join(chunks)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[OK] report written → {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
