"""In-process browser session pool for ``extract(action="interact")``.

Phase 3 spec section 4.2 NICE: opt-in via ``extract(action="interact",
session="<id>", ...)`` keeps the same patchright browser context (with
cookies + localStorage) across calls so multi-step flows like login then
fetch authenticated content work without re-authenticating each call.

The pool is process-scoped; on process restart all sessions are gone. A
background GC task evicts sessions past their TTL; LRU eviction caps
concurrent open browsers to ``_DEFAULT_MAX_CONCURRENT`` to bound RSS.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

_DEFAULT_TTL_SECONDS = 1800  # 30 minutes
_DEFAULT_MAX_CONCURRENT = 5
_GC_INTERVAL_SECONDS = 60


class _SessionEntry:
    """Tracks a live patchright session: playwright + browser + page handles."""

    __slots__ = ("playwright", "browser", "page", "ops", "last_used")

    def __init__(self, playwright: Any, browser: Any, page: Any, ops: Any) -> None:
        self.playwright = playwright
        self.browser = browser
        self.page = page
        self.ops = ops
        self.last_used: float = time.monotonic()

    async def close(self) -> None:
        try:
            if self.browser is not None:
                await self.browser.close()
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            logger.debug(f"_SessionEntry browser.close() raised: {exc}")
        try:
            if self.playwright is not None:
                await self.playwright.stop()
        except Exception as exc:  # pragma: no cover - best-effort cleanup
            logger.debug(f"_SessionEntry playwright.stop() raised: {exc}")


class SessionPool:
    """TTL + LRU bounded pool of patchright sessions keyed by session id."""

    def __init__(
        self,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        max_concurrent: int = _DEFAULT_MAX_CONCURRENT,
    ) -> None:
        self._sessions: dict[str, _SessionEntry] = {}
        self._ttl = ttl_seconds
        self._max = max_concurrent
        self._lock = asyncio.Lock()
        self._gc_task: asyncio.Task | None = None

    async def get(self, session_id: str, url: str) -> Any:
        """Return cached ops for ``session_id`` or open + cache a new one.

        ``url`` is used only when minting a fresh session (the new browser
        navigates there). Reusing an existing session does NOT re-navigate
        unless the caller explicitly does so via ``ops``.
        """
        async with self._lock:
            entry = self._sessions.get(session_id)
            if entry is not None:
                entry.last_used = time.monotonic()
                self._maybe_start_gc()
                return entry.ops

            # Evict LRU before opening new (capacity gate).
            if len(self._sessions) >= self._max:
                lru_id = min(self._sessions, key=lambda k: self._sessions[k].last_used)
                logger.info(f"SessionPool LRU evicting {lru_id!r} (cap {self._max})")
                lru = self._sessions.pop(lru_id)
                await lru.close()

            from wet_mcp.sources.interact_ops import open_interact_session

            pw, browser, page, ops = await open_interact_session(url)
            entry = _SessionEntry(playwright=pw, browser=browser, page=page, ops=ops)
            self._sessions[session_id] = entry
            self._maybe_start_gc()
            return ops

    async def close(self, session_id: str) -> None:
        """Explicitly close + drop one session."""
        async with self._lock:
            entry = self._sessions.pop(session_id, None)
        if entry is not None:
            await entry.close()

    async def close_all(self) -> None:
        """Close every cached session (e.g. on process shutdown)."""
        async with self._lock:
            entries = list(self._sessions.values())
            self._sessions.clear()
        for entry in entries:
            await entry.close()

    async def gc(self) -> None:
        """Evict sessions whose ``last_used`` is older than TTL."""
        now = time.monotonic()
        evicted: list[_SessionEntry] = []
        async with self._lock:
            stale_ids = [
                sid
                for sid, e in self._sessions.items()
                if now - e.last_used >= self._ttl
            ]
            for sid in stale_ids:
                logger.info(f"SessionPool TTL evicting {sid!r}")
                evicted.append(self._sessions.pop(sid))
        for entry in evicted:
            await entry.close()

    def _maybe_start_gc(self) -> None:
        """Lazily start the background GC task on first session use."""
        if self._gc_task is None or self._gc_task.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:  # pragma: no cover - no loop, can't schedule
                return
            self._gc_task = loop.create_task(self._gc_loop())

    async def _gc_loop(self) -> None:
        """Run ``gc()`` every ``_GC_INTERVAL_SECONDS`` until pool is empty."""
        try:
            while True:
                await asyncio.sleep(_GC_INTERVAL_SECONDS)
                await self.gc()
                async with self._lock:
                    if not self._sessions:
                        return
        except asyncio.CancelledError:  # pragma: no cover - loop teardown
            return


# Module-level singleton. Reset by tests via ``_reset_pool()``.
_pool: SessionPool = SessionPool()


def get_pool() -> SessionPool:
    """Return the process-wide session pool singleton."""
    return _pool


def _reset_pool(
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    max_concurrent: int = _DEFAULT_MAX_CONCURRENT,
) -> SessionPool:
    """Replace the singleton with a fresh pool (test helper).

    Tests that need a custom TTL or capacity call this before exercising
    the pool, then call ``await get_pool().close_all()`` in teardown.
    """
    global _pool
    _pool = SessionPool(ttl_seconds=ttl_seconds, max_concurrent=max_concurrent)
    return _pool
