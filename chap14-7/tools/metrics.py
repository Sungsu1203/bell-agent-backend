# tools/metrics.py
from __future__ import annotations
import os, time, json, threading
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

_METRICS_LOCK = threading.Lock()

def _enabled() -> bool:
    return (os.getenv("METRICS_ENABLED", "1").lower() in ("1","true","yes","on"))

@dataclass
class RoundAgg:
    # a) 검색 성공/실패
    queries_total: int = 0
    queries_zero_result: int = 0
    # b) gatekeep 차단
    gatekeep_blocked: int = 0
    gatekeep_total: int = 0
    # c) 백엔드 응답시간
    backend_lat_sum: Dict[str, float] = field(default_factory=dict)     # {"tavily": 12.3, ...}
    backend_lat_cnt: Dict[str, int] = field(default_factory=dict)
    # d) 소스 비율(웹/로컬)
    retrieved_web: int = 0
    retrieved_local: int = 0
    # f) 인덱싱 청크 평균 길이
    chunks_chars_sum: int = 0
    chunks_cnt: int = 0

@dataclass
class Registry:
    rounds: Dict[str, RoundAgg] = field(default_factory=dict)  # key = round_id (예: "2025-10-24T15:18:43")
    events: List[dict] = field(default_factory=list)           # 원시 이벤트
    cur_round_id: str = "default"

    def round(self) -> RoundAgg:
        with _METRICS_LOCK:
            if self.cur_round_id not in self.rounds:
                self.rounds[self.cur_round_id] = RoundAgg()
            return self.rounds[self.cur_round_id]

REG = Registry()

def set_round(round_id: str):
    if not _enabled(): return
    with _METRICS_LOCK:
        REG.cur_round_id = round_id

def record_query_issued():
    if not _enabled(): return
    with _METRICS_LOCK:
        REG.round().queries_total += 1

def record_zero_result():
    if not _enabled(): return
    with _METRICS_LOCK:
        REG.round().queries_zero_result += 1

def record_gatekeep(blocked_count: int, total_count: int):
    if not _enabled(): return
    with _METRICS_LOCK:
        r = REG.round()
        r.gatekeep_blocked += blocked_count
        r.gatekeep_total += total_count

def record_backend_latency(backend: str, latency_s: float):
    if not _enabled(): return
    with _METRICS_LOCK:
        r = REG.round()
        r.backend_lat_sum[backend] = r.backend_lat_sum.get(backend, 0.0) + float(latency_s)
        r.backend_lat_cnt[backend] = r.backend_lat_cnt.get(backend, 0) + 1

def record_retrieval_source(web_cnt: int, local_cnt: int):
    if not _enabled(): return
    with _METRICS_LOCK:
        r = REG.round()
        r.retrieved_web += int(web_cnt)
        r.retrieved_local += int(local_cnt)

def record_chunks(chars_sum: int, chunks_cnt: int):
    if not _enabled(): return
    with _METRICS_LOCK:
        r = REG.round()
        r.chunks_chars_sum += int(chars_sum)
        r.chunks_cnt += int(chunks_cnt)

def event(kind: str, **payload):
    if not _enabled(): return
    with _METRICS_LOCK:
        REG.events.append({"ts": time.time(), "kind": kind, **payload})

def snapshot(path: str):
    if not _enabled(): return
    with _METRICS_LOCK:
        data = {"rounds": {k: vars(v) for k,v in REG.rounds.items()}, "events": REG.events}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── 알림 임계치 체크
def check_thresholds_and_alert(logger):
    if not _enabled(): return
    thr_block = float(os.getenv("ALERT_GATEKEEP_BLOCK_RATE", "0.5"))      # >50%
    thr_tavily = float(os.getenv("ALERT_TAVILY_AVG_LAT", "15"))           # >15s
    thr_zero   = float(os.getenv("ALERT_ZERO_RESULT_RATE", "0.2"))        # >20%
    with _METRICS_LOCK:
        r = REG.round()
        # 차단률
        block_rate = (r.gatekeep_blocked / r.gatekeep_total) if r.gatekeep_total else 0.0
        # Tavily 평균
        tv_sum = r.backend_lat_sum.get("tavily", 0.0)
        tv_cnt = r.backend_lat_cnt.get("tavily", 0)
        tv_avg = (tv_sum / tv_cnt) if tv_cnt else 0.0
        # 0건 비율
        zero_rate = (r.queries_zero_result / r.queries_total) if r.queries_total else 0.0

    if block_rate > thr_block:
        logger.warning("[ALERT] Gatekeep 차단률 높음: %.1f%%", block_rate*100)
        event("alert", type="gatekeep", rate=block_rate)
    if tv_avg > thr_tavily:
        logger.warning("[ALERT] Tavily 평균 응답시간 초과: %.2fs", tv_avg)
        event("alert", type="tavily_latency", avg=tv_avg)
    if zero_rate > thr_zero:
        logger.warning("[ALERT] 결과 0건 쿼리 비율 높음: %.1f%%", zero_rate*100)
        event("alert", type="zero_result", rate=zero_rate)
