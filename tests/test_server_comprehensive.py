import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structured import payload, text

from wet_mcp import server


@pytest.fixture(autouse=True)
def _no_llm_provider_mode():
    """Force the offline LLM gate in the sources modules.

    The gate is ``has_llm_provider()`` (the [models.chat] cell); pinning it
    keeps hyde/expand/rewrite/find_similar/structured deterministic and
    network-free regardless of the host's ~/.wet/config.toml. The settings
    pin is belt-and-braces for any remaining direct settings reads in
    those modules (legacy resolve_provider_mode-era).
    """
    mock = MagicMock()
    mock.resolve_provider_mode.return_value = "local"
    with (
        patch("wet_mcp.sources.search_strategies.settings", mock),
        patch("wet_mcp.sources.structured.settings", mock),
        patch(
            "wet_mcp.sources.search_strategies.has_llm_provider",
            return_value=False,
        ),
        patch("wet_mcp.sources.structured.has_llm_provider", return_value=False),
    ):
        yield mock

# Windows IOCP event loop hangs on fire-and-forget asyncio.create_task
# teardown in _do_docs_search and _background_index_and_search tests.
# These tests pass on Linux CI.
_skip_win_iocp = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows IOCP hangs on fire-and-forget create_task teardown",
)


def _close_and_dummy_task(coro, label=None):
    """Drop-in for ``server._launch_background_task`` in tests.

    The production ``_do_docs_search`` fires the background indexer through
    ``_launch_background_task(...)``. In tests that leaves an orphan Task
    pending in the event loop; closing the loop at teardown then
    intermittently hangs on the macOS kqueue / Windows IOCP selectors
    (caught by pytest-timeout and reddening release-commit CI).

    Closing the coroutine here makes the call a no-op with no scheduled
    Task, so teardown is deterministic on every platform. The return value
    is unused by the caller.
    """
    coro.close()
    return None


@pytest.fixture(autouse=True)
def mock_settings():
    with patch("wet_mcp.server.settings") as mock:
        mock.log_level = "DEBUG"
        mock.wet_cache = True
        mock.get_db_path.return_value = MagicMock()
        mock.embedding_dims = 768
        # For tests, pretend we don't have timeout so tasks run synchronously
        mock.tool_timeout = 0
        yield mock


@pytest.fixture(autouse=True)
def mock_web_cache():
    server._web_cache = MagicMock()
    server._web_cache.get.return_value = None
    # Search dispatcher uses get_with_age (returns (content, age) tuple or
    # None). Default to a miss so non-cache tests still hit the fetch path.
    server._web_cache.get_with_age.return_value = None
    yield server._web_cache
    server._web_cache = None


@pytest.fixture(autouse=True)
def mock_docs_db():
    server._docs_db = MagicMock()
    server._docs_db.get_library.return_value = None
    server._docs_db.get_best_version.return_value = None
    server._docs_db.search.return_value = []
    # No indexing attempt on record -> the launch path treats the version as
    # never attempted, which is what these tests exercise. Left as a MagicMock
    # it would land in the tool payload and break JSON serialization.
    server._docs_db.get_index_state.return_value = None
    yield server._docs_db
    server._docs_db = None


@pytest.mark.asyncio
async def test_warmup_searxng():
    with (
        patch("wet_mcp.setup.run_auto_setup", new_callable=MagicMock) as mock_setup,
        patch(
            "wet_mcp.searxng_runner.ensure_searxng", new_callable=AsyncMock
        ) as mock_ensure,
    ):
        await server._warmup_searxng()
        mock_setup.assert_called_once()
        mock_ensure.assert_awaited_once()


@pytest.mark.asyncio
async def test_warmup_searxng_exception():
    with patch("wet_mcp.setup.run_auto_setup", side_effect=Exception("Test Error")):
        await server._warmup_searxng()


@pytest.mark.asyncio
async def test_lifespan():
    mock_fastmcp = MagicMock()
    with (
        patch("wet_mcp.server._PerSubCache"),
        patch("wet_mcp.server.make_docs_db", return_value=MagicMock()),
        patch(
            "wet_mcp.server.shutdown_crawler", new_callable=AsyncMock
        ) as mock_shutdown,
        patch("wet_mcp.server.stop_searxng") as mock_stop,
    ):
        async with server._lifespan(mock_fastmcp):
            pass

        mock_shutdown.assert_awaited_once()
        mock_stop.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_skips_searxng_warmup_in_uvx_tool_venv():
    """Stdio uvx mode must NOT spawn SearXNG warmup task: search actions are
    gated to return a clear error message instead.  Spawning the Docker
    container during startup wastes resources for a feature the user can
    never use in this transport.
    """
    mock_fastmcp = MagicMock()
    with (
        patch("wet_mcp.server._PerSubCache"),
        patch("wet_mcp.server.make_docs_db", return_value=MagicMock()),
        patch(
            "wet_mcp.server.shutdown_crawler", new_callable=AsyncMock
        ) as mock_shutdown,
        patch("wet_mcp.server.stop_searxng"),
        patch("wet_mcp.server.is_uvx_tool_venv", return_value=True),
        patch("wet_mcp.server._warmup_searxng", new_callable=AsyncMock) as mock_warmup,
    ):
        async with server._lifespan(mock_fastmcp):
            pass

        mock_warmup.assert_not_called()
        mock_shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_runs_searxng_warmup_outside_uvx():
    """Non-uvx transports (Docker / dev .venv) keep the eager warmup."""
    mock_fastmcp = MagicMock()
    with (
        patch("wet_mcp.server._PerSubCache"),
        patch("wet_mcp.server.make_docs_db", return_value=MagicMock()),
        patch("wet_mcp.server.shutdown_crawler", new_callable=AsyncMock),
        patch("wet_mcp.server.stop_searxng"),
        patch("wet_mcp.server.is_uvx_tool_venv", return_value=False),
        patch("wet_mcp.server._warmup_searxng", new_callable=AsyncMock) as mock_warmup,
    ):
        async with server._lifespan(mock_fastmcp):
            pass

        mock_warmup.assert_called_once()


@pytest.mark.asyncio
async def test_init_embedding_backend(monkeypatch):
    monkeypatch.setattr(server, "_embedding_dims", 0)
    cell = MagicMock()
    cell.model = "text-embedding-3-large"
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: True),
        patch("wet_mcp.server.model_cell", lambda t=None, settings=None: cell),
        patch("wet_mcp.embedder.init_backend") as mock_init,
    ):
        mock_backend = MagicMock()
        mock_backend.check_available = AsyncMock(return_value=768)
        mock_init.return_value = mock_backend

        await server._init_embedding_backend()
        assert server._embedding_dims == 768


@pytest.mark.asyncio
async def test_init_reranker_backend():
    cell = MagicMock()
    cell.model = "rerank-model"
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: True),
        patch("wet_mcp.server.model_cell", lambda t=None, settings=None: cell),
        patch("wet_mcp.reranker.init_reranker") as mock_init,
    ):
        mock_reranker = MagicMock()
        # CloudReranker.check_available is async (hull HTTP client).
        mock_reranker.check_available = AsyncMock(return_value=True)
        mock_init.return_value = mock_reranker

        await server._init_reranker_backend()


@pytest.mark.asyncio
async def test_embed():
    with patch("wet_mcp.embedder.resolve_embed_backend_for_request") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.embed_single = AsyncMock(return_value=[0.1, 0.2])
        mock_get_backend.return_value = mock_backend

        res = await server._embed("hello")
        assert res == [0.1, 0.2]


