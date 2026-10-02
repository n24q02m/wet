# media Tool Documentation

Media discovery and download from web pages.

## Actions

### list
Scan a page and return media URLs with metadata.

**Parameters:**
- `url` (required): Page URL to scan
- `media_type`: Type of media - images, videos, audio, files, all (default: all)
- `max_items`: Maximum items per type (default: 10)

**Example:**
```json
{"action": "list", "url": "https://example.com/gallery", "media_type": "images"}
```

**Returns:**
```json
{
  "images": [
    {"src": "https://...", "alt": "...", "width": 800, "height": 600}
  ],
  "videos": [],
  "audio": []
}
```

---

### download
Download specific media files to local storage for further analysis or processing.
Use this when you need to inspect the actual file content (e.g., sending an image to a Vision LLM).

**Parameters:**
- `media_urls` (required): List of media URLs to download
- `output_dir`: Output directory (default: ~/.wet-mcp/downloads)

**Example:**
```json
{"action": "download", "media_urls": ["https://example.com/image.jpg"]}
```

**Returns:**
```json
[
  {"url": "...", "path": "/path/to/file.jpg", "size": 12345}
]
```

---

### analyze (REMOVED in v2.0.0)

> **Removed.** `media(action="analyze", ...)` was removed in wet
> **v2.0.0**. Calling it now returns the standard unknown-action error
> with a migration hint.
>
> **Use** [`imagine-mcp`](https://github.com/n24q02m/imagine-mcp)'s
> `understand` action instead -- imagine-mcp is the dedicated
> multimodal pipeline (provider routing, caching, vision/audio/video)
> and is where all analysis features now land.
>
> Replacement flow:
> 1. `wet: media(action="list", url=...)` -- discover media URLs.
> 2. `wet: media(action="download", media_urls=[...])` -- save locally.
> 3. `imagine: understand(file=..., prompt=...)` -- analyze.

---

## Workflow

1. Use `list` to discover media on a page
2. Use `download` to save specific files locally
3. Hand the downloaded path off to `imagine-mcp`'s `understand` action
   for LLM analysis (vision/audio/video)
