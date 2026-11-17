"""Failure and edge paths of ``extract(action="interact")``.

The patchright browser is the external boundary: ``open_interact_session`` is
replaced by a stub module, exactly as in ``test_extract_interact.py``. Each
test pins what the caller sees when one step of the flow goes wrong.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

from wet.sources import _browser_sessions as bs
from wet.sources import interact_orchestrator as io


def _install_browser(monkeypatch, *, page_content=None, screenshot=None):
    """Stub the browser launcher; returns the ops/page of the opened session."""
    page = MagicMock(name="page")
    page.content = page_content or AsyncMock(return_value="<p>ok</p>")
    page.url = "https://example.com/after"
    ops = MagicMock(name="ops")
    ops._page = page
    ops.click = AsyncMock()
    ops.fill = AsyncMock()
    ops.submit = AsyncMock()
    ops.wait_for = AsyncMock()
    ops.screenshot = screenshot or AsyncMock(return_value=b"\x89PNG")
    browser = MagicMock(name="browser")
    browser.close = AsyncMock()
    pw = MagicMock(name="playwright")
    pw.stop = AsyncMock()

    async def _open(url, headless=True, timeout_ms=30000):
        return pw, browser, page, ops

    stub = types.ModuleType("hull_web.browsers.interact")
    stub.open_interact_session = _open
    monkeypatch.setitem(sys.modules, "hull_web.browsers.interact", stub)
    return ops, browser


def test_launch_error_other_than_missing_browser_is_passed_through():
    """Only the missing-executable case gets the install hint; any other
    launch error reaches the caller verbatim."""
    assert io._browser_launch_error(RuntimeError("proxy refused")) == "proxy refused"


def test_snapshot_text_is_truncated_past_8000_chars():
    """Pins the orientation snapshot budget."""
    snapshot = io._strip_html_to_markdown("<p>" + "word " * 3000 + "</p>")

    assert snapshot.endswith("\n...[snapshot truncated]")
    assert len(snapshot) == 8000 + len("\n...[snapshot truncated]")


async def test_wait_action_uses_selector_state_and_timeout(monkeypatch):
    """A ``wait`` op forwards its selector, state and timeout to the page."""
    ops, _ = _install_browser(monkeypatch)

    result = await io.run_interact(
        url="https://example.com",
        actions=[
            {
                "type": "wait",
                "selector": "#ready",
                "state": "attached",
                "timeout_ms": 50,
            }
        ],
    )

    assert isinstance(result, dict)
    ops.wait_for.assert_awaited_once_with("#ready", state="attached", timeout_ms=50)


async def test_session_launch_failure_is_reported(monkeypatch):
    """A failing persistent-session launch returns the launch error."""
    pool = bs._reset_pool()

    async def _fail(url, headless=True, timeout_ms=30000):
        raise RuntimeError("Executable doesn't exist at /x/chrome")

    stub = types.ModuleType("hull_web.browsers.interact")
    stub.open_interact_session = _fail
    monkeypatch.setitem(sys.modules, "hull_web.browsers.interact", stub)

    out = await io.run_interact(
        url="https://example.com",
        actions=[{"type": "click", "selector": "#b"}],
        session="s1",
    )

    assert isinstance(out, str)
    assert out.startswith("Error: browser launch failed")
    assert "python -m patchright install chromium" in out
    await pool.close_all()


async def test_snapshot_failure_is_reported_and_browser_closed(monkeypatch):
    """A page that cannot be read after the actions returns an error and the
    one-shot browser is still closed."""
    _, browser = _install_browser(
        monkeypatch, page_content=AsyncMock(side_effect=RuntimeError("detached"))
    )

    out = await io.run_interact(
        url="https://example.com", actions=[{"type": "click", "selector": "#b"}]
    )

    assert out == "Error: snapshot failed: detached"
    browser.close.assert_awaited_once()


async def test_screenshot_failure_keeps_the_snapshot(monkeypatch, tmp_path):
    """A failing screenshot is reported next to a still-usable snapshot."""
    monkeypatch.setattr(io.settings, "download_dir", str(tmp_path / "downloads"))
    _install_browser(
        monkeypatch, screenshot=AsyncMock(side_effect=RuntimeError("gpu lost"))
    )

    out = await io.run_interact(
        url="https://example.com",
        actions=[{"type": "click", "selector": "#b"}],
        screenshot=True,
    )

    assert isinstance(out, dict)
    assert out["screenshot_error"] == "gpu lost"
    assert out["snapshot_markdown"] == "ok"
    assert "screenshot_path" not in out


@pytest.fixture(autouse=True)
def _reset_session_pool():
    yield
    bs._reset_pool()
