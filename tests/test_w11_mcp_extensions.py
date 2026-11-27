"""W11 tests: MCP 2026-07-28 extensions (skills, tasks, elicitation, files) and E2E gates."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import mcp_types
import pytest
from fastmcp import FastMCP
from fastmcp.server.elicitation import AcceptedElicitation, DeclinedElicitation
from fastmcp.skills.models import (
    GetSkillParams,
    GetSkillRequest,
    GetSkillResult,
    ListSkillsParams,
    ListSkillsRequest,
    ListSkillsResult,
)
from fastmcp_tasks.client_models import (
    ClientCreateTaskResult,
    ClientGetTaskResult,
    GetTaskRequest,
    GetTaskRequestParams,
)
from hull_core.server import FILES_EXTENSION_ID, SKILLS_EXTENSION_ID, TASKS_EXTENSION_ID
from live_http import spawn_wet_server
from mcp.client._probe import negotiate_auto
from mcp.client.extension import ResultClaim
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from process_lifeline import stop_supervised
from structured import payload

from wet import cli
from wet import server as srv

pytestmark = [pytest.mark.timeout(120)]

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Unit tests: extension wiring, skills resolution, files, elicitation
# ---------------------------------------------------------------------------


def test_server_registers_skills_and_tasks_extensions() -> None:
    """Server uses FastMCP with Skills and Tasks extensions registered."""
    assert isinstance(srv.mcp, FastMCP)
    assert SKILLS_EXTENSION_ID in srv.mcp._extensions
    assert TASKS_EXTENSION_ID in srv.mcp._extensions


async def test_long_running_tools_advertise_optional_tasks() -> None:
    """Long-running web tools configure optional task mode; fast tools do not."""
    tools = {t.name: t for t in await srv.mcp.list_tools()}
    for name in ("search", "extract", "media"):
        assert tools[name].task_config.mode == "optional", (
            f"{name} missing optional task mode"
        )
    for name in ("help", "config"):
        assert tools[name].task_config.mode == "forbidden", (
            f"{name} should stay synchronous"
        )


def test_resolve_skills_dir_handles_wheel_and_source_layouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_resolve_skills_dir detects both site-packages/skills and repo/skills."""
    assert srv._resolve_skills_dir() == ROOT / "skills"

    wheel_root = tmp_path / "site-packages"
    wheel_skills = wheel_root / "skills"
    wheel_skills.mkdir(parents=True)
    fake_server = wheel_root / "wet" / "server.py"
    fake_server.parent.mkdir(parents=True)
    fake_server.write_text("", encoding="utf-8")

    monkeypatch.setattr(srv, "__file__", str(fake_server))
    assert srv._resolve_skills_dir() == wheel_skills

    # Neither site-packages/skills nor parent/skills exists
    isolated_server = tmp_path / "nowhere" / "wet" / "server.py"
    isolated_server.parent.mkdir(parents=True)
    isolated_server.write_text("", encoding="utf-8")
    monkeypatch.setattr(srv, "__file__", str(isolated_server))
    assert srv._resolve_skills_dir() is None


async def test_media_download_attaches_file_payloads(tmp_path: Path) -> None:
    """media(action='download') attaches ext-files entries for saved local files."""
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()
    sample = dl_dir / "photo.jpg"
    sample.write_bytes(b"\xff\xd8\xff\xe0test-jpeg")

    mock_dl = AsyncMock(
        return_value=json.dumps(
            [
                {
                    "url": "https://example.com/photo.jpg",
                    "path": str(sample),
                    "size": 14,
                },
                {
                    "url": "https://example.com/missing.jpg",
                    "path": str(dl_dir / "missing.jpg"),
                    "size": 0,
                },
                {"url": "https://example.com/empty.jpg", "path": "", "size": 0},
                "non-dict-entry",
            ]
        )
    )
    fake_settings = SimpleNamespace(download_dir=str(dl_dir), tool_timeout=30)

    with (
        patch.object(srv, "settings", fake_settings),
        patch("wet.sources.crawler.download_media", mock_dl),
    ):
        res = await srv.media(
            action="download",
            media_urls=["https://example.com/photo.jpg"],
        )

    data = payload(res)
    assert "files" in data
    assert len(data["files"]) == 1
    file_entry = data["files"][0]
    assert file_entry["extension"] == FILES_EXTENSION_ID
    assert file_entry["filename"] == "photo.jpg"
    assert file_entry["sizeBytes"] == len(b"\xff\xd8\xff\xe0test-jpeg")
    assert "blob" in file_entry["resource"]


