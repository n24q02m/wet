---
name: lock-project-stack
description: Detect a project's manifest (pyproject.toml / package.json / go.mod / Cargo.toml), pin its library set into wet-mcp's Cabinets project_context, then route subsequent docs queries to the locked versions automatically.
argument-hint: "[absolute path to project root]"
---

# lock-project-stack

Bind a project to its declared dependency versions so every
`search(action="docs_query")` call from inside that project surfaces
docs for the *exact* versions you pinned, instead of "latest". Mirrors
the Cabinets workflow from spec section 4.3.

## Steps

1. **Resolve the project root**:
   - If the user gave an absolute path, use it.
   - Otherwise infer the root from the current workspace context
     (e.g. `git rev-parse --show-toplevel` output).
   - Confirm at least one supported manifest exists:
     `pyproject.toml`, `package.json`, `go.mod`, or `Cargo.toml`.

2. **Lock the project**:
   - Call `search(action="docs_lock_project", project_path=<abs_path>)`.
   - The response includes `total` detected libraries + `indexed`
     count (how many already have docs in Tier 1 or Tier 2). Surface
     both numbers to the user so they know how much coverage they
     have today.

3. **Trigger Tier 2 ingestion for missing libraries (optional)**:
   - Iterate the `locked_libraries` list; for entries with
     `indexed == false`, call
     `search(action="docs_query", library=<name>, project_path=<abs_path>, query="<library> overview")`
     once. The first call kicks off background Tier 2 ingestion;
     subsequent calls return real chunks.

4. **Verify lock reuse**:
   - Re-call `search(action="docs_query", library=<name>, project_path=<abs_path>, query=...)`
     WITHOUT specifying `version`. The response should include a
     non-null `lock_pin` field matching the version from the
     manifest, confirming Cabinets is honoring the pin.

5. **Surface the pin to the user**:
   - Summarize "Locked N libraries against versions X.Y.Z (M already
     indexed, K queued for Tier 2 ingestion)."

## Best practices

- Re-run after every dependency bump so the lock stays in sync with
  what is actually installed.
- For monorepos, lock each workspace project separately — wet-mcp keys
  on absolute path so `apps/web` and `apps/api` get distinct locks.
- The lock is a hint, not a hard constraint — callers can always
  override the version by passing it explicitly to `docs_query`.
