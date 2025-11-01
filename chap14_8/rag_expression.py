# rag_expression.py — dynamic config access (v2025-10-27)
import re
from typing import Any, Optional
from re import Pattern  # 3.12+ 호환

import logging
logger = logging.getLogger(__name__)

# --- safe tail-trim patterns (quote/paren/bracket) ---
_TAIL_PUNCT_RE = re.compile(r"""[\"“”'’)\]]+$""")
_TAIL_SECTION_RE = re.compile(r"\s*(?:섹션|section)\s*$", re.IGNORECASE)

__all__ = [
    # compiled regexes
    "RE_WRITE_LINE", "RE_WRITE_INLINE", "RE_SHOW_OUTLINE", "RE_NEW_TOPIC", "RE_RENAME_CHAPTER",
    "RE_WRITE_REQUEST_KO",
    # helpers
    "extract_write_title", "is_outline_creation", "is_outline_display",
    "extract_new_topic_title", "extract_rename_chapter",
    "extract_section_index",
    "RE_QUANT_NUMBER", "RE_QUANT_SENT_HINTS", "split_sentences_ko_en",
    "coerce_message_content_to_str",
]

# ─────────────────────────────────────────────────────────────
# Dynamic config (CFG → module attr → default)
# ─────────────────────────────────────────────────────────────
import core.config as config

def _get_cfg_attr(name: str, default):
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return default


def _cfg_bool(name: str, default: bool) -> bool:
    v = _get_cfg_attr(name, default)
    try:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1","true","yes","on","y"}
    except Exception:
        return default


def _re_compile(name: str, default_pattern: str, flags: int = 0) -> Pattern[str]:
    pat = _get_cfg_attr(name, default_pattern)
    try:
        return re.compile(str(pat), flags)
    except Exception:
        logger.debug("regex compile failed for %s; using default", name, exc_info=True)
        return re.compile(default_pattern, flags)


# ─────────────────────────────────────────────────────────────
# Content normalizer: 메시지 content가 str | list[...] | dict 일 때도 안전하게 문자열로
# ─────────────────────────────────────────────────────────────

def coerce_message_content_to_str(content: Any) -> str:
    """LangChain/OpenAI 멀티모달 content까지 안전하게 문자열로 정규화."""
    # 0) LangChain BaseMessage 호환 (state_io._to_plain과 정합)
    try:
        from langchain_core.messages import BaseMessage as _LCBaseMessage  # type: ignore
    except Exception:
        _LCBaseMessage = None
    if _LCBaseMessage and isinstance(content, _LCBaseMessage):
        try:
            return str(getattr(content, "content", "") or "")
        except Exception:
            return ""

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


# ─────────────────────────────────────────────────────────────
# 정량 문장 탐지용 정규식/도우미 (config로 오버라이드 가능)
# ─────────────────────────────────────────────────────────────
_RE_QUANT_DEFAULT = r"(?<!\d)(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(\s?(?:%|퍼센트|배|억|만|조|달러|원|억원|조원|년|월|일|건|명|개|pt|포인트))?"
RE_QUANT_NUMBER: Pattern[str] = _re_compile("QUANT_NUMBER_REGEX", _RE_QUANT_DEFAULT, re.IGNORECASE)

_RE_QUANT_HINTS_DEFAULT = r"(증가|감소|성장|하락|상승|점유율|시장|매출|CAGR|연평균|ROI|전년|YoY|QoQ|전월|예상|전망|통계|조사|데이터|지표)"
RE_QUANT_SENT_HINTS: Pattern[str] = _re_compile("QUANT_HINTS_REGEX", _RE_QUANT_HINTS_DEFAULT, re.IGNORECASE)

_SENT_SPLIT_DEFAULT = r'(?<=[.!?])\s+|(?<=다)\s+|(?<=요)\s+|(?<=습니다)\s+'
_SENT_SPLIT_RE: Pattern[str] = _re_compile("SENT_SPLIT_REGEX", _SENT_SPLIT_DEFAULT)


