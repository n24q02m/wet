"""Unit tests for SearXNG search wrapper (delegates to web-core).

Tests the wet wrapper layer: JSON conversion, error handling,
health check integration, and parameter passing to web-core.
"""

import json
import unittest.mock

import pytest
from hull_web.search import SearchError
from hull_web.search.models import SearchResult

from wet.sources.searxng import search


@pytest.fixture(autouse=True)
def mock_health_check():
    """Mock _ensure_searxng_healthy to prevent real SearXNG startup in unit tests."""
    with unittest.mock.patch(
        "wet.sources.searxng._ensure_searxng_healthy",
        new_callable=unittest.mock.AsyncMock,
    ) as mock_healthy:
        mock_healthy.side_effect = lambda url: url
        yield mock_healthy


@pytest.fixture
def mock_wc_search():
    """Mock web-core's search function at the delegation boundary."""
    with unittest.mock.patch(
        "wet.sources.searxng._wc_search",
        new_callable=unittest.mock.AsyncMock,
    ) as mock_search:
        yield mock_search


def _make_results(count=1, **overrides):
    """Create mock SearchResult objects."""
    return [
        SearchResult(
            url=overrides.get("url", f"https://example.com/page{i}"),
            title=overrides.get("title", f"Title {i}"),
            snippet=overrides.get("snippet", f"Snippet {i}"),
            source=overrides.get("source", "google"),
        )
        for i in range(count)
    ]


async def test_search_success(mock_wc_search):
    """Test successful search returns JSON with correct structure."""
    mock_wc_search.return_value = [
        SearchResult(
            url="https://example.com",
            title="Example Domain",
            snippet="This domain is for use in illustrative examples.",
            source="google",
        )
    ]

    result = await search(
        searxng_url="http://localhost:8080",
        query="example",
        categories="general",
        max_results=1,
    )

    data = json.loads(result)
    assert data["query"] == "example"
    assert data["total"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["url"] == "https://example.com"
    assert data["results"][0]["title"] == "Example Domain"


async def test_search_empty(mock_wc_search):
    """Test search with no results."""
    mock_wc_search.return_value = []

    result = await search(
        searxng_url="http://localhost:8080",
        query="nonexistent",
    )

    data = json.loads(result)
    assert data["query"] == "nonexistent"
    assert data["total"] == 0
    assert len(data["results"]) == 0


async def test_search_error_returns_json(mock_wc_search):
    """Test SearchError is caught and returned as JSON error."""
    mock_wc_search.side_effect = SearchError("test", "HTTP 500")

    result = await search(
        searxng_url="http://localhost:8080",
        query="error",
    )

    data = json.loads(result)
    assert "error" in data


async def test_search_request_error_retry_fails(mock_wc_search):
    """Test connection error triggers restart + retry, both fail."""
    mock_wc_search.side_effect = SearchError(
        "test", "Request error: Connection refused"
    )

    result = await search(
        searxng_url="http://localhost:8080",
        query="retry_connect",
    )

    data = json.loads(result)
    assert "error" in data
    # Should have called _wc_search twice (original + retry after restart)
    assert mock_wc_search.call_count == 2


async def test_search_request_error_retry_succeeds(mock_wc_search):
    """Test connection error triggers restart + retry that succeeds."""
    retry_results = _make_results(1)
    mock_wc_search.side_effect = [
        SearchError("test", "Request error: Connection refused"),
        retry_results,
    ]

    result = await search(
        searxng_url="http://localhost:8080",
        query="retry_success",
    )

    data = json.loads(result)
    assert data["total"] == 1
    assert data["query"] == "retry_success"
    assert mock_wc_search.call_count == 2


async def test_search_passes_all_params(mock_wc_search):
    """Test all parameters are forwarded to web-core search."""
    mock_wc_search.return_value = _make_results(1)

    await search(
        searxng_url="http://localhost:8080",
        query="test",
        categories="images",
        max_results=5,
        time_range="week",
        language="vi",
        include_domains=["docs.python.org"],
        exclude_domains=["pinterest.com"],
    )

    mock_wc_search.assert_called_once_with(
        "http://localhost:8080",
        "test",
        categories="images",
        max_results=5,
        time_range="week",
        language="vi",
        include_domains=["docs.python.org"],
        exclude_domains=["pinterest.com"],
        auth=None,
    )


async def test_search_result_format(mock_wc_search):
    """Test search results have correct keys in JSON output."""
    mock_wc_search.return_value = [
        SearchResult(
            url="https://example.com",
            title="Example Title",
            snippet="Example snippet text",
            source="duckduckgo",
        )
    ]

    result = await search(
        searxng_url="http://localhost:8080",
        query="format_test",
    )

    data = json.loads(result)
    r = data["results"][0]
    assert r["url"] == "https://example.com"
    assert r["title"] == "Example Title"
    assert r["snippet"] == "Example snippet text"
    assert r["source"] == "duckduckgo"


async def test_search_health_check_called(mock_health_check, mock_wc_search):
    """Test that health check is called before search."""
    mock_wc_search.return_value = []

    await search(
        searxng_url="http://localhost:8080",
        query="health_test",
    )

    mock_health_check.assert_called_once_with("http://localhost:8080")


async def test_search_uses_healthy_url(mock_health_check, mock_wc_search):
    """Test that search uses the URL returned by health check."""
    mock_health_check.side_effect = None
    mock_health_check.return_value = "http://127.0.0.1:9090"
    mock_wc_search.return_value = []

    await search(
        searxng_url="http://localhost:8080",
        query="url_test",
    )

    # web-core search should receive the healthy URL
    mock_wc_search.assert_called_once()
    assert mock_wc_search.call_args[0][0] == "http://127.0.0.1:9090"


async def test_search_multiple_results(mock_wc_search):
    """Test search with multiple results."""
    mock_wc_search.return_value = _make_results(5)

    result = await search(
        searxng_url="http://localhost:8080",
        query="multi",
        max_results=5,
    )

    data = json.loads(result)
    assert data["total"] == 5
    assert len(data["results"]) == 5
