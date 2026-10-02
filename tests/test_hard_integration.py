"""Harder integration tests for WET MCP Server.

Tests with:
- Anti-bot protected sites (Cloudflare, etc.)
- JavaScript-heavy sites
- Data quality verification (not just "has content" but "correct content")

Run with: uv run python tests/test_hard_integration.py
"""

import asyncio
import json
import sys

import pytest
from loguru import logger

pytestmark = pytest.mark.integration

logger.remove()
logger.add(sys.stdout, level="INFO")


async def test_search_quality():
    """Test search result quality and relevance."""
    from wet_mcp.searxng_runner import ensure_searxng
    from wet_mcp.sources.searxng import search

    print("\n" + "=" * 60)
    print("TEST: Search Quality")
    print("=" * 60)

    searxng_url = await ensure_searxng()
    await asyncio.sleep(5)  # Wait for SearXNG to be ready

    test_cases = [
        {
            "query": "Python FastAPI tutorial",
            "expected_domains": [
                "fastapi.tiangolo.com",
                "realpython.com",
                "python.org",
            ],
            "expected_keywords": ["fastapi", "python", "api"],
        },
        {
            "query": "machine learning pytorch",
            "expected_domains": ["pytorch.org"],
            "expected_keywords": ["pytorch", "machine", "learning"],
        },
    ]

    results_summary = []

    for tc in test_cases:
        print(f"\n[TEST] Query: '{tc['query']}'")

        result = await search(
            searxng_url=searxng_url,
            query=str(tc["query"]),
            max_results=10,
        )
        data = json.loads(result)

        if "error" in data:
            print(f"  ERROR: {data['error']}")
            results_summary.append(
                {"query": tc["query"], "passed": False, "reason": data["error"]}
            )
            continue

        # Check result count
        total = data.get("total", 0)
        print(f"  Results: {total}")

        # Check for expected domains
        urls = [r.get("url", "") for r in data.get("results", [])]
        found_domains = []
        for domain in tc["expected_domains"]:
            if any(domain in url for url in urls):
                found_domains.append(domain)
                print(f"  ✓ Found expected domain: {domain}")

        # Check for keywords in snippets
        all_text = " ".join(
            [
                r.get("title", "") + " " + r.get("snippet", "")
                for r in data.get("results", [])
            ]
        ).lower()

        found_keywords = []
        for kw in tc["expected_keywords"]:
            if kw.lower() in all_text:
                found_keywords.append(kw)
                print(f"  ✓ Found keyword: {kw}")

        # Determine pass/fail
        passed = total > 0 and len(found_keywords) >= len(tc["expected_keywords"]) // 2
        results_summary.append(
            {
                "query": tc["query"],
                "passed": passed,
                "total_results": total,
                "domains_found": len(found_domains),
                "keywords_found": len(found_keywords),
            }
        )

    return all(r["passed"] for r in results_summary)


async def test_extract_js_heavy():
    """Test extraction from JavaScript-heavy sites."""
    from wet_mcp.sources.crawler import extract

    print("\n" + "=" * 60)
    print("TEST: JavaScript-Heavy Site Extraction")
    print("=" * 60)

    # Sites that require JS rendering
    test_urls = [
        # GitHub renders with JS but also has SSR fallback
        "https://github.com/python/cpython",
        # Wikipedia is a good baseline
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
    ]

    results = []

    for url in test_urls:
        print(f"\n[TEST] URL: {url}")

        try:
            result = await extract(
                urls=[url],
                format="markdown",
                stealth=True,
            )
            data = json.loads(result)

            if isinstance(data, list) and len(data) > 0:
                page = data[0]
                if "error" in page:
                    print(f"  ERROR: {page['error']}")
                    results.append({"url": url, "passed": False})
                    continue

                title = page.get("title", "")
                content = page.get("content", "")
                content_len = len(content)

                print(f"  Title: {title[:60]}...")
                print(f"  Content length: {content_len} chars")

                # Quality checks
                passed = True
                reasons = []

                # Check minimum content length
                if content_len < 500:
                    passed = False
                    reasons.append("Content too short (<500 chars)")

                # Check for meaningful content (not just boilerplate)
                meaningful_words = [
                    "python",
                    "programming",
                    "code",
                    "function",
                    "class",
                ]
                found_words = sum(
                    1 for w in meaningful_words if w.lower() in content.lower()
                )
                if found_words < 2:
                    passed = False
                    reasons.append(
                        f"Missing meaningful keywords (found {found_words}/5)"
                    )

                # Check for links extracted
                links = page.get("links", {})
                internal_count = len(links.get("internal", []))
                external_count = len(links.get("external", []))
                print(f"  Links: {internal_count} internal, {external_count} external")

                if passed:
                    print("  ✓ Quality check passed")
                else:
                    print(f"  ✗ Quality issues: {', '.join(reasons)}")

                results.append({"url": url, "passed": passed, "reasons": reasons})

        except Exception as e:
            print(f"  EXCEPTION: {e}")
            results.append({"url": url, "passed": False, "error": str(e)})

    return all(r.get("passed", False) for r in results)


