from __future__ import annotations

# ── 환경 로드 ───────────────────────────────────────────────────────────────────
from dotenv import load_dotenv; load_dotenv()

# ── 표준 라이브러리 ────────────────────────────────────────────────────────────
import os
import sys
import argparse
import logging
from logging import StreamHandler, Formatter
import json

from typing import Optional, TextIO
from logging.handlers import RotatingFileHandler

# ── 프로젝트 의존 ───────────────────────────────────────────────────────────────
from langchain_core.messages import SystemMessage, HumanMessage
from core.config import DOC_MODE
from core.paths import now_str as _now_str, current_path
from core.state_types import State
from core.state_io import save_state
from utils.sanitize import coerce_int
from report_builder import build_final_report


# ── 로깅 설정 ──────────────────────────────────────────────────────────────────
def _bool_env(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")

def setup_logging(stream: Optional[TextIO] = None) -> None:
    """
    LOG_LEVEL, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT, LOG_JSON 등 환경변수로 제어.
    재호출 시 기존 핸들러를 모두 제거/close 하여 중복을 방지합니다.
    stream 인자가 주어지면 콘솔 핸들러는 해당 스트림을 사용합니다(주로 테스트용).
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

    # 포맷 구성
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

    # 콘솔 핸들러
    ch = logging.StreamHandler(stream or sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    root.addHandler(ch)


    # (NEW) JSON 로그 활성화 시 사람이 읽기 쉬운 로그를 병행 출력하고 싶다면
    #       --human-logs 또는 ENV HUMAN_LOGS=1 로 토글
    if use_json and _bool_env("HUMAN_LOGS", False):
        human = logging.StreamHandler(stream or sys.stdout)
        human.setLevel(level)
        human.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(human)

    # 파일 핸들러(선택)
    log_file = (os.getenv("LOG_FILE") or "").strip()
    if log_file:
        try:
            max_bytes = int(os.getenv("LOG_MAX_BYTES", "1048576"))  # 1MB
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

# ── 초기 상태 ──────────────────────────────────────────────────────────────────
def initial_state(iteration_count: int, agent_role: str | None = None) -> State:
    default_outline = "outline_report.md" if DOC_MODE == "report" else "outline.md"
    base: State = {
        "messages": [SystemMessage(content=(
            f"너희 AI들은 사용자의 요구에 맞는 {('보고서' if DOC_MODE=='report' else '책')}을(를) 쓰는 작가팀이다. "
            f"사용자가 사용하는 언어로 대화하라. 현재시각은 {_now_str()}이다."
        ))],
        "task_history": [],
        "references": {"queries": [], "docs": []},
        "agent_role": (agent_role or os.getenv("BLOCKAGI_AGENT_ROLE", "").strip().lower()),
        "iteration_count": int(iteration_count),
        "research_objectives": [],
        "research_round": 0,
        "research_loop_active": False,
        "findings_md": [],
        "llm_logs": [],
        "new_url_count": None,
        "topic_slug": os.getenv("TOPIC_SLUG") or "default",
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

    # 도움말
    if s.lower() in ("help", "?"):
        print_help()
        return ""

    # 여러 줄 펜스: ``` 또는 """ 시작
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

    # 줄바꿈 이어쓰기(\)
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
                        default=os.getenv("ITERATION_COUNT", os.getenv("BLOCKAGI_ITERATION_COUNT", "3")))
    parser.add_argument("--agent_role", type=str, default=os.getenv("BLOCKAGI_AGENT_ROLE", "").strip().lower())
    parser.add_argument("--recursion_limit", type=int, default=int(os.getenv("RECURSION_LIMIT", "200")))
    parser.add_argument("--log-level", type=str, default=os.getenv("LOG_LEVEL", "INFO"))
    parser.add_argument("--log-file", type=str, default=os.getenv("LOG_FILE"))
    parser.add_argument("--log-json", action="store_true",
                        default=_bool_env("LOG_JSON", False))
    parser.add_argument("--topic-slug", type=str, default=os.getenv("TOPIC_SLUG") or "default")

    # === NEW: human-friendly console & echo switches ===
    parser.add_argument("--human-logs", action="store_true",
                        help="JSON 로그와 별개로 사람이 보기 좋은 콘솔 로그를 함께 출력")
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

    # ── 인자 → 환경 반영(인자가 있으면 환경보다 우선) ─────────────────────────
    if args.log_level:
        os.environ["LOG_LEVEL"] = args.log_level.upper()
    if args.log_file:
        os.environ["LOG_FILE"] = args.log_file
    os.environ["LOG_JSON"] = "1" if args.log_json else "0"

    # (NEW) 사람이 보기 좋은 콘솔 및 본문 에코 옵션을 ENV로 전달
    #       (모듈 곳곳에서 os.getenv로 읽어 쓸 수 있게 통일)
    os.environ["HUMAN_LOGS"]    = "1" if args.human_logs     else "0"
    os.environ["ECHO_OUTLINE"]  = "1" if args.echo_outline   else "0"
    os.environ["ECHO_SECTIONS"] = "1" if args.echo_sections  else "0"
    os.environ["ECHO_REPORT"]   = "1" if args.echo_report    else "0"
    # (참고) 여기서 ENV를 설정해두면 communicator/section_writer/report_assembler 등
    #        모듈에서 os.getenv("ECHO_*") 로 바로 분기 가능

    # 게이트키핑 ENV 반영
    if args.gatekeep is not None:
        os.environ["GATE_KEEP_SOURCES"] = "1" if args.gatekeep else "0"
    else:
        os.environ["GATE_KEEP_SOURCES"] = os.getenv("GATE_KEEP_SOURCES", "0")

    if args.allow_domains is not None:
        os.environ["ALLOWED_DOMAINS"] = args.allow_domains

    if args.allow_subdomains is not None:
        os.environ["ALLOW_SUBDOMAINS"] = "1" if args.allow_subdomains else "0"

    # ── 게이트키핑 캐시 리프레시 (ENV 반영 직후) ────────────────────────────────
    try:
        from settings_gatekeep import refresh_gatekeep_cache, gatekeep_enabled, get_allowed_domains
        refresh_gatekeep_cache()
    except Exception as e:
        # 로깅 설정 전이므로 print 사용 자제 → 조용히 넘김
        pass

    # ── 로깅은 딱 1회만 설정 ───────────────────────────────────────────────────
    setup_logging()

    # 게이트키핑 상태 로그 (로깅 설정 이후)
    try:
        from settings_gatekeep import gatekeep_enabled, get_allowed_domains
        if gatekeep_enabled():
            allow = ", ".join(sorted(get_allowed_domains())) or "(empty)"
            logger.info("[GATEKEEP] enabled; allowed=%s", allow)
        else:
            logger.info("[GATEKEEP] disabled")
    except Exception as e:
        logger.debug("Gatekeep status log skipped: %s", e)

    iter_count = coerce_int(args.iteration_count, default=3)
    effective_role = (args.agent_role or os.getenv("BLOCKAGI_AGENT_ROLE", "")).strip().lower() or None

    # topic-slug 주입
    os.environ["TOPIC_SLUG"] = args.topic_slug

    state: State = initial_state(iteration_count=iter_count, agent_role=effective_role)

    # 그래프 구성
    try:
        graph = _load_graph()
    except Exception as e:
        logger.exception("build_graph failed: %s", e)
        raise

    logger.info("Application started (DOC_MODE=%s, iteration_count=%s, agent_role=%s)",
                DOC_MODE, state.get("iteration_count"), state.get("agent_role"))

    try:
        while True:
            try:
                user_input = read_user_input()
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

            # (NEW) 최종 보고서 빌드 트리거
            _u = user_input.strip().lower()
            if _u in ("build: report", "report build", "보고서 빌드", "최종 보고서 생성"):
                slug = str(state.get("topic_slug") or "default")
                outline_fname = state.get("outline_fname") or ("outline_report.md" if DOC_MODE == "report" else "outline.md")
                try:
                    out_path, missing = build_final_report(
                        topic_slug=slug,
                        outline_fname=outline_fname,
                        mode=DOC_MODE,
                        root_dir=current_path
                    )
                    # TypedDict(State)에는 임의 키를 직접 넣을 수 없으니 flags 컨테이너를 사용
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
                # 메시지/그래프 실행 없이 다음 입력 대기
                continue

            # 메시지 추가
            state.setdefault("messages", []).append(HumanMessage(content=user_input))

            # 그래프 실행
            try:
                result = graph.invoke(state, config={"recursion_limit": args.recursion_limit})
            except Exception as e:
                logger.exception("graph.invoke failed: %s", e)
                raise

            if not isinstance(result, dict):
                logger.error("graph.invoke returned unexpected type: %s", type(result).__name__)
                raise TypeError(f"graph.invoke returned unexpected type: {type(result).__name__}")

            # 얕은 병합(shallow merge): 바뀐 키만 덮어쓰기
            merged = dict(state)
            merged.update(result)
            state = merged  # type: ignore

            # 로깅(레벨 구분)
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
