from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import json
import pickle
import os
from pathlib import Path
from dataclasses import is_dataclass, asdict
from typing import Any, Dict, Mapping, Optional, Tuple, cast

# CFG/경로 유틸(동적 접근)
import core.config as config
from core.paths import research_topic_dir


# ─────────────────────────────────────────────────────────────
# Dynamic CFG helpers (reload_config() 이후 런타임 값 반영)
# ─────────────────────────────────────────────────────────────
def _get_cfg_attr(name: str, default: Any) -> Any:
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default

def _cfg_str(name: str, env: str, default: str) -> str:
    v = _get_cfg_attr(name, None)
    if v is not None:
        try:
            s = str(v).strip()
            if s:
                return s
        except Exception:
            pass
    return (os.getenv(env, default) or default).strip()

def _cfg_int(name: str, env: str, default: int) -> int:
    s = _cfg_str(name, env, str(default))
    try:
        return int(s)
    except Exception:
        try:
            return int(float(s))
        except Exception:
            return default

def _cfg_bool(name: str, env: str, default: bool) -> bool:
    """CFG → ENV → default 순으로 불리언을 안전 파싱."""
    v = _get_cfg_attr(name, None)
    # 1) CFG가 bool이면 그대로
    if isinstance(v, bool):
        return v
    # 2) CFG가 존재하면 문자열로 변환해 판독
    if v is not None:
        s = str(v).strip().lower()
        if s:
            return s in {"1", "true", "yes", "on", "y"}
    # 3) ENV 폴백 (None 안전 처리)
    ev = os.getenv(env)
    if ev is not None:
        s = str(ev).strip().lower()
        if s:
            return s in {"1", "true", "yes", "on", "y"}
    # 4) 기본값
    return default

def _to_plain(x: Any) -> Any:
    """메시지/태스크 등 직렬화 보조: JSON 스냅샷 가독성 향상."""
    # LangChain BaseMessage 유형을 선택적으로 로드.
    # 타입 심볼에 None을 대입하지 않기 위해 "검사 대상 타입들의 튜플" 패턴 사용.
    _lc_msg_types: tuple[type, ...] = ()
    try:
        from langchain_core.messages import BaseMessage as _BM
        _lc_msg_types = (_BM,)
    except Exception:
        _lc_msg_types = ()

    # Pydantic v2
    if hasattr(x, "model_dump") and callable(getattr(x, "model_dump")):
        return x.model_dump()
    # Pydantic v1
    if hasattr(x, "dict") and callable(getattr(x, "dict")):
        return x.dict()
    # LangChain 메시지
    if _lc_msg_types and isinstance(x, _lc_msg_types):
        return {
            "type": x.__class__.__name__,
            "content": getattr(x, "content", ""),
        }
    # dataclass
    if is_dataclass(x) and not isinstance(x, type):
        return asdict(x)
    # 기본타입/사전/리스트는 그대로
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if isinstance(x, dict):
        return {k: _to_plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_to_plain(v) for v in x]
    # 마지막 수단
    return str(x)


def _decide_topic_slug(state: Mapping[str, Any] | None) -> str:
    """topic_slug 우선순위: state → CFG.TOPIC_SLUG → 'default'"""
    if isinstance(state, Mapping):
        cand = state.get("topic_slug")
        if isinstance(cand, str) and cand.strip():
            return cand.strip()
    cfg_slug = (_cfg_str("TOPIC_SLUG", "TOPIC_SLUG", "") or "").strip()
    return cfg_slug or "default"


def _resolve_state_dir(base_dir: Optional[str | Path], state: Mapping[str, Any] | None) -> Path:
    """
    base_dir가 주어지지 않으면 기본 경로를 선택:
    - CFG.STATE_OUT_DIR가 설정되면: <STATE_OUT_DIR>/state
    - 기본: research_topic_dir(topic_slug)/state
    """
    if isinstance(base_dir, (str, Path)) and str(base_dir).strip():
        return Path(str(base_dir)).expanduser().resolve() / "state"
    # CFG/ENV 기반 사용자 지정 루트
    custom_root = _cfg_str("STATE_OUT_DIR", "STATE_OUT_DIR", "")
    if custom_root:
        return Path(custom_root).expanduser().resolve() / "state"
    topic_slug = _decide_topic_slug(state)
    return research_topic_dir(topic_slug) / "state"


def get_state_dir(base_dir: Optional[str | Path] = None, state: Mapping[str, Any] | None = None) -> Path:
    """외부용 헬퍼: 최종 state 디렉터리만 반환."""
    return _resolve_state_dir(base_dir, state)


