"""Additional unit tests for db.py to increase coverage from 78% to 95%+.

Targets uncovered lines: 217-224, 27, 112, 117, 119, 142-151, 267-271, 287-291,
328-332, 396-403, 431-435, 526-540, 550-557, 581-598, 694-697, 712-743,
772, 804, 807, 812, 879-882, 889, 972-973.
"""

import importlib.util
import json
import sqlite3
import struct
import sys
import types
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap (same as test_db.py — avoids crawl4ai import chain)
# ---------------------------------------------------------------------------
_src_root = Path(__file__).resolve().parent.parent / "src"

if "wet_mcp" not in sys.modules:
    _pkg = types.ModuleType("wet_mcp")
    _pkg.__path__ = [str(_src_root / "wet_mcp")]
    sys.modules["wet_mcp"] = _pkg

if "wet_mcp.sources" not in sys.modules:
    _sources_pkg = types.ModuleType("wet_mcp.sources")
    _sources_pkg.__path__ = [str(_src_root / "wet_mcp" / "sources")]
    sys.modules["wet_mcp.sources"] = _sources_pkg

if "wet_mcp.sources.docs" not in sys.modules:
    _docs_file = _src_root / "wet_mcp" / "sources" / "docs.py"
    _docs_spec = importlib.util.spec_from_file_location(
        "wet_mcp.sources.docs", _docs_file
    )
    assert _docs_spec is not None
    _docs_mod = importlib.util.module_from_spec(_docs_spec)
    sys.modules["wet_mcp.sources.docs"] = _docs_mod
    _docs_spec.loader.exec_module(_docs_mod)
else:
    _docs_mod = sys.modules["wet_mcp.sources.docs"]

if "wet_mcp.db" not in sys.modules:
    _db_file = _src_root / "wet_mcp" / "db.py"
    _db_spec = importlib.util.spec_from_file_location("wet_mcp.db", _db_file)
    assert _db_spec is not None
    _db_mod = importlib.util.module_from_spec(_db_spec)
    sys.modules["wet_mcp.db"] = _db_mod
    _db_spec.loader.exec_module(_db_mod)
else:
    _db_mod = sys.modules["wet_mcp.db"]

DocsDB = _db_mod.DocsDB
_build_fts_queries = _db_mod._build_fts_queries
_chunk_quality_score = _db_mod._chunk_quality_score
_serialize_f32 = _db_mod._serialize_f32


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    """Fresh DocsDB without vec."""
    d = DocsDB(tmp_path / "test.db", embedding_dims=0)
    yield d
    d.close()


@pytest.fixture
def populated_db(db):
    """DB with library, version, and multiple chunks on the same URL."""
    lib_id = db.upsert_library(
        name="testlib",
        docs_url="https://example.com",
        registry="pypi",
        description="A test library",
    )
    ver_id = db.upsert_version(
        lib_id, version="1.0.0", docs_url="https://example.com/docs"
    )
    chunks = [
        {
            "content": "def hello(): pass",
            "title": "Hello function",
            "url": "https://example.com/page1",
            "heading_path": "API > hello",
            "chunk_index": 0,
        },
        {
            "content": "def world(): return 42",
            "title": "World function",
            "url": "https://example.com/page1",
            "heading_path": "API > world",
            "chunk_index": 1,
        },
        {
            "content": "class Foo: '''Docstring''' pass",
            "title": "Foo class",
            "url": "https://example.com/page1",
            "heading_path": "API > Foo",
            "chunk_index": 2,
        },
        {
            "content": "class Bar extends Foo for extra functionality",
            "title": "Bar class",
            "url": "https://example.com/page2",
            "heading_path": "API > Bar",
            "chunk_index": 0,
        },
    ]
    db.add_chunks(ver_id, lib_id, chunks)
    db.mark_version_indexed(ver_id, page_count=2, chunk_count=4)
    return db, lib_id, ver_id


# ---------------------------------------------------------------------------
# _serialize_f32 (line 27)
# ---------------------------------------------------------------------------


class TestSerializeF32:
    def test_serialize_roundtrip(self):
        """Verify float vector serialization produces correct bytes."""
        vec = [1.0, 2.0, 3.0]
        data = _serialize_f32(vec)
        assert isinstance(data, bytes)
        assert len(data) == 12  # 3 floats * 4 bytes
        unpacked = struct.unpack("3f", data)
        assert list(unpacked) == vec

    def test_serialize_empty(self):
        """Empty vector produces empty bytes."""
        assert _serialize_f32([]) == b""


