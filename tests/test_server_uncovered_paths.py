"""server.py paths the rest of the suite never reached.

Most server tests stand a ``MagicMock`` in for the web cache, so the real
per-namespace cache router and the search tool's cache-replay branches only
ran in production. These tests drive them with a real ``WebCache`` on the
isolated ``HOME`` from conftest. Mocks sit at the external boundary only: the
search-backend chain (``_run_configured_search``), the reranker model, the
``jev_score`` chat cell and the LLM query rewriter.
"""

from __future__ import annotations

import json
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from structured import payload

import wet.cache as cache_module
from wet import server
from wet.runtime import sub_root


@pytest.fixture(autouse=True)
def _no_real_searxng_spawn():
    """Same guard as test_server.py: the search chain must never spawn SearXNG."""
    with patch(
        "wet.sources.searxng._ensure_searxng_healthy",
        new_callable=AsyncMock,
        side_effect=lambda url: url,
    ):
        yield


@pytest.fixture
def per_sub_cache():
    """A real namespace-routing cache living under the isolated HOME."""
    cache = server._PerSubCache()
    yield cache
    cache.close()


@pytest.fixture
def live_cache(monkeypatch, per_sub_cache):
    """Install the real cache as the server's web cache for one test."""
    monkeypatch.setattr(server, "_web_cache", per_sub_cache)
    monkeypatch.setattr(server.settings, "tool_timeout", 0)
    return per_sub_cache


@pytest.fixture
def no_reranker():
    """Keep the search path off the local ONNX reranker (model download)."""
    with patch("wet.reranker.resolve_rerank_backend_for_request", return_value=None):
        yield


def _set_in_past(cache, seconds_ago: float, *args, **kwargs) -> None:
    """Write a cache row as if it had been stored ``seconds_ago`` seconds back.

    ``WebCache`` stamps rows with ``time.time()``; swapping the module's clock
    for the one call is the only way to age a row without sleeping.
    """
    import time as real_time

    frozen = real_time.time() - seconds_ago
    with patch.object(cache_module, "time", types.SimpleNamespace(time=lambda: frozen)):
        cache.set(*args, **kwargs)


def _search_params(query: str, **overrides) -> dict:
    """The cache key payload the search action builds for its defaults."""
    params = {
        "query": query,
        "categories": "general",
        "max_results": 10,
        "time_range": None,
        "language": None,
        "region": None,
        "include_domains": None,
        "exclude_domains": None,
        "parallel": False,
    }
    params.update(overrides)
    return params


def _jev_cell(monkeypatch, answer: str) -> None:
    """Configure only the ``jev_score`` chat cell, answering ``answer``."""
    from wet import runtime

    class _Cell:
        async def chat(self, messages, **kwargs):
            return answer

    real_configured = runtime.cell_configured
    monkeypatch.setattr(
        runtime,
        "cell_configured",
        lambda task, settings=None: (
            True if task == "jev_score" else real_configured(task, settings)
        ),
    )
    monkeypatch.setattr(
        runtime, "provider_client", lambda task, settings=None, **kw: _Cell()
    )


# ---------------------------------------------------------------------------
# _PerSubCache: one SQLite file per caller namespace
# ---------------------------------------------------------------------------


def test_per_sub_cache_keeps_each_namespace_in_its_own_file(per_sub_cache):
    """Pins the de-host layout: a write for one namespace lands in that
    namespace's ``cache.db`` and is invisible to every other namespace."""
    per_sub_cache.set("search", {"q": "a"}, '{"results": [1]}', None, "alice")

    assert per_sub_cache.get("search", {"q": "a"}, "alice") == '{"results": [1]}'
    assert per_sub_cache.get("search", {"q": "a"}, "bob") is None
    assert (sub_root("alice") / "cache.db").is_file()
    assert (sub_root("bob") / "cache.db").is_file()
    # The same namespace reuses the already-open file.
    assert per_sub_cache._for("alice") is per_sub_cache._for("alice")


