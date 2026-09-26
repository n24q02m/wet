"""Protocol contract for the tool names exposed by wet (f. wet-mcp).

De-host: there is no stdio spawn anymore, so the probe lists tools
in-process from the FastMCP instance instead of opening a client session.
"""

import pytest

pytestmark = pytest.mark.timeout(60)

EXPECTED_NAMES = [
    "config",
    "extract",
    "help",
    "media",
    "search",
]
RETIRED_NAMES: list[str] = [
    # CF-era control-plane tools that must never come back.
    "config__open_relay",
    "config__setup_sync",
    "config__setup_start",
]
_TOOL_NAMES: list[str] | None = None


async def _list_tool_names() -> list[str]:
    global _TOOL_NAMES
    if _TOOL_NAMES is not None:
        return _TOOL_NAMES

    from wet_mcp.server import mcp

    tools = await mcp.list_tools()
    _TOOL_NAMES = sorted(tool.name for tool in tools)
    return _TOOL_NAMES


@pytest.mark.asyncio
async def test_exposes_exactly_the_names_from_the_protocol_contract():
    assert await _list_tool_names() == EXPECTED_NAMES


@pytest.mark.asyncio
async def test_no_retired_name_is_still_exposed():
    names = await _list_tool_names()
    assert not [name for name in RETIRED_NAMES if name in names]
