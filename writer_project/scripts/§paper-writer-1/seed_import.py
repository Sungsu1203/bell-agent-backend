"""§paper-writer-2 seed_import — 수동 시드 입력 통로 (BibTeX/RIS → seed JSON).

목적
  연구자가 구글 스칼라·Zotero 에서 직접 고른 논문을 파이프라인의 기존 seed 주입
  (agent/web_search.py `_load_and_hydrate_seeds`, OA title hydrate) 에 넣는다.
  본 스크립트는 "형식 변환 + 병합 + 중복 검사"만 한다. 네트워크·LLM 호출 없음(비용 0).

입력
  .bib (BibTeX) 또는 .ris (RIS) 파일. Zotero 내보내기 / 스칼라 "인용 → BibTeX" 모두 가능.
  각 항목의 태그(BibTeX `keywords`, RIS `KW`)로 섹션·우선순위를 지정한다:
    sec:intro | sec:tb | sec:pf | sec:rd | sec:ec      (없으면 --section 기본값)
    prio:core | prio:context | prio:hold               (없으면 core)
    note:<한 줄 메모>                                    (선택, relevance_ko 로 저장)

출력
  기존 seed JSON(--base) + 새 항목을 합친 새 파일(--out). 원본 seed 는 건드리지 않는다.
  `<--out>.review.json` — 검토 목록(아래). 사람이 읽고 원본 .bib 을 고치는 용도.
  사용: SEED_REFERENCES_PATH=<--out 경로> 로 measure_paper 실행.

중복 처리
  DOI(소문자) 또는 정규화 제목이 base/앞선 항목과 같으면 추가하지 않고 보고만 한다.

검토 목록 (quarantine) — 원칙: 조용히 버리지 않는다
  ERROR = 주입하지 않되 사유와 함께 보존 / WARN = 주입하면서 표시 / INFO = 기록만

  | 코드 | 등급 | 뜻 |
  |---|---|---|
  | NO_TITLE         | ERROR | title 필드가 비었다 |
  | PARSE_ERROR      | ERROR | 따옴표·중괄호 짝이 맞지 않아 값 복구가 필요했다 |
  | EMAIL_LIKE_TITLE | ERROR | 제목이 메일주소 꼴 — 논문이 아닌 레코드 |
  | NOT_A_PAPER      | ERROR | 제목·저자·연도 중 2개 이상 결측 |
  | NO_SEC_TAG       | WARN  | sec: 태그 없음 → --section 기본값 적용 |
  | PRIO_CONFLICT    | WARN  | prio: 태그가 서로 다르게 여러 개 |
  | NON_LATIN_TITLE  | WARN  | 비라틴 제목 — OA 제목 검색 실패 위험 |
  | NO_DOI           | WARN  | doi 없음 — 동일성 검증이 제목 유사도에 의존 |
  | NEAR_DUPLICATE   | WARN  | 정규화 제목 유사도 ≥ 0.9 이나 동일하지는 않음 |
  | WEBPAGE_TYPE     | WARN  | Zotero 가 웹페이지(@misc/ELEC)로 저장 |
  | EXACT_DUPLICATE  | INFO  | DOI/정규화 제목 동일 → 추가하지 않음 |

  ⚠️ 등급은 **주입 여부만** 가른다. 품질 판정이 아니다 — WARN 항목도 전부 주입된다.

한계 (알고 남기는 것)
  - hydrate 는 OpenAlex 제목 검색이라 OA 에 없는 문헌(국내 KCI 논문 등)은 주입 단계에서
    skip 될 수 있다 → 보고서에 "OA 미회수 위험(한글 제목)" 으로 표시. KCI 백엔드 트랙에서 해소.
  - BibTeX 파서는 Zotero/스칼라 표준 출력용 최소 구현(중괄호 균형 기반). @string·매크로 미지원.
  - LaTeX 이스케이프는 악센트(\"u)·치찰(\c{c})·문장부호(\&)만 복원한다.
    \textit{..} 같은 서식 명령은 백슬래시+명령어가 제목에 남는다(실사용 미관측).
  - 태그 구분자가 `,` `;` 이므로 note: 메모에 쉼표가 있으면 그 뒤가 잘린다
    (relevance_ko 메모만 영향, 회수에는 무관).

예시
  python3 seed_import.py my_refs.bib --section pf \
      --base seeds/seed_references_trademark-similarity.json \
      --out seeds/seed_references_trademark-similarity+manual.json
  python3 seed_import.py my_refs.ris --dry     # 저장 없이 결과표만
"""
from __future__ import annotations

