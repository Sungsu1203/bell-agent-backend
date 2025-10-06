from __future__ import annotations
import pickle
from pathlib import Path
from dataclasses import is_dataclass, asdict
from typing import Any, Dict, Mapping, cast

def save_state(base_dir: str, state: Mapping[str, Any], fname: str = "last_state.pkl") -> None:
    try:
        outdir = Path(base_dir) / "state"
        outdir.mkdir(parents=True, exist_ok=True)
        with open(outdir / fname, "wb") as f:
            pickle.dump(dict(state), f)
    except Exception as e:
        print(f"[WARN] save_state 실패: {e}")

def state_as_mapping(s: Any) -> Dict[str, Any]:
    if s is None:
        return {}

    if isinstance(s, dict):
        return cast(Dict[str, Any], s)

    # Pydantic v2
    mdump = getattr(s, "model_dump", None)
    if callable(mdump):
        md: Any = mdump()
        if isinstance(md, dict):
            return cast(Dict[str, Any], md)
        if isinstance(md, Mapping):
            return dict(md)

    # Pydantic v1
    ddump = getattr(s, "dict", None)
    if callable(ddump):
        d: Any = ddump()
        if isinstance(d, dict):
            return cast(Dict[str, Any], d)
        if isinstance(d, Mapping):
            return dict(d)

    # dataclass 인스턴스만 허용 (클래스는 제외)
    if is_dataclass(s) and not isinstance(s, type):
        # asdict는 dataclass 인스턴스만 받음. 위에서 클래스 제외했지만
        # 타입 체커가 좁히지 못해 경고하므로 한 줄만 무시.
        return cast(Dict[str, Any], asdict(s))  # type: ignore[arg-type]

    # __dict__ 보유 객체
    dvars = getattr(s, "__dict__", None)
    if isinstance(dvars, dict):
        return cast(Dict[str, Any], dvars)

    if isinstance(s, Mapping):
        return dict(cast(Mapping[str, Any], s))

    return {}