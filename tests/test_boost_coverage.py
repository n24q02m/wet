"""Tests to boost overall coverage to 95%+ (de-host port).

Kept targets (new seams):
- server.py -- config tool, help tool, research, media download security
- llm.py -- acompletion via the [models.chat] cell (no fallback chain)
- searxng_runner.py -- subprocess lifecycle, cleanup, stale port, discovery

Deleted surface (tests removed with it): relay_setup, sync/gdrive,
token_store, credential_state, setup_sync, mcp_core.llm facade.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structured import payload, text

# =====================================================================
# llm.py -- acompletion, backends, message conversion
# =====================================================================


class TestLLMACompletion:
    """Cover acompletion over the [models.chat] cell (single cell, no chain)."""

    @staticmethod
    def _client(content: str) -> MagicMock:
        client = MagicMock()
        client.chat = AsyncMock(return_value=content)
        return client

    async def test_cell_content_roundtrip(self):
        """acompletion returns the cell client's content in ChatResult shape."""
        from wet_mcp.llm import acompletion

        with patch(
            "wet_mcp.llm._chat_provider_client", return_value=self._client("Hello")
        ):
            result = await acompletion(
                model="ignored-anyway",
                messages=[{"role": "user", "content": "Hi"}],
            )
            assert result.choices[0].message.content == "Hello"

    async def test_model_arg_ignored_cell_owns_model(self):
        """model/api_base/api_key args are accepted but ignored verbatim."""
        from wet_mcp.llm import acompletion

        client = self._client("Hello from the cell")
        with patch("wet_mcp.llm._chat_provider_client", return_value=client):
            result = await acompletion(
                model="xai/grok-4-1-fast-reasoning",
                messages=[{"role": "user", "content": "Hi"}],
                api_base="https://elsewhere.example.com",
                api_key="sk-not-used",
            )
            assert result.choices[0].message.content == "Hello from the cell"
        client.chat.assert_awaited_once()

    async def test_extra_kwargs_forwarded(self):
        """Extra provider options pass through to the cell client."""
        from wet_mcp.llm import acompletion

        client = self._client("ok")
        with patch("wet_mcp.llm._chat_provider_client", return_value=client):
            await acompletion(
                messages=[{"role": "user", "content": "Hi"}],
                top_p=0.9,
            )
        _, kwargs = client.chat.call_args
        assert kwargs.get("top_p") == 0.9

    async def test_fallbacks_accepted_but_no_chain(self):
        """fallbacks is accepted-and-ignored: one cell, exactly one attempt."""
        from wet_mcp.llm import acompletion

        client = MagicMock()
        client.chat = AsyncMock(side_effect=Exception("cell down"))
        with (
            patch("wet_mcp.llm._chat_provider_client", return_value=client),
            pytest.raises(Exception, match="cell down"),
        ):
            await acompletion(
                messages=[{"role": "user", "content": "Hi"}],
                fallbacks=["openai/gpt-4"],
            )
        assert client.chat.await_count == 1


class TestServerResearchAction:
    """Cover search research action."""

    async def test_research_missing_query(self):
        """Research requires query."""
        from wet_mcp.server import search

        result = await search(action="research")
        assert "Error: query is required" in text(result)

    async def test_research_success(self):
        """Research action delegates to _do_research."""
        from wet_mcp.server import search

        mock_results = json.dumps(
            {
                "results": [
                    {
                        "url": "https://arxiv.org/123",
                        "title": "Paper",
                        "snippet": "Abstract",
                    }
                ],
                "total": 1,
                "query": "attention",
            }
        )

        with (
            patch(
                "wet_mcp.server.ensure_searxng",
                new_callable=AsyncMock,
                return_value="http://localhost:8080",
            ),
            patch(
                "wet_mcp.sources.search_backends.run_search_chain",
                new_callable=AsyncMock,
                return_value=mock_results,
            ),
            patch("wet_mcp.server._web_cache", None),
            patch(
                "wet_mcp.server._rerank_results",
                new_callable=AsyncMock,
                return_value=[
                    {
                        "url": "https://arxiv.org/123",
                        "title": "Paper",
                        "snippet": "Abstract",
                        "content": "Abstract",
                        "score": 0.9,
                    }
                ],
            ),
        ):
            result = await search(action="research", query="attention mechanism")
            assert "arxiv" in text(result)

    async def test_docs_missing_library(self):
        """Docs requires library."""
        from wet_mcp.server import search

        result = await search(action="docs", query="routing")
        assert "Error: library is required" in text(result)

    async def test_docs_missing_query(self):
        """Docs requires query."""
        from wet_mcp.server import search

        result = await search(action="docs", library="fastapi")
        assert "Error: query is required" in text(result)

    async def test_search_typo_suggestion(self):
        """Typo in action gets suggestion."""
        from wet_mcp.server import search

        result = await search(action="serch")
        assert "Did you mean" in text(result)

    async def test_extract_typo_suggestion(self):
        """Typo in extract action gets suggestion."""
        from wet_mcp.server import extract

        result = await extract(action="exract")
        assert "Did you mean" in text(result)


