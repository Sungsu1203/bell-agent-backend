# core/config.py
from __future__ import annotations
from dataclasses import dataclass, fields
from typing import Literal, Optional, Set, Final, List
import os
from pathlib import Path
import json, re

import threading

# ── dotenv (선택적) ───────────────────────────────────────────
try:
    from dotenv import load_dotenv, find_dotenv
    _DOTENV_READY = True
except Exception:  # pragma: no cover
    _DOTENV_READY = False

# 기존 코드 호환: AgentName 타입 유지
from core.models import AgentName

# ── 타입 ───────────────────────────────────────────────────────
DocMode = Literal["report", "book"]

# ── 내부 helpers ───────────────────────────────────────────────
def _env_str(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v.strip() if v is not None else default

def _env_flag(name: str, default: bool = False) -> bool:
    """
    불리언 ENV 파서(엄격)
    True  : {"1","true","yes","on"}
    False : {"0","false","no","off",""}  ※ 빈 문자열 포함
    Other : default
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off", ""}:
        return False
    return default

def _env_int(
    name: str, default: int = 0, *, min_: Optional[int] = None, max_: Optional[int] = None
) -> int:
    v = _env_str(name)
    if not v:
        return default
    try:
        x = int(v)
    except Exception:
        return default
    if min_ is not None and x < min_:
        x = min_
    if max_ is not None and x > max_:
        x = max_
    return x

def _env_float(
    name: str, default: float = 0.0, *, min_: Optional[float] = None, max_: Optional[float] = None
) -> float:
    v = _env_str(name)
    if not v:
        return default
    try:
        x = float(v)
    except Exception:
        return default
    if min_ is not None and x < min_:
        x = min_
    if max_ is not None and x > max_:
        x = max_
    return x

def _coerce_doc_mode(v: str | None, fallback: DocMode = "report") -> DocMode:
    vv = (v or "").strip().lower()
    if vv in ("report", "book"):
        # mypy 리터럴 타입 만족
        return ("report" if vv == "report" else "book")
    return fallback

def _split_csv_set(v: str) -> Set[str]:
    return {x.strip().lower() for x in v.split(",") if x.strip()}

def _split_loose(s: str) -> list[str]:
    # 콤마/세미콜론/파이프/개행/과다 공백 구분자 처리
    #   - 문자클래스 내부의 '?', '|' 오작동 방지
    pat = r"[,\|;]|\r?\n|\s{2,}"
    return [p.strip() for p in re.split(pat, s) if p and p.strip()]

def _parse_hints(raw: str) -> List[str]:
    # GOOGLEISH_HINTS = "site:| OR | AND |(|)"
    return [t for t in (raw.split("|") if isinstance(raw, str) else []) if t]

# ── 기본 PROJECT_ROOT 추론 ────────────────────────────────────
_HERE = Path(__file__).resolve()
_DEFAULT_PROJECT_ROOT = _HERE.parents[1]  # .../chap14_8

# ── dotenv 1회 로드 ───────────────────────────────────────────
_cfg_lock = threading.RLock()
_dotenv_loaded = False

def _load_dotenv_once() -> None:
    global _dotenv_loaded
    with _cfg_lock:
        if _dotenv_loaded:
            return
        _dotenv_loaded = True
    if not _DOTENV_READY:
        return
    # 1) 기본 .env 로드
    try:
        load_dotenv(find_dotenv(usecwd=True), override=False)
    except Exception:
        pass
    # 2) TOPIC_SLUG에 맞는 토픽 프리셋 파일 추가 로드
    try:
        slug = os.getenv("TOPIC_SLUG", "").strip()
        if slug:
            root = Path(os.getenv("PROJECT_ROOT", str(_DEFAULT_PROJECT_ROOT))).resolve()
            preset_path = root / "topics" / f"{slug}.env"
            if preset_path.exists():
                load_dotenv(preset_path, override=True)
                print(f"[Config] 토픽 프리셋 로드: {preset_path}")
            else:
                print(f"[Config] 토픽 프리셋 없음 (기본 .env 사용): {preset_path}")
    except Exception as e:
        print(f"[Config] 토픽 프리셋 로드 실패 (무시): {e}")

# ── 연구 목적 ENV 로더(호환 유지 + 확장) ───────────────────────
def load_research_objectives_from_env(
    prefix: str = "BLOCKAGI_OBJECTIVE_",
    max_n: int = 10,
    *,
    batch_key: str = "BLOCKAGI_OBJECTIVES",
    allow_batch: bool = True,
) -> List[str]:
    """
    BLOCKAGI_OBJECTIVE_1..N 과 BLOCKAGI_OBJECTIVES(배열/구분자 문자열)를 통합 로드.
    - 공백 제거, 순서 보존 중복 제거
    - batch_key가 JSON 배열이면 그대로 사용, 아니면 느슨한 구분자로 분리
    """
    items: list[str] = []

    # 1) 번호붙은 키
    for i in range(1, max_n + 1):
        v = os.getenv(f"{prefix}{i}")
        if isinstance(v, str) and v.strip():
            items.append(v.strip())

    # 2) 집합형 키(선택)
    if allow_batch:
        raw = os.getenv(batch_key, "")
        if isinstance(raw, str) and raw.strip():
            added = False
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    for x in parsed:
                        if isinstance(x, str) and x.strip():
                            items.append(x.strip())
                            added = True
            except Exception:
                pass
            if not added:  # JSON 아니면 느슨한 분리
                items.extend(_split_loose(raw))

    # 3) 순서 보존 중복 제거
    seen, out = set(), []
    for s in items:
        if s not in seen:
            seen.add(s); out.append(s)
    return out

# ── 구성 데이터클래스 ─────────────────────────────────────────
# in-place 갱신을 위해 frozen=False
@dataclass(frozen=False)
class Config:
    # ── 운영 경로 ──────────────────────────────────────────────
    PROJECT_ROOT: Path  # ← 추가: 프로젝트 루트(환경변수 PROJECT_ROOT로 오버라이드 가능)

    # 문서/작동 모드
    DOC_MODE: DocMode
    # 새 필드: AGENT_ROLE(우선 사용)
    AGENT_ROLE: str
    # 하위호환/원문 보존: BLOCKAGI_AGENT_ROLE
    BLOCKAGI_AGENT_ROLE: str
    ITERATION_COUNT: int

    # RAG/검색 (네임스페이스/머지/탑K 등)
    SEARCH_POLICY: str
    SEARCH_MIN_OK: int
    SEARCH_TOPN: int
    SKIP_WEB_SEARCH: bool
    SKIP_VERTEX_SEARCH: bool
    LOCAL_RAG_GLOBS: str
    CHROMA_NAMESPACE: str
    CHROMA_NAMESPACE_WEB: str
    SKIP_VERTEX_SEARCH: bool
    CHROMA_NAMESPACE_LOCAL: str
    CLEAR_CHROMA_ON_START: bool
    CHROMA_INCLUDE_BASE: bool
    MERGE_RETRIEVE_MODE: str
    RETRIEVE_WEB_RATIO: float
    # refs 병합 상한(0=무제한)
    MERGE_REFS_MAX_QUERIES: int
    MERGE_REFS_MAX_DOCS: int
    RAG_TOP_K: int
    ALLOW_LOCAL_SUMMARY: bool

    # Writer
    WRITER_AGENT: AgentName
    AUTO_WRITE_AFTER_RAG: bool
    AUTO_WRITE_DURING_RESEARCH: bool
    DIRECT_QA: bool
    REQUIRE_EXPLICIT_WRITE_TITLE: bool
    AUTO_FOOTNOTE: bool
    ECHO_SECTIONS: bool
    ECHO_CHAPTERS: bool
    CHAPTERS_TOTAL_DEFAULT: int
    SECTIONS_TOTAL_DEFAULT: int

    # 게이트키핑/도메인
    GATE_KEEP_SOURCES: bool
    ALLOWED_DOMAINS: Set[str]

    # 로깅/대시보드
    LOG_LEVEL: str
    LOG_LEVEL_CONSOLE: str
    LOG_LEVEL_FILE: str
    LOG_TOPK: int
    LOG_WRAP: int
    SHOW_DASHBOARD: bool
    DASH_WRAP: int
    ECHO_OUTLINE: bool
    ECHO_QA: bool
    COMMUNICATOR_ECHO: bool
    HUMAN_LOGS: bool
    HUMAN_LOGS_VERBOSE: bool
    COMM_LOG_QA_BODY: bool
    COMM_LOG_QA_MAXLEN: int
    LOG_DASHBOARD: bool
    DASH_RATE_SEC: float

    # 기타
    TOPIC_SLUG: str
    REPORT_OUT_DIR: str
    RESEARCH_OUT_DIR: str
    TOPIC_TITLE: str
    PLANNER_FORCE_KR: bool
    RESEARCH_PLANNER_MAX_Q: int
    RESEARCH_PLANNER_ANNOUNCE: bool

    # 연구 목표(ENV 통합)
    RESEARCH_OBJECTIVES: List[str]

    # 합성 루프/중단 파라미터
    RESEARCH_HALT_THRESHOLD: int
    RESEARCH_MIN_ROUNDS: int
    RESEARCH_MAX_NO_NEW_ROUNDS: int

    # RAG/검색 백엔드 & 한도 (web_search.py 하위호환용)
    SEARCH_BACKENDS: str
    HAS_GOOGLE_KEYS: bool
    HAS_SERPAPI: bool
    HAS_TAVILY: bool
    MAX_INDEXED_PER_ROUND: int
    MAX_SEARCH_QUERIES_PER_ROUND: int
    LOCAL_RAG_ALLOW: str

    # (추가) 운영 편의 필드
    GOOGLEISH_HINTS: List[str]
    # supervisor 등에서 getattr(CFG, "BLOCKAGI_OBJECTIVES") 접근을 위해 원문도 노출
    BLOCKAGI_OBJECTIVES: str

    # ── Forced Queries (강제 검색 쿼리)
    ALLOW_FORCED_QUERIES: bool
    FORCED_QUERY_LOOKBACK: int
    FORCED_QUERY_MAX_PER_RUN: int
    FORCED_QUERY_MIN_LEN: int
    FORCED_QUERY_EXPAND_YEAR_RANGES: bool
    FORCED_QUERY_YEAR_SPAN_LIMIT: int
    FORCED_QUERY_ENABLE_SITE_SPLIT: bool
    FORCED_QUERY_ENFORCE_GATEKEEP: bool

    # ── LLM 공통/공급자 설정 ───────────────────────────────────
    LLM_PROVIDER: str                         # "openai" | "gemini" | "vertexai"
    RAG_EMBEDDING_MODEL: str                  # 임베딩 모델 강제 오버라이드(있으면 우선)
    BLOCKAGI_TEST_FAKE_LLM: bool

    # OpenAI
    OPENAI_MODEL: str
    OPENAI_EMBEDDING_MODEL: str
    OPENAI_BASE_URL: str
    OPENAI_API_BASE: str
    OPENAI_ORG_ID: str
    OPENAI_ORGANIZATION: str
    OPENAI_REQUEST_TIMEOUT: float
    OPENAI_MAX_RETRIES: int
    OPENAI_API_KEY: str                       # 선택(가독/정적타입 목적)

    # Gemini
    GEMINI_MODEL: str
    GEMINI_EMBEDDING_MODEL: str
    GEMINI_API_KEY: str                       # 선택

    # Vertex AI
    LLM_MODEL: str                            # Vertex chat 모델명
    GCP_PROJECT_ID: str
    GCP_REGION: str

    DEBUG_ROUTER_KEYS: bool

    MIRROR_STATE_TO_ENV: bool
    RESET_OBJECTIVES_ON_NEW_TOPIC: bool

    LOG_JSON: bool
    LOG_FILE: str
    LOG_MAX_BYTES: int
    LOG_BACKUP_COUNT: int
    LOG_FMT: str
    LOG_DATEFMT: str

    ALLOW_SUBDOMAINS: bool

    REPORT_SOURCES: str

    # ── post init: 경로/파생값 정규화 ─────────────────────────
    def __post_init__(self) -> None:
        # PROJECT_ROOT: 환경변수로 오버라이드 허용
        env_root = _env_str("PROJECT_ROOT", "")
        if env_root:
            try:
                self.PROJECT_ROOT = Path(env_root).resolve()
            except Exception:
                self.PROJECT_ROOT = _DEFAULT_PROJECT_ROOT

        # REPORT_OUT_DIR / RESEARCH_OUT_DIR 기본값(비어있으면 프로젝트 루트 기준)
        if not (self.REPORT_OUT_DIR or "").strip():
            self.REPORT_OUT_DIR = str(self.PROJECT_ROOT / "reports")
        if not (self.RESEARCH_OUT_DIR or "").strip():
            self.RESEARCH_OUT_DIR = str(self.PROJECT_ROOT / "research")

        # ── AGENT_ROLE ↔ BLOCKAGI_AGENT_ROLE 상호 폴백 ─────────
        try:
            ar = (self.AGENT_ROLE or "").strip()
            br = (self.BLOCKAGI_AGENT_ROLE or "").strip()
            if not ar and br:
                self.AGENT_ROLE = br
            elif ar and not br:
                self.BLOCKAGI_AGENT_ROLE = ar
        except Exception:
            # 안전 폴백: 둘 다 비면 기본값
            if not (getattr(self, "AGENT_ROLE", "") or "").strip():
                self.AGENT_ROLE = "research analyst"
            if not (getattr(self, "BLOCKAGI_AGENT_ROLE", "") or "").strip():
                self.BLOCKAGI_AGENT_ROLE = self.AGENT_ROLE
            # ── CHROMA_NAMESPACE 자동 파생 ──────────────────────────
            # TOPIC_SLUG 기반으로 비어있는 NS를 자동 생성
            def _ns(s: str) -> str:
                s = (s or "").strip().lower()
                s = re.sub(r"[^a-z0-9\-]+", "-", s)
                s = re.sub(r"-{2,}", "-", s).strip("-")
                return s or "default"

        slug = _ns(self.TOPIC_SLUG or "default")
        if not (self.CHROMA_NAMESPACE or "").strip():
            self.CHROMA_NAMESPACE = f"{slug}-default"
        if not (self.CHROMA_NAMESPACE_WEB or "").strip():
            self.CHROMA_NAMESPACE_WEB = f"{slug}-default-web"
        if not (self.CHROMA_NAMESPACE_LOCAL or "").strip():
            self.CHROMA_NAMESPACE_LOCAL = f"{slug}-default-local"

# ── 구성 빌더 ────────────────────────────────────────────────
def _build_config() -> Config:
    # .env → os.environ 주입 (최초 1회)
    _load_dotenv_once()
    doc_mode = _coerce_doc_mode(_env_str("DOC_MODE", "report"))
    writer_agent: AgentName = ("section_writer" if doc_mode == "report" else "chapter_writer")
    return Config(
        # 운영 경로
        PROJECT_ROOT=_DEFAULT_PROJECT_ROOT,

        # 모드/역할
        DOC_MODE=doc_mode,
        # 우선순위: AGENT_ROLE → BLOCKAGI_AGENT_ROLE → 기본
        AGENT_ROLE=_env_str("AGENT_ROLE") or _env_str("BLOCKAGI_AGENT_ROLE", "research analyst"),
        BLOCKAGI_AGENT_ROLE=_env_str("BLOCKAGI_AGENT_ROLE", "research analyst"),
        ITERATION_COUNT=_env_int("ITERATION_COUNT", 1, min_=1, max_=50),

        # RAG/검색
        SEARCH_POLICY=_env_str("SEARCH_POLICY", "best_of_chain"),
        SEARCH_MIN_OK=_env_int("SEARCH_MIN_OK", 1, min_=1, max_=5),
        SEARCH_TOPN=_env_int("SEARCH_TOPN", 10, min_=1, max_=50),
        SKIP_WEB_SEARCH=_env_flag("SKIP_WEB_SEARCH", False),
        SKIP_VERTEX_SEARCH=_env_flag("SKIP_VERTEX_SEARCH", False),
        LOCAL_RAG_GLOBS=_env_str("LOCAL_RAG_GLOBS", ""),
        CHROMA_NAMESPACE=_env_str("CHROMA_NAMESPACE", ""),
        CHROMA_NAMESPACE_WEB=_env_str("CHROMA_NAMESPACE_WEB", ""),
        CHROMA_NAMESPACE_LOCAL=_env_str("CHROMA_NAMESPACE_LOCAL", ""),
        CLEAR_CHROMA_ON_START=_env_flag("CLEAR_CHROMA_ON_START", False),
        CHROMA_INCLUDE_BASE=_env_flag("CHROMA_INCLUDE_BASE", False),
        MERGE_RETRIEVE_MODE=_env_str("MERGE_RETRIEVE_MODE", "web_first"),
        RETRIEVE_WEB_RATIO=_env_float("RETRIEVE_WEB_RATIO", 0.67, min_=0.0, max_=1.0),
        # refs 병합 상한(0=무제한)
        MERGE_REFS_MAX_QUERIES=_env_int("MERGE_REFS_MAX_QUERIES", 0, min_=0),
        MERGE_REFS_MAX_DOCS=_env_int("MERGE_REFS_MAX_DOCS", 0, min_=0),
        RAG_TOP_K=_env_int("RAG_TOP_K", 6, min_=1, max_=50),
        ALLOW_LOCAL_SUMMARY=_env_flag("ALLOW_LOCAL_SUMMARY", _env_flag("ALLOW_SUMMARY", False)),

        # Writer
        WRITER_AGENT=writer_agent,
        AUTO_WRITE_AFTER_RAG=_env_flag("AUTO_WRITE_AFTER_RAG", True),
        AUTO_WRITE_DURING_RESEARCH=_env_flag("AUTO_WRITE_DURING_RESEARCH", False),
        DIRECT_QA=_env_flag("DIRECT_QA", False),
        REQUIRE_EXPLICIT_WRITE_TITLE=_env_flag("REQUIRE_EXPLICIT_WRITE_TITLE", True),
        AUTO_FOOTNOTE=_env_flag("AUTO_FOOTNOTE", True),         # 기본 켜짐(과거 호환)
        ECHO_SECTIONS=_env_flag("ECHO_SECTIONS", False),
        ECHO_CHAPTERS=_env_flag("ECHO_CHAPTERS", False),
        CHAPTERS_TOTAL_DEFAULT=_env_int("CHAPTERS_TOTAL_DEFAULT", 12, min_=1),
        SECTIONS_TOTAL_DEFAULT=_env_int("SECTIONS_TOTAL_DEFAULT", 8, min_=1),

        # 게이트키핑/도메인
        GATE_KEEP_SOURCES=_env_flag("GATE_KEEP_SOURCES", False),
        ALLOWED_DOMAINS=_split_csv_set(_env_str("ALLOWED_DOMAINS", "")),

        # 로깅/대시보드
        LOG_LEVEL=_env_str("LOG_LEVEL", "INFO"),
        # 콘솔/파일 레벨은 없으면 LOG_LEVEL로 폴백
        LOG_LEVEL_CONSOLE=_env_str(
            "LOG_LEVEL_CONSOLE",
            _env_str("LOG_LEVEL", "INFO"),
        ),
        LOG_LEVEL_FILE=_env_str(
            "LOG_LEVEL_FILE",
            _env_str("LOG_LEVEL", "INFO"),
        ),
        LOG_TOPK=_env_int("LOG_TOPK", 3, min_=1, max_=50),
        LOG_WRAP=_env_int("LOG_WRAP", 88, min_=40, max_=200),
        SHOW_DASHBOARD=_env_flag("SHOW_DASHBOARD", False),
        DASH_WRAP=_env_int("DASH_WRAP", 88, min_=40, max_=200),
        ECHO_OUTLINE=_env_flag("ECHO_OUTLINE", False),
        ECHO_QA=_env_flag("ECHO_QA", False),
        COMMUNICATOR_ECHO=_env_flag("COMMUNICATOR_ECHO", False),
        HUMAN_LOGS=_env_flag("HUMAN_LOGS", False),
        HUMAN_LOGS_VERBOSE=_env_flag("HUMAN_LOGS_VERBOSE", False),
        COMM_LOG_QA_BODY=_env_flag("COMM_LOG_QA_BODY", False),
        COMM_LOG_QA_MAXLEN=_env_int("COMM_LOG_QA_MAXLEN", 0, min_=0, max_=1_000_000),
        LOG_DASHBOARD=_env_flag("LOG_DASHBOARD", True),
        DASH_RATE_SEC=float(_env_str("DASH_RATE_SEC", "6")),

        # 기타
        TOPIC_SLUG=_env_str("TOPIC_SLUG", ""),
        REPORT_OUT_DIR=_env_str("REPORT_OUT_DIR", ""),
        RESEARCH_OUT_DIR=_env_str("RESEARCH_OUT_DIR", ""),
        TOPIC_TITLE=_env_str("TOPIC_TITLE", ""),
        PLANNER_FORCE_KR=_env_flag("PLANNER_FORCE_KR", True),
        RESEARCH_PLANNER_MAX_Q=_env_int("RESEARCH_PLANNER_MAX_Q", 7, min_=0, max_=50),
        RESEARCH_PLANNER_ANNOUNCE=_env_flag("RESEARCH_PLANNER_ANNOUNCE", False),

        # 연구 목표
        RESEARCH_OBJECTIVES=load_research_objectives_from_env(),

        # 합성 루프/중단
        RESEARCH_HALT_THRESHOLD=_env_int("RESEARCH_HALT_THRESHOLD", 0, min_=0),
        RESEARCH_MIN_ROUNDS=_env_int("RESEARCH_MIN_ROUNDS", 1, min_=1),
        RESEARCH_MAX_NO_NEW_ROUNDS=_env_int("RESEARCH_MAX_NO_NEW_ROUNDS", 1, min_=1),

        # RAG/검색 백엔드 & 한도 (web_search.py 하위호환용)
        SEARCH_BACKENDS=_env_str("SEARCH_BACKENDS", ""),              # 예: "google,serpapi,tavily"
        HAS_GOOGLE_KEYS=bool((_env_str("GOOGLE_API_KEY") or _env_str("GOOGLE_CSE_API_KEY")) and (_env_str("GOOGLE_CSE_ID") or _env_str("GOOGLE_CSE_CX"))),
        HAS_SERPAPI=bool(_env_str("SERPAPI_API_KEY")),
        HAS_TAVILY=bool(_env_str("TAVILY_API_KEY")),
        MAX_INDEXED_PER_ROUND=_env_int("MAX_INDEXED_PER_ROUND", 0, min_=0),
        MAX_SEARCH_QUERIES_PER_ROUND=_env_int("MAX_SEARCH_QUERIES_PER_ROUND", 6, min_=0, max_=50),
        LOCAL_RAG_ALLOW=_env_str("LOCAL_RAG_ALLOW", ""),

        # 운영 편의
        GOOGLEISH_HINTS=_parse_hints(_env_str("GOOGLEISH_HINTS", "")) or ["site:", " OR ", " AND ", "(", ")"],
        # 참고: RESEARCH_OBJECTIVES는 파싱 결과, 아래 원문은 레거시 접근 호환용
        BLOCKAGI_OBJECTIVES=_env_str("BLOCKAGI_OBJECTIVES", ""),

        # ── Forced Queries (강제 검색 쿼리)
        ALLOW_FORCED_QUERIES=_env_flag("ALLOW_FORCED_QUERIES", True),
        FORCED_QUERY_LOOKBACK=_env_int("FORCED_QUERY_LOOKBACK", 15, min_=1, max_=200),
        FORCED_QUERY_MAX_PER_RUN=_env_int("FORCED_QUERY_MAX_PER_RUN", 20, min_=1, max_=200),
        FORCED_QUERY_MIN_LEN=_env_int("FORCED_QUERY_MIN_LEN", 3, min_=1, max_=20),
        FORCED_QUERY_EXPAND_YEAR_RANGES=_env_flag("FORCED_QUERY_EXPAND_YEAR_RANGES", True),
        FORCED_QUERY_YEAR_SPAN_LIMIT=_env_int("FORCED_QUERY_YEAR_SPAN_LIMIT", 6, min_=2, max_=50),
        FORCED_QUERY_ENABLE_SITE_SPLIT=_env_flag("FORCED_QUERY_ENABLE_SITE_SPLIT", True),
        FORCED_QUERY_ENFORCE_GATEKEEP=_env_flag("FORCED_QUERY_ENFORCE_GATEKEEP", True),

        # ── LLM 공통/공급자 설정 ────────────────────────────────
        LLM_PROVIDER=_env_str("LLM_PROVIDER", "openai").lower(),
        RAG_EMBEDDING_MODEL=_env_str("RAG_EMBEDDING_MODEL", ""),
        BLOCKAGI_TEST_FAKE_LLM=_env_flag("BLOCKAGI_TEST_FAKE_LLM", False),

        # OpenAI
        OPENAI_MODEL=_env_str("OPENAI_MODEL", "gpt-4o"),
        OPENAI_EMBEDDING_MODEL=_env_str("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002"),
        OPENAI_BASE_URL=_env_str("OPENAI_BASE_URL", ""),
        OPENAI_API_BASE=_env_str("OPENAI_API_BASE", ""),
        OPENAI_ORG_ID=_env_str("OPENAI_ORG_ID", ""),
        OPENAI_ORGANIZATION=_env_str("OPENAI_ORGANIZATION", ""),
        OPENAI_REQUEST_TIMEOUT=_env_float("OPENAI_REQUEST_TIMEOUT", 0.0, min_=0.0, max_=3600.0),
        OPENAI_MAX_RETRIES=_env_int("OPENAI_MAX_RETRIES", 0, min_=0, max_=10),
        OPENAI_API_KEY=_env_str("OPENAI_API_KEY", ""),

        # Gemini
        GEMINI_MODEL=_env_str("GEMINI_MODEL", "gemini-2.5-pro"),
        GEMINI_EMBEDDING_MODEL=_env_str("GEMINI_EMBEDDING_MODEL", "text-embedding-004"),
        GEMINI_API_KEY=_env_str("GEMINI_API_KEY", ""),

        # Vertex AI
        LLM_MODEL=_env_str("LLM_MODEL", "gemini-2.5-flash"),
        GCP_PROJECT_ID=_env_str("GCP_PROJECT_ID", "your-gcp-project-id"),
        GCP_REGION=_env_str("GCP_REGION", "asia-northeast3"),

        DEBUG_ROUTER_KEYS=_env_flag("DEBUG_ROUTER_KEYS", False),

        MIRROR_STATE_TO_ENV=_env_flag("MIRROR_STATE_TO_ENV", True),
        RESET_OBJECTIVES_ON_NEW_TOPIC=_env_flag("RESET_OBJECTIVES_ON_NEW_TOPIC", True),

        LOG_JSON=_env_flag("LOG_JSON", False),
        LOG_FILE=_env_str("LOG_FILE", ""),
        LOG_MAX_BYTES=_env_int("LOG_MAX_BYTES", 1048576, min_=1024, max_=1_000_000_000),
        LOG_BACKUP_COUNT=_env_int("LOG_BACKUP_COUNT", 3, min_=0, max_=100),
        LOG_FMT=_env_str("LOG_FMT", "[%(levelname)s] %(name)s: %(message)s"),
        LOG_DATEFMT=_env_str("LOG_DATEFMT", "%Y-%m-%dT%H:%M:%S"),

        ALLOW_SUBDOMAINS=_env_flag("ALLOW_SUBDOMAINS", False),

        REPORT_SOURCES=_env_str("REPORT_SOURCES", ""),
    )

# ── 싱글턴 구성 객체 ─────────────────────────────────────────
CFG: Config = _build_config()

def reload_config_inplace() -> Config:
    """
    ENV 변경을 반영하되, CFG 객체를 재바인딩하지 않고
    '같은 객체'의 필드만 갱신(in-place)합니다.
    """
    global CFG
    with _cfg_lock:
        # .env 재적용(override=True) → os.environ 갱신
        if _DOTENV_READY:
            try:
                load_dotenv(find_dotenv(usecwd=True), override=True)
            except Exception:
                pass
        new_cfg = _build_config()
        for f in fields(CFG):
            setattr(CFG, f.name, getattr(new_cfg, f.name))
        return CFG

def reload_config() -> Config:
    """호환용 엔트리포인트: in-place 갱신을 수행."""
    return reload_config_inplace()

# ── 동적 접근 헬퍼(개별 모듈 편의) ───────────────────────────
from typing import Any, Callable

def get(name: str, default: Any = None, coerce: Callable[[Any], Any] | None = None) -> Any:
    """CFG → ENV → default 순서로 읽되, 필요 시 coerce 적용"""
    val = getattr(CFG, name, os.getenv(name, default))
    return coerce(val) if (coerce and val is not None) else (val if val is not None else default)

def truthy(name: str, default: bool = False) -> bool:
    """불리언 해석(엄격: 1/true/yes/on) — CFG → ENV → default"""
    if hasattr(CFG, name):
        v = getattr(CFG, name)
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v != 0
        if isinstance(v, str):
            s = v.strip().lower()
            if s in {"1", "true", "yes", "on"}:
                return True
            if s in {"0", "false", "no", "off", ""}:
                return False
            return default
    envv = os.getenv(name)
    if envv is None:
        return default
    s = envv.strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off", ""}:
        return False
    return default

# ── 하위호환: 모듈 속성처럼 접근 허용(점진 제거 권장) ────────
def __getattr__(name: str):
    if hasattr(CFG, name):
        return getattr(CFG, name)
    raise AttributeError(name)

# ── 프로젝트 루트(하위호환 상수; CFG 우선) ───────────────────
PROJECT_ROOT: Final[str] = str(getattr(CFG, "PROJECT_ROOT", _DEFAULT_PROJECT_ROOT))

# ── Writer 기본 선택(기존 시그니처 유지) ─────────────────────
def preferred_writer_agent() -> AgentName:
    return "section_writer" if CFG.DOC_MODE == "report" else "chapter_writer"

# 기존 상수는 유지하되, 내부 값은 CFG를 참조(하위호환)
WRITER_AGENT: Final[AgentName] = CFG.WRITER_AGENT

# ── 하위 호환 상수(점진적 교체용; 이후 정리 가능) ───────────
DOC_MODE: Final[DocMode] = CFG.DOC_MODE
AGENT_ROLE: Final[str] = CFG.AGENT_ROLE
AUTO_WRITE_AFTER_RAG: Final[bool] = CFG.AUTO_WRITE_AFTER_RAG
AUTO_WRITE_DURING_RESEARCH: Final[bool] = CFG.AUTO_WRITE_DURING_RESEARCH
RESEARCH_OUT_DIR: Final[str] = CFG.RESEARCH_OUT_DIR
SEARCH_POLICY: Final[str] = CFG.SEARCH_POLICY
SEARCH_MIN_OK: Final[int] = CFG.SEARCH_MIN_OK
SEARCH_TOPN: Final[int] = CFG.SEARCH_TOPN
CHROMA_NAMESPACE_WEB: Final[str] = CFG.CHROMA_NAMESPACE_WEB
CHROMA_NAMESPACE_LOCAL: Final[str] = CFG.CHROMA_NAMESPACE_LOCAL
MERGE_REFS_MAX_QUERIES: Final[int] = CFG.MERGE_REFS_MAX_QUERIES
MERGE_REFS_MAX_DOCS: Final[int] = CFG.MERGE_REFS_MAX_DOCS
GATE_KEEP_SOURCES: Final[bool] = CFG.GATE_KEEP_SOURCES
ALLOWED_DOMAINS: Final[Set[str]] = CFG.ALLOWED_DOMAINS
SEARCH_BACKENDS: Final[str] = CFG.SEARCH_BACKENDS
HAS_GOOGLE_KEYS: Final[bool] = CFG.HAS_GOOGLE_KEYS
HAS_SERPAPI: Final[bool] = CFG.HAS_SERPAPI
HAS_TAVILY: Final[bool] = CFG.HAS_TAVILY
MAX_INDEXED_PER_ROUND: Final[int] = CFG.MAX_INDEXED_PER_ROUND
MAX_SEARCH_QUERIES_PER_ROUND: Final[int] = CFG.MAX_SEARCH_QUERIES_PER_ROUND
LOCAL_RAG_ALLOW: Final[str] = CFG.LOCAL_RAG_ALLOW
GOOGLEISH_HINTS: Final[List[str]] = CFG.GOOGLEISH_HINTS
ALLOW_FORCED_QUERIES: Final[bool] = CFG.ALLOW_FORCED_QUERIES
FORCED_QUERY_LOOKBACK: Final[int] = CFG.FORCED_QUERY_LOOKBACK
FORCED_QUERY_MAX_PER_RUN: Final[int] = CFG.FORCED_QUERY_MAX_PER_RUN
FORCED_QUERY_MIN_LEN: Final[int] = CFG.FORCED_QUERY_MIN_LEN
FORCED_QUERY_EXPAND_YEAR_RANGES: Final[bool] = CFG.FORCED_QUERY_EXPAND_YEAR_RANGES
FORCED_QUERY_YEAR_SPAN_LIMIT: Final[int] = CFG.FORCED_QUERY_YEAR_SPAN_LIMIT
FORCED_QUERY_ENABLE_SITE_SPLIT: Final[bool] = CFG.FORCED_QUERY_ENABLE_SITE_SPLIT
FORCED_QUERY_ENFORCE_GATEKEEP: Final[bool] = CFG.FORCED_QUERY_ENFORCE_GATEKEEP

# ── LLM 관련 하위호환 상수(선택) ─────────────────────────────
LLM_PROVIDER: Final[str] = CFG.LLM_PROVIDER
RAG_EMBEDDING_MODEL: Final[str] = CFG.RAG_EMBEDDING_MODEL
BLOCKAGI_TEST_FAKE_LLM: Final[bool] = CFG.BLOCKAGI_TEST_FAKE_LLM
OPENAI_MODEL: Final[str] = CFG.OPENAI_MODEL
OPENAI_EMBEDDING_MODEL: Final[str] = CFG.OPENAI_EMBEDDING_MODEL
OPENAI_BASE_URL: Final[str] = CFG.OPENAI_BASE_URL
OPENAI_API_BASE: Final[str] = CFG.OPENAI_API_BASE
OPENAI_ORG_ID: Final[str] = CFG.OPENAI_ORG_ID
OPENAI_ORGANIZATION: Final[str] = CFG.OPENAI_ORGANIZATION
OPENAI_REQUEST_TIMEOUT: Final[float] = CFG.OPENAI_REQUEST_TIMEOUT
OPENAI_MAX_RETRIES: Final[int] = CFG.OPENAI_MAX_RETRIES
GEMINI_MODEL: Final[str] = CFG.GEMINI_MODEL
GEMINI_EMBEDDING_MODEL: Final[str] = CFG.GEMINI_EMBEDDING_MODEL
LLM_MODEL: Final[str] = CFG.LLM_MODEL
GCP_PROJECT_ID: Final[str] = CFG.GCP_PROJECT_ID
GCP_REGION: Final[str] = CFG.GCP_REGION
