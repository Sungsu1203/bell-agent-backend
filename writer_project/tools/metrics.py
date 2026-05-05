# tools/metrics.py
from __future__ import annotations
import os, time, json, threading, glob, atexit
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from queue import Queue, Full, Empty
import logging
logger = logging.getLogger(__name__)

_METRICS_LOCK = threading.Lock()

# ─────────────────────────────────────────────────────────────────────────────
# CFG/경로 정책
# ─────────────────────────────────────────────────────────────────────────────
try:
    from core.config import CFG  
except Exception:  # pragma: no cover
    class _Dummy:  # 최소 폴백
        pass
    CFG = _Dummy()  # type: ignore

from pathlib import Path
try:
    from core.paths import research_base_dir as _rbd  # 실제 구현 import
except Exception:  # pragma: no cover
    _rbd = None  # type: ignore[assignment]

def research_base_dir() -> Path:
    """항상 Path를 반환하도록 통일."""
    if _rbd is not None:
        p = _rbd()
        return p if isinstance(p, Path) else Path(str(p))
    # 폴백: CWD/research
    return Path.cwd() / "research"

# ─────────────────────────────────────────────────────────────────────────────
# 환경/설정: CFG → ENV → 기본값 (런타임 재평가 지원)
# ─────────────────────────────────────────────────────────────────────────────
def _truthy(v: object, *, default: bool = False) -> bool:
    if v is None:
        return default
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")

def _cfg_str(name: str, default: str = "") -> str:
    """CFG 우선, 없으면 ENV, 마지막 기본값. 공백은 무시."""
    try:
        cv = getattr(CFG, name, None)
        if cv is not None and str(cv).strip() != "":
            return str(cv).strip()
    except Exception:
        pass
    ev = os.getenv(name, "")
    return ev.strip() if ev and ev.strip() != "" else default

def _cfg_int(name: str, default: int = 0) -> int:
    try:
        cv = getattr(CFG, name, None)
        if cv is not None and str(cv).strip() != "":
            return int(str(cv).strip())
    except Exception:
        pass
    try:
        ev = os.getenv(name, "")
        return int(ev.strip()) if ev and ev.strip() != "" else default
    except Exception:
        return default

def _cfg_float(name: str, default: float = 0.0) -> float:
    try:
        cv = getattr(CFG, name, None)
        if cv is not None and str(cv).strip() != "":
            return float(str(cv).strip())
    except Exception:
        pass
    try:
        ev = os.getenv(name, "")
        return float(ev.strip()) if ev and ev.strip() != "" else default
    except Exception:
        return default

def _cfg_bool(name: str, default: bool = False) -> bool:
    # CFG에 명시되면 우선 해석
    try:
        cv = getattr(CFG, name, None)
        if cv is not None:
            return _truthy(cv, default=default)
    except Exception:
        pass
    # ENV 폴백
    return _truthy(os.getenv(name), default=default)


def _enabled() -> bool:
    """
    메트릭 전역 토글. 아래 중 하나라도 참이면 비활성화:
    - DISABLE_METRICS=1
    - POSTHOG_DISABLED=1 또는 POSTHOG_DISABLE=1 (과거 텔레메트리 경로 호환)
    그 외: CFG.METRICS_ENABLED > ENV.METRICS_ENABLED (기본 on)
    """
    if _truthy(os.getenv("DISABLE_METRICS"), default=False):
        return False
    if _truthy(os.getenv("POSTHOG_DISABLED"), default=False):
        return False
    if _truthy(os.getenv("POSTHOG_DISABLE"), default=False):
        return False
    return _cfg_bool("METRICS_ENABLED", default=True)

def _now_ts() -> float:
    return time.time()

def _iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts or _now_ts()))

def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default

def _get_out_dir() -> str:
    """
    METRICS_OUT_DIR > research_base_dir()/metrics
    (snapshot(path=...)가 우선)
    """
    base = _cfg_str("METRICS_OUT_DIR", "")
    if base:
        return os.path.abspath(os.path.expanduser(base))
    return os.path.join(str(research_base_dir()), "metrics")

