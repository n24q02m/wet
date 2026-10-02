"""Baseline revision: lock existing wet-mcp docs.db schema.

This revision is intentionally a no-op for already-stamped/legacy databases.
It exists to anchor the migration chain at the schema produced by
``DocsDB._create_*_table`` prior to Alembic adoption:

  * ``libraries`` (id PK, name, docs_url, registry, description,
    created_at, updated_at, discovery_version)
  * ``versions`` (id PK, library_id FK, version, docs_url, indexed_at,
    page_count, chunk_count, status, UNIQUE(library_id, version))
  * ``doc_chunks`` (id PK, version_id FK, library_id FK, url, title,
    chunk_index, content, heading_path, created_at)
  * ``doc_chunks_fts`` (FTS5 virtual table content-synced to doc_chunks)
  * Triggers ``chunks_ai`` / ``chunks_ad`` / ``chunks_au``
  * ``doc_chunks_vec`` (sqlite-vec virtual table — created lazily at
    runtime by ``DocsDB._create_vector_table`` because it depends on the
    extension being loaded)

For a fresh database, the existing ``DocsDB._create_tables`` already runs
``CREATE TABLE IF NOT EXISTS`` ahead of the migration runner, so this
baseline only needs to ensure the same shape exists. We use raw SQL with
``CREATE TABLE IF NOT EXISTS`` so the migration is safe to apply on both
fresh and pre-Alembic databases without conflict.

Revision ID: docs_001_baseline
Revises:
Create Date: 2026-05-10
"""

from __future__ import annotations

from alembic import op

# Revision identifiers used by Alembic.
revision = "docs_001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Idempotent baseline create: matches DocsDB._create_*_table SQL exactly."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS libraries (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            docs_url TEXT,
            registry TEXT,
            description TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            discovery_version INTEGER DEFAULT 0
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_libraries_name ON libraries(name)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS versions (
            id TEXT PRIMARY KEY,
            library_id TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT 'latest',
            docs_url TEXT,
            indexed_at REAL,
            page_count INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (library_id) REFERENCES libraries(id) ON DELETE CASCADE,
            UNIQUE(library_id, version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS doc_chunks (
            id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            library_id TEXT NOT NULL,
            url TEXT,
            title TEXT,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            content TEXT NOT NULL,
            heading_path TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (version_id) REFERENCES versions(id) ON DELETE CASCADE,
            FOREIGN KEY (library_id) REFERENCES libraries(id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_version ON doc_chunks(version_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_ver_url_idx "
        "ON doc_chunks(version_id, url, chunk_index)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_library ON doc_chunks(library_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chunks_url_order "
        "ON doc_chunks(url, version_id, chunk_index)"
    )

    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts
        USING fts5(
            id UNINDEXED,
            content,
            title,
            heading_path,
            content=doc_chunks,
            content_rowid=rowid,
            tokenize='porter unicode61'
        )
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON doc_chunks BEGIN
            INSERT INTO doc_chunks_fts(rowid, id, content, title, heading_path)
            VALUES (new.rowid, new.id, new.content, new.title, new.heading_path);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON doc_chunks BEGIN
            INSERT INTO doc_chunks_fts(doc_chunks_fts, rowid, id, content, title, heading_path)
            VALUES ('delete', old.rowid, old.id, old.content, old.title, old.heading_path);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON doc_chunks BEGIN
            INSERT INTO doc_chunks_fts(doc_chunks_fts, rowid, id, content, title, heading_path)
            VALUES ('delete', old.rowid, old.id, old.content, old.title, old.heading_path);
            INSERT INTO doc_chunks_fts(rowid, id, content, title, heading_path)
            VALUES (new.rowid, new.id, new.content, new.title, new.heading_path);
        END
        """
    )


def downgrade() -> None:
    """No-op: baseline is the earliest schema state."""
    return None
