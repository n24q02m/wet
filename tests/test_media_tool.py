from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from structured import payload, text

from wet_mcp.server import media


@pytest.fixture
def mock_settings():
    with patch("wet_mcp.server.settings") as mock_settings:
        mock_settings.tool_timeout = 0  # Disable timeout for faster tests
        mock_settings.download_dir = "/tmp/downloads"
        mock_settings.log_level = "INFO"
        yield mock_settings


@pytest.mark.asyncio
async def test_media_list_success(mock_settings):
    """Test media list action successfully calls list_media."""
    mock_list_media = AsyncMock(return_value='{"images": []}')

    with patch("wet_mcp.server.list_media", mock_list_media):
        result = await media(
            action="list", url="http://example.com", media_type="images", max_items=5
        )

        mock_list_media.assert_called_once_with(
            url="http://example.com", media_type="images", max_items=5
        )
        assert payload(result)["images"] == []
        assert "<untrusted_media_content>" in text(result)
        assert "[SECURITY:" in text(result)


@pytest.mark.asyncio
async def test_media_list_missing_url():
    """Test media list action fails without url."""
    result = await media(action="list")
    assert "Error: url is required for list action" in text(result)


@pytest.mark.asyncio
async def test_media_download_success(mock_settings):
    """Test media download action successfully calls download_media."""
    mock_download_media = AsyncMock(return_value='["file1.jpg"]')

    # output_dir must be within the configured download_dir
    sub_dir = "/tmp/downloads/images"

    with patch("wet_mcp.sources.crawler.download_media", mock_download_media):
        result = await media(
            action="download",
            media_urls=["http://example.com/img.jpg"],
            output_dir=sub_dir,
        )

        mock_download_media.assert_called_once_with(
            media_urls=["http://example.com/img.jpg"],
            output_dir=str(Path(sub_dir).expanduser().resolve()),
        )
        assert payload(result)["results"] == ["file1.jpg"]
        assert "<untrusted_media_content>" in text(result)


@pytest.mark.asyncio
async def test_media_download_outside_download_dir(mock_settings):
    """Test media download rejects output_dir outside the configured download_dir."""
    result = await media(
        action="download",
        media_urls=["http://example.com/img.jpg"],
        output_dir="/etc/evil",
    )
    assert "Security Alert" in text(result)


@pytest.mark.asyncio
async def test_media_download_default_dir(mock_settings):
    """Test media download action uses default directory if not provided."""
    mock_download_media = AsyncMock(return_value='["file1.jpg"]')

    with patch("wet_mcp.sources.crawler.download_media", mock_download_media):
        result = await media(
            action="download", media_urls=["http://example.com/img.jpg"]
        )

        expected_dir = str(Path(mock_settings.download_dir).expanduser().resolve())
        mock_download_media.assert_called_once_with(
            media_urls=["http://example.com/img.jpg"],
            output_dir=expected_dir,
        )
        assert payload(result)["results"] == ["file1.jpg"]
        assert "<untrusted_media_content>" in text(result)


@pytest.mark.asyncio
async def test_media_download_missing_urls():
    """Test media download action fails without media_urls."""
    result = await media(action="download")
    assert "Error: media_urls is required for download action" in text(result)


@pytest.mark.asyncio
async def test_media_analyze_returns_unknown_action_post_removal(mock_settings):
    """Phase 3 Task 5 BREAKING: analyze removed -- routes to unknown-action."""
    mock_analyze_media = AsyncMock(return_value="Analysis result")

    with patch("wet_mcp.llm.analyze_media", mock_analyze_media):
        result = await media(
            action="analyze", url="/path/to/image.jpg", prompt="Describe it"
        )

        mock_analyze_media.assert_not_called()
        assert "Unknown action 'analyze'" in text(result)
        assert "removed in wet v2.0.0" in text(result)
        assert "imagine-mcp" in text(result)


@pytest.mark.asyncio
async def test_media_analyze_no_url_still_unknown_action():
    """Removal: analyze without url still routes through unknown-action."""
    result = await media(action="analyze")
    assert "Unknown action 'analyze'" in text(result)
    assert "imagine-mcp" in text(result)


@pytest.mark.asyncio
async def test_media_download_adds_extension_from_content_type(mock_settings, tmp_path):
    """Test download adds file extension from Content-Type when filename has none."""
    import json

    import httpx

    # Mock a response with Content-Type but no extension in URL path
    mock_response = httpx.Response(
        200,
        content=b"fake-png-data",
        headers={"Content-Type": "image/png"},
        request=httpx.Request("GET", "https://example.com/image/photo"),
    )

    async def mock_get(url, **kwargs):
        return mock_response

    mock_client = AsyncMock()
    mock_client.get = mock_get

    with (
        patch("wet_mcp.sources.crawler.is_safe_url", return_value=True),
        patch("wet_mcp.sources.crawler._safe_httpx_client") as MockClient,
        patch("wet_mcp.sources.crawler.settings") as crawler_settings,
    ):
        crawler_settings.crawler_timeout = 30
        # Use tmp_path as output dir to capture real writes
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from wet_mcp.sources.crawler import download_media

        result_str = await download_media(
            media_urls=["https://example.com/image/photo"],
            output_dir=str(tmp_path),
        )
        result = json.loads(result_str)
        assert len(result) == 1
        assert "path" in result[0]
        # Filename should have .png extension inferred from Content-Type
        assert result[0]["path"].endswith(".png")


@pytest.mark.asyncio
async def test_media_unknown_action():
    """Test media action with unknown action."""
    result = await media(action="unknown_action")
    assert "Error:" in text(result) and "unknown_action" in text(result)
    # Phase 3 v2.0.0 BREAKING: analyze removed from valid_actions list.
    assert "list" in text(result) and "download" in text(result)
    assert "analyze" not in text(result)
