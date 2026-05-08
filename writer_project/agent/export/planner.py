# agent/export/planner.py
from __future__ import annotations
import logging
import time

from prompts import get_pptx_planner_prompt
from core.llm import get_llm
from .spec import SlideDeckSpec

logger = logging.getLogger(__name__)

try:
    from tools.metrics import record_llm_call as _record_llm_call
except Exception:
    _record_llm_call = None  # type: ignore

import core.config as _config


def _cfg_str(name: str, default: str = "") -> str:
    try:
        v = getattr(_config.CFG, name, None)
        return str(v).strip() if v else default
    except Exception:
        return default


def plan_deck(md_text: str, *, slug: str, topic_title: str) -> SlideDeckSpec:
    """Markdown 보고서 → SlideDeckSpec (LLM structured output 1회 호출).

    결정론적 매핑 규칙은 get_pptx_planner_prompt() 의 프롬프트 안에 hardcode.
    LLM 호출 1회만 발생; renderer (§13-3) 는 LLM 호출 0.
    """
    if not md_text or not md_text.strip():
        raise ValueError("md_text is empty")
    if not slug or not topic_title:
        raise ValueError("slug and topic_title are required")

    llm = get_llm()
    structured = llm.with_structured_output(SlideDeckSpec)
    chain = get_pptx_planner_prompt() | structured

    provider = (_cfg_str("LLM_PROVIDER", "") or "").lower()
    try:
        model = str(getattr(llm, "model_name", "") or getattr(llm, "model", "") or type(llm).__name__)
    except Exception:
        model = type(llm).__name__

    t0 = time.monotonic()
    try:
        result = chain.invoke({
            "topic_title": topic_title,
            "slug": slug,
            "md_text": md_text,
        })
    except Exception as err:
        lat_fail = time.monotonic() - t0
        if _record_llm_call:
            try:
                _record_llm_call(
                    provider=provider, model=model, latency_s=lat_fail,
                    success=False, error_class=type(err).__name__,
                    section_title="pptx_plan",
                )
            except Exception:
                pass
        raise

    lat_ok = time.monotonic() - t0
    if _record_llm_call:
        try:
            hint = "slow" if lat_ok > 90.0 else ""
            _record_llm_call(
                provider=provider, model=model, latency_s=lat_ok,
                success=True, section_title="pptx_plan", retry_hint=hint,
            )
        except Exception:
            pass

    logger.info(
        "[pptx.planner] OK slides=%d slug=%r model=%r latency=%.2fs",
        len(result.slides), slug, model, lat_ok,
    )
    return result


__all__ = ["plan_deck"]
