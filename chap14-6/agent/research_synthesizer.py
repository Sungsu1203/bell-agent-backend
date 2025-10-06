from __future__ import annotations
from typing import Mapping, Any, Optional
from langchain_core.messages import AIMessage
from langchain_core.output_parsers.string import StrOutputParser

from core.config import DOC_MODE, WRITER_AGENT
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task, AgentName
from utils.sanitize import sanitize_state, as_int
from utils.rag_utils import score_doc as _score_doc
from content_utils import read_outline, next_unwritten_title

from utils.tasks import has_pending, get_last_write_target
from utils.outline import get_topic_outline_text
from utils.query_filters import strip_web_filters, looks_like_local_glob, clean_seed, ok_query
from utils.text_utils import clean_snip as _clean_snip  # 표시/스니펫 용
from prompts import get_research_synthesizer_prompt
import os
from pathlib import Path
from core.models import Task, AgentName

from core.llm import get_llm
llm=get_llm()

def research_synthesizer(state: State):
    print("\n\n============ RESEARCH SYNTHESIZER ============")
    # state = sanitize_numeric_state(dict(state))
    state = sanitize_state(state)

    rnd = as_int(state, "research_round", 0)
    max_iter = max(1, as_int(state, "iteration_count", 1))

    refs = state.get("references") or {"queries": [], "docs": []}
    docs = list(refs.get("docs") or [])

    # def _pick_round_new_urls(state_dict: dict) -> Optional[int]:
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

    # def _pick_round_new_urls(st: dict) -> Optional[int]:
    #     for k in ("new_url_count_round", "round_new_urls", "new_urls", "new_url_count"):
    #         if k in st and st[k] is not None and str(st[k]).strip() != "":
    #             try:
    #                 return max(0, int(str(st[k]).strip()))
    #             except Exception:
    #                 continue
    #     return None

    round_new_urls = _pick_round_new_urls(state)

    if round_new_urls is None:
        print(f"[SYNTH] round={rnd+1}/{max_iter}, round_new_urls=? (missing)")
    else:
        state["new_url_count"] = round_new_urls
        state["new_url_count_round"] = round_new_urls
        state["round_new_urls"] = round_new_urls
        print(f"[SYNTH] round={rnd+1}/{max_iter}, round_new_urls={round_new_urls}")

    def _as_int_env_first(env_key: str, state_key: str, default: int) -> int:
        v = os.getenv(env_key)
        if v is not None and str(v).strip() != "":
            try:
                return int(v)
            except:
                pass
        return as_int(state, state_key, default)

    # threshold는 최소 1로 강제(0이면 항상 통과해 '조기중단'이 영원히 안 됨)
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

    msgs = list(state.get("messages") or [])
    msgs.append(AIMessage(saved_msg))

    findings_md = list(state.get("findings_md") or [])
    if out_path:
        findings_md.append(out_path)

        next_round = min(rnd + 1, max_iter)

        tasks = list(state.get("task_history") or [])

        # ======== [SYNTH_HALT_TO_WRITER] : '신규 없음' 조기 정지 시 곧바로 writer 태스크 생성 ========
        # 라우터와 동일한 키를 사용해 정지 여부 계산
        min_rounds = _as_int_env_first("RESEARCH_MIN_ROUNDS", "research_min_rounds", 1)
        max_no_new = max(1, _as_int_env_first("RESEARCH_MAX_NO_NEW_ROUNDS", "research_max_no_new_rounds", 1))
        should_halt = ((rnd + 1) >= max(1, min_rounds)) and (as_int(state, "no_new_url_streak", 0) >= max_no_new)
        print(f"[SYNTH] should_halt={should_halt} (round={rnd+1}, streak={as_int(state,'no_new_url_streak',0)}/{max_no_new}, min_rounds={min_rounds})")

        if should_halt:
            # 정지 즉시 writer 작업을 예약 (라우터가 writer로 보낼 때 pending 보장)
            writer = WRITER_AGENT
            if not has_pending(tasks, writer, prefix="write"):
                outline_text = get_topic_outline_text(state)
                fallback_default = "Executive Summary" if DOC_MODE == "report" else "서문"
                requested_title = get_last_write_target(msgs, tasks)
                auto_title = next_unwritten_title(
                    outline_text, mode=DOC_MODE, root_dir=current_path, topic_slug=state.get("topic_slug")
                )
                target_title = requested_title or auto_title or fallback_default
                tasks.append(Task(agent=writer, done=False, description=f"write: {target_title}", done_at=""))
        else:
            # 계속 탐색해야 하는 경우에만 다음 planner를 건다
            if next_round < max_iter:
                try:
                    already_planning = has_pending(tasks, "research_planner", prefix="plan_")
                except Exception:
                    already_planning = False
                if not already_planning:
                    tasks.append(Task(agent="research_planner", done=False, description="plan_next", done_at=""))
            else:
                # 라운드 소진으로 인한 일반적인 writer 전환
                writer = WRITER_AGENT
                if not has_pending(tasks, writer, prefix="write"):
                    outline_text = get_topic_outline_text(state)
                    fallback_default = "Executive Summary" if DOC_MODE == "report" else "서문"
                    requested_title = get_last_write_target(msgs, tasks)
                    auto_title = next_unwritten_title(
                        outline_text, mode=DOC_MODE, root_dir=current_path, topic_slug=state.get("topic_slug")
                    )
                    target_title = requested_title or auto_title or fallback_default
                    tasks.append(Task(agent=writer, done=False, description=f"write: {target_title}", done_at=""))
        # ======== [END SYNTH_HALT_TO_WRITER] ========

    return {
        **state,
        "messages": msgs,
        "task_history": tasks,
        "findings_md": findings_md,
        "research_round": next_round,
        "last_synthesis": findings,
    }
