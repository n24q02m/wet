import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wet_mcp.sources.docs import (
    _discover_from_crates,
    _discover_from_github_search,
    _discover_from_go,
    _discover_from_hex,
    _discover_from_maven,
    _discover_from_npm,
    _discover_from_nuget,
    _discover_from_packagist,
    _discover_from_pubdev,
    _discover_from_pypi,
    _discover_from_rubygems,
    _fetch_github_readme,
    _filter_framework_paths,
    _filter_i18n_paths,
    _has_excessive_macros,
    _is_i18n_url,
    _probe_docs_url,
    _rst_to_markdown,
    _strip_template_macros,
    _try_github_raw_docs,
    _try_objects_inv,
    _try_sitemap,
    chunk_llms_txt,
    chunk_markdown,
    discover_library,
    fetch_docs_pages,
    try_llms_txt,
)


@pytest.mark.asyncio
async def test_all_registries():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_instance.get.return_value = mock_response

        # npm
        mock_response.json.return_value = {
            "repository": {"url": "git://github.com/a/b.git"},
            "homepage": "http://a.com",
        }
        await _discover_from_npm("test")

        # pypi
        mock_response.json.return_value = {
            "info": {"project_urls": {"Documentation": "http://docs.org"}}
        }
        await _discover_from_pypi("test")

        # crates
        mock_response.json.return_value = {
            "crate": {
                "documentation": "http://docs.rs",
                "repository": "http://github.com",
            }
        }
        await _discover_from_crates("test")

        # go
        mock_response.text = 'href="https://pkg.go.dev/test"'
        await _discover_from_go("test")

        # hex
        mock_response.json.return_value = {
            "meta": {"links": {"GitHub": "http://github.com"}}
        }
        await _discover_from_hex("test")

        # packagist
        mock_response.json.return_value = {
            "packages": {"test": [{"source": {"url": "http://github.com"}}]}
        }
        await _discover_from_packagist("test")

        # pubdev
        mock_response.json.return_value = {
            "latest": {"pubspec": {"homepage": "http://pub.dev"}}
        }
        await _discover_from_pubdev("test")

        # rubygems
        mock_response.json.return_value = {"documentation_uri": "http://docs.ruby"}
        await _discover_from_rubygems("test")

        # nuget
        mock_response.json.return_value = {
            "data": [{"projectUrl": "http://docs.nuget"}]
        }
        await _discover_from_nuget("test")

        # maven
        mock_response.json.return_value = {
            "response": {"docs": [{"g": "com", "a": "test"}]}
        }
        await _discover_from_maven("test")

        # Github search
        mock_response.json.return_value = {
            "items": [
                {
                    "html_url": "http://github.com/test",
                    "homepage": "https://docs.test",
                    "description": "Test",
                }
            ]
        }
        await _discover_from_github_search("test", "python")


@pytest.mark.asyncio
@patch("wet_mcp.sources.docs._get_github_homepage")
@patch("wet_mcp.sources.docs._probe_docs_url")
async def test_discover_library(mock_probe, mock_get_gh):
    mock_probe.return_value = "https://docs.test"
    mock_get_gh.return_value = "http://gh"

    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "test",
            "repository": {"url": "git://github.com/a/b.git"},
            "homepage": "http://docs.npm",
        }
        mock_instance.get.return_value = mock_response

        res = await discover_library("test", "javascript")
        assert res is not None
        assert res["homepage"] == "https://docs.test"


@pytest.mark.asyncio
async def test_probe_docs_url():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = (
            "<html><head><title>Docs</title></head><body></body></html>"
        )
        mock_instance.get.return_value = mock_response
        mock_instance.head.return_value = mock_response

        await _probe_docs_url("http://github.com/a/b", "b")


@pytest.mark.asyncio
async def test_try_llms_txt():
    # Fix existing test to use the safe httpx client and return sufficient text
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "A" * 201
        mock_instance.get.return_value = mock_response

        res = await try_llms_txt("https://docs.test")
        assert res == "A" * 201


