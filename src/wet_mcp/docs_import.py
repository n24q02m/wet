"""Host-side docs rescue: import a Cloudflare D1 SQL export into a local docs.db.

Reads a user-provided plain-SQL export (D1 ``--export`` shape: ``PRAGMA
defer_foreign_keys=TRUE``, ``CREATE TABLE`` for the old PK schema, line-based
``INSERT`` statements) and materializes it as the local SQLite docs store that
:meth:`wet_mcp.db.DocsDB` opens. Runs entirely host-side; the server does not
need to be running, and no export data is ever committed to the repo.

Pipeline (``import_docs``):

1. refuse to clobber a non-empty target DB unless ``force`` (then unlink the
   db + ``-wal``/``-shm`` sidecars);
2. ``executescript`` the whole export in one shot;
3. bootstrap the CURRENT schema onto the imported DB by instantiating
   ``DocsDB`` (``IF NOT EXISTS`` tables + guarded ``ALTER`` columns + FTS5
   table/triggers); opened with ``embedding_dims=0`` so no vector table is
   created here — ``docs_reembed`` owns vector (re)population;
4. store_meta hygiene: delete the ``embedding_model``/``embedding_dims`` rows
   (both any rows that arrived in the export and the fresh stamp the DocsDB
   identity guard just wrote) so the next server open treats every vector as
   pending re-embed;
5. rebuild FTS5 (``INSERT INTO doc_chunks_fts(doc_chunks_fts)
   VALUES('rebuild')``) unless skipped;
6. hard count assertions on write (doc_chunks/libraries/versions — the
   proven receipt numbers; a D1 export can silently truncate, so the counts
   are the only trust anchor), then close, reopen a FRESH connection and
   read the counts back again + ``PRAGMA integrity_check`` + FTS row-count
   probe;
7. stamp alembic (``run_migrations_on_startup``: stamps baseline + upgrades,
   backing up first when a forward migration applies).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from loguru import logger

# Proven receipt numbers of the D1 export this module exists to rescue.
# Asserted exactly; only the chunk count is overridable (``--expected-chunks``).
EXPECTED_CHUNKS = 49939
EXPECTED_LIBRARIES = 14
EXPECTED_VERSIONS = 8

# store_meta keys carrying the embedding identity. These are deleted on import
# so the B2 guard treats the imported vectors as pending re-embed; docs_reembed
# re-stamps them after backfilling.
_IDENTITY_KEYS = ("embedding_model", "embedding_dims")


def _delete_identity_rows(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM store_meta WHERE key IN (?, ?)", _IDENTITY_KEYS
    )


def _counts(conn: sqlite3.Connection) -> tuple[int, int, int]:
    chunks = conn.execute("SELECT COUNT(*) FROM doc_chunks").fetchone()[0]
    libraries = conn.execute("SELECT COUNT(*) FROM libraries").fetchone()[0]
    versions = conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0]
    return chunks, libraries, versions


def _assert_counts(
    chunks: int, libraries: int, versions: int, expected_chunks: int
) -> None:
    if chunks != expected_chunks:
        raise RuntimeError(
            f"docs import count mismatch: doc_chunks={chunks} but expected "
            f"{expected_chunks}. The export may be truncated or the wrong "
            "file. Pass --expected-chunks N to override the chunk count "
            "(libraries/versions stay hard-asserted)."
        )
    if libraries != EXPECTED_LIBRARIES:
        raise RuntimeError(
            f"docs import count mismatch: libraries={libraries} but expected "
            f"{EXPECTED_LIBRARIES}."
        )
    if versions != EXPECTED_VERSIONS:
        raise RuntimeError(
            f"docs import count mismatch: versions={versions} but expected "
            f"{EXPECTED_VERSIONS}."
        )


def import_docs(
    sql_path: Path,
    db_path: Path | None = None,
    *,
    force: bool = False,
    expected_chunks: int = EXPECTED_CHUNKS,
    skip_fts: bool = False,
) -> dict:
    """Import a D1 SQL export into a local docs.db. Returns a summary dict."""
    start = time.monotonic()
    sql_path = Path(sql_path)
    if not sql_path.is_file():
        raise FileNotFoundError(f"export SQL not found: {sql_path}")

    from wet_mcp.config import settings

    target = Path(db_path) if db_path is not None else settings.get_db_path()
    if target.exists() and target.stat().st_size > 0:
        if not force:
            raise RuntimeError(
                f"refusing to overwrite existing non-empty docs db: {target} "
                "(pass --force to replace it)"
            )
        for suffix in ("", "-wal", "-shm"):
            sidecar = Path(str(target) + suffix)
            if sidecar.exists():
                sidecar.unlink()
                logger.info(f"removed existing file: {sidecar}")
    target.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"reading export: {sql_path}")
    sql_text = sql_path.read_text(encoding="utf-8")

    # 1-2. Materialize the export in one shot (the script carries
    # PRAGMA defer_foreign_keys=TRUE for its own insert ordering).
    conn = sqlite3.connect(str(target))
    try:
        conn.executescript(sql_text)
        conn.commit()
        # Hygiene pass 1: drop any identity rows that arrived in the export
        # BEFORE DocsDB opens the file — its dims guard would otherwise see
        # exported dims vs the bootstrap dims and refuse.
        _delete_identity_rows(conn)
        conn.commit()
    finally:
        conn.close()

    # 3. Bootstrap the CURRENT schema (IF NOT EXISTS + guarded ALTERs + FTS5
    # triggers). dims=0 -> no vector table; reembed owns vectors.
    from wet_mcp.db import DocsDB

    DocsDB(target)

    conn = sqlite3.connect(str(target))
    try:
        # Hygiene pass 2: the fresh-store guard just stamped embedding_dims=0;
        # wipe it so the next open re-stamps the REAL embedding identity only
        # after reembed has actually backfilled vectors.
        _delete_identity_rows(conn)
        conn.commit()

        # 5. FTS rebuild from the external-content table.
        has_fts = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='doc_chunks_fts'"
        ).fetchone() is not None
        fts_rebuilt = False
        if has_fts and not skip_fts:
            logger.info("rebuilding doc_chunks_fts from doc_chunks")
            conn.execute("INSERT INTO doc_chunks_fts(doc_chunks_fts) VALUES('rebuild')")
            conn.commit()
            fts_rebuilt = True
        elif skip_fts:
            logger.warning(
                "--skip-fts given: doc_chunks_fts NOT rebuilt; docs keyword "
                "search will return nothing until a rebuild is run"
            )
        elif not has_fts:
            logger.warning(
                "doc_chunks_fts table absent after schema bootstrap; FTS "
                "rebuild skipped"
            )

        # 6a. Write-time count assertions (silent-truncation guard).
        chunks, libraries, versions = _counts(conn)
        _assert_counts(chunks, libraries, versions, expected_chunks)
    finally:
        conn.close()

    # 6b. Read back on a FRESH connection: counts must survive the close,
    # integrity must be ok, FTS rows must equal chunks after a rebuild.
    conn = sqlite3.connect(str(target))
    try:
        rb_chunks, rb_libraries, rb_versions = _counts(conn)
        _assert_counts(rb_chunks, rb_libraries, rb_versions, expected_chunks)
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(
                f"docs db failed integrity_check after import: {integrity!r}"
            )
        fts_rows: int | None = None
        if fts_rebuilt:
            fts_rows = conn.execute(
                "SELECT COUNT(*) FROM doc_chunks_fts"
            ).fetchone()[0]
            if fts_rows != rb_chunks:
                raise RuntimeError(
                    f"FTS rebuild mismatch: doc_chunks_fts has {fts_rows} rows "
                    f"but doc_chunks has {rb_chunks}"
                )
    finally:
        conn.close()

    # 7. Alembic stamp/upgrade (backs up before any forward migration; no-ops
    # when already at head or when the alembic dir is absent, e.g. wheel).
    from wet_mcp.migrations import run_migrations_on_startup

    run_migrations_on_startup(target)

    return {
        "chunks": rb_chunks,
        "libraries": rb_libraries,
        "versions": rb_versions,
        "fts_rows": fts_rows,
        "db_path": str(target),
        "elapsed_s": round(time.monotonic() - start, 1),
    }
