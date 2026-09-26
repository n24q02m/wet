"""Tests for src/wet_mcp/reranker.py — dual-backend reranking over hull cells.

Covers CloudReranker (async; the [models.rerank] cell's OpenAI-spec client),
LocalReranker (sync local ONNX cross-encoder), the per-request resolver, and
the init_reranker factory.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import wet_mcp.reranker as reranker_mod
from wet_mcp.reranker import (
    CloudReranker,
    LocalReranker,
    get_reranker,
    init_reranker,
    resolve_rerank_backend_for_request,
)


def _cell_client(model: str = "rerank-v4.0-pro") -> MagicMock:
    """A hull OpenAICompatClient stand-in for one [models.rerank] cell."""
    client = MagicMock()
    client.cell = SimpleNamespace(model=model)
    client.rerank = AsyncMock()
    return client


def _rerank_response(items: list[tuple[int, float]]) -> list[dict]:
    """A hull-client shaped rerank result (list of dicts)."""
    return [{"index": idx, "relevance_score": score} for idx, score in items]


@pytest.fixture(autouse=True)
def _reset_reranker_singletons():
    """Keep the module-level singletons from leaking between tests."""
    original_backend = reranker_mod._backend
    original_shared = reranker_mod._shared_local_backend
    reranker_mod._backend = None
    reranker_mod._shared_local_backend = None
    yield
    reranker_mod._backend = original_backend
    reranker_mod._shared_local_backend = original_shared


# -----------------------------------------------------------------------
# CloudReranker (async)
# -----------------------------------------------------------------------


class TestCloudReranker:
    async def test_rerank_success(self):
        """Reranking returns sorted (index, score) tuples."""
        client = _cell_client()
        client.rerank.return_value = _rerank_response([(0, 0.3), (1, 0.9), (2, 0.6)])
        reranker = CloudReranker(client)

        results = await reranker.rerank(
            "test query", ["doc a", "doc b", "doc c"], top_n=2
        )

        assert len(results) == 2
        assert results[0] == (1, 0.9)  # index of "doc b", sorted by score desc
        assert results[1] == (2, 0.6)

    async def test_rerank_empty_documents(self):
        """Empty documents return empty results without an API call."""
        client = _cell_client()
        reranker = CloudReranker(client)

        results = await reranker.rerank("query", [], top_n=5)

        assert results == []
        client.rerank.assert_not_awaited()

    async def test_rerank_api_error_returns_empty(self):
        """API errors return empty results (graceful fallback)."""
        client = _cell_client()
        client.rerank.side_effect = Exception("API error")
        reranker = CloudReranker(client)

        results = await reranker.rerank("query", ["doc1", "doc2"])

        assert results == []

    async def test_rerank_forwards_params(self):
        """Query, documents and top_n are forwarded to the cell client."""
        client = _cell_client()
        client.rerank.return_value = _rerank_response([(0, 0.9)])
        reranker = CloudReranker(client)

        await reranker.rerank("test query", ["doc a"], top_n=3)

        client.rerank.assert_awaited_once_with("test query", ["doc a"], top_n=3)

    async def test_check_available_success(self):
        """Returns True when the model is available."""
        client = _cell_client()
        client.rerank.return_value = _rerank_response([(0, 0.5)])

        assert await CloudReranker(client).check_available() is True

    async def test_check_available_failure(self):
        """Returns False when the model is not available."""
        client = _cell_client()
        client.rerank.side_effect = Exception("Not found")

        assert await CloudReranker(client).check_available() is False

    async def test_model_from_cell(self):
        reranker = CloudReranker(_cell_client("voyage-2.5-lite"))
        assert reranker.model == "voyage-2.5-lite"


class TestCloudRerankerApiKeyValidation:
    """check_available() distinguishes API key errors from other failures."""

    @pytest.mark.parametrize("error", ["401 Unauthorized", "403 Forbidden", "Invalid API key"])
    async def test_auth_errors_return_false(self, error):
        client = _cell_client()
        client.rerank.side_effect = Exception(error)

        assert await CloudReranker(client).check_available() is False

    async def test_non_auth_error_returns_false(self):
        client = _cell_client()
        client.rerank.side_effect = Exception("Model not found")

        assert await CloudReranker(client).check_available() is False

    async def test_success_returns_true(self):
        client = _cell_client()
        client.rerank.return_value = _rerank_response([(0, 0.9)])

        assert await CloudReranker(client).check_available() is True


# -----------------------------------------------------------------------
# LocalReranker (sync)
# -----------------------------------------------------------------------


class TestLocalReranker:
    def test_rerank_success(self):
        """Local cross-encoder reranking returns sorted results."""
        reranker = LocalReranker("test-model")

        mock_model = MagicMock()
        # Simulate P(yes) scores for 3 documents
        mock_model.rerank.return_value = iter([0.3, 0.9, 0.6])

        with patch.object(reranker, "_get_model", return_value=mock_model):
            results = reranker.rerank(
                "test query", ["doc a", "doc b", "doc c"], top_n=2
            )

        assert len(results) == 2
        assert results[0] == (1, 0.9)
        assert results[1] == (2, 0.6)

    def test_rerank_empty_documents(self):
        """Empty documents return empty results."""
        reranker = LocalReranker()
        results = reranker.rerank("query", [])
        assert results == []

    def test_rerank_passes_pairs(self):
        """Reranker receives (query, documents) pairs."""
        reranker = LocalReranker()

        mock_model = MagicMock()
        mock_model.rerank.return_value = iter([0.5, 0.8])

        with patch.object(reranker, "_get_model", return_value=mock_model):
            reranker.rerank("my query", ["doc1", "doc2"])

        assert mock_model.rerank.call_args[0][0] == "my query"
        assert mock_model.rerank.call_args[0][1] == ["doc1", "doc2"]

    def test_rerank_error_returns_empty(self):
        """Model errors return empty results (graceful fallback)."""
        reranker = LocalReranker()

        with patch.object(reranker, "_get_model", side_effect=Exception("ONNX error")):
            results = reranker.rerank("query", ["doc1"])

        assert results == []

    def test_check_available_success(self):
        """Returns True when model loads successfully."""
        reranker = LocalReranker()

        mock_model = MagicMock()
        mock_model.rerank.return_value = iter([0.5])

        with patch.object(reranker, "_get_model", return_value=mock_model):
            assert reranker.check_available() is True

    def test_check_available_failure(self):
        """Returns False when model fails to load."""
        reranker = LocalReranker()

        with patch.object(reranker, "_get_model", side_effect=Exception("Load error")):
            assert reranker.check_available() is False

    def test_check_available_import_error(self):
        """Returns False when fastretrieval is not installed."""
        reranker = LocalReranker()
        with patch.object(reranker, "_get_model", side_effect=ImportError("No module")):
            assert reranker.check_available() is False


# -----------------------------------------------------------------------
# Per-request resolution + factory
# -----------------------------------------------------------------------


class TestRerankerFactory:
    def test_init_cloud_reranker_uses_cell_client(self, monkeypatch):
        """init_reranker('cloud') wraps the [models.rerank] cell's client."""
        client = _cell_client("cell-rerank-model")
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured",
            lambda task, settings=None: task == "rerank",
        )
        monkeypatch.setattr(
            "wet_mcp.runtime.provider_client", lambda task, settings=None: client
        )

        reranker = init_reranker("cloud")

        assert isinstance(reranker, CloudReranker)
        assert reranker.model == "cell-rerank-model"
        assert get_reranker() is reranker

    def test_init_cloud_requires_configured_cell(self, monkeypatch):
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured", lambda task, settings=None: False
        )
        with pytest.raises(RuntimeError, match="not configured"):
            init_reranker("cloud")

    def test_init_local_reranker(self):
        reranker = init_reranker("local")
        assert isinstance(reranker, LocalReranker)
        assert get_reranker() is reranker

    def test_init_unknown_backend(self):
        with pytest.raises(ValueError, match="Unknown reranker"):
            init_reranker("unknown")

    def test_get_reranker_none_before_init(self):
        assert get_reranker() is None


class TestResolveRerankBackendForRequest:
    def test_startup_singleton_wins(self):
        """A startup-resolved reranker serves every request unchanged."""
        sentinel = LocalReranker("sentinel")
        reranker_mod._backend = sentinel

        assert resolve_rerank_backend_for_request() is sentinel

    def test_falls_back_to_shared_local(self, monkeypatch):
        """No singleton + local leg enabled -> process-shared local reranker."""
        backend = resolve_rerank_backend_for_request()
        assert isinstance(backend, LocalReranker)
        assert resolve_rerank_backend_for_request() is backend

    def test_none_when_rerank_disabled(self, monkeypatch):
        from wet_mcp.config import settings

        monkeypatch.setattr(settings, "rerank_enabled", False)
        assert resolve_rerank_backend_for_request() is None

    def test_none_when_local_leg_disabled(self, monkeypatch):
        from wet_mcp.config import settings

        monkeypatch.setattr(settings, "disable_local_rerank", True)
        assert resolve_rerank_backend_for_request() is None
