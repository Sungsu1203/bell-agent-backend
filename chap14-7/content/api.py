# content/api.py  ✅ (얇은 re-export 전용)
from content_utils import (
    save_md_draft, save_chapter, save_section, read_draft,
    list_draft_paths, rename_draft_title, move_draft_between_topics, merge_drafts,
)
from utils.text_utils import slugify, section_slugify
from utils.outline import (
    read_outline, save_outline, parse_outline_headings, list_outline_headings, next_unwritten_title
)
from core.paths import (
    get_content_dir, chapter_filepath, section_filepath, path_for_title,
    get_outline_dir, outline_path, is_written, _coerce_mode
)
__all__ = [
    "slugify","section_slugify",
    "get_content_dir","chapter_filepath","section_filepath","path_for_title",
    "get_outline_dir","outline_path","is_written","_coerce_mode",
    "read_outline","save_outline","parse_outline_headings","list_outline_headings","next_unwritten_title",
    "save_md_draft","save_chapter","save_section","read_draft",
    "list_draft_paths","rename_draft_title","move_draft_between_topics","merge_drafts",
]