"""A background indexing attempt must leave a durable, readable record.

Reproduced on a deployed Cloudflare container: ``config(action="status")``
reported ``docs_indexed: {libraries: 8, chunks: 0}`` while the container was
demonstrably awake, egress worked, and the background indexer issued zero
writes to D1. The task produced no effect and no trace outside the container,
because its only failure report was a ``logger.error`` on a stderr nothing
collects -- so ``chunks: 0`` covered four different states at once: never
attempted, running now, failed permanently, and succeeded with no content.

Three defects are pinned here:

1. the launch sites discarded the ``asyncio.Task``, so an exception surfaced
   only as a GC-time "Task exception was never retrieved" and the task itself
   could be collected mid-flight (asyncio holds only a weak reference);
2. the failure path wrote nothing durable;
3. every poll cleared the version's chunks BEFORE the replacement existed and
   relaunched work that was already running, so one failed re-index destroyed
   the library's only good copy.

The happy path is covered too, but only as a control: it is the failure paths
below that this module exists for.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from loguru import logger

from wet_mcp import server
from wet_mcp.db import (
    INDEX_STATE_DONE,
    INDEX_STATE_FAILED,
    INDEX_STATE_RUNNING,
    DocsDB,
)

DOCS_URL = "https://example.test/alpha"


@pytest.fixture
def docs_db(tmp_path, monkeypatch):
    """A real DocsDB wired in as the server's store.

    Deliberately not a MagicMock: the thing under test is whether the outcome
    survives in the database and can be read back through the normal query
    path, which a mock would assert away.
    """
    db = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    monkeypatch.setattr(server, "_docs_db", db)
    yield db
    db.close()


def _chunks(n: int, prefix: str = "old"):
    return [
        {
            "url": f"{DOCS_URL}/page",
            "title": "T",
            "chunk_index": i,
            "content": f"{prefix} chunk body number {i}",
            "heading_path": "T",
        }
        for i in range(n)
    ]


def _seed_indexed_library(db: DocsDB, chunk_count: int = 3):
    """A library that already holds usable chunks, as production would."""
    lib_id = db.upsert_library(name="alpha", docs_url=DOCS_URL)
    ver_id = db.upsert_version(library_id=lib_id, version="latest", docs_url=DOCS_URL)
    db.add_chunks(version_id=ver_id, library_id=lib_id, chunks=_chunks(chunk_count))
    db.mark_version_indexed(ver_id, page_count=2, chunk_count=chunk_count)
    db.set_index_state(ver_id, INDEX_STATE_DONE)
    return lib_id, ver_id


async def _run_indexer(lib_id: str, ver_id: str):
    return await server._background_index_and_search(
        library="alpha",
        lib_key="alpha",
        language=None,
        docs_url=DOCS_URL,
        repo_url="",
        query="how to install",
        version=None,
        lib_id=lib_id,
        ver_id=ver_id,
    )


@pytest.fixture
def no_searxng(monkeypatch):
    """Keep the indexer's SearXNG fallback leg off the network.

    ``_background_index_and_search`` reaches for an alternate docs source
    whenever the primary fetch came back thin, which is exactly the situation
    every failure test here sets up.
    """
    monkeypatch.setattr(
        server,
        "ensure_searxng",
        AsyncMock(side_effect=RuntimeError("searxng disabled in tests")),
    )


# ---------------------------------------------------------------------------
# Defect 2: a failed attempt must leave something readable behind
# ---------------------------------------------------------------------------


async def test_indexer_exception_leaves_a_readable_failed_record(
    docs_db, no_searxng, monkeypatch
):
    """An unexpected exception is recorded, not just logged into the void."""
    lib_id, ver_id = _seed_indexed_library(docs_db)
    docs_db.set_index_state(ver_id, INDEX_STATE_RUNNING)

    async def _explode(**_kwargs):
        raise RuntimeError("GitHub raw fetch exploded")

    monkeypatch.setattr(server, "_fetch_and_chunk_docs", _explode)

    await _run_indexer(lib_id, ver_id)

    state = docs_db.get_index_state(ver_id)
    assert state is not None, "the attempt left no record at all"
    assert state["state"] == INDEX_STATE_FAILED
    assert "RuntimeError" in state["error"]
    assert "GitHub raw fetch exploded" in state["error"]
    assert state["updated_at"] > 0


async def test_zero_chunks_records_the_reason_not_just_a_zero(
    docs_db, no_searxng, monkeypatch
):
    """Extracting nothing is a failure with a reason, not a silent return."""
    lib_id = docs_db.upsert_library(name="alpha", docs_url=DOCS_URL)
    ver_id = docs_db.upsert_version(library_id=lib_id, version="latest")
    docs_db.set_index_state(ver_id, INDEX_STATE_RUNNING)

    monkeypatch.setattr(
        server, "_fetch_and_chunk_docs", AsyncMock(return_value=([], 0))
    )

    await _run_indexer(lib_id, ver_id)

    state = docs_db.get_index_state(ver_id)
    assert state is not None
    assert state["state"] == INDEX_STATE_FAILED
    assert "Could not extract content" in state["error"]
    assert state["chunk_count"] == 0


async def test_recording_a_failure_never_masks_it(docs_db, no_searxng, monkeypatch):
    """A broken store must not turn "docs fetch failed" into "DB write failed".

    The recorder runs inside the ``except`` handler holding the real error, so
    an exception raised there would replace the diagnosis with a symptom.
    """
    lib_id, ver_id = _seed_indexed_library(docs_db)
    records: list[str] = []
    sink = logger.add(records.append, level="ERROR")

    async def _explode(**_kwargs):
        raise RuntimeError("GitHub raw fetch exploded")

    monkeypatch.setattr(server, "_fetch_and_chunk_docs", _explode)
    monkeypatch.setattr(
        docs_db,
        "set_index_state",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("D1 returned 500")),
    )

    try:
        await _run_indexer(lib_id, ver_id)
    finally:
        logger.remove(sink)

    joined = "".join(records)
    assert "GitHub raw fetch exploded" in joined, "the real failure was lost"
    assert "Could not record indexing state" in joined
    assert "D1 returned 500" in joined


async def test_recording_without_a_store_is_a_no_op():
    """No store means nothing was indexed and there is nowhere to record."""
    with patch.object(server, "_docs_db", None):
        server._record_index_state("ver-1", INDEX_STATE_FAILED, "boom")


async def test_never_attempted_is_distinguishable_from_failed(docs_db):
    """``None`` (never asked) must not read the same as a recorded failure."""
    lib_id = docs_db.upsert_library(name="alpha", docs_url=DOCS_URL)
    ver_id = docs_db.upsert_version(library_id=lib_id, version="latest")

    assert docs_db.get_index_state(ver_id) is None

    docs_db.set_index_state(ver_id, INDEX_STATE_FAILED, "boom")
    assert docs_db.get_index_state(ver_id)["state"] == INDEX_STATE_FAILED


async def test_config_status_reports_why_there_are_no_chunks(docs_db):
    """The status payload carries the outcome next to the raw counts."""
    lib_id = docs_db.upsert_library(name="alpha", docs_url=DOCS_URL)
    ver_id = docs_db.upsert_version(library_id=lib_id, version="latest")
    docs_db.set_index_state(ver_id, INDEX_STATE_FAILED, "Could not extract content")

    with (
        patch("wet_mcp.embedder.get_backend", return_value=None),
        patch("wet_mcp.reranker.get_reranker", return_value=None),
    ):
        status = await server._handle_config_status()

    indexing = status["database"]["indexing"]
    assert status["database"]["docs_indexed"]["chunks"] == 0
    assert indexing["counts"] == {INDEX_STATE_FAILED: 1}
    assert indexing["recent"][0]["library"] == "alpha"
    assert indexing["recent"][0]["error"] == "Could not extract content"


# ---------------------------------------------------------------------------
# Defect 3: good data must survive, and running work must not be relaunched
# ---------------------------------------------------------------------------


async def test_existing_chunks_survive_a_failed_reindex(
    docs_db, no_searxng, monkeypatch
):
    """A failed re-index must not leave the library emptier than it found it."""
    lib_id, ver_id = _seed_indexed_library(docs_db, chunk_count=3)

    async def _explode(**_kwargs):
        raise RuntimeError("docs host returned 503")

    monkeypatch.setattr(server, "_fetch_and_chunk_docs", _explode)

    await _run_indexer(lib_id, ver_id)

    assert docs_db.stats()["chunks"] == 3, "a failed re-index destroyed good data"
    assert docs_db.get_index_state(ver_id)["state"] == INDEX_STATE_FAILED
    # The version keeps serving what it already had.
    assert docs_db.get_best_version(lib_id)["chunk_count"] == 3
    assert docs_db.search("chunk body", library_name="alpha")


async def test_successful_reindex_still_replaces_the_old_chunks(
    docs_db, no_searxng, monkeypatch
):
    """Moving the clear must not turn a replace into an append."""
    lib_id, ver_id = _seed_indexed_library(docs_db, chunk_count=3)

    monkeypatch.setattr(
        server,
        "_fetch_and_chunk_docs",
        AsyncMock(return_value=(_chunks(2, prefix="fresh"), 2)),
    )
    monkeypatch.setattr(
        "wet_mcp.embedder.resolve_embed_backend_for_request", lambda: None
    )

    await _run_indexer(lib_id, ver_id)

    assert docs_db.stats()["chunks"] == 2
    assert docs_db.get_index_state(ver_id)["state"] == INDEX_STATE_DONE
    contents = [r["content"] for r in docs_db.search("chunk", library_name="alpha")]
    assert contents and all(c.startswith("fresh") for c in contents)


@pytest.fixture
def launch_recorder(monkeypatch):
    """Capture background launches without scheduling an orphan Task."""
    launched: list[str] = []

    def _record(coro, label):
        coro.close()
        launched.append(label)
        return None

    monkeypatch.setattr(server, "_launch_background_task", _record)
    return launched


@pytest.fixture
def offline_docs_search(monkeypatch):
    """Pin the network-touching legs of ``_do_docs_search``."""
    monkeypatch.setattr(
        server,
        "_discover_docs_url",
        AsyncMock(return_value=(DOCS_URL, "", "registry", "desc")),
    )
    monkeypatch.setattr(
        server, "_do_immediate_fallback_search", AsyncMock(return_value={"results": []})
    )
    monkeypatch.setattr(server, "_embed", AsyncMock(return_value=None))


async def test_second_search_while_running_neither_relaunches_nor_clears(
    docs_db, launch_recorder, offline_docs_search
):
    """The poll that used to wipe the index now reports on it instead."""
    _lib_id, ver_id = _seed_indexed_library(docs_db, chunk_count=3)
    docs_db.set_index_state(ver_id, INDEX_STATE_RUNNING)

    # A query no stored chunk matches is what drops the cached-index path and
    # sends production into the re-index branch.
    result = await server._do_docs_search(library="alpha", query="zzzznomatch")

    assert launch_recorder == [], "relaunched an index that was already running"
    assert docs_db.stats()["chunks"] == 3, "cleared chunks a live indexer was using"
    assert result["status"] == "indexing_in_progress"
    assert result["last_index_attempt"]["state"] == INDEX_STATE_RUNNING
    assert "has been indexing since" in result["message"]


async def test_a_stale_running_record_does_not_lock_the_library_out(
    docs_db, launch_recorder, offline_docs_search
):
    """A process that died mid-index must not block the version forever."""
    _lib_id, ver_id = _seed_indexed_library(docs_db, chunk_count=3)
    docs_db.set_index_state(ver_id, INDEX_STATE_RUNNING)
    docs_db._conn.execute(
        "UPDATE versions SET index_state_at = ? WHERE id = ?",
        (docs_db.get_index_state(ver_id)["updated_at"] - 10_000, ver_id),
    )
    docs_db._conn.commit()

    await server._do_docs_search(library="alpha", query="zzzznomatch")

    assert launch_recorder == ["docs-index:alpha"]


async def test_a_previous_failure_is_named_in_the_reply(
    docs_db, launch_recorder, offline_docs_search
):
    """ "Indexing in progress (3-5 minutes)" must not stand in for "it failed"."""
    _lib_id, ver_id = _seed_indexed_library(docs_db, chunk_count=3)
    docs_db.set_index_state(ver_id, INDEX_STATE_FAILED, "docs host returned 503")

    result = await server._do_docs_search(library="alpha", query="zzzznomatch")

    assert launch_recorder == ["docs-index:alpha"], "a failed version was never retried"
    assert "previous indexing attempt" in result["message"]
    assert "docs host returned 503" in result["message"]
    assert result["last_index_attempt"]["state"] == INDEX_STATE_FAILED


async def test_launching_marks_the_version_running_before_it_starts(
    docs_db, launch_recorder, offline_docs_search
):
    """Without this write, a concurrent poll sees "never attempted" and races."""
    await server._do_docs_search(library="alpha", query="anything")

    assert launch_recorder == ["docs-index:alpha"]
    lib = docs_db.get_library("alpha")
    ver_id = docs_db._conn.execute(
        "SELECT id FROM versions WHERE library_id = ?", (lib["id"],)
    ).fetchone()["id"]
    assert docs_db.get_index_state(ver_id)["state"] == INDEX_STATE_RUNNING


# ---------------------------------------------------------------------------
# Defect 1: a fire-and-forget task must be referenced and its failure reported
# ---------------------------------------------------------------------------


async def test_launcher_keeps_a_strong_reference_until_the_task_finishes():
    """asyncio holds only a weak reference; a discarded task can just vanish."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def _work():
        started.set()
        await release.wait()

    task = server._launch_background_task(_work(), "unit-test")
    await started.wait()
    assert task in server._background_tasks

    release.set()
    await task
    await asyncio.sleep(0)
    assert task not in server._background_tasks, "finished task was never released"


async def test_a_raising_background_task_is_reported_with_its_traceback():
    """The exception must be retrieved and logged, not left for the GC."""
    records: list[str] = []
    sink = logger.add(records.append, level="ERROR")

    async def _work():
        raise ValueError("background work blew up")

    try:
        task = server._launch_background_task(_work(), "unit-test-failing")
        with pytest.raises(ValueError):
            await task
        await asyncio.sleep(0)
    finally:
        logger.remove(sink)

    assert records, "the task's exception was never reported"
    joined = "".join(records)
    assert "unit-test-failing" in joined
    assert "ValueError" in joined
    assert "background work blew up" in joined
    assert "Traceback" in joined, "the traceback is what makes the log actionable"


async def test_a_cancelled_background_task_is_not_reported_as_a_failure():
    """Shutdown cancels tasks on purpose; that is not an error to shout about."""
    records: list[str] = []
    sink = logger.add(records.append, level="ERROR")

    async def _work():
        await asyncio.Event().wait()

    try:
        task = server._launch_background_task(_work(), "unit-test-cancelled")
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)
    finally:
        logger.remove(sink)

    assert records == []
    assert task not in server._background_tasks
