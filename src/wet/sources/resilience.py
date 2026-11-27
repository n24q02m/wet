"""Idempotent HTTP retry and a per-host circuit breaker for extract fetches.

Two independent pieces:

- :func:`request_with_retry` retries GET/HEAD on transient failures
  (connection errors, timeouts, 429/502/503/504) with bounded exponential
  backoff and jitter, honouring ``Retry-After``. Other methods get a single
  attempt. Cloudflare's origin-down statuses (520-524) count as transient
  for the breaker but are not retried. :class:`RetryingHttpClient` adapts it
  to the ``http_client`` hook of the hull-web ``BasicHTTPStrategy``.
- :class:`HostCircuitBreaker` tracks consecutive transient failures per host.
  After ``threshold`` of them the host is open: callers fail fast with
  :class:`CircuitOpenError` until the cooldown ends, then one half-open probe
  is let through. The probe holds a token and only that token's result
  counts: a probe success closes the circuit; a probe failure opens it again
  for a full cooldown.

The breaker counts whole extract operations, not single HTTP attempts. The
retry layer reports how the last fetch inside an operation ended through
:func:`observe_fetches`, so a 404 (the host answered) never trips the breaker
while a host that keeps timing out does.

Clock, sleep and jitter are injectable so tests never wait on real timers.
"""

from __future__ import annotations

import asyncio
import contextvars
import itertools
import math
import random
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from hull_core.credentials import parse_retry_after

from wet.config import settings
from wet.sources.hosts import normalize_host

IDEMPOTENT_METHODS = frozenset({"GET", "HEAD"})
RETRY_STATUSES = frozenset({429, 502, 503, 504})
# Cloudflare: the origin is down or unreachable (520-524). Retrying at once
# rarely helps, but the host is failing, so these still feed the breaker.
ORIGIN_DOWN_STATUSES = frozenset(range(520, 525))
TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)
# Upper bound for configured attempts; the time budget bounds the rest.
MAX_ATTEMPTS = 10
# Upper bound for a server-supplied Retry-After stretching the breaker
# cooldown, so a hostile header cannot park a host for days.
MAX_COOLDOWN = 900.0
# Hosts tracked by one breaker; the least recently failing is evicted first.
DEFAULT_MAX_HOSTS = 1024
# Longest a half-open probe may run. The probe's slot is leased for this long
# and extract gives up on a probe at the same deadline, so a slow probe keeps
# its slot until it ends instead of losing it after one cooldown.
PROBE_TIMEOUT = 300.0

_DEFAULT_PORTS = {"http": 80, "https": 443}

Sleep = Callable[[float], Awaitable[Any]]
Clock = Callable[[], float]
Rand = Callable[[], float]


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """Retry limits for one fetch.

    ``attempts`` counts the first try. ``budget`` caps the total seconds a
    fetch may spend (requests plus waits) before it stops retrying.
    """

    attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 10.0
    budget: float = 30.0

    @classmethod
    def from_settings(cls) -> RetryPolicy:
        return cls(
            attempts=min(max(1, int(settings.extract_retry_attempts)), MAX_ATTEMPTS),
            base_delay=max(0.0, float(settings.extract_retry_base_delay)),
            max_delay=max(0.0, float(settings.extract_retry_max_delay)),
            budget=max(0.0, float(settings.extract_retry_budget)),
        )

    def backoff(self, retry: int, jitter: float) -> float:
        """Delay before retry number ``retry`` (0-based), "equal jitter" style.

        The ceiling doubles per retry up to ``max_delay``; the delay is drawn
        from ``[ceiling / 2, ceiling]`` with ``jitter`` in ``[0, 1]``.
        """
        ceiling = min(self.max_delay, self.base_delay * 2 ** min(retry, 32))
        half = ceiling / 2
        return half + half * min(max(jitter, 0.0), 1.0)


@dataclass
class FetchOutcome:
    """How the last fetch observed in an operation ended.

    ``transient`` is None until a fetch is observed, True when the host
    failed transiently (connection error, timeout, 429/502/503/504, or a
    Cloudflare 520-524) and False when it answered definitively.
    ``retry_after`` carries the server hint.
    """

    transient: bool | None = None
    retry_after: float | None = None


_CURRENT_OUTCOME: contextvars.ContextVar[FetchOutcome | None] = contextvars.ContextVar(
    "wet_fetch_outcome", default=None
)


