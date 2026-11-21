---
name: wet
description: "Vận hành wet — MCP server HTTP-only (Streamable HTTP) qua CLI control plane `wet`: start/stop/status server, fetch docs web & library docs (web scraping, library-docs, crawl4ai, searxng), warmup cache. Không có stdio mode, không có auth/logout."
---

# wet — HTTP MCP server + control-plane CLI

wet là MCP server HTTP-only: `wet server start` phục vụ Streamable HTTP tại
`http://127.0.0.1:8000/mcp`. CLI `wet` là control plane cộng một consumer mỏng. Chạy `wet`
không subcommand chỉ in usage (rc 0) — không có passthrough stdio, không có `--http`, và
client không tự spawn wet như subprocess.

## Lệnh chính
- `wet --help` — xem toàn bộ subcommands; `wet -V` — in phiên bản
- `wet server start|stop|status` — vòng đời server HTTP (`start`: detached, `--foreground` để giữ tiến trình; `status`: pid/lock/HTTP liveness)
- `wet config init|path|show|get|set` — cấu hình `~/.wet/config.toml` (`get`/`set` dùng key dạng `server.port`)
- `printf '%s' "$TOKEN" | wet token hash` — đọc token từ stdin (hoặc prompt ẩn khi chạy trên terminal; token đưa qua argv bị từ chối vì sẽ nằm trong shell history) rồi in scrypt hash để dán vào `[server] token_hash` (mode `token`) hoặc `token_hash` của user trong `users.toml` (mode `multi`)
- `wet users path` — in đường dẫn `users.toml`
- `wet docs list|reindex|import|reembed` — bảo trì docs store, chạy trực tiếp trên SQLite (không cần server)
- `wet search "<query>"` — gọi server đang chạy qua MCP; server down thì in hint và exit 2
- `wet warmup` — auto-setup (browser lần đầu; SearXNG chỉ khi bật `WET_AUTO_SEARXNG`), rồi kiểm tra cell model cloud hoặc pre-download model local để tránh chậm lần đầu

## Ghi chú
- Repo + CLI: `wet`; distribution PyPI là `n24q02m-wet` (`uvx --python 3.13 --from n24q02m-wet wet …`). Console scripts: `n24q02m-wet`, `wet`, `wet-mcp` (legacy alias) — cả ba chạy cùng một CLI.
- Data/config dir: `~/.wet` (`config.toml`, `docs.db`, cache).
- Lệnh auth/logout/doctor không tồn tại trong CLI: kiểm tra sức khoẻ server bằng `wet server status`, kiểm tra provider bằng `wet warmup`. Google Drive sync thuộc về better-drive, không thuộc wet.
