# wet

Python MCP Server: web search, content extraction, library docs, structured extraction.
Xem `AGENTS.md` va `README.md` de hieu architecture va configuration.

## Cau truc

- `src/wet/` -- Package chinh (src layout)
  - `server.py` -- FastMCP server (orchestrator, file lon nhat); always the HTTP MCP endpoint (no stdio mode)
  - `cli.py` -- `wet` control plane: `server start|stop|status`, `config`, `token hash`, `users path`, `docs reindex|import|reembed`, `search`, `warmup`
  - `runtime.py` -- Bridge to hull-core (settings, auth mode, users store, per-sub namespace)
  - `config.py` -- Pydantic Settings (singleton)
  - `cache.py`, `db.py`, `embedder.py`, `reranker.py` -- Infrastructure
  - `identity.py` -- Coherent browsing identity across the strategy chain
  - `docs_import.py`, `docs_reembed.py` -- Offline docs maintenance (no running server needed)
  - `setup.py`, `setup_tool.py` -- First-run SearXNG install + warmup logic (MCP-callable)
  - `sources/` -- Data source integrations (crawler, docs, searxng, search backends/strategies)
  - `alembic/` -- Docs DB migrations
- `tests/` -- Mirror source modules

## Lenh thuong dung

```bash
uv sync --group dev                # Cai dependencies
uv build                           # Build package (hatchling)
uv run ruff check .                # Lint
uv run ruff format --check .       # Kiem tra format
uv run ruff check --fix . && uv run ruff format .  # Fix
uv run ty check                    # Type check (ty lenient config)
uv run pytest                      # Test tat ca (integration excluded by default)
uv run pytest -m integration       # Chi integration tests
uv run pytest tests/test_config.py::test_function_name -v  # Test don le
uv run wet server start            # Chay server (background; --foreground de giu terminal)
uv run wet server status           # pid / lock / HTTP liveness
uv run wet server stop

# Mise shortcuts
mise run setup     # Full dev env setup
mise run lint      # ruff check + ruff format --check + ty check
mise run test      # pytest
mise run fix       # ruff check --fix --unsafe-fixes + ruff format
mise run dev       # uv run wet server start --foreground
```

Script entry points: `wet` (`wet.cli:main`) and `wet-mcp` (legacy alias).
`wet search` and other server-backed subcommands talk to the running server over
streamable HTTP; with no server running they exit 2 and print a hint to run
`wet server start`. `wet docs reindex|import|reembed` work without a server.

## Cau hinh quan trong

- **Python 3.13 bat buoc** -- 3.14+ KHONG tuong thich do SearXNG
- `requires-python = "==3.13.*"` trong pyproject.toml
- Ruff: line-length 88, target py313, rules E/F/W/I/UP/B/C4, ignore E501
- ty: lenient (unresolved-import, unresolved-attribute, possibly-missing-attribute all "ignore")

## Pytest

- `asyncio_mode = "auto"` -- KHONG can `@pytest.mark.asyncio`
- Default timeout: 30 seconds per test
- Integration/live/full tests excluded by default
- `addopts = "-m 'not integration and not live and not full'"` trong pyproject.toml

## Server, bind & auth

- One transport: the HTTP MCP server (`wet server start`, or `python -m wet.server`).
- Bind: `[server] host` / `port` in `~/.wet/config.toml`; `WET_HOST` / `WET_PORT` env override (container deployments).
- Per-port lifecycle lock (`LifecycleLock("wet", port)`, lock files under `~/.config/mcp/locks`) -- one instance per port, several ports can run side by side.
- `[server] auth` modes:
  - `no-auth` -- loopback bind only; the server refuses to start on a non-loopback host.
  - `token` -- single bearer token; store only its hash (`wet token hash <token>`).
  - `multi` -- per-user tokens from `[server] users_file` (default `~/.wet/users.toml`, see `wet users path`); data is namespaced per sub under `~/.wet/subs/<sub>/`.
- Client config points at the HTTP endpoint (see the manual example below).

## Env vars

- KHONG co prefix ung dung (day la open-source MCP server)
- LLM/Embed/Rerank/Chat: per-task provider cells `[models.embed|rerank|chat|jev_score]` in `~/.wet/config.toml` (each `base_url` + `api_key` + `model`, OpenAI-spec). OpenRouter is the pre-wired default for every cell.
  - Credentials: `api_key` in the cell, or `HULL_<TASK>_API_KEY` env injection (`HULL_EMBED_API_KEY` / `HULL_RERANK_API_KEY` / `HULL_CHAT_API_KEY` / `HULL_JEV_SCORE_API_KEY` — env wins over the file).
  - `OPENROUTER_API_KEY` env serves any cell that keeps the OpenRouter default `base_url` — one key can power every task.
  - Empty embed/rerank cell -> local ONNX (fastretrieval); unkeyed chat cell -> LLM features off.
 - Local model cache: `FASTRETRIEVAL_CACHE_PATH`.
