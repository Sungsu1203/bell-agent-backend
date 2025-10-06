from __future__ import annotations
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers.string import StrOutputParser
from core.config import DOC_MODE
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task, AgentName
from utils.sanitize import sanitize_state
from utils.rag_utils import refs_preview_text
from utils.refs import attach_auto_citations, refs_preview_text as _refs_preview_text, facts_block as _facts_block
from prompts import get_chapter_writer_prompt
from content_utils import read_outline, save_md_draft, next_unwritten_title
from rag_expression import is_outline_creation, extract_write_title
from utils.tasks import has_pending, get_last_write_target
from utils.outline import get_topic_outline_text
import os

from core.llm import get_llm
llm=get_llm()

def chapter_writer(state: State):
    if DOC_MODE != "book":
        print(f"[CHAPTER WRITER] Skipped: DOC_MODE={DOC_MODE} (expected 'book').")
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}
    print("\n\n============ CHAPTER WRITER ============")
    state = sanitize_state(state)
    # state = sanitize_numeric_state(state)

    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "chapter_writer"), None)
    if pending is None:
        print("[WARN] pending 'chapter_writer' task가 없습니다. edge pass.")
        # section_writer와 동일: 경고만 띄우고 계속 진행

    messages = state.get("messages", [])
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and is_outline_creation(last_human.content):
        now = _now_str()
        if pending:
            pending.done = True
            pending.done_at = now
        tasks.append(Task(agent="content_strategist", done=False, description="create_outline:auto", done_at=""))
        messages.append(AIMessage("[Chapter Writer] Outline 요청 감지 → content_strategist로 위임"))
        return {"messages": messages, "task_history": tasks}

    outline_text = get_topic_outline_text(state)
    if not outline_text.strip():
        fname = state.get("outline_fname") or "outline.md"
        if not has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(f"[Chapter Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        return {"messages": messages, "task_history": tasks}

    target_title = get_last_write_target(messages, tasks) or next_unwritten_title(
        outline_text, mode="book", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    if not target_title:
        messages.append(AIMessage("[Chapter Writer] 모든 목차 항목의 초안이 이미 작성되었습니다."))
        now = _now_str()
        if pending:
            pending.done = True
            pending.done_at = now
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="집필 완료 보고 및 편집 여부 확인", done_at=""))
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target chapter: {target_title}")
    ref_text = _refs_preview_text(state) + _facts_block(state)
    
    chapter_writer_prompt = get_chapter_writer_prompt()
    writer_chain = chapter_writer_prompt | llm | StrOutputParser()
    gathered = ""
    for chunk in writer_chain.stream(
        {
            "target_title": target_title,
            "outline": outline_text,
            "references": ref_text,
            "messages": messages,
            "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
        }
    ):
        print(chunk, end="")
        gathered += chunk
    print()

    if os.getenv("AUTO_FOOTNOTE", "1") == "1":
        try:
            gathered = attach_auto_citations(gathered, state)
        except Exception as e:
            print(f"[WARN] auto-citation 실패: {e}")

    out_path = save_md_draft(
        target_title, gathered, mode="book", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    state["last_saved_path"] = out_path
    messages.append(AIMessage(f"[Chapter Writer] '{target_title}' 초안 작성 완료 → {out_path}"))

    if pending:
        pending.done = True
        pending.done_at = _now_str()

    if not has_pending(tasks, "communicator"):
        tasks.append(
            Task(agent="communicator", done=False, description=f"'{target_title}' 초안 완료 보고 및 다음 집필/수정 확인", done_at="")
        )

    return {"messages": messages, "task_history": tasks}
