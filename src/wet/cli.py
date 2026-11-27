"""Console-script control plane for wet (``wet``).

De-host CLI: the MCP server is a long-running HTTP process and this CLI is
its control plane plus one thin consumer:

- ``wet server start|stop|status`` — lifecycle for the detached HTTP server
  (lock files under ``~/.config/mcp/locks``, 4-line pid/port/token/spawned_at
  payload written by the hull ``LifecycleLock``);
- ``wet config …`` / ``wet token hash`` / ``wet users path`` — instance
  config management for ``~/.wet/config.toml``;
- ``wet docs list|reindex|import|reembed`` — host-side docs-store maintenance;
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
import getpass
import importlib.metadata
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVER_NOT_RUNNING = "wet server is not running — start it with `wet server start`"

# Same refusal as hull-core's own ``token hash``: a token on argv lands in
# shell history, so it is read from stdin or a hidden prompt instead.
_TOKEN_ON_ARGV_REFUSAL = (
    "wet: refusing to read a token from the command line (it would land in "
    "shell history); pipe it on stdin or omit it to be prompted"
)

# LifecycleLock root: <name>-<port>.lock files, wet server uses name "wet".
LOCKS_DIR = Path.home() / ".config" / "mcp" / "locks"

SERVER_LOG_NAME = "wet-server.log"

_MCP_PROTOCOL_VERSION = "2025-06-18"


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------


def _version() -> str:
    for name in ("n24q02m-wet", "wet-mcp", "wet"):
        try:
            return f"wet {importlib.metadata.version(name)}"
        except importlib.metadata.PackageNotFoundError:
            pass
    return "wet (unknown version)"


def _client_version() -> str:
    try:
        return importlib.metadata.version("wet")
    except importlib.metadata.PackageNotFoundError:
        return "0"


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _data_dir() -> Path:
    from wet.config import settings

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


def _resolved_port() -> int:
    """The port the server listens on when the CLI was not given ``--port``.

    ``wet.server`` resolves its bind from ``WET_PORT`` BEFORE the config file
    (container deployments set only the env var), so the CLI has to resolve the
    same way: reading ``[server] port`` alone pointed every CLI command at 8000
    while the server served 8011, and ``wet search`` reported "server is not
    running" against a live server.
    """
    from wet.runtime import hull_settings

    raw = os.environ.get("WET_PORT")
    if raw:
        try:
            return int(raw)
        except ValueError:
            print(
                f"wet: ignoring non-numeric WET_PORT={raw!r}; the server will "
                "refuse to start with it set",
                file=sys.stderr,
            )
    return hull_settings().server.port


def _http_probe(port: int) -> bool:
    """GET /mcp — any HTTP response (including 401/4xx/5xx) means up."""
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", method="GET")
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
    # The child (-m wet.server) reads WET_HOST/WET_PORT (see server.main);
    # MCP_HOST/MCP_PORT were dead names the child never consumed, which made
    # `wet server start --host/--port` silently bind the config port instead.
    if explicit_host:
        env["WET_HOST"] = host
    if explicit_port:
        env["WET_PORT"] = str(port)
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs["start_new_session"] = True
    try:
        return subprocess.Popen(  # nosec B603 - fixed argv, no shell
            [sys.executable, "-m", "wet.server"],
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
    from wet.runtime import hull_settings

    hs = hull_settings()
    host = args.host or hs.server.host
    port = args.port or _resolved_port()

    if not args.foreground:
        # Key the scan to the resolved port (args.port or config): a live lock
        # on a DIFFERENT port must not block, so per-port multi-instance works.
        for lock in _find_locks(port):
            meta = _parse_lock(lock)
            if meta and _pid_alive(meta["pid"]):
                print(
                    f"wet server already running: pid={meta['pid']} "
                    f"port={meta['port']} (lock: {lock})",
                    file=sys.stderr,
                )
                return 1

    if args.foreground:
        import wet.server as server_mod

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
            host,
            port,
            explicit_host=args.host is not None,
            explicit_port=args.port is not None,
        )
        try:
            return proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            return 130

    proc = _spawn_server(
        host,
        port,
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
            f"wet server exited immediately (exit code {rc}); "
            f"last log lines from {_server_log_path()}:",
            file=sys.stderr,
        )
        for line in _tail(_server_log_path(), 20):
            print(f"  {line}", file=sys.stderr)
        return 1

    print(f"wet server started: pid={proc.pid} port={port}")
    print(f"log: {_server_log_path()}")
    print(f"stop: wet server stop --port {port}")
    return 0


def _terminate(pid: int) -> None:
    """Graceful first pass."""
    if os.name == "nt":
        subprocess.run(
            [
                os.path.join(
                    os.environ.get("WINDIR", "C:\\Windows"), "System32", "taskkill.exe"
                ),
                "/PID",
                str(pid),
            ],
            check=False,
        )  # nosec B603 B607
    else:
        os.kill(pid, signal.SIGTERM)


def _force_kill(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(  # nosec B603 B607
            [
                os.path.join(
                    os.environ.get("WINDIR", "C:\\Windows"), "System32", "taskkill.exe"
                ),
                "/PID",
                str(pid),
                "/T",
                "/F",
            ],
            check=False,
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
                f"failed to stop wet server: pid={pid} port={port} still alive",
                file=sys.stderr,
            )
            ok = False
        else:
            lock.unlink(missing_ok=True)
            print(f"stopped wet server: pid={pid} port={port} (lock removed)")
    return 0 if ok else 1


def _cmd_server_status(args: argparse.Namespace) -> int:
    locks = _find_locks(args.port)
    if not locks:
        port = args.port or _resolved_port()
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


def _config_get(path: Path, key: str) -> int:
    """Print one dotted key, masking anything credential-shaped (like hull)."""
    import tomllib

    from hull_core.config.tomledit import (
        ConfigError,
        format_value,
        get_value,
        looks_secret,
    )

    try:
        value = get_value(path, key)
    except (ConfigError, tomllib.TOMLDecodeError) as exc:
        hint = "" if path.is_file() else " (run `wet config init`)"
        print(f"error: {exc}{hint}", file=sys.stderr)
        return 2
    if looks_secret(key):
        print("*** (value not echoed)")
    else:
        print(format_value(value))
    return 0


def _config_set(path: Path, key: str, raw_value: str) -> int:
    """Rewrite exactly one line so the template comments survive."""
    import tomllib

    from hull_core.config.tomledit import (
        ConfigError,
        looks_secret,
        set_value,
        toml_scalar,
    )

    try:
        set_value(path, key, raw_value)
    except (ConfigError, tomllib.TOMLDecodeError) as exc:
        hint = "" if path.is_file() else " (run `wet config init`)"
        print(f"error: {exc}{hint}", file=sys.stderr)
        return 2
    shown = "*** (value not echoed)" if looks_secret(key) else toml_scalar(raw_value)
    print(f"set {key} = {shown} in {path}")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    from wet.runtime import CONFIG_TEMPLATE, wet_config_dir, wet_config_path

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
    if args.token is not None:
        print(_TOKEN_ON_ARGV_REFUSAL, file=sys.stderr)
        return 2
    if sys.stdin.isatty():
        token = getpass.getpass("Token: ")
    else:
        token = sys.stdin.read().strip()
    if not token:
        print("wet: empty token", file=sys.stderr)
        return 1

    from hull_core.auth.tokens import hash_token

    print(hash_token(token))  # never echo the token itself
    return 0


def _cmd_users_path(args: argparse.Namespace) -> int:
    from wet.runtime import hull_settings, wet_config_dir

    users_file = hull_settings().server.users_file or (wet_config_dir() / "users.toml")
    print(users_file)
    return 0


# ---------------------------------------------------------------------------
# wet docs (host-side maintenance; the server need not be running)
# ---------------------------------------------------------------------------


def _cmd_docs_list(args: argparse.Namespace) -> int:
    from wet.config import settings
    from wet.db import DocsDB
    from wet.runtime import DEFAULT_EMBEDDING_DIMS

    dims = settings.embedding_dims or DEFAULT_EMBEDDING_DIMS
    try:
        db = DocsDB(settings.get_db_path(), embedding_dims=dims, model_identity="")
    except (RuntimeError, sqlite3.Error) as exc:
        # EmbeddingModelMismatch (a RuntimeError) lands here: the store was
        # built under a different model, and a traceback would read as a crash
        # rather than the refusal `docs import` already reports.
        print(f"wet docs list failed: {exc}", file=sys.stderr)
        return 1
    try:
        libraries = db.list_libraries()
    finally:
        db.close()
    if not libraries:
        print("no libraries indexed yet — the first docs search indexes one")
        return 0
    for lib in libraries:
        print(f"{lib['name']}  {lib['versions']} version(s)  {lib['chunks']} chunks")
    return 0


def _cmd_docs_reindex(args: argparse.Namespace) -> int:
    from wet.config import settings
    from wet.db import DocsDB
    from wet.runtime import DEFAULT_EMBEDDING_DIMS

    dims = settings.embedding_dims or DEFAULT_EMBEDDING_DIMS
    # Identity left empty: the guard then compares dims only, so reindex never
    # trips on a model-string format it did not mint itself.
    db = DocsDB(settings.get_db_path(), embedding_dims=dims, model_identity="")
    try:
        lib = db.get_library(args.library)
        if not lib:
            _emit(
                {
                    "error": (
                        f"Library '{args.library}' not found in index "
                        f"(run `wet docs list`)"
                    )
                }
            )
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
        db.close()


def _cmd_docs_import(args: argparse.Namespace) -> int:
    from wet.docs_import import import_docs

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

    from wet.docs_reembed import reembed

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
    # Slicing before lstrip prevents allocating a massive copy of the
    # entire body if leading whitespace is present.
    if "text/event-stream" in content_type or body[:2000].lstrip().startswith(
        ("event:", "data:")
    ):
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:") :].strip()
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


def _text_block_is_error(output: str) -> bool:
    """Whether a tool's text block carries an error envelope.

    Belt-and-braces next to ``isError``: a proxy or an older server can drop
    the flag while still returning ``{"error": ...}``, and the exit code is
    what a shell pipeline (``wet search ... && ...``) acts on.
    """
    stripped = output.strip()
    if not stripped.startswith("{"):
        return False
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict) and bool(payload.get("error"))


def _unwrap_tool_result(raw):
    """Extract a JSON dict from FastMCP CallToolResult when calling tools directly."""
    if isinstance(raw, dict):
        return raw
    structured = getattr(raw, "structured_content", None)
    if not isinstance(structured, dict):
        structured = getattr(raw, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    content = getattr(raw, "content", None)
    if content:
        text = getattr(content[0], "text", None)
        if isinstance(text, str):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                if start != -1:
                    try:
                        parsed, _ = json.JSONDecoder().raw_decode(text, start)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        pass
                return {"text": text}
    return raw


def _run_in_process(call_factory):
    """Execute an in-process async server tool inside the server lifespan."""
    import asyncio

    async def _runner():
        from wet.server import _lifespan, mcp

        async with _lifespan(mcp):
            return await call_factory()

    return _unwrap_tool_result(asyncio.run(_runner()))


def _cmd_mcp(args: argparse.Namespace) -> int:
    from wet.server import run_server_blocking, run_stdio

    if args.http:
        run_server_blocking(host=args.host, port=args.port)
    else:
        run_stdio()
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    from wet.server import extract

    action = args.action
    if action in ("extract", "crawl", "map") and not args.urls:
        _emit({"error": f"Error: urls is required for --action {action}."})
        return 1

    extra_kwargs: dict[str, object] = {}
    if action == "monitor":
        extra_kwargs["monitor_op"] = getattr(args, "monitor_op", "list")
        extra_kwargs["interval_seconds"] = getattr(args, "interval_seconds", 3600)
        if args.urls:
            extra_kwargs["url"] = args.urls[0]
    elif action in ("agent", "research"):
        extra_kwargs["job_op"] = getattr(args, "job_op", None)
        extra_kwargs["job_id"] = getattr(args, "job_id", None)

    result = _run_in_process(
        lambda: extract(
            action="agent" if action == "research" else action,
            urls=args.urls or None,
            depth=args.depth,
            max_pages=args.max_pages,
            format=args.format,
            query=args.query,
            **extra_kwargs,
        )
    )
    _emit(result)
    return 1 if isinstance(result, dict) and result.get("error") else 0


def _cmd_docs_status(args: argparse.Namespace) -> int:
    from wet.server import search

    result = _run_in_process(lambda: search(action="docs_status"))
    _emit(result)
    return 1 if isinstance(result, dict) and result.get("error") else 0


def _cmd_docs_audit(args: argparse.Namespace) -> int:
    from wet.server import search

    project_path = args.project_path or "."
    result = _run_in_process(
        lambda: search(action="docs_audit", project_path=project_path)
    )
    _emit(result)
    return 1 if isinstance(result, dict) and result.get("error") else 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from wet.doctor import run_doctor

    report = run_doctor()
    if getattr(args, "json", False):
        _emit(report)
    else:
        print(
            f"wet doctor: {report['status'].upper()} "
            f"({report['total_checks']} checks, "
            f"{report['failures']} fail, {report['warnings']} warn)"
        )
        for check in report["checks"]:
            tag = check["status"].upper()
            print(f"  [{tag}] {check['name']}: {check['detail']}")
            if check.get("hint"):
                print(f"         hint: {check['hint']}")
    return 1 if report["status"] == "fail" else 0


def _cmd_docs_search(args: argparse.Namespace) -> int:
    from wet.server import search

    result = _run_in_process(
        lambda: search(
            action="docs",
            library=args.library,
            query=args.query,
            version=args.version,
            limit=args.limit,
        )
    )
    _emit(result)
    return 1 if isinstance(result, dict) and result.get("error") else 0


def _cmd_search(args: argparse.Namespace) -> int:
    if args.query in ("docs-status", "docs_status"):
        return _cmd_docs_status(args)
    if args.query in ("docs-audit", "docs_audit"):
        return _cmd_docs_audit(args)

    if getattr(args, "local", False):
        from wet.server import search

        limit = args.max_results if args.max_results is not None else 10
        result = _run_in_process(
            lambda: search(action="search", query=args.query, limit=limit)
        )
        _emit(result)
        return 1 if isinstance(result, dict) and result.get("error") else 0

    base = (args.url or f"http://127.0.0.1:{_resolved_port()}").rstrip("/")
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
        print(
            f"wet search: initialize failed: {init_response['error']}", file=sys.stderr
        )
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
    if result.get("isError") or _text_block_is_error(output):
        print(output or "wet search: tool error (no detail returned)", file=sys.stderr)
        return 1
    print(output or "(empty result)")
    return 0


# ---------------------------------------------------------------------------
# wet warmup (ported unchanged)
# ---------------------------------------------------------------------------


def _cmd_warmup(args: argparse.Namespace) -> int:
    import asyncio

    from wet.setup_tool import run_warmup

    result = asyncio.run(run_warmup())
    _emit(result)
    return 0 if result.get("status") == "ok" else 1


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    profile_parent = argparse.ArgumentParser(add_help=False)
    profile_parent.add_argument(
        "--profile",
        default=argparse.SUPPRESS,
        help="profile name (overrides WET_PROFILE)",
    )

    parser = argparse.ArgumentParser(
        prog="wet",
        parents=[profile_parent],
        description=(
            "wet control plane: run and configure the MCP server, "
            "maintain the docs store, and call wet tools."
        ),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=_version(),
        help="print version and exit",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p_mcp = sub.add_parser(
        "mcp",
        parents=[profile_parent],
        help="start MCP server (stdio by default, --http for Streamable HTTP)",
    )
    p_mcp.add_argument(
        "--http",
        action="store_true",
        help="run Streamable HTTP transport instead of stdio",
    )
    p_mcp.add_argument(
        "--host",
        default=None,
        help="bind host when --http is set (default: [server].host in config.toml)",
    )
    p_mcp.add_argument(
        "--port",
        type=int,
        default=None,
        help="bind port when --http is set (default: [server].port)",
    )
    p_mcp.set_defaults(func=_cmd_mcp)

    p_server = sub.add_parser(
        "server",
        parents=[profile_parent],
        help="start/stop/status the wet HTTP server",
    )
    server_sub = p_server.add_subparsers(dest="server_action", required=True)

    p_start = server_sub.add_parser(
        "start",
        parents=[profile_parent],
        help="start the server as a detached background process",
    )
    p_start.add_argument(
        "--host",
        default=None,
        help="bind host (default: [server].host in ~/.wet/config.toml)",
    )
    p_start.add_argument(
        "--port", type=int, default=None, help="bind port (default: [server].port)"
    )
    p_start.add_argument(
        "--foreground",
        action="store_true",
        help="run the server blocking in this process instead of detaching",
    )
    p_start.set_defaults(func=_cmd_server_start)

    p_stop = server_sub.add_parser(
        "stop",
        parents=[profile_parent],
        help="stop the running server via its lock file",
    )
    p_stop.add_argument(
        "--port", type=int, default=None, help="target a specific wet-<port>.lock"
    )
    p_stop.set_defaults(func=_cmd_server_stop)

    p_status = server_sub.add_parser(
        "status", parents=[profile_parent], help="report pid/lock/HTTP liveness"
    )
    p_status.add_argument(
        "--port", type=int, default=None, help="probe a specific port"
    )
    p_status.set_defaults(func=_cmd_server_status)

    p_config = sub.add_parser(
        "config", parents=[profile_parent], help="manage config.toml"
    )
    config_sub = p_config.add_subparsers(dest="config_action", required=True)
    p_config_init = config_sub.add_parser(
        "init", parents=[profile_parent], help="write the default config template"
    )
    p_config_init.add_argument(
        "--force", action="store_true", help="overwrite an existing config"
    )
    p_config_init.set_defaults(func=_cmd_config)
    p_config_path = config_sub.add_parser(
        "path", parents=[profile_parent], help="print the config file path"
    )
    p_config_path.set_defaults(func=_cmd_config)
    p_config_show = config_sub.add_parser(
        "show", parents=[profile_parent], help="print the config file (or the template)"
    )
    p_config_show.set_defaults(func=_cmd_config)
    p_config_get = config_sub.add_parser(
        "get",
        parents=[profile_parent],
        help="print one value (dotted key, e.g. server.port)",
    )
    p_config_get.add_argument("key")
    p_config_get.set_defaults(func=_cmd_config)
    p_config_set = config_sub.add_parser(
        "set",
        parents=[profile_parent],
        help="set one value (line-based edit of the file)",
    )
    p_config_set.add_argument("key")
    p_config_set.add_argument("value")
    p_config_set.set_defaults(func=_cmd_config)

    p_token = sub.add_parser("token", parents=[profile_parent], help="token helpers")
    token_sub = p_token.add_subparsers(dest="token_action", required=True)
    p_token_hash = token_sub.add_parser(
        "hash",
        parents=[profile_parent],
        help="print the storable scrypt hash of a token read from stdin "
        "or a hidden prompt",
    )
    # Declared only so an argv token reaches the refusal in _cmd_token_hash
    # instead of argparse's "unrecognized arguments"; the safe input paths
    # are stdin and the hidden prompt.
    p_token_hash.add_argument("token", nargs="?", default=None, help=argparse.SUPPRESS)
    p_token_hash.set_defaults(func=_cmd_token_hash)

    p_users = sub.add_parser(
        "users", parents=[profile_parent], help="user store helpers"
    )
    users_sub = p_users.add_subparsers(dest="users_action", required=True)
    p_users_path = users_sub.add_parser(
        "path", parents=[profile_parent], help="print the users.toml path"
    )
    p_users_path.set_defaults(func=_cmd_users_path)

    p_docs = sub.add_parser(
        "docs",
        parents=[profile_parent],
        help="host-side docs-store maintenance (no server needed)",
    )
    docs_sub = p_docs.add_subparsers(dest="docs_action", required=True)
    p_docs_list = docs_sub.add_parser(
        "list",
        parents=[profile_parent],
        help="print the indexed library names that reindex accepts",
    )
    p_docs_list.set_defaults(func=_cmd_docs_list)
    p_docs_reindex = docs_sub.add_parser(
        "reindex",
        parents=[profile_parent],
        help="clear a library's chunks so the next search re-indexes",
    )
    p_docs_reindex.add_argument("library")
    p_docs_reindex.set_defaults(func=_cmd_docs_reindex)
    p_docs_import = docs_sub.add_parser(
        "import",
        parents=[profile_parent],
        help="import a CF D1 SQL export into the local docs.db",
    )
    p_docs_import.add_argument("export", help="path to the exported .sql file")
    p_docs_import.add_argument(
        "--db", default=None, help="target db (default: ~/.wet/docs.db)"
    )
    p_docs_import.add_argument(
        "--force", action="store_true", help="replace an existing non-empty db"
    )
    p_docs_import.add_argument(
        "--expected-chunks",
        type=int,
        default=49939,
        help="asserted doc_chunks count (default: 49939, the proven receipt number)",
    )
    p_docs_import.add_argument(
        "--skip-fts", action="store_true", help="skip the FTS5 rebuild"
    )
    p_docs_import.set_defaults(func=_cmd_docs_import)
    p_docs_reembed = docs_sub.add_parser(
        "reembed",
        parents=[profile_parent],
        help="backfill vectors for chunks missing them",
    )
    p_docs_reembed.add_argument(
        "--db", default=None, help="docs db (default: ~/.wet/docs.db)"
    )
    p_docs_reembed.add_argument("--batch-size", type=int, default=64)
    p_docs_reembed.add_argument(
        "--limit", type=int, default=None, help="cap chunks embedded this run"
    )
    p_docs_reembed.add_argument(
        "--dry-run", action="store_true", help="report counts only, no writes"
    )
    p_docs_reembed.set_defaults(func=_cmd_docs_reembed)
    p_docs_search = docs_sub.add_parser(
        "search",
        parents=[profile_parent],
        help="search indexed library documentation locally",
    )
    p_docs_search.add_argument("library", help="library name")
    p_docs_search.add_argument("query", help="documentation search query")
    p_docs_search.add_argument("--version", default=None, help="target library version")
    p_docs_search.add_argument("--limit", type=int, default=10, help="max results")
    p_docs_search.set_defaults(func=_cmd_docs_search)
    p_docs_status = docs_sub.add_parser(
        "status",
        parents=[profile_parent],
        help="show local docs index library/version/chunk summary",
    )
    p_docs_status.set_defaults(func=_cmd_docs_status)
    p_docs_audit = docs_sub.add_parser(
        "audit",
        parents=[profile_parent],
        help="audit project manifests/lockfiles against local docs index",
    )
    p_docs_audit.add_argument(
        "project_path", nargs="?", default=".", help="project root directory"
    )
    p_docs_audit.set_defaults(func=_cmd_docs_audit)

    p_search = sub.add_parser(
        "search",
        parents=[profile_parent],
        help="search via the RUNNING server (or in-process with --local)",
    )
    p_search.add_argument("query")
    p_search.add_argument(
        "--project-path",
        default=".",
        help="project root for `wet search docs-audit`",
    )
    p_search.add_argument(
        "--local",
        action="store_true",
        help="execute search in-process instead of calling the HTTP server",
    )
    p_search.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="passed to the tool as `limit` (server default when omitted)",
    )
    p_search.add_argument(
        "--url",
        default=None,
        help="server base URL (default: http://127.0.0.1:<config port>)",
    )
    p_search.add_argument(
        "--token",
        default=None,
        help="bearer token (default: WET_TOKEN env; header omitted when unset)",
    )
    p_search.set_defaults(func=_cmd_search)

    p_extract = sub.add_parser(
        "extract",
        parents=[profile_parent],
        help="extract/crawl/map/research URLs in-process",
    )
    p_extract.add_argument("urls", nargs="*", help="zero or more target URLs")
    p_extract.add_argument(
        "--action",
        choices=["extract", "crawl", "map", "research", "agent", "monitor"],
        default="extract",
        help="extract action mode",
    )
    p_extract.add_argument(
        "--format",
        choices=["markdown", "text", "json"],
        default="markdown",
        help="output format",
    )
    p_extract.add_argument("--depth", type=int, default=2, help="crawl depth")
    p_extract.add_argument("--max-pages", type=int, default=20, help="max crawl pages")
    p_extract.add_argument(
        "--query", default=None, help="research query (for --action research/agent)"
    )
    p_extract.add_argument(
        "--monitor-op",
        default="list",
        choices=["watch", "list", "unwatch", "check"],
        help="monitor operation (for --action monitor)",
    )
    p_extract.add_argument(
        "--interval-seconds",
        type=int,
        default=3600,
        help="monitor polling hint in seconds",
    )
    p_extract.add_argument(
        "--job-op",
        default=None,
        choices=["start", "status", "resume", "cancel"],
        help="async research job operation (for --action agent)",
    )
    p_extract.add_argument("--job-id", default=None, help="async job ID")
    p_extract.set_defaults(func=_cmd_extract)

    p_doctor = sub.add_parser(
        "doctor",
        parents=[profile_parent],
        help="run 12-point wet diagnostics and configuration audit",
    )
    p_doctor.add_argument(
        "--json", action="store_true", help="emit structured JSON diagnostics"
    )
    p_doctor.set_defaults(func=_cmd_doctor)

    p_warmup = sub.add_parser(
        "warmup",
        parents=[profile_parent],
        help="probe configured providers (unchanged warmup behavior)",
    )
    p_warmup.set_defaults(func=_cmd_warmup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    profile = getattr(args, "profile", None)
    if profile is not None:
        from hull_core.storage import validate_profile

        from wet.runtime import reset_settings_cache

        os.environ["WET_PROFILE"] = validate_profile(profile)
        reset_settings_cache()
    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
