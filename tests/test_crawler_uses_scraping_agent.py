"""Verify ``extract`` delegates to web-core ``ScrapingAgent`` and emits smart chunks.

Phase 1 migration (spec §4.2 + §5.5): wet's extract pipeline must consume
``hull_web.scraper.ScrapingAgent`` instead of instantiating Crawl4AI
directly. Output is the structured smart-chunks dict from
``wet_mcp.sources._smart_chunks``.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hull_web.scraper import RobotsCache, ScrapingAgent, ScrapingResult, StrategyCache


class _FakeRobotsCache(RobotsCache):
    def __init__(self, allowed: bool):
        super().__init__(user_agent="test-agent")
        self.allowed = allowed

    async def is_allowed(self, url: str) -> bool:
        return self.allowed


def _build_actual_scraping_agent(*, respect_robots: bool):
    strategy = MagicMock()
    strategy.fetch = AsyncMock(
        return_value=ScrapingResult(
            content="x" * 120,
            url="https://example.com/page",
            strategy="fake",
            status_code=200,
        )
    )
    agent = ScrapingAgent(
        strategies={"fake": strategy},
        strategy_cache=StrategyCache(default_order=["fake"]),
        robots_cache=_FakeRobotsCache(allowed=False),
        max_retries=1,
        min_content_length=1,
        enable_selector_inference=False,
        respect_robots=respect_robots,
    )
    return agent, strategy


def _build_fake_agent(scrape_return: str | None = None, scrape_side_effect=None):
    """Construct a minimal ScrapingAgent stand-in for crawler.extract tests."""
    fake_agent = MagicMock()
    if scrape_side_effect is not None:
        fake_agent.scrape = AsyncMock(side_effect=scrape_side_effect)
    else:
        fake_agent.scrape = AsyncMock(return_value=scrape_return or "")
    fake_agent.strategy_cache = MagicMock()
    fake_agent.strategy_cache.recommend = AsyncMock(return_value=["basic_http"])
    return fake_agent


@pytest.mark.asyncio
async def test_extract_calls_scraping_agent() -> None:
    """``extract`` MUST instantiate ScrapingAgent and call its scrape() coroutine."""
    from wet_mcp.sources.crawler import extract

    fake_agent = _build_fake_agent(scrape_return="# Example\n\nhello world")

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=fake_agent,
    ):
        result_json = await extract(["https://example.com/article"])

    fake_agent.scrape.assert_awaited_once()
    call_args = fake_agent.scrape.await_args
    assert call_args.args[0] == "https://example.com/article"

    pages = json.loads(result_json)
    assert isinstance(pages, list)
    assert len(pages) == 1


@pytest.mark.asyncio
async def test_extract_returns_smart_chunks_shape() -> None:
    """Each extract result must follow the 5-key smart-chunks shape."""
    from wet_mcp.sources.crawler import extract

    fake_agent = _build_fake_agent(
        scrape_return=(
            "<!doctype html><html><head><title>Doc</title></head>"
            "<body><h1>Doc</h1><p>body</p>"
            "<pre><code class='language-python'>x=1</code></pre>"
            "</body></html>"
        )
    )

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=fake_agent,
    ):
        result_json = await extract(["https://example.com/page"])

    pages = json.loads(result_json)
    page = pages[0]
    assert page["url"] == "https://example.com/page"
    for key in ("clean_text", "markdown", "structured_data", "code_blocks", "metadata"):
        assert key in page, f"missing {key} in smart-chunks output"
    assert page["metadata"]["scrape_strategy_used"]  # populated from agent state


@pytest.mark.asyncio
async def test_extract_unsafe_url_blocked_before_agent() -> None:
    """SSRF guard runs before ScrapingAgent is invoked."""
    from wet_mcp.sources.crawler import extract

    fake_agent = _build_fake_agent(scrape_return="should not run")

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=fake_agent,
    ):
        result_json = await extract(["http://127.0.0.1/admin"])

    fake_agent.scrape.assert_not_awaited()
    pages = json.loads(result_json)
    assert "Security Alert" in pages[0]["error"]


@pytest.mark.asyncio
async def test_extract_agent_error_surfaces_in_result() -> None:
    """When ScrapingAgent raises, extract emits a per-URL error entry."""
    from wet_mcp.sources.crawler import extract

    fake_agent = _build_fake_agent(
        scrape_side_effect=RuntimeError("strategy chain exhausted")
    )

    with patch(
        "wet_mcp.sources.crawler._get_scraping_agent",
        new_callable=AsyncMock,
        return_value=fake_agent,
    ):
        result_json = await extract(["https://example.com/x"])

    pages = json.loads(result_json)
    assert "strategy chain exhausted" in pages[0]["error"]


@pytest.mark.asyncio
async def test_extract_actual_agent_blocks_before_strategy_when_robots_enabled() -> (
    None
):
    """The real ScrapingAgent must enforce its RobotsCache before any strategy."""
    from wet_mcp.sources.crawler import extract

    agent, strategy = _build_actual_scraping_agent(respect_robots=True)

    with (
        patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=agent,
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await extract(["https://example.com/page"])

    pages = json.loads(result_json)
    assert "robots.txt disallows" in pages[0]["error"]
    strategy.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_actual_agent_reaches_strategy_when_robots_disabled() -> None:
    """The legacy disabled mode still executes the configured strategy."""
    from wet_mcp.sources.crawler import extract

    agent, strategy = _build_actual_scraping_agent(respect_robots=False)

    with (
        patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=agent,
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await extract(["https://example.com/page"])

    pages = json.loads(result_json)
    assert "error" not in pages[0]
    assert pages[0]["url"] == "https://example.com/page"
    strategy.fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_document_url_uses_markitdown_bypass() -> None:
    """PDF/DOCX URLs must skip ScrapingAgent and route through markitdown helper."""
    from wet_mcp.sources.crawler import extract

    fake_agent = _build_fake_agent(scrape_return="should not run")

    with (
        patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=fake_agent,
        ),
        patch(
            "wet_mcp.sources.crawler._extract_with_markitdown",
            new_callable=AsyncMock,
            return_value={"url": "https://example.com/r.pdf", "content": "PDF text"},
        ) as mock_md,
    ):
        result_json = await extract(["https://example.com/report.pdf"])

    fake_agent.scrape.assert_not_awaited()
    mock_md.assert_awaited_once()
    pages = json.loads(result_json)
    assert pages[0]["content"] == "PDF text"
