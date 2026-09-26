"""Persistent docs storage with hybrid search (FTS5 + optional sqlite-vec).

Stores library documentation chunks in SQLite with full-text search.
When an embedding model is configured, also stores vector embeddings
for semantic search with hybrid scoring.

Schema follows mnemo-mcp patterns: FTS5 content-sync mode with triggers,
sqlite-vec for vectors, JSONL export/import for sync.
"""

import json
import re
import sqlite3
import struct
import time
import uuid
from functools import lru_cache
from pathlib import Path

from loguru import logger

# Bump this when discovery scoring changes to invalidate stale caches.
from wet_mcp.sources.docs import DISCOVERY_VERSION


class EmbeddingModelMismatch(RuntimeError):
    """Raised when the docs vector store was built with a different model.

    The vector table stores embeddings produced by a specific embedding
    model at a specific dimensionality. Switching models silently mixes
    incompatible vector spaces (corruption / nonsense search). DocsDB
    stamps the active model identity on first init and refuses to open a
    store stamped with a different identity unless a rebuild is opted in.
    """


def _serialize_f32(vec: list[float]) -> bytes:
    """Serialize float vector for sqlite-vec."""
    return struct.pack(f"{len(vec)}f", *vec)


def _now_ts() -> float:
    """Current timestamp as float."""
    return time.time()


def new_chunk_id() -> str:
    """Mint a doc_chunks primary key.

    Chunk identity belongs to the DB layer, not to the caller: the chunkers in
    wet_mcp.sources.docs emit content only, and server._background_index_and_search
    hands their output to add_chunks untouched. Both backends call this so a
    chunk written to D1 and the same chunk written to SQLite are shaped alike --
    db_cf.DocsDBCfBackend used to read c["id"] instead, which the chunker never
    supplies (issue #1618).
    """
    return uuid.uuid4().hex[:12]


# Patterns for chunk quality scoring
_CODE_BLOCK_RE = re.compile(r"```")
_LINK_LINE_RE = re.compile(r"^\s*[-*]?\s*\[.+?\]\(.+?\)\s*$|^\s*https?://\S+\s*$")
# Function/class/type definitions (common across languages)
_DEF_KEYWORDS = (
    "def ",
    "class ",
    "fn ",
    "func ",
    "function ",
    "interface ",
    "type ",
    "struct ",
    "enum ",
    "const ",
    "let ",
    "var ",
    "export ",
)
_DEF_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(k) for k in _DEF_KEYWORDS) + ")",
    re.MULTILINE,
)
# Docstring / doc comment patterns
_DOCSTRING_RE = re.compile(
    r'"""|\'\'\'|/\*\*|///|#\s+(?:Args|Returns|Raises|Example|Usage|Parameters|Note)'
)
# Security: Strict allowlists for dynamic column/table construction
_LIBRARIES_COLUMNS = {
    "id",
    "name",
    "docs_url",
    "registry",
    "description",
    "canonical_name",
    "homepage",
    "github_url",
    "package_managers",
    "tier",
    "last_indexed_at",
    "metadata_seeded_at",
    "total_versions",
    "discovery_version",
    "created_at",
    "updated_at",
}

_DOC_CHUNKS_COLUMNS = {
    "id",
    "version_id",
    "library_id",
    "url",
    "title",
    "chunk_index",
    "content",
    "heading_path",
    "created_at",
    "topic",
    "section",
    "content_hash",
    "token_count",
    "summary",
    "summary_provider",
}

# Directive-heavy content (mkdocs leftover, rst directives)
_DIRECTIVE_RE = re.compile(r"^(?:!!!|:::|\.\.)\s", re.MULTILINE)

# Values written to ``versions.index_state`` by ``set_index_state``. They record
# what the LAST indexing attempt did, which ``versions.status`` cannot: status
# gates what ``get_best_version`` serves, so a version can be serving usable
# chunks (status='indexed') while its newest re-index attempt is 'failed'.
INDEX_STATE_RUNNING = "running"
INDEX_STATE_DONE = "done"
INDEX_STATE_FAILED = "failed"


def _build_fts_queries(query: str) -> list[str]:
    """Build tiered FTS5 queries: PHRASE -> AND -> OR.

    No stop-word filtering — BM25's IDF naturally down-weights common
    words (any language) and the PHRASE->AND->OR fallback ensures precision
    first, then recall.
    """
    # split() with no argument splits on arbitrary whitespace and drops the
    # empty strings, so the query needs no separate strip().
    words = query.split()
    safe = [w.replace('"', '""') for w in words]

    if not safe:
        return []
    if len(safe) == 1:
        return [f'"{safe[0]}"*']

    return [
        # Tier 0: PHRASE — exact phrase match (highest precision)
        '"' + " ".join(safe) + '"',
        # Tier 1: AND — all terms must appear
        " AND ".join(f'"{w}"*' for w in safe),
        # Tier 2: OR — any term matches (broadest fallback)
        " OR ".join(f'"{w}"*' for w in safe),
    ]


@lru_cache(maxsize=1024)
def _chunk_quality_score(content: str) -> float:
    """Score chunk content quality for docs ranking (0.0 to 1.0).

    Boosts chunks with code examples, function/class definitions, and
    docstrings. Penalizes link-heavy TOC chunks, directive-heavy content,
    and very short chunks.
    """
    score = 0.0

    code_blocks = content.count("```") // 2
    score += min(code_blocks, 3) * 2.0  # up to +6

    # One pass collects all three line-level signals below. Scored separately
    # they would each walk the whole chunk.
    defs = 0
    docstrings = 0
    lines_count = 0
    link_lines = 0

    for ln in content.splitlines():
        if not ln or ln.isspace():
            continue
        lines_count += 1

        # Function/class definitions signal API documentation
        if defs < 4 and ln.lstrip().startswith(_DEF_KEYWORDS):
            defs += 1

        # Docstrings/doc comments signal well-documented code.
        # The substring tests are a filter, not part of the definition: most
        # lines carry no docstring marker at all, and this keeps the regex off
        # them.
        if docstrings < 3 and (
            '"""' in ln or "'''" in ln or "/**" in ln or "///" in ln or "#" in ln
        ):
            for _ in _DOCSTRING_RE.finditer(ln):
                docstrings += 1
                if docstrings >= 3:
                    break

        # Link-heavy content is usually navigation/TOC, not docs
        if _LINK_LINE_RE.match(ln):
            link_lines += 1

    score += defs * 1.5  # up to +6
    score += docstrings * 1.0  # up to +3

    # Longer content tends to be more informative
    length = len(content)
    if length > 500:
        score += 2.0
    elif length > 200:
        score += 1.0

    if lines_count:
        ratio = link_lines / lines_count
        if ratio > 0.5:
            score -= 4.0
        elif ratio > 0.3:
            score -= 2.0

    # Directive-heavy content (leftover mkdocs/rst noise). Only the first four
    # matches change the score, so counting stops there instead of collecting
    # every match in the chunk.
    directives = 0
    for _ in _DIRECTIVE_RE.finditer(content):
        directives += 1
        if directives > 3:
            break
    if directives > 3:
        score -= 2.0
    elif directives > 1:
        score -= 1.0

    # Normalize to 0-1 range (wider range due to more signals)
    return max(0.0, min(score / 12.0, 1.0))


