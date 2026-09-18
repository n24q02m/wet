import inspect
import json
from pathlib import Path

import pytest
from conftest_cf import FakeD1Http, FakeVectorizeHttp
from mcp_core.storage.d1 import D1Backend
from mcp_core.storage.vectorize import VectorizeBackend

from wet_mcp.db import DocsDB
from wet_mcp.db_cf import DocsDBCfBackend
from wet_mcp.sources.docs import DocsQueryOptions, query_docs, resolve_library

# The D1 schema now spans more than one migration (0002 adds project_context and
# libraries.metadata_seeded_at), so apply them all in order rather than pinning 0001.
DDL = "\n".join(
    p.read_text(encoding="utf-8") for p in sorted(Path("migrations").glob("*.sql"))
)


def _backend(ready_after=0):
    d1 = D1Backend("http://d1.internal", http=FakeD1Http(DDL))
    vec = VectorizeBackend(
        "http://vectorize.internal", idx="wet", http=FakeVectorizeHttp(ready_after)
    )
    return DocsDBCfBackend(d1, vec, embedding_dims=768)


def test_add_chunks_then_fts_search():
    db = _backend()
    db.upsert_library("alpha", docs_url="https://a")
    lib = db.get_library("alpha")
    # upsert_version returns the id directly. get_best_version means "best
    # INDEXED version", and this row does not reach status='indexed' until
    # mark_version_indexed runs, so it is the wrong way to fetch a fresh row.
    ver_id = db.upsert_version(lib["id"], "1.0")
    db.add_chunks(
        ver_id,
        lib["id"],
        [
            {
                "id": "c1",
                "url": "https://a/p1",
                "title": "API",
                "chunk_index": 0,
                "content": "async function handler with error handling",
                "heading_path": "API",
            },
        ],
        embeddings=None,
    )
    results = db.search("function", limit=5)
    assert results and results[0]["content"].startswith("async function")
    assert results[0]["url"] == "https://a/p1"


def test_stats_reports_counts():
    # config(action="status") calls _docs_db.stats(); the CF backend must expose it
    # (regression: wet CF config(status) crashed with "'DocsDBCfBackend' object has no
    # attribute 'stats'", 2026-06-17).
    db = _backend()
    assert db.stats() == {"libraries": 0, "chunks": 0, "vec_enabled": True}
    db.upsert_library("alpha", docs_url="https://a")
    lib = db.get_library("alpha")
    # upsert_version returns the id directly. get_best_version means "best
    # INDEXED version", and this row does not reach status='indexed' until
    # mark_version_indexed runs, so it is the wrong way to fetch a fresh row.
    ver_id = db.upsert_version(lib["id"], "1.0")
    db.add_chunks(
        ver_id,
        lib["id"],
        [
            {
                "id": "c1",
                "url": "https://a/p1",
                "title": "API",
                "chunk_index": 0,
                "content": "hello world",
                "heading_path": "API",
            },
        ],
        embeddings=None,
    )
    s = db.stats()
    assert s["libraries"] == 1
    assert s["chunks"] == 1
    assert s["vec_enabled"] is True


def test_resolve_library_uses_cf_backend_for_prefix_and_substring():
    db = _backend()
    db.upsert_library("next")
    db.upsert_library("nextflow")
    db.upsert_library("my-react-lib")

    prefix = resolve_library(db, "next")
    substring = resolve_library(db, "react")

    assert [item["name"] for item in prefix] == ["next", "nextflow"]
    assert [item["name"] for item in substring] == ["my-react-lib"]


def test_query_docs_hydrates_library_through_cf_backend_api():
    db = _backend()
    lib_id = db.upsert_library("alpha")
    ver_id = db.upsert_version(lib_id, "1.0")
    db.add_chunks(
        ver_id,
        lib_id,
        [{"url": "https://a/p1", "content": "async function handler"}],
        embeddings=None,
    )
    db.mark_version_indexed(ver_id, page_count=1, chunk_count=1)

    results = query_docs(db, lib_id, "function", options=DocsQueryOptions(limit=1))

    assert results and results[0]["library"] == "alpha"


def test_hybrid_search_applies_rrf_and_url_diversity():
    db = _backend()
    db.upsert_library("alpha", docs_url="https://a")
    lib = db.get_library("alpha")
    ver_id = db.upsert_version(lib["id"], "1.0")
    chunks = [
        {
            "id": f"c{i}",
            "url": "https://a/same",
            "title": "T",
            "chunk_index": i,
            "content": f"vector search cosine similarity chunk {i}",
            "heading_path": "H",
        }
        for i in range(5)
    ]
    embeddings = [[1.0, 0.0, 0.0] + [0.0] * 765 for _ in chunks]
    db.add_chunks(ver_id, lib["id"], chunks, embeddings=embeddings)
    results = db.search(
        "vector search", limit=10, query_embedding=[1.0, 0.0, 0.0] + [0.0] * 765
    )
    # URL diversity caps same-url chunks at 2 (db.py max_per_url = 2)
    same_url = [r for r in results if r["url"] == "https://a/same"]
    assert len(same_url) <= 2


