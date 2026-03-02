# agent\vector_search.py -*- coding: utf-8 -*-
from __future__ import annotations

import logging, os, re, json as _json
from typing import TypedDict, List, Any, Mapping, cast, MutableMapping, Tuple, Dict
logger = logging.getLogger(__name__)

from utils.tasks import (
    HumanMessage, AIMessage, has_pending, iter_tool_calls, schedule_writer_if_needed
)
from core.llm import get_llm
import core.config as config
from core.paths import current_path, now_str as _now_str
from core.state_types import State
from core.models import Task
from utils.sanitize import sanitize_state, as_int
from utils.rag_utils import (
    merge_refs,
    is_qa_like,
    set_direct_qa_flag,
    mark_qa_answer_ready,
    clear_qa,
    refs_preview_text as _refs_preview_text,
)
from utils.query_filters import (
    strip_web_filters as _strip_web_filters,
    looks_like_local_glob as _looks_like_local_glob,
    clean_seed as _clean_seed,
    ok_query as _ok_query,
)
from prompts import get_vector_search_prompt, get_direct_qa_prompt
from utils.tasks import has_pending, iter_tool_calls, schedule_writer_if_needed
from utils.outline import get_topic_outline_text
from tools.web_rag import (
    retrieve,
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
    ensure_vector_store_cleared_once,
    _default_chroma_dir,
)

from typing import Any, Sequence

# URL/NS/경로 유틸(공식)
from tools.web_rag.utils import (
    sanitize_ns as _wr_sanitize_ns,
    _resolve_persist_dir as _wr_resolve_persist_dir,
    normalize_url as _wr_normalize_url,
    _host_only as _wr_host_only,
)
from tools.local_rag import ingest_local_files
from utils.text_utils import plain_snip as _plain_snip

from collections import Counter

from utils.ref_format import format_ref_for_log

from typing import Callable, Optional, TYPE_CHECKING
from pathlib import Path

from typing import Any, List, Optional, Sequence  # 파일 상단에 없으면 추가

from tools.web_rag import retrieve

try:
    from tools.metrics import record_retrieval_source as _record_retrieval_source  # pyright: ignore[reportMissingImports]
except Exception:
    _record_retrieval_source = None  # type: ignore[assignment]

# ── QA 최소 응답 보장 유틸(Direct QA 실패 시에도 메시지 생성) ────────────────
def _emit_min_qa(
    state: MutableMapping[str, Any],
    references: "Refs",
    messages: list[Any],
    *,
    reason: str = ""
) -> None:
    try:
        used_refs = _refs_preview_text(cast(Mapping[str, Any], references)) if (references.get("docs") or []) else ""
    except Exception:
        used_refs = ""
    if used_refs:
        answer_text = (
            "핵심 근거를 토대로 간단히 답합니다. 상세 근거는 이어서 보강하겠습니다.\n\n"
            "현재 확보 근거 미니요약:\n" + used_refs
        )
    else:
        answer_text = (
            "현재 확보된 근거가 부족해 신뢰도 높은 직답을 구성하기 어렵습니다. "
            "웹 소스를 보강하는 동안 우선 요지를 안내드립니다."
        )
    messages.append(
        AIMessage(
            content=answer_text,
            additional_kwargs={
                "role": "qa",
                "qa_fallback": True,
                "refs_preview": used_refs,
                "reason": (reason or "direct_qa_min_response"),
            },
        )
    )

    flags_now = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    flags_now["qa_fallback"] = True
    state["flags"] = dict(flags_now)
    state["messages"] = messages
    # 라우터 힌트
    cast(MutableMapping[str, Any], state)["next_agent"] = "communicator"


# ── Optional runtime hooks from tools.web_rag.ingest (safe optional binding) ──
#   - mypy `no-redef` 회피: 임시 이름으로 import → 사전 선언 변수에 대입
_get_collection_count: Optional[Callable[[str, str], int]] = None
_has_any_docs: Optional[Callable[[str, str], bool]] = None
try:
    from tools.web_rag.ingest import get_collection_count as _ingest_get_collection_count  # noqa: F401
    from tools.web_rag.ingest import has_any_docs as _ingest_has_any_docs  # noqa: F401
    _get_collection_count = _ingest_get_collection_count
    _has_any_docs = _ingest_has_any_docs
except Exception:
    # 두 훅은 선택 사항이므로 실패해도 무시
    _get_collection_count = None
    _has_any_docs = None


def record_retrieval_source(
    web_cnt: int,
    local_cnt: int,
    *,
    base_cnt: int = 0,
    total: Optional[int] = None,
) -> None:
    try:
        if _record_retrieval_source is not None:
            func = cast(Callable[..., None], _record_retrieval_source)
            func(web_cnt=web_cnt, local_cnt=local_cnt, base_cnt=base_cnt, total=total)
    except Exception:
        pass

# ── Refs ──────────────────────────────────────────────────────────────────────
class Refs(TypedDict):
    queries: List[str]
    docs: List[Any]

def _to_refs(raw: Mapping[str, Any] | None) -> Refs:
    if not isinstance(raw, Mapping):
        return {"queries": [], "docs": []}
    return {"queries": list(cast(List[str], raw.get("queries") or [])),
            "docs":    list(cast(List[Any], raw.get("docs") or []))}

def get_refs(state: Mapping[str, Any]) -> Refs:
    """
    호환성 유지: 우선 refs → references 순으로 조회.
    일부 경로가 refs만 갱신하거나 references만 갱신하는 문제를 방지.
    """
    raw = cast(Mapping[str, Any] | None, state.get("refs"))
    if not raw:
        raw = cast(Mapping[str, Any] | None, state.get("references"))
    return _to_refs(raw)

# ── config helpers (env → CFG → module default) ───────────────────────────────
def _cfg_str(name: str, default: str = "") -> str:
    try:
        v = getattr(config.CFG, name, None)
        if v is None:
            v = getattr(config, name, None)
    except Exception:
        v = None
    if v is None:
        v = os.getenv(name, default)
    return str(v) if v is not None else default

def _cfg_int(name: str, default: int = 0) -> int:
    v = _cfg_str(name, str(default))
    try:
        return int(str(v).strip())
    except Exception:
        return default

def _cfg_float(name: str, default: float = 0.0) -> float:
    v = _cfg_str(name, str(default))
    try:
        return float(str(v).strip())
    except Exception:
        return default

def _cfg_bool(name: str, default: bool = False) -> bool:
    v = _cfg_str(name, "1" if default else "0").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}

# ── logging helpers (runtime-config aware) ────────────────────────────────────
def _log_topk() -> int:
    return _cfg_int("LOG_TOPK", 5)

def _log_wrap() -> int:
    return _cfg_int("LOG_WRAP", 120)

def _ell(s: str, n: Optional[int] = None) -> str:
    if n is None:
        n = _log_wrap()
    s = (s or "").replace("\n", " ").strip()
    return (s[:n-1] + "…") if len(s) > n else s

def _host(u: str) -> str:
    # 안전 호스트 추출(경로 혼입 방지) — 정규화 후 host-only
    try:
        return _wr_host_only(_wr_normalize_url(u))
    except Exception:
        return _wr_host_only(u)

def _raw_title(d: Any) -> str:
    meta = getattr(d, "metadata", {}) or {}
    t = meta.get("title") or ""
    if not t:
        t = (getattr(d, "page_content", "") or "").split("\n", 1)[0]
    return (t or "").strip()

def _doc_title(d: Any) -> str:
    t = _raw_title(d)
    return _ell(t or "(no title)")

def _doc_url(d: Any) -> str:
    meta = getattr(d, "metadata", {}) or {}
    # 일부 로더는 path를 사용함
    return meta.get("source") or meta.get("url") or meta.get("path") or ""


def _doc_score(d: Any):
    s = getattr(d, "score", None)
    if s is None:
        meta = getattr(d, "metadata", {}) or {}
        s = meta.get("score")
    return s


def _domain_bonus(url: str) -> float:
    """
    도메인별 가중치:
    - LOCAL(file://)      : 강한 가중치 +
    - 약업/의약 전문 매체 : 중간 가중치 +
    - 공공 통계/규제 기관 : 약한 가중치 +
    - KRX/KIND, 해외 재무 : 감점
    """
    if not url:
        return 0.0
    if url.startswith("file://"):
        return 1.5

    h = _host(url).lower()
    if not h:
        return 0.0

    # 약업/의약 전문 매체
    pharma_hosts = (
        "dailypharm.com", "medipana.com", "kpanews.co.kr",
        "yakup.com", "pharmnews.com", "medicopharma.co.kr",
        "healtho.co.kr",
    )
    # 공공 통계/규제/공시
    public_hosts = (
        "kosis.kr", "index.go.kr", "data.go.kr", "moef.go.kr",
        "mfds.go.kr", "hira.or.kr", "khidi.or.kr", "law.go.kr",
        "dart.fss.or.kr",
    )

    if any(h.endswith(p) for p in pharma_hosts):
        return 1.0
    if any(h.endswith(p) for p in public_hosts):
        return 0.8
    if h.endswith("krx.co.kr") or "financialreports.eu" in h:
        return -0.5
    return 0.0


