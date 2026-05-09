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
    주의: thread cancel 안 됨 — timeout 후 백그라운드에서 호출 계속될 수 있으나 측정은 진행."""
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
            entry = {
                "run": i + 1,
                "slide_count": slide_count,
                "table_count": table_count,
                "lang": lang,
                "kor_ratio": round(ratio, 3),
                "src_in_body": body_n,
                "src_in_notes": notes_n,
                "latency_s": round(lat, 2),
                "ok": True,
            }
            _print(f"  run {i+1}: slides={slide_count}  tables={table_count}  "
                   f"lang={lang} (kor={ratio:.2f})  src(body={body_n},notes={notes_n})  "
                   f"lat={lat:.1f}s")
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
    if args.region or args.max_retries is not None:
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
