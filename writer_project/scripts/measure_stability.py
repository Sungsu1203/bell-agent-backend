# -*- coding: utf-8 -*-
"""§13-9 metric — n=5 안정성 측정 (출력 언어·표 추출·슬라이드 수 편차).

close 조건:
  - slide_spread = max - min  ≤ 2
  - all_korean = True (모든 슬라이드 제목·본문이 한국어 우세)
  - all_tables_match = True (각 run 의 TableSpec 개수 == X')

출력: 콘솔 보고 + JSON 파일 (logs/stability_<slug>_<timestamp>.json).
"""
from __future__ import annotations
import argparse
import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path

# 출처 마커 패턴 — 본문 침투 시 FAIL, notes 에 ≥1개 있어야 PASS.
URL_RE = re.compile(r"https?://\S+")
FOOTNOTE_RE = re.compile(r"\[\^[^\]]+\]")
FILE_CITE_RE = re.compile(r"\[[^\]]*\.(?:pdf|docx|xlsx|md|html?|txt|csv|hwp)\]", re.IGNORECASE)

# §13-7 (2026-05-09) 안전장치 (Vertex quota retry 누적·output buffer flush 누락 대응):
# - 각 run 의 plan_deck 호출에 wall-clock timeout 적용 (langchain retry 가 무한 backoff 못 하도록).
# - run 간 sleep 으로 rate limit 회피.
# - print 모두 flush=True (background 작업 강제 종료 시 buffer 잃음 회피).
#
# §13-7-3-bypass (2026-05-09): retry 차단 검증 우선 — sleep 은 기존 60s 유지, max_retries=0
# 단독 효과 측정. 정상이면 "retry 누적이 root cause" 박제, 비정상이면 sleep/다른 원인 추가 진단.
# - DEFAULT_REGION asia-northeast3 → us-central1 (이전 baseline 으로 복귀).
# - DEFAULT_MAX_RETRIES 0 (langchain internal retry 차단 — 가장 정밀한 root cause 검증 변수).
DEFAULT_PER_RUN_TIMEOUT_S = 180.0
DEFAULT_INTER_RUN_SLEEP_S = 0.0  # OpenAI 는 0, Vertex 는 60s 명시 (--inter-run-sleep 60)
DEFAULT_REGION = "us-central1"
DEFAULT_MAX_RETRIES = 0  # langchain ChatVertexAI internal _completion_with_retry 차단


def _print(msg: str = "") -> None:
    """flush=True 보장 print — 측정 도중 task killed 시 buffer 손실 방지."""
    print(msg, flush=True)


def _invoke_with_timeout(fn, timeout_s: float, *args, **kwargs):
    """ThreadPoolExecutor 로 fn 호출 wrap, timeout 초과 시 FuturesTimeoutError raise.

    §13-8 (2026-05-10) 박제 — ThreadPoolExecutor cancel 불가 함정:
    - timeout 발동 시 future.result() 만 raise. 내부 LLM 호출은 background 에서 계속.
    - 이론상 cancelled future 가 종료되기 전 다음 run 시작 시 OTPM/RPM 누적 위험.
    - §13-8 phase 2 안전 마진 검증 (claude-sonnet-4-6 venfobel 기준):
      * phase 1 단독 run OTPM = 4,035 tok/min (Tier 1 한도 8,000 의 50%)
      * inter-run-sleep 60s 동안 OTPM budget refresh 가능
      * background future 의 anthropic SDK timeout = 600s — 240s 측정 timeout 후 최대 360s
        잔여. 다음 run 의 OTPM 과 합쳐도 Anthropic Sonnet API 호출 1개당 ≤4K rate →
        2개 동시 ≤8K (한도 ±경계). 운영상 안전.
      * RPM 한도는 Tier 1 50/min — 충분히 여유.
    - 진짜 cancel 이 필요하면 multiprocessing 또는 ProcessPoolExecutor 로 강제 종료.
      현재 측정 인프라는 OTPM 안전 마진 + 60s sleep 으로 보호.
    """
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(fn, *args, **kwargs)
        return future.result(timeout=timeout_s)


