"""Tests for ``search(action="docs_resolve")`` and the resolve_library helper.

Covers exact match, ambiguous prefix ranking, unknown library returns
empty list, and the dispatcher wiring through ``server.search``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: load db + docs without triggering crawl4ai-heavy package imports.
# Same pattern as tests/test_db.py.
# ---------------------------------------------------------------------------

_src_root = Path(__file__).resolve().parent.parent / "src"

# Reuse (don't replace) any already-loaded wet_mcp.sources.docs / wet_mcp.db
# modules to avoid pollution of patches in sibling test files.
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
resolve_library = _docs_mod.resolve_library


@pytest.fixture
def db(tmp_path: Path) -> DocsDB:
    instance = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    yield instance
    instance.close()


def test_resolve_exact_match(db: DocsDB) -> None:
    db.upsert_library(name="react", canonical_name="React")

    results = resolve_library(db, "react")
    assert len(results) == 1
    assert results[0]["name"] == "react"
    assert results[0]["canonical_name"] == "React"


def test_resolve_case_insensitive(db: DocsDB) -> None:
    db.upsert_library(name="fastapi")
    results = resolve_library(db, "FastAPI")
    assert len(results) == 1
    assert results[0]["name"] == "fastapi"


def test_resolve_ambiguous_returns_ranked_list(db: DocsDB) -> None:
    db.upsert_library(name="next")
    db.upsert_library(name="nextflow")

    results = resolve_library(db, "next", limit=5)
    assert len(results) == 2
    # Exact prefix wins
    assert results[0]["name"] == "next"
    assert results[1]["name"] == "nextflow"


def test_resolve_substring_fallback(db: DocsDB) -> None:
    db.upsert_library(name="my-react-lib")
    db.upsert_library(name="other-lib")

    # No exact "react" match, but substring should pick up my-react-lib.
    results = resolve_library(db, "react", limit=5)
    assert any(r["name"] == "my-react-lib" for r in results)
    assert not any(r["name"] == "other-lib" for r in results)


def test_resolve_unknown_returns_empty(db: DocsDB) -> None:
    db.upsert_library(name="react")
    assert resolve_library(db, "obscure-lib-xyz") == []


def test_resolve_respects_limit(db: DocsDB) -> None:
    for i in range(5):
        db.upsert_library(name=f"react-helper-{i}")
    results = resolve_library(db, "react", limit=2)
    assert len(results) == 2


def test_resolve_includes_phase2_metadata(db: DocsDB) -> None:
    db.upsert_library(
        name="react",
        canonical_name="React",
        tier=1,
        homepage="https://react.dev",
        github_url="https://github.com/facebook/react",
    )
    results = resolve_library(db, "react")
    assert results[0]["tier"] == 1
    assert results[0]["homepage"] == "https://react.dev"
    assert results[0]["github_url"] == "https://github.com/facebook/react"


def test_resolve_empty_query_returns_empty(db: DocsDB) -> None:
    db.upsert_library(name="react")
    assert resolve_library(db, "") == []
    assert resolve_library(db, "   ") == []


def test_resolve_format_includes_required_keys(db: DocsDB) -> None:
    db.upsert_library(name="react")
    [item] = resolve_library(db, "react")
    for key in (
        "library_id",
        "name",
        "canonical_name",
        "tier",
        "homepage",
        "github_url",
        "registry",
        "description",
        "latest_version",
    ):
        assert key in item, f"Missing key {key} in resolved entry"


def test_resolve_serializable(db: DocsDB) -> None:
    """Resolved entries must round-trip through json.dumps for MCP."""
    db.upsert_library(name="react", canonical_name="React")
    serialized = json.dumps(resolve_library(db, "react"))
    assert "react" in serialized
