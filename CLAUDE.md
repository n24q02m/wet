# wet-mcp

Python MCP Server: web search, content extraction, library docs, structured extraction.
Xem `AGENTS.md` va `README.md` de hieu architecture va configuration.

## Cau truc

- `src/wet_mcp/` -- Package chinh (src layout)
  - `server.py` -- FastMCP server (orchestrator, file lon nhat)
  - `config.py` -- Pydantic Settings (singleton)
  - `cache.py`, `db.py`, `embedder.py`, `reranker.py` -- Infrastructure
  - `relay_setup.py` -- `apply_config` / `load_config_from_file` env-applier used by the OAuth setup form (live setup UX = OAuth-AS browser form at `<PUBLIC_URL>/authorize`; the `ensure_config` create-session/poll path is legacy/unused in production)
  - `relay_schema.py` -- Relay form schema (2 modes: local/cloud)
  - `sync/` -- Docs sync backends: `gdrive.py` (Google Drive, OAuth Device Code, httpx) + `s3.py` (S3/R2/B2 operator mode) + `base.py`
  - `token_store.py` -- Local token storage cho OAuth (~/.wet-mcp/tokens/)
  - `setup_tool.py` -- Warmup + setup-sync logic (MCP-callable)
  - `sources/` -- Data source integrations (crawler, docs, searxng)
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
uv run wet-mcp                     # Chay server