def test_per_sub_cache_set_with_empty_sub_uses_default_namespace(per_sub_cache):
    """Pins the ``sub or "default"`` fallback: an empty namespace from a
    request with no identity is stored where a default read finds it."""
    per_sub_cache.set("extract", {"u": 1}, "body", None, "")

    assert per_sub_cache.get("extract", {"u": 1}) == "body"
    assert Path(sub_root("default") / "cache.db").is_file()


def test_per_sub_cache_age_reads_and_stale_window(per_sub_cache):
    """Pins the two age-reporting reads the search tool relies on: a fresh
    row is served by ``get_with_age``; a row past its TTL but inside the
    stale window is served only by ``get_stale_with_age``."""
    per_sub_cache.set("search", {"q": "fresh"}, "fresh-body", 3600, "alice")
    _set_in_past(
        per_sub_cache._for("alice"),
        150,
        "search",
        {"q": "old"},
        "old-body",
        100,
        "alice",
    )

    content, age = per_sub_cache.get_with_age("search", {"q": "fresh"}, "alice")
    assert content == "fresh-body"
    assert age >= 0
    assert per_sub_cache.get_with_age("search", {"q": "old"}, "alice") is None
    stale_content, stale_age = per_sub_cache.get_stale_with_age(
        "search", {"q": "old"}, "alice"
    )
    assert stale_content == "old-body"
    assert stale_age >= 150


def test_per_sub_cache_snapshots_and_clear(per_sub_cache):
    """Pins snapshot routing (newest first, per namespace) and that
    ``clear`` only empties the caller's own namespace."""
    per_sub_cache.record_snapshot("https://e.com", "v1", "alice")
    per_sub_cache.record_snapshot("https://e.com", "v2", "alice")
    per_sub_cache.set("search", {"q": "x"}, "a-body", None, "alice")
    per_sub_cache.set("search", {"q": "x"}, "b-body", None, "bob")

    snapshots = per_sub_cache.latest_snapshots("https://e.com", 2, "alice")
    assert [s["content"] for s in snapshots] == ["v2", "v1"]
    assert per_sub_cache.latest_snapshots("https://e.com", 2, "bob") == []

    assert per_sub_cache.clear(None, "alice") >= 1
    assert per_sub_cache.get("search", {"q": "x"}, "alice") is None
    assert per_sub_cache.get("search", {"q": "x"}, "bob") == "b-body"


def test_per_sub_cache_stats_for_one_namespace(per_sub_cache):
    """Pins ``stats(sub)``: counts come from that namespace's file only."""
    per_sub_cache.set("search", {"q": 1}, "a", None, "alice")
    per_sub_cache.set("search", {"q": 2}, "b", None, "alice")
    per_sub_cache.set("search", {"q": 3}, "c", None, "bob")

    stats = per_sub_cache.stats("alice")

    assert stats["search"]["total"] == 2
    assert stats["search"]["active"] == 2


def test_per_sub_cache_stats_without_sub_sums_every_namespace(per_sub_cache):
    """``stats()`` with no namespace must report the per-action counters
    summed over every open namespace file.

    ``WebCache.stats`` returns ``{action: {"total", "active", "hits"}}``; the
    old merge added those inner dicts with ``+`` and raised ``TypeError`` as
    soon as one namespace held a row.
    """
    per_sub_cache.set("search", {"q": 1}, "a", None, "alice")
    per_sub_cache.set("search", {"q": 2}, "b", None, "alice")
    per_sub_cache.set("search", {"q": 3}, "c", None, "bob")
    per_sub_cache.set("extract", {"u": 1}, "d", None, "bob")
    per_sub_cache.get("search", {"q": 3}, "bob")

    stats = per_sub_cache.stats()

    assert stats["search"]["total"] == 3
    assert stats["search"]["active"] == 3
    assert stats["search"]["hits"] == 1
    assert stats["extract"] == {"total": 1, "active": 1, "hits": 0}


