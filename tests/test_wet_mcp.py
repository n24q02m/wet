"""Tests for wet_mcp package."""

import re

from wet_mcp import __version__, mcp


def test_version():
    """Test version is set and follows semver."""
    assert re.match(r"^\d+\.\d+\.\d+", __version__)


def test_mcp_server_exists():
    """Test MCP server is initialized."""
    assert mcp is not None
    assert mcp.name == "wet"
