from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from core.state_types import State
from core.config import DOC_MODE
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

def build_graph():
    g = StateGraph(State)
    g.add_node("supervisor", supervisor)
    g.add_node("communicator", communicator)
    g.add_node("content_strategist", content_strategist)
    g.add_node("vector_search_agent", vector_search_agent)
    g.add_node("web_search_agent", web_search_agent)
    g.add_node("chapter_writer", chapter_writer)
    g.add_node("section_writer", section_writer)
    g.add_node("research_planner", research_planner)
    g.add_node("research_synthesizer", research_synthesizer)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", supervisor_router, {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "vector_search_agent": "vector_search_agent",
        "web_search_agent": "web_search_agent",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "research_planner": "research_planner",
    })
    g.add_edge("content_strategist", "communicator")
    g.add_conditional_edges("research_planner", after_planner_router, {
        "communicator": "communicator", "web_search_agent": "web_search_agent"
    })
    g.add_edge("web_search_agent", "vector_search_agent")
    g.add_conditional_edges("vector_search_agent", after_vector_router, {
        "research_synthesizer": "research_synthesizer",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",
    })
    g.add_conditional_edges("research_synthesizer", after_synthesizer_router, {
        "research_planner": "research_planner",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",
    })
    g.add_conditional_edges("chapter_writer", tail_task_router, {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
    })
    g.add_conditional_edges("section_writer", tail_task_router, {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
    })
    g.add_edge("communicator", END)
    return g.compile()