@pytest.mark.asyncio
async def test_try_llms_txt_edge_cases():
    # Empty url
    assert await try_llms_txt("") is None

    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        # Test < 200 chars
        mock_response_short = MagicMock()
        mock_response_short.status_code = 200
        mock_response_short.text = "Short text"
        mock_instance.get.return_value = mock_response_short
        assert await try_llms_txt("https://docs.test") is None

        # Test DOCTYPE start
        mock_response_doctype = MagicMock()
        mock_response_doctype.status_code = 200
        mock_response_doctype.text = "<!DOCTYPE html>\n<html>" + "A" * 200
        mock_instance.get.return_value = mock_response_doctype
        assert await try_llms_txt("https://docs.test") is None

        # Test non-200 status code
        mock_response_err = MagicMock()
        mock_response_err.status_code = 404
        mock_instance.get.return_value = mock_response_err
        assert await try_llms_txt("https://docs.test") is None

        # Test toc only (for llms.txt)
        with patch("wet_mcp.sources.docs._is_toc_only", return_value=True):
            mock_response_toc = MagicMock()
            mock_response_toc.status_code = 200
            mock_response_toc.text = "TOC links" + "A" * 200

            # First request (llms-full.txt) fails/not found, second request (llms.txt) returns TOC
            mock_instance.get.side_effect = [
                MagicMock(status_code=404),
                mock_response_toc,
            ]
            assert await try_llms_txt("https://docs.test") is None

        # Test exception handling (e.g. connection error)
        mock_instance.get.side_effect = Exception("Network error")
        assert await try_llms_txt("https://docs.test") is None


