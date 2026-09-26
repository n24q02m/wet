"""Tests for wet_mcp.__main__ — ``python -m wet_mcp`` dispatch + setup_tool helpers.

Dispatch contract (de-host): no args (or ``--serve``) runs the BLOCKING HTTP
server via ``wet_mcp.server.run_server_blocking``; any other argv delegates to
the ``wet`` CLI control plane. There is no stdio mode and no ``--http`` flag.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# python -m wet_mcp dispatch
# ---------------------------------------------------------------------------


class TestModuleDispatch:
    """__main__.main routes bare/--serve argv to the server, else to the CLI."""

    def test_bare_invocation_runs_blocking_server(self):
        from wet_mcp import __main__ as m

        with patch("wet_mcp.server.run_server_blocking") as mock_serve:
            rc = m.main([])

        mock_serve.assert_called_once_with(host=None, port=None)
        assert rc == 0

    def test_serve_flag_with_port_override(self):
        from wet_mcp import __main__ as m

        with patch("wet_mcp.server.run_server_blocking") as mock_serve:
            rc = m.main(["--serve", "--port", "9999"])

        mock_serve.assert_called_once_with(host=None, port=9999)
        assert rc == 0

    def test_serve_flag_with_host_and_port(self):
        from wet_mcp import __main__ as m

        with patch("wet_mcp.server.run_server_blocking") as mock_serve:
            rc = m.main(["--serve", "--host", "0.0.0.0", "--port", "7000"])

        mock_serve.assert_called_once_with(host="0.0.0.0", port=7000)
        assert rc == 0

    def test_subcommand_delegates_to_cli(self):
        from wet_mcp import __main__ as m

        with patch("wet_mcp.cli.main", return_value=0) as mock_cli_main:
            rc = m.main(["config", "path"])

        mock_cli_main.assert_called_once_with(["config", "path"])
        assert rc == 0

    def test_missing_server_entry_falls_back_to_server_main(self, monkeypatch):
        """Defensive fallback when run_server_blocking is absent."""
        import wet_mcp.server as server_mod
        from wet_mcp import __main__ as m

        monkeypatch.setattr(server_mod, "run_server_blocking", None, raising=False)
        with patch.object(server_mod, "main") as mock_server_main:
            rc = m.main([])

        mock_server_main.assert_called_once_with()
        assert rc == 0


# ---------------------------------------------------------------------------
# setup_tool: local model download helpers (kept warmup building blocks)
# ---------------------------------------------------------------------------


class TestClearModelCache:
    """clear_model_cache removes corrupted HF Hub cache directories."""

    def test_removes_existing_cache(self, tmp_path):
        from wet_mcp.setup_tool import clear_model_cache

        model_dir = tmp_path / "models--org--model"
        model_dir.mkdir(parents=True)
        (model_dir / "refs").mkdir()
        (model_dir / "blobs").mkdir()
        (model_dir / "blobs" / "abc.incomplete").touch()

        with patch.dict("os.environ", {"FASTRETRIEVAL_CACHE_PATH": str(tmp_path)}):
            result = clear_model_cache("org/model")

        assert not model_dir.exists()
        assert result is not None

    def test_noop_when_cache_missing(self, tmp_path):
        from wet_mcp.setup_tool import clear_model_cache

        with patch.dict("os.environ", {"FASTRETRIEVAL_CACHE_PATH": str(tmp_path)}):
            result = clear_model_cache("nonexistent/model")

        assert result is None

    def test_explicit_cache_env_wins_over_xdg_default(self, tmp_path):
        from wet_mcp.setup_tool import clear_model_cache

        xdg_dir = tmp_path / "xdg"
        explicit_dir = tmp_path / "explicit"
        xdg_model = xdg_dir / "fastretrieval" / "models--org--model"
        explicit_model = explicit_dir / "models--org--model"
        xdg_model.mkdir(parents=True)
        explicit_model.mkdir(parents=True)

        with patch.dict(
            "os.environ",
            {
                "FASTRETRIEVAL_CACHE_PATH": str(explicit_dir),
                "XDG_CACHE_HOME": str(xdg_dir),
            },
        ):
            result = clear_model_cache("org/model")

        assert result == str(explicit_model)
        assert not explicit_model.exists()
        assert xdg_model.exists()


class TestDownloadLocalEmbedding:
    """_download_local_embedding validates and downloads local models."""

    @patch("fastretrieval.TextEmbedding")
    def test_embedding_success(self, mock_te):
        from wet_mcp.setup_tool import _download_local_embedding

        mock_settings = MagicMock()
        mock_settings.resolve_local_embedding_model.return_value = "org/embed"

        mock_model = MagicMock()
        mock_model.embed.return_value = iter([np.array([0.1, 0.2])])
        mock_te.return_value = mock_model

        result = _download_local_embedding(mock_settings)

        assert result["step"] == "local_embedding"
        assert result["status"] == "ok"
        assert result["dims"] == 2

    @patch("wet_mcp.setup_tool.clear_model_cache")
    @patch("fastretrieval.TextEmbedding")
    def test_corrupted_cache_clears_and_retries(self, mock_te, mock_clear):
        from wet_mcp.setup_tool import _download_local_embedding

        mock_settings = MagicMock()
        mock_settings.resolve_local_embedding_model.return_value = "org/embed"

        mock_model_ok = MagicMock()
        mock_model_ok.embed.return_value = iter([np.array([0.1, 0.2])])

        exc = Exception("[ONNXRuntimeError] : 3 : NO_SUCHFILE : file doesn't exist")
        mock_te.side_effect = [exc, mock_model_ok]

        result = _download_local_embedding(mock_settings)

        mock_clear.assert_called_once_with("org/embed")
        assert result["status"] == "ok"
        assert result.get("retried") is True

    @patch("fastretrieval.TextEmbedding")
    def test_non_cache_error_reraises(self, mock_te):
        from wet_mcp.setup_tool import _download_local_embedding

        mock_settings = MagicMock()
        mock_settings.resolve_local_embedding_model.return_value = "org/model"

        mock_te.side_effect = ImportError("fastretrieval not installed")

        with pytest.raises(ImportError, match="not installed"):
            _download_local_embedding(mock_settings)

    @patch("fastretrieval.TextEmbedding")
    def test_embedding_empty_result(self, mock_te):
        from wet_mcp.setup_tool import _download_local_embedding

        mock_settings = MagicMock()
        mock_settings.resolve_local_embedding_model.return_value = "org/embed"

        mock_model = MagicMock()
        mock_model.embed.return_value = iter([])
        mock_te.return_value = mock_model

        result = _download_local_embedding(mock_settings)
        assert result["status"] == "warning"

    @patch("wet_mcp.setup_tool.clear_model_cache")
    @patch("fastretrieval.TextEmbedding")
    def test_embedding_empty_after_retry(self, mock_te, mock_clear):
        from wet_mcp.setup_tool import _download_local_embedding

        mock_settings = MagicMock()
        mock_settings.resolve_local_embedding_model.return_value = "org/embed"

        exc = Exception("NO_SUCHFILE")
        mock_model_empty = MagicMock()
        mock_model_empty.embed.return_value = iter([])
        mock_te.side_effect = [exc, mock_model_empty]

        result = _download_local_embedding(mock_settings)
        assert result["status"] == "warning"
        assert "after cache clear" in result["message"]


class TestDownloadLocalReranker:
    """_download_local_reranker validates and downloads local reranker."""

    def test_rerank_disabled_skips(self):
        from wet_mcp.setup_tool import _download_local_reranker

        mock_settings = MagicMock()
        mock_settings.rerank_enabled = False

        result = _download_local_reranker(mock_settings)
        assert result["status"] == "skipped"

    @patch("fastretrieval.TextCrossEncoder")
    def test_reranker_success(self, mock_tce):
        from wet_mcp.setup_tool import _download_local_reranker

        mock_settings = MagicMock()
        mock_settings.rerank_enabled = True
        mock_settings.resolve_local_rerank_model.return_value = "org/rerank"

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = iter([0.9])
        mock_tce.return_value = mock_reranker

        result = _download_local_reranker(mock_settings)
        assert result["status"] == "ok"

    @patch("wet_mcp.setup_tool.clear_model_cache")
    @patch("fastretrieval.TextCrossEncoder")
    def test_corrupted_reranker_cache_retries(self, mock_tce, mock_clear):
        from wet_mcp.setup_tool import _download_local_reranker

        mock_settings = MagicMock()
        mock_settings.rerank_enabled = True
        mock_settings.resolve_local_rerank_model.return_value = "org/rerank"

        mock_reranker_ok = MagicMock()
        mock_reranker_ok.rerank.return_value = iter([0.9])
        exc = Exception("NO_SUCHFILE")
        mock_tce.side_effect = [exc, mock_reranker_ok]

        result = _download_local_reranker(mock_settings)
        mock_clear.assert_called_once_with("org/rerank")
        assert result["status"] == "ok"
        assert result.get("retried") is True

    @patch("fastretrieval.TextCrossEncoder")
    def test_reranker_empty_result(self, mock_tce):
        from wet_mcp.setup_tool import _download_local_reranker

        mock_settings = MagicMock()
        mock_settings.rerank_enabled = True
        mock_settings.resolve_local_rerank_model.return_value = "org/rerank"

        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = iter([])
        mock_tce.return_value = mock_reranker

        result = _download_local_reranker(mock_settings)
        assert result["status"] == "warning"

    @patch("wet_mcp.setup_tool.clear_model_cache")
    @patch("fastretrieval.TextCrossEncoder")
    def test_reranker_empty_after_retry(self, mock_tce, mock_clear):
        from wet_mcp.setup_tool import _download_local_reranker

        mock_settings = MagicMock()
        mock_settings.rerank_enabled = True
        mock_settings.resolve_local_rerank_model.return_value = "org/rerank"

        exc = Exception("NO_SUCHFILE")
        mock_reranker_empty = MagicMock()
        mock_reranker_empty.rerank.return_value = iter([])
        mock_tce.side_effect = [exc, mock_reranker_empty]

        result = _download_local_reranker(mock_settings)
        assert result["status"] == "warning"

    @patch("fastretrieval.TextCrossEncoder")
    def test_reranker_non_cache_error_reraises(self, mock_tce):
        from wet_mcp.setup_tool import _download_local_reranker

        mock_settings = MagicMock()
        mock_settings.rerank_enabled = True
        mock_settings.resolve_local_rerank_model.return_value = "org/rerank"

        mock_tce.side_effect = RuntimeError("GPU not available")

        with pytest.raises(RuntimeError, match="GPU not available"):
            _download_local_reranker(mock_settings)


# ---------------------------------------------------------------------------
# setup_tool: cloud cell validation ([models.embed] / [models.rerank])
# ---------------------------------------------------------------------------


def _cell(model: str):
    from types import SimpleNamespace

    return SimpleNamespace(model=model)


class TestValidateCloudModels:
    """_validate_cloud_models probes the per-task provider cells."""

    @patch("wet_mcp.reranker.init_reranker")
    @patch("wet_mcp.embedder.init_backend")
    async def test_configured_cells_both_ready(self, mock_init, mock_rr_init, monkeypatch):
        from wet_mcp.setup_tool import _validate_cloud_models

        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured",
            lambda task, settings=None: task in ("embed", "rerank"),
        )
        monkeypatch.setattr(
            "wet_mcp.runtime.model_cell",
            lambda task, settings=None: _cell(
                "gemini/embed-1" if task == "embed" else "cohere/rerank"
            ),
        )

        mock_backend = MagicMock()
        mock_backend.check_available = AsyncMock(return_value=768)
        mock_init.return_value = mock_backend

        mock_reranker = MagicMock()
        mock_reranker.check_available.return_value = True
        mock_rr_init.return_value = mock_reranker

        result = await _validate_cloud_models(MagicMock())

        assert result["cloud_ready"] is True
        assert result["embedding"]["model"] == "gemini/embed-1"
        assert result["reranker"]["model"] == "cohere/rerank"
        # The cell owns the model: init_backend gets the cell's model id.
        mock_init.assert_called_once_with("cloud", "gemini/embed-1")
        mock_rr_init.assert_called_once_with("cloud", "cohere/rerank")

    @patch("wet_mcp.embedder.init_backend")
    async def test_embed_cell_check_fails(self, mock_init, monkeypatch):
        from wet_mcp.setup_tool import _validate_cloud_models

        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured",
            lambda task, settings=None: task == "embed",
        )
        monkeypatch.setattr(
            "wet_mcp.runtime.model_cell",
            lambda task, settings=None: _cell("model-a"),
        )

        mock_backend = MagicMock()
        mock_backend.check_available = AsyncMock(return_value=0)
        mock_init.return_value = mock_backend

        result = await _validate_cloud_models(MagicMock())
        assert result["cloud_ready"] is False
        assert result["errors"]

    @patch("wet_mcp.reranker.init_reranker")
    @patch("wet_mcp.embedder.init_backend")
    async def test_rerank_check_false_keeps_embed_ready(
        self, mock_init, mock_rr_init, monkeypatch
    ):
        from wet_mcp.setup_tool import _validate_cloud_models

        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured", lambda task, settings=None: True
        )
        monkeypatch.setattr(
            "wet_mcp.runtime.model_cell",
            lambda task, settings=None: _cell("gemini/embed"),
        )

        mock_backend = MagicMock()
        mock_backend.check_available = AsyncMock(return_value=768)
        mock_init.return_value = mock_backend

        mock_reranker = MagicMock()
        mock_reranker.check_available.return_value = False
        mock_rr_init.return_value = mock_reranker

        result = await _validate_cloud_models(MagicMock())
        assert result["cloud_ready"] is True
        assert "reranker" not in result

    @patch("wet_mcp.reranker.init_reranker")
    @patch("wet_mcp.embedder.init_backend")
    async def test_rerank_init_exception_reported_not_raised(
        self, mock_init, mock_rr_init, monkeypatch
    ):
        from wet_mcp.setup_tool import _validate_cloud_models

        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured", lambda task, settings=None: True
        )
        monkeypatch.setattr(
            "wet_mcp.runtime.model_cell",
            lambda task, settings=None: _cell("gemini/embed"),
        )

        mock_backend = MagicMock()
        mock_backend.check_available = AsyncMock(return_value=768)
        mock_init.return_value = mock_backend

        mock_rr_init.side_effect = Exception("reranker init failed")

        result = await _validate_cloud_models(MagicMock())
        assert result["cloud_ready"] is True
        assert "reranker" not in result
        assert result["errors"]

    @patch("wet_mcp.embedder.init_backend")
    async def test_embed_init_exception_reported_not_raised(self, mock_init, monkeypatch):
        from wet_mcp.setup_tool import _validate_cloud_models

        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured",
            lambda task, settings=None: task == "embed",
        )
        monkeypatch.setattr(
            "wet_mcp.runtime.model_cell",
            lambda task, settings=None: _cell("model-a"),
        )
        mock_init.side_effect = Exception("init failed")

        result = await _validate_cloud_models(MagicMock())
        assert result["cloud_ready"] is False
        assert result["errors"]

    async def test_no_cells_configured(self, monkeypatch):
        from wet_mcp.setup_tool import _validate_cloud_models

        monkeypatch.setattr(
            "wet_mcp.runtime.cell_configured", lambda task, settings=None: False
        )

        result = await _validate_cloud_models(MagicMock())
        assert result == {"cloud_ready": False}
