"""Verify wet runs as a real HTTP MCP server (de-host entry).

Spawns ``python -m wet.server`` on an ephemeral loopback port and exercises
the initialize handshake plus ``tools/list`` over the streamable-HTTP MCP
transport, proving the FastMCP HTTP app is wired directly (no daemon-spawn
bridge layer in front of it). There is no stdio mode post-de-host.

Marked ``live`` because it spawns a real subprocess and speaks the MCP
protocol; excluded from the default ``pytest`` invocation but runs under
``uv run pytest -m live``.
"""

from __future__ import annotations

import pytest
from live_http import (
    EXPECTED_WET_TOOLS,
    mcp_client_session,
    wet_http_server,
    wet_server_env,
)

pytestmark = [pytest.mark.live, pytest.mark.timeout(120)]


async def test_http_direct_init_responds(tmp_path):
    """Spawn the HTTP server; verify the initialize response shape."""
    async with wet_http_server(
        wet_server_env(tmp_path), tmp_path / "server.log"
    ) as port:
        async with mcp_client_session(port) as session:
            result = await session.initialize()
            # FastMCP negotiates protocol version; just assert it returned one.
            assert result.protocolVersion
            # Server name is "wet" per FastMCP(name="wet", ...) in server.py.
            assert result.serverInfo.name == "wet"


async def test_http_direct_tools_list_returns_expected_tools(tmp_path):
    """Verify tools/list returns the de-hosted wet tool set over HTTP."""
    async with wet_http_server(
        wet_server_env(tmp_path), tmp_path / "server.log"
    ) as port:
        async with mcp_client_session(port) as session:
            await session.initialize()
            result = await session.list_tools()
            tool_names = sorted(t.name for t in result.tools)
            assert tool_names == EXPECTED_WET_TOOLS, (
                f"missing={set(EXPECTED_WET_TOOLS) - set(tool_names)} "
                f"unexpected={set(tool_names) - set(EXPECTED_WET_TOOLS)}"
            )
