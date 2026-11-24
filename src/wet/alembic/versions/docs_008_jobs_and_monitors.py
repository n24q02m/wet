"""Add jobs, watches, and alerts tables for async research and URL monitoring.

Revision ID: docs_008_jobs_and_monitors
Revises: docs_007_project_context_sub
Create Date: 2026-11-24

W10 P8 (WET-35, WET-46, WET-48): adds persistent tables for async agent
research jobs and URL change monitoring watches/alerts, scoped by caller
namespace ``sub``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "docs_008_jobs_and_monitors"
down_revision: str | None = "docs_007_project_context_sub"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name = :n"),
        {"n": name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    if not _table_exists("jobs"):
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                sub TEXT NOT NULL DEFAULT 'default',
                kind TEXT NOT NULL DEFAULT 'research',
                status TEXT NOT NULL DEFAULT 'pending',
                query TEXT NOT NULL,
                params_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                evidence_json TEXT,
                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                completed_at REAL
            )
            """
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_sub_status ON jobs(sub, status, updated_at)"
        )

    if not _table_exists("watches"):
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS watches (
                id TEXT PRIMARY KEY,
                sub TEXT NOT NULL DEFAULT 'default',
                url TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL DEFAULT 3600,
                last_content TEXT,
                last_hash TEXT,
                last_checked_at REAL,
                created_at REAL NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(sub, url)
            )
            """
        )
        op.execute("CREATE INDEX IF NOT EXISTS idx_watches_sub ON watches(sub, url)")

    if not _table_exists("alerts"):
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                watch_id TEXT NOT NULL,
                sub TEXT NOT NULL DEFAULT 'default',
                url TEXT NOT NULL,
                change_status TEXT NOT NULL,
                change_ratio REAL NOT NULL DEFAULT 0.0,
                summary TEXT NOT NULL DEFAULT '',
                diff_text TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                FOREIGN KEY (watch_id) REFERENCES watches(id) ON DELETE CASCADE
            )
            """
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_watch_created ON alerts(watch_id, created_at DESC)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alerts")
    op.execute("DROP TABLE IF EXISTS watches")
    op.execute("DROP TABLE IF EXISTS jobs")
