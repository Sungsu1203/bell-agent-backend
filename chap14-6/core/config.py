# core/config.py
from __future__ import annotations
from typing import Final, Literal, cast
import os
from pathlib import Path
from core.models import AgentName  # ← 추가: AgentName 타입을 사용

# ── 타입 ───────────────────────────────────────────────────────
DocMode = Literal["book", "report"]
Mode = DocMode  # 기존 호환 유지

# ── DOC_MODE ───────────────────────────────────────────────────
def _doc_mode() -> DocMode:
    v = (os.getenv("DOC_MODE", "book") or "book").strip('"').strip().lower()
    return cast(DocMode, v if v in ("book", "report") else "report")

DOC_MODE: Final[DocMode] = _doc_mode()

# ── PROJECT_ROOT ───────────────────────────────────────────────
PROJECT_ROOT: Final[str] = str(Path(__file__).resolve().parents[1])

# ── Writer 기본 선택 ───────────────────────────────────────────
def preferred_writer_agent() -> AgentName:  # ← 반환 타입을 AgentName으로
    # literal 값이라 사실 cast 없어도 대부분의 타입체커에서 통과합니다.
    return cast(AgentName, "section_writer" if DOC_MODE == "report" else "chapter_writer")

WRITER_AGENT: Final[AgentName] = preferred_writer_agent()  # ← 상수 타입도 AgentName

def load_research_objectives_from_env(
    prefix: str = "BLOCKAGI_OBJECTIVE_",
    max_n: int = 10,
) -> list[str]:
    """
    BLOCKAGI_OBJECTIVE_1..N 환경변수에서 연구 목적을 읽어 리스트로 반환.
    예)
      BLOCKAGI_OBJECTIVE_1="시장 규모 파악"
      BLOCKAGI_OBJECTIVE_2="경쟁사 비교"
    """
    objs: list[str] = []
    for i in range(1, max_n + 1):
        v = os.getenv(f"{prefix}{i}")
        if v and v.strip():
            objs.append(v.strip())
    return objs