def _rotate_keep(dirpath: str, pattern: str, keep: int) -> None:
    if keep <= 0:
        return
    try:
        files = sorted(glob.glob(os.path.join(dirpath, pattern)))
        if len(files) <= keep:
            return
        for f in files[:-keep]:
            try:
                os.remove(f)
            except Exception:
                pass
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# 논블로킹 싱크(Queue + Worker)
# ─────────────────────────────────────────────────────────────────────────────
def _get_sink() -> str:
    """런타임 재평가되는 sink 종류: file|stdout|null"""
    s = _cfg_str("METRICS_SINK", os.getenv("METRICS_SINK", "file") or "file").lower()
    return s if s in ("file", "stdout", "null") else "file"

def _get_file() -> str:
    return _cfg_str("METRICS_FILE", os.getenv("METRICS_FILE", "logs/metrics.ndjson") or "logs/metrics.ndjson")

def _get_qsize() -> int:
    return max(1, _cfg_int("METRICS_QUEUE_SIZE", int(os.getenv("METRICS_QUEUE_SIZE") or "1024")))

def _get_flush_interval() -> float:
    return max(0.05, _cfg_float("METRICS_FLUSH_SEC", float(os.getenv("METRICS_FLUSH_SEC") or "0.5")))

def _get_events_max() -> int:
    return max(0, _cfg_int("METRICS_EVENTS_MAX", int(os.getenv("METRICS_EVENTS_MAX") or "500")))

_Q: "Queue[dict]" = Queue(maxsize=_get_qsize())
_WORKER_STARTED = False
_STOP = False
_FH = None  # lazy-opened file handle for "file" sink

def _start_worker_once() -> None:
    global _WORKER_STARTED
    if not _enabled():
        return
    if _get_sink() == "null":
        return
    if _WORKER_STARTED:
        return
    _WORKER_STARTED = True
    th = threading.Thread(target=_worker, name="metrics-worker", daemon=True)
    th.start()
    atexit.register(_shutdown)

def _emit(ev: dict) -> None:
    """메인 스레드에서 절대 블로킹하지 않음. 큐가 가득 차면 조용히 드롭."""
    if not _enabled() or _get_sink() == "null":
        return
    _start_worker_once()
    try:
        _Q.put_nowait(ev)
    except Full:
        # 드롭(백프레셔를 메인으로 전파하지 않음)
        pass

def _worker() -> None:
    global _FH
    while not _STOP:
        try:
            try:
                item = _Q.get(timeout=_get_flush_interval())
            except Empty:
                item = None
            if not item:
                continue

            op = item.get("__op__")
            if op == "snapshot":
                # 스냅샷은 워커에서 파일 I/O
                _do_snapshot_file(item.get("path"), rotate_keep=int(item.get("rotate_keep") or 0))
                continue

            # 일반 이벤트는 NDJSON 라인으로 기록
            sink = _get_sink()
            if sink == "stdout":
                try:
                    print(json.dumps(item, ensure_ascii=False), flush=False)
                except Exception:
                    pass
            elif sink == "file":
                try:
                    if _FH is None:
                        fpath = _get_file()
                        os.makedirs(os.path.dirname(fpath), exist_ok=True)
                        _FH = open(fpath, "a", encoding="utf-8")
                    _FH.write(json.dumps(item, ensure_ascii=False) + "\n")
                except Exception:
                    # 파일 쓰기 실패는 무시(드롭)
                    pass
        except Exception as e:
            try:
                logger.debug("[metrics.worker] error: %s", e)
            except Exception:
                pass

