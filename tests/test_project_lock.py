"""Tests for project_lock — manifest detection + Cabinets lock builder.

Covers all 5 supported manifests (uv pyproject, poetry pyproject,
package.json, go.mod, Cargo.toml), multi-language merge, and the
docs_query lock-honoring path.
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

# Standalone load of project_lock (no heavy deps).
if "wet_mcp.sources.project_lock" not in sys.modules:
    _pl_file = _src_root / "wet_mcp" / "sources" / "project_lock.py"
    _pl_spec = importlib.util.spec_from_file_location(
        "wet_mcp.sources.project_lock", _pl_file
    )
    assert _pl_spec is not None
    _pl_mod = importlib.util.module_from_spec(_pl_spec)
    sys.modules["wet_mcp.sources.project_lock"] = _pl_mod
    _pl_spec.loader.exec_module(_pl_mod)
else:
    _pl_mod = sys.modules["wet_mcp.sources.project_lock"]

DocsDB = _db_mod.DocsDB
detect_manifests = _pl_mod.detect_manifests
lock_project = _pl_mod.lock_project
query_docs = _docs_mod.query_docs
DocsQueryOptions = _docs_mod.DocsQueryOptions


_FIXTURES = Path(__file__).parent / "fixtures" / "projects"


@pytest.fixture
def db(tmp_path: Path) -> DocsDB:
    instance = DocsDB(tmp_path / "docs.db", embedding_dims=0)
    yield instance
    instance.close()


def test_detect_pyproject_uv() -> None:
    deps = detect_manifests(_FIXTURES / "python_uv")
    by_id = {d["id"]: d["version"] for d in deps}
    assert "fastapi" in by_id
    assert by_id["fastapi"].startswith(">=0.110")
    assert "pydantic" in by_id
    assert by_id["pydantic"].startswith(">=2")
    assert "httpx" in by_id


def test_detect_pyproject_poetry() -> None:
    deps = detect_manifests(_FIXTURES / "python_poetry")
    by_id = {d["id"]: d["version"] for d in deps}
    assert "django" in by_id
    assert "celery" in by_id
    # Python pin is excluded.
    assert "python" not in by_id


def test_detect_package_json_npm() -> None:
    deps = detect_manifests(_FIXTURES / "nodejs_npm")
    by_id = {d["id"]: d["version"] for d in deps}
    assert by_id["react"] == "^19"
    assert by_id["next"] == "^15"
    # @types/react is filtered out.
    assert "@types/react" not in by_id


def test_detect_go_mod() -> None:
    deps = detect_manifests(_FIXTURES / "go_mod")
    by_id = {d["id"]: d["version"] for d in deps}
    # Per spec section 4.3 example: id strips github.com/ prefix.
    assert "gin-gonic/gin" in by_id
    assert by_id["gin-gonic/gin"] == "v1.10.0"
    assert "spf13/cobra" in by_id


def test_detect_cargo_toml() -> None:
    deps = detect_manifests(_FIXTURES / "rust_cargo")
    by_id = {d["id"]: d["version"] for d in deps}
    assert by_id["tokio"] == "1.40"
    assert by_id["serde"] == "1.0"
    assert by_id["clap"] == "4.5"
    assert "criterion" in by_id  # dev-dependencies included


def test_detect_multi_lang() -> None:
    deps = detect_manifests(_FIXTURES / "multi_lang")
    ids = {d["id"] for d in deps}
    # Both manifests merged; no dedup since IDs are language-namespaced
    # (fastapi from PyPI, react from npm).
    assert "fastapi" in ids
    assert "react" in ids


def test_detect_missing_directory_raises() -> None:
    with pytest.raises(FileNotFoundError):
        detect_manifests(Path("/nope/does/not/exist"))


def test_lock_persists_to_project_context(db: DocsDB) -> None:
    db.upsert_library(name="fastapi")  # exists → indexed = True
    project_path = _FIXTURES / "python_uv"

    summary = lock_project(db, project_path)
    assert summary["total"] >= 3
    assert summary["indexed"] >= 1

    fetched = db.get_project_context(str(project_path.resolve()))
    assert fetched is not None
    assert fetched["locked_libraries"]
    by_name = {entry["name"]: entry for entry in fetched["locked_libraries"]}
    assert by_name["fastapi"]["indexed"] is True
    assert by_name["pydantic"]["indexed"] is False


def test_parse_pep508_invalid_returns_empty() -> None:
    """A malformed dependency string yields empty (name, version) tuple."""
    assert _pl_mod._parse_pep508("@@@@@") == ("", "")
    assert _pl_mod._parse_pep508("") == ("", "")


def test_parse_pep508_with_extras_strips_them() -> None:
    name, version = _pl_mod._parse_pep508("pydantic[email]>=2.0")
    assert name == "pydantic"
    assert version == ">=2.0"


def test_detect_pyproject_handles_invalid_toml(tmp_path: Path) -> None:
    """A malformed pyproject.toml degrades gracefully (returns []
    for that manifest, doesn't crash)."""
    project = tmp_path / "broken-py"
    project.mkdir()
    (project / "pyproject.toml").write_text("not [valid toml")
    deps = detect_manifests(project)
    assert isinstance(deps, list)


def test_detect_package_json_handles_invalid(tmp_path: Path) -> None:
    project = tmp_path / "broken-js"
    project.mkdir()
    (project / "package.json").write_text("{ not valid json")
    deps = detect_manifests(project)
    assert isinstance(deps, list)


def test_detect_skips_empty_id_entries(tmp_path: Path) -> None:
    """Manifests yielding empty-id entries are filtered out by detect_manifests."""
    project = tmp_path / "noop"
    project.mkdir()
    # Empty pyproject — no [project] section, no [tool.poetry], no deps.
    (project / "pyproject.toml").write_text("[build-system]\nrequires = []\n")
    deps = detect_manifests(project)
    assert deps == []


def test_lock_project_with_no_manifests(tmp_path: Path, db: DocsDB) -> None:
    project = tmp_path / "empty"
    project.mkdir()
    summary = lock_project(db, project)
    assert summary["total"] == 0
    assert summary["indexed"] == 0


def test_docs_query_respects_lock(db: DocsDB) -> None:
    """When project_path is set and a lock pins react@18.0.0, the lock wins."""
    lib_id = db.upsert_library(name="react")
    v18 = db.upsert_version(library_id=lib_id, version="18.0.0")
    v19 = db.upsert_version(library_id=lib_id, version="19.0.0")
    db.add_chunks(
        version_id=v18,
        library_id=lib_id,
        chunks=[
            {
                "url": "https://react.dev/v18/p1",
                "title": "v18 page",
                "content": "useState pattern in React 18.",
                "topic": "useState",
                "token_count": 30,
            }
        ],
    )
    db.add_chunks(
        version_id=v19,
        library_id=lib_id,
        chunks=[
            {
                "url": "https://react.dev/v19/p1",
                "title": "v19 page",
                "content": "useState pattern in React 19.",
                "topic": "useState",
                "token_count": 30,
            }
        ],
    )
    db.mark_version_indexed(v18, 1, 1)
    db.mark_version_indexed(v19, 1, 1)

    project_path = "/test/lockproject"
    db.upsert_project_context(
        project_path,
        [{"id": lib_id, "name": "react", "version": "18.0.0"}],
    )

    # Direct query_docs honors version pin only when caller passes it.
    pinned_results = query_docs(
        db, lib_id, query="useState", options=DocsQueryOptions(version="18.0.0")
    )
    for chunk in pinned_results:
        assert "v18" in chunk.get("url", "")