def test_per_sub_cache_close_forgets_open_files(per_sub_cache):
    """Pins shutdown: ``close`` closes every namespace file and drops it, so
    a later call reopens instead of touching a closed connection."""
    per_sub_cache.set("search", {"q": 1}, "a", None, "alice")
    first = per_sub_cache._for("alice")

    per_sub_cache.close()

    assert per_sub_cache._caches == {}
    assert per_sub_cache._for("alice") is not first
    assert per_sub_cache.get("search", {"q": 1}, "alice") == "a"


# ---------------------------------------------------------------------------
# Shutdown and model registry helpers
# ---------------------------------------------------------------------------


async def test_lifespan_shutdown_with_nothing_opened(monkeypatch):
    """Pins shutdown when startup never opened the docs DB or the web cache:
    both stay ``None`` and nothing tries to close them."""
    monkeypatch.setattr(server, "_docs_db", None)
    monkeypatch.setattr(server, "_web_cache", None)
    monkeypatch.setattr(server, "_backend_init_task", None)
    with patch("wet.server.stop_searxng") as stop:
        await server._lifespan_shutdown(None)

    assert server._docs_db is None
    assert server._web_cache is None
    stop.assert_called_once()


def test_supported_model_ids_ignores_entries_without_a_string_id():
    """Pins the registry reader: dict rows, object rows and bare strings all
    count; a row whose id is not a string is skipped, not lower()-ed."""

    class _Registry:
        @classmethod
        def list_supported_models(cls):
            return [
                {"model": "Org/Dict-Model"},
                types.SimpleNamespace(model="Org/Attr-Model"),
                "Org/Bare",
                {"model": None},
                42,
            ]

    assert server._supported_model_ids(_Registry) == {
        "org/dict-model",
        "org/attr-model",
        "org/bare",
    }


def test_custom_embed_registration_value_error_is_not_fatal(monkeypatch):
    """Pins the re-init path: fastretrieval raising ``ValueError`` (already
    registered or invalid spec) must not escape server startup."""
    import fastretrieval

    monkeypatch.setattr(server.settings, "local_embedding_model", "Org/custom")
    monkeypatch.setattr(server.settings, "local_embedding_dim", 384)
    monkeypatch.setattr(
        fastretrieval.TextEmbedding, "list_supported_models", classmethod(lambda c: [])
    )

    def _raise(self):
        raise ValueError("already registered")

    monkeypatch.setattr(fastretrieval.CustomModelSpec, "register", _raise)

    server._maybe_register_custom_embed("Org/custom")


def test_custom_rerank_registration_value_error_is_not_fatal(monkeypatch):
    """Same contract as the embed path for a BYO local reranker."""
    import fastretrieval

    monkeypatch.setattr(server.settings, "local_rerank_model", "Org/custom-rr")
    monkeypatch.setattr(
        fastretrieval.TextCrossEncoder,
        "list_supported_models",
        classmethod(lambda c: []),
    )

    def _raise(self):
        raise ValueError("already registered")

    monkeypatch.setattr(fastretrieval.CustomRerankerSpec, "register", _raise)

    server._maybe_register_custom_rerank("Org/custom-rr")


# ---------------------------------------------------------------------------
# Backend init branches (the model backends are the external boundary)
# ---------------------------------------------------------------------------


class _Backend:
    """Stand-in for an embedding backend reporting ``dims`` native dims."""

    def __init__(self, dims: int) -> None:
        self.dims = dims

    async def check_available(self) -> int:
        return self.dims


async def test_cloud_embed_with_no_usable_dims_is_cleared(monkeypatch):
    """A configured cloud cell whose probe reports 0 dims must clear the
    backend instead of leaving a dead one installed."""
    cleared = []
    monkeypatch.setattr("wet.runtime.cell_configured", lambda t, settings=None: True)
    monkeypatch.setattr(
        "wet.embedder.init_backend", lambda mode, model=None: _Backend(0)
    )
    monkeypatch.setattr("wet.embedder.clear_backend", lambda: cleared.append(True))

    await server._init_embedding_backend()

    assert cleared == [True]