def _shutdown() -> None:
    global _STOP, _FH
    _STOP = True
    try:
        if _FH:
            _FH.flush()
            _FH.close()
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# 데이터 모델(집계)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class RoundAgg:
    # a) 검색 성공/실패
    queries_total: int = 0
    queries_zero_result: int = 0
    # b) gatekeep 차단
    gatekeep_blocked: int = 0
    gatekeep_total: int = 0
    # c) 백엔드 응답시간
    backend_lat_sum: Dict[str, float] = field(default_factory=dict)
    backend_lat_cnt: Dict[str, int] = field(default_factory=dict)
    # d) 소스 비율(웹/로컬)
    retrieved_web: int = 0
    retrieved_local: int = 0
    # f) 인덱싱 청크 평균 길이
    chunks_chars_sum: int = 0
    chunks_cnt: int = 0
    # g) 타임스탬프
    started_at: str = field(default_factory=lambda: _iso())
    updated_at: str = field(default_factory=lambda: _iso())

@dataclass
class Registry:
    rounds: Dict[str, RoundAgg] = field(default_factory=dict)  # key = round_id
    events: List[dict] = field(default_factory=list)           # 원시 이벤트(요약 UI용)
    cur_round_id: str = "default"
    topic_slug: Optional[str] = None

    def round(self) -> RoundAgg:
        with _METRICS_LOCK:
            if self.cur_round_id not in self.rounds:
                self.rounds[self.cur_round_id] = RoundAgg()
            self.rounds[self.cur_round_id].updated_at = _iso()
            return self.rounds[self.cur_round_id]

REG = Registry()

# ─────────────────────────────────────────────────────────────────────────────
# 퍼블릭 API (메인스레드 가벼움 보장)
# ─────────────────────────────────────────────────────────────────────────────
def init_metrics() -> None:
    """선제적으로 워커를 띄우고 싶을 때 호출(선택)."""
    _start_worker_once()

def set_round(round_id: Optional[str] = None):
    if not _enabled():
        return
    rid = (round_id or _iso()).strip()
    with _METRICS_LOCK:
        REG.cur_round_id = rid
        _ = REG.round()  # ensure created
    _emit({"ts": _now_ts(), "type": "set_round", "round": rid})

def get_round() -> str:
    return REG.cur_round_id

def set_topic_slug(slug: Optional[str]):
    if not _enabled():
        return
    s = (slug or "").strip() or None
    with _METRICS_LOCK:
        REG.topic_slug = s
    _emit({"ts": _now_ts(), "type": "set_topic", "topic_slug": s})

def get_topic_slug() -> Optional[str]:
    return REG.topic_slug

def record_query_issued():
    if not _enabled():
        return
    with _METRICS_LOCK:
        REG.round().queries_total += 1
    _emit({"ts": _now_ts(), "type": "query_issued", "round": get_round()})

def record_zero_result():
    if not _enabled():
        return
    with _METRICS_LOCK:
        REG.round().queries_zero_result += 1
    _emit({"ts": _now_ts(), "type": "zero_result", "round": get_round()})

def record_gatekeep(blocked_count: int, total_count: int):
    if not _enabled():
        return
    b = int(blocked_count); t = int(total_count)
    with _METRICS_LOCK:
        r = REG.round()
        r.gatekeep_blocked += b
        r.gatekeep_total += t
    _emit({"ts": _now_ts(), "type": "gatekeep", "blocked": b, "total": t, "round": get_round()})

def record_backend_latency(backend: str, latency_s: float):
    if not _enabled():
        return
    key = (backend or "unknown").strip().lower() or "unknown"
    lat = max(0.0, _as_float(latency_s, 0.0))
    with _METRICS_LOCK:
        r = REG.round()
        r.backend_lat_sum[key] = r.backend_lat_sum.get(key, 0.0) + lat
        r.backend_lat_cnt[key] = r.backend_lat_cnt.get(key, 0) + 1
    _emit({"ts": _now_ts(), "type": "backend_latency", "backend": key, "latency": lat, "round": get_round()})

def record_retrieval_source(web_cnt: int, local_cnt: int):
    if not _enabled():
        return
    w = int(web_cnt); l = int(local_cnt)
    with _METRICS_LOCK:
        r = REG.round()
        r.retrieved_web += w
        r.retrieved_local += l
    _emit({"ts": _now_ts(), "type": "retrieval", "web": w, "local": l, "round": get_round()})

