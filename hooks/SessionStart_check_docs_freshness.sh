#!/usr/bin/env bash
# SessionStart hook — surface a freshness warning when Tier 1 libraries
# are stale (>7 days since last_indexed_at).
#
# Spec section 12.2 + Phase 2 plan Task 11 step 8.
#
# Output: prints a one-line warning to stderr if any Tier 1 library is
# stale. Exits 0 either way (advisory only — never blocks the session).

set -euo pipefail

DB_PATH="${WET_DOCS_DB_PATH:-$HOME/.wet-mcp/docs.db}"

if [ ! -f "$DB_PATH" ]; then
    exit 0
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
    # sqlite3 CLI not installed — skip silently. Warmup still runs at
    # next server startup, so this is best-effort only.
    exit 0
fi

NOW=$(date +%s)
SEVEN_DAYS_AGO=$((NOW - 7 * 24 * 60 * 60))

# Count Tier 1 libraries whose last_indexed_at is older than 7 days.
STALE=$(
    sqlite3 "$DB_PATH" \
        "SELECT COUNT(*) FROM libraries
         WHERE tier = 1
         AND (last_indexed_at IS NULL OR last_indexed_at < $SEVEN_DAYS_AGO)" \
        2>/dev/null || echo 0
)

if [ "$STALE" -gt 0 ]; then
    >&2 echo "wet-mcp: $STALE Tier 1 libraries are >7 days stale."
    >&2 echo "Refresh suggestion:  config(action='docs_reindex', scope='tier1')"
    >&2 echo "  or run:  uv run python scripts/build_tier1_index.py"
fi

exit 0
