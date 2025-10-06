# tools/__init__.py  — clean, single-source exports

from .web_rag import (
    web_search,
    retrieve,
    web_results_to_documents,
    add_web_pages_json_to_chroma,
    web_page_json_to_documents,
)

__all__ = [
    "web_search",
    "retrieve",
    "web_results_to_documents",
    "add_web_pages_json_to_chroma",
    "web_page_json_to_documents",
]
