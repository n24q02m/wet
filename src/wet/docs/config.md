# WET MCP Server - Config Tool

Server configuration and management.

## Actions

### status

Show current server configuration and status.

```json
{"action": "status"}
```

Returns: auth mode (from `[server]` in `~/.wet/config.toml`) plus the caller's namespace in multi mode, database stats, embedding status (`backend`, resolved `model`, stored `dims`, `available`, and `unavailable_reason` when disabled), reranker status (`backend`, resolved `model`, `available`), cache status, runtime settings (`log_level`, `tool_timeout`), and search metrics (per-provider latency EMA and query counts).

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
| `wet_search_budget` | Integer | Per-provider web-search query budget per process; a provider at the cap is skipped by the chain (`0` = unlimited) |

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

Run first-time setup (browser installs; SearXNG only when `WET_AUTO_SEARXNG`
is on), then check the cloud model cells or pre-download local models.

```json
{"action": "warmup"}
```

Returns: status of each step (`auto_setup`, `geoip_mmdb`, then the cloud
check or the local model downloads).
When a cloud cell (`[models.embed]` / `[models.rerank]`) is configured in
`~/.wet/config.toml`, its model is validated instead of downloading local
ONNX weights.