class TestServerHelpers:
    """Cover _embed, _embed_batch, _rerank_results, _with_timeout."""

    async def test_embed_no_backend(self):
        """_embed returns None when no backend."""
        from wet_mcp.server import _embed

        with patch(
            "wet_mcp.embedder.resolve_embed_backend_for_request", return_value=None
        ):
            result = await _embed("test text")
            assert result is None

    async def test_embed_failure(self):
        """_embed returns None on a transient error (keyword-only degrade)."""
        from hull_core.providers.openai_spec import ProviderError

        from wet_mcp.server import _embed

        mock_backend = MagicMock()
        mock_backend.embed_single.side_effect = ProviderError(
            status=429, detail="rate limit exceeded"
        )
        with patch(
            "wet_mcp.embedder.resolve_embed_backend_for_request",
            return_value=mock_backend,
        ):
            result = await _embed("test text")
            assert result is None

    async def test_embed_batch_no_backend(self):
        """_embed_batch returns None when no backend."""
        from wet_mcp.server import _embed_batch

        with patch(
            "wet_mcp.embedder.resolve_embed_backend_for_request", return_value=None
        ):
            result = await _embed_batch(["text1", "text2"])
            assert result is None

    async def test_embed_batch_failure(self):
        """_embed_batch returns None on a transient error (degrade this call)."""
        from hull_core.providers.openai_spec import ProviderError

        from wet_mcp.server import _embed_batch

        mock_backend = MagicMock()
        mock_backend.embed_texts.side_effect = ProviderError(
            status=429, detail="rate limit exceeded"
        )
        with patch(
            "wet_mcp.embedder.resolve_embed_backend_for_request",
            return_value=mock_backend,
        ):
            result = await _embed_batch(["text1"])
            assert result is None

    async def test_rerank_no_reranker(self):
        """_rerank_results returns truncated results when no reranker."""
        from wet_mcp.server import _rerank_results

        results = [{"content": f"r{i}"} for i in range(5)]
        with patch(
            "wet_mcp.reranker.resolve_rerank_backend_for_request", return_value=None
        ):
            reranked = await _rerank_results("query", results, top_n=3)
            assert len(reranked) == 3

    async def test_rerank_fewer_than_topn(self):
        """_rerank_results returns all when fewer than top_n."""
        from wet_mcp.server import _rerank_results

        results = [{"content": "r1"}, {"content": "r2"}]
        with patch(
            "wet_mcp.reranker.resolve_rerank_backend_for_request",
            return_value=MagicMock(),
        ):
            reranked = await _rerank_results("query", results, top_n=5)
            assert len(reranked) == 2

    async def test_rerank_success(self):
        """_rerank_results reorders by score."""
        from wet_mcp.server import _rerank_results

        results = [{"content": "r0"}, {"content": "r1"}, {"content": "r2"}]
        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = [(2, 0.95), (0, 0.80)]

        with patch(
            "wet_mcp.reranker.resolve_rerank_backend_for_request",
            return_value=mock_reranker,
        ):
            reranked = await _rerank_results("query", results, top_n=2)
            assert len(reranked) == 2
            assert reranked[0]["content"] == "r2"
            assert reranked[0]["score"] == 0.95

    async def test_rerank_failure_fallback(self):
        """_rerank_results falls back on error."""
        from wet_mcp.server import _rerank_results

        results = [{"content": f"r{i}"} for i in range(5)]
        mock_reranker = MagicMock()
        mock_reranker.rerank.side_effect = Exception("rerank error")

        with patch(
            "wet_mcp.reranker.resolve_rerank_backend_for_request",
            return_value=mock_reranker,
        ):
            reranked = await _rerank_results("query", results, top_n=3)
            assert len(reranked) == 3

    async def test_with_timeout_no_timeout(self):
        """_with_timeout with timeout=0 runs normally."""
        from wet_mcp.server import _with_timeout

        async def fake_coro():
            return "result"

        with patch("wet_mcp.server.settings") as mock_settings:
            mock_settings.tool_timeout = 0
            result = await _with_timeout(fake_coro(), "test")
            assert result == "result"


