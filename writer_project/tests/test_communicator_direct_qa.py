# tests/test_communicator_direct_qa.py

from pathlib import Path
from agent.communicator import communicator
from utils.tasks import HumanMessage, AIMessage
from core.models import Task
import core.config as config
from core.state_types import State

def _make_state_for_height_qa(tmp_path: Path) -> State:
    # REPORT_OUT_DIR 을 임시 디렉토리로 강제 → 저장 경로 검증 가능
    config.CFG.REPORT_OUT_DIR = str(tmp_path)

    human = HumanMessage(content="키성장 건강기능식품에 대한 최신 근거를 알려줘.")
    qa_answer = (
        "일반적으로 키성장 건강기능식품은 성장판이 열려 있는 시기의 "
        "균형 잡힌 영양 공급을 보조하는 수준으로 이해하는 것이 안전합니다. "
        "필수 영양소(칼슘·비타민D·단백질 등)를 채우는 것이 핵심이며, "
        "과장 광고나 단기간 신장 증가를 보장하는 제품은 주의가 필요합니다."
    )
    ai_qa = AIMessage(
        content=qa_answer,
        additional_kwargs={"qa_direct_reply": True},
    )

    state: State = {
        "topic_slug": "height-growth-health-functional-food",
        "topic_title": "키성장 건강기능식품 시장(국내)",
        "messages": [human, ai_qa],
        "flags": {
            "qa_direct_reply": True,
            "suppress_writer": False,
        },
        "task_history": [
            Task(agent="communicator", done=False, description="direct qa test", done_at="")
        ],
        "references": {"docs": []},  # 일단 refs 없는 상태
    }
    return state

def test_direct_qa_happy_path(tmp_path):
    state = _make_state_for_height_qa(tmp_path)

    out = communicator(state)

    messages = out["messages"]
    tasks = out["task_history"]

    # 1) 마지막 AI 메시지가 우리가 넣은 QA 답변인지 확인
    last_ai = next(m for m in reversed(messages) if isinstance(m, AIMessage))

    qa_text = str(last_ai.content).strip()
    assert qa_text  # 비어 있지 않은지만 체크
    assert "키성장 건강기능식품" in qa_text

    # 2) qa_direct_reply 플래그는 모두 내려갔는지
    assert out.get("qa_direct_reply") is False
    assert (state.get("flags") or {}).get("qa_direct_reply") is False
    assert state.get("qa_direct_reply") is False

    # 3) communicator 태스크가 done 처리되었는지
    comm_tasks = [t for t in tasks if t.agent == "communicator"]
    assert comm_tasks
    assert all(t.done for t in comm_tasks)

    # 4) 파일이 실제로 저장되었는지, 내용이 QA 텍스트와 일치하는지
    last_path = state.get("last_saved_path")
    assert last_path, "last_saved_path 가 설정되어야 합니다."
    p = Path(last_path)
    assert p.exists()
    saved = p.read_text(encoding="utf-8").strip()
    assert "키성장 건강기능식품" in saved