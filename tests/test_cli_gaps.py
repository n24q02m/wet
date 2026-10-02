"""Coverage for the ``wet`` CLI paths test_cli.py does not reach.

Real behavior only: platform liveness branches, the real spawn/probe HTTP
helpers, the docs-import/reembed command handlers, and the ``wet search``
MCP consumer round-trip (initialize → notifications/initialized → tools/call)
against a scripted urllib transport — no real network.
"""

import email.message
import importlib.metadata
import io
import json
import os
import tomllib
import urllib.error
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from wet_mcp import cli

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _hs(port: int = 8802, host: str = "127.0.0.1") -> SimpleNamespace:
    return SimpleNamespace(
        server=SimpleNamespace(host=host, port=port, users_file=None)
    )


@pytest.fixture
def locks_dir(tmp_path, monkeypatch):
    d = tmp_path / "locks"
    d.mkdir()
    monkeypatch.setattr(cli, "LOCKS_DIR", d)
    return d


def _write_lock(locks_dir, port: int = 8802, pid: int = 4242):
    lock = locks_dir / f"wet-{port}.lock"
    lock.write_text(f"{pid}\n{port}\ntok\n2026-09-26T00:00:00\n", encoding="utf-8")
    return lock


class _FakeProc:
    """Popen stand-in with a scripted wait()/pid/returncode."""

    def __init__(self, pid=777, wait_result=None, wait_error=None, returncode=None):
        self.pid = pid
        self._wait_result = wait_result
        self._wait_error = wait_error
        self.returncode = returncode
        self.terminated = False

    def wait(self, timeout=None):
        if self._wait_error is not None:
            raise self._wait_error
        return self._wait_result

    def terminate(self):
        self.terminated = True


class _FakeResponse:
    """urlopen-compatible response for ``with urlopen(...) as r`` usage."""

    def __init__(self, payload: bytes, headers: dict | None = None, status: int = 200):
        self.status = status
        self.headers = headers or {}
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
# tiny shared helpers
# ---------------------------------------------------------------------------


def test_version_and_client_version_survive_missing_metadata(monkeypatch):
    def raise_not_found(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", raise_not_found)
    assert cli._version() == "wet (unknown version)"
    assert cli._client_version() == "0"


def test_tail_unreadable_file_reports_instead_of_raising(tmp_path):
    lines = cli._tail(tmp_path, 5)  # a directory cannot be read as text
    assert len(lines) == 1
    assert "unreadable" in lines[0]


def test_pid_alive_platform_liveness_semantics():
    # The running test process must be alive; a DWORD-sized far-fetched pid
    # must not (OpenProcess/os.kill(0) both report it dead).
    assert cli._pid_alive(os.getpid()) is True
    assert cli._pid_alive(2**31 - 1) is False


def test_pid_alive_posix_branches(monkeypatch):
    """os.kill(pid, 0) semantics: lookup failure = dead, permission = alive."""
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(
        cli.os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError())
    )
    assert cli._pid_alive(123) is False
    monkeypatch.setattr(
        cli.os, "kill", lambda pid, sig: (_ for _ in ()).throw(PermissionError())
    )
    assert cli._pid_alive(123) is True
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: None)
    assert cli._pid_alive(123) is True


def test_parse_lock_missing_file_and_garbage_payload(tmp_path):
    assert cli._parse_lock(tmp_path / "absent.lock") is None
    bad = tmp_path / "bad.lock"
    bad.write_text("not-a-pid\nalso-not\nx\ny\n", encoding="utf-8")
    assert cli._parse_lock(bad) is None


def test_find_locks_without_dir_and_exact_port_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "LOCKS_DIR", tmp_path / "absent")
    assert cli._find_locks(None) == []
    monkeypatch.setattr(cli, "LOCKS_DIR", tmp_path)
    (tmp_path / "wet-9001.lock").write_text("1\n9001\nt\nd\n", encoding="utf-8")
    assert cli._find_locks(9001) == [tmp_path / "wet-9001.lock"]
    assert cli._find_locks(9002) == []
    assert cli._find_locks(None) == [tmp_path / "wet-9001.lock"]


def test_http_probe_any_http_answer_means_up(monkeypatch):
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(b"", status=200),
    )
    assert cli._http_probe(9001) is True
    # 401 still proves the server is listening.
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(
            urllib.error.HTTPError(
                "u", 401, "no", email.message.Message(), io.BytesIO(b"")
            )
        ),
    )
    assert cli._http_probe(9001) is True
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(
            urllib.error.URLError("refused")
        ),
    )
    assert cli._http_probe(9001) is False


