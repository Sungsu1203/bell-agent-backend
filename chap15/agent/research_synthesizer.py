from __future__ import annotations
from typing import Mapping, Any, Optional, MutableMapping, cast
from pathlib import Path
import os

import logging
logger = logging.getLogger(__name__)

from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage, has_pending
from utils.sanitize import sanitize_state, as_int
from utils.text_utils import clean_snip as _clean_snip
from utils.outline import get_topic_outline_text
from prompts import get_research_synthesizer_prompt
from core.state_types import State
from core.config import DOC_MODE
from core.paths import current_path, now_str as _now_str
from utils.tasks import schedule_writer_if_needed
from utils.rag_utils import score_doc as _score_doc

from core.llm import get_llm


def research_synthesizer(state: State):
    logger.info("============ RESEARCH SYNTHESIZER ============")
    llm = get_llm()
    state = sanitize_state(state)

    # [ANCHOR: LOOP_FLAG_ON_ENTRY]
    state["research_loop_active"] = True

    # 안전한 기본값들
    msgs = list(state.get("messages") or [])
    tasks = list(state.get("task_history") or [])

    rnd = as_int(state, "research_round", 0)
    max_iter = max(1, as_int(state, "iteration_count", 1))
    next_round = min(rnd + 1, max_iter)

    refs = state.get("references") or {"queries": [], "docs": []}
    docs = list(refs.get("docs") or [])

    # ---- 신규 URL 수 카운트 추출 ----
    def _pick_round_new_urls(state_dict: Mapping[str, Any]) -> Optional[int]:
        for key in ("round_added_urls", "new_url_count_round", "round_new_urls", "new_urls", "new_url_count"):
            value = state_dict.get(key)
            if value is None:
                continue
            s = str(value).strip()
            if not s:
                continue
            try:
                return max(0, int(s))
            except Exception:
                continue
        return None

    # [ANCHOR: ROUND_URL_KEYS_SYNC]
    round_new_urls = _pick_round_new_urls(state)

    if round_new_urls is None:
        cand = state.get("round_new_urls", state.get("new_url_count_round", state.get("new_url_count")))
        if cand is None or str(cand).strip() == "":
            round_new_urls = 0
            logger.info("[SYNTH] round=%s/%s, round_new_urls=? (missing) → assume 0", rnd + 1, max_iter)
            msgs.append(AIMessage(content="[Research Synthesizer] 이번 라운드의 신규 URL 수가 전달되지 않아 0으로 간주합니다."))
        else:
            try:
                round_new_urls = max(0, int(str(cand)))
                logger.info("[SYNTH] round=%s/%s, round_new_urls(recovered)=%s", rnd + 1, max_iter, round_new_urls)
            except Exception:
                round_new_urls = 0
                logger.info("[SYNTH] round=%s/%s, round_new_urls parse fail → assume 0", rnd + 1, max_iter)
                msgs.append(AIMessage(content="[Research Synthesizer] 신규 URL 수 파싱 실패로 0으로 간주합니다."))
    else:
        try:
            round_new_urls = max(0, int(str(round_new_urls)))
        except Exception:
            round_new_urls = 0

    # 동기화
    state["new_url_count"] = round_new_urls
    state["new_url_count_round"] = round_new_urls
    state["round_new_urls"] = round_new_urls

    # 디버그 힌트
    flags = state.setdefault("flags", {})
    flags.setdefault("debug", {})["synth_round_new_urls"] = round_new_urls

    logger.debug("[SYNTH] round=%s/%s, round_new_urls=%s", rnd + 1, max_iter, round_new_urls)

    # ---- 조기중단 파라미터 ----
    def _as_int_env_first(env_key: str, state_key: str, default: int) -> int:
        v = os.getenv(env_key)
        if v is not None and str(v).strip() != "":
            try:
                return int(v)
            except Exception:
                pass
        return as_int(state, state_key, default)

    halt_threshold = _as_int_env_first("RESEARCH_HALT_THRESHOLD", "research_halt_threshold", 0)
    prev_streak = as_int(state, "no_new_url_streak", 0)

    if round_new_urls is None:
        streak = prev_streak
    elif round_new_urls <= halt_threshold:
        streak = prev_streak + 1
    else:
        streak = 0

    state["no_new_url_streak"] = streak
    logger.debug("[SYNTH] no_new_url_streak=%s (round_new_urls=%s, threshold=%s)", streak, round_new_urls, halt_threshold)

    # ---- 컨텍스트 스니펫 ----
    if docs:
        scored = sorted(docs, key=_score_doc, reverse=True)[:20]
        brief, seen = [], set()
        for d in scored:
            meta = getattr(d, "metadata", None)
            if meta is None and isinstance(d, dict):
                meta = d.get("metadata", {})
            meta = meta or {}

            page_content = getattr(d, "page_content", None)
            if page_content is None and isinstance(d, dict):
                page_content = d.get("page_content", "")
            page_content = page_content or ""

            src = meta.get("source") or meta.get("url") or "unknown"
            txt = _clean_snip(page_content, 420)
            key = (src, txt)
            if key in seen:
                continue
            seen.add(key)
            brief.append(f"- [{src}] {txt}")
        snippets = "\n".join(brief) if brief else "(자료 부족)"
    else:
        snippets = "(자료 부족)"

    # ---- LLM 합성 ----
    synth_prompt = get_research_synthesizer_prompt()
    try:
        findings = (synth_prompt | llm | StrOutputParser()).invoke({"snippets": snippets})
    except Exception as e:
        findings = f"""[Fallback Summary]
LLM 호출 실패로 간략 요약을 제공합니다.
에러: {type(e).__name__}: {e}
---
{snippets[:2000]}
"""

    # ---- 결과 저장 ----
    topic_slug = state.get("topic_slug") or "default"
    outdir = os.path.join(current_path, "research", topic_slug)
    try:
        Path(outdir).mkdir(parents=True, exist_ok=True)
        out_path = os.path.join(outdir, f"round-{rnd + 1:02d}-findings.md")
        Path(out_path).write_text(findings, encoding="utf-8")
        saved_msg = f"[Research Synthesizer] Round {rnd + 1} findings saved → {out_path}"
        logger.info(saved_msg)
    except Exception as e:
        out_path = None
        saved_msg = f"[Research Synthesizer] Round {rnd + 1} findings generated (file save failed: {e})"
        logger.warning(saved_msg)

    msgs.append(AIMessage(content=saved_msg))

    findings_md = list(state.get("findings_md") or [])
    if out_path:
        findings_md.append(out_path)

    # ── 결과 저장 직후 ~ 다음 단계 결정 직전
    if os.getenv("AUTO_WRITE_DURING_RESEARCH", "0") == "1":
        outline_text = get_topic_outline_text(state)
        schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            tasks=tasks,
            messages=msgs,
            outline_text=outline_text or "",
            allow_during_research=True,
            debug=True,
        )

    # ---- 다음 단계 결정 ----
    min_rounds = _as_int_env_first("RESEARCH_MIN_ROUNDS", "research_min_rounds", 1)
    max_no_new = _as_int_env_first("RESEARCH_MAX_NO_NEW_ROUNDS", "research_max_no_new_rounds", 1)
    max_no_new = max(1, max_no_new)

    streak_now = as_int(state, "no_new_url_streak", 0)
    should_halt = ((rnd + 1) >= max(1, min_rounds)) and (streak_now >= max_no_new)

    logger.info(
        "[SYNTH] should_halt=%s (round=%s, streak=%s/%s, min_rounds=%s, halt_threshold=%s)",
        should_halt, rnd + 1, streak_now, max_no_new, min_rounds, halt_threshold
    )

    # ---- 연구 메타 저장(옵션) ----
    try:
        topic = topic_slug
        res_dir = os.path.join(current_path, "resources", topic)
        Path(res_dir).mkdir(parents=True, exist_ok=True)
        import json  # 지역 임포트(의도 유지)
        meta = {
            "round": rnd + 1,
            "timestamp": _now_str(),
            "round_new_urls": round_new_urls,
            "no_new_url_streak": state.get("no_new_url_streak", 0),
            "min_rounds": min_rounds,
            "max_no_new": max_no_new,
            "halt_threshold": halt_threshold,
            "halted": should_halt,
            "findings_path": out_path,
        }
        meta_path = os.path.join(res_dir, f"round-{rnd + 1:02d}-meta.json")
        Path(meta_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as _e:
        msgs.append(AIMessage(content=f"[Research Synthesizer] meta save skipped: {type(_e).__name__}: {_e}"))

    if should_halt:
        # 연구 루프 종료
        state["research_loop_active"] = False
        msgs.append(AIMessage(content=f"[Research Synthesizer] HALT: no_new_url_streak={streak_now} (≥ {max_no_new})"))

        # writer 예약은 1회만
        outline_text = get_topic_outline_text(state)
        schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            tasks=tasks,
            messages=msgs,
            outline_text=outline_text or "",
            allow_during_research=True,
            debug=True,
        )
        msgs.append(AIMessage(content="[Research Synthesizer] 연구 종료 → Writer 예약 및 집필 단계로 전환"))
    else:
        # 라운드가 남아있으면 연구 계속
        if next_round < max_iter:
            state["research_loop_active"] = True
            try:
                already_planning = has_pending(tasks, "research_planner", prefix="plan:")
            except Exception:
                already_planning = False
            if not already_planning:
                from core.models import Task  # 순환 방지
                tasks.append(Task(agent="research_planner", done=False, description="plan_next", done_at=""))
            msgs.append(AIMessage(content=f"[Research Synthesizer] 연구 계속: 다음 라운드로 진행 (next_round={next_round}/{max_iter})"))
        else:
            # 최대 라운드 소진 → 종료 후 Writer 전환
            state["research_loop_active"] = False
            outline_text = get_topic_outline_text(state)
            schedule_writer_if_needed(
                cast(MutableMapping[str, Any], state),
                tasks=tasks,
                messages=msgs,
                outline_text=outline_text or "",
                allow_during_research=True,
                debug=True,
            )
            msgs.append(AIMessage(content="[Research Synthesizer] 최대 라운드 소진 → Writer 전환"))

    # ---- 반환 ----
    return {
        **state,
        "messages": msgs,
        "task_history": tasks,
        "findings_md": findings_md,
        "research_round": next_round,
        "last_synthesis": findings,
    }
