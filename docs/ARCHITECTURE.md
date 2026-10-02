# wet-mcp Architecture

> v2.0.0: `extract.agent` + `extract.interact` shipped; `media.analyze`
> removed (BREAKING).

This document describes the runtime architecture of wet-mcp built on the
`n24q02m-web-core` `ScrapingAgent`. It covers the component graph,
strategy escalation chain, storage layout, and LLM provider dispatch
model.

## Component graph

```text
wet-mcp client (Claude Code / Codex / Cursor / Antigravity)
    |
    | MCP protocol (stdio or HTTP)
    v
wet-mcp server (FastMCP)
    |
    +-- search tool   ----> sources/searxng.py + cache.py (TTL 1h / 5min)
    |                          |
    |                          v
    |                       SearXNG (bundled subprocess on port 41592)
    |
    +-- extract tool  ----> sources/crawler.py
    |                          |
    |                          v
    |                       web_core.scraper.ScrapingAgent
    |                          |
    |                          | strategy chain (escalation)
    |                          v
    |                       basic_http -> tls_spoof -> headless (Crawl4AI)
    |                          |
    |                          v
    |                       raw HTML / Markdown
    |                          |
    |                          v
    |                       sources/_smart_chunks.py (post-process)
    |                          |
    |                          v
    |                       { clean_text, markdown, structured_data,
    |                         code_blocks, metadata }
    |
    +-- media tool    ----> sources/crawler.py
    |                          |
    |                          +-- list:     web_core.scraper helpers
    |                          +-- download: SSRF-safe via web-core
    |                          +-- analyze:  DEPRECATED -> imagine-mcp.understand
    |
    +-- config tool   ----> mcp_core relay + config.py + cache management
    |
    +-- help tool     ----> src/wet_mcp/docs/{search,extract,media,config}.md
```

## Strategy escalation chain (extract pipeline)

`ScrapingAgent` walks the chain in order, stopping at the first strategy
that returns content above the quality threshold. Higher tiers cost more
in latency / browser memory / external API budget, so cheaper tiers run
first.

| Tier | Strategy | Cost | Success rate (tier-1 popular sites) |
|---|---|---|---|
| 0 | `basic_http` (httpx + standard headers) | very low | ~60% |
| 1 | `tls_spoof` (`curl_cffi` impersonation) | low | ~85% |
| 2 | `headless` (Crawl4AI Playwright) | medium | ~95% |

The chain extends with `patchright` (stealth interactive) and `captcha`
(CapSolver) tiers for interactive extraction.

### Rationale (cost vs success rate)

- **Latency budget**: each tier roughly 5x the previous tier's wall-clock
  cost. Always start cheap.
- **Browser bot detection**: many sites detect headless Chromium, but
  `tls_spoof` slips through TLS fingerprint checks at minimal cost.
- **Crawl4AI fallback**: serves the long tail (JS-heavy SPAs,
  infinite-scroll, dynamic loaders).
- **Markitdown bridge**: low-tier raw HTML routed through markitdown for
  HTML -> Markdown conversion when web-core does not supply MD natively.

### Smart chunks output schema

Every extract call returns a structured dict (no raw HTML leakage):

```json
{
  "clean_text": "Plain text extraction with whitespace normalized",
  "markdown": "Header- and list-aware markdown rendering",
  "structured_data": {
    "json_ld": [...],
    "open_graph": {...},
    "schema_org": {...}
  },
  "code_blocks": [
    {"language": "python", "content": "..."},
    {"language": "javascript", "content": "..."}
  ],
  "metadata": {
    "url": "https://example.com/article",
    "title": "Article title",
    "author": "...",
    "published_at": "...",
    "strategy_used": "tls_spoof",
    "fetched_at": 1747000000
  }
}
```

Heading extraction, code-block language detection, and JSON-LD parsing
live in `src/wet_mcp/sources/_smart_chunks.py`.

## Storage layout

| File | Purpose | Backend |
|---|---|---|
| `~/.wet-mcp/docs.db` | Library docs index (chunks + embeddings) | SQLite WAL + sqlite-vec |
| `~/.wet-mcp/cache.db` | Web search + extract cache (TTL gated) | SQLite WAL |
| `~/.wet-mcp/config.json` | Encrypted credentials (mcp-core `PerPluginStore`) | AES-GCM, machine-bound key at `~/.wet-mcp/.secret` |
| `~/.wet-mcp/downloads/` | Media download output dir | Filesystem |
| `~/.wet-mcp/tokens/google_drive.json` | OAuth Device Code token (sync) | Filesystem 0600 perms |

SearXNG runs as a bundled subprocess on `localhost:41592` (configurable
via `WET_SEARXNG_PORT`). It is not persisted across restarts; SearXNG
internal state is ephemeral.

