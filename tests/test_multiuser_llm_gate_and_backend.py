"""LLM/embed/rerank availability gates + per-request backend resolution (de-host).

The hosted per-sub credential buckets are gone: providers are host-owned
per-task cells in ``~/.wet/config.toml``. What must NOT regress:

1. LLM availability gating reads the ``[models.chat]`` cell (not env vars, not
   per-sub buckets) — an unconfigured cell means LLM features stay off.
2. The per-request resolvers (:func:`resolve_embed_backend_for_request`,
   :func:`resolve_rerank_backend_for_request`) hand out the startup singleton
   or the process-shared LOCAL backend without ever REBINDING the singleton,
   and return ``None`` (gracefully unavailable) when the local leg is disabled.
3. ``server._embed`` / ``server._rerank_results`` dispatch through the resolvers
   with the right sync/async protocol per backend kind.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import wet_mcp.embedder as embedder_mod
import wet_mcp.reranker as reranker_mod
from wet_mcp import server as srv
from wet_mcp.embedder import (
    CloudEmbeddingBackend,
    LocalEmbeddingBackend,
    init_backend,
    resolve_embed_backend_for_request,
)
from wet_mcp.llm import has_llm_provider
from wet_mcp.reranker import (
    CloudReranker,
    LocalReranker,
    init_reranker,
    resolve_rerank_backend_for_request,
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Keep the module-level backend singletons from leaking between tests."""
    saved = (
        embedder_mod._backend,
        embedder_mod._shared_local_backend,
        reranker_mod._backend,
        reranker_mod._shared_local_backend,
    )
    embedder_mod._backend = None
    embedder_mod._shared_local_backend = None
    reranker_mod._backend = None
    reranker_mod._shared_local_backend = None
    yield
    (
        embedder_mod._backend,
        embedder_mod._shared_local_backend,
        reranker_mod._backend,
        reranker_mod._shared_local_backend,
    ) = saved


# ---------------------------------------------------------------------------
# 1. LLM availability gate reads the chat cell
# ---------------------------------------------------------------------------


