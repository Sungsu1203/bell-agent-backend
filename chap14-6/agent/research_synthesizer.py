from __future__ import annotations
from typing import Mapping, Any, Optional, MutableMapping, cast
from pathlib import Path
import os

from langchain_core.output_parsers.string import StrOutputParser
from utils.tasks import AIMessage, has_pending
from utils.sanitize import sanitize_state, as_int
from utils.text_utils import clean_snip as _clean_snip
from utils.outline import get_topic_outline_text
from prompts import get_research_synthesizer_prompt
from core.state_types import State
from core.config import DOC_MODE
from core.paths import current_path, now_str as _now_str
from utils.writer_scheduler import schedule_writer_if_needed
from utils.rag_utils import score_doc as _score_doc

from core.llm import get_llm


def research_synthesizer(state: State):
    print("\n\n============ RESEARCH SYNTHESIZER ============")
    llm = get_llm()
    state = sanitize_state(state)

    # 안전한 기본값들
    msgs = list(state.get("messages") or [])
    tasks = list(state.get("task_history") or [])

    rnd = as_int(state, "research_round", 0)
    max_iter = max(1, as_int(state, "iteration_count", 1))
    next_round = min(rnd + 1, max_iter)

    refs = state.get("references") or {"queries": [], "docs": []}
    docs = list(refs.get("docs") or [])

    # ---- 신규 URL 수 카운트 추출(라우터와 동일 키 집합 사용) ----
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

    round_new_urls = _pick_round_new_urls(state)
    if round_new_urls is None:
        print(f"[SYNTH] round={rnd+1}/{max_iter}, round_new_urls=? (missing)")
    else:
        # 동기화
        state["new_url_count"] = round_new_urls
        state["new_url_count_round"] = round_new_urls
        state["round_new_urls"] = round_new_urls
        print(f"[SYNTH] round={rnd+1}/{max_iter}, round_new_urls={round_new_urls}")

    # ---- 조기중단 계산용 파라미터 ----
    def _as_int_env_first(env_key: str, state_key: str, default: int) -> int:
        v = os.getenv(env_key)
        if v is not None and str(v).strip() != "":
            try:
                return int(v)
            except Exception:
                pass
        return as_int(state, state_key, default)

    halt_threshold = max(1, _as_int_env_first("RESEARCH_HALT_THRESHOLD", "research_halt_threshold", 1))
    prev_streak = as_int(state, "no_new_url_streak", 0)
    if round_new_urls is None:
        streak = prev_streak
    elif round_new_urls <= halt_threshold:
        streak = prev_streak + 1
    else:
        streak = 0
    state["no_new_url_streak"] = streak
    print(f"[SYNTH] no_new_url_streak → {streak} (threshold={halt_threshold})")

    # ---- 컨텍스트 스니펫 만들기 ----
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

    # ---- 결과 저장(파일) ----
    topic = state.get("topic_slug") or "default"
    outdir = os.path.join(current_path, "research", topic)
    try:
        Path(outdir).mkdir(parents=True, exist_ok=True)
        out_path = os.path.join(outdir, f"round-{rnd + 1:02d}-findings.md")
        Path(out_path).write_text(findings, encoding="utf-8")
        saved_msg = f"[Research Synthesizer] Round {rnd + 1} findings saved → {out_path}"
    except Exception as e:
        out_path = None
        saved_msg = f"[Research Synthesizer] Round {rnd + 1} findings generated (file save failed: {e})"

    msgs.append(AIMessage(saved_msg))

    findings_md = list(state.get("findings_md") or [])
    if out_path:
        findings_md.append(out_path)

    # ---- 다음 단계 결정: 조기 종료/라운드 소진 → 집필 예약, 아니면 다음 planner ----
    min_rounds = _as_int_env_first("RESEARCH_MIN_ROUNDS", "research_min_rounds", 1)
    max_no_new = max(1, _as_int_env_first("RESEARCH_MAX_NO_NEW_ROUNDS", "research_max_no_new_rounds", 1))
    should_halt = ((rnd + 1) >= max(1, min_rounds)) and (as_int(state, "no_new_url_streak", 0) >= max_no_new)
    print(f"[SYNTH] should_halt={should_halt} (round={rnd+1}, streak={as_int(state,'no_new_url_streak',0)}/{max_no_new}, min_rounds={min_rounds})")

    if should_halt:
        # 연구 조기 종료 → 즉시 writer 예약 시도
        outline_text = get_topic_outline_text(state)
        schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            tasks=tasks,
            messages=msgs,
            outline_text=outline_text or "",
            allow_during_research=True,
            debug=True,
        )
    else:
        # 라운드 남았으면 다음 planner, 소진되면 writer
        if next_round < max_iter:
            try:
                already_planning = has_pending(tasks, "research_planner", prefix="plan_")
            except Exception:
                already_planning = False
            if not already_planning:
                from core.models import Task  # 지역 import로 순환 참조 방지
                tasks.append(Task(agent="research_planner", done=False, description="plan_next", done_at=""))
        else:
            outline_text = get_topic_outline_text(state)
            schedule_writer_if_needed(
                cast(MutableMapping[str, Any], state),
                tasks=tasks,
                messages=msgs,
                outline_text=outline_text or "",
                allow_during_research=True,  # 연구 종료 → 즉시 집필 허용
                debug=True,
            )

    # ---- 반환 ----
    return {
        **state,
        "messages": msgs,
        "task_history": tasks,
        "findings_md": findings_md,
        "research_round": next_round,
        "last_synthesis": findings,
    }
