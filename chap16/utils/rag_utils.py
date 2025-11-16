# utils/rag_utils.py — dynamic config access (v2025-10-27)
from __future__ import annotations

from typing import Mapping, Any, List, Sequence, Dict, Optional, cast, TypedDict, MutableMapping, Callable
from langchain_core.documents import Document
import re, hashlib
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
import os

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Dynamic config (avoid static binding to CFG values at import)
# ─────────────────────────────────────────────────────────────
import core.config as config

# ── refs 프리뷰 함수 로드(안전) + 어댑터 ──────────────────────────
# 내부 핸들: 어떤 시그니처든 수용하기 위해 가변 Callable로 보관
_refs_preview_handler: Callable[..., str]
try:
    # utils.refs의 정식 구현: (state, max_q=..., max_docs=..., snippet_len=...)
    from utils.refs import refs_preview_text as _rp
    _refs_preview_handler = cast(Callable[..., str], _rp)
except Exception:
    # 폴백: 정식 시그니처(state, ...)를 따르는 간단 구현
    def _refs_preview_fallback(state: Mapping[str, Any], max_q: int = 5, max_docs: int = 8, snippet_len: int = 350) -> str:
        refs = dict(state or {}).get("references", {}) or {}
        qs = list(cast(List[str], refs.get("queries") or []))[:max_q]
        docs = list(cast(List[Any], refs.get("docs") or []))[:max_docs]
        lines: List[str] = []
        for d in docs:
            try:
                if isinstance(d, Document):
                    meta = d.metadata or {}
                    title = meta.get("title") or meta.get("source") or "(untitled)"
                    url = meta.get("source") or meta.get("url") or ""
                elif isinstance(d, dict):
                    meta = d.get("metadata") or {}
                    title = meta.get("title") or d.get("source") or "(untitled)"
                    url = meta.get("source") or d.get("url") or d.get("path") or ""
                else:
                    meta = getattr(d, "metadata", {}) or {}
                    title = meta.get("title") or getattr(d, "source", "") or "(untitled)"
                    url = meta.get("source") or getattr(d, "url", "") or ""
                lines.append(f"- {str(title).strip() or '(untitled)'} ({url})")
            except Exception:
                lines.append("- (doc)")
        q_block = "\n".join(f"- {q}" for q in qs) if qs else "(none)"
        d_block = ("\n\nDocs:\n" + "\n".join(lines)) if lines else ""
        return "Queries:\n" + q_block + d_block
    _refs_preview_handler = cast(Callable[..., str], _refs_preview_fallback)
# 외부 공개 API(일관 시그니처): (refs, limit) → 내부 핸들 호출
def refs_preview_text(refs: Mapping[str, Any], limit: int = 3) -> str:
    """
    통합 어댑터:
    - 인자로 refs(dict: {"queries":[], "docs":[]})를 받는다.
    - 내부 구현이 (state, ...) 시그니처면 state={"references": refs}로 래핑하여 max_docs=limit로 전달.
    - 혹시 (refs, limit) 시그니처 구현이 남아있다면 TypeError 분기에서 안전 호출.
    """
    try:
        state = {"references": refs}
        return _refs_preview_handler(state, max_docs=int(limit))
    except TypeError:
        # 구현이 (refs, limit) 형태인 구버전 헬퍼 대응
        fn = cast(Callable[[Mapping[str, Any], int], str], _refs_preview_handler)
        return fn(refs, int(limit))

# 외부에서 import * 시 노출 대상
# (Direct QA 관련 심볼을 함께 노출)
__all__ = [
    "refs_preview_text",
    "merge_refs",
    "score_doc",
    "vector_count",
    "is_qa_like",
    "set_direct_qa_flag",
    "mark_qa_answer_ready",
    "clear_qa",
]

# (주의) 더 이상 핸들을 직접 재바인딩하지 않음. 어댑터 함수명을 그대로 export.
# ─────────────────────────────────────────────────────────────
# Config helpers & defaults (per-call read; no module-level cache)
# ─────────────────────────────────────────────────────────────

