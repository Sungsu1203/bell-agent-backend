from pathlib import Path
from tools.local_rag import _build_local_source

def test_fragment_order_is_stable(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_text("dummy")

    src1 = _build_local_source(p, part="Slide", index=1, chunk=0)
    src2 = _build_local_source(p, chunk=0, index=1, part="Slide")

    # 동일한 인자 값이면 호출 순서가 달라도 결과 동일해야 함
    assert src1 == src2

    # fragment 순서가 part → index → chunk 인지 확인
    assert "#part=Slide&index=1&chunk=0" in src1