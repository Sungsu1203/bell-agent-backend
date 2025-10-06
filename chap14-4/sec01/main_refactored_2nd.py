# ── Section Writer ===========================================================

def section_writer(state: State):
    """보고서 모드에서 섹션 단위로 초안을 작성합니다."""
    if DOC_MODE != "report":
        print(f"[SECTION WRITER] Skipped: DOC_MODE={DOC_MODE} (expected 'report').")
        return {"messages": state.get("messages", []), "task_history": state.get("task_history", [])}

    print("\n\n============ SECTION WRITER ============")
    state = sanitize_numeric_state(state)

    tasks = state.get("task_history", []) or []
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "section_writer"), None)
    if pending is None:
        print("[WARN] pending 'section_writer' task가 없습니다. edge pass.")

    messages = state.get("messages", []) or []
    outline_text = get_topic_outline_text(state)
    if not outline_text.strip():
        # 목차가 없으면 자동 생성 태스크 예약 후 보류
        fname = state.get("outline_fname") or "outline_report.md"
        if not has_pending(tasks, "content_strategist"):
            tasks.append(Task(agent="content_strategist", done=False, description=f"create_outline:{fname}", done_at=""))
        messages.append(AIMessage(f"[Section Writer] 아웃라인이 비어 있어 자동으로 목차 생성을 요청했습니다. (target={fname})"))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        return {"messages": messages, "task_history": tasks}

    target_title = get_last_write_target(messages, tasks) or next_unwritten_title(
        outline_text, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug")
    )
    if not target_title:
        messages.append(AIMessage("[Section Writer] 모든 섹션 초안이 이미 작성되었습니다."))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        if not has_pending(tasks, "communicator"):
            tasks.append(Task(agent="communicator", done=False, description="집필 완료 보고 및 편집 단계 여부 파악", done_at=""))
        return {"messages": messages, "task_history": tasks}

    print(f"👉 Target section: {target_title}")
    ref_text = _refs_preview_text(state)

    report_writer_prompt = get_section_writer_prompt()
    chain = report_writer_prompt | llm | StrOutputParser()
    gathered = ""
    for chunk in chain.stream(
        {
            "target_title": target_title,
            "outline": outline_text,
            "references": ref_text,
            "messages": messages,
            "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
        }
    ):
        print(chunk, end="")
        gathered += chunk
    print()

    # 저장 전: 자동 각주/참고 자료 부착(옵션)
    if os.getenv("AUTO_FOOTNOTE", "1") == "1":
        try:
            gathered = attach_auto_citations(gathered, state)
        except Exception as e:
            print(f"[WARN] auto-citation 실패: {e}")

    out_path = save_md_draft(
        target_title, gathered, mode="report", root_dir=current_path, topic_slug=state.get("topic_slug")
    )

    messages.append(AIMessage(f"[Section Writer] '{target_title}' 초안 작성 완료 → {out_path}"))
    state["last_saved_path"] = out_path
    print(f"[Section Writer] saved → {out_path}")

    if pending:
        pending.done = True
        pending.done_at = _now_str()

    if not has_pending(tasks, "communicator"):
        tasks.append(
            Task(agent="communicator", done=False, description=f"'{target_title}' 초안 완료 보고 및 다음 섹션/수정 범위 확인", done_at="")
        )

    return {"messages": messages, "task_history": tasks}


# ── Communicator =============================================================

