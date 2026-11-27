"""Idempotent retry and per-host circuit breaker for extract fetches.

Every test is deterministic: HTTP goes through ``httpx.MockTransport``, and
the clock, sleep and jitter source are injected so no test waits on a real
timer or touches the network.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from hull_web.scraper import ScrapingAgent
from hull_web.scraper.strategies import BasicHTTPStrategy

from wet.config import settings
from wet.sources import resilience
from wet.sources.resilience import (
    CircuitOpenError,
    FetchOutcome,
    HostCircuitBreaker,
    RetryingHttpClient,
    RetryPolicy,
    host_key,
    observe_fetches,
    request_with_retry,
)


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSleep:
    """Record requested delays and advance the fake clock instead of waiting."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        self.clock.advance(delay)


def _client(responder) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


def _sequence(*steps):
    """Build a MockTransport handler that replays ``steps`` in order.

    Each step is a status code, an ``(status, headers)`` tuple, or an
    exception class raised as a transport error.
    """
    calls: list[httpx.Request] = []
    queue = list(steps)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        step = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(step, type) and issubclass(step, Exception):
            raise step("boom", request=request)
        if isinstance(step, tuple):
            status, headers = step
            return httpx.Response(status, headers=headers, text="body")
        return httpx.Response(step, text="body")

    return handler, calls


POLICY = RetryPolicy(attempts=3, base_delay=0.5, max_delay=10.0, budget=30.0)


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


def test_backoff_is_exponential_with_bounded_jitter():
    assert POLICY.backoff(0, 0.0) == pytest.approx(0.25)
    assert POLICY.backoff(0, 1.0) == pytest.approx(0.5)
    assert POLICY.backoff(1, 1.0) == pytest.approx(1.0)
    assert POLICY.backoff(2, 0.5) == pytest.approx(1.5)


def test_backoff_is_capped_by_max_delay():
    policy = RetryPolicy(attempts=10, base_delay=1.0, max_delay=3.0, budget=60.0)
    assert policy.backoff(8, 1.0) == pytest.approx(3.0)
    assert policy.backoff(8, 0.0) == pytest.approx(1.5)


def test_policy_from_settings_uses_configured_values(monkeypatch):
    monkeypatch.setattr(settings, "extract_retry_attempts", 5)
    monkeypatch.setattr(settings, "extract_retry_base_delay", 0.1)
    monkeypatch.setattr(settings, "extract_retry_max_delay", 2.0)
    monkeypatch.setattr(settings, "extract_retry_budget", 9.0)
    assert RetryPolicy.from_settings() == RetryPolicy(
        attempts=5, base_delay=0.1, max_delay=2.0, budget=9.0
    )


def test_policy_from_settings_clamps_invalid_values(monkeypatch):
    monkeypatch.setattr(settings, "extract_retry_attempts", 0)
    monkeypatch.setattr(settings, "extract_retry_base_delay", -1.0)
    monkeypatch.setattr(settings, "extract_retry_max_delay", -1.0)
    monkeypatch.setattr(settings, "extract_retry_budget", -1.0)
    policy = RetryPolicy.from_settings()
    assert policy.attempts == 1
    assert policy.base_delay == 0.0
    assert policy.max_delay == 0.0
    assert policy.budget == 0.0


def test_settings_defaults_are_bounded():
    from wet.config import Settings

    fresh = Settings()
    assert fresh.extract_retry_attempts == 3
    assert fresh.extract_retry_base_delay == 0.5
    assert fresh.extract_retry_max_delay == 10.0
    assert fresh.extract_retry_budget == 30.0
    assert fresh.extract_breaker_threshold == 3
    assert fresh.extract_breaker_cooldown == 60.0


# ---------------------------------------------------------------------------
# request_with_retry
# ---------------------------------------------------------------------------


async def _call(handler, method="GET", policy=POLICY, rand=lambda: 1.0, **kwargs):
    clock = FakeClock()
    sleep = FakeSleep(clock)
    async with _client(handler) as client:
        response = await request_with_retry(
            client,
            method,
            "https://a.example/page",
            policy=policy,
            sleep=sleep,
            rand=rand,
            clock=clock,
            **kwargs,
        )
    return response, sleep.delays


