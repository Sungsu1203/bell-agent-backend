# app.py (final)

from __future__ import annotations

# ── Fault handler (deadlock/멈춤 추적) ──────────────────────────────────────────
import faulthandler, sys, time
faulthandler.enable()  # 항상 가능한 초반에 활성화
# 콘솔(stderr)로 90초 타임아웃 스택 덤프 예약
faulthandler.dump_traceback_later(90, file=sys.stderr)

_trace_fh = None  # 파일 트레이스 핸들(로깅 설정 후 열어 예약)

def _cancel_fault_timers_and_close() -> None:
    """예약된 스택 덤프 타이머를 취소하고 파일 핸들을 정리합니다."""
    try:
        faulthandler.cancel_dump_traceback_later()
    except Exception:
        pass
    try:
        global _trace_fh
        if _trace_fh and not _trace_fh.closed:
            _trace_fh.close()
            _trace_fh = None
    except Exception:
        pass

# ── 환경 로드 ───────────────────────────────────────────────────────────────────
import os
from dotenv import load_dotenv, find_dotenv

dotenv_path = find_dotenv(filename=".env", usecwd=True)
load_dotenv(dotenv_path=dotenv_path, override=False)

# .env 오염 방지: 특정 키 강제 주입(옵션)
try:
    from dotenv import get_key
    local_rag_globs_from_env = get_key(dotenv_path, "LOCAL_RAG_GLOBS")
    if local_rag_globs_from_env and os.getenv("LOCAL_RAG_GLOBS") != local_rag_globs_from_env:
        os.environ["LOCAL_RAG_GLOBS"] = local_rag_globs_from_env
        print(f"[CRITICAL DEBUG] LOCAL_RAG_GLOBS FORCED: {os.environ['LOCAL_RAG_GLOBS']}", flush=True)
except Exception as e:
    print(f"[CRITICAL DEBUG] Failed to force override: {e}", flush=True)

print(f"[CRITICAL DEBUG] LOCAL_RAG_GLOBS RAW: {os.getenv('LOCAL_RAG_GLOBS')}", flush=True)

# ── 표준 라이브러리 ────────────────────────────────────────────────────────────
import sys
import argparse
from logging import StreamHandler, Formatter
import logging
from typing import Optional, TextIO, Any, Dict, cast
from logging.handlers import RotatingFileHandler
import json

# ── 프로젝트 의존 ───────────────────────────────────────────────────────────────
from langchain_core.messages import SystemMessage, HumanMessage
import core.config as config
from core.paths import now_str as _now_str, current_path
from core.state_types import State
try:
    from core.state_types import Flags  # 프로젝트에 존재하면 사용
except Exception:
    from typing import Dict as Flags  # 폴백: Dict[str, Any]로 간주
from core.state_io import save_state
from utils.sanitize import coerce_int
from report_builder import build_final_report

_ALLOWED_FLAG_KEYS = {
    "pending_write_title","requested_write_title","suppress_vector_qa",
    "sections_done","sections_total","sections_seen",
    "chapters_done","chapters_total","chapters_seen",
    "dash_last_ts","dash_count","skip_web_search","debug",
    "topic_title","iteration_count",
}

def update_flags(state: State, **updates: Any) -> None:
    """Flags에 허용된 키만 반영하고, 나머지는 state 루트에 기록."""
    f: Dict[str, Any] = dict(state.get("flags") or {})
    for k, v in updates.items():
        if k in _ALLOWED_FLAG_KEYS:
            f[k] = v
        else:
            state[k] = v
    state["flags"] = cast(Flags, f)

if bool(getattr(config.CFG, "HUMAN_LOGS_VERBOSE", False)):
    print(config.CFG)

# ── 로깅 설정 ──────────────────────────────────────────────────────────────────
def _int_env(name: str, default: int) -> int:
    try:
        v = (os.getenv(name) or "").strip()
        return int(v) if v != "" else default
    except Exception:
        return default

