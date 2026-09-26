"""Tests for the de-hosted ``wet`` CLI control plane (wet_mcp.cli).

The old mcp_core build_cli mount is gone: bare ``wet`` prints help (rc 0),
subcommands run one-shot operator actions, and unknown subcommands fail with
argparse's exit 2. Auth google / logout / relay / sync are deleted surface and
are no longer exercised. No network or model calls — server spawn, hull
settings, DocsDB and reembed/warmup are mocked.
"""

import tomllib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wet_mcp import cli


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _hs(port: int = 8802, host: str = "127.0.0.1") -> SimpleNamespace:
    """Minimal stand-in for runtime.hull_settings() ([server] table)."""
    return SimpleNamespace(server=SimpleNamespace(host=host, port=port, users_file=None))


@pytest.fixture
def locks_dir(tmp_path, monkeypatch):
    """Redirect the LifecycleLock scan dir into the test tmp tree."""
    d = tmp_path / "locks"
    d.mkdir()
    monkeypatch.setattr(cli, "LOCKS_DIR", d)
    return d


def _write_lock(locks_dir, port: int = 8802, pid: int = 4242):
    lock = locks_dir / f"wet-{port}.lock"
    lock.write_text(f"{pid}\n{port}\ntok\n2026-09-26T00:00:00\n", encoding="utf-8")
    return lock


# ---------------------------------------------------------------------------
# bare invocation / unknown subcommand
# ---------------------------------------------------------------------------


class TestBareInvocation:
    """Bare ``wet`` prints help and returns 0 (the server is `wet server start`)."""

    def test_bare_invocation_prints_help(self, capsys):
        rc = cli.main([])

        assert rc == 0
        out = capsys.readouterr().out
        assert "server" in out
        assert "config" in out

    def test_bare_invocation_does_not_start_server(self, capsys):
        with patch("wet_mcp.server.run_server_blocking") as mock_serve:
            rc = cli.main([])

        mock_serve.assert_not_called()
        assert rc == 0


class TestUnknownSubcommand:
    """argparse rejects unknown subcommands with exit 2."""

    def test_unknown_subcommand_exits_2(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["bogus"])

        assert excinfo.value.code == 2
        assert "invalid choice" in capsys.readouterr().err

    def test_server_requires_action(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["server"])

        assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# wet server start / stop / status
# ---------------------------------------------------------------------------


