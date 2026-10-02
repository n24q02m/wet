"""Unit tests for crawl functionality with singleton browser pool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp.sources.crawler import crawl


@pytest.mark.asyncio
async def test_crawl_basic_success(mock_crawler_instance):
    """Test basic crawling functionality."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.markdown = "Mock Content"
    mock_result.cleaned_html = "<p>Mock Content</p>"
    mock_result.metadata = {"title": "Mock Title"}
    mock_result.links = {"internal": [], "external": []}

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await crawl(urls=["https://example.com"], depth=1, max_pages=10)

    results = json.loads(result_json)
    assert len(results) == 1
    assert results[0]["url"] == "https://example.com"
    assert results[0]["content"] == "Mock Content"
    assert results[0]["title"] == "Mock Title"
    assert results[0]["depth"] == 0


@pytest.mark.asyncio
async def test_crawl_depth_limit(mock_crawler_instance):
    """Test that crawling respects the depth limit."""

    def side_effect(url, config=None):
        result = MagicMock()
        result.success = True
        result.markdown = f"Content for {url}"
        result.cleaned_html = f"<p>Content for {url}</p>"
        result.metadata = {"title": f"Title for {url}"}

        if url == "https://example.com":
            result.links = {
                "internal": [{"href": "https://example.com/page2"}],
                "external": [],
            }
        elif url == "https://example.com/page2":
            result.links = {
                "internal": [{"href": "https://example.com/page3"}],
                "external": [],
            }
        else:
            result.links = {"internal": [], "external": []}

        return result

    mock_crawler_instance.arun = AsyncMock(side_effect=side_effect)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await crawl(urls=["https://example.com"], depth=1, max_pages=10)

    results = json.loads(result_json)

    urls_crawled = [r["url"] for r in results]
    assert set(urls_crawled) == {"https://example.com", "https://example.com/page2"}
    assert "https://example.com/page3" not in urls_crawled


@pytest.mark.asyncio
async def test_crawl_max_pages(mock_crawler_instance):
    """Test that crawling respects the max_pages limit."""

    def side_effect(url, config=None):
        result = MagicMock()
        result.success = True
        result.markdown = f"Content for {url}"
        result.cleaned_html = f"<p>Content for {url}</p>"
        result.metadata = {"title": f"Title for {url}"}

        if "page" in url:
            next_num = int(url.split("page")[-1]) + 1
        else:
            next_num = 2

        next_url = f"https://example.com/page{next_num}"
        result.links = {"internal": [{"href": next_url}], "external": []}
        return result

    mock_crawler_instance.arun = AsyncMock(side_effect=side_effect)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await crawl(
            urls=["https://example.com/page1"], depth=10, max_pages=3
        )

    results = json.loads(result_json)
    assert len(results) == 3
    urls = [r["url"] for r in results]
    assert set(urls) == {
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3",
    }


@pytest.mark.asyncio
async def test_crawl_unsafe_url(mock_crawler_instance):
    """Test that unsafe URLs are skipped."""
    mock_crawler_instance.arun = AsyncMock()

    with (
        patch(
            "wet_mcp.sources.crawler._get_crawler",
            new_callable=AsyncMock,
            return_value=mock_crawler_instance,
        ),
        patch(
            "wet_mcp.sources.crawler.is_safe_url", return_value=False
        ) as mock_is_safe,
    ):
        result_json = await crawl(urls=["https://unsafe.com"])

    results = json.loads(result_json)
    assert len(results) == 0
    mock_crawler_instance.arun.assert_not_called()
    mock_is_safe.assert_called_with("https://unsafe.com")


@pytest.mark.asyncio
async def test_crawl_error_handling(mock_crawler_instance):
    """Test that exceptions during crawling are handled gracefully."""
    mock_crawler_instance.arun = AsyncMock(side_effect=Exception("Crawl failed"))

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await crawl(urls=["https://example.com"])

    results = json.loads(result_json)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_crawl_already_visited(mock_crawler_instance):
    """Test that visited URLs are not re-crawled."""

    def side_effect(url, config=None):
        result = MagicMock()
        result.success = True
        result.markdown = f"Content for {url}"
        result.cleaned_html = f"<p>Content for {url}</p>"
        result.metadata = {"title": f"Title for {url}"}

        if url == "https://example.com/a":
            result.links = {
                "internal": [{"href": "https://example.com/b"}],
                "external": [],
            }
        elif url == "https://example.com/b":
            result.links = {
                "internal": [{"href": "https://example.com/a"}],
                "external": [],
            }
        else:
            result.links = {"internal": [], "external": []}

        return result

    mock_crawler_instance.arun = AsyncMock(side_effect=side_effect)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await crawl(urls=["https://example.com/a"], depth=5, max_pages=10)

    results = json.loads(result_json)
    assert len(results) == 2
    urls = [r["url"] for r in results]
    assert set(urls) == {"https://example.com/a", "https://example.com/b"}


@pytest.mark.asyncio
async def test_crawl_stealth_param(mock_crawler_instance):
    """Test stealth parameter is passed to _get_crawler."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.markdown = "content"
    mock_result.cleaned_html = "<p>content</p>"
    mock_result.metadata = {"title": "Test"}
    mock_result.links = {"internal": [], "external": []}

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ) as mock_get_crawler:
        await crawl(urls=["https://example.com"], stealth=True)
        mock_get_crawler.assert_called_with(True)

        mock_get_crawler.reset_mock()

        await crawl(urls=["https://example.com"], stealth=False)
        mock_get_crawler.assert_called_with(False)


@pytest.mark.asyncio
async def test_crawl_content_truncation(mock_crawler_instance):
    """Test that crawled content is truncated to 5000 chars."""
    long_content = "x" * 10000
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.markdown = long_content
    mock_result.cleaned_html = f"<p>{long_content}</p>"
    mock_result.metadata = {"title": "Long Page"}
    mock_result.links = {"internal": [], "external": []}

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await crawl(urls=["https://example.com"], depth=0)

    results = json.loads(result_json)
    assert len(results) == 1
    assert len(results[0]["content"]) == 5000


@pytest.mark.asyncio
async def test_crawl_failed_result(mock_crawler_instance):
    """Test that failed crawl results are skipped (not added to output)."""
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error_message = "404 Not Found"

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await crawl(urls=["https://example.com"], depth=0)

    results = json.loads(result_json)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_crawl_multiple_roots(mock_crawler_instance):
    """Test crawling multiple root URLs."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.markdown = "Content"
    mock_result.cleaned_html = "<p>Content</p>"
    mock_result.metadata = {"title": "Title"}
    mock_result.links = {"internal": [], "external": []}

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await crawl(
            urls=["https://example.com", "https://other.com"], depth=0
        )

    results = json.loads(result_json)
    urls = [r["url"] for r in results]
    assert set(urls) == {"https://example.com", "https://other.com"}
