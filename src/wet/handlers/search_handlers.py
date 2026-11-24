"""Search meta-action handlers (WET-17, WET-26, WET-41)."""

from __future__ import annotations

from typing import Any

from wet.handlers.docs_handlers import handle_docs_audit, handle_docs_status


async def search_meta_actions(
    action: str,
    *,
    docs_db: Any,
    project_path: str | None = None,
    sub: str = "default",
) -> dict[str, Any] | None:
    """Dispatch non-query docs inspection actions, or return None if unhandled."""
    if action == "docs_status":
        return await handle_docs_status(docs_db)
    if action == "docs_audit":
        return await handle_docs_audit(docs_db, project_path, sub=sub)
    return None
