# core/topic.py
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import os, hashlib, re
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING, cast, Callable

from core.state_types import State
if TYPE_CHECKING:  # 타입체커 전용 (런타임 순환 의존 방지)
    from core.state_types import WriterFlags, Flags

from core.paths import topic_dir
import core.config as config
from utils.text_utils import slugify as _slugify


def topic_slug_from(text: str) -> str:
    """사람 친화 슬러그 + 타임스탬프"""
    from datetime import datetime
    base = _slugify(text or "untitled")
    return f"{base}-{datetime.now().strftime('%Y%m%d-%H%M')}"

def ascii_namespace(seed: str) -> str:
    """토픽 네임스페이스(벡터DB/캐시 세그먼트용)"""
    core = hashlib.sha1(seed.encode("utf-8", "ignore")).hexdigest()[:10]
    return f"ns-{core}"

def _get_cfg_attr(name: str, default: Any) -> Any:
    """config.CFG → config 모듈 속성 → default 순으로 동적 조회."""
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default

def _cfg_str(name: str, default: str = "") -> str:
    v = _get_cfg_attr(name, default)
    try:
        s = str(v).strip()
        return s if s else default
    except Exception:
        return default

def _cfg_bool(name: str, default: bool = False) -> bool:
    v = _get_cfg_attr(name, default)
    if isinstance(v, bool):
        return v
    try:
        return str(v).strip().lower() in {"1", "true", "yes", "on", "y"}
    except Exception:
        return default

def _cfg_int(name: str, default: int = 0) -> int:
    v = _get_cfg_attr(name, default)
    try:
        if isinstance(v, int):
            return v
        return int(float(str(v)))
    except Exception:
        return default

def _default_outline_name() -> str:
    """DOC_MODE에 따른 outline 기본 파일명 (동적 조회)."""
    mode = (_cfg_str("DOC_MODE", "report") or "report").lower()
    return "outline_book.md" if mode == "book" else "outline_report.md"

def _reset_writer_flags(state: State) -> None:
    """writer 잠금·요청 타이틀 등 리셋(새 토픽에서의 교착 방지)"""
    try:
        # flags는 Union[Flags, Dict[str, Any]]로 운용 → Dict로 완화 후 갱신
        f: dict[str, Any] = dict(state.get("flags") or {})
        for k in ("pending_write_title", "requested_write_title", "suppress_vector_qa"):
            if k in f:
                f.pop(k, None)
        # TypedDict(Flags)로 캐스팅하여 대입
        state["flags"] = cast("Flags", f)

        wf: dict[str, Any] = dict(state.get("writer_flags") or {})
        for k in ("pending_write_title", "requested_write_title"):
            wf.pop(k, None)
        # TypedDict(WriterFlags)로 캐스팅하여 대입
        state["writer_flags"] = cast("WriterFlags", wf)
    except Exception as e:
        logger.debug("[topic] reset_writer_flags skipped: %s", e)

def start_new_topic(state: State, title: str, outline_fname: Optional[str] = None) -> State:
    """
    새 토픽 세션 초기화:
    - 슬러그/네임스페이스/로컬 디렉터리 생성
    - outline 기본 파일명(DOC_MODE 반영) 결정
    - refs/round/flags 등 일관 초기화
    - (옵션) ENV 미러링(CFG.MIRROR_STATE_TO_ENV)
    """
    # ── 식별자 생성
    slug = topic_slug_from(title)
    ns = ascii_namespace(slug)

    # ── 기본 상태 설정
    state["topic_title"] = title
    state["topic_slug"] = slug
    state["chroma_ns"] = ns

    # DOC_MODE에 따라 outline 기본값 선택
    fname = (outline_fname or state.get("outline_fname") or _default_outline_name())
    state["outline_fname"] = fname
    state["outline_shown"] = False

    # 참조 컨테이너 초기화
    state["references"] = {"queries": [], "docs": []}
    state["last_saved_path"] = ""

    # 진행률/락 플래그 초기화
    _reset_writer_flags(state)
    # 새 토픽에서는 연구 루프/직답 모드 끄기
    state["research_loop_active"] = False
    state["qa_direct_reply"] = False

    # 진행률 카운터 초기화(선택 키만)
    flags: dict[str, Any] = dict(state.get("flags") or {})
    for k in ("sections_done", "sections_total", "sections_seen",
              "chapters_done", "chapters_total", "chapters_seen"):
        flags.pop(k, None)
    # topic_title을 flags에도 미러링(일부 모듈은 flags.topic_title만 참조)
    flags["topic_title"] = title
    state["flags"] = flags

    # ── 토픽별 로컬 폴더 준비
    chroma_dir = topic_dir(slug)
    Path(chroma_dir).mkdir(parents=True, exist_ok=True)
    state["chroma_dir"] = chroma_dir

    # ── ENV 미러링(옵션)
    if _cfg_bool("MIRROR_STATE_TO_ENV", True):
        os.environ["CHROMA_NAMESPACE"] = ns
        os.environ["CHROMA_DIR"] = chroma_dir
        logger.debug("[topic] mirrored CHROMA_* to env (ns=%s dir=%s)", ns, chroma_dir)

    # ── 연구 목표/라운드 초기화 정책
    if _cfg_bool("RESET_OBJECTIVES_ON_NEW_TOPIC", True):
        # 환경 변수 기반 목표 시드 로더(있으면 사용)
        loader: Optional[Callable[[], list[str]]] = None
        try:
            loader = getattr(config, "load_research_objectives_from_env", None)  
        except Exception:
            loader = None
        try:
            state["research_objectives"] = loader() if callable(loader) else []
        except Exception:
            state["research_objectives"] = []
        state["research_round"] = 0
        state["no_new_url_streak"] = 0
    else:
        # 유지 모드에서도 라운드 카운터는 새로 시작하는 게 안전
        state["research_round"] = 0
        state["no_new_url_streak"] = 0

    # ── iteration/role 기본값 힌트(상위 가드가 없을 경우 대비)
    if "iteration_count" not in state:
        state["iteration_count"] = _cfg_int("ITERATION_COUNT", 0)
    if "agent_role" not in state or not str(state.get("agent_role") or "").strip():
        state["agent_role"] = _cfg_str("BLOCKAGI_AGENT_ROLE", "")

    logger.info(
        "[topic] new topic started: title=%r slug=%s ns=%s outline=%s role=%s iters=%s",
        title, slug, ns, fname, state.get("agent_role"), state.get("iteration_count"),
    )
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