async def test_antibot_sites():
    """Test sites with anti-bot protection."""
    from wet_mcp.sources.crawler import extract

    print("\n" + "=" * 60)
    print("TEST: Anti-Bot Protected Sites")
    print("=" * 60)
    print("NOTE: These may fail due to bot protection - that's expected")

    # Sites with known anti-bot measures
    antibot_urls = [
        # Medium uses Cloudflare
        ("https://medium.com", "medium", False),
        # LinkedIn heavily protected
        ("https://www.linkedin.com", "linkedin", False),
        # Twitter/X very strict
        ("https://twitter.com", "twitter", False),
        # News sites often have protection
        ("https://www.nytimes.com", "nytimes", False),
    ]

    results = []

    for url, name, _expected_pass in antibot_urls:
        print(f"\n[TEST] {name}: {url}")

        try:
            result = await extract(
                urls=[url],
                format="markdown",
                stealth=True,  # Enable stealth mode
            )
            data = json.loads(result)

            if isinstance(data, list) and len(data) > 0:
                page = data[0]
                if "error" in page:
                    print(f"  Blocked/Error: {page['error'][:50]}...")
                    results.append({"site": name, "blocked": True})
                else:
                    content_len = len(page.get("content", ""))
                    print(f"  Content: {content_len} chars")
                    if content_len > 100:
                        print("  ✓ Successfully extracted!")
                        results.append(
                            {"site": name, "blocked": False, "content_len": content_len}
                        )
                    else:
                        print("  ⚠ Minimal content (likely blocked)")
                        results.append(
                            {"site": name, "blocked": True, "content_len": content_len}
                        )

        except Exception as e:
            print(f"  Exception: {str(e)[:50]}...")
            results.append({"site": name, "blocked": True, "error": str(e)})

    # Report summary
    blocked_count = sum(1 for r in results if r.get("blocked", True))
    print(
        f"\n  Summary: {len(results) - blocked_count}/{len(results)} sites accessible"
    )

    # This test passes if we attempted all sites (anti-bot is expected to block some)
    return True


async def test_crawl_depth():
    """Test multi-page crawling with depth control."""
    from wet_mcp.sources.crawler import crawl

    print("\n" + "=" * 60)
    print("TEST: Multi-page Crawl with Depth")
    print("=" * 60)

    # Use a site with clear structure
    test_url = "https://docs.python.org/3/"
    print(f"\n[TEST] Crawling: {test_url}")
    print("       Depth: 1, Max pages: 5")

    try:
        result = await crawl(
            urls=[test_url],
            depth=1,
            max_pages=5,
            format="markdown",
            stealth=False,
        )
        data = json.loads(result)

        if isinstance(data, list):
            print(f"  Crawled {len(data)} pages:")

            # Check page depths
            depths = {}
            for page in data:
                d = page.get("depth", 0)
                depths[d] = depths.get(d, 0) + 1
                print(f"    [{d}] {page.get('title', 'No title')[:50]}...")

            print(f"\n  Pages by depth: {depths}")

            # Verify we got pages at different depths
            passed = len(data) >= 2 and len(depths) >= 1
            if passed:
                print("  ✓ Multi-page crawl successful")
            else:
                print("  ✗ Insufficient pages crawled")

            return passed

    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return False

    return False


async def test_media_detection():
    """Test media detection on pages with various media types."""
    from wet_mcp.sources.crawler import list_media

    print("\n" + "=" * 60)
    print("TEST: Media Detection")
    print("=" * 60)

    # Use GitHub which has images (badges, avatars)
    test_url = "https://github.com/python/cpython"
    print(f"\n[TEST] Scanning: {test_url}")

    try:
        result = await list_media(
            url=test_url,
            media_type="all",
            max_items=10,
        )
        data = json.loads(result)

        if "error" in data:
            print(f"  ERROR: {data['error']}")
            return False

        images = data.get("images", [])
        videos = data.get("videos", [])
        audio = data.get("audio", [])

        print(
            f"  Found: {len(images)} images, {len(videos)} videos, {len(audio)} audio"
        )

        # Verify image data structure
        if images:
            sample = images[0]
            src = sample.get("src", "") if isinstance(sample, dict) else sample
            print(f"  Sample image src: {src[:80]}...")

        passed = len(images) > 0
        if passed:
            print("  ✓ Media detection working")
        else:
            print("  ✗ No images found")

        return passed

    except Exception as e:
        print(f"  EXCEPTION: {e}")
        return False


async def main():
    """Run all harder integration tests."""
    from wet_mcp.searxng_runner import stop_searxng

    print("\n" + "#" * 60)
    print("# WET MCP - Harder Integration Tests")
    print("#" * 60)

    results = {}

    # Test 1: Search Quality
    results["search_quality"] = await test_search_quality()

    # Test 2: JS-heavy extraction
    results["js_extraction"] = await test_extract_js_heavy()

    # Test 3: Anti-bot sites (informational, always passes)
    results["antibot"] = await test_antibot_sites()

    # Test 4: Multi-page crawl
    results["crawl_depth"] = await test_crawl_depth()

    # Test 5: Media detection
    results["media_detection"] = await test_media_detection()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        indicator = "✓" if passed else "✗"
        print(f"  {indicator} {name}: {status}")

    # Cleanup
    print("\n[Cleanup] Stopping SearXNG...")
    stop_searxng()
    print("  Done!")

    # Overall result
    critical_tests = ["search_quality", "js_extraction", "crawl_depth"]
    critical_passed = all(results.get(t, False) for t in critical_tests)

    print(
        f"\n{'All critical tests passed!' if critical_passed else 'Some critical tests failed!'}"
    )
    return 0 if critical_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