def _rerank_docs_by_domain(docs: list[Any]) -> list[Any]:
    """
    벡터 스코어 + 도메인 보너스를 합산해 재정렬.
    ENABLE_DOMAIN_RERANK=0 이면 비활성화.
    """
    if not docs:
        return docs
    try:
        if not _cfg_bool("ENABLE_DOMAIN_RERANK", True):
            return docs
    except Exception:
        # config 로딩 문제 시에는 원래 순서 유지
        return docs

    scored: list[tuple[float, float, Any]] = []
    for d in docs:
        base = _doc_score(d)
        try:
            base_f = float(base) if base is not None else 0.0
        except Exception:
            base_f = 0.0
        bonus = _domain_bonus(_doc_url(d))
        scored.append((base_f + bonus, base_f, d))

    # (base+bonus, base) 기준 내림차순 정렬
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [t[2] for t in scored]



# URL 정규화(추적 파라미터 제거 + fragment 제거 + 소문자 + 트레일링 슬래시 제거)
def _normalize_url(u: str) -> str:
    # 규칙 일원화: tools.web_rag.utils.normalize_url 사용
    return _wr_normalize_url(u)

def _dedupe_docs(docs: list[Any]) -> list[Any]:
    """(normalized url, lowered title) 키로 문서 중복 제거."""
    seen, out = set(), []
    for d in docs or []:
        url = _normalize_url(_doc_url(d))
        title = (_raw_title(d) or "").lower()
        key = (url, title)
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out

def _log_retrieval(query: str, docs: list[Any], tag: str = "vector_search") -> None:
    try:
        logger.info("[%(tag)s][query] %(q)s", {"tag": tag, "q": _ell(query)})
        if not docs:
            logger.info("[%(tag)s] no hits", {"tag": tag})
            return

        lines, topn = [], min(_log_topk(), len(docs))
        for i, d in enumerate(docs[:topn], start=1):
            raw_url = _doc_url(d)
            title = _doc_title(d)
            # 사람이 읽기 쉬운 표시 두 줄 생성
            title_line, link_line = format_ref_for_log(raw_url)

            # 로컬/웹 라벨
            label = "LOCAL" if raw_url.startswith("file://") else _host(raw_url) or ""
            score = _doc_score(d)
            score_part = f"  (score={score})" if score is not None else ""

            # 타이틀은 메타데이터 우선, 없으면 포매터 타이틀 사용
            main_title = title or title_line

            lines.append(f"  {i:>2}. {main_title}\n      └─ {label} :: {link_line}{score_part}")

        logger.info("[%(tag)s][top%(n)d]\n%(body)s", {"tag": tag, "n": topn, "body": "\n".join(lines)})
    except Exception:
        pass

# ── Dual-namespace retrieve (웹/로컬 병합) ────────────────────────────────────
def _env_ratio() -> float:
    r = _cfg_float("RETRIEVE_WEB_RATIO", 0.5)
    return 0.0 if r < 0 else (1.0 if r > 1 else r)

def _split_k(top_k: int) -> Tuple[int, int]:
    """웹/로컬 k 분배: round half up 보정으로 최소 1 보장."""
    k = max(1, int(top_k or 1))
    r = _env_ratio()
    k_web = max(1, int(round(k * r))) if k > 1 else 1
    k_loc = max(0, k - k_web)
    return (k_web, k_loc)

def _merge_web_first(web_docs: List[Any], local_docs: List[Any], k: int) -> List[Any]:
    """웹 우선 인터리브: w, l, w, l ... 식으로 채우되, 부족분은 나머지로 채움."""
    merged: List[Any] = []
    i = j = 0
    while len(merged) < k and (i < len(web_docs) or j < len(local_docs)):
        if i < len(web_docs):
            merged.append(web_docs[i]); i += 1
        if len(merged) >= k: break
        if j < len(local_docs):
            merged.append(local_docs[j]); j += 1
    return _dedupe_docs(merged)[:k]

def _merge_by_score(web_docs: List[Any], local_docs: List[Any], k: int) -> List[Any]:
    """간단 점수 병합(없으면 웹>로컬 우선순)."""
    both = []
    for d in (web_docs or []):
        both.append(("web", _doc_score(d) or 0.0, d))
    for d in (local_docs or []):
        both.append(("local", _doc_score(d) or 0.0, d))
    # 점수 내림차순, 동점은 웹 우선
    both.sort(key=lambda x: (x[1], 1 if x[0]=="local" else 2), reverse=True)
    return _dedupe_docs([t[2] for t in both])[:k]