# Mise shortcuts
mise run setup     # Full dev env setup
mise run lint      # ruff check + ruff format --check + ty check
mise run test      # pytest
mise run fix       # ruff check --fix --unsafe-fixes + ruff format
mise run dev       # uv run wet-mcp
```

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

## Env vars

- KHONG co prefix ung dung (day la open-source MCP server)
- LLM/Embed/Rerank: litellm passthrough qua `mcp_core.llm` (mcp-core[llm]). Per-task model chains, CSV `provider/model,provider/model`, order = litellm fallback:
  - `EMBEDDING_MODELS` -- chain embedding. Rong = local ONNX (fastretrieval).
  - `RERANK_MODELS` -- chain rerank. Rong = local ONNX cross-encoder.
  - `LLM_MODELS` -- chain LLM. Rong = tat feature LLM.
- Provider duoc suy ra tu prefix model. API key theo convention litellm `<PROVIDER>_API_KEY`. 7 provider servers goi y:

  | model prefix | key env var | get it at |
  |---|---|---|
  | `gemini/` | `GEMINI_API_KEY` | aistudio.google.com/apikey |
  | `vertex_express/` | `GOOGLE_VERTEX_EXPRESS_API_KEY` | cloud.google.com/vertex-ai/generative-ai/docs/start/express-mode/overview |
  | `openai/` (or bare) | `OPENAI_API_KEY` | platform.openai.com |
  | `jina_ai/` | `JINA_AI_API_KEY` | jina.ai/api-key |
  | `cohere/` | `COHERE_API_KEY` | dashboard.cohere.com |
  | `xai/` | `XAI_API_KEY` | console.x.ai |
  | `anthropic/` | `ANTHROPIC_API_KEY` | console.anthropic.com |

  For any other litellm provider (used via env passthrough), see https://docs.litellm.ai/docs/providers/<provider> for its `<PROVIDER>_API_KEY` name.
 - Custom endpoint (SSRF-guarded): `LLM_API_BASE`, `EMBEDDING_API_BASE`, `RERANK_API_BASE`
 - Local model cache: `FASTRETRIEVAL_CACHE_PATH`.
- Search backends (`SEARCH_BACKENDS` CSV, runtime fallback — thử từng backend, rơi xuống backend kế khi error/empty): `searxng` (self-host) | `tavily` | `brave` | `exa` | `kagi` (keyed, `KAGI_API_KEY`) | `firecrawl` (key optional — không key vẫn thử keyless, `FIRECRAWL_API_KEY`) | `duckduckgo` | `startpage` (credential-free HTML scrape, uvx-safe; datacenter IP có thể bị bot-challenge → chain tự advance).
- Deprecated (honored mot release voi warning): singular `EMBEDDING_MODEL`/`RERANK_MODEL` + `EMBEDDING_BACKEND`/`RERANK_BACKEND` (backend gio suy ra tu chain rong hay khong). Priority-router cu "Jina > Gemini > OpenAI > Cohere" da bo.
- SearXNG: `WET_AUTO_SEARXNG` (default true), `SEARXNG_URL` (external mode)
- Browser render backends (headless leg of `extract`): `BROWSER_BACKENDS` (CSV escalation chain: `native` | `browserless` | `cf-browser-rendering`; empty = `native`), `BROWSERLESS_URL`/`BROWSERLESS_TOKEN` (self-host browserless), `CF_BROWSER_RENDERING_TOKEN`/`CF_ACCOUNT_ID` (Cloudflare Browser Rendering), `CAPSOLVER_API_KEY` (optional key-gated captcha tier)
- Robots policy: `RESPECT_ROBOTS_TXT` (default `false`); set `true` to enforce `robots.txt` for the ScrapingAgent extract chain and Crawl4AI `crawl`, `sitemap`, and `list_media` actions
- Disable-local toggles (skip heavy in-process fallbacks per capability): `DISABLE_LOCAL_BROWSER`, `DISABLE_LOCAL_SEARCH`, `DISABLE_LOCAL_EMBED`, `DISABLE_LOCAL_RERANK`
- Sync: `SYNC_ENABLED` (default true), `GOOGLE_DRIVE_CLIENT_ID` (required for sync), `SYNC_FOLDER` (default "wet-mcp"), `SYNC_INTERVAL` (default 300s)
- Sync dung Google Drive API truc tiep (httpx). OAuth Device Code flow, token luu tai `~/.wet-mcp/tokens/google_drive.json`
- HTTP auth (live self-host): credentials are configured via the OAuth-AS browser form at `<PUBLIC_URL>/authorize`; `GET /mcp` without a Bearer token returns 401 + `www-authenticate` pointing at `/.well-known/oauth-protected-resource`. The browser form is gated by `MCP_RELAY_PASSWORD` (single shared password, gate only — empty disables it; not per-user). Multi-user remote mode also requires `CREDENTIAL_SECRET` (per-sub vault key) + `MCP_DCR_SERVER_SECRET` (proof of intentional multi-user deploy).
- `MCP_RELAY_URL`: read only by the legacy `ensure_config` create-session/poll path (`relay_setup.py`), which has no production caller — the live setup UX is the OAuth-AS form above, not an ECDH relay.
- Secrets: skret SSM namespace `/wet-mcp/prod` (region `ap-southeast-1`)

### Manual config example

```json
{
  "mcpServers": {
    "wet": {
      "command": "uvx", "args": ["wet-mcp"],
      "env": {
        "EMBEDDING_MODELS": "jina_ai/jina-embeddings-v5-text-small,gemini/gemini-embedding-001",
        "RERANK_MODELS": "jina_ai/jina-reranker-v3",
        "LLM_MODELS": "gemini/gemini-3-flash-preview",
        "JINA_AI_API_KEY": "jina_xxx",
        "GEMINI_API_KEY": "AIza_xxx"
      }
    }
  }
}
```

## Cloudflare serverless mode

Forcing cloud embed/rerank (so the container never downloads local ONNX models):

| env var | value |
|---|---|
| `EMBEDDING_MODELS` | `jina_ai/jina-embeddings-v5-text-small` |
| `RERANK_MODELS` | `jina_ai/jina-reranker-v3` |
| `JINA_AI_API_KEY` | from jina.ai/api-key |

A non-empty `*_MODELS` chain whose provider key is set -> cloud backend (inferred,
not via the deprecated `*_BACKEND`). Empty chain -> local ONNX. With cloud forced,
  `fastretrieval` is never instantiated, keeping the container slim. Storage: set
`MCP_STORAGE_BACKEND=cf-kv` + `MCP_KV_BASE_URL=http://kv.internal`,
`DOCS_DB_BACKEND=cf-d1` + `MCP_D1_BASE_URL`/`MCP_VECTORIZE_BASE_URL`/`MCP_VECTORIZE_IDX`,
`SEARCH_BACKEND=tavily` + `TAVILY_API_KEY`, and `CREDENTIAL_SECRET`.