def test_spawn_server_env_and_detach_flags(tmp_path, monkeypatch):
    """The spawned child must inherit the transport default and explicit binds."""
    seen: dict = {}

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs["env"]
        seen["kwargs"] = kwargs
        return _FakeProc(pid=4321)

    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("WET_HOST", raising=False)
    monkeypatch.delenv("WET_PORT", raising=False)

    proc = cli._spawn_server("0.0.0.0", 9155, explicit_host=True, explicit_port=True)
    assert proc.pid == 4321
    assert seen["argv"] == [cli.sys.executable, "-m", "wet_mcp.server"]
    env = seen["env"]
    assert env["MCP_TRANSPORT"] == "http"
    # The child (-m wet_mcp.server) reads WET_HOST/WET_PORT; MCP_HOST/MCP_PORT
    # are dead names nothing consumes.
    assert env["WET_HOST"] == "0.0.0.0"
    assert env["WET_PORT"] == "9155"
    if cli.os.name == "nt":
        assert seen["kwargs"]["creationflags"] != 0
    else:
        assert seen["kwargs"]["start_new_session"] is True

    # Implicit binds must NOT pin the child to this probe's values.
    cli._spawn_server("0.0.0.0", 9155, explicit_host=False, explicit_port=False)
    assert "WET_HOST" not in seen["env"]
    assert "WET_PORT" not in seen["env"]


# ---------------------------------------------------------------------------
# wet server start: detached + foreground fallback paths
# ---------------------------------------------------------------------------


def test_start_without_port_ignores_live_lock_on_other_port(
    locks_dir, monkeypatch, capsys
):
    """The pre-start scan keys to the RESOLVED port: a live lock on another
    port must not block a start, so per-port multi-instance works."""
    _write_lock(locks_dir, port=9165)
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: True)
    fake = _FakeProc(pid=4322)
    monkeypatch.setattr(cli, "_spawn_server", lambda *a, **k: fake)
    with patch("wet_mcp.runtime.hull_settings", return_value=_hs(port=9166)):
        rc = cli.main(["server", "start"])

    assert rc == 0
    assert "started: pid=4322" in capsys.readouterr().out


