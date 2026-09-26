"""Cloud embed/rerank gating over host-owned provider cells (de-hosted).

Providers are no longer per-request env keys resolving into a
``Settings.embedding_chain()``; the cloud gate is the ``[models.embed]``
cell's api_key (``~/.wet/config.toml``, host-injected via ``HULL_EMBED_API_KEY``)
and the factory is :func:`wet_mcp.embedder.init_backend`. These tests pin the
de-hosted gating seams; the factory's full behaviour is covered in
``tests/test_embedder.py`` / ``tests/test_reranker.py``.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest.mock
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import wet_mcp.embedder as embedder_mod
from wet_mcp.embedder import CloudEmbeddingBackend, init_backend


def test_embed_cell_key_gating_follows_host_cell_key(monkeypatch):
    """The embed gate is the cell's key: absent -> unconfigured, env key -> on.

    ``HULL_EMBED_API_KEY`` is the host-injection path (env wins over the
    config table), so a cell that is unconfigured on disk still resolves as
    configured when the host exports the key at start.
    """
    from wet_mcp.runtime import cell_configured, model_cell, reset_settings_cache

    monkeypatch.delenv("HULL_EMBED_API_KEY", raising=False)
    reset_settings_cache()
    assert cell_configured("embed") is False

    monkeypatch.setenv("HULL_EMBED_API_KEY", "k")
    reset_settings_cache()
    assert cell_configured("embed") is True
    # The cell owns the model id regardless of key presence.
    assert model_cell("embed").model


def test_cloud_backend_never_loads_local_onnx(monkeypatch):
    """A configured embed cell serves cloud embeddings without fastretrieval.

    De-host port of "cloud config must not trigger the ~570MB local ONNX
    download": building the cloud backend must not import or touch the local
    ONNX stack at all.
    """
    fake_fastretrieval = unittest.mock.MagicMock()
    monkeypatch.setitem(sys.modules, "fastretrieval", fake_fastretrieval)

    client = SimpleNamespace(cell=SimpleNamespace(model="jina_ai/jina-embeddings-v5-text-small"))
    client.embeddings = AsyncMock()
    original_backend = embedder_mod._backend
    embedder_mod._backend = None
    try:
        with (
            patch(
                "wet_mcp.runtime.cell_configured",
                lambda task, settings=None: task == "embed",
            ),
            patch("wet_mcp.runtime.provider_client", lambda task, settings=None: client),
        ):
            backend = init_backend("cloud")

        assert isinstance(backend, CloudEmbeddingBackend)
        assert backend.model == "jina_ai/jina-embeddings-v5-text-small"
        fake_fastretrieval.assert_not_called()
    finally:
        embedder_mod._backend = original_backend


def test_local_onnx_presence_treats_broken_module_specs_as_unavailable(monkeypatch):
    from wet_mcp.config import local_onnx_installed

    for error in (ValueError("__spec__ is unset"), ImportError()):
        find_spec = unittest.mock.Mock(side_effect=error)
        monkeypatch.setattr(importlib.util, "find_spec", find_spec)

        assert local_onnx_installed() is False
