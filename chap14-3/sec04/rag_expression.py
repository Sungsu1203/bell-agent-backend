# rag_expression.py
import re
from typing import Optional, Pattern

__all__ = [
    # compiled regexes
    "RE_WRITE_LINE", "RE_WRITE_INLINE", "RE_SHOW_OUTLINE", "RE_NEW_TOPIC",
    # helpers
    "extract_write_title", "is_outline_creation", "is_outline_display", "extract_new_topic_title",
]

# ---- Compiled regexes (일관된 단일 소스) ------------------------------------
# 라인 선두형: "write: ..." / "작성: ..." / "집필: ..."
RE_WRITE_LINE: Pattern[str] = re.compile(
    r"^\s*(?:write|작성|집필)\s*[:：]\s*(.+)$", re.IGNORECASE
)

# 인라인형: 문장 중간의 "write: ..."도 포착
RE_WRITE_INLINE: Pattern[str] = re.compile(
    r"(?:^|[\s().,;])(?:write|작성|집필)\s*[:：]\s*(.+)", re.IGNORECASE
)

# "목차 보여줘/보기/출력/display/show" 등
RE_SHOW_OUTLINE: Pattern[str] = re.compile(
    r"(?:목차|outline).*(?:보여|보기|출력|display|show)|^(?:책|ai).*(?:목차)$",
    re.IGNORECASE,
)

# 새 주제/새 보고서 전환
RE_NEW_TOPIC: Pattern[str] = re.compile(
    r"(?:새\s*(?:보고서|프로젝트)|주제\s*(?:변경|바꿔)|new\s*(?:report|project)|switch\s*(?:topic|report))\s*[:：]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)

# ---- Helpers ----------------------------------------------------------------

def extract_write_title(text: str) -> Optional[str]:
    """문자열에서 write/작성/집필 명령의 타이틀을 추출."""
    if not text:
        return None
    m = RE_WRITE_LINE.search(text)
    if not m:
        m = RE_WRITE_INLINE.search(text)
    if not m:
        return None
    title = m.group(1).strip().strip('\'"“”‘’')
    return title or None

def is_outline_creation(text: str) -> bool:
    """목차 생성 의도 탐지."""
    return bool(re.search(r"(목차|outline).*(만들|작성|새로|생성)", text or "", re.IGNORECASE))

def is_outline_display(text: str) -> bool:
    """목차 표시 의도 탐지."""
    return bool(RE_SHOW_OUTLINE.search(text or ""))

def extract_new_topic_title(text: str) -> Optional[str]:
    """새 주제/보고서 전환 시 제목 추출."""
    if not text:
        return None
    m = RE_NEW_TOPIC.search(text)
    t = (m.group("title").strip() if (m and m.group("title")) else "")
    return t or None

# ---- Self-test (import 시 실행되지 않도록 보호) -----------------------------
if __name__ == "__main__":
    samples = [
        "write: Executive Summary",
        "작성: 서론",
        "집필: 2장 데이터 수집",
        "이번에는 outline 보여줘",
        "새 보고서: 생성형 AI 시장",
    ]
    for s in samples:
        print(">", s)
        print("  write:", extract_write_title(s))
        print("  show_outline:", is_outline_display(s))
        print("  new_topic:", extract_new_topic_title(s))