@pytest.mark.asyncio
async def test_embed_batch():
    with patch("wet_mcp.embedder.resolve_embed_backend_for_request") as mock_get_backend:
        mock_backend = MagicMock()
        mock_backend.embed_texts = AsyncMock(return_value=[[0.1, 0.2]])
        mock_get_backend.return_value = mock_backend

        res = await server._embed_batch(["hello"])
        assert res == [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_rerank_results():
    with patch("wet_mcp.reranker.resolve_rerank_backend_for_request") as mock_get_reranker:
        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [(0, 0.9)]
        mock_get_reranker.return_value = mock_reranker

        res = await server._rerank_results(
            "query", [{"content": "hello"}, {"content": "world"}], 1
        )
        assert res == [{"content": "hello", "score": 0.9}]


@pytest.mark.asyncio
async def test_search_tool_search():
    with patch(
        "wet_mcp.server._run_configured_search",
        new_callable=AsyncMock,
        return_value=(
            '{"results": [{"url": "https://e", "title": "T", "snippet": "search_result"}], '
            '"total": 1, "query": "test"}'
        ),
    ):
        res = await server.search("search", query="test")
        assert "search_result" in text(res)


@pytest.mark.asyncio
async def test_search_tool_research():
    with patch("wet_mcp.server._do_research", new_callable=AsyncMock) as mock_research:
        mock_research.return_value = "research_result"
        res = await server.search("research", query="test")
        assert "research_result" in text(res)


@pytest.mark.asyncio
async def test_search_tool_docs():
    with patch("wet_mcp.server._do_docs_search", new_callable=AsyncMock) as mock_docs:
        mock_docs.return_value = "docs_result"
        res = await server.search("docs", query="test", library="test")
        assert "docs_result" in text(res)


@pytest.mark.asyncio
async def test_search_tool_invalid():
    res = await server.search("invalid")
    assert "Unknown action" in text(res)


@pytest.mark.asyncio
async def test_extract_tool_extract():
    with patch("wet_mcp.server._extract", new_callable=AsyncMock) as mock_ext:
        mock_ext.return_value = "ext_result"
        res = await server.extract("extract", urls=["http://test"])
        assert "ext_result" in text(res)


@pytest.mark.asyncio
async def test_extract_tool_crawl():
    with patch("wet_mcp.server._crawl", new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = "crawl_result"
        res = await server.extract("crawl", urls=["http://test"])
        assert "crawl_result" in text(res)


@pytest.mark.asyncio
async def test_extract_tool_map():
    with patch("wet_mcp.server._sitemap", new_callable=AsyncMock) as mock_map:
        mock_map.return_value = "map_result"
        res = await server.extract("map", urls=["http://test"])
        assert "map_result" in text(res)


@pytest.mark.asyncio
async def test_media_tool():
    # list_media is imported in server.py at top level
    with (
        patch("wet_mcp.server.list_media", new_callable=AsyncMock) as mock_list,
        patch(
            "wet_mcp.sources.crawler.download_media", new_callable=AsyncMock
        ) as mock_down,
        patch("wet_mcp.llm.analyze_media", new_callable=AsyncMock) as mock_analyze,
    ):
        mock_list.return_value = "list_result"
        res = await server.media("list", url="http://test")
        assert "list_result" in text(res)

        mock_down.return_value = "down_result"
        res = await server.media("download", media_urls=["http://test"])
        assert "down_result" in text(res)

        # Phase 3 Task 5 BREAKING: analyze removed in v2.0.0 -- routes
        # through unknown-action with migration hint, never invokes LLM.
        mock_analyze.return_value = "analyze_result"
        res = await server.media("analyze", url="http://test")
        assert "Unknown action 'analyze'" in text(res)
        assert "removed in wet v2.0.0" in text(res)
        mock_analyze.assert_not_called()


@pytest.mark.asyncio
async def test_help_tool():
    with patch("wet_mcp.server.files") as mock_files:
        mock_path = MagicMock()
        mock_path.read_text.return_value = "help_text"
        mock_files.return_value.joinpath.return_value = mock_path

        res = await server.help("search")
        assert res == "help_text"


@pytest.mark.asyncio
async def test_config_tool():
    res = await server.config("status")
    assert "settings" in payload(res)

    res = await server.config("set", "tool_timeout", "20")
    assert "updated" in payload(res)["status"]


@pytest.mark.asyncio
async def test_do_research():
    with (
        patch("wet_mcp.server.ensure_searxng", new_callable=AsyncMock) as mock_ensure,
        patch(
            "wet_mcp.sources.search_backends.run_search_chain", new_callable=AsyncMock
        ) as mock_search,
    ):
        mock_ensure.return_value = "url"
        mock_search.return_value = json.dumps({"results": [{"url": "arxiv.org"}]})
        res = await server._do_research("test")
        assert "arxiv" in res


@pytest.mark.asyncio
async def test_fetch_and_chunk_docs():
    with patch(
        "wet_mcp.sources.docs.try_llms_txt", new_callable=AsyncMock
    ) as mock_llms:
        mock_llms.return_value = "content"
        with patch("wet_mcp.sources.docs.chunk_llms_txt") as mock_chunk:
            mock_chunk.return_value = [{"content": "c"}] * 20
            chunks, pages = await server._fetch_and_chunk_docs("test")
            assert pages == 1
            assert len(chunks) == 20


@pytest.mark.asyncio
async def test_do_docs_search_cached():
    server._docs_db.get_library.return_value = {"id": 1, "discovery_version": 999}
    server._docs_db.get_best_version.return_value = {
        "id": 1,
        "chunk_count": 10,
        "version": "latest",
    }
    server._docs_db.search.return_value = [{"content": "res"}]

    with (
        patch("wet_mcp.server._embed", new_callable=AsyncMock) as mock_embed,
        patch("wet_mcp.server._rerank_results", new_callable=AsyncMock) as mock_rerank,
    ):
        mock_embed.return_value = [0.1]
        mock_rerank.return_value = [{"content": "res"}]

        res = await server._do_docs_search("test", "test")
        assert "cached_index" in payload(res)["source"]


@pytest.mark.asyncio
async def test_do_docs_search_new():
    server._docs_db.get_library.return_value = None

    with (
        patch(
            "wet_mcp.server._discover_docs_url",
            new_callable=AsyncMock,
            return_value=("http://docs", "http://repo", "npm", "desc"),
        ),
        patch(
            "wet_mcp.server._background_index_and_search",
            new_callable=AsyncMock,
        ),
        # Patch the launcher so the fire-and-forget background indexer is
        # never scheduled as an orphan Task that survives into event-loop
        # teardown (closing the loop with a pending task hangs on the
        # Windows IOCP / macOS kqueue selectors -> pytest-timeout kill).
        patch("wet_mcp.server._launch_background_task", _close_and_dummy_task),
        # Mock the immediate fallback so the test makes no real network IO
        # (the un-mocked searxng_search hit httpx against a junk URL and
        # could hang on a slow/blocked CI runner).
        patch(
            "wet_mcp.server._do_immediate_fallback_search",
            new_callable=AsyncMock,
            return_value={"results": []},
        ),
        patch("wet_mcp.server.ensure_searxng", new_callable=AsyncMock),
    ):
        res = await server._do_docs_search("newlib", "query")
        data = payload(res)
        assert data["status"] == "indexing_in_progress"
        assert data["library"] == "newlib"


def _force_local_searxng_startup(monkeypatch):
    monkeypatch.setattr(
        server.search_backends, "chain_backend_names", lambda: ["searxng"]
    )


@pytest.mark.asyncio
async def test_do_research_timeout(monkeypatch):
    _force_local_searxng_startup(monkeypatch)
    with patch(
        "wet_mcp.server.ensure_searxng",
        new_callable=AsyncMock,
        side_effect=TimeoutError,
    ):
        res = await server._do_research("test")
        assert "timed out" in res


@pytest.mark.asyncio
async def test_do_research_exception(monkeypatch):
    _force_local_searxng_startup(monkeypatch)
    with patch(
        "wet_mcp.server.ensure_searxng",
        new_callable=AsyncMock,
        side_effect=Exception("Test error"),
    ):
        res = await server._do_research("test")
        assert "startup failed" in res


@pytest.mark.asyncio
async def test_do_research_json_decode_error():
    with (
        patch("wet_mcp.server.ensure_searxng", new_callable=AsyncMock) as mock_ensure,
        patch(
            "wet_mcp.sources.search_backends.run_search_chain", new_callable=AsyncMock
        ) as mock_search,
    ):
        mock_ensure.return_value = "url"
        mock_search.return_value = "invalid json"
        res = await server._do_research("test")
        assert res == "invalid json"


@pytest.mark.asyncio
async def test_do_research_source_types():
    with (
        patch("wet_mcp.server.ensure_searxng", new_callable=AsyncMock) as mock_ensure,
        patch(
            "wet_mcp.sources.search_backends.run_search_chain", new_callable=AsyncMock
        ) as mock_search,
    ):
        mock_ensure.return_value = "url"
        mock_search.return_value = json.dumps(
            {
                "results": [
                    {"url": "scholar.google.com"},
                    {"url": "semanticscholar.org"},
                    {"url": "pubmed.ncbi.nlm.nih.gov"},
                    {"url": "doi.org/10.123"},
                    {"url": "other.org"},
                ]
            }
        )
        res = await server._do_research("test")
        data = json.loads(res)
        types = [r["source_type"] for r in data["results"]]
        assert "google_scholar" in types
        assert "semantic_scholar" in types
        assert "pubmed" in types
        assert "doi" in types
        assert "academic" in types


@pytest.mark.asyncio
async def test_fetch_and_chunk_docs_github_raw():
    with (
        patch("wet_mcp.sources.docs.try_llms_txt", new_callable=AsyncMock) as mock_llms,
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs", new_callable=AsyncMock
        ) as mock_gh,
        patch("wet_mcp.sources.docs.chunk_markdown") as mock_chunk,
    ):
        mock_llms.return_value = None
        mock_gh.return_value = [{"content": "c", "title": "t", "url": "u"}]
        mock_chunk.return_value = [{"content": f"c{i}"} for i in range(30)]
        chunks, pages = await server._fetch_and_chunk_docs("docs_url", "repo_url")
        assert pages == 1
        assert len(chunks) == 30
        # Title injection check
        assert chunks[0]["title"] == "t"


@pytest.mark.asyncio
async def test_fetch_and_chunk_docs_crawl_fallback_to_gh():
    with (
        patch("wet_mcp.sources.docs.try_llms_txt", new_callable=AsyncMock) as mock_llms,
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs", new_callable=AsyncMock
        ) as mock_gh,
        patch("wet_mcp.sources.docs.chunk_markdown") as mock_chunk,
        patch(
            "wet_mcp.sources.docs.fetch_docs_pages", new_callable=AsyncMock
        ) as mock_fetch,
    ):
        mock_llms.return_value = None
        mock_gh.return_value = [{"content": "c"}]
        mock_chunk.side_effect = [
            [{"content": "gh_chunk"}],
            [],
        ]  # 1 for gh, 0 for crawl
        mock_fetch.return_value = []
        chunks, pages = await server._fetch_and_chunk_docs("docs_url")
        assert pages == 1
        assert len(chunks) == 1
        assert chunks[0]["content"] == "gh_chunk"