async def test_local_embed_sets_default_stored_dims(monkeypatch):
    """Pins the local path: a working local model with no stored dims yet
    stores at ``DEFAULT_EMBEDDING_DIMS``."""
    monkeypatch.setattr("wet.runtime.cell_configured", lambda t, settings=None: False)
    monkeypatch.setattr(server.settings, "local_embedding_model", "")
    monkeypatch.setattr(
        type(server.settings), "local_embed_available", lambda self: True
    )
    monkeypatch.setattr(
        "wet.embedder.init_backend", lambda mode, model=None: _Backend(384)
    )
    monkeypatch.setattr(server, "_embedding_dims", 0)

    await server._init_embedding_backend()

    assert server._embedding_dims == server.DEFAULT_EMBEDDING_DIMS


async def test_cloud_reranker_checked_on_the_event_loop(monkeypatch):
    """A ``CloudReranker`` is probed with ``await`` (its client is async);
    a passing probe keeps it installed."""
    from wet.reranker import CloudReranker

    reranker = CloudReranker.__new__(CloudReranker)
    probe = AsyncMock(return_value=True)
    monkeypatch.setattr(reranker, "check_available", probe, raising=False)
    cleared = []
    monkeypatch.setattr(server.settings, "rerank_enabled", True)
    monkeypatch.setattr("wet.runtime.cell_configured", lambda t, settings=None: True)
    monkeypatch.setattr("wet.reranker.init_reranker", lambda mode, model=None: reranker)
    monkeypatch.setattr("wet.reranker.clear_reranker", lambda: cleared.append(True))

    await server._init_reranker_backend()

    probe.assert_awaited_once()
    assert cleared == []


async def test_cloud_reranker_failing_probe_is_cleared(monkeypatch):
    """A configured cloud reranker whose probe fails must be cleared."""

    class _SyncReranker:
        def check_available(self) -> bool:
            return False

    cleared = []
    monkeypatch.setattr(server.settings, "rerank_enabled", True)
    monkeypatch.setattr("wet.runtime.cell_configured", lambda t, settings=None: True)
    monkeypatch.setattr(
        "wet.reranker.init_reranker", lambda mode, model=None: _SyncReranker()
    )
    monkeypatch.setattr("wet.reranker.clear_reranker", lambda: cleared.append(True))

    await server._init_reranker_backend()

    assert cleared == [True]


async def test_local_reranker_available_stays_installed(monkeypatch):
    """Pins the local reranker path when the ONNX model loads."""

    class _LocalReranker:
        def check_available(self) -> bool:
            return True

    cleared = []
    monkeypatch.setattr(server.settings, "rerank_enabled", True)
    monkeypatch.setattr(server.settings, "local_rerank_model", "")
    monkeypatch.setattr("wet.runtime.cell_configured", lambda t, settings=None: False)
    monkeypatch.setattr(
        type(server.settings), "local_rerank_available", lambda self: True
    )
    monkeypatch.setattr(
        "wet.reranker.init_reranker", lambda mode, model=None: _LocalReranker()
    )
    monkeypatch.setattr("wet.reranker.clear_reranker", lambda: cleared.append(True))

    await server._init_reranker_backend()

    assert cleared == []


# ---------------------------------------------------------------------------
# _rerank_results edge cases (the reranker model is the boundary)
# ---------------------------------------------------------------------------


class _Ranker:
    """Sync (local-style) reranker returning a fixed ranking."""

    def __init__(self, ranked):
        self.ranked = ranked

    def rerank(self, query, documents, top_n):
        return self.ranked


async def test_rerank_with_empty_ranking_keeps_source_order(monkeypatch):
    """A reranker answering with no ranking falls back to source order."""
    results = [{"content": "a"}, {"content": "b"}, {"content": "c"}]
    monkeypatch.setattr(server, "_backend_init_task", None)
    with patch(
        "wet.reranker.resolve_rerank_backend_for_request", return_value=_Ranker([])
    ):
        ranked, gate = await server._rerank_results("q", results, top_n=2)

    assert ranked == results[:2]
    assert gate is None


