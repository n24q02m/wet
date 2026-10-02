"""Pytest configuration and fixtures."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest_plugins = ["conftest_e2e"]


class _AvailableBothWays:
    """``check_available`` stub usable from both sync and async call sites.

    The cloud legs await ``check_available()`` (async HTTP client) while the
    local legs call it synchronously (CPU-bound ONNX). A stub handed out by
    the backend-init factory below must answer both so the lifespan's
    background init can run against either branch without loading a model.
    """

    def __init__(self, value=True) -> None:  # noqa: ANN001
        self.value = value

    def __call__(self):
        return self.value

    def __await__(self):
        async def _resolve():
            return self.value

        return _resolve().__await__()


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path_factory, monkeypatch):
    """Point ``Path.home()`` at a throwaway directory for every test.

    wet derives every storage path from ``Path.home()`` (``~/.wet/``:
    config.toml, docs.db, per-sub cache roots) and the local model caches
    key off it too. Without isolation a test touching the storage layer
    reads or writes the developer's real ``~/.wet`` — and two pytest
    processes running at once (``-n`` workers in CI) would contend on the
    same on-disk files.

    ``Path.home()`` resolves ``HOME`` on POSIX and ``USERPROFILE`` on Windows,
    so both are set; ``monkeypatch`` restores them when the test ends.
    """
    fake_home = tmp_path_factory.mktemp("wet_test_home")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))


@pytest.fixture(autouse=True)
def _stub_lifespan_heavy_init():
    """Keep the FastMCP lifespan off real disk, downloads and the network.

    The lifespan's startup leg runs migrations + Tier 1 warmup (both touch
    ``~/.wet/docs.db``, which a cold CI runner does not have) and kicks off
    the fire-and-forget backend init task (``wet-init-backends``). Stub the
    heavy pieces by default: tests that need the real migrations / warmup
    call them directly (test_migrations.py, test_tier1_warmup.py), and tests
    that exercise the backend-init factories patch the same targets
    themselves, overriding this default.
    """
    embed_backend = MagicMock()
    embed_backend.check_available = _AvailableBothWays(768)
    rerank = MagicMock()
    rerank.check_available = _AvailableBothWays(True)
    with (
        patch("wet_mcp.migrations.run_migrations_on_startup"),
        patch("wet_mcp.sources.tier1_warmup.maybe_warm"),
        patch("wet_mcp.embedder.init_backend", return_value=embed_backend),
        patch("wet_mcp.reranker.init_reranker", return_value=rerank),
    ):
        yield


@pytest.fixture(autouse=True)
def _disable_uvx_tool_venv_detection(monkeypatch):
    """Default ``is_uvx_tool_venv`` to ``False`` for all tests.

    The real detection inspects the dev ``.venv`` (which also lacks pip in
    uv-managed projects) and would otherwise short-circuit search-tool
    tests. Tests that exercise the uvx detection itself reset
    ``transport_check._UVX_TOOL_VENV_CACHE`` and patch the underlying
    signals directly.
    """
    import sys

    import wet_mcp.transport_check as tc

    monkeypatch.setattr(tc, "is_uvx_tool_venv", lambda: False)
    # ``test_server_timeout.py`` re-imports ``wet_mcp.server`` under heavy
    # mocking; patch every live copy registered in ``sys.modules`` so
    # subsequent tests still see ``False``.
    for mod_name, mod in list(sys.modules.items()):
        if mod_name == "wet_mcp.server" and hasattr(mod, "is_uvx_tool_venv"):
            monkeypatch.setattr(mod, "is_uvx_tool_venv", lambda: False)
    yield


@pytest.fixture
def sample_url():
    """Sample URL for testing."""
    return "https://example.com"


@pytest.fixture
def sample_query():
    """Sample search query."""
    return "test query"


@pytest.fixture(autouse=True)
async def _reset_crawler_singleton():
    """Reset the crawler singleton state before and after each test.

    This ensures tests do not leak state between each other when the
    singleton browser pool is involved.
    """
    import wet_mcp.sources.crawler as crawler_mod

    # Reset before test
    crawler_mod._crawler_instance = None
    crawler_mod._crawler_stealth = False
    crawler_mod._browser_semaphore = None

    yield

    # Reset after test
    crawler_mod._crawler_instance = None
    crawler_mod._crawler_stealth = False
    crawler_mod._browser_semaphore = None


@pytest.fixture
def mock_crawler_instance():
    """Create a mock AsyncWebCrawler instance for use with _get_crawler patch.

    Returns the mock instance directly.  Tests should patch
    ``wet_mcp.sources.crawler._get_crawler`` to return this mock so that
    the singleton browser pool is bypassed entirely.

    Example usage::

        async def test_something(mock_crawler_instance):
            mock_result = MagicMock(success=True, ...)
            mock_crawler_instance.arun = AsyncMock(return_value=mock_result)

            with patch(
                "wet_mcp.sources.crawler._get_crawler",
                new_callable=AsyncMock,
                return_value=mock_crawler_instance,
            ):
                result = await extract(["https://example.com"])
    """
    instance = AsyncMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    return instance