@pytest.mark.asyncio
async def test_do_docs_search_db_not_init():
    with patch("wet_mcp.server._docs_db", None):
        res = await server._do_docs_search("test", "test")
        assert "Docs database not initialized" in text(res)


@pytest.mark.asyncio
async def test_do_docs_search_force_reindex():
    from wet_mcp.sources.docs import DISCOVERY_VERSION

    server._docs_db.get_library.return_value = {
        "id": 1,
        "discovery_version": DISCOVERY_VERSION - 1,
    }
    server._docs_db.get_best_version.return_value = None

    with (
        patch(
            "wet_mcp.server._discover_docs_url",
            new_callable=AsyncMock,
            return_value=("http://docs", "", "", ""),
        ),
        patch("wet_mcp.server._background_index_and_search", new_callable=AsyncMock),
        # See test_do_docs_search_new: prevent orphan background Task and
        # mock the immediate fallback so the test is fully hermetic.
        patch("wet_mcp.server._launch_background_task", _close_and_dummy_task),
        patch(
            "wet_mcp.server._do_immediate_fallback_search",
            new_callable=AsyncMock,
            return_value={"results": []},
        ),
        patch("wet_mcp.server.ensure_searxng", new_callable=AsyncMock),
    ):
        res = await server._do_docs_search("test", "test")
        assert "indexing_in_progress" in text(res)


@pytest.mark.asyncio
async def test_do_docs_search_discovery_timeout():
    server._docs_db.get_library.return_value = None
    with patch("wet_mcp.server.asyncio.wait_for", side_effect=TimeoutError):
        res = await server._do_docs_search("test", "test")
        assert "Could not find documentation URL" in text(res)


@pytest.mark.asyncio
@_skip_win_iocp
async def test_do_docs_search_no_docs_but_repo():
    server._docs_db.get_library.return_value = None
    with (
        patch(
            "wet_mcp.server._discover_docs_url",
            new_callable=AsyncMock,
            return_value=(
                "http://github.com/test",
                "http://github.com/test",
                "",
                "",
            ),
        ),
        patch("wet_mcp.server._background_index_and_search", new_callable=AsyncMock),
        patch("wet_mcp.server.ensure_searxng", new_callable=AsyncMock),
    ):
        res = await server._do_docs_search("test", "test")
        assert "indexing_in_progress" in text(res)


@pytest.mark.asyncio
@_skip_win_iocp
async def test_do_docs_search_fallback_searxng():
    server._docs_db.get_library.return_value = None
    with (
        patch(
            "wet_mcp.sources.docs.discover_library", new_callable=AsyncMock
        ) as mock_discover,
        patch("wet_mcp.server.ensure_searxng", new_callable=AsyncMock) as mock_ensure,
        patch(
            "wet_mcp.sources.search_backends.run_search_chain", new_callable=AsyncMock
        ) as mock_search,
        patch("wet_mcp.server._background_index_and_search", new_callable=AsyncMock),
    ):
        mock_discover.return_value = None
        mock_ensure.return_value = "url"
        mock_search.return_value = json.dumps({"results": [{"url": "http://docs.alt"}]})

        res = await server._do_docs_search("test", "test")
        assert "indexing_in_progress" in text(res)


@pytest.mark.asyncio
@_skip_win_iocp
async def test_do_docs_search_fetch_timeout():
    server._docs_db.get_library.return_value = None
    with (
        patch(
            "wet_mcp.sources.docs.discover_library", new_callable=AsyncMock
        ) as mock_discover,
        patch("wet_mcp.server._background_index_and_search", new_callable=AsyncMock),
    ):
        mock_discover.return_value = {"homepage": "http://docs"}

        res = await server._do_docs_search("test", "test")
        assert "indexing_in_progress" in text(res)


@pytest.mark.asyncio
async def test_with_timeout_success():
    with patch("wet_mcp.server.settings") as mock_settings:
        mock_settings.tool_timeout = 1

        async def dummy_coro():
            return "success"

        res = await server._with_timeout(dummy_coro(), "test")
        assert res == "success"


@pytest.mark.asyncio
async def test_with_timeout_expired():
    with patch("wet_mcp.server.settings") as mock_settings:
        mock_settings.tool_timeout = 0.1

        async def slow_coro():
            await asyncio.sleep(0.5)
            return "too slow"

        res = await server._with_timeout(slow_coro(), "test")
        assert "timed out" in res


