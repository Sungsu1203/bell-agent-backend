"""§academic-1 Step A · A2 — 기존 ALLOWED_DOMAINS vs 신규 후보 set diff (read-only)."""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


ENV_PATH = Path("writer_project/.env")
GK_PATH = Path("writer_project/settings_gatekeep.py")
A1_JSON = Path("writer_project/scripts/output/§academic-1/a1_reachability.json")


def parse_env_allowed() -> tuple[set[str], int]:
    """Return (domains_set, line_no) from .env ALLOWED_DOMAINS=... line."""
    line_no = -1
    line_value = ""
    for i, line in enumerate(ENV_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("ALLOWED_DOMAINS="):
            line_no = i
            line_value = line.split("=", 1)[1]
            break
    items = {x.strip().lower() for x in line_value.split(",") if x.strip()}
    return items, line_no


def parse_base_allowed() -> tuple[set[str], int, int]:
    """Return (base_set, start_line, end_line) from settings_gatekeep.py _BASE_ALLOWED_DOMAINS tuple.

    Line-by-line scan: start at the line containing `_BASE_ALLOWED_DOMAINS:` and `(`,
    consume domain string lines, stop when line trim-equals `)`.
    """
    lines = GK_PATH.read_text(encoding="utf-8").splitlines()
    start_line = -1
    for i, line in enumerate(lines, start=1):
        if "_BASE_ALLOWED_DOMAINS:" in line and line.rstrip().endswith("("):
            start_line = i
            break
    if start_line < 0:
        return set(), -1, -1
    domains: set[str] = set()
    end_line = start_line
    for j in range(start_line, len(lines)):
        raw = lines[j]
        stripped = raw.strip()
        if stripped == ")":
            end_line = j + 1
            break
        body = stripped.split("#", 1)[0].strip().rstrip(",").strip()
        m = re.fullmatch(r'"([^"]+)"', body)
        if m:
            domains.add(m.group(1).strip().lower())
    return domains, start_line, end_line


def main() -> None:
    env_set, env_line = parse_env_allowed()
    base_set, base_start, base_end = parse_base_allowed()
    total_existing = env_set | base_set

    a1 = json.loads(A1_JSON.read_text(encoding="utf-8"))
    a1_reachable = {r["domain"].lower() for r in a1["results"] if r["reachable"] and r["bucket"] != "audit_only"}
    a1_audit_only = {r["domain"].lower() for r in a1["results"] if r["bucket"] == "audit_only"}
    a1_fail = {r["domain"].lower() for r in a1["results"] if not r["reachable"]}

    # 분류 → bucket map for reachable
    bucket_of = {r["domain"].lower(): r["bucket"] for r in a1["results"]}

    overlap = a1_reachable & total_existing
    add_only = a1_reachable - total_existing
    conflict_candidates = sorted(overlap)

    print(f"== A2 set diff ==")
    print(f".env line {env_line} : ALLOWED_DOMAINS count = {len(env_set)}")
    print(f"settings_gatekeep.py L{base_start}-L{base_end} : _BASE_ALLOWED_DOMAINS count = {len(base_set)}")
    print(f"union (existing total) = {len(total_existing)}  (env-only={len(env_set - base_set)}, base-only={len(base_set - env_set)}, both={len(env_set & base_set)})")
    print()
    print(f"A1 reachable (non audit-only) = {len(a1_reachable)}")
    print(f"  ∩ existing = {len(overlap)} (이미 포함)")
    print(f"  add-only   = {len(add_only)} (신규 도입 후보)")
    print(f"  audit-only = {len(a1_audit_only)} (분류 노트)")
    print(f"  fail       = {len(a1_fail)} (신규 도입 불가)")
    print()
    print("[Overlap — 이미 포함]")
    for d in sorted(overlap):
        in_env = "ENV" if d in env_set else ""
        in_base = "BASE" if d in base_set else ""
        print(f"  - {d:36s} bucket={bucket_of[d]:10s} {in_env} {in_base}")
    print()
    print("[Add-only — 신규]")
    for d in sorted(add_only):
        print(f"  - {d:36s} bucket={bucket_of[d]:10s}")
    print()
    print("[Audit-only]")
    for d in sorted(a1_audit_only):
        print(f"  - {d}")
    print()
    print("[Fail]")
    for d in sorted(a1_fail):
        print(f"  - {d}")

    out = {
        "env_line_no": env_line,
        "env_count": len(env_set),
        "base_lines": [base_start, base_end],
        "base_count": len(base_set),
        "existing_union": sorted(total_existing),
        "existing_union_count": len(total_existing),
        "a1_reachable": sorted(a1_reachable),
        "overlap": sorted(overlap),
        "add_only": sorted(add_only),
        "audit_only": sorted(a1_audit_only),
        "fail": sorted(a1_fail),
        "bucket_of_a1": {d: bucket_of[d] for d in a1_reachable | a1_audit_only | a1_fail},
    }
    out_path = Path("writer_project/scripts/output/§academic-1/a2_set_diff.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ wrote {out_path}")


if __name__ == "__main__":
    main()
