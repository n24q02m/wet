#!/usr/bin/env bash
# UserPromptSubmit hook -- pre-warm wet-mcp docs cache when the user's
# prompt mentions a known Tier 1 library import.
#
# Spec section 12.2 NICE + Phase 3 plan task 10. Best-effort only;
# never blocks the prompt and exits 0 on any error.
#
# How it works:
#   1. Read the user's prompt from $CLAUDE_USER_PROMPT (or stdin).
#   2. Extract library identifiers from common import keyword patterns
#      (Python, JavaScript/TypeScript, Go).
#   3. For each match that is a Tier 1 library, fire-and-forget a
#      docs_resolve warmup so subsequent docs_query calls hit a fresh
#      OS page-cache for the library chunks.
#
# The hook intentionally does NOT block; the warmup is detached.

set -euo pipefail

PROMPT="${CLAUDE_USER_PROMPT:-}"
if [ -z "$PROMPT" ]; then
    # Some harnesses pipe the prompt on stdin instead.
    if [ -t 0 ]; then
        exit 0
    fi
    PROMPT=$(cat || true)
fi

if [ -z "$PROMPT" ]; then
    exit 0
fi

# Tier 1 library aliases the wet-mcp registry currently knows about.
# The list mirrors tests/fixtures/libraries/tier1_libraries.json so the
# hook stays useful without a runtime DB lookup. Extend cautiously --
# extra entries cost a no-op warmup, missing entries are silent.
TIER1_LIBRARIES=(
    "fastapi"
    "pydantic"
    "starlette"
    "uvicorn"
    "react"
    "next"
    "vue"
    "svelte"
    "django"
    "flask"
    "numpy"
    "pandas"
    "polars"
    "scikit-learn"
    "pytorch"
    "tensorflow"
    "transformers"
    "langchain"
    "anthropic"
    "openai"
)

# Extract candidate identifiers from the prompt.
# Patterns covered:
#   from <pkg> import ...
#   import <pkg>
#   import { ... } from "<pkg>"     (JS/TS)
#   import <pkg> from "..."         (default-import; package follows from)
#   require("<pkg>")
CANDIDATES=$(
    {
        printf "%s\n" "$PROMPT" | grep -oE 'from[[:space:]]+[a-zA-Z0-9_.-]+' | awk '{print $2}'
        printf "%s\n" "$PROMPT" | grep -oE 'import[[:space:]]+[a-zA-Z0-9_.-]+' | awk '{print $2}'
        printf "%s\n" "$PROMPT" | grep -oE 'require\("[a-zA-Z0-9_.@/-]+"\)' | sed -E 's/require\("([^"]+)"\)/\1/'
        printf "%s\n" "$PROMPT" | grep -oE 'from[[:space:]]+"[a-zA-Z0-9_.@/-]+"' | sed -E 's/from[[:space:]]+"([^"]+)"/\1/'
    } 2>/dev/null | sort -u | head -20 || true
)

if [ -z "$CANDIDATES" ]; then
    exit 0
fi

# Match candidates against Tier 1 list (case-insensitive, strip path
# prefixes for sub-imports like "react/jsx-runtime" -> "react").
HITS=()
while IFS= read -r raw; do
    [ -z "$raw" ] && continue
    base=$(printf "%s" "$raw" | tr 'A-Z' 'a-z' | sed -E 's|/.*$||;s|^@[^/]+/||')
    for known in "${TIER1_LIBRARIES[@]}"; do
        if [ "$base" = "$known" ]; then
            HITS+=("$known")
            break
        fi
    done
done <<< "$CANDIDATES"

if [ ${#HITS[@]} -eq 0 ]; then
    exit 0
fi

# Deduplicate hits.
UNIQUE_HITS=$(printf "%s\n" "${HITS[@]}" | sort -u)

# Fire-and-forget docs_resolve warmup. We use the wet-mcp CLI in
# headless mode if available; otherwise log to stderr and exit so the
# operator can see what would have warmed.
WARMUP_LOG="${WET_PREWARM_LOG:-/dev/null}"
if command -v wet-mcp >/dev/null 2>&1; then
    while IFS= read -r lib; do
        [ -z "$lib" ] && continue
        # Detached subshell -- never blocks the user prompt.
        (
            wet-mcp call --tool search --action docs_resolve \
                --query "$lib" >>"$WARMUP_LOG" 2>&1 || true
        ) &
    done <<< "$UNIQUE_HITS"
else
    # Advisory-only fallback: tell the operator which libraries would
    # have been warmed if the wet-mcp CLI were on PATH.
    {
        printf '[wet-mcp UserPromptSubmit hook] would prewarm: '
        printf '%s ' "${UNIQUE_HITS[@]}"
        printf '\n'
    } >&2
fi

exit 0
