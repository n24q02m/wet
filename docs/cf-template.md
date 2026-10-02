# Cloudflare worker template (FROZEN for P3 replication)

`src/worker.ts` + `wrangler.jsonc` in this repo are the canonical CF template for
the n24q02m MCP stack. P3 servers (imagine, notion, email, telegram, mnemo) copy
them verbatim, changing only the Durable Object class name, the binding name, the
plugin/image/PUBLIC_URL strings, and the kept/dropped outbound handlers below.
Hardened for E.1 + E.2 (PR series cf-p3-01); do not re-solve those per server.

## Copy procedure
1. Copy `wet/src/worker.ts` -> `<server>/src/worker.ts`.
2. Rename `WetContainer` -> `<Name>Container`; `WET` binding -> `<NAME>`.
3. Update the image ref (`registry.cloudflare.com/<ACCOUNT_ID>/<server>:beta`) and
   `PUBLIC_URL`/route to `<server>.n24q02m.com`.
4. Apply the KEEP/DROP handler matrix below.
5. Copy `wrangler.jsonc`; drop the `d1_databases` / `vectorize` blocks for KV-only servers.

## ALWAYS KEEP (every server)
- `export { ContainerProxy }` (footgun #2).
- `pickContainerEnv` + the `CONTAINER_ENV_KEYS` allowlist (rename keys per server).
- `extractUserId` INCLUDING the single-user `idFromName("default")` contract (E.2 part a).
- The public `fetch` does **per-user DO routing ONLY**. It MUST NOT dispatch the
  kv/d1/vectorize handlers (see Security below). `export` the `OUTBOUND_BY_HOST`
  registry so unit tests invoke a handler directly instead of through `fetch`.
- `kvOutbound` INCLUDING the `GET __ready -> {ready:true}` readiness branch (E.1).
- `OUTBOUND_BY_HOST` registry + the `<Name>Container.outboundByHost = OUTBOUND_BY_HOST`
  ASSIGNMENT after the class (footgun #1 — NEVER a `static` field).
- The Container DO shape (`defaultPort`, `sleepAfter`, `enableInternet`, `envVars`).

## KEEP ONLY IF USED
- `d1Outbound` + `D1` binding -> ONLY if the server uses D1 (wet, mnemo).
- `vectorizeOutbound` + `VECTORIZE` binding -> ONLY if the server uses Vectorize (wet, mnemo).
  Routes: `POST /upsert`, `POST /query`, `POST /deleteByIds`, and `GET -> {ready:true}`.
  `deleteByIds` is REQUIRED on any server whose records can be re-indexed or deleted:
  dropping the D1 rows without dropping their vectors leaves entries that keep scoring
  in vector search but resolve to no content. Delete vectors BEFORE the rows, and do not
  wrap that call in a log-only `except` — a half-completed delete must be visible.
- imagine / notion / email / telegram are KV-only: drop both handlers + bindings; keep `kvOutbound`.

## Security (non-negotiable)
- **Outbound handlers stay OFF the public `fetch` entrypoint.** The container's
  kv/d1/vectorize.internal outbound is serviced via `@cloudflare/containers`'
  `ContainerProxy` + the `outboundByHost` registry assignment — an internal,
  container-only path. Dispatching them from the public `fetch` (e.g. keying on
  `new URL(request.url).hostname`) lets an external caller spoof the hostname to
  `kv.internal` and read/write/**DELETE** the credential KV namespace
  unauthenticated (HIGH finding, commit security review 2026-06-15). Test the
  handlers by calling `OUTBOUND_BY_HOST['kv.internal'](req, env)` directly; add a
  regression test asserting `worker.fetch` with an internal hostname is NOT
  serviced by a handler (returns the DO-routing `not found`, never a KV op).

## E.1 / E.2 (already solved in the template — inherit, do not re-solve)
- E.1 race: `kvOutbound` answers `GET __ready` (via ContainerProxy); the container
  setup path awaits `CfKvBackend.ready()` (mcp-core >=1.18.0b6) before the first
  credential PUT. Client backstop: `cf_full_flow.py get_token(save_retries=8)`
  retry-on-500.
- E.2 window: single-user `idFromName("default")` collapses setup+serving to one DO;
  the setup path polls `poll_until_readable(sub)` (presence of the raw ciphertext
  blob) before reporting success. Client backstop: `cf_full_flow.py
  _call(retries=20, delay=8)` awaiting-setup poll.

## 5 footguns (silent failure if violated)
1. `outboundByHost` is an ASSIGNMENT after the class, never a `static` field.
2. `export { ContainerProxy }` from the entrypoint.
3. KV blobs read/written as `arrayBuffer` (binary AES-GCM ciphertext).
4. CF has no `/.dockerenv`; detect container via `MCP_TRANSPORT=http`.
5. CF managed registry only (`registry.cloudflare.com/<ACCOUNT_ID>`); re-pushing the
   same tag does NOT roll a running app -> delete+recreate. `wrangler containers delete`
   takes the container ID (from `wrangler containers list`), NOT the name
   (wrangler 4.100.0: `Expected a container ID but got <name>`); it prompts -> pipe `yes`.
   The release workflow's opt-in `recreate_container` input (or
   `scripts/deploy_cf.py --recreate-container`) lists JSON, matches the exact
   worker name, and deletes only that ID; an absent exact worker is a no-op.
   `wrangler deploy` reports "no changes" for the container (tracks tag not digest) until
   the app is deleted+recreated. `wrangler kv` needs `--remote`.

## Sync mode-gating (servers with a docs/memory DB: wet, mnemo)
- Wet uses `DOCS_DB_BACKEND=cf-d1`; Mnemo uses `MEMORY_DB_BACKEND=cf-d1`.
  D1 + Vectorize is durable, so legacy GDrive/S3 file sync is disabled by the
  effective backend resolver even when old bucket/client settings remain.
- Startup, relay wizard and device-code entry points must all honor that
  resolver. `SYNC_ENABLED=false` disables both backends independently of CF.
- Non-CF SQLite deployments retain GDrive backup/portability, or S3 when
  `SYNC_S3_BUCKET` is configured; the backends remain mutually exclusive.

## Per-server success criteria (work-order-v3 DONE gate)
- Deploy to CF managed registry; `/.well-known/oauth-protected-resource` -> 200;
  `GET /mcp` (no token) -> 401 + www-authenticate.
- Full OAuth password flow self-test PASS (replicate `cf_full_flow.py`): login ->
  save credential (retry-on-500) -> authenticated tool call via relay.
  Supply `MCP_RELAY_PASSWORD` from the approved MCP-owned secret source and
  server runtime credentials separately. Never use a VM-hosted service or
  VM-named namespace as a deployment, verification, or rollback dependency.
  E.1 residual: <=1 `save 500 (interception race)` retry on a truly-cold instance is PASS
  (the readiness probe reduces but cannot fully eliminate it; client retry is the backstop).
- STATE SURVIVES delete+recreate (the key gate; first boot is not enough). Strong test:
  mint+save creds -> tool call -> delete+recreate -> reuse SAME token (no setup) -> creds
  resolve from KV (`cf_state_survives.py {mint|reuse}`).
- Per-sub isolation: 2 distinct JWT subs -> separate state, no bleed.
- T0 (precommit + CI) green; Protocol Test B (ClientSession all-tool-all-mode) PASS.
- STABLE dispatched ONLY on explicit user request.

Template frozen 2026-06-15 (cf-p3-01). Changes here require re-deploying + re-verifying
wet, then re-syncing all 5 downstream copies.
