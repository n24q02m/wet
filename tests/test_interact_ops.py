"""Tests for ``InteractOps`` (Phase 3 Task 1, wet-local).

Mocks the patchright ``Page`` so tests stay fast and offline. Real
browser-driven smoke tests live under the ``integration`` marker (not run
by default) once web-core ships the upstream contribution.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from wet_mcp.sources.interact_ops import InteractOps


def _fake_page() -> MagicMock:
    page = MagicMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nrest")
    page.evaluate = AsyncMock(return_value="expr-result")
    locator = MagicMock()
    locator.evaluate = AsyncMock()
    page.locator = MagicMock(return_value=locator)
    return page


@pytest.mark.asyncio
async def test_interact_ops_click_calls_native_click() -> None:
    page = _fake_page()
    ops = InteractOps(page)
    await ops.click("#btn")
    page.click.assert_awaited_once_with("#btn", timeout=10000)


@pytest.mark.asyncio
async def test_interact_ops_click_retries_on_timeout() -> None:
    page = _fake_page()
    page.click.side_effect = [TimeoutError("first"), None]
    ops = InteractOps(page)
    await ops.click("#btn", timeout_ms=500)
    assert page.click.await_count == 2
    page.wait_for_selector.assert_awaited_once_with("#btn", timeout=500)


@pytest.mark.asyncio
async def test_interact_ops_fill_calls_native_fill() -> None:
    page = _fake_page()
    ops = InteractOps(page)
    await ops.fill("#email", "user@example.com")
    page.fill.assert_awaited_once_with("#email", "user@example.com", timeout=10000)


@pytest.mark.asyncio
async def test_interact_ops_fill_retries_on_timeout() -> None:
    page = _fake_page()
    page.fill.side_effect = [TimeoutError("first"), None]
    ops = InteractOps(page)
    await ops.fill("#email", "x@y.com", timeout_ms=200)
    assert page.fill.await_count == 2


@pytest.mark.asyncio
async def test_interact_ops_submit_uses_evaluate_on_form_locator() -> None:
    page = _fake_page()
    ops = InteractOps(page)
    await ops.submit("form#login")
    page.locator.assert_called_once_with("form#login")
    page.locator.return_value.evaluate.assert_awaited_once()


@pytest.mark.asyncio
async def test_interact_ops_screenshot_returns_png_bytes() -> None:
    page = _fake_page()
    ops = InteractOps(page)
    data = await ops.screenshot()
    assert isinstance(data, bytes)
    assert data.startswith(b"\x89PNG"), "screenshot must be valid PNG bytes"
    page.screenshot.assert_awaited_once_with(full_page=False, type="png")


@pytest.mark.asyncio
async def test_interact_ops_screenshot_full_page_flag_propagates() -> None:
    page = _fake_page()
    ops = InteractOps(page)
    await ops.screenshot(full_page=True)
    page.screenshot.assert_awaited_once_with(full_page=True, type="png")


@pytest.mark.asyncio
async def test_interact_ops_wait_for_passes_state_and_timeout() -> None:
    page = _fake_page()
    ops = InteractOps(page)
    await ops.wait_for("#x", state="hidden", timeout_ms=2500)
    page.wait_for_selector.assert_awaited_once_with("#x", state="hidden", timeout=2500)


@pytest.mark.asyncio
async def test_interact_ops_evaluate_returns_page_evaluate_result() -> None:
    page = _fake_page()
    ops = InteractOps(page)
    result = await ops.evaluate("1+1")
    assert result == "expr-result"
    page.evaluate.assert_awaited_once_with("1+1")
