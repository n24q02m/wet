import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Import from the module we're testing
from wet_mcp.sources import crawler


# Helper classes to mock AsyncWebCrawler results
class MockCrawlerResult:
    def __init__(
        self,
        success=True,
        markdown="md content",
        cleaned_html="<html>content</html>",
        metadata=None,
        links=None,
        media=None,
        error_message=None,
    ):
        self.success = success
        self.markdown = markdown
        self.cleaned_html = cleaned_html
        self.metadata = metadata or {"title": "Test Title"}
        self.links = links or {"internal": [], "external": []}
        self.media = media or {}
        self.error_message = error_message


class MockAsyncWebCrawler:
    def __init__(self, *args, **kwargs):
        self.arun = AsyncMock()
        self.arun.return_value = MockCrawlerResult()
        self.__aenter__ = AsyncMock(return_value=self)
        self.__aexit__ = AsyncMock()
        self.config = kwargs.get("config")


@pytest.fixture(autouse=True)
def reset_crawler_state():
    """Reset the module-level singleton state before and after each test."""
    crawler._crawler_instance = None
    crawler._crawler_stealth = False
    crawler._browser_semaphore = None
    yield
    crawler._crawler_instance = None
    crawler._crawler_stealth = False
    crawler._browser_semaphore = None


def _fake_scraping_agent(scrape_return=None, scrape_side_effect=None):
    """Build a fake ScrapingAgent stand-in for extract() tests."""
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
    agent = _fake_scraping_agent(scrape_return="# Test Title\n\nmd content")
    with (
        patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=agent,
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.extract(
            ["https://safe.com"],
            format="markdown",
            stealth=True,
            scan_full_page=True,
            delay_before_return_html=1.0,
            page_timeout=30000,
        )

        data = json.loads(result_json)
        assert len(data) == 1
        assert data[0]["url"] == "https://safe.com"
        assert "md content" in data[0]["clean_text"]
        assert data[0]["metadata"]["title"] == "Test Title"


@pytest.mark.asyncio
async def test_extract_html_format():
    html_payload = "<!doctype html><html><body>content</body></html>"
    agent = _fake_scraping_agent(scrape_return=html_payload)
    with (
        patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=agent,
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.extract(["https://safe.com"], format="html")
        data = json.loads(result_json)
        assert "content" in data[0]["clean_text"]
        assert data[0]["metadata"]["source_format"] == "html"


@pytest.mark.asyncio
async def test_extract_unsafe_url():
    agent = _fake_scraping_agent(scrape_return="should not run")
    with (
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=False),
        patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=agent,
        ),
    ):
        result_json = await crawler.extract(["http://unsafe.com"])
        data = json.loads(result_json)
        assert data[0]["error"] == "Security Alert: Unsafe URL blocked"


