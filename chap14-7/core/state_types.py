from __future__ import annotations
from typing import List, Optional, NotRequired, Dict, Any, TypedDict, Required

import logging
logger = logging.getLogger(__name__)

class ResearchPlan(TypedDict, total=False):
    round: int
    objective: str
    queries: List[str]
    timestamp: str

class State(TypedDict, total=False):
    messages: Required[list[Any]]
    task_history: list
    references: dict
    # last_saved_path: str
    last_saved_path: NotRequired[str]
    topic_title: str
    topic_slug: str
    chroma_ns: str
    outline_fname: str
    outline_shown: bool
    agent_role: str
    iteration_count: int
    research_round: int
    research_objectives: List[str]
    findings_md: List[str]
    llm_logs: List[dict]
    new_url_count: int | None
    new_url_count_round: int | None
    round_new_urls: int | None
    round_added_urls: int | None
    qa_direct_reply: bool | None
    planner_queries: List[str] | None
    no_new_url_streak: int | None
    local_ingested_once: bool | None
    research_planner_announce: int | None
    research_halt_threshold: int | None
    research_min_rounds: int | None
    research_max_no_new_rounds: int | None
    research_loop_active: NotRequired[bool]
    facts_ctx: Optional[str]
    _vs_cleared_once: bool | None
    research_plan: ResearchPlan
    flags: NotRequired[Dict[str, Any]]
    writer_flags: NotRequired[dict[str, Any]]