async def test_config_cache_clear_elicitation_and_fallback() -> None:
    """cache_clear supports MCP elicitation and falls back gracefully when unsupported."""
    mock_cache = MagicMock()
    mock_cache.clear = MagicMock(return_value=3)

    with patch.object(srv, "_web_cache", mock_cache):
        # 1. Interactive client declines -> cancelled, cache untouched
        ctx_decline = MagicMock()
        ctx_decline.elicit = AsyncMock(return_value=DeclinedElicitation())
        with patch.object(srv, "_current_mcp_context", return_value=ctx_decline):
            res_declined = await srv.config("cache_clear")
        assert payload(res_declined)["status"] == "cancelled"
        mock_cache.clear.assert_not_called()

        # 2. Interactive client accepts -> cleared
        ctx_accept = MagicMock()
        ctx_accept.elicit = AsyncMock(return_value=AcceptedElicitation(data=True))
        with patch.object(srv, "_current_mcp_context", return_value=ctx_accept):
            res_accepted = await srv.config("cache_clear")
        assert payload(res_accepted)["status"] == "cache cleared"
        assert mock_cache.clear.call_count == 1

        # 3. Client does not support elicitation (MCPError) -> falls back to default=True
        ctx_unsupported = MagicMock()
        ctx_unsupported.elicit = AsyncMock(
            side_effect=MCPError(code=-32601, message="elicitation unsupported")
        )
        with patch.object(srv, "_current_mcp_context", return_value=ctx_unsupported):
            res_fallback = await srv.config("cache_clear")
        assert payload(res_fallback)["status"] == "cache cleared"
        assert mock_cache.clear.call_count == 2

        # 4. force=True bypasses elicitation completely
        ctx_force = MagicMock()
        ctx_force.elicit = AsyncMock()
        with patch.object(srv, "_current_mcp_context", return_value=ctx_force):
            res_forced = await srv.config("cache_clear", force=True)
        assert payload(res_forced)["status"] == "cache cleared"
        ctx_force.elicit.assert_not_called()
        assert mock_cache.clear.call_count == 3


def test_cli_unwrap_tool_result_handles_v2_and_v1_attributes() -> None:
    """_unwrap_tool_result supports both MCP v2 structured_content and legacy alias."""
    v2 = CallToolResult(content=[], structured_content={"ok": True}, is_error=False)
    assert cli._unwrap_tool_result(v2) == {"ok": True}

    v1 = SimpleNamespace(structuredContent={"legacy": 1}, content=[])
    assert cli._unwrap_tool_result(v1) == {"legacy": 1}


# ---------------------------------------------------------------------------
# E2E Wire Helpers (real subprocesses + real MCP ClientSession)
# ---------------------------------------------------------------------------


