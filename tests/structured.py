"""Helpers for reading the tools' structured output in tests.

``search`` / ``extract`` / ``media`` return a ``CallToolResult`` (built by
``server._wrap_tool``) so that both response channels can be asserted: the
text block keeps the ``<untrusted_{tool}_content>`` XPIA boundary tags and
``structuredContent`` carries the envelope markers. ``config`` returns a plain
dict, which FastMCP turns into ``structuredContent`` on the wire.

Use :func:`payload` to read what the tool returned and :func:`text` to assert
on the text block (markers, error messages).
"""

import json
from typing import Any

from mcp.types import CallToolResult, TextContent


def payload(result: CallToolResult | dict[str, Any]) -> dict[str, Any]:
    """Return the tool's structured payload."""
    if isinstance(result, CallToolResult):
        assert result.structuredContent is not None, "tool emitted no structuredContent"
        return result.structuredContent
    return result


def text(result: CallToolResult | dict[str, Any]) -> str:
    """Return the tool's text block, XPIA markers included."""
    if isinstance(result, CallToolResult):
        return "".join(
            block.text for block in result.content if isinstance(block, TextContent)
        )
    return json.dumps(result, ensure_ascii=False, indent=2)