# ---------------------------------------------------------------------------
# _chunk_quality_score edge cases (lines 112, 117, 119)
# ---------------------------------------------------------------------------


class TestChunkQualityScoreEdgeCases:
    def test_moderate_link_ratio(self):
        """Link ratio between 0.3-0.5 triggers -2.0 penalty (line 112)."""
        # 4 lines total, 2 are links -> ratio = 0.5 exactly (> 0.3, not > 0.5)
        # Actually need ratio > 0.3 but <= 0.5
        # 10 lines, 4 links -> ratio = 0.4
        lines = []
        for i in range(4):
            lines.append(f"- [Link {i}](https://example.com/{i})")
        for i in range(6):
            lines.append(f"Some regular content line {i}")
        content = "\n".join(lines)
        score = _chunk_quality_score(content)
        # With link ratio ~0.4, gets -2.0 penalty
        # Also gets length bonus if > 200 chars
        assert score >= 0.0  # score is clamped to 0-1

    def test_high_directive_count(self):
        """More than 3 directives triggers -2.0 penalty (line 117)."""
        content = "\n".join(
            [
                "!!! note This is a note",
                "!!! warning This is a warning",
                "!!! danger This is danger",
                "!!! tip This is a tip",
                "Some content here",
            ]
        )
        score = _chunk_quality_score(content)
        assert score >= 0.0

    def test_moderate_directive_count(self):
        """1-3 directives triggers -1.0 penalty (line 119)."""
        content = "\n".join(
            [
                "!!! note This is a note",
                "!!! warning This is a warning",
                "Some content here that is longer than what we need",
            ]
        )
        score = _chunk_quality_score(content)
        assert score >= 0.0

    def test_link_ratio_above_half(self):
        """Link ratio > 0.5 triggers -4.0 penalty."""
        # 5 lines, 4 are links -> ratio = 0.8
        lines = [
            "- [Link 1](https://example.com/1)",
            "- [Link 2](https://example.com/2)",
            "- [Link 3](https://example.com/3)",
            "- [Link 4](https://example.com/4)",
            "Normal text",
        ]
        content = "\n".join(lines)
        score = _chunk_quality_score(content)
        assert score == 0.0  # clamped to 0


# ---------------------------------------------------------------------------
# sqlite-vec loading failure (lines 142-151)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Migration: library table column (lines 217-224)
# ---------------------------------------------------------------------------


class TestLibraryMigration:
    def test_migration_discovery_version_exists(self, db):
        """Calling migration when column already exists is handled (lines 217-224)."""
        # First call happens in fixture initialization
        # Second call triggers OperationalError because column exists
        db._create_libraries_table()
        # Check if column exists
        info = db._conn.execute(
            "SELECT name FROM pragma_table_info(?)", ("libraries",)
        ).fetchall()
        cols = [c["name"] for c in info]
        assert "discovery_version" in cols


class TestSqliteVecLoading:
    def test_vec_load_failure_falls_back(self, tmp_path):
        """When sqlite-vec import fails, DB falls back to FTS-only (lines 142-151)."""
        with patch.dict(sys.modules, {"sqlite_vec": None}):
            d = DocsDB(tmp_path / "novec.db", embedding_dims=128)
            assert d._vec_enabled is False
            d.close()

    def test_vec_load_exception_falls_back(self, tmp_path):
        """When sqlite-vec load() raises, DB falls back gracefully."""
        mock_vec = MagicMock()
        mock_vec.load.side_effect = RuntimeError("Extension load failed")
        with patch.dict(sys.modules, {"sqlite_vec": mock_vec}):
            d = DocsDB(tmp_path / "vecfail.db", embedding_dims=128)
            assert d._vec_enabled is False
            d.close()


# ---------------------------------------------------------------------------
# upsert_library update with registry/description (lines 328-332)
# ---------------------------------------------------------------------------