@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_get_retries_transient_status_then_succeeds(status):
    handler, calls = _sequence(status, status, 200)
    response, delays = await _call(handler)
    assert response.status_code == 200
    assert len(calls) == 3
    assert delays == [pytest.approx(0.5), pytest.approx(1.0)]


async def test_jitter_scales_the_backoff_delay():
    handler, calls = _sequence(503, 200)
    _, delays = await _call(handler, rand=lambda: 0.0)
    assert len(calls) == 2
    assert delays == [pytest.approx(0.25)]


async def test_retry_exhaustion_returns_last_transient_response():
    handler, calls = _sequence(502)
    response, delays = await _call(handler)
    assert response.status_code == 502
    assert len(calls) == POLICY.attempts
    assert len(delays) == POLICY.attempts - 1


@pytest.mark.parametrize(
    "exc", [httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError]
)
async def test_transport_errors_are_retried_then_raised(exc):
    handler, calls = _sequence(exc)
    with pytest.raises(exc):
        await _call(handler)
    assert len(calls) == POLICY.attempts


async def test_transport_error_then_success():
    handler, calls = _sequence(httpx.ConnectTimeout, 200)
    response, delays = await _call(handler)
    assert response.status_code == 200
    assert len(calls) == 2
    assert delays == [pytest.approx(0.5)]


@pytest.mark.parametrize("status", [200, 301, 400, 403, 404, 500])
async def test_non_transient_status_is_not_retried(status):
    handler, calls = _sequence(status, 200)
    with observe_fetches() as outcome:
        response, delays = await _call(handler)
    assert response.status_code == status
    assert len(calls) == 1
    assert delays == []
    assert outcome.transient is False


@pytest.mark.parametrize("status", [520, 521, 522, 523, 524])
async def test_cloudflare_origin_down_is_transient_but_not_retried(status):
    handler, calls = _sequence(status, 200)
    with observe_fetches() as outcome:
        response, delays = await _call(handler)
    assert response.status_code == status
    assert len(calls) == 1
    assert delays == []
    assert outcome.transient is True
    assert outcome.retry_after is None


async def test_ssrf_block_style_request_error_is_not_retried():
    def handler(request):
        raise httpx.RequestError("SSRF blocked", request=request)

    with pytest.raises(httpx.RequestError):
        await _call(handler)


async def test_retry_after_seconds_header_is_honoured():
    handler, calls = _sequence((429, {"Retry-After": "2"}), 200)
    response, delays = await _call(handler)
    assert response.status_code == 200
    assert len(calls) == 2
    assert delays == [pytest.approx(2.0)]


async def test_retry_after_http_date_is_honoured():
    handler, calls = _sequence(
        (503, {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}), 200
    )
    # A past HTTP-date means "retry now" (zero delay).
    response, delays = await _call(handler)
    assert response.status_code == 200
    assert delays == [pytest.approx(0.0)]


async def test_retry_after_beyond_max_delay_gives_up_without_waiting():
    handler, calls = _sequence((429, {"Retry-After": "120"}), 200)
    with observe_fetches() as outcome:
        response, delays = await _call(handler)
    assert response.status_code == 429
    assert len(calls) == 1
    assert delays == []
    assert outcome.transient is True
    assert outcome.retry_after == pytest.approx(120.0)


async def test_budget_stops_retrying_before_exceeding_total_wait():
    policy = RetryPolicy(attempts=10, base_delay=1.0, max_delay=8.0, budget=3.5)
    handler, calls = _sequence(503)
    response, delays = await _call(handler, policy=policy)
    # 1.0 + 2.0 fits in 3.5s; the next 4.0s delay would exceed it.
    assert response.status_code == 503
    assert delays == [pytest.approx(1.0), pytest.approx(2.0)]
    assert len(calls) == 3


