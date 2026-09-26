"""Comprehensive unit tests to increase coverage across multiple modules.

Targets uncovered lines in:
- searxng_runner.py: process management, config, health checks, restart logic
- searxng.py: unhealthy restart path, URL dedup merge logic
- crawler.py: markitdown errors, _detect_document_content_type, _get_crawler retry
- embedder.py: cloud backend fallback, ONNX model loading errors
- llm.py: error handling paths
- reranker.py: cloud reranker fallback paths
"""

import asyncio
import json
import signal
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# -----------------------------------------------------------------------
# searxng_runner.py coverage
# -----------------------------------------------------------------------


class TestIsPidAliveWindows:
    """Cover lines 115-124: Windows ctypes branch."""

    async def test_is_pid_alive_windows_handle_found(self):
        from web_core.search.runner import _is_pid_alive

        mock_kernel32 = MagicMock()
        mock_kernel32.OpenProcess.return_value = 12345
        mock_kernel32.CloseHandle.return_value = None

        mock_windll = MagicMock()
        mock_windll.kernel32 = mock_kernel32

        with (
            patch("sys.platform", "win32"),
            patch("web_core.search.runner.sys") as mock_sys_mod,
        ):
            mock_sys_mod.platform = "win32"
            # We need to actually import ctypes in the function,
            # so we patch ctypes.windll

            with patch.dict("sys.modules", {"ctypes": MagicMock(windll=mock_windll)}):
                # The function checks sys.platform at module import level
                # Re-import to get fresh check
                pass

        # Alternative: directly test the logic
        # On linux, test the unix path (already covered), so test windows with mock
        with patch("web_core.search.runner.sys") as mock_sys:
            mock_sys.platform = "win32"
            # Mock the ctypes import inside the function
            mock_ctypes = MagicMock()
            mock_ctypes.windll.kernel32.OpenProcess.return_value = 42
            with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
                result = _is_pid_alive(1234)
                assert result is True
                mock_ctypes.windll.kernel32.CloseHandle.assert_called_once_with(42)

    async def test_is_pid_alive_windows_handle_not_found(self):
        from web_core.search.runner import _is_pid_alive

        with patch("web_core.search.runner.sys") as mock_sys:
            mock_sys.platform = "win32"
            mock_ctypes = MagicMock()
            mock_ctypes.windll.kernel32.OpenProcess.return_value = 0
            with patch.dict("sys.modules", {"ctypes": mock_ctypes}):
                result = _is_pid_alive(5678)
                assert result is False


class TestWriteDiscoveryFailure:
    """Cover lines 161-162: _write_discovery exception path."""

    async def test_write_discovery_exception_logged(self):
        from web_core.search.runner import _write_discovery

        with patch(
            "web_core.search.runner._DISCOVERY_FILE",
        ) as mock_file:
            mock_file.parent.mkdir.side_effect = PermissionError("denied")
            # Should not raise
            _write_discovery(8080, 1234)


class TestRemoveDiscoveryExceptionPath:
    """Cover lines 170-171: _remove_discovery exception path."""

    async def test_remove_discovery_exception_suppressed(self):
        from web_core.search.runner import _remove_discovery

        with patch("web_core.search.runner._DISCOVERY_FILE") as mock_file:
            mock_file.exists.side_effect = PermissionError("denied")
            # Should not raise
            _remove_discovery()


