"""Runtime bridge between wet and hull-core (de-host 2026-09).

One place wires the shared-core seams together:

- instance settings: ``~/.wet/config.toml`` (auth mode + bind + per-task
  provider cells), loaded via :func:`hull_core.config.settings.load_settings`
  with wet's config dir;
- identity: the request-scoped :class:`hull_core.auth.context.AuthContext`
  published by :class:`hull_core.auth.asgi.HullAuthMiddleware`;
- per-sub storage roots: everything a caller writes lands under
  ``~/.wet/subs/<namespace>/`` (cache.db, snapshots), so mode-3 users on one
  process can never see each other's data (spec §4 Q2);
- provider clients: one :class:`wet.keypool.PooledProviderClient` per task cell
  (embed / rerank / chat / jev_score), built with the mode-derived SSRF policy
  (loopback self-hosted providers are a no-auth single-instance feature only)
  and reading the cell's credential pool, so a 401/403 or a 429 rotates to the
  next key instead of failing the feature.
"""

from __future__ import annotations

import os
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from hull_core.auth.context import AuthContext, current_user
from hull_core.auth.middleware import Authenticator
from hull_core.auth.users import User, load_users
from hull_core.config.models import DEFAULT_BASE_URL, ModelCell, resolve_model_cells
from hull_core.config.settings import CONFIG_TEMPLATE, HullSettings, load_settings
from hull_core.limits.limiter import SlidingWindowLimiter
from loguru import logger

from wet.keypool import (
    PooledProviderClient,
    credential_db_path,
    pool_for_task,
)

# Default embedding dimensions for sqlite-vec when EMBEDDING_DIMS is unset.
# Embeddings are truncated to this size, but a same-dim model swap still
# yields an incompatible vector space -- DocsDB's embedding-model identity
# guard (B2) catches that. Override via EMBEDDING_DIMS env var.
DEFAULT_EMBEDDING_DIMS = 768

# Namespace used by mode 1/2 (no-auth / shared token): one shared namespace.
DEFAULT_NAMESPACE = "default"


def wet_config_dir() -> Path:
    """wet's instance-config + data root: ``~/.wet/``."""
    return Path.home() / ".wet"


def wet_config_path() -> Path:
    return wet_config_dir() / "config.toml"


@lru_cache(maxsize=4)
def _cached_settings(config_dir: Path, mtime: float) -> HullSettings:
    return load_settings(config_dir)


def hull_settings() -> HullSettings:
    """Load ``~/.wet/config.toml`` (cached per file mtime; tests can reset)."""
    config_dir = wet_config_dir()
    path = config_dir / "config.toml"
    return _cached_settings(config_dir, path.stat().st_mtime if path.is_file() else 0.0)


def reset_settings_cache() -> None:
    """Drop the cached instance settings and pooled clients (config edited, tests)."""
    _cached_settings.cache_clear()
    _PROVIDER_CLIENTS.clear()


def load_users_for(settings: HullSettings) -> dict[str, User] | None:
    """Load users.toml for multi mode; None otherwise."""
    if settings.server.auth != "multi":
        return None
    if settings.server.users_file is None:
        raise RuntimeError(
            "auth = 'multi' requires [server] users_file (default ~/.wet/users.toml)"
        )
    return load_users(settings.server.users_file)


def build_authenticator(
    settings: HullSettings | None = None,
    *,
    limiter: SlidingWindowLimiter | None = None,
) -> Authenticator:
    """Assemble the hull Authenticator from wet's instance config."""
    settings = settings if settings is not None else hull_settings()
    users = load_users_for(settings)
    return Authenticator(
        settings,
        users=users,
        limiter=limiter if limiter is not None else SlidingWindowLimiter(),
    )


def current_sub() -> str:
    """The authenticated caller's namespace (isolates every write path)."""
    user = current_user()
    return user.namespace


def sub_root(namespace: str | None = None) -> Path:
    """Per-namespace storage root: ``~/.wet/subs/<namespace>/``.

    Mode-3 isolation root (spec §4 Q2): cache.db and other per-caller writes
    live here. The docs corpus (docs.db) stays at the host root — it is
    host-imported shared content, queried read-only by all namespaces.
    """
    ns = namespace if namespace is not None else current_sub()
    return wet_config_dir() / "subs" / ns


def model_cell(task: str, settings: HullSettings | None = None) -> ModelCell:
    """Resolve one per-task provider cell (embed/rerank/chat/jev_score).

    Credential order per cell: ``HULL_<TASK>_API_KEY`` env > ``[models.<task>]
    api_key`` in config.toml > ``OPENROUTER_API_KEY`` env when the cell points
    at the OpenRouter default base URL (one OpenRouter key serves every cell;
    the fallback never applies to custom endpoints so it can never leak a key
    to a third-party base_url).
    """
    settings = settings if settings is not None else hull_settings()
    cell = resolve_model_cells(settings.models)[task]
    if cell.api_key or cell.base_url != DEFAULT_BASE_URL:
        return cell
    fallback = os.environ.get("OPENROUTER_API_KEY", "")
    return replace(cell, api_key=fallback) if fallback else cell


# One pooled client per cell identity: the client caches its per-credential
# HTTP clients, so rebuilding it per tool call would throw away every
# connection (and the rotation memo) each time.
_PROVIDER_CLIENTS: dict[tuple, PooledProviderClient] = {}


def provider_client(
    task: str,
    settings: HullSettings | None = None,
    *,
    timeout: float = 60.0,
) -> PooledProviderClient:
    """Build (or reuse) the pooled provider client for one task cell.

    The client serves the cell's ``base_url`` + ``model`` with a credential
    from the cell's provider pool (hull key pool: 401/403 disables that key,
    429 cools it down honouring ``Retry-After``, exhaustion surfaces as a
    redacted :class:`wet.keypool.ProviderUnavailable`). SSRF policy is
    mode-derived, as before.
    """
    settings = settings if settings is not None else hull_settings()
    cell = model_cell(task, settings)
    key = (
        task,
        cell.base_url,
        cell.model,
        cell.provider,
        cell.account,
        cell.api_key,
        settings.server.auth,
        timeout,
        str(credential_db_path()),
    )
    client = _PROVIDER_CLIENTS.get(key)
    if client is None:
        client = PooledProviderClient(
            cell,
            auth_mode=settings.server.auth,
            timeout=timeout,
        )
        _PROVIDER_CLIENTS[key] = client
    return client


def cell_configured(task: str, settings: HullSettings | None = None) -> bool:
    """True when the task's cell has a usable credential source.

    A key in the cell (config or ``HULL_<TASK>_API_KEY`` / the OpenRouter
    fallback) is the legacy single-key answer; a pool seeded through the
    credential store answers for a keyless cell too, so a host that moved its
    keys into the pool keeps the capability on.
    """
    cell = model_cell(task, settings)
    if cell.configured:
        return True
    try:
        return bool(pool_for_task(cell).credentials())
    except Exception as exc:
        logger.warning(f"provider pool unavailable for {task}: {exc}")
        return False


__all__ = [
    "CONFIG_TEMPLATE",
    "DEFAULT_EMBEDDING_DIMS",
    "DEFAULT_NAMESPACE",
    "AuthContext",
    "current_user",
    "wet_config_dir",
    "wet_config_path",
    "hull_settings",
    "reset_settings_cache",
    "load_users_for",
    "build_authenticator",
    "current_sub",
    "sub_root",
    "model_cell",
    "provider_client",
    "cell_configured",
]
