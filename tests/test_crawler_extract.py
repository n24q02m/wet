"""Tests for ``extract`` (post web-core ScrapingAgent migration).

Each test patches ``wet_mcp.sources.crawler._get_scraping_agent`` to return
a fake agent so the real strategy chain never fires. Output is the smart-
chunks dict shape from ``wet_mcp.sources._smart_chunks``.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp.sources.crawler import extract


def _fake_agent(scrape_return: str | None = None, scrape_side_effect=None):
    agent = MagicMock()
    if scrape_side_effect is not None:
        agent.scrape = AsyncMock(side_effect=scrape_side_effect)
    else:
        agent.scrape = AsyncMock(return_value=scrape_return or "")
    agent.strategy_cache = MagicMock()
    agent.strategy_cache.recommend = AsyncMock(return_value=["basic_http"])
    return agent


@pytest.mark.asyncio
async def test_extract_success():
    """Successful scrape returns smart-chunks shape with markdown body."""
    agent = _fake_agent(scrape_return="# Test Title\n\nTest content.")

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=agent,
    ):
        result_json = await extract(["https://example.com"], format="markdown")
        results = json.loads(result_json)

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com"
        assert results[0]["metadata"]["title"] == "Test Title"
        assert "Test content" in results[0]["clean_text"]
        assert results[0]["metadata"]["scrape_strategy_used"] == "basic_http"


@pytest.mark.asyncio
async def test_extract_failure():
    """ScrapingAgent failure surfaces as per-URL error entry."""
    agent = _fake_agent(scrape_side_effect=RuntimeError("Page not found"))

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=agent,
    ):
        result_json = await extract(["https://example.com"])
        results = json.loads(result_json)

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com"
        assert "Page not found" in results[0]["error"]


@pytest.mark.asyncio
async def test_extract_unsafe_url():
    """SSRF guard rejects internal URLs before agent invocation."""
    agent = _fake_agent(scrape_return="should not run")

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=agent,
    ):
        result_json = await extract(["http://127.0.0.1"])
        results = json.loads(result_json)

        assert len(results) == 1
        assert results[0]["url"] == "http://127.0.0.1"
        assert "Security Alert" in results[0]["error"]
        agent.scrape.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_exception():
    """Generic exception from agent.scrape becomes the result error string."""
    agent = _fake_agent(scrape_side_effect=Exception("Connection error"))

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=agent,
    ):
        result_json = await extract(["https://example.com"])
        results = json.loads(result_json)

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com"
        assert "Connection error" in results[0]["error"]


@pytest.mark.asyncio
async def test_extract_html_format():
    """HTML responses produce both clean_text and markdown bridge output."""
    html = "<!doctype html><html><body><p>HTML body</p></body></html>"
    agent = _fake_agent(scrape_return=html)

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=agent,
    ):
        result_json = await extract(["https://example.com"], format="html")
        results = json.loads(result_json)

        assert "HTML body" in results[0]["clean_text"]
        assert results[0]["metadata"]["source_format"] == "html"


@pytest.mark.asyncio
async def test_extract_stealth_param():
    """``stealth`` is forwarded to the agent factory."""
    agent = _fake_agent(scrape_return="ok")

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=agent,
    ) as mock_get:
        await extract(["https://example.com"], stealth=True)
        mock_get.assert_called_with(stealth=True)

        mock_get.reset_mock()
        await extract(["https://example.com"], stealth=False)
        mock_get.assert_called_with(stealth=False)


@pytest.mark.asyncio
async def test_extract_empty_list():
    """Empty input list returns empty array without invoking the agent."""
    agent = _fake_agent(scrape_return="ok")

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=agent,
    ):
        result_json = await extract([])
        results = json.loads(result_json)

        assert results == []
        agent.scrape.assert_not_awaited()
