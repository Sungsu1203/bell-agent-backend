# core/topic.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os, hashlib, re
from typing import Any
from core.state_types import State
from core.paths import topic_dir         # 프로젝트에서 제공 중인 함수로 가정
from core.config import load_research_objectives_from_env  # 없으면 아래 주석 참고
from utils.text_utils import slugify as _slugify

def topic_slug_from(text: str) -> str:
    from datetime import datetime
    base = _slugify(text or "untitled")
    return f"{base}-{datetime.now().strftime('%Y%m%d-%H%M')}"

def ascii_namespace(seed: str) -> str:
    core = hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()[:10]
    return f"ns-{core}"

def start_new_topic(state: State, title: str, outline_fname: str | None = None) -> State:
    """새 토픽 세션을 초기화하고, 디렉토리/ENV/state를 일관되게 세팅."""
    slug = topic_slug_from(title)
    ns = ascii_namespace(slug)

    state["topic_title"] = title
    state["topic_slug"] = slug
    state["chroma_ns"] = ns
    state["outline_fname"] = outline_fname or state.get("outline_fname") or "outline.md"
    state["outline_shown"] = False
    state["references"] = {"queries": [], "docs": []}
    state["last_saved_path"] = ""

    # 폴더 준비
    os.makedirs(topic_dir(slug), exist_ok=True)

    # RAG 경로 ENV 주입
    os.environ["CHROMA_NAMESPACE"] = ns
    os.environ["CHROMA_DIR"] = topic_dir(slug)

    # 연구 목적 초기화(옵션)
    if os.getenv("RESET_OBJECTIVES_ON_NEW_TOPIC", "1") == "1":
        # core.config에 아래 헬퍼가 없다면: 
        #   def load_research_objectives_from_env(prefix="BLOCKAGI_OBJECTIVE_"): ...
        state["research_objectives"] = load_research_objectives_from_env()
        state["research_round"] = 0
        state["no_new_url_streak"] = 0

    return state

def sanitize_title(raw: str) -> str:
    """
    '새 보고서/프로젝트 작성:' 같은 머리표기나 '작성:','write:' 접두를 제거하고
    양 끝 불필요한 기호를 정리.
    """
    s = (raw or "")
    s = re.sub(r'^\s*(새\s*(보고서|프로젝트)\s*(작성)?\s*)[:：]?\s*', '', s, flags=re.I)
    while re.match(r'^\s*(작성|write)\s*[:：]\s*', s, flags=re.I):
        s = re.sub(r'^\s*(작성|write)\s*[:：]\s*', '', s, flags=re.I)
    return s.strip(' :\u3000-—–')