def _dual_retrieve(query: str, *, top_k: int, ns_default: str, persist_dir: str) -> List[Any]:
    """환경설정에 따라 웹/로컬(+기본) 네임스페이스를 병합 조회.
       ⚠️ 말미에 기본 NS로 '무조건 폴백'을 수행하여 0-hit 반복을 방지한다.
       ⚠️ persist_directory는 호출 인자(persist_dir)를 우선 사용하여 모든 NS에 일관 적용.
    """
    import inspect  # 파일 상단에 없으면 추가

    ns_web = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    # ✅ env가 비어 있으면 ns_default 기반으로 자동 파생 (ingest 쪽 split 네임스페이스와 정합)
    if not ns_web:
        ns_web = f"{ns_default}-web"
    if not ns_loc:
        ns_loc = f"{ns_default}-local"
    include_base_cfg = _cfg_bool("CHROMA_INCLUDE_BASE", False)
    mode = (_cfg_str("MERGE_RETRIEVE_MODE", "web_first") or "web_first").lower()

    logger.debug(
        "[dual-retrieve][ns] ns_default=%s ns_web=%s ns_loc=%s",
        ns_default, ns_web, ns_loc
    )

    # persist_directory 일관성: 외부 인자가 있으면 모든 NS에 동일 적용, 없으면 기본 규칙
    def _dir_for(ns_name: str) -> str:
        """
        persist_directory 인자가 주어졌다면 모든 NS에 동일 규칙을 적용하되,
        최종 경로는 _resolve_persist_dir로 일관 생성한다.
        """
        base = persist_dir.strip() if (persist_dir and str(persist_dir).strip()) else _default_chroma_dir(ns_name)
        # ns_name은 반드시 sanitize된 값이어야 함
        return _wr_resolve_persist_dir(ns_name, base)

    def _call_retrieve(q: str, *, ns_name: str, k: int) -> List[Any]:
        if k <= 0:
            return []
        q_clean = (q or "").strip()
        if not q_clean:
            return []
        try:
            logger.warning(
                "[CHECK][_call_retrieve][which] retrieve=%r module=%s",
                retrieve,
                getattr(retrieve, "__module__", "?"),
            )
            return list(retrieve(q_clean, namespace=ns_name, persist_directory=_dir_for(ns_name), top_k=k) or [])
        except Exception as e:
            logger.warning("retrieve 실패(ns='%s'): %s", ns_name, e)
            return []

    # ✅ [CHECK] 현재 ns/persist_dir 기준으로 실제 컬렉션이 있는지 카운트 확인 (0-hit 원인 규명용)
    try:
        web_dir = _dir_for(ns_web) if ns_web else ""
        loc_dir = _dir_for(ns_loc) if ns_loc else ""
        base_dir = _dir_for(ns_default)

        web_cnt = _collection_count(ns_web, web_dir) if ns_web else None
        loc_cnt = _collection_count(ns_loc, loc_dir) if ns_loc else None
        base_cnt = _collection_count(ns_default, base_dir)

        logger.warning(
            "[CHECK][dual-retrieve][count] web=%s (ns=%s dir=%s) | local=%s (ns=%s dir=%s) | base=%s (ns=%s dir=%s)",
            web_cnt, ns_web, web_dir,
            loc_cnt, ns_loc, loc_dir,
            base_cnt, ns_default, base_dir,
        )
    except Exception as e:
        logger.warning("[CHECK][dual-retrieve][count] failed: %s", e)


    # ◀︎ 변경: 사용자가 CHROMA_INCLUDE_BASE=1 을 지정한 경우,
    #          컬렉션 비어있어도 include_base를 유지(초기 빈약 문제 완화).
    include_base = bool(include_base_cfg)
    if include_base:
        try:
            base_ns = ns_default
            base_dir = _dir_for(base_ns)
            cnt = _collection_count(base_ns, base_dir)
            logger.debug("[dual-retrieve] base collection count=%s (ns=%s dir=%s) | include_base=%s",
                         cnt, base_ns, base_dir, include_base)
        except Exception as e:
            logger.debug("[dual-retrieve] base collection check skipped: %s | include_base=%s", e, include_base)


    # 내부 헬퍼

    def _get(ns_name: str, k: int, src: str) -> List[Any]:
        if k <= 0:
            return []
        try:
            docs = _call_retrieve(query, ns_name=ns_name, k=k)
            logger.warning("[CHECK][_get] src=%s ns=%s k=%d raw=%d", src, ns_name, k, len(docs or []))
            # ✅ provenance tag: 이 doc이 어디서 retrieve됐는지 표시
            for d in docs:
                try:
                    md = getattr(d, "metadata", None)
                    if isinstance(md, dict):
                        md["_retrieved_src"] = src      # "web" | "local" | "base"
                        md["_retrieved_ns"] = ns_name   # 실제 namespace
                except Exception:
                    pass

            return docs
        except Exception as e:
            logger.warning("retrieve 실패(ns='%s'): %s", ns_name, e)
            return []

    # 1) (공통) 웹/로컬 조회
    #    - 우선 웹/로컬을 k 분할로 조회 (한쪽만 설정된 경우 자동으로 (top_k,0) 또는 (0,top_k))
    k_web, k_loc = _split_k(top_k) if (ns_web and ns_loc) else ((top_k, 0) if ns_web else (0, top_k))
    web_raw = _get(ns_web, k_web, "web") if ns_web else []
    loc_raw = _get(ns_loc, k_loc, "local") if ns_loc else []
    web_docs = _dedupe_docs(web_raw)
    loc_docs = _dedupe_docs(loc_raw)

    logger.warning(
        "[CHECK][dual-retrieve][peek] k=%d split(web=%d,local=%d) raw(web=%d,local=%d) dedupe(web=%d,local=%d)",
        top_k, k_web, k_loc,
        len(web_raw or []), len(loc_raw or []),
        len(web_docs or []), len(loc_docs or [])
    )

    # 2) base 포함 설정이면 부족분만큼 기본 NS에서 추가
    base_docs: List[Any] = []
    if include_base:
        remaining = max(0, top_k - len(web_docs) - len(loc_docs))
        if remaining > 0:
            try:
                base_docs = _dedupe_docs(_call_retrieve(query, ns_name=ns_default, k=remaining))

                # ✅ base provenance tag (include_base로 채운 문서도 출처가 보이게)
                for d in (base_docs or []):
                    try:
                        md = getattr(d, "metadata", None)
                        if isinstance(md, dict):
                            md["_retrieved_src"] = "base"
                            md["_retrieved_ns"] = ns_default
                    except Exception:
                        pass

                logger.info("[dual-retrieve] include_base used → fetched %d from base", len(base_docs))
            except Exception as e:
                logger.warning("retrieve 실패(base ns='%s'): %s", ns_default, e)
                base_docs = []

    # 3) 병합 정책 적용
    if mode == "score_merge":
        # 세 소스(웹/로컬/기본)를 점수 기준으로 통합 정렬(동점: 웹>로컬>기본)
        pool = []
        for d in web_docs:  pool.append(("web",   _doc_score(d) or 0.0, d))
        for d in loc_docs:  pool.append(("local", _doc_score(d) or 0.0, d))
        for d in base_docs: pool.append(("base",  _doc_score(d) or 0.0, d))
        prio = {"web": 3, "local": 2, "base": 1}  # 동점 우선순위
        pool.sort(key=lambda x: (x[1], prio.get(x[0], 0)), reverse=True)
        merged = _dedupe_docs([t[2] for t in pool])[:top_k]
    else:
        # web_first: 웹/로컬 인터리브 후, 부족분을 기본으로 보충
        merged = _merge_web_first(web_docs, loc_docs, top_k)
        if include_base and len(merged) < top_k and base_docs:
            tail_need = top_k - len(merged)
            merged = list(merged) + list(base_docs)[:tail_need]

    # 3-1) 도메인 기반 재정렬 적용
    merged = _rerank_docs_by_domain(list(merged or []))
    merged = _dedupe_docs(merged)[:top_k]

    # 4) ✅ 무조건 폴백: 병합 결과가 비었으면 기본 NS에서 재조회
    if not merged:
        try:
            fallback = _dedupe_docs(_call_retrieve(query, ns_name=ns_default, k=top_k))

            # ✅ base provenance tag (fallback으로 돌아온 문서도 출처가 보이게)
            for d in (fallback or []):
                try:
                    md = getattr(d, "metadata", None)
                    if isinstance(md, dict):
                        md["_retrieved_src"] = "base"
                        md["_retrieved_ns"] = ns_default
                except Exception:
                    pass

            # 폴백 결과에도 도메인 재랭킹 적용
            fallback = _rerank_docs_by_domain(list(fallback or []))
            fallback = _dedupe_docs(fallback)[:top_k]
            if fallback:
                logger.warning("[dual-retrieve] web/local empty → FALLBACK to base ns='%s' (%d hits)",
                               ns_default, len(fallback))
                # [METRICS] 폴백이 적용된 경우: 베이스만으로 집계
                try:
                    record_retrieval_source(web_cnt=0, local_cnt=0, base_cnt=len(fallback or []), total=len(fallback or []))
                except Exception:
                    pass

                return fallback
        except Exception as e:
            logger.warning("retrieve 실패(fallback base ns='%s'): %s", ns_default, e)

    logger.debug(
        "[dual-retrieve] mode=%s include_base=%s k=%d (web=%d, local=%d, base=%d) → merged=%d | ns_default=%s",
        mode, include_base, top_k, len(web_docs), len(loc_docs), len(base_docs), len(merged or []), ns_default
    )
    # [METRICS] 병합 결과의 웹/로컬(및 베이스) 비율 집계
    try:
        m_ids = {id(d) for d in (merged or [])}
        web_in  = sum(1 for d in (web_docs  or []) if id(d) in m_ids)
        local_in= sum(1 for d in (loc_docs  or []) if id(d) in m_ids)
        base_in = sum(1 for d in (base_docs or []) if id(d) in m_ids)
        record_retrieval_source(web_cnt=web_in, local_cnt=local_in, base_cnt=base_in, total=len(merged or []))
    except Exception:
        pass

    # ✅ [CHECK] metadata 기반 출처 카운트(객체 id 재생성 문제 회피)
    try:
        from collections import Counter
        src_cnt = Counter(
            (getattr(d, "metadata", {}) or {}).get("_retrieved_src", "unknown")
            for d in (merged or [])
        )
        ns_cnt = Counter(
            (getattr(d, "metadata", {}) or {}).get("_retrieved_ns", "unknown")
            for d in (merged or [])
        )
        logger.warning("[CHECK][dual-retrieve][merged] src=%s | ns=%s", dict(src_cnt), dict(ns_cnt))
    except Exception:
        pass

    return merged

# ── collection size helpers (optional, safe fallbacks) ────────────────────────
def _collection_count(ns: str, persist_dir: str) -> int:
    """
    벡터 스토어의 ns 컬렉션에 문서가 몇 개인지 추정.
    - tools.web_rag.ingest.get_collection_count 가 있으면 그것을 사용
    - 없으면 has_any_docs로 0/1만 판정
    - 실패 시 -1 반환(불명)
    """
    # 1) 명시적 카운트 함수가 있으면 그것을 사용
    try:
        if callable(_get_collection_count):
            return int(_get_collection_count(ns, persist_dir))
    except Exception:
        pass
    # 2) 폴백: 존재 여부만 체크(있으면 1, 없으면 0)
    try:
        if callable(_has_any_docs):
            ok = bool(_has_any_docs(ns, persist_dir))
            return 1 if ok else 0
    except Exception:
        pass
    # 3) 불명
    return -1


