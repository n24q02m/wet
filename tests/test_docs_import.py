"""``wet_mcp.docs_import`` — D1 SQL export → local docs.db rescue pipeline.

Synthetic exports use the old PK shape the real D1 ``--export`` produces
(plain CREATE TABLE + line INSERTs); the current-schema bootstrap in
``DocsDB`` is expected to upgrade it. Count assertions are the trust
anchor against silent truncation, so every test pins them exactly.
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from wet_mcp.docs_import import EXPECTED_LIBRARIES, EXPECTED_VERSIONS, import_docs

# ---------------------------------------------------------------------------
# synthetic D1 export builder
# ---------------------------------------------------------------------------


def _export_sql(
    *,
    n_libs: int = EXPECTED_LIBRARIES,
    n_vers: int = EXPECTED_VERSIONS,
    n_chunks: int = 3,
    with_identity_rows: bool = True,
) -> str:
    """A small but structurally faithful D1 export of the legacy docs store."""
    meta = (
        "INSERT INTO store_meta (key, value) VALUES "
        "('embedding_model', 'old-model');\n"
        "INSERT INTO store_meta (key, value) VALUES ('embedding_dims', '1536');\n"
        if with_identity_rows
        else ""
    )
    libs = "\n".join(
        f"INSERT INTO libraries (id, name, created_at, updated_at) "
        f"VALUES ('lib-{i}', 'lib{i}', 1.0, 1.0);"
        for i in range(n_libs)
    )
    vers = "\n".join(
        f"INSERT INTO versions (id, library_id, version) "
        f"VALUES ('ver-{i}', 'lib-{i % n_libs}', '1.0.{i}');"
        for i in range(n_vers)
    )
    chs = "\n".join(
        f"INSERT INTO doc_chunks (id, version_id, library_id, url, title, "
        f"chunk_index, content, heading_path, created_at) "
        f"VALUES ('ch-{i}', 'ver-{i % n_vers}', 'lib-0', 'https://x/{i}', "
        f"'t{i}', {i}, 'content {i}', 'a > b', 1.0);"
        for i in range(n_chunks)
    )
    return f"""PRAGMA defer_foreign_keys=TRUE;
CREATE TABLE store_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE libraries (
    id TEXT PRIMARY KEY, name TEXT NOT NULL,
    created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE versions (
    id TEXT PRIMARY KEY, library_id TEXT NOT NULL, version TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    UNIQUE(library_id, version)
);
CREATE TABLE doc_chunks (
    id TEXT PRIMARY KEY, version_id TEXT NOT NULL, library_id TEXT NOT NULL,
    url TEXT, title TEXT, chunk_index INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL, heading_path TEXT, created_at REAL NOT NULL
);
{meta}
{libs}
{vers}
{chs}
"""


def _write_export(tmp_path: Path, **kw) -> Path:
    export = tmp_path / "export.sql"
    export.write_text(_export_sql(**kw), encoding="utf-8")
    return export


def _store_meta_keys(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {row[0] for row in conn.execute("SELECT key FROM store_meta")}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


def test_import_materializes_export_and_strips_identity(tmp_path):
    """Happy path: counts asserted, FTS rebuilt 1:1, identity rows removed."""
    export = _write_export(tmp_path, n_chunks=3)
    target = tmp_path / "docs.db"

    result = import_docs(export, db_path=target, expected_chunks=3)

    assert result["chunks"] == 3
    assert result["libraries"] == EXPECTED_LIBRARIES
    assert result["versions"] == EXPECTED_VERSIONS
    assert result["fts_rows"] == 3
    assert result["db_path"] == str(target)
    assert result["elapsed_s"] >= 0
    # Both hygiene passes must leave NO embedding identity behind: the next
    # server open must treat every vector as pending re-embed.
    keys = _store_meta_keys(target)
    assert "embedding_model" not in keys
    assert "embedding_dims" not in keys


def test_import_refuses_nonempty_target_without_force(tmp_path):
    export = _write_export(tmp_path)
    target = tmp_path / "docs.db"
    import_docs(export, db_path=target, expected_chunks=3)

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        import_docs(export, db_path=target, expected_chunks=3)


def test_import_force_replaces_target_and_sidecars(tmp_path):
    """`--force` mirrors the operator flow: a fresh CLI process replaces a
    store written by a previous run (whose handles are long gone), stale
    WAL sidecar included. In-process force would race our own pooled
    connection, which no real CLI invocation ever sees."""
    export = _write_export(tmp_path, n_chunks=3)
    target = tmp_path / "docs.db"

    def run_import(**kw) -> subprocess.CompletedProcess:
        code = (
            "import json;from pathlib import Path;"
            "from wet_mcp.docs_import import import_docs;"
            f"r = import_docs(Path(r'{export}'), db_path=Path(r'{target}'),"
            f" expected_chunks=3, force={kw.get('force', False)});"
            "print(json.dumps({'chunks': r['chunks'],"
            " 'libraries': r['libraries'], 'fts_rows': r['fts_rows']}))"
        )
        return subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=180
        )

    first = run_import()
    assert first.returncode == 0, first.stderr
    # A stale WAL sidecar from a "crashed" run must die with the db.
    Path(str(target) + "-wal").write_bytes(b"stale")

    second = run_import(force=True)
    assert second.returncode == 0, second.stderr
    payload = json.loads(second.stdout.strip().splitlines()[-1])
    assert payload == {"chunks": 3, "libraries": EXPECTED_LIBRARIES, "fts_rows": 3}
    assert not Path(str(target) + "-wal").exists()


def test_import_missing_export_raises_filenotfound(tmp_path):
    with pytest.raises(FileNotFoundError):
        import_docs(tmp_path / "absent.sql", db_path=tmp_path / "docs.db")


def test_import_chunk_count_mismatch_names_the_override(tmp_path):
    export = _write_export(tmp_path, n_chunks=3)
    with pytest.raises(RuntimeError, match="--expected-chunks"):
        import_docs(export, db_path=tmp_path / "docs.db", expected_chunks=99999)


def test_import_library_and_version_counts_stay_hard(tmp_path):
    # Libraries/versions are not overridable: a truncated export must fail.
    export = _write_export(tmp_path, n_libs=13)
    with pytest.raises(RuntimeError, match="libraries=13"):
        import_docs(export, db_path=tmp_path / "a.db", expected_chunks=3)

    export = _write_export(tmp_path, n_vers=7)
    with pytest.raises(RuntimeError, match="versions=7"):
        import_docs(export, db_path=tmp_path / "b.db", expected_chunks=3)


def test_import_skip_fts_leaves_index_unbuilt(tmp_path):
    export = _write_export(tmp_path, n_chunks=3)
    target = tmp_path / "docs.db"

    result = import_docs(export, db_path=target, expected_chunks=3, skip_fts=True)

    assert result["fts_rows"] is None
    # NOTE: `SELECT COUNT(*)` on an external-content FTS5 table just mirrors
    # the content table, so it proves nothing about index state here — the
    # contract under test is the `(skipped)` receipt, not the index.


# ---------------------------------------------------------------------------
# CLI handler end-to-end (real import_docs, no mocks)
# ---------------------------------------------------------------------------


def test_cli_docs_import_end_to_end(tmp_path, capsys):
    from wet_mcp import cli

    export = _write_export(tmp_path, n_chunks=3)
    target = tmp_path / "docs.db"

    rc = cli.main(
        [
            "docs",
            "import",
            str(export),
            "--db",
            str(target),
            "--expected-chunks",
            "3",
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "docs import complete:" in out
    assert "chunks:     3" in out
    assert f"libraries:  {EXPECTED_LIBRARIES}" in out
