"""Tests for list_media functionality."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wet.sources.crawler import list_media


@pytest.mark.asyncio
async def test_list_media_success_all(mock_crawler_instance):
    """Test retrieving all media types."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.media = {
        "images": ["img1.jpg", "img2.jpg"],
        "videos": ["vid1.mp4"],
        "audios": ["aud1.mp3"],
    }

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await list_media(url="https://example.com", media_type="all")

    results = json.loads(result_json)
    assert "images" in results
    assert "videos" in results
    assert "audio" in results
    assert len(results["images"]) == 2
    assert len(results["videos"]) == 1
    assert len(results["audio"]) == 1


@pytest.mark.asyncio
async def test_list_media_type_filter(mock_crawler_instance):
    """Test filtering by media type."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.media = {
        "images": ["img1.jpg", "img2.jpg"],
        "videos": ["vid1.mp4"],
        "audios": ["aud1.mp3"],
    }

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        # Test images only
        result_images_json = await list_media(
            url="https://example.com", media_type="images"
        )
        results_images = json.loads(result_images_json)
        assert "images" in results_images
        assert "videos" not in results_images
        assert "audio" not in results_images

        # Test videos only
        result_videos_json = await list_media(
            url="https://example.com", media_type="videos"
        )
        results_videos = json.loads(result_videos_json)
        assert "videos" in results_videos
        assert "images" not in results_videos
        assert "audio" not in results_videos

        # Test audio only
        result_audio_json = await list_media(
            url="https://example.com", media_type="audio"
        )
        results_audio = json.loads(result_audio_json)
        assert "audio" in results_audio
        assert "images" not in results_audio
        assert "videos" not in results_audio


@pytest.mark.asyncio
async def test_list_media_max_items(mock_crawler_instance):
    """Test max items limit."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.media = {
        "images": [f"img{i}.jpg" for i in range(20)],
    }

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await list_media(
            url="https://example.com", media_type="images", max_items=5
        )

    results = json.loads(result_json)
    assert len(results["images"]) == 5


@pytest.mark.asyncio
async def test_list_media_unsafe_url():
    """Test unsafe URL handling."""
    with patch("wet.sources.crawler.is_safe_url", return_value=False):
        result_json = await list_media(url="https://unsafe.com")

    results = json.loads(result_json)
    assert "error" in results
    assert "Security Alert" in results["error"]


