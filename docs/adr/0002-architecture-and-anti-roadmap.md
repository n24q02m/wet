# ADR 0002: Wet v2 Architecture and Anti-Roadmap

- **Status:** Accepted (2026-11-24)
- **Context:** W10 architectural consolidation (`AP-14`, `AP-29`, `A10.12`–`A10.16`)
- **Supersedes:** Earlier HTTP-only / multi-user relay drafts

## Decision Drivers

`wet` provides local-first web search, extraction, structured parsing, documentation indexing, and research workflows for coding agents without mandatory paid APIs or hosted infrastructure.

## Architectural Decisions (D1–D5)

### D1. Four-Surface Contract
Every core workflow of `wet` is exposed consistently across four surfaces sharing one in-process core:
1. **CLI-first in-process** (`wet search`, `wet docs`, `wet extract`, `wet doctor`, `wet config`)
2. **MCP stdio** (`wet mcp` / `wet-mcp` without `--http`)
3. **MCP Streamable HTTP** (`wet mcp --http` / `wet server start`)
4. **Plugin surface** (`skills/`, `hooks/`, `.claude-plugin/plugin.json`)

### D2. Three-Tier Multi-User & Profile Isolation (`hull`)
`wet` adopts the 3-tier `hull` model without any multi-user hosted relay:
1. **Principal / Namespace (`subs/<ns>/`):** `no-auth` | `token` | `multi` (`users.toml` maps callers to isolated `subs/<ns>/` directories).
2. **Profile / Environment (`--profile`, `WET_PROFILE`):** Per-profile state rooted under `~/.n24q02m/wet/` (Respecting XDG/AppData, with automatic one-time migration from `~/.wet/`).
3. **Named Provider Pools:** Task-scoped provider cells (`embed`, `rerank`, `chat`, `jev_score`) with credential rotation and cooldown tracking via `hull-core`.

### D3. Keyless-First Search & Explicit SERP Opt-In
Zero-config operation defaults to credential-free, non-SERP-scraping backends (`keenable`, `firecrawl`) or user-provided keys (`tavily`, `brave`, `exa`, `kagi`, `openrouter`) and self-hosted `searxng` (`SEARXNG_URL`). HTML SERP scraping (`duckduckgo`, `startpage`) is disabled by default (`WET_ALLOW_SERP_SCRAPE=false`) and requires explicit opt-in. Provider selection is policy-driven (`WET_ROUTER_POLICY=free|balanced|quality`) with circuit-breaker health tracking.

### D4. Local SQLite Corpus & Deterministic Extraction First
Documentation retrieval (`FTS5` + `sqlite-vec` hybrid + cross-encoder rerank via `fastretrieval`), Cabinets lockfile-aware isolation across 12 lockfile formats, async research `jobs`, and page `watches`/`alerts` live in versioned SQLite schemas managed with Alembic (`docs_001`–`docs_008`). Structured extraction prioritizes deterministic parsing (JSON-LD, OpenGraph, microdata, CSS/XPath) and falls back to BYO-key LLMs only for missing schema fields.

### D5. Bounded Five-Tool MCP Surface
The MCP interface remains strictly five tools: `search`, `extract`, `media`, `config`, `help`. New capabilities (`docs_status`, `docs_audit`, async `agent` jobs, `monitor`) are implemented as actions within `search` and `extract` rather than expanding tool count.

## Anti-Roadmap (R1–R12)

To protect reliability, offline usability, context budget, and single-maintainer sustainability, `wet` explicitly will NOT pursue:
- **R1:** Adding a 6th top-level MCP tool (breaks context budget and tool-name stability).
- **R2:** Hosting a shared multi-user cloud relay or managed SaaS control plane.
- **R3:** Shipping paid CAPTCHA-solving services or anti-bot bypasses as defaults.
- **R4:** Enabling HTML SERP scraping (`duckduckgo`/`startpage`) by default without explicit user opt-in.
- **R5:** Adding mandatory telemetry or external analytics beacons.
- **R6:** Requiring paid cloud LLM keys for baseline search, `docs_query`, `docs_audit`, or `diff`/`monitor`.
- **R7:** Bundling heavy media transcription/OCR stacks (`yt-dlp`, `docling`, vision captions) into `wet`.
- **R8:** Turning `wet` into an always-on cron/email/webhook notification daemon.
- **R9:** Locking runtime support to a single Python minor version (must support Python 3.11–3.15 matrix).
- **R10:** Running paid LLM evaluation suites in automated CI schedules.
- **R11:** Creating separate companion repositories (`wet-bench`, `wet-stdio-proxy`) outside the single `wet` package.
- **R12:** Breaking the backward-compatible `search` / `extract` parameter signatures before a dedicated major release.
