"""Tests for src/wet_mcp/embedder.py — dual-backend embedding over hull cells.

Covers CloudEmbeddingBackend (the [models.embed] cell's OpenAI-spec client),
batch splitting, retry logic, LocalEmbeddingBackend (local ONNX), the
per-request resolver, and the init_backend factory.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

import wet_mcp.embedder as embedder_mod
from wet_mcp.embedder import (
    CloudEmbeddingBackend,
    LocalEmbeddingBackend,
    _is_retryable,
    _is_unsupported_param,
    get_backend,
    init_backend,
    resolve_embed_backend_for_request,
)


def _cell_client(model: str = "text-embedding-3-small") -> MagicMock:
    """A hull OpenAICompatClient stand-in for one [models.embed] cell."""
    client = MagicMock()
    client.cell = SimpleNamespace(model=model)
    client.embeddings = AsyncMock()
    return client


@pytest.fixture(autouse=True)
def _reset_backend_singletons():
    """Keep the module-level singletons from leaking between tests."""
    original_backend = embedder_mod._backend
    original_shared = embedder_mod._shared_local_backend
    embedder_mod._backend = None
    embedder_mod._shared_local_backend = None
    yield
    embedder_mod._backend = original_backend
    embedder_mod._shared_local_backend = original_shared


# -----------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------


class TestHelpers:
    def test_is_retryable(self):
        assert _is_retryable(Exception("429 rate limit exceeded"))
        assert _is_retryable(Exception("503 service temporarily unavailable"))
        assert _is_retryable(Exception("connection timeout"))
        assert not _is_retryable(Exception("Invalid API key"))

    def test_is_unsupported_param(self):
        assert _is_unsupported_param(
            Exception("does not support parameters: dimensions"), "dimensions"
        )
        assert _is_unsupported_param(
            Exception("output_dimension is not supported for this model"), "dimensions"
        )
        assert not _is_unsupported_param(Exception("rate limit"), "dimensions")


# -----------------------------------------------------------------------
# CloudEmbeddingBackend: embed_texts (mocking the cell client)
# -----------------------------------------------------------------------


class TestCloudEmbeddingBackend:
    async def test_embed_texts_success(self):
        """Batch embedding returns correct vectors."""
        client = _cell_client()
        client.embeddings.return_value = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        backend = CloudEmbeddingBackend(client)

        vecs = await backend.embed_texts(["hello", "world"])

        assert vecs[0] == [0.1, 0.2, 0.3]
        assert vecs[1] == [0.4, 0.5, 0.6]

    async def test_embed_texts_empty_input(self):
        """Empty input returns empty list without API call."""
        backend = CloudEmbeddingBackend(_cell_client())
        vecs = await backend.embed_texts([])
        assert vecs == []

    async def test_embed_texts_with_dimensions(self):
        """The dimensions parameter is passed through to the client."""
        client = _cell_client()
        client.embeddings.return_value = [[0.1]]
        backend = CloudEmbeddingBackend(client)

        await backend.embed_texts(["test"], dimensions=256)

        client.embeddings.assert_awaited_once_with(["test"], dimensions=256)

    async def test_embed_texts_no_dimensions(self):
        """No dimensions kwarg when not specified."""
        client = _cell_client()
        client.embeddings.return_value = [[0.1]]
        backend = CloudEmbeddingBackend(client)

        await backend.embed_texts(["test"])

        client.embeddings.assert_awaited_once_with(["test"], dimensions=None)

    async def test_embed_texts_dimensions_fallback(self):
        """Falls back to local truncation when the provider rejects dimensions."""
        client = _cell_client()
        unsupported_err = Exception("output_dimension is not supported for this model")
        client.embeddings.side_effect = [unsupported_err, [[0.1] * 1024]]
        backend = CloudEmbeddingBackend(client)

        result = await backend.embed_texts(["test"], dimensions=768)

        assert len(result[0]) == 768

    async def test_embed_texts_local_truncation(self):
        """Truncates locally when the server returns more dims than requested."""
        client = _cell_client()
        client.embeddings.return_value = [[0.1] * 3072]
        backend = CloudEmbeddingBackend(client)

        result = await backend.embed_texts(["test"], dimensions=768)

        assert len(result[0]) == 768

    async def test_embed_texts_api_error(self):
        """Non-retryable API errors are raised to caller."""
        client = _cell_client()
        client.embeddings.side_effect = Exception("Invalid model")
        backend = CloudEmbeddingBackend(client)

        with pytest.raises(Exception, match="Invalid model"):
            await backend.embed_texts(["test"])

    async def test_embed_single_success(self):
        """Single text embedding returns one vector."""
        client = _cell_client()
        client.embeddings.return_value = [[0.1, 0.2, 0.3]]
        backend = CloudEmbeddingBackend(client)

        vec = await backend.embed_single("hello")

        assert vec == [0.1, 0.2, 0.3]

    async def test_model_from_cell(self):
        """The model id is owned by the cell (no provider prefix handling)."""
        backend = CloudEmbeddingBackend(_cell_client("gemini-embedding-001"))
        assert backend.model == "gemini-embedding-001"

    async def test_check_available(self):
        """Returns the cell model's dimension count when available."""
        client = _cell_client()
        client.embeddings.return_value = [[0.0] * 768]
        backend = CloudEmbeddingBackend(client)

        dims = await backend.check_available()

        assert dims == 768

    async def test_check_unavailable(self):
        """Returns 0 when the model is not available."""
        client = _cell_client()
        client.embeddings.side_effect = Exception("Invalid API key")
        backend = CloudEmbeddingBackend(client)

        assert await backend.check_available() == 0