@pytest.mark.asyncio
async def test_list_media_crawler_failure(mock_crawler_instance):
    """Test crawler failure handling."""
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error_message = "Page load failed"

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with (
        patch(
            "wet.sources.crawler._get_crawler",
            new_callable=AsyncMock,
            return_value=mock_crawler_instance,
        ),
        patch(
            "wet.sources.crawler._probe_direct_media",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        result_json = await list_media(url="https://example.com")

    results = json.loads(result_json)
    assert "error" in results
    assert "Page load failed" in results["error"]


@pytest.mark.asyncio
async def test_list_media_empty(mock_crawler_instance):
    """Test handling of empty media results."""
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.media = {}

    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

    with patch(
        "wet.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await list_media(url="https://example.com", media_type="all")

    results = json.loads(result_json)
    assert results == {"images": [], "videos": [], "audio": []}


def _failed_crawl(mock_crawler_instance, message: str = "Blocked by anti-bot"):
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error_message = message
    mock_crawler_instance.arun = AsyncMock(return_value=mock_result)


def _head_client(*, content_type: str | None = None, error: Exception | None = None):
    """A ``safe_httpx_client`` stand-in whose HEAD answers once."""
    response = MagicMock()
    response.headers = {"content-type": content_type} if content_type else {}
    response.url = "https://cdn.example.com/final.webp"
    response.raise_for_status = MagicMock()
    client = MagicMock()
    client.head = AsyncMock(side_effect=error, return_value=response)

    @asynccontextmanager
    async def factory(**_kwargs):
        yield client

    return factory, client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "key", "kind"),
    [
        ("image/webp", "images", "image"),
        ("video/mp4; codecs=avc1", "videos", "video"),
        ("audio/mpeg", "audio", "audio"),
    ],
)
async def test_list_media_direct_media_url(
    mock_crawler_instance, monkeypatch, content_type, key, kind
):
    """A URL that serves a media file itself is listed as that one item.

    The browser renders a bare image/video/audio response as a near-empty
    viewer page, which the crawler rejects; the HEAD probe recovers it.
    """
    _failed_crawl(mock_crawler_instance)
    monkeypatch.setattr("wet.sources.crawler.settings.respect_robots_txt", False)
    factory, client = _head_client(content_type=content_type)

    with (
        patch(
            "wet.sources.crawler._get_crawler",
            new_callable=AsyncMock,
            return_value=mock_crawler_instance,
        ),
        patch("wet.sources.crawler._safe_httpx_client", factory),
    ):
        result_json = await list_media(url="https://example.com/img")

    results = json.loads(result_json)
    assert results[key] == [
        {
            "src": "https://cdn.example.com/final.webp",
            "type": kind,
            "content_type": content_type.split(";")[0],
        }
    ]
    assert sum(len(v) for v in results.values()) == 1
    client.head.assert_awaited_once_with("https://example.com/img")


@pytest.mark.asyncio
async def test_list_media_direct_media_respects_type_filter(
    mock_crawler_instance, monkeypatch
):
    """An image URL asked for videos lists no videos instead of an error."""
    _failed_crawl(mock_crawler_instance)
    monkeypatch.setattr("wet.sources.crawler.settings.respect_robots_txt", False)
    factory, _client = _head_client(content_type="image/png")

    with (
        patch(
            "wet.sources.crawler._get_crawler",
            new_callable=AsyncMock,
            return_value=mock_crawler_instance,
        ),
        patch("wet.sources.crawler._safe_httpx_client", factory),
    ):
        result_json = await list_media(
            url="https://example.com/img", media_type="videos"
        )

    assert json.loads(result_json) == {"videos": []}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "error"),
    [
        ("text/html; charset=utf-8", None),
        (None, None),
        (None, httpx.ConnectError("boom")),
    ],
)
async def test_list_media_failure_kept_when_url_is_not_media(
    mock_crawler_instance, monkeypatch, content_type, error
):
    """Non-media, untyped or unreachable URLs keep the crawler's error."""
    _failed_crawl(mock_crawler_instance, "Page load failed")
    monkeypatch.setattr("wet.sources.crawler.settings.respect_robots_txt", False)
    factory, _client = _head_client(content_type=content_type, error=error)

    with (
        patch(
            "wet.sources.crawler._get_crawler",
            new_callable=AsyncMock,
            return_value=mock_crawler_instance,
        ),
        patch("wet.sources.crawler._safe_httpx_client", factory),
    ):
        result_json = await list_media(url="https://example.com")

    assert json.loads(result_json) == {"error": "Page load failed"}


@pytest.mark.asyncio
async def test_list_media_no_probe_when_robots_respected(
    mock_crawler_instance, monkeypatch
):
    """With robots.txt enforced the failed URL is never fetched again."""
    _failed_crawl(mock_crawler_instance, "robots.txt disallows the URL")
    monkeypatch.setattr("wet.sources.crawler.settings.respect_robots_txt", True)
    factory, client = _head_client(content_type="image/png")

    with (
        patch(
            "wet.sources.crawler._get_crawler",
            new_callable=AsyncMock,
            return_value=mock_crawler_instance,
        ),
        patch("wet.sources.crawler._safe_httpx_client", factory),
    ):
        result_json = await list_media(url="https://example.com/img")

    assert json.loads(result_json) == {"error": "robots.txt disallows the URL"}
    client.head.assert_not_awaited()