def record_chunks(chars_sum: int, chunks_cnt: int):
    if not _enabled():
        return
    cs = int(chars_sum); cc = int(chunks_cnt)
    with _METRICS_LOCK:
        r = REG.round()
        r.chunks_chars_sum += cs
        r.chunks_cnt += cc
    _emit({"ts": _now_ts(), "type": "chunks", "chars_sum": cs, "cnt": cc, "round": get_round()})

def record_llm_call(
    *,
    provider: str = "",
    model: str = "",
    latency_s: float = 0.0,
    success: bool = True,
    error_class: str = "",
    section_title: str = "",
    retry_hint: str = "",
):
    """
    LLM 호출 1건 메트릭 기록(논블로킹). NDJSON 라인 1건을 emit.
    내부 retry_count는 langchain이 가려서 호출자가 알 수 없으므로 미수집.
    대신 latency가 평균 대비 비정상적으로 길면 retry_hint='slow'로 호출 측에서 표기.
    """
    if not _enabled():
        return
    _emit({
        "ts": _now_ts(),
        "type": "llm_call",
        "provider": (provider or "").strip().lower() or "unknown",
        "model": (model or "").strip() or "unknown",
        "latency": max(0.0, _as_float(latency_s, 0.0)),
        "success": bool(success),
        "error_class": (error_class or "").strip(),
        "section": (section_title or "").strip(),
        "retry_hint": (retry_hint or "").strip(),
        "round": get_round(),
        "topic_slug": REG.topic_slug,
    })

def event(kind: str, **payload):
    if not _enabled():
        return
    ev = {"ts": _now_ts(), "ts_iso": _iso(), "kind": kind, **payload}
    with _METRICS_LOCK:
        REG.events.append(ev)
        # 메모리 상한 유지(오래된 것부터 드롭) — 런타임 설정값 사용
        max_events = _get_events_max()
        if max_events > 0 and len(REG.events) > max_events:
            over = len(REG.events) - max_events
            if over > 0:
                del REG.events[0:over]
    _emit({"type": "event", **ev})

# ─────────────────────────────────────────────────────────────────────────────
# 요약/스냅샷/알림
# ─────────────────────────────────────────────────────────────────────────────
def summary() -> dict:
    """
    현재 라운드 요약 리턴.
    """
    if not _enabled():
        return {}
    with _METRICS_LOCK:
        rid = REG.cur_round_id
        r = REG.rounds.get(rid, RoundAgg())
        zero_rate = (r.queries_zero_result / r.queries_total) if r.queries_total else 0.0
        gate_rate = (r.gatekeep_blocked / r.gatekeep_total) if r.gatekeep_total else 0.0
        backend_avg = {
            k: (r.backend_lat_sum.get(k, 0.0) / r.backend_lat_cnt.get(k, 1))
            for k in set(list(r.backend_lat_sum.keys()) + list(r.backend_lat_cnt.keys()))
            if r.backend_lat_cnt.get(k, 0) > 0
        }
        chunk_avg = (r.chunks_chars_sum / r.chunks_cnt) if r.chunks_cnt else 0.0
        return {
            "round_id": rid,
            "topic_slug": REG.topic_slug,
            "started_at": r.started_at,
            "updated_at": r.updated_at,
            "queries_total": r.queries_total,
            "queries_zero_result": r.queries_zero_result,
            "zero_rate": zero_rate,
            "gatekeep_blocked": r.gatekeep_blocked,
            "gatekeep_total": r.gatekeep_total,
            "gatekeep_rate": gate_rate,
            "backend_avg": backend_avg,
            "retrieved_web": r.retrieved_web,
            "retrieved_local": r.retrieved_local,
            "chunks_chars_sum": r.chunks_chars_sum,
            "chunks_cnt": r.chunks_cnt,
            "chunk_avg_chars": chunk_avg,
        }

def _snapshot_payload() -> dict:
    with _METRICS_LOCK:
        return {
            "rounds": {k: vars(v) for k, v in REG.rounds.items()},
            "events": list(REG.events),
            "cur_round_id": REG.cur_round_id,
            "topic_slug": REG.topic_slug,
            "generated_at": _iso(),
        }

