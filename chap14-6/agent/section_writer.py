from __future__ import annotations
import os
from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage, HumanMessage, SystemMessage

from core.config import DOC_MODE
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task
from utils.sanitize import sanitize_state
from utils.rag_utils import refs_preview_text
from utils.refs import attach_auto_citations
from prompts import get_section_writer_prompt
from content_utils import read_outline, save_md_draft, next_unwritten_title
from utils.outline import get_topic_outline_text
from utils.tasks import get_last_write_target, has_pending
from utils.text_utils import section_slugify

from core.llm import get_llm

import re
import os

def section_writer(state: State):
    llm = get_llm()

    if DOC_MODE != "report":
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}

    print("\n\n============ SECTION WRITER ============")
    state = sanitize_state(state)
    tasks = state.get("task_history", []) or []
    messages = state.get("messages", []) or []

    pending = next((t for t in reversed(tasks) if (not getattr(t, "done", False)) and getattr(t, "agent","")=="section_writer"), None)

    outline_text = get_topic_outline_text(state)
    if not (outline_text or "").strip():
        fname = state.get("outline_fname") or "outline_report.md"
        if not has_pending(tasks, "content_strategist", prefix="create_outline"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(f"[Section Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True; pending.done_at = _now_str()
            if not pending.description: pending.description = "write: (no-outline)"
        return {"messages": messages, "task_history": tasks}

    target_title = get_last_write_target(messages, tasks) or next_unwritten_title(
        outline_text, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    if not target_title:
        messages.append(AIMessage("[Section Writer] 모든 섹션 초안이 이미 작성되었습니다."))
        if pending:
            pending.done = True; pending.done_at = _now_str()
            if not pending.description: pending.description = "write: (all-done)"
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="모든 섹션이 작성됨: 진행상황 보고", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # ---- refs + FACTS(옵션) ----
    ref_text = refs_preview_text(state)
    facts = state.get("facts_ctx")
    if isinstance(facts, str) and facts.strip():
        ref_text += "\n\n[FACTS]\n" + facts

    chain = get_section_writer_prompt() | llm | StrOutputParser()
    gathered = chain.invoke({
        "target_title": target_title,
        "outline": outline_text,
        "references": ref_text,
        "messages": messages,
        "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
    })

    if os.getenv("AUTO_FOOTNOTE","1") == "1":
        try:
            gathered = attach_auto_citations(gathered, state)
        except Exception:
            pass

   # ... 저장 폴백 위치에서
    from os import path, makedirs

    slug = str(state.get("topic_slug") or "default")
    out_dir = path.join(current_path, "content", slug)

    try:
        out_path = save_md_draft(
            target_title, gathered, mode="report",
            root_dir=current_path, topic_slug=slug
        )
        if not out_path or not os.path.isfile(out_path):
            raise RuntimeError("save_md_draft returned empty or file not found")
        print(f"[SECTION WRITER] saved via save_md_draft → {out_path}")
    except Exception as e:
        makedirs(out_dir, exist_ok=True)
        # ✅ 여기서 로컬 _slugify 대신 공용 유틸 사용
        fname = f"{section_slugify(target_title)}.md"
        out_path = path.join(out_dir, fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(gathered)
        print(f"[SECTION WRITER fallback] saved → {out_path}  (reason: {e})")

    state["last_saved_path"] = out_path
    messages.append(AIMessage(f"[SECTION WRITER] '{target_title}' 초안 저장 완료 → {out_path}"))

    # ---- 태스크 완료/후속 예약 ----
    if pending:
        pending.done = True; pending.done_at = _now_str()
        if not pending.description: pending.description = f"write: {target_title}"

    if not has_pending(tasks, "communicator"):
        tasks.append(Task(agent="communicator", done=False,
                          description=f"'{target_title}' 초안 완료 보고 및 다음 섹션/수정 범위 확인", done_at=""))

    return {"messages": messages, "task_history": tasks, "last_saved_path": out_path,}