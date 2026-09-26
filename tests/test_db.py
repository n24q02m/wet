"""Tests for src/wet_mcp/db.py — DocsDB with FTS5 hybrid search.

Covers library/version CRUD, FTS5 search scoring (phrase/AND/OR tiers),
JSONL export/import, edge cases (Unicode, empty queries, special characters),
chunk quality scoring, cross-chunk context retrieval, sqlite-vec vector search,
RRF fusion scoring, and tiered FTS fallback.
"""

import importlib.util
import json
import sqlite3
import struct
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: load wet_mcp.db directly from file without triggering the
# package __init__.py (which imports crawl4ai -> numpy, a flaky dep).
# We pre-register stub parent packages and the docs module so that
# ``from wet_mcp.sources.docs import DISCOVERY_VERSION`` resolves cleanly.
# ---------------------------------------------------------------------------
_src_root = Path(__file__).resolve().parent.parent / "src"

# Reuse already-loaded modules so we don't invalidate patches in
# sibling test files that bind names at import time.
if "wet_mcp" not in sys.modules:
    _pkg = types.ModuleType("wet_mcp")
    _pkg.__path__ = [str(_src_root / "wet_mcp")]
    sys.modules["wet_mcp"] = _pkg

if "wet_mcp.sources" not in sys.modules:
    _sources_pkg = types.ModuleType("wet_mcp.sources")
    _sources_pkg.__path__ = [str(_src_root / "wet_mcp" / "sources")]
    sys.modules["wet_mcp.sources"] = _sources_pkg

# Load docs module (lightweight — no crawl4ai dependency)
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

# Now load db module
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
EmbeddingModelMismatch = _db_mod.EmbeddingModelMismatch
_build_fts_queries = _db_mod._build_fts_queries
_chunk_quality_score = _db_mod._chunk_quality_score
_serialize_f32 = _db_mod._serialize_f32


# ---------------------------------------------------------------------------
# sqlite-vec extension availability check.
#
# macOS Python from ``actions/setup-python`` is built against a system
# SQLite compiled WITHOUT ``--enable-loadable-sqlite-extensions``, so
# ``sqlite3.Connection.enable_load_extension`` does not exist. Tests that
# exercise the vector table require the extension to load; on macOS CI we
# skip them rather than fail. Production code already degrades gracefully
# (FTS-only mode), so runtime behaviour is unchanged.
# ---------------------------------------------------------------------------
def _sqlite_vec_loadable() -> bool:
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(":memory:")
    try:
        if not hasattr(conn, "enable_load_extension"):
            return False
        try:
            import sqlite_vec  # noqa: F401
        except ImportError:
            return False
        return True
    finally:
        conn.close()


_SQLITE_VEC_AVAILABLE = _sqlite_vec_loadable()
_requires_sqlite_vec = pytest.mark.skipif(
    not _SQLITE_VEC_AVAILABLE,
    reason=(
        "sqlite-vec extension cannot be loaded on this platform "
        "(sqlite3 built without enable_load_extension, e.g. macOS "
        "actions/setup-python builds)"
    ),
)


@pytest.fixture
def db(tmp_path):
    """Create a fresh DocsDB for each test."""
    db_path = tmp_path / "test_docs.db"
    db = DocsDB(db_path, embedding_dims=0)
    yield db
    db.close()


@pytest.fixture
def db_with_data(db):
    """DB pre-populated with a library, version, and chunks."""
    lib_id = db.upsert_library(
        name="fastapi",
        docs_url="https://fastapi.tiangolo.com",
        registry="pypi",
        description="Modern web framework for Python",
    )
    ver_id = db.upsert_version(lib_id, version="0.100.0")
    chunks = [
        {
            "content": "FastAPI is a modern, fast web framework for building APIs with Python 3.8+.",
            "title": "Introduction",
            "url": "https://fastapi.tiangolo.com/",
            "heading_path": "Introduction",
            "chunk_index": 0,
        },
        {
            "content": "To create a route, use the @app.get() decorator. Path parameters are defined in the URL path.",
            "title": "Routing",
            "url": "https://fastapi.tiangolo.com/tutorial/first-steps/",
            "heading_path": "Tutorial > First Steps",
            "chunk_index": 1,
        },
        {
            "content": "Dependency injection in FastAPI uses the Depends() function. Dependencies can be nested.",
            "title": "Dependencies",
            "url": "https://fastapi.tiangolo.com/tutorial/dependencies/",
            "heading_path": "Tutorial > Dependencies",
            "chunk_index": 2,
        },
        {
            "content": "WebSocket endpoints use @app.websocket() decorator for real-time bidirectional communication.",
            "title": "WebSockets",
            "url": "https://fastapi.tiangolo.com/advanced/websockets/",
            "heading_path": "Advanced > WebSockets",
            "chunk_index": 3,
        },
    ]
    db.add_chunks(ver_id, lib_id, chunks)
    db.mark_version_indexed(ver_id, page_count=4, chunk_count=4)
    return db, lib_id, ver_id


# -----------------------------------------------------------------------
# Library CRUD
# -----------------------------------------------------------------------


class TestLibraryCRUD:
    def test_upsert_and_get_library(self, db):
        """Create a library and retrieve it."""
        lib_id = db.upsert_library(
            name="React",
            docs_url="https://react.dev",
            registry="npm",
            description="UI library",
        )
        assert lib_id
        lib = db.get_library("react")  # name is lowercased
        assert lib is not None
        assert lib["name"] == "react"
        assert lib["docs_url"] == "https://react.dev"
        assert lib["registry"] == "npm"

    def test_upsert_updates_existing(self, db):
        """Upserting same name updates fields, keeps same ID."""
        id1 = db.upsert_library(name="react", docs_url="https://old.dev")
        id2 = db.upsert_library(name="React", docs_url="https://react.dev")
        assert id1 == id2
        lib = db.get_library("react")
        assert lib["docs_url"] == "https://react.dev"

    def test_get_nonexistent_library(self, db):
        assert db.get_library("nonexistent") is None

    def test_library_name_normalization(self, db):
        """Names are lowercased and stripped."""
        db.upsert_library(name="  PyTorch  ")
        lib = db.get_library("pytorch")
        assert lib is not None
        assert lib["name"] == "pytorch"


# -----------------------------------------------------------------------
# Version management
# -----------------------------------------------------------------------


class TestVersionManagement:
    def test_upsert_version(self, db):
        lib_id = db.upsert_library(name="react")
        ver_id = db.upsert_version(lib_id, version="18.2.0")
        assert ver_id
        # Same version returns same ID
        ver_id2 = db.upsert_version(lib_id, version="18.2.0")
        assert ver_id == ver_id2

    def test_get_best_version_exact(self, db_with_data):
        db, lib_id, ver_id = db_with_data
        ver = db.get_best_version(lib_id, "0.100.0")
        assert ver is not None
        assert ver["version"] == "0.100.0"

    def test_get_best_version_latest(self, db_with_data):
        db, lib_id, _ = db_with_data
        ver = db.get_best_version(lib_id)
        assert ver is not None
        assert ver["status"] == "indexed"

    def test_get_best_version_nonexistent(self, db_with_data):
        db, lib_id, _ = db_with_data
        ver = db.get_best_version(lib_id, "99.99.99")
        # Should fallback to latest indexed
        assert ver is not None

    def test_mark_version_indexed(self, db):
        lib_id = db.upsert_library(name="test")
        ver_id = db.upsert_version(lib_id, version="1.0")
        db.mark_version_indexed(ver_id, page_count=5, chunk_count=20)
        ver = db.get_best_version(lib_id, "1.0")
        assert ver["status"] == "indexed"
        assert ver["page_count"] == 5
        assert ver["chunk_count"] == 20


# -----------------------------------------------------------------------
# Chunks & Search
# -----------------------------------------------------------------------


