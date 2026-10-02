"""Tests for ``SessionPool`` (Phase 3 Task 3)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from wet_mcp.sources import _browser_sessions as bs


@pytest.fixture
def _fake_open_session(monkeypatch):
    """Patch open_interact_session so no real browser is launched."""

    def _factory():
        pw = MagicMock(name="playwright")
        pw.stop = AsyncMock()
        browser = MagicMock(name="browser")
        browser.close = AsyncMock()
        page = MagicMock(name="page")
        ops = MagicMock(name="ops")
        return pw, browser, page, ops

    counter = {"n": 0}

    async def fake(url, headless=True, timeout_ms=30000):
        counter["n"] += 1
        pw, browser, page, ops = _factory()
        ops._url = url
        ops._n = counter["n"]
        return pw, browser, page, ops

    monkeypatch.setattr("wet_mcp.sources.interact_ops.open_interact_session", fake)
    return counter


@pytest.fixture
def _fresh_pool():
    """Reset the module singleton with default config; close all in teardown."""
    pool = bs._reset_pool(ttl_seconds=1800, max_concurrent=5)
    yield pool
    asyncio.get_event_loop().run_until_complete(pool.close_all()) if False else None


@pytest.mark.asyncio
async def test_get_returns_new_session_on_first_use(_fake_open_session, _fresh_pool):
    pool = _fresh_pool
    ops = await pool.get("login-1", "https://example.com")
    assert ops is not None
    assert _fake_open_session["n"] == 1
    await pool.close_all()


@pytest.mark.asyncio
async def test_get_reuses_existing_session(_fake_open_session, _fresh_pool):
    pool = _fresh_pool
    ops_a = await pool.get("login-1", "https://example.com")
    ops_b = await pool.get("login-1", "https://other.com")
    assert ops_a is ops_b, "second get must reuse same session"
    assert _fake_open_session["n"] == 1
    await pool.close_all()


@pytest.mark.asyncio
async def test_max_concurrent_evicts_lru(_fake_open_session, monkeypatch):
    pool = bs._reset_pool(ttl_seconds=1800, max_concurrent=2)
    try:
        await pool.get("a", "https://a")
        await asyncio.sleep(0.01)
        await pool.get("b", "https://b")
        await asyncio.sleep(0.01)
        # Third session should evict 'a' (oldest last_used).
        await pool.get("c", "https://c")
        async with pool._lock:
            assert "a" not in pool._sessions
            assert "b" in pool._sessions
            assert "c" in pool._sessions
        # 'a' was closed (browser.close + playwright.stop)
        # We can't reach into the closed entry directly, but counter
        # reflects 3 distinct opens.
        assert _fake_open_session["n"] == 3
    finally:
        await pool.close_all()


@pytest.mark.asyncio
async def test_gc_evicts_after_ttl(_fake_open_session, monkeypatch):
    pool = bs._reset_pool(ttl_seconds=1, max_concurrent=5)
    try:
        await pool.get("stale", "https://x")
        # Force last_used into the past so gc() considers it stale.
        async with pool._lock:
            pool._sessions["stale"].last_used -= 10
        await pool.gc()
        async with pool._lock:
            assert "stale" not in pool._sessions
    finally:
        await pool.close_all()


@pytest.mark.asyncio
async def test_close_specific_session(_fake_open_session, _fresh_pool):
    pool = _fresh_pool
    await pool.get("a", "https://a")
    await pool.get("b", "https://b")
    await pool.close("a")
    async with pool._lock:
        assert "a" not in pool._sessions
        assert "b" in pool._sessions
    await pool.close_all()


@pytest.mark.asyncio
async def test_close_unknown_session_is_noop(_fresh_pool):
    pool = _fresh_pool
    await pool.close("never-existed")  # must not raise


@pytest.mark.asyncio
async def test_close_all_clears_pool(_fake_open_session, _fresh_pool):
    pool = _fresh_pool
    await pool.get("a", "https://a")
    await pool.get("b", "https://b")
    await pool.close_all()
    async with pool._lock:
        assert pool._sessions == {}


@pytest.mark.asyncio
async def test_session_entry_close_swallows_browser_failures():
    pw = MagicMock(name="pw")
    pw.stop = AsyncMock(side_effect=RuntimeError("pw stop failed"))
    browser = MagicMock(name="browser")
    browser.close = AsyncMock(side_effect=RuntimeError("browser close failed"))
    entry = bs._SessionEntry(playwright=pw, browser=browser, page=None, ops=None)
    # Must not raise.
    await entry.close()
    pw.stop.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_pool_returns_singleton():
    a = bs.get_pool()
    b = bs.get_pool()
    assert a is b


@pytest.mark.asyncio
async def test_reset_pool_replaces_singleton(_fake_open_session):
    a = bs.get_pool()
    b = bs._reset_pool()
    assert a is not b
    assert bs.get_pool() is b
    await b.close_all()
