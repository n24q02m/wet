"""Provider credential pools: hull's key pool + account registry, wired for wet.

wet used to resolve exactly one ``api_key`` per provider: one ``[models.<task>]``
cell key (plus the ``OPENROUTER_API_KEY`` fallback) for embed / rerank / chat /
jev_score, and one CSV of keys per cloud search backend with a local rotation
primitive of its own. A revoked or rate-limited key therefore took the
capability down, and the two surfaces disagreed about what a 429 means.

hull 0.5 ships the shared layer (``hull_core.credentials``): an ordered
credential pool per provider identity in ``hull.db``, health/cooldown/lease
state, named accounts, and a redacted exhaustion error. This module is wet's
single seam onto it:

* :func:`credential_store` -- one :class:`CredentialStore` per process, at
  hull's default ``hull.db`` (``WET_HULL_DB`` overrides the path for an
  isolated instance).
* :func:`pool_for_task` -- the :class:`KeyPool` a model cell reads, with the
  legacy single key seeded into the store first (:func:`migrate_legacy_key`).
* :func:`pool_for_provider` -- the same for a non-model provider (the cloud
  search backends' CSV keys).
* :class:`PooledProviderClient` -- the ``OpenAICompatClient``-shaped client the
  task cells use: every provider call becomes acquire -> call -> report, so a
  401/403 disables the credential and moves to the next one, a 429 cools it
  down by ``Retry-After`` / ``rate_limit_reset``, and an exhausted pool raises
  :class:`ProviderUnavailable` instead of a bare provider error.

Rotation policy is hull's, unchanged: 401/403 disable, 429 cooldown (1 s..1 h,
default 60 s), 5xx retry the same credential once then rotate, any other status
re-raises untouched, bounded attempts per call. Keys never appear in a message,
a log line or a repr -- hull keeps only a 4-character hint.

Config stays the owner of the endpoint: a cell's ``base_url`` and ``model`` are
used verbatim for every credential of its pool (the store entry contributes the
key), so seeding the same key for another task can never silently redirect a
call at the wrong endpoint. ``provider`` and ``account`` are optional cell keys
that select which pool to read; the default is the provider's unaccounted pool.

Concurrency: a call leases its credential, so two concurrent calls never get the
same key while another could serve. A pool with exactly one usable credential is
shared instead of leased -- there is no rotation decision left to protect, and
serialising wet's batched embedding fan-out (or two concurrent tool calls) on a
single key would cost throughput and turn a healthy provider into spurious
exhaustion errors. That singleton is still health-tracked: one 401 disables it,
one 429 cools it down exactly like a leased entry.
"""

from __future__ import annotations

import contextvars
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
from hull_core.config.models import ModelCell
from hull_core.credentials import (
    AccountRegistry,
    Credential,
    CredentialExistsError,
    CredentialStore,
    KeyPool,
    MigrationResult,
    PoolExhaustedError,
    default_pool_db_path,
    parse_rate_limit_reset,
    parse_retry_after,
    provider_from_base_url,
)
from hull_core.http.ssrf import AsyncSSRFSafeTransport
from hull_core.providers.openai_spec import (
    AuthPolicy,
    OpenAICompatClient,
    ProviderError,
)
from loguru import logger

# Env override for the shared credential database (isolated instances, tests).
POOL_DB_ENV = "WET_HULL_DB"

# Provider identity of a cell with no pool pointers and no parseable base_url.
DEFAULT_PROVIDER = "default"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProviderConfigError(RuntimeError):
    """A pool pointer in the config cannot be honoured (unknown account, ...).

    Raised before any provider call, so the operator sees the fix (register the
    account, fix the provider identity) instead of spending another pool's
    quota under the wrong identity.
    """


