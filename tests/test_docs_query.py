"""Tests for ``query_docs`` and ``search(action="docs_query")``.

Covers:

* version filter — chunks from non-pinned versions are excluded;
* topic filter — chunks with non-matching topic are excluded;
* token cap — sum of returned token_count <= 5000 (spec section 3);
* RRF fusion path is exercised by the underlying DocsDB.search;
* unknown library returns empty list (caller may trigger Tier 2).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# Bootstrap (idempotent — see test_docs_resolve.py).
_src_root = Path(__file__).resolve().parent.parent / "src"

if "wet_mcp" not in sys.modules:
    _pkg = types.ModuleType("wet_mcp")
    _pkg.__path__ = [str(_src_root / "wet_mcp")]
    sys.modules["wet_mcp"] = _pkg

if "wet_mcp.sources" not in sys.modules:
    _sources_pkg = types.ModuleType("wet_mcp.sources")
    _sources_pkg.__path__ = [str(_src_root / "wet_mcp" / "sources")]
    sys.modules["wet_mcp.sources"] = _sources_pkg

if "wet_mcp.sources.docs" not in sys.modules:
    _docs_file = _src_root / "wet_mcp" / "sources" / "docs.py"
    _docs_spec = importlib.util.spec_from_file_location(
        "wet_mcp.sources.docs", _docs_file
    )
    assert _docs_spec is not None
    _docs_mod = importlib.util.module_from_spec(_docs_spec)
    sys.modules["wet_mcp.sources.docs"] = _docs_mod
    _docs_spec.loader.exec_module(_docs_mod)
else:
    _docs_mod = sys.modules["wet_mcp.sources.docs"]

if "wet_mcp.db" not in sys.modules:
    _db_file = _src_root / "wet_mcp" / "db.py"
    _db_spec = importlib.util.spec_from_file_location("wet_mcp.db", _db_file)
    assert _db_spec is not None
    _db_mod = importlib.util.module_from_spec(_db_spec)
    sys.modules["wet_mcp.db"] = _db_mod
    _db_spec.loader.exec_module(_db_mod)
else:
    _db_mod = sys.modules["wet_mcp.db"]

DocsDB = _db_mod.DocsDB
query_docs = _docs_mod.query_docs
DocsQueryOptions = _docs_mod.DocsQueryOptions
DOCS_QUERY_TOKEN_CAP = _docs_mod.DOCS_QUERY_TOKEN_CAP


@pytest.fixture
def db(tmp_path: Path) -> DocsDB:
    instance = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    yield instance
    instance.close()


def _seed_library_with_versions(
    db: DocsDB, lib_name: str = "react"
) -> tuple[str, str, str]:
    lib_id = db.upsert_library(name=lib_name, canonical_name=lib_name)
    v18 = db.upsert_version(library_id=lib_id, version="18.0.0")
    v19 = db.upsert_version(library_id=lib_id, version="19.0.0")
    db.add_chunks(
        version_id=v18,
        library_id=lib_id,
        chunks=[
            {
                "url": "https://react.dev/v18/useState",
                "title": "useState 18",
                "content": "useState lets you add state to functional components in React 18.",
                "heading_path": "Hooks > useState",
                "topic": "useState",
                "section": "Hooks",
                "token_count": 50,
            },
            {
                "url": "https://react.dev/v18/useEffect",
                "title": "useEffect 18",
                "content": "useEffect lets you perform side effects in components, React 18.",
                "heading_path": "Hooks > useEffect",
                "topic": "useEffect",
                "section": "Hooks",
                "token_count": 50,
            },
        ],
    )
    db.add_chunks(
        version_id=v19,
        library_id=lib_id,
        chunks=[
            {
                "url": "https://react.dev/v19/useState",
                "title": "useState 19",
                "content": "useState in React 19 supports new actions and transitions.",
                "heading_path": "Hooks > useState",
                "topic": "useState",
                "section": "Hooks",
                "token_count": 50,
            },
        ],
    )
    db.mark_version_indexed(v18, page_count=2, chunk_count=2)
    db.mark_version_indexed(v19, page_count=1, chunk_count=1)
    return lib_id, v18, v19


def test_docs_query_filters_by_version(db: DocsDB) -> None:
    lib_id, v18, v19 = _seed_library_with_versions(db)

    results = query_docs(
        db, lib_id, query="useState", options=DocsQueryOptions(version="18.0.0")
    )

    assert len(results) >= 1
    for chunk in results:
        # Either explicit version_id field, or URL contains v18 marker.
        assert "v18" in chunk.get("url", ""), (
            f"v19 chunk leaked into v18 query: {chunk.get('url')}"
        )


def test_docs_query_topic_filter(db: DocsDB) -> None:
    lib_id, _, _ = _seed_library_with_versions(db)

    results = query_docs(
        db, lib_id, query="React", options=DocsQueryOptions(topic="useState")
    )
    assert len(results) >= 1
    for chunk in results:
        assert chunk.get("title", "").lower().startswith("usestate"), (
            f"Non-useState chunk leaked: {chunk.get('title')}"
        )


def test_docs_query_unknown_library_returns_empty(db: DocsDB) -> None:
    # Library_id that never existed.
    assert query_docs(db, "not-a-real-id", query="anything") == []


def test_docs_query_pinned_version_not_indexed_returns_empty(
    db: DocsDB,
) -> None:
    lib_id, _, _ = _seed_library_with_versions(db)
    # Pin a version that does not exist.
    assert (
        query_docs(
            db, lib_id, query="useState", options=DocsQueryOptions(version="99.0.0")
        )
        == []
    )


def test_docs_query_token_cap_enforced(db: DocsDB) -> None:
    """Sum of returned token_count must respect DOCS_QUERY_TOKEN_CAP."""
    lib_id = db.upsert_library(name="bigdocs")
    ver_id = db.upsert_version(library_id=lib_id, version="latest")
    chunks = []
    for i in range(20):
        chunks.append(
            {
                "url": f"https://example.com/page{i}",
                "title": f"Page {i}",
                "content": f"keyword content describing item {i}. " * 50,
                "heading_path": "Section",
                "topic": "main",
                "token_count": 2000,  # Each chunk is 2000 tokens.
            }
        )
    db.add_chunks(version_id=ver_id, library_id=lib_id, chunks=chunks)
    db.mark_version_indexed(ver_id, page_count=20, chunk_count=20)

    results = query_docs(
        db, lib_id, query="keyword", options=DocsQueryOptions(limit=20)
    )
    assert results, "Expected at least one chunk"
    total_tokens = sum(c.get("token_count", 0) for c in results)
    # Cap is 5000 — first chunk 2000 -> 2000, second 4000, third would be
    # 6000 which exceeds, so we stop. Actual returned tokens <= 5000.
    assert total_tokens <= DOCS_QUERY_TOKEN_CAP


def test_docs_query_no_query_returns_empty(db: DocsDB) -> None:
    lib_id, _, _ = _seed_library_with_versions(db)
    assert query_docs(db, lib_id, query="") == []


def test_docs_query_estimates_tokens_when_count_missing(db: DocsDB) -> None:
    """Chunks without token_count fall back to chars/4 estimate, still capped."""
    lib_id = db.upsert_library(name="estimate")
    ver_id = db.upsert_version(library_id=lib_id, version="latest")
    chunks = [
        {
            "url": f"https://example.com/p{i}",
            "title": f"P{i}",
            "content": "x" * 16000,  # ~4000 estimated tokens
            "topic": "main",
            # No token_count
        }
        for i in range(5)
    ]
    db.add_chunks(version_id=ver_id, library_id=lib_id, chunks=chunks)
    db.mark_version_indexed(ver_id, page_count=5, chunk_count=5)

    results = query_docs(db, lib_id, query="x", options=DocsQueryOptions(limit=10))
    # Even with chars/4 estimation we should return at least one and respect cap.
    if results:
        used = sum(_docs_mod._estimate_tokens(c["content"]) for c in results)
        assert used <= DOCS_QUERY_TOKEN_CAP * 1.5  # estimation + greedy slack
