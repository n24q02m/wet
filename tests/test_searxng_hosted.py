"""Hosted (per-subject) SearXNG URLs in ``wet.sources.searxng.search``.

A hosted URL comes from a subject's own configuration, so it is untrusted: it
is SSRF-vetted, never receives the operator's basic-auth credentials, and an
unhealthy instance is never "fixed" by spawning a local SearXNG. The network
boundaries (health probe, web-core search call, local runner) are stubbed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from hull_web.search import SearchError
from hull_web.search.models import SearchResult

from wet.sources import searxng

# A public IP literal: passes the SSRF check without a DNS lookup.
HOSTED_URL = "https://1.1.1.1"


def _results(n: int = 1) -> list[SearchResult]:
    return [
        SearchResult(
            url=f"https://r{i}.example.com",
            title=f"T{i}",
            snippet=f"S{i}",
            source="hosted",
        )
        for i in range(n)
    ]


@pytest.fixture
def operator_auth(monkeypatch):
    """Process-global basic auth an operator set for their own SearXNG."""
    monkeypatch.setattr(searxng.settings, "searxng_auth_user", "operator")
    monkeypatch.setattr(searxng.settings, "searxng_auth_pass", "operator-pass")


@pytest.fixture
def local_runner():
    with patch("wet.searxng_runner.ensure_searxng", AsyncMock()) as runner:
        yield runner


async def test_unsafe_hosted_url_is_blocked_before_any_request(local_runner):
    with (
        patch.object(searxng, "_check_health", AsyncMock()) as health,
        patch.object(searxng, "_wc_search", AsyncMock()) as wc_search,
    ):
        out = await searxng.search("http://localhost:8080", "q", hosted=True)

    assert json.loads(out) == {"error": "Security Alert: unsafe SearXNG URL blocked"}
    health.assert_not_awaited()
    wc_search.assert_not_awaited()
    local_runner.assert_not_awaited()


async def test_unhealthy_hosted_instance_is_searched_without_auth_or_restart(
    operator_auth, local_runner
):
    """An unhealthy hosted instance is still tried as-is: no local restart,
    and neither the probe nor the search carries the operator's credentials."""
    with (
        patch.object(searxng, "_check_health", AsyncMock(return_value=False)) as health,
        patch.object(searxng, "_wc_search", AsyncMock(return_value=_results(2))) as wc,
    ):
        out = await searxng.search(HOSTED_URL, "q", hosted=True)

    assert json.loads(out)["total"] == 2
    health.assert_awaited_once_with(HOSTED_URL, use_settings_auth=False)
    assert wc.await_args is not None
    assert wc.await_args.args[0] == HOSTED_URL
    assert wc.await_args.kwargs["auth"] is None
    local_runner.assert_not_awaited()


async def test_hosted_connection_error_retries_the_same_url_without_restart(
    operator_auth, local_runner
):
    """A connection error re-probes the hosted URL (still unauthenticated)
    and retries it once; the local runner is never involved."""
    with (
        patch.object(searxng, "_check_health", AsyncMock(return_value=False)) as health,
        patch.object(
            searxng,
            "_wc_search",
            AsyncMock(
                side_effect=[
                    SearchError("hosted", "Request error: connection reset"),
                    _results(1),
                ]
            ),
        ) as wc,
    ):
        out = await searxng.search(HOSTED_URL, "q", hosted=True)

    assert json.loads(out)["total"] == 1
    assert wc.await_count == 2
    assert all(call.kwargs["auth"] is None for call in wc.await_args_list)
    assert [call.kwargs for call in health.await_args_list] == [
        {"use_settings_auth": False},
        {"use_settings_auth": False},
    ]
    local_runner.assert_not_awaited()


async def test_managed_instance_with_operator_auth_keeps_it(operator_auth):
    """The non-hosted path is the contrast: the operator's own instance gets
    the configured basic auth."""
    with (
        patch.object(searxng, "_check_health", AsyncMock(return_value=True)),
        patch.object(searxng, "_wc_search", AsyncMock(return_value=_results(1))) as wc,
    ):
        await searxng.search("http://127.0.0.1:8080", "q")

    assert wc.await_args is not None
    assert wc.await_args.kwargs["auth"] == ("operator", "operator-pass")