def test_start_with_stale_lock_still_spawns(locks_dir, monkeypatch, capsys):
    """A lock whose pid is dead does not block a fresh start."""
    _write_lock(locks_dir, port=9161)
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: False)
    fake = _FakeProc(pid=4321)
    monkeypatch.setattr(cli, "_spawn_server", lambda *a, **k: fake)
    with patch("wet_mcp.runtime.hull_settings", return_value=_hs(port=9161)):
        rc = cli.main(["server", "start", "--port", "9161"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "started: pid=4321" in out


def test_start_foreground_keyboard_interrupt_returns_130(monkeypatch):
    monkeypatch.setattr(cli, "_find_locks", lambda port: [])
    with (
        patch("wet_mcp.runtime.hull_settings", return_value=_hs()),
        patch(
            "wet_mcp.server.run_server_blocking",
            side_effect=KeyboardInterrupt(),
        ),
    ):
        assert cli.main(["server", "start", "--foreground"]) == 130


def test_start_foreground_fallback_spawns_and_waits(monkeypatch):
    """Without the blocking entry the CLI degrades to spawn-and-wait."""
    monkeypatch.setattr(cli, "_find_locks", lambda port: [])
    monkeypatch.delattr("wet_mcp.server.run_server_blocking")
    fake = _FakeProc(pid=99, wait_result=7)
    monkeypatch.setattr(cli, "_spawn_server", lambda *a, **k: fake)
    with patch("wet_mcp.runtime.hull_settings", return_value=_hs(port=9162)):
        rc = cli.main(["server", "start", "--foreground", "--port", "9162"])

    assert rc == 7


def test_start_foreground_fallback_interrupt_terminates_child(monkeypatch):
    monkeypatch.setattr(cli, "_find_locks", lambda port: [])
    monkeypatch.delattr("wet_mcp.server.run_server_blocking")
    fake = _FakeProc(pid=99, wait_error=KeyboardInterrupt())
    monkeypatch.setattr(cli, "_spawn_server", lambda *a, **k: fake)
    with patch("wet_mcp.runtime.hull_settings", return_value=_hs(port=9163)):
        rc = cli.main(["server", "start", "--foreground", "--port", "9163"])

    assert rc == 130
    assert fake.terminated is True


def test_terminate_and_force_kill_use_the_platform_mechanism(monkeypatch):
    """nt: taskkill; posix: SIGTERM then SIGKILL. Recorded, never real kills."""
    calls: list[tuple] = []
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(cli.os, "kill", lambda pid, sig: calls.append((pid, sig)))
    monkeypatch.setattr(cli.signal, "SIGKILL", 9, raising=False)
    cli._terminate(11)
    cli._force_kill(11)
    import signal

    assert calls == [(11, signal.SIGTERM), (11, 9)]

    calls.clear()
    monkeypatch.setattr(cli.os, "name", "nt")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda argv, **k: calls.append(tuple(argv)),
    )
    cli._terminate(22)
    cli._force_kill(22)
    assert calls == [
        (
            cli.os.path.join(
                cli.os.environ.get("WINDIR", "C:\\Windows"), "System32", "taskkill.exe"
            ),
            "/PID",
            "22",
        ),
        (
            cli.os.path.join(
                cli.os.environ.get("WINDIR", "C:\\Windows"), "System32", "taskkill.exe"
            ),
            "/PID",
            "22",
            "/T",
            "/F",
        ),
    ]


# ---------------------------------------------------------------------------
# wet server status: malformed payload branch
# ---------------------------------------------------------------------------


def test_status_malformed_lock_reports_payload(locks_dir, monkeypatch, capsys):
    bad = locks_dir / "wet-9164.lock"
    bad.write_text("garbage\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(cli, "_http_probe", lambda port: False)
    rc = cli.main(["server", "status", "--port", "9164"])

    assert rc == 1  # nothing alive, nothing up
    assert "malformed payload" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# wet config: scalar coercion + secret handling edges
# ---------------------------------------------------------------------------


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    d = tmp_path / "wet-home"
    d.mkdir()
    monkeypatch.setattr("wet_mcp.runtime.wet_config_dir", lambda: d)
    monkeypatch.setattr("wet_mcp.runtime.wet_config_path", lambda: d / "config.toml")
    return d


def _init_config(config_dir) -> None:
    cli.main(["config", "init"])


def test_config_get_prints_boolean_as_toml_bare_word(config_dir, capsys):
    _init_config(config_dir)
    path = config_dir / "config.toml"
    with patch("wet_mcp.runtime.wet_config_path", return_value=path):
        assert cli.main(["config", "set", "server.debug", "true"]) == 0
        assert cli.main(["config", "get", "server.debug"]) == 0
    assert capsys.readouterr().out.strip().endswith("true")


def test_config_set_bool_writes_bare_toml_bool(config_dir):
    _init_config(config_dir)
    path = config_dir / "config.toml"
    with patch("wet_mcp.runtime.wet_config_path", return_value=path):
        assert cli.main(["config", "set", "server.debug", "true"]) == 0
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data["server"]["debug"] is True


def test_config_set_hash_key_value_is_echoed(capsys, config_dir):
    """A scrypt *_hash is not the secret; echoing it IS the operator workflow."""
    _init_config(config_dir)
    with patch(
        "wet_mcp.runtime.wet_config_path", return_value=config_dir / "config.toml"
    ):
        assert (
            cli.main(["config", "set", "models.embed.api_key_hash", "scrypt$abc"]) == 0
        )
    assert "scrypt$abc" in capsys.readouterr().out


def test_config_set_without_file_fails_with_hint(capsys, config_dir):
    with patch(
        "wet_mcp.runtime.wet_config_path", return_value=config_dir / "config.toml"
    ):
        rc = cli.main(["config", "set", "server.port", "1234"])
    assert rc == 1
    assert "no config at" in capsys.readouterr().err


def test_config_set_rejects_non_dotted_key(capsys, config_dir):
    _init_config(config_dir)
    with patch(
        "wet_mcp.runtime.wet_config_path", return_value=config_dir / "config.toml"
    ):
        rc = cli.main(["config", "set", "port", "1234"])
    assert rc == 1
    assert "dotted" in capsys.readouterr().err


def test_toml_scalar_coercions():
    assert cli._toml_scalar("true") == "true"
    assert cli._toml_scalar('"quoted"') == '"quoted"'
    assert cli._toml_scalar("plain words") == '"plain words"'
    assert cli._toml_scalar("8.5") == "8.5"
    assert cli._toml_scalar("[1, 2]") == "[1, 2]"


# ---------------------------------------------------------------------------
# wet docs import / reembed command handlers
# ---------------------------------------------------------------------------


def test_docs_import_success_prints_receipt(capsys):
    result = {
        "chunks": 10,
        "libraries": 2,
        "versions": 3,
        "fts_rows": 10,
        "db_path": "/x/docs.db",
        "elapsed_s": 1.5,
    }
    with patch("wet_mcp.docs_import.import_docs", return_value=result) as mock:
        rc = cli.main(["docs", "import", "export.sql", "--db", "/x/docs.db"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "chunks:     10" in out
    assert "fts rows:   10" in out
    assert mock.call_args.kwargs["db_path"] is not None


def test_docs_import_skipped_fts_prints_placeholder(capsys):
    result = {
        "chunks": 1,
        "libraries": 1,
        "versions": 1,
        "fts_rows": None,
        "db_path": "/x/docs.db",
        "elapsed_s": 0.2,
    }
    with patch("wet_mcp.docs_import.import_docs", return_value=result):
        rc = cli.main(["docs", "import", "export.sql", "--skip-fts"])

    assert rc == 0
    assert "(skipped)" in capsys.readouterr().out


def test_docs_import_failure_returns_one(capsys):
    with patch(
        "wet_mcp.docs_import.import_docs",
        side_effect=RuntimeError("count mismatch"),
    ):
        rc = cli.main(["docs", "import", "export.sql"])

    assert rc == 1
    assert "wet docs import failed: count mismatch" in capsys.readouterr().err


def test_docs_reembed_transport_error_returns_one(capsys):
    with patch(
        "wet_mcp.docs_reembed.reembed",
        new_callable=AsyncMock,
        side_effect=RuntimeError("provider unreachable"),
    ):
        rc = cli.main(["docs", "reembed"])

    assert rc == 1
    assert "provider unreachable" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# wet search: RPC transport + response parsing + full consumer round-trip
# ---------------------------------------------------------------------------


def _init_ok(session_id="sid-1"):
    return _FakeResponse(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": cli._MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "serverInfo": {"name": "wet-mcp"},
                },
            }
        ).encode(),
        headers={"Content-Type": "application/json", "Mcp-Session-Id": session_id},
    )


def _call_ok(text="RESULT TEXT", *, is_error=False, extra=None):
    result: dict = {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    if extra:
        result.update(extra)
    return _FakeResponse(
        json.dumps({"jsonrpc": "2.0", "id": 2, "result": result}).encode(),
        headers={"Content-Type": "application/json"},
    )


def _scripted_urlopen(routes: dict, calls: list):
    """Route by JSON-RPC method; entries may be responses, exceptions, or
    callables of the parsed body."""

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data or b"null")
        calls.append(body)
        entry = routes[body.get("method")]
        if isinstance(entry, Exception):
            raise entry
        if callable(entry):
            entry = entry(body)
        assert isinstance(entry, _FakeResponse)
        return entry

    return fake_urlopen


def test_post_rpc_success_error_and_transport_failure(monkeypatch):
    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request, timeout=None: _FakeResponse(b"{}", headers={"X": "y"}),
    )
    status, headers, body, err = cli._post_rpc("http://x/mcp", {}, None, None, 1.0)
    assert (status, body, err) == (200, "{}", None)
    assert headers["X"] == "y"

    def raise_http_error(request, timeout=None):
        raise urllib.error.HTTPError(
            "http://x/mcp", 503, "down", email.message.Message(), io.BytesIO(b"boom")
        )

    monkeypatch.setattr(cli.urllib.request, "urlopen", raise_http_error)
    status, headers, body, err = cli._post_rpc("http://x/mcp", {}, None, None, 1.0)
    assert (status, body, err) == (503, "boom", None)

    monkeypatch.setattr(
        cli.urllib.request,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(
            urllib.error.URLError("refused")
        ),
    )
    status, headers, body, err = cli._post_rpc("http://x/mcp", {}, None, None, 1.0)
    assert status is None and err is not None