class DocsDB:
    """SQLite-backed docs storage with FTS5 hybrid search."""

    def __init__(
        self,
        db_path: Path,
        embedding_dims: int = 0,
        model_identity: str = "",
        reindex_on_model_change: bool = False,
    ):
        self._db_path = db_path
        if (
            type(embedding_dims) is not int
            or embedding_dims < 0
            or embedding_dims > 65536
        ):
            raise ValueError(
                f"embedding_dims must be an integer 0-65536, got {embedding_dims!r}"
            )
        self._embedding_dims = embedding_dims
        self._model_identity = model_identity
        self._reindex_on_model_change = reindex_on_model_change
        self._vec_enabled = False
        self._seed_stamp_migration_pending = False

        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False allows the connection to be used from
        # asyncio.to_thread workers (PRAGMA busy_timeout below serializes
        # concurrent writes safely; SQLite WAL is multi-reader-safe).
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA mmap_size = 268435456")  # 256MB mmap
        self._conn.execute("PRAGMA temp_store = MEMORY")
        self._conn.execute("PRAGMA cache_size = -64000")  # 64MB cache (KB)

        # Try loading sqlite-vec extension
        if embedding_dims > 0:
            try:
                import sqlite_vec

                self._conn.enable_load_extension(True)
                sqlite_vec.load(self._conn)
                self._conn.enable_load_extension(False)
                self._vec_enabled = True
                logger.debug("sqlite-vec extension loaded")
            except Exception as e:
                # sqlite-vec is a hard dependency, and the caller asked for
                # embedding_dims > 0. Falling back to FTS-only is a whole
                # capability going away for the life of the process, so it is
                # not a debug-level event.
                logger.warning(
                    f"sqlite-vec unavailable for {db_path} "
                    f"({type(e).__name__}: {e}); running FTS-only -- vector "
                    "search is disabled and docs queries answer with keyword "
                    "matching alone"
                )

        self._create_tables()
        self._guard_embedding_identity()
        logger.debug(f"DocsDB initialized at {db_path} (vec={self._vec_enabled})")

    def _create_tables(self) -> None:
        self._create_libraries_table()
        self._create_versions_table()
        self._create_doc_chunks_table()
        self._create_fts_table()
        self._create_vector_table()
        self._create_project_context_table()
        self._create_store_meta_table()
        if self._seed_stamp_migration_pending:
            # Deferred until the versions table exists — the relabel needs it.
            self._migrate_seed_stamps_off_last_indexed_at()
            self._seed_stamp_migration_pending = False
        self._conn.commit()

    def _migrate_seed_stamps_off_last_indexed_at(self) -> None:
        """Move seed-only ``last_indexed_at`` stamps into ``metadata_seeded_at``.

        A library that owns no ``status = 'indexed'`` version was never
        indexed, so its ``last_indexed_at`` can only have come from the old
        ``upsert_library`` stamp (or the ``docs_002`` ``updated_at``
        backfill). Leaving it in place would keep the Tier 1 freshness gate
        satisfied forever on an empty database. Mirrors the
        ``docs_005_metadata_seeded_at`` Alembic migration for DBs that reach
        ``DocsDB`` first.
        """
        cur = self._conn.execute("""
            UPDATE libraries
               SET metadata_seeded_at = COALESCE(metadata_seeded_at, last_indexed_at),
                   last_indexed_at = NULL
             WHERE last_indexed_at IS NOT NULL
               AND NOT EXISTS (
                   SELECT 1 FROM versions v
                    WHERE v.library_id = libraries.id AND v.status = 'indexed'
               )
        """)
        self._conn.commit()
        if cur.rowcount:
            logger.info(
                f"Relabelled {cur.rowcount} metadata-only library seeds "
                "(last_indexed_at -> metadata_seeded_at)"
            )

    def _create_store_meta_table(self) -> None:
        # Key/value metadata for store-level invariants (B2: embedding-model
        # identity guard). Stamped on first init; compared on every open.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS store_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

    def _guard_embedding_identity(self) -> None:
        """Guard the vector store against silent embedding-model swaps.

        Compares the CURRENT ``(embedding_model, embedding_dims)`` to the
        stamped values:

        * fresh (no stamp) -> stamp + proceed.
        * match -> proceed.
        * mismatch -> raise ``EmbeddingModelMismatch`` touching NO data,
          UNLESS ``reindex_on_model_change`` is set, in which case the
          vector table is dropped + cleared and the identity re-stamped
          (the docs-embed pipeline rebuilds on the next pass).

        ``embedding_dims`` is the primary guard (a dims mismatch is the
        most dangerous case — incompatible vector spaces); ``embedding_model``
        is also compared when an identity string is available.
        """
        stored = {
            r["key"]: r["value"]
            for r in self._conn.execute(
                "SELECT key, value FROM store_meta "
                "WHERE key IN ('embedding_model', 'embedding_dims')"
            ).fetchall()
        }

        current_dims = str(int(self._embedding_dims))
        # Fresh store: stamp identity and proceed.
        if "embedding_dims" not in stored and "embedding_model" not in stored:
            self._stamp_embedding_identity()
            return

        stored_dims = stored.get("embedding_dims")
        stored_model = stored.get("embedding_model", "")

        dims_mismatch = stored_dims is not None and stored_dims != current_dims
        # Only compare the model id when both sides carry one (dims-only guard
        # otherwise — stamping dims alone still catches the dangerous case).
        model_mismatch = bool(
            stored_model
            and self._model_identity
            and stored_model != self._model_identity
        )

        if not dims_mismatch and not model_mismatch:
            return

        if self._reindex_on_model_change:
            logger.warning(
                "Embedding-model change detected (stored model={!r} dims={!r}, "
                "requested model={!r} dims={!r}); REINDEX_ON_MODEL_CHANGE is set "
                "-- dropping the vector store and re-stamping. The docs-embed "
                "pipeline will rebuild embeddings on the next pass.",
                stored_model,
                stored_dims,
                self._model_identity,
                current_dims,
            )
            self._reindex_vector_store()
            self._stamp_embedding_identity()
            return

        raise EmbeddingModelMismatch(
            "Docs vector store was built with embedding model "
            f"{stored_model or '<unknown>'!r} (dims={stored_dims}) but the "
            f"server is now configured for {self._model_identity or '<unknown>'!r} "
            f"(dims={current_dims}). Mixing these vector spaces would corrupt "
            "search. Set REINDEX_ON_MODEL_CHANGE=true to rebuild, or restore "
            "the previous model."
        )

    def _stamp_embedding_identity(self) -> None:
        """Record the active embedding identity in store_meta."""
        self._conn.execute(
            "INSERT OR REPLACE INTO store_meta (key, value) VALUES (?, ?)",
            ("embedding_dims", str(int(self._embedding_dims))),
        )
        if self._model_identity:
            self._conn.execute(
                "INSERT OR REPLACE INTO store_meta (key, value) VALUES (?, ?)",
                ("embedding_model", self._model_identity),
            )
        self._conn.commit()

    def _reindex_vector_store(self) -> None:
        """Drop the vector table + clear stored vectors (opt-in reindex path).

        Does NOT re-run embeddings inline; the existing docs-embed pipeline
        rebuilds on the next pass.
        """
        try:
            self._conn.execute("DROP TABLE IF EXISTS doc_chunks_vec")
            self._conn.commit()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Failed to drop vector table during reindex: {e}")
        # Recreate the empty vector table at the current dims so the embed
        # pipeline has a target to write into.
        self._create_vector_table()
        self._conn.commit()

    def _create_project_context_table(self) -> None:
        # Phase 2 (spec section 5.4) — Cabinets project isolation.
        # Mode-3 isolation (spec §4 Q2): the logical key is now
        # (sub, project_path) so N callers can each hold their own lock for
        # the same project. Legacy DBs keep the old project_path PRIMARY KEY
        # shape; the guarded ALTER appends ``sub`` (all legacy rows become
        # 'default') and the unique index below preserves the logical key.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS project_context (
                project_path TEXT NOT NULL,
                sub TEXT NOT NULL DEFAULT 'default',
                locked_libraries TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_used_at REAL NOT NULL
            )
        """)
        try:
            self._conn.execute(
                "ALTER TABLE project_context "
                "ADD COLUMN sub TEXT NOT NULL DEFAULT 'default'"
            )
            self._conn.commit()
            logger.debug("Migrated project_context table: added sub")
        except sqlite3.OperationalError:
            pass  # Column already exists
        self._conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_project_context_sub_path
            ON project_context(sub, project_path)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_context_last_used
            ON project_context(last_used_at)
        """)
        self._conn.commit()

    def _create_libraries_table(self) -> None:
        # Libraries metadata (Phase 2 schema; pre-Alembic legacy databases
        # are upgraded to this shape by alembic/versions/docs_002_libraries.py).
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS libraries (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                docs_url TEXT,
                registry TEXT,
                description TEXT,
                canonical_name TEXT,
                homepage TEXT,
                github_url TEXT,
                package_managers TEXT,
                tier INTEGER NOT NULL DEFAULT 2,
                last_indexed_at REAL,
                metadata_seeded_at REAL,
                total_versions INTEGER NOT NULL DEFAULT 0,
                discovery_version INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_libraries_name
            ON libraries(name)
        """)

        # Idempotent column adds for legacy DBs that pre-date Alembic.
        # Each ALTER is wrapped in a try/except so re-running on a fresh
        # head-shape table does not raise.
        for sql, col_name in (
            (
                "ALTER TABLE libraries ADD COLUMN discovery_version INTEGER DEFAULT 0",
                "discovery_version",
            ),
            ("ALTER TABLE libraries ADD COLUMN canonical_name TEXT", "canonical_name"),
            ("ALTER TABLE libraries ADD COLUMN homepage TEXT", "homepage"),
            ("ALTER TABLE libraries ADD COLUMN github_url TEXT", "github_url"),
            (
                "ALTER TABLE libraries ADD COLUMN package_managers TEXT",
                "package_managers",
            ),
            (
                "ALTER TABLE libraries ADD COLUMN tier INTEGER NOT NULL DEFAULT 2",
                "tier",
            ),
            (
                "ALTER TABLE libraries ADD COLUMN last_indexed_at REAL",
                "last_indexed_at",
            ),
            (
                "ALTER TABLE libraries ADD COLUMN total_versions INTEGER NOT NULL DEFAULT 0",
                "total_versions",
            ),
            (
                "ALTER TABLE libraries ADD COLUMN metadata_seeded_at REAL",
                "metadata_seeded_at",
            ),
        ):
            try:
                self._conn.execute(sql)
                self._conn.commit()
                logger.debug(f"Migrated libraries table: added {col_name}")
                if col_name == "metadata_seeded_at":
                    # The column is new here, so this DB was written by a
                    # build where upsert_library stamped last_indexed_at for
                    # metadata-only seeds. Relabel those stamps once.
                    self._seed_stamp_migration_pending = True
            except sqlite3.OperationalError:
                pass  # Column already exists

    def _create_versions_table(self) -> None:
        # Versions (Phase 2 schema with release_date + source_url).
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS versions (
                id TEXT PRIMARY KEY,
                library_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT 'latest',
                docs_url TEXT,
                indexed_at REAL,
                page_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                release_date REAL,
                source_url TEXT,
                index_state TEXT,
                index_error TEXT,
                index_state_at REAL,
                FOREIGN KEY (library_id) REFERENCES libraries(id) ON DELETE CASCADE,
                UNIQUE(library_id, version)
            )
        """)
        # Idempotent column adds for legacy DBs.
        for sql in (
            "ALTER TABLE versions ADD COLUMN release_date REAL",
            "ALTER TABLE versions ADD COLUMN source_url TEXT",
            "ALTER TABLE versions ADD COLUMN index_state TEXT",
            "ALTER TABLE versions ADD COLUMN index_error TEXT",
            "ALTER TABLE versions ADD COLUMN index_state_at REAL",
        ):
            try:
                self._conn.execute(sql)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass

    def _create_doc_chunks_table(self) -> None:
        # Document chunks (Phase 2 schema with section/topic/content_hash/token_count).
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS doc_chunks (
                id TEXT PRIMARY KEY,
                version_id TEXT NOT NULL,
                library_id TEXT NOT NULL,
                url TEXT,
                title TEXT,
                chunk_index INTEGER NOT NULL DEFAULT 0,
                content TEXT NOT NULL,
                heading_path TEXT,
                section TEXT,
                topic TEXT,
                content_hash TEXT,
                token_count INTEGER,
                created_at REAL NOT NULL,
                FOREIGN KEY (version_id) REFERENCES versions(id) ON DELETE CASCADE,
                FOREIGN KEY (library_id) REFERENCES libraries(id) ON DELETE CASCADE
            )
        """)
        # Idempotent column adds for legacy DBs.
        for sql in (
            "ALTER TABLE doc_chunks ADD COLUMN section TEXT",
            "ALTER TABLE doc_chunks ADD COLUMN topic TEXT",
            "ALTER TABLE doc_chunks ADD COLUMN content_hash TEXT",
            "ALTER TABLE doc_chunks ADD COLUMN token_count INTEGER",
        ):
            try:
                self._conn.execute(sql)
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_version
            ON doc_chunks(version_id)
        """)
        # Covers the adjacent-chunk prefetch exactly, in its column order:
        # WHERE version_id = ? AND url = ? AND chunk_index IN (...)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_ver_url_idx
            ON doc_chunks(version_id, url, chunk_index)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_library
            ON doc_chunks(library_id)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_url_order
            ON doc_chunks(url, version_id, chunk_index)
        """)
        # Phase 2: composite index for topic-filtered queries.
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_doc_chunks_lib_ver_topic
            ON doc_chunks(library_id, version_id, topic)
        """)

    def _create_fts_table(self) -> None:
        # FTS5 (content-sync mode)
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts
            USING fts5(
                id UNINDEXED,
                content,
                title,
                heading_path,
                content=doc_chunks,
                content_rowid=rowid,
                tokenize='porter unicode61'
            )
        """)

        # FTS5 sync triggers
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON doc_chunks BEGIN
                INSERT INTO doc_chunks_fts(rowid, id, content, title, heading_path)
                VALUES (new.rowid, new.id, new.content, new.title, new.heading_path);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON doc_chunks BEGIN
                INSERT INTO doc_chunks_fts(doc_chunks_fts, rowid, id, content, title, heading_path)
                VALUES ('delete', old.rowid, old.id, old.content, old.title, old.heading_path);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON doc_chunks BEGIN
                INSERT INTO doc_chunks_fts(doc_chunks_fts, rowid, id, content, title, heading_path)
                VALUES ('delete', old.rowid, old.id, old.content, old.title, old.heading_path);
                INSERT INTO doc_chunks_fts(rowid, id, content, title, heading_path)
                VALUES (new.rowid, new.id, new.content, new.title, new.heading_path);
            END
        """)

    def _create_vector_table(self) -> None:
        # Vector table (optional)
        if self._vec_enabled and self._embedding_dims > 0:
            row = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='doc_chunks_vec'"
            ).fetchone()
            if not row:
                # Security: Dimensions are validated as 0-65536 integer in __init__.
                # Schema construction (CREATE VIRTUAL TABLE) does not support parameters.
                dims_str = str(int(self._embedding_dims))
                sql = (
                    "CREATE VIRTUAL TABLE doc_chunks_vec USING vec0("
                    "id TEXT PRIMARY KEY, "
                    "embedding float[" + dims_str + "]"
                    ")"
                )
                # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                self._conn.execute(sql)

    # -----------------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------------

    def stats(self) -> dict:
        """Return database statistics."""
        lib_count = self._conn.execute("SELECT COUNT(*) FROM libraries").fetchone()[0]
        chunk_count = self._conn.execute("SELECT COUNT(*) FROM doc_chunks").fetchone()[
            0
        ]
        return {
            "libraries": lib_count,
            "chunks": chunk_count,
            "vec_enabled": self._vec_enabled,
        }

    def _get_table_columns(self, table_name: str) -> set[str]:
        """Retrieve the set of column names for a given table."""
        return {
            r[0]
            for r in self._conn.execute(
                "SELECT name FROM pragma_table_info(?)", (table_name,)
            ).fetchall()
        }

    def _update_library_inner(
        self,
        lib_id: str,
        now: float,
        existing_cols: set[str],
        docs_url: str | None,
        registry: str | None,
        description: str | None,
        canonical_name: str | None,
        homepage: str | None,
        github_url: str | None,
        pkg_json: str | None,
        tier: int | None,
    ) -> None:
        """Internal helper for updating an existing library."""
        updates: list[str] = []
        params: list = []
        if docs_url is not None:
            updates.append("docs_url = ?")
            params.append(docs_url)
        if registry is not None:
            updates.append("registry = ?")
            params.append(registry)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if canonical_name is not None and "canonical_name" in existing_cols:
            updates.append("canonical_name = ?")
            params.append(canonical_name)
        if homepage is not None and "homepage" in existing_cols:
            updates.append("homepage = ?")
            params.append(homepage)
        if github_url is not None and "github_url" in existing_cols:
            updates.append("github_url = ?")
            params.append(github_url)
        if pkg_json is not None and "package_managers" in existing_cols:
            updates.append("package_managers = ?")
            params.append(pkg_json)
        if tier is not None and "tier" in existing_cols:
            updates.append("tier = ?")
            params.append(int(tier))

        updates.append("discovery_version = ?")
        params.append(DISCOVERY_VERSION)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(lib_id)

        if updates:
            for u in updates:
                col = u.split("=")[0].strip()
                if col not in _LIBRARIES_COLUMNS:
                    raise ValueError(f"Unauthorized column update: {col}")

            # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            self._conn.execute(
                "UPDATE libraries SET " + ", ".join(updates) + " WHERE id = ?",
                params,
            )
            self._conn.commit()

    def _insert_library_inner(
        self,
        lib_id: str,
        norm_name: str,
        now: float,
        existing_cols: set[str],
        docs_url: str | None,
        registry: str | None,
        description: str | None,
        canonical_name: str | None,
        homepage: str | None,
        github_url: str | None,
        pkg_json: str | None,
        tier: int | None,
    ) -> None:
        """Internal helper for inserting a new library."""
        cols = [
            "id",
            "name",
            "docs_url",
            "registry",
            "description",
            "discovery_version",
            "created_at",
            "updated_at",
        ]
        vals: list = [
            lib_id,
            norm_name,
            docs_url,
            registry,
            description,
            DISCOVERY_VERSION,
            now,
            now,
        ]
        for col_name, value, include_when_none in (
            ("canonical_name", canonical_name or norm_name, True),
            ("homepage", homepage, False),
            ("github_url", github_url, False),
            ("package_managers", pkg_json, False),
            ("tier", tier, False),
        ):
            if col_name in existing_cols and (value is not None or include_when_none):
                cols.append(col_name)
                vals.append(value)

        for c in cols:
            if c not in _LIBRARIES_COLUMNS:
                raise ValueError(f"Unauthorized library column: {c}")

        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        self._conn.execute(
            f"INSERT INTO libraries ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})",
            vals,
        )
        self._conn.commit()

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

        Automatically stamps the current ``DISCOVERY_VERSION``. It does
        *not* touch ``last_indexed_at``: writing metadata says nothing about
        whether chunks landed, and ``mark_library_indexed`` is the only
        writer that knows. Metadata-only seeding records its own progress
        via ``mark_metadata_seeded``.

        Phase 2 (spec §5.4) adds optional metadata: ``tier`` (1 curated /
        2 on-demand), ``package_managers`` (JSON list), ``homepage``,
        ``github_url``, and ``canonical_name`` (display label). Columns
        are added by ``docs_002_libraries`` migration; this writer
        gracefully skips any field whose column is missing so it can run
        against pre-Alembic legacy databases for one cycle.
        """
        now = _now_ts()
        norm_name = name.lower().strip()
        existing_cols = self._get_table_columns("libraries")
        pkg_json = (
            json.dumps(package_managers, ensure_ascii=False)
            if package_managers is not None
            else None
        )

        row = self._conn.execute(
            "SELECT id FROM libraries WHERE name = ?", (norm_name,)
        ).fetchone()

        if row:
            lib_id = row["id"]
            self._update_library_inner(
                lib_id=lib_id,
                now=now,
                existing_cols=existing_cols,
                docs_url=docs_url,
                registry=registry,
                description=description,
                canonical_name=canonical_name,
                homepage=homepage,
                github_url=github_url,
                pkg_json=pkg_json,
                tier=tier,
            )
            return lib_id

        lib_id = uuid.uuid4().hex[:12]
        self._insert_library_inner(
            lib_id=lib_id,
            norm_name=norm_name,
            now=now,
            existing_cols=existing_cols,
            docs_url=docs_url,
            registry=registry,
            description=description,
            canonical_name=canonical_name,
            homepage=homepage,
            github_url=github_url,
            pkg_json=pkg_json,
            tier=tier,
        )
        return lib_id

    # -----------------------------------------------------------------------
    # Library CRUD
    # -----------------------------------------------------------------------
    def mark_library_indexed(
        self, library_id: str, total_versions: int | None = None
    ) -> None:
        """Update libraries.last_indexed_at + total_versions (Phase 2).

        Silently no-ops on pre-Alembic legacy databases that lack the
        ``last_indexed_at`` / ``total_versions`` columns.
        """
        existing_cols = {
            r[0]
            for r in self._conn.execute(
                "SELECT name FROM pragma_table_info(?)", ("libraries",)
            ).fetchall()
        }
        sets: list[str] = []
        params: list = []
        if "last_indexed_at" in existing_cols:
            sets.append("last_indexed_at = ?")
            params.append(_now_ts())
        if "total_versions" in existing_cols and total_versions is not None:
            sets.append("total_versions = ?")
            params.append(int(total_versions))
        if not sets:
            return
        params.append(library_id)
        # Security: Validate all column names against a strict allowlist.
        for s in sets:
            col = s.split("=")[0].strip()
            if col not in _LIBRARIES_COLUMNS:
                raise ValueError(f"Unauthorized library column: {col}")

        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        self._conn.execute(
            "UPDATE libraries SET " + ", ".join(sets) + " WHERE id = ?",
            params,
        )
        self._conn.commit()

    def mark_metadata_seeded(self, library_id: str) -> None:
        """Record a metadata-only seed pass (Tier 1 warmup freshness anchor).

        Separate from ``last_indexed_at`` so a seeded-but-unindexed library
        is distinguishable from an indexed one. Silently no-ops on legacy
        databases that lack the column.
        """
        if "metadata_seeded_at" not in self._get_table_columns("libraries"):
            return
        self._conn.execute(
            "UPDATE libraries SET metadata_seeded_at = ? WHERE id = ?",
            (_now_ts(), library_id),
        )
        self._conn.commit()

    def get_library(self, name: str) -> dict | None:
        """Get library by name."""
        row = self._conn.execute(
            "SELECT * FROM libraries WHERE name = ?", (name.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None

    def get_library_by_id(self, library_id: str) -> dict | None:
        """Get a library row by its stable identifier."""
        row = self._conn.execute(
            "SELECT * FROM libraries WHERE id = ?", (library_id,)
        ).fetchone()
        return dict(row) if row else None

    def find_libraries_by_prefix(self, name: str, limit: int = 20) -> list[dict]:
        """Return libraries whose names start with ``name``, alphabetically."""
        norm_name = name.lower().strip()
        if not norm_name or limit <= 0:
            return []
        rows = self._conn.execute(
            "SELECT * FROM libraries "
            "WHERE name LIKE ? AND name != ? "
            "ORDER BY length(name) ASC, name ASC LIMIT ?",
            (f"{norm_name}%", norm_name, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def find_libraries_by_substring(self, name: str, limit: int = 20) -> list[dict]:
        """Return libraries containing ``name`` beyond a prefix match."""
        norm_name = name.lower().strip()
        if not norm_name or limit <= 0:
            return []
        rows = self._conn.execute(
            "SELECT * FROM libraries "
            "WHERE name LIKE ? AND name NOT LIKE ? AND name != ? "
            "ORDER BY length(name) ASC, name ASC LIMIT ?",
            (f"%{norm_name}%", f"{norm_name}%", norm_name, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    # -----------------------------------------------------------------------
    # Version management
    # -----------------------------------------------------------------------

    def upsert_version(
        self,
        library_id: str,
        version: str = "latest",
        docs_url: str | None = None,
    ) -> str:
        """Create or get version. Returns version ID."""
        row = self._conn.execute(
            "SELECT id FROM versions WHERE library_id = ? AND version = ?",
            (library_id, version),
        ).fetchone()

        if row:
            ver_id = row["id"]
            if docs_url:
                self._conn.execute(
                    "UPDATE versions SET docs_url = ? WHERE id = ?",
                    (docs_url, ver_id),
                )
                self._conn.commit()
            return ver_id

        ver_id = uuid.uuid4().hex[:12]
        self._conn.execute(
            """INSERT INTO versions (id, library_id, version, docs_url, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (ver_id, library_id, version, docs_url),
        )
        self._conn.commit()
        return ver_id

    def mark_version_indexed(
        self, version_id: str, page_count: int, chunk_count: int
    ) -> None:
        """Mark version as indexed with counts."""
        self._conn.execute(
            """UPDATE versions
               SET status = 'indexed', indexed_at = ?, page_count = ?, chunk_count = ?
               WHERE id = ?""",
            (_now_ts(), page_count, chunk_count, version_id),
        )
        self._conn.commit()

    def reset_version_index(self, version_id: str) -> None:
        """Mark a cleared version as NOT indexed so lazy re-ingest can fire.

        ``docs_reindex`` clears a version's chunks, but as long as the row
        still says ``status = 'indexed'`` every lazy path treats the library
        as servable: ``resolve_library`` -> ``get_best_version`` keeps
        returning it, so ``docs_query`` never fires ``ingest_tier2``, and the
        documented "next docs search will re-index" only holds on the
        search-chain path. A cleared version with zero chunks is not indexed.
        The index_state record is deliberately untouched: it is the log of
        the last ATTEMPT, and the next attempt overwrites it.
        """
        self._conn.execute(
            """UPDATE versions
               SET status = 'pending', indexed_at = NULL, page_count = 0, chunk_count = 0
               WHERE id = ?""",
            (version_id,),
        )
        self._conn.commit()

    def set_index_state(
        self, version_id: str, state: str, error: str | None = None
    ) -> None:
        """Record the outcome of an indexing attempt on a version.

        ``state`` is one of ``INDEX_STATE_RUNNING`` / ``INDEX_STATE_DONE`` /
        ``INDEX_STATE_FAILED``. Writing it to the database is the point: the
        background indexer's only previous record of a failure was a
        ``logger.error`` inside the container, which reaches nobody, so
        ``chunks: 0`` was indistinguishable from never-attempted,
        still-running, failed and succeeded-with-no-content.

        ``page_count`` / ``chunk_count`` are deliberately NOT written here.
        They describe the last SUCCESSFUL index (``mark_version_indexed`` owns
        them), and zeroing them on a failed attempt would erase the only
        record that usable chunks are still stored for this version.
        """
        self._conn.execute(
            """UPDATE versions
               SET index_state = ?, index_error = ?, index_state_at = ?
               WHERE id = ?""",
            (state, error, _now_ts(), version_id),
        )
        self._conn.commit()

    def get_index_state(self, version_id: str) -> dict | None:
        """Return the indexing-attempt record for a version.

        ``None`` means no attempt was ever recorded (or the version is gone),
        which is a different answer from a recorded failure -- telling those
        two apart is the whole reason this row exists.
        """
        row = self._conn.execute(
            """SELECT id, library_id, version, index_state, index_error,
                      index_state_at, page_count, chunk_count
               FROM versions WHERE id = ?""",
            (version_id,),
        ).fetchone()
        if row is None or row["index_state"] is None:
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
        """Summarize recorded indexing attempts for ``config(action="status")``.

        Returns a per-state tally plus the most recently touched attempts,
        newest first, so an operator reading the status payload can tell a
        store that indexed nothing from one that failed eight times and say
        why.
        """
        counts = {
            r["state"]: r["n"]
            for r in self._conn.execute(
                "SELECT index_state AS state, COUNT(*) AS n FROM versions "
                "WHERE index_state IS NOT NULL GROUP BY index_state"
            ).fetchall()
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
            for r in self._conn.execute(
                "SELECT v.version, v.index_state, v.index_error, v.index_state_at,"
                " v.page_count, v.chunk_count, l.name AS library"
                " FROM versions v LEFT JOIN libraries l ON v.library_id = l.id"
                " WHERE v.index_state IS NOT NULL"
                " ORDER BY v.index_state_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        ]
        return {"counts": counts, "recent": recent}

    def get_best_version(
        self, library_id: str, target: str | None = None
    ) -> dict | None:
        """Get best matching version for library."""
        if target:
            # Try exact match first
            row = self._conn.execute(
                """SELECT * FROM versions
                   WHERE library_id = ? AND version = ? AND status = 'indexed'""",
                (library_id, target),
            ).fetchone()
            if row:
                return dict(row)

        # Fallback to latest indexed
        row = self._conn.execute(
            """SELECT * FROM versions
               WHERE library_id = ? AND status = 'indexed'
               ORDER BY indexed_at DESC LIMIT 1""",
            (library_id,),
        ).fetchone()
        return dict(row) if row else None

    # -----------------------------------------------------------------------
    # Chunks CRUD
    # -----------------------------------------------------------------------

    def add_chunks(
        self,
        version_id: str,
        library_id: str,
        chunks: list[dict],
        embeddings: list[list[float]] | None = None,
    ) -> int:
        """Add document chunks with optional embeddings.

        Each chunk dict supports the v1 keys
        ``{url, title, content, heading_path, chunk_index}`` plus the
        Phase 2 (spec §5.4) optional keys ``topic``, ``section``,
        ``content_hash``, ``token_count`` plus the Phase 3 (spec §4.3
        NICE) optional keys ``summary``, ``summary_provider``. Optional
        keys are written only when the corresponding columns exist in
        the live schema (post ``docs_002_libraries`` for Phase 2;
        post ``docs_004_chunk_summaries`` for Phase 3).
        """
        now = _now_ts()
        optional_cols = self._get_optional_doc_chunks_columns()
        chunk_ids, chunk_rows = self._prepare_chunk_rows(
            version_id, library_id, chunks, optional_cols, now
        )

        base_cols = (
            "id",
            "version_id",
            "library_id",
            "url",
            "title",
            "chunk_index",
            "content",
            "heading_path",
            "created_at",
        )
        all_cols = base_cols + tuple(optional_cols)

        # Security: Validate all column names against a strict allowlist.
        for c in all_cols:
            if c not in _DOC_CHUNKS_COLUMNS:
                raise ValueError(f"Unauthorized doc_chunks column: {c}")

        # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        self._conn.executemany(
            f"INSERT INTO doc_chunks ({', '.join(all_cols)}) "
            f"VALUES ({', '.join('?' * len(all_cols))})",
            chunk_rows,
        )

        self._add_chunk_vectors(chunk_ids, embeddings)

        self._conn.commit()
        return len(chunks)

    def _add_chunk_vectors(
        self,
        chunk_ids: list[str],
        embeddings: list[list[float]] | None,
    ) -> None:
        """Batch insert vector embeddings if available."""
        if not (self._vec_enabled and embeddings):
            return

        vec_rows = []
        for i, emb in enumerate(embeddings):
            if i < len(chunk_ids) and emb:
                try:
                    vec_rows.append((chunk_ids[i], _serialize_f32(emb)))
                except Exception as e:
                    # Per-chunk skip is a real degrade (the other chunks keep
                    # their vectors and this one stays keyword-searchable), but
                    # it must name the chunk so a systematic producer bug is
                    # traceable instead of showing up as thin search results.
                    logger.warning(
                        f"Dropping the embedding for chunk {chunk_ids[i]}: "
                        f"cannot serialize {type(emb).__name__} "
                        f"({type(e).__name__}: {e}); the chunk will be "
                        "keyword-searchable only"
                    )

        if vec_rows:
            try:
                self._conn.executemany(
                    "INSERT INTO doc_chunks_vec (id, embedding) VALUES (?, ?)",
                    vec_rows,
                )
            except Exception as e:
                # Previously logged at debug and swallowed: add_chunks still
                # returned the full chunk count, so the caller stamped the
                # version 'indexed' over a database that could not answer a
                # single semantic query. Roll the whole batch back (the
                # doc_chunks INSERT above shares this open transaction) and let
                # the caller see the failure.
                logger.error(
                    f"Vector insert failed for {len(vec_rows)} of "
                    f"{len(chunk_ids)} chunks in {self._db_path} "
                    f"({type(e).__name__}: {e}); rolling back the chunk batch"
                )
                self._conn.rollback()
                raise

    def _prepare_chunk_rows(
        self,
        version_id: str,
        library_id: str,
        chunks: list[dict],
        optional_cols: list[str],
        now: float,
    ) -> tuple[list[str], list[tuple]]:
        """Generate chunk IDs and prepare rows for database insertion."""
        chunk_ids = [new_chunk_id() for _ in chunks]
        chunk_rows = []
        for i, chunk in enumerate(chunks):
            row = [
                chunk_ids[i],
                version_id,
                library_id,
                chunk.get("url", ""),
                chunk.get("title", ""),
                chunk.get("chunk_index", i),
                chunk["content"],
                chunk.get("heading_path", ""),
                now,
            ]
            for col in optional_cols:
                row.append(chunk.get(col))
            chunk_rows.append(tuple(row))
        return chunk_ids, chunk_rows

    def _get_optional_doc_chunks_columns(self) -> list[str]:
        """Detect optional columns in doc_chunks table."""
        existing_cols = {
            r[0]
            for r in self._conn.execute(
                "SELECT name FROM pragma_table_info(?)", ("doc_chunks",)
            ).fetchall()
        }
        return [
            c
            for c in (
                "topic",
                "section",
                "content_hash",
                "token_count",
                "summary",
                "summary_provider",
            )
            if c in existing_cols
        ]

    def clear_version_chunks(self, version_id: str) -> int:
        """Remove all chunks for a version (before re-indexing)."""
        if self._vec_enabled:
            # Bulk delete vector entries in a single query instead of N
            # individual DELETEs (eliminates N+1 pattern).
            try:
                self._conn.execute(
                    "DELETE FROM doc_chunks_vec WHERE id IN "
                    "(SELECT id FROM doc_chunks WHERE version_id = ?)",
                    (version_id,),
                )
            except Exception as e:
                logger.warning(
                    f"Failed to delete vector chunks: {e}",
                )

        cursor = self._conn.execute(
            "DELETE FROM doc_chunks WHERE version_id = ?", (version_id,)
        )
        self._conn.commit()
        return cursor.rowcount

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------

    def _combine_scores(
        self,
        fts_scores: dict[str, float],
        vec_scores: dict[str, float],
        fts_chunks: dict[str, dict],
    ) -> list[tuple[str, float]]:
        """Combine FTS and vector scores using RRF or FTS-only scoring."""
        all_ids = fts_scores.keys() | vec_scores.keys()
        scored: list[tuple[str, float]] = []

        if vec_scores:
            # RRF fusion when both FTS and vector signals available
            k = 60
            # __getitem__ is the dict's own lookup; a lambda here would add a
            # Python-level call for every element sorted.
            fts_ranked = sorted(fts_scores, key=fts_scores.__getitem__, reverse=True)
            vec_ranked = sorted(vec_scores, key=vec_scores.__getitem__, reverse=True)
            fts_rank = {cid: i + 1 for i, cid in enumerate(fts_ranked)}
            vec_rank = {cid: i + 1 for i, cid in enumerate(vec_ranked)}

            default_rank = len(all_ids)

            for cid in all_ids:
                fr = fts_rank.get(cid, default_rank)
                vr = vec_rank.get(cid, default_rank)
                rrf = 1.0 / (k + fr) + 1.0 / (k + vr)
                # Small quality boost
                chunk = fts_chunks.get(cid)
                quality = _chunk_quality_score(chunk["content"]) if chunk else 0.0
                scored.append((cid, rrf + quality * 0.005))
        else:
            # FTS-only: normalized score + quality boost
            for cid in fts_scores:
                fts = fts_scores[cid]
                chunk = fts_chunks.get(cid)
                quality = _chunk_quality_score(chunk["content"]) if chunk else 0.0
                score = fts * 0.85 + quality * 0.15
                scored.append((cid, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def _run_fts_search(
        self,
        fts_queries: list[str],
        library_id: str | None,
        version_id: str | None,
        candidate_limit: int,
    ) -> tuple[dict[str, float], dict[str, dict]]:
        """Execute FTS5 search with tiered queries and min-max normalization."""
        fts_scores: dict[str, float] = {}
        fts_chunks: dict[str, dict] = {}

        if not fts_queries:
            return fts_scores, fts_chunks

        try:
            subqueries = []
            fts_params: list = []
            for fts_query in fts_queries:
                sq = f"""
                    SELECT * FROM (
                        SELECT c.*,
                               l.name AS _library_name,
                               bm25(doc_chunks_fts, 0.0, 2.0, 3.0, 2.0) AS bm25_score
                        FROM doc_chunks_fts f
                        JOIN doc_chunks c ON f.id = c.id
                        LEFT JOIN libraries l ON c.library_id = l.id
                        WHERE doc_chunks_fts MATCH ?
                        {" AND c.library_id = ?" if library_id else ""}
                        {" AND c.version_id = ?" if version_id else ""}
                        ORDER BY bm25_score LIMIT ?
                    )
                """
                fts_params.append(fts_query)
                if library_id:
                    fts_params.append(library_id)
                if version_id:
                    fts_params.append(version_id)
                fts_params.append(candidate_limit)
                subqueries.append(sq)

            # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            full_fts_sql = " UNION ALL ".join(subqueries)
            rows = self._conn.execute(full_fts_sql, fts_params).fetchall()
            for row in rows:
                chunk = dict(row)
                cid = chunk["id"]
                score = -chunk.pop("bm25_score", 0)
                # Keep the best score across tiers (PHRASE > AND > OR)
                if cid not in fts_scores or score > fts_scores[cid]:
                    fts_scores[cid] = score
                    fts_chunks[cid] = chunk
        except Exception as e:
            # An FTS5 syntax/schema error returns the same empty dict as "no
            # document matched", and search() then reports an empty result set.
            # The return shape is deliberately unchanged (a broken keyword tier
            # must not take down a query the vector tier can still answer), so
            # this log is the only place the difference is recorded.
            logger.warning(
                f"FTS search failed for {fts_queries!r} "
                f"(library_id={library_id}, version_id={version_id}); "
                f"returning zero keyword matches: {type(e).__name__}: {e}"
            )

        # Min-max normalize FTS scores to 0-1
        if fts_scores:
            min_f = min(fts_scores.values())
            max_f = max(fts_scores.values())
            rng = max_f - min_f
            if rng > 0:
                fts_scores = {k: (v - min_f) / rng for k, v in fts_scores.items()}
            else:
                fts_scores = dict.fromkeys(fts_scores, 1.0)

        return fts_scores, fts_chunks

    def _run_vec_search(
        self,
        query_embedding: list[float] | None,
        library_id: str | None,
        version_id: str | None,
        candidate_limit: int,
        fts_chunks: dict[str, dict],
    ) -> dict[str, float]:
        """Execute vector matching and update fts_chunks for new hits."""
        vec_scores: dict[str, float] = {}
        if self._vec_enabled and query_embedding:
            try:
                vec_sql = """
                    SELECT v.id, v.distance, c.*, l.name AS _library_name
                    FROM doc_chunks_vec v
                    JOIN doc_chunks c ON v.id = c.id
                    LEFT JOIN libraries l ON c.library_id = l.id
                    WHERE v.embedding MATCH ?
                """
                vec_params: list = [_serialize_f32(query_embedding)]

                if library_id:
                    vec_sql += " AND c.library_id = ?"
                    vec_params.append(library_id)
                if version_id:
                    vec_sql += " AND c.version_id = ?"
                    vec_params.append(version_id)

                vec_sql += " ORDER BY v.distance LIMIT ?"
                vec_params.append(candidate_limit)

                vec_rows = self._conn.execute(vec_sql, vec_params).fetchall()
                for vr in vec_rows:
                    chunk_id = vr["id"]
                    vec_scores[chunk_id] = max(0.0, 1.0 - vr["distance"])

                    # The vector query already joins the chunk row, so reuse it
                    # here. Looking it up again would be one SELECT per result.
                    if chunk_id not in fts_chunks:
                        chunk_data = dict(vr)
                        chunk_data.pop("distance", None)
                        fts_chunks[chunk_id] = chunk_data
            except Exception as e:
                # Same shape as the FTS tier: an empty vec_scores is
                # indistinguishable from "nothing was semantically close", so a
                # dims mismatch or a missing doc_chunks_vec table used to read
                # as a merely disappointing result set.
                logger.warning(
                    f"Vector search failed (library_id={library_id}, "
                    f"version_id={version_id}, dims="
                    f"{len(query_embedding)}); returning zero semantic "
                    f"matches: {type(e).__name__}: {e}"
                )
        return vec_scores

    def _prefetch_adjacent_chunks(
        self,
        scored: list[tuple[str, float]],
        fts_chunks: dict[str, dict],
    ) -> dict[tuple[str, str, int], str]:
        """Batch fetch adjacent chunks for cross-chunk context."""
        _adj_keys: list[tuple[str, str, int]] = []
        for _cid, _sc in scored:
            _ch = fts_chunks.get(_cid)
            if not _ch:
                continue
            _url = _ch.get("url", "")
            _ver = _ch.get("version_id", "")
            _idx = _ch.get("chunk_index", -1)
            if _url and _ver and _idx >= 0:
                _adj_keys.append((_url, _ver, _idx - 1))
                _adj_keys.append((_url, _ver, _idx + 1))

        _adj_map: dict[tuple[str, str, int], str] = {}
        if not _adj_keys:
            return _adj_map

        _unique_keys = sorted(set(_adj_keys))
        _batch_size = (32766 if sqlite3.sqlite_version_info >= (3, 32, 0) else 999) // 3

        for i in range(0, len(_unique_keys), _batch_size):
            _batch = _unique_keys[i : i + _batch_size]
            _placeholders = ",".join(["(?,?,?)"] * len(_batch))
            _params = [item for key_tuple in _batch for item in key_tuple]

            sql = (
                "SELECT url, version_id, chunk_index, content "
                "FROM doc_chunks "
                "WHERE (url, version_id, chunk_index) IN (" + _placeholders + ")"
            )
            # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            rows = self._conn.execute(sql, _params).fetchall()
            for r in rows:
                _adj_map[(r["url"], r["version_id"], r["chunk_index"])] = r["content"]
        return _adj_map

    def search(
        self,
        query: str,
        library_name: str | None = None,
        version: str | None = None,
        limit: int = 10,
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        """Hybrid search: FTS5 + optional vector + quality scoring.

        Uses tiered FTS5 queries (AND -> OR fallback), BM25 column weights
        (boosting title/heading matches), min-max score normalization,
        and RRF fusion when vector search is available.
        Recency is intentionally excluded -- all doc chunks share the same
        indexing timestamp, making recency meaningless for static docs.

        Args:
            query: Search query text
            library_name: Filter by library name
            version: Filter by version
            limit: Max results
            query_embedding: Optional embedding vector for semantic search

        Returns:
            List of chunk dicts sorted by relevance score
        """
        # Resolve library/version filters
        library_id = None
        version_id = None
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

        fts_queries = _build_fts_queries(query)
        fts_scores, fts_chunks = self._run_fts_search(
            fts_queries, library_id, version_id, candidate_limit
        )

        vec_scores = self._run_vec_search(
            query_embedding,
            library_id,
            version_id,
            candidate_limit,
            fts_chunks,
        )

        scored = self._combine_scores(fts_scores, vec_scores, fts_chunks)
        _adj_map = self._prefetch_adjacent_chunks(scored, fts_chunks)

        # Build results with cross-chunk context + URL diversity limit
        # Cap results per URL to avoid returning 4-5 chunks from the same page
        max_per_url = 2
        url_counts: dict[str, int] = {}
        results = []

        for cid, score in scored:
            if len(results) >= limit:
                break
            chunk = fts_chunks.get(cid)
            if not chunk:
                continue
            chunk_url = chunk.get("url", "")
            if chunk_url:
                url_counts[chunk_url] = url_counts.get(chunk_url, 0) + 1
                if url_counts[chunk_url] > max_per_url:
                    continue

            result: dict = {
                "content": chunk["content"],
                "title": chunk.get("title", ""),
                "url": chunk.get("url", ""),
                "heading_path": chunk.get("heading_path", ""),
                "library": chunk.get("_library_name", ""),
                "score": round(score, 4),
                # Phase 2 (spec section 5.4) — propagate when columns exist.
                "topic": chunk.get("topic"),
                "section": chunk.get("section"),
                "token_count": chunk.get("token_count"),
                "version_id": chunk.get("version_id"),
            }

            # Cross-chunk context: include adjacent chunks for better RAG
            chunk_url = chunk.get("url", "")
            chunk_idx = chunk.get("chunk_index", -1)
            ver_id_val = chunk.get("version_id", "")
            if chunk_url and ver_id_val and chunk_idx >= 0:
                ctx_before = _adj_map.get((chunk_url, ver_id_val, chunk_idx - 1))
                if ctx_before:
                    result["context_before"] = ctx_before
                ctx_after = _adj_map.get((chunk_url, ver_id_val, chunk_idx + 1))
                if ctx_after:
                    result["context_after"] = ctx_after

            results.append(result)

        return results

    # -----------------------------------------------------------------------
    # Export / Import (JSONL for sync)
    # -----------------------------------------------------------------------

    def export_jsonl(self) -> str:
        """Export all docs data as JSONL for sync."""
        lines = []

        # Export libraries (using SQLite native JSON serialization for performance)
        for row in self._conn.execute(
            """
            SELECT json_insert(json_object(
                'id', id, 'name', name, 'docs_url', docs_url,
                'registry', registry, 'description', description,
                'created_at', created_at, 'updated_at', updated_at
            ), '$._type', 'library')
            FROM libraries ORDER BY name
            """
        ).fetchall():
            lines.append(row[0])

        # Export versions
        for row in self._conn.execute(
            """
            SELECT json_insert(json_object(
                'id', id, 'library_id', library_id, 'version', version,
                'docs_url', docs_url, 'indexed_at', indexed_at,
                'page_count', page_count, 'chunk_count', chunk_count,
                'status', status
            ), '$._type', 'version')
            FROM versions ORDER BY library_id
            """
        ).fetchall():
            lines.append(row[0])

        # Export chunks (without embeddings — re-generate on target)
        for row in self._conn.execute(
            """
            SELECT json_insert(json_object(
                'id', id, 'version_id', version_id, 'library_id', library_id,
                'url', url, 'title', title, 'chunk_index', chunk_index,
                'content', content, 'heading_path', heading_path,
                'created_at', created_at
            ), '$._type', 'chunk')
            FROM doc_chunks ORDER BY library_id, chunk_index
            """
        ).fetchall():
            lines.append(row[0])

        return "\n".join(lines)

    def _clear_for_import(self) -> None:
        """Clear all tables before a "replace" import."""
        if self._vec_enabled:
            try:
                self._conn.execute("DELETE FROM doc_chunks_vec")
            except Exception:
                logger.warning(
                    "Failed to clear vector table during import replace",
                    exc_info=True,
                )
        self._conn.execute("DELETE FROM doc_chunks")
        self._conn.execute("DELETE FROM versions")
        self._conn.execute("DELETE FROM libraries")

    def _get_existing_ids_for_import(self, table: str, items: list[dict]) -> set[str]:
        """Fetch existing IDs for a set of items in batches."""
        allowed_queries = {
            "libraries": "SELECT id FROM libraries WHERE id IN ({})",
            "versions": "SELECT id FROM versions WHERE id IN ({})",
            "doc_chunks": "SELECT id FROM doc_chunks WHERE id IN ({})",
        }
        if table not in allowed_queries:
            raise ValueError(f"Invalid table name: {table}")
        if not items:
            return set()
        ids = [obj["id"] for obj in items]
        existing = set()
        batch_size = 32766 if sqlite3.sqlite_version_info >= (3, 32, 0) else 999
        for i in range(0, len(ids), batch_size):
            batch = ids[i : i + batch_size]
            placeholders = ",".join("?" * len(batch))
            # Safe because table is strictly validated against allowlist
            # and placeholders string contains only static "?" and ",".
            query = allowed_queries[table].replace("{}", placeholders)
            # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            res = self._conn.execute(query, batch).fetchall()
            existing.update(r[0] for r in res)
        return existing

    def _import_libraries(self, libraries: list[dict], mode: str, stats: dict) -> None:
        """Import library entities."""
        if not libraries:
            return
        existing_libs = (
            self._get_existing_ids_for_import("libraries", libraries)
            if mode == "merge"
            else set()
        )
        to_insert = []
        for obj in libraries:
            if mode == "merge" and obj["id"] in existing_libs:
                stats["skipped"] += 1
                continue
            if mode == "merge":
                existing_libs.add(obj["id"])
            to_insert.append(
                (
                    obj["id"],
                    obj["name"],
                    obj.get("docs_url"),
                    obj.get("registry"),
                    obj.get("description"),
                    obj["created_at"],
                    obj["updated_at"],
                )
            )
        if to_insert:
            self._conn.executemany(
                """INSERT OR REPLACE INTO libraries
                   (id, name, docs_url, registry, description, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                to_insert,
            )
            stats["libraries"] += len(to_insert)

    def _import_versions(self, versions: list[dict], mode: str, stats: dict) -> None:
        """Import version entities."""
        if not versions:
            return
        existing_vers = (
            self._get_existing_ids_for_import("versions", versions)
            if mode == "merge"
            else set()
        )
        to_insert = []
        for obj in versions:
            if mode == "merge" and obj["id"] in existing_vers:
                stats["skipped"] += 1
                continue
            if mode == "merge":
                existing_vers.add(obj["id"])
            to_insert.append(
                (
                    obj["id"],
                    obj["library_id"],
                    obj["version"],
                    obj.get("docs_url"),
                    obj.get("indexed_at"),
                    obj.get("page_count", 0),
                    obj.get("chunk_count", 0),
                    obj.get("status", "indexed"),
                )
            )
        if to_insert:
            self._conn.executemany(
                """INSERT OR REPLACE INTO versions
                   (id, library_id, version, docs_url, indexed_at, page_count, chunk_count, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                to_insert,
            )
            stats["versions"] += len(to_insert)

    def _import_chunks(self, chunks: list[dict], mode: str, stats: dict) -> None:
        """Import chunk entities."""
        if not chunks:
            return
        existing_chunks = (
            self._get_existing_ids_for_import("doc_chunks", chunks)
            if mode == "merge"
            else set()
        )
        to_insert = []
        for obj in chunks:
            if mode == "merge" and obj["id"] in existing_chunks:
                stats["skipped"] += 1
                continue
            if mode == "merge":
                existing_chunks.add(obj["id"])
            to_insert.append(
                (
                    obj["id"],
                    obj["version_id"],
                    obj["library_id"],
                    obj.get("url", ""),
                    obj.get("title", ""),
                    obj.get("chunk_index", 0),
                    obj["content"],
                    obj.get("heading_path", ""),
                    obj["created_at"],
                )
            )
        if to_insert:
            self._conn.executemany(
                """INSERT OR REPLACE INTO doc_chunks
                   (id, version_id, library_id, url, title, chunk_index, content, heading_path, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                to_insert,
            )
            stats["chunks"] += len(to_insert)

    def import_jsonl(self, data: str, mode: str = "merge") -> dict:
        """Import JSONL data. mode: merge (skip existing) or replace (clear first)."""
        stats = {"libraries": 0, "versions": 0, "chunks": 0, "skipped": 0}

        if mode == "replace":
            self._clear_for_import()

        lines = data.split("\n")
        libraries, versions, chunks = [], [], []

        for line in lines:
            if not line or line.isspace():
                continue
            obj = json.loads(line)
            obj_type = obj.pop("_type", None)

            if obj_type == "library":
                libraries.append(obj)
            elif obj_type == "version":
                versions.append(obj)
            elif obj_type == "chunk":
                chunks.append(obj)

        self._import_libraries(libraries, mode, stats)
        self._import_versions(versions, mode, stats)
        self._import_chunks(chunks, mode, stats)

        self._conn.commit()
        return stats

    # -----------------------------------------------------------------------
    # Project context (Cabinets — Phase 2 docs_003_project_context)
    # -----------------------------------------------------------------------

    def _ensure_project_context(self) -> bool:
        """Return True iff the project_context table exists."""
        row = self._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='project_context'"
        ).fetchone()
        return row is not None

    def upsert_project_context(
        self,
        project_path: str,
        locked_libraries: list[dict],
        *,
        sub: str = "default",
    ) -> None:
        """Persist a project's locked-library set (Cabinets isolation).

        Args:
            project_path: Absolute project root path.
            locked_libraries: List of ``{"id": <library_id>, "version": <spec>}``.
            sub: Caller namespace (mode-3 isolation); the logical key is
                ``(sub, project_path)``.

        Silently no-ops on pre-Alembic legacy databases that lack the
        ``project_context`` table.
        """
        if not self._ensure_project_context():
            logger.debug(
                "project_context table absent; skipping upsert_project_context"
            )
            return
        now = _now_ts()
        payload = json.dumps(locked_libraries, ensure_ascii=False)
        existing = self._conn.execute(
            "SELECT created_at FROM project_context "
            "WHERE sub = ? AND project_path = ?",
            (sub, project_path),
        ).fetchone()
        if existing:
            self._conn.execute(
                "UPDATE project_context "
                "SET locked_libraries = ?, last_used_at = ? "
                "WHERE sub = ? AND project_path = ?",
                (payload, now, sub, project_path),
            )
        else:
            self._conn.execute(
                "INSERT INTO project_context "
                "(project_path, sub, locked_libraries, created_at, last_used_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (project_path, sub, payload, now, now),
            )
        self._conn.commit()

    def get_project_context(
        self, project_path: str, *, sub: str = "default"
    ) -> dict | None:
        """Return the lock entry for a project, or None if not locked."""
        if not self._ensure_project_context():
            return None
        row = self._conn.execute(
            "SELECT project_path, locked_libraries, created_at, last_used_at "
            "FROM project_context WHERE sub = ? AND project_path = ?",
            (sub, project_path),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        try:
            libs = json.loads(result["locked_libraries"])
            if not isinstance(libs, list):
                libs = []
            result["locked_libraries"] = libs
        except (TypeError, json.JSONDecodeError) as e:
            # An unreadable lock silently becomes "no libraries locked", which
            # is exactly the shape of a project that was never locked -- so
            # Cabinets isolation switches itself off with no trace.
            logger.warning(
                f"project_context row for {project_path!r} has unreadable "
                f"locked_libraries ({type(e).__name__}: {e}); treating the "
                "project as unlocked"
            )
            result["locked_libraries"] = []
        return result

    def touch_project_context(
        self, project_path: str, *, sub: str = "default"
    ) -> None:
        """Update last_used_at — call before each docs_query that honors a lock."""
        if not self._ensure_project_context():
            return
        self._conn.execute(
            "UPDATE project_context SET last_used_at = ? "
            "WHERE sub = ? AND project_path = ?",
            (_now_ts(), sub, project_path),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close database connection."""
        try:
            self._conn.close()
        except Exception:
            pass
