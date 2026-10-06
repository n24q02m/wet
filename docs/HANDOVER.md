# wet Handover

Operational handover for [wet](https://github.com/n24q02m/wet) — MCP server
for web search, content extraction, and library docs. Current stable line:
**wet-mcp 3.19.x**.

## Current operation

- PyPI dist: `wet-mcp`. Repo, CLI and module are `wet`; console scripts are
  `wet` (primary) and `wet-mcp` (legacy alias kept so existing
  `uvx wet-mcp` configs keep working).
- Transports: **stdio** (default, local — a bare `wet` invocation is the MCP
  passthrough) and **HTTP** (self-host, OAuth-gated; `wet --http`). No
  daemon-bridge layer and no auto-spawn from stdio.
- Post-de-host the project operates no hosted MCP endpoint; all deployments
  are user-owned (local stdio/HTTP, docker compose, or the user's own cloud).
- Public OCI image publication is discontinued; build containers from source.
- Local state is machine-bound under `~/.wet/`: `config.toml` (AES-GCM,
  machine-bound key), `docs.db`, `subs/` (per-namespace persistent browser
  profiles).

## Install

```bash
uvx wet-mcp                       # run the stdio server without a persistent install
claude mcp add wet -- uvx wet-mcp # Claude Code (stdio)
pip install wet-mcp               # persistent install (CLI + server)
uvx --from wet-mcp wet warmup     # try a subcommand without a persistent install
```

Extras: `wet-mcp[identity]`, `wet-mcp[invisible]` (hull-core passthrough;
`[invisible]` adds the stealth browser stack). Claude Code plugin:
`/plugin install wet@n24q02m-plugins`.

## Local run (README quick start)

```bash
git clone https://github.com/n24q02m/wet && cd wet
uv run wet config init            # writes ~/.wet/config.toml (default: auth = "no-auth")
uv run wet                        # dev loopback; README shows http://127.0.0.1:8000/mcp
```

`no-auth` refuses non-loopback binds. Docker compose publishes
`127.0.0.1:${WET_PORT:-8000}` → container `8000` (loopback only), mounts
`docker-config/config.toml` read-only, and persists `docs.db` + `subs/` in the
`wet-home` volume (caches in `wet-data`). Config edits take effect on
`docker compose restart`.

Token auth: `uv run wet token hash <token>` (scrypt, never echoes the token) →
paste into `[server] token_hash`; clients send `Authorization: Bearer`.

## CLI

A bare invocation (or leading-dash flag) starts the server; a leading
positional argument is a subcommand that prints a JSON result and exits:

```bash
wet warmup                    # pre-download local models + auto-setup (SearXNG, browser)
wet docs reindex <library>    # drop a cached docs index; next search re-indexes
wet auth google               # authorize Google credential provider for Drive sync
wet logout                    # clear the local Drive sync token
```

## Build, run, and verify

```bash
git clone https://github.com/n24q02m/wet.git && cd wet
uv sync
uv run pytest          # dev group: pytest, pytest-asyncio, pytest-timeout, ruff, ty
uv run wet
```

## Model configuration policy

- Task cells `[models.embed|rerank|chat|jev_score]` in `~/.wet/config.toml`
  are independent (`base_url + api_key + model`, OpenAI-spec HTTP); one
  OpenRouter key powers every cell. Inject `HULL_EMBED_API_KEY` /
  `HULL_RERANK_API_KEY` / `HULL_CHAT_API_KEY` / `HULL_JEV_SCORE_API_KEY` at
  start instead of storing keys in the file.
- **No sanctioned default cloud model.** A completion/chat cell left
  unconfigured fails closed — wet makes no model call without explicit
  configuration (regression covered since PR #1864). Embedding/rerank chains
  fall back to the local Fastretrieval reference model when empty; configured
  cloud chains do not silently fall back.
- Per-task chain selection: `EMBEDDING_MODELS` / `RERANK_MODELS` /
  `LLM_MODELS` (CSV `provider/model`, order = litellm fallback; provider
  inferred from the prefix; keys never select a model).
- Cloud search backends are an optional fallback chain (`SEARCH_BACKENDS`:
  Tavily, Brave, Exa, Kagi, OpenRouter, Firecrawl) over the embedded SearXNG.
- `DISABLE_LOCAL_BROWSER|SEARCH|EMBED|RERANK` opt out of in-process local
  fallbacks (slim containers).

## Multi-user HTTP self-host

`MCP_TRANSPORT=http`, `PUBLIC_URL=<your-domain>`; the setup form is gated by
`MCP_RELAY_PASSWORD`. Multi-user deployments require `CREDENTIAL_SECRET`
(per-user vault key), `MCP_JWT_SIGNING_SECRET` (rotatable OAuth JWT key), and
`MCP_DCR_SERVER_SECRET`. Credentials/tokens live per JWT sub
(`~/.wet/subs/<sub>/`).

Docs sync: `SYNC_ENABLED` (default `true`), `GOOGLE_DRIVE_CLIENT_ID`,
`SYNC_FOLDER` (default `wet`), `SYNC_INTERVAL` (default `300`s), optional
`SYNC_S3_BUCKET`; `DOCS_DB_BACKEND=cf-d1` disables file sync including
automatic startup.

## Data and safety invariants

- `no-auth` refuses non-loopback binds — the server is localhost-only until
  token auth is configured.
- The token-hash command never echoes the token; config is AES-GCM encrypted,
  file perm `0600`, machine-bound key.
- `media.analyze` was removed in v2.0.0 (see `docs/migration.md`); current
  release line is v3.x.

## In-flight and rollback

Roll back a source change by reverting the owning commit; keep `docs.db` and
`subs/` — they are forward-compatible instance state. Docker data continuity:
copy existing `docs.db` + `subs/` into the `wet-home` volume before first
start. Run `wet warmup` after deploy to avoid first-run cold delays.