def communicator(state: State):
    """사용자에게 현재 상태를 전달하고 다음 액션을 이끕니다."""
    print("\n\n============ COMMUNICATOR ============")
    state = sanitize_numeric_state(state)

    messages = state.get("messages", []) or []
    tasks = state.get("task_history", []) or []
    if not tasks:
        raise ValueError("작업 이력이 없습니다.")

    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "communicator"), None)
    desc = (pending.description if pending else "") or ""

    # 🔊 플래너 발표 모드
    if "announce_planner" in desc.lower():
        last_planner = next(
            (m for m in reversed(messages)
             if isinstance(m, AIMessage) and str(m.content or "").startswith("[Research Planner]")),
            None
        )
        text = last_planner.content if last_planner else "(리서치 플래너 메시지를 찾지 못했습니다.)"
        print("\nAI\t:\n" + text)
        messages.append(AIMessage(text))
        if pending:
            pending.done = True
            pending.done_at = _now_str()
        if not has_pending(tasks, "web_search_agent"):
            tasks.append(Task(agent="web_search_agent", done=False, description="rag_update:auto", done_at=""))
        return {"messages": messages, "task_history": tasks}

    # show_outline 요청 처리
    show_outline_req = False
    explicit_fname = None
    if desc:
        mdesc = re.search(r"show_outline\s*:\s*([A-Za-z0-9_\-\.]+)", desc, flags=re.I)
        if mdesc:
            explicit_fname = mdesc.group(1).strip()
            show_outline_req = True

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    if (last_human and isinstance(last_human.content, str) and is_outline_display(last_human.content)):
        show_outline_req = True

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

    text_buf = ""
    for chunk in system_chain.stream(
        {
            "messages": messages,
            "outline": fallback_outline,
            "doc_label": doc_label,
            "topic_title": state.get("topic_title") or "",
        }
    ):
        print(chunk.content, end="")
        text_buf += chunk.content
    messages.append(AIMessage(text_buf))

    # 마지막 저장 경로 힌트 부가(가능할 때만)
    try:
        base_text = messages[-1].content or ""
        if not any(x in base_text for x in ("chapters\\", "sections\\", "chapters/", "sections/")):
            last_save_path = None
            for m in reversed(messages):
                if not isinstance(m, AIMessage):
                    continue
                mtxt = m.content or ""
                m1 = re.search(r"→\s*(.+?\.md)\s*$", mtxt)
                if m1:
                    last_save_path = m1.group(1).strip()
                    break
            if not last_save_path:
                lsp = state.get("last_saved_path")
                if isinstance(lsp, str) and lsp.strip():
                    last_save_path = lsp.strip()
            if last_save_path:
                try:
                    last_save_path = os.path.normpath(last_save_path)
                except Exception:
                    pass
                messages[-1] = AIMessage(base_text + f"\n\n최종 저장 경로: `{last_save_path}`")
    except Exception:
        pass

    if pending:
        pending.done = True
        pending.done_at = _now_str()

    return {"messages": messages, "task_history": tasks}


# ── Graph ====================================================================

graph_builder = StateGraph(State)

# Nodes
graph_builder.add_node("supervisor", supervisor)
graph_builder.add_node("communicator", communicator)
graph_builder.add_node("content_strategist", content_strategist)
graph_builder.add_node("vector_search_agent", vector_search_agent)
graph_builder.add_node("web_search_agent", web_search_agent)
graph_builder.add_node("chapter_writer", chapter_writer)
graph_builder.add_node("section_writer", section_writer)
graph_builder.add_node("research_planner", research_planner)
graph_builder.add_node("research_synthesizer", research_synthesizer)


def tail_task_router(state: State):
    """목차 상태와 마지막 작성 태스크에 따라 후속 라우팅을 결정합니다."""
    outline_text = get_topic_outline_text(state)
    outline_missing = not (outline_text or "").strip()
    outline_not_shown = state.get("outline_shown") is False

    if outline_missing:
        return "content_strategist"   # 먼저 만들어야 함
    if outline_not_shown:
        return "communicator"         # 만들어졌으면 이제 보여주기

    allowed = {"chapter_writer", "section_writer", "communicator"}
    for t in reversed(state.get("task_history", [])):
        if (not t.done) and t.agent in allowed:
            return t.agent
    return WRITER_AGENT if WRITER_AGENT in {"chapter_writer", "section_writer"} else "chapter_writer"


def after_vector_router(state: State):
    """벡터 검색 이후 라우팅을 일원화합니다."""
    # 직답 플래그가 있으면 바로 커뮤니케이터
    if state.get("qa_direct_reply"):
        return "communicator"

    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)
    has_objs = bool(state.get("research_objectives"))

    if role == "research analyst" and has_objs and rounds_done < max_iter:
        return "research_synthesizer"
    return tail_task_router(state)


