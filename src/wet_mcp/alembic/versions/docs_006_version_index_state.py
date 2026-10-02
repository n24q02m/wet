"""Record indexing-attempt outcomes on ``versions``.

Adds the nullable ``index_state`` / ``index_error`` / ``index_state_at``
columns so a background indexing attempt leaves something durable behind.

Before this revision the only trace of a failed index was a ``logger.error``
inside the process that failed, so a store reporting zero chunks could equally
be one that was never asked to index, one still working, one that failed
permanently, and one that succeeded on a page with no extractable content.

``index_state`` is deliberately separate from the existing ``status`` column:
``status`` gates what ``get_best_version`` serves, so a version has to be able
to keep serving its old chunks (``status = 'indexed'``) while its most recent
re-index attempt reads ``failed``.

Idempotent: each column add is guarded by ``PRAGMA table_info``.

Revision ID: docs_006_version_index_state
Revises: docs_005_metadata_seeded_at
Create Date: 2026-08-03
"""

from __future__ import annotations

import logging

from alembic import op

# Revision identifiers used by Alembic.
revision = "docs_006_version_index_state"
down_revision = "docs_005_metadata_seeded_at"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Add the three nullable indexing-state columns to ``versions``."""
    existing_cols = {
        row[0]
        for row in op.get_bind()
        .exec_driver_sql("SELECT name FROM pragma_table_info(?)", ("versions",))
        .fetchall()
    }
    if "index_state" not in existing_cols:
        op.execute("ALTER TABLE versions ADD COLUMN index_state TEXT")
    if "index_error" not in existing_cols:
        op.execute("ALTER TABLE versions ADD COLUMN index_error TEXT")
    if "index_state_at" not in existing_cols:
        op.execute("ALTER TABLE versions ADD COLUMN index_state_at REAL")


def downgrade() -> None:
    """No-op: dropping the columns would discard the only failure record.

    The columns are nullable and no code path requires them to be absent, so
    leaving them in place is harmless when rolling back to
    ``docs_005_metadata_seeded_at``.
    """
    logger.warning(
        "docs_006_version_index_state downgrade is a no-op; "
        "versions.index_state / index_error / index_state_at are left in place"
    )
