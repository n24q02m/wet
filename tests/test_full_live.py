"""Full/real live MCP protocol tests for wet-mcp (HTTP transport).

De-host: the server is spawned as the blocking HTTP process and driven through
the streamable-HTTP MCP protocol. Local ONNX mode (no provider cells) unless a
test explicitly configures one.

Usage:
    uv run pytest tests/test_full_live.py -m full -v --tb=short
"""

import json
import os
import socket
import subprocess
import sys
import warnings
from pathlib import Path

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

pytestmark = [pytest.mark.full, pytest.mark.timeout(120)]


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


def _spawn_server(tmp_path: Path, *, rerank_enabled: bool = True):
    """Spawn the real blocking HTTP server on a tmp instance home."""
    local_state = tmp_path / "local-state"
    local_state.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    env = {
        **os.environ,
        "LOG_LEVEL": "WARNING",
        "HOME": str(local_state),
        "USERPROFILE": str(local_state),
        "XDG_CONFIG_HOME": str(local_state),
        "LOCALAPPDATA": str(local_state),
        "APPDATA": str(local_state),
        "CACHE_DIR": str(tmp_path),
        "DOCS_DB_PATH": str(tmp_path / "docs.db"),
        "DOWNLOAD_DIR": str(tmp_path / "downloads"),
        "RERANK_ENABLED": "true" if rerank_enabled else "false",
        "WET_HOST": "127.0.0.1",
        "WET_PORT": str(port),
    }
    log_path = tmp_path / "server.log"
    log_fh = open(log_path, "ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "wet_mcp.server"],
        env=env,
        stdout=log_fh,
        stderr=log_fh,
        close_fds=True,
    )
    log_fh.close()  # the child owns its inherited handle
    return proc, port


async def _connect(port: int):
    """Yield an initialized ClientSession once the listener is up."""
    url = f"http://127.0.0.1:{port}/mcp"
    deadline = 60.0
    waited = 0.0
    while True:
        try:
            httpx.get(url, timeout=2.0)
            break  # any response = up
        except httpx.HTTPError:
            if waited >= deadline:
                raise
            await __import__("asyncio").sleep(0.25)
            waited += 0.25
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def _finish(proc, gen) -> None:
    await gen.aexit(None, None, None)
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def mcp_session(tmp_path):
    """Start a real wet-mcp HTTP server, yield ClientSession (tmp data dirs)."""
    proc, port = _spawn_server(tmp_path)
    gen = _connect(port)
    try:
        session = await gen.asend(None)
        yield session
    except (RuntimeError, ExceptionGroup) as exc:
        msg = str(exc).lower()
        if "cancel scope" in msg or "different task" in msg:
            warnings.warn(f"Suppressed teardown error: {exc}", RuntimeWarning, stacklevel=1)
        else:
            raise
    finally:
        await _finish(proc, gen)


@pytest.fixture
async def mcp_session_rerank_off(tmp_path):
    """MCP session with reranking disabled."""
    proc, port = _spawn_server(tmp_path, rerank_enabled=False)
    gen = _connect(port)
    try:
        session = await gen.asend(None)
        yield session
    except (RuntimeError, ExceptionGroup) as exc:
        msg = str(exc).lower()
        if "cancel scope" in msg or "different task" in msg:
            warnings.warn(f"Suppressed teardown error: {exc}", RuntimeWarning, stacklevel=1)
        else:
            raise
    finally:
        await _finish(proc, gen)


