from __future__ import annotations
import sys, re, os, time
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
from core.events import emit_event
from core.models import Task
from utils.sanitize import sanitize_state
from utils.refs import attach_auto_citations, attach_marker_citations, build_marker_refs_map, refs_preview_text as _refs_preview_text, facts_block as _facts_block
from utils.chunk_summary import start_background_summarization
from prompts import get_section_writer_prompt
from content_utils import save_md_draft
from utils.outline import get_topic_outline_text, next_unwritten_title
from utils.tasks import get_last_write_target, has_pending
from utils.text_utils import section_slugify
from core.llm import get_llm
try:
    from tools.metrics import record_llm_call as _record_llm_call
except Exception:  # pragma: no cover
    def _record_llm_call(**_kw):  # type: ignore[no-redef]
        return None


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
    # 완료 목록: flags.completed_sections (TypedDict 충돌 회피)
    _flags = dict(cast(Dict[str, Any], state.get("flags") or {}))
    _completed = _flags.get("completed_sections") or []
    done: set[str] = {str(t).strip() for t in _completed if str(t).strip()}
    # 1) 직전 타깃 우선, 단 완료 목록이면 무시
    _last = get_last_write_target(messages, tasks)
    if _last and _last.strip() in done:
        _last = None
    title = _last or next_unwritten_title(
        outline_text or "",
        mode="report",
        root_dir=str(current_path() if callable(current_path) else current_path),
        topic_slug=_as_str(state.get("topic_slug")) or None,
        excluded_titles=done,  # 완료 목록 제외
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


_OUTLINE_H2_RE = re.compile(r"^\s*##\s+(?:(\d+)\.\s+)?(.+?)\s*$", re.M)


def _ensure_section_heading(body: str, target_title: str, outline_text: str) -> str:
    """§13-13-1: LLM 일관성 결함 우회 — outline ground truth 로 ## N. <title> 강제.

    LLM 출력 첫 라인이 정규 ## N. <title> 가 아닐 때만 정규화.
    outline 매칭 실패 시 번호 없는 ## <title> 로 fallback (현 _ensure_heading 동작 유지).

    §13-13-4-1: target_title 형식 흡수 — 평문/번호prefix/##prefix 모두 정규화 가능.
    docx export 경로 (_read_all_sections, _read_section_file) 가 outline 한 줄
    (`## N. <title>`) 을 그대로 넘기는 호출 패턴을 지원.
    """
    body = (body or "").lstrip()
    _t = (target_title or "").strip()
    _t = re.sub(r"^\s*#+\s*", "", _t)
    target_clean = re.sub(r"^\s*\d+[.)]\s*", "", _t).strip()
    if not target_clean:
        return body

    expected_num = ""
    for m in _OUTLINE_H2_RE.finditer(outline_text or ""):
        num = (m.group(1) or "").strip()
        title = (m.group(2) or "").strip()
        if title == target_clean:
            expected_num = num
            break

    expected_heading = (
        f"## {expected_num}. {target_clean}" if expected_num
        else f"## {target_clean}"
    )

    first_line = body.split("\n", 1)[0].strip() if body else ""
    if first_line == expected_heading:
        return body
    if first_line.startswith("##"):
        rest = body.split("\n", 1)[1] if "\n" in body else ""
        return f"{expected_heading}\n{rest}"
    return f"{expected_heading}\n\n{body}"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def section_writer(state: State):
    llm = get_llm()

    if _doc_mode() != "report":
        logger.info("[SECTION WRITER] Skipped: DOC_MODE=%s (expected 'report')", _doc_mode())
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}

    logger.info("============ SECTION WRITER ============")
    emit_event("섹션 본문 작성")

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
        # [§research-1 R36] (E)안 — 아웃라인을 이 자리에서 확보한다.
        #   종전에는 content_strategist Task 만 예약하고 return 했고, 그 노드의 출구가
        #   graph.py:125 고정 엣지(→ communicator → END) 라 writer 로 돌아오지 못했다(R34 §5-b).
        #   노드를 통째로 호출한다 — 시그니처가 (state) 단일 인자다(R35 §2-a).
        #   반환 dict 는 버린다: tasks/messages 는 얕은 복사라 append 만 유실되고
        #   state 대입·Task 변형·파일은 공유 객체·디스크로 전파된다(R36 §1-b).
        #   순환 import 없음(content_strategist 의 import 에 agent.* 0건, R35 §1-b) —
        #   모듈 적재 순서를 바꾸지 않도록 지역 import 으로 둔다.
        from agent.content_strategist import content_strategist as _r36_build_outline
        _r36_build_outline(state)
        #   save_outline 은 디스크에만 쓴다(utils/outline.py:260) — 재읽기가 필요하다(R36 §3-a).
        outline_text = get_topic_outline_text(state)
        if not (outline_text or "").strip():
            logger.info("[SECTION WRITER] outline missing → build failed (%s)", fname)
            # [§research-1 R36-b] 실패 경로에만 Task 종료를 복원한다(구 코드 :217-220 과 동일).
            #   빼두면 writer Task 가 미완료로 남고, tail_task_router:362 가 참이 돼
            #   :370 이 section_writer 를 되돌려 무한 루프가 된다(refs.docs>0 일 때).
            #   본문 경로는 무접촉 — 거기는 :490-493 이 같은 객체로 종료 처리한다.
            if pending:
                pending.done = True
                pending.done_at = _now_str()
                pending.description = pending.description or "write: (no-outline)"
            return {"messages": messages, "task_history": tasks}

    target_title, came_from_lock = _resolve_title(state, outline_text)

    # ── SAFETY GUARD: 이미 완료된 섹션이면 다시 쓰지 않기 ─────────────────────
    try:
        flags_now: Dict[str, Any] = dict(cast(Dict[str, Any], state.get("flags") or {}))
        completed_now = {
            str(t).strip()
            for t in (flags_now.get("completed_sections") or [])
            if str(t).strip()
        }
        if target_title and target_title.strip() in completed_now:
            logger.info(
                "[SECTION WRITER] target already in completed_sections, skip rewrite: %s",
                target_title,
            )
            if pending:
                pending.done = True
                pending.done_at = _now_str()
                pending.description = pending.description or f"write: (already-completed) {target_title}"
            if not has_pending(tasks, "communicator"):
                tasks.append(
                    Task(
                        agent="communicator",
                        done=False,
                        description=f"'{target_title}' 섹션은 이미 완료됨: 진행상황 보고 및 다음 섹션 확인",
                        done_at="",
                    )
                )
            return {
                "messages": messages,
                "task_history": tasks,
            }
    except Exception as _e:
        logger.debug("[SECTION WRITER] completed_sections safety guard skipped: %s", _e)

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
    # §13: numbered=True → LLM 컨텍스트에 [N] 인덱스 부여, 본문 [[N]] 마커 인용 가능.
    ref_text = _refs_preview_text(state, numbered=True) + _facts_block(state)

    # ---- LLM 초안 ----
    chain = get_section_writer_prompt() | llm | StrOutputParser()
    _llm_provider = (_cfg_str("LLM_PROVIDER", "") or "").strip().lower()
    try:
        _llm_model = str(getattr(llm, "model_name", "") or getattr(llm, "model", "") or type(llm).__name__)
    except Exception:
        _llm_model = type(llm).__name__
    _t0 = time.monotonic()
    try:
        gathered = chain.invoke({
            "target_title": target_title,
            "outline": outline_text,
            "references": ref_text,
            "messages": messages,
            "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
        })
    except Exception as _llm_err:
        _lat_fail = time.monotonic() - _t0
        try:
            _record_llm_call(
                provider=_llm_provider, model=_llm_model, latency_s=_lat_fail,
                success=False, error_class=type(_llm_err).__name__,
                section_title=target_title or "",
            )
        except Exception:
            pass
        raise
    _lat_ok = time.monotonic() - _t0
    try:
        # 평균 35~50초 대비 비정상적으로 길면 langchain 내부 retry 발생 의심.
        # 임계값 90초는 §12-13-6 발견 케이스(2분 49초)를 retry로 식별하기 위한 보수적 기준.
        _hint = "slow" if _lat_ok > 90.0 else ""
        _record_llm_call(
            provider=_llm_provider, model=_llm_model, latency_s=_lat_ok,
            success=True, section_title=target_title or "", retry_hint=_hint,
        )
    except Exception:
        pass
    logger.debug("[SECTION WRITER] draft length=%s chars", len(gathered or ""))

    # ---- §13: 마커 기반 footer (본문 [[N]] ↔ refs 1:1) ----
    # AUTO_FOOTNOTE 가드와 무관하게 항상 시도. 본문에 마커 없으면 변경 없음.
    # marker → chunk 메타 맵은 attach 가 본문을 mutate 하기 *전* 의 원본 gathered 에서 추출.
    marker_refs_map: dict = {}
    try:
        marker_refs_map = build_marker_refs_map(gathered, state)
    except Exception as e:
        logger.warning("[SECTION WRITER] marker refs map 생성 실패: %s", e)
        marker_refs_map = {}
    try:
        gathered = attach_marker_citations(gathered, state)
    except Exception as e:
        logger.warning("[SECTION WRITER] marker-citation 실패: %s", e)

    # ---- (legacy) AUTO_FOOTNOTE: quant/domain/footer 모드 (이미 footer 있으면 skip) ----
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
    # current_path는 함수/값 모두 허용 → 문자열로 일원화
    _proj_root = str(current_path() if callable(current_path) else current_path)
    out_dir = path.join(_proj_root, "content", slug)

    if not is_qa_mode:
        gathered = _ensure_section_heading(gathered, target_title, outline_text)
        try:
            out_path = save_md_draft(
                target_title, gathered, mode="report",
                root_dir=_proj_root, topic_slug=slug
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

        # 사이드카 .refs.json: marker → chunk 메타 (프런트 SourcePanel 의 'chunk 원본' 표시용)
        # §12-22: 저장 직후 백그라운드 daemon thread 가 요약(summary 필드) 점진 추가.
        if out_path and marker_refs_map:
            try:
                import json as _json
                sidecar = Path(out_path).with_suffix(".refs.json")
                sidecar.write_text(
                    _json.dumps(marker_refs_map, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info("[SECTION WRITER] refs sidecar saved → %s (markers=%d)", sidecar, len(marker_refs_map))
                try:
                    start_background_summarization(sidecar, gathered, marker_refs_map)
                except Exception as _e_bg:
                    logger.warning("[SECTION WRITER] background summarization 시작 실패: %s", _e_bg)
            except Exception as _e_side:
                logger.warning("[SECTION WRITER] refs sidecar write failed: %s", _e_side)

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

    # ---- 섹션 작성 완료 후 후처리: 완료 목록(flags) 반영 + 재선택 방지 + 락 해제 ----
    try:
        logger.info("[Section Writer] 섹션 작성 완료: %s", target_title)
        # flags 사본
        _flags: Dict[str, Any] = dict(cast(Dict[str, Any], state.get("flags") or {}))
        # 1) 완료 목록(flags.completed_sections) 반영 (중복 방지)
        completed = list(_flags.get("completed_sections") or [])
        if target_title and target_title not in completed:
            completed.append(target_title)
        _flags["completed_sections"] = completed
        # 2) 같은 섹션 재선택 방지: writer_target 초기화
        _flags.pop("writer_target", None)
        # 3) writer 락 해제 보강
        _flags.pop("writer_lock", None)
        state["flags"] = cast(Flags, _flags)
    except Exception as _e:
        logger.debug("[Section Writer] post-completion update skipped: %s", _e)


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

    # flags/진행률/완료 목록이 실제 state에 반영되도록 함께 반환
    flags_out: Flags = cast(Flags, state.get("flags") or {})

    return {
        "messages": messages,
        "task_history": tasks,
        "last_saved_path": out_path,
        "flags": flags_out,
    }