class TestSearch:
    def test_fts_search_basic(self, db_with_data):
        """FTS5 search returns relevant results."""
        db = db_with_data[0]
        results = db.search(query="route decorator", library_name="fastapi")
        assert len(results) > 0
        # The routing chunk should be most relevant
        assert any("route" in r["content"].lower() for r in results)

    def test_fts_search_returns_scored(self, db_with_data):
        """All results have a score > 0."""
        db = db_with_data[0]
        results = db.search(query="dependencies", library_name="fastapi")
        for r in results:
            assert "score" in r
            assert r["score"] > 0

    def test_fts_search_limit(self, db_with_data):
        """Limit parameter is respected."""
        db = db_with_data[0]
        results = db.search(query="FastAPI", library_name="fastapi", limit=2)
        assert len(results) <= 2

    def test_fts_search_no_results(self, db_with_data):
        """Query with no matches returns empty."""
        db = db_with_data[0]
        results = db.search(query="xyznonexistentterm", library_name="fastapi")
        assert results == []

    def test_fts_search_unknown_library(self, db_with_data):
        """Search for nonexistent library returns empty."""
        db = db_with_data[0]
        results = db.search(query="anything", library_name="nonexistent")
        assert results == []

    def test_fts_search_special_characters(self, db):
        """FTS handles special characters gracefully."""
        lib_id = db.upsert_library(name="test")
        ver_id = db.upsert_version(lib_id)
        db.add_chunks(
            ver_id,
            lib_id,
            [
                {"content": "Use @app.get('/items/{item_id}') for path params."},
                {"content": "Query: ?skip=0&limit=10 supports pagination."},
            ],
        )
        # Should not raise even with FTS-hostile characters
        results = db.search(query="@app.get path params", library_name="test")
        assert isinstance(results, list)

    def test_fts_search_unicode(self, db):
        """FTS handles Unicode content properly."""
        lib_id = db.upsert_library(name="i18n-lib")
        ver_id = db.upsert_version(lib_id)
        db.add_chunks(
            ver_id,
            lib_id,
            [
                {"content": "Internationalisation: Bonjour, Hola, Hallo, Xin chao"},
                {"content": "Japanese: Sumimasen, arigatou gozaimasu"},
            ],
        )
        results = db.search(query="Bonjour", library_name="i18n-lib")
        assert len(results) > 0
        assert "Bonjour" in results[0]["content"]

    def test_search_result_format(self, db_with_data):
        """Each result has all expected fields."""
        db = db_with_data[0]
        results = db.search(query="FastAPI", library_name="fastapi")
        assert len(results) > 0
        r = results[0]
        assert "content" in r
        assert "title" in r
        assert "url" in r
        assert "heading_path" in r
        assert "library" in r
        assert "score" in r
        assert r["library"] == "fastapi"

    def test_search_with_version_filter(self, db_with_data):
        """Search filtered to specific version."""
        db, lib_id, _ = db_with_data
        # Add another version with different content
        ver2_id = db.upsert_version(lib_id, "0.99.0")
        db.add_chunks(
            ver2_id,
            lib_id,
            [
                {"content": "Old deprecated routing system uses @app.route()."},
            ],
        )
        db.mark_version_indexed(ver2_id, 1, 1)

        # Search v0.99.0 should find "deprecated"
        results = db.search(
            query="deprecated routing",
            library_name="fastapi",
            version="0.99.0",
        )
        assert any("deprecated" in r["content"].lower() for r in results)


class TestRecencyScoring:
    """Verify scoring components (recency decay removed — docs chunks
    share the same indexing timestamp, making recency meaningless).

    Tests now cover chunk quality scoring and phrase tier queries.
    """

    def test_chunk_quality_with_code(self):
        """Chunks with code blocks get higher quality scores."""
        code_content = "Example:\n```python\napp = FastAPI()\n```\nSome text after."
        no_code = "This is plain documentation text without code examples."
        assert _chunk_quality_score(code_content) > _chunk_quality_score(no_code)

    def test_chunk_quality_long_content(self):
        """Longer content gets moderate quality boost."""
        short = "Short text."
        medium = "x " * 150  # ~300 chars
        long = "x " * 300  # ~600 chars
        assert _chunk_quality_score(long) >= _chunk_quality_score(medium)
        assert _chunk_quality_score(medium) >= _chunk_quality_score(short)

    def test_chunk_quality_link_heavy_penalty(self):
        """Link-heavy TOC chunks are penalized."""
        toc = "\n".join(f"- [Link {i}](https://example.com/{i})" for i in range(10))
        content = "This is real documentation with examples and explanations. " * 5
        assert _chunk_quality_score(content) > _chunk_quality_score(toc)


class TestPhraseTierQueries:
    """Verify the tiered FTS5 query builder (PHRASE > AND > OR)."""

    def test_single_word(self):
        """Single word returns a single prefix query."""
        queries = _build_fts_queries("routing")
        assert len(queries) == 1
        assert queries[0] == '"routing"*'

    def test_multi_word_tiers(self):
        """Multi-word query returns 3 tiers: PHRASE, AND, OR."""
        queries = _build_fts_queries("path parameters")
        assert len(queries) == 3
        # Tier 0: exact phrase
        assert queries[0] == '"path parameters"'
        # Tier 1: AND
        assert "AND" in queries[1]
        # Tier 2: OR
        assert "OR" in queries[2]

    def test_empty_query(self):
        """Empty query returns no tiers."""
        assert _build_fts_queries("") == []
        assert _build_fts_queries("   ") == []

    def test_quotes_escaped(self):
        """Double quotes in input are escaped."""
        queries = _build_fts_queries('say "hello"')
        # Should not break FTS syntax
        assert len(queries) == 3

    def test_phrase_search_ranks_higher(self, db_with_data):
        """Exact phrase match should rank higher than scattered terms."""
        db = db_with_data[0]
        # "path parameters" appears together in routing chunk
        results = db.search(query="path parameters", library_name="fastapi")
        assert len(results) > 0
        # First result should contain both words
        assert "path" in results[0]["content"].lower()


class TestCrossChunkContext:
    """Verify adjacent chunk retrieval in search results."""

    def test_context_before_and_after(self, db):
        """Search results include adjacent chunk content."""
        lib_id = db.upsert_library(name="ctx-test")
        ver_id = db.upsert_version(lib_id)
        chunks = [
            {
                "content": "Chapter 1: Introduction to the framework.",
                "url": "https://example.com/docs",
                "chunk_index": 0,
            },
            {
                "content": "Chapter 2: Routing and path parameters.",
                "url": "https://example.com/docs",
                "chunk_index": 1,
            },
            {
                "content": "Chapter 3: Dependency injection patterns.",
                "url": "https://example.com/docs",
                "chunk_index": 2,
            },
        ]
        db.add_chunks(ver_id, lib_id, chunks)

        results = db.search(query="routing path", library_name="ctx-test")
        assert len(results) > 0
        # Chunk 1 should match "routing path"
        routing_result = next(
            (r for r in results if "routing" in r["content"].lower()), None
        )
        assert routing_result is not None
        # Should have context from adjacent chunks
        assert "context_before" in routing_result
        assert "Introduction" in routing_result["context_before"]
        assert "context_after" in routing_result
        assert "Dependency" in routing_result["context_after"]

    def test_first_chunk_no_context_before(self, db):
        """First chunk has no context_before."""
        lib_id = db.upsert_library(name="first-chunk")
        ver_id = db.upsert_version(lib_id)
        chunks = [
            {
                "content": "First chapter about routing setup.",
                "url": "https://example.com/page",
                "chunk_index": 0,
            },
            {
                "content": "Second chapter about middleware.",
                "url": "https://example.com/page",
                "chunk_index": 1,
            },
        ]
        db.add_chunks(ver_id, lib_id, chunks)

        results = db.search(query="routing setup", library_name="first-chunk")
        assert len(results) > 0
        first = results[0]
        assert "context_before" not in first
        assert "context_after" in first

    def test_last_chunk_no_context_after(self, db):
        """Last chunk has no context_after."""
        lib_id = db.upsert_library(name="last-chunk")
        ver_id = db.upsert_version(lib_id)
        chunks = [
            {
                "content": "Previous chapter about configuration.",
                "url": "https://example.com/page",
                "chunk_index": 0,
            },
            {
                "content": "Final chapter about deployment and routing.",
                "url": "https://example.com/page",
                "chunk_index": 1,
            },
        ]
        db.add_chunks(ver_id, lib_id, chunks)

        results = db.search(query="deployment routing", library_name="last-chunk")
        assert len(results) > 0
        last = next((r for r in results if "deployment" in r["content"].lower()), None)
        assert last is not None
        assert "context_before" in last
        assert "context_after" not in last


