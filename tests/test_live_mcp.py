#!/usr/bin/env python3
"""
Phase 5 Live Comprehensive Test for wet-mcp.

Spawns the server as a subprocess via MCP SDK Client (StdioClientTransport),
communicates over JSON-RPC stdio protocol, and tests ALL tools x actions.

Usage:
    uv run python tests/test_live_mcp.py

Network-dependent tests (search, extract, media) are conditional.
Config + help tests work offline.
"""

import asyncio
import json
import os
import sys

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
passed = 0
failed = 0
skipped = 0
results: list[tuple[str, str, str]] = []  # (label, status, evidence)


def parse(r) -> str:
    """Extract text from MCP tool result."""
    if hasattr(r, "isError") and r.isError:
        raise RuntimeError(r.content[0].text)
    return r.content[0].text


def ok(label: str, evidence: str = ""):
    global passed
    passed += 1
    results.append((label, "PASS", evidence))
    print(f"  [PASS] {label}" + (f" | {evidence[:80]}" if evidence else ""))


def fail(label: str, err: str):
    global failed
    failed += 1
    results.append((label, "FAIL", err))
    print(f"  [FAIL] {label} | {err[:120]}")


def skip(label: str, reason: str):
    global skipped
    skipped += 1
    results.append((label, "SKIP", reason))
    print(f"  [SKIP] {label} | {reason}")


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------
async def run_tests():
    global passed, failed

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "wet-mcp"],
        env={
            **os.environ,
            "LOG_LEVEL": "WARNING",
        },
    )

    async with stdio_client(server_params) as streams:
        read_stream, write_stream = streams
        from mcp.client.session import ClientSession

        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Server connected. Running tests...\n")

            # ===== META =====
            print("--- Meta ---")
            tools_result = await session.list_tools()
            tool_names = sorted(t.name for t in tools_result.tools)
            expected = ["config", "extract", "help", "media", "search"]
            if tool_names == expected:
                ok("listTools", f"tools={tool_names}")
            else:
                fail("listTools", f"Expected {expected}, got {tool_names}")

            # ===== HELP TOOL (offline) =====
            print("\n--- help ---")
            for topic in ["search", "extract", "media", "config", "help"]:
                try:
                    r = await session.call_tool("help", {"tool_name": topic})
                    t = parse(r)
                    if len(t) >= 100:
                        ok(f"help({topic})", f"{len(t)} chars")
                    else:
                        fail(f"help({topic})", f"Too short: {len(t)} chars")
                except Exception as e:
                    fail(f"help({topic})", str(e))

            # ===== CONFIG TOOL (offline) =====
            print("\n--- config ---")

            # config.status
            try:
                r = await session.call_tool("config", {"action": "status"})
                t = parse(r)
                d = json.loads(t)
                if "database" in d and "embedding" in d:
                    ok("config.status", f"keys={list(d.keys())[:5]}")
                else:
                    fail("config.status", f"Missing expected keys: {list(d.keys())}")
            except Exception as e:
                fail("config.status", str(e))

            # config.set
            try:
                r = await session.call_tool(
                    "config", {"action": "set", "key": "log_level", "value": "DEBUG"}
                )
                t = parse(r)
                if "updated" in t.lower() or "set" in t.lower():
                    ok("config.set(log_level=DEBUG)", t[:80])
                else:
                    fail("config.set(log_level=DEBUG)", t[:80])
            except Exception as e:
                fail("config.set(log_level=DEBUG)", str(e))

            # config.cache_clear
            try:
                r = await session.call_tool("config", {"action": "cache_clear"})
                t = parse(r)
                if "clear" in t.lower() or "cache" in t.lower():
                    ok("config.cache_clear", t[:80])
                else:
                    fail("config.cache_clear", t[:80])
            except Exception as e:
                fail("config.cache_clear", str(e))

            # config.docs_reindex
            try:
                r = await session.call_tool(
                    "config", {"action": "docs_reindex", "key": "fastapi"}
                )
                t = parse(r)
                if (
                    "clear" in t.lower()
                    or "reindex" in t.lower()
                    or "fastapi" in t.lower()
                ):
                    ok("config.docs_reindex(fastapi)", t[:80])
                else:
                    fail("config.docs_reindex(fastapi)", t[:80])
            except Exception as e:
                fail("config.docs_reindex(fastapi)", str(e))

            # ===== SEARCH TOOL (network required) =====
            print("\n--- search (network) ---")

            # search.search
            try:
                r = await session.call_tool(
                    "search", {"action": "search", "query": "python testing"}
                )
                t = parse(r)
                if "result" in t.lower() or "http" in t.lower():
                    ok("search.search", f"{len(t)} chars, has results")
                else:
                    fail("search.search", t[:80])
            except Exception as e:
                err = str(e)
                if (
                    "network" in err.lower()
                    or "searxng" in err.lower()
                    or "connection" in err.lower()
                ):
                    skip("search.search", f"Network/SearXNG unavailable: {err[:60]}")
                else:
                    fail("search.search", err[:80])

            # search.research
            try:
                r = await session.call_tool(
                    "search",
                    {"action": "research", "query": "transformer attention mechanism"},
                )
                t = parse(r)
                if len(t) > 50:
                    ok("search.research", f"{len(t)} chars")
                else:
                    fail("search.research", t[:80])
            except Exception as e:
                err = str(e)
                if (
                    "network" in err.lower()
                    or "searxng" in err.lower()
                    or "connection" in err.lower()
                ):
                    skip("search.research", f"Network/SearXNG unavailable: {err[:60]}")
                else:
                    fail("search.research", err[:80])

            # search.docs
            try:
                r = await session.call_tool(
                    "search",
                    {"action": "docs", "library": "requests", "query": "get"},
                )
                t = parse(r)
                if len(t) > 50:
                    ok("search.docs", f"{len(t)} chars")
                else:
                    fail("search.docs", t[:80])
            except Exception as e:
                err = str(e)
                if "network" in err.lower() or "index" in err.lower():
                    skip("search.docs", f"Network unavailable: {err[:60]}")
                else:
                    fail("search.docs", err[:80])

            # ===== EXTRACT TOOL (network required) =====
            print("\n--- extract (network) ---")

            # extract.extract
            try:
                r = await session.call_tool(
                    "extract",
                    {"action": "extract", "urls": ["https://httpbin.org/html"]},
                )
                t = parse(r)
                if "melville" in t.lower() or "moby" in t.lower() or len(t) > 100:
                    ok("extract.extract", f"{len(t)} chars")
                else:
                    fail("extract.extract", f"Unexpected content: {t[:80]}")
            except Exception as e:
                err = str(e)
                if "network" in err.lower() or "connection" in err.lower():
                    skip("extract.extract", f"Network unavailable: {err[:60]}")
                else:
                    fail("extract.extract", err[:80])

            # extract.crawl
            try:
                r = await session.call_tool(
                    "extract",
                    {
                        "action": "crawl",
                        "urls": ["https://docs.python.org/3/library/json.html"],
                        "depth": 1,
                        "max_pages": 2,
                    },
                )
                t = parse(r)
                if len(t) > 100:
                    ok("extract.crawl", f"{len(t)} chars")
                else:
                    fail("extract.crawl", f"Too short: {t[:80]}")
            except Exception as e:
                err = str(e)
                if "network" in err.lower() or "connection" in err.lower():
                    skip("extract.crawl", f"Network unavailable: {err[:60]}")
                else:
                    fail("extract.crawl", err[:80])

            # extract.map
            try:
                r = await session.call_tool(
                    "extract",
                    {
                        "action": "map",
                        "urls": ["https://docs.python.org/3/"],
                        "max_pages": 5,
                    },
                )
                t = parse(r)
                if "http" in t.lower() or "url" in t.lower():
                    ok("extract.map", f"{len(t)} chars")
                else:
                    fail("extract.map", t[:80])
            except Exception as e:
                err = str(e)
                if "network" in err.lower() or "connection" in err.lower():
                    skip("extract.map", f"Network unavailable: {err[:60]}")
                else:
                    fail("extract.map", err[:80])

            # ===== MEDIA TOOL (network required) =====
            print("\n--- media (network) ---")

            # media.list
            try:
                r = await session.call_tool(
                    "media",
                    {"action": "list", "url": "https://httpbin.org/image"},
                )
                t = parse(r)
                if "image" in t.lower() or "media" in t.lower():
                    ok("media.list", f"{len(t)} chars")
                else:
                    fail("media.list", t[:80])
            except Exception as e:
                err = str(e)
                if "network" in err.lower() or "connection" in err.lower():
                    skip("media.list", f"Network unavailable: {err[:60]}")
                else:
                    fail("media.list", err[:80])

            # media.download
            try:
                r = await session.call_tool(
                    "media",
                    {
                        "action": "download",
                        "media_urls": ["https://httpbin.org/image/png"],
                    },
                )
                t = parse(r)
                if (
                    "download" in t.lower()
                    or "path" in t.lower()
                    or "file" in t.lower()
                ):
                    ok("media.download", f"{len(t)} chars")
                else:
                    fail("media.download", t[:80])
            except Exception as e:
                err = str(e)
                if "network" in err.lower() or "connection" in err.lower():
                    skip("media.download", f"Network unavailable: {err[:60]}")
                else:
                    fail("media.download", err[:80])

            # media.analyze (conditional — needs API keys)
            try:
                r = await session.call_tool(
                    "media",
                    {
                        "action": "analyze",
                        "url": "/tmp/nonexistent.png",
                        "prompt": "describe",
                    },
                )
                t = parse(r)
                if "api" in t.lower() or "key" in t.lower() or "error" in t.lower():
                    ok("media.analyze", f"Expected limitation: {t[:60]}")
                else:
                    fail("media.analyze", t[:80])
            except Exception as e:
                err = str(e)
                if (
                    "api" in err.lower()
                    or "key" in err.lower()
                    or "not found" in err.lower()
                ):
                    ok("media.analyze", f"Expected error: {err[:60]}")
                else:
                    fail("media.analyze", err[:80])

            # ===== ERROR PATHS =====
            print("\n--- Error paths ---")

            # search: missing query
            try:
                r = await session.call_tool("search", {"action": "search"})
                t = parse(r)
                if (
                    "error" in t.lower()
                    or "query" in t.lower()
                    or "required" in t.lower()
                ):
                    ok("search(no query)", t[:80])
                else:
                    fail("search(no query)", f"Expected error: {t[:60]}")
            except Exception as e:
                ok("search(no query)", f"Error: {str(e)[:60]}")

            # search: invalid action
            try:
                r = await session.call_tool(
                    "search", {"action": "invalid", "query": "test"}
                )
                t = parse(r)
                if (
                    "error" in t.lower()
                    or "unknown" in t.lower()
                    or "invalid" in t.lower()
                ):
                    ok("search(invalid action)", t[:80])
                else:
                    fail("search(invalid action)", f"Expected error: {t[:60]}")
            except Exception as e:
                ok("search(invalid action)", f"Error: {str(e)[:60]}")

            # extract: missing urls
            try:
                r = await session.call_tool("extract", {"action": "extract"})
                t = parse(r)
                if (
                    "error" in t.lower()
                    or "url" in t.lower()
                    or "required" in t.lower()
                ):
                    ok("extract(no urls)", t[:80])
                else:
                    fail("extract(no urls)", f"Expected error: {t[:60]}")
            except Exception as e:
                ok("extract(no urls)", f"Error: {str(e)[:60]}")

            # media: missing url
            try:
                r = await session.call_tool("media", {"action": "list"})
                t = parse(r)
                if (
                    "error" in t.lower()
                    or "url" in t.lower()
                    or "required" in t.lower()
                ):
                    ok("media(no url)", t[:80])
                else:
                    fail("media(no url)", f"Expected error: {t[:60]}")
            except Exception as e:
                ok("media(no url)", f"Error: {str(e)[:60]}")

            # config: invalid key
            try:
                r = await session.call_tool(
                    "config", {"action": "set", "key": "invalid_key", "value": "x"}
                )
                t = parse(r)
                if (
                    "error" in t.lower()
                    or "invalid" in t.lower()
                    or "valid" in t.lower()
                ):
                    ok("config.set(invalid key)", t[:80])
                else:
                    fail("config.set(invalid key)", f"Expected error: {t[:60]}")
            except Exception as e:
                ok("config.set(invalid key)", f"Error: {str(e)[:60]}")

            # help: invalid tool
            try:
                r = await session.call_tool("help", {"tool_name": "nonexistent"})
                t = parse(r)
                if "error" in t.lower() or "not found" in t.lower():
                    ok("help(invalid tool)", t[:80])
                else:
                    fail("help(invalid tool)", f"Expected error: {t[:60]}")
            except Exception as e:
                ok("help(invalid tool)", f"Error: {str(e)[:60]}")

            # ===== SECURITY BOUNDARY =====
            print("\n--- Security boundary ---")

            # SSRF: private IP
            try:
                r = await session.call_tool(
                    "extract",
                    {
                        "action": "extract",
                        "urls": ["http://169.254.169.254/latest/meta-data"],
                    },
                )
                t = parse(r)
                if (
                    "block" in t.lower()
                    or "denied" in t.lower()
                    or "ssrf" in t.lower()
                    or "error" in t.lower()
                ):
                    ok("extract(SSRF private IP)", f"Blocked: {t[:60]}")
                else:
                    fail("extract(SSRF private IP)", f"NOT blocked: {t[:60]}")
            except Exception as e:
                ok("extract(SSRF private IP)", f"Blocked: {str(e)[:60]}")

            # SSRF: localhost
            try:
                r = await session.call_tool(
                    "extract",
                    {"action": "extract", "urls": ["http://127.0.0.1:8080/secret"]},
                )
                t = parse(r)
                if (
                    "block" in t.lower()
                    or "denied" in t.lower()
                    or "ssrf" in t.lower()
                    or "error" in t.lower()
                ):
                    ok("extract(SSRF localhost)", f"Blocked: {t[:60]}")
                else:
                    fail("extract(SSRF localhost)", f"NOT blocked: {t[:60]}")
            except Exception as e:
                ok("extract(SSRF localhost)", f"Blocked: {str(e)[:60]}")

            # Path traversal in media download
            try:
                r = await session.call_tool(
                    "media",
                    {
                        "action": "download",
                        "media_urls": ["https://httpbin.org/image/png"],
                        "output_dir": "/tmp/evil/../../../etc",
                    },
                )
                t = parse(r)
                if (
                    "error" in t.lower()
                    or "denied" in t.lower()
                    or "security" in t.lower()
                ):
                    ok("media.download(path traversal)", f"Blocked: {t[:60]}")
                else:
                    fail("media.download(path traversal)", f"NOT blocked: {t[:60]}")
            except Exception as e:
                err = str(e)
                if (
                    "denied" in err.lower()
                    or "security" in err.lower()
                    or "error" in err.lower()
                ):
                    ok("media.download(path traversal)", f"Blocked: {err[:60]}")
                else:
                    fail("media.download(path traversal)", err[:60])

    # ===== SUMMARY =====
    total = passed + failed
    pct = 100 * passed / total if total > 0 else 0
    print(f"\n{'=' * 60}")
    print(
        f"RESULT: {passed}/{total} PASS ({pct:.1f}%)"
        + (f", {skipped} skipped" if skipped else "")
    )
    print(f"{'=' * 60}")

    if failed > 0:
        print("\nFailed tests:")
        for label, status, evidence in results:
            if status == "FAIL":
                print(f"  - {label}: {evidence}")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
