from __future__ import annotations
import re, os
from typing import Any
from langchain_core.messages import HumanMessage, AIMessage

from core.config import DOC_MODE
from core.paths import now_str as _now_str, current_path
from core.state_types import State
from core.models import Task, AgentName
from utils.sanitize import sanitize_state
from rag_expression import is_outline_creation, is_outline_display
from prompts import get_communicator_prompt
from content_utils import read_outline

from utils.tasks import has_pending
from utils.outline import get_topic_outline_text

from core.llm import get_llm
llm=get_llm()

def communicator(state: State):
    print("\n\n============ COMMUNICATOR ============")
    state = sanitize_state(state)
    # state = sanitize_numeric_state(state)

    messages = state.get("messages", [])
    tasks = state.get("task_history", [])
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
    desc = (pending.description if pending else "") or ""

    def _as_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    # 흔한 키들 우선
                    for k in ("text", "content", "value", "message"):
                        v = item.get(k)
                        if isinstance(v, str):
                            parts.append(v)
                            break
                    else:
                        # 텍스트가 없으면 안전하게 문자열화
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

    # 플래너 발표 모드
    if "announce_planner" in desc.lower():
        last_planner = next(
            (m for m in reversed(messages)
             if isinstance(m, AIMessage) and str(m.content or "").startswith("[Research Planner]")),
            None
        )
        raw = last_planner.content if last_planner else "(리서치 플래너 메시지를 찾지 못했습니다.)"
        text = _as_text(raw)
        print("\nAI\t:\n" + text)
        messages.append(AIMessage(text))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        if not has_pending(tasks, "web_search_agent"):
            tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # show_outline 처리
    show_outline_req = False
    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    explicit_fname = None
    mdesc = re.search(r"show_outline\s*:\s*([A-Za-z0-9_\-\.]+)", desc)
    if mdesc:
        explicit_fname = mdesc.group(1).strip()
        show_outline_req = True
    if ("show_outline" in desc.lower()) or (last_human and is_outline_display(last_human.content)):
        show_outline_req = True

    # 이미 outline을 보여준 상태이고, 이번에 명시적으로 요청되지 않았다면 재표시는 억제
    if state.get("outline_shown") and not show_outline_req:
        # outline을 다시 보여주지 않고 일반 커뮤니케이션으로만 진행
        pass

    if show_outline_req:
        preferred = state.get("outline_fname")
        default_by_mode = "outline_report.md" if DOC_MODE == "report" else "outline.md"
        fname = explicit_fname or preferred or default_by_mode
        state["outline_fname"] = fname

        outline_text, used_path = read_outline(
            filename=fname,
            root_dir=current_path,
            topic_slug=state.get("topic_slug"),
            mode=DOC_MODE,
            allow_fallbacks=False,
        )

        if not (outline_text or "").strip():
            if not has_pending(tasks, "content_strategist"):
                tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))

            note = f"({fname}) 파일이 아직 없습니다. 지금 기본 목차를 생성하겠습니다."
            print("\nAI\t:\n" + note)
            messages.append(AIMessage(note))
            state["outline_shown"] = False

            if pending:
                pending.done = True
                pending.done_at = _now_str()
            return {"messages": messages, "task_history": tasks, "outline_fname": fname}

        title = f"## 현재 목차 ({used_path.name if used_path else fname})"
        content = f"{title}\n\n{outline_text}"
        print("\nAI\t:\n" + content)
        messages.append(AIMessage(content))
        state["outline_shown"] = True

        followup = (
            "목차를 확인했습니다. 다음 중 어떻게 진행할까요?\n"
            "1) 특정 섹션부터 바로 집필 → `write: 섹션명`\n"
            "2) 목차 수정 → 바꿀 제목/순서를 말씀해 주세요\n"
            "3) 최신 자료 보강 → `최신 자료로 RAG 업데이트`\n"
        )
        # 동일 세션에서 불필요한 반복 표시 방지용 힌트
        # 다음 커뮤니케이터 호출에서 show_outline이 들어오지 않는 한, outline 재표시 생략
        # (state["outline_shown"] 는 이미 True)
        print("\nAI\t:\n" + followup)
        messages.append(AIMessage(followup))

        if pending:
            pending.done = True
            pending.done_at = _now_str()
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="목차 확인 후 다음 집필 대상/수정 요청 파악", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # 일반 커뮤니케이션
    fallback_outline = get_topic_outline_text(state)
    doc_label = "보고서" if DOC_MODE == "report" else "책"
    communicator_prompt = get_communicator_prompt()
    system_chain = communicator_prompt | llm

    parts: list[str] = []
    for chunk in system_chain.stream({
        "messages": messages,
        "outline": fallback_outline,
        "doc_label": doc_label,
        "topic_title": state.get("topic_title") or "",
    }):
        part_text = _as_text(getattr(chunk, "content", ""))
        print(part_text, end="")
        parts.append(part_text)

    def _dedupe_consecutive_lines(s: str) -> str:
        lines, out, prev = s.splitlines(), [], None
        for ln in lines:
            if ln == prev:
                continue
            out.append(ln)
            prev = ln
        return "\n".join(out)

    # 생성 후 후처리
    text_buf = "".join(parts)
    text_buf = _dedupe_consecutive_lines(text_buf)  # ← 추가
    messages.append(AIMessage(text_buf))

    # 마지막 저장 경로 힌트 부가
    try:
        base_text = _as_text(messages[-1].content)
        if not any(x in base_text for x in ["chapters\\", "sections\\", "chapters/", "sections/"]):
            last_save_path = None
            moved_note = None

            p_writer = re.compile(r"\[(?:Section|Chapter|Content)\s+Writer\].*?→\s*(?P<path>.+?\.md)\s*", re.DOTALL)
            p_strat  = re.compile(r"\[Content Strategist\].*?→\s*(?P<path>.+?\.md)\s*", re.DOTALL)
            p_moved  = re.compile(r"\[(?:Section|Chapter|Content)\s+Writer\]\s*moved.*?->\s*(?P<path>.+?\.md)\s*", re.DOTALL)

            for m in reversed(messages):
                if not isinstance(m, AIMessage):
                    continue
                content_text = _as_text(m.content)

                m1 = p_writer.search(content_text) or p_strat.search(content_text)
                if m1:
                    last_save_path = m1.group("path").strip()
                    break

                m2 = p_moved.search(content_text)
                if m2:
                    last_save_path = m2.group("path").strip()
                    moved_note = " (파일이 자동 정리되어 sections로 이동되었습니다.)"
                    break

            if not last_save_path:
                lsp = (state or {}).get("last_saved_path")
                if isinstance(lsp, str) and lsp.strip():
                    last_save_path = lsp.strip()

            if last_save_path:
                try:
                    last_save_path = os.path.normpath(last_save_path)
                except Exception:
                    pass
                messages[-1] = AIMessage(base_text + f"\n\n최종 저장 경로: `{last_save_path}`" + (moved_note or ""))
    except Exception as e:
        print(f"[WARN] last-save-path hint failed: {e}")
    
    #except Exception:
    #    pass


    if pending:
        pending.done = True
        pending.done_at = _now_str()

    return {"messages": messages, "task_history": tasks}