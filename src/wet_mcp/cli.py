"""Console-script control plane for wet-mcp (``wet``).

De-host CLI: the MCP server is a long-running HTTP process and this CLI is
its control plane plus one thin consumer:

- ``wet server start|stop|status`` — lifecycle for the detached HTTP server
  (lock files under ``~/.config/mcp/locks``, 4-line pid/port/token/spawned_at
  payload written by the hull ``LifecycleLock``);
- ``wet config …`` / ``wet token hash`` / ``wet users path`` — instance
  config management for ``~/.wet/config.toml``;
- ``wet docs reindex|import|reembed`` — host-side docs-store maintenance;
  these run WITHOUT the server (direct SQLite access);
- ``wet search`` — a CONSUMER: talks to the running server over streamable
  HTTP MCP (initialize → notifications/initialized → tools/call). When the
  server is down it prints the "not running" hint and exits 2 — there is no
  hidden in-process fallback;
- ``wet warmup`` — provider warmup probe (unchanged behavior).

All imports beyond the stdlib are deferred into the handlers so ``wet --help``
and ``wet -V`` stay instant.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

SERVER_NOT_RUNNING = "wet-mcp server is not running — start it with `wet server start`"

# LifecycleLock root: <name>-<port>.lock files, wet server uses name "wet".
LOCKS_DIR = Path.home() / ".config" / "mcp" / "locks"

SERVER_LOG_NAME = "wet-server.log"

_MCP_PROTOCOL_VERSION = "2025-06-18"

_HEADER_RE = re.compile(r"^\[([^\]]+)\]$")
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*=")


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------


def _version() -> str:
    try:
        return f"wet {importlib.metadata.version('wet-mcp')}"
    except importlib.metadata.PackageNotFoundError:
        return "wet (unknown version)"


def _client_version() -> str:
    try:
        return importlib.metadata.version("wet-mcp")
    except importlib.metadata.PackageNotFoundError:
        return "0"


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _data_dir() -> Path:
    from wet_mcp.config import settings

    return settings.get_data_dir()


def _server_log_path() -> Path:
    return _data_dir() / SERVER_LOG_NAME


def _tail(path: Path, count: int) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]
    except OSError:
        return [f"<log file unreadable: {path}>"]


def _pid_alive(pid: int) -> bool:
    """psutil-free liveness check. NOTE: os.kill(pid, 0) is used on POSIX
    only — on Windows os.kill with any signal TerminateProcess's the target,
    so liveness there goes through OpenProcess instead."""
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _parse_lock(path: Path) -> dict | None:
    """Read the 4-line lock payload: pid / port / token / spawned_at."""
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    if len(lines) < 4:
        return None
    try:
        return {
            "pid": int(lines[0].strip()),
            "port": int(lines[1].strip()),
            "token": lines[2].strip(),  # never printed
            "spawned_at": lines[3].strip(),
        }
    except ValueError:
        return None


def _find_locks(port: int | None) -> list[Path]:
    if not LOCKS_DIR.is_dir():
        return []
    if port is not None:
        exact = LOCKS_DIR / f"wet-{port}.lock"
        return [exact] if exact.is_file() else []
    return sorted(LOCKS_DIR.glob("wet-*.lock"))


def _http_probe(port: int) -> bool:
    """GET /mcp — any HTTP response (including 401/4xx/5xx) means up."""
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/mcp", method="GET"
        )
        urllib.request.urlopen(request, timeout=2.0)  # nosec B310 - fixed scheme/host
        return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


# ---------------------------------------------------------------------------
# wet server start / stop / status
# ---------------------------------------------------------------------------


def _spawn_server(host: str, port: int, *, explicit_host: bool, explicit_port: bool):
    """Spawn the detached HTTP server subprocess; returns the Popen."""
    log_path = _server_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # append mode: prior runs' logs stay readable for debugging crashes
    log_fh = open(log_path, "ab")  # nosec SIM115 - child owns the handle
    env = dict(os.environ)
    env.setdefault("MCP_TRANSPORT", "http")
    if explicit_host:
        env["MCP_HOST"] = host
    if explicit_port:
        env["MCP_PORT"] = str(port)
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(  # nosec B603 - fixed argv, no shell
            [sys.executable, "-m", "wet_mcp.server"],
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=log_fh,
            env=env,
            close_fds=True,
            **kwargs,
        )
    finally:
        log_fh.close()  # the child holds its own inherited handle


def _cmd_server_start(args: argparse.Namespace) -> int:
    from wet_mcp.runtime import hull_settings

    hs = hull_settings()
    host = args.host or hs.server.host
    port = args.port or hs.server.port

    if not args.foreground:
        for lock in _find_locks(args.port):
            meta = _parse_lock(lock)
            if meta and _pid_alive(meta["pid"]):
                print(
                    f"wet-mcp server already running: pid={meta['pid']} "
                    f"port={meta['port']} (lock: {lock})",
                    file=sys.stderr,
                )
                return 1

    if args.foreground:
        import wet_mcp.server as server_mod

        entry = getattr(server_mod, "run_server_blocking", None)
        if entry is not None:
            try:
                entry(
                    host=host if args.host else None,
                    port=port if args.port else None,
                )
            except KeyboardInterrupt:
                return 130
            except Exception as exc:  # startup refusal (e.g. no-auth + non-loopback)
                print(f"wet server failed to start: {exc}", file=sys.stderr)
                return 1
            return 0
        # Blocking entry not present: run via the subprocess and wait.
        proc = _spawn_server(
            host, port, explicit_host=args.host is not None,
            explicit_port=args.port is not None,
        )
        try:
            return proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            return 130

    proc = _spawn_server(
        host, port,
        explicit_host=args.host is not None,
        explicit_port=args.port is not None,
    )
    try:
        proc.wait(timeout=2.0)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        rc = None

    if rc is not None:
        # Server-side startup checks raise before the process detaches;
        # surface the log tail instead of reporting a phantom start.
        print(
            f"wet-mcp server exited immediately (exit code {rc}); "
            f"last log lines from {_server_log_path()}:",
            file=sys.stderr,
        )
        for line in _tail(_server_log_path(), 20):
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"wet-mcp server started: pid={proc.pid} port={port}")
    print(f"log: {_server_log_path()}")
    print(f"stop: wet server stop --port {port}")
    return 0


def _terminate(pid: int) -> None:
    """Graceful first pass."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid)], check=False)  # nosec B603 B607
    else:
        os.kill(pid, signal.SIGTERM)