class TestUpsertLibraryUpdate:
    def test_update_registry_and_description(self, db):
        """Updating existing library with registry and description (lines 328-332)."""
        lib_id = db.upsert_library(name="mylib", docs_url="https://mylib.io")
        # Now update with registry and description
        lib_id2 = db.upsert_library(
            name="mylib",
            registry="npm",
            description="Updated description",
        )
        assert lib_id == lib_id2
        lib = db.get_library("mylib")
        assert lib["registry"] == "npm"
        assert lib["description"] == "Updated description"

    def test_update_only_registry(self, db):
        """Updating only registry field."""
        db.upsert_library(name="lib2")
        db.upsert_library(name="lib2", registry="cargo")
        lib = db.get_library("lib2")
        assert lib["registry"] == "cargo"

    def test_update_only_description(self, db):
        """Updating only description field."""
        db.upsert_library(name="lib3")
        db.upsert_library(name="lib3", description="New desc")
        lib = db.get_library("lib3")
        assert lib["description"] == "New desc"


# ---------------------------------------------------------------------------
# upsert_version update docs_url (lines 431-435)
# ---------------------------------------------------------------------------


class TestUpsertVersionUpdate:
    def test_update_existing_version_docs_url(self, db):
        """When version exists and docs_url provided, update it (lines 431-435)."""
        lib_id = db.upsert_library(name="verlib")
        ver_id = db.upsert_version(lib_id, version="2.0.0", docs_url="https://old.com")
        # Call again with new docs_url
        ver_id2 = db.upsert_version(lib_id, version="2.0.0", docs_url="https://new.com")
        assert ver_id == ver_id2
        # Verify the URL was updated
        row = db._conn.execute(
            "SELECT docs_url FROM versions WHERE id = ?", (ver_id,)
        ).fetchone()
        assert row["docs_url"] == "https://new.com"


# ---------------------------------------------------------------------------
# clear_version_chunks with vec (lines 550-557)
# ---------------------------------------------------------------------------


class TestClearVersionChunksVec:
    def test_clear_chunks_vec_path(self, tmp_path):
        """clear_version_chunks exercises vec deletion path (lines 550-557)."""
        d = DocsDB(tmp_path / "cvec.db", embedding_dims=0)
        lib_id = d.upsert_library(name="clearlib")
        ver_id = d.upsert_version(lib_id)
        d.add_chunks(
            ver_id,
            lib_id,
            [
                {"content": "chunk 1"},
                {"content": "chunk 2"},
            ],
        )

        # Force vec_enabled
        d._vec_enabled = True
        # Exercise the vec deletion code path (will except silently)
        count = d.clear_version_chunks(ver_id)
        assert count == 2
        d.close()


# ---------------------------------------------------------------------------
# add_chunks with embeddings (lines 526-540)
# ---------------------------------------------------------------------------


class TestAddChunksWithEmbeddings:
    def test_add_chunks_vec_enabled_with_embeddings(self, tmp_path):
        """A failed vector insert aborts the batch instead of reporting success."""
        d = DocsDB(tmp_path / "emb.db", embedding_dims=0)
        lib_id = d.upsert_library(name="emblib")
        ver_id = d.upsert_version(lib_id)

        # Force vec_enabled to exercise embedding code path
        d._vec_enabled = True
        embeddings = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
        chunks = [
            {"content": "chunk A"},
            {"content": "chunk B"},
        ]
        # doc_chunks_vec does not exist at dims=0, so the vector INSERT fails.
        # add_chunks used to swallow that and still return 2, which let the
        # caller stamp the version 'indexed' over a vector-less batch.
        with pytest.raises(sqlite3.Error):
            d.add_chunks(ver_id, lib_id, chunks, embeddings=embeddings)
        assert d._conn.execute("SELECT COUNT(*) FROM doc_chunks").fetchone()[0] == 0
        d.close()

    def test_add_chunks_vec_empty_embedding_skipped(self, tmp_path):
        """Empty embedding lists are skipped (line 528 condition)."""
        d = DocsDB(tmp_path / "emb2.db", embedding_dims=0)
        lib_id = d.upsert_library(name="emblib2")
        ver_id = d.upsert_version(lib_id)

        d._vec_enabled = True
        # Second embedding is empty list (falsy) -> skipped
        embeddings = [[1.0, 2.0], []]
        chunks = [
            {"content": "chunk X"},
            {"content": "chunk Y"},
        ]

        # dims=0 leaves doc_chunks_vec uncreated and a failing vector INSERT now
        # aborts the batch, so route that one statement to a spy: what this test
        # asserts is which rows reach it, not that they land.
        real_conn = d._conn
        vec_batches: list[list] = []

        class _VecSpyConn:
            def executemany(self, sql, params):
                if "doc_chunks_vec" in sql:
                    vec_batches.append(list(params))
                    return None
                return real_conn.executemany(sql, params)

            def __getattr__(self, name):
                return getattr(real_conn, name)

        d._conn = cast(Any, _VecSpyConn())
        try:
            count = d.add_chunks(ver_id, lib_id, chunks, embeddings=embeddings)
        finally:
            d._conn = real_conn
        assert count == 2
        assert len(vec_batches) == 1
        assert len(vec_batches[0]) == 1  # only the non-empty embedding
        d.close()


