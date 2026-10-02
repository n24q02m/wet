import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp.sources.crawler import _extract_with_markitdown, _is_document_url, extract


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.com/file.pdf", True),
        ("https://example.com/file.DOCX", True),
        ("https://example.com/file.html", False),
        ("https://example.com/path/", False),
        ("https://example.com/file.pptx?query=1", True),
    ],
)
def test_is_document_url(url, expected):
    assert _is_document_url(url) == expected


@pytest.mark.asyncio
async def test_extract_with_markitdown_success():
    url = "https://example.com/test.pdf"
    mock_content = b"PDF content"

    mock_resp = MagicMock()
    mock_resp.content = mock_content
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client

    mock_result = MagicMock()
    mock_result.text_content = "Converted Markdown Content"

    with (
        patch("wet_mcp.sources.crawler._safe_httpx_client", return_value=mock_client),
        patch("markitdown.MarkItDown"),
        patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_thread.return_value = mock_result

        result = await _extract_with_markitdown(url)

        assert result["url"] == url
        assert result["content"] == "Converted Markdown Content"
        assert result["converter"] == "markitdown"
        assert result["title"] == "test"


@pytest.mark.asyncio
async def test_extract_with_markitdown_http_error():
    url = "https://example.com/test.pdf"

    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("HTTP Error")
    mock_client.__aenter__.return_value = mock_client

    with patch("wet_mcp.sources.crawler._safe_httpx_client", return_value=mock_client):
        result = await _extract_with_markitdown(url)

        assert "error" in result
        assert "Document conversion failed" in result["error"]


@pytest.mark.asyncio
async def test_extract_with_markitdown_import_error():
    url = "https://example.com/test.pdf"

    import builtins

    real_import = builtins.__import__

    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "markitdown":
            raise ImportError("Mocked ImportError")
        return real_import(name, globals, locals, fromlist, level)

    with patch("builtins.__import__", side_effect=mock_import):
        result = await _extract_with_markitdown(url)
        assert "error" in result
        assert "markitdown not installed" in result["error"]


@pytest.mark.asyncio
async def test_extract_document_via_process_url(mock_crawler_instance):
    """Test that extract() routes document URLs to markitdown."""
    url = "https://example.com/document.pdf"
    mock_doc_result = {
        "url": url,
        "title": "document",
        "content": "Markitdown Content",
        "converter": "markitdown",
    }

    with (
        patch("wet_mcp.sources.crawler._is_document_url", return_value=True),
        patch(
            "wet_mcp.sources.crawler._extract_with_markitdown", new_callable=AsyncMock
        ) as mock_md,
        patch(
            "wet_mcp.sources.crawler._get_crawler", return_value=mock_crawler_instance
        ),
    ):
        mock_md.return_value = mock_doc_result

        result_json = await extract([url])
        results = json.loads(result_json)

        assert len(results) == 1
        assert results[0]["content"] == "Markitdown Content"
        assert results[0]["converter"] == "markitdown"
        mock_md.assert_called_once_with(url)
        # Ensure browser-based crawler was NOT used for this URL
        mock_crawler_instance.arun.assert_not_called()


@pytest.mark.asyncio
async def test_extract_mixed_urls():
    """Test extract() with a mix of web and document URLs."""
    doc_url = "https://example.com/doc.pdf"
    web_url = "https://example.com/page"

    mock_doc_result = {
        "url": doc_url,
        "content": "PDF content",
        "converter": "markitdown",
    }

    fake_agent = MagicMock()
    fake_agent.scrape = AsyncMock(return_value="# Web Title\n\nWeb content")
    fake_agent.strategy_cache = MagicMock()
    fake_agent.strategy_cache.recommend = AsyncMock(return_value=["basic_http"])

    with (
        patch(
            "wet_mcp.sources.crawler._extract_with_markitdown", new_callable=AsyncMock
        ) as mock_md,
        patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=fake_agent,
        ),
    ):
        mock_md.return_value = mock_doc_result

        result_json = await extract([doc_url, web_url])
        results = json.loads(result_json)

        assert len(results) == 2

        doc_res = next(r for r in results if r["url"] == doc_url)
        web_res = next(r for r in results if r["url"] == web_url)

        # Document path keeps legacy markitdown shape (with raw "content" key)
        assert doc_res["content"] == "PDF content"
        # Web path now uses smart-chunks shape (markdown + clean_text)
        assert "Web content" in web_res["clean_text"]
        assert web_res["metadata"]["title"] == "Web Title"
