"""Tests for src/wet_mcp/server.py."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from structured import payload, text

from wet_mcp.server import (
    _maybe_register_custom_embed,
    _maybe_register_custom_rerank,
    extract,
    search,
)


@pytest.fixture(autouse=True)
def _no_real_searxng_spawn():
    """The search action's chain path reaches ``_ensure_searxng_healthy`` ->
    ``ensure_searxng()`` — a real SearXNG subprocess spawn that hangs a Windows CI
    runner blocking on the child's stdout. Stub the health-check so no test_server
    test ever starts a real SearXNG; tests asserting on these targets re-patch
    them and their patch overrides this default (same pattern as the conftest
    backend/crawler stubs)."""
    with patch(
        "wet_mcp.sources.searxng._ensure_searxng_healthy",
        new_callable=AsyncMock,
        side_effect=lambda url: url,
    ):
        yield


def test_maybe_register_custom_embed_no_optin_noop(monkeypatch):
    """No registration when LOCAL_EMBEDDING_MODEL is unset (default local)."""
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "local_embedding_model", "")
    _maybe_register_custom_embed("local-model")


def test_maybe_register_custom_embed_builtin_noop(monkeypatch):
    """Any id in the live registry is left untouched."""
    import fastretrieval

    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "local_embedding_model", "acme/tiny-e5")
    monkeypatch.setattr(
        fastretrieval.TextEmbedding,
        "list_supported_models",
        classmethod(lambda cls: [{"model": "acme/tiny-e5"}]),
    )
    called = []
    monkeypatch.setattr(
        fastretrieval.CustomModelSpec,
        "register",
        lambda self: called.append(self),
    )
    _maybe_register_custom_embed("acme/tiny-e5")
    assert called == []


def test_maybe_register_custom_embed_registers_public_spec(monkeypatch):
    """A BYO id with explicit metadata registers through the public spec API."""
    import fastretrieval

    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "local_embedding_model", "Org/custom-embed")
    monkeypatch.setattr(settings, "local_embedding_dim", 768)
    monkeypatch.setattr(settings, "local_embedding_pooling", "CLS")

    captured = {}

    monkeypatch.setattr(
        fastretrieval.TextEmbedding,
        "list_supported_models",
        classmethod(lambda cls: []),
    )
    monkeypatch.setattr(
        fastretrieval.CustomModelSpec,
        "register",
        lambda self: captured.update(
            model=self.model_id,
            pooling=self.pooling,
            normalization=self.normalization,
        ),
    )

    _maybe_register_custom_embed("Org/custom-embed")

    assert captured["model"] == "Org/custom-embed"
    assert captured["pooling"] == "CLS"
    assert captured["normalization"] is True


def test_maybe_register_custom_embed_missing_dim(monkeypatch):
    """A BYO id without LOCAL_EMBEDDING_DIM skips registration (no call)."""
    import fastretrieval

    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "local_embedding_model", "Org/custom-embed")
    monkeypatch.setattr(settings, "local_embedding_dim", 0)
    monkeypatch.setattr(
        fastretrieval.TextEmbedding,
        "list_supported_models",
        classmethod(lambda cls: []),
    )
    called = []
    monkeypatch.setattr(
        fastretrieval.CustomModelSpec,
        "register",
        lambda self: called.append(self),
    )
    _maybe_register_custom_embed("Org/custom-embed")
    assert called == []


def test_maybe_register_custom_rerank_no_optin_noop(monkeypatch):
    """No registration when LOCAL_RERANK_MODEL is unset (default local)."""
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "local_rerank_model", "")
    _maybe_register_custom_rerank("local-reranker")


def test_maybe_register_custom_rerank_builtin_noop(monkeypatch):
    """Any reranker id in the live registry is left untouched."""
    import fastretrieval

    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "local_rerank_model", "acme/tiny-reranker")
    monkeypatch.setattr(
        fastretrieval.TextCrossEncoder,
        "list_supported_models",
        classmethod(lambda cls: [{"model": "acme/tiny-reranker"}]),
    )
    called = []
    monkeypatch.setattr(
        fastretrieval.CustomRerankerSpec,
        "register",
        lambda self: called.append(self),
    )
    _maybe_register_custom_rerank("acme/tiny-reranker")
    assert called == []


def test_maybe_register_custom_rerank_registers_public_spec(monkeypatch):
    """A BYO reranker id registers through the public spec API."""
    import fastretrieval

    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "local_rerank_model", "Org/custom-reranker")
    monkeypatch.setattr(
        settings, "local_rerank_model_file", "onnx/model_quantized.onnx"
    )

    captured = {}

    monkeypatch.setattr(
        fastretrieval.TextCrossEncoder,
        "list_supported_models",
        classmethod(lambda cls: []),
    )
    monkeypatch.setattr(
        fastretrieval.CustomRerankerSpec,
        "register",
        lambda self: captured.update(
            model=self.model_id,
            model_file=self.model_file,
            hf=self.hf,
        ),
    )

    _maybe_register_custom_rerank("Org/custom-reranker")

    assert captured["model"] == "Org/custom-reranker"
    assert captured["model_file"] == "onnx/model_quantized.onnx"
    assert captured["hf"] == "Org/custom-reranker"


@pytest.mark.asyncio
async def test_search_success():
    """Test search action success path."""
    with patch(
        "wet_mcp.server._run_configured_search",
        new_callable=AsyncMock,
        return_value=(
            '{"results": [{"url": "https://e", "title": "T", "snippet": "Search Results"}], '
            '"total": 1, "query": "test query"}'
        ),
    ):
        result = await search(action="search", query="test query")

        assert "Search Results" in text(result)
        assert "<untrusted_search_content>" in text(result)
        assert "[SECURITY:" in text(result)


@pytest.mark.asyncio
async def test_search_missing_query():
    """Test search action missing query."""
    result = await search(action="search", query=None)
    assert "Error: query is required" in text(result)


@pytest.mark.asyncio
async def test_extract_success():
    """Test extract action success path."""
    with patch("wet_mcp.server._extract", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = "Extracted Content"

        result = await extract(action="extract", urls=["https://example.com"])

        assert "Extracted Content" in text(result)
        assert "<untrusted_extract_content>" in text(result)
        assert "[SECURITY:" in text(result)
        mock_extract.assert_called_once_with(
            urls=["https://example.com"],
            format="markdown",
            stealth=False,
        )


@pytest.mark.asyncio
async def test_extract_with_options():
    """Test extract action with custom options."""
    with patch("wet_mcp.server._extract", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = "Extracted Content"

        result = await extract(
            action="extract",
            urls=["https://example.com"],
            format="json",
            stealth=False,
        )

        assert "Extracted Content" in text(result)
        assert "<untrusted_extract_content>" in text(result)
        mock_extract.assert_called_once_with(
            urls=["https://example.com"],
            format="json",
            stealth=False,
        )


@pytest.mark.asyncio
async def test_extract_missing_urls():
    """Test extract action missing urls."""
    result = await extract(action="extract", urls=None)
    assert "Error: urls is required" in text(result)


@pytest.mark.asyncio
async def test_crawl_success():
    """Test crawl action success path."""
    with patch("wet_mcp.server._crawl", new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = "Crawl Results"

        result = await extract(
            action="crawl",
            urls=["https://example.com"],
            depth=3,
            max_pages=50,
            format="json",
            stealth=False,
        )

        assert "Crawl Results" in text(result)
        assert "<untrusted_extract_content>" in text(result)
        mock_crawl.assert_called_once_with(
            urls=["https://example.com"],
            depth=3,
            max_pages=50,
            format="json",
            stealth=False,
        )


@pytest.mark.asyncio
async def test_crawl_defaults():
    """Test crawl action with defaults."""
    with patch("wet_mcp.server._crawl", new_callable=AsyncMock) as mock_crawl:
        mock_crawl.return_value = "Crawl Results"

        result = await extract(action="crawl", urls=["https://example.com"])

        assert "Crawl Results" in text(result)
        assert "<untrusted_extract_content>" in text(result)
        mock_crawl.assert_called_once_with(
            urls=["https://example.com"],
            depth=2,
            max_pages=20,
            format="markdown",
            stealth=False,
        )


@pytest.mark.asyncio
async def test_crawl_missing_urls():
    """Test crawl action missing urls."""
    result = await extract(action="crawl", urls=None)
    assert "Error: urls is required" in text(result)


@pytest.mark.asyncio
async def test_map_success():
    """Test map action success path."""
    with patch("wet_mcp.server._sitemap", new_callable=AsyncMock) as mock_sitemap:
        mock_sitemap.return_value = "Sitemap Content"

        result = await extract(
            action="map", urls=["https://example.com"], depth=3, max_pages=50
        )

        assert "Sitemap Content" in text(result)
        assert "<untrusted_extract_content>" in text(result)
        mock_sitemap.assert_called_once_with(
            urls=["https://example.com"],
            depth=3,
            max_pages=50,
        )


@pytest.mark.asyncio
async def test_map_defaults():
    """Test map action with defaults."""
    with patch("wet_mcp.server._sitemap", new_callable=AsyncMock) as mock_sitemap:
        mock_sitemap.return_value = "Sitemap Content"

        result = await extract(action="map", urls=["https://example.com"])

        assert "Sitemap Content" in text(result)
        assert "<untrusted_extract_content>" in text(result)
        mock_sitemap.assert_called_once_with(
            urls=["https://example.com"],
            depth=2,
            max_pages=20,
        )


@pytest.mark.asyncio
async def test_map_missing_urls():
    """Test map action missing urls."""
    result = await extract(action="map", urls=None)
    assert "Error: urls is required" in text(result)


@pytest.mark.asyncio
async def test_search_invalid_action():
    """Test invalid action on search tool."""
    result = await search(action="invalid_action")
    assert "Error: Unknown action" in text(result)


@pytest.mark.asyncio
async def test_extract_invalid_action():
    """Test invalid action on extract tool."""
    result = await extract(action="invalid_action")
    assert "Error: Unknown action" in text(result)


@pytest.mark.asyncio
async def test_search_applies_reranking():
    """Verify search action calls _rerank_results when reranker is available."""
    mock_results = json.dumps(
        {
            "results": [
                {
                    "url": f"https://example{i}.com/page",
                    "title": f"R{i}",
                    "snippet": f"Content {i}",
                    "source": "g",
                }
                for i in range(6)
            ],
            "total": 6,
            "query": "test",
        }
    )

    reranked = [
        {
            "url": "https://example2.com/page",
            "title": "R2",
            "snippet": "Content 2",
            "source": "g",
            "content": "Content 2",
            "score": 0.9,
        },
        {
            "url": "https://example0.com/page",
            "title": "R0",
            "snippet": "Content 0",
            "source": "g",
            "content": "Content 0",
            "score": 0.7,
        },
    ]

    with (
        patch(
            "wet_mcp.server._run_configured_search",
            new_callable=AsyncMock,
            return_value=mock_results,
        ),
        patch(
            "wet_mcp.server._rerank_results",
            new_callable=AsyncMock,
            return_value=reranked,
        ) as mock_rerank,
        patch("wet_mcp.server._web_cache", None),
    ):
        result = await search(action="search", query="test", max_results=3)

        # Verify reranker was called
        mock_rerank.assert_called_once()
        call_args = mock_rerank.call_args
        assert call_args[0][0] == "test"  # query
        assert call_args[1]["top_n"] == 3  # top_n

        # Verify reranked results are used
        data = payload(result)
        assert data["total"] == 2  # only 2 reranked results
        assert data["results"][0]["url"] == "https://example2.com/page"


@pytest.mark.asyncio
async def test_search_reranking_failure_falls_back():
    """When reranking fails, original results are returned."""
    mock_results = json.dumps(
        {
            "results": [
                {"url": "https://a.com", "title": "A", "snippet": "S", "source": "g"}
            ],
            "total": 1,
            "query": "test",
        }
    )

    with (
        patch(
            "wet_mcp.server._run_configured_search",
            new_callable=AsyncMock,
            return_value=mock_results,
        ),
        patch(
            "wet_mcp.server._rerank_results",
            new_callable=AsyncMock,
            side_effect=Exception("rerank fail"),
        ),
        patch("wet_mcp.server._web_cache", None),
    ):
        result = await search(action="search", query="test", max_results=3)
        data = payload(result)
        assert data["total"] == 1  # original result preserved


async def test_extract_convert_requires_paths():
    result = await extract(action="convert")
    assert "Error" in text(result)
    assert "paths" in text(result)


# ---------------------------------------------------------------------------
# Phase 2: extract_structured
# ---------------------------------------------------------------------------


async def test_extract_structured_action():
    """Test extract_structured delegates to structured.extract_structured."""
    with patch(
        "wet_mcp.sources.structured.extract_structured",
        new_callable=AsyncMock,
        return_value='{"name": "Test"}',
    ) as mock_fn:
        result = await extract(
            action="extract_structured",
            urls=["https://example.com"],
            schema={"type": "object", "properties": {"name": {"type": "string"}}},
            prompt="Extract the name",
        )

        assert payload(result)["name"] == "Test"
        assert "<untrusted_extract_content>" in text(result)
        mock_fn.assert_called_once_with(
            urls=["https://example.com"],
            schema={"type": "object", "properties": {"name": {"type": "string"}}},
            prompt="Extract the name",
            stealth=False,
        )


async def test_extract_structured_requires_urls():
    """Test extract_structured requires urls."""
    result = await extract(
        action="extract_structured",
        schema={"type": "object"},
    )
    assert "Error" in text(result)
    assert "urls" in text(result)


async def test_extract_structured_requires_schema():
    """Test extract_structured requires schema."""
    result = await extract(
        action="extract_structured",
        urls=["https://example.com"],
    )
    assert "Error" in text(result)
    assert "schema" in text(result)


async def test_extract_batch_requires_urls():
    """Test batch action requires urls."""
    result = await extract(action="batch", urls=None)
    assert "Error: urls is required for batch action" in text(result)


# ---------------------------------------------------------------------------
# Phase 2: similar action
# ---------------------------------------------------------------------------


async def test_search_similar_action_uses_configured_chain():
    """The similar action delegates without forcing a SearXNG URL."""
    with patch(
        "wet_mcp.sources.search_strategies.find_similar",
        new_callable=AsyncMock,
        return_value='{"results": []}',
    ) as mock_fn:
        result = await search(action="similar", query="https://example.com")

    assert payload(result)["results"] == []
    assert "<untrusted_search_content>" in text(result)
    mock_fn.assert_awaited_once_with(
        url="https://example.com",
        max_results=10,
    )


async def test_search_similar_requires_url():
    """Test similar action requires query to be a URL."""
    result = await search(action="similar", query="not a url")
    assert "Error" in text(result)
    assert "URL" in text(result)


async def test_search_similar_requires_query():
    """Test similar action requires query."""
    result = await search(action="similar", query=None)
    assert "Error" in text(result)
    assert "query" in text(result)


# ---------------------------------------------------------------------------
# Phase 2: expand flag
# ---------------------------------------------------------------------------


async def test_search_expand_flag():
    """Test expand=True calls expand_query and uses expanded query."""
    with (
        patch(
            "wet_mcp.server._run_configured_search",
            new_callable=AsyncMock,
            return_value=(
                '{"results": [{"url": "https://e", "title": "T", "snippet": "Search Results"}], '
                '"total": 1, "query": "q"}'
            ),
        ) as mock_search,
        patch(
            "wet_mcp.sources.search_strategies.expand_query",
            new_callable=AsyncMock,
            return_value=[
                "python web scraping",
                "python html parsing",
                "python data extraction",
            ],
        ),
    ):
        result = await search(action="search", query="python web scraping", expand=True)

        assert "Search Results" in text(result)
        # Verify expanded query was passed to the configured chain.
        assert "OR" in mock_search.await_args.kwargs["query"]


# ---------------------------------------------------------------------------
# Phase 2: enrich flag
# ---------------------------------------------------------------------------


async def test_search_enrich_flag():
    """Test enrich=True calls enrich_snippets after search."""
    mock_results = json.dumps(
        {
            "results": [
                {
                    "url": "https://a.com",
                    "title": "A",
                    "snippet": "Short",
                    "source": "g",
                }
            ],
            "total": 1,
            "query": "test",
        }
    )
    enriched_results = [
        {
            "url": "https://a.com",
            "title": "A",
            "snippet": "Enriched content",
            "source": "g",
        }
    ]

    with (
        patch(
            "wet_mcp.server._run_configured_search",
            new_callable=AsyncMock,
            return_value=mock_results,
        ),
        patch(
            "wet_mcp.server._rerank_results",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("wet_mcp.server._web_cache", None),
        patch(
            "wet_mcp.sources.search_strategies.enrich_snippets",
            new_callable=AsyncMock,
            return_value=enriched_results,
        ) as mock_enrich,
    ):
        result = await search(action="search", query="test", enrich=True)

        mock_enrich.assert_called_once()
        # Verify enriched content is in output
        assert "Enriched content" in text(result)
