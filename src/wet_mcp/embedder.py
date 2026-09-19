"""Dual-backend embedding: Cloud (litellm passthrough via mcp_core.llm) + fastretrieval (local ONNX).

Backend is inferred from the EMBEDDING_MODELS chain:
- Non-empty chain (with a configured provider key) -> Cloud via mcp_core.llm.
- Empty chain -> Local ONNX via fastretrieval.

Embeddings are truncated to the configured dims in server._embed().
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Protocol

from loguru import logger

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# Retry config for transient errors (rate limits, 5xx, network).
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds, doubles each retry


# Patterns marking a PERMANENT client-side error (invalid request, unsupported
# capability, auth). litellm frequently re-wraps these as APIConnectionError --
# whose class name contains "connection" and whose status_code is a hardcoded
# 500 -- so classification MUST look at the message semantics, not the exception
# class or status code. Retrying a permanent error re-sends the same doomed
# request and (worse) would block capability fallbacks such as dropping an
# unsupported `dimensions` argument.
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

    Classifies on error semantics, NOT the exception class name or a synthetic
    status_code: litellm wraps a provider's permanent 4xx (e.g. a 422 "invalid
    output_dimension") as ``APIConnectionError`` whose repr contains "connection"
    and whose ``status_code`` is a hardcoded 500 -- matching either would wrongly
    retry a request that can never succeed and skip the dimensions fallback.
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

    async def check_available(self) -> int:
        """Check if backend is available.

        Returns:
            Embedding dimensions if available, 0 if not.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# Provider detection for embedding models
# ---------------------------------------------------------------------------


def _detect_embedding_provider(model: str) -> str:
    """Detect provider from model name.

    Returns 'gemini', 'openai', 'cohere', or 'jina'.
    """
    lower = model.lower()
    if lower.startswith("gemini/") or "gemini" in lower:
        return "gemini"
    if lower.startswith("jina_ai/") or lower.startswith("jina"):
        return "jina"
    if lower.startswith("embed-") or lower.startswith("cohere/"):
        return "cohere"
    # text-embedding-3-large, text-embedding-ada-002, etc.
    if lower.startswith("text-embedding") or lower.startswith("openai/"):
        return "openai"
    # Default fallback: check env vars
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("COHERE_API_KEY"):
        return "cohere"
    return "openai"


def _strip_provider(model: str) -> str:
    """Strip provider prefix (e.g. 'gemini/model' -> 'model')."""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


# ---------------------------------------------------------------------------
# Cloud Backend (litellm passthrough via mcp_core.llm)
# ---------------------------------------------------------------------------


