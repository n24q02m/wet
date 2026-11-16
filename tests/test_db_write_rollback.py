"""A ``DocsDB`` write that fails midway leaves nothing behind on the shared connection.

Python's ``sqlite3`` opens a transaction implicitly before the first write and
keeps it open when a later statement fails. ``DocsDB`` serves every caller from
one connection, so a unit of work left half-done used to be persisted by the
next unrelated method that called ``commit()``: part of a chunk batch, or the
replace-mode wipe of an import whose data never arrived. Each test fails a unit
midway, lets another method commit, then reads the file through an independent
connection, which only sees committed rows.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from wet.db import DocsDB


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
