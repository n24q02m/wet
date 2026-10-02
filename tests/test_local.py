"""Local functionality test for wet-mcp (no SearXNG required).

Tests extract, sitemap, list_media, and help tools.
Run with: uv run python tests/test_local.py
"""

import asyncio
import json
import sys

import pytest
from loguru import logger

pytestmark = pytest.mark.integration

logger.remove()
logger.add(sys.stdout, level="INFO")


async def test_extract():
    """Test content extraction from example.com."""
    from wet_mcp.sources.crawler import extract

    print("\n" + "=" * 50)
    print("TEST 1: Extract (example.com)")
    print("=" * 50)

    try:
        result = await extract(
            urls=["https://example.com"],
            format="markdown",
            stealth=False,
        )
        data = json.loads(result)

        if isinstance(data, list) and len(data) > 0:
            page = data[0]
            if "error" in page:
                print(f"  ERROR: {page['error']}")
                return False

            title = page.get("title", "")
            content = page.get("content", "")
            print(f"  Title: {title}")
            print(f"  Content: {len(content)} chars")
            print(f"  Preview: {content[:200]}...")
            return len(content) > 50
        return False
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return False


async def test_sitemap():
    """Test sitemap/map discovery."""
    from wet_mcp.sources.crawler import sitemap

    print("\n" + "=" * 50)
    print("TEST 2: Sitemap (example.com)")
    print("=" * 50)

    try:
        result = await sitemap(
            urls=["https://example.com"],
            depth=1,
            max_pages=5,
        )
        data = json.loads(result)

        if isinstance(data, list):
            print(f"  Found {len(data)} URLs")
            for item in data[:5]:
                print(f"    - {item.get('url', '')}")
            return len(data) > 0
        return False
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return False


async def test_list_media():
    """Test media listing from a page with images."""
    from wet_mcp.sources.crawler import list_media

    print("\n" + "=" * 50)
    print("TEST 3: List Media (wikipedia)")
    print("=" * 50)

    try:
        result = await list_media(
            url="https://en.wikipedia.org/wiki/Python_(programming_language)",
            media_type="images",
            max_items=5,
        )
        data = json.loads(result)

        if "error" in data:
            print(f"  ERROR: {data['error']}")
            return False

        images = data.get("images", [])
        print(f"  Found {len(images)} images")
        for img in images[:3]:
            src = img.get("src", "") if isinstance(img, dict) else str(img)
            print(f"    - {src[:80]}...")
        return len(images) > 0
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return False


async def test_help():
    """Test help tool documentation."""
    from wet_mcp.server import help

    print("\n" + "=" * 50)
    print("TEST 4: Help Tool")
    print("=" * 50)

    try:
        for tool_name in ["search", "extract", "media", "config"]:
            result = await help(tool_name)
            has_content = len(result) > 50 and "Error" not in result
            status = "OK" if has_content else "FAIL"
            print(f"  help('{tool_name}'): {len(result)} chars [{status}]")

        return True
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return False


async def test_extract_tool():
    """Test the extract() tool with extract action (full MCP tool path)."""
    from wet_mcp.server import extract

    print("\n" + "=" * 50)
    print("TEST 5: extract() tool - extract action")
    print("=" * 50)

    try:
        result = await extract(
            action="extract",
            urls=["https://httpbin.org/html"],
            format="markdown",
            stealth=False,
        )
        data = json.loads(result)

        if isinstance(data, list) and len(data) > 0:
            page = data[0]
            if "error" in page:
                print(f"  ERROR: {page['error']}")
                return False

            print(f"  Title: {page.get('title', '')}")
            print(f"  Content: {len(page.get('content', ''))} chars")
            return len(page.get("content", "")) > 20
        return False
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return False


async def test_search_fallback():
    """Test search() action when no SearXNG (should return error gracefully)."""
    from wet_mcp.server import search

    print("\n" + "=" * 50)
    print("TEST 6: search() tool - search (no SearXNG)")
    print("=" * 50)

    try:
        result = await search(
            action="search",
            query="python programming",
        )
        data = json.loads(result)
        # On Windows without SearXNG, should get a connection error (not crash)
        if "error" in data:
            print(f"  Expected error (no SearXNG): {data['error'][:100]}")
            return True  # Graceful error = pass
        else:
            print(f"  Got results: {data.get('total', 0)}")
            return True
    except Exception as e:
        print(f"  EXCEPTION (should be handled): {e}")
        return False


async def main():
    """Run all local tests."""
    print("#" * 50)
    print("# WET MCP - Local Functionality Tests")
    print("# (No SearXNG required)")
    print("#" * 50)

    results = {}

    results["extract"] = await test_extract()
    results["sitemap"] = await test_sitemap()
    results["list_media"] = await test_list_media()
    results["help"] = await test_help()
    results["extract_tool"] = await test_extract_tool()
    results["search_fallback"] = await test_search_fallback()

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(results.values())
    print(f"\n{'All tests passed!' if all_passed else 'Some tests failed!'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