# -----------------------------------------------------------------------
# CloudEmbeddingBackend: Batch splitting
# -----------------------------------------------------------------------


class TestBatchSplitting:
    async def test_splits_large_batch(self):
        """Texts exceeding MAX_BATCH_SIZE are split into sub-batches."""
        backend = CloudEmbeddingBackend(_cell_client())
        n = backend.MAX_BATCH_SIZE + 50  # 150 texts -> 2 batches

        async def mock_inner(texts, dimensions=None):
            return [[float(j)] for j in range(len(texts))]

        with patch.object(
            backend, "_embed_batch_inner", new=AsyncMock(side_effect=mock_inner)
        ):
            vecs = await backend.embed_texts([f"text_{i}" for i in range(n)])

        assert len(vecs) == n

    async def test_batch_call_count(self):
        """Correct number of API calls for split batches."""
        backend = CloudEmbeddingBackend(_cell_client())
        n = backend.MAX_BATCH_SIZE * 2 + 10  # 210 texts -> 3 batches

        async def mock_inner(texts, dimensions=None):
            return [[0.0] for _ in range(len(texts))]

        mock = AsyncMock(side_effect=mock_inner)
        with patch.object(backend, "_embed_batch_inner", new=mock):
            await backend.embed_texts([f"t{i}" for i in range(n)])

        assert mock.call_count == 3

    async def test_no_split_under_limit(self):
        """No splitting when under MAX_BATCH_SIZE."""
        backend = CloudEmbeddingBackend(_cell_client())
        n = backend.MAX_BATCH_SIZE

        async def mock_inner(texts, dimensions=None):
            return [[0.0] for _ in range(len(texts))]

        mock = AsyncMock(side_effect=mock_inner)
        with patch.object(backend, "_embed_batch_inner", new=mock):
            await backend.embed_texts([f"text_{i}" for i in range(n)])

        assert mock.call_count == 1


# -----------------------------------------------------------------------
# CloudEmbeddingBackend: Retry logic
# -----------------------------------------------------------------------


