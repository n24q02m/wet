import sys
from unittest import mock

from wet_mcp.config import (
    Settings,
    _detect_gpu,
    _has_gguf_support,
    _resolve_local_model,
)


def test_detect_gpu_cuda():
    """Test _detect_gpu returns True if CUDAExecutionProvider is available."""
    mock_ort = mock.MagicMock()
    mock_ort.get_available_providers.return_value = ["CUDAExecutionProvider"]

    with mock.patch.dict(sys.modules, {"onnxruntime": mock_ort}):
        assert _detect_gpu() is True


def test_detect_gpu_dml():
    """Test _detect_gpu returns True if DmlExecutionProvider is available."""
    mock_ort = mock.MagicMock()
    mock_ort.get_available_providers.return_value = ["DmlExecutionProvider"]

    with mock.patch.dict(sys.modules, {"onnxruntime": mock_ort}):
        assert _detect_gpu() is True


def test_detect_gpu_cpu_only():
    """Test _detect_gpu returns False if only CPUExecutionProvider is available."""
    mock_ort = mock.MagicMock()
    mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]

    with mock.patch.dict(sys.modules, {"onnxruntime": mock_ort}):
        assert _detect_gpu() is False


def test_detect_gpu_exception():
    """Test _detect_gpu returns False if onnxruntime raises Exception."""
    mock_ort = mock.MagicMock()
    mock_ort.get_available_providers.side_effect = Exception("Boom")

    with mock.patch.dict(sys.modules, {"onnxruntime": mock_ort}):
        assert _detect_gpu() is False


def test_detect_gpu_import_error():
    """Test _detect_gpu returns False if onnxruntime is not installed."""
    # We patch sys.modules to remove onnxruntime if present
    # And mock builtins.__import__ to raise ImportError for onnxruntime

    # However, since builtins.__import__ is tricky, we can just patch sys.modules
    # such that 'onnxruntime' is NOT in it, and rely on the fact that if it's not there,
    # python tries to find it. But we can't easily mock the loader to fail.

    # Easier: Just mock sys.modules['onnxruntime'] to be something that raises
    # ImportError on access? No.

    # If onnxruntime is in sys.modules, import uses it.
    # If not, import searches.

    # Let's try mocking builtins.__import__ properly.

    orig_import = __import__

    def side_effect(name, *args, **kwargs):
        if name == "onnxruntime":
            raise ImportError("No module named 'onnxruntime'")
        return orig_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=side_effect):
        # Temporarily remove from sys.modules to force import attempt
        with mock.patch.dict(sys.modules):
            if "onnxruntime" in sys.modules:
                del sys.modules["onnxruntime"]
            assert _detect_gpu() is False


def test_has_gguf_support_installed():
    """Test _has_gguf_support returns True if llama_cpp is importable."""
    with mock.patch("importlib.util.find_spec", return_value=mock.MagicMock()):
        assert _has_gguf_support() is True


def test_has_gguf_support_not_installed():
    """Test _has_gguf_support returns False if llama_cpp is not importable."""
    with mock.patch("importlib.util.find_spec", return_value=None):
        assert _has_gguf_support() is False


def test_resolve_local_model_gpu_gguf():
    """Test _resolve_local_model chooses GGUF if GPU and GGUF support are present."""
    with (
        mock.patch("wet_mcp.config._detect_gpu", return_value=True),
        mock.patch("wet_mcp.config._has_gguf_support", return_value=True),
    ):
        assert _resolve_local_model("onnx", "gguf") == "gguf"


def test_resolve_local_model_gpu_no_gguf():
    """Test _resolve_local_model chooses ONNX if GPU present but no GGUF support."""
    with (
        mock.patch("wet_mcp.config._detect_gpu", return_value=True),
        mock.patch("wet_mcp.config._has_gguf_support", return_value=False),
    ):
        assert _resolve_local_model("onnx", "gguf") == "onnx"


def test_resolve_local_model_no_gpu_gguf():
    """Test _resolve_local_model chooses ONNX if no GPU, even with GGUF support."""
    with (
        mock.patch("wet_mcp.config._detect_gpu", return_value=False),
        mock.patch("wet_mcp.config._has_gguf_support", return_value=True),
    ):
        assert _resolve_local_model("onnx", "gguf") == "onnx"


def test_resolve_local_model_no_gpu_no_gguf():
    """Test _resolve_local_model chooses ONNX if neither GPU nor GGUF support."""
    with (
        mock.patch("wet_mcp.config._detect_gpu", return_value=False),
        mock.patch("wet_mcp.config._has_gguf_support", return_value=False),
    ):
        assert _resolve_local_model("onnx", "gguf") == "onnx"


def test_resolve_local_embedding_model_gpu(monkeypatch):
    """Test resolve_local_embedding_model returns GGUF when GPU and GGUF available."""
    # A dev shell exporting LOCAL_EMBEDDING_MODEL (BYO override) would otherwise
    # get baked into Settings() below, short-circuiting resolve_local_embedding_model()
    # before it ever reaches the GPU/GGUF branch this test targets.
    monkeypatch.delenv("LOCAL_EMBEDDING_MODEL", raising=False)
    s = Settings()
    with (
        mock.patch("wet_mcp.config._detect_gpu", return_value=True),
        mock.patch("wet_mcp.config._has_gguf_support", return_value=True),
    ):
        result = s.resolve_local_embedding_model()
        assert "GGUF" in result
        assert "Embedding" in result


def test_resolve_local_embedding_model_no_gpu(monkeypatch):
    """Test resolve_local_embedding_model returns ONNX when no GPU."""
    monkeypatch.delenv("LOCAL_EMBEDDING_MODEL", raising=False)
    s = Settings()
    with (
        mock.patch("wet_mcp.config._detect_gpu", return_value=False),
        mock.patch("wet_mcp.config._has_gguf_support", return_value=True),
    ):
        result = s.resolve_local_embedding_model()
        assert "ONNX" in result
        assert "Embedding" in result


def test_resolve_local_rerank_model_gpu(monkeypatch):
    """Test resolve_local_rerank_model returns GGUF when GPU and GGUF available."""
    # Same leak vector as above, for the rerank BYO override.
    monkeypatch.delenv("LOCAL_RERANK_MODEL", raising=False)
    s = Settings()
    with (
        mock.patch("wet_mcp.config._detect_gpu", return_value=True),
        mock.patch("wet_mcp.config._has_gguf_support", return_value=True),
    ):
        result = s.resolve_local_rerank_model()
        assert "GGUF" in result
        assert "Reranker" in result


def test_resolve_local_rerank_model_no_gpu(monkeypatch):
    """Test resolve_local_rerank_model returns ONNX when no GPU."""
    monkeypatch.delenv("LOCAL_RERANK_MODEL", raising=False)
    s = Settings()
    with (
        mock.patch("wet_mcp.config._detect_gpu", return_value=False),
        mock.patch("wet_mcp.config._has_gguf_support", return_value=False),
    ):
        result = s.resolve_local_rerank_model()
        assert "ONNX" in result
        assert "Reranker" in result
