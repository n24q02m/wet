"""Tests for setup_tool module -- warmup as an MCP-callable function.

De-host: the GDrive ``setup_sync`` flow and the ``setup_status`` /
``setup_start`` / ``setup_reset`` config actions are gone (provider cells
are host-owned in ``~/.wet/config.toml``); only ``run_warmup`` and the
``config(action="warmup")`` dispatch remain.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from structured import text


def _no_cells():
    """No provider cell configured (host never wrote ~/.wet/config.toml)."""

    def _cell_configured(task, settings=None):
        return False

    return _cell_configured


def _all_cells():
    """Both embed and rerank cells configured."""

    def _cell_configured(task, settings=None):
        return task in ("embed", "rerank")

    return _cell_configured


def _embed_cell_only():
    """Only the embed cell configured (no rerank cell)."""

    def _cell_configured(task, settings=None):
        return task == "embed"

    return _cell_configured


class TestRunWarmup:
    """Tests for run_warmup() returning structured dict."""

    async def test_warmup_returns_dict_with_status(self):
        """run_warmup() must return a dict with 'status' key."""
        with (
            patch("wet_mcp.setup.run_auto_setup"),
            patch("wet_mcp.runtime.cell_configured", _no_cells()),
            patch("wet_mcp.setup_tool.settings") as mock_settings,
            patch("fastretrieval.TextEmbedding") as mock_embed,
        ):
            mock_settings.rerank_enabled = False
            mock_settings.resolve_local_embedding_model.return_value = "Qwen/test-model"

            mock_embed.return_value.embed.return_value = iter([[0.1] * 768])

            from wet_mcp import setup_tool
            from wet_mcp.setup_tool import run_warmup

            result = await run_warmup()

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] == "ok"

    async def test_warmup_cloud_models_success(self):
        """When the provider cells are configured and healthy, skip local downloads."""
        with (
            patch("wet_mcp.setup.run_auto_setup"),
            patch("wet_mcp.runtime.cell_configured", _all_cells()),
            patch("wet_mcp.setup_tool.settings") as mock_settings,
            patch("wet_mcp.embedder.init_backend") as mock_init_backend,
            patch("wet_mcp.reranker.init_reranker") as mock_init_reranker,
        ):
            cell = MagicMock()
            cell.model = "text-embedding-3-large"
            mock_init_backend.return_value = MagicMock(
                check_available=AsyncMock(return_value=768)
            )

            mock_reranker = MagicMock()
            mock_reranker.check_available.return_value = True
            mock_init_reranker.return_value = mock_reranker

            from wet_mcp.setup_tool import run_warmup

            result = await run_warmup()

        assert result["status"] == "ok"
        assert result["mode"] == "cloud"
        assert "embedding" in result
        assert "reranker" in result

    async def test_warmup_cloud_fallback_to_local(self):
        """When the configured cell fails its check, fall back to local download."""
        with (
            patch("wet_mcp.setup.run_auto_setup"),
            patch("wet_mcp.runtime.cell_configured", _embed_cell_only()),
            patch("wet_mcp.setup_tool.settings") as mock_settings,
            patch("wet_mcp.embedder.init_backend") as mock_init_backend,
            patch("fastretrieval.TextEmbedding") as mock_embed,
        ):
            mock_settings.rerank_enabled = False
            mock_settings.resolve_local_embedding_model.return_value = "Qwen/test-model"

            mock_init_backend.side_effect = Exception("no API key")

            mock_embed.return_value.embed.return_value = iter([[0.1] * 768])

            from wet_mcp.setup_tool import run_warmup

            result = await run_warmup()

        assert result["status"] == "ok"
        assert result["mode"] == "local"

    async def test_warmup_auto_setup_failure(self):
        """Auto-setup failure is reported but non-fatal."""
        with (
            patch(
                "wet_mcp.setup.run_auto_setup",
                side_effect=Exception("setup failed"),
            ),
            patch("wet_mcp.runtime.cell_configured", _no_cells()),
            patch("wet_mcp.setup_tool.settings") as mock_settings,
            patch("fastretrieval.TextEmbedding") as mock_embed,
        ):
            mock_settings.rerank_enabled = False
            mock_settings.resolve_local_embedding_model.return_value = "Qwen/test-model"

            mock_embed.return_value.embed.return_value = iter([[0.1] * 768])

            from wet_mcp.setup_tool import run_warmup

            result = await run_warmup()

        assert result["status"] == "ok"
        assert "setup failed" in result["steps"][0]["error"]

    async def test_warmup_local_embedding_with_reranker(self):
        """Both local embedding and reranker are downloaded when rerank enabled."""
        with (
            patch("wet_mcp.setup.run_auto_setup"),
            patch("wet_mcp.runtime.cell_configured", _no_cells()),
            patch("wet_mcp.setup_tool.settings") as mock_settings,
            patch("fastretrieval.TextEmbedding") as mock_embed,
            patch("fastretrieval.TextCrossEncoder") as mock_reranker,
        ):
            mock_settings.rerank_enabled = True
            mock_settings.resolve_local_embedding_model.return_value = "Qwen/test-model"
            mock_settings.resolve_local_rerank_model.return_value = "Qwen/test-reranker"

            mock_embed.return_value.embed.return_value = iter([[0.1] * 768])
            mock_reranker.return_value.rerank.return_value = iter([0.9])

            from wet_mcp.setup_tool import run_warmup

            result = await run_warmup()

        assert result["status"] == "ok"
        assert result["mode"] == "local"
        assert any(s["step"] == "local_reranker" for s in result["steps"])

    async def test_warmup_corrupted_cache_retry(self):
        """Corrupted cache triggers clear + retry."""
        with (
            patch("wet_mcp.setup.run_auto_setup"),
            patch("wet_mcp.runtime.cell_configured", _no_cells()),
            patch("wet_mcp.setup_tool.settings") as mock_settings,
            patch("wet_mcp.setup_tool.clear_model_cache") as mock_clear,
            patch("fastretrieval.TextEmbedding") as mock_embed,
        ):
            mock_settings.rerank_enabled = False
            mock_settings.resolve_local_embedding_model.return_value = "Qwen/test-model"

            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("NO_SUCHFILE")
                mock_instance = MagicMock()
                mock_instance.embed.return_value = iter([[0.1] * 768])
                return mock_instance

            mock_embed.side_effect = side_effect

            from wet_mcp.setup_tool import run_warmup

            result = await run_warmup()

        assert result["status"] == "ok"
        mock_clear.assert_called_once()


class TestSetupMcpTool:
    """Tests for the warmup action in the config tool."""

    async def test_config_tool_warmup_action(self):
        """config tool with action='warmup' calls run_warmup."""
        with patch(
            "wet_mcp.setup_tool.run_warmup",
            new_callable=AsyncMock,
            return_value={"status": "ok", "steps": [], "mode": "local"},
        ):
            from wet_mcp.server import config

            result = await config(action="warmup")
            assert '"status": "ok"' in text(result)

    async def test_config_tool_invalid_action(self):
        """config tool with invalid action returns an error payload."""
        from wet_mcp.server import config

        result = await config(action="invalid_xyz_action")
        assert '"error"' in text(result)
        assert "Unknown action" in text(result)

    async def test_removed_setup_actions_report_unknown(self):
        """The de-host removed setup_sync/setup_status/setup_start/setup_reset.

        They must not silently resurrect: each reports the same unknown-action
        error an operator would get for any typo, naming the valid actions.
        """
        from wet_mcp.server import config

        for action in ("setup_sync", "setup_status", "setup_start", "setup_reset"):
            result = await config(action=action)
            assert "Unknown action" in text(result), action
            assert "warmup" in text(result), action