@pytest.mark.asyncio
async def test_extract_crawler_failure():
    agent = _fake_scraping_agent(scrape_side_effect=RuntimeError("Crawling failed"))
    with (
        patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=agent,
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.extract(["https://safe.com"])
        data = json.loads(result_json)
        assert "Crawling failed" in data[0]["error"]


@pytest.mark.asyncio
async def test_extract_crawler_exception():
    agent = _fake_scraping_agent(scrape_side_effect=Exception("Unexpected error"))
    with (
        patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=agent,
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.extract(["https://safe.com"])
        data = json.loads(result_json)
        assert "Unexpected error" in data[0]["error"]


@pytest.mark.asyncio
async def test_crawl_success():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        links={
            "internal": [{"href": "https://safe.com/page2"}, "https://safe.com/page3"]
        }
    )

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
        patch("playwright.async_api.async_playwright"),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.crawl(["https://safe.com"], depth=1, max_pages=3)
        data = json.loads(result_json)

        assert len(data) == 3
        urls = [d["url"] for d in data]
        assert "https://safe.com" in urls
        assert "https://safe.com/page2" in urls
        assert "https://safe.com/page3" in urls


@pytest.mark.asyncio
async def test_crawl_robots_blocked_result_is_excluded(monkeypatch):
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        success=False,
        error_message="robots.txt disallows the URL",
    )
    monkeypatch.setattr(crawler.settings, "respect_robots_txt", True)

    with (
        patch(
            "wet_mcp.sources.crawler._get_crawler",
            new=AsyncMock(return_value=mock_crawler),
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.crawl(["https://safe.com"], depth=0)

    assert json.loads(result_json) == []
    assert mock_crawler.arun.await_args.kwargs["config"].check_robots_txt is True


@pytest.mark.asyncio
async def test_crawl_unsafe_url():
    with patch("wet_mcp.sources.crawler.is_safe_url", return_value=False):
        with patch("wet_mcp.sources.crawler._get_crawler", new_callable=AsyncMock):
            result_json = await crawler.crawl(["http://unsafe.com"])
        data = json.loads(result_json)
        assert len(data) == 0


@pytest.mark.asyncio
async def test_crawl_exception():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.side_effect = Exception("Unexpected error")

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
        patch("playwright.async_api.async_playwright"),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.crawl(["https://safe.com"])
        data = json.loads(result_json)
        assert len(data) == 0  # Exception is caught, page isn't added


@pytest.mark.asyncio
async def test_sitemap_success():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        links={
            "internal": [{"href": "https://safe.com/page2"}, "https://safe.com/page3"]
        }
    )

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
        patch("playwright.async_api.async_playwright"),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.sitemap(["https://safe.com"], depth=1, max_pages=3)
        data = json.loads(result_json)

        assert len(data) == 3
        urls = [d["url"] for d in data]
        assert "https://safe.com" in urls
        assert "https://safe.com/page2" in urls
        assert "https://safe.com/page3" in urls


@pytest.mark.asyncio
async def test_sitemap_robots_blocked_result_is_excluded_when_enabled(monkeypatch):
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        success=False,
        error_message="robots.txt disallows the URL",
    )
    monkeypatch.setattr(crawler.settings, "respect_robots_txt", True)

    with (
        patch(
            "wet_mcp.sources.crawler._get_crawler",
            new=AsyncMock(return_value=mock_crawler),
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.sitemap(["https://safe.com"], depth=0)

    assert json.loads(result_json) == []
    assert mock_crawler.arun.await_args.kwargs["config"].check_robots_txt is True


@pytest.mark.asyncio
async def test_sitemap_failed_result_keeps_legacy_output_when_disabled(monkeypatch):
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        success=False,
        error_message="robots.txt disallows the URL",
    )
    monkeypatch.setattr(crawler.settings, "respect_robots_txt", False)

    with (
        patch(
            "wet_mcp.sources.crawler._get_crawler",
            new=AsyncMock(return_value=mock_crawler),
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.sitemap(["https://safe.com"], depth=0)

    assert json.loads(result_json) == [{"url": "https://safe.com", "depth": 0}]
    assert mock_crawler.arun.await_args.kwargs["config"].check_robots_txt is False


@pytest.mark.asyncio
async def test_sitemap_unsafe_url():
    with patch("wet_mcp.sources.crawler.is_safe_url", return_value=False):
        with patch("wet_mcp.sources.crawler._get_crawler", new_callable=AsyncMock):
            result_json = await crawler.sitemap(["http://unsafe.com"])
        data = json.loads(result_json)
        assert len(data) == 0


@pytest.mark.asyncio
async def test_sitemap_exception():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.side_effect = Exception("Unexpected error")

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
        patch("playwright.async_api.async_playwright"),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.sitemap(["https://safe.com"])
        data = json.loads(result_json)
        assert len(data) == 1  # Only root is added, crawling fails silently


@pytest.mark.asyncio
async def test_list_media_success():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        media={
            "images": ["img1.jpg", "img2.jpg"],
            "videos": ["vid1.mp4"],
            "audios": ["audio1.mp3"],
        }
    )

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
        patch("playwright.async_api.async_playwright"),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.list_media("https://safe.com", media_type="all")
        data = json.loads(result_json)

        assert "images" in data
        assert len(data["images"]) == 2
        assert "videos" in data
        assert len(data["videos"]) == 1
        assert "audio" in data
        assert len(data["audio"]) == 1


@pytest.mark.asyncio
async def test_list_media_robots_blocked_result_returns_error(monkeypatch):
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        success=False,
        error_message="robots.txt disallows the URL",
    )
    monkeypatch.setattr(crawler.settings, "respect_robots_txt", True)

    with (
        patch(
            "wet_mcp.sources.crawler._get_crawler",
            new=AsyncMock(return_value=mock_crawler),
        ),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.list_media("https://safe.com")

    assert json.loads(result_json) == {"error": "robots.txt disallows the URL"}
    assert mock_crawler.arun.await_args.kwargs["config"].check_robots_txt is True


@pytest.mark.asyncio
async def test_list_media_specific_type():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        media={"images": ["img1.jpg"], "videos": ["vid1.mp4"], "audios": ["audio1.mp3"]}
    )

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
        patch("playwright.async_api.async_playwright"),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.list_media("https://safe.com", media_type="images")
        data = json.loads(result_json)

        assert "images" in data
        assert "videos" not in data
        assert "audio" not in data


@pytest.mark.asyncio
async def test_list_media_unsafe_url():
    with patch("wet_mcp.sources.crawler.is_safe_url", return_value=False):
        result_json = await crawler.list_media("http://unsafe.com")
        data = json.loads(result_json)
        assert data["error"] == "Security Alert: Unsafe URL blocked"


@pytest.mark.asyncio
async def test_list_media_failure():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        success=False, error_message="Media error"
    )

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
        patch("playwright.async_api.async_playwright"),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.list_media("https://safe.com")
        data = json.loads(result_json)
        assert data["error"] == "Media error"