- **CF template (frozen for P3 replication):** `docs/cf-template.md` pins the canonical
  worker.ts/wrangler.jsonc copy contract (KEEP/DROP handler matrix, 5 footguns, the
  security rule that outbound handlers stay OFF the public `fetch`, E.1 readiness probe
  + E.2 single-user-DO/poll patterns, sync mode-gating). The 5 P3 servers copy this; do
  not re-solve E.1/E.2 per server.

## Release & Deploy

- Conventional Commits. Tag format: `v{version}`
- CD: workflow_dispatch, chon beta/stable
- Pipeline: PSR v10 -> PyPI (uv publish) -> MCP Registry
- Cloudflare deploy remains release-triggered and pushes only its internal
  image to `registry.cloudflare.com`; no public OCI image is published.

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

## Known bugs / gotchas (phat hien 2026-04-18 E2E)

1. **Setup flow 2-phase race condition**:
   - Phase 1: user submit API keys form -> `writeConfig(SERVER_NAME, config)` -> `state=configured` (nhanh, ~5-30s)
   - Phase 2: Google Drive OAuth Device Code flow start (async, BLOCKING user hanh dong tren `google.com/device`)
   - Sau Phase 2, token save vao `~/.wet-mcp/tokens/google_drive.json`
   - **Gotcha:** E2E test script KHONG duoc kill server process sau Phase 1 -- PHAI wait cho `google_drive.json` ton tai TRUOC KHI exit. Neu kill som -> OAuth token mat -> next run phai re-auth.
   - Example fix: `phase-m-e2e-test/test_wet_full.py` phase_1 dung check `pathlib.Path(token_path).exists()` + 300s timeout after state=configured.

2. **GDrive token shared voi mnemo-mcp**:
   - Neu user auth mot account Google cho wet-mcp, mnemo-mcp co the auto-detect va skip device code flow (shared account pool ong)
   - Chua verify chinh xac mechanism, nhung observed 2026-04-18 E2E: setup mnemo ngay sau wet -> report "configured" rat nhanh
   - **Impact:** Tot cho UX, nhung can check xem logic share co security concern khong (token scope, privilege escalation)

3. **Relay "Setup complete" browser UI**: Python core-py relay implementation works correctly (browser hien "Setup complete!" sau phase 2). KHAC voi TS consumers (notion/email) bi stuck -- see `C:\Users\n24q02m-wlap\projects\mcp-core\CLAUDE.md` Known bugs #2.

## E2E

Driven by `mcp-core/scripts/e2e/` (matrix-locked, 15 configs). Run a single config from this repo via `make e2e` (proxy) or directly:

```
cd ../mcp-core && uv run --project scripts/e2e python -m e2e.driver <config-id>
```

Configs for this repo: `wet-full`.

t2-interaction: GDrive device-code (900s); per-sub token storage at ``~/.wet-mcp/subs/<sub>/tokens/google_drive.json``.

Tier policy:

- **T0** (precommit + CI on PR / main push) - runs without upstream identity. Skret keys not required.
- **T2 non-interaction** (`make e2e-config CONFIG=<id>` locally) - driver pre-fills relay form from skret AWS SSM `/wet-mcp/prod` (`ap-southeast-1`). No user gate.
- **T2 interaction** - driver fills relay form, then prints upstream user-gate URL; user signs in / types OTP at provider. Driver enforces per-flow timeouts (device-code 900s, oauth-redirect 300s, browser-form 600s) and emits `[poll] elapsed=Xs remaining=Ys status=<body>` every 30s. On timeout, container logs + last `setup-status` are saved to `<tmp>/e2e-diag/` BEFORE teardown for post-mortem.

Multi-user remote mode (deployment property; not a separate config) requires `MCP_DCR_SERVER_SECRET` in the same skret namespace - driver refuses to start the container without it when `PUBLIC_URL` is set.

References: `mcp-core/scripts/e2e/matrix.yaml`, `~/.claude/skills/mcp-dev/references/e2e-full-matrix.md` (harness-readiness gate), `~/.claude/skills/mcp-dev/references/secrets-skret.md` (per-server credential layout), `~/.claude/skills/mcp-dev/references/multi-user-pattern.md` (per-JWT-sub isolation).
