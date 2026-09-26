"""Tests for the de-hosted server entry points: build_http_app / run_server_blocking / main.

There is ONE way to run wet-mcp now (spec §3): a single HTTP process with the
MCP endpoint at ``http://host:port/mcp``, authenticated per
``~/.wet/config.toml`` ([server] auth = no-auth | token | multi). The old
stdio-default / ``--http`` / mcp-core ``run_http_server`` dispatch matrix and
the ``PUBLIC_URL`` remote-mode guard are deleted surface and are not exercised.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from hull_core.config.settings import HullSettings, ServerSettings

from wet_mcp import server as srv


def _hs(auth: str = "no-auth", host: str = "127.0.0.1", port: int = 8802):
    return SimpleNamespace(server=SimpleNamespace(auth=auth, host=host, port=port))


def _hull_settings(tmp_path, auth: str = "no-auth") -> HullSettings:
    return HullSettings(config_dir=tmp_path, server=ServerSettings(auth=auth))


# ---------------------------------------------------------------------------
# build_http_app
# ---------------------------------------------------------------------------


class TestBuildHttpApp:
    def test_returns_asgi_app_with_mounted_mcp(self, tmp_path):
        from starlette.applications import Starlette
        from starlette.routing import Mount

        app = srv.build_http_app(_hull_settings(tmp_path))

        # Starlette application wrapping the MCP streamable-HTTP app behind
        # the hull auth middleware, mounted at the root.
        assert isinstance(app, Starlette)
        assert any(isinstance(r, Mount) for r in app.routes)

    def test_default_settings_loaded_from_instance_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "wet_mcp.runtime.hull_settings",
            lambda: _hull_settings(tmp_path),
        )
        app = srv.build_http_app(None)

        assert hasattr(app, "routes")

    def test_auth_mode_from_settings_reaches_authenticator(self, tmp_path):
        """token/multi settings build an app too (authenticator accepts them)."""
        from hull_core.auth.tokens import hash_token

        users_file = tmp_path / "users.toml"
        users_file.write_text(
            "[users.alice]\n"
            f'token_hash = "{hash_token("alice-token")}"\n'
            "enabled = true\nnamespace = \"alice\"\n",
            encoding="utf-8",
        )
        multi = HullSettings(
            config_dir=tmp_path,
            server=ServerSettings(auth="multi", users_file=users_file),
        )
        for settings in (_hull_settings(tmp_path, auth="token"), multi):
            app = srv.build_http_app(settings)
            assert hasattr(app, "routes")


# ---------------------------------------------------------------------------
# run_server_blocking
# ---------------------------------------------------------------------------


class TestRunServerBlocking:
    def test_no_auth_non_loopback_bind_refused(self, monkeypatch):
        """An unauthenticated listener must never leave localhost."""
        monkeypatch.setattr("wet_mcp.runtime.hull_settings", lambda: _hs(auth="no-auth"))

        with pytest.raises(srv.ServerConfigError, match="no-auth"):
            srv.run_server_blocking(host="0.0.0.0", port=8802)

    def test_serves_uvicorn_on_requested_bind(self, monkeypatch, tmp_path):
        hs = _hs(auth="no-auth", host="127.0.0.1", port=8803)
        monkeypatch.setattr("wet_mcp.runtime.hull_settings", lambda: hs)

        lock_cm = MagicMock()
        lock_obj = MagicMock()
        lock_obj.__enter__.return_value = lock_obj
        lock_obj.__exit__.return_value = False
        lock_cm.return_value = lock_obj

        with (
            patch("hull_core.lifecycle.lock.LifecycleLock", lock_cm),
            patch("wet_mcp.server.build_http_app", return_value=MagicMock()) as mock_app,
            patch("uvicorn.run") as mock_uvicorn,
        ):
            srv.run_server_blocking(host="127.0.0.1", port=8803)

        lock_cm.assert_called_once_with("wet", 8803)
        mock_app.assert_called_once_with(hs)
        mock_uvicorn.assert_called_once()
        _, kwargs = mock_uvicorn.call_args
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8803

    def test_token_auth_allows_non_loopback(self, monkeypatch):
        """A shared bind requires token/multi auth — and is then allowed."""
        hs = _hs(auth="token", host="0.0.0.0", port=8804)
        monkeypatch.setattr("wet_mcp.runtime.hull_settings", lambda: hs)

        lock_obj = MagicMock()
        lock_obj.__enter__.return_value = lock_obj
        lock_obj.__exit__.return_value = False
        lock_factory = MagicMock(return_value=lock_obj)

        with (
            patch("hull_core.lifecycle.lock.LifecycleLock", lock_factory),
            patch("wet_mcp.server.build_http_app", return_value=MagicMock()),
            patch("uvicorn.run") as mock_uvicorn,
        ):
            srv.run_server_blocking(host="0.0.0.0", port=8804)

        _, kwargs = mock_uvicorn.call_args
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 8804

    def test_defaults_come_from_instance_config(self, monkeypatch):
        """host/port None -> [server].host/port from ~/.wet/config.toml."""
        hs = _hs(auth="no-auth", host="127.0.0.1", port=9310)
        monkeypatch.setattr("wet_mcp.runtime.hull_settings", lambda: hs)

        lock_obj = MagicMock()
        lock_obj.__enter__.return_value = lock_obj
        lock_obj.__exit__.return_value = False
        lock_factory = MagicMock(return_value=lock_obj)

        with (
            patch("hull_core.lifecycle.lock.LifecycleLock", lock_factory),
            patch("wet_mcp.server.build_http_app", return_value=MagicMock()),
            patch("uvicorn.run") as mock_uvicorn,
        ):
            srv.run_server_blocking()

        lock_factory.assert_called_once_with("wet", 9310)
        _, kwargs = mock_uvicorn.call_args
        assert kwargs["port"] == 9310


class TestIsLoopbackHost:
    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("127.0.0.1", True),
            ("localhost", True),
            ("::1", True),
            ("[::1]", True),
            ("127.9.9.9", True),
            ("0.0.0.0", False),
            ("192.168.1.10", False),
            ("wet.example.com", False),
        ],
    )
    def test_classification(self, host, expected):
        assert srv._is_loopback_host(host) is expected


# ---------------------------------------------------------------------------
# module main(): env-var bind overrides for container deployments
# ---------------------------------------------------------------------------


class TestMainDispatch:
    def test_no_env_defers_to_instance_config(self, monkeypatch):
        monkeypatch.delenv("WET_HOST", raising=False)
        monkeypatch.delenv("WET_PORT", raising=False)
        with patch("wet_mcp.server.run_server_blocking") as mock_serve:
            srv.main()

        mock_serve.assert_called_once_with(host=None, port=None)

    def test_wet_host_and_wet_port_override_bind(self, monkeypatch):
        monkeypatch.setenv("WET_HOST", "0.0.0.0")
        monkeypatch.setenv("WET_PORT", "8080")
        with patch("wet_mcp.server.run_server_blocking") as mock_serve:
            srv.main()

        mock_serve.assert_called_once_with(host="0.0.0.0", port=8080)

    def test_wet_port_only_pins_port(self, monkeypatch):
        monkeypatch.delenv("WET_HOST", raising=False)
        monkeypatch.setenv("WET_PORT", "9090")
        with patch("wet_mcp.server.run_server_blocking") as mock_serve:
            srv.main()

        mock_serve.assert_called_once_with(host=None, port=9090)

    def test_invalid_wet_port_fails_loudly(self, monkeypatch):
        """A typo'd WET_PORT aborts startup instead of silently auto-porting."""
        monkeypatch.setenv("WET_PORT", "not-a-port")
        with patch("wet_mcp.server.run_server_blocking") as mock_serve:
            with pytest.raises(ValueError, match="not-a-port"):
                srv.main()

        mock_serve.assert_not_called()
