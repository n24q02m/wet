import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wet_mcp.sources.crawler import download_media


@pytest.mark.asyncio
async def test_download_media_success(tmp_path):
    """Test successful download of media files."""
    mock_content = b"test content"

    mock_response = MagicMock()
    mock_response.is_redirect = False
    mock_response.content = mock_content
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {}

    # The client used inside the with block
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    # The context manager instance returned by httpx.AsyncClient()
    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__.return_value = mock_client
    mock_client_instance.__aexit__.return_value = None

    # The class/constructor httpx.AsyncClient
    mock_client_cls = MagicMock(return_value=mock_client_instance)

    url = "http://example.com/file.txt"
    output_dir = str(tmp_path)

    with patch("wet_mcp.sources.crawler._safe_httpx_client", mock_client_cls):
        result_json = await download_media([url], output_dir)

    results = json.loads(result_json)

    # Verify file was written
    expected_file = tmp_path / "file.txt"
    assert expected_file.exists()
    assert expected_file.read_bytes() == mock_content

    # Verify result JSON
    assert len(results) == 1
    assert results[0]["url"] == url
    assert results[0]["path"] == str(expected_file)
    assert results[0]["size"] == len(mock_content)

    # Verify client usage
    mock_client.get.assert_called_once()
    args, kwargs = mock_client.get.call_args
    assert args[0] == url


@pytest.mark.asyncio
async def test_download_media_uses_ssrf_safe_transport(tmp_path):
    """Media downloads must keep web-core's SSRF-protected transport."""
    mock_response = MagicMock()
    mock_response.is_redirect = False
    mock_response.content = b"safe content"
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__.return_value = mock_client
    mock_client_instance.__aexit__.return_value = None
    mock_client_factory = MagicMock(return_value=mock_client_instance)

    with patch("wet_mcp.sources.crawler._safe_httpx_client", mock_client_factory):
        await download_media(["http://example.com/file.txt"], str(tmp_path))

    assert "transport" not in mock_client_factory.call_args.kwargs


@pytest.mark.asyncio
async def test_download_media_protocol_relative(tmp_path):
    """Test handling of protocol-relative URLs."""
    mock_content = b"image data"

    mock_response = MagicMock()
    mock_response.is_redirect = False
    mock_response.content = mock_content
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__.return_value = mock_client
    mock_client_instance.__aexit__.return_value = None

    mock_client_cls = MagicMock(return_value=mock_client_instance)

    url = "//example.com/image.jpg"
    output_dir = str(tmp_path)

    with patch("wet_mcp.sources.crawler._safe_httpx_client", mock_client_cls):
        result_json = await download_media([url], output_dir)

    results = json.loads(result_json)

    # Verify file was written
    expected_file = tmp_path / "image.jpg"
    assert expected_file.exists()
    assert expected_file.read_bytes() == mock_content

    # Verify client called with https prefix
    mock_client.get.assert_called_once()
    args, kwargs = mock_client.get.call_args
    assert args[0] == "https://example.com/image.jpg"

    assert results[0]["url"] == url
    assert results[0]["path"] == str(expected_file)


@pytest.mark.asyncio
async def test_download_media_http_error(tmp_path):
    """Test handling of HTTP errors during download."""
    mock_response = MagicMock()
    mock_response.is_redirect = False
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404 Not Found",
        request=httpx.Request("GET", "http://example.com/missing.txt"),
        response=httpx.Response(
            404, request=httpx.Request("GET", "http://example.com/missing.txt")
        ),
    )

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__.return_value = mock_client
    mock_client_instance.__aexit__.return_value = None

    mock_client_cls = MagicMock(return_value=mock_client_instance)

    url = "http://example.com/missing.txt"

    with patch("wet_mcp.sources.crawler._safe_httpx_client", mock_client_cls):
        result_json = await download_media([url], str(tmp_path))

    results = json.loads(result_json)

    assert len(results) == 1
    assert results[0]["url"] == url
    assert "error" in results[0]
    assert "404 Not Found" in results[0]["error"]

    # File should not exist
    assert not (tmp_path / "missing.txt").exists()


@pytest.mark.asyncio
async def test_download_media_file_write_error(tmp_path):
    """Test handling of file write errors."""
    mock_content = b"test content"

    mock_response = MagicMock()
    mock_response.is_redirect = False
    mock_response.content = mock_content
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    mock_client_instance = AsyncMock()
    mock_client_instance.__aenter__.return_value = mock_client
    mock_client_instance.__aexit__.return_value = None

    mock_client_cls = MagicMock(return_value=mock_client_instance)

    url = "http://example.com/file.txt"

    # Mock Path.write_bytes to raise PermissionError
    # We need to patch pathlib.Path.write_bytes but since it's used via an instance method,
    # we patch the class method on the Path object returned or patch widely.
    # However, 'download_media' uses 'await asyncio.to_thread(filepath.write_bytes, response.content)'
    # The 'filepath' is a concrete Path object (PosixPath or WindowsPath).
    # Patching 'pathlib.Path.write_bytes' works for all instances.

    with patch("wet_mcp.sources.crawler._safe_httpx_client", mock_client_cls):
        with patch(
            "pathlib.Path.write_bytes", side_effect=PermissionError("Access denied")
        ):
            result_json = await download_media([url], str(tmp_path))

    results = json.loads(result_json)

    assert len(results) == 1
    assert results[0]["url"] == url
    assert "error" in results[0]
    assert "Access denied" in results[0]["error"]
