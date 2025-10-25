from __future__ import annotations
import os, sys, re
from os import path, makedirs
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


def _truthy_env(name: str) -> bool:
    """'1/true/yes/on' → True"""
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")

ECHO_SECTIONS = _truthy_env("ECHO_SECTIONS")

def _resolve_title(state: State, outline_text: str | None):
    """
    섹션 제목 결정 순서:
    1) flags.requested_write_title (잠금 우선)
    2) get_last_write_target(messages, tasks)  ← write: ... 에서 파싱
    3) next_unwritten_title(outline_text, ...)
    반환값: (title, from_lock: bool)
    """
    try:
        f = state.get("flags") or {}
        # bool 락(pending_write_title)이 켜져 있고, 요청 제목이 있으면 그것을 사용
        if bool(f.get("pending_write_title")):
            req = str(f.get("requested_write_title") or "").strip()
            if req:
                return req, True
    except Exception:
        pass

    messages = state.get("messages", []) or []
    tasks = state.get("task_history", []) or []

    # write: ... 가 있는 가장 최신 태스크/메시지에서 타이틀 파싱
    title = (
        get_last_write_target(messages, tasks)
        or next_unwritten_title(
            outline_text or "",
            mode="report",
            root_dir=current_path,
            topic_slug=state.get("topic_slug"),
        )
    )
    return title, False



def _guess_total_sections(outline_text: str, fallback: int = 8) -> int:
    """
    아웃라인에서 '총 섹션 수'를 추정:
    - 보고서 모드 가정으로 '## ' 헤더 개수 우선
    - 없으면 체크박스(- [ ], - [x]) 개수
    - 없으면 일반 불릿(-, *, +) 개수
    - 그래도 없으면 fallback(기본 8)
    """
    if not outline_text:
        return fallback
    lines = [ln.rstrip() for ln in outline_text.splitlines()]
    # 1) 섹션 헤더
    h2 = [ln for ln in lines if re.match(r"^\s*##\s+\S", ln)]
    if len(h2) >= 1:
        return len(h2)
    # 2) 체크박스 항목
    checks = [ln for ln in lines if re.match(r"^\s*-\s*\[(?: |x|X)\]\s+\S", ln)]
    if len(checks) >= 1:
        return len(checks)
    # 3) 일반 불릿
    bullets = [ln for ln in lines if re.match(r"^\s*[-*+]\s+\S", ln)]
    if len(bullets) >= 3:
        return len(bullets)
    return fallback


