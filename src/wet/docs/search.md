# search Tool Documentation

Search the web, academic papers, or library documentation.

## Actions

### search
Web search via the `SEARCH_BACKENDS` provider chain with runtime fallback: `searxng` (self-host) | `tavily` | `brave` | `exa` | `kagi` (cloud, keyed) | `firecrawl` (key optional — keyless attempt) | `duckduckgo` | `startpage` (credential-free HTML scrape, uvx-safe; may be bot-challenged on datacenter IPs — the chain then advances to the next backend).

**Parameters:**
- `query` (required): Search query string
- `categories`: Search category - general, images, videos, files (default: general)
- `max_results`: Maximum results to return (default: 10)
- `time_range`: Filter by recency - day, week, month, year
- `language`: Search language code - en, vi, ja, etc. (auto-detected by default)
- `include_domains`: Only include results from these domains (max 5) - ["github.com", "stackoverflow.com"]
- `exclude_domains`: Exclude results from these domains (max 10) - ["pinterest.com"]

- `expand`: Enable LLM query expansion for broader coverage (default: false, requires LLM)
- `enrich`: Fetch actual page content for better snippets (default: false, adds 2-5s latency)

Results are semantically reranked for better relevance. Duplicate URLs are normalized (tracking params stripped) and limited to 3 per domain.

Every response includes a `search_backend` trace with the requested and attempted
backend names, the selected backend, and a `fallback` result (`none`, `used`,
`exhausted`, or `unavailable`).

**Example:**
```json
{"action": "search", "query": "python web scraping tutorial", "max_results": 5}
{"action": "search", "query": "react hooks", "include_domains": ["react.dev"], "time_range": "month"}
{"action": "search", "query": "async python", "exclude_domains": ["w3schools.com"], "language": "en"}
{"action": "search", "query": "machine learning optimization", "expand": true, "enrich": true}
```

---

### research
Academic and scientific search using SearXNG science engines (Google Scholar, Semantic Scholar, arXiv, PubMed, CrossRef, BASE).

**Parameters:**
- `query` (required): Research query string
- `max_results`: Maximum results to return (default: 10)
- `time_range`: Filter by recency - day, week, month, year
- `language`: Search language code
- `include_domains`: Only include results from these domains
- `exclude_domains`: Exclude results from these domains

**Example:**
```json
{"action": "research", "query": "transformer attention mechanism", "max_results": 5}
```

**Returns:** Results include source_type (arxiv, google_scholar, semantic_scholar, pubmed, doi, academic).

---


### docs
Search library/framework documentation with auto-indexing. First call indexes docs into local FTS5 database; subsequent calls use cached index for instant results.

**Parameters:**
- `query` (required): What to search for in docs
- `library` (required): Library name (e.g., "react", "fastapi", "pytorch")
- `language`: Programming language for disambiguation (e.g., "python", "java", "rust"). Guides which registries to search and improves discovery for cross-language names. Supports: python/py, javascript/js/ts, rust/rs, go/golang, java, kotlin, csharp/c#, php, ruby, swift, c, cpp/c++, zig, dart, elixir, haskell, scala, and more.
- `version`: Specific version (default: latest)
- `limit`: Maximum results (default: 10)

**Discovery order:** llms.txt > npm/PyPI/crates.io registry > SearXNG fallback > Crawl4AI fetch.

**When to specify `language`:**
- Cross-language name collisions: "redis" (Python vs Node.js), "protobuf" (Python vs JS)
- Languages without registry: Java, C#, PHP, Ruby, C/C++, Swift, Zig
- Tools and system packages: "cmake", "boost", "openssl"

**Example:**
```json
{"action": "docs", "query": "how to create a router", "library": "fastapi"}
{"action": "docs", "query": "dependency injection", "library": "spring-boot", "language": "java"}
{"action": "docs", "query": "entity framework migrations", "library": "efcore", "language": "csharp"}
```

**Returns:** Relevant documentation chunks with title, content, URL, and relevance score.

---

### docs_resolve
Free-form library name → ranked list of resolved libraries. Returns `library_id`, `canonical_name`, `tier`, `homepage`, `github_url`, `latest_version`, etc. Useful when the agent wants to disambiguate `next` (Next.js) vs `nextflow` before calling `docs_query`.

**Parameters:**
- `query` (required): Library name (free-form, case-insensitive)
- `limit`: Max results (default: 10, smaller = stricter ranking)

**Example:**
```json
{"action": "docs_resolve", "query": "react"}
{"action": "docs_resolve", "query": "next", "limit": 3}
```

---

### docs_query
Version-aware library docs query honoring optional topic filter, project lock (Cabinets), and a 5000-token response cap.

**Parameters:**
- `query` (required): What to search for
- `library` (required): Library name OR `library_id` from `docs_resolve`
- `version`: Specific version (default: `latest`)
- `topic`: Section/topic filter (e.g. `useState`, `routing`)
- `project_path`: Absolute path to project root. When set AND no explicit `version` is given, the version pinned by a prior `docs_lock_project` call is used.
- `limit`: Max chunks (default: 10, also subject to 5000-token cap)

**Example:**
```json
{"action": "docs_query", "library": "react", "version": "18.0.0", "topic": "useState", "query": "how do I share state between components?"}
{"action": "docs_query", "library": "fastapi", "project_path": "/repo/my-api", "query": "dependency injection"}
```

When the requested library is not yet indexed, the action returns `status: "indexing_in_progress"` and starts a background Tier 2 ingestion (GitHub README + RTD/Docusaurus/Mintlify detection via web-core scraper). Retry shortly.

---

### docs_lock_project
Detect project manifests at `project_path` (`pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`) and persist the locked library set into the Cabinets `project_context` table. Subsequent `docs_query` calls passing the same `project_path` honor the pinned versions automatically.

**Parameters:**
- `project_path` (required): Absolute path to project root.

**Example:**
```json
{"action": "docs_lock_project", "project_path": "/repo/my-app"}
```

**Returns:** Lock summary with `project_path`, `locked_libraries` (each `{id, name, version, indexed}`), `total`, `indexed`.

---

### similar
Find pages similar to a given URL. Extracts content from the source page, generates search keywords, and finds related pages via SearXNG.

**Parameters:**
- `query` (required): URL of the source page (must start with http:// or https://)
- `max_results`: Maximum results to return (default: 10)

**Example:**
```json
{"action": "similar", "query": "https://example.com/interesting-article"}
```

**Note:** Requires LLM for keyword extraction. Falls back to page title if no LLM available.

---

## Caching

When `WET_CACHE=true` (default), search and research results are cached locally:
- search/research: 1 hour TTL
- docs: Persistent FTS5 index (no TTL)
