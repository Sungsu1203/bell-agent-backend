# agent/export/planner.py
from __future__ import annotations
import logging
import re
import time

from prompts import get_pptx_planner_prompt
from core.llm import get_llm, reset_llm
from .spec import SlideDeckSpec

logger = logging.getLogger(__name__)

_H2_LINE_RE = re.compile(r"^##\s+\S", re.MULTILINE)
_H3_LINE_RE = re.compile(r"^###\s+\S", re.MULTILINE)


def _count_headings(md_text: str) -> tuple[int, int]:
    """입력 md 의 (## 챕터 수, ### 섹션 수) 산출.

    §13-9 Round 3 (2026-05-09): LLM 의 슬라이드 수 자유도를 제거하기 위해 사전 카운트 후
    prompt 변수로 주입. spread 비결정성의 본질 원인 (압축/분할 자율 판단) 차단.
    """
    n_h2 = len(_H2_LINE_RE.findall(md_text))
    n_h3 = len(_H3_LINE_RE.findall(md_text))
    return n_h2, n_h3

try:
    from tools.metrics import record_llm_call as _record_llm_call
except Exception:
    _record_llm_call = None  # type: ignore

import core.config as _config
import json as _json
from datetime import datetime as _dt
from pathlib import Path as _Path

# §13-8 (2026-05-10): usage_metadata 캡처용 모듈-global. 다음 invoke 호출까지 유지.
# measure_stability.py 가 plan_deck 호출 직후 _LAST_USAGE_METADATA 를 읽어 per-run 토큰 박제.
# include_raw=True 로 받은 raw response 의 usage_metadata 를 그대로 노출
# (input_tokens / output_tokens / total_tokens / input_token_details).
_LAST_USAGE_METADATA: dict | None = None


def _append_warmup_log(*, provider: str, model: str, latency_s: float,
                       success: bool, error_class: str, slug: str) -> None:
    """§13-7-3 (2026-05-09): warmup 호출 latency 별도 ndjson 보존.

    metrics.ndjson 오염 방지 + cold start 패턴 분석 자료. 기록 실패는 silent.
    """
    try:
        log_path = _Path("logs") / "warmup_log.ndjson"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": _dt.now().isoformat(timespec="seconds"),
            "provider": provider,
            "model": model,
            "slug": slug,
            "latency_s": round(latency_s, 2),
            "success": success,
            "error_class": error_class,
            "section_title": "pptx_plan_warmup",
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _cfg_str(name: str, default: str = "") -> str:
    try:
        v = getattr(_config.CFG, name, None)
        return str(v).strip() if v else default
    except Exception:
        return default


