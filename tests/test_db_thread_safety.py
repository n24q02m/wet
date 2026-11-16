"""``DocsDB`` shares one SQLite connection across threads, so every use holds its lock.

The server keeps a single ``DocsDB`` whose ``check_same_thread=False``
connection is reached from ``asyncio.to_thread`` workers and from the event
loop thread at once. Python's ``sqlite3`` leaves serializing a shared
connection to the caller (``PRAGMA busy_timeout`` only arbitrates between
separate connections), so concurrent tool calls used to interleave statements
and transactions on that one connection: ``InterfaceError`` /
``OperationalError`` in one thread, or one thread's commit/rollback closing
another thread's half-done transaction.
"""

from __future__ import annotations

import ast
import sqlite3
import sys
import threading
from pathlib import Path

from wet.db import DocsDB

THREADS = 8
ROUNDS = 40
CHUNKS_PER_ROUND = 3
SRC = Path(__file__).resolve().parents[1] / "src" / "wet"


def _hammer(db: DocsDB) -> list[str]:
    """Run THREADS writer/reader threads against ``db``; return every error."""
    errors: list[str] = []
    guard = threading.Lock()
    start = threading.Barrier(THREADS)

    def work(tid: int) -> None:
        start.wait(timeout=10)
        for rnd in range(ROUNDS):
            try:
                name = f"lib-{tid}-{rnd}"
                lib_id = db.upsert_library(name, docs_url=f"https://{name}.dev")
                ver_id = db.upsert_version(lib_id, "latest")
                db.add_chunks(
                    ver_id,
                    lib_id,
                    [
                        {
                            "url": f"https://{name}.dev/page",
                            "title": f"{name} guide",
                            "content": f"alpha beta gamma {tid} {rnd} part {i}",
                            "chunk_index": i,
                        }
                        for i in range(CHUNKS_PER_ROUND)
                    ],
                )
                db.mark_version_indexed(ver_id, 1, CHUNKS_PER_ROUND)
                db.set_index_state(ver_id, "done")
                db.search("alpha beta", limit=5)
                db.stats()
                db.get_library(name)
                db.index_status(limit=5)
            except BaseException as exc:  # every thread failure surfaces in the result
                with guard:
                    errors.append(f"thread {tid} round {rnd}: {exc!r}")
                return

    threads = [threading.Thread(target=work, args=(t,)) for t in range(THREADS)]
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
    finally:
        sys.setswitchinterval(previous)
    assert not any(thread.is_alive() for thread in threads), "worker thread hung"
    return errors


def test_concurrent_writes_and_reads_share_one_connection_safely(tmp_path: Path):
    db_path = tmp_path / "docs.db"
    db = DocsDB(db_path, embedding_dims=0)
    try:
        errors = _hammer(db)
    finally:
        db.close()

    assert errors == []
    # Count through an independent connection: every committed write must be
    # on disk, none lost to another thread's transaction handling.
    conn = sqlite3.connect(str(db_path))
    try:
        expected = THREADS * ROUNDS
        assert conn.execute("SELECT COUNT(*) FROM libraries").fetchone()[0] == expected
        assert conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0] == expected
        assert (
            conn.execute("SELECT COUNT(*) FROM doc_chunks").fetchone()[0]
            == expected * CHUNKS_PER_ROUND
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM versions "
                "WHERE status = 'indexed' AND index_state = 'done'"
            ).fetchone()[0]
            == expected
        )
    finally:
        conn.close()


def _unlocked_conn_uses(cls: ast.ClassDef) -> list[str]:
    """``self._conn`` uses in ``cls`` that are not lexically inside ``with self._lock``."""
    unlocked: list[str] = []

    def holds_lock(node: ast.With) -> bool:
        return any(
            isinstance(item.context_expr, ast.Attribute)
            and item.context_expr.attr == "_lock"
            for item in node.items
        )

    def visit(node: ast.AST, locked: bool, where: str) -> None:
        # A nested function or lambda runs later, outside the enclosing hold.
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            where = getattr(node, "name", where)
            locked = False
        if isinstance(node, ast.With) and holds_lock(node):
            locked = True
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "_conn"
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and not locked
        ):
            unlocked.append(f"{where}:{node.lineno}")
        for child in ast.iter_child_nodes(node):
            visit(child, locked, where)

    visit(cls, False, cls.name)
    return unlocked


def test_every_docsdb_connection_access_holds_the_lock():
    """Static guard: ``DocsDB`` touches ``self._conn`` only inside ``with self._lock``."""
    tree = ast.parse((SRC / "db.py").read_text(encoding="utf-8"))
    docs_db = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DocsDB"
    )
    assert _unlocked_conn_uses(docs_db) == []


def test_no_module_reaches_into_a_shared_connection():
    """Only the classes that own a shared connection may touch ``._conn``.

    Everything else goes through the locked API (``DocsDB.connection()`` for
    the maintenance paths), so no statement can bypass the lock.
    """
    owners = {SRC / "db.py", SRC / "cache.py"}
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path in owners:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders.extend(
            f"{path.relative_to(SRC).as_posix()}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "_conn"
        )
    assert offenders == []
