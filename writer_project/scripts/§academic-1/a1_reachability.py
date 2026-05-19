"""§academic-1 Step A · A1 — whitelist 학술 도메인 reachability + 신뢰도 verify.

Read-only audit driver. DNS resolve + HTTPS GET (timeout 10s, follow redirect) per domain.
Output: scripts/output/§academic-1/a1_reachability.json (raw, gitignored)
        + console table fed into step_a_entry_audit.md.

신뢰도 분류 (manual mapping below):
  peer = peer-reviewed journal / publisher portal
  preprint = preprint server
  aggregator = multi-publisher aggregator / index portal
  society = academic society / association site
  db_index = academic DB / index / abstracting service
  audit_only = default 제외, 분류 노트만
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import socket
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DOMAINS: list[tuple[str, str, str, str]] = [
    # (domain, bucket, classification, note)
    # ── bucket 1: 분야 무관 핵심 (12+) ──
    ("arxiv.org",                  "core",        "preprint",   "Cornell arXiv preprint server"),
    ("semanticscholar.org",        "core",        "db_index",   "Allen AI · semantic search index"),
    ("openalex.org",               "core",        "db_index",   "OpenAlex open scholarly graph"),
    ("jstor.org",                  "core",        "aggregator", "ITHAKA JSTOR · multi-discipline archive"),
    ("springer.com",               "core",        "peer",       "Springer Nature root"),
    ("link.springer.com",          "core",        "peer",       "Springer journal portal"),
    ("wiley.com",                  "core",        "peer",       "Wiley root"),
    ("onlinelibrary.wiley.com",    "core",        "peer",       "Wiley Online Library"),
    ("plos.org",                   "core",        "peer",       "PLOS · open-access journals"),
    ("science.org",                "core",        "peer",       "AAAS Science family"),
    ("pmc.ncbi.nlm.nih.gov",       "core",        "aggregator", "NIH PubMed Central"),
    ("sagepub.com",                "core",        "peer",       "SAGE Publishing root"),
    ("journals.sagepub.com",       "core",        "peer",       "SAGE journal portal"),
    ("tandfonline.com",            "core",        "peer",       "Taylor & Francis Online"),
    ("doaj.org",                   "core",        "db_index",   "Directory of Open Access Journals"),
    ("nature.com",                 "core",        "peer",       "Nature Portfolio"),
    ("ssrn.com",                   "core",        "preprint",   "SSRN preprint network"),
    ("papers.ssrn.com",            "core",        "preprint",   "SSRN paper subdomain"),
    ("emerald.com",                "core",        "peer",       "Emerald Publishing"),
    # ── bucket 2: 광고/마케팅 영어 (8) ──
    ("ama.org",                    "ad_en",       "society",    "American Marketing Association"),
    ("journalofadvertising.org",   "ad_en",       "peer",       "Journal of Advertising (T&F via society)"),
    ("warc.com",                   "ad_en",       "db_index",   "WARC marketing knowledge base (paywall)"),
    ("msi.org",                    "ad_en",       "society",    "Marketing Science Institute"),
    ("pubsonline.informs.org",     "ad_en",       "peer",       "INFORMS journals · Marketing Science"),
    ("academic.oup.com",           "ad_en",       "peer",       "Oxford Academic · JCR 등 포함"),
    ("mmaglobal.com",              "ad_en",       "society",    "Mobile Marketing Association"),
    ("iab.com",                    "ad_en",       "society",    "Interactive Advertising Bureau"),
    # ── bucket 3: 한국 학술 DB (5) ──
    ("kci.go.kr",                  "kr_db",       "db_index",   "한국연구재단 KCI"),
    ("riss.kr",                    "kr_db",       "db_index",   "KERIS RISS 학술정보"),
    ("dbpia.co.kr",                "kr_db",       "aggregator", "DBpia 학술 DB"),
    ("kiss.kstudy.com",            "kr_db",       "aggregator", "KISS 한국학술정보"),
    ("earticle.net",               "kr_db",       "aggregator", "earticle 학술 DB"),
    # ── bucket 4: 한국 광고/마케팅 학회 (5) — best-effort ──
    ("kadpr.or.kr",                "kr_soc",      "society",    "한국광고홍보학회 (KADPR) — 확정"),
    ("koads.or.kr",                "kr_soc",      "society",    "한국광고학회 best-effort — 추후 audit"),
    ("kma.or.kr",                  "kr_soc",      "society",    "한국마케팅협회 (학회 아님 가능) — 추후 audit"),
    ("kosac.or.kr",                "kr_soc",      "society",    "한국소비자학회 best-effort — 추후 audit"),
    ("kabs.or.kr",                 "kr_soc",      "society",    "한국방송학회 best-effort — 추후 audit"),
    # ── audit-only: default 제외 ──
    ("researchgate.net",           "audit_only",  "audit_only", "사용자 업로드 비-peer-reviewed 多 · default 제외"),
    ("academia.edu",               "audit_only",  "audit_only", "사용자 업로드 비-peer-reviewed 多 · default 제외"),
]


def resolve_dns(host: str) -> tuple[bool, str]:
    try:
        info = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        ips = sorted({sa[4][0] for sa in info})
        return True, ",".join(ips[:2])
    except socket.gaierror as e:
        return False, f"gaierror:{e.strerror or e}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}:{e}"


def https_get(host: str, timeout: float = 10.0) -> tuple[bool, int | str, str]:
    url = f"https://{host}/"
    req = Request(url, headers={"User-Agent": "rag-academic-audit/0.1 (read-only)"})
    ctx = ssl.create_default_context()
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            return True, resp.getcode(), resp.geturl()
    except HTTPError as e:
        return True, e.code, url  # HTTP response 자체 도달 — reachable
    except URLError as e:
        return False, "url_error", str(e.reason)
    except (TimeoutError, socket.timeout):
        return False, "timeout", url
    except ssl.SSLError as e:
        return False, "ssl_error", str(e)
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__, str(e)


def probe(entry: tuple[str, str, str, str]) -> dict:
    host, bucket, cls, note = entry
    dns_ok, dns_info = resolve_dns(host)
    http_ok, code, final = (False, "skip_dns_fail", "") if not dns_ok else https_get(host)
    reachable = dns_ok and http_ok
    return {
        "domain": host,
        "bucket": bucket,
        "classification": cls,
        "note": note,
        "dns_ok": dns_ok,
        "dns_info": dns_info,
        "http_ok": http_ok,
        "http_code": code,
        "final_url": final,
        "reachable": reachable,
    }


def main() -> int:
    out_dir = Path(__file__).resolve().parents[2] / "scripts" / "output" / "§academic-1"
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(probe, DOMAINS):
            results.append(r)
            tag = "OK" if r["reachable"] else "FAIL"
            print(f"[{tag:4s}] {r['domain']:34s} bucket={r['bucket']:10s} cls={r['classification']:11s} dns={r['dns_ok']} http={r['http_code']}")
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_total": len(results),
        "n_reachable": sum(1 for r in results if r["reachable"]),
        "n_fail": sum(1 for r in results if not r["reachable"]),
        "results": results,
    }
    out_path = out_dir / "a1_reachability.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ wrote {out_path}  (reachable {payload['n_reachable']}/{payload['n_total']}, fail {payload['n_fail']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
