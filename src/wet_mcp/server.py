"""WET MCP Server - Main server definition."""

import asyncio
import datetime
import difflib
import functools
import io
import json
import math
import os
import re
import socket
import sys
import threading
import time

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(_s, io.TextIOWrapper):
            _s.reconfigure(encoding="utf-8", errors="replace")

from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from loguru import logger
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from wet_mcp import search_metrics
from wet_mcp.cache import WebCache
from wet_mcp.config import settings
from wet_mcp.db import (
    INDEX_STATE_DONE,
    INDEX_STATE_FAILED,
    INDEX_STATE_RUNNING,
    DocsDB,
)
from wet_mcp.runtime import (
    DEFAULT_EMBEDDING_DIMS,
    current_sub,
    model_cell,
)
from wet_mcp.searxng_runner import ensure_searxng, stop_searxng
from wet_mcp.security import UNTRUSTED_SOURCE, build_external_tool_result
from wet_mcp.sources import search_backends
from wet_mcp.sources.crawler import (
    crawl as _crawl,
)
from wet_mcp.sources.crawler import (
    extract as _extract,
)
from wet_mcp.sources.crawler import (
    list_media,
    shutdown_crawler,
)
from wet_mcp.sources.crawler import (
    sitemap as _sitemap,
)
from wet_mcp.transport_check import is_uvx_tool_venv, uvx_searxng_blocked_error

# Configure logging
logger.remove()
logger.add(sys.stderr, level=settings.log_level)


# ``region`` (search action): 2-letter ISO 3166-1 alpha-2 geo code.
_REGION_RE = re.compile(r"^[A-Za-z]{2}$")

# Reranking: retrieve more candidates than final limit, then rerank.
_RERANK_CANDIDATE_MULTIPLIER = 3

# Module-level state (set during lifespan). ``_web_cache`` routes to the
# calling namespace's own cache file -- see :class:`_PerSubCache`.
_web_cache: "_PerSubCache | None" = None
_docs_db: DocsDB | None = None
_embedding_dims: int = 0
_backend_init_task: asyncio.Task | None = None

# Strong references to fire-and-forget background tasks. asyncio keeps only a
# WEAK reference to a running task, so a task whose handle is discarded can be
# garbage-collected mid-flight and simply stop. Holding it here until it
# finishes is what makes "launched" mean "ran".
_background_tasks: set[asyncio.Task] = set()


def _on_background_task_done(task: asyncio.Task, label: str) -> None:
    """Release a finished background task and report what it did.

    An exception nobody retrieves surfaces only as a GC-time "Task exception
    was never retrieved" on stderr -- which, inside a slim container, is
    a place no operator can read. Log it here, with the traceback, at the
    moment it happens.

    Formatted with ``traceback`` rather than ``logger.opt(exception=True)``
    because the stderr sink runs with loguru's default ``diagnose=True``, which
    would dump every local (chunk bodies, provider objects) into the log.
    """
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        import traceback

        logger.error(
            f"Background task '{label}' failed: {type(exc).__name__}: {exc}\n"
            + "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).rstrip()
        )


def _launch_background_task(coro, label: str) -> asyncio.Task:
    """Start ``coro`` as a tracked task instead of an unreferenced one."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(functools.partial(_on_background_task_done, label=label))
    return task


class _PerSubCache:
    """Route WebCache operations to the caller's per-namespace cache file.

    De-host multi-user layout (spec §4 Q2 + mode-3 storage contract): each
    namespace gets its own SQLite file under ``~/.wet/subs/<namespace>/`` so
    users on one process never share a cache file. Instances are opened
    lazily per namespace and closed together on shutdown. WebCache itself
    ALSO folds the sub into its keys, so isolation holds even if two
    namespaces ever point at one file.
    """

    def __init__(self) -> None:
        self._caches: dict[str, WebCache] = {}
        self._lock = threading.Lock()

    def _for(self, sub: str) -> WebCache:
        cache = self._caches.get(sub)
        if cache is None:
            from wet_mcp.runtime import sub_root

            path = sub_root(sub) / "cache.db"
            path.parent.mkdir(parents=True, exist_ok=True)
            cache = WebCache(path)
            with self._lock:
                self._caches[sub] = cache
        return cache

    def get(self, action, params, sub):  # noqa: ANN001, ANN201
        return self._for(sub).get(action, params, sub)

    def get_with_age(self, action, params, sub):  # noqa: ANN001, ANN201
        return self._for(sub).get_with_age(action, params, sub)

    def get_stale_with_age(self, action, params, sub):  # noqa: ANN001, ANN201
        return self._for(sub).get_stale_with_age(action, params, sub)

    def set(self, action, params, content, ttl_override=None, sub=None):  # noqa: ANN001, ANN201
        return self._for(sub or "default").set(action, params, content, ttl_override, sub or "default")

    def record_snapshot(self, url, content, sub):  # noqa: ANN001, ANN201
        return self._for(sub).record_snapshot(url, content, sub)

    def latest_snapshots(self, url, n, sub):  # noqa: ANN001, ANN201
        return self._for(sub).latest_snapshots(url, n, sub)

    def clear(self, action, sub):  # noqa: ANN001, ANN201
        return self._for(sub).clear(action, sub)

    def stats(self, sub=None):  # noqa: ANN001, ANN201
        if sub:
            return self._for(sub).stats(sub)
        merged: dict[str, int] = {}
        for cache in self._caches.values():
            for key, value in cache.stats().items():
                merged[key] = merged.get(key, 0) + value
        return merged

    def close(self) -> None:
        for cache in self._caches.values():
            cache.close()
        self._caches.clear()


async def _wait_for_backend_init() -> None:
    """Wait for startup backend initialization when it is still running."""
    task = _backend_init_task
    if task is None or task.done():
        return
    # A canceled request must not cancel the shared startup task. Shutdown
    # owns cancellation of that task explicitly in _lifespan_shutdown.
    await asyncio.shield(task)


def _missing_docs_db_methods(backend) -> list[str]:
    """Public ``DocsDB`` methods that ``backend`` (class or instance) lacks.

    ``DocsDB`` itself is the contract, read at runtime rather than copied into
    a hand-written list, so a method added there cannot quietly become a hole
    in an alternate backend.
    """
    return sorted(
        name
        for name, attr in vars(DocsDB).items()
        if not name.startswith("_")
        and callable(attr)
        and not callable(getattr(backend, name, None))
    )


def make_docs_db(db_path: Path | None = None):
    """Open the local docs DB (SQLite under ``~/.wet/``).

    De-host: the CF D1 + Vectorize backend is gone — this is always a
    :class:`DocsDB` on a local file (WAL). ``db_path`` overrides
    ``settings.get_db_path()`` for callers that open a store at an explicit
    location (``scripts/build_tier1_index.py --db-path``).

    The B2 embedding-model identity guard needs the CURRENT model identity:
    the embed cell's model when the host configured ``[models.embed]``
    (stamped by the re-embed pass as ``openai-spec:<model>``), otherwise the
    local ONNX model id. Dims come from EMBEDDING_DIMS (default 768).
    """
    from wet_mcp.config import settings
    from wet_mcp.runtime import cell_configured

    dims = settings.embedding_dims or DEFAULT_EMBEDDING_DIMS
    if cell_configured("embed"):
        model_identity = f"openai-spec:{model_cell('embed').model}"
    else:
        model_identity = settings.resolve_local_embedding_model()
    return DocsDB(
        settings.get_db_path() if db_path is None else db_path,
        embedding_dims=dims,
        model_identity=model_identity,
        reindex_on_model_change=settings.reindex_on_model_change,
    )


async def _warmup_searxng() -> None:
    """Run heavy setup and pre-warm SearXNG in background.

    Non-fatal: if startup fails, the first search call will retry.
    """
    try:
        from wet_mcp.setup import run_auto_setup

        await asyncio.to_thread(run_auto_setup)

        # Pre-import crawl4ai
        await asyncio.to_thread(__import__, "crawl4ai")
        logger.info("Crawl4AI background load complete")

        from wet_mcp.searxng_runner import ensure_searxng

        url = await ensure_searxng()
        logger.info(f"SearXNG pre-warmed at {url}")
    except Exception as e:
        logger.debug(f"SearXNG pre-warm failed (non-fatal): {e}")


def _detect_gh_token() -> str | None:
    """Try to get GitHub token from gh CLI (GitHub CLI).

    Runs 'gh auth token' and returns the token string if available.
    Returns None if gh CLI is not installed or not authenticated.
    """
    import shutil
    import subprocess

    gh_path = shutil.which("gh")
    if not gh_path:
        return None

    try:
        result = subprocess.run(
            [gh_path, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            token = result.stdout.strip()
            if token:
                return token
    except Exception:
        pass
    return None


@asynccontextmanager
async def _lifespan(_server: FastMCP):
    """Server lifespan: startup SearXNG, init cache/docs DB, cleanup on shutdown."""
    warmup_task = await _lifespan_startup()
    yield
    await _lifespan_shutdown(warmup_task)


async def _lifespan_startup() -> asyncio.Task | None:
    """Initialize all server components. Returns SearXNG warmup task."""
    global _backend_init_task, _web_cache, _docs_db, _embedding_dims

    logger.info("Starting WET MCP Server...")

    # Warn about GitHub token for library docs discovery
    if not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")):
        # Try to get token from gh CLI (GitHub CLI)
        gh_token = _detect_gh_token()
        if gh_token:
            os.environ["GITHUB_TOKEN"] = gh_token
            logger.info("GITHUB_TOKEN loaded from gh CLI (gh auth token)")
        else:
            logger.warning(
                "No GITHUB_TOKEN set. Library docs discovery will use unauthenticated "
                "GitHub API (60 req/hr limit). Set GITHUB_TOKEN or run 'gh auth login'."
            )

    # SearXNG is pre-warmed eagerly as a background task to eliminate
    # startup latency on the first search call. If this instance finds an
    # existing healthy SearXNG (started by another MCP server instance), it
    # reuses it instead of spawning a new subprocess.
    #
    # Stdio uvx mode skips warmup entirely: the search/research/docs/similar
    # actions are gated by `is_uvx_tool_venv()` and return a clear error
    # pointing to Docker mode. Warming SearXNG in uvx mode wastes a Docker
    # spawn the user will never get value from.
    warmup_task: asyncio.Task | None = None
    if settings.auto_searxng_enabled() and not is_uvx_tool_venv():
        warmup_task = asyncio.create_task(_warmup_searxng())

    # 2. Initialize the web cache (per-namespace files under ~/.wet/subs/)
    if settings.wet_cache:
        _web_cache = _PerSubCache()
        logger.info("Web cache enabled (per-sub under ~/.wet/subs/)")

    # 3. Initialize embedding backend (dual-backend: cloud or local)
    _embedding_dims = settings.embedding_dims or DEFAULT_EMBEDDING_DIMS

    async def _init_backends_task():
        try:
            await _init_embedding_backend()
            await _init_reranker_backend()
        except Exception as e:
            logger.error(f"Background backend init failed: {e}")

    _backend_init_task = _launch_background_task(_init_backends_task(), "init-backends")

    # 5. Initialize the docs DB (local SQLite under ~/.wet/), then run Alembic
    #    migrations (auto-migrate-on-startup with backup-before-migrate).
    #    DocsDB._create_tables is the bootstrap path for fresh DBs (CREATE
    #    TABLE IF NOT EXISTS); Alembic stamps the baseline + applies forward
    #    migrations.
    _docs_db = make_docs_db()
    try:
        from wet_mcp.migrations import run_migrations_on_startup

        run_migrations_on_startup(settings.get_db_path())
    except Exception as e:  # pragma: no cover - never block startup
        logger.warning(f"Migrations skipped: {e}")

    # 5b. Tier 1 metadata warmup (Phase 2). Lazy chunk ingestion is
    # triggered on first docs_query for an unseeded library.
    try:
        from wet_mcp.sources.tier1_warmup import maybe_warm

        await asyncio.to_thread(maybe_warm, _docs_db)
    except Exception as e:  # pragma: no cover - never block startup
        logger.warning(f"Tier 1 warmup skipped: {e}")

    # De-host: docs.db backup/sync is an OUT-OF-REPO rclone job (host cron /
    # command) -- there is no in-process sync backend anymore.
    return warmup_task


async def _lifespan_shutdown(warmup_task: asyncio.Task | None) -> None:
    """Shut down all server components."""
    global _backend_init_task, _web_cache, _docs_db

    logger.info("Shutting down WET MCP Server...")

    # Cancel SearXNG warmup task if still running
    if warmup_task and not warmup_task.done():
        warmup_task.cancel()
        try:
            await warmup_task
        except (asyncio.CancelledError, Exception):
            pass

    # Backend initialization is tracked separately because embedding and
    # reranking requests wait for it while startup is still in progress.
    if _backend_init_task and not _backend_init_task.done():
        _backend_init_task.cancel()
        try:
            await _backend_init_task
        except (asyncio.CancelledError, Exception):
            pass
    _backend_init_task = None

    # Close databases
    if _docs_db:
        _docs_db.close()
        _docs_db = None
    if _web_cache:
        _web_cache.close()
        _web_cache = None

    # Shut down the shared browser pool first (may take a few seconds)
    try:
        await shutdown_crawler()
    except Exception as exc:
        logger.debug(f"Browser pool shutdown error (non-fatal): {exc}")

    stop_searxng()


def _supported_model_ids(model_class: Any) -> set[str]:
    """Read supported model ids from fastretrieval's public registry."""
    ids: set[str] = set()
    for item in model_class.list_supported_models():
        model_id = (
            item.get("model")
            if isinstance(item, dict)
            else getattr(item, "model", item)
        )
        if isinstance(model_id, str):
            ids.add(model_id.lower())
    return ids


