"""``wet.docs_reembed`` — host-side vector backfill for docs chunks.

Exercises the real decision ladder against a real DocsDB (dims=4, vec
table on): backend resolution (cell → local → pending), the batch →
per-chunk degradation on embed failures, head truncation at 8000 chars,
identity stamping, and every terminal status (pending/error/dry-run/ok).
Embeddings come from recorded fakes — no model, no network.
"""

import sqlite3
from types import SimpleNamespace

import pytest

from wet.config import settings
from wet.db import DocsDB
from wet.docs_reembed import reembed

DIMS = 4


def _vec_doc_ids(db_path):
    """Read the vec0 table through the store's own extension-loaded conn."""
    db = DocsDB(db_path, embedding_dims=DIMS)
    try:
        return {row[0] for row in db._conn.execute("SELECT id FROM doc_chunks_vec")}
    finally:
        db._conn.close()


def _store_meta(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return dict(conn.execute("SELECT key, value FROM store_meta"))
    finally:
        conn.close()


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A real docs store with two unembedded chunks + the runtime patches
    that pin the CLI repair entry to the local-backend leg at dims=4."""
    db = DocsDB(tmp_path / "docs.db", embedding_dims=DIMS)
    if not db._vec_enabled:
        # macOS CI: sqlite3 built without enable_load_extension, so the
        # vector table never exists here (same guard as test_embed_run_budget).
        db.close()
        pytest.skip(
            "sqlite-vec did not load here, so doc_chunks_vec was never "
            "created; vector-backed reembed paths run on the other legs"
        )
    lib_id = db.upsert_library(name="fastapi", docs_url="https://fastapi.tiangolo.com")
    ver_id = db.upsert_version(library_id=lib_id, version="latest")
    db.add_chunks(
        ver_id,
        lib_id,
        [
            {
                "url": "https://x/1",
                "title": "one",
                "content": "alpha",
                "chunk_index": 0,
            },
            {"url": "https://x/2", "title": "two", "content": "beta", "chunk_index": 1},
        ],
    )
    monkeypatch.setattr(settings, "embedding_dims", DIMS, raising=False)
    monkeypatch.setattr("wet.runtime.cell_configured", lambda name: False)
    yield db, tmp_path / "docs.db"
    db.close()


def _fake_local_backend(monkeypatch, vectors=None):
    """A real LocalEmbeddingBackend whose embed leg is a recorded fake."""
    from wet.embedder import LocalEmbeddingBackend

    backend = LocalEmbeddingBackend("local-test-model")
    calls: list = []

    async def fake_embed_texts(texts, dimensions=None):
        calls.append((list(texts), dimensions))
        if vectors is not None:
            return vectors
        return [[0.1] * DIMS for _ in texts]

    monkeypatch.setattr(backend, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(
        "wet.embedder.resolve_embed_backend_for_request", lambda: backend
    )
    return backend, calls


# ---------------------------------------------------------------------------
# resolution + preflight guards
# ---------------------------------------------------------------------------


async def test_reembed_pending_when_no_backend_resolves(store, monkeypatch):
    _, db_path = store
    monkeypatch.setattr("wet.embedder.resolve_embed_backend_for_request", lambda: None)

    result = await reembed(db_path=db_path)

    assert result["status"] == "pending"
    assert "no embedding backend" in result["reason"]


async def test_reembed_error_when_docs_db_missing(tmp_path, monkeypatch):
    _fake_local_backend(monkeypatch)
    monkeypatch.setattr(settings, "embedding_dims", DIMS, raising=False)
    monkeypatch.setattr("wet.runtime.cell_configured", lambda name: False)

    result = await reembed(db_path=tmp_path / "absent.db")

    assert result["status"] == "error"
    assert "no docs db" in result["reason"]


async def test_reembed_rejects_nonpositive_batch_size(store, monkeypatch):
    _, db_path = store
    _fake_local_backend(monkeypatch)

    with pytest.raises(ValueError, match="batch_size"):
        await reembed(db_path=db_path, batch_size=0)


async def test_reembed_error_when_vector_table_absent(tmp_path, monkeypatch):
    """dims=0 store has no doc_chunks_vec; backfill cannot store anything."""
    db = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    lib_id = db.upsert_library(name="x")
    ver_id = db.upsert_version(library_id=lib_id, version="latest")
    db.add_chunks(ver_id, lib_id, [{"content": "c", "chunk_index": 0}])
    db.close()
    # dims resolve to 0 (settings unset + default overridden) -> vec-less open.
    monkeypatch.setattr(settings, "embedding_dims", 0, raising=False)
    monkeypatch.setattr("wet.runtime.DEFAULT_EMBEDDING_DIMS", 0)
    monkeypatch.setattr("wet.runtime.cell_configured", lambda name: False)
    _fake_local_backend(monkeypatch)

    result = await reembed(db_path=tmp_path / "docs.db")

    assert result["status"] == "error"
    assert "doc_chunks_vec" in result["reason"]


# ---------------------------------------------------------------------------
# dry-run / already-complete
# ---------------------------------------------------------------------------


async def test_reembed_dry_run_reports_counts_without_writes(store, monkeypatch):
    _, db_path = store
    _fake_local_backend(monkeypatch)

    result = await reembed(db_path=db_path, dry_run=True)

    assert result["status"] == "dry-run"
    assert result["missing"] == 2
    assert result["embedded"] == 0
    assert result["remaining"] == 2
    assert result["vectors_present"] == 0
    assert result["chunks_total"] == 2
    assert "embedding_model" not in _store_meta(db_path)


async def test_reembed_noop_stamps_identity_and_reports_zero(store, monkeypatch):
    """Chunks already embedded: only the identity stamp must happen."""
    db, db_path = store
    ids = [row[0] for row in db._conn.execute("SELECT id FROM doc_chunks")]
    db._add_chunk_vectors(ids, [[0.5] * DIMS, [0.6] * DIMS])
    db._conn.commit()
    _fake_local_backend(monkeypatch)

    result = await reembed(db_path=db_path)

    assert result["status"] == "ok"
    assert result["embedded"] == 0 and result["remaining"] == 0
    meta = _store_meta(db_path)
    assert meta["embedding_dims"] == str(DIMS)
    # A local-backend run stamps the shared local model string as identity.
    assert meta["embedding_model"] == settings.resolve_local_embedding_model()
    assert result["model"] == meta["embedding_model"]


# ---------------------------------------------------------------------------
# happy path + failure degradation
# ---------------------------------------------------------------------------


async def test_reembed_backfills_vectors_and_stamps_identity(store, monkeypatch):
    _, db_path = store
    _fake_local_backend(monkeypatch)

    result = await reembed(db_path=db_path, batch_size=64)

    assert result["status"] == "ok"
    assert result["embedded"] == 2
    assert result["remaining"] == 0
    assert result["vectors_present"] == 0  # snapshot taken before the run
    assert len(_vec_doc_ids(db_path)) == 2
    meta = _store_meta(db_path)
    assert meta["embedding_dims"] == str(DIMS)
    assert meta["embedding_model"] == settings.resolve_local_embedding_model()
    assert result["model"] == meta["embedding_model"]


async def test_reembed_failed_batch_degrades_to_per_chunk(store, monkeypatch):
    """One pathological chunk must not lose the whole batch."""
    _, db_path = store
    from wet.embedder import LocalEmbeddingBackend

    backend = LocalEmbeddingBackend("local-test-model")
    batch_calls: list = []

    async def flaky_embed(texts, dimensions=None):
        batch_calls.append(list(texts))
        if len(texts) > 1:
            raise RuntimeError("onnx workspace overflow")
        if texts[0] == "beta":
            raise RuntimeError("chunk too weird")
        return [[0.3] * DIMS]

    monkeypatch.setattr(backend, "embed_texts", flaky_embed)
    monkeypatch.setattr(
        "wet.embedder.resolve_embed_backend_for_request", lambda: backend
    )

    conn = sqlite3.connect(str(db_path))
    try:
        id_by_content = {
            content: cid
            for cid, content in conn.execute("SELECT id, content FROM doc_chunks")
        }
    finally:
        conn.close()

    result = await reembed(db_path=db_path, batch_size=8)

    assert result["status"] == "ok"
    assert result["embedded"] == 1
    assert result["failed"] == [id_by_content["beta"]]
    assert result["remaining"] == 1
    # The good chunk survived the batch failure; the bad one stayed vectorless.
    assert _vec_doc_ids(db_path) == {id_by_content["alpha"]}


async def test_reembed_head_truncates_oversized_chunks(store, monkeypatch):
    _, db_path = store
    db = store[0]
    lib_id = db.upsert_library(name="big")
    ver_id = db.upsert_version(library_id=lib_id, version="latest")
    db.add_chunks(
        ver_id,
        lib_id,
        [{"url": "u", "title": "t", "content": "z" * 9000, "chunk_index": 0}],
    )
    _, calls = _fake_local_backend(monkeypatch)

    result = await reembed(db_path=db_path, batch_size=4)

    assert result["status"] == "ok"
    assert result["truncated"] == 1
    # Every text handed to the backend is within the ONNX-safe budget.
    assert all(len(t) <= 8000 for texts, _ in calls for t in texts)


# ---------------------------------------------------------------------------
# cloud-cell construction branch (CLI repair entry)
# ---------------------------------------------------------------------------


async def test_reembed_prefers_configured_embed_cell(store, monkeypatch):
    """A host-configured [models.embed] cell builds the cloud backend itself."""
    _, db_path = store
    constructed: list = []

    class FakeCloudBackend:
        def __init__(self, client):
            constructed.append(client)
            self.client = client

        async def embed_texts(self, texts, dimensions=None):
            return [[0.9] * DIMS for _ in texts]

    client = SimpleNamespace(name="provider-client")
    monkeypatch.setattr("wet.embedder.CloudEmbeddingBackend", FakeCloudBackend)
    monkeypatch.setattr("wet.runtime.cell_configured", lambda name: True)
    monkeypatch.setattr(
        "wet.runtime.model_cell",
        lambda name: SimpleNamespace(model="voyage-4-lite"),
    )
    monkeypatch.setattr("wet.runtime.provider_client", lambda name: client)

    result = await reembed(db_path=db_path)

    assert result["status"] == "ok"
    assert result["embedded"] == 2
    assert constructed == [client]
    assert result["model"] == "openai-spec:voyage-4-lite"
    assert _store_meta(db_path)["embedding_model"] == "openai-spec:voyage-4-lite"


async def test_reembed_keeps_server_resolved_cloud_identity(store, monkeypatch):
    """No cell, but the server resolved a cloud singleton: keep ITS identity."""
    _, db_path = store

    async def fake_embed(texts, dimensions=None):
        return [[0.2] * DIMS for _ in texts]

    # Not a LocalEmbeddingBackend: the server resolved a cloud singleton.
    cloud_like = SimpleNamespace(model=None, embed_texts=fake_embed)
    monkeypatch.setattr(
        "wet.embedder.resolve_embed_backend_for_request", lambda: cloud_like
    )
    monkeypatch.setattr("wet.runtime.cell_configured", lambda name: False)
    monkeypatch.setattr(
        "wet.runtime.model_cell",
        lambda name: SimpleNamespace(model="voyage-2.5-lite"),
    )

    result = await reembed(db_path=db_path)

    assert result["status"] == "ok"
    assert result["model"] == "openai-spec:voyage-2.5-lite"