def _count_source_markers(text: str) -> int:
    if not text:
        return 0
    return (
        len(URL_RE.findall(text))
        + len(FOOTNOTE_RE.findall(text))
        + len(FILE_CITE_RE.findall(text))
    )

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 부모 디렉토리 import 경로 보장
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.export.planner import plan_deck
from scripts.count_meaningful_tables import find_meaningful_tables


def _korean_ratio(text: str) -> float:
    """텍스트의 한국어 음절 비율 (영문자/한글 음절 중 한글 비율)."""
    if not text:
        return 1.0
    kor = sum(1 for c in text if "가" <= c <= "힯")
    eng = sum(1 for c in text if c.isascii() and c.isalpha())
    total = kor + eng
    if total == 0:
        return 1.0  # 숫자/기호만 있는 경우 — 언어 판정 무의미
    return kor / total


def _detect_lang(deck) -> tuple[str, float]:
    """deck 의 모든 텍스트(제목·body·bullets·table 셀)에 대해 한국어 비율 산출.

    return: ('ko' | 'en' | 'mixed', ratio)
      - ratio ≥ 0.7 → 'ko'
      - ratio ≤ 0.3 → 'en'
      - 그 외 → 'mixed'
    """
    parts: list[str] = []
    for s in deck.slides:
        if s.title:
            parts.append(s.title)
        if s.body:
            parts.append(s.body)
        if s.bullets:
            parts.extend(b for b in s.bullets if b)
        if s.table:
            parts.extend(s.table.header)
            for row in s.table.rows:
                parts.extend(row)
    joined = " ".join(parts)
    ratio = _korean_ratio(joined)
    if ratio >= 0.7:
        lang = "ko"
    elif ratio <= 0.3:
        lang = "en"
    else:
        lang = "mixed"
    return lang, ratio


def _count_tables(deck) -> int:
    return sum(1 for s in deck.slides if s.table is not None)


def _source_marker_locations(deck) -> tuple[int, int]:
    """deck 의 (본문 침투 마커 수, 노트 마커 수) 반환.

    본문 = bullets + body + table header/cell  (출처 마커 0개여야 PASS)
    notes = slide.notes  (입력 md 에 마커 있으면 ≥1개여야 PASS)
    """
    body_n = 0
    notes_n = 0
    for s in deck.slides:
        if s.body:
            body_n += _count_source_markers(s.body)
        if s.bullets:
            for b in s.bullets:
                body_n += _count_source_markers(b)
        if s.table:
            for h in s.table.header:
                body_n += _count_source_markers(h)
            for row in s.table.rows:
                for cell in row:
                    body_n += _count_source_markers(cell)
        if s.notes:
            notes_n += _count_source_markers(s.notes)
    return body_n, notes_n