def _maybe_register_custom_embed(local_model: str) -> None:
    """Register a BYO local embedding model when it is not in the registry.

    Built-in ids are resolved from fastretrieval's registry instead of a model
    family prefix. External ids require explicit dimension, pooling, and
    normalization settings from the user.
    """
    if not settings.local_embedding_model:
        return

    from fastretrieval import CustomModelSpec, TextEmbedding

    if local_model.lower() in _supported_model_ids(TextEmbedding):
        return
    if settings.local_embedding_dim <= 0:
        logger.error(
            "Custom local embedding model {!r} requires LOCAL_EMBEDDING_DIM > 0; "
            "skipping registration.",
            local_model,
        )
        return

    try:
        CustomModelSpec(
            model_id=local_model,
            hf=local_model,
            model_file=settings.local_embedding_model_file,
            dim=settings.local_embedding_dim,
            pooling=settings.local_embedding_pooling,
            normalization=settings.local_embedding_normalize,
        ).register()
        logger.info(
            "Registered custom local embedding model {!r} (dim={}, pooling={})",
            local_model,
            settings.local_embedding_dim,
            settings.local_embedding_pooling,
        )
    except ValueError as e:
        # Already registered (re-init) or invalid spec — non-fatal.
        logger.debug("Custom embedding registration skipped: {}", e)


def _maybe_register_custom_rerank(local_model: str) -> None:
    """Register a BYO local reranker when it is not in the registry."""
    if not settings.local_rerank_model:
        return

    from fastretrieval import CustomRerankerSpec, TextCrossEncoder

    if local_model.lower() in _supported_model_ids(TextCrossEncoder):
        return

    try:
        CustomRerankerSpec(
            model_id=local_model,
            hf=local_model,
            model_file=settings.local_rerank_model_file,
        ).register()
        logger.info("Registered custom local reranker {!r}", local_model)
    except ValueError as e:
        # Already registered (re-init) or invalid spec — non-fatal.
        logger.debug("Custom reranker registration skipped: {}", e)


async def _init_embedding_backend() -> None:
    """Initialize the embedding backend from the per-task config cells.

    Resolution (spec §4 — the cell owns the model, the host owns the key):

    - ``[models.embed]`` cell configured (api_key present) -> cloud, no
      silent local fallback: a broken host key must surface loudly, not
      masquerade as a working local index.
    - cell unconfigured and the local ONNX leg available -> local.
    - neither -> logged unavailable; callers degrade to keyword-only.
    """
    global _embedding_dims
    from wet_mcp.embedder import clear_backend, init_backend, no_local_embed_clause
    from wet_mcp.runtime import cell_configured

    if cell_configured("embed"):
        cell = model_cell("embed")
        try:
            backend = await asyncio.to_thread(init_backend, "cloud", cell.model)
            native_dims = await backend.check_available()
            if native_dims > 0:
                if _embedding_dims == 0:
                    _embedding_dims = DEFAULT_EMBEDDING_DIMS
                logger.info(
                    f"Embedding: {cell.model} via {cell.base_url} "
                    f"(native={native_dims}, stored={_embedding_dims})"
                )
                return
            clear_backend()
            logger.error(
                f"Cloud embedding {cell.model} check returned no usable dims"
            )
        except Exception as e:
            clear_backend()
            logger.error(f"Cloud embedding init failed ({cell.model}): {e}")
        return

    if not settings.local_embed_available():
        logger.error(
            "Embedding: unavailable ([models.embed] cell has no api_key and "
            f"the local ONNX leg is out: {no_local_embed_clause()}); "
            "embedding degrades to keyword-only"
        )
        return

    local_model = settings.resolve_local_embedding_model()
    _maybe_register_custom_embed(local_model)
    try:
        backend = await asyncio.to_thread(init_backend, "local", local_model)
        native_dims = await backend.check_available()
        if native_dims > 0:
            if _embedding_dims == 0:
                _embedding_dims = DEFAULT_EMBEDDING_DIMS
            logger.info(
                f"Embedding: local {local_model} "
                f"(native={native_dims}, stored={_embedding_dims})"
            )
        else:
            clear_backend()
            logger.error("Local embedding model not available")
    except Exception as e:
        clear_backend()
        logger.error(f"Local embedding init failed: {e}")


async def _init_reranker_backend() -> None:
    """Initialize the reranker backend from the per-task config cells.

    Same resolution ladder as :func:`_init_embedding_backend` with one extra
    branch: ``RERANK_ENABLED=false`` disables reranking entirely (empty
    backend; searches keep source order).
    """
    from wet_mcp.reranker import clear_reranker, init_reranker
    from wet_mcp.runtime import cell_configured

    if not settings.rerank_enabled:
        logger.info("Reranking disabled")
        return

    if cell_configured("rerank"):
        cell = model_cell("rerank")
        try:
            reranker = await asyncio.to_thread(init_reranker, "cloud", cell.model)
            # CloudReranker is async (hull-core httpx client); LocalReranker
            # is sync ONNX and needs a worker thread.
            available = await reranker.check_available()
            if available:
                logger.info(f"Reranker: {cell.model} via {cell.base_url}")
                return
            clear_reranker()
            logger.error(f"Cloud reranker {cell.model} check failed")
        except Exception as e:
            clear_reranker()
            logger.error(f"Cloud reranker init failed ({cell.model}): {e}")
        return

    if not settings.local_rerank_available():
        logger.error(
            "Reranker: unavailable ([models.rerank] cell has no api_key and "
            "the local ONNX leg is out — DISABLE_LOCAL_RERANK set, or no "
            "fastretrieval installed in this image); searches keep source order"
        )
        return

    local_model = settings.resolve_local_rerank_model()
    _maybe_register_custom_rerank(local_model)
    try:
        reranker = await asyncio.to_thread(init_reranker, "local", local_model)
        available = await asyncio.to_thread(reranker.check_available)
        if available:
            logger.info(f"Reranker: local {local_model}")
        else:
            clear_reranker()
            logger.error("Local reranker not available")
    except Exception as e:
        clear_reranker()
        logger.error(f"Local reranker init failed: {e}")


# --- Helpers ---


async def _embed(text: str, is_query: bool = False) -> list[float] | None:
    """Embed text if backend is available.

    Args:
        text: Text to embed.
        is_query: If True, use the model's query embedding path for asymmetric
            retrieval. Document embeddings stay raw.
    """
    await _wait_for_backend_init()

    from wet_mcp.embedder import (
        LocalEmbeddingBackend,
        _is_retryable,
        resolve_embed_backend_for_request,
    )

    backend = resolve_embed_backend_for_request()
    if not backend:
        return None
    try:
        if is_query and isinstance(backend, LocalEmbeddingBackend):
            return await backend.embed_single_query(text, _embedding_dims)
        return await backend.embed_single(text, _embedding_dims)
    except Exception as e:
        if _is_retryable(e):
            # Transient (rate-limit / network; the backend already exhausted
            # its retries). Degrade THIS call to keyword search -- the next
            # may succeed.
            logger.warning(f"Embedding transiently unavailable, degrading call: {e}")
            return None
        # Permanent config/capability error (bad key, unknown model, dims the
        # backend could not work around): every embed will fail. Surface it
        # loudly instead of silently returning None and hiding a broken
        # semantic search behind a keyword-only fallback.
        logger.error(
            f"Embedding permanently failing: {e}. "
            "Check the [models.embed] cell in ~/.wet/config.toml."
        )
        raise


async def _embed_batch(texts: list[str]) -> list[list[float]] | None:
    """Embed batch of texts if backend is available."""
    await _wait_for_backend_init()

    from wet_mcp.embedder import _is_retryable, resolve_embed_backend_for_request

    backend = resolve_embed_backend_for_request()
    if not backend:
        return None
    try:
        return await backend.embed_texts(texts, _embedding_dims)
    except Exception as e:
        if _is_retryable(e):
            # Transient (rate-limit / network; the backend already exhausted
            # its retries). Degrade THIS batch to keyword-only -- a later
            # index pass may succeed.
            logger.warning(
                f"Batch embedding transiently unavailable, degrading call: {e}"
            )
            return None
        # Permanent config/capability error: every embed will fail. Surface it
        # loudly instead of silently storing keyword-only chunks that masquerade
        # as a working semantic index.
        logger.error(
            f"Batch embedding permanently failing: {e}. "
            "Check the [models.embed] cell in ~/.wet/config.toml."
        )
        raise


async def _rerank_results(
    query: str,
    results: list[dict],
    top_n: int,
) -> list[dict]:
    """Rerank search results if reranker is available.

    Falls back to original results if reranking fails or is unavailable.
    """
    await _wait_for_backend_init()

    from wet_mcp.reranker import (
        CloudReranker,
        resolve_rerank_backend_for_request,
    )

    reranker = resolve_rerank_backend_for_request()
    if not reranker or len(results) < top_n:
        return results[:top_n]

    try:
        documents = [r["content"] for r in results]
        if isinstance(reranker, CloudReranker):
            ranked = await reranker.rerank(query, documents, top_n)
        else:
            ranked = await asyncio.to_thread(reranker.rerank, query, documents, top_n)
        if ranked:
            reranked = []
            for idx, score in ranked:
                if idx < len(results):
                    result = results[idx].copy()
                    result["score"] = round(score, 4)
                    reranked.append(result)
            return reranked
    except Exception as e:
        # A reranker that is configured but permanently broken (bad key, wrong
        # model id, dead endpoint) silently returns keyword order on EVERY
        # search. At debug level nobody sees that; warning is the level an
        # operator actually reads.
        logger.warning(
            f"Reranking failed with {type(reranker).__name__} "
            f"({len(results)} candidates, query {query[:80]!r}), "
            f"falling back to unranked order: {type(e).__name__}: {e}"
        )

    return results[:top_n]


# Initialize MCP server
mcp = FastMCP(
    name="wet",
    instructions=(
        "Web Extended Toolkit MCP Server. "
        "IMPORTANT: `search` and `extract` serve different purposes. "
        "`search` FINDS information (returns result listings with titles, URLs, snippets). "
        "`extract` READS content from a specific URL (returns full page text). "
        "Typical workflow: search first to find URLs, then extract to read them. "
        "`media` discovers and downloads images/videos/audio from pages. "
        "All web operations are cached for performance."
    ),
    lifespan=_lifespan,
)

# Report wet-mcp's own package version in serverInfo.version. FastMCP (the SDK
# class) does not accept a `version=` kwarg, so the underlying lowlevel Server
# defaults `.version` to None and the SDK fills serverInfo with the `mcp`
# package version instead. Setting it here propagates to
# create_initialization_options().server_version. Read the version via
# importlib.metadata (not `from wet_mcp import __version__`) to avoid a
# circular import: wet_mcp/__init__.py imports `mcp` from this module.
from importlib.metadata import version as _pkgver  # noqa: E402

mcp._mcp_server.version = _pkgver("wet-mcp")


# Grace period (seconds) given to a cancelled task to clean up resources
# (e.g. close browser tabs) before we abandon it entirely.
_CANCEL_GRACE_PERIOD = 5.0