# Helpers for download_media tests
class MockResponse:
    def __init__(
        self, content=b"content", status_code=200, is_redirect=False, headers=None
    ):
        self.content = content
        self.status_code = status_code
        self.is_redirect = is_redirect
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "Error", request=MagicMock(), response=MagicMock()
            )


@pytest.mark.asyncio
async def test_download_media_success(tmp_path):
    mock_client = AsyncMock()
    mock_client.get.return_value = MockResponse(content=b"file data")

    with (
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
        patch(
            "httpx.AsyncClient",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock()
            ),
        ),
    ):
        result_json = await crawler.download_media(
            ["http://safe.com/image.jpg", "//safe.com/image2.jpg"], str(tmp_path)
        )
        data = json.loads(result_json)

        assert len(data) == 2
        assert "path" in data[0]
        assert Path(data[0]["path"]).exists()
        assert Path(data[0]["path"]).read_bytes() == b"file data"
        assert "path" in data[1]


@pytest.mark.asyncio
async def test_download_media_redirect(tmp_path):
    mock_client = AsyncMock()
    # First call: redirect. Second call: success
    mock_client.get.side_effect = [
        MockResponse(is_redirect=True, headers={"Location": "/new_image.jpg"}),
        MockResponse(content=b"redirected data"),
    ]

    with (
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
        patch(
            "httpx.AsyncClient",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock()
            ),
        ),
    ):
        result_json = await crawler.download_media(
            ["http://safe.com/image.jpg"], str(tmp_path)
        )
        data = json.loads(result_json)

        assert len(data) == 1
        assert "path" in data[0]
        assert Path(data[0]["path"]).name == "new_image.jpg"
        assert Path(data[0]["path"]).read_bytes() == b"redirected data"


@pytest.mark.asyncio
async def test_download_media_unsafe_url(tmp_path):
    with patch("wet_mcp.sources.crawler.is_safe_url", return_value=False):
        result_json = await crawler.download_media(
            ["http://unsafe.com/image.jpg"], str(tmp_path)
        )
        data = json.loads(result_json)
        assert data[0]["error"] == "Security Alert: Unsafe URL blocked"


@pytest.mark.asyncio
async def test_download_media_path_traversal(tmp_path):
    mock_client = AsyncMock()
    mock_client.get.return_value = MockResponse(content=b"file data")

    with (
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
        patch(
            "httpx.AsyncClient",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock()
            ),
        ),
    ):
        # Test path traversal in URL
        with patch("pathlib.Path.is_relative_to", return_value=False):
            result_json = await crawler.download_media(
                ["http://safe.com/../../etc/passwd"], str(tmp_path)
            )
            data = json.loads(result_json)

            assert len(data) == 1
            assert "Security Alert: Path traversal" in data[0]["error"]


@pytest.mark.asyncio
async def test_download_media_http_error(tmp_path):
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("HTTP Failed")

    with (
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
        patch(
            "httpx.AsyncClient",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock()
            ),
        ),
    ):
        result_json = await crawler.download_media(
            ["http://safe.com/image.jpg"], str(tmp_path)
        )
        data = json.loads(result_json)
        assert data[0]["error"] == "HTTP Failed"


@pytest.mark.asyncio
async def test_get_crawler_singleton_and_recycle():
    with patch("wet_mcp.sources.crawler.AsyncWebCrawler", new=MockAsyncWebCrawler):
        # First call creates crawler
        c1 = await crawler._get_crawler(stealth=True)
        assert c1 is not None
        assert crawler._crawler_instance is c1
        assert crawler._crawler_stealth is True

        # Second call with same stealth returns same instance
        c2 = await crawler._get_crawler(stealth=True)
        assert c2 is c1

        # Call with different stealth recycles browser
        c3 = await crawler._get_crawler(stealth=False)
        assert c3 is not c1
        assert crawler._crawler_stealth is False
        c1.__aexit__.assert_called()


@pytest.mark.asyncio
async def test_get_crawler_retry_logic():
    # Mock crawler that fails on first __aenter__ but succeeds on second
    class FlakyMockCrawler(MockAsyncWebCrawler):
        _effect_idx = 0

        def get_effect(self):
            if FlakyMockCrawler._effect_idx == 0:
                FlakyMockCrawler._effect_idx += 1
                raise Exception("Init failed")
            return self

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.__aenter__ = AsyncMock(side_effect=self.get_effect)

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", new=FlakyMockCrawler),
        patch("wet_mcp.sources.crawler._cleanup_browser_data_dir") as mock_cleanup,
    ):
        c = await crawler._get_crawler(stealth=True)
        assert c is not None
        assert mock_cleanup.called


