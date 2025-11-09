# tools/web_rag/__init__.py
from .search import web_search
from .ingest import (
    web_results_to_documents, web_page_json_to_documents,
    documents_to_chroma, add_web_pages_json_to_chroma,
    retrieve, clear_vector_store, ensure_vector_store_cleared_once,
    _default_chroma_dir,
)
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