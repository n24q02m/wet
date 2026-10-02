"""Tests for ``extract(action="interact")`` (Phase 3 Task 4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import CallToolResult
from structured import text

from wet_mcp.sources import _browser_sessions as bs
from wet_mcp.sources import interact_orchestrator as io


@pytest.fixture
def _fake_browser(monkeypatch):
    """Patch open_interact_session so no real patchright is launched."""

    def _factory():
        pw = MagicMock(name="playwright")
        pw.stop = AsyncMock()
        browser = MagicMock(name="browser")
        browser.close = AsyncMock()
        page = MagicMock(name="page")
        page.content = AsyncMock(return_value="<html><body><h1>Done</h1></body></html>")
        page.url = "https://example.com/post"
        ops = MagicMock(name="ops")
        ops._page = page
        ops.click = AsyncMock()
        ops.fill = AsyncMock()
        ops.submit = AsyncMock()
        ops.wait_for = AsyncMock()
        ops.screenshot = AsyncMock(return_value=b"\x89PNGfake")
        return pw, browser, page, ops

    counter: dict = {"opens": 0, "instances": []}

    async def fake(url, headless=True, timeout_ms=30000):
        counter["opens"] = counter["opens"] + 1
        pw, browser, page, ops = _factory()
        counter["instances"].append(
            {"pw": pw, "browser": browser, "page": page, "ops": ops}
        )
        return pw, browser, page, ops

    monkeypatch.setattr(
        "wet_mcp.sources.interact_orchestrator.open_interact_session", fake
    )
    # Also patch the import inside _browser_sessions for session reuse path.
    monkeypatch.setattr("wet_mcp.sources.interact_ops.open_interact_session", fake)
    return counter


@pytest.fixture
def _fresh_pool():
    """Reset the singleton between tests."""
    pool = bs._reset_pool()
    yield pool


@pytest.mark.asyncio
async def test_missing_url_returns_error():
    result = await io.run_interact(
        url="", actions=[{"type": "click", "selector": "#x"}]
    )
    assert isinstance(result, str)
    assert "url is required" in result


@pytest.mark.asyncio
async def test_missing_actions_returns_error():
    result = await io.run_interact(url="https://x", actions=[])
    assert isinstance(result, str)
    assert "actions is required" in result


@pytest.mark.asyncio
async def test_too_many_actions_returns_error():
    actions = [{"type": "click", "selector": "#a"}] * 25
    result = await io.run_interact(url="https://x", actions=actions)
    assert isinstance(result, str)
    assert "too many actions" in result


@pytest.mark.asyncio
async def test_unknown_action_type_returns_error(_fake_browser):
    result = await io.run_interact(
        url="https://x", actions=[{"type": "evaluate", "selector": "x"}]
    )
    assert isinstance(result, str)
    assert "action" in result and "failed" in result


@pytest.mark.asyncio
async def test_single_click_action(_fake_browser):
    result = await io.run_interact(
        url="https://x", actions=[{"type": "click", "selector": "#btn"}]
    )
    assert isinstance(result, dict)
    assert result["url"] == "https://example.com/post"
    assert "Done" in result["snapshot_markdown"]


@pytest.mark.asyncio
async def test_multi_action_fill_then_submit(_fake_browser):
    result = await io.run_interact(
        url="https://example.com/login",
        actions=[
            {"type": "fill", "selector": "#email", "value": "x@y.com"},
            {"type": "fill", "selector": "#pwd", "value": "secret"},
            {"type": "submit", "selector": "form"},
        ],
    )
    assert isinstance(result, dict)
    instance = _fake_browser["instances"][0]
    instance["ops"].fill.assert_any_await("#email", "x@y.com", timeout_ms=10000)
    instance["ops"].fill.assert_any_await("#pwd", "secret", timeout_ms=10000)
    instance["ops"].submit.assert_awaited_once_with("form", timeout_ms=10000)


@pytest.mark.asyncio
async def test_fill_without_value_returns_error(_fake_browser):
    result = await io.run_interact(
        url="https://x", actions=[{"type": "fill", "selector": "#email"}]
    )
    assert isinstance(result, str)
    assert "fill action requires" in result or "value" in result


@pytest.mark.asyncio
async def test_session_reuse_does_not_reopen_browser(_fake_browser, _fresh_pool):
    actions = [{"type": "click", "selector": "#btn"}]
    await io.run_interact(url="https://example.com", actions=actions, session="abc")
    assert _fake_browser["opens"] == 1
    await io.run_interact(url="https://example.com", actions=actions, session="abc")
    assert _fake_browser["opens"] == 1, "second call must reuse session"
    await _fresh_pool.close_all()


@pytest.mark.asyncio
async def test_screenshot_writes_png_and_returns_path(
    _fake_browser, tmp_path, monkeypatch
):
    # Redirect screenshot dir to tmp_path/downloads/interact via settings.
    monkeypatch.setattr(
        "wet_mcp.sources.interact_orchestrator.settings.download_dir",
        str(tmp_path / "downloads"),
    )
    (tmp_path / "downloads").mkdir()
    result = await io.run_interact(
        url="https://x",
        actions=[{"type": "click", "selector": "#btn"}],
        screenshot=True,
    )
    assert isinstance(result, dict)
    assert "screenshot_path" in result
    from pathlib import Path

    assert Path(result["screenshot_path"]).exists()
    assert Path(result["screenshot_path"]).read_bytes().startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_description_fallback_resolves_to_text_locator(_fake_browser):
    await io.run_interact(
        url="https://x",
        actions=[{"type": "click", "description": "Sign in"}],
    )
    instance = _fake_browser["instances"][0]
    instance["ops"].click.assert_awaited_once_with("text=Sign in", timeout_ms=10000)


@pytest.mark.asyncio
async def test_action_with_neither_selector_nor_description_errors(_fake_browser):
    result = await io.run_interact(url="https://x", actions=[{"type": "click"}])
    assert isinstance(result, str)
    assert "selector" in result or "description" in result


# --- server-level dispatch wiring ---


@pytest.mark.asyncio
async def test_extract_interact_action_routes_to_orchestrator(_fake_browser):
    from wet_mcp.server import extract

    result = await extract(
        action="interact",
        url="https://example.com",
        actions=[{"type": "click", "selector": "#x"}],
    )
    assert isinstance(result, CallToolResult)
    # Result is wrapped by _wrap_tool but JSON body stays embedded.
    assert "<untrusted_extract_content>" in text(result)
    assert "snapshot_markdown" in text(result)


@pytest.mark.asyncio
async def test_extract_interact_action_missing_url_returns_error():
    from wet_mcp.server import extract

    result = await extract(
        action="interact", actions=[{"type": "click", "selector": "#x"}]
    )
    assert isinstance(result, CallToolResult)
    assert "url is required" in text(result)


@pytest.mark.asyncio
async def test_extract_interact_action_missing_actions_returns_error():
    from wet_mcp.server import extract

    result = await extract(action="interact", url="https://x")
    assert isinstance(result, CallToolResult)
    assert "actions is required" in text(result)


@pytest.mark.asyncio
async def test_extract_unknown_action_lists_interact_in_help():
    from wet_mcp.server import extract

    result = await extract(action="bogus_99")
    assert isinstance(result, CallToolResult)
    assert "interact" in text(result)