Docs-search schema additions (libraries, versions, project_context)
land via Alembic revisions `docs_002_libraries`,
`docs_003_project_context`.

## LLM provider dispatch (per-task model chains)

wet-mcp selects models via per-task model chains, not a pinned model or a
key-priority router. Each chain is a CSV of `provider/model` entries
(order = litellm fallback); the provider is inferred from the model prefix:

```text
LLM_MODELS        -> LLM chain (e.g. extract agent). Empty -> LLM features off.
EMBEDDING_MODELS  -> embedding chain. Empty -> local ONNX (fastretrieval).
RERANK_MODELS     -> rerank chain. Empty -> local ONNX cross-encoder.
LLM_API_BASE      -> custom OpenAI-compatible endpoint (SSRF-guarded)
```

The default chains list curated models but are filtered to providers whose
`<PROVIDER>_API_KEY` is configured; if none has a key, the chain resolves
empty and wet falls back to local (no keyless cloud call, no priority router).
All calls dispatch through `mcp_core.llm` (litellm passthrough via the
`mcp-core[llm]` extra); any litellm `provider/model` string works.

If none is set:

- `extract` selector inference falls back to heuristic rules + logs a
  warning.
- Core search/extract/docs continue to work via embedding-only ranking.
- No hard failure -- LLM is an enhancement, not a requirement.

This dispatch is shared with web-core's `selector_inference` module
(web-core 2.0.1+ removed the hardcoded `gemini-2.5-flash` default).

## Mode matrix

| Mode | Default? | Storage scope | Multi-user |
|---|---|---|---|
| stdio | Yes | Local user (`~/.wet-mcp/config.json`, perm 0600) | No |
| HTTP self-host (single-user) | No | Shared local store (`~/.wet-mcp/config.json`), bind 127.0.0.1 | No |
| HTTP self-host (multi-user) | No | Per-JWT-sub vault (`~/.wet-mcp/subs/<sub>/config.json`), bind 0.0.0.0 | Yes |

The stdio default avoids OAuth complexity for single-machine personal
use; HTTP self-host is recommended when multi-device sync, claude.ai web
compatibility, or team sharing matters. Multi-user mode is triggered by
setting `PUBLIC_URL` (with `MCP_DCR_SERVER_SECRET` required as proof of
intentional multi-user deployment); without it HTTP binds 127.0.0.1 and
reuses the single-user store.

## Library docs search (Context7-parity)

The docs-search pillar layers a curated library index, project lock
(Cabinets), and token-aware docs query on top of the FTS5 + sqlite-vec
hybrid search. Three actions ship under the `search` tool surface:

| Action | Purpose | Latency target |
|---|---|---|
| `docs_resolve` | Free-form library name -> ranked `library_id` list | < 50 ms (in-process SQLite) |
| `docs_query` | Version-aware docs query honoring lock + 5000-token cap | < 500 ms p95 |
| `docs_lock_project` | Detect `pyproject.toml` / `package.json` / `go.mod` / `Cargo.toml`, persist Cabinets pin | < 100 ms |

### Docs-search schema

Alembic migration chain:

* `docs_001_baseline` (no-op anchor for legacy DBs)
* `docs_002_libraries` — adds `libraries.{canonical_name, homepage,
  github_url, package_managers, tier, last_indexed_at, total_versions}`,
  `versions.{release_date, source_url}`, `doc_chunks.{section, topic,
  content_hash, token_count}` + `idx_doc_chunks_lib_ver_topic`.
* `docs_003_project_context` — Cabinets `project_context` table with
  `project_path` PK + `locked_libraries` JSON + LRU index.
* `docs_004_chunk_summaries` — `doc_chunks.summary` + its index.
* `docs_005_metadata_seeded_at` — adds `libraries.metadata_seeded_at`
  (Tier 1 warmup freshness anchor) and moves seed-only
  `last_indexed_at` stamps into it, so "metadata seeded" and "chunks
  landed" stop being the same column.

`run_migrations_on_startup()` (in `wet_mcp.migrations`) is invoked by
the FastMCP lifespan after `DocsDB.__init__`. The runner copies
`docs.db -> docs.db.bak.<unix-ts>` before any forward migration.
Failures are logged and swallowed so server startup never blocks.

### Tier 1 / Tier 2 ingestion pipeline

```text
First docs_query for library X
    |
    +-- (a) Does X resolve AND hold a status='indexed' version?
    |       |
    |       +-- yes: resolve library_id, run hybrid search
    |       +-- no:  trigger ingest_tier2 in background, return progress hint
    |               (Tier 1 warmup seeds metadata only — curated names
    |                always resolve, with latest_version = None until
    |                chunks land, so resolution alone is not the gate)
    |
    +-- ingest_tier2 reuses discover_library + fetch_docs_pages
            (delegates to web_core.scraper.ScrapingAgent strategy chain)
            -> chunks stored with topic / section / token_count
            -> mark_library_indexed updates last_indexed_at
```

