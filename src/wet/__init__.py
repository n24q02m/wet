"""WET MCP Server - Web Extended Toolkit for AI Agents."""

from importlib.metadata import version

from wet.cli import main
from wet.server import mcp

try:
    __version__ = version("n24q02m-wet")
except Exception:
    __version__ = version("wet-mcp")
__all__ = ["mcp", "main", "__version__"]
