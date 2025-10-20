# tests/test_last_saved_path.py
import os, json
from typing import cast
from langchain_core.messages import HumanMessage
from graph import build_graph
from app import initial_state
from core.paths import current_path
from core.state_io import save_state
from core.state_types import State

def _invoke_state(g, st: State) -> State:
    out = g.invoke(st, config={"recursion_limit": 200})
    if not isinstance(out, dict):
        raise TypeError(f"graph.invoke returned {type(out)}")
    return cast(State, out)

def test_last_saved_path_is_set_and_persisted(monkeypatch):
    monkeypatch.setenv("CHROMA_NAMESPACE", "demo_test")
    monkeypatch.setenv("SKIP_WEB_SEARCH", "1")
    monkeypatch.setenv("LOCAL_RAG_GLOBS", "demo_data/*.txt|demo_data/*.md")
    monkeypatch.setenv("CLEAR_CHROMA_ON_START", "1")
    monkeypatch.setenv("DOC_MODE", "report")
    monkeypatch.setenv("AUTO_WRITE_AFTER_RAG", "1")
    monkeypatch.setenv("AUTO_WRITE_DURING_RESEARCH", "1")
    monkeypatch.setenv("BLOCKAGI_AGENT_ROLE", "")

    g = build_graph()
    state: State = initial_state(iteration_count=1)

    # 1턴: RAG
    state.setdefault("messages", []).append(HumanMessage("demo_data 내용 중 policy 관련 핵심만 정리해줘"))
    state = _invoke_state(g, state)
    assert not state.get("last_saved_path")

    # 2턴: writer 실행
    state["messages"].append(HumanMessage("계속"))
    state = _invoke_state(g, state)

    lsp = state.get("last_saved_path")
    assert lsp and os.path.exists(lsp)

    # 저장 스냅샷에도 들어가는지 확인
    save_state(current_path, state)
    snap_path = os.path.join(current_path, "state", "last_state.json")
    with open(snap_path, "r", encoding="utf-8") as f:
        snap = json.load(f)
    assert snap.get("last_saved_path") == lsp
