"""Embedded SearXNG process management — delegates to web-core.

Bridges wet-mcp settings (``config.settings``) to web-core's
``ensure_searxng`` API. Also monkey-patches web-core's SearXNG
installer to apply wet-mcp-specific patches (version_frozen +
Windows valkeydb compatibility).

All internal functions are re-exported from web-core for backward
compatibility with existing tests and consumers.
"""

import web_core.search.runner as _wc_runner
from loguru import logger
from web_core.search.runner import shutdown_searxng

from wet_mcp.config import settings

# ---------------------------------------------------------------------------
# Monkey-patch web-core's SearXNG installer to apply wet-mcp patches.
# web-core's _install_searxng() does not create version_frozen.py or
# patch valkeydb.py for Windows. These are needed when installing
# SearXNG from zip archive.
# ---------------------------------------------------------------------------

_wc_original_install = _wc_runner._install_searxng


def _patched_install_searxng() -> bool:
    """Install SearXNG via web-core then apply wet-mcp patches."""
    result = _wc_original_install()
    if result:
        try:
            from wet_mcp.setup import (
                patch_searxng_version,
                patch_searxng_windows,
            )

            patch_searxng_version()
            patch_searxng_windows()
        except Exception as e:
            logger.debug(f"SearXNG patch failed (non-fatal): {e}")
    return result


_wc_runner._install_searxng = _patched_install_searxng  # type: ignore[assignment]  # ty: ignore[invalid-assignment]


# ---------------------------------------------------------------------------
# Randomize port discovery to avoid TOCTOU race when multiple instances
# start concurrently (e.g. wet, wet-nokey, wet-sync).
# ---------------------------------------------------------------------------


def _find_available_port(start_port: int, max_tries: int = 100) -> int:
    """Find an available port, randomizing offset to avoid collisions."""
    import random
    import socket

    offsets = list(range(max_tries))
    random.shuffle(offsets)

    for offset in offsets:
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue

    msg = f"No available port found in range {start_port}-{start_port + max_tries - 1}"
    raise RuntimeError(msg)


_wc_runner._find_available_port = _find_available_port  # type: ignore[assignment]  # ty: ignore[invalid-assignment]

# ---------------------------------------------------------------------------
# Re-export internal functions from web-core for backward compatibility.
# Tests and other modules import these from wet_mcp.searxng_runner.
# ---------------------------------------------------------------------------
from web_core.search.runner import (  # noqa: F401, E402
    _DISCOVERY_FILE,
    _HEALTH_CHECK_TIMEOUT,
    _RESTART_COOLDOWN,
    _STARTUP_HEALTH_TIMEOUT,
    _cleanup_process,
    _ensure_searxng_locked,
    _force_kill_process,
    _get_pip_command,
    _get_process_kwargs,
    _get_settings_path,
    _get_startup_lock,
    _handle_restart_and_start,
    _install_searxng,
    _is_owner,
    _is_pid_alive,
    _is_process_alive,
    _is_searxng_installed,
    _kill_stale_port_process,
    _last_restart_time,
    _quick_health_check,
    _read_discovery,
    _remove_discovery,
    _restart_count,
    _searxng_port,
    _searxng_process,
    _sigterm_then_kill,
    _start_searxng_subprocess,
    _startup_lock,
    _try_reuse_existing,
    _wait_for_service,
    _write_discovery,
)

# ---------------------------------------------------------------------------
# Public API — bridges wet-mcp settings to web-core
# ---------------------------------------------------------------------------


async def ensure_searxng() -> str:
    """Start embedded SearXNG subprocess if not running. Returns URL.

    Bridges wet-mcp settings to web-core's ensure_searxng API:
    - ``settings.wet_auto_searxng`` -> ``auto_start``
    - ``settings.searxng_url`` -> ``url`` (when auto disabled)
    - ``settings.wet_searxng_port`` -> ``start_port``

    Falls back to ``settings.searxng_url`` on failure.
    """
    if not settings.auto_searxng_enabled():
        logger.info(
            "Auto SearXNG disabled (WET_AUTO_SEARXNG off or DISABLE_LOCAL_SEARCH set), using external URL"
        )
        return settings.searxng_url

    try:
        return await _wc_runner.ensure_searxng(
            start_port=settings.wet_searxng_port,
        )
    except RuntimeError as e:
        logger.warning(f"SearXNG start failed: {e}. Falling back to external URL.")
        return settings.searxng_url


def stop_searxng() -> None:
    """Stop SearXNG subprocess if running."""
    shutdown_searxng()
