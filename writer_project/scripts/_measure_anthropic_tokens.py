"""§13-8 진단 phase 1 — claude-sonnet-4-6 venfobel 1-run usage_metadata 추출.

목적:
- Tier 1 OTPM 8K/min 한도에서 venfobel (34K char) → structured output (43 slides) 의
  실측 latency + input/output tokens 데이터 확보.
- §13-7 표준 baseline (timeout=240s, max_retries=0) 진입 가능성 사전 평가.
- 진단 단계라 timeout=600s 로 override (CFG mutate, .env 미수정).
- max_retries=0 은 .env.anthropic 표준값 그대로 — retry sleep 로 latency 오염 차단.

실행: $env:LLM_PROVIDER='anthropic'; .venv_anthropic\\Scripts\\python.exe -m scripts._measure_anthropic_tokens
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure project root on sys.path for module imports
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.config import load_topic_env
load_topic_env()

# 진단 phase: timeout 만 600s 로 override (max_retries=0 은 .env.anthropic 표준 유지).
# CFG 직접 mutate — overlay 재로드 회피 (load_dotenv override=True 함정 방지).
import core.config as _cfg
_cfg.CFG.ANTHROPIC_REQUEST_TIMEOUT = 600.0
print(f"[diag] CFG.ANTHROPIC_REQUEST_TIMEOUT override → 600.0 (진단 전용)")
print(f"[diag] CFG.ANTHROPIC_MAX_RETRIES = {_cfg.CFG.ANTHROPIC_MAX_RETRIES} (.env.anthropic 표준 — 0 기대)")

from core.llm import reset_llm, get_llm
from agent.export.planner import get_pptx_planner_prompt, _count_headings
from agent.export.spec import SlideDeckSpec


def _verify_llm_attrs(llm) -> dict:
    """ChatAnthropic 인스턴스에 timeout/max_retries 가 실제 적용됐는지 검증.

    §13-7-3-bypass 함정 패턴 재발 방지: build_kwargs 에서 strip 됐거나 ctor 가 kwarg 를
    받지 않아 default 로 fallback 한 경우를 catch.
    """
    attrs = {}
    for name in ("model", "max_retries", "default_request_timeout", "anthropic_api_url"):
        try:
            attrs[name] = getattr(llm, name, "<missing>")
        except Exception as e:
            attrs[name] = f"<err:{type(e).__name__}>"
    # langchain-anthropic 버전 차이 대응
    try:
        attrs["timeout_attr"] = getattr(llm, "timeout", "<missing>")
    except Exception:
        attrs["timeout_attr"] = "<err>"
    return attrs


def main() -> int:
    md_path = Path("reports/venfobel-vitamin/latest.md")
    md_text = md_path.read_text(encoding="utf-8")
    n_h2, n_h3 = _count_headings(md_text)
    n_total_slides = 1 + n_h2 + n_h3
    topic_title = "종근당 '벤포벨S' 2026 광고기획 / 고함량 활성비타민 시장 3C 분석"
    slug = "venfobel-vitamin"

    print(f"[setup] md={md_path}  ({len(md_text):,} chars)")
    print(f"[setup] headings: ## {n_h2}  ### {n_h3}  → 총 슬라이드 목표 {n_total_slides}")
    print(f"[setup] provider={os.environ.get('LLM_PROVIDER')!r}  model=claude-sonnet-4-6")

    reset_llm()
    llm = get_llm(model="claude-sonnet-4-6")
    attrs = _verify_llm_attrs(llm)
    print(f"[verify] LLM ctor 적용값: {json.dumps(attrs, default=str)}")
    if attrs.get("max_retries") != 0:
        print(f"[WARN] max_retries 가 0 이 아닙니다 (실제={attrs.get('max_retries')!r}). "
              f"latency 오염 가능 — §13-7 표준 위반.")

    llm_planner = llm.bind(temperature=0.1)
    structured = llm_planner.with_structured_output(SlideDeckSpec, include_raw=True)
    chain = get_pptx_planner_prompt() | structured

    print("[run] invoke …")
    t0 = time.monotonic()
    try:
        res = chain.invoke({
            "topic_title": topic_title,
            "slug": slug,
            "md_text": md_text,
            "n_h2_chapters": n_h2,
            "n_h3_sections": n_h3,
            "n_total_slides": n_total_slides,
        })
    except Exception as err:
        lat = time.monotonic() - t0
        print(f"[run] FAIL after {lat:.1f}s — {type(err).__name__}: {str(err)[:160]}")
        return 1
    lat = time.monotonic() - t0

    raw = res.get("raw") if isinstance(res, dict) else None
    parsed = res.get("parsed") if isinstance(res, dict) else res
    usage = getattr(raw, "usage_metadata", None) if raw else None

    out = {
        "model": "claude-sonnet-4-6",
        "md_chars": len(md_text),
        "n_h2": n_h2,
        "n_h3": n_h3,
        "n_total_slides_target": n_total_slides,
        "n_slides_actual": len(parsed.slides) if parsed else None,
        "latency_s": round(lat, 2),
        "usage_metadata": usage,
        "ctor_attrs": attrs,
        "diag_timeout_override": 600.0,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    # OTPM 8K/min 평가
    if usage and isinstance(usage, dict):
        out_tok = usage.get("output_tokens") or 0
        if lat > 0:
            tok_per_min = out_tok / (lat / 60.0)
            print(f"[OTPM] 실측 output rate: {tok_per_min:,.0f} tok/min  (Tier 1 한도 8,000)")
            print(f"[OTPM] n=5 burst (60s inter-run-sleep) 시 보호 여부: "
                  f"{'안전 (run 간 budget refresh)' if lat < 60 else 'WARN — run 단독이 60s 초과'}")

    out_path = Path("logs") / f"anthropic_tokens_{int(time.time())}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