async def test_rerank_drops_indexes_outside_the_candidates(monkeypatch):
    """An index the reranker returns past the candidate list is skipped
    rather than raising ``IndexError``."""
    results = [{"content": "a"}, {"content": "b"}]
    monkeypatch.setattr(server, "_backend_init_task", None)
    with patch(
        "wet.reranker.resolve_rerank_backend_for_request",
        return_value=_Ranker([(7, 0.99), (1, 0.81234)]),
    ):
        ranked, _gate = await server._rerank_results("q", results, top_n=2)

    assert ranked == [{"content": "b", "score": 0.8123}]


def test_unified_diff_is_truncated_with_a_note():
    """Pins the output budget: a diff over ``_DIFF_MAX_CHARS`` is cut and
    says so."""
    old = "\n".join(f"old line {i}" for i in range(3000))
    new = "\n".join(f"new line {i}" for i in range(3000))

    diff = server._unified_diff_truncated(old, new, "https://e.com")

    assert diff.endswith("\n... (diff truncated at 20000 chars)")
    assert len(diff) == server._DIFF_MAX_CHARS + len(
        "\n... (diff truncated at 20000 chars)"
    )


# ---------------------------------------------------------------------------
# search action: cache replay with the real cache
# ---------------------------------------------------------------------------


async def test_search_fresh_cache_hit_is_standardized_without_a_backend_call(
    live_cache, no_reranker
):
    """A fresh cached envelope is replayed with freshness metadata and the
    backend chain is not called."""
    cached = {"results": [{"url": "https://a.com", "title": "A", "content": "x"}]}
    live_cache.set("search", _search_params("cached q"), json.dumps(cached))
    chain = AsyncMock(return_value=json.dumps({"results": []}))

    with patch.object(server, "_run_configured_search", chain):
        result = payload(await server.search("search", query="cached q"))

    chain.assert_not_called()
    assert result["results"][0]["url"] == "https://a.com"
    assert "stale" not in result


async def test_search_fresh_cache_hit_of_non_envelope_text_passes_through(
    live_cache, no_reranker
):
    """A cached payload that is not a results envelope is handed to the
    tool boundary as-is (an object envelope here)."""
    live_cache.set(
        "search", _search_params("odd q"), json.dumps({"note": "no results key"})
    )
    chain = AsyncMock()

    with patch.object(server, "_run_configured_search", chain):
        result = payload(await server.search("search", query="odd q"))

    chain.assert_not_called()
    assert result["note"] == "no results key"
    assert "results" not in result


async def test_search_stale_cache_hit_is_served_and_flagged(live_cache, no_reranker):
    """Stale-while-revalidate: an expired row inside the stale window is
    served with ``stale: true`` instead of hitting the backends."""
    cached = {"results": [{"url": "https://s.com", "title": "S", "content": "y"}]}
    _set_in_past(
        live_cache._for("default"),
        150,
        "search",
        _search_params("stale q"),
        json.dumps(cached),
        100,
        "default",
    )
    chain = AsyncMock()

    with patch.object(server, "_run_configured_search", chain):
        result = payload(await server.search("search", query="stale q"))

    chain.assert_not_called()
    assert result["stale"] is True
    assert result["results"][0]["url"] == "https://s.com"


async def test_search_stale_cache_hit_of_plain_text_passes_through(
    live_cache, no_reranker
):
    """A stale row holding non-JSON text is replayed through ``_payload``."""
    _set_in_past(
        live_cache._for("default"),
        150,
        "search",
        _search_params("stale text"),
        "plain cached text",
        100,
        "default",
    )

    with patch.object(server, "_run_configured_search", AsyncMock()):
        result = payload(await server.search("search", query="stale text"))

    assert result["error"] == "plain cached text"