@pytest.mark.asyncio
async def test_fetch_docs_pages():
    with patch(
        "wet_mcp.sources.crawler.extract", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.return_value = json.dumps(
            [
                {
                    "url": "http://docs.test/page1",
                    "content": "## Docs",
                    "title": "Docs",
                    "metadata": {"links": ["http://docs.test/page2"]},
                }
            ]
        )

        with patch(
            "wet_mcp.sources.docs._try_sitemap", new_callable=AsyncMock
        ) as mock_sitemap:
            mock_sitemap.return_value = ["http://docs.test/page3"]

            with patch(
                "wet_mcp.sources.docs._try_objects_inv", new_callable=AsyncMock
            ) as mock_objects:
                mock_objects.return_value = []

                res = await fetch_docs_pages("https://docs.test", query="test")
                assert len(res) > 0


def test_sync_functions():
    chunk_markdown("## Test\n\nContent", "https://docs.test", "test")  # type: ignore
    chunk_llms_txt("## Section 1\nContent 1", "https://docs.test")


@pytest.mark.asyncio
async def test_try_github_raw_docs_success():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_resp_branch = MagicMock()
        mock_resp_branch.status_code = 200
        mock_resp_branch.json.return_value = {"default_branch": "main"}

        mock_resp_tree = MagicMock()
        mock_resp_tree.status_code = 200
        mock_resp_tree.json.return_value = {
            "tree": [
                {"type": "blob", "path": "docs/guide.md"},
                {"type": "blob", "path": "docs/api.md"},
                {"type": "blob", "path": "docs/tutorial.md"},
                {"type": "blob", "path": "docs/advanced.md"},
                {"type": "blob", "path": "docs/faq.md"},
                {"type": "blob", "path": "README.md"},
            ]
        }

        mock_resp_raw = MagicMock()
        mock_resp_raw.status_code = 200
        mock_resp_raw.text = (
            "This is a valid long text document without heavy templates " * 10
        )

        mock_instance.get.side_effect = [
            mock_resp_branch,
            mock_resp_tree,
            mock_resp_raw,
            mock_resp_raw,
            mock_resp_raw,
            mock_resp_raw,
            mock_resp_raw,
            mock_resp_raw,
        ]

        res = await _try_github_raw_docs("https://github.com/owner/repo", max_files=2)
        assert res is not None
        assert len(res) == 2


@pytest.mark.asyncio
async def test_try_github_raw_docs_failure():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_resp_branch = MagicMock()
        mock_resp_branch.status_code = 404
        mock_instance.get.return_value = mock_resp_branch

        res = await _try_github_raw_docs("https://github.com/owner/repo", max_files=2)
        assert res is None


@pytest.mark.asyncio
async def test_try_sitemap_success():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://docs.test/guide</loc></url>
  <url><loc>https://docs.test/api</loc></url>
</urlset>"""
        mock_instance.get.return_value = mock_resp

        res = await _try_sitemap("https://docs.test")
        assert len(res) == 2
        assert "https://docs.test/guide" in res


@pytest.mark.asyncio
async def test_try_sitemap_index():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_resp_idx = MagicMock()
        mock_resp_idx.status_code = 200
        mock_resp_idx.text = """<sitemapindex><sitemap><loc>https://docs.test/sub.xml</loc></sitemap></sitemapindex>"""

        mock_resp_sub = MagicMock()
        mock_resp_sub.status_code = 200
        mock_resp_sub.text = (
            """<urlset><url><loc>https://docs.test/guide</loc></url></urlset>"""
        )

        mock_instance.get.side_effect = [mock_resp_idx, mock_resp_sub]

        res = await _try_sitemap("https://docs.test")
        assert "https://docs.test/guide" in res


@pytest.mark.asyncio
async def test_try_objects_inv_success():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = httpx.URL("https://docs.test/")

        import zlib

        header = b"# Sphinx inventory version 2\n# Project: test\n# Version: 1.0\n# The remainder of this file is compressed using zlib.\n"
        body = b"guide std:doc -1 guide.html Guide\napi std:doc -1 api.html API\nchangelog std:doc -1 changelog.html Log"
        compressed = zlib.compress(body)
        mock_resp.content = header + compressed

        mock_instance.get.return_value = mock_resp

        res = await _try_objects_inv("https://docs.test")
        assert "https://docs.test/guide.html" in res
        assert "https://docs.test/api.html" in res


@pytest.mark.asyncio
async def test_fetch_docs_pages_thorough():
    with patch(
        "wet_mcp.sources.crawler.extract", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.side_effect = [
            json.dumps(
                [
                    {
                        "url": "http://docs.test/",
                        "content": "## Root",
                        "title": "Root",
                        "links": {"internal": [{"href": "/page1"}, "/page2"]},
                    }
                ]
            ),
            json.dumps(
                [
                    {
                        "url": "http://docs.test/page1",
                        "content": "## Page 1",
                        "title": "Page 1",
                        "links": {"internal": []},
                    },
                    {
                        "url": "http://docs.test/page2",
                        "content": "## Page 2",
                        "title": "Page 2",
                        "links": {"internal": []},
                    },
                ]
            ),
        ]

        with patch(
            "wet_mcp.sources.docs._try_sitemap", new_callable=AsyncMock
        ) as mock_sitemap:
            mock_sitemap.return_value = []

            with patch(
                "wet_mcp.sources.docs._try_objects_inv", new_callable=AsyncMock
            ) as mock_objects:
                mock_objects.return_value = []

                res = await fetch_docs_pages("https://docs.test", max_pages=10)
                assert len(res) == 3
                urls = [r["url"] for r in res]
                assert "http://docs.test/" in urls
                assert "http://docs.test/page1" in urls
                assert "http://docs.test/page2" in urls


def test_rst_to_markdown():
    rst = """
Heading
=======

Some text with :ref:`link` and ``code``.

.. code-block:: python

    def foo():
        pass

.. note::
   This is a note.

Literal block::

    def bar():
        pass
"""
    md = _rst_to_markdown(rst)
    assert "# Heading" in md
    assert "`link`" in md
    assert "`code`" in md
    assert "```python" in md
    assert "def foo():" in md
    assert "> **Note:**" in md
    assert "```" in md
    assert "def bar():" in md


def test_filter_framework_paths():
    paths = [
        "docs/framework/react/guide.md",
        "docs/framework/vue/guide.md",
        "docs/general.md",
    ]
    res = _filter_framework_paths(paths, "@tanstack/react-query")
    assert "docs/framework/react/guide.md" in res
    assert "docs/framework/vue/guide.md" not in res

    res = _filter_framework_paths(paths, "something")
    assert len(res) == 3


def test_filter_i18n_paths():
    paths = [
        "docs/en/guide.md",
        "docs/de/guide.md",
        "docs/ja/guide.md",
        "docs/api/foo.md",
    ]
    res = _filter_i18n_paths(paths)
    assert "docs/en/guide.md" in res
    assert "docs/de/guide.md" not in res
    assert "docs/api/foo.md" in res

    assert len(_filter_i18n_paths(["docs/guide.md"])) == 1


def test_has_excessive_macros():
    content = "hello\n" * 10
    assert not _has_excessive_macros(content)

    macro_content = "hello {{ macro }}\n" * 3 + "hello\n" * 5
    assert _has_excessive_macros(macro_content)


def test_strip_template_macros():
    content = "keep\n{{ strip }}\nkeep"
    res = _strip_template_macros(content)
    assert "strip" not in res
    assert "keep" in res


def test_is_i18n_url():
    assert _is_i18n_url("/ja/6.0/tutorial/", "/en/6.0/")
    assert not _is_i18n_url("/en/6.0/tutorial/", "/en/6.0/")
    assert not _is_i18n_url("/docs/tutorial/", "/docs/")
    assert _is_i18n_url("/de/docs/", "/")


@pytest.mark.asyncio
async def test_fetch_github_readme():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "# README\n\nContent" * 10
        mock_instance.get.return_value = mock_resp

        res = await _fetch_github_readme("https://github.com/owner/repo")
        assert res is not None
        assert len(res) > 0


@pytest.mark.asyncio
async def test_probe_docs_url_readthedocs():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "This is a very long text " * 100
        mock_resp.url = httpx.URL("https://pytest.readthedocs.io/en/latest/")

        mock_inv = MagicMock()
        mock_inv.status_code = 200
        import zlib

        header = b"# Sphinx inventory version 2\n# Project: pytest\n# Version: 1.0\n# The remainder of this file is compressed using zlib.\n"
        body = b"guide std:doc -1 guide.html Guide\n" * 100
        compressed = zlib.compress(body)
        mock_inv.content = header + compressed

        mock_instance.get.side_effect = [
            mock_resp,
            mock_inv,
            mock_resp,
            mock_inv,
            mock_resp,
            mock_inv,
        ]

        res = await _probe_docs_url("https://pytest.org", "pytest", "pypi")
        assert "pytest.readthedocs.io" in res or "pytest.org" in res


@pytest.mark.asyncio
async def test_probe_docs_url_subdomain():
    with patch("wet_mcp.sources.docs._safe_httpx_client") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = mock_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "This is a very long text " * 100
        mock_resp.url = httpx.URL("https://docs.pytest.org/")

        mock_inv = MagicMock()
        mock_inv.status_code = 404

        mock_instance.get.side_effect = [mock_resp, mock_inv, mock_resp, mock_inv]

        res = await _probe_docs_url("https://pytest.org", "pytest", "pypi")
        assert "docs.pytest.org" in res


def test_strip_nav_menus():
    content = (
        """# Main\nIntro\n## Nav 1\n## Nav 2\n## Nav 3\n## Nav 4\n## Nav 5\nContent\n"""
    )
    chunks = chunk_markdown(content, "http://test", min_chunk_size=10)
    stripped = "".join(c["content"] for c in chunks)
    assert "Nav 5" not in stripped
    assert "Intro" in stripped
    assert "Content" in stripped


def test_chunk_markdown_large():
    content = (
        """# Title\n## Section 1\n"""
        + ("A" * 500 + "\n\n") * 10
        + """## Section 2\n"""
        + ("B" * 500 + "\n\n") * 10
    )
    chunks = chunk_markdown(content, "http://test")
    assert len(chunks) > 2
    for c in chunks:
        assert c["url"] == "http://test"
        assert c["title"] in ("Title", "Section 1", "Section 2")


@pytest.mark.asyncio
async def test_fetch_docs_pages_reads_smart_chunks_shape():
    """Web pages come back as smart-chunks, not the markitdown shape.

    ``crawler.extract`` returns ``markdown`` / ``clean_text`` / ``metadata``
    for scraped pages; only its document branch emits ``content`` + a
    top-level ``title``. Reading the document keys alone silently dropped
    every scraped page, so the Tier 1 index produced zero chunks.
    """
    with patch(
        "wet_mcp.sources.crawler.extract", new_callable=AsyncMock
    ) as mock_extract:
        mock_extract.return_value = json.dumps(
            [
                {
                    "url": "https://docs.test/",
                    "markdown": "## Overview\n\nThe library does things.",
                    "clean_text": "Overview The library does things.",
                    "structured_data": [],
                    "code_blocks": [],
                    "metadata": {"title": "Overview", "headings": []},
                }
            ]
        )
        with (
            patch(
                "wet_mcp.sources.docs._try_sitemap", new_callable=AsyncMock
            ) as mock_sitemap,
            patch(
                "wet_mcp.sources.docs._try_objects_inv", new_callable=AsyncMock
            ) as mock_objects,
        ):
            mock_sitemap.return_value = []
            mock_objects.return_value = []
            res = await fetch_docs_pages("https://docs.test/")

    assert len(res) == 1
    assert res[0]["title"] == "Overview"
    assert res[0]["content"].startswith("## Overview")