class ProviderUnavailable(RuntimeError):
    """No credential in the pool can serve the call right now.

    wet's own type around hull's redacted
    :class:`~hull_core.credentials.PoolExhaustedError`, so callers do not have
    to import hull to catch an exhausted pool. ``provider`` and
    ``retry_after`` are forwarded from the pool diagnosis; neither the message
    nor these fields ever carry a key.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        account_id: str | None = None,
        retry_after: float | None = None,
        last_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.account_id = account_id
        self.retry_after = retry_after
        self.last_error = last_error


class ProviderHttpError(ProviderError):
    """A provider's non-2xx answer with the response headers rotation needs.

    ``hull_core.providers.openai_spec.ProviderError`` keeps only status +
    body, but a 429's cooldown lives in ``Retry-After`` /
    ``x-ratelimit-reset``. The pooled client wraps every provider error in this
    subclass so hull's rotation can honour the provider's own hint instead of
    falling back to the 60 s default. The message is hull's, unchanged.
    """

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        headers: httpx.Headers | dict[str, str] | None = None,
    ) -> None:
        super().__init__(status, detail)
        self.headers = headers
        self.retry_after = _header_hint(parse_retry_after, headers, "retry-after")
        self.rate_limit_reset = _header_hint(
            parse_rate_limit_reset, headers, "x-ratelimit-reset"
        )


# ---------------------------------------------------------------------------
# Store + identity resolution
# ---------------------------------------------------------------------------


def credential_db_path() -> Path:
    """Path of the shared credential store: hull's default, or ``WET_HULL_DB``."""
    override = os.environ.get(POOL_DB_ENV, "").strip()
    return Path(override).expanduser() if override else default_pool_db_path()


_STORES: dict[str, CredentialStore] = {}
_POOLS: dict[tuple, KeyPool] = {}
_SEEDED: set[tuple] = set()


def credential_store() -> CredentialStore:
    """The process-wide credential store (``hull.db``), opened on first use."""
    path = str(credential_db_path())
    store = _STORES.get(path)
    if store is None:
        store = CredentialStore(path)
        _STORES[path] = store
    return store


def reset_credential_state() -> None:
    """Drop cached stores, pools and provider clients (config change, tests)."""
    for store in _STORES.values():
        try:
            store.close()
        except Exception:  # pragma: no cover - already closed
            pass
    _STORES.clear()
    _POOLS.clear()
    _SEEDED.clear()


def provider_identity(cell: ModelCell) -> str:
    """Pool identity for one cell: its ``provider`` pointer, else its base URL."""
    named = (getattr(cell, "provider", "") or "").strip()
    if named:
        return named
    return provider_from_base_url(cell.base_url) or DEFAULT_PROVIDER


def resolve_account(
    cell: ModelCell, store: CredentialStore, provider: str
) -> str | None:
    """Resolve a cell's optional ``account`` pointer to a registry account id.

    ``None`` means the provider's default (unaccounted) pool. An unknown
    account, or one registered for another provider, is a config error: silently
    falling back to the default pool would spend the wrong identity's quota.
    """
    ref = (getattr(cell, "account", "") or "").strip()
    if not ref:
        return None
    account = AccountRegistry(store).maybe_get(ref)
    if account is None:
        raise ProviderConfigError(
            f"models.{cell.task}: account {ref!r} is not registered; add it with "
            "hull's account registry (hull_core.credentials.AccountRegistry.add) "
            "or drop the account key to use the provider's default pool"
        )
    if account.provider != provider:
        raise ProviderConfigError(
            f"models.{cell.task}: account {ref!r} belongs to provider "
            f"{account.provider!r}, not {provider!r}"
        )
    return account.account_id


def _pool(
    store: CredentialStore,
    provider: str,
    account_id: str | None,
    *,
    max_5xx_retries: int,
    lease_seconds: float,
) -> KeyPool:
    key = (str(store.path), provider, account_id, max_5xx_retries, lease_seconds)
    pool = _POOLS.get(key)
    if pool is None:
        pool = store.pool(
            provider,
            account_id=account_id,
            max_5xx_retries=max_5xx_retries,
            lease_seconds=lease_seconds,
        )
        _POOLS[key] = pool
    return pool


# ---------------------------------------------------------------------------
# Migration of the legacy single-key config
# ---------------------------------------------------------------------------


