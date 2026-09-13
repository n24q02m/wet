# WET - Web Extended Toolkit MCP Server

> **Renamed (2026-09-13):** repo is now `wet` — CLI-first (`wet` command). PyPI package stays `wet-mcp` (PyPI policy blocks new project `wet`); MCP server is a secondary surface: run `wet` with no subcommand.

mcp-name: io.github.n24q02m/wet-mcp

> **Renamed (2026-09-13):** package/repo is now `wet` (CLI-first). Install: `pip install wet`. The MCP server remains available: run `wet` with no subcommand (bare = MCP passthrough); legacy package name `wet-mcp` still installs the old CLI.

**Open-source MCP server for AI agents: web search, content extraction, and library docs.**

| Phase | Status | Scope |
|---|---|---|
| Phase 1 | Shipped | web-core ScrapingAgent migration, smart chunks output, search polish, media slim |
| Phase 2 | Shipped | Context7-level docs search: library index (Tier 1 + Tier 2), version-aware queries with token cap, project lock (Cabinets) |
| Phase 3 | **Shipped** | `extract.agent` multi-step research with cited synthesis, `extract.interact` click/fill/submit via patchright (optional session persistence), `docs_004_chunk_summaries` migration, **`media.analyze` removed (v2.0.0)** |

> **Current release: v3.x.** `media(action="analyze")` was removed in the
> v2.0.0 BREAKING release. Use
> [`imagine-mcp`](https://github.com/n24q02m/imagine-mcp)'s
> `understand` action for vision/audio/video analysis. See
> [`docs/migration.md`](docs/migration.md) for the upgrade recipe.

<!-- Badge Row 1: Status -->
[![Mode](https://img.shields.io/badge/mode-daemon_%C2%B7_http_remote_relay-5C6BC0)](https://mcp.n24q02m.com/get-started/modes-overview/)
[![CI](https://github.com/n24q02m/wet/actions/workflows/ci.yml/badge.svg)](https://github.com/n24q02m/wet/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/n24q02m/wet/graph/badge.svg?token=JK19TRLPEX)](https://codecov.io/gh/n24q02m/wet)
[![PyPI](https://img.shields.io/pypi/v/wet-mcp?logo=pypi&logoColor=white)](https://pypi.org/project/wet-mcp/)
[![License: Apache-2.0](https://img.shields.io/github/license/n24q02m/wet-mcp)](LICENSE)

<!-- Badge Row 2: Tech -->
[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](#)
[![SearXNG](https://img.shields.io/badge/SearXNG-3050FF?logo=searxng&logoColor=white)](#)
[![MCP](https://img.shields.io/badge/MCP-000000?logo=anthropic&logoColor=white)](#)
[![semantic-release](https://img.shields.io/badge/semantic--release-e10079?logo=semantic-release&logoColor=white)](https://github.com/python-semantic-release/python-semantic-release)
[![Renovate](https://img.shields.io/badge/renovate-enabled-1A1F6C?logo=renovatebot&logoColor=white)](https://developer.mend.io/)

<!-- BEGIN: AUTO-GENERATED-CROSS-PROMO -->
<details>
  <summary><strong>Sister projects from n24q02m</strong> (click to expand)</summary>

| Project | Tagline | Tag |
|---|---|---|
| [agent-chat-plugin](https://github.com/n24q02m/agent-chat-plugin) | Peer AI agents chat in a shared folder — no human relay, no orchestrator, wor... | Tooling |
| [better-code-review-graph](https://github.com/n24q02m/better-code-review-graph) | Knowledge graph for token-efficient code reviews -- semantic search and call-... | MCP |
| [better-drive](https://github.com/n24q02m/better-drive) | 2-way Google Drive sync with .driveignore filter — rclone engine, Windows tray | Tooling |
| [better-email-mcp](https://github.com/n24q02m/better-email-mcp) | IMAP/SMTP email for AI agents -- read, send, organize folders, and manage att... | MCP |
| [better-godot-mcp](https://github.com/n24q02m/better-godot-mcp) | Composite MCP server for Godot Engine -- 17 composite tools for AI-assisted g... | MCP |
| [better-notion-mcp](https://github.com/n24q02m/better-notion-mcp) | Markdown-first Notion for AI agents -- pages, databases, blocks, and comments... | MCP |
| [better-semantic-release](https://github.com/n24q02m/better-semantic-release) | Drop-in python-semantic-release fork with built-in release-safety guards (orp... | Tooling |
| [better-telegram-mcp](https://github.com/n24q02m/better-telegram-mcp) | Telegram for AI agents -- messages, chats, media, and contacts across both bo... | MCP |
| [better-workspace-mcp](https://github.com/n24q02m/better-workspace-mcp) | Google Workspace MCP server (Docs/Drive/Calendar/Gmail/Sheets/Slides/Tasks/Ch... | MCP |
| [claude-plugins](https://github.com/n24q02m/claude-plugins) | Claude Code plugin marketplace for the n24q02m MCP servers -- install web sea... | Marketplace |
| [imagine-mcp](https://github.com/n24q02m/imagine-mcp) | Image and video understanding + generation for AI agents -- across Gemini, Op... | MCP |
| [jules-task-archiver](https://github.com/n24q02m/jules-task-archiver) | Chrome Extension for bulk operations on Jules tasks via batchexecute API -- a... | Tooling |
| [mcp-core](https://github.com/n24q02m/mcp-core) | Shared foundation for building MCP servers -- Streamable HTTP transport, OAut... | MCP |
| [mnemo-mcp](https://github.com/n24q02m/mnemo-mcp) | Persistent AI memory with hybrid search and embedded sync. Open, free, unlimi... | MCP |
| [fastretrieval](https://github.com/n24q02m/fastretrieval) | Multi-model embedding and reranking runtime via ONNX and GGUF | Library |
| [skret](https://github.com/n24q02m/skret) | Secrets without the server. | CLI |
| [tacet](https://github.com/n24q02m/tacet) | A self-distilling neuro-symbolic cascade that amortises LLM cost across knowl... | Tooling |
| [web-core](https://github.com/n24q02m/web-core) | Shared web infrastructure package for search, scraping, HTTP security, and st... | Library |
| [wet-mcp](https://github.com/n24q02m/wet) | Open-source MCP server for AI agents: web search, content extraction, and lib... | MCP |

</details>
<!-- END: AUTO-GENERATED-CROSS-PROMO -->

## Table of contents

- [Features](#features)
- [Status](#status)
- [Quick install](#quick-install)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Tools](#tools)
- [CLI](#cli)
- [Comparison](#comparison)
- [Security](#security)
- [Build from Source](#build-from-source)
- [Deploy to Cloudflare](#deploy-to-cloudflare)
- [Smithery](#smithery)
- [Trust Model](#trust-model)
- [License](#license)



<a href="https://glama.ai/mcp/servers/n24q02m/wet-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/n24q02m/wet-mcp/badge" alt="WET MCP server" />
</a>

## Features

- **Web Search** -- Embedded SearXNG metasearch (Google, Bing, DuckDuckGo, Brave) with query expansion, TTL cache (1 h general / 5 min time-sensitive), standardized citation format, and 200-token snippet cap. Optional cloud search backends (Tavily, Brave, Exa) as a fallback chain via `SEARCH_BACKENDS`
- **Academic Research** -- Search Google Scholar, Semantic Scholar, arXiv, PubMed, CrossRef, BASE
- **Library Docs** -- Auto-discover and index documentation with FTS5 hybrid search, HyDE-enhanced retrieval, and version-specific docs
- **Content Extract** -- 5-strategy escalation chain via `n24q02m-web-core` `ScrapingAgent` (`basic_http` -> `tls_spoof` -> render backends from `BROWSER_BACKENDS` (`native` / `browserless` / `cf-browser-rendering`) -> optional key-gated `captcha`), markitdown bridge for low-tier HTML/MD fallback, smart chunks structured output (clean text + markdown + JSON-LD + code blocks + metadata), batch processing (up to 50 URLs), deep crawling, site mapping
- **Local File Conversion** -- Convert PDF, DOCX, XLSX, CSV, HTML, EPUB, PPTX to Markdown
- **Media** -- List + download images / videos / audio files. `analyze` was removed in v2.0.0 -- use `imagine-mcp.understand` for vision/audio inference
- **Anti-bot** -- Stealth strategies bypass Cloudflare, Medium, LinkedIn, Twitter
- **Zero Config** -- Built-in local reference embedding + reranking through fastretrieval, no API keys needed. Optional cloud providers (Jina AI, Gemini, OpenAI, Cohere, xAI, Anthropic) selected per task via the `EMBEDDING_MODELS` / `RERANK_MODELS` / `LLM_MODELS` model chains for higher-quality vectors and LLM features
- **Sync** -- Cross-machine sync of indexed docs via Google Drive (OAuth Device Code, no browser redirect)

## Quick install

```bash
# Method 1 (default): plugin install via Claude Code
/plugin marketplace add n24q02m/claude-plugins
/plugin install wet-mcp@n24q02m-plugins

# Method 2 (CLI): direct uvx invocation
claude mcp add wet -- uvx wet-mcp

# Method 3 (source-built container for HTTP / multi-device / OAuth)
docker build --target http -t wet-mcp:local .
docker run -d --name wet-mcp-http -p 8084:8080 \
  -v wet-data:/data -e PUBLIC_URL=https://wet.example.com \
  wet-mcp:local

# Method 4 (remote): point a client at an HTTP deployment
claude mcp add --transport http wet https://<your-host>/mcp
```

Install matrix (stdio unless noted; see the [Setup](https://mcp.n24q02m.com/servers/wet-mcp/setup/) page for full steps):

| Client | Install |
|---|---|
| Claude Code (plugin) | `/plugin marketplace add n24q02m/claude-plugins` then `/plugin install wet-mcp@n24q02m-plugins` |
| Claude Code (stdio) | `claude mcp add wet -- uvx wet-mcp` |
| Codex | register stdio command `uvx wet-mcp` under `mcp_servers` in `~/.codex/config.toml` |
| Gemini CLI | add the `mcpServers` JSON below to `~/.gemini/settings.json` |
| Cursor / Windsurf | add the `mcpServers` JSON below via the client's MCP settings (`mcp.json`) |
| Any client (HTTP self-host) | point the client at `https://<your-host>/mcp` (Streamable HTTP, OAuth-gated) |

Public OCI image publication is discontinued. Existing historical registry tags
remain untouched; new container deployments build from source or use the
Cloudflare-managed registry.

The HTTP endpoint speaks Streamable HTTP and is OAuth-gated -- your client is
prompted to authenticate in the browser on first connect (no API key to paste).
Stand one up via Method 3 or the
[Deploy to Cloudflare](#deploy-to-cloudflare) section.

Full setup matrices live at the canonical docs site
[mcp.n24q02m.com/servers/wet-mcp/setup/](https://mcp.n24q02m.com/servers/wet-mcp/setup/)
and the paste-to-agent snippets at
[claude-plugins/plugins/wet-mcp/setup-with-agent.md](https://github.com/n24q02m/claude-plugins/blob/main/plugins/wet-mcp/setup-with-agent.md)
(per Spec F single source of truth).

## Configuration

wet runs zero-config out of the box: web search uses an embedded local SearXNG,
and embedding/reranking fall back to the bundled local ONNX models through
fastretrieval when no cloud keys are set. For higher-quality results, point each task at a cloud model
chain. All settings are plain environment variables (no app prefix) -- in the
HTTP self-host mode they are entered through the browser setup form instead.

**Model chains** (CSV `provider/model,provider/model`; order = fallback). Leave a
chain empty to use the local ONNX models (embedding/rerank) or to disable LLM
features (LLM):

| Env var | Task | Empty default |
|---|---|---|
| `EMBEDDING_MODELS` | Embeddings for docs search | Local fastretrieval ONNX |
| `RERANK_MODELS` | Result reranking | Local fastretrieval cross-encoder |
| `LLM_MODELS` | `extract(action="agent")` synthesis | LLM features disabled |

**Provider keys** -- the provider is inferred from each model's prefix; supply the
matching key (litellm `<PROVIDER>_API_KEY` convention):

| Model prefix | Key env var | Get it at |
|---|---|---|
| `jina_ai/` | `JINA_AI_API_KEY` | jina.ai/api-key |
| `gemini/` | `GEMINI_API_KEY` | aistudio.google.com/apikey |
| `vertex_express/` | `GOOGLE_VERTEX_EXPRESS_API_KEY` | cloud.google.com/vertex-ai/generative-ai/docs/start/express-mode/overview |
| `openai/` (or bare) | `OPENAI_API_KEY` | platform.openai.com |
| `openrouter/` | `OPENROUTER_API_KEY` | openrouter.ai/settings/keys |
| `cohere/` | `COHERE_API_KEY` | dashboard.cohere.com |
| `xai/` | `XAI_API_KEY` | console.x.ai |
| `anthropic/` | `ANTHROPIC_API_KEY` | console.anthropic.com |

Any other litellm provider works via env passthrough -- see
[litellm provider docs](https://docs.litellm.ai/docs/providers) for its key name.

`FASTRETRIEVAL_CACHE_PATH` controls the local model cache.

**Search backends** -- `SEARCH_BACKENDS` is an ordered runtime fallback chain:
`searxng` (default, local or external via `SEARXNG_URL`), keyed `tavily` / `brave` /
`exa` / `kagi`, optional-key `firecrawl`, and credential-free `duckduckgo` /
`startpage`. Keyed providers use `TAVILY_API_KEY`, `BRAVE_API_KEY`, `EXA_API_KEY`,
or `KAGI_API_KEY`. Firecrawl attempts a keyless request when `FIRECRAWL_API_KEY`
is absent; rejection or a DuckDuckGo/Startpage bot challenge advances the chain.
The same chain serves web search, research, similar-page search, agent search,
and docs discovery/indexing fallbacks. SearXNG retains its science-category
filter for research; other providers use their own search capabilities.
Hosted users configure the chain and keys in their own relay record. An empty
hosted record never inherits an operator's provider key or local SearXNG URL;
single-user stdio still uses env/settings and preserves the public local path.

**Browser render backends** -- `BROWSER_BACKENDS` (CSV, escalation chain) picks
the headless render leg of `extract`: `native` (in-process chromium, the
zero-config default), `browserless` (self-host render service -- set
`BROWSERLESS_URL` + `BROWSERLESS_TOKEN`), and `cf-browser-rendering` (Cloudflare
Browser Rendering -- set `CF_ACCOUNT_ID` + `CF_BROWSER_RENDERING_TOKEN`). Empty
chain falls back to `native`. Set `CAPSOLVER_API_KEY` to append an optional,
key-gated CAPTCHA tier as the last escalation step.

**Robots policy** -- set `RESPECT_ROBOTS_TXT=true` to enforce `robots.txt`
across both the `extract` strategy chain and the Crawl4AI-backed `crawl`,
`sitemap`, and `list_media` actions. The default is `false` to preserve existing
deployment behaviour; configure this process-level policy explicitly when the
operator requires robots enforcement.

**Disable local fallbacks** -- opt out of the heavy in-process local fallbacks
per capability (e.g. on a slim container that renders/searches/embeds via cloud
backends only): `DISABLE_LOCAL_BROWSER`, `DISABLE_LOCAL_SEARCH`,
`DISABLE_LOCAL_EMBED`, `DISABLE_LOCAL_RERANK`.

**Docs sync** -- `SYNC_ENABLED` (default `true`), `GOOGLE_DRIVE_CLIENT_ID`
(required for sync), `SYNC_FOLDER` (default `wet-mcp`), `SYNC_INTERVAL` (default
`300`s). Sync uses Google Drive over the OAuth Device Code flow (no browser
redirect).
`DOCS_DB_BACKEND=cf-d1` disables GDrive/S3 file sync, including automatic
startup, relay wizard and device-code setup, even if legacy sync settings remain.
Non-CF SQLite deployments retain GDrive sync; `SYNC_S3_BUCKET` selects S3
instead, and `SYNC_ENABLED=false` disables both.

**HTTP self-host** -- `MCP_TRANSPORT=http`, `PUBLIC_URL=<your-domain>`. The setup
form is gated by `MCP_RELAY_PASSWORD`; multi-user deployments require
`CREDENTIAL_SECRET` (per-user vault key), `MCP_JWT_SIGNING_SECRET` (rotatable
OAuth JWT key), and `MCP_DCR_SERVER_SECRET`.

Example stdio config (cloud chains):

```json
{
  "mcpServers": {
    "wet": {
      "command": "uvx",
      "args": ["wet-mcp"],
      "env": {
        "EMBEDDING_MODELS": "jina_ai/jina-embeddings-v5-text-small",
        "RERANK_MODELS": "jina_ai/jina-reranker-v3",
        "LLM_MODELS": "gemini/gemini-3-flash-preview",
        "JINA_AI_API_KEY": "jina_xxx",
        "GEMINI_API_KEY": "AIza_xxx"
      }
    }
  }
}
```

## Status

Stable architecture with two transports: **stdio** (default, local) and
**HTTP** (self-host, OAuth-gated). No daemon-bridge layer and no auto-spawn
from stdio. The `media.analyze` action was removed in the v2.0.0 BREAKING
release -- see [`docs/migration.md`](docs/migration.md) for the upgrade
recipe. Current release line: v3.x.

## Documentation

Full docs at **[mcp.n24q02m.com/servers/wet-mcp/setup/](https://mcp.n24q02m.com/servers/wet-mcp/setup/)**:

- [Setup](https://mcp.n24q02m.com/servers/wet-mcp/setup/) -- install methods for Claude Code, Codex, Gemini CLI, Cursor, Windsurf, mcp.json
- [Modes overview](https://mcp.n24q02m.com/get-started/modes-overview/) -- stdio / local-relay / remote-relay / remote-oauth
- [Multi-user setup](https://mcp.n24q02m.com/get-started/multi-user/) -- per-JWT-sub credential model

In-repo references (Spec F single source of truth: setup docs live in
[claude-plugins/plugins/wet-mcp/](https://github.com/n24q02m/claude-plugins/tree/main/plugins/wet-mcp)):

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) -- web-core ScrapingAgent integration, strategy chain, storage layout, LLM provider dispatch
- [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md) -- v1.x baseline coverage / latency placeholders + tier-1 fixture metrics

**Install with AI agent** -- paste this to your AI coding agent:

> Install MCP server `wet-mcp` following the steps at
> https://raw.githubusercontent.com/n24q02m/claude-plugins/main/plugins/wet-mcp/setup-with-agent.md

## Tools

6 MCP tools (3 domain + `config` + `help` + `config__open_relay`). The legacy
`setup` tool merged into `config` action dispatch.

| Tool | Description |
|:-----|:------------|
| `search` | Web (SearXNG metasearch), news, images, academic research (Scholar / arXiv / PubMed / CrossRef / Semantic Scholar / BASE), library docs (HyDE + FTS5), find similar pages. Includes `docs_resolve` (library name -> ranked id), `docs_query` (version-aware + topic + 5000-token cap), `docs_lock_project` (Cabinets project pin via pyproject / package.json / go.mod / Cargo.toml manifest detection). |
| `extract` | URL -> smart chunks dict (`clean_text` + `markdown` + `structured_data` + `code_blocks` + `metadata`) via web-core 5-strategy chain. Batch processing (up to 50 URLs), deep crawling, site mapping, local file conversion (PDF/DOCX/XLSX/PPTX/EPUB), structured extraction (JSON Schema) |
| `media` | `list` (discover URLs from gallery pages), `download` (SSRF-safe). `analyze` was removed in v2.0.0 -- use `imagine-mcp.understand` instead |
| `config` | `status`, `set`, `cache_clear`, `docs_reindex`, `warmup`, `setup_sync`, `setup_status`, `setup_skip`, `setup_reset`, `setup_complete` |
| `help` | Per-tool documentation: `search`, `extract`, `media`, `config` |
| `config__open_relay` | Re-trigger the zero-config relay setup flow (prints a fresh relay URL for the browser form). Registered via `mcp-core`'s `register_open_relay_tool` so an LLM can restart setup without a manual restart. |

> **Media boundary**: For vision / audio understanding (image captioning,
> OCR, audio transcription, video summarization), use
> [imagine-mcp](https://github.com/n24q02m/imagine-mcp). `media.analyze`
> was removed in wet v2.0.0 -- use `imagine-mcp.understand` instead.

## CLI

The `wet-mcp` console script starts the server and also exposes a few one-shot
operator subcommands. A bare invocation (or any leading-dash flag) starts the
server; a leading positional argument is dispatched as a subcommand.

```bash
wet-mcp                        # start the server over stdio (default transport)
wet-mcp --http                 # start the server over Streamable HTTP (self-host mode)

wet-mcp auth google            # authorize the Google credential provider for Drive sync
wet-mcp logout                 # clear the local Google Drive sync token
wet-mcp warmup                 # pre-download local models + run auto-setup (SearXNG, browser) to avoid first-run delays
wet-mcp docs reindex <library> # drop the cached docs index for <library>; the next docs search re-indexes it
```

`auth google` accepts an optional bring-your-own OAuth client via `--client-id`
and `--client-secret` (single-user / local machine only; the token is written to
the local store). Each subcommand prints a JSON result and exits.

| Capability | wet-mcp | Brave Search | Tavily | Firecrawl | Context7 |
|---|---|---|---|---|---|
| Web search | Yes (SearXNG aggregation) | Yes | Yes | No | No |
| Extract URL | Yes (5-strategy chain) | No | Yes (basic) | Yes | No |
| Media list / download | Yes | No | No | No | No |
| Library docs search | Yes (Tier 1 curated + Tier 2 on-demand, version-aware, Cabinets) | No | No | No | Yes |
| Academic research | Yes (6 providers) | No | No | No | No |
| Self-hostable | Yes | No | No | No | Yes |
| Free tier | Yes (open source) | Limited | Limited | Limited | Yes |

## Security

- **SSRF prevention** -- URL validation on crawl targets
- **Graceful fallbacks** -- Cloud → Local embedding, multi-tier crawling
- **Error sanitization** -- No credentials in error messages
- **File conversion sandboxing** -- Optional `CONVERT_ALLOWED_DIRS` restriction

## Build from Source

```bash
git clone https://github.com/n24q02m/wet.git
cd wet-mcp
uv sync
uv run wet-mcp
```

## Deploy to Cloudflare

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/n24q02m/wet)

Run your own single-user wet instance serverless on Cloudflare (Containers + D1 + Vectorize + KV).

**Prerequisites:** a Cloudflare account on the **Workers Paid plan** — required for Containers, D1, and Vectorize (the Cloudflare free tier does not include them) — and the `wrangler` CLI.

1. `git clone https://github.com/n24q02m/wet && cd wet-mcp`
2. `wrangler login`
3. Provision resources and apply the D1 schema:
   ```
   wrangler d1 create wet-docs
   wrangler d1 execute wet-docs --file migrations/0001_init_wet.sql --remote
   wrangler d1 execute wet-docs --file migrations/0002_project_context.sql --remote
   wrangler d1 execute wet-docs --file migrations/0003_version_index_state.sql --remote
   wrangler vectorize create wet-docs-vectors --dimensions 768 --metric cosine
   wrangler kv namespace create wet-kv
   ```
   Paste the returned IDs into `wrangler.jsonc`.
4. Build the slim HTTP image from this checkout and push it directly to
   Cloudflare's managed registry (CF Containers cannot pull from external
   registries):
   ```
   docker build --target http --build-arg SLIM=1 -t wet-mcp:beta .
   wrangler containers push wet-mcp:beta   # prints registry.cloudflare.com/<ACCOUNT_ID>/wet-mcp:beta
   ```
5. Set operator auth/storage and Browser Run secrets:
   ```
   wrangler secret put CREDENTIAL_SECRET
   wrangler secret put MCP_JWT_SIGNING_SECRET
   wrangler secret put MCP_RELAY_PASSWORD
   wrangler secret put MCP_DCR_SERVER_SECRET
   wrangler secret put CF_BROWSER_RENDERING_TOKEN
   ```
6. `wrangler deploy` and complete setup in the browser relay form at your Worker domain.

Storage maps to Cloudflare via `MCP_STORAGE_BACKEND=cf-kv` (credentials/tokens, encrypted),
`DOCS_DB_BACKEND=cf-d1` (docs + BM25 full-text), and Vectorize (embeddings). The
default headless renderer is `BROWSER_BACKENDS=cf-browser-rendering`. Local
ONNX fallbacks are disabled in the slim image; configure search and cloud
retrieval through each authenticated subject's relay record. Worker-wide
search/model chains and provider keys are not forwarded to the container.

For a Cloudflare AI Gateway route, enter the following values in that subject's
relay form (`<CF_AIG_BASE>` is the account/gateway base URL):

| Relay field | Value |
|---|---|
| `SEARCH_BACKENDS` | `tavily,duckduckgo,startpage` |
| `LLM_MODELS` | `openrouter/minimax/minimax-m3:free` |
| `LLM_API_BASE` | `<CF_AIG_BASE>/openrouter/v1` |
| `EMBEDDING_MODELS` | `cohere/embed-v4.0` |
| `EMBEDDING_API_BASE` | `<CF_AIG_BASE>/cohere/v2/embed` |
| `RERANK_MODELS` | `cohere/rerank-v4.0-fast` |
| `RERANK_API_BASE` | `<CF_AIG_BASE>/cohere` |

Store the matching OpenRouter/Cohere credentials and any keyed search-provider
credentials (such as `TAVILY_API_KEY`) in the same subject record.
All Wet synthesis and summaries use `LLM_MODELS`; there is no separate
`SUMMARY_MODELS` field. This completion chain has no paid or alternate-model
fallback. Cohere embedding/reranking and Browser Run may incur charges; obtain
the required budget authorization before exercising them. Provision Vectorize
and `EMBEDDING_DIMS` for a dimension supported by the selected embedding model.
The earlier 768-dimension example is not a Cohere v4 compatibility guarantee.

### Deployment (maintained instance)

Every tagged release deploys automatically: the CD `deploy-cf` job checks out
the released tag, builds the http-slim image, pushes it to the Cloudflare-managed
registry as immutable `:<release-tag>`, deploys the Worker, and gates on a canary
health check -- a release is live at exactly its own version. A beta dispatch
redeploys the beta; a stable dispatch is maintainer-gated. Manual `wrangler deploy`
against the maintained instance is not permitted: it would break the
release-tag ↔ live-image correspondence. Self-hosting on your own Cloudflare
account (the button above) is unaffected.

## Smithery

wet-mcp ships a [`smithery.yaml`](smithery.yaml) so it can be installed and run
through [Smithery](https://smithery.ai). The manifest declares a stdio start
command (`uvx --python 3.13 wet-mcp`) with an empty config schema -- no config is
required to start, and providers and credentials are configured at runtime via
the server's own config flow (see [Configuration](#configuration)).

## Trust Model

This plugin implements **TC-Local** (machine-bound, single trust principal). See [mcp-core trust model](https://mcp.n24q02m.com/servers/mcp-core/trust-model/) for full classification.

| Mode | Storage | Encryption | Who can read your data? |
|---|---|---|---|
| stdio (default) | `~/.wet-mcp/config.json` | AES-GCM, machine-bound key | Only your OS user (file perm 0600) |
| HTTP self-host | Same as stdio | Same | Only you (admin = user) |

## License

Apache-2.0 -- See [LICENSE](LICENSE).
