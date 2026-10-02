#!/usr/bin/env bash
# Verify CLAUDE.md and AGENTS.md are kept in sync (body-identical).
#
# Allowed difference: line 1 only.
#   CLAUDE.md line 1 MUST be:  # wet-mcp
#   AGENTS.md line 1 MUST be:  # AGENTS.md - wet-mcp
# Lines 2..EOF MUST be byte-identical.
#
# Exits 1 on any drift; 0 on clean sync.

set -e

CLAUDE_FILE="CLAUDE.md"
AGENTS_FILE="AGENTS.md"

if [ ! -f "$CLAUDE_FILE" ] || [ ! -f "$AGENTS_FILE" ]; then
  echo "sync-claude-agents: missing $CLAUDE_FILE or $AGENTS_FILE in repo root."
  exit 1
fi

CLAUDE_HEAD=$(head -n 1 "$CLAUDE_FILE")
AGENTS_HEAD=$(head -n 1 "$AGENTS_FILE")

if [ "$CLAUDE_HEAD" != "# wet-mcp" ]; then
  echo "sync-claude-agents: CLAUDE.md line 1 must be '# wet-mcp' (got: '$CLAUDE_HEAD')."
  exit 1
fi

if [ "$AGENTS_HEAD" != "# AGENTS.md - wet-mcp" ]; then
  echo "sync-claude-agents: AGENTS.md line 1 must be '# AGENTS.md - wet-mcp' (got: '$AGENTS_HEAD')."
  exit 1
fi

CLAUDE_BODY=$(tail -n +2 "$CLAUDE_FILE")
AGENTS_BODY=$(tail -n +2 "$AGENTS_FILE")

if [ "$CLAUDE_BODY" != "$AGENTS_BODY" ]; then
  echo "sync-claude-agents: CLAUDE.md and AGENTS.md drift detected (body lines 2..EOF must match)."
  diff <(echo "$CLAUDE_BODY") <(echo "$AGENTS_BODY") || true
  exit 1
fi

exit 0
