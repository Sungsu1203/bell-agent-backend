# tests/test_rag_expression.py
import pytest
from rag_expression import extract_write_title, is_outline_display, extract_new_topic_title

def test_extract_write_title():
    assert extract_write_title("write: 서문") == "서문"
    assert extract_write_title("작성: 3장 기술") == "3장 기술"
    assert extract_write_title([{"type":"text","text":"집필: 결론"}]) == "결론"

def test_is_outline_display():
    for s in ["목차 보여줘", "outline show", "책 목차"]:
        assert is_outline_display(s)

def test_extract_new_topic_title():
    assert extract_new_topic_title("새 프로젝트: 샘플 북") == "샘플 북"
    assert extract_new_topic_title("switch topic: EV Report") == "EV Report"