class TestQuickHealthCheckRetryBackoff:
    """Cover line 198: asyncio.sleep in retry backoff."""

    async def test_health_check_retries_with_backoff(self):
        from web_core.search.runner import _quick_health_check

        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("connection refused")

        class MockClientCM:
            async def __aenter__(self):
                return mock_client

            async def __aexit__(self, *args):
                pass

        with (
            patch("httpx.AsyncClient", return_value=MockClientCM()),
            patch(
                "web_core.search.runner.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
        ):
            result = await _quick_health_check("http://localhost:8080", retries=3)
            assert result is False
            # Should have slept between retries: 0.5, 1.0
            assert mock_sleep.call_count == 2


class TestTryReuseExistingMissingFields:
    """Cover line 215: missing port or pid in discovery data."""

    async def test_try_reuse_missing_port(self):
        from web_core.search.runner import _try_reuse_existing

        with patch(
            "web_core.search.runner._read_discovery",
            return_value={"pid": 1234},
        ):
            result = await _try_reuse_existing()
            assert result is None

    async def test_try_reuse_missing_pid(self):
        from web_core.search.runner import _try_reuse_existing

        with patch(
            "web_core.search.runner._read_discovery",
            return_value={"port": 8080},
        ):
            result = await _try_reuse_existing()
            assert result is None


class TestWaitForServiceTimeout:
    """Cover lines 282-285: _wait_for_service timeout loop with sleep."""

    async def test_wait_for_service_retries_then_fails(self):
        from web_core.search.runner import _wait_for_service

        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("connection refused")

        class MockClientCM:
            async def __aenter__(self):
                return mock_client

            async def __aexit__(self, *args):
                pass

        call_count = 0

        async def fake_sleep(t):
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                raise asyncio.CancelledError

        with (
            patch("httpx.AsyncClient", return_value=MockClientCM()),
            patch("web_core.search.runner.asyncio.sleep", side_effect=fake_sleep),
            patch("web_core.search.runner.time") as mock_time,
        ):
            # Make time.time() return increasing values to eventually time out
            mock_time.time.side_effect = [0.0, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0]
            try:
                await _wait_for_service("http://localhost:8080", timeout=2.0)
            except asyncio.CancelledError:
                pass  # Expected


class TestIsSearchInstalled:
    """Cover lines 299-300: ModuleNotFoundError path."""

    async def test_is_searxng_installed_module_not_found(self):
        from web_core.search.runner import _is_searxng_installed

        with patch("importlib.util.find_spec", side_effect=ModuleNotFoundError):
            assert _is_searxng_installed() is False


class TestInstallSearxngPaths:
    """Cover lines 358-359, 364-366: install failure and exception paths."""

    async def test_install_searxng_deps_fail(self):
        from web_core.search.runner import _install_searxng

        with (
            patch("web_core.search.runner._get_pip_command", return_value=["pip"]),
            patch("subprocess.run") as mock_run,
        ):
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "deps failed"
            mock_run.return_value = mock_result
            assert _install_searxng() is False

    async def test_install_searxng_general_exception(self):
        from web_core.search.runner import _install_searxng

        with patch(
            "web_core.search.runner._get_pip_command",
            side_effect=RuntimeError("unexpected"),
        ):
            assert _install_searxng() is False


@pytest.mark.skipif(
    sys.platform == "win32", reason="SIGKILL/SIGTERM unavailable on Windows"
)
class TestSigtermThenKill:
    """Cover lines 410-411, 420-430: _sigterm_then_kill edge cases."""

    async def test_sigterm_already_dead(self):
        from web_core.search.runner import _sigterm_then_kill

        with patch("os.kill", side_effect=ProcessLookupError):
            result = await _sigterm_then_kill(9999, "test")
            assert result is True

    async def test_sigterm_permission_error_on_kill(self):
        from web_core.search.runner import _sigterm_then_kill

        with patch("os.kill", side_effect=PermissionError):
            result = await _sigterm_then_kill(9999, "test")
            assert result is True

    async def test_sigterm_graceful_exit_after_check(self):
        from web_core.search.runner import _sigterm_then_kill

        call_count = 0

        def kill_side_effect(pid, sig):
            nonlocal call_count
            if sig == signal.SIGTERM:
                return None  # SIGTERM sent
            if sig == 0:
                call_count += 1
                if call_count >= 2:
                    raise ProcessLookupError  # Process died
                return None  # Still alive

        with patch("os.kill", side_effect=kill_side_effect), patch("asyncio.sleep"):
            result = await _sigterm_then_kill(1234)
            assert result is True

    async def test_sigterm_permission_error_on_check(self):
        """Cover line 420-421: PermissionError on alive check."""
        from web_core.search.runner import _sigterm_then_kill

        call_count = 0

        def kill_side_effect(pid, sig):
            nonlocal call_count
            if sig == signal.SIGTERM:
                return None
            if sig == 0:
                raise PermissionError  # Can't check, treat as done
            return None

        with patch("os.kill", side_effect=kill_side_effect), patch("asyncio.sleep"):
            result = await _sigterm_then_kill(1234)
            assert result is True

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Unix-only: requires SIGKILL/killpg/getpgid",
    )
    async def test_sigterm_force_kill_needed(self):
        """Cover lines 424-430: needs SIGKILL after timeout."""
        from web_core.search.runner import _sigterm_then_kill

        def kill_side_effect(pid, sig):
            if sig == signal.SIGTERM:
                return None
            if sig == 0:
                return None  # Always alive, never exits
            if sig == signal.SIGKILL:
                return None  # SIGKILL succeeds

        with patch("os.kill", side_effect=kill_side_effect), patch("asyncio.sleep"):
            result = await _sigterm_then_kill(1234, "test-proc")
            assert result is True

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Unix-only: requires SIGKILL/killpg/getpgid",
    )
    async def test_sigterm_force_kill_already_dead(self):
        """Cover line 429-430: ProcessLookupError on SIGKILL."""
        from web_core.search.runner import _sigterm_then_kill

        def kill_side_effect(pid, sig):
            if sig == signal.SIGTERM:
                return None
            if sig == 0:
                return None  # Always alive
            if sig == signal.SIGKILL:
                raise ProcessLookupError  # Already dead

        with patch("os.kill", side_effect=kill_side_effect), patch("asyncio.sleep"):
            result = await _sigterm_then_kill(1234)
            assert result is True