# ── Main ──────────────────────────────────────────────────────────────────────
def vector_search_agent(state: State):
    logger.info("============ VECTOR SEARCH AGENT ============")
    llm = get_llm()
    state = cast(State, sanitize_state(state))

    # ── [DIRECT_QA] 모드: 선주입 금지 → 의도만 표시하고, 실제 답변 생성 시점에만 qa_direct_reply=True 세팅
    try:
        dq = bool(getattr(config.CFG, "DIRECT_QA", False))
    except Exception:
        dq = False
    if dq:
        flags_mm0 = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
        # 의도 플래그만 남김: 실제 답변 생성 성공 시점에 qa_direct_reply/suppress_writer를 켠다.
        flags_mm0["direct_qa_intent"] = True
        # 과거 선세팅 잔여치가 남아있다면 방지
        flags_mm0.pop("qa_direct_reply", None)
        flags_mm0.pop("suppress_writer", None)
        logger.debug("[vector_search][direct_qa] intent=1 (qa_direct_reply will be set only after answer is generated)")

    tasks = state.get("task_history", []) or []
    messages = state.get("messages", []) or []
    if not tasks:
        # 방어적 처리: 작업 이력이 없더라도 자체 펜딩을 생성해 진행
        logger.warning("[vector_search] task_history empty → auto-create and pend self")
        tasks = []
        # state는 TypedDict(State)이므로 MutableMapping으로 캐스팅 후 갱신
        cast(MutableMapping[str, Any], state)["task_history"] = tasks
        auto_task = Task(agent="vector_search_agent", done=False, description="auto-pend", done_at="")
        tasks.append(auto_task)
        # messages에도 안내 메시지를 남겨 가시성 확보(선택)
        messages.append(AIMessage(content="[VECTOR SEARCH AGENT] 펜딩이 없어 자동으로 등록하고 진행합니다."))

    pending = next((t for t in reversed(tasks) if (not t.done) and t.agent == "vector_search_agent"), None)
    if pending is None:
        # 마지막 태스크가 본인이며 미완료면 그것을 사용
        if tasks:
            last = tasks[-1]
            if (getattr(last, "agent", "") == "vector_search_agent") and (not getattr(last, "done", True)):
                pending = last
        # 그래도 없으면 자동 펜딩 추가 후 진행
        if pending is None:
            logger.warning("[vector_search] pending missing → auto-append and continue")
            auto_task = Task(agent="vector_search_agent", done=False, description="auto-pend", done_at="")
            tasks.append(auto_task)
            # state 반영(참조 동일하지만 안전하게 다시 대입)
            cast(MutableMapping[str, Any], state)["task_history"] = tasks
            messages.append(AIMessage(content="[VECTOR SEARCH AGENT] 기존 펜딩이 없어 자동 등록했습니다."))
            pending = auto_task

    vector_search_system_prompt = get_vector_search_prompt()

    mission = (pending.description or "")
    references: Refs = get_refs(state)
    outline_text = get_topic_outline_text(state)

    # ✅ 플래너/레퍼런스 기반 seed 쿼리 후보 확보
    plan_qs = ((state.get("research_plan") or {}).get("queries") or []) or (state.get("planner_queries") or [])
    refs_qs = list(references.get("queries") or [])

    # Namespace & persist dir
    topic_slug_raw: str = (state.get("topic_slug") or getattr(config.CFG, "TOPIC_SLUG", "") or "default").strip()
    env_ns_raw = (_cfg_str("CHROMA_NAMESPACE", "") or "").strip()
    # ▶︎ 네임스페이스 정규화(일관 규칙)
    topic_slug = _wr_sanitize_ns(topic_slug_raw)
    env_ns    = _wr_sanitize_ns(env_ns_raw) if env_ns_raw else ""
    ns: str   = env_ns or _wr_sanitize_ns(f"{topic_slug}-default")
    # ▶︎ persist_dir도 공식 규칙으로 결정(leaf/base 모두 허용)
    persist_dir = _wr_resolve_persist_dir(ns, _default_chroma_dir(ns))

    # ── [ANCHOR: NS_POLICY_INIT] 웹/로컬 NS 병합 정책(환경변수 우선) ─────────────
    ns_web_raw = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()
    ns_loc_raw = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()
    ns_web = _wr_sanitize_ns(ns_web_raw) if ns_web_raw else ""
    ns_loc = _wr_sanitize_ns(ns_loc_raw) if ns_loc_raw else ""
    merge_mode = (_cfg_str("MERGE_RETRIEVE_MODE", "web_first") or "web_first").lower()
    web_ratio = _cfg_float("RETRIEVE_WEB_RATIO", 0.5)
    include_base = _cfg_bool("CHROMA_INCLUDE_BASE", False)

    # 상태/플래그에 NS 정책 기록 (디버그/가시성)
    flags = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    chroma = cast(MutableMapping[str, Any], flags.setdefault("chroma", {}))
    chroma.update({
        "ns": ns, "dir": persist_dir,
        "ns_web": ns_web, "ns_local": ns_loc,
        "merge_retrieve_mode": merge_mode,
        "retrieve_web_ratio": web_ratio,
        "include_base": include_base,
    })

    # [변경] base 컬렉션이 비어 있어도, 사용자가 CHROMA_INCLUDE_BASE=1이면 유지
    try:
        want_include = _cfg_bool("CHROMA_INCLUDE_BASE", False)
        if callable(_has_any_docs):
            has_base = bool(_has_any_docs(ns, persist_dir))
            if not has_base and not want_include:
                include_base = False
                chroma["include_base"] = False
                logger.debug("[vector_search] base empty & CHROMA_INCLUDE_BASE=0 → include_base=False (ns=%s)", ns)
            else:
                logger.debug("[vector_search] base %s, CHROMA_INCLUDE_BASE=%s → include_base=%s",
                             "present" if has_base else "empty", want_include, include_base)
    except Exception as e:
        logger.debug("[vector_search] base presence check skipped: %s | include_base=%s", e, include_base)

    # 양쪽(NS_WEB/NS_LOCAL) 모두 설정되어 있고 include_base가 꺼져 있으면
    # 기본 NS에서도 부족분을 보충하도록 안내 로그(정책 확인용)
    if ns_web and ns_loc and not include_base:
        logger.info("[vector_search][ns_policy] Both web/local namespaces set. "
                    "Consider enabling CHROMA_INCLUDE_BASE=1 to backfill from base ns (optional).")

    logger.info("[vector_search][ns_policy] ns(web)=%r ns(local)=%r base=%r | mode=%s ratio=%.2f",
                ns_web or "-", ns_loc or "-", ns, merge_mode, web_ratio)

    # ── 비어있는 컬렉션 자동 스킵(환경으로 on/off) ─────────────────────────
    _skip_empty = _cfg_bool("RETRIEVE_SKIP_EMPTY_NS", True)
    if _skip_empty:
        try:
            def _cnt(_ns: str) -> int:
                if not _ns: return 0
                return _collection_count(_ns, _wr_resolve_persist_dir(_ns, _default_chroma_dir(_ns)))
            _web_cnt  = _cnt(ns_web)
            _loc_cnt  = _cnt(ns_loc)
            _base_cnt = _cnt(ns)
            logger.info("[vector_search][ns_counts] web=%s local=%s base=%s", _web_cnt, _loc_cnt, _base_cnt)
            # 실제 문서가 0이면 해당 NS 비활성화
            if ns_web and _web_cnt <= 0:
                logger.info("[vector_search] web ns empty → skip web retrieve (ns=%s)", ns_web)
                ns_web = ""
            if ns_loc and _loc_cnt <= 0:
                logger.info("[vector_search] local ns empty → skip local retrieve (ns=%s)", ns_loc)
                ns_loc = ""
            # base가 비면 include_base는 끔(아래 로직과 일관)
            # base=0이어도 사용자가 CHROMA_INCLUDE_BASE=1이면 유지
            if _base_cnt <= 0 and not _cfg_bool("CHROMA_INCLUDE_BASE", False):
                include_base = False
                chroma["include_base"] = False
        except Exception as e:
            logger.debug("[vector_search] ns count check skipped: %s", e)


    # 웹/로컬 네임스페이스가 있으면 1회 초기화 가드도 양쪽 적용
    try:
        ensure_vector_store_cleared_once(namespace=ns, persist_directory=persist_dir)
        # reload_config() 이후 값 반영 보장
        ns_web = (_cfg_str("CHROMA_NAMESPACE_WEB", "") or "").strip()
        ns_loc = (_cfg_str("CHROMA_NAMESPACE_LOCAL", "") or "").strip()
        if ns_web:
            ensure_vector_store_cleared_once(namespace=ns_web, persist_directory=_default_chroma_dir(ns_web))
        if ns_loc:
            ensure_vector_store_cleared_once(namespace=ns_loc, persist_directory=_default_chroma_dir(ns_loc))
    except Exception as e:
        logger.debug("ensure_vector_store_cleared_once skipped/failed: %s", e)

    flags = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    chroma = cast(MutableMapping[str, Any], flags.setdefault("chroma", {}))
    chroma["ns"], chroma["dir"] = ns, persist_dir

    logger.info("[vector_search] ns=%s (CHROMA_NAMESPACE=%r, topic_slug=%r)", ns, env_ns, topic_slug)
    logger.info("[vector_search] persist_dir(resolved)=%s", persist_dir)

    TOP_K = _cfg_int("RAG_TOP_K", 5)

    # ────────────────────────────────────────────────────────────────────
    # [SMOKE RETRIEVE] 시작점 품질 점검: 2~3개 선택 질의로 top-1 조회
    #   - 목적: 인덱스/네임스페이스/쿼리 정규화가 정상 동작하는지 빠르게 확인
    #   - 실패(전부 미스) 시: 라우팅 중단 + 사용자/로그 안내
    # 스위치: SMOKE_RETRIEVE(기본 on), SMOKE_RETRIEVE_MAX(기본 3)
    # ────────────────────────────────────────────────────────────────────
    def _mk_smoke_queries(st: Mapping[str, Any]) -> list[str]:
        title = (st.get("topic_title") or st.get("topic") or "").strip()
        base_qs: list[str] = []
        if title:
            base_qs.extend([f"{title} 성분", f"{title} 시장 규모", f"{title} 브랜드"])
        # 플래너/refs 보강(있으면 앞 2개만)
        plan = ((st.get("research_plan") or {}).get("queries") or [])[:2]
        refs = ((st.get("references") or {}).get("queries") or [])[:1]
        for q in list(plan) + list(refs):
            q = _strip_web_filters(_clean_seed(str(q or "")))
            if q and q not in base_qs:
                base_qs.append(q)
        # 과도 길이/노이즈 제거
        out: list[str] = []
        for q in base_qs:
            qc = _strip_web_filters(_clean_seed(q))
            if qc and (not _looks_like_local_glob(qc)) and _ok_query(qc):
                out.append(qc)
        max_n = max(1, _cfg_int("SMOKE_RETRIEVE_MAX", 3))
        return out[:max_n]

    def _summarize_doc(d: Any) -> str:
        try:
            ttl = _doc_title(d)
            url = _doc_url(d)
            score = _doc_score(d)
            host = "LOCAL" if (url or "").startswith("file://") else _host(url)
            sp = f" score={score}" if score is not None else ""
            return f"{ttl} | {host}{sp}"
        except Exception:
            return "(unknown)"

    flags_boot = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
    do_smoke = _cfg_bool("SMOKE_RETRIEVE", True) and not bool(flags_boot.get("smoke_retrieve_done"))
    if do_smoke:
        smoke_qs = _mk_smoke_queries(state)
        hits: list[tuple[str, Any]] = []
        for sq in smoke_qs:
            try:
                docs1 = _dual_retrieve(sq, top_k=1, ns_default=ns, persist_dir=persist_dir) or []
            except Exception as e:
                logger.warning("[smoke] retrieve 실패(q=%r): %s", sq, e)
                docs1 = []
            if docs1:
                top = docs1[0]
                hits.append((sq, top))
                logger.info("[smoke][hit] q=%s → %s", _ell(sq, 80), _summarize_doc(top))
            else:
                logger.info("[smoke][miss] q=%s", _ell(sq, 80))

        flags_boot["smoke_retrieve_done"] = True

        if not hits:
            # 전부 실패
            # ▶ DIRECT_QA가 켜져 있으면 스모크 실패만으로 중단하지 않고,
            #    곧이어 진행될 사용자 질의(DQ) 경로로 계속 진행한다.
            _direct_qa_on = False
            try:
                _direct_qa_on = bool(getattr(config.CFG, "DIRECT_QA", False))
            except Exception:
                _direct_qa_on = False

            if _direct_qa_on:
                logger.warning(
                    "[smoke] all queries miss, but DIRECT_QA=True → continue to user-query path "
                    "(ns=%s dir=%s)", ns, persist_dir
                )
                # 중단하지 않고 아래 일반 흐름으로 진행
            else:
                # 조기 종료(라우팅 stop) + 안내
                note = (
                    "[VECTOR SEARCH AGENT] 스모크 조회 결과, 인덱스에서 적합한 문서를 찾지 못했습니다.\n"
                    "- 점검 사항: (1) 네임스페이스/저장 경로, (2) 로컬 인제스트 수행 여부, (3) 웹 검색 후 인덱싱 상태\n"
                    "- 제안: web_search_agent 실행 또는 LOCAL_RAG_GLOBS 설정 후 재인제스트를 시도하세요."
                )
                messages.append(AIMessage(content=note))
                logger.warning("[smoke] all queries miss → stop routing (ns=%s dir=%s)", ns, persist_dir)
                pending.done = True
                pending.done_at = _now_str()
                flags_boot["routing_stopped_by_smoke"] = True
                return {"messages": messages, "task_history": tasks}
        
        else:
            # ── [DIRECT QA 게이트] 스모크 hit 중 최상위 스코어가 임계 이상이면 communicator 우선
            _MIN = _cfg_float("DIRECT_QA_MIN_SCORE", 0.35)
            _ALLOW_DUR = _cfg_bool("DIRECT_QA_ALLOW_DURING_RESEARCH", True)
            _REQ_SCORE = _cfg_bool("DIRECT_QA_REQUIRE_SCORE", True)

            def _score_of(d: Any) -> Optional[float]:
                s = _doc_score(d)
                try:
                    return float(s) if s is not None else None
                except Exception:
                    return None

            # 현재 연구 파이프라인 동작 중인지 경량 판정
            _pipeline_on = any(
                (getattr(t, "done", True) is False)
                and getattr(t, "agent", "") in ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")
                for t in (state.get("task_history") or [])
            )
            _ok_during = (not _pipeline_on) or (_ALLOW_DUR is True)

            # 점수 최댓값을 가진 문서 선택(스코어 없으면 정책에 따라 배제/허용)
            best_q, best_doc, best_sc = None, None, None
            for q, d in hits:
                sc = _score_of(d)
                if sc is None and _REQ_SCORE:
                    continue
                if (best_sc is None) or ((sc or 0.0) > (best_sc or 0.0)):
                    best_q, best_doc, best_sc = q, d, (sc if sc is not None else 0.0)

            if _ok_during and best_doc is not None and (best_sc is not None) and (best_sc >= _MIN):
                # writer가 이미 대기 중이면 직답 우선권을 양보
                _has_writer = (
                    has_pending(tasks, "section_writer", prefix="write:")
                    or has_pending(tasks, "chapter_writer", prefix="write:")
                )
                if not _has_writer:
                    # facts_ctx 제공 + Direct QA 프롬프트 기반 요약 생성(Direct QA 본문을 messages에 기록)
                    reply_text: str = ""
                    try:
                        txt = (getattr(best_doc, "page_content", "") or "").strip()
                        state["facts_ctx"] = (txt[:800] if txt else "")
                        context = (txt[:1200] if txt else "").strip()

                        if context:
                            # ── 질문 텍스트 추출 ─────────────────────────────
                            # 1) state에 저장된 qa_query / last_user_query 우선
                            question = (
                                (state.get("qa_query") or "").strip()
                                or (state.get("last_user_query") or "").strip()
                            )
                            # 2) 없으면 마지막 HumanMessage에서 가져오기
                            if not question:
                                last_human = next(
                                    (m for m in reversed(messages) if isinstance(m, HumanMessage)),
                                    None,
                                )
                                if last_human is not None and getattr(last_human, "content", None):
                                    question = str(last_human.content).strip()

                            # ── Direct QA 프롬프트 + LLM 체인 ─────────────────
                            prompt = get_direct_qa_prompt()
                            # 이 스코프에 llm이 이미 있다면 재사용, 아니면 get_llm() 호출
                            try:
                                _llm = llm  # 기존 llm 변수가 있으면 사용
                            except NameError:
                                _llm = get_llm()

                            chain = prompt | _llm
                            qa_result = chain.invoke(
                                {
                                    "topic_title": state.get("topic_title") or "",
                                    "question": question,
                                    "context": context,
                                }
                            )
                            reply_text = getattr(qa_result, "content", qa_result)
                            reply_text = (reply_text or "").strip()

                    except Exception as e:
                        logger.warning("[vector_search][smoke→direct_qa] summary generation failed: %s", e)
                        reply_text = ""

                    # 답변이 생성되었으면 messages에 추가하고 Direct QA 플래그를 확실히 세움
                    if reply_text:
                        # 메시지 객체에도 직답 플래그를 명시하여 다운스트림이 확실히 감지하도록 한다.
                        messages.append(
                            AIMessage(
                                content=reply_text,
                                additional_kwargs={"qa_direct_reply": True, "role": "qa"},
                            )
                        )
                        state["messages"] = messages
                        # TypedDict(State)에는 명시 키가 없을 수 있으므로 가변 매핑으로 캐스팅 후 기록
                        state_mm = cast(MutableMapping[str, Any], state)
                        state_mm["answer"] = reply_text
                        state_mm["qa_reply"] = reply_text  # (옵션) 호환 키
                        try:
                            # utils.rag_utils.mark_qa_answer_ready: qa_direct_reply/suppress_writer 세팅
                            mark_qa_answer_ready(state_mm, reply_text)
                        except Exception:
                            flags_now = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
                            flags_now["qa_direct_reply"] = True
                            flags_now["suppress_writer"] = True
                            # State.flags는 Dict/Flags 타입 요구 → plain dict로 재대입
                            state["flags"] = dict(flags_now)
                    else:
                        # 본문 생성 실패: qa_direct_reply는 "완료" 의미이므로 절대 True로 두지 않는다.
                        # communicator 폴백을 태우되, 완료 플래그 없이 진행한다.
                        flags_now = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
                        # 안전상 잔존값 제거(있을 수 있음)
                        if flags_now.get("qa_direct_reply") is True:
                            flags_now["qa_direct_reply"] = False
                        state["flags"] = dict(flags_now)

                    # communicator 스케줄(중복 예약 방지)
                    if not has_pending(tasks, "communicator"):
                        tasks.append(
                            Task(
                                agent="communicator",
                                done=False,
                                description="스모크 매치: 최상위 문서 임계 초과 → Direct QA 전달",
                                done_at=""
                            )
                        )
                    logger.info(
                        "[vector_search][smoke→communicator] q=%r | url=%s | score=%.3f (min=%.3f) | answered=%s",
                        best_q, _ell(_doc_url(best_doc), 96), best_sc, _MIN, bool(reply_text)
                    )
                    pending.done = True; pending.done_at = _now_str()
                    return {
                        "messages": messages,
                        "task_history": tasks,
                        "references": references,
                        "qa_direct_reply": bool(reply_text),
                        "next_agent": "communicator",
                    }


    # Local ingest on-demand (optional)
    try:
        ensure_local = _cfg_bool("SKIP_WEB_SEARCH", False)
        local_globs_env = _cfg_str("LOCAL_RAG_GLOBS", "")
        need_local = ensure_local and bool(local_globs_env.strip())
        not_yet = not state.get("local_ingested_once")
        if need_local and not_yet:
            slug = topic_slug
            import re as _re
            raw_globs = [g.strip() for g in _re.split(r"[|;, \n]+", local_globs_env) if g.strip()]

            def _norm(p: str) -> str:
                p = p.replace("<topic-slug>", slug or "**")
                return p.replace("\\", os.sep).replace("/", os.sep)

            dedup, seen = [], set()
            for g in (_norm(x) for x in raw_globs):
                k = g.lower() if os.name == "nt" else g
                if k in seen: continue
                seen.add(k); dedup.append(g)

            if dedup:
                logger.info("[VECTOR SEARCH AGENT] on-demand local ingest: %s", dedup)
                l_jsons, l_docs, l_chunks = ingest_local_files(
                    dedup, namespace=((getattr(config.CFG, "CHROMA_NAMESPACE_LOCAL", "") or ns)),
                    persist_directory=_default_chroma_dir(getattr(config.CFG, "CHROMA_NAMESPACE_LOCAL", "") or ns),
                    topic_slug=slug, root_dir=str(current_path),
                    add_web_pages_json_to_chroma=add_web_pages_json_to_chroma,
                    web_page_json_to_documents=web_page_json_to_documents,
                )
                if l_docs:
                    merged_dict = merge_refs(cast(dict[str, Any], references), [], l_docs)
                    # ✅ refs / references 동시 반영
                    cast(MutableMapping[str, Any], state)["refs"] = merged_dict
                    cast(MutableMapping[str, Any], state)["references"] = merged_dict
                    references = _to_refs(merged_dict)
                state["local_ingested_once"] = True
    except Exception as e:
        logger.warning("on-demand local ingest 실패: %s", e)

    ran_queries: set[str] = set()
    accum_queries: list[str] = []
    accum_docs: list[Any] = []

    def _extract_user_query(s: str) -> str:
        if not isinstance(s, str):
            return ""
        s = s.strip().strip(" \"'“”‘’`")
        s_l = s.lower()
        if s_l in {"research", "research:", "research;"} or s_l.startswith("research "):
            return ""
        if re.search(r"<\s*research\s*:\s*[^>]+>", s, re.I):
            return ""
        if re.search(r"(섹션|section|챕터|chapter).{0,10}(작성|집필|써|write)", s, re.I) or \
           re.search(r"(작성|집필)\s*해\s*줘", s) or \
           re.search(r"섹션을\s*작성", s):
            return ""
        s = re.sub(r"^write\s*:\s*", "", s, flags=re.I).strip()
        s = re.sub(r"(요약해줘|요약|정리해줘|정리)\s*[\.\!\?…]*\s*$", "", s).strip()
        s = re.sub(r"[\.\!\?…]+$", "", s).strip()
        m = re.search(r"[A-Za-z0-9_]{6,}", s)
        return (m.group(0) if m else s) if len(s) >= 2 else ""

    def _was_research_token(s: str) -> bool:
        if not isinstance(s, str):
            return False
        s_l = s.strip().lower()
        return (s_l == "research" or s_l.rstrip(":;") == "research" or s_l.startswith("research "))

    def _is_noise_query(q: str) -> bool:
        ql = (q or "").strip().lower()
        if ql.rstrip(":;") == "research":
            return True
        if not ql or ql in {"force_query","force_queries","force"} or len(ql) <= 2:
            return True
        return any(b in ql for b in ["gtm.js","function(","<meta","<script","@media","var ","cookieconsent","usercentrics"])

    # --- seed query 우선 적용 (planner/refs) ---
    plan_q = ((state.get("research_plan") or {}).get("queries") or [])[:1]
    refs_q = (state.get("references") or {}).get("queries") or []
    seed = plan_q or refs_q
    if seed:
        cast(MutableMapping[str, Any], state)["vector_seed_query"] = str(seed[0]).strip()

    # 연구 루프 판정
    def _looks_like_research_mode(st):
        role = (st.get("agent_role") or "").strip().lower()
        has_plan = bool((st.get("research_plan") or {}).get("queries"))
        pipeline_on = any((getattr(t, "done", True) is False)
                          and getattr(t, "agent", "") in ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")
                          for t in (st.get("task_history") or []))
        explicit = bool(st.get("research_loop_active"))
        return explicit or (role == "research analyst") or has_plan or pipeline_on

    last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
    forced_seed = bool(last_human and isinstance(last_human.content, str) and _was_research_token(last_human.content))
    # 연구 모드라도 DIRECT_QA=True면 user_q를 비우지 않는다(q='' 방지, research 흔들림 최소)
    _direct_qa_on = False
    try:
        _direct_qa_on = bool(getattr(config.CFG, "DIRECT_QA", False))
    except Exception:
        _direct_qa_on = False
    skip_direct_qa = _looks_like_research_mode(state) and (not _direct_qa_on)
    user_q = "" if skip_direct_qa else _extract_user_query(last_human.content) if (last_human and isinstance(last_human.content, str)) else ""
    user_q = _clean_seed(user_q)
    user_q_clean = _strip_web_filters(user_q)
    user_key = user_q_clean.strip().lower()

    # 유저 질의가 비고, 강제시드 허용 상태면 시드 사용
    if (not user_q_clean) and state.get("vector_seed_query") and (forced_seed or not bool(state.get("research_loop_active"))):
        user_q = str(state.get("vector_seed_query") or "").strip()
        user_q_clean = _strip_web_filters(user_q)
        user_key = user_q_clean.strip().lower()

    # ── (A) 콜드스타트 대비: 진입 직후 질의 저장 + 질문 변경 시 재시도키 리셋 ─────────────
    try:
        # flags/router는 복제 후 수정 → 다시 되돌려쓰기(타입 경고 회피)
        from typing import Mapping  # 상단 import에 이미 있으면 생략
        _flags: Dict[str, Any] = dict(cast(Mapping[str, Any] | None, state.get("flags")) or {})
        _router: Dict[str, Any] = dict(cast(Mapping[str, Any] | None, _flags.get("router")) or {})
        prev_q: str = (_flags.get("last_user_query") or "").strip()
        new_q: str = (user_q_clean or "").strip()
        if new_q:
            _flags["last_user_query"] = new_q
            if new_q != prev_q:
                _router["after_web_ws_retries"] = 0
        if _router:
            _flags["router"] = _router
        cast(MutableMapping[str, Any], state)["flags"] = _flags  # Flags(TypedDict) ← plain dict 재대입
    except Exception:
        pass


    if user_q_clean and (not _is_noise_query(user_q_clean)) and _ok_query(user_q_clean) and (user_key not in ran_queries):
        if _looks_like_local_glob(user_q_clean):
            logger.debug("[FILTER] skip local/glob query: %s", user_q_clean)
        else:
            retrieved_docs: list[Any] = []
            try:
                logger.debug("retrieve (dual) args: %s", {"query": user_q_clean, "top_k": TOP_K})
                retrieved_docs: list[Any] = _dual_retrieve(user_q_clean, top_k=TOP_K, ns_default=ns, persist_dir=persist_dir)

                src_cnt = Counter(
                    (getattr(d, "metadata", {}) or {}).get("_retrieved_src", "unknown")
                    for d in (retrieved_docs or [])
                )
                ns_cnt = Counter(
                    (getattr(d, "metadata", {}) or {}).get("_retrieved_ns", "unknown")
                    for d in (retrieved_docs or [])
                )

                logger.warning(
                    "[CHECK][dual-retrieve] src=%s | ns=%s",
                    dict(src_cnt),
                    dict(ns_cnt),
                )
            except Exception as e:
                logger.warning("retrieve 실패(user_q='%s' → '%s'): %s", user_q, user_q_clean, e)
                retrieved_docs = []

            retrieved_docs = _dedupe_docs(retrieved_docs)
            _log_retrieval(user_q_clean, retrieved_docs, tag="vector_search")
            accum_queries.append(user_q_clean); accum_docs.extend(retrieved_docs); ran_queries.add(user_key)

            merged_dict = merge_refs(cast(dict[str, Any], references), accum_queries, accum_docs)
            # ✅ refs / references 동시 반영
            cast(MutableMapping[str, Any], state)["refs"] = merged_dict
            cast(MutableMapping[str, Any], state)["references"] = merged_dict
            references = _to_refs(merged_dict)

            ALLOW_SUMMARY = _cfg_bool("ALLOW_LOCAL_SUMMARY", _cfg_bool("ALLOW_SUMMARY", False))

            def _has_writer_pending(_tasks):
                try:
                    return has_pending(_tasks, "section_writer", prefix="write:") or has_pending(_tasks, "chapter_writer", prefix="write:")
                except Exception:
                    return any(
                        (not getattr(t, "done", False))
                        and getattr(t, "agent", "") in ("section_writer", "chapter_writer")
                        and str(getattr(t, "description", "")).startswith("write:")
                        for t in (_tasks or [])
                    )

            # Flags(TypedDict) | dict → 항상 dict[str, Any]로 정규화
            from typing import Mapping  # (파일 상단에 이미 있으면 이 줄은 생략)
            flags_now2: Dict[str, Any] = dict(cast(Mapping[str, Any] | None, state.get("flags")) or {})
            if _has_writer_pending(tasks) and flags_now2.get("pending_write_title"):
                # writer 대기 시 직답 모드 사용하지 않음
                clear_qa(cast(MutableMapping[str, Any], state))
                logger.info("[vector_search] writer pending detected → skip Direct QA generation; hand off to writer.")
                pending.done = True; pending.done_at = _now_str()
                return {"messages": messages, "task_history": tasks, "references": references}

            if ALLOW_SUMMARY:
                if retrieved_docs:
                    ctx_parts = []
                    for d in (retrieved_docs or [])[:3]:
                        txt = (getattr(d, "page_content", "") or "").strip()
                        if txt: ctx_parts.append(txt[:1200])
                    context = "\n\n---\n\n".join(ctx_parts).strip()

                    if context:
                        try:
                            prompt = (
                                "다음 컨텍스트만 근거로 한국어로 1문단 요약을 작성하세요.\n"
                                f"질문: {user_q}\n\n컨텍스트:\n{context}\n\n"
                                "지시사항:\n- 컨텍스트 밖의 지식은 쓰지 말 것\n- 불확실하면 모른다고 말할 것\n- 1문단(3~5문장)으로 간결히"
                            )
                            resp = llm.invoke(prompt)
                            reply_text = getattr(resp, "content", str(resp))

                            flags_now = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
                            _writer_waiting = _has_writer_pending(tasks) and flags_now.get("pending_write_title")
                            if _writer_waiting:
                                # writer가 대기 중이면 직답 모드를 켜지 않음
                                clear_qa(cast(MutableMapping[str, Any], state))
                                logger.info("[vector_search] writer pending detected → skip qa_direct_reply; hand off to writer.")
                            else:
                                messages.append(
                                    AIMessage(
                                        content=reply_text,
                                        additional_kwargs={"qa_direct_reply": True, "role": "qa"},
                                    )
                                )
                                # ✅ 실제 답변 생성 성공 시점에만 직답 승격 (state.flags 세팅 포함)
                                mark_qa_answer_ready(cast(MutableMapping[str, Any], state), reply_text)
                                state["new_url_count"] = as_int(state, "new_url_count", 0)
                                state["new_url_count_round"] = as_int(state, "new_url_count_round", 0)
                                state["round_new_urls"] = as_int(state, "round_new_urls", 0)

                                flags_mm = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
                                has_writer_lock = bool(flags_mm.get("pending_write_title"))
                                has_writer_p = (
                                    has_pending(tasks, "section_writer", prefix="write:")
                                    or has_pending(tasks, "chapter_writer", prefix="write:")
                                )
                                if not (has_writer_lock and has_writer_p):
                                    if not has_pending(tasks, "communicator"):
                                        tasks.append(
                                            Task(
                                                agent="communicator",
                                                done=False,
                                                description="사용자 질의에 대한 요약 답변 전달",
                                                done_at=""
                                            )
                                        )
                                # ✅ Direct QA 성공 → router 힌트로 communicator 지정
                                cast(MutableMapping[str, Any], state)["next_agent"] = "communicator"
                            pending.done = True; pending.done_at = _now_str()
                            logger.info("[DIRECT QA] %s",
                                        "Summary generated and returning to communicator."
                                        if cast(MutableMapping[str, Any], state.get("flags", {})).get("qa_direct_reply") else
                                        "Writer pending; suppressed QA handoff (no communicator).")
                            return {"messages": messages, "task_history": tasks,
                                    "references": references,
                                    "qa_direct_reply": bool(cast(MutableMapping[str, Any], state.get("flags", {})).get("qa_direct_reply")),
                                    "next_agent": "communicator"}
                        except Exception as e:
                            logger.warning("QA 요약 생성 실패: %s", e)
                            # 요약 실패 → Direct QA 최소 응답 보장으로 즉시 커밋
                            clear_qa(cast(MutableMapping[str, Any], state))
                            _emit_min_qa(cast(MutableMapping[str, Any], state), references, messages, reason="summary_failed_min_qa")
                            pending.done = True; pending.done_at = _now_str()
                            if not has_pending(tasks, "communicator"):
                                tasks.append(Task(agent="communicator", done=False, description="Direct QA 최소 응답 전달", done_at=""))
                            return {
                                "messages": messages,
                                "task_history": tasks,
                                "references": references,
                                "qa_direct_reply": False,
                                "next_agent": "communicator",
                            }

            if not ALLOW_SUMMARY and _cfg_bool("AUTO_WRITE_DURING_RESEARCH", False):
                # 새 정본 schedule_writer_if_needed는 state와 reason만 받는다.
                schedule_writer_if_needed(
                    cast(MutableMapping[str, Any], state),
                    reason="auto_write_during_research_no_summary",
                )
            # 🔁 ALLOW_SUMMARY=0 이고 Direct QA 의도인데 답변을 못 만든 경우 → 최소 응답 보장
            try:
                _dq_on2 = bool(getattr(config.CFG, "DIRECT_QA", False))
            except Exception:
                _dq_on2 = False
            if _dq_on2 and not bool(cast(MutableMapping[str, Any], state.get("flags", {})).get("qa_direct_reply")):
                logger.warning("[vector_search] Direct QA produced no answer (ALLOW_SUMMARY=0) → MIN QA emit to communicator")
                _emit_min_qa(cast(MutableMapping[str, Any], state), references, messages, reason="no_summary_min_qa")
                pending.done = True; pending.done_at = _now_str()
                if not has_pending(tasks, "communicator"):
                    tasks.append(Task(agent="communicator", done=False, description="Direct QA 최소 응답 전달", done_at=""))
                return {
                    "messages": messages,
                    "task_history": tasks,
                    "references": references,
                    "qa_direct_reply": False,
                    "next_agent": "communicator",
                }
    else:
        logger.debug("[SKIP user] q='%s' empty=%s noise=%s ok=%s dup=%s",
                     user_q_clean, not bool(user_q_clean), _is_noise_query(user_q_clean),
                     _ok_query(user_q_clean), user_key in ran_queries)

    # 2) Preexisting and planned queries
    if not ran_queries:
        seed_list = [q for q in plan_qs if q] or [q for q in refs_qs if q]
        if seed_list:
            seed_raw = seed_list[0]
            seed_clean = _strip_web_filters(_clean_seed(seed_raw))
            seed_key = seed_clean.strip().lower()
            if seed_clean and (not _is_noise_query(seed_clean)) and _ok_query(seed_clean) and (not _looks_like_local_glob(seed_clean)):
                try:
                    logger.debug("retrieve (dual) args: %s", {"query_raw": seed_raw, "query_retrieval": seed_clean, "top_k": TOP_K})
                    retrieved_docs = _dual_retrieve(seed_clean, top_k=TOP_K, ns_default=ns, persist_dir=persist_dir)
                except Exception as e:
                    logger.warning("retrieve 실패(seed='%s' → '%s'): %s", seed_raw, seed_clean, e)
                    retrieved_docs = []

                retrieved_docs = _dedupe_docs(retrieved_docs)
                _log_retrieval(seed_clean, retrieved_docs, tag="vector_search")
                accum_queries.append(seed_clean); accum_docs.extend(retrieved_docs); ran_queries.add(seed_key)

                merged_dict = merge_refs(cast(dict[str, Any], references), accum_queries, accum_docs)
                # ✅ refs / references 동시 반영
                cast(MutableMapping[str, Any], state)["refs"] = merged_dict
                cast(MutableMapping[str, Any], state)["references"] = merged_dict
                references = _to_refs(merged_dict)

                flags = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
                flags["last_user_query"] = seed_raw

    inputs = {
        "mission": mission,
        "references": references,
        "messages": messages,
        "outline": outline_text,
        "topic_title": state.get("topic_title") or state.get("topic") or "(untitled)",
    }
    llm_with_retriever = llm.bind_tools([retrieve])
    search_plans = (vector_search_system_prompt | llm_with_retriever).invoke(inputs)
    preexisting_queries = list(references.get("queries", []))

    for raw in preexisting_queries:
        q = _clean_seed(raw); q_for_retrieve = _strip_web_filters(q); key = q_for_retrieve.strip().lower()
        if _looks_like_local_glob(q_for_retrieve): continue
        if (not q_for_retrieve) or _is_noise_query(q_for_retrieve) or (not _ok_query(q_for_retrieve)) or (key in ran_queries):
            continue
        try:
            retrieved_docs = _dual_retrieve(q_for_retrieve, top_k=TOP_K, ns_default=ns, persist_dir=persist_dir)
        except Exception as e:
            logger.warning("retrieve 실패(query='%s' → '%s'): %s", q, q_for_retrieve, e); continue
        retrieved_docs = _dedupe_docs(retrieved_docs)
        _log_retrieval(q_for_retrieve, retrieved_docs, tag="vector_search")
        accum_queries.append(q_for_retrieve); accum_docs.extend(retrieved_docs); ran_queries.add(key)

    for args in iter_tool_calls(search_plans, "retrieve"):
        # tool 호출 인자가 문자열/JSON 문자열/딕셔너리 등 다양할 수 있어 방어적으로 정규화
        if isinstance(args, str):
            try:
                args = _json.loads(args)
            except Exception:
                args = {"query": str(args)}
        elif not isinstance(args, dict):
            logger.debug(
                "retrieve tool args ignored (unsupported type): %r",
                type(args).__name__,
            )
            continue

        raw_q = args.get("query")
        # 🔒 LLM이 ["q1", "q2"] 같은 리스트로 넘기는 경우 방어
        if isinstance(raw_q, (list, tuple)):
            raw_q = " ".join(str(x) for x in raw_q if x)
        elif not isinstance(raw_q, str):
            raw_q = "" if raw_q is None else str(raw_q)

        query = _clean_seed(raw_q or "")
        q_for_retrieve = _strip_web_filters(query)
        key = q_for_retrieve.strip().lower()
        if _looks_like_local_glob(q_for_retrieve): continue
        if (not q_for_retrieve) or _is_noise_query(q_for_retrieve) or (not _ok_query(q_for_retrieve)) or (key in ran_queries):
            continue
        try:
            retrieved_docs = _dual_retrieve(q_for_retrieve, top_k=TOP_K, ns_default=ns, persist_dir=persist_dir)
        except Exception as e:
            logger.warning("retrieve 실패(query='%s' → '%s'): %s", query, q_for_retrieve, e); continue
        retrieved_docs = _dedupe_docs(retrieved_docs)
        _log_retrieval(q_for_retrieve, retrieved_docs, tag="vector_search")
        accum_queries.append(q_for_retrieve); accum_docs.extend(retrieved_docs); ran_queries.add(key)

    accum_docs = _dedupe_docs(accum_docs)
    merged_dict = merge_refs(cast(dict[str, Any], references), accum_queries, accum_docs)
    # ✅ refs / references 동시 반영 (최종 병합도 동일 규칙 적용)
    cast(MutableMapping[str, Any], state)["refs"] = merged_dict
    cast(MutableMapping[str, Any], state)["references"] = merged_dict
    references = _to_refs(merged_dict)

    if _cfg_bool("AUTO_WRITE_DURING_RESEARCH", False):
        schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            reason="auto_write_during_research_mid",
        )

    # facts_ctx (optional)
    try:
        snips = []
        for d in (references.get("docs") or [])[:20]:
            txt = (getattr(d, "page_content", "") or "")
            lines = [ln.strip() for ln in txt.splitlines()
                     if re.search(r"(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:%|조|억|만대|GWh|kWh|원|달러|bn|trn)\b", ln)]
            for ln in lines[:2]:
                snips.append(ln[:300])
            if len(snips) >= 5: break
        state["facts_ctx"] = "\n".join(snips[:5])
    except Exception:
        state["facts_ctx"] = ""

    try:
        _log_retrieval(f"(summary) total {len(accum_queries)} queries", references["docs"], tag="vector_search")
    except Exception:
        pass

    pending.done = True; pending.done_at = _now_str()

    role = (state.get("agent_role") or "").strip().lower()
    rounds_done = as_int(state, "research_round", 0)
    max_iter = as_int(state, "iteration_count", 0)

    def _has_research_pipeline(tsk_list) -> bool:
        return any((getattr(t, "done", True) is False)
                   and getattr(t, "agent", "") in ("research_planner","web_search_agent","vector_search_agent","research_synthesizer")
                   for t in (tsk_list or []))

    explicit_flag = state.get("research_loop_active")
    if isinstance(explicit_flag, bool):
        research_loop_active = explicit_flag
    else:
        has_objective = bool(state.get("research_objectives"))
        has_plan = bool((state.get("research_plan") or {}).get("objective"))
        pipeline_on = _has_research_pipeline(tasks)
        research_loop_active = (role == "research analyst") and (max_iter > 0) and (rounds_done < max_iter) and (has_objective or has_plan or pipeline_on)

    writer_agent = getattr(config.CFG, "WRITER_AGENT", "section_writer")
    AUTO_WRITE_DURING_RESEARCH = _cfg_bool("AUTO_WRITE_DURING_RESEARCH", False)
 

    logger.debug("[writer_guard] %s", {
        "DOC_MODE": getattr(config.CFG, "DOC_MODE", "report"),
        "WRITER_AGENT": writer_agent,
        "AUTO_WRITE_AFTER_RAG": _cfg_bool("AUTO_WRITE_AFTER_RAG", True),
        "AUTO_WRITE_DURING_RESEARCH": AUTO_WRITE_DURING_RESEARCH,
        "research_loop_active": research_loop_active,
        "has_writer_pending": has_pending(tasks, writer_agent, prefix="write:"),
        "agent_role": state.get("agent_role"),
        "iteration_count": state.get("iteration_count"),
        "research_round": state.get("research_round"),
    })

    if research_loop_active:
        logger.info("[HANDOFF] scheduling research_synthesizer (research_loop_active=True)")
        try:
            round_new = None
            for k in ("new_url_count_round", "round_added_urls", "round_new_urls", "new_urls", "new_url_count"):
                v = state.get(k)
                if v is not None and str(v).strip() != "":
                    round_new = max(0, int(str(v))); break
            if round_new is not None:
                state["new_url_count"] = round_new
                state["new_url_count_round"] = round_new
                state["round_new_urls"] = round_new
        except Exception:
            pass

        if not has_pending(tasks, "research_synthesizer"):
            tasks.append(Task(agent="research_synthesizer", done=False, description="synthesize:auto", done_at=""))

        messages.append(AIMessage(content="[VECTOR SEARCH AGENT] 연구 라운드 진행 중 → 합성 단계(Research Synthesizer)로 이동"))
        return {"messages": messages, "task_history": tasks, "references": references}

    writer_task_scheduled = False
    if (not research_loop_active) or AUTO_WRITE_DURING_RESEARCH:
        # 새 schedule_writer_if_needed는 반환값이 없고
        # state.flags.router.writer_pending 플래그만 세팅한다.
        schedule_writer_if_needed(
            cast(MutableMapping[str, Any], state),
            reason="vector_search_final",
        )

        flags_mm2 = cast(MutableMapping[str, Any], state.setdefault("flags", {}))
        router_flags2 = dict(flags_mm2.get("router") or {})
        writer_task_scheduled = bool(router_flags2.get("writer_pending"))
        flags_mm2["router"] = router_flags2

        has_writer_p = (
            has_pending(tasks, "section_writer", prefix="write:")
            or has_pending(tasks, "chapter_writer", prefix="write:")
        )

        if has_writer_p:
            flags_mm2["qa_direct_reply"] = False
            # 직답 의도가 남아있다면 여기서도 소거(옵션)
            if flags_mm2.get("direct_qa_intent"):
                flags_mm2.pop("direct_qa_intent", None)

        if (not writer_task_scheduled) and (not has_writer_p):
            if not has_pending(tasks, "communicator"):
                tasks.append(
                    Task(
                        agent="communicator",
                        done=False,
                        description="검색/인덱싱 완료 보고 및 다음 집필 대상 확인",
                        done_at=""
                    )
                )

        return {"messages": messages, "task_history": tasks, "references": references}
    
# (모듈 하단의 정적 상수는 제거하여 reload_config() 이후에도 값이 반영되도록 함)