def test_main():
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
# Config tool edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_cache_clear(mock_web_cache):
    """Test cache_clear action clears the web cache."""
    res = await server.config("cache_clear")
    data = payload(res)
    assert data["status"] == "cache cleared"
    mock_web_cache.clear.assert_called_once()


@pytest.mark.asyncio
async def test_config_cache_clear_disabled():
    """Test cache_clear when cache is None."""
    server._web_cache = None
    res = await server.config("cache_clear")
    data = payload(res)
    assert "error" in data
    assert "not enabled" in data["error"]


@pytest.mark.asyncio
async def test_config_docs_reindex(mock_docs_db):
    """Test docs_reindex action clears chunks for a known library."""
    mock_docs_db.get_library.return_value = {"id": 1, "discovery_version": 1}
    mock_docs_db.get_best_version.return_value = {"id": 10, "chunk_count": 5}

    res = await server.config("docs_reindex", key="react")
    data = payload(res)
    assert data["status"] == "cleared"
    assert data["library"] == "react"
    mock_docs_db.clear_version_chunks.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_config_docs_reindex_not_found(mock_docs_db):
    """Test docs_reindex with library not in index."""
    mock_docs_db.get_library.return_value = None

    res = await server.config("docs_reindex", key="unknown-lib")
    data = payload(res)
    assert "error" in data
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_config_set_invalid_key():
    """Test setting an invalid config key."""
    res = await server.config("set", key="nonexistent_key", value="123")
    data = payload(res)
    assert "error" in data
    assert "Invalid key" in data["error"]
    assert "valid_keys" in data


@pytest.mark.asyncio
async def test_config_set_missing_value():
    """Test set action without value."""
    res = await server.config("set", key="log_level")
    data = payload(res)
    assert "error" in data
    assert "key and value are required" in data["error"]


@pytest.mark.asyncio
async def test_config_unknown_action():
    """Test calling config with an invalid action."""
    res = await server.config("foobar")
    data = payload(res)
    assert "error" in data
    assert "Unknown action" in data["error"]
    assert "valid_actions" in data
    assert "models" not in data["valid_actions"]


@pytest.mark.asyncio
async def test_config_models_action_removed():
    """The 'models' catalog-listing action no longer exists."""
    res = await server.config("models")
    data = payload(res)
    assert "Unknown action 'models'" in data["error"]
    assert "models" not in data["valid_actions"]


@pytest.mark.asyncio
async def test_config_set_log_level():
    """Test changing log level via config set."""
    with patch("wet_mcp.server.logger") as mock_logger:
        res = await server.config("set", key="log_level", value="warning")
        data = payload(res)
        assert data["status"] == "updated"
        assert data["key"] == "log_level"
        mock_logger.remove.assert_called_once()
        mock_logger.add.assert_called_once()


@pytest.mark.asyncio
async def test_config_set_wet_cache(mock_settings):
    """Test toggling cache via config set."""
    res = await server.config("set", key="wet_cache", value="false")
    data = payload(res)
    assert data["status"] == "updated"
    assert data["key"] == "wet_cache"


@pytest.mark.asyncio
async def test_config_set_rejects_sync_enabled(mock_settings):
    """De-host: sync knobs are gone; set rejects them with valid keys."""
    res = await server.config("set", key="sync_enabled", value="true")
    data = payload(res)
    assert "error" in data
    assert data["valid_keys"] == [
        "log_level",
        "tool_timeout",
        "wet_cache",
        "wet_search_budget",
    ]


# ---------------------------------------------------------------------------
# Help tool edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_help_tool_not_found():
    """Test help with a non-existent tool name."""
    with patch("wet_mcp.server.files") as mock_files:
        mock_files.return_value.joinpath.return_value.read_text.side_effect = (
            FileNotFoundError("not found")
        )
        res = await server.help("nonexistent_tool")
        assert "Error: Invalid tool_name 'nonexistent_tool'" in res
        assert "nonexistent_tool" in res


@pytest.mark.asyncio
async def test_help_tool_exception():
    """Test help when file read raises a generic exception."""
    with patch("wet_mcp.server.files") as mock_files:
        mock_files.return_value.joinpath.return_value.read_text.side_effect = (
            RuntimeError("disk failure")
        )
        res = await server.help("search")
        assert "Error loading documentation" in res
        assert "disk failure" in res


@pytest.mark.asyncio
async def test_help_tool_extract():
    """Test help for 'extract' tool."""
    with patch("wet_mcp.server.files") as mock_files:
        mock_path = MagicMock()
        mock_path.read_text.return_value = "# Extract Help\nExtract content."
        mock_files.return_value.joinpath.return_value = mock_path
        res = await server.help("extract")
        assert res == "# Extract Help\nExtract content."


@pytest.mark.asyncio
async def test_help_tool_media():
    """Test help for 'media' tool."""
    with patch("wet_mcp.server.files") as mock_files:
        mock_path = MagicMock()
        mock_path.read_text.return_value = "# Media Help\nMedia discovery."
        mock_files.return_value.joinpath.return_value = mock_path
        res = await server.help("media")
        assert res == "# Media Help\nMedia discovery."


@pytest.mark.asyncio
async def test_help_tool_config():
    """Test help for 'config' tool."""
    with patch("wet_mcp.server.files") as mock_files:
        mock_path = MagicMock()
        mock_path.read_text.return_value = "# Config Help\nServer config."
        mock_files.return_value.joinpath.return_value = mock_path
        res = await server.help("config")
        assert res == "# Config Help\nServer config."


# ---------------------------------------------------------------------------
# Lifespan startup/shutdown edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_skip_win_iocp
async def test_lifespan_startup_no_github_token():
    """Test lifespan warns when GITHUB_TOKEN is not set (line 106)."""
    # Preserve home-directory env vars so Path.home() works on Windows
    _home_vars = {
        k: v
        for k, v in os.environ.items()
        if k in ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "SYSTEMROOT")
    }
    mock_fastmcp = MagicMock()
    with (
        patch("wet_mcp.server._PerSubCache"),
        patch("wet_mcp.server.make_docs_db", return_value=MagicMock()),
        patch("wet_mcp.server.shutdown_crawler", new_callable=AsyncMock),
        patch("wet_mcp.server.stop_searxng"),
        patch.dict("os.environ", _home_vars, clear=True),
    ):
        async with server._lifespan(mock_fastmcp):
            pass


@pytest.mark.asyncio
@patch("wet_mcp.server._warmup_searxng", new_callable=AsyncMock)
async def test_lifespan_startup_backend_init_error(mock_warmup):
    """Test lifespan handles backend init failure gracefully (lines 134-136)."""
    mock_fastmcp = MagicMock()
    with (
        patch("wet_mcp.server._PerSubCache"),
        patch("wet_mcp.server.make_docs_db", return_value=MagicMock()),
        patch("wet_mcp.server.shutdown_crawler", new_callable=AsyncMock),
        patch("wet_mcp.server.stop_searxng"),
        patch("wet_mcp.server._warmup_searxng", new_callable=AsyncMock),
        patch(
            "wet_mcp.server._init_embedding_backend",
            new_callable=AsyncMock,
            side_effect=Exception("backend init error"),
        ),
    ):
        async with server._lifespan(mock_fastmcp):
            # Allow background tasks to run
            await asyncio.sleep(0.1)


