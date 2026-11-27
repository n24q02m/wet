# extract Tool Documentation

Extract content from web pages, crawl sites, or map site structure.

## Actions

### extract
Get clean content from one or more URLs. Powered by `hull_web`'s `ScrapingAgent`
escalation chain (`basic_http` -> `tls_spoof` -> `headless`) with cache-recommended
ordering and LLM selector inference fallback.

**Parameters:**
- `urls` (required): List of URLs to extract
- `format`: Reserved for backward compat (smart chunks always emit both `markdown` and `clean_text`)
- `stealth`: Forwarded to the headless strategy when the agent is built (default: false)

**Example:**
```json
{"action": "extract", "urls": ["https://example.com/article"]}
```

**Smart chunks output (per URL):**

```json
{
  "url": "https://example.com/article",
  "clean_text": "Article body without HTML tags or markdown decorators",
  "markdown": "# Title\n\nBody...",
  "structured_data": [{"@type": "Article", "headline": "..."}],
  "code_blocks": [{"lang": "python", "code": "x = 1"}],
  "metadata": {
    "title": "Page title (HTML <title> or first H1)",
    "url": "https://example.com/article",
    "scrape_strategy_used": "basic_http",
    "latency_ms": 412.0,
    "content_length": 14523,
    "source_format": "html",
    "headings": [{"level": "1", "text": "Title"}, {"level": "2", "text": "Sub"}]
  }
}
```

`structured_data` contains all `<script type="application/ld+json">` blobs (JSON-LD).
`code_blocks` lists every fenced code block in the markdown rendition with detected
language hint (`plain` when none).

PDF/DOCX/PPTX/XLSX URLs bypass the agent and use the markitdown bridge directly,
returning the legacy `{url, title, content, converter}` shape.

**Retry and circuit breaker:** plain HTTP fetches (the `basic_http` leg and the
markitdown download) retry GET/HEAD on connection errors, timeouts and HTTP
429/502/503/504, with exponential backoff, jitter and `Retry-After` support,
inside a total time budget. Other methods are never retried. Each host also has
a circuit breaker: after `EXTRACT_BREAKER_THRESHOLD` URLs in a row fail on that
host with transient errors, its URLs fail fast for `EXTRACT_BREAKER_COOLDOWN`
seconds, then one probe request decides whether the circuit closes again. A
fast-failed URL returns:

```json
{"url": "https://down.example/page", "error": "Circuit open for down.example: recent requests failed with transient errors; retry after 42s.", "retry_after": 42}
```

A definitive answer such as HTTP 404 never trips the breaker, and one host's
failures never block another host.

---

### crawl
Deep crawl starting from root URLs.

**Parameters:**
- `urls` (required): List of root URLs to crawl from
- `depth`: How many levels deep to crawl (default: 2)
- `max_pages`: Maximum pages to crawl (default: 20)
- `format`: Output format (default: markdown)
- `stealth`: Enable stealth mode (default: false)

**Example:**
```json
{"action": "crawl", "urls": ["https://docs.example.com"], "depth": 3}
```

---

### map
Discover site structure without extracting content.

**Parameters:**
- `urls` (required): List of root URLs
- `depth`: Discovery depth (default: 2)
- `max_pages`: Maximum URLs to discover (default: 20)

**Example:**
```json
{"action": "map", "urls": ["https://example.com"]}
```

---

### convert
Convert local files to Markdown. Supports: PDF, DOCX, PPTX, XLSX, CSV, JSON, XML, HTML, EPUB, TXT, images (EXIF metadata).

**Parameters:**
- `paths` (required): List of absolute file paths (max 10)

**Example:**
```json
{"action": "convert", "paths": ["/home/user/report.pdf", "/home/user/data.xlsx"]}
```