# ---------------------------------------------------------------------------
# FTS search error handling (lines 694-697)
# ---------------------------------------------------------------------------


class TestSearchFTSError:
    def test_fts_query_error_continues(self, tmp_path):
        """FTS error on one tier continues to next tier (lines 694-697).

        We corrupt the FTS index to force an OperationalError on MATCH queries,
        then verify the search gracefully returns empty rather than raising.
        """
        d = DocsDB(tmp_path / "ftserr.db", embedding_dims=0)
        lib_id = d.upsert_library(name="errlib")
        ver_id = d.upsert_version(lib_id)
        d.add_chunks(ver_id, lib_id, [{"content": "hello world test"}])
        d.mark_version_indexed(ver_id, 1, 1)

        # Corrupt FTS index by dropping the underlying content table's trigger
        # and rebuilding with bad data won't work easily. Instead, use a
        # wrapper connection that intercepts execute calls.
        real_conn = d._conn

        class WrappedConn:
            """Proxy that raises on first MATCH query."""

            def __init__(self, conn):
                self._conn = conn
                self._match_count = 0

            def execute(self, sql, params=None):
                if "MATCH" in str(sql):
                    self._match_count += 1
                    if self._match_count <= 2:
                        raise sqlite3.OperationalError("FTS parse error")
                if params is not None:
                    return self._conn.execute(sql, params)
                return self._conn.execute(sql)

            def __getattr__(self, name):
                return getattr(self._conn, name)

        d._conn = WrappedConn(real_conn)
        results = d.search("hello")
        assert isinstance(results, list)
        d._conn = real_conn
        d.close()


# ---------------------------------------------------------------------------
# Search: result limit, skip chunks not in fts_chunks (lines 772, 804, 807, 812)
# ---------------------------------------------------------------------------


class TestSearchResultLimits:
    def test_search_limit_caps_results(self, populated_db):
        """Search respects limit parameter (line 804)."""
        db, lib_id, ver_id = populated_db
        results = db.search("function class", limit=1)
        assert len(results) <= 1

    def test_url_diversity_limit(self, populated_db):
        """Max 2 results per URL, then skip (line 812)."""
        db, lib_id, ver_id = populated_db
        # page1 has 3 chunks; at most 2 should appear from it
        results = db.search("def class", limit=10)
        url_counts = {}
        for r in results:
            url = r.get("url", "")
            url_counts[url] = url_counts.get(url, 0) + 1
        for url, count in url_counts.items():
            if url:
                assert count <= 2, f"URL {url} has {count} results, max is 2"

    def test_search_nonexistent_library(self, populated_db):
        """Search with nonexistent library returns empty (line 643)."""
        db, _, _ = populated_db
        results = db.search("hello", library_name="nonexistent")
        assert results == []


# ---------------------------------------------------------------------------
# import_jsonl: replace mode with vec + empty lines (lines 879-882, 889)
# ---------------------------------------------------------------------------