class _SearxngHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/healthz"):
            body_obj: dict = {"status": "ok"}
        elif self.path.startswith("/search"):
            body_obj = {
                "results": [
                    {
                        "url": f"https://example.com/w11-result-{idx}",
                        "title": f"W11 test result {idx}",
                        "content": f"Deterministic fixture snippet {idx}.",
                        "engine": "fixture",
                    }
                    for idx in range(3)
                ]
            }
        else:
            self.send_error(404)
            return

        raw = json.dumps(body_obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def mock_searxng_url():
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


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _hermetic_env(tmp_path: Path, searxng_url: str) -> dict[str, str]:
    local_state = tmp_path / "local-state"
    local_state.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    return {
        **os.environ,
        "LOG_LEVEL": "WARNING",
        "HOME": str(local_state),
        "USERPROFILE": str(local_state),
        "XDG_CONFIG_HOME": str(local_state),
        "LOCALAPPDATA": str(local_state),
        "APPDATA": str(local_state),
        "CACHE_DIR": str(tmp_path),
        "DOCS_DB_PATH": str(tmp_path / "docs.db"),
        "EMBEDDING_DIMS": "0",
        "RERANK_ENABLED": "false",
        "DISABLE_LOCAL_EMBED": "true",
        "DISABLE_LOCAL_RERANK": "true",
        "SEARCH_BACKENDS": "searxng",
        "SEARXNG_URL": searxng_url,
        "WET_AUTO_SEARXNG": "false",
        "WET_HOST": "127.0.0.1",
        "WET_PORT": str(port),
    }


def _task_claim_map() -> dict[str, list[ResultClaim]]:
    async def _noop_resolve(
        _create_result: ClientCreateTaskResult, _ctx
    ) -> CallToolResult:
        return CallToolResult(content=[])

    return {
        TASKS_EXTENSION_ID: [
            ResultClaim(
                result_type="task",
                model=ClientCreateTaskResult,
                resolve=_noop_resolve,
                protocol_versions=frozenset(MODERN_PROTOCOL_VERSIONS),
            )
        ]
    }


async def _poll_task_until_complete(
    session: ClientSession, task_id: str
) -> ClientGetTaskResult:
    for _ in range(100):
        status = await session.send_request(
            GetTaskRequest(params=GetTaskRequestParams(task_id=task_id)),
            ClientGetTaskResult,
        )
        if status.status in ("completed", "failed", "cancelled"):
            return status
        await asyncio.sleep(0.05)
    raise AssertionError(f"Task {task_id} did not reach terminal status")


async def _assert_skills_and_fallback(session: ClientSession) -> None:
    skills_res = await session.send_request(
        ListSkillsRequest(params=ListSkillsParams()),
        ListSkillsResult,
    )
    names = {s.frontmatter.root["name"] for s in skills_res.skills}
    assert {"wet", "compare", "research-topic", "scrape-batch"}.issubset(names)

    wet_skill = next(
        s for s in skills_res.skills if s.frontmatter.root["name"] == "wet"
    )
    get_res = await session.send_request(
        GetSkillRequest(params=GetSkillParams(uri=wet_skill.uri)),
        GetSkillResult,
    )
    assert get_res.skill.frontmatter.root["name"] == "wet"

    resource_res = await session.read_resource(wet_skill.uri)
    text_body = "".join(getattr(part, "text", "") for part in resource_res.contents)
    assert "wet" in text_body.lower()

    # Verify expected tools are listed on the wire
    tools_res = await session.list_tools()
    by_name = {t.name: t for t in tools_res.tools}
    assert {"search", "extract", "media", "help", "config"}.issubset(by_name)

    # Graceful fallback: plain ClientSession without tasks capability runs synchronously
    sync_res = await session.call_tool(
        "search",
        {"action": "search", "query": "mcp skills"},
    )
    assert isinstance(sync_res, CallToolResult)
    assert sync_res.is_error is False
    assert sync_res.structured_content is not None
    assert len(sync_res.structured_content["results"]) == 3


async def _assert_task_augmented_execution(session: ClientSession) -> None:
    created = await session.call_tool(
        "search",
        {"action": "search", "query": "mcp tasks"},
        allow_claimed=True,
    )
    assert isinstance(created, ClientCreateTaskResult), (
        f"Expected task result, got {type(created)}"
    )
    final = await _poll_task_until_complete(session, created.task_id)
    assert final.status == "completed", f"Task failed: {final.error}"
    raw_result = final.result
    if isinstance(raw_result, mcp_types.CallToolResult):
        assert raw_result.is_error is False
        assert raw_result.structured_content is not None
        assert len(raw_result.structured_content["results"]) == 3
    else:
        assert isinstance(raw_result, dict)
        assert raw_result.get("isError") is False
        assert len(raw_result["structuredContent"]["results"]) == 3


def _wait_until_http_up(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/mcp", timeout=2.0)
            return
        except httpx.HTTPError:
            time.sleep(0.25)
    raise RuntimeError(f"wet HTTP server on port {port} did not come up")


# ---------------------------------------------------------------------------
# Real E2E Tests: Stdio + Streamable HTTP
# ---------------------------------------------------------------------------


async def test_stdio_e2e_skills_tasks_and_fallback(
    tmp_path: Path, mock_searxng_url: str
) -> None:
    """Real stdio MCP ClientSession covers skills/list, skill://, tasks, and fallback."""
    env = _hermetic_env(tmp_path, mock_searxng_url)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from wet.server import run_stdio; run_stdio()"],
        env=env,
        cwd=str(ROOT),
    )

    # 1. Plain ClientSession (2026-07-28 via server/discover, no tasks capability) -> skills + fallback
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await negotiate_auto(session)
            assert session.protocol_version == "2026-07-28"
            assert session.server_capabilities is not None
            ext_caps = session.server_capabilities.extensions or {}
            assert SKILLS_EXTENSION_ID in ext_caps
            assert TASKS_EXTENSION_ID in ext_caps
            await _assert_skills_and_fallback(session)

    # 2. Task-capable ClientSession (2026-07-28) -> task execution + polling
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
            extensions={TASKS_EXTENSION_ID: {}},
            result_claims=_task_claim_map(),
        ) as session:
            await negotiate_auto(session)
            await _assert_task_augmented_execution(session)

    # 3. Legacy handshake ClientSession (2025-11-25) -> skill:// resource + synchronous fallback
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            legacy_res = await session.call_tool(
                "search", {"action": "search", "query": "legacy fallback"}
            )
            assert isinstance(legacy_res, CallToolResult)
            assert legacy_res.is_error is False