class TestServerStart:
    def test_foreground_calls_run_server_blocking(self, monkeypatch, capsys):
        monkeypatch.setattr(cli, "_find_locks", lambda port: [])
        with (
            patch("wet_mcp.runtime.hull_settings", return_value=_hs(port=9101)),
            patch("wet_mcp.server.run_server_blocking") as mock_serve,
        ):
            rc = cli.main(["server", "start", "--foreground", "--port", "9101"])

        mock_serve.assert_called_once_with(host=None, port=9101)
        assert rc == 0

    def test_foreground_without_flags_defers_bind_to_server(self, monkeypatch):
        """No --host/--port: the config file decides the bind inside run_server_blocking."""
        monkeypatch.setattr(cli, "_find_locks", lambda port: [])
        with (
            patch("wet_mcp.runtime.hull_settings", return_value=_hs(port=9101)),
            patch("wet_mcp.server.run_server_blocking") as mock_serve,
        ):
            rc = cli.main(["server", "start", "--foreground"])

        mock_serve.assert_called_once_with(host=None, port=None)
        assert rc == 0

    def test_foreground_startup_refusal_reports_error(self, monkeypatch, capsys):
        monkeypatch.setattr(cli, "_find_locks", lambda port: [])
        with (
            patch("wet_mcp.runtime.hull_settings", return_value=_hs()),
            patch(
                "wet_mcp.server.run_server_blocking",
                side_effect=ValueError("no-auth loopback"),
            ),
        ):
            rc = cli.main(["server", "start", "--foreground"])

        assert rc == 1
        assert "wet server failed to start" in capsys.readouterr().err

    def test_detached_spawn_reports_pid_and_port(self, monkeypatch, capsys):
        monkeypatch.setattr(cli, "_find_locks", lambda port: [])
        proc = MagicMock()
        proc.pid = 5555
        proc.wait.side_effect = __import__("subprocess").TimeoutExpired(
            cmd="wet", timeout=2.0
        )
        with (
            patch("wet_mcp.runtime.hull_settings", return_value=_hs(port=9102)),
            patch("wet_mcp.cli._spawn_server", return_value=proc) as mock_spawn,
        ):
            rc = cli.main(["server", "start"])

        mock_spawn.assert_called_once_with(
            "127.0.0.1", 9102, explicit_host=False, explicit_port=False
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "pid=5555" in out
        assert "port=9102" in out

    def test_already_running_lock_blocks_start(self, monkeypatch, capsys, locks_dir):
        lock = _write_lock(locks_dir)
        with (
            patch("wet_mcp.runtime.hull_settings", return_value=_hs()),
            patch("wet_mcp.cli._pid_alive", return_value=True),
            patch("wet_mcp.cli._spawn_server") as mock_spawn,
        ):
            rc = cli.main(["server", "start"])

        mock_spawn.assert_not_called()
        assert rc == 1
        err = capsys.readouterr().err
        assert "already running" in err
        assert str(lock) in err

    def test_spawned_process_exiting_immediately_fails_loudly(
        self, monkeypatch, capsys, tmp_path
    ):
        """A server-side startup refusal must surface the log tail, not a phantom start."""
        monkeypatch.setattr(cli, "_find_locks", lambda port: [])
        proc = MagicMock()
        proc.pid = 5556
        proc.returncode = 1
        proc.wait.return_value = 1
        log_path = tmp_path / "wet-server.log"
        log_path.write_text("boom: bad config\n", encoding="utf-8")
        with (
            patch("wet_mcp.runtime.hull_settings", return_value=_hs()),
            patch("wet_mcp.cli._spawn_server", return_value=proc),
            patch("wet_mcp.cli._server_log_path", return_value=log_path),
        ):
            rc = cli.main(["server", "start"])

        assert rc == 1
        assert "exited immediately" in capsys.readouterr().err


class TestServerStop:
    def test_stop_without_locks_is_a_noop_success(self, capsys, locks_dir):
        rc = cli.main(["server", "stop"])

        assert rc == 0
        assert "not running" in capsys.readouterr().out

    def test_stop_kills_live_pid_and_removes_lock(self, monkeypatch, capsys, locks_dir):
        lock = _write_lock(locks_dir)
        # Alive until terminated, then gone (the wait loop re-checks).
        state = {"terminated": False}
        monkeypatch.setattr(
            cli, "_pid_alive", lambda pid: not state["terminated"]
        )
        monkeypatch.setattr(
            cli, "_terminate", MagicMock(side_effect=lambda pid: state.update(terminated=True))
        )
        rc = cli.main(["server", "stop", "--port", "8802"])

        assert rc == 0
        assert "stopped wet-mcp server" in capsys.readouterr().out
        assert not lock.exists()

    def test_stop_removes_stale_lock(self, monkeypatch, capsys, locks_dir):
        lock = _write_lock(locks_dir)
        monkeypatch.setattr(cli, "_pid_alive", lambda pid: False)
        rc = cli.main(["server", "stop"])

        assert rc == 0
        assert "removed stale lock" in capsys.readouterr().out
        assert not lock.exists()

    def test_stop_removes_malformed_lock(self, monkeypatch, capsys, locks_dir):
        lock = locks_dir / "wet-8803.lock"
        lock.write_text("garbage\n", encoding="utf-8")
        rc = cli.main(["server", "stop"])

        assert rc == 0
        assert "malformed lock" in capsys.readouterr().out
        assert not lock.exists()

    def test_stop_survivor_returns_nonzero(self, monkeypatch, capsys, locks_dir):
        _write_lock(locks_dir)
        monkeypatch.setattr(cli, "_pid_alive", lambda pid: True)
        monkeypatch.setattr(cli, "_terminate", MagicMock())
        monkeypatch.setattr(cli, "_force_kill", MagicMock())
        rc = cli.main(["server", "stop"])

        assert rc == 1
        assert "still alive" in capsys.readouterr().err


class TestServerStatus:
    def test_status_without_lock_probes_config_port(self, monkeypatch, capsys, locks_dir):
        with (
            patch("wet_mcp.runtime.hull_settings", return_value=_hs(port=9103)),
            patch("wet_mcp.cli._http_probe", return_value=False),
        ):
            rc = cli.main(["server", "status"])

        assert rc == 1
        out = capsys.readouterr().out
        assert "lock: none" in out
        assert "port 9103" in out
        assert "down" in out

    def test_status_reports_dead_lock(self, monkeypatch, capsys, locks_dir):
        _write_lock(locks_dir)
        monkeypatch.setattr(cli, "_pid_alive", lambda pid: False)
        monkeypatch.setattr(cli, "_http_probe", lambda port: False)
        rc = cli.main(["server", "status"])

        assert rc == 1
        out = capsys.readouterr().out
        assert "dead" in out
        assert "down" in out

    def test_status_reports_live_server(self, monkeypatch, capsys, locks_dir):
        _write_lock(locks_dir, port=8802, pid=99)
        monkeypatch.setattr(cli, "_pid_alive", lambda pid: True)
        monkeypatch.setattr(cli, "_http_probe", lambda port: True)
        rc = cli.main(["server", "status"])

        assert rc == 0
        out = capsys.readouterr().out
        assert "alive" in out
        assert "up" in out


# ---------------------------------------------------------------------------
# wet config init / get / set / path / show
# ---------------------------------------------------------------------------


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Point wet's instance-config root at the test tmp tree."""
    d = tmp_path / "wet-home"
    d.mkdir()
    monkeypatch.setattr("wet_mcp.runtime.wet_config_dir", lambda: d)
    monkeypatch.setattr("wet_mcp.runtime.wet_config_path", lambda: d / "config.toml")
    return d


class TestConfigCommand:
    def test_init_writes_template(self, capsys, config_dir):
        rc = cli.main(["config", "init"])

        assert rc == 0
        assert (config_dir / "config.toml").is_file()
        assert "wrote" in capsys.readouterr().out

    def test_init_refuses_existing_without_force(self, capsys, config_dir):
        cli.main(["config", "init"])
        rc = cli.main(["config", "init"])

        assert rc == 1
        assert "already exists" in capsys.readouterr().err

    def test_init_force_overwrites(self, capsys, config_dir):
        cli.main(["config", "init"])
        rc = cli.main(["config", "init", "--force"])

        assert rc == 0

    def test_path_prints_config_location(self, capsys, config_dir):
        rc = cli.main(["config", "path"])

        assert rc == 0
        assert str(config_dir / "config.toml") in capsys.readouterr().out

    def test_show_prints_template_when_missing(self, capsys, config_dir):
        rc = cli.main(["config", "show"])

        assert rc == 0
        assert "[server]" in capsys.readouterr().out

    def test_get_returns_value(self, capsys, config_dir):
        cli.main(["config", "init"])
        capsys.readouterr()  # drain the init banner
        rc = cli.main(["config", "get", "server.port"])

        assert rc == 0
        assert capsys.readouterr().out.strip() == "8000"

    def test_get_missing_file_hints_init(self, capsys, config_dir):
        rc = cli.main(["config", "get", "server.port"])

        assert rc == 1
        assert "config init" in capsys.readouterr().err

    def test_get_unknown_key_errors(self, capsys, config_dir):
        cli.main(["config", "init"])
        rc = cli.main(["config", "get", "server.nope"])

        assert rc == 1
        assert "key not found" in capsys.readouterr().err

    def test_set_updates_existing_key(self, capsys, config_dir):
        cli.main(["config", "init"])
        rc = cli.main(["config", "set", "server.port", "9001"])

        assert rc == 0
        data = tomllib.loads((config_dir / "config.toml").read_text(encoding="utf-8"))
        assert data["server"]["port"] == 9001

    def test_set_inserts_key_under_existing_section(self, config_dir):
        cli.main(["config", "init"])
        rc = cli.main(["config", "set", "server.rpm", "120"])

        assert rc == 0
        data = tomllib.loads((config_dir / "config.toml").read_text(encoding="utf-8"))
        assert data["server"]["rpm"] == 120

    def test_set_missing_section_errors(self, capsys, config_dir):
        cli.main(["config", "init"])
        rc = cli.main(["config", "set", "models.nonsense.key", "x"])

        assert rc == 1
        assert "edit the file directly" in capsys.readouterr().err

    def test_set_secret_value_is_not_echoed(self, capsys, config_dir):
        cli.main(["config", "init"])
        rc = cli.main(["config", "set", "models.chat.api_key", "sk-super-secret"])

        assert rc == 0
        out = capsys.readouterr().out
        assert "sk-super-secret" not in out
        assert "***" in out
        data = tomllib.loads((config_dir / "config.toml").read_text(encoding="utf-8"))
        assert data["models"]["chat"]["api_key"] == "sk-super-secret"

    def test_set_scalar_quoting(self, config_dir):
        cli.main(["config", "init"])
        assert cli.main(["config", "set", "server.auth", "token"]) == 0
        data = tomllib.loads((config_dir / "config.toml").read_text(encoding="utf-8"))
        assert data["server"]["auth"] == "token"


# ---------------------------------------------------------------------------
# token / users helpers
# ---------------------------------------------------------------------------


class TestTokenHash:
    def test_prints_storable_hash_never_the_token(self, capsys):
        rc = cli.main(["token", "hash", "my-secret-token"])

        assert rc == 0
        out = capsys.readouterr().out.strip()
        assert "my-secret-token" not in out
        assert out.startswith("scrypt$")


class TestUsersPath:
    def test_default_users_path(self, monkeypatch, capsys, config_dir):
        with patch("wet_mcp.runtime.hull_settings", return_value=_hs()):
            rc = cli.main(["users", "path"])

        assert rc == 0
        assert str(config_dir / "users.toml") in capsys.readouterr().out

    def test_configured_users_file_wins(self, monkeypatch, capsys, tmp_path):
        hs = _hs()
        hs.server.users_file = tmp_path / "custom-users.toml"
        with patch("wet_mcp.runtime.hull_settings", return_value=hs):
            rc = cli.main(["users", "path"])

        assert rc == 0
        assert str(tmp_path / "custom-users.toml") in capsys.readouterr().out


# ---------------------------------------------------------------------------
# wet docs reindex / reembed
# ---------------------------------------------------------------------------


class TestDocsReindexSubcommand:
    """`wet docs reindex <library>` opens a standalone DocsDB."""

    def _patch_docs_db(self, monkeypatch, mock_db):
        monkeypatch.setattr("wet_mcp.db.DocsDB", lambda *a, **k: mock_db)

    def test_reindex_known_library_clears_chunks(self, monkeypatch, capsys, tmp_path):
        mock_db = MagicMock()
        mock_db.get_library.return_value = {"id": "lib-1", "name": "requests"}
        mock_db.get_best_version.return_value = {"id": "ver-1"}
        self._patch_docs_db(monkeypatch, mock_db)

        rc = cli.main(["docs", "reindex", "requests"])

        mock_db.get_library.assert_called_once_with("requests")
        mock_db.get_best_version.assert_called_once_with("lib-1")
        mock_db.clear_version_chunks.assert_called_once_with("ver-1")
        mock_db.reset_version_index.assert_called_once_with("ver-1")
        assert rc == 0
        assert '"status": "cleared"' in capsys.readouterr().out

    def test_reindex_unknown_library_returns_error(self, monkeypatch, capsys):
        mock_db = MagicMock()
        mock_db.get_library.return_value = None
        self._patch_docs_db(monkeypatch, mock_db)

        rc = cli.main(["docs", "reindex", "ghost-lib"])

        mock_db.get_best_version.assert_not_called()
        assert rc == 1
        assert "not found" in capsys.readouterr().out


class TestDocsReembedSubcommand:
    def test_reembed_happy_path(self, monkeypatch, capsys):
        result = {
            "status": "complete",
            "missing": 3,
            "embedded": 3,
            "remaining": 0,
            "model": "openai-spec:embed",
            "dims": 768,
            "vectors_present": 10,
            "chunks_total": 10,
            "db_path": "/tmp/docs.db",
        }
        with patch(
            "wet_mcp.docs_reembed.reembed", new_callable=AsyncMock, return_value=result
        ):
            rc = cli.main(["docs", "reembed", "--dry-run"])

        assert rc == 0
        out = capsys.readouterr().out
        assert "missing:        3" in out
        assert "dims:           768" in out

    def test_reembed_error_returns_nonzero(self, monkeypatch, capsys):
        result = {"status": "error", "reason": "embedding model mismatch"}
        with patch(
            "wet_mcp.docs_reembed.reembed", new_callable=AsyncMock, return_value=result
        ):
            rc = cli.main(["docs", "reembed"])

        assert rc == 1
        assert "model mismatch" in capsys.readouterr().err

    def test_reembed_unconfigured_cell_returns_3(self, monkeypatch, capsys):
        result = {"status": "pending", "reason": "no embed cell configured"}
        with patch(
            "wet_mcp.docs_reembed.reembed", new_callable=AsyncMock, return_value=result
        ):
            rc = cli.main(["docs", "reembed"])

        assert rc == 3
        assert "no embed cell configured" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# wet search (consumer over streamable HTTP) + warmup
# ---------------------------------------------------------------------------


class TestSearchSubcommand:
    def test_connection_failure_hints_server_start(self, monkeypatch, capsys):
        with (
            patch("wet_mcp.runtime.hull_settings", return_value=_hs(port=9104)),
            patch(
                "wet_mcp.cli._post_rpc",
                return_value=(None, None, None, OSError("refused")),
            ),
        ):
            rc = cli.main(["search", "python testing"])

        assert rc == 2
        err = capsys.readouterr().err
        assert "not running" in err
        assert "wet server start" in err


class TestWarmupSubcommand:
    def test_happy_path(self, capsys):
        result = {"status": "ok", "mode": "local", "steps": []}
        with patch(
            "wet_mcp.setup_tool.run_warmup", new_callable=AsyncMock, return_value=result
        ) as mock_warmup:
            rc = cli.main(["warmup"])

        mock_warmup.assert_awaited_once_with()
        assert rc == 0
        assert '"mode": "local"' in capsys.readouterr().out

    def test_error_status_returns_nonzero(self, capsys):
        result = {"status": "error", "steps": []}
        with patch(
            "wet_mcp.setup_tool.run_warmup", new_callable=AsyncMock, return_value=result
        ):
            rc = cli.main(["warmup"])

        assert rc == 1
