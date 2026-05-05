from __future__ import annotations
import re, os, sys, time
from typing import Any, cast, Optional
from utils.tasks import HumanMessage, AIMessage, has_pending
import core.config as config
from core.paths import now_str as _now_str, current_path, sections_dir
from core.state_types import State
from core.models import Task
from utils.sanitize import sanitize_state, coerce_int
from rag_expression import is_outline_display
from prompts import get_communicator_prompt
from core.paths import read_outline
from utils.outline import get_topic_outline_text
from core.llm import get_llm
from core.routers import _is_show_outline_intent
import logging
from pathlib import Path
logger = logging.getLogger(__name__)
# outline 저장/읽기 경로 계산은 core.paths 내부에서 처리하므로
# root_dir에는 프로젝트 루트만 넘긴다.

def communicator(state: State):
    # 진행률: 실제 섹션 디렉터리(sections/<topic_slug>)에 저장된 *.md 개수로 계산
    def _count_existing_section_files(topic_slug: str) -> int:
        try:
            mode = getattr(config.CFG, "DOC_MODE", "report")
            sd = sections_dir(topic_slug, mode=mode)  # core.paths.find_section_path와 동일 기준
        except Exception:
            # 안전 폴백(예외적 경로): 프로젝트 루트 기준 추정
            base = str(current_path() if callable(current_path) else current_path)
            sd = Path(base) / "sections" / (topic_slug or "untitled")
        if not sd.exists():
            return 0
        # 토픽 루트 바로 하위의 섹션 파일만 집계(중첩 폴더 제외)
        return sum(1 for _ in sd.glob("*.md"))
    # 안전 텍스트 변환: str/list/dict → str, 그 외는 str()로 변환
    def _to_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    for k in ("text", "content", "value", "message"):
                        v = item.get(k)
                        if isinstance(v, str):
                            parts.append(v)
                            break
                    else:
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

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

    def _safe_save_report(state: State, content_hint: str | None = None, *, qa_mode: bool = False):
        """
        산출물(최소한 커뮤니케이터 응답 텍스트라도)을 파일로 저장하고
        state['last_saved_path']를 갱신한다.

        §12-13-4: qa_mode=True이면 reports/<topic_slug>/qa/ 서브디렉터리 +
        파일명 prefix 'qa_'로 저장하여 작성(write) 산출물과 분리.
        """
        try:
            topic_slug = (state.get("topic_slug") or "report").strip()
            # REPORT_OUT_DIR이 비었으면 <project_root>/outputs 사용
            cfg_root = getattr(config.CFG, "REPORT_OUT_DIR", None)
            if cfg_root and str(cfg_root).strip():
                out_root_path: Path = Path(str(cfg_root))
            else:
                base = current_path() if callable(current_path) else current_path  # function 혹은 값 모두 대응
                out_root_path = Path(str(base)) / "outputs"
            # §12-13-4: QA 응답은 별도 서브디렉터리로 분리
            if qa_mode:
                out_dir = out_root_path / topic_slug / "qa"
            else:
                out_dir = out_root_path / topic_slug
            out_dir.mkdir(parents=True, exist_ok=True)

            ts = _now_str().replace(":", "").replace(" ", "_").replace("-", "")
            # §12-13-4: QA는 'qa_' prefix로 작성 산출물과 식별 분리
            prefix = "qa_" if qa_mode else ""
            fname = f"{prefix}{topic_slug}_{ts}.md"
            out_path = out_dir / fname

            content: str | None = None
            if isinstance(content_hint, str) and content_hint.strip():
                content = content_hint
            else:
                # compiled_document가 dict/list 등일 수 있으므로 안전 변환
                content = _to_text(state.get("compiled_document") or "").strip()
                if not content:
                    msgs = state.get("messages") or []
                    last_ai = next((m for m in reversed(msgs) if isinstance(m, AIMessage)), None)
                    if last_ai is not None and hasattr(last_ai, "content"):
                        content = _to_text(last_ai.content).strip()
                    else:
                        content = ""
                if not content:
                    content = "# 보고서(자동 저장)\n\n(현재 수집된 본문이 없어 빈 보고서를 저장했습니다.)\n"

            out_path.write_text(content, encoding="utf-8")
            size = out_path.stat().st_size
            state["last_saved_path"] = str(out_path)
            logger.info("[SAVE] %sreport saved → %s (bytes=%d)",
                        "QA " if qa_mode else "", out_path.as_posix(), size)
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
            text = _to_text(last_ai.content).strip() if (last_ai is not None and hasattr(last_ai, "content")) else ""
            if text:
                _safe_save_report(state, content_hint=text)
        except Exception as e:
            logger.warning("[SAVE][EARLY] save last AI failed: %s", e)

    # 토글/설정: config로 일원화
    ECHO_OUTLINE = bool(getattr(config.CFG, "ECHO_OUTLINE", False))
    COMMUNICATOR_ECHO = bool(getattr(config.CFG, "ECHO_QA", False) or getattr(config.CFG, "COMMUNICATOR_ECHO", False))
    HUMAN_LOGS_STRICT = bool(getattr(config.CFG, "HUMAN_LOGS", False) and (not getattr(config.CFG, "HUMAN_LOGS_VERBOSE", False)))
    COMM_LOG_QA_BODY = bool(getattr(config.CFG, "COMM_LOG_QA_BODY", False))
    COMM_LOG_QA_MAXLEN = int(getattr(config.CFG, "COMM_LOG_QA_MAXLEN", 0) or 0)

    logger.info("============ COMMUNICATOR ============")
    DASH_ON = bool(getattr(config.CFG, "LOG_DASHBOARD", False))
    DASH_RATE = float(getattr(config.CFG, "DASH_RATE_SEC", 0.0) or 0.0)

    # ─────────────────────────────────────────────────────────────
    # [HARD GUARANTEE] Direct QA는 항상 마지막 AI 메시지 본문을 저장/출력한다.
    # - 다른 분기(writer pending, outline, dashboard rate-limit 등)로 덮이지 않도록 최상단에서 처리
    # - 원천 데이터는 "messages의 마지막 AIMessage.content"를 사용(Direct QA Summary의 실제 본문)
    # - 성공 시: messages 끝을 QA 본문으로 보장 + 파일 저장 + (옵션) 콘솔 출력 + 플래그 정리 + 종료
    # ─────────────────────────────────────────────────────────────
    def _set_flag_qa_done(st: State) -> None:
        ff = dict(st.get("flags") or {})
        ff["qa_direct_reply"] = False
        ff["suppress_writer"] = False
        st["flags"] = ff
        # 레거시/혼용 방지: 루트키도 보조로 정리(사용하지 않는 게 원칙이어도 방어적으로)
        st["qa_direct_reply"] = False

    def _get_last_ai_text(msgs: list[Any]) -> str:
        last_ai = next((m for m in reversed(msgs) if isinstance(m, AIMessage)), None)
        if last_ai is None or not hasattr(last_ai, "content"):
            return ""
        return (_to_text(getattr(last_ai, "content", "")) or "").strip()

    def _ensure_last_ai_is(msgs: list[Any], text: str) -> list[Any]:
        if not text:
            return msgs
        if msgs:
            last = msgs[-1]
            if isinstance(last, AIMessage):
                last_txt = (_to_text(getattr(last, "content", "")) or "").strip()
                if last_txt == text:
                    return msgs
        msgs.append(AIMessage(content=text))
        return msgs

    flags0 = dict(state.get("flags") or {})
    qa_mode = bool(flags0.get("qa_direct_reply") or state.get("qa_direct_reply"))
    # 🔹 새 Direct QA 경로(additional_kwargs["qa_direct_reply"]=True)는
    # 아래 _deliver_direct_qa_and_exit()에서 처리한다.
    # 여기 블록은 "레거시 플래그 기반 QA"만 처리하도록,
    # tagged QA 메시지가 없을 때만 동작시키자.
    has_tagged_qa = False
    try:
        for m in reversed(state.get("messages") or []):
            if not isinstance(m, AIMessage):
                continue
            extra = getattr(m, "additional_kwargs", {}) or {}
            if isinstance(extra, dict) and extra.get("qa_direct_reply") is True:
                has_tagged_qa = True
                break
    except Exception:
        has_tagged_qa = False
        
    # 🔴 레거시 플래그 기반 Direct QA만 처리
    # tagged QA(additional_kwargs["qa_direct_reply"]=True)가 있으면
    # 이 블록은 건너뛰고, 아래 _deliver_direct_qa_and_exit()에 맡긴다.
    if qa_mode and not has_tagged_qa:
        messages0 = state.get("messages") or []
        reply_text = _get_last_ai_text(messages0)

        if not reply_text:
            # Direct QA 플래그는 있는데 본문이 없으면: 빈 저장/빈 출력 금지 → fallback 스케줄링
            logger.warning("[COMMUNICATOR] qa_direct_reply=True but last AI message is empty. Scheduling fallback.")

            # ✅ show_outline이면 RAG 재시도 스케줄링 금지 (web/vector로 새는 것 차단)
            if state.get("command_intent") == "show_outline" or (state.get("flags") or {}).get("show_outline"):
                logger.info("[COMMUNICATOR][fallback-skip] show_outline intent → skip web/vector scheduling")
                tasks0 = state.get("task_history", []) or []

                # communicator task 닫기 (기존 로직 재사용)
                pending0 = next((t for t in reversed(tasks0)
                                 if (not getattr(t, "done", True)) and getattr(t, "agent", "") == "communicator"), None)
                if pending0:
                    pending0.done = True
                    pending0.done_at = _now_str()

                state["task_history"] = tasks0
                _set_flag_qa_done(state)
                return {"messages": state.get("messages") or [], "task_history": tasks0, "qa_direct_reply": False}

            tasks0 = state.get("task_history", []) or []
            allow_web = not bool(getattr(config.CFG, "SKIP_WEB_SEARCH", False))
            have_refs = bool(((state.get("references") or {}).get("docs") or []))


            if have_refs:
                if not has_pending(tasks0, "vector_search_agent"):
                    tasks0.append(Task(agent="vector_search_agent", done=False, description="fallback: direct_qa_missing → retry", done_at=""))
                    logger.info("[COMMUNICATOR][fallback] refs present → scheduled vector_search_agent")
            else:
                if allow_web and not has_pending(tasks0, "web_search_agent"):
                    tasks0.append(Task(agent="web_search_agent", done=False, description="fallback: direct_qa_missing → rag_update:auto", done_at=""))
                    logger.info("[COMMUNICATOR][fallback] refs empty → scheduled web_search_agent")
                elif not has_pending(tasks0, "vector_search_agent"):
                    tasks0.append(Task(agent="vector_search_agent", done=False, description="fallback: direct_qa_missing → retry", done_at=""))
                    logger.info("[COMMUNICATOR][fallback] scheduled vector_search_agent")

            # communicator task 닫기
            pending0 = next((t for t in reversed(tasks0) if (not getattr(t, "done", True)) and getattr(t, "agent", "") == "communicator"), None)
            if pending0:
                pending0.done = True
                pending0.done_at = _now_str()
            state["task_history"] = tasks0
            _set_flag_qa_done(state)
            return {"messages": messages0, "task_history": tasks0, "qa_direct_reply": False}

        # ✅ 보장: messages 마지막 AI가 reply_text가 되도록 강제
        messages0 = _ensure_last_ai_is(list(messages0), reply_text)
        state["messages"] = messages0

        # ✅ 보장: Direct QA 본문은 항상 저장
        try:
            # §12-13-4: QA 응답은 qa/ 서브디렉터리 + qa_ prefix로 분리 저장
            _safe_save_report(state, content_hint=reply_text, qa_mode=True)
        except Exception as e:
            logger.warning("[SAVE][DirectQA] save failed: %s", e)

        # ✅ 보장: 출력(옵션) 또는 최소 로그
        try:
            COMM_LOG_QA_BODY = bool(getattr(config.CFG, "COMM_LOG_QA_BODY", False))
            COMM_LOG_QA_MAXLEN = int(getattr(config.CFG, "COMM_LOG_QA_MAXLEN", 0) or 0)
            HUMAN_LOGS_STRICT = bool(getattr(config.CFG, "HUMAN_LOGS", False) and (not getattr(config.CFG, "HUMAN_LOGS_VERBOSE", False)))
            log_text = reply_text
            if COMM_LOG_QA_BODY and COMM_LOG_QA_MAXLEN > 0 and len(log_text) > COMM_LOG_QA_MAXLEN:
                log_text = log_text[:COMM_LOG_QA_MAXLEN] + "…"
            if COMM_LOG_QA_BODY:
                logger.info("[COMMUNICATOR][DirectQA] text=%s", log_text)
            if COMMUNICATOR_ECHO and not HUMAN_LOGS_STRICT:
                sys.stdout.write((log_text if COMM_LOG_QA_BODY else reply_text).rstrip() + "\n")
                sys.stdout.write("---------------------\n")
                sys.stdout.flush()
            else:
                logger.debug("[COMMUNICATOR] QA reply prepared (len=%d)", len(reply_text))
        except Exception:
            pass

        # task 닫기 + 플래그 정리 + 종료
        tasks0 = state.get("task_history", []) or []
        pending0 = next((t for t in reversed(tasks0) if (not getattr(t, "done", True)) and getattr(t, "agent", "") == "communicator"), None)
        if pending0:
            pending0.done = True
            pending0.done_at = _now_str()
        state["task_history"] = tasks0
        _set_flag_qa_done(state)
        logger.info("[COMMUNICATOR] Delivered Direct QA Summary.")
        return {"messages": messages0, "task_history": tasks0, "qa_direct_reply": False}

    # Mapping → dict(materialize) for mutation safety & type-check compatibility
    state = cast(State, sanitize_state(state))

    # ─────────────────────────────────────────────────────────────
    # [HARD STOP — Direct QA 즉시 종료 + 저장 + flags 정리]
    # - qa_direct_reply가 설정된 경우, 항상 "마지막 AI 메시지"가
    #   QA 본문이 되도록 보장하고, 바로 저장 후 반환한다.
    # - Synthesizer 등의 로그 메시지가 뒤에 오더라도
    #   사용자에게는 QA 답변이 마지막으로 보이도록 강제한다.
    # ─────────────────────────────────────────────────────────────
    def _deliver_direct_qa_and_exit() -> dict[str, Any] | None:
        msgs = state.get("messages") or []
        tasks = state.get("task_history") or []
        flags = dict(state.get("flags") or {})

        # (1) additional_kwargs.qa_direct_reply=True 인 AIMessage 탐색
        qa_msg = None
        for m in reversed(msgs):
            if not isinstance(m, AIMessage):
                continue
            extra = getattr(m, "additional_kwargs", {}) or {}
            if isinstance(extra, dict) and extra.get("qa_direct_reply") is True:
                if _to_text(getattr(m, "content", "")).strip():
                    qa_msg = m
                    break

        # (2) flags["qa_direct_reply"]만 켜져 있는 경우: 마지막 AI를 QA로 간주
        if qa_msg is None and flags.get("qa_direct_reply") is True:
            last_ai = next((m for m in reversed(msgs) if isinstance(m, AIMessage)), None)
            if last_ai is not None and _to_text(getattr(last_ai, "content", "")).strip():
                qa_msg = last_ai

        if qa_msg is None:
            return None

        reply_text = _to_text(getattr(qa_msg, "content", "")).strip()
        if not reply_text:
            return None

        # (3) QA 플래그 제거: 재진입 시 다시 Direct QA로 처리되지 않도록
        try:
            extra = getattr(qa_msg, "additional_kwargs", None)
            if isinstance(extra, dict) and "qa_direct_reply" in extra:
                extra["qa_direct_reply"] = False
        except Exception:
            pass

        # (4) 마지막 AI 메시지로 보장 (필요 시 append)
        last_msg = msgs[-1] if msgs else None
        last_txt = _to_text(getattr(last_msg, "content", "")).strip() if last_msg is not None else ""
        if last_txt != reply_text:
            msgs.append(AIMessage(content=reply_text))
            state["messages"] = msgs

        # (5) Direct QA 본문을 즉시 저장
        # §12-13-4: QA 응답은 qa/ 서브디렉터리 + qa_ prefix로 분리 저장
        _safe_save_report(state, content_hint=reply_text, qa_mode=True)

        # (6) communicator pending task 종료
        pending = next(
            (t for t in reversed(tasks)
             if (not getattr(t, "done", True)) and getattr(t, "agent", "") == "communicator"),
            None,
        )
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        state["task_history"] = tasks

        # (7) flags 정리 (루트키도 함께 정리해 후속 라우터 혼란 방지)
        flags["qa_direct_reply"] = False
        flags["suppress_writer"] = False
        state["flags"] = flags
        state["qa_direct_reply"] = False

        logger.info("[COMMUNICATOR] Direct QA delivered (hard-stop, len=%d)", len(reply_text))
        return {
            "messages": msgs,
            "task_history": tasks,
            "qa_direct_reply": False,
            "suppress_writer": False,
        }

    _dq_out = _deliver_direct_qa_and_exit()
    if _dq_out is not None:
        return _dq_out

    # ─────────────────────────────────────────────────────────────
    # [STRICT WRITER GUARD — 최상단]
    # - writer가 pending이면 communicator가 개입/메시지 추가/저장을 하지 않도록 즉시 반환
    # - 단, suppress_writer=True면 우회(직답/안내 허용)
    # - 기준: write: prefix 대기, CFG.WRITER_AGENT, open writer task, pending_write_title
    # ─────────────────────────────────────────────────────────────
    _flags0 = state.get("flags") or {}
    _suppress_writer = bool(_flags0.get("suppress_writer"))
    _tasks0 = state.get("task_history", []) or []

    def _has_writer_pending_strict(ts) -> bool:
        try:
            # 표준 writer 대기
            if has_pending(ts, "section_writer", prefix="write:") or has_pending(ts, "chapter_writer", prefix="write:"):
                return True
            # 커스텀 WRITER_AGENT 지원
            wa = getattr(config.CFG, "WRITER_AGENT", None)
            if isinstance(wa, str) and has_pending(ts, wa, prefix="write:"):
                return True
        except Exception:
            pass
        # 안전망: 'write:' 없이 열린 writer 태스크가 있는지 점검
        for t in reversed(ts):
            if (getattr(t, "done", True) is False) and getattr(t, "agent", "") in ("section_writer", "chapter_writer"):
                return True
        return False

    _writer_lock = bool(_flags0.get("pending_write_title"))
    if (not _suppress_writer) and (_has_writer_pending_strict(_tasks0) or _writer_lock):
        # 현재 communicator 태스크가 있으면 auto-close
        _pending = next((t for t in reversed(_tasks0)
                         if (not getattr(t, "done", True)) and getattr(t, "agent", "") == "communicator"), None)
        if _pending:
            _pending.done = True
            _pending.done_at = _now_str()
            _pending.description = (getattr(_pending, "description", "") or "") + " [auto-closed: writer pending(strict)]"
        # Direct QA 플래그를 안전하게 정리
        _f = dict(_flags0)
        _f["qa_direct_reply"] = False
        state["flags"] = _f
        state["task_history"] = _tasks0
        # 마지막 AI 메시지는 안전 저장(있을 때만)
        try:
            _msgs0 = state.get("messages") or []
            last_ai = next((m for m in reversed(_msgs0) if isinstance(m, AIMessage)), None)
            if last_ai is not None and hasattr(last_ai, "content") and str(getattr(last_ai, "content") or "").strip():
                # 내부 헬퍼 활용(이미 선언됨)
                # _save_last_ai_if_any는 state/messages 기반으로 안전 저장
                _save_last_ai_if_any(state, _msgs0)  # noqa: F405
        except Exception:
            pass
        return {"messages": state.get("messages", []) or [], "task_history": _tasks0, "qa_direct_reply": False}


    # ── Direct QA 모드(간단 경로): 벡터검색 요약만 1~2문장으로 반환 ─────────────
    _flags_obj = state.get("flags") or {}
    _qa_mode = False
    if isinstance(_flags_obj, dict):
        _qa_mode = bool(_flags_obj.get("qa_direct_reply", False))
    else:
        # dict가 아닐 비정상 상황 가드
        _qa_mode = bool(state.get("qa_direct_reply", False))
    # NOTE: Direct QA 보장은 상단 HARD GUARANTEE에서 처리한다.
    # 안전 정규화: 답변 실체가 없으면 qa_direct_reply 강제 해제(루프/경고 방지)
    if _qa_mode:
        _has_reply = bool(state.get("qa_reply")) or bool(_to_text(
            getattr(next((m for m in reversed(state.get("messages") or [])
                        if hasattr(m, "content")), None), "content", "")
        ).strip())
        if not _has_reply:
            flags_fix = dict(state.get("flags") or {})
            flags_fix["qa_direct_reply"] = False
            state["flags"] = flags_fix
            state["qa_direct_reply"] = False
            _qa_mode = False

    if _qa_mode:
        # 우선순위: state.answer → state.last_summary → 마지막 AI 메시지
        ans = (str(state.get("answer") or "") or str(state.get("last_summary") or "")).strip()
        _msgs = state.get("messages") or []
        _last_ai = next((m for m in reversed(_msgs) if hasattr(m, "content")), None)
        if not ans:
            try:
                ans = (str(getattr(_last_ai, "content", "") or "")).strip()
            except Exception:
                ans = ""
        # ▾ 답변이 비어 있으면 직답 경로 중단 → 폴백 라우팅(웹서치/벡터 재시도)
        if not ans:
            tasks = state.get("task_history", []) or []

            # ✅ show_outline intent면: web_search/vector_search 폴백 스케줄링 금지
            # (목차 요청이 DB-empty 보정 로직에 의해 web→vector로 새는 것 차단)
            if _is_show_outline_intent(state):
                logger.info("[COMMUNICATOR][fallback-skip] show_outline intent → skip web/vector scheduling")
                # 현 communicator 태스크 종료
                pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
                if pending:
                    pending.done = True
                    pending.done_at = _now_str()
                state["task_history"] = tasks
                # 플래그 정리(내부 flags에만)
                flags_fix = dict(state.get("flags") or {})
                flags_fix["qa_direct_reply"] = False
                flags_fix["suppress_writer"] = False
                state["flags"] = flags_fix
                return {
                    "messages": state.get("messages", []) or [],
                    "task_history": tasks,
                    "qa_direct_reply": False,
                }

            # 폴백 선택: refs가 있으면 벡터 재시도, 없으면(가능 시) 웹서치, 아니면 벡터 재시도
            have_refs = bool(((state.get("references") or {}).get("docs") or []))
            allow_web = not bool(getattr(config.CFG, "SKIP_WEB_SEARCH", False))
            if have_refs:
                if not has_pending(tasks, "vector_search_agent"):
                    tasks.append(Task(agent="vector_search_agent", done=False, description="fallback: direct_qa_missing → retry", done_at=""))
                    logger.info("[COMMUNICATOR][fallback] refs present → scheduled vector_search_agent")
            else:
                if allow_web and not has_pending(tasks, "web_search_agent"):
                    tasks.append(Task(agent="web_search_agent", done=False, description="fallback: direct_qa_missing → rag_update:auto", done_at=""))
                    logger.info("[COMMUNICATOR][fallback] refs empty → scheduled web_search_agent")
                elif not has_pending(tasks, "vector_search_agent"):
                    tasks.append(Task(agent="vector_search_agent", done=False, description="fallback: direct_qa_missing → retry", done_at=""))
                    logger.info("[COMMUNICATOR][fallback] direct QA missing → scheduled vector_search_agent")
            # 현 communicator 태스크 종료
            pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
            if pending:
                pending.done = True; pending.done_at = _now_str()
            state["task_history"] = tasks
            # 플래그 정리(내부 flags에만)
            flags_fix = dict(state.get("flags") or {})
            flags_fix["qa_direct_reply"] = False
            flags_fix["suppress_writer"] = False
            state["flags"] = flags_fix
            return {"messages": state.get("messages", []) or [], "task_history": tasks, "qa_direct_reply": False}

        # (정상) 답변이 존재하면 그대로 전달하되, 중복 append 방지
        reply_text = ans
        messages = state.get("messages", []) or []
        if not (_last_ai and hasattr(_last_ai, "content") and str(getattr(_last_ai, "content") or "").strip() == reply_text):
            messages.append(AIMessage(content=reply_text))
            state["messages"] = messages
        # 현재 communicator 태스크가 있으면 auto-close
        tasks = state.get("task_history", []) or []
        pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        state["task_history"] = tasks
        # 플래그 정리(직답 종료 → writer 억제 해제)
        flags_fix = dict(state.get("flags") or {})
        flags_fix["qa_direct_reply"] = False
        flags_fix["suppress_writer"] = False
        state["flags"] = flags_fix
        return {
            "messages": messages,
            "task_history": tasks,
            "qa_direct_reply": False,
            "suppress_writer": False,
        }


    # 🔸 집필 언블락을 위해, 필요한 경우 자동 타이틀 주입
    _inject_requested_title_if_needed(state)

    # ── 초기화 ───────────────────────────────────────────────────────────
    messages = state.get("messages", []) or []
    tasks = state.get("task_history", []) or []
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")
    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)

    # [GUARD] writer pending이면 communicator를 건너뜀(하단도 동일 정책 적용)
    # - suppress_writer=True면 우회(커뮤니케이터 허용)
    # - pending_write_title(제목 대기)도 writer 대기 취급
    _flags_now = state.get("flags") or {}
    _suppress_writer2 = bool(_flags_now.get("suppress_writer"))
    _writer_lock2 = bool(_flags_now.get("pending_write_title"))
    if (not _suppress_writer2) and (
        has_pending(tasks, "section_writer", prefix="write:") or
        has_pending(tasks, "chapter_writer", prefix="write:") or
        (isinstance(getattr(config.CFG, "WRITER_AGENT", None), str) and has_pending(tasks, getattr(config.CFG, "WRITER_AGENT"), prefix="write:")) or
        _writer_lock2
    ):
        logger.info("[COMMUNICATOR] writer pending(write:) → skipping reply and handing off to writer")
        # 현재 communicator 태스크가 있다면 auto-close 해서 재진입 방지
        if pending:
            pending.done = True
            pending.done_at = _now_str()
            pending.description = (pending.description or "") + " [auto-closed: writer pending]"
        # Direct QA/Suppress 플래그 안전 정리
        _ff = dict(_flags_now)
        _ff["qa_direct_reply"] = False
        state["flags"] = _ff
        # ← 여기서 반환값에 명시적으로 포함
        _save_last_ai_if_any(state, messages)
        return {"messages": messages, "task_history": tasks, "qa_direct_reply": False}
    
    # Dash rate-limit
    flags = state.get("flags") or {}   # <- _flags 대신 flags 보장
    last_dash = float(flags.get("dash_last_ts") or 0.0)
    recent = (DASH_ON and (time.time() - last_dash) < DASH_RATE)
    if recent:
        logger.info("[Communicator] (dashboard recently printed) 최소 메시지만 표시합니다.")

    # 진행률 계산/로그(파일 존재 기준으로 환산)
    try:
        topic_slug = (state.get("topic_slug") or "untitled").strip()
        # TypedDict(Flags) → 일반 dict로 복사해 가변/옵션키 경고 회피
        f0 = state.get("flags") or {}
        progress_flags: dict[str, object] = dict(f0)  # plain dict
        completed = _count_existing_section_files(topic_slug)
        sections_done = coerce_int(completed, 0)
        progress_flags["sections_done"] = sections_done
        # sections_total은(있다면) 유지, 없으면 0
        sections_total = coerce_int(progress_flags.get("sections_total"), 0)
        progress_flags["sections_total"] = sections_total
        state["flags"] = progress_flags
        if sections_total > 0:
            logger.info("[Communicator] 진행률: %d / %d", sections_done, sections_total)
        else:
            logger.info("[Communicator] 진행률(완료 섹션): %d", sections_done)
    except Exception as e:
        logger.debug("[Communicator] 진행률 계산 실패: %s", e)
    try:
        f2 = state.get("flags") or {}
        cd = coerce_int(f2.get("chapters_done"), 0)
        ct = coerce_int(f2.get("chapters_total"), 0)
        if ct:
            logger.info("[Communicator] 챕터 진행률: %d / %d", cd, ct)
    except Exception:
        pass

    desc = (pending.description if pending else "") or ""

    # 기존 구현과 동일 동작을 유지하되 내부적으로 _to_text 사용
    def _as_text(content: Any) -> str:
        return _to_text(content)

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

    # ── FAST-SKIP: 이미 아웃라인을 보여준 상태이고, 명시적 요청이 아니면 재표시 금지
    if bool(state.get("outline_shown")) is True and not show_outline_req:
        logger.debug("[Communicator] outline already shown; fast-skip communicator")
        # 현재 communicator 태스크가 있다면 auto-close 해서 재진입 방지
        if pending:
            pending.done = True
            pending.done_at = _now_str()
            pending.description = (pending.description or "") + " [auto-closed: outline already shown]"
        # 상태에 확실히 기록(라우터 tail에서 outline_shown 검사를 신뢰)
        state["outline_shown"] = True
        _save_last_ai_if_any(state, messages)
        return {"messages": messages, "task_history": tasks, "outline_shown": True}

    if show_outline_req:
        preferred = state.get("outline_fname")
        # 모드별 기본 아웃라인 파일명 통일
        default_by_mode = "outline_report.md" if config.CFG.DOC_MODE == "report" else "outline_book.md"
        fname = explicit_fname or preferred or default_by_mode
        state["outline_fname"] = fname

        # 아웃라인 저장 정책(헬퍼)만 사용: REPORT_OUT_DIR/outlines → 없으면 <project>/outlines
        _outline_res = read_outline(
            filename=fname,
            # current_path가 함수/값 모두 가능 → 안전 처리
            root_dir=str(current_path() if callable(current_path) else current_path),
            topic_slug=state.get("topic_slug"),
            mode=config.CFG.DOC_MODE,
            allow_fallbacks=False,
        )
        # read_outline가 str 또는 (str, Path)를 반환할 수 있으므로 안전 언패킹
        if isinstance(_outline_res, tuple):
            outline_text, used_path = _outline_res[0], _outline_res[1]
        else:
            outline_text, used_path = str(_outline_res or ""), None

        if not (str(outline_text or "").strip()):
            if not has_pending(tasks, "content_strategist"):
                tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
            messages.append(AIMessage(content=f"({fname}) 파일이 아직 없습니다. 지금 기본 목차를 생성하겠습니다."))
            logger.info("[Communicator] outline missing; scheduled content_strategist to create (%s)", fname)
            # 아직 파일이 없으므로 표시 불가 → 명시적으로 False
            state["outline_shown"] = False
            if pending:
                pending.done = True; pending.done_at = _now_str()
            # ✅ 저장하지 않음(안내만)
            return {"messages": messages, "task_history": tasks, "outline_fname": fname}

        # ✅ show_outline 경로에서는 LLM 스트리밍을 돌리지 않습니다. parts/chunk 사용 금지.
        title = f"## 현재 목차 ({used_path.name if used_path else fname})"
        followup = (
            "목차를 확인했습니다. 다음 중 어떻게 진행할까요?\n"
            "1) 특정 섹션부터 바로 집필 → `write: 섹션명`\n"
            "2) 목차 수정 → 바꿀 제목/순서를 말씀해 주세요\n"
            "3) 최신 자료 보강 → `최신 자료로 RAG 업데이트`\n"
        )
        messages.append(AIMessage(content=f"{title}\n\n{outline_text}\n\n{followup}"))
        logger.info("[Communicator] outline displayed (%s, %s chars)", fname, len(outline_text or ""))
        # ✅ 아웃라인을 실제로 보여줬으니 표시 플래그를 반드시 True로
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
        # 반복 진입 방지: outline을 보여준 직후 communicator 재스케줄은 선택 사항.
        # router.tail에서 outline_shown=True를 확인하므로 여기선 추가 예약 불필요.
        # 필요 시 아래 두 줄을 주석 해제.
        # if not has_pending(tasks, "communicator"):
        #     tasks.append(Task(agent="communicator", done=False, description="목차 확인 후 다음 집필 대상/수정 요청 파악", done_at=""))
        # ✅ 목차 표시 응답도 보고서 파일로 저장하지 않음(혼동 방지)
        return {"messages": messages, "task_history": tasks, "outline_shown": True}

    # ── Direct QA 출력 안전판 ──────────────────────────────────────────────────
    fallback_outline = get_topic_outline_text(state)
    # Direct QA일 때도 아래 공통 SAVE HOOK(628+)까지 흘려보내기 위해
    # text_buf를 여기서도 채울 수 있게 플래그/버퍼를 준비한다.
    direct_qa_mode = False
    text_buf: str = ""

    if state.get("qa_direct_reply"):
        last_ai_msg = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if last_ai_msg is not None and hasattr(last_ai_msg, "content") and _to_text(last_ai_msg.content):
            reply_text = _to_text(last_ai_msg.content)

            # 1) 파일 로그에 QA 본문 기록 (COMM_LOG_QA_BODY=1)
            log_text = reply_text or ""
            if COMM_LOG_QA_BODY:
                if COMM_LOG_QA_MAXLEN > 0 and len(log_text) > COMM_LOG_QA_MAXLEN:
                    log_text = log_text[:COMM_LOG_QA_MAXLEN] + "…"
                logger.info("[COMMUNICATOR][DirectQA] text=%s", log_text)

            # 2) 콘솔 에코(옵션). 간소 로그 모드(HUMAN_LOGS_STRICT)에서는 억제
            if COMMUNICATOR_ECHO and not HUMAN_LOGS_STRICT:
                try:
                    sys.stdout.write((log_text if COMM_LOG_QA_BODY else (reply_text or "")).rstrip() + "\n")
                    sys.stdout.write("---------------------\n")
                    sys.stdout.flush()
                except Exception:
                    logger.warning("[COMMUNICATOR] Console write failed for QA answer.")
            else:
                logger.debug("[COMMUNICATOR] QA reply prepared (len=%d)", len((reply_text or "")))

            if pending:
                pending.done = True; pending.done_at = _now_str()
            # qa_direct_reply는 flags 기준으로 정리 (state 루트키는 사용하지 않거나 보조로만)
            _ff = dict(state.get("flags") or {})
            _ff["qa_direct_reply"] = False
            state["flags"] = _ff
            logger.info("[COMMUNICATOR] Delivered Direct QA Summary.")

            # ✅ 여기서 return 하지 말고, 아래 공통 SAVE HOOK 경로를 타도록 버퍼 세팅
            direct_qa_mode = True
            text_buf = (reply_text or "").strip()

            # 안전 가드: messages 끝이 QA 답변이 아니면 추가
            try:
                last_msg = messages[-1] if messages else None
                last_txt = _to_text(getattr(last_msg, "content", "")) if last_msg is not None else ""
                if not last_txt or (last_txt.strip() != text_buf):
                    messages.append(AIMessage(content=text_buf))
            except Exception:
                # 최악의 경우라도 text_buf는 유지
                pass

            # 저장은 아래 공통 SAVE HOOK에서 1회만 수행 (중복 저장 방지)
        else:
            # 🔧 변경: 메시지가 없으면 합성하지 말고 즉시 폴백 라우팅(웹서치/벡터 재시도)
            logger.warning("[COMMUNICATOR] qa_direct_reply=True but no AI message. Routing to fallback instead of synthesizing.")
            tasks = state.get("task_history", []) or []

            # ✅ show_outline intent면: web_search/vector_search 폴백 스케줄링 금지
            if _is_show_outline_intent(state):
                logger.info("[COMMUNICATOR][fallback-skip] show_outline intent → skip web/vector scheduling")
                # 커뮤니케이터 태스크 종료
                pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
                if pending:
                    pending.done = True
                    pending.done_at = _now_str()
                state["task_history"] = tasks
                # 플래그 정리
                flags_fix = dict(state.get("flags") or {})
                flags_fix["qa_direct_reply"] = False
                flags_fix["suppress_writer"] = False
                state["flags"] = flags_fix
                # 저장 없음(빈 요약 저장 방지)
                return {"messages": messages, "task_history": tasks, "qa_direct_reply": False}

            allow_web = not bool(getattr(config.CFG, "SKIP_WEB_SEARCH", False))
            if allow_web and not has_pending(tasks, "web_search_agent"):
                tasks.append(Task(agent="web_search_agent", done=False, description="fallback: direct_qa_missing → rag_update:auto", done_at=""))
                logger.info("[COMMUNICATOR][fallback] scheduled web_search_agent")
            elif not has_pending(tasks, "vector_search_agent"):
                tasks.append(Task(agent="vector_search_agent", done=False, description="fallback: direct_qa_missing → retry", done_at=""))
                logger.info("[COMMUNICATOR][fallback] scheduled vector_search_agent")
            # 커뮤니케이터 태스크 종료
            pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
            if pending:
                pending.done = True; pending.done_at = _now_str()
            state["task_history"] = tasks
            # 플래그 정리
            flags_fix = dict(state.get("flags") or {})
            flags_fix["qa_direct_reply"] = False
            flags_fix["suppress_writer"] = False
            state["flags"] = flags_fix
            # 저장 없음(빈 요약 저장 방지)
            return {"messages": messages, "task_history": tasks, "qa_direct_reply": False}


    # 최소 모드
    if recent:
        messages.append(AIMessage(content="[Communicator] 최신 진행상황만 간단히 안내합니다. 자세한 내용은 대시보드 로그를 참고하세요."))
        if pending:
            pending.done = True; pending.done_at = _now_str()
        _save_last_ai_if_any(state, messages)
        return {"messages": messages, "task_history": tasks}

    # ✅ 일반 communicator 생성
    # Direct QA 모드면 이미 text_buf/messages를 준비했으니 LLM 생성은 건너뛴다.
    if direct_qa_mode:
        # 아래 SAVE HOOK(628+)로 그대로 내려감
        pass
    else:
        # ✅ LLM은 "진짜로 생성이 필요할 때만" 지연 초기화 (show_outline/early-return 경로에서 init 방지)
        llm = get_llm()
        communicator_prompt = get_communicator_prompt()
        system_chain = communicator_prompt | llm

        parts: list[str] = []
        for chunk in system_chain.stream({
            "messages": messages,
            "outline": fallback_outline,
            "doc_label": "보고서" if config.CFG.DOC_MODE == "report" else "책",
            "topic_title": state.get("topic_title") or "",
        }):
            # chunk.content가 비문자/None일 수 있어 _to_text로 안전 변환
            c = getattr(chunk, "content", None)
            parts.append(_to_text(c))

        # 개선안: 바로 앞줄 중복만 제거
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
        if not just_wrote and (text_buf or "").strip():
            # §12-13-4: off-topic QA 가드(§12-13-1)가 routing한 응답도
            # qa/ 서브디렉터리로 분리 저장. desc 기반 1차 추론 + flag 2차 확인.
            _qa_save = bool(
                (desc or "").startswith("off_topic:")
                or (state.get("flags") or {}).get("qa_direct_reply")
                or state.get("qa_direct_reply")
            )
            _safe_save_report(state, content_hint=text_buf, qa_mode=_qa_save)
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
                content_text = _to_text(m.content)
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