@contextmanager
def observe_fetches() -> Generator[FetchOutcome]:
    """Collect the classification of fetches made inside the block.

    Tasks spawned inside the block copy the context, so they report into the
    same :class:`FetchOutcome`.
    """
    outcome = FetchOutcome()
    token = _CURRENT_OUTCOME.set(outcome)
    try:
        yield outcome
    finally:
        _CURRENT_OUTCOME.reset(token)


def _report(transient: bool, retry_after: float | None = None) -> None:
    outcome = _CURRENT_OUTCOME.get()
    if outcome is not None:
        outcome.transient = transient
        outcome.retry_after = retry_after


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    policy: RetryPolicy | None = None,
    sleep: Sleep | None = None,
    rand: Rand | None = None,
    clock: Clock | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Send a request, retrying idempotent methods on transient failures.

    Returns the final response, which may still be a retryable status once
    attempts or the budget run out. A transient transport error on the last
    attempt is re-raised. A ``Retry-After`` beyond ``policy.max_delay`` ends
    retrying at once instead of waiting that long.
    """
    policy = policy or RetryPolicy.from_settings()
    sleep = sleep or asyncio.sleep
    rand = rand or random.random
    clock = clock or time.monotonic
    verb = method.upper()
    attempts = policy.attempts if verb in IDEMPOTENT_METHODS else 1
    started = clock()

    def _can_wait(retry: int, delay: float) -> bool:
        return retry + 1 < attempts and clock() - started + delay <= policy.budget

    retry = 0
    while True:
        try:
            response = await client.request(verb, url, **kwargs)
        except TRANSIENT_ERRORS:
            _report(True)
            delay = policy.backoff(retry, rand())
            if not _can_wait(retry, delay):
                raise
        else:
            if response.status_code not in RETRY_STATUSES:
                _report(response.status_code in ORIGIN_DOWN_STATUSES)
                return response
            hint = parse_retry_after(response.headers.get("Retry-After"))
            _report(True, hint)
            if hint is not None and hint > policy.max_delay:
                return response
            delay = hint if hint is not None else policy.backoff(retry, rand())
            if not _can_wait(retry, delay):
                return response
            await response.aclose()
        await sleep(delay)
        retry += 1


class RetryingHttpClient:
    """``get``-only HTTP adapter with idempotent retry.

    Fits the ``http_client`` hook of hull-web's ``BasicHTTPStrategy``. A fresh
    client comes from ``factory`` for each fetch (the factory carries the SSRF
    guard); per-request options such as ``timeout`` and ``headers`` pass
    through. Per-request cookies become client cookies, since httpx
    deprecates setting them per request.
    """

    def __init__(
        self,
        factory: Callable[..., httpx.AsyncClient],
        *,
        policy: RetryPolicy | None = None,
        sleep: Sleep | None = None,
        rand: Rand | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._factory = factory
        self._policy = policy
        self._sleep = sleep
        self._rand = rand
        self._clock = clock

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        cookies = kwargs.pop("cookies", None)
        client_kwargs: dict[str, Any] = {"cookies": cookies} if cookies else {}
        async with self._factory(**client_kwargs) as client:
            return await request_with_retry(
                client,
                "GET",
                url,
                policy=self._policy,
                sleep=self._sleep,
                rand=self._rand,
                clock=self._clock,
                **kwargs,
            )


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


def host_key(url: str) -> str:
    """Breaker key for ``url``: normalised host plus any non-default port.

    The host goes through :func:`~wet.sources.hosts.normalize_host`, so all
    spellings of one host share a key and an IPv6 literal stays bracketed.
    """
    try:
        parts = urlsplit(url)
        host = normalize_host(parts.hostname or "")
        port = parts.port
    except ValueError:
        return ""
    if not host:
        return ""
    if port is not None and port != _DEFAULT_PORTS.get(parts.scheme):
        return f"{host}:{port}"
    return host


class CircuitOpenError(Exception):
    """Raised instead of contacting a host whose circuit is open."""

    def __init__(self, host: str, retry_after: float, *, probing: bool = False):
        self.host = host
        self.retry_after = max(0.0, retry_after)
        self.probing = probing
        if probing:
            reason = "a recovery probe is already in flight"
        else:
            reason = "recent requests failed with transient errors"
        super().__init__(
            f"Circuit open for {host}: {reason}; retry after {self.retry_seconds}s."
        )

    @property
    def retry_seconds(self) -> int:
        """``retry_after`` rounded up to whole seconds (at least 1)."""
        return max(1, math.ceil(round(self.retry_after, 3)))


@dataclass
class _HostState:
    failures: int = 0
    opened: bool = False
    open_until: float = 0.0
    probe_token: int | None = None
    probe_until: float = 0.0


class HostCircuitBreaker:
    """Per-host breaker: closed, open, then one half-open probe.

    State lives per host key, so one failing host never gates another.
    ``threshold <= 0`` disables the breaker. An empty host is never gated.
    While a host is open only its current probe's token can change its
    state; results of requests admitted earlier are ignored. With a zero
    cooldown every request after the threshold is a probe, one at a time.
    """

    def __init__(
        self,
        threshold: int,
        cooldown: float,
        *,
        clock: Clock | None = None,
        max_hosts: int = DEFAULT_MAX_HOSTS,
        probe_timeout: float = PROBE_TIMEOUT,
    ) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self.probe_timeout = probe_timeout
        self._clock = clock or time.monotonic
        self._max_hosts = max(1, max_hosts)
        self._hosts: OrderedDict[str, _HostState] = OrderedDict()
        self._tokens = itertools.count(1)

    def _enabled(self, host: str) -> bool:
        return self.threshold > 0 and bool(host)

    def before_request(self, host: str) -> int | None:
        """Gate a request to ``host``.

        Returns None when the circuit is closed. The half-open probe gets a
        token instead and must end with :meth:`record_success`,
        :meth:`record_failure` or :meth:`release` given that token. Raises
        :class:`CircuitOpenError` while the circuit is open or another probe
        is in flight. The probe's slot is leased for ``probe_timeout``
        seconds; after that a new probe may take it.
        """
        if not self._enabled(host):
            return None
        state = self._hosts.get(host)
        if state is None or not state.opened:
            return None
        now = self._clock()
        if now < state.open_until:
            raise CircuitOpenError(host, state.open_until - now)
        if state.probe_token is not None and now < state.probe_until:
            raise CircuitOpenError(host, state.probe_until - now, probing=True)
        state.probe_token = next(self._tokens)
        state.probe_until = now + self.probe_timeout
        return state.probe_token

    @staticmethod
    def _settles(state: _HostState | None, token: int | None) -> bool:
        """Whether a result reported with ``token`` may change ``state``.

        While open only the current probe's token counts; while closed only
        ordinary requests (no token) do.
        """
        if state is not None and state.opened:
            return token is not None and token == state.probe_token
        return token is None

    def record_success(self, host: str, token: int | None = None) -> None:
        """The host answered: close its circuit and forget its failures."""
        if host and self._settles(self._hosts.get(host), token):
            self._hosts.pop(host, None)

    def record_failure(
        self,
        host: str,
        retry_after: float | None = None,
        *,
        token: int | None = None,
    ) -> None:
        """Count a transient failure; open the circuit at the threshold.

        A failure of the current probe re-opens for a full cooldown. A
        ``retry_after`` hint can stretch the cooldown (capped at
        :data:`MAX_COOLDOWN`) but never shorten it.
        """
        if not self._enabled(host):
            return
        state = self._hosts.get(host)
        if not self._settles(state, token):
            return
        if state is None:
            state = self._hosts[host] = _HostState()
            while len(self._hosts) > self._max_hosts:
                self._hosts.popitem(last=False)
        else:
            self._hosts.move_to_end(host)
        state.failures += 1
        if state.failures < self.threshold:
            return
        hint = min(retry_after or 0.0, MAX_COOLDOWN)
        state.opened = True
        state.open_until = self._clock() + max(self.cooldown, hint)
        state.probe_token = None
        state.probe_until = 0.0

    def release(self, host: str, token: int) -> None:
        """Free the slot of probe ``token`` when it ended without a verdict."""
        state = self._hosts.get(host)
        if state is not None and state.probe_token == token:
            state.probe_token = None
            state.probe_until = 0.0


_extract_breaker: HostCircuitBreaker | None = None


def extract_breaker() -> HostCircuitBreaker:
    """Process-wide breaker for extract, configured from settings."""
    global _extract_breaker
    if _extract_breaker is None:
        _extract_breaker = HostCircuitBreaker(
            threshold=int(settings.extract_breaker_threshold),
            cooldown=max(0.0, float(settings.extract_breaker_cooldown)),
        )
    return _extract_breaker


def reset_extract_breaker() -> None:
    """Drop the process-wide breaker (tests and settings reloads)."""
    global _extract_breaker
    _extract_breaker = None