def _force_kill(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(  # nosec B603 B607
            ["taskkill", "/PID", str(pid), "/T", "/F"], check=False
        )
    else:
        os.kill(pid, signal.SIGKILL)


def _cmd_server_stop(args: argparse.Namespace) -> int:
    locks = _find_locks(args.port)
    if not locks:
        print(SERVER_NOT_RUNNING)
        return 0
    ok = True
    for lock in locks:
        meta = _parse_lock(lock)
        if meta is None:
            lock.unlink(missing_ok=True)
            print(f"removed malformed lock file: {lock}")
            continue
        pid, port = meta["pid"], meta["port"]
        if not _pid_alive(pid):
            lock.unlink(missing_ok=True)
            print(f"removed stale lock (pid {pid} not running): {lock}")
            continue
        _terminate(pid)
        deadline = time.monotonic() + 8.0
        while _pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.25)
        if _pid_alive(pid):
            _force_kill(pid)
            time.sleep(0.5)
        if _pid_alive(pid):
            print(
                f"failed to stop wet-mcp server: pid={pid} port={port} still alive",
                file=sys.stderr,
            )
            ok = False
        else:
            lock.unlink(missing_ok=True)
            print(f"stopped wet-mcp server: pid={pid} port={port} (lock removed)")
    return 0 if ok else 1


def _cmd_server_status(args: argparse.Namespace) -> int:
    from wet_mcp.runtime import hull_settings

    locks = _find_locks(args.port)
    if not locks:
        port = args.port or hull_settings().server.port
        up = _http_probe(port)
        print("lock: none")
        print(f"http (port {port}): {'up' if up else 'down'}")
        return 0 if up else 1

    any_up = False
    for lock in locks:
        meta = _parse_lock(lock)
        if meta is None:
            print(f"lock: {lock} (malformed payload)")
            continue
        pid, port = meta["pid"], meta["port"]
        alive = _pid_alive(pid)
        up = _http_probe(port)
        any_up = any_up or alive or up
        print(f"lock: {lock}")
        print(f"pid: {pid} ({'alive' if alive else 'dead'})")
        print(f"port: {port}")
        print(f"http (GET http://127.0.0.1:{port}/mcp): {'up' if up else 'down'}")
    return 0 if any_up else 1


