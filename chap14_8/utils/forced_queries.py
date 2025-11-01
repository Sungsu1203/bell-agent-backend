# utils/forced_queries.py
from __future__ import annotations

import json
import re
from typing import List, Iterable, Optional, Any

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config 일원화: core/config.CFG 사용 (없어도 안전하게 동작)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from core.config import CFG  # 권장 경로
except Exception:  # pragma: no cover
    class _DummyCFG:  # 최소 폴백
        ALLOW_FORCED_QUERIES: bool = True
        FORCED_QUERY_LOOKBACK: int = 15
        FORCED_QUERY_MAX_PER_RUN: int = 20
        FORCED_QUERY_MIN_LEN: int = 3
        FORCED_QUERY_EXPAND_YEAR_RANGES: bool = True
        FORCED_QUERY_YEAR_SPAN_LIMIT: int = 6  # 2020..2025 → span=6(포함)
        FORCED_QUERY_ENABLE_SITE_SPLIT: bool = True
        FORCED_QUERY_ENFORCE_GATEKEEP: bool = True
        # 게이트키핑 연동(있으면 사용)
        GATE_KEEP_SOURCES: bool = False
        ALLOWED_DOMAINS: set[str] = set()
    CFG = _DummyCFG()  # type: ignore

# 하위호환 상수(다른 코드가 import 할 수 있음)
ALLOW_FORCED_QUERIES: bool = getattr(CFG, "ALLOW_FORCED_QUERIES", True)
FORCED_QUERY_LOOKBACK: int = getattr(CFG, "FORCED_QUERY_LOOKBACK", 15)
FORCED_QUERY_MAX_PER_RUN: int = getattr(CFG, "FORCED_QUERY_MAX_PER_RUN", 20)
FORCED_QUERY_MIN_LEN: int = getattr(CFG, "FORCED_QUERY_MIN_LEN", 3)
FORCED_QUERY_EXPAND_YEAR_RANGES: bool = getattr(CFG, "FORCED_QUERY_EXPAND_YEAR_RANGES", True)
FORCED_QUERY_YEAR_SPAN_LIMIT: int = getattr(CFG, "FORCED_QUERY_YEAR_SPAN_LIMIT", 6)
FORCED_QUERY_ENABLE_SITE_SPLIT: bool = getattr(CFG, "FORCED_QUERY_ENABLE_SITE_SPLIT", True)
FORCED_QUERY_ENFORCE_GATEKEEP: bool = getattr(CFG, "FORCED_QUERY_ENFORCE_GATEKEEP", True)

GATE_KEEP_SOURCES: bool = getattr(CFG, "GATE_KEEP_SOURCES", False)
ALLOWED_DOMAINS: set[str] = set(getattr(CFG, "ALLOWED_DOMAINS", set()) or [])

__all__ = [
    "extract_forced_queries_from_messages",
    "normalize_forced_query",
]

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
BULLET = r"^[\-\*\u2022\u2013]\s*"  # -, *, •, – 지원
# 공백 포함한 범위, 괄호 안 범위도 허용: (2020 .. 2023)
_YEAR_RANGE_RE = re.compile(r"\b(19|20)\d{2}\s*\.\.\s*(19|20)\d{2}\b")

# site:(a.com OR b.com) / site:a.com OR site:b.com 모두 지원
_SITE_GROUP_RE = re.compile(
    r"""(?ix)
    (?:^|\s)                # 앞 공백/시작
    site:
    (?:
        \(\s*               # 괄호 그룹 시작 (옵션)
        (?P<grp>[^)]+?)     # 괄호 안 텍스트 (예: a.com OR b.com)
        \s*\)
        |
        (?P<single>\S+)     # 단일 사이트
    )
    """
)

def _strip_bullet(line: str) -> str:
    return re.sub(BULLET, "", line).strip()

def _dedupe(seq: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for s in seq:
        k = (s or "").strip()
        if not k or len(k) < FORCED_QUERY_MIN_LEN:
            continue
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out

def _parse_json_array(text: str) -> List[str]:
    try:
        arr = json.loads(text)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr]
    except Exception:
        pass
    return []

