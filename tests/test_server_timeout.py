"""Tests for _with_timeout helper in server.py.

De-host: the old fixture re-imported ``wet_mcp.server`` under a wall of
``sys.modules`` mocks because the module pulled in the CF/auth stack at
import time. That stack is gone and the module imports cleanly, so these
tests run against the real module and just set the runtime knob they
exercise: ``settings.tool_timeout``.
"""

import asyncio

import pytest


@pytest.fixture
def server_module():
    """The real server module (it imports cleanly in the de-hosted image)."""
    import wet_mcp.server

    return wet_mcp.server


@pytest.fixture
def tool_timeout(monkeypatch):
    """Settable stand-in for the operational ``tool_timeout`` knob."""
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "tool_timeout", 120)
    return settings


def test_with_timeout_success(server_module, tool_timeout):
    """Test _with_timeout returns result when task completes within timeout."""
    _with_timeout = server_module._with_timeout
    tool_timeout.tool_timeout = 1.0

    async def fast_coro():
        return "success"

    async def _test():
        result = await _with_timeout(fast_coro(), "test_action")
        assert result == "success"

    asyncio.run(_test())


def test_with_timeout_exceeded(server_module, tool_timeout):
    """Test _with_timeout returns error message when task exceeds timeout."""
    _with_timeout = server_module._with_timeout
    tool_timeout.tool_timeout = 0.1

    async def slow_coro():
        await asyncio.sleep(0.5)
        return "fail"

    async def _test():
        result = await _with_timeout(slow_coro(), "test_action")
        expected_msg = (
            "Error: 'test_action' timed out after 0.1s. "
            "Increase TOOL_TIMEOUT or try simpler parameters."
        )
        assert result == expected_msg

    asyncio.run(_test())


def test_with_timeout_exception(server_module, tool_timeout):
    """Test _with_timeout propagates exceptions from inner task."""
    _with_timeout = server_module._with_timeout
    tool_timeout.tool_timeout = 1.0

    async def failing_coro():
        raise ValueError("oops")

    async def _test():
        with pytest.raises(ValueError, match="oops"):
            await _with_timeout(failing_coro(), "test_action")

    asyncio.run(_test())


def test_with_timeout_disabled(server_module, tool_timeout):
    """Test _with_timeout bypasses timeout logic when <= 0."""
    _with_timeout = server_module._with_timeout

    async def _test():
        # Test with 0
        tool_timeout.tool_timeout = 0

        async def coro1():
            return "success"

        result = await _with_timeout(coro1(), "test_action")
        assert result == "success"

        # Test with negative
        tool_timeout.tool_timeout = -1

        async def coro2():
            return "success"

        result = await _with_timeout(coro2(), "test_action")
        assert result == "success"

    asyncio.run(_test())


def test_with_timeout_cleanup(server_module, tool_timeout):
    """Test that cancelled task is given grace period for cleanup."""
    _with_timeout = server_module._with_timeout
    tool_timeout.tool_timeout = 0.1

    cleanup_done = [False]

    async def cleanup_coro():
        try:
            await asyncio.sleep(0.5)
        finally:
            # This should run during the grace period
            cleanup_done[0] = True

    async def _test():
        result = await _with_timeout(cleanup_coro(), "test_action")

        expected_msg = (
            "Error: 'test_action' timed out after 0.1s. "
            "Increase TOOL_TIMEOUT or try simpler parameters."
        )
        assert result == expected_msg
        # Verify cleanup ran
        assert cleanup_done[0] is True, "Cleanup block did not run"

    asyncio.run(_test())