async def test_search_stale_lookup_failure_falls_through_to_backends(
    monkeypatch, live_cache, no_reranker
):
    """A failing stale read must not fail the search: the chain runs."""

    def _boom(*args, **kwargs):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(live_cache, "get_stale_with_age", _boom)
    fresh = {"results": [{"url": "https://n.com", "title": "N", "content": "z"}]}
    chain = AsyncMock(return_value=json.dumps(fresh))

    with patch.object(server, "_run_configured_search", chain):
        result = payload(await server.search("search", query="no stale"))

    chain.assert_awaited_once()
    assert result["results"][0]["url"] == "https://n.com"


async def test_search_non_json_chain_payload_is_cached_and_returned(
    live_cache, no_reranker
):
    """Text from the chain that is not JSON is not an error: it is cached
    verbatim and reaches the tool boundary unchanged."""
    chain = AsyncMock(return_value="backend said hi")

    with patch.object(server, "_run_configured_search", chain):
        result = payload(await server.search("search", query="text q"))

    assert result["error"] == "backend said hi"
    assert live_cache.get("search", _search_params("text q")) == "backend said hi"


async def test_search_drops_results_without_body_and_backfills_snippet(
    live_cache, no_reranker
):
    """Results with neither content nor snippet are dropped (and ``total``
    recounted); a result with content but no snippet gets the content as
    its snippet."""
    chain_payload = {
        "results": [
            {"url": "https://empty.com", "title": "E", "content": " ", "snippet": ""},
            {"url": "https://body.com", "title": "B", "content": "real body"},
        ],
        "total": 2,
    }
    chain = AsyncMock(return_value=json.dumps(chain_payload))

    with patch.object(server, "_run_configured_search", chain):
        result = payload(await server.search("search", query="filter q"))

    assert [r["url"] for r in result["results"]] == ["https://body.com"]
    assert result["total"] == 1
    assert result["results"][0]["snippet"] == "real body"


async def test_search_attaches_the_rerank_gate_receipt(monkeypatch, live_cache):
    """When the jev cell is consulted at the rerank step its receipt rides
    in the response under ``jev``."""
    _jev_cell(monkeypatch, "0.2")
    results = [
        {"url": f"https://r{i}.com", "title": f"R{i}", "content": f"body {i}"}
        for i in range(3)
    ]
    chain = AsyncMock(return_value=json.dumps({"results": results}))
    monkeypatch.setattr(server, "_backend_init_task", None)

    with (
        patch(
            "wet.reranker.resolve_rerank_backend_for_request",
            return_value=_Ranker([(2, 0.9), (0, 0.5), (1, 0.1)]),
        ),
        patch.object(server, "_run_configured_search", chain),
    ):
        result = payload(await server.search("search", query="gate q", max_results=3))

    assert result["jev"]["gate"] == "rerank"
    assert result["jev"]["decision"] == "rerank"
    assert [r["url"] for r in result["results"]][0] == "https://r2.com"


async def test_refine_stops_when_the_rewritten_round_fails(live_cache, no_reranker):
    """A rewritten round that comes back unparseable ends refinement and the
    original round is kept."""
    chain = AsyncMock(
        side_effect=[json.dumps({"results": []}), "not json from round two"]
    )
    rewrite = AsyncMock(return_value="better query")

    with (
        patch.object(server, "_run_configured_search", chain),
        patch("wet.sources.search_strategies.rewrite_query", rewrite),
    ):
        result = payload(await server.search("search", query="refine q", refine=True))

    assert chain.await_count == 2
    rewrite.assert_awaited_once()
    assert result["results"] == []


async def test_enrich_with_no_results_skips_enrichment(live_cache, no_reranker):
    """``enrich=True`` on an empty result set must not call the enricher."""
    chain = AsyncMock(return_value=json.dumps({"results": []}))
    enrich = AsyncMock()

    with (
        patch.object(server, "_run_configured_search", chain),
        patch("wet.sources.search_strategies.enrich_snippets", enrich),
    ):
        result = payload(await server.search("search", query="enrich q", enrich=True))

    enrich.assert_not_called()
    assert result["results"] == []


