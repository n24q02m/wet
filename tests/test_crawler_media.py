"""Tests for list_media functionality."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp.sources.crawler import list_media


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
        "wet_mcp.sources.crawler._get_crawler",
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
        "wet_mcp.sources.crawler._get_crawler",
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
        "wet_mcp.sources.crawler._get_crawler",
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
    with patch("wet_mcp.sources.crawler.is_safe_url", return_value=False):
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

    with patch(
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
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
        "wet_mcp.sources.crawler._get_crawler",
        new_callable=AsyncMock,
        return_value=mock_crawler_instance,
    ):
        result_json = await list_media(url="https://example.com", media_type="all")

    results = json.loads(result_json)
    assert results == {"images": [], "videos": [], "audio": []}