def _get_cfg_attr(name: str, default):
    """config.CFG.<name> → config.<name> 순으로 조회."""
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default

def _as_list(v: Any, *, lower: bool = False) -> List[str]:
    try:
        seq = list(v or [])
    except Exception:
        return []
    out: List[str] = []
    for x in seq:
        s = str(x).strip()
        if not s:
            continue
        out.append(s.lower() if lower else s)
    return out

# ── per-call getters (reload_config() 즉시 반영) ─────────────────
def _sig_head_chars() -> int:
    try:
        return int(_get_cfg_attr("DOC_SIGNATURE_HEAD_CHARS", 500) or 500)
    except Exception:
        return 500

def _gov_edu_bonus() -> float:
    try:
        return float(_get_cfg_attr("SCORE_GOV_EDU_BONUS", 3.0) or 3.0)
    except Exception:
        return 3.0

def _ifi_bonus() -> float:
    try:
        return float(_get_cfg_attr("SCORE_IFI_BONUS", 2.0) or 2.0)
    except Exception:
        return 2.0

def _consult_bonus() -> float:
    try:
        return float(_get_cfg_attr("SCORE_CONSULT_BONUS", 1.5) or 1.5)
    except Exception:
        return 1.5

def _recency_window_years() -> int:
    try:
        return int(_get_cfg_attr("RECENCY_WINDOW_YEARS", 6) or 6)
    except Exception:
        return 6

def _recency_weight() -> float:
    try:
        return float(_get_cfg_attr("RECENCY_WEIGHT", 0.2) or 0.2)
    except Exception:
        return 0.2

def _bot_penalty() -> float:
    try:
        return float(_get_cfg_attr("SCORE_BOTPAGE_PENALTY", 2.0) or 2.0)
    except Exception:
        return 2.0

def _ifi_domains() -> List[str]:
    # 하드코어 디폴트 + CFG 추가 목록(소문자 비교)
    base = ["imf.org", "kostat.go", "kotra.or"]
    return list({*base, *(_as_list(_get_cfg_attr("SCORE_IFI_DOMAINS", []), lower=True))})

def _consult_domains() -> List[str]:
    base = ["kpmg", "mckinsey", "gartner", "idc"]
    return list({*base, *(_as_list(_get_cfg_attr("SCORE_CONSULT_DOMAINS", []), lower=True))})

def _bot_terms() -> List[str]:
    base = ["enable javascript", "captcha", "access denied", "just a moment"]
    return list({*base, *(_as_list(_get_cfg_attr("SCORE_BOT_TERMS", []), lower=True))})

def _merge_refs_max_queries() -> int:
    try:
        return int(_get_cfg_attr("MERGE_REFS_MAX_QUERIES", 0) or 0)
    except Exception:
        return 0

def _merge_refs_max_docs() -> int:
    try:
        return int(_get_cfg_attr("MERGE_REFS_MAX_DOCS", 0) or 0)
    except Exception:
        return 0

# ─────────────────────────────────────────────────────────────
# Refs 타입(문서화/정적체커 친화)
# ─────────────────────────────────────────────────────────────
class Refs(TypedDict, total=False):
    queries: List[str]
    docs: List[Any]
    # 필요한 경우 확장 키 허용(예: 'meta')


# ─────────────────────────────────────────────────────────────
# 내부 유틸
# ─────────────────────────────────────────────────────────────

