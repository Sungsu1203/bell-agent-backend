# -*- coding: utf-8 -*-
import os, sys
from pathlib import Path
from typing import List
from pptx import Presentation
from langchain_core.documents import Document

# 프로젝트 내 도구 재사용
from tools.web_rag import (
    documents_to_chroma,
    retrieve,
    clear_vector_store,
    _default_chroma_dir,
)

def _shape_texts(shape) -> List[str]:
    out = []
    try:
        if getattr(shape, "has_text_frame", False) and shape.text_frame:
            txt = "\n".join(p.text for p in shape.text_frame.paragraphs if p.text)
            if txt.strip():
                out.append(txt.strip())
        elif getattr(shape, "has_table", False) and shape.table:
            tbl = shape.table
            for r in tbl.rows:
                for c in r.cells:
                    if c.text and c.text.strip():
                        out.append(c.text.strip())
        # 그룹 내부 재귀
        if hasattr(shape, "shapes"):
            for s in shape.shapes:
                out.extend(_shape_texts(s))
    except Exception:
        pass
    return out

def load_pptx_to_documents(pptx_path: str) -> List[Document]:
    prs = Presentation(pptx_path)
    docs: List[Document] = []
    p = Path(pptx_path).resolve()
    for i, slide in enumerate(prs.slides, start=1):
        texts = []
        for shp in slide.shapes:
            texts.extend(_shape_texts(shp))
        text = "\n".join(t for t in texts if t).strip()
        if not text:
            continue
        docs.append(Document(
            page_content=text,
            metadata={
                "title": p.name,
                "source": f"file://{p.as_posix()}#slide={i}",
                "slide": i,
            }
        ))
    return docs

def main():
    if len(sys.argv) < 2 and not os.getenv("PPTX_PATH"):
        print("Usage: python smoke_pptx_qa.py <path_to_pptx>  (or set PPTX_PATH)")
        sys.exit(2)

    pptx_path = Path(sys.argv[1] if len(sys.argv) >= 2 else os.getenv("PPTX_PATH")).expanduser()
    if not pptx_path.exists():
        print(f"File not found: {pptx_path}")
        sys.exit(2)

    ns = os.getenv("CHROMA_NAMESPACE", "pptx-test")
    pd = os.getenv("CHROMA_DIR") or _default_chroma_dir(ns)

    # 깨끗한 공간에서 시작
    clear_vector_store(namespace=ns, persist_directory=pd)

    docs = load_pptx_to_documents(str(pptx_path))
    n_src, n_chunks = documents_to_chroma(
        docs,
        namespace=ns,
        persist_directory=pd,
    )
    print(f"loaded: {n_src} docs, {n_chunks} chunks")
    print(f"persist dir = {pd}")

    # 간단 요약(슬라이드 첫 줄들)
    titles = []
    for d in docs:
        head = (d.page_content.splitlines() or [""])[0].strip()
        if head:
            titles.append(head)
    print("\n# Quick summary (slide headings, up to 10)")
    for t in titles[:10]:
        print(f"- {t}")

    # 질의 REPL
    print("\nType your question (enter to quit).")
    while True:
        q = input("Q> ").strip()
        if not q:
            break
        hits = retrieve.invoke({
            "query": q,
            "top_k": 5,
            "namespace": ns,
            "persist_directory": pd,
        })
        print(f"#hits={len(hits)}")
        for d in hits:
            slide = (d.metadata or {}).get("slide")
            snip = (d.page_content or "").replace("\n", " / ")
            print(f"- slide {slide}: {snip[:160]}...")

if __name__ == "__main__":
    main()
