"""``config(action="status")`` must describe the docs store actually in use.

The status payload is what an operator reads before they go looking for the
data: they copy ``database.path`` into a backup script, an rsync, a `sqlite3`
session. De-host there is exactly one backend — the local SQLite file under
``~/.wet/`` — so ``backend`` always reads ``"sqlite"`` and ``path`` always
names the real file: printing anything else would point the operator at a
file whose contents are unrelated to what the server is serving.
"""

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _status_backends():
    """Keep the status call off real model loading (it never had singletons).

    ``_handle_config_status`` calls the per-request resolvers directly, so the
    stub keeps the local ONNX legs from being constructed during a status read.
    """
    with (
        patch("wet_mcp.embedder.resolve_embed_backend_for_request", return_value=None),
        patch("wet_mcp.reranker.resolve_rerank_backend_for_request", return_value=None),
        patch("wet_mcp.embedder.embedding_unavailable_reason", return_value=None),
    ):
        yield


@pytest.fixture
def _built_backend(monkeypatch):
    """Run the real ``make_docs_db`` builder, stubbing only its leaf opener.

    What gets replaced is strictly what would demand a disk file: the
    ``DocsDB.__init__`` on the real class (not the name ``server`` holds), so
    construction records the build and opens nothing. The CF D1 backend is
    gone — there is no other branch left to stub.

    Returns a list that records ``"sqlite"`` per construction.
    """
    from wet_mcp.db import DocsDB

    built: list[str] = []

    def _sqlite_init(self, *args, **kwargs):
        built.append("sqlite")

    monkeypatch.setattr(DocsDB, "__init__", _sqlite_init)
    return built


async def test_status_names_the_single_sqlite_backend(monkeypatch, _status_backends):
    """The only backend is the local store; the label is a constant."""
    from wet_mcp.server import _active_docs_backend, _handle_config_status

    assert _active_docs_backend() == "sqlite"
    status = await _handle_config_status()
    assert status["database"]["backend"] == "sqlite"


async def test_status_names_sqlite_even_with_stale_backend_env(
    monkeypatch, _status_backends
):
    """A stale ``DOCS_DB_BACKEND`` env var must not resurrect the CF backend.

    The de-host removed the field, so nothing reads the var — but an old
    container env still carries it. The status label and the store must not
    flip based on dead configuration.
    """
    from wet_mcp.server import _active_docs_backend, _handle_config_status

    monkeypatch.setenv("DOCS_DB_BACKEND", "cf-d1")

    assert _active_docs_backend() == "sqlite"
    assert (await _handle_config_status())["database"]["backend"] == "sqlite"


async def test_status_reports_the_local_docs_path(monkeypatch, _status_backends):
    """The field every existing reader expects: the real local file."""
    from wet_mcp.config import settings
    from wet_mcp.server import _handle_config_status

    status = await _handle_config_status()

    assert status["database"]["path"] == str(settings.get_db_path())
    assert status["database"]["path"].endswith("docs.db")


async def test_status_leaks_no_host_secret(monkeypatch, _status_backends):
    """Naming the store must not drag secret material into the payload.

    ``config`` is an operator-facing tool, but its output gets pasted into bug
    reports and agent transcripts; whatever shows up here must be paths and
    labels only.
    """
    from wet_mcp.config import settings
    from wet_mcp.server import _handle_config_status

    monkeypatch.setattr(settings, "tavily_api_key", "SECRET-TAVILY", raising=False)
    monkeypatch.setattr(settings, "brave_api_key", "SECRET-BRAVE", raising=False)
    monkeypatch.setattr(settings, "openrouter_api_key", "SECRET-OR", raising=False)

    dumped = json.dumps(await _handle_config_status(), default=str)

    for secret in ("SECRET-TAVILY", "SECRET-BRAVE", "SECRET-OR"):
        assert secret not in dumped


async def test_make_docs_db_builds_sqlite_and_status_agrees(
    monkeypatch, _built_backend, _status_backends
):
    """The status label and the constructed store must never disagree.

    ``_active_docs_backend`` is documented as a mirror of what ``make_docs_db``
    builds. A docstring is a promise nobody checks, so run the real builder
    (leaf-stubbed) and hold the label against the outcome.
    """
    from wet_mcp.config import settings
    from wet_mcp.server import _active_docs_backend, _handle_config_status, make_docs_db

    make_docs_db()
    assert _built_backend == ["sqlite"], "make_docs_db built something else"

    assert _active_docs_backend() == "sqlite"

    status = await _handle_config_status()
    assert status["database"]["backend"] == "sqlite"
    assert status["database"]["path"] == str(settings.get_db_path())


async def test_status_reports_empty_stats_when_docs_db_not_initialized(
    monkeypatch, _status_backends
):
    """Before the lifespan opens the store, stats read as ``{}`` — not a lie."""
    from wet_mcp import server
    from wet_mcp.server import _handle_config_status

    monkeypatch.setattr(server, "_docs_db", None)

    status = await _handle_config_status()

    assert status["database"]["docs_indexed"] == {}