def _norm_url_for_key(u: str) -> str:
    """
    refs dedupe용 URL 정규화:
    - 소문자 스킴/호스트, 기본포트 제거(:80/:443)
    - http(s): fragment 제거(조각은 동일 문서로 간주)
    - file://: fragment/쿼리 보존(슬라이드/페이지 조각 구분을 위해)
    - 그 외 스킴: 원형 최대 보존(소문자화만)
    """
    try:
        s = (u or "").strip()
        if not s:
            return ""
        p = urlparse(s)
        scheme = (p.scheme or "").lower()
        netloc = (p.netloc or "").lower()
        if netloc.endswith(":80"):
            netloc = netloc[:-3]
        if netloc.endswith(":443"):
            netloc = netloc[:-4]
        path  = p.path or ""
        query = p.query or ""
        frag  = p.fragment or ""
        if scheme == "file":
            # 조각/쿼리 유지(분할 파트 보존)
            out = f"{scheme}://{netloc}{path}"
            if query:
                out += f"?{query}"
            if frag:
                out += f"#{frag}"
            return out
        if scheme in ("http", "https"):
            # fragment 제거
            return f"{scheme}://{netloc}{path}" + (f"?{query}" if query else "")
        # 기타 스킴: 가능한 한 보존
        return f"{scheme}://{netloc}{path}" + (f"?{query}" if query else "") + (f"#{frag}" if frag else "")
    except Exception:
        return (u or "").strip().lower()


def _doc_key_from_any(d: Any) -> str:
    """
    문서 고유키(확장):
      • normalized_url(_norm_url_for_key)
      • + 원본 source 메타(가능 시)
      • + (part|page|fragment) 메타(있으면)
    - URL이 전혀 없으면 빈 문자열 → 상위에서 시그니처 폴백
    """
    try:
        if isinstance(d, Document):
            meta = d.metadata or {}
            # url 후보와 별도의 source 원문을 분리 취득
            url_raw = (meta.get("url") or meta.get("source") or "").strip()
            src_raw = (meta.get("source") or "").strip()
            part = (meta.get("part") or meta.get("page") or meta.get("fragment") or "").strip()
        elif isinstance(d, dict):
            meta = d.get("metadata") or {}
            url_raw = (meta.get("url") or meta.get("source") or d.get("url") or d.get("source") or "").strip()
            src_raw = (meta.get("source") or d.get("source") or "").strip()
            part = (
                meta.get("part") or meta.get("page") or meta.get("fragment")
                or d.get("part") or d.get("page") or d.get("fragment") or ""
            )
            part = str(part).strip()
        else:
            meta = getattr(d, "metadata", {}) or {}
            url_raw = (meta.get("url") or meta.get("source") or "").strip()
            src_raw = (meta.get("source") or "").strip()
            part = (meta.get("part") or meta.get("page") or meta.get("fragment") or "").strip()
    except Exception:
        url_raw, src_raw, part = "", "", ""

    if not url_raw and not src_raw:
        return ""
    norm_url = _norm_url_for_key(url_raw or src_raw)
    src_key  = (src_raw or "").strip().lower()
    # 기본 조합: 정규화 URL + source 원문(있을 때)
    base = f"{norm_url}|src:{src_key}" if src_key else norm_url
    part_key = (part or "").strip().lower()
    return f"{base}##{part_key}" if part_key else base


def _coerce_docs_list(objs: Optional[Sequence[Any]]) -> List[Any]:
    """docs 입력(Sequence|None)을 안전하게 list로 강제."""
    if objs is None:
        return []
    # 이미 시퀀스면 그대로 리스트화
    try:
        return list(objs)
    except Exception:
        # objs가 어떤 타입이든 Any로 처리해 1-요소 리스트로 감싼다
        return [cast(Any, objs)]
    
def _norm_queries(seq: Sequence[str] | None) -> List[str]:
    if not seq:
        return []
    out: List[str] = []
    for q in seq:
        if not isinstance(q, str):
            continue
        qq = q.strip()
        if qq:
            out.append(qq)
    return out

