"""Host-side docs re-embed: backfill vectors for chunks missing them.

After ``docs_import`` the imported store has rows in ``doc_chunks`` but (by
design) an empty/absent ``doc_chunks_vec`` table and no embedding identity in
``store_meta``. This module resolves the ``[models.embed]`` cell from the
instance config, batches the missing chunks through the OpenAI-spec embeddings
endpoint, stores the vectors through the same DocsDB internals the indexer
uses, and re-stamps the embedding identity so the B2 guard accepts the store
on the next server open.

Rowid/id mapping (verified against db.py): ``doc_chunks_vec`` is a sqlite-vec
``vec0`` table declared as ``id TEXT PRIMARY KEY, embedding float[dims]`` —
its ``id`` is the ``doc_chunks.id`` text key (uuid hex), NOT a rowid mirror.
The miss query is therefore an anti-join on that id column.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from loguru import logger

PENDING_REASON = (
    "no [models.embed] api_key configured (set api_key or HULL_EMBED_API_KEY "
    "env; default route = OpenRouter voyage-4-lite)"
)

_PROGRESS_EVERY = 20  # batches between progress logs


def _embedding_identity(cell) -> str:
    """Identity string stamped into store_meta.embedding_model.

    The server-side ``make_docs_db`` lane must stamp the SAME string for the
    B2 guard to accept this store: ``openai-spec:<[models.embed].model>``.
    """
    return f"openai-spec:{cell.model}"


def _open_docs_db(db_path: Path, dims: int):
    """Open the store with the dims guard only (model compared post-stamp)."""
    from wet_mcp.db import DocsDB

    return DocsDB(db_path, embedding_dims=dims, model_identity="")


def _open_read_conn(target: Path) -> sqlite3.Connection:
    """Read-only side connection. The vec0 virtual table needs the sqlite-vec
    extension loaded on EVERY connection that touches it — a plain connection
    cannot even SELECT from doc_chunks_vec."""
    conn = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception as exc:  # vec queries below will fail loudly if unusable
        logger.warning(f"sqlite-vec unavailable on read connection: {exc}")
    return conn


def _missing_chunks(
    read_conn: sqlite3.Connection,
    vec_ids: set[str],
    limit: int | None,
) -> list[tuple[str, str]]:
    """Chunk (id, content) pairs whose id has no vector row yet."""
    missing: list[tuple[str, str]] = []
    cursor = read_conn.execute("SELECT id, content FROM doc_chunks ORDER BY rowid")
    for chunk_id, content in cursor:
        if chunk_id not in vec_ids:
            missing.append((chunk_id, content))
            if limit is not None and len(missing) >= limit:
                break
    return missing


def _vec_ids(read_conn: sqlite3.Connection) -> set[str]:
    return {
        row[0] for row in read_conn.execute("SELECT id FROM doc_chunks_vec")
    }


def _stamp_identity(db, dims: int, identity: str) -> None:
    """Write the embedding identity the guard expects on the next open."""
    db._conn.execute(
        "INSERT OR REPLACE INTO store_meta (key, value) VALUES (?, ?)",
        ("embedding_dims", str(int(dims))),
    )
    db._conn.execute(
        "INSERT OR REPLACE INTO store_meta (key, value) VALUES (?, ?)",
        ("embedding_model", identity),
    )
    db._conn.commit()


async def reembed(
    db_path: Path | None = None,
    *,
    batch_size: int = 64,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Backfill missing doc-chunk vectors. Returns a status dict.

    ``status``: ``pending`` (embed cell unconfigured), ``error`` (store not
    usable for vectors), ``dry-run``, or ``ok``.
    """
    from wet_mcp.config import settings
    from wet_mcp.runtime import cell_configured, model_cell, provider_client

    if not cell_configured("embed"):
        return {"status": "pending", "reason": PENDING_REASON}

    cell = model_cell("embed")
    identity = _embedding_identity(cell)
    dims = settings.embedding_dims or 768  # runtime.DEFAULT_EMBEDDING_DIMS
    target = Path(db_path) if db_path is not None else settings.get_db_path()
    if not target.exists():
        return {
            "status": "error",
            "reason": f"no docs db at {target} (run `wet docs import` first)",
        }
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")

    db = _open_docs_db(target, dims)
    try:
        has_vec_table = db._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='doc_chunks_vec'"
        ).fetchone() is not None
        if not has_vec_table:
            return {
                "status": "error",
                "reason": (
                    "doc_chunks_vec table does not exist in "
                    f"{target} (sqlite-vec unavailable?); cannot store vectors"
                ),
            }

        read_conn = _open_read_conn(target)
        try:
            vec_ids = _vec_ids(read_conn)
            missing = _missing_chunks(read_conn, vec_ids, limit)
            total_chunks = read_conn.execute(
                "SELECT COUNT(*) FROM doc_chunks"
            ).fetchone()[0]
        finally:
            read_conn.close()

        already = len(vec_ids)
        base = {
            "model": identity,
            "dims": dims,
            "db_path": str(target),
            "chunks_total": total_chunks,
            "vectors_present": already,
            "missing": len(missing),
        }
        if dry_run:
            return {
                "status": "dry-run",
                "embedded": 0,
                "remaining": len(missing),
                **base,
            }

        if not missing:
            # Nothing to embed; make sure the identity is stamped so the
            # guard does not treat present vectors as orphaned.
            _stamp_identity(db, dims, identity)
            return {
                "status": "ok",
                "embedded": 0,
                "remaining": 0,
                **base,
            }

        client = provider_client("embed")
        embedded = 0
        for start in range(0, len(missing), batch_size):
            batch = missing[start : start + batch_size]
            batch_ids = [chunk_id for chunk_id, _ in batch]
            embeddings = await client.embeddings(
                [content for _, content in batch],
                dimensions=dims if dims else None,
            )
            # Same internals the indexer uses; rolls back + raises on failure.
            db._add_chunk_vectors(batch_ids, embeddings)
            db._conn.commit()
            embedded += len(batch_ids)
            if (start // batch_size + 1) % _PROGRESS_EVERY == 0:
                logger.info(
                    f"reembed: {embedded}/{len(missing)} chunks embedded "
                    f"(model={identity}, dims={dims})"
                )

        read_conn = _open_read_conn(target)
        try:
            vec_ids_after = _vec_ids(read_conn)
            remaining = sum(
                1
                for (chunk_id,) in read_conn.execute("SELECT id FROM doc_chunks")
                if chunk_id not in vec_ids_after
            )
        finally:
            read_conn.close()
        _stamp_identity(db, dims, identity)
        logger.info(
            f"reembed done: embedded={embedded} remaining={remaining} "
            f"identity={identity} dims={dims}"
        )
        return {
            "status": "ok",
            "embedded": embedded,
            "remaining": remaining,
            **base,
        }
    finally:
        db._conn.close()


def main() -> int:  # pragma: no cover - manual repair entry
    result = asyncio.run(reembed())
    logger.info(result)
    return 0 if result.get("status") in ("ok", "dry-run") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