def _expand_year_range_once(q: str) -> str:
    """
    '2023..2025' → '(2023 OR 2024 OR 2025)'
    스팬이 FORCED_QUERY_YEAR_SPAN_LIMIT를 초과하면 확장하지 않음.
    """
    if not FORCED_QUERY_EXPAND_YEAR_RANGES:
        return q

    def _repl(m: re.Match) -> str:
        left_s, right_s = m.group(0).split("..")
        try:
            left = int(re.sub(r"\D", "", left_s))
            right = int(re.sub(r"\D", "", right_s))
        except Exception:
            return m.group(0)
        if left > right:
            left, right = right, left
        span = right - left + 1
        if span <= 1 or span > FORCED_QUERY_YEAR_SPAN_LIMIT:
            return m.group(0)  # 과도/무의미 범위는 그대로 둠
        years = " OR ".join(str(y) for y in range(left, right + 1))
        return f"({years})"

    return _YEAR_RANGE_RE.sub(_repl, q)

def _normalize_host_from_site_expr(s: str) -> str:
    # site: 앞부분 제거 후 괄호·공백·트레일러 정리
    h = re.sub(r"^site:\s*", "", s.strip(), flags=re.I)
    # 불필요 문자 제거
    return re.sub(r"[)\]]+$", "", h).strip().lower()

def _filter_sites_by_gatekeep(sites: List[str]) -> List[str]:
    """
    게이트키핑이 강제되는 경우(ALLOWED_DOMAINS가 비어있지 않음) 허용 도메인만 유지
    """
    if not (FORCED_QUERY_ENFORCE_GATEKEEP and GATE_KEEP_SOURCES and ALLOWED_DOMAINS):
        return sites
    allowed = set(ALLOWED_DOMAINS)
    kept = [s for s in sites if s in allowed]
    if len(kept) != len(sites):
        dropped = set(sites) - set(kept)
        if dropped:
            logger.info("[FORCED_QUERY] gatekeep: dropped sites=%s kept=%s",
                        sorted(dropped), sorted(kept))
    return kept

def _split_multi_site_query(q: str) -> Optional[List[str]]:
    """
    '... site:a OR site:b' → ['... site:a', '... site:b']
    '... site:(a OR b OR c)' → ['... site:a', '... site:b', '... site:c']
    게이트키핑이 켜져 있으면 허용 도메인만 유지.
    """
    if not FORCED_QUERY_ENABLE_SITE_SPLIT:
        return None
    if "site:" not in q:
        return None

    m = _SITE_GROUP_RE.search(q)
    if not m:
        return None

    sites: List[str] = []
    if m.group("single"):
        sites = [m.group("single").strip()]
    else:
        grp = m.group("grp") or ""
        # OR/쉼표/공백 분리 허용
        raw_sites = re.split(r"\s*(?:OR|,|\s)\s*", grp, flags=re.I)
        sites = [s for s in (x.strip() for x in raw_sites) if s]

    sites = [_normalize_host_from_site_expr(s) for s in sites if s]
    sites = _filter_sites_by_gatekeep(sites)

    # base에서 모든 site:... 제거 (괄호 그룹/단일 모두)
    base = re.sub(_SITE_GROUP_RE, " ", q).strip()
    base = re.sub(r"\s{2,}", " ", base).strip()

    return [f"{base} site:{s}" for s in sites] if sites else [base]

def _parse_force_queries_block(text: str) -> List[str]:
    out: List[str] = []

    # 1) "정확히 다음 쿼리로 검색" 이후 불릿 라인들
    m = re.search(r"(정확히\s*다음\s*쿼리로\s*검색[하새]세요?[:：]?\s*)(?P<blk>(?:\n.+)+)", text, flags=re.I)
    if m:
        blk = m.group("blk")
        for line in blk.splitlines():
            line = line.strip()
            if re.match(BULLET, line):
                out.append(_strip_bullet(line))

    # 2) 트리플쿼트 블록 안의 불릿 라인
    for qblk in re.findall(r"```+([\s\S]*?)```+|\"\"\"+([\s\S]*?)\"\"\"+", text):
        blk = (qblk[0] or qblk[1] or "")
        for line in blk.splitlines():
            line = line.strip()
            if re.match(BULLET, line):
                out.append(_strip_bullet(line))

    # 3) JSON/YAML 스타일
    for m in re.finditer(r"force_queries\s*:\s*(\[[\s\S]*?\])", text, flags=re.I):
        out += _parse_json_array(m.group(1))
    for m in re.finditer(r"\{[\s\S]*?\"force_queries\"\s*:\s*(\[[\s\S]*?\])[\s\S]*?\}", text, flags=re.I):
        out += _parse_json_array(m.group(1))

    # 4) YAML 불릿
    yml = re.search(r"(?m)^\s*queries\s*:\s*(?P<blk>(?:\n\s*-\s*.+)+)", text)
    if yml:
        for line in yml.group("blk").splitlines():
            line = line.strip()
            if re.match(BULLET, line):
                out.append(_strip_bullet(line))

    # 5) 독립 불릿 라인
    for line in text.splitlines():
        s = line.strip()
        if re.match(BULLET, s):
            out.append(_strip_bullet(s))

    return _dedupe(out)

