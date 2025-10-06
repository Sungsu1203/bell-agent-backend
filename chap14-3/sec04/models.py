from pydantic import BaseModel, Field
from typing import Literal, Optional

# 추가: research 플로우에서 쓰는 에이전트 2종 포함
AgentName = Literal[
    "content_strategist",
    "communicator",
    "web_search_agent",
    "vector_search_agent",
    "chapter_writer",
    "section_writer",
    "research_planner",
    "research_synthesizer",
]

class Task(BaseModel):
    agent: AgentName = Field(
        ...,
        description=(
            "작업을 수행하는 agent의 종류.\n"
            "- content_strategist: 콘텐츠 전략/목차 작성·수정\n"
            "- communicator: 진행상황 보고 및 사용자 질의 응대\n"
            "- web_search_agent: 웹 검색으로 참고자료 수집\n"
            "- vector_search_agent: 벡터DB 검색(RAG)으로 참고자료 수집\n"
            "- chapter_writer: (책) 특정 챕터 본문 초안 작성\n"
            "- section_writer: (보고서) 특정 섹션 본문 초안 작성\n"
            "- research_planner: 리서치 라운드별 질의 설계/계획\n"
            "- research_synthesizer: 리서치 결과 요약/시사점 도출"
        ),
    )

    # LLM structured output 시 누락되더라도 파싱되게 기본값 제공
    done: bool = Field(False, description="종료 여부")
    description: str = Field("", description="해야 할 작업 설명(맥락/목표 포함 가능)")

    # 문자열로 유지(ISO 추천). 비어 있으면 미기록 상태로 간주
    done_at: str = Field("", description="작업 완료 시각(예: '2025-03-06 14:32:10')")

    def to_dict(self):
        return {
            "agent": self.agent,
            "done": self.done,
            "description": self.description,
            "done_at": self.done_at,
        }
