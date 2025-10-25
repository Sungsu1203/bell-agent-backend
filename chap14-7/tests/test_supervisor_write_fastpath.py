# tests/test_research_auto_write_policy.py
import os
from pathlib import Path
from typing import cast

import pytest
from langchain_core.messages import HumanMessage

from agent.vector_search import vector_search_agent
from core.models import Task
from core.state_types import State
from utils.tasks import has_pending


def _make_demo_data(tmp_path: Path) -> str:
    """임시 demo_data 폴더와 샘플 파일 2개 생성 후 경로 반환"""
    data_dir = tmp_path / "demo_data"
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "energy_policy.txt").write_text(
        "태양광 보조금은 2024년 기준 kW당 75만원까지 지원됩니다. 설치 건수는 2023년에 12,345건이었습니다.",
        encoding="utf-8",
    )
    (data_dir / "memo.md").write_text(
        "# 재생에너지 메모\n- 보조금 단가 변동성 큼\n- 2030 목표: 보급률 21%",
        encoding="utf-8",
    )
    return str(data_dir)


def _mk_research_state() -> State:
    """타입체커를 만족하는 최소 상태(State) 구성"""
    state: State = {
        "messages": [HumanMessage("demo_data 내용 중 policy 관련 핵심만 정리해줘")],
        "task_history": [
            Task(
                agent="vector_search_agent",
                done=False,
                description="사용자 질의 기반 RAG 검색을 수행한다.",
                done_at="",
            )
        ],
        # ↓ references는 TypedDict상 필수로 보는 경우가 있어 안전하게 채워둠
        "references": {"queries": [], "docs": []},
        "agent_role": "research analyst",
        "iteration_count": 2,
        "research_objectives": ["시장규모/동향 확인"],
        "topic_slug": "default",
        # chroma_ns는 없으면 env/기본값 사용, 필요시 다음 줄 주석 해제
        # "chroma_ns": "demo",
    }
    return state


@pytest.fixture(autouse=True)
def _env_common(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """공통 환경 설정 + 임시 demo_data 구성"""
    data_dir = _make_demo_data(tmp_path)

    monkeypatch.setenv("CHROMA_NAMESPACE", "demo")
    monkeypatch.setenv("SKIP_WEB_SEARCH", "1")  # 로컬만
    # 윈도우/리눅스 경로 모두 허용되도록 문자열로 넣어줌
    monkeypatch.setenv("LOCAL_RAG_GLOBS", f"{data_dir}/*.txt|{data_dir}/*.md")
    monkeypatch.setenv("CLEAR_CHROMA_ON_START", "1")
    # WRITER 기본값(리포트 모드면 section_writer)
    monkeypatch.setenv("DOC_MODE", "report")
    monkeypatch.setenv("WRITER_AGENT", "section_writer")


def test_no_writer_when_auto_write_during_research_off(monkeypatch: pytest.MonkeyPatch):
    # 연구모드 ON + 연구 중 자동집필 금지
    monkeypatch.setenv("BLOCKAGI_AGENT_ROLE", "research analyst")
    monkeypatch.setenv("AUTO_WRITE_AFTER_RAG", "1")
    monkeypatch.setenv("AUTO_WRITE_DURING_RESEARCH", "0")

    state = _mk_research_state()
    out = vector_search_agent(state)

    tasks = cast(list, out["task_history"])
    writer = os.getenv("WRITER_AGENT", "section_writer")

    # 연구 중에는 writer 예약이 없어야 함
    assert not has_pending(tasks, writer, prefix="write")


def test_writer_when_auto_write_during_research_on(monkeypatch: pytest.MonkeyPatch):
    # 연구모드 ON + 연구 중 자동집필 허용
    monkeypatch.setenv("BLOCKAGI_AGENT_ROLE", "research analyst")
    monkeypatch.setenv("AUTO_WRITE_AFTER_RAG", "1")
    monkeypatch.setenv("AUTO_WRITE_DURING_RESEARCH", "1")

    state = _mk_research_state()
    out = vector_search_agent(state)

    tasks = cast(list, out["task_history"])
    writer = os.getenv("WRITER_AGENT", "section_writer")

    # 연구 중에도 writer 예약이 있어야 함
    assert has_pending(tasks, writer, prefix="write")
