# -*- coding: utf-8 -*-
"""
Markdown 자동 교정 스크립트
- 헤딩(###/#### 등) 뒤에 공백 줄 삽입
- 한 줄에 이어 붙은 불릿(" - **...** - **...**")을 줄바꿈된 리스트로 분리
- 알려진 하위 섹션(배경/핵심 요점/근거/시사점/Actionable Recommendations) 헤딩 레벨 통일
- 코드블록(```/~~~) 내부는 절대 수정하지 않음

Usage:
  python md_autofix.py input.md -o output.md
  python md_autofix.py input.md --inplace
  python md_autofix.py input.md -o output.md --sublevel 3   # 하위 섹션을 ###로
"""
import re
import argparse
from pathlib import Path

# 하위 섹션 이름 패턴 (양쪽 공백 허용, 괄호 안 변형 허용)
SUBSECTION_PAT = re.compile(
    r"^\s*#{1,6}\s*(배경|핵심\s*요점|근거(\s*\(.*?\))?|시사점|Actionable\s+Recommendations)\s*$",
    flags=re.IGNORECASE
)

# 코드펜스 토글용
FENCE_RE = re.compile(r"^(```|~~~)")

def split_inline_bullets(line: str) -> str:
    """
    한 줄에 이어 붙은 불릿을 줄바꿈으로 분리
    예) "- **A** ... - **B** ..." → "- **A** ...\n- **B** ..."
    """
    # 불릿이 2개 이상 있는 경우만 시도
    if line.count("- **") + line.count("-**") >= 2:
        # ' - **' 앞에서 줄바꿈으로 교체
        line = re.sub(r"\s+-\s+(?=\*\*)", "\n- ", line)
    return line

def ensure_blank_line_after_headings(lines: list[str]) -> list[str]:
    """
    헤딩(#...) 바로 다음 줄이 비어있지 않으면 공백 라인 삽입
    """
    out = []
    for i, ln in enumerate(lines):
        out.append(ln)
        if re.match(r"^\s*#{1,6}\s+\S", ln.strip()):
            # 다음 줄이 존재하고 비어있지 않으면 공백 추가
            if i + 1 < len(lines):
                nxt = lines[i + 1]
                if nxt.strip() != "":
                    out.append("")  # 빈 줄 삽입
            else:
                out.append("")
    return out

def ensure_blank_line_around_headings(lines: list[str]) -> list[str]:
    """
    헤딩 위/아래 공백 라인 보장(위는 선택적, 아래는 필수)
    """
    # 위: 헤딩 위에 본문이 붙어있는 경우 공백 추가
    out = []
    prev_blank = True
    for ln in lines:
        if re.match(r"^\s*#{1,6}\s+\S", ln.strip()) and not prev_blank:
            out.append("")  # 위쪽 공백
            out.append(ln)
            prev_blank = False
        else:
            out.append(ln)
            prev_blank = (ln.strip() == "")
    # 아래: 별도 함수에서 한 번 더 처리
    out = ensure_blank_line_after_headings(out)
    return out

def normalize_subsection_heading_level(line: str, sublevel: int) -> str:
    """
    알려진 하위 섹션의 헤딩 레벨을 통일(예: ### 로)
    """
    if SUBSECTION_PAT.match(line.strip()):
        title = re.sub(r"^\s*#{1,6}\s*", "", line).strip()
        return f"{'#' * sublevel} {title}"
    return line

def process_markdown(text: str, sublevel: int = 3) -> str:
    lines = text.splitlines()
    out: list[str] = []

    in_fence = False
    fence_marker = None

    for ln in lines:
        s = ln.rstrip("\n")

        # 코드펜스 토글
        if FENCE_RE.match(s.strip()):
            if not in_fence:
                in_fence = True
                fence_marker = s.strip()[:3]
            else:
                # 같은 펜스면 닫기
                if s.strip().startswith(fence_marker):
                    in_fence = False
                    fence_marker = None
            out.append(s)
            continue

        if in_fence:
            # 코드블록 내부는 그대로 유지
            out.append(s)
            continue

        # 1) 한 줄에 붙은 불릿 나누기
        s = split_inline_bullets(s)

        # 2) 하위 섹션 헤딩 레벨 통일
        s = normalize_subsection_heading_level(s, sublevel=sublevel)

        out.append(s)

    # 3) 헤딩 주변 공백 보정
    out = ensure_blank_line_around_headings(out)

    # 4) 리스트 가독성: 불릿 다음 줄이 바로 붙으면 한 줄 추가 (선택적, 과도 삽입 방지)
    final: list[str] = []
    for i, s in enumerate(out):
        final.append(s)
        if re.match(r"^\s*[-*]\s+\S", s.strip()):
            if i + 1 < len(out) and out[i + 1].strip() != "":
                final.append("")

    return "\n".join(final).rstrip() + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="입력 Markdown 파일 경로")
    ap.add_argument("-o", "--output", help="출력 파일 경로(미지정 시 --inplace 필요)")
    ap.add_argument("--inplace", action="store_true", help="원본을 덮어쓰기")
    ap.add_argument("--sublevel", type=int, default=3, help="하위 섹션(배경/핵심요점/근거/시사점/AR) 헤딩 레벨 (기본=3 → ###)")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise FileNotFoundError(src)

    text = src.read_text(encoding="utf-8", errors="ignore")
    fixed = process_markdown(text, sublevel=args.sublevel)

    if args.inplace:
        src.write_text(fixed, encoding="utf-8")
        print(f"[md_autofix] in-place fixed: {src}")
    else:
        if not args.output:
            raise SystemExit("출력 경로(-o)나 --inplace 중 하나를 지정하세요.")
        dst = Path(args.output)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(fixed, encoding="utf-8")
        print(f"[md_autofix] wrote: {dst}")

if __name__ == "__main__":
    main()