import argparse
import json
import difflib
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

SEC_MAP = {
    "intro": "introduction",
    "tb": "theoretical_background",
    "pf": "proposed_framework",
    "rd": "research_design",
    "ec": "expected_contributions",
}
PRIOS = {"core", "context", "hold"}


# ── 파서 ─────────────────────────────────────────────────────────────
# 구글 스칼라 BibTeX 는 비ASCII 를 LaTeX 이스케이프로 내보낸다: M{\"u}ller · Caf{\'e} · {\&}.
# 중괄호만 지우면 제목에 백슬래시가 남아(M\"uller) OpenAlex 제목 검색이 빗나간다.
_LATEX_ACCENTS = {"`": "\u0300", "'": "\u0301", "^": "\u0302", '"': "\u0308",
                  "~": "\u0303", "=": "\u0304", ".": "\u0307"}
_ACC_RE = re.compile(r"\\([`'^~=.\"])\s*\{?([A-Za-z])\}?")   # \"u → ü
# \c{c} 와 {\c c} 두 표기 모두 허용. 중괄호 없으면 공백을 요구해 \cite 오매치를 막는다.
_CEDILLA_RE = re.compile(r"\\c(?:\s*\{([A-Za-z])\}|\s+([A-Za-z]))")
_ESCPUNCT_RE = re.compile(r"\\([&%$#_{}])")                   # \& → &


def _unlatex(s: str) -> str:
    """LaTeX 이스케이프를 평문 유니코드로 되돌린다 (합성 후 NFC 정규화)."""
    s = _ACC_RE.sub(lambda m: unicodedata.normalize("NFC", m.group(2) + _LATEX_ACCENTS[m.group(1)]), s)
    s = _CEDILLA_RE.sub(
        lambda m: unicodedata.normalize("NFC", (m.group(1) or m.group(2)) + "\u0327"), s)
    return _ESCPUNCT_RE.sub(r"\1", s)


def _strip_braces(s: str) -> str:
    s = re.sub(r"[{}]", "", _unlatex(s or ""))
    return re.sub(r"\s+", " ", s).strip()


