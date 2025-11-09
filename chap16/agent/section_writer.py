from __future__ import annotations
import sys, re, os
from os import path
from pathlib import Path
from typing import Tuple, Any, Dict, cast

import logging
logger = logging.getLogger(__name__)

from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage
import core.config as config
from core.paths import current_path, now_str as _now_str
from core.state_types import State, Flags
from core.models import Task
from utils.sanitize import sanitize_state
from utils.refs import attach_auto_citations, refs_preview_text as _refs_preview_text, facts_block as _facts_block
from prompts import get_section_writer_prompt
from content_utils import save_md_draft
from utils.outline import get_topic_outline_text, next_unwritten_title
from utils.tasks import get_last_write_target, has_pending
from utils.text_utils import section_slugify
from core.llm import get_llm


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (타입/런타임 안전 변환)
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

# ─────────────────────────────────────────────────────────────────────────────
# Config helpers (env → CFG → module default)  ※ reload_config() 반영
# ─────────────────────────────────────────────────────────────────────────────
def _cfg_str(name: str, default: str = "") -> str:
    try:
        v = getattr(config.CFG, name, None)
        if v is None:
            v = getattr(config, name, None)
    except Exception:
        v = None
    if v is None:
        v = os.getenv(name, default)
    return str(v) if v is not None else default

def _cfg_int(name: str, default: int = 0) -> int:
    s = _cfg_str(name, str(default))
    try:
        return int(str(s).strip())
    except Exception:
        return default

def _cfg_bool(name: str, default: bool = False) -> bool:
    s = _cfg_str(name, "1" if default else "0").strip().lower()
    return s in {"1","true","yes","y","on"}

def _doc_mode() -> str:
    return (_cfg_str("DOC_MODE", "report") or "report").lower()



# ─────────────────────────────────────────────────────────────────────────────
# Title resolver
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_title(state: State, outline_text: str | None) -> Tuple[str | None, bool]:
    """
    섹션 제목 결정 순서:
      1) flags.requested_write_title (잠금 우선)
      2) get_last_write_target(messages, tasks)
      3) next_unwritten_title(outline_text, ...)
    returns: (title, from_lock)
    """
    try:
        f = state.get("flags") or {}
        if bool(f.get("pending_write_title")):
            req = _as_str(f.get("requested_write_title")).strip()
            if req:
                return req, True
    except Exception:
        pass

    messages = state.get("messages", []) or []
    tasks = state.get("task_history", []) or []
    title = (
        get_last_write_target(messages, tasks)
        or next_unwritten_title(
            outline_text or "",
            mode="report",
            root_dir=str(current_path),            # ✅ str로 통일
            topic_slug=_as_str(state.get("topic_slug")) or None,
        )
    )
    return title, False