class TestServerDetectGhToken:
    """Cover _detect_gh_token branches."""

    def test_no_gh_cli(self):
        """Returns None when gh CLI not installed."""
        from wet_mcp.server import _detect_gh_token

        with patch("shutil.which", return_value=None):
            assert _detect_gh_token() is None

    def test_gh_cli_returns_token(self):
        """Returns token from gh auth token."""
        from wet_mcp.server import _detect_gh_token

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_test_token_123\n"

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert _detect_gh_token() == "ghp_test_token_123"

    def test_gh_cli_fails(self):
        """Returns None when gh auth token fails."""
        from wet_mcp.server import _detect_gh_token

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert _detect_gh_token() is None

    def test_gh_cli_empty_token(self):
        """Returns None when gh returns empty token."""
        from wet_mcp.server import _detect_gh_token

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  \n"

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", return_value=mock_result),
        ):
            assert _detect_gh_token() is None

    def test_gh_cli_exception(self):
        """Returns None on exception."""
        from wet_mcp.server import _detect_gh_token

        with (
            patch("shutil.which", return_value="/usr/bin/gh"),
            patch("subprocess.run", side_effect=Exception("timeout")),
        ):
            assert _detect_gh_token() is None


# =====================================================================
# searxng_runner.py -- additional coverage
# =====================================================================