def migrate_legacy_key(
    cell: ModelCell, *, store: CredentialStore | None = None
) -> MigrationResult | None:
    """Seed one cell's single ``api_key`` into its pool, idempotently.

    Returns ``None`` when the cell carries no key. The legacy material is never
    removed from the env var or the config file -- it stays the first-run seed
    and a fallback the operator can read; re-running this only ever *skips* what
    the store already holds (``MigrationResult.skipped``). No key is logged.
    """
    api_key = (cell.api_key or "").strip()
    if not api_key:
        return None
    store = store if store is not None else credential_store()
    provider = provider_identity(cell)
    account_id = resolve_account(cell, store, provider)
    result = store.migrate_model_cells([cell], provider=provider, account_id=account_id)
    logger.debug(
        f"provider pool {provider!r}: legacy key seed added={result.added} "
        f"skipped={result.skipped}"
    )
    return result


def _migrate_once(
    store: CredentialStore, cell: ModelCell, provider: str, account_id: str | None
) -> None:
    """Run the legacy seed at most once per (store, pool, key) in this process."""
    api_key = (cell.api_key or "").strip()
    if not api_key:
        return
    marker = (
        str(store.path),
        provider,
        account_id or "",
        cell.base_url,
        api_key,
    )
    if marker in _SEEDED:
        return
    migrate_legacy_key(cell, store=store)
    _SEEDED.add(marker)


def migrate_legacy_cells(cells: Sequence[ModelCell]) -> list[MigrationResult]:
    """Seed every configured cell's legacy key (server startup, CLI entry)."""
    results: list[MigrationResult] = []
    for cell in cells:
        result = migrate_legacy_key(cell)
        if result is not None:
            results.append(result)
    return results


def pool_for_task(
    cell: ModelCell,
    *,
    store: CredentialStore | None = None,
    max_5xx_retries: int = 1,
    lease_seconds: float = 60.0,
) -> KeyPool:
    """The pool a model cell reads, after seeding its legacy key once."""
    store = store if store is not None else credential_store()
    provider = provider_identity(cell)
    account_id = resolve_account(cell, store, provider)
    _migrate_once(store, cell, provider, account_id)
    return _pool(
        store,
        provider,
        account_id,
        max_5xx_retries=max_5xx_retries,
        lease_seconds=lease_seconds,
    )


# ---------------------------------------------------------------------------
# Non-model providers (search backends)
# ---------------------------------------------------------------------------


def seed_provider_keys(
    store: CredentialStore,
    provider: str,
    keys: Sequence[str],
    *,
    base_url: str,
    account_id: str | None = None,
) -> MigrationResult:
    """Seed a provider's configured keys into its pool, idempotently.

    Same contract as hull's ``migrate_model_cells``: every key that is not in
    the pool yet is added in order, the rest are counted as skipped, so this is
    safe to call on every request.
    """
    added = 0
    skipped = 0
    for api_key in keys:
        key = api_key.strip()
        if not key:
            continue
        try:
            store.add_credential(
                provider, key, base_url=base_url, account_id=account_id
            )
        except CredentialExistsError:
            skipped += 1
        else:
            added += 1
    return MigrationResult(provider=provider, added=added, skipped=skipped)


def pool_for_provider(
    provider: str,
    *,
    keys: Sequence[str] = (),
    base_url: str = "",
    account_id: str | None = None,
    store: CredentialStore | None = None,
    max_5xx_retries: int = 1,
    lease_seconds: float = 60.0,
) -> KeyPool:
    """The pool for a non-model provider, seeding its configured keys once."""
    store = store if store is not None else credential_store()
    if keys and base_url:
        marker = (
            str(store.path),
            provider,
            account_id or "",
            base_url,
            tuple(keys),
        )
        if marker not in _SEEDED:
            seed_provider_keys(
                store, provider, keys, base_url=base_url, account_id=account_id
            )
            _SEEDED.add(marker)
    return _pool(
        store,
        provider,
        account_id,
        max_5xx_retries=max_5xx_retries,
        lease_seconds=lease_seconds,
    )


# ---------------------------------------------------------------------------
# One-call rotation over a pool
# ---------------------------------------------------------------------------


def _header_hint(
    parser: Callable[..., float | None],
    headers: httpx.Headers | dict[str, str] | None,
    name: str,
) -> float | None:
    """Parse one hint header (case-insensitive) into delay seconds."""
    if not isinstance(headers, (httpx.Headers, dict)):
        # Absent, or not a header mapping at all (a mocked response in tests).
        return None
    try:
        value = headers.get(name)
        if value is None:
            for key, item in headers.items():
                if str(key).lower() == name:
                    value = item
                    break
    except Exception:  # pragma: no cover - exotic header mapping
        return None
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        # A header value is text (or a number); anything else is not a hint.
        return None
    return parser(value)


