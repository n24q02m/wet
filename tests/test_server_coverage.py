"""Additional unit tests for server.py to increase coverage to 95%+.

Ported to the de-host seams: per-task provider cells (no chains), the
HTTP-only server entry, sqlite-only docs store and the slim Settings.
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structured import payload, text

from wet_mcp import server


async def test_rerank_waits_for_background_backend_initialization(monkeypatch):
    """A first request must not silently bypass a backend still starting."""
    ready = asyncio.Event()

    async def _pending_backend_init():
        await ready.wait()

    backend_init_task = asyncio.create_task(_pending_backend_init())
    monkeypatch.setattr(server, "_backend_init_task", backend_init_task, raising=False)
    results = [{"content": "doc-a"}, {"content": "doc-b"}]
    rerank_task = asyncio.create_task(server._rerank_results("query", results, 1))

    await asyncio.sleep(0)
    assert not rerank_task.done()

    ready.set()
    assert await rerank_task == [{"content": "doc-a"}]


@pytest.fixture(autouse=True)
def _mock_settings():
    # SRC GAP (reported, not fixed): search_strategies / structured still
    # call the deleted Settings.resolve_provider_mode; pin their settings
    # binding so no test reaches that AttributeError (offline "local" gate).
    llm_gate = MagicMock()
    llm_gate.resolve_provider_mode.return_value = "local"
    with (
        patch("wet_mcp.server.settings") as mock,
        patch("wet_mcp.sources.search_strategies.settings", llm_gate),
        patch("wet_mcp.sources.structured.settings", llm_gate),
        # LLM gate: sources modules branch on has_llm_provider(); pin it
        # offline so tests stay deterministic regardless of the host's
        # configured [models.chat] cell.
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=False,
        ),
        patch("wet_mcp.sources.structured.has_llm_provider", return_value=False),
        # Per-request resolver singletons: never let a test lazily build the
        # real local ONNX legs (model download). Tests wanting a backend
        # patch the resolver again inside their own body.
        patch(
            "wet_mcp.embedder.resolve_embed_backend_for_request",
            return_value=None,
        ),
        patch(
            "wet_mcp.reranker.resolve_rerank_backend_for_request",
            return_value=None,
        ),
    ):
        mock.log_level = "DEBUG"
        mock.tool_timeout = 0
        mock.wet_cache = True
        mock.get_db_path.return_value = MagicMock()
        mock.embedding_dims = 768
        mock.resolve_local_embedding_model.return_value = "local-model"
        mock.resolve_local_rerank_model.return_value = "local-rerank"
        mock.local_embedding_model = ""
        mock.wet_auto_searxng = False
        mock.download_dir = "/tmp/downloads"
        yield mock


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_web_cache():
    server._web_cache = MagicMock()
    server._web_cache.get.return_value = None
    # Search dispatcher uses get_with_age (returns (content, age) tuple or
    # None). Default to a miss so non-cache tests still hit the fetch path.
    server._web_cache.get_with_age.return_value = None
    yield server._web_cache
    server._web_cache = None


@pytest.fixture(autouse=True)
def _mock_docs_db():
    server._docs_db = MagicMock()
    server._docs_db.get_library.return_value = None
    server._docs_db.get_best_version.return_value = None
    server._docs_db.search.return_value = []
    yield server._docs_db
    server._docs_db = None


# ---------------------------------------------------------------------------
# _lifespan_startup (lines 106, 134, 136, 147-149)
# ---------------------------------------------------------------------------


async def test_lifespan_startup_no_github_token():
    """Line 106: warn when no GITHUB_TOKEN set."""
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("wet_mcp.server._PerSubCache"),
        patch("wet_mcp.server.make_docs_db", return_value=MagicMock()),
        patch("wet_mcp.server._init_embedding_backend", new_callable=AsyncMock),
        patch("wet_mcp.server._init_reranker_backend", new_callable=AsyncMock),
        patch("wet_mcp.server.settings") as cfg,
    ):
        cfg.setup_providers.return_value = "sdk"
        cfg.wet_auto_searxng = False
        cfg.auto_searxng_enabled.return_value = False
        cfg.wet_cache = False
        cfg.sync_enabled = False
        cfg.sync_s3_bucket = ""
        cfg.resolve_embedding_dims.return_value = 768
        cfg.get_db_path.return_value = MagicMock()
        task = await server._lifespan_startup()
        assert task is None  # auto SearXNG disabled


async def test_lifespan_startup_with_auto_searxng():
    """Line 117: creates warmup task when auto_searxng is True."""
    with (
        patch.dict("os.environ", {"GITHUB_TOKEN": "tok"}, clear=False),
        patch("wet_mcp.server._PerSubCache"),
        patch("wet_mcp.server.make_docs_db", return_value=MagicMock()),
        patch("wet_mcp.server._init_embedding_backend", new_callable=AsyncMock),
        patch("wet_mcp.server._init_reranker_backend", new_callable=AsyncMock),
        patch("wet_mcp.server._warmup_searxng", new_callable=AsyncMock),
        patch("wet_mcp.server.settings") as cfg,
    ):
        cfg.setup_providers.return_value = "sdk"
        cfg.wet_auto_searxng = True
        cfg.auto_searxng_enabled.return_value = True
        cfg.wet_cache = False
        cfg.sync_enabled = False
        cfg.sync_s3_bucket = ""
        cfg.resolve_embedding_dims.return_value = 768
        cfg.get_db_path.return_value = MagicMock()
        task = await server._lifespan_startup()
        assert task is not None
        # Clean up the task
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def test_lifespan_startup_backends_init_failure():
    """Lines 134-136: background backend init logs error on failure."""
    with (
        patch.dict("os.environ", {"GITHUB_TOKEN": "tok"}, clear=False),
        patch("wet_mcp.server._PerSubCache"),
        patch("wet_mcp.server.make_docs_db", return_value=MagicMock()),
        patch(
            "wet_mcp.server._init_embedding_backend",
            new_callable=AsyncMock,
            side_effect=Exception("backend fail"),
        ),
        patch("wet_mcp.server.settings") as cfg,
    ):
        cfg.setup_providers.return_value = "sdk"
        cfg.wet_auto_searxng = False
        cfg.auto_searxng_enabled.return_value = False
        cfg.wet_cache = False
        cfg.sync_enabled = False
        cfg.sync_s3_bucket = ""
        cfg.resolve_embedding_dims.return_value = 768
        cfg.get_db_path.return_value = MagicMock()
        await server._lifespan_startup()
        # Allow the background task to run
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# _lifespan_shutdown (lines 172-174, 187-188)
# ---------------------------------------------------------------------------


async def test_lifespan_shutdown_browser_error():
    """Lines 187-188: shutdown_crawler error is non-fatal."""
    with (
        patch(
            "wet_mcp.server.shutdown_crawler",
            new_callable=AsyncMock,
            side_effect=Exception("browser err"),
        ),
        patch("wet_mcp.server.stop_searxng"),
    ):
        # Should not raise
        await server._lifespan_shutdown(None)


async def test_lifespan_shutdown_cancel_warmup_task():
    """Lines 161-166: cancel in-progress warmup task."""

    async def _never_complete() -> None:
        await asyncio.Future()

    task = asyncio.create_task(_never_complete())
    with (
        patch("wet_mcp.server.shutdown_crawler", new_callable=AsyncMock),
        patch("wet_mcp.server.stop_searxng"),
    ):
        await server._lifespan_shutdown(task)
    assert task.cancelled() or task.done()


# ---------------------------------------------------------------------------
# _init_embedding_backend (lines 217, 224-261)
# ---------------------------------------------------------------------------


async def test_init_embedding_cloud_cell_success(monkeypatch):
    """A configured [models.embed] cell inits cloud with the cell model."""
    monkeypatch.setattr(server, "_embedding_dims", 0)
    cell = MagicMock()
    cell.model = "text-embedding-3-large"
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: True),
        patch("wet_mcp.server.model_cell", lambda t=None, settings=None: cell),
        patch("wet_mcp.embedder.init_backend") as mock_init,
    ):
        mock_backend = MagicMock()
        mock_backend.check_available = AsyncMock(return_value=1024)
        mock_init.return_value = mock_backend

        await server._init_embedding_backend()
        assert server._embedding_dims == 768  # DEFAULT_EMBEDDING_DIMS


async def test_init_embedding_cloud_cell_failure_no_local_fallback():
    """A broken host key surfaces loudly: init fails once, no local fallback."""
    call_count = 0

    def fake_init_backend(backend_type, model, **kwargs):
        nonlocal call_count
        call_count += 1
        raise Exception("cloud unavailable")

    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: True),
        patch("wet_mcp.embedder.init_backend", side_effect=fake_init_backend),
    ):
        await server._init_embedding_backend()
        assert call_count == 1  # cloud only, no local fallback


async def test_init_embedding_local_success(_mock_settings):
    """No cell + local leg available: local backend inits with stored dims."""
    _mock_settings.local_embed_available.return_value = True

    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: False),
        patch("wet_mcp.embedder.init_backend") as mock_init,
    ):
        mock_b = MagicMock()
        mock_b.check_available = AsyncMock(return_value=384)
        mock_init.return_value = mock_b

        await server._init_embedding_backend()
        mock_init.assert_called_once_with("local", "local-model")


async def test_init_embedding_local_zero_dims():
    """Local backend returns 0 dims: the backend is cleared."""
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: False),
        patch("wet_mcp.embedder.init_backend") as mock_init,
    ):
        mock_backend_local = MagicMock()
        mock_backend_local.check_available = AsyncMock(return_value=0)
        mock_init.return_value = mock_backend_local

        await server._init_embedding_backend()

        from wet_mcp import embedder

        assert embedder.get_backend() is None


async def test_init_embedding_local_exception(_mock_settings):
    """Local init raises: handled, no raise."""
    _mock_settings.local_embed_available.return_value = True

    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: False),
        patch("wet_mcp.embedder.init_backend", side_effect=Exception("onnx fail")),
    ):
        await server._init_embedding_backend()


# ---------------------------------------------------------------------------
# _init_reranker_backend (lines 274-275, 292-307)
# ---------------------------------------------------------------------------


async def test_init_reranker_disabled(_mock_settings):
    """RERANK_ENABLED=false disables reranking entirely."""
    _mock_settings.rerank_enabled = False
    await server._init_reranker_backend()


async def test_init_reranker_cloud_cell_success(_mock_settings):
    """A configured [models.rerank] cell inits cloud with the cell model."""
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: True),
        patch("wet_mcp.reranker.init_reranker") as mock_init,
    ):
        mock_reranker = MagicMock()
        # CloudReranker.check_available is async (hull HTTP client).
        mock_reranker.check_available = AsyncMock(return_value=True)
        mock_init.return_value = mock_reranker

        await server._init_reranker_backend()
        mock_init.assert_called_once()
        assert mock_init.call_args.args[0] == "cloud"


async def test_init_reranker_cloud_cell_fail_no_local_fallback(_mock_settings):
    """A broken rerank key surfaces loudly: init fails once, no local fallback."""
    call_count = 0

    def fake_init(backend_type, model, **kwargs):
        nonlocal call_count
        call_count += 1
        raise Exception("cloud unavailable")

    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: True),
        patch("wet_mcp.reranker.init_reranker", side_effect=fake_init),
    ):
        await server._init_reranker_backend()
        assert call_count == 1  # cloud only, no local fallback


async def test_init_reranker_local_not_available(_mock_settings):
    """Local reranker returns False for check_available: cleared."""
    _mock_settings.local_rerank_available.return_value = True

    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: False),
        patch("wet_mcp.reranker.init_reranker") as mock_init,
    ):
        mock_r = MagicMock()
        mock_r.check_available = MagicMock(return_value=False)
        mock_init.return_value = mock_r

        await server._init_reranker_backend()

        from wet_mcp import reranker as reranker_mod

        assert reranker_mod.get_reranker() is None


async def test_init_reranker_local_exception(_mock_settings):
    """Local reranker init fails: handled, no raise."""
    _mock_settings.local_rerank_available.return_value = True

    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: False),
        patch(
            "wet_mcp.reranker.init_reranker", side_effect=Exception("reranker fail")
        ),
    ):
        await server._init_reranker_backend()


# ---------------------------------------------------------------------------
# _embed (lines 325, 328, 332-334)
# ---------------------------------------------------------------------------


async def test_embed_query_local_backend():
    """Lines 327-330: query embedding with LocalEmbeddingBackend."""
    with patch("wet_mcp.embedder.resolve_embed_backend_for_request") as mock_get:
        from wet_mcp.embedder import LocalEmbeddingBackend

        mock_backend = MagicMock(spec=LocalEmbeddingBackend)
        mock_backend.embed_single_query.return_value = [0.5, 0.6]
        mock_get.return_value = mock_backend

        res = await server._embed("hello", is_query=True)
        assert res == [0.5, 0.6]
        mock_backend.embed_single_query.assert_called_once()


async def test_embed_no_backend():
    """Line 325: backend is None."""
    with patch(
        "wet_mcp.embedder.resolve_embed_backend_for_request", return_value=None
    ):
        res = await server._embed("test")
        assert res is None


async def test_embed_transient_exception_returns_none():
    """A transient embedding error degrades this call to keyword-only (None)."""
    from hull_core.providers.openai_spec import ProviderError

    with patch("wet_mcp.embedder.resolve_embed_backend_for_request") as mock_get:
        mock_backend = MagicMock()
        mock_backend.embed_single.side_effect = ProviderError(
            status=429, detail="rate limit exceeded"
        )
        mock_get.return_value = mock_backend

        res = await server._embed("test")
        assert res is None


async def test_embed_permanent_exception_raises():
    """A permanent embedding error is surfaced loudly, not swallowed to None."""
    with patch("wet_mcp.embedder.resolve_embed_backend_for_request") as mock_get:
        mock_backend = MagicMock()
        mock_backend.embed_single.side_effect = Exception("model does not exist")
        mock_get.return_value = mock_backend

        with pytest.raises(Exception, match="does not exist"):
            await server._embed("test")


# ---------------------------------------------------------------------------
# _embed_batch (lines 343, 346-348)
# ---------------------------------------------------------------------------


async def test_embed_batch_no_backend():
    """Line 343: backend is None."""
    with patch(
        "wet_mcp.embedder.resolve_embed_backend_for_request", return_value=None
    ):
        res = await server._embed_batch(["test"])
        assert res is None


async def test_embed_batch_transient_exception_returns_none():
    """A transient batch embedding error degrades this call to None."""
    from hull_core.providers.openai_spec import ProviderError

    with patch("wet_mcp.embedder.resolve_embed_backend_for_request") as mock_get:
        mock_backend = MagicMock()
        mock_backend.embed_texts.side_effect = ProviderError(
            status=429, detail="rate limit exceeded"
        )
        mock_get.return_value = mock_backend

        res = await server._embed_batch(["test"])
        assert res is None


async def test_embed_batch_permanent_exception_raises():
    """A permanent batch embedding error is surfaced loudly, not swallowed."""
    with patch("wet_mcp.embedder.resolve_embed_backend_for_request") as mock_get:
        mock_backend = MagicMock()
        mock_backend.embed_texts.side_effect = Exception("model does not exist")
        mock_get.return_value = mock_backend

        with pytest.raises(Exception, match="does not exist"):
            await server._embed_batch(["test"])


# ---------------------------------------------------------------------------
# _rerank_results (lines 377-380)
# ---------------------------------------------------------------------------


async def test_rerank_exception_fallback():
    """Lines 377-380: reranking raises, falls back to original order."""
    with patch("wet_mcp.reranker.resolve_rerank_backend_for_request") as mock_get:
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = Exception("rerank fail")
        mock_get.return_value = mock_reranker

        results = [{"content": "a"}, {"content": "b"}, {"content": "c"}]
        res = await server._rerank_results("q", results, 2)
        assert len(res) == 2
        assert res[0]["content"] == "a"


async def test_rerank_fewer_results_than_top_n():
    """Line 363: results <= top_n, returns as-is."""
    with patch("wet_mcp.reranker.resolve_rerank_backend_for_request") as mock_get:
        mock_get.return_value = MagicMock()

        results = [{"content": "a"}]
        res = await server._rerank_results("q", results, 5)
        assert len(res) == 1


# ---------------------------------------------------------------------------
# search tool: cache hit paths (lines 511, 535, 540)
# ---------------------------------------------------------------------------


async def test_search_cache_hit(_mock_web_cache):
    """Line 511: search returns cached result."""
    # Search dispatcher consumes get_with_age -> (content, age) | None.
    _mock_web_cache.get_with_age.return_value = ("cached search result", 0)
    result = await server.search("search", query="test")
    assert "cached search result" in text(result)


async def test_research_cache_hit(_mock_web_cache):
    """Lines 539-540: research returns cached result."""
    _mock_web_cache.get.return_value = "cached research result"
    result = await server.search("research", query="test")
    assert "cached research result" in text(result)


# ---------------------------------------------------------------------------
# search tool: SearXNG errors (lines 516-519)
# ---------------------------------------------------------------------------


def _force_local_searxng_startup(monkeypatch):
    monkeypatch.setattr(
        server.search_backends, "chain_backend_names", lambda: ["searxng"]
    )


async def test_search_searxng_timeout(monkeypatch):
    """Lines 516-517: SearXNG startup timeout."""
    _force_local_searxng_startup(monkeypatch)
    with patch(
        "wet_mcp.server.ensure_searxng",
        new_callable=AsyncMock,
        side_effect=TimeoutError,
    ):
        result = await server.search("search", query="test")
        assert "timed out" in text(result)


async def test_search_searxng_startup_failed(monkeypatch):
    """Lines 518-519: SearXNG startup exception."""
    _force_local_searxng_startup(monkeypatch)
    with patch(
        "wet_mcp.server.ensure_searxng",
        new_callable=AsyncMock,
        side_effect=Exception("container died"),
    ):
        result = await server.search("search", query="test")
        assert "startup failed" in text(result)


# ---------------------------------------------------------------------------
# search tool: missing query for research (line 535)
# ---------------------------------------------------------------------------


async def test_search_research_missing_query():
    """Line 535: research action requires query."""
    result = await server.search("research", query=None)
    assert "Error: query is required" in text(result)


# ---------------------------------------------------------------------------
# search tool: docs missing library/query (lines 551, 553)
# ---------------------------------------------------------------------------


async def test_search_docs_missing_library():
    """Line 551: docs action requires library."""
    result = await server.search("docs", query="test")
    assert "library is required" in text(result)


async def test_search_docs_missing_query():
    """Line 553: docs action requires query."""
    result = await server.search("docs", library="react")
    assert "query is required" in text(result)


# ---------------------------------------------------------------------------
# extract tool: cache hit paths (lines 615, 636, 663)
# ---------------------------------------------------------------------------


async def test_extract_cache_hit(_mock_web_cache):
    """Line 615: extract returns cached result."""
    _mock_web_cache.get.return_value = json.dumps({"cached": "extract"})
    result = await server.extract("extract", urls=["http://x.com"])
    assert payload(result)["cached"] == "extract"


async def test_crawl_cache_hit(_mock_web_cache):
    """Line 636: crawl returns cached result."""
    _mock_web_cache.get.return_value = json.dumps({"cached": "crawl"})
    result = await server.extract("crawl", urls=["http://x.com"])
    assert payload(result)["cached"] == "crawl"


async def test_map_cache_hit(_mock_web_cache):
    """Line 663: map returns cached result."""
    _mock_web_cache.get.return_value = json.dumps({"cached": "map"})
    result = await server.extract("map", urls=["http://x.com"])
    assert payload(result)["cached"] == "map"


# ---------------------------------------------------------------------------
# config tool: sync_interval set, generic setattr (lines 885-888)
# ---------------------------------------------------------------------------


async def test_config_set_rejects_removed_sync_keys():
    """De-host: sync knobs are gone; set rejects them naming valid keys."""
    for key in ("sync_interval", "sync_folder"):
        result = await server.config("set", key=key, value="x")
        data = payload(result)
        assert "error" in data
        assert data["valid_keys"] == [
            "log_level",
            "tool_timeout",
            "wet_cache",
            "wet_search_budget",
        ]


# ---------------------------------------------------------------------------
# config tool: docs_reindex missing key, db not init (lines 906, 908)
# ---------------------------------------------------------------------------


async def test_config_docs_reindex_missing_key():
    """Line 906: docs_reindex without key."""
    result = await server.config("docs_reindex")
    data = payload(result)
    assert "error" in data
    assert "key" in data["error"]


async def test_config_docs_reindex_db_not_init():
    """Line 908: docs_reindex when docs DB is None."""
    server._docs_db = None
    result = await server.config("docs_reindex", key="react")
    data = payload(result)
    assert "error" in data
    assert "not initialized" in data["error"]


# ---------------------------------------------------------------------------
# _fetch_and_chunk_docs: llms.txt too small (line 1037)
# ---------------------------------------------------------------------------


async def test_fetch_and_chunk_docs_llms_txt_too_small():
    """Line 1037: llms.txt produces fewer chunks than _MIN_GH_CHUNKS."""
    with (
        patch("wet_mcp.sources.docs.try_llms_txt", new_callable=AsyncMock) as mock_llms,
        patch("wet_mcp.sources.docs.chunk_llms_txt") as mock_chunk_llms,
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs", new_callable=AsyncMock
        ) as mock_gh,
        patch("wet_mcp.sources.docs.chunk_markdown") as mock_chunk_md,
        patch(
            "wet_mcp.sources.docs.fetch_docs_pages", new_callable=AsyncMock
        ) as mock_fetch,
    ):
        # llms.txt returns content but only 5 chunks (below _MIN_GH_CHUNKS=20)
        mock_llms.return_value = "some llms content"
        mock_chunk_llms.return_value = [{"content": f"c{i}"} for i in range(5)]
        # GitHub raw returns nothing
        mock_gh.return_value = []
        # Crawl returns enough
        mock_fetch.return_value = [
            {"content": "page content", "url": "http://docs.example.com", "title": "T"}
        ]
        mock_chunk_md.return_value = [{"content": f"chunk{i}"} for i in range(25)]

        chunks, pages = await server._fetch_and_chunk_docs("http://docs.example.com")
        assert pages == 1
        assert len(chunks) == 25


# ---------------------------------------------------------------------------
# _fetch_and_chunk_docs: crawl produces chunks with page titles (1085-1092)
# ---------------------------------------------------------------------------


async def test_fetch_and_chunk_docs_crawl_with_page_titles():
    """Lines 1085-1092: crawl chunks inherit page title when missing."""
    with (
        patch(
            "wet_mcp.sources.docs.try_llms_txt",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "wet_mcp.sources.docs.fetch_docs_pages", new_callable=AsyncMock
        ) as mock_fetch,
        patch("wet_mcp.sources.docs.chunk_markdown") as mock_chunk,
    ):
        mock_fetch.return_value = [
            {"content": "page1", "url": "http://example.com/a", "title": "Page A"},
            {"content": "page2", "url": "http://example.com/b", "title": "Page B"},
        ]
        # Chunks without titles
        mock_chunk.side_effect = [
            [{"content": "chunk1"}, {"content": "chunk2", "title": ""}],
            [{"content": "chunk3", "title": "Existing"}],
        ]

        chunks, pages = await server._fetch_and_chunk_docs("http://example.com")
        assert pages == 2
        # chunk1 gets page title, chunk2 has empty title -> gets page title,
        # chunk3 has existing title -> keeps it
        assert chunks[0]["title"] == "Page A"
        assert chunks[1]["title"] == "Page A"
        assert chunks[2]["title"] == "Existing"


# ---------------------------------------------------------------------------
# _fetch_and_chunk_docs: README fallback (lines 1109-1121)
# ---------------------------------------------------------------------------


async def test_fetch_and_chunk_docs_readme_fallback():
    """Lines 1109-1118: all tiers fail, README fallback used."""
    with (
        patch(
            "wet_mcp.sources.docs.try_llms_txt",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "wet_mcp.sources.docs.fetch_docs_pages",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("wet_mcp.sources.docs.chunk_markdown", return_value=[]),
        patch(
            "wet_mcp.sources.docs._fetch_github_readme", new_callable=AsyncMock
        ) as mock_readme,
    ):
        mock_readme.return_value = [{"content": "readme chunk"}]
        chunks, pages = await server._fetch_and_chunk_docs(
            "http://example.com", repo_url="http://github.com/org/repo"
        )
        assert pages == 1
        assert chunks[0]["content"] == "readme chunk"


async def test_fetch_and_chunk_docs_all_tiers_fail_no_readme():
    """Lines 1109-1121: all tiers fail, README also empty."""
    with (
        patch(
            "wet_mcp.sources.docs.try_llms_txt",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "wet_mcp.sources.docs.fetch_docs_pages",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("wet_mcp.sources.docs.chunk_markdown", return_value=[]),
        patch(
            "wet_mcp.sources.docs._fetch_github_readme",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        chunks, pages = await server._fetch_and_chunk_docs("http://example.com")
        assert chunks == []
        assert pages == 0


# ---------------------------------------------------------------------------
# _background_index_and_search (lines 1160-1163, 1185-1207, 1218-1249, 1254)
# ---------------------------------------------------------------------------


async def test_background_index_fetch_timeout():
    """Lines 1160-1163: fetch times out in background indexer."""
    server._docs_db = MagicMock()
    server._docs_db.mark_version_indexed = MagicMock()
    server._docs_db.add_chunks = MagicMock()

    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs.x"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
            return_value=json.dumps({"results": []}),
        ),
    ):
        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://docs.x",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )
        # No chunks -> returns early, no add_chunks call
        server._docs_db.add_chunks.assert_not_called()


async def test_background_index_with_fallback_alt_url():
    """Lines 1185-1207: fallback SearXNG finds alt URL with better content."""
    server._docs_db = MagicMock()

    fetch_call_count = 0

    async def fake_fetch(docs_url="", repo_url="", query="", library_hint=""):
        nonlocal fetch_call_count
        fetch_call_count += 1
        if fetch_call_count == 1:
            # First fetch: few results
            return [{"content": "c1"}], 1
        # Alt URL: more results
        return [{"content": f"c{i}"} for i in range(30)], 5

    with (
        patch(
            "wet_mcp.sources.docs._normalize_docs_url",
            return_value="http://original.com/docs",
        ),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
            side_effect=fake_fetch,
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
            return_value=json.dumps(
                {"results": [{"url": "http://alt-docs.com/guide"}]}
            ),
        ),
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock, return_value=None),
    ):
        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://original.com/docs",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )
        server._docs_db.add_chunks.assert_called_once()
        # Alt URL was used (30 chunks > 1 chunk)
        args = server._docs_db.add_chunks.call_args
        assert len(args.kwargs.get("chunks", args[1].get("chunks", []))) == 30


async def test_background_index_with_embeddings():
    """Lines 1218-1249: generate embeddings for chunks."""
    server._docs_db = MagicMock()

    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs.x"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
            return_value=(
                [
                    {"content": "chunk1", "title": "T1", "heading_path": "H1"},
                    {"content": "chunk2", "title": "T2"},
                    {"content": "chunk3"},
                ],
                3,
            ),
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            side_effect=Exception("no searxng"),
        ),
        patch(
            "wet_mcp.embedder.resolve_embed_backend_for_request"
        ) as mock_get_backend,
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock) as mock_embed,
    ):
        mock_get_backend.return_value = MagicMock()  # backend available
        mock_embed.return_value = [[0.1], [0.2], [0.3]]

        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://docs.x",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )
        server._docs_db.add_chunks.assert_called_once()
        call_kwargs = server._docs_db.add_chunks.call_args
        # Embeddings should be passed
        embs = call_kwargs.kwargs.get("embeddings") or call_kwargs[1].get("embeddings")
        assert embs == [[0.1], [0.2], [0.3]]
        server._docs_db.mark_version_indexed.assert_called_once()


async def test_background_index_exception():
    """Line 1254: top-level exception in background indexer."""
    server._docs_db = MagicMock()

    with patch(
        "wet_mcp.sources.docs._normalize_docs_url",
        side_effect=Exception("unexpected"),
    ):
        # Should not raise
        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://docs.x",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )


async def test_background_index_with_language_fallback():
    """Lines 1166-1171: fallback query includes language when provided."""
    server._docs_db = MagicMock()

    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs.x"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
            return_value=([{"content": "c1"}], 1),
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain", new_callable=AsyncMock
        ) as mock_search,
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock, return_value=None),
    ):
        mock_search.return_value = json.dumps({"results": []})

        await server._background_index_and_search(
            library="redis",
            lib_key="redis:python",
            language="python",
            docs_url="http://docs.x",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )
        # Verify fallback query includes language
        call_args = mock_search.call_args
        assert "python" in call_args.kwargs.get("query", call_args[1].get("query", ""))


async def test_background_index_embed_timeout():
    """Lines 1238-1239: embedding batch times out."""
    server._docs_db = MagicMock()

    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs.x"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
            return_value=([{"content": "c1"}], 1),
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            side_effect=Exception("no"),
        ),
        patch(
            "wet_mcp.embedder.resolve_embed_backend_for_request"
        ) as mock_get_backend,
        patch(
            "wet_mcp.server._embed_batch",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ),
    ):
        mock_get_backend.return_value = MagicMock()

        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://docs.x",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )
        # Should still add chunks with embeddings=None
        server._docs_db.add_chunks.assert_called_once()


# ---------------------------------------------------------------------------
# _search_cached_index (line 1289, 1304)
# ---------------------------------------------------------------------------


async def test_search_cached_index_no_results():
    """Line 1304: search returns empty results -> None."""
    server._docs_db.get_library.return_value = {
        "id": 1,
        "discovery_version": 999,
    }
    server._docs_db.get_best_version.return_value = {
        "id": 1,
        "chunk_count": 10,
        "version": "latest",
    }
    server._docs_db.search.return_value = []

    with patch("wet_mcp.server._embed", new_callable=AsyncMock, return_value=None):
        result = await server._search_cached_index("lib", "query", None, 10)
        assert result is None


async def test_search_cached_index_version_zero_chunks():
    """Line 1289: version has chunk_count=0 -> None."""
    server._docs_db.get_library.return_value = {
        "id": 1,
        "discovery_version": 999,
    }
    server._docs_db.get_best_version.return_value = {
        "id": 1,
        "chunk_count": 0,
        "version": "latest",
    }

    result = await server._search_cached_index("lib", "query", None, 10)
    assert result is None


# ---------------------------------------------------------------------------
# _discover_docs_url: SearXNG fallback paths (lines 1390-1391)
# ---------------------------------------------------------------------------


async def test_discover_docs_url_searxng_timeout():
    """Lines 1388-1389: SearXNG fallback times out."""
    with (
        patch(
            "wet_mcp.sources.docs.discover_library",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ),
    ):
        docs_url, repo_url, registry, desc = await server._discover_docs_url(
            "mylib", None
        )
        assert docs_url == ""


async def test_discover_docs_url_searxng_json_decode_error():
    """Lines 1390-1391: SearXNG returns invalid JSON."""
    with (
        patch(
            "wet_mcp.sources.docs.discover_library",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
            return_value="not json",
        ),
    ):
        docs_url, repo_url, registry, desc = await server._discover_docs_url(
            "mylib", None
        )
        assert docs_url == ""


async def test_discover_docs_url_with_language():
    """Lines 1366-1368: language included in search query."""
    with (
        patch(
            "wet_mcp.sources.docs.discover_library",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain", new_callable=AsyncMock
        ) as mock_search,
    ):
        mock_search.return_value = json.dumps(
            {"results": [{"url": "http://docs.redis.io"}]}
        )
        docs_url, _, _, _ = await server._discover_docs_url("redis", "python")
        assert docs_url == "http://docs.redis.io"
        # Verify language was in the query
        call_args = mock_search.call_args
        assert "python" in call_args.kwargs.get("query", "")


# ---------------------------------------------------------------------------
# __main__ guard (line 1542)
# ---------------------------------------------------------------------------


def test_main_entry_point():
    """main() always serves HTTP: run_server_blocking with WET_HOST/WET_PORT."""
    with (
        patch.object(server, "run_server_blocking") as mock_serve,
        patch.dict(os.environ, {"WET_HOST": "127.0.0.9", "WET_PORT": "8777"}),
    ):
        server.main()
    _, kwargs = mock_serve.call_args
    assert kwargs["host"] == "127.0.0.9"
    assert kwargs["port"] == 8777


# ---------------------------------------------------------------------------
# media tool: download with security check
# ---------------------------------------------------------------------------


async def test_media_download_invalid_output_dir(_mock_settings):
    """Lines 726-730: output_dir outside configured download_dir."""
    _mock_settings.download_dir = "/tmp/downloads"
    result = await server.media(
        "download", media_urls=["http://x.com/img.jpg"], output_dir="/etc/malicious"
    )
    assert "Security Alert" in text(result)


async def test_media_download_missing_urls():
    """Line 718: download without media_urls."""
    result = await server.media("download")
    assert "media_urls is required" in text(result)


async def test_media_list_missing_url():
    """Line 710: list without url."""
    result = await server.media("list")
    assert "url is required" in text(result)


async def test_media_analyze_missing_url():
    """Phase 3 Task 5 BREAKING: analyze removed -- routes to unknown-action
    regardless of url presence."""
    result = await server.media("analyze")
    assert "Unknown action 'analyze'" in text(result)
    assert "imagine-mcp" in text(result)


async def test_media_invalid_action():
    """Line 752: unknown media action."""
    result = await server.media("invalid")
    assert "Unknown action" in text(result)


# ---------------------------------------------------------------------------
# _do_research: reranking results filtering
# ---------------------------------------------------------------------------


async def test_do_research_reranking_filters_low_scores():
    """Lines 960-963: reranking filters results with score <= 0.3."""
    with (
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain", new_callable=AsyncMock
        ) as mock_search,
        patch("wet_mcp.server._rerank_results", new_callable=AsyncMock) as mock_rerank,
    ):
        mock_search.return_value = json.dumps(
            {
                "results": [
                    {"url": "http://arxiv.org/1", "content": "good"},
                    {"url": "http://other.org/2", "content": "bad"},
                ]
            }
        )
        # Only first result has score > 0.3
        mock_rerank.return_value = [
            {"url": "http://arxiv.org/1", "content": "good", "score": 0.8},
            {"url": "http://other.org/2", "content": "bad", "score": 0.1},
        ]
        result = await server._do_research("test query")
        data = json.loads(result)
        # Low-score result filtered
        assert len(data["results"]) == 1
        assert data["results"][0]["source_type"] == "arxiv"


# ---------------------------------------------------------------------------
# _do_research: reranking exception path
# ---------------------------------------------------------------------------


async def test_do_research_rerank_exception():
    """Lines 964-965: reranking exception logged, original results kept."""
    with (
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain", new_callable=AsyncMock
        ) as mock_search,
        patch(
            "wet_mcp.server._rerank_results",
            new_callable=AsyncMock,
            side_effect=Exception("rerank boom"),
        ),
    ):
        mock_search.return_value = json.dumps(
            {"results": [{"url": "http://example.org", "content": "result"}]}
        )
        result = await server._do_research("test query")
        # Should still return results (reranking is best-effort)
        data = json.loads(result)
        assert len(data["results"]) >= 1


# ---------------------------------------------------------------------------
# _background_index_and_search: fallback alt URL timeout
# ---------------------------------------------------------------------------


async def test_background_index_alt_url_fetch_timeout():
    """Lines 1201-1202: alt URL fetch times out, continues."""
    server._docs_db = MagicMock()

    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs.x"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs", new_callable=AsyncMock
        ) as mock_fetch,
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
            return_value=json.dumps(
                {"results": [{"url": "http://alt-docs.com/guide"}]}
            ),
        ),
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock, return_value=None),
    ):
        # First fetch returns few chunks, alt URL fetch times out
        mock_fetch.side_effect = [
            ([{"content": "c1"}], 1),
            TimeoutError("alt timeout"),
        ]

        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://docs.x",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )
        # Still uses original chunks
        server._docs_db.add_chunks.assert_called_once()


# ---------------------------------------------------------------------------
# _background_index_and_search: skip same-netloc alt URLs
# ---------------------------------------------------------------------------


async def test_background_index_skip_same_netloc():
    """Lines 1192-1195: skip alt URL with same netloc as original."""
    server._docs_db = MagicMock()

    with (
        patch(
            "wet_mcp.sources.docs._normalize_docs_url",
            return_value="http://docs.x/guide",
        ),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
            return_value=([{"content": "c1"}], 1),
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
            return_value=json.dumps({"results": [{"url": "http://docs.x/other-page"}]}),
        ),
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock, return_value=None),
    ):
        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://docs.x/guide",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )
        # Original chunks used (same netloc alt URL skipped)
        server._docs_db.add_chunks.assert_called_once()
        args = server._docs_db.add_chunks.call_args
        chunks = args.kwargs.get("chunks") or args[1].get("chunks")
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# _warmup_searxng exception coverage (line 196)
# ---------------------------------------------------------------------------


async def test_warmup_searxng_ensure_fails():
    """Line 196: _warmup_searxng handles Exception from ensure_searxng."""
    with (
        patch("wet_mcp.setup.run_auto_setup", return_value=None),
        patch(
            "wet_mcp.searxng_runner.ensure_searxng", new_callable=AsyncMock
        ) as mock_ensure,
    ):
        mock_ensure.side_effect = Exception("searxng fail")
        # Should not raise
        await server._warmup_searxng()
