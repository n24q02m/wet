# `extract(action="interact")` Guide

Drive a page interactively via patchright (undetected Playwright fork)
with a small action language. Useful for surfaces that need a few
targeted user actions before content becomes visible:

- Search forms with no GET-equivalent URL.
- Simple email/password logins.
- "Load more" buttons on lazy-loading pages.
- Multi-step flows that need a persistent session across calls.

## Action language

Each entry in `actions` is a JSON object with a `type` key plus the
fields required by that type. All actions accept an optional
`timeout_ms` (default 10000).

### `click`

```json
{"type": "click", "selector": "#submit"}
{"type": "click", "description": "Sign in"}
```

Clicks the element matched by `selector` (preferred) or the
`description` fallback (resolved via Playwright's `text=...` locator in
the wet-local implementation; will switch to web-core LLM selector
inference once the upstream contribution lands).

### `fill`

```json
{"type": "fill", "selector": "#email", "value": "user@example.com"}
{"type": "fill", "description": "Email", "value": "user@example.com"}
```

Fills an input. `value` is required; `selector` or `description` must
be supplied.

### `submit`

```json
{"type": "submit", "selector": "form#login"}
```

Submits a form. Uses `page.locator(selector).evaluate('f => f.submit()')`
under the hood so it works on forms without a visible submit button.

### `wait`

```json
{"type": "wait", "selector": "#dashboard", "state": "visible"}
```

Waits for `selector` to reach `state` (visible / hidden / attached /
detached). Useful when an SPA needs a beat to render after `submit`.

## Hard limits

- Max 20 actions per call. Split larger flows across multiple calls
  (use `session` to keep the same browser between them).

## Session persistence

```json
{
  "action": "interact",
  "url": "https://example.com/login",
  "actions": [
    {"type": "fill", "selector": "#email", "value": "user@example.com"},
    {"type": "fill", "selector": "#password", "value": "secret"},
    {"type": "submit", "selector": "form"}
  ],
  "session": "demo-login"
}
```

The first call mints a fresh patchright browser and caches it in the
process-scoped `SessionPool` keyed by `session`. Subsequent calls with
the same `session` reuse the same browser context (cookies +
localStorage preserved). Caps:

- TTL eviction: sessions idle longer than 30 minutes are torn down by
  the background GC loop (runs every 60 seconds).
- LRU eviction: at most 5 concurrent live sessions; opening a 6th evicts
  the oldest.

Sessions are NOT shared across processes. A wet-mcp restart loses all
active sessions.

## Optional screenshot

```json
{
  "action": "interact",
  "url": "https://example.com",
  "actions": [{"type": "click", "selector": "#btn"}],
  "screenshot": true
}
```

Saves a PNG of the post-interaction page under `~/.wet-mcp/interact/`.
The filename is a stable 16-char SHA prefix derived from `(url, actions)`
so identical re-runs collide on the same path. The response includes
`screenshot_path`; failures emit `screenshot_error` and do NOT abort
the call (the snapshot Markdown still returns).

## Response shape

```json
{
  "url": "https://example.com/dashboard",
  "snapshot_markdown": "# Dashboard\n\n...",
  "screenshot_path": "/home/user/.wet-mcp/interact/<sha>.png"
}
```

`snapshot_markdown` is a cheap HTML-stripped + whitespace-collapsed
extraction (truncated at 8000 chars). For full smart-chunks output,
follow up with:

```json
{"action": "extract", "urls": ["<post-interaction-url>"]}
```

## Security notes

- `evaluate` (arbitrary JS in the page context) is **NOT** exposed at
  the MCP boundary. Only the in-process orchestrator uses
  `InteractOps.evaluate` for snapshot capture.
- Network requests still follow wet's SSRF guards; the same private/
  link-local/loopback denylist applies.
- Screenshots are written to `~/.wet-mcp/interact/`; deleting or
  rotating them is the operator's responsibility (no auto-cleanup
  beyond the SHA-keyed collision behaviour).
- `description`-based selectors are best-effort; if your flow depends
  on hitting a specific element, prefer raw CSS selectors.

## Error contract

`extract(action="interact", ...)` returns an `"Error: ..."` string on:

- Missing `url` or `actions`.
- More than 20 actions in one call.
- Unknown action `type` (anything outside click / fill / submit / wait).
- `fill` action without a `value`.
- Action without `selector` AND without `description`.
- Patchright launch failure (network, missing chromium, etc.).
- Action dispatch failure (selector not found within timeout, page
  navigation error, etc.) -- the error string includes the failing
  action and the underlying exception.

The orchestrator never raises -- callers only need to inspect the
return type.
