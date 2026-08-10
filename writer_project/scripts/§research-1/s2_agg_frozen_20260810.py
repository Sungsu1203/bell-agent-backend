# 박제본 — §research-1 S4 계열 (S4 ~ S4-i) 계산 코드. 실행용 아님.
# 원본: writer_project/probe_s2_agg.py (untracked, .gitignore:106 probe_*)
# 박제 시점 sha256: 9db06411014ad3d4f97a076a688b068d8934d3d8373fcc245463acf8c808b75c
#!/usr/bin/env python
"""④ 유형별 집계 + ④ 본문 대조 확정. 네트워크 0(저장 HTML 재사용).

두 단계.
 (1) 본문 대조 — 임계 200 에서 대조군이 0이면 120 → 80 으로 낮춰 살린다.
     그래도 0이면 그 페이지의 ④ 는 **확정하지 않는다**(미확정).
     지시: "대조 없이 '단서가 없어 보인다'로 ④를 매기지 않는다".
 (2) ④ 확정 규칙 — ④ span 의 조상 토큰 집합에서 본문 조상 토큰 집합을 뺀
     차집합이 공집합이면 = 본문과 구조 동일 → **④ 확정**.
     차집합이 있으면 크롬만 가진 컨테이너가 존재하므로 단서가 될 수 있다
     → **④-구분가능**으로 분리한다(STOP 합계에서 뺀다).

⚠️ 2026-08-09 S4 리팩터 (동작 무변경, 순수 추출).
   사유 = `CC_ADDENDUM_20260809_S4_probe_review.md` D
   ("대조군 선정 로직을 복제하지 말고 import 한다").
   - 모듈 본문 실행부 → `main()` + `__main__` 가드.
     🔴 이전에는 가드가 없어 `import probe_s2_agg` 만으로 전량 재실행 +
     `_s2_final.json` 덮어쓰기가 일어났다(2026-08-09 실측).
   - 대조군 선정부 → `build_body_ctx()` 로 추출. `MIN_CTL` → 모듈 상수.
   - 추출 후 스크립트 재실행으로 R9 값 재현을 확인했다(D-4).
"""
from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup

import probe_s2_tagmap as P

OUT = P.OUT

# 40 추가 (2026-08-09) — brunch 는 문장을 <br>/<span> 으로 잘게 쪼개 렌더링해
# 본문 최대 행이 67자다. 80 에서 0건이 난 것은 "본문 없음"이 아니라
# "본문 노드가 전부 짧음"이었다. 임계 설계 탓이지 페이지 탓이 아니다.
THRESHOLDS = (200, 120, 80, 40)

# 🔴 "≥1건이면 만족"으로 멈추지 않는다 (2026-08-09 2차 정정).
# #45 는 임계 200 에서 1건이 잡혀 폴백이 멈췄으나 120 으로 내리면 14건이었다.
# 대조군이 얇으면 본문 토큰 집합이 작아져 차집합이 남기 쉽고,
# 판정이 ④확정 → ④-구분가능 쪽으로 기운다. 즉 **④를 과소 계상**한다.
# 방향이 STOP 기준과 반대이므로 최소 두께 MIN_CTL 을 요구한다.
MIN_CTL = 3


def load():
    raw = json.loads((OUT / "_s2_tagmap_raw.json").read_text(encoding="utf-8"))
    rows, full, frag = P.parse_r8()
    url_chunks: dict[str, list[int]] = {}
    for n, r in rows.items():
        url_chunks.setdefault(r["url"], []).append(n)
    return raw, rows, full, frag, url_chunks


def tokens(chain):
    """체인을 태그·class·id 토큰 집합으로."""
    out = set()
    for c in chain:
        t = c.replace("#", ".").split(".")
        out |= {x.lower() for x in t if x}
    return out


def chrome_keys_of(u, url_chunks, frag, full):
    """URL 이 보유한 청크 전체의 크롬 문구 집합 (대조군 제외 열쇠 원본)."""
    ck = set()
    for n in url_chunks[u]:
        ck |= set(frag.get(n, []))
        if n in full:
            ck |= {P.norm(x) for x in full[n].split("\n") if P.norm(x)}
    return ck


