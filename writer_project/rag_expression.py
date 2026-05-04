# rag_expression.py — dynamic config access (v2025-10-27)
import re
import sys
from typing import Any, Optional

# re.Pattern (3.12+) / typing.Pattern (3.10~3.11) 호환 별칭 (type: ignore 제거)
if sys.version_info >= (3, 12):
    from re import Pattern as RePattern
else:
    from typing import Pattern as RePattern

import logging
logger = logging.getLogger(__name__)

# LangChain BaseMessage 존재 여부를 런타임에만 검사하는 안전 헬퍼
def _is_langchain_message(obj: Any) -> bool:
    try:
        from langchain_core.messages import BaseMessage  # 런타임 의존성
    except Exception:  # 미설치/버전 차이 등
        return False
    try:
        return isinstance(obj, BaseMessage)
    except Exception:
        return False

# --- safe tail-trim patterns (quote/paren/bracket) ---
# §13-7: 닫는 괄호/대괄호는 대응하는 여는 짝이 있으면 보존, 없으면 제거.
# 닫는 따옴표는 기존 동작 유지(짝 매칭이 모호함).
_TAIL_QUOTE_RE = re.compile(r"""[\"""'']+$""")


def _strip_tail_punct(s: str) -> str:
    """문자열 끝의 닫는 따옴표/괄호/대괄호를 정리.
    단, 닫는 ')' 또는 ']'는 문자열 안에 대응 여는 짝이 있으면 보존한다.
    예: '실행 로드맵(KPI)' → '실행 로드맵(KPI)' (짝 매칭, 보존)
        'foo)' → 'foo' (짝 없음, 제거)
        'foo")' → 'foo' (짝 없음 → ) 제거 → " 제거)
    """
    if not s:
        return s
    # 1) 닫는 따옴표만 우선 제거 (짝 개념 모호)
    s = _TAIL_QUOTE_RE.sub("", s)
    # 2) 닫는 괄호/대괄호: 짝 매칭 검사 후 결정
    while s and s[-1] in (")", "]"):
        closer = s[-1]
        opener = "(" if closer == ")" else "["
        # 끝의 closer 1개를 떼고 나머지에서 opener 갯수 vs closer 갯수 비교
        body = s[:-1]
        if body.count(opener) > body.count(closer):
            # 대응하는 여는 짝이 있으니 closer는 짝의 일부 → 보존
            break
        # 짝 없는 떠돌이 closer → 제거 후 다시 검사 (e.g. '...))')
        s = body.rstrip()
        # 한 번 더 닫는 따옴표 제거 (e.g. 'foo")' 케이스)
        s = _TAIL_QUOTE_RE.sub("", s)
    return s


# 하위 호환: 기존 변수명 보존 (다른 모듈이 import할 가능성 대비)
# §13-7 이후로는 _strip_tail_punct() 사용을 권장
_TAIL_PUNCT_RE = re.compile(r"""[\"""'')\]]+$""")  # legacy, deprecated
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
    """CFG → 모듈 상수 → 기본값 순 안전 조회(예외시 기본값)."""
    try:
        cfg = getattr(config, "CFG", None)
        if cfg is not None and hasattr(cfg, name):
            return getattr(cfg, name)
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        return default
    return default


def _cfg_bool(name: str, default: bool) -> bool:
    v = _get_cfg_attr(name, default)
    try:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"1","true","yes","on","y"}
    except Exception:
        return default


def _re_compile(name: str, default_pattern: str, flags: int = 0) -> RePattern[str]:
    pat = _get_cfg_attr(name, default_pattern)
    try:
        return re.compile(str(pat), flags)
    except Exception:
        # 설정 오타 등으로 컴파일 실패 시 기본 패턴으로 폴백
        logger.debug("regex compile failed for %s; using default", name, exc_info=True)
        return re.compile(default_pattern, flags)


# ─────────────────────────────────────────────────────────────
# Content normalizer: 메시지 content가 str | list[...] | dict 일 때도 안전하게 문자열로
# ─────────────────────────────────────────────────────────────

def coerce_message_content_to_str(content: Any) -> str:
    """LangChain/OpenAI 멀티모달 content까지 안전하게 문자열로 정규화."""
    # 0) LangChain BaseMessage 호환 (런타임 안전 검사)
    if _is_langchain_message(content):
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
RE_QUANT_NUMBER: RePattern[str] = _re_compile("QUANT_NUMBER_REGEX", _RE_QUANT_DEFAULT, re.IGNORECASE)


_RE_QUANT_HINTS_DEFAULT = r"(증가|감소|성장|하락|상승|점유율|시장|매출|CAGR|연평균|ROI|전년|YoY|QoQ|전월|예상|전망|통계|조사|데이터|지표)"
RE_QUANT_SENT_HINTS: RePattern[str] = _re_compile("QUANT_HINTS_REGEX", _RE_QUANT_HINTS_DEFAULT, re.IGNORECASE)

