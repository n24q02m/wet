"""Tests for _with_timeout helper in server.py."""

import asyncio
import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_dependencies():
    """Mock external dependencies to allow importing server.py."""
    modules = {
        "loguru": MagicMock(),
        "mcp": MagicMock(),
        "mcp.server": MagicMock(),
        "mcp.server.fastmcp": MagicMock(),
        "mcp.types": MagicMock(),
        "crawl4ai": MagicMock(),
        "httpx": MagicMock(),
        "pydantic": MagicMock(),
        "pydantic_settings": MagicMock(),
        "sqlite_vec": MagicMock(),
        # Internal modules
        "wet_mcp.cache": MagicMock(),
        "wet_mcp.db": MagicMock(),
        "wet_mcp.searxng_runner": MagicMock(),
        "wet_mcp.sources": MagicMock(),
        "wet_mcp.sources.crawler": MagicMock(),
        "wet_mcp.sources.searxng": MagicMock(),
        "wet_mcp.embedder": MagicMock(),
        "wet_mcp.reranker": MagicMock(),
        "wet_mcp.setup": MagicMock(),
        "wet_mcp.sync": MagicMock(),
        # Mock config explicitly
        "wet_mcp.config": MagicMock(),
    }

    # Mock importlib.metadata to avoid PackageNotFoundError
    mock_metadata = MagicMock()
    mock_metadata.version.return_value = "0.0.0"
    modules["importlib.metadata"] = mock_metadata

    # Re-importing ``wet_mcp.server`` under mocks rebinds the parent package
    # attribute ``wet_mcp.server`` to the throwaway module. patch.dict restores
    # sys.modules on exit but NOT that attribute, leaving an orphaned copy
    # (fresh module state, MagicMock-wired imports) shadowing the real module
    # for every later attribute-style import -- e.g. pytest's string-target
    # ``monkeypatch.setattr("wet_mcp.server._embedding_dims", ...)`` wrote the
    # copy while ``from wet_mcp.server import ...`` read the real module, so
    # tests running after this file saw stale state (#test-order pollution).
    saved_server = sys.modules.get("wet_mcp.server")

    with patch.dict(sys.modules, modules):
        # Create a mock settings object
        mock_settings = MagicMock()
        mock_settings.tool_timeout = 120
        sys.modules["wet_mcp.config"].settings = mock_settings

        # Import the module inside the patch context
        # We must invalidate the cache first if it exists to force re-import with mocks
        if "wet_mcp.server" in sys.modules:
            del sys.modules["wet_mcp.server"]

        module = importlib.import_module("wet_mcp.server")
        try:
            yield module, mock_settings
        finally:
            # Put back the pre-fixture module identity: sys.modules comes back
            # via patch.dict, the package attribute must be restored by hand.
            if saved_server is not None:
                sys.modules["wet_mcp"].server = saved_server
            elif hasattr(sys.modules["wet_mcp"], "server"):
                delattr(sys.modules["wet_mcp"], "server")


def test_with_timeout_success(mock_dependencies):
    """Test _with_timeout returns result when task completes within timeout."""
    server_module, mock_settings = mock_dependencies
    _with_timeout = server_module._with_timeout

    mock_settings.tool_timeout = 1.0

    async def fast_coro():
        return "success"

    async def _test():
        result = await _with_timeout(fast_coro(), "test_action")
        assert result == "success"

    asyncio.run(_test())


def test_with_timeout_exceeded(mock_dependencies):
    """Test _with_timeout returns error message when task exceeds timeout."""
    server_module, mock_settings = mock_dependencies
    _with_timeout = server_module._with_timeout

    mock_settings.tool_timeout = 0.1

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


def test_with_timeout_exception(mock_dependencies):
    """Test _with_timeout propagates exceptions from inner task."""
    server_module, mock_settings = mock_dependencies
    _with_timeout = server_module._with_timeout

    mock_settings.tool_timeout = 1.0

    async def failing_coro():
        raise ValueError("oops")

    async def _test():
        with pytest.raises(ValueError, match="oops"):
            await _with_timeout(failing_coro(), "test_action")

    asyncio.run(_test())


def test_with_timeout_disabled(mock_dependencies):
    """Test _with_timeout bypasses timeout logic when <= 0."""
    server_module, mock_settings = mock_dependencies
    _with_timeout = server_module._with_timeout

    async def _test():
        # Test with 0
        mock_settings.tool_timeout = 0

        async def coro1():
            return "success"

        result = await _with_timeout(coro1(), "test_action")
        assert result == "success"

        # Test with negative
        mock_settings.tool_timeout = -1

        async def coro2():
            return "success"

        result = await _with_timeout(coro2(), "test_action")
        assert result == "success"

    asyncio.run(_test())


def test_with_timeout_cleanup(mock_dependencies):
    """Test that cancelled task is given grace period for cleanup."""
    server_module, mock_settings = mock_dependencies
    _with_timeout = server_module._with_timeout

    cleanup_done = [False]
    mock_settings.tool_timeout = 0.1

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
