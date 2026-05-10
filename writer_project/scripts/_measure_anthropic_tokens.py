"""§13-8 진단 phase 1 — Anthropic 모델 venfobel 1-run usage_metadata 추출.

목적:
- Tier 1 OTPM 8K/min 한도에서 venfobel (34K char) → structured output (43 slides) 의
  실측 latency + input/output tokens 데이터 확보.
- §13-7 표준 baseline (timeout=240s, max_retries=0) 진입 가능성 사전 평가.
- 진단 단계라 timeout=600s 로 override (CFG mutate, .env 미수정).
- max_retries=0 은 .env.anthropic 표준값 그대로 — retry sleep 로 latency 오염 차단.

실행 예:
  $env:LLM_PROVIDER='anthropic'
  $env:PYTHONIOENCODING='utf-8'
  .venv_anthropic\\Scripts\\python.exe -m scripts._measure_anthropic_tokens \\
      --model claude-sonnet-4-6
  .venv_anthropic\\Scripts\\python.exe -m scripts._measure_anthropic_tokens \\
      --model claude-haiku-4-5-20251001

§13-8-3 (2026-05-10): CLI 인자화 — Sonnet/Haiku/Opus 평가 시 같은 도구 재사용.
"""
from __future__ import annotations

import argparse
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
    p = argparse.ArgumentParser(description="§13-8 phase 1 진단 — Anthropic 모델 1-run 측정")
    p.add_argument("--model", required=True, help="Anthropic 모델 ID (예: claude-sonnet-4-6, claude-haiku-4-5-20251001)")
    p.add_argument("--md", default="reports/venfobel-vitamin/latest.md", help="입력 .md (default: venfobel latest)")
    p.add_argument("--slug", default="venfobel-vitamin")
    p.add_argument("--topic-title", default="종근당 '벤포벨S' 2026 광고기획 / 고함량 활성비타민 시장 3C 분석")
    args = p.parse_args()

    md_path = Path(args.md)
    md_text = md_path.read_text(encoding="utf-8")
    n_h2, n_h3 = _count_headings(md_text)
    n_total_slides = 1 + n_h2 + n_h3
    topic_title = args.topic_title
    slug = args.slug

    print(f"[setup] md={md_path}  ({len(md_text):,} chars)")
    print(f"[setup] headings: ## {n_h2}  ### {n_h3}  → 총 슬라이드 목표 {n_total_slides}")
    print(f"[setup] provider={os.environ.get('LLM_PROVIDER')!r}  model={args.model}")

    reset_llm()
    llm = get_llm(model=args.model)
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
    parsing_error = res.get("parsing_error") if isinstance(res, dict) else None
    usage = getattr(raw, "usage_metadata", None) if raw else None

    # §13-8-3 (2026-05-10): parse fail 4 케이스 분류용 정밀 캡처.
    # A (schema mismatch): stop_reason='end_turn' + tool_use 0 → schema 무시 응답
    # B (tool_use 형식 fail): stop_reason='tool_use' + tool_calls 형식 위반 → ValidationError
    # C (truncation): stop_reason='max_tokens' → 출력 길이 한계
    # D (refusal): stop_reason='refusal' → safety 차단
    raw_meta: dict = {}
    if raw is not None:
        # response_metadata 에서 stop_reason 캡처 (langchain-anthropic 표기 다양 — 다중 키 시도)
        rmeta = getattr(raw, "response_metadata", {}) or {}
        raw_meta["stop_reason"] = rmeta.get("stop_reason") or rmeta.get("finish_reason")
        raw_meta["response_metadata_keys"] = sorted(list(rmeta.keys()))[:20]
        # tool_calls 개수 (parsed structured tool 호출)
        tc = getattr(raw, "tool_calls", None) or []
        raw_meta["tool_calls_count"] = len(tc) if isinstance(tc, list) else 0
        # invalid_tool_calls (parse 실패한 tool_use)
        itc = getattr(raw, "invalid_tool_calls", None) or []
        raw_meta["invalid_tool_calls_count"] = len(itc) if isinstance(itc, list) else 0
        # raw content preview (text 부분 + tool_use block 요약)
        content = getattr(raw, "content", None)
        if isinstance(content, str):
            raw_meta["content_type"] = "str"
            raw_meta["content_preview"] = content[:500]
        elif isinstance(content, list):
            raw_meta["content_type"] = "list"
            raw_meta["content_block_types"] = [
                (b.get("type") if isinstance(b, dict) else type(b).__name__) for b in content[:10]
            ]
            # 첫 번째 text block preview
            text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if text_blocks:
                raw_meta["first_text_preview"] = (text_blocks[0].get("text", "") or "")[:500]
            tool_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            raw_meta["tool_use_blocks_count"] = len(tool_blocks)
            if tool_blocks:
                # tool_use input preview (첫번째)
                _ti = tool_blocks[0].get("input")
                if isinstance(_ti, dict):
                    raw_meta["first_tool_input_keys"] = sorted(list(_ti.keys()))[:20]
                    # slides key 존재성
                    raw_meta["first_tool_has_slides_key"] = "slides" in _ti
                    if "slides" in _ti and isinstance(_ti["slides"], list):
                        raw_meta["first_tool_slides_count"] = len(_ti["slides"])
        else:
            raw_meta["content_type"] = type(content).__name__

    parse_err_info: dict = {}
    if parsing_error is not None:
        parse_err_info["error_type"] = type(parsing_error).__name__
        parse_err_info["error_msg"] = str(parsing_error)[:500]
        # §13-8-3 (2026-05-10): Pydantic ValidationError 의 e.errors() 구조화 캡처.
        # 각 에러: {loc: tuple, msg: str, input: any, type: str, url: str}.
        # truncation 없이 모든 ValidationError 박제 — schema-relax 후속 task ground truth.
        try:
            _errors_method = getattr(parsing_error, "errors", None)
            if callable(_errors_method):
                _errs = _errors_method()
                if isinstance(_errs, list):
                    parse_err_info["validation_errors"] = [
                        {
                            "loc": list(e.get("loc", [])) if isinstance(e, dict) else [],
                            "msg": (e.get("msg") if isinstance(e, dict) else str(e))[:300],
                            "type": (e.get("type") if isinstance(e, dict) else "") or "",
                            "input_repr": repr(e.get("input"))[:120] if isinstance(e, dict) else "",
                            "url": (e.get("url") if isinstance(e, dict) else "") or "",
                        }
                        for e in _errs
                    ]
                    parse_err_info["validation_error_count"] = len(_errs)
        except Exception as _ee:
            parse_err_info["errors_capture_fail"] = f"{type(_ee).__name__}: {_ee}"

    # §13-8-3 (2026-05-10): case 자동 분류 + nuance + slides_overshoot + fix_options 박제.
    case_classification = None
    case_nuance = None
    if parsed is None:
        sr = (raw_meta.get("stop_reason") or "").lower()
        tuc = raw_meta.get("tool_use_blocks_count", 0)
        itc = raw_meta.get("invalid_tool_calls_count", 0)
        if sr == "max_tokens":
            case_classification = "C (truncation)"
        elif "refus" in sr:
            case_classification = "D (refusal/safety)"
        elif sr == "tool_use" and itc > 0:
            case_classification = "B (tool_use 형식 fail — invalid tool_calls)"
        elif sr in ("end_turn", "stop") and tuc == 0:
            case_classification = "A (schema mismatch — tool 호출 안 함)"
        elif sr == "tool_use" and tuc > 0 and parsing_error is not None:
            case_classification = "B (tool_use 형식 fail — Pydantic ValidationError)"
            # Pydantic ValidationError 만으로는 A/B 경계 모호 — payload 가 schema 따르려 했으나
            # type strict 검증 실패. prompt patch 또는 schema relax 양쪽 가능.
            case_nuance = "B/A 경계 — tool_use 응답 valid (schema 따르려는 의도 OK), payload type strict fail (prompt patch 또는 schema relax 가능)"
        else:
            case_classification = f"? unclassified (stop_reason={sr!r}, tool_use={tuc}, invalid={itc})"

    slides_in_raw = raw_meta.get("first_tool_slides_count")
    slides_overshoot = (slides_in_raw - n_total_slides) if slides_in_raw is not None else None

    fix_options = []
    if parse_err_info.get("validation_errors"):
        # ValidationError loc 패턴 분석 — 모든 error 가 동일 field path 면 단일 fix 권고 구체화
        _locs = [tuple(e.get("loc", [])) for e in parse_err_info["validation_errors"]]
        _last_keys = [l[-1] for l in _locs if l]
        _common_field = _last_keys[0] if _last_keys and all(k == _last_keys[0] for k in _last_keys) else None
        fix_options = [
            {
                "id": "schema_relax",
                "desc": (
                    f"SlideSpec.{_common_field} 를 Optional[List[str]] = None 으로 완화 — "
                    "Haiku null 응답 허용 + gpt-4o/Sonnet omit 응답 호환"
                    if _common_field else
                    "SlideSpec 의 strict 필드를 Optional 로 완화 — null 응답 허용"
                ),
                "scope": "agent/export/spec.py 의 SlideSpec 정의",
                "side_effect": "gpt-4o / Sonnet 회귀 테스트 필요 (default behavior 변동 가능)",
                "permanence": "영구 자산 (모든 모델 호환성 향상)",
            },
            {
                "id": "prompt_patch",
                "desc": (
                    f"prompt 에 '{_common_field} 가 없으면 [] 또는 필드 생략' 명시"
                    if _common_field else
                    "prompt 에 'null 대신 빈 리스트 또는 필드 생략' 명시"
                ),
                "scope": "prompts/get_pptx_planner_prompt() — system 또는 instruction 라인 1~2 추가",
                "side_effect": "prompt 길이 증가 → input_tokens 누적 비용",
                "permanence": "모델별 누적 비용 (영구 자산 아님)",
            },
            {
                "id": "schema_relax_with_validator",
                "desc": (
                    f"SlideSpec.{_common_field} 를 Optional 완화 + @field_validator 로 None → []"
                    if _common_field else
                    "Optional 완화 + validator 로 None → 적절 default 변환"
                ),
                "scope": "agent/export/spec.py — Pydantic validator 추가",
                "side_effect": "renderer/소비자 측 None 처리 불필요 (validator 가 normalize)",
                "permanence": "영구 자산 + 정합성 유지",
            },
        ]

    out = {
        "model": args.model,
        "md_chars": len(md_text),
        "n_h2": n_h2,
        "n_h3": n_h3,
        "n_total_slides_target": n_total_slides,
        "n_slides_actual": len(parsed.slides) if parsed else None,
        "latency_s": round(lat, 2),
        "usage_metadata": usage,
        "ctor_attrs": attrs,
        "diag_timeout_override": 600.0,
        # §13-8-3 정밀 진단 필드
        "parsed_is_none": parsed is None,
        "parsing_error": parse_err_info,
        "raw_diagnostic": raw_meta,
        # §13-8-3 자산화 필드 (commit B 보강 — schema-relax 후속 task ground truth)
        "case_classification": case_classification,
        "case_classification_nuance": case_nuance,
        "slides_in_raw": slides_in_raw,
        "slides_target": n_total_slides,
        "slides_overshoot": slides_overshoot,
        "fix_options": fix_options,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    # §13-8-3 case 분류 + slides_overshoot + fix_options 콘솔 보고
    if case_classification:
        print(f"\n[CASE] §13-8-3 분기: **{case_classification}**")
        if case_nuance:
            print(f"[NUANCE] {case_nuance}")
        if slides_in_raw is not None:
            print(f"[SLIDES] raw={slides_in_raw}  target={n_total_slides}  "
                  f"overshoot={slides_overshoot:+d}")
        if parse_err_info.get("validation_error_count"):
            print(f"[VAL_ERR] {parse_err_info['validation_error_count']}건 (구조화 박제 in JSON)")
        if fix_options:
            print(f"[FIX_OPTIONS] {len(fix_options)}종: {', '.join(o['id'] for o in fix_options)}")

    # OTPM 8K/min 평가
    if usage and isinstance(usage, dict):
        out_tok = usage.get("output_tokens") or 0
        if lat > 0:
            tok_per_min = out_tok / (lat / 60.0)
            print(f"[OTPM] 실측 output rate: {tok_per_min:,.0f} tok/min  (Tier 1 한도 8,000)")
            print(f"[OTPM] n=5 burst (60s inter-run-sleep) 시 보호 여부: "
                  f"{'안전 (run 간 budget refresh)' if lat < 60 else 'WARN — run 단독이 60s 초과'}")

    _model_tag = args.model.replace("-", "").replace(".", "").replace("_", "")
    out_path = Path("logs") / f"anthropic_tokens_{_model_tag}_{int(time.time())}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
