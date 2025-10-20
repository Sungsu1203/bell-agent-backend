from __future__ import annotations

import os
# ── 환경 로드 ───────────────────────────────────────────────────────────────────
from dotenv import load_dotenv, find_dotenv

# .env 탐색을 CWD 기준으로 보장
dotenv_path = find_dotenv(filename=".env", usecwd=True)
load_dotenv(dotenv_path=dotenv_path, override=False)

# 💡 LOCAL_RAG_GLOBS 정규화: .env 값을 **존중**하되, 구분자(,|)만 통일
_lrg = (os.getenv("LOCAL_RAG_GLOBS") or "").strip()
if not _lrg:
    # .env에 값이 없으면만 기본값 설정 (PDF/TXT/PPTX/XLSX 재귀 검색)
    os.environ["LOCAL_RAG_GLOBS"] = "refs/*.pdf|refs/**/*.pdf|refs/*.txt|refs/**/*.pptx|refs/**/*.xlsx"
else:
    # 콤마로 들어온 패턴도 지원: ',' → '|' 변환하여 내부 처리 통일
    os.environ["LOCAL_RAG_GLOBS"] = _lrg.replace(",", "|")

# ── 표준 라이브러리 ────────────────────────────────────────────────────────────
import sys
import argparse
import logging
from logging import StreamHandler, Formatter
import json
from typing import Optional, TextIO, cast
from logging.handlers import RotatingFileHandler

# ── 프로젝트 의존 (DOC_MODE 대신 Config 임포트) ────────────────────────────────
from langchain_core.messages import SystemMessage, HumanMessage
from core.config import Config # 💡 Config 클래스 임포트
from core.paths import now_str as _now_str, current_path
from core.state_types import State
from core.state_io import save_state
from utils.sanitize import coerce_int
from report_builder import build_final_report


