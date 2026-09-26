"""The local ONNX leg must be resolved from the IMAGE, not only from a flag.

The http-slim build uninstalls ``fastretrieval`` and ``onnxruntime`` (see
``Dockerfile``), so on that image the local embed/rerank leg does not exist --
whatever the configuration says. Every resolver deciding the question from
``DISABLE_LOCAL_EMBED`` / ``DISABLE_LOCAL_RERANK`` alone makes a slim
deployment correct only for as long as somebody remembers to set those vars.
Forget one, and the first index attempt dies inside the lazy import in
``LocalEmbeddingBackend._get_model``. The pre-de-host deployment recorded
exactly that::

    fastapi:python  pending  0 chunks  failed
        ModuleNotFoundError: No module named 'fastretrieval'

-- a hard failure with zero chunks, where the same request had a perfectly good
keyword-only degrade available to it.

These tests pin the fix at four levels: the per-request resolvers, the reason
string a caller is told, the durable record the background indexer leaves in
``versions.index_error``, and the startup path that used to install a backend
it had already proved could not load.

Both ``fastretrieval`` and ``onnxruntime`` ARE installed in the dev venv, so the
slim container cannot be reproduced by simply not having them. The
``slim_image`` fixture simulates both packages on two channels at once:
``find_spec`` answers "absent" (what the fix is supposed to consult) and
``__import__`` raises (what the old code hit). Recording every attempted import
is what lets these tests assert the local leg was never entered, rather than
merely that the return value looked right.
"""

from __future__ import annotations

import builtins
import importlib.util
from unittest.mock import AsyncMock, Mock

import pytest
from hull_core.auth.context import AuthContext, reset_current_user, set_current_user

from wet_mcp import server
from wet_mcp.db import INDEX_STATE_DONE, INDEX_STATE_RUNNING, DocsDB

# Captured at collection time, BEFORE conftest's autouse lifespan stub
# replaces both factories with MagicMocks that report a healthy backend and never
# touch the module singleton. Under that stub the startup tests below pass on
# unfixed code, asserting nothing. Its docstring says as much: "Tests that
# exercise these init factories patch the same targets themselves."
from wet_mcp.embedder import init_backend as _REAL_INIT_BACKEND
from wet_mcp.reranker import init_reranker as _REAL_INIT_RERANKER

