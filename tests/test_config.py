"""Tests for wet_mcp.config (de-host: slim, env-driven operational knobs).

The instance config (auth mode, bind, per-task provider cells) lives in
``~/.wet/config.toml`` and is loaded via :mod:`wet_mcp.runtime` (hull-core);
this module only tests the operational ``Settings`` that remains here:
search/browser/crawler/cache knobs, path helpers, and the local-ONNX
availability toggles.
"""

import os
from unittest import mock
from unittest.mock import patch

import pytest
from pydantic_settings.sources import EnvSettingsSource

from wet_mcp.config import Settings


def _settings_env_names() -> set[str]:
    """Every env var name that ``Settings`` itself reads.

    Derived from the model instead of hand-listed. ``EnvSettingsSource`` is the
    same resolver pydantic-settings runs at ``Settings.__init__``, so it already
    accounts for ``env_prefix`` (empty in this repo) and ``case_sensitive``.
    Adding or renaming a settings field therefore updates this set automatically
    instead of silently drifting behind a hand-written list.
    """
    source = EnvSettingsSource(Settings)
    return {
        env_name.upper()
        for field_name, field in Settings.model_fields.items()
        for _, env_name, _ in source._extract_field_info(field, field_name)
    }


# Env vars that steer the config code but are NOT declared as ``Settings``
# fields, so they cannot be derived from the model and must be named by hand:
#   * ``BROWSER_BACKENDS`` -- re-read via ``os.getenv`` inside
#     ``Settings.browser_backend_chain()`` so the env beats a constructed
#     value; the chain method is the only reader.
_EXTRA_ENV_NAMES = {"BROWSER_BACKENDS"}