**Security:** Paths are validated against traversal attacks, symlink escapes, and directory allowlist (default: the server working directory and the temp directory; set `CONVERT_ALLOWED_DIRS` to a comma-separated list of absolute paths to change it). Max file size: 100MB (configurable via `CONVERT_MAX_FILE_SIZE`).

---

### batch
Batch extract content from multiple URLs with per-domain rate limiting. Polite crawling: max 2 concurrent per domain, 1 req/s per domain, 10 global concurrent. Returns partial results on failure.

**Parameters:**
- `urls` (required): List of URLs (max 50)
- `format`: Output format (default: markdown)
- `stealth`: Enable stealth mode (default: false)

**Example:**
```json
{"action": "batch", "urls": ["https://a.com/1", "https://a.com/2", "https://b.com/1", ...]}
```

**Returns:** `{results: [...], errors: [...], summary: {total, success, failed}}`

---

### extract_structured
Extract structured data from web pages using LLM + JSON Schema. Provide a schema defining the data structure you want, and the LLM extracts matching data from the page content.

**Parameters:**
- `urls` (required): List of URLs to extract from
- `schema` (required): JSON Schema dict defining the expected output structure
- `prompt`: Additional instructions for the LLM (optional)
- `stealth`: Enable stealth mode (default: false)

**Example:**
```json
{
  "action": "extract_structured",
  "urls": ["https://example.com/pricing"],
  "schema": {
    "type": "object",
    "properties": {
      "plans": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name": {"type": "string"},
            "price": {"type": "string"},
            "features": {"type": "array", "items": {"type": "string"}}
          }
        }
      }
    }
  },
  "prompt": "Extract all pricing plans with their features"
}
```

**Returns:** `{data: <extracted>, urls: [...]}` with `"extraction_method": "deterministic"` when JSON-LD/OpenGraph/microdata satisfies the schema cleanly without an LLM, or falls back to your configured `[models.chat]` LLM cell.

**Requires:** Only requires an LLM when deterministic HTML/JSON-LD extraction cannot satisfy all required schema properties (or when custom `prompt` instructions are supplied).

---

### agent
Multi-step research orchestration -- search the web, extract the top results, then synthesise a citation-preserving Markdown answer with deterministic citation `verification`. Supports synchronous execution or persistent async lifecycle (`job_op`: `start` | `status` | `resume` | `steer` | `cancel`, plus `job_id`).

**Parameters:**
- `query` (required): Research question to answer
- `max_urls`: Number of search hits to extract and cite (default: 5, hard cap: 20)
- `synthesis_model`: Override the LLM model used for the synthesis step; falls back to the `[models.chat]` cell's model
- `token_budget`: Soft cap on prompt tokens for the synthesis call (default: 10000). Each extract gets `(token_budget - 200) / N` tokens of room and is truncated above that.
- `job_op`: Optional async job lifecycle operation (`start`, `status`, `resume`, `steer`, `cancel`)
- `job_id`: Job ID for `status`, `resume`, `steer`, or `cancel`
- `steering` (`steer` only): Changes for a pending or running job, any of:
  - `add_focus` / `remove_focus`: focus topics (string or list of strings)
  - `add_constraints`: requirements the answer must respect
  - `exclude_sources`: hosts or URLs to drop; subdomains are dropped too
  - `depth`: follow-up search rounds still allowed (0-5, default 2)

**Example:**
```json
{"action": "agent", "query": "latest pydantic 2 changes", "max_urls": 5}
{"action": "agent", "job_op": "start", "query": "compare python lockfile tools"}
{"action": "agent", "job_op": "status", "job_id": "job_123abc"}
{"action": "agent", "job_op": "steer", "job_id": "job_123abc", "steering": {"add_focus": ["pricing"], "exclude_sources": ["example.com"], "depth": 1}}
```

**Returns:** Synchronous mode returns `{markdown, sources, per_url_metadata, verification}`; async `start` returns `{job_id, status: "running", query}`.

