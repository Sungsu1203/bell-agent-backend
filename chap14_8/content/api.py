# content/api.py  ✅ (얇은 re-export 전용)
from __future__ import annotations

"""
의도: 상위 모듈들이 이 파일만 임포트해도 콘텐츠/아웃라인 관련 헬퍼에 접근 가능하도록
얇은 re-export 계층을 제공한다. 직접 심볼 임포트(from ... import ...)를 지양하고,
모듈 단위 임포트 후 속성 재노출로 변경하여 순환/로드 타이밍 이슈를 최소화한다.
"""

import logging
logger = logging.getLogger(__name__)

# ── 모듈 단위 임포트(안전) ────────────────────────────────────────────────
try:
    import content_utils as _cu
except Exception as e:
    logger.exception("content_utils import failed: %s", e)
    raise

try:
    import core.paths as _paths
except Exception as e:
    logger.exception("core.paths import failed: %s", e)
    raise

try:
    import utils.outline as _outline
except Exception as e:
    logger.exception("utils.outline import failed: %s", e)
    raise

try:
    from utils.text_utils import slugify, section_slugify  # 경량, 직접 노출
except Exception as e:
    logger.exception("utils.text_utils import failed: %s", e)
    raise

# ── re-export: content_utils ────────────────────────────────────────────────
save_md_draft = _cu.save_md_draft
save_chapter = _cu.save_chapter
save_section = _cu.save_section
read_draft = _cu.read_draft
list_draft_paths = _cu.list_draft_paths
rename_draft_title = _cu.rename_draft_title
move_draft_between_topics = _cu.move_draft_between_topics
merge_drafts = _cu.merge_drafts

# ── re-export: core.paths (read_outline는 여기 구현을 표준으로 사용) ───────
get_content_dir = _paths.get_content_dir
chapter_filepath = _paths.chapter_filepath
section_filepath = _paths.section_filepath
path_for_title = _paths.path_for_title
get_outline_dir = _paths.get_outline_dir
outline_path = _paths.outline_path
is_written = _paths.is_written
# 공개 별칭(권장): 언더스코어 내부 구현을 외부에 노출하지 않도록
coerce_mode = _paths._coerce_mode
# 하위호환: 과거 코드가 import한 경우를 위해 유지
_coerce_mode = coerce_mode  # alias
read_outline = _paths.read_outline

# ── re-export: utils.outline ────────────────────────────────────────────────
save_outline = _outline.save_outline
parse_outline_headings = _outline.parse_outline_headings
list_outline_headings = _outline.list_outline_headings
next_unwritten_title = _outline.next_unwritten_title

__all__ = [
    # text utils
    "slugify", "section_slugify",
    # core.paths
    "get_content_dir", "chapter_filepath", "section_filepath", "path_for_title",
    "get_outline_dir", "outline_path", "is_written", "coerce_mode", "_coerce_mode", "read_outline",
    # utils.outline
    "save_outline", "parse_outline_headings", "list_outline_headings", "next_unwritten_title",
    # content_utils
    "save_md_draft", "save_chapter", "save_section", "read_draft",
    "list_draft_paths", "rename_draft_title", "move_draft_between_topics", "merge_drafts",
]


# ── lazy proxy: 하위 모듈에 새 심볼이 추가되어도 깨지지 않도록 ──────────────
def __getattr__(name: str):
    """
    명시 re-export 목록에 없더라도, 하위 모듈(content_utils / core.paths / utils.outline)
    에 존재하면 그대로 전달한다. 미존재 시 AttributeError.
    """
    for mod in (_cu, _paths, _outline):
        try:
            return getattr(mod, name)
        except AttributeError:
            continue
    raise AttributeError(f"module 'content.api' has no attribute {name!r}")

def __dir__():
    base = set(globals().keys())
    for mod in (_cu, _paths, _outline):
        try:
            base.update(dir(mod))
        except Exception:
            pass
    return sorted(base)