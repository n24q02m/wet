"""Integration tests for WET MCP Server.

Run with: uv run python tests/test_integration.py
"""

import asyncio
import json
import sys

import pytest
from loguru import logger

pytestmark = pytest.mark.integration

logger.remove()
logger.add(sys.stdout, level="INFO")


async def test_searxng():
    """Test SearXNG search functionality."""
    from wet_mcp.searxng_runner import ensure_searxng
    from wet_mcp.sources.searxng import search

    print("\n" + "=" * 50)
    print("TEST: SearXNG Integration")
    print("=" * 50)

    # Start SearXNG subprocess
    print("\n[1] Starting SearXNG...")
    searxng_url = await ensure_searxng()
    print(f"    URL: {searxng_url}")

    # Wait for SearXNG to be ready
    print("[2] Waiting for SearXNG to be ready...")
    await asyncio.sleep(5)

    # Test search
    print("[3] Testing search query: 'python programming'...")
    try:
        result = await search(
            searxng_url=searxng_url,
            query="python programming",
            categories="general",
            max_results=5,
        )
        data = json.loads(result)

        if "error" in data:
            print(f"    ERROR: {data['error']}")
            return False

        print(f"    Found {data.get('total', 0)} results")
        for r in data.get("results", [])[:3]:
            print(f"    - {r.get('title', 'No title')[:50]}")

        return data.get("total", 0) > 0

    except Exception as e:
        print(f"    EXCEPTION: {e}")
        return False


async def test_extract():
    """Test content extraction."""
    from wet_mcp.sources.crawler import extract

    print("\n" + "=" * 50)
    print("TEST: Content Extraction")
    print("=" * 50)

    test_url = "https://example.com"
    print(f"\n[1] Extracting content from: {test_url}")

    try:
        result = await extract(
            urls=[test_url],
            format="markdown",
            stealth=False,
        )
        data = json.loads(result)

        if isinstance(data, list) and len(data) > 0:
            page = data[0]
            if "error" in page:
                print(f"    ERROR: {page['error']}")
                return False

            title = page.get("title", "")
            content_len = len(page.get("content", ""))
            print(f"    Title: {title}")
            print(f"    Content length: {content_len} chars")
            return content_len > 0

        return False

    except Exception as e:
        print(f"    EXCEPTION: {e}")
        return False


async def test_sitemap():
    """Test sitemap discovery."""
    from wet_mcp.sources.crawler import sitemap

    print("\n" + "=" * 50)
    print("TEST: Sitemap Discovery")
    print("=" * 50)

    test_url = "https://example.com"
    print(f"\n[1] Mapping: {test_url}")

    try:
        result = await sitemap(
            urls=[test_url],
            depth=1,
            max_pages=5,
        )
        data = json.loads(result)

        if isinstance(data, list):
            print(f"    Found {len(data)} URLs")
            for item in data[:3]:
                print(f"    - {item.get('url', '')}")
            return len(data) > 0

        return False

    except Exception as e:
        print(f"    EXCEPTION: {e}")
        return False


async def main():
    """Run all integration tests."""
    print("\n" + "#" * 50)
    print("# WET MCP Integration Tests")
    print("#" * 50)

    results = {}

    # Test 1: SearXNG
    results["searxng"] = await test_searxng()

    # Test 2: Extract
    results["extract"] = await test_extract()

    # Test 3: Sitemap
    results["sitemap"] = await test_sitemap()

    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    # Cleanup
    print("\n[Cleanup] Stopping SearXNG...")
    from wet_mcp.searxng_runner import stop_searxng

    stop_searxng()
    print("    Done!")

    # Exit code
    all_passed = all(results.values())
    print(f"\n{'All tests passed!' if all_passed else 'Some tests failed!'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
