from __future__ import annotations
from typing import Any, Dict, cast
import sys, re
from os import path, makedirs

from utils.tasks import HumanMessage, AIMessage
from langchain_core.output_parsers.string import StrOutputParser

import logging
logger = logging.getLogger(__name__)

import core.config as config
from core.paths import current_path, now_str as _now_str, outline_base_dir
from core.state_types import State, Flags
from core.models import Task, AgentName
from utils.sanitize import sanitize_state
from typing import cast
from core.state_types import State

from utils.refs import attach_auto_citations, refs_preview_text as _refs_preview_text, facts_block as _facts_block
from prompts import get_chapter_writer_prompt
from content_utils import save_md_draft
from utils.outline import next_unwritten_title, get_topic_outline_text
from rag_expression import is_outline_creation
from utils.tasks import has_pending, get_last_write_target
from core.llm import get_llm


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _as_str(x: Any, default: str = "") -> str:
    return x if isinstance(x, str) else default

def _as_int(x: Any, default: int = 0) -> int:
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return int(x)
    if isinstance(x, str):
        s = x.strip()
        if s.lstrip("+-").isdigit():
            try:
                return int(s)
            except Exception:
                return default
    return default

def _safe_slug(s: str) -> str:
    """폴백 저장에 쓰는 간단 슬러그."""
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    return s[:120] or "chapter"


