"""The Tier 1 ingest script and the server must agree on embedding identity.

``DocsDB`` stamps ``(embedding_model, embedding_dims)`` into ``store_meta`` on
first open and refuses to reopen a store stamped with a different identity
(``EmbeddingModelMismatch``). Both the script and the server therefore have to
build the store through the same construction path -- ``make_docs_db`` -- which
stamps the ``[models.embed]`` cell's model (``openai-spec:<model>``) when the
host configured one, and the local ONNX model id otherwise, always at the
server's 768 default dims.

These tests pin both open orders, the CI-runner case specifically (no host
key present, so the stamp must still be the 768-dim local identity, never 0),
and the de-hosted storage contract: the store is local SQLite, whatever a
stale ``DOCS_DB_BACKEND`` environment variable claims.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sqlite3

import pytest

from wet_mcp import server
from wet_mcp.config import settings
from wet_mcp.db import DocsDB, EmbeddingModelMismatch

_SCRIPT = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "build_tier1_index.py"
)
_spec = importlib.util.spec_from_file_location("build_tier1_index", _SCRIPT)
assert _spec is not None and _spec.loader is not None
build_tier1_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_tier1_index)

# Every host cell key that can configure the embed identity. Cleared so a
# developer shell that exports one does not turn a clean-runner test into a
# cloud-identity test.
_CELL_KEYS = (
    "HULL_EMBED_API_KEY",
    "HULL_RERANK_API_KEY",
    "HULL_CHAT_API_KEY",
    "HULL_JEV_SCORE_API_KEY",
)


@pytest.fixture
def clean_runner_env(monkeypatch):
    """Reproduce a clean CI runner: no host cell keys, no rebuild escape hatch.

    ``REINDEX_ON_MODEL_CHANGE`` is cleared on both the env and the settings
    singleton: with it set the guard rebuilds instead of raising, which is
    exactly how a developer shell that exports it hides this bug.
    ``EMBEDDING_DIMS`` is cleared and the singleton reset to 0 so the store is
    stamped at the server default, not a developer's override.
    """
    for key in _CELL_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("EMBEDDING_DIMS", raising=False)
    monkeypatch.delenv("REINDEX_ON_MODEL_CHANGE", raising=False)
    monkeypatch.setattr(settings, "embedding_dims", 0)
    monkeypatch.setattr(settings, "reindex_on_model_change", False)
    from wet_mcp.runtime import reset_settings_cache

    reset_settings_cache()


@pytest.fixture
def embed_cell_configured(clean_runner_env, monkeypatch):
    """A host that configured the ``[models.embed]`` cell (key via start env)."""
    monkeypatch.setenv("HULL_EMBED_API_KEY", "placeholder-not-a-real-key")


def _stamp(db_path: pathlib.Path) -> dict[str, str]:
    """Read the embedding identity recorded in ``store_meta``."""
    conn = sqlite3.connect(str(db_path))
    try:
        return dict(
            conn.execute(
                "SELECT key, value FROM store_meta "
                "WHERE key IN ('embedding_model', 'embedding_dims')"
            ).fetchall()
        )
    finally:
        conn.close()


def _open_as_server(db_path: pathlib.Path, monkeypatch):
    """Open ``db_path`` through the server's own construction path.

    Goes through ``settings.get_db_path()`` rather than an argument, so the
    test exercises the resolution a running server actually uses.
    """
    monkeypatch.setattr(settings, "docs_db_path", str(db_path))
    return server.make_docs_db()


def test_script_stamped_store_opens_with_server_construction(
    tmp_path, monkeypatch, clean_runner_env
):
    """Direction 2: the weekly job's store must be openable by a server.

    This is the CI case: no host cell key is present, so the script stamps the
    local identity -- which must still be a real one. The historical bug was
    stamping ``dims=0`` ("no model, no dims"), which disables sqlite-vec
    entirely and yields a store that could never hold the vectors the server
    expects to find there.
    """
    db_path = tmp_path / "docs.db"

    build_tier1_index.open_docs_db(db_path).close()
    script_stamp = _stamp(db_path)

    assert script_stamp.get("embedding_dims") != "0", (
        f"script stamped a dims=0 identity no server produces: {script_stamp}"
    )
    assert script_stamp.get("embedding_model"), script_stamp

    _open_as_server(db_path, monkeypatch).close()
    assert _stamp(db_path) == script_stamp, (
        "opening as the server changed the stamp, so the two callers still "
        "disagree about identity"
    )


def test_script_opens_store_stamped_by_server(
    tmp_path, monkeypatch, embed_cell_configured
):
    """Direction 1: eager ingest on a host that configured the embed cell.

    The server stamps the cell identity ``openai-spec:<cell model>``; the
    script -- delegating to the same ``make_docs_db`` -- must accept and keep
    that stamp instead of refusing the store.
    """
    db_path = tmp_path / "docs.db"

    _open_as_server(db_path, monkeypatch).close()
    server_stamp = _stamp(db_path)
    assert server_stamp == {
        "embedding_dims": "768",
        "embedding_model": "openai-spec:voyage-4-lite",
    }, server_stamp

    build_tier1_index.open_docs_db(db_path).close()
    assert _stamp(db_path) == server_stamp


def test_script_and_server_agree_without_any_provider_key(
    tmp_path, monkeypatch, clean_runner_env
):
    """Both orders agree on a clean runner, and neither stamps dims=0.

    Pins the answer to "what does a keyless runner resolve to": the local ONNX
    identity at the server's default 768 dims, not ``unavailable``/0.
    """
    script_first = tmp_path / "script_first.db"
    build_tier1_index.open_docs_db(script_first).close()

    server_first = tmp_path / "server_first.db"
    _open_as_server(server_first, monkeypatch).close()

    assert _stamp(script_first) == _stamp(server_first)
    assert _stamp(script_first)["embedding_dims"] == "768"


def test_store_is_sqlite_only_even_with_stale_backend_env(
    tmp_path, monkeypatch, clean_runner_env
):
    """De-host: the cf-d1 backend branch is gone; storage is always local SQLite.

    The script is SQLite-shaped end to end (``--db-path``, migrations, the
    metrics file written beside the database). A stale ``DOCS_DB_BACKEND=cf-d1``
    in the environment must not reroute ingest: the store written is the local
    SQLite file at the operator-named path.
    """
    monkeypatch.setenv("DOCS_DB_BACKEND", "cf-d1")

    db_path = tmp_path / "docs.db"
    db = build_tier1_index.open_docs_db(db_path)
    try:
        assert isinstance(db, DocsDB)
    finally:
        db.close()

    conn = sqlite3.connect(str(db_path))
    try:
        # The identity stamp proves the server-shaped SQLite store exists.
        assert conn.execute("SELECT count(*) FROM store_meta").fetchone()[0] > 0
    finally:
        conn.close()


def test_ingest_works_without_an_embedder_available(
    tmp_path, monkeypatch, clean_runner_env
):
    """A keyless runner must still be able to write chunks.

    The stamped dims of 768 turn on the sqlite-vec table. CI has no host cell
    key and downloads no local model, so if ``add_chunks`` needed an embedder
    once dims > 0 the contract would trade a corrupt store for a broken
    weekly job.
    """
    db_path = tmp_path / "docs.db"
    db = build_tier1_index.open_docs_db(db_path)
    try:
        lib_id = db.upsert_library(name="requests", canonical_name="requests")
        ver_id = db.upsert_version(library_id=lib_id, version="latest")
        # Exactly how ingest_tier2 calls it: no ``embeddings`` argument.
        written = db.add_chunks(
            version_id=ver_id,
            library_id=lib_id,
            chunks=[
                {
                    "url": "https://example.com/doc",
                    "title": "Doc",
                    "content": "some documentation text",
                    "heading_path": "",
                    "chunk_index": 0,
                }
            ],
        )
    finally:
        db.close()

    assert written == 1
    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT count(*) FROM doc_chunks").fetchone()[0] == 1
    finally:
        conn.close()


def test_guard_still_fires_on_a_genuine_model_change(
    tmp_path, monkeypatch, clean_runner_env
):
    """Positive control: none of the above may have defanged the guard.

    Every other test here asserts something opens. Without this one they would
    also pass if the guard had been disabled, the exception swallowed, or
    ``REINDEX_ON_MODEL_CHANGE`` switched on.
    """
    db_path = tmp_path / "docs.db"
    build_tier1_index.open_docs_db(db_path).close()

    monkeypatch.setenv("HULL_EMBED_API_KEY", "placeholder-not-a-real-key")
    with pytest.raises(EmbeddingModelMismatch):
        build_tier1_index.open_docs_db(db_path)
