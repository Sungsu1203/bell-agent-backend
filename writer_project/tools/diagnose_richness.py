"""풍부도 실측: 모든 chroma_store NS의 청크 수/길이/소스 분포 + PDF 페이지 사용률.

NOTE: (Windows 시절 기록, 2026-05-06) 당시 환경에서 chromadb의 Rust binding이
      PersistentClient.start() 단계에서 panic이 발생하는 관계로
      (chromadb_rust_bindings.Bindings) langchain-chroma 경유 접근이 막혀 있었다.
      대안: chroma의 SQLite 파일(chroma.sqlite3)을 직접 읽는다. ChromaDB의 스키마는
      안정적이며 embeddings/embedding_metadata 테이블에 chunk text + metadata가 들어 있다.

      ※ 2026-08-02 macOS 실측: PersistentClient 정상 동작(count=416) — catch BA.
        아래 SQLite 직접 읽기 우회는 동작에 문제 없어 그대로 유지한다.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent


def _classify_ct(meta: dict) -> str:
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


def _host_of(meta: dict) -> str:
    if not meta:
        return "(no-meta)"
    src = meta.get("source") or meta.get("url") or ""
    if not src:
        return "(no-source)"
    if src.startswith("file://"):
        return "(local)"
    try:
        return urlparse(src).netloc.lower() or "(no-host)"
    except Exception:
        return "(parse-fail)"


def _stats(lens: list[int]) -> str:
    if not lens:
        return "(empty)"
    n = len(lens)
    s = sorted(lens)
    return (f"n={n} avg={sum(lens)/n:.0f} p25={s[n//4]} p50={s[n//2]} "
            f"p75={s[3*n//4]} min={s[0]} max={s[-1]}")


def _load_chunks(sqlite_path: Path) -> list[tuple[str, dict]]:
    """ChromaDB SQLite에서 (document_text, metadata_dict) 리스트 추출.

    스키마(chromadb 1.x): embeddings(id INTEGER PK, embedding_id TEXT, ...),
    embedding_metadata(id INTEGER FK→embeddings.id, key TEXT, string_value TEXT, ...).
    document 본문은 embedding_metadata 의 key='chroma:document' string_value 에 저장.
    """
    out: list[tuple[str, dict]] = []
    con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        # 모든 embedding_id 별로 메타데이터 모으기
        cur.execute("""
            SELECT id, key, string_value, int_value, float_value, bool_value
              FROM embedding_metadata
        """)
        per_emb: dict[int, dict] = {}
        for emb_id, key, sv, iv, fv, bv in cur.fetchall():
            d = per_emb.setdefault(emb_id, {})
            if sv is not None:
                d[key] = sv
            elif iv is not None:
                d[key] = iv
            elif fv is not None:
                d[key] = fv
            elif bv is not None:
                d[key] = bool(bv)

        for emb_id, meta in per_emb.items():
            doc = meta.pop("chroma:document", "") or ""
            out.append((doc, meta))
    finally:
        con.close()
    return out


def main() -> None:
    store_root = ROOT / "data" / "chroma_store"
    if not store_root.exists():
        print(f"NOT FOUND: {store_root}")
        return

    namespaces = sorted(
        d.name for d in store_root.iterdir()
        if d.is_dir() and (d.name.endswith("-web") or d.name.endswith("-local"))
    )
    print(f"[scan] root={store_root}")
    print(f"[scan] namespaces={len(namespaces)}: {namespaces}\n")

    topic_totals: dict[str, dict[str, int]] = {}

    for ns in namespaces:
        sqlite_path = store_root / ns / "chroma.sqlite3"
        if not sqlite_path.exists():
            print(f"[{ns}] no chroma.sqlite3\n")
            continue
        try:
            chunks = _load_chunks(sqlite_path)
        except Exception as e:
            print(f"[{ns}] load failed: {e}\n")
            continue
        cnt = len(chunks)
        if cnt == 0:
            print(f"[{ns}] empty (0)\n")
            continue

        slug = ns
        kind = "other"
        for suf in ("-web", "-local"):
            if ns.endswith(suf):
                slug = ns[: -len(suf)]
                kind = suf[1:]
                break
        topic_totals.setdefault(slug, {"web": 0, "local": 0})
        topic_totals[slug][kind] = cnt

        ct_counter: Counter = Counter()
        ct_lens: dict[str, list[int]] = {}
        all_hosts: Counter = Counter()
        pdf_sources: Counter = Counter()
        all_sources: Counter = Counter()

        for doc_text, meta in chunks:
            ct = _classify_ct(meta)
            ct_counter[ct] += 1
            L = len((doc_text or "").strip())
            ct_lens.setdefault(ct, []).append(L)
            all_hosts[_host_of(meta)] += 1
            src = (meta.get("source") if meta else "") or ""
            if src:
                all_sources[src] += 1
            if ct == "pdf":
                pdf_sources[src] += 1

        print("=" * 80)
        print(f"=== {ns}  count={cnt}  ({slug}/{kind})")
        print("=" * 80)

        print("  [content type]")
        for ct, c in ct_counter.most_common():
            print(f"    {ct:12s}: {c:5d} ({c*100/cnt:5.1f}%)  len {_stats(ct_lens[ct])}")

        print("  [hosts top 10]")
        for h, c in all_hosts.most_common(10):
            print(f"    {h:55s}: {c:5d} ({c*100/cnt:5.1f}%)")

        print(f"  [unique sources] total={len(all_sources)}, "
              f"avg_chunks/source={cnt/max(1,len(all_sources)):.1f}")

        if pdf_sources:
            n_pdfs = len(pdf_sources)
            sum_chunks = sum(pdf_sources.values())
            print(f"  [PDF 요약] unique_pdfs={n_pdfs}, total_pdf_chunks={sum_chunks}, "
                  f"avg_chunks/pdf={sum_chunks/n_pdfs:.1f}")
            print("  [PDF top 10]")
            for src, c in pdf_sources.most_common(10):
                short = src if len(src) <= 100 else src[:55] + "..." + src[-42:]
                print(f"    chunks={c:3d} | {short}")

        # 가장 큰 단일 source가 NS 전체에서 차지하는 비율 (한 페이지가 많은 청크로 쪼개졌는지)
        if all_sources:
            top_src, top_c = all_sources.most_common(1)[0]
            print(f"  [집중도] top_source={top_c} chunks ({top_c*100/cnt:.1f}%) "
                  f"-- {top_src[:80]}")
        print()

    print("=" * 80)
    print("=== 토픽별 web/local 합계")
    print("=" * 80)
    print(f"  {'topic':30s} {'web':>8s} {'local':>8s} {'total':>8s}")
    for slug, d in sorted(topic_totals.items()):
        tot = d["web"] + d["local"]
        print(f"  {slug:30s} {d['web']:>8d} {d['local']:>8d} {tot:>8d}")


if __name__ == "__main__":
    main()