async def test_budget_exhaustion_reraises_transport_error():
    policy = RetryPolicy(attempts=10, base_delay=1.0, max_delay=8.0, budget=0.5)
    handler, calls = _sequence(httpx.ConnectError)
    with pytest.raises(httpx.ConnectError):
        await _call(handler, policy=policy)
    assert len(calls) == 1


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_non_idempotent_method_is_not_retried_on_status(method):
    handler, calls = _sequence(503, 200)
    response, delays = await _call(handler, method=method)
    assert response.status_code == 503
    assert len(calls) == 1
    assert delays == []


async def test_non_idempotent_method_is_not_retried_on_transport_error():
    handler, calls = _sequence(httpx.ConnectError, 200)
    with pytest.raises(httpx.ConnectError):
        await _call(handler, method="post")
    assert len(calls) == 1


async def test_head_is_idempotent_and_retried():
    handler, calls = _sequence(503, 200)
    response, _ = await _call(handler, method="head")
    assert response.status_code == 200
    assert [c.method for c in calls] == ["HEAD", "HEAD"]


async def test_request_kwargs_are_forwarded():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200)

    await _call(handler, headers={"X-Probe": "1"})
    assert seen[0].headers["X-Probe"] == "1"


async def test_default_policy_comes_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "extract_retry_attempts", 2)
    monkeypatch.setattr(settings, "extract_retry_base_delay", 0.0)
    handler, calls = _sequence(503)
    clock = FakeClock()
    async with _client(handler) as client:
        response = await request_with_retry(
            client, "GET", "https://a.example/", sleep=FakeSleep(clock), clock=clock
        )
    assert response.status_code == 503
    assert len(calls) == 2


async def test_outcome_tracks_last_fetch_classification():
    with observe_fetches() as outcome:
        handler, _ = _sequence(503)
        await _call(handler)
        assert outcome.transient is True
        handler, _ = _sequence(404)
        await _call(handler)
        assert outcome.transient is False
    assert isinstance(outcome, FetchOutcome)


async def test_outcome_outside_observation_is_ignored():
    handler, calls = _sequence(503, 200)
    response, _ = await _call(handler)
    assert response.status_code == 200


async def test_retrying_http_client_wraps_factory_and_retries():
    handler, calls = _sequence(503, 200)
    made: list[dict] = []

    def factory(**kwargs):
        made.append(kwargs)
        return _client(handler)

    clock = FakeClock()
    adapter = RetryingHttpClient(
        factory, policy=POLICY, sleep=FakeSleep(clock), rand=lambda: 0.0, clock=clock
    )
    response = await adapter.get(
        "https://a.example/", headers={"User-Agent": "t"}, timeout=5
    )
    assert response.status_code == 200
    assert len(calls) == 2
    assert made == [{}]
    assert calls[0].headers["User-Agent"] == "t"


# ---------------------------------------------------------------------------
# host_key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://Example.COM/a/b", "example.com"),
        ("http://example.com:8080/x", "example.com:8080"),
        ("https://sub.example.com", "sub.example.com"),
        ("not a url", ""),
        # Userinfo never leaks into the key.
        ("https://user:pw@Example.com:8443/x", "example.com:8443"),
        ("https://example.com@evil.example/x", "evil.example"),
        # IPv6 literals are bracketed, so the port cannot merge into the address.
        ("http://[::1]:8080/x", "[::1]:8080"),
        ("http://[::1:8080]/x", "[::1:8080]"),
        ("http://[0:0::1]/x", "[::1]"),
        ("https://[::1]:443/x", "[::1]"),
        ("http://[::1/x", ""),
        # Trailing dot, IDN and punycode spellings share one key.
        ("https://example.com./x", "example.com"),
        ("https://bücher.example/x", "xn--bcher-kva.example"),
        ("https://BÜCHER.example./x", "xn--bcher-kva.example"),
        ("https://xn--bcher-kva.example/x", "xn--bcher-kva.example"),
        ("https://faß.de/x", "xn--fa-hia.de"),
        ("https://bad。example/x", "bad.example"),
        ("https://my_host.example/x", "my_host.example"),
    ],
)
def test_host_key_normalises(url, expected):
    assert host_key(url) == expected


