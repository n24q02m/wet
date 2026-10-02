"""Separate "metadata seeded" from "docs indexed" on ``libraries``.

Adds the nullable ``libraries.metadata_seeded_at`` column and repairs the
rows that the previous behaviour mislabelled.

Before this revision ``DocsDB.upsert_library`` stamped ``last_indexed_at``
on every write, including the metadata-only Tier 1 warmup seed, which
indexes nothing. A database could therefore claim 50 freshly indexed
libraries while holding zero versions and zero chunks — and the warmup's
own 7-day freshness gate read that same column, so it was satisfied by the
very write it was meant to guard.

The data repair keys off ownership of an indexed version: a library with
no ``versions`` row at ``status = 'indexed'`` was never indexed, so its
``last_indexed_at`` can only have come from the old seed stamp (or from the
``docs_002`` ``last_indexed_at = updated_at`` backfill). Those stamps move
to ``metadata_seeded_at``; genuinely indexed libraries keep theirs.

Idempotent: the column add is guarded by ``PRAGMA table_info`` and the
repair matches nothing on a second run (``last_indexed_at`` is already
NULL for the affected rows).

Revision ID: docs_005_metadata_seeded_at
Revises: docs_004_chunk_summaries
Create Date: 2026-08-01
"""

from __future__ import annotations

import logging

from alembic import op

# Revision identifiers used by Alembic.
revision = "docs_005_metadata_seeded_at"
down_revision = "docs_004_chunk_summaries"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Add ``metadata_seeded_at`` and relabel seed-only index stamps."""
    existing_cols = {
        row[0]
        for row in op.get_bind()
        .exec_driver_sql("SELECT name FROM pragma_table_info(?)", ("libraries",))
        .fetchall()
    }
    if "metadata_seeded_at" not in existing_cols:
        op.execute("ALTER TABLE libraries ADD COLUMN metadata_seeded_at REAL")

    op.execute(
        """
        UPDATE libraries
           SET metadata_seeded_at = COALESCE(metadata_seeded_at, last_indexed_at),
               last_indexed_at = NULL
         WHERE last_indexed_at IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM versions v
                WHERE v.library_id = libraries.id AND v.status = 'indexed'
           )
        """
    )


def downgrade() -> None:
    """No-op: dropping the column would discard the seed timestamps.

    The relabelled ``last_indexed_at`` values cannot be reconstructed, and
    the added column is nullable, so leaving it in place is harmless when
    rolling back to ``docs_004_chunk_summaries``.
    """
    logger.warning(
        "docs_005_metadata_seeded_at downgrade is a no-op; "
        "libraries.metadata_seeded_at is left in place"
    )
