"""TTL-based cache for web operations (search, extract, crawl, map).

Uses SQLite for persistence across restarts. Cache entries expire based
on configurable TTL per action type. A re-entrant lock serializes access to
the shared SQLite connection; WAL mode provides persistence-friendly reads.

Cache is transparent — callers use ``get``/``set`` and the cache handles
expiry automatically. Old entries are purged periodically.

Cache entries are namespaced per caller: the key folds in the caller's
``sub`` namespace (mode-3 isolation, spec §4 Q2), so one process serving
N users never leaks results across callers. Content snapshots are kept
per ``(sub, url)`` rather than per URL alone.
"""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from threading import RLock

from loguru import logger

# Default TTL per action (seconds)
_DEFAULT_TTLS: dict[str, int] = {
    "search": 3600,  # 1 hour
    "research": 3600,  # 1 hour
    "extract": 86400,  # 1 day
    "crawl": 86400,  # 1 day
    "map": 86400,  # 1 day
}

# Purge expired entries every N operations
_PURGE_INTERVAL = 50

# Snapshots kept per URL for change tracking (extract action="diff")
_SNAPSHOT_RETENTION = 5


def _cache_key(action: str, params: dict, sub: str = "default") -> str:
    """Generate a deterministic cache key from caller namespace + action + params.

    The ``sub`` namespace is folded into the hashed dict (mode-3 isolation,
    spec §4 Q2) instead of concatenated onto the payload, so params of a
    different shape can never collide across namespaces.
    """
    # Sort keys for deterministic hashing
    raw = json.dumps(
        {"action": action, "sub": sub, "params": params},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class WebCache:
    """SQLite-backed TTL cache for web operations."""

    def __init__(self, db_path: Path, ttls: dict[str, int] | None = None):
        self._db_path = db_path
        self._ttls = {**_DEFAULT_TTLS, **(ttls or {})}
        self._op_count = 0
        self._lock = RLock()

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._conn.execute("PRAGMA mmap_size = 268435456")  # 256MB mmap
        self._conn.execute("PRAGMA temp_store = MEMORY")
        self._conn.execute("PRAGMA cache_size = -64000")  # 64MB cache (KB)

        self._create_tables()
        logger.debug(f"WebCache initialized at {db_path}")

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS web_cache (
                key TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                params TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0,
                sub TEXT NOT NULL DEFAULT 'default'
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_web_cache_expires
            ON web_cache(expires_at)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_web_cache_action
            ON web_cache(action)
        """)
        # Append-only, unlike ``web_cache``'s INSERT OR REPLACE — a fresh
        # extract must not overwrite the prior fetch, or there is nothing
        # left to diff against.
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                content TEXT NOT NULL,
                sub TEXT NOT NULL DEFAULT 'default'
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_url_fetched
            ON snapshots(url, fetched_at DESC)
        """)
        # Idempotent column adds for legacy caches that pre-date per-caller
        # namespacing (mode-3 isolation, spec §4 Q2). Fresh tables already
        # carry ``sub`` in the DDL above, so the ALTER raises duplicate-column
        # and is swallowed.
        for sql in (
            "ALTER TABLE web_cache ADD COLUMN sub TEXT NOT NULL DEFAULT 'default'",
            "ALTER TABLE snapshots ADD COLUMN sub TEXT NOT NULL DEFAULT 'default'",
        ):
            try:
                self._conn.execute(sql)
                self._conn.commit()
                logger.debug("Migrated cache table: added sub column")
            except sqlite3.OperationalError:
                pass  # Column already exists
        self._conn.commit()

    def get(self, action: str, params: dict, sub: str = "default") -> str | None:
        """Get cached result if exists and not expired (within ``sub``)."""
        key = _cache_key(action, params, sub)
        now = time.time()

        # One connection is shared by asyncio worker threads, so the update
        # and transaction close must remain one serialized operation.
        with self._lock:
            row = self._conn.execute(
                "UPDATE web_cache SET hit_count = hit_count + 1 WHERE key = ? AND expires_at > ? RETURNING content",
                (key, now),
            ).fetchone()
            self._conn.commit()

        if row:
            logger.debug(f"Cache HIT: {action} ({key[:12]}...)")
            return row["content"]

        logger.debug(f"Cache MISS: {action} ({key[:12]}...)")
        return None

    def get_with_age(
        self, action: str, params: dict, sub: str = "default"
    ) -> tuple[str, int] | None:
        """Like ``get`` but also returns ``cache_age_seconds`` (now - created_at).

        Returns ``None`` on miss or expiry. Used by callers that want to
        derive a freshness signal from the cache age.
        """
        key = _cache_key(action, params, sub)
        now = time.time()

        with self._lock:
            row = self._conn.execute(
                "UPDATE web_cache SET hit_count = hit_count + 1 WHERE key = ? AND expires_at > ? RETURNING content, created_at",
                (key, now),
            ).fetchone()
            self._conn.commit()

        if row:
            age = max(0, int(now - row["created_at"]))
            logger.debug(f"Cache HIT: {action} ({key[:12]}...) age={age}s")
            return row["content"], age

        logger.debug(f"Cache MISS: {action} ({key[:12]}...)")
        return None

    def get_stale_with_age(
        self, action: str, params: dict, sub: str = "default"
    ) -> tuple[str, int] | None:
        """Serve a TTL-expired entry for stale-while-revalidate reads.

        Returns ``(content, age)`` even when ``expires_at`` has passed, as
        long as the entry is still within the stale window (one extra TTL
        past expiry, so total staleness never exceeds 2x the entry's own
        TTL); ``None`` on miss or once the stale window is exhausted. The
        caller decides freshness: the existing per-result freshness signal
        already flags ``"stale"`` once ``age > ttl / 2``.
        """
        key = _cache_key(action, params, sub)
        now = time.time()

        with self._lock:
            row = self._conn.execute(
                """SELECT content, created_at, expires_at FROM web_cache
                   WHERE key = ? AND expires_at + (expires_at - created_at) > ?""",
                (key, now),
            ).fetchone()
        if row is None:
            logger.debug(f"Cache STALE-MISS: {action} ({key[:12]}...)")
            return None

        age = max(0, int(now - row["created_at"]))
        logger.debug(f"Cache STALE-HIT: {action} ({key[:12]}...) age={age}s")
        return row["content"], age

    def set(
        self,
        action: str,
        params: dict,
        content: str,
        ttl_override: int | None = None,
        sub: str = "default",
    ) -> None:
        """Store result in cache with TTL.

        ``ttl_override`` lets callers pin a custom TTL (e.g. 300s for
        time-filtered search queries) without mutating the per-action
        defaults shared by all callers. The entry is stored under the
        caller's ``sub`` namespace; the persisted ``params`` column keeps
        the original params JSON, not the sub-wrapped key payload.
        """
        key = _cache_key(action, params, sub)
        now = time.time()
        ttl = ttl_override if ttl_override is not None else self._ttls.get(action, 3600)
        expires_at = now + ttl

        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO web_cache
                   (key, action, params, content, created_at, expires_at, hit_count, sub)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                (
                    key,
                    action,
                    json.dumps(params, sort_keys=True),
                    content,
                    now,
                    expires_at,
                    sub,
                ),
            )
            self._conn.commit()

            self._op_count += 1
            if self._op_count >= _PURGE_INTERVAL:
                self._purge_expired()
                self._op_count = 0

        logger.debug(f"Cache SET: {action} ({key[:12]}...) TTL={ttl}s")

    def record_snapshot(self, url: str, content: str, sub: str = "default") -> None:
        """Append a content snapshot for ``(sub, url)``, pruning to the last N.

        Unlike ``set()``, this never overwrites — each call adds a new row so
        ``latest_snapshots`` has history to diff against. Retention keeps at
        most ``_SNAPSHOT_RETENTION`` rows per ``(sub, url)`` pair.
        """
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO snapshots (url, fetched_at, content, sub) "
                "VALUES (?, ?, ?, ?)",
                (url, now, content, sub),
            )
            self._conn.execute(
                """
                DELETE FROM snapshots
                WHERE sub = ? AND url = ? AND id NOT IN (
                    SELECT id FROM snapshots
                    WHERE sub = ? AND url = ?
                    ORDER BY fetched_at DESC, id DESC
                    LIMIT ?
                )
                """,
                (sub, url, sub, url, _SNAPSHOT_RETENTION),
            )
            self._conn.commit()
        logger.debug(f"Snapshot recorded for {url}")

    def latest_snapshots(
        self, url: str, n: int = 2, sub: str = "default"
    ) -> list[dict]:
        """Return up to ``n`` most recent snapshots for ``(sub, url)``, newest first.

        Each item is ``{"fetched_at": float, "content": str}``.
        """
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT fetched_at, content FROM snapshots
                WHERE sub = ? AND url = ?
                ORDER BY fetched_at DESC, id DESC
                LIMIT ?
                """,
                (sub, url, n),
            ).fetchall()
        return [
            {"fetched_at": row["fetched_at"], "content": row["content"]} for row in rows
        ]

    def _purge_expired(self) -> None:
        """Remove expired cache entries."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM web_cache WHERE expires_at <= ?",
                (time.time(),),
            )
            self._conn.commit()
            purged = cursor.rowcount
        if purged > 0:
            logger.debug(f"Purged {purged} expired cache entries")

    def clear(self, action: str | None = None, sub: str = "default") -> int:
        """Clear this namespace's cache entries.

        If action specified, only clear that action; only rows belonging to
        ``sub`` are ever removed — other callers' entries are untouched.
        """
        with self._lock:
            if action:
                cursor = self._conn.execute(
                    "DELETE FROM web_cache WHERE sub = ? AND action = ?",
                    (sub, action),
                )
            else:
                cursor = self._conn.execute(
                    "DELETE FROM web_cache WHERE sub = ?", (sub,)
                )
            self._conn.commit()
            return cursor.rowcount

    def stats(self, sub: str | None = None) -> dict:
        """Get cache statistics.

        With ``sub``, returns counts for that caller namespace only;
        without it, counts span every namespace.
        """
        now = time.time()
        with self._lock:
            sql = """
                SELECT action,
                       COUNT(*) as total,
                       SUM(CASE WHEN expires_at > ? THEN 1 ELSE 0 END) as active,
                       SUM(hit_count) as total_hits
                FROM web_cache
            """
            params: tuple = (now,)
            if sub is not None:
                sql += "WHERE sub = ? "
                params += (sub,)
            rows = self._conn.execute(sql + "GROUP BY action", params).fetchall()

        return {
            row["action"]: {
                "total": row["total"],
                "active": row["active"],
                "hits": row["total_hits"],
            }
            for row in rows
        }

    def close(self) -> None:
        """Close database connection."""
        try:
            with self._lock:
                self._conn.close()
        except Exception as e:
            logger.debug(f"Failed to close cache database connection: {e}")