QUERIES = [
    "async function",
    "install the package",
    "error handling",
    "rate limit",
    "vector search",
]


def test_cf_search_matches_sqlite_golden(cf_corpus, cf_golden_topk):
    db = _backend()
    for d in cf_corpus:
        db.upsert_library(d["library"], docs_url=d["url"])
        lib = db.get_library(d["library"])
        ver_id = db.upsert_version(lib["id"], d["version"])
        db.add_chunks(ver_id, lib["id"], [d], embeddings=None)  # FTS-only parity
    for q in QUERIES:
        cf_top = [r["content"][:40] for r in db.search(q, limit=10)]
        golden = cf_golden_topk[q]
        overlap = len(set(cf_top[:3]) & set(golden[:3]))
        assert overlap >= 2, (
            f"top-3 rank parity failed for {q!r}: {cf_top[:3]} vs {golden[:3]}"
        )


# ---------------------------------------------------------------------------
# Regression: cf-d1 index path died before a single row reached doc_chunks
# ---------------------------------------------------------------------------


def test_upsert_version_accepts_docs_url_kwarg():
    """Both production index call sites pass ``docs_url=``: ``server.py`` (docs
    auto-index) and ``sources/docs.py`` (tier-2 lazy index). ``DocsDB.upsert_version``
    accepts it; ``DocsDBCfBackend.upsert_version`` did not, so under
    ``DOCS_DB_BACKEND=cf-d1`` every index run raised TypeError *after*
    ``upsert_library`` had already committed -- ``libraries`` kept growing while
    ``doc_chunks`` stayed at 0.
    """
    db = _backend()
    lib_id = db.upsert_library("alpha", docs_url="https://a")
    ver_id = db.upsert_version(
        library_id=lib_id, version="1.0", docs_url="https://a/docs"
    )
    # Read the row itself: this asserts what upsert_version WROTE, which is a
    # different question from what get_best_version chooses to SERVE.
    row = db._d1.fetchone("SELECT * FROM versions WHERE id = ?", [ver_id])
    assert row["id"] == ver_id
    assert row["docs_url"] == "https://a/docs"


def test_upsert_version_updates_docs_url_on_existing_row():
    """Mirror ``DocsDB.upsert_version``: an existing row is reused, a non-empty
    ``docs_url`` is written back onto it, and a missing one leaves it untouched.
    """
    db = _backend()
    lib_id = db.upsert_library("alpha", docs_url="https://a")

    def stored_docs_url(ver_id):
        # The stored row, not get_best_version: a 'pending' version is exactly
        # what this test is about, and "best version" no longer includes one.
        return db._d1.fetchone("SELECT * FROM versions WHERE id = ?", [ver_id])[
            "docs_url"
        ]

    first = db.upsert_version(lib_id, "1.0")
    assert stored_docs_url(first) is None

    again = db.upsert_version(lib_id, "1.0", docs_url="https://a/docs")
    assert again == first
    assert stored_docs_url(first) == "https://a/docs"

    db.upsert_version(lib_id, "1.0")
    assert stored_docs_url(first) == "https://a/docs"


def test_upsert_version_defaults_to_latest():
    """``DocsDB.upsert_version`` defaults ``version`` to ``"latest"``; the CF
    backend made it required, so the two backends were not interchangeable."""
    db = _backend()
    lib_id = db.upsert_library("alpha", docs_url="https://a")
    ver_id = db.upsert_version(lib_id)
    row = db._d1.fetchone("SELECT * FROM versions WHERE id = ?", [ver_id])
    assert row["version"] == "latest"


def test_get_best_version_target_is_optional():
    """``config(action="clear")`` and ``cli.py`` call ``get_best_version(lib_id)``
    with no target. ``DocsDB`` defaults it to ``None``; the CF backend required a
    second argument and named it ``version``, so the same call raised TypeError.

    The fixture now indexes the version before reading it back. This test used
    to pass against a bare 'pending' row, which quietly pinned a second
    property the signature fix never intended to assert: that "best version"
    includes versions that were never indexed. `DocsDB.get_best_version`
    filters `status = 'indexed'` on both of its branches, so that reading made
    the two backends disagree about which version a library can serve (#1626).
    What this test is for -- `target` being optional and keyword-addressable --
    is unchanged and still asserted; only the fixture gained the
    `mark_version_indexed` that makes the row servable in the first place.
    """
    db = _backend()
    lib_id = db.upsert_library("alpha", docs_url="https://a")
    ver_id = db.upsert_version(lib_id, "1.0")
    db.mark_version_indexed(ver_id, 1, 1)
    assert db.get_best_version(lib_id)["id"] == ver_id
    assert db.get_best_version(lib_id, target="1.0")["id"] == ver_id


