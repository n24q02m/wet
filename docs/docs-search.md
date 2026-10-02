# wet-mcp Docs Search (Context7-parity)

> Context7-level docs search.

This document explains how wet-mcp's docs search compares with
Context7, Nia, Docfork, and Grounded Docs, and how to use the three
`search` actions in practice.

## Why a docs search pillar?

Code-assistant agents need fresh, version-aware library documentation
to generate correct snippets. Generic web search returns blog posts
that often lag the latest API; LLMs trained months ago hallucinate APIs
that no longer exist. A self-hosted indexed docs cache solves both:

* **Fresh**: Tier 1 libraries refresh weekly via the `refresh-tier1`
  cron job; Tier 2 ingests on first query.
* **Version-aware**: every chunk is tagged with its `version_id`;
  `docs_query(version="18.0.0")` filters strictly to React 18.
* **Project-aware (Cabinets)**: `docs_lock_project` pins the version
  set declared in your `pyproject.toml` / `package.json` / `go.mod` /
  `Cargo.toml`, so subsequent `docs_query` calls without an explicit
  `version` honor the lock automatically.
* **Token-efficient**: each `docs_query` response respects a
  5000-token cap — the agent gets the most relevant chunks first
  without blowing the context window.

## Library coverage tiers

| Tier | Source | Freshness | Latency |
|---|---|---|---|
| **Tier 1** | Curated `data/tier1_libraries.json` (50 popular libs across React/Next/Vue/Svelte/SolidJS/Express/Nest/Fastify/Prisma/Drizzle/TanStack/TailwindCSS/Zod/Vite/esbuild/Axios/Lodash/TypeScript/FastAPI/Pydantic/SQLAlchemy/Django/Flask/pytest/NumPy/pandas/Polars/Requests/HTTPX/Celery/PyTorch/Transformers/LangChain/Gin/Echo/Fiber/sqlc/Cobra/Tokio/Axum/Serde/clap/MongoDB/PostgreSQL/Redis/DuckDB/SQLite/Kafka...). Metadata seeded at startup; chunks ingested lazily on first `docs_query` or eagerly via the weekly `build_tier1_index.py` script. | Re-validated weekly (>= 90% within 7 days) | Metadata < 50 ms; chunks served from local SQLite (FTS5 + sqlite-vec) |
| **Tier 2** | On-demand discovery via `discover_library` chain (npm / PyPI / crates.io / Go / Hex / Packagist / Pub / RubyGems / NuGet / Maven / GitHub README) and content fetch via `fetch_docs_pages` (web-core ScrapingAgent strategy chain). | Refreshes whenever the chunk fetch runs | First call: 3-30 s for ingestion + indexing; subsequent calls: < 500 ms |

## When to use which action

| Action | Use case |
|---|---|
| `docs_resolve` | "Is this library indexed? Which library_id should I pass?" Disambiguates `next` (Next.js) vs `nextflow`, returns canonical metadata. |
| `docs_query` | "Show me docs chunks for X about topic Y." Honors version pin (`version="18.0.0"`), topic filter (`topic="useState"`), and the 5000-token cap. If `project_path` is supplied AND no explicit `version`, the Cabinets lock wins. |
| `docs_lock_project` | "Lock my project to its declared dependency versions." Walks `pyproject.toml` (PEP 621 + Poetry), `package.json` (deps + devDeps), `go.mod` (require blocks), `Cargo.toml` (deps + dev-deps + build-deps). Subsequent `docs_query` calls passing the same `project_path` honor the lock. |

## Cabinets usage example

```jsonc
// 1. Lock the project once (idempotent; updates last_used_at on re-call).
search(action="docs_lock_project", project_path="/repo/my-react-app")
// -> {"project_path": "/repo/my-react-app",
//     "locked_libraries": [
//       {"id": "react", "name": "react", "version": "^18.3", "indexed": true},
//       {"id": "next",  "name": "next",  "version": "^14",   "indexed": true},
//       {"id": "tailwindcss", ...}
//     ],
//     "total": 8, "indexed": 5}

// 2. Query without specifying version — lock wins.
search(action="docs_query",
       library="react",
       project_path="/repo/my-react-app",
       query="useState pattern for forms")
// -> Chunks filtered to React 18 because the lock pinned ^18.3.

// 3. Override lock by passing an explicit version.
search(action="docs_query",
       library="react",
       version="19.0.0",
       project_path="/repo/my-react-app",
       query="useTransition")
// -> Chunks filtered to React 19; lock is bypassed when caller pins.
```

## Comparison vs alternatives

| Capability | wet-mcp | Context7 | Nia | Docfork | Grounded Docs |
|---|---|---|---|---|---|
| Tier 1 curated libs | 50 (expanding) | 9000+ aspirational | varies | varies | varies |
| Tier 2 on-demand | Yes (web-core ScrapingAgent + RTD/Docusaurus/Mintlify/MkDocs detection) | No | partial | No | partial |
| Version-aware queries | Yes (per-version chunks via `version_id`) | partial | partial | partial | partial |
| Project lock (Cabinets) | Yes (pyproject + package.json + go.mod + Cargo.toml) | partial | No | No | No |
| Token cap per response | 5000 tokens (greedy accumulator) | configurable | partial | configurable | partial |
| Self-hosted | Yes (no upstream subscription) | No | No | partial | Yes |
| Hybrid search (FTS5 + sqlite-vec) | Yes | unknown | unknown | unknown | unknown |
| Local SQLite + WAL | Yes | No | No | partial | partial |

## Performance targets

| Metric | Target | Methodology |
|---|---|---|
| `docs_resolve` + `docs_query` p95 | < 500 ms | 500 popular library queries |
| Recall@10 | >= 0.85 | 200 (library, question, expected_chunks) eval set |
| Tier 1 freshness within 7 days | >= 90% | Weekly `refresh-tier1` cron |
| Tier 2 freshness within 7 days | >= 70% | First-query ingestion timestamps |

## Cross-references

- Action surface: `src/wet_mcp/docs/search.md`
- Server dispatcher: `src/wet_mcp/server.py` (`case "docs_resolve"` /
  `case "docs_query"` / `case "docs_lock_project"`)
- Resolve / query: `src/wet_mcp/sources/docs.py::resolve_library` /
  `query_docs` / `ingest_tier2`
- Project lock: `src/wet_mcp/sources/project_lock.py`
- Tier 1 fixture: `src/wet_mcp/data/tier1_libraries.json`
- Tier 1 warmup: `src/wet_mcp/sources/tier1_warmup.py::maybe_warm`
- Eager Tier 1 build: `scripts/build_tier1_index.py`
- Schema migrations: `alembic/versions/docs_002_libraries.py` +
  `alembic/versions/docs_003_project_context.py`