_SENT_SPLIT_DEFAULT = r'(?<=[.!?])\s+|(?<=다)\s+|(?<=요)\s+|(?<=습니다)\s+'
_SENT_SPLIT_RE: RePattern[str] = _re_compile("SENT_SPLIT_REGEX", _SENT_SPLIT_DEFAULT)


def split_sentences_ko_en(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(_SENT_SPLIT_RE, text)
    return [p.strip() for p in parts if p and p.strip()]


# ─────────────────────────────────────────────────────────────
# 라인/인라인/자연어 write 패턴 (config로 오버라이드 가능)
# ─────────────────────────────────────────────────────────────
_RE_WRITE_LINE_DEFAULT = r"^\s*(?:write|작성|집필)\s*[:：]\s*(.+)$"
RE_WRITE_LINE: RePattern[str] = _re_compile("WRITE_LINE_REGEX", _RE_WRITE_LINE_DEFAULT, re.IGNORECASE)

_RE_WRITE_INLINE_DEFAULT = r"(?:^|[\s().,;])(?:write|작성|집필)\s*[:：]\s*(.+?)\s*(?=$|[\r\n)\]]|[.;])"
RE_WRITE_INLINE: RePattern[str] = _re_compile("WRITE_INLINE_REGEX", _RE_WRITE_INLINE_DEFAULT, re.IGNORECASE)

# 한국어 자연어형: "4. XXX 섹션 작성해주세요", "XXX 작성해줘", "4) XXX 작성" 등
_RE_WRITE_KO_DEFAULT = (
    r"(?P<prefix>^|[\s])"                              # 문장 시작 또는 공백
    r"(?:(?P<idx>\d+)[\.|\)]\s*)?"                   # 선택적 선행 번호 "4." / "4)"
    r"(?P<title>[^.\n\r\t:：]+?)"                      # 제목(콜론/줄바꿈/마침표 전까지)
    r"(?:\s*섹션)?\s*(?:을|를)?\s*"                    # '섹션', 목적격 조사 선택
    r"(?:작성|집필)"                                     # 동사
    r"(?:해줘|해\s*줘|해주세요|해\s*주세요|해주시오|해\s*주시오)?"  # 공손 표현
)
RE_WRITE_REQUEST_KO: RePattern[str] = _re_compile("WRITE_REQUEST_KO_REGEX", _RE_WRITE_KO_DEFAULT, re.IGNORECASE)
_ENABLE_KO_NATURAL_WRITE: bool = _cfg_bool("ENABLE_KO_NATURAL_WRITE", True)

# "목차 보여줘/보기/출력/display/show" 등
_RE_SHOW_OUTLINE_DEFAULT = r"(?:목차|outline).*(?:보여|보기|출력|display|show)|^(?:책|ai).*(?:목차)$"
RE_SHOW_OUTLINE: RePattern[str] = _re_compile("SHOW_OUTLINE_REGEX", _RE_SHOW_OUTLINE_DEFAULT, re.IGNORECASE)

# 새 주제/새 보고서 전환
_RE_NEW_TOPIC_DEFAULT = (
    r"(?:새\s*(?:보고서|책|프로젝트)\s*(?:작성|집필|write)?|"
    r"주제\s*(?:변경|바꿔)|"
    r"new\s*(?:report|project|book)|"
    r"switch\s*(?:topic|report|project|book))"
    r"\s*[:：]?\s*(?P<title>.*)$"
)
RE_NEW_TOPIC: RePattern[str] = _re_compile("NEW_TOPIC_REGEX", _RE_NEW_TOPIC_DEFAULT, re.IGNORECASE)

# --- Rename chapter intent ---
_RE_RENAME_CHAPTER_DEFAULT = r"^\s*(\d+)\s*장\s*제목.*?['\"](.+?)['\"]\s*로\s*변경"
RE_RENAME_CHAPTER: RePattern[str] = _re_compile("RENAME_CHAPTER_REGEX", _RE_RENAME_CHAPTER_DEFAULT, re.IGNORECASE)


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
    """따옴표 + 마침표/세미콜론 등 꼬리 noise 정리.
    §13-7: 닫는 괄호/대괄호는 _strip_tail_punct()에서 짝 매칭 후 결정하므로
           여기서는 strip 대상에서 제외한다.
    """
    # 1) 양끝의 공백/따옴표/마침표/세미콜론 정리 (괄호류 제외)
    s = s.strip(' \t\'\"""''.;:。．;…‥.')
    # 2) 꼬리 괄호/대괄호는 짝 매칭 기반으로 정리
    s = _strip_tail_punct(s)
    return s

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
            raw = _strip_tail_punct(raw).strip()
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
    t = _strip_smart_quotes(t)
    return (t or None)


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