def plan_deck(
    md_text: str,
    *,
    slug: str,
    topic_title: str,
    model: str | None = None,
    _record_metrics: bool = True,
) -> SlideDeckSpec:
    """Markdown 보고서 → SlideDeckSpec (LLM structured output 1회 호출).

    결정론적 매핑 규칙은 get_pptx_planner_prompt() 의 프롬프트 안에 hardcode.
    LLM 호출 1회만 발생; renderer (§13-3) 는 LLM 호출 0.

    §13-7 (2026-05-09): model 인자 추가 — 명시 시 reset_llm() + get_llm(model=...) 으로
    새 LLM 인스턴스 강제 생성 (싱글턴 캐시 무시). gpt-4o vs gemini-2.5-pro vs gemini-2.5-flash
    비교 측정 시 사용. 미명시 시 기존 싱글턴 동작 (provider/model 은 .env overlay 기반).

    §13-7-3 (2026-05-09): _record_metrics flag — False 시 metrics.ndjson 미기록.
    측정 도구의 warmup 호출이 운영 metric 데이터를 오염시키지 않도록 차단.
    warmup latency 는 logs/warmup_log.ndjson 에 별도 보존 (cold start 분석용).
    """
    if not md_text or not md_text.strip():
        raise ValueError("md_text is empty")
    if not slug or not topic_title:
        raise ValueError("slug and topic_title are required")

    # §13-9 (2026-05-09): temperature 0.1 적용 — 출력 안정성 우선.
    # get_llm() 은 싱글턴이라 인자로 temperature 넘겨도 첫 호출 후 무시됨 → bind 로 호출별 override.
    # bind 는 invoke 시점에 temperature 파라미터를 chat completion API 로 전달 (싱글턴 미오염).
    if model:
        reset_llm()
        llm = get_llm(model=model)
    else:
        llm = get_llm()
    llm_planner = llm.bind(temperature=0.1)

    # §13-7 (2026-05-09): SlideSpec.layout_id 의 Literal[0,1,2] 를 int + validator 로 단순화 →
    # Vertex AI 의 function_calling schema 호환성 확보 (이전엔 protobuf marshal 단계에서 ParseError).
    # 모든 provider 동일 경로 (gpt-4o / gemini-pro / gemini-flash 무차별).
    # §13-8 (2026-05-10): include_raw=True — raw AIMessage 의 usage_metadata 캡처 목적.
    # parsed=SlideDeckSpec, raw=AIMessage(usage_metadata=...) 둘 다 회수. measure_stability
    # 가 _LAST_USAGE_METADATA 모듈-global 을 읽어 per-run 토큰 박제.
    structured = llm_planner.with_structured_output(SlideDeckSpec, include_raw=True)
    chain = get_pptx_planner_prompt() | structured

    # §13-9 Round 3 (2026-05-09): 슬라이드 수 결정성 — md 헤딩 사전 카운트 후 prompt 주입.
    n_h2, n_h3 = _count_headings(md_text)
    n_total_slides = 1 + n_h2 + n_h3  # TITLE 1 + SECTION_HEADER N_h2 + TITLE_CONTENT N_h3

    provider = (_cfg_str("LLM_PROVIDER", "") or "").lower()
    try:
        model = str(getattr(llm, "model_name", "") or getattr(llm, "model", "") or type(llm).__name__)
    except Exception:
        model = type(llm).__name__

    t0 = time.monotonic()
    try:
        _raw_res = chain.invoke({
            "topic_title": topic_title,
            "slug": slug,
            "md_text": md_text,
            "n_h2_chapters": n_h2,
            "n_h3_sections": n_h3,
            "n_total_slides": n_total_slides,
        })
        # §13-8 (2026-05-10): include_raw=True 로 받은 응답 형태 = {"raw": AIMessage,
        # "parsed": SlideDeckSpec, "parsing_error": Exception | None}.
        if isinstance(_raw_res, dict):
            result = _raw_res.get("parsed")
            _raw = _raw_res.get("raw")
            global _LAST_USAGE_METADATA
            try:
                _LAST_USAGE_METADATA = getattr(_raw, "usage_metadata", None) if _raw else None
            except Exception:
                _LAST_USAGE_METADATA = None
            if result is None:
                # parse 실패 → parsing_error 또는 raw 만 있는 케이스. 호환 위해 예외화.
                _err = _raw_res.get("parsing_error")
                if _err is not None:
                    raise _err
                raise RuntimeError("with_structured_output(include_raw=True) returned no parsed object")
        else:
            # 안전장치: 구버전 langchain 호환 (include_raw 미적용 시)
            result = _raw_res
            _LAST_USAGE_METADATA = None
    except Exception as err:
        lat_fail = time.monotonic() - t0
        if _record_metrics and _record_llm_call:
            try:
                _record_llm_call(
                    provider=provider, model=model, latency_s=lat_fail,
                    success=False, error_class=type(err).__name__,
                    section_title="pptx_plan",
                )
            except Exception:
                pass
        elif not _record_metrics:
            _append_warmup_log(provider=provider, model=model, latency_s=lat_fail,
                               success=False, error_class=type(err).__name__, slug=slug)
        raise

    lat_ok = time.monotonic() - t0
    if _record_metrics and _record_llm_call:
        try:
            hint = "slow" if lat_ok > 90.0 else ""
            _record_llm_call(
                provider=provider, model=model, latency_s=lat_ok,
                success=True, section_title="pptx_plan", retry_hint=hint,
            )
        except Exception:
            pass
    elif not _record_metrics:
        _append_warmup_log(provider=provider, model=model, latency_s=lat_ok,
                           success=True, error_class="", slug=slug)

    logger.info(
        "[pptx.planner] OK slides=%d (target=%d, h2=%d h3=%d) slug=%r model=%r latency=%.2fs",
        len(result.slides), n_total_slides, n_h2, n_h3, slug, model, lat_ok,
    )
    return result


__all__ = ["plan_deck"]
