"""Dual-backend embedding: Cloud ([models.embed] provider cell) + fastretrieval (local ONNX).

The backend is resolved once at startup:
- A configured ``[models.embed]`` cell (``base_url + api_key + model``,
  OpenAI-spec HTTP, ``~/.wet/config.toml``) -> Cloud via the shared hull-core
  provider client (:mod:`wet_mcp.runtime`).
- No cell -> Local ONNX via fastretrieval.

Embeddings are truncated to the configured dims in server._embed().
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from loguru import logger

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# Retry config for transient errors (rate limits, 5xx, network).
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds, doubles each retry


# Patterns marking a PERMANENT client-side error (invalid request, unsupported
# capability, auth). A provider's 4xx arrives as ProviderError whose message
# embeds the upstream status and body verbatim, so classification MUST look at
# the message semantics, not the exception class or status code. Retrying a
# permanent error re-sends the same doomed request and (worse) would block
# capability fallbacks such as dropping an unsupported `dimensions` argument.
_PERMANENT_PATTERNS = (
    "not a valid",
    "not support",
    "unsupported",
    "invalid request",
    "invalid_request",
    "invalid api key",
    "output_dimension",
    "unauthorized",
    "forbidden",
    "authentication",
    "no such model",
    "model not found",
    "does not exist",
    "401",
    "403",
    "404",
    "422",
)

# Patterns marking a TRANSIENT error worth retrying (rate limit, 5xx, network).
_RETRYABLE_PATTERNS = (
    "rate limit",
    "rate_limit",
    "429",
    "quota",
    "too many requests",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection",
    "temporarily unavailable",
    "unavailable",
    "overloaded",
)


def _is_retryable(exc: Exception) -> bool:
    """Return True only for TRANSIENT errors worth retrying.

    Classifies on error semantics, NOT the exception class name or status
    code: :class:`~hull_core.providers.openai_spec.ProviderError` embeds the
    provider's status + body verbatim (e.g. ``provider returned 422: ...
    output_dimension ...``) and transport failures are wrapped as 502s whose
    text contains "connection" -- matching either blindly would wrongly retry
    a request that can never succeed and skip the dimensions fallback.
    """
    msg = str(exc).lower()
    if any(p in msg for p in _PERMANENT_PATTERNS):
        return False
    return any(p in msg for p in _RETRYABLE_PATTERNS)


def _is_unsupported_param(exc: Exception, param: str) -> bool:
    """Check if the error is due to an unsupported parameter."""
    msg = str(exc).lower()
    # "dimensions" parameter is the primary one we care about for fallback
    if param == "dimensions":
        return any(
            p in msg
            for p in (
                "dimensions",
                "output_dimension",
                "output_dimensionality",
                "unexpected keyword argument",
                "invalid argument",
                "unsupported parameter",
            )
        )
    return False


# ---------------------------------------------------------------------------
# Backend Protocol
# ---------------------------------------------------------------------------


class EmbeddingBackend(Protocol):
    """Protocol for embedding backends."""

    async def embed_texts(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed a batch of texts. Returns list of embedding vectors."""
        ...  # pragma: no cover

    async def embed_single(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a single text. Returns embedding vector."""
        ...  # pragma: no cover

    async def embed_single_query(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a query text. Returns embedding vector.

        Only the local ONNX backend implements a true asymmetric query
        embedding; the cloud leg embeds queries like documents.
        """
        ...  # pragma: no cover

    async def check_available(self) -> int:
        """Check if backend is available.

        Returns:
            Embedding dimensions if available, 0 if not.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Cloud Backend ([models.embed] provider cell)
# ---------------------------------------------------------------------------


class CloudEmbeddingBackend:
    """Cloud embedding via the ``[models.embed]`` provider cell.

    Wraps exactly one :class:`~hull_core.providers.openai_spec.
    OpenAICompatClient` built from the cell; the cell owns base_url, api_key,
    and model -- there is no provider prefix and no per-request credential
    resolution.
    """

    MAX_BATCH_SIZE = 96  # Common safe batch size across providers
    # In-flight provider requests while draining a multi-batch embed run
    # (the semaphore in embed_texts). Callers that budget the whole run --
    # the background indexer's wait_for ceiling -- read this instead of
    # re-guessing the batch geometry.
    CONCURRENCY = 8

    def __init__(self, client) -> None:
        self._client = client

    @property
    def model(self) -> str:
        """The cell-owned embedding model id (for logs and diagnostics)."""
        return self._client.cell.model

    async def _embed_batch_inner(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed a single batch with retry logic for transient errors.

        Tries server-side MRL truncation first (``dimensions`` param).
        If the provider rejects ``dimensions``, retries without it and
        truncates locally. This ensures providers that don't support
        ``dimensions`` still work.
        """
        use_dimensions = dimensions
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                embeddings = await self._client.embeddings(
                    texts, dimensions=use_dimensions
                )
                # Truncate locally if server returned more dims than requested
                if dimensions and embeddings and len(embeddings[0]) > dimensions:
                    embeddings = [e[:dimensions] for e in embeddings]
                return embeddings
            except Exception as e:
                # A dimensions rejection is PERMANENT -- retrying with the same
                # dims can never succeed. Recover (drop `dimensions`, truncate
                # locally) BEFORE the retryability check: ProviderError embeds
                # the provider's status/body, so retry classification must not
                # gate this capability fallback.
                if use_dimensions and _is_unsupported_param(e, "dimensions"):
                    logger.warning(
                        f"Provider {self.model} rejected dimensions="
                        f"{use_dimensions}; retrying without it and truncating "
                        f"locally: {e}"
                    )
                    use_dimensions = None
                    continue

                last_exc = e
                if attempt < MAX_RETRIES - 1 and _is_retryable(e):
                    delay = RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        f"Embedding retry {attempt + 1}/{MAX_RETRIES} "
                        f"after {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    break

        logger.error(f"Embedding failed ({self.model}): {last_exc}")
        assert last_exc is not None  # guaranteed by loop logic
        raise last_exc

    async def embed_texts(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed texts with auto batch splitting."""
        if not texts:
            return []

        if len(texts) <= self.MAX_BATCH_SIZE:
            return await self._embed_batch_inner(texts, dimensions)

        # Split into batches
        all_embeddings: list[list[float]] = []
        total_batches = (len(texts) + self.MAX_BATCH_SIZE - 1) // self.MAX_BATCH_SIZE
        logger.info(
            f"Splitting {len(texts)} texts into {total_batches} batches "
            f"(max {self.MAX_BATCH_SIZE}/batch)"
        )

        # The batches go out to a remote embedding API, so they are issued
        # together rather than one after another. The semaphore is what keeps a
        # large document from opening one request per batch at once and hitting
        # the provider's rate limit.
        sem = asyncio.Semaphore(self.CONCURRENCY)

        async def _embed_with_sem(
            batch: list[str], batch_num: int
        ) -> list[list[float]]:
            async with sem:
                logger.debug(
                    f"Embedding batch {batch_num}/{total_batches}: {len(batch)} texts"
                )
                return await self._embed_batch_inner(batch, dimensions)

        tasks = []
        for i in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[i : i + self.MAX_BATCH_SIZE]
            batch_num = i // self.MAX_BATCH_SIZE + 1
            tasks.append(_embed_with_sem(batch, batch_num))

        batch_results = await asyncio.gather(*tasks)
        for batch_result in batch_results:
            all_embeddings.extend(batch_result)

        return all_embeddings

    async def embed_single(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a single text."""
        results = await self.embed_texts([text], dimensions)
        return results[0]

    async def embed_single_query(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a query text.

        The OpenAI-spec ``/embeddings`` endpoint has no asymmetric query mode
        (no instruction prefix), so queries embed exactly like documents --
        raw ``embed_single``. Only the local ONNX backend has a true query
        embedding.
        """
        return await self.embed_single(text, dimensions)

    async def check_available(self) -> int:
        """Return the cell model's native embedding dims, 0 when unavailable.

        Distinguishes between invalid API keys (warning) and other
        failures (debug) so users know when their key is wrong.
        """
        try:
            embeddings = await self._client.embeddings(["ping"])
            if embeddings:
                dim = len(embeddings[0])
                logger.info(f"Embedding model {self.model} available (dims={dim})")
                return dim
            return 0
        except Exception as e:
            msg = str(e).lower()
            if any(
                p in msg for p in ("401", "403", "invalid", "unauthorized", "api key")
            ):
                logger.warning(
                    f"API key invalid for {self.model}: {e}. "
                    "Check the api_key of the [models.embed] cell in "
                    "~/.wet/config.toml."
                )
            else:
                logger.debug(f"Embedding model {self.model} not available: {e}")
            return 0


# ---------------------------------------------------------------------------
# fastretrieval Backend (local ONNX)
# ---------------------------------------------------------------------------


class LocalEmbeddingBackend:
    """Local ONNX embedding via fastretrieval's configured model.

    Uses last-token pooling with instruction-aware queries.
    Model is downloaded on first use (~0.57GB).
    Batch size is forced to 1 (static ONNX graph).
    """

    # Default model supplied by fastretrieval
    DEFAULT_MODEL = "n24q02m/Qwen3-Embedding-0.6B-ONNX"

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model = None

    def _get_model(self):
        """Lazy-load the embedding model.

        On first call, downloads the ONNX model (~570 MB) from HuggingFace
        if not already cached. Logs a warning so users know why startup is slow.
        """
        if self._model is None:
            from fastretrieval import TextEmbedding

            logger.warning(
                f"Loading local embedding model: {self._model_name} "
                "(~570 MB download on first run). "
                "Set the [models.embed] cell in ~/.wet/config.toml to use cloud embedding instead."
            )
            self._model = TextEmbedding(model_name=self._model_name)
            logger.info("Local embedding model loaded")
        return self._model

    async def embed_texts(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed texts using local ONNX model."""
        if not texts:
            return []

        model = self._get_model()

        # Local inference is CPU-bound, use to_thread to keep loop responsive
        def _embed():
            # Pass dim to model.embed() so MRL truncation happens BEFORE L2-normalization
            kwargs = {}
            if dimensions and dimensions > 0:
                kwargs["dim"] = dimensions
            return list(model.embed(texts, **kwargs))

        embeddings = await asyncio.to_thread(_embed)
        return [emb.tolist() for emb in embeddings]

    async def embed_single(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a single text (document/passage)."""
        results = await self.embed_texts([text], dimensions)
        return results[0]

    async def embed_single_query(
        self,
        text: str,
        dimensions: int | None = None,
    ) -> list[float]:
        """Embed a query with instruction prefix (asymmetric retrieval)."""
        model = self._get_model()

        def _embed_query():
            kwargs = {}
            if dimensions and dimensions > 0:
                kwargs["dim"] = dimensions
            return list(model.query_embed(text, **kwargs))

        result = await asyncio.to_thread(_embed_query)
        return result[0].tolist()

    async def check_available(self) -> int:
        """Check if fastretrieval is available."""
        try:
            model = self._get_model()

            def _check():
                return list(model.embed(["test"]))

            result = await asyncio.to_thread(_check)
            if result:
                dim = len(result[0])
                logger.info(
                    f"Local embedding {self._model_name} available (dims={dim})"
                )
                return dim
            return 0
        except Exception as e:
            logger.warning(f"Local embedding not available: {e}")
            return 0


# ---------------------------------------------------------------------------
# Factory + module-level convenience functions
# ---------------------------------------------------------------------------

_backend: EmbeddingBackend | None = None

# Shared local ONNX backend for all requests without a startup singleton.
# Local inference is stateless and key-free, so a single instance is safely
# shared. Lazily created so deployments that never fall back to the local leg
# don't download the model.
_shared_local_backend: LocalEmbeddingBackend | None = None


def get_backend() -> EmbeddingBackend | None:
    """Get the current embedding backend singleton (startup-resolved)."""
    return _backend


def clear_backend() -> None:
    """Clear the startup singleton after backend validation fails."""
    global _backend
    _backend = None


def _shared_local_embed_backend() -> LocalEmbeddingBackend:
    """Return the process-shared local ONNX embedding backend (lazy)."""
    global _shared_local_backend
    if _shared_local_backend is None:
        _shared_local_backend = LocalEmbeddingBackend()
    return _shared_local_backend


def resolve_embed_backend_for_request() -> EmbeddingBackend | None:
    """Resolve the embedding backend for the CURRENT request.

    The startup singleton wins (cloud via the ``[models.embed]`` cell, or
    local). Without one, the process-shared local ONNX backend serves every
    request -- unless the local leg is unavailable (``DISABLE_LOCAL_EMBED``,
    or an image built without the ONNX extras), in which case embedding is
    ``None``: gracefully unavailable, keyword-only.

    There is no per-request credential resolution any more: providers are
    host-configured cells, not per-sub secrets.
    """
    backend = get_backend()
    if backend is not None:
        return backend

    from wet_mcp.config import settings

    if not settings.local_embed_available():
        return None
    return _shared_local_embed_backend()


def no_local_embed_clause() -> str:
    """Name the reason the local ONNX embedding leg is out, for a human.

    Three states, three different actions, so they must not share one string.
    Saying "DISABLE_LOCAL_EMBED is set" on an image that never shipped
    ``fastretrieval`` sends the reader after a var they never set -- and having
    checked it and found it empty, they conclude the message is wrong. The
    absent-image wording says instead that this is a property of the build, so
    the answer is "configure the [models.embed] cell", not "unset a flag".
    """
    from wet_mcp.config import local_onnx_installed, settings

    if local_onnx_installed() and not settings.local_embed_available():
        # Installed but not available == the deployment disabled the local leg.
        return "this deployment runs with DISABLE_LOCAL_EMBED set"
    if not local_onnx_installed():
        return (
            "this image has no local ONNX leg installed (no fastretrieval or "
            "onnxruntime, which the slim container build removes on purpose)"
        )
    # Enabled and installed, yet nothing was resolved: it broke on load.
    return "the local ONNX leg failed to load"


def embedding_unavailable_reason() -> str | None:
    """Why this request has no embedding backend, or ``None`` if it has one.

    A caller that degrades to keyword-only needs to say WHY in its reply. The
    degraded result set is shaped exactly like a working hybrid one, so silence
    reads as "semantic search ran and matched little" when semantic search
    never ran at all.

    Mirrors :func:`resolve_embed_backend_for_request` rather than re-deriving
    the decision: it asks that function first, so a reason can only be produced
    for a request that genuinely has no backend.
    """
    if resolve_embed_backend_for_request() is not None:
        return None
    return (
        "no embedding backend is available: the [models.embed] provider cell "
        "is unconfigured (set base_url + api_key + model in ~/.wet/config.toml) "
        f"and {no_local_embed_clause()}"
    )


def init_backend(backend_type: str, model: str | None = None) -> EmbeddingBackend:
    """Initialize and cache the embedding backend.

    Args:
        backend_type: 'cloud' or 'local'.
        model: Local ONNX model override ('local' only). Ignored for 'cloud':
            the [models.embed] cell owns the model.

    Returns:
        Initialized backend instance.
    """
    global _backend

    if backend_type == "cloud":
        from wet_mcp.runtime import cell_configured, provider_client

        if not cell_configured("embed"):
            raise RuntimeError(
                "cloud embedding requested but the [models.embed] cell is not "
                "configured: set base_url + api_key + model in ~/.wet/config.toml"
            )
        _backend = CloudEmbeddingBackend(provider_client("embed"))
    elif backend_type == "local":
        _backend = LocalEmbeddingBackend(model)
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")

    return _backend
