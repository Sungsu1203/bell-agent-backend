from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from typing import Any, cast

import core.config as config
from utils.outline import next_unwritten_title
from core.paths import outline_base_dir


from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage

from core.paths import current_path, now_str as _now_str
from core.models import Task, AgentName
from core.config import DocMode
from utils.sanitize import sanitize_state
from core.state_types import State
from core.events import emit_event
from prompts import get_content_strategist_prompt
from utils.outline import read_outline, save_outline
from utils.outline import normalize_outline_headings as _normalize_outline_headings
from utils.tasks import has_pending
from utils.outline import get_topic_outline_text

from core.llm import get_llm
import re


def content_strategist(state: State):
    logger.info("============ CONTENT STRATEGIST ============")
    emit_event("목차 구성")
    llm = get_llm()
    state = cast(State, sanitize_state(state))

    # 공통 준비
    messages = list(state.get("messages") or [])
    tasks = list(state.get("task_history") or [])

    # outline 파일명 결정 및 상태 반영 (런타임 CFG → DocMode 강제)
    def _coerce_doc_mode(x: object) -> DocMode:
        try:
            s = str(x).strip().lower()
        except Exception:
            s = "report"
        # Literal["book","report"]로 안전 캐스팅
        return cast(DocMode, ("book" if s == "book" else "report"))

    MODE: DocMode = _coerce_doc_mode(getattr(config.CFG, "DOC_MODE", "report"))
    fname = state.get("outline_fname") or ("outline_book.md" if MODE == "book" else "outline_report.md")
    state["outline_fname"] = fname

    # AgentName 캐스팅 헬퍼 (Task 생성 시 타입 안전)
    def _agent(name: str) -> AgentName:
        # Python에서는 typing.cast로 처리해야 합니다.
        return cast(AgentName, name)


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
            root_dir=str(current_path() if callable(current_path) else current_path),
            topic_slug=state.get("topic_slug"),
            mode=MODE,
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
            root_dir=str(current_path() if callable(current_path) else current_path),
            topic_slug=state.get("topic_slug"),
            mode=MODE,
            backup=True,
        )

        # [ADD] 아웃라인 저장 직후 자동 집필 연결용 타이틀 플래그 설정
        try:
            auto_title = (next_unwritten_title(
                updated or "",
                mode=("book" if MODE == "book" else "report"),
                root_dir=str(outline_base_dir()),
                topic_slug=state.get("topic_slug"),
            ) or "").strip()
            if auto_title:
                flags = dict(state.get("flags") or {})
                flags["requested_write_title"] = auto_title
                state["flags"] = flags
                logger.info("[Content Strategist] requested_write_title set → %s", auto_title)
        except Exception as e:
            logger.debug("[Content Strategist] set requested_write_title skipped: %s", e)


        messages.append(AIMessage(
            content=f"[Content Strategist] {idx}장 제목을 '{new_title}'로 변경했습니다. 저장 위치: {out_path}"))
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
            tasks.append(Task(agent=_agent("communicator"), done=False, description=f"show_outline:{fname}", done_at=""))

        return {"messages": messages, "task_history": tasks}
    
    # ─────────────────────────────────────────────────────────
    # objectives 추출 (state 우선 → env fallback)
    def _format_objectives(st: State) -> str:
        objs: list = list(st.get("research_objectives") or [])
        if not objs:
            try:
                objs = config.load_research_objectives_from_env()
            except Exception:
                objs = []
        if not objs:
            return "(리서치 목표 없음 — topic_title 기반으로 자유롭게 설계)"
        return "\n".join(f"{i+1}. {o}" for i, o in enumerate(objs))

    # ─────────────────────────────────────────────────────────
    # 일반 경로: 목차 생성 (LLM 호출)
    # [§research-1 R41] 리서치 리포트 프롬프트 트랙 — 프리셋 키로 갈린다.
    #   기존 report/book 문안은 무접촉이다. 이 키가 없거나 0 이면 종전 그대로 돈다.
    #   분기를 prompts.py 안이 아니라 여기서 하는 이유 — prompts.py:18-31 _get_cfg_attr 은
    #   ENV 폴백이 없어 프리셋 전용 키가 보이지 않는다(R41 Phase 0 §2-c 실측).
    #   config.truthy 는 CFG → ENV 순으로 보므로 CFG 필드 없이 프리셋 키만으로 성립한다.
    if config.truthy("RESEARCH1_PROMPT_TRACK", False):
        from prompts_research import get_research_outline_prompt as _r41_outline_prompt
        strategist_prompt = _r41_outline_prompt()
        logger.info("[Content Strategist] research prompt track ON (RESEARCH1_PROMPT_TRACK=1)")
    else:
        strategist_prompt = get_content_strategist_prompt(MODE)
    chain = strategist_prompt | llm | StrOutputParser()

    outline_text = get_topic_outline_text(state)
    # refs / references 키 모두를 지원 (호환)
    _refs = (state.get("refs")
             or state.get("references")
             or {"queries": [], "docs": []})
    gathered = ""
    logger.info("[Content Strategist] outline generation started (fname=%s, mode=%s)", fname, MODE)
    
    objectives_text = _format_objectives(state)
    logger.info("[Content Strategist] objectives %d개 주입",
                len(state.get("research_objectives") or []))

    for chunk in chain.stream(
        {
            "messages": messages,
            "outline": outline_text,
            "references": _refs,
            "topic_title": state.get("topic_title") or "",
            "objectives": objectives_text,
        }
    ):
        # 화면 실시간 출력 대신 버퍼에만 모으고, 필요 시 디버그로 일부만 남깁니다.
        try:
            gathered += str(chunk)
        except Exception:  # 방어적: chunk가 객체일 경우
            gathered += getattr(chunk, "content", "") or ""
    logger.debug("[Content Strategist] streamed outline length=%s chars", len(gathered))

    # H2 헤딩 정규화
    gathered = _normalize_outline_headings(gathered)

    # 저장
    out_path = save_outline(
        gathered,
        filename=fname,
        root_dir=str(current_path() if callable(current_path) else current_path),
        topic_slug=state.get("topic_slug"),
        mode=MODE,
        backup=True,
    )
    messages.append(AIMessage(
        content=f"[Content Strategist] 목차 작성이 완료되었습니다. 저장 위치: {out_path}"
    ))
    logger.info("[Content Strategist] outline saved → %s", out_path)

    # [ADD] 아웃라인 저장 직후 자동 집필 연결용 타이틀 플래그 설정
    try:
        auto_title = (next_unwritten_title(
            gathered or "",
            mode=("book" if MODE == "book" else "report"),
            root_dir=str(outline_base_dir()),
            topic_slug=state.get("topic_slug"),
        ) or "").strip()
        if auto_title:
            flags = dict(state.get("flags") or {})
            flags["requested_write_title"] = auto_title
            state["flags"] = flags
            logger.info("[Content Strategist] requested_write_title set → %s", auto_title)
    except Exception as e:
        logger.debug("[Content Strategist] set requested_write_title skipped: %s", e)


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
        tasks.append(Task(agent=_agent("communicator"), done=False, description=f"show_outline:{fname}", done_at=""))

    return {"messages": messages, "task_history": tasks}
