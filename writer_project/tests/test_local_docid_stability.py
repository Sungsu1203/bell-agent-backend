from pathlib import Path
from tools.local_rag import _build_local_source
from tools.web_rag.utils import make_doc_id


def test_doc_id_stable_for_local_source(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_text("hello")

    src = _build_local_source(p, part="Slide", index=1, chunk=0)

    ver = "1700000000"
    text = "hello world"

    counter1 = {}
    id1 = make_doc_id(src, ver, text, counter=counter1, max_id_chars=128)

    counter2 = {}
    id2 = make_doc_id(src, ver, text, counter=counter2, max_id_chars=128)

    assert id1 == id2


def test_doc_id_not_affected_by_argument_order(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_text("hello")

    src1 = _build_local_source(p, part="Slide", index=1, chunk=0)
    src2 = _build_local_source(p, chunk=0, index=1, part="Slide")

    ver = "1700000000"
    text = "hello world"

    counter1 = {}
    id1 = make_doc_id(src1, ver, text, counter=counter1, max_id_chars=128)

    counter2 = {}
    id2 = make_doc_id(src2, ver, text, counter=counter2, max_id_chars=128)

    assert id1 == id2