# 박제본 — §research-1 S4 계열 (S4 ~ S4-i) 계산 코드. 실행용 아님.
# 원본: writer_project/probe_s2_tagmap.py (untracked, .gitignore:106 probe_*)
# 박제 시점 sha256: 1530a6ba5a611408b2dd939e24668f9ec7112114b50cb11e9cf8bbfe06ad91b4
#!/usr/bin/env python
"""§research-1 선분3 작업3 — 크롬 문구 조상 태그 체인 판별 탐침.

파이프라인 일치 (catch CI):
  - HTTP  = requests GET  (tools/web_rag/ingest_net.py:151 sess.get)
  - UA    = tools/web_rag/ingest_config.py:26 _UA 와 동일 문자열
  - 파서  = BeautifulSoup(html, "lxml")        (ingest.py:675)
  - 텍스트= soup.get_text(separator="\n")      (ingest.py:679)

파이프라인 코드를 import 하지 않는다 (catch CK — web_search 경로 부작용 회피).
받아온 HTML 은 색인 X·Y 입력이 아니다. 원장 밖 별도 재료.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "scripts" / "output" / "§research-1"
R8 = OUT / "R8_CHROME_LEXICON.md"
HTMLDIR = OUT / "_s2_probe_html"
HTMLDIR.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120 Safari/537.36"
)
CONN_TIMEOUT, READ_TIMEOUT = 5.0, 20.0

STRUCT_TAGS = {"nav", "footer", "aside", "header"}

# 길이 기준 2개 — 한 값을 두 용도에 쓰지 않는다. 쓰는 곳이 서로 다르다.
#  MIN_SPAN : 찾기용(find_chains · spans_of). 짧은 크롬("메뉴"·"로그인")도
#             찾아야 하므로 낮게 둔다.
#  MIN_KEY  : 거르기용(body_samples 의 제외 열쇠). 2글자("제품"·"문의")를
#             열쇠로 쓰면 200자 본문이 그걸 포함할 확률이 사실상 1 →
#             대조군이 통째로 비어버린다.
MIN_SPAN = 2
MIN_KEY = 10
CLASSID_HINTS = (
    "gnb", "lnb", "snb", "nav", "menu", "footer", "foot", "header", "head",
    "comment", "reply", "sidebar", "side", "widget", "aside", "related",
    "share", "sns", "tag", "banner", "copyright", "breadcrumb", "toolbar",
    "pagination", "prev", "next", "util", "quick", "top", "bottom",
)


# ── 1. R8 파싱 ────────────────────────────────────────────────
def parse_r8():
    txt = R8.read_text(encoding="utf-8")
    lines = txt.split("\n")

    # §4 전체 목록 → 조각ID/판정/범주/URL
    rows = {}
    for ln in lines:
        m = re.match(
            r"^\|\s*(\d+)\s*\|\s*`([0-9a-f]{6})`\s*\|\s*([^|]*?)\s*\|"
            r"\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*(\d+)\s*\|\s*(https?://\S+?)\s*\|$",
            ln,
        )
        if m:
            rows[int(m.group(1))] = {
                "n": int(m.group(1)), "cid": m.group(2), "verdict": m.group(3),
                "cats": m.group(4), "dist": m.group(5), "chars": int(m.group(6)),
                "url": m.group(7),
            }

    # §5 크롬 판정 18건 — 펜스 블록 전문
    full = {}
    i, cur = 0, None
    while i < len(lines):
        h = re.match(r"^### #(\d+) `([0-9a-f]{6})` — (.+)$", lines[i])
        if h:
            cur = int(h.group(1))
        elif lines[i].strip() == "```" and cur is not None:
            body = []
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                body.append(lines[i])
                i += 1
            full[cur] = "\n".join(body)
            cur = None
        i += 1

    # §6 혼재 27건 — 백틱 발췌
    frag = {}
    in6 = False
    for ln in lines:
        if ln.startswith("## 6."):
            in6 = True
            continue
        if in6 and ln.startswith("## 7."):
            break
        if not in6:
            continue
        m = re.match(r"^\|\s*(\d+)\s*\|\s*`([0-9a-f]{6})`\s*\|\s*([^|]*?)\s*\|\s*(.+?)\s*\|$", ln)
        if m:
            spans = re.findall(r"`([^`]+)`", m.group(4))
            frag[int(m.group(1))] = spans
    return rows, full, frag


# ── 2. 수집 (GET) ────────────────────────────────────────────
def slug(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", url)[:120]


def fetch_all(urls):
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})
    log = {}
    for u in sorted(urls):
        p = HTMLDIR / (slug(u) + ".html")
        if p.exists():
            log[u] = {"status": "cached", "bytes": p.stat().st_size, "file": p.name}
            continue
        try:
            r = sess.get(u, timeout=(CONN_TIMEOUT, READ_TIMEOUT))
            data = r.content
            enc = r.encoding
            if not enc:
                try:
                    import chardet
                    enc = chardet.detect(data).get("encoding") or "utf-8"
                except Exception:
                    enc = "utf-8"
            p.write_text(data.decode(enc, errors="replace"), encoding="utf-8")
            log[u] = {"status": r.status_code, "bytes": len(data), "ctype":
                      (r.headers.get("Content-Type") or "")[:60], "file": p.name}
        except Exception as e:
            log[u] = {"status": "ERR", "err": f"{type(e).__name__}: {e}"[:200]}
        print(f"  {log[u].get('status')} {u[:90]}", flush=True)
        time.sleep(1.2)
    return log


# ── 3. 조상 체인 ─────────────────────────────────────────────
def desc(tag) -> str:
    s = tag.name
    cid = tag.get("id")
    if cid:
        s += f"#{cid}"
    cls = tag.get("class")
    if cls:
        s += "." + ".".join(cls[:3])
    return s[:70]


def chain_of(node) -> list[str]:
    out = []
    p = node.parent
    while p is not None and getattr(p, "name", None) not in (None, "[document]"):
        out.append(desc(p))
        p = p.parent
    return out


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def find_chains(soup_nodes, span: str):
    """span 을 담은 텍스트 노드를 **전수** 찾아 조상 체인 반환. 상한 없음.

    ⚠️ 상한을 두면 HTML 앞쪽만 표집된다. 메뉴·헤더는 문서 상단 편중이라
    ①②로 잡히기 쉬운 출현만 뽑히고 하단·본문 중간의 ④ 출현이 누락된다.
    누락 방향이 STOP 기준(④가 많으면 정지)과 반대다.
    또한 판정을 최악값으로 내리므로 **출현 전수를 봐야 성립**한다 —
    상한을 3→10 으로 올려도 11번째가 남는다. 그래서 없앤다.
    """
    key = norm(span)
    if len(key) < MIN_SPAN:
        return []
    return [{"direct": node.parent.name if node.parent else "?",
             "chain": chain_of(node)}
            for ntext, node in soup_nodes if key in ntext]


def cat_of_one(chain) -> str:
    """출현 1건의 범주. ① 자기태그 ② 조상태그 ③ class/id ④ 못가름"""
    if not chain:
        return "4"
    direct = chain[0].split("#")[0].split(".")[0]
    if direct in STRUCT_TAGS:
        return "1"
    if any(c.split("#")[0].split(".")[0] in STRUCT_TAGS for c in chain):
        return "2"
    if any(k in " ".join(chain).lower() for k in CLASSID_HINTS):
        return "3"
    return "4"


def classify(hits):
    """출현 전수의 범주 분포를 내고, 판정은 **최악값(worst)** 으로 한다.

    판정 단위는 문구가 아니라 **출현**이다. 청크는 페이지 전체 텍스트에서
    만들어지므로, 한 문구가 3곳에 나오고 그중 1곳만 <footer> 안이면
    구조 규칙은 그 1곳만 지운다. 나머지 출현은 살아서 청크에 들어간다.

    분포를 함께 남긴다 — "5개 중 4개가 footer"와 "5개 다 본문"은
    최악값이 똑같이 ④여도 처방이 다르다. 최악값 하나로는 그 차이가 안 보인다.
    """
    if not hits:
        return {"verdict": "MISS", "n": 0, "dist": {}, "reps": {}}
    cats = [cat_of_one(h["chain"]) for h in hits]
    # 범주별 대표 체인 1건씩. hits[:4] 로 자르면 출현 7개 중 앞 4개가 ①이고
    # 7번째가 ④일 때 verdict=④ 인데 저장 체인은 ① 뿐이 된다 —
    # STOP 을 결정하는 범주의 근거가 육안 확인 불가가 된다.
    reps = {}
    for c, h in zip(cats, hits):
        if c not in reps:
            reps[c] = h["chain"][:8]
    return {"verdict": max(cats), "n": len(cats),
            "dist": {c: cats.count(c) for c in sorted(set(cats))},
            "reps": reps}


# ── 4. 본문 대조 샘플 (같은 페이지 긴 산문 노드) ─────────────
def body_samples(soup_nodes, chrome_keys, n=8):
    """④ 판정용 같은-페이지 본문 대조군.

    ⚠️ chrome_keys 에는 §6 발췌뿐 아니라 **§5 18건의 크롬 행도 전부** 넣는다.
    §6 만 넣으면 sweetspot·오픈애즈처럼 크롬 청크가 §5 에만 있는 URL 에서
    대조군에 크롬이 섞인다. 대조군이 오염되면 ④ 판정 근거가 무너진다.
    단 열쇠는 MIN_KEY 이상만 쓴다 — 오염된 대조군보다 없는 대조군이 나쁘다.
    """
    keys = [k for k in chrome_keys if len(k) >= MIN_KEY]
    out = []
    for t, node in soup_nodes:
        if len(t) < 200:
            continue
        if any(k in t for k in keys):
            continue
        ch = chain_of(node)
        out.append({"text": t[:90], "direct": ch[0] if ch else "?", "chain": ch[:8]})
        if len(out) >= n:
            break
    return out


def text_nodes(soup):
    """페이지당 1회만 만든다. 상한 제거로 span 마다 DOM 을 다시 훑으면
    span 수 × 노드 수가 되어 비용이 곱으로 는다."""
    out = []
    for node in soup.find_all(string=True):
        if node.parent and node.parent.name in ("script", "style"):
            continue
        t = norm(str(node))
        if t:
            out.append((t, node))
    return out


def main():
    rows, full, frag = parse_r8()
    print(f"[R8] rows={len(rows)} full={len(full)} frag={len(frag)}", flush=True)

    urls = {r["url"] for r in rows.values()}
    print(f"[URL] 청크 65 → 고유 URL {len(urls)}", flush=True)

    if "--fetch" in sys.argv:
        log = fetch_all(urls)
        (OUT / "_s2_fetch_log.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        print("[FETCH] done", flush=True)
        return

    # 분석 — 페이지당 텍스트 노드 목록을 1회만 만들어 재사용
    nodes, pagetext = {}, {}
    for u in urls:
        p = HTMLDIR / (slug(u) + ".html")
        if not p.exists():
            continue
        soup = BeautifulSoup(p.read_text(encoding="utf-8"), "lxml")
        nodes[u] = text_nodes(soup)
        # 파이프라인과 동일 (ingest.py:679). MISS 원인 2분할에 쓴다.
        # 공백 제거판을 같이 둔다 — norm() 만으로는 span 쪽 줄바꿈 구성이
        # 다를 때 in 비교가 실패하고, 고칠 수 있는 SPLIT 이 불가피한
        # DRIFT 로 새어나간다. 방향이 나쁜 오분류라 2차 비교를 붙인다.
        gt = norm(soup.get_text(separator="\n"))
        pagetext[u] = (gt, re.sub(r"\s+", "", gt))
    print(f"[PARSE] {len(nodes)} 페이지 · 텍스트노드 "
          f"{sum(len(v) for v in nodes.values())}", flush=True)

    def spans_of(n):
        if n in frag:
            return frag[n], "§6 발췌"
        if n in full:
            seen, ded = set(), []
            for x in full[n].split("\n"):
                s = norm(x)
                if len(s) >= MIN_SPAN and s not in seen:
                    seen.add(s)
                    ded.append(s)
            return ded, "§5 전문(행)"
        return None, None

    t0 = time.time()
    result = {"chunks": {}, "body": {}}
    for n, r in sorted(rows.items()):
        u = r["url"]
        spans, src = spans_of(n)
        if spans is None:
            result["chunks"][n] = {"meta": r, "status": "NO_CHROME", "spans": []}
            continue
        if u not in nodes:
            result["chunks"][n] = {"meta": r, "status": "NO_HTML", "spans": []}
            continue
        recs = []
        for s in spans:
            hits = find_chains(nodes[u], s)
            c = classify(hits)
            if c["verdict"] == "MISS":
                # MISS 원인 2분할 — 노드 단위로 못 찾았을 때 페이지 전체
                # 텍스트(soup.get_text)에 있는지 한 번 더 본다.
                #   있음 → SPLIT   : 텍스트 노드가 쪼개진 것. 탐침 한계, 개선 가능
                #   없음 → DRIFT   : 07-31 이후 사이트가 바뀐 것. 불가피
                gt, gt_ns = pagetext[u]
                if norm(s) in gt or re.sub(r"\s+", "", s) in gt_ns:
                    c["verdict"] = "SPLIT"
                else:
                    c["verdict"] = "DRIFT"
            recs.append({"span": s, "verdict": c["verdict"], "occ": c["n"],
                         "dist": c["dist"], "reps": c["reps"]})
        result["chunks"][n] = {"meta": r, "status": "OK", "src": src, "spans": recs}
        cnt = lambda v: sum(1 for x in recs if x["verdict"] == v)  # noqa: E731
        print(f"  #{n:>2} {r['cid']} {src:<12} spans={len(recs):>3} "
              f"①{cnt('1'):>3} ②{cnt('2'):>3} ③{cnt('3'):>3} ④{cnt('4'):>3} "
              f"SPLIT={cnt('SPLIT'):>3} DRIFT={cnt('DRIFT'):>3}", flush=True)
    print(f"[MATCH] {time.time()-t0:.1f}s", flush=True)

    # 본문 대조군 — chrome_keys 에 §6 발췌 + §5 전문 행을 모두 넣는다.
    # ⚠️ 필터는 두 겹이다. 여기서는 길이를 안 자르고 전량 넣고,
    #    body_samples 가 MIN_KEY 로 다시 거른다. 자르는 자리가 한 곳뿐이라
    #    MIN_KEY 를 바꾸면 동작이 한 번에 바뀐다.
    for u in nodes:
        ck = set()
        for n, r in rows.items():
            if r["url"] != u:
                continue
            ck |= set(frag.get(n, []))
            if n in full:
                ck |= {norm(x) for x in full[n].split("\n") if norm(x)}
        result["body"][u] = body_samples(nodes[u], ck)
        # 0건이 조용히 지나가면 안 된다 — URL 별 산출 개수를 전건 찍는다.
        print(f"  body={len(result['body'][u]):>2}  keys={len([k for k in ck if len(k) >= MIN_KEY]):>3}"
              f"  {u[:80]}", flush=True)

    (OUT / "_s2_tagmap_raw.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[ANALYZE] done → _s2_tagmap_raw.json", flush=True)


if __name__ == "__main__":
    main()
