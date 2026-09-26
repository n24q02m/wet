"""The per-request embed/rerank resolvers must honour the disable-local flags.

Two backend-selection paths exist and they used to disagree. The startup path
made a deployment choice; the per-request path
(``embedder.resolve_embed_backend_for_request`` /
``reranker.resolve_rerank_backend_for_request``) fell through to the local
ONNX backend unconditionally, so on a deployment built WITHOUT the local
extras -- the http-slim image, which uninstalls ``fastretrieval`` and
``onnxruntime`` -- every indexing request with no cloud backend died on
``ModuleNotFoundError: No module named 'fastretrieval'`` raised from the lazy
import inside ``LocalEmbeddingBackend._get_model`` while ``config status``
claimed embedding was available.

The expected behaviour: the startup-resolved backend (the ``[models.embed]`` /
``[models.rerank]`` cell) wins when present; otherwise the request falls back
to the shared local ONNX leg -- unless the local leg is unavailable
(``DISABLE_LOCAL_EMBED`` / ``DISABLE_LOCAL_RERANK``, or an image built
without the ONNX extras), in which case it is ``None``: gracefully
unavailable, keyword-only. De-host there is no per-request credential
resolution any more: the cell is host-owned, not a per-sub secret.

``fastretrieval`` is installed in the dev venv, so these tests intercept the
import instead of relying on its absence: that both reproduces the slim image
and makes "the local leg was never reached" assertable. A test that only
checked the return value would stay green if the import happened first.
"""

from __future__ import annotations

import builtins
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hull_core.auth.context import AuthContext, reset_current_user, set_current_user