def _payload(result: str | dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Adapt a helper's result into a structured tool payload.

    The ``sources.*`` helpers and ``_with_timeout`` still speak the JSON-string
    / ``"Error: ..."`` contract because the web cache stores that text verbatim
    in a TEXT column. The tool boundary is where it turns into structured
    output: an object passes through, an array gets an object envelope
    (``structuredContent`` must be an object) and an error string becomes
    ``{"error": ...}``.
    """
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        return {"results": result}
    if result.startswith("Error"):
        return {"error": result}
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return {"error": result}
    return data if isinstance(data, dict) else {"results": data}


# Cap on diff text landed in a tool payload (token guard), matching the
# ``token_budget`` convention used elsewhere in this file.
_DIFF_MAX_CHARS = 20_000


def _unified_diff_truncated(old_content: str, new_content: str, url: str) -> str:
    """Line-based unified diff (stdlib) between two snapshot bodies.

    Truncated at ``_DIFF_MAX_CHARS`` with a note appended, so a large page
    rewrite can't blow the tool's output budget.
    """
    diff_lines = difflib.unified_diff(
        old_content.splitlines(),
        new_content.splitlines(),
        fromfile=f"{url} (old)",
        tofile=f"{url} (new)",
        lineterm="",
        n=3,
    )
    diff_text = "\n".join(diff_lines)
    if len(diff_text) > _DIFF_MAX_CHARS:
        diff_text = (
            diff_text[:_DIFF_MAX_CHARS] + "\n... (diff truncated at 20000 chars)"
        )
    return diff_text


def _build_diff_result(url: str, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn up to 2 ``latest_snapshots`` rows (newest first) into a diff payload."""
    if not snapshots:
        return {
            "url": url,
            "error": f"Error: no snapshot history for {url}. Extract it once "
            "(refetch=True, the default) to start tracking changes.",
        }
    newest = snapshots[0]
    if len(snapshots) == 1:
        return {
            "url": url,
            "change_status": "new",
            "diff": "",
            "old_fetched_at": None,
            "new_fetched_at": newest["fetched_at"],
        }
    old = snapshots[1]
    if old["content"] == newest["content"]:
        return {
            "url": url,
            "change_status": "same",
            "diff": "",
            "old_fetched_at": old["fetched_at"],
            "new_fetched_at": newest["fetched_at"],
        }
    return {
        "url": url,
        "change_status": "changed",
        "diff": _unified_diff_truncated(old["content"], newest["content"], url),
        "old_fetched_at": old["fetched_at"],
        "new_fetched_at": newest["fetched_at"],
    }


def _wrap_tool(tool_name: str):
    """Decorator to wrap tool results with XPIA safety markers.

    The decorated tool returns a plain ``dict``; this turns it into a
    ``CallToolResult`` so BOTH response channels defend against XPIA: the text
    block keeps its ``<untrusted_{tool}_content>`` boundary tags and the
    ``structuredContent`` carries the envelope markers (a client reading
    structured output never sees the text block). FastMCP still derives the
    tool's ``outputSchema`` from the wrapped function's ``-> dict`` annotation,
    which ``functools.wraps`` keeps reachable via ``__wrapped__``.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            # A per-action handler may tag its dict with an internal ``_source``
            # hint (trusted: set by handler code, while external content only
            # ever lands in VALUES, never as a top-level key) so a fan-out tool
            # like ``search`` labels the XPIA envelope with the real upstream
            # (e.g. "x" for X posts) instead of the default "web".
            source = (
                result.pop("_source", UNTRUSTED_SOURCE)
                if isinstance(result, dict)
                else UNTRUSTED_SOURCE
            )
            return build_external_tool_result(tool_name, result, source=source)

        return wrapper

    return decorator


# Sub-operation timeouts (seconds) within docs search.
# These prevent any single step from consuming the entire tool_timeout budget.
_SEARXNG_TIMEOUT = 150  # ensure_searxng() — cold start can take 90-120s
_DISCOVERY_TIMEOUT = 30  # discover_library() — registry + probe
_FETCH_TIMEOUT = 90  # _fetch_and_chunk_docs() — llms.txt + GH raw + crawl
_EMBED_TIMEOUT = 60  # _embed_batch() — per concurrency wave; see _embed_run_timeout
_FALLBACK_TIMEOUT = 60  # SearXNG fallback fetch

# Upper bound on the waves _embed_run_timeout may budget for. 11 waves *
# _EMBED_TIMEOUT plus the other phase timeouts stays under
# _INDEX_RUNNING_STALE_AFTER (900s), so even a pathologically large library
# can never hold a live run past the stale-running marker.
_EMBED_MAX_WAVES = 11


def _embed_run_timeout(num_texts: int) -> float:
    """Overall ``wait_for`` budget for one background-index embed run.

    ``_EMBED_TIMEOUT`` was sized for a local ONNX pass over the whole chunk
    set. The cloud backend now splits the same set into
    ``CloudEmbeddingBackend.MAX_BATCH_SIZE``-text batches drained
    ``CONCURRENCY`` at a time, so wall time grows with the wave count: a
    fixed 60s ceiling killed large libraries mid-embed (1967 chunks -> 21
    batches -> 3 waves) and stamped every chunk keyword-only. Budget one
    ``_EMBED_TIMEOUT`` per wave instead. The local backend (one linear
    pass) only ever receives a larger budget out of this, which is the
    intended direction: time out a hung backend, never a healthy-but-slow
    one.
    """
    from wet_mcp.embedder import CloudEmbeddingBackend

    per_wave = CloudEmbeddingBackend.MAX_BATCH_SIZE * CloudEmbeddingBackend.CONCURRENCY
    waves = max(1, math.ceil(num_texts / per_wave))
    return _EMBED_TIMEOUT * min(waves, _EMBED_MAX_WAVES)


async def _with_timeout(coro, action: str) -> Any:
    """Wrap coroutine with hard timeout. Passes the coroutine's result through
    (a JSON string from ``sources.*``, or a dict from a dict-returning helper);
    a timeout yields the usual ``"Error: ..."`` string.

    Uses ``asyncio.wait`` instead of ``asyncio.wait_for`` because
    Playwright / Crawl4AI may suppress ``CancelledError`` internally,
    causing ``wait_for`` to block indefinitely.  ``asyncio.wait``
    returns immediately when the deadline expires regardless of whether
    the inner task cooperates with cancellation.

    After cancellation the task is given a brief grace period to release
    resources (browser tabs, network connections) before being abandoned.
    """
    timeout = settings.tool_timeout
    if timeout <= 0:
        return await coro

    task = asyncio.create_task(coro)
    done, _pending = await asyncio.wait({task}, timeout=timeout)

    if done:
        # Propagate any exception raised by the task
        return task.result()

    # Hard timeout -- cancel and wait briefly for cleanup
    task.cancel()
    logger.warning(f"Tool '{action}' timed out after {timeout}s, cancelling...")

    # Give the task a grace period to clean up (close browser pages, etc.)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=_CANCEL_GRACE_PERIOD)
    except (asyncio.CancelledError, TimeoutError, Exception):
        # Task either cancelled cleanly, timed out again, or raised -- all OK
        pass

    logger.error(f"Tool '{action}' timed out after {timeout}s")
    return (
        f"Error: '{action}' timed out after {timeout}s. "
        "Increase TOOL_TIMEOUT or try simpler parameters."
    )


async def _run_configured_search(*, timeout: float | None = None, **kwargs: Any) -> str:
    """Run the configured backend chain, auto-starting local SearXNG."""
    searxng_url = None
    if (
        settings.auto_searxng_enabled()
        and not is_uvx_tool_venv()
        and "searxng" in search_backends.chain_backend_names()
    ):
        try:
            searxng_url = await asyncio.wait_for(
                ensure_searxng(), timeout=_SEARXNG_TIMEOUT
            )
        except TimeoutError:
            return f"Error: SearXNG startup timed out ({_SEARXNG_TIMEOUT}s). Try again or check logs."
        except (SystemExit, Exception) as exc:
            return f"Error: SearXNG startup failed: {exc}"
    search_call = search_backends.run_search_chain(searxng_url=searxng_url, **kwargs)
    if timeout is not None:
        return await asyncio.wait_for(search_call, timeout=timeout)
    return await search_call


# ---------------------------------------------------------------------------
# search tool: search, research, docs
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        openWorldHint=True,
        idempotentHint=True,
    ),
)
@_wrap_tool("search")
async def search(  # noqa: PLR0913
    action: str,
    query: str | None = None,
    library: str | None = None,
    version: str | None = None,
    topic: str | None = None,
    project_path: str | None = None,
    language: str | None = None,
    categories: str = "general",
    max_results: int = 10,
    limit: int = 10,
    time_range: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    expand: bool = False,
    enrich: bool = False,
    region: str | None = None,
    refine: bool = False,
    parallel: bool = False,
) -> dict[str, Any]:
    """Find information across web, academic sources, or library docs. Returns search result listings (titles, URLs, snippets) -- NOT full page content. To read full content from a URL, use the `extract` tool instead.

    Actions:
    - search: Web search via SearXNG. Example: search(action="search", query="python async patterns")
    - research: Academic/scientific search (Google Scholar, arXiv, PubMed). Example: search(action="research", query="transformer attention mechanism")
    - docs: Search library documentation with auto-indexing. Example: search(action="docs", query="how to create routes", library="fastapi")
    - docs_resolve: Free-form library name to ranked library_id list. Example: search(action="docs_resolve", query="react")
    - docs_query: Version-aware library docs query honoring project lock + token cap. Example: search(action="docs_query", library="react", version="latest", topic="useState", query="how to set initial state")
    - docs_lock_project: Detect project manifests (pyproject/package.json/go.mod/Cargo.toml) and lock the library set for Cabinets isolation. Example: search(action="docs_lock_project", project_path="/repo/my-app")
    - similar: Find pages similar to a URL (pass URL as query). Example: search(action="similar", query="https://example.com/article")

    Key parameters:
    - query (required for all actions): Search terms or URL (for similar)
    - library (required for docs): Library name, e.g. "react", "fastapi"
    - language: Programming language for disambiguation in docs, e.g. "python", "java"
    - expand: Enable LLM query expansion for broader coverage (default: false)
    - enrich: Fetch actual page content for richer snippets (default: false, adds latency)
    - max_results: Number of results (default: 10)
    - time_range: Recency filter -- day, week, month, year
    - include_domains / exclude_domains: Domain filters
    - region (search only): 2-letter ISO 3166-1 country code (e.g. "US", "vn") geo filter. Backends without region support are skipped (named in a warning); a chain with no region-capable backend returns a structured error naming them.
    - refine (search only): Opt-in iterative refinement. When results are empty or low-relevance, re-queries up to 2 times with LLM-rewritten terms and returns the best round (adds LLM latency/cost per round).

    Use `help` tool with tool_name="search" for full parameter documentation.
    """
    # Stdio uvx tool venv lacks pip, so the web-core SearXNG runner cannot
    # install/start a local SearXNG instance, and its hardcoded
    # ``localhost:8080`` fallback is wrong for our pinned Docker port.
    # Per spec ``2026-05-01-stdio-pure-http-multiuser.md`` §4.1.1, reject
    # SearXNG-dependent actions with a clear error pointing at Method 3
    # (stdio Docker) or Method 2 (HTTP Docker). Other actions on the
    # ``extract`` tool (``extract`` / ``crawl`` / ``map`` / ``media``) hit
    # upstream via ``httpx`` directly and remain available.
    # docs_resolve and docs_lock_project do not need SearXNG (pure DB ops);
    # docs_query falls back to local FTS even without SearXNG, so allow it.
    # Only block when NO configured backend can run under uvx: a cloud key
    # (tavily/brave/exa/kagi/firecrawl), the credential-free duckduckgo or
    # startpage backends, or an external SEARXNG_URL all work without the
    # local SearXNG auto-spawn that uvx tool venvs cannot start.
    if (
        action in ("search", "research", "docs", "similar")
        and is_uvx_tool_venv()
        and not search_backends.has_uvx_runnable_backend()
    ):
        return {"error": uvx_searxng_blocked_error(action)}

    match action:
        case "search":
            if not query:
                return {
                    "error": 'Error: query is required for search action. Example: search(action="search", query="python async patterns")'
                }
            from wet_mcp.sources._search_polish import (
                normalize_query,
                refine_needed,
                round_quality,
                search_ttl_seconds,
                standardize_results,
            )

            normalized_query = normalize_query(query)
            ttl = search_ttl_seconds(time_range)
            region_normalized = region.strip() if isinstance(region, str) else ""
            if region_normalized and not _REGION_RE.fullmatch(region_normalized):
                return {
                    "error": (
                        f"Invalid region={region!r} for search action: expected "
                        "a 2-letter ISO 3166-1 code (e.g. 'US', 'vn')."
                    )
                }
            region_normalized = region_normalized.upper() or None
            cache_params = {
                "query": normalized_query,
                "categories": categories,
                "max_results": max_results,
                "time_range": time_range,
                "language": language,
                "region": region_normalized,
                "include_domains": include_domains,
                "exclude_domains": exclude_domains,
                "parallel": parallel,
            }
            if _web_cache:
                cache_hit = await asyncio.to_thread(
                    _web_cache.get_with_age, "search", cache_params, current_sub()
                )
                if cache_hit:
                    cached_content, cache_age = cache_hit
                    try:
                        cached_data = json.loads(cached_content)
                        if isinstance(cached_data, dict) and cached_data.get("results"):
                            cached_data["results"] = standardize_results(
                                cached_data["results"],
                                cache_age_seconds=cache_age,
                                ttl_seconds=ttl,
                            )
                            return cached_data
                    except json.JSONDecodeError:
                        pass
                    return _payload(cached_content)

                # Stale-While-Revalidate: serve stale if within 2x TTL window
                try:
                    stale_hit = await asyncio.to_thread(
                        _web_cache.get_stale_with_age, "search", cache_params, current_sub()
                    )
                except Exception:
                    stale_hit = None

                if stale_hit and isinstance(stale_hit, tuple) and len(stale_hit) == 2:
                    cached_content, cache_age = stale_hit
                    try:
                        cached_data = json.loads(cached_content)
                        if isinstance(cached_data, dict) and cached_data.get("results"):
                            cached_data["results"] = standardize_results(
                                cached_data["results"],
                                cache_age_seconds=cache_age,
                                ttl_seconds=ttl,
                            )
                            cached_data["stale"] = True
                            return cached_data
                    except json.JSONDecodeError:
                        pass
                    return _payload(cached_content)
            # Optional query expansion (LLM-driven, opt-in)
            search_query = normalized_query or query
            if expand:
                from wet_mcp.sources.search_strategies import expand_query

                expanded = await expand_query(query)
                if len(expanded) > 1:
                    search_query = " OR ".join(expanded)

            async def _round(round_query: str) -> tuple[str, dict[str, Any] | None]:
                """One chain round: run the chain, sanity-filter, rerank.

                Returns ``(raw_payload, parsed_envelope)``; ``data`` is
                ``None`` when the chain itself failed (tool timeout or
                unparseable payload) and the raw text must pass through.
                """
                result = await _with_timeout(
                    _run_configured_search(
                        query=round_query,
                        categories=categories,
                        max_results=max_results * _RERANK_CANDIDATE_MULTIPLIER,
                        time_range=time_range,
                        language=language,
                        region=region_normalized,
                        include_domains=include_domains,
                        exclude_domains=exclude_domains,
                        parallel=parallel,
                    ),
                    "search",
                )
                if result.startswith("Error"):
                    return result, None
                try:
                    data = json.loads(result)
                except json.JSONDecodeError:
                    return result, None
                # Rerank by semantic relevance (same as research/docs). The
                # rerank anchor is the query actually sent to the chain for
                # this round (with expand=True the original behavior reranked
                # against the pre-expansion query).
                try:
                    raw_results = data.get("results", [])
                    results_list = [
                        r
                        for r in raw_results
                        if any(
                            isinstance(value, str) and value.strip()
                            for value in (r.get("content"), r.get("snippet"))
                        )
                    ]
                    if len(results_list) != len(raw_results):
                        data["results"] = results_list[:max_results]
                        data["total"] = len(data["results"])
                    if results_list:
                        # Normalize the usable body for reranking and output.
                        for r in results_list:
                            content = r.get("content")
                            snippet = r.get("snippet")
                            if not isinstance(content, str) or not content.strip():
                                r["content"] = snippet
                            if not isinstance(snippet, str) or not snippet.strip():
                                r["snippet"] = r["content"]
                        reranked = await _rerank_results(
                            round_query, results_list, top_n=max_results
                        )
                        if reranked:
                            data["results"] = reranked
                            data["total"] = len(data["results"])
                except Exception as e:
                    logger.warning(
                        f"Search reranking step failed for query {round_query!r}, "
                        f"returning backend order: {type(e).__name__}: {e}"
                    )
                return json.dumps(data, ensure_ascii=False, indent=2), data

            raw, data = await _round(search_query)
            if data is None:
                if raw.startswith("Error"):
                    return _payload(raw)
                if _web_cache:
                    await asyncio.to_thread(
                        _web_cache.set, "search", cache_params, raw, ttl, current_sub()
                    )
                return _payload(raw)

            # Quality-tracked rounds. With refine=True a round that fails the
            # quality gate (all-empty or mean rerank score below the floor)
            # triggers at most 2 re-queries with LLM-rewritten terms; the
            # best round by quality wins (ties keep the original query).
            rounds: list[tuple[float, dict[str, Any]]] = [
                (round_quality(data.get("results", [])), data)
            ]
            if refine:
                tried: list[str] = [search_query]
                current = search_query
                for _ in range(2):  # hard bound: max 2 review rounds
                    if not refine_needed(rounds[-1][1].get("results", [])):
                        break
                    from wet_mcp.sources.search_strategies import rewrite_query

                    results_now = rounds[-1][1].get("results", [])
                    if results_now:
                        scored = [
                            r["score"]
                            for r in results_now
                            if isinstance(r.get("score"), (int, float))
                            and not isinstance(r.get("score"), bool)
                        ]
                        reason = (
                            f"low relevance (mean score {sum(scored) / len(scored):.2f})"
                            if scored
                            else "irrelevant results"
                        )
                    else:
                        reason = "no results at all"
                    rewritten = await rewrite_query(current, avoid=tried, reason=reason)
                    if not rewritten:
                        break  # no LLM available or nothing new to try
                    tried.append(rewritten)
                    _r_raw, r_data = await _round(rewritten)
                    if r_data is None:
                        break  # a failed round never poisons the best-round pick
                    rounds.append((round_quality(r_data.get("results", [])), r_data))
                    current = rewritten
            _, data = max(rounds, key=lambda pair: pair[0])

            # Optional snippet enrichment
            if enrich:
                try:
                    results_list = data.get("results", [])
                    if results_list:
                        from wet_mcp.sources.search_strategies import (
                            enrich_snippets,
                        )

                        enriched = await enrich_snippets(results_list, query, top_n=5)
                        data["results"] = enriched
                except Exception as e:
                    # enrich=True is an explicit opt-in the caller pays
                    # latency for. Dropping it at debug level returns
                    # plain snippets that look like a successful
                    # enrichment.
                    logger.warning(
                        f"Snippet enrichment (enrich=True) failed for "
                        f"query {query!r}; returning unenriched "
                        f"snippets: {type(e).__name__}: {e}"
                    )

            # Citation standardization (always on -- cheap pure-python).
            try:
                results_list = data.get("results", [])
                if results_list:
                    data["results"] = standardize_results(
                        results_list,
                        cache_age_seconds=None,
                        ttl_seconds=ttl,
                    )
            except Exception as e:
                # Pure-python and always on, so a failure here is our
                # own bug, not an upstream outage.
                logger.warning(
                    f"Citation standardization failed for query "
                    f"{query!r}; results ship without freshness / "
                    f"citation metadata: {type(e).__name__}: {e}"
                )

            result = json.dumps(data, ensure_ascii=False, indent=2)
            if _web_cache:
                await asyncio.to_thread(
                    _web_cache.set, "search", cache_params, result, ttl, current_sub()
                )
            return _payload(result)

        case "research":
            if not query:
                return {
                    "error": 'Error: query is required for research action. Example: search(action="research", query="transformer attention mechanism")'
                }
            cache_params = {
                "query": query,
                "max_results": max_results,
                "time_range": time_range,
                "language": language,
                "include_domains": include_domains,
                "exclude_domains": exclude_domains,
                "parallel": parallel,
            }
            if _web_cache:
                cached = await asyncio.to_thread(
                    _web_cache.get, "research", cache_params, current_sub()
                )
                if cached:
                    return _payload(cached)
            result = await _with_timeout(
                _do_research(
                    query=query,
                    max_results=max_results,
                    time_range=time_range,
                    language=language,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                ),
                "research",
            )
            if _web_cache and not result.startswith("Error"):
                await asyncio.to_thread(
                    _web_cache.set, "research", cache_params, result, current_sub()
                )
            return _payload(result)

        case "docs":
            if not library:
                return {
                    "error": 'Error: library is required for docs action. Example: search(action="docs", query="routing", library="fastapi")'
                }
            if not query:
                return {
                    "error": 'Error: query is required for docs action. Example: search(action="docs", query="how to create routes", library="fastapi")'
                }
            return _payload(
                await _with_timeout(
                    _do_docs_search(
                        library=library,
                        query=query,
                        language=language,
                        version=version,
                        limit=limit,
                    ),
                    "docs",
                )
            )

        case "similar":
            if not query:
                return {
                    "error": 'Error: query (URL) is required for similar action. Example: search(action="similar", query="https://example.com/article")'
                }
            if not query.startswith(("http://", "https://")):
                return {
                    "error": 'Error: query must be a full URL starting with http:// or https://. Example: search(action="similar", query="https://example.com/article"). If you want to search by keywords instead, use action="search".'
                }
            from wet_mcp.sources.search_strategies import find_similar

            return _payload(
                await _with_timeout(
                    find_similar(url=query, max_results=max_results),
                    "similar",
                )
            )

        case "docs_resolve":
            if not query:
                return {
                    "error": 'Error: query (library name) is required for docs_resolve. Example: search(action="docs_resolve", query="react")'
                }
            if not _docs_db:
                return {"error": "Error: Docs database not initialized"}
            from wet_mcp.sources.docs import resolve_library

            results = await asyncio.to_thread(resolve_library, _docs_db, query, limit)
            return {"query": query, "results": results, "total": len(results)}

        case "docs_query":
            if not query:
                return {
                    "error": 'Error: query is required for docs_query. Example: search(action="docs_query", library="react", query="useState")'
                }
            if not library:
                return {
                    "error": 'Error: library is required for docs_query. Example: search(action="docs_query", library="react", query="useState")'
                }
            if not _docs_db:
                return {"error": "Error: Docs database not initialized"}
            from wet_mcp.sources.docs import (
                DocsQueryOptions,
                ingest_tier2,
                query_docs,
                resolve_library,
            )

            # Resolve library: accept either library_id (12-char hex) or
            # canonical/alias name. We always look up by name first so the
            # caller can pass either form.
            resolved = await asyncio.to_thread(resolve_library, _docs_db, library, 1)
            # Ingest when the library is unknown OR known-but-empty. Tier 1
            # warmup seeds 50 curated libraries metadata-only, so those names
            # always resolve; gating on `not resolved` alone left exactly them
            # stuck at zero chunks forever. `latest_version` is populated from
            # get_best_version, i.e. it is None until a version reaches
            # status='indexed'.
            if not resolved or resolved[0].get("latest_version") is None:
                # Tier 2 lazy ingest: fire-and-forget, return progress hint.
                _launch_background_task(
                    ingest_tier2(_docs_db, library), f"ingest-tier2:{library}"
                )
                return {
                    "status": "indexing_in_progress",
                    "library": library,
                    "message": (
                        "Library not yet indexed. Tier 2 ingestion has "
                        "started in the background; retry shortly."
                    ),
                    "results": [],
                }

            lib_id = resolved[0]["library_id"]
            effective_version = version

            # Honor Cabinets project lock when project_path is supplied AND
            # the caller did not explicitly pin a version.
            lock_pin: str | None = None
            if project_path and not version:
                lock_entry = await asyncio.to_thread(
                    _docs_db.get_project_context, project_path
                )
                if lock_entry:
                    for locked in lock_entry.get("locked_libraries", []):
                        if locked.get("id") in (lib_id, library, library.lower()):
                            lock_pin = locked.get("version")
                            break
                    await asyncio.to_thread(
                        _docs_db.touch_project_context, project_path
                    )
            if lock_pin:
                effective_version = lock_pin

            results = await asyncio.to_thread(
                query_docs,
                _docs_db,
                lib_id,
                query,
                DocsQueryOptions(
                    version=effective_version,
                    topic=topic,
                    limit=limit,
                ),
            )
            return {
                "library": resolved[0],
                "query": query,
                "version": effective_version or "latest",
                "topic": topic,
                "project_path": project_path,
                "lock_pin": lock_pin,
                "results": results,
                "total": len(results),
            }

        case "docs_lock_project":
            if not project_path:
                return {
                    "error": 'Error: project_path is required for docs_lock_project. Example: search(action="docs_lock_project", project_path="/repo/my-app")'
                }
            if not _docs_db:
                return {"error": "Error: Docs database not initialized"}
            from wet_mcp.sources.project_lock import lock_project

            try:
                lock = await asyncio.to_thread(
                    lock_project, _docs_db, Path(project_path)
                )
            except FileNotFoundError as exc:
                return {"error": f"Error: project_path does not exist: {exc}"}
            return lock

        case _:
            import difflib

            valid_actions = [
                "docs",
                "docs_resolve",
                "docs_query",
                "docs_lock_project",
                "research",
                "search",
                "similar",
                "x",
            ]
            closest = (
                difflib.get_close_matches(action, valid_actions, n=1)
                if action is not None
                else []
            )
            suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
            return {
                "error": (
                    f"Error: Unknown action '{action}'.{suggestion} "
                    "Valid actions: search (web search), research (academic), "
                    "x (X/Twitter search via xAI, returns synthesized answer + citations), "
                    "docs (library documentation, auto-indexing), "
                    "docs_resolve (library name → ranked library_id), "
                    "docs_query (version-aware docs query with token cap), "
                    "docs_lock_project (Cabinets project isolation), "
                    "similar (find related pages). "
                    "If you want to read content from a URL, use the `extract` tool instead."
                )
            }


# ---------------------------------------------------------------------------
# extract tool: extract, crawl, map
# ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        openWorldHint=True,
    ),
)
@_wrap_tool("extract")
async def extract(  # noqa: PLR0913
    action: str,
    urls: list[str] | None = None,
    paths: list[str] | None = None,
    depth: int = 2,
    max_pages: int = 20,
    format: str = "markdown",
    stealth: bool = False,
    schema: dict | None = None,
    prompt: str | None = None,
    query: str | None = None,
    max_urls: int = 5,
    synthesis_model: str | None = None,
    token_budget: int = 10000,
    actions: list[dict] | None = None,
    session: str | None = None,
    screenshot: bool = False,
    url: str | None = None,
    refetch: bool = True,
) -> dict[str, Any]:
    """Read and return full page content from URLs or local files. Use this when you have a specific URL and need its content. For finding URLs first, use the `search` tool instead.

    Actions:
    - extract: Get clean content from URLs. Example: extract(action="extract", urls=["https://example.com/article"])
    - batch: Batch extract with per-domain rate limiting (max 50 URLs). Example: extract(action="batch", urls=["https://a.com/1", "https://b.com/2"])
    - crawl: Deep crawl following links from root URLs. Example: extract(action="crawl", urls=["https://docs.example.com"], depth=2)
    - map: Discover site URL structure without extracting content. Example: extract(action="map", urls=["https://example.com"])
    - convert: Convert local files (PDF, DOCX, PPTX, XLSX) to Markdown. Example: extract(action="convert", paths=["/home/user/report.pdf"])
    - extract_structured: Extract structured data using JSON Schema + LLM. Example: extract(action="extract_structured", urls=["https://example.com/pricing"], schema={"type": "object", "properties": {"price": {"type": "string"}}})
    - agent: Multi-step research orchestration -- search the web, extract top results, synthesize a cited Markdown answer. Example: extract(action="agent", query="latest pydantic 2 changes", max_urls=5)
    - interact: Drive a page with click/fill/submit via patchright. Example: extract(action="interact", url="https://example.com/login", actions=[{"type": "fill", "selector": "#email", "value": "x@y.com"}, {"type": "submit", "selector": "form"}])
    - diff: Track content changes across fetches of the same URL(s). Example: extract(action="diff", urls=["https://example.com/pricing"])

    Key parameters:
    - urls (required for extract/batch/crawl/map/extract_structured/diff): List of URLs
    - paths (required for convert): List of local file paths
    - query (required for agent): Research question to answer
    - url (required for interact): Page URL to drive
    - actions (required for interact): List of {type, selector?, description?, value?} ops
    - max_urls (agent): Default 5, hard cap 20
    - synthesis_model (agent): Override LLM model for the synthesis step
    - token_budget (agent): Max prompt tokens (default 10000)
    - session (interact): Persistent session id; reuses browser across calls
    - screenshot (interact): Capture post-interaction screenshot
    - format: Output format -- "markdown" (default), "text", "html"
    - depth: Crawl depth (default: 2, max: 5)
    - max_pages: Max pages for crawl/map (default: 20, max: 100)
    - stealth: Enable anti-bot bypass for protected sites (default: false)
    - schema: JSON Schema dict for extract_structured
    - refetch (diff): Fetch a fresh copy before comparing (default: true). Set
      false to compare already-recorded snapshots without a new network fetch.

    Use `help` tool with tool_name="extract" for full parameter documentation.
    """
    # Security: enforce hard limits to prevent resource exhaustion
    _MAX_EXTRACT_URLS = 20
    _MAX_CRAWL_PAGES = 100
    _MAX_DEPTH = 5

    max_pages = min(max_pages, _MAX_CRAWL_PAGES)
    depth = min(depth, _MAX_DEPTH)

    match action:
        case "extract":
            if not urls:
                return {
                    "error": 'Error: urls is required for extract action. Example: extract(action="extract", urls=["https://example.com/page"])'
                }
            urls = urls[:_MAX_EXTRACT_URLS]
            cache_params = {"urls": sorted(urls), "format": format, "stealth": stealth}
            if _web_cache:
                cached = await asyncio.to_thread(
                    _web_cache.get, "extract", cache_params, current_sub()
                )
                if cached:
                    return _payload(cached)
            result = await _with_timeout(
                _extract(urls=urls, format=format, stealth=stealth),
                "extract",
            )
            if _web_cache and not result.startswith("Error"):
                await asyncio.to_thread(_web_cache.set, "extract", cache_params, result, current_sub())
            return _payload(result)

        case "batch":
            if not urls:
                return {
                    "error": 'Error: urls is required for batch action. Example: extract(action="batch", urls=["https://a.com/1", "https://b.com/2"])'
                }
            from wet_mcp.sources.crawler import batch_extract

            return _payload(
                await _with_timeout(
                    batch_extract(urls=urls, format=format, stealth=stealth),
                    "batch",
                )
            )

        case "crawl":
            if not urls:
                return {
                    "error": 'Error: urls is required for crawl action. Example: extract(action="crawl", urls=["https://docs.example.com"], depth=2)'
                }
            urls = urls[:_MAX_EXTRACT_URLS]
            cache_params = {
                "urls": sorted(urls),
                "depth": depth,
                "max_pages": max_pages,
            }
            if _web_cache:
                cached = await asyncio.to_thread(_web_cache.get, "crawl", cache_params, current_sub())
                if cached:
                    return _payload(cached)
            result = await _with_timeout(
                _crawl(
                    urls=urls,
                    depth=depth,
                    max_pages=max_pages,
                    format=format,
                    stealth=stealth,
                ),
                "crawl",
            )
            if _web_cache and not result.startswith("Error"):
                await asyncio.to_thread(_web_cache.set, "crawl", cache_params, result, current_sub())
            return _payload(result)

        case "map":
            if not urls:
                return {
                    "error": 'Error: urls is required for map action. Example: extract(action="map", urls=["https://example.com"])'
                }
            urls = urls[:_MAX_EXTRACT_URLS]
            cache_params = {
                "urls": sorted(urls),
                "depth": depth,
                "max_pages": max_pages,
            }
            if _web_cache:
                cached = await asyncio.to_thread(_web_cache.get, "map", cache_params, current_sub())
                if cached:
                    return _payload(cached)
            result = await _with_timeout(
                _sitemap(urls=urls, depth=depth, max_pages=max_pages),
                "map",
            )
            if _web_cache and not result.startswith("Error"):
                await asyncio.to_thread(_web_cache.set, "map", cache_params, result, current_sub())
            return _payload(result)

        case "convert":
            if not paths:
                return {
                    "error": 'Error: paths is required for convert action. Example: extract(action="convert", paths=["/home/user/report.pdf"])'
                }
            from wet_mcp.sources.crawler import convert_local_files

            return _payload(
                await _with_timeout(
                    convert_local_files(paths=paths),
                    "convert",
                )
            )

        case "extract_structured":
            if not urls:
                return {
                    "error": 'Error: urls is required for extract_structured action. Example: extract(action="extract_structured", urls=["https://example.com/pricing"], schema={"type": "object", "properties": {"price": {"type": "string"}}})'
                }
            if not schema:
                return {
                    "error": 'Error: schema (JSON Schema dict) is required for extract_structured action. Provide a JSON Schema defining the data structure to extract. Example: schema={"type": "object", "properties": {"title": {"type": "string"}, "items": {"type": "array", "items": {"type": "object"}}}}'
                }
            from wet_mcp.sources.structured import extract_structured

            return _payload(
                await _with_timeout(
                    extract_structured(
                        urls=urls, schema=schema, prompt=prompt, stealth=stealth
                    ),
                    "extract_structured",
                )
            )

        case "agent":
            if not query:
                return {
                    "error": 'Error: query is required for agent action. Example: extract(action="agent", query="latest pydantic 2 changes", max_urls=5)'
                }
            from wet_mcp.sources.agent_orchestrator import run_agent

            return _payload(
                await _with_timeout(
                    run_agent(
                        query=query,
                        max_urls=max_urls,
                        synthesis_model=synthesis_model,
                        token_budget=token_budget,
                    ),
                    "agent",
                )
            )

        case "interact":
            if not url:
                return {
                    "error": 'Error: url is required for interact action. Example: extract(action="interact", url="https://example.com/login", actions=[{"type": "click", "selector": "#submit"}])'
                }
            if not actions:
                return {
                    "error": 'Error: actions is required for interact action. Provide a list of {type, selector?, description?, value?} ops. Example: actions=[{"type": "fill", "selector": "#email", "value": "x@y.com"}, {"type": "submit", "selector": "form"}]'
                }
            from wet_mcp.sources.interact_orchestrator import run_interact

            return _payload(
                await _with_timeout(
                    run_interact(
                        url=url,
                        actions=actions,
                        session=session,
                        screenshot=screenshot,
                    ),
                    "interact",
                )
            )

        case "diff":
            if not urls:
                return {
                    "error": 'Error: urls is required for diff action. Example: extract(action="diff", urls=["https://example.com"])'
                }
            if not _web_cache:
                return {
                    "error": "Error: diff action requires the web cache to be "
                    "enabled (set WET_CACHE=true)."
                }
            urls = urls[:_MAX_EXTRACT_URLS]
            diff_items: list[dict[str, Any]] = []
            for target_url in urls:
                if refetch:
                    fresh = await _with_timeout(
                        _extract(urls=[target_url], format=format, stealth=stealth),
                        "diff",
                    )
                    if fresh.startswith("Error"):
                        diff_items.append({"url": target_url, "error": fresh})
                        continue
                    try:
                        parsed = json.loads(fresh)
                    except json.JSONDecodeError:
                        diff_items.append(
                            {
                                "url": target_url,
                                "error": f"Error: failed to parse extract result for diff: {fresh}",
                            }
                        )
                        continue
                    item = parsed[0] if parsed else {}
                    if item.get("error"):
                        diff_items.append({"url": target_url, "error": item["error"]})
                        continue
                    await asyncio.to_thread(
                        _web_cache.record_snapshot, target_url, item.get("markdown", ""), current_sub()
                    )
                snapshots = await asyncio.to_thread(
                    _web_cache.latest_snapshots, target_url, 2, current_sub()
                )
                diff_items.append(_build_diff_result(target_url, snapshots))
            return _payload(diff_items[0] if len(diff_items) == 1 else diff_items)

        case _:
            valid_actions = [
                "agent",
                "batch",
                "convert",
                "crawl",
                "diff",
                "extract",
                "extract_structured",
                "interact",
                "map",
            ]
            closest = (
                difflib.get_close_matches(action, valid_actions, n=1)
                if action is not None
                else []
            )
            suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
            return {
                "error": (
                    f"Error: Unknown action '{action}'.{suggestion} "
                    "Valid actions: extract (read URL content), batch (bulk extract), crawl (follow links), "
                    "map (site structure), convert (local files to markdown), extract_structured (schema-based), "
                    "agent (multi-step research orchestration), interact (drive a page with click/fill/submit), "
                    "diff (track changes between fetches). "
                    "If you want to search for information, use the `search` tool instead."
                )
            }


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        openWorldHint=True,
    ),
)
@_wrap_tool("media")
async def media(  # noqa: PLR0913
    action: str,
    url: str | None = None,
    media_type: str = "all",
    media_urls: list[str] | None = None,
    output_dir: str | None = None,
    max_items: int = 10,
    prompt: str = "Describe this image in detail.",
) -> dict[str, Any]:
    """Discover and download media files (images, videos, audio) from web pages.

    Actions:
    - list: Scan a page and return media URLs with metadata. Example: media(action="list", url="https://example.com/gallery", media_type="images")
    - download: Download media files to local storage. Example: media(action="download", media_urls=["https://example.com/photo.jpg"])

    Key parameters:
    - url (required for list): Page URL to scan
    - media_urls (required for download): List of media URLs to download
    - media_type: Filter for list -- "images", "videos", "audio", "files", "all" (default: "all")
    - output_dir: Download directory (default: ~/.wet-mcp/downloads)
    - prompt: Reserved -- accepted for backward compatibility, ignored

    Typical workflow: list (discover) -> download (save locally). For LLM
    analysis (vision/audio/video), hand the downloaded path to
    imagine-mcp's understand action. The legacy media(action="analyze")
    was REMOVED in wet v2.0.0 (deprecated since v1.x.y); calling it now
    returns the standard unknown-action error.

    Use `help` tool with tool_name="media" for full documentation.
    """
    from wet_mcp.sources.crawler import download_media

    match action:
        case "list":
            if not url:
                return {
                    "error": 'Error: url is required for list action. Example: media(action="list", url="https://example.com/gallery", media_type="images")'
                }
            return _payload(
                await _with_timeout(
                    list_media(url=url, media_type=media_type, max_items=max_items),
                    "media.list",
                )
            )

        case "download":
            if not media_urls:
                return {
                    "error": 'Error: media_urls is required for download action. Example: media(action="download", media_urls=["https://example.com/image.jpg"]). Use media(action="list", url="...") first to discover media URLs.'
                }

            # Security: validate output_dir is within the configured
            # download directory to prevent arbitrary file writes.
            resolved_download_dir = Path(settings.download_dir).expanduser().resolve()
            target_dir = (
                Path(output_dir or settings.download_dir).expanduser().resolve()
            )
            if not target_dir.is_relative_to(resolved_download_dir):
                return {
                    "error": (
                        "Error: Security Alert — output_dir must be within "
                        f"the configured download directory ({resolved_download_dir})"
                    )
                }

            return _payload(
                await _with_timeout(
                    download_media(
                        media_urls=media_urls,
                        output_dir=str(target_dir),
                    ),
                    "media.download",
                )
            )

        case _:
            import difflib

            # Phase 3 (v2.0.0) BREAKING: analyze removed entirely after the
            # 2-minor-version deprecation grace period started in Phase 1
            # commit 2ea6f23. Vision/audio/video analysis lives in
            # imagine-mcp's understand action. We special-case the
            # message for callers still passing analyze so they can
            # migrate without hunting through release notes.
            valid_actions = ["download", "list"]
            closest = (
                difflib.get_close_matches(action, valid_actions, n=1)
                if action is not None
                else []
            )
            suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
            if action == "analyze":
                return {
                    "error": (
                        "Error: Unknown action 'analyze'. The analyze action was "
                        "removed in wet v2.0.0. Use imagine-mcp's understand "
                        "action for vision/audio/video analysis. "
                        "Valid wet media actions: list (discover media on page), "
                        "download (save to local)."
                    )
                }
            return {
                "error": (
                    f"Error: Unknown action '{action}'.{suggestion} "
                    "Valid actions: list (discover media on page), "
                    "download (save to local)."
                )
            }


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        openWorldHint=False,
        idempotentHint=True,
    ),
)
async def help(tool_name: str = "search") -> str:
    """Get detailed documentation for any tool. Call this when you need full parameter reference or usage examples.

    Valid tool_name values: search, extract, media, config.

    Quick guide -- which tool to use:
    - Need to FIND information? Use `search` (returns result listings with URLs)
    - Need to READ a page? Use `extract` (returns full page content from a URL)
    - Need media files? Use `media` (discover, download images/videos/audio)
    - Need server settings? Use `config` (status, cache, settings, warmup)
    """
    allowed_tools = {"search", "extract", "media", "config"}
    if tool_name not in allowed_tools:
        import difflib

        closest = (
            difflib.get_close_matches(tool_name, sorted(allowed_tools), n=1)
            if tool_name is not None
            else []
        )
        suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
        return f"Error: Invalid tool_name '{tool_name}'.{suggestion} Valid options: {', '.join(sorted(allowed_tools))}."

    try:
        doc_file = files("wet_mcp.docs").joinpath(f"{tool_name}.md")
        return doc_file.read_text()
    except FileNotFoundError:
        return f"Error: No documentation found for tool '{tool_name}'"
    except Exception as e:
        return f"Error loading documentation: {e}"


def _active_docs_backend() -> str:
    """The docs-store backend name, mirrored with ``make_docs_db``.

    De-host there is exactly one backend: the local SQLite store.
    """
    return "sqlite"


def _backend_model_identity(backend: Any) -> str | None:
    """Return the resolved model id without exposing backend internals."""
    if backend is None:
        return None
    model = getattr(backend, "model", None) or getattr(backend, "_model_name", None)
    return model if isinstance(model, str) else None


async def _handle_config_status() -> dict[str, Any]:
    await _wait_for_backend_init()

    from wet_mcp.embedder import (
        embedding_unavailable_reason,
        resolve_embed_backend_for_request,
    )
    from wet_mcp.reranker import resolve_rerank_backend_for_request

    # Same principle as _active_docs_backend above, one layer up -- with the
    # part that makes it easier: there is nothing to mirror here, so these call
    # the resolvers themselves and cannot drift from them.
    #
    # What they replaced was `get_backend()` / `get_reranker()`, the startup
    # singletons. In HTTP multi-user mode those are nobody's backend: they were
    # resolved from the OPERATOR's process env before any sub existed. A sub
    # whose request resolves to local ONNX -- or, on a slim image, to nothing --
    # was still told `CloudEmbeddingBackend available=true`.
    #
    # Cheap to call: every branch either hands back an already-built object or
    # constructs one that loads no model until it is actually used.
    embed_backend = resolve_embed_backend_for_request()
    reranker = resolve_rerank_backend_for_request()

    # The docs store is the local SQLite file under ~/.wet/. The path is
    # host-owned info: status is read by the operator on the box, so the
    # path is shown as-is and `backend` names where `docs_indexed` came from.
    docs_backend = _active_docs_backend()
    from wet_mcp.runtime import hull_settings, sub_root

    hs = hull_settings()
    status = {
        "auth": {
            "mode": hs.server.auth,
            "host": hs.server.host,
            "port": hs.server.port,
            # The namespace of the caller reading this status (mode 3:
            # per-user storage roots live under ~/.wet/subs/<namespace>/).
            "namespace": current_sub(),
        },
        "database": {
            "backend": docs_backend,
            "path": str(settings.get_db_path()),
            "docs_indexed": (_docs_db.stats() if _docs_db else {}),
            # docs_indexed alone cannot say why a number is what it is: zero
            # chunks reads the same whether nothing was ever indexed, an
            # indexer is running now, or every attempt failed. This is the
            # recorded outcome of those attempts, read back from the store.
            "indexing": (_docs_db.index_status() if _docs_db else {}),
        },
        "embedding": {
            "backend": (type(embed_backend).__name__ if embed_backend else None),
            "model": _backend_model_identity(embed_backend),
            "dims": _embedding_dims,
            "available": embed_backend is not None,
            # "available: false" on its own reads as a fault. Most of the time
            # it is a deployment choice (no cloud chain + DISABLE_LOCAL_EMBED),
            # and saying which knob produced it is the difference between an
            # answer and a bug hunt. None whenever embedding IS available.
            "unavailable_reason": embedding_unavailable_reason(),
        },
        "reranker": {
            "available": reranker is not None,
            "backend": (type(reranker).__name__ if reranker else None),
            "model": _backend_model_identity(reranker),
        },
        "cache": {
            "enabled": settings.wet_cache,
            # Per-caller cache file (mode-3 isolation): ~/.wet/subs/<ns>/cache.db
            "path": (str(sub_root() / "cache.db") if settings.wet_cache else None),
        },
        "settings": {
            "log_level": settings.log_level,
            "tool_timeout": settings.tool_timeout,
        },
        "search_metrics": search_metrics.snapshot(),
    }
    return status


def _handle_config_set(key: str | None, value: str | None) -> dict[str, Any]:
    if not key or value is None:
        return {"error": "key and value are required for set"}
    valid_keys = {
        "log_level",
        "tool_timeout",
        "wet_cache",
        "wet_search_budget",
    }
    if key not in valid_keys:
        import difflib

        closest = (
            difflib.get_close_matches(key, sorted(valid_keys), n=1)
            if key is not None
            else []
        )
        suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
        return {
            "error": f"Invalid key: {key}.{suggestion}",
            "valid_keys": sorted(valid_keys),
        }
    if key == "log_level":
        settings.log_level = value.upper()
        logger.remove()
        logger.add(sys.stderr, level=settings.log_level)
    elif key in ("tool_timeout", "wet_search_budget"):
        setattr(settings, key, int(value))
    elif key == "wet_cache":
        setattr(settings, key, value.lower() in ("true", "1", "yes"))
    else:
        setattr(settings, key, value)
    return {
        "status": "updated",
        "key": key,
        "value": getattr(settings, key),
    }


async def _handle_config_cache_clear() -> dict[str, Any]:
    if _web_cache:
        await asyncio.to_thread(_web_cache.clear, None, current_sub())
        return {"status": "cache cleared"}
    return {"error": "Cache is not enabled"}


def _handle_config_docs_reindex(key: str | None) -> dict[str, Any]:
    if not key:
        return {"error": "key (library name) is required"}
    if not _docs_db:
        return {"error": "Docs database not initialized"}
    lib = _docs_db.get_library(key)
    if lib:
        ver = _docs_db.get_best_version(lib["id"])
        if ver:
            _docs_db.clear_version_chunks(ver["id"])
            # A cleared version is not an indexed version: without this the
            # row keeps status='indexed', resolve_library keeps serving it as
            # latest_version, and the docs_query lazy-ingest gate never fires
            # -- the re-index then depends on the full search chain, which a
            # keyword-only subject may not have working.
            _docs_db.reset_version_index(ver["id"])
        return {
            "status": "cleared",
            "library": key,
            "hint": "Next docs search will re-index",
        }
    return {"error": f"Library '{key}' not found in index"}


async def _handle_config_warmup() -> dict[str, Any]:
    from wet_mcp.setup_tool import run_warmup

    return await run_warmup()


@mcp.tool(
    description=(
        "Server config and management. Actions: "
        "status|set|cache_clear|docs_reindex|warmup. "
        "Use help tool with tool_name='config' for full docs."
    ),
    annotations=ToolAnnotations(
        title="Config",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def config(
    action: str,
    key: str | None = None,
    value: str | None = None,
    remote_type: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Server configuration and management.

    Actions:
    - status: Show current config and status
    - set: Update runtime setting (key + value required)
    - cache_clear: Clear the caller's web cache
    - docs_reindex: Force re-index a library (key = library name)
    - warmup: Pre-download local models and run first-time setup

    Provider/model configuration (per-task cells) and auth mode are
    host-owned: edit ~/.wet/config.toml and restart — there is no
    setup wizard anymore (de-host: host-only keys, no per-user credentials).
    """
    match action:
        case "status":
            return await _handle_config_status()

        case "set":
            return _handle_config_set(key, value)

        case "cache_clear":
            return await _handle_config_cache_clear()

        case "docs_reindex":
            return _handle_config_docs_reindex(key)

        case "warmup":
            return await _handle_config_warmup()

        case _:
            import difflib

            valid_actions = [
                "cache_clear",
                "docs_reindex",
                "set",
                "status",
                "warmup",
            ]
            closest = (
                difflib.get_close_matches(action, valid_actions, n=1)
                if action is not None
                else []
            )
            suggestion = f" Did you mean '{closest[0]}'?" if closest else ""
            return {
                "error": f"Unknown action '{action}'.{suggestion}",
                "valid_actions": valid_actions,
            }


# ---------------------------------------------------------------------------
# Research (configured search chain; SearXNG retains its science category)
# ---------------------------------------------------------------------------
async def _do_research(
    query: str,
    max_results: int = 10,
    time_range: str | None = None,
    language: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> str:
    """Academic/scientific search through the configured provider chain."""
    result_str = await _run_configured_search(
        query=query,
        categories="science",
        max_results=max_results * 3,
        time_range=time_range,
        language=language,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
    )
    try:
        data = json.loads(result_str)

        # Rerank
        try:
            if "results" in data and data["results"]:
                reranked = await _rerank_results(
                    query, data["results"], top_n=max_results
                )
                data["results"] = [r for r in reranked if r.get("score", 1.0) > 0.3]
                data["total"] = len(data["results"])
        except Exception as e:
            logger.error(f"Reranking failed: {e}")

        # Re-format results for academic context
        results = data.get("results", [])

        # Enrich with academic metadata hints
        SOURCE_TYPE_MAPPING = {
            "arxiv.org": "arxiv",
            "scholar.google": "google_scholar",
            "semanticscholar.org": "semantic_scholar",
            "pubmed": "pubmed",
            "nih.gov": "pubmed",
            "doi.org": "doi",
        }
        for r in results:
            url = r.get("url", "")
            r["source_type"] = next(
                (
                    source_type
                    for domain, source_type in SOURCE_TYPE_MAPPING.items()
                    if domain in url
                ),
                "academic",
            )

        data["query"] = query
        data["search_type"] = "academic"
        return json.dumps(data, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return result_str


# ---------------------------------------------------------------------------
# Docs helpers (extracted from _do_docs_search for clarity)
# ---------------------------------------------------------------------------

# Minimum number of chunks required from llms.txt or GitHub raw docs.
# If fewer are produced, the tier is skipped in favor of crawling.
_MIN_GH_CHUNKS = 20


async def _fetch_and_chunk_docs(
    docs_url: str,
    repo_url: str = "",
    query: str = "",
    library_hint: str = "",
) -> tuple[list[dict], int]:
    """Fetch library documentation and split into searchable chunks.

    Tries content sources in priority order:
    1. llms.txt / llms-full.txt (fastest, AI-optimized)
    2. GitHub raw markdown (clean, no JS rendering needed)
    3. Crawl4AI page crawling (rendered HTML -> markdown)

    Returns:
        Tuple of (chunks, page_count).
    """
    from wet_mcp.sources.docs import (
        _try_github_raw_docs,
        chunk_llms_txt,
        chunk_markdown,
        fetch_docs_pages,
        try_llms_txt,
    )

    # Tier 0: Try llms.txt (fastest, best quality)
    llms_content = await try_llms_txt(docs_url)
    if llms_content:
        chunks = chunk_llms_txt(llms_content, base_url=docs_url)
        # Quality gate: skip llms.txt if it's too small (likely a TOC/meta file)
        if len(chunks) >= _MIN_GH_CHUNKS:
            logger.info(f"Indexed {len(chunks)} chunks from llms.txt")
            return chunks, 1
        else:
            logger.info(
                f"llms.txt produced only {len(chunks)} chunks "
                f"(min {_MIN_GH_CHUNKS}), falling through"
            )

    # chunk_markdown is CPU-bound and runs off the loop in a worker thread. A
    # large crawl would otherwise offload one page per thread at once, which
    # exhausts the default executor and starves the event loop.
    sem = asyncio.Semaphore(10)

    async def _process_page(page: dict) -> list[dict]:
        async with sem:
            p_chunks = await asyncio.to_thread(
                chunk_markdown,
                content=page["content"],
                url=page.get("url", ""),
            )
        for chunk in p_chunks:
            if not chunk.get("title") and page.get("title"):
                chunk["title"] = page["title"]
        return p_chunks

    # Tier 1: Try GitHub raw markdown (clean content, no JS rendering)
    gh_target = repo_url or docs_url
    gh_pages = await _try_github_raw_docs(
        gh_target, max_files=50, library_hint=library_hint
    )
    gh_chunks: list[dict] = []
    gh_page_count = 0
    if gh_pages:
        page_chunk_results = await asyncio.gather(
            *[_process_page(page) for page in gh_pages]
        )
        for page_chunks in page_chunk_results:
            gh_chunks.extend(page_chunks)
        gh_page_count = len(gh_pages)

        # Quality gate: if GitHub raw produced too few meaningful chunks,
        # fall through to Tier 2 (crawl docs site). This handles repos
        # where docs use template macros (Polars), RST, or other formats
        # that produce poor raw markdown.
        if len(gh_chunks) >= _MIN_GH_CHUNKS:
            logger.info(
                f"Indexed {len(gh_chunks)} chunks from {len(gh_pages)} "
                "GitHub raw markdown files"
            )
            return gh_chunks, len(gh_pages)
        else:
            logger.info(
                f"GitHub raw produced only {len(gh_chunks)} chunks "
                f"(min {_MIN_GH_CHUNKS}), falling through to crawl"
            )

    # Tier 2: Crawl docs pages (rendered HTML -> markdown)
    pages = await fetch_docs_pages(
        docs_url=docs_url,
        query=query,
        max_pages=50,
    )
    chunks: list[dict] = []
    if pages:
        page_chunk_results = await asyncio.gather(
            *[_process_page(page) for page in pages]
        )
        for page_chunks in page_chunk_results:
            chunks.extend(page_chunks)

    # If Tier 2 crawl produced no results (e.g. Cloudflare blocked) but
    # Tier 1 GitHub raw had some content (below threshold), use it instead
    # of returning nothing.  Some docs are better than no docs.
    if not chunks and gh_chunks:
        logger.info(
            f"Crawl produced 0 chunks, using {len(gh_chunks)} GitHub raw "
            f"chunks from {gh_page_count} files (below threshold but "
            "better than nothing)"
        )
        return gh_chunks, gh_page_count

    # Tier 3: Last-resort README fallback.
    # When all tiers fail AND we have a GitHub repo, fetch just the
    # README.md.  This handles repos without a docs/ directory whose
    # docs site is also uncrawlable (Cloudflare, JS-rendered, etc.).
    if not chunks:
        from wet_mcp.sources.docs import _fetch_github_readme

        readme_chunks = await _fetch_github_readme(repo_url or docs_url)
        if readme_chunks:
            logger.info(
                f"All tiers failed, using {len(readme_chunks)} chunks "
                "from GitHub README (last resort)"
            )
            return readme_chunks, 1

    logger.info(f"Indexed {len(chunks)} chunks from {len(pages)} pages")
    return chunks, len(pages)


# ---------------------------------------------------------------------------
# Docs search (library documentation with auto-indexing)
# ---------------------------------------------------------------------------

# A ``running`` record older than this counts as abandoned. The indexer lives
# in a process that can vanish without unwinding (container evicted, OOM kill,
# redeploy), and a ``running`` row nobody will ever finish would otherwise lock
# its library out of indexing forever. The pipeline's own sub-timeouts
# (_DISCOVERY_TIMEOUT + _FETCH_TIMEOUT + _SEARXNG_TIMEOUT + _FALLBACK_TIMEOUT
# plus _embed_run_timeout, which scales with the chunk count but is capped by
# _EMBED_MAX_WAVES) sum to well under this, so a live run is never mistaken for
# an abandoned one.
_INDEX_RUNNING_STALE_AFTER = 900.0


def _index_attempt_in_flight(state: dict[str, Any] | None) -> bool:
    """True when another indexer is still working on this version."""
    if not isinstance(state, dict) or state.get("state") != INDEX_STATE_RUNNING:
        return False
    started = state.get("updated_at")
    if not isinstance(started, int | float):
        # A ``running`` row with no timestamp cannot be aged out; treat it as
        # live rather than relaunch on top of an indexer that may be running.
        return True
    return (time.time() - started) < _INDEX_RUNNING_STALE_AFTER


def _format_index_timestamp(ts: Any) -> str:
    """Epoch seconds as a readable UTC stamp for a user-facing message."""
    if not isinstance(ts, int | float):
        return "an unrecorded time"
    return (
        datetime.datetime.fromtimestamp(ts, tz=datetime.UTC)
        .replace(microsecond=0)
        .isoformat()
    )


def _docs_indexing_message(
    library: str, state: dict[str, Any] | None, already_running: bool
) -> str:
    """Describe what actually happened to this library's index.

    A docs search that finds no chunks used to answer with one unconditional
    "indexing in progress, this may take 3-5 minutes" whether the version had
    never been attempted, was still running, or had failed on every previous
    try -- so a permanently broken library was reported as a slow one forever.
    """
    if already_running and isinstance(state, dict):
        return (
            f"Library '{library}' has been indexing since "
            f"{_format_index_timestamp(state.get('updated_at'))} (started by an "
            "earlier request); no second indexing run was launched. Retry "
            "shortly. In the meantime, here are temporary web search results."
        )
    if isinstance(state, dict) and state.get("state") == INDEX_STATE_FAILED:
        return (
            f"The previous indexing attempt for '{library}' failed at "
            f"{_format_index_timestamp(state.get('updated_at'))}: "
            f"{state.get('error') or 'no reason was recorded'}. A fresh attempt "
            "has started; here are temporary web search results."
        )
    return (
        f"Library '{library}' is currently being downloaded and indexed in the "
        "background (this may take 3-5 minutes). In the meantime, here are "
        "temporary web search results."
    )


def _record_index_state(ver_id: str, state: str, error: str | None = None) -> None:
    """Persist a background indexing outcome, without ever masking it.

    This is the reporting channel of last resort, so it must not be able to
    throw over the failure it is reporting: the caller is an `except` handler
    holding the real error. A missing store means there is nothing to record
    into and nothing was indexed either; a store that rejects the write leaves
    only the log, which is the very situation this record exists to improve on,
    so say so loudly rather than let it pass as recorded.
    """
    if _docs_db is None:
        return
    try:
        _docs_db.set_index_state(ver_id, state, error)
    except Exception as exc:
        logger.error(
            f"Could not record indexing state '{state}' for version {ver_id}: "
            f"{type(exc).__name__}: {exc}"
        )


async def _background_index_and_search(
    library: str,
    lib_key: str,
    language: str | None,
    docs_url: str,
    repo_url: str,
    query: str,
    version: str | None,
    lib_id: str,
    ver_id: str,
):
    """Background task to fetch, chunk, embed, and store docs."""
    try:
        from urllib.parse import urlparse

        from wet_mcp.sources.docs import _normalize_docs_url

        docs_url = _normalize_docs_url(docs_url)
        logger.info(f"Background indexing started for '{library}' from {docs_url}...")

        try:
            all_chunks, page_count = await asyncio.wait_for(
                _fetch_and_chunk_docs(
                    docs_url=docs_url,
                    repo_url=repo_url,
                    query=query,
                    library_hint=library,
                ),
                timeout=_FETCH_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                f"Docs fetch timed out after {_FETCH_TIMEOUT}s for '{library}'"
            )
            all_chunks, page_count = [], 0

        # Fallback through the configured search chain.
        if page_count <= 2 and len(all_chunks) < 100:
            fallback_query = (
                f"{library} {language} documentation"
                if language
                else f"{library} documentation"
            )
            try:
                fallback_result = await _run_configured_search(
                    query=fallback_query,
                    categories="general",
                    max_results=3,
                    timeout=15,
                )
                import json

                fallback_data = json.loads(fallback_result)
                tasks = []
                alt_urls = []
                for fr in fallback_data.get("results", []):
                    alt_url = fr.get("url", "")
                    if not alt_url or not alt_url.startswith("http"):
                        continue
                    alt_parsed = urlparse(alt_url)
                    orig_parsed = urlparse(docs_url)
                    if alt_parsed.netloc == orig_parsed.netloc:
                        continue
                    alt_urls.append(alt_url)
                    tasks.append(
                        asyncio.wait_for(
                            _fetch_and_chunk_docs(alt_url, "", query),
                            timeout=_FALLBACK_TIMEOUT,
                        )
                    )

                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, res in enumerate(results):
                        if isinstance(res, BaseException):
                            logger.warning(
                                f"Alternate docs source failed for '{library}' "
                                f"at {alt_urls[i]}: {type(res).__name__}: {res}"
                            )
                            continue
                        alt_chunks, alt_pages = res
                        if alt_pages > page_count and len(alt_chunks) > len(all_chunks):
                            docs_url = alt_urls[i]
                            all_chunks = alt_chunks
                            page_count = alt_pages
                            break
            except Exception as e:
                logger.warning(
                    f"Configured search docs fallback failed for '{library}' "
                    f"(query {fallback_query!r}); staying with "
                    f"{len(all_chunks)} chunks from {page_count} pages: "
                    f"{type(e).__name__}: {e}"
                )

        if not all_chunks:
            reason = f"Could not extract content from {docs_url}"
            logger.error(f"Background indexing failed: {reason}")
            # The log line above never leaves the process. Record the outcome
            # where the normal query path can read it, so a store reporting
            # zero chunks can say WHY instead of looking identical to one that
            # was never asked to index.
            _record_index_state(ver_id, INDEX_STATE_FAILED, reason)
            return

        # Generate embeddings
        embeddings = None
        # Set when the chunks are about to be stored without vectors. The log
        # lines below never leave the container -- which is the whole reason
        # Diagnosing a silent empty index needs the failure reason on disk -- so it is recorded on
        # the version too, where `config(action="status")` and the docs query
        # path can both read it back.
        keyword_only_reason: str | None = None
        if all_chunks:
            await _wait_for_backend_init()

            from wet_mcp.embedder import (
                embedding_unavailable_reason,
                resolve_embed_backend_for_request,
            )

            if resolve_embed_backend_for_request() is None:
                # The intended degrade, and the one the version is about to be
                # stamped 'indexed' for: chunks land keyword-searchable with no
                # vectors behind them. Same reasoning as the timeout branch
                # below -- an unremarked swap here is a store that looks
                # healthy and answers half as well.
                keyword_only_reason = (
                    f"indexed keyword-only: {len(all_chunks)} chunks stored "
                    "WITHOUT vectors because embedding was unavailable "
                    f"({embedding_unavailable_reason()})"
                )
                logger.warning(
                    f"Embedding unavailable while indexing '{library}' from "
                    f"{docs_url}: {embedding_unavailable_reason()}. "
                    f"{len(all_chunks)} chunks are stored WITHOUT vectors, so "
                    "this version answers keyword-only"
                )
            else:
                embed_texts_list = []
                for c in all_chunks:
                    parts = []
                    if c.get("title"):
                        parts.append(c["title"])
                    if c.get("heading_path") and c.get("heading_path") != c.get(
                        "title"
                    ):
                        parts.append(c["heading_path"])
                    parts.append(c["content"])
                    embed_texts_list.append(" | ".join(parts)[:2000])
                embed_budget = _embed_run_timeout(len(embed_texts_list))
                try:
                    embeddings = await asyncio.wait_for(
                        _embed_batch(embed_texts_list), timeout=embed_budget
                    )
                except TimeoutError:
                    # Storing the chunks anyway is the intended degrade (they
                    # stay keyword-searchable), but the version is then stamped
                    # 'indexed' with a full chunk_count while holding zero
                    # vectors. Without this line that swap is invisible.
                    keyword_only_reason = (
                        f"indexed keyword-only: {len(embed_texts_list)} chunks "
                        "stored WITHOUT vectors because the embedding run "
                        f"timed out after {embed_budget:.0f}s"
                    )
                    logger.error(
                        f"Embedding run timed out after {embed_budget:.0f}s for "
                        f"'{library}' ({len(embed_texts_list)} chunks from "
                        f"{docs_url}); chunks are stored WITHOUT vectors, so "
                        "this version answers keyword-only until it is "
                        "re-indexed"
                    )
                    embeddings = None

        # Drop the previous content only now that its replacement is in hand.
        # This clear used to run at launch time in _do_docs_search, so every
        # docs search on an already-indexed library wiped it first and a failed
        # re-index left nothing behind.
        _docs_db.clear_version_chunks(ver_id)

        # Store chunks
        _docs_db.add_chunks(
            version_id=ver_id,
            library_id=lib_id,
            chunks=all_chunks,
            embeddings=embeddings,
        )
        _docs_db.mark_version_indexed(ver_id, page_count, len(all_chunks))
        # last_indexed_at is now written only by mark_library_indexed; before
        # the seed/index split upsert_library stamped it as a side effect,
        # which hid the fact that this path never marked the library. Left
        # out, a library indexed here would read as permanently stale.
        # total_versions is deliberately not passed: this path takes a
        # caller-supplied `version`, so one library can own several rows in
        # `versions` (the table is UNIQUE(library_id, version)) and a
        # hardcoded 1 would be wrong.
        _docs_db.mark_library_indexed(lib_id)
        # 'done' with a note, not 'failed': the chunks ARE there and ARE
        # served. `set_index_state` writes the note to `index_error`, which the
        # status payload surfaces for every state -- while `_docs_indexing_message`
        # only quotes it for 'failed', so a healthy-but-degraded version is
        # never reported to a caller as a failed one.
        _record_index_state(ver_id, INDEX_STATE_DONE, keyword_only_reason)
        logger.info(
            f"Background indexing complete for '{library}'. Pages: {page_count}, Chunks: {len(all_chunks)}"
        )

    except Exception as e:
        # A bare `{e}` on a KeyError/TypeError prints just the attribute name,
        # which is what made the Tier 1 breakage of #1590 unreadable -- keep
        # the traceback. Formatted here rather than via
        # ``logger.opt(exception=True)`` because the stderr sink runs with
        # loguru's default ``diagnose=True``, which would dump every local
        # (chunk bodies, provider objects) into the log.
        import traceback

        logger.error(
            f"Background indexing failed for '{library}' ({docs_url}): "
            f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        )
        # And record it durably: an unexpected exception must leave the same
        # readable trace as the empty-chunks case, or the version stays
        # 'running' forever and the log is again the only witness.
        _record_index_state(ver_id, INDEX_STATE_FAILED, f"{type(e).__name__}: {e}")


async def _search_cached_index(
    lib_key: str,
    query: str,
    version: str | None,
    limit: int,
) -> dict[str, Any] | None:
    """Search an already-indexed library and return the results.

    Returns the search-result payload if the library is indexed and has
    matching chunks, or None if the library needs (re-)indexing.
    """
    from wet_mcp.sources.docs import DISCOVERY_VERSION

    lib = _docs_db.get_library(lib_key)

    if lib:
        # Invalidate cache if discovery scoring has been updated
        cached_version = lib.get("discovery_version", 0)
        if cached_version < DISCOVERY_VERSION:
            logger.info(
                f"Library '{lib_key}' cached with discovery v{cached_version} "
                f"(current v{DISCOVERY_VERSION}), forcing re-index"
            )
            lib = None  # Force re-discovery below

    if not lib:
        return None

    # Check if we have indexed chunks
    ver = _docs_db.get_best_version(lib["id"], version)
    if not ver or ver.get("chunk_count", 0) <= 0:
        return None

    # Search existing index — retrieve extra candidates for reranking
    query_embedding = await _embed(query, is_query=True)
    retrieve_limit = limit * _RERANK_CANDIDATE_MULTIPLIER

    # Without a query vector the hybrid search silently drops its semantic leg
    # and answers from BM25 alone. The reply is shaped identically either way,
    # so the caller reads a thin result set as "the docs don't cover this"
    # rather than "half the retrieval never ran" -- and retries the same query.
    retrieval_notice: str | None = None
    if query_embedding is None:
        from wet_mcp.embedder import embedding_unavailable_reason

        # No reason means a backend exists and the embed call itself failed;
        # _embed already logged which, and degraded deliberately.
        why = (
            embedding_unavailable_reason() or "the embedding call failed for this query"
        )
        retrieval_notice = (
            f"Vector search unavailable ({why}); these results are keyword-only."
        )

    results = _docs_db.search(
        query=query,
        library_name=lib_key,
        version=version,
        limit=retrieve_limit,
        query_embedding=query_embedding,
    )

    if not results:
        return None

    # HyDE augmentation: if initial results are poor, try hypothetical doc
    from wet_mcp.sources.search_strategies import (
        _HYDE_SCORE_THRESHOLD,
        generate_hyde_query,
    )

    scores = [r.get("score", 0) for r in results]
    if len(results) < 3 or (scores and max(scores) < _HYDE_SCORE_THRESHOLD):
        library_name = lib_key.split(":")[0]
        hyde_text = await generate_hyde_query(query, library_name)
        if hyde_text:
            hyde_embedding = await _embed(hyde_text, is_query=False)
            hyde_results = _docs_db.search(
                query=query,
                library_name=lib_key,
                version=version,
                limit=retrieve_limit,
                query_embedding=hyde_embedding,
            )
            if hyde_results:
                hyde_scores = [r.get("score", 0) for r in hyde_results]
                # Use HyDE results if they have better top score
                if max(hyde_scores, default=0) > max(scores, default=0):
                    results = hyde_results

    # Extract original library name (strip language suffix for display)
    library = lib_key.split(":")[0]

    # Rerank if available, otherwise truncate to limit
    results = await _rerank_results(query, results, limit)
    return {
        "library": library,
        "version": ver.get("version", "latest"),
        "results": results,
        "total": len(results),
        "source": "cached_index",
        "retrieval": ("keyword_only" if query_embedding is None else "hybrid"),
        "retrieval_notice": retrieval_notice,
    }


async def _discover_docs_url(
    library: str,
    language: str | None,
) -> tuple[str, str, str, str]:
    """Auto-discover documentation URL for a library.

    Tries registry discovery first, then the configured web-search chain.

    Returns:
        Tuple of (docs_url, repo_url, registry, description). Any field
        may be an empty string if discovery failed.
    """
    from wet_mcp.sources.docs import (
        discover_library,
    )

    docs_url = ""
    repo_url = ""
    registry = ""
    description = ""

    # Discover library metadata from registries (with sub-timeout)
    try:
        discovery = await asyncio.wait_for(
            discover_library(library, language=language),
            timeout=_DISCOVERY_TIMEOUT,
        )
    except TimeoutError:
        logger.warning(
            f"Discovery timed out after {_DISCOVERY_TIMEOUT}s for '{library}'"
        )
        discovery = None

    if discovery:
        docs_url = discovery.get("homepage", "")
        repo_url = discovery.get("repository", "")
        registry = discovery.get("registry", "")
        description = discovery.get("description", "")
    else:
        # Fallback: use the configured search chain to find docs.
        # Include language context for better results
        search_query = (
            f"{library} {language} documentation"
            if language
            else f"{library} official documentation"
        )
        logger.info(
            f"Registry lookup failed, trying configured search for '{library}'..."
        )
        try:
            search_result = await _run_configured_search(
                query=search_query,
                categories="general",
                max_results=3,
                timeout=15,
            )
            search_data = json.loads(search_result)
            top_results = search_data.get("results", [])
            if top_results:
                docs_url = top_results[0].get("url", "")
        except TimeoutError:
            logger.warning("Configured search discovery fallback timed out")
        except json.JSONDecodeError:
            # Startup failures return an "Error: ..." string. Keep a failed
            # search distinguishable from a library without a docs page.
            logger.warning(
                f"Configured search discovery fallback for '{library}' returned "
                f"non-JSON output, so no docs URL was found: "
                f"{search_result[:200]!r}"
            )

    return docs_url, repo_url, registry, description


async def _do_docs_search(
    library: str,
    query: str,
    language: str | None = None,
    version: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search library documentation. Auto-discovers and indexes if needed."""
    if not _docs_db:
        return {"error": "Error: Docs database not initialized"}

    # Build library identity — include language for DB disambiguation
    # e.g., "redis" (no lang) vs "redis:python" vs "redis:javascript"
    lib_key = f"{library}:{language.lower()}" if language else library

    # Step 1: Check if library is already indexed
    cached = await _search_cached_index(lib_key, query, version, limit)
    if cached:
        return cached

    # Step 2: Auto-discover and index
    logger.info(f"Library '{lib_key}' not indexed, discovering docs...")

    docs_url, repo_url, registry, description = await _discover_docs_url(
        library, language
    )

    if not docs_url:
        # When no docs URL found but we have a GitHub repo URL,
        # use it as the docs source — _fetch_and_chunk_docs will
        # try GitHub raw docs (Tier 1) which often has good docs/.
        # The host check is a suffix match, not a substring one: `repo_url`
        # came from publisher-controlled registry metadata and is about to
        # become a URL this server fetches.
        from wet_mcp.sources.docs import _is_github_url

        if _is_github_url(repo_url):
            docs_url = repo_url
            logger.info(f"No docs URL for '{library}', using GitHub repo: {repo_url}")
        else:
            return {
                "error": f"Could not find documentation URL for '{library}'",
                "hint": "Try providing the docs URL directly via extract action",
            }

    # Apply version to docs URL if applicable (e.g. ReadTheDocs, docs.rs)
    from wet_mcp.sources.docs import _apply_version_to_url

    docs_url = _apply_version_to_url(docs_url, version)

    # Create/update library record
    lib_id = _docs_db.upsert_library(
        name=lib_key,
        docs_url=docs_url,
        registry=registry,
        description=description,
    )
    ver_id = _docs_db.upsert_version(
        library_id=lib_id,
        version=version or "latest",
        docs_url=docs_url,
    )

    # Step 3: launch a background indexer, unless one is already working this
    # version. The old-chunk clear that used to sit here has moved into the
    # indexer, next to the write that replaces them: clearing before the
    # replacement exists meant one failed re-index destroyed the library's
    # only good copy, and left every later search restarting the same failing
    # work against an empty store.
    index_state = _docs_db.get_index_state(ver_id)
    already_running = _index_attempt_in_flight(index_state)
    if not already_running:
        _docs_db.set_index_state(ver_id, INDEX_STATE_RUNNING)
        _launch_background_task(
            _background_index_and_search(
                library=library,
                lib_key=lib_key,
                language=language,
                docs_url=docs_url,
                repo_url=repo_url,
                query=query,
                version=version,
                lib_id=lib_id,
                ver_id=ver_id,
            ),
            f"docs-index:{lib_key}",
        )

    fallback_data = await _do_immediate_fallback_search(
        docs_url=docs_url,
        library=library,
        language=language,
        query=query,
        limit=limit,
    )

    return {
        "status": "indexing_in_progress",
        "message": _docs_indexing_message(library, index_state, already_running),
        # The last attempt on record, machine-readable next to the prose. Named
        # for what it is: when one was already running this IS that run, and
        # when a fresh one was just launched this is the attempt it follows
        # (carrying the reason the previous one failed).
        "last_index_attempt": index_state,
        "temporary_results": fallback_data.get("results", []),
        "library": library,
        "docs_url": docs_url,
    }


async def _do_immediate_fallback_search(
    docs_url: str,
    library: str,
    language: str | None,
    query: str,
    limit: int,
) -> dict:
    """Perform an immediate fallback web search while docs are indexing."""
    fallback_search_query = (
        f"site:{urlparse(docs_url).netloc} {query}"
        if docs_url
        else f"{library} {language} {query}"
    )
    fallback_data = {"results": []}
    try:
        fallback_result = await _run_configured_search(
            query=fallback_search_query,
            categories="general",
            max_results=limit,
            timeout=15,
        )
        fallback_data = json.loads(fallback_result)
        if "results" in fallback_data and fallback_data["results"]:
            fallback_data["results"] = await _rerank_results(
                query, fallback_data["results"], top_n=limit
            )
    except Exception as e:
        # The caller ships this as `temporary_results` next to a message
        # promising web results. An empty list therefore reads as "the web had
        # nothing" rather than "the fallback search never ran".
        logger.warning(
            f"Immediate fallback search failed for '{library}' "
            f"(query {fallback_search_query!r}); temporary_results will be "
            f"empty: {type(e).__name__}: {e}"
        )
    return fallback_data


def build_http_app(settings=None):
    """Build the authenticated HTTP MCP app (Starlette), no port bind.

    Composition (de-host): the MCP SDK's ``streamable_http_app()`` carries
    only the session-manager lifespan, so this outer Starlette app runs BOTH
    lifespans — wet's own (SearXNG warmup, cache/docs-db init, backend init)
    and the session manager's — via an AsyncExitStack. :class:`HullAuthMiddleware`
    (pure ASGI) authenticates every request BEFORE the MCP handler and binds
    the identity to a contextvar that tools read with
    :func:`hull_core.auth.context.current_user`.
    """
    from contextlib import AsyncExitStack, asynccontextmanager

    from hull_core.auth.asgi import HullAuthMiddleware
    from starlette.applications import Starlette
    from starlette.routing import Mount

    from wet_mcp.runtime import build_authenticator

    inner = mcp.streamable_http_app()
    authenticator = build_authenticator(settings)

    @asynccontextmanager
    async def _combined_lifespan(app):  # noqa: ANN001, ANN202
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(_lifespan(mcp))
            await stack.enter_async_context(inner.router.lifespan_context(inner))
            yield

    app = HullAuthMiddleware(inner, authenticator)
    return Starlette(lifespan=_combined_lifespan, routes=[Mount("/", app=app)])


def _is_loopback_host(host: str) -> bool:
    if host in ("localhost", "::1", "[::1]"):
        return True
    try:
        return int(socket.inet_aton(host).hex(), 16) & 0xFF000000 == 0x7F000000
    except OSError:
        return False


class ServerConfigError(ValueError):
    """Invalid server start configuration."""


def run_server_blocking(
    host: str | None = None,
    port: int | None = None,
    settings=None,
) -> None:
    """Blocking entry point: acquire the lifecycle lock, serve until stopped.

    The ONLY way wet-mcp runs (spec §3): one HTTP process, MCP endpoint at
    ``http://host:port/mcp``, auth per ``~/.wet/config.toml`` ([server]
    auth = no-auth | token | multi). In no-auth mode a non-loopback bind is
    refused — an unauthenticated listener must never leave localhost.
    """
    import uvicorn

    from wet_mcp.runtime import hull_settings

    hs = hull_settings()
    bind_host = host or hs.server.host
    bind_port = port or hs.server.port

    if hs.server.auth == "no-auth" and not _is_loopback_host(bind_host):
        raise ServerConfigError(
            f"auth = 'no-auth' only permits loopback binds, refusing host "
            f"{bind_host!r} (set [server] auth to 'token' or 'multi' in "
            "~/.wet/config.toml for a shared listener)"
        )

    from hull_core.lifecycle.lock import LifecycleLock

    lock = LifecycleLock("wet", bind_port)
    with lock:
        app = build_http_app(hs)
        logger.info(
            f"wet-mcp MCP endpoint: http://{bind_host}:{bind_port}/mcp "
            f"(auth mode: {hs.server.auth})"
        )
        uvicorn.run(app, host=bind_host, port=bind_port, log_level="info")


def main() -> None:
    """Blocking server entry (used by `wet server start` and `python -m wet-mcp`).

    De-host: there is no stdio spawn mode and no ``--http`` flag anymore —
    the server is always the HTTP MCP endpoint. Bind host/port come from
    ``~/.wet/config.toml`` ([server] host/port), overridable via
    WET_HOST / WET_PORT env for container deployments.
    """
    host = os.environ.get("WET_HOST") or None
    port_env = os.environ.get("WET_PORT")
    port = int(port_env) if port_env else None
    run_server_blocking(host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    main()
