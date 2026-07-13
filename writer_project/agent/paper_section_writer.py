# agent/paper_section_writer.py — §paper-writer-1 Step C-2
"""학술 paper IMRD section writer agent.

기존 agent/section_writer.py (보고서/Q&A) 와는 별 모듈로 분리. 본 모듈은 4
구성요소로 이루어진다:

1. write_paper_section(): 1 section LLM 호출 → 본문 markdown 반환
2. build_apa_references(): chunks → APA 7th formatted list
3. attach_references_footer(): 본문 끝에 ## References 헤더 + 번호 list 부착
4. paper_section_writer(): LangGraph entry point (minimal wrapper)

References footer 는 본 모듈에서 utils.citations.format_apa7() 로 구성한다.
본문 안 [[N]] marker 와 footer 번호는 references_chunks 의 enumerate index
(1-based) 로 매칭한다.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Mapping

from langchain_core.output_parsers.string import StrOutputParser

from core.llm import get_llm
from prompts import get_paper_section_writer_prompt
from utils.citations import format_apa7

logger = logging.getLogger(__name__)


def write_paper_section(
    topic: str,
    section_type: str,
    target_title: str,
    outline: str,
    references_chunks: list[dict],
    previous_sections: str = "",
) -> str:
    """1 section LLM 호출 → 본문 markdown 반환 ([[N]] marker 포함).

    Placeholder 7개를 채워 prompts.get_paper_section_writer_prompt() 를 invoke.
    References footer 는 호출부에서 attach_references_footer() 로 부착.
    """
    llm = get_llm()
    prompt = get_paper_section_writer_prompt()
    # references 요약: [N] title (venue, year) + abstract snippet (240자)
    refs_lines: list[str] = []
    for i, c in enumerate(references_chunks or [], 1):
        title = (c.get("title") or "(no title)").strip()
        venue = (c.get("venue") or "(no venue)").strip() or "(no venue)"
        year = c.get("year") if c.get("year") is not None else "n.d."
        abs_v = (c.get("abstract") or "").strip()
        snippet = (abs_v[:240] + "...") if len(abs_v) > 240 else abs_v
        line = f"[{i}] {title} ({venue}, {year})"
        if snippet:
            line += f"\n    abstract: {snippet}"
        refs_lines.append(line)
    refs_text = "\n".join(refs_lines)
    # catch 81: previous_sections 의 글로벌 [[N]] 마커 strip (leak 채널 절단).
    # writer 가 이전 섹션 글로벌 번호를 복사→재shift 하는 feedback loop 를 여기서
    # 끊는다. 프롬프트로 나가는 로컬 복사본만 정제 — previous_sections 원본 인자·
    # measure_paper 의 section_bodies·최종 paper_body 는 전부 불변. prose 는 유지돼
    # 논리연속성/중복회피/용어일관성 손상 0 (marker 는 이들 어디에도 불요).
    _stripped = re.sub(r"\[\[\d+\]\]", "", previous_sections or "")
    prev_text = re.sub(r"[ \t]{2,}", " ", _stripped).strip() or "(없음 — 첫 section)"

    # 재현성 측정 스캐폴드(조건부): WRITER_SEED 설정 시에만 temp=0 + seed 를 bind 해
    # 생성을 결정론화(측정 통제). 미설정 = 프로덕션 원래 동작(get_llm 기본 temp=0.3, bind
    # 없음) 그대로 — 프로덕션 불변. ctor 인자는 싱글턴 캐시에 먹혀 무시되므로 bind 로 호출별
    # override(planner.py:104 명문화). vertex/gemini 검증됨.
    _env_seed = os.environ.get("WRITER_SEED")
    if _env_seed is not None:
        llm_writer = llm.bind(temperature=0, seed=int(_env_seed))
        logger.info("[paper_section_writer] bind temperature=0 seed=%d section=%s", int(_env_seed), section_type)
    else:
        llm_writer = llm
    chain = prompt | llm_writer | StrOutputParser()
    body = chain.invoke({
        "topic_title": topic,
        "target_title": target_title,
        "section_type": section_type,
        "outline": outline,
        "previous_sections": prev_text,
        "references": refs_text,
        "messages": "",
    })
    logger.info("[paper_section_writer] %s done (len=%d)", section_type, len(body or ""))
    return body or ""


def build_apa_references(chunks: list[dict]) -> list[str]:
    """chunks → APA 7th formatted reference list (1-based index 와 동일 순서)."""
    lines: list[str] = []
    for c in chunks or []:
        line = format_apa7(
            authors=c.get("authors") or [],
            year=c.get("year"),
            title=c.get("title") or "",
            venue=c.get("venue"),
            doi=c.get("doi"),
        )
        lines.append(line)
    return lines


def attach_references_footer(body: str, apa_lines: list[str]) -> str:
    """본문 끝에 ## References footer 부착 (번호 list, [[N]] 매칭)."""
    if not apa_lines:
        return body or ""
    parts = [(body or "").rstrip(), "", "## References", ""]
    for i, line in enumerate(apa_lines, 1):
        parts.append(f"{i}. {line}")
    return "\n".join(parts) + "\n"


def paper_section_writer(state: Mapping[str, Any]) -> dict:
    """LangGraph entry point — state 의 7 key 를 받아 section_body 반환.

    References footer 부착은 호출부에서 build_apa_references + attach_references_footer 로 처리.
    """
    body = write_paper_section(
        topic=state.get("topic_title", "") or "",
        section_type=state.get("section_type", "Introduction") or "Introduction",
        target_title=state.get("target_title", "") or "",
        outline=state.get("outline", "") or "",
        references_chunks=list(state.get("references_chunks") or []),
        previous_sections=state.get("previous_sections", "") or "",
    )
    return {"section_body": body}