- Search backends (`SEARCH_BACKENDS` CSV, runtime fallback — thử từng backend, rơi xuống backend kế khi error/empty): `searxng` (self-host) | `tavily` | `brave` | `exa` | `kagi` (keyed, `KAGI_API_KEY`) | `openrouter` (`OPENROUTER_API_KEY`, `openrouter:web_search` server tool) | `firecrawl` (key optional — không key vẫn thử keyless, `FIRECRAWL_API_KEY`) | `duckduckgo` | `startpage` (credential-free HTML scrape, uvx-safe; datacenter IP có thể bị bot-challenge → chain tự advance).
- SearXNG: `WET_AUTO_SEARXNG` (default true), `SEARXNG_URL` (external mode)
- Browser render backends (headless leg of `extract`): `BROWSER_BACKENDS` (CSV escalation chain: `native` | `browserless` | `invisible`; empty = `native`), `BROWSERLESS_URL`/`BROWSERLESS_TOKEN` (self-host browserless), `STEALTHFOX_BINARY` (path to a patched Firefox build for the `invisible` tier — skips the engine download, seal still verified), `CAPSOLVER_API_KEY` (optional key-gated captcha tier)
- Identity layer (one coherent person across the chain): `WET_IDENTITY_SEED` (int pin; default 0 = derive once and persist per namespace under `~/.wet/subs/<sub>/identity.json`), `IDENTITY_PROFILE_DIR` (persistent browser profile dir; default `~/.wet/subs/<sub>/profiles`). Requires the optional `n24q02m-hull[identity]` extra (`invisible-core`); without it strategies keep legacy behavior (warn once). First identity build may download a GeoIP mmdb (egress) and resolve locale/timezone from the egress IP — `timezone_mismatch` behind a proxy falls back to en-US/UTC, never raises to MCP callers
- Robots policy: `RESPECT_ROBOTS_TXT` (default `false`); set `true` to enforce `robots.txt` for the ScrapingAgent extract chain and Crawl4AI `crawl`, `sitemap`, and `list_media` actions
- Disable-local toggles (skip heavy in-process fallbacks per capability): `DISABLE_LOCAL_BROWSER`, `DISABLE_LOCAL_SEARCH`, `DISABLE_LOCAL_EMBED`, `DISABLE_LOCAL_RERANK`
- Docs DB backup is an external concern (e.g. rclone of `~/.wet/`); the server has no built-in sync.
- Secrets: skret SSM namespace `/wet-mcp/prod` (region `ap-southeast-1`)

### Manual config example

```bash
wet server start            # binds [server] host/port from ~/.wet/config.toml
```

```json
{
  "mcpServers": {
    "wet": {
      "type": "http",
      "url": "http://127.0.0.1:<port>/mcp"
    }
  }
}
```

With `auth = "token"` or `"multi"`, add the client's bearer token header
(`"headers": {"Authorization": "Bearer <token>"}`).

## Release & Deploy

- Conventional Commits. Tag format: `v{version}`
- CD: workflow_dispatch, chon beta/stable
- Pipeline (`cd.yml`): `benchmark-contract` gate -> `release` (PSR v10) -> `publish-pypi` (uv publish) -> `publish-mcp-registry` -> `sync-marketplace`
- No container image and no Cloudflare deploy are published.

## Pre-commit hooks

1. Ruff lint (`--fix --target-version=py313`) + format
2. ty type check
3. pytest (`--tb=short -q --timeout=30`)
4. Commit message: enforce `feat`/`fix` prefix

## Luu y quan trong

- Lazy imports ben trong functions cho heavy deps va tranh circular deps
- MCP tools return error strings (`return "Error: ..."`) -- KHONG raise exceptions
- Graceful fallback chains: Cloud -> Local, Tier 0 -> 1 -> 2 -> 3
- `match action:` cho tool action dispatch
- `asyncio.to_thread()` cho wrapping sync operations
- Embedding luu tai 768 dims (default). Doi embedding MODEL = doi vector space -> B2 identity guard CHAN boot (set REINDEX_ON_MODEL_CHANGE=true de re-embed). 768-dim chung chi giu table khong vo schema; KHONG cho mix vector tu 2 model khac nhau (cung dims van rac search).
- Renovate: Python upgrades DISABLED

## Protocol & live tests

All suites spawn the real HTTP server (`python -m wet.server`) on an ephemeral
loopback port against a tmp instance home; there is no external E2E driver.

- `tests/test_protocol_gate.py` -- protocol gate over the production HTTP transport, runs from the source tree (default suite).
- `tests/test_live_protocol.py` -- `-m live` (real server + stub SearXNG).
- `tests/test_full_live.py` -- `-m full` (real upstream services; keys from skret `/wet-mcp/prod`).
- `tests/test_live_mcp.py` -- standalone live script (defines no pytest tests; run it directly).

```bash
uv run pytest tests/test_protocol_gate.py
uv run pytest -m live
uv run pytest -m full
uv run python tests/test_live_mcp.py
```

References: `~/.claude/skills/mcp-dev/references/protocol-test-coverage.md`, `~/.claude/skills/mcp-dev/references/secrets-skret.md` (per-server credential layout), `~/.claude/skills/mcp-dev/references/multi-user-pattern.md` (per-sub isolation).
