from __future__ import annotations
import re, os, sys, time
from typing import Any
from utils.tasks import HumanMessage, AIMessage
import core.config as config
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
from pathlib import Path
logger = logging.getLogger(__name__)
# outline 저장/읽기 경로 계산은 core.paths 내부에서 처리하므로
# root_dir에는 프로젝트 루트만 넘긴다.

def communicator(state: State):
    def _get_topic_title(st) -> str:
        """state/flags/CFG에서 주제 타이틀을 일관되게 해석."""
        flags = (st.get("flags") or {})
        return (
            (flags.get("topic_title") or "").strip()
            or (st.get("topic_title") or "").strip()
            or (config.CFG.TOPIC_TITLE or "").strip()
            or (st.get("topic_slug") or "untitled")
        )

    def _inject_requested_title_if_needed(state: State):
        """
        REQUIRE_EXPLICIT_WRITE_TITLE=True 인 경우,
        requested_write_title 이 비어 있으면 자동 타이틀을 주입해 writer 블로킹을 해제.
        """
        try:
            if not config.CFG.REQUIRE_EXPLICIT_WRITE_TITLE:
                return
            # writer_flags 저장 위치가 프로젝트마다 다를 수 있어 유연하게 조회
            wf = state.get("writer_flags") or state.get("flags") or {}
            # 이미 타이틀 있으면 패스
            existing = (wf.get("requested_write_title") or "").strip()
            if existing:
                return

            # 주입 타이틀 생성
            topic_title = _get_topic_title(state)
            iter_no = int((state.get("iteration_count") or 0)
                          or (state.get("flags") or {}).get("iteration_count")
                          or config.CFG.ITERATION_COUNT or 1)
            auto_title = f"{topic_title} v{iter_no}"

            # 원본 딕셔너리를 직접 수정 (state["writer_flags"] 우선)
            if "writer_flags" not in state or not isinstance(state["writer_flags"], dict):
                state["writer_flags"] = {}
            state["writer_flags"]["requested_write_title"] = auto_title

            # state.flags에도 미러링(모듈에 따라 flags만 읽는 경우가 있어 중복 세팅)
            if "flags" not in state or not isinstance(state["flags"], dict):
                state["flags"] = {}
            state["flags"]["requested_write_title"] = auto_title

            logger.info("[WRITER] injected requested_title='%s'", auto_title)
        except Exception as e:
            logger.warning("[WRITER] requested_title injection failed: %s", e)

    def _safe_save_report(state: State, content_hint: str | None = None):
        """
        산출물(최소한 커뮤니케이터 응답 텍스트라도)을 파일로 저장하고
        state['last_saved_path']를 갱신한다.
        """
        try:
            topic_slug = (state.get("topic_slug") or "report").strip()
            out_root = config.CFG.REPORT_OUT_DIR
            out_root = Path(out_root) if (out_root and str(out_root).strip()) else (Path(current_path) / "outputs")
            out_dir = out_root / topic_slug
            out_dir.mkdir(parents=True, exist_ok=True)

            ts = _now_str().replace(":", "").replace(" ", "_").replace("-", "")
            fname = f"{topic_slug}_{ts}.md"
            out_path = out_dir / fname

            content = None
            if isinstance(content_hint, str) and content_hint.strip():
                content = content_hint
            else:
                content = (state.get("compiled_document") or "").strip()
                if not content:
                    msgs = state.get("messages") or []
                    last_ai = next((m for m in reversed(msgs) if isinstance(m, AIMessage)), None)
                    content = (getattr(last_ai, "content", "") or "").strip()
                if not content:
                    content = "# 보고서(자동 저장)\n\n(현재 수집된 본문이 없어 빈 보고서를 저장했습니다.)\n"

            out_path.write_text(content, encoding="utf-8")
            size = out_path.stat().st_size
            state["last_saved_path"] = str(out_path)
            logger.info("[SAVE] report saved → %s (bytes=%d)", out_path.as_posix(), size)
            logger.debug("last_saved_path after save: %s", state.get("last_saved_path"))
            if size == 0:
                logger.warning("[SAVE][WARN] file saved but size=0 bytes")
        except Exception as e:
            logger.exception("[SAVE][ERROR] failed to save report: %s", e)


    def _save_last_ai_if_any(state: State, messages: list[Any]):
        """
        조기 반환 경로에서도 마지막 AI 메시지를 안전 저장.
        """
        try:
            last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
            text = (getattr(last_ai, "content", "") or "").strip() if last_ai else ""
            if text:
                _safe_save_report(state, content_hint=text)
        except Exception as e:
            logger.warning("[SAVE][EARLY] save last AI failed: %s", e)

    # 토글/설정: config로 일원화
    ECHO_OUTLINE = config.CFG.ECHO_OUTLINE
    COMMUNICATOR_ECHO = config.CFG.ECHO_QA or config.CFG.COMMUNICATOR_ECHO
    HUMAN_LOGS_STRICT = config.CFG.HUMAN_LOGS and (not config.CFG.HUMAN_LOGS_VERBOSE)
    COMM_LOG_QA_BODY = config.CFG.COMM_LOG_QA_BODY
    COMM_LOG_QA_MAXLEN = int(config.CFG.COMM_LOG_QA_MAXLEN or 0)

    logger.info("============ COMMUNICATOR ============")
    DASH_ON = config.CFG.LOG_DASHBOARD
    DASH_RATE = float(config.CFG.DASH_RATE_SEC)

    llm = get_llm()
    state = sanitize_state(state)

    # 🔸 집필 언블락을 위해, 필요한 경우 자동 타이틀 주입
    _inject_requested_title_if_needed(state)

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
        _save_last_ai_if_any(state, messages)
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
        _save_last_ai_if_any(state, messages)
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
        # 모드별 기본 아웃라인 파일명 통일
        default_by_mode = "outline_report.md" if config.CFG.DOC_MODE == "report" else "outline_book.md"
        fname = explicit_fname or preferred or default_by_mode
        state["outline_fname"] = fname

        # 아웃라인 저장 정책(헬퍼)만 사용: REPORT_OUT_DIR/outlines → 없으면 <project>/outlines
        outline_text, used_path = read_outline(
            filename=fname,
            root_dir=str(current_path),               # ✅ 프로젝트 루트
            topic_slug=state.get("topic_slug"),
            mode=config.CFG.DOC_MODE,
            allow_fallbacks=False
        )

        if not (outline_text or "").strip():
            if not has_pending(tasks, "content_strategist"):
                tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
            messages.append(AIMessage(content=f"({fname}) 파일이 아직 없습니다. 지금 기본 목차를 생성하겠습니다."))
            logger.info("[Communicator] outline missing; scheduled content_strategist to create (%s)", fname)
            state["outline_shown"] = False
            if pending:
                pending.done = True; pending.done_at = _now_str()
            # ✅ 저장하지 않음(안내만)
            return {"messages": messages, "task_history": tasks, "outline_fname": fname}

        title = f"## 현재 목차 ({used_path.name if used_path else fname})"
        followup = (
            "목차를 확인했습니다. 다음 중 어떻게 진행할까요?\n"
            "1) 특정 섹션부터 바로 집필 → `write: 섹션명`\n"
            "2) 목차 수정 → 바꿀 제목/순서를 말씀해 주세요\n"
            "3) 최신 자료 보강 → `최신 자료로 RAG 업데이트`\n"
        )
        messages.append(AIMessage(content=f"{title}\n\n{outline_text}\n\n{followup}"))
        logger.info("[Communicator] outline displayed (%s, %s chars)", fname, len(outline_text or ""))
        state["outline_shown"] = True

        if ECHO_OUTLINE and not HUMAN_LOGS_STRICT:
            try:
                _hdr = f"\n============ OUTLINE ({used_path.name if used_path else fname}) ============"
                _ftr = "=" * len(_hdr)
                sys.stdout.write(_hdr + "\n\n")
                sys.stdout.write((outline_text or "").rstrip() + "\n")
                sys.stdout.write(_ftr + "\n")
                sys.stdout.flush()
            except Exception as e:
                logger.debug("outline echo failed: %s", e)

        if pending:
            pending.done = True; pending.done_at = _now_str()
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="목차 확인 후 다음 집필 대상/수정 요청 파악", done_at=""))
        # ✅ 목차 표시 응답도 보고서 파일로 저장하지 않음(혼동 방지)
        return {"messages": messages, "task_history": tasks}

    # ── Direct QA 출력 안전판 ──────────────────────────────────────────────────
    fallback_outline = get_topic_outline_text(state)
    if state.get("qa_direct_reply"):
        last_ai_msg = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last_ai_msg and getattr(last_ai_msg, "content", ""):
            reply_text = _as_text(last_ai_msg.content)

            # 1) 파일 로그에 QA 본문 기록 (COMM_LOG_QA_BODY=1)
            if COMM_LOG_QA_BODY:
                _out = reply_text or ""
                if COMM_LOG_QA_MAXLEN > 0 and len(_out) > COMM_LOG_QA_MAXLEN:
                    _out = _out[:COMM_LOG_QA_MAXLEN] + "…"
                logger.info("[COMMUNICATOR][DirectQA] text=%s", _out)

            # 2) 콘솔 에코는 옵션(ECHO_QA=1 또는 COMMUNICATOR_ECHO=1)이고,
            #    사람용 간소화(HUMAN_LOGS=1 & HUMAN_LOGS_VERBOSE=0)일 땐 억제
            if COMMUNICATOR_ECHO and not HUMAN_LOGS_STRICT:
                try:
                    echo_text = (_out if COMM_LOG_QA_BODY else (reply_text or ""))  # _out은 True일 때만 정의
                    sys.stdout.write((echo_text or "").rstrip() + "\n")
                    sys.stdout.write("---------------------\n")
                    sys.stdout.flush()
                except Exception:
                    logger.warning("[COMMUNICATOR] Console write failed for QA answer.")
            else:
                logger.debug("[COMMUNICATOR] QA reply prepared (len=%d)", len((reply_text or "")))

            if pending:
                pending.done = True; pending.done_at = _now_str()
            state["qa_direct_reply"] = False
            logger.info("[COMMUNICATOR] Delivered Direct QA Summary.")
            _save_last_ai_if_any(state, messages)   # 🔸 누락 보완
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
        _save_last_ai_if_any(state, messages)
        return {"messages": messages, "task_history": tasks}

    # 일반 커뮤니케이션
    communicator_prompt = get_communicator_prompt()
    system_chain = communicator_prompt | llm

    parts: list[str] = []
    for chunk in system_chain.stream({
        "messages": messages,
        "outline": fallback_outline,
        "doc_label": "보고서" if config.CFG.DOC_MODE == "report" else "책",
        "topic_title": state.get("topic_title") or "",
    }):
        parts.append(_as_text(getattr(chunk, "content", "")))

    # 개선안
    merged = "".join(parts)
    lines = merged.splitlines()
    # 연속으로 같은 줄이 두 번 이상 나오는 경우만 제거
    deduped_lines = []
    prev = None
    for ln in lines:
        if ln != prev:
            deduped_lines.append(ln)
        prev = ln
    text_buf = "\n".join(deduped_lines)
    messages.append(AIMessage(content=text_buf))
    logger.debug("[Communicator] generated reply (%s chars)", len(text_buf))
    # === [SAVE HOOK] 산출물 저장 보장 ===
    # Writer가 방금 저장한 직후에는 안내문 자동 저장을 생략
    try:
        just_wrote = False
        # 직전 몇 개 메시지 내에 Writer 완료 신호가 있는지 확인
        for m in reversed(messages[-3:]):
            if isinstance(m, AIMessage):
                mc = str(getattr(m, "content", "") or "")
                # section/chapter/content writer 문구 탐지(대소문자 무시)
                if ("[SECTION WRITER]" in mc.upper()
                    or "[CHAPTER WRITER]" in mc.upper()
                    or "[CONTENT WRITER]" in mc.upper()):
                    just_wrote = True
                    break
        if not just_wrote:
            _safe_save_report(state, content_hint=text_buf)
        else:
            logger.debug("[Communicator] skip autosave (writer just saved).")
    except Exception as e:
        logger.warning("[SAVE][HOOK] save attempt failed: %s", e)

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
            # 우선 방금 저장된 경로를 최우선으로 사용
            if not last_save_path:
                lsp = (state or {}).get("last_saved_path")
                if isinstance(lsp, str) and lsp.strip():
                    last_save_path = lsp.strip()
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