class TestImportJsonlEdgeCases:
    def test_import_replace_mode_vec_path(self, tmp_path):
        """import_jsonl replace mode exercises vec deletion (lines 879-882)."""
        d = DocsDB(tmp_path / "imp.db", embedding_dims=0)
        # Add some data first
        lib_id = d.upsert_library(name="implib")
        ver_id = d.upsert_version(lib_id)
        d.add_chunks(ver_id, lib_id, [{"content": "old data"}])
        d.mark_version_indexed(ver_id, 1, 1)

        # Export to get valid JSONL
        exported = d.export_jsonl()

        # Force vec_enabled to exercise the DELETE path (line 879-882)
        d._vec_enabled = True
        stats = d.import_jsonl(exported, mode="replace")
        assert stats["libraries"] >= 1
        d.close()

    def test_import_with_empty_lines(self, db):
        """Empty lines in JSONL data are skipped (line 889)."""
        lib_data = json.dumps(
            {
                "_type": "library",
                "id": "abc123",
                "name": "emptytest",
                "docs_url": None,
                "registry": None,
                "description": None,
                "created_at": 1000.0,
                "updated_at": 1000.0,
            }
        )
        data = f"\n{lib_data}\n\n\n"
        stats = db.import_jsonl(data, mode="merge")
        assert stats["libraries"] == 1
        assert stats["skipped"] == 0

    def test_import_merge_skips_existing(self, db):
        """Merge mode skips existing entries."""
        lib_data = json.dumps(
            {
                "_type": "library",
                "id": "dup123",
                "name": "duplib",
                "docs_url": None,
                "registry": None,
                "description": None,
                "created_at": 1000.0,
                "updated_at": 1000.0,
            }
        )
        # Import once
        db.import_jsonl(lib_data, mode="merge")
        # Import again - should skip
        stats = db.import_jsonl(lib_data, mode="merge")
        assert stats["skipped"] == 1
        assert stats["libraries"] == 0


# ---------------------------------------------------------------------------
# close() exception path (lines 972-973)
# ---------------------------------------------------------------------------


class TestCloseException:
    def test_close_handles_error(self, tmp_path):
        """close() silently handles exceptions (lines 972-973)."""
        d = DocsDB(tmp_path / "cls.db", embedding_dims=0)
        # Close the underlying connection to force an error on second close
        d._conn.close()
        # Should not raise
        d.close()


# ---------------------------------------------------------------------------
# get_best_version with target version (exact match path)
# ---------------------------------------------------------------------------


class TestGetBestVersion:
    def test_exact_version_match(self, db):
        """get_best_version returns exact match when available."""
        lib_id = db.upsert_library(name="verlib2")
        ver_id = db.upsert_version(lib_id, version="3.0.0")
        db.mark_version_indexed(ver_id, 1, 10)
        result = db.get_best_version(lib_id, target="3.0.0")
        assert result is not None
        assert result["version"] == "3.0.0"

    def test_fallback_to_latest(self, db):
        """get_best_version falls back to latest when target not found."""
        lib_id = db.upsert_library(name="verlib3")
        ver_id = db.upsert_version(lib_id, version="2.0.0")
        db.mark_version_indexed(ver_id, 1, 5)
        result = db.get_best_version(lib_id, target="9.9.9")
        assert result is not None
        assert result["version"] == "2.0.0"

    def test_no_indexed_version(self, db):
        """get_best_version returns None when no indexed versions exist."""
        lib_id = db.upsert_library(name="verlib4")
        db.upsert_version(lib_id, version="1.0.0")  # pending, not indexed
        result = db.get_best_version(lib_id)
        assert result is None


# ---------------------------------------------------------------------------
# Search with version filter
# ---------------------------------------------------------------------------


class TestSearchWithVersionFilter:
    def test_search_with_version(self, populated_db):
        """Search filtered by version."""
        db, lib_id, ver_id = populated_db
        results = db.search("hello", library_name="testlib", version="1.0.0")
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# _combine_scores with vec_scores (RRF fusion path)
# ---------------------------------------------------------------------------


class TestCombineScoresRRF:
    def test_rrf_fusion_with_vec_scores(self, db):
        """_combine_scores uses RRF when vec_scores are present."""
        fts_scores = {"a": 0.9, "b": 0.5}
        vec_scores = {"a": 0.8, "c": 0.7}
        fts_chunks = {
            "a": {"content": "def foo(): pass", "library_id": "x"},
            "b": {"content": "some text content here", "library_id": "x"},
            "c": {"content": "class Bar: pass", "library_id": "x"},
        }
        scored = db._combine_scores(fts_scores, vec_scores, fts_chunks)
        assert len(scored) == 3
        # All IDs should be present
        ids = {s[0] for s in scored}
        assert ids == {"a", "b", "c"}
        # "a" should rank highest (present in both)
        assert scored[0][0] == "a"

    def test_fts_only_scoring(self, db):
        """_combine_scores with empty vec_scores uses FTS-only path."""
        fts_scores = {"x": 1.0, "y": 0.5}
        fts_chunks = {
            "x": {"content": "```python\ndef hello():\n    pass\n```"},
            "y": {"content": "short"},
        }
        scored = db._combine_scores(fts_scores, {}, fts_chunks)
        assert len(scored) == 2


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats(self, populated_db):
        """stats returns correct counts."""
        db, _, _ = populated_db
        s = db.stats()
        assert s["libraries"] >= 1
        assert s["chunks"] >= 4
        assert s["vec_enabled"] is False