# ---------------------------------------------------------------------------
# _init_embedding_backend edge cases (cell-based: the [models.embed] cell
# decides cloud; otherwise local-if-available; no chain, no fallbacks)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_embedding_backend_cloud_cell():
    """A configured cell inits cloud with the cell-owned model id."""
    cell = MagicMock()
    cell.model = "text-embedding-3-large"
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: True),
        patch("wet_mcp.server.model_cell", lambda t=None, settings=None: cell),
        patch("wet_mcp.embedder.init_backend") as mock_init,
    ):
        mock_backend = MagicMock()
        mock_backend.check_available = AsyncMock(return_value=1536)
        mock_init.return_value = mock_backend

        await server._init_embedding_backend()
        mock_init.assert_called_once_with("cloud", "text-embedding-3-large")


@pytest.mark.asyncio
async def test_init_embedding_backend_cloud_cell_fail_no_local_fallback():
    """A broken host key surfaces loudly: init fails once, no local fallback."""
    cell = MagicMock()
    cell.model = "bad-model"
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: True),
        patch("wet_mcp.server.model_cell", lambda t=None, settings=None: cell),
        patch("wet_mcp.embedder.init_backend") as mock_init,
    ):
        mock_init.side_effect = Exception("model not available")

        await server._init_embedding_backend()
        assert mock_init.call_count == 1


@pytest.mark.asyncio
async def test_init_embedding_backend_local_fail():
    """No cell + local available: a failing local init is handled (no raise)."""
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: False),
        patch("wet_mcp.server.settings") as ms,
        patch("wet_mcp.embedder.init_backend") as mock_init,
    ):
        ms.local_embed_available.return_value = True
        ms.resolve_local_embedding_model.return_value = "local-model"
        ms.local_embedding_model = ""
        mock_init.side_effect = Exception("local init failed")

        await server._init_embedding_backend()


@pytest.mark.asyncio
async def test_init_embedding_backend_local_not_available():
    """No cell + local check returns 0 dims: the backend is cleared."""
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: False),
        patch("wet_mcp.server.settings") as ms,
        patch("wet_mcp.embedder.init_backend") as mock_init,
    ):
        ms.local_embed_available.return_value = True
        ms.resolve_local_embedding_model.return_value = "local-model"
        ms.local_embedding_model = ""

        mock_backend = MagicMock()
        mock_backend.check_available = AsyncMock(return_value=0)
        mock_init.return_value = mock_backend

        await server._init_embedding_backend()

        from wet_mcp import embedder

        assert embedder.get_backend() is None


# ---------------------------------------------------------------------------
# _init_reranker_backend edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_reranker_backend_disabled():
    """RERANK_ENABLED=false disables reranking entirely."""
    with patch("wet_mcp.server.settings") as ms:
        ms.rerank_enabled = False

        await server._init_reranker_backend()


@pytest.mark.asyncio
async def test_init_reranker_backend_cloud_fail_no_local_fallback():
    """A configured rerank cell that fails inits once, no local fallback."""
    cell = MagicMock()
    cell.model = "rerank-model"
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: True),
        patch("wet_mcp.server.model_cell", lambda t=None, settings=None: cell),
        patch("wet_mcp.reranker.init_reranker") as mock_init,
    ):
        mock_init.side_effect = Exception("cloud not available")

        await server._init_reranker_backend()
        assert mock_init.call_count == 1


@pytest.mark.asyncio
async def test_init_reranker_backend_local_fail():
    """No cell + local available: a failing local init is handled (no raise)."""
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: False),
        patch("wet_mcp.server.settings") as ms,
        patch("wet_mcp.reranker.init_reranker") as mock_init,
    ):
        ms.local_rerank_available.return_value = True
        ms.resolve_local_rerank_model.return_value = "local-rerank"
        ms.local_rerank_model = ""
        mock_init.side_effect = Exception("local rerank init failed")

        await server._init_reranker_backend()


@pytest.mark.asyncio
async def test_init_reranker_backend_local_not_available():
    """No cell + local check false: the backend is cleared."""
    with (
        patch("wet_mcp.runtime.cell_configured", lambda t, settings=None: False),
        patch("wet_mcp.server.settings") as ms,
        patch("wet_mcp.reranker.init_reranker") as mock_init,
    ):
        ms.local_rerank_available.return_value = True
        ms.resolve_local_rerank_model.return_value = "local-rerank"
        ms.local_rerank_model = ""

        mock_reranker = MagicMock()
        mock_reranker.check_available = MagicMock(return_value=False)
        mock_init.return_value = mock_reranker

        await server._init_reranker_backend()

        from wet_mcp import reranker as reranker_mod

        assert reranker_mod.get_reranker() is None


# ---------------------------------------------------------------------------
# _embed / _embed_batch / _rerank_results edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_no_backend():
    """Test _embed returns None when no backend (line 325)."""
    with patch(
        "wet_mcp.embedder.resolve_embed_backend_for_request", return_value=None
    ):
        res = await server._embed("hello")
        assert res is None


@pytest.mark.asyncio
async def test_embed_query_mode():
    """Test _embed with is_query=True for the local backend (lines 327-330)."""
    with patch("wet_mcp.embedder.get_backend") as mock_get:
        from wet_mcp.embedder import LocalEmbeddingBackend

        mock_backend = MagicMock(spec=LocalEmbeddingBackend)
        mock_backend.embed_single_query.return_value = [0.5, 0.6]
        mock_get.return_value = mock_backend

        res = await server._embed("hello", is_query=True)
        assert res == [0.5, 0.6]


@pytest.mark.asyncio
async def test_embed_transient_exception_returns_none():
    """A transient embedding error degrades this call to None (keyword-only)."""
    from hull_core.providers.openai_spec import ProviderError

    with patch("wet_mcp.embedder.resolve_embed_backend_for_request") as mock_get:
        mock_backend = MagicMock()
        mock_backend.embed_single.side_effect = ProviderError(
            status=429, detail="rate limit exceeded"
        )
        mock_get.return_value = mock_backend

        res = await server._embed("hello")
        assert res is None


@pytest.mark.asyncio
async def test_embed_permanent_exception_raises():
    """A permanent embedding error is surfaced loudly, not swallowed to None."""
    with patch("wet_mcp.embedder.get_backend") as mock_get:
        mock_backend = MagicMock()
        mock_backend.embed_single.side_effect = Exception("model does not exist")
        mock_get.return_value = mock_backend

        with pytest.raises(Exception, match="does not exist"):
            await server._embed("hello")


@pytest.mark.asyncio
async def test_embed_batch_no_backend():
    """Test _embed_batch returns None when no backend (line 343)."""
    with patch(
        "wet_mcp.embedder.resolve_embed_backend_for_request", return_value=None
    ):
        res = await server._embed_batch(["hello"])
        assert res is None


@pytest.mark.asyncio
async def test_embed_batch_transient_exception_returns_none():
    """A transient batch embedding error degrades this call to None."""
    from hull_core.providers.openai_spec import ProviderError

    with patch("wet_mcp.embedder.resolve_embed_backend_for_request") as mock_get:
        mock_backend = MagicMock()
        mock_backend.embed_texts.side_effect = ProviderError(
            status=429, detail="rate limit exceeded"
        )
        mock_get.return_value = mock_backend

        res = await server._embed_batch(["hello"])
        assert res is None


@pytest.mark.asyncio
async def test_embed_batch_permanent_exception_raises():
    """A permanent batch embedding error is surfaced loudly, not swallowed."""
    with patch("wet_mcp.embedder.get_backend") as mock_get:
        mock_backend = MagicMock()
        mock_backend.embed_texts.side_effect = Exception("model does not exist")
        mock_get.return_value = mock_backend

        with pytest.raises(Exception, match="does not exist"):
            await server._embed_batch(["hello"])