class TestRetryLogic:
    @patch("wet_mcp.embedder.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_rate_limit(self, mock_sleep):
        """Retries on rate limit errors with exponential backoff."""
        client = _cell_client()
        client.embeddings.side_effect = [Exception("429 rate limit exceeded"), [[0.1]]]
        backend = CloudEmbeddingBackend(client)

        result = await backend.embed_texts(["test"])

        assert result == [[0.1]]
        mock_sleep.assert_called_once_with(1.0)

    @patch("wet_mcp.embedder.asyncio.sleep", new_callable=AsyncMock)
    async def test_retries_on_server_error(self, mock_sleep):
        """Retries on 5xx server errors."""
        client = _cell_client()
        client.embeddings.side_effect = [
            Exception("503 service temporarily unavailable"),
            [[0.2]],
        ]
        backend = CloudEmbeddingBackend(client)

        result = await backend.embed_texts(["test"])

        assert result == [[0.2]]

    @patch("wet_mcp.embedder.asyncio.sleep", new_callable=AsyncMock)
    async def test_no_retry_on_non_retryable(self, mock_sleep):
        """Non-retryable errors fail immediately without retry."""
        client = _cell_client()
        client.embeddings.side_effect = Exception("Invalid API key")
        backend = CloudEmbeddingBackend(client)

        with pytest.raises(Exception, match="Invalid API key"):
            await backend.embed_texts(["test"])

        mock_sleep.assert_not_called()

    @patch("wet_mcp.embedder.asyncio.sleep", new_callable=AsyncMock)
    async def test_exponential_backoff(self, mock_sleep):
        """Retry delays use exponential backoff."""
        client = _cell_client()
        client.embeddings.side_effect = [
            Exception("429 rate limit"),
            Exception("429 rate limit"),
            [[0.1]],
        ]
        backend = CloudEmbeddingBackend(client)

        await backend.embed_texts(["test"])

        assert mock_sleep.call_args_list == [call(1.0), call(2.0)]

    @patch("wet_mcp.embedder.asyncio.sleep", new_callable=AsyncMock)
    async def test_max_retries_exhausted(self, mock_sleep):
        """Raises after all retries are exhausted."""
        client = _cell_client()
        client.embeddings.side_effect = Exception("429 rate limit")
        backend = CloudEmbeddingBackend(client)

        with pytest.raises(Exception, match="429 rate limit"):
            await backend.embed_texts(["test"])

        # 3 attempts total, 2 sleeps
        assert mock_sleep.call_count == 2


# -----------------------------------------------------------------------
# LocalEmbeddingBackend
# -----------------------------------------------------------------------


class TestLocalEmbeddingBackend:
    async def test_embed_texts_success(self):
        """Local ONNX embedding returns correct vectors."""
        import numpy as np

        backend = LocalEmbeddingBackend("test-model")
        mock_model = MagicMock()
        mock_model.embed.return_value = iter(
            [np.array([0.1, 0.2, 0.3]), np.array([0.4, 0.5, 0.6])]
        )

        with patch.object(backend, "_get_model", return_value=mock_model):
            vecs = await backend.embed_texts(["hello", "world"])

        assert len(vecs) == 2
        assert vecs[0] == pytest.approx([0.1, 0.2, 0.3])
        assert vecs[1] == pytest.approx([0.4, 0.5, 0.6])

    async def test_embed_texts_empty(self):
        """Empty input returns empty list."""
        backend = LocalEmbeddingBackend()
        assert await backend.embed_texts([]) == []

    async def test_embed_texts_with_mrl_truncation(self):
        """Dimensions parameter is passed to model.embed(dim=) for MRL."""
        import numpy as np

        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([np.array([0.1, 0.2, 0.3])])

        with patch.object(backend, "_get_model", return_value=mock_model):
            vecs = await backend.embed_texts(["test"], dimensions=3)

        mock_model.embed.assert_called_once_with(["test"], dim=3)
        assert len(vecs[0]) == 3

    async def test_embed_single(self):
        """embed_single delegates to embed_texts."""
        import numpy as np

        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([np.array([0.1, 0.2])])

        with patch.object(backend, "_get_model", return_value=mock_model):
            vec = await backend.embed_single("test")

        assert vec == pytest.approx([0.1, 0.2])

    async def test_check_available_success(self):
        """Returns dimensions when model loads successfully."""
        import numpy as np

        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([np.array([0.0] * 1024)])

        with patch.object(backend, "_get_model", return_value=mock_model):
            dims = await backend.check_available()

        assert dims == 1024

    async def test_check_available_failure(self):
        """Returns 0 when model fails to load."""
        backend = LocalEmbeddingBackend()
        with patch.object(backend, "_get_model", side_effect=Exception("ONNX load error")):
            assert await backend.check_available() == 0

    async def test_check_available_embed_exception(self):
        """Returns 0 when model.embed fails."""
        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.embed.side_effect = Exception("Runtime error")

        with patch.object(backend, "_get_model", return_value=mock_model):
            assert await backend.check_available() == 0

    async def test_check_available_empty_result(self):
        """Returns 0 when model.embed returns empty list."""
        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.embed.return_value = []

        with patch.object(backend, "_get_model", return_value=mock_model):
            assert await backend.check_available() == 0

    async def test_embed_single_query_success(self):
        """embed_single_query calls model.query_embed (asymmetric retrieval)."""
        import numpy as np

        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.query_embed.return_value = iter([np.array([0.1, 0.2])])

        with patch.object(backend, "_get_model", return_value=mock_model):
            vec = await backend.embed_single_query("query")

        assert vec == pytest.approx([0.1, 0.2])
        mock_model.query_embed.assert_called_once_with("query")

    async def test_embed_single_query_with_mrl(self):
        """embed_single_query passes dim parameter to model.query_embed."""
        import numpy as np

        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.query_embed.return_value = iter([np.array([0.1, 0.2])])

        with patch.object(backend, "_get_model", return_value=mock_model):
            vec = await backend.embed_single_query("query", dimensions=2)

        assert vec == pytest.approx([0.1, 0.2])
        mock_model.query_embed.assert_called_once_with("query", dim=2)

    async def test_get_model_caching(self):
        """_get_model instantiates TextEmbedding once and caches it."""
        backend = LocalEmbeddingBackend()
        with patch("fastretrieval.TextEmbedding") as mock_cls:
            mock_model = MagicMock()
            mock_cls.return_value = mock_model

            model1 = backend._get_model()
            assert model1 is mock_model
            mock_cls.assert_called_once_with(model_name=backend._model_name)

            model2 = backend._get_model()
            assert model2 is mock_model
            assert mock_cls.call_count == 1


# -----------------------------------------------------------------------
# Per-request resolution + factory
# -----------------------------------------------------------------------


class TestBackendFactory:
    async def test_init_cloud_backend_uses_cell_client(self, monkeypatch):
        """init_backend('cloud') wraps the [models.embed] cell's client."""
        client = _cell_client("voyage-4-lite")
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured",
            lambda task, settings=None: task == "embed",
        )
        monkeypatch.setattr(
            "wet_mcp.runtime.provider_client", lambda task, settings=None: client
        )

        backend = init_backend("cloud")

        assert isinstance(backend, CloudEmbeddingBackend)
        assert backend.model == "voyage-4-lite"
        assert get_backend() is backend

    async def test_init_cloud_ignores_model_arg(self, monkeypatch):
        """The cell owns the model; a caller-supplied id is ignored."""
        client = _cell_client("cell-model")
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured", lambda task, settings=None: True
        )
        monkeypatch.setattr(
            "wet_mcp.runtime.provider_client", lambda task, settings=None: client
        )

        backend = init_backend("cloud", "someone-elses-model")
        assert backend.model == "cell-model"

    async def test_init_cloud_requires_configured_cell(self, monkeypatch):
        """Unconfigured [models.embed] cell -> loud RuntimeError."""
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured", lambda task, settings=None: False
        )

        with pytest.raises(RuntimeError, match="not configured"):
            init_backend("cloud")

    async def test_init_local_backend(self):
        backend = init_backend("local")
        assert isinstance(backend, LocalEmbeddingBackend)
        assert get_backend() is backend

    async def test_init_unknown_backend(self):
        with pytest.raises(ValueError, match="Unknown backend"):
            init_backend("unknown")