DOCS_URL = "https://example.test/alpha"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Both disable-local flags OFF, and a clean identity.

    The flags being off is the whole point: this module covers the deployment
    that never set them and is nonetheless running an image without the local
    extras.
    """
    from wet_mcp import embedder, reranker
    from wet_mcp.config import settings

    monkeypatch.setattr(settings, "disable_local_embed", False)
    monkeypatch.setattr(settings, "disable_local_rerank", False)
    # Process-wide singletons; a leftover from another module would make these
    # assertions pass or fail for the wrong reason.
    monkeypatch.setattr(embedder, "_shared_local_backend", None)
    monkeypatch.setattr(reranker, "_shared_local_backend", None)
    monkeypatch.setattr(embedder, "_backend", None)
    monkeypatch.setattr(reranker, "_backend", None)
    token = set_current_user(AuthContext.local())
    yield
    reset_current_user(token)


@pytest.fixture
def slim_image(monkeypatch):
    """Make both local ONNX packages absent as the slim build leaves them.

    Returns the list of import names the code under test asked for; an empty
    list is the assertion that the local leg was never entered at all.
    """
    real_import = builtins.__import__
    real_find_spec = importlib.util.find_spec
    attempted: list[str] = []
    missing = ("fastretrieval", "onnxruntime")

    def _guarded_import(name, *args, **kwargs):
        if any(
            name == package or name.startswith(f"{package}.") for package in missing
        ):
            attempted.append(name)
            raise ModuleNotFoundError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    def _guarded_find_spec(name, *args, **kwargs):
        if any(
            name == package or name.startswith(f"{package}.") for package in missing
        ):
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)
    monkeypatch.setattr(importlib.util, "find_spec", _guarded_find_spec)
    return attempted


# ---------------------------------------------------------------------------
# Per-request resolution
# ---------------------------------------------------------------------------


class TestEmbedResolutionOnASlimImage:
    def test_absent_local_extras_resolve_to_none_without_any_flag(self, slim_image):
        """The flag is unset; the package is gone. That is still 'unavailable'."""
        from wet_mcp.embedder import resolve_embed_backend_for_request

        assert resolve_embed_backend_for_request() is None
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    async def test_index_batch_degrades_instead_of_raising(self, slim_image):
        """``_embed_batch`` is what the background indexer calls.

        On unfixed code this raises ``ModuleNotFoundError`` straight through
        ``_embed_batch``'s permanent-error branch, which is how the failure
        reached the index record as the version's ``index_error``.
        """
        from wet_mcp import server

        assert await server._embed_batch(["a", "b"]) is None
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    async def test_query_embed_degrades_instead_of_raising(self, slim_image):
        from wet_mcp import server

        assert await server._embed("hello", is_query=True) is None
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    def test_reason_names_the_missing_package_not_a_flag_nobody_set(self, slim_image):
        """A reason must be true. ``DISABLE_LOCAL_EMBED`` is not set here.

        Telling an operator to look at a flag they never touched sends them
        after the wrong thing; the actionable fact is that the image has no
        local extras, so the deployment needs a cloud cell.
        """
        from wet_mcp.embedder import embedding_unavailable_reason

        reason = embedding_unavailable_reason()
        assert reason is not None
        assert "fastretrieval" in reason
        assert "onnxruntime" in reason
        # Named as a property of the build, so the reader looks for a cloud
        # cell rather than a flag to unset.
        assert "slim" in reason
        assert "DISABLE_LOCAL_EMBED" not in reason

    def test_reason_still_names_the_flag_when_the_flag_is_what_did_it(
        self, monkeypatch
    ):
        """Control for the branch above: the flag wording must not be lost."""
        from wet_mcp.config import settings
        from wet_mcp.embedder import embedding_unavailable_reason

        monkeypatch.setattr(settings, "disable_local_embed", True)

        reason = embedding_unavailable_reason()
        assert reason is not None
        assert "DISABLE_LOCAL_EMBED" in reason
        assert "fastretrieval" not in reason

    def test_installed_local_extras_are_still_used(self):
        """No regression: a full image with the flag off keeps its local leg."""
        from wet_mcp import embedder
        from wet_mcp.embedder import LocalEmbeddingBackend

        backend = embedder.resolve_embed_backend_for_request()
        assert isinstance(backend, LocalEmbeddingBackend)
        assert backend is embedder.resolve_embed_backend_for_request()


class TestRerankResolutionOnASlimImage:
    def test_absent_local_extras_resolve_to_none_without_any_flag(self, slim_image):
        from wet_mcp.reranker import resolve_rerank_backend_for_request

        assert resolve_rerank_backend_for_request() is None
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    async def test_rerank_returns_unranked_order_touching_nothing(self, slim_image):
        """``LocalReranker.rerank`` swallows its own load failure and returns
        ``[]``, so the broken leg is invisible in the result. The import list is
        the only thing that can tell "skipped" from "failed quietly"."""
        from wet_mcp import server

        results = [{"content": "doc-a"}, {"content": "doc-b"}]
        assert await server._rerank_results("q", results, 1) == [
            {"content": "doc-a"}
        ]
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    def test_installed_local_extras_are_still_used(self):
        from wet_mcp import reranker
        from wet_mcp.reranker import LocalReranker

        assert isinstance(reranker.resolve_rerank_backend_for_request(), LocalReranker)


# ---------------------------------------------------------------------------
# The durable record -- the index row from the issue
# ---------------------------------------------------------------------------


@pytest.fixture
def docs_db(tmp_path, monkeypatch):
    """A real store, so the outcome is asserted where an operator reads it."""
    db = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    monkeypatch.setattr(server, "_docs_db", db)
    yield db
    db.close()


@pytest.fixture
def no_searxng(monkeypatch):
    """Keep the indexer's alternate-source leg off the network."""
    monkeypatch.setattr(
        server,
        "ensure_searxng",
        AsyncMock(side_effect=RuntimeError("searxng disabled in tests")),
    )


def _fresh_version(db: DocsDB):
    """A never-indexed version, as ``fastapi:python`` was in prod."""
    lib_id = db.upsert_library(name="alpha", docs_url=DOCS_URL)
    ver_id = db.upsert_version(library_id=lib_id, version="latest", docs_url=DOCS_URL)
    db.set_index_state(ver_id, INDEX_STATE_RUNNING)
    return lib_id, ver_id


def _chunks(n: int):
    return [
        {
            "url": f"{DOCS_URL}/page",
            "title": "T",
            "chunk_index": i,
            "content": f"chunk body number {i}",
            "heading_path": "T",
        }
        for i in range(n)
    ]