# ---------------------------------------------------------------------------
# Search tool (local ONNX, SearXNG at SEARXNG_URL / auto-local)
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
class TestFullSearch:
    async def test_search_search(self, mcp_session: ClientSession):
        """search.search -- basic web search."""
        r = await mcp_session.call_tool(
            "search", {"action": "search", "query": "python testing"}
        )
        text = parse(r)
        assert len(text) > 50, f"Search result too short: {len(text)} chars"
        assert "result" in text.lower() or "http" in text.lower(), text[:120]

    async def test_search_research(self, mcp_session: ClientSession):
        """search.research -- multi-query deep research."""
        r = await mcp_session.call_tool(
            "search",
            {"action": "research", "query": "transformer attention mechanism"},
        )
        text = parse(r)
        assert len(text) > 100, f"Research result too short: {len(text)} chars"

    async def test_search_docs(self, mcp_session: ClientSession):
        """search.docs -- library documentation search."""
        r = await mcp_session.call_tool(
            "search", {"action": "docs", "library": "requests", "query": "get"}
        )
        text = parse(r)
        assert len(text) > 50, f"Docs result too short: {len(text)} chars"

    async def test_search_similar(self, mcp_session: ClientSession):
        """search.similar -- find similar content in docs."""
        # First index some docs
        await mcp_session.call_tool(
            "search", {"action": "docs", "library": "requests", "query": "get"}
        )
        # Then search similar
        r = await mcp_session.call_tool(
            "search",
            {"action": "similar", "query": "HTTP requests in Python"},
        )
        text = parse_allow_error(r)
        # May return results or "no similar docs" -- both are valid
        assert len(text) > 10, f"Similar result too short: {len(text)} chars"


# ---------------------------------------------------------------------------
# Extract tool (real URLs)
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
class TestFullExtract:
    async def test_extract_extract(self, mcp_session: ClientSession):
        """extract.extract -- extract content from a real URL."""
        r = await mcp_session.call_tool(
            "extract", {"action": "extract", "urls": ["https://example.com"]}
        )
        text = parse(r)
        assert len(text) > 50, f"Extract result too short: {len(text)} chars"
        assert "example" in text.lower() or "domain" in text.lower(), text[:120]

    async def test_extract_crawl(self, mcp_session: ClientSession):
        """extract.crawl -- crawl with depth=1."""
        r = await mcp_session.call_tool(
            "extract",
            {
                "action": "crawl",
                "urls": ["https://example.com"],
                "depth": 1,
                "max_pages": 2,
            },
        )
        text = parse(r)
        assert len(text) > 50, f"Crawl result too short: {len(text)} chars"

    async def test_extract_map(self, mcp_session: ClientSession):
        """extract.map -- site map."""
        r = await mcp_session.call_tool(
            "extract",
            {"action": "map", "urls": ["https://example.com"], "max_pages": 3},
        )
        text = parse(r)
        assert len(text) > 10, f"Map result too short: {len(text)} chars"

    async def test_extract_batch(self, mcp_session: ClientSession):
        """extract.batch -- extract from multiple URLs."""
        r = await mcp_session.call_tool(
            "extract",
            {
                "action": "batch",
                "urls": [
                    "https://example.com",
                    "https://httpbin.org/html",
                ],
            },
        )
        text = parse(r)
        assert len(text) > 50, f"Batch result too short: {len(text)} chars"

    async def test_extract_convert(self, mcp_session: ClientSession, tmp_path):
        """extract.convert -- convert a local file to markdown."""
        test_file = tmp_path / "test.txt"
        test_file.write_text(
            "This is a test document for conversion.", encoding="utf-8"
        )
        r = await mcp_session.call_tool(
            "extract",
            {"action": "convert", "paths": [str(test_file)]},
        )
        text = parse_allow_error(r)
        # Should either convert or report unsupported
        assert len(text) > 10, f"Convert result too short: {len(text)} chars"


# ---------------------------------------------------------------------------
# Media tool
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
class TestFullMedia:
    async def test_media_list(self, mcp_session: ClientSession):
        """media.list -- list media on a page."""
        r = await mcp_session.call_tool(
            "media", {"action": "list", "url": "https://httpbin.org/image"}
        )
        text = parse(r)
        assert (
            "image" in text.lower() or "media" in text.lower() or "http" in text.lower()
        ), text[:120]

    async def test_media_download(self, mcp_session: ClientSession):
        """media.download -- download media file."""
        r = await mcp_session.call_tool(
            "media",
            {"action": "download", "media_urls": ["https://httpbin.org/image/png"]},
        )
        text = parse(r)
        assert any(w in text.lower() for w in ("download", "saved", "path", "file")), (
            text[:120]
        )


# ---------------------------------------------------------------------------
# Config tool
# ---------------------------------------------------------------------------