class CloudEmbeddingBackend:
    """Cloud embedding via mcp_core.llm (litellm passthrough)."""

    MAX_BATCH_SIZE = 96  # Common safe batch size across providers
    # In-flight provider requests while draining a multi-batch embed run
    # (the semaphore in embed_texts). Callers that budget the whole run --
    # the background indexer's wait_for ceiling -- read this instead of
    # re-guessing the batch geometry.
    CONCURRENCY = 8

    def __init__(
        self,
        model: str,
        api_base: str | None = None,
        api_key: str | None = None,
    ):
        self.model = model
        self.api_base = api_base
        self.api_key = api_key
        self._provider = _detect_embedding_provider(model)

    async def _embed_batch_inner(
        self,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed a single batch with retry logic for transient errors.

        Tries server-side MRL truncation first (``dimensions`` param).
        If the provider rejects ``dimensions``, retries without it and
        truncates locally. This ensures Gemini, Cohere, and other
        providers that don't support ``dimensions`` still work.
        """
        use_dimensions = dimensions
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                embeddings = await self._call_provider(texts, use_dimensions)
                # Truncate locally if server returned more dims than requested
                if dimensions and embeddings and len(embeddings[0]) > dimensions:
                    embeddings = [e[:dimensions] for e in embeddings]
                return embeddings
            except Exception as e:
                # A dimensions rejection is PERMANENT -- retrying with the same
                # dims can never succeed. Recover (drop `dimensions`, truncate
                # locally) BEFORE the retryability check: litellm may wrap the
                # provider's 422 as an APIConnectionError, so retry
                # classification must not gate this capability fallback.
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

    def _litellm_model(self) -> str:
        """Map wet's model naming to a litellm ``provider/model`` string."""
        if "/" in self.model:
            return self.model
        if self._provider == "jina":
            return f"jina_ai/{self.model}"
        if self._provider == "gemini":
            return f"gemini/{self.model}"
        if self._provider == "cohere":
            return f"cohere/{self.model}"
        # OpenAI-style bare names (text-embedding-3-*) pass through as-is.
        return self.model

    async def _call_provider(
        self, texts: list[str], dimensions: int | None = None
    ) -> list[list[float]]:
        """Single cloud path via mcp_core.llm (litellm passthrough)."""
        # Lazy import: litellm costs ~1-2s on first import.
        from mcp_core.llm import aembedding

        from wet_mcp.credential_state import api_base_for_task, api_key_for_model

        kwargs: dict = {}
        if dimensions:
            kwargs["dimensions"] = dimensions
        if self._provider == "cohere":
            kwargs["input_type"] = "search_document"

        litellm_model = self._litellm_model()
        # Resolve the provider key AND custom endpoint from the request-scoped
        # per-sub bucket (HTTP multi-user) or the process env (single-user);
        # explicit init-time overrides win. Avoids relying on os.environ, which
        # bled keys/endpoints across concurrent users. SSRF-vetted downstream
        # in mcp_core.llm dispatch.
        response = await aembedding(
            model=litellm_model,
            input=texts,
            api_base=self.api_base or api_base_for_task("EMBEDDING_API_BASE"),
            api_key=self.api_key or api_key_for_model(litellm_model),
            **kwargs,
        )

        # litellm embedding items may be pydantic ``Embedding`` objects or
        # plain dicts depending on provider/version — handle both shapes.
        def _idx(item: Any) -> int:
            return (
                item.get("index", 0)
                if isinstance(item, dict)
                else getattr(item, "index", 0)
            )

        def _vec(item: Any) -> list[float]:
            return item["embedding"] if isinstance(item, dict) else item.embedding

        data = sorted(response.data or [], key=_idx)
        return [_vec(item) for item in data]

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

    async def check_available(self) -> int:
        """Check if the cloud model is available via test request.

        Distinguishes between invalid API keys (warning) and other
        failures (debug) so users know when their keys are wrong.
        """
        try:
            embeddings = await self._call_provider(["test"])
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
                    "Check your API_KEYS configuration."
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
                "Set API_KEYS to use cloud embedding instead."
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

# Shared local ONNX backend for the HTTP multi-user path. Local inference is
# stateless and key-free, so a single instance is safely shared across subs
# (no per-sub data flows through it). Lazily created so single-user / stdio
# deployments that never hit the multi-user resolver don't download the model.
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

    * **Stdio / single-user HTTP** (``_current_sub`` is ``None``): return the
      module-level startup singleton resolved once at lifespan start
      (:func:`get_backend`). Behaviour is unchanged.

    * **HTTP multi-user** (``_current_sub`` set): resolve PER REQUEST from the
      sub's credential bucket. If the sub has a cloud embedding chain whose
      provider key is present, build a fresh request-scoped
      :class:`CloudEmbeddingBackend` carrying that sub's key explicitly (so the
      key flows down the call, never into ``os.environ``). With no such chain,
      fall back to the process-shared local ONNX backend -- unless that leg is
      unavailable, in which case embedding is ``None``: gracefully unavailable.

    That last exit is the same three-way resolution
    :meth:`Settings.resolve_embedding_backend` performs at startup, where it
    is spelled ``'unavailable'``, and it asks the same predicate
    (:meth:`Settings.local_embed_available`) so the two cannot drift. Both
    inputs matter: ``DISABLE_LOCAL_EMBED`` is what a slim deployment sets, and
    whether ``fastretrieval`` is installed is what is actually true of the image.
    Consulting only the flag meant a slim image whose operator forgot it handed
    back a backend that raises ``ModuleNotFoundError`` on first use, failing the
    entire index instead of storing keyword-searchable chunks without vectors.

    ``None`` here, specifically -- NOT the startup singleton. That one was
    resolved from the OPERATOR's process env, and lending it to an arbitrary
    sub bills the operator's provider account for that sub's traffic.

    A per-sub request NEVER rebinds the module-level ``_backend`` singleton —
    that would let one user's cloud model/key serve another concurrent user
    (cross-sub contamination). The startup singleton is read-only here.
    """
    from wet_mcp.config import settings
    from wet_mcp.credential_state import (
        api_key_for_model,
        credentials_for_current_request,
        get_current_sub,
    )

    if get_current_sub() is None:
        return get_backend()

    creds = credentials_for_current_request()
    chain = settings.embedding_chain_for_creds(creds)
    if chain:
        model = chain[0]
        return CloudEmbeddingBackend(model, api_key=api_key_for_model(model))
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
    the answer is "give this deployment a cloud chain", not "unset a flag".
    """
    from wet_mcp.config import local_onnx_installed, settings

    if settings.disable_local_embed:
        return "this deployment runs with DISABLE_LOCAL_EMBED set"
    if not local_onnx_installed():
        return (
            "this image has no local ONNX leg installed (no fastretrieval or "
            "onnxruntime, which the slim Cloudflare container build removes "
            "on purpose)"
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
    from wet_mcp.credential_state import get_current_sub

    if resolve_embed_backend_for_request() is not None:
        return None
    if get_current_sub() is None:
        return (
            "no embedding backend was initialised at startup: no EMBEDDING_MODELS "
            f"chain with a configured provider key, and {no_local_embed_clause()}"
        )
    # The only ``None`` exit left for a request that HAS a sub. (The clause's
    # "failed to load" state cannot be reached from here: a usable local leg
    # would have been returned as the backend.)
    return (
        "this session has no cloud embedding model configured (set "
        "EMBEDDING_MODELS plus the matching provider key) and "
        f"{no_local_embed_clause()}, so there is no local fallback"
    )


def init_backend(
    backend_type: str,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> EmbeddingBackend:
    """Initialize and cache the embedding backend.

    Args:
        backend_type: 'cloud' or 'local'
        model: Model name (required for cloud, optional for local)
        api_base: Custom API base URL (cloud only)
        api_key: Custom API key (cloud only)

    Returns:
        Initialized backend instance.
    """
    global _backend

    if backend_type == "cloud":
        if not model:
            raise ValueError("model is required for cloud backend")
        _backend = CloudEmbeddingBackend(model, api_base=api_base, api_key=api_key)
    elif backend_type == "local":
        _backend = LocalEmbeddingBackend(model)
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")

    return _backend
