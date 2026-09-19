"""Regressions for failures that used to be swallowed in server.py / db.py.

Every test here pins an *observable* signal: either a WARNING/ERROR log record
carrying enough context to trace the fault, or an exception that reaches the
caller. On the pre-fix code each of these paths produced a success-shaped
result with the cause hidden behind ``logger.debug`` or a bare ``pass`` -- the
same shape that let ``refresh-tier1`` report success for eleven weeks over an
empty docs database.

Asserting "the function did not raise" is deliberately NOT what these tests do;
that is the property that hid the bug.
"""

import contextlib
import json
import sqlite3
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from loguru import logger

from wet_mcp import server
from wet_mcp.db import DocsDB
from wet_mcp.server import search

if TYPE_CHECKING:
    from loguru import Record

_LEVELS = {
    "TRACE": 5,
    "DEBUG": 10,
    "INFO": 20,
    "SUCCESS": 25,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


@contextlib.contextmanager
def captured_logs(level: str = "DEBUG"):
    """Collect loguru records emitted inside the block.

    ``logger.add`` is additive, so the module-level stderr sink configured by
    ``wet_mcp.server`` keeps working and no global logger state is mutated.
    """
    records: list[Record] = []
    sink_id = logger.add(lambda message: records.append(message.record), level=level)
    try:
        yield records
    finally:
        logger.remove(sink_id)


def at_least(records: list["Record"], level: str) -> list["Record"]:
    """Records logged at ``level`` or above."""
    floor = _LEVELS[level]
    return [r for r in records if r["level"].no >= floor]


def messages(records: list["Record"], level: str) -> list[str]:
    return [r["message"] for r in at_least(records, level)]


@pytest.fixture(autouse=True)
def _single_user_stdio_context():
    """Keep this module off the real embedder and on the stdio credential path.

    Three order-dependent hazards, all observed under ``pytest-randomly``:

    * ``_background_index_and_search`` resolves the embedding backend lazily,
      so an unmocked run downloads and loads a local ONNX model -- that turns a
      failing assertion into a 30s timeout that kills the run. Tests that need
      a backend patch the same target inside their own ``with`` block, which
      takes precedence.
    * ``credential_state._current_sub`` is a ContextVar that some tests set and
      never clear, and pytest-asyncio copies the ambient context into the test
      task. A leaked ``sub`` sends ``_require_credentials`` down the HTTP
      multi-user branch, so the ``search`` tool returns an awaiting_setup
      payload and never reaches the post-processing under test.
    * conftest's ``_disable_uvx_tool_venv_detection`` neutralises
      ``is_uvx_tool_venv`` only on whatever object is registered as
      ``sys.modules["wet_mcp.server"]``. ``test_serverinfo_version.py`` pops
      that key and re-imports, so from then on the module object bound at the
      top of this file is a *different* object, and conftest patches the other
      one. Measured under a random seed: ``{'uvx': True, 'same_module':
      False}``; reproduced deterministically with
      ``pytest tests/test_serverinfo_version.py tests/test_silent_failure_surfacing.py -p no:randomly``.
      The detector genuinely returns True here -- it keys off a missing
      ``pip``, which this uv-managed venv has none of -- so the unpatched copy
      makes ``search`` bail out at the SearXNG gate and return the
      blocked-error string before any post-processing runs. Pin the name on
      the object these tests actually call into.
    """
    from wet_mcp.credential_state import set_current_sub

    set_current_sub(None)
    previous_db = server._docs_db
    with (
        patch("wet_mcp.embedder.resolve_embed_backend_for_request", return_value=None),
        patch.object(server, "is_uvx_tool_venv", lambda: False),
    ):
        yield
    server._docs_db = previous_db


def _diag() -> dict:
    """Ambient state that decides whether the search tool even runs its body."""
    import sys

    from wet_mcp.credential_state import get_current_sub, get_state

    return {
        "uvx": server.is_uvx_tool_venv(),
        "same_module": server is sys.modules.get("wet_mcp.server"),
        "sub": get_current_sub(),
        "cred_state": get_state(),
    }


# ---------------------------------------------------------------------------
# server.py -- reranking and search post-processing
# ---------------------------------------------------------------------------


async def test_rerank_failure_is_reported_at_warning():
    """A broken reranker degrades every search; debug level hid that."""
    reranker = MagicMock()
    reranker.rerank.side_effect = RuntimeError("rerank endpoint returned 502")
    results = [{"content": f"chunk {i}"} for i in range(5)]

    with (
        patch(
            "wet_mcp.reranker.resolve_rerank_backend_for_request",
            return_value=reranker,
        ),
        captured_logs() as records,
    ):
        out = await server._rerank_results("how to mount a volume", results, top_n=2)

    assert out == results[:2]
    warned = messages(records, "WARNING")
    assert any(
        "Reranking failed" in m and "how to mount a volume" in m for m in warned
    ), warned


async def test_search_rerank_step_failure_is_reported_at_warning():
    """The search action's rerank block swallowed its own bugs at debug."""
    backend_results = json.dumps(
        {
            "results": [
                {"url": "https://a.example", "title": "A", "snippet": "S"},
            ],
            "total": 1,
            "query": "test",
        }
    )

    chain = AsyncMock(return_value=backend_results)
    with (
        patch(
            "wet_mcp.sources.search_backends.chain_backend_names",
            return_value=[],
        ),
        patch("wet_mcp.sources.search_backends.run_search_chain", new=chain),
        patch.object(
            server,
            "_rerank_results",
            new_callable=AsyncMock,
            side_effect=RuntimeError("rerank blew up"),
        ),
        patch.object(server, "_web_cache", None),
        captured_logs() as records,
    ):
        out = await search(action="search", query="pinned query", max_results=3)

    warned = messages(records, "WARNING")
    assert any(
        "Search reranking step failed" in m and "pinned query" in m for m in warned
    ), (warned, chain.await_count, _diag(), out)


async def test_search_enrichment_failure_is_reported_at_warning():
    """enrich=True is an explicit opt-in; dropping it must not be silent."""
    backend_results = json.dumps(
        {
            "results": [
                {"url": "https://a.example", "title": "A", "snippet": "S"},
            ],
            "total": 1,
            "query": "test",
        }
    )

    chain = AsyncMock(return_value=backend_results)
    with (
        patch(
            "wet_mcp.sources.search_backends.chain_backend_names",
            return_value=[],
        ),
        patch("wet_mcp.sources.search_backends.run_search_chain", new=chain),
        patch.object(
            server,
            "_rerank_results",
            new_callable=AsyncMock,
            side_effect=lambda q, r, top_n: r,
        ),
        patch(
            "wet_mcp.sources.search_strategies.enrich_snippets",
            new_callable=AsyncMock,
            side_effect=RuntimeError("enrichment fetch failed"),
        ),
        patch.object(server, "_web_cache", None),
        captured_logs() as records,
    ):
        out = await search(
            action="search", query="enrich me", max_results=3, enrich=True
        )

    warned = messages(records, "WARNING")
    assert any("Snippet enrichment" in m and "enrich me" in m for m in warned), (
        warned,
        chain.await_count,
        _diag(),
        out,
    )


async def test_search_citation_standardization_failure_is_reported_at_warning():
    """Citation standardization is our own pure-python step -- a failure is a bug."""
    backend_results = json.dumps(
        {
            "results": [
                {"url": "https://a.example", "title": "A", "snippet": "S"},
            ],
            "total": 1,
            "query": "test",
        }
    )

    chain = AsyncMock(return_value=backend_results)
    with (
        patch(
            "wet_mcp.sources.search_backends.chain_backend_names",
            return_value=[],
        ),
        patch("wet_mcp.sources.search_backends.run_search_chain", new=chain),
        patch.object(
            server,
            "_rerank_results",
            new_callable=AsyncMock,
            side_effect=lambda q, r, top_n: r,
        ),
        patch(
            "wet_mcp.sources._search_polish.standardize_results",
            side_effect=RuntimeError("bad citation shape"),
        ),
        patch.object(server, "_web_cache", None),
        captured_logs() as records,
    ):
        out = await search(action="search", query="cite me", max_results=3)

    warned = messages(records, "WARNING")
    assert any(
        "Citation standardization failed" in m and "cite me" in m for m in warned
    ), (warned, chain.await_count, _diag(), out)


# ---------------------------------------------------------------------------
# server.py -- background docs indexing
# ---------------------------------------------------------------------------


def _chunk(i: int) -> dict:
    return {
        "url": "http://docs",
        "title": "Guide",
        "content": f"chunk {i}",
        "heading_path": "Guide",
        "chunk_index": i,
    }


async def test_background_index_alternate_source_failure_is_reported():
    """Alternate docs URLs failed inside gather() with no record at all."""
    searx_payload = json.dumps({"results": [{"url": "https://alt.example/docs"}]})

    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"),
        patch.object(
            server,
            "_fetch_and_chunk_docs",
            new_callable=AsyncMock,
            side_effect=[([], 0), RuntimeError("alt source 403")],
        ),
        patch.object(
            server,
            "_run_configured_search",
            new_callable=AsyncMock,
            return_value=searx_payload,
        ),
        captured_logs() as records,
    ):
        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://docs",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )

    warned = messages(records, "WARNING")
    assert any(
        "Alternate docs source failed" in m
        and "testlib" in m
        and "https://alt.example/docs" in m
        for m in warned
    ), warned


