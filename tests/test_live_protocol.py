"""Pytest-based live MCP protocol tests for wet-mcp (HTTP transport).

De-host: there is ONE transport — the HTTP server (``python -m wet_mcp.server``,
bind from WET_HOST/WET_PORT, auth per ``~/.wet/config.toml``). The fixture
below spawns that real server against a tmp instance home + a stub SearXNG and
exercises all tools through the streamable-HTTP MCP protocol. Offline tests run
without network; network-dependent tests use the ``network`` marker.

Usage:
    uv run pytest tests/test_live_protocol.py -v --tb=short -m live
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from structured import payload

pytestmark = [pytest.mark.live, pytest.mark.timeout(120)]


# ---------------------------------------------------------------------------
# Helpers
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
        "RERANK_ENABLED": "true",
        "DISABLE_LOCAL_EMBED": "false",
        "DISABLE_LOCAL_RERANK": "false",
        "SEARCH_BACKENDS": "searxng",
        "SEARXNG_URL": searxng_url,
        "WET_AUTO_SEARXNG": "false",
        # De-host: model cells live in config.toml, which the tmp home lacks —
        # no cloud cell is configured, so the server runs the local ONNX legs.
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
                            f"foundation live protocol fixture {index}."
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
# Meta
# ---------------------------------------------------------------------------


class TestMeta:
    async def test_list_tools(self, mcp_session: ClientSession):
        result = await mcp_session.list_tools()
        tool_names = sorted(t.name for t in result.tools)
        expected = [
            "config",
            "extract",
            "help",
            "media",
            "search",
        ]
        assert tool_names == expected, f"Expected {expected}, got {tool_names}"


# ---------------------------------------------------------------------------
# Help tool (offline)
# ---------------------------------------------------------------------------


class TestHelp:
    @pytest.mark.parametrize("topic", ["search", "extract", "media", "config", "help"])
    async def test_help_topics(self, mcp_session: ClientSession, topic: str):
        r = await mcp_session.call_tool("help", {"tool_name": topic})
        text = parse(r)
        assert len(text) >= 100, f"Help for '{topic}' too short: {len(text)} chars"

    async def test_help_invalid_topic(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool("help", {"tool_name": "nonexistent"})
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("error", "not found", "unknown")), (
            f"Expected error response, got: {text[:80]}"
        )


# ---------------------------------------------------------------------------
# Config tool (offline)
# ---------------------------------------------------------------------------


class TestConfig:
    @pytest.mark.timeout(300)
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

    async def test_config_set(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "config", {"action": "set", "key": "log_level", "value": "DEBUG"}
        )
        text = parse(r)
        assert any(w in text.lower() for w in ("updated", "set")), text[:80]

    async def test_config_cache_clear(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool("config", {"action": "cache_clear"})
        text = parse_allow_error(r)
        # May fail with "database is locked" if warmup is still running
        assert any(
            w in text.lower() for w in ("clear", "cache", "database", "error")
        ), text[:80]

    async def test_config_docs_reindex(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "config", {"action": "docs_reindex", "key": "fastapi"}
        )
        text = parse(r)
        assert any(w in text.lower() for w in ("clear", "reindex", "fastapi")), text[
            :80
        ]

    async def test_config_set_invalid_key(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "config", {"action": "set", "key": "invalid_key", "value": "x"}
        )
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("error", "invalid", "valid")), (
            f"Expected error for invalid key, got: {text[:80]}"
        )


# ---------------------------------------------------------------------------
# Config tool -- warmup action (offline)
# ---------------------------------------------------------------------------


class TestConfigWarmup:
    async def test_config_warmup(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool("config", {"action": "warmup"})
        text = parse(r)
        data = json.loads(text)
        assert "status" in data or "error" not in data, text[:120]


# ---------------------------------------------------------------------------
# Error paths (offline)
# ---------------------------------------------------------------------------


class TestErrorPaths:
    async def test_search_missing_query(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool("search", {"action": "search"})
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("error", "query", "required")), (
            f"Expected error, got: {text[:80]}"
        )

    async def test_search_invalid_action(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "search", {"action": "invalid", "query": "test"}
        )
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("error", "unknown", "invalid")), (
            f"Expected error, got: {text[:80]}"
        )

    async def test_extract_missing_urls(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool("extract", {"action": "extract"})
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("error", "url", "required")), (
            f"Expected error, got: {text[:80]}"
        )

    async def test_media_missing_url(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool("media", {"action": "list"})
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("error", "url", "required")), (
            f"Expected error, got: {text[:80]}"
        )


# ---------------------------------------------------------------------------
# Security boundary (offline)
# ---------------------------------------------------------------------------


class TestSecurity:
    async def test_ssrf_private_ip(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "extract",
            {"action": "extract", "urls": ["http://169.254.169.254/latest/meta-data"]},
        )
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("block", "denied", "ssrf", "error")), (
            f"SSRF not blocked: {text[:80]}"
        )

    async def test_ssrf_localhost(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "extract",
            {"action": "extract", "urls": ["http://127.0.0.1:8080/secret"]},
        )
        text = parse_allow_error(r)
        assert any(w in text.lower() for w in ("block", "denied", "ssrf", "error")), (
            f"SSRF not blocked: {text[:80]}"
        )

    async def test_media_path_traversal(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "media",
            {
                "action": "download",
                "media_urls": ["https://httpbin.org/image/png"],
                "output_dir": "/tmp/evil/../../../etc",
            },
        )
        text = parse_allow_error(r)
        assert any(
            w in text.lower() for w in ("error", "denied", "security", "block")
        ), f"Path traversal not blocked: {text[:80]}"


# ---------------------------------------------------------------------------
# Network-dependent tests (search, extract, media)
# ---------------------------------------------------------------------------


@pytest.mark.network
@pytest.mark.timeout(120)
class TestSearch:
    async def test_search_search(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "search", {"action": "search", "query": "python testing"}
        )
        data = payload(r)
        assert data["_untrusted_source"] == "web"
        results = data["results"]
        assert isinstance(results, list) and results
        assert data["search_backend"] == {
            "requested": ["searxng"],
            "attempted": ["searxng"],
            "selected": "searxng",
            "fallback": "none",
        }

    async def test_search_research(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "search",
            {"action": "research", "query": "transformer attention mechanism"},
        )
        text = parse(r)
        assert len(text) > 50, f"Research result too short: {len(text)} chars"

    async def test_search_docs(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "search", {"action": "docs", "library": "requests", "query": "get"}
        )
        text = parse(r)
        assert len(text) > 50, f"Docs result too short: {len(text)} chars"


@pytest.mark.network
@pytest.mark.timeout(120)
class TestExtract:
    async def test_extract_extract(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "extract", {"action": "extract", "urls": ["https://httpbin.org/html"]}
        )
        text = parse(r)
        assert len(text) > 100, f"Extract result too short: {len(text)} chars"
        data = payload(r)
        assert data["_untrusted_source"] == "web"
        pages = data.get("results")
        assert isinstance(pages, list) and pages
        assert isinstance(pages[0], dict)
        metadata = pages[0].get("metadata")
        assert isinstance(metadata, dict)
        strategy = metadata.get("scrape_strategy_used")
        assert isinstance(strategy, str) and strategy

    async def test_extract_crawl(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "extract",
            {
                "action": "crawl",
                "urls": ["https://docs.python.org/3/library/json.html"],
                "depth": 1,
                "max_pages": 2,
            },
        )
        text = parse(r)
        assert len(text) > 100, f"Crawl result too short: {len(text)} chars"

    async def test_extract_map(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "extract",
            {"action": "map", "urls": ["https://docs.python.org/3/"], "max_pages": 5},
        )
        text = parse(r)
        assert "http" in text.lower() or "url" in text.lower(), text[:80]


@pytest.mark.network
@pytest.mark.timeout(120)
class TestMedia:
    async def test_media_list(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "media", {"action": "list", "url": "https://httpbin.org/image"}
        )
        text = parse(r)
        assert "image" in text.lower() or "media" in text.lower(), text[:80]

    async def test_media_download(self, mcp_session: ClientSession):
        r = await mcp_session.call_tool(
            "media",
            {"action": "download", "media_urls": ["https://httpbin.org/image/png"]},
        )
        text = parse(r)
        assert any(w in text.lower() for w in ("download", "path", "file")), text[:80]

    async def test_media_analyze_no_cell(self, mcp_session: ClientSession):
        """media.analyze with no [models.chat] cell fails gracefully."""
        r = await mcp_session.call_tool(
            "media",
            {"action": "analyze", "url": "/tmp/nonexistent.png", "prompt": "describe"},
        )
        text = parse_allow_error(r)
        assert any(
            w in text.lower() for w in ("cell", "configured", "error", "not found")
        ), text[:80]