def after_planner_router(state: State):
    """플래너 이후 알림 여부에 따라 분기."""
    announce = os.getenv("RESEARCH_PLANNER_ANNOUNCE", "0") == "1" or as_int(state, "research_planner_announce", 0) == 1
    return "communicator" if announce else "web_search_agent"


def after_synthesizer_router(state: State):
    """
    연구 합성 이후 라우팅:
    - 최소 라운드 충족 + 무신규 연속 라운드 초과 시 집필로 전환
    - 아니면 다음 라운드
    """
    rounds_done = as_int(state, "research_round", 0)
    max_iter    = as_int(state, "iteration_count", 0)

    # 신규 URL 수 표준 키 선택
    def first_int(st, keys, default=0):
        for k in keys:
            if k in st and str(st[k]).strip() != "":
                try:
                    return int(str(st[k]).strip())
                except Exception:
                    continue
        return default

    new_url_count = first_int(state, ["new_url_count", "new_url_count_round", "new_urls", "round_new_urls"], 0)

    def _pick(env_key, state_key, default):
        v = os.getenv(env_key)
        if v is not None and str(v).strip() != "":
            try:
                return int(v)
            except Exception:
                pass
        return as_int(state, state_key, default)

    halt_threshold = _pick("RESEARCH_HALT_THRESHOLD",       "research_halt_threshold",        0)
    min_rounds     = _pick("RESEARCH_MIN_ROUNDS",           "research_min_rounds",            1)
    max_no_new     = max(1, _pick("RESEARCH_MAX_NO_NEW_ROUNDS", "research_max_no_new_rounds", 1))
    streak         = as_int(state, "no_new_url_streak", 0)

    print(f"[ROUTER] after_synthesizer: rounds_done={rounds_done}, max_iter={max_iter}, "
          f"new_url_count={new_url_count}, halt_threshold={halt_threshold}, "
          f"min_rounds={min_rounds}, no_new_url_streak={streak}/{max_no_new}")

    should_halt = (rounds_done >= max(1, min_rounds)) and (streak >= max_no_new)

    if rounds_done < max_iter and not should_halt:
        print("[ROUTER] → research_planner")
        return "research_planner"

    if should_halt:
        print(f"[ROUTER] halt: new_url_count<=threshold for {streak} round(s) → writer")
        return WRITER_AGENT

    nxt = tail_task_router(state)
    print(f"[ROUTER] → {nxt}")
    return nxt


# Edges
graph_builder.add_edge(START, "supervisor")

graph_builder.add_conditional_edges(
    "supervisor",
    supervisor_router,
    {
        "content_strategist": "content_strategist",
        "communicator": "communicator",
        "vector_search_agent": "vector_search_agent",
        "web_search_agent": "web_search_agent",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "research_planner": "research_planner",
    },
)

graph_builder.add_edge("content_strategist", "communicator")

graph_builder.add_conditional_edges(
    "research_planner",
    after_planner_router,
    {"communicator": "communicator", "web_search_agent": "web_search_agent"},
)

graph_builder.add_edge("web_search_agent", "vector_search_agent")

# ✅ after_vector_router에서 qa_direct_reply를 포함해 모든 경우를 일원화
graph_builder.add_conditional_edges(
    "vector_search_agent",
    after_vector_router,
    {
        "research_synthesizer": "research_synthesizer",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",
    },
)

graph_builder.add_conditional_edges(
    "research_synthesizer",
    after_synthesizer_router,
    {
        "research_planner": "research_planner",
        "chapter_writer": "chapter_writer",
        "section_writer": "section_writer",
        "communicator": "communicator",
        "content_strategist": "content_strategist",
    },
)

graph_builder.add_edge("chapter_writer", "communicator")
graph_builder.add_edge("section_writer", "communicator")
graph_builder.add_edge("communicator", END)

# Compile graph
graph = graph_builder.compile()


# ── Mermaid 렌더 (선택) ------------------------------------------------------
HTML_TMPL = Template(
    """<!DOCTYPE html>
<html>
<head>
<meta charset=\"UTF-8\">
<script src=\"https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js\"></script>
<script>mermaid.initialize({ startOnLoad: true, theme: 'default' });</script>
<style> body{margin:0;padding:16px;} </style>
</head>
<body><div class=\"mermaid\">$mmd</div></body>
</html>
"""
)

