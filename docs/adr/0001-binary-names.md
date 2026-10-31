# ADR 0001: Distribution and Binary Executable Names for wet

## Status
Accepted

## Context
Following the stack stabilization plan (Q3, Q13), distribution packages across the n24q02m stack are renamed to use the standard publisher prefix `n24q02m-*` on PyPI to prevent namespace confusion, clarify ownership, and align with other tools in the suite (`n24q02m-telegram`, etc.).

Users invoke the CLI tool in multiple contexts:
1. `uvx` ephemeral execution with package name matching binary: `uvx n24q02m-wet`
2. Local shell invocation where a short, concise command is preferred: `wet`
3. Existing automation, scripts, and workflows expecting the historical binary name: `wet-mcp`

## Decision
We expose three entry point aliases in `pyproject.toml` pointing to `wet.cli:main`:
- `n24q02m-wet`: Canonical primary executable name matching the PyPI package distribution.
- `wet`: Short ergonomic alias for local interactive shell use.
- `wet-mcp`: Backward-compatible alias for existing configurations and scripts.

## Consequences
- PyPI package name is `n24q02m-wet`.
- Users running `uvx n24q02m-wet` will execute `wet.cli:main` without requiring `--from`.
- Users with existing `uvx --from wet-mcp wet-mcp` or local `wet` / `wet-mcp` commands continue to work seamlessly.
