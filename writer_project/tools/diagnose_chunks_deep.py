"""인덱스 청크 심층 진단.

- 의문 A: PDF가 왜 적은가? → 콘텐츠 타입별 비율 + 소스 도메인 top
- 의문 B: 길이 분포 이중봉우리 정상인가? → 전체 콘텐츠 타입 길이 분포 비교
"""
import sys
from pathlib import Path
from collections import Counter
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tools.web_rag.ingest_vector import _get_vs, _default_chroma_dir

NAMESPACES = [
    "height-growth-supplement-web",
    "height-growth-supplement-local",
    "pet-food-premium-web",
]

# 길이 버킷 (PDF 진단보다 더 세밀)
BUCKETS = [
    (0, 50),
    (50, 120),
    (120, 300),
    (300, 600),
    (600, 1000),
    (1000, 1500),
    (1500, 2000),
    (2000, 2400),
    (2400, 99999),
]


def _classify_ct(meta) -> str:
    """콘텐츠 타입을 거친 카테고리로 분류."""
    if not meta:
        return "unknown"
    ct = (meta.get("content_type") or "").lower()
    src = (meta.get("source") or "").lower()
    if "pdf" in ct or src.endswith(".pdf"):
        return "pdf"
    if "presentationml" in ct or src.endswith(".pptx"):
        return "pptx"
    if "spreadsheetml" in ct or "xlsx-summary" in ct or src.endswith(".xlsx"):
        return "xlsx"
    if "html" in ct:
        return "html"
    if src.startswith("file://"):
        return "local_other"
    if ct.startswith("text/"):
        return "text"
    return "other"


def _host_of(meta) -> str:
    if not meta:
        return "(no-meta)"
    src = meta.get("source") or meta.get("url") or ""
    if not src:
        return "(no-source)"
    if src.startswith("file://"):
        return "(local)"
    try:
        host = urlparse(src).netloc.lower()
        return host or "(no-host)"
    except Exception:
        return "(parse-fail)"


def _print_distribution(name: str, lens: list[int]) -> None:
    if not lens:
        print(f"    {name}: (no chunks)")
        return
    n = len(lens)
    lens_sorted = sorted(lens)
    median = lens_sorted[n // 2]
    p25 = lens_sorted[n // 4]
    p75 = lens_sorted[3 * n // 4]
    avg = sum(lens) / n
    print(f"    {name}: n={n} avg={avg:.0f} p25={p25} p50={median} p75={p75} min={lens_sorted[0]} max={lens_sorted[-1]}")
    for lo, hi in BUCKETS:
        cnt = sum(1 for L in lens if lo <= L < hi)
        if cnt > 0:
            pct = cnt * 100 / n
            bar = "█" * int(pct / 2)
            print(f"      [{lo:5d} .. {hi:5d}): {cnt:5d} ({pct:5.1f}%) {bar}")


for ns in NAMESPACES:
    pd = _default_chroma_dir(ns)
    if not Path(pd).exists():
        print(f"\n[{ns}] dir not found")
        continue

    try:
        vs = _get_vs(ns, pd)
        col = vs._collection
        cnt = col.count()
    except Exception as e:
        print(f"\n[{ns}] error: {e}")
        continue

    if cnt == 0:
        continue

    print(f"\n{'=' * 70}")
    print(f"=== {ns} (count={cnt}) ===")
    print(f"{'=' * 70}")

    try:
        result = col.get(include=["documents", "metadatas"])
    except Exception as e:
        print(f"  get failed: {e}")
        continue

    docs = result.get("documents") or []
    metas = result.get("metadatas") or []

    # 콘텐츠 타입별 분류
    ct_counter: Counter = Counter()
    ct_lens: dict[str, list[int]] = {}
    pdf_hosts: Counter = Counter()
    pdf_sources: Counter = Counter()
    all_hosts: Counter = Counter()

    for doc_text, meta in zip(docs, metas):
        ct_cat = _classify_ct(meta)
        ct_counter[ct_cat] += 1
        L = len((doc_text or "").strip())
        ct_lens.setdefault(ct_cat, []).append(L)

        host = _host_of(meta)
        all_hosts[host] += 1
        if ct_cat == "pdf":
            pdf_hosts[host] += 1
            src = (meta.get("source") if meta else "") or ""
            pdf_sources[src] += 1

    # 1) 콘텐츠 타입 비율
    print(f"\n  [content type breakdown]")
    for ct, cn in ct_counter.most_common():
        pct = cn * 100 / cnt
        print(f"    {ct:15s}: {cn:5d} ({pct:5.1f}%)")

    # 2) 콘텐츠 타입별 길이 분포
    print(f"\n  [length distribution by content type]")
    for ct in ["pdf", "html", "pptx", "xlsx", "text", "local_other", "other", "unknown"]:
        if ct in ct_lens:
            _print_distribution(ct, ct_lens[ct])

    # 3) PDF 출처 분석
    if pdf_hosts:
        print(f"\n  [PDF source hosts (top 10)]")
        for host, c in pdf_hosts.most_common(10):
            print(f"    {host:50s}: {c}")

    if pdf_sources:
        print(f"\n  [PDF unique URLs (top 5)]")
        for src, c in pdf_sources.most_common(5):
            src_short = src if len(src) <= 90 else src[:50] + "..." + src[-37:]
            print(f"    chunks={c:3d} | {src_short}")

    # 4) 전체 호스트 top
    if all_hosts:
        print(f"\n  [all source hosts (top 10)]")
        for host, c in all_hosts.most_common(10):
            pct = c * 100 / cnt
            print(f"    {host:50s}: {c:5d} ({pct:5.1f}%)")

print(f"\n{'=' * 70}")
print("=== done ===")