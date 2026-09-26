"""Dual-backend reranking: Cloud ([models.rerank] provider cell) + fastretrieval (local ONNX).

Supports two backends:
- **cloud**: Cloud reranking via the ``[models.rerank]`` cell (``base_url +
  api_key + model``, OpenAI-spec /rerank, ``~/.wet/config.toml``) served by the
  shared hull-core provider client (:mod:`wet_mcp.runtime`).
- **local**: Local ONNX cross-encoder via fastretrieval's configured model.
  No API keys needed, ~0.57GB model download on first use.

Reranker takes search results and re-scores them with a cross-encoder
for better precision. Pipeline: retrieve top-30 -> rerank -> return top-N.
"""

from __future__ import annotations

from typing import Protocol

from loguru import logger

# ---------------------------------------------------------------------------
# Backend Protocol
# ---------------------------------------------------------------------------
_AUTH_ERROR_PATTERNS = ("401", "403", "invalid", "unauthorized", "api key")


class RerankerBackend(Protocol):
    """Protocol for reranker backends.

    Note the asymmetry kept from the dual-backend design: the local ONNX leg
    is sync (CPU-bound; callers run it via ``asyncio.to_thread``), while the
    cloud leg is async (it awaits the shared OpenAI-spec HTTP client).
    """

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 10,
    ) -> list[tuple[int, float]]:
        """Rerank documents against a query.

        Args:
            query: Search query text.
            documents: List of document texts to rerank.
            top_n: Return top N results.

        Returns:
            List of (original_index, score) tuples, sorted by score descending.
        """
        ...

    def check_available(self) -> bool:
        """Check if the reranker backend is available."""
        ...


# ---------------------------------------------------------------------------
# Cloud Backend ([models.rerank] provider cell)
# ---------------------------------------------------------------------------


class CloudReranker:
    """Cloud reranking via the ``[models.rerank]`` provider cell.

    Wraps exactly one :class:`~hull_core.providers.openai_spec.
    OpenAICompatClient` built from the cell; the cell owns base_url, api_key,
    and model. Unlike :class:`LocalReranker`, the methods here are async --
    the hull-core client is an async HTTP client, so there is nothing to push
    to a worker thread.
    """

    def __init__(self, client) -> None:
        self._client = client

    @property
    def model(self) -> str:
        """The cell-owned rerank model id (for logs and diagnostics)."""
        return self._client.cell.model

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 10,
    ) -> list[tuple[int, float]]:
        """Rerank using the cell's ``/rerank`` endpoint."""
        if not documents:
            return []

        try:
            results = await self._client.rerank(query, documents, top_n=top_n)
            mapped = [
                (int(r["index"]), float(r["relevance_score"])) for r in results
            ]

            # Sort by score descending
            mapped.sort(key=lambda x: x[1], reverse=True)
            return mapped[:top_n]

        except Exception as e:
            logger.warning(f"Cloud reranking failed: {e}")
            return []

    async def check_available(self) -> bool:
        """Check if the cell's reranking model is available.

        Distinguishes between invalid API keys (warning) and other
        failures (debug) so users know when their key is wrong.
        """
        try:
            results = await self._client.rerank("ping", ["doc"], top_n=1)
            return bool(results)
        except Exception as e:
            msg = str(e).lower()
            if any(p in msg for p in _AUTH_ERROR_PATTERNS):
                logger.warning(
                    f"API key invalid for reranker {self.model}: {e}. "
                    "Check the api_key of the [models.rerank] cell in "
                    "~/.wet/config.toml."
                )
            else:
                logger.debug(f"Cloud reranker {self.model} not available: {e}")
            return False


# ---------------------------------------------------------------------------
# fastretrieval Backend (local ONNX)
# ---------------------------------------------------------------------------


