# Migration: wet v1.x.y -> v2.0.0

This guide covers what changed in the v2.0.0 BREAKING release and how
to upgrade existing wet-mcp deployments cleanly.

## What's removed

### `media(action="analyze")`

The `analyze` action was deprecated in wet **v2.31.x** with a stable
migration string returned for a two-minor-version grace period. wet
**v2.0.0** removes the action entirely. Calls now return:

```text
Error: Unknown action 'analyze'. The analyze action was removed in
wet v2.0.0. Use imagine-mcp's understand action for vision/audio/video
analysis. Valid wet media actions: list (discover media on page),
download (save to local).
```

The `wet_mcp.llm.analyze_media` helper itself is preserved for tests
that exercise it directly, but it is no longer reachable from any MCP
tool surface.

#### Replacement recipe

The "discover -> save -> analyse" workflow now spans two MCP servers:

```text
1. wet:     media(action="list",     url="https://example.com/gallery")
2. wet:     media(action="download", media_urls=[...])
3. imagine: understand(file=..., prompt=...)
```

`imagine-mcp` is the dedicated multimodal pipeline (provider routing,
caching, vision/audio/video). Its `understand` action accepts the local
path produced by `wet: media(action="download")` directly.

## What's new

### `extract(action="agent", query=...)`

Multi-step research orchestration in a single tool call: SearXNG search
round -> concurrent extracts of the top hits -> LLM synthesis with
numbered `[N]` citations matching the returned `sources` array.

Requires one configured LLM provider (`GEMINI_API_KEY` /
`OPENAI_API_KEY` / `XAI_API_KEY`). Returns a clear
`Error: no LLM provider detected` string when none is set instead of
crashing the SDK.

See `src/wet_mcp/docs/extract.md` for full parameter reference.

### `extract(action="interact", url=..., actions=...)`

Drive a page interactively via patchright with a small action language
(`click` / `fill` / `submit` / `wait`). Optional `session=<id>` parameter
persists the browser context across calls (cookies + localStorage) for
multi-step flows like login then fetch authenticated content.

See [`docs/interact.md`](interact.md) for the full action-language
reference, session-persistence semantics, and security notes.

### `docs_004_chunk_summaries` schema migration

Adds nullable `summary` + `summary_provider` columns to `doc_chunks`.
Backward-compatible (existing rows have NULL); reserved for the future
LLM-enhanced summaries feature. No code path generates summaries yet --
the schema is only made available so adopters do not need a second
migration when the feature lands.

## Auto-migrate-on-startup

wet-mcp ships an Alembic-based auto-migrate runner that runs on server
startup before the FastMCP lifespan completes. The runner:

1. Detects the current Alembic revision (or stamps an unstamped DB).
2. If the head differs from the current revision, snapshots the DB to
   `<docs.db>.v<rev>.backup` BEFORE running any forward migration.
3. Runs `alembic upgrade head`.
4. On any migration failure, restores the backup to the original
   location and exits with `SystemExit(1)`.

The backup files survive across runs; you can keep the latest one as a
safety net or delete older ones manually.

### Manual rollback

If you need to roll back from v2.0.0 to v1.x.y for any reason:

```bash
# Stop the wet-mcp process, then:
mv ~/.wet-mcp/docs.db ~/.wet-mcp/docs.db.v2-attempt
cp ~/.wet-mcp/docs.db.v003.backup ~/.wet-mcp/docs.db
# Pin wet-mcp back to the previous version (e.g. uvx wet-mcp@2.31.0)
```

The `summary` + `summary_provider` columns from `docs_004` cannot be
used by v1.x.y, but their presence is harmless if you skip the rollback
and prefer to keep v2.0.0.

## FAQ

**Q: Does my pinned client config break?**
A: No. The wet tool surface is unchanged for `search`, `extract` (all
pre-existing actions), and `media.list` / `media.download`. Only
`media.analyze` is removed.

**Q: Will the new `agent` and `interact` actions cost me LLM tokens?**
A: Only when you call them. `agent` requires an LLM provider key (one
LLM call per invocation). `interact` does NOT call an LLM by default;
when you supply `description` instead of `selector`, a future web-core
upgrade will route through LLM-based selector inference. The wet-local
implementation in v2.0.0 uses a simple `text=...` heuristic.

**Q: What if I do not want to migrate yet?**
A: Stay on the latest v1.x release (`uvx wet-mcp@2.31.x`) until you are
ready. The deprecation message in v1.x explicitly named v2.0.0 as the
removal target, so the upgrade window has been advertised across two
minor releases.
