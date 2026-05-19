"""§academic-1 Step C-2 — A/B measurement driver (catch 43 + MODE infra).

목적: 5 metrics 산출
  1. business invariant     — venfobel 토픽 출력 분포 변동 (source domain set 안정성)
  2. academic source ratio   — academic 토픽 출력의 학술 29 도메인 source 비율
  3. lang detect 정확도      — 10 labeled queries (5 EN + 5 KO) × detect_query_lang()
  4. EN → vertex 활성        — MODE=academic + EN query → effective_skip_vertex=False 비율
  5. KO → naver 활성         — MODE=academic + KO query → effective_skip_vertex=True 비율

측정 환경 standards (박제 정합):
  - max_retries=0
  - warmup 2 + measure 3 (per topic)
  - per-run-timeout 240s
  - inter-run-sleep 60s
  - PYTHONIOENCODING=utf-8

호출 path (per topic per run):
  1. topic env 로드 (override=True) + core.config.reload_config_inplace()
  2. catch 43 hook 모사 → effective_skip_vertex 결정
  3. vertex_web_search(query) (effective_skip_vertex=False 일 때)
  4. web_search.invoke({"query": q}) (항상 — legacy chain)
  5. source domain set / per-backend dist 기록

산출:
  - scripts/output/§academic-1/c_ab_results.json (.gitignored, raw)
  - scripts/output/§academic-1/c_ab_run.log (.gitignored, run-level log)

플래그:
  --dry-run        : API 호출 없이 driver 구조 검증 (STOP check 용)
  --warmup-only    : warmup 만 (measure skip) — C-2 dry-run protocol
  --topic X        : 단일 토픽만 (기본: business + academic-en + academic-ko)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ["LLM_MAX_RETRIES"] = "0"
os.environ["VERTEX_MAX_RETRIES"] = "0"
os.environ["OPENAI_MAX_RETRIES"] = "0"


# ── 측정 standards ────────────────────────────────────────────────────────────
WARMUP_RUNS = 2
MEASURE_RUNS = 3
PER_RUN_TIMEOUT_S = 240.0
INTER_RUN_SLEEP_S = 60.0


# ── B1 final 29 academic domains (§academic-1 Step B 박제 정합) ───────────────
ACADEMIC_DOMAINS_29 = {
    "academic.oup.com", "ama.org", "arxiv.org", "dbpia.co.kr", "doaj.org",
    "emerald.com", "journals.sagepub.com", "jstor.org", "kadpr.or.kr",
    "kci.go.kr", "kiss.kstudy.com", "link.springer.com", "mmaglobal.com",
    "msi.org", "onlinelibrary.wiley.com", "openalex.org", "papers.ssrn.com",
    "plos.org", "pmc.ncbi.nlm.nih.gov", "pubsonline.informs.org", "riss.kr",
    "sagepub.com", "science.org", "semanticscholar.org", "springer.com",
    "ssrn.com", "tandfonline.com", "warc.com", "wiley.com",
}


# ── 토픽 set + query ──────────────────────────────────────────────────────────
TOPICS = {
    "business-venfobel": {
        "env_file": "topics/venfobel-vitamin.env",
        "query": "벤포벨S 종근당 광고비 2024",
        "expected_mode": "business",
        "expected_lang": "ko",  # but MODE=business → catch 43 bypass
        "purpose": "invariant",
    },
    "academic-en": {
        "env_file": "topics/academic-influencer-marketing-consumer-behavior.env",
        "query": "consumer behavior in influencer marketing",
        "expected_mode": "academic",
        "expected_lang": "en",
        "purpose": "academic-en",
    },
    "academic-ko": {
        "env_file": "topics/academic-genz-mobile-ad-acceptance.env",
        "query": "Z세대 모바일 광고 수용도 연구",
        "expected_mode": "academic",
        "expected_lang": "ko",
        "purpose": "academic-ko",
    },
}


# ── lang detect ground-truth (10 labeled queries) ────────────────────────────
LANG_DETECT_LABELED = [
    # EN labeled
    ("consumer behavior in influencer marketing", "en"),
    ("source credibility theory parasocial interaction", "en"),
    ("arxiv preprint advertising effectiveness 2023", "en"),
    ("digital advertising attention metrics", "en"),
    ("Gen Z mobile ad acceptance survey", "en"),
    # KO labeled
    ("Z세대 모바일 광고 수용도 연구", "ko"),
    ("한국 광고홍보학회 디지털 광고 효과", "ko"),
    ("소비자 행동 인플루언서 마케팅", "ko"),
    ("국내 학술지 광고 수용도 메타분석", "ko"),
    ("KCI 등재지 모바일 광고 회피 연구", "ko"),
]


def setup_logging(log_path: Path) -> logging.Logger:
    """Run-level logger + tools.web_rag.search capture handler."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s"))
    root.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    root.addHandler(ch)
    return logging.getLogger("measure_ab")


