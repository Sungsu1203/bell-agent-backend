from __future__ import annotations
from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage

import logging
logger = logging.getLogger(__name__)

from core.config import DOC_MODE
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task, AgentName
from utils.sanitize import sanitize_state
from prompts import get_content_strategist_prompt
from utils.outline import read_outline, save_outline
from utils.rag_utils import refs_preview_text
from utils.outline import normalize_outline_headings as _normalize_outline_headings
from utils.tasks import has_pending
from utils.outline import get_topic_outline_text

from typing import Pattern, Match  # ✅ 타입 힌트 (Pylance 경고 방지)
from core.llm import get_llm
import re


def content_strategist(state: State):
    logger.info("============ CONTENT STRATEGIST ============")
    llm = get_llm()
    state = sanitize_state(state)

    # 공통 준비
    messages = list(state.get("messages") or [])
    tasks = list(state.get("task_history") or [])

    # outline 파일명 결정 및 상태 반영
    fname = state.get("outline_fname") or ("outline_book.md" if DOC_MODE == "book" else "outline_report.md")
    state["outline_fname"] = fname

    # ─────────────────────────────────────────────────────────
    # FAST-PATH: 장 제목 리네임 (LLM 건너뛰고 즉시 수정/저장)
    desc = next(
        (t.description for t in reversed(tasks)
         if (not getattr(t, "done", False)) and getattr(t, "agent", "") == "content_strategist"),
        ""
    ) or ""
    m = re.match(r"^rename_heading:(\d+):(.+?)(?::(.+))?$", desc)
    if m:
        idx = m.group(1)                 # 문자열 형태의 번호
        new_title = (m.group(2) or "").strip()
        fname_override = (m.group(3) or "").strip()

        if fname_override:
            fname = fname_override
            state["outline_fname"] = fname

        raw = read_outline(
            filename=fname,
            root_dir=current_path,
            topic_slug=state.get("topic_slug"),
            mode=DOC_MODE,
        )
        if not raw:
            raw = get_topic_outline_text(state) or ""

        # read_outline 가 (text, path) 튜플을 줄 수 있으므로 문자열만 뽑아낸다
        current_outline: str = raw[0] if isinstance(raw, tuple) else str(raw)

        # 안전한 패턴 컴파일 (멀티라인): "## {idx}. 기존제목" → "## {idx}. new_title"
        idx_escaped = re.escape(idx)
        pattern: re.Pattern[str] = re.compile(rf'^(##\s*{idx_escaped}\.\s*)(.+)$', flags=re.M)

        def _repl(m: re.Match[str]) -> str:
            return f"{m.group(1)}{new_title}"

        updated: str = pattern.sub(_repl, current_outline)

        out_path = save_outline(
            updated,
            filename=fname,
            root_dir=current_path,
            topic_slug=state.get("topic_slug"),
            mode=DOC_MODE,
            backup=True,
        )

        messages.append(AIMessage(content=f"[Content Strategist] {idx}장 제목을 '{new_title}'로 변경 → {out_path}"))
        logger.info("[Content Strategist] heading %s renamed → %s", idx, out_path)

        # 해당 content_strategist 펜딩 완료 처리
        for t in reversed(tasks):
            if (not getattr(t, "done", False)) and getattr(t, "agent", "") == "content_strategist":
                t.done = True
                t.done_at = _now_str()
                break

        # communicator 알림 중복 방지 후 예약
        try:
            already = has_pending(tasks, "communicator")
        except Exception:
            already = any((not getattr(t, "done", False)) and getattr(t, "agent", "") == "communicator" for t in tasks)
        if not already:
            tasks.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))

        return {"messages": messages, "task_history": tasks}

    # ─────────────────────────────────────────────────────────
    # 일반 경로: 목차 생성 (LLM 호출)
    strategist_prompt = get_content_strategist_prompt(DOC_MODE)
    chain = strategist_prompt | llm | StrOutputParser()

    outline_text = get_topic_outline_text(state)
    gathered = ""
    logger.info("[Content Strategist] outline generation started (fname=%s, mode=%s)", fname, DOC_MODE)
    for chunk in chain.stream(
        {
            "messages": messages,
            "outline": outline_text,
            "references": state.get("references", {"queries": [], "docs": []}),
            "topic_title": state.get("topic_title") or "",
        }
    ):
        # 화면 실시간 출력 대신 버퍼에만 모으고, 필요 시 디버그로 일부만 남깁니다.
        gathered += chunk
    logger.debug("[Content Strategist] streamed outline length=%s chars", len(gathered))

    # H2 헤딩 정규화
    gathered = _normalize_outline_headings(gathered)

    # 저장
    out_path = save_outline(
        gathered,
        filename=fname,
        root_dir=current_path,
        topic_slug=state.get("topic_slug"),
        mode=DOC_MODE,
        backup=True,
    )
    messages.append(AIMessage(content=f"[Content Strategist] 목차 작성 완료 → {out_path}"))
    logger.info("[Content Strategist] outline saved → %s", out_path)

    # 가장 최근 미완료 content_strategist 펜딩 마킹
    pending = next(
        (t for t in reversed(tasks)
         if (not getattr(t, "done", False)) and getattr(t, "agent", "") == "content_strategist"),
        None
    )
    if pending is None:
        logger.warning("[WARN] pending 'content_strategist' task가 없습니다. edge pass.")
    else:
        pending.done = True
        pending.done_at = _now_str()

    # communicator 알림 예약(중복 방지)
    try:
        already = has_pending(tasks, "communicator")
    except Exception:
        already = any((not getattr(t, "done", False)) and getattr(t, "agent", "") == "communicator" for t in tasks)
    if not already:
        tasks.append(Task(agent="communicator", done=False, description=f"show_outline:{fname}", done_at=""))

    return {"messages": messages, "task_history": tasks}
