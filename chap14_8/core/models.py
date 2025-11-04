# core/models.py
from __future__ import annotations
from typing import Literal, Iterable, Optional, Tuple, List, Set, Any
from pydantic import BaseModel, Field

import logging

# 동적 설정 접근
import core.config as config


# 프로젝트에서 쓰는 에이전트 이름을 Literal로 고정 (필요 시 여기에만 추가)
AgentName = Literal[
    "content_strategist",
    "communicator",
    "web_search_agent",
    "vector_search_agent",
    "chapter_writer",
    "section_writer",
    "research_planner",
    "research_synthesizer",
]

 
# 고정 가능한 에이전트 집합(런타임 검증 및 보조 유틸에 사용)
AGENT_NAMES: Tuple[AgentName, ...] = (
    "content_strategist",
    "communicator",
    "web_search_agent",
    "vector_search_agent",
    "chapter_writer",
    "section_writer",
    "research_planner",
    "research_synthesizer",
)

# ─────────────────────────────────────────────────────────────
# 동적 레지스트리: CFG로 에이전트 목록 확장/교체
#
# - CFG.AGENT_NAMES_OVERRIDE: 전체 목록을 교체(List[str] 또는 세미콜론 구분 문자열)
# - CFG.AGENT_NAMES_EXTRA: 기존 목록에 추가(List[str] 또는 세미콜론 구분 문자열)
# - CFG.AGENT_CASEFOLD: 비교 시 대소문 무시(True/False)
#
_AGENTS_CACHE: Optional[Tuple[Tuple[str, ...], bool]] = None  # (names, casefold)

def _as_list(v: Any) -> List[str]:
    if not v:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x).strip() for x in v if str(x).strip()]
    try:
        return [s.strip() for s in str(v).split(";") if s.strip()]
    except Exception:
        return []

def _casefold_enabled() -> bool:
    try:
        return bool(getattr(config.CFG, "AGENT_CASEFOLD", False))
    except Exception:
        return False

def get_agent_names() -> Tuple[str, ...]:
    """
    현재 CFG를 반영한 에이전트 이름 튜플을 반환.
    - override가 있으면 전면 교체, 없으면 기본 + extra 병합
    - reload_config() 후에는 refresh_agents()로 캐시 무효화 가능
    """
    global _AGENTS_CACHE
    cf = _casefold_enabled()
    if _AGENTS_CACHE and _AGENTS_CACHE[1] == cf:
        return _AGENTS_CACHE[0]

    base: List[str] = list(AGENT_NAMES)
    try:
        override = _as_list(getattr(config.CFG, "AGENT_NAMES_OVERRIDE", []))
        extra = _as_list(getattr(config.CFG, "AGENT_NAMES_EXTRA", []))
    except Exception:
        override, extra = [], []

    names: List[str] = override if override else [*base, *extra]

    # 중복 제거(대소문 옵션 반영)
    seen: Set[str] = set()
    uniq: List[str] = []
    for n in names:
        key = n.casefold() if cf else n
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(n)

    _AGENTS_CACHE = (tuple(uniq), cf)
    return _AGENTS_CACHE[0]

def refresh_agents() -> None:  # pragma: no cover
    """reload_config() 이후 호출하면 동적 에이전트 캐시가 즉시 갱신됩니다."""
    global _AGENTS_CACHE
    _AGENTS_CACHE = None

def is_valid_agent(name: str) -> bool:
    """주어진 문자열이 허용된 AgentName인지 검증(CFG.AGENT_CASEFOLD에 따라 대소문 무시)."""
    if not isinstance(name, str) or not name.strip():
        return False
    cf = _casefold_enabled()
    key = name.casefold() if cf else name
    pool = get_agent_names()
    if cf:
        return key in {p.casefold() for p in pool}
    return key in pool

def coerce_agent(name: Optional[str]) -> Optional[AgentName]:
    """
    문자열을 AgentName으로 강제 변환(정확 일치일 때만).
    - CFG 기본값 주입은 상위 계층(core.config.preferred_writer_agent 등)에서 처리하세요.
    """
    if not name or not isinstance(name, str):
        return None
    pool = get_agent_names()
    if _casefold_enabled():
        # 입력을 casefold 후 pool에서 동일 항목을 찾아 Canonical(원형)로 반환
        nf = name.casefold()
        for p in pool:
            if p.casefold() == nf:
                return p  # type: ignore[return-value]
        return None
    return name if name in pool else None  # type: ignore[return-value]


class Task(BaseModel):
    agent: AgentName = Field(
        ...,
        description=(
            "작업을 수행하는 agent의 종류.\n"
            "- content_strategist: 콘텐츠 전략/목차 작성·수정\n"
            "- communicator: 진행상황 보고 및 사용자 질의 응대\n"
            "- web_search_agent: 웹 검색으로 참고자료 수집\n"
            "- vector_search_agent: 벡터DB 검색(RAG)으로 참고자료 수집\n"
            "- chapter_writer: (책) 특정 챕터 본문 초안 작성\n"
            "- section_writer: (보고서) 특정 섹션 본문 초안 작성\n"
            "- research_planner: 리서치 라운드별 질의 설계/계획\n"
            "- research_synthesizer: 리서치 결과 요약/시사점 도출"
        ),
    )
    # LLM structured output 시 누락되더라도 파싱되게 기본값 제공
    done: bool = Field(False, description="종료 여부")
    description: str = Field("", description="해야 할 작업 설명(맥락/목표 포함 가능)")
    done_at: str = Field("", description="작업 완료 시각(예: '2025-03-06 14:32:10')")

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "done": self.done,
            "description": self.description,
            "done_at": self.done_at,
        }

__all__ = [
    "AgentName", "Task",
    # 정적 호환 상수
    "AGENT_NAMES",
    # 동적 레지스트리/헬퍼
    "get_agent_names", "refresh_agents",
    "is_valid_agent", "coerce_agent",
]