class TestSearxngRunnerExtras:
    """Cover additional branches in searxng_runner.py."""

    def test_is_pid_alive_unix_zombie(self):
        """Zombie process detected on Linux."""
        from web_core.search.runner import _is_pid_alive

        if sys.platform == "win32":
            pytest.skip("Unix-only test")

        with (
            patch("os.kill"),  # os.kill succeeds for zombies
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value="State:\tZ (zombie)\n"),
        ):
            assert _is_pid_alive(12345) is False

    def test_cleanup_process_owner(self):
        """Cleanup kills process when owner."""
        import web_core.search.runner as runner

        mock_proc = MagicMock()
        runner._searxng_process = mock_proc
        runner._searxng_port = 8080
        runner._is_owner = True

        with (
            patch.object(runner, "_force_kill_process"),
            patch.object(runner, "_remove_discovery"),
        ):
            runner._cleanup_process()
            assert runner._searxng_process is None
            assert runner._searxng_port is None
            assert runner._is_owner is False

    def test_cleanup_process_not_owner(self):
        """Cleanup leaves process running when not owner."""
        import web_core.search.runner as runner

        mock_proc = MagicMock()
        runner._searxng_process = mock_proc
        runner._searxng_port = 8080
        runner._is_owner = False

        runner._cleanup_process()
        assert runner._searxng_process is None

    def test_cleanup_no_process(self):
        """Cleanup with no process is a no-op."""
        import web_core.search.runner as runner

        runner._searxng_process = None
        runner._cleanup_process()  # Should not raise

    @pytest.mark.skipif(
        sys.platform == "win32", reason="os.setsid unavailable on Windows"
    )
    def test_get_process_kwargs_unix(self):
        """Unix kwargs include start_new_session for process group management."""
        from web_core.search.runner import _get_process_kwargs

        with patch("web_core.search.runner.sys") as mock_sys:
            mock_sys.platform = "linux"
            kwargs = _get_process_kwargs()
            # web-core uses start_new_session=True (modern Python) instead of
            # preexec_fn — keep both expectations covered so future regressions
            # in either direction surface here.
            assert kwargs.get("start_new_session") is True
            assert "preexec_fn" not in kwargs

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
    def test_get_process_kwargs_windows(self):
        """Windows kwargs include creationflags."""
        from web_core.search.runner import _get_process_kwargs

        kwargs = _get_process_kwargs()
        assert "creationflags" in kwargs

    def test_get_startup_lock_creates_once(self):
        """Startup lock is created once and reused."""
        import web_core.search.runner as runner

        runner._startup_lock = None
        lock1 = runner._get_startup_lock()
        lock2 = runner._get_startup_lock()
        assert lock1 is lock2
        runner._startup_lock = None  # cleanup

    def test_find_available_port(self):
        """Port finder returns a valid port."""
        from web_core.search.runner import _find_available_port

        port = _find_available_port(40000, max_tries=10)
        assert 40000 <= port < 40010

    def test_is_searxng_installed_true(self):
        """Returns True when searx.webapp is importable."""
        from web_core.search.runner import _is_searxng_installed

        with patch("importlib.util.find_spec", return_value=MagicMock()):
            assert _is_searxng_installed() is True

    def test_is_searxng_installed_false(self):
        """Returns False when searx.webapp not importable."""
        from web_core.search.runner import _is_searxng_installed

        with patch("importlib.util.find_spec", return_value=None):
            assert _is_searxng_installed() is False

    def test_is_searxng_installed_error(self):
        """Returns False on import error."""
        from web_core.search.runner import _is_searxng_installed

        with patch(
            "importlib.util.find_spec", side_effect=ModuleNotFoundError("no module")
        ):
            assert _is_searxng_installed() is False

    def test_read_discovery_valid(self, tmp_path):
        """Read valid discovery file."""
        import web_core.search.runner as runner

        old = runner._DISCOVERY_FILE
        runner._DISCOVERY_FILE = tmp_path / "instance.json"
        runner._DISCOVERY_FILE.write_text(json.dumps({"pid": 123, "port": 8080}))
        # web-core's _read_discovery rejects files whose mode is not 0o600 on
        # POSIX (defence-in-depth). tmp_path inherits umask, so chmod here.
        if sys.platform != "win32":
            os.chmod(runner._DISCOVERY_FILE, 0o600)

        result = runner._read_discovery()
        assert result is not None
        assert result["port"] == 8080
        runner._DISCOVERY_FILE = old

    def test_read_discovery_invalid(self, tmp_path):
        """Read invalid discovery file returns None."""
        import web_core.search.runner as runner

        old = runner._DISCOVERY_FILE
        runner._DISCOVERY_FILE = tmp_path / "instance.json"
        runner._DISCOVERY_FILE.write_text("not json")

        result = runner._read_discovery()
        assert result is None
        runner._DISCOVERY_FILE = old

    def test_read_discovery_missing(self, tmp_path):
        """Missing discovery file returns None."""
        import web_core.search.runner as runner

        old = runner._DISCOVERY_FILE
        runner._DISCOVERY_FILE = tmp_path / "nonexistent.json"

        result = runner._read_discovery()
        assert result is None
        runner._DISCOVERY_FILE = old

    def test_write_and_remove_discovery(self, tmp_path):
        """Write and remove discovery file."""
        import web_core.search.runner as runner

        old = runner._DISCOVERY_FILE
        runner._DISCOVERY_FILE = tmp_path / "instance.json"

        runner._write_discovery(8080, 12345)
        assert runner._DISCOVERY_FILE.exists()

        runner._remove_discovery()
        assert not runner._DISCOVERY_FILE.exists()

        runner._DISCOVERY_FILE = old

    def test_get_pip_command_uv(self):
        """Returns uv pip command when uv available."""
        from web_core.search.runner import _get_pip_command

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/uv" if x == "uv" else None
            cmd = _get_pip_command()
            assert "uv" in cmd[0]

    def test_get_pip_command_pip(self):
        """Returns pip command when pip available."""
        from web_core.search.runner import _get_pip_command

        with patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda x: "/usr/bin/pip" if x == "pip" else None
            cmd = _get_pip_command()
            assert "pip" in cmd[0]

    def test_get_pip_command_fallback(self):
        """Returns python -m pip as fallback."""
        from web_core.search.runner import _get_pip_command

        with patch("shutil.which", return_value=None):
            cmd = _get_pip_command()
            # [sys.executable, "-m", "pip", "install", "--python", sys.executable]
            # or [sys.executable, "-m", "pip", "install"]
            assert "pip" in cmd
            assert "-m" in cmd

    @pytest.mark.asyncio
    async def test_force_kill_already_dead(self):
        """Force kill on already dead process is no-op."""
        from web_core.search.runner import _force_kill_process

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Already dead
        await _force_kill_process(mock_proc)
        # Should not call terminate/kill