def parse_bibtex(text: str) -> list[dict]:
    """@type{key, field = {value} | "value" | number, ...} 항목 목록."""
    entries = []
    i = 0
    while True:
        m = re.compile(r"@(\w+)\s*\{", re.S).search(text, i)
        if not m:
            break
        if m.group(1).lower() in ("comment", "string", "preamble"):
            i = m.end()
            continue
        # 중괄호 균형으로 항목 끝 찾기
        depth, j = 1, m.end()
        while j < len(text) and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = text[m.end():j - 1]
        i = j
        key, _, rest = body.partition(",")
        fields: dict[str, str] = {}
        parse_warn: list[str] = []
        k = 0
        while k < len(rest):
            fm = re.compile(r"\s*([A-Za-z_\-]+)\s*=\s*", re.S).match(rest, k)
            if not fm:
                k += 1
                continue
            name = fm.group(1).lower()
            k = fm.end()
            if k < len(rest) and rest[k] == "{":
                d, s0 = 1, k + 1
                k += 1
                while k < len(rest) and d:
                    if rest[k] == "{":
                        d += 1
                    elif rest[k] == "}":
                        d -= 1
                    k += 1
                val = rest[s0:k - 1]
            elif k < len(rest) and rest[k] == '"':
                e = rest.find('"', k + 1)
                # 닫는 따옴표가 없으면 find 가 -1 → k 가 0 으로 되돌아가 무한루프.
                # 남은 전체를 값으로 보고 항목을 끝낸다 + PARSE_ERROR 로 보고한다.
                if e < 0:
                    val, k = rest[k + 1:], len(rest)
                    parse_warn.append(f"{name}: 닫는 큰따옴표 없음 — 남은 전체를 값으로 복구")
                else:
                    val, k = rest[k + 1:e], e + 1
            else:
                vm = re.compile(r"[^,]+").match(rest, k)
                val, k = (vm.group(0), vm.end()) if vm else ("", k + 1)
            fields[name] = _strip_braces(val)
        entries.append({
            "title": fields.get("title", ""),
            "authors": [a.strip() for a in fields.get("author", "").split(" and ") if a.strip()],
            "year": fields.get("year", ""),
            "venue": fields.get("journal") or fields.get("booktitle") or fields.get("publisher", ""),
            "doi": fields.get("doi", ""),
            "tags": [t.strip() for t in re.split(r"[,;]", fields.get("keywords", "")) if t.strip()],
            "_key": key.strip(),
            "_type": m.group(1).lower(),
            "_parse_warn": parse_warn,
        })
    return entries


def parse_ris(text: str) -> list[dict]:
    entries, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9])  - ?(.*)$", line)
        if not m:
            continue
        tag, val = m.group(1), m.group(2).strip()
        if tag == "TY":
            cur = {"title": "", "authors": [], "year": "", "venue": "", "doi": "", "tags": [],
                   "_key": "", "_type": val.strip().lower(), "_parse_warn": []}
        elif cur is None:
            continue
        elif tag in ("TI", "T1") and not cur["title"]:
            cur["title"] = val
        elif tag in ("AU", "A1"):
            cur["authors"].append(val)
        elif tag in ("PY", "Y1", "DA") and not cur["year"]:
            ym = re.search(r"\d{4}", val)
            cur["year"] = ym.group(0) if ym else ""
        elif tag in ("JO", "T2", "JF", "BT") and not cur["venue"]:
            cur["venue"] = val
        elif tag == "DO":
            cur["doi"] = val
        elif tag == "KW":
            cur["tags"].append(val)
        elif tag == "ER":
            entries.append(cur)
            cur = None
    return entries


# ── 변환 ─────────────────────────────────────────────────────────────
def norm_title(t: str) -> str:
    """중복 검사용 제목 정규화 — 구두점·공백만 제거하고 문자는 문자체 불문 보존한다.

    구 구현은 [^0-9a-z가-힣] 를 지워 키릴·일문 등 비라틴 제목이 통째로 ""
    가 됐고, 서로 다른 논문이 전부 같은 키로 접혀 조용히 중복 처리됐다.
    """
    return re.sub(r"[\W_]+", "", (t or "").lower(), flags=re.UNICODE)


def norm_doi(d: str) -> str:
    d = (d or "").strip().lower()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", d)