@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix process group APIs unavailable on Windows"
)
class TestForceKillProcess:
    """Cover lines 440, 450-451, 462-463, 467-476."""

    async def test_force_kill_already_dead(self):
        """Cover line 440: process already dead."""
        from web_core.search.runner import _force_kill_process

        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = 0  # Already dead
        await _force_kill_process(proc)  # Should return immediately

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Unix-only: requires SIGKILL/killpg/getpgid",
    )
    async def test_force_kill_unix_killpg_fails_falls_back(self):
        """Cover lines 450-451: killpg fails, falls back to proc.terminate."""
        from web_core.search.runner import _force_kill_process

        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.pid = 1234
        proc.wait.return_value = None

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("os.killpg", side_effect=ProcessLookupError),
            patch("os.getpgid", return_value=1234),
        ):
            mock_sys.platform = "linux"
            await _force_kill_process(proc)
            proc.terminate.assert_called_once()

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Unix-only: requires SIGKILL/killpg/getpgid",
    )
    async def test_force_kill_unix_sigkill_fallback(self):
        """Cover lines 462-463: SIGKILL killpg fails, falls back to proc.kill."""
        from web_core.search.runner import _force_kill_process

        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.pid = 1234
        proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="test", timeout=3),
            None,
        ]

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("os.getpgid", return_value=1234),
        ):
            mock_sys.platform = "linux"
            call_count = 0

            def killpg_side_effect(pgid, sig):
                nonlocal call_count
                call_count += 1
                if sig == signal.SIGKILL:
                    raise PermissionError("denied")

            with patch("os.killpg", side_effect=killpg_side_effect):
                await _force_kill_process(proc)
                proc.kill.assert_called_once()

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Unix-only: requires SIGKILL/killpg/getpgid",
    )
    async def test_force_kill_unix_cannot_kill(self):
        """Cover lines 467-468: process cannot be killed."""
        from web_core.search.runner import _force_kill_process

        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.pid = 1234
        proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=3)

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("os.killpg"),
            patch("os.getpgid", return_value=1234),
        ):
            mock_sys.platform = "linux"
            await _force_kill_process(proc)  # Should log warning but not crash

    async def test_force_kill_windows_path(self):
        """Cover lines 469-474: Windows path."""
        from web_core.search.runner import _force_kill_process

        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.pid = 1234
        proc.wait.return_value = None

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("web_core.search.runner._sigterm_then_kill", return_value=True),
        ):
            mock_sys.platform = "win32"
            await _force_kill_process(proc)

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Unix-only: requires SIGKILL/killpg/getpgid",
    )
    async def test_force_kill_general_exception(self):
        """Cover lines 475-476: general exception in force kill."""
        from web_core.search.runner import _force_kill_process

        proc = MagicMock(spec=subprocess.Popen)
        proc.poll.return_value = None
        proc.pid = 1234

        with patch("web_core.search.runner.sys") as mock_sys:
            mock_sys.platform = "linux"
            with patch("os.killpg", side_effect=RuntimeError("unexpected")):
                with patch("os.getpgid", return_value=1234):
                    await _force_kill_process(proc)  # Should not crash


class TestKillStalePortProcess:
    """Cover lines 503-506, 523-537: stale port process edge cases."""

    async def test_kill_stale_port_windows_exception(self):
        """Cover lines 503-506: Windows netstat exception."""
        from web_core.search.runner import _kill_stale_port_process

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("subprocess.run", side_effect=RuntimeError("netstat failed")),
        ):
            mock_sys.platform = "win32"
            await _kill_stale_port_process(8080)  # Should not crash

    async def test_kill_stale_port_windows_invalid_pid(self):
        """Cover lines 503: ValueError on pid parse."""
        from web_core.search.runner import _kill_stale_port_process

        mock_result = MagicMock()
        mock_result.stdout = "  TCP    127.0.0.1:8080         0.0.0.0:0              LISTENING       notapid\n"

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("subprocess.run", return_value=mock_result),
        ):
            mock_sys.platform = "win32"
            await _kill_stale_port_process(8080)  # Should not crash

    async def test_kill_stale_port_unix_lsof_not_found_fuser_fallback(self):
        """Cover lines 525-534: lsof not found, falls back to fuser."""
        from web_core.search.runner import _kill_stale_port_process

        call_count = 0

        def run_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise FileNotFoundError("lsof not found")
            # fuser call
            return MagicMock(returncode=0)

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            mock_sys.platform = "linux"
            await _kill_stale_port_process(8080)

    async def test_kill_stale_port_unix_lsof_not_found_fuser_not_found(self):
        """Cover lines 534: both lsof and fuser not found."""
        from web_core.search.runner import _kill_stale_port_process

        def run_side_effect(*args, **kwargs):
            raise FileNotFoundError("command not found")

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            mock_sys.platform = "linux"
            await _kill_stale_port_process(8080)  # Should not crash

    async def test_kill_stale_port_unix_general_exception(self):
        """Cover lines 536-537: general exception on lsof."""
        from web_core.search.runner import _kill_stale_port_process

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("subprocess.run", side_effect=RuntimeError("unexpected")),
        ):
            mock_sys.platform = "linux"
            await _kill_stale_port_process(8080)  # Should not crash

    async def test_kill_stale_port_unix_invalid_pid(self):
        """Cover lines 523: ValueError on pid parse from lsof."""
        from web_core.search.runner import _kill_stale_port_process

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "notanumber\n"

        with (
            patch("web_core.search.runner.sys") as mock_sys,
            patch("subprocess.run", return_value=mock_result),
        ):
            mock_sys.platform = "linux"
            await _kill_stale_port_process(8080)  # Should not crash


