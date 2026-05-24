# utils/citations.py — §paper-writer-1 Step C-1
"""APA 7th edition citation formatter.

기존 utils/refs.py footnote layer ([[N]] marker → URL footer) 와는 분리된
학술 paper 전용 인용 모듈. paper writer prompt 가 본문 안에 [[N]] marker 만
사용하고, References section 은 post-process 단계에서 format_apa7() 호출로
구성한다.

future hook: MLA / Chicago / KCI 등은 동일 signature 패턴으로 추가한다
(본 파일 하단 sketch 참조). 본 cycle 은 APA 7th default 단독 채택.
"""
from __future__ import annotations

from typing import Optional


def format_apa7(
    authors: list[str],
    year: Optional[int],
    title: str,
    venue: Optional[str],
    doi: Optional[str],
) -> str:
    """APA 7th edition 형식의 인용 문자열 1건 반환.

    출력 예시:
        Smith, J. A., & Doe, B. C. (2024). Consumer behavior in influencer
        marketing. *Journal of Marketing Research*, 61(2), 123-145.
        https://doi.org/10.1177/00222437...

    edge case:
        authors=[] → 저자 생략, 제목부터 시작
        year=None → "(n.d.)"
        venue=None → italic 블록 생략
        doi=None → URL 생략
    """
    parts: list[str] = []

    author_str = _format_authors_apa7(authors)
    if author_str:
        parts.append(f"{author_str} ")

    year_str = f"({year})" if year is not None else "(n.d.)"
    parts.append(f"{year_str}. ")

    clean_title = (title or "").strip().rstrip(".")
    if clean_title:
        parts.append(f"{clean_title}. ")

    if venue:
        parts.append(f"*{venue.strip()}*. ")

    if doi:
        parts.append(_format_doi_url(doi))

    return "".join(parts).rstrip()


def _format_authors_apa7(authors: list[str]) -> str:
    """authors list 를 APA 7th 형식 문자열로 변환.

    - 1명: 'Last, F. M.'
    - 2명: 'Last1, F. M., & Last2, F. M.'
    - 3-20명: 'Last1, F. M., Last2, F. M., ..., & LastN, F. M.'
    - 21명 이상: first 19 + ', ... ' + last (APA 7th 21+ rule)

    입력은 'Last, First' 또는 'First Last' 형태 모두 허용 (정규화 미수행 —
    호출부에서 backend 별 추출 시 형식 일관성 보장).
    """
    clean = [a.strip() for a in (authors or []) if a and a.strip()]
    n = len(clean)
    if n == 0:
        return ""
    if n == 1:
        return clean[0]
    if n == 2:
        return f"{clean[0]}, & {clean[1]}"
    if n <= 20:
        return ", ".join(clean[:-1]) + f", & {clean[-1]}"
    # 21명 이상: APA 7th — 첫 19명, ..., 마지막 1명
    head = ", ".join(clean[:19])
    return f"{head}, ... {clean[-1]}"


def _format_doi_url(doi: str) -> str:
    """DOI 입력을 정규화한 URL 로 반환.

    - prefix 'https://doi.org/' 있으면 그대로 반환
    - 'doi:' prefix 만 있으면 strip 후 https://doi.org/ 부착
    - bare DOI (예: '10.1177/00222437...') → 'https://doi.org/' 부착
    """
    s = (doi or "").strip()
    if not s:
        return ""
    if s.startswith("https://doi.org/") or s.startswith("http://doi.org/"):
        return s
    if s.lower().startswith("doi:"):
        s = s[4:].strip()
    return f"https://doi.org/{s}"


# ─────────────────────────────────────────────────────────────────────────────
# future hook (sketch only — 본 cycle 미구현)
# ─────────────────────────────────────────────────────────────────────────────
# def format_mla(authors, title, venue, year, doi) -> str: ...
# def format_chicago(authors, year, title, venue, doi) -> str: ...
# def format_kci(authors, year, title, venue, doi, kci_id=None) -> str: ...
