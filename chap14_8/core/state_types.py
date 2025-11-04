from __future__ import annotations
from typing import List, Optional, Dict, Any, TypedDict, Literal, NotRequired, Required, MutableMapping, Union, Mapping

import logging
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────
# DocMode: core.config.DocMode과 동일 리터럴(순환 의존 방지용 로컬 정의)
# ────────────────────────────────────────────────────────────────────────────
DocMode = Literal["report", "book"]

# ────────────────────────────────────────────────────────────────────────────
# References 컨테이너(실사용 키만 경량 모델링)
# ────────────────────────────────────────────────────────────────────────────
class References(TypedDict, total=False):
    queries: List[str]
    docs: List[Any]  # RAG 문서 오브젝트(LC Document 등) 또는 dict

# ────────────────────────────────────────────────────────────────────────────
# Planner 산출 구조
# ────────────────────────────────────────────────────────────────────────────
class ResearchPlan(TypedDict, total=False):
    round: int
    objective: str
    queries: List[str]
    timestamp: str

# ────────────────────────────────────────────────────────────────────────────
# Flags (자주 쓰는 키만 선언, 확장 가능)
# ────────────────────────────────────────────────────────────────────────────
class WriterFlags(TypedDict, total=False):
    pending_write_title: bool
    requested_write_title: str

# NOTE:
#  - Flags는 '자주 쓰는' 키만 문서화합니다(= total=False).
#  - 실제 런타임에선 flags에 임시/추가 키가 들어갈 수 있으므로
#    State.flags는 Dict[str, Any]도 허용(Union)하여 TypedDict 엄격성으로 인한
#    "Could not assign item in TypedDict" 오류를 회피합니다.
class Flags(TypedDict, total=False):
    # writer 잠금/요청
    pending_write_title: bool
    requested_write_title: str
    suppress_vector_qa: bool

    # 진행률(보고서/책 공용)
    sections_done: int
    sections_total: int
    sections_seen: str
    chapters_done: int
    chapters_total: int
    chapters_seen: str

    # 대시보드/제어
    dash_last_ts: float
    dash_count: int
    skip_web_search: bool
    debug: Dict[str, Any]

    # 메타
    topic_title: str
    iteration_count: int
    last_saved_report: str   # ← 추가

    # 라우터 내부 재시도/상태 저장용 네임스페이스(동적 확장 허용)
    router: NotRequired[MutableMapping[str, Any]]

# ────────────────────────────────────────────────────────────────────────────
# 상태 객체
# ────────────────────────────────────────────────────────────────────────────
class State(TypedDict, total=False):
    # 필수 컨테이너
    messages: Required[List[Any]]
    task_history: List[Any]

    # 수집/참조 데이터
    references: References
    # 경량 레퍼런스(쿼리/URL 위주). web_search_agent에서 사용.
    refs: NotRequired[References]
    findings_md: NotRequired[List[str]]
    llm_logs: NotRequired[List[Dict[str, Any]]]
    facts_ctx: NotRequired[Optional[str]]

    # 토픽/아웃라인/산출물
    topic_title: NotRequired[str]
    topic_slug: NotRequired[str]          # 기본: CFG.TOPIC_SLUG
    chroma_ns: NotRequired[str]
    chroma_dir: NotRequired[str]
    outline_fname: NotRequired[str]
    outline_shown: NotRequired[bool]
    last_saved_path: NotRequired[str]

    # 작동 모드/역할/라운드
    doc_mode: NotRequired[DocMode]        # 기본: CFG.DOC_MODE
    agent_role: NotRequired[str]          # 기본: CFG.BLOCKAGI_AGENT_ROLE
    iteration_count: NotRequired[int]     # 기본: CFG.ITERATION_COUNT
    research_round: NotRequired[int]
    research_loop_active: NotRequired[bool]

    # 리서치 플래닝/목표
    research_plan: NotRequired[ResearchPlan]
    research_objectives: NotRequired[List[str]]  # 기본: CFG.RESEARCH_OBJECTIVES
    planner_queries: NotRequired[List[str]]

    # 신규 URL/조기중단 지표
    new_url_count: NotRequired[Optional[int]]
    new_url_count_round: NotRequired[int]
    round_new_urls: NotRequired[int]
    round_added_urls: NotRequired[int]
    no_new_url_streak: NotRequired[int]

    # 라우팅/플래그 모음
    qa_direct_reply: NotRequired[bool]
    local_ingested_once: NotRequired[bool]
    research_planner_announce: NotRequired[int]   # 기본: CFG.RESEARCH_PLANNER_ANNOUNCE (0/1)
    research_halt_threshold: NotRequired[int]     # 기본: CFG.RESEARCH_HALT_THRESHOLD
    research_min_rounds: NotRequired[int]         # 기본: CFG.RESEARCH_MIN_ROUNDS
    research_max_no_new_rounds: NotRequired[int]  # 기본: CFG.RESEARCH_MAX_NO_NEW_ROUNDS
    _vs_cleared_once: NotRequired[bool]
    # Flags는 문서화를 위한 TypedDict 제공하되,
    # 실제 저장/갱신 시 Dict[str, Any]를 허용해 타입 충돌을 방지합니다.
    flags: NotRequired[Union[Flags, Dict[str, Any]]]
    writer_flags: NotRequired[WriterFlags]

    # 인덱스 디스크 존재 플래그
    rag_on_disk: NotRequired[bool]
    # 다음 단계용 펜딩 라우팅(간단 문자열 리스트)
    pending: NotRequired[List[str]]


    # (옵션) CFG 스냅샷(디버그/리프로듀서용)
    cfg_snapshot: NotRequired[Dict[str, Any]]

    # ... 기존 필드 ...
    last_resources: NotRequired[List[str]]
    indexed_chunks_round: NotRequired[int]
    web_stage: NotRequired[Dict[str, Any]]

    router_error: NotRequired[str]

__all__ = ["DocMode", "References", "ResearchPlan", "WriterFlags", "Flags", "State"]