# ---------------------------------------------------------------------------
# HostCircuitBreaker
# ---------------------------------------------------------------------------


def _breaker(threshold=3, cooldown=60.0, **kwargs):
    clock = FakeClock()
    return HostCircuitBreaker(
        threshold=threshold, cooldown=cooldown, clock=clock, **kwargs
    ), clock


def test_breaker_opens_after_threshold_consecutive_failures():
    breaker, clock = _breaker()
    for _ in range(2):
        assert breaker.before_request("down.example") is None
        breaker.record_failure("down.example")
    assert breaker.before_request("down.example") is None
    breaker.record_failure("down.example")

    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")
    err = info.value
    assert err.host == "down.example"
    assert err.retry_after == pytest.approx(60.0)
    assert "down.example" in str(err)
    assert "retry after 60s" in str(err)


def test_open_breaker_fails_fast_until_cooldown_elapses():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure("down.example")
    clock.advance(20.0)
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")
    assert info.value.retry_after == pytest.approx(10.0)
    assert "retry after 10s" in str(info.value)


def test_success_resets_consecutive_failure_count():
    breaker, _ = _breaker()
    breaker.record_failure("flaky.example")
    breaker.record_failure("flaky.example")
    breaker.record_success("flaky.example")
    breaker.record_failure("flaky.example")
    breaker.record_failure("flaky.example")
    assert breaker.before_request("flaky.example") is None


def test_half_open_allows_single_probe_and_success_closes():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure("down.example")
    clock.advance(30.0)

    probe = breaker.before_request("down.example")
    assert probe is not None  # the probe
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")  # concurrent caller
    assert info.value.probing is True
    assert "down.example" in str(info.value)

    breaker.record_success("down.example", probe)
    assert breaker.before_request("down.example") is None
    assert breaker.before_request("down.example") is None


def test_half_open_probe_failure_reopens_for_full_cooldown():
    breaker, clock = _breaker(threshold=3, cooldown=30.0)
    for _ in range(3):
        breaker.record_failure("down.example")
    clock.advance(31.0)
    probe = breaker.before_request("down.example")
    assert probe is not None

    breaker.record_failure("down.example", token=probe)
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")
    assert info.value.probing is False
    assert info.value.retry_after == pytest.approx(30.0)


def test_released_probe_lets_the_next_caller_probe():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure("down.example")
    clock.advance(30.0)
    probe = breaker.before_request("down.example")
    assert probe is not None
    breaker.release("down.example", probe)
    assert breaker.before_request("down.example") not in (None, probe)


def test_probe_outliving_the_cooldown_keeps_its_slot():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure("down.example")
    clock.advance(30.0)
    probe = breaker.before_request("down.example")
    assert probe is not None

    clock.advance(90.0)  # three cooldowns later the probe is still running
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")
    assert info.value.probing is True
    assert info.value.retry_after == pytest.approx(resilience.PROBE_TIMEOUT - 90.0)

    breaker.record_success("down.example", probe)
    assert breaker.before_request("down.example") is None


def test_abandoned_probe_lease_expires_after_the_probe_timeout():
    breaker, clock = _breaker(threshold=1, cooldown=30.0, probe_timeout=120.0)
    breaker.record_failure("down.example")
    clock.advance(30.0)
    assert breaker.before_request("down.example") is not None
    clock.advance(119.0)
    with pytest.raises(CircuitOpenError):
        breaker.before_request("down.example")
    clock.advance(1.0)
    assert breaker.before_request("down.example") is not None


def test_stale_probe_token_cannot_settle_or_release_a_newer_probe():
    breaker, clock = _breaker(threshold=1, cooldown=30.0, probe_timeout=60.0)
    breaker.record_failure("down.example")
    clock.advance(30.0)
    stale = breaker.before_request("down.example")
    clock.advance(60.0)  # the first lease ran out; a second probe takes over
    current = breaker.before_request("down.example")
    assert current is not None and current != stale

    breaker.release("down.example", stale)
    breaker.record_success("down.example", stale)
    breaker.record_failure("down.example", token=stale)
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")
    assert info.value.probing is True

    breaker.record_failure("down.example", token=current)
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")
    assert info.value.probing is False
    assert info.value.retry_after == pytest.approx(30.0)