class TestLlmGate:
    def test_gate_true_when_chat_cell_configured(self, monkeypatch):
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured",
            lambda task, settings=None: task == "chat",
        )
        assert has_llm_provider() is True

    def test_gate_false_when_chat_cell_unconfigured(self, monkeypatch):
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured", lambda task, settings=None: False
        )
        assert has_llm_provider() is False

    def test_gate_ignores_embed_and_rerank_cells(self, monkeypatch):
        """Only [models.chat] turns LLM features on."""
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured",
            lambda task, settings=None: task in ("embed", "rerank"),
        )
        assert has_llm_provider() is False

    def test_gate_never_touches_process_env(self, monkeypatch):
        """Env keys must not flip the gate: cells are the only source."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-something")
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured", lambda task, settings=None: False
        )
        assert has_llm_provider() is False


# ---------------------------------------------------------------------------
# 2. Cloud cell factories
# ---------------------------------------------------------------------------


def _cell_client(model: str) -> MagicMock:
    client = MagicMock()
    client.cell = SimpleNamespace(model=model)
    return client


class TestCloudCellFactory:
    def test_embed_factory_wraps_cell_client(self, monkeypatch):
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

    def test_rerank_factory_wraps_cell_client(self, monkeypatch):
        client = _cell_client("voyage-2.5-lite")
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured",
            lambda task, settings=None: task == "rerank",
        )
        monkeypatch.setattr(
            "wet_mcp.runtime.provider_client", lambda task, settings=None: client
        )

        reranker = init_reranker("cloud")

        assert isinstance(reranker, CloudReranker)
        assert reranker.model == "voyage-2.5-lite"

    def test_unconfigured_cells_raise_instead_of_silent_local(self, monkeypatch):
        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured", lambda task, settings=None: False
        )
        with pytest.raises(RuntimeError, match="embed.*not configured|not configured"):
            init_backend("cloud")
        with pytest.raises(RuntimeError, match="not configured"):
            init_reranker("cloud")


# ---------------------------------------------------------------------------
# 3. Per-request resolution without singleton rebinding
# ---------------------------------------------------------------------------


class TestPerRequestEmbedBackend:
    def test_startup_singleton_served_unchanged(self):
        sentinel = LocalEmbeddingBackend("sentinel")
        embedder_mod._backend = sentinel

        assert resolve_embed_backend_for_request() is sentinel
        assert embedder_mod._backend is sentinel

    def test_no_cloud_cell_falls_back_to_shared_local(self):
        """No startup backend -> the shared local ONNX backend, once."""
        backend = resolve_embed_backend_for_request()

        assert isinstance(backend, LocalEmbeddingBackend)
        assert resolve_embed_backend_for_request() is backend
        # The resolver never REBINDS the startup singleton.
        assert embedder_mod._backend is None

    def test_disabled_local_leg_returns_none(self, monkeypatch):
        from wet_mcp.config import settings

        monkeypatch.setattr(settings, "disable_local_embed", True)
        assert resolve_embed_backend_for_request() is None


class TestPerRequestRerankBackend:
    def test_startup_singleton_served_unchanged(self):
        sentinel = LocalReranker("sentinel")
        reranker_mod._backend = sentinel

        assert resolve_rerank_backend_for_request() is sentinel
        assert reranker_mod._backend is sentinel

    def test_no_cloud_cell_falls_back_to_shared_local(self):
        backend = resolve_rerank_backend_for_request()

        assert isinstance(backend, LocalReranker)
        assert resolve_rerank_backend_for_request() is backend
        assert reranker_mod._backend is None

    def test_disabled_rerank_returns_none(self, monkeypatch):
        from wet_mcp.config import settings

        monkeypatch.setattr(settings, "rerank_enabled", False)
        assert resolve_rerank_backend_for_request() is None


# ---------------------------------------------------------------------------
# 4. Server dispatch wiring (_embed / _rerank_results)
# ---------------------------------------------------------------------------


class TestEmbedDispatchWiring:
    async def test_embed_uses_request_backend(self, monkeypatch):
        backend = MagicMock()
        backend.embed_single = AsyncMock(return_value=[0.1, 0.2])
        monkeypatch.setattr(
            "wet_mcp.embedder.resolve_embed_backend_for_request", lambda: backend
        )

        result = await srv._embed("hello")

        assert result == [0.1, 0.2]
        backend.embed_single.assert_awaited_once_with("hello", srv._embedding_dims)

    async def test_embed_without_backend_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "wet_mcp.embedder.resolve_embed_backend_for_request", lambda: None
        )
        assert await srv._embed("hello") is None


class TestRerankDispatchWiring:
    @staticmethod
    def _results(n: int) -> list[dict]:
        return [
            {"url": f"https://example.com/{i}", "content": f"doc {i}"} for i in range(n)
        ]

    async def test_cloud_reranker_is_awaited_not_threaded(self, monkeypatch):
        """The cloud leg is async: _rerank_results must await it directly."""
        reranker = MagicMock(spec=CloudReranker)
        reranker.rerank = AsyncMock(return_value=[(1, 0.9), (0, 0.1)])
        monkeypatch.setattr(
            "wet_mcp.reranker.resolve_rerank_backend_for_request", lambda: reranker
        )

        results = self._results(3)
        reranked = await srv._rerank_results("query", results, top_n=2)

        reranker.rerank.assert_awaited_once()
        assert [r["url"] for r in reranked] == [
            "https://example.com/1",
            "https://example.com/0",
        ]
        assert reranked[0]["score"] == 0.9

    async def test_local_reranker_runs_in_thread(self, monkeypatch):
        """The local leg is sync: it must go through asyncio.to_thread."""
        reranker = MagicMock(spec=LocalReranker)
        # Return a plain (non-awaitable) ranking — a threadpool result.
        reranker.rerank.return_value = [(2, 0.8), (0, 0.4)]
        monkeypatch.setattr(
            "wet_mcp.reranker.resolve_rerank_backend_for_request", lambda: reranker
        )

        reranked = await srv._rerank_results("query", self._results(3), top_n=2)

        assert [r["url"] for r in reranked] == [
            "https://example.com/2",
            "https://example.com/0",
        ]

    async def test_semantic_order_applied_when_candidates_equal_top_n(self, monkeypatch):
        """Candidates == top_n is exactly the boundary worth reranking on."""
        reranker = MagicMock(spec=LocalReranker)
        reranker.rerank.return_value = [(1, 0.95), (0, 0.10)]
        monkeypatch.setattr(
            "wet_mcp.reranker.resolve_rerank_backend_for_request", lambda: reranker
        )

        results = self._results(2)
        reranked = await srv._rerank_results("query", results, top_n=2)

        assert [r["url"] for r in reranked] == [
            "https://example.com/1",
            "https://example.com/0",
        ]

    async def test_broken_reranker_falls_back_to_source_order(self, monkeypatch):
        """A configured but failing reranker degrades to unranked order."""
        reranker = MagicMock(spec=LocalReranker)
        reranker.rerank.side_effect = RuntimeError("boom")
        monkeypatch.setattr(
            "wet_mcp.reranker.resolve_rerank_backend_for_request", lambda: reranker
        )

        results = self._results(3)
        reranked = await srv._rerank_results("query", results, top_n=2)

        assert [r["url"] for r in reranked] == [
            "https://example.com/0",
            "https://example.com/1",
        ]

    async def test_no_reranker_keeps_source_order(self, monkeypatch):
        monkeypatch.setattr(
            "wet_mcp.reranker.resolve_rerank_backend_for_request", lambda: None
        )

        results = self._results(3)
        reranked = await srv._rerank_results("query", results, top_n=2)

        assert [r["url"] for r in reranked][:2] == [
            "https://example.com/0",
            "https://example.com/1",
        ]