def get_state_paths(
    base_dir: Optional[str | Path] = None,
    state: Mapping[str, Any] | None = None,
    fname: str = "last_state.pkl",
) -> Tuple[Path, Path]:
    """
    최종 저장될 (pickle_path, json_snapshot_path) 반환.
    디렉터리는 생성하지 않는다.
    """
    outdir = _resolve_state_dir(base_dir, state)
    # 파일명/스냅샷명은 CFG/ENV로 오버라이드 가능
    pkl_name = (fname or "").strip() or _cfg_str("STATE_PICKLE_NAME", "STATE_PICKLE_NAME", "last_state.pkl")
    json_name = _cfg_str("STATE_JSON_NAME", "STATE_JSON_NAME", "last_state.json")
    return (outdir / pkl_name, outdir / json_name)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding=encoding) as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save_state(
    base_dir: Optional[str | Path],
    state: Mapping[str, Any],
    fname: str = "last_state.pkl",
) -> None:
    """
    상태를 pickle/JSON으로 저장(원자적 쓰기).
    - base_dir: None/"" 면 CFG 기반 기본 경로(연구 토픽 디렉터리 하위 /state 또는 STATE_OUT_DIR/state)
    - fname: pickle 파일명 (기본 last_state.pkl)
    - JSON 스냅샷은 항상 last_state.json로 함께 저장
    """
    try:
        pkl_path, json_path = get_state_paths(base_dir, state, fname)

        # 직렬화 옵션을 런타임에서 읽음
        use_json = _cfg_bool("STATE_SAVE_JSON_SNAPSHOT", "STATE_SAVE_JSON_SNAPSHOT", True)
        json_indent = _cfg_int("STATE_JSON_INDENT", "STATE_JSON_INDENT", 2)
        json_ascii = _cfg_bool("STATE_JSON_ASCII", "STATE_JSON_ASCII", False)
        pkl_protocol = _cfg_int("STATE_PICKLE_PROTOCOL", "STATE_PICKLE_PROTOCOL", pickle.HIGHEST_PROTOCOL)

        # 1) 원본 그대로 pickle
        _atomic_write_bytes(pkl_path, pickle.dumps(dict(state), protocol=pkl_protocol))
        logger.debug("[state_io] pickle saved → %s", pkl_path.as_posix())

        # 2) 읽기 편한 JSON 스냅샷(옵션)
        if use_json:
            snap = {k: _to_plain(v) for k, v in dict(state).items()}
            _atomic_write_text(json_path, json.dumps(snap, ensure_ascii=json_ascii, indent=json_indent))
            logger.debug("[state_io] json snapshot saved → %s", json_path.as_posix())

    except Exception as e:
        logger.warning("[state_io] save_state 실패: %s", e, exc_info=True)


def load_state(
    base_dir: Optional[str | Path],
    state_hint: Mapping[str, Any] | None = None,
    fname: str = "last_state.pkl",
    *,
    prefer: str = "pkl",   # "pkl" | "json"
) -> Dict[str, Any]:
    """
    저장된 상태를 로드.
    - prefer='pkl'이면 피클 우선, 실패 시 JSON 시도(반대도 동일).
    - 파일 없으면 빈 dict 반환.
    """
    pkl_path, json_path = get_state_paths(base_dir, state_hint, fname)

    def _load_pkl() -> Dict[str, Any]:
        if not pkl_path.exists():
            return {}
        with open(pkl_path, "rb") as f:
            obj = pickle.load(f)
        return state_as_mapping(obj)

    def _load_json() -> Dict[str, Any]:
        if not json_path.exists():
            return {}
        with open(json_path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return state_as_mapping(obj)

    if prefer.lower() == "json":
        try:
            data = _load_json()
            if data:
                return data
        except Exception as e:
            logger.debug("[state_io] json load failed: %s", e)
        try:
            return _load_pkl()
        except Exception as e:
            logger.debug("[state_io] pickle load failed: %s", e)
            return {}
    else:
        try:
            data = _load_pkl()
            if data:
                return data
        except Exception as e:
            logger.debug("[state_io] pickle load failed: %s", e)
        try:
            return _load_json()
        except Exception as e:
            logger.debug("[state_io] json load failed: %s", e)
            return {}


def state_as_mapping(s: Any) -> Dict[str, Any]:
    """여러 타입(Pydantic/dataclass/객체)을 Dict로 완화."""
    if s is None:
        return {}
    if isinstance(s, dict):
        return s
    if hasattr(s, "model_dump") and callable(getattr(s, "model_dump")):  # pydantic v2
        out = s.model_dump()
        return dict(out) if isinstance(out, dict) else {}
    if hasattr(s, "dict") and callable(getattr(s, "dict")):             # pydantic v1
        out = s.dict()
        return dict(out) if isinstance(out, dict) else {}
    if is_dataclass(s) and not isinstance(s, type):
        return asdict(s)
    d = getattr(s, "__dict__", None)
    return dict(d) if isinstance(d, dict) else {}