def test_results_without_the_probe_token_are_ignored_while_open():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure("down.example")
    clock.advance(10.0)
    # Requests admitted before the circuit opened end after it did.
    breaker.record_failure("down.example")
    breaker.record_success("down.example")
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")
    assert info.value.retry_after == pytest.approx(20.0)

    clock.advance(20.0)
    probe = breaker.before_request("down.example")
    breaker.record_success("down.example")
    breaker.record_failure("down.example")
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")
    assert info.value.probing is True
    breaker.record_success("down.example", probe)
    assert breaker.before_request("down.example") is None


def test_probe_token_from_an_earlier_cycle_is_ignored_once_closed():
    breaker, clock = _breaker(threshold=2, cooldown=30.0)
    breaker.record_failure("down.example")
    breaker.record_failure("down.example")
    clock.advance(30.0)
    probe = breaker.before_request("down.example")
    breaker.record_success("down.example", probe)

    breaker.record_failure("down.example")
    breaker.record_failure("down.example", token=probe)  # not counted
    assert breaker.before_request("down.example") is None
    breaker.record_success("down.example", probe)  # does not reset the count
    breaker.record_failure("down.example")
    with pytest.raises(CircuitOpenError):
        breaker.before_request("down.example")


def test_zero_cooldown_makes_every_request_after_the_threshold_a_probe():
    breaker, _ = _breaker(threshold=1, cooldown=0.0)
    breaker.record_failure("down.example")
    probe = breaker.before_request("down.example")
    assert probe is not None
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")  # still one probe at a time
    assert info.value.probing is True

    breaker.record_failure("down.example", token=probe)
    second = breaker.before_request("down.example")
    assert second is not None and second != probe


async def test_concurrent_callers_get_exactly_one_probe():
    breaker, clock = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure("down.example")
    clock.advance(30.0)

    async def caller():
        await asyncio.sleep(0)
        try:
            return breaker.before_request("down.example")
        except CircuitOpenError as exc:
            return exc

    results = await asyncio.gather(*(caller() for _ in range(20)))
    probes = [r for r in results if isinstance(r, int)]
    refused = [r for r in results if isinstance(r, CircuitOpenError)]
    assert len(probes) == 1
    assert len(refused) == 19
    assert all(exc.probing for exc in refused)


def test_release_without_probe_is_harmless():
    breaker, _ = _breaker()
    breaker.release("never.example", 1)
    breaker.record_failure("once.example")
    breaker.release("once.example", 1)
    assert breaker.before_request("once.example") is None


def test_breaker_state_does_not_leak_across_hosts():
    breaker, _ = _breaker(threshold=1)
    breaker.record_failure("down.example")
    with pytest.raises(CircuitOpenError):
        breaker.before_request("down.example")
    assert breaker.before_request("up.example") is None
    assert breaker.before_request("down.example:8443") is None


def test_retry_after_hint_extends_cooldown_with_a_cap():
    breaker, _ = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure("slow.example", retry_after=90.0)
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("slow.example")
    assert info.value.retry_after == pytest.approx(90.0)

    breaker.record_failure("hostile.example", retry_after=10_000_000.0)
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("hostile.example")
    assert info.value.retry_after == pytest.approx(resilience.MAX_COOLDOWN)


def test_short_retry_after_hint_never_shortens_cooldown():
    breaker, _ = _breaker(threshold=1, cooldown=30.0)
    breaker.record_failure("down.example", retry_after=1.0)
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("down.example")
    assert info.value.retry_after == pytest.approx(30.0)


def test_threshold_zero_disables_the_breaker():
    breaker, _ = _breaker(threshold=0)
    for _ in range(10):
        breaker.record_failure("down.example")
    assert breaker.before_request("down.example") is None


