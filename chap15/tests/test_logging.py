# tests/test_logging.py
from __future__ import annotations
import io, json, logging, os, sys
import types
import importlib
import contextlib
import pytest

AGENT_LOGGERS = [
    "agent.supervisor",
    "agent.communicator",
    "agent.content_strategist",
    "agent.vector_search",
    "agent.web_search",
    "agent.chapter_writer",
    "agent.section_writer",
    "agent.research_planner",
    "agent.research_synthesizer",
]

def _reset_root_logger():
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    root.setLevel(logging.NOTSET)

def _import_setup_logging():
    """
    프로젝트의 app.py에 존재하는 setup_logging()을 불러옵니다.
    - 만약 import 경로가 다르면 여기만 수정하세요.
    """
    app = importlib.import_module("app")
    assert hasattr(app, "setup_logging"), "app.setup_logging()이 필요합니다."
    return app.setup_logging

@pytest.fixture(autouse=True)
def clean_logging_env(monkeypatch):
    # 각 테스트 시작 전 로거/환경변수 초기화
    _reset_root_logger()
    for k in ["LOG_JSON", "LOG_FILE", "LOG_LEVEL"]:
        monkeypatch.delenv(k, raising=False)
    yield
    _reset_root_logger()

def test_plain_text_single_line_no_duplicates(monkeypatch, capsys):
    """
    목표:
    - 중복 핸들러 없이 한 줄 단위로 기록되는지 검증
    방법:
    - setup_logging()으로 stdout 스트림 핸들러 구성
    - 여러 에이전트 로거에서 같은 메시지 키로 로그 발생
    - stdout 캡처 후 줄 수/중복/개행 여부 점검
    """
    setup_logging = _import_setup_logging()

    # JSON 끔, 파일 없음 → stdout으로만 출력되도록
    monkeypatch.setenv("LOG_JSON", "0")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_FILE", "")  # 파일 비활성

    # setup_logging이 스트림 지정 인자를 지원하면 사용, 아니면 기본 호출
    try:
        setup_logging(stream=sys.stdout)  # 선택적 인자
    except TypeError:
        setup_logging()

    # 로거 중복 핸들러가 없는지(루트 기준) 1개 스트림만 기대
    root = logging.getLogger()
    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    assert len(stream_handlers) == 1, f"중복 핸들러 감지: {stream_handlers}"

    # 동일 키로 에이전트들이 한 번씩 INFO 로그
    msg = "PING_SINGLE_LINE"
    for name in AGENT_LOGGERS:
        logging.getLogger(name).info("%s", msg)

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if "PING_SINGLE_LINE" in ln]

    # 각 에이전트별 한 줄씩 존재해야 함
    assert len(lines) == len(AGENT_LOGGERS), f"줄 수 불일치: {len(lines)} vs {len(AGENT_LOGGERS)}"
    # 각 줄 내부에 개행 문자가 있으면 안 됨
    for ln in lines:
        assert "\n" not in ln and "\r" not in ln, f"멀티라인 감지: {repr(ln)}"

def test_json_logging_structure(monkeypatch, capsys):
    """
    목표:
    - LOG_JSON=1일 때 출력이 유효한 JSON인지 확인
    - 각 레코드에 message/level/module(또는 name) 필드가 존재하는지 점검
    방법:
    - setup_logging()으로 stdout JSON 포맷 구성
    - 한 건 로그 발생 후 stdout을 JSON 파싱
    """
    setup_logging = _import_setup_logging()

    monkeypatch.setenv("LOG_JSON", "1")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_FILE", "")  # 파일 비활성

    try:
        setup_logging(stream=sys.stdout)  # 선택적 인자
    except TypeError:
        setup_logging()

    logger = logging.getLogger("agent.supervisor")
    logger.info("HELLO_JSON_TEST")

    out = capsys.readouterr().out.strip()
    # 복수 레코드일 수 있으니 줄 단위 파싱
    json_lines = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
            json_lines.append(obj)
        except json.JSONDecodeError:
            # JSON 포맷이 아니면 실패
            pytest.fail(f"JSON 파싱 실패: {ln}")

    assert len(json_lines) >= 1, "JSON 로그가 캡처되지 않았습니다."
    j = json_lines[-1]
    # 필수 키 점검 (프로젝트 포맷에 맞춰 최소 키만 확인)
    assert "message" in j, f"message 누락: {j}"
    # level 필드는 level 혹은 levelname 등 구현에 따라 다를 수 있어 유연하게 점검
    has_level = any(k in j for k in ("level", "levelname", "severity"))
    assert has_level, f"level 필드 누락: {j}"
    # module/name 중 하나는 반드시 있어야 추적 가능
    has_module = any(k in j for k in ("module", "name", "logger"))
    assert has_module, f"module/name 필드 누락: {j}"

def test_reinit_no_duplicate_handlers(monkeypatch, capsys):
    """
    목표:
    - setup_logging()을 여러 번 호출해도 중복 핸들러가 생기지 않는지 확인
    """
    setup_logging = _import_setup_logging()
    monkeypatch.setenv("LOG_JSON", "0")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_FILE", "")

    # 두 번 호출
    try:
        setup_logging(stream=sys.stdout)
        setup_logging(stream=sys.stdout)
    except TypeError:
        setup_logging()
        setup_logging()

    root = logging.getLogger()
    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    assert len(stream_handlers) == 1, f"재초기화 후 중복 핸들러: {stream_handlers}"

    logging.getLogger("agent.web_search").info("DUP_HANDLER_CHECK")
    out = capsys.readouterr().out
    assert out.count("DUP_HANDLER_CHECK") == 1, "중복 로그 출력 감지"
