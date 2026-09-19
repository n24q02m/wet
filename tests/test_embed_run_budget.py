"""Residual N10 regression: the ingest embed budget must scale with batches.

``_background_index_and_search`` wraps the whole embed run in one
``asyncio.wait_for``. The 60s ceiling was sized for a local ONNX pass over the
whole chunk set; once the embed path goes remote (Cohere via the credential
vault), ``CloudEmbeddingBackend`` splits the same set into 96-text batches
drained 8 at a time, and a large library (1967 chunks -> 21 batches -> 3
waves) legitimately needs longer than any fixed 60s. The run was cancelled
mid-embed and every chunk was stamped keyword-only ("embedding batch timed
out after 60s").

These tests pin the wave-scaled budget (``_embed_run_timeout``) and prove the
end-to-end indexer stores vectors for a multi-wave embed that outlasts the
per-wave budget.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from wet_mcp import embedder, server
from wet_mcp.db import INDEX_STATE_DONE, DocsDB

DOCS_URL = "https://example.test/biglib"


def _chunks(n: int):
    return [
        {
            "url": f"{DOCS_URL}/page",
            "title": "T",
            "chunk_index": i,
            "content": f"chunk body number {i}",
            "heading_path": "T",
        }
        for i in range(n)
    ]


class TestEmbedRunTimeoutMath:
    def test_single_batch_gets_the_base_budget(self):
        assert server._embed_run_timeout(1) == server._EMBED_TIMEOUT
        assert (
            server._embed_run_timeout(embedder.CloudEmbeddingBackend.MAX_BATCH_SIZE)
            == server._EMBED_TIMEOUT
        )

    def test_1967_chunks_get_three_waves(self):
        # The live failure: 1967 chunks -> 21 batches of 96 -> 3 waves of 8.
        assert server._embed_run_timeout(1967) == 3 * server._EMBED_TIMEOUT

    def test_budget_tracks_backend_geometry(self):
        backend_cls = embedder.CloudEmbeddingBackend
        just_over_one_wave = backend_cls.MAX_BATCH_SIZE * backend_cls.CONCURRENCY + 1
        assert (
            server._embed_run_timeout(just_over_one_wave) == 2 * server._EMBED_TIMEOUT
        )

    def test_budget_is_capped_under_the_stale_running_marker(self):
        # _INDEX_RUNNING_STALE_AFTER (900s) reaps a RUNNING version whose
        # attempt started too long ago; the embed leg alone must never be
        # budgeted past the point where a live run could be reaped mid-embed.
        assert server._embed_run_timeout(10**6) < server._INDEX_RUNNING_STALE_AFTER


@pytest.fixture
def docs_db(tmp_path, monkeypatch):
    """A real DocsDB with the vector table enabled, wired as the store."""
    db = DocsDB(tmp_path / "docs.db", embedding_dims=4)
    monkeypatch.setattr(server, "_docs_db", db)
    yield db
    db.close()


@pytest.fixture
def no_searxng(monkeypatch):
    """Keep the indexer's SearXNG fallback leg off the network."""
    monkeypatch.setattr(
        server,
        "ensure_searxng",
        AsyncMock(side_effect=RuntimeError("searxng disabled in tests")),
    )


async def test_multiwave_embed_stores_vectors_instead_of_degrading(
    docs_db, no_searxng, monkeypatch
):
    """A large library's embed run must complete, not die at one-wave budget.

    Stub remote backend: every provider call sleeps 0.3s. With 2400 chunks
    (25 batches of 96) the semaphore drains them in 4 staggered rounds, so
    the run cannot finish in under 1.2s -- a fixed one-wave budget of 1.0s
    always cancels it (the N10 symptom: chunks stored WITHOUT vectors), while
    the wave-scaled budget (4 x 1.0s) always finishes it.
    """
    lib_id = docs_db.upsert_library(name="biglib", docs_url=DOCS_URL)
    ver_id = docs_db.upsert_version(library_id=lib_id, version="latest")

    monkeypatch.setattr(
        server,
        "_fetch_and_chunk_docs",
        AsyncMock(return_value=(_chunks(2400), 50)),
    )

    batch_sizes: list[int] = []

    class _SlowRemoteBackend(embedder.CloudEmbeddingBackend):
        """Real batch splitting + semaphore, stubbed slow provider calls."""

        def __init__(self):
            super().__init__("cohere/embed-english-v3.0")

        async def _call_provider(self, texts, dimensions=None):
            batch_sizes.append(len(texts))
            await asyncio.sleep(0.3)
            return [[0.5, 0.5, 0.5, 0.5] for _ in texts]

    monkeypatch.setattr(
        embedder,
        "resolve_embed_backend_for_request",
        lambda: _SlowRemoteBackend(),
    )
    # Shrink the per-wave budget so the whole scenario runs in ~2s; the
    # scaling relationship under test is unaffected.
    monkeypatch.setattr(server, "_EMBED_TIMEOUT", 1.0)

    await server._background_index_and_search(
        library="biglib",
        lib_key="biglib",
        language=None,
        docs_url=DOCS_URL,
        repo_url="",
        query="how to install",
        version=None,
        lib_id=lib_id,
        ver_id=ver_id,
    )

    # The stub ran once per provider batch, each within the batch limit.
    assert batch_sizes and max(batch_sizes) <= 96
    assert sum(batch_sizes) == 2400

    # The degrade would stamp DONE with a keyword-only note; a real vector
    # index lands DONE with no note.
    state = docs_db.get_index_state(ver_id)
    assert state["state"] == INDEX_STATE_DONE
    assert not state["error"]

    if not docs_db._vec_enabled:
        pytest.skip(
            "sqlite-vec did not load here, so doc_chunks_vec was never "
            "created; the embeddings-not-None contract is still asserted "
            "via the index state above"
        )
    vec_rows = docs_db._conn.execute("SELECT COUNT(*) FROM doc_chunks_vec").fetchone()[
        0
    ]
    assert vec_rows == 2400
