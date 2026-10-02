"""Cabinets-style project isolation table per spec section 5.4.

Adds ``project_context`` table that stores per-project locked library set
so ``docs_query`` invocations from inside a project filter to the lock
list (Cabinets behaviour).

Schema:

* ``project_path`` TEXT PRIMARY KEY — absolute project root.
* ``locked_libraries`` TEXT NOT NULL — JSON-encoded list of
  ``{"id": <library_id>, "version": <version-or-spec>}``.
* ``created_at`` REAL NOT NULL.
* ``last_used_at`` REAL NOT NULL.
* Index ``idx_project_context_last_used`` for LRU eviction queries.

Idempotent via ``CREATE TABLE IF NOT EXISTS``. Downgrade drops the
table cleanly (no FK from other tables references it).

Revision ID: docs_003_project_context
Revises: docs_002_libraries
Create Date: 2026-05-10
"""

from __future__ import annotations

from alembic import op

# Revision identifiers used by Alembic.
revision = "docs_003_project_context"
down_revision = "docs_002_libraries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create ``project_context`` table + LRU index."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_context (
            project_path TEXT PRIMARY KEY,
            locked_libraries TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_used_at REAL NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_context_last_used "
        "ON project_context(last_used_at)"
    )


def downgrade() -> None:
    """Drop ``project_context`` + LRU index."""
    op.execute("DROP INDEX IF EXISTS idx_project_context_last_used")
    op.execute("DROP TABLE IF EXISTS project_context")
