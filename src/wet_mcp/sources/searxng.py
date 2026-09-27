"""SearXNG search integration — delegates to web-core.

Wraps web-core's ``search()`` function to return JSON strings (MCP tool
format) and adds health-check + auto-restart logic before each search.

Internal helpers (``_normalize_url``, ``_apply_domain_cap``, etc.) are
re-exported from web-core for backward compatibility.
"""

import json

import httpx
from loguru import logger

# Re-export URL helpers for backward compat
from hull_web.http.url import _TRACKING_PARAMS  # noqa: F401
from hull_web.http.url import is_valid_domain as _is_valid_domain  # noqa: F401
from hull_web.http.url import normalize_url as _normalize_url  # noqa: F401
from hull_web.search import SearchError
from hull_web.search import search as _wc_search
from hull_web.search.client import (  # noqa: F401
    _apply_domain_cap,
    _build_filtered_query,
)

from wet_mcp.config import settings
from wet_mcp.security import is_safe_url

# Default health check timeout
_HEALTH_CHECK_TIMEOUT = 5.0


def _searxng_auth() -> tuple[str, str] | None:
    """HTTP basic-auth ``(user, pass)`` for an external authenticated SearXNG
    (e.g. behind Caddy basic-auth), or ``None`` when not both configured — the
    auto-local SearXNG needs none. Avoids embedding credentials in SEARXNG_URL."""
    user = settings.searxng_auth_user
    pwd = settings.searxng_auth_pass
    return (user, pwd) if user and pwd else None


async def _check_health(searxng_url: str, *, use_settings_auth: bool = True) -> bool:
    """Whether the SearXNG instance is REACHABLE (not whether /healthz is 200).

    Any HTTP response means the instance is up: 200 = ready, and 401/403 = up but
    auth-gated / reverse-proxy-blocked (an external SearXNG behind Caddy/CF basic
    auth answers /healthz with 401/403 even though /search works — the search call
    itself carries the auth). Only a 5xx or a connection/timeout error means it is
    actually down and worth an auto-restart. Returning True on 401/403 stops the
    pointless restart→spawn of a local SearXNG when an external one is configured.
    """
    try:
        auth = _searxng_auth() if use_settings_auth else None
        extra = {"auth": auth} if auth else {}
        async with httpx.AsyncClient(timeout=_HEALTH_CHECK_TIMEOUT) as client:
            response = await client.get(
                f"{searxng_url}/healthz",
                headers={
                    "X-Real-IP": "127.0.0.1",
                    "X-Forwarded-For": "127.0.0.1",
                },
                **extra,
            )
            return response.status_code < 500
    except Exception:
        return False


async def _ensure_searxng_healthy(
    searxng_url: str,
    *,
    allow_local_restart: bool = True,
    use_settings_auth: bool = True,
) -> str:
    """Verify SearXNG is reachable and restart only managed local instances."""
    if await _check_health(searxng_url, use_settings_auth=use_settings_auth):
        return searxng_url

    if not allow_local_restart:
        logger.warning("Hosted SearXNG is unhealthy; local restart is disabled")
        return searxng_url

    logger.warning(f"SearXNG at {searxng_url} is unhealthy, attempting restart...")

    from wet_mcp.searxng_runner import ensure_searxng

    new_url = await ensure_searxng()

    if await _check_health(new_url, use_settings_auth=use_settings_auth):
        logger.info(f"SearXNG restarted successfully at {new_url}")
        return new_url

    # Even if health check fails after restart, return the URL
    # and let the search attempt proceed — it may still work.
    logger.warning(f"SearXNG at {new_url} still unhealthy after restart attempt")
    return new_url


async def search(
    searxng_url: str,
    query: str,
    categories: str = "general",
    max_results: int = 10,
    time_range: str | None = None,
    language: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    hosted: bool = False,
) -> str:
    """Search via SearXNG API — delegates to web-core, returns JSON string.

    Managed local/single-user instances retain health-check restart and optional
    operator basic auth. Hosted subject URLs are SSRF-vetted, never inherit
    process-global auth, and never fall back to a local SearXNG.

    Args:
        searxng_url: SearXNG instance URL
        query: Search query
        categories: Search category (general, images, videos, files)
        max_results: Maximum number of results
        time_range: Time filter (day, week, month, year)
        language: Language filter (e.g. en, vi, zh)
        include_domains: Only search these domains (max 5)
        exclude_domains: Exclude these domains (max 10)
        hosted: Treat ``searxng_url`` as untrusted per-subject configuration.

    Returns:
        JSON string with search results
    """
    logger.info(f"Searching SearXNG: {query}")

    if hosted and not is_safe_url(searxng_url):
        return json.dumps({"error": "Security Alert: unsafe SearXNG URL blocked"})

    auth = None if hosted else _searxng_auth()

    # Pre-search health check + auto-restart if needed
    if hosted:
        active_url = await _ensure_searxng_healthy(
            searxng_url,
            allow_local_restart=False,
            use_settings_auth=False,
        )
    else:
        active_url = await _ensure_searxng_healthy(searxng_url)

    try:
        import dataclasses

        results = await _wc_search(
            active_url,
            query,
            categories=categories,
            max_results=max_results,
            time_range=time_range,
            language=language,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            auth=auth,
        )

        output = {
            "results": [dataclasses.asdict(r) for r in results],
            "total": len(results),
            "query": query,
        }

        logger.info(f"Found {len(results)} results for: {query}")
        return json.dumps(output, ensure_ascii=False, indent=2)

    except SearchError as e:
        error_msg = str(e)
        logger.error(f"SearXNG search failed: {error_msg}")

        # On connection errors, try restart + one more attempt
        if "Request error" in error_msg:
            logger.info("Attempting SearXNG restart before final retry...")
            if hosted:
                active_url = await _ensure_searxng_healthy(
                    active_url,
                    allow_local_restart=False,
                    use_settings_auth=False,
                )
            else:
                active_url = await _ensure_searxng_healthy(active_url)
            try:
                results = await _wc_search(
                    active_url,
                    query,
                    categories=categories,
                    max_results=max_results,
                    time_range=time_range,
                    language=language,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    auth=auth,
                )
                output = {
                    "results": [dataclasses.asdict(r) for r in results],
                    "total": len(results),
                    "query": query,
                }
                return json.dumps(output, ensure_ascii=False, indent=2)
            except SearchError:
                pass

        return json.dumps({"error": error_msg})