def test_add_chunks_persists_every_column_the_sqlite_backend_writes():
    """``doc_chunks`` in ``migrations/0001_init_wet.sql`` carries ``section``,
    ``topic``, ``content_hash`` and ``token_count``, and ``search()`` reads three of
    them back into its results. The CF writer only ever INSERTed the nine base
    columns, so those four were silently NULL on every cf-d1 row."""
    db = _backend()
    lib_id = db.upsert_library("alpha", docs_url="https://a")
    ver_id = db.upsert_version(lib_id, "1.0", docs_url="https://a/docs")
    db.add_chunks(
        ver_id,
        lib_id,
        [
            {
                "url": "https://a/p1",
                "title": "Routing",
                "chunk_index": 0,
                "content": "async function handler with error handling",
                "heading_path": "Guide > Routing",
                "section": "guide",
                "topic": "routing",
                "content_hash": "deadbeef",
                "token_count": 7,
            },
        ],
        embeddings=None,
    )

    # Looked up by version, not by a caller-chosen id: add_chunks mints the id
    # itself (like DocsDB does), so the caller never knows one.
    stored = db._d1.fetchone("SELECT * FROM doc_chunks WHERE version_id = ?", [ver_id])
    assert stored["section"] == "guide"
    assert stored["topic"] == "routing"
    assert stored["content_hash"] == "deadbeef"
    assert stored["token_count"] == 7

    result = db.search("function", limit=5)[0]
    assert result["section"] == "guide"
    assert result["topic"] == "routing"
    assert result["token_count"] == 7


def test_add_chunks_leaves_optional_columns_null_when_absent():
    """The optional keys stay optional: a v1-shaped chunk still inserts cleanly."""
    db = _backend()
    lib_id = db.upsert_library("alpha", docs_url="https://a")
    ver_id = db.upsert_version(lib_id, "1.0")
    db.add_chunks(
        ver_id,
        lib_id,
        [{"content": "hello world", "url": "https://a/p1"}],
        embeddings=None,
    )
    stored = db._d1.fetchone("SELECT * FROM doc_chunks WHERE version_id = ?", [ver_id])
    assert stored["section"] is None
    assert stored["topic"] is None
    assert stored["content_hash"] is None
    assert stored["token_count"] is None


# ---------------------------------------------------------------------------
# Signature parity gate: db_cf.py claims to mirror db.py, so prove it
# ---------------------------------------------------------------------------

MIRRORED_METHODS = sorted(
    name
    for name, _member in inspect.getmembers(DocsDBCfBackend, inspect.isfunction)
    if not name.startswith("_") and callable(getattr(DocsDB, name, None))
)


def _required(param):
    return param.default is inspect.Parameter.empty


@pytest.mark.parametrize("method_name", MIRRORED_METHODS)
def test_cf_backend_signature_mirrors_sqlite_backend(method_name):
    """``db_cf.py``'s module docstring states its public interface mirrors
    ``wet_mcp.db.DocsDB``, and ``server.py`` depends on that: it stores either
    backend in the same ``_docs_db`` global and calls it with keyword arguments.
    So every parameter ``DocsDB`` accepts must also be accepted by
    ``DocsDBCfBackend``, in the same order and with the same required/optional
    status.

    This is the gate that was missing when ``db_cf.py`` was first added: the new
    ``upsert_version`` silently dropped ``docs_url`` and no test compared the two
    signatures, so the drift shipped and broke every cf-d1 index run.
    """
    sqlite_params = inspect.signature(getattr(DocsDB, method_name)).parameters
    cf_params = inspect.signature(getattr(DocsDBCfBackend, method_name)).parameters
    cf_takes_kwargs = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in cf_params.values()
    )

    for name, sqlite_param in sqlite_params.items():
        if sqlite_param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        cf_param = cf_params.get(name)
        if cf_param is None:
            assert cf_takes_kwargs, (
                f"DocsDBCfBackend.{method_name}() does not accept {name!r}, "
                f"but DocsDB.{method_name}() does -- a call that works on the "
                f"sqlite backend raises TypeError on cf-d1"
            )
            continue
        assert _required(cf_param) == _required(sqlite_param), (
            f"DocsDBCfBackend.{method_name}() makes {name!r} "
            f"{'required' if _required(cf_param) else 'optional'} while "
            f"DocsDB.{method_name}() makes it "
            f"{'required' if _required(sqlite_param) else 'optional'}"
        )

    shared = [name for name in sqlite_params if name in cf_params]
    assert [name for name in cf_params if name in sqlite_params] == shared, (
        f"DocsDBCfBackend.{method_name}() reorders parameters relative to "
        f"DocsDB.{method_name}(), so positional calls bind different values"
    )