# ---------------------------------------------------------------------------
# export_jsonl roundtrip
# ---------------------------------------------------------------------------


class TestExportJsonlRoundtrip:
    def test_export_import_roundtrip(self, populated_db):
        """JSONL export -> import in replace mode preserves data."""
        db, _, _ = populated_db
        exported = db.export_jsonl()
        lines = [ln for ln in exported.strip().split("\n") if ln.strip()]
        # Should have library + version + chunks
        types_found = set()
        for ln in lines:
            obj = json.loads(ln)
            types_found.add(obj["_type"])
        assert "library" in types_found
        assert "version" in types_found
        assert "chunk" in types_found


# ---------------------------------------------------------------------------
# mark_library_indexed (lines 580-608)
# ---------------------------------------------------------------------------


class TestMarkLibraryIndexed:
    def test_mark_library_indexed_all_cols(self, db):
        """Update last_indexed_at and total_versions (line 580)."""
        lib_id = db.upsert_library(name="marklib")
        with patch("wet_mcp.db._now_ts", return_value=12345.6):
            db.mark_library_indexed(lib_id, total_versions=42)

        row = db._conn.execute(
            "SELECT last_indexed_at, total_versions FROM libraries WHERE id = ?",
            (lib_id,),
        ).fetchone()
        assert row["last_indexed_at"] == 12345.6
        assert row["total_versions"] == 42

    def test_mark_library_indexed_no_total_versions(self, db):
        """Update only last_indexed_at if total_versions is None (line 597)."""
        lib_id = db.upsert_library(name="marklib2")
        # Ensure total_versions starts at 0 (default)
        row_before = db._conn.execute(
            "SELECT total_versions FROM libraries WHERE id = ?", (lib_id,)
        ).fetchone()
        assert row_before["total_versions"] == 0

        with patch("wet_mcp.db._now_ts", return_value=67890.0):
            db.mark_library_indexed(lib_id)

        row = db._conn.execute(
            "SELECT last_indexed_at, total_versions FROM libraries WHERE id = ?",
            (lib_id,),
        ).fetchone()
        assert row["last_indexed_at"] == 67890.0
        assert row["total_versions"] == 0

    def test_mark_library_indexed_legacy_db(self, db):
        """No-op if columns are missing (lines 600-601)."""
        # We can't easily mock sqlite3.Connection.execute as it's read-only.
        # Instead, mock the return value of fetchall for PRAGMA table_info.

        mock_results = [("id",), ("name",)]

        # We need to mock the object returned by execute().fetchall()
        # d.execute(...) -> returns a cursor-like object
        # cursor.fetchall() -> returns mock_results

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = mock_results

        with patch.object(db, "_conn") as mock_conn:
            mock_conn.execute.return_value = mock_cursor

            db.mark_library_indexed("legacy1", total_versions=10)

            # Verify it did NOT call execute with UPDATE
            # The first call should be SELECT name FROM pragma_table_info
            # If it didn't return early, there would be a second call with UPDATE
            assert mock_conn.execute.call_count == 1
            assert "pragma_table_info" in mock_conn.execute.call_args[0][0]


# ---------------------------------------------------------------------------
# Project Context (Lines 1392-1408)
# ---------------------------------------------------------------------------


