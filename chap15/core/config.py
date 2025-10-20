# core/config.py
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Final, Literal, cast, Any, get_args, TypeAlias

logger = logging.getLogger(__name__)

# ── 타입 ───────────────────────────────────────────────────────
DocMode = Literal["book", "report"]
ActionMode = Literal["full_write", "research_only", "direct_qa", "write_only"]

# 외부(Enum/상수 등) 정의와 독립적인 로컬 타입 에일리어스
AgentNameT: TypeAlias = Literal[
    "supervisor", "content_strategist", "communicator",
    "web_search_agent", "vector_search_agent", "section_writer",
    "chapter_writer", "research_planner", "research_synthesizer"
]

# ── PROJECT_ROOT ───────────────────────────────────────────────
PROJECT_ROOT: Final[str] = str(Path(__file__).resolve().parents[1])

# ── ENV 파서 헬퍼 ─────────────────────────────────────────────
def _str_env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v.strip() if v is not None else default

def _int_env(name: str, default: int) -> int:
    try:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        return int(raw.strip())
    except Exception:
        return default

def _bool_env(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")

def _csv_to_set(raw: str) -> set[str]:
    if not raw:
        return set()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}

# ── Config ────────────────────────────────────────────────────
class Config:
    """
    시스템 전체 설정을 관리하는 단일 진실 공급원(SSOT).
    모든 런타임 옵션은 이 객체를 통해 접근합니다.
    """

    # 1) CLI/ENV 입력
    task_description: str
    topic_slug: str
    doc_mode: DocMode
    action_mode: ActionMode
    iteration_count: int
    recursion_limit: int

    # 2) 내부 파생 설정
    initial_agent_name: AgentNameT | None
    writer_agent_name: AgentNameT
    is_direct_qa: bool

    # 3) 로깅/출력
    log_topk: int
    log_dashboard: bool
    log_wrap: int
    human_logs_verbose: bool

    # 4) 게이트키핑
    gate_keep_sources: bool
    allowed_domains: str
    allow_subdomains: bool

    def __init__(self, **kwargs: Any):
        """
        app.py의 argparse 결과를 kwargs로 받아 초기화.
        미지정 항목은 환경변수 → 기본값 순으로 결정합니다.
        """

        # --- 기본 입력 ---
        self.task_description = kwargs.pop("task", _str_env("INITIAL_TASK", "시장 보고서 초안 작성"))
        self.topic_slug = kwargs.pop("topic_slug", _str_env("TOPIC_SLUG", "default"))

        mode_raw = kwargs.pop("mode", _str_env("DOC_MODE", "report")).lower()
        self.doc_mode = cast(DocMode, mode_raw if mode_raw in get_args(DocMode) else "report")

        action_raw = kwargs.pop("action", _str_env("INITIAL_ACTION", "full_write")).lower()
        self.action_mode = cast(ActionMode, action_raw if action_raw in get_args(ActionMode) else "full_write")

        # --- 로깅/일반 ---
        self.iteration_count = kwargs.pop("iteration_count", _int_env("ITERATION_COUNT", 3))
        self.recursion_limit = kwargs.pop("recursion_limit", _int_env("RECURSION_LIMIT", 200))

        self.log_topk = kwargs.pop("log_topk", _int_env("LOG_TOPK", 3))
        self.log_dashboard = kwargs.pop("log_dashboard", _bool_env("LOG_DASHBOARD", True))
        self.log_wrap = kwargs.pop("log_wrap", _int_env("LOG_WRAP", 88))
        self.human_logs_verbose = kwargs.pop("human_logs_verbose", _bool_env("HUMAN_LOGS_VERBOSE", False))

        # --- 게이트키핑 ---
        gatekeep_cli = kwargs.pop("gatekeep", None)  # Optional[bool]
        default_gatekeep = _bool_env("GATE_KEEP_SOURCES", False)
        self.gate_keep_sources = default_gatekeep if gatekeep_cli is None else bool(gatekeep_cli)

        self.allowed_domains = kwargs.pop("allow_domains", _str_env("ALLOWED_DOMAINS", ""))

        subdomains_cli = kwargs.pop("allow_subdomains", None)  # Optional[bool]
        default_subdomains = _bool_env("ALLOW_SUBDOMAINS", False)
        self.allow_subdomains = default_subdomains if subdomains_cli is None else bool(subdomains_cli)

        # --- Writer 결정 & Action 플래그 ---
        self.writer_agent_name = cast(
            AgentNameT, "section_writer" if self.doc_mode == "report" else "chapter_writer"
        )
        self._set_action_flags()

        logger.info(
            "Config loaded | mode=%s action=%s writer=%s topic=%s",
            self.doc_mode, self.action_mode, self.writer_agent_name, self.topic_slug
        )

    # 내부: action_mode에 따른 흐름 제어 플래그
    def _set_action_flags(self) -> None:
        self.is_direct_qa = False
        self.initial_agent_name = None

        if self.action_mode == "direct_qa":
            self.is_direct_qa = True
            self.initial_agent_name = cast(AgentNameT, "communicator")
        elif self.action_mode == "research_only":
            self.initial_agent_name = cast(AgentNameT, "research_planner")
        elif self.action_mode == "write_only":
            self.initial_agent_name = self.writer_agent_name
        else:  # "full_write"
            self.initial_agent_name = cast(AgentNameT, "content_strategist")

    # 게이트키핑에서 바로 사용 가능한 프로퍼티
    @property
    def allowed_domains_set(self) -> set[str]:
        return _csv_to_set(self.allowed_domains)

    # 로깅/테스트 편의용
    def as_dict(self) -> dict[str, Any]:
        return {
            "task_description": self.task_description,
            "topic_slug": self.topic_slug,
            "doc_mode": self.doc_mode,
            "action_mode": self.action_mode,
            "iteration_count": self.iteration_count,
            "recursion_limit": self.recursion_limit,
            "initial_agent_name": self.initial_agent_name,
            "writer_agent_name": self.writer_agent_name,
            "is_direct_qa": self.is_direct_qa,
            "log_topk": self.log_topk,
            "log_dashboard": self.log_dashboard,
            "log_wrap": self.log_wrap,
            "human_logs_verbose": self.human_logs_verbose,
            "gate_keep_sources": self.gate_keep_sources,
            "allowed_domains": self.allowed_domains,
            "allow_subdomains": self.allow_subdomains,
            "project_root": PROJECT_ROOT,
        }
# ── Legacy compatibility (optional) ───────────────────────────
# 과거 코드에서 'from core.config import DOC_MODE'를 사용할 수 있으므로 얇은 상수 제공
DOC_MODE: Final[str] = (os.getenv("DOC_MODE", "report") or "report").strip().lower()
