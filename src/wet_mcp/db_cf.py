"""Cloudflare docs DB: relational + FTS5 on D1, vectors on Vectorize.

Public interface mirrors wet_mcp.db.DocsDB (upsert_library / upsert_version /
get_library / get_best_version / add_chunks / search) so server.py is polymorphic.
The ranking pipeline (tiered FTS5, bm25 weights 0/2/3/2, RRF k=60, quality boost,
URL diversity 2/url, adjacent prefetch) is REUSED from db.py, not reimplemented.
"""

from __future__ import annotations

import json
import time
import uuid

from loguru import logger
from mcp_core.storage.d1 import D1_MAX_BOUND_PARAMS, D1Backend
from mcp_core.storage.vectorize import VectorizeBackend

# Reuse the exact ranking helpers, the chunk-id generator and the column
# allowlist from the SQLite implementation -- both backends must mint identity
# and validate dynamic column names the same way.
from wet_mcp.db import (
    _LIBRARIES_COLUMNS,
    _build_fts_queries,
    _chunk_quality_score,
    new_chunk_id,
)

# Stamped onto every library row, exactly as db.py does it. `_search_cached_index`
# re-indexes any library whose stored value trails this constant, so a backend
# that does not write it can never serve a cached index (issue #1624).
from wet_mcp.sources.docs import DISCOVERY_VERSION


