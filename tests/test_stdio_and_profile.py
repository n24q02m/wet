"""Tests for wet MCP stdio transport, canonical ~/.n24q02m/wet storage, profiles, and in-process CLI."""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client

from wet import cli, runtime
from wet.config import Settings


@asynccontextmanager
async def _noop_lifespan(_server):
    yield


def test_default_dirs_use_n24q02m_wet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert runtime.wet_config_dir() == tmp_path / ".n24q02m" / "wet"
    assert Settings(cache_dir="").get_data_dir() == tmp_path / ".n24q02m" / "wet"


def test_n24q02m_home_and_xdg_overrides(tmp_path: Path, monkeypatch) -> None:
    custom_home = tmp_path / "custom-home"
    monkeypatch.setenv("N24Q02M_HOME", str(custom_home))
    assert runtime.wet_config_dir() == custom_home / "wet"

    monkeypatch.delenv("N24Q02M_HOME")
    xdg_cfg = tmp_path / "xdg-cfg"
    monkeypatch.setenv("N24Q02M_USE_XDG", "1")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_cfg))
    monkeypatch.setenv("APPDATA", str(xdg_cfg))
    expected = (xdg_cfg if sys.platform != "win32" else xdg_cfg) / "n24q02m" / "wet"
    assert runtime.wet_config_dir() == expected


def test_legacy_wet_dir_migrates_non_destructively(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    legacy = tmp_path / ".wet"
    legacy.mkdir()
    (legacy / "config.toml").write_text("[server]\nport = 9123\n", encoding="utf-8")

    migrated = runtime.wet_config_dir()
    assert migrated == tmp_path / ".n24q02m" / "wet"
    assert (migrated / "config.toml").read_text(encoding="utf-8") == (
        "[server]\nport = 9123\n"
    )
    assert (legacy / "config.toml").is_file()


def test_profile_routes_config_path(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert cli.main(["--profile", "work", "config", "path"]) == 0
    out_work = Path(capsys.readouterr().out.strip())
    assert (
        out_work == tmp_path / ".n24q02m" / "wet" / "profiles" / "work" / "config.toml"
    )

    assert cli.main(["config", "path", "--profile", "staging"]) == 0
    out_staging = Path(capsys.readouterr().out.strip())
    assert (
        out_staging
        == tmp_path / ".n24q02m" / "wet" / "profiles" / "staging" / "config.toml"
    )


def test_mcp_cli_dispatches_stdio_and_http() -> None:
    with patch("wet.server.run_stdio") as mock_stdio:
        assert cli.main(["mcp"]) == 0
    mock_stdio.assert_called_once_with()

    with patch("wet.server.run_server_blocking") as mock_http:
        assert cli.main(["mcp", "--http", "--host", "127.0.0.1", "--port", "9099"]) == 0
    mock_http.assert_called_once_with(host="127.0.0.1", port=9099)


def test_run_stdio_calls_fastmcp_stdio() -> None:
    from wet import server

    with patch.object(server.mcp, "run") as mock_run:
        server.run_stdio()
    mock_run.assert_called_once_with(transport="stdio")


@pytest.mark.timeout(60)
async def test_stdio_wire_initialize_and_list_tools(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    env["WET_AUTO_SEARXNG"] = "false"
    for k in ("N24Q02M_HOME", "N24Q02M_USE_XDG", "WET_PROFILE", "HULL_PROFILE"):
        env.pop(k, None)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wet.cli", "mcp"],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            info = getattr(init, "server_info", None) or init.serverInfo
            assert info.name == "wet"

            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            assert {"search", "extract", "config", "help"}.issubset(names)


def test_cli_in_process_search_extract_and_docs_search(capsys) -> None:
    mock_search = AsyncMock(return_value={"results": [{"title": "ok"}]})
    mock_extract = AsyncMock(return_value={"content": "hello"})

    with (
        patch("wet.server._lifespan", _noop_lifespan),
        patch("wet.server.search", mock_search),
        patch("wet.server.extract", mock_extract),
    ):
        assert (
            cli.main(["search", "python asyncio", "--local", "--max-results", "5"]) == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload == {"results": [{"title": "ok"}]}
        mock_search.assert_awaited_once_with(
            action="search", query="python asyncio", limit=5
        )

        mock_search.reset_mock()
        assert (
            cli.main(
                [
                    "docs",
                    "search",
                    "fastapi",
                    "routing",
                    "--version",
                    "0.115",
                    "--limit",
                    "3",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload == {"results": [{"title": "ok"}]}
        mock_search.assert_awaited_once_with(
            action="docs",
            library="fastapi",
            query="routing",
            version="0.115",
            limit=3,
        )

        assert (
            cli.main(
                [
                    "extract",
                    "https://example.com",
                    "--action",
                    "extract",
                    "--format",
                    "text",
                ]
            )
            == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload == {"content": "hello"}
        mock_extract.assert_awaited_once_with(
            action="extract",
            urls=["https://example.com"],
            depth=2,
            max_pages=20,
            format="text",
            query=None,
        )