class TestBackgroundIndexerOnASlimImage:
    async def test_it_stores_keyword_only_chunks_and_records_why(
        self, docs_db, no_searxng, slim_image, monkeypatch
    ):
        """The exact prod row, inverted.

        Before: ``state=failed``, ``error='ModuleNotFoundError: No module named
        'fastretrieval''``, ``chunk_count=0`` -- the library unservable forever.
        After: the chunks land keyword-searchable and the version says, where
        ``config(action="status")`` reads it, that it holds no vectors and why.
        Storing them silently would trade a loud failure for a quiet one, which
        is the outcome this test exists to forbid.
        """
        lib_id, ver_id = _fresh_version(docs_db)
        monkeypatch.setattr(
            server, "_fetch_and_chunk_docs", AsyncMock(return_value=(_chunks(2), 3))
        )

        await server._background_index_and_search(
            library="alpha",
            lib_key="alpha",
            language=None,
            docs_url=DOCS_URL,
            repo_url="",
            query="how to install",
            version=None,
            lib_id=lib_id,
            ver_id=ver_id,
        )

        state = docs_db.get_index_state(ver_id)
        assert state is not None, "the attempt left no record at all"
        assert state["state"] == INDEX_STATE_DONE
        assert state["chunk_count"] == 2, "the keyword-searchable chunks were lost"
        assert docs_db.search("chunk body", library_name="alpha")

        error = state["error"] or ""
        assert "ModuleNotFoundError" not in error
        assert "fastretrieval" in error
        assert "keyword" in error.lower(), (
            "the record must say the version holds no vectors, not just that "
            f"something was off: {error!r}"
        )
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    async def test_a_fully_embedded_index_records_no_complaint(
        self, docs_db, no_searxng, monkeypatch
    ):
        """Control: the happy path must not grow a spurious error string."""
        from wet_mcp import embedder

        lib_id, ver_id = _fresh_version(docs_db)
        monkeypatch.setattr(
            server, "_fetch_and_chunk_docs", AsyncMock(return_value=(_chunks(2), 3))
        )
        # A resolvable backend, or the indexer takes the keyword-only branch
        # before it ever calls _embed_batch.
        embed_backend = AsyncMock()
        embed_backend.embed_texts = AsyncMock(return_value=[[0.1] * 4] * 2)
        monkeypatch.setattr(embedder, "_backend", embed_backend)

        await server._background_index_and_search(
            library="alpha",
            lib_key="alpha",
            language=None,
            docs_url=DOCS_URL,
            repo_url="",
            query="how to install",
            version=None,
            lib_id=lib_id,
            ver_id=ver_id,
        )

        state = docs_db.get_index_state(ver_id)
        assert state["state"] == INDEX_STATE_DONE
        assert state["error"] is None


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


@pytest.fixture
def real_backend_factories(monkeypatch):
    """Undo conftest's blanket stubbing of the two init factories.

    Without this the code under test never runs at all.
    """
    from wet_mcp import embedder, reranker

    monkeypatch.setattr(embedder, "init_backend", _REAL_INIT_BACKEND)
    monkeypatch.setattr(reranker, "init_reranker", _REAL_INIT_RERANKER)


class TestStartupNeverInstallsABackendItCannotLoad:
    @staticmethod
    def _enable_local_startup(monkeypatch):
        from wet_mcp.config import settings

        monkeypatch.setattr(type(settings), "local_embed_available", lambda self: True)
        monkeypatch.setattr(type(settings), "local_rerank_available", lambda self: True)

    async def test_local_backend_is_not_installed_when_the_package_is_absent(
        self, slim_image, real_backend_factories
    ):
        """A slim image with no cell and no local leg resolves to NO backend.

        The startup init must not install an unusable backend as the process
        singleton: every later request would resolve to an object whose first
        use raises, and the indexer's ``is None`` guard -- the one place
        written to produce a loud, informative degrade -- never fires.
        """
        from wet_mcp import embedder

        await server._init_embedding_backend()

        assert embedder.get_backend() is None
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    async def test_local_backend_is_cleared_when_availability_check_returns_zero(
        self, real_backend_factories, monkeypatch
    ):
        from wet_mcp import embedder
        from wet_mcp.embedder import LocalEmbeddingBackend

        self._enable_local_startup(monkeypatch)
        monkeypatch.setattr(
            LocalEmbeddingBackend, "check_available", AsyncMock(return_value=0)
        )

        await server._init_embedding_backend()

        assert embedder.get_backend() is None

    async def test_local_backend_is_cleared_when_availability_check_raises(
        self, real_backend_factories, monkeypatch
    ):
        from wet_mcp import embedder
        from wet_mcp.embedder import LocalEmbeddingBackend

        self._enable_local_startup(monkeypatch)
        monkeypatch.setattr(
            LocalEmbeddingBackend,
            "check_available",
            AsyncMock(side_effect=RuntimeError("embedding unavailable")),
        )

        await server._init_embedding_backend()

        assert embedder.get_backend() is None

    async def test_local_reranker_is_not_installed_when_the_package_is_absent(
        self, slim_image, real_backend_factories
    ):
        from wet_mcp import reranker

        await server._init_reranker_backend()

        assert reranker.get_reranker() is None
        assert slim_image == [], f"local ONNX leg was entered: {slim_image}"

    async def test_local_reranker_is_cleared_when_availability_check_returns_false(
        self, real_backend_factories, monkeypatch
    ):
        from wet_mcp import reranker
        from wet_mcp.reranker import LocalReranker

        self._enable_local_startup(monkeypatch)
        monkeypatch.setattr(LocalReranker, "check_available", Mock(return_value=False))

        await server._init_reranker_backend()

        assert reranker.get_reranker() is None

    async def test_local_reranker_is_cleared_when_availability_check_raises(
        self, real_backend_factories, monkeypatch
    ):
        from wet_mcp import reranker
        from wet_mcp.reranker import LocalReranker

        self._enable_local_startup(monkeypatch)
        monkeypatch.setattr(
            LocalReranker,
            "check_available",
            Mock(side_effect=RuntimeError("reranker unavailable")),
        )

        await server._init_reranker_backend()

        assert reranker.get_reranker() is None
