from __future__ import annotations
import re, os, sys, time
from typing import Any
from utils.tasks import HumanMessage, AIMessage
from core.config import DOC_MODE
from core.paths import now_str as _now_str, current_path
from core.state_types import State
from core.models import Task
from utils.sanitize import sanitize_state
from rag_expression import is_outline_display
from prompts import get_communicator_prompt
from core.paths import read_outline
from utils.tasks import has_pending
from utils.outline import get_topic_outline_text
from core.llm import get_llm
import logging
logger = logging.getLogger(__name__)

def communicator(state: State):
    def _truthy_env(name: str) -> bool:
        v = (os.getenv(name) or "").strip().lower()
        return v in ("1","true","yes","on")
    ECHO_OUTLINE = _truthy_env("ECHO_OUTLINE")

    logger.info("============ COMMUNICATOR ============")
    DASH_ON = (os.getenv("LOG_DASHBOARD", "1").strip().lower() in ("1","true","yes","on"))
    DASH_RATE = float(os.getenv("DASH_RATE_SEC", "6"))

    llm = get_llm()
    state = sanitize_state(state)

    # ── 초기화 ───────────────────────────────────────────────────────────
    messages = state.get("messages", []) or []
    tasks = state.get("task_history", []) or []
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)

   # [GUARD] write: 펜딩이 있으면 플래그와 무관하게 커뮤니케이터를 건너뜀
    if (
        has_pending(tasks, "section_writer", prefix="write:") or
        has_pending(tasks, "chapter_writer", prefix="write:")
    ):
        logger.info("[COMMUNICATOR] writer pending(write:) → skipping reply and handing off to writer")
        # 현재 communicator 태스크가 있다면 auto-close 해서 재진입 방지
        if pending:
            pending.done = True
            pending.done_at = _now_str()
            pending.description = (pending.description or "") + " [auto-closed: writer pending]"
        # 혹시 직전 단계에서 QA 직답 플래그가 켜졌다면 안전하게 끔
        state["qa_direct_reply"] = False
        # ← 여기서 반환값에 명시적으로 포함
        return {"messages": messages, "task_history": tasks, "qa_direct_reply": False}
    
    # Dash rate-limit
    flags = state.get("flags") or {}   # <- _flags 대신 flags 보장
    last_dash = float(flags.get("dash_last_ts") or 0.0)
    recent = (DASH_ON and (time.time() - last_dash) < DASH_RATE)
    if recent:
        logger.info("[Communicator] (dashboard recently printed) 최소 메시지만 표시합니다.")

    # 진행률 로그 (optional)
    try:
        f = state.get("flags") or {}
        done, total = int(f.get("sections_done") or 0), int(f.get("sections_total") or 0)
        if total > 0: logger.info("[Communicator] 진행률: %d / %d", done, total)
    except Exception: pass
    try:
        f = state.get("flags") or {}
        cd, ct = int(f.get("chapters_done") or 0), int(f.get("chapters_total") or 0)
        if ct: logger.info("[Communicator] 챕터 진행률: %d / %d", cd, ct)
    except Exception: pass

    desc = (pending.description if pending else "") or ""

    def _as_text(content: Any) -> str:
        if isinstance(content, str): return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    for k in ("text","content","value","message"):
                        v = item.get(k)
                        if isinstance(v, str): parts.append(v); break
                    else:
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

    # 플래너 발표 모드
    if "announce_planner" in desc.lower():
        last_planner = next((m for m in reversed(messages)
                             if isinstance(m, AIMessage) and str(m.content or "").startswith("[Research Planner]")), None)
        raw = last_planner.content if last_planner else "(리서치 플래너 메시지를 찾지 못했습니다.)"
        text = _as_text(raw)
        messages.append(AIMessage(content=text))
        logger.info("[Communicator] announce_planner delivered (%s chars)", len(text))
        if pending:
            pending.done = True; pending.done_at = _now_str()
        if not has_pending(tasks, "web_search_agent"):
            tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # show_outline
    show_outline_req, explicit_fname = False, None
    mdesc = re.search(r"show_outline\s*:\s*([A-Za-z0-9_\-\.]+)", desc)
    if mdesc:
        explicit_fname = mdesc.group(1).strip(); show_outline_req = True
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if ("show_outline" in desc.lower()) or (last_human and is_outline_display(last_human.content)):
        show_outline_req = True

    if state.get("outline_shown") and not show_outline_req:
        logger.debug("[Communicator] outline already shown in this session; skipping re-display")

    if show_outline_req:
        preferred = state.get("outline_fname")
        default_by_mode = "outline_report.md" if DOC_MODE == "report" else "outline.md"
        fname = explicit_fname or preferred or default_by_mode
        state["outline_fname"] = fname

        outline_text, used_path = read_outline(filename=fname, root_dir=current_path,
                                               topic_slug=state.get("topic_slug"), mode=DOC_MODE, allow_fallbacks=False)

        if not (outline_text or "").strip():
            if not has_pending(tasks, "content_strategist"):
                tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
            messages.append(AIMessage(content=f"({fname}) 파일이 아직 없습니다. 지금 기본 목차를 생성하겠습니다."))
            logger.info("[Communicator] outline missing; scheduled content_strategist to create (%s)", fname)
            state["outline_shown"] = False
            if pending:
                pending.done = True; pending.done_at = _now_str()
            return {"messages": messages, "task_history": tasks, "outline_fname": fname}

        title = f"## 현재 목차 ({used_path.name if used_path else fname})"
        messages.append(AIMessage(content=f"{title}\n\n{outline_text}"))
        logger.info("[Communicator] outline displayed (%s, %s chars)", fname, len(outline_text or ""))
        state["outline_shown"] = True

        if ECHO_OUTLINE:
            try:
                _hdr = f"\n============ OUTLINE ({used_path.name if used_path else fname}) ============"
                _ftr = "=" * len(_hdr)
                sys.stdout.write(_hdr + "\n\n")
                sys.stdout.write((outline_text or "").rstrip() + "\n")
                sys.stdout.write(_ftr + "\n")
                sys.stdout.flush()
            except Exception as e:
                logger.debug("outline echo failed: %s", e)

        followup = (
            "목차를 확인했습니다. 다음 중 어떻게 진행할까요?\n"
            "1) 특정 섹션부터 바로 집필 → `write: 섹션명`\n"
            "2) 목차 수정 → 바꿀 제목/순서를 말씀해 주세요\n"
            "3) 최신 자료 보강 → `최신 자료로 RAG 업데이트`\n"
        )
        messages.append(AIMessage(content=followup))

        if pending:
            pending.done = True; pending.done_at = _now_str()
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="목차 확인 후 다음 집필 대상/수정 요청 파악", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # ── Direct QA 출력 안전판 ──────────────────────────────────────────────────
    fallback_outline = get_topic_outline_text(state)
    if state.get("qa_direct_reply"):
        last_ai_msg = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last_ai_msg and getattr(last_ai_msg, "content", ""):
            reply_text = _as_text(last_ai_msg.content)
            try:
                sys.stdout.write(reply_text.rstrip() + "\n")
                sys.stdout.write("---------------------\n")
                sys.stdout.flush()
            except Exception:
                logger.warning("[COMMUNICATOR] Console write failed for QA answer.")
            if pending:
                pending.done = True; pending.done_at = _now_str()
            state["qa_direct_reply"] = False
            logger.info("[COMMUNICATOR] Delivered Direct QA Summary.")
            return {"messages": messages, "task_history": tasks, "qa_direct_reply": False}
        else:
            # 미세수정: 플래그는 있는데 메시지가 없을 때 stuck 방지
            logger.warning("[COMMUNICATOR] qa_direct_reply=True but no AI message found. Clearing flag.")
            state["qa_direct_reply"] = False
            # 계속 일반 커뮤니케이션으로 진행

    # 최소 모드
    if recent:
        messages.append(AIMessage(content="[Communicator] 최신 진행상황만 간단히 안내합니다. 자세한 내용은 대시보드 로그를 참고하세요."))
        if pending:
            pending.done = True; pending.done_at = _now_str()
        return {"messages": messages, "task_history": tasks}

    # 일반 커뮤니케이션
    communicator_prompt = get_communicator_prompt()
    system_chain = communicator_prompt | llm

    parts: list[str] = []
    for chunk in system_chain.stream({
        "messages": messages,
        "outline": fallback_outline,
        "doc_label": "보고서" if DOC_MODE == "report" else "책",
        "topic_title": state.get("topic_title") or "",
    }):
        parts.append(_as_text(getattr(chunk, "content", "")))
    text_buf = "\n".join([ln for i, ln in enumerate(("".join(parts)).splitlines()) if i == 0 or ln != ("".join(parts)).splitlines()[i-1]])
    messages.append(AIMessage(content=text_buf))
    logger.debug("[Communicator] generated reply (%s chars)", len(text_buf))

    # 마지막 저장 경로 힌트 (optional)
    try:
        base_text = str(messages[-1].content)
        if not any(x in base_text for x in ["chapters\\","sections\\","chapters/","sections/"]):
            last_save_path, moved_note = None, None
            p_writer = re.compile(r"\[(?:Section|Chapter|Content)\s+Writer\].*?→\s*(?P<path>.+?\.md)\s*", re.DOTALL)
            p_strat  = re.compile(r"\[Content Strategist\].*?→\s*(?P<path>.+?\.md)\s*", re.DOTALL)
            p_moved  = re.compile(r"\[(?:Section|Chapter|Content)\s+Writer\]\s*moved.*?->\s*(?P<path>.+?\.md)\s*", re.DOTALL)
            for m in reversed(messages):
                if not isinstance(m, AIMessage): continue
                content_text = str(m.content)
                m1 = p_writer.search(content_text) or p_strat.search(content_text)
                if m1: last_save_path = m1.group("path").strip(); break
                m2 = p_moved.search(content_text)
                if m2: last_save_path = m2.group("path").strip(); moved_note = " (파일이 자동 정리되어 sections로 이동되었습니다.)"; break
            if not last_save_path:
                lsp = (state or {}).get("last_saved_path")
                if isinstance(lsp, str) and lsp.strip(): last_save_path = lsp.strip()
            if last_save_path:
                try: last_save_path = os.path.normpath(last_save_path)
                except Exception: pass
                messages[-1] = AIMessage(content=base_text + f"\n\n최종 저장 경로: `{last_save_path}`" + (moved_note or ""))
                logger.debug("[Communicator] appended last_saved_path hint → %s", last_save_path)
    except Exception as e:
        logger.warning("[WARN] last-save-path hint failed: %s", e)

    if pending:
        pending.done = True; pending.done_at = _now_str()
    return {"messages": messages, "task_history": tasks}