def _guess_total_sections(outline_text: str, fallback: int = 8) -> int:
    """아웃라인으로 총 섹션 수 추정."""
    if not outline_text:
        return fallback
    lines = [ln.rstrip() for ln in outline_text.splitlines()]

    # 1) H2 섹션 헤더
    h2 = [ln for ln in lines if re.match(r"^\s*##\s+\S", ln)]
    if h2:
        return len(h2)
    # 2) 체크박스 항목
    checks = [ln for ln in lines if re.match(r"^\s*-\s*\[(?: |x|X)\]\s+\S", ln)]
    if checks:
        return len(checks)
    # 3) 일반 불릿
    bullets = [ln for ln in lines if re.match(r"^\s*[-*+]\s+\S", ln)]
    if len(bullets) >= 3:
        return len(bullets)
    return fallback


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def section_writer(state: State):
    llm = get_llm()

    if _doc_mode() != "report":
        logger.info("[SECTION WRITER] Skipped: DOC_MODE=%s (expected 'report')", _doc_mode())
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}

    logger.info("============ SECTION WRITER ============")

    state = cast(State, sanitize_state(state))
    tasks = list(state.get("task_history", []) or [])
    messages = list(state.get("messages", []) or [])

    pending = next(
        (t for t in reversed(tasks) if (not getattr(t, "done", False)) and getattr(t, "agent", "") == "section_writer"),
        None
    )

    outline_text = get_topic_outline_text(state)
    if not (outline_text or "").strip():
        default_outline = "outline_book.md" if _doc_mode() == "book" else "outline_report.md"
        fname = state.get("outline_fname") or default_outline
        if not has_pending(tasks, "content_strategist", prefix="create_outline"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(content=f"[Section Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
            pending.description = pending.description or "write: (no-outline)"
        logger.info("[SECTION WRITER] outline missing → scheduled content_strategist (%s)", fname)
        return {"messages": messages, "task_history": tasks}

    target_title, came_from_lock = _resolve_title(state, outline_text)
    if not target_title:
        messages.append(AIMessage(content="[Section Writer] 모든 섹션 초안이 이미 작성되었습니다."))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
            pending.description = pending.description or "write: (all-done)"
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="모든 섹션이 작성됨: 진행상황 보고", done_at=""))
        logger.info("[SECTION WRITER] nothing left to write → handoff to communicator")
        return {"messages": messages, "task_history": tasks}

    logger.info("[SECTION WRITER] target section: %s", target_title)

    # ---- 컨텍스트 구성 (레퍼런스 + 사실 블록) ----
    ref_text = _refs_preview_text(state) + _facts_block(state)

    # ---- LLM 초안 ----
    chain = get_section_writer_prompt() | llm | StrOutputParser()
    gathered = chain.invoke({
        "target_title": target_title,
        "outline": outline_text,
        "references": ref_text,
        "messages": messages,
        "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
    })
    logger.debug("[SECTION WRITER] draft length=%s chars", len(gathered or ""))

    # ---- 자동 각주 ----
    if _cfg_bool("AUTO_FOOTNOTE", False):
        try:
            gathered = attach_auto_citations(gathered, state)
        except Exception as e:
            logger.warning("[SECTION WRITER] auto-citation 실패: %s", e)

    # ---- Q&A 모드 판별 ----
    is_qa_mode = _as_str(target_title).strip().lower().startswith("q&a:")

    # ---- 저장 시도 ----
    out_path: str | None = None
    slug = _as_str(state.get("topic_slug")) or "default"
    out_dir = path.join(str(current_path), "content", slug)

    if not is_qa_mode:
        try:
            out_path = save_md_draft(
                target_title, gathered, mode="report",
                root_dir=str(current_path), topic_slug=slug
            )
            if not out_path or not path.isfile(out_path):
                raise RuntimeError("save_md_draft returned empty or file not found")
            logger.info("[SECTION WRITER] saved via save_md_draft → %s", out_path)
        except Exception as e:
            try:
                out_dir_p = Path(out_dir)
                out_dir_p.mkdir(parents=True, exist_ok=True)
                fname = f"{section_slugify(target_title)}.md"
                out_path_p = out_dir_p / fname
                with open(out_path_p, "w", encoding="utf-8") as fp:
                    fp.write(str(gathered or ""))
                out_path = str(out_path_p)
                logger.warning("[SECTION WRITER fallback] saved → %s  (reason: %s)", out_path, e)
            except Exception as e2:
                logger.exception("[SECTION WRITER] failed to save draft (both primary and fallback): %s", e2)

        state["last_saved_path"] = out_path or ""
        messages.append(AIMessage(content=f"[Section Writer] '{target_title}' 초안 저장 완료 → {out_path or '(save failed)'}"))

        # writer-lock 해제(요청 제목과 일치할 때만)
        try:
            if came_from_lock:
                flags_map = dict(cast(Dict[str, Any], state.get("flags") or {}))
                req = _as_str(flags_map.get("requested_write_title")).strip()
                if req and (req == _as_str(target_title).strip()):
                    flags_map.pop("pending_write_title", None)
                    flags_map.pop("requested_write_title", None)
                    flags_map.pop("suppress_vector_qa", None)
                    state["flags"] = cast(Flags, flags_map)
                    logger.debug("[Section Writer] cleared writer lock: %s", target_title)
        except Exception as _e:
            logger.debug("[Section Writer] writer lock clear skipped: %s", _e)

    else:
        logger.info("[SECTION WRITER] Q&A Mode detected. Skipping file save.")
        messages.append(AIMessage(content=gathered))
        try:
            if came_from_lock:
                flags_map2 = dict(cast(Dict[str, Any], state.get("flags") or {}))
                req = _as_str(flags_map2.get("requested_write_title")).strip()
                if req and (req == _as_str(target_title).strip()):
                    flags_map2.pop("pending_write_title", None)
                    flags_map2.pop("requested_write_title", None)
                    flags_map2.pop("suppress_vector_qa", None)
                    state["flags"] = cast(Flags, flags_map2)
                    logger.debug("[Section Writer][QA] cleared writer lock: %s", target_title)
        except Exception as _e:
            logger.debug("[Section Writer][QA] writer lock clear skipped: %s", _e)

    # ---- 진행률 플래그 업데이트 ----
    try:
        # 진행률 계산은 여기서 한 번만 타입 주석을 사용해 정의
        f_raw: Dict[str, Any] = dict(cast(Dict[str, Any], state.get("flags") or {}))
        seen_raw = _as_str(f_raw.get("sections_seen"))
        seen: set[str] = set(s.strip() for s in seen_raw.split(",") if s.strip())
        key = _as_str(target_title).strip()

        # CFG 일원화: 기본 섹션 수 (런타임 반영)
        total_default = _as_int(_cfg_int("SECTIONS_TOTAL_DEFAULT", 8), 8)
        guessed_total = _as_int(_guess_total_sections(outline_text, fallback=total_default), total_default)

        sections_done = _as_int(f_raw.get("sections_done"), 0)
        if key and key not in seen:
            sections_done += 1
            seen.add(key)

        sections_total = _as_int(f_raw.get("sections_total"), 0) or guessed_total

        f_raw["sections_done"] = sections_done
        f_raw["sections_total"] = sections_total
        f_raw["sections_seen"] = ",".join(sorted(seen))

        state["flags"] = cast(Flags, f_raw)
        logger.info("[Section Writer] 진행률: %d / %d", sections_done, sections_total)
    except Exception as e:
        logger.debug("[SECTION WRITER] progress flag update skipped: %s", e)

    # ---- 콘솔 에코(옵션, CFG 제어) ----
    if _cfg_bool("ECHO_SECTIONS", False) or _cfg_bool("ECHO_CHAPTERS", False):
        try:
            box_title = ("Q&A ANSWER: " if is_qa_mode else "SECTION DRAFT: ") + _as_str(target_title)
            src_tag = "(Answer Only)" if is_qa_mode else f"saved → {out_path or '(save failed)'}"
            hdr_len = max(len(box_title), len(src_tag), 24)
            hdr_line = "=" * hdr_len

            sys.stdout.write("\n" + hdr_line + "\n")
            sys.stdout.write(box_title + "\n")
            if not is_qa_mode:
                sys.stdout.write(src_tag + "\n")
            else:
                sys.stdout.write("=" * len(box_title) + "\n")
            sys.stdout.write(hdr_line + "\n\n")
            sys.stdout.write((gathered or "").rstrip() + "\n")
            sys.stdout.write(hdr_line + "\n")
            sys.stdout.flush()
        except Exception as _e:
            logger.debug("[Section Writer] echo failed: %s", _e)

    # ---- 태스크 완료/후속 예약 ----
    if pending:
        pending.done = True
        pending.done_at = _now_str()
        pending.description = pending.description or f"write: {target_title}"

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