class TestResolveEmbedBackendForRequest:
    async def test_startup_singleton_wins(self):
        """A startup-resolved backend serves every request unchanged."""
        sentinel = LocalEmbeddingBackend("sentinel")
        embedder_mod._backend = sentinel

        assert resolve_embed_backend_for_request() is sentinel

    async def test_falls_back_to_shared_local(self):
        """No singleton -> the process-shared local ONNX backend."""
        backend = resolve_embed_backend_for_request()
        assert isinstance(backend, LocalEmbeddingBackend)
        # Same shared instance on the next request (no per-request rebuild).
        assert resolve_embed_backend_for_request() is backend

    async def test_unavailable_when_local_leg_disabled(self, monkeypatch):
        from wet_mcp.config import settings

        monkeypatch.setattr(settings, "disable_local_embed", True)
        assert resolve_embed_backend_for_request() is None


# -----------------------------------------------------------------------
# check_available: API key validation messages
# -----------------------------------------------------------------------


class TestCheckAvailableApiKeyValidation:
    """check_available() distinguishes API key errors from other failures."""

    @pytest.mark.parametrize(
        "error", ["401 Unauthorized", "403 Forbidden", "Invalid API key provided", "Unauthorized access"]
    )
    async def test_auth_errors_return_zero(self, error):
        client = _cell_client()
        client.embeddings.side_effect = Exception(error)

        assert await CloudEmbeddingBackend(client).check_available() == 0

    async def test_non_auth_error_returns_zero(self):
        """Non-auth errors (e.g. model not found) also return 0."""
        client = _cell_client()
        client.embeddings.side_effect = Exception("Model not found")

        assert await CloudEmbeddingBackend(client).check_available() == 0

    async def test_success_returns_dims(self):
        client = _cell_client()
        client.embeddings.return_value = [[0.1, 0.2, 0.3]]

        assert await CloudEmbeddingBackend(client).check_available() == 3

    async def test_empty_embeddings_returns_zero(self):
        client = _cell_client()
        client.embeddings.return_value = []

        assert await CloudEmbeddingBackend(client).check_available() == 0


# -----------------------------------------------------------------------
# Shared local backend
# -----------------------------------------------------------------------


class TestSharedLocalBackend:
    def test_shared_local_embed_backend_lazy(self):
        """_shared_local_embed_backend lazily creates and caches instance."""
        from wet_mcp.embedder import _shared_local_embed_backend

        with patch("wet_mcp.embedder.LocalEmbeddingBackend") as mock_cls:
            instance = MagicMock()
            mock_cls.return_value = instance

            res1 = _shared_local_embed_backend()
            assert res1 is instance
            mock_cls.assert_called_once()

            res2 = _shared_local_embed_backend()
            assert res2 is instance
            assert mock_cls.call_count == 1