def _default_snapshot_path() -> tuple[str, str]:
    base_dir = _get_out_dir()
    os.makedirs(base_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(base_dir, f"metrics_{ts}.json")
    pattern = "metrics_*.json"
    return path, pattern

def _do_snapshot_file(path: Optional[str], rotate_keep: int = 0) -> None:
    if path is None:
        path, pattern = _default_snapshot_path()
        base_dir = os.path.dirname(path)
    else:
        base_dir = os.path.dirname(os.path.abspath(path))
        os.makedirs(base_dir, exist_ok=True)
        pattern = "*.json"
    data = _snapshot_payload()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if rotate_keep > 0:
            _rotate_keep(base_dir, pattern, rotate_keep)
    except Exception as e:
        try:
            logger.debug("[metrics.snapshot] write failed: %s", e)
        except Exception:
            pass

def snapshot(path: str | None = None, *, rotate_keep: int = 0):
    """
    메트릭 스냅샷을 저장. 워커 큐로 위임되어 메인 스레드가 블로킹되지 않음.
    """
    if not _enabled():
        return
    _emit({"__op__": "snapshot", "path": path, "rotate_keep": rotate_keep})

def check_thresholds_and_alert(logger_obj):
    """
    임계치 초과 시 logger.warning + 이벤트 기록.
    - ALERT_GATEKEEP_BLOCK_RATE (기본 0.5)
    - ALERT_TAVILY_AVG_LAT (기본 15.0)
    - ALERT_ZERO_RESULT_RATE (기본 0.2)
    """
    if not _enabled():
        return

    def _f(name: str, default: float) -> float:
        cv = getattr(CFG, name, None)
        if cv is not None:
            try:
                return float(cv)
            except Exception:
                pass
        try:
            return float(os.getenv(name, str(default)))
        except Exception:
            return default

    thr_block = _f("ALERT_GATEKEEP_BLOCK_RATE", 0.5)
    thr_tavily = _f("ALERT_TAVILY_AVG_LAT", 15.0)
    thr_zero   = _f("ALERT_ZERO_RESULT_RATE", 0.2)

    with _METRICS_LOCK:
        r = REG.round()
        block_rate = (r.gatekeep_blocked / r.gatekeep_total) if r.gatekeep_total else 0.0
        tv_sum = r.backend_lat_sum.get("tavily", 0.0)
        tv_cnt = r.backend_lat_cnt.get("tavily", 0)
        tv_avg = (tv_sum / tv_cnt) if tv_cnt else 0.0
        zero_rate = (r.queries_zero_result / r.queries_total) if r.queries_total else 0.0

    if block_rate > thr_block:
        msg = f"[ALERT] Gatekeep 차단률 높음: {block_rate*100:.1f}%"
        try: logger_obj.warning(msg)
        except Exception: pass
        event("alert", type="gatekeep", rate=block_rate)

    if tv_avg > thr_tavily:
        msg = f"[ALERT] Tavily 평균 응답시간 초과: {tv_avg:.2f}s"
        try: logger_obj.warning(msg)
        except Exception: pass
        event("alert", type="tavily_latency", avg=tv_avg)

    if zero_rate > thr_zero:
        msg = f"[ALERT] 결과 0건 쿼리 비율 높음: {zero_rate*100:.1f}%"
        try: logger_obj.warning(msg)
        except Exception: pass
        event("alert", type="zero_result", rate=zero_rate)

# ─────────────────────────────────────────────────────────────────────────────
# 유지보수/테스트 보조
# ─────────────────────────────────────────────────────────────────────────────
def reset() -> None:
    """레지스트리를 초기화(테스트/세션 전환용)."""
    with _METRICS_LOCK:
        REG.rounds.clear()
        REG.events.clear()
        REG.cur_round_id = "default"
        REG.topic_slug = None

    # 파일 핸들 초기화 (테스트/세션 리셋 시 안전)
    global _FH
    try:
        if _FH:
            _FH.flush()
            _FH.close()
    except Exception:
        pass
    _FH = None