# ---------------------------------------------------------------------------
# Vectorize mutation batching: the Workers binding caps upsert / deleteByIds
# at 1000 vectors per call (developers.cloudflare.com/vectorize/platform/
# limits). A version bigger than that -- @modelcontextprotocol/sdk at 1875 --
# made config(action="docs_reindex") die mid-request ("Server disconnected
# without sending a response") twice on 2026-09-17, landing nothing.
# ---------------------------------------------------------------------------


class CappedVectorizeHttp(FakeVectorizeHttp):
    """FakeVectorizeHttp that enforces the real binding's per-request mutation
    ceiling, so any regression back to single-shot calls fails HERE instead of
    only on the deployed worker."""

    MAX_MUTATION = 1000

    def __init__(self) -> None:
        super().__init__()
        self.mutation_calls: list[tuple[str, int]] = []

    def request(self, method, url, data=None, headers=None):
        if url.endswith("/upsert"):
            lines = data.decode().splitlines()
            assert len(lines) <= self.MAX_MUTATION, (
                f"upsert sent {len(lines)} vectors in one request; the binding "
                f"caps mutations at {self.MAX_MUTATION}"
            )
            self.mutation_calls.append(("upsert", len(lines)))
        elif url.endswith("/deleteByIds"):
            ids = json.loads(data.decode())["ids"]
            assert len(ids) <= self.MAX_MUTATION, (
                f"deleteByIds sent {len(ids)} ids in one request; the binding "
                f"caps mutations at {self.MAX_MUTATION}"
            )
            self.mutation_calls.append(("deleteByIds", len(ids)))
        return super().request(method, url, data, headers)


def _backend_with_vec(vec):
    d1 = D1Backend("http://d1.internal", http=FakeD1Http(DDL))
    return DocsDBCfBackend(d1, vec, embedding_dims=768)


def _seed_version(db, chunk_count):
    lib_id = db.upsert_library("@modelcontextprotocol/sdk", docs_url="https://m")
    ver_id = db.upsert_version(lib_id, "latest", docs_url="https://m/docs")
    db.add_chunks(
        ver_id,
        lib_id,
        [
            {"content": f"chunk {i} client transport", "url": f"https://m/p{i}"}
            for i in range(chunk_count)
        ],
        embeddings=None,
    )
    db.mark_version_indexed(ver_id, 1, chunk_count)
    return ver_id


def test_clear_version_chunks_batches_1875_ids_under_binding_cap():
    """The 2026-09-17 incident: one deleteByIds call carrying all 1875 ids of
    @modelcontextprotocol/sdk exceeded the binding's 1000-mutation cap, killed
    the request before the D1 DELETE ran, and the reindex never landed."""
    vec_http = CappedVectorizeHttp()
    db = _backend_with_vec(
        VectorizeBackend("http://vectorize.internal", idx="wet", http=vec_http)
    )
    ver_id = _seed_version(db, 1875)

    removed = db.clear_version_chunks(ver_id)

    assert removed == 1875
    sizes = [n for kind, n in vec_http.mutation_calls if kind == "deleteByIds"]
    assert sizes == [1000, 875]
    # Both vectors and D1 rows are actually gone: the mutation ordering is
    # vectors-first precisely so a refusal leaves the store merely stale.
    assert vec_http.vectors == {}
    remaining = db._d1.fetchone(
        "SELECT COUNT(*) AS n FROM doc_chunks WHERE version_id = ?", [ver_id]
    )
    assert remaining["n"] == 0


def test_add_chunks_batches_1875_vectors_under_binding_cap():
    """Indexing a big library WITH embeddings would hit the identical single
    upsert overflow; batched, every vector still lands and stays queryable."""
    vec_http = CappedVectorizeHttp()
    db = _backend_with_vec(
        VectorizeBackend("http://vectorize.internal", idx="wet", http=vec_http)
    )
    lib_id = db.upsert_library("biglib", docs_url="https://b")
    ver_id = db.upsert_version(lib_id, "latest", docs_url="https://b/docs")
    chunks = [{"content": f"entry {i}", "url": f"https://b/p{i}"} for i in range(1875)]
    embeddings = [[float(i % 7), 1.0] for i in range(1875)]

    db.add_chunks(ver_id, lib_id, chunks, embeddings=embeddings)

    sizes = [n for kind, n in vec_http.mutation_calls if kind == "upsert"]
    assert sizes == [1000, 875]
    assert len(vec_http.vectors) == 1875
    hits = db.search("entry 1", limit=3)
    assert hits