def test_breaker_bounds_tracked_hosts():
    clock = FakeClock()
    breaker = HostCircuitBreaker(threshold=1, cooldown=30.0, clock=clock, max_hosts=2)
    breaker.record_failure("a.example")
    breaker.record_failure("b.example")
    breaker.record_failure("c.example")  # evicts the oldest host
    assert breaker.before_request("a.example") is None
    with pytest.raises(CircuitOpenError):
        breaker.before_request("c.example")


def test_empty_host_is_never_gated():
    breaker, _ = _breaker(threshold=1)
    breaker.record_failure("")
    assert breaker.before_request("") is None


def test_extract_breaker_singleton_reads_settings(monkeypatch):
    monkeypatch.setattr(settings, "extract_breaker_threshold", 7)
    monkeypatch.setattr(settings, "extract_breaker_cooldown", 12.0)
    resilience.reset_extract_breaker()
    breaker = resilience.extract_breaker()
    assert breaker is resilience.extract_breaker()
    assert breaker.threshold == 7
    assert breaker.cooldown == 12.0
    assert breaker.probe_timeout == resilience.PROBE_TIMEOUT
    resilience.reset_extract_breaker()
    assert resilience.extract_breaker() is not breaker


# ---------------------------------------------------------------------------
# crawler.extract integration (real ScrapingAgent, mocked transport)
# ---------------------------------------------------------------------------


@pytest.fixture
def fast_retry(monkeypatch):
    """Zero backoff so integration tests never sleep for real."""
    monkeypatch.setattr(settings, "extract_retry_attempts", 2)
    monkeypatch.setattr(settings, "extract_retry_base_delay", 0.0)
    monkeypatch.setattr(settings, "extract_retry_max_delay", 0.0)


@pytest.fixture
def breaker_clock(monkeypatch):
    clock = FakeClock()
    breaker = HostCircuitBreaker(threshold=2, cooldown=30.0, clock=clock)
    monkeypatch.setattr(resilience, "_extract_breaker", breaker)
    return clock


def _http_only_agent(handler) -> ScrapingAgent:
    adapter = RetryingHttpClient(lambda **_: _client(handler))
    return ScrapingAgent(
        strategies={"basic_http": BasicHTTPStrategy(timeout=5, http_client=adapter)},
        respect_robots=False,
    )


@pytest.fixture
def allow_hosts(monkeypatch):
    monkeypatch.setattr("wet.sources.crawler.is_safe_url", lambda url: True)
    monkeypatch.setattr(
        "hull_web.scraper.strategies.basic_http.is_safe_url", lambda url: True
    )


async def _extract(agent, urls):
    from wet.sources import crawler

    with patch.object(crawler, "_get_scraping_agent", AsyncMock(return_value=agent)):
        return json.loads(await crawler.extract(urls))


HTML = (
    "<html><head><title>Ok</title></head><body>"
    + ("<p>word</p>" * 50)
    + "</body></html>"
)


async def test_extract_opens_breaker_and_then_fails_fast(
    fast_retry, breaker_clock, allow_hosts
):
    calls: list[str] = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(503, text="down")

    agent = _http_only_agent(handler)
    for i in range(2):
        [entry] = await _extract(agent, [f"https://down.example/{i}"])
        assert "error" in entry
    hits_before = len(calls)
    assert hits_before == 4  # 2 extracts x 2 attempts

    [entry] = await _extract(agent, ["https://down.example/2"])
    assert len(calls) == hits_before  # fast fail, no request sent
    assert "down.example" in entry["error"]
    assert "retry after 30s" in entry["error"]
    assert entry["retry_after"] == 30


async def test_extract_breaker_is_per_host(fast_retry, breaker_clock, allow_hosts):
    def handler(request):
        if request.url.host == "down.example":
            return httpx.Response(503, text="down")
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    agent = _http_only_agent(handler)
    for i in range(2):
        await _extract(agent, [f"https://down.example/{i}"])

    entries = await _extract(agent, ["https://down.example/x", "https://up.example/x"])
    by_url = {e["url"]: e for e in entries}
    assert "retry after" in by_url["https://down.example/x"]["error"]
    assert "error" not in by_url["https://up.example/x"]


