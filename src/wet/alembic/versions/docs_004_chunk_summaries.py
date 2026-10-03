"""Phase 3 schema: nullable per-chunk LLM summary columns.

Per spec section 5.4 + Phase 3 plan task 6. Adds two nullable TEXT
columns to ``doc_chunks`` so future LLM-enhanced docs (NICE per spec
section 4.3) can attach a per-chunk summary plus the provider that
produced it without re-running the indexing pipeline. No Phase 3 task
populates these columns; the migration is schema-ready only.

Idempotent on re-run via ``ADD COLUMN IF NOT EXISTS`` (SQLite >= 3.35);
backward-compatible because both columns default to NULL.

Revision ID: docs_004_chunk_summaries
Revises: docs_003_project_context
Create Date: 2026-05-10
"""

from __future__ import annotations

from alembic import op

# Revision identifiers used by Alembic.
revision = "docs_004_chunk_summaries"
down_revision = "docs_003_project_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable ``summary`` + ``summary_provider`` to ``doc_chunks``."""
    # SQLite ALTER TABLE ADD COLUMN does not have IF NOT EXISTS in older
    # versions; we guard via PRAGMA introspection so re-running the
    # migration on an already-upgraded DB is a no-op. PRAGMA table_info
    # returns rows shaped as (cid, name, type, notnull, dflt_value, pk).
    existing_cols = {
        row[0]
        for row in op.get_bind()
        .exec_driver_sql("SELECT name FROM pragma_table_info(?)", ("doc_chunks",))
        .fetchall()
    }
    if "summary" not in existing_cols:
        op.execute("ALTER TABLE doc_chunks ADD COLUMN summary TEXT")
    if "summary_provider" not in existing_cols:
        op.execute("ALTER TABLE doc_chunks ADD COLUMN summary_provider TEXT")


def downgrade() -> None:
    """Drop ``summary`` + ``summary_provider`` from ``doc_chunks``.

    SQLite < 3.35 does not support DROP COLUMN; on those versions the
    downgrade is a no-op (data is left in place but unused). On modern
    SQLite (>= 3.35) we drop both columns cleanly.
    """
    try:
        op.execute("ALTER TABLE doc_chunks DROP COLUMN summary_provider")
        op.execute("ALTER TABLE doc_chunks DROP COLUMN summary")
    except Exception:  # pragma: no cover - SQLite < 3.35 fallback
        pass
