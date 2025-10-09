# rag_expression.py
import re
from typing import Any, Optional, Pattern

__all__ = [
    # compiled regexes
    "RE_WRITE_LINE", "RE_WRITE_INLINE", "RE_SHOW_OUTLINE", "RE_NEW_TOPIC",
    # helpers
    "extract_write_title", "is_outline_creation", "is_outline_display", "extract_new_topic_title",
    "RE_QUANT_NUMBER", "RE_QUANT_SENT_HINTS", "split_sentences_ko_en",
    "coerce_message_content_to_str",
]

# ───────────────────────────────────────────────────────────────────────────────
# Content normalizer: 메시지 content가 str | list[...] | dict 일 때도 안전하게 문자열로
def coerce_message_content_to_str(content: Any) -> str:
    """LangChain/OpenAI 멀티모달 content까지 안전하게 문자열로 정규화."""
    if isinstance(content, str):
        return content

    # list[dict/type] 포맷 (예: [{"type":"text","text":"..."}, {"type":"image_url", ...}])
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                t = (item.get("type") or "").lower()
                if t == "text" and "text" in item:
                    parts.append(str(item["text"]))
                elif "content" in item:
                    parts.append(str(item["content"]))
                # 그 외 타입은 무시(이미지/오디오 등)
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)

    # dict가 온 경우에도 텍스트 필드 우선
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"])
        if "content" in content:
            return str(content["content"])
        return ""

    return "" if content is None else str(content)

# ───────────────────────────────────────────────────────────────────────────────
# 정량 문장 탐지용 정규식/도우미
RE_QUANT_NUMBER = re.compile(
    r"(?<!\d)(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(\s?(?:%|퍼센트|배|억|만|조|달러|원|억원|조원|년|월|일|건|명|개|pt|포인트))?",
    re.IGNORECASE,
)
RE_QUANT_SENT_HINTS = re.compile(
    r"(증가|감소|성장|하락|상승|점유율|시장|매출|CAGR|연평균|ROI|전년|YoY|QoQ|전월|예상|전망|통계|조사|데이터|지표)",
    re.IGNORECASE,
)

def split_sentences_ko_en(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r'(?<=[.!?])\s+|(?<=다)\s+|(?<=요)\s+|(?<=습니다)\s+', text)
    return [p.strip() for p in parts if p and p.strip()]

# ───────────────────────────────────────────────────────────────────────────────
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
RE_NEW_TOPIC = re.compile(
    r"(?:새\s*(?:보고서|책|프로젝트)\s*(?:작성|집필|write)?|"
    r"주제\s*(?:변경|바꿔)|"
    r"new\s*(?:report|project|book)|"
    r"switch\s*(?:topic|report|project|book))"
    r"\s*[:：]?\s*(?P<title>.*)$",
    re.IGNORECASE,
)

# --- Rename chapter intent ---
RE_RENAME_CHAPTER = re.compile(
    r"^\s*(\d+)\s*장\s*제목.*?['\"](.+?)['\"]\s*로\s*변경", re.IGNORECASE
)

# ───────────────────────────────────────────────────────────────────────────────
# Helpers

def _strip_smart_quotes(s: str) -> str:
    return s.strip(' \t\'"“”‘’')

def extract_write_title(text_like: Any) -> Optional[str]:
    """문자열/멀티모달 입력에서 write/작성/집필 명령의 타이틀을 추출."""
    text = coerce_message_content_to_str(text_like)
    if not text:
        return None    
    # ✅ 새 주제 전환 문구면 write 해석 금지
    if RE_NEW_TOPIC.search(text):
        return None
    m = RE_WRITE_LINE.search(text) or RE_WRITE_INLINE.search(text)
    if not m:
        return None
    title = _strip_smart_quotes(m.group(1))
    return title or None

def is_outline_creation(text_like: Any) -> bool:
    """목차 생성 의도 탐지(멀티모달 입력 안전)."""
    text = coerce_message_content_to_str(text_like)
    return bool(re.search(r"(목차|outline).*(만들|작성|새로|생성)", text, re.IGNORECASE))

def is_outline_display(text_like: Any) -> bool:
    """목차 표시 의도 탐지(멀티모달 입력 안전)."""
    text = coerce_message_content_to_str(text_like)
    return bool(RE_SHOW_OUTLINE.search(text))

def extract_new_topic_title(text_like: Any) -> Optional[str]:
    """새 주제/보고서 전환 시 제목 추출(멀티모달 입력 안전)."""
    text = coerce_message_content_to_str(text_like)
    if not text:
        return None
    m = RE_NEW_TOPIC.search(text)
    if not m:
        return None
    t = (m.group("title") or "").strip()
    # ✅ 제목 앞에 "작성:/집필:/write:"가 붙은 경우 제거 (예: "작성: 샘플 북 프로젝트")
    if t:
        t = re.sub(r"^(?:작성|집필|write)\s*[:：]\s*", "", t, flags=re.IGNORECASE).strip()
    return t or None

def extract_rename_chapter(text_like: Any) -> Optional[tuple[int, str]]:
    text = coerce_message_content_to_str(text_like)
    if not text:
        return None
    m = RE_RENAME_CHAPTER.search(text)
    if not m:
        return None
    idx = int(m.group(1))
    new_title = m.group(2).strip()
    return (idx, new_title) if new_title else None

# ───────────────────────────────────────────────────────────────────────────────
# Self-test
if __name__ == "__main__":
    samples = [
        "write: Executive Summary",
        "작성: 서론",
        "집필: 2장 데이터 수집",
        "이번에는 outline 보여줘",
        "새 보고서: 생성형 AI 시장",
        # 멀티모달 예시
        [
            {"type": "text", "text": "Here is an image"},
            {"type": "text", "text": "write: Results & Discussion"},
            {"type": "image_url", "image_url": {"url": "https://.../img.png"}},
        ],
    ]
    for s in samples:
        print(">", s)
        print("  write:", extract_write_title(s))
        print("  show_outline:", is_outline_display(s))
        print("  new_topic:", extract_new_topic_title(s))