async def test_extract_definitive_http_errors_do_not_open_breaker(
    fast_retry, breaker_clock, allow_hosts
):
    calls: list[str] = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(404, text="missing")

    agent = _http_only_agent(handler)
    for i in range(4):
        [entry] = await _extract(agent, [f"https://up.example/{i}"])
        assert "error" in entry
        assert "retry after" not in entry["error"]
    assert len(calls) == 4


async def test_extract_half_open_probe_success_closes_breaker(
    fast_retry, breaker_clock, allow_hosts
):
    healthy = {"value": False}

    def handler(request):
        if healthy["value"]:
            return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
        return httpx.Response(503, text="down")

    agent = _http_only_agent(handler)
    for i in range(2):
        await _extract(agent, [f"https://down.example/{i}"])

    breaker_clock.advance(30.0)
    healthy["value"] = True
    [probe] = await _extract(agent, ["https://down.example/probe"])
    assert "error" not in probe
    [after] = await _extract(agent, ["https://down.example/after"])
    assert "error" not in after


async def test_extract_half_open_probe_failure_reopens(
    fast_retry, breaker_clock, allow_hosts
):
    calls: list[str] = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(503, text="down")

    agent = _http_only_agent(handler)
    for i in range(2):
        await _extract(agent, [f"https://down.example/{i}"])
    breaker_clock.advance(30.0)

    [probe] = await _extract(agent, ["https://down.example/probe"])
    assert "retry after" not in probe["error"]  # the probe really ran
    hits = len(calls)
    [entry] = await _extract(agent, ["https://down.example/next"])
    assert "retry after 30s" in entry["error"]
    assert len(calls) == hits


async def test_extract_releases_probe_when_cancelled(breaker_clock, allow_hosts):
    import asyncio

    from wet.sources import crawler

    breaker = resilience.extract_breaker()
    breaker.record_failure("slow.example")
    breaker.record_failure("slow.example")
    breaker_clock.advance(30.0)

    started = asyncio.Event()

    async def hang(url):
        started.set()
        await asyncio.sleep(3600)

    agent = MagicMock()
    agent.scrape = hang
    with patch.object(crawler, "_get_scraping_agent", AsyncMock(return_value=agent)):
        task = asyncio.create_task(crawler.extract(["https://slow.example/a"]))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    # The cancelled probe released its slot: the next caller may probe.
    assert breaker.before_request("slow.example") is not None


async def test_extract_probe_past_its_deadline_counts_as_a_failure(
    breaker_clock, allow_hosts, monkeypatch
):
    from wet.sources import crawler

    breaker = HostCircuitBreaker(
        threshold=1, cooldown=30.0, clock=breaker_clock, probe_timeout=0.05
    )
    monkeypatch.setattr(resilience, "_extract_breaker", breaker)
    breaker.record_failure("slow.example")
    breaker_clock.advance(30.0)

    async def hang(url):
        await asyncio.sleep(3600)

    agent = MagicMock()
    agent.scrape = hang
    with patch.object(crawler, "_get_scraping_agent", AsyncMock(return_value=agent)):
        [entry] = json.loads(await crawler.extract(["https://slow.example/a"]))
    assert "timed out" in entry["error"].lower()
    assert "retry_after" not in entry
    with pytest.raises(CircuitOpenError) as info:
        breaker.before_request("slow.example")
    assert info.value.probing is False
    assert info.value.retry_after == pytest.approx(30.0)


