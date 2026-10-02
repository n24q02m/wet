"""Extend libraries / versions / doc_chunks per spec §5.4.

Adds the Phase 2 Context7-level docs search columns:

* ``libraries``: ``canonical_name``, ``homepage``, ``github_url``,
  ``package_managers``, ``tier``, ``last_indexed_at``, ``total_versions``.
* ``versions``: ``release_date``, ``source_url``.
* ``doc_chunks``: ``section``, ``topic``, ``content_hash``, ``token_count``
  + composite index ``idx_doc_chunks_lib_ver_topic``.

The migration is *idempotent*: it inspects ``PRAGMA table_info(...)`` and
only adds columns / indexes that do not already exist. Pre-existing
``libraries`` rows are backfilled so:

* ``canonical_name = name``
* ``last_indexed_at = updated_at`` (best-effort recency anchor)
* ``tier`` defaults to 2 (on-demand) — Tier 1 warmup will explicitly
  upgrade curated entries to ``tier = 1``.

SQLite cannot drop columns without a table rebuild, so ``downgrade`` is a
no-op with a logged warning. The new columns are nullable / defaulted and
harmless to leave in place if rolling back to baseline.

Revision ID: docs_002_libraries
Revises: docs_001_baseline
Create Date: 2026-05-10
"""

from __future__ import annotations

import logging

from alembic import op

# Revision identifiers used by Alembic.
revision = "docs_002_libraries"
down_revision = "docs_001_baseline"
branch_labels = None
depends_on = None


logger = logging.getLogger("alembic.runtime.migration")


def _existing_columns(table: str) -> set[str]:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        "SELECT name FROM pragma_table_info(?)", (table,)
    ).fetchall()
    return {row[0] for row in rows}


def _existing_indexes(table: str) -> set[str]:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        "SELECT name FROM pragma_index_list(?)", (table,)
    ).fetchall()
    return {row[0] for row in rows}


def _add_column_if_missing(table: str, name: str, alter_sql: str) -> None:
    if name not in _existing_columns(table):
        op.execute(alter_sql)
    else:
        logger.info(f"docs_002: {table}.{name} already present, skipping")


def upgrade() -> None:
    """Add Phase 2 columns idempotently + backfill key fields."""
    # libraries
    _add_column_if_missing(
        "libraries",
        "canonical_name",
        "ALTER TABLE libraries ADD COLUMN canonical_name TEXT",
    )
    _add_column_if_missing(
        "libraries", "homepage", "ALTER TABLE libraries ADD COLUMN homepage TEXT"
    )
    _add_column_if_missing(
        "libraries", "github_url", "ALTER TABLE libraries ADD COLUMN github_url TEXT"
    )
    _add_column_if_missing(
        "libraries",
        "package_managers",
        "ALTER TABLE libraries ADD COLUMN package_managers TEXT",
    )
    _add_column_if_missing(
        "libraries",
        "tier",
        "ALTER TABLE libraries ADD COLUMN tier INTEGER NOT NULL DEFAULT 2",
    )
    _add_column_if_missing(
        "libraries",
        "last_indexed_at",
        "ALTER TABLE libraries ADD COLUMN last_indexed_at REAL",
    )
    _add_column_if_missing(
        "libraries",
        "total_versions",
        "ALTER TABLE libraries ADD COLUMN total_versions INTEGER NOT NULL DEFAULT 0",
    )

    # Backfill canonical_name + last_indexed_at for pre-existing rows.
    op.execute(
        "UPDATE libraries SET canonical_name = name WHERE canonical_name IS NULL"
    )
    op.execute(
        "UPDATE libraries SET last_indexed_at = updated_at "
        "WHERE last_indexed_at IS NULL"
    )

    # versions
    _add_column_if_missing(
        "versions", "release_date", "ALTER TABLE versions ADD COLUMN release_date REAL"
    )
    _add_column_if_missing(
        "versions", "source_url", "ALTER TABLE versions ADD COLUMN source_url TEXT"
    )

    # doc_chunks
    _add_column_if_missing(
        "doc_chunks", "section", "ALTER TABLE doc_chunks ADD COLUMN section TEXT"
    )
    _add_column_if_missing(
        "doc_chunks", "topic", "ALTER TABLE doc_chunks ADD COLUMN topic TEXT"
    )
    _add_column_if_missing(
        "doc_chunks",
        "content_hash",
        "ALTER TABLE doc_chunks ADD COLUMN content_hash TEXT",
    )
    _add_column_if_missing(
        "doc_chunks",
        "token_count",
        "ALTER TABLE doc_chunks ADD COLUMN token_count INTEGER",
    )

    if "idx_doc_chunks_lib_ver_topic" not in _existing_indexes("doc_chunks"):
        op.execute(
            "CREATE INDEX idx_doc_chunks_lib_ver_topic "
            "ON doc_chunks(library_id, version_id, topic)"
        )


def downgrade() -> None:
    """SQLite cannot drop columns without rebuilding the table.

    The new columns are nullable / defaulted and harmless to leave in place.
    """
    logger.warning(
        "docs_002 downgrade is a no-op: SQLite drop-column requires manual "
        "table rebuild. Phase 2 libraries / versions / doc_chunks columns "
        "left in place."
    )