def measure_run(
    md_path: Path, *, slug: str, topic_title: str, n: int = 5,
    model: str | None = None,
    per_run_timeout_s: float = DEFAULT_PER_RUN_TIMEOUT_S,
    inter_run_sleep_s: float = DEFAULT_INTER_RUN_SLEEP_S,
    warmup_runs: int = 0,
    warmup_md_path: Path | None = None,
) -> dict:
    md_text = md_path.read_text(encoding="utf-8")
    pre = find_meaningful_tables(md_text)
    x_prime = sum(1 for t in pre if t["meaningful"])
    md_source_markers = _count_source_markers(md_text)
    _print(f"=== 사전 측정 ===")
    _print(f"  md: {md_path}  ({len(md_text):,} chars)")
    _print(f"  유의미한 표 X' = {x_prime}")
    _print(f"  입력 md 출처 마커 (URL+footnote+파일인용): {md_source_markers}")
    if model:
        _print(f"  강제 model = {model!r} (plan_deck 에 인자로 전달, reset_llm 후 새 인스턴스)")
    _print(f"  안전장치: per_run_timeout={per_run_timeout_s:.0f}s  inter_run_sleep={inter_run_sleep_s:.0f}s")

    # §13-7 (2026-05-09) warmup — Vertex AI 등 cold start 영향이 큰 provider 평가 시 사전 호출.
    # 본 측정 시작 전 warmup_runs 회 호출하여 model instance / region pool 데움.
    # 실패해도 무시 (warmup 자체가 throw 해도 본 측정 진입).
    if warmup_runs > 0:
        warmup_path = warmup_md_path or md_path
        warmup_text = warmup_path.read_text(encoding="utf-8")
        _print(f"  [warmup] {warmup_runs}회 사전 호출 ({warmup_path.name}, {len(warmup_text)} chars)")
        for w in range(warmup_runs):
            t_w = time.monotonic()
            try:
                # §13-7-3 (2026-05-09): _record_metrics=False — warmup 은 metrics.ndjson 미기록,
                # logs/warmup_log.ndjson 별도 보존. 운영 LLM call metric 오염 방지.
                _invoke_with_timeout(
                    plan_deck, per_run_timeout_s,
                    warmup_text, slug=f"{slug}_warmup", topic_title=topic_title, model=model,
                    _record_metrics=False,
                )
                _print(f"    warmup {w+1}/{warmup_runs}: OK ({time.monotonic()-t_w:.1f}s)")
            except Exception as err:
                _print(f"    warmup {w+1}/{warmup_runs}: FAIL ({type(err).__name__}: {str(err)[:80]}) — 본 측정 계속")

    runs: list[dict] = []
    for i in range(n):
        if i > 0 and inter_run_sleep_s > 0:
            _print(f"  [sleep {inter_run_sleep_s:.0f}s — rate limit 보호]")
            time.sleep(inter_run_sleep_s)
        _print(f"  run {i+1} 시작 …")
        t0 = time.monotonic()
        try:
            deck = _invoke_with_timeout(
                plan_deck, per_run_timeout_s,
                md_text, slug=slug, topic_title=topic_title, model=model,
            )
            lat = time.monotonic() - t0
            slide_count = len(deck.slides)
            lang, ratio = _detect_lang(deck)
            table_count = _count_tables(deck)
            body_n, notes_n = _source_marker_locations(deck)
            # §13-8 (2026-05-10): plan_deck 모듈-global 에서 usage_metadata 회수.
            # input/output tokens 분포 + 비용 추정용. 실패 시 None 유지 (호환).
            try:
                from agent.export import planner as _planner_mod
                usage = getattr(_planner_mod, "_LAST_USAGE_METADATA", None)
            except Exception:
                usage = None
            entry = {
                "run": i + 1,
                "slide_count": slide_count,
                "table_count": table_count,
                "lang": lang,
                "kor_ratio": round(ratio, 3),
                "src_in_body": body_n,
                "src_in_notes": notes_n,
                "latency_s": round(lat, 2),
                "input_tokens": (usage or {}).get("input_tokens") if isinstance(usage, dict) else None,
                "output_tokens": (usage or {}).get("output_tokens") if isinstance(usage, dict) else None,
                "ok": True,
            }
            _tok_str = ""
            if entry["input_tokens"] is not None and entry["output_tokens"] is not None:
                _tok_str = f"  tok(in={entry['input_tokens']:,} out={entry['output_tokens']:,})"
            _print(f"  run {i+1}: slides={slide_count}  tables={table_count}  "
                   f"lang={lang} (kor={ratio:.2f})  src(body={body_n},notes={notes_n})  "
                   f"lat={lat:.1f}s{_tok_str}")
        except FuturesTimeoutError:
            lat = time.monotonic() - t0
            entry = {
                "run": i + 1,
                "ok": False,
                "error_class": "TimeoutError",
                "error_msg": f"per-run timeout {per_run_timeout_s:.0f}s 초과",
                "latency_s": round(lat, 2),
            }
            _print(f"  run {i+1}: TIMEOUT ({per_run_timeout_s:.0f}s 초과 — quota retry 누적 의심)")
        except Exception as err:
            lat = time.monotonic() - t0
            entry = {
                "run": i + 1,
                "ok": False,
                "error_class": type(err).__name__,
                "error_msg": str(err)[:200],
                "latency_s": round(lat, 2),
            }
            _print(f"  run {i+1}: FAIL ({type(err).__name__}: {str(err)[:120]})")
        runs.append(entry)

    ok_runs = [r for r in runs if r.get("ok")]
    if ok_runs:
        slide_counts = [r["slide_count"] for r in ok_runs]
        slide_spread = max(slide_counts) - min(slide_counts)
        all_korean = all(r["lang"] == "ko" for r in ok_runs)
        all_tables_match = all(r["table_count"] == x_prime for r in ok_runs)
        # 출처 metric: 본문 침투 0 + (입력 md 에 마커 있으면 노트 ≥1)
        all_body_clean = all(r["src_in_body"] == 0 for r in ok_runs)
        if md_source_markers > 0:
            all_notes_have_src = all(r["src_in_notes"] >= 1 for r in ok_runs)
        else:
            all_notes_have_src = True  # 입력 자체에 마커 없으면 metric 무관 PASS
        source_consistency = all_body_clean and all_notes_have_src
    else:
        slide_spread = None
        all_korean = False
        all_tables_match = False
        all_body_clean = False
        all_notes_have_src = False
        source_consistency = False

    passed = (
        len(ok_runs) == n
        and slide_spread is not None
        and slide_spread <= 2
        and all_korean
        and all_tables_match
        and source_consistency
    )

    # §13-8 (2026-05-10): 7개 지표 자동 산출 — latency / token / cost 분포.
    def _stat(vals: list[float]) -> dict:
        if not vals:
            return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
        m = sum(vals) / len(vals)
        v = sum((x - m) ** 2 for x in vals) / len(vals)
        return {"n": len(vals), "mean": round(m, 2), "std": round(v ** 0.5, 2),
                "min": round(min(vals), 2), "max": round(max(vals), 2)}

    lat_vals = [float(r["latency_s"]) for r in ok_runs if r.get("latency_s") is not None]
    in_tok_vals = [int(r["input_tokens"]) for r in ok_runs if r.get("input_tokens") is not None]
    out_tok_vals = [int(r["output_tokens"]) for r in ok_runs if r.get("output_tokens") is not None]
    timeout_count = sum(1 for r in runs if r.get("error_class") == "TimeoutError")
    other_fail = sum(1 for r in runs if not r.get("ok") and r.get("error_class") != "TimeoutError")

    # 비용 추정 — 모델 기반 hardcoded rates (1M token 당 USD).
    # claude-sonnet-4-6 (2026-05 기준 공시): input $3 / output $15.
    # 다른 모델 추가 시 _PRICE 사전에 등록.
    _PRICE = {
        "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
        "claude-opus-4-7": {"in": 15.0, "out": 75.0},
        "claude-haiku-4-5": {"in": 1.0, "out": 5.0},
        "gpt-4o": {"in": 2.5, "out": 10.0},
        "gemini-2.5-pro": {"in": 1.25, "out": 5.0},
        "gemini-2.5-flash": {"in": 0.075, "out": 0.30},
    }
    _rate = _PRICE.get((model or "").strip().lower())
    if _rate and in_tok_vals and out_tok_vals:
        cost_runs = [
            (i_tok / 1e6) * _rate["in"] + (o_tok / 1e6) * _rate["out"]
            for i_tok, o_tok in zip(in_tok_vals, out_tok_vals)
        ]
        cost_total = round(sum(cost_runs), 4)
        cost_per_run = round(cost_total / len(cost_runs), 4) if cost_runs else None
    else:
        cost_runs = []
        cost_total = None
        cost_per_run = None

    metrics_7 = {
        "ok_runs_count": len(ok_runs),
        "timeout_count": timeout_count,
        "other_fail_count": other_fail,
        "latency_stats": _stat(lat_vals),
        "input_tokens_stats": _stat([float(x) for x in in_tok_vals]),
        "output_tokens_stats": _stat([float(x) for x in out_tok_vals]),
        "slide_count_distribution": [r["slide_count"] for r in ok_runs if r.get("slide_count") is not None],
        "cost_estimate": {
            "model": model,
            "rate_in_per_mtok_usd": _rate["in"] if _rate else None,
            "rate_out_per_mtok_usd": _rate["out"] if _rate else None,
            "per_run_usd": cost_per_run,
            "total_usd": cost_total,
            "n_runs": len(cost_runs),
        },
    }

    summary = {
        "md_path": str(md_path),
        "slug": slug,
        "topic_title": topic_title,
        "n": n,
        "x_prime": x_prime,
        "md_source_markers": md_source_markers,
        "runs": runs,
        "slide_spread": slide_spread,
        "lang_consistency": all_korean,
        "table_consistency": all_tables_match,
        "source_body_clean": all_body_clean,
        "source_notes_present": all_notes_have_src,
        "source_consistency": source_consistency,
        "ok_runs": len(ok_runs),
        "pass": passed,
        "metrics_7": metrics_7,
    }
    return summary


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--md", required=True, help="입력 .md 경로")
    p.add_argument("--slug", required=True)
    p.add_argument("--topic-title", required=True)
    p.add_argument("--n", type=int, default=5)
    p.add_argument("--model", default=None, help="LLM 모델 ID 명시 (미지정 시 .env 의 LLM_MODEL 또는 provider default). 예: gpt-4o, gemini-2.5-pro, gemini-2.5-flash")
    p.add_argument("--out", default=None, help="결과 JSON 저장 경로 (default: logs/stability_<slug>_<model>_<ts>.json)")
    p.add_argument("--per-run-timeout", type=float, default=DEFAULT_PER_RUN_TIMEOUT_S, help=f"한 run 의 wall-clock timeout (default: {DEFAULT_PER_RUN_TIMEOUT_S:.0f}s). 초과 시 fail 처리하고 다음 run 진입.")
    p.add_argument("--inter-run-sleep", type=float, default=DEFAULT_INTER_RUN_SLEEP_S, help="run 간 sleep 초 (Vertex 권장 60s, OpenAI 0). default 0.")
    p.add_argument("--region", default=DEFAULT_REGION, help=f"Vertex AI region (default: {DEFAULT_REGION}). 명시 시 GCP_REGION 환경변수 set + reload_config_inplace + reset_llm.")
    p.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES, help=f"Vertex langchain internal retry 횟수 (default: {DEFAULT_MAX_RETRIES}). 0 = 즉시 fail (quota retry 누적 차단). VERTEX_MAX_RETRIES env 로 전달.")
    p.add_argument("--warmup-runs", type=int, default=0, help="본 측정 전 warmup 호출 횟수. cold start 회피 (Vertex 권장 1~2회). default 0.")
    p.add_argument("--warmup-input", default=None, help="warmup 입력 .md 경로. 짧은 입력 권장 (예: reports/_cli_test/test.md). 미명시 시 --md 와 동일.")
    args = p.parse_args()

    # §13-7-3c (2026-05-09): region override 적용 (us-central1 → asia-northeast3 등)
    # 진행 절차: env set → core.config reload → core.llm reset → plan_deck 호출 시 새 location 적용.
    # 주의: reload_config_inplace 가 글로벌 .env 를 override=True 로 재로드 → LLM_PROVIDER 등
    # 호출자 환경변수 덮어씀. provider 보존을 위해 reload 전후 명시 capture·복원.
    #
    # §13-7-3-bypass (2026-05-09): VERTEX_MAX_RETRIES 도 함께 env 전달 → reload 후 CFG 반영.
    #
    # §13-7-3-regress (2026-05-09): bypass 블록은 Vertex 측정 전용. OpenAI 측정 (회귀 테스트 등)
    # 시 진입 시 reload_config_inplace 두 번째 호출이 .env 의 LLM_PROVIDER=vertexai 를
    # 덮어써 ImportError 유발. provider 분기로 OpenAI 경로에서는 bypass 블록 skip.
    _provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if _provider == "vertexai" and (args.region or args.max_retries is not None):
        if args.region:
            os.environ["GCP_REGION"] = args.region
        if args.max_retries is not None:
            os.environ["VERTEX_MAX_RETRIES"] = str(args.max_retries)
        saved_provider = os.environ.get("LLM_PROVIDER", "")
        saved_model = os.environ.get("LLM_MODEL", "")
        from core.config import reload_config_inplace
        from core.llm import reset_llm
        reload_config_inplace()
        if saved_provider:
            os.environ["LLM_PROVIDER"] = saved_provider
        if saved_model:
            os.environ["LLM_MODEL"] = saved_model
        if saved_provider or saved_model:
            reload_config_inplace()  # 복원된 env 값 다시 반영
        reset_llm()
        _print(f"[bypass] GCP_REGION={args.region!r}  VERTEX_MAX_RETRIES={args.max_retries}  "
               f"LLM_PROVIDER 보존={os.environ.get('LLM_PROVIDER','')!r}")
    elif _provider != "vertexai":
        _print(f"[bypass] skip — LLM_PROVIDER={_provider!r} (Vertex 전용 bypass 블록 미진입)")

    summary = measure_run(
        Path(args.md), slug=args.slug, topic_title=args.topic_title,
        n=args.n, model=args.model,
        per_run_timeout_s=args.per_run_timeout,
        inter_run_sleep_s=args.inter_run_sleep,
        warmup_runs=args.warmup_runs,
        warmup_md_path=Path(args.warmup_input) if args.warmup_input else None,
    )
    summary["model"] = args.model  # 결과 JSON 에 모델 ID 박제
    summary["per_run_timeout_s"] = args.per_run_timeout
    summary["inter_run_sleep_s"] = args.inter_run_sleep
    summary["warmup_runs"] = args.warmup_runs
    summary["warmup_input"] = args.warmup_input
    summary["region"] = args.region
    summary["max_retries"] = args.max_retries
    _print(f"\n=== close 조건 평가 ===")
    _print(f"  ok_runs:           {summary['ok_runs']}/{summary['n']}")
    _print(f"  slide_spread:      {summary['slide_spread']}  (≤2 통과)")
    _print(f"  lang_consistency:  {summary['lang_consistency']}  (True 통과)")
    _print(f"  table_consistency: {summary['table_consistency']}  (True 통과, X'={summary['x_prime']})")
    _print(f"  src_body_clean:    {summary['source_body_clean']}  (True 통과 — 본문 마커 0)")
    _print(f"  src_notes_present: {summary['source_notes_present']}  (True 통과 — 노트 마커 ≥1)")
    _print(f"  PASS: {summary['pass']}")

    # §13-8 (2026-05-10): 7개 지표 콘솔 보고
    m7 = summary.get("metrics_7", {})
    _print(f"\n=== §13-8 7-metric 보고 ===")
    _print(f"  (1) ok_runs:           {m7.get('ok_runs_count')}/{summary['n']}  "
           f"(timeout={m7.get('timeout_count')}, other_fail={m7.get('other_fail_count')})")
    _print(f"  (2) timeout 분류:      "
           f"{'A (clean baseline)' if m7.get('timeout_count', 0) == 0 else ('B (' + str(m7.get('timeout_count')) + '/' + str(summary['n']) + ' timeout)' if m7.get('timeout_count', 0) <= 2 else 'C (≥3 timeout — 운영 부적합)')}")
    ls = m7.get("latency_stats", {})
    _print(f"  (3) latency:           mean={ls.get('mean')}s std={ls.get('std')}s "
           f"min={ls.get('min')}s max={ls.get('max')}s")
    its = m7.get("input_tokens_stats", {})
    ots = m7.get("output_tokens_stats", {})
    _print(f"  (4) input_tokens:      mean={its.get('mean')} std={its.get('std')} "
           f"min={its.get('min')} max={its.get('max')}")
    _print(f"  (5) output_tokens:     mean={ots.get('mean')} std={ots.get('std')} "
           f"min={ots.get('min')} max={ots.get('max')}")
    _print(f"  (6) slide_count 분포: {m7.get('slide_count_distribution')}  "
           f"(phase 1=37, gpt-4o baseline=37.4±0.5)")
    ce = m7.get("cost_estimate", {})
    _print(f"  (7) cost 추정:         per_run=${ce.get('per_run_usd')}  "
           f"total(n={ce.get('n_runs')})=${ce.get('total_usd')} USD  "
           f"(rates: in=${ce.get('rate_in_per_mtok_usd')}/Mtok, out=${ce.get('rate_out_per_mtok_usd')}/Mtok)")

    if args.out:
        out = Path(args.out)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_tag = f"_{args.model.replace('-', '').replace('.', '')}" if args.model else ""
        out = Path("logs") / f"stability_{args.slug}{model_tag}_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(f"\n결과 저장: {out}")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