async def test_concurrent_extracts_send_exactly_one_probe(
    fast_retry, breaker_clock, allow_hosts, monkeypatch
):
    from wet.sources import crawler

    monkeypatch.setattr(crawler, "_browser_semaphore", None)
    entered = asyncio.Event()
    gate = asyncio.Event()
    calls: list[str] = []

    async def handler(request):
        calls.append(str(request.url))
        entered.set()
        await gate.wait()
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    agent = _http_only_agent(handler)
    breaker = resilience.extract_breaker()
    breaker.record_failure("down.example")
    breaker.record_failure("down.example")
    breaker_clock.advance(30.0)

    def wave(tag):
        return asyncio.gather(
            *(crawler.extract([f"https://down.example/{tag}{i}"]) for i in range(5))
        )

    with patch.object(crawler, "_get_scraping_agent", AsyncMock(return_value=agent)):
        first = asyncio.ensure_future(wave("a"))
        await entered.wait()
        breaker_clock.advance(90.0)  # the probe outlives the 30s cooldown
        second = await wave("b")
        assert len(calls) == 1
        gate.set()
        entries = [json.loads(raw)[0] for raw in [*await first, *second]]
        [after] = json.loads(await crawler.extract(["https://down.example/after"]))

    assert len(calls) == 2  # the probe, then the request after it closed
    assert sum("error" not in entry for entry in entries) == 1
    refused = [entry for entry in entries if "error" in entry]
    assert len(refused) == 9
    assert all("probe is already in flight" in e["error"] for e in refused)
    assert "error" not in after


async def test_extract_cloudflare_origin_down_opens_breaker(
    fast_retry, breaker_clock, allow_hosts
):
    calls: list[str] = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(522, text="origin down")

    agent = _http_only_agent(handler)
    for i in range(2):
        [entry] = await _extract(agent, [f"https://down.example/{i}"])
        assert "error" in entry
    assert len(calls) == 2  # 522 is not retried

    [entry] = await _extract(agent, ["https://down.example/2"])
    assert len(calls) == 2
    assert "retry after 30s" in entry["error"]


async def test_markitdown_download_retries_transient_status(fast_retry, allow_hosts):
    from wet.sources import crawler

    handler, calls = _sequence(503, 200)
    with (
        patch.object(crawler, "_safe_httpx_client", lambda **_: _client(handler)),
        patch("markitdown.MarkItDown") as md_cls,
    ):
        md_cls.return_value.convert_stream.return_value = MagicMock(
            text_content="converted"
        )
        result = await crawler._extract_with_markitdown("https://docs.example/a.pdf")
    assert result["content"] == "converted"
    assert len(calls) == 2


def test_scraping_agent_basic_http_uses_retrying_client(monkeypatch):
    from wet.sources.crawler import _build_scraping_agent

    monkeypatch.setattr(settings, "browser_backends", "")
    monkeypatch.setattr(settings, "capsolver_api_key", "")
    agent = _build_scraping_agent(stealth=True)
    basic = agent.strategies["basic_http"]
    assert isinstance(basic._http_client, RetryingHttpClient)


# ---------------------------------------------------------------------------
# structured extraction surfaces per-URL failures
# ---------------------------------------------------------------------------


async def test_structured_extract_reports_url_errors_when_nothing_extracted():
    from wet.sources import structured

    payload = json.dumps(
        [
            {
                "url": "https://down.example/a",
                "error": "Circuit open for down.example; retry after 30s.",
                "retry_after": 30,
            }
        ]
    )
    with (
        patch.object(structured, "raw_extract", AsyncMock(return_value=payload)),
        patch.object(structured, "has_llm_provider", return_value=True),
    ):
        out = json.loads(
            await structured.extract_structured(
                ["https://down.example/a"],
                {"type": "object", "properties": {"title": {"type": "string"}}},
                prompt="extract",
            )
        )
    assert out["error"] == "No content extracted from the provided URLs."
    assert out["url_errors"] == [
        {
            "url": "https://down.example/a",
            "error": "Circuit open for down.example; retry after 30s.",
        }
    ]


# ---------------------------------------------------------------------------
# tool-level cache never stores open-circuit answers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload,is_error",
    [
        (json.dumps([{"url": "https://a.example/", "markdown": "ok"}]), False),
        (
            json.dumps(
                [
                    {"url": "https://a.example/", "markdown": "ok"},
                    {"url": "https://b.example/", "error": "x", "retry_after": 5},
                ]
            ),
            True,
        ),
        (json.dumps([{"url": "https://a.example/", "error": "HTTP 404"}]), False),
        (json.dumps(["not a dict"]), False),
    ],
)
def test_payload_with_open_circuit_entry_is_not_cacheable(payload, is_error):
    from wet.server import _payload_is_error

    assert _payload_is_error(payload) is is_error
