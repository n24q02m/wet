# wet Handover

Operational handover for [wet](https://github.com/n24q02m/wet) — MCP server
for web search, content extraction, and library docs. Current stable line:
**n24q02m-wet 3.20.x**.

## Current operation

- PyPI dist: `n24q02m-wet` (renamed from `wet-mcp`; see
  `docs/adr/0001-binary-names.md`). Repo, CLI and module are `wet`; console
  scripts are `n24q02m-wet` (canonical), `wet` (short alias) and `wet-mcp`
  (legacy alias kept so existing `uvx wet-mcp` configs keep working).
- Transport: Streamable HTTP only, served by `wet server start`
  (`~/.wet/config.toml` `[server]`: `host`, `port`, `auth`). There is no stdio
  mode; a bare `wet` prints the control-plane usage. No daemon-bridge layer and
  no client-side auto-spawn.
- Post-de-host the project operates no hosted MCP endpoint; all deployments
  are user-owned (local HTTP, the compose stack, or the user's own cloud).
- Public OCI image publication is discontinued; build containers from source.
- Local state is machine-bound under `~/.wet/`: `config.toml` (AES-GCM,
  machine-bound key), `docs.db`, `subs/` (per-namespace persistent browser
  profiles).

## Install

```bash
uvx --python 3.13 --from n24q02m-wet wet server start   # start the HTTP server without a persistent install
claude mcp add --transport http wet http://127.0.0.1:8000/mcp  # Claude Code -> the running instance
pip install n24q02m-wet               # persistent install (CLI + server)
uvx --from n24q02m-wet wet warmup     # try a subcommand without a persistent install
```

Extras: `n24q02m-wet[identity]`, `n24q02m-wet[invisible]` (n24q02m-hull passthrough;
`[invisible]` adds the stealth browser stack). Claude Code plugin:
`/plugin install wet@n24q02m-plugins` (HTTP entry driven by `WET_URL`, default
`http://127.0.0.1:8000/mcp`, optional `WET_TOKEN`; start the instance first).

## Local run (README quick start)

```bash
git clone https://github.com/n24q02m/wet && cd wet
uv run wet config init            # writes ~/.wet/config.toml (default: auth = "no-auth")
uv run wet server start           # dev loopback; serves http://127.0.0.1:8000/mcp
```

`no-auth` refuses non-loopback binds. Docker compose publishes
`127.0.0.1:${WET_PORT:-8000}` → container `8000` (loopback only), mounts
`docker-config/config.toml` read-only, and persists `docs.db` + `subs/` in the
`wet-home` volume (caches in `wet-data`). Config edits take effect on
`docker compose restart`.

Token auth: `uv run wet token hash <token>` (scrypt, never echoes the token) →
paste into `[server] token_hash`; clients send `Authorization: Bearer`.

## CLI

`wet server start|stop|status` runs the HTTP server; the other subcommands
print a JSON result and exit:

```bash
wet warmup                    # pre-download local models + auto-setup (SearXNG, browser)
wet docs reindex <library>    # drop a cached docs index; next search re-indexes
```

## Build, run, and verify

```bash
git clone https://github.com/n24q02m/wet.git && cd wet
uv sync
uv run pytest          # dev group: pytest, pytest-asyncio, pytest-timeout, ruff, ty
uv run wet server start --foreground
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

`[server] auth = "multi"` with per-user tokens from `users_file` (default
`~/.wet/users.toml`, `wet users path`). Data is namespaced per sub
(`~/.wet/subs/<sub>/`).

## Data and safety invariants

- `no-auth` refuses non-loopback binds — the server is localhost-only until
  token auth is configured.
- The token-hash command never echoes the token; only `token_hash` is stored
  in `config.toml`.
- `media.analyze` was removed in v2.0.0 (see `docs/migration.md`); current
  release line is v3.x.

## In-flight and rollback

Roll back a source change by reverting the owning commit; keep `docs.db` and
`subs/` — they are forward-compatible instance state. Docker data continuity:
copy existing `docs.db` + `subs/` into the `wet-home` volume before first
start. Run `wet warmup` after deploy to avoid first-run cold delays.