def to_seed(e: dict, default_sec: str, warns: list | None = None) -> dict:
    """warns 에 태그 문제(섹션 태그 없음·우선순위 충돌)를 사람이 읽을 문장으로 추가한다."""
    warns = warns if warns is not None else []
    sec, note = SEC_MAP[default_sec], ""
    secs, prios = [], []
    for t in e["tags"]:
        tl = t.lower()
        if tl.startswith("sec:") and tl[4:] in SEC_MAP:
            secs.append(SEC_MAP[tl[4:]])
        elif tl.startswith("prio:") and tl[5:] in PRIOS:
            prios.append(tl[5:])
        elif tl.startswith("note:"):
            note = t[5:].strip()
    if secs:
        sec = secs[0]
        if len(set(secs)) > 1:
            warns.append(f"섹션 태그 여러 개 {secs} → 첫 번째({sec}) 사용")
    else:
        warns.append(f"섹션 태그 없음 → 기본 섹션({sec}) 적용")
    # 우선순위 충돌 시 core > context > hold (핵심 문헌을 실수로 빠뜨리지 않는 쪽)
    prio = "core"
    if prios:
        prio = min(prios, key=["core", "context", "hold"].index)
        if len(set(prios)) > 1:
            warns.append(f"우선순위 태그 충돌 {prios} → {prio} 사용")
    year = int(e["year"]) if str(e["year"]).isdigit() else None
    first = (e["authors"][0].split(",")[0] if e["authors"] else "anon").strip().lower()
    # id 에 한글·키릴 문자도 남긴다 (러시아어 저자·제목이 지워져 id 가 겹치는 것 방지)
    sid = re.sub(r"[^a-z0-9가-힣а-яё]+", "-", f"manual-{first}-{year or 'nd'}-{e['title'][:24]}".lower()).strip("-")
    seed = {
        "id": sid,
        "section": f"{sec}/manual",
        "priority": prio,
        "title": e["title"],
        "authors_short": "; ".join(e["authors"][:3]) or "(hydrate)",
        "year": year,
        "venue": e["venue"],
        "relevance_ko": note or "(수동 시드 — 연구자 선정)",
        "status": "manual",
        "fetch_key": {"title": e["title"]},
        "verify_labels": ({"doi": norm_doi(e["doi"])} if e["doi"] else {}),
    }
    return seed


# ── 검토 목록(quarantine) 판정 ───────────────────────────────────────
# 원칙: 조용히 버리지 않는다. ERROR 는 주입하지 않되 사유와 함께 보존하고,
#       WARN 은 주입하면서 검토 목록에 남긴다. 표는 docstring 「검토 목록」 절과 동일.
REVIEW_CODES: dict[str, tuple[str, str]] = {
    "NO_TITLE":         ("ERROR", "원본에서 title 필드를 채우고 다시 변환"),
    "PARSE_ERROR":      ("ERROR", "해당 항목의 따옴표·중괄호 짝을 고치고 다시 변환"),
    "EMAIL_LIKE_TITLE": ("ERROR", "논문이 아닌 레코드(연락처 등) — 원본에서 삭제"),
    "NOT_A_PAPER":      ("ERROR", "제목·저자·연도 중 2개 이상 결측 — 서지를 보강"),
    "NO_SEC_TAG":       ("WARN",  "keywords 에 sec:<intro|tb|pf|rd|ec> 추가 (지금은 --section 기본값)"),
    "PRIO_CONFLICT":    ("WARN",  "prio: 태그를 하나만 남길 것"),
    "NON_LATIN_TITLE":  ("WARN",  "OA 제목 검색 실패 위험 — 영문 제목 병기 또는 KCI 트랙 대기"),
    "NO_DOI":           ("WARN",  "doi 를 채우면 동일성 검증이 title 유사도 대신 doi-match 로 올라감"),
    "NEAR_DUPLICATE":   ("WARN",  "기존 항목과 제목이 거의 같음 — 같은 논문인지 확인"),
    "WEBPAGE_TYPE":     ("WARN",  "Zotero 가 웹페이지로 저장함 — 저널 서지로 교체 권장"),
    "EXACT_DUPLICATE":  ("INFO",  "DOI 또는 정규화 제목이 기존 항목과 같아 추가하지 않음"),
}
_NON_LATIN_RE = re.compile(r"[^\x00-ɏ\s\W\d]")
_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
_WEBPAGE_TYPES = {"misc", "webpage", "elec", "web", "online"}


