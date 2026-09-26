"""Runtime bridge between wet-mcp and hull-core (de-host 2026-09).

One place wires the shared-core seams together:

- instance settings: ``~/.wet/config.toml`` (auth mode + bind + per-task
  provider cells), loaded via :func:`hull_core.config.settings.load_settings`
  with wet's config dir;
- identity: the request-scoped :class:`hull_core.auth.context.AuthContext`
  published by :class:`hull_core.auth.asgi.HullAuthMiddleware`;
- per-sub storage roots: everything a caller writes lands under
  ``~/.wet/subs/<namespace>/`` (cache.db, snapshots), so mode-3 users on one
  process can never see each other's data (spec §4 Q2);
- provider clients: one :class:`hull_core.providers.openai_spec.
  OpenAICompatClient` per task cell (embed / rerank / chat / jev_score),
  built with the mode-derived SSRF policy (loopback self-hosted providers are
  a no-auth single-instance feature only).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from hull_core.auth.context import AuthContext, current_user
from hull_core.auth.middleware import Authenticator
from hull_core.auth.users import User, load_users
from hull_core.config.models import ModelCell, resolve_model_cells
from hull_core.config.settings import CONFIG_TEMPLATE, HullSettings, load_settings
from hull_core.providers.openai_spec import OpenAICompatClient

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
    """Drop the cached instance settings (config edited, tests)."""
    _cached_settings.cache_clear()


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
    limiter: object | None = None,
) -> Authenticator:
    """Assemble the hull Authenticator from wet's instance config."""
    from hull_core.limits.limiter import SlidingWindowLimiter

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
    """Resolve one per-task provider cell (embed/rerank/chat/jev_score)."""
    settings = settings if settings is not None else hull_settings()
    return resolve_model_cells(settings.models)[task]


def provider_client(
    task: str,
    settings: HullSettings | None = None,
    *,
    timeout: float = 60.0,
) -> OpenAICompatClient:
    """Build an OpenAI-spec client for one task cell (SSRF policy by mode)."""
    settings = settings if settings is not None else hull_settings()
    return OpenAICompatClient(
        model_cell(task, settings),
        auth_mode=settings.server.auth,
        timeout=timeout,
    )


def cell_configured(task: str, settings: HullSettings | None = None) -> bool:
    """True when the host configured a key for the task's cell."""
    return model_cell(task, settings).configured


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