def _dedupe_preserve_order_str(items: Sequence[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for it in items:
        key = it.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _signature_for_doc_like(d: Any) -> str:
    """
    문서 중복 판정용 시그니처.
    - 기존 방식(폴백): source(URL) + 내용 앞부분(공백 정규화 후 N자; N=DOC_SIGNATURE_HEAD_CHARS)
    - Document/딕셔너리/임의 객체 모두 수용
    """
    try:
        if isinstance(d, Document):
            pc = (d.page_content or "")
            meta = d.metadata or {}
        elif isinstance(d, dict):
            pc = (d.get("page_content") or d.get("content") or "") or ""
            meta = d.get("metadata") or {}
        else:
            pc = getattr(d, "page_content", "") or ""
            meta = getattr(d, "metadata", {}) or {}

        pc_head = " ".join(str(pc).split())[:_sig_head_chars()]
        src = (meta.get("source") or meta.get("url") or "").strip()
        base = f"{src}|{pc_head}"
    except Exception as e:
        base = repr(d)[:200]
        logger.debug("Doc signature fallback used: %s", e)

    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()


#─────────────────────────────────────────────────────────────
# 공개 함수
# ─────────────────────────────────────────────────────────────

def merge_refs(
    existing: Mapping[str, Any] | None,
    new_queries: Sequence[str] | None,
    new_docs: Sequence[Any] | None,
    *,
    preserve_extra: bool = True,
    limit_queries: Optional[int] = None,
    limit_docs: Optional[int] = None,
    sort_docs_by_score: bool = False,
) -> Refs:
    """
    references 병합(불변): 입력을 절대 수정하지 않고 새로운 dict(List 포함)를 반환.
    - preserve_extra=True: existing의 기타 키(meta 등)를 그대로 보존
    - limit_*: 상한 적용(CFG.MERGE_REFS_MAX_QUERIES / CFG.MERGE_REFS_MAX_DOCS 기본값 사용)
    - sort_docs_by_score=True: score_doc 기준 내림차순 정렬 후 상한 적용
    """
    # CFG 기반 상한 기본값(동적)
    if limit_queries is None:
        limit_queries = _merge_refs_max_queries()
    if limit_docs is None:
        limit_docs = _merge_refs_max_docs()

    base: Dict[str, Any] = dict(existing or {})  # shallow copy(입력 보호)
    base_q = _norm_queries(cast(Sequence[str] | None, base.get("queries")))
    base_d = _coerce_docs_list(cast(Sequence[Any] | None, base.get("docs")))

    add_q = _norm_queries(new_queries)
    add_d = _coerce_docs_list(new_docs)

    # 1) 쿼리: 기존→신규 순서 유지+디듀프(대소문자 무시)
    merged_q = _dedupe_preserve_order_str([*base_q, *add_q])
    if limit_queries and limit_queries > 0:
        merged_q = merged_q[:limit_queries]

    # 2) 문서: URL(+part/page/fragment) 기반 우선 디듀프 → 키 없을 때만 시그니처 폴백
    seen_keys: set[str] = set()
    dedup_docs: List[Any] = []
    for d in [*base_d, *add_d]:
        if d is None:
            continue
        key = _doc_key_from_any(d)
        if not key:
            # URL이 없다면 내용 기반 시그니처로 폴백
            try:
                key = "sig:" + _signature_for_doc_like(d)
            except Exception as e:
                key = "repr:" + repr(d)[:120]
                logger.debug("Doc signature build failed; using repr: %s", e)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        dedup_docs.append(d)

    # 3) (옵션) 점수 정렬
    docs_out = dedup_docs
    if sort_docs_by_score:
        try:
            docs_out = sorted(
                dedup_docs,
                key=lambda x: score_doc(x) if isinstance(x, Document) else 0.0,
                reverse=True,
            )
        except Exception:
            # 안전 폴백: 정렬 실패 시 원래 순서 유지
            docs_out = dedup_docs

    if limit_docs and limit_docs > 0:
        docs_out = docs_out[:limit_docs]

    # 4) 순수 새 객체 구성(입력 불변 보장)
    # TypedDict에 동적 키 대입은 금지되므로, 우선 일반 dict로 구성 후 마지막에 cast
    out_dict: Dict[str, Any] = {"queries": list(merged_q), "docs": list(docs_out)}
    if preserve_extra:
        # 나머지 키(meta 등)는 얕은 복사로 보존(참조 공유 허용)
        for k, v in base.items():
            if k not in ("queries", "docs"):
                out_dict[k] = v  # 그대로 보존

    logger.debug(
        "merge_refs(pure): queries %d→%d, docs %d→%d (sorted=%s, cap_q=%s, cap_d=%s)",
        len(base_q) + len(add_q), len(out_dict["queries"]),
        len(base_d) + len(add_d), len(out_dict["docs"]),
        sort_docs_by_score, limit_queries, limit_docs,
    )
    return cast(Refs, out_dict)


def score_doc(d: Document, year_now: int | None = None) -> float:
    """
    간단 점수 함수(정렬용):
    - .gov/.go.kr/.edu/.ac.kr 가산 (SCORE_GOV_EDU_BONUS)
    - 공공/국제/컨설팅 일부 도메인 가산 (SCORE_IFI_DOMAINS, SCORE_CONSULT_DOMAINS)
    - URL/본문 내 연도(20xx) → 최신일수록 가산 (RECENCY_WINDOW_YEARS, RECENCY_WEIGHT)
    - 차단/봇 페이지 패턴 감점 (SCORE_BOT_TERMS, SCORE_BOTPAGE_PENALTY)
    """
    if year_now is None:
        year_now = datetime.now().year

    meta = getattr(d, "metadata", {}) or {}
    src  = (meta.get("source") or meta.get("url") or "").strip().lower()
    text = (getattr(d, "page_content", "") or "")

    def _norm_domain(url: str) -> str:
        if not url:
            return ""
        try:
            netloc = urlparse(url).netloc or urlparse("http://" + url).netloc
        except Exception:
            return ""
        netloc = netloc.split("@")[-1].split(":")[0]
        for pref in ("www.", "m.", "mobile."):
            if netloc.startswith(pref):
                netloc = netloc[len(pref):]
        return netloc

    domain = _norm_domain(src)
    score = 0.0

    gov_edu = (
        domain.endswith(".go.kr") or domain.endswith(".gov")
        or domain.endswith(".ac.kr") or domain.endswith(".edu")
    )
    if gov_edu:
        score += _gov_edu_bonus()

    if any(k in domain for k in _ifi_domains()):
        score += _ifi_bonus()
    if any(k in domain for k in _consult_domains()):
        score += _consult_bonus()

    m = re.search(r"\b(20\d{2})\b", src) or re.search(r"\b(20\d{2})\b", text)
    if m:
        yr = int(m.group(1))
        recency = max(0, _recency_window_years() - (year_now - yr))
        score += recency * _recency_weight()

    lt = text.lower()
    if any(b in lt for b in _bot_terms()):
        score -= _bot_penalty()

    return score


def vector_count(collection_name: str, persist_directory: str | os.PathLike[str] | None) -> int:
    """
    현재 Chroma persistent 디렉터리에서 collection_name 컬렉션의 문서(아이템) 개수를 반환.
    - 컬렉션이 없으면 0
    - 오류 시 -1
    """
    try:
        if not persist_directory:
            logger.debug("vector_count: persist_directory is None/empty.")
            return -1

        p = str(Path(persist_directory))
        if not p:
            return -1

        import chromadb  # 선택적 의존성, 런타임 임포트
        client = chromadb.PersistentClient(path=p)
        try:
            try:
                col = client.get_collection(collection_name)  # 존재 안 하면 예외
            except Exception:
                return 0
            return int(col.count())
        finally:
            # 가능한 경우 클라이언트 정리
            for meth in ("close", "shutdown", "persist", "teardown", "reset", "stop"):
                fn = getattr(client, meth, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
    except Exception as e:
        logger.debug("vector_count failed: %s: %s", type(e).__name__, e)
        return -1

# ─────────────────────────────────────────────────────────────
# (옵션) 캐시 무효화 훅 — 현재 구현은 per-call 조회이므로 no-op
# ─────────────────────────────────────────────────────────────
def refresh_rag_utils() -> None:  # pragma: no cover
    """향후 lru_cache 최적화 시 캐시 무효화를 위해 호출 가능.
    현재 버전은 per-call 조회로 즉시 반영되므로 동작 없음."""
    return


# ─────────────────────────────────────────────────────────────
# Direct QA 헬퍼 (의향/실답 분리)
#  - is_qa_like(text): 질문이 단문·사실질문(정의/성분/가격 등)인지 판별
#  - set_direct_qa_flag(state, text): **의향만** 기록 (flags["qa_intent"])
#    * 트리거 조건
#       1) CFG.DIRECT_QA 또는 ENV:DIRECT_QA=1
#       2) (CFG.SKIP_WEB_SEARCH 또는 ENV:SKIP_WEB_SEARCH=1) 이면서 is_qa_like(text)=True
#    * 효과: flags["qa_intent"]=True 만 설정
#           (여기서는 qa_direct_reply를 절대 올리지 않음)
#  - mark_qa_answer_ready(state, text): 실제 답 생성 직후 호출 → qa_reply 저장 + qa_direct_reply=True
#  - clear_qa(state): 폴백/실패 시 의향/실답 플래그/값 정리
# ─────────────────────────────────────────────────────────────
def _truthy(v: Any, *, default: bool = False) -> bool:
    try:
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
        return default
    except Exception:
        return default

def _get_bool(name: str, env_name: Optional[str] = None, default: bool = False) -> bool:
    # CFG 우선 → 모듈 속성 → ENV 폴백
    val = _get_cfg_attr(name, None)
    if val is not None:
        return _truthy(val, default=default)
    if hasattr(config, name):
        return _truthy(getattr(config, name), default=default)
    envv = os.getenv(env_name or name)
    return _truthy(envv, default=default)

def is_qa_like(text: str) -> bool:
    """
    단문·사실확인형 QA 여부를 가볍게 판별.
    - 예: '주성분', '정의', '가격', '효능', '용량', '누가/언제/어디'
    - 연구 모드 유발(분석/평가/시사점 등) 키워드가 있으면 False
    """
    t = (text or "").strip()
    if not t:
        return False
    # 연구/서술형 배제 토큰
    if re.search(r"(연구|분석|평가|시사점|전망|트렌드)", t):
        return False
    # 짧은 의문문은 QA로 가정
    if len(t) <= 30 and (t.endswith("?") or re.search(r"(은\?|는\?|이\?|가\?)$", t)):
        return True
    # 사실질문 키워드
    QA_KEYWORDS = (
        "무엇","누구","언제","어디","정의","뜻","성분","주성분",
        "가격","용량","효능","효과","원인","해결","방법","사용법"
    )
    if any(k in t for k in QA_KEYWORDS):
        return True
    return False

def set_direct_qa_flag(state: MutableMapping[str, Any], user_text: str, *, force: Optional[bool] = None) -> None:
    """
    Direct QA 의향만 기록합니다.
    - flags['qa_intent'] = True/False
    - 여기서는 qa_direct_reply를 절대 건드리지 않습니다.
    """
    try:
        flags = state.setdefault("flags", {})
        if force is None:
            force = _get_bool("DIRECT_QA", "DIRECT_QA", default=False)
        skip_web = _get_bool("SKIP_WEB_SEARCH", "SKIP_WEB_SEARCH", default=False)
        intent = bool(force) or (skip_web and is_qa_like(user_text))
        # 의향만 세팅
        flags["qa_intent"] = bool(intent)
        state["flags"] = flags
        # (선택) 최근 사용자 질문 저장
        try:
            state["last_user_query"] = user_text
        except Exception:
            pass
    except Exception:
        # 방어적 무시
        return

def mark_qa_answer_ready(state: MutableMapping[str, Any], text: Optional[str]) -> None:
    """
    실제 답 생성 직후 호출:
    - state['qa_reply'] 저장
    - flags['qa_direct_reply']=True 로 승격 (의향→실답)
    """
    try:
        reply = (text or "").strip()
        flags = state.setdefault("flags", {})
        if reply:
            state["qa_reply"] = reply
            flags["qa_direct_reply"] = True
        else:
            # 빈 텍스트면 승격하지 않음
            flags["qa_direct_reply"] = False
        state["flags"] = flags
    except Exception:
        return

def clear_qa(state: MutableMapping[str, Any]) -> None:
    """
    폴백/실패/루프 종료 시 사용:
    - qa_reply 제거
    - qa_direct_reply / qa_intent 내려서 정리
    """
    try:
        flags = state.setdefault("flags", {})
        flags["qa_direct_reply"] = False
        flags["qa_intent"] = False
        state["flags"] = flags
        if "qa_reply" in state:
            try:
                del state["qa_reply"]
            except Exception:
                pass
    except Exception:
        return

# (참고) __all__은 파일 상단에서 이미 선언함


# ─────────────────────────────────────────────────────────────
# Direct QA 허용 여부 판별(경량 가드)
#  - 연구 라운드/연구 모드 활성 시: 차단
#  - writer 예약/잠금 상태 시: 차단
#  - suppress_vector_qa 플래그 시: 차단
#  - 그 외: 허용
#  반환: True(허용) / False(차단)
# ─────────────────────────────────────────────────────────────
from typing import Iterable

def _bool(v: Any) -> bool:
    try:
        return bool(v)
    except Exception:
        return False

def _get_flag(st: Mapping[str, Any], name: str, default: bool = False) -> bool:
    try:
        f = st.get("flags") or {}
        return _bool(f.get(name, default))
    except Exception:
        return default

def _has_pending_writer(tasks: Iterable[Any]) -> bool:
    try:
        for t in (tasks or []):
            # 객체/딕셔너리 모두 지원
            done = getattr(t, "done", None)
            if done is None and isinstance(t, dict):
                done = t.get("done", False)
            if done:
                continue
            agent = getattr(t, "agent", None)
            if agent is None and isinstance(t, dict):
                agent = t.get("agent", "")
            if str(agent) in ("chapter_writer", "section_writer"):
                # prefix 검사(write:)는 여기서 생략 — writer가 살아있으면 Direct QA 차단
                return True
        return False
    except Exception:
        return False

def _looks_like_research_mode(st: Mapping[str, Any]) -> bool:
    try:
        # 1) 연구 라운드 진행 중
        if int(st.get("research_round", 0) or 0) > 0:
            return True
        # 2) 역할/목표/반복횟수로 유추
        role = str(st.get("agent_role", "") or "").strip().lower()
        has_objs = bool(st.get("research_objectives"))
        iter_count = int(st.get("iteration_count", 0) or 0)
        if role == "research analyst" and has_objs and iter_count > 0:
            return True
        # 3) 플래그 기반 힌트
        if _get_flag(st, "research_loop_active", False):
            return True
        return False
    except Exception:
        return False

def should_direct_qa(state: Mapping[str, Any]) -> bool:
    """
    Direct QA를 지금 허용할지 여부를 판정합니다.
    차단 조건:
      - 연구 라운드/연구 모드 유사 상태
      - writer 예약/잠금(pending_write_title) 또는 writer 펜딩 존재
      - suppress_vector_qa 플래그
    허용 조건:
      - 위 차단 조건이 모두 거짓
    """
    try:
        if _looks_like_research_mode(state):
            return False
        if _get_flag(state, "suppress_vector_qa", False):
            return False
        if _get_flag(state, "pending_write_title", False):
            return False
        tasks = state.get("task_history", []) or []
        if _has_pending_writer(tasks):
            return False
        return True
    except Exception:
        return False

if "should_direct_qa" not in __all__:
    __all__.append("should_direct_qa")