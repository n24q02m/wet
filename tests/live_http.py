"""Spawn the real wet HTTP MCP server for live tests.

De-host: wet has no stdio mode — ``python -m wet.server`` binds the HTTP MCP
endpoint at ``http://host:port/mcp`` (auth per ``~/.wet/config.toml``;
``no-auth`` on loopback is the default). These helpers spawn that server in a
subprocess on an ephemeral loopback port and hand out MCP ``ClientSession``s
over the streamable-HTTP transport. Everything stays on loopback with a tmp
instance home -- no network, no credentials.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

# The exact de-hosted tool registry (mirrors tests/test_tool_names.py).
EXPECTED_WET_TOOLS = [
    "config",
    "extract",
    "help",
    "media",
    "search",
]


def free_port() -> int:
    """Reserve an ephemeral loopback port for the spawned server."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wet_server_env(tmp_path: Path, *, searxng_url: str | None = None) -> dict:
    """Env for a real local-only server process: tmp instance home, no cells."""
    local_state = tmp_path / "local-state"
    local_state.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "LOG_LEVEL": "WARNING",
        # Windows Path.home() reads USERPROFILE; POSIX reads HOME.
        "HOME": str(local_state),
        "USERPROFILE": str(local_state),
        "XDG_CONFIG_HOME": str(local_state),
        "LOCALAPPDATA": str(local_state),
        "APPDATA": str(local_state),
        "CACHE_DIR": str(tmp_path),
        "DOCS_DB_PATH": str(tmp_path / "docs.db"),
        "EMBEDDING_DIMS": "0",
        "RERANK_ENABLED": "true",
        "DISABLE_LOCAL_EMBED": "false",
        "DISABLE_LOCAL_RERANK": "false",
        "WET_AUTO_SEARXNG": "false",
        # De-host: model cells live in config.toml, which the tmp home lacks —
        # no cloud cell is configured, so the server runs the local ONNX legs.
        "WET_HOST": "127.0.0.1",
        "WET_PORT": str(free_port()),
    }
    if searxng_url:
        env["SEARCH_BACKENDS"] = "searxng"
        env["SEARXNG_URL"] = searxng_url
    return env


def spawn_wet_server(env: dict, log_path: Path) -> subprocess.Popen[bytes]:
    """Start ``python -m wet.server``; the caller owns termination."""
    log_fh = open(log_path, "ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "wet.server"],
        env=env,
        stdout=log_fh,
        stderr=log_fh,
        close_fds=True,
    )
    log_fh.close()  # the child owns its inherited handle
    return proc


def _log_tail(log_path: Path, chars: int = 2000) -> str:
    try:
        return log_path.read_text(errors="replace")[-chars:]
    except OSError:
        return "<no log>"


def wait_until_up(
    proc: subprocess.Popen[bytes], port: int, log_path: Path, timeout: float = 60.0
) -> None:
    """Block until the spawned server answers HTTP (or die with its log)."""
    url = f"http://127.0.0.1:{port}/mcp"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"wet server exited with {proc.returncode} before accepting "
                f"connections; log {log_path}:\n{_log_tail(log_path)}"
            )
        try:
            # Any HTTP response (incl. 4xx from the auth layer or the
            # streamable endpoint) means the listener is serving requests.
            httpx.get(url, timeout=2.0)
            return
        except httpx.HTTPError:
            time.sleep(0.25)
    raise RuntimeError(
        f"wet server on port {port} never came up; log {log_path}:\n"
        f"{_log_tail(log_path)}"
    )


@asynccontextmanager
async def mcp_client_session(
    port: int, *, timeout: float = 120.0
) -> AsyncIterator[ClientSession]:
    """Yield an initialized MCP ``ClientSession`` over streamable HTTP."""
    url = f"http://127.0.0.1:{port}/mcp"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session


@asynccontextmanager
async def wet_http_server(env: dict, log_path: Path) -> AsyncIterator[int]:
    """Spawn the server, wait for readiness, yield its port, then stop it."""
    proc = spawn_wet_server(env, log_path)
    port = int(env["WET_PORT"])
    try:
        wait_until_up(proc, port, log_path)
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