def _bool_env(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")

def _truthy_cfg(name: str, fallback_env: str | None = None, default: bool = False) -> bool:
    if hasattr(config.CFG, name):
        return bool(getattr(config.CFG, name))
    return (os.getenv(fallback_env or name, "1" if default else "0").strip().lower() in ("1","true","yes","on"))

def human_print(msg: str):
    if bool(getattr(config.CFG, "HUMAN_LOGS", False)):
        print(msg, flush=True)

def setup_logging(stream: Optional[TextIO] = None) -> None:
    root = logging.getLogger()

    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)
    root.propagate = False

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("unstructured").setLevel(logging.WARNING)
    logging.getLogger("absl").setLevel(logging.WARNING)
    logging.getLogger("grpc").setLevel(logging.WARNING)

    use_json = _bool_env("LOG_JSON", False)
    fmt = os.getenv("LOG_FMT") or "[%(levelname)s] %(name)s: %(message)s"
    datefmt = os.getenv("LOG_DATEFMT") or "%Y-%m-%dT%H:%M:%S"

    if use_json:
        class _JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                obj = {
                    "time": self.formatTime(record, datefmt),
                    "level": getattr(record, "levelname", ""),
                    "name": record.name,
                    "module": record.module,
                    "lineno": record.lineno,
                    "message": record.getMessage(),
                }
                if record.exc_info:
                    obj["exc_info"] = self.formatException(record.exc_info)
                return json.dumps(obj, ensure_ascii=False)
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

    import re as _re
    class HumanOnlyFilter(logging.Filter):
        _pat_basic = _re.compile(
            r'^\s*User\s*:'
            r'|^\s*\[REPORT\]'
            r'|^\s*Application started'
            r'|^\s*Goodbye!'
            r'|^\s*MESSAGE COUNT'
        , _re.I)

        def filter(self, record: logging.LogRecord) -> bool:
            msg = str(record.getMessage() or "")
            if (os.getenv("HUMAN_LOGS_STRICT","0").lower() in ("1","true","yes","on")):
                return bool(self._pat_basic.search(msg))
            if record.name.startswith(("agent.", "tools.", "utils.")):
                return False
            if self._pat_basic.search(msg):
                return True
            if record.levelno >= logging.INFO and record.name in {"__main__", "report_builder"}:
                return True
            return False

    show_human_only = bool(getattr(config.CFG, "HUMAN_LOGS", False))

    ch = logging.StreamHandler(stream or sys.stdout)
    ch.setLevel(level)
    if show_human_only:
        ch.addFilter(HumanOnlyFilter())
        ch.setFormatter(logging.Formatter("%(message)s"))
    else:
        ch.setFormatter(formatter)
    root.addHandler(ch)

    log_file = (os.getenv("LOG_FILE") or "").strip()
    if not log_file:
        log_file = os.path.join(".", "logs", "run_full.log")
    try:
        max_bytes = int(os.getenv("LOG_MAX_BYTES", "1048576"))
    except Exception:
        max_bytes = 1048576
    try:
        backups = int(os.getenv("LOG_BACKUP_COUNT", "3"))
    except Exception:
        backups = 3

    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    fh = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # ▼ faulthandler: 파일로도 90초 덤프 예약(로깅 경로 확정 후)
    global _trace_fh
    try:
        _trace_fh = open(log_file, "a", encoding="utf-8", buffering=1)
        faulthandler.dump_traceback_later(90, file=_trace_fh)  # stderr 예약은 유지, 파일로 재예약(마지막 예약이 유효)
    except Exception:
        _trace_fh = None
    # ▲

logger = logging.getLogger(__name__)

# ── 도움말 ──────────────────────────────────────────────────────────────────────
def print_help():
    logger.info(
        "\n[도움말]\n"
        "- 일반 입력: 에이전트에게 지시/질문을 보냅니다.\n"
        "- 여러 줄 입력: 첫 줄에 ``` 또는 \"\"\" 를 입력해 시작/종료합니다.\n"
        "- 줄바꿈 이어쓰기: 줄 끝에 \\ 입력\n"
        "- 종료: exit | quit | q\n"
        "- 예시: '목차 생성', '최신 자료로 RAG 업데이트', 'write: 서론'\n"
    )

# ── 초기 상태 ──────────────────────────────────────────────────────────────────
def initial_state(iteration_count: int, agent_role: str | None = None) -> State:
    default_outline = "outline_report.md" if config.DOC_MODE == "report" else "outline.md"
    base: State = {
        "messages": [SystemMessage(content=(
            f"너희 AI들은 사용자의 요구에 맞는 {('보고서' if config.DOC_MODE=='report' else '책')}을(를) 쓰는 작가팀이다. "
            f"사용자가 사용하는 언어로 대화하라. 현재시각은 {_now_str()}이다. "
            f"항상 한국어로 작성하라. 사용자에게서 한국어/영어가 섞여와도 산출물은 전부 한국어로 통일하라."
        ))],
        "task_history": [],
        "references": {"queries": [], "docs": []},
        # 일부 라우터/도구는 경량 미러 키 'refs'도 참조하므로 초깃값에서 함께 준비
        "refs": {"queries": [], "docs": []},
        "agent_role": (agent_role or getattr(config.CFG, "BLOCKAGI_AGENT_ROLE", "")).strip().lower(),
        "iteration_count": int(iteration_count),
        "research_objectives": [],
        "research_round": 0,
        "research_loop_active": False,
        "findings_md": [],
        "llm_logs": [],
        "new_url_count": None,
        "topic_slug": getattr(config.CFG, "TOPIC_SLUG", "") or "default",
        "outline_fname": default_outline,
        "outline_shown": False,
        "facts_ctx": "",
        "research_plan": {"round": 0, "objective": "", "queries": [], "timestamp": _now_str()},
        "flags": {},
    }
    return base