class TestSearxngInstall:
    """Cover _install_searxng."""

    def test_install_success(self):
        """Successful installation."""
        from web_core.search.runner import _install_searxng

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(subprocess, "run", return_value=mock_result),
            patch(
                "web_core.search.runner._get_pip_command",
                return_value=["pip", "install"],
            ),
            patch("wet_mcp.setup.patch_searxng_version"),
            patch("wet_mcp.setup.patch_searxng_windows"),
        ):
            assert _install_searxng() is True

    def test_install_deps_failure(self):
        """Build deps installation failure."""
        from web_core.search.runner import _install_searxng

        mock_deps_result = MagicMock()
        mock_deps_result.returncode = 1
        mock_deps_result.stderr = "dependency error"

        with (
            patch.object(subprocess, "run", return_value=mock_deps_result),
            patch(
                "web_core.search.runner._get_pip_command",
                return_value=["pip", "install"],
            ),
        ):
            assert _install_searxng() is False

    def test_install_searxng_failure(self):
        """SearXNG installation failure."""
        from web_core.search.runner import _install_searxng

        call_count = 0

        def fake_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count == 1:
                mock.returncode = 0  # deps succeed
            else:
                mock.returncode = 1  # searxng fails
                mock.stderr = "install error"
            return mock

        with (
            patch.object(subprocess, "run", side_effect=fake_run),
            patch(
                "web_core.search.runner._get_pip_command",
                return_value=["pip", "install"],
            ),
        ):
            assert _install_searxng() is False

    def test_install_timeout(self):
        """Installation timeout."""
        from web_core.search.runner import _install_searxng

        with (
            patch.object(
                subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("pip", 300),
            ),
            patch(
                "web_core.search.runner._get_pip_command",
                return_value=["pip", "install"],
            ),
        ):
            assert _install_searxng() is False

    def test_install_exception(self):
        """General exception during installation."""
        from web_core.search.runner import _install_searxng

        with (
            patch.object(
                subprocess,
                "run",
                side_effect=Exception("unexpected"),
            ),
            patch(
                "web_core.search.runner._get_pip_command",
                return_value=["pip", "install"],
            ),
        ):
            assert _install_searxng() is False


# =====================================================================
# setup_tool.py -- additional coverage
# =====================================================================


class TestSetupTool:
    """Cover setup_tool.py functions."""

    def test_clear_model_cache_exists(self, tmp_path):
        """Clears existing cache directory."""
        from wet_mcp.setup_tool import clear_model_cache

        cache_dir = tmp_path / "models--test--model"
        cache_dir.mkdir(parents=True)
        (cache_dir / "file.bin").write_bytes(b"data")

        with patch.dict(os.environ, {"FASTRETRIEVAL_CACHE_PATH": str(tmp_path)}):
            result = clear_model_cache("test/model")
            assert result is not None
            assert not cache_dir.exists()

    def test_clear_model_cache_not_exists(self, tmp_path):
        """Returns None when no cache."""
        from wet_mcp.setup_tool import clear_model_cache

        with patch.dict(os.environ, {"FASTRETRIEVAL_CACHE_PATH": str(tmp_path)}):
            result = clear_model_cache("nonexistent/model")
            assert result is None

