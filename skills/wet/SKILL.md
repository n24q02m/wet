---
name: wet
description: Dùng wet CLI để tải/đọc/nén tài liệu web & library docs (web scraping, library-docs, crawl4ai, searxng). Dùng khi cần fetch docs, warmup cache, doctor kiểm tra cấu hình — thay vì mở MCP server.
---

# wet — CLI-first web docs fetcher

Wet là CLI/API hạng-1; MCP server là surface phụ: chạy `wet` không subcommand → passthrough vào MCP server (flags như `--http` đi thẳng).

## Lệnh chính
- `wet --help` — xem toàn bộ subcommands
- `wet doctor` — kiểm tra cấu hình/API keys
- `wet auth` / `wet logout` — quản lý Google Drive auth
- `wet config` — cấu hình (SYNC_FOLDER, cache, data dir ~/.wet-mcp legacy)
- `wet docs` — truy vấn library docs đã nén
- `wet warmup` — làm nóng cache
- `wet relay` — relay form cho MCP HTTP mode

## Ghi chú
- Repo + CLI: `wet` (2026-09-13). Package PyPI giữ `wet-mcp` (PyPI chặn project name `wet`); data dir `~/.wet-mcp` giữ nguyên.
- MCP surface: `wet` (bare) — passthrough MCP server; legacy entry `wet-mcp` của bản cũ vẫn chạy.