# ── 사용자 입력 ────────────────────────────────────────────────────────────────
def read_user_input() -> str:
    try:
        first = input("\nUser\t: ")
    except (EOFError, KeyboardInterrupt):
        raise
    s = first.strip()

    if s.lower() in ("help", "?"):
        print_help()
        return ""

    if s.startswith('```') or s == '"""':
        fence = '```' if s.startswith('```') else '"""'
        lines = []
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                return "\n".join(lines).strip()
            if line.strip() == fence:
                break
            lines.append(line)
        return "\n".join(lines).strip()

    buf = first
    while buf.endswith("\\"):
        try:
            buf = buf[:-1] + "\n" + input()
        except (EOFError, KeyboardInterrupt):
            break
    return buf.strip()

# ── 지연 로딩: 그래프 빌더 ─────────────────────────────────────────────────────
def _load_graph():
    from graph import build_graph
    return build_graph()

# ── 엔트리포인트 ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration_count", type=str,
                        default=str(getattr(config.CFG, "ITERATION_COUNT", 3)))
    parser.add_argument("--agent_role", type=str,
                        default=(getattr(config.CFG, "BLOCKAGI_AGENT_ROLE", "") or "").strip().lower())
    parser.add_argument("--recursion_limit", type=int, default=int(os.getenv("RECURSION_LIMIT", "200")))
    parser.add_argument("--log-level", type=str, default=getattr(config.CFG, "LOG_LEVEL", "INFO"))
    parser.add_argument("--log-file", type=str, default=os.getenv("LOG_FILE"))
    parser.add_argument("--log-json", action="store_true", default=_bool_env("LOG_JSON", False))
    parser.add_argument("--topic-slug", type=str, default=getattr(config.CFG, "TOPIC_SLUG", "") or "default")

    parser.add_argument("--log-topk", type=int, default=_int_env("LOG_TOPK", 3))
    parser.add_argument("--log-dashboard", action="store_true",
                        default=_bool_env("LOG_DASHBOARD", True))
    parser.add_argument("--log-wrap", type=int, default=_int_env("LOG_WRAP", 88))
    parser.add_argument("--human-logs-verbose", action="store_true")
    parser.add_argument("--human-logs", action="store_true")
    parser.add_argument("--echo-outline", action="store_true")
    parser.add_argument("--echo-sections", action="store_true")
    parser.add_argument("--echo-report", action="store_true")

    parser.add_argument("--gatekeep", action="store_true", dest="gatekeep")
    parser.add_argument("--no-gatekeep", action="store_false", dest="gatekeep")
    parser.set_defaults(gatekeep=None)

    parser.add_argument("--allow-domains", type=str, default=os.getenv("ALLOWED_DOMAINS", ""))
    parser.add_argument("--allow-subdomains", action="store_true", dest="allow_subdomains")
    parser.add_argument("--no-allow-subdomains", action="store_false", dest="allow_subdomains")
    parser.set_defaults(allow_subdomains=None)

    args = parser.parse_args()

    logger.info("ARGS topic_slug=%r | ENV.TOPIC_TITLE=%r",
                args.topic_slug, os.getenv("TOPIC_TITLE"))

    # 인자 → ENV 반영
    if args.log_level:
        os.environ["LOG_LEVEL"] = args.log_level.upper()
    if args.log_file:
        os.environ["LOG_FILE"] = args.log_file
    os.environ["LOG_JSON"] = "1" if args.log_json else "0"

    os.environ["LOG_TOPK"] = str(args.log_topk)
    os.environ["LOG_DASHBOARD"] = "1" if args.log_dashboard else "0"
    os.environ["LOG_WRAP"] = str(args.log_wrap)
    os.environ["DASH_SIMPLE"]   = os.getenv("DASH_SIMPLE", "1")
    os.environ["DASH_RATE_SEC"] = os.getenv("DASH_RATE_SEC", str(getattr(config.CFG, "DASH_RATE_SEC", 6)))
    os.environ["COMMUNICATOR_ECHO"] = os.getenv("COMMUNICATOR_ECHO", "0")
    os.environ["HUMAN_LOGS_VERBOSE"] = "1" if args.human_logs_verbose else ("1" if getattr(config.CFG, "HUMAN_LOGS_VERBOSE", False) else "0")
    os.environ["HUMAN_LOGS"]    = "1" if args.human_logs     else ("1" if getattr(config.CFG, "HUMAN_LOGS", False) else "0")
    os.environ["ECHO_OUTLINE"]  = "1" if args.echo_outline   else ("1" if getattr(config.CFG, "ECHO_OUTLINE", False) else "0")
    os.environ["ECHO_SECTIONS"] = "1" if args.echo_sections  else ("1" if getattr(config.CFG, "ECHO_SECTIONS", False) else "0")
    os.environ["ECHO_REPORT"]   = "1" if args.echo_report    else os.getenv("ECHO_REPORT", "0")

    if args.gatekeep is not None:
        os.environ["GATE_KEEP_SOURCES"] = "1" if args.gatekeep else "0"
    else:
        os.environ["GATE_KEEP_SOURCES"] = os.getenv("GATE_KEEP_SOURCES", "0")

    if args.allow_domains is not None:
        os.environ["ALLOWED_DOMAINS"] = args.allow_domains

    if args.allow_subdomains is not None:
        os.environ["ALLOW_SUBDOMAINS"] = "1" if args.allow_subdomains else "0"

    # CFG 재로딩
    try:
        config.CFG = config.reload_config()
    except Exception:
        pass

    # 게이트키핑 캐시 리프레시
    try:
        from settings_gatekeep import refresh_gatekeep_cache
        refresh_gatekeep_cache()
    except Exception:
        pass

    # 로깅 설정 (여기서 로그 파일 경로 확정 → faulthandler 파일 예약도 여기서)
    try:
        setup_logging()
    except Exception as e:
        # 로깅 설정 실패해도 덤프 타이머는 정리
        _cancel_fault_timers_and_close()
        raise

    logger.info(
        "ENV TOPIC_TITLE=%r | TOPIC_SLUG=%r | dotenv_path=%s",
        os.getenv("TOPIC_TITLE"),
        os.getenv("TOPIC_SLUG"),
        dotenv_path
    )

    try:
        from settings_gatekeep import gatekeep_enabled, get_allowed_domains
        if gatekeep_enabled():
            allow = ", ".join(sorted(get_allowed_domains())) or "(empty)"
            logger.info("[GATEKEEP] enabled; allowed=%s", allow)
        else:
            logger.info("[GATEKEEP] disabled")
    except Exception:
        pass

    iter_count = coerce_int(args.iteration_count, default=3)
    effective_role = (args.agent_role or os.getenv("BLOCKAGI_AGENT_ROLE", "")).strip().lower() or None

    os.environ["TOPIC_SLUG"] = args.topic_slug
    if not os.getenv("TOPIC_TITLE"):
        os.environ["TOPIC_TITLE"] = args.topic_slug.replace("-", " ")

    state: State = initial_state(iteration_count=iter_count, agent_role=effective_role)

    state["topic_slug"] = args.topic_slug
    update_flags(state, topic_title=os.environ.get("TOPIC_TITLE", ""))
    state["topic_title"] = os.environ["TOPIC_TITLE"]

    _topic_title = (state.get("flags") or {}).get("topic_title") or args.topic_slug.replace("-", " ")
    state.setdefault("messages", []).append(
        HumanMessage(content=f"주제는 '{_topic_title}'로 고정. 다른 산업으로 확장하지 말고 이 주제에 한정해 최신 자료로 RAG 업데이트.")
    )

    # 그래프 구성
    try:
        graph = _load_graph()
    except Exception as e:
        logger.exception("build_graph failed: %s", e)
        _cancel_fault_timers_and_close()   # ← 예약 취소 + 파일 핸들 정리
        raise

    logger.info("Application started (config.DOC_MODE=%s, iteration_count=%s, agent_role=%s)",
                config.DOC_MODE, state.get("iteration_count"), state.get("agent_role"))

    human_print(
        "┌─ Console: "
        f"HUMAN_LOGS={int(bool(getattr(config.CFG,'HUMAN_LOGS',False)))}, "
        f"VERBOSE={int(bool(getattr(config.CFG,'HUMAN_LOGS_VERBOSE',False))) } | "
        f"LOG_TOPK={getattr(config.CFG,'LOG_TOPK',3)} LOG_WRAP={getattr(config.CFG,'LOG_WRAP',88)} "
        f"LOG_DASHBOARD={int(bool(getattr(config.CFG,'LOG_DASHBOARD',True)))}"
    )

    try:
        while True:
            try:
                user_input = read_user_input()
                human_print(f"User    : {user_input}")
            except (EOFError, KeyboardInterrupt):
                logger.info("Interrupt received. Attempting to save final state...")
                try:
                    save_state(current_path, state)
                except Exception as se:
                    logger.exception("final save_state failed: %s", se)
                finally:
                    _cancel_fault_timers_and_close()  # ← 종료 전 정리
                    logger.info("Goodbye!")
                break

            if not user_input.strip():
                logger.warning("빈 입력 수신. 도움말은 'help' 또는 '?'")
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                logger.info("Exit command received. Saving state...")
                try:
                    save_state(current_path, state)
                except Exception as se:
                    logger.exception("final save_state failed: %s", se)
                finally:
                    _cancel_fault_timers_and_close()  # ← 종료 전 정리
                    logger.info("Goodbye!")
                break

            _u = user_input.strip().lower()
            if _u in ("build: report", "report build", "보고서 빌드", "최종 보고서 생성"):
                slug = str(state.get("topic_slug") or "default")
                outline_fname = state.get("outline_fname") or ("outline_report.md" if config.DOC_MODE == "report" else "outline.md")
                try:
                    out_path, missing = build_final_report(
                        topic_slug=slug,
                        outline_fname=outline_fname,
                        mode=config.DOC_MODE,
                        root_dir=str(current_path)
                    )
                    update_flags(state)
                    state["last_saved_path"] = out_path
                    if missing:
                        logger.warning("Report built with missing sections: %s", ", ".join(missing))
                    print(f"\n[REPORT] 생성 완료 → {out_path}")
                    if missing:
                        print(f"[REPORT] 미수록 섹션({len(missing)}): " + ", ".join(missing))
                except Exception as e:
                    logger.exception("build_final_report failed: %s", e)
                    print(f"[REPORT][ERROR] {e}")
                continue

            state.setdefault("messages", []).append(HumanMessage(content=user_input))

            try:
                result = graph.invoke(state, config={"recursion_limit": args.recursion_limit})
            except Exception as e:
                logger.exception("graph.invoke failed: %s", e)
                _cancel_fault_timers_and_close()  # ← 예외 시에도 정리
                raise

            if not isinstance(result, dict):
                logger.error("graph.invoke returned unexpected type: %s", type(result).__name__)
                _cancel_fault_timers_and_close()
                raise TypeError(f"graph.invoke returned unexpected type: {type(result).__name__}")

            merged = dict(state)
            merged.update(result)
            state = merged  # type: ignore

            try:
                from langchain_core.messages import AIMessage
                msgs = list(state.get("messages", []))
                last_ai = next((m for m in reversed(msgs) if isinstance(m, AIMessage)), None)
                if last_ai and bool(getattr(config.CFG, "HUMAN_LOGS", False)):
                    print(str(getattr(last_ai, "content", "") or "").strip(), flush=True)
            except Exception:
                pass

            logger.info("MESSAGE COUNT = %s", len(state.get("messages", [])))

            tail = [(getattr(t, "agent", None), getattr(t, "done", None), getattr(t, "description", None))
                    for t in state.get("task_history", [])][-3:]
            logger.debug("TASKS tail = %s", tail)

            try:
                flags = {
                    "agent_role": state.get("agent_role"),
                    "iteration_count": state.get("iteration_count"),
                    "research_round": state.get("research_round"),
                    "research_loop_active": state.get("research_loop_active"),
                    "has_plan": bool((state.get("research_plan") or {}).get("objective")),
                }
                logger.debug("RESEARCH flags = %s", flags)
            except Exception as e:
                logger.exception("Failed to log research flags: %s", e)

            logger.debug("last_saved_path before save: %s", state.get("last_saved_path"))

            try:
                save_state(current_path, state)
            except Exception as e:
                logger.exception("save_state failed: %s", e)

    except Exception:
        # 최상위 안전망
        logger.exception("Fatal error in main loop")
        _cancel_fault_timers_and_close()  # ← 비정상 종료 시에도 정리
        raise
    finally:
        # 정상 종료 루트에서도 타이머/파일 정리 보장
        _cancel_fault_timers_and_close()