# ---------------------------------------------------------------------------
# wet config / token / users
# ---------------------------------------------------------------------------


def _looks_secret(key: str) -> bool:
    lowered = key.lower()
    if lowered.endswith("_hash"):
        return False  # a scrypt hash is not the token; echoing it is the workflow
    return any(word in lowered for word in ("api_key", "token", "secret", "password"))


def _toml_scalar(raw: str) -> str:
    """Coerce a CLI value into TOML text (quoted string when not TOML)."""
    try:
        parsed = tomllib.loads(f"v = {raw}")
        value = parsed["v"]
    except tomllib.TOMLDecodeError:
        value = raw
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _config_get(path: Path, key: str) -> int:
    if not path.is_file():
        print(f"no config at {path} (run `wet config init`)", file=sys.stderr)
        return 1
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    current: object = data
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            print(f"key not found: {key} (in {path})", file=sys.stderr)
            return 1
    if isinstance(current, bool):
        print("true" if current else "false")
    else:
        print(current)
    return 0


def _config_set(path: Path, key: str, raw_value: str) -> int:
    if not path.is_file():
        print(f"no config at {path} (run `wet config init`)", file=sys.stderr)
        return 1
    parts = key.split(".")
    if len(parts) < 2:
        print(
            f"key must be dotted (<section>.<key>, e.g. server.port or "
            f"models.embed.model): got {key!r}",
            file=sys.stderr,
        )
        return 1
    section, name = ".".join(parts[:-1]), parts[-1]
    value_text = _toml_scalar(raw_value)

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    section_idx: int | None = None
    insert_at: int | None = None
    replaced = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        header = _HEADER_RE.match(stripped)
        if header:
            if section_idx is not None:
                insert_at = i  # next section begins: insert before it
                break
            if header.group(1) == section:
                section_idx = i
            continue
        if section_idx is not None:
            key_match = _KEY_RE.match(stripped)
            if key_match and key_match.group(1) == name:
                lines[i] = f"{name} = {value_text}\n"
                replaced = True
                break
    if section_idx is None:
        print(
            f"section [{section}] not found in {path}; edit the file directly "
            f"to add it (path: `wet config path`, template: `wet config show`)",
            file=sys.stderr,
        )
        return 1
    if not replaced:
        lines.insert(
            insert_at if insert_at is not None else len(lines),
            f"{name} = {value_text}\n",
        )
    path.write_text("".join(lines), encoding="utf-8")
    shown = "*** (value not echoed)" if _looks_secret(key) else value_text
    print(f"set {key} = {shown} in {path}")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    from wet_mcp.runtime import CONFIG_TEMPLATE, wet_config_dir, wet_config_path

    path = wet_config_path()
    action = args.config_action
    if action == "init":
        try:
            from hull_core.config.settings import write_default_config

            written = write_default_config(wet_config_dir(), force=args.force)
        except FileExistsError:
            print(
                f"config already exists: {path} (use --force to overwrite)",
                file=sys.stderr,
            )
            return 1
        print(f"wrote {written}")
        return 0
    if action == "path":
        print(path)
        return 0
    if action == "show":
        print(path.read_text(encoding="utf-8") if path.is_file() else CONFIG_TEMPLATE)
        return 0
    if action == "get":
        return _config_get(path, args.key)
    return _config_set(path, args.key, args.value)


def _cmd_token_hash(args: argparse.Namespace) -> int:
    from hull_core.auth.tokens import hash_token

    print(hash_token(args.token))  # never echo the token itself
    return 0


def _cmd_users_path(args: argparse.Namespace) -> int:
    from wet_mcp.runtime import hull_settings, wet_config_dir

    users_file = hull_settings().server.users_file or (
        wet_config_dir() / "users.toml"
    )
    print(users_file)
    return 0