def load_topic_env(env_file: str, logger: logging.Logger) -> dict[str, str]:
    """토픽 env 로드 (override=True) + reload_config_inplace. 기존 process env override."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning("[env] python-dotenv missing — process env only")
        return {}
    p = PROJECT_ROOT / env_file
    if not p.exists():
        logger.error("[env] missing: %s", p)
        return {}
    # global .env first (low priority)
    g = PROJECT_ROOT / ".env"
    if g.exists():
        load_dotenv(g, override=False)
    # topic env (high priority)
    load_dotenv(p, override=True)
    snapshot = {
        "MODE": os.getenv("MODE", "business"),
        "EXPECTED_LANG": os.getenv("EXPECTED_LANG", "auto"),
        "SKIP_VERTEX_SEARCH": os.getenv("SKIP_VERTEX_SEARCH", ""),
        "ALLOWED_DOMAINS_EXTRA_count": len(
            [x for x in (os.getenv("ALLOWED_DOMAINS_EXTRA", "")).split(",") if x.strip()]
        ),
    }
    logger.info("[env] loaded %s → %s", env_file, snapshot)
    # config reload — CFG.MODE / CFG.EXPECTED_LANG 반영
    try:
        from core.config import reload_config_inplace
        reload_config_inplace()
        logger.info("[env] reload_config_inplace OK")
    except Exception as e:
        logger.warning("[env] reload_config_inplace fail: %s", e)
    return snapshot


def _detect_query_lang_local(query: str) -> str:
    """Local mirror of agent.web_search.detect_query_lang — 의존성 없는 fallback."""
    s = "".join(c for c in (query or "") if c.isalpha() or '가' <= c <= '힣')
    if not s:
        return "en"
    r = sum(1 for c in s if '가' <= c <= '힣') / len(s)
    return "ko" if r > 0.7 else ("en" if r < 0.3 else "mixed")


def _load_production_detect_query_lang():
    """production detect_query_lang (agent.web_search) try-import. 실패 시 local fallback."""
    try:
        from agent.web_search import detect_query_lang as _f
        return _f, "production"
    except Exception:
        return _detect_query_lang_local, "local-fallback"


def compute_effective_skip_vertex(query: str, mode: str, expected_lang: str,
                                  detect_fn=None) -> tuple[bool, str]:
    """catch 43 hook replicate. agent/web_search.py:733-744 와 동일 logic."""
    fn = detect_fn or _detect_query_lang_local
    if mode == "academic":
        q_lang = expected_lang if expected_lang in ("en", "ko", "mixed") else fn(query)
        return q_lang == "ko", q_lang
    skip_env = (os.getenv("SKIP_VERTEX_SEARCH", "0") or "").strip().lower() in {"1", "true", "yes", "on"}
    return skip_env, "n/a"


def domain_of(url: str) -> str:
    try:
        h = urlparse(url).hostname or ""
        return h.lower().lstrip("www.")
    except Exception:
        return ""


def call_vertex(query: str, timeout_s: float, dry_run: bool) -> dict:
    if dry_run:
        return {"mode": "vertex", "elapsed_sec": 0.0, "items": 0, "domains": [], "dry_run": True}
    t0 = time.monotonic()
    err = None
    domains: list[str] = []
    items = 0
    try:
        from tools.web_rag.vertex_search import vertex_web_search
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(vertex_web_search, query)
            result = fut.result(timeout=timeout_s)
        chunks = (result or {}).get("chunks", []) or []
        items = len(chunks)
        domains = [domain_of(c.get("uri") or "") for c in chunks if c.get("uri")]
    except FuturesTimeoutError:
        err = f"timeout {timeout_s}s"
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:200]}"
    return {
        "mode": "vertex",
        "elapsed_sec": round(time.monotonic() - t0, 3),
        "items": items,
        "domains": domains,
        "domains_unique": sorted(set(d for d in domains if d)),
        "error": err,
    }


def call_legacy(query: str, timeout_s: float, dry_run: bool) -> dict:
    if dry_run:
        return {"mode": "legacy", "elapsed_sec": 0.0, "items": 0, "domains": [], "dry_run": True}
    t0 = time.monotonic()
    err = None
    domains: list[str] = []
    items_list: list[dict] = []
    backend_signals: list[str] = []
    try:
        from tools.web_rag.search import web_search
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(web_search.invoke, {"query": query})
            ret = fut.result(timeout=timeout_s)
        if isinstance(ret, tuple) and len(ret) >= 2:
            items_list = list(ret[0] or [])
        elif isinstance(ret, list):
            items_list = list(ret)
        elif isinstance(ret, dict):
            items_list = list(ret.get("results") or ret.get("items") or [])
        for it in items_list:
            if isinstance(it, dict):
                u = it.get("url") or it.get("source") or ""
                if u:
                    d = domain_of(u)
                    domains.append(d)
                    if "naver" in d:
                        backend_signals.append("naver_direct")
                    else:
                        backend_signals.append("tavily_or_other")
    except FuturesTimeoutError:
        err = f"timeout {timeout_s}s"
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:200]}"
    return {
        "mode": "legacy",
        "elapsed_sec": round(time.monotonic() - t0, 3),
        "items": len(items_list),
        "domains": domains,
        "domains_unique": sorted(set(d for d in domains if d)),
        "backend_signals": backend_signals,
        "naver_count": backend_signals.count("naver_direct"),
        "error": err,
    }


def run_single(topic_key: str, query: str, mode: str, expected_lang: str,
               timeout_s: float, dry_run: bool, logger: logging.Logger,
               detect_fn=None) -> dict:
    """1회 측정 run: catch 43 hook 결정 → vertex/legacy 호출 → 결과 dict."""
    eff_skip, q_lang = compute_effective_skip_vertex(query, mode, expected_lang, detect_fn)
    logger.info("[run] topic=%s mode=%s expected_lang=%s q_lang=%s skip_vertex=%s q=%r",
                topic_key, mode, expected_lang, q_lang, eff_skip, query[:60])
    vertex_rec = (call_vertex(query, timeout_s, dry_run)
                  if not eff_skip else {"mode": "vertex", "skipped_by_catch43": True,
                                         "items": 0, "domains": [], "elapsed_sec": 0.0})
    legacy_rec = call_legacy(query, timeout_s, dry_run)
    all_domains = list(vertex_rec.get("domains", [])) + list(legacy_rec.get("domains", []))
    all_domains_set = sorted(set(d for d in all_domains if d))
    academic_domains = sorted(set(all_domains_set) & ACADEMIC_DOMAINS_29)
    academic_ratio = (len(academic_domains) / len(all_domains_set)) if all_domains_set else 0.0
    return {
        "topic_key": topic_key,
        "mode": mode,
        "expected_lang": expected_lang,
        "q_lang_detected": q_lang,
        "effective_skip_vertex": eff_skip,
        "query": query,
        "vertex": vertex_rec,
        "legacy": legacy_rec,
        "all_domains_unique": all_domains_set,
        "academic_domains_hit": academic_domains,
        "academic_source_ratio": round(academic_ratio, 4),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
    }


def measure_topic(topic_key: str, cfg: dict, warmup: int, measure: int,
                  timeout_s: float, sleep_s: float, dry_run: bool,
                  logger: logging.Logger, detect_fn=None) -> dict:
    snapshot = load_topic_env(cfg["env_file"], logger)
    mode = snapshot.get("MODE", "business")
    expected_lang = snapshot.get("EXPECTED_LANG", "auto")
    runs: list[dict] = []
    total_runs = warmup + measure
    for i in range(total_runs):
        phase = "warmup" if i < warmup else "measure"
        logger.info("[topic=%s] %s run %d/%d", topic_key, phase, i + 1, total_runs)
        rec = run_single(topic_key, cfg["query"], mode, expected_lang, timeout_s, dry_run, logger, detect_fn)
        rec["phase"] = phase
        rec["run_index"] = i
        runs.append(rec)
        if i < total_runs - 1 and not dry_run:
            logger.info("[topic=%s] sleeping %.0fs (inter-run)", topic_key, sleep_s)
            time.sleep(sleep_s)
    return {
        "topic_key": topic_key,
        "env_snapshot": snapshot,
        "runs": runs,
        "purpose": cfg.get("purpose", ""),
    }


def lang_detect_accuracy(logger: logging.Logger, detect_fn) -> dict:
    """Metric 3: 10 labeled query × detect_query_lang() 일치율."""
    rows = []
    correct = 0
    for q, exp in LANG_DETECT_LABELED:
        got = detect_fn(q)
        ok = (got == exp)
        if ok:
            correct += 1
        rows.append({"query": q, "expected": exp, "got": got, "match": ok})
    accuracy = correct / len(LANG_DETECT_LABELED)
    logger.info("[lang-detect] accuracy = %d/%d = %.2f", correct, len(LANG_DETECT_LABELED), accuracy)
    return {"n": len(LANG_DETECT_LABELED), "correct": correct, "accuracy": round(accuracy, 4), "rows": rows}


def aggregate_metrics(topic_results: dict[str, dict], lang_acc: dict) -> dict:
    """5 metrics 집계."""
    metrics: dict[str, Any] = {}

    # Metric 1: business invariant — venfobel 토픽의 domain set 변동
    biz = topic_results.get("business-venfobel")
    if biz:
        measure_runs = [r for r in biz["runs"] if r["phase"] == "measure"]
        domain_sets = [set(r["all_domains_unique"]) for r in measure_runs]
        # Jaccard 안정성 — 첫 measure run vs others
        if len(domain_sets) >= 2:
            base = domain_sets[0]
            jaccards = []
            for ds in domain_sets[1:]:
                u = len(base | ds)
                jaccards.append(len(base & ds) / u if u else 1.0)
            stability = statistics.mean(jaccards) if jaccards else 1.0
        else:
            stability = 1.0
        # MODE 분기 검증: catch 43 hook 우회 (eff_skip = SKIP_VERTEX_SEARCH env)
        catch43_bypassed = all(r["q_lang_detected"] == "n/a" for r in measure_runs)
        metrics["1_business_invariant"] = {
            "stability_jaccard_mean": round(stability, 4),
            "catch43_bypass_business_mode": catch43_bypassed,
            "n_measure_runs": len(measure_runs),
            "verdict": "PASS" if (catch43_bypassed and stability >= 0.7) else "REVIEW",
        }

    # Metric 2: academic source ratio (academic 토픽 measure runs 평균)
    acad_ratios = []
    for k in ("academic-en", "academic-ko"):
        tr = topic_results.get(k)
        if not tr:
            continue
        for r in tr["runs"]:
            if r["phase"] == "measure":
                acad_ratios.append(r["academic_source_ratio"])
    metrics["2_academic_source_ratio"] = {
        "n": len(acad_ratios),
        "mean": round(statistics.mean(acad_ratios), 4) if acad_ratios else None,
        "min": round(min(acad_ratios), 4) if acad_ratios else None,
        "max": round(max(acad_ratios), 4) if acad_ratios else None,
        "threshold": 0.6,
        "verdict": "PASS" if (acad_ratios and statistics.mean(acad_ratios) >= 0.6) else "REVIEW",
    }

    # Metric 3: lang detect accuracy
    metrics["3_lang_detect_accuracy"] = {
        **lang_acc,
        "threshold": 0.8,
        "verdict": "PASS" if lang_acc["accuracy"] >= 0.8 else "REVIEW",
    }

    # Metric 4: EN → vertex 활성 비율 (academic-en measure runs 중 eff_skip=False 비율)
    en = topic_results.get("academic-en")
    if en:
        m = [r for r in en["runs"] if r["phase"] == "measure"]
        if m:
            active = sum(1 for r in m if not r["effective_skip_vertex"])
            rate = active / len(m)
            metrics["4_en_to_vertex_active_rate"] = {
                "n": len(m),
                "active": active,
                "rate": round(rate, 4),
                "threshold": 1.0,
                "verdict": "PASS" if rate >= 1.0 else "REVIEW",
            }

    # Metric 5: KO → naver 활성 (academic-ko measure runs 중 eff_skip=True 비율 + legacy.naver_count > 0)
    ko = topic_results.get("academic-ko")
    if ko:
        m = [r for r in ko["runs"] if r["phase"] == "measure"]
        if m:
            skip_v = sum(1 for r in m if r["effective_skip_vertex"])
            naver_hits = sum(1 for r in m if (r["legacy"].get("naver_count") or 0) > 0)
            metrics["5_ko_to_naver_active_rate"] = {
                "n": len(m),
                "eff_skip_vertex_count": skip_v,
                "naver_hit_count": naver_hits,
                "skip_rate": round(skip_v / len(m), 4),
                "naver_rate": round(naver_hits / len(m), 4),
                "threshold_skip": 1.0,
                "threshold_naver": 0.8,
                "verdict": "PASS" if (skip_v / len(m) >= 1.0 and naver_hits / len(m) >= 0.8) else "REVIEW",
            }

    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 구조 검증")
    parser.add_argument("--warmup-only", action="store_true", help="warmup 만 (measure skip)")
    parser.add_argument("--topic", default="", help="단일 토픽만 (key: business-venfobel/academic-en/academic-ko)")
    parser.add_argument("--warmup", type=int, default=WARMUP_RUNS)
    parser.add_argument("--measure", type=int, default=MEASURE_RUNS)
    parser.add_argument("--timeout", type=float, default=PER_RUN_TIMEOUT_S)
    parser.add_argument("--sleep", type=float, default=INTER_RUN_SLEEP_S)
    args = parser.parse_args()

    out_dir = PROJECT_ROOT / "scripts" / "output" / "§academic-1"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "c_ab_run.log"
    logger = setup_logging(log_path)
    logger.info("=" * 60)
    logger.info("§academic-1 Step C-2 measurement driver — start")
    logger.info("standards: warmup=%d measure=%d timeout=%ds sleep=%ds dry_run=%s",
                args.warmup, args.measure, args.timeout, args.sleep, args.dry_run)
    logger.info("host=%s python=%s", socket.gethostname(), sys.executable)
    logger.info("=" * 60)

    detect_fn, detect_src = _load_production_detect_query_lang()
    logger.info("[main] detect_query_lang source = %s", detect_src)

    measure_n = 0 if args.warmup_only else args.measure
    topic_keys = [args.topic] if args.topic else list(TOPICS.keys())
    topic_results: dict[str, dict] = {}

    for k in topic_keys:
        if k not in TOPICS:
            logger.error("[main] unknown topic key: %s", k)
            continue
        cfg = TOPICS[k]
        try:
            tr = measure_topic(k, cfg, args.warmup, measure_n, args.timeout, args.sleep,
                               args.dry_run, logger, detect_fn)
            topic_results[k] = tr
        except Exception as e:
            logger.exception("[main] topic=%s aborted: %s", k, e)
            topic_results[k] = {"topic_key": k, "error": f"{type(e).__name__}: {e}"}

    logger.info("[main] lang-detect accuracy benchmark (10 labeled queries)")
    lang_acc = lang_detect_accuracy(logger, detect_fn)
    lang_acc["detect_source"] = detect_src

    metrics = aggregate_metrics(topic_results, lang_acc)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "standards": {
            "warmup_runs": args.warmup,
            "measure_runs": measure_n,
            "per_run_timeout_s": args.timeout,
            "inter_run_sleep_s": args.sleep,
            "PYTHONIOENCODING": os.getenv("PYTHONIOENCODING", ""),
        },
        "host": socket.gethostname(),
        "python": sys.executable,
        "dry_run": args.dry_run,
        "warmup_only": args.warmup_only,
        "topic_results": topic_results,
        "lang_detect": lang_acc,
        "metrics": metrics,
    }
    out_path = out_dir / "c_ab_results.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("→ wrote %s", out_path)
    logger.info("=" * 60)
    logger.info("[summary]")
    for k, v in metrics.items():
        verdict = v.get("verdict") if isinstance(v, dict) else ""
        logger.info("  %s: %s", k, verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
