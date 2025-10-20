from __future__ import annotations
from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage

import logging
logger = logging.getLogger(__name__)

# ❌ 전역 DOC_MODE 상수 의존 제거
# from core.config import DOC_MODE
from core.config import DocMode  # 타입만 사용

from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task
from utils.sanitize import sanitize_state
from prompts import get_content_strategist_prompt
from utils.outline import read_outline, save_outline
from utils.outline import normalize_outline_headings as _normalize_outline_headings
from utils.tasks import has_pending
from utils.outline import get_topic_outline_text

from core.llm import get_llm
import re
from typing import cast as _cast


def _env_doc_mode(default: DocMode = _cast(DocMode, "report")) -> DocMode:
    """ENV에서 DOC_MODE를 읽어 DocMode로 안전 변환."""
    raw = (os.getenv("DOC_MODE") or "").strip().lower()
    return _cast(DocMode, raw if raw in ("report", "book") else default)


import os


def content_strategist(state: State):
    logger.info("============ CONTENT STRATEGIST ============")
    llm = get_llm()
    state = sanitize_state(state)

    MODE: DocMode = _env_doc_mode()  # ✅ 현재 실행 시점의 모드 해석

    # 공통 준비
    messages = list(state.get("messages") or [])
    tasks = list(state.get("task_history") or [])

    # outline 파일명 결정 및 상태 반영(모드별 기본 파일명)
    fname_default = "outline_book.md" if MODE == _cast(DocMode, "book") else "outline_report.md"
    fname = state.get("outline_fname") or fname_default
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
            mode=MODE,  # ✅ 동적 모드
        )
        if not raw:
            raw = get_topic_outline_text(state) or ""

        # read_outline가 (text, path) 튜플을 줄 수 있으므로 문자열만 뽑아낸다
        current_outline: str = raw[0] if isinstance(raw, tuple) else str(raw)

        # 안전한 패턴 컴파일 (멀티라인): "## {idx}. 기존제목" → "## {idx}. new_title"
        idx_escaped = re.escape(idx)
        pattern = re.compile(rf'^(##\s*{idx_escaped}\.\s*)(.+)$', flags=re.M)

        def _repl(mm: re.Match[str]) -> str:
            return f"{mm.group(1)}{new_title}"

        updated: str = pattern.sub(_repl, current_outline)

        out_path = save_outline(
            updated,
            filename=fname,
            root_dir=current_path,
            topic_slug=state.get("topic_slug"),
            mode=MODE,   # ✅ 동적 모드
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
    strategist_prompt = get_content_strategist_prompt(MODE)  # ✅ 모드 전달
    chain = strategist_prompt | llm | StrOutputParser()

    outline_text = get_topic_outline_text(state)
    gathered = ""
    logger.info("[Content Strategist] outline generation started (fname=%s, mode=%s)", fname, MODE)
    for chunk in chain.stream(
        {
            "messages": messages,
            "outline": outline_text,
            "references": state.get("references", {"queries": [], "docs": []}),
            "topic_title": state.get("topic_title") or "",
        }
    ):
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
        mode=MODE,   # ✅ 동적 모드
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

