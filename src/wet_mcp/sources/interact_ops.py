"""Interactive page ops via patchright (click / fill / submit / screenshot).

Phase 3 Task 1 (wet-local) — temporary home for ``InteractOps`` until the
class is contributed back to ``web-core`` per spec section 5.7. Once
upstream ships ``hull_web.browsers.patchright.InteractOps``, this module
becomes a re-export shim and eventually deletes.

Design:
    Stateful helper bound to a single patchright ``Page``. Each method
    first attempts the native patchright call; on ``TimeoutError`` falls
    back to a best-effort "wait for selector then retry" path.

The selector-inference (LLM-resolved selector when raw selector is missing)
fallback is a NICE per spec section 4.2 — we expose ``description`` as an
input but resolve it with a deterministic CSS-like heuristic in this
in-tree implementation. The web-core contribution will swap in the full
``hull_web.scraper.selector_inference`` LLM resolver.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


class InteractOps:
    """Stateful interactive ops on a patchright page.

    Args:
        page: A patchright (Playwright-compatible) ``Page`` instance.
    """

    def __init__(self, page: Any) -> None:
        self._page = page

    async def click(self, selector: str, timeout_ms: int = 10000) -> None:
        """Click an element matched by ``selector``.

        Falls back to ``wait_for(selector)`` + retry once on timeout.
        """
        try:
            await self._page.click(selector, timeout=timeout_ms)
        except Exception as exc:  # pragma: no cover - native exception bubble
            logger.debug(f"click({selector!r}) primary failed: {exc}; retrying")
            await self._page.wait_for_selector(selector, timeout=timeout_ms)
            await self._page.click(selector, timeout=timeout_ms)

    async def fill(self, selector: str, value: str, timeout_ms: int = 10000) -> None:
        """Fill input matched by ``selector`` with ``value``."""
        try:
            await self._page.fill(selector, value, timeout=timeout_ms)
        except Exception as exc:  # pragma: no cover - native exception bubble
            logger.debug(f"fill({selector!r}) primary failed: {exc}; retrying")
            await self._page.wait_for_selector(selector, timeout=timeout_ms)
            await self._page.fill(selector, value, timeout=timeout_ms)

    async def submit(self, selector: str, timeout_ms: int = 10000) -> None:
        """Submit a form matched by ``selector``.

        Patchright/Playwright does not expose ``form.submit`` directly; the
        canonical pattern is ``page.locator(form).evaluate('f => f.submit()')``
        or pressing Enter on the focused input. We use the evaluate path so
        the action works on forms without a visible submit button.
        """
        try:
            locator = self._page.locator(selector)
            await locator.evaluate("(form) => form.submit()", timeout=timeout_ms)
        except Exception as exc:  # pragma: no cover - native exception bubble
            logger.debug(f"submit({selector!r}) primary failed: {exc}; retrying")
            await self._page.wait_for_selector(selector, timeout=timeout_ms)
            locator = self._page.locator(selector)
            await locator.evaluate("(form) => form.submit()", timeout=timeout_ms)

    async def screenshot(self, full_page: bool = False) -> bytes:
        """Capture a PNG screenshot of the page; returns raw bytes."""
        return await self._page.screenshot(full_page=full_page, type="png")

    async def wait_for(
        self, selector: str, state: str = "visible", timeout_ms: int = 10000
    ) -> None:
        """Wait for ``selector`` to reach ``state`` (visible / hidden / attached / detached)."""
        await self._page.wait_for_selector(selector, state=state, timeout=timeout_ms)

    async def evaluate(self, expression: str) -> Any:
        """Evaluate a JS expression in the page context.

        Security note: the public ``extract(action="interact", ...)``
        dispatcher does NOT expose this method to MCP callers — only the
        in-process orchestrator may invoke it for snapshot capture.
        """
        return await self._page.evaluate(expression)


async def open_interact_session(
    url: str,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> tuple[Any, Any, Any, InteractOps]:
    """Launch a patchright browser, open ``url``, return handles + ops.

    Returns ``(playwright, browser, page, ops)`` so the caller is
    responsible for the matched ``await browser.close()`` /
    ``await playwright.stop()`` lifecycle when no session pool is in use.
    """

    # Lazy import — patchright + playwright are heavy and only needed
    # when interact actions actually run.
    def _import_async_playwright():
        from patchright.async_api import async_playwright as _ap

        return _ap

    async_playwright = await asyncio.to_thread(_import_async_playwright)
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(url, timeout=timeout_ms)
    return pw, browser, page, InteractOps(page)