class TestCleanupProcessSettingsFile:
    """Cover lines 553-554, 567-569: settings file cleanup."""

    async def test_cleanup_process_settings_file(self, tmp_path):
        import web_core.search.runner as module

        module._searxng_process = None

        pid_settings = tmp_path / f"searxng_settings_{__import__('os').getpid()}.yml"
        pid_settings.write_text("test")

        with patch("web_core.search.runner._CONFIG_DIR", tmp_path):
            module._cleanup_process()

    async def test_cleanup_process_settings_file_exception(self):
        import web_core.search.runner as module

        module._searxng_process = None

        mock_config_dir = MagicMock()
        mock_config_dir.__truediv__ = MagicMock(side_effect=RuntimeError("error"))

        with patch("web_core.search.runner._CONFIG_DIR", mock_config_dir):
            module._cleanup_process()  # Should not crash


class TestHandleRestartCrashDiagnostics:
    """Cover lines 747-748: stderr read exception during crash diagnostics."""

    async def test_crash_stderr_read_exception(self):
        import web_core.search.runner as module
        from web_core.search.runner import _handle_restart_and_start

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # Crashed
        mock_proc.stderr.read.side_effect = Exception("read error")
        module._searxng_process = mock_proc
        module._restart_count = 0
        module._last_restart_time = 0.0

        expected_url = "http://127.0.0.1:8080"
        with (
            patch("web_core.search.runner._is_searxng_installed", return_value=True),
            # web-core 1.2.0 tries Docker before subprocess; disable it so
            # _start_searxng_subprocess is reached and returns a known URL.
            # Use create=True so the patch is a no-op on web-core 1.1.0
            # where the Docker path does not exist.
            patch(
                "web_core.search.runner._start_docker_searxng",
                AsyncMock(return_value=None),
                create=True,
            ),
            patch(
                "web_core.search.runner._start_searxng_subprocess",
                AsyncMock(return_value=expected_url),
            ),
        ):
            url = await _handle_restart_and_start(start_port=8080)
            assert url == expected_url


# -----------------------------------------------------------------------
# searxng.py coverage
# -----------------------------------------------------------------------


class TestEnsureSearxngHealthyUnhealthy:
    """Cover lines 46-59: unhealthy path with restart attempt."""

    async def test_unhealthy_triggers_restart(self):
        from wet_mcp.sources.searxng import _ensure_searxng_healthy

        # First health check fails, restart succeeds, second health check succeeds
        mock_ensure = AsyncMock(return_value="http://127.0.0.1:9090")
        with (
            patch(
                "wet_mcp.sources.searxng._check_health",
                side_effect=[False, True],
            ),
            patch(
                "wet_mcp.searxng_runner.ensure_searxng",
                mock_ensure,
            ),
        ):
            result = await _ensure_searxng_healthy("http://localhost:8080")
            assert result == "http://127.0.0.1:9090"

    async def test_unhealthy_restart_still_unhealthy(self):
        from wet_mcp.sources.searxng import _ensure_searxng_healthy

        # Both health checks fail
        mock_ensure = AsyncMock(return_value="http://127.0.0.1:9090")
        with (
            patch(
                "wet_mcp.sources.searxng._check_health",
                side_effect=[False, False],
            ),
            patch(
                "wet_mcp.searxng_runner.ensure_searxng",
                mock_ensure,
            ),
        ):
            result = await _ensure_searxng_healthy("http://localhost:8080")
            assert result == "http://127.0.0.1:9090"

    async def test_healthy_no_restart(self):
        from wet_mcp.sources.searxng import _ensure_searxng_healthy

        with patch(
            "wet_mcp.sources.searxng._check_health",
            return_value=True,
        ):
            result = await _ensure_searxng_healthy("http://localhost:8080")
            assert result == "http://localhost:8080"