Tier 1 freshness window: 7 days. `maybe_warm` measures that window
against `metadata_seeded_at`; `last_indexed_at` is written only by
`mark_library_indexed`. The `refresh-tier1` cron job in
`.github/workflows/ci.yml` re-runs `scripts/build_tier1_index.py`
weekly to keep curated chunks fresh; that script exits non-zero when
fewer than `--min-success-rate` of the libraries produce chunks.

### Cabinets project isolation

`docs_lock_project(project_path=...)` walks the project root, parses
the supported manifests (PEP 621 + Poetry, `package.json`, `go.mod`,
`Cargo.toml`), resolves each entry against the libraries table, and
persists the lock list to `project_context`. Subsequent
`docs_query(library=..., project_path=...)` calls without an explicit
`version` honor the pin from the lock; `last_used_at` is bumped for
LRU eviction tracking.

## Agent + interact + media.analyze removal

### `extract(action="agent")` orchestrator

```text
extract(action="agent", query=...)
  |
  +-- resolve LLM_MODELS chain (provider inferred from prefix; key-gated)
  |     |
  |     +-- no provider key configured -> return "Error: no LLM provider detected"
  |     |                     (does not crash the SDK)
  |     +-- configured     -> proceed
  |
  +-- searxng_search(query, max_results=clamp(max_urls, 1, 20))
  |     |
  |     v
  |   urls = [r.url for r in results]
  |
  +-- _extract_many(urls)  (sem-bounded 3, lazy-imports crawler)
  |     |
  |     v
  |   list of smart-chunks-shaped dicts in input order
  |
  +-- build_cited_prompt(query, extracts, token_budget)
  |     |
  |     v
  |   per-extract char budget = (token_budget - 200) / N * 4
  |   numbered [N] citations with URL + title + truncated body
  |
  +-- llm.acompletion(model=synthesis_model or LLM_MODELS[0], ...)
  |     |
  |     v
  |   synthesis Markdown with [1], [2], ... matching sources index
  |
  +-- return {markdown, sources, per_url_metadata}
```

### `extract(action="interact")` orchestrator + session pool

```text
extract(action="interact", url=, actions=, session=None, screenshot=False)
  |
  +-- input validation (url + actions required, max 20 actions)
  |
  +-- session?
  |     +-- yes -> SessionPool.get(session, url)
  |     |           |
  |     |           +-- cached  -> reuse browser + page (cookies preserved)
  |     |           +-- absent  -> open_interact_session() + cache
  |     |                          (LRU eviction at max_concurrent=5,
  |     |                           TTL=1800s background gc)
  |     |
  |     +-- no  -> open_interact_session() (one-shot, closed in finally)
  |
  +-- for each action:
  |     +-- click   -> InteractOps.click(selector OR text=description)
  |     +-- fill    -> InteractOps.fill(selector OR text=description, value)
  |     +-- submit  -> InteractOps.submit(selector)
  |     +-- wait    -> InteractOps.wait_for(selector, state=visible)
  |
  +-- snapshot: page.content() -> _strip_html_to_markdown() (8000 char cap)
  +-- screenshot? -> ops.screenshot() -> ~/.wet-mcp/interact/<sha>.png
  +-- return {url, snapshot_markdown, screenshot_path?}
```

`SessionPool` lifecycle: process-scoped singleton in
`wet_mcp.sources._browser_sessions`. Background `_gc_loop` runs every
60s, evicts entries past `_ttl` (default 1800s), and self-cancels
when the pool is empty.

### `media.analyze` removal (BREAKING)

The legacy deprecation handler is gone. The `media` dispatcher now
routes `action="analyze"` through the standard unknown-action branch
with a special-cased migration string pointing to `imagine-mcp`'s
`understand` action. `wet_mcp.llm.analyze_media` is preserved for unit
tests but is unreachable from any MCP tool surface.

### `docs_004_chunk_summaries` schema

Adds nullable `summary` + `summary_provider` TEXT columns to
`doc_chunks`. Backward-compatible (existing rows have NULL); the
migration is schema-ready only -- no code path generates summaries yet.
Reserved for the future LLM-enhanced summaries feature.

## Cross-references

- Migration guide: `docs/migration.md` (v1.x.y -> v2.0.0)
- Interact reference: `docs/interact.md` (action language + session)
- Web-core repo: `n24q02m/web-core` (`web_core.scraper.ScrapingAgent`,
  future `web_core.browsers.patchright.InteractOps`)
- mcp-core repo: `n24q02m/mcp-core` (relay, JWT issuer, config storage primitives)
- Trust model: <https://mcp.n24q02m.com/servers/mcp-core/trust-model/>
