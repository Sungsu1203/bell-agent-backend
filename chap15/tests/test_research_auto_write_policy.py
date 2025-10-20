# tests/test_research_auto_write_policy.py
import os
import importlib
from typing import Any, Iterable, cast
from core.state_types import State
from core.models import Task
from langchain_core.messages import HumanMessage
from utils.tasks import has_pending

def _import_vector_search(monkeypatch):
    # transformers가 torch를 로드하지 않도록 차단
    monkeypatch.setenv("TRANSFORMERS_NO_TORCH", "1")
    monkeypatch.setenv("TRANSFORMERS_NO_TF", "1")
    monkeypatch.setenv("TRANSFORMERS_NO_FLAX", "1")
    # core.llm에 “가짜 LLM” 경로 사용 지시 (아래 2번 패치가 있어야 동작)
    monkeypatch.setenv("BLOCKAGI_TEST_FAKE_LLM", "1")
    return importlib.import_module("agent.vector_search")

def _mk_research_state() -> State:
    return {
        "messages": [HumanMessage("demo_data 내용 중 policy 관련 핵심만 정리해줘")],
        "task_history": [Task(
            agent="vector_search_agent", done=False,
            description="사용자 질의 기반 RAG 검색을 수행한다.", done_at=""
        )],
        "agent_role": "research analyst",
        "iteration_count": 2,
        "research_objectives": ["시장규모/동향 확인"],
        "topic_slug": "default",
    }

def _hp(tasks: list[Task], agent: str, prefix: str | None = None) -> bool:
    return has_pending(cast(Iterable[Any], tasks), agent, prefix=prefix)

def test_no_writer_when_auto_write_during_research_off(monkeypatch):
    monkeypatch.setenv("BLOCKAGI_AGENT_ROLE", "research analyst")
    monkeypatch.setenv("AUTO_WRITE_AFTER_RAG", "1")
    monkeypatch.setenv("AUTO_WRITE_DURING_RESEARCH", "0")
    monkeypatch.setenv("SKIP_WEB_SEARCH", "1")
    monkeypatch.setenv("LOCAL_RAG_GLOBS", "demo_data/*.txt|demo_data/*.md")
    monkeypatch.setenv("CLEAR_CHROMA_ON_START", "1")

    vsa = _import_vector_search(monkeypatch)
    state: State = _mk_research_state()
    out = vsa.vector_search_agent(state)
    tasks = out["task_history"]

    writer = os.getenv("WRITER_AGENT", "section_writer")
    assert not _hp(tasks, writer, prefix="write")

def test_writer_when_auto_write_during_research_on(monkeypatch):
    monkeypatch.setenv("BLOCKAGI_AGENT_ROLE", "research analyst")
    monkeypatch.setenv("AUTO_WRITE_AFTER_RAG", "1")
    monkeypatch.setenv("AUTO_WRITE_DURING_RESEARCH", "1")
    monkeypatch.setenv("SKIP_WEB_SEARCH", "1")
    monkeypatch.setenv("LOCAL_RAG_GLOBS", "demo_data/*.txt|demo_data/*.md")
    monkeypatch.setenv("CLEAR_CHROMA_ON_START", "1")

    vsa = _import_vector_search(monkeypatch)
    state: State = _mk_research_state()
    out = vsa.vector_search_agent(state)
    tasks = out["task_history"]

    writer = os.getenv("WRITER_AGENT", "section_writer")
    assert _hp(tasks, writer, prefix="write")
