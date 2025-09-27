# utils_forced_queries.py (예: 별도 파일 또는 기존 유틸에 추가)
import json, re
from typing import List

BULLET = r"^[\-\*\u2022\u2013]\s*"  # -, *, •, – 지원

def _strip_bullet(line: str) -> str:
    return re.sub(BULLET, "", line).strip()

def _dedupe(seq: List[str]) -> List[str]:
    seen, out = set(), []
    for s in seq:
        k = s.strip()
        if not k or len(k) < 3:  # 너무 짧은 건 버림
            continue
        if k not in seen:
            seen.add(k); out.append(k)
    return out

def _parse_json_array(text: str) -> List[str]:
    try:
        arr = json.loads(text)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr]
    except Exception:
        pass
    return []

def _parse_force_queries_block(text: str) -> List[str]:
    out = []

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
    #   - force_queries: ["a","b"]
    for m in re.finditer(r"force_queries\s*:\s*(\[[\s\S]*?\])", text, flags=re.I):
        out += _parse_json_array(m.group(1))

    #   - {"force_queries":[...]}
    for m in re.finditer(r"\{[\s\S]*?\"force_queries\"\s*:\s*(\[[\s\S]*?\])[\s\S]*?\}", text, flags=re.I):
        out += _parse_json_array(m.group(1))

    #   - queries: \n  - a \n  - b
    yml = re.search(r"(?m)^\s*queries\s*:\s*(?P<blk>(?:\n\s*-\s*.+)+)", text)
    if yml:
        for line in yml.group("blk").splitlines():
            line = line.strip()
            if re.match(BULLET, line):
                out.append(_strip_bullet(line))

    # 4) 독립 불릿 라인만 들어온 경우(사용자가 불릿만 여러 번 보낸 케이스)
    #    최근 10개 메시지의 모든 불릿 라인을 수집
    for line in text.splitlines():
        s = line.strip()
        if re.match(BULLET, s):
            out.append(_strip_bullet(s))

    return _dedupe(out)

def extract_forced_queries_from_messages(messages, lookback:int=15) -> List[str]:
    """최근 사용자 메시지 lookback개를 모아 강제 쿼리 리스트 반환"""
    user_texts = []
    for m in messages[-lookback:]:
        role = getattr(m, "type", None) or getattr(m, "role", None)
        if role in ("human", "user"):
            user_texts.append(getattr(m, "content", "") or "")
    big = "\n\n".join(user_texts)
    return _parse_force_queries_block(big)