def status_of_http(error: BaseException) -> int | None:
    """HTTP status carried by a provider error (``status`` or ``status_code``)."""
    for attribute in ("status", "status_code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _shared_credential(pool: KeyPool) -> Credential | None:
    """The pool's lone usable credential, when there is nothing to rotate.

    Leasing exists so two concurrent callers never receive the same key while
    another key could serve. With one usable credential that decision has no
    alternative, and refusing the second caller would break the product (wet's
    embedding fan-out and concurrent tool calls both hit one key). The entry
    stays health-tracked by the caller: failures are reported exactly as they
    are for a leased entry.
    """
    usable = [
        health
        for health in pool.health()
        if not health.disabled and health.cooldown_remaining <= 0.0
    ]
    if len(usable) != 1:
        return None
    wanted = usable[0].id
    for credential in pool.credentials():
        if credential.id == wanted:
            return credential
    return None


async def pool_run[T](
    pool: KeyPool,
    call: Callable[[Credential], Awaitable[T]],
    *,
    status_of: Callable[[BaseException], int | None] | None = None,
) -> T:
    """Run one provider call through ``pool``: acquire -> call -> report.

    Multi-credential pools use hull's rotation verbatim (lease per call,
    bounded attempts, 401/403 disable, 429 cooldown, 5xx retry-then-next, a
    non-HTTP failure released without touching health). A lone usable
    credential is shared between concurrent callers instead of leased; its
    success/failure is reported the same way.
    """
    resolve = status_of if status_of is not None else status_of_http
    shared = _shared_credential(pool)
    if shared is None:
        return await pool.arun(call, status_of=resolve)

    try:
        result = await call(shared)
    except Exception as exc:
        headers = getattr(exc, "headers", None)
        retry_after = getattr(exc, "retry_after", None)
        rate_limit_reset = getattr(exc, "rate_limit_reset", None)
        if headers is not None:
            if retry_after is None:
                retry_after = _header_hint(parse_retry_after, headers, "retry-after")
            if rate_limit_reset is None:
                rate_limit_reset = _header_hint(
                    parse_rate_limit_reset, headers, "x-ratelimit-reset"
                )
        pool.report_failure(
            shared,
            resolve(exc),
            retry_after=retry_after,
            rate_limit_reset=rate_limit_reset,
        )
        raise
    pool.report_success(shared)
    return result


# ---------------------------------------------------------------------------
# Pooled provider client (the model cells' call surface)
# ---------------------------------------------------------------------------

# Response headers of the in-flight provider request, for ProviderHttpError.
_CAPTURE: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "wet_provider_response_capture", default=None
)