def _near_dup_ratio(t: str, pool: "set[str]") -> tuple[float, str]:
    """정규화 제목 t 와 pool 중 가장 비슷한 것의 유사도·상대. 완전 일치는 제외."""
    best, who = 0.0, ""
    for p in pool:
        if not p or p == t:
            continue
        r = difflib.SequenceMatcher(None, t, p).ratio()
        if r > best:
            best, who = r, p
    return best, who


def classify(e: dict, norm_pool: "set[str]") -> list[str]:
    """항목 하나의 사유 코드 목록. 등급은 REVIEW_CODES 에서 끌어온다."""
    codes: list[str] = []
    title = e.get("title") or ""
    if e.get("_parse_warn"):
        codes.append("PARSE_ERROR")
    if not title:
        codes.append("NO_TITLE")
    elif _EMAIL_RE.search(title) or "e-mail" in title.lower():
        codes.append("EMAIL_LIKE_TITLE")
    missing = sum(1 for v in (title, e.get("authors") or [], str(e.get("year") or "")) if not v)
    if missing >= 2:
        codes.append("NOT_A_PAPER")

    tags = [t.lower() for t in (e.get("tags") or [])]
    if not any(t.startswith("sec:") and t[4:] in SEC_MAP for t in tags):
        codes.append("NO_SEC_TAG")
    prios = {t[5:] for t in tags if t.startswith("prio:") and t[5:] in PRIOS}
    if len(prios) > 1:
        codes.append("PRIO_CONFLICT")
    if title and _NON_LATIN_RE.search(title):
        codes.append("NON_LATIN_TITLE")
    if not (e.get("doi") or "").strip():
        codes.append("NO_DOI")
    if (e.get("_type") or "") in _WEBPAGE_TYPES:
        codes.append("WEBPAGE_TYPE")
    if title:
        ratio, _ = _near_dup_ratio(norm_title(title), norm_pool)
        if ratio >= 0.9:
            codes.append("NEAR_DUPLICATE")
    return codes


