"""Tests for Alembic auto-migrate-on-startup runner.

Covers:

* baseline migration is idempotent (running ``alembic upgrade head`` twice
  on a fresh DB is a no-op the second time);
* ``run_migrations_on_startup`` stamps an unstamped DB without applying any
  forward migration when current == head after stamp;
* backup file is created when a real upgrade would run;
* docs_002_libraries forward migration adds the spec §5.4 columns and
  preserves existing rows;
* docs_003_project_context creates the Cabinets table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from wet_mcp.migrations import (
    _ALEMBIC_INI_PATH,
    _ALEMBIC_SCRIPT_LOCATION,
    _read_alembic_version,
    run_migrations_on_startup,
)


def _make_alembic_cfg(db_path: Path) -> Config:
    cfg = Config(str(_ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.resolve().as_posix()}")
    return cfg


def _table_columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM pragma_table_info(?)", (table,)
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def _table_exists(db_path: Path, table: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def _has_revision(rev_id: str) -> bool:
    """Return True when the named Alembic revision file exists in alembic/versions."""
    versions_dir = _ALEMBIC_SCRIPT_LOCATION / "versions"
    return any(p.stem.startswith(rev_id) for p in versions_dir.glob("*.py"))


def test_baseline_migration_idempotent(tmp_path: Path) -> None:
    """alembic upgrade head twice on fresh DB == no schema diff second run."""
    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)

    command.upgrade(cfg, "docs_001_baseline")
    rev_after_first = _read_alembic_version(db_path)

    command.upgrade(cfg, "docs_001_baseline")
    rev_after_second = _read_alembic_version(db_path)

    assert rev_after_first == rev_after_second == "docs_001_baseline"
    # Baseline tables present
    assert _table_exists(db_path, "libraries")
    assert _table_exists(db_path, "versions")
    assert _table_exists(db_path, "doc_chunks")
    assert _table_exists(db_path, "doc_chunks_fts")


def test_run_migrations_on_startup_stamps_fresh_db(tmp_path: Path) -> None:
    """Fresh DB created by DocsDB.__init__ → runner stamps + upgrades to head.

    Mimics the real production sequence: ``DocsDB._create_tables`` runs
    first (CREATE TABLE IF NOT EXISTS for libraries / versions / doc_chunks
    + FTS5), then the runner stamps the baseline and applies any forward
    migrations to head.
    """
    db_path = tmp_path / "docs.db"

    # Simulate DocsDB._create_tables having already run by applying the
    # baseline-shape DDL via Alembic itself (without stamping). We then
    # delete alembic_version so the runner observes an "unstamped" DB.
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "docs_001_baseline")
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE IF EXISTS alembic_version")
    conn.commit()
    conn.close()

    run_migrations_on_startup(db_path)

    # alembic_version table now present + populated; DB ends at head.
    rev = _read_alembic_version(db_path)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    assert rev == head


def test_run_migrations_on_startup_creates_backup_when_upgrading(
    tmp_path: Path,
) -> None:
    """When an actual forward migration would run, a .bak.<ts> file appears."""
    if not _has_revision("docs_002_libraries"):
        pytest.skip("docs_002_libraries not yet created")

    db_path = tmp_path / "docs.db"

    # Apply only baseline so the runner has work to do (head > baseline).
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "docs_001_baseline")

    # Insert a marker row so we can verify the backup is a real copy.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO libraries (id, name, created_at, updated_at) "
        "VALUES ('marker', 'marker-lib', 1.0, 1.0)"
    )
    conn.commit()
    conn.close()

    run_migrations_on_startup(db_path)

    backups = list(tmp_path.glob("docs.db.bak.*"))
    assert backups, "Expected a docs.db.bak.<ts> file from backup-before-migrate"


def test_002_adds_libraries_columns(tmp_path: Path) -> None:
    """docs_002 adds tier/last_indexed_at/package_managers/etc."""
    if not _has_revision("docs_002_libraries"):
        pytest.skip("docs_002_libraries not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "docs_001_baseline")

    # Seed pre-existing rows on the v1 schema.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO libraries (id, name, docs_url, registry, description, "
        "created_at, updated_at, discovery_version) "
        "VALUES ('lib1', 'react', 'https://react.dev', 'npm', 'react lib', "
        "1.0, 2.0, 1)"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "docs_002_libraries")

    cols = _table_columns(db_path, "libraries")
    for required in (
        "canonical_name",
        "homepage",
        "github_url",
        "package_managers",
        "tier",
        "last_indexed_at",
        "total_versions",
    ):
        assert required in cols, f"Missing column {required} in libraries"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM libraries WHERE id = 'lib1'").fetchone()
    conn.close()
    assert row is not None
    assert row["canonical_name"] == "react"  # backfill from name
    assert row["last_indexed_at"] == 2.0  # backfill from updated_at
    assert row["tier"] == 2  # default for pre-existing rows
    assert row["total_versions"] == 0  # default


def test_002_adds_versions_columns(tmp_path: Path) -> None:
    """docs_002 adds release_date + source_url to versions."""
    if not _has_revision("docs_002_libraries"):
        pytest.skip("docs_002_libraries not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "docs_001_baseline")

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO libraries (id, name, created_at, updated_at) "
        "VALUES ('lib1', 'react', 1.0, 2.0)"
    )
    conn.execute(
        "INSERT INTO versions (id, library_id, version, status, "
        "page_count, chunk_count) "
        "VALUES ('v1', 'lib1', '18.0.0', 'indexed', 5, 50)"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "docs_002_libraries")

    cols = _table_columns(db_path, "versions")
    assert "release_date" in cols
    assert "source_url" in cols

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM versions WHERE id = 'v1'").fetchone()
    conn.close()
    assert row is not None
    assert row["page_count"] == 5  # preserved
    assert row["chunk_count"] == 50  # preserved


def test_002_adds_doc_chunks_columns(tmp_path: Path) -> None:
    """docs_002 adds section/topic/content_hash/token_count to doc_chunks."""
    if not _has_revision("docs_002_libraries"):
        pytest.skip("docs_002_libraries not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "docs_002_libraries")

    cols = _table_columns(db_path, "doc_chunks")
    for required in ("section", "topic", "content_hash", "token_count"):
        assert required in cols, f"Missing column {required} in doc_chunks"


def test_003_creates_project_context_table(tmp_path: Path) -> None:
    """docs_003 creates Cabinets project_context table."""
    if not _has_revision("docs_003_project_context"):
        pytest.skip("docs_003_project_context not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "head")

    assert _table_exists(db_path, "project_context")
    cols = _table_columns(db_path, "project_context")
    for required in ("project_path", "locked_libraries", "created_at", "last_used_at"):
        assert required in cols, f"Missing column {required} in project_context"


def test_alembic_version_advances_through_chain(tmp_path: Path) -> None:
    """Sequential upgrade chain: baseline → 002 → 003 → 004 lands at head."""
    if not _has_revision("docs_003_project_context"):
        pytest.skip("docs_003_project_context not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)

    command.upgrade(cfg, "docs_001_baseline")
    assert _read_alembic_version(db_path) == "docs_001_baseline"

    command.upgrade(cfg, "docs_002_libraries")
    assert _read_alembic_version(db_path) == "docs_002_libraries"

    command.upgrade(cfg, "docs_003_project_context")
    assert _read_alembic_version(db_path) == "docs_003_project_context"

    if _has_revision("docs_004_chunk_summaries"):
        command.upgrade(cfg, "head")
        assert (
            _read_alembic_version(db_path)
            == ScriptDirectory.from_config(cfg).get_current_head()
        )


def test_004_adds_summary_columns(tmp_path: Path) -> None:
    """docs_004 adds nullable summary + summary_provider to doc_chunks."""
    if not _has_revision("docs_004_chunk_summaries"):
        pytest.skip("docs_004_chunk_summaries not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "head")

    cols = _table_columns(db_path, "doc_chunks")
    assert "summary" in cols, "Missing column summary in doc_chunks"
    assert "summary_provider" in cols, "Missing column summary_provider in doc_chunks"


def test_004_preserves_existing_chunk_rows(tmp_path: Path) -> None:
    """Backward compat: pre-existing rows have NULL for the new columns."""
    if not _has_revision("docs_004_chunk_summaries"):
        pytest.skip("docs_004_chunk_summaries not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)

    # Land at docs_003 first, insert a row, then upgrade through 004.
    command.upgrade(cfg, "docs_003_project_context")
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO doc_chunks (id, version_id, library_id, url, title, "
        "chunk_index, content, heading_path, created_at) "
        "VALUES ('c1', 'v1', 'lib1', 'https://x', 't', 0, 'body', '', 0.0)"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM doc_chunks WHERE id = 'c1'").fetchone()
    conn.close()
    assert row is not None
    assert row["summary"] is None
    assert row["summary_provider"] is None
    assert row["content"] == "body"  # untouched


def test_004_idempotent_on_rerun(tmp_path: Path) -> None:
    """Re-running docs_004 upgrade on an already-upgraded DB is a no-op."""
    if not _has_revision("docs_004_chunk_summaries"):
        pytest.skip("docs_004_chunk_summaries not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "head")
    # Stamp back to 003 then re-run; column add must be a no-op.
    command.stamp(cfg, "docs_003_project_context")
    command.upgrade(cfg, "head")  # must not raise "duplicate column"
    cols = _table_columns(db_path, "doc_chunks")
    assert "summary" in cols
    assert "summary_provider" in cols


def test_full_v1_to_v2_round_trip(tmp_path: Path) -> None:
    """Phase 3 Task 9 regression: v1.x.y (docs_001) -> v2.0.0 (head)."""
    if not _has_revision("docs_004_chunk_summaries"):
        pytest.skip("docs_004_chunk_summaries not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)

    # Land at docs_001 (v1.x.y baseline) and seed representative rows so
    # we can verify the data survives the full chain.
    command.upgrade(cfg, "docs_001_baseline")
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO libraries (id, name, docs_url, registry, description, "
        "created_at, updated_at, discovery_version) "
        "VALUES ('lib-pre', 'Pre', 'http://x', 'github', 'd', 0.0, 0.0, 0)"
    )
    conn.execute(
        "INSERT INTO versions (id, library_id, version, status, "
        "page_count, chunk_count) "
        "VALUES ('ver-pre', 'lib-pre', '1.0.0', 'indexed', 1, 1)"
    )
    conn.execute(
        "INSERT INTO doc_chunks (id, version_id, library_id, url, title, "
        "chunk_index, content, heading_path, created_at) "
        "VALUES ('c-pre', 'ver-pre', 'lib-pre', 'https://x', 't', 0, 'b', '', 0.0)"
    )
    conn.commit()
    conn.close()

    # Now run the production auto-migrate-on-startup runner end-to-end.
    run_migrations_on_startup(db_path)

    # Version stamp advanced to head.
    assert (
        _read_alembic_version(db_path)
        == ScriptDirectory.from_config(cfg).get_current_head()
    )

    # Pre-existing rows are preserved across all forward migrations.
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        lib_count = conn.execute("SELECT COUNT(*) FROM libraries").fetchone()[0]
        ver_count = conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0]
        chunk_row = conn.execute(
            "SELECT * FROM doc_chunks WHERE id = 'c-pre'"
        ).fetchone()
    finally:
        conn.close()
    assert lib_count == 1
    assert ver_count == 1
    assert chunk_row is not None
    assert chunk_row["content"] == "b"
    # Phase 3 columns are present and NULL for the pre-existing row.
    assert chunk_row["summary"] is None
    assert chunk_row["summary_provider"] is None

    # Backup file was created when the runner saw current_rev != head.
    backups = list(tmp_path.glob("docs.db.bak.*"))
    assert backups, "auto-migrate-on-startup must snapshot before upgrade"


def test_db_add_chunks_writes_summary_columns_when_present(tmp_path: Path) -> None:
    """db.DocsDB.add_chunks must write summary + summary_provider when set."""
    if not _has_revision("docs_004_chunk_summaries"):
        pytest.skip("docs_004_chunk_summaries not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "head")

    # Seed library + version rows that add_chunks expects to reference.
    # Baseline columns: libraries(id, name, docs_url, registry, description,
    # created_at, updated_at, discovery_version); versions(id, library_id,
    # version, status, page_count, chunk_count, docs_url, indexed_at).
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO libraries (id, name, docs_url, registry, description, "
        "created_at, updated_at, discovery_version) "
        "VALUES ('lib1', 'Lib', 'http://x', 'github', 'desc', 0.0, 0.0, 0)"
    )
    conn.execute(
        "INSERT INTO versions (id, library_id, version, status, "
        "page_count, chunk_count) "
        "VALUES ('v1', 'lib1', '1.0.0', 'indexed', 0, 0)"
    )
    conn.commit()
    conn.close()

    from wet_mcp.db import DocsDB

    db = DocsDB(db_path=db_path)
    chunks = [
        {
            "url": "https://x/page",
            "title": "Page",
            "content": "body",
            "summary": "Short overview",
            "summary_provider": "gemini-3-flash-preview",
        }
    ]
    db.add_chunks(version_id="v1", library_id="lib1", chunks=chunks)
    db.close()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT summary, summary_provider FROM doc_chunks LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["summary"] == "Short overview"
    assert row["summary_provider"] == "gemini-3-flash-preview"


def test_005_moves_seed_stamp_into_metadata_seeded_at(tmp_path: Path) -> None:
    """docs_005 adds metadata_seeded_at and relabels bogus index stamps.

    Pre-fix ``upsert_library`` stamped ``last_indexed_at`` for metadata-only
    Tier 1 seeds, so an upgraded DB must not keep claiming those libraries
    are indexed. Rows that really do own an indexed version are untouched.
    """
    if not _has_revision("docs_005_metadata_seeded_at"):
        pytest.skip("docs_005_metadata_seeded_at not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "docs_004_chunk_summaries")

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO libraries (id, name, tier, last_indexed_at, created_at, "
        "updated_at) VALUES ('seeded', 'react', 1, 1000.0, 1.0, 1.0)"
    )
    conn.execute(
        "INSERT INTO libraries (id, name, tier, last_indexed_at, created_at, "
        "updated_at) VALUES ('indexed', 'fastapi', 2, 2000.0, 1.0, 1.0)"
    )
    conn.execute(
        "INSERT INTO versions (id, library_id, version, status, chunk_count) "
        "VALUES ('v1', 'indexed', 'latest', 'indexed', 382)"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "docs_005_metadata_seeded_at")

    assert "metadata_seeded_at" in _table_columns(db_path, "libraries")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = {
        r["id"]: r
        for r in conn.execute(
            "SELECT id, last_indexed_at, metadata_seeded_at FROM libraries"
        ).fetchall()
    }
    conn.close()

    assert rows["seeded"]["last_indexed_at"] is None
    assert rows["seeded"]["metadata_seeded_at"] == 1000.0
    assert rows["indexed"]["last_indexed_at"] == 2000.0
    assert rows["indexed"]["metadata_seeded_at"] is None


def test_005_is_idempotent(tmp_path: Path) -> None:
    """Re-running docs_005 does not disturb an already-corrected DB."""
    if not _has_revision("docs_005_metadata_seeded_at"):
        pytest.skip("docs_005_metadata_seeded_at not yet created")

    db_path = tmp_path / "docs.db"
    cfg = _make_alembic_cfg(db_path)
    command.upgrade(cfg, "docs_004_chunk_summaries")

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO libraries (id, name, tier, last_indexed_at, created_at, "
        "updated_at) VALUES ('seeded', 'react', 1, 1000.0, 1.0, 1.0)"
    )
    conn.commit()
    conn.close()

    command.upgrade(cfg, "docs_005_metadata_seeded_at")
    # Rewind only the revision pointer (the column + corrected rows stay) and
    # replay the migration: it must find nothing left to fix.
    command.stamp(cfg, "docs_004_chunk_summaries")
    command.upgrade(cfg, "docs_005_metadata_seeded_at")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT last_indexed_at, metadata_seeded_at FROM libraries WHERE id = 'seeded'"
    ).fetchone()
    conn.close()
    assert row["last_indexed_at"] is None
    assert row["metadata_seeded_at"] == 1000.0
