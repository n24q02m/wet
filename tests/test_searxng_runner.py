"""Tests for SearXNG runner wrapper (delegates to web-core).

Tests the wet wrapper layer that bridges settings to web-core's API.
Internal SearXNG process management is tested in web-core's test suite.
"""

from unittest.mock import AsyncMock, patch

import pytest

from wet.searxng_runner import ensure_searxng, stop_searxng


@pytest.fixture
def mock_settings():
    with patch("wet.searxng_runner.settings") as mock:
        mock.wet_auto_searxng = True
        mock.disable_local_search = False
        mock.searxng_url = "http://external:8080"
        mock.wet_searxng_port = 8080
        # Reflect the real auto_searxng_enabled() logic against the mock fields
        # (a bare MagicMock method would return a truthy Mock, defeating the test).
        mock.auto_searxng_enabled.side_effect = lambda: (
            mock.wet_auto_searxng and not mock.disable_local_search
        )
        yield mock


@pytest.fixture
def mock_wc_ensure():
    """Mock web-core's ensure_searxng at the delegation boundary."""
    with patch(
        "wet.searxng_runner._wc_runner.ensure_searxng",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


async def test_ensure_searxng_auto_disabled(mock_settings):
    """When auto-start disabled, return external URL without calling web-core."""
    mock_settings.wet_auto_searxng = False

    url = await ensure_searxng()

    assert url == "http://external:8080"


async def test_ensure_searxng_delegates_to_hull_web(mock_settings, mock_wc_ensure):
    """When auto-start enabled, delegate to web-core with correct params."""
    mock_settings.wet_searxng_port = 9090
    mock_wc_ensure.return_value = "http://127.0.0.1:9090"

    url = await ensure_searxng()

    assert url == "http://127.0.0.1:9090"
    mock_wc_ensure.assert_called_once_with(start_port=9090)


async def test_ensure_searxng_fallback_on_error(mock_settings, mock_wc_ensure):
    """When web-core raises RuntimeError, fall back to external URL."""
    mock_wc_ensure.side_effect = RuntimeError("SearXNG start failed")

    url = await ensure_searxng()

    assert url == "http://external:8080"


async def test_ensure_searxng_passes_configured_port(mock_settings, mock_wc_ensure):
    """Verify wet_searxng_port setting is forwarded as start_port."""
    mock_settings.wet_searxng_port = 12345
    mock_wc_ensure.return_value = "http://127.0.0.1:12345"

    await ensure_searxng()

    mock_wc_ensure.assert_called_once_with(start_port=12345)


def test_stop_searxng_delegates():
    """stop_searxng should call web-core's shutdown_searxng."""
    with patch("wet.searxng_runner.shutdown_searxng") as mock_shutdown:
        stop_searxng()
        mock_shutdown.assert_called_once()


def test_patched_installer_calls_patches():
    """Verify monkey-patched installer applies wet patches after install."""
    with (
        patch("wet.searxng_runner._wc_original_install", return_value=True),
        patch("wet.setup.patch_searxng_version") as mock_version,
        patch("wet.setup.patch_searxng_windows") as mock_windows,
    ):
        from wet.searxng_runner import _patched_install_searxng

        result = _patched_install_searxng()

        assert result is True
        mock_version.assert_called_once()
        mock_windows.assert_called_once()


def test_patched_installer_skips_patches_on_failure():
    """If web-core install fails, patches are not applied."""
    with (
        patch("wet.searxng_runner._wc_original_install", return_value=False),
        patch("wet.setup.patch_searxng_version") as mock_version,
        patch("wet.setup.patch_searxng_windows") as mock_windows,
    ):
        from wet.searxng_runner import _patched_install_searxng

        result = _patched_install_searxng()

        assert result is False
        mock_version.assert_not_called()
        mock_windows.assert_not_called()