def _guess_total_chapters(outline_text: str, fallback: int) -> int:
    """
    아웃라인에서 '챕터 수'를 대략 추정:
    - Markdown heading(예: '^# ' 또는 '^## ') 개수
    - 또는 불릿(예: '^- ' '* ' '+ ') 개수
    둘 다 없으면 fallback 반환.
    """
    if not outline_text:
        return fallback
    lines = [ln.rstrip() for ln in outline_text.splitlines()]
    # 1) 헤더 기반
    heads = [ln for ln in lines if re.match(r"^\s*#{1,2}\s+\S", ln)]
    if len(heads) >= 2:
        return len(heads)
    # 2) 불릿 기반
    bullets = [ln for ln in lines if re.match(r"^\s*[-*+]\s+\S", ln)]
    if len(bullets) >= 3:
        return len(bullets)
    return fallback


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def chapter_writer(state: State):
    """DOC_MODE == 'book'에서 챕터 초안을 생성한다."""
    if config.CFG.DOC_MODE != "book":
        logger.info("[CHAPTER WRITER] Skipped: DOC_MODE=%s (expected 'book')", config.CFG.DOC_MODE)
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}

    logger.info("============ CHAPTER WRITER ============")
    llm = get_llm()
    state = cast(State, sanitize_state(state))

    tasks = list(state.get("task_history", []) or [])
    messages = list(state.get("messages", []) or [])

    # 펜딩 태스크 핸들(있으면)
    pending = next(
        (t for t in reversed(tasks)
         if (not getattr(t, "done", False)) and getattr(t, "agent", "") == "chapter_writer"),
        None
    )
    if pending is None:
        logger.warning("[CHAPTER WRITER] pending 'chapter_writer' task가 없습니다. edge pass (계속 진행).")

    # 사용자의 최근 입력이 목차 생성 의도면 위임
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if last_human and isinstance(last_human.content, str) and is_outline_creation(last_human.content):
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        default_outline = "outline_book.md" if config.CFG.DOC_MODE == "book" else "outline_report.md"
        fname = state.get("outline_fname") or default_outline
        if not has_pending(tasks, cast(AgentName, "content_strategist")):
            tasks.append(Task(agent=cast(AgentName, "content_strategist"),
                              done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(content="[Chapter Writer] Outline 요청 감지 → content_strategist로 위임"))
        logger.info("[CHAPTER WRITER] outline creation intent detected → scheduled content_strategist (%s)", fname)
        return {"messages": messages, "task_history": tasks}

    # 아웃라인 필수
    outline_text = get_topic_outline_text(state)
    if not (outline_text or "").strip():
        default_outline = "outline_book.md" if config.CFG.DOC_MODE == "book" else "outline_report.md"
        fname = state.get("outline_fname") or default_outline
        if not has_pending(tasks, cast(AgentName, "content_strategist")):
            tasks.append(Task(agent=cast(AgentName, "content_strategist"),
                              done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(content=f"[Chapter Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        logger.info("[CHAPTER WRITER] outline missing → scheduled content_strategist (%s)", fname)
        return {"messages": messages, "task_history": tasks}

    # 타이틀: 마지막 write: → 다음 미작성 → '서문'
    requested = get_last_write_target(messages, tasks)
    auto_title = next_unwritten_title(
        outline_text,
        mode="book",
        root_dir=str(outline_base_dir()),            # ✅ str로 통일
        topic_slug=_as_str(state.get("topic_slug")) or None,
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
    writer_chain = get_chapter_writer_prompt() | llm | StrOutputParser()
    gathered = writer_chain.invoke(
        {
            "target_title": target_title,
            "outline": outline_text,
            "references": ref_text,
            "messages": messages,
            "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
        }
    )
    logger.debug("[CHAPTER WRITER] draft length=%s chars", len(gathered or ""))

    # 자동 각주
    if getattr(config.CFG, "AUTO_FOOTNOTE", False):
        try:
            gathered = attach_auto_citations(gathered, state)
        except Exception as e:
            logger.warning("[CHAPTER WRITER] auto-citation 실패: %s", e)

    # 저장 시도 (save_md_draft 우선, 실패 시 폴백)
    slug = _as_str(state.get("topic_slug")) or "default"
    out_dir = path.join(str(current_path), "content", slug)
    out_path: str | None = None
    try:
        out_path = save_md_draft(
            target_title,
            gathered,
            mode=config.CFG.DOC_MODE,   # ← DocMode로 일치
            root_dir=str(current_path),
            topic_slug=slug,
        )
        if not out_path or not path.isfile(out_path):
            raise RuntimeError("save_md_draft returned empty or file not found")
        logger.info("[CHAPTER WRITER] saved via save_md_draft → %s", out_path)
    except Exception as e:
        try:
            makedirs(out_dir, exist_ok=True)
            fname = f"{_safe_slug(target_title)}.md"
            out_path = path.join(out_dir, fname)
            with open(out_path, "w", encoding="utf-8") as fp:
                fp.write(gathered or "")
            logger.warning("[CHAPTER WRITER fallback] saved → %s  (reason: %s)", out_path, e)
        except Exception as e2:
            logger.exception("[CHAPTER WRITER] failed to save draft (both primary and fallback): %s", e2)

    state["last_saved_path"] = out_path or ""
    messages.append(AIMessage(content=f"[Chapter Writer] '{target_title}' 초안 작성 완료 → {out_path or '(save failed)'}"))
    if out_path:
        logger.info("[CHAPTER WRITER] draft saved → %s", out_path)

    # 진행 카운트(중복 방지)
    try:
        f_raw: Dict[str, Any] = dict(state.get("flags") or {})
        seen_raw = _as_str(f_raw.get("chapters_seen"))
        seen: set[str] = set(s.strip() for s in seen_raw.split(",") if s.strip())

        key = _as_str(target_title).strip()

        total_default = _as_int(getattr(config.CFG, "CHAPTERS_TOTAL_DEFAULT", 12), 12)
        guessed_total = _as_int(_guess_total_chapters(outline_text, fallback=total_default), total_default)

        chapters_done = _as_int(f_raw.get("chapters_done"), 0)
        if key and key not in seen:
            chapters_done += 1
            seen.add(key)

        chapters_total = _as_int(f_raw.get("chapters_total"), 0) or guessed_total

        f_raw["chapters_done"] = chapters_done
        f_raw["chapters_total"] = chapters_total
        f_raw["chapters_seen"]  = ",".join(sorted(seen))

        state["flags"] = cast(Flags, f_raw)

        logger.info("[Chapter Writer] 진행률: %d / %d", chapters_done, chapters_total)
    except Exception as _e:
        logger.debug("[Chapter Writer] progress flag update skipped: %s", _e)

    # 콘솔 에코(옵션, CFG 제어)
    if getattr(config.CFG, "ECHO_CHAPTERS", False) or getattr(config.CFG, "ECHO_SECTIONS", False):
        try:
            box_title = f"CHAPTER DRAFT: {target_title}"
            src_tag   = f"saved → {out_path or '(save failed)'}"
            hdr_line  = "=" * max(len(box_title), len(src_tag), 24)
            sys.stdout.write("\n" + hdr_line + "\n")
            sys.stdout.write(box_title + "\n")
            sys.stdout.write(src_tag + "\n")
            sys.stdout.write(hdr_line + "\n\n")
            sys.stdout.write((gathered or "").rstrip() + "\n")
            sys.stdout.write(hdr_line + "\n")
            sys.stdout.flush()
        except Exception as _e:
            logger.debug("[CHAPTER WRITER] echo failed: %s", _e)

    # 펜딩 정리 + 후속 안내
    if pending:
        pending.description = (pending.description or "") or f"write: {target_title}"
        pending.done = True
        pending.done_at = _now_str()

    if not has_pending(tasks, cast(AgentName, "communicator")):
        tasks.append(Task(agent=cast(AgentName, "communicator"),
                          done=False,
                          description=f"'{target_title}' 초안 완료 보고 및 다음 집필/수정 확인",
                          done_at=""))

    return {"messages": messages, "task_history": tasks, "last_saved_path": out_path}
