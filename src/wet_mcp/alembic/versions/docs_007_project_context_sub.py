"""Namespaces ``project_context`` per caller (mode-3 isolation, spec §4 Q2).

Adds the ``sub`` column so the logical key becomes ``(sub, project_path)``:
one wet-mcp process serves N authenticated callers, and each caller holds
its own Cabinets lock for the same project path. Existing rows belong to
the shared mode-1/2 namespace and gain ``sub = 'default'`` via the column
default; their ``project_path`` was already unique, so the new unique index
builds cleanly on legacy shapes.

Idempotent: the column add is guarded by ``PRAGMA table_info``; the index
is ``CREATE UNIQUE INDEX IF NOT EXISTS``.

Revision ID: docs_007_project_context_sub
Revises: docs_006_version_index_state
Create Date: 2026-09-26
"""

from __future__ import annotations

import logging

from alembic import op

# Revision identifiers used by Alembic.
revision = "docs_007_project_context_sub"
down_revision = "docs_006_version_index_state"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Add ``project_context.sub`` + the unique (sub, project_path) index."""
    existing_cols = {
        row[0]
        for row in op.get_bind()
        .exec_driver_sql("SELECT name FROM pragma_table_info(?)", ("project_context",))
        .fetchall()
    }
    if "sub" not in existing_cols:
        op.execute(
            "ALTER TABLE project_context ADD COLUMN sub TEXT NOT NULL DEFAULT 'default'"
        )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_project_context_sub_path "
        "ON project_context(sub, project_path)"
    )


def downgrade() -> None:
    """Drop the unique index, then best-effort drop the ``sub`` column."""
    op.execute("DROP INDEX IF EXISTS idx_project_context_sub_path")
    try:
        op.execute("ALTER TABLE project_context DROP COLUMN sub")
    except Exception as e:
        # Best-effort: SQLite builds without DROP COLUMN support, or a table
        # that already lost the column, must not block the rollback. The
        # column has a constant default, so leaving it in place is harmless.
        logger.warning(f"docs_007 downgrade left sub column in place: {e}")
