"""§citation-claim-faithfulness R2-T2 — 문장↔인용 페어 추출 (오프라인, 유료 0).

입력
    - draft md (본문 [[N]] 마커 포함, References footer 는 파싱 전 절단)
    - chunks_with_abstract_dump.json (R2-T1 산물; index = N-1, 89 chunks + abstract240)

페어 정의 (사용자 컨펌)
    - 측정 단위 = 문장. [[N]] 붙은 문장 1개 ↔ N번 chunk abstract.
    - [[N]] 없는 문장 = 대상 아님.
    - 한 문장에 [[N]] 여럿 = 각 N 마다 페어 (문장 중복 허용).

페어 status
    - valid       : 1<=N<=89 AND abstract 비어있지 않음  → T3 코사인 대상
    - no_abstract : 1<=N<=89 이나 abstract 결손(OA/SS 소스 결손, T1 24건) → 제외
    - out_of_range: N>89 (footer 범위 밖 = section-local↔global 오정렬, catch 80 계열) → 제외

dedup (측정 전처리, 파이프라인 :262 무수정)
    같은 논문 다른 N 이면 abstract 동일 → 페어는 N 별 유지, 통계는 identity(doi>title)
    단위로 고유 논문 수 집계(같은 논문이 여러 표 던지는 것 방지).

실행
    python3 "scripts/§paper-writer-1/extract_pairs.py"   # 순수 stdlib, 무료
출력
    scripts/output/§paper-writer-1/citation_pairs.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parents[1] / "scripts" / "output" / "§paper-writer-1"
DRAFT = OUT_DIR / "paper_consumer_perceived_trademark_similarity_and_likelihood_of_co_20260706_004833.md"
CHUNKS = OUT_DIR / "chunks_with_abstract_dump.json"
PAIRS_OUT = OUT_DIR / "citation_pairs.json"

_MARK_RE = re.compile(r"\[\[(\d+)\]\]")


def _norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _identity(chunk: dict) -> str:
    d = (chunk.get("doi") or "").strip().lower()
    return f"doi:{d}" if d else f"title:{_norm_title(chunk.get('title'))}"


_BLOCK_PREFIX_RE = re.compile(r"^\s*(?:[#>]+|[*\-+]\s+|\d+[.)]\s+)")


def _split_sentences(body: str) -> list[str]:
    """라인(=블록) 단위 → 문장 단위. 영어 위주 + 일부 한국어.

    이 draft 는 한 줄 = 한 문단/블록(하드랩 없음, 불릿도 각자 줄). 따라서 모든 개행으로
    라인 분리해야 인접 불릿(예: line81 [[58]] 문장 ↔ line82 Phonetic 불릿)이 병합되지
    않는다. 라인 선두 마크다운 마커(#, *, -, 숫자.)·표 파이프는 제거 후 문장 분할.
    문장 경계 = [.!?] 뒤 공백 + 다음이 문장 시작처럼 보일 때(대문자/숫자/따옴표/한글/`[`)만
    — 약어(U.S. 등) 과분할 완화.
    """
    sentences: list[str] = []
    for raw in body.split("\n"):
        line = _BLOCK_PREFIX_RE.sub("", raw).strip()
        if line.startswith("|"):          # 표 행 skip
            continue
        line = " ".join(line.split())     # 중복 공백 정리
        if not line:
            continue
        for s in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"“\[가-힣])', line):
            s = s.strip()
            if s:
                sentences.append(s)
    return sentences


def main() -> int:
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))["chunks"]
    n_chunks = len(chunks)

    body = DRAFT.read_text(encoding="utf-8")
    ref_idx = body.find("## References")
    if ref_idx > 0:
        body = body[:ref_idx]  # footer 절단(본문 [[N]] 만 파싱)

    sentences = _split_sentences(body)

    pairs: list[dict] = []
    sents_with_cite = 0
    for s in sentences:
        ns = [int(m.group(1)) for m in _MARK_RE.finditer(s)]
        if not ns:
            continue
        sents_with_cite += 1
        sent_clean = _MARK_RE.sub("", s).strip()  # 마커 제거한 문장(임베딩 입력)
        sent_clean = re.sub(r"\s+", " ", sent_clean)
        for n in ns:
            if n < 1 or n > n_chunks:
                status = "out_of_range"
                abstract = ""
                identity = None
                title = None
            else:
                ch = chunks[n - 1]
                abstract = ch.get("abstract") or ""
                identity = _identity(ch)
                title = ch.get("title")
                status = "valid" if abstract.strip() else "no_abstract"
            pairs.append({
                "n": n,
                "status": status,
                "sentence": sent_clean,
                "cited_title": title,
                "cited_identity": identity,
                "abstract": abstract,
            })

    # ── 집계 ──
    from collections import Counter
    by_status = Counter(p["status"] for p in pairs)
    valid = [p for p in pairs if p["status"] == "valid"]
    unique_papers = len({p["cited_identity"] for p in valid})
    oor_ns = sorted({p["n"] for p in pairs if p["status"] == "out_of_range"})
    noabs_ns = sorted({p["n"] for p in pairs if p["status"] == "no_abstract"})

    out = {
        "source": "extract_pairs (R2-T2, offline, 유료 0)",
        "draft": DRAFT.name,
        "chunks_file": CHUNKS.name,
        "n_pairs_total": len(pairs),
        "n_sentences_with_citation": sents_with_cite,
        "status_counts": dict(by_status),
        "n_valid_pairs": len(valid),
        "n_unique_cited_papers_valid": unique_papers,
        "out_of_range_n": oor_ns,
        "no_abstract_n": noabs_ns,
        "pairs": pairs,
    }
    PAIRS_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 리포트 ──
    print(f"[saved] {PAIRS_OUT}")
    print(f"총 페어: {len(pairs)}  |  [[N]] 있는 문장: {sents_with_cite}")
    print(f"status: {dict(by_status)}")
    print(f"valid(코사인 대상) 페어: {len(valid)}  |  dedup 후 고유 논문: {unique_papers}")
    print(f"out_of_range N(>{n_chunks}, catch80): {oor_ns}")
    print(f"no_abstract N(소스 결손): {noabs_ns}")

    # Beebe [[58]] 페어
    print("\n--- [[58]] 페어 ---")
    for p in pairs:
        if p["n"] == 58:
            print(f"status={p['status']}  cited={p['cited_title']!r}")
            print(f"문장: {p['sentence'][:220]}")
            print(f"abstract: {p['abstract'][:160]}")
            break

    # valid 샘플 2건
    print("\n--- valid 페어 샘플 2건 ---")
    for p in valid[:2]:
        print(f"[[{p['n']}]] {p['cited_title'][:50]!r}")
        print(f"  문장: {p['sentence'][:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