class LocalReranker:
    """Local ONNX cross-encoder reranking via fastretrieval's configured model.

    Uses causal LM yes/no logit scoring with chat template.
    Scores are P(yes) in [0, 1].
    Model is downloaded on first use (~0.57GB).
    """

    # YesNo variant: ~598 MB at inference vs ~12 GB for the full-vocab build,
    # The reference YesNo variant is small and keeps scores batch-invariant.
    DEFAULT_MODEL = "n24q02m/Qwen3-Reranker-0.6B-ONNX-YesNo"

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model = None

    def _get_model(self):
        """Lazy-load the reranking model.

        On first call, downloads the ONNX model (~570 MB) from HuggingFace
        if not already cached. Logs a warning so users know why startup is slow.
        """
        if self._model is None:
            from fastretrieval import TextCrossEncoder

            logger.warning(
                f"Loading local reranker model: {self._model_name} "
                "(~570 MB download on first run). "
                "Set the [models.rerank] cell in ~/.wet/config.toml "
                "to use cloud reranking instead."
            )
            self._model = TextCrossEncoder(model_name=self._model_name)
            logger.info("Local reranker model loaded")
        return self._model

    def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 10,
    ) -> list[tuple[int, float]]:
        """Rerank documents using local cross-encoder."""
        if not documents:
            return []

        try:
            model = self._get_model()
            scores = list(model.rerank(query, documents))

            # Build (index, score) pairs
            results = list(enumerate(scores))
            # Sort by score descending
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_n]

        except Exception as e:
            logger.warning(f"Local reranking failed: {e}")
            return []

    def check_available(self) -> bool:
        """Check if fastretrieval reranker is available."""
        try:
            model = self._get_model()
            scores = list(model.rerank("test", ["test document"]))
            return len(scores) > 0
        except Exception as e:
            logger.debug(f"Local reranker not available: {e}")
            return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_backend: RerankerBackend | None = None

# Shared local ONNX reranker for all requests without a startup singleton.
# Local inference is stateless and key-free, so one instance is safely shared.
# Lazy so deployments that never fall back to the local leg never download the
# model.
_shared_local_backend: LocalReranker | None = None


def get_reranker() -> RerankerBackend | None:
    """Get the current reranker backend singleton (startup-resolved)."""
    return _backend


def clear_reranker() -> None:
    """Clear the startup singleton after backend validation fails."""
    global _backend
    _backend = None


def _shared_local_reranker() -> LocalReranker:
    """Return the process-shared local ONNX reranker backend (lazy)."""
    global _shared_local_backend
    if _shared_local_backend is None:
        _shared_local_backend = LocalReranker()
    return _shared_local_backend


def resolve_rerank_backend_for_request() -> RerankerBackend | None:
    """Resolve the reranker backend for the CURRENT request.

    The startup singleton wins (cloud via the ``[models.rerank]`` cell, or
    local). Without one, the process-shared local ONNX reranker serves every
    request -- unless the local leg is unavailable (``DISABLE_LOCAL_RERANK``,
    or an image built without the ONNX extras), in which case reranking is
    ``None``: gracefully unavailable, source order kept.

    That ``None`` matters more than the traceback suggests:
    :meth:`LocalReranker.rerank` swallows its own load failure and returns
    ``[]``, so a local reranker on an image built without the ONNX extras
    degrades every search to unranked order behind one log line, quietly,
    forever. Returning ``None`` says the same thing out loud.

    There is no per-request credential resolution any more: providers are
    host-configured cells, not per-sub secrets.
    """
    reranker = get_reranker()
    if reranker is not None:
        return reranker

    from wet_mcp.config import settings

    if not settings.rerank_enabled or not settings.local_rerank_available():
        return None
    return _shared_local_reranker()


def init_reranker(backend_type: str, model: str | None = None) -> RerankerBackend:
    """Initialize and cache the reranker backend.

    Args:
        backend_type: 'cloud' or 'local'.
        model: Local ONNX model override ('local' only). Ignored for 'cloud':
            the [models.rerank] cell owns the model.

    Returns:
        Initialized reranker backend instance.
    """
    global _backend

    if backend_type == "cloud":
        from wet_mcp.runtime import cell_configured, provider_client

        if not cell_configured("rerank"):
            raise RuntimeError(
                "cloud reranking requested but the [models.rerank] cell is not "
                "configured: set base_url + api_key + model in ~/.wet/config.toml"
            )
        _backend = CloudReranker(provider_client("rerank"))
    elif backend_type == "local":
        _backend = LocalReranker(model)
    else:
        raise ValueError(f"Unknown reranker backend type: {backend_type}")

    return _backend