# ---------------------------------------------------------------------------
# wet docs (host-side maintenance; the server need not be running)
# ---------------------------------------------------------------------------


def _cmd_docs_reindex(args: argparse.Namespace) -> int:
    from wet_mcp.config import settings
    from wet_mcp.db import DocsDB
    from wet_mcp.runtime import DEFAULT_EMBEDDING_DIMS

    dims = settings.embedding_dims or DEFAULT_EMBEDDING_DIMS
    # Identity left empty: the guard then compares dims only, so reindex never
    # trips on a model-string format it did not mint itself.
    db = DocsDB(settings.get_db_path(), embedding_dims=dims, model_identity="")
    try:
        lib = db.get_library(args.library)
        if not lib:
            _emit({"error": f"Library '{args.library}' not found in index"})
            return 1
        ver = db.get_best_version(lib["id"])
        if ver:
            db.clear_version_chunks(ver["id"])
            # A cleared version must stop resolving as servable, or the lazy
            # re-ingest gate never fires.
            db.reset_version_index(ver["id"])
        _emit(
            {
                "status": "cleared",
                "library": args.library,
                "hint": "Next docs search will re-index",
            }
        )
        return 0
    finally:
        db._conn.close()


def _cmd_docs_import(args: argparse.Namespace) -> int:
    from wet_mcp.docs_import import import_docs

    try:
        result = import_docs(
            Path(args.export),
            db_path=Path(args.db) if args.db else None,
            force=args.force,
            expected_chunks=args.expected_chunks,
            skip_fts=args.skip_fts,
        )
    except (RuntimeError, FileNotFoundError, sqlite3.Error) as exc:
        print(f"wet docs import failed: {exc}", file=sys.stderr)
        return 1
    print("docs import complete:")
    print(f"  chunks:     {result['chunks']}")
    print(f"  libraries:  {result['libraries']}")
    print(f"  versions:   {result['versions']}")
    fts = result["fts_rows"]
    print(f"  fts rows:   {fts if fts is not None else '(skipped)'}")
    print(f"  db:         {result['db_path']}")
    print(f"  elapsed:    {result['elapsed_s']}s")
    return 0


def _cmd_docs_reembed(args: argparse.Namespace) -> int:
    import asyncio

    from wet_mcp.docs_reembed import reembed

    try:
        result = asyncio.run(
            reembed(
                db_path=Path(args.db) if args.db else None,
                batch_size=args.batch_size,
                limit=args.limit,
                dry_run=args.dry_run,
            )
        )
    except Exception as exc:  # EmbeddingModelMismatch, provider/transport errors
        print(f"wet docs reembed failed: {exc}", file=sys.stderr)
        return 1
    status = result.get("status")
    if status == "pending":
        print(f"wet docs reembed pending: {result.get('reason')}", file=sys.stderr)
        return 3
    if status == "error":
        print(f"wet docs reembed failed: {result.get('reason')}", file=sys.stderr)
        return 1
    if status == "dry-run":
        print("docs reembed dry-run (no writes):")
    else:
        print("docs reembed complete:")
    print(f"  missing:        {result.get('missing')}")
    print(f"  embedded:       {result.get('embedded')}")
    print(f"  remaining:      {result.get('remaining')}")
    print(f"  identity:       {result.get('model')}")
    print(f"  dims:           {result.get('dims')}")
    print(f"  vectors before: {result.get('vectors_present')}")
    print(f"  chunks total:   {result.get('chunks_total')}")
    print(f"  db:             {result.get('db_path')}")
    return 0


# ---------------------------------------------------------------------------
# wet search (consumer via streamable HTTP MCP)
# ---------------------------------------------------------------------------