def test_post_rpc_sends_session_and_token_headers(monkeypatch):
    seen: dict = {}

    def fake_urlopen(request, timeout=None):
        seen["session"] = request.get_header("Mcp-session-id")
        seen["auth"] = request.get_header("Authorization")
        return _FakeResponse(b"{}")

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    cli._post_rpc("http://x/mcp", {}, "sid-9", "tok-9", 1.0)
    assert seen["session"] == "sid-9"
    assert seen["auth"] == "Bearer tok-9"


def test_extract_rpc_response_sse_and_json_variants():
    sse = (
        "event: message\r\n"
        'data: {"jsonrpc":"2.0","id":7,"result":{"a":1}}\r\n'
        "data: [DONE]\r\n"
        "data: not-json\r\n"
        'data: {"jsonrpc":"2.0","id":8}\r\n'
    )
    matched = cli._extract_rpc_response(sse, "text/event-stream", 7)
    assert matched == {"jsonrpc": "2.0", "id": 7, "result": {"a": 1}}
    # No data line carries the requested id.
    assert cli._extract_rpc_response(sse, "text/event-stream", 99) is None
    # SSE detection via body shape even without the content type.
    assert cli._extract_rpc_response("data: {}", "", 1) is None
    # Plain JSON both ways.
    assert cli._extract_rpc_response('{"id":1}', "application/json", 1) == {"id": 1}
    assert cli._extract_rpc_response("<html>", "application/json", 1) is None


