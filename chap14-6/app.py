from __future__ import annotations
import os, argparse
from langchain_core.messages import SystemMessage, HumanMessage
from core.config import DOC_MODE
from core.paths import now_str as _now_str, current_path
from core.state_types import State
from core.state_io import save_state
from utils.sanitize import coerce_int
from graph import build_graph

def initial_state(iteration_count: int, agent_role: str | None = None) -> State:
    default_outline = "outline_report.md" if DOC_MODE == "report" else "outline.md"
    base: State = {
        "messages": [SystemMessage(
            f"너희 AI들은 사용자의 요구에 맞는 {('보고서' if DOC_MODE=='report' else '책')}을(를) 쓰는 작가팀이다. "
            f"사용자가 사용하는 언어로 대화하라. 현재시각은 {_now_str()}이다."
        )],
        "task_history": [],
        "references": {"queries": [], "docs": []},
        "agent_role": (agent_role or os.getenv("BLOCKAGI_AGENT_ROLE","").strip().lower()),
        "iteration_count": int(iteration_count),
        "research_objectives": [],
        "research_round": 0,
        "findings_md": [],
        "llm_logs": [],
        "new_url_count": None,
        "topic_slug": os.getenv("TOPIC_SLUG") or "default",
        "outline_fname": default_outline,
        "outline_shown": False,
        "facts_ctx": "",
        "research_plan": {"round": 0, "objective": "", "queries": [], "timestamp": _now_str()},
    }
    return base

def read_user_input() -> str:
    first = input("\nUser\t: ")
    s = first.strip()
    if s in ('```','"""'):
        fence = s; lines=[]
        while True:
            line = input()
            if line.strip() == fence: break
            lines.append(line)
        return "\n".join(lines).strip()
    buf = first
    while buf.endswith("\\"):
        buf = buf[:-1] + "\n" + input()
    return buf.strip()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration_count", type=str, default=os.getenv("ITERATION_COUNT", os.getenv("BLOCKAGI_ITERATION_COUNT", "3")))
    parser.add_argument("--agent_role", type=str, default=os.getenv("BLOCKAGI_AGENT_ROLE","").strip().lower())
    args = parser.parse_args()

    iter_count = coerce_int(args.iteration_count, default=3)
    state: State = initial_state(iteration_count=iter_count, agent_role=args.agent_role)
    graph = build_graph()

    while True:
        try:
            user_input = read_user_input()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!"); break
        if user_input.lower() in ["exit","quit","q"]:
            print("Goodbye!"); break

        state.setdefault("messages", []).append(HumanMessage(user_input))
        result = graph.invoke(state, config={"recursion_limit": 200})
        if not isinstance(result, dict):
            raise TypeError(f"graph.invoke returned unexpected type: {type(result).__name__}")
        state = result  # type: ignore
        print("\n------------------------------------ MESSAGE COUNT\t", len(state.get("messages", [])))
        print("TASKS tail =",
            [(getattr(t, "agent", None), getattr(t, "done", None), getattr(t, "description", None))
            for t in state.get("task_history", [])][-3:])
        
        print("DEBUG last_saved_path before save:", state.get("last_saved_path"))
        save_state(current_path, state)