class TestChunksCRUD:
    def test_add_and_clear_chunks(self, db):
        lib_id = db.upsert_library(name="test")
        ver_id = db.upsert_version(lib_id)
        count = db.add_chunks(
            ver_id,
            lib_id,
            [
                {"content": "chunk 1"},
                {"content": "chunk 2"},
                {"content": "chunk 3"},
            ],
        )
        assert count == 3
        cleared = db.clear_version_chunks(ver_id)
        assert cleared == 3

    def test_add_chunks_minimal_fields(self, db):
        """Chunks only require content field."""
        lib_id = db.upsert_library(name="minimal")
        ver_id = db.upsert_version(lib_id)
        count = db.add_chunks(ver_id, lib_id, [{"content": "just content"}])
        assert count == 1
        results = db.search(query="just content", library_name="minimal")
        assert len(results) == 1
        assert results[0]["content"] == "just content"


# -----------------------------------------------------------------------
# JSONL Export / Import
# -----------------------------------------------------------------------


class TestJSONLSync:
    def test_export_empty_db(self, db):
        """Exporting empty DB returns empty string."""
        assert db.export_jsonl() == ""

    def test_export_roundtrip(self, db_with_data, tmp_path):
        """Export from one DB, import into another — same data."""
        src_db = db_with_data[0]
        jsonl = src_db.export_jsonl()
        assert jsonl.strip()

        # Parse and verify structure
        lines = [json.loads(line) for line in jsonl.strip().split("\n")]
        types = [item["_type"] for item in lines]
        assert "library" in types
        assert "version" in types
        assert "chunk" in types

        # Import into fresh DB
        dst_db = DocsDB(tmp_path / "dst.db", embedding_dims=0)
        try:
            stats = dst_db.import_jsonl(jsonl, mode="replace")
            assert stats["libraries"] == 1
            assert stats["versions"] == 1
            assert stats["chunks"] == 4

            # Verify data is searchable
            results = dst_db.search(query="route decorator", library_name="fastapi")
            assert len(results) > 0
        finally:
            dst_db.close()

    def test_import_merge_skips_existing(self, db_with_data, tmp_path):
        """Merge mode skips existing records."""
        src_db = db_with_data[0]
        jsonl = src_db.export_jsonl()

        dst_db = DocsDB(tmp_path / "dst.db", embedding_dims=0)
        try:
            # First import
            stats1 = dst_db.import_jsonl(jsonl, mode="merge")
            assert stats1["libraries"] == 1
            assert stats1["skipped"] == 0

            # Second import — all should be skipped
            stats2 = dst_db.import_jsonl(jsonl, mode="merge")
            assert stats2["libraries"] == 0
            assert stats2["skipped"] > 0
        finally:
            dst_db.close()

    def test_import_replace_clears_first(self, db_with_data, tmp_path):
        """Replace mode clears existing data before import."""
        src_db = db_with_data[0]
        jsonl = src_db.export_jsonl()

        dst_db = DocsDB(tmp_path / "dst.db", embedding_dims=0)
        try:
            # First import
            dst_db.import_jsonl(jsonl, mode="replace")

            # Second import with replace — should not fail
            stats = dst_db.import_jsonl(jsonl, mode="replace")
            assert stats["libraries"] == 1
            assert stats["chunks"] == 4
        finally:
            dst_db.close()


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------


class TestEdgeCases:
    def test_close_and_reopen(self, tmp_path):
        """Data persists after close and reopen."""
        db_path = tmp_path / "persist.db"
        db1 = DocsDB(db_path, embedding_dims=0)
        db1.upsert_library(name="persist-test", docs_url="https://example.com")
        db1.close()

        db2 = DocsDB(db_path, embedding_dims=0)
        lib = db2.get_library("persist-test")
        assert lib is not None
        assert lib["docs_url"] == "https://example.com"
        db2.close()

    def test_empty_query(self, db_with_data):
        """Empty query should not crash."""
        db = db_with_data[0]
        results = db.search(query="", library_name="fastapi")
        assert isinstance(results, list)

    def test_single_word_query(self, db_with_data):
        """Single word queries work."""
        db = db_with_data[0]
        results = db.search(query="WebSocket", library_name="fastapi")
        assert len(results) > 0

    def test_multiple_libraries(self, db):
        """Search is scoped to specified library."""
        # Library A
        id_a = db.upsert_library(name="lib-a")
        ver_a = db.upsert_version(id_a)
        db.add_chunks(
            ver_a,
            id_a,
            [
                {"content": "Alpha library routing system."},
            ],
        )
        # Library B
        id_b = db.upsert_library(name="lib-b")
        ver_b = db.upsert_version(id_b)
        db.add_chunks(
            ver_b,
            id_b,
            [
                {"content": "Beta library routing system."},
            ],
        )

        results_a = db.search(query="routing", library_name="lib-a")
        results_b = db.search(query="routing", library_name="lib-b")

        assert all(r["library"] == "lib-a" for r in results_a)
        assert all(r["library"] == "lib-b" for r in results_b)


# -----------------------------------------------------------------------
# sqlite-vec extension loading and vector table creation (lines 141-151, 266-271)
# -----------------------------------------------------------------------


class TestSqliteVecLoading:
    """Test sqlite-vec extension loading paths."""

    @_requires_sqlite_vec
    def test_vec_enabled_when_extension_available(self, tmp_path):
        """When sqlite-vec is available and dims > 0, vec should be enabled."""
        db = DocsDB(tmp_path / "vec_test.db", embedding_dims=4)
        try:
            assert db._vec_enabled is True
            # Verify the vector table was created
            row = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='doc_chunks_vec'"
            ).fetchone()
            assert row is not None
        finally:
            db.close()

    def test_vec_disabled_when_dims_zero(self, tmp_path):
        """When embedding_dims=0, vec should not be enabled."""
        db = DocsDB(tmp_path / "no_vec.db", embedding_dims=0)
        try:
            assert db._vec_enabled is False
        finally:
            db.close()

    def test_vec_disabled_when_extension_fails(self, tmp_path):
        """When sqlite-vec import fails, fallback to FTS-only mode."""
        with patch.dict("sys.modules", {"sqlite_vec": None}):
            db = DocsDB(tmp_path / "no_vec_ext.db", embedding_dims=4)
            try:
                assert db._vec_enabled is False
            finally:
                db.close()

    @_requires_sqlite_vec
    def test_vec_table_not_recreated_on_reopen(self, tmp_path):
        """Re-opening a DB with existing vec table does not error."""
        db_path = tmp_path / "vec_reopen.db"
        db1 = DocsDB(db_path, embedding_dims=4)
        db1.close()
        # Re-open — should not try to CREATE again
        db2 = DocsDB(db_path, embedding_dims=4)
        try:
            assert db2._vec_enabled is True
        finally:
            db2.close()


# -----------------------------------------------------------------------
# _serialize_f32 (line 27)
# -----------------------------------------------------------------------


class TestSerializeF32:
    def test_serialize_roundtrip(self):
        """Serialize and deserialize a float vector."""
        vec = [1.0, 2.5, -3.0, 0.0]
        data = _serialize_f32(vec)
        assert isinstance(data, bytes)
        assert len(data) == 4 * 4  # 4 floats * 4 bytes each
        unpacked = struct.unpack(f"{len(vec)}f", data)
        for a, b in zip(vec, unpacked, strict=True):
            assert abs(a - b) < 1e-6

    def test_serialize_empty_vector(self):
        """Empty vector produces empty bytes."""
        data = _serialize_f32([])
        assert data == b""


# -----------------------------------------------------------------------
# upsert_library() update and insert paths (lines 328-332)
# -----------------------------------------------------------------------


