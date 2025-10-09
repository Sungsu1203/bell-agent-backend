from __future__ import annotations
import json
import pickle
from pathlib import Path
from dataclasses import is_dataclass, asdict
from typing import Any, Dict, Mapping, cast

def _to_plain(x: Any) -> Any:
    # 메시지/태스크 등 직렬화 보조
    try:
        from langchain_core.messages import BaseMessage
    except Exception:
        BaseMessage = tuple()  # fallback

    # Pydantic v2
    if hasattr(x, "model_dump") and callable(x.model_dump):
        return x.model_dump()
    # Pydantic v1
    if hasattr(x, "dict") and callable(x.dict):
        return x.dict()
    # LangChain 메시지
    if BaseMessage and isinstance(x, BaseMessage):
        return {"type": x.__class__.__name__, "content": getattr(x, "content", "")}
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

def save_state(base_dir: str, state: Mapping[str, Any], fname: str = "last_state.pkl") -> None:
    try:
        outdir = Path(base_dir) / "state"
        outdir.mkdir(parents=True, exist_ok=True)

        # 1) 원본 그대로 pickle (필터링 없음)
        with open(outdir / fname, "wb") as f:
            pickle.dump(dict(state), f)

        # 2) 읽기 편한 JSON 스냅샷도 추가
        snap = {k: _to_plain(v) for k, v in dict(state).items()}
        with open(outdir / "last_state.json", "w", encoding="utf-8") as jf:
            json.dump(snap, jf, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"[WARN] save_state 실패: {e}")

def state_as_mapping(s: Any) -> Dict[str, Any]:
    if s is None:
        return {}
    if isinstance(s, dict):
        return s
    if hasattr(s, "model_dump") and callable(s.model_dump):  # pydantic v2
        out = s.model_dump()
        return dict(out) if isinstance(out, dict) else {}
    if hasattr(s, "dict") and callable(s.dict):              # pydantic v1
        out = s.dict()
        return dict(out) if isinstance(out, dict) else {}
    if is_dataclass(s) and not isinstance(s, type):
        return asdict(s)
    d = getattr(s, "__dict__", None)
    return dict(d) if isinstance(d, dict) else {}