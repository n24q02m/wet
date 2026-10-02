"""Protocol gate that runs in the DEFAULT CI suite (no marker, HTTP transport).

De-host: there is ONE transport — the HTTP server (``python -m wet_mcp.server``,
bind from WET_HOST/WET_PORT). Unlike ``test_live_protocol.py`` (marker-gated),
this gate runs against the SOURCE TREE over that production HTTP transport in
every default ``pytest`` run: ``list_tools``, per-tool dispatch, one real
representative domain round-trip and one bounded concurrency case.

Scope honesty (mcp-dev/references/protocol-test-coverage.md):
- This is PRE-BETA hardening of the source tree. The authoritative D3 gate runs
  against the INSTALLED BETA artifact (``uvx --from wet-mcp==<beta>``) with the
  headless creds/searxng wiring the reference requires, and is blocked until
  PyPI trusted publishing exists. This file does NOT claim D3 is satisfied.
- A real ``search`` is deliberately NOT asserted here: it needs a searxng
  backend (or network), and the repo's real-network tests stay marker-gated on
  purpose. ``search`` below is checked as DISPATCH ONLY (missing-argument
  validation error) — do not read a green run as "search verified".
- The representative DOMAIN op is ``extract`` ``action=convert`` on a real
  local file (Rule 1): the converted output is asserted, not just config/help.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from test_tool_names import EXPECTED_NAMES

pytestmark = [pytest.mark.timeout(120)]


# ---------------------------------------------------------------------------
# Helpers (mirrored from tests/test_live_protocol.py)
# ---------------------------------------------------------------------------


def parse(r) -> str:
    """Extract text from MCP tool result."""
    if hasattr(r, "isError") and r.isError:
        raise RuntimeError(r.content[0].text)
    return r.content[0].text


def parse_allow_error(r) -> str:
    """Extract text from MCP tool result, including error responses."""
    return r.content[0].text


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _server_env(tmp_path: Path, searxng_url: str) -> tuple[dict, Path]:
    """Env for a real local-only server process: tmp instance home, no cells."""
    local_state = tmp_path / "local-state"
    local_state.mkdir(parents=True, exist_ok=True)
    port = _free_port()
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
        # Hermetic gate: the local ONNX legs would try a ~570 MB HF download
        # per spawn (slow retry ladder, network). Disable both so startup
        # degrades to keyword-only exactly like a slim deployment.
        "RERANK_ENABLED": "false",
        "DISABLE_LOCAL_EMBED": "true",
        "DISABLE_LOCAL_RERANK": "true",
        "SEARCH_BACKENDS": "searxng",
        "SEARXNG_URL": searxng_url,
        "WET_AUTO_SEARXNG": "false",
        # De-host: model cells live in config.toml, which the tmp home lacks —
        # no cloud cell is configured, so both legs stay disabled (above).
        "WET_HOST": "127.0.0.1",
        "WET_PORT": str(port),
    }
    return env, local_state


class _SearxngHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path.startswith("/healthz"):
            payload_data: dict = {"status": "ok"}
        elif self.path.startswith("/search"):
            payload_data = {
                "results": [
                    {
                        "url": f"https://example.com/python-testing-{index}",
                        "title": f"Python testing result {index}",
                        "content": (
                            "Deterministic Python testing guidance for the "
                            f"protocol gate fixture {index}."
                        ),
                        "engine": "fixture",
                    }
                    for index in range(12)
                ]
            }
        else:
            self.send_error(404)
            return

        body = json.dumps(payload_data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def searxng_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SearxngHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host = server.server_address[0]
        port = server.server_address[1]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _wait_until_up(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/mcp", timeout=2.0)
            return  # any HTTP response (incl. 4xx) means the listener is up
        except httpx.HTTPError:
            time.sleep(0.25)
    raise RuntimeError(f"wet-mcp server on port {port} never came up")


@pytest.fixture
async def mcp_session(searxng_server: str, tmp_path):
    """Start a real local-only wet-mcp HTTP server; yield an MCP session."""
    env, _state = _server_env(tmp_path, searxng_server)
    port = int(env["WET_PORT"])
    log_path = tmp_path / "server.log"
    with open(log_path, "ab") as log_fh:
        proc = subprocess.Popen(
            [sys.executable, "-m", "wet_mcp.server"],
            env=env,
            stdout=log_fh,
            stderr=log_fh,
        )
    try:
        _wait_until_up(port)
        url = f"http://127.0.0.1:{port}/mcp"
        async with streamablehttp_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
    except (RuntimeError, ExceptionGroup) as exc:
        msg = str(exc).lower()
        if "cancel scope" in msg or "different task" in msg:
            warnings.warn(
                f"Suppressed teardown error: {exc}",
                RuntimeWarning,
                stacklevel=1,
            )
        else:
            raise
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---------------------------------------------------------------------------
# Tool contract (over HTTP, single-sourced from the protocol contract)
# ---------------------------------------------------------------------------


class TestToolContract:
    async def test_list_tools_matches_protocol_contract(
        self, mcp_session: ClientSession
    ):
        # EXPECTED_NAMES is THE protocol contract (test_tool_names.py), so a
        # server-side rename fails both the in-process check and this
        # over-the-wire check from one edit.
        result = await mcp_session.list_tools()
        tool_names = sorted(t.name for t in result.tools)
        assert tool_names == EXPECTED_NAMES, (
            f"Expected {EXPECTED_NAMES}, got {tool_names}"
        )


# ---------------------------------------------------------------------------
# Help tool (offline)
# ---------------------------------------------------------------------------


class TestHelp:
    async def test_help_returns_full_docs(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool("help", {"tool_name": "search"})
        text = parse(r)
        assert len(text) >= 100, f"Help too short: {len(text)} chars"


# ---------------------------------------------------------------------------
# Config tool (offline)
# ---------------------------------------------------------------------------


class TestConfig:
    async def test_config_status(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool("config", {"action": "status"})
        text = parse(r)
        data = json.loads(text)
        assert "database" in data and "embedding" in data, (
            f"Missing expected keys: {list(data.keys())}"
        )
        embedding = data["embedding"]
        assert isinstance(embedding, dict)
        assert {
            "backend",
            "model",
            "dims",
            "available",
            "unavailable_reason",
        } <= embedding.keys()
        assert isinstance(embedding["backend"], (str, type(None)))
        assert isinstance(embedding["model"], (str, type(None)))
        assert isinstance(embedding["dims"], int)
        assert embedding["dims"] >= 0
        assert isinstance(embedding["available"], bool)
        if embedding["available"]:
            assert isinstance(embedding["model"], str) and embedding["model"]
            assert embedding["dims"] > 0
            assert embedding["unavailable_reason"] is None
        else:
            assert isinstance(embedding["unavailable_reason"], str)
            assert embedding["unavailable_reason"]

        reranker = data["reranker"]
        assert isinstance(reranker, dict)
        assert {"backend", "model", "available"} <= reranker.keys()
        assert isinstance(reranker["backend"], (str, type(None)))
        assert isinstance(reranker["model"], (str, type(None)))
        assert isinstance(reranker["available"], bool)

    async def test_config_set_log_level(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "config", {"action": "set", "key": "log_level", "value": "DEBUG"}
        )
        text = parse(r)
        assert any(w in text.lower() for w in ("updated", "set")), text[:80]


# ---------------------------------------------------------------------------
# Dispatch checks (offline) -- NOT domain coverage
# ---------------------------------------------------------------------------


class TestDispatch:
    """Prove each domain tool dispatches and validates args WITHOUT network.

    A missing-argument validation error proves the request reached the tool
    and came back through the session. It does NOT exercise the tool's real
    operation (see the module docstring and TestDomainRoundTrip).
    """

    async def test_search_missing_query_is_dispatch_error(
        self, mcp_session: ClientSession
    ):
        # Dispatch only: a real web search needs a searxng backend/network.
        r = await mcp_session.call_tool("search", {"action": "search"})
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("error", "query", "required")), (
            f"Expected error, got: {text[:80]}"
        )

    async def test_extract_missing_urls_is_dispatch_error(
        self, mcp_session: ClientSession
    ):
        r = await mcp_session.call_tool("extract", {"action": "extract"})
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("error", "url", "required")), (
            f"Expected error, got: {text[:80]}"
        )

    async def test_media_missing_url_is_dispatch_error(
        self, mcp_session: ClientSession
    ):
        r = await mcp_session.call_tool("media", {"action": "list"})
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("error", "url", "required")), (
            f"Expected error, got: {text[:80]}"
        )


# ---------------------------------------------------------------------------
# Representative domain round-trip (Rule 1, offline-safe)
# ---------------------------------------------------------------------------


class TestDomainRoundTrip:
    async def test_extract_convert_real_local_file(
        self, mcp_session: ClientSession, tmp_path
    ):
        """extract.convert -- convert a real local file and assert the output.

        This is the gate's representative domain operation: a real round-trip
        through the production HTTP transport whose converted result is
        asserted (not just a config/help/status handshake).
        """
        marker = "PROTOCOL-GATE-CONVERT-MARKER-7c4f"
        test_file = tmp_path / "protocol_gate.txt"
        test_file.write_text(
            f"{marker} wet converts this file to Markdown.", encoding="utf-8"
        )
        r = await mcp_session.call_tool(
            "extract",
            {"action": "convert", "paths": [str(test_file)]},
        )
        text = parse_allow_error(r)
        assert marker in text, f"Converted output missing the marker: {text[:160]}"


# ---------------------------------------------------------------------------
# Concurrency (bounded, offline-safe)
# ---------------------------------------------------------------------------


class TestConcurrency:
    async def test_concurrent_calls_share_one_session(
        self, mcp_session: ClientSession, tmp_path
    ):
        """Several tool calls on ONE session resolve via asyncio.gather."""

        async def convert(index: int) -> str:
            path = tmp_path / f"concurrent_{index}.txt"
            path.write_text(f"CONCURRENT-MARKER-{index}", encoding="utf-8")
            r = await mcp_session.call_tool(
                "extract",
                {"action": "convert", "paths": [str(path)]},
            )
            return parse_allow_error(r)

        status_call = mcp_session.call_tool("config", {"action": "status"})
        results = await asyncio.gather(convert(1), convert(2), convert(3), status_call)
        for index in (1, 2, 3):
            assert f"CONCURRENT-MARKER-{index}" in results[index - 1], (
                f"Convert {index} result wrong: {results[index - 1][:120]}"
            )
        data = json.loads(parse_allow_error(results[3]))
        assert "database" in data, f"Status payload unexpected: {list(data.keys())}"