def test_search_happy_path_round_trip(monkeypatch, capsys):
    calls: list = []
    routes = {
        "initialize": _init_ok("sid-42"),
        "notifications/initialized": _FakeResponse(b"", status=202),
        "tools/call": lambda body: calls.append(body) or _call_ok("found it"),
    }
    monkeypatch.setattr(cli.urllib.request, "urlopen", _scripted_urlopen(routes, []))
    monkeypatch.delenv("WET_TOKEN", raising=False)
    rc = cli.main(
        ["search", "pytest fixtures", "--max-results", "5", "--token", "tok-1"]
    )

    assert rc == 0
    assert "found it" in capsys.readouterr().out
    call = calls[-1]
    assert call["params"]["arguments"] == {
        "action": "search",
        "query": "pytest fixtures",
        "limit": 5,
    }


def test_search_sends_session_id_on_subsequent_requests(monkeypatch):
    """The Mcp-Session-Id minted by initialize rides every later POST."""
    captured: list = []
    calls: list = []

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data or b"null")
        captured.append(dict(request.headers))
        calls.append(body)
        if body.get("method") == "initialize":
            return _init_ok("sid-77")
        return (
            _FakeResponse(b"", status=202)
            if body.get("method", "").startswith("notifications")
            else _call_ok()
        )

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    rc = cli.main(["search", "q"])

    assert rc == 0
    assert captured[-1].get("Mcp-session-id") == "sid-77"


def test_search_tool_error_prints_detail_and_fails(monkeypatch, capsys):
    routes = {
        "initialize": _init_ok(),
        "notifications/initialized": _FakeResponse(b""),
        "tools/call": _call_ok("boom detail", is_error=True),
    }
    monkeypatch.setattr(cli.urllib.request, "urlopen", _scripted_urlopen(routes, []))
    rc = cli.main(["search", "q"])

    assert rc == 1
    assert "boom detail" in capsys.readouterr().err


def test_search_empty_result_prints_placeholder(monkeypatch, capsys):
    routes = {
        "initialize": _init_ok(),
        "notifications/initialized": _FakeResponse(b""),
        "tools/call": _FakeResponse(
            json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"content": []}}).encode(),
            headers={"Content-Type": "application/json"},
        ),
    }
    monkeypatch.setattr(cli.urllib.request, "urlopen", _scripted_urlopen(routes, []))
    rc = cli.main(["search", "q"])

    assert rc == 0
    assert "(empty result)" in capsys.readouterr().out


def test_search_tools_call_answer_arriving_as_sse(monkeypatch, capsys):
    sse_body = (
        "event: message\r\n"
        'data: {"jsonrpc":"2.0","id":2,'
        '"result":{"content":[{"type":"text","text":"SSE TEXT"}]}}\r\n\r\n'
    )
    routes = {
        "initialize": _init_ok(),
        "notifications/initialized": _FakeResponse(b""),
        "tools/call": _FakeResponse(
            sse_body.encode(), headers={"Content-Type": "text/event-stream"}
        ),
    }
    monkeypatch.setattr(cli.urllib.request, "urlopen", _scripted_urlopen(routes, []))
    rc = cli.main(["search", "q"])

    assert rc == 0
    assert "SSE TEXT" in capsys.readouterr().out


