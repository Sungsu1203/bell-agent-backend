from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from langgraph.graph import StateGraph, START, END
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # 순환 임포트 방지: 타입체킹시에만 참조
    from core.config import Config

from core.state_types import State
from agent.supervisor import supervisor, supervisor_router
from agent.communicator import communicator
from agent.content_strategist import content_strategist
from agent.vector_search import vector_search_agent
from agent.web_search import web_search_agent
from agent.chapter_writer import chapter_writer
from agent.section_writer import section_writer
from agent.research_planner import research_planner
from agent.research_synthesizer import research_synthesizer
from core.routers import (
    tail_task_router, after_vector_router, after_planner_router, after_synthesizer_router
)

def build_graph(config: Optional["Config"] = None):
    """
    단일 'writer' 노드로 정규화한 LangGraph 구성.
    - config.doc_mode == 'book' 이면 chapter_writer를, 그 외에는 section_writer를 내부적으로 사용
    - 라우터가 반환하는 'chapter_writer' / 'section_writer' 분기는 모두 'writer' 노드로 매핑
    """
    g = StateGraph(State)

    # ── 노드 등록 ──────────────────────────────────────────────
    g.add_node("supervisor", supervisor)
    g.add_node("communicator", communicator)
    g.add_node("content_strategist", content_strategist)
    g.add_node("vector_search_agent", vector_search_agent)
    g.add_node("web_search_agent", web_search_agent)
    g.add_node("research_planner", research_planner)
    g.add_node("research_synthesizer", research_synthesizer)

    # 단일 writer 노드: config에 따라 내부 구현 결정
    _doc_mode = (getattr(config, "doc_mode", None) or "report").lower()
    writer_impl = chapter_writer if _doc_mode == "book" else section_writer
    g.add_node("writer", writer_impl)

    # ── 엣지/라우팅 ───────────────────────────────────────────
    g.add_edge(START, "supervisor")

    # supervisor 라우터 매핑: writer 단일화
    g.add_conditional_edges("supervisor", supervisor_router, {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "vector_search_agent": "vector_search_agent",
        "web_search_agent": "web_search_agent",
        "research_planner": "research_planner",
        "research_synthesizer": "research_synthesizer",
        # 라우터가 과거 라벨을 내보내더라도 모두 'writer'로 흡수
        "writer": "writer",
        "chapter_writer": "writer",
        "section_writer": "writer",
    })

    # content_strategist → communicator (기존 유지)
    g.add_edge("content_strategist", "communicator")

    # research_planner 라우터: writer 단일화
    g.add_conditional_edges("research_planner", after_planner_router, {
        "communicator": "communicator",
        "web_search_agent": "web_search_agent",
        "vector_search_agent": "vector_search_agent",  # SKIP_WEB_SEARCH=1이면 바로 우회
        "writer": "writer",
        "chapter_writer": "writer",
        "section_writer": "writer",
    })

    # web_search_agent → vector_search_agent (직결)
    g.add_edge("web_search_agent", "vector_search_agent")

    # vector_search_agent 라우터: writer 단일화
    g.add_conditional_edges("vector_search_agent", after_vector_router, {
        "research_synthesizer": "research_synthesizer",
        "writer": "writer",
        "chapter_writer": "writer",
        "section_writer": "writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",
    })

    # research_synthesizer 라우터: writer 단일화
    g.add_conditional_edges("research_synthesizer", after_synthesizer_router, {
        "research_planner": "research_planner",
        "writer": "writer",
        "chapter_writer": "writer",
        "section_writer": "writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",
    })

    # writer 테일 라우터: 자기지시(chapter/section)도 모두 writer로 환류
    g.add_conditional_edges("writer", tail_task_router, {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "writer": "writer",
        "chapter_writer": "writer",
        "section_writer": "writer",
    })

    # 종료
    g.add_edge("communicator", END)

    return g.compile()