def _post_rpc(
    url: str,
    payload: dict,
    session_id: str | None,
    token: str | None,
    timeout: float,
):
    """POST one JSON-RPC message. Returns (status, headers, body, error)."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(  # nosec B310 - fixed scheme, operator URL
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (
                response.status,
                response.headers,
                response.read().decode("utf-8", "replace"),
                None,
            )
    except urllib.error.HTTPError as exc:
        return (
            exc.code,
            exc.headers,
            exc.read().decode("utf-8", "replace"),
            None,
        )
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        return None, None, None, exc


def _extract_rpc_response(body: str, content_type: str, request_id: int) -> dict | None:
    """Pull the JSON-RPC response with ``request_id`` from a JSON or SSE body."""
    if "text/event-stream" in content_type or body.lstrip().startswith(
        ("event:", "data:")
    ):
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                message = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _cmd_search(args: argparse.Namespace) -> int:
    from wet_mcp.runtime import hull_settings

    base = (args.url or f"http://127.0.0.1:{hull_settings().server.port}").rstrip("/")
    url = f"{base}/mcp"
    token = args.token or os.environ.get("WET_TOKEN")

    session_id: str | None = None

    def _rpc(payload: dict, request_id: int | None) -> tuple[dict | None, str | None]:
        """One round-trip. Returns (message, error); error "connection" already
        printed the not-running hint (consumer contract: exit 2)."""
        nonlocal session_id
        status, headers, body, error = _post_rpc(
            url, payload, session_id, token, timeout=30.0
        )
        if error is not None:
            print(SERVER_NOT_RUNNING, file=sys.stderr)
            print(f"  ({error})", file=sys.stderr)
            return None, "connection"
        if request_id is None:
            return None, None
        new_session = headers.get("Mcp-Session-Id") if headers is not None else None
        if new_session:
            session_id = new_session
        content_type = headers.get("Content-Type", "") if headers is not None else ""
        return _extract_rpc_response(body, content_type, request_id), None

    init_response, err = _rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "wet-cli", "version": _client_version()},
            },
        },
        1,
    )
    if err is not None:
        return 2
    if not isinstance(init_response, dict):
        print(f"wet search: unexpected initialize response from {url}", file=sys.stderr)
        return 1
    if "error" in init_response:
        print(f"wet search: initialize failed: {init_response['error']}", file=sys.stderr)
        return 1

    _rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, None)

    call_arguments: dict = {"action": "search", "query": args.query}
    if args.max_results is not None:
        call_arguments["limit"] = args.max_results
    response, err = _rpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "search", "arguments": call_arguments},
        },
        2,
    )
    if err is not None:
        return 2
    if not isinstance(response, dict):
        print(f"wet search: unexpected tools/call response from {url}", file=sys.stderr)
        return 1
    if "error" in response:
        print(f"wet search: {response['error']}", file=sys.stderr)
        return 1
    result = response.get("result") or {}
    texts = [
        item.get("text", "")
        for item in (result.get("content") or [])
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    output = "\n".join(part for part in texts if part)
    if result.get("isError"):
        print(output or "wet search: tool error (no detail returned)", file=sys.stderr)
        return 1
    print(output or "(empty result)")
    return 0


# ---------------------------------------------------------------------------
# wet warmup (ported unchanged)
# ---------------------------------------------------------------------------


def _cmd_warmup(args: argparse.Namespace) -> int:
    import asyncio

    from wet_mcp.setup_tool import run_warmup

    result = asyncio.run(run_warmup())
    _emit(result)
    return 0 if result.get("status") == "ok" else 1


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wet",
        description=(
            "wet-mcp control plane: run and configure the HTTP server, "
            "maintain the docs store, and call the server as a consumer."
        ),
    )
    parser.add_argument(
        "-V", "--version", action="version", version=_version(), help="print version and exit"
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_server = sub.add_parser("server", help="start/stop/status the wet-mcp HTTP server")
    server_sub = p_server.add_subparsers(dest="server_action", required=True)

    p_start = server_sub.add_parser(
        "start", help="start the server as a detached background process"
    )
    p_start.add_argument("--host", default=None, help="bind host (default: [server].host in ~/.wet/config.toml)")
    p_start.add_argument("--port", type=int, default=None, help="bind port (default: [server].port)")
    p_start.add_argument(
        "--foreground",
        action="store_true",
        help="run the server blocking in this process instead of detaching",
    )
    p_start.set_defaults(func=_cmd_server_start)

    p_stop = server_sub.add_parser("stop", help="stop the running server via its lock file")
    p_stop.add_argument("--port", type=int, default=None, help="target a specific wet-<port>.lock")
    p_stop.set_defaults(func=_cmd_server_stop)

    p_status = server_sub.add_parser("status", help="report pid/lock/HTTP liveness")
    p_status.add_argument("--port", type=int, default=None, help="probe a specific port")
    p_status.set_defaults(func=_cmd_server_status)

    p_config = sub.add_parser("config", help="manage ~/.wet/config.toml")
    config_sub = p_config.add_subparsers(dest="config_action", required=True)
    p_config_init = config_sub.add_parser("init", help="write the default config template")
    p_config_init.add_argument("--force", action="store_true", help="overwrite an existing config")
    p_config_init.set_defaults(func=_cmd_config)
    p_config_path = config_sub.add_parser("path", help="print the config file path")
    p_config_path.set_defaults(func=_cmd_config)
    p_config_show = config_sub.add_parser("show", help="print the config file (or the template)")
    p_config_show.set_defaults(func=_cmd_config)
    p_config_get = config_sub.add_parser("get", help="print one value (dotted key, e.g. server.port)")
    p_config_get.add_argument("key")
    p_config_get.set_defaults(func=_cmd_config)
    p_config_set = config_sub.add_parser("set", help="set one value (line-based edit of the file)")
    p_config_set.add_argument("key")
    p_config_set.add_argument("value")
    p_config_set.set_defaults(func=_cmd_config)

    p_token = sub.add_parser("token", help="token helpers")
    token_sub = p_token.add_subparsers(dest="token_action", required=True)
    p_token_hash = token_sub.add_parser("hash", help="print the storable scrypt hash of a token")
    p_token_hash.add_argument("token")
    p_token_hash.set_defaults(func=_cmd_token_hash)

    p_users = sub.add_parser("users", help="user store helpers")
    users_sub = p_users.add_subparsers(dest="users_action", required=True)
    p_users_path = users_sub.add_parser("path", help="print the users.toml path")
    p_users_path.set_defaults(func=_cmd_users_path)

    p_docs = sub.add_parser("docs", help="host-side docs-store maintenance (no server needed)")
    docs_sub = p_docs.add_subparsers(dest="docs_action", required=True)
    p_docs_reindex = docs_sub.add_parser("reindex", help="clear a library's chunks so the next search re-indexes")
    p_docs_reindex.add_argument("library")
    p_docs_reindex.set_defaults(func=_cmd_docs_reindex)
    p_docs_import = docs_sub.add_parser("import", help="import a CF D1 SQL export into the local docs.db")
    p_docs_import.add_argument("export", help="path to the exported .sql file")
    p_docs_import.add_argument("--db", default=None, help="target db (default: ~/.wet/docs.db)")
    p_docs_import.add_argument("--force", action="store_true", help="replace an existing non-empty db")
    p_docs_import.add_argument(
        "--expected-chunks",
        type=int,
        default=49939,
        help="asserted doc_chunks count (default: 49939, the proven receipt number)",
    )
    p_docs_import.add_argument("--skip-fts", action="store_true", help="skip the FTS5 rebuild")
    p_docs_import.set_defaults(func=_cmd_docs_import)
    p_docs_reembed = docs_sub.add_parser("reembed", help="backfill vectors for chunks missing them")
    p_docs_reembed.add_argument("--db", default=None, help="docs db (default: ~/.wet/docs.db)")
    p_docs_reembed.add_argument("--batch-size", type=int, default=64)
    p_docs_reembed.add_argument("--limit", type=int, default=None, help="cap chunks embedded this run")
    p_docs_reembed.add_argument("--dry-run", action="store_true", help="report counts only, no writes")
    p_docs_reembed.set_defaults(func=_cmd_docs_reembed)

    p_search = sub.add_parser("search", help="search via the RUNNING server (streamable HTTP MCP)")
    p_search.add_argument("query")
    p_search.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="passed to the tool as `limit` (server default when omitted)",
    )
    p_search.add_argument("--url", default=None, help="server base URL (default: http://127.0.0.1:<config port>)")
    p_search.add_argument("--token", default=None, help="bearer token (default: WET_TOKEN env; header omitted when unset)")
    p_search.set_defaults(func=_cmd_search)

    p_warmup = sub.add_parser("warmup", help="probe configured providers (unchanged warmup behavior)")
    p_warmup.set_defaults(func=_cmd_warmup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