def _clean_env_names() -> set[str]:
    """Full set of env vars the ``clean_env`` fixture unsets."""
    return _settings_env_names() | _EXTRA_ENV_NAMES


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ensure environment isolation for configuration tests.

    Clears every env var ``Settings`` declares (derived from the model, see
    :func:`_settings_env_names`) plus the undeclared overrides that config
    code reads straight from ``os.environ`` (see :data:`_EXTRA_ENV_NAMES`).

    This runs before each test body, so a developer shell exporting e.g.
    ``BROWSER_BACKENDS`` / ``DISABLE_LOCAL_EMBED`` can no longer bake a
    leaked value into a ``Settings()`` constructed later in the test:
    pydantic-settings resolves env vars once, synchronously, inside
    ``Settings.__init__``.
    """
    vars_to_clear = _clean_env_names()
    # Thoroughly clear any variant of these keys in os.environ.
    for k in list(os.environ.keys()):
        if k.upper() in vars_to_clear:
            monkeypatch.delenv(k, raising=False)
    for v in vars_to_clear:
        monkeypatch.delenv(v, raising=False)


class TestCleanEnvCoverage:
    """Guards against the clear-list drifting behind ``Settings`` again."""

    def test_operational_knob_vars_are_derived(self):
        """The vars a hand-written list would be prone to miss."""
        derived = _settings_env_names()
        for name in (
            "SEARXNG_URL",
            "BROWSER_BACKENDS",
            "DISABLE_LOCAL_EMBED",
            "DISABLE_LOCAL_RERANK",
            "EMBEDDING_DIMS",
            "DOCS_DB_PATH",
        ):
            assert name in derived, name

    def test_deprecated_host_owned_vars_are_not_settings_fields(self):
        """Provider/auth knobs moved to ~/.wet/config.toml in the de-host.

        ``Settings`` must NOT re-declare them as env fields: host-owned
        provider keys and auth material would silently become per-process
        operational knobs again.
        """
        derived = _settings_env_names()
        for name in (
            "EMBEDDING_MODELS",
            "RERANK_MODELS",
            "LLM_MODELS",
            "DOCS_DB_BACKEND",
            "PUBLIC_URL",
            "GOOGLE_DRIVE_CLIENT_ID",
        ):
            assert name not in derived, name


def test_robots_policy_preserves_legacy_default():
    """Existing deployments keep robots checks disabled unless opted in."""
    assert Settings().respect_robots_txt is False


def test_robots_policy_reads_environment(monkeypatch):
    """RESPECT_ROBOTS_TXT is the explicit process-level policy switch."""
    monkeypatch.setenv("RESPECT_ROBOTS_TXT", "1")
    assert Settings().respect_robots_txt is True


# -----------------------------------------------------------------------
# Disable-local toggle (DISABLE_LOCAL_EMBED / DISABLE_LOCAL_RERANK)
# Availability truth table — the conflation fix, on the de-host seams.
# -----------------------------------------------------------------------


def _patch_local_onnx(available: bool):
    """Patch the image-side check used by local_embed/rerank_available."""
    return patch("wet_mcp.config.local_onnx_installed", return_value=available)


def test_embedding_unavailable_when_local_disabled_even_if_installed():
    """DISABLE_LOCAL_EMBED -> the local leg is out regardless of the image."""
    settings = Settings(disable_local_embed=True)
    with _patch_local_onnx(True):
        assert settings.local_embed_available() is False


def test_embedding_local_when_toggle_off_and_image_has_extras():
    """Toggle off + local ONNX extras installed -> local leg available."""
    settings = Settings(disable_local_embed=False)
    with _patch_local_onnx(True):
        assert settings.local_embed_available() is True


def test_embedding_unavailable_when_image_lacks_local_extras():
    """A build without the ONNX extras is out even with the toggle off."""
    settings = Settings(disable_local_embed=False)
    with _patch_local_onnx(False):
        assert settings.local_embed_available() is False


def test_rerank_unavailable_when_local_disabled_even_if_installed():
    """DISABLE_LOCAL_RERANK -> the local rerank leg is out."""
    settings = Settings(rerank_enabled=True, disable_local_rerank=True)
    with _patch_local_onnx(True):
        assert settings.local_rerank_available() is False


def test_rerank_toggle_leaves_embed_available():
    """rerank_enabled=False disables reranking but NOT the local embed leg."""
    settings = Settings(rerank_enabled=False)
    with _patch_local_onnx(True):
        assert settings.local_embed_available() is True


def test_auto_searxng_enabled_default():
    """Default: auto-spawn local SearXNG enabled."""
    assert (
        Settings(
            wet_auto_searxng=True, disable_local_search=False
        ).auto_searxng_enabled()
        is True
    )


def test_disable_local_search_suppresses_auto_spawn():
    """DISABLE_LOCAL_SEARCH suppresses the auto-spawn even with WET_AUTO_SEARXNG on."""
    assert (
        Settings(
            wet_auto_searxng=True, disable_local_search=True
        ).auto_searxng_enabled()
        is False
    )


def test_auto_searxng_disabled_when_wet_auto_off():
    assert (
        Settings(
            wet_auto_searxng=False, disable_local_search=False
        ).auto_searxng_enabled()
        is False
    )


def test_embed_and_rerank_toggles_are_independent():
    """A user may disable local embed but keep local rerank (and vice versa)."""
    with _patch_local_onnx(True):
        settings = Settings(disable_local_embed=True, disable_local_rerank=False)
        assert settings.local_embed_available() is False
        assert settings.local_rerank_available() is True

        settings = Settings(disable_local_embed=False, disable_local_rerank=True)
        assert settings.local_embed_available() is True
        assert settings.local_rerank_available() is False


# -----------------------------------------------------------------------
# Embedding dims
# -----------------------------------------------------------------------


def test_embedding_dims_field():
    """Explicit dims wins; 0 means auto-detect (server default 768)."""
    assert Settings(embedding_dims=768).embedding_dims == 768
    assert Settings(embedding_dims=0).embedding_dims == 0


def test_embedding_dims_reads_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIMS", "1024")
    assert Settings().embedding_dims == 1024


# -----------------------------------------------------------------------
# Browser backend chain
# -----------------------------------------------------------------------


def test_browser_chain_defaults_to_native():
    """Empty BROWSER_BACKENDS -> the in-process chromium leg."""
    assert Settings().browser_backend_chain() == ["native"]


def test_browser_chain_reads_env_over_field(monkeypatch):
    """The env var beats a constructed value (operator override at runtime)."""
    monkeypatch.setenv("BROWSER_BACKENDS", "browserless,native")
    assert Settings(browser_backends="native").browser_backend_chain() == [
        "browserless",
        "native",
    ]


def test_browser_chain_disable_local_drops_native(monkeypatch):
    """DISABLE_LOCAL_BROWSER drops the native leg: slim images render
    only via the self-host browserless backend."""
    monkeypatch.setenv("BROWSER_BACKENDS", "browserless,native")
    settings = Settings(disable_local_browser=True)
    assert settings.browser_backend_chain() == ["browserless"]


# -----------------------------------------------------------------------
# Path helpers: get_data_dir / get_db_path with custom paths
# -----------------------------------------------------------------------


def test_get_data_dir_custom_cache_dir(tmp_path):
    """get_data_dir returns custom cache_dir when set."""
    settings = Settings(cache_dir=str(tmp_path / "custom"))
    assert settings.get_data_dir() == tmp_path / "custom"


def test_get_data_dir_default():
    """get_data_dir returns ~/.wet when cache_dir is empty."""
    from pathlib import Path

    settings = Settings(cache_dir="")
    assert settings.get_data_dir() == Path.home() / ".wet"


def test_get_db_path_custom_docs_db_path(tmp_path):
    """get_db_path returns custom docs_db_path when set."""
    custom = tmp_path / "my_docs.db"
    settings = Settings(docs_db_path=str(custom))
    assert settings.get_db_path() == custom


def test_get_db_path_default():
    """get_db_path returns get_data_dir()/docs.db when docs_db_path is empty."""
    settings = Settings(docs_db_path="")
    assert settings.get_db_path() == settings.get_data_dir() / "docs.db"


# -----------------------------------------------------------------------
# Local model resolution helpers
# -----------------------------------------------------------------------


def test_detect_gpu_no_onnxruntime():
    """_detect_gpu returns False when onnxruntime is not available."""
    from wet_mcp.config import _detect_gpu

    with mock.patch.dict("sys.modules", {"onnxruntime": None}):
        assert _detect_gpu() is False


def test_detect_gpu_with_cuda():
    """_detect_gpu returns True when CUDAExecutionProvider is available."""
    from wet_mcp.config import _detect_gpu

    ort_mock = mock.MagicMock()
    ort_mock.get_available_providers.return_value = [
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]
    with mock.patch.dict("sys.modules", {"onnxruntime": ort_mock}):
        assert _detect_gpu() is True


def test_detect_gpu_cpu_only():
    """_detect_gpu returns False with CPU-only providers."""
    from wet_mcp.config import _detect_gpu

    ort_mock = mock.MagicMock()
    ort_mock.get_available_providers.return_value = ["CPUExecutionProvider"]
    with mock.patch.dict("sys.modules", {"onnxruntime": ort_mock}):
        assert _detect_gpu() is False


def test_has_gguf_support_missing():
    """_has_gguf_support returns False when llama_cpp is not installed."""
    from wet_mcp.config import _has_gguf_support

    with mock.patch("importlib.util.find_spec", return_value=None):
        assert _has_gguf_support() is False


def test_has_gguf_support_available():
    """_has_gguf_support returns True when llama_cpp is installed."""
    from wet_mcp.config import _has_gguf_support

    with mock.patch("importlib.util.find_spec", return_value=mock.MagicMock()):
        assert _has_gguf_support() is True


def test_resolve_local_model_onnx_fallback():
    """_resolve_local_model returns ONNX model when no GPU or no GGUF support."""
    from wet_mcp.config import _resolve_local_model

    with mock.patch("wet_mcp.config._detect_gpu", return_value=False):
        assert _resolve_local_model("onnx-model", "gguf-model") == "onnx-model"


def test_resolve_local_model_gguf():
    """_resolve_local_model returns GGUF model when GPU and llama-cpp available."""
    from wet_mcp.config import _resolve_local_model

    with (
        mock.patch("wet_mcp.config._detect_gpu", return_value=True),
        mock.patch("wet_mcp.config._has_gguf_support", return_value=True),
    ):
        assert _resolve_local_model("onnx-model", "gguf-model") == "gguf-model"


def test_resolve_local_embedding_model():
    """resolve_local_embedding_model delegates to _resolve_local_model."""
    settings = Settings()
    with mock.patch(
        "wet_mcp.config._resolve_local_model", return_value="test-model"
    ) as m:
        result = settings.resolve_local_embedding_model()
        assert result == "test-model"
        m.assert_called_once()


def test_resolve_local_rerank_model():
    """resolve_local_rerank_model delegates to _resolve_local_model."""
    settings = Settings()
    with mock.patch(
        "wet_mcp.config._resolve_local_model", return_value="test-rerank"
    ) as m:
        result = settings.resolve_local_rerank_model()
        assert result == "test-rerank"
        m.assert_called_once()


# -----------------------------------------------------------------------
# BYO local model override (LOCAL_EMBEDDING_MODEL / LOCAL_RERANK_MODEL)
# -----------------------------------------------------------------------


def test_local_embedding_model_override(monkeypatch):
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "Org/custom-embed")
    s = Settings()
    assert s.resolve_local_embedding_model() == "Org/custom-embed"


def test_local_rerank_model_override(monkeypatch):
    monkeypatch.setenv("LOCAL_RERANK_MODEL", "Org/custom-rerank")
    s = Settings()
    assert s.resolve_local_rerank_model() == "Org/custom-rerank"


# -----------------------------------------------------------------------
# Runtime-settable operational knobs (config tool "set" valid keys)
# -----------------------------------------------------------------------


def test_runtime_settable_knobs_exist():
    """The keys ``config(action='set')`` accepts are real Settings fields."""
    for key in ("log_level", "tool_timeout", "wet_cache", "wet_search_budget"):
        assert key in Settings.model_fields, key


def test_tool_timeout_reads_environment(monkeypatch):
    monkeypatch.setenv("TOOL_TIMEOUT", "30")
    assert Settings().tool_timeout == 30


def test_search_budget_reads_environment(monkeypatch):
    monkeypatch.setenv("WET_SEARCH_BUDGET", "5")
    assert Settings().wet_search_budget == 5


def test_reindex_on_model_change_reads_environment(monkeypatch):
    """B2 identity-guard override: default safe (False), env opts in."""
    assert Settings().reindex_on_model_change is False
    monkeypatch.setenv("REINDEX_ON_MODEL_CHANGE", "1")
    assert Settings().reindex_on_model_change is True


@pytest.mark.parametrize(
    ("field", "env", "value"),
    [
        ("wet_cache", "WET_CACHE", "false"),
        ("disable_local_search", "DISABLE_LOCAL_SEARCH", "1"),
        ("disable_local_embed", "DISABLE_LOCAL_EMBED", "1"),
        ("disable_local_rerank", "DISABLE_LOCAL_RERANK", "1"),
    ],
)
def test_boolean_knobs_read_environment(field, env, value, monkeypatch):
    monkeypatch.setenv(env, value)
    assert getattr(Settings(), field) is True if value == "1" else getattr(
        Settings(), field
    ) is False


def test_no_llm_provider_cells_among_settings_fields():
    """No LLM provider-key material in Settings: those are host cells now.

    The de-host moved the embedding/rerank/chat/jev_score provider keys into
    ``~/.wet/config.toml`` ([models.*] cells). A ``*_api_key`` field for a
    cloud LLM provider that sneaks back into the env-driven model would make
    host-only secret material a per-process knob again. (Search-backend and
    browserless service keys are NOT provider cells -- they stay.)"""
    llm_provider_key_fields = [
        name
        for name in Settings.model_fields
        if name
        in (
            "openai_api_key",
            "gemini_api_key",
            "google_api_key",
            "jina_ai_api_key",
            "anthropic_api_key",
            "embedding_models",
            "rerank_models",
            "llm_models",
        )
    ]
    assert llm_provider_key_fields == []
