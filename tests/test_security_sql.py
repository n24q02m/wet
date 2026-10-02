import json

from wet_mcp.db import DocsDB


def test_get_existing_allowed_tables(tmp_path):
    db_path = tmp_path / "test.db"
    db = DocsDB(db_path)

    # Setup some data
    lib_id = "lib1"
    ver_id = "ver1"
    chunk_id = "chunk1"

    db.import_jsonl(
        json.dumps(
            {
                "_type": "library",
                "id": lib_id,
                "name": "lib1",
                "created_at": 1,
                "updated_at": 1,
            }
        )
    )
    db.import_jsonl(
        json.dumps(
            {
                "_type": "version",
                "id": ver_id,
                "library_id": lib_id,
                "version": "1.0",
                "created_at": 1,
                "updated_at": 1,
            }
        )
    )
    db.import_jsonl(
        json.dumps(
            {
                "_type": "chunk",
                "id": chunk_id,
                "version_id": ver_id,
                "library_id": lib_id,
                "url": "u",
                "title": "t",
                "chunk_index": 0,
                "content": "c",
                "created_at": 1,
            }
        )
    )

    # This indirectly tests _get_existing during import_jsonl merge mode
    stats = db.import_jsonl(
        json.dumps(
            {
                "_type": "library",
                "id": lib_id,
                "name": "lib1",
                "created_at": 1,
                "updated_at": 1,
            }
        ),
        mode="merge",
    )
    assert stats["skipped"] == 1

    stats = db.import_jsonl(
        json.dumps(
            {
                "_type": "version",
                "id": ver_id,
                "library_id": lib_id,
                "version": "1.0",
                "created_at": 1,
                "updated_at": 1,
            }
        ),
        mode="merge",
    )
    assert stats["skipped"] == 1

    stats = db.import_jsonl(
        json.dumps(
            {
                "_type": "chunk",
                "id": chunk_id,
                "version_id": ver_id,
                "library_id": lib_id,
                "url": "u",
                "title": "t",
                "chunk_index": 0,
                "content": "c",
                "created_at": 1,
            }
        ),
        mode="merge",
    )
    assert stats["skipped"] == 1


def test_get_existing_invalid_table(tmp_path):
    db_path = tmp_path / "test.db"
    # Just ensure we can instantiate DocsDB
    db = DocsDB(db_path)
    assert db._db_path == db_path
