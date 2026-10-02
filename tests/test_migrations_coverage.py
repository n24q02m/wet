from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from loguru import logger

from wet_mcp.migrations import (
    _ALEMBIC_INI_PATH,
    _ALEMBIC_SCRIPT_LOCATION,
    _backup_db_file,
    _read_alembic_version,
    run_migrations_on_startup,
)


def test_read_alembic_version_missing_db(tmp_path: Path):
    """_read_alembic_version returns None if DB file does not exist."""
    assert _read_alembic_version(tmp_path / "missing.db") is None


def test_read_alembic_version_empty_table(tmp_path: Path):
    """_read_alembic_version returns None if table exists but is empty."""
    db_path = tmp_path / "docs.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE alembic_version (version_num TEXT)")
    conn.commit()
    conn.close()
    assert _read_alembic_version(db_path) is None


def test_backup_db_file_no_source(tmp_path: Path):
    """_backup_db_file returns None if source does not exist."""
    assert _backup_db_file(tmp_path / "missing.db") is None


def test_backup_db_file_with_sidecars(tmp_path: Path):
    """_backup_db_file copies WAL/SHM sidecars if present."""
    db_path = tmp_path / "docs.db"
    db_path.write_text("db content")
    wal_path = tmp_path / "docs.db-wal"
    wal_path.write_text("wal content")
    shm_path = tmp_path / "docs.db-shm"
    shm_path.write_text("shm content")

    backup_path = _backup_db_file(db_path)
    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.read_text() == "db content"
    assert backup_path.with_suffix(backup_path.suffix + "-wal").exists()
    assert (
        backup_path.with_suffix(backup_path.suffix + "-wal").read_text()
        == "wal content"
    )
    assert backup_path.with_suffix(backup_path.suffix + "-shm").exists()
    assert (
        backup_path.with_suffix(backup_path.suffix + "-shm").read_text()
        == "shm content"
    )


def test_run_migrations_on_startup_no_config(tmp_path: Path, caplog):
    """run_migrations_on_startup skips if alembic.ini is missing."""
    db_path = tmp_path / "docs.db"
    handler_id = logger.add(caplog.handler, format="{message}")
    try:
        # Use tmp_path instead of hardcoded /tmp for portability
        missing_ini = tmp_path / "missing_alembic.ini"
        with patch("wet_mcp.migrations._ALEMBIC_INI_PATH", missing_ini):
            run_migrations_on_startup(db_path)
        assert "Alembic config not found" in caplog.text
    finally:
        logger.remove(handler_id)


def test_run_migrations_on_startup_already_at_head(tmp_path: Path, caplog):
    """run_migrations_on_startup is a no-op if already at head."""
    db_path = tmp_path / "docs.db"
    cfg = Config(str(_ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.resolve().as_posix()}")

    # Pre-migrate to head
    command.upgrade(cfg, "head")

    handler_id = logger.add(caplog.handler, format="{message}")
    try:
        import logging

        with caplog.at_level(logging.DEBUG):
            run_migrations_on_startup(db_path)
        assert "already at head revision" in caplog.text
    finally:
        logger.remove(handler_id)


def test_run_migrations_on_startup_unstamped(tmp_path: Path, caplog):
    """run_migrations_on_startup stamps and upgrades unstamped DB."""
    db_path = tmp_path / "docs.db"

    # Seed minimal baseline schema so forward migrations find their columns.
    # The SQL matches src/wet_mcp/alembic/versions/docs_001_baseline.py
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE libraries (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            docs_url TEXT,
            registry TEXT,
            description TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            discovery_version INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE versions (
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
    """)
    conn.execute("""
        CREATE TABLE doc_chunks (
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
    """)
    conn.commit()
    conn.close()

    handler_id = logger.add(caplog.handler, format="{message}")
    try:
        run_migrations_on_startup(db_path)
        assert "Stamping docs.db at docs_001_baseline" in caplog.text
        assert "Alembic upgrade complete" in caplog.text
    finally:
        logger.remove(handler_id)