class TestUpsertLibraryPaths:
    def test_upsert_update_registry_and_description(self, db):
        """Updating registry and description on existing library."""
        lib_id = db.upsert_library(name="mylib", docs_url="https://a.com")
        # Update with registry and description
        lib_id2 = db.upsert_library(
            name="mylib", registry="npm", description="A great lib"
        )
        assert lib_id == lib_id2
        lib = db.get_library("mylib")
        assert lib["registry"] == "npm"
        assert lib["description"] == "A great lib"

    def test_upsert_update_only_registry(self, db):
        """Updating only registry leaves description unchanged."""
        db.upsert_library(
            name="mylib", docs_url="https://a.com", description="original"
        )
        db.upsert_library(name="mylib", registry="pypi")
        lib = db.get_library("mylib")
        assert lib["registry"] == "pypi"
        # description should remain from original insert
        assert lib["description"] == "original"

    def test_upsert_update_only_description(self, db):
        """Updating only description leaves registry unchanged."""
        db.upsert_library(name="mylib", registry="npm")
        db.upsert_library(name="mylib", description="updated desc")
        lib = db.get_library("mylib")
        assert lib["registry"] == "npm"
        assert lib["description"] == "updated desc"

    def test_upsert_insert_new_library(self, db):
        """Insert path creates a new library with all fields."""
        lib_id = db.upsert_library(
            name="brand-new",
            docs_url="https://new.dev",
            registry="crates",
            description="A Rust library",
        )
        lib = db.get_library("brand-new")
        assert lib["id"] == lib_id
        assert lib["docs_url"] == "https://new.dev"
        assert lib["registry"] == "crates"
        assert lib["description"] == "A Rust library"


# -----------------------------------------------------------------------
# add_chunks() vector embedding batch insert (lines 526-540)
# -----------------------------------------------------------------------


