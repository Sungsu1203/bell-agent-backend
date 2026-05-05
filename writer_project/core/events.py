# core/events.py
# 사용자 관점 진행 이벤트 버퍼 — supervisor / web_search / vector_qa 등
# 노드 진입 시 한국어 라벨을 emit_event 로 적재.
# /api/events 가 cursor 폴링으로 읽어 frontend LogPanel 헤더에 노출.

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

_EVENT_MAX = int(os.getenv("WEB_EVENT_MAX", "200"))
_EVENT_BUF: Deque[Tuple[int, float, str, str, Optional[str]]] = deque(maxlen=_EVENT_MAX)
_EVENT_SEQ = 0
_EVENT_LOCK = threading.Lock()


def emit_event(label: str, kind: str = "phase", detail: Optional[str] = None) -> None:
    """
    사용자 관점 진행 이벤트 적재.
    - label: 한국어 라벨 (예: "웹 검색", "섹션 본문 작성")
    - kind: "phase" | "start" | "done" | "error"
    - detail: 부가 설명 (선택)
    """
    global _EVENT_SEQ
    with _EVENT_LOCK:
        _EVENT_SEQ += 1
        _EVENT_BUF.append((_EVENT_SEQ, time.time(), str(label), str(kind), detail))


def get_events_since(cursor: int = 0, limit: int = 200) -> Tuple[int, List[Dict[str, Any]]]:
    """
    cursor 보다 큰 seq 만 반환. (next_cursor, lines)

    호출자 cursor 가 현재 _EVENT_SEQ 보다 크면 (= 새 명령으로 clear_events 가 seq 를 되돌린 직후)
    next_cursor 를 현재 _EVENT_SEQ 로 반환해 프런트 reset 감지에 사용된다.
    """
    limit = max(1, min(int(limit or 200), 500))
    c = int(cursor or 0)
    with _EVENT_LOCK:
        # ── reset 감지: caller cursor 가 현재 seq 보다 앞서있으면 backend 가 reset 됐다는 신호
        if c > _EVENT_SEQ:
            return _EVENT_SEQ, []

        out: List[Dict[str, Any]] = [
            {"seq": seq, "ts": ts, "label": label, "kind": kind, "detail": detail}
            for (seq, ts, label, kind, detail) in _EVENT_BUF
            if seq > c
        ]
        if len(out) > limit:
            out = out[-limit:]
        next_cursor = out[-1]["seq"] if out else c
    return next_cursor, out


def clear_events() -> None:
    global _EVENT_SEQ
    with _EVENT_LOCK:
        _EVENT_BUF.clear()
        _EVENT_SEQ = 0


def latest_event() -> Optional[Dict[str, Any]]:
    """마지막 이벤트 (없으면 None)."""
    with _EVENT_LOCK:
        if not _EVENT_BUF:
            return None
        seq, ts, label, kind, detail = _EVENT_BUF[-1]
    return {"seq": seq, "ts": ts, "label": label, "kind": kind, "detail": detail}