@pytest.mark.asyncio
async def test_rerank_results_exception():
    """Test _rerank_results falls back on exception (lines 377-380)."""
    with patch("wet_mcp.reranker.resolve_rerank_backend_for_request") as mock_get:
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = Exception("rerank error")
        mock_get.return_value = mock_reranker

        results = [{"content": "a"}, {"content": "b"}, {"content": "c"}]
        res = await server._rerank_results("query", results, 2)
        assert len(res) == 2
        assert res == [{"content": "a"}, {"content": "b"}]


# ---------------------------------------------------------------------------
# Search tool cache and error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_tool_cache_hit(mock_web_cache):
    """Test search returns cached result (lines 509-511)."""
    # Search dispatcher consumes get_with_age -> (content, age) | None.
    mock_web_cache.get_with_age.return_value = ("cached_search_result", 0)
    res = await server.search("search", query="test")
    assert "cached_search_result" in text(res)


@pytest.mark.asyncio
async def test_search_tool_searxng_timeout(monkeypatch):
    """Test search handles SearXNG timeout (lines 516-517)."""
    _force_local_searxng_startup(monkeypatch)
    with patch(
        "wet_mcp.server.ensure_searxng",
        new_callable=AsyncMock,
        side_effect=TimeoutError,
    ):
        res = await server.search("search", query="test")
        assert "timed out" in text(res)


@pytest.mark.asyncio
async def test_search_tool_searxng_exception(monkeypatch):
    """Test search handles SearXNG startup exception (lines 518-519)."""
    _force_local_searxng_startup(monkeypatch)
    with patch(
        "wet_mcp.server.ensure_searxng",
        new_callable=AsyncMock,
        side_effect=Exception("docker not found"),
    ):
        res = await server.search("search", query="test")
        assert "startup failed" in text(res)


@pytest.mark.asyncio
async def test_search_tool_research_cache_hit(mock_web_cache):
    """Test research returns cached result (lines 538-540)."""
    mock_web_cache.get.return_value = "cached_research_result"
    res = await server.search("research", query="test")
    assert "cached_research_result" in text(res)


@pytest.mark.asyncio
async def test_search_tool_research_missing_query():
    """Test research missing query (line 535)."""
    res = await server.search("research", query=None)
    assert "Error: query is required" in text(res)


@pytest.mark.asyncio
async def test_search_tool_docs_missing_library():
    """Test docs action missing library (line 551)."""
    res = await server.search("docs", query="test", library=None)
    assert "Error: library is required" in text(res)


@pytest.mark.asyncio
async def test_search_tool_docs_missing_query():
    """Test docs action missing query (line 553)."""
    res = await server.search("docs", library="react", query=None)
    assert "Error: query is required" in text(res)


# ---------------------------------------------------------------------------
# Extract tool cache paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_tool_extract_cache_hit(mock_web_cache):
    """Test extract returns cached result (lines 613-615)."""
    mock_web_cache.get.return_value = "cached_extract_result"
    res = await server.extract("extract", urls=["http://test"])
    assert "cached_extract_result" in text(res)


@pytest.mark.asyncio
async def test_extract_tool_crawl_cache_hit(mock_web_cache):
    """Test crawl returns cached result (lines 634-636)."""
    mock_web_cache.get.return_value = "cached_crawl_result"
    res = await server.extract("crawl", urls=["http://test"])
    assert "cached_crawl_result" in text(res)


@pytest.mark.asyncio
async def test_extract_tool_map_cache_hit(mock_web_cache):
    """Test map returns cached result (lines 661-663)."""
    mock_web_cache.get.return_value = "cached_map_result"
    res = await server.extract("map", urls=["http://test"])
    assert "cached_map_result" in text(res)


# ---------------------------------------------------------------------------
# Media tool edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_media_tool_list_missing_url():
    """Test media list missing url (line 710)."""
    res = await server.media("list", url=None)
    assert "Error: url is required" in text(res)


@pytest.mark.asyncio
async def test_media_tool_download_missing_urls():
    """Test media download missing media_urls (line 718)."""
    res = await server.media("download", media_urls=None)
    assert "Error: media_urls is required" in text(res)


@pytest.mark.asyncio
async def test_media_tool_download_security_check():
    """Test media download output_dir security check (lines 722-730)."""
    with patch("wet_mcp.server.settings") as ms:
        ms.download_dir = "/tmp/wet_downloads"
        ms.tool_timeout = 0
        res = await server.media(
            "download",
            media_urls=["http://test/img.png"],
            output_dir="/etc/passwd",
        )
        assert "Security Alert" in text(res)


@pytest.mark.asyncio
async def test_media_tool_analyze_missing_url():
    """Phase 3 Task 5 BREAKING: analyze removed -- routes to unknown-action
    regardless of url presence."""
    res = await server.media("analyze", url=None)
    assert "Unknown action 'analyze'" in text(res)
    assert "imagine-mcp" in text(res)


@pytest.mark.asyncio
async def test_media_tool_invalid_action():
    """Test media invalid action (lines 751-752)."""
    res = await server.media("invalid")
    assert "Unknown action" in text(res)


# ---------------------------------------------------------------------------
# Config tool edge cases (continued)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_set_rejects_removed_sync_keys(mock_settings):
    """De-host: sync knobs are gone; invalid set keys name the valid ones."""
    res = await server.config("set", key="sync_interval", value="30")
    data = payload(res)
    assert "error" in data
    assert data["valid_keys"] == ["log_level", "tool_timeout", "wet_cache", "wet_search_budget"]


@pytest.mark.asyncio
async def test_config_docs_reindex_missing_key():
    """Test docs_reindex without key (line 906)."""
    res = await server.config("docs_reindex", key=None)
    data = payload(res)
    assert "error" in data
    assert "required" in data["error"]


@pytest.mark.asyncio
async def test_config_docs_reindex_db_not_init():
    """Test docs_reindex when docs db is not initialized (line 908)."""
    server._docs_db = None
    res = await server.config("docs_reindex", key="react")
    data = payload(res)
    assert "error" in data
    assert "not initialized" in data["error"]


# ---------------------------------------------------------------------------
# _fetch_and_chunk_docs edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_and_chunk_docs_llms_txt_too_few():
    """Test llms.txt fallthrough when too few chunks (line 1037)."""
    with (
        patch("wet_mcp.sources.docs.try_llms_txt", new_callable=AsyncMock) as mock_llms,
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs", new_callable=AsyncMock
        ) as mock_gh,
        patch("wet_mcp.sources.docs.chunk_llms_txt") as mock_chunk_llms,
        patch("wet_mcp.sources.docs.chunk_markdown") as mock_chunk_md,
        patch(
            "wet_mcp.sources.docs.fetch_docs_pages", new_callable=AsyncMock
        ) as mock_fetch,
    ):
        mock_llms.return_value = "small content"
        mock_chunk_llms.return_value = [{"content": f"c{i}"} for i in range(5)]
        mock_gh.return_value = []
        mock_fetch.return_value = [
            {"content": f"page{i}", "url": f"http://docs/p{i}", "title": f"T{i}"}
            for i in range(25)
        ]
        mock_chunk_md.return_value = [{"content": "chunk"}]

        chunks, pages = await server._fetch_and_chunk_docs("http://docs")
        assert pages == 25
        assert len(chunks) == 25


@pytest.mark.asyncio
async def test_fetch_and_chunk_docs_tier2_crawl():
    """Test Tier 2 crawl produces chunks with title injection (lines 1085-1092)."""
    with (
        patch("wet_mcp.sources.docs.try_llms_txt", new_callable=AsyncMock) as mock_llms,
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs", new_callable=AsyncMock
        ) as mock_gh,
        patch("wet_mcp.sources.docs.chunk_markdown") as mock_chunk_md,
        patch(
            "wet_mcp.sources.docs.fetch_docs_pages", new_callable=AsyncMock
        ) as mock_fetch,
    ):
        mock_llms.return_value = None
        mock_gh.return_value = []
        mock_fetch.return_value = [
            {
                "content": "page content",
                "url": "http://docs/page",
                "title": "Page Title",
            }
        ]
        mock_chunk_md.return_value = [{"content": "chunk1"}, {"content": "chunk2"}]

        chunks, pages = await server._fetch_and_chunk_docs("http://docs")
        assert pages == 1
        assert len(chunks) == 2
        # Title injection
        assert chunks[0]["title"] == "Page Title"
        assert chunks[1]["title"] == "Page Title"


