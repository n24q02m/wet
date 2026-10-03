"""Tests for Alembic offline migration mode."""

from __future__ import annotations

import io
import os
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config

from wet.migrations import _ALEMBIC_INI_PATH, _ALEMBIC_SCRIPT_LOCATION


def test_run_migrations_offline(tmp_path: Path) -> None:
    """Verify that run_migrations_offline emits SQL to stdout.

    This test covers the 'run_migrations_offline' function in env.py.
    """
    # Use a dummy DB path to ensure it doesn't try to touch any real DB
    db_path = tmp_path / "offline_test.db"

    cfg = Config(str(_ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    f = io.StringIO()
    with redirect_stdout(f):
        # sql=True triggers the offline mode in env.py
        command.upgrade(cfg, "docs_001_baseline", sql=True)

    output = f.getvalue()

    # Verify expected SQL is in the output
    assert "CREATE TABLE alembic_version" in output
    assert "CREATE TABLE IF NOT EXISTS libraries" in output
    assert "CREATE TABLE IF NOT EXISTS versions" in output
    assert "CREATE TABLE IF NOT EXISTS doc_chunks" in output

    # Ensure the database file was NOT created (offline mode)
    assert not db_path.exists()


def test_run_migrations_offline_with_x_args(tmp_path: Path) -> None:
    """Verify run_migrations_offline handles -x db_path override."""
    db_path = tmp_path / "x_args_offline.db"

    cfg = Config(str(_ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    # Pass db_path via x-arguments
    cfg.attributes["x"] = ["db_path=" + str(db_path)]

    f = io.StringIO()
    with redirect_stdout(f):
        command.upgrade(cfg, "docs_001_baseline", sql=True)

    output = f.getvalue()
    assert "CREATE TABLE IF NOT EXISTS libraries" in output
    assert not db_path.exists()


def test_run_migrations_offline_with_env_var(tmp_path: Path) -> None:
    """Verify run_migrations_offline handles WET_DOCS_DB_PATH env var."""
    db_path = tmp_path / "env_var_offline.db"

    cfg = Config(str(_ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))

    with patch.dict(os.environ, {"WET_DOCS_DB_PATH": str(db_path)}):
        f = io.StringIO()
        with redirect_stdout(f):
            command.upgrade(cfg, "docs_001_baseline", sql=True)

    output = f.getvalue()
    assert "CREATE TABLE IF NOT EXISTS libraries" in output
    assert not db_path.exists()


def test_run_migrations_offline_fallback_to_default(tmp_path: Path) -> None:
    """Verify run_migrations_offline falls back to default path (mocked home)."""
    cfg = Config(str(_ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    # Force fallback by clearing env and setting placeholder in ini
    cfg.set_main_option("sqlalchemy.url", "driver://placeholder")

    with patch.dict(os.environ, {"WET_DOCS_DB_PATH": ""}):
        with patch("pathlib.Path.home", return_value=tmp_path):
            f = io.StringIO()
            with redirect_stdout(f):
                command.upgrade(cfg, "docs_001_baseline", sql=True)
            output = f.getvalue()
            assert "CREATE TABLE IF NOT EXISTS libraries" in output

            default_db = tmp_path / ".wet" / "docs.db"
            assert not default_db.exists()


def test_run_migrations_offline_full_chain_fails_gracefully(tmp_path: Path) -> None:
    """Verify that offline migration for the full chain fails due to live DB inspection.

    This test documents a known limitation: some migration scripts (like docs_002)
    use live database inspection (PRAGMA table_info) which fails in offline mode
    because 'op.get_bind()' returns a 'MockConnection' that doesn't support 'exec_driver_sql'.

    Even though it fails in the migration script, it still exercises the
    'run_migrations_offline' setup in env.py.
    """
    db_path = tmp_path / "offline_full.db"

    cfg = Config(str(_ALEMBIC_INI_PATH))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    with pytest.raises(
        AttributeError,
        match="'MockConnection' object has no attribute 'exec_driver_sql'",
    ):
        command.upgrade(cfg, "head", sql=True)
