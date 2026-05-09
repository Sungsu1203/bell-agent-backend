# agent/export/planner.py
from __future__ import annotations
import logging
import re
import time

from prompts import get_pptx_planner_prompt
from core.llm import get_llm
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

    # §13-9 (2026-05-09): temperature 0.1 적용 — 출력 안정성 우선.
    # get_llm() 은 싱글턴이라 인자로 temperature 넘겨도 첫 호출 후 무시됨 → bind 로 호출별 override.
    # bind 는 invoke 시점에 temperature 파라미터를 chat completion API 로 전달 (싱글턴 미오염).
    llm = get_llm()
    llm_planner = llm.bind(temperature=0.1)
    structured = llm_planner.with_structured_output(SlideDeckSpec)
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
        result = chain.invoke({
            "topic_title": topic_title,
            "slug": slug,
            "md_text": md_text,
            "n_h2_chapters": n_h2,
            "n_h3_sections": n_h3,
            "n_total_slides": n_total_slides,
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
        "[pptx.planner] OK slides=%d (target=%d, h2=%d h3=%d) slug=%r model=%r latency=%.2fs",
        len(result.slides), n_total_slides, n_h2, n_h3, slug, model, lat_ok,
    )
    return result


__all__ = ["plan_deck"]
