from __future__ import annotations
from typing import Any
import sys

from utils.tasks import HumanMessage, AIMessage
from langchain_core.output_parsers.string import StrOutputParser

import logging
logger = logging.getLogger(__name__)

from core.config import DOC_MODE
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task
from utils.sanitize import sanitize_state
from utils.refs import attach_auto_citations, refs_preview_text as _refs_preview_text, facts_block as _facts_block
from prompts import get_chapter_writer_prompt
from content_utils import save_md_draft
from utils.outline import next_unwritten_title
from rag_expression import is_outline_creation
from utils.tasks import has_pending, get_last_write_target
from utils.outline import get_topic_outline_text
import os

from core.llm import get_llm

def _truthy_env(name: str) -> bool:
    """'1/true/yes/on' → True 로 처리"""
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")

# 섹션/챕터 공용 에코 스위치 지원
ECHO_CHAPTERS = _truthy_env("ECHO_CHAPTERS") or _truthy_env("ECHO_SECTIONS")


def chapter_writer(state: State):
    """DOC_MODE == 'book'에서 챕터 초안을 생성한다.
    - 섹션 라이터와 동일한 타이틀 선택 규칙 사용(get_last_write_target → next_unwritten_title → '서문')
    - state['last_saved_path']만 갱신, 반환 딕셔너리엔 넣지 않음(※ 필요 시 유지)
    """
    if DOC_MODE != "book":
        logger.info("[CHAPTER WRITER] Skipped: DOC_MODE=%s (expected 'book')", DOC_MODE)
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}

    logger.info("============ CHAPTER WRITER ============")
    llm = get_llm()
    state = sanitize_state(state)

    # 안전 기본값
    tasks = list(state.get("task_history", []) or [])
    messages = list(state.get("messages", []) or [])

    # 펜딩 태스크 핸들(있으면)
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "chapter_writer"), None)
    if pending is None:
        logger.warning("[CHAPTER WRITER] pending 'chapter_writer' task가 없습니다. edge pass (계속 진행).")

    # 사용자의 최근 입력이 목차 생성 의도면 위임
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and isinstance(last_human.content, str) and is_outline_creation(last_human.content):
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        fname = state.get("outline_fname") or "outline.md"
        if not has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(content="[Chapter Writer] Outline 요청 감지 → content_strategist로 위임"))
        logger.info("[CHAPTER WRITER] outline creation intent detected → scheduled content_strategist (%s)", fname)
        return {"messages": messages, "task_history": tasks}

    # 아웃라인 필수
    outline_text = get_topic_outline_text(state)
    if not (outline_text or "").strip():
        fname = state.get("outline_fname") or "outline.md"
        if not has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(content=f"[Chapter Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        logger.info("[CHAPTER WRITER] outline missing → scheduled content_strategist (%s)", fname)
        return {"messages": messages, "task_history": tasks}

    # ✅ 섹션 라이터와 동일한 타이틀 결정 규칙
    requested = get_last_write_target(messages, tasks)
    auto_title = next_unwritten_title(
        outline_text, mode="book", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    target_title = requested or auto_title or "서문"

    if not target_title:
        messages.append(AIMessage(content="[Chapter Writer] 모든 목차 항목의 초안이 이미 작성되었습니다."))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="집필 완료 보고 및 편집 여부 확인", done_at=""))
        logger.info("[CHAPTER WRITER] nothing left to write → handoff to communicator")
        return {"messages": messages, "task_history": tasks}

    logger.info("[CHAPTER WRITER] target chapter: %s", target_title)

    # 참고 문맥
    ref_text = _refs_preview_text(state) + _facts_block(state)

    # 집필
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
        # 콘솔 출력 대신 버퍼에만 모음
        gathered += chunk
    logger.debug("[CHAPTER WRITER] streamed draft length=%s chars", len(gathered))

    # 자동 각주(옵션)
    if os.getenv("AUTO_FOOTNOTE", "1") == "1":
        try:
            gathered = attach_auto_citations(gathered, state)
        except Exception as e:
            logger.warning("[CHAPTER WRITER] auto-citation 실패: %s", e)

    # 저장 + 상태 기록(반환값엔 포함 X — 필요 시 유지)
    out_path = save_md_draft(
        target_title, gathered, mode="book", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    state["last_saved_path"] = out_path
    messages.append(AIMessage(content=f"[Chapter Writer] '{target_title}' 초안 작성 완료 → {out_path}"))
    logger.info("[CHAPTER WRITER] draft saved → %s", out_path)


    # (NEW) 콘솔 에코: 저장된 챕터 초안 원문을 바로 출력 (옵션)
    #  - app.py 의 --echo-sections 플래그가 ECHO_SECTIONS=1 로 설정되어 있으면 이것도 동작
    #  - 별도로 ECHO_CHAPTERS=1 을 주면 독립적으로도 동작
    if ECHO_CHAPTERS:
        try:
            box_title = f"CHAPTER DRAFT: {target_title}"
            src_tag   = f"saved → {out_path}"
            hdr_line  = "=" * max(len(box_title), len(src_tag), 24)
            sys.stdout.write("\n" + hdr_line + "\n")
            sys.stdout.write(box_title + "\n")
            sys.stdout.write(src_tag + "\n")
            sys.stdout.write(hdr_line + "\n\n")
            # LLM 출력 원문 그대로 에코 (후처리 없이)
            sys.stdout.write((gathered or "").rstrip() + "\n")
            sys.stdout.write(hdr_line + "\n")
            sys.stdout.flush()
        except Exception as _e:
            logger.debug("[CHAPTER WRITER] echo failed: %s", _e)

    # 펜딩 정리 + 후속 안내
    if pending:
        if not (pending.description or "").strip():
            pending.description = f"write: {target_title}"
        pending.done = True
        pending.done_at = _now_str()

    if not has_pending(tasks, "communicator"):
        tasks.append(
            Task(agent="communicator", done=False, description=f"'{target_title}' 초안 완료 보고 및 다음 집필/수정 확인", done_at="")
        )

    # ❌ last_saved_path 반환 포함 여부는 팀 컨벤션에 맞추세요.
    return {"messages": messages, "task_history": tasks, "last_saved_path": out_path}
