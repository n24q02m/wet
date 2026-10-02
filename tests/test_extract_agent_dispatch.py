"""Server-level dispatch tests for ``extract(action="agent")`` (Phase 3 Task 2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from mcp.types import CallToolResult
from structured import payload, text

from wet_mcp.server import extract


@pytest.mark.asyncio
async def test_agent_action_missing_query_returns_error() -> None:
    result = await extract(action="agent")
    assert isinstance(result, CallToolResult)
    assert "query is required" in text(result)


@pytest.mark.asyncio
async def test_agent_action_routes_to_orchestrator_and_serialises_dict() -> None:
    fake_result = {
        "markdown": "synth",
        "sources": [{"index": 1, "url": "https://x", "title": "t"}],
        "per_url_metadata": [
            {"url": "https://x", "extract_strategy": "basic_http", "tokens": 10}
        ],
    }
    with patch(
        "wet_mcp.sources.agent_orchestrator.run_agent",
        new_callable=AsyncMock,
        return_value=fake_result,
    ):
        result = await extract(action="agent", query="explain X")
    # _wrap_tool wraps non-error responses in <untrusted_extract_content>
    # tags; the JSON payload is embedded inside.
    assert isinstance(result, CallToolResult)
    assert "<untrusted_extract_content>" in text(result)
    assert '"markdown": "synth"' in text(result)
    assert '"url": "https://x"' in text(result)
    data = payload(result)
    assert data["sources"][0]["url"] == "https://x"


@pytest.mark.asyncio
async def test_agent_action_passes_through_error_string() -> None:
    with patch(
        "wet_mcp.sources.agent_orchestrator.run_agent",
        new_callable=AsyncMock,
        return_value="Error: no LLM provider detected. ...",
    ):
        result = await extract(action="agent", query="x")
    assert isinstance(result, CallToolResult)
    assert payload(result)["error"].startswith("Error: no LLM provider detected")


@pytest.mark.asyncio
async def test_agent_listed_in_unknown_action_help() -> None:
    result = await extract(action="bogus_action_99")
    assert isinstance(result, CallToolResult)
    assert "agent" in text(result), "agent should appear in valid actions list"