@pytest.mark.asyncio
async def test_fetch_and_chunk_docs_readme_fallback():
    """Test Tier 3 README fallback (lines 1109-1121)."""
    with (
        patch("wet_mcp.sources.docs.try_llms_txt", new_callable=AsyncMock) as mock_llms,
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs", new_callable=AsyncMock
        ) as mock_gh,
        patch("wet_mcp.sources.docs.chunk_markdown") as mock_chunk_md,
        patch(
            "wet_mcp.sources.docs.fetch_docs_pages", new_callable=AsyncMock
        ) as mock_fetch,
        patch(
            "wet_mcp.sources.docs._fetch_github_readme", new_callable=AsyncMock
        ) as mock_readme,
    ):
        mock_llms.return_value = None
        mock_gh.return_value = []
        mock_fetch.return_value = []
        mock_chunk_md.return_value = []
        mock_readme.return_value = [{"content": "readme chunk", "title": "README"}]

        chunks, pages = await server._fetch_and_chunk_docs(
            "http://docs", "http://github.com/repo"
        )
        assert pages == 1
        assert len(chunks) == 1
        assert chunks[0]["content"] == "readme chunk"


@pytest.mark.asyncio
async def test_fetch_and_chunk_docs_all_tiers_fail():
    """Test all tiers fail returns empty (line 1120-1121)."""
    with (
        patch("wet_mcp.sources.docs.try_llms_txt", new_callable=AsyncMock) as mock_llms,
        patch(
            "wet_mcp.sources.docs._try_github_raw_docs", new_callable=AsyncMock
        ) as mock_gh,
        patch("wet_mcp.sources.docs.chunk_markdown") as mock_chunk_md,
        patch(
            "wet_mcp.sources.docs.fetch_docs_pages", new_callable=AsyncMock
        ) as mock_fetch,
        patch(
            "wet_mcp.sources.docs._fetch_github_readme", new_callable=AsyncMock
        ) as mock_readme,
    ):
        mock_llms.return_value = None
        mock_gh.return_value = []
        mock_fetch.return_value = []
        mock_chunk_md.return_value = []
        mock_readme.return_value = []

        chunks, pages = await server._fetch_and_chunk_docs("http://docs")
        assert pages == 0
        assert len(chunks) == 0


# ---------------------------------------------------------------------------
# _background_index_and_search edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_skip_win_iocp
async def test_background_index_fetch_timeout():
    """Test background indexing handles fetch timeout (lines 1160-1163)."""
    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            side_effect=Exception("no searxng"),
        ),
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


@pytest.mark.asyncio
async def test_background_index_marks_library_indexed(tmp_path):
    """The background index path must stamp libraries.last_indexed_at.

    Before the seed/index split, ``upsert_library`` stamped that column as a
    side effect of writing metadata, which hid the fact that this path never
    calls ``mark_library_indexed``. Now that only ``mark_library_indexed``
    writes it, a library indexed here would stay NULL forever and read as
    permanently stale (``hooks/SessionStart_check_docs_freshness.sh``).
    """
    from wet_mcp.db import DocsDB

    db = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    lib_id = db.upsert_library(name="testlib", docs_url="http://docs")
    ver_id = db.upsert_version(
        library_id=lib_id, version="latest", docs_url="http://docs"
    )
    before = db.get_library("testlib")
    assert before is not None
    assert before["last_indexed_at"] is None

    chunks = [
        {
            "url": "http://docs",
            "title": "Guide",
            "content": f"chunk {i}",
            "heading_path": "Guide",
            "chunk_index": i,
        }
        for i in range(3)
    ]
    previous_db = server._docs_db
    server._docs_db = db
    try:
        with (
            patch(
                "wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"
            ),
            patch(
                "wet_mcp.server._fetch_and_chunk_docs",
                new_callable=AsyncMock,
                return_value=(chunks, 5),
            ),
            patch(
                "wet_mcp.embedder.resolve_embed_backend_for_request",
                return_value=None,
            ),
        ):
            await server._background_index_and_search(
                library="testlib",
                lib_key="testlib",
                language=None,
                docs_url="http://docs",
                repo_url="",
                query="test",
                version=None,
                lib_id=lib_id,
                ver_id=ver_id,
            )

        after = db.get_library("testlib")
        assert after is not None
        assert after["last_indexed_at"] is not None
        assert db.get_best_version(lib_id, None) is not None
    finally:
        server._docs_db = previous_db
        db.close()


@pytest.mark.asyncio
@_skip_win_iocp
async def test_background_index_with_searxng_fallback():
    """Test background indexing SearXNG fallback (lines 1185-1207)."""
    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
        ) as mock_search,
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock) as mock_embed,
    ):
        # First call returns few chunks, second call returns more
        mock_fetch.side_effect = [
            ([{"content": "c1"}], 1),
            ([{"content": "c1"}, {"content": "c2"}, {"content": "c3"}], 3),
        ]
        mock_search.return_value = json.dumps(
            {"results": [{"url": "http://alt-docs.com/guide"}]}
        )
        mock_embed.return_value = [[0.1], [0.2], [0.3]]

        server._docs_db = MagicMock()

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
        server._docs_db.add_chunks.assert_called_once()
        server._docs_db.mark_version_indexed.assert_called_once()


@pytest.mark.asyncio
@_skip_win_iocp
async def test_background_index_with_language():
    """Test background indexing with language context (line 1168-1169)."""
    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
        ) as mock_search,
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock) as mock_embed,
    ):
        mock_fetch.return_value = ([{"content": "c1"}], 1)
        mock_search.return_value = json.dumps({"results": []})
        mock_embed.return_value = [[0.1]]

        server._docs_db = MagicMock()

        await server._background_index_and_search(
            library="redis",
            lib_key="redis:python",
            language="python",
            docs_url="http://docs",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )


@pytest.mark.asyncio
@_skip_win_iocp
async def test_background_index_embeddings_and_store():
    """Test background indexing generates embeddings and stores (lines 1218-1249)."""
    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch("wet_mcp.embedder.get_backend") as mock_get_backend,
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock) as mock_embed,
    ):
        chunks = [
            {"content": "chunk1", "title": "T1", "heading_path": "H1"},
            {"content": "chunk2", "title": "T2"},
            {"content": "chunk3"},
        ]
        mock_fetch.return_value = (chunks, 3)
        mock_get_backend.return_value = MagicMock()  # backend available
        mock_embed.return_value = [[0.1], [0.2], [0.3]]

        server._docs_db = MagicMock()

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
        server._docs_db.add_chunks.assert_called_once()
        call_args = server._docs_db.add_chunks.call_args
        assert call_args.kwargs["embeddings"] == [[0.1], [0.2], [0.3]]


@pytest.mark.asyncio
@_skip_win_iocp
async def test_background_index_embed_timeout():
    """Test background indexing handles embed timeout (lines 1238-1239)."""
    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch("wet_mcp.embedder.get_backend") as mock_get_backend,
        patch(
            "wet_mcp.server._embed_batch",
            new_callable=AsyncMock,
            side_effect=TimeoutError,
        ),
    ):
        mock_fetch.return_value = ([{"content": "chunk1"}], 1)
        mock_get_backend.return_value = MagicMock()

        server._docs_db = MagicMock()

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
        # Should still store chunks even without embeddings
        server._docs_db.add_chunks.assert_called_once()
        call_args = server._docs_db.add_chunks.call_args
        assert call_args.kwargs["embeddings"] is None


