# tools/web_rag/__init__.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # For type checkers only (avoid import-time side effects / circular imports)
    from typing import Callable, cast

    from .search import web_search as _web_search_tool
    from .ingest import (
        web_results_to_documents as web_results_to_documents,
        web_page_json_to_documents as web_page_json_to_documents,
        documents_to_chroma as documents_to_chroma,
        add_web_pages_json_to_chroma as add_web_pages_json_to_chroma,
        retrieve as _retrieve_tool,
        clear_vector_store as clear_vector_store,
        ensure_vector_store_cleared_once as ensure_vector_store_cleared_once,
        _default_chroma_dir as _default_chroma_dir,
    )

def _call_maybe_tool(obj: Any, *args: Any, **kwargs: Any) -> Any:
    """
    search/ingest에서 함수 대신 LangChain BaseTool 인스턴스를 내보내는 경우를 흡수.
    우선순위: invoke() -> run() -> (callable이면 직접 호출)
    """
    inv = getattr(obj, "invoke", None)
    if callable(inv):
        # LangChain Tool.invoke는 보통 단일 input만 안정적으로 받는다.
        # 따라서 (args, kwargs)를 "input"으로 정규화해서 전달한다.
        if kwargs:
            if args:
                # 보통 첫 positional은 query 같은 핵심 입력이므로 query로 보관
                payload = {"query": args[0], **kwargs}
            else:
                payload = dict(kwargs)
            return inv(payload)
        # kwargs가 없으면 기존처럼 단일 positional로 호출
        if len(args) == 1:
            return inv(args[0])
        if not args:
            return inv({})
        # 여러 positional은 안전하게 list로 감싸 전달
        return inv(list(args))
    run = getattr(obj, "run", None)
    if callable(run):
        # run도 툴 구현에 따라 단일 input만 받는 경우가 있어 invoke와 동일 정책 적용
        if kwargs:
            if args:
                payload = {"query": args[0], **kwargs}
            else:
                payload = dict(kwargs)
            return run(payload)
        if len(args) == 1:
            return run(args[0])
        if not args:
            return run({})
        return run(list(args))
    if callable(obj):
        return obj(*args, **kwargs)
    raise TypeError(f"Object is not callable and has no invoke/run: {type(obj)!r}")

def web_search(*args, **kwargs):
    from .search import web_search as _web_search
    return _call_maybe_tool(_web_search, *args, **kwargs)

def web_results_to_documents(*args, **kwargs):
    from .ingest import web_results_to_documents as _fn
    return _call_maybe_tool(_fn, *args, **kwargs)

def web_page_json_to_documents(*args, **kwargs):
    from .ingest import web_page_json_to_documents as _fn
    return _call_maybe_tool(_fn, *args, **kwargs)

def documents_to_chroma(*args, **kwargs):
    from .ingest import documents_to_chroma as _fn
    return _call_maybe_tool(_fn, *args, **kwargs)

def add_web_pages_json_to_chroma(*args, **kwargs):
    from .ingest import add_web_pages_json_to_chroma as _fn
    return _call_maybe_tool(_fn, *args, **kwargs)

def retrieve(*args, **kwargs):
    from .ingest import retrieve as _fn
    return _call_maybe_tool(_fn, *args, **kwargs)

def clear_vector_store(*args, **kwargs):
    from .ingest import clear_vector_store as _fn
    return _call_maybe_tool(_fn, *args, **kwargs)

def ensure_vector_store_cleared_once(*args, **kwargs):
    from .ingest import ensure_vector_store_cleared_once as _fn
    return _call_maybe_tool(_fn, *args, **kwargs)

def _default_chroma_dir(*args, **kwargs):
    from .ingest import _default_chroma_dir as _fn
    return _call_maybe_tool(_fn, *args, **kwargs)
__all__ = [
    "web_search", "web_results_to_documents", "web_page_json_to_documents",
    "documents_to_chroma", "add_web_pages_json_to_chroma", "retrieve",
    "clear_vector_store", "ensure_vector_store_cleared_once", "_default_chroma_dir",
]

import logging

# pdfminer 전역 로그 레벨 낮추기
for name in [
    "pdfminer",
    "pdfminer.psparser",
    "pdfminer.pdfparser",
    "pdfminer.pdfdocument",
    "pdfminer.pdfinterp",
    "pdfminer.pdfpage",
]:
    logging.getLogger(name).setLevel(logging.WARNING)