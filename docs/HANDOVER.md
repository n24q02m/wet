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

`wet server start|stop|status` runs the HTTP server. `wet warmup` prints a JSON
result; `wet config …` and `wet docs …` print plain text; `wet search` prints the
tool's text answer from the running server.

```bash
wet warmup                    # pre-download local models + auto-setup (SearXNG, browser)
wet docs list                 # indexed library names (the input for `docs reindex`)
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

## Provider credentials -- key pools and accounts

Every provider credential wet resolves goes through hull's shared pool
(`hull_core.credentials`, hull 0.5). Two surfaces read it: the four task cells
(`[models.<task>]`) and the cloud search backends' `*_API_KEY` CSV.

- Store: `~/.hull/hull.db` (hull's default; `WET_HULL_DB` overrides the path).
  Keys are sealed with `~/.hull/.credential-key`; rows keep a 4-character hint
  only. The tables are additive, so an older hull ignores them and a newer wet
  keeps reading a file an older wet wrote.
- Rotation (hull's policy, identical in hull's TypeScript mirror): `401`/`403`
  disable that credential and the call moves to the next; `429` cools it down
  by `Retry-After` / `rate_limit_reset` (clamped 1 s..1 h, default 60 s); `5xx`
  retries the same credential once then rotates; any other status re-raises
  untouched. Attempts are bounded, and an exhausted pool raises
  `wet.keypool.ProviderUnavailable` naming the provider and the cooldown --
  never a key.
- Concurrency: a call leases its credential, so two concurrent calls never get
  the same key while another could serve. A pool with a single usable
  credential is shared instead (there is no rotation decision to protect, and
  wet's batched embedding fan-out would otherwise turn one healthy key into
  spurious exhaustion errors); that entry is still health-tracked.
- Backward compatibility: the cell `api_key` / `HULL_<TASK>_API_KEY` /
  `OPENROUTER_API_KEY` material is **never removed**. On startup (and on the
  first provider call, for CLI paths that skip the server) it is seeded into
  the pool once; re-running only skips what the store already holds.
- Multi-account: `[models.<task>] account = "<account id>"` (or a unique
  account name) selects a named account's pool; omit it for the provider's
  default pool. The provider identity is `[models.<task>] provider` when set,
  else derived from `base_url`. An unknown account, or one registered for a
  different provider, fails closed with `wet.keypool.ProviderConfigError`
  rather than spending another identity's quota. Accounts and extra keys are
  managed with hull's API (`CredentialStore`, `AccountRegistry`).
- Config owns the endpoint: a cell's `base_url` and `model` are used verbatim
  for every credential of its pool; the store entry contributes the key.

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
