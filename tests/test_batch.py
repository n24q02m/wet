"""Tests for batch extraction with per-domain rate limiting."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from wet_mcp.sources.crawler import DomainRateLimiter, batch_extract


@pytest.mark.asyncio
async def test_domain_rate_limiter_acquire():
    """Verify DomainRateLimiter acquire/release works correctly."""
    limiter = DomainRateLimiter(
        max_per_domain=2, requests_per_second=100.0, global_max=5
    )

    acquired = False
    async with limiter.acquire("https://example.com/page1"):
        acquired = True
    assert acquired


@pytest.mark.asyncio
async def test_batch_extract_success():
    """Batch extract 3 URLs -- all succeed."""
    mock_pages = [
        json.dumps(
            [
                {
                    "url": f"https://example{i}.com",
                    "title": f"Page {i}",
                    "content": f"Content {i}",
                }
            ]
        )
        for i in range(3)
    ]

    with patch(
        "wet_mcp.sources.crawler.extract", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.side_effect = mock_pages

        result = await batch_extract(
            urls=[f"https://example{i}.com" for i in range(3)],
            format="markdown",
            stealth=False,
        )

        parsed = json.loads(result)
        assert parsed["summary"]["total"] == 3
        assert parsed["summary"]["success"] == 3
        assert parsed["summary"]["failed"] == 0
        assert len(parsed["results"]) == 3
        assert len(parsed["errors"]) == 0


@pytest.mark.asyncio
async def test_batch_extract_partial_failure():
    """One URL fails, others succeed -- verify partial results."""

    async def mock_extract_fn(urls, format, stealth):
        url = urls[0]
        if "fail" in url:
            return json.dumps([{"url": url, "error": "Connection refused"}])
        return json.dumps([{"url": url, "title": "OK", "content": "OK"}])

    with patch(
        "wet_mcp.sources.crawler.extract", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.side_effect = mock_extract_fn

        result = await batch_extract(
            urls=["https://good1.com", "https://fail.com", "https://good2.com"],
        )

        parsed = json.loads(result)
        assert parsed["summary"]["total"] == 3
        assert parsed["summary"]["success"] == 2
        assert parsed["summary"]["failed"] == 1
        assert len(parsed["errors"]) == 1
        assert parsed["errors"][0]["url"] == "https://fail.com"


@pytest.mark.asyncio
async def test_batch_extract_max_urls():
    """Verify 51 URLs returns error."""
    urls = [f"https://example.com/page{i}" for i in range(51)]
    result = await batch_extract(urls=urls)
    assert "Error: Maximum 50 URLs per batch" in result
    assert "got 51" in result


@pytest.mark.asyncio
async def test_batch_extract_empty():
    """Verify empty URL list returns empty results."""
    result = await batch_extract(urls=[])
    parsed = json.loads(result)
    assert parsed["summary"]["total"] == 0
    assert parsed["summary"]["success"] == 0
    assert parsed["summary"]["failed"] == 0
    assert parsed["results"] == []
    assert parsed["errors"] == []
