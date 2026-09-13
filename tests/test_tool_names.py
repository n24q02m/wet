"""Protocol contract for the tool names exposed by wet (f. wet-mcp)."""

import os

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.timeout(60)

EXPECTED_NAMES = [
    "config",
    "config__open_relay",
    "extract",
    "help",
    "media",
    "search",
]
RETIRED_NAMES: list[str] = []
_TOOL_NAMES: list[str] | None = None


async def _list_tool_names() -> list[str]:
    global _TOOL_NAMES
    if _TOOL_NAMES is not None:
        return _TOOL_NAMES

    params = StdioServerParameters(
        command="uv",
        # The contract probe must not let uv mutate/sync the workspace while
        # it is opening the real stdio server. Tool registration does not need
        # remote D1 bindings; the CF selector is covered separately.
        args=["run", "--no-sync", "wet"],
        env={
            **os.environ,
            "LOG_LEVEL": "WARNING",
            "DISABLE_LOCAL_EMBED": "true",
            "DISABLE_LOCAL_RERANK": "true",
            "DISABLE_LOCAL_SEARCH": "true",
            "WET_AUTO_SEARXNG": "false",
            "DOCS_DB_BACKEND": "sqlite",
            "SYNC_ENABLED": "false",
            "WET_CACHE": "false",
        },
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            _TOOL_NAMES = sorted(
                tool.name for tool in (await session.list_tools()).tools
            )
            return _TOOL_NAMES


@pytest.mark.asyncio
async def test_exposes_exactly_the_names_from_the_protocol_contract():
    assert await _list_tool_names() == EXPECTED_NAMES


@pytest.mark.asyncio
async def test_no_retired_name_is_still_exposed():
    names = await _list_tool_names()
    assert not [name for name in RETIRED_NAMES if name in names]
