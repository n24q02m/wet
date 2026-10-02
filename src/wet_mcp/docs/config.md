# WET MCP Server - Config Tool

Server configuration and management.

## Actions

### status

Show current server configuration and status.

```json
{"action": "status"}
```

Returns: auth mode (from `[server]` in `~/.wet/config.toml`) plus the caller's namespace in multi mode, database stats, embedding status (`backend`, resolved `model`, stored `dims`, `available`, and `unavailable_reason` when disabled), reranker status (`backend`, resolved `model`, `available`), cache status, SearXNG status.

### set

Update a runtime setting.

```json
{"action": "set", "key": "log_level", "value": "DEBUG"}
```

Valid keys:

| Key | Values | Description |
|:----|:-------|:------------|
| `log_level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | Server log level |
| `tool_timeout` | Integer (seconds) | Max time per tool call |
| `wet_cache` | `true`, `false` | Enable/disable web cache |
| `wet_search_budget` | Integer | Per-search crawl budget |

Settings that are per-task model/provider cells (`[models.*]`), auth mode
(`[server] auth`), and storage paths are host-owned: edit
`~/.wet/config.toml` and restart the server. There is no setup wizard.

### cache_clear

Clear the caller's web cache (search, extract, crawl, map results,
snapshots). In multi mode this clears only the calling namespace's cache.

```json
{"action": "cache_clear"}
```

### docs_reindex

Force re-index documentation for a library.

```json
{"action": "docs_reindex", "key": "fastapi"}
```

### warmup

Pre-download local models and run first-time setup (SearXNG).

```json
{"action": "warmup"}
```

Returns: status of each component (models downloaded, SearXNG ready, etc.).
When a cloud cell (`[models.embed]` / `[models.rerank]`) is configured in
`~/.wet/config.toml`, its model is validated instead of downloading local
ONNX weights.
