"""Tests for ``extract(action="diff")`` -- snapshot retention + change tracking (S14 Task 7)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult
from structured import payload, text

from wet_mcp.cache import WebCache
from wet_mcp.server import extract


def _extract_json(url: str, markdown: str) -> str:
    """Build a JSON string matching ``sources.crawler.extract``'s per-URL shape."""
    return json.dumps(
        [
            {
                "url": url,
                "markdown": markdown,
                "clean_text": markdown,
                "structured_data": [],
                "code_blocks": [],
                "metadata": {"title": "", "url": url},
            }
        ]
    )


@pytest.fixture
def real_cache(tmp_path):
    """A real (not mocked) WebCache so record_snapshot/latest_snapshots/diff
    run against actual SQLite state instead of a hand-wired mock.
    """
    import wet_mcp.server as server

    cache = WebCache(tmp_path / "diff_test.db")
    old_cache = server._web_cache
    server._web_cache = cache
    yield cache
    cache.close()
    server._web_cache = old_cache


@pytest.mark.asyncio
async def test_diff_missing_urls_returns_error():
    result = await extract(action="diff")
    assert isinstance(result, CallToolResult)
    assert "urls is required" in text(result)


@pytest.mark.asyncio
async def test_diff_requires_cache_enabled():
    import wet_mcp.server as server

    old_cache = server._web_cache
    server._web_cache = None
    try:
        result = await extract(action="diff", urls=["https://example.com"])
    finally:
        server._web_cache = old_cache
    assert isinstance(result, CallToolResult)
    assert "requires the web cache" in text(result)


@pytest.mark.asyncio
async def test_diff_first_fetch_is_new(real_cache):
    """Only one snapshot exists so far -> change_status 'new', empty diff."""
    with patch(
        "wet_mcp.server._extract",
        new_callable=AsyncMock,
        return_value=_extract_json("https://example.com", "hello v1"),
    ):
        result = await extract(action="diff", urls=["https://example.com"])

    data = payload(result)
    assert data["change_status"] == "new"
    assert data["diff"] == ""
    assert data["old_fetched_at"] is None
    assert data["new_fetched_at"] is not None


@pytest.mark.asyncio
async def test_diff_second_fetch_changed(real_cache):
    """Two differing snapshots -> change_status 'changed' with -old/+new lines."""
    with patch(
        "wet_mcp.server._extract",
        new_callable=AsyncMock,
        return_value=_extract_json("https://example.com", "line one\nline two"),
    ):
        await extract(action="diff", urls=["https://example.com"])

    with patch(
        "wet_mcp.server._extract",
        new_callable=AsyncMock,
        return_value=_extract_json("https://example.com", "line one\nline THREE"),
    ):
        result = await extract(action="diff", urls=["https://example.com"])

    data = payload(result)
    assert data["change_status"] == "changed"
    assert "-line two" in data["diff"]
    assert "+line THREE" in data["diff"]
    assert data["old_fetched_at"] is not None
    assert data["new_fetched_at"] is not None
    # Diff output is external content -- XPIA marker must be present on both
    # response channels (structuredContent envelope + text-block boundary tag).
    assert data["_untrusted_source"] == "web"
    assert "<untrusted_extract_content>" in text(result)


@pytest.mark.asyncio
async def test_diff_unchanged_content_is_same(real_cache):
    """Refetching identical content -> change_status 'same', empty diff."""
    with patch(
        "wet_mcp.server._extract",
        new_callable=AsyncMock,
        return_value=_extract_json("https://example.com", "static content"),
    ):
        await extract(action="diff", urls=["https://example.com"])
        result = await extract(action="diff", urls=["https://example.com"])

    data = payload(result)
    assert data["change_status"] == "same"
    assert data["diff"] == ""


@pytest.mark.asyncio
async def test_diff_no_refetch_uses_existing_snapshots_only(real_cache):
    """refetch=False must not trigger a new fetch; diff the 2 newest stored snapshots."""
    real_cache.record_snapshot("https://example.com", "line one\nline two")
    real_cache.record_snapshot("https://example.com", "line one\nline THREE")

    with patch("wet_mcp.server._extract", new_callable=AsyncMock) as mock_extract:
        result = await extract(
            action="diff", urls=["https://example.com"], refetch=False
        )
        mock_extract.assert_not_called()

    data = payload(result)
    assert data["change_status"] == "changed"
    assert "-line two" in data["diff"]
    assert "+line THREE" in data["diff"]


@pytest.mark.asyncio
async def test_diff_no_history_and_no_refetch_returns_error(real_cache):
    """refetch=False with zero prior snapshots -> per-URL error, not a fabricated status."""
    with patch("wet_mcp.server._extract", new_callable=AsyncMock) as mock_extract:
        result = await extract(
            action="diff", urls=["https://never-fetched.com"], refetch=False
        )
        mock_extract.assert_not_called()

    data = payload(result)
    assert "no snapshot history" in data["error"]


@pytest.mark.asyncio
async def test_diff_multiple_urls_wraps_in_results(real_cache):
    """More than one URL -> list of per-URL diff dicts under 'results'."""

    async def fake_extract(urls, format, stealth):
        return _extract_json(urls[0], f"content for {urls[0]}")

    with patch(
        "wet_mcp.server._extract", new_callable=AsyncMock, side_effect=fake_extract
    ):
        result = await extract(action="diff", urls=["https://a.com", "https://b.com"])

    data = payload(result)
    assert [item["url"] for item in data["results"]] == [
        "https://a.com",
        "https://b.com",
    ]
    assert all(item["change_status"] == "new" for item in data["results"])