def _d1_param_batches(items: list, params_per_item: int):
    """Slice ``items`` so no single D1 statement binds more than D1's cap.

    D1's ceiling counts BOUND PARAMETERS, not rows. The cap itself is imported
    from ``mcp_core.storage.d1`` rather than restated here, so the read path
    and the write path (``D1Backend.executemany``, which derives its
    rows-per-INSERT the same way) can never drift apart on the number.

    Batching a multi-column key list by ROWS is what killed the deployed
    worker: 100 three-column keys bind 300 parameters, D1 answers
    ``D1_ERROR: too many SQL variables``, and the container dies mid-request so
    the client only sees "Server disconnected without sending a response".
    Dividing the cap by the per-item width means widening a key tuple shrinks
    the batch automatically instead of silently overflowing it.
    """
    per_batch = max(1, D1_MAX_BOUND_PARAMS // params_per_item)
    for i in range(0, len(items), per_batch):
        yield items[i : i + per_batch]


# Vectorize mutation batch size. The docs' "Maximum upsert batch size" is 1000
# (Workers) / 5000 (HTTP API) (developers.cloudflare.com/vectorize/platform/
# limits), but on the deployed wet worker (v3.15.1, 2026-09-18) a single
# deleteByIds of 1000 ids still died mid-request -- the container's httpx
# reported "Server disconnected without sending a response" -- while the SAME
# code path cleared a 1-chunk and a 382-chunk version fine (live bisect:
# typescript=1, fastapi=382, @modelcontextprotocol/sdk batch of 1000). The
# 1875-row chunk-id SELECT through d1.internal is suspect on the same grounds,
# so clear_version_chunks pages that read at this size too. 100 is the same
# batch unit the D1 parameter cap already imposes via _d1_param_batches, and
# 4-10x under the observed failure threshold.
_VECTORIZE_MUTATION_BATCH = 100


def _vectorize_mutation_batches(items: list) -> list[list]:
    """Slice a Vectorize mutation payload into <=_VECTORIZE_MUTATION_BATCH chunks."""
    return [
        items[i : i + _VECTORIZE_MUTATION_BATCH]
        for i in range(0, len(items), _VECTORIZE_MUTATION_BATCH)
    ]


class DocsDBCfBackend:
    def __init__(
        self, d1: D1Backend, vectorize: VectorizeBackend, embedding_dims: int = 768
    ) -> None:
        self._d1 = d1
        self._vec = vectorize
        self._embedding_dims = embedding_dims

    def stats(self) -> dict:
        """Return database statistics. Mirrors wet_mcp.db.DocsDB.stats over D1 so
        config(action="status") is polymorphic across the SQLite and CF backends."""
        lib_row = self._d1.fetchone("SELECT COUNT(*) AS n FROM libraries", [])
        chunk_row = self._d1.fetchone("SELECT COUNT(*) AS n FROM doc_chunks", [])
        return {
            "libraries": (lib_row or {}).get("n", 0),
            "chunks": (chunk_row or {}).get("n", 0),
            "vec_enabled": self._vec is not None,
        }

    # --- relational CRUD (parameterized D1) ---

    def upsert_library(
        self,
        name: str,
        docs_url: str | None = None,
        registry: str | None = None,
        description: str | None = None,
        tier: int | None = None,
        package_managers: list[str] | None = None,
        homepage: str | None = None,
        github_url: str | None = None,
        canonical_name: str | None = None,
    ) -> str:
        """Create or update a library. Returns library ID.

        Column-for-column mirror of ``wet_mcp.db.DocsDB.upsert_library`` over
        the ``libraries`` table in ``migrations/0001_init_wet.sql`` +
        ``0002_project_context.sql``. The signature is explicit rather than
        ``**extra`` on purpose: it used to swallow every keyword past
        ``docs_url`` and write none of them, so ``registry`` / ``description``
        from the docs index path and ``tier`` / ``canonical_name`` /
        ``homepage`` / ``github_url`` / ``package_managers`` from the Tier 1
        warmup all vanished, and the next column added would have vanished
        too. An unknown field must now raise TypeError, as it does on SQLite.

        ``discovery_version`` is stamped on BOTH paths. Insert-only stamping
        would leave every row already written at 0 re-indexing forever, since
        an existing library is only ever updated (issue #1624).

        ``last_indexed_at`` stays untouched here, matching DocsDB: writing
        metadata says nothing about whether chunks landed.
        """
        norm_name = name.lower().strip()
        now = time.time()
        pkg_json = (
            json.dumps(package_managers, ensure_ascii=False)
            if package_managers is not None
            else None
        )
        # Both stores key on the normalised name. Storing it raw meant a search
        # for "FastAPI" and one for "fastapi" minted two library rows on D1 and
        # indexed the same docs twice.
        optional = (
            ("docs_url", docs_url),
            ("registry", registry),
            ("description", description),
            ("canonical_name", canonical_name),
            ("homepage", homepage),
            ("github_url", github_url),
            ("package_managers", pkg_json),
            ("tier", None if tier is None else int(tier)),
        )

        existing = self.get_library(norm_name)
        if existing:
            # Mirrors DocsDB._update_library_inner: a field left None keeps its
            # stored value (assigning it unconditionally erased the docs URL of
            # an indexed library on any metadata-only re-upsert), while
            # discovery_version, name and updated_at are rewritten every time.
            #
            # `name` is rewritten for the same reason discovery_version is: the
            # UPDATE path, not the INSERT, is what repairs rows that are
            # already stored. A row written un-normalised by an older container
            # is healed in place here, so it keeps its id and its chunks stay
            # reachable instead of being orphaned behind a second row.
            sets = ["discovery_version = ?", "name = ?", "updated_at = ?"]
            params: list = [DISCOVERY_VERSION, norm_name, now]
            for col, value in optional:
                if value is not None:
                    sets.append(f"{col} = ?")
                    params.append(value)
            params.append(existing["id"])
            self._assert_library_columns(s.split("=")[0].strip() for s in sets)
            # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            self._d1.execute(
                "UPDATE libraries SET " + ", ".join(sets) + " WHERE id = ?",
                params,
            )
            return existing["id"]

        lib_id = str(uuid.uuid4())
        cols = ["id", "name", "discovery_version", "created_at", "updated_at"]
        vals: list = [lib_id, norm_name, DISCOVERY_VERSION, now, now]
        for col, value in optional:
            # canonical_name is the one field DocsDB writes even when absent:
            # it is the display label and defaults to the library's own name.
            if col == "canonical_name":
                value = value or norm_name
            if value is not None:
                cols.append(col)
                vals.append(value)
        self._assert_library_columns(cols)
        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        self._d1.execute(
            f"INSERT INTO libraries ({', '.join(cols)})"
            f" VALUES ({', '.join('?' * len(cols))})",
            vals,
        )
        return lib_id

    @staticmethod
    def _assert_library_columns(cols) -> None:
        """Gate dynamic column names against the same allowlist db.py uses."""
        for col in cols:
            if col not in _LIBRARIES_COLUMNS:
                raise ValueError(f"Unauthorized library column: {col}")

    def get_library(self, name: str) -> dict | None:
        """Get library by name. Normalises like ``DocsDB.get_library`` does.

        Unlike DocsDB, this falls back to normalising the STORED name on a
        miss. Normalising the lookup changes the key of a table that is
        already populated: a row an older container wrote as "FastAPI" would
        stop being found, the next upsert would mint a second row, and the
        first row's chunks would become unreachable. Losing an index that was
        built correctly is worse than the bug this fix exists for. DocsDB
        needs no such fallback -- its writer has always normalised, so no
        SQLite store can hold a raw name.

        The exact match runs first so the common case still uses
        ``idx_libraries_name``; the scan only happens when a library is
        genuinely absent or still un-normalised. ``upsert_library`` then
        rewrites the name in place, so each legacy row is repaired the first
        time it is touched and the scan stops being reachable for it.

        Measured on prod ``wet-docs`` before shipping: 0 of 10 library rows
        had a name differing from ``lower(trim(name))``, so this covers the
        mixed-version rollout window rather than a known-bad row.
        """
        norm_name = name.lower().strip()
        row = self._d1.fetchone("SELECT * FROM libraries WHERE name = ?", [norm_name])
        if row is None:
            row = self._d1.fetchone(
                "SELECT * FROM libraries WHERE lower(trim(name)) = ?", [norm_name]
            )
        return row

    def get_library_by_id(self, library_id: str) -> dict | None:
        """Get a library row by its stable identifier."""
        return self._d1.fetchone("SELECT * FROM libraries WHERE id = ?", [library_id])

    def find_libraries_by_prefix(self, name: str, limit: int = 20) -> list[dict]:
        """Return libraries whose names start with ``name``, alphabetically."""
        norm_name = name.lower().strip()
        if not norm_name or limit <= 0:
            return []
        return self._d1.fetchall(
            "SELECT * FROM libraries "
            "WHERE name LIKE ? AND name != ? "
            "ORDER BY length(name) ASC, name ASC LIMIT ?",
            [f"{norm_name}%", norm_name, limit],
        )

    def find_libraries_by_substring(self, name: str, limit: int = 20) -> list[dict]:
        """Return libraries containing ``name`` beyond a prefix match."""
        norm_name = name.lower().strip()
        if not norm_name or limit <= 0:
            return []
        return self._d1.fetchall(
            "SELECT * FROM libraries "
            "WHERE name LIKE ? AND name NOT LIKE ? AND name != ? "
            "ORDER BY length(name) ASC, name ASC LIMIT ?",
            [f"%{norm_name}%", f"{norm_name}%", norm_name, limit],
        )

    def upsert_version(
        self,
        library_id: str,
        version: str = "latest",
        docs_url: str | None = None,
    ) -> str:
        """Create or get version. Returns version ID.

        Signature and docs_url handling mirror wet_mcp.db.DocsDB.upsert_version:
        both production index call sites pass ``docs_url=``, and an existing row
        gets the new ``docs_url`` written back onto it (a missing one leaves the
        stored value alone).

        The existence check is its own direct, UNFILTERED lookup, exactly as
        ``DocsDB.upsert_version`` does it -- deliberately not
        ``get_best_version``, which only considers rows that reached
        ``status='indexed'``. Reusing it here would miss a ``pending`` row and
        INSERT a duplicate against ``UNIQUE(library_id, version)``.
        """
        existing = self._d1.fetchone(
            "SELECT id FROM versions WHERE library_id = ? AND version = ?",
            [library_id, version],
        )
        if existing:
            ver_id = existing["id"]
            if docs_url:
                self._d1.execute(
                    "UPDATE versions SET docs_url = ? WHERE id = ?",
                    [docs_url, ver_id],
                )
            return ver_id
        ver_id = str(uuid.uuid4())
        self._d1.execute(
            "INSERT INTO versions (id, library_id, version, docs_url) VALUES (?,?,?,?)",
            [ver_id, library_id, version, docs_url],
        )
        return ver_id

    def get_best_version(
        self, library_id: str, target: str | None = None
    ) -> dict | None:
        """Get the best SERVABLE version for a library. Mirrors DocsDB.

        "Best" means indexed. A version that exists but never finished
        indexing has no chunks behind it, so returning it tells the caller
        the library is unservable when another version could in fact have
        answered: ``_search_cached_index`` reads ``chunk_count`` off this row
        and re-indexes when it is 0, which on cf-d1 meant asking for an
        explicit ``version=`` that happened to be mid-index re-indexed the
        library instead of serving the copy already on disk.

        So both branches filter ``status = 'indexed'``, and an exact target
        that is not indexed falls through to the newest version that is --
        the same two-step DocsDB.get_best_version performs.

        Callers that need a row REGARDLESS of status (``upsert_version``'s
        existence check) must query directly; that is not what "best" means.
        """
        if target:
            row = self._d1.fetchone(
                "SELECT * FROM versions WHERE library_id = ? AND version = ?"
                " AND status = 'indexed'",
                [library_id, target],
            )
            if row:
                return row
        return self._d1.fetchone(
            "SELECT * FROM versions WHERE library_id = ? AND status = 'indexed'"
            " ORDER BY indexed_at DESC LIMIT 1",
            [library_id],
        )

    def add_chunks(
        self,
        version_id: str,
        library_id: str,
        chunks: list[dict],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        now = time.time()
        # Minted here, not read off the chunk: the chunkers in sources.docs emit
        # content only and server._background_index_and_search forwards their
        # dicts untouched, so a c["id"] subscript raised KeyError on every cf-d1
        # index. new_chunk_id() is the same generator DocsDB._prepare_chunk_rows
        # uses, so the two stores agree on id shape. Generated once and reused
        # below -- the vector must carry its own chunk row's id.
        chunk_ids = [new_chunk_id() for _ in chunks]
        # Fallbacks are copied from DocsDB._prepare_chunk_rows, not chosen here:
        # `content` is the only key add_chunks requires of a caller, so every
        # other column is a default that both stores have to pick the same way
        # or the same batch lands as two different documents. chunk_index in
        # particular defaults to the chunk's position in the batch -- a constant
        # 0 flattens the batch, and _build_results_cf then looks for a hit's
        # neighbours at index +/-1 and never finds them.
        rows = [
            [
                cid,
                version_id,
                library_id,
                c.get("url", ""),
                c.get("title", ""),
                c.get("chunk_index", i),
                c["content"],
                c.get("heading_path", ""),
                c.get("section"),
                c.get("topic"),
                c.get("content_hash"),
                c.get("token_count"),
                now,
            ]
            for i, (cid, c) in enumerate(zip(chunk_ids, chunks, strict=True))
        ]
        # section/topic/content_hash/token_count exist in migrations/0001_init_wet.sql
        # and search() reads them back, so persist them like DocsDB.add_chunks does.
        self._d1.executemany(
            "INSERT INTO doc_chunks (id, version_id, library_id, url, title, chunk_index,"
            " content, heading_path, section, topic, content_hash, token_count,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        # One upsert per _VECTORIZE_MUTATION_BATCH slice -- see the constant's
        # note: the documented 1000 cap failed live for deleteByIds, and the
        # unbatched call dies the same mid-request death as the delete path.
        if embeddings:
            vectors = [
                {
                    "id": cid,
                    "values": emb,
                    "metadata": {
                        "library_id": library_id,
                        "version_id": version_id,
                        "url": c.get("url", ""),
                        "chunk_index": c.get("chunk_index", i),
                    },
                }
                for i, (cid, c, emb) in enumerate(
                    zip(chunk_ids, chunks, embeddings, strict=False)
                )
            ]
            for batch in _vectorize_mutation_batches(vectors):
                self._vec.upsert(batch)
            # Upsert is eventual; block until index is ready so an immediate
            # search() doesn't return empty (mirrors spec risk mitigation).
            self._vec.wait_until_indexed()

    def clear_version_chunks(self, version_id: str) -> int:
        """Drop a version's chunks from D1 and their vectors from Vectorize.

        Vectors go FIRST, and the delete is not error-suppressed. If Vectorize
        refuses, the D1 rows stay as well, leaving the store merely stale --
        the alternative ordering leaves vectors whose chunk row is gone, and
        those come back from search() as hits with no content behind them.

        Returns the number of chunks removed, counted from the ids actually
        read (the D1 HTTP contract returns rows, not a rowcount).
        """
        # Paged at the mutation batch size: a version holding thousands of
        # chunks turns this into a multi-tens-of-KB response over the
        # d1.internal interception route, which dies at roughly the same
        # payload sizes observed for deleteByIds (see _VECTORIZE_MUTATION_BATCH).
        ids: list[str] = []
        offset = 0
        while True:
            rows = self._d1.execute(
                "SELECT id FROM doc_chunks WHERE version_id = ?"
                " ORDER BY id LIMIT ? OFFSET ?",
                [version_id, _VECTORIZE_MUTATION_BATCH, offset],
            )
            page = [r["id"] for r in rows]
            ids.extend(page)
            if len(page) < _VECTORIZE_MUTATION_BATCH:
                break
            offset += _VECTORIZE_MUTATION_BATCH
        if not ids:
            return 0
        # One deleteByIds per batch: a single call over a bigger version
        # (1875 ids) exceeds what the route/binding accepts and dies
        # mid-request before the D1 rows below are ever touched.
        for batch in _vectorize_mutation_batches(ids):
            self._vec.delete_by_ids(batch)
        self._d1.execute("DELETE FROM doc_chunks WHERE version_id = ?", [version_id])
        return len(ids)

    # --- index bookkeeping ---

    def mark_version_indexed(
        self, version_id: str, page_count: int, chunk_count: int
    ) -> None:
        """Mark a version indexed with its counts.

        The absence of exactly this method is what made cf-d1 lose data: the
        indexer wrote chunks, raised AttributeError here inside a log-only
        `except Exception`, and left the version at status='pending' so the
        next request indexed it all over again.
        """
        self._d1.execute(
            "UPDATE versions SET status = 'indexed', indexed_at = ?,"
            " page_count = ?, chunk_count = ? WHERE id = ?",
            [time.time(), page_count, chunk_count, version_id],
        )

    def reset_version_index(self, version_id: str) -> None:
        """Mark a cleared version as NOT indexed. Cf twin of DocsDB.reset_version_index:
        a cleared version with zero chunks must stop resolving as servable, or
        the docs_query lazy-ingest gate (latest_version is None) never fires."""
        self._d1.execute(
            "UPDATE versions SET status = 'pending', indexed_at = NULL,"
            " page_count = 0, chunk_count = 0 WHERE id = ?",
            [version_id],
        )

    def set_index_state(
        self, version_id: str, state: str, error: str | None = None
    ) -> None:
        """Record an indexing attempt's outcome on D1.

        This is the CF half of the durability fix: a background indexer
        running inside the Cloudflare container writes its logs to a stderr
        nothing collects, so D1 is the only place a failure can be read from
        outside the container. Four bound parameters, well inside D1's
        per-statement parameter ceiling -- and fixed, not scaled by row count.
        """
        self._d1.execute(
            "UPDATE versions SET index_state = ?, index_error = ?,"
            " index_state_at = ? WHERE id = ?",
            [state, error, time.time(), version_id],
        )

    def get_index_state(self, version_id: str) -> dict | None:
        """Return the indexing-attempt record for a version, or None."""
        row = self._d1.fetchone(
            "SELECT id, library_id, version, index_state, index_error,"
            " index_state_at, page_count, chunk_count FROM versions WHERE id = ?",
            [version_id],
        )
        if row is None or row.get("index_state") is None:
            return None
        return {
            "version_id": row["id"],
            "library_id": row["library_id"],
            "version": row["version"],
            "state": row["index_state"],
            "error": row["index_error"],
            "updated_at": row["index_state_at"],
            "page_count": row["page_count"],
            "chunk_count": row["chunk_count"],
        }

    def index_status(self, limit: int = 20) -> dict:
        """Summarize recorded indexing attempts. Mirrors DocsDB.index_status."""
        counts = {
            r["state"]: r["n"]
            for r in self._d1.execute(
                "SELECT index_state AS state, COUNT(*) AS n FROM versions"
                " WHERE index_state IS NOT NULL GROUP BY index_state",
                [],
            )
        }
        recent = [
            {
                "library": r["library"],
                "version": r["version"],
                "state": r["index_state"],
                "error": r["index_error"],
                "updated_at": r["index_state_at"],
                "page_count": r["page_count"],
                "chunk_count": r["chunk_count"],
            }
            for r in self._d1.execute(
                "SELECT v.version, v.index_state, v.index_error, v.index_state_at,"
                " v.page_count, v.chunk_count, l.name AS library"
                " FROM versions v LEFT JOIN libraries l ON v.library_id = l.id"
                " WHERE v.index_state IS NOT NULL"
                " ORDER BY v.index_state_at DESC LIMIT ?",
                [limit],
            )
        ]
        return {"counts": counts, "recent": recent}

    def mark_library_indexed(
        self, library_id: str, total_versions: int | None = None
    ) -> None:
        """Update libraries.last_indexed_at, and total_versions when given.

        DocsDB.mark_library_indexed probes pragma_table_info because a
        pre-Alembic SQLite file may lack these columns. D1's schema is owned by
        migrations/0001_init_wet.sql, which has both, so this writes fixed SQL
        with no column names assembled at runtime.
        """
        if total_versions is None:
            self._d1.execute(
                "UPDATE libraries SET last_indexed_at = ? WHERE id = ?",
                [time.time(), library_id],
            )
            return
        self._d1.execute(
            "UPDATE libraries SET last_indexed_at = ?, total_versions = ? WHERE id = ?",
            [time.time(), int(total_versions), library_id],
        )

    def mark_metadata_seeded(self, library_id: str) -> None:
        """Record a metadata-only seed pass (Tier 1 warmup freshness anchor).

        Deliberately separate from last_indexed_at so a seeded-but-unindexed
        library stays distinguishable from an indexed one. The column arrives
        in migrations/0002_project_context.sql.
        """
        self._d1.execute(
            "UPDATE libraries SET metadata_seeded_at = ? WHERE id = ?",
            [time.time(), library_id],
        )

    # --- project context (Cabinets isolation) ---

    def upsert_project_context(
        self, project_path: str, locked_libraries: list[dict]
    ) -> None:
        """Persist a project's locked-library set, preserving created_at."""
        now = time.time()
        payload = json.dumps(locked_libraries, ensure_ascii=False)
        existing = self._d1.fetchone(
            "SELECT created_at FROM project_context WHERE project_path = ?",
            [project_path],
        )
        if existing:
            self._d1.execute(
                "UPDATE project_context SET locked_libraries = ?, last_used_at = ?"
                " WHERE project_path = ?",
                [payload, now, project_path],
            )
            return
        self._d1.execute(
            "INSERT INTO project_context (project_path, locked_libraries,"
            " created_at, last_used_at) VALUES (?,?,?,?)",
            [project_path, payload, now, now],
        )

    def get_project_context(self, project_path: str) -> dict | None:
        """Return the lock entry for a project, or None if not locked."""
        row = self._d1.fetchone(
            "SELECT project_path, locked_libraries, created_at, last_used_at"
            " FROM project_context WHERE project_path = ?",
            [project_path],
        )
        if row is None:
            return None
        result = dict(row)
        try:
            libs = json.loads(result["locked_libraries"])
            if not isinstance(libs, list):
                libs = []
            result["locked_libraries"] = libs
        except (TypeError, json.JSONDecodeError) as e:
            # Same trade-off DocsDB.get_project_context documents: an unreadable
            # lock reads as "nothing locked", which is shaped exactly like a
            # project that was never locked, so it is logged rather than hidden.
            logger.warning(
                f"project_context row for {project_path!r} has unreadable "
                f"locked_libraries ({type(e).__name__}: {e}); treating the "
                "project as unlocked"
            )
            result["locked_libraries"] = []
        return result

    def touch_project_context(self, project_path: str) -> None:
        """Update last_used_at; call before each query that honors a lock."""
        self._d1.execute(
            "UPDATE project_context SET last_used_at = ? WHERE project_path = ?",
            [time.time(), project_path],
        )

    # --- lifecycle + file-based sync ---

    def close(self) -> None:
        """No handle to release: D1 and Vectorize are reached per request.

        DocsDB.close() ends a long-lived sqlite3 connection. D1Backend and
        VectorizeBackend hold nothing open between calls, so there is nothing
        here to close. server.py calls this during shutdown, so it returns
        quietly because there genuinely is no work -- not because a failure
        was swallowed.
        """

    def export_jsonl(self) -> str:
        raise NotImplementedError(
            "export_jsonl is not available on DOCS_DB_BACKEND=cf-d1. The store "
            "is Cloudflare D1 + Vectorize, already shared and durable across "
            "every instance, so there is no local docs.db to export and no "
            "second copy to keep in step. The GDrive/S3 DB-sync exists to move "
            "a single-machine SQLite file around and is redundant here (see "
            "docs/cf-template.md, 'Sync mode-gating'). Leave SYNC_ENABLED off "
            "on a cf-d1 deployment, or read the rows directly with "
            "`wrangler d1 execute`."
        )

    def import_jsonl(self, data: str, mode: str = "merge") -> dict:
        raise NotImplementedError(
            "import_jsonl is not available on DOCS_DB_BACKEND=cf-d1. Sync JSONL "
            "carries no embeddings -- export_jsonl drops them by design -- so "
            "every imported chunk would land in D1 with no matching vector in "
            "Vectorize. Those chunks would answer FTS queries while staying "
            "invisible to the vector arm of search(), i.e. a half-ranked index "
            "that looks like a working one. Index the library normally so "
            "chunks and embeddings are written together, or bulk-load D1 with "
            "`wrangler d1 execute` and re-embed."
        )

    # --- hybrid search (ranking pipeline reused from db.py) ---

    def search(
        self,
        query: str,
        library_name: str | None = None,
        version: str | None = None,
        limit: int = 10,
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        library_id = version_id = None
        if library_name:
            lib = self.get_library(library_name)
            if not lib:
                return []
            library_id = lib["id"]
            if version:
                ver = self.get_best_version(library_id, version)
                if ver:
                    version_id = ver["id"]

        candidate_limit = limit * 3
        fts_scores: dict[str, float] = {}
        fts_chunks: dict[str, dict] = {}

        for fts_query in _build_fts_queries(query):
            sql = (
                "SELECT c.*, l.name AS _library_name, "
                "bm25(doc_chunks_fts, 0.0, 2.0, 3.0, 2.0) AS bm25_score "
                "FROM doc_chunks_fts f JOIN doc_chunks c ON f.id = c.id "
                "LEFT JOIN libraries l ON c.library_id = l.id "
                "WHERE doc_chunks_fts MATCH ?"
            )
            params: list = [fts_query]
            if library_id:
                sql += " AND c.library_id = ?"
                params.append(library_id)
            if version_id:
                sql += " AND c.version_id = ?"
                params.append(version_id)
            sql += " ORDER BY bm25_score LIMIT ?"
            params.append(candidate_limit)
            for row in self._d1.execute(sql, params):
                cid = row["id"]
                score = -row.pop("bm25_score", 0)
                if cid not in fts_scores or score > fts_scores[cid]:
                    fts_scores[cid] = score
                    fts_chunks[cid] = row

        if fts_scores:
            mn, mx = min(fts_scores.values()), max(fts_scores.values())
            rng = mx - mn
            fts_scores = (
                {k: (v - mn) / rng for k, v in fts_scores.items()}
                if rng > 0
                else dict.fromkeys(fts_scores, 1.0)
            )

        vec_scores: dict[str, float] = {}
        if query_embedding:
            mfilter = {}
            if library_id:
                mfilter["library_id"] = library_id
            if version_id:
                mfilter["version_id"] = version_id
            vec_results = list(
                self._vec.query(
                    query_embedding,
                    top_k=min(candidate_limit, 50),
                    metadata_filter=mfilter or None,
                )
            )
            missing_ids = []
            for m in vec_results:
                cid = m["id"]
                vec_scores[cid] = max(0.0, float(m["score"]))
                if cid not in fts_chunks:
                    missing_ids.append(cid)

            if missing_ids:
                # One bound parameter per id. Today this cannot reach D1's cap
                # on its own -- top_k above clamps vec_results to 50 -- but that
                # is a property of a number written elsewhere, not of this
                # statement. Routing it through the same helper as the
                # neighbour prefetch means raising candidate_limit or that
                # clamp can never silently reintroduce the "too many SQL
                # variables" crash that takes the whole container down.
                for batch in _d1_param_batches(missing_ids, 1):
                    placeholders = ",".join(["?"] * len(batch))
                    sql = (
                        "SELECT c.*, l.name AS _library_name FROM doc_chunks c "
                        "LEFT JOIN libraries l ON c.library_id = l.id "
                        f"WHERE c.id IN ({placeholders})"
                    )
                    for row in self._d1.execute(sql, batch):
                        fts_chunks[row["id"]] = row
                for cid in missing_ids:
                    if cid not in fts_chunks:
                        fts_chunks[cid] = {}

        scored = _combine_scores_cf(fts_scores, vec_scores, fts_chunks)
        return _build_results_cf(scored, fts_chunks, self._d1, limit)


def _combine_scores_cf(fts_scores, vec_scores, fts_chunks):
    """RRF k=60 + quality boost, identical formula to db.py DocsDB._combine_scores."""
    all_ids = fts_scores.keys() | vec_scores.keys()
    scored: list[tuple[str, float]] = []
    if vec_scores:
        k = 60
        fts_ranked = sorted(fts_scores, key=fts_scores.__getitem__, reverse=True)
        vec_ranked = sorted(vec_scores, key=vec_scores.__getitem__, reverse=True)
        fts_rank = {cid: i + 1 for i, cid in enumerate(fts_ranked)}
        vec_rank = {cid: i + 1 for i, cid in enumerate(vec_ranked)}
        default_rank = len(all_ids)
        for cid in all_ids:
            fr = fts_rank.get(cid, default_rank)
            vr = vec_rank.get(cid, default_rank)
            rrf = 1.0 / (k + fr) + 1.0 / (k + vr)
            chunk = fts_chunks.get(cid)
            quality = _chunk_quality_score(chunk["content"]) if chunk else 0.0
            scored.append((cid, rrf + quality * 0.005))
    else:
        for cid in fts_scores:
            chunk = fts_chunks.get(cid)
            quality = _chunk_quality_score(chunk["content"]) if chunk else 0.0
            scored.append((cid, fts_scores[cid] * 0.85 + quality * 0.15))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _build_results_cf(scored, fts_chunks, d1: D1Backend, limit: int):
    """URL diversity (2/url) + adjacent prefetch, ported from db.py L1172-1260."""
    max_per_url = 2
    url_counts: dict[str, int] = {}
    # batch-prefetch adjacent chunks from D1
    adj_keys: set[tuple[str, str, int]] = set()
    for cid, _ in scored:
        ch = fts_chunks.get(cid)
        if not ch:
            continue
        url, ver, idx = (
            ch.get("url", ""),
            ch.get("version_id", ""),
            ch.get("chunk_index", -1),
        )
        if url and ver and idx >= 0:
            adj_keys.add((url, ver, idx - 1))
            adj_keys.add((url, ver, idx + 1))
    adj_map: dict[tuple[str, str, int], str] = {}
    if adj_keys:
        unique_keys = sorted(adj_keys)
        # The key width drives BOTH the ?-tuple and the batch size, so the two
        # cannot disagree: adding a column to the key re-derives each of them.
        key_width = len(unique_keys[0])
        key_tuple = "(" + ",".join(["?"] * key_width) + ")"
        for batch in _d1_param_batches(unique_keys, key_width):
            placeholders = ",".join([key_tuple] * len(batch))
            params = [v for k in batch for v in k]
            sql = (
                "SELECT url, version_id, chunk_index, content "
                "FROM doc_chunks WHERE (url, version_id, chunk_index) "
                f"IN (VALUES {placeholders})"
            )
            for row in d1.execute(sql, params):
                adj_map[(row["url"], row["version_id"], row["chunk_index"])] = row[
                    "content"
                ]

    results: list[dict] = []
    for cid, score in scored:
        if len(results) >= limit:
            break
        chunk = fts_chunks.get(cid)
        if not chunk:
            continue
        url = chunk.get("url", "")
        if url:
            url_counts[url] = url_counts.get(url, 0) + 1
            if url_counts[url] > max_per_url:
                continue
        result = {
            "content": chunk["content"],
            "title": chunk.get("title", ""),
            "url": url,
            "heading_path": chunk.get("heading_path", ""),
            "library": chunk.get("_library_name", ""),
            "score": round(score, 4),
            "topic": chunk.get("topic"),
            "section": chunk.get("section"),
            "token_count": chunk.get("token_count"),
            "version_id": chunk.get("version_id"),
        }
        idx, ver = chunk.get("chunk_index", -1), chunk.get("version_id", "")
        if url and ver and idx >= 0:
            if b := adj_map.get((url, ver, idx - 1)):
                result["context_before"] = b
            if a := adj_map.get((url, ver, idx + 1)):
                result["context_after"] = a
        results.append(result)
    return results