class _CapturingTransport(httpx.AsyncBaseTransport):
    """Transparent transport wrapper that remembers a failed response's headers.

    Sits under the OpenAI-spec client (which keeps the SSRF-pinned transport
    below it) purely so the rotation layer can read ``Retry-After``: hull's
    ``ProviderError`` carries status + body only.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        if response.status_code >= 400:
            slot = _CAPTURE.get()
            if slot is not None:
                slot["headers"] = response.headers
        return response

    async def aclose(self) -> None:
        closable = getattr(self._inner, "aclose", None)
        if closable is not None:
            await closable()


def _ssrf_transport(auth_mode: str) -> httpx.AsyncBaseTransport:
    policy = AuthPolicy.for_mode(auth_mode)
    return AsyncSSRFSafeTransport(
        allow_private=policy.allow_private, allow_loopback=policy.allow_loopback
    )


def _new_client(
    cell: ModelCell,
    *,
    auth_mode: str,
    timeout: float,
    inner: httpx.AsyncBaseTransport | None = None,
) -> OpenAICompatClient:
    """Build one OpenAI-spec client whose transport records failure headers."""
    return OpenAICompatClient(
        cell,
        auth_mode=auth_mode,
        timeout=timeout,
        transport=_CapturingTransport(
            inner if inner is not None else _ssrf_transport(auth_mode)
        ),
    )


class PooledProviderClient:
    """OpenAI-spec provider client bound to a task cell's credential pool.

    Drop-in for :class:`~hull_core.providers.openai_spec.OpenAICompatClient`
    (``cell``, ``embeddings``, ``chat``, ``rerank``, ``aclose``): every call
    acquires a credential from the cell's pool, performs the call with it, and
    reports the outcome back, so a dead key rotates instead of failing the
    feature. ``base_url`` and ``model`` stay the cell's (config owns the
    endpoint); the pool entry contributes the key.
    """

    def __init__(
        self,
        cell: ModelCell,
        *,
        auth_mode: str = "no-auth",
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
        max_5xx_retries: int = 1,
        lease_seconds: float = 60.0,
        store: CredentialStore | None = None,
    ) -> None:
        self._cell = cell
        self._auth_mode = auth_mode
        self._timeout = timeout
        self._transport = transport
        self._pool = pool_for_task(
            cell,
            store=store,
            max_5xx_retries=max_5xx_retries,
            lease_seconds=lease_seconds,
        )
        self._clients: dict[tuple, OpenAICompatClient] = {}

    @property
    def cell(self) -> ModelCell:
        """The config cell (``base_url`` + ``model``) this client serves."""
        return self._cell

    @property
    def pool(self) -> KeyPool:
        """The credential pool behind this client (masked ``health()``)."""
        return self._pool

    # -- provider calls ---------------------------------------------------

    async def embeddings(
        self,
        texts: list[str],
        *,
        dimensions: int | None = None,
        **extra: Any,
    ) -> list[list[float]]:
        async def call(client: OpenAICompatClient) -> list[list[float]]:
            return await client.embeddings(texts, dimensions=dimensions, **extra)

        return await self._run(call)

    async def chat(self, messages: list[dict], **options: Any) -> str:
        async def call(client: OpenAICompatClient) -> str:
            return await client.chat(messages, **options)

        return await self._run(call)

    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[dict]:
        async def call(client: OpenAICompatClient) -> list[dict]:
            return await client.rerank(query, documents, top_n=top_n)

        return await self._run(call)

    async def aclose(self) -> None:
        """Close every cached per-credential client for this cell."""
        clients = list(self._clients.values())
        self._clients.clear()
        for client in clients:
            await client.aclose()

    # -- plumbing ---------------------------------------------------------

    async def _run[T](self, call: Callable[[OpenAICompatClient], Awaitable[T]]) -> T:
        async def attempt(credential: Credential) -> T:
            client = self._client_for(credential)
            slot: dict[str, Any] = {}
            token = _CAPTURE.set(slot)
            try:
                return await call(client)
            except ProviderHttpError:
                raise
            except ProviderError as exc:
                raise ProviderHttpError(
                    exc.status, exc.detail, headers=slot.get("headers")
                ) from exc
            finally:
                _CAPTURE.reset(token)

        try:
            return await pool_run(self._pool, attempt)
        except PoolExhaustedError as exc:
            raise ProviderUnavailable(
                str(exc),
                provider=exc.provider,
                account_id=exc.account_id,
                retry_after=exc.retry_after,
                last_error=exc.last_error,
            ) from exc

    def _client_for(self, credential: Credential) -> OpenAICompatClient:
        """One cached client per (cell, credential, base url, auth mode)."""
        cell = replace(self._cell, api_key=credential.api_key)
        cache_key = (
            cell.task,
            credential.id,
            credential.base_url,
            cell.base_url,
            cell.model,
            self._auth_mode,
            self._timeout,
        )
        client = self._clients.get(cache_key)
        if client is None:
            client = _new_client(
                cell,
                auth_mode=self._auth_mode,
                timeout=self._timeout,
                inner=self._transport,
            )
            self._clients[cache_key] = client
        return client


__all__ = [
    "POOL_DB_ENV",
    "PooledProviderClient",
    "ProviderConfigError",
    "ProviderHttpError",
    "ProviderUnavailable",
    "credential_db_path",
    "credential_store",
    "migrate_legacy_cells",
    "migrate_legacy_key",
    "pool_for_provider",
    "pool_for_task",
    "pool_run",
    "provider_identity",
    "reset_credential_state",
    "resolve_account",
    "seed_provider_keys",
    "status_of_http",
]
