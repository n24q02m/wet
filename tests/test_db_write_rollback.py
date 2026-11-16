"""A ``DocsDB`` write that fails midway leaves nothing behind on the shared connection.

Python's ``sqlite3`` opens a transaction implicitly before the first write and
keeps it open when a later statement fails. ``DocsDB`` serves every caller from
one connection, so a unit of work left half-done used to be persisted by the
next unrelated method that called ``commit()``: part of a chunk batch, or the
replace-mode wipe of an import whose data never arrived. Each test fails a unit
midway, lets another method commit, then reads the file through an independent
connection, which only sees committed rows.

A write of a single statement that fails leaves no half-done data, but the
transaction ``sqlite3`` opened for it stays open and keeps the database write
lock, so every other connection to the file gets "database is locked" until
some later call commits. Those tests check that nothing stays open.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from wet.db import INDEX_STATE_FAILED, DocsDB


def _count(db_path: Path, sql: str, *, vec: bool = False) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        if vec:
            import sqlite_vec

            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


def _seed(db: DocsDB, embeddings: list[list[float]] | None = None) -> str:
    """Store one library, version and chunk; return the version id."""
    lib_id = db.upsert_library("seeded", docs_url="https://seeded.dev")
    ver_id = db.upsert_version(lib_id, "latest")
    db.add_chunks(
        ver_id,
        lib_id,
        [{"url": "https://seeded.dev/a", "title": "A", "content": "seeded alpha"}],
        embeddings=embeddings,
    )
    return ver_id


def _later_commit_landed(db_path: Path) -> bool:
    return (
        _count(db_path, "SELECT COUNT(*) FROM libraries WHERE name = 'unrelated'") == 1
    )


def test_add_chunks_failing_midway_commits_no_part_of_the_batch(tmp_path: Path):
    db_path = tmp_path / "docs.db"
    db = DocsDB(db_path, embedding_dims=0)
    try:
        lib_id = db.upsert_library("lib")
        ver_id = db.upsert_version(lib_id)
        # The second row breaks doc_chunks.content NOT NULL after the first
        # row is already written into the open transaction.
        with pytest.raises(sqlite3.IntegrityError):
            db.add_chunks(
                ver_id, lib_id, [{"content": "first row lands"}, {"content": None}]
            )
        db.upsert_library("unrelated")
    finally:
        db.close()

    assert _later_commit_landed(db_path)
    assert _count(db_path, "SELECT COUNT(*) FROM doc_chunks") == 0


def test_import_jsonl_replace_with_a_bad_line_keeps_the_old_store(tmp_path: Path):
    db_path = tmp_path / "docs.db"
    db = DocsDB(db_path, embedding_dims=0)
    try:
        _seed(db)
        good = json.dumps(
            {
                "_type": "library",
                "id": "new-lib",
                "name": "new",
                "created_at": 1.0,
                "updated_at": 1.0,
            }
        )
        # The replace-mode clear runs before the lines are parsed.
        with pytest.raises(json.JSONDecodeError):
            db.import_jsonl(good + "\n{truncated", mode="replace")
        db.upsert_library("unrelated")
    finally:
        db.close()

    assert _later_commit_landed(db_path)
    assert _count(db_path, "SELECT COUNT(*) FROM libraries WHERE name = 'seeded'") == 1
    assert _count(db_path, "SELECT COUNT(*) FROM versions") == 1
    assert _count(db_path, "SELECT COUNT(*) FROM doc_chunks") == 1


def test_clear_version_chunks_failing_midway_keeps_the_vectors(tmp_path: Path):
    db_path = tmp_path / "docs.db"
    db = DocsDB(db_path, embedding_dims=4)
    try:
        if not db._vec_enabled:
            pytest.skip("sqlite-vec cannot be loaded in this interpreter")
        ver_id = _seed(db, embeddings=[[0.1, 0.2, 0.3, 0.4]])
        with db.connection() as conn:
            # Refuse the chunk DELETE, which runs after the vector DELETE.
            conn.execute(
                "CREATE TRIGGER refuse_chunk_delete BEFORE DELETE ON doc_chunks "
                "BEGIN SELECT RAISE(ABORT, 'chunk delete refused'); END"
            )
            conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="chunk delete refused"):
            db.clear_version_chunks(ver_id)
        db.upsert_library("unrelated")
    finally:
        db.close()

    assert _later_commit_landed(db_path)
    assert _count(db_path, "SELECT COUNT(*) FROM doc_chunks") == 1
    assert _count(db_path, "SELECT COUNT(*) FROM doc_chunks_vec", vec=True) == 1


def test_connection_block_that_raises_leaves_no_write_behind(tmp_path: Path):
    db_path = tmp_path / "docs.db"
    db = DocsDB(db_path, embedding_dims=0)
    try:
        with (
            pytest.raises(RuntimeError, match="maintenance step failed"),
            db.connection() as conn,
        ):
            conn.execute(
                "INSERT INTO store_meta (key, value) VALUES ('probe', 'half-done')"
            )
            raise RuntimeError("maintenance step failed")
        db.upsert_library("unrelated")
    finally:
        db.close()

    assert _later_commit_landed(db_path)
    assert _count(db_path, "SELECT COUNT(*) FROM store_meta WHERE key = 'probe'") == 0


def _refuse(db: DocsDB, event: str) -> None:
    """Make every statement on ``db``'s connection that fires ``event`` abort."""
    with db.connection() as conn:
        conn.execute(
            f"CREATE TEMP TRIGGER injected_failure {event} "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )


