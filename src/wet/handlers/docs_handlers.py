"""Docs status and project dependency audit handlers (WET-17, WET-26, WET-41)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from wet.sources.project_lock import docs_audit, docs_status


async def handle_docs_status(docs_db: Any) -> dict[str, Any]:
    """Return local docs index summary across libraries, versions, and chunks."""
    if docs_db is None:
        return {"error": "Error: Docs database not initialized"}
    return await asyncio.to_thread(docs_status, docs_db)


async def handle_docs_audit(
    docs_db: Any,
    project_path: str | None,
    *,
    sub: str = "default",
) -> dict[str, Any]:
    """Audit project manifests and lockfiles against the local docs database."""
    if not project_path:
        return {
            "error": (
                "Error: project_path is required for docs_audit. "
                'Example: search(action="docs_audit", project_path="/repo/my-app")'
            )
        }
    if docs_db is None:
        return {"error": "Error: Docs database not initialized"}
    try:
        return await asyncio.to_thread(docs_audit, docs_db, Path(project_path), sub=sub)
    except FileNotFoundError as exc:
        return {"error": f"Error: project_path does not exist: {exc}"}