async def test_background_index_configured_search_fallback_failure_is_reported():
    """The last-resort configured search fallback reports its own failure."""
    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"),
        patch.object(
            server,
            "_fetch_and_chunk_docs",
            new_callable=AsyncMock,
            return_value=([], 0),
        ),
        patch.object(
            server,
            "_run_configured_search",
            new_callable=AsyncMock,
            side_effect=RuntimeError("configured search is down"),
        ),
        captured_logs() as records,
    ):
        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language="python",
            docs_url="http://docs",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )

    warned = messages(records, "WARNING")
    assert any(
        "Configured search docs fallback failed" in m
        and "testlib" in m
        and "testlib python documentation" in m
        for m in warned
    ), warned


async def test_background_index_embedding_timeout_is_reported():
    """Chunks stored with embeddings=None still get stamped 'indexed'."""
    docs_db = MagicMock()
    chunks = [_chunk(i) for i in range(3)]
    previous_db = server._docs_db
    server._docs_db = docs_db
    try:
        with (
            patch(
                "wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"
            ),
            patch.object(
                server,
                "_fetch_and_chunk_docs",
                new_callable=AsyncMock,
                return_value=(chunks, 5),
            ),
            patch(
                "wet_mcp.embedder.resolve_embed_backend_for_request",
                return_value=MagicMock(),
            ),
            patch.object(
                server,
                "_embed_batch",
                new_callable=AsyncMock,
                side_effect=TimeoutError,
            ),
            captured_logs() as records,
        ):
            await server._background_index_and_search(
                library="testlib",
                lib_key="testlib",
                language=None,
                docs_url="http://docs",
                repo_url="",
                query="test",
                version=None,
                lib_id="1",
                ver_id="1",
            )
    finally:
        server._docs_db = previous_db

    # The degrade itself is intended -- the chunks are still stored.
    assert docs_db.add_chunks.call_args.kwargs["embeddings"] is None
    docs_db.mark_version_indexed.assert_called_once()

    errored = messages(records, "ERROR")
    assert any(
        "Embedding run timed out" in m and "testlib" in m and "3 chunks" in m
        for m in errored
    ), errored