# ── 로깅 설정 ──────────────────────────────────────────────────────────────────
# NOTE: _int_env, _bool_env, _truthy 로직은 이제 Config 클래스 내부로 통합됨.
# 로깅 설정을 위한 최소한의 ENV 읽기 헬퍼 함수만 유지
def _bool_env(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")

def _truthy(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in ("1","true","yes","on")

def human_print(msg: str):
    """사람용 콘솔 출력(로거와 분리)."""
    # HUMAN_LOGS ENV 값은 Config에서 설정되지만, setup_logging 이전에 임시로 ENV에서 읽음
    if _truthy("HUMAN_LOGS"): 
        print(msg, flush=True)

def setup_logging(stream: Optional[TextIO] = None) -> None:
    """
    LOG_LEVEL, LOG_FILE 등 ENV 기반으로 로깅을 설정합니다.
    """
    root = logging.getLogger()

    # 기존 핸들러 제거 + close (중복 방지)
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    # 레벨 설정
    level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    root.setLevel(level)
    root.propagate = False 

    # 서드파티 노이즈 억제 (기존 로직 유지)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("absl").setLevel(logging.WARNING)
    logging.getLogger("grpc").setLevel(logging.WARNING)

    # 포맷 구성 (기존 로직 유지)
    use_json = _bool_env("LOG_JSON", False)
    fmt = os.getenv("LOG_FMT") or "[%(levelname)s] %(name)s: %(message)s"
    datefmt = os.getenv("LOG_DATEFMT") or "%Y-%m-%dT%H:%M:%S"

    if use_json:
        import json as _json
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
                return _json.dumps(obj, ensure_ascii=False)
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

    # HumanOnlyFilter (기존 로직 유지)
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

    show_human_only = _bool_env("HUMAN_LOGS", False)

    # 콘솔 핸들러 (기존 로직 유지)
    ch = logging.StreamHandler(stream or sys.stdout)
    ch.setLevel(level)
    if show_human_only:
        ch.addFilter(HumanOnlyFilter())
        ch.setFormatter(logging.Formatter("%(message)s"))
    else:
        ch.setFormatter(formatter)
    root.addHandler(ch)

    # 파일 핸들러 (기존 로직 유지)
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

# ── 초기 상태 (Config 객체를 받도록 수정) ───────────────────────────────────────
def initial_state(config: Config, user_task_content: str) -> State:
    """Config 객체와 사용자 입력을 기반으로 초기 상태를 생성합니다."""
    # config.doc_mode 사용
    default_outline = "outline_report.md" if config.doc_mode == "report" else "outline.md"
    base: State = {
        "messages": [
            SystemMessage(content=(
                f"너희 AI들은 사용자의 요구에 맞는 {('보고서' if config.doc_mode=='report' else '책')}을(를) 쓰는 작가팀이다. "
                f"사용자가 사용하는 언어로 대화하라. 현재시각은 {_now_str()}이다. "
                f"항상 한국어로 작성하라. 사용자에게서 한국어/영어가 섞여와도 산출물은 전부 한국어로 통일하라."
            )),
            # 첫 프라이밍 메시지를 여기서 추가 (Task를 주제로 고정)
            HumanMessage(content=f"주제는 '{config.task_description}'로 고정. 이 주제에 한정해 최신 자료로 RAG 업데이트.")
        ],
        "task_history": [],
        "references": {"queries": [], "docs": []},
        "agent_role": os.getenv("BLOCKAGI_AGENT_ROLE", "").strip().lower(),
        "iteration_count": config.iteration_count,
        "research_objectives": [],
        "research_round": 0,
        "research_loop_active": False,
        "findings_md": [],
        "llm_logs": [],
        "new_url_count": None,
        "topic_slug": config.topic_slug,
        "outline_fname": default_outline,
        "outline_shown": False,
        "facts_ctx": "",
        "research_plan": {"round": 0, "objective": "", "queries": [], "timestamp": _now_str()},
        "flags": {
            "topic_title": config.task_description, # Task를 title로 사용
            "pending_action": config.action_mode, # 첫 턴에 action을 수행하도록 플래그 기록
            "initial_agent": config.initial_agent_name, # 시작 에이전트 기록
        },
    }
    
    # Action Mode가 QA/Research Only/Write Only일 경우, Task를 첫 사용자 입력으로 추가하여 그래프를 트리거
    if config.action_mode in ("direct_qa", "research_only", "write_only"):
        base["messages"].append(HumanMessage(content=user_task_content))
    
    return base

# ── 사용자 입력 (기존 로직 유지) ────────────────────────────────────────────────
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

# ── 지연 로딩: 그래프 빌더 (Config 객체를 받도록 수정) ───────────────────────────
def _load_graph(config: Config):
    """Config 객체를 LangGraph 빌더에 전달할 수 있습니다."""
    from graph import build_graph
    return build_graph(config=config) # ← Config 객체를 전달하도록 변경

# ── 엔트리포인트 ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent RAG Writing System")
    
    # 💡 필수 CLI 인자 추가 (사용 간소화)
    parser.add_argument("-t", "--task", required=False, type=str, 
                        help="시스템에 전달할 초기 지시사항/QA 질문. Env: INITIAL_TASK")
    parser.add_argument("-m", "--mode", default="report", choices=["report", "book"], 
                        help="문서 모드: report (section) 또는 book (chapter). Env: DOC_MODE")
    parser.add_argument("-a", "--action", default="full_write", 
                        choices=["full_write", "research_only", "direct_qa", "write_only"],
                        help="실행할 액션: 전체 집필(기본), 연구만, QA 질의, 집필만. Env: INITIAL_ACTION")
    
    # 기존 인자들은 그대로 유지 (Config에 전달)
    parser.add_argument("--iteration_count", type=str, default=os.getenv("ITERATION_COUNT", "3"))
    parser.add_argument("--agent_role", type=str, default=os.getenv("BLOCKAGI_AGENT_ROLE", "").strip().lower())
    parser.add_argument("--recursion_limit", type=int, default=int(os.getenv("RECURSION_LIMIT", "200")))
    parser.add_argument("--topic-slug", type=str, default=os.getenv("TOPIC_SLUG") or "default")

    # 로깅/대시보드/에코/게이트키핑 인자들 유지
    parser.add_argument("--log-level", type=str, default=os.getenv("LOG_LEVEL", "INFO"))
    parser.add_argument("--log-file", type=str, default=os.getenv("LOG_FILE"))
    parser.add_argument("--log-json", action="store_true",
                         default=_bool_env("LOG_JSON", False))
    parser.add_argument("--log-topk", type=int, default=os.getenv("LOG_TOPK", 3), help="요약 로그에 표시할 상위 개수(기본 3)")
    parser.add_argument("--log-dashboard", action="store_true", default=_bool_env("LOG_DASHBOARD", True), help="supervisor 대시보드 출력 On/Off")
    parser.add_argument("--log-wrap", type=int, default=os.getenv("LOG_WRAP", 88), help="표시 텍스트 자르기 폭(기본 88)")
    parser.add_argument("--human-logs-verbose", action="store_true", help="HUMAN_LOGS=1일 때도 필터 해제하여 INFO+ 전부 출력")
    parser.add_argument("--human-logs", action="store_true", default=_bool_env("HUMAN_LOGS", False), help="JSON 로그와 별개로 사람이 보기 좋은 콘솔 로그만 필터링 출력")
    parser.add_argument("--echo-outline", action="store_true", help="아웃라인 생성/표시 시 콘솔로 본문 출력")
    parser.add_argument("--echo-sections", action="store_true", help="섹션 저장 시 콘솔로 본문 출력")
    parser.add_argument("--echo-report", action="store_true", help="최종 보고서 저장 시 콘솔로 본문 출력")

    # 게이트키핑 CLI 토글(+ 역토글)
    parser.add_argument("--gatekeep", action="store_true", dest="gatekeep")
    parser.add_argument("--no-gatekeep", action="store_false", dest="gatekeep")
    parser.set_defaults(gatekeep=None)

    # 허용 도메인 / 서브도메인 옵션
    parser.add_argument("--allow-domains", type=str, default=os.getenv("ALLOWED_DOMAINS", ""))
    parser.add_argument("--allow-subdomains", action="store_true", dest="allow_subdomains")
    parser.add_argument("--no-allow-subdomains", action="store_false", dest="allow_subdomains")
    parser.set_defaults(allow_subdomains=None)

    args = parser.parse_args()
    
    # ── 1. Config 객체 생성 (모든 설정의 통합) ──────────────────────────
    config = Config(**vars(args)) # CLI 인자를 Config에 전달하여 SSOT 생성

    # ── 2. 환경 반영 (로깅 및 외부 모듈 호환을 위한 최소한의 ENV만 설정) ─────────
    # Config 객체의 값을 ENV로 내보내기 (setup_logging 및 다른 모듈 호환용)
    os.environ["LOG_LEVEL"] = args.log_level.upper()
    os.environ["LOG_JSON"] = "1" if args.log_json else "0"
    if args.log_file: os.environ["LOG_FILE"] = args.log_file
    
    os.environ["TOPIC_SLUG"] = config.topic_slug
    os.environ["DOC_MODE"] = config.doc_mode
    os.environ["LOG_TOPK"] = str(config.log_topk)
    os.environ["LOG_DASHBOARD"] = "1" if config.log_dashboard else "0"
    os.environ["LOG_WRAP"] = str(config.log_wrap)
    os.environ["HUMAN_LOGS_VERBOSE"] = "1" if config.human_logs_verbose else "0"
    os.environ["HUMAN_LOGS"] = "1" if args.human_logs else "0"
    # Communicator 및 Writer 에코 옵션 ENV 반영
    os.environ["ECHO_OUTLINE"] = "1" if args.echo_outline else "0"
    os.environ["ECHO_SECTIONS"] = "1" if args.echo_sections else "0"
    os.environ["ECHO_REPORT"] = "1" if args.echo_report else "0"
    os.environ["COMMUNICATOR_ECHO"] = os.getenv("COMMUNICATOR_ECHO", "0") # Communicator 자체 에코는 0 유지
    
    # 게이트키핑 ENV도 Config 값으로 설정
    os.environ["GATE_KEEP_SOURCES"] = "1" if config.gate_keep_sources else "0"
    os.environ["ALLOWED_DOMAINS"] = config.allowed_domains
    os.environ["ALLOW_SUBDOMAINS"] = "1" if config.allow_subdomains else "0"
    
    # 기타 ENV (기존 로직 유지)
    os.environ["DASH_SIMPLE"] = os.getenv("DASH_SIMPLE", "1")
    os.environ["DASH_RATE_SEC"] = os.getenv("DASH_RATE_SEC", "8")
    
    # TOPIC_TITLE 설정 (topic-slug 기반)
    if not os.getenv("TOPIC_TITLE"):
        os.environ["TOPIC_TITLE"] = config.task_description.replace("-", " ")

    # ── 게이트키핑 캐시 리프레시 ────────────────────────────────
    try:
        from settings_gatekeep import refresh_gatekeep_cache, gatekeep_enabled, get_allowed_domains
        refresh_gatekeep_cache()
    except Exception as e:
        pass
    
    # ── 로깅은 딱 1회만 설정 ───────────────────────────────────────────────────
    setup_logging()

    logger.info("ARGS topic_slug=%r | ENV.TOPIC_TITLE=%r",
             args.topic_slug, os.getenv("TOPIC_TITLE"))

    # 게이트키핑 상태 로그
    try:
        from settings_gatekeep import gatekeep_enabled, get_allowed_domains
        if gatekeep_enabled():
            allow = ", ".join(sorted(get_allowed_domains())) or "(empty)"
            logger.info("[GATEKEEP] enabled; allowed=%s", allow)
        else:
            logger.info("[GATEKEEP] disabled")
    except Exception as e:
        logger.debug("Gatekeep status log skipped: %s", e)

    # ── 상태 초기화 (Config 객체를 전달) ──────────────────────────────────────
    state: State = initial_state(config=config, user_task_content=config.task_description)

    # ── 그래프 구성 (Config 객체를 전달) ──────────────────────────────────────
    try:
        graph = _load_graph(config=config)
    except Exception as e:
        logger.exception("build_graph failed: %s", e)
        raise

    logger.info("Application started (DOC_MODE=%s, iteration_count=%s, action_mode=%s)",
                config.doc_mode, config.iteration_count, config.action_mode)
    
    # 시작 배너
    human_print(f"┌─ Console: HUMAN_LOGS={os.getenv('HUMAN_LOGS','0')}, "
                f"VERBOSE={os.getenv('HUMAN_LOGS_VERBOSE','0')} | "
                f"LOG_TOPK={config.log_topk} LOG_WRAP={config.log_wrap} "
                f"LOG_DASHBOARD={config.log_dashboard}")

    try:
        while True:
            # 사용자 입력 읽기
            try:
                # full_write 모드가 아니더라도 첫 턴 이후에는 사용자 입력이 필요
                user_input = read_user_input()
                human_print(f"User  : {user_input}")
            except (EOFError, KeyboardInterrupt):
                logger.info("Interrupt received. Attempting to save final state...")
                try:
                    save_state(current_path, state)
                except Exception as se:
                    logger.exception("final save_state failed: %s", se)
                finally:
                    logger.info("Goodbye!")
                break

            # 빈 입력/도움말: 턴 스킵
            if not user_input.strip():
                logger.warning("빈 입력 수신. 도움말은 'help' 또는 '?'")
                continue

            # 종료 명령
            if user_input.lower() in ["exit", "quit", "q"]:
                logger.info("Exit command received. Saving state...")
                try:
                    save_state(current_path, state)
                except Exception as se:
                    logger.exception("final save_state failed: %s", se)
                finally:
                    logger.info("Goodbye!")
                break

            # 최종 보고서 빌드 트리거
            _u = user_input.strip().lower()
            if _u in ("build: report", "report build", "보고서 빌드", "최종 보고서 생성"):
                slug = str(state.get("topic_slug") or "default")
                # config.doc_mode 사용
                outline_fname = state.get("outline_fname") or ("outline_report.md" if config.doc_mode == "report" else "outline.md") 
                try:
                    out_path, missing = build_final_report(
                        topic_slug=slug,
                        outline_fname=outline_fname,
                        mode=config.doc_mode, # config.doc_mode 사용
                        root_dir=current_path
                    )
                    _flags = dict(state.get("flags") or {})
                    _flags["last_saved_report"] = out_path
                    state["flags"] = _flags
                    if missing:
                        logger.warning("Report built with missing sections: %s", ", ".join(missing))
                    print(f"\n[REPORT] 생성 완료 → {out_path}")
                    if missing:
                        print(f"[REPORT] 미수록 섹션({len(missing)}): " + ", ".join(missing))
                except Exception as e:
                    logger.exception("build_final_report failed: %s", e)
                    print(f"[REPORT][ERROR] {e}")
                continue

            # 메시지 추가
            state.setdefault("messages", []).append(HumanMessage(content=user_input))

            # 그래프 실행
            try:
                # config.recursion_limit 사용
                result = graph.invoke(state, config={"recursion_limit": config.recursion_limit})
            except Exception as e:
                logger.exception("graph.invoke failed: %s", e)
                raise

            if not isinstance(result, dict):
                logger.error("graph.invoke returned unexpected type: %s", type(result).__name__)
                raise TypeError(f"graph.invoke returned unexpected type: {type(result).__name__}")

            # 얕은 병합
            merged = dict(state)
            merged.update(result)
            state = merged # type: ignore

            # 마지막 AI 발화만 콘솔로 출력
            try:
                from langchain_core.messages import AIMessage
                msgs = list(state.get("messages", []))
                last_ai = next((m for m in reversed(msgs) if isinstance(m, AIMessage)), None)
                if last_ai and _truthy("HUMAN_LOGS", "0"):
                    print(str(getattr(last_ai, "content", "") or "").strip(), flush=True)
            except Exception:
                pass


            # 로깅 및 상태 저장
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

            # 상태 저장
            try:
                save_state(current_path, state)
            except Exception as e:
                logger.exception("save_state failed: %s", e)
    except Exception:
        # 최상위 안전망
        logger.exception("Fatal error in main loop")
        raise