async def test_search_cached_error_envelope_is_never_replayed(live_cache, no_reranker):
    """A cached failure (fresh or stale) must not be served: the chain runs
    again instead of replaying an outage for the entry's whole TTL."""
    live_cache.set(
        "search", _search_params("outage q"), json.dumps({"error": "backends down"})
    )
    fresh = {"results": [{"url": "https://ok.com", "title": "OK", "content": "b"}]}
    chain = AsyncMock(return_value=json.dumps(fresh))

    with patch.object(server, "_run_configured_search", chain):
        result = payload(await server.search("search", query="outage q"))

    chain.assert_awaited_once()
    assert result["results"][0]["url"] == "https://ok.com"


async def test_search_stale_hit_without_results_passes_through(live_cache, no_reranker):
    """A stale JSON object with no ``results`` is replayed as-is, without
    the ``stale`` flag the results envelope gets."""
    _set_in_past(
        live_cache._for("default"),
        150,
        "search",
        _search_params("stale obj"),
        json.dumps({"note": "kept"}),
        100,
        "default",
    )

    with patch.object(server, "_run_configured_search", AsyncMock()):
        result = payload(await server.search("search", query="stale obj"))

    assert result["note"] == "kept"
    assert "stale" not in result


async def test_wait_for_backend_init_waits_for_the_running_task(monkeypatch):
    """A request arriving during startup waits for backend init to finish."""
    import asyncio

    release = asyncio.Event()
    finished = []

    async def _init():
        await release.wait()
        finished.append(True)

    task = asyncio.create_task(_init())
    monkeypatch.setattr(server, "_backend_init_task", task)
    waiter = asyncio.create_task(server._wait_for_backend_init())
    await asyncio.sleep(0)
    assert not waiter.done()

    release.set()
    await waiter

    assert finished == [True]


async def test_help_reports_a_missing_doc_file(monkeypatch, tmp_path):
    """A valid tool name whose packaged doc is missing gets an error string,
    not an exception."""
    monkeypatch.setattr(server, "files", lambda package: tmp_path)

    message = await server.help("search")

    assert message == "Error: No documentation found for tool 'search'"


def test_running_index_without_timestamp_counts_as_in_flight():
    """A ``running`` row that cannot be aged out is treated as live."""
    assert server._index_attempt_in_flight({"state": server.INDEX_STATE_RUNNING})


def test_index_timestamp_without_a_value_is_described():
    """A missing timestamp renders as readable prose, not ``None``."""
    assert server._format_index_timestamp(None) == "an unrecorded time"


# ---------------------------------------------------------------------------
# Docs search helpers (registry, LLM and search chain are the boundaries)
# ---------------------------------------------------------------------------


def _poor_then_hyde_db(monkeypatch, first, hyde):
    from unittest.mock import MagicMock

    db = MagicMock()
    db.get_library.return_value = {"id": "lib1", "discovery_version": 10**6}
    db.get_best_version.return_value = {"id": "ver1", "chunk_count": 3}
    db.search.side_effect = [first, hyde]
    monkeypatch.setattr(server, "_docs_db", db)
    return db


class _EmbedBackend:
    async def embed_single(self, text, dimensions=None):
        return [0.5] * 4


async def test_hyde_results_replace_poor_results_when_better(monkeypatch):
    """Thin, low-score results trigger HyDE; its results win when their top
    score beats the original top score."""
    first = [{"content": "weak", "title": "W", "score": 0.1}]
    hyde = [{"content": "strong", "title": "S", "score": 0.9}]
    _poor_then_hyde_db(monkeypatch, first, hyde)
    monkeypatch.setattr(server, "_backend_init_task", None)

    with (
        patch(
            "wet.embedder.resolve_embed_backend_for_request",
            return_value=_EmbedBackend(),
        ),
        patch("wet.reranker.resolve_rerank_backend_for_request", return_value=None),
        patch(
            "wet.sources.search_strategies.generate_hyde_query",
            AsyncMock(return_value="a hypothetical answer"),
        ),
    ):
        out = await server._search_cached_index("fastapi", "routing", None, 10)

    assert out is not None
    assert [r["content"] for r in out["results"]] == ["strong"]