async def test_background_index_crash_keeps_the_traceback():
    """`{e}` alone on a KeyError prints one word; the task result is discarded."""
    docs_db = MagicMock()
    docs_db.add_chunks.side_effect = KeyError("content")
    chunks = [_chunk(0)]
    previous_db = server._docs_db
    server._docs_db = docs_db
    try:
        with (
            patch(
                "wet_mcp.sources.docs._normalize_docs_url",
                return_value="http://docs.example/guide",
            ),
            patch.object(
                server,
                "_fetch_and_chunk_docs",
                new_callable=AsyncMock,
                return_value=(chunks, 5),
            ),
            patch(
                "wet_mcp.embedder.resolve_embed_backend_for_request",
                return_value=None,
            ),
            captured_logs() as records,
        ):
            await server._background_index_and_search(
                library="testlib",
                lib_key="testlib",
                language=None,
                docs_url="http://docs.example/guide",
                repo_url="",
                query="test",
                version=None,
                lib_id="1",
                ver_id="1",
            )
    finally:
        server._docs_db = previous_db

    crashes = [
        r
        for r in at_least(records, "ERROR")
        if "Background indexing failed for 'testlib'" in r["message"]
    ]
    assert crashes, messages(records, "ERROR")
    message = crashes[0]["message"]
    assert "http://docs.example/guide" in message
    assert "KeyError" in message
    # The traceback is the part that makes a bare KeyError readable, and it
    # must not carry loguru's `diagnose` variable dump.
    assert "Traceback (most recent call last)" in message
    assert "_background_index_and_search" in message


