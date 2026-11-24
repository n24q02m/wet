"""Domain handler modules extracted from wet.server (WET-17)."""

from wet.handlers.config_handlers import config_status_providers
from wet.handlers.docs_handlers import handle_docs_audit, handle_docs_status
from wet.handlers.extract_handlers import (
    build_semantic_diff_result,
    handle_async_agent,
    handle_monitor,
)
from wet.handlers.search_handlers import search_meta_actions

__all__ = [
    "build_semantic_diff_result",
    "config_status_providers",
    "handle_async_agent",
    "handle_docs_audit",
    "handle_docs_status",
    "handle_monitor",
    "search_meta_actions",
]