def _other_connection_can_write(db_path: Path) -> bool:
    conn = sqlite3.connect(str(db_path), timeout=0.2)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO store_meta (key, value) VALUES ('probe', 'other')"
        )
        conn.commit()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("event", "write"),
    [
        pytest.param(
            "BEFORE INSERT ON libraries",
            lambda db, lib_id, ver_id: db.upsert_library("new"),
            id="upsert_library-insert",
        ),
        pytest.param(
            "BEFORE UPDATE ON libraries",
            lambda db, lib_id, ver_id: db.upsert_library("seeded", description="d"),
            id="upsert_library-update",
        ),
        pytest.param(
            "BEFORE UPDATE ON libraries",
            lambda db, lib_id, ver_id: db.mark_library_indexed(lib_id),
            id="mark_library_indexed",
        ),
        pytest.param(
            "BEFORE UPDATE ON libraries",
            lambda db, lib_id, ver_id: db.mark_metadata_seeded(lib_id),
            id="mark_metadata_seeded",
        ),
        pytest.param(
            "BEFORE INSERT ON versions",
            lambda db, lib_id, ver_id: db.upsert_version(lib_id, "2.0"),
            id="upsert_version-insert",
        ),
        pytest.param(
            "BEFORE UPDATE ON versions",
            lambda db, lib_id, ver_id: db.upsert_version(
                lib_id, "latest", docs_url="https://seeded.dev/docs"
            ),
            id="upsert_version-update",
        ),
        pytest.param(
            "BEFORE UPDATE ON versions",
            lambda db, lib_id, ver_id: db.mark_version_indexed(ver_id, 1, 1),
            id="mark_version_indexed",
        ),
        pytest.param(
            "BEFORE UPDATE ON versions",
            lambda db, lib_id, ver_id: db.reset_version_index(ver_id),
            id="reset_version_index",
        ),
        pytest.param(
            "BEFORE UPDATE ON versions",
            lambda db, lib_id, ver_id: db.set_index_state(
                ver_id, INDEX_STATE_FAILED, "boom"
            ),
            id="set_index_state",
        ),
        pytest.param(
            "BEFORE INSERT ON project_context",
            lambda db, lib_id, ver_id: db.upsert_project_context("/other", []),
            id="upsert_project_context-insert",
        ),
        pytest.param(
            "BEFORE UPDATE ON project_context",
            lambda db, lib_id, ver_id: db.upsert_project_context("/project", []),
            id="upsert_project_context-update",
        ),
        pytest.param(
            "BEFORE UPDATE ON project_context",
            lambda db, lib_id, ver_id: db.touch_project_context("/project"),
            id="touch_project_context",
        ),
    ],
)
def test_failed_single_statement_write_releases_the_database(
    tmp_path: Path, event, write
):
    db_path = tmp_path / "docs.db"
    db = DocsDB(db_path, embedding_dims=0)
    try:
        lib_id = db.upsert_library("seeded")
        ver_id = db.upsert_version(lib_id)
        db.upsert_project_context("/project", [])
        _refuse(db, event)
        with pytest.raises(sqlite3.IntegrityError, match="injected"):
            write(db, lib_id, ver_id)
        with db._lock:
            assert db._conn.in_transaction is False
        assert _other_connection_can_write(db_path)
    finally:
        db.close()