class TestSetup:
    """Cover setup.py functions."""

    def test_needs_setup_false(self, tmp_path):
        """Returns False when marker exists."""
        from wet_mcp import setup

        old = setup.SETUP_MARKER
        setup.SETUP_MARKER = tmp_path / ".setup-complete"
        setup.SETUP_MARKER.touch()
        assert setup.needs_setup() is False
        setup.SETUP_MARKER = old

    def test_needs_setup_true(self, tmp_path):
        """Returns True when marker missing."""
        from wet_mcp import setup

        old = setup.SETUP_MARKER
        setup.SETUP_MARKER = tmp_path / ".setup-complete"
        assert setup.needs_setup() is True
        setup.SETUP_MARKER = old

    def test_find_searx_package_dir_found(self):
        """Returns path when searx found."""
        from wet_mcp.setup import _find_searx_package_dir

        mock_spec = MagicMock()
        mock_spec.submodule_search_locations = ["/path/to/searx"]
        with patch("importlib.util.find_spec", return_value=mock_spec):
            result = _find_searx_package_dir()
            assert result == Path("/path/to/searx")

    def test_find_searx_package_dir_not_found(self):
        """Returns None when searx not found."""
        from wet_mcp.setup import _find_searx_package_dir

        with patch("importlib.util.find_spec", return_value=None):
            result = _find_searx_package_dir()
            assert result is None

    def test_find_searx_package_dir_error(self):
        """Returns None on exception."""
        from wet_mcp.setup import _find_searx_package_dir

        with patch("importlib.util.find_spec", side_effect=Exception("error")):
            result = _find_searx_package_dir()
            assert result is None

    def test_patch_searxng_version_creates_file(self, tmp_path):
        """Creates version_frozen.py when missing."""
        from wet_mcp.setup import patch_searxng_version

        searx_dir = tmp_path / "searx"
        searx_dir.mkdir()
        vf = searx_dir / "version_frozen.py"

        with patch("wet_mcp.setup._find_searx_package_dir", return_value=searx_dir):
            patch_searxng_version()
            assert vf.exists()
            content = vf.read_text()
            assert "VERSION_STRING" in content

    def test_patch_searxng_version_already_exists(self, tmp_path):
        """Does not overwrite existing version_frozen.py."""
        from wet_mcp.setup import patch_searxng_version

        searx_dir = tmp_path / "searx"
        searx_dir.mkdir()
        vf = searx_dir / "version_frozen.py"
        vf.write_text("existing content")

        with patch("wet_mcp.setup._find_searx_package_dir", return_value=searx_dir):
            patch_searxng_version()
            assert vf.read_text() == "existing content"

    def test_patch_searxng_version_no_dir(self):
        """No-op when searx dir not found."""
        from wet_mcp.setup import patch_searxng_version

        with patch("wet_mcp.setup._find_searx_package_dir", return_value=None):
            patch_searxng_version()  # Should not raise


class TestRandomizedPortFinder:
    """Tests for the randomized port finder in searxng_runner."""

    def test_finds_available_port(self):
        """Should find an available port in range."""
        from wet_mcp.searxng_runner import _find_available_port

        port = _find_available_port(40000, max_tries=100)
        assert 40000 <= port < 40100

    def test_raises_when_no_port_available(self):
        """Raises RuntimeError when all ports are occupied."""
        from wet_mcp.searxng_runner import _find_available_port

        with patch("socket.socket") as mock_socket:
            mock_sock = MagicMock()
            mock_sock.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_sock.bind.side_effect = OSError("Address in use")
            mock_socket.return_value = mock_sock
            with pytest.raises(RuntimeError, match="No available port"):
                _find_available_port(40000, max_tries=3)
