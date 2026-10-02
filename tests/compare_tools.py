"""Compare wet-mcp docs search vs Context7 vs Tavily for 30 out-of-benchmark libraries.

Runs wet's discover_library internally, calls Context7 REST API and Tavily REST API,
then compares results side-by-side.

Usage:
    uv run --no-sync python tests/compare_tools.py
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 30 libraries NOT in the benchmark (verified against 1200 benchmark cases)
COMPARISON_CASES = [
    # Python (5)
    {"name": "pydash", "query": "map filter collections", "lang": "python"},
    {"name": "python-multipart", "query": "file upload parsing", "lang": "python"},
    {"name": "pyjwt", "query": "encode decode JWT tokens", "lang": "python"},
    {"name": "passlib", "query": "password hashing bcrypt", "lang": "python"},
    {"name": "textual", "query": "TUI widgets layout CSS", "lang": "python"},
    # JS/TS (5)
    {"name": "h3", "query": "event handler routing", "lang": "javascript"},
    {"name": "nitro", "query": "server engine deployment", "lang": "javascript"},
    {"name": "vinejs", "query": "schema validation rules", "lang": "javascript"},
    {"name": "inertia", "query": "server-side rendering adapter", "lang": "javascript"},
    {"name": "million", "query": "virtual DOM optimization", "lang": "javascript"},
    # Rust (5)
    {"name": "ratatui", "query": "terminal UI widgets layout", "lang": "rust"},
    {"name": "egui", "query": "immediate mode GUI widgets", "lang": "rust"},
    {"name": "iced", "query": "application widget styling", "lang": "rust"},
    {"name": "yew", "query": "components hooks HTML macro", "lang": "rust"},
    {"name": "dioxus", "query": "signals components routing", "lang": "rust"},
    # Go (3)
    {"name": "chi", "query": "router middleware context", "lang": "go"},
    {"name": "fx", "query": "dependency injection lifecycle", "lang": "go"},
    {"name": "consul", "query": "service discovery health check", "lang": "go"},
    # .NET (3)
    {"name": "mediatr", "query": "mediator pattern CQRS handler", "lang": "csharp"},
    {
        "name": "fluentvalidation",
        "query": "validation rules validator",
        "lang": "csharp",
    },
    {"name": "dapper", "query": "query mapping stored procedure", "lang": "csharp"},
    # Java (2)
    {
        "name": "hibernate-validator",
        "query": "bean validation constraints",
        "lang": "java",
    },
    {
        "name": "resilience4j",
        "query": "circuit breaker retry rate limiter",
        "lang": "java",
    },
    # Ruby (2)
    {"name": "pundit", "query": "authorization policy scope", "lang": "ruby"},
    {"name": "dry-rb", "query": "validation schema types", "lang": "ruby"},
    # PHP (1)
    {"name": "doctrine", "query": "ORM entity mapping repository", "lang": "php"},
    # Docs sites (3)
    {
        "name": "vitepress",
        "query": "markdown theme configuration",
        "lang": "javascript",
    },
    {"name": "quarto", "query": "render publish document format", "lang": "python"},
    {"name": "hexo", "query": "theme plugin deployment", "lang": "javascript"},
    # Misc (1)
    {"name": "caddy", "query": "reverse proxy HTTPS Caddyfile", "lang": "go"},
]


@dataclass
class ToolResult:
    found: bool = False
    url: str = ""
    snippet: str = ""
    latency_ms: int = 0
    error: str = ""


@dataclass
class ComparisonResult:
    library: str = ""
    query: str = ""
    lang: str = ""
    wet: ToolResult = field(default_factory=ToolResult)
    context7: ToolResult = field(default_factory=ToolResult)
    tavily: ToolResult = field(default_factory=ToolResult)


async def test_wet(name: str, query: str, lang: str) -> ToolResult:
    """Test wet-mcp's discover_library."""
    result = ToolResult()
    try:
        from wet_mcp.sources.docs import discover_library

        start = time.monotonic()
        disc = await discover_library(name, language=lang)
        result.latency_ms = int((time.monotonic() - start) * 1000)

        if disc and disc.get("docs_url"):
            result.found = True
            result.url = disc["docs_url"]
            result.snippet = disc.get("source", "")
        elif disc and disc.get("homepage"):
            result.found = True
            result.url = disc["homepage"]
            result.snippet = disc.get("source", "")
        else:
            result.found = False
            result.error = "No docs_url or homepage found"
    except Exception as e:
        result.error = str(e)[:200]
    return result


async def test_context7(name: str, query: str) -> ToolResult:
    """Test Context7 resolve + query via REST API."""
    result = ToolResult()
    api_key = os.environ.get("CONTEXT7_API_KEY", "")

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Resolve library ID
            resolve_resp = await client.get(
                "https://context7.com/api/v1/search",
                params={"query": name},
                headers={"X-Context7-Api-Key": api_key} if api_key else {},
            )

            if resolve_resp.status_code == 200:
                data = resolve_resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    lib_id = data[0].get("id", "")
                    result.found = True
                    result.url = f"https://context7.com{lib_id}"
                    result.snippet = data[0].get("title", "")
                else:
                    result.found = False
                    result.error = "No library found in Context7"
            else:
                result.found = False
                result.error = f"Context7 HTTP {resolve_resp.status_code}"

        result.latency_ms = int((time.monotonic() - start) * 1000)
    except Exception as e:
        result.error = str(e)[:200]
    return result