def build_body_ctx(url_chunks, frag, full, keep_nodes=False):
    """④ 판정용 같은-페이지 본문 대조군을 URL 별로 만든다.

    ⚠️ 토큰화 범위는 **비대칭**이다 (원본 유지 — addendum H).
      · 대조군 : `tokens(ch)`             = 체인 **전체**
      · 히트   : `tokens(reps['4'])`      = `probe_s2_tagmap.classify` 가
                 `h["chain"][:8]` 로 잘라 저장한 값
    대조군 토큰이 더 커져 `extra` 가 줄고 → ④확정 쪽으로 기운다.
    R9 박제값이 이 비대칭 위에서 나왔으므로 **고치지 않고 기록만 한다.**

    keep_nodes=True 면 파싱한 텍스트 노드도 함께 돌려준다(재파싱 회피).
    """
    body_ctx, nodes_all = {}, {}
    for u in sorted(url_chunks):
        p = P.HTMLDIR / (P.slug(u) + ".html")
        if not p.exists():
            continue
        soup = BeautifulSoup(p.read_text(encoding="utf-8"), "lxml")
        nodes = P.text_nodes(soup)
        if keep_nodes:
            nodes_all[u] = nodes
        keys = [k for k in chrome_keys_of(u, url_chunks, frag, full)
                if len(k) >= P.MIN_KEY]

        cands = []
        for th in THRESHOLDS:
            got = []
            for t, node in nodes:
                if len(t) < th or any(k in t for k in keys):
                    continue
                got.append(P.chain_of(node))
                if len(got) >= 8:
                    break
            cands.append((th, got))
            if len(got) >= MIN_CTL:
                break
        # MIN_CTL 을 채운 첫 임계. 어느 임계도 못 채우면 가장 많이 나온 것.
        chosen, used_th = [], None
        for th, got in cands:
            if len(got) >= MIN_CTL:
                chosen, used_th = got, th
                break
        else:
            th, got = max(cands, key=lambda x: len(x[1]))
            if got:
                chosen, used_th = got, th
        tok = set()
        for ch in chosen:
            tok |= tokens(ch)
        body_ctx[u] = {"n": len(chosen), "th": used_th, "tok": tok,
                       "chains": [c[:6] for c in chosen[:3]]}
    return (body_ctx, nodes_all) if keep_nodes else body_ctx


def main():
    raw, rows, full, frag, url_chunks = load()
    body_ctx = build_body_ctx(url_chunks, frag, full)

    no_ctl = [u for u in body_ctx if not body_ctx[u]["n"]
              and any(n in frag or n in full for n in url_chunks[u])]
    print(f"[대조군] 임계 폴백 후 0건 URL = {len(no_ctl)}")
    for u in no_ctl:
        print(f"   청크{[n for n in url_chunks[u] if n in frag or n in full]}  {u[:75]}")
    print(f"[대조군] 임계별 URL 수 = "
          f"{ {th: sum(1 for v in body_ctx.values() if v['th'] == th) for th in (200,120,80)} }")

    # ── (2) ④ 확정 / 구분가능 / 미확정 ────────────────────────────
    out = {}
    for k, ch in raw["chunks"].items():
        n = int(k)
        if ch["status"] != "OK":
            continue
        u = ch["meta"]["url"]
        ctx = body_ctx.get(u, {"n": 0, "tok": set()})
        recs = []
        for s in ch["spans"]:
            v = s["verdict"]
            if v != "4":
                recs.append({**s, "final": v})
                continue
            rep = s["reps"].get("4", [])
            if not ctx["n"]:
                recs.append({**s, "final": "4-미확정"})
                continue
            extra = tokens(rep) - ctx["tok"]
            recs.append({**s, "final": "4확정" if not extra else "4-구분가능",
                         "extra": sorted(extra)[:6]})
        out[n] = {"meta": ch["meta"], "src": ch["src"], "spans": recs,
                  "body_n": ctx["n"], "body_th": ctx.get("th")}

    (OUT / "_s2_final.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n{:>4} {:>7} {:>6} {:>7} {:>9} {:>8} {:>6} {:>6}".format(
        "청크", "spans", "④확정", "④구분가", "④미확정", "①②③", "SPLIT", "DRIFT"))
    print("-" * 72)
    tot = {"4확정": 0, "4-구분가능": 0, "4-미확정": 0}
    for n in sorted(out):
        sp = out[n]["spans"]
        c = lambda v: sum(1 for x in sp if x["final"] == v)  # noqa: E731
        for kk in tot:
            tot[kk] += c(kk)
        print("{:>4} {:>7} {:>6} {:>7} {:>9} {:>8} {:>6} {:>6}  body={}@{}".format(
            n, len(sp), c("4확정"), c("4-구분가능"), c("4-미확정"),
            c("1") + c("2") + c("3"), c("SPLIT"), c("DRIFT"),
            out[n]["body_n"], out[n]["body_th"]))
    print("-" * 72)
    print(f"span 합계  ④확정={tot['4확정']}  ④구분가능={tot['4-구분가능']}  "
          f"④미확정={tot['4-미확정']}")

    ck4 = {n for n in out if any(x["final"] == "4확정" for x in out[n]["spans"])}
    ckU = {n for n in out if any(x["final"] == "4-미확정" for x in out[n]["spans"])}
    print(f"\n④확정 span 을 하나라도 가진 청크 = {len(ck4)}건 {sorted(ck4)}")
    print(f"④미확정 span 을 가진 청크        = {len(ckU)}건 {sorted(ckU)}")


if __name__ == "__main__":
    main()
