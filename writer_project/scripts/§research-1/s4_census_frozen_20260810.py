# 박제본 — §research-1 S4 계열 (S4 ~ S4-i) 계산 코드. 실행용 아님.
# 원본: writer_project/probe_s4_census.py (untracked, .gitignore:106 probe_*)
# 박제 시점 sha256: d70a723137a4640e1da308c265bb7d8841b93dcdd2472232d213c674ecee06da
#!/usr/bin/env python
"""§research-1 선분3 작업 S4 — 라벨 규모 역산용 span 통계 (a)~(d) + ② 태그별 내역.

비용 $0 · 네트워크 0 · 유료 API 0 · 색인 0 · 파이프라인 `.py` 수정 0.
재료 = R9 산출물(`_s2_probe_html/` 45장 + `_s2_final.json`)만 재사용.

지시 = `CC_HANDOFF_20260809_segment3_S4-S6.md` §2
     + `CC_ADDENDUM_20260809_S4_probe_review.md`  (1차 A~E · F~J · L~O)
     + `CC_ADDENDUM2_20260809_S4_probe_review2.md` (2차 P1~P5 · Q1~Q4)

측정 4값 (인계문 §2-c):
  (a) 잔여 1,241 출현의 고유 문구 수            → 라벨 하한
  (b) 문구별 자수 히스토그램                    → 경계 T 결정 재료
  (c) 문구별 출현 URL 수 분포                   → 전파 배수
  (d) 자수 구간별 양측 출현률                   → T 의 실제 근거  ← 핵심

🔴 (d) 를 `_s2_final.json` 의 `reps` 로 계산할 수 없다 (catch CL — 대표 체인 하나).
   `reps` 는 범주별 **첫 출현** 체인 1건만 저장한다. 양측 출현 판정은 출현 전수의
   체인이 있어야 성립하므로 저장 HTML 에서 **체인을 전량 재계산**한다.
   부수 효과 — `4-구분가능` 레코드의 2번째 이후 cat4 출현이 본문측일 수 있는데
   원본은 그것을 보지 못했다. 이 탐침은 본다.

판정 축 (출현 1건 단위):
  크롬측  = cat_of_one ∈ {1,2,3}                    (구조·이름으로 크롬 식별됨)
  본문측  = cat 4 이고 체인 토큰 - 본문대조 토큰 = ∅ (본문과 구조 동일 = 못 가름)
  중간    = cat 4 인데 차집합 있음(④-구분가능) / 대조군 0 (판정 불가)
            → 제3의 칸. 어느 쪽으로도 밀지 않는다 (catch CM)

양측 출현률 2정의:
  D-strict(하한) : 크롬측{1,2,3}      AND 본문측
  D-loose (상한) : 크롬측{1,2,3}+중간 AND 본문측
STOP 판정은 loose(상한)로 한다 — 멈추는 쪽이 안전 방향 (1차 E).

🔴 `find_chains` 술어 (probe_s2_tagmap.py:178-183, 2차 P2-2 대조용 인용):
     key = norm(span);  len(key) < MIN_SPAN → [];  filter: `key in ntext`
     중복 제거 없음 · soup_nodes 원순서 · ntext 는 text_nodes 가 이미 norm 적용
   아래 `texts` 재구성은 이 술어와 문자 단위로 동일하며, **개수 + 내용** 2중
   assert 로 잠근다. 불일치는 완화하지 않고 전량 수집 후 정지한다.
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_s2_tagmap as P     # noqa: E402  (__main__ 가드 실측 확인 — 2차 P3)
import probe_s2_agg as A        # noqa: E402  (가드 신설 후 import 부작용 0줄 실측)

OUT = P.OUT
STRUCT_TAGS = P.STRUCT_TAGS

# 잔여 모집단 = ②③④-구분가능. ④확정 72 · MISS 51 은 라벨 대상 아님(인계문 §2-b)
POP = {"2", "3", "4-구분가능"}
# 참고값 전용 — ④확정을 포함한 확장 모집단. STOP 판정에 쓰지 않는다.
POP_REF = POP | {"4확정"}

EXPECTED = {"2": 627, "3": 452, "4-구분가능": 162}   # R9 §6-a 박제값
EXPECTED_TOTAL = 1241

STOP_A_MAX = 600                      # (a) 고유 문구 수
STOP_A_BAND = (570, 630)              # ±5% 경계 밴드 (2차 P5-1)
STOP_D_PCT = 20.0                     # (d) T=10 이상 구간 양측 출현률
T_HEADLINE = 10                       # 표제 T (인계문 §2-d 초기 후보)

# Q3 — 육안 덤프 절단 정책. 이 길이 이하는 전문 보존, 초과는 매칭 위치 ±CTX.
FULL_KEEP = 400
CTX = 40

BUCKETS = [(1, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 14), (15, 19),
           (20, 29), (30, 49), (50, 99), (100, 10 ** 9)]

# S4-c 작업 5 — 오탐 판별용 조사·어미 첫 글자 집합.
# 매칭 직후 글자가 한글이면서 이 집합 **밖**이면 "더 긴 낱말의 앞부분"(오탐 후보).
# ⚠️ 이것은 **후보 추출**이다. 확정은 `_s4c_bodyaudit.json` 전량 육안으로 한다
#    (CLAUDE.md §9 — 세는 용도로 정규식/사전을 쓰지 않는다).
PARTICLE = set("이가을를은는의에도와과로으들만부터까지라고나며인입었했하한할함")


def bname(lo, hi):
    return f"{lo}-{hi}" if hi < 10 ** 9 else f"{lo}+"


def bucket_of(L):
    for lo, hi in BUCKETS:
        if lo <= L <= hi:
            return bname(lo, hi)
    return "?"


def struct_tags_in(chain):
    """체인 안의 구조 태그 집합. desc() 형식 `tag#id.cls` 에서 태그명만 뗀다."""
    return {c.split("#")[0].split(".")[0] for c in chain} & STRUCT_TAGS


def nearest_struct(chain):
    """가장 가까운(안쪽) 구조 태그. chain[0] 이 직부모이므로 앞에서부터."""
    for c in chain:
        t = c.split("#")[0].split(".")[0]
        if t in STRUCT_TAGS:
            return t
    return None


def excerpt(text, key):
    """Q3 — 육안 판정용 발췌. 전문이 원칙, 과대할 때만 매칭 위치 ±CTX."""
    if len(text) <= FULL_KEEP:
        return text, False
    i = text.find(key)
    if i < 0:
        return text[:FULL_KEEP] + " …", True
    a, b = max(0, i - CTX), min(len(text), i + len(key) + CTX)
    return ("… " if a else "") + text[a:b] + (" …" if b < len(text) else ""), True


def classify_occ(chain, ctx_tok, ctx_n):
    """🔴 출현 1건의 판정 — **이 함수가 유일한 판정 경로다** (S4-c self-check #36).

    모집단 집계 · 양성대조 ① · 양성대조 ② · 상한 민감도판이 **전부 이 함수를
    호출한다.** 대조가 본선과 다른 경로를 타면 대조로서 성립하지 않으므로
    분기를 복제하지 않는다.

    반환 = (side, cat)  side ∈ {chrome, body, mid}
      chrome = cat_of_one ∈ {1,2,3}
      body   = cat 4 이고 체인토큰[:8] − 대조군토큰 = ∅  (본문과 구조 동일)
      mid    = cat 4 인데 차집합 있음 / 대조군 0 (판정 불가) — catch CM 제3의 칸

    ⚠️ 토큰화 범위 비대칭은 원본 유지 (1차 addendum H):
       히트 = chain[:8] · 대조군 = 체인 전체 (probe_s2_agg.build_body_ctx)
    """
    c = P.cat_of_one(chain)
    if c in ("1", "2", "3"):
        return "chrome", c
    if not ctx_n:
        return "mid", c
    extra = A.tokens(chain[:8]) - ctx_tok
    return ("body" if not extra else "mid"), c


def select_body_nodes(nodes_u, keys, th, cap):
    """`A.build_body_ctx` 의 대조군 선정 루프와 **같은 술어**로 노드를 고르되
    **`nodes_u` 인덱스·텍스트**를 체인과 함께 돌려준다 (양성대조 ① 재료).

    `build_body_ctx` 는 인덱스·텍스트를 버리므로 재현이 불가피하다.
    🔴 `probe_s2_agg.py` 는 수정하지 않는다(S4-c·S4-d 지시) — 대신 원본판(cap=8)
    결과를 `body_ctx` 의 `n`·`chains` 와 **대조 assert** 로 잠근다.

    반환 = [(idx, text, chain), …]   idx = `nodes_u` 안의 위치
    🔴 S4-d #45 — 노드 동일성 판정의 기준을 **인덱스**로 삼기 위해 필요하다.
       텍스트 비교로는 같은 문장이 두 노드에 있을 때 갈리지 않는다.
    """
    got = []
    for i, (t, node) in enumerate(nodes_u):
        if len(t) < th or any(k in t for k in keys):
            continue
        got.append((i, t, P.chain_of(node)))
        if len(got) >= cap:
            break
    return got


def extract_probe_phrases(sel, min_len=10, max_len=60, cap=20):
    """🔴 양성대조 ① 어구 추출 규칙 — **코드로 고정한다** (self-check #35).

    1. 재료 = `select_body_nodes` 산출 `[(idx, text, chain)]`
    2. 텍스트를 공백으로 어절 분할 (텍스트는 이미 `P.norm` 적용 = 공백 1개)
    3. 연속 **2어절·3어절**을 공백 1개로 결합
    4. 길이 `min_len` 이상 `max_len` 이하만 채택
    5. 등장 순서 유지 중복 제거
    6. URL 당 상한 `cap` 건 (앞에서부터)

    임의 선별이 아니다. 노드 순서·어절 순서에만 의존하는 결정적 규칙이다.

    반환 = [(phrase, src_idx), …]  src_idx = 그 어구를 **뽑아온 노드**의 인덱스
    """
    out, seen = [], set()
    for idx, t, _chain in sel:
        w = t.split(" ")
        for i in range(len(w)):
            for k in (2, 3):
                if i + k > len(w):
                    continue
                ph = " ".join(w[i:i + k])
                if not (min_len <= len(ph) <= max_len) or ph in seen:
                    continue
                seen.add(ph)
                out.append((ph, idx))
                if len(out) >= cap:
                    return out
    return out


def hint_names(chain):
    """cat3 을 발동시킨 실제 class/id 이름과 걸린 사전 항목을 짝지어 돌려준다.

    `P.cat_of_one` 은 `" ".join(chain).lower()` 에 사전 항목이 들어 있는지만 본다.
    어느 이름이 걸었는지는 남기지 않으므로 여기서 사후 복원한다(로직 미개입).
    반환 = [(체인요소, 걸린 사전항목), …]
    """
    out = []
    for c in chain:
        cl = c.lower()
        for k in P.CLASSID_HINTS:
            if k in cl:
                out.append((c, k))
    return out


def hint_detail(chain):
    """S4-e §3-a — 발동 근거를 **어느 문자열의 어느 부분**까지 낸다.

    `probe_s2_tagmap.py:195` 는 `k in " ".join(chain).lower()` 평문 부분일치다.
    여기서는 체인 요소별로 다시 걸어 다음을 남긴다:
      element  = 체인 요소 원문
      hint     = 걸린 사전 항목
      token    = 그 항목을 품은 토큰(비영숫자로 분할한 조각)
      exact    = hint == token       (완전일치)
      partial  = hint ⊂ token, ≠     (부분일치)  ← catch CP 기전
    """
    out = []
    for c in chain:
        cl = c.lower()
        toks = [x for x in re.split(r"[^a-z0-9]+", cl) if x]
        for k in P.CLASSID_HINTS:
            if k not in cl:
                continue
            owners = [t for t in toks if k in t] or ["(토큰경계 밖)"]
            for t in owners:
                out.append({"element": c, "hint": k, "token": t,
                            "exact": t == k, "partial": (k in t and t != k)})
    return out


def top_family(element):
    """S4-f §3-b — `top` **완전일치**가 어디서 왔는지 가른다 (CP-2 분해).

    `desc()` 형식은 `tag#id.cls1.cls2` 다.
      `#top` 조각을 가지면        → id=top
      `margin-top` 문자열을 가지면 → margin-top (CSS 여백 유틸리티)
      그 밖                       → 기타
    """
    el = element.lower()
    if re.search(r"#top(?:\.|$)", el):
        return "id=top"
    if "margin-top" in el:
        return "margin-top"
    return "기타 top 완전일치"


# 🔴 S4-h §4-b — 배치·간격 접두어. **이 목록을 임의로 늘리거나 줄이지 않는다.**
#    추가 후보(`u-`·`is-`·`js-` 등)는 표제에 넣지 않고 별도 관측으로만 보고한다.
LAYOUT_PREFIXES = ("layout-", "grid-", "flex-", "col-", "row-",
                   "spacer-", "glue-", "gap-",
                   "margin-", "padding-", "mt-", "mb-", "pt-", "pb-")
GLOBAL_TAGS = {"html", "body"}


def segments(element):
    """`desc()` 형식 `tag#id.cls1.cls2` 를 **태그 / id / class 조각**으로 가른다.

    접두어 매칭의 **경계**를 여기서 준다 — 조각 단위로 `startswith` 를 보므로
    `margin-` 은 `margin-top` 에 걸리고 `submargin-x` 에는 걸리지 않는다.
    """
    tag = element.split("#")[0].split(".")[0]
    rest = element[len(tag):]
    segs = [s for s in re.split(r"[#.]", rest) if s]
    return tag, segs


def is_layout_seg(seg):
    return any(seg.lower().startswith(p) for p in LAYOUT_PREFIXES)


def hint_segments(element, hint):
    """그 hint 를 품은 **조각**들. 없으면 태그명 자체가 근거인 경우다."""
    tag, segs = segments(element)
    owners = [s for s in segs if hint in s.lower()]
    if not owners and hint in tag.lower():
        owners = [f"<{tag}>"]
    return owners


def stop_verdict(st_pct, ls_pct, thr):
    """1차 E — 3상태. loose 기준, strict≤thr<loose 는 경계(확정 금지)."""
    if ls_pct <= thr:
        return "미발동"
    if st_pct > thr:
        return "🔴 발동"
    return "⚠️ 경계 — 확정 금지, 챗 판정"


def pct(a, b):
    """P4 — 분모 0 가드. 0이면 None 을 돌려주고 호출부가 n/a 로 찍는다."""
    return None if not b else 100.0 * a / b


def fpct(v):
    return "n/a (모집단 0)" if v is None else f"{v:.1f}%"


def main():
    final = json.loads((OUT / "_s2_final.json").read_text(encoding="utf-8"))
    rows, full, frag = P.parse_r8()
    url_chunks = defaultdict(list)
    for n, r in rows.items():
        url_chunks[r["url"]].append(n)

    # ── 0. 모집단 확정 + 🔴 A. 양성 대조 assert ────────────────────
    pop_recs, ref_recs = [], []
    pair_final = defaultdict(set)      # (span,url) -> set(final)   ← J 에서 읽는다
    for k, ch in final.items():
        u = ch["meta"]["url"]
        for s in ch["spans"]:
            if s["final"] in POP_REF:
                ref_recs.append((int(k), u, s["span"], s["final"]))
            if s["final"] not in POP:
                continue
            pop_recs.append((int(k), u, s["span"], s["final"]))
            pair_final[(s["span"], u)].add(s["final"])

    by_fin = Counter(f for *_, f in pop_recs)
    assert by_fin == Counter(EXPECTED), f"모집단 불일치: {dict(by_fin)} != {EXPECTED}"
    assert len(pop_recs) == EXPECTED_TOTAL, f"레코드 {len(pop_recs)} != {EXPECTED_TOTAL}"
    print(f"[A] 양성 대조 assert 통과 — 레코드 {len(pop_recs)} · {dict(by_fin)}")

    pairs = sorted(pair_final)
    phrases = sorted({p for p, _ in pairs})
    ref_pairs = sorted({(sp, u) for _n, u, sp, _f in ref_recs})
    print(f"[모집단] 레코드 {len(pop_recs)} · (문구,URL) 쌍 {len(pairs)} · "
          f"고유 문구 {len(phrases)}")
    print(f"[참고 모집단] ④확정 포함 레코드 {len(ref_recs)} · 쌍 {len(ref_pairs)}")

    # ── M. span → urls 를 1회 구성 (완전탐색 회피) ─────────────────
    p2u = defaultdict(list)
    for sp, u in pairs:
        p2u[sp].append(u)

    # ── 🔴 J. pair_final 다중 verdict 쌍 계상 ─────────────────────
    multi = {k: sorted(v) for k, v in pair_final.items() if len(v) > 1}
    print(f"\n[J] 같은 (문구,URL)이 청크마다 다른 verdict 를 받은 쌍 = {len(multi)}")
    for combo, c in Counter("+".join(v) for v in multi.values()).most_common():
        print(f"    {combo} : {c}")

    # ── 1. 대조군 — 🔴 D. probe_s2_agg 를 import 해서 그대로 호출 ──
    body_ctx, nodes = A.build_body_ctx(url_chunks, frag, full, keep_nodes=True)
    zero_ctl = sorted(u for u in body_ctx if not body_ctx[u]["n"])
    print(f"\n[대조군] MIN_CTL={A.MIN_CTL} (probe_s2_agg 상수) · 페이지 {len(nodes)} · "
          f"0건 URL {len(zero_ctl)}")
    for u in zero_ctl:
        print(f"    0건: {u[:90]}")

    # ── 2. 출현 전량 재계산 (catch CL 회피) ───────────────────────
    # 🔴 P2 — 개수 assert + 내용 assert. 불일치는 즉사시키지 않고 전량 수집 후 정지.
    occ, hitdump = {}, {}
    bad_count, bad_content = [], []
    tri3 = {}             # S4-f 작업1 — ③ 쌍별 트리거 (전체 체인). 루프에서 채운다
    for sp, u in ref_pairs:
        if u not in nodes:
            occ[(sp, u)] = None
            continue
        hits = P.find_chains(nodes[u], sp)
        key = P.norm(sp)
        texts = [t for t, _n in nodes[u] if key in t] if len(key) >= P.MIN_SPAN else []
        if len(texts) != len(hits):
            bad_count.append({"span": sp, "url": u,
                              "texts": len(texts), "hits": len(hits)})
            continue
        for t in texts:
            if key not in P.norm(t):
                bad_content.append({"span": sp, "url": u, "text": t[:80]})
        rec = {"chrome": 0, "body": 0, "mid": 0, "n": len(hits),
               "structs": Counter(), "nearest": Counter()}
        det = []
        ctx = body_ctx.get(u, {})
        for h, t in zip(hits, texts):
            # 🔴 판정은 classify_occ 하나로만 한다 (S4-c #36). 분기 복제 금지.
            side, c = classify_occ(h["chain"], ctx.get("tok", set()), ctx.get("n"))
            rec[side] += 1
            if side == "chrome" and c in ("1", "2"):
                for tg in struct_tags_in(h["chain"]):
                    rec["structs"][tg] += 1
                nt = nearest_struct(h["chain"])
                if nt:
                    rec["nearest"][nt] += 1
            if c == "3":
                # 🔴 S4-f 작업1 — ③ 트리거 분해. **전체 체인**으로 본다.
                #    `_s2_final.json` 의 reps 는 chain[:8] 절단본이라
                #    452 중 65(14.4%)에서 트리거가 안 보인다(실측) → 여기서 낸다.
                d3 = tri3.setdefault((sp, u), {"exact": Counter(),
                                               "partial": Counter(),
                                               "topfam": Counter(), "occ": 0,
                                               "texts": [], "chains": []})
                d3["occ"] += 1
                # S4-g — 육안 재료. 노드 텍스트와 **전체 체인**을 함께 남긴다.
                d3["texts"].append(t[:300] + (" …" if len(t) > 300 else ""))
                d3["chains"].append(h["chain"])
                for t in hint_detail(h["chain"]):
                    if t["exact"]:
                        d3["exact"][t["hint"]] += 1
                        if t["hint"] == "top":
                            d3["topfam"][top_family(t["element"])] += 1
                    else:
                        d3["partial"][f'{t["hint"]}⊂{t["token"]}'] += 1
            ex, cut = excerpt(t, key)
            row = {"side": side, "cat": c, "node_text": ex,
                   "truncated": cut, "full_len": len(t),
                   "chain": h["chain"][:8]}
            if side == "body":
                # S4-c 작업 5 — body 전건 오탐 감사용. 노드 안 **모든** 매칭 위치의
                # 앞뒤 30자를 남긴다(대표 1건 아님 — catch CL).
                row["ctxs"] = [t[max(0, m.start() - 30):m.end() + 30]
                               for m in re.finditer(re.escape(key), t)]
            det.append(row)
        occ[(sp, u)] = rec
        hitdump[(sp, u)] = det

    print(f"\n[P2] 짝짓기 검증 — 개수 불일치 {len(bad_count)} · 내용 불일치 "
          f"{len(bad_content)}  (0/0 이어야 정상)")
    if bad_count or bad_content:
        for x in (bad_count + bad_content)[:20]:
            print(f"    {x}")
        print("🔴 정지 — assert 를 완화하지 않는다. 술어 불일치를 보고한다.")
        sys.exit(2)

    # ── 🔴 F. 결손 2원인 분리 계상 ────────────────────────────────
    miss_nohtml = [k for k in pairs if occ.get(k) is None]
    miss_zero = [k for k in pairs if occ.get(k) is not None and occ[k]["n"] == 0]
    print(f"\n[F] 결손 2분할 — HTML 부재 {len(miss_nohtml)} · 파일 있으나 0출현 "
          f"{len(miss_zero)}")
    for sp, u in miss_zero[:10]:
        print(f"    0출현: {sp[:50]!r}  {u[:60]}")
    if len(miss_zero) > 10:
        print(f"    … 외 {len(miss_zero)-10}건 (전량은 _s4_census.json)")

    # ── 3. (a) 고유 문구 수 ───────────────────────────────────────
    print(f"\n(a) 고유 문구 수 = {len(phrases)}")

    # ── 4. (b) 자수 히스토그램 — I: 1자 버킷 명시, 0건도 찍는다 ────
    hb = Counter(bucket_of(len(p)) for p in phrases)
    print("\n(b) 문구별 자수 히스토그램 (고유 문구 기준)")
    for lo, hi in BUCKETS:
        k = bname(lo, hi)
        print(f"    {k:>8} : {hb.get(k, 0):>4}")
    print(f"    {'?':>8} : {hb.get('?', 0):>4}   ← 버킷 밖(있으면 설계 오류)")
    lt10 = sum(1 for p in phrases if len(p) < T_HEADLINE)
    print(f"    합계 {sum(hb.values())} = 10자 미만 {lt10} + 10자 이상 "
          f"{len(phrases)-lt10}")

    # ── 5. (c) 문구별 출현 URL 수 분포 ────────────────────────────
    purl = {sp: len(us) for sp, us in p2u.items()}
    cd = Counter(purl.values())
    print("\n(c) 문구별 출현 URL 수 분포")
    for k in sorted(cd):
        print(f"    {k:>3} URL : {cd[k]:>4} 문구")
    ratio = (lambda a, b: "n/a (분모 0)" if not b else f"{a/b:.3f}")
    print(f"    → 전파 배수(쌍/문구)       = {len(pairs)}/{len(phrases)} = "
          f"{ratio(len(pairs), len(phrases))}")
    print(f"    → 레코드 배수(레코드/문구) = {len(pop_recs)}/{len(phrases)} = "
          f"{ratio(len(pop_recs), len(phrases))}")

    # ── 6. (d) 양측 출현률 ────────────────────────────────────────
    # G — 결손 제외판: 대조군 0건 URL · HTML 부재 · 0출현 쌍을 뺀다.
    def aggregate(plist, pair_filter):
        agg = {}
        for sp in plist:
            us = [u for u in p2u[sp] if pair_filter(sp, u)]
            if not us:
                continue
            ch = bd = md = 0
            for u in us:
                r = occ.get((sp, u))
                if not r or not r["n"]:
                    continue
                ch += r["chrome"]; bd += r["body"]; md += r["mid"]
            agg[sp] = (ch, bd, md)
        return agg

    def ok_pair(sp, u):
        r = occ.get((sp, u))
        return bool(r and r["n"] and body_ctx.get(u, {}).get("n"))

    agg_all = aggregate(phrases, lambda sp, u: True)
    agg_clean = aggregate(phrases, ok_pair)

    inpage = {sp for (sp, u), r in occ.items()
              if r and r["chrome"] and r["body"] and (sp, u) in pair_final}

    def dtable(agg, label):
        print(f"\n(d-{label}) 자수 구간별 양측 출현률   [모집단 문구 {len(agg)}]")
        print(f"    {'구간':>8} {'문구':>5} {'strict':>7} {'%':>7} "
              f"{'loose':>7} {'%':>7} {'페이지내':>8}")
        tab = {}
        for lo, hi in BUCKETS:
            k = bname(lo, hi)
            ps = [p for p in agg if lo <= len(p) <= hi]
            if not ps:
                continue
            st = [p for p in ps if agg[p][0] and agg[p][1]]
            ls = [p for p in ps if (agg[p][0] or agg[p][2]) and agg[p][1]]
            ip = [p for p in ps if p in inpage]
            tab[k] = {"n": len(ps), "strict": len(st), "loose": len(ls),
                      "inpage": len(ip)}
            print(f"    {k:>8} {len(ps):>5} {len(st):>7} "
                  f"{fpct(pct(len(st), len(ps))):>7} {len(ls):>7} "
                  f"{fpct(pct(len(ls), len(ps))):>7} {len(ip):>8}")
        return tab

    tab_all = dtable(agg_all, "전체")
    tab_clean = dtable(agg_clean, "결손제외")

    # ── 7. T 후보별 — 🔴 C. <T 단위 3값 병기 ──────────────────────
    print("\n[T 후보별] ≥T 양측 출현률 + <T 라벨 단위 3값")
    trow = {}
    for T in (8, 10, 12, 15, 20):
        for label, agg in (("전체", agg_all), ("결손제외", agg_clean)):
            ge = [p for p in agg if len(p) >= T]
            st = sum(1 for p in ge if agg[p][0] and agg[p][1])
            ls = sum(1 for p in ge if (agg[p][0] or agg[p][2]) and agg[p][1])
            st_p, ls_p = pct(st, len(ge)), pct(ls, len(ge))
            n1 = sum(1 for (ss, _u) in pairs if len(ss) < T)
            n2 = sum(1 for (_n, _u, ss, _f) in pop_recs if len(ss) < T)
            n3 = sum(occ[(ss, u)]["n"] for (ss, u) in pairs
                     if len(ss) < T and occ.get((ss, u)))
            v = ("판정 불가 (≥T 문구 0건)" if st_p is None
                 else stop_verdict(st_p, ls_p, STOP_D_PCT))
            trow[f"T{T}-{label}"] = {
                "ge": len(ge), "strict": st,
                "strict_pct": None if st_p is None else round(st_p, 2),
                "loose": ls, "loose_pct": None if ls_p is None else round(ls_p, 2),
                "lt_pair": n1, "lt_record": n2, "lt_occ": n3,
                "label_est": [len(ge) + n1, len(ge) + n2, len(ge) + n3],
                "verdict": v}
            print(f"  T={T:>2} [{label:>4}] ≥T문구 {len(ge):>4} | strict {st:>3} "
                  f"({fpct(st_p)}) loose {ls:>3} ({fpct(ls_p)}) → {v}")
            print(f"           <T 단위: 쌍 {n1} · 레코드 {n2} · 페이지출현 {n3}"
                  f"  → 역산 라벨 = {len(ge)} + [{n1} | {n2} | {n3}]"
                  f" = [{len(ge)+n1} | {len(ge)+n2} | {len(ge)+n3}]")

    # ── 8. 참고값 — ④확정 포함 확장 모집단 (Q2: 변수명 분리) ───────
    ref_phr = sorted({sp for sp, _u in ref_pairs})
    r2u = defaultdict(list)
    for sp, u in ref_pairs:
        r2u[sp].append(u)
    agg_ref = {}
    for sp in ref_phr:
        ch = bd = md = 0
        for u in r2u[sp]:
            r = occ.get((sp, u))
            if not r or not r["n"]:
                continue
            ch += r["chrome"]; bd += r["body"]; md += r["mid"]
        agg_ref[sp] = (ch, bd, md)
    ref_ge = [p for p in agg_ref if len(p) >= T_HEADLINE]
    ref_st = sum(1 for p in ref_ge if agg_ref[p][0] and agg_ref[p][1])
    ref_ls = sum(1 for p in ref_ge if (agg_ref[p][0] or agg_ref[p][2]) and agg_ref[p][1])
    ref_ls_p = pct(ref_ls, len(ref_ge))
    base_ls_p = trow.get(f"T{T_HEADLINE}-전체", {}).get("loose_pct")
    # Q1 — 사전 논증이 아니라 실측 부호로 방향어를 결정한다.
    if ref_ls_p is None or base_ls_p is None:
        ref_line = "→ 차분 산출 불가 (한쪽 모집단 0)"
    else:
        d = base_ls_p - ref_ls_p
        arrow = "하향" if d < 0 else ("상향" if d > 0 else "무")
        ref_line = (f"→ 잔여 모집단은 ④확정을 뺀 만큼 {arrow} 편향으로 관측됨 "
                    f"({d:+.1f}%p)")
    print(f"\n[참고] ④확정 포함 T={T_HEADLINE} — 문구 {len(ref_ge)} · "
          f"strict {ref_st} ({fpct(pct(ref_st, len(ref_ge)))}) · "
          f"loose {ref_ls} ({fpct(ref_ls_p)})")
    print(f"       잔여 모집단 loose {fpct(base_ls_p)}  {ref_line}")

    # ── 9. ② 627 의 태그별 내역 ──────────────────────────────────
    two_multi, two_near, two_only = Counter(), Counter(), Counter()
    two_n = 0
    for _n, u, sp, fin in pop_recs:
        if fin != "2":
            continue
        two_n += 1
        r = occ.get((sp, u))
        if not r or not r["structs"]:
            two_multi["(태그 미확인)"] += 1
            two_only["(태그 미확인)"] += 1
            two_near["(태그 미확인)"] += 1
            continue
        s = set(r["structs"])
        for t in s:
            two_multi[t] += 1
        two_only["+".join(sorted(s))] += 1
        two_near[r["nearest"].most_common(1)[0][0] if r["nearest"] else "?"] += 1
    print(f"\n② 태그별 내역 (레코드 {two_n})")
    print("  [중복허용] " + "  ".join(f"{k}={v}" for k, v in two_multi.most_common()))
    print("  [조합배타] " + "  ".join(f"{k}={v}" for k, v in two_only.most_common()))
    print("  [최근접]   " + "  ".join(f"{k}={v}" for k, v in two_near.most_common()))
    hdr_any, hdr_only = two_multi.get("header", 0), two_only.get("header", 0)

    # ══════════════════════════════════════════════════════════════════
    # S4-c — (d) 검정력 확정 (지시 `CC_S4c_20260809_power_control.md`)
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 74)
    print("S4-c")
    print("=" * 74)

    # ── S4c-0. 환경 캡처 + R9/S4 재현 대조 (재실행 없이) ────────────
    import platform
    import bs4 as _bs4
    import lxml.etree as _ET
    env = {"python": platform.python_version(), "executable": sys.executable,
           "bs4": _bs4.__version__, "lxml": _ET.__version__,
           "libxml2": ".".join(map(str, _ET.LIBXML_VERSION)),
           "platform": platform.platform(), "cwd": str(Path.cwd())}
    print("[env] " + " · ".join(f"{k}={v}" for k, v in env.items()
                                if k in ("python", "bs4", "lxml", "libxml2")))
    print(f"[env] venv={env['executable']}")
    print(f"[env] cwd={env['cwd']}")

    r9now = Counter(s["final"] for ch in final.values() for s in ch["spans"])
    R9EXP = {"2": 627, "3": 452, "4-구분가능": 162, "4확정": 72,
             "SPLIT": 9, "DRIFT": 42}
    r9_ok = dict(r9now) == R9EXP
    print(f"[R9 재현] {dict(sorted(r9now.items()))} · 전항 일치 = {r9_ok}")

    prev_path = OUT / "_s4_census.json"
    bm_now = {u: {"n": v["n"], "th": v["th"]} for u, v in body_ctx.items()}
    bm_ok = None
    if prev_path.exists():
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        bm_ok = prev.get("body_meta") == bm_now
        print(f"[대조군 동일성] S4(.venv_vertex) body_meta == 현재 = {bm_ok}  "
              f"← dump 확장 무영향 + 크로스 venv 대조")
        print(f"[S4 재현] phrases {prev['phrases']}=={len(phrases)} · "
              f"pairs {prev['pairs']}=={len(pairs)}")

    # ── S4c-작업4. 45장 vs 43 URL 차집합 ──────────────────────────
    html_files = sorted(p.name for p in P.HTMLDIR.glob("*.html"))
    expect_files = {P.slug(u) + ".html" for u in url_chunks}
    extra_files = sorted(set(html_files) - expect_files)
    missing_files = sorted(expect_files - set(html_files))
    print(f"\n[작업4] HTML {len(html_files)}장 · R8 65청크 고유 URL "
          f"{len(url_chunks)} · 차집합 {len(extra_files)} · 파일없는URL "
          f"{len(missing_files)}")
    for f in extra_files:
        print(f"    HTML 에만: {f}")
    # `expect_files` 는 rows URL 에서 만든 집합이므로 `extra_files` 는 정의상
    # rows 에 없다. 정지 조건은 그 반대 방향 — rows 에 있는데 HTML 이 없는 경우다.
    print(f"    → rows 에 있는데 HTML 이 없는 URL = {len(missing_files)} "
          f"{'🔴 정지 대상' if missing_files else '(0건 — 판정 누락 없음)'}")

    # ── S4c-작업1 / S4d-작업1. 양성대조 ① + 🔴 위치 분해 ────────────
    # 🔴 S4-d #45 — 노드 동일성은 **`nodes[u]` 인덱스**로 판정한다.
    #    텍스트 비교가 아니다. 인덱스 일치 ⟺ 객체 동일이며, 그 등가성도
    #    `is` 비교로 매 히트마다 assert 한다(아래 same_obj).
    pc1 = {"chrome": 0, "body": 0, "mid": 0}
    pc1_by_url, pc1_rows = {}, []
    pos = {}          # (side/cat 구분) -> {"same": n, "other": n}
    trig = Counter()  # 동일 노드 cat3 을 발동시킨 (이름, 사전항목)
    trig_url = {}
    purity = {"1": 0, "2": 0, "3": 0, "4": 0}
    purity_by_url = {}
    # S4-e — 육안 103건. 🔴 텍스트와 이름을 **별도 파일**로 낸다 (#52 순서 강제)
    s4e_text, s4e_name = [], []
    same_full = []        # S4-e 작업2 — 349 전량 전체체인 판정

    def bump(k, same):
        d = pos.setdefault(k, {"same": 0, "other": 0})
        d["same" if same else "other"] += 1

    for u in sorted(nodes):
        th = body_ctx[u]["th"]
        if th is None:                      # 대조군 0건 URL — 되먹일 것이 없다
            pc1_by_url[u] = {"skip": "대조군 0건"}
            purity_by_url[u] = {"skip": "대조군 0건"}
            continue
        keys = [k for k in A.chrome_keys_of(u, url_chunks, frag, full)
                if len(k) >= P.MIN_KEY]
        sel = select_body_nodes(nodes[u], keys, th, 8)
        # 🔴 원본 대조군과 동일 선택임을 잠근다 (복제 아님을 증명)
        assert len(sel) == body_ctx[u]["n"], (
            f"대조군 재현 실패 {u}: {len(sel)} != {body_ctx[u]['n']}")
        assert [c[:6] for _i, _t, c in sel[:3]] == body_ctx[u]["chains"], (
            f"대조군 체인 불일치 {u}")

        # ── S4e-작업1. cat3 견본 노드 전건 수집 (육안 103건 본체) ──
        # 🔴 체인을 **자르지 않는다** — S4-d 미판정 134 의 원인이 chain[:8] 이었다.
        for _i, _t, _c in sel:
            if P.cat_of_one(_c) != "3":
                continue
            hd = hint_detail(_c)
            s4e_text.append({"id": len(s4e_text) + 1, "url": u,
                             "chars": len(_t), "text": _t})
            s4e_name.append({"id": len(s4e_name) + 1, "url": u,
                             "chain": _c, "triggers": hd,
                             "any_exact": any(h["exact"] for h in hd),
                             "all_partial": bool(hd) and not any(h["exact"] for h in hd)})

        # ── S4d-작업2. 대조군 순도 — **사후 분류만.** 선정 로직 미개입 ──
        pu = Counter(P.cat_of_one(c) for _i, _t, c in sel)
        for k4 in ("1", "2", "3", "4"):
            purity[k4] += pu.get(k4, 0)
        nsel = sum(pu.values())
        purity_by_url[u] = {"th": th, "n": nsel, **{k4: pu.get(k4, 0)
                                                    for k4 in ("1", "2", "3", "4")},
                            "chrome_pct": round(100 * (nsel - pu.get("4", 0)) / nsel, 1)
                            if nsel else None}

        probes = extract_probe_phrases(sel)
        cnt = {"chrome": 0, "body": 0, "mid": 0}
        for ph, src_idx in probes:
            hits = P.find_chains(nodes[u], ph)
            key_ph = P.norm(ph)
            idxs = ([i for i, (t, _n) in enumerate(nodes[u]) if key_ph in t]
                    if len(key_ph) >= P.MIN_SPAN else [])
            assert len(idxs) == len(hits), (
                f"인덱스/히트 개수 불일치 {ph!r} {u}: {len(idxs)}!={len(hits)}")
            for h, i in zip(hits, idxs):
                side, c = classify_occ(h["chain"], body_ctx[u]["tok"],
                                       body_ctx[u]["n"])
                same = (i == src_idx)
                # 인덱스 동일 ⟺ 객체 동일 을 매 건 검증 (#45)
                assert same == (nodes[u][i][1] is nodes[u][src_idx][1]), (
                    f"인덱스-객체 동일성 어긋남 {ph!r} {u}")
                cnt[side] += 1
                pc1[side] += 1
                bump(f"{side}/cat{c}", same)
                bump(side, same)
                if same and side == "chrome" and c == "3":
                    for nm, hk in hint_names(h["chain"]):
                        trig[(nm, hk)] += 1
                        trig_url.setdefault((nm, hk), u)
                    # 🔴 S4-e 작업2 — **전체 체인**으로 판정. 절단 없음 → 미판정 0
                    hd = hint_detail(h["chain"])
                    same_full.append({"url": u, "phrase": ph,
                                      "n_trig": len(hd),
                                      "any_exact": any(x["exact"] for x in hd),
                                      "all_partial": bool(hd) and not any(
                                          x["exact"] for x in hd)})
                if side != "body":
                    pc1_rows.append({"url": u, "phrase": ph, "side": side,
                                     "cat": c, "same_node": same,
                                     "hit_idx": i, "src_idx": src_idx,
                                     "chain": h["chain"][:8]})
        pc1_by_url[u] = {"th": th, "sel": len(sel), "probes": len(probes), **cnt}
    n1 = sum(pc1.values())
    print(f"\n[작업1 · 양성대조 ①] 되먹임 어구 출현 N={n1}")
    for k in ("chrome", "body", "mid"):
        print(f"    {k:<7} {pc1[k]:>5}  {fpct(pct(pc1[k], n1))}")

    print("\n[S4d 작업1 · 위치 분해]  동일성 판정 = nodes[u] 인덱스 (+객체 is 검증)")
    print(f"    {'구분':<14}{'전체':>6}{'동일노드':>8}{'타위치':>8}{'동일%':>8}")
    for k in ("body", "chrome", "mid", "chrome/cat1", "chrome/cat2",
              "chrome/cat3", "mid/cat4", "body/cat4"):
        d = pos.get(k)
        if not d:
            continue
        tt = d["same"] + d["other"]
        print(f"    {k:<14}{tt:>6}{d['same']:>8}{d['other']:>8}"
              f"{fpct(pct(d['same'], tt)):>8}")
    c3 = pos.get("chrome/cat3", {"same": 0, "other": 0})
    c3t = c3["same"] + c3["other"]
    print(f"    → 🔴 동일 노드 cat3 비율 = {c3['same']}/{c3t} = "
          f"{fpct(pct(c3['same'], c3t))}   [챗 기준 ≥30% / 5~30% / <5%]")

    print("\n[S4d 작업1-e · 동일 노드 cat3 발동 이름 상위 20]")
    print(f"    {'이름':<44}{'사전항목':<10}{'건':>4}  대표 URL")
    for (nm, hk), v in trig.most_common(20):
        print(f"    {nm[:43]:<44}{hk:<10}{v:>4}  {trig_url[(nm, hk)][:44]}")
    if not trig:
        print("    (0건)")

    print("\n[S4d 작업2 · 대조군 순도]  ⚠️ 사후 분류. build_body_ctx 미개입")
    npu = sum(purity.values())
    print(f"    선택 체인 N={npu} · cat1 {purity['1']} · cat2 {purity['2']} · "
          f"cat3 {purity['3']} · cat4 {purity['4']}")
    print(f"    → 크롬 판정 비율 = {npu - purity['4']}/{npu} = "
          f"{fpct(pct(npu - purity['4'], npu))}  (대조① chrome 42.0% 중 정당한 몫의 상한)")
    print(f"    비-body {len(pc1_rows)}행 전량 → _s4c_control.json")

    # ── S4e-작업2. 349 전량 전체체인 재판정 (미판정 0) ───────────────
    sf_all = len(same_full)
    sf_part = sum(1 for x in same_full if x["all_partial"])
    sf_exact = sum(1 for x in same_full if x["any_exact"])
    sf_none = sum(1 for x in same_full if not x["n_trig"])
    print(f"\n[S4e 작업2 · 절단 해제] 동일노드 cat3 {sf_all} 전량 전체체인 판정")
    print(f"    완전일치 포함 {sf_exact} · 🔴 부분일치만 {sf_part} "
          f"({fpct(pct(sf_part, sf_all))}) · 트리거 0 {sf_none}  ← 미판정 0")
    print("    부분일치만 인 건의 URL 분포: " + str(dict(Counter(
        x["url"][:46] for x in same_full if x["all_partial"]))))

    # ── S4e-작업3. 견본 100% 크롬 URL 특정 + body 기여 ───────────────
    body_by_url = Counter()
    for (sp, u) in pairs:
        r = occ.get((sp, u))
        if r:
            body_by_url[u] += r["body"]
    pure100 = sorted(u for u, v in purity_by_url.items()
                     if "skip" not in v and v["chrome_pct"] == 100.0)
    pure0 = sorted(u for u, v in purity_by_url.items()
                   if "skip" not in v and v["chrome_pct"] == 0.0)
    tot_body_all = sum(body_by_url.values())
    b100 = sum(body_by_url[u] for u in pure100)
    b0 = sum(body_by_url[u] for u in pure0)
    print(f"\n[S4e 작업3 · 견본 순도 극단 URL]  전체 body {tot_body_all}")
    print(f"    순도 100% 크롬 URL {len(pure100)}개 → body {b100} "
          f"({fpct(pct(b100, tot_body_all))})")
    for u in pure100:
        print(f"      th={purity_by_url[u]['th']:>3} n={purity_by_url[u]['n']:>2} "
              f"body={body_by_url[u]:>3}  {u[:70]}")
    print(f"    순도 0%(전량 본문) URL {len(pure0)}개 → body {b0} "
          f"({fpct(pct(b0, tot_body_all))})")

    # ── S4e-작업4. th=40 3 URL 특정 ────────────────────────────────
    th40 = sorted(u for u, v in body_ctx.items() if v["th"] == 40)
    print(f"\n[S4e 작업4 · th=40] URL {len(th40)}")
    for u in th40:
        pv = purity_by_url.get(u, {})
        print(f"    body={body_by_url[u]:>3} 순도크롬%={pv.get('chrome_pct')} "
              f"100%크롬목록에 포함={u in pure100}  {u[:66]}")
    print(f"    th=40 body 합계 = {sum(body_by_url[u] for u in th40)} / "
          f"{tot_body_all}")

    # ── 🔴 S4f-작업1. ③ 452 트리거 분해 (본체) ─────────────────────
    # 단위 = **레코드**(452). 쌍(451)이 아니다 — 지시 §3-a 의 계가 452 다.
    # 한 레코드가 두 유형에 동시 해당할 수 있으므로 **중복허용/배타 2벌**을 낸다.
    #   배타 우선순위: 부분일치만 > top 완전일치 보유 > 그 외 완전일치
    tri3_multi = Counter()
    tri3_excl = Counter()
    tri3_topfam = Counter()
    tri3_names = Counter()
    tri3_miss = []
    n3 = 0
    for _n, u, sp, fin in pop_recs:
        if fin != "3":
            continue
        n3 += 1
        d = tri3.get((sp, u))
        if not d or not d["occ"]:
            tri3_miss.append((sp, u))
            tri3_excl["(cat3 출현 0 — 조회 실패)"] += 1
            continue
        has_exact = bool(d["exact"])
        has_part = bool(d["partial"])
        has_top = d["exact"].get("top", 0) > 0
        if has_part:
            tri3_multi["부분일치 보유"] += 1
        if not has_exact and has_part:
            tri3_multi["부분일치 유일 근거"] += 1
        if has_top:
            tri3_multi["top 완전일치 보유"] += 1
        if has_exact:
            tri3_multi["완전일치 보유"] += 1
        if not has_exact and has_part:
            tri3_excl["① 부분일치 유일 근거 (CP-1)"] += 1
        elif has_top:
            tri3_excl["② top 완전일치 보유 (CP-2)"] += 1
        elif has_exact:
            tri3_excl["③ 그 외 완전일치"] += 1
        else:
            tri3_excl["(트리거 0)"] += 1
        for k, v in d["topfam"].items():
            tri3_topfam[k] += 1 if v else 0
        for k in set(list(d["exact"]) + [x.split("⊂")[0] for x in d["partial"]]):
            tri3_names[k] += 1

    print(f"\n[S4f 작업1 · ③ 452 트리거 분해]  레코드 {n3} (조회실패 {len(tri3_miss)})")
    print("  [배타 — 표제]")
    for k in ("① 부분일치 유일 근거 (CP-1)", "② top 완전일치 보유 (CP-2)",
              "③ 그 외 완전일치", "(트리거 0)", "(cat3 출현 0 — 조회 실패)"):
        if tri3_excl.get(k):
            print(f"    {k:<32} {tri3_excl[k]:>4}  {fpct(pct(tri3_excl[k], n3))}")
    print(f"    {'계':<32} {sum(tri3_excl.values()):>4}   (452 대조)")
    print("  [중복허용]")
    for k, v in tri3_multi.most_common():
        print(f"    {k:<32} {v:>4}  {fpct(pct(v, n3))}")
    print("  [top 완전일치 내역(레코드 보유 기준)] " +
          "  ".join(f"{k}={v}" for k, v in tri3_topfam.most_common()))
    print("  [사전 항목별 보유 레코드 상위] " +
          "  ".join(f"{k}={v}" for k, v in tri3_names.most_common(12)))

    # ── 🔴 S4g-작업1. 307 무작위 60건 표본 추출 ─────────────────────
    # 모집단 = ③ 레코드 중 **부분일치 보유 ∧ 완전일치 보유**.
    # 🔴 층화하지 않는다. 사전 항목·URL·빈도 어느 것으로도 나누지 않는다.
    #    `random.Random(SEED).sample()` = 단순 무작위 비복원 추출.
    SEED = 20260809          # 고정. 지시 작성일. 재현 가능.
    SAMPLE_N = 60            # 고정. 늘리거나 줄이지 않는다.

    pop307, in_excl = [], Counter()
    for _n, u, sp, fin in pop_recs:
        if fin != "3":
            continue
        d = tri3.get((sp, u))
        if not d or not d["occ"]:
            continue
        if not (d["partial"] and d["exact"]):
            continue
        # 이 레코드가 배타 분류에서 어디로 갔는지도 함께 센다(지시 문안 대조용)
        in_excl["② top 완전일치" if d["exact"].get("top") else "③ 그 외 완전일치"] += 1
        pop307.append((_n, u, sp))
    # 결정적 정렬 후 추출 — dict 순서에 의존하지 않는다
    pop307 = sorted(pop307, key=lambda x: (x[0], x[1], x[2]))
    picked = random.Random(SEED).sample(pop307, SAMPLE_N)
    picked = sorted(picked, key=lambda x: (x[0], x[1], x[2]))

    print(f"\n[S4g 작업1 · 307 표본] 모집단 = {len(pop307)} "
          f"(부분일치∧완전일치 보유) · 배타 내역 {dict(in_excl)}")
    print(f"    SEED={SEED} · N={SAMPLE_N} · 방식 = random.Random(SEED).sample "
          f"(단순 무작위 비복원, 층화 없음)")

    s4g_text, s4g_name = [], []
    for i, (n, u, sp) in enumerate(picked, 1):
        d = tri3[(sp, u)]
        s4g_text.append({"id": i, "rec": n, "url": u, "span": sp,
                         "occ": d["occ"], "chars": [len(x) for x in d["texts"]],
                         "texts": d["texts"]})
        s4g_name.append({"id": i, "rec": n, "url": u, "span": sp,
                         "chains": d["chains"],
                         "exact": dict(d["exact"]), "partial": dict(d["partial"]),
                         "triggers": [hint_detail(c) for c in d["chains"]]})
    (OUT / "_s4g_TEXT.json").write_text(
        json.dumps(s4g_text, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "_s4g_NAMES.json").write_text(
        json.dumps(s4g_name, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"    [OUT] _s4g_TEXT.json · _s4g_NAMES.json  ← 육안 순서 강제용 분리")
    print("    추출 id(레코드번호) = " +
          ", ".join(f"{i}:#{n}" for i, (n, _u, _s) in enumerate(picked, 1)))

    # ── S4g-작업2. 사전 항목별 완전/부분 내역 (③ 452 레코드 기준) ────
    HINTS6 = ["menu", "nav", "side", "head", "top", "tag"]
    print("\n[S4g 작업2 · 사전 항목별 완전/부분 (③ 452 레코드 보유 기준)]")
    print(f"    {'항목':<8}{'총':>5}{'완전일치':>9}{'부분일치':>9}  대표 부분일치 실물")
    hint_break = {}
    for hk in HINTS6:
        tot_h = ex_h = pa_h = 0
        toks = Counter()
        for (sp, u), d in tri3.items():
            e = d["exact"].get(hk, 0)
            p = sum(v for k, v in d["partial"].items() if k.startswith(hk + "⊂"))
            if e or p:
                tot_h += 1
            if e:
                ex_h += 1
            if p:
                pa_h += 1
                for k, v in d["partial"].items():
                    if k.startswith(hk + "⊂"):
                        toks[k.split("⊂", 1)[1]] += 1
        hint_break[hk] = {"total": tot_h, "exact": ex_h, "partial": pa_h,
                          "tokens": dict(toks.most_common(6))}
        rep = " ".join(f"{k}({v})" for k, v in toks.most_common(4)) or "0건"
        print(f"    {hk:<8}{tot_h:>5}{ex_h:>9}{pa_h:>9}  {rep}")

    # ══════════════════════════════════════════════════════════════
    # S4-h — CP-3 · 배치계열 · 기타 top · 배타 집계 (전부 기계 조회, 육안 0)
    # ══════════════════════════════════════════════════════════════
    print("\n" + "=" * 74)
    print("S4-h")
    print("=" * 74)

    # ── S4h-작업1. CP-3 — 전역 요소(<html>/<body>) class·id 매칭 ────
    # 근거 체인은 `cat_of_one` 이 실제로 보는 `desc()` 문자열을 그대로 쓴다.
    glob_of = {}
    for u in sorted(nodes):
        seen = {}
        for _t, node in nodes[u][:300]:
            for el in P.chain_of(node):
                tag = el.split("#")[0].split(".")[0]
                if tag in GLOBAL_TAGS:
                    seen[tag] = el
            if len(seen) == len(GLOBAL_TAGS):
                break
        glob_of[u] = sorted(seen.values())
    glob_hit = {}
    for u, els in glob_of.items():
        # ⚠️ hint_detail 은 **체인(리스트)** 를 받는다. 문자열을 넘기면 글자 단위로
        #    순회해 조용히 0건이 된다(2026-08-10 실측 버그).
        hits = hint_detail(els)
        if hits:
            glob_hit[u] = hits
    rec3_by_url = Counter()
    rec_all_by_url = Counter()
    for _n, u, sp, fin in pop_recs:
        rec_all_by_url[u] += 1
        if fin == "3":
            rec3_by_url[u] += 1
    cp3_rec3 = sum(rec3_by_url[u] for u in glob_hit)
    cp3_recall = sum(rec_all_by_url[u] for u in glob_hit)
    print(f"\n[S4h 작업1 · CP-3 전역 요소] 매칭 URL {len(glob_hit)} / 파싱 {len(nodes)} "
          f"(HTML 45장)")
    print(f"    🔴 표제 — 그 URL 들의 ③ 452 내 레코드 = **{cp3_rec3}**")
    print(f"    (참고) 잔여 1,241 내 레코드 = {cp3_recall}   ← 표제 합산에 넣지 않음")
    gh = Counter()
    for u, hits in glob_hit.items():
        for h in hits:
            gh[(h["hint"], "완전" if h["exact"] else "부분")] += 1
    print("    매칭 항목별(전역 요소 기준) = " +
          "  ".join(f"{k[0]}/{k[1]}={v}" for k, v in gh.most_common()))
    print("    URL 별 실물 전량:")
    for u in sorted(glob_hit):
        els = " | ".join(sorted({h["element"] for h in glob_hit[u]}))
        hs = ",".join(sorted({f'{h["hint"]}{"=" if h["exact"] else "⊂"}{h["token"]}'
                              for h in glob_hit[u]}))
        print(f"      ③{rec3_by_url[u]:>3} 전체{rec_all_by_url[u]:>3}  {u[:52]}")
        print(f"           {els[:110]}")
        print(f"           {hs[:110]}")

    # ── S4h-작업2. 배치·간격 접두어 계열 ────────────────────────────
    lay_any, lay_only, lay_pref, lay_names = 0, 0, Counter(), Counter()
    lay_only_ids = []
    rec3_list = [(n, u, sp) for n, u, sp, f in pop_recs if f == "3"]
    rec_flags = {}
    for n, u, sp in rec3_list:
        d = tri3.get((sp, u))
        # ⚠️ 이름 충돌 주의 — S4-d 의 `trig`(Counter) 를 덮지 않도록 지역명 분리
        trigs = []
        for c in d["chains"]:
            trigs += hint_detail(c)
        segs_hit, all_layout, has_global = [], bool(trigs), False
        for t in trigs:
            tag, _ = segments(t["element"])
            if tag in GLOBAL_TAGS:
                has_global = True
            owners = hint_segments(t["element"], t["hint"])
            lay = any(is_layout_seg(o) for o in owners)
            if lay:
                for o in owners:
                    if is_layout_seg(o):
                        segs_hit.append(o)
                        for p in LAYOUT_PREFIXES:
                            if o.lower().startswith(p):
                                lay_pref[p] += 1
                                break
            else:
                all_layout = False
        if segs_hit:
            lay_any += 1
            for o in segs_hit:
                lay_names[o] += 1
        if all_layout and segs_hit:
            lay_only += 1
            lay_only_ids.append((n, u, sp))
        rec_flags[(n, u, sp)] = {
            "global": has_global,
            "no_exact": not d["exact"],
            "top_exact": d["exact"].get("top", 0) > 0,
            "layout_any": bool(segs_hit),
            "layout_only": bool(all_layout and segs_hit)}
    print(f"\n[S4h 작업2 · 배치계열]  접두어 목록 고정 {list(LAYOUT_PREFIXES)}")
    print(f"    경계 = `desc()` 를 태그/id/class **조각**으로 가른 뒤 조각 startswith")
    print(f"    ③ 452 중 배치계열 이름 보유 = {lay_any}")
    print(f"    🔴 그중 **배치계열에서만 매칭**(부당 확정) = {lay_only}")
    print(f"    그 외(정당 근거 병존) = {lay_any - lay_only}")
    print("    접두어별 = " + ("  ".join(f"{k}{v}" for k, v in lay_pref.most_common())
                              or "0건"))
    print("    실물 상위 20 = " + "  ".join(f"{k}({v})"
                                          for k, v in lay_names.most_common(20)))

    # 별도 관측 — 목록 밖 후보 (표제 미포함)
    extra = Counter()
    for n, u, sp in rec3_list:
        for c in tri3[(sp, u)]["chains"]:
            for t in hint_detail(c):
                for o in hint_segments(t["element"], t["hint"]):
                    if o.startswith("<"):
                        continue
                    m = re.match(r"^(u|is|js|has|el|c|o|_)[-_]", o.lower())
                    if m and not is_layout_seg(o):
                        extra[m.group(1) + "-"] += 1
    print("    [별도 관측 · 표제 미포함] 목록 밖 접두어 후보 = " +
          (str(dict(extra.most_common())) if extra else "0건"))

    # ── S4h-작업3. `기타 top 17` 정체 ──────────────────────────────
    top_other = Counter()
    for n, u, sp in rec3_list:
        d = tri3[(sp, u)]
        if not d["exact"].get("top"):
            continue
        for c in d["chains"]:
            for t in hint_detail(c):
                if t["exact"] and t["hint"] == "top":
                    if top_family(t["element"]) == "기타 top 완전일치":
                        for o in hint_segments(t["element"], "top"):
                            top_other[o] += 1
    print(f"\n[S4h 작업3 · 기타 top 완전일치 이름 전량] 고유 {len(top_other)}")
    for k, v in top_other.most_common():
        print(f"    {k:<34} {v:>4}")

    # ── S4h-작업4. 배타 집계 (우선순위 고정) ───────────────────────
    PRIO = ["CP-3 전역", "CP-1 부분일치 유일", "CP-2 top 완전일치",
            "배치계열(부당 확정)", "그 외"]
    excl, multi = Counter(), Counter()
    for k, f in rec_flags.items():
        if f["global"]:
            multi["CP-3 전역"] += 1
        if f["no_exact"]:
            multi["CP-1 부분일치 유일"] += 1
        if f["top_exact"]:
            multi["CP-2 top 완전일치"] += 1
        if f["layout_only"]:
            multi["배치계열(부당 확정)"] += 1
        if f["global"]:
            excl["CP-3 전역"] += 1
        elif f["no_exact"]:
            excl["CP-1 부분일치 유일"] += 1
        elif f["top_exact"]:
            excl["CP-2 top 완전일치"] += 1
        elif f["layout_only"]:
            excl["배치계열(부당 확정)"] += 1
        else:
            excl["그 외"] += 1
    print("\n[S4h 작업4 · ③ 452 배타 집계]  우선순위 = " + " > ".join(PRIO[:-1]))
    for k in PRIO:
        print(f"    {k:<22} {excl[k]:>4}  {fpct(pct(excl[k], 452))}")
    tot3 = sum(excl.values())
    print(f"    {'③ 계':<22} {tot3:>4}   (452 대조 {'✅ 일치' if tot3 == 452 else '🔴 불일치'})")
    print("    [중복허용] " + "  ".join(f"{k}={multi[k]}" for k in PRIO[:-1]))

    risk3 = tot3 - excl["그 외"]
    total_full = 162 + 98 + risk3
    print(f"\n    ③ 위험군(CP-3+CP-1+CP-2+배치계열) = {risk3}")
    print(f"    전수 대상 총계 = ④구분가능 162 + ②header최근접 98 + ③위험군 {risk3} "
          f"= **{total_full}**")
    print("\n[S4h STOP]")
    print(f"  1) 전수 총계 {total_full} > 450 ? → "
          f"{'🔴 발동' if total_full > 450 else '미발동'}")
    print(f"  2) ③ 계 {tot3} == 452 ? → {'미발동' if tot3 == 452 else '🔴 발동'}")
    print(f"  3) CP-3 {excl['CP-3 전역']} > 226(452 과반) ? → "
          f"{'🔴 발동' if excl['CP-3 전역'] > 226 else '미발동'}")

    (OUT / "_s4h_scope.json").write_text(json.dumps({
        "cp3": {"urls": len(glob_hit), "rec3": cp3_rec3, "rec_all_ref": cp3_recall,
                "by_url": {u: {"rec3": rec3_by_url[u], "rec_all": rec_all_by_url[u],
                               "elements": sorted({h["element"] for h in hits}),
                               "hints": sorted({f'{h["hint"]}'
                                                f'{"=" if h["exact"] else "⊂"}'
                                                f'{h["token"]}' for h in hits})}
                           for u, hits in glob_hit.items()}},
        "layout": {"prefixes": list(LAYOUT_PREFIXES), "any": lay_any,
                   "only": lay_only, "by_prefix": dict(lay_pref),
                   "names": dict(lay_names.most_common(40)),
                   "extra_candidates_not_counted": dict(extra)},
        "top_other": dict(top_other),
        "exclusive": dict(excl), "multi": dict(multi),
        "risk3": risk3, "total_full": total_full,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[OUT] _s4h_scope.json")

    # ── S4e-작업5a. #45 span 확인 ──────────────────────────────────
    s45 = sorted({(len(sp), sp) for n, _u, sp, f in ref_recs
                  if n == 45 and f == "4확정"}, reverse=True)
    print("\n[S4e 작업5a · #45 ④확정 span 전량]")
    for L, sp in s45:
        print(f"    {L:>3}자  {sp!r}")

    # ── S4c-작업2. 양성대조 ② 축4 (④확정 72 / (a)51) ───────────────
    pure = json.loads((OUT / "_s2_pure.json").read_text(encoding="utf-8"))
    pure_a = {(p["url"], p["span"]) for p in pure if p["cat"] == "a"}
    pure_cats = Counter(p["cat"] for p in pure)
    c4_pairs = sorted({(sp, u) for _n, u, sp, f in ref_recs if f == "4확정"})
    # (span,url)이 ④확정과 다른 final 을 함께 받은 경우 계상
    pop_pairset = set(pairs)
    overlap = [k for k in c4_pairs if k in pop_pairset]

    def split3(prs):
        d = {"chrome": 0, "body": 0, "mid": 0, "n_pairs": len(prs)}
        for sp, u in prs:
            r = occ.get((sp, u))
            if not r:
                continue
            for k in ("chrome", "body", "mid"):
                d[k] += r[k]
        d["N"] = d["chrome"] + d["body"] + d["mid"]
        return d

    c4_all = split3(c4_pairs)
    c4_a = split3([k for k in c4_pairs if (k[1], k[0]) in pure_a])
    c4_lt = split3([k for k in c4_pairs if len(k[0]) < 10])
    c4_ge = split3([k for k in c4_pairs if len(k[0]) >= 10])
    print(f"\n[작업2 · 양성대조 ②] ④확정 쌍 {len(c4_pairs)} "
          f"(POP 과 겹치는 쌍 {len(overlap)})")
    print(f"    _s2_pure.json cat 분포 = {dict(pure_cats)} → (a) 특정 "
          f"{'가능' if pure_cats.get('a') else '불가'} ({pure_cats.get('a')}건)")
    for lab, d in (("④확정 전량", c4_all), ("(a) 크롬아님", c4_a),
                   ("④확정 <10자", c4_lt), ("④확정 ≥10자", c4_ge)):
        print(f"    {lab:<12} 쌍 {d['n_pairs']:>3} N={d['N']:>4} "
              f"chrome {d['chrome']:>4} ({fpct(pct(d['chrome'], d['N']))}) "
              f"body {d['body']:>4} ({fpct(pct(d['body'], d['N']))}) "
              f"mid {d['mid']:>4} ({fpct(pct(d['mid'], d['N']))})")

    # ── S4c-작업3(=지시 §3). 축2 verdict / 축3 th 3분할 ────────────
    pair_verdict = {}
    for _n, u, sp, f in pop_recs:
        pair_verdict.setdefault((sp, u), set()).add(f)
    ax2 = {}
    for (sp, u), vs in pair_verdict.items():
        k = "+".join(sorted(vs))
        d = ax2.setdefault(k, {"chrome": 0, "body": 0, "mid": 0, "pairs": 0})
        d["pairs"] += 1
        r = occ.get((sp, u))
        if r:
            for x in ("chrome", "body", "mid"):
                d[x] += r[x]
    print("\n[축2 · verdict] (POP 쌍 기준)")
    for k in sorted(ax2):
        d = ax2[k]; N = d["chrome"] + d["body"] + d["mid"]
        print(f"    {k:<12} 쌍 {d['pairs']:>4} N={N:>5} chrome {d['chrome']:>5} "
              f"body {d['body']:>4} ({fpct(pct(d['body'], N))}) mid {d['mid']:>5}")
    ax3 = {}
    for (sp, u) in pairs:
        k = str(body_ctx.get(u, {}).get("th"))
        d = ax3.setdefault(k, {"chrome": 0, "body": 0, "mid": 0, "pairs": 0})
        d["pairs"] += 1
        r = occ.get((sp, u))
        if r:
            for x in ("chrome", "body", "mid"):
                d[x] += r[x]
    # S4-d §6-b — 분모(출현 N)를 비율과 나란히 낸다
    print("[축3 · 대조군 th]  (URL 수 · 쌍 · 출현 N · body · 비율)")
    th_urls = Counter(str(v["th"]) for v in body_ctx.values())
    for k in sorted(ax3, key=lambda x: (x == "None", x)):
        d = ax3[k]; N = d["chrome"] + d["body"] + d["mid"]
        print(f"    th={k:<5} URL {th_urls.get(k, 0):>2} 쌍 {d['pairs']:>4} "
              f"N={N:>5} chrome {d['chrome']:>5} body {d['body']:>4} "
              f"({fpct(pct(d['body'], N))}) mid {d['mid']:>5}")

    # ── S4d-작업4(=§6-a). 축2 "구조상 필연" 실증 ────────────────────
    # 주장: verdict '2'·'3' 레코드는 cat4 출현이 원리적으로 0이다.
    #   근거 = probe_s2_tagmap.py:220 `verdict = max(cats)` — cats 는 그 문구의
    #   **출현 전수**에 대한 cat_of_one 결과이고, S4 재계산은 같은
    #   `find_chains(nodes[u], span)` 를 쓰므로 출현 집합이 동일하다.
    # 코드 근거만으로 끝내지 않고 **전수 관측으로 확인한다** (CLAUDE.md §9).
    viol = []
    for (sp, u), vs in pair_verdict.items():
        if vs & {"4-구분가능"}:
            continue
        for row in hitdump.get((sp, u), []):
            if row["cat"] == "4":
                viol.append({"span": sp, "url": u, "verdict": sorted(vs)})
    n23 = sum(1 for vs in pair_verdict.values() if not (vs & {"4-구분가능"}))
    print(f"\n[S4d 작업4 · 축2 필연 실증] ②·③ 쌍 {n23} 전수 검사 → "
          f"cat4 출현 보유 쌍 = {len(viol)}  "
          f"{'✅ 필연 성립(코드+관측)' if not viol else '🔴 반례 존재 → 관측으로 격하'}")
    for v in viol[:5]:
        print(f"    반례: {v}")

    # ── S4d-작업3(=§5). ④확정 span 자수 분포 (T 결정 입력) ──────────
    c4_recs = [(n, u, sp) for n, u, sp, f in ref_recs if f == "4확정"]
    c4_hist = Counter(len(sp) for _n, _u, sp in c4_recs)
    c4_by_chunk = {}
    for n, u, sp in c4_recs:
        c4_by_chunk.setdefault(n, []).append((sp, len(sp)))
    print(f"\n[S4d 작업3 · ④확정 span 자수 분포] 레코드 {len(c4_recs)} · "
          f"청크 {len(c4_by_chunk)}")
    print("    자수: " + " ".join(f"{k}자×{v}" for k, v in sorted(c4_hist.items())))
    print(f"    🔴 8~9자 존재 여부 = "
          f"{c4_hist.get(8, 0) + c4_hist.get(9, 0)}건 "
          f"(8자 {c4_hist.get(8, 0)} · 9자 {c4_hist.get(9, 0)})")
    print(f"    {'청크':>4}  {'ge10':>4}  문구(자수)")
    for n in sorted(c4_by_chunk):
        ss = sorted(set(c4_by_chunk[n]), key=lambda x: -x[1])
        ge = sum(1 for _s, L in ss if L >= 10)
        print(f"    #{n:>3}  {ge:>4}  " +
              ", ".join(f"{s}({L})" for s, L in ss[:8]))

    # ── S4c-작업3(민감도). 대조군 상한 8 → 32 ─────────────────────
    # 🔴 원본판(상한 8)이 표제값. 이것은 별도 계상뿐이며
    #    `probe_s2_agg.py` 는 건드리지 않는다 (지시 §9-1·§9-2).
    SENS_CAP = 32
    sens_tok, sens_n = {}, {}
    for u in sorted(nodes):
        th = body_ctx[u]["th"]
        if th is None:
            sens_tok[u], sens_n[u] = set(), 0
            continue
        keys = [k for k in A.chrome_keys_of(u, url_chunks, frag, full)
                if len(k) >= P.MIN_KEY]
        sel = select_body_nodes(nodes[u], keys, th, SENS_CAP)
        tok = set()
        for _i, _t, ch in sel:
            tok |= A.tokens(ch)
        sens_tok[u], sens_n[u] = tok, len(sel)
    # cat 은 상한과 무관하므로 저장된 cat/chain[:8] 로 정확히 재판정한다
    sens = {"chrome": 0, "body": 0, "mid": 0}
    sens_ge = {"chrome": 0, "body": 0, "mid": 0}
    base_ge = {"chrome": 0, "body": 0, "mid": 0}
    for (sp, u) in pairs:
        for row in hitdump.get((sp, u), []):
            if row["cat"] in ("1", "2", "3"):
                s2 = "chrome"
            elif not sens_n.get(u):
                s2 = "mid"
            else:
                s2 = "body" if not (A.tokens(row["chain"]) - sens_tok[u]) else "mid"
            sens[s2] += 1
            if len(sp) >= 10:
                sens_ge[s2] += 1
                base_ge[row["side"]] += 1
    print(f"\n[민감도] 대조군 상한 8(원본·표제) → {SENS_CAP}")
    print(f"    선택 노드 합계  8: {sum(v['n'] for v in body_ctx.values()):>4}  "
          f"{SENS_CAP}: {sum(sens_n.values()):>4}")
    Nb = sum(base_ge.values()); Ns = sum(sens_ge.values())
    print(f"    전체 POP   원본 body {sum(occ[k]['body'] for k in pairs if occ.get(k)):>4}"
          f"  → 상한{SENS_CAP} body {sens['body']:>4}")
    print(f"    ≥10자만    원본 body {base_ge['body']:>4}/{Nb}  → 상한{SENS_CAP} "
          f"body {sens_ge['body']:>4}/{Ns}")

    # ── S4c-작업5. body 전건 오탐 감사 ────────────────────────────
    HANGUL = lambda ch: "가" <= ch <= "힣"  # noqa: E731
    audit = []
    for (sp, u) in pairs:
        for row in hitdump.get((sp, u), []):
            if row["side"] != "body":
                continue
            over = 0
            for cx in row.get("ctxs", []):
                i = cx.find(sp)
                if i < 0:
                    continue
                nxt = cx[i + len(sp):i + len(sp) + 1]
                # 오탐 후보 = 직후가 한글이면서 조사/어미가 아닌 경우
                if nxt and HANGUL(nxt) and nxt not in PARTICLE:
                    over += 1
            audit.append({"span": sp, "len": len(sp), "url": u,
                          "matches": len(row.get("ctxs", [])),
                          "overmatch": over, "ctxs": row.get("ctxs", [])})
    tot_body = len(audit)
    tot_m = sum(a["matches"] for a in audit)
    tot_o = sum(a["overmatch"] for a in audit)
    full_over = [a for a in audit if a["matches"] and a["overmatch"] == a["matches"]]
    print(f"\n[작업5] body 행 {tot_body} · 매칭 {tot_m} · 오탐후보 매칭 {tot_o} "
          f"· 전 매칭이 오탐인 행 {len(full_over)}")
    print(f"    오탐 제외 후 body 행 = {tot_body - len(full_over)}")

    s4c = {"env": env, "r9_repro": {"counts": dict(r9now), "expected": R9EXP,
                                    "ok": r9_ok, "body_meta_same_as_S4": bm_ok},
           "diff_45_43": {"html": len(html_files), "rows_urls": len(url_chunks),
                          "html_only": extra_files, "url_only": missing_files},
           "control1": {"total": pc1, "N": n1, "by_url": pc1_by_url,
                        "rule": {"min_len": 10, "max_len": 60, "cap_per_url": 20,
                                 "ngram": [2, 3], "source": "body_ctx 선택 노드"}},
           "control2": {"pure_cats": dict(pure_cats), "a_identified": len(pure_a),
                        "all": c4_all, "a": c4_a, "lt10": c4_lt, "ge10": c4_ge,
                        "overlap_with_POP": len(overlap)},
           "axis2_verdict": ax2, "axis3_th": ax3,
           "sensitivity": {"cap": SENS_CAP, "all": sens, "ge10": sens_ge,
                           "ge10_base": base_ge,
                           "nodes_base": sum(v["n"] for v in body_ctx.values()),
                           "nodes_sens": sum(sens_n.values())},
           "audit": {"body_rows": tot_body, "matches": tot_m,
                     "overmatch_matches": tot_o, "full_overmatch_rows": len(full_over)},
           # ── S4-d 추가분 ──────────────────────────────────────────
           "s4d": {
               "node_identity": "nodes[u] 인덱스 (+ 매 히트 `is` 객체 동일성 assert)",
               "position": pos,
               "cat3_same_pct": pct(c3["same"], c3t),
               "triggers": [{"name": nm, "hint": hk, "n": v,
                             "url": trig_url[(nm, hk)]}
                            for (nm, hk), v in trig.most_common(20)],
               "purity": {**purity, "N": npu,
                          "chrome_pct": pct(npu - purity["4"], npu)},
               "purity_by_url": purity_by_url,
               "axis2_necessity": {"pairs_23": n23, "violations": len(viol),
                                   "examples": viol[:5],
                                   "code": "probe_s2_tagmap.py:220 verdict = max(cats)"},
               "c4_len_hist": {str(k): v for k, v in sorted(c4_hist.items())},
               "c4_by_chunk": {str(n): sorted(set(v), key=lambda x: -x[1])
                               for n, v in c4_by_chunk.items()},
               "axis3_url_counts": dict(th_urls)}}
    # 🔴 S4-e #52 — 텍스트와 이름을 **별도 파일**로 낸다.
    #    육안 판정은 `_s4e_nodes_TEXT.json` 만 열고 하고, 그 뒤에
    #    `_s4e_nodes_NAMES.json` 을 열어 판정 변경 건수를 센다.
    (OUT / "_s4e_nodes_TEXT.json").write_text(
        json.dumps(s4e_text, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "_s4e_nodes_NAMES.json").write_text(
        json.dumps(s4e_name, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[OUT] _s4e_nodes_TEXT.json ({len(s4e_text)}건) · "
          f"_s4e_nodes_NAMES.json ({len(s4e_name)}건)  ← 육안 순서 강제용 분리")

    (OUT / "_s4c_control.json").write_text(
        json.dumps({**s4c, "control1_nonbody_rows": pc1_rows},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "_s4c_bodyaudit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[OUT] _s4c_control.json · _s4c_bodyaudit.json")

    # ── 10. STOP 값 산출 (P4: 출력보다 덤프가 먼저 나가도록 값만 먼저) ──
    if len(phrases) > STOP_A_MAX and len(phrases) > STOP_A_BAND[1]:
        a_v = "🔴 발동"
    elif STOP_A_BAND[0] <= len(phrases) <= STOP_A_BAND[1]:
        a_v = "⚠️ 경계 — 확정 금지, 챗 판정"
    else:
        a_v = "미발동"

    s2a = trow.get(f"T{T_HEADLINE}-전체")
    s2c = trow.get(f"T{T_HEADLINE}-결손제외")
    if s2a is None or s2c is None:
        head2 = "판정 불가 (≥T 문구 0건)"
    elif s2a["verdict"] != s2c["verdict"]:
        head2 = "⚠️ 경계 — 전체/결손제외 판정 불일치, 확정 금지 (챗 판정)"
    else:
        head2 = s2a["verdict"]

    bilateral = sorted({p for p in agg_all
                        if (agg_all[p][0] or agg_all[p][2]) and agg_all[p][1]})
    bdet = []
    for sp in bilateral:
        for u in p2u[sp]:
            for d in hitdump.get((sp, u), []):
                bdet.append({"span": sp, "len": len(sp), "url": u, **d})

    dump = {
        "assert": {"pop_records": len(pop_recs), "by_final": dict(by_fin),
                   "expected": EXPECTED, "expected_total": EXPECTED_TOTAL},
        "pairs": len(pairs), "phrases": len(phrases),
        "ref_records": len(ref_recs), "ref_pairs": len(ref_pairs),
        "p2_check": {"count_mismatch": len(bad_count),
                     "content_mismatch": len(bad_content)},
        "multi_verdict_pairs": {f"{k[0]}\t{k[1]}": v for k, v in multi.items()},
        "hist": dict(hb), "url_dist": {str(k): v for k, v in sorted(cd.items())},
        "d_table_all": tab_all, "d_table_clean": tab_clean, "t_rows": trow,
        "ref_T10": {"n": len(ref_ge), "strict": ref_st, "loose": ref_ls,
                    "loose_pct": None if ref_ls_p is None else round(ref_ls_p, 2),
                    "base_loose_pct": base_ls_p, "note": ref_line},
        "two_multi": dict(two_multi), "two_only": dict(two_only),
        "two_nearest": dict(two_near), "two_n": two_n,
        "stop": {"1": {"value": len(phrases), "thr": STOP_A_MAX,
                       "band": list(STOP_A_BAND), "verdict": a_v},
                 "2": {"all": s2a, "clean": s2c, "thr": STOP_D_PCT,
                       "headline": head2},
                 "3": {"header_any": hdr_any, "header_only": hdr_only,
                       "n": two_n, "verdict": "판정 보류 — 기준 미정(챗 소관)"}},
        "body_meta": {u: {"n": v["n"], "th": v["th"]} for u, v in body_ctx.items()},
        "zero_ctl_urls": zero_ctl,
        "miss_nohtml": [list(k) for k in miss_nohtml],
        "miss_zero_occ": [list(k) for k in miss_zero],
        "s4c": s4c,
        # S4-c 지시 §3 — 축2·축3 복구용 필드 3종 추가 (verdict · url_list · th)
        "phrase_detail": [
            {"span": p, "len": len(p), "urls": purl[p],
             "chrome": agg_all[p][0], "body": agg_all[p][1], "mid": agg_all[p][2],
             "in_clean": p in agg_clean, "bilateral_loose": p in set(bilateral),
             "verdict": sorted({v for u in p2u[p]
                                for v in pair_verdict.get((p, u), ())}),
             "url_list": p2u[p],
             "th": [body_ctx.get(u, {}).get("th") for u in p2u[p]]}
            for p in sorted(phrases, key=lambda x: (-len(x), x))],
    }
    # 🔴 S4 원본(`_s4_census.json`·`_s4_bilateral.json`)을 덮지 않는다.
    #    S4-b 판정의 증거 기반이므로 보존하고 새 파일로 낸다 (catch CN 규율).
    (OUT / "_s4c_census.json").write_text(
        json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "_s4c_bilateral.json").write_text(
        json.dumps({"phrases": bilateral, "detail": bdet},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[B] 양측(loose) 문구 {len(bilateral)}건 · 매칭 실물 {len(bdet)}행 덤프 "
          f"(절단 {sum(1 for x in bdet if x['truncated'])}행, 정책 전문≤{FULL_KEEP}자 / "
          f"초과는 ±{CTX}자)")
    print("[OUT] _s4c_census.json · _s4c_bilateral.json  ← STOP 출력보다 먼저 기록됨")

    # ── 11. 🔴 E/P5. STOP 3건 판정줄 (덤프 이후) ──────────────────
    print("\n" + "=" * 74)
    print(f"[STOP-1] (a) 고유 문구 = {len(phrases)}   기준 {STOP_A_MAX} 초과 "
          f"(경계 밴드 {STOP_A_BAND[0]}~{STOP_A_BAND[1]}) → {a_v}")
    if s2a and s2c:
        print(f"[STOP-2] (d) T={T_HEADLINE} 전체    loose {fpct(s2a['loose_pct'])} "
              f"strict {fpct(s2a['strict_pct'])} → {s2a['verdict']}")
        print(f"         (d) T={T_HEADLINE} 결손제외 loose {fpct(s2c['loose_pct'])} "
              f"strict {fpct(s2c['strict_pct'])} → {s2c['verdict']}")
    print(f"         기준 {STOP_D_PCT}% 초과 · 표제 → {head2}")
    print(f"[STOP-3] ② header 포함 {hdr_any}/{two_n} ({fpct(pct(hdr_any, two_n))}) · "
          f"단독 {hdr_only}/{two_n} ({fpct(pct(hdr_only, two_n))})  기준 과반")
    print("         → ⚠️ 판정 보류 (포함/단독 중 어느 것이 기준인지 미정 — 챗 소관)")
    print("=" * 74)


if __name__ == "__main__":
    main()