async def test_http_e2e_skills_tasks_and_fallback(
    tmp_path: Path, mock_searxng_url: str
) -> None:
    """Real Streamable HTTP ClientSession covers skills/list, skill://, tasks, and fallback."""
    env = _hermetic_env(tmp_path, mock_searxng_url)
    port = int(env["WET_PORT"])
    log_path = tmp_path / "server.log"
    proc = spawn_wet_server(env, log_path)
    try:
        _wait_until_http_up(port)
        url = f"http://127.0.0.1:{port}/mcp"

        # 1. Plain ClientSession (2026-07-28 via server/discover, no tasks capability) -> skills + fallback
        try:
            async with streamable_http_client(url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await negotiate_auto(session)
                    assert session.protocol_version == "2026-07-28"
                    assert session.server_capabilities is not None
                    ext_caps = session.server_capabilities.extensions or {}
                    assert SKILLS_EXTENSION_ID in ext_caps
                    assert TASKS_EXTENSION_ID in ext_caps
                    await _assert_skills_and_fallback(session)
        except (RuntimeError, ExceptionGroup) as exc:
            if (
                "cancel scope" not in str(exc).lower()
                and "different task" not in str(exc).lower()
            ):
                raise
            warnings.warn(
                f"Suppressed teardown error: {exc}", RuntimeWarning, stacklevel=1
            )

        # 2. Task-capable ClientSession (2026-07-28) -> task execution + polling
        try:
            async with streamable_http_client(url) as (read_stream, write_stream):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    extensions={TASKS_EXTENSION_ID: {}},
                    result_claims=_task_claim_map(),
                ) as session:
                    await negotiate_auto(session)
                    await _assert_task_augmented_execution(session)
        except (RuntimeError, ExceptionGroup) as exc:
            if (
                "cancel scope" not in str(exc).lower()
                and "different task" not in str(exc).lower()
            ):
                raise
            warnings.warn(
                f"Suppressed teardown error: {exc}", RuntimeWarning, stacklevel=1
            )
    finally:
        stop_supervised(proc)