**Steering a running job:** a `steer` call is recorded with a timestamp and
applied at the job's next step (before its next search round, before
extraction, or before synthesis). It returns `{job_id, status, steer}`, where
`steer` holds `seq`, `at` and the normalised `changes`. Each focus topic the
job has not searched yet adds one follow-up search round (`"<query> <topic>"`)
while depth remains; follow-up rounds skip URLs already extracted, and all
rounds together extract at most 20 URLs. Excluded sources are dropped before
extraction and again before synthesis. Constraints and focus topics are passed
to the synthesis prompt. Once a job is synthesising, or has completed, failed
or been cancelled, `steer` returns an error. `status` then shows `progress`
(the last step reached), the `steering` log (each entry with `applied_at`,
`applied_step` and `applied_round` once applied) and the effective
`direction`. Steering is applied by the process running the job; a job left
`running` by a stopped server picks up its pending steering on `resume`.

---

### monitor
Persistent URL change monitoring watches and noise-filtered alerts stored per namespace (`watches` and `alerts` tables).

**Parameters:**
- `monitor_op`: `watch` | `list` | `unwatch` | `check`
- `url`: Target URL to watch/unwatch/check (or `urls[0]`)
- `interval_seconds`: Advisory check interval in seconds (default: 3600)

**Example:**
```json
{"action": "monitor", "monitor_op": "watch", "url": "https://example.com/changelog"}
{"action": "monitor", "monitor_op": "check", "url": "https://example.com/changelog"}
```

**Returns:**
```json
{
  "markdown": "# Pydantic 2 highlights\n\nThe v2 release [1] introduces ...",
  "sources": [
    {"index": 1, "url": "https://...", "title": "..."}
  ],
  "per_url_metadata": [
    {"url": "...", "extract_strategy": "basic_http", "tokens": 487, "error": null}
  ]
}
```

**Requires:** a configured `[models.chat]` cell in `~/.wet/config.toml` (or the `HULL_CHAT_API_KEY` / `OPENROUTER_API_KEY` env credentials). Returns a clear "no LLM provider detected" error string when none is set instead of crashing the SDK.

---

### interact
Drive a page interactively via patchright (click / fill / submit / optional screenshot). Useful for surfaces that need a few targeted user actions before content becomes visible (search forms, simple logins, "load more" buttons). Exposes a small action language so callers do not have to embed JavaScript.

**Parameters:**
- `url` (required): Page URL to drive
- `actions` (required): List of `{type, selector?, description?, value?}` operations applied in order. Supported types: `click`, `fill` (uses `value`), `submit`, `wait`. Either `selector` OR `description` (LLM-resolved selector fallback, NICE) must be provided.
- `session`: Persistent session id; reusing the same id across calls keeps the same browser + cookies + localStorage (TTL eviction, see `docs/interact.md`)
- `screenshot`: When `true`, save a PNG of the post-interaction page under `~/.wet/interact/` and include its path in the response (default: false)

**Example:**
```json
{
  "action": "interact",
  "url": "https://example.com/login",
  "actions": [
    {"type": "fill", "selector": "#email", "value": "user@example.com"},
    {"type": "fill", "selector": "#password", "value": "secret"},
    {"type": "submit", "selector": "form#login"}
  ],
  "session": "demo-login"
}
```

**Returns:**
```json
{
  "url": "https://example.com/dashboard",
  "snapshot_markdown": "# Dashboard\n\n...",
  "screenshot_path": "/home/user/.wet/interact/<sha>.png"
}
```

See `docs/interact.md` for the full action-language reference, session-persistence semantics, and security notes.

---

## Anti-Bot Features

The `stealth` parameter enables:
- Stealth mode: Masks navigator.webdriver, emulates plugins
- Undetected browser: For advanced detection (Cloudflare, Datadome)

## Caching

When `WET_CACHE=true` (default), all extraction results are cached locally:
- extract/crawl/map: 1 day TTL
