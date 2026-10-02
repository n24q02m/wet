"""Tests for sitemap functionality with singleton browser pool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp.sources.crawler import sitemap


@pytest.mark.asyncio
async def test_sitemap_basic(mock_crawler_instance):
    """Test basic sitemap generation."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.links = {"internal": ["https://example.com/page1"]}
    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result = await sitemap(["https://example.com"], depth=1)

    data = json.loads(result)
    assert len(data) == 2
    assert data[0]["url"] == "https://example.com"
    assert data[1]["url"] == "https://example.com/page1"


@pytest.mark.asyncio
async def test_sitemap_dict_links(mock_crawler_instance):
    """Test sitemap with dict links (bug fix verification)."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.links = {
        "internal": [{"href": "https://example.com/page1", "text": "Page 1"}]
    }
    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result = await sitemap(["https://example.com"], depth=1)

    data = json.loads(result)
    assert len(data) == 2
    assert data[0]["url"] == "https://example.com"
    assert data[1]["url"] == "https://example.com/page1"


@pytest.mark.asyncio
async def test_sitemap_depth_limit(mock_crawler_instance):
    """Test sitemap depth limit."""

    def side_effect(url, config=None):
        res = MagicMock()
        res.success = True
        if url == "https://example.com":
            res.links = {"internal": ["https://example.com/page1"]}
        elif url == "https://example.com/page1":
            res.links = {"internal": ["https://example.com/page2"]}
        else:
            res.links = {"internal": []}
        return res

    mock_crawler_instance.arun = AsyncMock(side_effect=side_effect)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result = await sitemap(["https://example.com"], depth=1)

    data = json.loads(result)
    urls = [item["url"] for item in data]
    assert set(urls) == {"https://example.com", "https://example.com/page1"}
    assert "https://example.com/page2" not in urls


@pytest.mark.asyncio
async def test_sitemap_max_pages(mock_crawler_instance):
    """Test sitemap max pages limit."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.links = {
        "internal": [f"https://example.com/page{i}" for i in range(10)]
    }
    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result = await sitemap(["https://example.com"], depth=2, max_pages=5)

    data = json.loads(result)
    assert len(data) <= 5


@pytest.mark.asyncio
async def test_sitemap_error_handling(mock_crawler_instance):
    """Test error handling during crawl."""
    mock_crawler_instance.arun = AsyncMock(side_effect=Exception("Network error"))

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result = await sitemap(["https://example.com"], depth=1)

    data = json.loads(result)
    assert len(data) == 1
    assert data[0]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_sitemap_unsafe_url(mock_crawler_instance):
    """Test that unsafe URLs are skipped."""
    mock_crawler_instance.arun = AsyncMock()

    with (
        patch(
            "wet_mcp.sources.crawler._get_crawler",
            new_callable=AsyncMock,
            return_value=mock_crawler_instance,
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=False),
    ):
        result = await sitemap(["https://unsafe.example.com"], depth=1)

    data = json.loads(result)
    assert len(data) == 0
    mock_crawler_instance.arun.assert_not_called()


@pytest.mark.asyncio
async def test_sitemap_multiple_roots(mock_crawler_instance):
    """Test sitemap with multiple root URLs."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.links = {"internal": []}
    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result = await sitemap(["https://example.com", "https://other.com"], depth=0)

    data = json.loads(result)
    urls = [item["url"] for item in data]
    assert set(urls) == {"https://example.com", "https://other.com"}


@pytest.mark.asyncio
async def test_sitemap_no_duplicate_visits(mock_crawler_instance):
    """Test that already-visited URLs are not re-crawled."""

    def side_effect(url, config=None):
        res = MagicMock()
        res.success = True
        if url == "https://example.com/a":
            # Points back to itself and to /b
            res.links = {
                "internal": [
                    "https://example.com/b",
                    "https://example.com/a",
                ]
            }
        elif url == "https://example.com/b":
            # Points back to /a (cycle)
            res.links = {"internal": ["https://example.com/a"]}
        else:
            res.links = {"internal": []}
        return res

    mock_crawler_instance.arun = AsyncMock(side_effect=side_effect)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result = await sitemap(["https://example.com/a"], depth=5, max_pages=10)

    data = json.loads(result)
    urls = [item["url"] for item in data]
    assert set(urls) == {"https://example.com/a", "https://example.com/b"}
    # arun should only be called twice (once per unique URL)
    assert mock_crawler_instance.arun.call_count == 2
