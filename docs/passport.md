# Docs Sync (Passport-Style Backend)

wet-mcp ships a backend-pluggable sync layer that lets you carry the
indexed docs cache (`docs.db`) across machines without re-crawling
upstream documentation. Two backends are available: per-user
**Google Drive** (default uvx mode) and operator-provisioned
**S3 / R2 / B2 / MinIO** (HTTP / Docker deploy mode).

Unlike mnemo-mcp's `passport.md` flow (which encrypts memory rows with
AES-256-GCM + Argon2id), wet-mcp's docs.db is a non-sensitive cache of
indexed open-source documentation — no per-update encryption is
required. The file is pushed and pulled directly.

## Concept

`docs.db` contains chunked + embedded representations of public library
documentation (Python stdlib, popular OSS packages, etc.). Re-indexing
the same library on a fresh machine produces the same chunks, so the
sync model is **last-write-wins** — every push overwrites the remote
copy with the current local state.

## Backend choice (XOR per deployment mode)

| Backend | Pros | Cons |
|---|---|---|
| **S3** (R2 / B2 / MinIO / AWS) | Cheap (CF R2 free tier covers most users), portable, no API rate limits, single shared cache across container fleet | Requires you to register a bucket + IAM key |
| **Google Drive** | Zero infra setup if you already have a Google account, OAuth Device Code flow via relay form | API quotas, per-user only (no fleet-wide share), ties you to Google |

**The two backends are mutually exclusive at deployment level (XOR).**
A single wet-mcp process never runs both — `resolve_active_backend()`
is consulted once at lifespan startup and never switches.

Resolution rule (`wet_mcp.sync.resolve_active_backend`):

- `SYNC_S3_BUCKET` is set (env var or pydantic `settings.sync_s3_bucket`)
  → active backend = **S3**. GDrive Device Code OAuth is **disabled** at
  startup; the relay form does NOT prompt for a Google account.
- `DOCS_DB_BACKEND=cf-d1` → active backend = **disabled** for legacy DB-file
  sync. Cloudflare D1 + Vectorize already hold the durable docs store, so
  this override wins even if an old bucket or bundled Google client remains
  in the container environment. Set `SYNC_ENABLED=false` to disable sync in
  any deployment mode.
- Otherwise → active backend = **GDrive**. The relay form drives the
  Device Code flow for the end-user's Google account on first config.

### Per-mode runbook

#### Method 1 (local-relay / uvx) → GDrive

End-user runs `uvx wet-mcp`, opens the relay URL, pastes API keys,
then authorises Google Drive via Device Code. No S3 env vars set.

```bash
# uvx (no S3 env vars; GDrive flow auto-fires after relay form submit)
uvx wet-mcp
```

Token storage: `~/.wet-mcp/tokens/google_drive.json` (chmod 600). Folder
on Drive: `wet-mcp` (override via `SYNC_FOLDER`).

#### Method 2/3 (HTTP deploy / docker) → S3

Operator builds the image from this checkout and sets S3 env at container
spawn. End-users only paste API keys via the relay form — the docs.db sync
is invisible to them and S3-backed under the hood.

```bash
docker build --target http -t wet-mcp:local .
docker run \
  -e SYNC_S3_BUCKET=wet-docs-cache \
  -e SYNC_S3_ACCESS_KEY_ID=AKIA... \
  -e SYNC_S3_SECRET_ACCESS_KEY=... \
  -e SYNC_S3_REGION=auto \
  -e SYNC_S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com \
  -e SYNC_S3_PREFIX=docs/ \
  -e PUBLIC_URL=https://wet.example.com \
  wet-mcp:local
```

The credentials live ONLY in the container process. End-users never
see the bucket name and never authenticate with Google.

#### Operator credential sourcing

- **AWS S3**: standard IAM access key + secret. Region matches bucket.
- **Cloudflare R2**: account-scoped API token + access key + secret;
  `SYNC_S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com`,
  `SYNC_S3_REGION=auto`.
- **Backblaze B2 / MinIO**: same shape — bucket + access key + secret +
  endpoint.

### Switching modes (local → prod migration)

1. Locally, copy your current `~/.wet-mcp/docs.db` to the bucket once:
   ```bash
   aws s3 cp ~/.wet-mcp/docs.db \
     s3://wet-docs-cache/docs/docs.db
   ```
2. Restart the container with the env vars above. On startup the S3
   auto-sync loop pulls `docs/docs.db`, merges it into the local cache
   via JSONL export/import, then enters the push cycle.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SYNC_ENABLED` | `true` | Master toggle for auto-sync loops |
| `SYNC_INTERVAL` | `300` | Seconds between push ticks (0 = manual only) |
| `SYNC_FOLDER` | `wet-mcp` | GDrive folder name (gdrive mode only) |
| `GOOGLE_DRIVE_CLIENT_ID` | `<bundled>` | Desktop OAuth client (public per Google docs) |
| `SYNC_S3_BUCKET` | `` | **Setting this switches to S3 mode** (unless `DOCS_DB_BACKEND=cf-d1`) |
| `SYNC_S3_REGION` | `us-east-1` | Region (`auto` for R2) |
| `SYNC_S3_ENDPOINT` | `` | Custom endpoint for R2 / B2 / MinIO (empty = AWS) |
| `SYNC_S3_ACCESS_KEY_ID` | `` | Static access key |
| `SYNC_S3_SECRET_ACCESS_KEY` | `` | Static secret key |
| `SYNC_S3_PREFIX` | `docs/` | Object key prefix inside the bucket |

## Object layout (S3 mode)

```
s3://<bucket>/<prefix>/docs.db   <- single file, overwrite-on-push
```

Unlike mnemo-mcp's passport bundles (which use monotonic
`seq-NNNNNN.bin` keys for delta sync), wet's docs cache is idempotent +
last-write-wins so a flat single-file layout is sufficient. Reindexing
produces the same chunks, and concurrent writers are not expected at
the deployment level.

## Failure modes

| Symptom | Diagnose |
|---|---|
| Startup log shows `Sync backend: gdrive` but operator expected S3 | `SYNC_S3_BUCKET` not propagated into the container env |
| Startup log shows `Sync backend: s3` but `health_check` returns False | Bucket missing / IAM denied / wrong endpoint — `aws s3 ls s3://<bucket>/` to verify |
| S3 push errors every interval (loop keeps running) | Inspect `S3 auto-sync push error` in logs; check bucket lifecycle rules or quota |
| GDrive sync silent on uvx | `~/.wet-mcp/tokens/google_drive.json` missing — re-run relay setup to refresh OAuth |

## Implementation reference

- `src/wet_mcp/sync/base.py` — `SyncBackend` abstract contract.
- `src/wet_mcp/sync/gdrive.py` — legacy DB-file sync helpers + the new
  `GDriveBackend` adapter.
- `src/wet_mcp/sync/s3.py` — `S3Backend` (boto3, push docs.db,
  pull docs.db, health_check, supports_oauth_setup=False).
- `src/wet_mcp/sync/__init__.py` — registry + `resolve_active_backend`
  + S3 auto-sync loop helpers.
- `tests/test_sync_backend_resolve.py`, `tests/test_s3_sync.py` —
  contract + moto fixture coverage.