@pytest.mark.asyncio
@_skip_win_iocp
async def test_background_index_exception():
    """Test background indexing handles top-level exception (line 1254)."""
    with patch(
        "wet_mcp.sources.docs._normalize_docs_url",
        side_effect=Exception("unexpected error"),
    ):
        # Should not raise
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


@pytest.mark.asyncio
@_skip_win_iocp
async def test_background_index_no_chunks():
    """Test background indexing logs error when no chunks found."""
    with (
        patch("wet_mcp.sources.docs._normalize_docs_url", return_value="http://docs"),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
            return_value=([], 0),
        ),
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            side_effect=Exception("no searxng"),
        ),
    ):
        server._docs_db = MagicMock()

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
        server._docs_db.add_chunks.assert_not_called()


@pytest.mark.asyncio
@_skip_win_iocp
async def test_background_index_fallback_alt_timeout():
    """Test background indexing SearXNG fallback with alt fetch timeout (lines 1201-1202)."""
    with (
        patch(
            "wet_mcp.sources.docs._normalize_docs_url",
            return_value="http://docs.example.com",
        ),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
        ) as mock_search,
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock) as mock_embed,
    ):
        # First call returns few, alt fetch times out
        mock_fetch.side_effect = [
            ([{"content": "c1"}], 1),
            TimeoutError("alt fetch timeout"),
        ]
        mock_search.return_value = json.dumps(
            {"results": [{"url": "http://alt-docs.com/guide"}]}
        )
        mock_embed.return_value = [[0.1]]

        server._docs_db = MagicMock()

        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://docs.example.com",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )
        # Should still use original chunks
        server._docs_db.add_chunks.assert_called_once()


@pytest.mark.asyncio
@_skip_win_iocp
async def test_background_index_fallback_same_netloc():
    """Test background indexing skips same netloc in fallback (line 1194)."""
    with (
        patch(
            "wet_mcp.sources.docs._normalize_docs_url",
            return_value="http://docs.example.com",
        ),
        patch(
            "wet_mcp.server._fetch_and_chunk_docs",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "wet_mcp.server.ensure_searxng",
            new_callable=AsyncMock,
            return_value="http://searxng",
        ),
        patch(
            "wet_mcp.sources.search_backends.run_search_chain",
            new_callable=AsyncMock,
        ) as mock_search,
        patch("wet_mcp.server._embed_batch", new_callable=AsyncMock) as mock_embed,
    ):
        mock_fetch.return_value = ([{"content": "c1"}], 1)
        mock_search.return_value = json.dumps(
            {
                "results": [
                    {"url": "http://docs.example.com/other"},  # same netloc, skip
                    {"url": ""},  # empty url, skip
                ]
            }
        )
        mock_embed.return_value = [[0.1]]

        server._docs_db = MagicMock()

        await server._background_index_and_search(
            library="testlib",
            lib_key="testlib",
            language=None,
            docs_url="http://docs.example.com",
            repo_url="",
            query="test",
            version=None,
            lib_id="1",
            ver_id="1",
        )


# ---------------------------------------------------------------------------
# _search_cached_index edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_cached_index_no_results():
    """Test _search_cached_index returns None when no results (line 1304)."""
    server._docs_db = MagicMock()
    server._docs_db.get_library.return_value = {"id": 1, "discovery_version": 999}
    server._docs_db.get_best_version.return_value = {
        "id": 1,
        "chunk_count": 10,
        "version": "latest",
    }
    server._docs_db.search.return_value = []

    with patch("wet_mcp.server._embed", new_callable=AsyncMock, return_value=[0.1]):
        res = await server._search_cached_index("testlib", "query", None, 10)
        assert res is None


@pytest.mark.asyncio
async def test_search_cached_index_no_version():
    """Test _search_cached_index returns None when no version (line 1289)."""
    server._docs_db = MagicMock()
    server._docs_db.get_library.return_value = {"id": 1, "discovery_version": 999}
    server._docs_db.get_best_version.return_value = None

    res = await server._search_cached_index("testlib", "query", None, 10)
    assert res is None


@pytest.mark.asyncio
async def test_search_cached_index_zero_chunks():
    """Test _search_cached_index returns None when chunk_count is 0."""
    server._docs_db = MagicMock()
    server._docs_db.get_library.return_value = {"id": 1, "discovery_version": 999}
    server._docs_db.get_best_version.return_value = {
        "id": 1,
        "chunk_count": 0,
        "version": "latest",
    }

    res = await server._search_cached_index("testlib", "query", None, 10)
    assert res is None


# ---------------------------------------------------------------------------
# _discover_docs_url edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_docs_url_searxng_timeout():
    """Test _discover_docs_url SearXNG fallback timeout (lines 1388-1389)."""
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
        docs_url, repo_url, registry, description = await server._discover_docs_url(
            "testlib", None
        )
        assert docs_url == ""


@pytest.mark.asyncio
async def test_discover_docs_url_searxng_json_error():
    """Test _discover_docs_url SearXNG JSON decode error (lines 1390-1391)."""
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
            return_value="invalid json",
        ),
    ):
        docs_url, repo_url, registry, description = await server._discover_docs_url(
            "testlib", None
        )
        assert docs_url == ""


@pytest.mark.asyncio
async def test_discover_docs_url_with_language():
    """Test _discover_docs_url with language context."""
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
        ) as mock_search,
    ):
        mock_search.return_value = json.dumps(
            {"results": [{"url": "http://redis.io/docs/python"}]}
        )
        docs_url, _, _, _ = await server._discover_docs_url("redis", "python")
        assert docs_url == "http://redis.io/docs/python"
        # Verify language was included in search query
        call_args = mock_search.call_args
        assert "python" in call_args.kwargs["query"]


@pytest.mark.asyncio
async def test_discover_docs_url_discovery_timeout():
    """Test _discover_docs_url discovery timeout."""
    with (
        patch(
            "wet_mcp.sources.docs.discover_library",
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
        docs_url, _, _, _ = await server._discover_docs_url("testlib", None)
        assert docs_url == ""


# ---------------------------------------------------------------------------
# _do_docs_search fallback exception path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_skip_win_iocp
async def test_do_docs_search_fallback_exception():
    """Test _do_docs_search handles fallback search exception (lines 1493-1494)."""
    server._docs_db = MagicMock()
    server._docs_db.get_library.return_value = None
    server._docs_db.upsert_library.return_value = "1"
    server._docs_db.upsert_version.return_value = "1"

    with (
        patch(
            "wet_mcp.server._search_cached_index",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "wet_mcp.server._discover_docs_url",
            new_callable=AsyncMock,
            return_value=("http://docs", "", "", ""),
        ),
        patch(
            "wet_mcp.server._background_index_and_search",
            new_callable=AsyncMock,
        ),
        patch(
            "wet_mcp.server._do_immediate_fallback_search",
            new_callable=AsyncMock,
            return_value={"results": []},
        ),
    ):
        res = await server._do_docs_search("testlib", "query")
        data = payload(res)
        assert data["status"] == "indexing_in_progress"
        assert data["temporary_results"] == []


# ---------------------------------------------------------------------------
# _with_timeout edge case: task raises exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_timeout_task_exception():
    """Test _with_timeout propagates task exception when done within timeout."""
    with patch("wet_mcp.server.settings") as mock_settings:
        mock_settings.tool_timeout = 5

        async def failing_coro():
            raise ValueError("task failed")

        with pytest.raises(ValueError, match="task failed"):
            await server._with_timeout(failing_coro(), "test")
