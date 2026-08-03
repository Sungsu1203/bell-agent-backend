import os, sys
assert os.environ.get("TOPIC_SLUG") == "experiential-marketing-media", \
    "TOPIC_SLUG 미지정/불일치 — 논문 트랙 프리셋 오염 방지 (catch AB)"

import re
from collections import Counter
from tools.web_rag import retrieve

NS = "experiential-marketing-media-web"
QUERIES = {
    "04주": "브랜드 사운드 로고 사운드 아이덴티티 사례",
    "07주": "숏폼 챌린지 UGC 캠페인 성공 사례 2025",
    "13주": "팝업스토어 브랜드 체험관 사례 2025",
    "15주": "가상인간 브랜드 캠페인 사례",
}
TOPK = int(os.environ.get("PROBE_TOPK", "25"))
SRC_CAP = int(os.environ.get("PROBE_SRC_CAP", "0"))  # 0 = 무제한

YR = re.compile(r"(?:19|20)\d{2}")

def host(m):
    s = str((m or {}).get("source", ""))
    return s.split("/")[2] if s.startswith("http") else "(local)"

out = []
seen = {}
for wk, q in QUERIES.items():
    docs = retrieve(q, top_k=TOPK, namespace=NS, collection_name=NS,
                    persist_directory="data/chroma_store/" + NS)
    # AT 확인: 요청 대비 반환
    out.append(f"\n{'='*78}\n## {wk}  요청={TOPK} 반환={len(docs)}  q={q}\n{'='*78}")
    cap = Counter()
    for i, d in enumerate(docs, 1):
        m = getattr(d, "metadata", {}) or {}
        h = host(m)
        if SRC_CAP and cap[h] >= SRC_CAP:
            continue
        cap[h] += 1
        key = str(m.get("source")) + d.page_content[:40]
        seen[key] = d
        yrs = sorted(set(YR.findall(d.page_content)))
        out.append(
            f"\n--- [{wk}-{i:02d}] {h}  len={len(d.page_content)}\n"
            f"TITLE : {str(m.get('title'))[:90]}\n"
            f"URL   : {m.get('source')}\n"
            f"YEARS : {yrs}\n"
            f"HEAD40: {d.page_content[:40]!r}\n"
            f"BODY  :\n{d.page_content}\n"
        )

out.append(f"\n\n{'#'*78}\n# 합집합 unique = {len(seen)}\n{'#'*78}")
c = Counter(host(getattr(d, 'metadata', {})) for d in seen.values())
out.append("호스트: " + str(c.most_common(15)))

path = f"probe_Z_top{TOPK}_cap{SRC_CAP}.md"
open(path, "w", encoding="utf-8").write("\n".join(out))
print("WROTE:", path, "chunks:", len(seen))