@_requires_sqlite_vec
class TestAddChunksVec:
    def test_add_chunks_with_embeddings(self, tmp_path):
        """add_chunks inserts vector embeddings when vec is enabled."""
        db = DocsDB(tmp_path / "add_vec.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="emblib")
            ver_id = db.upsert_version(lib_id)
            embeddings = [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
            ]
            count = db.add_chunks(
                ver_id,
                lib_id,
                [
                    {"content": "alpha"},
                    {"content": "beta"},
                    {"content": "gamma"},
                ],
                embeddings=embeddings,
            )
            assert count == 3

            vec_count = db._conn.execute(
                "SELECT COUNT(*) FROM doc_chunks_vec"
            ).fetchone()[0]
            assert vec_count == 3
        finally:
            db.close()

    def test_add_chunks_with_empty_embedding_skipped(self, tmp_path):
        """Empty embeddings in the list are skipped."""
        db = DocsDB(tmp_path / "add_vec_empty.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="emblib2")
            ver_id = db.upsert_version(lib_id)
            embeddings = [
                [1.0, 0.0, 0.0, 0.0],
                [],  # empty — should be skipped
                [0.0, 0.0, 1.0, 0.0],
            ]
            db.add_chunks(
                ver_id,
                lib_id,
                [
                    {"content": "alpha"},
                    {"content": "beta"},
                    {"content": "gamma"},
                ],
                embeddings=embeddings,
            )
            vec_count = db._conn.execute(
                "SELECT COUNT(*) FROM doc_chunks_vec"
            ).fetchone()[0]
            assert vec_count == 2  # only 2 non-empty embeddings
        finally:
            db.close()

    def test_add_chunks_vec_batch_insert_error(self, tmp_path):
        """Batch vec insert error aborts the batch instead of reporting success.

        This used to be swallowed at debug level: ``add_chunks`` returned the
        full chunk count and the caller stamped the version ``indexed`` over a
        database that could not answer a single semantic query.
        """
        db = DocsDB(tmp_path / "add_vec_err.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="emblib3")
            ver_id = db.upsert_version(lib_id)

            # Drop vec table to force insert error
            db._conn.execute("DROP TABLE doc_chunks_vec")
            db._conn.commit()

            embeddings = [[1.0, 0.0, 0.0, 0.0]]
            with pytest.raises(sqlite3.Error):
                db.add_chunks(
                    ver_id,
                    lib_id,
                    [{"content": "test"}],
                    embeddings=embeddings,
                )
            # The doc_chunks rows share the failed transaction.
            remaining = db._conn.execute("SELECT COUNT(*) FROM doc_chunks").fetchone()[
                0
            ]
            assert remaining == 0
        finally:
            db.close()

    def test_add_chunks_no_embeddings_with_vec_enabled(self, tmp_path):
        """add_chunks without embeddings does not touch vec table."""
        db = DocsDB(tmp_path / "no_emb.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="noemblib")
            ver_id = db.upsert_version(lib_id)
            count = db.add_chunks(
                ver_id,
                lib_id,
                [{"content": "no embedding chunk"}],
            )
            assert count == 1
            vec_count = db._conn.execute(
                "SELECT COUNT(*) FROM doc_chunks_vec"
            ).fetchone()[0]
            assert vec_count == 0
        finally:
            db.close()


# -----------------------------------------------------------------------
# search() vec0 KNN constraint regression
# -----------------------------------------------------------------------


@_requires_sqlite_vec
class TestSearchVecKnnConstraint:
    def test_semantic_hits_without_keyword_overlap(self, tmp_path):
        """Regression: vec0 KNN requires a ``k = ?`` constraint; binding the
        candidate limit as a plain ``LIMIT ?`` placeholder raises
        OperationalError ("A LIMIT or 'k = ?' constraint is required on vec0
        knn queries"), which the vector leg swallowed as a warning — so every
        semantic query silently degraded to keyword-only search.

        The query text shares no vocabulary with any chunk, so a hit can only
        come from the vector leg through a real sqlite-vec MATCH.
        """
        db = DocsDB(tmp_path / "knn.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="knnlib")
            ver_id = db.upsert_version(lib_id)
            db.add_chunks(
                ver_id,
                lib_id,
                [
                    {"content": "flurb gorb exfil quux"},
                    {"content": "zibro nathek vorlan"},
                    {"content": "crelt mوندar psiven"},
                ],
                embeddings=[
                    [1.0, 0.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                ],
            )
            rows = db.search(
                "qqwrn zzpelt hvorn",
                limit=3,
                query_embedding=[1.0, 0.0, 0.0, 0.0],
            )
            assert rows, "vector leg dead: no hits without keyword overlap"
            assert rows[0]["content"] == "flurb gorb exfil quux"
        finally:
            db.close()


# -----------------------------------------------------------------------
# clear_version_chunks() vec deletion (lines 550-557)
# -----------------------------------------------------------------------


@_requires_sqlite_vec
class TestClearVersionChunksVec:
    def test_clear_version_chunks_with_vec(self, tmp_path):
        """clear_version_chunks removes vec entries."""
        db = DocsDB(tmp_path / "clear_vec.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="clearlib")
            ver_id = db.upsert_version(lib_id)
            db.add_chunks(
                ver_id,
                lib_id,
                [{"content": "to clear"}],
                embeddings=[[1.0, 2.0, 3.0, 4.0]],
            )
            vec_before = db._conn.execute(
                "SELECT COUNT(*) FROM doc_chunks_vec"
            ).fetchone()[0]
            assert vec_before == 1

            cleared = db.clear_version_chunks(ver_id)
            assert cleared == 1

            vec_after = db._conn.execute(
                "SELECT COUNT(*) FROM doc_chunks_vec"
            ).fetchone()[0]
            assert vec_after == 0
        finally:
            db.close()

    def test_clear_version_chunks_vec_error_handled(self, tmp_path):
        """clear_version_chunks handles vec deletion errors gracefully."""
        db = DocsDB(tmp_path / "clear_vec_err.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="clearlib2")
            ver_id = db.upsert_version(lib_id)
            db.add_chunks(ver_id, lib_id, [{"content": "to clear"}])

            # Drop vec table to force error
            db._conn.execute("DROP TABLE doc_chunks_vec")
            db._conn.commit()

            # Should not raise
            cleared = db.clear_version_chunks(ver_id)
            assert cleared == 1
        finally:
            db.close()


# -----------------------------------------------------------------------
# _combine_scores() RRF fusion scoring (lines 581-598)
# -----------------------------------------------------------------------


class TestCombineScores:
    def test_rrf_fusion_with_both_signals(self, db):
        """RRF fusion combines FTS and vec scores."""
        fts_scores = {"a": 0.9, "b": 0.5, "c": 0.1}
        vec_scores = {"a": 0.2, "b": 0.8, "c": 0.5}
        fts_chunks = {
            "a": {"content": "def foo(): pass"},
            "b": {"content": "some text"},
            "c": {"content": "more text"},
        }
        scored = db._combine_scores(fts_scores, vec_scores, fts_chunks)
        assert len(scored) == 3
        # All tuples have (id, score)
        for cid, score in scored:
            assert isinstance(cid, str)
            assert isinstance(score, float)
        # Sorted descending
        scores_only = [s for _, s in scored]
        assert scores_only == sorted(scores_only, reverse=True)

    def test_fts_only_scoring(self, db):
        """FTS-only scoring when no vec scores provided."""
        fts_scores = {"a": 0.9, "b": 0.3}
        vec_scores = {}
        fts_chunks = {
            "a": {"content": "def foo(): pass"},
            "b": {"content": "short"},
        }
        scored = db._combine_scores(fts_scores, vec_scores, fts_chunks)
        assert len(scored) == 2
        # "a" should score higher (better FTS + code quality)
        assert scored[0][0] == "a"

    def test_rrf_with_missing_chunk_data(self, db):
        """RRF handles missing chunk data (quality defaults to 0)."""
        fts_scores = {"a": 0.9}
        vec_scores = {"a": 0.5, "b": 0.8}
        fts_chunks = {"a": {"content": "some text"}}
        scored = db._combine_scores(fts_scores, vec_scores, fts_chunks)
        assert len(scored) == 2

    def test_fts_only_with_missing_chunk(self, db):
        """FTS-only with missing chunk data uses quality=0."""
        fts_scores = {"a": 0.9, "b": 0.5}
        fts_chunks = {"a": {"content": "text"}}  # "b" missing
        scored = db._combine_scores(fts_scores, {}, fts_chunks)
        assert len(scored) == 2


# -----------------------------------------------------------------------
# search() vector search via sqlite-vec (lines 712-743)
# -----------------------------------------------------------------------


class TestSearchWithVec:
    def test_vector_search_integration(self, tmp_path):
        """Full hybrid search with FTS + vector."""
        db = DocsDB(tmp_path / "hybrid.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="hybridlib")
            ver_id = db.upsert_version(lib_id)
            chunks = [
                {"content": "Vector search uses embeddings for semantic similarity."},
                {"content": "FTS search uses BM25 text matching for retrieval."},
                {"content": "Hybrid combines both FTS and vector approaches."},
            ]
            embeddings = [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.5, 0.5, 0.0, 0.0],
            ]
            db.add_chunks(ver_id, lib_id, chunks, embeddings=embeddings)
            db.mark_version_indexed(ver_id, 3, 3)

            # Search with query embedding — vec search may fail on some
            # sqlite-vec versions but FTS fallback should still work
            results = db.search(
                query="vector embeddings",
                library_name="hybridlib",
                query_embedding=[0.9, 0.1, 0.0, 0.0],
            )
            assert len(results) > 0
            # Results should have scores >= 0
            for r in results:
                assert r["score"] >= 0
        finally:
            db.close()

    def test_vector_search_with_version_filter(self, tmp_path):
        """Vector search respects version filter."""
        db = DocsDB(tmp_path / "vec_ver.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="vecverlib")
            ver1 = db.upsert_version(lib_id, "1.0")
            ver2 = db.upsert_version(lib_id, "2.0")
            db.add_chunks(
                ver1,
                lib_id,
                [{"content": "Version one content about search."}],
                embeddings=[[1.0, 0.0, 0.0, 0.0]],
            )
            db.add_chunks(
                ver2,
                lib_id,
                [{"content": "Version two content about search."}],
                embeddings=[[0.0, 1.0, 0.0, 0.0]],
            )
            db.mark_version_indexed(ver1, 1, 1)
            db.mark_version_indexed(ver2, 1, 1)

            results = db.search(
                query="search",
                library_name="vecverlib",
                version="1.0",
                query_embedding=[1.0, 0.0, 0.0, 0.0],
            )
            assert len(results) > 0
            assert "one" in results[0]["content"].lower()
        finally:
            db.close()

    @_requires_sqlite_vec
    def test_vector_search_error_handled(self, tmp_path):
        """Vector search errors are caught gracefully."""
        db = DocsDB(tmp_path / "vec_err.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="vecerrlib")
            ver_id = db.upsert_version(lib_id)
            db.add_chunks(ver_id, lib_id, [{"content": "test search content"}])
            db.mark_version_indexed(ver_id, 1, 1)

            # Drop vec table to force search error
            db._conn.execute("DROP TABLE doc_chunks_vec")
            db._conn.commit()

            # Should not raise — falls back to FTS only
            results = db.search(
                query="test search",
                library_name="vecerrlib",
                query_embedding=[1.0, 0.0, 0.0, 0.0],
            )
            assert isinstance(results, list)
        finally:
            db.close()


# -----------------------------------------------------------------------
# FTS search tiered fallback: PHRASE -> AND -> OR (lines 694-697)
# -----------------------------------------------------------------------


class TestFTSTieredFallback:
    def test_fts_error_continues_to_next_tier(self, db):
        """FTS search continues to next tier on error."""
        lib_id = db.upsert_library(name="tiertest")
        ver_id = db.upsert_version(lib_id)
        db.add_chunks(
            ver_id,
            lib_id,
            [
                {"content": "alpha beta gamma delta"},
                {"content": "epsilon zeta eta theta"},
            ],
        )

        # Search with a multi-word query exercises all tiers
        results = db.search(query="alpha gamma", library_name="tiertest")
        assert isinstance(results, list)

    def test_search_url_diversity_limit(self, db):
        """URL diversity limit caps results per URL (lines 804, 807, 812)."""
        lib_id = db.upsert_library(name="urlcap")
        ver_id = db.upsert_version(lib_id)
        # Create many chunks from same URL
        chunks = [
            {
                "content": f"Chunk {i} about routing and parameters in detail.",
                "url": "https://example.com/same-page",
                "chunk_index": i,
            }
            for i in range(6)
        ]
        db.add_chunks(ver_id, lib_id, chunks)

        results = db.search(query="routing parameters", library_name="urlcap", limit=10)
        # max_per_url = 2, so at most 2 results from same URL
        same_url_count = sum(
            1 for r in results if r["url"] == "https://example.com/same-page"
        )
        assert same_url_count <= 2

    def test_search_skips_missing_chunk(self, db):
        """Search skips entries where chunk data is missing (line 772, 807)."""
        lib_id = db.upsert_library(name="skiptest")
        ver_id = db.upsert_version(lib_id)
        db.add_chunks(
            ver_id,
            lib_id,
            [{"content": "searchable content here"}],
        )
        results = db.search(query="searchable content", library_name="skiptest")
        assert len(results) > 0


# -----------------------------------------------------------------------
# _chunk_quality_score edge cases (lines 112, 117, 119)
# -----------------------------------------------------------------------


class TestChunkQualityEdgeCases:
    def test_moderate_link_ratio_penalty(self):
        """Link ratio between 0.3 and 0.5 gets moderate penalty (line 112)."""
        # 4 out of 10 lines are links = 0.4 ratio
        lines = []
        for i in range(6):
            lines.append(f"Regular text line {i} about something.")
        for i in range(4):
            lines.append(f"- [Link {i}](https://example.com/{i})")
        content = "\n".join(lines)
        score = _chunk_quality_score(content)
        # Should be penalized but not as much as >0.5 ratio
        # Compare with no-link version
        no_links = "\n".join(f"Regular text line {i}." for i in range(10))
        assert _chunk_quality_score(no_links) > score

    def test_many_directives_penalty(self):
        """More than 3 directives gets -2.0 penalty (line 117)."""
        content = "\n".join(
            [
                "!!! note Some note",
                "!!! warning A warning",
                "!!! tip A tip",
                "!!! danger Danger",
                "Some actual content here.",
            ]
        )
        score_heavy = _chunk_quality_score(content)
        # Compare against same content without directives (same length range)
        content_clean = "\n".join(
            [
                "First paragraph of real docs.",
                "Second paragraph of real docs.",
                "Third paragraph of real docs.",
                "Fourth paragraph of real docs.",
                "Some actual content here.",
            ]
        )
        score_clean = _chunk_quality_score(content_clean)
        assert score_clean >= score_heavy

    def test_moderate_directives_penalty(self):
        """1-3 directives gets -1.0 penalty (line 119)."""
        content = "\n".join(
            [
                "!!! note Some note",
                "!!! warning A warning",
                "Regular content about usage.",
            ]
        )
        score = _chunk_quality_score(content)
        # Should be penalized less than 4+ directives
        content_heavy = "\n".join(
            [
                "!!! note 1",
                "!!! note 2",
                "!!! note 3",
                "!!! note 4",
                "Content.",
            ]
        )
        assert score >= _chunk_quality_score(content_heavy)

    def test_init_invalid_dims_type(self, tmp_path):
        """Test that invalid types for embedding_dims raise ValueError."""

        class EvilInt(int):
            def __str__(self):
                return "1]; DROP TABLE doc_chunks_vec; --"

        with pytest.raises(ValueError, match="embedding_dims must be an integer"):
            DocsDB(tmp_path / "invalid.db", embedding_dims=EvilInt(1))

        with pytest.raises(ValueError, match="embedding_dims must be an integer"):
            DocsDB(tmp_path / "invalid2.db", embedding_dims="4")

    def test_chunk_quality_with_definitions(self):
        """Chunks with function/class definitions get boosted."""
        code = "def foo():\n    pass\n\nclass Bar:\n    pass\n\nfunc baz() {}\n"
        plain = "This is just plain text without any definitions."
        assert _chunk_quality_score(code) > _chunk_quality_score(plain)

    def test_chunk_quality_with_docstrings(self):
        """Chunks with docstrings/doc comments get boosted."""
        documented = (
            '"""This is a docstring."""\n# Args:\n#   x: value\n# Returns:\n#   result'
        )
        plain = "Regular text without documentation patterns."
        assert _chunk_quality_score(documented) > _chunk_quality_score(plain)


# -----------------------------------------------------------------------
# upsert_version() update path (lines 431-435)
# -----------------------------------------------------------------------


class TestUpsertVersionUpdate:
    def test_upsert_version_updates_docs_url(self, db):
        """Upserting existing version with docs_url updates it."""
        lib_id = db.upsert_library(name="verlib")
        ver_id1 = db.upsert_version(lib_id, "1.0", docs_url="https://old.com")
        ver_id2 = db.upsert_version(lib_id, "1.0", docs_url="https://new.com")
        assert ver_id1 == ver_id2
        # Version exists but not indexed, so get_best_version may not return it
        # Check directly
        row = db._conn.execute(
            "SELECT docs_url FROM versions WHERE id = ?", (ver_id1,)
        ).fetchone()
        assert row["docs_url"] == "https://new.com"


# -----------------------------------------------------------------------
# import_jsonl() replace and merge modes (lines 879-882, 889)
# -----------------------------------------------------------------------


class TestImportJSONLModes:
    def test_import_replace_with_vec(self, tmp_path):
        """Replace mode clears vec table when vec is enabled (lines 879-882)."""
        db = DocsDB(tmp_path / "import_vec.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="importlib")
            ver_id = db.upsert_version(lib_id)
            db.add_chunks(
                ver_id,
                lib_id,
                [{"content": "old vec chunk"}],
                embeddings=[[1.0, 0.0, 0.0, 0.0]],
            )

            # Export first
            jsonl = db.export_jsonl()

            # Replace mode should clear vec table
            stats = db.import_jsonl(jsonl, mode="replace")
            assert stats["libraries"] == 1
            assert stats["chunks"] == 1
        finally:
            db.close()

    @_requires_sqlite_vec
    def test_import_replace_vec_error_handled(self, tmp_path):
        """Replace mode handles vec table deletion errors (lines 879-882)."""
        db = DocsDB(tmp_path / "import_vec_err.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="importlib2")
            ver_id = db.upsert_version(lib_id)
            db.add_chunks(ver_id, lib_id, [{"content": "test chunk"}])
            jsonl = db.export_jsonl()

            # Drop vec table to force error
            db._conn.execute("DROP TABLE doc_chunks_vec")
            db._conn.commit()

            # Should not raise
            stats = db.import_jsonl(jsonl, mode="replace")
            assert stats["libraries"] == 1
        finally:
            db.close()

    def test_import_skips_empty_lines(self, db):
        """Import skips empty lines in JSONL (line 889)."""
        now = _db_mod._now_ts()
        data = (
            json.dumps(
                {
                    "_type": "library",
                    "id": "lib1",
                    "name": "skiplib",
                    "docs_url": None,
                    "registry": None,
                    "description": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            + "\n\n\n"
        )
        stats = db.import_jsonl(data, mode="merge")
        assert stats["libraries"] == 1
        assert stats["skipped"] == 0

    def test_import_merge_skips_existing_versions(self, db):
        """Merge mode skips existing version records."""
        now = _db_mod._now_ts()
        lib_data = json.dumps(
            {
                "_type": "library",
                "id": "libA",
                "name": "mergelib",
                "docs_url": None,
                "registry": None,
                "description": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        ver_data = json.dumps(
            {
                "_type": "version",
                "id": "verA",
                "library_id": "libA",
                "version": "1.0",
                "docs_url": None,
                "indexed_at": now,
                "page_count": 0,
                "chunk_count": 0,
                "status": "indexed",
            }
        )
        chunk_data = json.dumps(
            {
                "_type": "chunk",
                "id": "chkA",
                "version_id": "verA",
                "library_id": "libA",
                "url": "",
                "title": "",
                "chunk_index": 0,
                "content": "merge chunk",
                "heading_path": "",
                "created_at": now,
            }
        )
        data = "\n".join([lib_data, ver_data, chunk_data])

        # First import
        stats1 = db.import_jsonl(data, mode="merge")
        assert stats1["libraries"] == 1
        assert stats1["versions"] == 1
        assert stats1["chunks"] == 1

        # Second import — all skipped
        stats2 = db.import_jsonl(data, mode="merge")
        assert stats2["skipped"] == 3
        assert stats2["libraries"] == 0
        assert stats2["versions"] == 0
        assert stats2["chunks"] == 0


# -----------------------------------------------------------------------
# close() error handling (lines 972-973)
# -----------------------------------------------------------------------


class TestCloseErrorHandling:
    def test_close_twice_no_error(self, tmp_path):
        """Calling close() twice does not raise."""
        db = DocsDB(tmp_path / "close_twice.db", embedding_dims=0)
        db.close()
        db.close()  # Should not raise

    def test_close_with_broken_connection(self, tmp_path):
        """close() handles broken connections gracefully (lines 972-973)."""
        db = DocsDB(tmp_path / "close_broken.db", embedding_dims=0)
        # Replace _conn with a mock whose close() raises
        mock_conn = MagicMock()
        mock_conn.close.side_effect = Exception("connection error")
        db._conn = mock_conn
        db.close()  # Should not raise


# -----------------------------------------------------------------------
# stats() (lines 287-291)
# -----------------------------------------------------------------------


class TestStats:
    def test_stats_empty_db(self, db):
        """Stats on empty DB returns zeros."""
        stats = db.stats()
        assert stats["libraries"] == 0
        assert stats["chunks"] == 0
        assert stats["vec_enabled"] is False

    def test_stats_with_data(self, db_with_data):
        """Stats reflects actual counts."""
        db = db_with_data[0]
        stats = db.stats()
        assert stats["libraries"] == 1
        assert stats["chunks"] == 4
        assert stats["vec_enabled"] is False

    @_requires_sqlite_vec
    def test_stats_vec_enabled(self, tmp_path):
        """Stats shows vec_enabled when extension loaded."""
        db = DocsDB(tmp_path / "stats_vec.db", embedding_dims=4)
        try:
            stats = db.stats()
            assert stats["vec_enabled"] is True
        finally:
            db.close()


# -----------------------------------------------------------------------
# Remaining uncovered lines: targeted tests
# -----------------------------------------------------------------------


class TestSerializeEmbeddingError:
    """Cover lines 531-532: embedding serialization failure."""

    @_requires_sqlite_vec
    def test_add_chunks_bad_embedding_caught(self, tmp_path):
        """A single bad embedding is caught, others still inserted."""
        db = DocsDB(tmp_path / "bad_emb.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="bademb")
            ver_id = db.upsert_version(lib_id)

            # Patch _serialize_f32 to fail on first call only
            call_count = [0]
            original_serialize = _db_mod._serialize_f32

            def flaky_serialize(vec):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise ValueError("bad embedding data")
                return original_serialize(vec)

            with patch.object(_db_mod, "_serialize_f32", side_effect=flaky_serialize):
                count = db.add_chunks(
                    ver_id,
                    lib_id,
                    [{"content": "chunk A"}, {"content": "chunk B"}],
                    embeddings=[[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
                )
            assert count == 2  # Both doc chunks inserted

            # Only second embedding should have been inserted (first failed)
            vec_count = db._conn.execute(
                "SELECT COUNT(*) FROM doc_chunks_vec"
            ).fetchone()[0]
            assert vec_count == 1
        finally:
            db.close()


class TestFTSSearchError:
    """Cover lines 694-697: FTS MATCH error caught and continues."""

    def test_fts_error_on_first_tier_falls_through(self, db):
        """FTS error on one tier continues to the next."""
        lib_id = db.upsert_library(name="ftserr")
        ver_id = db.upsert_version(lib_id)
        db.add_chunks(ver_id, lib_id, [{"content": "hello world test"}])

        # sqlite3.Connection attributes are read-only, so wrap with a proxy
        original_conn = db._conn
        original_execute = original_conn.execute
        call_count = [0]

        class ConnProxy:
            """Proxy that intercepts execute() calls."""

            def __getattr__(self, name):
                return getattr(original_conn, name)

            def execute(self, sql, params=None):
                if "MATCH" in str(sql):
                    call_count[0] += 1
                    if call_count[0] == 1:
                        raise Exception("FTS synthetic error")
                if params is not None:
                    return original_execute(sql, params)
                return original_execute(sql)

        db._conn = ConnProxy()
        try:
            results = db.search(query="hello world", library_name="ftserr")
        finally:
            db._conn = original_conn
        # Should still return results from later tiers
        assert isinstance(results, list)


class TestSearchLimitBreak:
    """Cover lines 804, 807: limit break and missing chunk skip."""

    def test_search_hits_limit(self, db):
        """Search stops collecting once limit is reached (line 804)."""
        lib_id = db.upsert_library(name="limitlib")
        ver_id = db.upsert_version(lib_id)
        # Create chunks with distinct URLs to avoid URL diversity filter
        chunks = [
            {
                "content": f"Documentation about routing features part {i}.",
                "url": f"https://example.com/page-{i}",
                "chunk_index": 0,
            }
            for i in range(10)
        ]
        db.add_chunks(ver_id, lib_id, chunks)

        results = db.search(query="routing features", library_name="limitlib", limit=3)
        assert len(results) <= 3

    def test_search_skips_chunk_not_in_fts_chunks(self, db):
        """When _combine_scores returns IDs not in fts_chunks, they are skipped (line 807)."""
        lib_id = db.upsert_library(name="skiplib")
        ver_id = db.upsert_version(lib_id)
        db.add_chunks(ver_id, lib_id, [{"content": "data for skipping test"}])

        # Monkey-patch _combine_scores to inject a phantom ID
        original_combine = db._combine_scores

        def patched_combine(fts_scores, vec_scores, fts_chunks):
            result = original_combine(fts_scores, vec_scores, fts_chunks)
            # Inject a phantom ID that does not exist in fts_chunks
            result.insert(0, ("phantom_id_not_in_chunks", 99.0))
            return result

        with patch.object(db, "_combine_scores", side_effect=patched_combine):
            results = db.search(query="data skipping", library_name="skiplib")
        # Phantom ID should be skipped, real results returned
        assert all(r["content"] != "" for r in results)


class TestImportBlankLines:
    """Cover line 889: blank lines in JSONL import."""

    def test_import_only_blank_lines(self, db):
        """Import data that is only blank lines."""
        stats = db.import_jsonl("\n\n\n", mode="merge")
        assert stats["libraries"] == 0
        assert stats["versions"] == 0
        assert stats["chunks"] == 0
        assert stats["skipped"] == 0


class TestVecSearchChunkLoading:
    """Cover lines 732-741: vec search loads chunk data not in FTS."""

    @_requires_sqlite_vec
    def test_vec_search_loads_non_fts_chunks(self, tmp_path):
        """When vec search returns chunks not found by FTS, they get loaded."""

        db = DocsDB(tmp_path / "vec_load.db", embedding_dims=4)
        try:
            lib_id = db.upsert_library(name="vecloadlib")
            ver_id = db.upsert_version(lib_id)
            # Create chunks — one FTS-findable, one only vec-findable
            chunks = [
                {"content": "This chunk matches the FTS query about searching."},
                {
                    "content": "Completely different topic not matching query terms at all xyz."
                },
            ]
            embeddings = [
                [1.0, 0.0, 0.0, 0.0],
                [0.9, 0.1, 0.0, 0.0],
            ]
            db.add_chunks(ver_id, lib_id, chunks, embeddings=embeddings)
            db.mark_version_indexed(ver_id, 2, 2)

            # Get the actual chunk IDs from DB
            all_chunks = db._conn.execute(
                "SELECT id, content FROM doc_chunks WHERE library_id = ?",
                (lib_id,),
            ).fetchall()
            fts_chunk_id = None
            vec_only_chunk_id = None
            for c in all_chunks:
                if "searching" in c["content"]:
                    fts_chunk_id = c["id"]
                else:
                    vec_only_chunk_id = c["id"]

            # Mock the connection to intercept vec MATCH queries and return
            # fake results including the chunk not found by FTS
            original_conn = db._conn
            original_execute = original_conn.execute

            class VecConnProxy:
                def __getattr__(self, name):
                    return getattr(original_conn, name)

                def execute(self, sql, params=None):
                    if "embedding MATCH" in str(sql):
                        # Return fake vec results as sqlite3.Row objects
                        # by querying a temp table
                        original_execute(
                            "CREATE TEMP TABLE IF NOT EXISTS _fake_vec "
                            "(id TEXT, distance REAL, content TEXT, title TEXT, chunk_index INTEGER, url TEXT, heading_path TEXT, version_id TEXT, library_id TEXT, created_at REAL)"
                        )
                        original_execute("DELETE FROM _fake_vec")

                        vec_only_row = original_execute(
                            "SELECT * FROM doc_chunks WHERE id = ?",
                            (vec_only_chunk_id,),
                        ).fetchone()
                        original_execute(
                            "INSERT INTO _fake_vec VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                vec_only_chunk_id,
                                0.1,
                                vec_only_row["content"],
                                vec_only_row["title"],
                                vec_only_row["chunk_index"],
                                vec_only_row["url"],
                                vec_only_row["heading_path"],
                                vec_only_row["version_id"],
                                vec_only_row["library_id"],
                                vec_only_row["created_at"],
                            ),
                        )
                        fts_row = original_execute(
                            "SELECT * FROM doc_chunks WHERE id = ?", (fts_chunk_id,)
                        ).fetchone()
                        original_execute(
                            "INSERT INTO _fake_vec VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                fts_chunk_id,
                                0.2,
                                fts_row["content"],
                                fts_row["title"],
                                fts_row["chunk_index"],
                                fts_row["url"],
                                fts_row["heading_path"],
                                fts_row["version_id"],
                                fts_row["library_id"],
                                fts_row["created_at"],
                            ),
                        )
                        return original_execute("SELECT * FROM _fake_vec")
                    if params is not None:
                        return original_execute(sql, params)
                    return original_execute(sql)

            db._conn = VecConnProxy()
            try:
                results = db.search(
                    query="searching",
                    library_name="vecloadlib",
                    query_embedding=[0.95, 0.05, 0.0, 0.0],
                )
            finally:
                db._conn = original_conn

            assert len(results) > 0
            # The vec-only chunk should also appear in results via vec search
            all_contents = [r["content"] for r in results]
            assert any("different topic" in c for c in all_contents)
        finally:
            db.close()


# -----------------------------------------------------------------------
# Embedding-model identity guard (store_meta table)
# -----------------------------------------------------------------------
class TestEmbeddingModelIdentityGuard:
    """Guard the docs vector store against silent embedding-model swaps.

    The vector table stores embeddings with no record of which model/dims
    produced them. Switching models silently mixes incompatible vector
    spaces. DocsDB stamps ``(embedding_model, embedding_dims)`` in a
    ``store_meta`` table on first init and raises ``EmbeddingModelMismatch``
    on reopen with a different identity unless reindex is opted in.
    """

    def test_fresh_store_stamps_identity(self, tmp_path):
        """A fresh store records the current model id + dims in store_meta."""
        db = DocsDB(
            tmp_path / "stamp.db",
            embedding_dims=4,
            model_identity="provider/model-a",
        )
        try:
            rows = {
                r["key"]: r["value"]
                for r in db._conn.execute(
                    "SELECT key, value FROM store_meta"
                ).fetchall()
            }
            assert rows["embedding_model"] == "provider/model-a"
            assert rows["embedding_dims"] == "4"
        finally:
            db.close()

    def test_reopen_same_identity_proceeds(self, tmp_path):
        """Reopening with the same (model, dims) does not raise."""
        db_path = tmp_path / "same.db"
        db1 = DocsDB(db_path, embedding_dims=4, model_identity="provider/model-a")
        db1.close()
        db2 = DocsDB(db_path, embedding_dims=4, model_identity="provider/model-a")
        try:
            assert db2._embedding_dims == 4
        finally:
            db2.close()

    def test_reopen_different_identity_raises(self, tmp_path):
        """Reopening with a different model id raises EmbeddingModelMismatch."""
        db_path = tmp_path / "diff.db"
        db1 = DocsDB(db_path, embedding_dims=4, model_identity="provider/model-a")
        db1.close()
        with pytest.raises(EmbeddingModelMismatch) as exc:
            DocsDB(db_path, embedding_dims=4, model_identity="provider/model-b")
        msg = str(exc.value)
        assert "provider/model-a" in msg
        assert "provider/model-b" in msg
        assert "REINDEX_ON_MODEL_CHANGE" in msg

    def test_reopen_different_dims_raises(self, tmp_path):
        """A dims change alone (the most dangerous case) raises."""
        db_path = tmp_path / "dims.db"
        db1 = DocsDB(db_path, embedding_dims=4, model_identity="provider/model-a")
        db1.close()
        with pytest.raises(EmbeddingModelMismatch):
            DocsDB(db_path, embedding_dims=8, model_identity="provider/model-a")

    def test_mismatch_touches_no_data(self, tmp_path):
        """Default mismatch path raises WITHOUT destroying stamped identity."""
        db_path = tmp_path / "safe.db"
        db1 = DocsDB(db_path, embedding_dims=4, model_identity="provider/model-a")
        db1.close()
        with pytest.raises(EmbeddingModelMismatch):
            DocsDB(db_path, embedding_dims=4, model_identity="provider/model-b")
        # Stored identity must be intact (untouched) after the raise.
        db3 = DocsDB(db_path, embedding_dims=4, model_identity="provider/model-a")
        try:
            row = db3._conn.execute(
                "SELECT value FROM store_meta WHERE key = 'embedding_model'"
            ).fetchone()
            assert row["value"] == "provider/model-a"
        finally:
            db3.close()

    @_requires_sqlite_vec
    def test_reindex_on_model_change_drops_and_restamps(self, tmp_path):
        """With reindex opted in, a mismatch drops vectors + re-stamps, no raise."""
        db_path = tmp_path / "reindex.db"
        db1 = DocsDB(db_path, embedding_dims=4, model_identity="provider/model-a")
        try:
            lib_id = db1.upsert_library("reidxlib")
            ver_id = db1.upsert_version(lib_id, "1.0")
            db1.add_chunks(
                ver_id,
                lib_id,
                [{"content": "alpha", "url": "u", "chunk_index": 0}],
                embeddings=[[0.1, 0.2, 0.3, 0.4]],
            )
            vec_count = db1._conn.execute(
                "SELECT COUNT(*) FROM doc_chunks_vec"
            ).fetchone()[0]
            assert vec_count == 1
        finally:
            db1.close()

        # Reopen with a new model id + reindex enabled -> no raise, drop vectors.
        db2 = DocsDB(
            db_path,
            embedding_dims=4,
            model_identity="provider/model-b",
            reindex_on_model_change=True,
        )
        try:
            # Identity re-stamped to the new model.
            row = db2._conn.execute(
                "SELECT value FROM store_meta WHERE key = 'embedding_model'"
            ).fetchone()
            assert row["value"] == "provider/model-b"
            # Vector table cleared (rebuild deferred to the docs-embed pipeline).
            vec_count = db2._conn.execute(
                "SELECT COUNT(*) FROM doc_chunks_vec"
            ).fetchone()[0]
            assert vec_count == 0
        finally:
            db2.close()


# ---------------------------------------------------------------------------
# Seed-vs-indexed separation (metadata_seeded_at)
# ---------------------------------------------------------------------------
_PRE_FIX_LIBRARIES_DDL = """
    CREATE TABLE libraries (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        docs_url TEXT,
        registry TEXT,
        description TEXT,
        canonical_name TEXT,
        homepage TEXT,
        github_url TEXT,
        package_managers TEXT,
        tier INTEGER NOT NULL DEFAULT 2,
        last_indexed_at REAL,
        total_versions INTEGER NOT NULL DEFAULT 0,
        discovery_version INTEGER DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
"""

_PRE_FIX_VERSIONS_DDL = """
    CREATE TABLE versions (
        id TEXT PRIMARY KEY,
        library_id TEXT NOT NULL,
        version TEXT NOT NULL DEFAULT 'latest',
        docs_url TEXT,
        indexed_at REAL,
        page_count INTEGER DEFAULT 0,
        chunk_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        release_date REAL,
        source_url TEXT,
        UNIQUE(library_id, version)
    )
"""


def _make_pre_fix_db(db_path):
    """Build a docs.db in the shape shipped before metadata_seeded_at existed.

    ``seeded-lib`` reproduces the observed bug: a metadata-only Tier 1 seed
    that upsert_library stamped as freshly indexed while holding zero
    versions. ``indexed-lib`` is a genuinely indexed library.
    """
    import sqlite3 as _sqlite3

    conn = _sqlite3.connect(str(db_path))
    conn.execute(_PRE_FIX_LIBRARIES_DDL)
    conn.execute(_PRE_FIX_VERSIONS_DDL)
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


def test_pre_fix_db_moves_seed_stamp_to_metadata_seeded_at(tmp_path):
    """Opening a pre-fix DB relabels bogus last_indexed_at stamps.

    Libraries with no indexed version were never indexed, so their stamp
    belongs in metadata_seeded_at; libraries that do have one keep theirs.
    """
    db_path = tmp_path / "docs.db"
    _make_pre_fix_db(db_path)

    db = DocsDB(db_path, embedding_dims=0)
    try:
        seeded = db._conn.execute(
            "SELECT last_indexed_at, metadata_seeded_at FROM libraries "
            "WHERE id = 'seeded'"
        ).fetchone()
        assert seeded["last_indexed_at"] is None
        assert seeded["metadata_seeded_at"] == 1000.0

        indexed = db._conn.execute(
            "SELECT last_indexed_at, metadata_seeded_at FROM libraries "
            "WHERE id = 'indexed'"
        ).fetchone()
        assert indexed["last_indexed_at"] == 2000.0
        assert indexed["metadata_seeded_at"] is None
    finally:
        db.close()


def test_upsert_library_does_not_stamp_last_indexed_at(tmp_path):
    """upsert_library writes metadata only; last_indexed_at stays untouched."""
    db = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    try:
        lib_id = db.upsert_library(name="react", tier=1)
        row = db.get_library("react")
        assert row["last_indexed_at"] is None

        # A second upsert (metadata refresh) must not resurrect the stamp.
        db.upsert_library(name="react", homepage="https://react.dev", tier=1)
        assert db.get_library("react")["last_indexed_at"] is None

        # mark_library_indexed remains the single writer of the column.
        db.mark_library_indexed(lib_id, total_versions=1)
        assert db.get_library("react")["last_indexed_at"] is not None
    finally:
        db.close()


def test_mark_metadata_seeded_records_seed_time(tmp_path):
    """mark_metadata_seeded stamps metadata_seeded_at without claiming index."""
    db = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    try:
        lib_id = db.upsert_library(name="react", tier=1)
        assert db.get_library("react")["metadata_seeded_at"] is None

        db.mark_metadata_seeded(lib_id)
        row = db.get_library("react")
        assert row["metadata_seeded_at"] is not None
        assert row["last_indexed_at"] is None
    finally:
        db.close()