class TestCheckHealth:
    """Cover _check_health success and exception paths."""

    async def test_check_health_success(self):
        from wet_mcp.sources.searxng import _check_health

        with patch("wet_mcp.sources.searxng.httpx.AsyncClient") as mock_client_cls:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await _check_health("http://localhost:8080")
            assert result is True

    async def test_check_health_exception(self):
        from wet_mcp.sources.searxng import _check_health

        with patch("wet_mcp.sources.searxng.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("connection refused")
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
            result = await _check_health("http://localhost:8080")
            assert result is False


class TestSearchDedup:
    """Cover lines 134-143: URL dedup merge logic with multiple engines."""

    async def test_search_dedup_merges_engines_and_keeps_longer_snippet(self):
        import unittest.mock

        from wet_mcp.sources.searxng import search

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "url": "https://example.com",
                    "title": "Short Title",
                    "content": "Short",
                    "engine": "google",
                },
                {
                    "url": "https://example.com",
                    "title": "Better Title",
                    "content": "This is a much longer snippet with more detail",
                    "engine": "bing",
                },
                {
                    "url": "https://example.com",
                    "title": "",
                    "content": "Medium snippet here",
                    "engine": "google",  # Duplicate engine, should not be appended
                },
            ]
        }

        mock_context = AsyncMock()
        mock_context.get.return_value = mock_response
        mock_context.__aenter__.return_value = mock_context

        with (
            unittest.mock.patch(
                "wet_mcp.sources.searxng._ensure_searxng_healthy",
                new_callable=AsyncMock,
                side_effect=lambda url: url,
            ),
            unittest.mock.patch(
                "wet_mcp.sources.searxng.httpx.AsyncClient",
                return_value=mock_context,
            ),
        ):
            result = await search(
                searxng_url="http://localhost:8080",
                query="dedup_test",
                max_results=10,
            )

        data = json.loads(result)
        assert data["total"] == 1
        r = data["results"][0]
        # Should have merged engines
        assert "google" in r["source"]
        assert "bing" in r["source"]
        # Should keep the longest snippet
        assert r["snippet"] == "This is a much longer snippet with more detail"
        # Title should be from the longer snippet entry
        assert r["title"] == "Better Title"


# -----------------------------------------------------------------------
# crawler.py coverage
# -----------------------------------------------------------------------


class TestDetectDocumentContentType:
    """Cover lines 175-184: _detect_document_content_type."""

    async def test_pdf_content_type(self):
        from wet_mcp.sources.crawler import _detect_document_content_type

        assert _detect_document_content_type("application/pdf") is True

    async def test_docx_content_type(self):
        from wet_mcp.sources.crawler import _detect_document_content_type

        assert (
            _detect_document_content_type(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            is True
        )

    async def test_pptx_content_type(self):
        from wet_mcp.sources.crawler import _detect_document_content_type

        assert (
            _detect_document_content_type(
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )
            is True
        )

    async def test_xlsx_content_type(self):
        from wet_mcp.sources.crawler import _detect_document_content_type

        assert (
            _detect_document_content_type(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            is True
        )

    async def test_msword_content_type(self):
        from wet_mcp.sources.crawler import _detect_document_content_type

        assert _detect_document_content_type("application/msword") is True

    async def test_ms_powerpoint_content_type(self):
        from wet_mcp.sources.crawler import _detect_document_content_type

        assert _detect_document_content_type("application/vnd.ms-powerpoint") is True

    async def test_ms_excel_content_type(self):
        from wet_mcp.sources.crawler import _detect_document_content_type

        assert _detect_document_content_type("application/vnd.ms-excel") is True

    async def test_non_document_content_type(self):
        from wet_mcp.sources.crawler import _detect_document_content_type

        assert _detect_document_content_type("text/html") is False

    async def test_empty_content_type(self):
        from wet_mcp.sources.crawler import _detect_document_content_type

        assert _detect_document_content_type("") is False


class TestExtractWithMarkitdown:
    """Cover lines 189-217: _extract_with_markitdown error paths."""

    async def test_markitdown_import_error(self):
        from wet_mcp.sources.crawler import _extract_with_markitdown

        with patch.dict("sys.modules", {"markitdown": None}):
            with patch("builtins.__import__", side_effect=ImportError("no markitdown")):
                result = await _extract_with_markitdown("https://example.com/doc.pdf")
                assert "error" in result
                assert "markitdown not installed" in result["error"]

    async def test_markitdown_conversion_error(self):
        from wet_mcp.sources.crawler import _extract_with_markitdown

        mock_md = MagicMock()
        mock_md_cls = MagicMock(return_value=mock_md)
        mock_md.convert_stream.side_effect = Exception("conversion failed")

        mock_response = MagicMock()
        mock_response.content = b"fake pdf content"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.dict(
                "sys.modules", {"markitdown": MagicMock(MarkItDown=mock_md_cls)}
            ),
        ):
            result = await _extract_with_markitdown("https://example.com/doc.pdf")
            assert "error" in result
            assert "Document conversion failed" in result["error"]

    async def test_markitdown_http_error(self):
        from wet_mcp.sources.crawler import _extract_with_markitdown

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_md_cls = MagicMock()

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.dict(
                "sys.modules", {"markitdown": MagicMock(MarkItDown=mock_md_cls)}
            ),
        ):
            result = await _extract_with_markitdown("https://example.com/doc.pdf")
            assert "error" in result