def test_search_initialize_failures(monkeypatch, capsys):
    # Non-dict body.
    routes = {
        "initialize": _FakeResponse(
            b"[1,2]", headers={"Content-Type": "application/json"}
        ),
        "tools/call": _call_ok(),
    }
    monkeypatch.setattr(cli.urllib.request, "urlopen", _scripted_urlopen(routes, []))
    assert cli.main(["search", "q"]) == 1
    assert "unexpected initialize response" in capsys.readouterr().err

    # JSON-RPC error object.
    routes = {
        "initialize": _FakeResponse(
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "bad"}}
            ).encode(),
            headers={"Content-Type": "application/json"},
        ),
        "tools/call": _call_ok(),
    }
    monkeypatch.setattr(cli.urllib.request, "urlopen", _scripted_urlopen(routes, []))
    assert cli.main(["search", "q"]) == 1
    assert "initialize failed" in capsys.readouterr().err


def test_search_tools_call_failures(monkeypatch, capsys):
    # Non-dict tools/call body.
    routes = {
        "initialize": _init_ok(),
        "notifications/initialized": _FakeResponse(b""),
        "tools/call": _FakeResponse(
            b'"str"', headers={"Content-Type": "application/json"}
        ),
    }
    monkeypatch.setattr(cli.urllib.request, "urlopen", _scripted_urlopen(routes, []))
    assert cli.main(["search", "q"]) == 1
    assert "unexpected tools/call response" in capsys.readouterr().err

    # JSON-RPC error object.
    routes = {
        "initialize": _init_ok(),
        "notifications/initialized": _FakeResponse(b""),
        "tools/call": _FakeResponse(
            json.dumps(
                {"jsonrpc": "2.0", "id": 2, "error": {"code": -1, "message": "nope"}}
            ).encode(),
            headers={"Content-Type": "application/json"},
        ),
    }
    monkeypatch.setattr(cli.urllib.request, "urlopen", _scripted_urlopen(routes, []))
    assert cli.main(["search", "q"]) == 1
    assert "nope" in capsys.readouterr().err


def test_search_connection_drop_midflight_returns_2(monkeypatch, capsys):
    routes = {
        "initialize": _init_ok(),
        "notifications/initialized": _FakeResponse(b""),
        "tools/call": urllib.error.URLError("connection reset"),
    }
    monkeypatch.setattr(cli.urllib.request, "urlopen", _scripted_urlopen(routes, []))
    rc = cli.main(["search", "q"])

    assert rc == 2
    assert "not running" in capsys.readouterr().err


def test_search_custom_url_rstrip_and_env_token(monkeypatch, capsys):
    seen: list = []
    routes = {
        "initialize": _init_ok(),
        "notifications/initialized": _FakeResponse(b""),
        "tools/call": _call_ok("ok"),
    }

    def fake_urlopen(request, timeout=None):
        seen.append(request.full_url)
        return _scripted_urlopen(routes, [])(request, timeout)

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("WET_TOKEN", "env-tok")
    rc = cli.main(["search", "q", "--url", "http://127.0.0.1:9991/"])

    assert rc == 0
    assert seen[0] == "http://127.0.0.1:9991/mcp"


# ---------------------------------------------------------------------------
# wet docs reindex: library without a servable version
# ---------------------------------------------------------------------------


class _FakeDocsDB:
    def __init__(self, *a, **k):
        self._conn = SimpleNamespace(close=lambda: None)
        self.cleared: list = []
        self.reset: list = []

    def get_library(self, name):
        return {"id": "lib-1", "name": name}

    def get_best_version(self, library_id):
        return None  # indexed metadata only, nothing servable

    def clear_version_chunks(self, version_id):
        self.cleared.append(version_id)

    def reset_version_index(self, version_id):
        self.reset.append(version_id)


def test_reindex_library_without_version_skips_clearing(monkeypatch, capsys):
    fake = _FakeDocsDB()
    monkeypatch.setattr("wet_mcp.db.DocsDB", lambda *a, **k: fake)
    rc = cli.main(["docs", "reindex", "solo-lib"])

    assert rc == 0
    assert fake.cleared == [] and fake.reset == []
    assert '"status": "cleared"' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# jev._results_blob bounds (used by the K1/N6 prompts)
# ---------------------------------------------------------------------------


def test_results_blob_skips_non_dicts_and_falls_back():
    from typing import cast

    from wet_mcp.jev import _results_blob

    assert _results_blob([]) == "(no result text)"
    assert _results_blob(cast(list[dict], ["junk", 42])) == "(no result text)"
    blob = _results_blob(
        cast(
            list[dict],
            [{"title": "T", "snippet": "s"}, {"content": "c"}, "junk", {"title": "T2"}],
        ),
        max_chars=10_000,
    )
    assert "- T: s" in blob and "- : c" in blob and "- T2:" in blob
    assert "junk" not in blob