async def test_tavily(name: str, query: str, lang: str) -> ToolResult:
    """Test Tavily search for library docs."""
    result = ToolResult()
    api_key = os.environ.get("TAVILY_API_KEY", "")

    if not api_key:
        result.error = "TAVILY_API_KEY not set"
        return result

    try:
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": f"{name} {lang} library official documentation {query}",
                    "max_results": 3,
                    "search_depth": "basic",
                },
            )

            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    result.found = True
                    result.url = results[0].get("url", "")
                    result.snippet = results[0].get("title", "")[:100]
                else:
                    result.found = False
                    result.error = "No Tavily results"
            else:
                result.error = f"Tavily HTTP {resp.status_code}"

        result.latency_ms = int((time.monotonic() - start) * 1000)
    except Exception as e:
        result.error = str(e)[:200]
    return result


async def run_comparison():
    """Run all 30 comparisons."""
    results: list[ComparisonResult] = []

    for i, case in enumerate(COMPARISON_CASES):
        name = case["name"]
        query = case["query"]
        lang = case["lang"]

        print(f"[{i + 1:2d}/30] {name} ({lang})...", end=" ", flush=True)

        # Run all 3 tools concurrently
        wet_task = test_wet(name, query, lang)
        ctx7_task = test_context7(name, query)
        tavily_task = test_tavily(name, query, lang)

        wet_r, ctx7_r, tavily_r = await asyncio.gather(wet_task, ctx7_task, tavily_task)

        comp = ComparisonResult(
            library=name,
            query=query,
            lang=lang,
            wet=wet_r,
            context7=ctx7_r,
            tavily=tavily_r,
        )
        results.append(comp)

        status = (
            f"W:{'Y' if wet_r.found else 'N'} "
            f"C7:{'Y' if ctx7_r.found else 'N'} "
            f"T:{'Y' if tavily_r.found else 'N'}"
        )
        print(status)

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)

    return results


def print_summary(results: list[ComparisonResult]):
    """Print comparison summary table."""
    wet_found = sum(1 for r in results if r.wet.found)
    ctx7_found = sum(1 for r in results if r.context7.found)
    tavily_found = sum(1 for r in results if r.tavily.found)

    wet_latency = [r.wet.latency_ms for r in results if r.wet.found]
    ctx7_latency = [r.context7.latency_ms for r in results if r.context7.found]
    tavily_latency = [r.tavily.latency_ms for r in results if r.tavily.found]

    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY: wet-mcp vs Context7 vs Tavily (30 cases)")
    print("=" * 80)

    print(f"\n{'Metric':<25} {'wet-mcp':>12} {'Context7':>12} {'Tavily':>12}")
    print("-" * 65)
    print(
        f"{'Found docs':<25} {wet_found:>9}/30 {ctx7_found:>9}/30 {tavily_found:>9}/30"
    )
    print(
        f"{'Found rate':<25} {wet_found / 30 * 100:>11.1f}% {ctx7_found / 30 * 100:>11.1f}% {tavily_found / 30 * 100:>11.1f}%"
    )

    if wet_latency:
        print(
            f"{'Avg latency (ms)':<25} {sum(wet_latency) // len(wet_latency):>12} "
            f"{sum(ctx7_latency) // len(ctx7_latency) if ctx7_latency else 'N/A':>12} "
            f"{sum(tavily_latency) // len(tavily_latency) if tavily_latency else 'N/A':>12}"
        )

    # Per-case detail
    print(f"\n{'Library':<22} {'Lang':<8} {'Wet':>5} {'C7':>5} {'Tav':>5}  Wet URL")
    print("-" * 100)
    for r in results:
        print(
            f"{r.library:<22} {r.lang:<8} "
            f"{'Y' if r.wet.found else 'N':>5} "
            f"{'Y' if r.context7.found else 'N':>5} "
            f"{'Y' if r.tavily.found else 'N':>5}  "
            f"{r.wet.url[:55] if r.wet.found else r.wet.error[:55]}"
        )

    # Cases where wet fails but others succeed
    wet_only_fail = [
        r for r in results if not r.wet.found and (r.context7.found or r.tavily.found)
    ]
    if wet_only_fail:
        print(f"\nWet FAILS but others succeed ({len(wet_only_fail)}):")
        for r in wet_only_fail:
            print(f"  - {r.library}: C7={r.context7.url[:50]} Tav={r.tavily.url[:50]}")

    # Cases where wet succeeds but others fail
    wet_only_win = [
        r
        for r in results
        if r.wet.found and not r.context7.found and not r.tavily.found
    ]
    if wet_only_win:
        print(f"\nWet WINS uniquely ({len(wet_only_win)}):")
        for r in wet_only_win:
            print(f"  - {r.library}: {r.wet.url[:60]}")

    # Save detailed results
    output_path = Path(__file__).parent / "compare_results.jsonl"
    with open(output_path, "w") as f:
        for r in results:
            f.write(
                json.dumps(
                    {
                        "library": r.library,
                        "query": r.query,
                        "lang": r.lang,
                        "wet": {
                            "found": r.wet.found,
                            "url": r.wet.url,
                            "latency_ms": r.wet.latency_ms,
                            "error": r.wet.error,
                        },
                        "context7": {
                            "found": r.context7.found,
                            "url": r.context7.url,
                            "latency_ms": r.context7.latency_ms,
                            "error": r.context7.error,
                        },
                        "tavily": {
                            "found": r.tavily.found,
                            "url": r.tavily.url,
                            "latency_ms": r.tavily.latency_ms,
                            "error": r.tavily.error,
                        },
                    }
                )
                + "\n"
            )
    print(f"\nDetailed results saved to: {output_path}")


async def main():
    print("Comparing wet-mcp vs Context7 vs Tavily on 30 out-of-benchmark cases\n")
    results = await run_comparison()
    print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
