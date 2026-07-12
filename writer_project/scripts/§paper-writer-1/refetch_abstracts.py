"""§citation-claim-faithfulness catch83 ② — full abstract 재조회 (order-preserving backfill, 유료 OA/SS·$0).

목적
    chunks_raw_dump.json 의 89 chunk identity/order 를 **authoritative** 로 고정하고,
    paper_section_fetch 를 섹션별 재실행해 **abstract 만** full 로 backfill 한다.
    catch83 파일럿에서 240자 절단이 근거를 논문 논지에서 이탈시킴이 실증됨(Gone in Sixty:
    제목은 인지과학인데 240자엔 dilution/Kodak만 노출) → full 로 재시험.

order-preserving (조건1)
    old 89 의 identity/order 고정. 새 논문 fetch 금지 — fetch 결과는 (section,identity)
    매칭으로 abstract 소스로만 쓰고 old 순서/집합은 불변. catch 81 [[N]] 정합 보존.

fallback B (조건: SS 429 커버리지 후퇴 방지)
    fetch 매칭 non-empty → full (abstract_source="full").
    fetch 미매칭/empty → 기존 240 abstract 유지 (abstract_source="truncated_240").
    → dump 는 full/240 혼재. abstract_source 필드로 혼재를 명시(rank 인공물 판별용).

산출 (조건 2·4)
    - 섹션별 full 비율 (pool 전체 full 섹션이면 공정 대조 가능).
    - abstract 길이 분포 + e5 512토큰(≈2000자) 초과 건수 (full 받아도 임베딩은 앞부분만 → 새 Y).

실행 (.venv_vertex, macOS)
    .venv_vertex/bin/python "scripts/§paper-writer-1/refetch_abstracts.py"
출력
    scripts/output/§paper-writer-1/chunks_full_abstract_dump.json (기존 dump 무변경, 신규 파일)
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# measure_paper import = env bootstrap 재사용 (dotenv chain / provider lock /
# SKIP_VERTEX_SEARCH=1 / TOPIC_SLUG / certifi SSL / sys.path). main() 은 __name__
# 가드로 미실행. writer 는 import 만 되고 호출 안 함.
import measure_paper  # noqa: E402,F401

from agent.web_search import paper_section_fetch  # noqa: E402

OUT_DIR = measure_paper.PROJECT_ROOT / "scripts" / "output" / "§paper-writer-1"
OLD_DUMP = OUT_DIR / "chunks_raw_dump.json"
NEW_DUMP = OUT_DIR / "chunks_full_abstract_dump.json"   # 조건2: 별도 신규(기존 240 dump 보존)

E5_CHAR_LIMIT = 2000   # e5-large 512토큰 ≈ 2000자 실질 임베딩 상한(조건4 보고 기준)


def _keep_abstract(abstract: str | None) -> str:
    """catch83 ②: 무절단 full 보존 (구 _trunc240 개명 — 조건3 정직성)."""
    return (abstract or "").strip()


def _norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _identity(chunk: dict) -> tuple[str, str]:
    d = (chunk.get("doi") or "").strip().lower()
    if d:
        return ("doi", d)
    return ("title", _norm_title(chunk.get("title")))


def main() -> int:
    old = json.loads(OLD_DUMP.read_text(encoding="utf-8"))
    old_chunks: list[dict] = old["chunks"]
    topic: str = old["topic"]

    # 섹션 순서 = old dump 등장 순 (동일 쿼리 재현).
    sections: list[str] = []
    for c in old_chunks:
        if c["section"] not in sections:
            sections.append(c["section"])

    print(f"[refetch] topic={topic!r}")
    print(f"[refetch] sections={sections}")
    print(f"[refetch] old chunks={len(old_chunks)}")

    # 섹션별 재fetch → (section, identity) -> full abstract 맵.
    abs_map: dict[tuple[str, tuple[str, str]], str] = {}
    fresh_counts: dict[str, int] = {}
    for sec in sections:
        try:
            fresh = paper_section_fetch(topic, sec)
        except Exception as e:  # noqa: BLE001
            print(f"[refetch][{sec}] FETCH FAIL: {type(e).__name__}: {e}")
            fresh = []
        fresh_counts[sec] = len(fresh)
        for fc in fresh:
            key = (sec, _identity(fc))
            snip = _keep_abstract(fc.get("abstract"))
            if key not in abs_map or (not abs_map[key] and snip):   # 먼저 본 non-empty 우선
                abs_map[key] = snip
        print(f"[refetch][{sec}] fresh={len(fresh)}")

    # backfill (fallback B): old identity/order 고정, abstract 만 full 로 채우거나 240 유지.
    new_chunks: list[dict] = []
    n_full = n_fallback = n_empty = 0
    unmatched_rows: list[int] = []
    for i, c in enumerate(old_chunks, 1):
        key = (c["section"], _identity(c))
        fetched = abs_map.get(key)
        if fetched:                                   # fetch 성공 & non-empty → full
            abstract, source = fetched, "full"
            n_full += 1
        else:                                         # fallback: 기존 240 유지
            old_abs = (c.get("abstract") or "").strip()
            abstract, source = old_abs, "truncated_240"
            if old_abs:
                n_fallback += 1
            else:
                n_empty += 1
            if fetched is None:
                unmatched_rows.append(i)
        nc = dict(c)                                  # old 필드 보존
        nc["abstract"] = abstract
        nc["abstract_source"] = source                # 조건1: 혼재 표시
        new_chunks.append(nc)

    # ── 섹션별 full 비율 (조건2) ──
    from collections import Counter
    sec_total: Counter = Counter(nc["section"] for nc in new_chunks)
    sec_full: Counter = Counter(nc["section"] for nc in new_chunks if nc["abstract_source"] == "full")

    # ── abstract 길이 분포 + 512토큰 초과 (조건4) ──
    full_lens = [len(nc["abstract"]) for nc in new_chunks if nc["abstract_source"] == "full"]
    over_512 = [i + 1 for i, nc in enumerate(new_chunks)
                if nc["abstract_source"] == "full" and len(nc["abstract"]) > E5_CHAR_LIMIT]

    out = {
        "generated_at_utc": old.get("generated_at_utc"),
        "source": "refetch_abstracts (catch83 ②, order-preserving full backfill + fallback B)",
        "topic": topic,
        "n_chunks": len(new_chunks),
        "aligned_to": "chunks_raw_dump.json (89-chunk order preserved)",
        "abstract_recovery": {
            "full": n_full, "fallback_240": n_fallback, "empty": n_empty,
            "coverage_nonempty": n_full + n_fallback,
            "e5_char_limit": E5_CHAR_LIMIT, "over_limit_n": len(over_512),
        },
        "section_full_ratio": {s: f"{sec_full.get(s, 0)}/{sec_total[s]}" for s in sections},
        "chunks": new_chunks,
    }
    NEW_DUMP.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 리포트 ──
    print("\n" + "=" * 60)
    print(f"[saved] {NEW_DUMP}")
    print(f"[recovery] full={n_full}  fallback_240={n_fallback}  empty={n_empty}  "
          f"| non-empty 커버리지={n_full + n_fallback}/89 (baseline 65)")
    print(f"[recovery] cited_no_abstract 개선분(=empty였다가 full): 아래 fetch 매칭으로 판단")

    print(f"\n=== ⭐ 섹션별 full 비율 (조건2 — pool 전체 full이면 공정 대조) ===")
    for s in sections:
        tot, ful = sec_total[s], sec_full.get(s, 0)
        flag = " ← 전체 full(공정대조 가능)" if ful == tot else ""
        print(f"  {s:30} full {ful:>2}/{tot:<2}  ({100*ful/tot:.0f}%){flag}")

    print(f"\n=== ⭐ abstract 길이 분포 (full만, n={len(full_lens)}) + 512토큰 초과 (조건4) ===")
    if full_lens:
        print(f"  len min={min(full_lens)} median={int(st.median(full_lens))} max={max(full_lens)}")
        print(f"  2000자(≈512토큰) 초과: {len(over_512)}건  N={over_512}")
        print(f"  → {'⚠️ 초과 다수: full 받아도 임베딩은 앞부분만(새 Y)' if len(over_512) > len(full_lens)*0.3 else '초과 소수: 대부분 full 임베딩 반영'}")

    # 표적 확인: Gone in Sixty [[5계열]], Beebe [[2계열]] 이 full 로 회수됐나
    print(f"\n=== ⭐ 성공기준 표적 회수 확인 ===")
    for label, needle in [("Gone in Sixty(인지과학)", "gone in sixty"),
                          ("Beebe(Search and Persuasion)", "search and persuasion")]:
        hits = [(i + 1, nc["abstract_source"], len(nc["abstract"]))
                for i, nc in enumerate(new_chunks) if needle in _norm_title(nc.get("title"))]
        print(f"  {label}: {hits}")
        for n, src, ln in hits:
            if src == "full":
                nc = new_chunks[n - 1]
                print(f"    [[{n}]] full len={ln}  head: {nc['abstract'][:100]!r}")

    if unmatched_rows:
        print(f"\nunmatched(240 fallback 유지) rows: {len(unmatched_rows)}건 {unmatched_rows}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
