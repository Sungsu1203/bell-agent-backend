import os
import json
from pathlib import Path
import pytest

from tools.local_rag import build_webjson_from_local
from tools.web_rag import add_web_pages_json_to_chroma, retrieve

def test_e2e_local_ingest_then_optional_retrieve(tmp_path, monkeypatch):
    # 1) 데모 파일 준비
    demo = tmp_path / "demo_data"
    demo.mkdir(parents=True, exist_ok=True)

    (demo / "policy_kr.txt").write_text(
        "Korea EV battery EPR policy: certification expected from 2027. "
        "Recycling targets increase; extended producer responsibility applies.",
        encoding="utf-8",
    )
    (demo / "memo.md").write_text(
        "# Memo\nIndicative volumes 2024→2027. Focus on retired packs and recycled flows.",
        encoding="utf-8",
    )

    # 2) web.json 생성
    out_dir = tmp_path / "resources" / "testtopic"
    out_path = build_webjson_from_local(
        globs=[str(demo / "*.txt"), str(demo / "*.md")],
        out_dir=str(out_dir),
    )
    assert Path(out_path).exists(), "web.json 이 생성되어야 합니다."

    with open(out_path, encoding="utf-8") as f:
        items = json.load(f)
    assert len(items) == 2, "데모 2개 파일 → 2개 아이템이어야 함"
    assert all(it.get("content") for it in items), "content 가 비면 안 됨"

    # 3) (선택) 온라인: Chroma 색인 + 벡터 검색 (OPENAI_API_KEY 필요)
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY 미설정 → 색인/검색 단계는 건너뜁니다.")

    ns = "e2e-" + os.urandom(4).hex()
    persist_dir = str(tmp_path / "chroma")
    os.environ["CHROMA_NAMESPACE"] = ns
    os.environ["CHROMA_DIR"] = persist_dir

    _orig, chunk_count = add_web_pages_json_to_chroma(
        out_path, namespace=ns, persist_directory=persist_dir
    )
    assert int(chunk_count or 0) > 0, "색인된 청크 수가 0보다 커야 함"

    # 질의에 정책 키워드 포함 (policy/EPR/2027)
    docs = retrieve.invoke({
        "query": "Korea EPR policy 2027",
        "namespace": ns,
        "persist_directory": persist_dir,
        "top_k": 5
    })
    # 간단한 매칭 확인
    body = " ".join((getattr(d, "page_content", "") or "") for d in docs)
    assert ("EPR" in body) or ("policy" in body.lower()), "검색 결과에 정책 텍스트가 포함되어야 함"