def render_mermaid_with_playwright(mmd: str, out_path: str, width: int = 1600, height: int = 1000):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("[INFO] Playwright 미설치: 그래프 렌더를 건너뜁니다.")
        return None
    html = HTML_TMPL.substitute(mmd=mmd)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(300)
        page.locator(".mermaid").screenshot(path=out_path)
        browser.close()
    return out_path


# ── 초기 상태 & CLI 루프 ──────────────────────────────────────────

def _initial_state(iteration_count: int, agent_role: str | None = None) -> State:
    default_outline = "outline_report.md" if DOC_MODE == "report" else "outline.md"
    base: State = {
        "messages": [
            SystemMessage(
                f"""
                너희 AI들은 사용자의 요구에 맞는 {('보고서' if DOC_MODE=='report' else '책')}을(를) 쓰는 작가팀이다.
                사용자가 사용하는 언어로 대화하라.
                현재시각은 {_now_str()}이다.
                """
            )
        ],
        "task_history": [],
        "references": {"queries": [], "docs": []},
        "agent_role": (agent_role or os.getenv("BLOCKAGI_AGENT_ROLE", "").strip().lower()),
        "iteration_count": int(iteration_count),
        "research_objectives": _load_objectives_from_env(),
        "research_round": 0,
        "findings_md": [],
        "llm_logs": [],
        "new_url_count": None,                 # 합성기 조기종료 방지(초기 None)
        "topic_slug": os.getenv("TOPIC_SLUG") or "default",
        "outline_fname": default_outline,
        "outline_shown": False,               # 목차 실제 표시 여부 추적
    }
    return sanitize_numeric_state(base)

def read_user_input() -> str:
    r'''
    콘솔에서 멀티라인 입력을 한 번에 읽어오는 도우미.
    - 첫 줄이 ``` 또는 """ 면 '펜스 모드': 같은 펜스로 닫힐 때까지 읽음
    - 첫 줄이 \ 로 끝나면 줄연결 모드
    '''
    first = input("\nUser\t: ")
    s = first.strip()
    if s in ('```', '"""'):
        fence = s
        lines = []
        while True:
            line = input()
            if line.strip() == fence:
                break
            lines.append(line)
        return "\n".join(lines).strip()
    buf = first
    while buf.endswith("\\"):
        buf = buf[:-1] + "\n" + input()
    return buf.strip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--iteration_count",
        type=str,
        default=os.getenv("ITERATION_COUNT", os.getenv("BLOCKAGI_ITERATION_COUNT", "3")),
        help="연구 라운드 최대 횟수(정수/문자열 모두 허용)",
    )
    parser.add_argument(
        "--agent_role",
        type=str,
        default=os.getenv("BLOCKAGI_AGENT_ROLE", "").strip().lower(),
        help="'research analyst'로 설정하면 연구 라운드 모드 활성화",
    )
    parser.add_argument(
        "--render_graph",
        action="store_true",
        help="Mermaid 그래프 PNG 렌더",
    )
    args = parser.parse_args()

    iter_count = coerce_int(args.iteration_count, default=3)
    state: State = _initial_state(iteration_count=iter_count, agent_role=args.agent_role)

    if args.render_graph or os.getenv("RENDER_GRAPH", "0") == "1":
        try:
            mmd = graph.get_graph().draw_mermaid()
            out_png = absolute_path.replace(".py", ".png")
            if render_mermaid_with_playwright(mmd, out_png):
                print("Saved:", out_png)
        except Exception as e:
            print("[WARN] mermaid 렌더 실패:", e)

    while True:
        try:
            user_input = read_user_input()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ["exit", "quit", "q"]:
            print("Goodbye!")
            break

        state["messages"].append(HumanMessage(user_input))
        state = graph.invoke(state, config={"recursion_limit": 200})
        print("\n------------------------------------ MESSAGE COUNT\t", len(state["messages"]))
        save_state(current_path, state)