import wet_mcp.embedder as embedder_mod
import wet_mcp.reranker as reranker_mod


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Fresh backend singletons; no request identity; reset after."""
    monkeypatch.setattr(embedder_mod, "_backend", None)
    monkeypatch.setattr(embedder_mod, "_shared_local_backend", None)
    monkeypatch.setattr(reranker_mod, "_backend", None)
    monkeypatch.setattr(reranker_mod, "_shared_local_backend", None)
    token = set_current_user(AuthContext.local())
    yield
    reset_current_user(token)


@pytest.fixture
def as_user_a():
    """Resolve requests under a mode-3 identity (namespace ``user_a``)."""
    token = set_current_user(
        AuthContext(uid="a", namespace="user_a", mode="multi")
    )
    yield
    reset_current_user(token)


@pytest.fixture
def slim_image(monkeypatch):
    """Make ``fastretrieval`` unimportable, as the http-slim build leaves it.

    Returns the list of import names the code under test asked for, so a test
    can assert the local leg was never even entered.
    """
    real_import = builtins.__import__
    attempted: list[str] = []

    def _guarded(name, *args, **kwargs):
        if name == "fastretrieval" or name.startswith("fastretrieval."):
            attempted.append(name)
            raise ModuleNotFoundError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guarded)
    return attempted


@pytest.fixture
def local_embed_disabled(monkeypatch):
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "disable_local_embed", True)


@pytest.fixture
def local_rerank_disabled(monkeypatch):
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "disable_local_rerank", True)


def _cloud_embed_backend(model: str = "text-embedding-3-large"):
    """A CloudEmbeddingBackend over a stub client (cell-owned model id)."""
    from wet_mcp.embedder import CloudEmbeddingBackend

    client = MagicMock()
    client.cell.model = model
    client.embeddings = AsyncMock(return_value=[[0.1] * 4])
    return CloudEmbeddingBackend(client)


def _cloud_reranker(model: str = "cohere/rerank-v3.5"):
    """A CloudReranker over a stub client (cell-owned model id)."""
    from wet_mcp.reranker import CloudReranker

    client = MagicMock()
    client.cell.model = model
    client.rerank = AsyncMock(return_value=[])
    return CloudReranker(client)


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


class TestEmbedResolverHonoursDisableLocalEmbed:
    def test_no_backend_and_local_disabled_resolves_to_none(
        self, local_embed_disabled
    ):
        """The exit the slim image actually takes: gracefully unavailable."""
        from wet_mcp.embedder import resolve_embed_backend_for_request

        assert resolve_embed_backend_for_request() is None

    async def test_no_backend_and_local_disabled_never_imports_fastretrieval(
        self, local_embed_disabled, slim_image
    ):
        """End-to-end through the live dispatch helper, on a slim image.

        ``server._embed`` is what the search path calls. With the local leg
        still reachable this raises ModuleNotFoundError out of the lazy import;
        the fix has to make the resolver say "none" BEFORE anything touches
        ``fastretrieval``, which is why the import list is asserted too.
        """
        from wet_mcp import server

        assert await server._embed("hello", is_query=True) is None
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    async def test_no_backend_and_local_disabled_degrades_the_index_batch(
        self, local_embed_disabled, slim_image
    ):
        """The batch path the background indexer uses degrades the same way."""
        from wet_mcp import server

        assert await server._embed_batch(["a", "b"]) is None
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    def test_no_backend_with_local_enabled_still_returns_shared_local(self):
        """No regression: the local fallback is untouched when local is on."""
        from wet_mcp.embedder import LocalEmbeddingBackend

        backend = embedder_mod.resolve_embed_backend_for_request()
        assert isinstance(backend, LocalEmbeddingBackend)
        # It is the process-shared instance, not a fresh one per request.
        assert backend is embedder_mod.resolve_embed_backend_for_request()

    def test_cloud_backend_wins_over_the_flag(self, local_embed_disabled):
        """A startup-resolved cloud backend is unaffected: the flag only
        gates the LOCAL leg (the cell is host-owned, so there is no per-sub
        key for the flag to interact with any more)."""
        from wet_mcp.embedder import resolve_embed_backend_for_request

        backend = _cloud_embed_backend()
        embedder_mod._backend = backend

        assert resolve_embed_backend_for_request() is backend

    def test_startup_backend_wins_regardless_of_request_identity(
        self, local_embed_disabled, as_user_a
    ):
        """The startup backend is THE server backend: every caller gets it.

        De-host there is exactly one host-configured backend; a mode-3
        identity changes storage roots, not which embedding backend serves.
        """
        from wet_mcp.embedder import LocalEmbeddingBackend

        sentinel = LocalEmbeddingBackend()
        embedder_mod._backend = sentinel

        assert embedder_mod.resolve_embed_backend_for_request() is sentinel


# ---------------------------------------------------------------------------
# Reranking
# ---------------------------------------------------------------------------


class TestRerankResolverHonoursDisableLocalRerank:
    def test_no_backend_and_local_disabled_resolves_to_none(
        self, local_rerank_disabled
    ):
        from wet_mcp.reranker import resolve_rerank_backend_for_request

        assert resolve_rerank_backend_for_request() is None

    async def test_no_backend_and_local_disabled_never_imports_fastretrieval(
        self, local_rerank_disabled, slim_image
    ):
        """``_rerank_results`` must return the unranked order, importing nothing.

        ``LocalReranker.rerank`` swallows its own exceptions, so the broken
        local leg shows up here as a silent ``logger.warning`` per search
        rather than a traceback -- the import list is the only assertion that
        can tell "reranking was skipped" from "reranking failed quietly".
        """
        from wet_mcp import server

        results = [{"content": "doc-a"}, {"content": "doc-b"}]
        ranked = await server._rerank_results("q", results, 1)
        assert ranked == [{"content": "doc-a"}]
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    def test_no_backend_with_local_enabled_still_returns_shared_local(self):
        from wet_mcp.reranker import LocalReranker

        backend = reranker_mod.resolve_rerank_backend_for_request()
        assert isinstance(backend, LocalReranker)
        assert backend is reranker_mod.resolve_rerank_backend_for_request()

    def test_cloud_backend_wins_over_the_flag(self, local_rerank_disabled):
        from wet_mcp.reranker import resolve_rerank_backend_for_request

        backend = _cloud_reranker()
        reranker_mod._backend = backend

        assert resolve_rerank_backend_for_request() is backend


# ---------------------------------------------------------------------------
# config(action="status")
# ---------------------------------------------------------------------------


class TestConfigStatusReflectsPerRequestResolution:
    """Reported state must be served state.

    A status handler that read a DIFFERENT source than the resolvers would
    describe a backend the caller will never be served by.
    """

    async def test_embedding_reads_unavailable_when_the_request_has_no_backend(
        self, local_embed_disabled
    ):
        from wet_mcp.server import _handle_config_status

        status = await _handle_config_status()
        assert status["embedding"]["available"] is False
        assert status["embedding"]["backend"] is None

    async def test_embedding_names_the_resolved_cloud_backend(self):
        from wet_mcp.server import _handle_config_status

        embedder_mod._backend = _cloud_embed_backend(
            "jina_ai/jina-embeddings-v5-text-small"
        )

        status = await _handle_config_status()
        assert status["embedding"]["backend"] == "CloudEmbeddingBackend"
        assert status["embedding"]["available"] is True

    async def test_embedding_status_records_model_and_dimensions(self, monkeypatch):
        from wet_mcp import server
        from wet_mcp.server import _handle_config_status

        embedder_mod._backend = _cloud_embed_backend(
            "jina_ai/jina-embeddings-v5-text-small"
        )
        monkeypatch.setattr(server, "_embedding_dims", 768)

        status = await _handle_config_status()

        assert status["embedding"]["model"] == "jina_ai/jina-embeddings-v5-text-small"
        assert status["embedding"]["dims"] == 768

    async def test_reranker_reads_unavailable_when_the_request_has_no_backend(
        self, local_rerank_disabled
    ):
        from wet_mcp.server import _handle_config_status

        status = await _handle_config_status()
        assert status["reranker"]["available"] is False
        assert status["reranker"]["backend"] is None

    async def test_status_reports_the_resolved_backends(self):
        """Existing readers keep seeing the backends requests actually get."""
        from wet_mcp.server import _handle_config_status

        embedder_mod._backend = _cloud_embed_backend()
        reranker_mod._backend = _cloud_reranker()

        status = await _handle_config_status()
        assert status["embedding"]["backend"] == "CloudEmbeddingBackend"
        assert status["embedding"]["available"] is True
        assert status["reranker"]["backend"] == "CloudReranker"
        assert status["reranker"]["available"] is True

    async def test_status_says_why_embedding_is_unavailable(
        self, local_embed_disabled
    ):
        """ "available: false" alone reads as a bug report, not a config answer."""
        from wet_mcp.server import _handle_config_status

        reason = (await _handle_config_status())["embedding"]["unavailable_reason"]
        assert reason and "DISABLE_LOCAL_EMBED" in reason


# ---------------------------------------------------------------------------
# Search-time signal
# ---------------------------------------------------------------------------


class TestSearchSignalsKeywordOnlyRetrieval:
    """A keyword-only result set must say so.

    Without a vector the hybrid search silently drops to BM25. The reply is
    shaped identically either way, so the caller reads a thin result set as
    "semantic search found little" when semantic search never ran at all.
    """

    @staticmethod
    def _stub_docs_db(monkeypatch, captured: dict):
        from wet_mcp import server

        db = MagicMock()
        db.get_library.return_value = {"id": "lib1", "discovery_version": 10**6}
        db.get_best_version.return_value = {"id": "ver1", "chunk_count": 3}

        def _search(**kwargs):
            captured.update(kwargs)
            return [{"content": "c", "score": 0.9}]

        db.search.side_effect = _search
        monkeypatch.setattr(server, "_docs_db", db)
        return db

    @staticmethod
    def _stub_hyde(monkeypatch):
        """HyDE needs an LLM; these tests are about the retrieval signal."""
        monkeypatch.setattr(
            "wet_mcp.sources.search_strategies.generate_hyde_query",
            AsyncMock(return_value=None),
        )

    async def test_keyword_only_reply_names_the_missing_vector_leg(
        self, local_embed_disabled, slim_image, monkeypatch
    ):
        from wet_mcp import server

        captured: dict = {}
        self._stub_docs_db(monkeypatch, captured)
        self._stub_hyde(monkeypatch)

        payload = await server._search_cached_index("fastapi", "routing", None, 10)

        assert payload is not None
        assert captured["query_embedding"] is None
        assert payload["retrieval"] == "keyword_only"
        assert "DISABLE_LOCAL_EMBED" in payload["retrieval_notice"]
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    async def test_hybrid_reply_says_hybrid_and_carries_no_notice(self, monkeypatch):
        from wet_mcp import server

        class _FakeBackend:
            async def embed_single(self, text, dimensions=None):
                return [0.5] * 4

        embedder_mod._backend = _FakeBackend()

        captured: dict = {}
        self._stub_docs_db(monkeypatch, captured)
        self._stub_hyde(monkeypatch)

        payload = await server._search_cached_index("fastapi", "routing", None, 10)

        assert payload is not None
        assert captured["query_embedding"] == [0.5] * 4
        assert payload["retrieval"] == "hybrid"
        assert payload["retrieval_notice"] is None