async def test_discover_docs_url_non_json_configured_search_is_reported():
    """A configured search failure string is logged, not mistaken for no result."""
    with (
        patch(
            "wet_mcp.sources.docs.discover_library",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch.object(
            server,
            "_run_configured_search",
            new_callable=AsyncMock,
            return_value="Error: configured search unreachable",
        ),
        captured_logs() as records,
    ):
        docs_url, _repo, _registry, _desc = await server._discover_docs_url(
            "ghostlib", None
        )

    assert docs_url == ""
    warned = messages(records, "WARNING")
    assert any(
        "Configured search discovery fallback" in m
        and "ghostlib" in m
        and "configured search unreachable" in m
        for m in warned
    ), warned


async def test_immediate_fallback_search_failure_is_reported():
    """An empty temporary_results read as "the web had nothing"."""
    with (
        patch.object(
            server,
            "_run_configured_search",
            new_callable=AsyncMock,
            side_effect=RuntimeError("configured search is down"),
        ),
        captured_logs() as records,
    ):
        data = await server._do_immediate_fallback_search(
            docs_url="https://docs.example/guide",
            library="testlib",
            language=None,
            query="how to install",
            limit=5,
        )

    assert data == {"results": []}
    warned = messages(records, "WARNING")
    assert any(
        "Immediate fallback search failed" in m
        and "testlib" in m
        and "how to install" in m
        for m in warned
    ), warned


# ---------------------------------------------------------------------------
# db.py
# ---------------------------------------------------------------------------


def test_sqlite_vec_unavailable_is_reported_at_warning(tmp_path):
    """Dropping to FTS-only kills semantic search for the whole process."""
    db_path = tmp_path / "novec.db"
    with (
        patch("sqlite_vec.load", side_effect=RuntimeError("no vec0 in this build")),
        captured_logs() as records,
    ):
        db = DocsDB(db_path, embedding_dims=4)
    try:
        assert db._vec_enabled is False
        warned = messages(records, "WARNING")
        assert any("sqlite-vec unavailable" in m and "novec.db" in m for m in warned), (
            warned
        )
    finally:
        db.close()


def test_embedding_serialization_failure_names_the_chunk(tmp_path):
    """A per-chunk skip is fine; an unattributed per-chunk skip is not."""
    db = DocsDB(tmp_path / "ser.db", embedding_dims=2)
    if not db._vec_enabled:
        db.close()
        pytest.skip(
            "sqlite-vec did not load here (macOS CI runs a python whose "
            "sqlite3 has no enable_load_extension), so doc_chunks_vec was "
            "never created. This test needs the surviving vector to land, and "
            "forcing _vec_enabled on without the table is a state the server "
            "cannot reach."
        )
    try:
        lib_id = db.upsert_library(name="serlib")
        ver_id = db.upsert_version(lib_id)
        embeddings = cast(Any, [[1.0, 2.0], "not-an-embedding"])

        with captured_logs() as records:
            db.add_chunks(
                ver_id,
                lib_id,
                [{"content": "good"}, {"content": "bad"}],
                embeddings=embeddings,
            )

        warned = messages(records, "WARNING")
        assert any(
            "Dropping the embedding for chunk" in m and "str" in m for m in warned
        ), warned
    finally:
        db.close()


def test_vector_batch_insert_failure_reaches_the_caller(tmp_path):
    """add_chunks used to report the full chunk count over a vector-less batch."""
    # embedding_dims=0 leaves doc_chunks_vec uncreated; forcing _vec_enabled
    # reproduces a live database whose vector table is missing or unwritable.
    db = DocsDB(tmp_path / "batch.db", embedding_dims=0)
    db._vec_enabled = True
    try:
        lib_id = db.upsert_library(name="batchlib")
        ver_id = db.upsert_version(lib_id)

        raised: Exception | None = None
        with captured_logs() as records:
            try:
                db.add_chunks(
                    ver_id,
                    lib_id,
                    [{"content": "c1"}, {"content": "c2"}],
                    embeddings=[[1.0, 2.0], [3.0, 4.0]],
                )
            except sqlite3.Error as exc:
                raised = exc

        assert raised is not None, "vector insert failure never reached the caller"

        errored = messages(records, "ERROR")
        assert any("Vector insert failed" in m and "batch.db" in m for m in errored), (
            errored
        )

        # The doc_chunks rows share the failed transaction and must not survive
        # as a half-written "indexed" batch.
        remaining = db._conn.execute("SELECT COUNT(*) FROM doc_chunks").fetchone()[0]
        assert remaining == 0
    finally:
        db.close()


def test_fts_search_failure_is_reported_at_warning(tmp_path):
    """A broken FTS tier returns the same empty dict as "nothing matched"."""

    class _FtsFailingConn:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if "doc_chunks_fts" in sql:
                raise sqlite3.OperationalError("fts5: syntax error near AND")
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    db = DocsDB(tmp_path / "fts.db", embedding_dims=0)
    try:
        lib_id = db.upsert_library(name="ftslib")
        ver_id = db.upsert_version(lib_id)
        db.add_chunks(ver_id, lib_id, [{"content": "installing the thing"}])
        db.mark_version_indexed(ver_id, 1, 1)

        real_conn = db._conn
        db._conn = cast(Any, _FtsFailingConn(real_conn))
        try:
            with captured_logs() as records:
                results = db.search(query="installing", library_name="ftslib")
        finally:
            db._conn = real_conn

        assert results == []
        warned = messages(records, "WARNING")
        assert any("FTS search failed" in m and "installing" in m for m in warned), (
            warned
        )
    finally:
        db.close()


def test_vector_search_failure_is_reported_at_warning(tmp_path):
    """An empty vec_scores read as "nothing was semantically close"."""
    db = DocsDB(tmp_path / "vecsearch.db", embedding_dims=0)
    db._vec_enabled = True  # no doc_chunks_vec table exists at dims=0
    try:
        lib_id = db.upsert_library(name="veclib")
        ver_id = db.upsert_version(lib_id)
        db.add_chunks(ver_id, lib_id, [{"content": "installing the thing"}])
        db.mark_version_indexed(ver_id, 1, 1)

        with captured_logs() as records:
            db.search(
                query="installing",
                library_name="veclib",
                query_embedding=[1.0, 2.0],
            )

        warned = messages(records, "WARNING")
        assert any("Vector search failed" in m for m in warned), warned
    finally:
        db.close()


def test_unreadable_project_lock_is_reported_at_warning(tmp_path):
    """An unreadable lock silently becomes "this project was never locked"."""
    db = DocsDB(tmp_path / "lock.db", embedding_dims=0)
    try:
        db._conn.execute(
            "INSERT INTO project_context "
            "(project_path, locked_libraries, created_at, last_used_at) "
            "VALUES (?, ?, ?, ?)",
            ("/repo/my-app", "{truncated json", 0.0, 0.0),
        )
        db._conn.commit()

        with captured_logs() as records:
            ctx = db.get_project_context("/repo/my-app")

        assert ctx is not None
        assert ctx["locked_libraries"] == []
        warned = messages(records, "WARNING")
        assert any("locked_libraries" in m and "/repo/my-app" in m for m in warned), (
            warned
        )
    finally:
        db.close()