async def test_hyde_results_kept_out_when_not_better(monkeypatch):
    """HyDE results with a lower top score leave the original results."""
    first = [{"content": "orig", "title": "O", "score": 0.2}]
    hyde = [{"content": "worse", "title": "W", "score": 0.1}]
    _poor_then_hyde_db(monkeypatch, first, hyde)
    monkeypatch.setattr(server, "_backend_init_task", None)

    with (
        patch(
            "wet.embedder.resolve_embed_backend_for_request",
            return_value=_EmbedBackend(),
        ),
        patch("wet.reranker.resolve_rerank_backend_for_request", return_value=None),
        patch(
            "wet.sources.search_strategies.generate_hyde_query",
            AsyncMock(return_value="a hypothetical answer"),
        ),
    ):
        out = await server._search_cached_index("fastapi", "routing", None, 10)

    assert out is not None
    assert [r["content"] for r in out["results"]] == ["orig"]


async def test_good_results_skip_hyde(monkeypatch):
    """Three or more results above the HyDE threshold never consult HyDE."""
    good = [{"content": f"c{i}", "title": f"T{i}", "score": 0.99} for i in range(3)]
    _poor_then_hyde_db(monkeypatch, good, [])
    monkeypatch.setattr(server, "_backend_init_task", None)
    hyde = AsyncMock(return_value="unused")

    with (
        patch(
            "wet.embedder.resolve_embed_backend_for_request",
            return_value=_EmbedBackend(),
        ),
        patch("wet.reranker.resolve_rerank_backend_for_request", return_value=None),
        patch("wet.sources.search_strategies.generate_hyde_query", hyde),
    ):
        out = await server._search_cached_index("fastapi", "routing", None, 10)

    assert out is not None
    hyde.assert_not_awaited()
    assert len(out["results"]) == 3


async def test_discovered_registry_metadata_is_returned():
    """Registry discovery fills every field of the returned tuple."""
    discovery = {
        "homepage": "https://docs.example.com",
        "repository": "https://github.com/example/lib",
        "registry": "pypi",
        "description": "An example library",
    }
    with patch("wet.sources.docs.discover_library", AsyncMock(return_value=discovery)):
        found = await server._discover_docs_url("examplelib", "python")

    assert found == (
        "https://docs.example.com",
        "https://github.com/example/lib",
        "pypi",
        "An example library",
    )


async def test_immediate_fallback_search_carries_the_rerank_gate(monkeypatch):
    """The temporary web results shown while docs index are reranked and
    keep the jev receipt."""
    _jev_cell(monkeypatch, "0.1")
    monkeypatch.setattr(server, "_backend_init_task", None)
    results = [
        {"url": f"https://d{i}.example.com", "content": f"c{i}"} for i in range(2)
    ]
    chain = AsyncMock(return_value=json.dumps({"results": results}))

    with (
        patch.object(server, "_run_configured_search", chain),
        patch(
            "wet.reranker.resolve_rerank_backend_for_request",
            return_value=_Ranker([(1, 0.7), (0, 0.6)]),
        ),
    ):
        data = await server._do_immediate_fallback_search(
            docs_url="https://docs.example.com",
            library="examplelib",
            language=None,
            query="install",
            limit=2,
        )

    assert chain.await_args is not None
    assert chain.await_args.kwargs["query"] == "site:docs.example.com install"
    assert [r["url"] for r in data["results"]] == [
        "https://d1.example.com",
        "https://d0.example.com",
    ]
    assert data["jev"]["gate"] == "rerank"