# 라인형 "force_query: ..." 매칭
_FORCE_RE = re.compile(r"""^\s*force_query\s*:\s*(?P<q>.+?)\s*$""", re.IGNORECASE)

def _dequote(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and (s[0] == s[-1]) and s[0] in ("'", '"'):
        return s[1:-1].strip()
    return s

def _msg_role(m: Any) -> str:
    """LangChain/딕셔너리 혼용 환경에서 role/human 구분."""
    role = getattr(m, "type", None) or getattr(m, "role", None)
    if not role and isinstance(m, dict):
        role = m.get("role") or m.get("type")
    return (role or "").lower()

def _msg_content(m: Any) -> str:
    c = getattr(m, "content", None)
    if c is None and isinstance(m, dict):
        c = m.get("content")
    return str(c or "")

# ─────────────────────────────────────────────────────────────────────────────
# Public APIs
# ─────────────────────────────────────────────────────────────────────────────
def normalize_forced_query(q: str) -> list[str]:
    """
    강제 쿼리 전처리:
      - 연도 범위(YYYY..YYYY) 일반화 확장
      - 다중 site 분할(괄호/OR/쉼표 모두) 및 게이트키핑 연동
    """
    if not isinstance(q, str):
        return []
    q = q.strip()
    if not q:
        return []

    # 1) 연도 범위 일반화
    q = _expand_year_range_once(q)

    # 2) 다중 site 분할
    multi = _split_multi_site_query(q)
    if multi is not None:
        return [s for s in multi if s]

    return [q]

def extract_forced_queries_from_messages(messages, lookback: Optional[int] = None) -> List[str]:
    """
    최근 사용자 메시지의 강제 검색 쿼리를 추출하여 반환합니다.
    - 라인형:   force_query: "EV charging Korea site:iea.org"
    - 블록/불릿/JSON/YAML: _parse_force_queries_block에서 처리
    - CFG 옵션
      * ALLOW_FORCED_QUERIES(False)면 빈 리스트 반환
      * FORCED_QUERY_LOOKBACK / MAX_PER_RUN / MIN_LEN 등 반영
      * 게이트키핑 정책과 연동(옵션)
    """
    if not ALLOW_FORCED_QUERIES:
        return []

    try:
        _lookback = int(lookback if lookback is not None else FORCED_QUERY_LOOKBACK)
    except Exception:
        _lookback = FORCED_QUERY_LOOKBACK

    if _lookback <= 0:
        return []

    # 최근 사용자 메시지 텍스트 결합 (LangChain BaseMessage/dict 모두 허용)
    user_texts: List[str] = []
    pool = list(messages or [])[-_lookback:]
    for m in pool:
        role = _msg_role(m)
        if role in ("human", "user"):
            user_texts.append(_msg_content(m))
    big = "\n".join(t for t in user_texts if t)

    if not big.strip():
        return []

    # 1) 라인형 우선 매칭
    line_hits: List[str] = []
    for line in big.splitlines():
        mo = _FORCE_RE.match(line)
        if mo:
            q = _dequote(mo.group("q"))
            if q:
                line_hits.append(q)

    # 2) 블록형/불릿형 파싱
    block_hits = _parse_force_queries_block(big)

    # 3) 병합 (순서 보존: 라인형 → 블록형)
    raw_merged = line_hits + block_hits

    if not raw_merged:
        return []

    # 4) 정규화(범위 보정/다중 site 분할) → 평탄화
    expanded: list[str] = []
    for q in raw_merged:
        expanded.extend(normalize_forced_query(q))

    # 5) 중복 제거 및 상한 제한
    deduped = _dedupe(expanded)
    if len(deduped) > FORCED_QUERY_MAX_PER_RUN:
        logger.info("[FORCED_QUERY] max cap applied: %d → %d", len(deduped), FORCED_QUERY_MAX_PER_RUN)
        deduped = deduped[:FORCED_QUERY_MAX_PER_RUN]

    return deduped