def grade_of(codes: "list[str]") -> str:
    """코드 목록 → 최악 등급 (ERROR > WARN > INFO > OK)."""
    grades = {REVIEW_CODES[c][0] for c in codes if c in REVIEW_CODES}
    for g in ("ERROR", "WARN", "INFO"):
        if g in grades:
            return g
    return "OK"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", help=".bib 또는 .ris 파일")
    ap.add_argument("--section", default="pf", choices=sorted(SEC_MAP), help="태그 없는 항목의 기본 섹션")
    ap.add_argument("--base", help="병합할 기존 seed JSON (없으면 새 seed set)")
    ap.add_argument("--out", help="출력 seed JSON 경로 (원본과 같은 경로 금지)")
    ap.add_argument("--dry", action="store_true", help="저장하지 않고 결과표만 출력")
    a = ap.parse_args()

    src = Path(a.src)
    text = src.read_text(encoding="utf-8-sig")
    entries = parse_ris(text) if src.suffix.lower() == ".ris" else parse_bibtex(text)

    base = {"seed_set": "manual", "version": str(date.today()), "references": []}
    if a.base:
        base = json.loads(Path(a.base).read_text(encoding="utf-8"))
    refs = list(base.get("references") or [])
    seen_doi = {norm_doi((r.get("verify_labels") or {}).get("doi", "")) for r in refs} - {""}
    seen_title = {norm_title(r.get("title", "")) for r in refs}

    added, dup, bad = [], [], []
    warn_map: dict[str, list] = {}
    review: list[dict] = []          # 검토 목록 — ERROR/WARN/INFO 전건 보존
    for e in entries:
        codes = classify(e, seen_title)
        grade = grade_of(codes)
        rec = {
            "key": e.get("_key") or "?",
            "type": e.get("_type") or "",
            "title": (e.get("title") or "")[:120],
            "grade": grade,
            "codes": codes,
            "actions": [REVIEW_CODES[c][1] for c in codes if c in REVIEW_CODES],
            "parse_detail": e.get("_parse_warn") or [],
            "injected": False,
            "id": None,
        }
        if grade == "ERROR":
            # 주입하지 않되 사유와 함께 검토 목록에 보존한다 (조용히 버리지 않는다).
            bad.append(f"{rec['key']} [{','.join(codes)}] {rec['title'][:40]}")
            review.append(rec)
            continue
        w: list = []
        s = to_seed(e, a.section, w)
        d, t = norm_doi(e["doi"]), norm_title(e["title"])
        if (d and d in seen_doi) or (t and t in seen_title):
            dup.append(e["title"])
            rec["grade"] = "INFO"
            rec["codes"] = codes + ["EXACT_DUPLICATE"]
            rec["actions"] = [REVIEW_CODES[c][1] for c in rec["codes"] if c in REVIEW_CODES]
            review.append(rec)
            continue
        # 같은 id 가 이미 있으면 번호를 붙여 구분
        ids = {r.get("id") for r in refs}
        base_id, n = s["id"], 2
        while s["id"] in ids:
            s["id"] = f"{base_id}-{n}"; n += 1
        seen_title.add(t)
        if d:
            seen_doi.add(d)
        refs.append(s)
        added.append(s)
        if w:
            warn_map[s["id"]] = w
        rec["injected"] = True
        rec["id"] = s["id"]
        if codes:
            review.append(rec)

    print(f"[seed_import] 읽음 {len(entries)} / 추가 {len(added)} / 중복 {len(dup)} / 건너뜀 {len(bad)}")
    for s in added:
        # OpenAlex 제목 검색은 영어 제목 기준 → 한글·키릴 등 비라틴 제목은 회수 실패 위험
        risk = "  ⚠ OA 미회수 위험(비영어 제목)" if re.search(r"[^\x00-\u024f\s\W\d]", s["title"]) else ""
        print(f"  + [{s['section'].split('/')[0]}|{s['priority']}] {s['title'][:70]}{risk}")
        for msg in warn_map.get(s["id"], []):
            print(f"      ↳ {msg}")
    for t in dup:
        print(f"  = 중복(추가 안 함) {t[:70]}")
    for k in bad:
        print(f"  ! 건너뜀 (ERROR): {k}")

    # ── 검토 목록 등급별 요약 ──
    counts = {g: sum(1 for r in review if r["grade"] == g) for g in ("ERROR", "WARN", "INFO")}
    code_tally: dict[str, int] = {}
    for r in review:
        for c in r["codes"]:
            code_tally[c] = code_tally.get(c, 0) + 1
    print(f"[검토목록] ERROR {counts['ERROR']} / WARN {counts['WARN']} / INFO {counts['INFO']}"
          + (f"  · 사유: {', '.join(f'{c}×{n}' for c, n in sorted(code_tally.items()))}"
             if code_tally else ""))

    if a.dry or not a.out:
        print("[seed_import] --dry 또는 --out 없음 → 저장 안 함 (검토 목록도 저장 안 함)")
        return 0
    out = Path(a.out)
    if a.base and out.resolve() == Path(a.base).resolve():
        print("[seed_import] --out 이 --base 와 같음 → 원본 보호를 위해 중단", file=sys.stderr)
        return 2
    base["references"] = refs
    base["manual_import"] = {"source": src.name, "date": str(date.today()), "added": len(added)}
    out.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[seed_import] 저장: {out}  (총 {len(refs)}건) → SEED_REFERENCES_PATH 로 지정해 사용")
    rv = out.with_name(out.name + ".review.json")
    rv.write_text(json.dumps({
        "source": src.name, "date": str(date.today()),
        "read": len(entries), "added": len(added),
        "duplicate": len(dup), "rejected": len(bad),
        "counts": counts, "code_tally": code_tally,
        "legend": {c: {"grade": g, "action": act} for c, (g, act) in REVIEW_CODES.items()},
        "items": review,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[seed_import] 검토 목록: {rv}  ({len(review)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
