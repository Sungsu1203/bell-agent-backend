from __future__ import annotations
from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage

from core.config import DOC_MODE
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task, AgentName
from utils.sanitize import sanitize_state
from prompts import get_content_strategist_prompt
# from content_utils import read_outline, save_outline
from utils.outline import read_outline, save_outline
from utils.rag_utils import refs_preview_text
from utils.outline import normalize_outline_headings as _normalize_outline_headings
from utils.tasks import has_pending
from utils.outline import get_topic_outline_text

from core.llm import get_llm
llm=get_llm()

def content_strategist(state: State):
    print("\n\n============ CONTENT STRATEGIST ============")
    state = sanitize_state(state)
    # state = sanitize_numeric_state(state)

    strategist_prompt = get_content_strategist_prompt(DOC_MODE)
    chain = strategist_prompt | llm | StrOutputParser()

    messages = state.get("messages", [])
    outline_text = get_topic_outline_text(state)
    gathered = ""
    for chunk in chain.stream(
        {
            "messages": messages,
            "outline": outline_text,
            "references": state.get("references", {"queries": [], "docs": []}),
            "topic_title": state.get("topic_title") or "",
        }
    ):
        print(chunk, end="")
        gathered += chunk
    print()

    # ✅ 여기서 목차를 H2 헤딩으로 정규화
    gathered = _normalize_outline_headings(gathered)

    # 저장
    fname = state.get("outline_fname") or "outline.md"
    out_path = save_outline(
        gathered,
        filename=fname,
        root_dir=current_path,
        topic_slug=state.get("topic_slug"),
        mode=DOC_MODE,
        backup=True,
    )
    messages.append(AIMessage(f"[Content Strategist] 목차 작성 완료 → {out_path}"))

    tasks = state.get("task_history", [])
    if not tasks or tasks[-1].agent != "content_strategist":
        raise ValueError("Content Strategist가 아닌 agent가 목차 작성을 시도했습니다.")
    tasks[-1].done = True
    tasks[-1].done_at = _now_str()

    if not has_pending(tasks, "communicator"):
        tasks.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))

    return {"messages": messages, "task_history": tasks}
