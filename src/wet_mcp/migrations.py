"""Auto-migrate-on-startup runner for wet-mcp docs.db.

Mirrors the canonical pattern from mnemo-mcp:

1. Read ``alembic_version`` via raw SQL on a short-lived sqlite3 connection.
   Absent table => unstamped (pre-Alembic or freshly initialised) DB.
2. If a forward migration would actually run (current revision != head),
   copy ``docs.db`` to ``docs.db.bak.<unix-ts>`` (with WAL/SHM sidecars)
   first, so a failure can be recovered manually.
3. Stamp ``docs_001_baseline`` for unstamped DBs, then call
   ``alembic.command.upgrade(config, "head")``.

Any failure is logged via loguru and swallowed so server startup is not
blocked by migration issues. Tests can pass an alternative ``db_path``.

The runner deliberately operates on a fresh sqlite connection to avoid
clashing with the long-lived ``DocsDB._conn`` used by the running server
(SQLite WAL mode plays nicely with multiple readers/writers, but Alembic's
own engine should not piggy-back on application code).
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

from loguru import logger

_PKG_DIR = Path(__file__).resolve().parent
_ALEMBIC_INI_PATH = _PKG_DIR / "alembic.ini"
_ALEMBIC_SCRIPT_LOCATION = _PKG_DIR / "alembic"


def _read_alembic_version(db_path: Path) -> str | None:
    """Return the current ``alembic_version`` revision, or ``None`` if unstamped."""
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return None
        if not row:
            return None
        return row[0]
    finally:
        conn.close()


def _backup_db_file(db_path: Path) -> Path | None:
    """Copy the SQLite DB file to ``<path>.bak.<unix-ts>`` and return the path.

    Returns ``None`` if the source file does not exist (fresh DB, nothing to
    back up). WAL/SHM sidecars are also copied when present so the backup is
    internally consistent.
    """
    if not db_path.exists():
        return None

    ts = int(time.time())
    backup_path = db_path.with_suffix(db_path.suffix + f".bak.{ts}")
    try:
        shutil.copy2(db_path, backup_path)
        for sidecar in ("-wal", "-shm"):
            src = db_path.with_suffix(db_path.suffix + sidecar)
            if src.exists():
                shutil.copy2(src, backup_path.with_suffix(backup_path.suffix + sidecar))
        logger.info(f"docs.db backup created at {backup_path}")
        return backup_path
    except Exception as e:  # pragma: no cover - runtime guard
        logger.warning(f"docs.db backup failed: {e}")
        return None


def run_migrations_on_startup(db_path: Path) -> None:
    """Run Alembic migrations to head, with backup-before-migrate.

    Args:
        db_path: Absolute path to the docs.db SQLite file. If the file does
            not yet exist Alembic will create it, but the more usual flow is
            that ``DocsDB._create_tables`` runs first via ``DocsDB.__init__``
            (creating fresh schema), then this runner stamps + upgrades.
    """
    if not _ALEMBIC_INI_PATH.exists():
        logger.debug(
            f"Alembic config not found at {_ALEMBIC_INI_PATH}, "
            "skipping migrations (likely a wheel install without alembic dir)"
        )
        return

    try:
        from alembic import command
        from alembic.config import Config
        from alembic.script import ScriptDirectory
    except ImportError as e:  # pragma: no cover - dep is required at runtime
        logger.warning(f"Alembic import failed, skipping migrations: {e}")
        return

    try:
        cfg = Config(str(_ALEMBIC_INI_PATH))
        cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
        cfg.set_main_option(
            "sqlalchemy.url", f"sqlite:///{db_path.resolve().as_posix()}"
        )

        script = ScriptDirectory.from_config(cfg)
        head_rev = script.get_current_head()

        current_rev = _read_alembic_version(db_path)

        if current_rev == head_rev:
            logger.debug(f"docs.db already at head revision {head_rev}")
            return

        if current_rev is None:
            logger.info("Stamping docs.db at docs_001_baseline")
            command.stamp(cfg, "docs_001_baseline")
            current_rev = "docs_001_baseline"
            if current_rev == head_rev:
                return

        # Backup before applying any forward migration
        _backup_db_file(db_path)

        logger.info(f"Running Alembic upgrade: {current_rev} -> {head_rev}")
        command.upgrade(cfg, "head")
        logger.info(f"Alembic upgrade complete (head={head_rev})")
    except Exception as e:  # pragma: no cover - runtime guard
        logger.warning(f"Alembic migration failed: {e}")
