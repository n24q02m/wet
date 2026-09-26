"""Tests to cover remaining gaps in setup_tool.py, cache.py, and reranker.py.

De-host: the ``sync.py`` gap tests are gone with the module (GDrive sync was
cut); the kept targets are the setup_tool local-model download edge cases,
the cache purge/close branches, the CloudReranker result parsing (now over
the hull OpenAI-spec client), and the SearXNG version patcher.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# setup_tool.py coverage gaps (migrated from __main__.py)
# ---------------------------------------------------------------------------


class TestSetupToolCoverageGaps:
    """Cover setup_tool.py edge cases for local embedding/reranker."""

    @patch("fastretrieval.TextEmbedding")
    def test_local_embedding_empty_result(self, mock_te):
        """embed returns empty list -- returns warning dict."""
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
    def test_local_embedding_empty_after_retry(self, mock_te, mock_clear):
        """embed returns empty after cache clear retry."""
        from wet_mcp.setup_tool import _download_local_embedding

        mock_settings = MagicMock()
        mock_settings.resolve_local_embedding_model.return_value = "org/embed"

        exc = Exception("NO_SUCHFILE: file doesn't exist")
        mock_model_retry = MagicMock()
        mock_model_retry.embed.return_value = iter([])
        mock_te.side_effect = [exc, mock_model_retry]

        result = _download_local_embedding(mock_settings)

        mock_clear.assert_called_once_with("org/embed")
        assert result["status"] == "warning"

    @patch("wet_mcp.reranker.init_reranker")
    @patch("wet_mcp.embedder.init_backend")
    async def test_cloud_reranker_init_exception(self, mock_init, mock_rr_init):
        """reranker init raises exception, caught and reported under errors.

        The embed cell validated fine, so ``cloud_ready`` stays True; the
        failed rerank cell is named in ``errors`` instead of silently vanish
        -- and ``reranker`` is absent, not a fake-ok entry.
        """
        from wet_mcp.setup_tool import _validate_cloud_models

        def _both_cells(task, settings=None):
            return task in ("embed", "rerank")

        cell = MagicMock()
        cell.model = "gemini/embed"

        mock_backend = MagicMock()
        mock_backend.check_available = AsyncMock(return_value=768)
        mock_init.return_value = mock_backend

        mock_rr_init.side_effect = Exception("reranker init failed")

        with (
            patch("wet_mcp.runtime.cell_configured", _both_cells),
            patch("wet_mcp.runtime.model_cell", lambda task, settings=None: cell),
        ):
            result = await _validate_cloud_models(MagicMock())

        assert result["cloud_ready"] is True
        assert "reranker" not in result
        assert any("rerank cell" in e for e in result["errors"])

    @patch("fastretrieval.TextCrossEncoder")
    def test_local_reranker_empty_result(self, mock_tce):
        """local reranker returns empty scores."""
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
    def test_local_reranker_empty_after_retry(self, mock_tce, mock_clear):
        """reranker retry returns empty scores."""
        from wet_mcp.setup_tool import _download_local_reranker

        mock_settings = MagicMock()
        mock_settings.rerank_enabled = True
        mock_settings.resolve_local_rerank_model.return_value = "org/rerank"

        exc = Exception("NO_SUCHFILE: file doesn't exist")
        mock_reranker_retry = MagicMock()
        mock_reranker_retry.rerank.return_value = iter([])
        mock_tce.side_effect = [exc, mock_reranker_retry]

        result = _download_local_reranker(mock_settings)

        mock_clear.assert_called_once_with("org/rerank")
        assert result["status"] == "warning"

    @patch("fastretrieval.TextCrossEncoder")
    def test_local_reranker_non_cache_error_reraises(self, mock_tce):
        """non-cache reranker error is re-raised."""
        from wet_mcp.setup_tool import _download_local_reranker

        mock_settings = MagicMock()
        mock_settings.rerank_enabled = True
        mock_settings.resolve_local_rerank_model.return_value = "org/rerank"

        mock_tce.side_effect = ImportError("fastretrieval broken")

        with pytest.raises(ImportError, match="broken"):
            _download_local_reranker(mock_settings)


# ---------------------------------------------------------------------------
# cache.py coverage gaps
# ---------------------------------------------------------------------------


class TestCachePurgeAndClose:
    """Cover cache.py periodic-purge trigger and the close() exception guard."""

    def test_periodic_purge_triggered(self, tmp_path):
        """_purge_expired called after _PURGE_INTERVAL ops."""
        from wet_mcp import cache as cache_mod
        from wet_mcp.cache import WebCache

        c = WebCache(tmp_path / "test.db")

        # Set op_count to just below threshold
        c._op_count = cache_mod._PURGE_INTERVAL - 1

        # This set should trigger purge
        c.set("search", {"q": "test"}, "content")

        # After purge, op_count resets to 0
        assert c._op_count == 0
        c.close()

    def test_close_handles_exception(self):
        """close() catches exceptions from conn.close()."""
        from wet_mcp.cache import WebCache

        cache = WebCache.__new__(WebCache)
        cache._conn = MagicMock()
        cache._lock = MagicMock()
        cache._conn.close.side_effect = Exception("already closed")

        cache.close()  # Should not raise


# ---------------------------------------------------------------------------
# reranker.py coverage gaps
# ---------------------------------------------------------------------------


class TestCloudRerankerResults:
    """Cover CloudReranker rerank result parsing (over the hull client)."""

    async def test_rerank_with_dict_results(self):
        from wet_mcp.reranker import CloudReranker

        client = MagicMock()
        client.cell.model = "cohere/rerank-v3.5"
        client.rerank = AsyncMock(
            return_value=[
                {"index": 0, "relevance_score": 0.8},
                {"index": 1, "relevance_score": 0.95},
            ]
        )
        reranker = CloudReranker(client)

        results = await reranker.rerank("query", ["doc1", "doc2"], top_n=2)

        assert results == [(1, 0.95), (0, 0.8)]

    async def test_rerank_provider_failure_returns_empty(self):
        """A broken cell degrades to "no reranking", not an exception."""
        from hull_core.providers.openai_spec import ProviderError

        from wet_mcp.reranker import CloudReranker

        client = MagicMock()
        client.cell.model = "cohere/rerank-v3.5"
        client.rerank = AsyncMock(
            side_effect=ProviderError(status=502, detail="bad gateway")
        )
        reranker = CloudReranker(client)

        assert await reranker.rerank("query", ["doc1"], top_n=1) == []


class TestSetupPatchSearxngVersion:
    """Cover setup.py patch_searxng_version() gaps."""

    @patch("wet_mcp.setup._find_searx_package_dir")
    def test_patch_searxng_version_success(self, mock_find_dir):
        from wet_mcp.setup import patch_searxng_version

        mock_dir = MagicMock(spec=Path)
        mock_find_dir.return_value = mock_dir
        mock_file = MagicMock(spec=Path)
        mock_dir.__truediv__.return_value = mock_file
        mock_file.exists.return_value = False

        patch_searxng_version()

        mock_file.write_text.assert_called_once()
        args = mock_file.write_text.call_args[0][0]
        assert "VERSION_STRING =" in args

    @patch("wet_mcp.setup._find_searx_package_dir")
    def test_patch_searxng_version_already_exists(self, mock_find_dir):
        from wet_mcp.setup import patch_searxng_version

        mock_dir = MagicMock(spec=Path)
        mock_find_dir.return_value = mock_dir
        mock_file = MagicMock(spec=Path)
        mock_dir.__truediv__.return_value = mock_file
        mock_file.exists.return_value = True

        patch_searxng_version()

        mock_file.write_text.assert_not_called()

    @patch("wet_mcp.setup._find_searx_package_dir")
    def test_patch_searxng_version_no_dir(self, mock_find_dir):
        from wet_mcp.setup import patch_searxng_version

        mock_find_dir.return_value = None
        patch_searxng_version()
        # No error should be raised

    @patch("wet_mcp.setup._find_searx_package_dir", side_effect=Exception("Test error"))
    @patch("wet_mcp.setup.logger.warning")
    def test_patch_searxng_version_exception(self, mock_warning, mock_find_dir):
        from wet_mcp.setup import patch_searxng_version

        patch_searxng_version()
        mock_warning.assert_called_once()