class TestGetCrawlerRetryOnFailure:
    """Cover line 143: RuntimeError after browser start retry fails."""

    async def test_get_crawler_retry_exhausted(self):
        import wet_mcp.sources.crawler as crawler_mod
        from wet_mcp.sources.crawler import _get_crawler

        crawler_mod._crawler_instance = None

        mock_crawler = MagicMock()
        mock_crawler.__aenter__ = AsyncMock(side_effect=RuntimeError("browser failed"))

        with (
            patch("wet_mcp.sources.crawler.AsyncWebCrawler", return_value=mock_crawler),
            patch("wet_mcp.sources.crawler._cleanup_browser_data_dir"),
        ):
            with pytest.raises(RuntimeError, match="browser failed"):
                await _get_crawler()


class TestExtractDocumentUrl:
    """Cover line 270-271: document URL routing in extract."""

    async def test_extract_routes_document_to_markitdown(self):
        from wet_mcp.sources.crawler import extract

        mock_crawler = AsyncMock()

        with (
            patch(
                "wet_mcp.sources.crawler._get_crawler",
                new_callable=AsyncMock,
                return_value=mock_crawler,
            ),
            patch(
                "wet_mcp.sources.crawler._extract_with_markitdown",
                new_callable=AsyncMock,
                return_value={
                    "url": "https://example.com/doc.pdf",
                    "title": "doc",
                    "content": "pdf content",
                    "converter": "markitdown",
                },
            ) as mock_markitdown,
        ):
            result_json = await extract(urls=["https://example.com/doc.pdf"])

        results = json.loads(result_json)
        assert len(results) == 1
        assert results[0]["converter"] == "markitdown"
        mock_markitdown.assert_called_once()


class TestCrawlSkipsVisitedAndDepth:
    """Cover lines 353, 437: visited/depth skip in crawl/sitemap."""

    async def test_sitemap_skips_visited_urls(self):
        from wet_mcp.sources.crawler import sitemap

        mock_crawler = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.links = {"internal": [{"href": "https://example.com/page1"}]}
        mock_crawler.arun = AsyncMock(return_value=mock_result)

        with patch(
            "wet_mcp.sources.crawler._get_crawler",
            new_callable=AsyncMock,
            return_value=mock_crawler,
        ):
            result_json = await sitemap(
                urls=["https://example.com"], depth=1, max_pages=50
            )

        results = json.loads(result_json)
        urls = [r["url"] for r in results]
        assert "https://example.com" in urls


class TestExtractErrorPath:
    """Cover the error branch in extract.process_url after ScrapingAgent migration."""

    async def test_extract_crawl_error(self):
        from wet_mcp.sources.crawler import extract

        agent = MagicMock()
        agent.scrape = AsyncMock(side_effect=RuntimeError("browser crash"))
        agent.strategy_cache = MagicMock()
        agent.strategy_cache.recommend = AsyncMock(return_value=["basic_http"])

        with patch(
            "wet_mcp.sources.crawler._get_scraping_agent",
            new_callable=AsyncMock,
            return_value=agent,
        ):
            result_json = await extract(urls=["https://example.com"])

        results = json.loads(result_json)
        assert len(results) == 1
        assert "error" in results[0]
        assert "browser crash" in results[0]["error"]


# -----------------------------------------------------------------------
# embedder.py coverage
# -----------------------------------------------------------------------


def _stub_embed_client(model: str = "text-embedding-3-large"):
    """A stub hull OpenAI-spec client for the embed cell."""
    client = MagicMock()
    client.cell.model = model
    client.embeddings = AsyncMock()
    return client


class TestCloudEmbeddingBackendCheckAvailableEmpty:
    """Cover check_available returns 0 when embeddings are empty."""

    async def test_check_available_empty_data(self):
        from wet_mcp.embedder import CloudEmbeddingBackend

        client = _stub_embed_client()
        client.embeddings.return_value = []
        backend = CloudEmbeddingBackend(client)

        assert await backend.check_available() == 0


class TestCloudEmbeddingBackendCellOwned:
    """The cell owns model/base_url/key; the backend reads the model id."""

    async def test_embed_reads_model_from_cell_and_returns_vectors(self):
        from wet_mcp.embedder import CloudEmbeddingBackend

        client = _stub_embed_client("text-embedding-3-large")
        client.embeddings.return_value = [[0.1]]
        backend = CloudEmbeddingBackend(client)

        assert backend.model == "text-embedding-3-large"
        assert await backend.embed_texts(["test"]) == [[0.1]]

    async def test_check_available_reports_native_dims(self):
        from wet_mcp.embedder import CloudEmbeddingBackend

        client = _stub_embed_client()
        client.embeddings.return_value = [[0.1, 0.2]]
        backend = CloudEmbeddingBackend(client)

        assert await backend.check_available() == 2


