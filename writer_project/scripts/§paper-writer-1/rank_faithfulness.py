"""§citation-claim-faithfulness catch83 R2 — rank(상대/대조) 기반 faithfulness 측정 (오프라인, 유료 0).

절대 코사인 negative result → rank 전환. "인용된 abstract가 그 문장의 섹션 pool에서 몇 등인가"로
도메인 공통 오프셋을 상쇄한다.

pool 정의 (catch83 재설계):
    비교집합 = (문장 draft 섹션 pool P) ∪ {인용 chunk C}.  P = 그 섹션 fetch chunk 중 abstract 보유.
    - chunk["section"]은 fetch 출처 태그일 뿐 "인용 허가 섹션"이 아님 → 섹션 불일치 배제(구 misaligned) 폐기.
    - C가 P에 (identity로) 이미 있으면 in_pool=True, m=|P_uniq|. 없으면 강제편입, m=|P_uniq|+1.
    - dedup: 같은 논문(doi>title) 복사본을 비교에서 제외(Beebe 5중 등재 → 자기복제 코사인 1.0 편향 차단).
    - tie: 코사인 정확 동점은 average rank(0.5)로. tie 건수 산출 포함.

마커 (catch83 2단 교정):
    [[1], [2], [7]] 다중묶음을 바깥 [[...]] 덩어리로 잡고 내부 \\d+ 를 참조번호 단위로 분해.
    문장 정제도 덩어리 통째 제거(임베딩 입력 오염 차단). 묶음크기 태그 부착(단독/방증 구분).

성능:
    identity→passage 임베딩 캐시(중복 인코딩 제거) + 섹션당 sims=emat@q 1회(행렬곱 반복 제거).

측정: 임베딩 e5-large(로컬). 문장=query:, abstract=passage:. percentile=(m-rank_pos)/(m-1).
실행: <emb_venv>/bin/python "scripts/§paper-writer-1/rank_faithfulness.py"
출력: rank_faithfulness.json
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parents[1] / "scripts" / "output" / "§paper-writer-1"
DRAFT = OUT_DIR / "paper_consumer_perceived_trademark_similarity_and_likelihood_of_co_20260710_132826.md"
# CHUNKS 인자화: argv[1]=dump 파일명 (기본 240 baseline). 출력은 dump별 파생명(240 결과 보존).
_CHUNKS_NAME = sys.argv[1] if len(sys.argv) > 1 else "chunks_raw_dump.json"
CHUNKS = OUT_DIR / _CHUNKS_NAME
RANK_OUT = OUT_DIR / f"rank_faithfulness_{CHUNKS.stem}.json"
E5_CHAR_LIMIT = 2000   # e5 512토큰 실질 상한 (조건4: 초과분 rank 하위 몰림 검증)

_MARK_CHUNK_RE = re.compile(r"\[\[.*?\]\]")   # 바깥 덩어리(단독+다중묶음+변종 [[#],[[#]] 방어)
_MARK_NUM_RE = re.compile(r"\d+")             # 덩어리 내부 참조번호
_BLOCK_PREFIX_RE = re.compile(r"^\s*(?:[#>]+|[*\-+]\s+|\d+[.)]\s+)")
_HEAD_RE = re.compile(r"(?m)^##\s+\d+\.\s+(.*)$")


def _norm_title(t: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _ident(c: dict) -> str:
    d = (c.get("doi") or "").strip().lower()
    return f"doi:{d}" if d else f"title:{_norm_title(c.get('title'))}"


def _iter_marked_sentences(body: str):
    """(sentence, [(N, bundle_size)...], body_section) yield. draft 한 줄=한 블록 구조 반영."""
    heads = [(m.start(), m.group(1).strip()) for m in _HEAD_RE.finditer(body)]

    def sec_of(pos: int) -> str:
        cur = "(pre)"
        for p, h in heads:
            if p <= pos:
                cur = h
            else:
                break
        return cur

    offset = 0
    for raw in body.split("\n"):
        line_start = offset
        offset += len(raw) + 1  # +1 개행
        line = _BLOCK_PREFIX_RE.sub("", raw).strip()
        if line.startswith("|") or not line:
            continue
        line = " ".join(line.split())
        for s in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"“\[가-힣])', line):
            s = s.strip()
            if not s:
                continue
            pairs_meta: list[tuple[int, int]] = []     # (참조번호, 묶음크기)
            for ch in _MARK_CHUNK_RE.findall(s):
                nums = [int(x) for x in _MARK_NUM_RE.findall(ch)]
                for n in nums:
                    pairs_meta.append((n, len(nums)))  # len(nums)=1 단독, ≥2 묶음
            if not pairs_meta:
                continue
            sec = sec_of(line_start)
            sent_clean = re.sub(r"\s+", " ", _MARK_CHUNK_RE.sub("", s)).strip()  # 덩어리 통째 제거
            yield sent_clean, pairs_meta, sec


def main() -> int:
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))["chunks"]
    n_chunks = len(chunks)
    body = DRAFT.read_text(encoding="utf-8")
    body = body[:body.find("## References")]

    # 섹션별 pool = {identity: 대표 idx} — 먼저 본 것 대표(섹션 내 중복 방어; 현 데이터 0건)
    pool_uniq: dict[str, dict[str, int]] = {}
    for i, c in enumerate(chunks):
        if (c.get("abstract") or "").strip():
            pool_uniq.setdefault(c["section"], {}).setdefault(_ident(c), i)

    model = SentenceTransformer("intfloat/multilingual-e5-large", device="cpu")

    def enc(texts, prefix):
        return model.encode([prefix + t for t in texts], normalize_embeddings=True,
                            batch_size=16, show_progress_bar=False)

    # pool 대표 abstract 임베딩 캐시 + identity→embedding 캐시(중복 인코딩 제거)
    pool_emb: dict[str, tuple[list[str], np.ndarray]] = {}   # sec -> (identities, emb)
    emb_cache: dict[str, np.ndarray] = {}
    pool_full_ratio: dict[str, float] = {}                   # 조건1: 섹션 pool의 full 비율
    for sec, idmap in pool_uniq.items():
        ids = list(idmap.keys())
        emat = enc([chunks[idmap[i]]["abstract"] for i in ids], "passage: ")
        pool_emb[sec] = (ids, emat)
        for k, id_ in enumerate(ids):
            emb_cache[id_] = emat[k]
        srcs = [chunks[idmap[i]].get("abstract_source") for i in ids]
        pool_full_ratio[sec] = round(sum(1 for s in srcs if s == "full") / len(srcs), 3) if srcs else None

    records: list[dict] = []
    for sent, pairs_meta, sec in _iter_marked_sentences(body):
        q = enc([sent], "query: ")[0]
        ids, emat = pool_emb.get(sec, ([], None))
        sims = (emat @ q) if ids else None           # (b) 섹션 sims 1회
        for n, bundle in pairs_meta:
            rec = {"n": n, "body_section": sec, "bundle_size": bundle, "sentence": sent[:200]}
            if n < 1 or n > n_chunks:
                rec["status"] = "out_of_range"
                records.append(rec); continue
            cited = chunks[n - 1]
            rec["cited_title"] = cited.get("title")
            rec["cited_section"] = cited.get("section")
            cabs = (cited.get("abstract") or "").strip()
            if not cabs:
                rec["status"] = "cited_no_abstract"
                records.append(rec); continue
            cid = _ident(cited)
            in_pool = cid in (pool_uniq.get(sec) or {})   # C가 원래 그 섹션 pool 소속?
            # (a) cited embedding 캐시 재사용
            cvec = emb_cache.get(cid)
            if cvec is None:
                cvec = enc([cabs], "passage: ")[0]
                emb_cache[cid] = cvec
            cited_cos = float(np.dot(cvec, q))
            # 비교 대상 = pool 대표 중 C와 '다른 논문'만 (dedup: 동일 identity 복사본 제외)
            other_cos = [float(sims[k]) for k, id_ in enumerate(ids) if id_ != cid] if ids else []
            m = len(other_cos) + 1                        # |P_uniq ∪ {C}|
            better = sum(1 for c in other_cos if c > cited_cos)
            ties = sum(1 for c in other_cos if c == cited_cos)
            rank_pos = better + ties * 0.5 + 1            # average rank
            pct = (m - rank_pos) / (m - 1) if m > 1 else 1.0
            rec.update({"status": "measured", "in_pool": in_pool, "pool_size": m,
                        "cited_abstract_source": cited.get("abstract_source"),
                        "cited_over512": len(cabs) > E5_CHAR_LIMIT,
                        "pool_full_ratio": pool_full_ratio.get(sec),
                        "cited_cos": round(cited_cos, 4), "rank_pos": rank_pos,
                        "ties": ties, "percentile": round(pct, 4), "top3_hit": rank_pos <= 3})
            records.append(rec)

    # ── 집계 ──
    measured = [r for r in records if r["status"] == "measured"]
    status_counts = Counter(r["status"] for r in records)

    def _dist(vals):
        if not vals:
            return None
        s = sorted(vals)
        qq = np.quantile(s, [.25, .5, .75]).tolist()
        return {"n": len(s), "min": round(min(s), 3), "q25": round(qq[0], 3),
                "median": round(qq[1], 3), "mean": round(st.mean(s), 3),
                "q75": round(qq[2], 3), "max": round(max(s), 3)}

    def _cdist(vals):
        if not vals:
            return None
        s = sorted(vals)
        qq = np.quantile(s, [.25, .5, .75]).tolist()
        return {"n": len(s), "min": round(min(s), 4), "q25": round(qq[0], 4),
                "median": round(qq[1], 4), "mean": round(st.mean(s), 4),
                "q75": round(qq[2], 4), "max": round(max(s), 4),
                "std": round(st.pstdev(s), 4) if len(s) > 1 else 0.0}

    def _hist(vals, bins=12):
        if not vals:
            return ""
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-9:
            hi = lo + 1e-9
        w = (hi - lo) / bins
        counts = [0] * bins
        for v in vals:
            counts[min(int((v - lo) / w), bins - 1)] += 1
        mx = max(counts) or 1
        return "\n".join(f"    [{lo+i*w:.3f},{lo+(i+1)*w:.3f}) {c:3d} {'#'*int(round(28*c/mx))}"
                         for i, c in enumerate(counts))

    ccos_all = [r["cited_cos"] for r in measured]
    ip_yes = [r["percentile"] for r in measured if r["in_pool"]]
    ip_no = [r["percentile"] for r in measured if not r["in_pool"]]
    solo = [r["percentile"] for r in measured if r["bundle_size"] == 1]
    multi = [r["percentile"] for r in measured if r["bundle_size"] >= 2]
    BEEBE_NS = {2, 20, 42, 58, 73}
    beebe = [r for r in measured if r["n"] in BEEBE_NS]
    ties_total = sum(r.get("ties", 0) for r in measured)
    over512 = [r["percentile"] for r in measured if r.get("cited_over512")]
    under512 = [r["percentile"] for r in measured if not r.get("cited_over512")]

    out = {
        "source": "rank_faithfulness (catch83 R2, e5-large, 유료 0)",
        "draft": DRAFT.name, "chunks_file": CHUNKS.name,
        "model": "e5-large", "encoding": "query:/passage: (asymmetric)",
        "pool_def": "P_uniq ∪ {C}, dedup by identity, average-rank ties",
        "status_counts": dict(status_counts),
        "n_measured": len(measured), "n_in_pool": len(ip_yes), "n_forced_insert": len(ip_no),
        "cited_cos_dist": _cdist(ccos_all),
        "dist_all": _dist([r["percentile"] for r in measured]),
        "dist_in_pool": _dist(ip_yes),
        "dist_forced_insert": _dist(ip_no),
        "dist_solo": _dist(solo), "dist_bundle": _dist(multi),
        "dist_over512": _dist(over512), "dist_under512": _dist(under512), "n_over512": len(over512),
        "ties_total": ties_total,
        "cited_no_abstract": sum(1 for r in records if r["status"] == "cited_no_abstract"),
        "out_of_range": sum(1 for r in records if r["status"] == "out_of_range"),
        "records": records,
    }
    RANK_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 리포트 (순서: in_pool 건수/분포 → cited_cos → rank×in_pool → rank×bundle → Beebe → 성공기준) ──
    print(f"[saved] {RANK_OUT}")
    print(f"status: {dict(status_counts)}  | ties총 {ties_total}")
    print(f"\n=== [선행] in_pool 건수 (성공기준3 판정 가부) ===")
    print(f"  measured={len(measured)}  in_pool(원래소속)={len(ip_yes)}  forced(강제편입)={len(ip_no)}")
    print(f"  → 강제편입 {'≥5, 성공기준3 판정 가능' if len(ip_no) >= 5 else '<5, 성공기준3 표본부족→판정불가(1·2로만)'}")
    print(f"\n=== [cited_cos 분포] 실패 원인 귀속용 (measured 전체) ===")
    cd = _cdist(ccos_all)
    if cd:
        print(f"  n={cd['n']} min={cd['min']} q25={cd['q25']} median={cd['median']} "
              f"mean={cd['mean']} q75={cd['q75']} max={cd['max']} std={cd['std']}")
        print(_hist(ccos_all))
        span = cd['max'] - cd['min']
        print(f"  → 범위폭={span:.3f}  {'좁은 띠(포화 의심, Y=근거길이)' if span < 0.15 else '넓게 퍼짐(rank 재료는 존재)'}")
    print(f"\n=== ① rank × pool 소속 ===")
    print(f"  in_pool(원래소속) : {_dist(ip_yes)}")
    print(f"  forced(강제편입)  : {_dist(ip_no)}  (n={len(ip_no)})")
    print(f"\n=== ② rank × 묶음 ===")
    print(f"  단독(bundle=1)    : {_dist(solo)}")
    print(f"  묶음(bundle>=2)   : {_dist(multi)}")
    print(f"\n=== [조건4] rank × e5 512토큰 초과 (초과분 하위 몰림 검증) ===")
    print(f"  >2000자(절단권) : {_dist(over512)}  (n={len(over512)})")
    print(f"  <=2000자        : {_dist(under512)}")
    print(f"\n=== ③ Beebe [[2/20/42/58/73]] 집계 ===")
    for r in sorted(beebe, key=lambda x: x["percentile"]):
        print(f"  pct={r['percentile']:.3f} rank {r['rank_pos']}/{r['pool_size']} "
              f"in_pool={r['in_pool']} [[{r['n']}]] sec={r['body_section']}")

    print(f"\n=== ⭐ 성공기준 표적 ===")
    print("  [표적1] '인지과학+상표법 통합' EC섹션 [[5]] (rank 상위 기대):")
    for r in measured:
        if r["n"] == 5 and r["body_section"] == "Expected Contributions":
            print(f"    pct={r['percentile']:.3f} rank {r['rank_pos']}/{r['pool_size']} in_pool={r['in_pool']}")
            print(f"    문장: {r['sentence'][:90]}")
    fdist = _dist(ip_no)
    print(f"  [표적2] Beebe TB/PF 인용 rank (하위 기대): 위 ③ 참조")
    print(f"  [표적3] 강제편입 전부 하위 아님? forced median={fdist['median'] if fdist else 'N/A'} (n={len(ip_no)})")

    print(f"\n--- 최저 percentile 8건 (measured) ---")
    for r in sorted(measured, key=lambda x: x["percentile"])[:8]:
        print(f"  pct={r['percentile']:.3f} rank {r['rank_pos']}/{r['pool_size']} "
              f"bundle={r['bundle_size']} in_pool={r['in_pool']} [[{r['n']}]] "
              f"{(r['cited_title'] or '')[:32]!r} sec={r['body_section']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
