from __future__ import annotations
import os,sys
from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage, HumanMessage, SystemMessage

import logging
logger = logging.getLogger(__name__)

from core.config import DOC_MODE
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task
from utils.sanitize import sanitize_state
from utils.rag_utils import refs_preview_text
from utils.refs import attach_auto_citations
from prompts import get_section_writer_prompt
from core.paths import read_outline
from content_utils import save_md_draft 
from utils.outline import get_topic_outline_text, next_unwritten_title
from utils.tasks import get_last_write_target, has_pending
from utils.text_utils import section_slugify

from core.llm import get_llm

import re
import os

def _truthy_env(name: str) -> bool:
    """'1/true/yes/on' → True 로 처리하는 간단한 헬퍼"""
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")
ECHO_SECTIONS = _truthy_env("ECHO_SECTIONS")

def section_writer(state: State):
    llm = get_llm()

    if DOC_MODE != "report":
        logger.info("[SECTION WRITER] Skipped: DOC_MODE=%s (expected 'report')", DOC_MODE)
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}

    logger.info("============ SECTION WRITER ============")
    state = sanitize_state(state)
    tasks = state.get("task_history", []) or []
    messages = state.get("messages", []) or []

    pending = next(
        (t for t in reversed(tasks) if (not getattr(t, "done", False)) and getattr(t, "agent", "") == "section_writer"),
        None
    )

    outline_text = get_topic_outline_text(state)
    if not (outline_text or "").strip():
        fname = state.get("outline_fname") or "outline_report.md"
        if not has_pending(tasks, "content_strategist", prefix="create_outline"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(content=f"[Section Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
            if not pending.description:
                pending.description = "write: (no-outline)"
        logger.info("[SECTION WRITER] outline missing → scheduled content_strategist (%s)", fname)
        return {"messages": messages, "task_history": tasks}

    target_title = (
        get_last_write_target(messages, tasks)
        or next_unwritten_title(outline_text, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug"))
    )
    if not target_title:
        messages.append(AIMessage(content="[Section Writer] 모든 섹션 초안이 이미 작성되었습니다."))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
            if not pending.description:
                pending.description = "write: (all-done)"
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="모든 섹션이 작성됨: 진행상황 보고", done_at=""))
        logger.info("[SECTION WRITER] nothing left to write → handoff to communicator")
        return {"messages": messages, "task_history": tasks}

    logger.info("[SECTION WRITER] target section: %s", target_title)

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
    logger.debug("[SECTION WRITER] draft length=%s chars", len(gathered or ""))

    if os.getenv("AUTO_FOOTNOTE", "1") == "1":
        try:
            gathered = attach_auto_citations(gathered, state)
        except Exception as e:
            logger.warning("[SECTION WRITER] auto-citation 실패: %s", e)

    # 저장 시도 (save_md_draft 우선, 실패 시 폴백)
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
        logger.info("[SECTION WRITER] saved via save_md_draft → %s", out_path)
    except Exception as e:
        makedirs(out_dir, exist_ok=True)
        # 공용 유틸 슬러그 사용
        fname = f"{section_slugify(target_title)}.md"
        out_path = path.join(out_dir, fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(gathered)
        logger.warning("[SECTION WRITER fallback] saved → %s  (reason: %s)", out_path, e)

    state["last_saved_path"] = out_path
    messages.append(AIMessage(content=f"[SECTION WRITER] '{target_title}' 초안 저장 완료 → {out_path}"))


    # (NEW) 콘솔 에코: 저장된 섹션 초안 원문을 바로 출력 (옵션)
    #  - app.py 의 --echo-sections 플래그가 ECHO_SECTIONS=1 로 설정
    #  - JSON 로깅과 무관하게 사람이 읽기 쉽게 stdout 직출
    if ECHO_SECTIONS:
        try:
            box_title = f"SECTION DRAFT: {target_title}"
            src_tag   = f"saved → {out_path}"
            hdr_line  = "=" * max(len(box_title), len(src_tag), 24)
            sys.stdout.write("\n" + hdr_line + "\n")
            sys.stdout.write(box_title + "\n")
            sys.stdout.write(src_tag + "\n")
            sys.stdout.write(hdr_line + "\n\n")
            sys.stdout.write((gathered or "").rstrip() + "\n")
            sys.stdout.write(hdr_line + "\n")
            sys.stdout.flush()
        except Exception as _e:
            logger.debug("[SECTION WRITER] echo failed: %s", _e)

    # ---- 태스크 완료/후속 예약 ----
    if pending:
        pending.done = True
        pending.done_at = _now_str()
        if not pending.description:
            pending.description = f"write: {target_title}"

    if not has_pending(tasks, "communicator"):
        tasks.append(
            Task(
                agent="communicator",
                done=False,
                description=f"'{target_title}' 초안 완료 보고 및 다음 섹션/수정 범위 확인",
                done_at=""
            )
        )

    return {"messages": messages, "task_history": tasks, "last_saved_path": out_path}
