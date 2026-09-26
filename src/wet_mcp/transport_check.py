"""Transport / runtime venv detection helpers.

Stdio uvx native invocation (`uvx wet-mcp`) places the server inside a
uv-managed tool venv that ships without `pip`. The web-core SearXNG
runner relies on `pip install` and a Docker fallback that neither is
available nor reliable in that context (see spec
``2026-05-01-stdio-pure-http-multiuser.md`` §4.1.1).

This module provides a single memoized predicate, :func:`is_uvx_tool_venv`,
used to short-circuit ``web.search`` / ``research`` / ``docs`` / ``similar``
actions with a clear error message in stdio uvx mode. Other actions
(``extract`` / ``crawl`` / ``map`` / ``media``) remain available because
they hit upstream HTTP directly via ``httpx`` and require no SearXNG.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_UVX_TOOL_VENV_CACHE: bool | None = None


def is_uvx_tool_venv() -> bool:
    """Return True when the current interpreter lives in a uvx tool venv.

    Detection is layered to avoid false positives:

    1. **Docker short-circuit**: if ``/.dockerenv`` exists (every Docker
       container has this marker file), return ``False`` immediately. The
       wet-mcp Docker image uses ``uv sync`` which produces a venv WITHOUT
       pip — that signal would otherwise trigger detection #3 below and
       reject SearXNG-dependent actions even though Method 3 stdio Docker
       has full Docker daemon access.
    2. **Path-based positive**: ``sys.executable`` contains the
       ``uv/tools/`` segment used by uv on Linux/Mac
       (``~/.local/share/uv/tools/<name>/...``) or Windows
       (``%APPDATA%/uv/tools/<name>/...``).
    3. **Module-based fallback**: ``importlib.util.find_spec("pip")``
       returns ``None`` — uv tool venvs deliberately omit pip, while
       normal pip-managed venvs keep it. Only checked if not in Docker.

    Either path/module signal alone is sufficient. Result is memoized for
    the lifetime of the process.
    """
    global _UVX_TOOL_VENV_CACHE
    if _UVX_TOOL_VENV_CACHE is not None:
        return _UVX_TOOL_VENV_CACHE

    _UVX_TOOL_VENV_CACHE = _detect_uvx_tool_venv()
    return _UVX_TOOL_VENV_CACHE


def _is_in_docker() -> bool:
    """Detect Docker container runtime via the standard ``/.dockerenv`` marker.

    Docker creates this file in every container regardless of base image,
    so it is the most reliable cross-distro signal. Podman creates it too
    when running with Docker compatibility mode.
    """
    return os.path.exists("/.dockerenv")


def _is_http_transport() -> bool:
    """Detect HTTP server mode (``--http`` / ``MCP_TRANSPORT`` / ``TRANSPORT_MODE``).

    The uvx-tool-venv limitation is specific to *stdio* native uvx invocation
    (``uvx wet-mcp``). An HTTP deployment reaches SearXNG via its configured
    backend (external ``SEARXNG_URL`` or an auto-spawned instance) and is never
    the constrained stdio-uvx context, so detection must not fire there.

    This also covers hardened container images, which run the app via a
    non-Docker runtime that does NOT create the ``/.dockerenv`` marker the
    Docker short-circuit relies on -- without this the no-pip ``uv sync`` venv
    would be misdetected as stdio uvx and SearXNG actions wrongly rejected.
    """
    return (
        "--http" in sys.argv
        or os.environ.get("MCP_TRANSPORT") == "http"
        or os.environ.get("TRANSPORT_MODE") == "http"
    )


def _detect_uvx_tool_venv() -> bool:
    """Run the actual detection (no caching). Exposed for tests."""
    # Docker / HTTP short-circuit: containers running ``uv sync`` images (Docker
    # or hardened containers) would otherwise trip the no-pip fallback even
    # though they reach SearXNG via Docker daemon or an external SEARXNG_URL.
    # HTTP transport is by definition not stdio uvx, and also catches CF
    # Containers (no ``/.dockerenv`` marker).
    if _is_in_docker() or _is_http_transport():
        return False

    # Path-based check: uv installs tool venvs under a "uv/tools/" directory
    # on every platform. ``Path.parts`` works regardless of separator quirks.
    try:
        parts = Path(sys.executable).resolve().parts
    except (OSError, ValueError):
        parts = ()

    for i in range(len(parts) - 1):
        if parts[i].lower() == "uv" and parts[i + 1].lower() == "tools":
            return True

    # Module-based check: uv tool venvs ship without pip.
    if importlib.util.find_spec("pip") is None:
        return True

    return False


def reset_cache() -> None:
    """Clear the memoized detection result.

    Tests use this between cases that monkeypatch ``sys.executable`` or
    ``importlib.util.find_spec``. Production code never calls this.
    """
    global _UVX_TOOL_VENV_CACHE
    _UVX_TOOL_VENV_CACHE = None


# Error message returned by tools when no configured search backend can run
# under a stdio uvx tool venv (no cloud key, no external SearXNG). Per spec
# ``2026-05-01-stdio-pure-http-multiuser.md`` §4.1.1, extended by
# ``2026-07-13-e0-1-uvx-guard-conditional-fix.md`` to only fire when the
# configured ``SEARCH_BACKENDS`` chain has no uvx-runnable option.
UVX_SEARXNG_BLOCKED_ERROR = (
    "Error: action '{action}' needs a search backend, and the local SearXNG "
    "cannot\n"
    "auto-start under uvx (no pip in a uv tool venv).\n"
    "Pick ONE:\n"
    "  1. Set a cloud key (no Docker needed):\n"
    "       TAVILY_API_KEY=...   (or BRAVE_API_KEY / EXA_API_KEY / KAGI_API_KEY)\n"
    "     then set SEARCH_BACKENDS=tavily  (or brave / exa / kagi)\n"
    "  1b. No key at all — use the credential-free backends:\n"
    "       SEARCH_BACKENDS=duckduckgo,startpage   (firecrawl also works keyless)"
    "  2. Point at an already-running SearXNG:\n"
    "       SEARXNG_URL=https://your-searxng.example\n"
    "  3. Build and run from this checkout (bundles SearXNG):\n"
    "       docker build --target stdio -t wet-mcp:local .\n"
    "       docker run -i --rm wet-mcp:local\n"
    "See https://github.com/n24q02m/wet-mcp#setup"
)


def uvx_searxng_blocked_error(action: str) -> str:
    """Format the SearXNG-blocked error message for ``action``."""
    return UVX_SEARXNG_BLOCKED_ERROR.format(action=action)