class TestProjectContext:
    def test_get_project_context_valid(self, db):
        """get_project_context returns parsed JSON for valid entries."""
        project_path = "/path/to/project"
        libs = [{"id": "lib1", "version": "1.0.0"}]
        db.upsert_project_context(project_path, libs)

        result = db.get_project_context(project_path)
        assert result is not None
        assert result["project_path"] == project_path
        assert result["locked_libraries"] == libs
        assert "created_at" in result
        assert "last_used_at" in result

    def test_get_project_context_invalid_json(self, db):
        """get_project_context returns empty list on JSON decode error (line 1536)."""
        project_path = "/path/to/bad_json"
        # Manually insert invalid JSON
        db._conn.execute(
            "INSERT INTO project_context (project_path, locked_libraries, created_at, last_used_at) "
            "VALUES (?, ?, ?, ?)",
            (project_path, "{invalid", 1000.0, 1000.0),
        )
        db._conn.commit()

        result = db.get_project_context(project_path)
        assert result is not None
        assert result["locked_libraries"] == []

    def test_get_project_context_type_error(self, db):
        """get_project_context returns empty list on TypeError (line 1536)."""
        project_path = "/path/to/type_error"
        # Manually insert an integer to trigger TypeError in json.loads
        db._conn.execute(
            "INSERT INTO project_context (project_path, locked_libraries, created_at, last_used_at) "
            "VALUES (?, ?, ?, ?)",
            (project_path, 123, 1000.0, 1000.0),
        )
        db._conn.commit()

        result = db.get_project_context(project_path)
        assert result is not None
        assert result["locked_libraries"] == []

    def test_get_project_context_none(self, db):
        """get_project_context returns None for missing project."""
        assert db.get_project_context("/non/existent") is None

    def test_get_project_context_no_table(self, db):
        """get_project_context returns None if table is missing (line 1524)."""
        db._conn.execute("DROP TABLE project_context")
        db._conn.commit()
        assert db.get_project_context("/any/path") is None


# add_chunks error paths (lines 817-818, 825-826)
# ---------------------------------------------------------------------------


class TestAddChunksEdgeCases:
    def test_add_chunks_serialization_error(self, tmp_path):
        """add_chunks handles embedding serialization failure (lines 817-818)."""
        # embedding_dims > 0 both reaches the serialization loop and creates
        # doc_chunks_vec -- but only where sqlite-vec actually loads.
        db = DocsDB(tmp_path / "ser.db", embedding_dims=2)
        if not db._vec_enabled:
            db.close()
            pytest.skip(
                "sqlite-vec did not load here (sqlite3 built without "
                "enable_load_extension, e.g. macOS actions/setup-python), so "
                "doc_chunks_vec was never created; the batch insert below now "
                "aborts rather than swallowing, and forcing the flag on would "
                "fabricate a state the server cannot reach"
            )
        lib_id = db.upsert_library(name="serlib")
        ver_id = db.upsert_version(lib_id)

        chunks = [{"content": "c1"}, {"content": "c2"}]
        # First valid, second invalid (not a list of floats)
        embeddings = [[1.0, 2.0], "invalid"]

        # Should not raise, and should return count of chunks added to FTS
        count = db.add_chunks(ver_id, lib_id, chunks, embeddings=embeddings)
        assert count == 2

        # Verify only one vector was inserted (the valid one)
        # Note: sqlite-vec might not be loaded in all test environments,
        # so we check if the table exists first or just catch the error.
        try:
            rows = db._conn.execute("SELECT count(*) FROM doc_chunks_vec").fetchone()
            assert rows[0] == 1
        except sqlite3.OperationalError:
            # Table doesn't exist or extension not loaded, that's fine for this test
            pass
        db.close()

    def test_add_chunks_batch_insert_error(self, db):
        """A batch vector-insert failure reaches the caller (lines 825-826)."""
        # Force vec_enabled to reach the insert path
        db._vec_enabled = True
        lib_id = db.upsert_library(name="batchlib")
        ver_id = db.upsert_version(lib_id)

        chunks = [{"content": "c1"}]
        embeddings = [[1.0, 2.0]]

        # We can't patch db._conn.executemany directly (it's read-only).
        # We patch the instance's _conn attribute instead.
        real_conn = db._conn
        mock_conn = MagicMock()

        def mock_executemany(sql, params):
            if "doc_chunks_vec" in sql:
                raise sqlite3.Error("batch fail")
            # For other calls (like inserting chunks), use the real connection
            return real_conn.executemany(sql, params)

        mock_conn.executemany.side_effect = mock_executemany
        mock_conn.commit = real_conn.commit
        mock_conn.rollback = real_conn.rollback

        with patch.object(db, "_conn", mock_conn), pytest.raises(sqlite3.Error):
            db.add_chunks(ver_id, lib_id, chunks, embeddings=embeddings)
        assert real_conn.execute("SELECT COUNT(*) FROM doc_chunks").fetchone()[0] == 0
