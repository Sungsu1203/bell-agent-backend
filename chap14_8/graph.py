from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from langgraph.graph import StateGraph, START, END
from core.state_types import State

from typing import Mapping, Hashable, cast

# ─────────────────────────────────────────────────────────────
# Dynamic config (avoid static CFG/DOC_MODE binding)
# ─────────────────────────────────────────────────────────────
import core.config as config

def _get_cfg_attr(name: str, default):
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default

# Feature toggles (all default True → back-compat)
_EN_COMMUNICATOR = bool(_get_cfg_attr("ENABLE_COMMUNICATOR", True))
_EN_CONTENT_STRAT = bool(_get_cfg_attr("ENABLE_CONTENT_STRATEGIST", True))
_EN_VECTOR = bool(_get_cfg_attr("ENABLE_VECTOR_SEARCH", True))
_EN_WEB = bool(_get_cfg_attr("ENABLE_WEB_SEARCH", True))
_EN_CHAPTER = bool(_get_cfg_attr("ENABLE_CHAPTER_WRITER", True))
_EN_SECTION = bool(_get_cfg_attr("ENABLE_SECTION_WRITER", True))
_EN_PLANNER = bool(_get_cfg_attr("ENABLE_RESEARCH_PLANNER", True))
_EN_SYNTH = bool(_get_cfg_attr("ENABLE_RESEARCH_SYNTHESIZER", True))
_EN_SUPERVISOR = bool(_get_cfg_attr("ENABLE_SUPERVISOR", True))

# Routers & agents
from agent.supervisor import supervisor, supervisor_router
from agent.communicator import communicator
from agent.content_strategist import content_strategist
from agent.vector_search import vector_search_agent
from agent.web_search import web_search_agent
from agent.chapter_writer import chapter_writer
from agent.section_writer import section_writer
from agent.research_planner import research_planner
from agent.research_synthesizer import research_synthesizer

# ⬇️ routers.py와의 조응: after_* 라우터 + after_web 라우터 사용
from core.routers import (
    tail_task_router,
    after_web_search_agent,
    after_vector_router,
    after_planner_router,
    after_synthesizer_router,
)

def build_graph():
    g = StateGraph(State)
    nodes: dict[str, bool] = {}

    def _add_node(name: str, fn, enabled: bool):
        if enabled:
            g.add_node(name, fn)
            nodes[name] = True
        else:
            nodes[name] = False

    def _add_edge_safe(src: str, dst: str):
        if (src == START or nodes.get(src)) and (dst == END or nodes.get(dst)):
            g.add_edge(src, dst)
        else:
            logger.debug("edge skipped (disabled node): %s -> %s", src, dst)

    def _add_conditional_edges_safe(src: str, router, mapping: Mapping[str, str]) -> None:
        if not nodes.get(src):
            logger.debug("conditional edges skipped (src disabled): %s", src)
            return
        filt_dict: dict[Hashable, str] = {
            cast(Hashable, k): v
            for k, v in mapping.items()
            if nodes.get(v)
        }
        if not filt_dict:
            logger.debug("conditional edges skipped (no enabled dests) from %s", src)
            return
        g.add_conditional_edges(src, router, cast("dict[Hashable, str]", filt_dict))

    # Add nodes (respect toggles)
    _add_node("supervisor", supervisor, _EN_SUPERVISOR)
    _add_node("communicator", communicator, _EN_COMMUNICATOR)
    _add_node("content_strategist", content_strategist, _EN_CONTENT_STRAT)
    _add_node("vector_search_agent", vector_search_agent, _EN_VECTOR)
    _add_node("web_search_agent", web_search_agent, _EN_WEB)
    _add_node("chapter_writer", chapter_writer, _EN_CHAPTER)
    _add_node("section_writer", section_writer, _EN_SECTION)
    _add_node("research_planner", research_planner, _EN_PLANNER)
    _add_node("research_synthesizer", research_synthesizer, _EN_SYNTH)

    # START → supervisor (or fallback to communicator if supervisor disabled)
    start_target = "supervisor" if nodes.get("supervisor") else ("communicator" if nodes.get("communicator") else None)
    if start_target:
        _add_edge_safe(START, start_target)

    # supervisor routes to others
    _add_conditional_edges_safe("supervisor", supervisor_router, {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "vector_search_agent": "vector_search_agent",
        "web_search_agent": "web_search_agent",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "research_planner": "research_planner",
        "research_synthesizer": "research_synthesizer",
    })

    # fixed chains/routers (only if both ends enabled)
    _add_edge_safe("content_strategist", "communicator")

    # ✅ research_planner 이후: synthesizer 가능성 추가
    _add_conditional_edges_safe("research_planner", after_planner_router, {
        "communicator": "communicator",
        "web_search_agent": "web_search_agent",
        "vector_search_agent": "vector_search_agent",
        "section_writer": "section_writer",
        "chapter_writer": "chapter_writer",
        "research_synthesizer": "research_synthesizer",   # ← 추가 (중요)
    })

    # ✅ web_search_agent 이후: 고정 엣지 → 조건부 라우터로 교체
    _add_conditional_edges_safe("web_search_agent", after_web_search_agent, {
        "vector_search_agent": "vector_search_agent",
        "research_synthesizer": "research_synthesizer",
        "web_search_agent": "web_search_agent",            # 재시도
        "communicator": "communicator",
        "content_strategist": "content_strategist",
        "section_writer": "section_writer",
        "chapter_writer": "chapter_writer",
    })

    # ✅ vector_search_agent 이후: web_search_agent 가능성 추가
    _add_conditional_edges_safe("vector_search_agent", after_vector_router, {
        "research_synthesizer": "research_synthesizer",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",
        "web_search_agent": "web_search_agent",            # ← 추가
    })

    _add_conditional_edges_safe("research_synthesizer", after_synthesizer_router, {
        "research_planner": "research_planner",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",
    })

    # ✅ tail 라우터는 web_search_agent를 반환할 수 있음
    _add_conditional_edges_safe("chapter_writer", tail_task_router, {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "web_search_agent": "web_search_agent",            # ← 추가
    })
    _add_conditional_edges_safe("section_writer", tail_task_router, {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "web_search_agent": "web_search_agent",            # ← 추가
    })

    # terminal edge
    if nodes.get("communicator"):
        _add_edge_safe("communicator", END)
    else:
        if nodes.get("supervisor"):
            _add_edge_safe("supervisor", END)

    return g.compile()
