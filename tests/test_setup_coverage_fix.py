from unittest.mock import patch

from wet_mcp.setup import patch_searxng_version, patch_searxng_windows


@patch("wet_mcp.setup.logger")
@patch("wet_mcp.setup.Path")
@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_version_no_dir_robust(mock_find_dir, mock_path, mock_logger):
    """Verify patch_searxng_version returns early without any side effects if searx dir is missing."""
    mock_find_dir.return_value = None

    patch_searxng_version()

    # Should exit early without any Path operations
    mock_path.assert_not_called()
    # Should not log anything on early return
    mock_logger.debug.assert_not_called()
    mock_logger.warning.assert_not_called()
    mock_logger.error.assert_not_called()


@patch("wet_mcp.setup.platform.system")
@patch("wet_mcp.setup.logger")
@patch("wet_mcp.setup.Path")
@patch("wet_mcp.setup._find_searx_package_dir")
def test_patch_searxng_windows_no_dir_robust(
    mock_find_dir, mock_path, mock_logger, mock_system
):
    """Verify patch_searxng_windows returns early without any side effects if searx dir is missing on Windows."""
    mock_system.return_value = "Windows"
    mock_find_dir.return_value = None

    patch_searxng_windows()

    # Should exit early without any Path operations
    mock_path.assert_not_called()
    # Should not log anything on early return
    mock_logger.debug.assert_not_called()
    mock_logger.warning.assert_not_called()
