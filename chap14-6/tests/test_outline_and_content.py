from tempfile import TemporaryDirectory
from utils.outline import save_outline, read_outline, list_outline_headings
from core.paths import path_for_title, is_written
from content_utils import save_md_draft, read_draft
from core.config import DOC_MODE

def test_outline_rw_and_headings():
    with TemporaryDirectory() as tmp:
        body = "# A\n## B"
        fname = "outline_report.md" if DOC_MODE=="report" else "outline_book.md"
        save_outline(body, filename=fname, root_dir=tmp, topic_slug="t", mode=DOC_MODE)
        text, p = read_outline(filename=fname, root_dir=tmp, topic_slug="t", mode=DOC_MODE)
        assert p is not None and p.exists()
        heads = list_outline_headings(text)
        assert heads == ["A","B"]

def test_draft_save_and_read():
    with TemporaryDirectory() as tmp:
        title = "테스트 초안"
        path = save_md_draft(title, "hello", mode=DOC_MODE, root_dir=tmp, topic_slug="t")
        assert is_written(title, mode=DOC_MODE, root_dir=tmp, topic_slug="t")
        text, p = read_draft(title, mode=DOC_MODE, root_dir=tmp, topic_slug="t")
        assert p.exists() and text.strip()=="hello"
