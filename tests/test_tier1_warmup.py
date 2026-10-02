"""Tests for Tier 1 warmup — metadata-only seeding + freshness window."""

from __future__ import annotations

import importlib.util
import sys
import time
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

if "wet_mcp.sources.tier1_warmup" not in sys.modules:
    _tw_file = _src_root / "wet_mcp" / "sources" / "tier1_warmup.py"
    _tw_spec = importlib.util.spec_from_file_location(
        "wet_mcp.sources.tier1_warmup", _tw_file
    )
    assert _tw_spec is not None
    _tw_mod = importlib.util.module_from_spec(_tw_spec)
    sys.modules["wet_mcp.sources.tier1_warmup"] = _tw_mod
    _tw_spec.loader.exec_module(_tw_mod)
else:
    _tw_mod = sys.modules["wet_mcp.sources.tier1_warmup"]

DocsDB = _db_mod.DocsDB
maybe_warm = _tw_mod.maybe_warm


@pytest.fixture
def db(tmp_path: Path) -> DocsDB:
    instance = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    yield instance
    instance.close()


def test_tier1_warmup_seeds_libraries_metadata(db: DocsDB) -> None:
    """Fresh DB → maybe_warm seeds every Tier 1 entry with tier=1."""
    summary = maybe_warm(db)
    assert summary["seeded"] >= 1
    assert summary["total"] == summary["seeded"] + summary["skipped_fresh"]

    # Spot check — react should be present with tier=1 + homepage.
    react = db.get_library("react")
    assert react is not None
    assert react["tier"] == 1
    assert react["homepage"] == "https://react.dev"
    assert react["github_url"] == "https://github.com/facebook/react"


def test_tier1_warmup_idempotent(db: DocsDB) -> None:
    """Second call within freshness window skips libraries already seeded."""
    first = maybe_warm(db)
    assert first["seeded"] > 0

    second = maybe_warm(db)
    assert second["skipped_fresh"] > 0
    # Re-seeded count is 0 because nothing aged out.
    assert second["seeded"] == 0


def test_tier1_warmup_force_reseeds(db: DocsDB) -> None:
    """force=True bypasses the freshness check."""
    maybe_warm(db)
    second = maybe_warm(db, force=True)
    assert second["seeded"] > 0


def test_tier1_warmup_re_seeds_when_stale(db: DocsDB) -> None:
    """Library with metadata_seeded_at older than 7 days is re-seeded."""
    maybe_warm(db)

    # Manually back-date react's metadata_seeded_at by 10 days.
    stale_ts = time.time() - (10 * 24 * 60 * 60)
    db._conn.execute(
        "UPDATE libraries SET metadata_seeded_at = ? WHERE name = ?",
        (stale_ts, "react"),
    )
    db._conn.commit()

    summary = maybe_warm(db)
    assert summary["seeded"] >= 1


def test_tier1_warmup_does_not_stamp_last_indexed_at(db: DocsDB) -> None:
    """Metadata-only seeding must not claim the libraries are indexed.

    ``last_indexed_at`` belongs to ``mark_library_indexed`` — the only
    writer that knows chunks actually landed. The warmup records its own
    progress in ``metadata_seeded_at`` instead, so a seeded-but-unindexed
    DB is distinguishable from an indexed one.
    """
    maybe_warm(db)

    assert (
        db._conn.execute(
            "SELECT COUNT(*) FROM libraries WHERE last_indexed_at IS NOT NULL"
        ).fetchone()[0]
        == 0
    )
    assert (
        db._conn.execute(
            "SELECT COUNT(*) FROM libraries WHERE metadata_seeded_at IS NOT NULL"
        ).fetchone()[0]
        >= 50
    )
    # The seed writes no versions and no chunks — that is the point.
    assert db._conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0] == 0
    assert db._conn.execute("SELECT COUNT(*) FROM doc_chunks").fetchone()[0] == 0


def test_tier1_warmup_freshness_gate_ignores_last_indexed_at(db: DocsDB) -> None:
    """A fresh last_indexed_at must not satisfy the seed freshness gate.

    Pre-fix the warmup's own ``upsert_library`` write stamped
    ``last_indexed_at``, so the gate was satisfied by the very write it was
    supposed to guard.
    """
    maybe_warm(db)

    stale_ts = time.time() - (10 * 24 * 60 * 60)
    db._conn.execute(
        "UPDATE libraries SET metadata_seeded_at = ?, last_indexed_at = ? "
        "WHERE name = ?",
        (stale_ts, time.time(), "react"),
    )
    db._conn.commit()

    assert maybe_warm(db)["seeded"] == 1


def test_tier1_warmup_total_matches_fixture(db: DocsDB) -> None:
    """Sanity: the bundled fixture exposes at least 50 libraries."""
    summary = maybe_warm(db)
    assert summary["total"] >= 50


def test_tier1_warmup_empty_payload_returns_zero(db: DocsDB, monkeypatch) -> None:
    """If _load_tier1_payload returns no libraries, maybe_warm short-circuits."""
    monkeypatch.setattr(_tw_mod, "_load_tier1_payload", lambda: {"libraries": []})
    summary = maybe_warm(db)
    assert summary == {"total": 0, "skipped_fresh": 0, "seeded": 0}


def test_load_tier1_payload_missing_resource_returns_empty() -> None:
    """ModuleNotFoundError / FileNotFoundError fall back to empty payload."""

    def _broken(*args, **kwargs):
        raise ModuleNotFoundError("simulated missing data package")

    original = _tw_mod.files
    try:
        _tw_mod.files = _broken
        result = _tw_mod._load_tier1_payload()
        assert result == {"libraries": []}
    finally:
        _tw_mod.files = original


def test_tier1_warmup_handles_upsert_error(db: DocsDB, monkeypatch) -> None:
    """If upsert_library raises for one entry, the loop continues."""
    monkeypatch.setattr(
        _tw_mod,
        "_load_tier1_payload",
        lambda: {
            "libraries": [
                {"id": "good-lib", "canonical_name": "Good", "tier": 1},
                {"id": "broken-lib", "canonical_name": "Broken", "tier": 1},
            ]
        },
    )
    original = db.upsert_library

    def _flaky(name, **kwargs):
        if name == "broken-lib":
            raise RuntimeError("simulated DB failure")
        return original(name=name, **kwargs)

    monkeypatch.setattr(db, "upsert_library", _flaky)
    summary = maybe_warm(db)
    # good-lib seeded, broken-lib raised -> seeded = 1.
    assert summary["seeded"] == 1
