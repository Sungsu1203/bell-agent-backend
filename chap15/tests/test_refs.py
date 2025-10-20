import os
from langchain_core.documents import Document
from utils.refs import attach_auto_citations

def _state():
    return {"references":{"docs":[
        Document(page_content="a", metadata={"url":"https://iea.org","title":"IEA"}),
        Document(page_content="b", metadata={"url":"https://oecd.org"}),
    ]}}

def test_footer_mode_inserts_footnotes(monkeypatch):
    monkeypatch.setenv("AUTO_FOOTNOTE_MODE","footer")
    out = attach_auto_citations("라인1\n라인2", _state())
    assert "### 참고 문헌 / 각주" in out
    assert "[^1]:" in out

def test_domain_mode_appends_inline_marker(monkeypatch):
    monkeypatch.setenv("AUTO_FOOTNOTE_MODE","domain")
    text = "IEA 보고서 참고."
    out = attach_auto_citations(text, _state())
    assert "### 참고 문헌 / 각주" in out
    assert "[^" in out  # 라인 끝에 번호 붙었는지