def split_sentences_ko_en(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(_SENT_SPLIT_RE, text)
    return [p.strip() for p in parts if p and p.strip()]


# ─────────────────────────────────────────────────────────────
# 라인/인라인/자연어 write 패턴 (config로 오버라이드 가능)
# ─────────────────────────────────────────────────────────────
_RE_WRITE_LINE_DEFAULT = r"^\s*(?:write|작성|집필)\s*[:：]\s*(.+)$"
RE_WRITE_LINE: Pattern[str] = _re_compile("WRITE_LINE_REGEX", _RE_WRITE_LINE_DEFAULT, re.IGNORECASE)

_RE_WRITE_INLINE_DEFAULT = r"(?:^|[\s().,;])(?:write|작성|집필)\s*[:：]\s*(.+?)\s*(?=$|[\r\n)\]]|[.;])"
RE_WRITE_INLINE: Pattern[str] = _re_compile("WRITE_INLINE_REGEX", _RE_WRITE_INLINE_DEFAULT, re.IGNORECASE)

# 한국어 자연어형: "4. XXX 섹션 작성해주세요", "XXX 작성해줘", "4) XXX 작성" 등
_RE_WRITE_KO_DEFAULT = (
    r"(?P<prefix>^|[\s])"                              # 문장 시작 또는 공백
    r"(?:(?P<idx>\d+)[\.|\)]\s*)?"                   # 선택적 선행 번호 "4." / "4)"
    r"(?P<title>[^.\n\r\t:：]+?)"                      # 제목(콜론/줄바꿈/마침표 전까지)
    r"(?:\s*섹션)?\s*(?:을|를)?\s*"                    # '섹션', 목적격 조사 선택
    r"(?:작성|집필)"                                     # 동사
    r"(?:해줘|해\s*줘|해주세요|해\s*주세요|해주시오|해\s*주시오)?"  # 공손 표현
)
RE_WRITE_REQUEST_KO: Pattern[str] = _re_compile("WRITE_REQUEST_KO_REGEX", _RE_WRITE_KO_DEFAULT, re.IGNORECASE)
_ENABLE_KO_NATURAL_WRITE: bool = _cfg_bool("ENABLE_KO_NATURAL_WRITE", True)

# "목차 보여줘/보기/출력/display/show" 등
_RE_SHOW_OUTLINE_DEFAULT = r"(?:목차|outline).*(?:보여|보기|출력|display|show)|^(?:책|ai).*(?:목차)$"
RE_SHOW_OUTLINE: Pattern[str] = _re_compile("SHOW_OUTLINE_REGEX", _RE_SHOW_OUTLINE_DEFAULT, re.IGNORECASE)

# 새 주제/새 보고서 전환
_RE_NEW_TOPIC_DEFAULT = (
    r"(?:새\s*(?:보고서|책|프로젝트)\s*(?:작성|집필|write)?|"
    r"주제\s*(?:변경|바꿔)|"
    r"new\s*(?:report|project|book)|"
    r"switch\s*(?:topic|report|project|book))"
    r"\s*[:：]?\s*(?P<title>.*)$"
)
RE_NEW_TOPIC: Pattern[str] = _re_compile("NEW_TOPIC_REGEX", _RE_NEW_TOPIC_DEFAULT, re.IGNORECASE)

# --- Rename chapter intent ---
_RE_RENAME_CHAPTER_DEFAULT = r"^\s*(\d+)\s*장\s*제목.*?['\"](.+?)['\"]\s*로\s*변경"
RE_RENAME_CHAPTER: Pattern[str] = _re_compile("RENAME_CHAPTER_REGEX", _RE_RENAME_CHAPTER_DEFAULT, re.IGNORECASE)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def extract_section_index(text_like: Any) -> Optional[int]:
    """사용자 문장 맨 앞의 '4.' / '4)' 형태 섹션 번호를 추출."""
    text = coerce_message_content_to_str(text_like)
    if not text:
        return None
    m = re.search(r"^\s*(\d+)[\.\)]\s*", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    # 한국어 자연어 패턴에도 idx 그룹이 있으면 활용
    if _ENABLE_KO_NATURAL_WRITE:
        m2 = RE_WRITE_REQUEST_KO.search(text)
        if m2 and m2.group("idx"):
            try:
                return int(m2.group("idx"))
            except ValueError:
                return None
    return None


def _strip_smart_quotes(s: str) -> str:
    # 따옴표 + 괄호/대괄호/마침표/세미콜론까지 정리 (국문 마침표 포함)
    return s.strip(' \t\'\"“”‘’()[];:。．.;…‥.')


def extract_write_title(text_like: Any) -> Optional[str]:
    """문자열/멀티모달 입력에서 write/작성/집필 명령의 타이틀을 추출.
    - 명시형: "write: XXX", "작성: XXX", "집필: XXX"
    - 자연어형: "4. XXX 섹션 작성해주세요", "XXX 작성해줘"
    """
    text = coerce_message_content_to_str(text_like)
    if not text:
        return None

    # 새 주제 전환 문구면 write 해석 금지
    if RE_NEW_TOPIC.search(text):
        return None

    # 1) 명시형 우선
    m = RE_WRITE_LINE.search(text) or RE_WRITE_INLINE.search(text)
    if m:
        title = _strip_smart_quotes(m.group(1))
        logger.debug("extract_write_title explicit hit: %s", title)
        return title or None

    # 2) 한국어 자연어형 보조: 번호/공손표현 포함 문장 처리
    if _ENABLE_KO_NATURAL_WRITE:
        m2 = RE_WRITE_REQUEST_KO.search(text)
        if m2:
            raw = (m2.group("title") or "").strip()
            # 문장 끝 불필요 토큰 제거(따옴표/괄호/대괄호 닫힘 등)
            raw = _TAIL_PUNCT_RE.sub("", raw).strip()
            # '섹션/section' 꼬리 제거(대소문자 무시)
            raw = _TAIL_SECTION_RE.sub("", raw).strip()
            title = _strip_smart_quotes(raw)
            logger.debug("extract_write_title ko-natural hit: %s", title)
            return title or None

    return None


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
    return _strip_smart_quotes(t) or None


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


# ─────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────
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
        logger.info("> %s", s)
        logger.info("  write: %s", extract_write_title(s))
        logger.info("  show_outline: %s", is_outline_display(s))
        logger.info("  new_topic: %s", extract_new_topic_title(s))