class TestFullConfig:
    async def test_config_status(self, mcp_session: ClientSession):
        """config.status -- verify mode and config info."""
        r = await mcp_session.call_tool("config", {"action": "status"})
        text = parse(r)
        data = json.loads(text)
        assert "database" in data or "embedding" in data, (
            f"Missing expected keys: {list(data.keys())}"
        )

    async def test_config_set_log_level(self, mcp_session: ClientSession):
        """config.set -- change a runtime setting (the kept set surface)."""
        r = await mcp_session.call_tool(
            "config", {"action": "set", "key": "log_level", "value": "DEBUG"}
        )
        text = parse(r)
        assert any(w in text.lower() for w in ("updated", "set")), text[:120]

    async def test_config_set_rejects_deleted_backend_keys(self, mcp_session):
        """De-host: provider cells live in config.toml, not config.set keys."""
        for key in ("embedding_backend", "rerank_backend"):
            r = await mcp_session.call_tool(
                "config", {"action": "set", "key": key, "value": "local"}
            )
            text = parse_allow_error(r)
            assert "error" in text.lower(), f"{key} should be rejected: {text[:120]}"
            assert "valid_keys" in text

    async def test_config_cache_clear(self, mcp_session: ClientSession):
        """config.cache_clear -- clear web cache."""
        r = await mcp_session.call_tool("config", {"action": "cache_clear"})
        text = parse_allow_error(r)
        assert any(
            w in text.lower()
            for w in ("clear", "cache", "removed", "error", "database")
        ), text[:120]

    async def test_config_docs_reindex(self, mcp_session: ClientSession):
        """config.docs_reindex -- reindex library docs."""
        r = await mcp_session.call_tool(
            "config", {"action": "docs_reindex", "key": "requests"}
        )
        text = parse(r)
        assert any(
            w in text.lower() for w in ("clear", "reindex", "requests", "removed")
        ), text[:120]


# ---------------------------------------------------------------------------
# Setup tool
# ---------------------------------------------------------------------------


class TestFullSetup:
    @pytest.mark.timeout(120)
    async def test_config_warmup(self, mcp_session: ClientSession):
        """config.warmup -- pre-download/verify models."""
        r = await mcp_session.call_tool("config", {"action": "warmup"})
        text = parse(r)
        data = json.loads(text)
        assert "status" in data or "embedding" in data, text[:120]


# ---------------------------------------------------------------------------
# Rerank disabled mode
# ---------------------------------------------------------------------------


@pytest.mark.timeout(120)
class TestFullRerankOff:
    async def test_search_docs_no_rerank(self, mcp_session_rerank_off: ClientSession):
        """search.docs without reranking should still return results."""
        r = await mcp_session_rerank_off.call_tool(
            "search", {"action": "docs", "library": "requests", "query": "get"}
        )
        text = parse(r)
        assert len(text) > 50, f"Docs result too short: {len(text)} chars"

    async def test_config_status_rerank_off(
        self, mcp_session_rerank_off: ClientSession
    ):
        """config.status should show reranking disabled."""
        r = await mcp_session_rerank_off.call_tool("config", {"action": "status"})
        text = parse(r)
        data = json.loads(text)
        reranker = data.get("reranker", {})
        assert reranker.get("available") is False, f"Reranker should be off: {reranker}"


# ---------------------------------------------------------------------------
# Security boundary
# ---------------------------------------------------------------------------


class TestFullSecurity:
    async def test_ssrf_private_ip(self, mcp_session: ClientSession):
        """SSRF: private IP (AWS metadata) should be blocked."""
        r = await mcp_session.call_tool(
            "extract",
            {"action": "extract", "urls": ["http://169.254.169.254/latest/meta-data"]},
        )
        text = parse_allow_error(r)
        assert any(
            w in text.lower() for w in ("block", "denied", "ssrf", "error", "private")
        ), f"SSRF not blocked: {text[:120]}"

    async def test_ssrf_localhost(self, mcp_session: ClientSession):
        """SSRF: localhost should be blocked."""
        r = await mcp_session.call_tool(
            "extract",
            {"action": "extract", "urls": ["http://127.0.0.1:8080/secret"]},
        )
        text = parse_allow_error(r)
        assert any(
            w in text.lower() for w in ("block", "denied", "ssrf", "error", "private")
        ), f"SSRF not blocked: {text[:120]}"

    async def test_path_traversal(self, mcp_session: ClientSession):
        """Path traversal in media download should be blocked."""
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
            w in text.lower()
            for w in ("error", "denied", "security", "block", "traversal")
        ), f"Path traversal not blocked: {text[:120]}"