def section_writer(state: State):
    llm = get_llm()

    if DOC_MODE != "report":
        logger.info("[SECTION WRITER] Skipped: DOC_MODE=%s (expected 'report')", DOC_MODE)
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}

    logger.info("============ SECTION WRITER ============")

    # === [여기에 out_path 초기화 코드 추가] ===
    out_path = None  # <-- 이 위치에 추가합니다.
    # ========================================

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

    # target_title = (
    #     get_last_write_target(messages, tasks)
    #     or next_unwritten_title(outline_text, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug"))
    # )
    target_title, _came_from_lock = _resolve_title(state, outline_text)

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

    # Q&A 모드 감지: "Q&A:"로 시작하면 파일 저장을 건너뛰고 답변 출력만 준비
    IS_QA_MODE = target_title.strip().lower().startswith("q&a:")

    # 저장 시도 (save_md_draft 우선, 실패 시 폴백)
    slug = str(state.get("topic_slug") or "default")
    out_dir = path.join(current_path, "content", slug)
    out_path = None

    if not IS_QA_MODE: # Q&A 모드가 아닐 때만 파일 저장 로직 실행
        try:
            out_path = save_md_draft(
                target_title, gathered, mode="report",
                root_dir=current_path, topic_slug=slug
            )
            if not out_path or not path.isfile(out_path):
                raise RuntimeError("save_md_draft returned empty or file not found")
            logger.info("[SECTION WRITER] saved via save_md_draft → %s", out_path)
        except Exception as e:
            try:
                makedirs(out_dir, exist_ok=True)
                fname = f"{section_slugify(target_title)}.md"
                out_path = path.join(out_dir, fname)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(gathered or "")
                logger.warning("[SECTION WRITER fallback] saved → %s  (reason: %s)", out_path, e)
            except Exception as e2:
                logger.exception("[SECTION WRITER] failed to save draft (both primary and fallback): %s", e2)
                # 저장 실패여도 후속 로직은 진행

        state["last_saved_path"] = out_path or ""
        messages.append(AIMessage(content=f"[SECTION WRITER] '{target_title}' 초안 저장 완료 → {out_path or '(save failed)'}"))

        # [FIX] 잠금 해제: 요청 제목 일치 시에만 해제 (bool과 문자열 비교 금지)
        try:
            if _came_from_lock:
                ff = dict(state.get("flags") or {})
                req = str(ff.get("requested_write_title") or "").strip()
                if req and (req == str(target_title).strip()):
                    ff.pop("pending_write_title", None)
                    ff.pop("requested_write_title", None)
                    ff.pop("suppress_vector_qa", None)
                    state["flags"] = ff
                    logger.debug("[Section Writer] cleared writer lock: %s", target_title)
        except Exception as _e:
            logger.debug("[Section Writer] writer lock clear skipped: %s", _e)

    else: # Q&A 모드일 때는 파일 저장 생략
        logger.info("[SECTION WRITER] Q&A Mode detected. Skipping file save.")
        # Q&A 답변 내용을 메시지에 추가 (파일 저장 메시지 대신)
        messages.append(AIMessage(content=gathered))

        # [ADD] 잠금 해제
        # [FIX][QA] 잠금 해제: 요청 제목 일치 시에만 해제
        try:
            if _came_from_lock:
                ff = dict(state.get("flags") or {})
                req = str(ff.get("requested_write_title") or "").strip()
                if req and (req == str(target_title).strip()):
                    ff.pop("pending_write_title", None)
                    ff.pop("requested_write_title", None)
                    ff.pop("suppress_vector_qa", None)
                    state["flags"] = ff
                    logger.debug("[Section Writer][QA] cleared writer lock: %s", target_title)
        except Exception as _e:
            logger.debug("[Section Writer][QA] writer lock clear skipped: %s", _e)

    # [ADD] 진행 카운트: flags에만 저장(TypedDict 경고 회피) + 중복 카운트 방지 + 총 섹션 수 추정
    try:
        f = dict(state.get("flags") or {})
        seen_raw = (f.get("sections_seen") or "").strip()
        seen = set(filter(None, (x.strip() for x in seen_raw.split(",")))) if seen_raw else set()
        key = target_title.strip()

        # 총 섹션 수 추정(아웃라인 기반 → 없으면 ENV 또는 기본 8)
        total_default = int(os.getenv("SECTIONS_TOTAL_DEFAULT", "8"))
        guessed_total = _guess_total_sections(outline_text, fallback=total_default)

        if key not in seen:
            f["sections_done"] = int(f.get("sections_done") or 0) + 1
            seen.add(key)
            f["sections_seen"] = ",".join(sorted(seen))
        # 항상 최신 total 유지(아웃라인 변경 시 반영)
        f["sections_total"] = int(f.get("sections_total") or 0) or guessed_total

        state["flags"] = f
        logger.info("[Section Writer] 진행률: %d / %d", int(f.get("sections_done") or 0), int(f.get("sections_total") or 0))
    except Exception as e:
        logger.debug("[SECTION WRITER] progress flag update skipped: %s", e)

    # (NEW) 콘솔 에코: 저장된 섹션 초안 원문을 바로 출력 (옵션)
    # (NEW) 콘솔 에코: 저장된 섹션 초안 원문을 바로 출력 (옵션)
        # (NEW) 콘솔 에코: 저장된 섹션 초안 원문을 바로 출력 (옵션)
    if ECHO_SECTIONS:
        # 1) 선초기화(예외 발생 시 NameError 방지)
        box_title = ""
        src_tag = ""
        hdr_line = "=" * 24  # 최소 길이

        try:
            # 2) 두 변수 먼저 확정 (※ 특수공백 없이 일반 스페이스만 사용)
            if IS_QA_MODE:
                box_title = f"Q&A ANSWER: {target_title}"
                src_tag = "(Answer Only)"
            else:
                box_title = f"SECTION DRAFT: {target_title}"
                src_tag = f"saved → {out_path or '(save failed)'}"

            # 3) 헤더 길이는 상황에 따라 안전 계산
            #    (src_tag가 필요 없을 때도 대비)
            hdr_len = max(len(box_title), len(src_tag), 24)
            hdr_line = "=" * hdr_len

            if IS_QA_MODE:
                # Q&A 모드: 깔끔한 답변 텍스트만 출력
                sys.stdout.write("\n" + hdr_line + "\n")
                sys.stdout.write(box_title + "\n")
                sys.stdout.write("=" * len(box_title) + "\n\n")
                sys.stdout.write((gathered or "").strip() + "\n")
                sys.stdout.write(hdr_line + "\n")
            else:
                # 보고서 모드: 저장 경로와 함께 파일 내용 출력
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