class TestLocalEmbeddingBackendLoadError:
    """Cover lines 262-272: _get_model import error and lazy loading."""

    async def test_get_model_import_error(self):
        from wet_mcp.embedder import LocalEmbeddingBackend

        backend = LocalEmbeddingBackend()
        with patch.dict("sys.modules", {"fastretrieval": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("No module named 'fastretrieval'"),
            ):
                with pytest.raises(ImportError):
                    backend._get_model()

    async def test_get_model_caches(self):
        from wet_mcp.embedder import LocalEmbeddingBackend

        backend = LocalEmbeddingBackend("test-model")
        mock_text_embedding = MagicMock()
        mock_module = MagicMock()
        mock_module.TextEmbedding = mock_text_embedding

        with patch.dict("sys.modules", {"fastretrieval": mock_module}):
            model1 = backend._get_model()
            model2 = backend._get_model()
            assert model1 is model2
            # TextEmbedding should only be called once
            mock_text_embedding.assert_called_once()


class TestLocalEmbedCheckAvailableEmptyResult:
    """Cover line 324: check_available returns 0 when result is empty."""

    async def test_check_available_empty_result(self):
        from wet_mcp.embedder import LocalEmbeddingBackend

        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([])

        with patch.object(backend, "_get_model", return_value=mock_model):
            dims = await backend.check_available()
            assert dims == 0


class TestLocalEmbedSingleQuery:
    """Cover lines 306-311: embed_single_query with dimensions."""

    async def test_embed_single_query_with_dims(self):
        import numpy as np

        from wet_mcp.embedder import LocalEmbeddingBackend

        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.query_embed.return_value = iter([np.array([0.1, 0.2, 0.3])])

        with patch.object(backend, "_get_model", return_value=mock_model):
            vec = await backend.embed_single_query("search query", dimensions=3)
            assert vec == pytest.approx([0.1, 0.2, 0.3])
            mock_model.query_embed.assert_called_once_with("search query", dim=3)

    async def test_embed_single_query_no_dims(self):
        import numpy as np

        from wet_mcp.embedder import LocalEmbeddingBackend

        backend = LocalEmbeddingBackend()
        mock_model = MagicMock()
        mock_model.query_embed.return_value = iter([np.array([0.4, 0.5])])

        with patch.object(backend, "_get_model", return_value=mock_model):
            vec = await backend.embed_single_query("query")
            assert vec == pytest.approx([0.4, 0.5])
            mock_model.query_embed.assert_called_once_with("query")


# -----------------------------------------------------------------------
# llm.py coverage
# -----------------------------------------------------------------------


class TestGetLlmConfigCellGating:
    """The [models.chat] cell decides whether LLM features exist at all."""

    async def test_unconfigured_cell_means_no_model(self):
        from wet_mcp.llm import get_llm_config

        unconfigured = MagicMock()
        unconfigured.configured = False

        with patch(
            "wet_mcp.runtime.model_cell", lambda task, settings=None: unconfigured
        ):
            config = get_llm_config()

        # Unconfigured cell -> no model (LLM feature off), empty key.
        assert config["model"] is None
        assert config["api_key"] == ""
        assert config["fallbacks"] == []

    async def test_configured_cell_owns_model_and_base(self):
        from wet_mcp.llm import get_llm_config

        cell = MagicMock()
        cell.configured = True
        cell.model = "gemini/gemini-3-flash"
        cell.base_url = "https://cell.example/v1"
        cell.api_key = "cell-key"

        with patch("wet_mcp.runtime.model_cell", lambda task, settings=None: cell):
            config = get_llm_config()

        assert config["model"] == "gemini/gemini-3-flash"
        assert config["api_base"] == "https://cell.example/v1"
        assert config["api_key"] == "cell-key"
        assert config["fallbacks"] == []


class TestAnalyzeMediaMimeUnknown:
    """Cover unknown mime type."""

    async def test_mime_type_none(self, tmp_path):
        from wet_mcp.config import settings
        from wet_mcp.llm import analyze_media

        original_download = settings.download_dir
        settings.download_dir = str(tmp_path)

        # Create file with no extension
        f = tmp_path / "noext"
        f.write_bytes(b"\x00\x01\x02")

        try:
            with patch("wet_mcp.llm.has_llm_provider", return_value=True):
                result = await analyze_media(str(f))
            assert "Error" in result
        finally:
            settings.download_dir = original_download


class TestAnalyzeMediaErrorPaths:
    """Cover lines 120-121, 131-132, 134-135, 166-168: error handling."""

    async def test_text_file_completion_error(self, tmp_path):
        from wet_mcp.config import settings
        from wet_mcp.llm import analyze_media

        settings.download_dir = str(tmp_path)

        txt = tmp_path / "test.txt"
        txt.write_text("hello")

        with (
            patch("wet_mcp.llm.has_llm_provider", return_value=True),
            patch(
                "wet_mcp.llm.acompletion",
                side_effect=Exception("API down"),
            ),
        ):
            result = await analyze_media(str(txt))
            assert "Error analyzing text file" in result

    async def test_audio_not_supported(self, tmp_path):
        from wet_mcp.config import settings
        from wet_mcp.llm import analyze_media

        settings.download_dir = str(tmp_path)

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        with (
            patch("wet_mcp.llm.has_llm_provider", return_value=True),
            patch("wet_mcp.llm.get_model_capabilities") as mock_caps,
        ):
            mock_caps.return_value = {
                "vision": False,
                "audio_input": False,
                "audio_output": False,
            }
            result = await analyze_media(str(audio_file))
            assert "does not support audio input" in result

    async def test_video_not_supported(self, tmp_path):
        from wet_mcp.config import settings
        from wet_mcp.llm import analyze_media

        settings.download_dir = str(tmp_path)

        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video")

        with (
            patch("wet_mcp.llm.has_llm_provider", return_value=True),
            patch("wet_mcp.llm.get_model_capabilities") as mock_caps,
        ):
            mock_caps.return_value = {
                "vision": False,
                "audio_input": False,
                "audio_output": False,
            }
            result = await analyze_media(str(video_file))
            assert "does not support video" in result

    async def test_media_analysis_exception(self, tmp_path):
        """Cover exception during media analysis."""
        from wet_mcp.config import settings
        from wet_mcp.llm import analyze_media

        settings.download_dir = str(tmp_path)

        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake image")

        with (
            patch("wet_mcp.llm.has_llm_provider", return_value=True),
            patch("wet_mcp.llm.get_model_capabilities") as mock_caps,
            patch(
                "wet_mcp.llm.acompletion",
                side_effect=Exception("LLM crashed"),
            ),
        ):
            mock_caps.return_value = {
                "vision": True,
                "audio_input": False,
                "audio_output": False,
            }
            result = await analyze_media(str(img))
            assert "Error analyzing media" in result
            assert "LLM crashed" in result


# -----------------------------------------------------------------------
# reranker.py coverage
# -----------------------------------------------------------------------


def _stub_rerank_client(model: str = "rerank-v4.0-pro"):
    """A stub hull OpenAI-spec client for the rerank cell."""
    client = MagicMock()
    client.cell.model = model
    client.rerank = AsyncMock()
    return client


class TestCloudRerankerCellOwned:
    """The cell owns model/base_url/key; results parse to (index, score)."""

    async def test_rerank_parses_provider_results(self):
        from wet_mcp.reranker import CloudReranker

        client = _stub_rerank_client()
        client.rerank.return_value = [{"index": 0, "relevance_score": 0.9}]
        reranker = CloudReranker(client)

        results = await reranker.rerank("query", ["doc1"], top_n=5)
        assert len(results) == 1
        assert reranker.model == "rerank-v4.0-pro"
        client.rerank.assert_awaited_once_with("query", ["doc1"], top_n=5)

    async def test_check_available_true_when_provider_answers(self):
        from wet_mcp.reranker import CloudReranker

        client = _stub_rerank_client()
        client.rerank.return_value = [{"index": 0, "relevance_score": 0.5}]
        reranker = CloudReranker(client)

        assert await reranker.check_available() is True


class TestLocalRerankerLoadModel:
    """Cover lines 164-174: _get_model lazy loading and caching."""

    async def test_get_model_loads_and_caches(self):
        from wet_mcp.reranker import LocalReranker

        reranker = LocalReranker("test-model")
        mock_cross_encoder = MagicMock()
        mock_module = MagicMock()
        mock_module.TextCrossEncoder = mock_cross_encoder

        with patch.dict("sys.modules", {"fastretrieval": mock_module}):
            model1 = reranker._get_model()
            model2 = reranker._get_model()
            assert model1 is model2
            mock_cross_encoder.assert_called_once()

    async def test_get_model_import_error(self):
        from wet_mcp.reranker import LocalReranker

        reranker = LocalReranker()
        with patch.dict("sys.modules", {"fastretrieval": None}):
            with patch(
                "builtins.__import__",
                side_effect=ImportError("No module"),
            ):
                with pytest.raises(ImportError):
                    reranker._get_model()


class TestCloudRerankerCheckAvailableEmpty:
    """Cover edge case: check_available with empty results."""

    async def test_check_available_empty_results(self):
        from wet_mcp.reranker import CloudReranker

        client = _stub_rerank_client()
        client.rerank.return_value = []
        reranker = CloudReranker(client)

        assert await reranker.check_available() is False
