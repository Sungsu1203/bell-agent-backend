from __future__ import annotations
from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.config import DOC_MODE
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task, AgentName
from utils.sanitize import sanitize_state
from utils.rag_utils import refs_preview_text
from utils.refs import attach_auto_citations
from prompts import get_section_writer_prompt
from content_utils import read_outline, save_md_draft, next_unwritten_title
from utils.outline import get_topic_outline_text
from utils.tasks import get_last_write_target
import os

from core.llm import get_llm
llm=get_llm()


def section_writer(state: State):
    if DOC_MODE != "report":
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}

    state = sanitize_state(state)
    tasks = state.get("task_history", [])
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "section_writer"), None)

    messages = state.get("messages", [])
    outline_text = get_topic_outline_text(state)
    if not outline_text.strip():
        fname = state.get("outline_fname") or "outline_report.md"
        if not any((not t.done) and t.agent=="content_strategist" for t in tasks):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(f"[Section Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True; pending.done_at = ...
        return {"messages": messages, "task_history": tasks}

    # 타깃 선택
    def get_last_write_target(messages, tasks):
        from rag_expression import extract_write_title
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                t = extract_write_title(getattr(m, "content", "") or "")
                if t: return t
        for t in reversed(tasks):
            title = extract_write_title(getattr(t, "description", "") or "")
            if title: return title
        return None

    target_title = get_last_write_target(messages, tasks) or next_unwritten_title(
        outline_text, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    if not target_title:
        messages.append(AIMessage("[Section Writer] 모든 섹션 초안이 이미 작성되었습니다."))
        if pending: pending.done = True; pending.done_at = ...
        # communicator 예약 등 원본 로직 유지
        return {"messages": messages, "task_history": tasks}

    ref_text = refs_preview_text(state) + (("\n\n[FACTS]\n"+(state.get("facts_ctx") or "")) if state.get("facts_ctx") else "")
    chain = get_section_writer_prompt() | llm | StrOutputParser()

    gathered = chain.invoke({
        "target_title": target_title,
        "outline": outline_text,
        "references": ref_text,
        "messages": messages,
        "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
    })

    if os.getenv("AUTO_FOOTNOTE","1") == "1":
        try: gathered = attach_auto_citations(gathered, state)
        except Exception: pass

    out_path = save_md_draft(target_title, gathered, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug"))
    messages.append(AIMessage(f"[Section Writer] '{target_title}' 초안 작성 완료 → {out_path}"))
    state["last_saved_path"] = out_path

    if pending: pending.done = True; pending.done_at = ...
    if not any((not t.done) and t.agent=="communicator" for t in tasks):
        tasks.append(Task(agent="communicator", done=False, description=f"'{target_title}' 초안 완료 보고 및 다음 섹션/수정 범위 확인", done_at=""))

    return {"messages": messages, "task_history": tasks}
