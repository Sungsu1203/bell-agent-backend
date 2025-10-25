# test_progress_and_communicator_minimal.py
import os, time, types
import pytest

from typing import cast
from core.state_types import State

# 경로는 프로젝트 구조에 맞게 조정하세요
import agent.section_writer as sw_mod
import agent.communicator as comm_mod
from utils.tasks import HumanMessage
from core.models import Task

@pytest.fixture(autouse=True)
def _env_setup(monkeypatch, tmp_path):
    # 섹션 라이터 동작 모드
    monkeypatch.setattr(sw_mod, "DOC_MODE", "report", raising=False)
    # Communicator rate-limit 토글
    monkeypatch.setenv("LOG_DASHBOARD", "1")
    monkeypatch.setenv("DASH_RATE_SEC", "6")
    # 각주/에코 비활성(단순화)
    monkeypatch.setenv("AUTO_FOOTNOTE", "0")
    monkeypatch.setenv("ECHO_SECTIONS", "0")

    # 저장 스텁
    def _fake_save_md_draft(title, body, mode, root_dir, topic_slug):
        outdir = tmp_path / "content" / topic_slug / ("sections" if mode=="report" else "chapters")
        outdir.mkdir(parents=True, exist_ok=True)
        p = outdir / (f"{title}.md".replace("/", "_"))
        p.write_text(body or "", encoding="utf-8")
        return str(p)
    monkeypatch.setattr(sw_mod, "save_md_draft", _fake_save_md_draft, raising=True)

    # LLM 체인 스텁 (invoke 사용)
    class _FakeChain:
        def invoke(self, _):
            return "# 섹션 본문 DRAFT\n\n내용...\n"

    def _fake_get_prompt():
        class _Prompt:
            def __or__(self, other):
                class _Mid:
                    def __or__(self, _parser):
                        return _FakeChain()
                return _Mid()
        return _Prompt()
    monkeypatch.setattr(sw_mod, "get_section_writer_prompt", _fake_get_prompt, raising=True)

    # outline 스텁(섹션 2개로 간주)
    def _fake_outline(_state):
        return "## 섹션 A\n- 항목\n\n## 섹션 B\n- 항목\n"
    monkeypatch.setattr(sw_mod, "get_topic_outline_text", _fake_outline, raising=True)

        # --- LLM 스텁: section_writer가 실제 OpenAI 초기화하지 않도록 막기 ---
    def _fake_get_llm():
        class _LLM:
            # section_writer에서 get_section_writer_prompt() | llm | StrOutputParser()
            # 체인을 만들 때 __or__만 필요합니다.
            def __or__(self, other):
                return self
        return _LLM()
    monkeypatch.setattr(sw_mod, "get_llm", _fake_get_llm, raising=True)

    yield


def test_section_writer_progress_and_communicator_minimal(monkeypatch):
    state = {
        "topic_title": "테스트 리포트",
        "topic_slug": "demo",
        "messages": [HumanMessage(content="write: 섹션 A")],
        "task_history": [Task(agent="section_writer", done=False, description="", done_at="")],
        "flags": {},
    }

    # 1) section_writer 실행 → 저장 + 진행률 갱신
    res1 = sw_mod.section_writer(cast(State, state))
    assert "messages" in res1 and "task_history" in res1
    f = state.get("flags") or {}
    assert int(f.get("sections_done", 0)) == 1
    assert int(f.get("sections_total", 0)) >= 2
    assert "섹션 A" in (f.get("sections_seen") or "")
    assert isinstance(state.get("last_saved_path"), str) and state["last_saved_path"]

    # 같은 섹션 다시 요청 → done 카운트 증가 안 함
    state["task_history"].append(Task(agent="section_writer", done=False, description="", done_at=""))
    res2 = sw_mod.section_writer(cast(State, state))
    f2 = state.get("flags") or {}
    assert int(f2.get("sections_done", 0)) == 1

    # 2) Communicator minimal 모드 확인
    state["flags"]["dash_last_ts"] = time.time()
    state["task_history"].append(Task(agent="communicator", done=False, description="상태 보고", done_at=""))

    # communicator가 LLM 스트림을 타지 않아도 되게 스텁
    monkeypatch.setattr(comm_mod, "DOC_MODE", "report", raising=False)
    def _fake_get_llm():
        class _LLM:
            def __or__(self, other): return self
            def stream(self, _): 
                yield types.SimpleNamespace(content="")
        return _LLM()
    monkeypatch.setattr(comm_mod, "get_llm", _fake_get_llm, raising=True)

     # ⬇⬇⬇ 여기 추가하세요 (communicator 호출 '바로 전')
    def _fake_prompt():
        class _P:
            # communicator_prompt | llm 를 그대로 통과시켜 주는 더미
            def __or__(self, other):
                return other
        return _P()

    monkeypatch.setattr(comm_mod, "get_communicator_prompt", _fake_prompt, raising=True)
    # ⬆⬆⬆ 여기까지

    res3 = comm_mod.communicator(cast(State, state))
    last_msg = res3["messages"][-1]
    assert "[Communicator] 최신 진행상황만 간단히 안내합니다." in str(getattr(last_msg, "content", ""))
    last_comm = next((t for t in reversed(res3["task_history"]) if t.agent == "communicator"), None)
    assert last_comm and last_comm.done