@pytest.mark.asyncio
async def test_get_crawler_total_failure():
    # Mock crawler that always fails
    class FailingMockCrawler(MockAsyncWebCrawler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.__aenter__ = AsyncMock(side_effect=Exception("Always fails"))

    with patch("wet_mcp.sources.crawler.AsyncWebCrawler", new=FailingMockCrawler):
        with pytest.raises(Exception, match="Always fails"):
            await crawler._get_crawler(stealth=True)


@pytest.mark.asyncio
async def test_shutdown_crawler():
    with patch("wet_mcp.sources.crawler.AsyncWebCrawler", new=MockAsyncWebCrawler):
        c = await crawler._get_crawler(stealth=True)
        assert crawler._crawler_instance is not None

        await crawler.shutdown_crawler()
        assert crawler._crawler_instance is None
        c.__aexit__.assert_called()


@pytest.mark.asyncio
async def test_shutdown_crawler_exception_handled():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.__aexit__.side_effect = Exception("Shutdown error")

    with patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler):
        crawler._crawler_instance = mock_crawler  # type: ignore
        await crawler.shutdown_crawler()
        assert crawler._crawler_instance is None


def test_cleanup_browser_data_dir():
    with patch("shutil.rmtree") as mock_rmtree:
        # Create a dummy dir to pass exists() check
        with patch("pathlib.Path.exists", return_value=True):
            crawler._cleanup_browser_data_dir()
            assert mock_rmtree.called


def test_cleanup_browser_data_dir_exception():
    with patch("shutil.rmtree", side_effect=Exception("rmtree failed")):
        with patch("pathlib.Path.exists", return_value=True):
            # Should not raise
            crawler._cleanup_browser_data_dir()


def test_browser_config_docker_env():
    with patch("os.path.exists", return_value=True):
        config = crawler._browser_config(stealth=True)
        assert "--no-sandbox" in config.extra_args

    with patch("os.environ.get", return_value="1"):
        config = crawler._browser_config(stealth=True)
        assert "--disable-dev-shm-usage" in config.extra_args


def test_get_semaphore():
    sem1 = crawler._get_semaphore()
    sem2 = crawler._get_semaphore()
    assert sem1 is sem2
    assert isinstance(sem1, asyncio.Semaphore)


@pytest.mark.asyncio
async def test_get_crawler_recycle_exception():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.__aexit__.side_effect = Exception("aexit failed")
    with patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler):
        # We need to manually set it so recycle logic triggers
        crawler._crawler_instance = mock_crawler  # type: ignore
        crawler._crawler_stealth = True
        await crawler._get_crawler(stealth=False)
        mock_crawler.__aexit__.assert_called()


@pytest.mark.asyncio
async def test_crawl_visited_and_depth():
    mock_crawler = MockAsyncWebCrawler()
    # Return links that point to already visited page and new page
    mock_crawler.arun.return_value = MockCrawlerResult(
        links={
            "internal": [
                {"href": "https://safe.com"},
                {"href": "http://safe.com/deep"},
                {"href": "http://safe.com/deep2"},
            ]
        }
    )

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
        patch("playwright.async_api.async_playwright"),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.crawl(["https://safe.com"], depth=1, max_pages=5)
        json.loads(result_json)
        # Should not get stuck in infinite loop, should hit the visited continue


@pytest.mark.asyncio
async def test_sitemap_visited_and_depth():
    mock_crawler = MockAsyncWebCrawler()
    mock_crawler.arun.return_value = MockCrawlerResult(
        links={
            "internal": [{"href": "https://safe.com"}, {"href": "http://safe.com/deep"}]
        }
    )

    with (
        patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
        patch("playwright.async_api.async_playwright"),
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
    ):
        result_json = await crawler.sitemap(["https://safe.com"], depth=1, max_pages=5)
        json.loads(result_json)


@pytest.mark.asyncio
async def test_download_media_redirect_no_location(tmp_path):
    mock_client = AsyncMock()
    mock_client.get.return_value = MockResponse(is_redirect=True, headers={})

    with (
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
        patch(
            "httpx.AsyncClient",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock()
            ),
        ),
    ):
        result_json = await crawler.download_media(
            ["http://safe.com/image.jpg"], str(tmp_path)
        )
        data = json.loads(result_json)
        assert len(data) == 1


@pytest.mark.asyncio
async def test_download_media_too_many_redirects(tmp_path):
    mock_client = AsyncMock()
    mock_client.get.return_value = MockResponse(
        is_redirect=True, headers={"Location": "/loop.jpg"}
    )

    with (
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
        patch(
            "httpx.AsyncClient",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_client), __aexit__=AsyncMock()
            ),
        ),
    ):
        result_json = await crawler.download_media(
            ["http://safe.com/loop.jpg"], str(tmp_path)
        )
        data = json.loads(result_json)
        assert len(data) == 1
