import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from wet_mcp import search_metrics
from wet_mcp.cache import WebCache
from wet_mcp.sources.search_backends import run_search_chain


def test_cache_get_stale_with_age(tmp_path):
    cache = WebCache(tmp_path / "cache.db")
    params = {"query": "python asyncio"}
    # Store with TTL override = 10s
    cache.set(
        "search",
        params,
        json.dumps({"results": [{"title": "Asyncio"}]}),
        ttl_override=10,
    )

    # 1. Immediate hit: get_with_age is valid
    hit = cache.get_with_age("search", params)
    assert hit is not None
    content, age = hit
    assert "Asyncio" in content
    assert age >= 0

    # 2. Simulate expired entry (expires_at in the past, but within 2x TTL window)
    import time

    now = time.time()
    with cache._conn:
        cache._conn.execute(
            "UPDATE web_cache SET created_at = ?, expires_at = ? WHERE action = 'search'",
            (now - 15, now - 5),
        )

    # Fresh hit should be None
    assert cache.get_with_age("search", params) is None

    # Stale hit should return the content
    stale_hit = cache.get_stale_with_age("search", params)
    assert stale_hit is not None
    stale_content, stale_age = stale_hit
    assert "Asyncio" in stale_content

    # 3. Simulate very old entry (past 2x TTL window: expired 25s ago for 10s TTL)
    now = time.time()
    with cache._conn:
        cache._conn.execute(
            "UPDATE web_cache SET created_at = ?, expires_at = ? WHERE action = 'search'",
            (now - 35, now - 25),
        )
    assert cache.get_stale_with_age("search", params) is None


def test_search_metrics_ema_and_counts():
    search_metrics._latency_ema.clear()
    search_metrics._query_counts.clear()

    # Record query counts
    search_metrics.record_query("tavily")
    search_metrics.record_query("tavily")
    search_metrics.record_query("brave")

    assert search_metrics.query_count("tavily") == 2
    assert search_metrics.query_count("brave") == 1
    assert search_metrics.query_count("searxng") == 0

    # Record latency EMA
    search_metrics.record_latency("tavily", 1.0)
    assert search_metrics.latency_ema("tavily") == 1.0

    # EMA calculation: 0.3 * 2.0 + 0.7 * 1.0 = 0.6 + 0.7 = 1.3
    search_metrics.record_latency("tavily", 2.0)
    ema = search_metrics.latency_ema("tavily")
    assert ema is not None and abs(ema - 1.3) < 1e-6

    snap = search_metrics.snapshot()
    assert snap["query_counts"]["tavily"] == 2
    assert snap["latency_ema_seconds"]["tavily"] == 1.3


@pytest.mark.asyncio
async def test_search_budget_enforcement():
    search_metrics._latency_ema.clear()
    search_metrics._query_counts.clear()

    b1 = Mock()
    b1.name = "b1"
    b1.search = AsyncMock(
        return_value=json.dumps({"results": [{"url": "https://b1/1", "title": "B1"}]})
    )

    b2 = Mock()
    b2.name = "b2"
    b2.search = AsyncMock(
        return_value=json.dumps({"results": [{"url": "https://b2/1", "title": "B2"}]})
    )

    with patch("wet_mcp.sources.search_backends.settings.wet_search_budget", 1):
        with patch(
            "wet_mcp.sources.search_backends.search_backends_from_env",
            return_value=[b1, b2],
        ):
            # 1st call: b1 should be used
            res1 = await run_search_chain("test query")
            data1 = json.loads(res1)
            assert data1["results"][0]["title"] == "B1"
            assert search_metrics.query_count("b1") == 1

            # 2nd call: b1 has reached budget cap (1), should advance to b2
            res2 = await run_search_chain("test query 2")
            data2 = json.loads(res2)
            assert data2["results"][0]["title"] == "B2"
            assert (
                search_metrics.query_count("b1") == 1
            )  # not incremented because skipped
            assert search_metrics.query_count("b2") == 1

            # 3rd call: both b1 and b2 reached budget cap -> fails with structured error naming exhausted providers
            res3 = await run_search_chain("test query 3")
            data3 = json.loads(res3)
            assert "error" in data3
            assert "budget exhausted" in data3["error"].lower()
            assert "b1" in data3["error"] and "b2" in data3["error"]


@pytest.mark.asyncio
async def test_config_status_and_set_metrics():
    from wet_mcp.config import settings
    from wet_mcp.server import _handle_config_set, _handle_config_status

    search_metrics.record_query("tavily")
    status = await _handle_config_status()
    assert "search_metrics" in status
    assert "query_counts" in status["search_metrics"]

    # Test setting wet_search_budget
    res = _handle_config_set("wet_search_budget", "50")
    assert res.get("status") == "updated"
    assert settings.wet_search_budget == 50

    # Reset
    settings.wet_search_budget = 0
